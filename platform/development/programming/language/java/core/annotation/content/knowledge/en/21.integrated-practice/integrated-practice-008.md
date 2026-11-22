# Annotation Selection Summary Table and Self-Assessment Questions

## 1. Objectives and Usage

This integrated practice exercise helps you **decide which annotation to use, where to place it, until which stage to retain it, and who actually reads it**, and then test your ability to justify that decision. The scope covers Java core annotations on Java 17 and later: built-in Java annotations, custom annotations, meta-annotations, reflection, and annotation processing at the tool-selection level. No external frameworks are needed.

After studying this, you should be able to answer four questions yourself:

1. **Who consumes the metadata?** The Java compiler, an annotation processor, a class-file reader tool, or the running program?
2. **Where does the metadata appear?** On a class, method, field, constructor, parameter, record component, or type parameter declaration, or at a type-use site?
3. **How long must the metadata be retained?** Only in source, in the .class file, or must it be visible via runtime reflection?
4. **Is a single annotation enough?** Does it need to be included in API documentation, inherited by subclasses, repeated multiple times, or does processing logic need to be written in the program itself?

**Principle:** Annotations primarily describe metadata. Whether an annotation actually triggers checks, generates code, or changes behavior depends on whether the compiler, processor, runtime/framework, or your own code actively processes it. Adding a custom annotation to a method does **not** automatically perform validation, dependency injection, logging, or transactions.

## 2. Quick Summary Table: Choosing Built-in Annotations

| Need | Appropriate Annotation | Scope/Meaning | Selection Notes |
| --- | --- | --- | --- |
| Verify that a method actually overrides or implements a supertype method | **@Override** | The compiler checks the method declaration | Carries no meaning for the runtime to invoke the method automatically |
| Mark an API as obsolete or discouraged from further use | **@Deprecated** | Compiler/tools display warnings; the API can add **since**, **forRemoval** | Should explain the replacement in Javadoc; does not block calls on its own |
| Suppress compiler warnings that have been reviewed | **@SuppressWarnings** | On an appropriate declaration, such as **"unchecked"** or **"deprecation"** | Limit to the smallest possible scope; does not fix the underlying cause of the warning |
| Confirm that an interface is designed as a functional interface | **@FunctionalInterface** | The compiler ensures there is exactly one abstract method according to functional interface rules | Not required in order to use a lambda |
| Assert that a varargs method/constructor performs no unsafe operations per the annotation's contract | **@SafeVarargs** | Suppresses heap-pollution-related warnings when usage conditions are met | Use only when the implementation is truly safe; applicable to static/final methods, constructors, and private instance methods since Java 9 |
| Give the compiler/processor or build tool a custom domain signal | **@YourCustomAnnotation** | Declared by you, with a consumer written by you | Clearly specify @Retention, @Target, and processing rules |

**Note:** @Override, @SuppressWarnings, @Deprecated, @FunctionalInterface, and @SafeVarargs are standard annotations with Java-defined semantics. Naming your own **@OverrideLike** does not produce a similar override check; to enforce a custom check, you must build a processor or analysis tool.

## 3. Decision Table for Custom Annotations

### 3.1. Choosing @Retention Based on Where the Annotation Is Read

| Specific Need | RetentionPolicy | Retained in .class After Compilation? | Normally Visible via Runtime Reflection? |
| --- | --- | --- | --- |
| Only supports checks or code generation when source is read by the compiler/annotation processor | **SOURCE** | No | No |
| For bytecode analysis/transformation tools reading class files; the program does not need reflection | **CLASS** | Yes | No |
| Using **getAnnotation**, **getAnnotationsByType**, runtime scanning, or dynamic configuration | **RUNTIME** | Yes | Yes, when reading the right element and the annotation is valid |

If **@Retention is not specified**, the default policy is **CLASS**. Do not choose on intuition that “RUNTIME is more flexible”; runtime metadata increases coupling and requires consumer logic. However, if the true goal is reflection, you must use **RUNTIME**.

