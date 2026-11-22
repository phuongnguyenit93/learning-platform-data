# Controlling Assertions by Class, Package, and Default Value

## 1. Where Are Assertions Enabled or Disabled in Java?

Java has the **assert** statement for checking internal program assumptions:

~~~java
assert balance >= 0;
assert result != null : "Unexpected null result";
~~~

When assertions are **enabled** for the class containing the statement, the condition expression is evaluated. If the condition is false, the JVM throws an **AssertionError**; the message expression after the colon, if present, is evaluated when needed to create the error. When assertions are **disabled**, the entire assert statement does not evaluate these expressions. Therefore, **do not put side effects or mandatory business logic inside an assert**.

Assertions are typically disabled by default for application classes when running the `java` command without configuration. The program runner can enable/disable them using the **-ea/-da** options, while code controlling the class loader can set policies using the **ClassLoader.setDefaultAssertionStatus**, **setPackageAssertionStatus**, and **setClassAssertionStatus** APIs.

This lesson explains the three policy levels: **loader default, per-package, and per-class**, precedence rules, when policies take effect, clearing policies, limitations with nested classes, and interaction with JVM options. The focus is on the class loader and how policies affect classes **that will be initialized**.

## 2. The Four APIs on `java.lang.ClassLoader`

| API | Meaning | Scope of Impact |
| --- | --- | --- |
| **setDefaultAssertionStatus(boolean enabled)** | Sets the default enable/disable assertion status for the loader. | Classes managed by the loader and initialized subsequently, unless overridden by package/class. |
| **setPackageAssertionStatus(String packageName, boolean enabled)** | Sets the default for a package. | The specified package and all of its **subpackages**, unless a more specific policy exists. |
| **setClassAssertionStatus(String className, boolean enabled)** | Sets the policy for a **top-level class**. | The specified top-level class along with the nested classes inside it. |
| **clearAssertionStatus()** | Clears all class/package directives and sets the loader's default to **false**. | Classes initialized subsequently within the loader's scope. |

All four are **public** methods of ClassLoader, so they can be called on a loader object when you have access to that reference:

~~~java
ClassLoader loader = MyApplication.class.getClassLoader();
loader.setDefaultAssertionStatus(true);
loader.setPackageAssertionStatus("com.example.service", false);
loader.setClassAssertionStatus("com.example.service.Checker", true);
~~~

The snippet above is illustrative code placed in an application that has the MyApplication and Checker classes; it is not yet a standalone runnable program. A complete example is provided later.

**The boolean has a direct meaning:** true = assertions enabled, false = assertions disabled. There is no **`Class<?>`** parameter for the class name in these methods: the class is specified as a **name string**. Do not confuse this value with **Class.desiredAssertionStatus()**, which is an API for reading the desired status.

## 3. Precedence Order: class > most specific package > default

If a class has multiple matching rules, the following order is used:

1. **The rule for the top-level class**, if specified, has the highest precedence, including for nested classes belonging to that top-level class.
2. **The most specific package rule** applicable to the class, meaning the package with the longest name in the applicable package tree.
3. **The default of the class loader itself**, if there is no matching override.

~~~text
   Need to determine the assertion status of class C
                           |
                           v
 Is there a directive for the top-level class containing C?
               |                             |
              Yes                            No
               |                             |
               v                             v
       Use class status           Is there a package status?
                                        |             |
                                       Yes            No
                                        |             |
                                        v             v
                                Choose the most   Use loader's
                                specific package    default
~~~

For example, a loader has the policy:

~~~java
loader.setDefaultAssertionStatus(true);
loader.setPackageAssertionStatus("app", false);
loader.setPackageAssertionStatus("app.data", true);
loader.setClassAssertionStatus("app.data.Special", false);
~~~

Results for classes initialized after setting the policies:

| Class | Selected Policy | Assertion |
| --- | --- | --- |
| **other.Task** | Loader default | Enabled |
| **app.Main** | Package app | Disabled |
| **app.web.Controller** | Package app (includes subpackages) | Disabled |
| **app.data.Repository** | Package app.data is more specific than app | Enabled |
| **app.data.deep.Parser** | Package app.data | Enabled |
| **app.data.Special** | Class override | Disabled |
| **app.data.Special.Nested** | Top-level Special policy | Disabled |

Note that the names in the table describe classes using Java syntax; the binary name of a nested class normally uses the **$** character, but the **setClassAssertionStatus** API takes the **top-level class name** when you want to control both the class and its nested classes.

