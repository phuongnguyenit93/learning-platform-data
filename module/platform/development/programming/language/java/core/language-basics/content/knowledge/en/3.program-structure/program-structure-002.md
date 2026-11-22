# Role of `public static void main(String[] args)` in Java

When running a simple Java application from the terminal, the JVM needs to know **where the program starts executing**. When launching a class normally on **JDK 17**, the Java launcher looks for a method with a matching signature, typically:

~~~java
public static void main(String[] args)
~~~

The `main` method is the **entry point** of the program. The statements in the body of `main` are executed when the user runs that class with the `java` command. It is not the entire application: from `main`, you can call other methods and classes to perform work.

This lesson focuses on the signature above, how to run a class containing `main`, the role of the `args` parameter, and common beginner mistakes. The examples use **JDK 17 or later** and traditional Java 17-compatible `main` syntax.

## 1. Reading Each Part of the `main` Signature

| Component | Meaning | Why is it needed when running a class on Java 17? |
| --- | --- | --- |
| `public` | Method has public accessibility | The Java launcher needs to be able to call the entry point |
| `static` | Method belongs to the class, no object needed to call it | The launcher can invoke `main` without having to `new` its enclosing class |
| `void` | Method does not return a Java value | The traditional entry-point signature requires returning `void` |
| `main` | Entry-point method name | The launcher looks for a method with this name |
| `String[]` | Type **array of strings** | Holds arguments passed by the user when running the program |
| `args` | Parameter name of the `String[]` array | The name can be changed; `args` is simply a clear convention |

The keywords `public`, `static`, and `void` are not three decorative words: omitting or changing them incorrectly can make the method **no longer satisfy the entry-point requirements**, even though the class still compiles.

For example, a regular method can also be named `main` without necessarily being used by the Java launcher as an entry point:

~~~java
static void main(int number) {
    System.out.println(number);
}
~~~

That is a method with an `int` parameter, **not** the `main(String[] args)` signature required by the class-running examples below.

### Why is `main` `static`?

A `static` method can be called by class name without creating an instance. When starting `GreetingMain`, the launcher does not need to know how to create `new GreetingMain()`; it uses the matching `main` method to start the execution flow.

The `static` keyword here **does not mean** all application data must be `static` variables. You can still create objects, call instance methods, and organize the program into multiple classes from `main`.

## 2. A Complete Java 17+ Program

Create the file **`GreetingMain.java`** with the following content:

~~~java
public class GreetingMain {
    public static void main(String[] args) {
        if (args.length != 2) {
            System.out.println(
                    "Cach dung: java GreetingMain <ten> <soLan>");
            return;
        }

        String name = args[0];
        if (name.isBlank()) {
            System.out.println("Loi: ten khong duoc trong");
            return;
        }

        final int times;
        try {
            times = Integer.parseInt(args[1]);
        } catch (NumberFormatException ex) {
            System.out.println("Loi: soLan phai la so nguyen");
            return;
        }

        if (times < 1 || times > 5) {
            System.out.println("Loi: soLan phai tu 1 den 5");
            return;
        }

        for (int i = 1; i <= times; i++) {
            System.out.println(
                    "Lan " + i + ": Xin chao, " + name + "!");
        }
    }
}
~~~

This example intentionally has only **one public class** containing one entry point.

- `public class GreetingMain`: the class name must match the filename `GreetingMain.java`.
- `main`: receives two arguments, validates data, and decides what to do.
- `args.length`: the number of **argument strings**, excluding the word `java` or the class name.
- `args[0]`: name of the person to greet; `args[1]`: text to parse into the repetition count.
- `Integer.parseInt(args[1])`: parses an integer string; inputs such as `abc` or numbers outside the `int` range throw `NumberFormatException`.
- `return;`: terminates the current `main` call without returning a value because `main` has type `void`.
- The `for` loop prints the exact number of times after the data is confirmed to be in the range 1–5.

Having the **right** method signature is not enough for the program to be functionally correct. Checking the argument count, blank name, and valid repetition count is the responsibility of the code inside `main`.

## 3. Compiling and Running via Terminal

Open PowerShell on Windows or Bash on Linux and go to the directory containing `GreetingMain.java`.

### Check the tools

~~~bash
java -version
javac -version
~~~

Use JDK 17 or later that includes `java` and `javac`. Create a separate directory for bytecode:

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force -Path out | Out-Null
~~~

**Linux/Bash:**

~~~bash
mkdir -p out
~~~

