# Which Annotations a Processor Discovers and What Claiming Annotations Means

Annotation processing is a pluggable stage in Java compilation. When encountering an annotation, javac does not automatically run every class named Processor: it must locate **processor implementations**, know **which annotation types they support**, determine **which annotation types are present in a round**, and then decide **which types still get passed to the next processor**. That final decision is expressed by the boolean return value of **Processor.process**: returning true means **claim**, returning false means **do not claim**.

This lesson belongs to the **Annotation Processing** section of Java Advance – compilation. The focus is the standard JSR 269 protocol in the javax.annotation.processing and javax.lang.model packages. Examples compile targeting Java 17 via javac --release 17 and were verified on JDK 24.0.2. Mechanisms and log results are described accurately per experimental run; note the default processor-discovery policy changes introduced in JDK 23.

## 1. Three Distinct Things: Annotation Type, Annotation Use, and Processor

An **annotation type** is declared using the @interface keyword:

~~~java
package demo;
public @interface Flag {}
~~~

An **annotation use** is applying an annotation type to a program element:

~~~java
package demo;
@Flag
public class Use {}
~~~

An **annotation processor** is a class implementing the javax.annotation.processing.Processor interface, typically extending AbstractProcessor to reduce boilerplate. It is invoked by javac to analyze program elements, emit diagnostics, and/or generate additional sources or resources during the build.

Simply having @Flag in source **does not guarantee** any processor was discovered and invoked. An annotation type can exist with no processor at all; that is not automatically a compile error. Conversely, a processor may be discovered yet not invoked because no matching annotation type is present.

### 1.1. Selection Flow in One Round

~~~text
Source, class, and generated sources considered in round
                          |
                          v
             Identify present annotation types
                          |
                          v
         Locate configured/discovered processors
                          |
                          v
    Match against each processor's supported annotation types
                          |
                          v
       process(Set<TypeElement>, RoundEnvironment)
                          |
                +---------+---------+
                |                   |
           return false        return true
                |                   |
     Do not claim types       Claim received types
                |                   |
        Later processors may   Later processors do not receive
        receive same types     types already claimed
                          |
                          v
     If new sources/classes are created, a new round may open
~~~

**Claiming applies per annotation type per round**; it is not an operation that deletes annotations from source, not a success/failure indicator, and not a command that halts the entire compilation.

## 2. How Does javac Discover Processors?

There are two common approaches: **specifying processor classes** or **service discovery**.

### 2.1. Explicit Specification

~~~sh
javac -processor processor.MyProcessor -processorpath processor-classes ...
~~~

Where:

- **-processor**: list of package-qualified processor class names; multiple names separated by commas.
- **-processorpath**, also written **--processor-path**: path for finding processor implementations and dependencies required by the processor itself.
- **-classpath** / **-cp**: path for finding types needed by application Java sources to compile; do not automatically equate it with the processor path.

A processor may need build-only libraries that the compiled application does not need at runtime. Therefore, real projects typically declare processor dependencies separately.

Selecting processors via -processor lets learners reproduce exactly which processors participate. It bypasses choosing processor names via default service discovery, though the specified class still must load successfully.

### 2.2. Service Provider

For processors on a path, registration can be done via a file inside the processor JAR/directory:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

Example content:

~~~text
processor.FirstProcessor
processor.SecondProcessor
~~~

When annotation processing is enabled and service discovery is used, javac finds processors through this metadata on the processor lookup path. The file is named strictly after the javax.annotation.processing.Processor interface.

**JDK 23 and later changed the default:** javac no longer automatically runs annotation processors merely because a processor happens to be on the classpath without any annotation processing configuration. You must configure explicitly using -processor, --processor-path, --processor-module-path, or request -proc:full / -proc:only as appropriate. On older JDKs, defaults may differ. This lesson explicitly passes -processor so it does not rely on defaults.

### 2.3. Annotation Processing Modes

| Option | Effect |
|---|---|
| -proc:none | Disables annotation processing, still compiles source code |
| -proc:only | Runs processors without continuing to the build's normal class-generation step |
| -proc:full | Runs processors and then compiles normally |
| -processor A,B | Selects specifically named processors instead of relying on discovery |
| -processorpath path | Specifies where to locate processor implementations |
| -XprintRounds | Diagnostics for processing rounds |
| -XprintProcessorInfo | Diagnostics showing which annotations each processor matches and what claims it returns |

