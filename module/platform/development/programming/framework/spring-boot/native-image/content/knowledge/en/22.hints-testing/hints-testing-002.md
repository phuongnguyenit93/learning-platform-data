# Testing Reflection for Constructors, Methods, and Fields Actually Used

## 1. Why test each reflection operation individually?

GraalVM Native Image analyzes an application at build time. Constructors, methods, or fields accessed via Java Reflection might not be fully inferred from the static call graph. Spring Runtime Hints describe the members an application needs to access when running natively.

A test that merely verifies a class has a reflection hint is not enough. The code might call a specific constructor, invoke a method with a particular signature, or read and write a specific field. Tests must verify the exact member and the exact access mode.

This lesson belongs to the **Hints Testing** chapter of the **SPRING_BOOT_NATIVE_IMAGE** module. Its goal is to test the constructors, methods, and fields the code actually uses; distinguish introspection from invocation; catch missing, mismatched-signature, or overly broad hints; and verify the results via Spring AOT and a native executable.

## 2. Start from the code performing reflection

Suppose a library needs to instantiate `CredentialEnvelope`, call a token normalization method, and read/write the `token` field:

```java
package com.example.security;

public class CredentialEnvelope {

    private String token;

    public CredentialEnvelope() {
    }

    public CredentialEnvelope(String token) {
        this.token = token;
    }

    public String normalize(String prefix) {
        return prefix + token.trim();
    }

    public String normalize(String prefix, boolean uppercase) {
        String value = prefix + token.trim();
        return uppercase ? value.toUpperCase() : value;
    }
}
```

The component using reflection:

```java
package com.example.security;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public class CredentialInspector {

    public CredentialEnvelope create(String token) throws Exception {
        Constructor<CredentialEnvelope> constructor =
            CredentialEnvelope.class.getDeclaredConstructor(String.class);
        return constructor.newInstance(token);
    }

    public String normalize(CredentialEnvelope target, String prefix)
            throws Exception {
        Method method = CredentialEnvelope.class.getDeclaredMethod(
            "normalize", String.class
        );
        return (String) method.invoke(target, prefix);
    }

    public String readToken(CredentialEnvelope target) throws Exception {
        Field field = CredentialEnvelope.class.getDeclaredField("token");
        field.setAccessible(true);
        return (String) field.get(target);
    }

    public void replaceToken(CredentialEnvelope target, String value)
            throws Exception {
        Field field = CredentialEnvelope.class.getDeclaredField("token");
        field.setAccessible(true);
        field.set(target, value);
    }
}
```

Reflection requirements derived from the code:

| Operation | Member | Mode |
| --- | --- | --- |
| Get constructor with `String` parameter and call `newInstance` | `CredentialEnvelope(String)` | Invoke |
| Get `normalize` with one `String` parameter and call `invoke` | `normalize(String)` | Invoke |
| Get `token` field and call `get` | `token` | Field access |
| Get `token` field and call `set` | `token` | Field access for writing |

The overloaded method `normalize(String, boolean)` is not called in the example, so it does not need to be registered simply because it shares a name with the method being used.

## 3. Distinguishing introspection and invocation

Spring represents constructor and method reflection requirements using `ExecutableMode`:

- `INTROSPECT`: metadata lookup is needed, such as reading method or constructor information.
- `INVOKE`: calling the executable is needed, such as `Constructor.newInstance()` or `Method.invoke()`.

Example of only introspecting a method:

```java
Method method = CredentialEnvelope.class.getDeclaredMethod(
    "normalize", String.class
);

String methodName = method.getName();
Class<?>[] parameterTypes = method.getParameterTypes();
```

If the code only queries metadata without calling the method, an `INTROSPECT` hint can satisfy the requirement. If the code calls `method.invoke(...)`, an `INVOKE` hint is required. If the code both queries metadata and invokes it, describe both activities accurately.

Do not use an introspection assertion as a substitute for an invocation assertion when the code actually invokes reflection.

## 4. Registering the exact constructor, method, and field

A `RuntimeHintsRegistrar` can describe the three members used in the example:

```java
package com.example.security;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

import org.springframework.aot.hint.ExecutableMode;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public final class CredentialReflectionHints
        implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        try {
            Constructor<CredentialEnvelope> constructor =
                CredentialEnvelope.class.getDeclaredConstructor(String.class);

            Method normalize = CredentialEnvelope.class.getDeclaredMethod(
                "normalize", String.class
            );

            Field token = CredentialEnvelope.class.getDeclaredField("token");

            hints.reflection().registerConstructor(
                constructor, ExecutableMode.INVOKE
            );
            hints.reflection().registerMethod(
                normalize, ExecutableMode.INVOKE
            );
            hints.reflection().registerField(token);
        }
        catch (NoSuchMethodException | NoSuchFieldException ex) {
            throw new IllegalStateException(
                "Reflection member definition changed", ex
            );
        }
    }
}
```

