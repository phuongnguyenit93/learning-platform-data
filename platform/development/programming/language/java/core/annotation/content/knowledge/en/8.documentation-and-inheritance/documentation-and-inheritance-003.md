# @Inherited and Annotation Lookup Through Superclasses in Java

An annotation applied to a superclass **can be found when querying annotations on a subclass** if that annotation type is marked with the **@Inherited** meta-annotation. Java applies this rule when looking up annotations on a **class declaration**, traversing up the superclass chain if the class in question does not directly declare the corresponding annotation.

Importantly, **@Inherited does not copy the annotation into the subclass** and also does not mean that every annotation on a class, method, field, or interface is inherited. This is a rule about the presence of an annotation during lookup, especially noticeable through the reflection API.

## 1. How to Declare an Inherited Annotation

**@Inherited** is in the **java.lang.annotation** package and is applied to an **annotation type declaration**, not directly to a subclass.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Configuration {
    String value();
}
~~~

Each meta-annotation has its own role:

- **@Inherited** enables the rule to look up the annotation on a superclass when the subclass does not directly declare an annotation of the same type.
- **@Retention(RetentionPolicy.RUNTIME)** retains the metadata so it can be queried via reflection at runtime. If retention is not specified, the default is **CLASS**; in that case, you cannot expect **Class.getAnnotation(...)** to find the annotation through reflection.
- **@Target(ElementType.TYPE)** restricts where Configuration can be used to type declarations such as a class, interface, enum, or annotation type. Being able to *place* an annotation on an interface does not mean that annotation is propagated from the interface to an implementing class.
- **String value()** is an element of Configuration. The name **value** allows the shorthand **@Configuration("prod")** instead of **@Configuration(value = "prod")**.

Usage example:

~~~java
@Configuration("production")
class BaseService {
}

class OrderService extends BaseService {
}
~~~

The following call can find Configuration from BaseService when looking it up on OrderService:

~~~java
Configuration config =
        OrderService.class.getAnnotation(Configuration.class);
System.out.println(config.value()); // production
~~~

The query snippet above assumes that the Configuration type has runtime retention and BaseService is directly annotated as shown in the example. In real code, **getAnnotation(...)** can return **null**, so you should check it before calling **value()**.

## 2. Lookup Rules in the Superclass Chain

For an annotation type **A** marked with **@Inherited**, when querying **SomeClass.class.getAnnotation(A.class)**, it can be understood in the following order:

1. Check whether the queried class has an annotation of type **A** directly on its declaration. If so, use that annotation.
2. If not, and A carries **@Inherited**, check the **direct superclass**.
3. If the superclass also does not directly declare A, continue moving up the superclass chain.
4. Stop when a matching annotation is found; if it reaches **Object** without finding one, the result is **null**.

Example:

~~~text
@Policy("root")
class Root
    │
    └── class Intermediate extends Root
              │
              └── class FinalChild extends Intermediate
~~~

Suppose Policy is an annotation with **@Inherited** and **RUNTIME**. When querying **FinalChild.class.getAnnotation(Policy.class)**, Java can find Policy from Root after traversing through Intermediate. It is not required for every intermediate class to redeclare the annotation.

**Only superclasses in the extends chain are considered.** A class can implement multiple interfaces, but Java does not search for @Inherited from the list of interfaces to return an annotation for the implementing class.

### Subclass Redeclaring the Same Annotation

~~~java
@Policy("root")
class Root {
}

@Policy("child")
class Specialized extends Root {
}
~~~

When looking up Policy on Specialized, the result is **"child"**. The direct annotation on the subclass takes precedence, so the instance on Root is not retrieved for the same annotation type. The two instances do not automatically merge their elements together.

For example, if Policy has elements **name()** and **active() default true**, and the subclass itself declares **@Policy(name = "child")**, then **active()** takes the default of the *Policy type*, rather than inheriting an **active = false** value that the superclass might have explicitly declared in the superclass's annotation.

## 3. How @Inherited Differs from Class, Method, and Field Inheritance

Behavior inheritance via **extends** is a mechanism of Java's type and method system. Annotation inheritance via **@Inherited** is a metadata lookup rule on a **class**.

