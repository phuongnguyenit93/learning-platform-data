# Recognizing `public`, `private`, and Package Access in Java

> **Java core — language-basics / Classes and Objects**  
> **Environment:** JDK 17+, no external libraries.  
> **Goal:** Read access modifiers on classes, constructors, fields, and methods; distinguish `public`, `private`, and **package-private** (no modifier written); use public APIs to protect state; know when code in the same or different packages can access members.

## 1. The First Three Access Levels to Recognize

In Java, an *access modifier* specifies where code is allowed to use a class or member. For ordinary members:

| Declaration | Inside declaring class | Other class in same package | Unrelated class in different package |
| --- | --- | --- | --- |
| `public` | Yes | Yes | Yes, if the declaring class is also accessible |
| `private` | Yes | No | No |
| **No modifier** (*package-private*) | Yes | Yes | No |

Example illustrating the three levels:

~~~java
class Sample {
    public int shown = 10;
    private int hidden = 20;
    int sharedWithinPackage = 30; // NO access modifier.
}
~~~

- `public` allows usage from any code that has permission to see the containing class/type.
- `private` keeps the member within the access scope of the declaring class and nested structures permitted by the language; **another top-level class**, even in the same package, cannot read it directly.
- Omitting the modifier is called **package-private** or *package access*: classes in the same package can access it, even if located in different `.java` files.
- There is no Java keyword `package-private` or `default` to write before a declaration; simply **omit** the modifier.

Java also has `protected`: code in the same package can access it, and subclasses in other packages have access according to specific inheritance rules. This lesson focuses only on recognizing the three basic cases; do **not** treat `protected` as simply `public` for all subclasses in every situation.

## 2. What Is a Package, and Why It Does Not Mean "Same File"

A Java file can begin with a declaration:

~~~java
package school.model;
~~~

Classes with the same package name such as `school.model` are considered in the same package even across **multiple source files**. Conversely, two classes in different packages are not allowed to use each other's package-private members, even if they sit near each other in the directory structure.

Java uses `.` to separate segments of a package name, but being in the same package is determined by the **full package name**, not a name prefix:

- `school.model` and `school.model`: same package.
- `school.model` and `school.app`: different packages.
- `school.model` and `school.model.extra`: **also different packages**; a subpackage does not automatically inherit package-private access from a parent package.

A class without a `package` declaration belongs to the **unnamed package** (often called the *default package*) in introductory examples. When writing real applications, use named packages to organize code and avoid integration limitations.

**Do not confuse:** Being in the same **project**, same **directory**, or same **parent package** does not implicitly grant package-private access. `import` also only assists referencing by name; it **does not grant extra access permissions**.

## 3. Modifiers on Classes vs. Members Are Two Different Layers

For a **top-level class** (a class not nested inside another class), there are two levels to remember:

~~~java
public class PublicType {
    // Visible outside the package when the environment permits.
}

class PackageType {
    // Directly accessible only from the same package.
}
~~~

When placed in a separate file, a `public` top-level class must reside in a matching filename, such as `PublicType.java`. An ordinary source file cannot have two `public` top-level classes declared and validly compiled together. Do not use `private class Hidden { ... }` for a **top-level class**: the `private` modifier is invalid here. For a **nested class**, `private` can be valid.

A `public` member inside a package-private top-level class **does not make its enclosing class public**:

~~~java
class PackageType {
    public void run() {
        System.out.println("running");
    }
}
~~~

Code in another package still cannot name and use `PackageType` directly just because `run()` is declared `public`. To provide a cross-package API, the exposed class/type itself must also have sufficient access, in addition to module and compilation context conditions.

## 4. `private` Helps Encapsulate State

Introductory convention: keep mutable fields `private`, then provide public methods with validation when needed:

~~~java
class Wallet {
    private int balance;

    public Wallet(int initial) {
        if (initial < 0) {
            throw new IllegalArgumentException("initial must be non-negative");
        }
        this.balance = initial;
    }

    public int balance() {
        return balance;
    }

    public void deposit(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        balance += amount;
    }

    private boolean hasEnough(int amount) {
        return balance >= amount;
    }

    public boolean canPay(int amount) {
        return amount >= 0 && hasEnough(amount);
    }
}
~~~