An annotation with **SOURCE** can still be processed by an annotation processor at compile time. Do not infer that *every* processor must use SOURCE: a processor can process annotations declared with other retention policies when those annotations appear in the input sources.

### 3.2. Choosing @Target Based on Where the Annotation Is Applied

| ElementType | Common Placement | Example Intent |
| --- | --- | --- |
| **TYPE** | Class, interface, enum, annotation type, record declaration | Marking the role of a type |
| **ANNOTATION_TYPE** | Declaration of an annotation type | Meta-annotation for custom annotations |
| **METHOD** | Method declaration | Operational metadata for a method |
| **FIELD** | Field declaration | Processing or mapping rules for a field |
| **CONSTRUCTOR** | Constructor declaration | Selecting the instantiation approach |
| **PARAMETER** | Parameter declaration | Rules applied to a parameter |
| **LOCAL_VARIABLE** | Local variable declaration | Marking for the compiler/analysis tools; standard reflection does not provide access to local variables |
| **TYPE_PARAMETER** | Type variable declaration such as **T** in generics | Metadata attached to a generic type parameter |
| **TYPE_USE** | Type use site, such as **List<@NonNull String>** | Correctness analysis at type-use sites; the annotation itself does not automatically perform null checks |
| **RECORD_COMPONENT** | Record component | Attaching metadata directly to a record component |
| **PACKAGE**, **MODULE** | Package/module declaration | Describing package/module-scoped metadata |

For example: if only methods are accepted, write **@Target(ElementType.METHOD)**; if both classes and methods are accepted, write **@Target({ElementType.TYPE, ElementType.METHOD})**. Omitting @Target allows the annotation to apply broadly across appropriate declaration contexts; an explicit @Target generally helps the compiler prevent misuse in invalid locations. Do not assume **TYPE** means **TYPE_USE**: an annotation intended for a *class declaration* is not automatically an annotation for the *type of a variable or expression*.

### 3.3. Additional Meta-Annotations

| Desired Property | Use | Essential Conditions/Limitations |
| --- | --- | --- |
| Annotation appears in the Javadoc of the annotated element | **@Documented** on the annotation declaration | Does not change retention or runtime behavior |
| Class-level annotation can be found on a subclass via reflection's inheritance mechanism | **@Inherited** | Only meaningful for annotations on a **class**; not inherited from interfaces, nor does it propagate method/field annotations down to subclasses |
| Allow the same annotation to appear multiple times at the same location | **@Repeatable(Container.class)** | The container has a **value()** element returning an array of the repeated annotation; the container's retention and target must be compatible |
| Set a default value for an element | **default** in the element declaration method | Allows omitting that element when applying the annotation; the default is not null |
| Use shorthand form for an annotation with a single element named **value** | **@Tag("x")** | Equivalent to **@Tag(value = "x")** |
| Annotation acting only as a flag, with no elements | Marker annotation | Use **@Marker** or **@Marker()** |

**Note on @Inherited:** **Child.class.getAnnotation(Tag.class)** can see the superclass's annotation if Tag has @Inherited. Conversely, **getDeclaredAnnotation(Tag.class)** considers only annotations declared directly on Child; annotations on interfaces or supertype methods do not appear automatically via @Inherited.

**Note on @Repeatable:** A repeated annotation may be contained indirectly inside its container in the class file. To read all repeated values, **getAnnotationsByType(Repeated.class)** is typically preferred instead of assuming **getAnnotation(Repeated.class)** returns all values.

### 3.4. Valid Element Types and Restrictions

Each annotation element is a method with **no parameters**, whose return type belongs to one of the following groups: primitive, String, Class or an appropriately parameterized Class, enum, annotation, or a **one-dimensional array** of these types. Provided values must satisfy the compile-time constant rules appropriate to the type (e.g., primitive/String), a class literal, an enum constant, or an annotation value.

Do not declare elements of type **List<String>**, **Map**, arbitrary object types, or multidimensional arrays; do not use **null** as a value or default. If an attribute is optional, choose a meaningful default and handle that value explicitly in the consumer. For elements of type **Class<?>**, the syntax used in the annotation is typically **SomeType.class**, not an object created with **new**.

