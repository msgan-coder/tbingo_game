<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Bingo Online</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        :root { --primary: #2c3e50; --accent: #f1c40f; --success: #2ecc71; --danger: #e74c3c; }
        body { font-family: sans-serif; background: #f0f2f5; padding: 20px; display: flex; flex-direction: column; align-items: center; }
        .bingo-board { display: grid; grid-template-columns: repeat(5, 1fr); gap: 5px; width: 100%; max-width: 400px; background: white; padding: 10px; border-radius: 10px; }
        .cell { aspect-ratio: 1; border: 1px solid #ddd; border-radius: 5px; display: flex; align-items: center; justify-content: center; font-weight: bold; cursor: pointer; }
        .cell.marked { background: var(--accent); }
        .cell.free { background: var(--success); color: white; font-size: 10px; }
        .win-btn { width: 100%; max-width: 400px; padding: 15px; margin-top: 20px; background: var(--danger); color: white; border: none; border-radius: 50px; font-weight: bold; font-size: 1.2rem; }
        
        /* Waiting Overlay */
        #waiting-overlay {
            display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.9); color: white; flex-direction: column; align-items: center; justify-content: center; z-index: 1000; text-align: center;
        }
    </style>
</head>
<body>

    <div id="waiting-overlay">
        <h2 style="color: var(--accent);">VERIFYING CARD...</h2>
        <p>The Admin is checking your Bingo claim.</p>
        <p>Please wait for the notification in chat!</p>
        <button onclick="tg.close()" style="margin-top:20px; padding:10px 20px;">Return to Telegram</button>
    </div>

    <h1>BINGO</h1>
    <div class="bingo-board" id="board"></div>
    <button class="win-btn" onclick="claimBingo()">BINGO! 🏆</button>

    <script>
        const tg = window.Telegram.WebApp;
        tg.expand();

        function getRandom(min, max, count) {
            let arr = [];
            while(arr.length < count) {
                let r = Math.floor(Math.random() * (max - min + 1)) + min;
                if(!arr.includes(r)) arr.push(r);
            }
            return arr;
        }

        const boardElement = document.getElementById('board');
        const columns = {
            'B': getRandom(1, 15, 5), 'I': getRandom(16, 30, 5),
            'N': getRandom(31, 45, 5), 'G': getRandom(46, 60, 5), 'O': getRandom(61, 75, 5)
        };

        for (let r = 0; r < 5; r++) {
            ['B','I','N','G','O'].forEach((col, i) => {
                const cell = document.createElement('div');
                cell.className = 'cell';
                let val = columns[col][r];
                if (r === 2 && i === 2) {
                    cell.textContent = "FREE";
                    cell.classList.add('free', 'marked');
                } else {
                    cell.textContent = val;
                    cell.onclick = () => cell.classList.toggle('marked');
                }
                boardElement.appendChild(cell);
            });
        }

        function claimBingo() {
            const marked = Array.from(document.querySelectorAll('.cell.marked')).map(c => c.textContent);
            if(marked.length < 5) return tg.showAlert("Mark at least 5 numbers!");

            document.getElementById('waiting-overlay').style.display = 'flex';

            tg.sendData(JSON.stringify({
                action: "claim_bingo",
                user: tg.initDataUnsafe.user?.username || "Player",
                numbers: marked
            }));
        }
    </script>
</body>
</html>