Then, on **both operating systems**:

~~~bash
javac -encoding UTF-8 -d out GreetingMain.java
java -cp out GreetingMain Mai 3
~~~

**Output:**

~~~text
Lan 1: Xin chao, Mai!
Lan 2: Xin chao, Mai!
Lan 3: Xin chao, Mai!
~~~

`javac` creates `out/GreetingMain.class` when the code is valid; `-d out` specifies outputting into that directory. The command `java -cp out GreetingMain Mai 3` uses the Java launcher to find the `GreetingMain` class in the `out` classpath and invoke the corresponding `main` method.

With the command above, the launcher passes into `main`:

~~~text
args.length == 2
args[0] == "Mai"
args[1] == "3"
~~~

That means **`args[1]` is still a `String`** `"3"`, even though it looks like a number when typed in the command. Only when calling `Integer.parseInt` does the program obtain the `int` value 3.

### A name containing spaces is still one argument

~~~bash
java -cp out GreetingMain "Lan Anh" 2
~~~

~~~text
Lan 1: Xin chao, Lan Anh!
Lan 2: Xin chao, Lan Anh!
~~~

PowerShell and Bash both interpret double quotes here to keep `Lan Anh` as **one argument**. If you omit the quotes, the shell usually splits it into two arguments `Lan` and `Anh`, changing `args.length`.

## 4. How Execution Flow Passes Through `main`

~~~mermaid
flowchart TD
    A["java -cp out GreetingMain Mai 3"] --> B["Java launcher locates GreetingMain"]
    B --> C["Find matching main(String[] args)"]
    C --> D["Call main with 2 string arguments"]
    D --> E{"Data valid?"}
    E -->|No| F["Print error or usage, return"]
    E -->|Yes| G["Run for loop, print greetings"]
    G --> H["End main call"]
~~~

Larger applications still use `main` as the place to **start up and wire components together**; you should not cram all calculations and I/O operations into one very long method just because `main` is the entry point.

`main` is normally called at the start of the main thread in class-launching examples, but it is **not necessarily the only method executed**. It can call other methods. If the program spawns additional active threads, `main` returning **does not automatically guarantee the JVM stops immediately**.

## 5. What `args` Is and What It Is Not

### `args` is only the parameter variable name

The following two signatures both describe a `String[]` parameter:

~~~java
public static void main(String[] args)
~~~

~~~java
public static void main(String[] arguments)
~~~

The name `args` is widely used, but it is **not a keyword**. If you rename it to `arguments`, you must update its uses inside the method.

Java also accepts variable-arity parameter syntax (*varargs*) for the string type:

~~~java
public static void main(String... args)
~~~

Inside, `args` can still be used like a `String[]` array. For beginners, writing `String[] args` is usually clearer.

### Initial value of `args`

When launched normally through the Java launcher, the program receives an array containing the arguments after the class name. Providing no arguments means the array has **length 0**:

~~~bash
java -cp out GreetingMain
~~~

Output from the example program:

~~~text
Cach dung: java GreetingMain <ten> <soLan>
~~~

**Do not read `args[0]` before checking `args.length`.** If the array has no elements, accessing index 0 throws `ArrayIndexOutOfBoundsException` at runtime.

A Java method can be called manually in other code via `GreetingMain.main(null)`, which is different from normal startup. Therefore, you should not assume every direct call to `main` automatically has a non-null valid array.

## 6. Distinguishing Entry-Point Signature Errors from Data Errors Inside `main`

| Issue | Compiles with `javac`? | When running `java`? |
| --- | --- | --- |
| `public static void main(String[] args)` | Valid | Launcher uses it as the entry point |
| Only `public void main(String[] args)` | Class still compiles | On Java 17, not a valid entry point because `static` is missing |
| Only `private static void main(String[] args)` | Class still compiles | On Java 17, not a valid entry point because it is not `public` |
| Only `public static int main(String[] args)` | Compiles as an ordinary method | Does not match the `void` return type of a Java 17 entry point |
| Only `public static void main(int[] args)` | Compiles as an ordinary method | Does not match the `String` array parameter |
| `args[0]` when no arguments are given | Still compiles | Can throw `ArrayIndexOutOfBoundsException` |
| `Integer.parseInt("abc")` | Type-valid | Throws `NumberFormatException` at runtime |

**Important:** `javac` does not require **every class** to have `main`. A library class or data class can compile normally without being directly runnable via `java ClassName` in the standard way.