### 3.1 Packages and Subpackages Are Determined by Dots

If a policy is set for **app.data**, it applies to **app.data** itself and packages starting with **app.data.**, such as **app.data.deep**. It does **not** apply to **app.database** because that name does not start with **app.data.**.

Java has no package inheritance relationship in the language: “subpackage” here is how the assertion API uses **package name prefixes** to select defaults. A more specific package rule always wins over a parent package, regardless of whether the parent rule was called before or after.

### 3.2 Unnamed Package

You can use:

~~~java
loader.setPackageAssertionStatus(null, true);
~~~

The value **null** represents the current **unnamed package**. Do not use an empty string instead of null according to the API contract. In real-world code, you should organize classes into named packages; however, this feature helps control applications or Java examples that do not declare a package.

## 4. `setClassAssertionStatus` Takes the Top-Level Class Name

This is an easily overlooked detail in the Javadoc.

~~~java
loader.setClassAssertionStatus("com.example.Outer", true);
~~~

This operation sets the policy for the top-level class **Outer** and the nested classes inside Outer, such as **Outer.Inner** or **Outer.StaticNested**. For a nested class, the desired status is derived from its top-level enclosing class according to the assertion rules.

Conversely, calling the API using the name of a nested class:

~~~java
loader.setClassAssertionStatus("com.example.Outer$Inner", false);
~~~

**Does not change the actual assertion status of the nested class** according to the API contract. The parameter here is designed for a **top-level class**; if you want to control a nested class separately by that name string, this method does not provide such an option.

**Do not confuse with `ClassLoader.loadClass`:** loadClass typically takes the **binary name** of the class being loaded, including the **$** sign for nested classes. However, **setClassAssertionStatus** applies the assertion policy at the **top-level** class level and to the nested classes inside it.

Within the same top-level class, if you want checks enabled only in certain places, you can organize the logic into separate top-level classes, or use another appropriate control/testing mechanism; do not misuse assertion policies to control business logic.

## 5. When to Set Policies: Before the Class Is Initialized

According to the ClassLoader API, the setters affect **classes that will be initialized in the future**. An already initialized class **does not change its assertion execution state** simply because the loader is reconfigured.

~~~text
Time A: loader.setClassAssertionStatus("app.Task", true)
                    |
                    v
Time B: app.Task initialized for the first time
        → Task's assertion status is finalized
                    |
                    v
Time C: loader.setClassAssertionStatus("app.Task", false)
        → does not disable assertions already finalized for Task
~~~

Four situations to distinguish:

- **Merely having a Class object** (for example, obtained from **Class.forName(name, false, loader)**) does not mean the class is initialized.
- **Already loaded/linked but not yet initialized:** setting the assertion status can still take effect when the class is initialized, according to the API contract.
- **Already initialized:** changing the loader configuration does not change how asserts already determined for that class execute.
- **Another uninitialized class:** the new configuration can apply to that other class even if it is in the same package.

Therefore, if a program wants to control assertions for a group of classes, it should set the policies **before their active use** (for example, before creating a new instance, calling a static method, or reading a static field that is not a compile-time constant).

### 5.1 Assertion Status Is Not a Variable Read at Every Statement

The compiler may generate a synthetic field such as **$assertionsDisabled** in the class bytecode, with its state based on the assertion policy when the class is initialized. A subsequent change to the loader does not cause asserts in an already initialized class to re-read the configuration.

You can inspect the bytecode using:

~~~bash
javap -c -p lab.rules.PackageProbe
~~~

Depending on the compiler and class, the output may include a synthetic field related to assertions; the name and layout are compilation details and should not be relied upon as a public API.

## 6. Runnable Example 1: Default, Package, Subpackage, Class, and Clear Levels

The Java 17+ example below tests the entire precedence order using uninitialized classes. Each **enabled()** intentionally uses **assert false** and catches AssertionError to determine whether assertions are executed. This is a **test probe**, not a recommendation to write assertions like this in production.

Directory structure:

~~~text
project/
└── src/
    └── lab/
        ├── rules/
        │   ├── PolicyDemo.java
        │   └── deep/
        │       └── DeepProbe.java
        └── misc/
            └── DefaultProbe.java
~~~

**src/lab/rules/PolicyDemo.java**:

~~~java
package lab.rules;

import lab.misc.DefaultProbe;
import lab.rules.deep.DeepProbe;

