-- Q4. Is time spent watching TV related to job satisfaction?
-- Variables: tvhours (hours per day), satjob (work satisfaction), wrkstat (is_working in
-- dim_respondent). satjob is also answered by people keeping house and by some who are
-- unemployed, and may not then describe a current job, so only working respondents are
-- counted. Only respondents with a real answer to both satjob and tvhours are counted.
-- avg_tv_hours and pct_tv_4_plus_hours are weighted; unweighted_avg_tv_hours is shown for
-- comparison and respondents is the unweighted group size. The years are pooled, so a
-- difference between years in either variable is mixed into the comparison.
-- This describes an association in the sample, not a cause.

with satisfaction as (

    select respondent_year_id, answer_code as satisfaction_code, answer_label as job_satisfaction
    from {{ ref('fct_response') }}
    where variable_name = 'satjob' and is_answer

),

television as (

    select respondent_year_id, answer_number as tv_hours
    from {{ ref('fct_response') }}
    where variable_name = 'tvhours' and is_answer

)

select
    satisfaction.job_satisfaction,
    count(*)                                              as respondents,
    round(avg(television.tv_hours), 2)                    as unweighted_avg_tv_hours,
    round(sum(respondent.weight * television.tv_hours) / sum(respondent.weight), 2)
                                                          as avg_tv_hours,
    round(100 * sum(respondent.weight) filter (where television.tv_hours >= 4)
              / sum(respondent.weight), 1)                as pct_tv_4_plus_hours
from {{ ref('dim_respondent') }} as respondent
inner join satisfaction using (respondent_year_id)
inner join television using (respondent_year_id)
where respondent.is_working
group by satisfaction.satisfaction_code, satisfaction.job_satisfaction
order by satisfaction.satisfaction_code
