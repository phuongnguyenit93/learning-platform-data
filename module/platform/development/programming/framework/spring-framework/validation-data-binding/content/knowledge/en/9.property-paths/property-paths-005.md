# Nested Paths Traversing Null Objects in Spring Data Binding

A nested property path such as **student.address.city** describes how to navigate from a root object to a target property: retrieve **student**, retrieve the student's **address**, then set **city**. What happens if **student == null** or **student.getAddress() == null** at binding time?

In Spring Framework **property binding**, the outcome depends primarily on **autoGrowNestedPaths**. A standard **DataBinder** enables this mechanism by default: when possible, Spring instantiates a **null** intermediate object, attaches it back into the object graph, and continues. When disabled or when an object cannot be instantiated, the path cannot be traversed normally; depending on the API and invalid-field policy, the application either encounters an error or ignores the field.

Key point: **auto-creating a child object to assign a property does not mean the data is validated or accepted by business logic**. Furthermore, this mechanism applies to **property/field binding**; it must not be assumed identical to Jackson JSON deserialization or **constructor binding**.

## 1. Understanding a nested property path accurately

Consider three JavaBean classes:

~~~java
public class EnrollmentForm {
    private Student student;      // initially null
    public Student getStudent() { return student; }
    public void setStudent(Student student) { this.student = student; }
}

public class Student {
    private Address address;      // initially null
    public Address getAddress() { return address; }
    public void setAddress(Address address) { this.address = address; }
}

public class Address {
    private String city;          // initially null
    public String getCity() { return city; }
    public void setCity(String city) { this.city = city; }
}
~~~

This is **structural illustration code**: in real Java source files, place public top-level classes in separate files or use nested static classes. Section 4 provides a standalone program that compiles cleanly.

The path **student.address.city** has these links:

~~~text
EnrollmentForm (root object exists)
      |
      +-- student = null
                |
                +-- address = ?      (cannot read yet while student is null)
                        |
                        +-- city = ? (cannot assign yet)
~~~

You cannot call **form.getStudent().getAddress().setCity("Hanoi")** in plain Java when **getStudent()** returns **null**: Java throws a **NullPointerException**. Spring **BeanWrapper** does not blindly chain setter calls; it inspects the path and, when configured, can auto-create intermediate objects.

For example, when receiving **student.address.city=Hanoi**:

1. Spring locates property **student** on **EnrollmentForm**.
2. If **student == null** and nested path auto-growth is enabled, Spring creates a default **Student** and assigns it through the corresponding property.
3. Spring locates **address** on **Student**; if **null**, it creates a default **Address** and assigns it back.
4. Spring converts the input value if needed, then calls the **city** setter.
5. The root object now has **student != null**, **address != null**, **city = "Hanoi"**.

This mechanism is called **auto-grow nested paths**. Auto-creation only happens when traversal must cross a **null** link; if no input requests navigating to **student.address.city**, there is no reason to expect Spring to eagerly instantiate the whole object tree.

**Distinguishing a null intermediate node from a null leaf:** in **student.address.city**, **student** and **address** are intermediate nodes that must exist to continue; **city** is the target leaf value and can certainly be assigned **null** when the property contract permits. A null leaf by itself is not a "cannot traverse nested path" error.

## 2. APIs and default values to remember

| API or configuration | Meaning | Important default |
| --- | --- | --- |
| **DataBinder.setAutoGrowNestedPaths(boolean)** | Enables or prevents auto-creating intermediate objects when binding by property path | **true** on a standard DataBinder |
| **DataBinder.isAutoGrowNestedPaths()** | Reads the enabled/disabled state | **true** on a newly created binder |
| **BeanWrapperImpl.setAutoGrowNestedPaths(boolean)** | Similar option on the low-level accessor | **false** on a directly instantiated BeanWrapperImpl |
| **DataBinder.setAutoGrowCollectionLimit(int)** | Caps auto-added elements for arrays/collections | **256** on a standard DataBinder |
| **DataBinder.setIgnoreInvalidFields(boolean)** | Chooses to ignore input fields whose path has a declared property that is currently unreachable, e.g., a null intermediate node | **false** |
| **DataBinder.setIgnoreUnknownFields(boolean)** | Chooses to ignore field names that do not exist on the target type | **true** |
| **DataBinder.setAllowedFields(String...)** | Restricts which properties may be bound | Unrestricted unless configured |

