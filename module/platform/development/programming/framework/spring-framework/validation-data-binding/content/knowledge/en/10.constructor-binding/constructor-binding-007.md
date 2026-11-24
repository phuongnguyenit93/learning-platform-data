# DataBinder.NameResolver and Custom Parameter Names in Constructor Binding

## 1. The Problem: Request Names and Java Parameter Names Do Not Always Match

When Spring receives data for an object, names sent from the outside often do not match Java naming conventions. For example, a form or URL has the key **first-name**, while the Java constructor declares the parameter **firstName**:

~~~text
Form/query data: first-name=Lan&age=29

public Account(String firstName, Integer age)
                      ↑                ↑
              "first-name"          "age"
             needs mapping      matches directly
~~~

If it only looks up **firstName**, the binder cannot find the value under key **first-name**. **DataBinder.NameResolver** solves this exact problem in **constructor binding**: it decides **which input key name** DataBinder uses to look up the value for *a constructor parameter*. The key phrase to remember is **name mapping at lookup time**, not renaming Java variables or modifying the request itself.

Lesson context: the **Constructor Binding** section of **Spring Framework – validation-data-binding**. Since Spring Framework **6.1**, DataBinder supports **NameResolver** and **ValueResolver** for constructor binding. In Spring MVC, the common declarative approach is the **@BindParam** annotation; when another annotation or naming rule is needed, you can provide a custom **DataBinder.NameResolver**.

Learning outcomes:

- Know where constructor binding takes place and which step **NameResolver** participates in.
- Use **@BindParam** to map an external parameter name differing from the constructor parameter name.
- Know how to write a **DataBinder.NameResolver** for custom rules/annotations and understand fallback behavior.
- Distinguish **NameResolver**, **ValueResolver**, type conversion, and Bean Validation.
- Recognize limitations, common mistakes, and safety requirements when binding HTTP data.

## 2. Constructor Binding and the Path of a Value

**DataBinder** supports two related data-binding modes:

1. **Constructor binding**: creates a new object via a constructor, looks up each parameter, converts types if needed, and passes the arguments to the constructor.
2. **Property binding**: after an object exists, assigns properties via setters or configured property access mechanisms.

**DataBinder.NameResolver** belongs to **the first mode**. It is not a global setting that renames all fields during the property binding step.

Conceptual diagram of constructor binding:

~~~text
Input names/values (e.g., "first-name"="Lan", "age"="29")
          |
          v
DataBinder prepares to construct Account
          |
          v
Inspect each constructor MethodParameter
          |
          +--> NameResolver.resolveName(parameter)
          |      |
          |      +--> "first-name" for firstName
          |      +--> null if no custom name decided
          |
          +--> Fallback: Java parameter name (if discoverable)
          |
          v
ValueResolver.resolveValue(lookupName, expectedType)
          |
          v
Convert type if needed, e.g., "29" -> Integer 29
          |
          v
new Account("Lan", 29)
          |
          v
DataBinder.getTarget() and BindingResult
~~~

This is a logical order for learning, not a guarantee that Spring calls each method strictly once in all scenarios (especially with nested objects, collections, and binding failures). If the target was not constructed successfully, **getTarget()** may still be **null**, and **BindingResult** must be checked.

### Roles Not to Confuse

| Component | Receives | Decides | Not responsible for |
| --- | --- | --- | --- |
| **DataBinder.NameResolver** | Constructor **MethodParameter** | Lookup key name; may return **null** | Does not fetch raw values, convert types, or validate |
| **DataBinder.ValueResolver** | Lookup key name and parameter type | Raw value for that name; provides available key set | Does not decide Java parameter aliases |
| **ConversionService** and editors/formatters | Input value and target type | How to convert types when needed | Does not assign parameter name aliases |
| **Constructor** | Prepared Java arguments | Initializes object state | Does not read HTTP requests directly |
| **Validator / @Valid** | Object or arguments per validation mechanism | Checks declared constraints | Does not rewrite key names or raw values |

Normally, Java constructor parameter **firstName** is looked up under the name **firstName**. Discovering Java parameter names relies on available metadata, typically compiler metadata emitted with **-parameters**. When an explicit alias is provided via a resolver, that parameter can be looked up by its alias even when the Java name and external name differ.

