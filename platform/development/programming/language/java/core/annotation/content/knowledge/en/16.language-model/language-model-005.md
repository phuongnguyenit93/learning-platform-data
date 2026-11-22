# Reading Explicitly Declared Elements and Default Values in Java Annotation Processing

When a Java annotation has an element (*element*) declaring **default**, an annotation usage can **pass only some elements** and let the remaining ones take their default values. If you are writing an annotation processing tool at compile time, you need to distinguish two questions:

1. **Which elements did the code author explicitly specify at the annotation site?**
2. **What are the effective values of all elements after applying the default values from the annotation type?**

In the Java language model (**javax.lang.model**) and the Annotation Processing API (**javax.annotation.processing**), the two central APIs for these two questions are:

- **AnnotationMirror.getElementValues()**: returns **only the explicitly declared element–value pairs** in the annotation under consideration.
- **Elements.getElementValuesWithDefaults(AnnotationMirror)**: returns the element–value pairs, **including elements that receive a default** when not explicitly specified.

They are often used together with **ExecutableElement.getDefaultValue()**, which lets you query **the default value in the declaration of an annotation type element**. The three APIs have different roles and should not be conflated.

## 1. A Concrete Example: An Annotation Used with Omitted Elements

Annotation type declaration:

~~~java
@interface Endpoint {
    String path();
    int retries() default 3;
    boolean enabled() default true;
}
~~~

Applying the annotation to a class:

~~~java
@Endpoint(path = "/orders", enabled = false)
class OrderApi {
}
~~~

Here:

- **path()** has no default, so it is a **required** element. The usage site must provide **path = "/orders"**.
- **retries()** has **default 3**. The usage site does not provide retries, so when retrieving the effective value, it is **3**.
- **enabled()** has **default true**, but the usage site **explicitly specifies enabled = false**. Therefore, the effective value is **false** and is not overridden by the default.

Expected result when querying for **explicit elements**:

~~~text
enabled=false
path=/orders
~~~

When querying for **effective values, including defaults**:

~~~text
enabled=false
path=/orders
retries=3
~~~

The line order here is sorted by name for readability; the API does not require you to process the map in the order shown above. The Java 17+ example below will sort entries itself to produce stable output.

### Two Layers of Data to Keep in Mind

**Values written in the code that uses the annotation** and **values taken from the annotation type declaration** are not from the same source.

| Element | Declaration on Endpoint | Explicitly Written at @Endpoint on OrderApi? | Effective Value |
| --- | --- | --- | --- |
| **path()** | No default | Yes: **"/orders"** | "/orders" |
| **retries()** | **default 3** | No | 3 |
| **enabled()** | **default true** | Yes: **false** | false |

If a processor only wants to report the options that the author **deliberately wrote at the usage site**, it must inspect the explicit map. If a processor needs to build a complete configuration to generate code or check thresholds, it should inspect the map **including defaults**.

## 2. What Does AnnotationMirror Represent?

In JSR 269, **AnnotationMirror** belongs to the **javax.lang.model.element** package. It is **the model of an annotation** that the compiler sees when processing source and symbols.

For example, a processor receives a **TypeElement** representing class OrderApi, and then reads:

~~~java
for (AnnotationMirror mirror : typeElement.getAnnotationMirrors()) {
    System.out.println(mirror.getAnnotationType());
}
~~~

This is an illustrative snippet inside a processor; **typeElement** has already been obtained from the compiler model, not a variable that exists automatically in an ordinary Java program.

Related components:

- **Element**: a program declaration such as a package, class, interface, method, field, or parameter.
- **TypeElement**: a kind of Element representing a type declaration, such as class OrderApi.
- **AnnotationMirror**: an annotation attached to the declaration being processed.
- **ExecutableElement**: represents an element of an annotation type, for example the method **retries()**.
- **AnnotationValue**: the value of an element, for example **3**, **false**, or the string **"/orders"**.
- **ProcessingEnvironment**: the set of utilities for a processor, including **getElementUtils()** which returns **Elements**.
- **Elements**: a language model utility containing the **getElementValuesWithDefaults(...)** method.

