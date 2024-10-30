import requests
import math
import logging
import os
from collections import defaultdict

# Set up logging
# logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# STATIC VARS
GRAPHQL_URL = "https://api.regolith.rocks"
CONFFILE = "regolith.conf"

# Read API key from file, handle creation if necessary
if not os.path.isfile(CONFFILE):
  API_KEY = str(input("\nInsérer la clé API trouvable sur https://regolith.rocks/profile/api : "))
  open(CONFFILE, "w").writelines(API_KEY)
else:
  f = open(CONFFILE, "r")
  API_KEY = f.readlines()
  for line in API_KEY:
      API_KEY = line.replace("\n", "")

# GraphQL query
query = """
{
  profile {
    joinedSessions {
      items {
        sessionId
        name
        workOrders {
          nextToken
          items {
            ... on ShipMiningOrder {
              shipOres {
                ore
                yield
              }
              isSold
              seller {
                scName
                userId
              }
              orderId
            }
          }
        }
      }
      nextToken
    }
    mySessions {
      items {
        sessionId
        name
        workOrders {
          nextToken
          items {
            ... on ShipMiningOrder {
              shipOres {
                ore
                yield
              }
              isSold
              seller {
                scName
                userId
              }
              orderId
            }
          }
        }
      }
      nextToken
    }
  }
}
"""

def log_debug(message):
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(message)

# Function to execute the GraphQL query
def fetch_graphql_data(query):
    headers = {
        "x-api-key": API_KEY,
        "Content-Type": "application/json"
    }
    try:
      response = requests.post(GRAPHQL_URL, json={'query': query}, headers=headers)
      response.raise_for_status()  # Raise an error for bad responses
    except requests.exceptions.HTTPError as http_err:
        if response.status_code == 500:
            raise SystemExit(f"Il y a un problème pour accéder à l'api, vérifier la clé dans le fichier {CONFFILE}")
    else:
        return response.json()

# Function to process sessions and aggregate yields
def process_sessions(data):
    joined_sessions = {session['sessionId']: session for session in data['data']['profile']['joinedSessions']['items']}
    my_sessions = {session['sessionId']: session for session in data['data']['profile']['mySessions']['items']}

    log_debug(f"Joined Sessions: {joined_sessions}")
    log_debug(f"My Sessions: {my_sessions}")

    seller_yields = defaultdict(lambda: defaultdict(float))  # seller -> scName -> ore -> yield
    seller_totals = defaultdict(float)  # seller -> scName -> total SCU
    available_sellers = set()  # To keep track of sellers with isSold: false
    active_sessions = set()  # Keep ids of sessions w/ ores pending sale

    # Process sessions: prioritize mySessions over joinedSessions
    for session_id, session in my_sessions.items():
        session_name = session['name']
        log_debug(f"Processing session: {session_name} - {session_id}")
        
        for order in session['workOrders']['items']:
            log_debug(f"Processing work order: {order['orderId']} - {session_name}")

            if order['isSold'] is False or order['isSold'] is None:
                seller_name = order['seller']['scName']
                available_sellers.add(seller_name)  # Track available sellers

                if session_id not in active_sessions:
                    active_sessions.add(session_id)
                
                for ore_data in order['shipOres']:
                    ore_type = ore_data['ore']
                    yield_value = ore_data['yield']
                    log_debug(f"Adding yield: {yield_value} for ore: {ore_type} from seller: {seller_name}")
                    seller_yields[seller_name][ore_type] += yield_value
                    seller_totals[seller_name] += yield_value  # Add to total SCU

    # Also process joinedSessions for any unique sessions not in mySessions
    for session_id, session in joined_sessions.items():
        session_name = session['name']
        if session_id not in my_sessions:  # Only process if not already in mySessions
            log_debug(f"Processing joined session: {session_name} - {session_id}")
            # You can add similar processing for workOrders here if needed.
            for order in session['workOrders']['items']:
                log_debug(f"Processing work order: {order['orderId']} - {session_name}")

                if order['isSold'] is False or order['isSold'] is None:
                    seller_name = order['seller']['scName']
                    available_sellers.add(seller_name)  # Track available sellers

                    if session_id not in active_sessions:
                      active_sessions.add(session_id)
                    
                    for ore_data in order['shipOres']:
                        ore_type = ore_data['ore']
                        yield_value = ore_data['yield']
                        log_debug(f"Adding yield: {yield_value} for ore: {ore_type} from seller: {seller_name}")
                        seller_yields[seller_name][ore_type] += yield_value
                        seller_totals[seller_name] += yield_value  # Add to total SCU

    log_debug(f"Seller Yields: {seller_yields}")
    log_debug(f"Seller Totals: {seller_totals}")
    return my_sessions, joined_sessions, seller_yields, seller_totals, available_sellers, active_sessions

# Function to round yields
def round_yield(value):
    return math.ceil(value / 100)  # Divide by 100 and round up to the next whole number

# Function to print summary
def print_summary(seller, seller_yields, seller_totals):
    print(f"\nQuantité à vendre pour {seller}:")
    total_scu = seller_totals[seller]
    rounded_total = round_yield(total_scu)  # Round the total as well

    for ore, total_yield in seller_yields[seller].items():
        rounded_yield = round_yield(total_yield)
        print(f"{ore}: {rounded_yield} SCU")  # (original total: {total_yield})
    
    print(f"Total: {rounded_total} SCU")  # Print rounded total at the end

# Main function
def main():
    data = fetch_graphql_data(query)
    my_sessions, joined_sessions, seller_yields, seller_totals, available_sellers, active_sessions = process_sessions(data)

    print("Sessions Actives:")
    for session_id, session in my_sessions.items():
        if session_id in active_sessions:
          print(f"- {session['name']} (ID: {session_id})")

    for session_id, session in joined_sessions.items():
        if session_id in active_sessions:
          if session_id not in my_sessions:
              print(f"- {session['name']} (ID: {session_id})")

    print("\nVendeurs:")
    sellers_list = list(available_sellers)
    for idx, seller in enumerate(sellers_list, start=1):
        print(f"{idx}. {seller}")
    
    print(f"{len(sellers_list) + 1}. Tous les vendeurs")

    choice = int(input("\nSélectionner un vendeur par son numéro (ou tous les vendeurs): ")) - 1

    if choice == len(sellers_list):  # If 'All Sellers' is selected
        full_seller = 0.00
        for seller in sellers_list:
            print_summary(seller, seller_yields, seller_totals)
            full_seller += seller_totals[seller]
        print(f"\nTotal vendeurs: {round_yield(full_seller)} SCU")
    else:
        selected_seller = sellers_list[choice]
        print_summary(selected_seller, seller_yields, seller_totals)

    input("Presser Entrer pour quitter")

if __name__ == "__main__":
    main()