public class PolicyDemo {
    public static void main(String[] args) {
        ClassLoader loader = PolicyDemo.class.getClassLoader();

        loader.clearAssertionStatus();
        loader.setDefaultAssertionStatus(true);
        loader.setPackageAssertionStatus("lab.rules", false);
        loader.setPackageAssertionStatus("lab.rules.deep", true);
        loader.setClassAssertionStatus("lab.rules.ClassProbe", true);

        System.out.println("package = " + PackageProbe.enabled());
        System.out.println("class = " + ClassProbe.enabled());
        System.out.println("nested = " + ClassProbe.Nested.enabled());
        System.out.println("subpackage = " + DeepProbe.enabled());
        System.out.println("default = " + DefaultProbe.enabled());

        loader.setPackageAssertionStatus("lab.rules", true);
        System.out.println("late package = " + LateProbe.enabled());

        loader.clearAssertionStatus();
        System.out.println("initialized class = " + ClassProbe.enabled());
        System.out.println("future class = " + FutureProbe.enabled());
    }
}

class PackageProbe {
    static boolean enabled() {
        try {
            assert false : "probe";
            return false;
        } catch (AssertionError expected) {
            return true;
        }
    }
}

class ClassProbe {
    static boolean enabled() {
        try {
            assert false : "probe";
            return false;
        } catch (AssertionError expected) {
            return true;
        }
    }

    static class Nested {
        static boolean enabled() {
            try {
                assert false : "probe";
                return false;
            } catch (AssertionError expected) {
                return true;
            }
        }
    }
}

class LateProbe {
    static boolean enabled() {
        try {
            assert false : "probe";
            return false;
        } catch (AssertionError expected) {
            return true;
        }
    }
}

class FutureProbe {
    static boolean enabled() {
        try {
            assert false : "probe";
            return false;
        } catch (AssertionError expected) {
            return true;
        }
    }
}
~~~

**src/lab/misc/DefaultProbe.java**:

~~~java
package lab.misc;

public class DefaultProbe {
    public static boolean enabled() {
        try {
            assert false : "probe";
            return false;
        } catch (AssertionError expected) {
            return true;
        }
    }
}
~~~

**src/lab/rules/deep/DeepProbe.java**:

~~~java
package lab.rules.deep;

public class DeepProbe {
    public static boolean enabled() {
        try {
            assert false : "probe";
            return false;
        } catch (AssertionError expected) {
            return true;
        }
    }
}
~~~

From the **project** directory, compile and run:

~~~bash
javac -d out src/lab/rules/PolicyDemo.java src/lab/misc/DefaultProbe.java src/lab/rules/deep/DeepProbe.java
java -cp out lab.rules.PolicyDemo
~~~

Stdout verified on JDK 21 (the code uses APIs available since Java 17):

~~~text
package = false
class = true
nested = true
subpackage = true
default = true
late package = true
initialized class = true
future class = false
~~~

### 6.1 Analyzing the Eight Results

**package = false:** **PackageProbe** is in package **lab.rules**. The package false rule takes higher precedence than default true.

**class = true:** **ClassProbe** also belongs to **lab.rules**, but has a class override of true. The class rule overrides package false.

**nested = true:** **ClassProbe.Nested** is inside the top-level ClassProbe, so it inherits the assertion policy set for ClassProbe, despite the package rule being false.

**subpackage = true:** **DeepProbe** belongs to **lab.rules.deep**. The most specific package rule **lab.rules.deep = true** wins over **lab.rules = false**.

**default = true:** **DefaultProbe** belongs to **lab.misc**, has no specific package/class rule, so it uses default true.

**late package = true:** After changing **lab.rules** to true, the uninitialized **LateProbe** receives the new policy.

**initialized class = true:** ClassProbe was previously initialized on line 2. The **clearAssertionStatus()** call does not disable assertions already finalized in ClassProbe.

**future class = false:** FutureProbe is only initialized at this point. **clearAssertionStatus()** has cleared all overrides and reset the default to false, so FutureProbe has assertions disabled.

### 6.2 Why Does the Example Proactively Call `clearAssertionStatus` at the Beginning?

To keep the results independent of any assertion configuration that the JVM or the runner passed to the application loader, the program clears the loader state before setting the rules. **clearAssertionStatus** does not mean “restore the initial settings from the command line”; it **sets default=false and clears all package/class overrides on this loader**. If you need to restore a specific policy, you must re-establish the corresponding rules using the API.

Do not arbitrarily apply this technique of resetting assertion status to the application loader in a large software product: many libraries may already have initialized classes or depend on the environment's assertion configuration. The example only illustrates the API's semantics in an isolated program.

