# Limiting Conditions When Field.set Encounters final in Java Reflection

A field with the **final** keyword is designed to receive a value only during valid initialization according to Java rules. When using Reflection, you can still obtain the java.lang.reflect.Field object and read the field's value. However, **being able to read a Field, or even calling setAccessible(true) successfully, does not mean Field.set has permission to modify a final value**.

In Java 17, some **instance final fields** of ordinary classes can still be modified via deep reflection under very strict conditions; however, **static final**, final fields in a **record**, and final fields in a **hidden class** are **non-modifiable** fields and cannot be written using Field.set. Starting in JDK 26, modifying final fields via deep reflection is also subject to new warning/restriction policies, moving toward being disallowed by default in future Java releases.

Lesson objectives: recognize cases that are allowed or blocked when calling Field.set, predict exceptions, distinguish access permission from write permission, examine the impact of modules, and choose safe design alternatives instead of mutating final fields after initialization.

## 1. How does final in source code differ from Reflection?

Example:

~~~java
class Order {
    private final int id;

    Order(int id) {
        this.id = id;
    }

    int id() {
        return id;
    }
}
~~~

Ordinary Java code does not allow writing order.id = 100 after the constructor because the field is declared final. Reflection has two separate steps:

1. Obtain metadata: Field field = Order.class.getDeclaredField("id").
2. Access or write: field.get(order), field.set(order, 100), which may require field.setAccessible(true).

**getDeclaredField** lets you look up a private field declared directly in the class, but by itself it grants no read/write permission. **setAccessible(true)** requests suppressing Java language access checks for that Field, within the bounds permitted by module permissions. It **does not remove the categories of final that Java marks as non-modifiable**.

This must be separated into three questions:

- Were the right Field and target object found?
- Is the caller permitted to perform the Reflection operation?
- Does the field belong to a final category that can be modified in the running runtime/JDK version?

Only when all three conditions align does Field.set have a chance to complete. A successful modification does not mean subsequent program behavior will always observe the new value.

## 2. Field.set rules for final on Java 17

According to the Java SE 17 API, to **write a final field with Field.set(Object, Object)**, the following conditions must all hold simultaneously:

1. **setAccessible(true) has succeeded on this exact Field**.
2. The field is an **instance field**, meaning **not static**.
3. The field's declaring class is **not a hidden class**.
4. The field's declaring class is **not a record class**.
5. The target object is compatible, the passed value can be validly assigned/converted to the field's type, and there are no additional runtime barriers.

When any of the final-write conditions above is missing, Field.set may throw **IllegalAccessException**. If access is already blocked at setAccessible(true), the common exception is **InaccessibleObjectException**. If the value or target object is incompatible, you may encounter **IllegalArgumentException**; if null is passed for an instance field requiring a receiver, you may encounter **NullPointerException**.

| Field type | Example | Can setAccessible(true) allow reading? | Does Field.set write final on Java 17? |
| --- | --- | --- | --- |
| Instance final in an ordinary class | private final int id | Yes, if access permissions allow | **Conditionally**, with the restrictions above |
| Static final of a class | private static final String NAME | Yes, if access permissions allow | **No** |
| Static final in an interface | String NAME = "x" | Yes, according to visibility/access permissions | **No** |
| Instance final of a record | record User(int id) | Yes, if access permissions allow | **No** |
| Final field in a hidden class | final field of a class created via Lookup.defineHiddenClass | Yes, if access permissions allow | **No** |
| Ordinary instance non-final | private int count | Yes, if access permissions allow | Possible, subject to access and type rules |

**Note:** this table describes the **Field.set** operation of Java Reflection, and does not draw conclusions about all mechanisms such as Java bytecode, JNI, serialization internals, or other special APIs. Do not use tricks based on Unsafe or modifying Modifier flags to bypass constraints: those approaches are not stable API contracts.

### What does non-modifiable final field mean?

JDK 17 defines three groups that **cannot be written via Field.set**:

- All **static final** fields (in a class or interface).
- All **final fields declared in a hidden class**.
- All **final fields declared in a record class**.

For these groups, setAccessible(true), when permitted, only helps Reflection **read** a non-public field; it **does not turn** the field into a writable one.