## 3. API Contract of DataBinder.NameResolver

This interface resides inside **org.springframework.validation.DataBinder**:

~~~java
public interface NameResolver {
    String resolveName(org.springframework.core.MethodParameter parameter);
}
~~~

The snippet above is a **simplified signature for explanation**, not Spring's full source code.

An implementation returns:

- A non-**null** **String**, such as **"first-name"**: Spring uses that name to look up the value for the parameter in question.
- **null**: the resolver does not specify a custom name; DataBinder falls back to its default parameter name discovery (such as **DefaultParameterNameDiscoverer**) when possible.
- Do not return an empty string to represent "no alias", because **""** is still a name, not a fallback signal under the interface contract.

Related APIs:

~~~java
binder.setNameResolver(customResolver);
DataBinder.NameResolver configured = binder.getNameResolver();
binder.construct(valueResolver);
~~~

These are illustrative calls on an already-created **DataBinder** with an appropriate **targetType**. **setNameResolver(...)** configures how names are chosen; **construct(...)** actually performs constructor binding. **getNameResolver()** can be null when not yet configured.

**NameResolver is only used to choose names for constructor parameters** during **construct(ValueResolver)**. It does not make **binder.bind(MutablePropertyValues)** automatically understand old/new setter names, does not rename properties inside the class, and does not define a JSON response contract.

## 4. Simplest Approach in Spring MVC: @BindParam

When a constructor parameter needs an input name different from the Java name, Spring MVC supports the annotation:

~~~java
import org.springframework.web.bind.annotation.BindParam;

public final class CreateAccount {
    private final String firstName;
    private final Integer age;

    public CreateAccount(
            @BindParam("first-name") String firstName,
            Integer age) {
        this.firstName = firstName;
        this.age = age;
    }

    public String getFirstName() {
        return firstName;
    }

    public Integer getAge() {
        return age;
    }
}
~~~

With a controller declaring a model attribute:

~~~java
@PostMapping("/accounts")
public String create(
        @Valid @ModelAttribute("account") CreateAccount account,
        BindingResult errors) {
    if (errors.hasErrors()) {
        return "account-form";
    }
    return "account-saved";
}
~~~

**These are two illustrative snippets to place in a Spring MVC application**, requiring appropriate imports, controller, views, and validation provider; they do not form a standalone app. The form sends **first-name=Lan&age=29**. When Spring invokes **CreateAccount(String firstName, Integer age)**, **@BindParam("first-name")** directs the binder to look up key **first-name** to supply **firstName**. Parameter **age** continues using the normal name **age**.

Distinctions to keep straight:

- **@BindParam** is designed for **constructor binding** of a model attribute, not as a general way to rename every property.
- **@BindParam** can be placed on the **constructor parameter** or corresponding field where Spring supports it; placing it directly on the constructor parameter usually states intent most clearly.
- **@ModelAttribute("account")** only sets the model attribute name to **account**. It does **not** rename constructor argument **firstName** to **first-name**.
- **@RequestParam("first-name") String firstName** is a different mechanism: a name for a *handler method parameter*, not constructor mapping inside a model attribute.
- **@RequestBody** JSON is typically deserialized by Jackson's **HttpMessageConverter**; **@BindParam** and **DataBinder.NameResolver** do not replace **@JsonProperty** for renaming JSON fields when Jackson constructs objects.
- **@Valid** triggers constraint checks in supported contexts after/alongside binding; it does not resolve aliases itself.

**Note on using DataBinder directly:** Core **DataBinder** does not automatically assume it should read **@BindParam** in every manual instantiation. To use this annotation when calling **construct(...)** yourself, configure **setNameResolver(new BindParamNameResolver())**. In the **Spring MVC @ModelAttribute** flow, Spring provides **@BindParam** support via web binding configuration.

## 5. When Custom Names Beyond @BindParam Are Needed

A system might have to accept input names following another convention, such as **customer_name**, **display-name**, or names fixed by an external protocol. If you do not want to annotate every field with **@BindParam**, you can create your own annotation and a resolver that reads it.