Different older JDK update releases support -proc:full differently; check javac --help on the compiler in use. -X options are for diagnostics and do not need to be enabled permanently on every build.

## 3. Supported Annotation Types Declare Capability, Not Scan Results

Every Processor has the method:

~~~java
Set<String> getSupportedAnnotationTypes();
~~~

It describes **the names of annotation interfaces** the processor claims to support. With AbstractProcessor, this can be declared using:

~~~java
@SupportedAnnotationTypes("demo.Flag")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class ExampleProcessor extends AbstractProcessor {
    // Must implement the process method.
}
~~~

The snippet above illustrates only the class declaration, not a runnable standalone processor. AbstractProcessor can derive supported values from annotation metadata on the class; another Processor implementation can also return the set directly from the corresponding method.

| Supported type pattern | Meaning |
|---|---|
| demo.Flag | Supports the annotation type named demo.Flag |
| demo.* | Supports annotation types matching the demo namespace per pattern syntax |
| * | Universal: every annotation type, including the empty set |
| some.module/demo.Flag | Module-prefixed type name in named-module processing environments |

Do not declare **demo.Use** if the intent is processing **@demo.Flag** on class Use; demo.Use is the annotated class name, not the annotation type. Also do not include the @ character in the supported type string.

When supporting multiple types, you can write:

~~~java
@SupportedAnnotationTypes({
    "demo.Flag",
    "demo.OtherFlag"
})
~~~

This does not mean every process call receives both. The compiler passes only **types that actually appear and remain unclaimed in the round**, while belonging to the processor's supported set.

### 3.1. Why Does the Wildcard "*" Require Caution?

A universal processor supporting "*" can be selected **even when a round has no annotations at all**. This is useful for general checkers needing to inspect root elements. However, if it always returns true, it can claim every present annotation type and prevent specialized processors from being considered for those same types. Checkers that only scan/audit source should usually return false to avoid unintended interference.

**Supporting "*"** states the processor **can** receive all types. **Returning true** is the action that **claims** the types the tool offered the processor in that specific invocation.

## 4. What Does the annotations Parameter of process Contain?

Signature of the processing method:

~~~java
@Override
public boolean process(
    Set<? extends TypeElement> annotations,
    RoundEnvironment roundEnv
) {
    // processing...
}
~~~

**annotations** holds TypeElement objects representing **annotation types**, not the annotated classes/fields/methods. For example, if 50 classes carry @demo.Flag in a round, the annotations set passed to a Flag-specific processor still typically contains **one type: demo.Flag**.

To find the annotated elements, use RoundEnvironment:

~~~java
for (TypeElement annotationType : annotations) {
    for (Element element :
            roundEnv.getElementsAnnotatedWith(annotationType)) {
        System.out.println(element.getSimpleName());
    }
}
~~~

The snippet above needs an import for javax.lang.model.element.Element and placement inside a complete processor. These elements belong to the compilation model, not runtime Class objects loaded by Class.forName. Classes being compiled do not even have bytecode to load yet.

**Two distinct scopes:**

- Annotation types present in the **round**: may include @Target and @Retention on the annotation type source itself, as well as @Flag on application classes.
- Annotation types **passed to a specific processor**: depends on supported types and what earlier processors already claimed.

For a processor supporting only demo.Flag, logs may show annotations = [demo.Flag] even if round-wide info lists java.lang.annotation.Target and java.lang.annotation.Retention as well.

## 5. What Does Claiming an Annotation Exactly Mean?

The process method returns a boolean.

~~~java
return true;  // Claim annotation types assigned in this call
~~~

~~~java
return false; // Do not claim; later processors still get a chance for those types
~~~

**True:** in the current round, the annotation types passed by the tool to the processor are marked **claimed**, so subsequent processors are not asked to process those exact types as remaining unmatched types.

**False:** those annotation types **remain unclaimed** in the round; if another processor supports them, it **may** be called to handle them.

### 5.1. Claiming Does Not Report Success Status

Returning true **does not** mean compilation passed. A processor can emit an error via Messager and still return true. Returning false **does not** mean processing failed: an auxiliary validator can finish normally and return false so other tools remain eligible.

