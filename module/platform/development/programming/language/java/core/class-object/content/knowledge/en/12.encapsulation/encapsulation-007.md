# The JavaBeans Convention and Its Differences from Behavior-Oriented Design in Java

In Java Core, **encapsulation** is controlling how an object is created, observed, and has its state modified. A very familiar convention for exposing data is **JavaBeans**: *properties* are represented through methods such as `getName()`, `setName(...)`, or `isActive()`. This convention helps tools, libraries, and frameworks discover properties by name and use objects in a uniform way.

However, **a class with full getters/setters is not necessarily well-encapsulated**. If the business logic only allows "deposit", "withdraw", or "reset the entire time range", a general-purpose setter like `setBalance(...)` or two independent setters `setStart(...)` and `setEnd(...)` can expose unauthorized changes or cause an invalid intermediate state. *Behavior-oriented design* prioritizes methods that express **valid actions** and maintain the object's *invariants* itself.

This lesson accurately explains the JavaBeans convention, how introspection tools discover properties, the role of the no-argument constructor, how to use setters with validation, the advantages/disadvantages of data models and behavior-oriented design, patterns for combining the two approaches, along with standalone **Java 17+** programs with verifiable results.

## 1. Two Ways of Looking at an Object

Suppose you are modeling an account with a balance. The two APIs below demonstrate two different perspectives:

~~~java
// Data-oriented API: lets the caller set the value directly.
account.setBalanceCents(900);

// Behavior-oriented API: expresses a valid action.
account.withdraw(100);
~~~

These are **illustrative calls**; `account` is not yet defined in this snippet. The `setBalanceCents` method answers the question "what value should this field be set to?". The `withdraw` method answers the question "what business operation is permitted on this account?".

In the first case, the caller must know on its own whether the new balance is valid, whether deducting money requires checking for sufficient funds, and whether a transaction event needs to be recorded. In the second case, the class has the opportunity to keep these rules in one unified place.

**There is no conclusion that JavaBeans is wrong.** JavaBeans is useful for data exchange, tool integration, configuration, forms, or simple property models. Behavior-oriented design is useful when an object has a lifecycle, invariants, state transition rules, or business logic that must be protected.

## 2. What Is JavaBeans and What Is It Not?

**JavaBeans** is a set of conventions/specifications for reusable Java components that can be analyzed by tools. A prominent part is the **property accessor method naming pattern**, recognized by the standard introspection system in the `java.beans` package.

Common conventions:

- A `name` property typically has `public String getName()` and `public void setName(String name)`.
- A `boolean`-typed property can have `public boolean isActive()`; `getActive()` is also a normal getter form recognized depending on the signature.
- A typical JavaBeans setter is named `setX`, accepts **a single value**, and returns `void`.
- A bean serving many tools that create instances typically has a **public no-argument constructor**, after which the tool sets the properties. This is an important compatibility convention, but **not every Java class with getters must have a no-arg constructor**.
- An object may support property change events, `BeanInfo` information, bound/constrained properties, or serialization when needed; **not every bean is required to implement all of them**.

A Java class that merely has `private` fields and public methods **does not automatically become a full JavaBean meeting every convention that tools expect**. Conversely, a valid domain entity may not want to expose every property via setters.

Do not equate:

| Term | Primary Meaning |
| --- | --- |
| Java class | Declaration of type and behavior in the Java language |
| POJO (*Plain Old Java Object*) | Ordinary Java object, without implying mandatory adherence to JavaBeans |
| JavaBean | Component adhering to appropriate bean conventions, especially properties/introspection |
| DTO (*Data Transfer Object*) | Data type used to transfer information across a boundary |
| Domain entity | Object modeling a business entity, typically having identity/invariants |
| Value object | Object representing a value, typically suited to immutability and comparison by value |

**JavaBean, DTO, entity, and value object are concepts along different dimensions.** A DTO can be written following JavaBeans; an entity can also have JavaBeans accessors; an immutable `record` can serve as a DTO without following the classic JavaBeans setter pattern.

## 3. Basic Property Naming Rules

The table below assumes the methods are **public**, have valid signatures, and are inspected by an introspector following JavaBeans conventions:

| Method | Recognized Property | Role |
| --- | --- | --- |
| `String getName()` | `name` | Getter |
| `void setName(String value)` | `name` | Setter |
| `int getStock()` | `stock` | Getter |
| `boolean isActive()` | `active` | Boolean getter |
| `void setActive(boolean value)` | `active` | Setter |
| `long getBalanceCents()` | `balanceCents` | Getter |
| `void receive(int amount)` | Not automatically property `amount` | Behavioral method |
| `String name()` | Not a classic JavaBeans getter | Accessor in another style |

The field name **does not have to match** the property name:

~~~java
private String internalTitle;

public String getName() {
    return internalTitle;
}

public void setName(String value) {
    internalTitle = value;
}
~~~

This is an illustrative snippet placed inside a class. The property exposed to the introspector is `name`, even though the field name is `internalTitle`. A property can also **be computed** without needing a corresponding field, for example `getFullName()` concatenating `firstName` and `lastName`.

**A property is a contract through methods**, not direct access rights to a field. That allows validating or computing the value when the getter/setter is called.

## 4. A JavaBean with Getters, Setters, and Additional Behavior

Create a standalone file **`JavaBeanIntrospectionDemo.java`**. The program uses Java's `Introspector` and `PropertyDescriptor` APIs to display the exact properties discovered by standard tools.