## 7. Controlling Assertions with JVM Options

Before the JVM launches the application, the runner can pass options:

| Option | Meaning |
| --- | --- |
| **-ea** or **-enableassertions** | Enables assertions by default for applicable application classes. |
| **-da** or **-disableassertions** | Disables assertions by default. |
| **-ea:com.example...** | Enables assertions in the com.example package and its subpackages. |
| **-da:com.example.internal...** | Disables assertions in the internal package and its subpackages. |
| **-ea:com.example.Service** | Enables assertions for the specified top-level class (and its nested classes). |
| **-da:com.example.Service** | Disables assertions for the specified class. |
| **-ea:...** | Enables assertions in the unnamed package. |
| **-esa** or **-enablesystemassertions** | Enables assertions in system classes. |
| **-dsa** or **-disablesystemassertions** | Disables assertions in system classes. |

Options can be combined; the JVM processes options in command-line order before loading the relevant classes. The **-ea** option without arguments has an exception for system classes: use **-esa/-dsa** when you want to control system classes specifically.

### 7.1 Runnable Example 2: Class Option vs. Package Option

Create the file **src/lab/flags/FlagsDemo.java**:

~~~java
package lab.flags;

public class FlagsDemo {
    static class Nested {
        static boolean enabled() {
            try {
                assert false : "probe";
                return false;
            } catch (AssertionError expected) {
                return true;
            }
        }
    }

    public static void main(String[] args) {
        System.out.println("nested = " + Nested.enabled());
        System.out.println("peer = " + Peer.enabled());
    }
}

class Peer {
    static boolean enabled() {
        try {
            assert false : "probe";
            return false;
        } catch (AssertionError expected) {
            return true;
        }
    }
}
~~~

From the project directory:

~~~bash
javac -d out src/lab/flags/FlagsDemo.java
java -ea:lab.flags.FlagsDemo -cp out lab.flags.FlagsDemo
~~~

Stdout:

~~~text
nested = true
peer = false
~~~

Explanation: the **-ea:lab.flags.FlagsDemo** option enables assertions for the top-level class FlagsDemo and its nested class **FlagsDemo.Nested**, whereas **Peer** is another top-level class in the same package and therefore remains at the default (false).

Another command:

~~~bash
java -ea:lab.flags... -da:lab.flags.Peer -cp out lab.flags.FlagsDemo
~~~

Stdout:

~~~text
nested = true
peer = false
~~~

Here the **lab.flags** package is enabled first, but the specific option for the **Peer** class disables it. The result is the same, but the **source of the decision** is different.

If you only run:

~~~bash
java -ea:lab.flags... -cp out lab.flags.FlagsDemo
~~~

the result will be:

~~~text
nested = true
peer = true
~~~

Because both FlagsDemo.Nested and Peer are in the enabled package.

### 7.2 Comparing Command-Line Options and ClassLoader APIs

| Aspect | `java -ea/-da` Options | ClassLoader Methods |
| --- | --- | --- |
| Who configures it? | JVM runner / application launch script | Code holding a loader reference |
| Typical timing | Before the program runs | Before the corresponding classes are initialized |
| Scope | Can target multiple loaders via JVM options | Applies policy on the invoked loader object |
| Class/package/default levels | Has corresponding options | Has three specific setters |
| Clear all overrides? | Re-specify options at startup | **clearAssertionStatus()** on the loader |
| Effect on initialized classes? | Cannot be changed via CLI in the same run | Subsequent setters do not change the finalized state either |

The ClassLoader APIs allow a loader to actively change assertion settings associated with that loader, including overriding command-line settings when clearAssertionStatus is called. In real-world applications, you need to check which loader **actually defines** the class to avoid setting policies on a child loader when the parent is the one providing the Class.

## 8. Which ClassLoader Should Receive the Configuration?

An application may have a bootstrap loader, platform loader, application loader, and multiple plugin loaders. Each class normally has a **defining loader**; other loaders may delegate to receive the same Class object.

If you call:

~~~java
pluginLoader.setPackageAssertionStatus("shared.api", true);
~~~

but **shared.api** is defined by the parent loader through delegation, you cannot assume that the rule on pluginLoader will control assertions for a class defined by the parent. The configuration must correspond to the **loader that manages the definition and assertion policy of that class**.

When debugging:

~~~java
Class<?> type = loader.loadClass("com.example.Service");
System.out.println(type.getClassLoader());
~~~

