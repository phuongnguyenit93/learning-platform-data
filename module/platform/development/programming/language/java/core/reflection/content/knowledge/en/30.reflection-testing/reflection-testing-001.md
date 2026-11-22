# Testing Reflection Fixtures with `public`, `protected`, Package-Private, and `private` Members

When building Reflection-based Java tools (mappers, serializers, dependency injection, API doc generators, or scanners), **merely seeing a member in metadata does not mean you are permitted to read, invoke, or instantiate through that member**. A good fixture must intentionally create all four Java access levels, place test code **in both the same package and a different package**, and verify actual behavior rather than guessing from modifier names.

This lesson designs a Java 17+ fixture with **fields, methods, and constructors** at all four levels: `public`, `protected`, **package-private** (no access modifier), and `private`. We observe the difference between `getFields()/getMethods()` and `getDeclaredFields()/getDeclaredMethods()`, and test permissions using `AccessibleObject.canAccess(...)`, `trySetAccessible()`, and rules for subclasses/JPMS.

## 1. The Four Access Levels to Test in a Fixture

| Member modifier | Own class/nestmate allowed | Another class in same package | Subclass in different package | Unrelated class in different package |
| --- | --- | --- | --- | --- |
| `public` | Yes | Yes | Yes | Yes, if the target class/package is also visible |
| `protected` | Yes | Yes | Yes, **with the receiver rule when in a different package** | No |
| *package-private* (no modifier) | Yes | Yes | Not merely because it is a subclass | No |
| `private` | Yes, under Java nestmate rules | Not merely because it is in the same package | Not merely because of inheritance | No |

The table above describes the permissions of **normal Java code**, before using an authorized reflective access suppression mechanism. You must also check the accessibility of the **enclosing class** and module relationships (`exports`/`opens`). `public` on a member inside a non-public class or an unexported package does not automatically create a system-wide public API.

- **Protected in a different package:** a subclass is allowed to access a `protected` instance member through a receiver whose type is that subclass itself (or an appropriate subtype). From that subclass, accessing the same member on an ordinary `BaseFixture` instance may still be rejected.
- **Package-private:** depends on the **runtime package**. When Java has different class loaders/modules, having the same package name string in source files is not enough to establish the same runtime package.
- **Private and nestmates:** nested classes in the same nest have their own private access mechanism. To test private failure cleanly, the example uses **three top-level classes in separate files**, rather than putting the entire fixture inside a nested class of the test.
- **Constructor:** also has four permission levels, but is not inherited. Testing constructors requires `getDeclaredConstructor(...)` or `getConstructor(...)`, without applying override rules.

## 2. Identify the Testing Question Before Choosing an API

Reflection has two distinct activities: **looking up metadata** and **using a member**.

| API | What does it tell you? | What not to infer |
| --- | --- | --- |
| `Class.getDeclaredField(name)` | Finds a directly declared field, including public/non-public | Does not prove the caller can read/write the field |
| `Class.getFields()` | Lists matching public fields, including inherited fields | Not a complete list of all private fields in the hierarchy |
| `Class.getDeclaredMethod(name, parameterTypes...)` | Finds the exact method declared by the class, regardless of modifier | Does not prove permission to `invoke` |
| `Class.getMethods()` | Matching public methods, accounting for inheritance/interfaces | Does not return all non-public methods |
| `Class.getDeclaredConstructors()` | Constructors declared by the class, of all modifier levels | No inherited constructors |
| `Class.getConstructor(parameterTypes...)` | Finds a public constructor by signature | Private/protected/package-private constructors do not appear |
| `Field.get`/`set`, `Method.invoke`, `Constructor.newInstance` | Performs the operation, checking access and invocation conditions | Do not rely solely on having found the metadata |
| `AccessibleObject.canAccess(receiver)` | Asks whether the member can be used at the current caller site, considering accessible state | Does not change permissions itself; for instance fields/methods requires a suitable receiver; for static members/constructors requires `null` |
| `AccessibleObject.trySetAccessible()` | Attempts to enable the flag to suppress Java access checks where permitted | May return `false` if blocked by module encapsulation; does not grant unconditional permission |

**Practical note:** `getDeclaredFields()` and Reflection APIs returning arrays **do not guarantee ordering**. When printing results for tests/snapshot comparisons, call `sorted()`; otherwise, tests will depend on an arbitrary environment order rather than the meaning of access modifiers.

`canAccess` is not suitable as a generic function taking `null` for every member: for instance fields and instance methods, you must pass a compatible receiver; constructors and static members use `null`. If the receiver is the wrong kind, the API may throw `IllegalArgumentException`. It also checks against the **actual caller**, so the same `Field` can yield different results when `canAccess` is called from a different test class.

