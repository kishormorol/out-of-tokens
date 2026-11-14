// Filtering on the index page and copy buttons on idea pages. The site works
// without this file; it only adds convenience.
(function () {
  var cards = Array.prototype.slice.call(document.querySelectorAll("#cards .card"));
  if (cards.length) {
    var text = document.getElementById("f-text");
    var why = document.getElementById("f-why");
    var tag = document.getElementById("f-tag");
    var status = document.getElementById("f-status");
    var count = document.getElementById("count");
    var empty = document.getElementById("empty");

    var has = function (list, value) {
      return !value || list.split(" ").indexOf(value) !== -1;
    };
    var apply = function () {
      var query = text.value.trim().toLowerCase();
      var shown = 0;
      cards.forEach(function (card) {
        var d = card.dataset;
        var ok =
          has(d.why, why.value) &&
          has(d.tags, tag.value) &&
          (!status.value || d.status === status.value) &&
          (!query || d.text.indexOf(query) !== -1);
        card.hidden = !ok;
        if (ok) shown += 1;
      });
      count.textContent = shown + (shown === 1 ? " idea" : " ideas");
      empty.hidden = shown !== 0;
    };
    [text, why, tag, status].forEach(function (el) {
      el.addEventListener("input", apply);
    });
    apply();
  }

  Array.prototype.forEach.call(document.querySelectorAll(".copy-btn"), function (button) {
    button.addEventListener("click", function () {
      var code = button.closest(".copy").querySelector("code").textContent;
      navigator.clipboard.writeText(code).then(function () {
        button.textContent = "Copied";
        setTimeout(function () {
          button.textContent = "Copy";
        }, 1500);
      });
    });
  });
})();
