# isAnnotationPresent and Handling When getAnnotation Returns null in Java

When reading annotations at runtime, Java reflection provides two common approaches: **isAnnotationPresent(...)** to check whether an annotation is present, and **getAnnotation(...)** to retrieve the annotation object and read its elements. If the annotation is not found according to the lookup rules of the queried element, **getAnnotation(...) returns null**.

That is a valid situation in a program. You should not immediately invoke methods on the result without checking, because doing so can cause a **NullPointerException**. This article explains when to use each API, how to write safe handling branches, the role of **@Retention(RUNTIME)**, the differences from querying directly declared annotations, and commonly misunderstood cases such as **@Inherited** and **@Repeatable**.

## 1. Two APIs Defined on AnnotatedElement

Many reflection objects in Java implement **java.lang.reflect.AnnotatedElement**, such as **Class**, **Method**, **Field**, **Constructor**, **Parameter**, and appropriate type-reflection objects. They provide the following methods:

~~~java
boolean isAnnotationPresent(
        Class<? extends java.lang.annotation.Annotation> annotationClass);

<T extends java.lang.annotation.Annotation>
T getAnnotation(Class<T> annotationClass);
~~~

These are abbreviated signatures of the two methods in the API, not a standalone Java program.

- **isAnnotationPresent(A.class)** returns **true** if an annotation of type A is *present* on the queried element; otherwise **false**.
- **getAnnotation(A.class)** returns the annotation of type A if it is *present*; otherwise it returns **null**. The returned object has methods corresponding to the annotation elements declared in A.
- By the API contract, **isAnnotationPresent(A.class)** is equivalent in boolean result to **getAnnotation(A.class) != null**.
- If the passed **annotationClass** argument is **null**, the API may throw a **NullPointerException**. This is an API call argument error, distinct from the case where the annotation is not found and a null value is returned.

**The key term present has an important meaning.** On **Class**, if the annotation type has **@Inherited**, the result may come from a superclass; therefore, present does not always mean the annotation is written directly on the class being queried.

## 2. Minimal Example: With Annotation and Without Annotation

Declaring an annotation that can be read at runtime:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface ComponentInfo {
    String name();
}
~~~

Using it on a class:

~~~java
@ComponentInfo(name = "billing")
class BillingService {
}

class PlainService {
}
~~~

With **BillingService**:

~~~java
boolean exists = BillingService.class
        .isAnnotationPresent(ComponentInfo.class);

ComponentInfo info = BillingService.class
        .getAnnotation(ComponentInfo.class);

// exists == true
// info != null
// info.name().equals("billing")
~~~

With **PlainService**:

~~~java
boolean exists = PlainService.class
        .isAnnotationPresent(ComponentInfo.class);

ComponentInfo info = PlainService.class
        .getAnnotation(ComponentInfo.class);

// exists == false
// info == null
~~~

**Why is this not an error?** PlainService does not have ComponentInfo within the lookup scope. Java reflection uses **null** to represent absence for the **getAnnotation** API, while **isAnnotationPresent** uses **false**.

### Mistake Leading to NullPointerException

~~~java
ComponentInfo info = PlainService.class
        .getAnnotation(ComponentInfo.class);

// Wrong: info == null, so calling name() will throw NPE.
// System.out.println(info.name());
~~~

The error occurs when invoking the **name()** method on a null reference. The **getAnnotation(...)** call itself does not throw a NullPointerException merely because the annotation is not found.

## 3. When Should You Use isAnnotationPresent?

**Use isAnnotationPresent when you only need to know whether a marker exists**, which is especially suitable for marker annotations without elements.

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface InternalOnly {
}

@InternalOnly
class InternalService {
}

class PublicService {
}
~~~

Checking:

~~~java
boolean internal = InternalService.class
        .isAnnotationPresent(InternalOnly.class);

boolean external = PublicService.class
        .isAnnotationPresent(InternalOnly.class);

// internal == true
// external == false
~~~

