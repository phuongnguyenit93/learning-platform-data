# Never Share Stateful `PropertyEditor` Instances Across Threads

## 1. The Problem to Solve

In Spring Framework, `PropertyEditor` is the JavaBeans mechanism for converting text values to property types and back. `DataBinder`/`WebDataBinder` and `BeanWrapper` can use these editors when populating object properties. An editor typically **stores the value being processed inside its own instance**: calling `setAsText(...)` or `setValue(...)` mutates state, and `getValue()` or `getAsText()` then reads that state.

Therefore, **never share a stateful editor instance across multiple threads or interleaved binding sessions**. Each independent binder or usage should receive its own editor. You may reuse *immutable configuration* or *stateless factories/registrars*, provided they instantiate fresh editors when registering.

The consequence of unsafe editor sharing is that request A's value can be overwritten by request B, causing misbound data, intermittent bugs, or—in sensitive cases—cross-user data leakage.

## 2. Why Is `PropertyEditor` Prone to Race Conditions?

The `java.beans.PropertyEditor` interface has operations that depend on current state. `java.beans.PropertyEditorSupport` (the common base class) stores the value via `setValue(Object)` and returns it via `getValue()`. A custom editor typically writes:

```java
@Override
public void setAsText(String text) {
    setValue(parse(text)); // Mutates the current instance's state
}
```

The snippet above **is only an illustrative method**; it requires a surrounding editor class and `parse` method to compile.

If threads A and B share editor object `E`, the following sequence can occur:

| Step | Thread A | Thread B | Internal state of E |
| --- | --- | --- | --- |
| 1 | `E.setAsText("Alice")` | | `"Alice"` |
| 2 | | `E.setAsText("Bob")` | `"Bob"` |
| 3 | `E.getValue()` -> `"Bob"` | | `"Bob"` |

Thread A mistakenly reads B's value. Even if each method works fine single-threaded, a *set-then-read* sequence is not an atomic operation. Besides `value`, an editor may hold caches, parse state, or an object like `SimpleDateFormat` (which itself has mutable state). There is no general thread-safety guarantee for a custom `PropertyEditor` instance.

**Distinguish two issues:** Spring MVC normally creates a separate `WebDataBinder` for each request. However, if multiple binders register **the exact same editor object stored in a singleton field**, having separate binders no longer isolates editor state.

## 3. Reproducing the Bug Using Only JDK 17+

The following `SharedEditorRaceDemo.java` file **runs standalone**, requiring no Spring. Two `CountDownLatch` instances deliberately force A to read after B writes, demonstrating the bug deterministically instead of leaving it to scheduler luck.

```java
import java.beans.PropertyEditorSupport;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;

public class SharedEditorRaceDemo {
    static final class NameEditor extends PropertyEditorSupport {
        @Override
        public void setAsText(String text) {
            setValue(text == null ? null : text.trim());
        }
    }

    static void await(CountDownLatch latch) {
        try {
            latch.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(e);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        NameEditor shared = new NameEditor(); // Wrong: same instance across 2 threads
        CountDownLatch aHasWritten = new CountDownLatch(1);
        CountDownLatch bHasWritten = new CountDownLatch(1);
        AtomicReference<Object> aRead = new AtomicReference<>();

        Thread a = new Thread(() -> {
            shared.setAsText("Alice");
            aHasWritten.countDown();
            await(bHasWritten);
            aRead.set(shared.getValue());
        });

        Thread b = new Thread(() -> {
            await(aHasWritten);
            shared.setAsText("Bob");
            bHasWritten.countDown();
        });

        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("A expected: Alice; actual: " + aRead.get());
        System.out.println("Final editor value: " + shared.getValue());
    }
}
```

Compile and run:

```bash
javac SharedEditorRaceDemo.java
java SharedEditorRaceDemo
```

```text
A expected: Alice; actual: Bob
Final editor value: Bob
```

The output is deterministic because `CountDownLatch` enforces the order A writes -> B writes -> A reads. In real applications, interleaving order varies, so bugs often appear intermittently and are hard to reproduce. This example proves *loss of state isolation*, without claiming every shared editor access fails on every run.

Replacing `shared` with two separate instances (`editorA` and `editorB`), where each thread sets/reads its own editor, eliminates this overwrite interaction. To audit a Spring system, inspect both **where editors are created** and **where they are registered**.

## 4. Spring Anti-Pattern: Storing an Editor in a Singleton

