# @Retention and RetentionPolicy Policies in Java

## 1. What Question Does \`@Retention\` Answer?

When declaring an annotation type in Java, we can decide **until which phase the metadata of that annotation type is retained**. The \`java.lang.annotation.Retention\` meta-annotation allows setting this policy:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface Audited {
    String value();
}
```

\`@Retention\` **is placed on the declaration of an annotation type** (\`@interface Audited\`); its argument is a constant of the \`RetentionPolicy\` enum.

Do not confuse the two operations:

- **Declaring an annotation type**: \`@Retention(RetentionPolicy.RUNTIME) @interface Audited { ... }\` defines the metadata retention lifecycle of \`Audited\`.
- **Using an annotation**: \`@Audited("payment") class PaymentService {}\` attaches metadata to a specific declaration. The policy declared on \`Audited\` determines which phases the metadata from this usage is carried through.

This is a policy about **annotation retention** during compilation and program execution; it **does not say that Java will automatically execute business behavior**. To produce behavior, there must be a compiler, annotation processor, bytecode-reading tool, Reflection, or framework that actually processes the metadata.

## 2. Three Policies in \`RetentionPolicy\`

Java defines three main values:

| Policy | Present in source code | Written to \`.class\` file | Readable via standard Reflection at runtime? | Typical use case |
| --- | --- | --- | --- | --- |
| \`RetentionPolicy.SOURCE\` | Yes | No | No | Information needed only when analyzing/compiling source code |
| \`RetentionPolicy.CLASS\` | Yes | Yes | No | Metadata that needs to be kept in bytecode for class analysis/transformation tools |
| \`RetentionPolicy.RUNTIME\` | Yes | Yes | Yes | Metadata that Java code or a framework needs to read at runtime via Reflection |

Remember the three levels in the order **SOURCE → CLASS → RUNTIME**, meaning metadata persists through increasingly more phases:

```text
.java source code
   │
   ├── @Retention(SOURCE) ──> readable by compiler/processor ──> not stored in .class
   │
   ├── @Retention(CLASS)  ──> compiler/processor ──> stored in .class
   │                                               │
   │                                               └── bytecode-reading tools can process it
   │                                                   (not visible to standard Reflection)
   │
   └── @Retention(RUNTIME) ──> compiler/processor ──> stored in .class
                                                   │
                                                   └── readable by runtime Reflection/frameworks
```

The diagram is about **potential presence**, without guaranteeing that any tool/processor/framework is registered to actually consume the annotation.

### \`SOURCE\`: needed only at the source code phase

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.SOURCE)
@interface SourceHint {}
```

When an element is annotated with \`@SourceHint\`, the compiler can validate syntax and Java rules. An annotation processor running during compilation can also read the annotation from the program model.

After compilation, **usages of \`@SourceHint\` are not stored in \`.class\`**. Therefore, at runtime, \`getAnnotation(SourceHint.class)\` or \`isAnnotationPresent(SourceHint.class)\` will not find the attached information.

For example, the standard \`@Override\` annotation has \`SOURCE\`: it helps the compiler verify that a method actually overrides or validly implements a method in a supertype, yet the application does not need to carry this metadata to runtime for overriding to work. \`@SuppressWarnings\` is also an example of an annotation needed only by the compiler.

**When to choose it?** When the purpose of the annotation ends at compile time and there is no need to retain the annotation placement information in bytecode.

### \`CLASS\`: stored in bytecode, not exposed to standard Reflection

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.CLASS)
@interface BytecodeHint {}
```

\`CLASS\` means **annotation usages are recorded in the \`.class\` file** so that tools that understand bytecode structure can analyze them. For instance, a build/instrumentation tool reading class files can inspect the metadata if that tool is designed to do so.

However, standard Reflection APIs such as \`Class.getAnnotation(...)\` and \`Method.getDeclaredAnnotations()\` **do not return annotations with the \`CLASS\` policy**. Being present in bytecode and being visible through Reflection are two different things.

**When to choose it?** When metadata needs to persist after compilation, but the designer does not need to query it via standard Reflection at runtime. A library that reads class files can use that metadata even though the Java program cannot see it through Reflection.

### \`RUNTIME\`: stored in bytecode and accessible at runtime

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface RuntimeHint {
    String value();
}
```

