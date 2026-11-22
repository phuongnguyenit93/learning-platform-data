# Choose an Abstract Class When You Need Shared State and Workflow

## 1. Main Idea

In Java, you should consider an abstract class when a group of classes has a same-kind relationship, needs to hold per-object data, and must execute a common workflow. An abstract class can provide fields, constructors, implemented methods, and abstract methods for subclasses to complete the differing parts.

For example, multiple types of reports may all have a title, perform the same input validation, and generate the same header and summary, while presenting each item in a different way. An abstract class can hold the title and define the report generation sequence; subclasses only decide how to present each item.

The phrase “shared state and workflow” is a signal to consider an abstract class, not an absolute rule. Choose it when the shared part genuinely belongs to a family of classes and makes the model easier to understand.

## 2. What Does an Abstract Class Provide?

An abstract class can combine the following capabilities:

- **Per-instance state:** it has instance fields to store shared data, such as a title, configuration, or information needed for processing steps. Each object still has its own values.
- **Initialization and invariants:** constructors validate input data and establish a valid state. **private final** fields are suitable for data assigned once.
- **Shared behavior:** concrete methods implement the logic that every subclass needs.
- **Extension points:** abstract methods require subclasses to supply the differing behavior.
- **Controlled workflow:** a concrete method can invoke common steps in a clear order. If subclasses must not be allowed to change the sequence, that method can be declared **final**.

An abstract class cannot be instantiated directly. A concrete subclass must complete the missing abstract methods. The superclass constructor still runs through a **super(...)** call when a subclass object is created.

An abstract class can implement interfaces and can contain both concrete and abstract methods. Java allows a class to inherit directly from only one superclass, so you need to consider the single-inheritance limit when designing a system.

## 3. Distinguishing Between Abstract Class, Interface, and Composition

| Need | Option to Consider |
| --- | --- |
| Multiple classes share instance state and initialization | Abstract class |
| Multiple classes need to follow a contract, but do not need shared state or workflow | Interface |
| Classes need to share a capability, but do not belong to the same inheritance hierarchy | Interface or composition |
| You want to fix the steps of an algorithm and let subclasses customize a few steps | Abstract class with Template Method |
| You want to change algorithms or collaborating components flexibly at runtime | Composition, such as passing a strategy object into the constructor |

An interface can still contain **default** methods and **static** methods. However, an interface has no instance fields to store per-object state; fields declared in an interface are **public static final** constants. Therefore, when each object needs to carry shared state initialized through a constructor, an abstract class is usually more suitable.

Do not choose an abstract class merely to avoid writing a few duplicate lines. If classes do not have a clear “is a kind of” relationship, or need to combine multiple independent capabilities, interfaces and composition usually keep the design more flexible.

## 4. Runnable Example with Java 17+

The following example generates reports with a shared title and summary section. The bulleted report and the numbered report differ only in how they present each item.

Create a **Main.java** file with the following complete content:

~~~java
import java.util.List;
import java.util.Objects;

abstract class ReportGenerator {
    private final String title;

    protected ReportGenerator(String title) {
        this.title = Objects.requireNonNull(title, "title");
        if (title.isBlank()) {
            throw new IllegalArgumentException("title must not be blank");
        }
    }

    public final String generate(List<String> items) {
        Objects.requireNonNull(items, "items");

        StringBuilder out = new StringBuilder();
        appendHeader(out);

        int index = 1;
        for (String item : items) {
            Objects.requireNonNull(item, "items must not contain null");
            appendItem(out, index, item);
            index++;
        }

        out.append("Total: ").append(items.size()).append(" items").append('\n');
        return out.toString();
    }

    private void appendHeader(StringBuilder out) {
        out.append(title).append('\n');
        out.append("-----").append('\n');
    }

    protected abstract void appendItem(StringBuilder out, int index, String item);
}

final class BulletReportGenerator extends ReportGenerator {
    BulletReportGenerator(String title) {
        super(title);
    }

    @Override
    protected void appendItem(StringBuilder out, int index, String item) {
        out.append("- ").append(item).append('\n');
    }
}

final class NumberedReportGenerator extends ReportGenerator {
    NumberedReportGenerator(String title) {
        super(title);
    }

    @Override
    protected void appendItem(StringBuilder out, int index, String item) {
        out.append(index).append(". ").append(item).append('\n');
    }
}

public class Main {
    public static void main(String[] args) {
        ReportGenerator bullets = new BulletReportGenerator("Fruits");
        ReportGenerator numbered = new NumberedReportGenerator("Tasks");

        System.out.println(bullets.generate(List.of("Apple", "Banana")));
        System.out.println(numbered.generate(List.of("Read", "Practice")));
    }
}
~~~

Compile and run in the directory containing the file:

~~~text
javac Main.java
java Main
~~~

Exact stdout:

~~~text
Fruits
-----
- Apple
- Banana
Total: 2 items

Tasks
-----
1. Read
2. Practice
Total: 2 items
~~~

