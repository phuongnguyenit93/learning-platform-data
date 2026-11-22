# Practice: Writing a Tool to Invoke Methods from a Verified Contract

## 1. Problem Statement and Target Outcomes

A tool using Java Reflection can receive requests of the form `(operation name, list of input values)` and translate them into method invocations. For example:

```text
sum   ["7", "5"] -> 12
label ["go", "3"] -> "gogogo"
```

However, the tool **must not** infer an arbitrary class, method name, or signature from the input and invoke it directly. It needs a **pre-declared and verified contract**: which operations are allowed, which Java method handles each, exact parameter/return types, parsing/validation rules, the target object, and an error policy.

After this lesson, you will be able to:

1. Design a **registry/allowlist** mapping public command names to a trusted method.
2. Verify the contract at startup using `Class.getMethod(name, parameterTypes)`, return type, and declaring class.
3. Map string inputs to `Object[]` using an **explicit parser for each parameter**.
4. Validate argument count, data ranges, and business rules; classify errors before and after invocation.
5. Invoke the target using `Method.invoke(target, args)` and unwrap `InvocationTargetException` properly.
6. Test the success path, invalid input, forbidden operations, missing arguments, and exceptions thrown by the target.

This lesson uses **Java 17+**, requiring only the JDK. A "verified" contract here means that **metadata and invocation rules are verified by the program during startup**. This does not by itself replace user identity authentication or authorization if the tool is exposed over HTTP/RPC.

## 2. Designing a Verifiable Contract

A method invocation contract should minimally describe:

| Component | Function | Example |
| --- | --- | --- |
| **Alias** | Accepted public operation name | `sum` |
| **Target class** | Service class containing allowed behavior | `Service.class` |
| **Java method name** | Fixed implementation method | `sum` |
| **Parameter types** | Parameter type list **in exact order** | `int.class, int.class` |
| **Return type** | Expected return type | `int.class` |
| **Argument parsers** | Rule converting each input into a Java object | `Integer.parseInt` + range check |
| **Allowed target** | Instance created/managed by the application | `new Service()` |
| **Error policy** | Distinguish request, contract, and business errors | `IllegalArgumentException` / exception from target |

Execution flow:

```text
Register TRUSTED contract at startup
  -> resolve Method by predetermined name + parameter types
  -> verify class, public access, return type, and parser count
  -> store Method in an immutable registry

Receive request: alias + raw arguments
  -> look up in allowlist
  -> check argument count
  -> run positional parser; check syntax and value range
  -> build converted Object[]
  -> Method.invoke(target, converted)
  -> return result or classify exception
```

There are two trust boundaries that must be kept separate:

- **Contract definition** is determined by application code or vetted administrative configuration. It defines what the system is *capable* of executing.
- **Caller requests** may only pick an alias from the list and supply data. Callers must never add methods themselves, choose arbitrary classes, set `setAccessible(true)`, or define parsers via code passed in the request.

If callers come over a network or have multiple roles, you must **check the caller's permission for the alias** before invoking; the allowlist does not by itself determine who is allowed to run an operation.

## 3. Why Verify the Method Before Invoking?

Java supports exact lookup using:

```java
Method method = Service.class.getMethod("sum", int.class, int.class);
```

`Class.getMethod` retrieves the `public` method with the matching name and parameter type sequence; unlike searching only by name. Overloaded methods can share the same name with different parameter types, so a name-only contract is insufficient.

You should also verify:

```java
if (method.getDeclaringClass() != Service.class
        || method.getReturnType() != int.class
        || !Modifier.isPublic(method.getModifiers())) {
    throw new IllegalStateException("Contract mismatch");
}
```

The two snippets above are **illustrative code fragments** placed in a context with `Service`, `Method`, `Modifier`, and appropriate imports; the complete runnable program is in Section 5.

In this fixed design, requiring `getDeclaringClass() == Service.class` rejects unintended inherited methods. Another application might **intentionally** allow inherited methods if stated in the contract. These constraints must also align with how interfaces, generic bridge methods, or framework proxies are registered if used.

Do not call `clazz.getMethods()` and pick the first method matching the name: the order from the API is not a reliable overload resolution mechanism and may expose unintended behavior.