Suppose a class is annotated with \`@RuntimeHint("customer")\`. When the class is loaded and code invokes Reflection on the appropriate element, Java can return that annotation along with the value \`"customer"\`.

**When to choose it?** When actual runtime logic needs to read the metadata—for example, a framework looking up mappings, registering tests, configuring objects, or applying a rule based on an annotation. \`RUNTIME\` only makes metadata **available**; it does not invoke methods or run a framework on its own.

## 3. Default Policy: Omitting \`@Retention\` Means \`CLASS\`

This is a common source of bugs:

```java
@interface DefaultHint {}
```

When an annotation type **does not declare \`@Retention\`**, Java defaults to **\`RetentionPolicy.CLASS\`**. Therefore:

- \`@DefaultHint\` is still a valid annotation.
- Metadata attached via \`@DefaultHint\` is stored in the class file.
- Standard Reflection at runtime **cannot read** \`@DefaultHint\` merely because the annotation was stored in \`.class\`.

If your goal is for \`SomeClass.class.getAnnotation(DefaultHint.class)\` to return the metadata, you must declare the **\`RUNTIME\`** policy on the \`DefaultHint\` type and then recompile the relevant code. Changing the policy in source while still running old \`.class\` files does not guarantee that the bytecode data has been updated.

**Do not infer that \`RUNTIME\` is the default just because many framework annotations are read at runtime.** Frameworks must explicitly define annotations that require Reflection with the appropriate retention.

## 4. Complete Java 17+ Example: Testing All Three Policies and the Default

Create a file named **\`RetentionPoliciesDemo.java\`** containing all of the code below. The program uses Java SE and requires no external libraries.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
@interface SourceOnly {}

@Retention(RetentionPolicy.CLASS)
@Target(ElementType.TYPE)
@interface ClassOnly {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface RuntimeVisible {
    String value();
}

// No @Retention: the default policy is CLASS.
@Target(ElementType.TYPE)
@interface DefaultClassOnly {}

@SourceOnly
@ClassOnly
@RuntimeVisible("document-service")
@DefaultClassOnly
class DocumentService {}

public class RetentionPoliciesDemo {
    public static void main(String[] args) {
        Class<DocumentService> type = DocumentService.class;

        System.out.println("SOURCE: "
                + type.isAnnotationPresent(SourceOnly.class));
        System.out.println("CLASS: "
                + type.isAnnotationPresent(ClassOnly.class));
        System.out.println("DEFAULT: "
                + type.isAnnotationPresent(DefaultClassOnly.class));
        System.out.println("RUNTIME: "
                + type.isAnnotationPresent(RuntimeVisible.class));

        RuntimeVisible info =
                type.getDeclaredAnnotation(RuntimeVisible.class);
        System.out.println("RUNTIME value: " + info.value());
    }
}
```

Navigate in your terminal to the directory containing the file, then run:

```bash
javac -encoding UTF-8 RetentionPoliciesDemo.java
java RetentionPoliciesDemo
```

The **exact stdout** output:

```text
SOURCE: false
CLASS: false
DEFAULT: false
RUNTIME: true
RUNTIME value: document-service
```

### Explaining the Output

1. \`SourceOnly\` has \`SOURCE\`. The metadata of \`@SourceOnly\` on \`DocumentService\` serves only the compilation process; Reflection returns \`false\`.
2. \`ClassOnly\` has \`CLASS\`. \`@ClassOnly\` is written into bytecode, but standard Reflection does not expose it; hence \`false\`.
3. \`DefaultClassOnly\` has no \`@Retention\`, so it defaults to \`CLASS\`, and Reflection returns \`false\`.
4. \`RuntimeVisible\` has \`RUNTIME\`. \`@RuntimeVisible("document-service")\` is stored in a form readable by Reflection; \`isAnnotationPresent\` returns \`true\`.
5. \`getDeclaredAnnotation(RuntimeVisible.class)\` reads the annotation attached directly to \`DocumentService\`, and \`info.value()\` returns \`"document-service"\`.

This example assumes in advance that \`DocumentService\` has the \`RuntimeVisible\` annotation. In a general program, \`getDeclaredAnnotation\` **can return \`null\`**, so you should check before calling \`value()\`.

Try removing \`@RuntimeVisible("document-service")\` from \`DocumentService\`: the program still compiles, but \`getDeclaredAnnotation\` returns \`null\`; the sample code will throw a \`NullPointerException\` at \`info.value()\`. This scenario shows that \`RUNTIME\` **allows querying**, but does not guarantee that every element carries that annotation.

### Inspecting Metadata in Bytecode with \`javap\`

With the JDK, you can inspect the contents of \`.class\` after compilation:

```bash
javap -v DocumentService
```

In the annotation section of the \`javap -v\` output, you can recognize two groups:

- **\`RuntimeVisibleAnnotations\`**: represents annotations stored with the \`RUNTIME\` policy, such as \`RuntimeVisible\`.
- **\`RuntimeInvisibleAnnotations\`**: shows annotations stored with \`CLASS\`, such as \`ClassOnly\` and \`DefaultClassOnly\`.
- The usage of **\`SourceOnly\`** is not emitted into the class file due to \`SOURCE\`, so it is not among the annotations in \`DocumentService.class\`.

Do not rely on the ordering or offsets in the full \`javap -v\` output; detailed contents including the constant pool and compiler information may vary. Here, the aspects to compare are **presence in bytecode** and **retrievability via Reflection**. They are two non-synonymous axes.

## 5. Where Is \`@Retention\` Placed, and How Does It Differ from \`@Target\`?

\`@Retention\` is a **meta-annotation**: it describes **an annotation type** and is placed on an \`@interface\` declaration:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface TrackedAction {
    String value();
}

class PaymentService {
    @TrackedAction("PAYMENT")
    public void pay() {}
}
```

