(function () {
  const QUESTIONS = window.__QUESTIONS__;
  const SCALE = window.__ANSWER_SCALE__;
  const CATEGORY_NAMES = window.__CATEGORY_NAMES__;
  const TARGET_DATE = window.__TARGET_DATE__;
  const RESULT_URL_BASE = window.__RESULT_URL_BASE__;

  const answers = {};
  Object.entries(window.__EXISTING_ANSWERS__ || {}).forEach(([k, v]) => {
    answers[parseInt(k, 10)] = v;
  });

  let current = 0;

  const categoryLabel = document.getElementById('categoryLabel');
  const questionCount = document.getElementById('questionCount');
  const questionText = document.getElementById('questionText');
  const answerOptions = document.getElementById('answerOptions');
  const careNote = document.getElementById('careNote');
  const backBtn = document.getElementById('backBtn');
  const nextBtn = document.getElementById('nextBtn');
  const questionPanel = document.getElementById('questionPanel');
  const errorMsg = document.getElementById('errorMsg');
  const segFills = Array.from(document.querySelectorAll('.progress-seg-fill'));

  function updateProgress() {
    segFills.forEach((seg, i) => {
      seg.style.width = i <= current ? '100%' : '0%';
    });
  }

  function renderQuestion() {
    const q = QUESTIONS[current];
    categoryLabel.textContent = CATEGORY_NAMES[q.category] || '';
    questionCount.textContent = `${current + 1} / ${QUESTIONS.length}`;
    questionText.textContent = q.text;
    careNote.classList.toggle('hidden', q.category !== 'urges');

    answerOptions.innerHTML = '';
    SCALE.forEach((opt) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'answer-card' + (answers[q.id] === opt.value ? ' is-selected' : '');
      btn.innerHTML = `
        <span class="value-chip">${opt.value}</span>
        <span class="font-medium text-[15px]">${opt.label}</span>
      `;
      btn.addEventListener('click', () => selectAnswer(q.id, opt.value));
      answerOptions.appendChild(btn);
    });

    backBtn.classList.toggle('hidden', current === 0);
    nextBtn.disabled = answers[q.id] === undefined;
    nextBtn.textContent = current === QUESTIONS.length - 1 ? 'Complete Assessment' : 'Next →';
    updateProgress();
  }

  function selectAnswer(qid, value) {
    answers[qid] = value;
    renderQuestion();
  }

  function transition(direction, after) {
    const cls = direction === 'forward' ? 'is-leaving-forward' : 'is-leaving-back';
    questionPanel.classList.add(cls);
    setTimeout(() => {
      after();
      questionPanel.classList.remove(cls);
    }, 140);
  }

  backBtn.addEventListener('click', () => {
    if (current === 0) return;
    transition('back', () => {
      current -= 1;
      renderQuestion();
    });
  });

  nextBtn.addEventListener('click', async () => {
    const q = QUESTIONS[current];
    if (answers[q.id] === undefined) return;

    if (current < QUESTIONS.length - 1) {
      transition('forward', () => {
        current += 1;
        renderQuestion();
      });
    } else {
      await submitAssessment();
    }
  });

  async function submitAssessment() {
    errorMsg.classList.add('hidden');
    if (Object.keys(answers).length !== QUESTIONS.length) {
      errorMsg.textContent = 'Please answer every question before finishing.';
      errorMsg.classList.remove('hidden');
      return;
    }

    nextBtn.disabled = true;
    nextBtn.textContent = 'Saving…';

    try {
      const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';
      const res = await fetch('/api/assessments', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
        },
        body: JSON.stringify({ answers, date: TARGET_DATE }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Something went wrong.');
      window.location.href = RESULT_URL_BASE + data.id;
    } catch (err) {
      errorMsg.textContent = err.message || 'Could not save your check-in. Please try again.';
      errorMsg.classList.remove('hidden');
      nextBtn.disabled = false;
      nextBtn.textContent = 'Complete Assessment';
    }
  }

  renderQuestion();
})();
