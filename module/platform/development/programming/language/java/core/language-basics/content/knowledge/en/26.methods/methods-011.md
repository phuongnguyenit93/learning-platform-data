# Decomposing Problems into Methods with Clear Responsibilities — Java 17+

## 1. Why Separate Methods?

When one method simultaneously validates input, performs calculations, assigns ratings, and prints output, the reader has to track **multiple purposes at once**. When requirements change, it is easy to accidentally break unrelated logic.

A method with a **clear responsibility** should be describable with one concrete action: `validateScores` checks data, `calculateAverage` computes the average, `classify` assigns a rating, `formatReport` builds a string, and `showCase` displays output.

**Practical principle:** a method should have **one primary reason to change**, not necessarily just one line of code. Split by business meaning rather than breaking apart every assignment or addition.

Example problem: receive a student's name and an array of integer scores (0–100), compute the **integer-truncated** average, classify it, and output a single report line. If the input is invalid, report a clear error.

## 2. Decomposing the Problem into Steps

| Responsibility | Method | Input → Output |
|---|---|---|
| Validate name | `requireName` | `String` → trimmed `String` or throw error |
| Validate score list | `validateScores` | `int[]` → `void` or throw error |
| Compute average score | `calculateAverage` | Valid `int[]` → `int` |
| Classify | `classify` | `int average` → `String` |
| Format result | `formatReport` | Name, subject count, average, level → `String` |
| Coordinate steps | `buildReport` | Name + scores → complete string |
| Display / handle errors | `showCase` | Sample data → print report or error |

~~~mermaid
flowchart TD
    A["showCase"] --> B["buildReport"]
    B --> C["requireName"]
    B --> D["validateScores"]
    B --> E["calculateAverage"]
    B --> F["classify"]
    B --> G["formatReport"]
    G --> H["Result string"]
    H --> A
    A --> I["System.out.println"]
~~~

`buildReport` is the **orchestrating** method: it calls smaller methods in the right sequence without duplicating score calculation or classification formulas. This is a sensible separation between “knowing what needs to be done” and “knowing how one step is done”.

## 3. Defining Each Method's Contract

Before coding, specify the **inputs, outputs, and error cases**:

- `requireName(name)`: rejects `null` or whitespace-only strings; valid names are trimmed with `strip()`.
- `validateScores(scores)`: rejects `null`, empty arrays, and scores outside 0–100; does not mutate the array.
- `calculateAverage(scores)`: assumes data has **already been validated**, sums with `long`, and performs integer division by the number of subjects. For example, `(70 + 71) / 2 = 70`.
- `classify(avg)`: `avg >= 80` → `GOOD`; `avg >= 50` → `PASS`; otherwise → `RETRY`.
- `formatReport(...)`: only formats the string; does not print or mutate data.
- `buildReport(...)`: returns the string; if data is invalid, lets `IllegalArgumentException` propagate to the caller.

Each method should have a **meaningful verb name**, a return type matching its job, and no unintended state mutations. `validateScores` is `void` because its job is to **validate or throw an error**, not compute a sum.

**Calculation warning:** using `long` to sum `int` values reduces sum overflow risk; for scores 0–100 and valid Java array lengths, `long` easily holds the sum. The average here is **intentional integer division**, not floating-point rounding.

## 4. Separating Computation from Side Effects

A method like:

~~~java
static int classify(int average) {
    // WRONG in terms of example design: both classifies and prints, hard to reuse.
    System.out.println("classifying");
    return average >= 50 ? 1 : 0;
}
~~~

mixes **computed results** with **writing to the screen**. It becomes awkward when later you need to write to a file, return JSON, or run tests that do not expect stdout.

Separated approach:

~~~java
static String classify(int average) {
    if (average >= 80) return "GOOD";
    if (average >= 50) return "PASS";
    return "RETRY";
}

// Call: only when the presentation layer needs to display
System.out.println(classify(75)); // PASS
~~~

`classify` does not depend on `Scanner`, `System.out`, or where results are displayed. The same input produces the same output, making boundary values 49/50/79/80 easy to test.

**A method does not need to be strictly “pure” to have a clear responsibility.** Printing messages is a valid responsibility of `showCase`; just avoid mixing it into calculation formulas.

## 5. `private`, `static`, and Reuse

