# From Input to Processing and Output in a Java Program

> **Java core — language-basics / Overview**  
> **Goal:** After this lesson, you can explain the **Input → Processing → Output (IPO)** pipeline, know where a Java program receives data, how it validates and transforms it, and how it prints results or reports errors. You can also compile and run a simple console application yourself, testing normal data and boundary cases.

## 1. What Does a Program Do with Data?

Imagine a user wants to calculate the total cost of buying pens. They enter the item name, unit price, and quantity. The program validates the data, computes the total amount, and then displays the result.

| Stage | Questions to answer | Purchase example |
| --- | --- | --- |
| **Input** | Where does the data come from? What is its initial form? | The keyboard provides `"Bút bi"`, `"12000"`, `"3"` as lines of characters |
| **Processing** | Is the data valid? What needs to be calculated or decided? | Parse price to `long` and quantity to `int`, verify price is non-negative and quantity is positive; compute `12000 × 3` |
| **Output** | Where is the result or error sent? | Print `Tổng tiền: 36000 VND` or the reason why the input is invalid |

Do not confuse **input** with “already processed data”. The user types `12000` on the keyboard; the program first receives the **character string** `"12000"`, and only then converts it into the number `12000L`. Reading input successfully **does not** mean the data is valid.

~~~mermaid
flowchart TD
    A["User / data source"] --> B["Read input: line of characters"]
    B --> C["Parse + validate"]
    C --> D{"Valid?"}
    D -->|No| E["Report error via stderr"]
    D -->|Yes| F["Business processing: calculation"]
    F --> G{"Operation valid?"}
    G -->|No| E
    G -->|Yes| H["Print result via stdout"]
~~~

The IPO process does not apply only to the console. For a web application, input can be an HTTP request, processing is validation and computation, and output is an HTTP response. For a file-reading application, input is file content and output can be a result file. **The three thinking steps stay the same**, while how sources and destinations are connected differs.

## 2. Input in Java: Where Does Data Come From?

A typical Java program has several sources of input:

| Source | Typical Java API/usage | When is it appropriate? |
| --- | --- | --- |
| **Command-line arguments** | The `String[] args` array in `main` | Parameters passed **when starting** the program |
| **Keyboard/standard input** | `System.in`, commonly wrapped with `Scanner` or `BufferedReader` | Interactive input in a terminal; receiving data redirected from a file or pipe |
| **Files** | `Files.readString`, `Files.newBufferedReader`, etc. | Reading stored data |
| **Calls from other code** | Method parameters, objects, API/network | Data coming from other components of the system |

Example with command-line arguments:

~~~java
public class ArgumentsDemo {
    public static void main(String[] args) {
        System.out.println("So doi so: " + args.length);
        if (args.length > 0) {
            System.out.println("Doi so dau: " + args[0]);
        }
    }
}
~~~

Compile and run (Java 11+):

~~~bash
javac ArgumentsDemo.java
java ArgumentsDemo xin-chao
~~~

Output:

~~~text
So doi so: 1
Doi so dau: xin-chao
~~~

If you run `java ArgumentsDemo`, `args.length` equals `0`. Trying to access `args[0]` on an empty array causes `ArrayIndexOutOfBoundsException`; therefore, the code above checks the length first.

**Distinction:** `args` is data passed in at startup. `System.in` is a stream for reading **while the program is running**; both can supply strings, but their lifecycles and usage differ.

## 3. Standard Input, Standard Output, and Standard Error

A console application normally uses three standard streams:

| Stream | In Java | Purpose |
| --- | --- | --- |
| **stdin** (*standard input*) | `System.in` | Receives input bytes, usually from the terminal |
| **stdout** (*standard output*) | `System.out` | Prints normal output |
| **stderr** (*standard error*) | `System.err` | Prints error/diagnostic messages |

Example:

~~~java
System.out.println("Tong tien: 36000 VND");
System.err.println("Loi: so luong phai lon hon 0");
~~~

In a terminal, **both lines may appear together on the screen**, making it easy to assume stdout and stderr are the same. However, when streams are redirected, they can be handled separately. This is useful when a program is automated: another program can read results from stdout without confusing them with error messages.