Example:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
public @interface ExternalName {
    String value();
}
~~~

And constructor:

~~~java
public Account(@ExternalName("customer_name") String name,
               Integer age) {
    this.name = name;
    this.age = age;
}
~~~

The two snippets above are **excerpts only**; the complete runnable file with imports and class declarations is in section 6.

A **NameResolver** can read the parameter annotation:

~~~java
DataBinder.NameResolver resolver = parameter -> {
    ExternalName annotation =
            parameter.getParameterAnnotation(ExternalName.class);
    return (annotation != null ? annotation.value() : null);
};
~~~

When parameter **name** carries **@ExternalName("customer_name")**, the resolver returns **"customer_name"**. For **age** without the annotation, the resolver returns **null**, letting DataBinder look up **age** from constructor metadata.

You can combine a custom resolver with **BindParamNameResolver** so **@BindParam** remains supported:

~~~java
BindParamNameResolver builtIn = new BindParamNameResolver();

DataBinder.NameResolver combined = parameter -> {
    ExternalName external =
            parameter.getParameterAnnotation(ExternalName.class);

    if (external != null) {
        return external.value();
    }
    return builtIn.resolveName(parameter);
};
~~~

This illustrates a precedence rule: **@ExternalName** is tried first, then **@BindParam**, and finally if the result is null, Spring discovers the Java name. Precedence is an application decision, not a feature that auto-configures arbitrary annotations.

## 6. Complete Java 17+ Example: Default, @BindParam, and Custom NameResolver

The Maven example below **does not require running a web server**. It explicitly creates a **DataBinder** with an initial **null** target, declares the target type, supplies raw values via **ValueResolver**, and calls **construct(...)**. Three cases show exactly which name is used for lookup.

Uses Java 17+ and **Spring Framework 6.2.6** modules at the same version. Reproducing the example requires Maven and dependency download access on the first build.

File structure:

~~~text
constructor-name-resolver/
├── pom.xml
└── src/main/java/demo/ConstructorNameResolverDemo.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>constructor-name-resolver</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.6</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-web</artifactId>
            <version>6.2.6</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <parameters>true</parameters>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
                <configuration>
                    <mainClass>demo.ConstructorNameResolverDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/ConstructorNameResolverDemo.java**:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Map;
import java.util.Set;

import org.springframework.core.ResolvableType;
import org.springframework.core.convert.support.DefaultConversionService;
import org.springframework.validation.DataBinder;
import org.springframework.web.bind.annotation.BindParam;
import org.springframework.web.bind.support.BindParamNameResolver;

public final class ConstructorNameResolverDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.PARAMETER)
    public @interface ExternalName {
        String value();
    }

    // Java parameter names match the input key names.
    public static final class DefaultPerson {
        private final String firstName;
        private final Integer age;

        public DefaultPerson(String firstName, Integer age) {
            this.firstName = firstName;
            this.age = age;
        }

        public String firstName() { return firstName; }
        public Integer age() { return age; }
    }

    // One parameter uses an alias provided by @BindParam.
    public static final class AliasedPerson {
        private final String firstName;
        private final Integer age;

        public AliasedPerson(
                @BindParam("given-name") String firstName,
                Integer age) {
            this.firstName = firstName;
            this.age = age;
        }

        public String firstName() { return firstName; }
        public Integer age() { return age; }
    }

    // One parameter uses an application-declared annotation.
    public static final class CustomPerson {
        private final String firstName;
        private final Integer age;

        public CustomPerson(
                @ExternalName("display_name") String firstName,
                Integer age) {
            this.firstName = firstName;
            this.age = age;
        }

        public String firstName() { return firstName; }
        public Integer age() { return age; }
    }

    private static <T> T create(
            Class<T> type,
            Map<String, String> rawInput,
            DataBinder.NameResolver nameResolver) {

        DataBinder binder = new DataBinder(null, "person");
        binder.setTargetType(ResolvableType.forClass(type));
        binder.setConversionService(new DefaultConversionService());

        if (nameResolver != null) {
            binder.setNameResolver(nameResolver);
        }

        binder.construct(new DataBinder.ValueResolver() {
            @Override
            public Object resolveValue(String name, Class<?> targetType) {
                // This is raw data. DataBinder is responsible for type conversion.
                return rawInput.get(name);
            }

            @Override
            public Set<String> getNames() {
                return rawInput.keySet();
            }
        });

        if (binder.getBindingResult().hasErrors()) {
            throw new IllegalStateException(
                    binder.getBindingResult().toString());
        }

        return type.cast(binder.getTarget());
    }

    public static void main(String[] args) {
        DefaultPerson first = create(
                DefaultPerson.class,
                Map.of("firstName", "Mai", "age", "23"),
                null);
        System.out.println("DEFAULT -> "
                + first.firstName() + " / " + first.age());

        AliasedPerson second = create(
                AliasedPerson.class,
                Map.of("given-name", "Lan", "age", "29"),
                new BindParamNameResolver());
        System.out.println("BIND_PARAM -> "
                + second.firstName() + " / " + second.age());

        DataBinder.NameResolver custom = parameter -> {
            ExternalName annotation =
                    parameter.getParameterAnnotation(ExternalName.class);
            return (annotation != null ? annotation.value() : null);
        };

        CustomPerson third = create(
                CustomPerson.class,
                Map.of("display_name", "An", "age", "31"),
                custom);
        System.out.println("CUSTOM -> "
                + third.firstName() + " / " + third.age());
    }
}
~~~

