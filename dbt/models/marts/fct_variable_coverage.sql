{#- Where each variable is valid: for every variable, survey year and ballot, how many
    respondents gave a real answer, how many were not asked or it did not apply, and how many
    gave no usable answer. Built from the data and the ref_codes response types, so a new
    variable appears here with no change. is_asked is true when anyone answered. -#}

select
    answers.variable_name,
    respondent.survey_year,
    respondent.ballot,
    count(*)                                                          as respondents,
    count(*) filter (where answers.is_answer)                         as answered,
    count(*) filter (where answers.response_type in
        ('inapplicable', 'unavailable_that_year', 'unavailable_in_release'))
                                                                      as not_asked_or_not_applicable,
    count(*) filter (where not answers.is_answer and answers.response_type not in
        ('inapplicable', 'unavailable_that_year', 'unavailable_in_release'))
                                                                      as no_usable_answer,
    round(100.0 * count(*) filter (where answers.is_answer) / count(*), 1) as pct_answered,
    count(*) filter (where answers.is_answer) > 0                     as is_asked
from {{ ref('fct_response') }} as answers
inner join {{ ref('dim_respondent') }} as respondent using (respondent_year_id)
group by answers.variable_name, respondent.survey_year, respondent.ballot
