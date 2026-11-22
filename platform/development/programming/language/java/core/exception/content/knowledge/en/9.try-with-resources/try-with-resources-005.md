# Left-to-Right Resource Creation Order in try-with-resources

> Java Core – Exception · Group: Try-with-resources · Java 17+.

## 1. Rules and Lesson Scope

When a `try-with-resources` statement declares multiple resources, Java **evaluates initializers from left to right**, and only then executes the `try` body. When leaving the body, Java **closes the successfully initialized resources in right-to-left order**. This rule still applies when the try body throws an exception or when a subsequent initializer fails.

~~~java
try (Resource a = createA();
     Resource b = createB();
     Resource c = createC()) {
    useResources();
}
~~~

This is illustrative code; you need to define a `Resource` type implementing `AutoCloseable` and the corresponding methods. If there are no errors, the sequence is:

~~~text
createA() → createB() → createC() → useResources()
                                → c.close() → b.close() → a.close()
~~~

If `createB()` throws an error: A is closed, C **is not initialized**, the try body **does not run**, and the outer catch receives the exception after the cleanup step. Do not confuse “initializer B has started” with “B has been successfully initialized and registered to be closed”.

## 2. How to Read a Resource Specification

~~~java
try (TypeA a = openA();
     TypeB b = openB()) {
    process(a, b);
} catch (IOException ex) {
    handle(ex);
}
~~~

This snippet only illustrates the structure and is not standalone. Key conditions:

- Resource variables must have a type compatible with `AutoCloseable`. Standard library examples: `InputStream`, `BufferedReader`, `java.sql.Connection`.
- The `;` character separates resource declarations. The trailing semicolon before the closing parenthesis is optional.
- Initializer A must complete **normally** before initializer B is evaluated.
- If initializer B fails, resource A that was already successfully initialized is still closed automatically; B is not closed if it was not successfully created/acquired.
- Resource declarations are `final` variables and cannot be reassigned in the body.
- Non-null resources are closed **in reverse order of the header**; null resources are skipped during automatic closing.
- When one close call throws an error, Java still attempts to close the remaining resources according to language rules.
- This mechanism has existed since **Java 7**. Writing `try (existingVariable)` with a previously declared final/effectively final variable is supported from **Java 9**.

An initializer does not necessarily contain `new`; it can be a factory call, opening a file, or combining multiple operations. What Java guarantees is **the evaluation order of expressions**. Side effects that already occurred in a factory are not automatically rolled back if the final factory throws an exception.

## 3. Complete, Runnable Java 17 Example

Create the file **`ResourceOrderDemo.java`**. The `TracedResource` class implements `AutoCloseable`, logs each open/close call, and throws simulated exceptions based on configuration.

~~~java
import java.io.IOException;

public class ResourceOrderDemo {
    private static final class TracedResource implements AutoCloseable {
        private final String name;
        private final boolean failClose;

        TracedResource(String name, boolean failOpen, boolean failClose)
                throws IOException {
            System.out.println("open " + name);
            if (failOpen) {
                throw new IOException("open " + name + " failed");
            }
            this.name = name;
            this.failClose = failClose;
        }

        @Override
        public void close() throws IOException {
            System.out.println("close " + name);
            if (failClose) {
                throw new IOException("close " + name + " failed");
            }
        }
    }

    private static TracedResource open(
            String name, boolean failOpen, boolean failClose)
            throws IOException {
        return new TracedResource(name, failOpen, failClose);
    }

    private static void report(IOException ex) {
        System.out.println("caught=" + ex.getMessage());
        for (Throwable suppressed : ex.getSuppressed()) {
            System.out.println("suppressed=" + suppressed.getMessage());
        }
    }

    private static void normal() {
        System.out.println("== normal ==");
        try (TracedResource a = open("A", false, false);
             TracedResource b = open("B", false, false);
             TracedResource c = open("C", false, false)) {
            System.out.println("body");
        } catch (IOException ex) {
            report(ex);
        }
    }

