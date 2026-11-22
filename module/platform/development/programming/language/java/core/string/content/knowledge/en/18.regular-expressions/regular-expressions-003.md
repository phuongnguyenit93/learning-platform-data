# Matcher.matches(), find(), and lookingAt() in Java

## 1. Objective and Context

When working with **regular expressions (regex)**, Java separates two roles:

- **Pattern**: a compiled expression; reusable.
- **Matcher**: an object holding the input string, search region, current position, and match result. Created via **pattern.matcher(input)**.

The three methods **Matcher.matches()**, **Matcher.lookingAt()**, and **Matcher.find()** all return **boolean**, but the questions they answer are different:

- **matches()**: *Does the entire region under consideration match the regex?*
- **lookingAt()**: *Does the regex match right at the beginning of the region under consideration?*
- **find()**: *Is there any subsequence matching the regex starting from the current search position?*

The "region under consideration" defaults to the entire input string. A Matcher can restrict the region with **region(start, end)**; hence the accurate description is "the entire region" rather than always "the entire String".

## 2. Quick Comparison

| Method | Must start at the beginning of the region? | Must end at the end of the region? | Can search multiple times sequentially? | Typical Purpose |
| --- | --- | --- | --- | --- |
| **matches()** | Yes | Yes | No; each call checks full-region match | Validate whether a value conforms to a pattern |
| **lookingAt()** | Yes | No | No; checks the prefix of the region | Identify a prefix or token at the start |
| **find()** | No | No | Yes; call repeatedly to iterate through matches | Extract matching parts from text |

Example with the regex **cat**:

| Input String | matches() | lookingAt() | find() |
| --- | --- | --- | --- |
| cat | true | true | true |
| cat nap | false | true | true |
| a cat | false | false | true |
| dog | false | false | false |

**Note:** all three only know regex, not business semantics. The regex **cat** can be found inside **scatter** if word boundaries are not enforced; to match a whole word, use **\bcat\b** (written in Java as **"\\bcat\\b"**).

## 3. Standalone Runnable Java 17+ Example

Create the file **MatcherOperationsDemo.java**:

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class MatcherOperationsDemo {
    public static void main(String[] args) {
        String input = "ID=42; ID=7";
        Pattern pattern = Pattern.compile("ID=(\\d+)");

        Matcher whole = pattern.matcher(input);
        System.out.println("matches: " + whole.matches());

        Matcher prefix = pattern.matcher(input);
        System.out.println("lookingAt: " + prefix.lookingAt());
        System.out.println("prefix id: " + prefix.group(1));

        Matcher scan = pattern.matcher(input);
        while (scan.find()) {
            System.out.printf(
                    "find: %s, id=%s, range=[%d,%d)%n",
                    scan.group(), scan.group(1), scan.start(), scan.end());
        }

        System.out.println("find after loop: " + scan.find());
        System.out.println("find after reset: " + scan.reset().find());
    }
}
~~~

Compile and run:

~~~bash
javac MatcherOperationsDemo.java
java MatcherOperationsDemo
~~~

Standard output:

~~~text
matches: false
lookingAt: true
prefix id: 42
find: ID=42, id=42, range=[0,5)
find: ID=7, id=7, range=[7,11)
find after loop: false
find after reset: true
~~~

Explanation:

1. **matches() = false** because **ID=42** only matches the beginning; the remaining **; ID=7** causes the full string not to match.
2. **lookingAt() = true** because the string begins with **ID=42**; the method does not require the trailing part to match as well.
3. **find()** finds the first match at **[0, 5)** and the second at **[7, 11)**. The **end()** index is the position *immediately after* the last character of the matched part.
4. Once matches are exhausted, **find()** returns **false**. **reset()** restores the Matcher to its initial state so it can search from the beginning again.

The example uses **three independent Matchers** so each check is not affected by the position or result of the previous check. A **Pattern** can be reused, whereas a Matcher has state that changes after each operation.

## 4. matches(): Checking a Full-Region Match

~~~java
Pattern digits = Pattern.compile("\\d+");

System.out.println(digits.matcher("12345").matches());  // true
System.out.println(digits.matcher("a12345").matches()); // false
System.out.println(digits.matcher("12345a").matches()); // false
System.out.println(digits.matcher("").matches());       // false
~~~

**matches()** attempts to make the regex cover the entire region. Therefore:

- With the region being the full string, the regex **\\d+** accepts strings consisting only of at least one standard ASCII digit under this regex usage.
- The regex **\\d+** does not need **^** and **$** added for **matches()** to check the whole region.
- If you only want to find a sequence of digits somewhere inside text, use **find()** instead of mechanically loosening the regex to **.*\\d+.*** .
- Do not confuse **Matcher.matches()** with "checking whether a matching substring exists". It does not act like a partial search.

Two utility forms also have full-string matching semantics:

~~~java
boolean a = "123".matches("\\d+");
boolean b = Pattern.matches("\\d+", "123");