`type.getClassLoader()` indicates the **defining loader** of the class (or null if bootstrap). Calling **loader.loadClass(name)** may return a Class defined by another loader. To apply rules accurately, you need to understand delegation and where the class will be initialized.

**An easy-to-confuse example:** a plugin loader that is child-first for internal packages, but parent-first for shared APIs. A separate assertion policy on the plugin loader may apply to the plugin's implementation classes; API classes from the parent must follow the parent's policy.

## 9. Assertion Timing Differs from When the Developer Calls the Setter

Suppose:

~~~java
Class<?> metadata = Class.forName("lab.rules.LateProbe", false, loader);
loader.setPackageAssertionStatus("lab.rules", true);
~~~

If LateProbe is **not yet initialized**, changing the policy can take effect when it is used for the first time. According to the API, **Class.forName(name, false, loader)** retrieves the Class without actively initializing it. Conversely:

~~~java
Class<?> metadata = Class.forName("lab.rules.LateProbe", true, loader);
loader.setPackageAssertionStatus("lab.rules", true);
~~~

With initialize=true, LateProbe has already been requested to initialize before the setter runs; if initialization succeeds, changing the policy afterward does not alter the finalized assertion status.

These two snippets **illustrate the API semantics** and are not standalone programs: an appropriate loader and class must already be available. Additionally, the JVM may have already initialized that class from another active use before reaching this code. Do not treat `Class.forName(..., false, ...)` as a way to revert the state of an already initialized class.

## 10. How Is `Class.desiredAssertionStatus()` Used?

The API:

~~~java
boolean desired = SomeClass.class.desiredAssertionStatus();
~~~

returns the **desired** assertion status for the class according to the applicable configuration. The word “desired” is very important: it lets you inspect the configuration from the Class API perspective, but you should not call it again after a configuration change to conclude that an **already initialized** class will change how its assert statements execute.

To verify the actual behavior of an assert statement, observe the class containing it directly (like the **enabled()** method in the example), or use an isolated test with an uninitialized class. Do not rely solely on the package name, loader name, or a configuration boolean value to judge initialized code.

If an assert contains an expression with side effects, the enabled/disabled state will cause the program to behave differently, which is precisely why you should avoid using assert for mandatory validation.

## 11. When Should Assertions Be Used, and When Not?

Assertions are appropriate for **internal invariants** that the developer believes must hold true if the code is implemented correctly, for example:

~~~java
assert index >= 0 && index < buffer.length;
assert state != null : "Internal state must exist";
~~~

For user input, mandatory validation, or system safety conditions, **do not use assert as the sole mechanism**:

~~~java
// Mandatory validation, runs even when assertions are disabled:
if (amount < 0) {
    throw new IllegalArgumentException("amount must be >= 0");
}
~~~

In production, assertions may be disabled by default or configured selectively. A correct program must continue performing its required operations regardless of the assertion policy.

Avoid:

~~~java
// WRONG: when assertions are disabled, counter++ will not execute.
assert counter++ >= 0;
~~~

Prefer separating the computation:

~~~java
counter++;
assert counter >= 0;
~~~

The last two blocks are illustrative snippets placed inside a method with an appropriate counter variable.

## 12. Common Misconceptions

### 12.1 “Setting default=true can re-enable all already initialized classes”

No. Setters apply to classes **that will be initialized**; an already initialized class has a fixed assertion state. To test a new policy, use a new uninitialized class or restart the JVM with a different configuration.

### 12.2 “Setting package=false is enough even if a class was explicitly enabled”

No. A class-specific override wins over a package rule, even the most specific package. If you need to change the policy for an uninitialized class, you must modify the class rule itself (or clear the state on the loader and reconfigure, while understanding the consequences for other classes).

### 12.3 “A parent package rule always takes precedence over a child package”

False. The package with the **most specific** name wins. For example, **app.data=true** wins over **app=false** for **app.data.deep.Model**, unless there is a class-specific rule.

### 12.4 “You can set `Outer$Inner` to enable only a nested class”

According to the **setClassAssertionStatus** contract, the call only applies to a **top-level class** name and the nested classes inside it. Using a non-top-level name does not change the actual status of the targeted class. Use the **Outer** name to control the whole group.

### 12.5 “clearAssertionStatus restores all settings from the java command”

No. The method sets the loader's default to **false** and removes the loader's package/class rules. It is not a mechanism for reverting to previous values.

### 12.6 “Having a `Class` means the assertion status is finalized”

Not necessarily. **Loading** and **initialization** are two different phases; the status is determined according to the class initialization rules. Be careful if reflection or another active use has already initialized the class beforehand.

