-- Q6. How have newspaper reading and TV viewing changed from one survey wave to the next?
-- Variables: news (how often reads a newspaper), tvhours (hours of TV per day).
-- A wave is a survey year in the extracts (2016, 2018, 2022). Each respondent-year counts
-- once even when it is in both cuts. Shares and means are weighted and use real answers
-- only; respondents_* shows how many that is, because both questions are put to ballots a and
-- b only.
-- change_* is the difference from the previous wave in the extracts, in percentage points or
-- hours. 2016 to 2018 is two years; 2018 to 2022 is four years and spans the 2021-22 switch
-- to mixed web and in-person interviewing, so part of that change may be a mode effect.

with newspaper as (

    select respondent_year_id, answer_label, is_answer
    from {{ ref('fct_response') }}
    where variable_name = 'news'

),

television as (

    select respondent_year_id, answer_number, is_answer
    from {{ ref('fct_response') }}
    where variable_name = 'tvhours'

),

per_wave as (

    select
        respondent.survey_year,
        count(*) filter (where newspaper.is_answer)                     as respondents_news,
        round(100 * sum(respondent.weight) filter (where newspaper.answer_label = 'Every day')
                  / sum(respondent.weight) filter (where newspaper.is_answer), 1)
                                                                        as pct_news_every_day,
        round(100 * sum(respondent.weight) filter (where newspaper.answer_label = 'Never')
                  / sum(respondent.weight) filter (where newspaper.is_answer), 1)
                                                                        as pct_news_never,
        count(*) filter (where television.is_answer)                    as respondents_tv,
        round(sum(respondent.weight * television.answer_number) filter (where television.is_answer)
              / sum(respondent.weight) filter (where television.is_answer), 2)
                                                                        as avg_tv_hours,
        round(100 * sum(respondent.weight) filter (where television.answer_number >= 4)
                  / sum(respondent.weight) filter (where television.is_answer), 1)
                                                                        as pct_tv_4_plus_hours
    from {{ ref('dim_respondent') }} as respondent
    inner join newspaper using (respondent_year_id)
    inner join television using (respondent_year_id)
    group by respondent.survey_year

)

select
    survey_year,
    lag(survey_year) over (order by survey_year)                        as previous_wave,
    respondents_news,
    pct_news_every_day,
    round(pct_news_every_day - lag(pct_news_every_day) over (order by survey_year), 1)
                                                                        as change_pct_news_every_day,
    pct_news_never,
    round(pct_news_never - lag(pct_news_never) over (order by survey_year), 1)
                                                                        as change_pct_news_never,
    respondents_tv,
    avg_tv_hours,
    round(avg_tv_hours - lag(avg_tv_hours) over (order by survey_year), 2)
                                                                        as change_avg_tv_hours,
    pct_tv_4_plus_hours,
    round(pct_tv_4_plus_hours - lag(pct_tv_4_plus_hours) over (order by survey_year), 1)
                                                                        as change_pct_tv_4_plus_hours
from per_wave
order by survey_year