A record such as record Customer(int id) automatically has a corresponding private final instance component field. Even if you can obtain Field("id"), Field.set is still not permitted to modify it.

## 3. Compilable and runnable Java 17+ example

Save the entire snippet below into **FinalFieldRulesDemo.java**. The example intentionally tests four cases: modifying an ordinary instance final, writing a static final, writing a record final, and passing the wrong data type.

~~~java
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;

public class FinalFieldRulesDemo {
    static final class Invoice {
        private final int id;

        Invoice(int id) {
            this.id = id;
        }
    }

    static final class Settings {
        private static final String VERSION = "v1";
    }

    record Receipt(int id) {}

    public static void main(String[] args) throws ReflectiveOperationException {
        Invoice invoice = new Invoice(1);
        Field instanceField = Invoice.class.getDeclaredField("id");
        System.out.println("instance final = "
                + Modifier.isFinal(instanceField.getModifiers()));
        instanceField.setAccessible(true);
        instanceField.set(invoice, 42);
        System.out.println("instance Field.get = " + instanceField.getInt(invoice));

        Field constantField = Settings.class.getDeclaredField("VERSION");
        constantField.setAccessible(true);
        try {
            constantField.set(null, "v2");
        } catch (IllegalAccessException ex) {
            System.out.println("static final = " + ex.getClass().getSimpleName());
        }

        Field recordField = Receipt.class.getDeclaredField("id");
        recordField.setAccessible(true);
        try {
            recordField.set(new Receipt(3), 9);
        } catch (IllegalAccessException ex) {
            System.out.println("record final = " + ex.getClass().getSimpleName());
        }

        try {
            instanceField.set(invoice, "text");
        } catch (IllegalArgumentException ex) {
            System.out.println("wrong value type = " + ex.getClass().getSimpleName());
        }
    }
}
~~~

Compile/run using JDK 17–25, or run using JDK 21 to reproduce the exact stdout below:

~~~bash
javac --release 17 -encoding UTF-8 FinalFieldRulesDemo.java
java FinalFieldRulesDemo
~~~

Stdout verified by compiling with **--release 17** and running on JDK 21:

~~~text
instance final = true
instance Field.get = 42
static final = IllegalAccessException
record final = IllegalAccessException
wrong value type = IllegalArgumentException
~~~

Step-by-step explanation:

1. Modifier.isFinal(instanceField.getModifiers()) returns true: metadata confirms the instance field id has the final modifier.
2. instanceField.setAccessible(true) succeeds because the example resides in the same program/module with the necessary permissions. On JDK 21, Field.set(invoice, 42) can write to an **ordinary class instance final**, and Field.getInt returns 42.
3. Settings.VERSION is **static final**. Even after setAccessible(true), Field.set(null, "v2") throws IllegalAccessException; the null receiver argument is already valid for a static field, so the error is due to final write restrictions.
4. Receipt.id is a **record final**. setAccessible(true) does not make it writable; Field.set throws IllegalAccessException.
5. The instance id field has type int. Passing the string "text" cannot unbox/widen to int, so Field.set throws IllegalArgumentException.

**Limitations of the example:** only conclude that Field.get observes 42 immediately after the successful operation on the tested JDK. Do not treat this as a guarantee that all compiled code, other threads, or other JVMs/JITs will see 42 via getters or direct access. On JDK 26, the command modifying the instance final in the example may emit **a warning on stderr** under the new policy; stdout is recorded separately to avoid confusion.

## 4. setAccessible, trySetAccessible, and module permissions

Before calling Field.set, check the class and module that actually contain the field. In the **Java Platform Module System (JPMS)**, directives serve different roles:

- **requires** establishes a module readability relationship; it does not automatically open private members for Reflection.
- **exports package** allows modules reading the library to use the public API in that package; it does not automatically grant access to private fields.
- **opens package** or **opens package to target.module** allows deep reflection within the opened module scope, including the ability to request setAccessible(true) on private fields.

Example module containing entities:

~~~java
module com.example.data {
    exports com.example.data.api;
    opens com.example.data.entity to com.example.json;
}
~~~

Module com.example.json can request reflective access to the fields of com.example.data.entity. However, if a field is **static final** or **record final**, opens still **does not make it writable**. If the field is an ordinary instance final, opens can satisfy the access condition; the final limits of Field.set and the JDK still apply.

