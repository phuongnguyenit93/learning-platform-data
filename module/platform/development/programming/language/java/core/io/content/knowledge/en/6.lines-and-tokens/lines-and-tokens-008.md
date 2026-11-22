# Scanner.hasNext(), InputMismatchException, and Handling Invalid Tokens

## 1. Problem: Input Can Contain Tokens of the Wrong Type

**Scanner** in package **java.util** reads text, splits data into **tokens** using a **delimiter** expression, and converts tokens to Java types such as **int**, **double**, **boolean**, or retrieves them as **String**. The default delimiter is whitespace per **Character.isWhitespace**, typically including spaces, tabs, and line breaks.

For example, with input:

~~~text
12 abc 3.5 -7 2147483648 25
~~~

There are six tokens: **12**, **abc**, **3.5**, **-7**, **2147483648**, **25**. If the program expects all of them to be **int**, then **abc**, **3.5**, and **2147483648** cannot be read with **nextInt()** (the last exceeds the signed 32-bit int range). An invalid token does not mean the stream has ended. Distinguish:

- **Are there any tokens left?** → **hasNext()**.
- **Can the next token be parsed as an int?** → **hasNextInt()**.
- **Read and convert the token to int** → **nextInt()**.
- **Wrong token type when calling nextInt()** → **InputMismatchException**.
- **No tokens left when calling nextInt()** → **NoSuchElementException**.

The most important point is that **the token causing InputMismatchException is not automatically skipped by Scanner**. If you keep calling **nextInt()** on the same invalid token, the program can fail in an infinite loop. You must decide whether to **discard the token**, **discard the whole line**, **prompt the user again**, or **halt with an error message** depending on the problem.

## 2. Token Mechanics: Delimiter, Read Position, and Data Consumption

Scanner maintains a read position on the text source. With the default delimiter, spaces or newlines separate tokens; Scanner typically skips delimiters before retrieving the next token.

~~~text
Data:            "  12   abc \n 25 "
Tokens:             12   abc    25
After nextInt():         ↑
                  token 12 has been consumed;
                  next token is abc.
~~~

| Method | Return | Consumes a valid token? | Meaning |
| --- | --- | --- | --- |
| **hasNext()** | boolean | **No** | Whether any next token exists |
| **next()** | String | **Yes** | Retrieves the next token as a string |
| **hasNextInt()** | boolean | **No** | Whether the next token can be converted to int per Scanner's radix/locale |
| **nextInt()** | int | **Yes, if successful** | Converts the next token into an int integer |
| **hasNextDouble()** | boolean | **No** | Whether the next token can be converted to double per applicable rules |
| **nextDouble()** | double | **Yes, if successful** | Converts the next token into a double |

**hasNext() is not hasNextInt().** When the next token is **abc**, **hasNext() == true** yet **hasNextInt() == false**. When the token is **3.5**, **hasNext()** is still true, whereas **hasNextInt()** is false even though **hasNextDouble()** may be true under a locale allowing decimal points.

**hasNextInt() does not consume the token**: two consecutive calls to **hasNextInt()** inspect the exact same token if nothing else has consumed it. Only when **nextInt()** succeeds is the token consumed and Scanner's position advanced.

Note that **hasNext() / hasNextInt()** may **block** waiting for data from interactive or network sources. Even a single `hasNext()` returning true is not an absolute guarantee that the next `next()` will not block, per the API contract. Do not treat them as non-blocking, instantaneous checks.

## 3. What Is InputMismatchException? When Does It Occur?

**java.util.InputMismatchException** is an **unchecked exception** (subclass of **NoSuchElementException**). It occurs when the current token **does not match the type or value range** required by a **nextXxx()** method.

Examples with **nextInt()**:

| Next token | nextInt() (base 10) | Explanation |
| --- | --- | --- |
| **42** | 42 | Valid |
| **-7** | -7 | Valid |
| **abc** | InputMismatchException | Does not represent an integer |
| **3.14** | InputMismatchException | Does not represent an int |
| **2147483648** | InputMismatchException | Greater than **Integer.MAX_VALUE = 2147483647** |
| **-2147483649** | InputMismatchException | Less than **Integer.MIN_VALUE = -2147483648** |
| No tokens left | NoSuchElementException | EOF/no tokens left, distinct from type mismatch |

Number recognition rules are also affected by **locale** and **radix**. Never assume every decimal/grouping symbol is interpreted identically across all environments. The examples below use simple ASCII tokens and set locale explicitly where needed.

### 3.1. The Offending Token Remains Intact for Handling

Visualize it like this:

~~~text
Scanner is at token "abc".
nextInt() → InputMismatchException.
Scanner is still at token "abc".
nextInt() again → InputMismatchException again.
next() → "abc"; consumes the invalid token.
nextInt() next → tries the token following "abc".
~~~

According to Java documentation, when Scanner throws **InputMismatchException**, Scanner **does not skip the token** that caused the error, so the application can still read or discard it using another method. This is a common reason why a loop like **while (scanner.hasNext()) { scanner.nextInt(); }** crashes with an exception at the first bad token; if you catch it without advancing the position, the loop gets stuck.

**Do not use hasNextInt() alone as the loop condition when you want to continue past invalid tokens**:

~~~java
while (scanner.hasNextInt()) {
    System.out.println(scanner.nextInt());
}
~~~

The snippet above is **valid** if you only accept *a contiguous sequence of ints up to the first non-int token*. However, on input **1 bad 2**, the loop reads only **1**, stops at **bad**, and never reaches **2**. To **skip invalid tokens and continue**, use a **hasNext()** loop with a branch handling invalid tokens.

## 4. Recommended Strategy: hasNext() + hasNextInt() + next()

For a token stream where the goal is to **filter valid integers**, a readable approach is:

1. Use **hasNext()** to check whether tokens remain.
2. Use **hasNextInt()** to check the type, **without advancing the position**.
3. If valid, use **nextInt()** to consume and use the number.
4. If invalid, use **next()** to **consume exactly one token** and log/skip it.
5. Loop until no tokens remain.

Standalone runnable Java 17+ example. Save as **ScannerTokenDemo.java**:

~~~java
import java.util.Locale;
import java.util.Scanner;

public class ScannerTokenDemo {
    public static void main(String[] args) {
        String data = "12 abc 3.5 -7 2147483648 25";

        try (Scanner scanner = new Scanner(data).useLocale(Locale.US)) {
            while (scanner.hasNext()) {
                if (scanner.hasNextInt()) {
                    int number = scanner.nextInt();
                    System.out.println("INT: " + number);
                } else {
                    String invalid = scanner.next();
                    System.out.println("INVALID: " + invalid);
                }
            }
        }
    }
}
~~~

Compile and run:

~~~bash
javac ScannerTokenDemo.java
java ScannerTokenDemo
~~~

Exact output:

~~~text
INT: 12
INVALID: abc
INVALID: 3.5
INT: -7
INVALID: 2147483648
INT: 25
~~~

**12**, **-7**, and **25** are read successfully. **abc** is not a number, **3.5** is a decimal number rather than an int, and **2147483648** exceeds int range. Each time an invalid token is encountered, **next()** consumes it; thus the loop **always makes progress** and still reads **25** after the bad tokens.

**Locale.US** here makes the number-parsing environment explicit. **nextInt()** returns a true **int**; there is no need to run **Integer.parseInt(scanner.next())** again after a successful check, unless the application deliberately wants custom String validation rules.

## 5. Alternative Strategy: try/catch InputMismatchException

When code intentionally calls **nextInt()** directly, try/catch can handle type mismatches. The mandatory requirement is that the **catch branch must advance the position** or choose to stop, avoiding re-encountering the bad token.

Standalone runnable Java 17+ example; save as **ScannerMismatchDemo.java**:

~~~java
import java.util.InputMismatchException;
import java.util.Scanner;