`System.in` is a **byte** stream. When reading text, Java commonly wraps it in an `InputStreamReader` to decode bytes into characters, and then a `BufferedReader` to read line by line:

~~~java
BufferedReader input = new BufferedReader(
        new InputStreamReader(System.in, StandardCharsets.UTF_8));
String line = input.readLine();
~~~

You need to import `java.io.BufferedReader`, `java.io.InputStreamReader`, and `java.nio.charset.StandardCharsets`. `readLine()` returns a `String`, stripping the line terminator; it **returns `null` when input has ended**, rather than returning an empty string. This is an important difference when input comes from a file or pipe.

`Scanner` is a simple choice for many number-input lessons, though `Scanner.nextInt()` depends on token splitting and locale, which can cause surprises when mixing `nextInt()` with `nextLine()`. The main example in this lesson uses `BufferedReader.readLine()`, and then explicitly parses and validates so each IPO step is clearly visible.

## 4. A Complete End-to-End Runnable Program

Problem: the user enters **one item's name**, **unit price in VND**, and **quantity**. The program calculates the total amount for that item.

**Input contract:**

- The item name must not be empty or consist only of whitespace.
- Unit price is an **integer from 0 to `Long.MAX_VALUE`**; a price of 0 is allowed, for example a promotional gift.
- Quantity is a **positive integer from 1 to `Integer.MAX_VALUE`**.
- The total `unit price × quantity` must fit within the `long` range.
- The program reads exactly **three lines** from stdin in exact order.
- When valid, the program prints the item name and total amount to stdout. On error, it prints a message to stderr and exits with a non-zero status.

The example chooses `long` for whole VND currency instead of `float`/`double` to avoid binary rounding errors in currency examples. Real financial software might use `BigDecimal` and require more detailed currency/unit/rounding rules; this lesson simply demonstrates the processing flow and a clear integer contract.

### 4.1. Source Code: PurchaseFlowDemo.java

Create the file **PurchaseFlowDemo.java** and copy all of the following code. The program uses Java 11 or later and requires no libraries outside the JDK.

~~~java
import java.io.BufferedReader;
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public class PurchaseFlowDemo {

    // After validation, the program holds values that already have the right types.
    static final class Purchase {
        final String productName;
        final long unitPriceVnd;
        final int quantity;

        Purchase(String productName, long unitPriceVnd, int quantity) {
            this.productName = productName;
            this.unitPriceVnd = unitPriceVnd;
            this.quantity = quantity;
        }
    }

    // INPUT: read exactly one line of text, without assuming data is always present.
    private static String requestLine(
            BufferedReader reader, String prompt) throws IOException {

        System.out.print(prompt);
        System.out.flush();

        String line = reader.readLine();
        if (line == null) {
            throw new EOFException("Thieu du lieu tai: " + prompt);
        }
        return line.strip();
    }

    // INPUT + VALIDATION: convert String to the appropriate data types.
    private static Purchase readPurchase(
            BufferedReader reader) throws IOException {

        String name = requestLine(reader, "Ten san pham: ");
        String rawPrice = requestLine(reader, "Don gia (VND): ");
        String rawQuantity = requestLine(reader, "So luong: ");

        if (name.isEmpty()) {
            throw new IllegalArgumentException("Ten san pham khong duoc rong");
        }

        long price;
        int quantity;
        try {
            price = Long.parseLong(rawPrice);
            quantity = Integer.parseInt(rawQuantity);
        } catch (NumberFormatException error) {
            throw new IllegalArgumentException(
                    "Don gia va so luong phai la so nguyen hop le", error);
        }

        if (price < 0) {
            throw new IllegalArgumentException("Don gia khong duoc am");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("So luong phai lon hon 0");
        }
        return new Purchase(name, price, quantity);
    }

    // PROCESSING: only computes; does not read from the keyboard or print to the screen.
    private static long calculateTotal(Purchase purchase) {
        return Math.multiplyExact(
                purchase.unitPriceVnd, (long) purchase.quantity);
    }

    // OUTPUT: present the processed result.
    private static void printReceipt(Purchase purchase, long total) {
        System.out.println("Mat hang : " + purchase.productName);
        System.out.println("Tong tien: " + total + " VND");
    }

    public static void main(String[] args) {
        BufferedReader reader = new BufferedReader(
                new InputStreamReader(System.in, StandardCharsets.UTF_8));

        try {
            Purchase purchase = readPurchase(reader);
            long total = calculateTotal(purchase);
            printReceipt(purchase, total);
        } catch (EOFException error) {
            System.err.println("Loi dau vao: " + error.getMessage());
            System.exit(1);
        } catch (IllegalArgumentException | ArithmeticException error) {
            System.err.println("Loi du lieu/tinh toan: " + error.getMessage());
            System.exit(1);
        } catch (IOException error) {
            System.err.println("Loi doc stdin: " + error.getMessage());
            System.exit(1);
        }
    }
}
~~~

