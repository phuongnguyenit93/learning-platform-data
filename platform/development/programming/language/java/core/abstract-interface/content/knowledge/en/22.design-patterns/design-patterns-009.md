# Choosing Patterns by Problem and Avoiding Superficial Application

A design pattern is a way of organizing classes and objects that has been used to solve a recurring group of design problems. Patterns help express a solution in a common language, but **design patterns are not the goal of design**. A system with many patterns is not necessarily better; if the requirements are simple, adding interfaces, factories, or multiple intermediate classes can make the code harder to understand.

The right way to choose is to start from the problem currently occurring, identify what is likely to change, and then see which pattern reduces that dependency at a reasonable cost. If a few simple statements already express the intent clearly and there is not yet a need for variations, keeping the simple approach is a valid design decision.

## 1. Start from the Problem, Not from the Pattern Name

Before applying a pattern, answer the following questions in order:

1. **Where is the code causing difficulty?** For example: an algorithm varies by customer type; multiple places must instantiate the same group of objects; one class needs to notify multiple parties; or two APIs are incompatible.
2. **What actually changes?** Distinguish frequently changing business rules from the stable remainder. If there is only one fixed rule and no sign of needing extension, an abstraction may not yet bring any benefit.
3. **What cost is the change causing?** For example, an `if/else` branch duplicated in multiple places, a single change requiring edits across many classes, or testing one rule forcing the entire system to be initialized.
4. **Does the pattern isolate the right point of change?** A suitable pattern must make the code easier to read, easier to test, or easier to extend right in the current context.
5. **What are the new costs?** Include the increased number of classes and interfaces, harder-to-trace call flows, object lifecycles, event ordering, and the team's maintenance requirements.
6. **Can it be solved in a smaller way?** A dedicated function, a clear conditional, or simple object composition is often enough. There is no need to create a pattern structure just to make the code look like an example from a book.

You can use a short workflow: describe the problem in one sentence → identify the axis of change → propose the simplest approach → compare with one or two relevant patterns → verify with examples and tests → keep the pattern only if it resolves the identified cost.

## 2. Problem and Design Pattern Map

The following table is a starting point for selection, not a list of mandatory rules. One problem can have multiple valid options; choose the option that matches the specific cause.

| Problem Encountered | Pattern Worth Considering | Signs the Pattern Is Useful | When Not to Use |
|---|---|---|---|
| A task has multiple interchangeable algorithms | **Strategy** | Different calculation or processing methods are independent of the main flow and need to be selected by context | There is only one stable algorithm, or a few lines of conditionals are easier to read |
| Object creation is complex, has multiple variants, or needs to hide the rule for selecting a concrete class | **Factory Method / Abstract Factory** | Object creation logic is scattered, or a family of products needs to be compatible with one another | A simple `new` call is already clear; the factory only forwards without adding any decision |
| An object needs to notify multiple subscribers of changes | **Observer** | The event publisher should not know the specific list of recipients | There is only one fixed recipient; the subscription and unsubscription lifecycle would introduce unnecessary risk |
| An existing API does not match the interface required by current code | **Adapter** | Need to convert an existing contract when external source code cannot or should not be modified | You can modify your own interface directly without affecting a public contract |
| Want to add responsibilities that can be combined as needed | **Decorator** | There are multiple independent additions that need to be stacked, such as compressing and encrypting a stream | There is only one simple option; a decorator chain makes the processing flow hard to understand |
| Behavior depends on the current state and state transition rules | **State** | State-based conditionals have become complex, duplicated, and need explicit transition management | There are only two states with small, stable logic and a single conditional remains easy to read |
| The overall workflow is fixed, but some steps can vary | **Template Method** | Classes share the same algorithm skeleton but need to customize a few steps | There is no natural inheritance relationship, or individual steps need to change dynamically at runtime; in that case, composition may be more suitable |
| An object has many optional parameters or construction rules that need validation | **Builder** | Long constructor, many overloads, or configuration state needs to be clear | The object has only a few required parameters and can be safely created with a constructor |
| A client must coordinate multiple APIs/subsystems to perform a task | **Facade** | A simple entry point helps reduce direct dependencies on multiple components | The facade class merely forwards every call without clarifying or simplifying usage |

### Similar Patterns That Solve Different Problems

