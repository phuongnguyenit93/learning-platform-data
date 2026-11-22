# 19.3 Designing a Dynamic Dispatcher with Signatures, Type Conversion, and Structured Errors

**Module:** Java Advance - dynamic-runtime  
**Parent Topic:** 19. Design and Performance  
**Language:** Java 17+  
**Key APIs:** `MethodType`, `MethodHandle`, `MethodHandles.Lookup`, `MethodHandle.asType`, `asSpreader`, `invokeExact`; application-layer dispatch policy and error handling.

## Learning Objectives

A **dynamic dispatcher** receives a request at runtime, finds the right registered operation, checks the signature, normalizes arguments according to policy, invokes the implementation, and returns a value or a predictable error. It can sit behind a plugin system, workflow engine, rule engine, RPC adapter, or dynamic operation handling API.

The challenge does not lie in invoking an arbitrary method using Reflection. The challenge is building **a stable and controlled contract** between dynamic data and typed Java methods: distinguishing overloads, avoiding dangerous implicit conversions, defining error-checking order, preserving failure causes, and not accidentally expanding execution privileges.

After this lesson, you can:

1. Design a registry using **`(operation, MethodType)`** as the key for explicit overload dispatch, instead of choosing a method by arbitrary iteration order.
2. Distinguish **declared signature**, **runtime type of a Java value**, and **MethodHandle adapter**.
3. Separate two conversion policies: **`STRICT`** (primitive parameters only accept the exact wrapper) and **`WIDEN_INT_TO_LONG`** (allows exactly one intentional widening conversion).
4. Establish clear error rules for nonexistent operations, unsupported signatures, wrong arity, wrong types, and target exceptions.
5. Build an immutable registry, create MethodHandle adapters once, and use `invokeExact` at the validated boundary.
6. Distinguish `invokeExact`, `invoke`, `asType`, `asSpreader`, and `invokeWithArguments`; understand why something may link/call at the JVM layer yet still be unsuitable for business policy.
7. Compile/run two Java 17 programs demonstrating practical dispatch and type conversion boundaries.
8. Evaluate trade-offs in performance, concurrency, class loaders, access control, input validation, and observability.

## 1. A Dynamic Dispatcher Is a Contracted Boundary

Let us start from external requests:

~~~text
"format", "(String)String", ["Java"]
"format", "(String,int)String", ["ha", 3]
"sum",    "(long,long)long", [2, 5]
~~~

This is **illustrative data**, not JSON format or complete Java syntax. The two `format` operations have the same name but different signatures, so they are **two separate routes**. The `sum` operation requires two `long`s, whereas an external source might supply numbers as `Integer`, `Long`, `BigDecimal`, or the string `"2"`. The dispatcher should not silently guess conversions.

Proposed pipeline:

~~~text
Request data
      |
      v
[1] Validate request shape
      |
      v
[2] Exact lookup of (operation, MethodType)
      |
      v
[3] Validate argument count (arity)
      |
      v
[4] Validate/normalize each runtime value per Policy
      |
      v
[5] Invoke target via prepared MethodHandle adapter
      |
      +-- success -> Object/boxed primitive/null for void
      |
      +-- target error -> TARGET_FAILURE code + root cause
~~~

Each phase has its own **responsibility** and **error category**. Do not use an outer `catch(Exception e)` block to turn everything into an "operation failed" message and lose track of signature errors, data errors, and target errors.

### 1.1. A Signature Is Not Just a Method Name

`java.lang.invoke.MethodType` describes parameter types **in order** and the return type. The snippet:

~~~java
MethodType oneString =
        MethodType.methodType(String.class, String.class);
MethodType stringInt =
        MethodType.methodType(String.class, String.class, int.class);
MethodType twoLongs =
        MethodType.methodType(long.class, long.class, long.class);
~~~

is a snippet inside a method with `import java.lang.invoke.MethodType`. The corresponding descriptors:

~~~text
(String)String
(String,int)String
(long,long)long
~~~

**The first parameter** of `MethodType.methodType` is the **return type**; the remaining parameters are the **parameter types**. `String.class` differs from `Object.class`, `long.class` differs from `Long.class`, and `(String)String` differs from `(String)Object` even though the runtime return value may be a String in both cases.

Use `MethodType.equals` to compare signatures: same return type and each parameter type in order. Do not select an overload merely because `getName()` matches or because the argument count matches.

### 1.2. Runtime Arguments Are Not a MethodType

Suppose the signature requires `(long,long)long`, but the source receives data of the form:

~~~java
Object[] values = {Integer.valueOf(2), Long.valueOf(5)};
~~~

This is valid Java code inside a method. The fact that `values[0] instanceof Integer` does not turn the registered signature into `(Integer,Long)long`. One must distinguish:

- **Declared target signature:** `MethodHandle.type()`.
- **Selected route signature:** the registered `MethodType`, which must equal the declared target signature.
- **Runtime values:** the actual objects present in `Object[]`.
- **Conversion policy:** normalizes runtime values into types that can be passed to the target in an approved manner.

A good dispatcher **does not let arbitrary runtime values alter the route's contract**. If you want overload resolution by runtime types, you must publish a clear selection algorithm with rules for ambiguous cases. This lesson chooses a safer and more testable design: **the caller must select the exact descriptor; conversion does not participate in automatic overload selection**.

## 2. Overload Dispatch by Explicit Key

### 2.1. Immutable Registry

A route has an identity:

~~~java
record Key(String operation, MethodType signature) { }
~~~

This is a Java 17 `record`, not a standalone program. When building the Map:

~~~text
Key("format", (String)String)       -> MethodHandle format(String)
Key("format", (String,int)String)   -> MethodHandle format(String,int)
Key("sum",    (long,long)long)      -> MethodHandle sum(long,long)
~~~

**The same operation name with different signatures** are different keys. An exact duplicate of the same `Key` must be rejected immediately upon registration — never silently overwrite an already installed implementation.

The architecture has two phases:

1. **Bootstrap/registration:** use `MethodHandles.Lookup.findStatic`, `findVirtual`, or a factory with valid access to obtain handles; verify `handle.type().equals(key.signature())`; create the adapter; freeze the registry.
2. **Request-time dispatch:** only look up an approved route, validate runtime args, then invoke.

When not updating the registry mid-flight, `Map.copyOf` prevents callers from arbitrarily adding routes through an old Map reference. **Map immutability does not automatically make target methods thread-safe** or eliminate state inside objects referenced by handles.