| Scenario | Is the annotation automatically found via @Inherited? | Explanation |
| --- | --- | --- |
| Class B extends A, A has **@Policy**, and Policy has **@Inherited** | Yes | Querying class B can walk up to superclass A |
| Class C extends B extends A | Yes, unless shadowed by a direct instance on a closer class | Lookup continues up the superclass chain |
| B has its own **@Policy** | Uses B's instance | The direct annotation on B takes precedence |
| Class B implements interface I annotated with **@Policy** | No | @Inherited does not follow implements relationships |
| Interface J extends interface I annotated with **@Policy** | Not via the @Inherited mechanism | The lookup rule only applies to a class's superclasses |
| A method in a subclass overrides an annotated method in the superclass | No | @Inherited does not copy annotations to overriding methods |
| A field in the superclass has an annotation and the subclass declares a new field with the same name | No | @Inherited does not propagate annotations from one field to another |
| The annotation type lacks **@Inherited** | No | The subclass does not automatically have the annotation unless directly declared |

For instance, the following snippet clearly illustrates the limitation for methods:

~~~java
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Logged {
}

class Parent {
    @Logged
    public void execute() {
    }
}

class Child extends Parent {
    @Override
    public void execute() {
    }
}
~~~

Even though **Logged** carries @Inherited, the expression **Child.class.getDeclaredMethod("execute").getAnnotation(Logged.class)** returns **null**. The @Inherited mechanism only takes effect when an annotation is used to annotate a **class**; it does not apply to propagating annotations across method override chains. Conversely, the **@Override** annotation on Child's execute verifies proper overriding behavior at compile time and is unrelated to inheriting Logged.

**A common source of confusion:** if Child *does not override* execute, **Child.class.getMethod("execute")** can return the **Method** object belonging to Parent's declaration. When reading Logged on that Method, Parent's annotation can be seen because you are inspecting the method declared in Parent itself. That is **not** an @Inherited effect applied to a method of Child.

## 4. How Do getAnnotation and getDeclaredAnnotation Differ?

When using **Class** reflection, these two methods answer two different questions:

~~~java
Configuration effective =
        Child.class.getAnnotation(Configuration.class);

Configuration local =
        Child.class.getDeclaredAnnotation(Configuration.class);
~~~

- **getAnnotation(...)**: finds an annotation of the requested type that is **present** on the class. For an annotation marked with @Inherited, the result may come from a superclass.
- **getDeclaredAnnotation(...)**: looks only for an annotation **directly declared** on the queried class, ignoring any annotations found via the inheritance mechanism.
- **isAnnotationPresent(...)**: returns a boolean indicating whether an annotation of that type is present following the same lookup semantics as **getAnnotation(...)**.
- **getAnnotations()**: returns an array of annotations present on the class, which may include annotations inherited from a superclass if the annotation type permits it.
- **getDeclaredAnnotations()**: returns only annotations directly declared on the class, excluding inherited ones.

Comparison table when **@Configuration** has @Inherited:

| Class | getAnnotation(Configuration.class) | getDeclaredAnnotation(Configuration.class) |
| --- | --- | --- |
| **BaseService** with @Configuration | Present | Present |
| **OrderService extends BaseService**, without Configuration | Present, receives instance from BaseService | null |
| **IndependentService** without Configuration and not extending a class with Configuration | null | null |
| **CustomService extends BaseService** with its own @Configuration | Present, receives direct instance from CustomService | Present |

From Java 8 onward, **getAnnotationsByType(...)** and **getDeclaredAnnotationsByType(...)** are also available for working with *repeatable annotations*. These APIs support finding annotations that may be contained indirectly inside a container; they differ from the single-annotation APIs in how they handle repeatable annotations. When a problem requires multiple annotations of the same type, you should use the *ByType* APIs and read up on @Repeatable rules rather than inferring solely from getAnnotation.

## 5. Standalone Java 17+ Example: Inheritance, Shadowing, and Interfaces

