# Recognizing Signs That OOP Design Needs Improvement

> **Topic:** Refactoring — recognizing when design starts causing difficulties, identifying underlying causes, and choosing small, verifiable improvements.

A Java program that **runs correctly** is not necessarily **easy to change**. Warning signs appear when adding one small rule requires edits in many places, one class handles unrelated concerns, a business condition is duplicated, or testing a simple feature requires constructing numerous dependencies.

Such symptoms are commonly called **code smells**: signals that a code structure may deserve investigation. **A code smell is not automatically a defect**, and there is no rule requiring every smell to be refactored. Instead, assess the design's *impact* on debugging, extension, comprehension, and testing, then improve it at a reasonable cost.

## 1. Examine the Difficulty of Change, Not Just Code Length

Ask practical questions:

- When adding a small feature, how many classes must be opened and modified? Do those edits share one reason to change?
- When fixing a bug, are business conditions or formulas duplicated in several places?
- Does a class perform business calculations, query data, format UI content, and send email?
- Can a method be understood from its name and the abstraction level of its steps, or must readers track many flags, nested branches, and temporary variables?
- Can tests easily construct objects and verify behavior, or must they mock numerous implementation details?
- Does modifying one class frequently cause defects in seemingly unrelated classes?

These answers are more useful than line counts alone: a long, stable method expressing a straightforward sequence may be less risky than a short method with hidden side effects.

### Common Warning Signs

| Code smell | Observation in Java code | Practical risk | Possible direction, not a mandate |
|---|---|---|---|
| **Long Method** | A method mixes many steps, branches, or abstraction levels | Difficult to read and test individual rules | Use `Extract Method` to name meaningful steps |
| **Large Class / God Object** | A class owns unrelated responsibilities and many fields and method groups | Every change has a broad impact | Split by reasons to change; improve cohesion |
| **Duplicate Code** | A business condition or formula appears in multiple places | Missing an update creates inconsistent behavior | Centralize genuinely shared rules; avoid abstracting coincidental similarities |
| **Shotgun Surgery** | A small requirement forces edits across many classes | Scattered changes are difficult to review | Move related logic to an appropriate owner |
| **Divergent Change** | A class repeatedly changes for unrelated reasons | Unclear responsibilities and cross-impact risks | Separate responsibilities along distinct change axes |
| **Feature Envy** | A method on A repeatedly inspects B's data/details to make decisions | Rules live in the wrong place; low cohesion | Consider `Move Method` or a meaningful API on B |
| **Primitive Obsession** | `String`/`int`/`boolean` carry many domain rules and "magic strings" | Unit confusion and invalid states | Use `enum`, records/value objects, or domain types |
| **Long Parameter List / Data Clumps** | Repeated parameter groups and many boolean flags | Wrong argument order and expensive changes | Introduce a parameter object when the group represents one concept |
| **Conditional Complexity** | Repeated `switch`/`if` branches based on object type | Each new type requires edits in many places | Consider polymorphism, Strategy, or rule tables |
| **Inappropriate Intimacy / Tight Coupling** | A class knows another class's internals and directly constructs many dependencies | Testing and substitution are difficult | Reduce coupling; inject dependencies at meaningful boundaries |
| **Data Class / Anemic Model** | Domain objects only expose getters/setters while associated rules live in services | Invariants are hard to enforce | Move *domain-owned behavior* to its appropriate owner |
| **Speculative Generality** | Interfaces, inheritance, and plugin points lack a real need | Too many classes and poor navigability | Remove abstraction layers without clear benefits |
| **Comments as Deodorant** | Comments must explain obscure branches | Intent is hidden behind confusing structure | Improve names and decompose logic; retain comments explaining why |
| **Mutable Shared State** | Many objects mutate the same shared list/cache | Order-dependent bugs and race conditions | Prefer immutable data and explicit ownership/concurrency management |

**Do not impose rigid line-count or class-count rules.** A small class with conflicting rules can still be problematic. Conversely, splitting simple logic across 15 interfaces may make the design worse.

## 2. Distinguishing Easily Confused Code Smells

**Divergent Change** and **Shotgun Surgery** both make code changes painful, but from different perspectives:

- **Divergent Change:** *One class* must change for several independent **reasons**; for example, `OrderManager` is affected by pricing policy, email-format, and storage-schema changes.
- **Shotgun Surgery:** *One reason for change* forces edits in **many classes**; for example, changing the free-shipping threshold requires updates to `Cart`, `Checkout`, `Invoice`, and `OrderPreview`.