In the example, internal steps are declared `private static`:

~~~java
private static int calculateAverage(int[] scores) { /* ... */ }
~~~

- `private`: restricts calling from outside the class, avoiding exposing implementation details as API.
- `static`: work needs no instance state and can be called from `static` methods in the same class.
- Parameter / return types form a **contract** that helps the compiler verify call sites.

Not all methods in every program should be `static`: when a responsibility genuinely belongs to an object's state, an instance method may be more appropriate. This lesson uses `static` because the example processes input data and returns results without needing a specialized object.

**Avoid duplication:** if three places check `score >= 80`, share a single `classify`; when the threshold changes, only one place needs updating. However, do not create dozens of one-line methods just to “inflate the method count”.

## 6. Complete Java 17+ Program

Save the file with the exact name **`ClearMethodResponsibilitiesDemo.java`**:

~~~java
public final class ClearMethodResponsibilitiesDemo {
    private ClearMethodResponsibilitiesDemo() {}

    // Responsibility 1: validate and normalize the name.
    private static String requireName(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return name.strip();
    }

    // Responsibility 2: validate scores, without computing.
    private static void validateScores(int[] scores) {
        if (scores == null || scores.length == 0) {
            throw new IllegalArgumentException("scores must not be null or empty");
        }
        for (int i = 0; i < scores.length; i++) {
            if (scores[i] < 0 || scores[i] > 100) {
                throw new IllegalArgumentException(
                        "score at index " + i + " must be 0..100");
            }
        }
    }

    // Responsibility 3: compute average, assuming already validated.
    private static int calculateAverage(int[] scores) {
        long sum = 0;
        for (int score : scores) {
            sum += score;
        }
        return (int) (sum / scores.length);
    }

    // Responsibility 4: apply only the classification rule.
    private static String classify(int average) {
        if (average >= 80) return "GOOD";
        if (average >= 50) return "PASS";
        return "RETRY";
    }

    // Responsibility 5: format output; do not print to screen.
    private static String formatReport(
            String name, int count, int average, String level) {
        return name + " | count=" + count
                + " | avg=" + average + " | level=" + level;
    }

    // Orchestrates business flow without duplicating formulas.
    public static String buildReport(String name, int[] scores) {
        String cleanName = requireName(name);
        validateScores(scores);
        int average = calculateAverage(scores);
        String level = classify(average);
        return formatReport(cleanName, scores.length, average, level);
    }