public class ScannerMismatchDemo {
    public static void main(String[] args) {
        try (Scanner scanner = new Scanner("8 oops 9")) {
            while (scanner.hasNext()) {
                try {
                    int number = scanner.nextInt();
                    System.out.println("number=" + number);
                } catch (InputMismatchException ex) {
                    // Failed nextInt() does not consume the token.
                    String bad = scanner.next();
                    System.out.println("skipped=" + bad);
                }
            }
        }
    }
}
~~~

Run:

~~~bash
javac ScannerMismatchDemo.java
java ScannerMismatchDemo
~~~

Output:

~~~text
number=8
skipped=oops
number=9
~~~

If you remove **scanner.next()** inside **catch**, the loop keeps hitting "oops" forever; **scanner.hasNext()** remains true and **scanner.nextInt()** keeps throwing the same exception. Hence, whenever pre-checking with **hasNextInt()** is possible, the approach in section 4 is usually clearer and avoids using exceptions for expected invalid-data control flow.

**Do not catch overly broad Exception just to swallow every error**. When a program requires a strict data structure, encountering a bad token may need to report an error and stop, rather than silently dropping data.

## 6. InputMismatchException Differs from NoSuchElementException and IllegalStateException

Common scenarios:

| Scanner State | Operation | Result |
| --- | --- | --- |
| Current token is **abc** | **hasNext()** | true |
| Current token is **abc** | **hasNextInt()** | false |
| Current token is **abc** | **nextInt()** | **InputMismatchException**, token not consumed |
| No tokens left | **hasNext() / hasNextInt()** | false |
| No tokens left | **next() / nextInt()** | **NoSuchElementException** |
| Scanner already **close()**d | **hasNext() / nextInt()** | **IllegalStateException** |

**InputMismatchException extends NoSuchElementException**, so if you need to catch both separately, **catch InputMismatchException first**, then **NoSuchElementException**. If you catch the parent class first, the child catch block afterward becomes unreachable and Java refuses to compile.

Correct catch-order example:

~~~java
try {
    int value = scanner.nextInt();
    System.out.println(value);
} catch (java.util.InputMismatchException ex) {
    System.out.println("Sai định dạng int");
} catch (java.util.NoSuchElementException ex) {
    System.out.println("Không còn token");
}
~~~

This is an **illustrative snippet**, assuming **scanner** is already created and open. In an application processing multiple tokens, if catching InputMismatchException to continue, you must still **consume the bad token** via **next()** or choose to terminate. This catch block only illustrates distinguishing exceptions and catch order.

## 7. Tokens and Lines Differ: hasNext() Is Not hasNextLine()

A common mistake is thinking **Scanner** always processes full lines. In fact:

- **hasNext() / next()** work by **token**, separated by whitespace by default, including line breaks.
- **hasNextLine() / nextLine()** work by **line**; **nextLine()** reads the remainder of the current line, *excluding line-ending characters*, then moves to the next line.
- A blank line can be returned by **nextLine()** as an empty String. **hasNext()** can be false when the source has only whitespace or blank lines remaining.
- **nextInt()** reads a numeric token but typically **leaves the newline character behind**, so calling **nextLine()** right after may return an empty String because it only reads the rest of the same line.

Standalone runnable Java 17+ example; save as **ScannerLineDemo.java**:

~~~java
import java.util.Scanner;

public class ScannerLineDemo {
    public static void main(String[] args) {
        String data = "42\nhello world\n\nZ";

        try (Scanner scanner = new Scanner(data)) {
            int number = scanner.nextInt();
            String rest = scanner.nextLine();
            String line1 = scanner.nextLine();
            String line2 = scanner.nextLine();
            String line3 = scanner.nextLine();

            System.out.println("number=" + number);
            System.out.println("rest=[" + rest + "]");
            System.out.println("line1=[" + line1 + "]");
            System.out.println("line2=[" + line2 + "]");
            System.out.println("line3=[" + line3 + "]");
        }
    }
}
~~~

