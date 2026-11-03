-- A respondent-year has at most one row per question.
select respondent_year_id, variable_name, count(*) as n
from {{ ref('fct_response') }}
group by respondent_year_id, variable_name
having count(*) > 1