When detecting invalid annotations, use the diagnostic mechanism:

~~~java
processingEnv.getMessager().printMessage(
    javax.tools.Diagnostic.Kind.ERROR,
    "Invalid annotation usage"
);
~~~

This is code placed inside a processor; emitting an error of kind Diagnostic.Kind.ERROR informs the compiler of an error. The claim boolean is independent of emitting diagnostics.

### 5.2. Claiming Does Not Remove a Single Annotation Use

If classes A and B both carry @demo.Flag, the processor receives **the type demo.Flag**. You cannot use return true to say “claim @Flag on A but leave @Flag on B for another processor”. The claim boolean applies at **the level of annotation types assigned in the round**, not individual annotated elements. Internal logic can still treat A/B differently, but that is the processor's own choice, not the scope of the boolean.

### 5.3. Claiming Does Not End All Rounds

A processor returning true in round 1 can still be called in round 2 if newly generated source again carries that annotation type. Claiming is scoped to **the current round**, not a permanent lock across the entire compilation.

### 5.4. Not Claiming Does Not Force Another Processor to Run

Returning false merely leaves the type unclaimed. If no other processor supports it or no eligible processor remains, nobody else is invoked. Returning false also **does not** create a new round and does not make the compiler immediately re-invoke the same processor with the same type within the current round.

## 6. Java 17 Hands-On: Two Processors Competing to Claim

We create one SOURCE annotation and two processors that both support it. One processor returns true; the other returns false. Results are observed directly by swapping their order in -processor.

Structure:

~~~text
project/
├── src/demo/
│   ├── Flag.java
│   ├── Use.java
│   └── Plain.java
├── processor-src/processor/
│   ├── TrueProcessor.java
│   ├── FalseProcessor.java
│   └── StarProcessor.java
├── processor-classes/
├── out1/
├── out2/
├── out3/
└── out4/
~~~

Save each public class under its exact stated filename. Run terminal commands from the project root.

### 6.1. Annotation Type and Application Sources

**src/demo/Flag.java:**

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface Flag {
}
~~~

**src/demo/Use.java:**

~~~java
package demo;

@Flag
public class Use {
}
~~~

**src/demo/Plain.java:**

~~~java
package demo;

public class Plain {
}
~~~

RetentionPolicy.SOURCE means the annotation does not need to be retained in class files. This **does not prevent** javac processors from seeing the annotation while reading source; compile-time annotation processing and runtime reflection querying are two different things.

### 6.2. First Processor: Returns true

**processor-src/processor/TrueProcessor.java:**

~~~java
package processor;

import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.TypeElement;

@SupportedAnnotationTypes("demo.Flag")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class TrueProcessor extends AbstractProcessor {
    @Override
    public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment roundEnv
    ) {
        System.out.println(
            "TRUE " + annotations
            + " final=" + roundEnv.processingOver()
        );
        return true;
    }
}
~~~

### 6.3. Second Processor: Returns false

**processor-src/processor/FalseProcessor.java:**

~~~java
package processor;

import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.TypeElement;

@SupportedAnnotationTypes("demo.Flag")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class FalseProcessor extends AbstractProcessor {
    @Override
    public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment roundEnv
    ) {
        System.out.println(
            "FALSE " + annotations
            + " final=" + roundEnv.processingOver()
        );
        return false;
    }
}
~~~

The two processors differ only in their claim decision. In real applications, process typically queries elements and generates code/validates; this lesson prints only status lines so the coordination mechanism is clear.

### 6.4. Compile the Processors

From the project root, create output directories. Linux/macOS:

~~~sh
mkdir -p processor-classes out1 out2 out3 out4
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force -Path processor-classes,out1,out2,out3,out4 | Out-Null
~~~

Compile both processors:

~~~sh
javac --release 17 -encoding UTF-8 -d processor-classes processor-src/processor/TrueProcessor.java processor-src/processor/FalseProcessor.java
~~~

This command creates only **the implementation classes**; it does not yet run them to process @Flag in application sources.

### 6.5. FalseProcessor Before TrueProcessor

~~~sh
javac --release 17 -encoding UTF-8 -processorpath processor-classes -processor processor.FalseProcessor,processor.TrueProcessor -d out1 src/demo/Flag.java src/demo/Use.java
~~~

