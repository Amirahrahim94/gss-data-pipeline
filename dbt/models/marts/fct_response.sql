{#- One row per respondent-year per question: the answer, its code and what kind of answer
    it is. Missing kinds stay as rows with is_answer = false, so a query can count "not asked"
    separately from real answers. Adding a variable to the extract and to the answer_variables
    setting adds its rows here with no change to this model.

    Rows are stored sorted by variable_name. Every analysis filters on one variable at a time,
    and DuckDB keeps a min/max per row group (about 122,880 rows), so sorted rows let a filter
    skip the row groups that cannot hold that variable. On a 100x copy of this table Q1 read
    8 of 129 row groups per scan instead of 129 (report, section 7). That copy tests the
    layout only; repeated rows are not a realistic full-scale benchmark. -#}

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
order by variable_name, survey_year
