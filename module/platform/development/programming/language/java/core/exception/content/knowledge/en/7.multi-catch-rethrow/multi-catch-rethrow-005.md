# Member Access Restrictions Through Multi-Catch Parameters in Java

## 1. Learning Objectives

Multi-catch lets you handle multiple exception types in **one** `catch` block:

```java
try {
    performOperation();
} catch (java.io.IOException | java.sql.SQLException failure) {
    System.out.println(failure.getMessage());
}
```

This is an illustrative snippet inside a method; `performOperation()` must be defined and capable of throwing the caught checked exception types. The key point: even though at runtime `failure` is an `IOException` **or** `SQLException` object, the compiler does not automatically allow every type-specific method of both classes on the same `failure` variable.

After this lesson, you will be able to:

- Understand that the type of the exception parameter in `catch (A | B e)` is determined by the **least upper bound** (the closest common upper bound under Java's type system rules).
- Distinguish between the **actual runtime type of the object** and the **compile-time static type of the expression `e`**.
- Identify members directly accessible through `e`, branch-specific members, and access modifier rules.
- Use `instanceof` or pattern matching for `instanceof` in Java 17 to access type-specific APIs after checking the type.
- Understand why a multi-catch parameter cannot be reassigned and how rethrowing preserves exception information.
- Recognize common errors involving parent–child exception types in multi-catch, overloaded methods, and checked exceptions.
- Write compilable Java 17+ programs with deterministic observable output.

The focus of this lesson is **the restriction on members accessible through a multi-catch parameter**. Related rules on rethrowing, checked exceptions, and variable scope are presented to explain the mechanism completely.

## 2. How Does Multi-Catch Differ From Separate `catch` Blocks?

Writing two handlers with the same logic:

```java
try {
    readOrQuery();
} catch (java.io.IOException failure) {
    System.out.println(failure.getMessage());
} catch (java.sql.SQLException failure) {
    System.out.println(failure.getMessage());
}
```

Can be combined into:

```java
try {
    readOrQuery();
} catch (java.io.IOException | java.sql.SQLException failure) {
    System.out.println(failure.getMessage());
}
```

Both are **illustrative snippets**, requiring an appropriate `readOrQuery()`. The `|` here is **multi-catch** syntax (Java 7+), not a logical OR operator on variables, and it does not create a general-purpose union type usable everywhere in Java.

In the first approach, each handler has a parameter with a specific type: `IOException` or `SQLException`. In the second approach, **there is only one `failure` variable** in the handler body. That variable must be safe to use for every type the handler can receive.

### You Cannot Infer That "Same Variable Name" Means "Same Specific Type"

Both `IOException` and `SQLException` extend `Exception`, but they have their own methods:

- `SQLException.getSQLState()` returns the SQLSTATE code, if available.
- `SQLException.getErrorCode()` returns the vendor-specific error code.
- `SQLException.getNextException()` follows the chain of SQL exceptions.
- `IOException` does not declare `getSQLState()`, `getErrorCode()`, or `getNextException()`.

Therefore, `failure.getMessage()` is valid in multi-catch because `getMessage()` belongs to `Throwable`, whereas `failure.getSQLState()` is invalid without narrowing the type first.

## 3. Static Type of a Multi-Catch Parameter

With the syntax:

```java
catch (TypeA | TypeB | TypeC ex) {
    // The compiler must determine the type of ex.
}
```

Java determines the parameter's type using the **least upper bound** — often written `lub(TypeA, TypeB, TypeC)`. The idea is to find a common type bound sufficient to safely represent all the exception alternatives.

In the example:

```java
catch (java.io.IOException | java.sql.SQLException ex) {
    System.out.println(ex.getClass().getSimpleName());
    System.out.println(ex.getMessage());
    System.out.println(ex.getCause());
}
```

The parameter `ex` can point to an object of any of the alternatives at runtime. The methods above are valid because they are all members of `Object` or `Throwable` in the shared hierarchy.

**Note on precision:** `lub` in Java can be an *intersection type* consisting of a common class and matching interfaces. Thus, you should not claim that **every** multi-catch has `Exception` as its exact static type. For member calls, check whether the member exists in the static type inferred by the compiler and is **accessible** at the call site.

A helpful mental model:

```text
IOException -----\
                   > catch parameter ex
SQLException ----/   |
                       v
          valid members from the common type bound
          (e.g., getMessage(), getCause(), printStackTrace())
```

**It is NOT:** the compiler accepting every member of `IOException` **plus** every member of `SQLException`. That would be unsafe because at runtime the object can only belong to one branch.

### 3.1. The Runtime Type Is Preserved

Even though the expression `ex` has a common static type, the object it references **is not converted** into a new `Exception` object. If a method throws `SQLException`, the actual object is still `SQLException`. Information such as the object's message, cause, SQL state, and stack trace is not lost.

Access to type-specific methods is restricted by **compile-time type checking**. You can access them after proving the actual type, as shown in the `instanceof` example below.

### 3.2. A Common Type Does Not Mean Only `Object` Methods

If the alternatives extend the same **intermediate exception class** that defines application methods, the common type can allow access to those methods.

For example:

```text
Exception
    └── AppFailure (method: code())
        ├── NetworkFailure
        └── ValidationFailure
```

In `catch (NetworkFailure | ValidationFailure e)`, a public `code()` method declared on `AppFailure` can be called directly via `e.code()`. We will verify this with a standalone program in Section 6.

## 4. Runnable Example: Common Members and Type-Specific Methods

Create the file **`MultiCatchAccessDemo.java`**:

```java
import java.io.IOException;
import java.sql.SQLException;

public class MultiCatchAccessDemo {
    private static void execute(String mode)
            throws IOException, SQLException {
        if ("io".equals(mode)) {
            throw new IOException("disk unavailable");
        }
        if ("sql".equals(mode)) {
            throw new SQLException("connection refused", "08006");
        }
    }

    private static void run(String mode) {
        try {
            execute(mode);
            System.out.println(mode + ": success");
        } catch (IOException | SQLException failure) {
            System.out.println(failure.getClass().getSimpleName()
                    + ": " + failure.getMessage());

            if (failure instanceof SQLException sqlFailure) {
                System.out.println("SQLSTATE=" + sqlFailure.getSQLState());
            }
        }
    }

    public static void main(String[] args) {
        run("io");
        run("sql");
        run("ok");
    }
}
```

Compile/run commands with JDK 17+:

```bash
javac MultiCatchAccessDemo.java
java MultiCatchAccessDemo
```

`stdout` output:

```text
IOException: disk unavailable
SQLException: connection refused
SQLSTATE=08006
ok: success
```

Line-by-line explanation:

1. `run("io")` receives an `IOException`; `getClass()` and `getMessage()` are valid through the multi-catch parameter because they belong to the common API.
2. `failure instanceof SQLException sqlFailure` is `false`, so SQLSTATE is not printed.
3. `run("sql")` receives an `SQLException`; the object still retains the `SQLState` data passed at construction.
4. The pattern `instanceof SQLException sqlFailure` checks the runtime type and creates the `sqlFailure` variable with the specific static type `SQLException` in the true branch, making `sqlFailure.getSQLState()` valid.
5. `run("ok")` throws no exception and follows the success path.

The `instanceof` form with a binding variable (`pattern matching for instanceof`) is a standard feature in Java 17, requiring no preview flags.

## 5. Non-Compiling Example: Accessing a Type-Specific Method Directly

The following snippet has an intentional error:

```java
import java.io.IOException;
import java.sql.SQLException;

public class InvalidMultiCatchMember {
    static void fail(boolean sql) throws IOException, SQLException {
        if (sql) {
            throw new SQLException("db error", "42000");
        }
        throw new IOException("IO error");
    }

    public static void main(String[] args) {
        try {
            fail(true);
        } catch (IOException | SQLException failure) {
            System.out.println(failure.getSQLState()); // COMPILE ERROR
        }
    }
}
```

If saved as `InvalidMultiCatchMember.java` and compiled:

```bash
javac InvalidMultiCatchMember.java
```

The compiler will report that it cannot find a matching `getSQLState()` method on the static type of the `failure` expression. The exact diagnostic text may vary by JDK version; **do not run `java InvalidMultiCatchMember`** because this example intentionally fails to compile.

**Why doesn't `fail(true)` help?** The compiler checks the `catch` body against the **declared type of the parameter**, rather than inferring from the `true` argument of one call to turn `failure` into `SQLException`. Moreover, the signature of `fail` is capable of propagating two checked exception types.

Fix it with a type check:

```java
if (failure instanceof SQLException sqlFailure) {
    System.out.println(sqlFailure.getSQLState());
}
```

This is a **snippet inside the handler body**, not a standalone program. Adding `instanceof` moves the type-specific API access into a branch where a compatible type has been proven.

### 5.1. You Also Cannot Pass the Common Parameter to a Method Expecting One Specific Type

For example, suppose you have the method:

```java
static void logSql(java.sql.SQLException failure) {
    System.out.println(failure.getSQLState());
}
```

The following is **invalid**:

```java
catch (java.io.IOException | java.sql.SQLException failure) {
    logSql(failure); // Not guaranteed that failure is an SQLException.
}
```

This is a snippet placed inside a `try/catch` with matching checked exception types. `logSql(SQLException)` requires an argument compatible with `SQLException`, whereas `failure` could be an `IOException`.

Fix:

```java
catch (java.io.IOException | java.sql.SQLException failure) {
    if (failure instanceof java.sql.SQLException sqlFailure) {
        logSql(sqlFailure);
    } else {
        System.out.println("Not a SQL exception");
    }
}
```

**This rule also applies to method arguments**, assignments, and overload selection. You cannot directly use a multi-catch variable as if it always belonged to one specific branch.

## 6. Runnable Example: A Custom Common Superclass

To see that the common type does not stop at `Throwable`, let's create two distinct exceptions sharing a common API.

Create the file **`CommonCatchMemberDemo.java`**:

```java
abstract class AppFailure extends Exception {
    private final String code;

    protected AppFailure(String code) {
        super(code);
        this.code = code;
    }

    public String code() {
        return code;
    }
}

class NetworkFailure extends AppFailure {
    NetworkFailure() {
        super("NETWORK");
    }
}

class ValidationFailure extends AppFailure {
    ValidationFailure() {
        super("VALIDATION");
    }
}

public class CommonCatchMemberDemo {
    private static void fail(boolean network)
            throws NetworkFailure, ValidationFailure {
        if (network) {
            throw new NetworkFailure();
        }
        throw new ValidationFailure();
    }

    private static void inspect(boolean network) {
        try {
            fail(network);
        } catch (NetworkFailure | ValidationFailure failure) {
            System.out.println(failure.code()
                    + ": " + failure.getMessage());
        }
    }

    public static void main(String[] args) {
        inspect(true);
        inspect(false);
    }
}
```

```bash
javac CommonCatchMemberDemo.java
java CommonCatchMemberDemo
```

Output:

```text
NETWORK: NETWORK
VALIDATION: VALIDATION
```

Both `NetworkFailure` and `ValidationFailure` extend `AppFailure`; at the `catch` point, the parameter can use the public `code()` method of the common superclass. There is no need to cast to each subclass when accessing only information that both **guarantee to provide**.

The program is intentionally kept simple to focus solely on common members. In real systems, consider whether application exceptions should expose a shared superclass or a stable interface contract so handlers can process them consistently.

### 6.1. Common Interfaces and Intersection Types

The least upper bound in Java's type system can also include interfaces that all the exception alternatives implement. In that case, interface members **can** be accessed from the multi-catch parameter if Java infers a compatible intersection type and access rules permit it.

However, having two classes declare methods with the same **method name** without actually sharing a common interface is not enough for the compiler to allow the call. Do not rely on "duck typing" (two classes happening to have a method with the same name): Java checks static types, inheritance hierarchies, and interfaces.

In application APIs, a **common superclass with a clear contract** like `AppFailure` is usually the most readable example. For complex intersection types or generics, verify the exact compilation behavior of the code you are using.

## 7. Static Type Determines Overload Selection

Even though every object at runtime has a concrete type, Java resolves **overloads** at compile time based on the type of the passed expression.

Suppose there are two overloads:

```java
static void report(Exception failure) {
    System.out.println("general");
}

static void report(java.sql.SQLException failure) {
    System.out.println("SQL-specific");
}
```

If placed inside an appropriate method:

```java
catch (java.io.IOException | java.sql.SQLException failure) {
    report(failure);
}
```

The call `report(failure)` does not select the `SQLException` overload just because the actual object at runtime might be an `SQLException`. The compiler selects the overload applicable to the **common static type** of `failure`; in this example, the `Exception` overload matches.

To call the specialized overload:

```java
if (failure instanceof java.sql.SQLException sqlFailure) {
    report(sqlFailure);
} else {
    report(failure);
}
```

These are illustrative snippets used within exception handling, not standalone `main` programs. The general rule is that **overload resolution** uses the static type, whereas **override dispatch** at runtime can select the overridden version based on the class of the object for the already-selected method.

## 8. What Happens With `protected` and `private` Members?

Accessibility through a multi-catch parameter is also governed by Java's standard member access rules:

- `public`: callable if the member appears in the appropriate static type and the involved types are accessible.
- `protected`: subject to specific rules based on package, inheritance, and the type of the receiver expression; it does not automatically become public just because two exceptions both have that member.
- Members with no access modifier (*package-private*): depends on the accessing package.
- `private`: only accessible within the scope allowed by Java; multi-catch does not grant special access to another class's private data.

For example, suppose two distinct exception classes each declare their own `detail()` method, **but there is no common superclass or interface declaring `detail()`**. You cannot assume `failure.detail()` is valid just because both classes have a method with that name. That case requires designing a shared API or checking the concrete type.

In addition, a method might be declared on a common superclass as `protected`, and calling code in a package that does not satisfy the protection rules still cannot call it. This is an **accessibility** issue, separate from finding the member in the static type.

## 9. Multi-Catch Parameters Are Implicitly Final

In `catch (IOException | SQLException failure)`, `failure` is **implicitly `final`**. You cannot reassign `failure = new IOException("other")`, though you can still call methods allowed by the common static type, check `instanceof`, or rethrow the object itself. This rule **does not grant extra members** to the variable: whether reassignment is disallowed and whether `SQLException.getSQLState()` can be called are two independent type-system questions. To use a branch-specific API, narrow the type safely or separate handlers according to policy.

## 10. Rethrowing and Its Relationship to Multi-Catch Types

A useful pattern with multi-catch is logging or attaching shared context and then executing `throw failure;`. When you do so, Java still checks the checked exceptions that the call can propagate.

Create the file **`MultiCatchRethrowDemo.java`**:

```java
import java.io.IOException;
import java.sql.SQLException;

public class MultiCatchRethrowDemo {
    private static void execute(String mode)
            throws IOException, SQLException {
        if ("io".equals(mode)) {
            throw new IOException("read failed");
        }
        if ("sql".equals(mode)) {
            throw new SQLException("query failed");
        }
    }

    private static void relay(String mode)
            throws IOException, SQLException {
        try {
            execute(mode);
        } catch (IOException | SQLException failure) {
            System.out.println("forward: "
                    + failure.getClass().getSimpleName());
            throw failure;
        }
    }

    public static void main(String[] args) {
        for (String mode : new String[] {"io", "sql", "ok"}) {
            try {
                relay(mode);
                System.out.println(mode + ": success");
            } catch (IOException | SQLException failure) {
                System.out.println("received: "
                        + failure.getClass().getSimpleName());
            }
        }
    }
}
```

```bash
javac MultiCatchRethrowDemo.java
java MultiCatchRethrowDemo
```

`stdout`:

```text
forward: IOException
received: IOException
forward: SQLException
received: SQLException
ok: success
```

`relay` declares `throws IOException, SQLException`; when `failure` is rethrown, the exact received object is propagated to the caller. Java allows more precise analysis of which checked exceptions can be rethrown in an appropriate catch context, rather than forcing you to declare `throws Exception` unnecessarily.

**Do not confuse the two:** the common static type restricts **which members you can call on `failure`**; exception-checking rules for `throw failure;` can examine the caught exception types and the paths originating in the `try` block. Therefore, `failure.getSQLState()` being rejected does not imply `throw failure;` must also be rejected if the method declares the corresponding checked exception types.

### 10.1. Single-Type `catch` and Precise Rethrow

Java 7 also has a precise rethrow analysis mechanism for certain **effectively final** `catch` parameters of single-type handlers, based on the checked exception types that the `try` block can throw. This is related to, but **not identical to**, the **implicitly final** rule for multi-catch parameters.

If you need to fix a handler where precise rethrow no longer applies, check whether the parameter is reassigned and examine which checked exception types can actually escape the `try` block. Avoid equating "having multiple types in `catch`" with "all rethrows follow the exact same rules."

### 10.2. When to Rethrow vs. When to Wrap?

- **Rethrow** `throw failure;` when the current layer cannot recover and the upper layer's contract still permits those checked exception types.
- **Wrap** in an exception with a `cause` when the current layer adds domain meaning or needs to change the error abstraction.
- **Handle locally** if you know how to genuinely recover, rather than just logging and assuming the operation succeeded.

In all cases, do not write a handler just to catch, print stack traces repeatedly, and obscure the error path.

## 11. Other Restrictions of Multi-Catch Syntax

### 11.1. Alternatives Must Not Have a Parent–Child Relationship

This snippet **does not compile**:

```java
catch (java.io.IOException
       | java.io.FileNotFoundException failure) {
    System.out.println(failure.getMessage());
}
```

`FileNotFoundException` is a subclass of `IOException`, so the two alternatives in the **same multi-catch** have a subtype relationship, which Java forbids. Replace it with:

```java
catch (java.io.IOException failure) {
    System.out.println(failure.getMessage());
}
```

If you want two different handling paths, use two consecutive `catch` blocks ordered with **FileNotFoundException first, IOException second**. Do not use multi-catch to list a broader type alongside its own subclass.

### 11.2. You Cannot Write Multi-Catch With an Arbitrary Type List

Each alternative must be a valid exception type according to Java's grammar and restrictions, separated by `|`. Some examples of **invalid** syntax:

```java
catch (java.io.IOException, java.sql.SQLException e) { } // Wrong: comma instead of |.
catch (new java.io.IOException() | java.sql.SQLException e) { } // Wrong: object is not a type.
```

These are two snippets that intentionally fail to compile. In a `throws` clause, **types** are separated by commas: `throws IOException, SQLException`. Do not mix up these two syntactic positions.

### 11.3. Checked Exception Checking Still Applies

Multi-catch does not exempt you from checked exception rules. A handler can be invalid if the `try` block has no way to throw a checked exception type that it declares it catches, even if the other type is valid.

For example, the following **does not compile** because `try` has no operation capable of throwing checked `SQLException`:

```java
try {
    System.out.println("hello");
} catch (java.io.IOException | java.sql.SQLException failure) {
    System.out.println(failure.getMessage());
}
```

In fact, neither `IOException` nor `SQLException` can be thrown from the shown `try` block, so the compiler has grounds to reject it. When inspecting a specific multi-catch, distinguish between:
- Alternatives having an invalid subtype relationship.
- A checked exception type that cannot be thrown by the `try` block.
- Trying to call a type-specific method not present on the parameter's static type.
- Trying to reassign an implicitly final multi-catch variable.

Each error produces different diagnostics and requires a different fix.

## 12. Design Choice: Keep One Common Handler or Split Handlers?

There is no rule that having two exception types means you must use multi-catch. Choose based on **handling logic**:

| Need | Appropriate Approach | Why |
| --- | --- | --- |
| Two errors share the same logging and forwarding policy | One `catch (A | B e)` | Avoids duplicate logic, uses only common API |
| Two types need different recovery strategies | Two separate `catch` blocks | Each handler has a specific parameter type |
| Both share an application superclass with a common API | Multi-catch or catch the appropriate superclass | Accesses the shared contract; consider API breadth |
| Only one branch needs a specific API | Multi-catch + `instanceof` for small branching | Safely narrows the type, avoids unconditional casts |
| Most logic differs by type | Two separate `catch` blocks | Clearer than complex `instanceof` chains |
| Need to preserve checked exception types when propagating | Rethrow with matching `throws` contract | Preserves the original object and type information |
| Want to change the error abstraction layer | Create a new exception with `cause` | Expresses context while preserving the cause |

### 12.1. Split Handlers When Specialized Methods Are Needed Frequently

Example:

```java
try {
    perform();
} catch (java.sql.SQLException sql) {
    System.err.println("SQLSTATE: " + sql.getSQLState());
    System.err.println("Vendor code: " + sql.getErrorCode());
} catch (java.io.IOException io) {
    System.err.println("File I/O: " + io.getMessage());
}
```

This is an illustrative snippet, requiring `perform()` to be defined as capable of throwing both checked exception types. For this kind of specialized handling, two separate handlers are usually more readable than multi-catch followed by multiple `instanceof` checks.

### 12.2. Use `instanceof` at the Right Time

`instanceof` is helpful when only a small part needs type-specific handling; however, if you find yourself repeating `instanceof` checks dozens of times, the shared handler may be masking two distinct handling policies. Split the handlers if they require separate operations.

Do not use unchecked casts:

```java
catch (java.io.IOException | java.sql.SQLException failure) {
    java.sql.SQLException sql =
            (java.sql.SQLException) failure; // May throw ClassCastException when it is IOException.
}
```

This snippet may **compile** inside a valid `try/catch`, but the cast is only safe if the object is actually an `SQLException`. Do not assume that because one test branch tends to run with SQL, every runtime execution will take that type.

Instead, use:

```java
if (failure instanceof java.sql.SQLException sql) {
    System.out.println(sql.getSQLState());
}
```

This is a snippet inside the handler body; Java 17 supports type patterns in `instanceof` without needing an extra cast.

## 13. Self-Check Exercises

### Exercise 1 — Common Members

```java
catch (java.io.IOException | java.sql.SQLException ex) {
    System.out.println(ex.getMessage());
    System.out.println(ex.getCause());
}
```

**True or false?** True for member access. These methods are declared in `Throwable`, so they are valid through the common static type, assuming the corresponding `try` statement can throw those checked exceptions.

### Exercise 2 — `SQLException`-Only Member

```java
catch (java.io.IOException | java.sql.SQLException ex) {
    System.out.println(ex.getErrorCode());
}
```

**True or false?** False at compile-time type checking: `getErrorCode()` does not belong to the common API of the two alternatives. Check `ex instanceof SQLException sql` before calling `sql.getErrorCode()`, or split the handlers.

### Exercise 3 — Reassigning the Parameter

```java
catch (java.io.IOException | java.sql.SQLException ex) {
    ex = new java.io.IOException("new");
}
```

**True or false?** False. A multi-catch parameter is implicitly final and cannot be reassigned.

### Exercise 4 — Common Superclass

Suppose `ReadFailure` and `WriteFailure` both extend `StorageFailure`, which has a public `kind()` method. Can you call `ex.kind()` in `catch (ReadFailure | WriteFailure ex)`?

**Answer:** Yes, provided the type declarations are valid and `kind()` is actually accessible through the common type inferred by Java.

### Exercise 5 — Rethrow

The method `execute()` declares `throws IOException, SQLException` and the `try` block only calls that method; inside `catch (IOException | SQLException ex)` there is `throw ex;`. What must the enclosing method do?

**Answer:** Catch or declare the checked exceptions that can propagate out, such as `throws IOException, SQLException`. You do not need to broaden it to `throws Exception` just because the expression `ex` has a common type.

### Exercise 6 — Two Alternatives in a Subtype Relationship

Is `catch (IOException | FileNotFoundException ex)` valid?

**Answer:** No. `FileNotFoundException` extends `IOException`, so it violates the multi-catch restriction.

### Exercise 7 — Overload

There are `report(Exception)` and `report(SQLException)`. In `catch (IOException | SQLException ex)`, does calling `report(ex)` automatically choose the `SQLException` overload when an `SQLException` arrives at runtime?

**Answer:** No. Overload selection happens at compile time based on the static type of `ex`, not based on the actual runtime class to switch to the SQL overload.

## 14. Common Misconceptions

**" `IOException | SQLException` creates an object that is both an IOException and an SQLException."** False. Multi-catch receives a single object belonging to one of the matching exception branches.

**"You can call the union of all methods from the classes after `|`."** False. The compiler only allows members consistent with the common static type and accessibility rules.

**"The compiler knows it's SQL this time, so `ex.getSQLState()` is always valid."** False. The static type does not turn into `SQLException` because of runtime data or a test branch.

**"`ex.getMessage()` is invalid because the concrete type is unknown."** False. `getMessage()` belongs to `Throwable`, so it is usable.

**"In multi-catch, the parameter is always declared as `Exception`."** False. The type uses `lub` and may involve intersection type components or another common superclass.

**"As long as two classes have a method with the same name, the multi-catch variable can call it."** False. Java uses type relationships, not duck typing.

**"`final` means you cannot call methods that mutate the exception object."** False. `final` applies to reassigning the parameter variable; it does not make the object immutable.

**"`throw ex` requires declaring `throws Exception` because of the common static type."** False in many precise rethrow scenarios, where Java can determine the caught checked exception types being propagated.

**"`catch (FileNotFoundException | IOException e)` lets you handle both cases separately."** False. These two types have a parent–child relationship, so multi-catch is invalid.

**"Casting `(SQLException) ex` is always safe if the catch includes SQL."** False. `ex` could be an `IOException`, in which case the cast throws `ClassCastException`.

**"To use SQL-specific APIs, you must always use multi-catch followed by `instanceof`."** False. If the recovery paths differ significantly, two separate `catch` blocks can be clearer.

## 15. Official Documentation

- [Java Language Specification 17 — `14.20, The try Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20): multi-catch syntax, parameter types, and alternative constraints.
- [Java Language Specification 17 — `11.2, Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2): checked exception checking and rethrowing.
- [Java Language Specification 17 — `4.10.4, Least Upper Bound](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.10.4): how Java determines the common type bound.
- [Java Language Specification 17 — `15.20.2, Type Comparison Operator instanceof](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2): type checking and narrowing with `instanceof`.
- [Java SE 17 API — Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): common members such as `getMessage()`, `getCause()`.
- [Java SE 17 API — SQLException](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLException.html): SQL-specific exception members.
- [Java SE 17 API — IOException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOException.html): an I/O exception type commonly used in multi-catch.

**Takeaway:** `catch (A | B e)` catches two exception branches, but the parameter `e` can only access members permitted by the **common static type inferred from the alternatives**. To use members belonging to only one branch, narrow the type safely with `instanceof` or split the handlers when the handling policies differ. Rethrowing can preserve the original exception types without unnecessarily broadening the checked exception contract.