**Verified lines printed by the processors:**

~~~text
FALSE [demo.Flag] final=false
TRUE [demo.Flag] final=false
FALSE [] final=true
TRUE [] final=true
~~~

Sequence of events:

1. The regular round contains type demo.Flag.
2. FalseProcessor receives [demo.Flag] and returns false, so demo.Flag remains unclaimed.
3. TrueProcessor is permitted to receive [demo.Flag] in **the same round**, returning true.
4. When processing ends, both participating processors are called in the final round with an empty set, processingOver() being true.

No extra round occurs due to FalseProcessor returning false. The final lines belong to the terminating round, not evidence that code failed processing.

### 6.6. TrueProcessor Before FalseProcessor

~~~sh
javac --release 17 -encoding UTF-8 -processorpath processor-classes -processor processor.TrueProcessor,processor.FalseProcessor -d out2 src/demo/Flag.java src/demo/Use.java
~~~

**Verified lines printed by the processors:**

~~~text
TRUE [demo.Flag] final=false
TRUE [] final=true
~~~

TrueProcessor claims demo.Flag first. FalseProcessor is not invoked because the type to process is no longer in the unmatched annotation set when its turn arrives. In this experiment, FalseProcessor does not receive the final round either because it was never activated.

Both commands still **compile cleanly**, whether claim is true or false. That proves claiming is not an error flag.

**Note on order:** we explicitly passed the -processor list in the exercise. In projects using service discovery or build tools, do not assume an unguaranteed order to create dependencies between processors.

## 7. A Universal Processor Can Run Even Without Annotations

Create **processor-src/processor/StarProcessor.java**:

~~~java
package processor;

import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.TypeElement;

@SupportedAnnotationTypes("*")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class StarProcessor extends AbstractProcessor {
    @Override
    public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment roundEnv
    ) {
        System.out.println(
            "STAR " + annotations
            + " final=" + roundEnv.processingOver()
        );
        return false;
    }
}
~~~

Compile:

~~~sh
javac --release 17 -encoding UTF-8 -d processor-classes processor-src/processor/StarProcessor.java
~~~

Run it on **Plain.java** which has no annotations:

~~~sh
javac --release 17 -encoding UTF-8 -processorpath processor-classes -processor processor.StarProcessor -d out3 src/demo/Plain.java
~~~

Output:

~~~text
STAR [] final=false
STAR [] final=true
~~~

Because StarProcessor supports "*", the tool can invoke it in a **regular round with an empty annotation set**. This is not an error. The processor can use roundEnv.getRootElements() to scan root elements even when annotations holds no types.

Compare with a processor supporting only Flag:

~~~sh
javac --release 17 -encoding UTF-8 -processorpath processor-classes -processor processor.FalseProcessor -d out4 src/demo/Plain.java
~~~

When verified, the command **prints no FALSE lines**, because the round has no demo.Flag annotation to trigger FalseProcessor. Distinguish this: a processor invoked with an empty set **differs from** a processor never invoked.

If StarProcessor were changed to return true, it could claim every annotation type offered in a round containing annotations. Universal checkers should typically **return false** to avoid inadvertently preventing specialized processors from running.

## 8. Rounds When a Processor Generates Additional Source

Annotation processing can span multiple **processing rounds**. If a processor uses Filer to create Java source containing annotations, the new source can become a root of the next round. That is why a processor that claimed a type in round 1 can still encounter **the same type** in round 2.

### 8.1. A Processor Generating an Extra @Flag Class

Create **processor-src/processor/GeneratingProcessor.java**:

~~~java
package processor;

import java.io.IOException;
import java.io.Writer;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.TypeElement;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("demo.Flag")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class GeneratingProcessor extends AbstractProcessor {
    private boolean generated;

    @Override
    public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment roundEnv
    ) {
        System.out.println(
            "GEN types=" + annotations
            + ", last=" + roundEnv.processingOver()
        );

        if (!roundEnv.processingOver() && !generated) {
            try {
                JavaFileObject file = processingEnv.getFiler()
                    .createSourceFile("generated.Extra");
                try (Writer writer = file.openWriter()) {
                    writer.write(
                        "package generated; "
                        + "@demo.Flag public class Extra {}"
                    );
                }
                generated = true;
            } catch (IOException ex) {
                throw new IllegalStateException(ex);
            }
        }
        return true;
    }
}
~~~

