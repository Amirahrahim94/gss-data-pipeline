-- ref_variable_validity must describe the data that is loaded: every variable, year and
-- ballot in the response table has a seed row, and is_asked is true exactly where someone
-- gave a real answer. Fails when a new extract arrives and the seeds were not rebuilt with
-- source/pipeline/build_reference_seeds.py.
with observed as (

    select
        answers.variable_name,
        answers.survey_year,
        answers.ballot,
        bool_or(answers.response_type = 'answer') as has_answer
    from {{ ref('int_gss__responses_long') }} as answers
    group by answers.variable_name, answers.survey_year, answers.ballot

)

select
    observed.variable_name,
    observed.survey_year,
    observed.ballot,
    observed.has_answer,
    validity.is_asked
from observed
left join {{ ref('ref_variable_validity') }} as validity
    on validity.variable_name = observed.variable_name
   and validity.survey_year = observed.survey_year
   and validity.ballot = observed.ballot
where validity.is_asked is null
   or validity.is_asked <> observed.has_answer