**AnnotationMirror is not a runtime reflection Annotation object.** Although both relate to metadata, AnnotationMirror belongs to the compiler model, whereas things like **java.lang.Class** and **java.lang.reflect.Method** belong to the runtime reflection model.

In a processor program, you should compare annotation types via the Java model, such as **mirror.getAnnotationType()** or **TypeElement**, rather than trying to load the source class with Class.forName.

## 3. Reading Only Explicitly Specified Elements

API:

~~~java
Map<? extends ExecutableElement, ? extends AnnotationValue>
        values = mirror.getElementValues();
~~~

This map contains only **the elements whose values are explicitly written** at the annotation usage described by mirror.

Example:

~~~java
@Endpoint(path = "/orders", enabled = false)
class OrderApi {}
~~~

The map contains keys corresponding to **path()** and **enabled()**. It **does not contain retries()**, even though retries has default 3 and the effective value of retries is 3.

Iterating over the map:

~~~java
for (Map.Entry<? extends ExecutableElement,
               ? extends AnnotationValue> entry
        : mirror.getElementValues().entrySet()) {

    String elementName =
            entry.getKey().getSimpleName().toString();

    AnnotationValue value = entry.getValue();

    System.out.println(elementName + "=" + value);
}
~~~

This is illustrative code inside a processor with imports **java.util.Map**, **javax.lang.model.element.ExecutableElement**, and **AnnotationValue**. It prints values as representations of AnnotationValue; for example, a string value may be represented with quotation marks. If you need to convert to specific model objects, you must inspect **AnnotationValue.getValue()**.

**Important warning:** if the author specifies a value **equal to the default**, it is **still considered explicit**.

~~~java
@Endpoint(path = "/orders", retries = 3)
class ExplicitDefaultApi {}
~~~

For this case, **retries()** will appear in **getElementValues()**, even though the number 3 equals default 3. The API answers the question **“was it written?”**, not **“does it differ from the default?”**.

### Marker Annotations and Empty Maps

A marker annotation declares no elements:

~~~java
@interface Ready {}

@Ready
class Service {}
~~~

**AnnotationMirror.getElementValues()** for Ready is an **empty map**. This is true because the annotation has no elements, and **does not mean the annotation is absent**. First, the processor must find the **AnnotationMirror** corresponding to Ready; only then should it inspect the element map inside.

An annotation where all elements have defaults and that is used as **@SomeAnnotation** can also yield an **empty explicit map**, but **getElementValuesWithDefaults(...)** will return the default elements.

## 4. Getting All Values, Including Defaults

When you need the effective configuration, use the **Elements** utility:

~~~java
Map<? extends ExecutableElement, ? extends AnnotationValue>
        effective = processingEnv.getElementUtils()
                .getElementValuesWithDefaults(mirror);
~~~

**processingEnv** is a field provided by AbstractProcessor after the processor is initialized. The result is a map containing the explicitly specified element–value pairs and the remaining pairs taken from the defaults declared in the annotation type.

For the OrderApi example:

~~~text
path=/orders      (explicit)
enabled=false     (explicit)
retries=3         (default)
~~~

In a processor, this is a convenient way to produce a configuration with defaults applied, avoiding having to manually iterate over every element and look up the default for each name.

Do not use a check such as **containsKey("retries")** directly because this map has **ExecutableElement keys**, not String keys. If you need to query by name, iterate over the keys and use **getSimpleName()**, or convert to a custom-designed structure.

### Properly Comparing the Two Maps

| Question | API to Use |
| --- | --- |
| Which specific element=value pairs did the author write? | **mirror.getElementValues()** |
| What are the effective values of the entire annotation? | **elements.getElementValuesWithDefaults(mirror)** |
| What default does this annotation type declare for the retries element? | **ExecutableElement.getDefaultValue()** |
| Which program element is the annotation attached to? | **Element.getAnnotationMirrors()** or finding via RoundEnvironment |
| Need to read annotations while the application is running? | **reflection getAnnotation(...)** and RUNTIME retention |