Likewise, **Duplicate Code** does not mean every similar snippet must be merged. Rules that look alike today but belong to contexts that change independently may be better kept separate. An abstraction should represent **shared knowledge or policy**, not merely shared syntax.

**Long Method** differs from **Complex Method**: a method that describes many sequential steps is not necessarily hard to understand, while a short method involving state interactions and side effects may be complex.

### From Observation to a Design Hypothesis

| Observation | Hypothesis to test | Evidence to seek |
|---|---|---|
| Changing one rule requires editing 5 files | The rule is scattered | Previous diffs and duplicated formulas |
| Testing one class requires 8 mocked collaborators | Too many responsibilities or high coupling | Constructors, I/O calls, and test setup |
| Newcomers take a long time to understand a method | Unclear abstraction levels or names | Nested branches, temporary variables, explanations needed during review |
| Many `boolean` flags | Multiple modes control one behavior | Flag combinations, invalid combinations, and missing tests |
| The same bug occurs across multiple screens | The same rule has inconsistent implementations | Failing inputs/outputs and copies of the rule |
| Change velocity noticeably declines | A design hotspot may exist | Edit frequency, regressions, review time, and diff scope |

To avoid hasty conclusions, examine **responsibilities**, **change history**, **actual defects**, and **existing tests**. Static analysis and complexity warnings can help locate candidates, but metrics only provide supporting signals.

## 3. Example: Three Responsibilities Mixed in One Class

Suppose a quotation system has an established contract:

- `subtotalCents` is the goods subtotal in **cents**, from `0` to `1_000_000`.
- Valid customer types are the case-sensitive strings `"STANDARD"` and `"VIP"`.
- VIP customers receive a `10%` discount on goods (rounded down to the cent) and free shipping.
- Standard customers receive no discount; shipping is free when `subtotalCents >= 100_000` and otherwise costs `15_000` cents.
- `total = subtotal - discount + shipping`.
- Invalid input must throw `IllegalArgumentException`.
- The result string has the format `discount=...;shipping=...;total=...`.

The initial version combines **input validation**, **pricing calculations**, and **output formatting** in one method. Changes to shipping rules, output format, or customer types all affect that code. This suggests **Divergent Change** as well as **Primitive Obsession**, because a `String` represents the customer type.

One refactoring option extracts **pricing rules**, a **formatter**, and a **facade** preserving the old API. This is only *one* sensible choice when those parts have independent reasons to change; adding classes may not be worth the cost in a tiny application.

### Running Before and After Refactoring (Java 17+)

Create `DesignSmellsDemo.java` and place the complete code below in it:

~~~java
import java.util.List;

public class DesignSmellsDemo {
    private static final long MAX_SUBTOTAL = 1_000_000L;
    private static final long FREE_SHIPPING_AT = 100_000L;
    private static final long SHIPPING_FEE = 15_000L;

    // API mà client sử dụng; cả hai phiên bản đều thực hiện.
    interface QuoteService {
        String quote(String customerType, long subtotalCents);
    }

    // BEFORE: validation, chính sách giá và định dạng nằm chung.
    static final class LegacyQuoteService implements QuoteService {
        @Override
        public String quote(String customerType, long subtotalCents) {
            if (subtotalCents < 0 || subtotalCents > MAX_SUBTOTAL) {
                throw new IllegalArgumentException("subtotal");
            }
            if (!"VIP".equals(customerType)
                    && !"STANDARD".equals(customerType)) {
                throw new IllegalArgumentException("customerType");
            }

            boolean vip = "VIP".equals(customerType);
            long discount = vip ? subtotalCents / 10 : 0;
            long shipping = (vip || subtotalCents >= FREE_SHIPPING_AT)
                    ? 0 : SHIPPING_FEE;
            long total = subtotalCents - discount + shipping;

            return "discount=" + discount
                    + ";shipping=" + shipping
                    + ";total=" + total;
        }
    }

    // AFTER: biểu diễn loại khách hàng bằng một kiểu miền rõ ràng.
    enum CustomerType {
        STANDARD, VIP;

        static CustomerType parse(String text) {
            if ("STANDARD".equals(text)) return STANDARD;
            if ("VIP".equals(text)) return VIP;
            throw new IllegalArgumentException("customerType");
        }
    }

    // Value object bất biến; trường dữ liệu không bị trộn với format.
    record Price(long discount, long shipping, long total) {}