**Two defaults that are easily confused:** **DataBinder** defaults to **autoGrowNestedPaths = true**, whereas a directly constructed **BeanWrapperImpl** defaults to **false**. Therefore two seemingly similar snippets handle null differently:

~~~java
DataBinder binder = new DataBinder(form, "enrollmentForm");
// binder.isAutoGrowNestedPaths() -> true

BeanWrapperImpl wrapper = new BeanWrapperImpl(form);
// wrapper.isAutoGrowNestedPaths() -> false
~~~

The **form** variable and the **DataBinder** and **BeanWrapperImpl** imports above are supplied by the application. When using a standalone **BeanWrapper**, you can explicitly enable it via **wrapper.setAutoGrowNestedPaths(true)** before accessing paths.

**Configuration timing also matters.** With **DataBinder**, call **setAutoGrowNestedPaths(false)** or **setAutoGrowCollectionLimit(...)** **before** the binder initializes its accessor/BindingResult. For instance, calling **binder.getBindingResult()** and then trying to change auto-grow settings can trigger **IllegalStateException** because the binder is already initialized. Configure right after **new DataBinder(...)**, before **bind(...)** or operations that force binder initialization.

## 3. Conditions for auto-grow to work

Setting the flag to **true** does not turn Spring into a dependency-injection container for arbitrary nested objects. To auto-grow a **null** value, Spring must know the property type, instantiate a suitable default value, and attach it back into the object graph.

For a regular JavaBean, practical requirements include:

- The root object already exists for property binding, e.g., **new EnrollmentForm()**.
- Intermediate properties are exposed via matching getters/setters in bean-property access (or via fields when supported direct-field access is enabled).
- The intermediate type is concrete enough to instantiate; typically a class with an accessible no-arg constructor. Pure interfaces, abstract classes, or types with only parameterized constructors usually cannot be auto-created by default.
- After instantiation, the accessor must have a way to attach the new value to the parent property; a missing setter, unavailable setter, type mismatch, or exception thrown inside a getter/setter can cause failure.
- If the path traverses a **List**, array, or **Map**, Spring also needs element/key/value type information and an expandable structure. Collection limits apply separately.

Do not state "Spring will auto-create **every** null object." A more accurate phrasing is: **Spring attempts to instantiate a default value at a null link if auto-grow is enabled and the target type can be instantiated and attached**.

A common case that does not work:

~~~java
public class Form {
    private Location location;
    public Location getLocation() { return location; }
    public void setLocation(Location location) { this.location = location; }
}

public interface Location {
    String getCity();
    void setCity(String city);
}
~~~

This is an explanatory example only. If **location == null** and the declared type **Location** is an interface, Spring cannot invoke **new Location()** with a default constructor. To bind **location.city**, provide a concrete instance beforehand, design a different DTO, or use an appropriate initialization/constructor-binding approach. **A String Converter does not resolve the inability to instantiate an interface intermediate object.**

Also be careful with **records** or immutable objects with **final** fields and no setters: those models fit **constructor binding** better; do not assume property binding auto-grow can mutate them like mutable JavaBeans.

## 4. Complete example: same path, three handling approaches

The following program uses **Java 17+** and **Spring Framework 6.2.10**, without needing Spring Boot or a web server. It demonstrates:

1. Default **DataBinder** auto-creating **Student** and **Address** when they are null.
2. Directly created **BeanWrapperImpl** without auto-grow throwing **NullValueInNestedPathException** when crossing **student == null**.
3. **DataBinder** with auto-grow disabled still binding successfully when the application **pre-initializes** all intermediate objects.

Create two files:

~~~text
nested-null-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── NestedNullDemo.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>nested-null-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.10</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/NestedNullDemo.java**:

~~~java
package demo;

import java.util.Map;

import org.springframework.beans.BeanWrapperImpl;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.beans.NullValueInNestedPathException;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

