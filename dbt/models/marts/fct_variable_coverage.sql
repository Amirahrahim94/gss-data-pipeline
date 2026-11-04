{#- Where each variable is valid: for every variable, survey year and ballot, how many
    respondents gave a real answer, how many were not asked or it did not apply, and how many
    gave no usable answer. is_asked comes from the ref_variable_validity seed, the
    machine-readable record of where a question was answered (observed in the data, not
    verified against the questionnaires); the assert_validity_seed_matches_data
    test checks the seed against these counts. A new variable appears here with no change. -#}

select
    answers.variable_name,
    respondent.survey_year,
    respondent.ballot,
    count(*)                                                          as respondents,
    count(*) filter (where answers.is_answer)                         as answered,
    count(*) filter (where answers.response_type in
        ('not_asked_on_ballot', 'unavailable_that_year', 'unavailable_in_release'))
                                                                      as not_asked,
    count(*) filter (where answers.response_type = 'inapplicable')    as inapplicable,
    count(*) filter (where not answers.is_answer and answers.response_type not in
        ('not_asked_on_ballot', 'unavailable_that_year', 'unavailable_in_release',
         'inapplicable'))
                                                                      as no_usable_answer,
    round(100.0 * count(*) filter (where answers.is_answer) / count(*), 1) as unweighted_pct_answered,
    validity.is_asked
from {{ ref('fct_response') }} as answers
inner join {{ ref('dim_respondent') }} as respondent using (respondent_year_id)
left join {{ ref('ref_variable_validity') }} as validity
    on validity.variable_name = answers.variable_name
   and validity.survey_year = respondent.survey_year
   and validity.ballot = respondent.ballot
group by answers.variable_name, respondent.survey_year, respondent.ballot, validity.is_asked