In a package not opened to the caller module, for example:

~~~java
Field field = someClass.getDeclaredField("value");
field.setAccessible(true); // may throw InaccessibleObjectException
~~~

This is an **illustrative snippet**; someClass must be a Class<?> already defined in the calling context, not a standalone program.

Replace with:

~~~java
if (field.trySetAccessible()) {
    // Allowed to request bypassing access checks; may still not be writable if the field is final.
} else {
    // Module/package or access control does not permit it.
}
~~~

trySetAccessible() typically returns false instead of throwing InaccessibleObjectException when accessibility cannot be enabled (though special security exceptions may still exist). The success of trySetAccessible() **does not mean Field.set is guaranteed to succeed**. Errors at the access-enabling stage must be separated from errors at the write stage.

To diagnose:

~~~java
Class<?> owner = field.getDeclaringClass();
Module ownerModule = owner.getModule();
Module callerModule = YourCaller.class.getModule();
System.out.println(ownerModule.isOpen(owner.getPackageName(), callerModule));
~~~

This is also an illustrative snippet; replace YourCaller with the class performing Reflection. **Module.isOpen** helps inspect package boundaries, not independently determine whether a final field is writable. When the class and caller are in the same module, access rules may differ from the case of two separate named modules.

The **--add-opens source.module/package=target.module** option can grant deep reflection permission at startup when appropriate, but **does not** allow writing non-modifiable final fields. And starting in JDK 26, **--add-opens also does not substitute for the additional final-field mutation permission** discussed in section 7.

## 5. Distinguishing each error type when Field.set fails

| Symptom | Failure point | Common cause | Resolution |
| --- | --- | --- | --- |
| NoSuchFieldException | getDeclaredField/getField | Wrong name or wrong class searched; getDeclaredField does not search inherited fields | Choose the right declaring class/field name |
| InaccessibleObjectException | setAccessible(true) | Package in a named module is not opened to the caller | Check module-info.java and appropriate opens permissions |
| trySetAccessible() returns false | trySetAccessible() | Cannot enable suppression under access/module rules | Use a public API or intentionally adjust permissions |
| IllegalAccessException | Field.set | Insufficient write permission; or final belongs to a non-modifiable category | Check final/static/record/hidden and the accessible flag |
| IllegalArgumentException | Field.set | Receiver of wrong class or value type cannot be validly converted | Pass the right object and compatible field type |
| NullPointerException | Field.set | Null receiver with an instance field | Pass an actual instance |
| Final field mutation warning (JDK 26) | When final mutation is detected | Deep reflective mutation not explicitly permitted | Move initialization logic; if unavoidable, see JEP 500 |

**Example:** a Field f of type int can accept Integer via unboxing and some supported primitive *widening* conversions. However, it cannot arbitrarily convert String to int, nor does it perform narrowing conversions by default such as long to int. A specialized method like Field.setInt(...) can be used if appropriate, but **it also does not bypass final restrictions**.

### Checking modifiers and declaring class

Use the following helper code after obtaining a Field:

~~~java
int modifiers = field.getModifiers();
boolean isFinal = Modifier.isFinal(modifiers);
boolean isStatic = Modifier.isStatic(modifiers);
boolean inRecord = field.getDeclaringClass().isRecord();
boolean inHidden = field.getDeclaringClass().isHidden();
~~~

This is an illustrative snippet, requiring imports of java.lang.reflect.Field and java.lang.reflect.Modifier and a field variable. A self-check rule is: if isFinal and (isStatic or inRecord or inHidden), **do not call Field.set expecting to modify that field**. Even when all the above conditions are false, you must still consider access permissions, the Java version, and the risks of mutating an instance final.

## 6. Why is modifying an instance final still dangerous even when it succeeds?

Java permits certain reflective exceptions to support object-reconstruction tools or deserialization, but **final is not designed as a configuration variable that can be modified at arbitrary times**. JDK 17 describes modifying final via Reflection as meaningful only in appropriate reconstruction/deserialization scenarios, before the object is used by other components.

### The value may not be observed uniformly by all code

Consider an explanatory example (without predicting stdout):

~~~java
class Flags {
    final int mode = 1;