This registration approach has the following characteristics:

1. Selects the constructor with the exact `String` parameter type.
2. Selects the method overload with the exact `String` parameter type.
3. Selects the field by name `token`.
4. Uses `INVOKE` because the constructor and method are actually called.
5. Registers the field because the code reads and writes it via reflection.

With Spring Framework 6.2.x, `registerField(Field)` registers a field that requires reflection access. The same field hint applies to both `Field.get()` and `Field.set()` operations performed by the code. Register only the fields that the library actually accesses; do not open all declared fields if only a few are needed.

### 4.1. When to use MemberCategory?

Spring also supports registering by member categories, such as `INVOKE_PUBLIC_CONSTRUCTORS`, `INVOKE_DECLARED_METHODS`, or `DECLARED_FIELDS`:

```java
hints.reflection().registerType(
    CredentialEnvelope.class,
    MemberCategory.INVOKE_DECLARED_CONSTRUCTORS,
    MemberCategory.INVOKE_DECLARED_METHODS,
    MemberCategory.DECLARED_FIELDS
);
```

This is broader in scope than registering a specific constructor and a specific method. Only use a member category when the code truly needs that entire category. Do not add `INVOKE_DECLARED_METHODS` just to fix an error on a single method.

## 5. Testing a constructor with RuntimeHintsPredicates

`RuntimeHintsPredicates.reflection()` can check a specific constructor. Obtain the exact constructor that the code uses:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.lang.reflect.Constructor;

import org.junit.jupiter.api.Test;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

class CredentialReflectionHintsTests {

    @Test
    void registersConstructorThatIsActuallyInvoked() throws Exception {
        RuntimeHints hints = new RuntimeHints();

        new CredentialReflectionHints().registerHints(
            hints, getClass().getClassLoader()
        );

        Constructor<CredentialEnvelope> constructor =
            CredentialEnvelope.class.getDeclaredConstructor(String.class);

        assertThat(
            RuntimeHintsPredicates.reflection()
                .onConstructor(constructor)
                .invoke()
        ).accepts(hints);
    }
}
```

`onConstructor(constructor)` selects the exact constructor; `invoke()` requires the hint to permit invocation. If the registrar only registered introspection, this assertion must fail.

You can check that another constructor is not used:

```java
Constructor<CredentialEnvelope> noArg =
    CredentialEnvelope.class.getDeclaredConstructor();

assertThat(
    RuntimeHintsPredicates.reflection()
        .onConstructor(noArg)
        .invoke()
).rejects(hints);
```

This negative assertion example assumes the class has a no-arg constructor. If it does not, pick an existing constructor that is not part of the library's operations.

## 6. Testing methods, including overloads

The `onMethod(Class, String)` predicate is suitable when a method name uniquely identifies a single method. With overloads, pass the `Method` object obtained via `getDeclaredMethod(...)` to avoid testing the wrong signature:

```java
@Test
void registersOnlyTheNormalizeOverloadUsedByTheLibrary()
        throws Exception {

    RuntimeHints hints = new RuntimeHints();
    new CredentialReflectionHints().registerHints(
        hints, getClass().getClassLoader()
    );

    Method usedMethod = CredentialEnvelope.class.getDeclaredMethod(
        "normalize", String.class
    );

    Method unusedOverload = CredentialEnvelope.class.getDeclaredMethod(
        "normalize", String.class, boolean.class
    );

    assertThat(
        RuntimeHintsPredicates.reflection()
            .onMethod(usedMethod)
            .invoke()
    ).accepts(hints);

    assertThat(
        RuntimeHintsPredicates.reflection()
            .onMethod(unusedOverload)
            .invoke()
    ).rejects(hints);
}
```

The `Method` object carries both the declaring class and parameter types, so the test distinguishes `normalize(String)` from `normalize(String, boolean)`.

### 6.1. Checking introspection separately

If a component only needs to look up method metadata, check the corresponding mode:

```java
assertThat(
    RuntimeHintsPredicates.reflection()
        .onMethod(usedMethod)
        .introspect()
).accepts(hints);
```

Do not use this assertion in place of `invoke()` when the code calls `Method.invoke()`.

## 7. Testing field access

With Spring Framework 6.2.x, you can check a field using `onField(Class, String)`:

```java
@Test
void registersTokenField() {
    RuntimeHints hints = new RuntimeHints();

    new CredentialReflectionHints().registerHints(
        hints, getClass().getClassLoader()
    );

    assertThat(
        RuntimeHintsPredicates.reflection()
            .onField(CredentialEnvelope.class, "token")
    ).accepts(hints);
}
```

This predicate verifies that the field is registered. You can inspect the list of field hints directly on `TypeHint`:

```java
import org.springframework.aot.hint.TypeHint;

