# Template Method in Java: Fixed Workflow and Abstract Steps

## 1. Core Idea

**Template Method** is a behavioral design pattern used when multiple classes need to execute the same overall workflow, but a few steps within the workflow vary depending on the object type. The superclass defines the order of the steps in a template method; subclasses provide the implementations for the steps assigned to them.

For example, many types of reports all need to prepare data, process data, print headers, and then output results. This order is a general rule and should not be arbitrarily rearranged by each subclass. However, how data is fetched or how content is calculated may vary between a sales report and an inventory report. Template Method keeps the common workflow in one place and allows subclasses to customize precisely the designed points.

The name “Template Method” refers to the method that holds the skeleton of the algorithm. In Java, that method is usually an instance method declared `final` in an abstract class, while the varying steps are declared as `abstract` methods or hooks with a default implementation.

## 2. Structure of the Design Pattern

A Template Method typically has three components:

- **Superclass (abstract class):** owns the overall algorithm and defines the steps in the exact order.
- **Template method:** the method that calls the steps in sequence; it is usually `final` so subclasses cannot override it and break the workflow order.
- **Customizable steps:** abstract methods that subclasses are required to implement, along with hooks that have default behavior which subclasses can override when needed.

Typical call diagram:

~~~text
Client
  |
  v
ConcreteClass.templateMethod()   (inherited from AbstractClass)
  |
  +--> stepA()                   (can be a fixed step)
  +--> requiredStep()            (abstract, implemented by subclass)
  +--> optionalHook()            (has a default, can be overridden)
  +--> stepB()                   (fixed step)
~~~

The key point is that **the superclass controls the call flow**. Subclasses only supply behavior at the extension points declared by the superclass. If a subclass is allowed to replace the entire template method, the contract regarding the overall sequence is weakened.

## 3. Runnable Java 17 Example

The example below creates a report generation workflow. Every report prints the header, collects data, performs calculations, and then prints the footer. The superclass preserves that order; the subclass only provides how data is collected and how the total is calculated.

~~~java
abstract class ReportGenerator {
    // Template Method: preserves the sequence of the entire workflow.
    public final void generateReport() {
        printHeader();
        String data = collectData();
        String result = calculate(data);
        afterCalculation(result); // Optional hook
        printFooter();
    }

    private void printHeader() {
        System.out.println("=== REPORT START ===");
    }

    protected abstract String collectData();

    protected abstract String calculate(String data);

    // Hook with default behavior; subclasses are not required to override it.
    protected void afterCalculation(String result) {
        System.out.println("Result prepared");
    }

    private void printFooter() {
        System.out.println("=== REPORT END ===");
    }
}

final class SalesReport extends ReportGenerator {
    @Override
    protected String collectData() {
        return "10,20,30";
    }

    @Override
    protected String calculate(String data) {
        int total = 0;
        for (String part : data.split(",")) {
            total += Integer.parseInt(part);
        }
        return "Sales total = " + total;
    }

    @Override
    protected void afterCalculation(String result) {
        System.out.println(result);
    }
}

public class Main {
    public static void main(String[] args) {
        ReportGenerator report = new SalesReport();
        report.generateReport();
    }
}
~~~

Save all the code to the file `Main.java`, then run it with JDK 17 or later:

~~~text
javac Main.java
java Main
~~~

Exact stdout output:

~~~text
=== REPORT START ===
Sales total = 60
=== REPORT END ===
~~~

The call flow proceeds as follows:

1. `main` calls `generateReport()` on a SalesReport object through a variable of type ReportGenerator.
2. The template method prints the header before requesting data.
3. The calls to `collectData()` and `calculate(data)` are dispatched to the implementation in SalesReport.
4. The `afterCalculation(result)` hook is also dynamically dispatched and prints the result.
5. The superclass prints the footer, so the subclass cannot skip this step by overriding the template method.

In this example, the `printHeader()` and `printFooter()` methods are private because they are fixed details of the superclass. The two abstract steps are protected so that subclasses can implement them. The template method is public final so that clients can call it and subclasses cannot change the order of the entire algorithm.

## 4. Why Use Abstract Steps?

An abstract step represents behavior that every concrete subclass is required to provide. If the superclass cannot determine a sensible common implementation, declaring it abstract makes it clear that missing that step results in an incomplete implementation.

For example, a `DataImporter` superclass can define the `importData()` template in the order: read the source, parse the content, validate the data, and then save the result. Reading CSV and reading JSON may differ, so `readSource()` or `parse()` can be abstract steps. Common operations such as logging or timing can be implemented directly in the superclass.

You should not turn every line of code into an abstract method. Only make extensible the steps that genuinely need to differ across subclasses. If too many steps are customizable, the overall workflow becomes hard to understand and subclasses may create variants that no longer follow the original intent.

A class that has at least one abstract method must be declared abstract. An abstract class can contain implemented methods, fields, constructors, and abstract methods; it cannot be instantiated directly with `new`. A concrete subclass must implement every remaining abstract method; otherwise, that subclass must also be declared abstract.

## 5. Hook: Optional Extension Point

A hook is a method provided by the superclass with a default behavior. A subclass can override the hook when it needs to add behavior, but is not required to do so. In the example, `afterCalculation(result)` prints a message by default; SalesReport overrides it to print the calculation result.

Hooks are useful for points such as:

- running additional validation checks before or after the algorithm;
- adding logs or diagnostic information;
- allowing a subclass to decide whether to perform an optional action;
- adjusting a small part of the workflow without replacing the entire template method.