public final class NestedNullDemo {

    public static void main(String[] args) {
        // Case 1: Two intermediate nodes have not been initialized.
        EnrollmentForm form = new EnrollmentForm();
        System.out.println("beforeStudentNull=" + (form.getStudent() == null));

        DataBinder binder = new DataBinder(form, "enrollmentForm");
        System.out.println("binderAutoGrow=" + binder.isAutoGrowNestedPaths());

        // Allow only the two fields used in this scenario.
        binder.setAllowedFields(
                "student.address.city",
                "student.address.zipCode");

        binder.bind(new MutablePropertyValues(Map.of(
                "student.address.city", "Hanoi",
                "student.address.zipCode", "100000"
        )));

        BindingResult result = binder.getBindingResult();

        System.out.println("bindErrors=" + result.hasErrors());
        System.out.println("studentCreated=" + (form.getStudent() != null));
        System.out.println("addressCreated="
                + (form.getStudent().getAddress() != null));
        System.out.println("city="
                + form.getStudent().getAddress().getCity());
        System.out.println("zipCode="
                + form.getStudent().getAddress().getZipCode());

        // Case 2: Standalone BeanWrapperImpl defaults to auto-grow OFF.
        BeanWrapperImpl plain = new BeanWrapperImpl(new EnrollmentForm());
        System.out.println("plainWrapperAutoGrow="
                + plain.isAutoGrowNestedPaths());
        try {
            plain.setPropertyValue("student.address.city", "Hue");
            System.out.println("unexpectedSuccess");
        } catch (NullValueInNestedPathException exception) {
            System.out.println("plainFailure="
                    + exception.getClass().getSimpleName());
        }

        // Case 3: Disable auto-grow, but pre-initialize parent nodes explicitly.
        EnrollmentForm prebuilt = new EnrollmentForm();
        Student student = new Student();
        student.setAddress(new Address());
        prebuilt.setStudent(student);

        DataBinder manual = new DataBinder(prebuilt, "enrollmentForm");
        manual.setAutoGrowNestedPaths(false);
        manual.setAllowedFields("student.address.city");
        manual.bind(new MutablePropertyValues(Map.of(
                "student.address.city", "Da Nang"
        )));

        System.out.println("manualAutoGrow=" + manual.isAutoGrowNestedPaths());
        System.out.println("manualErrors="
                + manual.getBindingResult().hasErrors());
        System.out.println("manualCity="
                + prebuilt.getStudent().getAddress().getCity());
    }

    public static class EnrollmentForm {
        private Student student;

        public EnrollmentForm() {
        }

        public Student getStudent() {
            return student;
        }

        public void setStudent(Student student) {
            this.student = student;
        }
    }

    public static class Student {
        private Address address;

        public Student() {
        }

        public Address getAddress() {
            return address;
        }

        public void setAddress(Address address) {
            this.address = address;
        }
    }

    public static class Address {
        private String city;
        private String zipCode;

        public Address() {
        }

        public String getCity() {
            return city;
        }

        public void setCity(String city) {
            this.city = city;
        }

        public String getZipCode() {
            return zipCode;
        }

        public void setZipCode(String zipCode) {
            this.zipCode = zipCode;
        }
    }
}
~~~

Inside **nested-null-demo**, use JDK 17 or newer and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.NestedNullDemo
~~~

**Lines printed by the program**, excluding build tool logs:

~~~text
beforeStudentNull=true
binderAutoGrow=true
bindErrors=false
studentCreated=true
addressCreated=true
city=Hanoi
zipCode=100000
plainWrapperAutoGrow=false
plainFailure=NullValueInNestedPathException
manualAutoGrow=false
manualErrors=false
manualCity=Da Nang
~~~

Explanation of each case:

