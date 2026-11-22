# Running a Single-File Program in Java

You have just written a small Java program in a `.java` file and want to see the result right away, without needing to create a `.class` directory or configure a project. Since **JDK 11**, Java has supported **source-file mode**: using the `java` command pointed directly at a source file. On **JDK 17 or higher**, you can run:

~~~bash
java QuickTotal.java 3 125000
~~~

The Java launcher will compile the source code in memory and run the program. With this approach, you **do not have to run `javac` first** and no `QuickTotal.class` file is created on disk just from that command.

This lesson explains how to use that mode, when it fits, and how it differs from the traditional compilation workflow.

## 1. Two ways to run a Java program

Suppose you have a `QuickTotal.java` file declaring the `QuickTotal` class with a `main` method.

| Approach | Command | `.class` file on disk? | When is it suitable? |
| --- | --- | --- | --- |
| **Run source directly** | `java QuickTotal.java` | Not created by a source-file mode run | Quickly trying a small source program |
| **Compile then run** | `javac QuickTotal.java` then `java QuickTotal` | Yes, after compilation | When you want control over build outputs, deployment, or larger projects |

The key point is that **the `java` command has two different interpretations**:

- `java QuickTotal.java`: the first argument is a **source file path**; the launcher uses source-file mode.
- `java QuickTotal`: the first argument is a **class name**; the JVM must find the class's bytecode via the appropriate classpath/module path.

Never replace `QuickTotal.java` with `QuickTotal.class` in the class-running command. Source file names and class names are two different concepts.

### What happens inside source-file mode?

~~~mermaid
flowchart TD
    A["QuickTotal.java"] --> B["Command java QuickTotal.java"]
    B --> C["Compile source code in memory"]
    C --> D{"Compile error in code?"}
    D -->|Yes| E["Print diagnostics and do not run main"]
    D -->|No| F["Start main in JVM"]
    F --> G["Print result or report runtime error"]
~~~

Because compilation occurs when running, syntax errors and type errors are still detected. Not creating `.class` on disk **does not mean Java skips the compilation step**.

## 2. Checking the JDK before starting

Open **PowerShell (Windows)** or **Bash (Linux)**:

~~~bash
java -version
javac -version
~~~

The output should indicate that you are using JDK 17 or higher (or a corresponding supported version). Direct source execution began to be supported in JDK 11; here we use JDK 17+ to keep the learning environment consistent.

If the terminal reports that `java` or `javac` cannot be found:

1. Verify a JDK is installed and reopen the terminal after installing or changing `PATH`.
2. **Windows PowerShell:** use `Get-Command java, javac` to see where the programs are found.
3. **Linux:** use `command -v java` and `command -v javac`.
4. When multiple JDKs coexist, ensure the `java` command is using the desired version.

Source-file mode runs from the `java` command, while having a full JDK is helpful when you want to compare with using `javac` later on.

## 3. Creating the Java file for the example

Open a practice directory of your choice in the terminal. You can create the directory with:

**PowerShell (Windows):**

~~~powershell
New-Item -ItemType Directory -Force -Path quick-java | Out-Null
Set-Location quick-java
~~~

**Bash (Linux):**

~~~bash
mkdir -p quick-java
cd quick-java
~~~

Use a text editor to create a file named exactly **`QuickTotal.java`**, saved as UTF-8 text. On Windows, check that the file did not accidentally become `QuickTotal.java.txt`.

Problem: receive **item quantity** and **unit price in integer VND** via command-line arguments; print the total amount. Quantity must be greater than 0, unit price non-negative; when multiplication overflows the `long` range, report an error instead of silently using an overflowed result.

Complete contents:

~~~java
public class QuickTotal {
    public static void main(String[] args) {
        if (args.length != 2) {
            System.out.println(
                    "Cach dung: java QuickTotal.java <soLuong> <donGiaVnd>");
            return;
        }

        try {
            int quantity = Integer.parseInt(args[0]);
            long unitPriceVnd = Long.parseLong(args[1]);

            if (quantity <= 0) {
                throw new IllegalArgumentException(
                        "So luong phai lon hon 0");
            }
            if (unitPriceVnd < 0) {
                throw new IllegalArgumentException(
                        "Don gia khong duoc am");
            }

            long totalVnd = Math.multiplyExact(
                    (long) quantity, unitPriceVnd);

            System.out.println("So luong: " + quantity);
            System.out.println("Don gia: " + unitPriceVnd + " VND");
            System.out.println("Thanh tien: " + totalVnd + " VND");
        } catch (NumberFormatException ex) {
            System.out.println("Loi: Dau vao phai la so nguyen hop le");
        } catch (IllegalArgumentException ex) {
            System.out.println("Loi: " + ex.getMessage());
        } catch (ArithmeticException ex) {
            System.out.println("Loi: Ket qua vuot mien long");
        }
    }
}
~~~