A hook does not necessarily have to be a no-argument method. It can accept data or return a value if the design contract requires it. However, it should be clearly documented when the hook is called and whether the hook's result affects subsequent steps.

A boolean hook can be used to allow skipping an optional step, but you should ensure that this state does not break the invariants of the algorithm. If a step must always happen, keep it fixed in the template method or use an abstract method to force subclasses to provide the required behavior.

## 6. Call Flow Control and Dynamic Dispatch

Template Method embodies the “Hollywood” principle: the superclass calls the subclass at defined extension points. The client only needs to call a high-level method such as `generateReport()`; the client does not need to orchestrate each step itself.

When a template method calls an overridable instance method, Java selects the implementation based on the actual runtime type of the object (dynamic dispatch). Therefore, the call to `collectData()` inside ReportGenerator still executes the SalesReport method when the actual object is a SalesReport.

You should declare the template method `final` when preserving the step order is an essential part of the contract. If there is a genuine reason for a subclass to change the entire algorithm, consider an alternative design or explicitly evaluate not using final. Do not add final mechanically when the superclass is intentionally designed to allow changing the overall algorithm.

A template method is usually an instance method, not static, because the customizable steps need to dispatch to the subclass object. Static methods are not overridden through instance polymorphism, so they are not suitable as customizable steps of this kind.

## 7. Error Handling, Resources, and Step Order

When a workflow can fail, clearly define the behavior when a step throws an exception. Under normal sequential execution, if a step throws an exception and it is not caught locally, subsequent steps will not run. For example, if `collectData()` fails, `calculate()`, the hook, and `printFooter()` will be skipped in the basic implementation.

If the workflow must release resources or run a closing operation even when an error occurs, use constructs such as try/finally or try-with-resources in the superclass. Do not assume that a template method automatically runs every step after an error. Error logging, rollback, closing connections, or emitting failure notifications must be explicitly designed.

You should also avoid calling overridable methods from the superclass constructor. While the superclass constructor is running, the subclass may not have finished initializing its fields; a dynamic call to a subclass method at that point could observe an unready state. Start the template method after the object has been fully constructed, typically via an explicit call from the client or an appropriate orchestration method.

## 8. When to Use Template Method?

This pattern is appropriate when:

- There is a common algorithm or workflow with a stable step order.
- Some steps vary across variants, while the order and orchestration logic need to be shared.
- You want to enforce that subclasses implement required steps via abstract methods.
- You want to provide optional extension points using hooks without duplicating the entire algorithm.

Common examples include data import workflows, report generation, file processing, input validation, processing pipelines, and test workflows with shared setup/execution/teardown steps. In each case, only use the pattern when the algorithm structure is genuinely stable and the differences can be expressed as small, clear steps.

## 9. Limitations and Comparison with Strategy

Template Method typically uses inheritance to vary certain steps. Consequently, subclasses are coupled to the superclass structure and must adhere to the contract defined by the superclass. If there are multiple independent dimensions of variation, the number of subclasses can grow and the customizable steps can become difficult to coordinate.

**Strategy** addresses a similar situation using composition: an object receives interchangeable behavior through a strategy interface. This allows changing the algorithm at runtime and combining behaviors without creating a subclass for every combination. In return, Strategy may require additional interfaces and separate objects.

| Criterion | Template Method | Strategy |
|---|---|---|
| Core mechanism | Inheritance and overriding specific steps | Composition and delegation to a strategy object |
| Who maintains the workflow order? | The template method in the superclass | The orchestrating object calling strategies by design |
| Scope of change | Certain steps within a shared algorithm | Can replace an entire behavior/algorithm |
| Changing behavior at runtime | Usually limited; depends on object type and hooks | More natural because the strategy object can be swapped |
| Design risks | Rigid inheritance hierarchy; subclasses depend on superclass | More objects/interfaces and the need to manage delegation |

Choose Template Method when the overall workflow needs to remain stable and the varying steps are a natural part of an inheritance hierarchy. Choose Strategy when you need to swap algorithms flexibly, compose behaviors, or avoid creating many additional subclasses. The two patterns can be combined if the workflow remains fixed while a specific step is delegated to a Strategy.

## 10. Common Pitfalls

- **Repeating the entire workflow in each subclass.** This duplicates logic and makes it easy for the step order to diverge over time. Keep the common part in the template method.
- **Letting subclasses override the template method when the order is invariant.** Consider using `final` so the compiler prevents overriding.
- **Marking every step as abstract.** Behaviors that have a shared implementation should be kept in the superclass; only create extension points when there is a clear reason.
- **Using a hook for a mandatory step.** A hook with a default implementation might not be overridden. If a subclass is required to provide the behavior, use an abstract method.
- **Calling the template method from a constructor.** Overridable methods may execute before the subclass state is fully initialized.
- **Assuming subsequent steps still run when a step throws an exception.** In a basic sequential flow, an unhandled exception interrupts the workflow. Design a finally block or try-with-resources if cleanup is required.
- **Using inheritance when behaviors need to change independently.** When you need to swap algorithms flexibly or combine multiple variants, evaluate Strategy and composition.

## 11. Key Takeaways

Template Method places the skeleton of an algorithm in the superclass and keeps the order of steps in one place. Abstract methods force subclasses to provide required steps; hooks allow extending behavior with a default implementation. A template method is usually declared final to protect the workflow sequence. This pattern is suitable when the workflow is stable while some steps vary; if you need flexible algorithm replacement or independent behavior composition, composition-based Strategy may be a better fit.