- **Case 1:** there is no **new Student()** or **new Address()** in application code before binding. Traversing **student.address.city** caused DataBinder to instantiate and attach them because **autoGrowNestedPaths** is enabled by default. Both String fields are assigned cleanly, so **BindingResult.hasErrors()** returns **false**.
- **Case 2:** uses a fresh **BeanWrapperImpl** without configuring auto-grow. With the same path, traversal stops at **student == null**; the example catches **NullValueInNestedPathException**. This is a null-path error, not a **NullPointerException** thrown from learner setter calls.
- **Case 3:** **autoGrowNestedPaths(false)** only stops Spring from auto-creating null nodes; it does not forbid accessing nested properties that already exist. Because **prebuilt.student.address** was pre-initialized, the binder still assigns **city** with no errors.

**Case 2 demonstrates direct BeanWrapperImpl behavior, not a claim that every DataBinder error is wrapped into a FieldError.** For an unreachable path, the low-level API can throw **NullValueInNestedPathException**; in the binding pipeline, distinguish property access exceptions from conversion errors aggregated in **BindingResult**.

## 5. When disabling auto-grow on DataBinder

There are two design options, depending on form requirements:

**Auto-expand paths (default):**

~~~java
EnrollmentForm target = new EnrollmentForm();
DataBinder binder = new DataBinder(target, "enrollmentForm");
// autoGrowNestedPaths defaults to true
binder.bind(new MutablePropertyValues(
        Map.of("student.address.city", "Hanoi")));
~~~

**Disable auto-expand and prepare the object graph explicitly:**

~~~java
EnrollmentForm target = new EnrollmentForm();
Student student = new Student();
student.setAddress(new Address());
target.setStudent(student);

DataBinder binder = new DataBinder(target, "enrollmentForm");
binder.setAutoGrowNestedPaths(false);
binder.bind(new MutablePropertyValues(
        Map.of("student.address.city", "Hanoi")));
~~~

These are **two illustrative snippets** using the classes and imports from section 4. Call **setAutoGrowNestedPaths(false)** before the binder initializes.

If auto-grow is disabled while **student == null** and **student.address.city** is submitted, the path is unreachable. By default **setIgnoreInvalidFields(false)**; do not rely on assuming **bind(...)** will silently skip the field or always return a **BindingResult** with a type error. With low-level **BeanWrapper**, this case clearly leads to **NullValueInNestedPathException**.

There is also the option:

~~~java
binder.setIgnoreInvalidFields(true);
~~~

It tells the binder to **skip fields whose property path is unreachable**, including when an intermediate node is null. This is **not** a way to auto-create objects, nor a way to fix bad data. If the application silently skips **student.address.city**, user-submitted values are not written to the target. Therefore do not enable this option just to make requests "error-free"; verify that business requirements truly permit skipping the field.

### Invalid field vs. unknown field

Two cases that are easily mixed up:

| Case | Example | Problem | Relevant settings |
| --- | --- | --- | --- |
| **Path exists but cannot be traversed** | **student.address.city**, when **student == null** and auto-grow is off | Intermediate node is unreachable | **autoGrowNestedPaths**, **ignoreInvalidFields** |
| **Property name does not exist** | **student.address.planetName** when Address has no such property | Target field/property not found | **ignoreUnknownFields** |
| **Value cannot be converted to target type** | **student.age = "abc"**, where age is **Integer** | Type conversion failed | **ConversionService**, binding error |
| **Field blocked by allowedFields** | Sending **student.role** when binder only allows **student.address.city** | Binding allow policy | **setAllowedFields(...)**, **getSuppressedFields()** |

Default **ignoreUnknownFields = true** does not imply **ignoreInvalidFields = true**. And a field blocked by **allowedFields** is not a "null intermediate object" error. Look at the exact root cause when diagnosing.

## 6. Nulls at different levels and non-atomicity of binding

A request can send multiple paths together:

~~~text
student.address.city=Hanoi
student.address.zipCode=100000
student.fullName=Lan
~~~

When the system binds properties sequentially, traversing **student** creates the instance once and reuses it. Once **address** has been created for **city**, **zipCode** is written onto that same object. Final state should be checked on the **object tree**, not merely by checking whether a single setter ran.

However, **DataBinder.bind(...) is not a database transaction**. For example, the binder might assign **student.address.city** successfully and then fail converting **student.age = "abc"** to **Integer**. Already-assigned properties can remain on the object while **BindingResult** records an error on the failed field. Do not assume that a single error causes Spring to roll back all prior mutations.