Compile the processor, create output and generated-source directories:

~~~sh
javac --release 17 -encoding UTF-8 -d processor-classes processor-src/processor/GeneratingProcessor.java
~~~

Linux/macOS:

~~~sh
mkdir -p generated-src output
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force -Path generated-src,output | Out-Null
~~~

Run from the project root:

~~~sh
javac -XprintRounds -XprintProcessorInfo --release 17 -encoding UTF-8 -processorpath processor-classes -processor processor.GeneratingProcessor -s generated-src -d output src/demo/Flag.java src/demo/Use.java
~~~

**Verified three lines printed by the processor:**

~~~text
GEN types=[demo.Flag], last=false
GEN types=[demo.Flag], last=false
GEN types=[], last=true
~~~

| Round | Primary source processed | Annotation type sent to processor | processingOver |
|---|---|---|---|
| 1 | demo.Flag and demo.Use | demo.Flag | false |
| 2 | generated.Extra created by processor in round 1 | demo.Flag | false |
| 3 | Final round, no new sources | empty set | true |

The second line proves: returning true in round 1 **does not permanently claim** demo.Flag across all rounds. A new root carrying the same annotation makes it appear again in the next round.

The instance variable **generated** ensures the processor does not create the same file across multiple rounds, avoiding duplicate-creation errors or uncontrolled generation loops. When using Filer, never overwrite original sources arbitrarily; each generated file must follow Filer rules and consistent naming.

### 8.2. Final Round Is Not Identical to an Empty Set in a Regular Round

There are two separate facts:

- **annotations.isEmpty()**: no annotation types were passed in this call.
- **roundEnv.processingOver()**: the tool is in the final round.

A universal processor can receive an empty set **when processingOver is false**, like StarProcessor. A processor invoked in an earlier round can receive an empty set **when processingOver is true**, like TrueProcessor or GeneratingProcessor. An empty set cannot be used as the sole signal that processing has ended.

In the final round, do not rely on creating new files to trigger further regular processing rounds. Use the final round to summarize or emit diagnostics after the necessary generation rounds have run.

## 9. Claiming and Annotation Retention Are Two Separate Concepts

Retention decides how far an annotation is kept:

| Retention | General meaning |
|---|---|
| SOURCE | Exists in source, need not be stored in bytecode |
| CLASS | Stored in class file yet not required to be visible via runtime reflection |
| RUNTIME | Queryable at runtime via reflection under appropriate conditions |

Processors use the compiler model, so they can process SOURCE annotations. **Claiming does not alter retention**: returning true does not turn SOURCE into RUNTIME, nor does it delete the annotation type from class files.

The lesson's @Flag example has SOURCE retention. The processor still receives demo.Flag and logs during compilation. If the application later needs reflection to see the annotation, declare RUNTIME retention appropriately; flipping return true/false does not satisfy that requirement.

## 10. Repeatable Annotations and Overlooked Types

With repeatable annotations, a type like Tag can be applied multiple times on the same element via a container annotation Tags. Per the Processor specification, **an annotation wrapped inside a container does not automatically count as a present annotation type** merely by appearing under the container. Therefore, processors handling repeatable annotations should consider supporting **both the repeatable type and the container type**:

~~~java
@SupportedAnnotationTypes({
    "demo.Tag",
    "demo.Tags"
})
~~~

This is illustrative metadata only; to run, Tag, Tags, and @Repeatable must be defined accordingly. Do not assume that writing multiple @Tag always places the exact same combination of types in annotations across all source/bytecode forms.

With named modules, the API also permits supported annotation type names with a module prefix like moduleName/package.Annotation to disambiguate when necessary. The basic exercise uses the unnamed module, so demo.Flag is fully qualified and clear enough.

## 11. The Claim Mechanism Does Not Override Semantic Checks

An annotation processor can check domain rules and report its own errors, yet javac remains responsible for checking Java code: types, names, access, returns, and other language constraints.