Distinguish clearly:

| Element | Question Answered | In the Example |
| --- | --- | --- |
| \`@Retention(RUNTIME)\` on \`TrackedAction\` | **How long** is the metadata retained? | Until runtime, readable via Reflection |
| \`@Target(METHOD)\` on \`TrackedAction\` | **Where** is the annotation applied? | On a method declaration |
| \`@TrackedAction("PAYMENT")\` on \`pay()\` | **What metadata value** does this element carry? | \`value = "PAYMENT"\` |
| Consumer of \`TrackedAction\` | **Who** reads and **what** is done with the metadata? | Must be written or configured separately |

An annotation with \`@Target(METHOD)\` can still have \`SOURCE\`, \`CLASS\`, or \`RUNTIME\`. Conversely, \`@Retention(RUNTIME)\` does not permit an annotation to be applied everywhere; \`@Target\` and Java rules still control where it can be used.

This code snippet only illustrates declaration and usage; it has no \`main\` method or consumer. If you merely compile and call \`pay()\`, having \`@TrackedAction\` **does not automatically print logs or create a transaction**.

If you need to use \`getDeclaredAnnotation(TrackedAction.class)\`, obtain the \`Method\` object corresponding to \`pay\`, because the annotation is attached to the **method**, not to \`PaymentService.class\` itself.

## 6. Processing Flow at Compile Time and Runtime

\`RetentionPolicy\` describes the potential persistence of metadata. The processor and the time of processing must still be determined separately:

### Compiler and annotation processors

When compiling Java code, the compiler validates annotations against language rules: type names, elements, value types, \`@Target\` locations, and other constraints.

An **annotation processor** registered in the compilation pipeline can read metadata on program elements using the \`javax.annotation.processing\` and \`javax.lang.model\` APIs. The processor can report errors/warnings or generate files. It does not require an annotation to have \`RUNTIME\` retention in order to read it at compile time.

Therefore:

- \`SOURCE\` is appropriate if only the processor/compiler needs the metadata during compilation.
- \`CLASS\` and \`RUNTIME\` can also be seen by a processor during compilation.
- Merely writing \`@Retention(SOURCE)\` **does not automatically trigger a processor**. A corresponding processor must be provided and enabled through compiler/build configuration.

### Bytecode-reading tools

A tool that reads \`.class\` files can observe \`CLASS\` or \`RUNTIME\` metadata when it supports the relevant class file attributes. This example is independent of Reflection and does not require the business program to be running.

If a library uses its own class file reader, do not jump to the conclusion that the annotations it consumes must have \`RUNTIME\`. You need to check the **specific metadata-reading API** of that library.

### Reflection and frameworks at runtime

Standard Reflection APIs such as \`Class.getDeclaredAnnotation\`, \`Method.getAnnotation\`, and \`Field.getDeclaredAnnotations\` only provide matching annotations that have \`RUNTIME\` retention. Frameworks that use Reflection typically require that policy for the annotations they query.

A framework may also have other mechanisms for reading metadata, caching at startup, or generating code at build time. Therefore, the right way to verify is to **identify the consumer and the retrieval mechanism**, and then choose the appropriate retention.

\`RUNTIME\` retention is only a prerequisite for an annotation to be visible via Reflection; **it does not automatically discover, invoke, or apply logic**. For example, placing Spring's \`@Transactional\` on a method does not cause Java SE to manage transactions on its own. Spring must have the appropriate supporting infrastructure and invocation path.

## 7. Common Misconceptions

### 7.1 “Does \`CLASS\` mean it only exists in source?”

No. \`CLASS\` **exists in the \`.class\` file** after compilation. The difference is that standard Reflection does not expose it. Using \`javap -v\` or a bytecode-reading tool is an appropriate way to observe it.

### 7.2 “Does \`RUNTIME\` make an annotation execute by itself?”

No. \`@Retention(RUNTIME)\` only retains metadata so that it can be read at runtime. Without a consumer, the presence of metadata does not automatically produce logs, mappings, access permissions, or transactions.

### 7.3 “Does an annotation without \`@Retention\` default to \`RUNTIME\`?”

No. The default retention value is **\`CLASS\`**. This is a common reason why a custom annotation is placed correctly yet \`getAnnotation(...)\` returns \`null\`.

### 7.4 “If it is \`RUNTIME\`, can I call \`getAnnotation\` on any object?”

No. You must read from **the exact kind of program element that carries the annotation**. For example, an annotation on a method must be read from \`Method\`, and an annotation on a field must be read from \`Field\`. Annotation inheritance mechanisms such as \`@Inherited\` have their own rules; they do not turn every method or interface annotation into automatically inherited metadata.

### 7.5 “Does retaining an annotation until runtime mean its metadata can change like a field?”

No. Annotation element values are declared according to compile-time constant rules. \`RUNTIME\` retention does not turn an annotation into mutable state or a parameter received from a request at runtime. If a value must vary by environment, you need to design corresponding configuration or runtime data.

### 7.6 “Is \`@Retention\` how you declare where an annotation applies?”

No. Placement targets are determined by \`@Target\`. For example, an annotation restricted to \`METHOD\` must still separately choose a retention policy suited to its consumer.

### 7.7 “With \`RUNTIME\`, do all other annotations placed on that annotation automatically transfer to the annotated class?”

No. If \`@MyStereotype\` is placed on a class and the declaration of \`MyStereotype\` itself has other meta-annotations, plain Reflection on the class **does not automatically traverse all meta-annotations across every level**. A consumer that wants such inference must implement its own logic. Retention only ensures that the corresponding annotation can be read at the location where its metadata is actually stored.

## 8. Which Policy Should You Choose When Designing a Custom Annotation?

Start with one question: **who needs to read the annotation, and when?**

| Practical Need | Potentially Suitable Policy | Why |
| --- | --- | --- |
| Compiler/annotation processor checks conventions at build time, then discards it | \`SOURCE\` | No need to emit metadata into the class file |
| A tool that reads or transforms \`.class\` files needs metadata, while Reflection does not | \`CLASS\` | Metadata remains in bytecode |
| Java Reflection in the application needs to read the annotation at runtime | \`RUNTIME\` | Runtime APIs can access it |
| Consumer or processing mechanism has not yet been determined | Cannot yet choose based on desired behavior | Clarify who will read the metadata first |

For example, a \`@GenerateMapper\` annotation used only by an annotation processor during compilation can use \`SOURCE\`. A \`@Route\` annotation that a custom framework reads via \`getDeclaredAnnotation\` at runtime must have \`RUNTIME\`.

**Note:** there is no reason to choose \`RUNTIME\` for every annotation “just in case.” Doing so causes metadata to additionally persist in the class file and become available through runtime Reflection; choose the policy that fits the purpose. However, if a library or framework you use mandates a specific policy, follow its contract.

## 9. Knowledge Check Exercises

**Exercise 1.** Define \`@interface Label {}\` and apply \`@Label\` to \`class A {}\`. After compilation, what does \`A.class.isAnnotationPresent(Label.class)\` return?

**Answer:** \`false\`, because without \`@Retention\`, the default policy is \`CLASS\`, which is not accessible via standard Reflection.

**Exercise 2.** Can an annotation using \`SOURCE\` be detected by an annotation processor during compilation?

**Answer:** Yes, provided the processor is registered/executed and accesses the appropriate location containing the annotation. \`SOURCE\` only specifies that the metadata is no longer in bytecode after compilation.

**Exercise 3.** \`javap -v\` displays an annotation's metadata under \`RuntimeInvisibleAnnotations\`. Can we conclude from this that \`Class.getAnnotation(...)\` will be able to read that annotation?

**Answer:** No. The metadata is written into \`.class\`, but the \`RuntimeInvisibleAnnotations\` group is not exposed by standard Reflection.

**Exercise 4.** Does changing \`@Retention(CLASS)\` to \`@Retention(RUNTIME)\` on a custom annotation cause the annotated method to execute automatically?

**Answer:** No. It only changes the metadata lifecycle; a consumer and an execution flow are still required to produce behavior.

**Exercise 5.** An annotation type has \`@Retention(RUNTIME)\` and \`@Target(METHOD)\`. Is \`MyClass.class.getAnnotation(MyAnnotation.class)\` the right way to check the annotation applied to \`doWork()\`?

**Answer:** No. You must obtain the \`Method\` object representing \`doWork()\` and then use \`method.getAnnotation(MyAnnotation.class)\` or the corresponding API.

**Exercise 6.** If a build tool reads \`.class\` files directly, what is the minimum suitable policy to retain metadata into bytecode?

**Answer:** \`CLASS\`. \`RUNTIME\` is also stored in bytecode, but is needed when runtime Reflection must see the metadata; the exact choice still depends on the consumer's requirements.

\`@Retention\` determines **how long an annotation is retained**, rather than specifying where it can be applied or its business behavior. \`SOURCE\` serves source-level processing, \`CLASS\` remains in bytecode, and \`RUNTIME\` remains in bytecode **and** is readable via standard Reflection; if \`@Retention\` is omitted, the default is \`CLASS\`.