### 12.7 “Setting a rule on a child loader definitely affects parent classes”

That cannot be assumed. Delegation may return a Class defined by the parent. Check **getClassLoader()**, how the loader delegates definitions, and when the class is initialized.

### 12.8 “AssertionError should be caught so the program keeps running in production”

In the example, catching AssertionError is only to **definitively observe the assertion status**. In application code, AssertionError typically indicates a broken internal assumption, so you should investigate and fix the logic rather than swallowing the error.

## 13. Inspection Procedure When Assertions Do Not Run

1. Confirm that the code actually contains **assert** and that the execution path passes through that statement.
2. Determine whether the class containing the assert has already been **initialized**; setters called after that point will not change behavior.
3. Check whether JVM options **-ea/-da/-esa/-dsa** are present.
4. For the loader being used, inspect its **default**, the most specific package rule, and the class rule.
5. If the class is nested, identify the exact **top-level class** governing the policy.
6. Check the **defining loader** using **Class.getClassLoader()**, especially with plugin/classloader delegation.
7. If **clearAssertionStatus()** is used, remember that it resets default=false and clears all overrides.
8. Write a small test running in a fresh JVM to avoid already initialized classes and compare the results.

In particular, do not conclude that a class is “not yet loaded” simply because an assert does not run: assertions may simply have been disabled.

## 14. Self-Check Exercises

**Question 1.** The loader's default is true; package **shop** is set to false; class **shop.Cart** is set to true. Are assertions in Cart enabled or disabled if Cart is not yet initialized?

**Answer:** Enabled. The class-level rule takes higher precedence than the package rule.

**Question 2.** Default is false; package **shop=true**, package **shop.internal=false**. Which rule does class **shop.internal.engine.Parser** use?

**Answer:** **shop.internal=false**, because this is the most specific matching package.

**Question 3.** If a class has already been initialized with assertions disabled, does calling **setClassAssertionStatus(className, true)** enable assertions for that class?

**Answer:** No; the execution state of an already initialized class does not change.

**Question 4.** To enable assertions in top-level **sample.Outer** and nested **Outer.Nested**, which API do you call?

**Answer:** **setClassAssertionStatus("sample.Outer", true)** before initialization. Do not use the string **sample.Outer$Nested** to control the nested class separately.

**Question 5.** Does **clearAssertionStatus()** restore the state from the **-ea** option?

**Answer:** No; it clears package/class rules and sets default=false on the loader.

**Question 6.** What logic bug does the statement **assert x++ > 0;** cause when assertions are disabled?

**Answer:** The expression is not evaluated, so **x++ does not run**. Assertions should not contain mandatory side effects.

**Question 7.** Why does **-ea:lab.flags.FlagsDemo** enable the nested class but not the peer class **Peer**?

**Answer:** The option targets the top-level FlagsDemo and its nested classes; Peer is an independent top-level class.

**Question 8.** A package rule was set on pluginLoader, but the class is actually defined by the parent. What should be checked?

**Answer:** Check **Class.getClassLoader()**, delegation, and where the defining loader's policy is managed; do not assume a rule on the child applies to a parent's class.

## 15. Summary

The three assertion control levels of ClassLoader are applied according to the principle:

~~~text
       class-specific rule
               ↓ wins over
       package-specific rule
        (deepest package)
               ↓ wins over
       loader's default rule
~~~

- **setDefaultAssertionStatus** sets the default value.
- **setPackageAssertionStatus** applies to a package and its subpackages; a more specific package wins.
- **setClassAssertionStatus** applies to a top-level class and its nested classes; the class rule wins over other rules.
- **clearAssertionStatus** clears rules and sets the default to false.
- Policy modifications affect classes **to be initialized**, and do not reverse the state of already initialized classes.
- JVM options **-ea/-da** allow control at launch time; applications can also proactively set policies on a loader.
- Assertions are used to check internal assumptions, **do not replace mandatory validation**, and should not have side effects.

### References

- **ClassLoader, Java SE 21** – the four assertion control methods and precedence rules: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html
- **The java Command, Java 17** – -ea, -da, -esa, -dsa options: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- **JLS §14.10 (The assert Statement), Java SE 21** – assert execution rules: https://docs.oracle.com/en/java/javase/specs/jls/se21/html/jls-14.html#jls-14.10
- **JLS §12.4 (Initialization), Java SE 21** – timing of class and interface initialization: https://docs.oracle.com/en/java/javase/specs/jls/se21/html/jls-12.html#jls-12.4