In the directory containing **pom.xml**, run:

~~~bash
mvn -q compile exec:java
~~~

Standard output of the program (excluding Maven messages, if any):

~~~text
DEFAULT -> Mai / 23
BIND_PARAM -> Lan / 29
CUSTOM -> An / 31
~~~

### Output Analysis

**DEFAULT:** **DefaultPerson**'s constructor has parameters **firstName** and **age**, matching the two keys of **rawInput**. **nameResolver = null**, so DataBinder looks up by Java parameter names. Maven's **parameters=true** configuration ensures parameter name metadata is included in bytecode. The string **"23"** is converted to **Integer 23** before invoking the constructor.

**BIND_PARAM:** **AliasedPerson** declares **@BindParam("given-name")** on the **firstName** parameter. Because this is a manually executed **DataBinder**, the example sets **new BindParamNameResolver()** via **setNameResolver(...)**. External key **given-name** is found; parameter **age** has no alias and falls back to **age**. Result is **Lan / 29**.

**CUSTOM:** the resolver reads **@ExternalName("display_name")** on parameter **firstName** and returns **display_name**. For **age**, it returns **null** so Spring uses the Java name **age**. Value **"31"** is converted to **Integer 31**, and the object is successfully created.

Note: **ValueResolver**'s **getNames()** returns the provided key set; it is also useful for complex constructor binding with nested objects and collections. The example's **resolveValue(...)** intentionally only fetches values from the map without parsing Integer itself: the goal is to let DataBinder handle the conversion step.

If **"31"** is replaced with **"bad"**, resolving the right name **age** still does not make the string a valid integer. Check **BindingResult** to detect conversion errors. Keep "key not found" distinct from "key's value cannot be converted".

## 7. Integrating a Resolver into Spring MVC's WebDataBinder

In a Spring MVC application, **@InitBinder** configures a **WebDataBinder** used for controller model attributes. Example illustrating how to register a resolver when the app uses **@ExternalName**:

~~~java
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.support.BindParamNameResolver;

@ControllerAdvice
public class AccountBinderAdvice {
    private final BindParamNameResolver builtIn =
            new BindParamNameResolver();

    @InitBinder("account")
    public void setup(WebDataBinder binder) {
        binder.setNameResolver(parameter -> {
            ExternalName alias =
                    parameter.getParameterAnnotation(ExternalName.class);
            return (alias != null
                    ? alias.value()
                    : builtIn.resolveName(parameter));
        });

        binder.setDeclarativeBinding(true);
    }
}
~~~

This is an **integration configuration snippet**, requiring the application's **ExternalName** declaration/import and matching controller/model attribute classes. **@InitBinder("account")** scopes the configuration to the **model attribute name account**, not a constructor parameter name. The resolver supports the custom annotation first, then **@BindParam**, and finally Java names via fallback.

