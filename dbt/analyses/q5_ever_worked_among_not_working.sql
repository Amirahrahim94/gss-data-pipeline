-- Q5. Among respondents who are not currently working, what share have ever worked for 12
-- months or more?  Variables: wrkstat (labor force status), evwork (ever worked as long as
-- one year; only put to people who are not working).
-- Not working = retired, keeping house, unemployed, in school, other. "With a job but not at
-- work" counts as working. pct_yes_of_answered is weighted, among YES and NO answers.

with not_working as (

    select respondent_year_id, answer_label as work_status
    from {{ ref('fct_response') }}
    where variable_name = 'wrkstat'
      and answer_label in (
          'Retired',
          'Keeping house',
          'Unemployed, laid off, looking for work',
          'In school',
          'Other'
      )

),

ever_worked as (

    select respondent_year_id, answer_label, is_answer
    from {{ ref('fct_response') }}
    where variable_name = 'evwork'

)

select
    coalesce(not_working.work_status, 'All not working') as work_status,
    count(*)                                                       as respondents,
    count(*) filter (where ever_worked.answer_label = 'YES')       as yes_count,
    count(*) filter (where ever_worked.answer_label = 'NO')        as no_count,
    count(*) filter (where not ever_worked.is_answer)              as no_usable_answer,
    round(100 * sum(respondent.weight) filter (where ever_worked.answer_label = 'YES')
              / sum(respondent.weight) filter (where ever_worked.is_answer), 1)
                                                                   as pct_yes_of_answered
from not_working
inner join ever_worked using (respondent_year_id)
inner join {{ ref('dim_respondent') }} as respondent using (respondent_year_id)
group by rollup (not_working.work_status)
order by respondents desc