There are four clearly visible groups of responsibilities:

| Method | Stage | What it does | What it does **not** do |
| --- | --- | --- | --- |
| `requestLine` | Input | Prompts for input, reads one line, detects end of data | Does not multiply price and quantity |
| `readPurchase` | Input / Validation | Collects three lines, parses to `long`/`int`, rejects invalid input | Does not print the receipt |
| `calculateTotal` | Processing | Computes total with overflow checking | Does not read from `System.in` itself |
| `printReceipt` | Output | Formats and prints the valid result | Does not alter the pricing rule itself |

Separating responsibilities this way lets you see the **data flow** instead of looking at one block of code mixing reading, calculating, and printing. For a smaller program, you can certainly write everything inside `main`; splitting methods here serves an educational purpose, **not a rule forcing every program to have four methods**.

### 4.2. Compile with javac, Run with java

Open a terminal in the directory containing `PurchaseFlowDemo.java`:

~~~bash
javac -encoding UTF-8 PurchaseFlowDemo.java
java PurchaseFlowDemo
~~~

When the program prompts, enter sequentially:

~~~text
Ten san pham: But bi
Don gia (VND): 12000
So luong: 3
Mat hang : But bi
Tong tien: 36000 VND
~~~

The three lines starting with prompts are the **interactive part where you type and press Enter**; the two lines `Mat hang` and `Tong tien` are the output printed by the program. The compiler generates `PurchaseFlowDemo.class`, while the command `java PurchaseFlowDemo` launches the compiled class. Do **not** append `.class` when passing the class name to `java`.

Try entering `0` for unit price and `5` for quantity; the result will be `0 VND`. Try entering leading/trailing spaces on the item name: `strip()` trims whitespace at both ends. How accented characters display in the terminal depends on the console/encoding configuration; the code specifies UTF-8 for **input**.

## 5. How Does Data Flow Through the Program?

Given the input:

~~~text
But bi
12000
3
~~~

The table below simulates each state:

| Step | Value in the program | Data type | Meaning |
| --- | --- | --- | --- |
| Read name | `"But bi"` | `String` | Empty name not yet checked |
| Read price | `"12000"` | `String` | Still text |
| Read quantity | `"3"` | `String` | Still text |
| Parse and validate price | `12000L` | `long` | Non-negative integer |
| Parse and validate quantity | `3` | `int` | Positive integer |
| Compute | `36000L` | `long` | `12000 × 3` |
| Print result | `"Tong tien: 36000 VND"` | String written to stdout | User sees the result |

Data is **converted from an external representation** (string) into **typed Java values**, and then checked against business rules. There is no valid processing step if the quantity is `"ba"`: calling `Integer.parseInt("ba")` throws `NumberFormatException`; in the example, the error is turned into a clearer message for the user.

Distinguish two kinds of questions:

- **Syntactically valid?** `"1000"` parses as a number; `"1,000"` or `"1 000"` does not parse directly with `Long.parseLong`.
- **Business-valid?** `"-100"` parses as a number, yet a **negative price** is rejected; `"0"` parses as a number, yet a **quantity of 0** is invalid per the contract.

The calculation code uses `Math.multiplyExact` instead of ordinary multiplication so it **never returns an overflowed number** if price × quantity exceeds the `long` range.

## 6. Edge Cases: Broken Input and How the Program Responds