~~~java
import java.beans.BeanInfo;
import java.beans.Introspector;
import java.beans.PropertyDescriptor;
import java.util.Map;
import java.util.TreeMap;

public class JavaBeanIntrospectionDemo {
    public static class ProductBean {
        private String name;
        private boolean active;
        private int stock;

        public ProductBean() {
            this.name = "Chưa đặt";
            this.active = true;
            this.stock = 0;
        }

        public String getName() {
            return name;
        }

        public void setName(String name) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("name không hợp lệ");
            }
            this.name = name.strip();
        }

        public boolean isActive() {
            return active;
        }

        public void setActive(boolean active) {
            this.active = active;
        }

        public int getStock() {
            return stock;
        }

        public void receive(int amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("amount phải dương");
            }
            stock = Math.addExact(stock, amount);
        }
    }

    public static void main(String[] args) throws Exception {
        ProductBean bean = new ProductBean();
        bean.setName("  Bút  ");
        bean.receive(5);

        System.out.println("value=" + bean.getName()
                + ", active=" + bean.isActive()
                + ", stock=" + bean.getStock());

        BeanInfo info = Introspector.getBeanInfo(
                ProductBean.class, Object.class);
        Map<String, String> properties = new TreeMap<>();

        for (PropertyDescriptor descriptor
                : info.getPropertyDescriptors()) {
            String getter = descriptor.getReadMethod() == null
                    ? "-" : descriptor.getReadMethod().getName();
            String setter = descriptor.getWriteMethod() == null
                    ? "-" : descriptor.getWriteMethod().getName();
            properties.put(descriptor.getName(),
                    getter + "/" + setter);
        }

        properties.forEach((name, methods) ->
                System.out.println(name + "=" + methods));
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac -encoding UTF-8 JavaBeanIntrospectionDemo.java
java JavaBeanIntrospectionDemo
~~~

**Exact stdout:**

~~~text
value=Bút, active=true, stock=5
active=isActive/setActive
name=getName/setName
stock=getStock/-
~~~

### Analysis of Introspection Results

- `ProductBean` has a no-argument constructor `public ProductBean()`, creating a valid initial state.
- `name` has the `getName/setName` pair: a **read/write** property.
- `active` has `isActive/setActive`: a **read/write** boolean property.
- `stock` only has `getStock`: a **read-only property under the JavaBeans pattern**.
- `receive(int)` is a stock-receiving behavior; it is **not** reported as a property.
- `Introspector.getBeanInfo(ProductBean.class, Object.class)` excludes methods from `Object`, preventing the `class` property from `getClass()` from appearing.
- `TreeMap` sorts property names alphabetically, so the last three lines have a fixed order: `active`, `name`, `stock`.

The important point: the class both has JavaBeans-style properties for tools to discover and has the **behavioral method `receive`**. The two styles can **be combined** rather than being mutually exclusive. Omitting `setStock` is an intentional encapsulation decision.

## 5. Getters and Setters Do Not Necessarily Correspond to a Field

A property can have a composite getter:

~~~java
public String getFullName() {
    return firstName + " " + lastName;
}
~~~

This is an **illustrative method**, assuming the class has `firstName` and `lastName`. An introspector can recognize a read-only `fullName` property, even though `private String fullName` does not exist.

Similarly, a setter can apply validation or normalization before assigning:

~~~java
public void setName(String name) {
    if (name == null || name.isBlank()) {
        throw new IllegalArgumentException("name không hợp lệ");
    }
    this.name = name.strip();
}
~~~

No JavaBeans rule forces a setter to contain only **a bare field assignment**. However, tools calling the setter may encounter exceptions, so the validation contract and how the framework handles exceptions still need to be considered.

Distinguish four kinds of properties:

| Kind | Method Set | Remarks |
| --- | --- | --- |
| Read/write | `getX()` + `setX(T)` | Common in forms/configs/DTOs |
| Read-only | Only `getX()` or `isX()` | Does not expose a corresponding setter |
| Write-only | Only `setX(T)` | Limited usefulness; tools cannot read the value back directly |
| Computed | Getter constructs the result from other fields | Does not require a field with the same name |

To preserve invariants, sometimes you should not expose a setter for a property even if tools can display it. "A tool recognizing a property" and "a caller being allowed to modify state" are two different questions.

## 6. Easily Confused Details in JavaBeans Naming

**With boolean:** the primitive `boolean` type typically uses `isActive()`. A `getActive()` getter also follows the `getX` pattern. For the `Boolean` wrapper, do not assume every introspector will treat `Boolean isActive()` as a standard `is` getter: the traditional JavaBeans rule for `isX` requires a primitive `boolean` return type. If you want broad compatibility for a nullable wrapper, `getActive()` is clearer.

**With capitalization:** a property name is not simply "take the characters after get and lowercase the first letter" in all cases. `Introspector.decapitalize` leaves a name unchanged if it starts with **two uppercase letters**. Therefore, `getURL()` is typically the `URL` property, whereas `getName()` is `name`.

**With setters having a non-void return type:** fluent APIs like `Builder setName(String)` or `withName(String)` can be useful in code, but are not considered standard setters by every classic JavaBeans introspector. If a specific tool recognizes fluent accessors, that is **a convention of that tool** and should not be confused with all JavaBeans tools.

**With getters taking parameters:** `getName(Locale locale)` is not a simple property getter following the `getName()` pattern. A regular property must have a no-argument read method.

**With overloaded setters:** multiple `setValue(...)` methods accepting inconsistent types can prevent introspection tools from accurately determining the property type. Avoid ambiguous overload sets, especially for JavaBeans used for automatic binding.

Example verifying the naming rules:

~~~java
System.out.println(
        java.beans.Introspector.decapitalize("Name")); // name
System.out.println(
        java.beans.Introspector.decapitalize("URL"));  // URL
~~~

This is an illustrative snippet placed inside a method. A codebase with multiple binding tools should choose **a stable naming convention**, and test directly against the library consuming the bean rather than inferring from field names.

## 7. No-Argument Constructor: Convenient for Tools, but with Trade-Offs

Many traditional JavaBeans tools expect to be able to instantiate an object using a no-argument constructor and then invoke setters sequentially:

~~~java
ProductBean product = new ProductBean();
product.setName("Bút");
product.setActive(true);
~~~

In `ProductBean`, the constructor creates a **valid** default state. However, not every business object has a meaningful default state. For `BankAccount`, if the account ID and initial balance are mandatory data, allowing `new BankAccount()` and leaving `accountId == null` can break the invariant right at creation time.

Two options to consider:

1. **JavaBean for input/transfer data:** an incomplete state can be intentionally represented in a DTO, and then validated as a whole before being converted into a domain object.
2. **Always-valid domain object:** the constructor or factory requires the mandatory values upfront; there is no need to create a no-arg constructor merely for a convenience convention if the business logic does not permit it.

Some modern frameworks support constructor binding, factories, records, or custom instantiation mechanisms. **Actual capabilities depend on the framework and configuration**; you cannot conclude that every library requires a no-arg constructor or that every library supports records.

**Principle:** choose the object structure based on its role; if a mutable JavaBean type is needed to interact with tools, treat it as a separate data model rather than weakening the invariants of the domain object.

## 8. Behavior-Oriented Design: Methods Expressing an Action

An object with business logic should typically provide operations such as:

~~~java
account.deposit(250);
account.withdraw(100);
cart.addProduct(product, 2);
reservation.cancel();
~~~

These are **illustrative** calls, not a standalone program. They tell the reader the **intent** of the operation rather than how to write to a field.

A behavioral method is typically responsible for:

- Checking the **preconditions** of the request and the current state.
- Computing the resulting state while accounting for invariants, overflow, and business limits.
- Updating fields only when the operation is permitted.
- Producing, if needed, a meaningful result or event that the caller can handle.
- Rejecting an invalid command via a declared error mechanism, rather than silently storing invalid data.

This design places rules **close to where the data is owned**. The caller does not need to compute the new balance itself and call a general-purpose setter. The `private` keyword guards direct access paths; **behavioral methods** guard valid modification paths.

## 9. Complete Example: An Account Encapsulating Behavior Instead of Exposing a Balance Setter

Create the file **`AccountBehaviorDemo.java`**:

~~~java
final class LedgerAccount {
    private final String id;
    private long balanceCents;

    LedgerAccount(String id, long initialBalanceCents) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id không hợp lệ");
        }
        if (initialBalanceCents < 0) {
            throw new IllegalArgumentException("số dư âm");
        }
        this.id = id;
        this.balanceCents = initialBalanceCents;
    }

    public String getId() {
        return id;
    }

    public long getBalanceCents() {
        return balanceCents;
    }

    public void deposit(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("số tiền phải dương");
        }
        long next = Math.addExact(balanceCents, amount);
        balanceCents = next;
    }

    public void withdraw(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("số tiền phải dương");
        }
        if (amount > balanceCents) {
            throw new IllegalArgumentException("không đủ số dư");
        }
        balanceCents -= amount;
    }
}