`balance` and `hasEnough` are private members; code in another class cannot call `wallet.hasEnough(...)` or read `wallet.balance` directly. The methods `balance()`, `deposit(...)`, and `canPay(...)` form the public API and can be invoked through a reference to a `Wallet` object wherever `Wallet` is visible.

**Note:** `private` is language-level access control, not data encryption or a security boundary between processes. Do not assume a private field by itself protects passwords or sensitive data against all forms of inspection.

## 5. Package-Private Access: Use Intentionally

If no modifier is written on a **field**, **method**, or **constructor**, it defaults to package-private:

~~~java
class Task {
    String phase = "NEW";             // Package-private field.

    Task() {                          // Package-private constructor.
    }

    void markStarted() {              // Package-private method.
        phase = "STARTED";
    }

    public String status() {          // Public method.
        return phase;
    }

    private void resetInternally() {  // Private method.
        phase = "NEW";
    }
}
~~~

**Another class in the same package** can call `new Task()`, read `task.phase`, and call `task.markStarted()` and `task.status()`, but cannot call `task.resetInternally()` because it is private.

Package-private is often suitable for **internal helper code within the same package**. However, directly assigning a package-private field can bypass invariant checks; do not expose fields just for "convenience" when a getter or business method would be clearer.

Declaring an access modifier for a constructor is independent of other methods: a `public class Type` can have a `private` or package-private constructor. Therefore, seeing a **public class** does not automatically guarantee you can call `new Type()` from every package.

## 6. Single-File Example: Distinguishing `public`, `private`, and Package Access

The following program intentionally includes one `public` top-level class and two top-level classes **with no modifier**, so all three classes are in **the same package**. It demonstrates that another class can call package-private methods/fields, yet cannot read `private` fields.

Create file **AccessLevelsDemo.java**:

~~~java
public final class AccessLevelsDemo {
    public static void main(String[] args) {
        Account account = new Account("Lan", 100, "A7");
        System.out.println("initial=" + account.summary());
        System.out.println("publicName=" + account.owner());
        System.out.println("packageField=" + account.category);
        System.out.println("packageMethod=" + account.internalCode());
        System.out.println("readerCode="
                + SamePackageReader.readCode(account));

        account.deposit(25);
        System.out.println("afterDeposit=" + account.balance());
        account.adjustInsidePackage(5);
        System.out.println("afterPackageAdjustment=" + account.balance());
        System.out.println("privateBridge="
                + account.privateInfoThroughClass());

        Account other = new Account("Bao", 40, "A7");
        System.out.println("sameInternalId="
                + account.sameInternalId(other));
        System.out.println("sameReference=" + (account == other));

        account.category = "VIP"; // Allowed because same package.
        System.out.println("afterPackageField=" + account.summary());
        System.out.println("readerSummary="
                + SamePackageReader.readSummary(account));

        // DOES NOT COMPILE if uncommented:
        // System.out.println(account.internalId); // private.
        // account.privateTag();                    // private.
    }
}

// Package-private top-level class: neither public nor private written.
final class Account {
    private final String name;
    private int balance;
    private final String internalId;
    String category = "BASIC"; // package-private field.

    Account(String name, int balance, String internalId) {
        this.name = name;
        this.balance = balance;
        this.internalId = internalId;
    }

    public String owner() {
        return name;
    }

    public int balance() {
        return balance;
    }

    public void deposit(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount > 0");
        }
        balance += amount;
    }

    String internalCode() { // package-private method.
        return name.substring(0, 1) + "-" + category;
    }

    void adjustInsidePackage(int delta) { // package-private.
        balance += delta;
    }

    private String privateTag() {
        return "tag:" + internalId;
    }

    String privateInfoThroughClass() {
        return privateTag(); // This class itself can call private.
    }

    public boolean sameInternalId(Account other) {
        // Inside the Account class, it can read a private field
        // of ANOTHER Account object.
        return internalId.equals(other.internalId);
    }

    public String summary() {
        return name + ":" + balance + ":" + category;
    }
}

// Third class in the same package, can access package-private members.
final class SamePackageReader {
    static String readCode(Account account) {
        return account.internalCode();
    }