### Why does this code work?

- `public class QuickTotal` defines the class to run. The example uses a `QuickTotal.java` file matching the public class name so it can be run with **both source-file mode and traditional `javac QuickTotal.java`**. Source-file mode itself does not require the file name to match the `public` class name: the launcher runs the first top-level class in the file, so that class must have a valid `main`. With traditional compilation via `javac`, a `public` top-level class must still reside in a file of the same name.
- `main(String[] args)` is the starting point; tokens after the source file name become elements of the `args` array.
- `Integer.parseInt` reads the quantity; `Long.parseLong` reads the unit price. Both can throw `NumberFormatException` when the string is malformed or out of numeric range.
- `quantity <= 0` and `unitPriceVnd < 0` enforce the specified input rules.
- `Math.multiplyExact` returns the product as `long` and throws `ArithmeticException` if `long` overflows, avoiding silently wrong results.
- `NumberFormatException` is a subclass of `IllegalArgumentException`, so it must be caught before the general `IllegalArgumentException` branch.
- The source code uses ASCII message strings so output stays consistent across terminals with different encoding configurations.

This is a standalone source file: no external libraries, build configuration files, or second class are needed.

## 4. Running directly with `java TenTep.java`

In the directory containing `QuickTotal.java`, run:

~~~bash
java QuickTotal.java 3 125000
~~~

Expected output:

~~~text
So luong: 3
Don gia: 125000 VND
Thanh tien: 375000 VND
~~~

Explanation: `3 × 125000 = 375000`. When using source-file mode, you do not have to create `.class` files on disk and do not need to run `javac` separately.

Try running again with different inputs:

~~~bash
java QuickTotal.java 2 45000
~~~

~~~text
So luong: 2
Don gia: 45000 VND
Thanh tien: 90000 VND
~~~

If you edit `QuickTotal.java` and save the file, the next `java QuickTotal.java` call will use the **updated source code**. This is a convenient feature when practicing small programs.

### When you are in the parent directory

If saved at `quick-java/QuickTotal.java` while you are in the parent directory of `quick-java`, use:

~~~bash
java quick-java/QuickTotal.java 3 125000
~~~

Both Windows and Linux accept passing this path through the Java launcher. If the actual path contains spaces, wrap the path in double quotes:

~~~bash
java "quick-java/QuickTotal.java" 3 125000
~~~

The quotes wrap the **path**, while `3` and `125000` are two separate program arguments.

## 5. Distinguishing easily confused command forms

| Command | What happens |
| --- | --- |
| `java QuickTotal.java 3 125000` | Runs the source file directly |
| `java --source 17 QuickTotal.java 3 125000` | Runs source and requests Java 17 language level |
| `javac QuickTotal.java` | Compiles to `QuickTotal.class` in the current directory |
| `java QuickTotal 3 125000` | Runs the bytecode of class `QuickTotal` via the current classpath |
| `java QuickTotal.class` | Not a valid class invocation; the launcher does not take a `.class` file name as a class name |
| `javac -d out QuickTotal.java` | Places `QuickTotal.class` in the `out` directory (requires an existing destination directory) |
| `java -cp out QuickTotal 3 125000` | Runs the compiled class from the `out` directory |

The `--source 17` option is useful when you want to request a specific language mode. If the JDK in use supports Java 17, the following example is also valid:

~~~bash
java --source 17 QuickTotal.java 3 125000
~~~

Do not confuse `--source 17` with `javac --release 17`. `javac --release` is for compiling bytecode targeting a supported Java version and that release's platform APIs; source-file mode in this lesson uses the `java` launcher for direct execution.

## 6. Testing invalid inputs and edge cases

Try each command; when data is invalid, the program prints the error message written in code:

| Command | Result / point to check |
| --- | --- |
| `java QuickTotal.java 1 0` | Total 0 VND |
| `java QuickTotal.java 2 100` | Total 200 VND |
| `java QuickTotal.java 0 100` | Reports quantity must be greater than 0 |
| `java QuickTotal.java -2 100` | Reports invalid quantity |
| `java QuickTotal.java 2 -1` | Reports unit price cannot be negative |
| `java QuickTotal.java abc 100` | Reports input is not a valid integer |
| `java QuickTotal.java 2 10.5` | Reports error because this version requires integer VND |
| `java QuickTotal.java 3` | Prints usage instructions due to missing argument |
| `java QuickTotal.java 2 9223372036854775807` | Reports result exceeds `long` range |
| `java QuickTotal.java 2147483648 1` | Reports quantity exceeds `int` range error |

**Two important boundary points:**