A safe processing flow is:

1. Bind onto a dedicated **request DTO** with an allowed property surface.
2. Inspect **BindingResult** and stop before invoking the service if binding errors remain.
3. Run Bean Validation or a suitable Spring Validator to check required values, lengths, and cross-field rules.
4. Only map valid data into domain commands/entities and execute business logic inside an appropriate transaction.

**If the form omits every field under student**, auto-grow does not guarantee student will be created. Conversely, **if it auto-creates an empty Student/Address from a single field**, the object's existence does not prove required inner fields have values. This is especially important with **@Valid**, **@NotNull**, and **@NotBlank**.

## 7. Collections, arrays, maps: null and nested indices

Spring supports paths containing indices/keys such as:

~~~text
students[0].address.city
students[2].address.city
settings[timezone].value
~~~

Here you can encounter multiple kinds of "empty": the collection is **null**; the collection exists but lacks an element at that index; the element at the index is **null**; or the element's **address** is **null**.

When auto-grow is enabled, Spring can create the collection/array or intermediate elements based on resolved type metadata. For a **List<Student>** with a clear generic element type and a default-instantiable **Student** class, **students[0].address.city** can create all needed nodes. For unresolved types, immutable collections, special implementations, or non-instantiable elements, the operation can still fail.

**Default limit:** **DataBinder.setAutoGrowCollectionLimit(...)** defaults to **256**. This helps prevent malicious inputs like **students[1000000].name** from allocating huge collections. You can lower it per business rules:

~~~java
DataBinder binder = new DataBinder(form, "form");
binder.setAutoGrowCollectionLimit(20); // set before binder initialization
~~~

This limit applies to **auto-growing arrays/collections**; it is not a path-depth limit, an HTTP body byte limit, or business validation of item count. Also enforce max input sizes, allowed field patterns, and proper validation.

**Do not assume Map behaves identically to List:** index **[2]** is a positional index for lists/arrays; **[KEY]** is a map key. Map implementations, key/value types, and default-value creation rules can produce different behavior. When building forms with collections/maps, test the exact declared property type.

## 8. Integration with Spring MVC and @ModelAttribute

With an HTTP form sending parameters:

~~~text
POST /enrollments
Content-Type: application/x-www-form-urlencoded

student.address.city=Hanoi&student.address.zipCode=100000
~~~

When a handler uses **@ModelAttribute**, MVC creates/retrieves the model attribute and performs binding accordingly. In the **property binding** branch backed by JavaBeans, **WebDataBinder** uses settings similar to **DataBinder**, including auto-grow nested paths.

An illustrative controller in an existing MVC application:

~~~java
@Controller
class EnrollmentController {

    @InitBinder("enrollmentForm")
    void configure(WebDataBinder binder) {
        // Restrict the data surface clients are allowed to modify.
        binder.setAllowedFields(
                "student.address.city",
                "student.address.zipCode");
        binder.setAutoGrowCollectionLimit(20);
        // autoGrowNestedPaths defaults to true on DataBinder.
    }

    @PostMapping("/enrollments")
    String enroll(
            @ModelAttribute("enrollmentForm") EnrollmentForm form,
            BindingResult result) {
        if (result.hasErrors()) {
            return "enrollment-form";
        }

        // Verify all required conditions thoroughly before processing.
        return "redirect:/enrollments";
    }
}
~~~

This is an **illustrative integration snippet**, requiring imports for **org.springframework.stereotype.Controller**, **org.springframework.web.bind.annotation.InitBinder**, **ModelAttribute**, **PostMapping**, **org.springframework.web.bind.WebDataBinder**, **org.springframework.validation.BindingResult**, and the project's **EnrollmentForm**. To run in a real app, add Spring MVC dependencies, the **enrollment-form** view, validation handling, and the corresponding service.

If a real application **does not want auto-grow**, it can set **binder.setAutoGrowNestedPaths(false)** when configuring the binder, provided all accessible nested objects are pre-created by the application or supplied by another initialization mechanism. Do not flip the default blindly just because fields look null; design the form's null semantics first.