## 3. Java 17+ Fixture: Three Files, Two Packages, and Multiple Caller Contexts

Directory structure:

~~~text
fixture/
  BaseFixture.java
  SamePackageProbe.java
client/
  FixtureAccessDemo.java
~~~

These three classes are compiled and run on the **classpath/unnamed module** to isolate modifier/package rules before testing named modules. The same package name in two source files loaded by the same class loader is treated as the same runtime package.

### 3.1. `fixture/BaseFixture.java`

Defines all four access levels for **fields, constructors, and methods**:

~~~java
package fixture;

public class BaseFixture {
    public int publicField = 10;
    protected int protectedField = 20;
    int packageField = 30;
    private int privateField = 40;

    public BaseFixture() {}
    protected BaseFixture(String text) {}
    BaseFixture(int number) {}
    private BaseFixture(boolean value) {}

    public String publicMethod() { return "public"; }
    protected String protectedMethod() { return "protected"; }
    String packageMethod() { return "package"; }
    private String privateMethod() { return "private"; }
}
~~~

- Having no modifier keyword before `packageField`/`packageMethod`/`BaseFixture(int)` means **package-private**, not `protected`.
- `privateField` still exists in `BaseFixture`'s metadata; the fact that an external test cannot access it directly does not mean this field is "completely hidden" from Reflection.
- The constructors intentionally use different parameter types. Since Java does not allow two constructors with the same parameter signature differing only by modifier, that is how to build a valid fixture with all four permission levels.

### 3.2. `fixture/SamePackageProbe.java`

A caller in **a different class, same package** checks the fields and constructor:

~~~java
package fixture;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;

public class SamePackageProbe {
    public static void run() throws Exception {
        BaseFixture base = new BaseFixture();
        for (String name : new String[]{
                "publicField", "protectedField", "packageField", "privateField"}) {
            Field f = BaseFixture.class.getDeclaredField(name);
            System.out.println("same-package " + name + ": " + f.canAccess(base));
        }
        Constructor<?> ctor = BaseFixture.class.getDeclaredConstructor(int.class);
        System.out.println("same-package constructor: " + ctor.canAccess(null));
    }
}
~~~

Expected observation: `public`, `protected`, and package-private are all `true`, while `private` returns `false`. `SamePackageProbe` is not a nestmate of `BaseFixture`; being in the same package is not enough for private access.

`getDeclaredConstructor(int.class)` finds the package-private constructor. `ctor.canAccess(null)` returns `true` because the caller `SamePackageProbe` belongs to the same runtime package. This is a constructor permission check, where the receiver must be `null`.

### 3.3. `client/FixtureAccessDemo.java`

A caller in a **different package** that is also a subclass, showing the receiver constraint of `protected`:

~~~java
package client;

import fixture.BaseFixture;
import fixture.SamePackageProbe;
import java.lang.reflect.Field;
import java.util.Arrays;
import java.util.stream.Collectors;

public class FixtureAccessDemo extends BaseFixture {
    private void checkProtected() throws Exception {
        Field f = BaseFixture.class.getDeclaredField("protectedField");
        System.out.println("subclass receiver protected: " + f.canAccess(this));
        System.out.println("base receiver protected: " +
                f.canAccess(new BaseFixture()));
    }

    public static void main(String[] args) throws Exception {
        BaseFixture base = new BaseFixture();

        System.out.println("declared fields: " +
                Arrays.stream(BaseFixture.class.getDeclaredFields())
                        .map(Field::getName).sorted()
                        .collect(Collectors.joining(", ")));
        System.out.println("public fields: " +
                Arrays.stream(BaseFixture.class.getFields())
                        .filter(f -> f.getDeclaringClass() == BaseFixture.class)
                        .map(Field::getName).sorted()
                        .collect(Collectors.joining(", ")));

        for (String name : new String[]{
                "publicField", "protectedField", "packageField", "privateField"}) {
            Field f = BaseFixture.class.getDeclaredField(name);
            System.out.println("client " + name + ": " + f.canAccess(base));
        }

        System.out.println("public method: " +
                BaseFixture.class.getMethod("publicMethod").invoke(base));
        try {
            BaseFixture.class.getMethod("privateMethod");
            System.out.println("unexpected lookup");
        } catch (NoSuchMethodException expected) {
            System.out.println("getMethod(private): NoSuchMethodException");
        }

        SamePackageProbe.run();
        new FixtureAccessDemo().checkProtected();

        Field privateField = BaseFixture.class.getDeclaredField("privateField");
        System.out.println("private trySetAccessible: " +
                privateField.trySetAccessible());
        System.out.println("private field value: " + privateField.getInt(base));
    }
}
~~~