### 2.2. Why Not Use `Map<String, Method>` Naively?

A map keyed only by the name `format` will overwrite one of the two overloads, or force you to guess the method based on `Object[]`. Guessing by "the first method that can be cast/coerced" is an anti-pattern:

- The order of `Class.getDeclaredMethods()` is not a business precedence rule.
- `Integer` could match `int`, `long`, or `Number` if widening conversions are chosen; the result easily depends on iteration order.
- `null` can match many reference types without selecting a specific type.
- Two methods differing in **return type** cannot be safely distinguished from the argument count alone.
- The same method name in two modules/class loaders may require additional namespace/version identifiers.

If a system must auto-select overloads, it should have **a specified and tested resolution algorithm** (exact match first, whitelisted widening, ambiguous → dedicated error code), or avoid overloads at the external API boundary by providing distinct operation names. In the demo, we do **not** auto-select overloads.

### 2.3. Type Identity and Class Loaders

`MethodType` holds actual `Class<?>` instances. If two plugin loaders define the same name `com.example.Request`, those two `Class<?>` instances are not the same type. There is no guarantee that two `MethodType` instances with the same display name will be equal when parameter classes belong to different defining loaders.

When designing a plugin dispatcher:

- Place the SPI contract in a shared module/loader with exactly **one definition**.
- Only register an implementation when `Lookup` has actual access; `IllegalAccessException` at registration is not a request-time conversion error.
- Do not normalize signatures by comparing `Class.getName()` strings and ignoring loader identity.

## 3. Type Conversion Policy: Explicit, Minimal, and Verifiable

A dispatcher typically receives `Object[]`. For Java primitive parameters, the object at the boundary must be unboxed. However, the fact that the JVM **is capable of** adapting a MethodHandle call does not mean the system should allow every conversion.

### 3.1. The STRICT Policy

Under `STRICT`:

- Primitive `int` → only accepts `Integer`, `long` → only accepts `Long`, `boolean` → only accepts `Boolean`, etc.
- Reference type `String` → accepts a `String` object or a valid subtype; `Number` → can accept `Integer`/`Long` because they are subclasses of Number.
- Reference parameters may accept `null` if the contract allows; primitive parameters **do not** accept null.
- Do not parse the string `"123"` into a number.
- Do not accept `Integer` to pass into a primitive `long` parameter.
- Do not narrow `Long` to `int`, and do not automatically convert an arbitrary object to String via `toString()`.

Verification table:

| Target parameter | Runtime value | STRICT |
| --- | --- | --- |
| `long` | `Long.valueOf(2)` | Allowed |
| `long` | `Integer.valueOf(2)` | Rejected |
| `int` | `Integer.valueOf(2)` | Allowed |
| `int` | `Long.valueOf(2)` | Rejected |
| `String` | `"Java"` | Allowed |
| `String` | `Integer.valueOf(2)` | Rejected |
| `Number` | `Integer.valueOf(2)` | Allowed by assignability |
| `long` | `null` | Rejected |
| `String` | `null` | Allowed in this API example; domain may restrict further |

**Note:** `STRICT` here is **a policy defined by us**, not a built-in constant of Java `MethodHandles`. It ensures the input object matches the wrapper or reference assignability; the target itself may apply stricter business validation.

### 3.2. The WIDEN_INT_TO_LONG Policy

To demonstrate intentional conversion, we only widen:

~~~text
target param type = primitive long
runtime value     = java.lang.Integer
Policy            = WIDEN_INT_TO_LONG
conversion        = Long.valueOf(integer.longValue())
~~~

Other conversions remain rejected. The reason for choosing `Integer → long`: this is a **widening primitive conversion** without losing any value of a 32-bit signed int. Still, it must be converted **before invoking**, and then the adapter only unboxes `Long`.

This policy **does not** allow `String "2" → long`, `Long → int`, or `Double → long`. Those conversions may require parsing, rounding, overflow checking, or depend on locale, and should not be "conveniently" allowed by a mode named "coerce".

If the application has additional conversion rules, design an **intentional policy table**:

| Proposed conversion | Risk level | Recommendation |
| --- | --- | --- |
| `byte → short/int/long`, `int → long` | Exact integer widening | Can be whitelisted if the contract allows |
| `long → double` | May lose precision for large numbers | Do not apply by default; requires explicit rule |
| `double → int` | Narrowing, truncates fraction/bounds | Requires range and semantics checks |
| `String → Integer/Long` | Parsing can fail, subject to format/locale | Only parse in a dedicated DTO/schema layer |
| `Number → String` | Formatting and locale are inconsistent | Choose a standardized codec and versioning |
| `Object → domain DTO` | Reflection/mapper has side effects and vulnerabilities | Validate schema/whitelist fields |
| `null → primitive` | No valid value | Reject |
| `String → enum` | Needs valid name table and case policy | Choose an explicit validator |

### 3.3. Typed Return Values Are Also a Contract

The return type is part of `MethodType`. A dispatcher can choose the Java API:

~~~java
Object call(String operation, MethodType signature,
            Policy policy, Object... args)
~~~

When calling through a generic adapter `(Object[])Object`:

- A target returning `long` is boxed into `Long` at the boundary.
- A target returning `String` yields `String`.
- A target returning `void` can be normalized by the adapter to **`null`**.
- A target throwing an error does not return a normal result; it follows the error-handling policy.

**Do not conflate a returned `null` with void** in a public API if consumers need to distinguish them. In a real system, you can use a result envelope containing `VOID`/`NULL`/`VALUE` or an explicitly typed result contract, such as `record Success(Object value, boolean isVoid)`. The minimal demo uses `Object` and explicitly documents `void → null`.

If the caller needs a return type `T`, use a typed facade based on the **registered route signature**, verifying the return type and casting in a controlled manner. Do not let the client choose a different return type and cast from object without checking the descriptor.

## 4. "Structured" Errors Are the Result of Layered Responsibilities

Instead of using unstable exceptions as API messages, fixed error codes can be defined:

| Code | Phase | Condition |
| --- | --- | --- |
| `INVALID_REQUEST` | Validate request shape | Blank/null name, null signature, null policy, null varargs array |
| `UNKNOWN_OPERATION` | Lookup name | No such operation name is registered |
| `SIGNATURE_MISMATCH` | Lookup exact key | Operation exists, but not with the requested `MethodType` |
| `ARITY_MISMATCH` | Validate argument count | Runtime argument count differs from `signature.parameterCount()` |
| `ARGUMENT_TYPE` | Validate/normalize | Runtime value does not match declared param or policy; null primitive |
| `TARGET_FAILURE` | Invoke target | Implementation throws an exception or a nonfatal error wrapped by policy |

**The checking order in the demo is part of the contract:** `INVALID_REQUEST → UNKNOWN_OPERATION → SIGNATURE_MISMATCH → ARITY_MISMATCH → ARGUMENT_TYPE → invoke`. If a request both selects the wrong signature and passes the wrong type, the demo reports **`SIGNATURE_MISMATCH` first**, because there is not yet a route to determine the expected parameter types.

If an application needs to check arity before signature resolution, decide that explicitly in the API documentation and test the new order. Do not let exception-catching order change arbitrarily across versions.

### 4.1. Separating Caller Errors from System Errors

- **Request errors**: unknown operation, signature mismatch, bad argument; the consumer can fix the input without changing the target's source code.
- **Configuration errors**: registering the same route twice, target.type not matching the route key, lookup lacking access; usually detected at startup rather than waiting for a request to handle.
- **Target errors**: business logic throws `IllegalStateException`, `ArithmeticException`, or a checked exception; must preserve `getCause()` to debug the target accurately.
- **JVM/linkage/fatal errors**: `VirtualMachineError`, `ThreadDeath`, `LinkageError`; in the demo we **do not attempt to wrap** these three groups into ordinary error codes, so as not to mask conditions where execution cannot safely continue.

This is an example of a practical policy, **not the only taxonomy**. Production may need a `Result<T,Error>` or explicit HTTP/RPC mapping, and dedicated handling for interruption, cancellation, timeout, retry, and idempotency. Do not blindly retry a target with side effects when an exception occurred **after** the successful part of the work.

### 4.2. Preserving Root Cause

When the real target throws an error:

~~~java
throw new DispatchFailure(
        Code.TARGET_FAILURE, "target failed: " + operation, failure);
~~~

Saving `failure` as the cause lets operators see the stack trace and causal chain, while callers get a stable code to decide UI/retry/alert behavior. Do not expose full stack traces, classpaths, or secret tokens from `Throwable.getMessage()` in public responses: internal logs and response envelopes have different levels of detail.

One caveat: the example uses `catch(Throwable)` as the catch path for MethodHandle exceptions, but it **separates out the three special JVM error groups first**. In a real system, consider rethrowing other `Error`s according to a specific fatal/bug policy; do not assume every `Error` can be safely recovered from.

## 5. Adapter Design: Register Once, Use Many Times

Keep the accurately typed target in the registry, while providing a uniform call path using `Object[]`:

~~~text
target:       (String,int)String
      |
      | asType((Object,Object)Object)
      v
generic:      (Object,Object)Object
      |
      | asSpreader(Object[].class, 2)
      v
invoker:      (Object[])Object
~~~

At registration:

~~~java
MethodHandle invoker = target
        .asType(MethodType.genericMethodType(
                target.type().parameterCount()))
        .asSpreader(Object[].class, target.type().parameterCount());
~~~

This snippet assumes `target` is a MethodHandle already found via `Lookup`.

**Why design it this way?**

- `asType` creates a handle that externally accepts/returns `Object`, inserting checkcasts, unboxing, boxing, or the appropriate default value for a void return.
- `asSpreader` converts an `Object[]` into the arguments of the handle after adaptation.
- Every route has an invoker of type **`(Object[])Object`**, so the dispatcher can call:

~~~java
return (Object) route.invoker().invokeExact(prepared);
~~~

- `invokeExact` requires the call-site descriptor to match **exactly**; the expression above has a compile-time argument of type `Object[]` and a return type of `Object`.
- Normalizing `prepared` is performed **before** the handle call, according to app policy. The generic adapter can still cast/unbox internally, but it is not the source of truth deciding "whether Integer can be widened to long".

**Do not optimize prematurely:** `asType`/`asSpreader` can support a flexible call path, yet still incur overhead, boxing, and runtime checks. The demo builds the adapter **once in the constructor** rather than per request. For hot requests, caching/layering a typed path may be more appropriate; measure in practice with JMH.

### 5.1. `invokeWithArguments` Can Be Convenient, but Does Not Replace Validation

`MethodHandle.invokeWithArguments(Object...)` is very useful for dynamic code, but it uses flexible conversion semantics and a varargs/generic call path. It is not a "business conversion policy" API and often has different overhead from typed `invokeExact`. If called directly with unvalidated data, casts/unboxing/numeric adaptations will occur according to JVM rules, which may not match application rules.

The chosen approach fixes a **single generic invoker shape**, validates first, and then invokes. When a high-performance typed call path is needed, you can also keep the direct handle with its signature to call via `invokeExact` from a call site with a matching compile-time descriptor.

### 5.2. `asType` Can Adapt the Type, but Does Not Change the Route Key

An `asType` adapter returns a **new MethodHandle**. It does not alter the `MethodType` of the original direct target. If the target has type `(long)long`, you can create an `(int)long` adapter for a specific call site, but in the registry:

~~~text
registered route signature = (long)long
runtime integer conversion = Policy.WIDEN_INT_TO_LONG
normalized object          = Long
generic invocation         = (Object[])Object
~~~

Here **the route remains `(long)long`**. Do not accidentally register it as `(int)long` just because the policy allows Integer input. Conversion is an operation **after selecting the route**.

## 6. Complete Java 17 Demo: Dynamic Dispatcher with Signatures and Error Codes

The program below implements:

- Route key is `record Key(String operation, MethodType signature)`.
- Registry has two overloads of `format` along with three other operations.
- Each registered MethodHandle is type-checked and then converted into a generic invoker `(Object[])Object`.
- `STRICT` checks primitive wrappers or reference assignability.
- `WIDEN_INT_TO_LONG` allows only the exact conversion `Integer → primitive long`.
- Error paths have fixed codes; target errors are preserved under `DispatchFailure.getCause()`.
- `void` is represented as `null` via the generic return adapter.
- The registry is immutable after bootstrap; runtime does not mutate the route list.

**Standalone file:** `TypedDispatcherDemo.java`