The example only builds report strings in memory; it does not write files to disk. You can replace the string output with I/O operations in a real application, while handling I/O errors appropriately.

## 5. Reading the Example by Execution Flow

**State and constructor.** **ReportGenerator** holds **title** as a **private final** field. The constructor accepts the title and rejects **null** as well as empty or whitespace-only strings. Every subclass calls this constructor via **super(title)**, so this initialization rule is not duplicated.

**Shared workflow.** The **generate** method validates the list, creates a buffer, calls **appendHeader**, iterates over each item, calls **appendItem**, and then appends the total item count. Both subclasses use that same workflow.

**Customization point.** **appendItem** is a **protected abstract** method. Subclasses are required to implement how an item is written: **BulletReportGenerator** adds a bullet, while **NumberedReportGenerator** adds a sequence number.

**Preserving step order.** **generate** is declared **final**, so subclasses cannot replace the entire workflow with a different implementation. Subclasses only customize the step designed for extension. This is an example of the Template Method design pattern.

**Polymorphism.** Both variables in **main** have the declared type **ReportGenerator**, yet Java invokes the **appendItem** version of the actual object. Calling code does not need to check each type with **if** or **switch**.

**Single Java file.** Only **Main** is a **public** class, so the remaining classes can be placed in the same **Main.java** file. In a large project, you can separate each class into its own file according to the project's conventions.

## 6. Template Method: When Should You Fix the Workflow?

Template Method is a design approach in which a high-level method defines the steps of an algorithm, while one or more methods are implemented by subclasses to vary the details. In the example, **generate** is the template method and **appendItem** is the extension point.

This pattern is useful when the order of steps is part of the business rules. For example, data processing may always require validating input, normalizing data, processing each part, and aggregating results; different types of processors only differ in how they process each part.

Use **final** on the template method when subclasses genuinely must not alter the order or skip a required step. If a subclass legitimately needs to change the entire algorithm, a **final** method will be too restrictive; consider a strategy interface or composition.

Avoid calling overridable methods from an abstract class constructor. When the superclass constructor runs, the subclass may not have finished initializing its fields yet. Calling an overridden method at this stage can easily cause subclass code to operate on incomplete state.

## 7. State Design Rules

- Keep fields **private** and provide intentional accessor methods when needed. Do not make every field **protected** just so subclasses can modify it conveniently.
- Prefer **final** for configuration data that is set once. This does not automatically make the object immutable if the field holds a mutable object, but it prevents reassigning the reference.
- Validate data in the constructor so that every instance starts in a valid state.
- Avoid placing mutable state with unclear ownership in the superclass, as subclasses can inadvertently introduce conflicting updates.
- Do not put per-request or per-user data into a shared **static** field if that data must remain independent across executions.
- Only move state up into the superclass when it truly makes sense for every subclass. If only one report type needs a field, you can keep that field in the subclass.

In the example, the title is per-instance data and does not change after initialization. The buffer and index are local variables inside **generate**, so they are not shared across calls.

## 8. Common Mistakes

**Choosing an abstract class without a sound shared relationship.** Having only a few similar methods is not enough to establish an inheritance relationship. If classes are independent yet need the same capability, using an interface or a collaborator object may be more appropriate.

**Repeating the workflow in every subclass.** If every subclass validates input, builds the header, and calculates the total in the same way, group those steps into the superclass. Each step should only be overridden when there is a clear design reason.

**Allowing subclasses to modify shared state directly.** Mutable **protected** fields make the superclass's rules hard to control. Prefer **private** fields, methods with a clear purpose, and small extension points.

**Making abstract methods too broad.** A hook should express the exact part that needs to vary. If subclasses have to rewrite almost the entire algorithm, the abstract class may be grouping classes that do not genuinely share a workflow.

**Using final everywhere.** **final** is useful for protecting invariants or a required sequence, but it should not be applied mechanically. Clearly identify which parts must remain stable and which parts are valid extension points.

**Calling overridden methods from a constructor.** Avoid having a superclass constructor call a method that a subclass can replace; the subclass state may not be ready yet.

**Confusing abstract classes with interfaces.** An abstract class can hold instance state and constructors. An interface describes a contract that multiple types can implement, even when they already inherit from different superclasses.

## 9. Decision Checklist

Before creating an abstract class, ask yourself:

1. Are the classes truly variants of the same concept?
2. Do they need the same instance state or the same initialization rules?
3. Is there a common workflow that every subclass should follow?
4. Can you identify a few clear extension points instead of allowing subclasses to change everything?
5. Can an interface or composition be used to share the capability without forcing the classes into an unnecessary inheritance hierarchy?

If the answers to the questions about shared state and workflow are yes, an abstract class is worth considering. If the primary need is to describe a contract, an interface is usually enough. When you need to change behavior flexibly and combine multiple components, composition usually helps reduce dependence on an inheritance hierarchy.

The goal is to place the genuinely shared state and workflow in one place, while keeping subclasses responsible only for their differing behavior.