The pattern below is a **flawed illustration, not a standalone program**. Suppose `TrackingCodeEditor` extends `PropertyEditorSupport` and `TrackingCode` is the property type being bound:

```java
@ControllerAdvice
class UnsafeBindingAdvice {
    private final TrackingCodeEditor sharedEditor = new TrackingCodeEditor();

    @InitBinder
    void initBinder(WebDataBinder binder) {
        binder.registerCustomEditor(TrackingCode.class, sharedEditor);
    }
}
```

`@ControllerAdvice` is typically a shared bean; the `sharedEditor` field lives with the bean. Every time `@InitBinder` runs, binders receive **the same reference**. When requests are processed concurrently, conversions can interfere with each other. Changing the field to `static`, marking it `final`, or merely adding `synchronized` onto `setAsText` alone does not solve the full problem: `final` only fixes the reference, while the set-and-read sequence still needs end-to-end isolation.

The same mistake can appear in singleton services, bean configurations, custom registries, or caches holding `PropertyEditor`s. **Never store a value-holding `PropertyEditor` in a scope wider than the binding session it serves.**

## 5. Correct Approach with `@InitBinder`: Create a Fresh Editor

In Spring MVC, instantiate and register the editor **inside the `@InitBinder` invocation**. The `TrackingCodeBindingAdvice.java` example below is a valid Java 17 class when placed in an application with `spring-webmvc`; it is an MVC configuration class, **not a standalone program with `main`**.

```java
import java.beans.PropertyEditorSupport;
import java.util.Locale;

import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.bind.annotation.InitBinder;

@ControllerAdvice
public class TrackingCodeBindingAdvice {

    public record TrackingCode(String value) {}

    public static final class TrackingCodeEditor
            extends PropertyEditorSupport {
        @Override
        public void setAsText(String text) {
            if (text == null || text.isBlank()) {
                throw new IllegalArgumentException("Tracking code is blank");
            }

            setValue(new TrackingCode(
                    text.trim().toUpperCase(Locale.ROOT)));
        }
    }

    @InitBinder
    public void initBinder(WebDataBinder binder) {
        // Each binder initialization receives a fresh editor.
        binder.registerCustomEditor(
                TrackingCode.class, new TrackingCodeEditor());
    }
}
```

When a `TrackingCode` property receives `" ab-12 "`, the editor converts it into `new TrackingCode("AB-12")`. Another binding pass's editor has its own `value` field. `registerCustomEditor(Class, PropertyEditor)` binds **the passed-in instance** to the registry; the author of the configuration is responsible for supplying an appropriate instance.

For legacy date APIs, the same principle applies:

```java
@InitBinder
public void initBinder(WebDataBinder binder) {
    SimpleDateFormat format = new SimpleDateFormat("yyyy-MM-dd");
    format.setLenient(false);
    binder.registerCustomEditor(
            Date.class, new CustomDateEditor(format, false));
}
```

This is an **illustrative method snippet**, requiring imports for `java.text.SimpleDateFormat`, `java.util.Date`, `org.springframework.beans.propertyeditors.CustomDateEditor`, and MVC annotations. Each call creates **both a fresh formatter and a fresh editor**; never promote `SimpleDateFormat` to a shared field.

## 6. Reusing Registration Rules with `PropertyEditorRegistrar`

When the same logic is needed across multiple `DataBinder`s, `BeanWrapper`s, or Spring bean creation, you can share a **stateless `PropertyEditorRegistrar` object**. Its job is to *create and register* fresh editors onto the passed-in registry; it does not retain an editor for all registries to share.

```java
import org.springframework.beans.PropertyEditorRegistrar;
import org.springframework.beans.PropertyEditorRegistry;

public final class TrackingCodeRegistrar
        implements PropertyEditorRegistrar {

    @Override
    public void registerCustomEditors(PropertyEditorRegistry registry) {
        registry.registerCustomEditor(
                TrackingCodeBindingAdvice.TrackingCode.class,
                new TrackingCodeBindingAdvice.TrackingCodeEditor());
    }
}
```

This `TrackingCodeRegistrar.java` file compiles when placed next to `TrackingCodeBindingAdvice.java` in the same package with Spring Beans on the classpath. For a manually created `DataBinder`, invoke `registrar.registerCustomEditors(binder)` during binder setup. The key rule: the registrar may be reused, yet **`new ...Editor()` must stay inside `registerCustomEditors`**. Spring documentation specifies that registrars should create new editors per registration pass, avoiding synchronization across shared editors.

