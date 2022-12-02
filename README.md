# **PaperTrading: CS50 Final Project**

&nbsp;

## **General**

PaperTrading is a web application that allows users to simulate trading US stocks without real money. This gives users the opportunity to practice having a stock portfolio without any financial risk.

To use the application, users register for an account with a username and password. Their password is hashed using a function from the [Werkzeug Security module](https://werkzeug.palletsprojects.com/en/2.2.x/utils/) and is then added to a SQL database along with their username. Users are given $10,000 to begin with, but this can be modified inside their account.

After users have registered and logged in to their account, the application provides several functionalities for practicing paper trading, which are highlighted below.

All stock data is provided with the use of the [Yahoo Finance API](https://pypi.org/project/yfinance/).

&nbsp;

## **Index**

After registering, users are directed to the Index page, which provides users with an overview of their portfolio. An example overview page is displayed below, with its separate components highlighted in red.

&nbsp;

**Light Mode**:

![PaperTrading Home Page - Light Mode](/static/light-mode.png)

&nbsp;

**Dark Mode (Dark Reader Chrome Extension)**:

![PaperTrading Home Page - Dark Mode](/static/dark-mode.png)

Within the index page, there are three main components to this overview, namely:
1. Summary
2. Portfolio Distribution
3. Holdings Table

Each of these components aims to help users get an idea of how their portfolio is allocated and performing holistically. There are several key functions provided within the index page, which are explained in more detail below.

&nbsp;

### **1a.&nbsp;Summary - Unrealized Gains**

Along with an indication of the user's total portfolio value and cash reserve, PaperTrading tracks the total current unrealized gains that the user has. Unrealized gains are determined from currently held stocks and are gains "on paper" - this comes from investments that have not been sold yet.

> Example:
>
> You bought 1 share of Amazon at $150.
>
> The price of the share has now increased from $150 to $200, but you have not sold it.
>
> The unrealized gain on this stock is currently $50.
>
> Note: unrealized gains fluctuate from day to day with the stock market.

&nbsp;

### **1b.&nbsp;Summary - Realized Gains**

PaperTrading also tracks the total current realized gains that the user has. Realized gains are determined from stocks that have been sold and are "locked" gains.

> Example:
>
> You bought 1 share of Amazon at $150.
>
> The price of the share has now increased from $150 to $250, and you decide to sell it.
>
> Before you sold, the unrealized gain was $100. After you sold the share, the unrealized gain became realized at $100 (or "locked").
>
> Note: realized gains do not fluctuate day to day with the stock market.

&nbsp;

### **2.&nbsp;Portfolio Distribution - Donut Chart**

Along with a portfolio summary, the index page contains a donut chart showing a distribution of how much of each stock the user holds and how much cash they have. Using a JavaScript code created by Google developers [here](https://developers.google.com/chart/interactive/docs/gallery/piechart#fullhtml), stock symbols and their total values are added to the data and presented in a donut chart. When the user hovers over a segment of the chart, it reveals how much they have in the stock and the percentage of their portfolio that it represents.

![Donut Chart](/pictures/donut-chart.gif)

&nbsp;

### **3a.&nbsp;Holdings Table - Buy & Sell Buttons**

Within the holdings table, the user has green buy and red sell buttons on each of their holdings which link to the buy and sell pages for easily trading shares. On the buy and sell pages, the default values for the stock symbol are then set to the stock that was pressed from the index page (with the use of URL parameters).

![Sell Button](/pictures/sell-button.gif)

&nbsp;

### **3b.&nbsp;Holdings Table - Color Formatting**

Using conditional statements with Jinja syntax in HTML, all gains on the index page have their color formatted depending on if the number is positive or negative. Positive numbers are formatted as green with positive signs and negative numbers are formatted as red with negative signs.

![Gains](/pictures/gain.png)

&nbsp;

## **Quote**
In the Quote tab on the top of the website, users can input a stock name and see the corresponding symbol and current price of that stock. They can then be directed to buy some shares of that stock after quoting.

&nbsp;

### **Auto-Complete**
Using source code online and [Yong Hong Tan's full list of stocks](https://medium.datadriveninvestor.com/download-list-of-all-stock-symbols-using-this-python-package-12937073b25), Auto-Complete functionality was added to the Quote tab. As users type into the input box, the application searches through the list of stock names to determine possible suggestions. This code was based on an article by [Geeks for Geeks](https://www.geeksforgeeks.org/autocomplete-input-suggestion-using-python-and-flask/), with [styling](https://stackoverflow.com/questions/17838380/styling-jquery-ui-autocomplete) and [adjusted search functionality](https://stackoverflow.com/questions/43615966/jquery-ui-autocomplete-match-first-letter-typed) provided via Stack Overflow.

![autocomplete](/pictures/autocomplete.gif)

&nbsp;

### **Buy Button**

After the user has quoted the stock, they can easily buy shares by clicking the buy button below the stock quote. The default stock symbol is set to the stock that they were viewing from the quote page.

&nbsp;

## **Buy**

As highlighted in **3a. Holding Table - Buy & Sell Buttons**, PaperTrading provides a tab where users can buy stocks. For a better user experience, both the Buy and Sell pages provide three useful features:
1. An indication of the user's current cash reserve.
2. If the user arrived at the Buy/Sell page via links from Index or Quote, Jinja syntax is used to set the value of the 'Symbol' field as the one selected from those pages.
3. If there was a symbol selected from the Index or Quote pages, autofocus is set to the 'Shares' field instead of the 'Symbol' field to increase speed of use.

The program checks whether the user has sufficient cash available to buy the desired stock.

&nbsp;

## **Sell**

In addition to the features above, the Sell page allows users to select only from their current holdings as stocks that they can sell.

![sell](/pictures/sell.gif)

&nbsp;

## **Deposit**

Users are also given the ability to add to their cash position if they wish to practice trading with a larger portfolio - this is done within the "Deposit" tab. Users can also see how much cash they currently have.

&nbsp;

## **Withdraw**

Users are also given the ability to decrease their cash position if they wish to practice trading with a smaller portfolio. This is done within the "Withdraw" tab. Users can also see how much cash they currently have.

&nbsp;

## **History**

Users can see a log of their trading transactions, which includes:
- stock symbol
- company name
- shares
- price per share
- total transaction value
- time of transaction

See below for an example:

![history](/pictures/history.png)

&nbsp;

## **Account**

Within the "Account" tab, users can update their password. This will also update the hash of their password within the SQL database, as per [Werkzeug Security's Python module](https://werkzeug.palletsprojects.com/en/2.2.x/utils/). They will first need to submit their current password, which is checked against the hash stored in the database. If their current password is correct, then their new password hash will be stored.

&nbsp;

## **Helper Functions**

To handle specific functions of the web application, a few necessary helper functions were used from other sources and were not created by me. They are highlighted below.


### **Apology**

Returns an apology message when user provides invalid input.

### **Login Required**

This function is used on all pages within the web application except Register and Login, so that all functionality within the app is only provided to users who have logged in to their accounts.

### **AutoComplete**

Using Yong Hong Tan's API [linked here](https://medium.datadriveninvestor.com/download-list-of-all-stock-symbols-using-this-python-package-12937073b25), this function creates a dictionary of all available stock names and their symbols for use in an AutoComplete script within the Quote tab.

### **USD**

This function formats floating point values as United States Dollars (USD) within HTML/Jinja.