Example of a valid declaration:

~~~java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface ServiceInfo {
    String name();
    int priority() default 0;
    Class<?> implementation() default Object.class;
    String[] tags() default {};
}
~~~

Usage example: **@ServiceInfo(name = "catalog", priority = 2, tags = {"api", "core"})** on a class. If **name** is omitted, the compiler reports an error because a required element has not been provided.

## 4. Six-Step Decision Flow Before Writing an Annotation

1. **Describe the requirement with a verb:** “the compiler warns”, “the processor generates source”, “the runtime scans methods”, or “a bytecode tool reads metadata”. If the goal can be achieved with a standard annotation, prefer the standard annotation.
2. **Identify the actual reader.** Without a processor/reflection consumer, a custom annotation is just data; write the consumer or remove the unnecessary annotation.
3. **Choose retention based on where it is consumed:** SOURCE for compile-only information; CLASS for class-file analysis; RUNTIME for Java reflection/runtime scanning.
4. **Restrict the target:** for example, METHOD for checking methods, TYPE_USE for checking type-use sites, RECORD_COMPONENT for record components.
5. **Determine the data shape:** marker if only a flag is needed; elements if parameters are needed; default for optional fields; @Repeatable if multiple instances on a single element are genuinely desired.
6. **Verify reading behavior, correctness, and API evolution:** whether @Inherited is needed and applicable, whether @Documented is needed, what impact renaming an element or changing its default has, whether the processor creates duplicate files, and whether the runtime finds the right annotation.

The final decision-check question: **“If the annotation is removed, which part of the program will detect it or change its behavior?”** If the answer does not point to a specific consumer, reconsider the motivation for adding the annotation.

## 5. Java 17+ Example: runtime, repeatable, inherited, and SOURCE

The complete example below illustrates three parallel decisions:

- **ModuleTag** has @Retention(RUNTIME), @Target(TYPE), @Inherited: runtime metadata on a parent class is visible via reflection on its child class.
- **Rule** is a repeatable METHOD annotation, and its container **Rules** has compatible retention/target.
- **ReviewAtCompile** has @Retention(SOURCE): the compiler can read it from source, while runtime reflection cannot see it.

Place all the code in a single file **AnnotationChoiceLab.java** in the working directory:

~~~java
import java.lang.annotation.*;
import java.lang.reflect.Method;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Inherited
@interface ModuleTag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@Repeatable(Rules.class)
@interface Rule {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Rules {
    Rule[] value();
}

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.METHOD)
@interface ReviewAtCompile {
}

@ModuleTag("core")
class ParentService {
}

class ChildService extends ParentService {
    @Rule("notBlank")
    @Rule("maxLength")
    @ReviewAtCompile
    public void execute() {
    }
}

public class AnnotationChoiceLab {
    public static void main(String[] args) throws NoSuchMethodException {
        ModuleTag tag = ChildService.class.getAnnotation(ModuleTag.class);
        Method method = ChildService.class.getDeclaredMethod("execute");
        Rule[] rules = method.getAnnotationsByType(Rule.class);

        System.out.println("module=" + tag.value());
        System.out.println("declaredModule=" +
                (ChildService.class.getDeclaredAnnotation(ModuleTag.class) != null));
        System.out.println("ruleCount=" + rules.length);
        System.out.println("rule0=" + rules[0].value());
        System.out.println("rule1=" + rules[1].value());
        System.out.println("reviewVisible=" +
                method.isAnnotationPresent(ReviewAtCompile.class));
    }
}
~~~

Compile/run on **Java 17+** from the directory containing the file:

~~~bash
javac -d out AnnotationChoiceLab.java
java -cp out AnnotationChoiceLab
~~~

Exact stdout:

~~~text
module=core
declaredModule=false
ruleCount=2
rule0=notBlank
rule1=maxLength
reviewVisible=false
~~~

**Explanation of the output:**