    private static void failedSecond() {
        System.out.println("== failed second ==");
        try (TracedResource a = open("A", false, false);
             TracedResource b = open("B", true, false);
             TracedResource c = open("C", false, false)) {
            System.out.println("body");
        } catch (IOException ex) {
            report(ex);
        }
    }

    private static void failedThirdAndClose() {
        System.out.println("== failed third + close ==");
        try (TracedResource a = open("A", false, true);
             TracedResource b = open("B", false, true);
             TracedResource c = open("C", true, false)) {
            System.out.println("body");
        } catch (IOException ex) {
            report(ex);
        }
    }

    private static void failedBodyAndClose() {
        System.out.println("== failed body + close ==");
        try (TracedResource a = open("A", false, true);
             TracedResource b = open("B", false, true)) {
            System.out.println("body");
            throw new IOException("body failed");
        } catch (IOException ex) {
            report(ex);
        }
    }

    private static void failedCloseOnly() {
        System.out.println("== failed close only ==");
        try (TracedResource a = open("A", false, true);
             TracedResource b = open("B", false, true)) {
            System.out.println("body");
        } catch (IOException ex) {
            report(ex);
        }
    }

    private static void nullResource() {
        System.out.println("== null resource ==");
        try (TracedResource a = null;
             TracedResource b = open("B", false, false)) {
            System.out.println("body");
        } catch (IOException ex) {
            report(ex);
        }
    }

    private static void referenceJava9() {
        System.out.println("== variable reference (Java 9+) ==");
        try {
            final TracedResource resource = open("X", false, false);
            try (resource) {
                System.out.println("body");
            }
        } catch (IOException ex) {
            report(ex);
        }
    }

    public static void main(String[] args) {
        normal();
        failedSecond();
        failedThirdAndClose();
        failedBodyAndClose();
        failedCloseOnly();
        nullResource();
        referenceJava9();
    }
}
~~~

Compile and run from the directory containing the file:

~~~bash
javac --release 17 -encoding UTF-8 ResourceOrderDemo.java
java ResourceOrderDemo
~~~

**Exact stdout** verified by running the actual compiled Java program:

~~~text
== normal ==
open A
open B
open C
body
close C
close B
close A
== failed second ==
open A
open B
close A
caught=open B failed
== failed third + close ==
open A
open B
open C
close B
close A
caught=open C failed
suppressed=close B failed
suppressed=close A failed
== failed body + close ==
open A
open B
body
close B
close A
caught=body failed
suppressed=close B failed
suppressed=close A failed
== failed close only ==
open A
open B
body
close B
close A
caught=close B failed
suppressed=close A failed
== null resource ==
open B
body
close B
== variable reference (Java 9+) ==
open X
body
close X
~~~

The sample exceptions have messages generated by the program, so the output does not depend on the OS locale. The entire program compiles with `--release 17` and requires no external libraries.

## 4. Case-by-Case Analysis

### 4.1. Success with Three Resources

The `normal()` branch prints `open A`, `open B`, `open C` in order; only then does the body print `body`. After the body, Java calls `c.close()`, `b.close()`, `a.close()`. If the three resources have a dependency relationship—such as A being the underlying source, B wrapping A, and C wrapping B—the reverse closing order ensures dependent layers are released before the underlying layer.

### 4.2. B Fails During Initialization

In `failedSecond()`, A succeeds; B's constructor prints `open B` and then throws `IOException("open B failed")`. Therefore:

1. C **is not initialized**, because B's initializer did not complete normally.
2. The body **is not entered**, because the entire resource list has not succeeded.
3. B has not been registered as a successfully initialized resource, so try-with-resources **does not call B.close()**.
4. Java automatically calls `a.close()`, printing `close A`.
5. After cleaning up A, catch prints `caught=open B failed`.

This demonstrates that try-with-resources manages successfully initialized resources **even when the try body never starts**.

### 4.3. C Fails to Open, B and A Fail to Close