System.out.println(a); // true
System.out.println(b); // true
~~~

**String.matches(regex)** and **Pattern.matches(regex, input)** are suitable for single checks. When running the same regex multiple times, compile **Pattern** once and create a new Matcher for each input to avoid unnecessary recompilation.

## 5. lookingAt(): Recognizing a Prefix

**lookingAt()** requires the regex to start at the beginning of the region, without requiring it to reach the end of the region:

~~~java
Pattern command = Pattern.compile("GET|POST");

System.out.println(command.matcher("GET /users").lookingAt());  // true
System.out.println(command.matcher("POST /users").lookingAt()); // true
System.out.println(command.matcher("X GET /users").lookingAt());// false
~~~

The return value indicates that **a prefix** matched; it does not check whether the token ends at an appropriate boundary. For instance, the regex **GET|POST** also matches the prefix in **GETAWAY**. If you need to distinguish a standalone **GET** command, you must add an appropriate boundary, such as **(?:GET|POST)\b** for word-like tokens or a pattern that includes the delimiter.

Upon success, **group()**, **start()**, and **end()** identify the matched prefix so the program can continue processing the text that follows.

**lookingAt()** always tries from the start of the region, even if the Matcher previously ran another search. However, to compare the three methods fairly and clearly, use separate Matchers or call **reset()** between independent scenarios.

## 6. find(): Scanning and Extracting Multiple Matches

**find()** looks for a matching subsequence from the current search position; on success, the next **find()** call continues after the just-matched portion. Common case:

~~~java
Pattern number = Pattern.compile("\\d+");
Matcher matcher = number.matcher("A12 B345 C6");

while (matcher.find()) {
    System.out.println(matcher.group());
}
~~~

Output:

~~~text
12
345
6
~~~

**find()** is commonly used for logs, free text, ID extraction, token searching, or finding occurrences of a pattern. Each time **find()** succeeds, the new match information replaces the previous match result.

### 6.1. find(int start) and reset()

The **find(int start)** overload starts searching from a specified index in the **input string** and **resets the Matcher before searching**:

~~~java
Matcher m = Pattern.compile("aba").matcher("ababa");

System.out.println(m.find());    // true: [0,3)
System.out.println(m.start());   // 0
System.out.println(m.find());    // false (does not scan overlapping the already matched segment)

System.out.println(m.find(2));   // true: [2,5)
System.out.println(m.start());   // 2
~~~

The second **aba** match starts at index 2, overlapping the first one. Sequential **find()** does not return overlapping matches by default. **find(2)** is an explicit way to start a new search from index 2; it is not an automatic behavior for finding all overlapping positions.

**find(int start)** invokes reset logic, so you should not assume it preserves a custom region or prior search state. If a specific region is needed, reconfigure the region after resetting or create a new Matcher.

### 6.2. Patterns That Match the Empty String

Some regexes can match **zero length**, such as **a*** or the word boundary **\b**. In that case **start() == end()**. Matcher has a mechanism to advance the search position so a **while (find())** loop does not loop forever at an empty position, but the results may include empty matches that the application does not want.

If you need to extract content that actually has characters, verify whether the regex allows zero length; for example **\\d+** requires at least one digit, whereas **\\d*** allows the empty string as well.

## 7. Match Results, Capturing Groups, and Matcher State

After **a successful match** of any of the methods:

- **group()** or **group(0)**: the entire matched substring.
- **group(1)**, **group(2)**, ...: values of *capturing groups* numbered starting from 1 according to the capturing parentheses in the regex.
- **start()**, **end()**: the start index and exclusive end index of the entire match; there are overloads **start(group)** and **end(group)**.
- Indices use offsets in **UTF-16 units** of Java String, which do not necessarily equal the number of visible characters when emojis or Unicode supplementary characters are present.

Capturing group example:

~~~java
Pattern p = Pattern.compile("([A-Z]+)-(\\d+)");
Matcher m = p.matcher("x AB-12 y");

if (m.find()) {
    System.out.println(m.group());  // AB-12
    System.out.println(m.group(1)); // AB
    System.out.println(m.group(2)); // 12
    System.out.println(m.start());  // 2
    System.out.println(m.end());    // 7
}
~~~

If a group is **optional and did not participate in the match**, **group(n)** returns **null**, while **start(n)** and **end(n)** return **-1**. This differs from a group that participated and matched the empty string, in which case **group(n)** is **""**.

**Very important:** do not call **group()**, **start()**, or **end()** to retrieve results before any successful match or right after a failed match; Java will throw **IllegalStateException**. Check the boolean first:

~~~java
Matcher m = Pattern.compile("\\d+").matcher("abc");

if (m.find()) {
    System.out.println(m.group());
} else {
    System.out.println("No number found");
}
~~~

A group index exceeding the valid number of capturing groups also causes a group index error. Additionally, use **(?:...)** when you only need syntactic grouping without capturing data.