- **module=core**: the runtime finds ModuleTag inherited from ParentService thanks to **@Inherited**.
- **declaredModule=false**: ChildService does not declare ModuleTag itself.
- **ruleCount=2**, **rule0**, **rule1**: two Rule annotations on a single method are read as two annotations in declaration order using **getAnnotationsByType**.
- **reviewVisible=false**: @Retention(SOURCE) does not leave the annotation visible to runtime reflection.
- **Important:** There is no execution logic for notBlank or maxLength in this example. Those two strings are merely metadata; for real validation, you must write code that reads Rule and applies the rules.

To inspect the class file details:

~~~bash
javap -v -p -classpath out ChildService
~~~

You can observe **RuntimeVisibleAnnotations** or the container encoded by the compiler; the detailed output depends on the JDK version. **ReviewAtCompile** is absent from the class file because it has SOURCE retention. Note that some JVMs/compilers may display the container name differently from the form returned by reflection via **getAnnotationsByType**.

If you need to illustrate a target for a record, the separate example below demonstrates only the declaration syntax, without an accompanying consumer:

~~~java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.RECORD_COMPONENT)
@interface DisplayName {
    String value();
}

record Customer(@DisplayName("Customer ID") String id) {
}
~~~

In a real application, read annotations on **RecordComponent** using reflection if the annotation has the corresponding target and retention, or via compile-time tools. A record component differs from a regular field at the reflection API level and in its declaration concept.

## 6. Selection Table by Real-World Scenario

| Scenario | Recommended Choice | Why? | Common Mistake |
| --- | --- | --- | --- |
| Want javac to catch a misspelled override method name | @Override | The compiler already knows the override rules | Creating a custom annotation and expecting javac to understand it |
| Interface used for a lambda, wanting the compiler to enforce the number of abstract methods | @FunctionalInterface | Checks the SAM contract | Thinking the annotation is a mandatory requirement to write a lambda |
| Old API needs to warn users | @Deprecated, Javadoc on the replacement API | Marks API lifecycle | Thinking Java forbids calling a deprecated method |
| Suppress an audited unchecked warning | @SuppressWarnings("unchecked") at a narrow scope | The compiler understands the specific warning | Suppressing an entire class and hiding other errors |
| Annotation processor generates code from a marked class | Custom @Target(TYPE), typically SOURCE, and a processor | Compiler/processor reads it at compile time | Forgetting to write and register the processor |
| Non-runtime tool reads annotation attributes in .class files | Custom CLASS with an appropriate @Target | Retains metadata in bytecode | Using SOURCE and then searching for it in the JAR |
| Program at runtime selects a handler from a method annotation | Custom RUNTIME + METHOD + reflection consumer | The runtime needs to retrieve method metadata | Using CLASS and expecting getAnnotation to find it |
| Want the annotation to be present in the element's Javadoc | @Documented on the annotation type | Javadoc displays the metadata | Confusing @Documented with @Retention(RUNTIME) |
| Subclass looks up a parent class annotation via Class.getAnnotation | @Inherited with TYPE and RUNTIME | Reflection has annotation inheritance rules on classes | Expecting annotations from interfaces or methods to also inherit automatically |
| One method declares multiple rules of the same type | @Repeatable with a container and getAnnotationsByType | Allows multiple uses on a single element | Forgetting a compatible container/retention/target |
| Type analysis in List<@NonNull String> | @Target(TYPE_USE) and a tool that understands the annotation | Metadata attaches to the exact type-use site | Thinking the annotation adds null checks automatically |
| Metadata is on a record component | @Target(RECORD_COMPONENT), retention per consumer | Specifies the proper declaration context | Confusing a record component with any field of the same name |
| Annotation configuration parameter has a default value | Element with **default** | Reduces mandatory value input | Using null or a List type as an element |
| Build reports **FilerException** | Check generated file names, processors, and rounds | Usually relates to duplicate or invalid output creation requests | Renaming with a timestamp to dodge collisions |
| Runtime reports **AnnotationFormatError** | Check the loaded class/JAR, bytecode metadata, and transform tools | Relates to parsing annotation data in the class file | Randomly editing @Target or deleting sources without verifying artifacts |

The table above provides an **initial decision**. Each project must also consider processor placement, class loaders, module boundaries, and the specific contract of the consuming library.