@Test
void tokenFieldIsRegistered() {
    RuntimeHints hints = new RuntimeHints();

    new CredentialReflectionHints().registerHints(
        hints, getClass().getClassLoader()
    );

    TypeHint typeHint =
        hints.reflection().getTypeHint(CredentialEnvelope.class);

    assertThat(typeHint).isNotNull();

    assertThat(typeHint.fields()
        .anyMatch(field -> field.getName().equals("token")))
        .isTrue();
}
```

In this example, the same `token` field is read via `Field.get()` and written via `Field.set()`. The test verifies that the field hint is present; the integration test in a later section verifies that both operations actually run in the native executable.

### 7.1. Inherited fields

If a field is declared in a superclass, the hint must be attached to the class that actually declares that field:

```java
Field inheritedField =
    BaseCredential.class.getDeclaredField("tenantId");

hints.reflection().registerField(
    inheritedField
);
```

Do not assume a subclass owns every field an object can access. An inherited field still has its own declaring class.

## 8. Verifying exact hints instead of opening the entire type

A passing predicate proves the operation is supported, but does not by itself prove the registrar is minimal. If the registrar uses `MemberCategory.INVOKE_DECLARED_METHODS`, a predicate for an unused method can still return `true` because the category hint covers that method.

When you want to keep reflection scope narrow:

- Check the specific constructor.
- Check the specific method using a `Method` object.
- Check the specific field.
- Check the specific field instead of registering all fields of the type.
- Check `TypeHint.getMemberCategories()` to catch unexpectedly broad member categories.
- Include negative assertions for an existing member that is not used.

Example verifying that a type does not open all declared methods:

```java
TypeHint typeHint =
    hints.reflection().getTypeHint(CredentialEnvelope.class);

assertThat(typeHint).isNotNull();
assertThat(typeHint.getMemberCategories())
    .doesNotContain(MemberCategory.INVOKE_DECLARED_METHODS);
```

If a project intentionally opens an entire group of methods, this assertion is inappropriate. In that case, document the reason clearly and test that the opened scope is part of the runtime contract.

Do not turn negative assertions into a rigid rule for every library. There are cases where a serializer or framework needs many members. What needs to be controlled is proportionality between hint scope and actual behavior.

## 9. Testing the registrar with RuntimeHintsPredicates

A single test can verify all three member types in the same method:

```java
@Test
void registersOnlyTheReflectionOperationsUsed() throws Exception {
    RuntimeHints hints = new RuntimeHints();

    new CredentialReflectionHints().registerHints(
        hints, getClass().getClassLoader()
    );

    Constructor<CredentialEnvelope> constructor =
        CredentialEnvelope.class.getDeclaredConstructor(String.class);

    Method method = CredentialEnvelope.class.getDeclaredMethod(
        "normalize", String.class
    );

    Field field = CredentialEnvelope.class.getDeclaredField("token");

    assertThat(RuntimeHintsPredicates.reflection()
        .onConstructor(constructor).invoke()).accepts(hints);

    assertThat(RuntimeHintsPredicates.reflection()
        .onMethod(method).invoke()).accepts(hints);

    assertThat(RuntimeHintsPredicates.reflection()
        .onField(field)).accepts(hints);
}
```

These predicates verify the in-memory `RuntimeHints` contents. They are useful for unit testing the registrar, but do not prove that Spring AOT discovered the registrar or that the native executable can actually perform the operation.

## 10. Distinguishing the three testing layers

| Testing layer | What needs to be proven | How to execute |
| --- | --- | --- |
| Registrar unit test | Constructor/method/field hints are contributed properly | Create `RuntimeHints`, call registrar, check predicates |
| AOT integration test | Spring discovers the registrar/annotation and merges hints | Run AOT processing on `ApplicationContext` or consumer app |
| Native executable test | Reflection operations work in the actual binary | Build native, run tests/endpoints performing constructor, method, and field access |

A unit test can pass while the registrar is not imported into the `ApplicationContext`. Likewise, AOT metadata may be generated while native tests have not yet hit an overloaded method or a field used only on a rare branch.

Therefore, native tests must exercise the exact code paths that the library or application intends to support.

## 11. Running tests on the native executable

You can write an integration test that calls the service performing reflection:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

@SpringBootTest
@Import(CredentialInspector.class)
class CredentialNativeIntegrationTests {

    @Autowired
    CredentialInspector inspector;

    @Test
    void createsInvokesAndAccessesCredentialReflectively() throws Exception {
        CredentialEnvelope envelope = inspector.create("  abc  ");

        assertThat(inspector.normalize(envelope, "Bearer "))
            .isEqualTo("Bearer abc");

        assertThat(inspector.readToken(envelope))
            .isEqualTo("  abc  ");

        inspector.replaceToken(envelope, "rotated");

        assertThat(inspector.readToken(envelope))
            .isEqualTo("rotated");
    }
}
```

