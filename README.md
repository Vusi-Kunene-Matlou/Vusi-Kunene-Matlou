<div style="font-family: 'Courier', monospace; color: #00FF00; background-color: black; padding: 10px;">
    <h3>🚀 Welcome to My Matrix</h3>
    <pre id="matrix-effect"></pre>
</div>
<script>
    var text = "Welcome to the Matrix...\nPlease wait...\nInitializing...\n";
    var i = 0;
    var speed = 100;

    function typeWriter() {
        if (i < text.length) {
            document.getElementById("matrix-effect").innerHTML += text.charAt(i);
            i++;
            setTimeout(typeWriter, speed);
        }
    }
    typeWriter();
</script>


