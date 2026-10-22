
# Feature Selection (Notes on Wang & Nicolau (2017))

Krystal, Oct 22, 2026

Paper: Wang, D., & Nicolau, J. L. (2017). Price determinants of sharing economy based accommodation rental:
A study of listings from 33 cities on Airbnb.com. *International Journal of Hospitality Management*, 62, 120–131.

## What they did

They took about 180k Inside Airbnb listings from 33 cities (2015–16, only listings with at least one
review) and looked at what drives price. The target was log price per person per night, with 25
variables. Besides regular OLS they used quantile regression, so they could see whether an effect is
different for cheap and expensive listings.

## Their variables vs. our data

Most of what they used, we also have. The numbers are their OLS estimates (% change in price).

| Their variable                  | Their result                       | Our column                 | Do we have it?                                          |
| ------------------------------- | ---------------------------------- | -------------------------- | ------------------------------------------------------- |
| **Host**                  |                                    |                            |                                                         |
| Superhost                       | +9%, bigger for cheap listings     | `host_is_superhost`      | Yes                                                     |
| Host listings count             | small, positive                    | `host_listings_count`    | Yes                                                     |
| Host profile picture            | −11%                              | `host_has_profile_pic`   | Yes, but almost every host has one                      |
| Verified ID                     | +9%                                | `host_identity_verified` | Yes                                                     |
| **Property and location** |                                    |                            |                                                         |
| Distance to city centre         | −0.6% per km                      | from lat/lon               | Yes                                                     |
| Property type (3 groups)        | apartments ~8% cheaper than houses | `property_type`          | Yes, needs grouping                                     |
| Entire home / private room      | +145% / +41% vs. shared room       | `room_type`              | Yes                                                     |
| Guests                          | +6% per guest                      | `accommodates`           | Yes                                                     |
| Bathrooms                       | +11%                               | `bathrooms_text`         | Yes, needs parsing (`bathrooms` is empty in Sep 2026) |
| Bedrooms                        | +12%                               | `bedrooms`               | Yes                                                     |
| **Amenities and rules**   |                                    |                            |                                                         |
| Wi-Fi                           | +10%                               | `amenities`              | Can get it                                              |
| Free parking                    | +8%                                | `amenities`              | Can get it                                              |
| Smoking allowed                 | −23%                              | `amenities`              | Probably, need to check                                 |
| Breakfast                       | −1%                               | `amenities`              | Can get it                                              |
| Real bed                        | +16%                               | —                         | No                                                      |
| Instant booking                 | −6%                               | `instant_bookable`       | No, empty in 2026                                       |
| Cancellation policy             | +5%                                | —                         | No                                                      |
| Guest photo / phone required    | none / +2%                         | —                         | No                                                      |
| **Reviews**               |                                    |                            |                                                         |
| Reviews per year                | negative                           | `reviews_per_month`      | Yes, but see below                                      |
| Overall review score            | +0.9% per point                    | `review_scores_rating`   | Yes                                                     |

So 12 we have, 4 we can pull from `amenities`, and 5 we don't have.

## Where it agrees with features.md

Most of Rui's calls hold up.

| features.md says                             | The paper                                                                                               |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `accommodates` is the strongest column     | +6% per guest, at every price level                                                                     |
| Use `room_type`                            | Biggest effect in the paper                                                                             |
| Use distance to centre in the linear model   | −0.6% per km                                                                                           |
| Use bedrooms and bathrooms                   | +12% and +11%                                                                                           |
| Group `property_type`                      | They grouped it too (3 groups)                                                                          |
| Use host listings count                      | Small positive effect                                                                                   |
| Superhost is weak but keep it                | Actually about +9%, so definitely keep it                                                               |
| Use the overall review score                 | +0.9% per point                                                                                         |
| Don't use `review_scores_value`            | They didn't use it either                                                                               |
| Recent review counts are for validation only | More reviews go with lower prices because cheap places get booked more, so review counts react to price |
| Model log price                              | Same                                                                                                    |

## Where it doesn't

| # | features.md says                             | The paper                                                                                                 | What I'd do                                                                                               |
| - | -------------------------------------------- | --------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| 1 | Set `amenities` aside for now              | Three of the four amenities they tested had clear effects                                                 | Add a handful of flags (Wi-Fi, parking, smoking, maybe a few more) once we check they show up in our data |
| 2 | Profile picture and verified ID are weak     | −11% and +9%                                                                                             | Keep them as candidates and test them in the model (profile picture barely varies, though)                |
| 3 | Use lifetime `number_of_reviews`           | Their reviews per year is basically lifetime reviews / years listed, and it shows the same reverse effect | features.md already suggests a model without any review count. I think we should actually run it          |
| 4 | Use the location score and the overall score | They kept only the overall score because the sub-scores overlap too much                                  | Check VIF before putting both in the linear model, or leave sub-scores to the random forest               |
| 5 | Fold shared rooms into private rooms         | Private rooms cost ~40% more than shared rooms                                                            | Fine since shared rooms are rare, just note it                                                            |

**Why 2 happens:** features.md scores each column against price on its own. The paper looks at each
variable with the others held fixed, and the two can disagree. Superhost barely correlates with price by
itself (0.06) but adds about 9% once room type, size and location are in the model. So I'd test the
"weak" columns inside the model before dropping them.

## Things we can borrow

- **Quantile regression.** Effects change with price level: superhost, Wi-Fi and parking matter more for
  cheap places; bathrooms, bedrooms and distance matter more for expensive ones. Also a good reason to
  report our errors by price tier.
- **Model checks.** VIF below 10, and robust standard errors (they used White SEs; in statsmodels that's
  `cov_type="HC3"`, or cluster by host).
- **Sample filter.** They only kept listings with a review. We could try that as a robustness check
  (70–84% of our listings have one).

## What we do that they didn't

Useful for the report:

- Results per city. The paper itself says it didn't look into city differences.
- Our price is a quote for specific dates and a specific stay length, so we control for monthly quotes
  and how far ahead the quote is.
- We drop leaky columns (revenue, occupancy, recent reviews).
- Review text, not just ratings.

## For the meeting

1. Bring amenities back in a limited way?
2. Test the "weak" columns in the model before dropping them?
3. Add the no-review-count model and the VIF check to notebook 03.

## Next step

Check how often Wi-Fi, free parking, breakfast and smoking show up in `amenities` in the Sep 2026 snapshot.