Messages from the Java launcher can vary across JDK versions, but the principle holds: **valid compilation** and **having a valid entry point to run a class** are two different checks.

A valid signature specifies **how to start**, without checking the count or numeric format of arguments: input strings still need to be parsed inside the application.

## 7. Cases to Try with the Sample Program

| Command after compiling | Expected result to verify |
| --- | --- |
| `java -cp out GreetingMain Mai 1` | Prints one greeting |
| `java -cp out GreetingMain Mai 5` | Prints five greetings |
| `java -cp out GreetingMain Mai 0` | `Loi: soLan phai tu 1 den 5` |
| `java -cp out GreetingMain Mai 6` | `Loi: soLan phai tu 1 den 5` |
| `java -cp out GreetingMain Mai abc` | `Loi: soLan phai la so nguyen` |
| `java -cp out GreetingMain Mai 2147483648` | `Loi: soLan phai la so nguyen` because it is outside the `int` range |
| `java -cp out GreetingMain Mai` | Prints usage message because an argument is missing |
| `java -cp out GreetingMain "Lan Anh" 2` | Two greetings with the exact name containing a space |
| `java -cp out GreetingMain "" 2` | `Loi: ten khong duoc trong` |

Another scenario: if `" 2 "` is passed as the repetition count string, `Integer.parseInt` does not automatically strip whitespace. When whitespace should be accepted, the application must have explicit handling rules such as `trim()`. Do not patch code just to pass a single test case without deciding the expected input behavior.

### Why is `return;` not the same as `System.exit(...)`?

In the example code, `return;` only **terminates the `main` method**. In a simple single-threaded program, no other tasks remain, so the program usually finishes right after.

In contrast, `System.exit(2)` requests the JVM to terminate the process with status code 2; this is often useful for CLI tools or automation systems that need to distinguish success from failure. It affects the **entire process**, so it is unnecessary when the lesson is only introducing the basic role of `main`.

Because the current example prints an error and executes `return;`, it **does not automatically set a non-zero exit code**. Do not assume that printing the word `Loi` causes the shell to see the process as failed.

## 8. Self-Practice Exercises

**Exercise 1 — Explain the signature.** Without looking at the table, state one sentence for each of `public`, `static`, `void`, `main`, `String[]`, and `args`.

**Exercise 2 — Predict the output.** Run `java -cp out GreetingMain "Minh Chau" 2`. How many elements are in `args`? What do the two elements contain, and how many lines are printed?

*Answer:* Two elements, `"Minh Chau"` and `"2"`; two greetings.

**Exercise 3 — Spot the entry-point error.** Try changing `public static void main(String[] args)` to `public void main(String[] args)`. Why might `javac` report no error while `java -cp out GreetingMain Mai 2` fails to run as intended on Java 17?

*Answer:* You created an instance method, leaving no `public static` `main` method with the exact signature the Java 17 launcher looks for.

**Exercise 4 — Input handling.** Modify the code to accept repetition counts from 1 to 10, then test the valid boundary case 10 and invalid case 11. Confirm that you only changed the count validation rule without changing the meaning of `main`.

**Exercise 5 — Extract work out of `main`.** Add the following method **inside the `GreetingMain` class**:

~~~java
static void greet(String name, int sequence) {
    System.out.println(
            "Lan " + sequence + ": Xin chao, " + name + "!");
}
~~~

Then replace the `println` statement inside the `for` loop with `greet(name, i);`. Does the output change? Explain why this is a good code-organization step even though `main` remains the entry point.

## Checklist

- [ ] Know that `main` is the entry point when the Java launcher runs a class in the traditional way on JDK 17.
- [ ] Explain `public`, `static`, `void`, `main`, `String[]`, and `args`.
- [ ] Create a properly named file containing a `public class` and compile it with `javac`.
- [ ] Run `java -cp out GreetingMain Mai 3` and predict its output.
- [ ] Know that CLI arguments are initially all `String` values and the class name is not in `args[]`.
- [ ] Check `args.length` before accessing elements.
- [ ] Distinguish missing entry-point errors from data errors inside the `main` method.
- [ ] Understand that `main` finishing does not always force all threads/the JVM to stop immediately.

**Summary:** `public static void main(String[] args)` is the familiar starting-point declaration of a Java 17 application. The Java launcher uses this signature to invoke your code, while the program uses `args` to receive input strings. Understanding that boundary helps you build runnable programs, diagnose errors in the right place, and organize logic outside `main` as applications grow.