**Do not modify the map returned by the API** to “attach” defaults or assume the map can be arbitrarily mutated. In real-world tools, you can copy it to a **TreeMap<String, ...>** or your program's own immutable data structure.

## 5. Reading the Default Directly on the Element Declaration

When you have an **ExecutableElement** representing a method of an annotation type:

~~~java
AnnotationValue declaredDefault =
        annotationElement.getDefaultValue();
~~~

- If the annotation element has a **default**, it returns an **AnnotationValue** representing that default value.
- If the element **has no default**, it returns **null**.
- This is information of the **element declaration in the annotation type**, not of a specific annotation usage.

Example with Endpoint:

~~~java
interface-like Endpoint {
    // Diagram, NOT Java syntax:
    path()       : no default
    retries()    : default 3
    enabled()    : default true
}
~~~

The diagram above only illustrates the role of the API, not a compilable source file; the actual Java syntax is **@interface Endpoint** in section 1.

Processor snippet to inspect defaults:

~~~java
TypeElement annotationType =
        (TypeElement) mirror.getAnnotationType().asElement();

for (Element member : annotationType.getEnclosedElements()) {
    if (member instanceof ExecutableElement element) {
        AnnotationValue defaultValue = element.getDefaultValue();

        System.out.println(element.getSimpleName() + " -> "
                + (defaultValue == null
                        ? "<required>" : defaultValue));
    }
}
~~~

Here **mirror.getAnnotationType()** returns a **DeclaredType** and **asElement()** returns the corresponding type declaration, and then the **ExecutableElement**s inside are retrieved.

**getDefaultValue()** can return **null** to indicate there is no default, whereas **getElementValuesWithDefaults(...)** does not fabricate a value for an omitted required element in an invalid annotation. When the source is missing a required element, the compiler reports an error; tools should not expect a “valid null” value to appear as a substitute.

### Default and Value Having the Same Number

Suppose the declaration has **default 3**. The following two sources have the same effective value:

~~~java
@Endpoint(path = "/a")
class A {}

@Endpoint(path = "/b", retries = 3)
class B {}
~~~

However, for **retries**:

- **A** does not have retries in the explicit map.
- **B** has retries in the explicit map.
- Both A and B have retries = 3 in the full map with defaults.

If the requirement is to **recover the author's configuration decisions**, this difference matters. If the requirement is only to **apply the configuration**, the effective values are usually sufficient.

## 6. Complete Java 17+ Example: Reading Explicit and Default Values with a Processor

The experiment below creates an **annotation processor** that reads an annotation with SOURCE retention and generates **a report class** so the main program can print the results. It lets you observe the exact difference between the two maps without relying on internal iteration order or javac's diagnostic formatting.

### Project Structure

Create four files:

~~~text
project/
├── processor/
│   └── demo/
│       └── EndpointProcessor.java
└── src/
    └── demo/
        ├── Endpoint.java
        ├── OrderApi.java
        └── Main.java
~~~

The **processor** directory contains the processor code; the **src** directory contains the annotation type and the application program. The processor does not directly reference class Endpoint when building the processor, so it can be compiled separately.

### File 1 — src/demo/Endpoint.java

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface Endpoint {
    String path();
    int retries() default 3;
    boolean enabled() default true;
}
~~~

**SOURCE retention** is chosen intentionally: the processor in javac can still analyze the annotation, but this annotation will not be retained for runtime reflection.

### File 2 — src/demo/OrderApi.java

~~~java
package demo;

@Endpoint(path = "/orders", enabled = false)
public class OrderApi {
}
~~~

Only **path** and **enabled** are written explicitly; **retries** uses default 3.

### File 3 — processor/demo/EndpointProcessor.java

~~~java
package demo;

import java.io.IOException;
import java.io.Writer;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;