### Other paths must not be conflated

- **@ModelAttribute / form property binding:** this lesson's behavior occurs while the binder traverses **student.address.city**.
- **Constructor binding (Spring Framework 6.1+):** **DataBinder.construct(...)** can recursively build objects and nested constructor arguments. **setAutoGrowNestedPaths(...)** targets setter/field binding and does not control constructor binding. A **record** DTO typically calls for constructor initialization rather than setter auto-grow.
- **@RequestBody JSON:** an **HttpMessageConverter** such as Jackson deserializes the object graph from JSON; **DataBinder.autoGrowNestedPaths** is not a global switch controlling how Jackson creates child objects. JSON with **{"student":null}** and JSON with **{"student":{"address":{"city":"Hanoi"}}}** are completely different inputs.
- **Bean Validation (@Valid/@Validated):** validation reads/checks existing objects. Cascade validation on nested properties needs **@Valid** and suitable constraints; enabling **@Valid** does not make Spring DataBinder instantiate null objects.

When one endpoint binds successfully and another does not, inspect the **input format, @ModelAttribute/@RequestBody, DTO type, property vs. constructor binding, and binder configuration** before changing code.

## 9. Input constraints, validation, and security

Auto-grow is a technical convenience: client-supplied field names can cause an object graph to be constructed. This is handy for complex forms, yet can cause unwanted side effects if binding directly onto domain entities.

For example, suppose an entity has:

~~~text
account.owner.role
account.billing.limit
account.profile.displayName
~~~

If clients can bind any public property on the entity, they might try changing **owner.role** or **billing.limit**, and auto-grow could instantiate intermediate objects to reach sensitive fields if types allow. Therefore:

- **Prefer a dedicated request DTO** declaring only values clients are authorized to send.
- When using property binding, configure an explicit **allowedFields** list; check **BindingResult.getSuppressedFields()** to observe rejected fields.
- Avoid binding **@ModelAttribute** directly onto JPA entities containing lazy-loaded relationships, owners, roles, or sensitive state just to save mapping a DTO. Traversing getters and instantiating objects in a persistence model can trigger side effects and unintended graph mutations.
- Set appropriate limits on collection growth and request size. Ensure validation runs after binding, especially for fields auto-grown into empty objects.
- **Do not use ignoreInvalidFields(true) to hide errors** if the application actually requires every submitted value to be captured.

A DTO can declare:

~~~java
class EnrollmentRequest {
    @jakarta.validation.Valid
    @jakarta.validation.constraints.NotNull
    private StudentRequest student;
    // getters/setters...
}

class StudentRequest {
    @jakarta.validation.Valid
    @jakarta.validation.constraints.NotNull
    private AddressRequest address;
    // getters/setters...
}

class AddressRequest {
    @jakarta.validation.constraints.NotBlank
    private String city;
    // getters/setters...
}
~~~

This is an **annotation/field illustration snippet**, not a standalone program. Place **@NotNull** on intermediate objects when they cannot be omitted, **@Valid** to cascade into child objects when present, and **@NotBlank** on required strings. Remember: **@Valid** alone does not reject **null**, and auto-grow can instantiate objects whose inner properties remain null. Validation requires a provider (such as Hibernate Validator) and must be triggered in the request pipeline.

## 10. Diagnosing null-path errors

| Symptom | Likely cause | How to check/fix |
| --- | --- | --- |
| **NullValueInNestedPathException** | An intermediate node is null; auto-grow is off or cannot instantiate a default object | Check flag state, property type, constructor, setter, getter, and exact path |
| No error reported, yet child object stays null | Field not sent, suppressed, ignored by config, or flow does not use property binding | Check request field names, **getSuppressedFields()**, **ignoreInvalidFields**, binding mode |
| **NotWritablePropertyException** or introspection error | Wrong field name, missing setter, or property incompatible with access mode | Verify JavaBean getters/setters/fields and exact spelling |
| **typeMismatch** | Path is reachable, yet value cannot convert to target property type | Check **BindingResult.getFieldErrors()**, converters/formatters, rejected value |
| Unexpected collection growth or index error | Oversized indexed path sent, unsuitable collection structure or element type | Cap collection limit, check generic types and input size |
| Previous value remains on target despite bind error | Property binding does not roll back the entire target | Use a dedicated DTO, inspect all errors before calling services |
| JSON behaves differently from form | Jackson deserialization is not the BeanWrapper property binding path | Distinguish **@RequestBody** and **@ModelAttribute** |