Note that `FixtureAccessDemo` is a subclass of `BaseFixture`, yet the loop calling `canAccess(base)` passes a **receiver of `BaseFixture` itself**, not of `FixtureAccessDemo`. This is intentional to test the case where `protected` is denied across packages. In `checkProtected()`, the receiver `this` is an instance of the subclass, so the `protected` check succeeds.

### 3.4. Compile, Run, and Verify stdout

From the directory containing the two folders `fixture` and `client`, create an `out` directory and run:

~~~bash
mkdir out
javac --release 17 -d out fixture/BaseFixture.java fixture/SamePackageProbe.java client/FixtureAccessDemo.java
java -cp out client.FixtureAccessDemo
~~~

Verified output with JDK `--release 17`:

~~~text
declared fields: packageField, privateField, protectedField, publicField
public fields: publicField
client publicField: true
client protectedField: false
client packageField: false
client privateField: false
public method: public
getMethod(private): NoSuchMethodException
same-package publicField: true
same-package protectedField: true
same-package packageField: true
same-package privateField: false
same-package constructor: true
subclass receiver protected: true
base receiver protected: false
private trySetAccessible: true
private field value: 40
~~~

**Explanation of key results:**

1. `declared fields` lists all four fields, because `getDeclaredFields()` does not filter by `public`. `public fields` only has `publicField` in the fixture (filtered by `getDeclaringClass()`).
2. In the `client` loop, `canAccess(base)` is only true for `publicField`. The other three fields do not automatically become accessible just because the `Field` was obtained from `getDeclaredField`.
3. `BaseFixture.class.getMethod("privateMethod")` does not find it because this API only searches for public methods: it throws **`NoSuchMethodException`**. Using `getDeclaredMethod("privateMethod")` finds the metadata, while `invoke` still requires permission.
4. `SamePackageProbe` can see `protectedField` and `packageField`. `privateField` is still denied because the two top-level classes are not nestmates.
5. `subclass receiver protected: true` while `base receiver protected: false` proves the special receiver condition for `protected` when the caller is a subclass in a different package.
6. `private trySetAccessible: true` is the result in this example running **on the classpath/unnamed module**. `trySetAccessible()` can return `false` in a named-module application if the target package does not `opens` to the caller module. Do not use the `true` result here to claim Java always allows bypassing private access.
7. After `trySetAccessible()` succeeds, `getInt(base)` can read `privateField = 40`. This is an explicit operation requesting to suppress access checks in a permitted context, distinct from the default access check via `canAccess`.

## 4. Extending the Same Fixture to Test Methods and Constructors

For methods, use the same names from `BaseFixture`:

| Method | Found with `getDeclaredMethod(...)` | Found with `getMethod(...)` | Default invocation permission from another package |
| --- | --- | --- | --- |
| `publicMethod()` | Yes | Yes | Allowed, if the target class/package is visible |
| `protectedMethod()` | Yes | No with this API on a fixture with only this protected member | Depends on subclass and receiver |
| `packageMethod()` | Yes | No | No |
| `privateMethod()` | Yes | No | No |

If you want to test **invocation permission** instead of lookup capability, first retrieve `Method m = BaseFixture.class.getDeclaredMethod("privateMethod")`, then call `m.canAccess(base)` or `m.invoke(base)`; when invocation is not allowed, it throws `IllegalAccessException`. `NoSuchMethodException` belongs to the step of **looking up the method by API/signature**. Do not conflate these two causes into the same error.

For constructors:

- `BaseFixture.class.getConstructor()` finds the public no-arg constructor.
- `BaseFixture.class.getDeclaredConstructor(String.class)` finds the `protected` constructor.
- `BaseFixture.class.getDeclaredConstructor(int.class)` finds the package-private constructor.
- `BaseFixture.class.getDeclaredConstructor(boolean.class)` finds the `private` constructor.
- `BaseFixture.class.getConstructor(boolean.class)` throws `NoSuchMethodException` because the corresponding constructor is not public.

`Constructor.canAccess(null)` checks permissions at the current caller; use `null` because a constructor does not yet have a receiver object. `newInstance(...)` can throw `IllegalAccessException` when calling the constructor is not allowed, `InvocationTargetException` if the constructor itself throws an exception, or `InstantiationException` for an abstract class; these exceptions must not be confused with failing to find the constructor.