- **Strategy and State:** Strategy swaps an implementation based on client choice or configuration; State represents behavior that changes according to an object's internal state and is typically tied to state transitions.
- **Factory and Builder:** Factory focuses on selecting or creating which type of object; Builder focuses on the process of assembling an object with multiple steps or multiple options.
- **Adapter and Facade:** Adapter makes an incompatible interface usable as the desired interface; Facade provides a simple entry point for a group of APIs.
- **Decorator and inheritance:** Decorator adds responsibilities by wrapping an object, allowing combination at runtime; inheritance defines a type relationship and typically fixes the structure more rigidly.
- **Observer and direct method calls:** Observer is useful when there are multiple independent subscribers or the publisher should not know the recipients. If calling only a single known collaborator, a direct call can be clearer.

Do not choose a pattern just because the problem name sounds similar. Check the responsibilities, dependency direction, how behavior is selected, and the object lifecycle in the specific situation.

## 3. Java Example: When a Simple Solution Is the Right Choice

Suppose a small application has exactly two delivery methods: standard and express. The base fees are 20,000 and 40,000 VND respectively; every 500 g over 1 kg adds 5,000 VND. The current requirements have no external shipping carriers, no configuration-driven algorithm changes, and no multiple places that have to select the policy themselves. A method with an enum type and a switch expression is clear enough to describe the rule.

Save the following complete program in the file **PatternChoiceDemo.java**:

~~~java
import java.util.Objects;

public class PatternChoiceDemo {
    enum Delivery {
        STANDARD, EXPRESS
    }

    static long shippingFee(Delivery delivery, int weightGrams) {
        Objects.requireNonNull(delivery, "delivery");
        if (weightGrams < 0) {
            throw new IllegalArgumentException("weight must not be negative");
        }

        long baseFee = switch (delivery) {
            case STANDARD -> 20_000L;
            case EXPRESS -> 40_000L;
        };
        long extraGrams = Math.max(0L, (long) weightGrams - 1_000L);
        long extraBlocks = (extraGrams + 499L) / 500L;
        return baseFee + extraBlocks * 5_000L;
    }

