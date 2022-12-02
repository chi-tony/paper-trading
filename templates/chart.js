// Load Google chart properties
google.charts.load("current", { packages: ["corechart"] });

// Call function for drawing chart
google.charts.setOnLoadCallback(drawChart);

function drawChart() {
    var totals = google.visualization.arrayToDataTable([
        // Loop through each holding symbol and total price and add to table
        ['Holding', 'Total'],
        {% for key, value in totals.items() %}
['{{ key }}', {{ value }}],
    {% endfor %}
        ]);

// Set properties of chart
var options = {
    pieHole: 0.6,
};

// Assign chart as per document ID
var chart = new google.visualization.PieChart(document.getElementById('donut_chart'));

// Draw chart with input values and properties
chart.draw(totals, options);
    }