import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.AnnotationMirror;
import javax.lang.model.element.AnnotationValue;
import javax.lang.model.element.Element;
import javax.lang.model.element.ExecutableElement;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("demo.Endpoint")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class EndpointProcessor extends AbstractProcessor {
    private boolean generated;

    @Override
    public boolean process(
            Set<? extends TypeElement> annotationTypes,
            RoundEnvironment round) {

        if (round.processingOver() || generated) {
            return true;
        }

        for (TypeElement annotationType : annotationTypes) {
            for (Element annotated :
                    round.getElementsAnnotatedWith(annotationType)) {

                for (AnnotationMirror mirror :
                        annotated.getAnnotationMirrors()) {

                    if (!mirror.getAnnotationType().toString()
                            .equals("demo.Endpoint")) {
                        continue;
                    }

                    String explicit = describe(
                            mirror.getElementValues());

                    String effective = describe(
                            processingEnv.getElementUtils()
                                    .getElementValuesWithDefaults(mirror));

                    try {
                        JavaFileObject file = processingEnv.getFiler()
                                .createSourceFile(
                                        "demo.generated.AnnotationReport",
                                        annotated);

                        try (Writer writer = file.openWriter()) {
                            writer.write("package demo.generated;\n");
                            writer.write(
                                    "public final class AnnotationReport {\n");
                            writer.write(
                                    "  private AnnotationReport() {}\n");
                            writer.write(
                                    "  public static final String EXPLICIT = "
                                    + javaLiteral(explicit) + ";\n");
                            writer.write(
                                    "  public static final String EFFECTIVE = "
                                    + javaLiteral(effective) + ";\n");
                            writer.write("}\n");
                        }

                        generated = true;
                    } catch (IOException ex) {
                        processingEnv.getMessager().printMessage(
                                Diagnostic.Kind.ERROR,
                                "Unable to generate report: "
                                        + ex.getMessage(),
                                annotated);
                    }

                    return true;
                }
            }
        }

        return true;
    }

    private static String describe(
            Map<? extends ExecutableElement,
                ? extends AnnotationValue> values) {

        Map<String, String> sorted = new TreeMap<>();

        for (Map.Entry<? extends ExecutableElement,
                       ? extends AnnotationValue> entry
                : values.entrySet()) {

            String name = entry.getKey()
                    .getSimpleName().toString();

            Object rawValue = entry.getValue().getValue();
            sorted.put(name, String.valueOf(rawValue));
        }

        return sorted.toString();
    }

    private static String javaLiteral(String text) {
        return "\"" + text
                .replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\r", "\\r")
                .replace("\n", "\\n") + "\"";
    }
}
~~~

**Explanation of the processor steps:**

1. The processor is declared to support the **demo.Endpoint** annotation with **@SupportedAnnotationTypes**.
2. **RoundEnvironment.getElementsAnnotatedWith(annotationType)** retrieves the declarations annotated with Endpoint in the processing round. The code has only one target, OrderApi.
3. **annotated.getAnnotationMirrors()** retrieves the AnnotationMirrors present on the declaration. The processor selects the mirror of type **demo.Endpoint**.
4. **mirror.getElementValues()** contains the explicit values: **enabled=false** and **path=/orders**.
5. **processingEnv.getElementUtils().getElementValuesWithDefaults(mirror)** additionally includes **retries=3**.
6. **describe(...)** uses a **TreeMap** to sort keys by name, so the output does not depend on the map order returned by the compiler.
7. **AnnotationValue.getValue()** in this example only returns simple types (**String**, **Boolean**, **Integer**), so **String.valueOf(...)** is sufficient to represent them as intended. In a general-purpose processor, for class literals, enums, nested annotations, or arrays, you must handle the specific Java language model forms and must not assume getValue() is always a primitive/String.
8. **Filer.createSourceFile(...)** creates the **demo.generated.AnnotationReport** source file, containing the two string constants EXPLICIT and EFFECTIVE for Main to print. **javaLiteral(...)** escapes the characters needed for a Java string literal in the illustrative values.
9. The **generated** field and the **processingOver()** condition help avoid repeatedly generating the same source across multiple processing rounds.
10. **return true** declares that the processor has handled (*claim*) the annotation types it supports. It does not mean the processor automatically runs the Main application.