When testing each member kind, create **independent test cases** (field lookup, field get/set, method lookup/invoke, constructor lookup/newInstance) with specific expected exceptions. If you only write a single `getDeclaredXxx` check, the fixture only verifies metadata visibility, not usage permission.

## 5. What Do Named Modules, `exports`, and `opens` Change?

The example in section 3 intentionally runs on the classpath in the unnamed module. A test suite for **JPMS** needs separate named modules, because `exports` and `opens` control different aspects:

- `exports fixture;` allows another module (if it reads the target module) to use **public types/public members** of package `fixture` under normal access rules. It does not allow outsiders to arbitrarily invoke `privateMethod`.
- `opens fixture to client.app;` grants **deep reflection** capability on package `fixture` to module `client.app`, when other API and module conditions are satisfied. `opens` does not turn private members into public Java source members.
- If the package is not open to the caller, `trySetAccessible()` on a private member in another module may return `false`, and `setAccessible(true)` may throw `InaccessibleObjectException`.
- Modules can use `--add-opens source.module/fixture=client.app` for controlled diagnostic needs, but this flag should not be treated as a default requirement for the application to work.

Separate illustrative example of descriptors (not required files to run the classpath demo above):

~~~java
// module-info.java of module fixture.lib:
module fixture.lib {
    exports fixture;
    opens fixture to client.app;
}

// module-info.java of module client.app:
module client.app {
    requires fixture.lib;
}
~~~

If you want to test blocking deep reflection, add a fixture in a **named module that does not `opens` the package** and verify `trySetAccessible()` fails from another module. Pay attention to launch options/module path, and do not use the classpath demo output as expected output for JPMS tests.

## 6. Designing a Stable Test Matrix

Do not design a fixture just to "run once." For Reflection tools, have a clear verification matrix:

| Test axis | Minimum cases |
| --- | --- |
| Member | Field, method, constructor; consider static, inherited, final in extended tests |
| Modifier | `public`, `protected`, package-private, `private` |
| Caller relationship | Same class, same-package different nest, cross-package subclass, cross-package unrelated class |
| Receiver | Proper subclass receiver, base-class receiver, `null` for static/constructor, incompatible receiver |
| Lookup | `getDeclaredXxx` vs `getXxx`; verify `NoSuchFieldException`/`NoSuchMethodException` |
| Usage | `canAccess`, `Field.get/set`, `Method.invoke`, `Constructor.newInstance`, `trySetAccessible` |
| Module | Classpath unnamed module, named modules with `exports`, named modules with/without `opens` |
| Result | Correct data, expected exception, complete metadata, stable log format and ordering |

**Do not use Reflection array ordering as expected output.** Perform `sorted()` or set comparisons when ordering is meaningless. Avoid tests that rely on `setAccessible(true)` on closed JDK packages; the goal here is to verify the fixture's access rules, not to find ways to disable encapsulation.

When testing with nested classes, explicitly record which nest they belong to using `Class.getNestHost()` and `getNestMembers()`. A nested test class may already have private access to its enclosing class from the start, turning a "private must be denied" check into a **false negative in test design**.

## 7. Common Mistakes When Using Fixtures

1. **Having only public classes:** does not prove the tool handles protected/package-private/private correctly.
2. **Putting the fixture and runner in the same class/nest:** private permissions may be shared, losing cases that should be denied.
3. **Obtaining a `Field` successfully and concluding you have read permission:** metadata lookup and access check are two independent steps.
4. **Using `getMethods()` to find a private method:** that API only serves public methods; for private metadata use `getDeclaredMethod`.
5. **Using `canAccess(null)` for an instance field:** passes the wrong receiver; you must supply an instance of the right type.
6. **Calling `trySetAccessible()` and ignoring its status:** it returns a boolean; when disallowed, `false` must be handled properly.
7. **Confusing a protected member with public for every subclass receiver:** in a different package, instance member receivers follow specific rules.
8. **Relying on named modules while still using classpath expected output:** JPMS can alter reflective access results.
9. **Comparing method/field lists by the order Reflection returns:** there is no ordering guarantee, causing flaky tests.
10. **Failing to distinguish lookup exceptions from invoke exceptions:** a missing method and missing permission to invoke are two different causes.

**Takeaway:** a useful Reflection fixture must separate **visible metadata**, **default access by caller/receiver**, and **conditionally granted deep reflection permission**. The three-class, two-package example both demonstrates all four access modifiers and proves why `protected`, package-private, and `private` must be tested from multiple contexts rather than a single class.

**References:**
- [`Class` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html)
- [`AccessibleObject` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
- [`Field` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Field.html)
- [`Constructor` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Constructor.html)