~~~java
import java.lang.invoke.*;
import java.util.*;

public final class TypedDispatcherDemo {
    enum Policy { STRICT, WIDEN_INT_TO_LONG }
    enum Code {
        INVALID_REQUEST, UNKNOWN_OPERATION, SIGNATURE_MISMATCH,
        ARITY_MISMATCH, ARGUMENT_TYPE, TARGET_FAILURE
    }

    static final class DispatchFailure extends RuntimeException {
        private final Code code;
        DispatchFailure(Code code, String message) {
            super(message);
            this.code = code;
        }
        DispatchFailure(Code code, String message, Throwable cause) {
            super(message, cause);
            this.code = code;
        }
        Code code() { return code; }
    }

    record Key(String operation, MethodType signature) { }
    record Route(MethodType signature, MethodHandle invoker) { }

    static final class Dispatcher {
        private final Map<Key, Route> routes;
        private final Set<String> names;

        Dispatcher(Map<Key, MethodHandle> targets) {
            Map<Key, Route> built = new HashMap<>();
            for (Map.Entry<Key, MethodHandle> e : targets.entrySet()) {
                Key key = e.getKey();
                MethodHandle target = e.getValue();
                if (target == null || !target.type().equals(key.signature())) {
                    throw new IllegalArgumentException("invalid route " + key);
                }
                MethodHandle invoker = target
                        .asType(MethodType.genericMethodType(
                                key.signature().parameterCount()))
                        .asSpreader(Object[].class,
                                key.signature().parameterCount());
                built.put(key, new Route(key.signature(), invoker));
            }
            routes = Map.copyOf(built);
            Set<String> declared = new HashSet<>();
            for (Key key : routes.keySet()) {
                declared.add(key.operation());
            }
            names = Set.copyOf(declared);
        }

        Object call(String operation, MethodType signature,
                    Policy policy, Object... args) {
            if (operation == null || operation.isBlank() ||
                    signature == null || policy == null || args == null) {
                throw new DispatchFailure(Code.INVALID_REQUEST, "invalid call");
            }
            if (!names.contains(operation)) {
                throw new DispatchFailure(Code.UNKNOWN_OPERATION,
                        "unknown operation: " + operation);
            }
            Route route = routes.get(new Key(operation, signature));
            if (route == null) {
                throw new DispatchFailure(Code.SIGNATURE_MISMATCH,
                        "unsupported signature: " + signature);
            }
            if (args.length != signature.parameterCount()) {
                throw new DispatchFailure(Code.ARITY_MISMATCH, "wrong arity");
            }
            Object[] prepared = args.clone();
            for (int i = 0; i < prepared.length; i++) {
                prepared[i] = normalize(signature.parameterType(i),
                        prepared[i], policy, i);
            }
            try {
                return (Object) route.invoker().invokeExact(prepared);
            } catch (VirtualMachineError | ThreadDeath | LinkageError fatal) {
                throw fatal;
            } catch (Throwable failure) {
                throw new DispatchFailure(Code.TARGET_FAILURE,
                        "target failed: " + operation, failure);
            }
        }

        private static Object normalize(Class<?> expected, Object value,
                                        Policy policy, int index) {
            if (value == null) {
                if (expected.isPrimitive()) {
                    throw new DispatchFailure(Code.ARGUMENT_TYPE,
                            "null for primitive argument " + index);
                }
                return null;
            }
            Class<?> boxed = wrapper(expected);
            if (boxed.isInstance(value)) {
                return value;
            }
            if (policy == Policy.WIDEN_INT_TO_LONG
                    && expected == long.class
                    && value instanceof Integer n) {
                return Long.valueOf(n.longValue());
            }
            throw new DispatchFailure(Code.ARGUMENT_TYPE,
                    "argument " + index + ": expected " + boxed.getSimpleName());
        }

        private static Class<?> wrapper(Class<?> type) {
            if (type == boolean.class) return Boolean.class;
            if (type == byte.class) return Byte.class;
            if (type == short.class) return Short.class;
            if (type == char.class) return Character.class;
            if (type == int.class) return Integer.class;
            if (type == long.class) return Long.class;
            if (type == float.class) return Float.class;
            if (type == double.class) return Double.class;
            return type;
        }
    }

    private static void add(Map<Key, MethodHandle> routes,
                            String name, MethodHandle target) {
        if (routes.putIfAbsent(new Key(name, target.type()), target) != null) {
            throw new IllegalArgumentException("duplicate route");
        }
    }

    public static String format(String value) {
        return "tag:" + value;
    }

    public static String format(String value, int times) {
        return value.repeat(times);
    }

    public static long sum(long left, long right) {
        return Math.addExact(left, right);
    }

    public static void audit(String value) {
        System.out.println("audit:" + value);
    }

    public static String fail(String value) {
        throw new IllegalStateException("boom:" + value);
    }

    private static void expect(String label, Code code, Runnable action) {
        try {
            action.run();
            System.out.println(label + "=unexpected-success");
        } catch (DispatchFailure error) {
            if (error.code() != code) {
                throw error;
            }
            System.out.println(label + "=" + error.code());
            if (code == Code.TARGET_FAILURE) {
                System.out.println(label + ".cause=" +
                        error.getCause().getClass().getSimpleName());
            }
        }
    }

