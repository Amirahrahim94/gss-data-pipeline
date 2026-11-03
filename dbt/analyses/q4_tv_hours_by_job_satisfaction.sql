-- Q4. Is time spent watching TV related to job satisfaction?
-- Variables: tvhours (hours per day), satjob (work satisfaction; asked of people with a job).
-- Only respondents with a real answer to both are counted; n shows the group size.
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
    count(*)                                              as n,
    round(avg(television.tv_hours), 2)                    as avg_tv_hours,
    round(sum(respondent.weight * television.tv_hours) / sum(respondent.weight), 2)
                                                          as weighted_avg_tv_hours,
    round(100.0 * count(*) filter (where television.tv_hours >= 4) / count(*), 1)
                                                          as pct_4_plus_hours
from satisfaction
inner join television using (respondent_year_id)
inner join {{ ref('dim_respondent') }} as respondent using (respondent_year_id)
group by satisfaction.satisfaction_code, satisfaction.job_satisfaction
order by satisfaction.satisfaction_code