Compile/run:

~~~bash
javac ScannerLineDemo.java
java ScannerLineDemo
~~~

Output:

~~~text
number=42
rest=[]
line1=[hello world]
line2=[]
line3=[Z]
~~~

After **nextInt()**, Scanner sits right after token **42** while still on the first line; the first **nextLine()** reads the empty remainder and consumes the newline. Only the subsequent **nextLine()** gets "hello world". The following blank line becomes **line2=[]**.

If the input structure is **one record per line**, use **while (scanner.hasNextLine())**, read **line = scanner.nextLine()**, and validate tokens within that line itself. Line-based parsing lets you report exact line numbers on errors and avoids accidentally consuming into another record. Conversely, if the data is simply **a stream of tokens regardless of lines**, using hasNext()/next() is more natural.

## 8. Handling Bad Tokens: Skip One Token or Skip the Whole Line?

Suppose the input is:

~~~text
10 bad 20
30 40
~~~

**Skip exactly one token:** when "bad" fails, call **scanner.next()**; afterward the program still reads **20**, **30**, **40**. Suitable when tokens are independent and every valid number matters.

**Skip the remainder of the line:** when a record must have a fixed structure, hitting "bad" may require calling **scanner.nextLine()** to discard the rest of the current line. Then **20** is also discarded along with the first line; the next line still provides **30 40**. Do not use this strategy if you want to keep 20.

**Stop with an error message:** when each line must satisfy a data contract (for example, exactly 3 numeric fields), it is better to report the line clearly and reject the record rather than pretending the data is complete.

**Prompt to re-enter:** in interactive console input, after a user enters an invalid token, discard the bad token or current line before reading the new answer; otherwise the next iteration re-checks the exact same old token.

No single recovery policy fits every application. The general engineering rule is: **never let an error-handling branch loop infinitely on an unconsumed token**.

## 9. Delimiter, Locale, Radix, and Why a Token Is Rejected

### 9.1. Default Delimiter and Custom Delimiter

With the default delimiter, input **"10 20"** has two tokens. However, **"10,20"** is a single token because a comma is not a default Scanner separator. To split on commas, configure a regular expression:

~~~java
Scanner scanner = new Scanner("10,abc,20")
        .useDelimiter("\\s*,\\s*");
~~~

This snippet assumes **import java.util.Scanner**; in real code, close the Scanner if you own it. The delimiter above matches a comma with optional whitespace on both sides, suited for simple examples. It **is not a full CSV parser**: CSV with quotes and commas inside fields requires a standards-compliant CSV parser.

If the delimiter does not match the data format, **hasNextInt()** can return false simply because tokens were merged incorrectly, even when each individual piece is numeric.

### 9.2. Locale Affects Number Syntax

**Scanner.useLocale(Locale.US)** selects grouping separators, decimal points, and number forms matching that locale. For example, **1.5** is normally a valid decimal under Locale.US; under another locale, the decimal mark might be a **comma**. When reading decimal numbers, set locale explicitly so code behaves identically across development and production environments.

**hasNextInt()** does not "truncate the integer part" of a decimal number. Token **3.5** is not an **int** under standard settings; if floating-point numbers are required, use **hasNextDouble() / nextDouble()** or dedicated rules.

### 9.3. Radix Affects Integer Parsing

By default, integers are parsed in base **10**, yet you can use **scanner.useRadix(16)** or **nextInt(16)** to parse base 16. Example:

~~~java
try (Scanner scanner = new Scanner("FF")) {
    scanner.useRadix(16);
    System.out.println(scanner.hasNextInt());
    System.out.println(scanner.nextInt());
}
~~~

This snippet requires importing **java.util.Scanner**; output is **true** then **255**. Without setting base 16, token **FF** is not a decimal integer. Hence **InputMismatchException** can also indicate *violating the active interpretation rule*, not merely letters inside a token.

