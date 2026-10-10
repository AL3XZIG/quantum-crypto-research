# Quantum Crypto Research

Исследовательский прототип для работы **«Криптография в эпоху квантовых вычислений: угрозы, уязвимости и постквантовая защита»**.

## Что делает программа

Проект не моделирует физический квантовый процессор. Он собирает воспроизводимые экспериментальные данные и включает математическую модель Гровера, маломасштабную симуляцию квантовой схемы, бенчмарк подписей и модель накладных расходов.

### 1. Модель Гровера

Программа строит математическую модель идеализированного квантового поиска:

- классическая оценка перебора: (N);
- оценка Grover: (sqrt{N}).

Результат сохраняется в `data/grover_results.csv`. Это позволяет построить таблицу и график того, как теоретическая сложность поиска меняется при увеличении пространства поиска.

**Важно:** это модель асимптотики, а не измерение реального квантового процессора.

### 1.1. Симуляция квантовой схемы Гровера

`experiments/grover/grover_circuit.py` строит схему Гровера в Qiskit и запускает её на локальном симуляторе Qiskit Aer. В отличие от простой формулы `sqrt(N)`, эта программа моделирует суперпозицию, фазовый oracle, диффузор и измерения для небольшого пространства поиска.

Программа перебирает несколько чисел итераций и сравнивает:

- экспериментальную долю измерений, в которых найден целевой битовый набор;
- теоретическую вероятность успеха;
- число итераций, близкое к оптимальному по формуле Гровера.

Результаты сохраняются в `data/grover_circuit_results.csv` и `results/figures/grover_success_probability.png`.

Это именно **симуляция квантовой схемы на обычном компьютере**, а не запуск на квантовом процессоре. Для демонстрации используется небольшое пространство поиска; прямое моделирование быстро дорожает с ростом числа кубитов и не является атакой на реальные ключи или хеши.

Для установки дополнительных зависимостей квантового симулятора:

```powershell
python -m pip install -r requirements-quantum.txt
```

### 2. ECDSA vs ML-DSA

Это главный эксперимент проекта.

Программа реально создаёт ключи и подписи двух схем:

- **ECDSA P-256 / SHA-256** — классическая эллиптическая криптография;
- **ML-DSA-65** — постквантовая схема цифровой подписи.

Для каждой схемы измеряются:

- время генерации ключевой пары (**KeyGen**);
- время создания подписи (**Sign**);
- время проверки подписи (**Verify**);
- размер открытого ключа;
- размер закрытого ключа;
- размер подписи.

Перед сохранением результата программа также проверяет, что созданная подпись действительно проходит верификацию.

Именно эти данные можно использовать в статье для собственного экспериментального сравнения классической и постквантовой подписи.

### 3. Signature overhead

Отдельная модель показывает, как увеличение размера цифровой подписи влияет на объём подписных данных.

Это не измерение блокчейна или сети: модель используется для количественной оценки накладных расходов от более крупных подписей.

## Структура

- `experiments/grover/grover_model.py` — математическая модель сложности Гровера.
- `experiments/grover/grover_circuit.py` — симуляция небольшой квантовой схемы Гровера.
- `experiments/signatures/` — бенчмарк ECDSA P-256 и ML-DSA-65.
- `experiments/transaction/` — модели накладных расходов.
- `experiments/run_all.py` — единая точка запуска.
- `data/` — сырые CSV-результаты.
- `results/figures/` — автоматически построенные графики.
- `results/tables/` — таблицы для анализа.
- `tests/` — автоматические проверки.

## Установка в Windows

### 1. Что установить

Нужны:

1. **Python 3.10 или новее**.
2. **Git**.
3. **CMake**.
4. **Visual Studio Build Tools** с компонентом **Desktop development with C++**.

Последние два пункта нужны потому, что `liboqs-python` использует библиотеку `liboqs`, которая при отсутствии готовой системной установки может автоматически собираться из исходников.

### 2. Скачать проект

Откройте PowerShell или CMD и выполните:

```powershell
git clone https://github.com/AL3XZIG/quantum-crypto-research-.git
cd quantum-crypto-research-
```

### 3. Создать виртуальное окружение

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Если PowerShell запрещает запуск скриптов, можно использовать CMD:

```cmd
.venv\Scripts\activate.bat
```

После активации в начале строки терминала появится `(.venv)`.

### 4. Обновить pip и установить зависимости

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

В текущей версии проекта используется `liboqs-python 0.16.0.1`. При первом импорте `oqs` пакет может автоматически загрузить и собрать соответствующую версию `liboqs`. На Windows для такой сборки должны быть доступны Git, CMake и C/C++ toolchain.

### 5. Проверить ML-DSA

```powershell
python -c "import oqs; print('ML-DSA-65' in oqs.get_enabled_sig_mechanisms()); print(oqs.get_enabled_sig_mechanisms())"
```

В выводе должно быть `True`, а в списке алгоритмов — `ML-DSA-65`.

### 6. Запустить весь эксперимент

```powershell
python -m experiments.run_all
```

После завершения состав файлов зависит от выбранной команды. Для актуального автоматизированного запуска сравнения цифровых подписей используются:

- `data/signature_benchmark.csv` — агрегированные результаты бенчмарка;
- `results/tables/signature_benchmark_statistics.csv` — статистика независимых серий;
- `results/tables/comparison_summary.csv` — единая сравнительная таблица с временами, SD, 95% доверительными интервалами и размерами;
- `results/figures/signature_comparison.png` — объединённый график времени операций;
- `results/report.md` — отчёт автоматизации;
- `results/raw/` и `results/logs/` — сохранённые серии и журналы запуска.

## Запуск отдельных частей

### Только математическая модель Гровера

```powershell
python -m experiments.grover.grover_model
```

### Квантовая схема Гровера (требует `requirements-quantum.txt`)

```powershell
python -m pip install -r requirements-quantum.txt
python -m experiments.grover.grover_circuit --qubits 4 --shots 2048
```

В Windows после установки зависимостей можно запустить `run_grover_simulation.bat` двойным щелчком. Скрипт использует виртуальное окружение `.venv` и сохраняет CSV с результатами и график.

Параметры: `--qubits` (от 2 до 12), `--target` (например, `1010` для четырёх кубитов), `--shots` (число измерений на каждое число итераций) и `--seed` (для воспроизводимости). По умолчанию цель — `1111`.

### Только бенчмарк подписей

```powershell
python -m experiments.signatures.run_benchmark --repetitions 100
```

В Windows можно запустить `run_signature_benchmark.bat` двойным щелчком. Он запускает бенчмарк ECDSA/ML-DSA, а затем строит графики и сводную таблицу. Перед этим установите зависимости из `requirements.txt`.

### Только анализ результатов

```powershell
python -m experiments.signatures.analyze_results
```

Команда читает уже существующий `data/signature_benchmark.csv` и создаёт/обновляет `results/tables/comparison_summary.csv` и `results/figures/signature_comparison.png`. Она не запускает новые измерения. Если нужна полная серия экспериментов, используй автоматизацию проекта; анализатор сам по себе не обновляет `results/report.md`.

### Только модель накладных расходов подписей

```powershell
python -m experiments.transaction.signature_overhead
```

Модель берёт фактические размеры подписей из `data/signature_benchmark.csv`, если бенчмарк уже запускался, и иначе использует справочные значения (ECDSA P-256 ≈ 72 байта, ML-DSA-65 = 3309 байт по FIPS 204). Результат сохраняется в `data/signature_overhead_results.csv`. Параметр `--counts` задаёт список чисел подписей на транзакцию (по умолчанию 1..1000).

### Автоматические тесты

```powershell
python -m pytest tests
```

Тесты для симуляции Гровера с реальным запуском Qiskit Aer автоматически пропускаются, если `qiskit`/`qiskit-aer` не установлены.

## Методика бенчмарка

