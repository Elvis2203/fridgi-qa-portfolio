"""Three end-to-end smoke workflows; infrastructure and failure evidence live in conftest."""

from selenium.webdriver.common.by import By


def click(driver, selector):
    element = driver.find_element(By.CSS_SELECTOR, selector)
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'})", element)
    element.click()


def add(driver, wait, text, count):
    driver.find_element(By.ID, "ingredients").send_keys(text)
    click(driver, '[data-testid="add-ingredients"]')
    wait.until(lambda _: driver.find_element(By.ID, "ingredients").get_attribute("value") == "")
    wait.until(
        lambda _: len(driver.find_elements(By.CSS_SELECTOR, '[data-testid="pantry-item"]')) == count
    )


def test_pantry_duplicate_reload_and_delete(browser):
    driver, wait = browser
    add(driver, wait, "eggs, EGGS, leftover roast chicken", 2)
    driver.refresh()
    wait.until(
        lambda _: len(driver.find_elements(By.CSS_SELECTOR, '[data-testid="pantry-item"]')) == 2
    )
    click(driver, '[aria-label="Delete eggs"]')
    wait.until(
        lambda _: len(driver.find_elements(By.CSS_SELECTOR, '[data-testid="pantry-item"]')) == 1
    )
    driver.refresh()
    wait.until(
        lambda _: len(driver.find_elements(By.CSS_SELECTOR, '[data-testid="pantry-item"]')) == 1
    )
    assert (
        "leftover roast chicken"
        in driver.find_element(By.CSS_SELECTOR, '[data-testid="pantry-list"]').text
    )


def test_sample_preference_exclusion_and_result_invalidation(browser):
    driver, wait = browser
    add(driver, wait, "Greek yogurt,oats", 2)
    driver.find_element(By.ID, "prefer-to-avoid").send_keys("apple")
    click(driver, ".recipe-actions .refresh-button")
    wait.until(lambda _: driver.find_elements(By.CSS_SELECTOR, ".recipe-card"))
    assert "Preference warnings" in driver.find_element(By.CSS_SELECTOR, ".recipe-card").text
    missing = driver.find_elements(By.CSS_SELECTOR, ".recipe-ingredients > div")[1]
    assert "apple" in missing.text
    driver.find_element(By.ID, "do-not-use").send_keys("apple")
    wait.until(lambda _: not driver.find_elements(By.CSS_SELECTOR, ".recipe-card"))
    click(driver, ".recipe-actions .refresh-button")
    wait.until(lambda _: driver.find_elements(By.ID, "requirements-error"))
    message = driver.find_element(By.CSS_SELECTOR, "#requirements-error > p").text
    assert message == (
        "The sample did not meet all ingredient requirements and recipe checks. "
        "Review your selections. The fixed sample only contains Greek yogurt, apple, and oats."
    )
    assert not driver.find_elements(By.CSS_SELECTOR, ".recipe-card")
    assert driver.find_element(By.ID, "do-not-use").get_attribute("value") == "apple"


def test_long_name_deletion_layout_regression(browser):
    driver, wait = browser
    for width in (1000, 500):
        driver.set_window_size(width, 950)
        initial = driver.find_element(By.ID, "ingredients").rect["width"]
        add(driver, wait, "a" * 100 + ",rice", 2)
        click(driver, '[aria-label="Delete ' + "a" * 100 + '"]')
        wait.until(
            lambda _: len(driver.find_elements(By.CSS_SELECTOR, '[data-testid="pantry-item"]')) == 1
        )
        assert abs(driver.find_element(By.ID, "ingredients").rect["width"] - initial) <= 1
        assert driver.execute_script(
            "return document.documentElement.scrollWidth <= window.innerWidth"
        )
        click(driver, '[aria-label="Delete rice"]')
        wait.until(
            lambda _: not driver.find_elements(By.CSS_SELECTOR, '[data-testid="pantry-item"]')
        )
        assert abs(driver.find_element(By.ID, "ingredients").rect["width"] - initial) <= 1
