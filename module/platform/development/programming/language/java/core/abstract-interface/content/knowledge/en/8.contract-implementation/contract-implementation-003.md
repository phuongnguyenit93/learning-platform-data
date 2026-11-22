# Abstract Classes Partially Implementing an Interface in Java

An abstract class can accept a contract from an interface and implement the shared parts, leaving concrete subclasses to complete the behaviors that depend on the object type. Unfulfilled obligations remain in the hierarchy; only the final concrete class must have a valid implementation for all missing abstract methods.

## 1. Complete Example: A Base Class Sharing Common Processing

The following Java 17 program illustrates an interface defining a contract, an abstract class holding shared state and logic, and a concrete subclass providing specialized behavior. Save it as **PartialImplementationDemo.java**:

~~~java
import java.util.Objects;

public class PartialImplementationDemo {
    interface ReportJob {
        void validate();
        String generate();
        void audit(String result);

        default String kind() {
            return "report";
        }
    }

    abstract static class AbstractReportJob implements ReportJob {
        private final String reportName;

        protected AbstractReportJob(String reportName) {
            this.reportName = Objects.requireNonNull(reportName, "reportName");
        }

        @Override
        public final void validate() {
            if (reportName.isBlank()) {
                throw new IllegalArgumentException("reportName is blank");
            }
            System.out.println("validated: " + reportName);
        }

        @Override
        public void audit(String result) {
            System.out.println("audit: " + reportName + " -> " + result);
        }

        protected final String reportName() {
            return reportName;
        }

        // generate() still has no body; an abstract class can defer it.
    }

    static final class CsvReportJob extends AbstractReportJob {
        CsvReportJob(String reportName) {
            super(reportName);
        }

        @Override
        public String generate() {
            return reportName() + ": csv ready";
        }
    }

    public static void main(String[] args) {
        ReportJob job = new CsvReportJob("Sales");

        System.out.println("kind: " + job.kind());
        job.validate();
        String result = job.generate();
        System.out.println("result: " + result);
        job.audit(result);
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 PartialImplementationDemo.java
java PartialImplementationDemo
~~~

Output:

~~~text
kind: report
validated: Sales
result: Sales: csv ready
audit: Sales -> Sales: csv ready
~~~

### Responsibilities of Each Type

- **ReportJob** describes the behaviors callers can rely on. Three abstract methods create implementation obligations; **kind()** is a default method that already has a body.
- **AbstractReportJob** implements **validate()** and **audit()**, holds the **reportName** state, and provides a protected helper for subclasses. It is valid even without a body for **generate()**, because the class itself is declared abstract.
- **CsvReportJob** is a concrete class. It inherits the two existing methods and only needs to provide **generate()**. After its constructor calls **super(reportName)**, a concrete object can be created with **new**.
- **validate()** is marked final so subclasses cannot bypass the shared validation rule by overriding it. **generate()** is left open for behavior specific to each report type.

## 2. How Much Can an Abstract Class Implement?

An abstract class can implement **none, some, or all** of an interface's abstract methods. The abstract keyword does not require a class to contain an abstract method; even when it already has bodies for all methods, the class can still be intentionally kept as a base class that cannot be instantiated directly.

| Type Layer | Responsibility |
| --- | --- |
| Interface | Declares the contract and the required abstract methods |
| Abstract class | Holds shared state, constructors, helpers, and logic; may defer some methods |
| Another abstract subclass | May complete an additional part and continue leaving the remaining parts missing |
| Concrete subclass | Must have a valid implementation for all abstract obligations still in effect |

An abstract class is not required to redeclare the signature of a method it leaves unimplemented. For example, **AbstractReportJob** does not need to rewrite **public abstract String generate()** for the compiler to know that the method is still missing. It can be explicitly redeclared if you want to emphasize an extension point or add API documentation; doing so does not create a body. If you redeclare a public interface method, you must not reduce its access level to protected.

## 3. When Is This Design Useful?

This approach fits well when multiple classes in the same family need to share state, constructors, data validation, processing order, or part of an algorithm, while still having a specialized step for each type.

For example, CSV and JSON reports can share report name validation and audit logging, while each type has its own way of generating content. Placing the shared part in an abstract class keeps subclasses from having to duplicate it and reduces the risk of them applying shared rules inconsistently.

Interfaces and abstract classes address two different needs:

- **Interface** allows clients to depend on the capability an object provides, while a class can implement multiple interfaces.
- **Abstract class** is suitable when subclasses need to share instance state, constructors, protected methods, or an algorithm with fixed steps.
- **Default method** is useful for default behavior that does not need instance state from the base class. If interfaces provide conflicting default methods, they must be resolved according to Java inheritance rules.
- **Composition** is often more appropriate if you only need to reuse an independent service or if inheritance creates overly tight coupling. Java allows only one direct superclass.

## 4. Mistakes to Avoid

**Mistake 1 — An incomplete class missing abstract.** If **AbstractReportJob** is changed into a regular class while still missing **generate()**, the program will not compile. Keep it abstract or provide a suitable body.

**Mistake 2 — Thinking a concrete subclass must rewrite every method.** **CsvReportJob** does not need to override **validate()** or **audit()** just to complete the interface, because those methods are already validly inherited.

**Mistake 3 — Using an abstract class to dodge type conflicts.** If two contracts require incompatible return types, making the class abstract does not automatically make the conflicting declarations valid. You need to analyze and fix the type contract.

**Mistake 4 — Calling an overridable method from a superclass constructor.** An abstract class constructor runs before the subclass's own initialization completes. If the constructor calls an overridable hook, the subclass implementation may read state that is not yet fully initialized. The constructor should set up and validate its own class's state; invoke polymorphic behavior after the object has been created.

**Mistake 5 — Pushing subclass-specific logic into the base class.** If an abstract class has to check the subclass type to choose a processing branch, responsibilities may not be divided properly. Consider an explicit abstract method, a smaller interface, or composition.

## 5. Self-Check

**Question 1.** Interface **Vehicle** declares **start()** and **stop()**. Abstract class **BaseVehicle** already implements **start()**. What does a concrete class **Car** extending **BaseVehicle** need to do?

**Answer:** provide **stop()**, unless another valid implementation is inherited.

**Question 2.** Must an abstract class that has already implemented every interface method remove the abstract keyword?

**Answer:** no. It can still be kept abstract to indicate that only concrete subclasses should be instantiated.

**Question 3.** If an abstract class does not redeclare a missing interface method, does Java forget that obligation?

**Answer:** no. The obligation still exists in the hierarchy and is checked when a concrete class is declared.

**Remember:** an abstract class is the right place to implement shared parts and defer specialized parts. Only a concrete class must resolve all abstract obligations still in effect; clearly design which parts are inherited and which parts are extension points.