| Input data | What happens | Why? |
| --- | --- | --- |
| Name is empty or all whitespace | Prints empty-name error | `strip()` and `isEmpty()` detect a name with no content |
| Price is `-1` | Prints negative-price error | Parses successfully, but violates business rule |
| Price is `0`, quantity is `2` | Prints total `0 VND` | Price 0 is permitted by the contract |
| Quantity is `0` | Prints non-positive quantity error | Rule requires at least one item |
| Quantity is `2.5` or `hai` | Prints integer error | `Integer.parseInt` does not accept decimals or words |
| Price is `1_000` | Prints integer error | Underscores are valid in **Java source literals**, not syntax accepted from users by `parseLong` |
| Price exceeds `Long.MAX_VALUE` | Prints integer error | Number cannot be represented by `long` |
| Price = `Long.MAX_VALUE`, quantity = `2` | Prints arithmetic error | `Math.multiplyExact` detects `long` overflow |
| Only two lines provided before stdin ends | Prints missing-data error | `readLine()` returns `null` at EOF |
| Blank line between two values | Blank line is read as real input | `readLine()` does not skip blank lines automatically |
| Fourth line added | Program ignores the fourth line | Example contract reads only three lines |

An error does not mean “the program prints a total of 0”. **You should not silently turn bad input into 0 just to avoid errors**, because then the user cannot tell invalid data apart from valid values. The program stops with exit code 1 and writes the error to stderr, rather than producing a receipt that looks successful.

One small but meaningful point: in this example, `readPurchase` **reads all three lines before checking the name**. If the name is empty, the user is still prompted for price and quantity before seeing the error message. That is a processing-order choice made by this example, **not** Java's default behavior. You can improve UX by validating immediately after reading each field, while noting the difference in prompt order.

## 7. Automated Testing and Stream Redirection

Because the program reads from **stdin**, you do not have to type manually. In shells that support pipes, another command can feed data to it.

**macOS/Linux — terminal shell:**

~~~bash
printf 'But bi\n12000\n3\n' | java PurchaseFlowDemo
~~~

**Windows PowerShell:**

~~~powershell
@('But bi', '12000', '3') | java PurchaseFlowDemo
~~~

The output produces the same calculation result; when stdin is piped from another command, the prompts may appear run together on one line because the input data itself **is not necessarily echoed back by the terminal**. Do not compare the prompt formatting of piped runs directly against a manual typing transcript.

To see that stderr is separate from stdout (for example on macOS/Linux or a shell supporting equivalent syntax):

~~~bash
printf 'But bi\n12000\n0\n' | java PurchaseFlowDemo > result.txt 2> errors.txt
~~~

- `> result.txt` redirects **stdout** to the file `result.txt`.
- `2> errors.txt` redirects **stderr** to `errors.txt`.
- In the invalid-quantity case, `errors.txt` holds the error message; `result.txt` may hold the input prompts the program printed before failing.
- A non-zero exit code indicates the program did not complete successfully. How to inspect the exit code varies by shell, e.g. `echo $?` in Bash after the command.

**Note:** The redirection commands above affect the **process** streams; `System.out` and `System.err` are still the Java APIs. Java does not need to know whether data comes from a keyboard, a file, or a pipe in order to read line by line with `BufferedReader`.

## 8. Debugging by Tracing Backward Along the Data Flow

When the result is wrong, trace step by step:

1. **Did input arrive?** Did `readLine()` return `null` or a string? Is it waiting for Enter?
2. **What string was read?** Are there leading/trailing spaces, blank lines, or unexpected separators? Avoid printing passwords/sensitive info when debugging.
3. **How was it parsed?** Does `parseInt/parseLong` accept that string? Does the numeric type have sufficient range?
4. **Were business rules checked?** Are negative prices, zero quantities, or out-of-bounds values blocked?
5. **Is the arithmetic safe?** Could addition or multiplication overflow `int`/`long`? If needed, use the corresponding `Math.*Exact` methods.
6. **What output was produced?** Is success output emitted only when all prior steps succeed? Do error messages go to stderr?

Some common issues:

| Symptom | Possibility | What to Check |
| --- | --- | --- |
| Program “hangs” after a prompt | Waiting for data from stdin | Type a line and press Enter, or supply enough input via pipe |
| `NumberFormatException` | String is not a supported integer | Check for stray characters, commas, or overly large numbers |
| `NullPointerException` when calling a method on `readLine()` | EOF not handled first | Check for `null` like `requestLine` does |
| Price looks right, yet total is unexpectedly negative | Numeric overflow with ordinary multiplication | Use `Math.multiplyExact` and handle the error |
| Machine displays Vietnamese diacritics incorrectly | Console encoding mismatch | Check terminal, source/input/output charsets |
| Main class not found | Wrong working directory/classpath/class name | Verify compilation succeeded and run `java PurchaseFlowDemo` |

Do not assume every input error is an `IOException`: invalid number conversion usually causes `NumberFormatException` (an `IllegalArgumentException`), while actual failures reading the source are `IOException` cases. Distinguishing them makes error messages and fixes more accurate.

## 9. From Console Example to Testable Design

Input/output depends on the **environment**; the calculation part can be written as a pure function. That is why we separated:

~~~java
private static long calculateTotal(Purchase purchase) {
    return Math.multiplyExact(
            purchase.unitPriceVnd, (long) purchase.quantity);
}
~~~

If unit price is `12000` and quantity is `3`, the method returns `36000` without needing a keyboard. If unit price is `Long.MAX_VALUE` and quantity is `2`, the method throws `ArithmeticException` without printing a result. Both behaviors can be tested directly with unit tests as the project grows.

In a real program, the input source might change from a terminal to an HTTP request or a CSV file. If processing does not read input or print output itself, we can **reuse the rules** without carrying a dependency on the console. Even so, deeper class splitting and architecture are not mandatory goals for an introductory lesson: first master how data moves through each stage.

### Manual Testing Against the Contract

Test at least the following cases, writing down input/expected output before running:

| Case | Three-line input | Expected |
| --- | --- | --- |
| Normal | `But bi / 12000 / 3` | `Tong tien: 36000 VND` |
| Free item | `Qua tang / 0 / 2` | `Tong tien: 0 VND` |
| Empty name | `(blank) / 12000 / 3` | Message saying name cannot be empty |
| Invalid quantity | `But bi / 12000 / 0` | Message saying quantity must be positive |
| Not a number | `But bi / abc / 3` | Message requiring an integer |
| Numeric overflow | `But bi / 9223372036854775807 / 2` | Overflow error, no total line printed |

A useful test suite always includes **normal cases + boundary cases + error cases**, not just one screenshot showing the program printed one multiplication.

## 10. Practice Exercises

**Exercise 1 — Draw the IPO flow:** For an application that calculates the average score of three tests, identify the inputs, internal data types, processing formula, how results are displayed, and invalid inputs. If valid scores are `0..10`, at which stage do you check them?

**Exercise 2 — Add a discount:** Add an input line “Discount percentage” (integer `0..100`) and calculate the final amount. Specify the multiplication/division order and rounding method using integer arithmetic. Write out cases for 0%, 100%, 50%, and out-of-range inputs beforehand. This is a **feature extension**, no longer the original three-line version.

**Exercise 3 — Improve invalid-input feedback:** In `readPurchase`, validate the name right after reading it and the price right after parsing it so invalid input is reported earlier. Observe the change in the number of prompts while keeping the total-price formula unchanged.

**Exercise 4 — Distinguish stdout/stderr:** Supply quantity 0 via a pipe and redirect the two streams to two files. Which line is output, and which line is error? Why should an automated tool also check the exit code?

**Exercise 5 — Change the input source:** Replace the keyboard with data from a three-line text file. Use shell `<` where supported or `Files.newBufferedReader`. Point out which part of the program must change and which part can stay the same.

### Self-Assessment

You understand this lesson when you can: **(1)** describe the Input → Validation → Processing → Output path; **(2)** distinguish the `String` read as input from parsed numeric values; **(3)** state the roles of `System.in`, `System.out`, and `System.err`; **(4)** explain why invalid data or numeric overflow **must not be printed as a successful result**; and **(5)** run and diagnose the example yourself using `javac`/`java`.
