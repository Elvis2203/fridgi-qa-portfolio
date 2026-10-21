Feature: Recipe requirements
  As a user
  I want to set which ingredients a recipe must use or avoid
  So that I only get recipes I am happy to cook

  Background:
    Given the pantry contains "Greek yogurt" and "Oats"
    And the sample recipe contains "Apple"

  Scenario: "Prefer to avoid" only gives a warning
    Given "Apple" is in "Prefer to avoid"
    When I generate a recipe
    Then the recipe is shown
    And I see a warning that the recipe contains "Apple"

  Scenario: "Do not use" rejects the recipe
    Given "Apple" is in "Do not use"
    When I generate a recipe
    Then no recipe is shown
    And I see a message that the recipe was rejected because it contains "Apple"

  Scenario: The same ingredient in "Must use" and "Do not use" is an error
    Given "Oats" is in "Must use"
    And "Oats" is in "Do not use"
    When I generate a recipe
    Then I see an error that "Oats" cannot be in both "Must use" and "Do not use"
    And no recipe is shown

  Scenario: Changing a requirement clears the old result
    Given a recipe is shown
    When I add "Apple" to "Do not use"
    Then the old recipe is no longer shown
