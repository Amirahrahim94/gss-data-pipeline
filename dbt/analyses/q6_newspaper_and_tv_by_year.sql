-- Q6. How have newspaper reading and TV viewing changed from one survey wave to the next?
-- Variables: news (how often reads a newspaper), tvhours (hours of TV per day).
-- A wave is a survey year (2016, 2018, 2022). Each respondent-year counts once even when it
-- is in both cuts. Shares and means are weighted and use real answers only; n_* shows how many
-- that is, because both questions are put to part of the sample (by ballot).

with newspaper as (

    select respondent_year_id, answer_label, is_answer
    from {{ ref('fct_response') }}
    where variable_name = 'news'

),

television as (

    select respondent_year_id, answer_number, is_answer
    from {{ ref('fct_response') }}
    where variable_name = 'tvhours'

)

select
    respondent.survey_year,
    count(*) filter (where newspaper.is_answer)                         as n_news,
    round(100 * sum(respondent.weight) filter (where newspaper.answer_label = 'Every day')
              / sum(respondent.weight) filter (where newspaper.is_answer), 1)
                                                                        as pct_news_every_day,
    round(100 * sum(respondent.weight) filter (where newspaper.answer_label = 'Never')
              / sum(respondent.weight) filter (where newspaper.is_answer), 1)
                                                                        as pct_news_never,
    count(*) filter (where television.is_answer)                        as n_tv,
    round(sum(respondent.weight * television.answer_number) filter (where television.is_answer)
          / sum(respondent.weight) filter (where television.is_answer), 2)
                                                                        as avg_tv_hours,
    round(100.0 * count(*) filter (where television.answer_number >= 4)
          / count(*) filter (where television.is_answer), 1)            as pct_tv_4_plus_hours
from {{ ref('dim_respondent') }} as respondent
inner join newspaper using (respondent_year_id)
inner join television using (respondent_year_id)
group by respondent.survey_year
order by respondent.survey_year