## 7. Integrated Practice Exercises

### Exercise A — Designing an Annotation Based on Requirements

A compile-time tool reads a class annotation **@GenerateDto**, takes a class-name suffix defaulting to "Dto", and generates new source files. There is no runtime reflection functionality.

**Choose** the retention, target, and element/default, and clearly specify who processes it. Then explain why RUNTIME is not needed.

Hint to try on your own before reading the answer: a suffix name is a valid String for an annotation element; the validity of the generated file name depends on Filer rules.

### Exercise B — Declaring Multiple Repeated Conditions

A method has two rules named **"nonEmpty"** and **"maxLength"**. The runtime needs to read both via reflection and execute the corresponding validation.

**List** the retention, target, repeatable/container setup, and reflection API to use; add one sentence explaining whether the annotation by itself is enough for validation to run.

### Exercise C — Reading an Annotation on a Subclass

Suppose **@Flag** is placed on the interface **BaseApi** and class **Impl implements BaseApi**. Flag declares @Inherited, @Retention(RUNTIME), and @Target(TYPE). Will **Impl.class.getAnnotation(Flag.class)** automatically return that Flag? What if Flag is moved from the interface to Impl's direct superclass?

### Exercise D — Identifying the Stage of an Error

Pipeline: javac runs a processor that generates source files, then a bytecode tool modifies the classes; a unit test starts scanning annotations and throws **AnnotationFormatError**. The team proposes deleting the generated sources and disabling the processor.

**Propose** an evidence-based sequence of checks to find the real fault. If instead javac reports **FilerException**, how would you shift your first point of investigation?

## 8. Self-Assessment Questions (Answer Yourself Before Opening the Solutions)

### Part 1 — Multiple Choice

**Question 1.** A custom annotation is only read via reflection after the application has started. Which retention is required?

A. SOURCE · B. CLASS · C. RUNTIME · D. Any retention.

**Question 2.** If @Retention is not declared for a custom annotation, what is the default retention?

A. SOURCE · B. CLASS · C. RUNTIME · D. No annotation is compiled.

**Question 3.** To declare an annotation that is valid only on methods, you need:

A. @Target(METHOD) · B. @Retention(METHOD) · C. @Documented · D. @Inherited.

**Question 4.** Which statement is true about @Inherited?

A. Automatically propagates annotations from an interface to all implementations.  
B. Automatically propagates annotations from a parent method to an overriding method.  
C. Allows the Class API to find eligible annotations from the superclass on the subclass according to inheritance rules.  
D. Requires every subclass to redeclare the annotation.

**Question 5.** To use the same @Rule multiple times on a single method, the most suitable choice is:

A. @SuppressWarnings · B. @Repeatable and its corresponding container · C. @SafeVarargs · D. @Override.

**Question 6.** Can a SOURCE annotation be read by an annotation processor during source processing?

A. Never · B. Yes · C. Only when @Inherited is present · D. Only when @Documented is present.

**Question 7.** To attach an annotation to a type-use site **List<@Checked String>**, the main target is:

A. FIELD · B. PARAMETER · C. TYPE · D. TYPE_USE.

**Question 8.** Which annotation provides compile-time checking for a method intended to override?

A. @Override · B. @Deprecated · C. @Documented · D. @Repeatable.

**Question 9.** Which pair is accurate regarding errors?

A. FilerException is always a runtime reflection error; AnnotationFormatError is always a javac error.  
B. FilerException relates to Filer in annotation processing; AnnotationFormatError relates to annotation metadata formatting when parsed at runtime.  
C. Both are caused solely by missing @Target.  
D. Both are completely fixed by @Retention(RUNTIME).

**Question 10.** An annotation defines **String name(); int level() default 1;**. Which usage is valid on a class with the right target?

A. @Label() when name is not provided.  
B. @Label(name = "demo") using the default level.  
C. @Label(name = null).  
D. @Label(name = new String("demo")).

### Part 2 — True/False with a One-Sentence Explanation

**Question 11.** “Simply writing @Audit on a method causes Java to automatically log every method call.”