An easy-to-miss detail: `getMethod` can return a `public` method from a class that is not accessible to invoke in a given module/accessibility context. In practice, **being able to find a Method** does not guarantee **being able to invoke it** across all modules/targets. This example keeps the class/method `public` within the same application, so bypassing encapsulation with `setAccessible` is unnecessary.

## 4. Converting Arguments Positionally with Explicit Rules

Inputs shaped like `List<String>` or `String[]` need to be parsed into the declared Java types, for example:

| Parameter | Raw input | Target type | Rule |
| --- | --- | --- | --- |
| `left` | `"7"` | `int` | `Integer.parseInt` and range `0..1000` |
| `right` | `"5"` | `int` | Same as `left` |
| `text` | `"go"` | `String` | Non-null/empty/blank; max length 20 |
| `times` | `"3"` | `int` | `Integer.parseInt` and range `1..3` |

Parsers process the input, while reflection is responsible for passing the parsed values into the method. When calling `Method.invoke`, an `int` in `Object[]` is represented as `Integer`; reflection can validly unbox it when the method parameter is `int`. However, it **does not automatically** parse the string `"7"` into an integer.

The policy must be explicit:

- `null` is distinct from the string `"null"` or `""`; do not silently substitute a default value when not requested.
- `Integer.parseInt` can throw `NumberFormatException`, a subclass of `IllegalArgumentException`, for malformed syntax or numbers outside the `int` range.
- A value successfully parsed into an `int` **can still violate business rules**, such as a sum exceeding an allowed threshold.
- Do not automatically trim, change case, apply a locale, or parse alternate formats unless the contract permits it.
- Converters should enforce data limits and report **parameter position + expected type**, avoiding echoing sensitive raw input directly in error messages.

## 5. Complete Java 17+ Program

Create a file named `ContractInvocationDemo.java`. The example has no external library dependencies. It uses an immutable `Map<String, Plan>` containing two commands, `sum` and `label`; a `Plan` stores the verified `Method` and the corresponding parser for each position.

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.List;
import java.util.Map;

public final class ContractInvocationDemo {
    @FunctionalInterface
    interface Parser {
        Object parse(String raw);
    }

    static final class BusinessRuleException extends RuntimeException {
        BusinessRuleException(String message) {
            super(message);
        }
    }

    public static final class Service {
        public int sum(int left, int right) {
            int total = Math.addExact(left, right);
            if (total > 1_500) {
                throw new BusinessRuleException("sum exceeds 1500");
            }
            return total;
        }

        public String label(String text, int times) {
            return text.repeat(times);
        }
    }

    static final class Plan {
        private final String alias;
        private final Method method;
        private final Parser[] parsers;

        Plan(String alias, String methodName, Class<?> returnType,
             Class<?>[] argumentTypes, Parser[] parsers)
                throws ReflectiveOperationException {
            Method resolved = Service.class.getMethod(methodName, argumentTypes);
            if (resolved.getDeclaringClass() != Service.class
                    || !Modifier.isPublic(resolved.getModifiers())
                    || resolved.getReturnType() != returnType
                    || argumentTypes.length != parsers.length) {
                throw new IllegalStateException("invalid trusted contract: " + alias);
            }
            this.alias = alias;
            this.method = resolved;
            this.parsers = parsers.clone();
        }

        Object execute(Service target, List<String> raw) throws Throwable {
            if (raw.size() != parsers.length) {
                throw new IllegalArgumentException(alias + ": expected "
                        + parsers.length + " args, got " + raw.size());
            }
            Object[] converted = new Object[parsers.length];
            for (int i = 0; i < parsers.length; i++) {
                try {
                    converted[i] = parsers[i].parse(raw.get(i));
                } catch (IllegalArgumentException ex) {
                    throw new IllegalArgumentException(alias + ": argument " + i
                            + " expected " + method.getParameterTypes()[i].getTypeName(), ex);
                }
            }
            try {
                return method.invoke(target, converted);
            } catch (InvocationTargetException ex) {
                throw ex.getCause();
            }
        }
    }

    static int parseAmount(String raw) {
        int value = Integer.parseInt(raw);
        if (value < 0 || value > 1_000) {
            throw new IllegalArgumentException("amount out of range");
        }
        return value;
    }

    static int parseTimes(String raw) {
        int value = Integer.parseInt(raw);
        if (value < 1 || value > 3) {
            throw new IllegalArgumentException("times out of range");
        }
        return value;
    }