**setDeclarativeBinding(true)** is a *separate* binding-scope decision: constructor binding remains permitted, while property binding runs only when **allowedFields** is configured appropriately. It is not a mandatory requirement of **setNameResolver**, but useful in designs that only permit binding declared fields.

Consider the scope of **@ControllerAdvice** and verify that the attribute name matches reality. If a resolver is only needed for one controller or DTO, local configuration is often easier to manage than an application-wide change.

### When Not to Use NameResolver

| Situation | More suitable API | Reason |
| --- | --- | --- |
| Model attribute constructor needs an alias differing from Java name | **@BindParam** or **DataBinder.NameResolver** | Maps names when looking up constructor arguments |
| Handler wants parameter **?first-name=...** directly | **@RequestParam("first-name")** | Names a handler method argument rather than creating a DTO |
| JSON **@RequestBody** has key **first_name** | **@JsonProperty("first_name")** or Jackson config | Jackson reads JSON instead of DataBinder constructor mapping |
| Property binding needs to write into **userName** | Appropriate DTO/setter or contract-aligned preprocessing | **NameResolver** does not rename keys for **bind(PropertyValues)** |
| String **"29"** needs conversion to **Integer** | **ConversionService**, converter/formatter | Converts the *value*, does not rename the key |
| Age value must be >= 18 | **@Min(18)** and appropriate validation | Checks value after a valid type is produced |
| Endpoint must stop clients from modifying internal fields | Narrow constructor/DTO; **allowedFields** when using property binding | Aliasing is not an authorization mechanism |

## 8. Edge Cases and Common Errors

### 8.1. Both Original Name and Alias Present in Input

For example, the client sends both **firstName=Mai** and **given-name=Lan**, while the constructor uses **@BindParam("given-name")**. Do not implicitly assume Spring compares or merges both values to detect conflicts. With the setup in section 6, the resolver instructs looking up **given-name** for parameter **firstName**. An API should clearly specify which name is valid, whether legacy names are accepted, and how to respond if both appear.

### 8.2. Alias Missing

If the resolver returns **display_name** while the source only contains **firstName**, there is no "fuzzy name guessing." **ValueResolver** may return **null** because the key is absent. The resulting constructor argument or error depends on the parameter type, constraints, default rules, and binding configuration. For a reference **String** parameter, the constructor may receive **null**. If the field is required, enforce it with validation and DTO contracts; do not assume NameResolver ensures non-missing fields.

### 8.3. Resolver Returns Null for All Parameters

This does *not* mean all parameters disappear; DataBinder tries discovering Java parameter names as usual. For Java, compile with **-parameters** to avoid relying on guesswork or metadata-less bytecode. If names cannot be found and no fallback info exists, binding may fail or fail to receive proper data.

### 8.4. Inconsistent Alias Rules

Aliases like **display_name**, **display-name**, and **displayName** can be three distinct keys. Writing a resolver that automatically "replaces every separator" can cause name collisions (two different fields resolving to the same name) or silent API contract shifts. For important schemas, prefer explicit annotations and test for duplicate or conflicting aliases.

### 8.5. Names for Nested Objects and Collections

Constructor binding supports nested objects, **List**, **Map**, arrays, and keys like **addresses[0].city**, **accounts[KEY].name** in Spring-supported contexts. Constructor parameter aliases can affect the root name used to look up nested path strings. Do not manually concatenate prefixes or assume every child field follows one rule, especially when custom resolvers use names containing dots, brackets, or special characters.

### 8.6. Successful Binding Does Not Mean Valid Data

The resolver only picks names; **ConversionService** converts types; **Bean Validation** and the business layer check constraints. When a form sends **age=abc** for constructor parameter **Integer age**, conversion errors should surface through **BindingResult** or the corresponding MVC error path. If the form sends **age=12**, conversion succeeds yet can still violate **@Min(18)**. Do not arbitrarily replace syntax errors with business errors.

### 8.7. Letting Clients Dictate Arbitrary Aliases and Reflection