**Question 12.** “@Documented causes an annotation to be retained for runtime reflection.”

**Question 13.** “An annotation with CLASS retention can exist in a .class file even though Class.getAnnotation does not return it.”

**Question 14.** “@FunctionalInterface is a mandatory condition for an interface to be used with a lambda.”

**Question 15.** “Suppressing all warnings at the class level is always better than suppressing a specific expression/method.”

**Question 16.** “@Repeatable makes reading multiple annotations with getAnnotationsByType a useful approach.”

**Question 17.** “An annotation element can return a Map<String, String> object to store arbitrary configuration.”

**Question 18.** “A processor that avoids generating duplicate names within itself definitely cannot encounter FilerException.”

### Part 3 — Short Answer and Prediction

**Question 19.** Why does the section 5 example output show **declaredModule=false** but **module=core**?

**Question 20.** Why is **reviewVisible=false** even though @ReviewAtCompile is explicitly written on the method in source?

**Question 21.** With two @Rule annotations on a method, which reflection API should be used to retrieve both and why?

**Question 22.** State the first three diagnostic questions when seeing FilerException in a build.

**Question 23.** State the first three pieces of evidence to collect when encountering AnnotationFormatError after a bytecode instrumentation step.

**Question 24.** Design **@EndpointPermission("admin")** to be checked at runtime on a method: specify the required retention, target, and element; indicate what logic still has to be written yourself.

## 9. Answers with Explanations

### Scenario Exercise Answers

**A.** Choose a custom annotation with **@Target(TYPE)** and **@Retention(SOURCE)**; declare **String suffix() default "Dto";**. A processor in javac reads the annotation and generates source files under deterministic qualified names. Because there is no runtime consumer, there is no need to retain it in bytecode for reflection; SOURCE is sufficient for compile-time needs. The processor must avoid duplicate output names across rounds and with other processors.

**B.** Choose @Retention(RUNTIME) and @Target(METHOD) on @Rule and its container; apply **@Repeatable(Rules.class)**, declare **Rule[] value()** in @Rules, with compatible container retention and target. Reflection reads **method.getAnnotationsByType(Rule.class)**. Separate code is needed to validate nonEmpty/maxLength; the annotation only describes the rules.

**C.** **No**. @Inherited does not enable a class to inherit an annotation declared on an interface. When Flag is placed on an actual class superclass with TYPE/RUNTIME/@Inherited properly applied, **Impl.class.getAnnotation(Flag.class)** can return the inherited annotation, provided Impl does not directly carry an annotation of the same type overriding the lookup mechanism.

**D.** Preserve the stack trace and artifacts; identify the actual loaded class/JAR, run **javap -v -p** to inspect annotation attributes, compare the class before and after the bytecode tool, try disabling only the transform step and re-run the reflection test. Do not assume the processor is the culprit. If the error is **FilerException** right at javac, start from **the output name, which processor created it, which round, and which input file/source collides**; log before each createSourceFile/createResource call.

### Multiple-Choice Answers

| Question | Answer | Reason |
| --- | --- | --- |
| 1 | **C** | Runtime reflection requires RUNTIME retention. |
| 2 | **B** | The default is CLASS, not RUNTIME. |
| 3 | **A** | @Target specifies valid locations. |
| 4 | **C** | @Inherited affects looking up class-level annotations through a superclass. |
| 5 | **B** | @Repeatable with a container allows repeated use on a single element. |
| 6 | **B** | A processor processes annotations present in source. |
| 7 | **D** | TYPE_USE is for type-use sites. |
| 8 | **A** | @Override is checked by javac. |
| 9 | **B** | The two errors belong to two different stages/mechanisms. |
| 10 | **B** | name is required and level has a default; null/new String are invalid in annotation values. |

### True/False Answers

