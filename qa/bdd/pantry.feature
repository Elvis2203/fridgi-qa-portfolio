Feature: Add pantry ingredients
  As a user
  I want to add several ingredients at once
  So that filling my pantry is fast

  Scenario: Same ingredient in different upper/lower case is saved only once
    Given the pantry is empty
    When I add "Chicken, chicken, CHICKEN"
    Then the pantry shows 1 item
    And the item is called "Chicken"

  Scenario: Greek yoghurt and Greek yogurt count as the same food
    Given the pantry is empty
    When I add "Greek yoghurt, Greek yogurt"
    Then the pantry shows 1 item
    And the item is called "Greek yogurt"

  Scenario: Tomato and cherry tomatoes stay separate
    Given the pantry is empty
    When I add "Tomato, Cherry tomatoes"
    Then the pantry shows 2 items
    And the items are:
      | Tomato          |
      | Cherry tomatoes |

  Scenario: Commas, new lines and blank lines all separate ingredients
    Given the pantry is empty
    When I add:
      """
      Rice, Pasta
      Oats

      Apple
      """
    Then the pantry shows 4 items
    And the items are:
      | Rice  |
      | Pasta |
      | Oats  |
      | Apple |

  Scenario Outline: Name length limit is 100 characters
    Given the pantry is empty
    When I add an ingredient name of <length> characters
    Then the name is <result>

    Examples:
      | length | result   |
      | 99     | accepted |
      | 100    | accepted |
      | 101    | rejected |

  Scenario: A batch with a 101-character name is rejected entirely
    Given the pantry is empty
    When I add "eggs" together with an ingredient name of 101 characters
    Then I see an error that a name can be at most 100 characters
    And "eggs" is not saved

  Scenario: Saved ingredients are still there after reload
    Given the pantry contains "Rice" and "Oats"
    When I reload the page
    Then the pantry shows 2 items
    And the items are:
      | Rice |
      | Oats |
