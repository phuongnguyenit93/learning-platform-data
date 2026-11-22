# Checked Exceptions and UndeclaredThrowableException in Java Dynamic Proxies

## 1. Context and goal

In JDK Dynamic Proxies, a call to an interface method is routed to **InvocationHandler.invoke(proxy, method, args)**. The handler can call a target object, return a result, or throw an exception. The issue is that **InvocationHandler.invoke** declares **throws Throwable**, whereas the method on the interface implemented by the proxy still has its own checked exception contract.

For example, if the interface declares **String read() throws IOException**, the caller is prepared to handle **IOException**. When the handler throws an **SQLException** not covered by the contract, the JDK-generated proxy class does not pass this checked exception through as-is: it wraps it in **UndeclaredThrowableException** (UTE), an unchecked exception.

The lesson goals are:
- Understand the boundary between the interface method's **throws** clause and the invocation handler's **throws Throwable**.
- Predict when an exception passes through directly and when it gets wrapped by **UndeclaredThrowableException**.
- Distinguish the proxy wrapper from **InvocationTargetException** created by **Method.invoke** when a target throws an error.
- Write a delegating handler that forwards or translates exceptions according to the contract while preserving the root cause.

**Prerequisites:** checked/unchecked exceptions, **throw**, **throws**, interfaces, **Proxy.newProxyInstance**, **InvocationHandler**, **Method.invoke**.

## 2. Three exception groups to distinguish

**Checked exceptions** consist of subclasses of **Exception** excluding **RuntimeException** and its subclasses. Examples include **IOException**, **SQLException**, and **ClassNotFoundException**. For statically checked calls, Java requires callers to catch or declare them.

**Unchecked exceptions** are **RuntimeException** and its subclasses, or **Error** and its subclasses. Examples include **IllegalArgumentException**, **IllegalStateException**, and **AssertionError**. These exceptions do not need to appear in a **throws** clause.

**Exceptions permitted by the interface contract** are checked exceptions whose type is compatible with at least one type declared by the method in **throws**. For example:

~~~java
interface Reader {
    String read() throws java.io.IOException;
}
~~~

A **FileNotFoundException** is a subclass of **IOException**, so it is allowed through a **Reader.read()** call. **SQLException** is not compatible with **IOException** and is not allowed through as an unwrapped checked exception.

Key point to remember: **InvocationHandler.invoke** takes responsibility for dynamic handling at runtime, while **Reader.read()** is the Java contract seen by the caller. The compiler cannot know which handler will be attached to the proxy at runtime, so the JDK generates a proxy class that enforces the interface's exception propagation rules.

## 3. Exactly when does JDK Proxy throw UndeclaredThrowableException?

When **InvocationHandler.invoke** finishes by throwing an exception, the method on the proxy handles it semantically as follows:

| Throwable leaving the handler | Contract **read() throws IOException** | Result |
| --- | --- | --- |
| **IOException("disk")** | Compatible with **IOException** | Caller receives **IOException** directly |
| **FileNotFoundException("missing")** | Subclass of **IOException** | Caller receives **FileNotFoundException** directly |
| **SQLException("db")** | Not compatible with **IOException** | Proxy throws **UndeclaredThrowableException** containing **SQLException** |
| **IllegalStateException("bad")** | Unchecked | Caller receives **IllegalStateException** directly |
| **AssertionError("bad")** | **Error**, unchecked | Caller receives **AssertionError** directly |
| **InvocationTargetException** containing **IOException** | Wrapper type not compatible with **IOException** | Proxy throws **UndeclaredThrowableException** containing **InvocationTargetException** |

Call flow:

~~~text
Caller -> proxy.read() -> InvocationHandler.invoke(...)
                          |
                          +-- returns value -------------> Caller
                          +-- RuntimeException / Error --> Thrown directly
                          +-- declared checked ----------> Thrown directly
                          +-- undeclared checked --------> UndeclaredThrowableException
                                                           -> Caller
~~~

**UndeclaredThrowableException** belongs to **java.lang.reflect** and extends **RuntimeException**, so callers are not forced by the compiler to catch it. The **getUndeclaredThrowable()** API returns the exact Throwable wrapped by the proxy; **getCause()** provides the corresponding cause.