    int mode() {
        return mode;
    }
}
~~~

The compiler and JIT can leverage the immutability of final; a getter call or optimized code may continue using the old value even though Reflection modified the memory slot. Especially for **compile-time constants**—final primitives/Strings initialized with constant expressions—Java can replace references with the constant directly in the consumer's bytecode.

Therefore:

- Do not use Field.get right after set as proof that the change will be consistently reflected across all code.
- Do not build business correctness on modifying a final field that has already been published to other threads.
- Do not use Reflection to change a static final constant and expect the entire program to see the change; Field.set even rejects writing this category.
- Modifying final after initialization breaks optimization and immutability assumptions and can undermine safe-publication guarantees for objects.

### Threading and Java Memory Model issues

The Java Memory Model's final field rules have special meaning at the moment object initialization completes via a constructor. Those guarantees are not a license for one thread to modify final at will and expect all other threads to see the new value. A successful Field.set is a reflective operation, **not a synchronization protocol** that replaces happens-before, volatile, or synchronized.

If data genuinely needs to change over time, design it with an ordinary field combined with appropriate synchronization; if data needs to remain immutable, create a new instance via a constructor or factory method. Do not treat final as a hidden mutable field.

## 7. New note from JDK 26: JEP 500 – Prepare to Make Final Mean Final

The rules in section 2 describe the capabilities of **Java SE 17**. Contrast them with a change when running on a modern JDK.

Starting in **JDK 26**, JEP 500 adds a mechanism to detect **mutating final instance fields via deep reflection**. Under the default mode in JDK 26, an unauthorized mutation by a module may continue running while emitting a **warning**. The JDK's stated goal is that a future release will switch the default to **denying the operation**, unless the application explicitly grants permission to the mutating module.

Related options:

- **--enable-final-field-mutation=ALL-UNNAMED**: allows code in unnamed modules (applications on the classpath) to perform this kind of mutation when other access conditions are also met.
- **--enable-final-field-mutation=module.one,module.two**: grants the specified named modules permission to perform final-field mutation under the JDK 26 policy.
- **--illegal-final-field-mutation=warn**: allows but warns, which is the JDK 26 default for unauthorized mutation.
- **--illegal-final-field-mutation=debug**: warns with a stack trace, useful for finding libraries that mutate final fields.
- **--illegal-final-field-mutation=deny**: denies unauthorized mutation and leads to IllegalAccessException.
- **--illegal-final-field-mutation=allow**: allows without warning; should only be treated as a transitional measure.

Illustrative example **for Java 26+ only**, assuming an application on the classpath genuinely must perform mutation after access permissions have been considered:

~~~bash
java --enable-final-field-mutation=ALL-UNNAMED FinalFieldRulesDemo
~~~

Or proactively test the application under JDK 26's strict policy:

~~~bash
java --illegal-final-field-mutation=deny FinalFieldRulesDemo
~~~

If you run the deny command without a matching --enable-final-field-mutation grant, the example in section 3 may fail early at instanceField.set(invoice, 42) with IllegalAccessException, so **do not use the JDK 21 stdout as a prediction for that run**.

**Two independent layers of conditions:** the module owning the field must still open the appropriate package to the caller via opens/--add-opens (or another permitted access case); at the same time, JDK 26 may require granting mutation permission to the caller module. --enable-final-field-mutation does not automatically open packages, and **does not turn static final/record final/hidden-class final into writable fields**.

This policy helps serialization/DI libraries gradually drop reliance on mutating existing final fields. When maintaining a project across multiple JDKs, test the newer release, check stderr, and upgrade library versions before considering any permission-granting options.

## 8. Design alternatives to Reflection to keep final truly final

### Set data at initialization time

~~~java
public record UserProfile(String name, int level) {
    public UserProfile withLevel(int nextLevel) {
        return new UserProfile(name, nextLevel);
    }
}
~~~

This is a standalone record class usable in a project; when level needs to change, create a new UserProfile instead of calling Field.set on the record's field.

### Constructor, factory, builder

If an object requires mandatory values, pass them through a constructor/factory/builder. Frameworks can support **constructor-based binding** or a **record canonical constructor** instead of writing each private final field after instance creation. When a framework needs to access a non-public constructor in another module, opens may still be needed, but mutating final after the constructor is not necessarily needed.

