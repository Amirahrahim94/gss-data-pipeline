{#- One row per respondent-year: who the respondent is, which ballot and weight they carry.
    Age comes from the classified long table: age_number is the age in years, 89 for the
    top-coded "89 or older", and null for any missing kind. -#}

select
    s.respondent_year_id,
    s.survey_year,
    s.respondent_id,
    s.ballot,
    s.weight,
    s.extract_count,
    s.sex,
    s.region,
    s.educ,
    a.answer_number as age_number,
    a.response_type as age_response_type
from {{ ref('stg_gss__respondents') }} as s
left join {{ ref('int_gss__responses_long') }} as a
    on a.respondent_year_id = s.respondent_year_id
   and a.variable_name = 'age'
