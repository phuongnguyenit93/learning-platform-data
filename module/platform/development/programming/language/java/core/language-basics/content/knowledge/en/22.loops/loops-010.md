# Choosing `while`, `do-while`, or `for` for a problem — Java 17+

Java has three basic looping constructs. **Choose a loop based on when the condition is checked and how the stopping point is determined**, not because one syntax always runs faster than another:

- **`for`**: suitable when managing indices, counters, or initialization–check–update steps that belong to the same loop.
- **`while`**: suitable when the iteration count is not known in advance and execution only continues while a condition remains true; the body **can run 0 times**.
- **`do-while`**: suitable when the body needs to run **at least once** before deciding whether to repeat, such as prompting for input the first time.

## 1. Quick selection table

| Situation | Consider | Reason |
| --- | --- | --- |
| Traversing indices `0..n-1` | `for` | Initialization, condition, and counter update sit in one place |
| Repeating exactly `n` times | `for` | Iteration count and bounds are clearly expressed |
| Reading until end of data / sentinel marker | `while` | Iteration count is not fixed; there may be no data at all |
| Waiting for state to change, with a retry limit | `while` or `for` | Stops when condition is met or attempts run out |
| Showing a prompt then validating to re-prompt | `do-while` | Body needs to run at least once |
| Wanting body to run 0 times if initial condition is false | `while` or `for` | Both check beforehand |
| Reading each array element's value without needing position | Enhanced `for` | Easier to read, no manual index management |

**There is no mandatory rule**: the same algorithm can be written correctly with multiple loop types. Choose the construct that highlights the **stopping condition**, reduces the risk of forgetting an update, and is easy to test.

## 2. The three syntaxes and execution orders

### `for` — expresses counter steps

~~~java
for (int i = 0; i < 3; i++) {
    System.out.println(i);
}
~~~

Order: **initialize once → check → body → update → re-check**. When the condition is false right from the start, the body does not run. If `i` is declared directly in the initialization part, it is no longer in scope after the `for` statement.

### `while` — checks before running the body

~~~java
int remaining = 3;
while (remaining > 0) {
    System.out.println(remaining);
    remaining--;
}
~~~

Order: **check → body → re-check**. The author is normally responsible for updating state inside the body; if `remaining--` is forgotten, the loop may never terminate. `while` fits when the stopping point depends on data/state rather than just a counter index.

### `do-while` — runs first, then checks

~~~java
int attempt = 0;
do {
    attempt++;
    System.out.println("attempt=" + attempt);
} while (attempt < 2);
~~~

Order: **body → check → body...**; the body runs at least once if execution enters the loop normally. The syntax has a **mandatory semicolon after `while (condition);`**. Unlike `while`, even if the initial condition is already false, the body still runs once before the first check.

| Construct | Checked before first body? | Minimum iterations | Typical update location |
| --- | --- | ---: | --- |
| Basic `for` | Yes | 0 | Update part in the loop header |
| `while` | Yes | 0 | Inside body, or from state changes |
| `do-while` | No | 1 | Inside body before checking |

## 3. Self-contained, CLI-runnable Java 17+ demo

Create a UTF-8 file named **`ChooseLoopDemo.java`**:

~~~java
public class ChooseLoopDemo {
    static void countedFor() {
        for (int i = 0; i < 3; i++) {
            System.out.println("for=" + i);
        }
    }

    static void unknownAttemptsWhile() {
        int attempts = 0;
        boolean connected = false;
        while (!connected && attempts < 3) {
            attempts++;
            System.out.println("try=" + attempts);
            connected = attempts == 2;
        }
        System.out.println("connected=" + connected);
        System.out.println("attempts=" + attempts);
    }

    static void promptDoWhile() {
        String[] inputs = {"", " An "};
        int index = 0;
        String name;
        do {
            name = inputs[index++];
            System.out.println("entry="
                    + (name.isBlank() ? "blank" : name.trim()));
        } while (name.isBlank() && index < inputs.length);
        System.out.println("name=" + name.trim());
    }

    static void initialFalse() {
        int available = 0;
        int whileVisits = 0;
        while (available > 0) {
            whileVisits++;
        }

        int doVisits = 0;
        do {
            doVisits++;
        } while (available > 0);

        System.out.println("whileVisits=" + whileVisits);
        System.out.println("doVisits=" + doVisits);
    }

    static void readUntilSentinel() {
        String[] tokens = {"4", "bad", "6", "stop", "100"};
        int index = 0;
        int total = 0;

        while (index < tokens.length) {
            String token = tokens[index++];
            if (token.equals("stop")) {
                System.out.println("sentinel=stop");
                break;
            }
            try {
                total += Integer.parseInt(token);
            } catch (NumberFormatException ex) {
                System.out.println("invalid=" + token);
            }
        }
        System.out.println("total=" + total);
        System.out.println("consumed=" + index);
    }

    static void forContinue() {
        for (int i = 0; i < 4; i++) {
            if (i == 1) {
                continue;
            }
            System.out.println("keep=" + i);
        }
    }

    static void enhancedFor() {
        int total = 0;
        for (int value : new int[] {2, 4, 6}) {
            total += value;
        }
        System.out.println("enhancedTotal=" + total);
    }

    public static void main(String[] args) {
        System.out.println("== counted for ==");
        countedFor();

        System.out.println("== conditional while ==");
        unknownAttemptsWhile();

        System.out.println("== do-while prompt ==");
        promptDoWhile();

        System.out.println("== initially false ==");
        initialFalse();

        System.out.println("== sentinel while ==");
        readUntilSentinel();

        System.out.println("== continue in for ==");
        forContinue();

        System.out.println("== enhanced for ==");
        enhancedFor();
        System.out.println("done");
    }
}
~~~