    static String parseText(String raw) {
        if (raw == null || raw.isBlank() || raw.length() > 20) {
            throw new IllegalArgumentException("invalid text");
        }
        return raw;
    }

    static Map<String, Plan> register() throws ReflectiveOperationException {
        return Map.of(
                "sum", new Plan("sum", "sum", int.class,
                        new Class<?>[]{int.class, int.class},
                        new Parser[]{ContractInvocationDemo::parseAmount,
                                ContractInvocationDemo::parseAmount}),
                "label", new Plan("label", "label", String.class,
                        new Class<?>[]{String.class, int.class},
                        new Parser[]{ContractInvocationDemo::parseText,
                                ContractInvocationDemo::parseTimes}));
    }

    public static void main(String[] args) throws Throwable {
        Map<String, Plan> allowlist = register();
        Service target = new Service();

        System.out.println(call(allowlist, target, "sum", List.of("7", "5")));
        System.out.println(call(allowlist, target, "label", List.of("go", "3")));

        try {
            call(allowlist, target, "getClass", List.of());
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected: " + ex.getMessage());
        }
        try {
            call(allowlist, target, "sum", List.of("7"));
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected: " + ex.getMessage());
        }
        try {
            call(allowlist, target, "sum", List.of("abc", "5"));
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected: " + ex.getMessage());
        }
        try {
            call(allowlist, target, "label", List.of("go", "9"));
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected: " + ex.getMessage());
        }
        try {
            call(allowlist, target, "sum", List.of("900", "900"));
        } catch (BusinessRuleException ex) {
            System.out.println("business: " + ex.getMessage());
        }
    }

    static Object call(Map<String, Plan> allowlist, Service target,
                       String alias, List<String> raw) throws Throwable {
        Plan plan = allowlist.get(alias);
        if (plan == null) {
            throw new IllegalArgumentException("unsupported command");
        }
        return plan.execute(target, raw);
    }
}
```

Compile and run in the directory containing the file:

```bash
javac ContractInvocationDemo.java
java ContractInvocationDemo
```

**Exact stdout** (verified by running the program on the JDK):

```text
12
gogogo
rejected: unsupported command
rejected: sum: expected 2 args, got 1
rejected: sum: argument 0 expected int
rejected: label: argument 1 expected int
business: sum exceeds 1500
```

### Tracing the Code Along a Request Path

1. `register()` is called at startup, using method names, parameter types, and return types **hard-coded by the application**. `Service.class.getMethod` looks up the exact signature. If the method does not exist, `NoSuchMethodException` causes startup to fail. If the return/declaring class is wrong or the parser count does not match, `IllegalStateException` rejects the contract.
2. `Map.of(...)` creates an unmodifiable map, so callers cannot add an alias like `getClass` afterward. `Plan` clones the parser array, preventing external code from mutating the parser array after registration.
3. `call(...)` looks up the alias in the allowlist. `"getClass"` is not in the registry even though `Service` inherits `Object.getClass`, so it reports `unsupported command`.
4. `execute(...)` checks arity before parsing. The `sum` command with only one value is rejected immediately without attempting to assign a default value.
5. Each `Parser` applies rules for one parameter. Input `"abc"` fails to parse as `int`; input `"9"` exceeds the allowed repetition limit. Both errors add context for alias, position, and target type without exposing the raw input string.
6. `method.invoke(target, converted)` invokes the **actual service object**, not a proxy itself or a method chosen from a user-supplied name.
7. If `Service.sum` throws `BusinessRuleException` because the sum exceeds 1500, reflection wraps it in `InvocationTargetException`; the handler calls `getCause()` so the caller receives the actual business error. Mapping errors are handled **before the target runs**.

In the example, the range of `parseAmount` is `0..1000`, so `Math.addExact` cannot overflow `int`; it still demonstrates how to prevent overflow when arithmetic problems have larger ranges. The 1500 limit is only used to illustrate a business rule.

### Stated Limitations of the Example

- `List.of(...)` in `main` does not permit null elements. Real-world inputs may be null/missing, so the request-receiving layer must decide the policy for both cases before calling the plan.
- The example accepts requests in code without opening an HTTP endpoint or building an authentication/authorization system. For a multi-user API, you must check the caller/role and permissions for each alias.
- `Plan.execute` does not guard against `target == null` or an incompatible target, because the code only creates a `Service` of the right type. A general-purpose tool must validate the target before invoking.
- The example registers only two methods and does not handle varargs, generic DTOs, optional values, or asynchronous methods. Those capabilities require dedicated contracts and converters.

## 6. Errors at Each Stage and How to Classify Them

Do not lump everything into a single `catch (Exception)` and report "invalid data". Separate them:

| Stage | Typical error | Meaning |
| --- | --- | --- |
| Startup / contract verification | `NoSuchMethodException` | Method does not exist with the declared signature |
| Startup / contract verification | `IllegalStateException` | Return type, declaring class, or parser count is incorrect |
| Dispatch | Alias not in allowlist | Command is unsupported or not permitted |
| Mapping | Wrong arity, invalid number, invalid null | Request does not match the schema |
| Reflection invocation | `IllegalAccessException`, `IllegalArgumentException` | Access permission issue or incompatible receiver/argument |
| Business execution | `InvocationTargetException` wrapping target's cause | Method ran and threw an exception itself |

Catch `InvocationTargetException` only at the invocation layer to extract the business cause:

```java
try {
    return method.invoke(target, converted);
} catch (InvocationTargetException ex) {
    throw ex.getCause();
}
```

This is a code snippet inside a method declared `throws Throwable`. Do not assume every `IllegalArgumentException` comes from a parser: `Method.invoke` can also raise `IllegalArgumentException` when the receiver/arguments are incompatible. If the target throws `IllegalArgumentException`, it arrives as the **cause** inside `InvocationTargetException`, allowing you to distinguish its origin.

For an HTTP API, the mapping stage may correspond to a `400 Bad Request` response; denial due to missing permissions is typically `403 Forbidden`; contract/startup failures are system errors. This is a mapping guideline depending on protocol design, not automatic Reflection behavior. Do not send raw stack traces or sensitive values to callers.

## 7. Areas to Expand for a Production Tool

### 7.1. Authorization and operation limits

The allowlist constrains **which commands exist**, whereas authorization determines **who may run which command**. Before `call`:

```text
Caller identity -> check permission for alias -> check quota/rate limit
               -> verify contract + validate input -> execute
