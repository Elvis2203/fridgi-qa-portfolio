Feature: Delete pantry ingredients
  As a user
  I want to remove ingredients I no longer have
  So that my pantry stays accurate

  Scenario: A deleted ingredient stays deleted after reload
    Given the pantry contains "Rice" and "Oats"
    When I delete "Rice"
    And I reload the page
    Then the pantry shows 1 item
    And the item is called "Oats"

  @regression @BUG-001
  Scenario: The input box keeps its size after deleting a long name
    Given the pantry contains an ingredient with a 100-character name
    And I note the size of the input box
    When I delete that ingredient
    Then the input box has the same size as before