When an interface method **has no throws clause**, every checked exception leaving the handler is wrapped according to this rule. Conversely, an interface declaring **throws Exception** lets many checked exceptions pass through, though that does not mean you should declare it that way: you should design a meaningful contract for callers.

## 4. Complete Java 17+ example: four different scenarios

Save the following program in **ProxyExceptionDemo.java**. The **Reader.read()** interface declares **IOException**. The real target always throws **IOException("disk")**. The handler has four branches to show exactly which exception leaves the proxy.

~~~java
import java.io.IOException;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.lang.reflect.UndeclaredThrowableException;
import java.sql.SQLException;

public class ProxyExceptionDemo {
    public interface Reader {
        String read() throws IOException;
    }

    public static class FailingReader implements Reader {
        @Override
        public String read() throws IOException {
            throw new IOException("disk");
        }
    }

    enum Mode {
        DIRECT_CHECKED, UNDECLARED, BAD_DELEGATION, GOOD_DELEGATION
    }

    static void run(Mode mode) {
        Reader reader = (Reader) Proxy.newProxyInstance(
                ProxyExceptionDemo.class.getClassLoader(),
                new Class<?>[]{Reader.class},
                (proxy, method, args) -> {
                    if (mode == Mode.DIRECT_CHECKED) {
                        throw new IOException("disk");
                    }
                    if (mode == Mode.UNDECLARED) {
                        throw new SQLException("db");
                    }
                    if (mode == Mode.BAD_DELEGATION) {
                        // Method.invoke wraps the target error in
                        // InvocationTargetException: this is an
                        // unwrapped checked exception.
                        return method.invoke(new FailingReader(), args);
                    }

                    // GOOD_DELEGATION: rethrow the target's real error.
                    try {
                        return method.invoke(new FailingReader(), args);
                    } catch (InvocationTargetException e) {
                        throw e.getCause();
                    }
                });

        try {
            reader.read();
        } catch (IOException e) {
            System.out.println(
                    mode + ": IOException(" + e.getMessage() + ")");
        } catch (UndeclaredThrowableException e) {
            Throwable cause = e.getUndeclaredThrowable();
            if (cause instanceof InvocationTargetException ite) {
                cause = ite.getCause();
            }
            System.out.println(mode + ": UTE("
                    + cause.getClass().getSimpleName()
                    + ":" + cause.getMessage() + ")");
        }
    }

    public static void main(String[] args) {
        for (Mode mode : Mode.values()) {
            run(mode);
        }
    }
}
~~~

Compile and run in the directory containing the file with JDK 17 or later:

~~~bash
javac -encoding UTF-8 ProxyExceptionDemo.java
java ProxyExceptionDemo
~~~

Output:

~~~text
DIRECT_CHECKED: IOException(disk)
UNDECLARED: UTE(SQLException:db)
BAD_DELEGATION: UTE(IOException:disk)
GOOD_DELEGATION: IOException(disk)
~~~

**Detailed explanation:**

1. **DIRECT_CHECKED:** the handler throws **IOException** directly. Since **Reader.read()** has **throws IOException**, the proxy passes the correctly typed exception outward; **catch (IOException)** catches it.
2. **UNDECLARED:** the handler throws **SQLException**, which is incompatible with the **throws IOException** contract. The proxy creates **UndeclaredThrowableException**, with the **SQLException** object inside **getUndeclaredThrowable()**.
3. **BAD_DELEGATION:** the target throws **IOException**, but **Method.invoke** catches the target exception and throws **InvocationTargetException**. Because the handler does not unwrap it, the Throwable leaving the handler is **InvocationTargetException**, which is not covered by **throws IOException**. The proxy wraps it in another layer of UTE.
4. **GOOD_DELEGATION:** the handler catches **InvocationTargetException** and throws **getCause()**. The Throwable leaving the handler is the target's **IOException**; the proxy passes it through as-is so the caller catches it with **catch (IOException)**.

The output above was verified by running Java; the display order matches the order of values in the **Mode** enum. The example uses explicit imports for **java.lang.reflect.Proxy** and can be compiled standalone on JDK 17+.

## 5. How does InvocationTargetException differ from UndeclaredThrowableException?