Для каждой операции выполняется серия измерений. Перед серией используются несколько прогревочных запусков, которые не входят в итоговую статистику. В CSV сохраняется среднее время выполнения.

Размеры ключей и подписей измеряются непосредственно у объектов, созданных реализацией. Для ECDSA используются DER-представления ключей; это важно учитывать при интерпретации результатов: размер относится к выбранному формату сериализации, а не только к математическому размеру кривой.

Для ML-DSA фиксируется конкретный вариант **ML-DSA-65**. Подпись сначала проверяется, чтобы эксперимент не мог незаметно сохранить результат неработающей реализации.

## Что можно получить из эксперимента

Главная цель — получить собственные измеряемые результаты для статьи.

Например, после запуска можно построить таблицу вида:

| Алгоритм | KeyGen, ms | Sign, ms | Verify, ms | Public key, B | Private key, B | Signature, B |
|---|---:|---:|---:|---:|---:|---:|
| ECDSA P-256 | измеряется | измеряется | измеряется | измеряется | измеряется | измеряется |
| ML-DSA-65 | измеряется | измеряется | измеряется | измеряется | измеряется | измеряется |

Числа в статье должны быть взяты непосредственно из собственного запуска программы, а не вписаны вручную.

## Что не утверждает этот прототип

- Он **не моделирует физический квантовый процессор и не выполняет криптографическую атаку**.
- `grover_model.py` показывает асимптотическое соотношение, а `grover_circuit.py` симулирует только небольшую квантовую схему на классическом компьютере; ни то ни другое не доказывает практический взлом криптографии.
- Бенчмарк измеряет конкретные программные реализации и конкретное аппаратное окружение.
- Время выполнения нельзя переносить на все компьютеры без повторения эксперимента.
- `liboqs` является исследовательским/прототипным проектом и не должен автоматически рассматриваться как production-ready криптографическая библиотека.

## Воспроизводимость

Рекомендуется сохранять вместе с результатами:

- версию Python;
- версию Windows;
- модель CPU;
- версии `cryptography`, `liboqs-python` и зависимостей;
- число повторений;
- дату запуска.

Эти сведения затем будут включены в раздел «Методика исследования» статьи.

## Текущее состояние

В репозитории уже сохранён предварительный экспериментальный набор для ECDSA P-256 / SHA-256 и ML-DSA-65: 10 независимых серий на алгоритм, сводная таблица со статистикой и единый график. Итоги и ограничения описаны в [`results/report.md`](results/report.md). Это всё ещё **исследовательский прототип**, а не готовый production-криптографический инструмент или окончательное научное заключение. Перед использованием цифр в статье следует повторить эксперимент в документированном окружении, проверить воспроизводимость и явно указать особенности реализации и сериализации.

## Captured benchmark results

The consolidated comparison of ECDSA P-256 / SHA-256 and ML-DSA-65 is available in the report and in the table/chart below. The reported statistics use 10 independent benchmark series per algorithm; the underlying benchmark functions return per-series means, so the confidence intervals describe variation between series rather than individual operations within a series.

- [Automated experiment report](results/report.md)
- [Consolidated comparison table (CSV)](results/tables/comparison_summary.csv)
- [Consolidated comparison chart (PNG)](results/figures/signature_comparison.png)
- [Benchmark methodology and earlier captured run](results/benchmark.md)
- [Aggregate benchmark input](data/signature_benchmark.csv)
- [Per-metric statistics](results/tables/signature_benchmark_statistics.csv)
- [Captured logs and environment details](results/logs/)

The PNG and CSV comparison files are generated locally and are explicitly tracked in Git despite the general ignore rules for generated PNG/CSV files.

## Additional captured results

- [Grover circuit simulation report](results/grover_simulation.md)
- [Grover raw data](data/grover_circuit_results.csv)
- [Grover probability chart](results/figures/grover_success_probability.svg)

Results are experimental and environment-specific. The Grover experiment is a small classical simulation of a quantum circuit, not an attack on real cryptographic systems.