If the program needs to decide whether to include a class in a list, a boolean flag may be sufficient. Even though the name InternalOnly suggests a purpose, the annotation **does not implement security or access policy on its own**. Application logic must actually check and enforce the desired rule.

Example of a conditional branch:

~~~java
if (serviceType.isAnnotationPresent(InternalOnly.class)) {
    // Handle according to the application's policy.
}
~~~

The **serviceType** variable in this snippet is assumed to be an already defined **Class<?>** object. This is a snippet illustrating the context, not a standalone program.

**There is no need to retrieve the annotation object** if the task is only to detect the presence of the marker.

## 4. When Annotation Values Are Needed, Call getAnnotation Once and Check for null

A clear and concise pattern:

~~~java
ComponentInfo info = serviceType.getAnnotation(ComponentInfo.class);

if (info == null) {
    System.out.println("Không có ComponentInfo");
} else {
    System.out.println("name=" + info.name());
}
~~~

Here **serviceType** has type **Class<?>**, and ComponentInfo is defined as in the previous example.

If the annotation value is only used in the branch where it is present, you can also write:

~~~java
ComponentInfo info = serviceType.getAnnotation(ComponentInfo.class);
if (info != null) {
    process(info.name());
}
~~~

The **process(...)** call is a business method defined by the program, not a built-in Java API. Only use the pattern above when handling the absent case by skipping it is appropriate.

Comparing the two styles:

~~~java
// Valid, but queries twice when the value needs to be read.
if (serviceType.isAnnotationPresent(ComponentInfo.class)) {
    ComponentInfo info =
            serviceType.getAnnotation(ComponentInfo.class);
    System.out.println(info.name());
}
~~~

~~~java
// Clearer when the annotation needs to be read.
ComponentInfo info =
        serviceType.getAnnotation(ComponentInfo.class);
if (info != null) {
    System.out.println(info.name());
}
~~~

Both are valid if referring to the same stable reflection element and the annotation exists. **When data is needed**, the second pattern is usually easier to maintain because it retrieves the object once and uses the same result to decide the branch. **When only a boolean is needed**, use isAnnotationPresent directly.

There is no need to default to two calls to "be safer". **getAnnotation != null** itself already indicates that the annotation is present under the same contract.

## 5. Three Handling Policies When getAnnotation Returns null

The right handling approach depends on the business requirements.

### 5.1. Optional Annotation: Use a Fallback Value

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface RetryConfig {
    int attempts() default 3;
}
~~~

Code to read the configuration:

~~~java
RetryConfig config =
        serviceType.getAnnotation(RetryConfig.class);

int attempts = config == null ? 1 : config.attempts();
~~~

**If @RetryConfig is not attached**, the application chooses the fallback **1**. **If @RetryConfig is present without specifying attempts**, the **attempts()** element has the default **3**.

The two situations **are not the same**:

- **No annotation:** **getAnnotation(RetryConfig.class) == null**; the application chooses a value outside the annotation.
- **@RetryConfig present with attempts omitted:** the annotation object exists; **config.attempts()** returns the default **3** declared in the annotation type.

**An annotation element's default does not create an annotation when the annotation is absent.** Therefore, do not infer that a class without @RetryConfig will automatically receive a RetryConfig object with attempts = 3.

### 5.2. Required Annotation: Report a Clear Error

If the design requires a class to definitely have the annotation, you can reject it immediately with a specific message:

~~~java
ComponentInfo info =
        serviceType.getAnnotation(ComponentInfo.class);

if (info == null) {
    throw new IllegalStateException(
            serviceType.getName() + " thiếu @ComponentInfo");
}

String componentName = info.name();
~~~

When the annotation is missing, **IllegalStateException** helps report a clear configuration error instead of letting a NullPointerException occur deeper down where **info.name()** is used. This is an application decision; Java does not inherently require every class to have ComponentInfo.

### 5.3. Optional Annotation: Use Optional

If the application's API wants to explicitly represent "present or absent", you can convert the nullable result into an **Optional**:

~~~java
java.util.Optional<ComponentInfo> maybeInfo =
        java.util.Optional.ofNullable(
                serviceType.getAnnotation(ComponentInfo.class));

String componentName =
        maybeInfo.map(ComponentInfo::name).orElse("unclassified");
~~~

**Optional.ofNullable(...)** creates an empty Optional when getAnnotation returns null. **map(...)** only invokes **name()** when the annotation object exists; **orElse(...)** provides a fallback value. This approach is useful in APIs returning optional data, though not necessarily better than if/else in every processing block.

Do not use **Optional.of(serviceType.getAnnotation(...))** if the result may be null: Optional.of does not accept null and will throw an NPE.

## 6. Complete Java 17+ Program: boolean, Values, Fallback, and Inheritance

The following example is a standalone program. It demonstrates an annotation with elements, a marker annotation, and an annotation with **@Inherited** to show the difference between an annotation looked up via the superclass and a directly declared annotation.

Create the file **src/demo/AnnotationLookupDemo.java**:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Feature {
    String name();
    int level() default 1;
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Audited {
}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Region {
    String value();
}

@Feature(name = "checkout", level = 2)
@Audited
class CheckoutService {
}

@Feature(name = "search")
class SearchService {
}

class LegacyService {
}

@Region("parent")
class ParentService {
}

class ChildService extends ParentService {
}

public class AnnotationLookupDemo {
    public static void main(String[] args) {
        inspect(CheckoutService.class);
        inspect(SearchService.class);
        inspect(LegacyService.class);

        Region inherited =
                ChildService.class.getAnnotation(Region.class);
        Region declared =
                ChildService.class.getDeclaredAnnotation(Region.class);

        System.out.println("Child inherited region="
                + (inherited == null ? "<none>" : inherited.value()));
        System.out.println("Child declared region="
                + (declared == null ? "<none>" : declared.value()));
    }

    private static void inspect(Class<?> type) {
        System.out.println("[" + type.getSimpleName() + "]");

        boolean audited = type.isAnnotationPresent(Audited.class);
        System.out.println("audited=" + audited);

        Feature feature = type.getAnnotation(Feature.class);
        if (feature == null) {
            System.out.println("feature=not configured");
        } else {
            System.out.println("feature=" + feature.name()
                    + ", level=" + feature.level());
        }
    }
}
~~~

In the directory containing **src**, compile:

~~~bash
javac -encoding UTF-8 -d out src/demo/AnnotationLookupDemo.java
java -cp out demo.AnnotationLookupDemo
~~~

Stdout output:

~~~text
[CheckoutService]
audited=true
feature=checkout, level=2
[SearchService]
audited=false
feature=search, level=1
[LegacyService]
audited=false
feature=not configured
Child inherited region=parent
Child declared region=<none>
~~~

Explanation:

1. **CheckoutService** directly has **@Audited** and **@Feature(name = "checkout", level = 2)**, so the marker is detected and both Feature elements are read normally.
2. **SearchService** does not have @Audited but has **@Feature(name = "search")**. Since **level()** has a default of **1**, the code prints **level=1**.
3. **LegacyService** does not have @Feature. **getAnnotation(Feature.class)** returns null; the if branch prints **feature=not configured** and does not invoke any element on the null value.
4. **ChildService** does not declare Region itself, but inherits from ParentService. The Region type has **@Inherited**, so **getAnnotation(Region.class)** on ChildService finds Region from ParentService, whereas **getDeclaredAnnotation(Region.class)** on ChildService itself returns null.
5. All three annotation types have **@Retention(RetentionPolicy.RUNTIME)**, so Java 17 reflection can read them at runtime.

The program uses **one public class**, AnnotationLookupDemo, in the corresponding file; the supporting annotations/classes are top-level package-private so they can coexist in the file. The java command uses the fully qualified name **demo.AnnotationLookupDemo** of the class containing main.

**What must not be inferred from the output:** Audited does not automatically enable an audit system; Feature does not automatically control a feature flag; Region does not automatically change configuration. The program or framework must read the metadata and enforce the desired behavior.

## 7. Why Can getAnnotation Be null Even When You See @ in the Code?

Several common causes should be distinguished.

### 7.1. The Annotation Does Not Have RUNTIME Retention

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.CLASS)
@interface BuildMarker {
}