| Question | **InvocationTargetException** | **UndeclaredThrowableException** |
| --- | --- | --- |
| Who creates the wrapper? | **Method.invoke** when code in the invoked method throws a Throwable | JDK-generated proxy method code when the handler throws a checked exception outside the contract |
| Checked or unchecked? | Checked, extends **ReflectiveOperationException** | Unchecked, extends **RuntimeException** |
| What does the wrapper hold? | The actual exception thrown by the target | The Throwable thrown by the invocation handler that is not validly declared by the interface |
| Getting the cause | **getCause()** or **getTargetException()** | **getUndeclaredThrowable()** or **getCause()** |
| Where to fix? | Catch and unwrap right inside the handler when delegating via Reflection | Fix the contract or how the handler raises/translates checked exceptions |

A typical chain for the **BAD_DELEGATION** branch:

~~~text
UndeclaredThrowableException
  -> InvocationTargetException
       -> IOException("disk")
~~~

Do not read only the outermost exception line and conclude the target object threw the wrong type. The target may have thrown a completely valid **IOException**; the mistake lies in the handler letting **InvocationTargetException** cross the proxy boundary.

If the target throws **IllegalArgumentException** through **Method.invoke**, Reflection still wraps the error in **InvocationTargetException**. A handler that fails to unwrap it can cause the caller to receive UTE even though **IllegalArgumentException** itself is unchecked and could have been thrown directly.

## 6. Handler pattern for properly forwarding exceptions

When a handler simply delegates from a proxy to a real object using **Method.invoke**, the basic pattern is:

~~~java
try {
    return method.invoke(target, args);
} catch (InvocationTargetException e) {
    throw e.getCause();
}
~~~

This is a **snippet used inside InvocationHandler.invoke**, assuming **target** exists and **method/args** are callback parameters. It is not a standalone program. **InvocationHandler.invoke** declares **throws Throwable**, so it can throw **e.getCause()**.

However, **unwrapping InvocationTargetException does not guarantee every checked exception is valid**. If the target throws an **SQLException** while the interface only declares **IOException**, the proxy still wraps SQLException in UTE. An error policy is needed:

- **Forward the real cause** if it is compatible with the interface's **throws** contract. No type change is needed.
- **Translate meaningfully** if a library/infrastructure exception is outside the API contract. For example, a database document-reading error can be translated into **IOException** while attaching the cause.
- **Preserve the cause** in the new exception. Do not swallow exceptions or throw a wrapper without a cause that loses diagnostic facts.
- **Adjust the contract design** if callers genuinely need to handle an additional checked exception; do not carelessly widen it to **throws Throwable** to bypass the rules.

Illustrative example translating a data-layer error into a document-reading error:

~~~java
try {
    return loadDocumentFromDatabase();
} catch (java.sql.SQLException e) {
    throw new java.io.IOException("Unable to read document", e);
}
~~~

This snippet assumes a **loadDocumentFromDatabase()** method that can throw **SQLException** and resides inside a handler for an interface method with **throws IOException**. The compiler will require a complete implementation of that method if this example is placed in a project. Do not apply this translation arbitrarily when there is no semantic link between data errors and read errors.

## 7. Edge cases

### 7.1. No checked exception declared

For an interface method **void execute()** with no **throws** declaration, a handler throwing **IOException** will result in UTE. **throws Throwable** on the handler does not change the signature of **execute()**.

### 7.2. One proxy implementing multiple interfaces with matching signatures

If multiple interfaces declare a method with the same name and same parameter list but different **throws** clauses, a checked exception leaving the handler must be compatible with the contracts of **all** interfaces to which the corresponding call could belong. Being compatible with only one interface is not enough.

For example, **A.process() throws IOException** and **B.process() throws SQLException**: when a proxy implements both **A** and **B**, a handler throwing **IOException** will be wrapped by the proxy in UTE because that type is incompatible with **B.process()**'s **throws SQLException**. This is a property of matching-signature methods, independent of whether the caller cast the proxy to **A** or **B**.

### 7.3. The equals, hashCode, and toString methods

Calls to **equals**, **hashCode**, and **toString** on a proxy are also routed through the handler. They declare no checked exceptions, so a handler throwing a checked exception for these calls also produces UTE. Make explicit decisions on how to handle these three methods in the handler if the application uses them.