public class AccountBehaviorDemo {
    public static void main(String[] args) {
        LedgerAccount account = new LedgerAccount("A-01", 1000);
        System.out.println("start=" + account.getBalanceCents());

        account.deposit(250);
        System.out.println("after deposit=" + account.getBalanceCents());

        try {
            account.withdraw(2000);
        } catch (IllegalArgumentException ex) {
            System.out.println("reject=" + ex.getMessage());
        }
        System.out.println("after reject=" + account.getBalanceCents());

        account.withdraw(500);
        System.out.println("after withdraw=" + account.getBalanceCents());

        try {
            account.deposit(Long.MAX_VALUE);
        } catch (ArithmeticException ex) {
            System.out.println("reject overflow");
        }
        System.out.println("final=" + account.getBalanceCents());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 AccountBehaviorDemo.java
java AccountBehaviorDemo
~~~

**Exact stdout:**

~~~text
start=1000
after deposit=1250
reject=không đủ số dư
after reject=1250
after withdraw=750
reject overflow
final=750
~~~

### Why Does This API Not Have `setBalanceCents`?

If the caller were allowed `account.setBalanceCents(-50)`, the class author would have to guard the non-negative condition. Yet even if the setter checks for non-negativity, the caller could still bypass business meaning: for example, changing from 1000 to 500 without an explicit "withdraw 500" operation.

In the example:

- `deposit(amount)` checks that the deposit amount is positive and uses `Math.addExact` to detect overflow **before assigning the field**.
- `withdraw(amount)` validates the request and checks for sufficient funds before reducing the balance.
- `getBalanceCents()` is a **getter for reading state**; it does not grant permission to update the balance.
- `id` is `final`, supplied at creation time, and has no setter to change the account ID.
- When `withdraw(2000)` or `deposit(Long.MAX_VALUE)` fails, the previous value remains unchanged according to the specific logic of the program.

In this model, JavaBeans-style getters remain useful for **reading**, whereas write operations are behaviors with their own names and contracts. This is an instructional example of an in-memory domain object, **not a concurrent or persistent transactional banking system**.

## 10. A Setter Even with Validation Can Still Be Too Broad

Consider a setter:

~~~java
public void setBalanceCents(long amount) {
    if (amount < 0) {
        throw new IllegalArgumentException("balance âm");
    }
    balanceCents = amount;
}
~~~

This is an illustrative method inside a class with the `balanceCents` field. This setter helps prevent negative numbers, but does not enforce other business constraints such as:

- Is deducting money allowed to occur if a withdrawal request has not been verified?
- Does setting a new balance require recording the source of the change?
- Are there per-transaction amount limits or locked account states?
- Is it necessary to ensure this change is tied to a stored transaction?

When the business logic requires meaningful behaviors, simply checking the domain of the **resulting value** may not be enough. You should express `deposit`/`withdraw` (and other necessary behaviors) so that each operation has clear preconditions/postconditions.

Conversely, for a form DTO, `setBalanceCents` is sometimes solely intended to receive raw data for display or processing in a subsequent step. **The role of the class** determines whether a setter is appropriate, not whether the setter name itself is good or bad.

## 11. Cross-Field Invariants: Two Independent Setters Cause Ordering Issues

Suppose an integer interval must satisfy `0 <= start <= end`. Two independent setters can be valid **step by step individually**, yet force the caller to remember **the exact update order**, or even make a valid transition awkward to use.

Create the complete file **`WindowDesignDemo.java`**:

~~~java
class WindowBean {
    private int start = 2;
    private int end = 5;

    public int getStart() {
        return start;
    }

    public int getEnd() {
        return end;
    }

    public void setStart(int start) {
        if (start < 0 || start > end) {
            throw new IllegalArgumentException("window không hợp lệ");
        }
        this.start = start;
    }

    public void setEnd(int end) {
        if (end < start) {
            throw new IllegalArgumentException("window không hợp lệ");
        }
        this.end = end;
    }

    public String describe() {
        return "[" + start + "," + end + "]";
    }
}

final class Window {
    private int start;
    private int end;

    Window(int start, int end) {
        validate(start, end);
        this.start = start;
        this.end = end;
    }

    private static void validate(int start, int end) {
        if (start < 0 || end < start) {
            throw new IllegalArgumentException("window không hợp lệ");
        }
    }

    public void moveTo(int newStart, int newEnd) {
        validate(newStart, newEnd);
        start = newStart;
        end = newEnd;
    }

    public String describe() {
        return "[" + start + "," + end + "]";
    }
}

public class WindowDesignDemo {
    public static void main(String[] args) {
        WindowBean bean = new WindowBean();
        System.out.println("bean=" + bean.describe());

        try {
            bean.setStart(7);
        } catch (IllegalArgumentException ex) {
            System.out.println("setter blocked=" + ex.getMessage());
        }

        bean.setEnd(9);
        bean.setStart(7);
        System.out.println("bean after ordered setters="
                + bean.describe());

        Window window = new Window(2, 5);
        window.moveTo(7, 9);
        System.out.println("window=" + window.describe());

        try {
            window.moveTo(10, 8);
        } catch (IllegalArgumentException ex) {
            System.out.println("window rejected=" + ex.getMessage());
        }
        System.out.println("window after reject="
                + window.describe());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 WindowDesignDemo.java
java WindowDesignDemo
~~~

**Stdout:**

~~~text
bean=[2,5]
setter blocked=window không hợp lệ
bean after ordered setters=[7,9]
window=[7,9]
window rejected=window không hợp lệ
window after reject=[7,9]
~~~

`WindowBean` is a class with getters/setters following the JavaBeans pattern, yet updating `start` before `end` from `[2,5]` to `[7,9]` is rejected because `start=7` temporarily exceeds `end=5`. The caller is forced to call `setEnd(9)` first and only then `setStart(7)`.

In `Window`, the `moveTo(7,9)` method accepts **the entire target state**, checks the cross-field condition **once**, and then updates. When `moveTo(10,8)` fails, both fields remain unchanged.

**Note on multithreading:** the two assignments `start = ...; end = ...;` inside `moveTo` do not automatically become an atomic transaction when multiple threads are involved. If the object is shared across threads, reading/updating must be synchronized, or an immutable representation must be published atomically as appropriate.

## 12. Where Should You Keep Getters/Setters and Where Should You Avoid Them?

A guiding table:

| Context | Getter | Setter | Behavioral Method |
| --- | --- | --- | --- |
| Simple input/output DTO | Useful for binding tools | May be appropriate | Typically does not contain much business logic |
| Configuration bean | Useful for admin tools | Appropriate if adjustment is needed | May need `reload`, `validate` |
| Domain entity with strong invariants | Selective getters | Limit general-purpose setters | Prioritize valid behaviors |
| Immutable value object | Query state | Usually no setters | `withX`/return a new value |
| Resource-managing object | Limited state getters | Avoid arbitrary setters | `open`, `close`, `start`, `stop` |
| Form display model | Needs to read/write form data | May be appropriate | Holistic validation before applying |

A domain object can still serve as a **data source for display** via getters or a DTO projection, without needing to expose every setter. A DTO can hold invalid data while the user is typing and only convert into a domain object once validation succeeds.

Choose based on **the class's responsibility**; do not automatically apply one set of rules to every class in the application.

## 13. Using a JavaBean for Input Data and Creating a Valid Domain Object

Separating externally received data from domain objects can help both stay compatible with JavaBeans tools and protect business invariants.

Example of a bean serving input data:

~~~java
public class AccountFormBean {
    private String id;
    private Long initialBalanceCents;

    public AccountFormBean() {
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public Long getInitialBalanceCents() {
        return initialBalanceCents;
    }

    public void setInitialBalanceCents(Long initialBalanceCents) {
        this.initialBalanceCents = initialBalanceCents;
    }
}
~~~

This is a **valid class definition** if saved as `AccountFormBean.java`. Using `Long` instead of `long` can represent the scenario where a form **does not yet have a value** (`null`). Because the bean has a no-argument constructor and public getters/setters, it fits many JavaBeans-style binding tools.

At the conversion boundary, the application logic needs to check both `id` and `initialBalanceCents` before calling:

~~~java
if (form.getInitialBalanceCents() == null) {
    throw new IllegalArgumentException("thiếu số dư");
}
LedgerAccount account = new LedgerAccount(
        form.getId(), form.getInitialBalanceCents());
~~~

This snippet is **illustrative usage code**, with `form` being an `AccountFormBean` instance and `LedgerAccount` from section 9. The domain object's constructor still checks for a valid `id` and non-negative balance. If the balance is missing, checking for null at the boundary avoids unboxing that causes a confusing `NullPointerException`.

Advantage of this separation: the user or framework can populate the form step by step, yet the domain object **never needs to be exposed in an initialized state missing mandatory fields**.

**Trade-off:** there is an extra conversion step and two data types. For a very small application, both types might not be necessary; however, when binding and invariants have different goals, the separation makes the contract clearer.

## 14. `final`, Immutable Objects, and Records Are Not Traditional Setter-Based JavaBeans

A class with `final` fields and no setters is a way to represent an object whose state is hard to reassign after initialization. Java 17 has `record`:

~~~java
record ProductView(String sku, String name, long priceCents) {
    ProductView {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku sai");
        }
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name sai");
        }
        if (priceCents <= 0) {
            throw new IllegalArgumentException("price sai");
        }
    }

    ProductView withPrice(long newPriceCents) {
        return new ProductView(sku, name, newPriceCents);
    }
}
~~~

This is a **valid record definition**, without `main`. The generated accessors are named `sku()`, `name()`, and `priceCents()` rather than `getSku()`, `getName()`, and `getPriceCents()` as in the classic JavaBeans pattern. A record **has no normal setters**, and record components cannot be reassigned.

Whether a framework supports records for serialization/binding depends on the framework's capabilities/version; do not assume that traditional `java.beans.Introspector` recognizes record accessors as JavaBeans property getters.

The `withPrice` method creates and returns a **new record**, causing the constructor to re-check the invariants. A caller wanting to apply the result must write:

~~~java
ProductView current = new ProductView("P1", "Bút", 5000);
current = current.withPrice(7000);
~~~

Not using getters/setters does not mean losing encapsulation: for value objects, **immutability and validation at creation time** often protect state more effectively than many setters.

## 15. Do Not Let Getters Expose Mutable Data

Even when only getters exist, encapsulation can still be broken if a getter directly returns a modifiable collection or array.

~~~java
class LeakyBean {
    private final java.util.List<String> tags =
            new java.util.ArrayList<>();

    public java.util.List<String> getTags() {
        return tags;
    }
}
~~~

This is a valid illustrative class. A caller invoking `bean.getTags().add(null)` can modify the **internal** list even without `setTags` and with a `private final` field.

To protect invariants:

- Copy mutable data **when receiving** it in constructors/setters.
- Consider returning an **unmodifiable snapshot** when reading.
- For primitive arrays, you can clone/copy in both directions.
- For lists containing mutable objects, copying the list is only a **shallow copy**; you still need to consider ownership of the element objects.
- Do not confuse `Collections.unmodifiableList(list)` (a view over the backing list) with an independent snapshot in every situation.

This holds true for JavaBeans, domain entities, and records alike. **A getter does not automatically guarantee read-only semantics across the entire object graph.**

## 16. Runnable Example: A Bean with a Collection Without Exposing an Alias

Create the file **`SafeCollectionBeanDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class SafeCollectionBeanDemo {
    public static class TagsBean {
        private List<String> tags = List.of();

        public TagsBean() {
        }

        public List<String> getTags() {
            return tags;
        }

        public void setTags(List<String> tags) {
            this.tags = List.copyOf(tags);
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("java");

        TagsBean bean = new TagsBean();
        bean.setTags(source);
        source.add("oop");

        System.out.println("source=" + source);
        System.out.println("bean=" + bean.getTags());

        try {
            bean.getTags().add("unsafe");
        } catch (UnsupportedOperationException ex) {
            System.out.println("getter blocks mutation");
        }

        try {
            bean.setTags(java.util.Arrays.asList("java", null));
        } catch (NullPointerException ex) {
            System.out.println("reject null element");
        }

        System.out.println("final=" + bean.getTags());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 SafeCollectionBeanDemo.java
java SafeCollectionBeanDemo
~~~

**Stdout:**

~~~text
source=[java, oop]
bean=[java]
getter blocks mutation
reject null element
final=[java]
~~~

`List.copyOf(source)` provides a list that **forbids modification via its API** and does not change when the caller adds elements to `source`. When attempting to pass a null element to `List.copyOf`, the method throws a `NullPointerException` before the `this.tags = ...` assignment completes, so `tags` retains its previous data.

**Limitation:** `List.copyOf` does not deep-copy individual elements. The example uses immutable `String`, so external changes cannot modify an element's contents in place. For `List<MutableItem>`, you must further consider the immutability/copying of `MutableItem`.

## 17. Bound Properties and Change Notifications in JavaBeans

Beyond getters/setters, JavaBeans also supports the notion of a **bound property**: when a property value changes, the object can emit a `PropertyChangeEvent` to registered listeners. The standard library provides `PropertyChangeSupport`.

Create the file **`BeanChangeNotificationDemo.java`**:

~~~java
import java.beans.PropertyChangeListener;
import java.beans.PropertyChangeSupport;

public class BeanChangeNotificationDemo {
    public static class SettingsBean {
        private final PropertyChangeSupport changes =
                new PropertyChangeSupport(this);
        private int volume = 50;

        public SettingsBean() {
        }

        public int getVolume() {
            return volume;
        }

        public void setVolume(int next) {
            if (next < 0 || next > 100) {
                throw new IllegalArgumentException("volume ngoài 0..100");
            }
            int old = volume;
            if (old == next) {
                return;
            }
            volume = next;
            changes.firePropertyChange("volume", old, next);
        }

        public void addPropertyChangeListener(
                PropertyChangeListener listener) {
            changes.addPropertyChangeListener(listener);
        }

        public void removePropertyChangeListener(
                PropertyChangeListener listener) {
            changes.removePropertyChangeListener(listener);
        }
    }

    public static void main(String[] args) {
        SettingsBean bean = new SettingsBean();
        bean.addPropertyChangeListener(event ->
                System.out.println(event.getPropertyName()
                        + ": " + event.getOldValue()
                        + "->" + event.getNewValue()));

        bean.setVolume(70);
        bean.setVolume(70);

        try {
            bean.setVolume(150);
        } catch (IllegalArgumentException ex) {
            System.out.println("reject=" + ex.getMessage());
        }
        System.out.println("volume=" + bean.getVolume());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 BeanChangeNotificationDemo.java
java BeanChangeNotificationDemo
~~~

**Stdout:**

~~~text
volume: 50->70
reject=volume ngoài 0..100
volume=70
~~~

In the example, `setVolume(70)` is valid: the field is updated and then the listener receives an event describing `50 -> 70`. The second call sets `70` when it is already `70`, so the method skips the update and does not fire an event. `setVolume(150)` is rejected by validation **before modifying the field**.

**Not every JavaBean must have `PropertyChangeSupport`.** This is an optional capability when an application needs to observe changes, such as in admin tools or user interfaces. An advanced variant is a **constrained property** with `VetoableChangeListener` so listeners can reject changes under the JavaBeans contract.

**Important note:** `firePropertyChange` can invoke listeners in the calling context of the setter. If a listener throws an unchecked exception, a field change that has already been performed **does not automatically roll back**. If multiple threads are involved, you must design proper protection for fields, event ordering, and listeners; the presence of `PropertyChangeSupport` does not automatically make all bean methods thread-safe.

## 18. How Do Frameworks and Automated Tools Use JavaBeans?

Some tools use **reflection** or **introspection** to identify properties and then read/write them:

~~~text
Information from form / configuration / decoded data
                         |
                         v
  Identify property names: "name", "active", ...
                         |
                         v
          Find matching read/write methods
                         |
                         v
       Invoke setter / constructor / factory
                         |
                         v
          Data object in the application
~~~

The diagram above is a conceptual model. **Each library has different policies**: some use getters/setters, while others use fields, annotations, record components, constructor binding, or a combination. You cannot infer that every serialization, ORM, or UI library always follows a single JavaBeans mechanism.

When a framework needs setters to *bind* a DTO, **do not expose public setters on every domain entity just for that reason**. You can use a boundary data class with the conventions the tool expects, and then convert the validated data into a domain object with behavior.

Questions to ask when choosing an integration approach:

1. Does the tool use fields, JavaBeans getters/setters, or constructors?
2. Is a no-argument constructor required?
3. Does calling individual setters leave the object in an invalid intermediate state?
4. If a setter throws `IllegalArgumentException`, what message does the framework turn that error into?
5. Does it support immutable objects/`record`?
6. Which properties truly need to be exposed externally?
7. Where and when are cross-field constraints checked?

Reading the documentation for the exact version of the framework you are using is more reliable than guessing from the word "Bean".

## 19. Validation at Creation Time and Update Time: Rules Applicable to Both Models

Whether designed with JavaBeans or behavior-oriented design, a domain object exposed as **valid** still needs to protect its invariants:

~~~text
CREATION:
  Validate mandatory data
  -> normalize according to the contract
  -> assign valid state

UPDATE:
  Validate request
  -> check current state
  -> compute resulting state
  -> verify all invariants
  -> update

FAILURE:
  If promising "errors do not change state", avoid modifying fields before an error is raised
~~~

For a setter like `setName`, simple per-field validation may suffice. For an operation like `withdraw`, you must also know the current balance. For two related fields `start/end`, you need to validate them **together**.

An operation that modifies multiple fields should compute the validated values before assigning:

~~~java
public void updateDetails(String nextName, long nextPrice) {
    String checkedName = validateName(nextName);
    long checkedPrice = validatePrice(nextPrice);
    this.name = checkedName;
    this.priceCents = checkedPrice;
}
~~~

This is an **illustrative method** belonging to a hypothetical class where `validateName`, `validatePrice`, and the corresponding fields are already defined. This snippet only demonstrates how to centralize validation; it is not a standalone program.

**Do not confuse sequential validation with a multithreaded transaction.** Even when validating first and assigning afterward, an object shared across different threads may still need locks, atomic updates, or an appropriate ownership model.

## 20. Side Effects, Data Ownership, and Encapsulation

Behavior-oriented design often raises the question of **who owns mutable state**. A class controls its fields, yet if it directly returns a mutable `Map`, `List`, or array, the caller can bypass behavioral methods by mutating the data through an alias.

A trustworthy API needs to distinguish:

- **Reading data:** getters return immutable scalars, copies, or views according to the contract.
- **Controlled updates:** behavioral methods preserve invariants before and after.
- **Mutable inputs:** do you store the reference passed by the caller or copy it?
- **Mutable outputs:** do you return an internal object or a snapshot?
- **Callbacks/events:** do you invoke external code right during an update, and what happens if a listener fails?
- **Multithreading:** is state shared? Do update operations have appropriate atomicity/visibility?

A well-validated JavaBeans setter can still be the right API for configuration. A method with a very "business-sounding" name that ignores invariants is still a poor API. **Method names suggest intent; the implementation must actually uphold the contract.**

## 21. Guidelines for Choosing a Design in a Project

Ask yourself the following questions:

| Question | If the Answer Is "Yes" | Typically Suitable Approach |
| --- | --- | --- |
| Is the object a form/DTO for tools to instantiate and populate property by property? | Yes | JavaBeans properties or a binding model matching the tool |
| Does the object have strong invariants and must never exist with missing data? | Yes | Constructor/factory validating mandatory inputs |
| Does a change need to inspect the old state and check business conditions? | Yes | Behavioral methods instead of general-purpose setters |
| Must multiple fields change together to preserve an invariant? | Yes | A grouped update operation |
| Do you want to keep multiple before/after versions of data? | Yes | Immutable value object, record, or `withX` |
| Does the UI need to be notified when a property changes? | Yes | Bound property/event support per contract |
| Is there a shared mutable list/array? | Yes | Defensive copying and clear ownership |
| Is the API accessed concurrently? | Yes | Dedicated synchronization/atomic update design |

**Practical tip:** you do not have to turn every class into a JavaBean, nor do you need to turn every getter into a behavioral method. You can have `OrderFormBean` for the UI screen, `Order` protecting `place/cancel` operations, and `OrderView`/a record for read-only results. This separation introduces extra classes and conversions, so weigh it against the project's complexity.

## 22. Common Mistakes

| Mistake | Why It Is Risky | How to Improve |
| --- | --- | --- |
| Thinking a JavaBean is any class with `getX/setX` | Ignores property semantics, introspection, and bean roles | Understand the convention and the tools in use |
| Auto-generating getters/setters for every domain field | Opens up state transitions that violate business logic | Expose only the operations needed |
| Treating `private` fields as complete encapsulation | Setters or getters exposing aliases still break invariants | Control every update path |
| Exposing `setBalance` when business logic only allows deposit/withdraw | Callers set state directly while bypassing business meaning | `deposit`/`withdraw` |
| Using two setters when an invariant spans two fields | Callers must know update ordering; easy to create invalid intermediate states | A single method `moveTo(start,end)` |
| Assuming a class is immutable just because it only has getters | Getters may return internal mutable lists/arrays | Defensive copy/immutable components |
| Thinking `final List` makes elements immutable | `final` only prevents reassigning the field reference | Protect the objects inside |
| Using `Boolean isActive()` and assuming every tool recognizes it | Traditional `isX` expects primitive boolean | Use `getActive()` for wrappers when needed |
| Assuming `getURL()` produces the name `uRL` | Special decap rule applies when the first two letters are uppercase | Verify via `Introspector` |
| Using fluent setters and expecting every bean tool to recognize them | Classic setter convention typically uses `void` | Follow the signatures the tool requires |
| Adding a no-arg constructor that creates an invalid domain object | Domain object exists without required state | Use a separate DTO or a parameterized constructor |
| Validating setters individually while ignoring relationships between fields | Can produce invalid cross-field invariants | Validate the resulting state as a whole |
| Assuming PropertyChangeSupport rolls back automatically | A listener may fail after the field has already been modified | Define update ordering and error handling |
| Thinking a record is automatically a classic setter-based JavaBean | Accessor `name()` differs from `getName()`, and there are no setters | Use record-capable binding or a compatible DTO |
| Thinking `private`/JavaBeans automatically guarantees thread safety | Multiple threads can still invoke setters/behaviors concurrently | Protect the entire read–compute–write operation |

## 23. Testing: Verify Both Conventions and Invariants

For `JavaBeanIntrospectionDemo`, distinguish two kinds of tests.

**Testing JavaBeans conventions:**

- `getName` getter and `setName` setter exist with standard parameter/return types.
- `isActive` exists for boolean along with `setActive`.
- The `stock` property is read-only according to `Introspector`.
- Property names after introspection follow the convention, without confusing `getURL` with `getName`.
- The public no-argument constructor creates the bean in an allowed state.

**Testing object contracts:**

- `setName(null)` or blank strings are rejected.
- `receive(5)` increases stock by exactly 5.
- `receive(-1)` and operations causing overflow are rejected before changing stock.
- Getters do not return a mutable alias when the contract requires a snapshot.
- If bound properties exist, events are emitted only on changes accepted by design.

For `LedgerAccount`, test that `withdraw` does not allow withdrawing more than the balance, `deposit` rejects non-positive values, and the state stays non-negative after operations; there is **no** need for a test checking "whether setBalance works" because the API **intentionally has no setter**.

For `Window`, test that `moveTo(7,9)` is valid and `moveTo(10,8)` is rejected **without changing either field**.

Some bugs are not caught by simply checking "the method call did not throw an exception". Assert the **exact state after the call**, the **appropriate exception**, and the **state after failure**.

## 24. Self-Practice Exercises

**Exercise 1.** What property do `public boolean isAvailable()` and `public void setAvailable(boolean v)` get recognized as by a JavaBeans introspector? If only `getCount()` exists without a setter, what kind of property is it?

**Exercise 2.** A class has a `private String title` field but exposes `getName()` and `setName(...)`. Is the JavaBeans property name `title` or `name`? Why?

**Exercise 3.** A configuration class has `public Settings()`, `getTimeout()`, and `setTimeout(int)`. When is this style of API more reasonable than behavioral methods?

**Exercise 4.** An account has a public `setBalance(long)`. Why does merely rejecting negative numbers fail to adequately protect deposit/withdrawal semantics?

**Exercise 5.** Suppose you want to change the interval `[2,5]` to `[7,9]`. Why might calling `setStart(7)` before `setEnd(9)` be rejected in an invariant-checking class? Propose an alternative method.

**Exercise 6.** A getter `getTags()` returns the internal `ArrayList` directly. Does `private final` on the field prevent callers from modifying the list? What should you do instead?

**Exercise 7.** In a system receiving form data, is it a good idea to use a JavaBean for incomplete input state and then convert it into a domain object through validation? Explain the trade-offs.

**Exercise 8.** Does `getURL()` typically produce the property `URL` or `uRL`? What does `getName()` produce? Which mechanism determines this?

**Exercise 9.** Between `Boolean getReady()` and `Boolean isReady()`, which form is the safer JavaBeans getter for a nullable wrapper in traditional tools?

**Exercise 10.** The `SettingsBean` class emits a `PropertyChangeEvent` in `setVolume`. If a listener throws an error after the field has already been updated, does Java automatically roll back `volume`?

**Exercise 11.** A `record PersonView(String name)` has the accessor `name()`. Why should you not assume that a tool that only understands `getName()` will automatically recognize the record's property?

**Exercise 12.** Two threads concurrently call `withdraw` on a shared object. Do `private` fields and standardly named getters/setters automatically prevent lost updates? What else must be considered?

### Reference Answers

1. A read/write `available` property via `isAvailable/setAvailable`; `count` is read-only.
2. `name`; introspection recognizes properties based on matching public accessors, not necessarily on field names.
3. Appropriate when the responsibility is exchanging/configuring independent properties without complex business invariants; `timeout`'s valid range should still be checked.
4. A general-purpose setter does not express the reason for the state change, amount limits, permissions, or transaction rules; `deposit/withdraw` are more suitable when business logic exists.
5. `start=7` exceeds `end=5` in the intermediate step; use `moveTo(7,9)` to validate both values together before assigning.
6. No. `final` does not lock the contents of the list; you need a snapshot/copy or a query API aligned with the contract.
7. Yes, it can be; the DTO lets tools populate data step by step while the domain object is created only once valid; the trade-off is an extra model and conversion step.
8. `URL` and `name`, following the property decapitalization rule in JavaBeans/Introspector.
9. `getReady()` with the `Boolean` type; do not expect a wrapper `isReady()` to be recognized by every classic JavaBeans introspector.
10. No. An exception from a listener does not automatically undo an assignment that has already happened; you must clearly design the ordering and error-handling guarantees.
11. Record accessors follow component names rather than the classic `getX` pattern; record support depends on the tool.
12. No. You need synchronization, atomic updates, or ownership suitable for the check-and-write state operation.

## 25. References

- [Java SE 17 — JavaBeans Introspector](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/beans/Introspector.html): how beans are analyzed and property naming rules.
- [Java SE 17 — PropertyDescriptor](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/beans/PropertyDescriptor.html): read/write methods of a property.
- [Java SE 17 — BeanInfo](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/beans/BeanInfo.html): property, event, and method metadata for tools.
- [Java SE 17 — PropertyChangeSupport](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/beans/PropertyChangeSupport.html): support for bound property events.
- [Java SE 17 — Introspector.decapitalize](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/beans/Introspector.html#decapitalize(java.lang.String)): rules for turning a method name into a property name.
- [Java Language Specification 17, §8 — Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html): classes, fields, methods, and constructors.
- [Java Language Specification 17, §8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): records and component accessors.

**Takeaway:** the JavaBeans convention standardizes **how properties are exposed and discovered**; behavior-oriented design protects **the meaning of permitted state transitions**. Both approaches can work together: getters for observation, validated setters for properties that are genuinely allowed to be set directly, and methods such as `deposit`, `withdraw`, `moveTo`, and `receive` for business operations. The ultimate goal is not to have as many setters as possible, but to **preserve invariants across every path that creates, reads, and updates state**.