| Question | Result | Explanation |
| --- | --- | --- |
| 11 | **False** | Code/processor/framework must read @Audit and perform the logging. |
| 12 | **False** | @Documented serves documentation; @Retention(RUNTIME) serves runtime reflection. |
| 13 | **True** | CLASS is stored in the class file, though it is not a runtime-visible annotation for reflection. |
| 14 | **False** | A valid functional interface can still use lambdas without @FunctionalInterface. |
| 15 | **False** | Limit suppression to the narrowest scope and resolve the underlying warning when possible. |
| 16 | **True** | getAnnotationsByType supports reading directly or indirectly via the container. |
| 17 | **False** | Map is not a valid return type for an annotation element. |
| 18 | **False** | Collisions can still occur with original inputs, other processors, or resource paths; an internal Set does not guarantee system-wide uniqueness. |

### Short-Answer Solution Hints

**19.** **getAnnotation**, following @Inherited rules, can find ModuleTag on the superclass ParentService, while **getDeclaredAnnotation** checks only whether class ChildService declares it directly.

**20.** ReviewAtCompile has **SOURCE** retention, so the metadata is not retained for runtime reflection.

**21.** Use **getAnnotationsByType(Rule.class)**; this API returns directly present annotations and repeated annotations contained indirectly in the container under repeatable rules.

**22.** (1) Which qualified name/path is being created? (2) Which processor called Filer and in which round? (3) Does that name belong to an input source/class or was it already created by another processor in the same invocation?

**23.** (1) At which reflection API does the stack trace occur? (2) From which JAR/path does the runtime load the class? (3) Where do the annotation attributes in the class file differ before and after instrumentation?

**24.** Example declaration:

~~~java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface EndpointPermission {
    String value();
}
~~~

When using **@EndpointPermission("admin")** on a method, the program/framework must still find the annotation at runtime, retrieve **value()**, determine the caller's permissions, and **actually reject** the call if permissions do not match. Without this processing step, @EndpointPermission is only a metadata label and **provides no security**.

## 10. Self-Grading and Completion Standards

Each correct answer from **1–24** earns **1 point**; total **24 points**. For questions 19–24, count an answer as correct only if it states the **cause/mechanism** rather than merely repeating keywords.

| Correct Answers | Self-Assessment Level | Recommended Action |
| --- | --- | --- |
| **21–24** | Solid | Design your own annotations with retention/target/consumer and test both compile-time and runtime |
| **17–20** | Good | Review incorrect answers; practice repeatable, inherited, and reflection again |
| **12–16** | Needs reinforcement | Rewrite the retention/target table, run the section 5 example, and explain each line of stdout |
| **0–11** | Needs to relearn fundamentals | Distinguish compiler, processor, class file, and reflection before continuing |

To confirm mastery, try changing one thing at a time in the section 5 example: remove @Inherited, change Rule to CLASS retention and adjust its container compatibly, or change @Target(METHOD) to @Target(TYPE). **Predict the result first**, then compile/run and explain the actual output. A compile-time error caused by a wrong target is fundamentally different from the runtime not seeing an annotation due to retention.

## 11. Annotation Selection Checklist for Java Projects

- [ ] Clearly stated who reads the annotation and at which stage it is read.
- [ ] Considered standard Java annotations before creating a custom one.
- [ ] Chosen @Retention based on SOURCE/CLASS/RUNTIME.
- [ ] Restricted @Target to the exact element or type-use site where it should apply.
- [ ] Elements have valid names/types; defaults are clear and unnecessary configuration is avoided.
- [ ] Used @Documented, @Inherited, and @Repeatable only when those properties are genuinely needed.
- [ ] If repeating annotations, the container and reading API have been designed/verified.
- [ ] If using reflection, tested against compiled class files and actual runtime artifacts.
- [ ] If using a processor, logged and controlled output names across rounds and processors.
- [ ] If the annotation affects authentication, validation, transactions, or logging, there is a consumer/test proving the concrete behavior.
- [ ] Able to answer the scenarios yourself and explain why the alternative choices are wrong.

**Rule to remember:** *Choose the annotation by purpose; @Target for placement; @Retention for lifecycle; meta-annotations for additional properties; the consumer determines behavior*. A good design lets the compiler reject invalid placements, allows the reader to access the right metadata, and includes tests verifying the actual outcome.