Use **JDK 17+**. Open PowerShell (Windows) or Bash (Linux/macOS) in the directory containing the file:

~~~bash
java -version
javac -version
javac -encoding UTF-8 ChooseLoopDemo.java
java ChooseLoopDemo
~~~

**Exact expected stdout** of the `java ChooseLoopDemo` command alone:

~~~text
== counted for ==
for=0
for=1
for=2
== conditional while ==
try=1
try=2
connected=true
attempts=2
== do-while prompt ==
entry=blank
entry=An
name=An
== initially false ==
whileVisits=0
doVisits=1
== sentinel while ==
invalid=bad
sentinel=stop
total=10
consumed=4
== continue in for ==
keep=0
keep=2
keep=3
== enhanced for ==
enhancedTotal=12
done
~~~

`java -version` and `javac -version` print machine-dependent version information and are not part of the fixed stdout. The program simulates pre-populated data so results do not depend on keyboard or network.

## 4. Choosing by input condition, not just iteration count

### Known iteration count or index bound: `for`

~~~java
int[] values = {10, 20, 30};
for (int i = 0; i < values.length; i++) {
    System.out.println(values[i]);
}
~~~

The right bound is `i < values.length`, not `<=`. For an empty array, the loop runs **0 iterations**. Enhanced `for (int value : values)` is even more concise if you only need values and do not need indices or modifying elements by position.

### State-dependent looping: `while`

~~~java
int attempts = 0;
boolean success = false;
while (!success && attempts < 3) {
    attempts++;
    success = tryOnce(attempts);
}
~~~

`tryOnce` here is just an illustrative name for a business method provided by the application; the **runnable** example in section 3 used the simulated condition `attempts == 2`. In practice, set a limit to avoid infinite retries, and make clear whether an attempt should occur if the state is already successful from the start.

### Must execute the first time before knowing whether to repeat: `do-while`

~~~java
String input;
do {
    input = askForName(); // Data-retrieval method provided by the application.
} while (input == null || input.isBlank());
~~~

This is the common form when a prompt needs to be displayed at least once. In a real application, you need to add a cancellation policy, input closing, or retry limit; if invalid data is always received, the loop may never finish. The `askForName()` method in this conceptual snippet is **not part of the demo file**.

## 5. `for` and `while` can be converted, but order must be preserved

The following two snippets are normally equivalent when there is no special flow control:

~~~java
for (int i = 0; i < 3; i++) {
    System.out.println(i);
}
~~~

~~~java
int i = 0;
while (i < 3) {
    System.out.println(i);
    i++;
}
~~~

However, **`continue` changes how conversion works**:

~~~java
for (int i = 0; i < 4; i++) {
    if (i == 1) {
        continue; // Java still runs the for loop's i++ update part.
    }
    System.out.println(i);
}
~~~

If rewritten into `while` with `i++` placed after `continue`, the loop can spin forever at `i == 1` because the update is skipped. When converting, ensure every continuing loop path **makes progress**.

| Statement in body | Basic `for` | `while` / `do-while` |
| --- | --- | --- |
| `continue` targeting this loop | Runs the `for` update part, then checks condition | Jumps to condition check; you must ensure state is updated |
| `break` | Exits loop immediately, skips `for` update | Exits loop immediately |
| `return` or `throw` | Exits method or throws exception | Same effect |

`do-while` also differs in checking **after the body**, so it cannot be mechanically converted to `while` while preserving behavior if the condition is initially false.

## 6. Safety and readability notes

- **Condition must be `boolean`**: do not use `while (1)` or `for (; number;)` as in languages that treat numbers as booleans.
- **Semicolon `;` placement matters**: basic `for` has two `;` in its header; `do-while` has `;` at the end; accidentally placing `;` after `while (condition)` or `for (...)` creates an **empty body**.
- **Have a clear stopping point**: update counter/state, consume data, or use `break`/`return` intentionally. `while (true)` is not inherently wrong, but must have an exit strategy.
- **Do not pick a construct based on loop length**: the three syntaxes have no fixed speed ranking. Prioritize expressing behavior accurately and maintainability.
- **Variable scope**: `int i` declared in a `for` header cannot be used outside the loop; a variable declared before `while` usually stays in scope after the loop.

## 7. Self-check exercises

1. To traverse every array element using indices `0..length-1`, what should you choose?  
   *Hint:* `for` with `i < array.length`.
2. To read data until encountering `"stop"`, when the number of items is unknown, what should you choose?  
   *Hint:* `while`, updating position or reading the next item each pass.
3. To display an input prompt **at least once** and then validate, what should you choose?  
   *Hint:* `do-while`.
4. When the condition is false right from the start, what are the minimum iterations for the three forms?  
   *Answer:* Basic `for` = 0, `while` = 0, `do-while` = 1.
5. When converting a `for` with `continue` into a `while`, what is easy to forget?  
   *Answer:* Updating state before the next check.
6. If indices are not needed when traversing an array, which syntax makes the code simpler?  
   *Hint:* Enhanced `for`.

## Checklist

- [ ] Choose **`for`** when counting / index traversal steps are clear.
- [ ] Choose **`while`** when the condition is checked **beforehand** and iteration count depends on state.
- [ ] Choose **`do-while`** when the body needs to run **at least once**.
- [ ] Check index bounds, initial condition, and progression mechanism.
- [ ] Understand `continue`/`break` before converting loop types.
- [ ] Know how to distinguish basic `for` from enhanced `for`.

**Conclusion:** Choose according to **problem semantics**: `for` for clear counting loops, `while` for pre-checked continuation conditions, and `do-while` for a mandatory first execution step. Checking stopping conditions and updates carefully matters more than trying to use one loop type for every case.