For numeric tokens too large for **int**, you can choose **nextLong()** or **nextBigInteger()** if the contract genuinely allows a wider value range; do not switch types arbitrarily when the program only permits int.

## 10. Strict Data Validation vs. Casual Token Filtering

The **hasNext() + hasNextInt() + next()** pattern fits when you want to **filter valid tokens** out of a stream that may contain noise. However, if an application parses a structured protocol, it must enforce **exact order, exact field count, exact types, and no extra fields**.

For example, a record must contain strictly **two integers** like:

~~~text
12 34
~~~

Simply looping to find any two int tokens is insufficient, because input **12 wrong 34** would skip "wrong" and still be accepted. A stricter approach is reading the whole line, extracting strictly the expected fields, validating **every token**, and rejecting lines with extra/invalid data.

You can use a second Scanner over each line's String:

~~~java
String line = scanner.nextLine();
try (Scanner row = new Scanner(line)) {
    if (!row.hasNextInt()) {
        throw new IllegalArgumentException("Thiếu hoặc sai số thứ nhất");
    }
    int first = row.nextInt();

    if (!row.hasNextInt()) {
        throw new IllegalArgumentException("Thiếu hoặc sai số thứ hai");
    }
    int second = row.nextInt();

    if (row.hasNext()) {
        throw new IllegalArgumentException("Dữ liệu thừa trong bản ghi");
    }
    System.out.println(first + second);
}
~~~

This is an **illustrative snippet**, assuming **scanner** is open to read input lines and **java.util.Scanner** is imported. If processing one record per line, check **scanner.hasNextLine()** before calling **nextLine()** and wrap each line in try/catch per your error policy. This snippet illustrates **not silently discarding invalid tokens** in records requiring strict formatting.

## 11. Edge Cases, Source Errors, and Resources

### 11.1. EOF and Scanner Reading from Console

A **Scanner(System.in)** typically reads user-entered data. If no tokens are present and the console source remains open, **hasNext()** may **block waiting for user input**; false normally appears only when the source reaches EOF. In a console, ending input depends on the OS/terminal, such as an EOF key combination. Do not equate "nothing typed yet" with end of data.

When you own a Scanner reading a file or String, use **try-with-resources**. However, **closing Scanner(System.in)** also closes the underlying **System.in** wrapped by Scanner; avoid closing it when other parts of the application still need standard input.

### 11.2. IOException Can Be Treated as End of Input by Scanner

Per Scanner's contract, when the underlying **Readable** throws an **IOException** during reading, Scanner **assumes it has reached the end of input**. You can retrieve the most recent IOException via **scanner.ioException()**. In applications that must distinguish normal EOF from file/network read failures, inspect `ioException()` afterward instead of assuming every **hasNext() == false** means clean completion.

Example check after the loop:

~~~java
java.io.IOException readFailure = scanner.ioException();
if (readFailure != null) {
    throw new java.io.UncheckedIOException(readFailure);
}
~~~

This snippet assumes **scanner** is still open. It illustrates not ignoring I/O errors when system policy requires reporting failures, even though input data is normally consumed by Scanner as tokens.

### 11.3. Scanner and Performance

Scanner is convenient because it combines regex delimiters, locale, and type parsing, yet it carries higher overhead than reading bytes/chars and parsing manually in certain massive workloads. For high-volume data with simple rules, **BufferedReader** with String processing or a dedicated parser may fit better after benchmarking. Do not switch reading strategies merely assuming Scanner is always slow: measure on real data.

**Scanner is not thread-safe for concurrent use across multiple threads without external synchronization.** Sharing one Scanner between tasks lets one task consume another's tokens, breaking atomicity of hasNext/next.

## 12. Common Mistakes