    // Display boundary: print results and handle invalid inputs.
    private static void showCase(String name, int[] scores) {
        try {
            System.out.println(buildReport(name, scores));
        } catch (IllegalArgumentException ex) {
            System.out.println("ERROR: " + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        showCase(" An ", new int[]{90, 80, 70});
        showCase("Binh", new int[]{40, 50, 60, 50});
        showCase("Chi", new int[]{30, 40});
        showCase("Dung", new int[]{});
        showCase("Em", new int[]{90, 101});
        showCase("", new int[]{90});
        showCase("Phuc", null);
        showCase("Giang", new int[]{100});
    }
}
~~~

**Requirements:** JDK 17 or later, terminal opened in the directory containing the file. The program uses only standard Java, needing no external libraries, Maven/Gradle, or preview features.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 ClearMethodResponsibilitiesDemo.java
java -cp . ClearMethodResponsibilitiesDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\ClearMethodResponsibilitiesDemo.java
java -cp . ClearMethodResponsibilitiesDemo
~~~

### Exact expected stdout

~~~text
An | count=3 | avg=80 | level=GOOD
Binh | count=4 | avg=50 | level=PASS
Chi | count=2 | avg=35 | level=RETRY
ERROR: scores must not be null or empty
ERROR: score at index 1 must be 0..100
ERROR: name must not be blank
ERROR: scores must not be null or empty
Giang | count=1 | avg=100 | level=GOOD
~~~

Reading the flow: `showCase` calls `buildReport`, which validates name and scores before computing. Example `Em` contains score 101 so it is rejected **before** the averaging step; invalid data is never silently replaced with 0.

## 7. Testing by Responsibility and Edge Cases

Once methods are separated, each requirement group can be checked independently:

| Item to test | Input | Expected |
|---|---|---|
| Name | `" An "` | `"An"` |
| Valid scores | `{90,80,70}` | Average `80`, level `GOOD` |
| Upper boundary | Average `79` and `80` | `PASS`, `GOOD` |
| Lower boundary | Average `49` and `50` | `RETRY`, `PASS` |
| Non-integer average | `{70,71}` | `70` under integer division rule |
| Empty/null array | `{}`, `null` | `IllegalArgumentException` |
| Out-of-range score | `{-1}`, `{101}` | `IllegalArgumentException` |

Example of a simple check when placed in the same class:

~~~java
if (!"GOOD".equals(classify(80))) {
    throw new AssertionError("80 must be GOOD");
}
if (!"PASS".equals(classify(50))) {
    throw new AssertionError("50 must be PASS");
}
~~~

These are logic checks, not another example of the `assert` statement (which is disabled by default unless `-ea` is used). In larger projects, JUnit and dedicated unit tests can be used; the main example intentionally uses no external libraries.

## 8. Extension and Design Mistakes to Avoid

**When changing the classification threshold** from 80 to 85, modify `classify` and its related tests, without touching validation or printing code. When switching output from console to web, reuse `buildReport` and replace the presentation layer.

| Symptom | Risk | Improvement |
|---|---|---|
| One long method doing validation + math + printing | Hard to read, test, and modify | Split by separate goals |
| `calculateAverage` calls `System.out.println` itself | Coupled to UI | Return the value, let caller display it |
| Multiple places repeat the same classification threshold | Inconsistent logic | Centralize in `classify` |
| Method named `process` with unclear output | Confusing for API users | Choose names like `buildReport`, `validateScores` |
| Calculation method mutates `scores[i]` unexpectedly | Caller sees data modified | Avoid side effects, document contract clearly |
| Splitting every single line into a method | Fragmented code, constant jumping | Split by **real responsibility** |
| Catching every `Exception` inside a calculation method | Can hide bugs | Handle errors at an appropriate boundary |
| Not defining valid input requirements | Easy division by 0, wrong results | Validate before computing |
| Making every helper `public` | Unnecessarily expands API | Keep `private` when only used within the class |

**Consideration:** `buildReport` currently returns a string serving one fixed format. When an application must support multiple complex outputs, it can return a result object (such as a Java 17 record) so the presentation layer formats it later. Do not add complexity before the problem needs it.

## 9. Exercises and Answers

**Exercise A.** A method reads keyboard input, computes a total, classifies it, and prints it. Propose how to split it.

**Answer:** `readInput` reads data; `validateInput` validates; `calculateTotal` computes; `classify` classifies; `formatReport` builds the string; `main` or `showResult` coordinates and displays. Small steps can be merged if they truly share one clear goal.

**Exercise B.** If the `GOOD` threshold changes from 80 to 85, which method should be modified?

**Answer:** `classify` and tests for the new rule. No need to change `validateScores` or `formatReport`.

**Exercise C.** What does `buildReport("Mai", new int[]{70,71})` return?

**Answer:** `Mai | count=2 | avg=70 | level=PASS` because integer division gives `141 / 2 = 70`.

**Exercise D.** Why should computation and printing results be separated? **Answer:** the same calculation can be used in CLI, web, and tests without producing stdout; the presentation layer can change independently.

## 10. Checklist and Conclusion

- [ ] Can describe each method's responsibility in one short sentence.
- [ ] Name methods to reflect real actions or results.
- [ ] Know inputs, outputs, validity conditions, and throwable errors.
- [ ] Separate validation, computation, business rules, formatting, and display.
- [ ] Use an orchestrating method to keep processing flow readable.
- [ ] Keep internal helpers `private` where appropriate.
- [ ] Avoid mutating caller data unintentionally.
- [ ] Centralize repeated rules in one place.
- [ ] Test normal values, empty arrays, null, indices, and boundaries.
- [ ] Do not over-fragment into dozens of meaningless methods.
- [ ] Run `ClearMethodResponsibilitiesDemo.java` with JDK 17+ and compare exact stdout.

**Conclusion:** Decomposing problems into methods with clear responsibilities keeps every change **well-scoped**, easy to read, easy to test, and reusable. Let validation methods validate, calculation methods return results, formatting methods construct strings, and the presentation layer handle output.