@BuildMarker
class GeneratedService {
}
~~~

With standard runtime reflection:

~~~java
BuildMarker marker =
        GeneratedService.class.getAnnotation(BuildMarker.class);

// marker == null
~~~

**@Retention(CLASS)** specifies that metadata be retained in the class file, but not exposed through Java reflection at runtime in the usual way. If an annotation uses **SOURCE** retention, the metadata is not retained in the class file after compilation.

When **@Retention** is omitted, the default is **RetentionPolicy.CLASS**, not RUNTIME. If you intend to call **getAnnotation(...)** at runtime, you should declare **@Retention(RetentionPolicy.RUNTIME)**.

### 7.2. You Are Querying the Wrong Reflection Element

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Endpoint {
}

class Api {
    @Endpoint
    void handle() {
    }
}
~~~

The annotation is on **method handle**, not on the Api class declaration:

~~~java
boolean onClass =
        Api.class.isAnnotationPresent(Endpoint.class); // false

boolean onMethod =
        Api.class.getDeclaredMethod("handle")
                .isAnnotationPresent(Endpoint.class); // true
~~~

The snippet above must be placed inside a method declaring **throws NoSuchMethodException** or handling the corresponding exception. When looking for annotations on a field/parameter/constructor, retrieve the appropriate **Field**, **Parameter**, or **Constructor** object instead of only querying Class.

For a **TYPE_USE** annotation, it may be attached to the type usage of a field or return type, rather than directly to the declaration. In that case, **field.getAnnotatedType().getAnnotation(...)** or **method.getAnnotatedReturnType().getAnnotation(...)** is the appropriate API.

### 7.3. Confusing Direct Annotations with Inherited Annotations

For **Class**, **getAnnotation(A.class)** can return an annotation from a superclass if A has **@Inherited**; whereas **getDeclaredAnnotation(A.class)** only returns an annotation declared directly on the class being inspected.

If the annotation type **does not have @Inherited**, a subclass does not automatically inherit annotation lookup from its superclass through this mechanism. **@Inherited does not traverse implemented interfaces** and does not make annotations on overridden methods automatically inherited.

This explains why code can return false/null even when the annotation is visible on an interface or on a superclass method; you must check the exact **relationship** and **reflection element** being used.

### 7.4. Mistaking the Annotation Type or Not Loading the Updated Class

Having the same simple name does not prove two annotation types are the same type. For example, **com.example.audit.Mark** and **com.example.security.Mark** are two different types; calling **getAnnotation(com.example.security.Mark.class)** will not find the audit type's annotation.

In a multi-JAR/multi-class-loader environment, the annotation type in the running binary and the type passed to reflection must match exactly. Check dependencies and the actually loaded class if the result differs from expectations. After changing source code or @Retention, the program also needs to use the properly recompiled and deployed binary.

## 8. Differences Between getAnnotation, getDeclaredAnnotation, and getAnnotationsByType

| API | Result When Annotation Is Absent | Characteristics |
| --- | --- | --- |
| **isAnnotationPresent(A.class)** | false | Checks whether A is *present* on the element; equivalent to getAnnotation != null |
| **getAnnotation(A.class)** | null | Retrieves a single present annotation A, potentially considering @Inherited on Class |
| **getDeclaredAnnotation(A.class)** | null | Looks up only directly declared annotation A, without traversing inheritance |
| **getAnnotations()** | Empty array | Retrieves present annotations |
| **getDeclaredAnnotations()** | Empty array | Retrieves only directly declared annotations |
| **getAnnotationsByType(A.class)** | Empty A[] array | Supports repeatable annotations and can apply appropriate inheritance rules |
| **getDeclaredAnnotationsByType(A.class)** | Empty A[] array | Supports repeatable annotations, but only considers annotations directly/indirectly present on the element itself |

