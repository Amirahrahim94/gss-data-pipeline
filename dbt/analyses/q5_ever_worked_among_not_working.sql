-- Q5. Among respondents who are not currently working, what share have ever worked for 12
-- months or more?  Variables: wrkstat (work_status and is_working in dim_respondent), evwork
-- (ever worked as long as one year; almost only people not working have an answer).
-- Not working = a real wrkstat answer other than working: retired, keeping house, unemployed,
-- in school, other. "With a job but not at work" counts as working.
-- pct_yes_of_answered is weighted, among YES and NO answers.
-- Nearly all unemployed respondents are ".i" for evwork (the reason is not in the extract),
-- so their rows land in not_asked, not in no_usable_answer, and the "All not working" share
-- is in practice a share of the retired, keeping house, in school and other groups.

with ever_worked as (

    select respondent_year_id, answer_label, is_answer, response_type
    from {{ ref('fct_response') }}
    where variable_name = 'evwork'

)

select
    coalesce(respondent.work_status, 'All not working')            as work_status,
    count(*)                                                       as respondents,
    count(*) filter (where ever_worked.answer_label = 'YES')       as yes_count,
    count(*) filter (where ever_worked.answer_label = 'NO')        as no_count,
    count(*) filter (where ever_worked.response_type in
        ('inapplicable', 'not_asked_on_ballot', 'unavailable_that_year')) as not_asked,
    count(*) filter (where not ever_worked.is_answer and ever_worked.response_type not in
        ('inapplicable', 'not_asked_on_ballot', 'unavailable_that_year')) as no_usable_answer,
    round(100 * sum(respondent.weight) filter (where ever_worked.answer_label = 'YES')
              / sum(respondent.weight) filter (where ever_worked.is_answer), 1)
                                                                   as pct_yes_of_answered
from {{ ref('dim_respondent') }} as respondent
inner join ever_worked using (respondent_year_id)
where not respondent.is_working
group by rollup (respondent.work_status)
order by respondents desc