In `failedThirdAndClose()`, A and B open successfully, while C starts and then fails. Both `B.close()` and `A.close()` throw errors, yet Java still attempts to close them in the order **B then A**. The primary exception is the failure to open C. The two close errors are added to the primary exception's `getSuppressed()`:

~~~text
Primary:    open C failed
Suppressed: close B failed
Suppressed: close A failed
~~~

There is no `close C` because C was never successfully initialized. The catch block executes **after the cleanup step**.

### 4.4. Body Throws an Error

In `failedBodyAndClose()`, both A and B open successfully; the body prints `body` and then throws `IOException("body failed")`. B and A are closed in reverse order; the close errors become suppressed exceptions on **the body's error**. Unlike case 4.3, the body actually started, but the closing rules remain the same.

### 4.5. Only Close Fails

In `failedCloseOnly()`, the body succeeds. `B.close()` runs first and throws an error; `A.close()` continues to run and also throws an error. **B's error is primary** because it is the first close error; A's error is suppressed. Succeeding in the body does not guarantee the entire try-with-resources succeeds, because closing can also fail.

### 4.6. Null Resource

In `nullResource()`, A has the value null, and B opens normally. Java **does not call close on null**; B is still closed. This is a rule of the automatic closing mechanism and does not mean dereferencing A in the body is safe: invoking a method on A can throw `NullPointerException`.

### 4.7. Resource Reference Since Java 9

In `referenceJava9()`, the `resource` variable is created before the header, and then `try (resource)` is used. Java 9 allows an existing final or effectively final variable to be used as a resource in the header. The resource is closed after the body, but **the creation of X happens before the try**; if opening X fails, the `try (resource)` header has not yet started.

## 5. Cleanup Boundaries When an Initializer Fails

It is important to distinguish between **starting initialization** and **being successfully registered**. A factory might open an intermediate socket or file and then throw an exception before returning the final resource. The caller's try-with-resources does not automatically know about those intermediate resources; **the factory must clean them up before exiting with an error**.

Non-standalone illustrative example:

~~~java
static Wrapper create() throws IOException {
    InputStream stream = Files.newInputStream(path);
    return buildWrapper(stream);
}
~~~

If `buildWrapper(stream)` fails, the stream has already been opened, yet the caller has not received a Wrapper. The code above must be fixed to protect the stream if creating the wrapper fails; `Wrapper`, `path`, and `buildWrapper` are also undefined in this example.

Conversely, if A is declared as the first resource of the try block and B is created from A and fails, A is already managed and will be closed. Designing **ownership** and declaration order makes a major difference.

## 6. Suppressed Exceptions and Primary Exception

Try-with-resources preserves the more important exception using the suppressed mechanism:

| Case | Primary | Suppressed |
| --- | --- | --- |
| Initializer C fails; A/B close normally | C's error | None |
| Initializer C fails; B/A close fails | C's error | B's error then A's error |
| Body fails; B/A close fails | Body's error | B's error then A's error |
| Body normal; B/A close fails | `B.close()`'s error | `A.close()`'s error |
| All operations normal | None | None |

To diagnose inside an appropriate catch block:

~~~java
catch (IOException ex) {
    System.out.println("primary=" + ex.getMessage());
    for (Throwable child : ex.getSuppressed()) {
        System.out.println("suppressed=" + child.getMessage());
    }
}
~~~

This is an illustrative snippet within an appropriate try/catch structure. `getSuppressed()` is not the same as `getCause()`: cause describes the causal chain of a wrapped exception; suppressed stores secondary exceptions thrown during cleanup.

A manual close sequence such as:

~~~java
b.close();
a.close();
~~~

can stop right at B if `B.close()` throws an exception. Try-with-resources has special semantics to **continue attempting to close the remaining resources** and preserve error details.

## 7. Catch, finally, and return

With the structure:

~~~java
try (Resource a = openA();
     Resource b = openB()) {
    process();
} catch (IOException ex) {
    handle(ex);
} finally {
    afterAll();
}
~~~