The example intentionally assumes **only one class is annotated with Endpoint** in the compilation run. In a real project, handle multiple annotated elements and generate a unique file name for each class, or create a consolidated report after examining all inputs. You need to design processing round management and duplicate file error handling accordingly.

### File 4 — src/demo/Main.java

~~~java
package demo;

import demo.generated.AnnotationReport;

public class Main {
    public static void main(String[] args) {
        System.out.println("explicit="
                + AnnotationReport.EXPLICIT);
        System.out.println("effective="
                + AnnotationReport.EFFECTIVE);

        boolean visibleAtRuntime =
                OrderApi.class.getAnnotation(Endpoint.class) != null;

        System.out.println("runtimePresent="
                + visibleAtRuntime);
    }
}
~~~

**Main** uses the class generated by the processor. The **getAnnotation(Endpoint.class)** line will return null because Endpoint has SOURCE retention; this is a secondary check to show that the compiler model and runtime reflection are two different mechanisms.

### Compiling and Running

From the **project** directory:

~~~bash
mkdir -p processor-out generated-src out
~~~

On Windows PowerShell, you can create the directories with:

~~~powershell
New-Item -ItemType Directory -Force processor-out,generated-src,out | Out-Null
~~~

**Phase 1: compile the processor.**

~~~bash
javac --release 17 -proc:none -d processor-out processor/demo/EndpointProcessor.java
~~~

**Phase 2: compile the source files and invoke the processor explicitly.**

~~~bash
javac --release 17 -processorpath processor-out -processor demo.EndpointProcessor -s generated-src -d out src/demo/Endpoint.java src/demo/OrderApi.java src/demo/Main.java
~~~

**Phase 3: run the application.**

~~~bash
java -cp out demo.Main
~~~

**Stdout of the java command:**

~~~text
explicit={enabled=false, path=/orders}
effective={enabled=false, path=/orders, retries=3}
runtimePresent=false
~~~

The Java compiler additionally generates the source file:

~~~text
generated-src/demo/generated/AnnotationReport.java
~~~

With semantically equivalent content:

~~~java
package demo.generated;
public final class AnnotationReport {
  private AnnotationReport() {}
  public static final String EXPLICIT =
      "{enabled=false, path=/orders}";
  public static final String EFFECTIVE =
      "{enabled=false, path=/orders, retries=3}";
}
~~~

**Note:** Compilation commands may print diagnostics if the tool or environment has special configurations. The stdout listing above describes **the java command running Main**, excluding javac messages. The generated-src directory contains source files generated by the processor; class files are placed in **out** by javac.

### Experiment: Changing How the Annotation Is Written

Change **OrderApi.java** from:

~~~java
@Endpoint(path = "/orders", enabled = false)
~~~

to:

~~~java
@Endpoint(path = "/orders", enabled = false, retries = 3)
~~~

Because **retries = 3** is now written explicitly, the **EXPLICIT** report includes **retries=3**, while **EFFECTIVE** remains the same. If you rerun the experiment, you should clean up the old generated files or create new output directories to avoid a **FilerException** or mixing up stale binaries.

## 7. Why Not Use Element.getAnnotation Directly to Distinguish Explicit/Default?

Alongside AnnotationMirror, the compiler model provides utilities in the form of annotation proxies:

~~~java
Endpoint endpoint =
        annotated.getAnnotation(Endpoint.class);

if (endpoint != null) {
    int retries = endpoint.retries();
}
~~~

In a compiled processor that can reference the Endpoint type, **Element.getAnnotation(Endpoint.class)** can return an object providing the effective values of the annotation, similar to calling element methods on an annotation object.

However, it is **not the preferred API for retrieving the list of explicitly written elements**. If **retries()** returns 3, you cannot conclude whether the author typed **retries=3** or not: 3 could come from the default.

Therefore:

- **To find out which elements were explicitly specified:** use **AnnotationMirror.getElementValues()**.
- **To get the full map including defaults:** use **Elements.getElementValuesWithDefaults(...)**.
- **To conveniently call element methods with a known annotation type:** you can use **Element.getAnnotation(...)** when appropriate, but you must understand the limitations on data types and reading individual elements.

**An important issue with class-valued annotation elements:** on the proxies provided by the compiler model, calling an element that returns **Class** or **Class[]** can throw **MirroredTypeException** or **MirroredTypesException**, because the source class has not been loaded yet. When you need to analyze class literal values at compile time, using **AnnotationMirror/AnnotationValue** and **TypeMirror** is generally more robust.

Do not try to fix that error by loading a non-existent class with **Class.forName(...)** in the processor. Annotation processing is designed to work with symbols and types in the compiler model.

## 8. What Forms Does AnnotationValue.getValue() Return?

**AnnotationValue** is not simply a runtime object for each element. It is a value in the language model; depending on the element type, **getValue()** returns the appropriate model types.

| Annotation Element Type | Value Form in AnnotationValue.getValue() |
| --- | --- |
| Primitive such as **int**, **boolean**, **long** | Boxed value, for example Integer, Boolean, Long |
| **String** | String |
| **Class<?>** or class literal | **TypeMirror**, not necessarily java.lang.Class |
| Enum | **VariableElement** for the enum constant |
| Nested annotation | **AnnotationMirror** |
| One-dimensional array of valid types | **List<? extends AnnotationValue>** |

In the processor example, simple types are converted to String using **String.valueOf(...)**. Do not use that approach as a general solution for all nested structures.

When writing a general-purpose processor, Java provides **AnnotationValueVisitor** and utility classes such as **SimpleAnnotationValueVisitor9**. A visitor lets you branch cleanly by value type:

~~~java
AnnotationValue value = /* value retrieved from the map */;

value.accept(new javax.lang.model.util.SimpleAnnotationValueVisitor9<Void, Void>() {
    @Override
    public Void visitString(String text, Void unused) {
        System.out.println("String value: " + text);
        return null;
    }

    @Override
    public Void visitType(
            javax.lang.model.type.TypeMirror type,
            Void unused) {
        System.out.println("Class literal type: " + type);
        return null;
    }
}, null);
~~~

This is **an illustrative code snippet inside a processor**, not a standalone runnable file. Using a visitor ensures you properly handle the data types that an annotation processor receives at compile time.

### Default Values Are Also AnnotationValues

Both **ExecutableElement.getDefaultValue()** and the **getElementValuesWithDefaults(...)** map work with **AnnotationValue**. Because of this, the same value traversal/interpretation mechanism can be used for both explicit data and default data.

However, the default **is not necessarily copied into the metadata at the usage site**. When the author omits retries, seeing retries=3 in **getElementValuesWithDefaults(...)** does not prove that the source code of OrderApi contains the string **retries=3**.

## 9. Reading Annotations on Declarations and Type Uses at the Right Location

Both **Element** and **TypeMirror** in the language model can carry annotations, but at different locations:

- **Annotations attached to a declaration** of a class/method/field: typically inspect **Element.getAnnotationMirrors()** of that declaration.
- **Annotations attached to a type use (TYPE_USE)**: you may need to inspect **TypeMirror.getAnnotationMirrors()** at the appropriate type position.
- **Annotations on a type parameter declaration**: you may need to inspect **TypeParameterElement** in the generic parameter list of the corresponding type/method.

Example:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.TYPE_USE)
@interface Checked {}

class Box<T> {
    java.util.List<@Checked T> items;
}
~~~

Here **@Checked** is attached to **the type argument position T** in **List<T>**, not declared directly on class Box. A processor that only calls **BoxTypeElement.getAnnotationMirrors()** will not automatically get an AnnotationMirror representing the @Checked annotation deep inside the type of field items. You need to traverse the field's type structure using the appropriate compiler model APIs.

