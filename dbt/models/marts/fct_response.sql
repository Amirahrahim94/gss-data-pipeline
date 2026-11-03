{#- One row per respondent-year per question: the answer, its code and what kind of answer
    it is. Missing kinds stay as rows with is_answer = false, so a query can count "not asked"
    separately from real answers. Adding a variable to the extract and to the answer_variables
    setting adds its rows here with no change to this model. -#}

select
    respondent_year_id,
    survey_year,
    variable_name,
    answer_label,
    answer_code,
    answer_number,
    response_type,
    response_type = 'answer' as is_answer
from {{ ref('int_gss__responses_long') }}