    static final class PricingRules {
        Price calculate(CustomerType type, long subtotalCents) {
            long discount = type == CustomerType.VIP ? subtotalCents / 10 : 0;
            long shipping =
                    (type == CustomerType.VIP || subtotalCents >= FREE_SHIPPING_AT)
                        ? 0 : SHIPPING_FEE;
            return new Price(discount, shipping,
                    subtotalCents - discount + shipping);
        }
    }

    static final class QuoteFormatter {
        String format(Price price) {
            return "discount=" + price.discount()
                    + ";shipping=" + price.shipping()
                    + ";total=" + price.total();
        }
    }

    // Giữ API cũ; phối hợp các trách nhiệm đã tách ra.
    static final class RefactoredQuoteService implements QuoteService {
        private final PricingRules pricing;
        private final QuoteFormatter formatter;

        RefactoredQuoteService(PricingRules pricing, QuoteFormatter formatter) {
            this.pricing = java.util.Objects.requireNonNull(pricing);
            this.formatter = java.util.Objects.requireNonNull(formatter);
        }

        @Override
        public String quote(String customerType, long subtotalCents) {
            if (subtotalCents < 0 || subtotalCents > MAX_SUBTOTAL) {
                throw new IllegalArgumentException("subtotal");
            }
            CustomerType type = CustomerType.parse(customerType);
            Price price = pricing.calculate(type, subtotalCents);
            return formatter.format(price);
        }
    }

    record Example(String type, long subtotal, String expected) {}

    // Expected values được viết theo yêu cầu, không tính bằng production code.
    private static final List<Example> EXAMPLES = List.of(
        new Example("STANDARD", 0,
                "discount=0;shipping=15000;total=15000"),
        new Example("STANDARD", 99_999,
                "discount=0;shipping=15000;total=114999"),
        new Example("STANDARD", 100_000,
                "discount=0;shipping=0;total=100000"),
        new Example("VIP", 100_000,
                "discount=10000;shipping=0;total=90000"),
        new Example("VIP", 250_001,
                "discount=25000;shipping=0;total=225001"),
        new Example("STANDARD", 1_000_000,
                "discount=0;shipping=0;total=1000000")
    );