**Matcher is not safe to share concurrently across multiple threads** because it carries mutable state. **Pattern** can be shared across threads; each thread or task should create its own Matcher.

## 8. region(), Anchors, and Flags: Common Misconceptions

### 8.1. region(start, end) Changes the Search Scope

~~~java
Matcher m = Pattern.compile("\\d+")
        .matcher("xx123yy")
        .region(2, 5);

System.out.println(m.matches()); // true
System.out.println(m.start());   // 2
System.out.println(m.end());     // 5
~~~

Here the original input is **xx123yy**, but the region **[2,5)** contains only **123**, so **matches()** succeeds. **start()** and **end()** are still offsets in the original input.

The region also governs the starting point of **lookingAt()** and the search range of **find()**. By default, Matcher uses **anchoring bounds = true**, allowing **^** and **$** to treat region boundaries as anchors; **transparent bounds = false** prevents certain lookaheads/lookbehinds and word boundaries from seeing past the region. When a regex relies on lookaround/anchors at region boundaries, you may need to understand **useAnchoringBounds(...)** and **useTransparentBounds(...)**.

### 8.2. ^, $, MULTILINE, and DOTALL Do Not Turn the Three Methods into One Another

- **^** and **$** are anchors in the **regex**. **matches()** inherently requires covering the entire region even without writing anchors.
- **Pattern.MULTILINE** changes the meaning of anchors **^** and **$** so they can also attach to line boundaries; it **does not** turn **matches()** into searching for an arbitrary line within the whole input.
- **Pattern.DOTALL** allows the dot **.** to match newline characters as well; if the regex **a.b** is used with **matches()** on **"a\nb"**, the default result is **false**, whereas it can be **true** when DOTALL is enabled.

Example separating regex, mode, and method:

~~~java
String lines = "one\ntwo";
Pattern p = Pattern.compile("^two$", Pattern.MULTILINE);

System.out.println(p.matcher(lines).find());    // true
System.out.println(p.matcher(lines).matches()); // false
~~~

**find()** finds the second line thanks to MULTILINE for **^two$**. **matches()** still requires the entire region from **one** to **two** to match.

### 8.3. Backslashes in Java Regexes

Both Java String literals and regex syntax use the **\** character. For the regex engine to receive **\d+**, the Java code must write **"\\d+"**. Likewise, the word boundary regex **\b** must be written in Java as **"\\b"**; writing **"\b"** produces a backspace character at the Java String layer and gives the regex a different meaning.

## 9. Choosing the Right Method for the Task

| Task | Recommended | Reason |
| --- | --- | --- |
| Validate that a code consists only of digits | **matches()** with regex **\\d+** | Does not allow extra leading/trailing characters |
| Check whether the start of a statement has a valid token | **lookingAt()** with regex and token boundary | Only requires matching from the start |
| Extract all numbers in log content | **while (find())** loop | Scans each matching subsequence |
| Check whether text contains at least one email matching a pattern | **find()** | Only needs one matching subsequence |
| Validate the entire input value against a format | **matches()** | Every character in the region must be covered by the regex |

For business data validation, regex only verifies **syntax**. For example, a date matching **\\d{4}-\\d{2}-\\d{2}** can still be a nonexistent date; value validation with an appropriate API is still needed.

## 10. Common Mistakes and Self-Checks

1. **Using matches() and being surprised when it returns false.** Check for extra characters or newlines; if you want to find a subsequence try **find()**, if you want a prefix try **lookingAt()**.
2. **Using lookingAt() to validate the entire input.** It can return true for a string with an invalid suffix. Use **matches()** if the whole input must be valid.
3. **Calling find() only once even though all matches are needed.** Use a **while (matcher.find())** loop; read **group()** inside each iteration.
4. **Reading group() after find() returns false.** There is no longer a valid match result for the failed check; only read match info in the boolean true branch.
5. **Reusing a Matcher while forgetting its current position.** Call **reset()** or create a new Matcher before an independent scenario; a **Pattern** can be reused.
6. **Wanting overlapping matches but calling find() consecutively.** Sequential results do not overlap by default; design the search from an appropriate index or use lookahead depending on the problem.
7. **Confusing \d with the Java string "\\d" or forgetting to escape.** Check both the Java string and regex layers; if building a regex from user input, consider **Pattern.quote(...)** when the input should be treated as plain text.
8. **Thinking ^ and $ are always equivalent to matches().** Anchors are affected by MULTILINE, region, and bounds; **matches()** has its own full-region coverage condition.

## 11. Remembering Through Three Questions

Given a compiled **Pattern** and a **Matcher** on an input/region:

- **"Is the entire region valid according to the pattern?" → matches().**
- **"Does the region start with this pattern?" → lookingAt().**
- **"Where in the region is there a match, and how many are there?" → find().**

When a match succeeds, extract **group/start/end** right then; when an independent check is needed, start with a new Matcher or **reset()**. The core difference is **the scope to cover and the starting position**, not three different regex syntaxes.