```

Do not accept class names, package paths, method names, or a `setAccessible` flag from clients to escalate privileges. If the registry comes from a database/configuration, verify the integrity and trustworthiness of the configuration before building invocation plans.

Target calls with side effects (DB writes, sending notifications, deleting data) require idempotency, transactions, and authorization appropriate to the system. Reflection does not make a call safe or automatically retryable.

### 7.2. Overloads and selecting the exact Method

If `Service` has `save(int)` and `save(String)`, the name `"save"` alone does not identify an overload. Register the contract with **specific** parameter types, for example:

```java
Method numericSave = Service.class.getMethod("save", int.class);
```

This is an illustrative snippet assuming `Service` has a `public save(int)` method; that method **is not declared in the program in Section 5**. If you want to pick an overload based on runtime data, you need precedence rules and ambiguity detection. Never pick the first method from `getMethods()`.

### 7.3. Generics, varargs, null, and validation

- `getParameterTypes()` provides types after **type erasure**; to parse `List<String>` or generic DTOs, you need a schema or `getGenericParameterTypes()` paired with corresponding converters.
- Varargs such as `send(String... values)` have `String[]` as their last parameter type in reflection. You must construct an array of the right type and place it at that position in the arguments array; the example above does not automatically expand varargs.
- Primitive parameters cannot accept null. Wrapper/reference types can accept null at the Reflection level, though the schema or business logic may forbid it. You must distinguish **missing**, **null**, and the string `"null"`.
- Successful parsing does not guarantee business validity: for example, a negative quantity may parse cleanly yet be forbidden by the schema; `sum` also has a threshold constraint on the total.
- Enforce limits on length, element count, nesting depth, and task timeouts if requests are untrusted.

### 7.4. Do not abuse setAccessible or scan all methods

Just because you can use `getDeclaredMethods()` or `setAccessible(true)` does not mean it is a valid way to build a method invocation tool. They can bypass encapsulation design, hit JPMS module boundaries, and leave the operation surface uncontrolled.

If the goal is an API/plugin with a public contract, prefer **clear interfaces, a command registry**, or startup-verified annotations. Reflection is useful when dynamic dispatch is needed, but it does not replace typed API design and permission checks.

## 8. Test Plan for the Tool

Tests must ensure **the contract is verified**, **the mapper does not invoke the target on invalid input**, and **unauthorized/unknown commands do not run another method**.

| Test case | Input | Expected outcome |
| --- | --- | --- |
| Valid `sum` | `sum("7", "5")` | `12` |
| Valid `label` | `label("go", "3")` | `gogogo` |
| Unregistered alias | `getClass()` | Rejected, no reflection invoke performed |
| Wrong argument count | `sum("7")` | Argument count error; target not invoked |
| Bad format | `sum("abc", "5")` | Error at argument 0, expected int |
| Parser range exceeded | `label("go", "9")` | Error at argument 1 |
| Business error | `sum("900", "900")` | Target throws `BusinessRuleException`, cause preserved |
| Invalid contract | `sum` declared returning `String` | Startup fails before accepting requests |
| Missing method | Name/signature mismatch | Startup fails with `NoSuchMethodException` |
| Wrong receiver type | Invoking instance method on incompatible object | Blocked during target check or reflection reports error |
| Null/missing input | `null` or missing field | Apply schema policy, no implicit default substitution |
| Security error | Caller lacks permission for alias | Rejected before mapping/invoke |

You can log events such as `alias, result status, duration, error code`; avoid logging raw inputs and stack traces on user-facing channels. Benchmarking and caching `Method` should only be done after correctness and permissions are secured.

## 9. Practice Extensions

**Exercise 1 — Add a safe command.** Add `multiply(int,int)` and register the `multiply` alias with two range-checking parsers and return type `int`. Verify both valid commands and overflow errors using `Math.multiplyExact` if you want to demonstrate arithmetic errors.

**Exercise 2 — Permission checks.** Create a `role -> allowed aliases` map and enforce it before `call`. Write a test proving a user with only `label` permission cannot run `sum` even if they know the alias.

**Exercise 3 — Enums and dates.** Add a method accepting `LocalDate` or a specific enum; register explicit converters. Test valid/invalid ISO formats and non-existent enum constants.

**Exercise 4 — Target exceptions.** Create a method that intentionally throws a declared checked exception; verify the caller receives the business cause via `InvocationTargetException.getCause()`, not confused with a parser error.

**Exercise 5 — Null/missing.** Replace `List.of` with a request class capable of representing missing/null/string. Clearly define required, optional, and default fields, and validate before reflection invocation.

**Exercise 6 — Contract drift.** Change the method's return type while keeping the old registration metadata, then rerun the application. The right outcome is **startup failure**, instead of waiting for the first user request to uncover the mismatched contract.

## 10. Self-Check Questions

1. **Why not let callers send any class/method name?** Because input would then control the set of callable behaviors; a trusted registry must restrict operations.
2. **Why check the return type even though `getMethod` searches only by parameter types?** Because the contract may require a specific return type, and the actual method might have changed.
3. **Does `Method.invoke` parse `"7"` into `int`?** No. A parser must do that beforehand, after which reflection can unbox `Integer` to `int`.
4. **What happens if a caller chooses an unregistered alias `getClass`?** It is rejected, even though `getClass()` actually exists on `Object`.
5. **How do target errors differ from conversion errors?** Conversion errors happen before invoke; target errors pass through `InvocationTargetException` and require extracting the cause.
6. **Does an allowlist replace authentication/authorization?** No. An allowlist decides which operations are *supported by the system*; caller permissions must still be checked separately.
7. **Why not pick an overload solely by method name?** Because multiple different signatures may exist; you need parameter types or explicit disambiguation rules.

## 11. Key Takeaways

A controlled method invocation tool should follow the sequence **declare trusted contract → verify exact Method → register allowed aliases → check caller permissions → parse/validate each argument → invoke target → classify result/exception**.

Reflection provides the dynamic execution mechanism; the contract and mapping rules decide which behaviors are permitted. Favor failing fast at startup for broken contracts, returning clear errors for invalid input, preserving business exception causes, and testing every rejection path before deploying the tool to production.

Java 17 Documentation:

- [Class.getMethod](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getMethod(java.lang.String,java.lang.Class...))
- [Method.invoke](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#invoke(java.lang.Object,java.lang.Object...))
- [InvocationTargetException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationTargetException.html)
- [Modifier](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Modifier.html)