### When data is genuinely mutable

Use a non-final field with a controlled setter, or create a new object when state changes. For multi-threaded applications, choose volatile, AtomicReference, synchronized, or an immutable snapshot based on actual consistency requirements. Do not bypass final with Reflection to silently change state.

### For static constants

To change runtime configuration, use a configuration source or a mutable configuration object with an explicit update mechanism. Do not rely on editing static final primitives/Strings, especially compile-time constants that may be inlined at usage sites.

## 9. Step-by-step diagnostic workflow

1. **Locate the right Field.** Use getDeclaredField(name) on the declaring class; do not assume it searches superclasses. For inherited fields, look up on the declaring class.
2. **Check the field category.** Modifier.isFinal(), Modifier.isStatic(), getDeclaringClass().isRecord(), isHidden(). If it is final and static/record/hidden: treat it as non-writable via Field.set.
3. **Check access.** Who is performing Reflection? Is the package containing the field opened to the right caller module? If using setAccessible(true), errors here usually differ from errors at Field.set.
4. **Check receiver and value.** An instance field requires an object of a compatible class; a primitive requires a convertible type; a static field needs no receiver.
5. **Check the running JDK.** Java 17 capabilities differ from JDK 26 mutation policies. Read warnings/stack traces and test appropriate configuration flags during maintenance.
6. **Evaluate correctness after mutation.** If the field is final, do not use a single Field.get result to conclude that other getters/consumers will see the new value; prioritize fixing the object architecture.

A sound diagnostic process clearly distinguishes **metadata lookup**, **enabling access**, **field-category write permission**, **data types**, and **immutability semantics**. This usually pinpoints where the failure lies without having to open permissions for an entire module.

## 10. Self-check

**Question 1.** private static final int LIMIT = 10; belongs to an ordinary class, and field.setAccessible(true) succeeds. Will Field.setInt(null, 20) succeed?

**Answer:** No. This is static final, belonging to the non-modifiable group on Java 17; specialized setters do not bypass final restrictions.

**Question 2.** private final int age of an ordinary class, Field.setAccessible(true) succeeds; valid receiver, compatible value type. Can Field.set run on Java 17?

**Answer:** Conditionally. This is an instance final not in a record/hidden class. However, modifying it after the object has been published is not guaranteed to be observed uniformly, and JDK 26 also introduces new warning/restriction policies.

**Question 3.** record Book(String title) has a field title. If setAccessible(true) can be called, is Field.set(book, "new") valid?

**Answer:** No. An instance final declared by a record belongs to the non-modifiable group.

**Question 4.** A module exports the package containing a class but does not open it to a framework module that wants to write a private final field. At which step can an error appear?

**Answer:** At setAccessible(true) because there is no opens (may throw InaccessibleObjectException). Adding exports does not replace opens; even when opens is granted, you must still check the final category and JDK policy.

**Question 5.** On JDK 26, is opening a package with --add-opens enough to avoid the final field mutation warning?

**Answer:** Not necessarily. Deep reflection permission and **final mutation** permission are evaluated separately; if truly needed, you must understand --enable-final-field-mutation and --illegal-final-field-mutation.

**Remember:** Reflection can **read** final fields within appropriate access bounds; **Field.set only ever allowed modifying certain instance finals of ordinary classes under strict conditions**. Static final, record final, and hidden-class final fields cannot be written with Field.set. On JDK 26+, also check the final-field mutation policy and prefer proper immutable initialization via constructors/factories.

### References

- Java SE 17, java.lang.reflect.Field – Field.set: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html#set(java.lang.Object,java.lang.Object)
- Java SE 17, AccessibleObject – setAccessible and non-modifiable final fields: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html#setAccessible(boolean)
- Java SE 17, Class – isRecord/isHidden: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- Java Language Specification §17.5 – final Field Semantics: https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.5
- JEP 500 – Prepare to Make Final Mean Final: https://openjdk.org/jeps/500
- Oracle JDK 26 Migration Guide – Preparing for final Field Mutation Restrictions: https://docs.oracle.com/en/java/javase/26/migrate/preparing-final-field-mutation-restrictions.html