If using legacy `BeanFactory`-level custom editor registration APIs, read that API's exact semantics: some mechanisms may manage shared editors with internal synchronization. Never generalize from a framework compatibility hook to conclude custom editors can be freely shared. For new configuration, prefer registrars creating fresh instances.

## 7. When to Choose `Converter` or `Formatter`?

`PropertyEditor` is a stateful JavaBeans API. For modern conversion rules, consider Spring's abstractions:

| Case | Choice | Thread-safety condition |
| --- | --- | --- |
| JavaBeans/legacy binder integration requiring `PropertyEditor` | Fresh editor per binder/registry | Do not share `value` state |
| General conversion from type `S` to `T` | `Converter<S, T>` in `ConversionService` | Implementation should be stateless or explicitly thread-safe |
| `Locale`-aware parse/format (dates, numbers, currency...) | `Formatter<T>` / `FormattingConversionService` | Hold no shared mutable parsers; use immutable APIs like `DateTimeFormatter` when suitable |

Example stateless converter: `Converter<String, TrackingCode>` has `convert(String)` returning `TrackingCode` directly from input, without going through `setValue/getValue`. A converter/formatter **can still be unsafe** if the author puts unsynchronized mutable state into a field; interface names do not magically create thread safety.

Note that `DateTimeFormatter` (in `java.time`) is immutable and safe to share; `SimpleDateFormat` (in `java.text`) is stateful/mutable and must not be shared freely across threads.

## 8. Inspecting and Fixing Concurrency Bugs

**Suspicious symptoms** include intermittent parse results under concurrent load; values from one request appearing on another request's object; bugs impossible to reproduce in sequential tests; or editor fields stored in singletons/statics/caches.

To find the root cause:

1. Search for fields/variables of type `PropertyEditor`/`PropertyEditorSupport` (especially `static` fields, `@ControllerAdvice`, `@Controller`, `@Component` fields, singleton beans, and caches).
2. Find `registerCustomEditor(...)` calls and check whether the passed instance is created inline or pulled from a shared field.
3. If using `PropertyEditorRegistrar`, verify `registerCustomEditors(...)` **instantiates a fresh editor object on every call**.
4. Audit mutable dependencies held by the editor (e.g., `SimpleDateFormat`, buffers, per-request context), even when the editor itself is newly created.
5. Write tests running multiple concurrent binding tasks with distinct inputs; each task should use its own binder/target/editor and assert output matches **that exact task's input**. Run concurrent rounds to catch interleavings, and also use latch/barrier tests when deterministic reproduction is needed.
6. Verify neither editors nor target objects from one request are handed to another thread post-bind without explicit lifecycle design.

**Preferred fix:** move editor creation into per-binding `@InitBinder`/registrar/factory; keep shared objects purely for immutable logic and configuration. Do not use `ThreadLocal<PropertyEditor>` as a default band-aid: thread pools reuse threads, leaving stale data across requests unless cleaned up strictly. Also avoid locking a global editor just to hide a race, since that creates contention and requires the entire call sequence to obey the same lock.

## 9. Self-Check

**Q:** `@InitBinder` runs for multiple requests—so is that method thread-safe?

**A:** What decides thread safety is the state it accesses. A method using local variables and creating a fresh editor for the binder shares no editor instance; a method pulling an editor from a shared field introduces a race. `@InitBinder` itself does not make mutable fields safe.

**Q:** Is wrapping `setAsText` in `synchronized` enough?

**A:** Not necessarily. If `getValue` happens after releasing the lock and another thread overwrites the value, data still mixes. Locking would have to span the entire multi-step protocol and all callers, which is hard to guarantee across frameworks; isolating instances per binding lifecycle is far simpler and cleaner.

**Q:** Can a registrar be shared?

**A:** Yes, provided the registrar holds no binding data and creates a fresh editor for each registry/registration pass. Never hold one `PropertyEditor` inside a registrar and register the same instance repeatedly.

**Quick rule of thumb:** *Share the conversion blueprint, never share a `PropertyEditor` object holding the converted value.*

## References

- Spring Framework Reference — Validation, Data Binding, and Type Conversion: https://docs.spring.io/spring-framework/reference/core/validation.html
- Spring Framework Reference — Spring MVC `@InitBinder`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html
- Spring Framework Reference — MVC Data Binding (per-request binder): https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html
- Spring Framework API — `PropertyEditorRegistry`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/PropertyEditorRegistry.html