This test exercises constructor invocation, method invocation, field read, and field write. When running native integration tests, make sure the test actually executes inside the native executable or the corresponding native test harness. Running the same test on the JVM only verifies JVM behavior.

With Maven or Gradle, native test configuration depends on Native Build Tools and plugin versions. Use the project's corresponding native test task/goal and inspect the logs to confirm the test process is the native executable.

### 11.1. Testing over HTTP

If reflection is triggered by a request, send requests through the native application rather than only calling the service directly. This also verifies Spring AOT, dependency injection, HTTP message conversion, and business code paths together.

Make sure requests trigger every operation. If a field is only written when handling a rare event type, create a dedicated test for that event. Do not merely check that an endpoint returns HTTP 200 without verifying the exact field/method outcome.

## 12. Testing patterns that easily lead to false conclusions

| Test or configuration | Why it is insufficient | How to improve |
| --- | --- | --- |
| Asserting only `onType(MyType.class)` | Does not prove specific constructor/method/field has a hint | Assert each member actually used |
| Checking only `INVOKE_DECLARED_METHODS` | May expose every method even if only one is needed | Use `registerMethod` with the exact `Method` |
| Selecting method by name when overloaded | Predicate may not uniquely identify the method | Resolve `Method` using parameter types |
| Asserting only constructor introspection | Actual code calls `newInstance` | Assert `invoke()` |
| Asserting only that field hint exists | Does not prove `Field.get()` and `Field.set()` work in native | Run integration test performing both field read and write |
| Testing only the registrar directly | Does not prove the AOT engine finds the registrar | Add an AOT integration test |
| Running only JVM tests | JVM can access reflection without native registration | Run native executable tests |
| Using `setAccessible(true)` in tests without checking hints | JVM tests do not reflect native metadata | Check field hints and native behavior |
| Exercising only one request branch | May miss members used in other branches | Cover each actual operation and subtype |

## 13. Predicate API differences between Spring Framework 6 and 7

In Spring Framework 6.x, the APIs commonly used in this lesson are:

```java
RuntimeHintsPredicates.reflection().onConstructor(constructor).invoke();
RuntimeHintsPredicates.reflection().onMethod(method).invoke();
RuntimeHintsPredicates.reflection().onField(type, "fieldName");
```

Spring Framework 7.0 deprecates several older predicates in favor of names that describe the operation more clearly:

| Spring Framework 6.x | Spring Framework 7.x |
| --- | --- |
| `onConstructor(constructor).invoke()` | `onConstructorInvocation(constructor)` |
| `onMethod(method).invoke()` | `onMethodInvocation(method)` |
| `onField(type, "name")` | `onFieldAccess(type, "name")` |

When writing tests, use the API matching the Spring Framework baseline your project compiles against. Do not copy tests using 7.x APIs into a Spring 6.x project or vice versa without checking dependencies.

## 14. Hands-on exercise: testing minimal reflection hints

**Context:** The `CredentialInspector` library uses reflection to instantiate `CredentialEnvelope(String)`, call `normalize(String)`, and read/write the `token` field.

**Steps:**

1. Create the `CredentialEnvelope` model with a parameterized constructor, two method overloads, and a private field.
2. Write reflection code that calls one specific constructor, one method overload, reads the field, and writes the field.
3. Write a registrar that registers only those members.
4. Write a unit test using `RuntimeHintsPredicates` to verify constructor invocation.
5. Verify method invocation using a `Method` object resolved with specific parameter types.
6. Verify the field hint using `RuntimeHintsPredicates` and `TypeHint.fields()`.
7. Add negative assertions for the uncalled method overload and the unused constructor.
8. Verify that the type is not broadened to all declared methods unnecessarily.
9. Run AOT processing and verify that the registrar is discovered.
10. Build the native executable and run a test triggering constructor, method, field read, and field write.

**Acceptance criteria:**

- Tests select the exact constructor by parameter types.
- Tests distinguish method overloads.
- Field tests verify the exact field is registered; native integration tests verify both read and write if the code needs both operations.
- `INTROSPECT` and `INVOKE` are used appropriately.
- Negative assertions detect hints for unrequested members.
- AOT integration tests confirm the registrar is discovered.
- The native executable performs all supported reflection operations.

## 15. Summary

Testing reflection hints should start from the actual operations performed by the code. Use `Constructor` and `Method` objects resolved with full signatures to test the right overload; use field predicates and `TypeHint.fields()` to confirm field registration. Distinguish `INTROSPECT` from `INVOKE`, and avoid opening an entire member category if the application only needs a few members.

`RuntimeHintsPredicates` is a unit testing tool for the registrar. To prove that the native application works, AOT integration tests and native executable tests that trigger the exact constructors, methods, and fields used by the application are still required.