    private static void require(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    static void verifyBehavior(String label, QuoteService service) {
        for (Example ex : EXAMPLES) {
            String actual = service.quote(ex.type(), ex.subtotal());
            require(ex.expected().equals(actual),
                    label + " mismatch at " + ex + "; actual=" + actual);
        }
        expectInvalid(() -> service.quote("VIP", -1));
        expectInvalid(() -> service.quote("STANDARD", 1_000_001));
        expectInvalid(() -> service.quote("UNKNOWN", 50_000));
        expectInvalid(() -> service.quote(null, 50_000));
    }

    interface Action {
        void run();
    }

    private static void expectInvalid(Action action) {
        try {
            action.run();
        } catch (IllegalArgumentException expected) {
            return;
        }
        throw new AssertionError("Expected IllegalArgumentException");
    }

    public static void main(String[] args) {
        QuoteService legacy = new LegacyQuoteService();
        QuoteService refactored =
                new RefactoredQuoteService(new PricingRules(), new QuoteFormatter());

        verifyBehavior("legacy", legacy);
        verifyBehavior("refactored", refactored);

        for (Example ex : EXAMPLES) {
            require(
                legacy.quote(ex.type(), ex.subtotal())
                    .equals(refactored.quote(ex.type(), ex.subtotal())),
                "Observable behavior changed at " + ex);
        }

        System.out.println("PASS: original business rules");
        System.out.println("PASS: refactored business rules");
        System.out.println("PASS: same public API and observable output");
        System.out.println(refactored.quote("VIP", 250_001));
    }
}
~~~

Compile and run:

~~~bash
javac DesignSmellsDemo.java
java DesignSmellsDemo
~~~

Expected output:

~~~text
PASS: original business rules
PASS: refactored business rules
PASS: same public API and observable output
discount=25000;shipping=0;total=225001
~~~

Here, the **design benefit** is the ability to test and modify `PricingRules` independently from `QuoteFormatter` while reducing the risk that presentation changes unintentionally affect pricing. `CustomerType` replaces unrestricted strings with a domain enum; the external API still accepts strings under the original contract.

**Important note:** This example is intentionally small so it can run independently. Do not conclude that every method resembling `LegacyQuoteService.quote` must be split into three classes. Consider change frequency and testing benefits before introducing additional abstractions.

## 4. Follow the Change: Where Must You Edit, and What Is Affected?

Consider a request: "Raise the free-shipping threshold from 100.000 to 120.000 cents."

- If one clearly defined policy is updated, tests cover the new thresholds, and output formatting remains unaffected, the design has a good responsibility boundary.
- If the same constant must change in `CartController`, `CheckoutService`, `OrderConfirmationEmail`, and `InvoiceExporter`, **Shotgun Surgery** is likely. Verify whether they really share *the same business rule*.
- If the affected class contains pricing formulas, DB persistence, SMS delivery, and HTML rendering, it may suffer from **Divergent Change**.
- If adding a customer type always requires updating `switch` blocks in five classes, consider **polymorphism/Strategy** or moving the logic to an appropriate owner. A single `switch` is not necessarily a smell.

~~~mermaid
flowchart TD
    A["Phát hiện khó khăn khi sửa hoặc test"] --> B["Mô tả triệu chứng bằng ví dụ cụ thể"]
    B --> C["Xác định các lý do thay đổi và trách nhiệm"]
    C --> D{"Có bằng chứng về chi phí hoặc lỗi?"}
    D -->|Chưa| E["Theo dõi; tránh trừu tượng hóa vội"]
    D -->|Có| F["Đặt giả thuyết: lặp logic, coupling, cohesion..."]
    F --> G["Chọn phép refactor nhỏ nhất phù hợp"]
    G --> H["Chạy unit/contract/regression tests"]
    H --> I{"Hành vi còn đúng và code dễ thay đổi hơn?"}
    I -->|Không| J["Điều chỉnh hoặc hoàn tác bước vừa làm"]
    I -->|Có| K["Giữ thay đổi, ghi lại lý do thiết kế"]
~~~

## 5. Choose Refactorings That Address the Cause

| Confirmed problem | Potential technique | Important caution |
|---|---|---|
| A method contains several meaningful groups of operations | `Extract Method` and intention-revealing names | Avoid chains of forwarding methods that add no clarity |
| A class mixes UI, business logic, and data access | `Extract Class` and responsibility-based layering | Preserve boundary contracts and avoid cyclic dependencies |
| The same rule is duplicated | `Extract Function` or move to a shared service/value object | Consolidate only genuinely shared rules |
| Domain parameters are error-prone strings/numbers | `Replace Primitive with Object`, `enum`, `record` | Preserve serialization/deserialization and API compatibility |
| Type-based branches repeat across components | `Replace Conditional with Polymorphism` or Strategy | Avoid hierarchies for one simple, stable condition |
| A method manipulates another class's data extensively | `Move Method`, `Encapsulate Field` | Avoid breaking encapsulation when moving behavior |
| Object creation tightly couples a class to dependencies | Constructor injection and interfaces at suitable boundaries | Not every class needs an interface |
| Inheritance exists only to reuse a few lines | Switch to composition or delegation | Verify substitutability and compatibility before removing inheritance |
| A boolean flag selects two different behaviors | `Replace Parameter with Explicit Methods` or a domain type | Consider client-facing APIs, not only internal naming |
| Many getters/setters permit invalid states | Move validation/invariants into entities/value objects | Avoid making pure data objects unnecessarily complex |

**Cohesion:** The parts of a class serve one meaningful responsibility. **Coupling:** The degree to which modules need to know about each other. We generally want higher cohesion and less unnecessary coupling while balancing the complexity introduced by abstractions.

## 6. Four Levels of Evidence Before Proposing a Refactoring

### Level 1: Code-Reading Signals

Examine class/method names, repeated conditions, unrelated fields, and dependency counts to form a hypothesis. This is preliminary evidence, **not enough** to determine design costs.

### Level 2: Actual Changes

Trace one specific requirement: how many places change, where defects occur, and what makes review difficult. Areas that are both **frequently changed** and **complex** deserve higher priority than old code rarely touched.

### Level 3: Behavioral Tests

Identify inputs, expected outputs, exception types, state, and observable side effects. Test ordinary cases, boundaries, failures, and operation sequences. Establish regression tests before refactoring important business logic.

### Level 4: Evaluation After Improvement

A good refactoring makes subsequent changes easier to locate, tests clearer, and rules less duplicated without violating contracts. If it merely increases class count and makes abstractions harder to understand, there is insufficient evidence of improvement.

Useful metrics include **cyclomatic complexity**, dependency counts, duplication, files frequently edited together, time to fix bugs, and regression counts. No universal threshold is correct for every project.

## 7. When Should You Avoid Refactoring Immediately?

- **No current change need, little risk, and sufficiently clear code:** Document the issue and prioritize areas with greater impact.
- **Code lacks tests and handles money, data, or critical workflows:** First write characterization/contract tests rather than refactor based on guesses.
- **Business rules are not yet understood:** Consult domain owners and clarify edge cases before splitting classes.
- **An urgent bug fix is underway:** Isolate the fix and add regression tests; scope large refactorings separately if they increase risk.
- **An abstraction has one stable implementation and does not simplify tests or substitution:** Consider using a concrete class; interfaces do not automatically improve design.
- **Two snippets share syntax but change independently:** Merging them may introduce inappropriate coupling, causing changes in domain A to break domain B.

**Technical debt** can describe the future costs of an existing design, but not every smell is a debt that must be repaid immediately. Consider impact, likelihood of change, and the cost of improvement.

## 8. Checklist for Analyzing a Java Class

When reviewing a class, use this sequence:

1. **Purpose:** Describe the class's responsibility in one sentence. If it needs several unrelated "and" clauses, reassess cohesion.
2. **Boundary:** Which methods do clients use? Do they depend on internals, call order, or hidden state?
3. **Changes:** Identify 2–3 recent requirements that would force class edits. Do they share one reason to change?
4. **Dependencies:** Does the class create dependencies and perform I/O throughout its methods, or are dependencies managed at clear boundaries?
5. **Domain representation:** Can invalid values be passed using `String`/`int`/multiple booleans? Would an enum/value object help?
6. **Duplication:** Does the business logic exist elsewhere? Is it genuinely shared or merely coincidentally similar?
7. **Tests:** Can you state a clear input and expected output/exception? Do existing tests protect the change?
8. **Scope:** What is the smallest refactoring, and how can unchanged behavior be demonstrated?

A useful code-review report might say: **"For change X, we had to edit the same rule in A/B/C, risking inconsistency. Move the shared rule into Y and preserve boundary tests Z."** This is more actionable than "the code is bad; apply SOLID."

## 9. Common Mistakes

**Treating SOLID as a mandatory checklist.** SRP, OCP, LSP, ISP, and DIP are design guidelines; they do not require an interface for every method or class. Start with a real problem and apply the relevant principle.

**Mixing refactoring with business changes without separating their scopes.** If a new pricing requirement changes expected output, document it as a functional change. Pure refactoring must preserve the observable contract.

**Replacing outcome tests with implementation-detail tests.** Tests asserting how often a private method is called break when classes are split, even if results stay correct. Prefer public behavior; test interactions only when they form a meaningful contract (for example, sending a notification at most once).

**Measuring only complexity before and after.** Lower complexity metrics are insufficient if the API becomes harder to use, processing gets significantly slower, or unsafe state emerges. Test and assess actual development impact.

**Mistaking additional classes for extensibility.** Numerous interfaces without real variants can scatter logic. Good abstractions make intent and likely change directions easier to understand.

**Ignoring compatibility.** Replacing `String` with `enum` in the core may still require adapters preserving existing JSON/API or database representations. Internal refactoring does not automatically permit breaking public APIs.

## 10. Self-Assessment Exercises

**Exercise 1 — Recognition:** A `ReportManager` class has methods `loadFromDatabase()`, `calculateTax()`, `renderHtml()`, and `sendEmail()`. Identify independent reasons to change, possible smells, and appropriate class boundaries. Do not decide based on names alone; consider whether the methods always change together.

**Exercise 2 — Shotgun Surgery:** Changing VAT codes requires updating the same lookup table in three services. Identify one owner for VAT rules, design tests covering existing cases, and explain why future rule changes should occur there.

**Exercise 3 — Primitive Obsession:** The signature `createAccount(String type, String status, int level, boolean active)` allows conflicting state combinations. Propose an enum or value object that rules out invalid states. Give one case where a new class would be unnecessary.

**Exercise 4 — Safe refactoring:** In `DesignSmellsDemo`, rename `PricingRules` and extract `shippingFor`. Rerun tests to confirm unchanged output. Then deliberately change the free-shipping condition from `>=` to `>` and identify the test that detects the error at 100.000 cents.

**Exercise 5 — Prioritization:** Two areas of code exist: A has 800 lines but has not changed for 18 months; B has 150 lines, changes weekly, and often causes regressions. Choose which to evaluate first, describe the evidence to collect, and explain when the choice might differ.

### Completion Criteria

You can identify **a concrete symptom**, explain **why it creates cost or risk**, gather evidence from behavior and change history, select a clearly scoped refactoring, and write tests proving that Java contracts remain correct afterward. Recognizing a code smell is diagnostic; **design improvements must be validated by outcomes**, not by changed line or class counts.