Once you have the right **AnnotationMirror** at the location to process, the rules for **getElementValues()** and **getElementValuesWithDefaults(...)** remain the same.

## 10. Differences Between the Compiler Model and Runtime Reflection

The two stages can view the same annotation concept, yet through different APIs.

| Purpose | Compile-time annotation processing | Runtime reflection |
| --- | --- | --- |
| Annotation representation | **AnnotationMirror** | Object implementing the **Annotation** interface |
| Class representation | **TypeElement** and **TypeMirror** | **Class<?>** |
| Explicit values | **AnnotationMirror.getElementValues()** | Standard reflection API does not provide a separate map of explicit syntax |
| Values with defaults | **Elements.getElementValuesWithDefaults(...)** | Directly calling the annotation element method (effective value) |
| Default declared on the type | **ExecutableElement.getDefaultValue()** | **Method.getDefaultValue()** |
| Retention SOURCE | Processor can read it during source compilation | Not visible via reflection after compilation |
| Retention RUNTIME | Processor can read it while processing source | Can access the annotation at runtime |

For example:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@interface Flags {
    boolean active() default true;
}

@Flags
class Client {}
~~~

At runtime:

~~~java
Flags f = Client.class.getAnnotation(Flags.class);
System.out.println(f.active()); // true
~~~

The result **true** does not reveal whether the author wrote **active=true** or omitted it: reflection reads the effective value. If you want to check **explicit versus default at compile time**, AnnotationMirror is the appropriate model.

**One thing to note when reading older binaries:** The default value of an annotation element resides on the annotation type definition and can change across library versions. Therefore, the map with defaults reflects the type declaration that the tool currently sees; it should not be treated as proof that the author entered that value in the source.

## 11. Common Mistakes

| Mistake | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| Assuming getElementValues() always returns all elements | The API contains only explicit elements | Use getElementValuesWithDefaults to get the complete map |
| Seeing retries=3 and concluding the author declared retries=3 | The value may be a default | Compare the explicit map and the full map |
| Only comparing the value to the default to decide whether it is explicit | An explicit value can equal the default | Check whether the element is present in getElementValues() |
| Using **Map<String,Object>** directly with getElementValues() | The API's key/value types are ExecutableElement and AnnotationValue | Iterate/copy and convert deliberately |
| Thinking getDefaultValue() reads the value of an annotation usage | It reads the default of the **element declaration** | Use AnnotationMirror's map to read the usage site |
| Assuming getDefaultValue() returning null means the annotation is absent | Null only means the element declares no default | Distinguish between the annotation type, the element, and the usage site |
| Trying to cast a Class value to Class<?> in a processor | The compiler model represents class literals using TypeMirror | Handle TypeMirror or AnnotationValueVisitor |
| Using reflection to distinguish explicit/default syntax from an annotation object | Reflection provides effective values | Read the source model with an annotation processor if you need to distinguish them |
| Looking for a TYPE_USE annotation deep inside generics via the class's getAnnotationMirrors() | The annotation is attached to a type position, not the class declaration | Traverse the TypeMirror at the right position |
| Expecting a processor to run without configuring javac | Annotations do not invoke processors automatically | Specify -processor/-processorpath or configure the build tool |
| Relying on the map order returned by the compiler | The ordering can introduce presentation/tool dependencies | Sort by name when producing stable reports |
| Re-creating the same source file across multiple rounds | Filer does not allow creating the same path repeatedly within a processing run | Track state and handle rounds properly |
| Reading a SOURCE-retained annotation with Class.getAnnotation at runtime | SOURCE is not retained for reflection | Distinguish compile-time processing from runtime reflection |

## 12. Practical Workflow for a Processor Needing Configuration Values

A clear verification sequence:

1. **Obtain the right Element** from **RoundEnvironment.getElementsAnnotatedWith(annotationType)** or via compiler model traversal.
2. **Find the AnnotationMirror of the right type** in **getAnnotationMirrors()** of the relevant Element/TypeMirror.
3. **Get the explicit map** via **mirror.getElementValues()** if you need to know which elements the author deliberately passed.
4. **Get the full map** via **elements.getElementValuesWithDefaults(mirror)** if you need to produce the effective configuration.
5. **Analyze AnnotationValue according to its type**, using getValue()/visitor for class literals, enums, arrays, and nested annotations.
6. **Validate required elements and data types** against the declaration; the compiler handles language rules, while the processor can enforce additional business constraints.
7. **Report diagnostics properly** through **Messager**, or generate source/resource files through **Filer**, without making assumptions about traversal order or the number of rounds.
8. **Write compile-time tests** covering all three cases: omitting an element with a default, passing a value different from the default, and explicitly passing a value equal to the default.

How you choose the API depends on your goal: **“Did the author specify it?”** and **“What is the effective value?”** are two independent questions. Do not use the explicit-only map for a task requiring the full configuration, and do not use the map with defaults to infer backwards what syntax was typed.

## 13. Self-Check Exercises

**Exercise 1.** Given:

~~~java
@interface Cache {
    int ttl() default 60;
    String region() default "global";
}

@Cache
class CacheA {}

@Cache(ttl = 60)
class CacheB {}

@Cache(ttl = 120, region = "eu")
class CacheC {}
~~~

How will the explicit map and the map with defaults differ?

| Class | getElementValues() | getElementValuesWithDefaults(...) |
| --- | --- | --- |
| **CacheA** | Empty | ttl=60; region="global" |
| **CacheB** | ttl=60 | ttl=60; region="global" |
| **CacheC** | ttl=120; region="eu" | ttl=120; region="eu" |

**Key answer:** CacheA and CacheB have the same effective **ttl** value, but differ in whether the author entered **ttl=60** or not. CacheA's empty explicit map **does not mean @Cache is absent**.

**Exercise 2.** When **retries()** has **default 3**, what does **ExecutableElement.getDefaultValue()** return? It returns an **AnnotationValue** representing the number 3. If **path()** has no default, this method returns **null**.

**Exercise 3.** An element has type **Class<?> target()** and is used as **target = String.class**. In a processor, what does AnnotationValue.getValue() represent the value with? A **TypeMirror** describing the String type, not a **java.lang.Class** object like at runtime.

**Exercise 4.** If a processor reads an annotation with SOURCE retention, can reflection be used after the program runs to look up that annotation again? **No**, not with standard reflection APIs; SOURCE annotations are not retained in the class file.

**Exercise 5.** If the author writes **@Endpoint(path = "/orders", retries = 3)** while retries has default 3, does the explicit map contain retries? **Yes**. Being equal to the default does not eliminate explicitness.

**Exercise 6.** Why does the example use TreeMap? To present keys by name in a stable manner, independent of the iteration order of entries in the compiler model map or the author reordering element=value pairs.

## 14. Official Java Documentation

- **Java SE 17 — AnnotationMirror:** https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/AnnotationMirror.html — **getElementValues()** contains only explicit element-values.
- **Java SE 17 — Elements:** https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/util/Elements.html#getElementValuesWithDefaults(javax.lang.model.element.AnnotationMirror) — **getElementValuesWithDefaults(...)** adds defaults.
- **Java SE 17 — ExecutableElement:** https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/ExecutableElement.html#getDefaultValue() — queries the default of an annotation element.
- **Java SE 17 — AnnotationValue:** https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/AnnotationValue.html — value forms, getValue(), and visitor.
- **Java SE 17 — javax.annotation.processing:** https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/package-summary.html — processor API, rounds, and processing environment.
- **Java Language Specification §9.6.2 — Defaults for Annotation Interface Elements:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.2 — language-level meaning of defaults.

**Remember:** **getElementValues()** reflects **what was explicitly specified**; **getElementValuesWithDefaults(...)** reflects **the values after defaults are applied**; and **getDefaultValue()** reflects **the default value declared on the annotation type element itself**. Using the right API helps an annotation processor both preserve the source author's intent and produce an effective configuration compliant with Java.