1. `quantity = 1` is accepted whereas `quantity = 0` is rejected — because the problem requires greater than 0.
2. The true product of multiplication can exceed the `long` range even when each input parses successfully. Type checking does not eliminate the need to detect overflow at runtime.

`javac` or the in-memory compilation step checks syntax and types, yet **cannot decide on its own** whether a quantity of 0 is valid; that is a rule you write in your program.

## 7. Common errors with direct execution mode

### Error 1: Source file not found or unreadable

If you run `java QuickTotal.java ...` and the path does not point to an existing, readable source file, the launcher fails **before executing `main`**. The message depends on the JDK and how the launcher parses arguments; do not copy a sample error about `main` and assume the file was missing.

Check in order:

- What is the current working directory? Is `QuickTotal.java` actually there?
- If the file is in a subdirectory, did you pass the right path (e.g., `java quick-java/QuickTotal.java 3 125000`)?
- Was it accidentally saved as `QuickTotal.java.txt`, with wrong path casing, or lacking read permissions?
- If the source is found yet the launcher reports **no `main`**, check the `main` signature of the **first top-level class** in the file. That is a program entry point error, **not proof that the source file does not exist**.

**PowerShell:** `Get-Location` and `Get-ChildItem`. **Linux:** `pwd` and `ls`.

### Error 2: Running class name instead of source file

~~~bash
java QuickTotal
~~~

The command above asks to find a **compiled class**. If you only have `QuickTotal.java`, the JVM may report that the class cannot be found. To run source directly, use:

~~~bash
java QuickTotal.java
~~~

Running with fewer than two arguments still compiles and enters `main`, though the example prints the usage line. That differs from a compiler error.

### Error 3: Syntax or type error in source

If you accidentally edit:

~~~java
int quantity = "ba"; // Invalid: String cannot be assigned directly to int.
~~~

Source-file mode still performs the compilation step and reports the error. **`main` is not executed**, because the code is not valid yet. After fixing `int quantity = 3;`, you can re-run `java QuickTotal.java ...` right away.

### Error 4: Older JVM or mismatched tool versions

JDK 8 does not support running `java File.java`. In that case you need to upgrade to a supported version (this lesson selects JDK 17+), or use `javac` and then run `java TenLop` via the traditional workflow.

Check `java -version` if you encounter source-file mode errors.

## 8. When should you use source-file mode?

**Use it** when:

- Practicing the Java language with a single small file.
- Writing algorithm examples, testing standard libraries, or quickly validating a hypothesis.
- Wanting to edit and re-run without managing build output files.

**Consider switching to traditional compilation/build** when:

- The program has multiple source files and dependencies that need clear management.
- You want control over packaging, automated testing, or bytecode version for deployment.
- Repeatable builds in CI, JAR integration, or tools like Maven/Gradle are needed.
- You want to reuse already compiled `.class` files instead of processing source files on every run.

Source-file mode can work with classes/dependencies already on the classpath and has detailed rules when a source file contains multiple classes. However, this lab uses only **a single self-contained source file** to avoid extra configuration.

## 9. Short exercises

**Exercise 1.** Run `java QuickTotal.java 4 75000`. Predict the total amount output before running.

*Answer:* `300000 VND`.

**Exercise 2.** Change the print string `"Thanh tien:"` to `"Tong tien:"`, save the file, and run source directly. Do you need to run `javac` separately?

*Answer:* No. When executing `java QuickTotal.java`, the launcher uses the saved source code.

**Exercise 3.** Test `java QuickTotal.java 0 1`, `java QuickTotal.java 1 -1`, and `java QuickTotal.java one 1` in turn. Identify which case fails when **converting string to number**, and which are rejected due to **problem rules**.

*Answer:* `one` cannot be parsed; 0 and −1 parse successfully but are rejected by business rules.

**Exercise 4.** Compile traditionally with `javac QuickTotal.java`, then run `java QuickTotal 3 125000`. Explain why the `java` command this time **does not have `.java`**.

*Answer:* The JVM is looking up the class name from bytecode generated on disk by `javac`, rather than running a source file directly.

### Completion checklist

- [ ] `java -version` shows a version supporting source-file mode (lesson uses JDK 17+).
- [ ] Have `QuickTotal.java` with the exact name and directory.
- [ ] Can run `java QuickTotal.java 3 125000` and get `375000 VND`.
- [ ] Edited and re-ran source code yourself without a separate `javac` command.
- [ ] Distinguished compile errors from runtime data errors.
- [ ] Know when to switch to `javac` / classpath / build tools.

## Remember

**`java TenTep.java` runs source code directly by compiling in memory and then executing**, suitable for learning and quickly testing a small Java program. **`javac TenTep.java` followed by `java TenLop`** is the workflow for generating and running bytecode on disk. Learning both methods properly helps you know whether you are running a **source file** or a **compiled class**, and handle errors more accurately.