Never use **NameResolver** to take arbitrary instructions from requests and look up arbitrary property/class names. Resolvers should rely on fixed rules, approved schemas, or code-controlled annotations. Untrusted input still requires restricting accepted fields, collection sizes, and passing data through validators. Use dedicated web DTOs rather than binding directly to domain entities containing sensitive fields.

## 9. What Should Tests Cover?

| Test case | Submitted data | Key expectation |
| --- | --- | --- |
| Default | firstName=Mai, age=23 | Constructs DTO from Java names; age becomes Integer |
| Alias via @BindParam | given-name=Lan, age=29 | firstName comes from given-name |
| Alias via custom annotation | display_name=An, age=31 | firstName comes from display_name |
| Null fallback | age=31, resolver ignores age annotation | age still resolves by Java name |
| Wrong alias | firstName=Mai when display_name is expected | Does not automatically look up firstName instead of alias |
| Type mismatch | age=bad | Conversion error; matching name alone is not enough |
| Missing required field | neither firstName nor alias present | Missing/null policy and validation are verified |
| Both old name and alias present | firstName=Mai, given-name=Lan | Contract decides which name takes precedence |
| Property binding after constructor | extra property outside expected DTO | Alias must not expand data modification privileges |
| JSON @RequestBody | {"first_name":"Lan"} | Tested via Jackson; does not go through NameResolver by default |

In Spring MVC, use **MockMvc** to verify real request names, **@ModelAttribute** creation, **BindingResult**, and constraint errors. With plain DataBinder as in section 6, verify the constructor receives the right arguments, **getTarget()** holds the object, **getBindingResult().hasErrors()** matches expectations, and ValueResolver receives the expected lookup names.

## 10. Practice Exercises

1. **Add a second alias:** update **AliasedPerson**'s constructor to use **@BindParam("given_name")** instead of **given-name**. Update the input map accordingly and predict stdout.
2. **Test fallback:** remove **@ExternalName** from **CustomPerson**'s **firstName** parameter, change the map key from **display_name** to **firstName**, and keep the same resolver. Why does it still work when Maven enables **parameters=true**?
3. **Combine annotations:** write a resolver checking **@ExternalName** first and then **BindParamNameResolver**. Test a constructor with one parameter annotated with **@ExternalName**, another with **@BindParam**, and one plain parameter.
4. **Distinguish conversion:** change valid age from **"31"** to **"abc"** and inspect **BindingResult**. Was the name resolved properly, and at which step did the error occur?
5. **API design:** a service must accept **first_name** from a partner system while using **firstName** in the Java DTO. Choose between **@BindParam** on the constructor or a custom resolver. State criteria for choosing, how to test aliases, and how to report errors consistently.

## 11. Official Documentation

- [Spring Framework — Constructor Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html): DataBinder initialization sequence, targetType, construct, and customizing parameter names.
- [Spring MVC — @ModelAttribute](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): **@BindParam** examples and NameResolver explanation.
- [Spring Framework 6.2.6 — DataBinder.NameResolver](https://www.springframework.org/spring/docs/6.2.6/javadoc-api/org/springframework/validation/DataBinder.NameResolver.html): **resolveName(MethodParameter)** signature and fallback.
- [Spring Framework 6.2.6 — DataBinder.ValueResolver](https://www.springframework.org/spring/docs/6.2.6/javadoc-api/org/springframework/validation/DataBinder.ValueResolver.html): **resolveValue(...)** and **getNames()**.
- [Spring Framework 6.2.6 — DataBinder](https://www.springframework.org/spring/docs/6.2.6/javadoc-api/org/springframework/validation/DataBinder.html): **setNameResolver**, **setTargetType**, **construct**, and **getBindingResult**.
- [Spring MVC — Data Binding Model Design](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html): DTOs, constructor binding, and controlling property binding.

**Principle to remember:** **NameResolver** only answers *"for this constructor parameter, under which name should data be looked up?"*. **ValueResolver** answers *"what value does that name have?"*; Spring converts types and invokes the constructor; validation evaluates data afterward per configuration. Use **@BindParam** for simple aliases and a custom resolver when custom rules or annotations are required, while keeping the input contract and binding scope clear.