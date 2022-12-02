$(function () {
    var availableTags = [
        {% for stock_option in stock_options %}
            "{{ stock_option }}",
    {% endfor %}
    ];
$("#symbol").autocomplete({
    source: function (request, response) {
        var results = $.ui.autocomplete.filter(availableTags, request.term);

        response(results.slice(0, 10));

        $.ui.autocomplete.filter = function (array, term) {
            var matcher = new RegExp("^" + $.ui.autocomplete.escapeRegex(term), "i");
            return $.grep(array, function (value) {
                return matcher.test(value.label || value.value || value);
            });
        };
    }
});
} );