1. **Using hasNext() and assuming nextInt() is always valid.** hasNext only checks whether a token exists. Use **hasNextInt()** when expecting an int.
2. **Using while (hasNextInt()) when invalid tokens should be skipped.** The loop stops at the first bad token, missing valid tokens afterward; use **while (hasNext())** with an error-handling branch.
3. **Catching InputMismatchException and immediately calling nextInt() again.** The bad token remains at the current position; call **next()** to discard it or change strategy.
4. **Confusing format mismatch with EOF.** nextInt on a bad token throws InputMismatchException; when out of tokens, it throws NoSuchElementException.
5. **Ignoring numbers exceeding int range.** "2147483648" contains valid digits yet does not fit int. Define value bounds and choose an appropriate type.
6. **Mixing nextInt() and nextLine() without accounting for the rest of the line.** nextLine directly after nextInt may return an empty String; design line/token boundaries clearly.
7. **Using nextLine() to skip an error while wanting to keep remaining tokens on the same line.** nextLine skips the rest of the current line; to skip just one token, call next().
8. **Assuming commas are always delimiters.** Scanner splits on whitespace by default; declare a delimiter or use a format-specific parser.
9. **Ignoring locale/radix.** Numeric methods depend on parsing rules; configure locale and radix appropriately for predictable input.
10. **Silently dropping bad tokens in strict protocols.** For records requiring integrity, report errors or reject rather than stitching disjoint valid tokens together.
11. **Ignoring source IOException.** Scanner can treat I/O failures as EOF; check **ioException()** when distinction matters.
12. **Closing Scanner(System.in) when other components still need to read.** Closing the wrapper can close the underlying source.

## 13. Self-Check and Answers

**Question 1:** Scanner is at token **"abc"**. What are the results of **hasNext()**, **hasNextInt()**, and **nextInt()** in order?  
**Answer:** **true**, **false**, then **InputMismatchException**. Token "abc" remains intact after the exception.

**Question 2:** What numbers does **while (scanner.hasNextInt())** read on input **"1 bad 2"**?  
**Answer:** Only **1**. It stops at "bad"; to continue, handle the bad token with **next()** or another strategy.

**Question 3:** Why can't **2147483648** be read by **nextInt()**?  
**Answer:** It exceeds **Integer.MAX_VALUE (2147483647)**. You may use a wider numeric type if the contract permits, rather than silently discarding out-of-range errors.

**Question 4:** What exception does calling **nextInt()** after the source has run out of tokens throw?  
**Answer:** **NoSuchElementException**, not InputMismatchException.

**Question 5:** If you need to skip a bad token **while keeping subsequent tokens on the same line**, should you call **next()** or **nextLine()**?  
**Answer:** **next()** consumes only the bad token; **nextLine()** would discard the entire remainder of the line.

**Question 6:** Why does **nextLine()** right after **nextInt()** often return an empty String?  
**Answer:** nextInt consumes only the numeric token, leaving the newline character behind; nextLine reads the remainder of the current line, which may have no characters left.

**Question 7:** Can token **FF** be accepted by **hasNextInt()**?  
**Answer:** Yes, if Scanner is using base 16 (**useRadix(16)**). In the default base 10, it is not a valid int.

## 14. Conclusion

**hasNext()** determines whether a token remains; **hasNextInt()** checks whether the next token can be parsed as an **int**; **nextInt()** consumes and converts the token on success. When a token has the wrong type or is out of range, **nextInt() throws InputMismatchException and leaves the bad token unconsumed**. When no tokens remain, **nextInt() throws NoSuchElementException**.

To **filter and continue reading past invalid tokens**, use **while (hasNext())**, choosing **hasNextInt() → nextInt()** or **next() to discard the bad token** inside the loop. For structured data, validate every line/record completely and report errors per contract instead of arbitrarily dropping data.

### Official References

- [Oracle Java SE 21 — Scanner](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Scanner.html): delimiters, hasNext/next, hasNextInt/nextInt, unconsumed invalid tokens, ioException, locale, radix, blocking.
- [Oracle Java SE 21 — InputMismatchException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/InputMismatchException.html): exception class and inheritance hierarchy.
- [Oracle Java SE 21 — NoSuchElementException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/NoSuchElementException.html): exception when no elements/tokens remain.