### 7.4. IllegalAccessException when calling Reflection

If **Method.invoke** throws **IllegalAccessException** due to access permissions, this is a Reflection-layer checked exception, not an error thrown by the target wrapped in **InvocationTargetException**. If the handler lets it pass out directly and the interface does not declare a compatible type, the proxy wraps it in UTE. Fixing this requires examining actual access rights and Java modules; unwrapping or calling **setAccessible(true)** arbitrarily does not solve every case.

## 8. Diagnostic guide when encountering UTE

1. **Check the throws clause on the interface.** Note the method called by the caller and any interfaces with matching method signatures.
2. **Extract the throwable inside UTE.** Call **getUndeclaredThrowable()** (or **getCause()**). Do not rely on the UTE name alone.
3. **Check whether InvocationTargetException is present.** If so, inspect its **getCause()** to see the target's real error.
4. **Locate the exact code in the handler.** Which line throws a Throwable out of **InvocationHandler.invoke**? Is it a valid checked type, an out-of-contract type, or a forgotten Reflection wrapper?
5. **Fix at the right boundary.** If the target threw a declared error but the handler leaked the wrapper, unwrap it. If the target genuinely threw a checked exception outside the contract, redesign the translation or interface signature.
6. **Test both call paths.** Call the target directly to record the root cause, then call through the proxy to confirm the exception type the caller sees.

You can log the full cause chain at monitoring boundaries, but you should not routinely catch UTE across all callers as a substitute for fixing the handler.

## 9. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Assuming the handler's **throws Throwable** lets any checked exception reach the caller | UTE appears at runtime | Match exceptions against the interface's **throws** clause |
| Delegating with **return method.invoke(target, args)** without catching **InvocationTargetException** | UTE may wrap **InvocationTargetException** even when the root error is valid | Catch the wrapper and **throw e.getCause()** |
| Converting every exception to **new RuntimeException()** without passing the cause | Loses original info, makes debugging hard | Preserve the cause and choose a semantically right exception |
| Forcing every cause into **IOException** | Can cause casting errors and hide bugs | Check types and translate intentionally |
| Caller catches only declared checked exceptions and assumes all errors are handled | Unchecked UTE still escapes | Fix the handler and monitor UTE at appropriate boundaries |
| Reading only the UTE message instead of the cause chain | Misdiagnoses the error source | Use **getUndeclaredThrowable()** and **getCause()** |

## 10. Practice and self-check

**Exercise 1:** Change the interface method to **read()** without declaring **IOException** while keeping the handler throwing **IOException**. After updating the implementation so the program compiles, predict the result: the caller receives **UndeclaredThrowableException**, containing **IOException** inside.

**Exercise 2:** Have the target throw **IllegalArgumentException**. Compare a handler that only calls **Method.invoke** with one that catches **InvocationTargetException** and throws **getCause()**. The first case produces a UTE containing the wrapper; the second lets **IllegalArgumentException** escape directly.

**Exercise 3:** Have the handler throw **SQLException** when the interface only declares **IOException**. Write a translation to **IOException** with a cause, then verify the caller catches **IOException** and reads **SQLException** from **getCause()**.

**Exercise 4:** Create two interfaces both declaring **process()**, where one **throws IOException** and the other **throws SQLException**. Create a proxy implementing both and explain why throwing **IOException** directly from the handler results in UTE.

**Self-check questions:**
- Why does **InvocationHandler.invoke throws Throwable** not remove the interface's checked exception constraint?
- When UTE wraps **InvocationTargetException** wrapping **IOException**, which exception actually left the handler?
- When a target throws **RuntimeException** through **Method.invoke**, is unwrapping **InvocationTargetException** necessary?
- Why can fixing UTE by always adding **throws Exception** to the interface degrade API contract quality?

**Core answers:** The proxy preserves the interface's contract; **InvocationTargetException** is a checked wrapper created by Reflection; unwrap it to propagate the real cause; widening **throws** must serve how callers handle errors, never be used as a trick to mask design flaws.

Once you can answer the questions above and accurately predict all four output lines, you understand the relationship between checked exceptions, Reflection delegation, and JDK Dynamic Proxy's **UndeclaredThrowableException**.