    public static void main(String[] args) {
        System.out.println("standard=" + shippingFee(Delivery.STANDARD, 1_500));
        System.out.println("express=" + shippingFee(Delivery.EXPRESS, 1_500));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~text
javac PatternChoiceDemo.java
java PatternChoiceDemo
~~~

Stdout output:

~~~text
standard=25000
express=45000
~~~

The example intentionally does **not** create a Strategy interface, factory, or subclasses: there is only a small selection axis, two defined values, and one shared weight-surcharge rule. The enum prevents typos in the delivery method name; the switch expression enforces handling all existing values. The negative weight check prevents invalid input from producing a meaningless fee. The 1,500 g case has exactly one 500 g block over the threshold, so it increases by 5,000 VND.

### When Requirements Change, Which Pattern Actually Adds Value?

| New Requirement | Potentially Suitable Approach | Considerations |
|---|---|---|
| Dozens of independent fee-calculation policies, selected by configuration and tested separately | Strategy via a policy interface | Needs a place to select the strategy and a unified fee-calculation contract |
| Integrating a carrier's API that returns prices in a different unit or data type | Adapter converting the external contract to the application contract | Needs defined rounding, units, and error handling |
| Optionally adding logging, timing, or auditing around the fee-calculation call | Decorator wrapping the same interface | Wrapping order and exception propagation must be clear |
| Each order type follows the same validate → calculate fee → save result workflow, but a few steps vary | Template Method, if the inheritance relationship is natural | Keep required steps and invariants in the parent class |
| Creating multiple concrete shipping objects within a stable workflow | Factory Method | Only beneficial if the product creation point truly needs polymorphism |
| Multiple components need to subscribe when an order is delivered | Listener or Observer | Manage registration, ordering, and listener errors |

These are options for **different new problems**, not a checklist of classes to add all at once. If the application only has two simple fee rates, continuing to use the switch version above is a well-grounded choice. Only when an actual change introduces many branches or dependencies that make maintenance costly should you refactor the appropriate changing part.


## 4. Recognizing Superficial Pattern Application

Some signs indicate that the structure has become more complex than the problem it needs to solve:

- **Pattern names appear without a clear reason:** the team can explain which class is responsible for what, but cannot point out what cost is being reduced.
- **Forwarding-only abstractions:** an interface has a single implementation, no variation point or useful constraint, and each class simply calls through to the next one.
- **A factory for every `new`:** if a factory does not hide a selection, does not control the lifecycle, and does not protect construction rules, it may just add an extra navigation step.
- **Strategy for a small expression:** a simple, easy-to-understand conditional is split into multiple classes even though there is no need to swap algorithms.
- **Singleton used to share everything:** global uniqueness creates hidden dependencies and makes tests vulnerable to leftover state. Use it only when uniqueness is truly a domain or lifecycle requirement.
- **Observer makes control flow unpredictable:** multiple listeners call one another, an error in one listener affects other parties, or it is unclear when to subscribe/unsubscribe. Lifecycle, ordering, and error handling must be clearly defined.
- **Overly nested patterns:** readers must trace through multiple interfaces, factories, and wrappers before finding the actual behavior. Check whether each class has an independent responsibility and benefit.

Note: a single sign alone is not enough to conclude that a pattern is wrong. For example, a Strategy with only one current implementation can still be reasonable if it serves as an important boundary with an external API or needs runtime configuration changes. Consider the full context and maintenance cost.

## 5. Choosing Between Alternatives on a Sound Basis

When multiple options exist, evaluate them against the same set of criteria:

1. **Clarity:** can someone new understand the intent and locate where the core business logic is handled?
2. **Changeability:** how many places need to be modified for a new variant? Does the stable part have to know details of the changing part?
3. **Testability:** can a rule be tested independently, or does it require initializing too many components?
4. **Safety:** does the pattern help preserve invariants, or manage resources, state, or subscription lifecycles better?
5. **Reading and maintenance cost:** are the number of classes, indirection, and new conventions worth the current benefit?
6. **Reversibility:** can you start simple and refactor later once an actual need arises? Are there tests protecting behavior before changing the structure?

There is no need to score every change mechanically. Use these criteria to explain trade-offs when the design is not obvious. If two options meet the requirements equally well, prefer the one with fewer new concepts that is easier for the team to understand.

## 6. Safe Refactoring Process

When a piece of code starts showing problems, proceed step by step:

1. **Capture current behavior.** Create or update tests for important cases before changing the structure.
2. **Pinpoint the axis of change.** For example: pricing rules, data sources, notification types, or object creation processes.
3. **Keep the stable part intact.** Extract the exact changing part from the main flow, rather than converting the entire system to a new structure.
4. **Apply the smallest useful pattern.** Start with an abstraction that has a clear contract; only add a Factory, Builder, or supporting classes when they handle a real responsibility.
5. **Compare before and after.** Check outputs and tests; confirm that caller code is easier to understand, new changes spread less widely, or testing is simpler.
6. **Remove redundant structure.** If an abstraction no longer helps reduce dependencies or clarify responsibilities, consider removing it in a separate refactoring with tests.

## 7. Self-Assessment Exercises

For each scenario, state the problem clearly before choosing a pattern:

- **A.** A program has only a single shipping-fee formula, with no configuration or variants. Should you create a Strategy right away? Explain the cost of the new interface.
- **B.** There are multiple ways to calculate fees by delivery region; the rules change independently and need to be tested separately. Does Strategy help? Which part should depend on the interface?
- **C.** An external SDK provides `LegacyPaymentClient`, but the application requires the `PaymentGateway` interface and cannot modify the SDK. Why is Adapter more suitable than Facade in this case?
- **D.** An order is sent to multiple independent subscribers when its status changes. What needs to be decided regarding subscription, unsubscription, listener errors, and notification order before using Observer?
- **E.** A constructor has only two required parameters. Does Builder make object creation clearer, or does it just add code that must be maintained?

A good answer does more than just name a pattern. It describes the problem, identifies which responsibility needs to be separated, explains why the pattern fits, and states the costs or situations that would make the pattern no longer necessary.

## 8. Principle to Remember

Design patterns are tools for managing change and clarifying responsibilities. Choose a pattern after identifying the problem, the axis of change, and the limits of the simplest approach. Use a pattern when it makes the system easier to read, test, or extend in the current situation; avoid adding structure just for the sake of form.