Create the file **src/demo/InheritedLookupDemo.java**:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Mode {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface LocalOnly {
}

@Mode("base")
@LocalOnly
class Base {
}

class Middle extends Base {
}

class Leaf extends Middle {
}

@Mode("override")
class Overridden extends Base {
}

@Mode("interface")
interface Contract {
}

class ContractImpl implements Contract {
}

public class InheritedLookupDemo {
    public static void main(String[] args) {
        inspect(Base.class);
        inspect(Middle.class);
        inspect(Leaf.class);
        inspect(Overridden.class);
        inspect(Contract.class);
        inspect(ContractImpl.class);
    }

    private static void inspect(Class<?> type) {
        Mode effective = type.getAnnotation(Mode.class);
        Mode declared = type.getDeclaredAnnotation(Mode.class);
        LocalOnly local = type.getAnnotation(LocalOnly.class);

        String mode = effective == null
                ? "<none>" : effective.value();

        System.out.println(type.getSimpleName()
                + ": mode=" + mode
                + ", declaredMode=" + (declared != null)
                + ", localOnly=" + (local != null));
    }
}
~~~

From the directory containing **src**, compile and run:

~~~bash
javac -encoding UTF-8 -d out src/demo/InheritedLookupDemo.java
java -cp out demo.InheritedLookupDemo
~~~

Stdout:

~~~text
Base: mode=base, declaredMode=true, localOnly=true
Middle: mode=base, declaredMode=false, localOnly=false
Leaf: mode=base, declaredMode=false, localOnly=false
Overridden: mode=override, declaredMode=true, localOnly=false
Contract: mode=interface, declaredMode=true, localOnly=false
ContractImpl: mode=<none>, declaredMode=false, localOnly=false
~~~

**Result analysis:**

1. **Base** directly declares **@Mode("base")** and **@LocalOnly**, so the corresponding checks are all true.
2. **Middle** and **Leaf** do not directly declare Mode, yet **getAnnotation(Mode.class)** finds Mode from Base because Mode has @Inherited. Therefore, **declaredMode** remains false on both classes.
3. **LocalOnly** does not have @Inherited, so subclasses do not receive LocalOnly through class reflection lookup.
4. **Overridden** has **@Mode("override")** directly, so it receives "override" and does not receive "base" from Base for the same Mode type.
5. **Contract** is an interface directly annotated with Mode. Querying **Contract.class** itself sees Contract's Mode because it has direct metadata.
6. **ContractImpl** implements Contract but does not receive Mode from Contract: implements is not part of the @Inherited mechanism.

Both Mode and LocalOnly have **@Retention(RUNTIME)**, so the results are accessible via reflection. **@Target(TYPE)** allows applying the annotation to classes and interfaces, but it does not change the inheritance rules.

**Note on the source file:** the example uses non-public annotations and helper classes in the same **demo** package; only **InheritedLookupDemo** is public, so the entire snippet compiles in a single file with the same name as the public class.

## 6. Does @Inherited Copy the Annotation into the Subclass?

No. Distinguish between the following:

- **Directly declared annotation (directly present):** written on the class itself, such as **@Mode("base") class Base**.
- **Annotation that can be inherited (present through inheritance):** when querying a subclass, reflection searches up the superclass chain because the annotation type has **@Inherited**.
- **Annotation automatically written into the subclass's class file:** this is **not** what @Inherited does. A subclass is not automatically recompiled with or given an added annotation on its direct declaration just because its superclass carries the annotation.

You can verify this using the **javap** command:

~~~bash
javap -v -p out/demo/Base.class
javap -v -p out/demo/Middle.class
~~~

With RUNTIME retention, **Base.class** contains metadata for Mode and LocalOnly. **Middle.class** does not need to contain a direct copy of Mode for **Middle.class.getAnnotation(Mode.class)** to still return Base's annotation.

This also explains why **getDeclaredAnnotation(Mode.class)** on Middle returns null, while **getAnnotation(Mode.class)** finds Mode from Base. To check which class **declares the annotation itself**, choose the API containing **Declared**; to check the annotation value **effective during class lookup**, choose the standard API.

### Values of an Annotation Received from a Superclass

When an annotation is found from a superclass, its elements retain the meaning of the annotation declared on the source class; Java does not automatically override individual elements according to the subclass's configuration.

~~~java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Access {
    String role();
    boolean enabled() default true;
}

@Access(role = "reader", enabled = false)
class ParentArea {
}

class ChildArea extends ParentArea {
}

@Access(role = "writer")
class WriterArea extends ParentArea {
}
~~~

For **ChildArea**, calling **getAnnotation(Access.class)** retrieves Access from ParentArea, yielding **role() = "reader"** and **enabled() = false**. For **WriterArea**, Access is directly declared and yields **role() = "writer"**, **enabled() = true** from the default of the Access type. ParentArea's **enabled = false** value is not automatically merged into Access on WriterArea.

If a library requires a mechanism to merge configurations across multiple hierarchy levels or apply per-attribute precedence, that is a **custom rule the library must implement** by traversing superclasses and processing metadata. @Inherited alone does not provide per-field merging functionality.

## 7. Methods and Fields: Distinguishing Member Inheritance from Annotation Lookup

Consider the following example:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@Inherited
@interface Tracked {
}

class SuperController {
    @Tracked
    public void handle() {
    }
}

class ChildController extends SuperController {
}
~~~

Because ChildController does not override **handle**, reflection via **ChildController.class.getMethod("handle")** locates the public method declared in SuperController. If you check **getDeclaringClass()**, the result is **SuperController.class**; when calling **getAnnotation(Tracked.class)** on that Method, SuperController's Tracked appears.

Now, if ChildController overrides handle without reapplying **@Tracked**:

~~~java
class ChildController extends SuperController {
    @Override
    public void handle() {
    }
}
~~~

Reflection via **ChildController.class.getDeclaredMethod("handle")** returns a **Method belonging to ChildController** and does not automatically have Tracked. This difference comes from which Method you are retrieving, not because @Inherited ever worked on methods.

Similarly, inherited fields and fields shadowed by a declaration are a matter of Java's member management; **@Inherited does not automatically attach annotations from a parent field to a child field**. If a framework has a mechanism to find annotations on overridden methods or fields according to its own rules, the results may differ from the standard reflection API. When analyzing framework behavior, you should read the documentation of that specific framework.

## 8. Limitations with Interfaces and Multi-Level Relationships

Suppose:

~~~java
@Mode("contract")
interface ServiceContract {
}

interface ExtendedContract extends ServiceContract {
}

class ServiceImpl implements ExtendedContract {
}
~~~

Neither **ExtendedContract.class.getAnnotation(Mode.class)** nor **ServiceImpl.class.getAnnotation(Mode.class)** automatically receives Mode from ServiceContract via @Inherited. Meanwhile, **ServiceContract.class.getAnnotation(Mode.class)** finds the directly declared annotation.

The reason is that @Inherited only specifies **querying the superclass of a class declaration**. It does not specify following **extends between interfaces**, nor does it traverse **implements**.

If a framework wants to support metadata from interfaces, it must have an additional lookup mechanism (for example, iterating **getInterfaces()**, recursing through parent interfaces, and applying a clear precedence order). Such a rule is **framework policy** and should not be assumed to be the default result from **Class.getAnnotation(...)**.

## 9. When Should and Shouldn't You Design with @Inherited?

**Appropriate** when an annotation describes a **class-level** policy that you want subclasses without their own declaration to inherit by default from a superclass, such as a class-classification marker or shared system configuration metadata.

For example, a library inspects a classification annotation:

~~~java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface ModuleGroup {
    String value();
}

@ModuleGroup("reporting")
class BaseReport {
}

class DailyReport extends BaseReport {
}
~~~

Querying **DailyReport.class.getAnnotation(ModuleGroup.class)** can receive "reporting". However, the grouping behavior in the product only occurs if the library **reads and uses** this information.

**You should not rely on @Inherited as the default mechanism** when you need to:

- Look up annotations on interfaces, generic type uses, methods, fields, parameters, or constructors.
- Merge individual configuration elements from multiple superclasses/subclasses in a custom manner.
- Guarantee that all frameworks interpret or scan annotations in the same way as Java reflection.
- Enforce security policies or business logic merely through the presence of an annotation, without corresponding code to inspect and enforce it.

For these requirements, you need to design and document concrete metadata-reading rules. For example, a framework can proactively traverse superclasses/interfaces/methods and combine annotations with custom logic. The presence of @Inherited on an annotation type does not guarantee that a framework will follow that exact strategy.

### @Inherited and @Documented

**@Documented** instructs documentation tools such as javadoc to include the annotation in the documentation of annotated elements according to the tool's rules. **@Inherited** affects the presence of an annotation on a class during lookup. The two meta-annotations solve different problems; an annotation type can use both if needed.

## 10. Common Pitfalls

| Assumption or Practice | Why It Is Wrong | How to Handle It |
| --- | --- | --- |
| Applying @Inherited directly to a class | @Inherited is a meta-annotation for an **annotation type**, not a regular class | Apply @Inherited to the **@interface** declaration |
| Assuming all annotations are automatically inherited by subclasses | @Inherited is required on the annotation type itself | Verify the annotation definition |
| Using getDeclaredAnnotation to find annotations from a superclass | **Declared** APIs ignore inheritance | Use **getAnnotation** when you want inherited annotations included |
| Expecting annotations from an interface to propagate to implementing classes | @Inherited does not traverse interfaces | Traverse interfaces manually or use a tool with explicit rules |
| Expecting an overriding method to automatically inherit a parent method's annotation | @Inherited has no effect on methods | Inspect the parent method or handle metadata inheritance with custom logic |
| Omitting @Retention(RUNTIME) and then querying via reflection | The default CLASS retention is insufficient for runtime reflection | Use RUNTIME if it needs to be read at runtime |
| Expecting a subclass to override only one element of a parent annotation | A subclass's direct annotation replaces the effective parent annotation of the same type | Declare all needed values or design a custom merge mechanism |
| Thinking the annotation is copied into the subclass's bytecode | @Inherited defines a lookup rule | Compare **getAnnotation** with **getDeclaredAnnotation** and inspect the class file |
| Inferring that @Inherited automatically enforces access permissions or validation | Annotations only hold metadata | The consuming component must read and enforce the policy |

## 11. Self-Check Exercises

**Exercise 1.** Given:

~~~java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Region {
    String value();
}

@Region("north")
class A {
}

class B extends A {
}

@Region("south")
class C extends B {
}

class D extends C {
}
~~~

When calling **getAnnotation(Region.class).value()** on each class, the respective results are: **A = north**, **B = north**, **C = south**, **D = south**. B receives it from A, while D receives it from C because C is the closer class that directly declares Region.

**Exercise 2.** For B and D above, what does **getDeclaredAnnotation(Region.class)** return? **null** for both because B and D do not declare Region themselves.

**Exercise 3.** If **interface I** has **@Region("shared")** and **class E implements I**, does **E.class.getAnnotation(Region.class)** return Region? **No**, because @Inherited does not follow implements.

**Exercise 4.** If a superclass has an annotation on method **run()** and a subclass overrides **run()** without the annotation, does @Inherited cause the subclass method to receive the annotation? **No**. Only if a framework writes its own rule to search parent methods can parent method metadata serve as a fallback source.

**Exercise 5.** Class F directly declares **@Region("east")** and extends A. Which takes precedence? **The direct annotation @Region("east")** on F. Java does not merge "east" with "north".

## 12. Official References

- **Java SE 17 — java.lang.annotation.Inherited:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Inherited.html — explicitly specifies superclass lookup and does not apply to interfaces or non-class targets.
- **Java Language Specification §9.6.4.3 — @Inherited:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.3 — describes inherited annotations on classes.
- **Java SE 17 — Class.getAnnotation/getDeclaredAnnotation:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html — distinguishes between present annotations and directly declared annotations.
- **Java SE 17 — AnnotatedElement:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html — defines the terms directly present, present, associated, and annotation lookup methods.

When encountering the question "Does a superclass annotation apply to its subclass?", you must first determine **whether the annotation type has @Inherited**, **whether the annotation is placed on a class or a member**, **whether the relationship is extends or implements**, and **which API is being called**. These four factors determine the metadata lookup result in Java reflection.