    static String readSummary(Account account) {
        return account.summary();
    }
}
~~~

Compile and run in the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 AccessLevelsDemo.java
java AccessLevelsDemo
~~~

**Exact expected stdout:**

~~~text
initial=Lan:100:BASIC
publicName=Lan
packageField=BASIC
packageMethod=L-BASIC
readerCode=L-BASIC
afterDeposit=125
afterPackageAdjustment=130
privateBridge=tag:A7
sameInternalId=true
sameReference=false
afterPackageField=Lan:130:VIP
readerSummary=Lan:130:VIP
~~~

**Observation:** `SamePackageReader` can call `Account.internalCode()` because the top-level classes are in the same package, even though they are different classes. `internalId` and `privateTag()` remain inaccessible directly from `AccessLevelsDemo` because they are `private`. Inside `Account` itself, `sameInternalId` can read the private field of **another `Account` object**; `private` restricts access by class, **not** only to `this`.

## 7. Across Two Packages: What Remains Accessible?

When moving to another package, access conditions become clearer. You can test two standalone files as follows.

**File `src/school/model/Student.java`:**

~~~java
package school.model;

public final class Student {
    private final int score = 8;
    String note = "class-only"; // package-private.

    public int score() {
        return score;
    }
}
~~~

**File `src/school/app/Main.java`:**

~~~java
package school.app;

import school.model.Student;

public final class Main {
    public static void main(String[] args) {
        Student student = new Student();
        System.out.println("outside=" + student.score());

        // DOES NOT COMPILE if uncommented:
        // System.out.println(student.score); // private.
        // System.out.println(student.note);  // package-private.
    }
}
~~~

Compile and run in the directory containing `src`:

~~~bash
javac -encoding UTF-8 -d out src/school/model/Student.java src/school/app/Main.java
java -cp out school.app.Main
~~~

**Exact expected stdout:**

~~~text
outside=8
~~~

`import school.model.Student;` makes the class name easier to use, but does not allow accessing `note` or `score` directly. Calling `student.score()` is valid because **both the `Student` class and the `score()` method are public**. If you change `public final class Student` to `final class Student`, the class becomes package-private and `Main` in another package can no longer use this type directly.

## 8. Distinguishing Access Errors from Other Errors

| Situation | Main cause | How to handle |
| --- | --- | --- |
| `account.internalId` from another top-level class | `private` field | Use a valid API or move logic into the owning class |
| `student.note` from `school.app` | Package-private field, different package | Consider a public API; do not bypass access with `import` |
| `new HiddenType()` from another package | Package-private top-level class | Design a needed public type or keep code inside the package |
| `new PublicType()` invalid due to hidden constructor | Public class, non-public constructor | Use a valid factory or adjust the API |
| `obj.method()` inaccessible | Private/package-private method or declaring class not visible | Check both the class and the method |
| `obj == null` then calling an instance method | `NullPointerException` at runtime; not an access modifier issue | Create an object / check for null |
| `private class X` at top level | `private` modifier invalid on a top-level class | Remove the modifier or make it a nested class |
| `cannot find symbol` for class name | Could be missing import, classpath, or typo | Verify name/package before concluding it is an access error |

A small, clear API typically uses **`private` fields** and **necessary `public` methods**, reserving package-private for members genuinely used only internally within the same package. Avoid making all fields public just for quick example code.

### Self-Check Exercises

1. In the same package, create two files `Book.java` and `BookDemo.java`. Give `Book` a package-private field and a private field; try accessing both from `BookDemo`.
2. Move `BookDemo` to another package and change `Book` to `public class Book`. Which accesses no longer compile?
3. Define a top-level class with no modifier that has a `public` method. Why can code in another package still not use that class directly?
4. Write a package-private constructor and a `public static` factory in a `public` class. When must code in another package use the factory?
5. Explain why a method of `Account` can read `other.internalId` while `SamePackageReader` cannot read the same field.

### Takeaways

**`public` opens access per the API; `private` keeps members within the declaring class/appropriate nested structure; omitting the access modifier means package-private — same package only.** Access checks consider **both the declaring type and the member**. Same package does not require same file; a subpackage is still a different package; `import` does not bypass access control. Prefer encapsulating `private` fields and providing intentional public methods.