    public static void main(String[] args) throws Exception {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType oneString = MethodType.methodType(String.class, String.class);
        MethodType stringInt =
                MethodType.methodType(String.class, String.class, int.class);
        MethodType twoLongs =
                MethodType.methodType(long.class, long.class, long.class);
        MethodType voidString =
                MethodType.methodType(void.class, String.class);

        Map<Key, MethodHandle> targets = new HashMap<>();
        add(targets, "format", lookup.findStatic(
                TypedDispatcherDemo.class, "format", oneString));
        add(targets, "format", lookup.findStatic(
                TypedDispatcherDemo.class, "format", stringInt));
        add(targets, "sum", lookup.findStatic(
                TypedDispatcherDemo.class, "sum", twoLongs));
        add(targets, "audit", lookup.findStatic(
                TypedDispatcherDemo.class, "audit", voidString));
        add(targets, "fail", lookup.findStatic(
                TypedDispatcherDemo.class, "fail", oneString));

        Dispatcher dispatcher = new Dispatcher(targets);
        System.out.println("routes=" + targets.size());
        System.out.println("format.one=" +
                dispatcher.call("format", oneString, Policy.STRICT, "Java"));
        System.out.println("format.two=" +
                dispatcher.call("format", stringInt, Policy.STRICT, "ha", 3));
        System.out.println("sum.strict=" +
                dispatcher.call("sum", twoLongs, Policy.STRICT, 2L, 5L));
        System.out.println("sum.widen=" +
                dispatcher.call("sum", twoLongs, Policy.WIDEN_INT_TO_LONG, 2, 5));
        Object ignored = dispatcher.call("audit", voidString,
                Policy.STRICT, "saved");
        System.out.println("audit.return=" + ignored);

        expect("unknown", Code.UNKNOWN_OPERATION,
                () -> dispatcher.call("missing", oneString, Policy.STRICT, "x"));
        expect("signature", Code.SIGNATURE_MISMATCH,
                () -> dispatcher.call("format",
                        MethodType.methodType(Object.class, String.class),
                        Policy.STRICT, "x"));
        expect("arity", Code.ARITY_MISMATCH,
                () -> dispatcher.call("format", stringInt, Policy.STRICT, "ha"));
        expect("strictInteger", Code.ARGUMENT_TYPE,
                () -> dispatcher.call("sum", twoLongs, Policy.STRICT, 2, 5));
        expect("nullPrimitive", Code.ARGUMENT_TYPE,
                () -> dispatcher.call("sum", twoLongs, Policy.STRICT,
                        new Object[]{null, 2L}));
        expect("stringToNumber", Code.ARGUMENT_TYPE,
                () -> dispatcher.call("sum", twoLongs,
                        Policy.WIDEN_INT_TO_LONG, "2", 5L));
        expect("targetFailure", Code.TARGET_FAILURE,
                () -> dispatcher.call("fail", oneString, Policy.STRICT, "x"));
        expect("overflow", Code.TARGET_FAILURE,
                () -> dispatcher.call("sum", twoLongs, Policy.STRICT,
                        Long.MAX_VALUE, 1L));
    }
}
~~~

### 6.1. How to Compile and Run

Save the file `TypedDispatcherDemo.java` in a separate directory. Use JDK 17 or higher:

~~~bash
javac --release 17 -d out TypedDispatcherDemo.java
java -cp out TypedDispatcherDemo
~~~

The example uses `record`, pattern matching `instanceof`, `String.repeat`, and the MethodHandle API available in Java 17. The command `javac -d out` can create the `out` directory if it does not yet exist.

### 6.2. Exact Tested Stdout

~~~text
routes=5
format.one=tag:Java
format.two=hahaha
sum.strict=7
sum.widen=7
audit:saved
audit.return=null
unknown=UNKNOWN_OPERATION
signature=SIGNATURE_MISMATCH
arity=ARITY_MISMATCH
strictInteger=ARGUMENT_TYPE
nullPrimitive=ARGUMENT_TYPE
stringToNumber=ARGUMENT_TYPE
targetFailure=TARGET_FAILURE
targetFailure.cause=IllegalStateException
overflow=TARGET_FAILURE
overflow.cause=ArithmeticException
~~~

This Java code has been **compiled with `javac --release 17` and actually executed**; the order and content of the lines above match the output.

### 6.3. Reading the Success Results

**`routes=5`**: the registry has **five** exact `Key`s. `format` has two overloads, so the number of operation names differs from the number of routes. One implementation does not overwrite another.

**`format.one=tag:Java`**: route `(String)String` invokes `format(String)`. `format.two=hahaha`: route `(String,int)String` invokes `format(String,int)`. The caller **specifies the signature upfront**; the dispatcher does not rely on the runtime type String to find an overload.

**`sum.strict=7`**: both arguments are `Long` so they match `long,long` after unboxing. **`sum.widen=7`**: both arguments are initially `Integer`, but the `WIDEN_INT_TO_LONG` policy converts them to `Long` before entering the generic invoker.

**`audit:saved`**: the `void`-returning method is actually invoked. **`audit.return=null`**: the generic adapter has an Object return, so it represents a void result as null. That is not a null returned by the `audit` target itself.

### 6.4. Reading the Error Codes by Phase

**`unknown=UNKNOWN_OPERATION`**: there is no name `missing` in the registry, so there is no need to examine the descriptor or runtime arguments.

**`signature=SIGNATURE_MISMATCH`**: operation `format` exists, but route `(String)Object` does not. The fact that String is assignable to Object does not make two `MethodType`s equal.

**`arity=ARITY_MISMATCH`**: the caller selects route `format(String,int)`, but passes only one argument; the count check runs before type normalization.

**`strictInteger=ARGUMENT_TYPE`**: `sum` requires `long,long`; two `Integer`s are invalid under `STRICT` even though the JVM has some numeric adaptations. **`nullPrimitive=ARGUMENT_TYPE`**: null cannot be unboxed to `long`.

**`stringToNumber=ARGUMENT_TYPE`**: `WIDEN_INT_TO_LONG` does not include parsing Strings. The value `"2"` is not silently parsed.

**`targetFailure=TARGET_FAILURE`** and `targetFailure.cause=IllegalStateException`: the request has the right signature and the right runtime args, but `fail(String)` intentionally throws an error. **`overflow.cause=ArithmeticException`**: `Math.addExact` checks for overflow; the dispatcher does not turn a target exception into a data-type error. Preserving `getCause()` helps distinguish business logic from boundary errors.

### 6.5. What the Demo Intentionally Does Not Do

This is an **illustrative architecture**, not a production RPC framework:

- The API returns `Object`, without an envelope distinguishing void and nullable returns.
- No detailed schema validation such as string length, allowed format, domain constraints, currency, timezone, or locale.
- No principal/tenant-based authorization. A route existing **does not mean** the caller is allowed to run it.
- Does not provide hot reload/route registration while requests are in flight.
- Does not implement retry/timeout/circuit breaker/tracing.
- Does not auto-generate overload resolution from runtime values. The caller must know the published `MethodType`.
- Does not manage thread interruption/cancellation separately; production needs specific mechanisms if targets perform blocking operations.
- Does not prove throughput/latency. It only tests correctness of error categories and results.

## 7. Standalone Example: `invokeExact`, `invoke`, and `asType` Do Not Equal Application Policy

A method with signature `(long)long` can be called in several ways with different JVM rules. Yet the sample dispatcher still chooses **`STRICT`** per API requirements.