This is illustrative syntax and not standalone. Resources that have been opened are closed before the corresponding catch block runs; the outer finally block runs afterward according to its rules.

When the body contains `return expression;`, the return expression is evaluated before leaving the try block, but resources are still closed before the caller receives the result. A close error can cause the method to throw an exception instead of completing the return. Example:

~~~java
static String firstLine(Path path) throws IOException {
    try (BufferedReader reader = Files.newBufferedReader(path)) {
        return reader.readLine();
    }
}
~~~

This is an illustrative method that needs to be placed inside a class with the relevant I/O APIs imported.

## 8. Best Practices and Common Pitfalls

- **Confusing the two directions:** initializers run left→right, close runs right→left.
- **Assuming the body runs after A even if B fails:** the body only runs when all initializers succeed.
- **Assuming B is closed when B's constructor starts and throws:** B was never successfully handed off to the header, so the caller does not manage it yet.
- **Forgetting left-hand resources when a right-hand initializer fails:** Java closes them automatically.
- **Assuming A is not closed if B's close throws:** Java still attempts to close A.
- **Logging only the primary exception:** you may miss close errors stored in suppressed.
- **Confusing suppressed with cause:** these are two different exception relationships.
- **Registering both a wrapper and the underlying resource without checking the Javadoc:** the wrapper may automatically close the underlying resource, causing double closing.
- **Reassigning a resource variable:** variables in a resource declaration are final.
- **Using Java 9 resource reference syntax in a Java 8 project:** not source-compatible.
- **Assuming a null resource always throws NPE during close:** null is skipped during automatic closing.
- **Thinking try-with-resources rolls back all side effects:** it manages closing, not transactions.
- **Not checking partial initializer failure scenarios:** factories must release internal resources themselves.

Quick reasoning method: label resources A, B, C from left to right; identify the first initializer that can throw; keep the list of resources completed before it; reverse that list to determine the closing order; finally determine the primary/suppressed exceptions and the handler that receives the error.

## 9. Self-Assessment

**Question 1.** With A, B, C, if B fails to open, is C opened?

*No.* Java stops evaluating initializers to the right. A (already opened) is closed and the body does not run.

**Question 2.** If A, B, C succeed, what is the closing order?

*C → B → A.*

**Question 3.** What if C fails to open and both `B.close()` and `A.close()` fail?

*C's initialization error is primary; B's then A's close errors are suppressed.*

**Question 4.** What if the body runs normally but both `B.close()` and `A.close()` fail?

*`B.close()`'s error is primary because B closes first; `A.close()`'s error is suppressed.*

**Question 5.** What if A=null and B is valid?

*Java skips `A.close()`; B is still opened and closed according to the rules.*

**Question 6.** Why can B's constructor cause a leak when it fails even though the caller uses try-with-resources?

*B may have opened intermediate objects before returning a result to the caller; the constructor/factory must clean up those objects itself.*

**Question 7.** Which Java version does §try (existingResource)§ require?

*Direct resource reference syntax has been available since Java 9; the variable must be final/effectively final.*

## 10. References

- [JLS Java SE 17, Section 14.20.3 – try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3) – resource specification and resource management.
- [JLS Java SE 17, Section 14.20.3.1 – Basic try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3.1) – closing order and equivalent expansion mechanism.
- [JLS Java SE 17, Section 14.20.3.2 – Extended try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3.2) – outer catch/finally.
- [Java SE 17 API – AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html) – close contract.
- [Java SE 17 API – Throwable.getSuppressed](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#getSuppressed()) – suppressed exceptions.
- [Oracle Java Tutorials – try-with-resources](https://docs.oracle.com/javase/tutorial/essential/exceptions/tryResourceClose.html) – syntax examples from Java 7.

**Conclusion:** Java **evaluates initializers from left to right**, runs the body only when all initializers succeed, and then **closes successfully initialized non-null resources from right to left**. An error in a later resource does not prevent earlier resources from being closed; additional cleanup errors are stored in §getSuppressed()§.