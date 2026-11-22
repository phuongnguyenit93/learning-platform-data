# Looking up a member does not mean having permission to use it

## 1. Core idea: finding metadata is different from being allowed access

In Java Reflection, a program can **find a member's descriptor** (`Field`, `Method`, `Constructor`) and still **lack permission to read a field, write a field, invoke a method, or create an object via a constructor**. This is an easy point of confusion when starting out with `getDeclaredField()`, `getDeclaredMethod()`, and `getDeclaredConstructor()`.

Imagine an example:

```java
Field secret = Account.class.getDeclaredField("passwordHash");
```

If class `Account` has a `private` field named `passwordHash`, the statement above can still return a `Field` object. That only proves the field is **declared** and **discovered** by Reflection. The next statement such as `secret.get(account)` can still throw `IllegalAccessException` because the calling code does not have access permission.

At least three steps should be distinguished:

1. **Member lookup:** Specify the class, name, signature, and obtain metadata.
2. **Access check:** Decide whether the calling code can use that member or is allowed to request suppressing normal Java access checks.
3. **Actual operation:** `Field.get/set`, `Method.invoke`, or `Constructor.newInstance`, with a valid target object and arguments.

```text
Class<?> and member name/signature
              |
              v
     getDeclaredXxx / getXxx
              |
         Is it found?
         /           \
       No            Yes
       |               |
NoSuch...Exception     v
              Field/Method/Constructor obtained
                         |
                         v
              Access permission check
                   /            \
            Insufficient     Sufficient
                 |                |
        Cannot be used       get/set/invoke/
        directly             newInstance
```

**Lookup ability and accessibility are two independent questions.** Having metadata does not eliminate `private`, package boundaries, inheritance relationships, or Java Platform Module System (JPMS) rules.

## 2. Finding members with `getXxx` and `getDeclaredXxx`

`Class<?>` provides two important API families:

| Member | Public lookup | Lookup declared by the type itself |
|---|---|---|
| Field | `getField(name)`, `getFields()` | `getDeclaredField(name)`, `getDeclaredFields()` |
| Method | `getMethod(name, parameterTypes...)`, `getMethods()` | `getDeclaredMethod(name, parameterTypes...)`, `getDeclaredMethods()` |
| Constructor | `getConstructor(parameterTypes...)`, `getConstructors()` | `getDeclaredConstructor(parameterTypes...)`, `getDeclaredConstructors()` |

How to understand them:

- `getField` and `getMethod` look up **public** members according to the API rules, which may include inherited members.
- `getDeclaredField` and `getDeclaredMethod` inspect members **declared in the class/interface under consideration itself**, including `private`, `protected`, and package-private ones. The declared APIs do not automatically include inherited members.
- Constructors are not inherited; the difference between `getConstructor` and `getDeclaredConstructor` is mainly `public` scope versus any access level.
- `getDeclaredXxx` does not mean "allowed to use private members". The word *declared* describes **search scope**, not permission.
- Finding a `public` member with `getXxx` also does not guarantee the reflective operation will succeed: the declaring class may be inaccessible from the calling code, the package may not be exported by its module, or the target object/arguments may be invalid.

Illustrative example (assuming `Profile` has a `private String token` field):

```java
Field f = Profile.class.getDeclaredField("token");
System.out.println(f.getName()); // token

// The line below is NOT guaranteed to succeed:
Object value = f.get(profile);
```

This snippet only illustrates API semantics; `Profile` and `profile` are hypothetical elements, not a standalone program. A complete runnable program is presented in section 3.

A `NoSuchFieldException` or `NoSuchMethodException` means **the member was not found under the chosen name/signature/lookup scope**. It differs from `IllegalAccessException`, where metadata already exists but the operation is denied. For example, `getDeclaredMethod("pay", int.class)` does not find `pay(Integer)`, even though Java has boxing in regular source-code calls.

## 3. Runnable example on Java 17+: proving "found ≠ usable"

The program below defines **two separate top-level classes in the same file**. `Vault` contains a private field and a private method; `AccessLookupDemo` is a caller in a different class and different nest, so it **does not have private access permission under the Java language**. However, both reside in the same unnamed module, so `trySetAccessible` can enable suppression and demonstrate the difference.

Save verbatim to file **`AccessLookupDemo.java`**:

```java
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;

public class AccessLookupDemo {
    public static void main(String[] args)
            throws ReflectiveOperationException {

        Vault vault = new Vault("abc123");

        Field field = Vault.class.getDeclaredField("secret");
        System.out.println("field found: " + field.getName());
        System.out.println("field public: "
                + Modifier.isPublic(field.getModifiers()));
        System.out.println("field canAccess before: "
                + field.canAccess(vault));

        try {
            field.get(vault);
            System.out.println("field read unexpectedly succeeded");
        } catch (IllegalAccessException ex) {
            System.out.println("field get: "
                    + ex.getClass().getSimpleName());
        }

        boolean fieldOpened = field.trySetAccessible();
        System.out.println("field trySetAccessible: " + fieldOpened);
        System.out.println("field canAccess after: "
                + field.canAccess(vault));

        if (fieldOpened) {
            System.out.println("field value: " + field.get(vault));
        }

        Method method = Vault.class.getDeclaredMethod("formatSecret");
        System.out.println("method found: " + method.getName());
        System.out.println("method canAccess before: "
                + method.canAccess(vault));

        try {
            method.invoke(vault);
            System.out.println("method invoke unexpectedly succeeded");
        } catch (IllegalAccessException ex) {
            System.out.println("method invoke: "
                    + ex.getClass().getSimpleName());
        }

        boolean methodOpened = method.trySetAccessible();
        System.out.println("method trySetAccessible: " + methodOpened);

        if (methodOpened) {
            System.out.println("method result: "
                    + method.invoke(vault));
        }
    }
}

class Vault {
    private final String secret;

    Vault(String secret) {
        this.secret = secret;
    }

    private String formatSecret() {
        return "[" + secret + "]";
    }
}
```

Compile/run with JDK 17+:

```bash
javac AccessLookupDemo.java
java AccessLookupDemo
```

Expected output when running normally, without agents/configurations altering Reflection permissions:

```text
field found: secret
field public: false
field canAccess before: false
field get: IllegalAccessException
field trySetAccessible: true
field canAccess after: true
field value: abc123
method found: formatSecret
method canAccess before: false
method invoke: IllegalAccessException
method trySetAccessible: true
method result: [abc123]
```

Step-by-step explanation:

1. `getDeclaredField("secret")` and `getDeclaredMethod("formatSecret")` **find** the private members. No lookup exception occurs.
2. `Modifier.isPublic(...)` returns `false`; `canAccess(vault)` initially also returns `false` because the caller lacks private access permission.
3. `field.get(vault)` and `method.invoke(vault)` initially throw `IllegalAccessException` **before reading contents/executing the method**. Catching the exception allows the program to continue.
4. `trySetAccessible()` returns `true` in this example because the two top-level classes are in the same unnamed module and are not blocked by another access constraint from the environment.
5. After enabling suppression on each metadata object, `field.get(vault)` and `method.invoke(vault)` succeed.
6. `Vault` is the second top-level class without the `public` modifier. Java allows declaring multiple top-level classes in the same `.java` file, but only one `public` class matching the file name.

The example clearly shows that **it is not metadata that makes private members usable**, but rather that the caller was subsequently permitted by the runtime to enable suppression on the specific Reflection object.

## 4. Diagnosing an access error by the right stage

| Stage | Symptom | What to check |
| --- | --- | --- |
| Lookup | `NoSuchFieldException`, `NoSuchMethodException` | Are the name, signature, declaring class, and `getXxx` vs `getDeclaredXxx` scope right? |
| Access check | `canAccess(receiver) == false` | Does the caller have permission under Java rules? Are the declaring class and package/module accessible? |
| Opening access | `trySetAccessible() == false` or `InaccessibleObjectException` | Does the named module `opens` the package to the caller? Is deep reflection really needed? |
| Execution | `IllegalAccessException` | Metadata was found, but the caller does not yet have permission to use the member |
| Running target code | `InvocationTargetException` | Method/constructor ran and threw an exception; inspect `getCause()` |
| Argument check | `IllegalArgumentException` | Are the receiver, argument types/count, or assigned value valid? |

A `public` member can still be blocked if its *declaring class* is inaccessible. A `private` member can be called normally from its own class or a valid nestmate; the check result depends on the caller. `trySetAccessible()` only attempts to bypass access checks and remains subject to JPMS boundaries; succeeding does not guarantee every `final` field can be written.

## 5. Self-check

1. Why does `getDeclaredField("secret")` find the member even though `Field.get` can throw `IllegalAccessException`?
2. Why does finding a `public` method with `getMethod` still not guarantee `Method.invoke` is allowed?
3. Do two top-level classes in the same source file become nestmates? Why does the example use two separate classes?
4. Why do `exports` and `opens` affect public APIs and deep reflection differently?
5. When `Method.invoke` throws `InvocationTargetException`, should you investigate Reflection permissions or an error from the executed code?

**Key takeaway:** lookup determines that metadata **exists**; permission to use it is decided separately at the operation site. Choose the right `getXxx`/`getDeclaredXxx` family first, then evaluate the caller, receiver, and module.