**File:** `ConversionBoundaryDemo.java`

~~~java
import java.lang.invoke.*;

public final class ConversionBoundaryDemo {
    public static long twice(long value) {
        return Math.multiplyExact(value, 2L);
    }

    public static void main(String[] args) throws Throwable {
        MethodHandle exact = MethodHandles.lookup().findStatic(
                ConversionBoundaryDemo.class, "twice",
                MethodType.methodType(long.class, long.class));
        System.out.println("target.type=" + exact.type());
        System.out.println("exact=" + (long) exact.invokeExact(7L));

        try {
            long ignored = (long) exact.invokeExact(7);
            System.out.println("badExact=" + ignored);
        } catch (WrongMethodTypeException expected) {
            System.out.println("badExact=WrongMethodTypeException");
        }

        System.out.println("invoke.widen=" + (long) exact.invoke(7));
        MethodHandle adapter = exact.asType(
                MethodType.methodType(long.class, int.class));
        System.out.println("adapter.type=" + adapter.type());
        System.out.println("adapter.exact=" + (long) adapter.invokeExact(7));
        try {
            exact.asType(MethodType.methodType(long.class, String.class));
            System.out.println("badAdapter=unexpected");
        } catch (WrongMethodTypeException expected) {
            System.out.println("badAdapter=WrongMethodTypeException");
        }
    }
}
~~~

Compile/run in the directory containing the file:

~~~bash
javac --release 17 -d out ConversionBoundaryDemo.java
java -cp out ConversionBoundaryDemo
~~~

**Verified** stdout:

~~~text
target.type=(long)long
exact=14
badExact=WrongMethodTypeException
invoke.widen=14
adapter.type=(int)long
adapter.exact=14
badAdapter=WrongMethodTypeException
~~~

**Analysis:**

- `exact.invokeExact(7L)` uses descriptor `(long)long`, matching the target; result is 14.
- `exact.invokeExact(7)` has a compile-time argument of type `int`, whereas the target requires `long`; `invokeExact` **does not auto-widen**, causing `WrongMethodTypeException`.
- `exact.invoke(7)` allows adaptation from `(int)long` to `(long)long`, so int → long widening is valid.
- `exact.asType((int)long)` creates **another handle** that an external caller can `invokeExact` with an int; the original handle remains `(long)long`.
- `asType((String)long)` cannot find a valid adapter to convert String to primitive long, so `WrongMethodTypeException` occurs when creating the adapter.

**Lesson:** The JVM has its own conversion rules; dispatcher policy is **a decision about data and application contract**. Validate/normalize before calling the handle. Do not let every coercion that `invoke` can perform accidentally become an allowed conversion on the public API.

### 7.1. `explicitCastArguments` Is Not a "Safer asType"

`MethodHandles.explicitCastArguments` has different conversion rules from `asType` and can support narrowing/explicit casting similar to a cast; misusing it can lose precision or produce unexpected results. Do not pick it just to "avoid WrongMethodTypeException"; if the contract forbids narrowing, keep the policy strict and check range/semantics when an explicit conversion exists.

Do not confuse the errors:

| Layer | Example | Error |
| --- | --- | --- |
| Route selection | `(String)Object` when only `(String)String` exists | `SIGNATURE_MISMATCH` (application) |
| Runtime value normalization | `Integer` into primitive `long` under STRICT | `ARGUMENT_TYPE` (application) |
| Wrong `invokeExact` call-site descriptor | int argument for `(long)long` handle | `WrongMethodTypeException` (JVM MethodHandle API) |
| Creating incompatible adapter | String argument to adapt to primitive long | `WrongMethodTypeException` |
| Runtime cast after adaptation | Actual Object is not the required subtype | Possible `ClassCastException` |
| Target method throws | `Math.addExact` overflow | `ArithmeticException`, from target |

If the dispatcher catches JVM exceptions indiscriminately without distinguishing steps, the caller will not know whether to fix the request, fix the registry, or fix the implementation.

## 8. Performance: Optimize What Is Necessary Without Sacrificing the Contract

### 8.1. Startup Work and Request Work

In the demo:

~~~text
Startup:
  Lookup.findStatic -> MethodHandle.type validation
  -> asType -> asSpreader -> immutable Map

Each request:
  Key lookup -> count check -> normalize
  -> prepared Object[] -> cached generic invoker.invokeExact
~~~

By building the adapter at startup:

- Avoids creating new `asType`/`asSpreader` instances per request.
- Detects target signature mismatches at registration.
- Exposes a stable call path of shape `(Object[])Object` to the runtime.

However, the generic invoker uses `Object[]`, boxed primitives, and dynamic type checks. On a high-volume hot path, the cost can be nontrivial. Do not claim that every `MethodHandle` is always faster than Reflection, or that the JIT always inlines every dynamic call.

### 8.2. Improvement Options When a Bottleneck Is Measured

| Technique | Potential benefit | Risks/conditions |
| --- | --- | --- |
| Cache `MethodHandle` and adapters after registration | Reduces repeated member lookup/conversion | Requires clear invalidation and loader lifecycle |
| Cache route lookup by `Key` | Reduces map lookup overhead on hot paths | Do not cache keys holding old classloaders indefinitely |
| Typed fast path using `invokeExact` at fixed call sites | Can reduce boxing/array allocations | Requires matching static compiler/type signatures |
| Guarded dispatch via `guardWithTest` / PIC | Optimizes common input types | Guard/fallback must preserve the same MethodType |
| `MutableCallSite`/`VolatileCallSite` for runtime relinking | Swaps target while keeping descriptor | Requires managing visibility/thread coordination |
| Generate code with JMH benchmarks | Measures real throughput/latency | Benchmarks need warmup, forks, proper result consumption |
| Avoid overly broad conversions | Reduces errors and data conversion cost | Requires explicit policy specification at API boundary |

If **auto-overload resolution** is genuinely needed, cache the result of the **specified algorithm** by signature/runtime type vector, while properly handling `null` and class loader identity; do not hash only class names.

### 8.3. Caches and Plugin Lifecycle

A registry holding `MethodHandle`s can retain references to the declaring class, bound receiver, classloader, and object graph. With plugin hot reload:

- Do not keep static caches unboundedly keyed by `Class<?>` from old loaders.
- Have a mechanism to retire routes, wait for/coordinate in-flight calls, and clean up resources.
- If swapping the registry by snapshot, an atomic swap of **an immutable registry** is usually easier to reason about than updating individual live entries.
- Do not let an in-flight request see half old state and half new state when transaction-level consistency is required.

## 9. Security, Ownership, and Module Boundaries

### 9.1. A MethodHandle Carries Access Privileges Matching Its Lookup

`Lookup.findStatic`, `findVirtual`, `findConstructor`, `findGetter`, etc. check member access when creating the handle. Once created, a handle can carry the capability to invoke a member that ordinary callers are not permitted to call directly under source access rules. Therefore **the registry is a capability boundary**.

Do not let request data directly choose arbitrary class/method names and then use a privileged `MethodHandles.Lookup` to create handles. Register **allowlisted operations** at startup from privileged code, and verify that each request is authorized to call the selected route.

### 9.2. What Contracts Are Allowed Across the Plugin Boundary?

If plugins A and B use two different class loaders, the same binary name of a parameter type does not guarantee the same runtime Class. Use public Java contracts in a shared module/loader, and pass data through defined DTOs/interfaces.

For callers over the network:

- Do not accept class name/sig strings from clients and reflect them into arbitrary `MethodType`s in the JVM.
- Define an independent **API schema**; map the validated schema to an **allowlisted route key** on the server.
- Separate identity authentication, authorization, content validation, and transport codec from target dispatch.
- Set rate limits, quotas, timeout/cancellation policies, and auditing for routes with side effects.

### 9.3. Null and Wrongly Typed Data Are Domain Issues

Java primitives do not accept null, whereas a `String` reference can accept null under the Java type system. **That does not mean the operation `format(null)` is valid in business logic.** In the demo, normalization can let a null reference through, and then the target may throw `NullPointerException`. If `format` requires non-null, validate the schema/domain **before** calling the target and return a dedicated code, such as `INVALID_VALUE`.

Similarly, `int times=-1` has the right type int, yet `String.repeat(-1)` throws `IllegalArgumentException`. This is **domain validation** or a target error, not `ARGUMENT_TYPE`; distinguish them when extending the API.

## 10. Concurrency, Consistency, and Errors When Swapping Routes

An immutable registry allows multiple threads to **read the route table** without synchronizing entry additions/removals. However:

- Targets may use static mutable fields, files, database connections, or non-thread-safe receiver objects.
- Conversion policy may need per-tenant or per-version configuration; do not use a global mutable static variable as a hidden policy.
- When swapping routes, safe publication is required. You can build a new map and swap a `volatile`/`AtomicReference`, or use a CallSite with proper semantics, instead of mutating a shared `HashMap` while requests are reading it.
- Whether a request that acquired the old route right before the swap is allowed or blocked must be governed by policy. Do not promise that every in-flight call switches to the new route instantaneously.
- Retries must distinguish **invalid requests** from **target execution failures**. A timed-out call may or may not have stopped at the target, so do not retry non-idempotent operations without a deduplication mechanism.

### 10.1. Error Envelope for External APIs

The demo uses `DispatchFailure` as an unchecked exception. For RPC/REST, an envelope can be defined:

~~~text
{
  "ok": false,
  "code": "ARGUMENT_TYPE",
  "operation": "sum",
  "requestId": "req-42",
  "message": "argument 0 must be long-compatible under STRICT"
}
~~~

This is **illustrative JSON**, not output from the Java demo. Do not expose full stack traces, classpaths, or secrets from `Throwable.getMessage()` to clients. Internal logs can retain `cause` and trace identifiers.

If compatibility tracking is needed, versioning error codes is as important as versioning route signatures. Do not silently change the meaning of `SIGNATURE_MISMATCH` from "route does not exist" to "conversion failed".

## 11. Comparison with Other Options

| Mechanism | What it provides | Should it be used for this dispatcher? |
| --- | --- | --- |
| `java.lang.reflect.Method.invoke` | Invokes a method after lookup, one level of argument checking/conversion and wrapping | Useful for simple admin tools; still needs registry/policy/error taxonomy |
| `MethodHandle.invokeExact` | Call by exact descriptor, favorable for typed hot paths | Use after building appropriate handles and validation |
| `MethodHandle.invoke` | Performs some adaptations like `asType` | Use when conversion semantics are valid by design |
| `asType` / `asSpreader` | Builds a generic typed adapter once | Suitable for a dispatcher receiving `Object[]` |
| `invokeWithArguments` | Calls a handle with a dynamic number of arguments | Convenient, but does not replace policy/schema |
| `ServiceLoader` | Discovers SPI providers | Can be used to **register routes**, does not solve invocation policy itself |
| `LambdaMetafactory` | Creates a function object implementing a functional interface from a direct impl handle under its own protocol | Not a generic dispatcher for arbitrary adapter handles |
| `ConstantCallSite` | Binds an immutable target by MethodType | Useful if a JVM/dynamic runtime needs a call site |
| `MutableCallSite`/`VolatileCallSite` | Relinks a target with the same MethodType | Useful for hot-swap/inline cache with a synchronization policy |
| `invokedynamic` | JVM instruction linking via bootstrap to a CallSite | For compilers/runtimes emitting bytecode; unnecessary for a typical Java registry |

**Avoid turning advanced tools into an end in themselves.** If the number of operations is small, a Java `switch` and typed interfaces can be easier to audit, faster to develop, and safer. Only add dynamic dispatch when operation registration, runtime type routing, or plugin integration is genuinely needed.

## 12. Real-World Design Scenarios

### 12.1. Dynamic Plugin Operations

A plugin publishes operations:

~~~text
"validate" : (Document,Context)ValidationResult
"transform": (Document,Options)Document
"emit"     : (Event)void
~~~

These are **illustrative signatures**, not built-in Java SE classes. The host only permits fixed operation IDs, uses contract classes in a shared loader, and registers direct MethodHandles from authorized providers. A runtime request must select the schema version, validate the payload, and then choose the exact signature.

If `Document` belongs to plugin A's loader while the host uses a `Document` defined by plugin B, both may share the same name yet **not be the same Class**; `MethodType.equals` prevents accidentally treating them as identical.

### 12.2. When Numeric Policy Needs Clear Bounds

A JSON source decodes the number `5` as an Integer while the target expects long. `WIDEN_INT_TO_LONG` may be allowed. However, another source sends `5.2` as a Double; it must not be converted to long by truncating the decimal and silently executing. If business logic genuinely has a conversion, you need to:

- Specify allowed source types;
- Check range/overflow/precision;
- Specify rounding mode (if decimals are used);
- Audit conversions;
- Test large/small bounds, NaN, and infinities if floating-point is involved.

Do not interpret the label "numeric widening" as permission to convert any number into any primitive.

### 12.3. Return Contract When Adding a Plugin Version

An old route `(String)String` does not automatically become a route `(String)Object` merely because `String <: Object`. If changing the return type in the API schema:

- Keep the old route for old clients or version explicitly.
- Register the new route with a MethodHandle/adapter **of the right type**.
- Test binary compatibility of callers, not just JSON shape.
- If using `CallSite`, **you cannot change the MethodType of the same CallSite with `setTarget`**; the site's signature must be preserved.

## 13. Debugging a Dynamic Dispatcher Error

### 13.1. Ordered Checklist

1. **Request:** is the operation on the allowlist? which version/descriptor was selected for the route?
2. **Registry:** does `Key` match the exact `MethodType`? which `Lookup` created the MethodHandle? does `handle.type()` equal the key signature?
3. **Arity:** does `args.length` equal the parameter count? did the caller pass an `Object[]` or pass a single array into varargs?
4. **Types:** is each expected parameter primitive or reference? what is the runtime value class? is `null` allowed? which policy is active?
5. **Conversion:** was it normalized to the **exact boxed type** for a primitive target? is there implicit parsing/narrowing?
6. **Adapter:** from what type were `asType`/`asSpreader` built? is the final generic invoker `(Object[])Object`?
7. **Invocation:** is the error from method handle linkage/call site or from the target? is `cause` preserved?
8. **Concurrency:** is the registry immutable or being mutated? does the target have shared/thread-safe state? could loader lifecycle cause a stale cache?
9. **Security:** is the caller authorized for the operation? is there sensitive data in logs/exceptions or arguments?
10. **Benchmark:** if performance is needed, did you use JMH with warmup/forks, verify results/side effects, and measure the distribution of request types?

### 13.2. What Action Corresponds to Each Error Code in the Demo?

| Code | Who should handle it | First action |
| --- | --- | --- |
| `INVALID_REQUEST` | Caller/API gateway | Fix request structure, do not retry as-is |
| `UNKNOWN_OPERATION` | Client/contract owner | Check operation ID, version, allowlist |
| `SIGNATURE_MISMATCH` | Client and provider owner | Verify registered exact MethodType/ABI |
| `ARITY_MISMATCH` | Client/codec layer | Check positional argument count |
| `ARGUMENT_TYPE` | Client/validation layer | Check runtime data types and conversion policy |
| `TARGET_FAILURE` | Owner of the target method | Inspect root cause, error domain, idempotency/retry policy |

Do not apply one generic retry policy across the whole table. Invalid requests usually do not resolve themselves on retry; target failures may or may not be retryable depending on business logic.

## 14. Practice Exercises

1. **Overload selection:** Why can both `"format"` with `(String)String` and `(String,int)String` reside in the demo's Map? What happens if it is keyed only by name?
2. **Return type:** Change the requested signature `(String)String` to `(String)Object`, still passing a String. Why does `SIGNATURE_MISMATCH` occur before invocation?
3. **STRICT versus widening:** Given route `sum(long,long)long` and values `[Integer(2),Long(5)]`, predict which error/value `STRICT` and `WIDEN_INT_TO_LONG` return.
4. **Primitive null:** Why is `Long.valueOf(2)` accepted for `long`, whereas `null` is not? What if the parameter type is `Long.class`?
5. **Target failure:** Given `format("ha",-1)`. The arguments still match `(String,int)String`, so should the error be treated as `ARGUMENT_TYPE`, domain validation, or `TARGET_FAILURE` under the current demo?
6. **Interruption:** Replace the target with a blocking method that can throw `InterruptedException`. Propose a policy that preserves the interrupt flag, cancellation, and root cause.
7. **Registration failure:** Register `Key("sum",(long,long)long)` twice; how should the `add` helper handle it? Why not choose "last registered wins"?
8. **Adapter boundary:** Why does the generic invoker have `(Object[])Object` even though target `sum` is `(long,long)long`? Where in the pipeline is `STRICT` enforced?
9. **Direct invocation:** Why does `invokeExact(7)` on target `(long)long` fail, while `invoke(7)` can succeed? Does this allow the dispatcher to drop its validation policy?
10. **Plugin security:** A user sends the method name `deleteAllUsers` through an external API. Why should you not use a privileged lookup to reflect that method? Design a route allowlist and authorization.
11. **Hot reload:** Can two classes with the same name in two plugin loaders produce equal `MethodType`s when the parameter type is a loader-private class? When replacing a plugin, how must caches and lifecycle be handled?
12. **Benchmark:** Design an experiment comparing Reflection, generic MethodHandle adapter, and typed direct invoke for the same operation, with warmup, forks, and production-representative data ratios.

## 15. Summary

A reliable dynamic dispatcher needs to **separate three layers**:

1. **Route selection by static contract:** `(operation, MethodType)` and exact signature.
2. **Data conversion by application policy:** validate arity, null, primitive wrappers, reference assignability, and whitelist only intentional conversions.
3. **Execution and structured error reporting:** cached MethodHandle adapters, phase-based stable error codes, preserved target causes, without conflating configuration errors, data errors, and JVM errors.

The demo uses `Map.copyOf` and a generic `(Object[])Object` invoker to illustrate the mechanism accurately. For a production system, add authorization, schema/domain validation, thread safety, class loader lifecycle, timeout/cancellation, observability, and benchmarks. **The JVM's type adaptation capabilities do not replace the API's conversion rules.**

## Official References

- [Java SE 17 — `MethodHandle`: `invokeExact`, `invoke`, `asType`, `invokeWithArguments`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html)
- [Java SE 17 — `MethodType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html)
- [Java SE 17 — `MethodHandles`: `asSpreader`, `explicitCastArguments`, `guardWithTest`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html)
- [Java SE 17 — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html)
- [Java SE 17 — `MutableCallSite` and `syncAll`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MutableCallSite.html)
- [Java SE 17 — `VolatileCallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VolatileCallSite.html)
- [JVM Specification 17 — `invokevirtual` / `invokedynamic`](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html)
