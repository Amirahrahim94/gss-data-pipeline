{#- One row per respondent-year per question: the answers in long form, each one classified.

    Staging holds each answer as the text received. Here every answer is turned into a row and
    matched to ref_codes by (variable, label) to get its code and response_type:
      - 'answer'            a real answer
      - a missing kind      e.g. 'inapplicable', 'no_answer', 'dont_know'
      - 'not_asked_on_ballot'  the source says ".i: Inapplicable", and ref_variable_validity
                               shows nobody on this ballot answered it in this year. This
                               is derived from observed coverage, not read from the
                               questionnaires: it is an inference until verified there.
                               The GSS uses ".i" for both "not on your ballot" and "did not
                               apply to you"; the seed separates them so neither is mistaken
                               for the other. ".i" on a ballot that was asked stays
                               'inapplicable'.
      - 'answer' with answer_number   a numeric answer the code list does not enumerate
                                      (age 45, tvhours 3) for the variables in numeric_variables;
                                      listed labels such as "0 hours" or "89 or older" take their
                                      code as the number (0 and 89, the top-coded age)
      - 'null_in_source'    the extract holds no value at all
      - 'unmapped'          anything else; a test fails if this ever appears
    ref_codes can hold the same label under two codes (indus10 "Uncodeable" is 9890 and 9997).
    The label alone cannot say which was meant, so answer_code stays NULL and code_is_ambiguous
    is true; the lookup is grouped by label, so the join never multiplies rows. If the two codes
    also differ in response_type, response_type is 'ambiguous_label'. Nothing is dropped:
    missing kinds stay as rows so the analysis can choose what to exclude. -#}

with respondents as (

    select * from {{ ref('stg_gss__respondents') }}

),

long_form as (

    {% for variable in var('answer_variables') %}
    select
        respondent_year_id, survey_year, respondent_id, ballot, weight,
        '{{ variable }}'                  as variable_name,
        cast({{ variable }} as varchar)   as answer_label
    from respondents
    {{ "union all" if not loop.last }}
    {% endfor %}

),

code_lookup as (

    select
        variable_name,
        label,
        count(*) > 1                                           as code_is_ambiguous,
        case when count(*) = 1 then min(code) end              as answer_code,
        case when min(response_type) = max(response_type)
             then min(response_type) else 'ambiguous_label' end as response_type
    from {{ ref('ref_codes') }}
    group by variable_name, label

),

validity as (

    select variable_name, survey_year, ballot, is_asked
    from {{ ref('ref_variable_validity') }}

)

select
    l.respondent_year_id,
    l.survey_year,
    l.respondent_id,
    l.ballot,
    l.weight,
    l.variable_name,
    l.answer_label,
    c.answer_code,
    coalesce(c.code_is_ambiguous, false) as code_is_ambiguous,
    case
        when l.answer_label is null then 'null_in_source'
        when c.response_type = 'inapplicable' and v.is_asked = false then 'not_asked_on_ballot'
        when c.response_type is not null then c.response_type
        when l.variable_name in ({{ "'" ~ var('numeric_variables') | join("', '") ~ "'" }})
             and try_cast(l.answer_label as double) is not null then 'answer'
        else 'unmapped'
    end as response_type,
    case
        when l.variable_name in ({{ "'" ~ var('numeric_variables') | join("', '") ~ "'" }})
             and (c.response_type = 'answer' or c.response_type is null)
        then coalesce(try_cast(l.answer_label as double), c.answer_code)
    end as answer_number
from long_form as l
left join code_lookup as c
    on c.variable_name = l.variable_name
   and c.label = l.answer_label
left join validity as v
    on v.variable_name = l.variable_name
   and v.survey_year = l.survey_year
   and v.ballot = l.ballot