**An empty array and null are not the same.** The two single-annotation retrieval APIs use null to represent absence; the APIs returning multiple annotations use a **zero-length array** when none are found.

You should not replace **getAnnotationsByType** with **getAnnotation** when you need all repeated annotations of the same type. This case has an important difference.

### Repeatable Annotations: isAnnotationPresent Can Be false Even Though getAnnotationsByType Finds Values

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Tags.class)
@interface Tag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Tags {
    Tag[] value();
}

@Tag("fast")
@Tag("safe")
class Processor {
}
~~~

When compiling two Tag annotations of the same kind on a class, the information may be represented via the container annotation **Tags**. Therefore:

~~~java
boolean singlePresent =
        Processor.class.isAnnotationPresent(Tag.class);

Tag one = Processor.class.getAnnotation(Tag.class);
Tag[] all = Processor.class.getAnnotationsByType(Tag.class);

// singlePresent == false
// one == null
// all.length == 2
// all[0].value().equals("fast")
// all[1].value().equals("safe")
~~~

This is the standard behavior for the case of **two directly repeated @Tag annotations** shown above: Tag is indirectly contained in Tags; **getAnnotation(Tag.class)** and **isAnnotationPresent(Tag.class)** do not unwrap the container automatically. When you need to retrieve both Tags, use **getAnnotationsByType(Tag.class)**.

The rules for **repeatable annotations** have their own direct/indirect and inheritance cases; the safe approach is to choose a **ByType** API when your requirement is actually "all annotations of type A" rather than "a single present annotation A".

## 9. Should You Always Call isAnnotationPresent Before getAnnotation?

It is not necessary when you only want to read the annotation's elements. Two calls can duplicate metadata lookups while making the code longer without increasing clarity:

~~~java
// Use when only a boolean is needed.
boolean marked = type.isAnnotationPresent(Audited.class);

// Use when reading elements and handling absence.
Feature feature = type.getAnnotation(Feature.class);
if (feature != null) {
    useFeature(feature.name(), feature.level());
}
~~~

**useFeature(...)** in the example is a hypothetical business method.

For value-based logic, the practical principle is to **retrieve the annotation once, check for null, and then read the elements once you are sure the object is present**. In cases where a standalone boolean check is genuinely needed, isAnnotationPresent is the explicit choice.

If the annotation is required, instead of silently ignoring it, return a clear configuration error. If it is optional, use a sensible fallback or Optional. Choosing between a fallback and an error depends on the business contract; there is no one-size-fits-all approach.

## 10. Distinguishing null from getAnnotation and Annotation Element Values

A normal annotation element cannot declare **null** as a value:

~~~java
@interface Label {
    String value() default "unknown";
}

// Wrong: annotation element value cannot be null.
// @Label(null)
// class Invalid {}
~~~

With **@Label("ok")**, **getAnnotation(Label.class)** returns the Label object and **value()** returns **"ok"**. With **@Label** without passing value, the Label object exists and **value()** returns **"unknown"**.

For a class **without @Label**, **getAnnotation(Label.class)** returns **null** (assuming no other presence mechanism such as inheritance). That is **the absence of the annotation itself**, not "Label.value() is null".

Certain exceptions when processing incompatible binary annotations may be thrown upon accessing an element, such as **IncompleteAnnotationException** if a required element has no value in old metadata and no default in the new type. This is a binary/runtime compatibility issue distinct from the normal null when an annotation is absent. Do not rely on a null check to assume that annotation reading operations will never throw an exception.

## 11. Common Mistakes

