def amenities_breakout(df):
    import pandas as pd
    import ast

    df['amenities'] = df.amenities.apply(lambda x: ast.literal_eval(x))
    df1 = df[['id','amenities']].explode('amenities').copy()

    laundry_pattern = r'^(?!.*(?:dishwasher|hair\s*dryer)).*?(?:washer|dryer)'
    free_parking_pattern1 = r'^(?=.*free)(?=.*parking)'
    free_parking_pattern2 = r'^(?=.*free)(?=.*garage)'
    paid_parking_pattern = r'^(?=.*paid)(?=.*parking)'
    paid_housekeeping_pattern1 = r'^(?=.*paid)(?=.*housekeeping)'
    paid_housekeeping_pattern2 = r'^(?=.*housekeeping)(?=.*extra cost)'
    pool_pattern1 = r'(?:(?:outdoor|indoor)\s+pool|hot\s+tub)'
    pool_pattern2 = r'(?:(?:shared|private)\s+pool)'
    pool_pattern3 = r'^pool$'
    wifi_pattern = r'wi[- ]?fi'
    breakfast_pattern = r'(?i)(?=.*\bbreakfast\b)(?=.*\bfree\b)'
    
    df1.loc[df1['amenities'].str.contains('TV', na=False), 'amenities'] = 'TV & Streaming'
    df1.loc[df1['amenities'].str.contains('AC', na=False), 'amenities'] = 'Climate Control'
    df1.loc[df1['amenities'].str.contains('game', case=False, na=False), 'amenities'] = 'Entertainment'
    df1.loc[df1['amenities'].str.contains('pool table', case=False, na=False), 'amenities'] = 'Entertainment'
    df1.loc[df1['amenities'].str.contains('movie theater', case=False, na=False), 'amenities'] = 'Entertainment'
    df1.loc[df1['amenities'].str.contains('ping pong table', case=False, na=False), 'amenities'] = 'Entertainment'
    df1.loc[df1['amenities'].str.contains('view', case=False, na=False), 'amenities']= 'Outdoor & Views'
    df1.loc[df1['amenities'].str.contains('grill', case=False, na=False), 'amenities']= 'Grill'
    df1.loc[df1['amenities'].str.contains('backyard', case=False, na=False), 'amenities']= 'Outdoor & Views'
    df1.loc[df1['amenities'].str.contains('outdoor', case=False, na=False), 'amenities']= 'Outdoor & Views'
    df1.loc[df1['amenities'].str.contains('balcony', case=False, na=False), 'amenities']= 'Outdoor & Views'
    df1.loc[df1['amenities'].str.contains('patio', case=False, na=False), 'amenities']= 'Outdoor & Views'
    df1.loc[df1['amenities'].str.contains('beach', case=False, na=False), 'amenities']= 'Outdoor & Views'
    df1.loc[df1['amenities'].str.contains('fire pit', case=False, na=False), 'amenities']= 'Outdoor & Views'
    df1.loc[df1['amenities'].str.contains('gym', case=False, na=False), 'amenities'] = 'Exercise Facilities & Equipment'
    df1.loc[df1['amenities'].str.contains('sauna', case=False, na=False), 'amenities'] = 'Luxury & Recreation'
    df1.loc[df1['amenities'].str.contains('spa', case=False, na=False), 'amenities'] = 'Luxury & Recreation'
    df1.loc[df1['amenities'].str.contains('fridge', case=False, na=False), 'amenities'] = 'Fridge & Freezer'
    df1.loc[df1['amenities'].str.contains('refrig', case=False, na=False), 'amenities'] = 'Fridge & Freezer'
    df1.loc[df1['amenities'].str.contains('freezer', case=False, na=False), 'amenities'] = 'Fridge & Freezer'
    df1.loc[df1['amenities'].str.contains('stove', case=False, na=False), 'amenities'] = 'Cooking Appliances'
    df1.loc[df1['amenities'].str.contains('oven', case=False, na=False), 'amenities'] = 'Cooking Appliances'
    df1.loc[df1['amenities'].str.contains('kitchen', case=False, na=False), 'amenities'] = 'Cooking Appliances'
    df1.loc[df1['amenities'].str.contains('body soap', case=False, na=False), 'amenities'] = 'Toiletries'
    df1.loc[df1['amenities'].str.contains('shampoo', case=False, na=False), 'amenities'] = 'Toiletries'
    df1.loc[df1['amenities'].str.contains('conditioner', case=False, na=False), 'amenities'] = 'Toiletries'
    df1.loc[df1['amenities'].str.contains('baby ', case=False, na=False), 'amenities'] = 'Family & Pet Amenities'
    df1.loc[df1['amenities'].str.contains('children', case=False, na=False), 'amenities'] = 'Family & Pet Amenities'
    df1.loc[df1['amenities'].str.contains('exercise equipment', case=False, na=False), 'amenities'] = 'Exercise Facilities & Equipment'
    df1.loc[df1['amenities'].str.contains('coffee', case=False, na=False), 'amenities'] = 'Coffee'
    df1.loc[df1['amenities'].str.contains('ethernet', case=False, na=False), 'amenities'] = 'Connectivity'
    df1.loc[df1['amenities'].str.contains('air conditioning', case=False, na=False), 'amenities'] = 'Climate Control'
    df1.loc[df1['amenities'].str.contains('ac unit', case=False, na=False), 'amenities'] = 'Climate Control'

    df1.loc[df1['amenities'].str.contains(laundry_pattern, case=False, regex=True, na=False), 'amenities'] = 'Laundry'
    df1.loc[df1['amenities'].str.contains(breakfast_pattern, case=False, regex=True, na=False), 'amenities'] = 'Breakfast'
    df1.loc[df1['amenities'].str.contains(free_parking_pattern1, case=False, regex=True, na=False), 'amenities'] = 'Parking & Facilities'
    df1.loc[df1['amenities'].str.contains(free_parking_pattern2, case=False, regex=True, na=False), 'amenities'] = 'Parking & Facilities'
    df1.loc[df1['amenities'].str.contains(paid_parking_pattern, case=False, regex=True, na=False), 'amenities'] = 'Paid Parking'
    df1.loc[df1['amenities'].str.contains(paid_housekeeping_pattern1, case=False, regex=True, na=False), 'amenities'] = 'Paid Housekeeping'
    df1.loc[df1['amenities'].str.contains(paid_housekeeping_pattern2, case=False, regex=True, na=False), 'amenities'] = 'Paid Housekeeping'
    df1.loc[df1['amenities'].str.contains(pool_pattern1, case=False, regex=True, na=False), 'amenities'] = 'Luxury & Recreation'
    df1.loc[df1['amenities'].str.contains(pool_pattern2, case=False, regex=True, na=False), 'amenities'] = 'Luxury & Recreation'
    df1.loc[df1['amenities'].str.contains(pool_pattern3, case=False, regex=True, na=False), 'amenities'] = 'Luxury & Recreation'
    df1.loc[df1['amenities'].str.contains(wifi_pattern, case=False, regex=True, na=False), 'amenities'] = 'Connectivity'

    df1.drop_duplicates(inplace=True)

    amenities = ['TV & Streaming', 'Entertainment', 'Outdoor & Views', 'Grill', 'Luxury & Recreation', 'Cooking Appliances', 'Climate Control',
                 'Exercise Facilities & Equipment', 'Parking & Facilities', 'Laundry', 'Connectivity', 'Breakfast', 'Fridge & Freezer']

    df1 = df1[df1.amenities.isin(amenities)]
    df1['values'] = 1
    df1_pivot = df1.pivot(index='id',columns='amenities', values='values').fillna(0).reset_index()

    merged_df = pd.merge(df, df1_pivot, on='id', how='left')
    merged_df[amenities] = merged_df[amenities].fillna(0)
    
    return merged_df