- Returning true does not excuse Java errors.
- Returning false does not tell the compiler processing failed.
- A processor can generate new source, yet that source must still compile/pass validation.
- A processor running cleanly does not prove generated code runs properly at runtime.
- If a processor throws an unhandled exception, the compiler may stop processing or fail the build; that is completely different from the claim boolean.

When reporting necessary business/rule errors, use **Messager**. When generating sources/resources, use **Filer**. When resolving types or elements, use **Elements**, **Types**, **RoundEnvironment**. Do not turn process's boolean return value into a custom error code.

## 12. Lifecycle of a Processor

A normal processor is instantiated and initialized **once per tool processing run**, not a new instance per round:

~~~text
Locate processor name/instance
       |
       v
constructor -> init(ProcessingEnvironment)
       |
       v
getSupportedAnnotationTypes(), getSupportedSourceVersion(), options
       |
       v
process(... round 1 ...)
       |
       v
process(... subsequent rounds if invoked ...)
       |
       v
process(... final round if processor participated ...)
~~~

Hence fields such as **generated** in GeneratingProcessor can retain state across rounds of **the same invocation**. However, never rely on such fields to share state between two independent javac runs, even when builds use a daemon or run concurrently.

A processor being discovered does not guarantee process is called; in the Plain.java experiment with FalseProcessor, the processor received no processing round because no matching type existed.

## 13. Diagnosing When a Processor Fails to Run or Gets Blocked

An effective investigation sequence:

1. **Is the processor implementation compiled?** Check processor-classes or processor JAR for the right package/class name.
2. **Is annotation processing enabled?** Is -proc:none present? Are processor/processor path or an appropriate -proc mode configured?
3. **Is service discovery valid?** Is META-INF/services/javax.annotation.processing.Processor named properly, and does the implementation have a suitable constructor?
4. **Is the supported annotation type name right?** demo.Flag differs from Flag, demo.Use, and module-qualified names.
5. **In which round does the annotation appear?** Use -XprintRounds, checking root elements and generated sources.
6. **Did an earlier processor claim the annotation?** Use -XprintProcessorInfo, checking return true/false.
7. **Was the processor ever activated?** If it never matched once, the final round is not required to call it.
8. **Is the source version compatible?** @SupportedSourceVersion and JDK/source levels can emit warnings when mismatched.
9. **Are there constructor/init/process errors?** Read compiler diagnostics rather than inspecting only stdout.
10. **Do IDE and terminal use the same config?** Compare JDK, processorpath, proc mode, flags, and output.
11. **Does the processor emit files properly?** Track Filer, generated sources, and duplicate-creation cases.
12. **Is a universal processor claiming too broadly?** A processor supporting "*" and returning true can shadow other processors.

Diagnostic example:

~~~sh
javac -XprintRounds -XprintProcessorInfo --release 17 -processorpath processor-classes -processor processor.FalseProcessor,processor.TrueProcessor -d out1 src/demo/Flag.java src/demo/Use.java
~~~

In the output, javac reports which round contains which annotation types, which processor **matches**, and whether it returns true/false. Exact stdout/stderr logs and detailed formatting order may differ across IDEs, OSes, or JDKs; what matters is the meaning of those fields.

## 14. Rules for Designing Well-Cooperating Processors

| Scenario | Typically sensible claim choice |
|---|---|
| Exclusive processor handling a dedicated annotation type as primary component | May return true if intending to claim the type |
| Checker only emitting warnings and wanting other tools to continue | Return false |
| Processor supporting "*" merely scanning root elements | Typically return false to avoid claiming all annotations |
| Multiple processors needing to read the same annotation type | Design coordination mechanisms and avoid unnecessary early claiming |
| Codegen processor spanning multiple rounds | Hold state per invocation, claim appropriately per type/round |
| Processor emitting errors | Use Messager ERROR; decide claiming independently |

Do not rely on implicit discovery order as a “contract” for complex pipelines. If one processor needs another processor's output, clearly organize generating source in an earlier round and reading generated source in a later round, or split into build tasks with explicitly declared dependencies.

## 15. Security of Annotation Processing

Annotation processors are **code executing during the build**. A third-party processor can access environment variables/files with the privileges of the javac process. Explicitly configuring processor path/processor lists reduces the risk of inadvertently executing unwanted code on the classpath.

Trustworthy practices:

- Select processors from controlled dependencies/versions.
- Separate compile dependencies, annotation processor dependencies, and runtime dependencies.
- Never leak environment secrets into generated sources/logs.
- Track generated sources and verify build artifacts before release.
- In CI, use least privilege and verify consistent JDKs/toolchains.
- When upgrading JDKs, re-check how processors are activated; pay particular attention to javac's default change from JDK 23.

## 16. Practice Questions and Guided Answers

**Exercise 1.** Twenty classes use @demo.Flag in one round. How many TypeElements does a processor supporting demo.Flag receive in the annotations parameter? Answer: by annotation type, the set contains demo.Flag; use roundEnv.getElementsAnnotatedWith to locate those specific elements.

**Exercise 2.** Why did FalseProcessor before TrueProcessor make both print [demo.Flag], while reversing the order made only TrueProcessor print? Answer: false leaves the type unclaimed; true claims it within the round.

**Exercise 3.** Plain.java uses no annotations. Why was StarProcessor invoked while FalseProcessor was not? Answer: "*" can match the empty set in a regular round; demo.Flag cannot.

**Exercise 4.** Why did GeneratingProcessor return true in round 1 yet still see demo.Flag in round 2? Answer: generated.Extra source introduced the annotation type anew in the new round, while claiming applies per round.

**Exercise 5.** A processor detects an invalid annotation yet returns true. Will the compiler definitely fail? Answer: no; an ERROR diagnostic must be emitted via Messager or an actual compiler error must occur.

**Exercise 6.** Why is SOURCE retention still received by processors? Answer: javac processes the source model at compile time, before class files/runtime are required to retain annotations.

**Exercise 7.** A project has a processor JAR on the classpath, yet javac 24 does not automatically run the processor. What should be done? Answer: configure processing explicitly via -processor or processor path/-proc:full per compiler docs, without relying on implicit discovery.

**Exercise 8.** If a universal validator does not want to block other processors, what should it return and why? Answer: return false because "*" can match many annotation types and returning true claims the passed set.

## 17. Misconceptions to Avoid

**“Having @Flag means the processor will run.”** False. Discovery/activation and matching supported annotation types are required.

**“The annotations set contains a list of every class using @Flag.”** False. It contains **TypeElements for annotation types**. To get specific classes/methods/fields, use RoundEnvironment.

**“@SupportedAnnotationTypes lists annotations encountered in source.”** False. It is a declaration of **supported capability**, not per-round scan results.

**“Returning true = processing succeeded; false = failed.”** False. The boolean expresses claiming, and cannot substitute for errors/diagnostics.

**“Claiming an annotation removes it from the class.”** False. Retention and class file metadata follow their own rules.

**“Claiming in round 1 forbids generated code from using that annotation in round 2.”** False. Claim decisions are evaluated per round.

**“If annotations is empty, it is definitely the final round.”** False. A universal processor can receive an empty set in a regular round.

**“Every declared processor will be called in the final round.”** False. A processor that was never activated may not be called.

**“Using a wildcard and always returning true is the safest approach.”** False. It can accidentally claim every annotation type and block other processors.

## 18. Official References

- Oracle Java SE 24, **javax.annotation.processing.Processor**: https://docs.oracle.com/en/java/javase/24/docs/api/java.compiler/javax/annotation/processing/Processor.html
- Oracle Java SE 24, **AbstractProcessor**: https://docs.oracle.com/en/java/javase/24/docs/api/java.compiler/javax/annotation/processing/AbstractProcessor.html
- Oracle Java SE 24, **RoundEnvironment**: https://docs.oracle.com/en/java/javase/24/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html
- Oracle Java SE 24, **The javac Command**: https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html
- Inside Java / OpenJDK, **JDK 23: Changes Default Annotation Processing Policy**: https://inside.java/2024/06/18/quality-heads-up/
- **JSR 269** — Pluggable Annotation Processing API, the foundation of the javax.annotation.processing and javax.lang.model packages.

**Conclusion:** to understand which annotations a processor handles, clearly separate **discovery → supported annotation types → present/unclaimed annotation types in the round → process → return true/false → next round**. Claiming is a coordination contract among processors at compile time, not an operation mutating annotations in source code, not an error code set, and not a runtime control mechanism.