| Mistake or Assumption | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| Calling **getAnnotation(...).value()** directly | getAnnotation may return null | Store it in a variable first, check for null, and then call the element |
| Using **Optional.of(getAnnotation(...))** | Optional.of does not accept null | Use **Optional.ofNullable(...)** |
| Calling isAnnotationPresent and still forgetting to handle the result | A boolean does not automatically guard subsequent operations | Place the logic inside an if branch or check the result of getAnnotation |
| Assuming that an element with a default means getAnnotation cannot be null | The default applies only if the annotation is present | Distinguish between a missing annotation and a missing element value |
| Omitting @Retention or leaving it as CLASS while expecting runtime reflection to read it | The default retention is CLASS | Add **@Retention(RUNTIME)** for runtime annotations |
| Looking up a method annotation using **SomeClass.class.getAnnotation(...)** | That queries the class, not the method | Retrieve the **Method** via reflection and then query it |
| Using getDeclaredAnnotation to retrieve an annotation from a superclass | Declared only inspects directly declared annotations | Use getAnnotation when @Inherited rules are needed |
| Assuming @Inherited finds annotations on implemented interfaces | @Inherited does not traverse interfaces | Traverse interfaces separately if business logic requires it |
| Using getAnnotation to retrieve all repeated @Tag annotations | Only the container annotation may be present | Use **getAnnotationsByType(Tag.class)** |
| Confusing an empty result from **getAnnotations()** with null | The API returns an array and does not use null for the empty case | Check **array.length == 0** |
| Passing **null** for annotationClass | That is an invalid argument | Pass a valid annotation class literal, such as Feature.class |

## 12. Self-Check Exercises

**Exercise 1.** A class does not have **@Feature**. What are the results of the following two calls?

~~~java
boolean present = SomeClass.class.isAnnotationPresent(Feature.class);
Feature feature = SomeClass.class.getAnnotation(Feature.class);
~~~

Assuming no applicable inherited annotation exists and Feature has runtime retention: **present = false**, **feature = null**. Calling **feature.name()** afterward will cause an NPE.

**Exercise 2.** The **@RetryConfig** type has **attempts() default 3**. Does a class without **@RetryConfig** automatically return a RetryConfig object with attempts = 3? **No.** The annotation is still absent; only when the annotation is attached with the attempts element omitted is the default 3 used.

**Exercise 3.** If a library needs to read the value of **Feature.name()** when the annotation is present, which pattern is more suitable: checking isAnnotationPresent and then calling getAnnotation, or simply calling getAnnotation and checking for null? **Simply calling getAnnotation once and checking for null** is usually clearer and more concise.

**Exercise 4.** Why does **ChildService.class.getAnnotation(Region.class)** find Region while **getDeclaredAnnotation** does not? **Region has @Inherited** and is declared on the superclass; ChildService itself does not declare it directly.

**Exercise 5.** Two **@Tag** annotations of the same type are attached to a class via **@Repeatable**. Why can **getAnnotationsByType(Tag.class).length** be 2 while **isAnnotationPresent(Tag.class)** is false? **ByType** unwraps the container annotation, whereas isAnnotationPresent only follows the presence of a Tag annotation just like getAnnotation.

## 13. Official Java Documentation

- **Java SE 17 — AnnotatedElement:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html — contracts of isAnnotationPresent, getAnnotation, getDeclaredAnnotation, and getAnnotationsByType.
- **Java SE 17 — Class:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html — reflection methods on class.
- **Java SE 17 — RetentionPolicy:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/RetentionPolicy.html — SOURCE, CLASS, and RUNTIME.
- **Java Language Specification §9.6.4.3 — @Inherited:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.3 — mechanism for finding annotations on superclasses.
- **Java Language Specification §9.6.3 — Repeatable Annotation Interfaces:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.3 — repeatable annotation and container rules.

When you only want to know whether an annotation is present, choose **isAnnotationPresent**. When you need to read values, choose **getAnnotation**, check for **null**, and handle it according to the business contract. Before concluding an annotation is missing, verify **retention**, the **reflection object**, **inheritance relationships**, and **whether the annotation is used as a repeatable annotation**.