**How to pinpoint the exact null:** for **student.address.city**, check **form**, **form.getStudent()**, **form.getStudent().getAddress()**, and then writability of **city** in order. Do not merely log "city=null" at the end because it cannot distinguish missing valid input from a missing intermediate object or broken setter.

When an exception occurs, inspect the **propertyName/path** reported by Spring and the root **cause**, especially when Spring tried to instantiate an object and found no suitable constructor. Not every nested null error is a **NullPointerException**; Spring has **BeansException/InvalidPropertyException** subclasses describing property access failures.

## 11. Exercises and test scenarios

Tests that verify more than just an HTTP 200 from a controller:

| Test case | Setup | Input | Expected result |
| --- | --- | --- | --- |
| Auto-grow enabled | **student=null** | **student.address.city=Hanoi** | Creates **Student**, **Address**, and assigns **city** |
| Auto-grow disabled, parent node null | **student=null** | **student.address.city=Hanoi** | Does not auto-create parent; handles error/invalid field per API and config |
| Auto-grow disabled, parent pre-built | **student.address=new Address()** | **student.address.city=Hanoi** | Binds successfully |
| Uncreatable intermediate node | **student** or **address** is an interface/non-instantiable type | Nested path must cross it | Not treated as successful bind; observe expected exception |
| Null leaf value | **student.address** exists, **city=null** | Assign **city** value | Assignable if accessor/setter permits |
| Two nested fields sharing a parent | **student=null** | **student.address.city** and **student.address.zipCode** | Both share the newly created **Address** object |
| Non-existent field name | DTO has no **student.planet** | Send that field | Distinguish ignoreUnknownFields from null errors |
| Disallowed field | allowedFields allows only **student.address.city** | Also send **student.role** | Role is not bound; inspect suppressed fields |
| Large collection index | Empty list, low limit | **students[100000].name** | Prevents unbounded growth |
| Missing required fields | No nested fields in request | Empty form | Check Bean Validation; do not assume auto-grow creates objects |

A Spring MVC integration test should cover at least one **@ModelAttribute** form and one **@RequestBody** JSON request, since these two data paths use different object-creation mechanisms. To prove **autoGrowNestedPaths** takes effect, use a mutable JavaBean whose nested property is **null** right before binding; testing on a pre-initialized object graph will not distinguish enabled from disabled.

## 12. Practical rules

When facing **"nested path through a null object"**, answer in order:

1. Is the path accessed via **DataBinder/BeanWrapper property binding**, constructor binding, or JSON deserialization?
2. Which node is **null**: root object, intermediate object, collection element, or leaf?
3. Is **autoGrowNestedPaths** enabled on the accessor actually being used? On standard **DataBinder it is true**, on standalone **BeanWrapperImpl it is false**.
4. Can the null node's type be instantiated and attached back to the target? If not, initialize explicitly or adjust the DTO/constructor binding.
5. Is the input allowed to bind to that property, was it ignored/suppressed, and were errors thoroughly checked?
6. After binding finishes, were validation and business checks executed before updating real state?

Reasoning through these steps separates object-graph structure issues, type conversion errors, validation errors, and business rules; it also prevents relying on the wrong default between **DataBinder** and **BeanWrapperImpl**.

## Official documentation

- [Spring Framework 6.2 — Data Binding, property binding, and nested paths](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beans-beans.html)
- [Spring Framework — DataBinder Javadoc: autoGrowNestedPaths, ignoreInvalidFields, collection limit](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework — BeanWrapperImpl API](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/beans/BeanWrapperImpl.html)
- [Spring Framework — NullValueInNestedPathException API](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/beans/NullValueInNestedPathException.html)
- [Spring MVC — @InitBinder and securing model data binding](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html)
