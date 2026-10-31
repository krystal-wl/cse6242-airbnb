def tourist_area_distance(df):
    import time
    import numpy as np
    import pandas as pd
    from geopy.geocoders import Nominatim
    from geopy.exc import GeocoderTimedOut
    from sklearn.neighbors import BallTree # LIBRARY OPTIMIZE FOR CALCULATING DISTANCE

    # LIST OF TOURIST ATTRACTIONS IN EACH CITY (CAN ADD MORE)
    tourist_data = [
        # New York City
        ("New York City", "Times Square"),
        ("New York City", "Central Park"),
        ("New York City", "Statue of Liberty"),
        ("New York City", "Empire State Building"),
        ("New York City", "Rockefeller Center"),
        ("New York City", "Brooklyn Bridge"),
        ("New York City", "The Metropolitan Museum of Art"),
        ("New York City", "High Line"),
        ("New York City", "One World Trade Center"),
        ("New York City", "Grand Central Terminal"),
        ("New York City", "Chelsea Market"),
        ("New York City", "Madison Square Garden"),
        ("New York City", "SoHo"),
        ("New York City", "Chinatown"),
        ("New York City", "Williamsburg"),
        ("New York City", "DUMBO"),
        ("New York City", "West Village"),
        
        # Toronto
        ("Toronto", "CN Tower"),
        ("Toronto", "Royal Ontario Museum"),
        ("Toronto", "Distillery District"),
        ("Toronto", "St. Lawrence Market"),
        ("Toronto", "Casa Loma"),
        ("Toronto", "Ripley's Aquarium of Canada"),
        ("Toronto", "Toronto Islands"),
        ("Toronto", "High Park"),
        ("Toronto", "Art Gallery of Ontario"),
        ("Toronto", "Eaton Centre"),
        ("Toronto", "Yorkville"),
        ("Toronto", "Kensington Market"),
        ("Toronto", "Financial District"),
        
        # Los Angeles
        ("Los Angeles", "Hollywood Sign"),
        ("Los Angeles", "Griffith Observatory"),
        ("Los Angeles", "Universal Studios Hollywood"),
        ("Los Angeles", "Santa Monica Pier"),
        ("Los Angeles", "Venice Beach"),
        ("Los Angeles", "The Getty Center"),
        ("Los Angeles", "Walk of Fame"),
        ("Los Angeles", "The Grove"),
        ("Los Angeles", "Los Angeles County Museum of Art"),
        ("Los Angeles", "Downtown Los Angeles (DTLA)"),
        ("Los Angeles", "Universal Studios Hollywood"),
        ("Los Angeles", "Crypto.com Arena"),
        ("Los Angeles", "Dodger Stadium"),
        ("Los Angeles", "TCL Chinese Theater"),
        ("Los Angeles", "Little Tokyo"),
        ("Los Angeles", "Venice Beach"),
        ("Los Angeles", "Malibu Beach"),
        ("Los Angeles", "Echo Park"),
        ("Los Angeles", "Koreatown"),
        ("Los Angeles", "Beverly Hills"),
        
        # Boston
        ("Boston", "Freedom Trail"),
        ("Boston", "Boston Common"),
        ("Boston", "Fenway Park"),
        ("Boston", "TD Garden"),
        ("Boston", "Faneuil Hall"),
        ("Boston", "New England Aquarium"),
        ("Boston", "Museum of Fine Arts"),
        ("Boston", "USS Constitution"),
        ("Boston", "Boston Public Garden"),
        ("Boston", "North End"),
        ("Boston", "Science Museum"),
        ("Boston", "Prudential Center"),
        ("Boston", "Seaport"),
        ("Boston", "Beacon Hill"),
        
        # San Diego
        ("San Diego", "Balboa Park"),
        ("San Diego", "San Diego Zoo"),
        ("San Diego", "USS Midway Museum"),
        ("San Diego", "Gaslamp Quarter"),
        ("San Diego", "La Jolla Cove"),
        ("San Diego", "Old Town San Diego State Historic Park"),
        ("San Diego", "Coronado Beach"),
        ("San Diego", "Seaport Village"),
        ("San Diego", "Cabrillo National Monument"),
        ("San Diego", "Little Italy"),
        ("San Diego", "Petco Park"),
        ("San Diego", "Pacific Beach"),
        ("San Diego", "Ocean Beach"),
        ("San Diego", "Point Loma"),
        ("San Diego", "SeaWorld"),
        
        # Clark County, NV
        ("Clark County, NV", "The Las Vegas Strip"),
        ("Clark County, NV", "Fremont Street Experience"),
        ("Clark County, NV", "Red Rock Canyon National Conservation Area"),
        ("Clark County, NV", "The High Roller"),
        ("Clark County, NV", "Bellagio Conservatory & Botanical Gardens"),
        ("Clark County, NV", "The Sphere"),
        ("Clark County, NV", "Hoover Dam"),
        ("Clark County, NV", "Neon Museum"),
        ("Clark County, NV", "Mandalay Bay"),
        ("Clark County, NV", "Seven Magic Mountains"),
        ("Clark County, NV", "Strat Hotel")
    ]
    
    # CREATE DATAFRAME FOR THE TOURIST ATTRACTIONS
    df_attractions = pd.DataFrame(tourist_data, columns=['city', 'attraction'])
    
    
    # INITIATE LOCATOR FOR RETRIEVING THE LATITUDE AND LONGITUDE OF TOURIST ATTRACTION
    locator = Nominatim(user_agent="my_tourist_app_analytics")
    
    latitudes = []
    longitudes = []
    
    for idx, row in df_attractions.iterrows():
        # COMBINE ATTRACTION AND CITY TO ENSURE THE CORRECTLOCATION IS PULLED
        query = f"{row['attraction']}, {row['city']}"
        
        try:
            location = locator.geocode(query)
            if location:
                latitudes.append(location.latitude)
                longitudes.append(location.longitude)
            else:
                latitudes.append(None)
                longitudes.append(None)
        except GeocoderTimedOut:
            latitudes.append(None)
            longitudes.append(None)
        
        # SLEEP FOR 1 SECOND DUE TO NOMINATIM USAGE POLICY
        time.sleep(1)
    
    df_attractions['latitude'] = latitudes
    df_attractions['longitude'] = longitudes

    # DROP ANY TOURIST ATTRACTIONS THAT WERE NOT FOUND 
    df_attractions.dropna(inplace=True)
    
    # CALCULATE THE DISTANCE TO THE CLOSEST TOURIST ATTRACTION TO LISTING  
    kms_per_radian = 6371.0

    attraction_coords = np.radians(df_attractions[['latitude', 'longitude']].values)
    airbnb_coords = np.radians(df[['latitude', 'longitude']].values)
    
    # CREATE THE BALLTREE USING THE TOURIST ATTRACTION COORDINATE
    tree = BallTree(attraction_coords, metric='haversine')
    
    # FIND THE CLOSEST ATTRACTION TO EACH LISTING
    distances_rad, indices = tree.query(airbnb_coords, k=1)
    
    df['dist_to_nearest_attraction_km'] = distances_rad.flatten() * kms_per_radian
    nearest_indices = indices.flatten()

    # RETURN THE NAME OF THE CLOSEST ATTRACTION FOR SANITY CHECK
    df['nearest_attraction'] = df_attractions.iloc[nearest_indices]['attraction'].values

    return df
