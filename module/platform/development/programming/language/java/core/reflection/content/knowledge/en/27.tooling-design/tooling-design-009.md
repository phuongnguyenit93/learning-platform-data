# JavaBeans Introspector and How It Differs from Direct Field Scanning

## 1. Why do Java tools need to distinguish properties from fields?

`Field` represents an actual storage variable; a **JavaBeans property** represents a logical contract discovered primarily from getters/setters. `getSummary()` can expose a computed property without a `summary` field, while `internalCache` can be a real field with no property. Using `getDeclaredFields()` to simulate JavaBeans will corrupt the schema.

Unlike the article on **choosing a field/property/accessor strategy**, this article dives into JDK `java.beans.Introspector`, `BeanInfo`, and `PropertyDescriptor`: `getX`/`isX`/`setX` rules, inheritance, custom `BeanInfo`, read/write methods, and access limits. In named modules, `java.beans` belongs to the `java.desktop` module; modular code requires the appropriate `requires` relationship.

## 2. How are JavaBeans properties inferred?

Basic patterns:

| Public method | Recognized property | Role |
| --- | --- | --- |
| **String getName()** | **name** | Getter of property **name** |
| **void setName(String value)** | **name** | Setter of property **name** |
| **boolean isActive()** | **active** | Boolean getter in **isX** form |
| **int getCount()** | **count** | Getter with primitive type |
| **String getSummary()** | **summary** | Read-only property if no matching setter exists |
| **void setPassword(String value)** | **password** | Write-only property if no matching getter exists |
| **String name()** | Not automatically recognized as property **name** under traditional JavaBeans getter conventions | Normal method; commonly seen in records |
| **public String raw;** | Not automatically recognized as property **raw** solely from having a field | Public field is not a getter/setter |

A property can be:
- **Read-write**: compatible getter and setter.
- **Read-only**: has a getter but lacks a setter.
- **Write-only**: has a setter but lacks a getter.
- **Computed/derived**: getter computes value from other data, needing no field of the same name.
- **Inherited**: public getter or setter inherited from a superclass.

Familiar conventions are a parameterless getter returning a value, and a single-parameter setter returning **void** under the JavaBeans convention. For **isX()** getters, a **primitive boolean** return type is the safe rule; do not assume every tool accepts **Boolean** or non-standard signatures identically. With complex getter/setter overloads, the inferred property type may differ from expectations; inspect the actual **PropertyDescriptor** result.

Property names follow **Introspector.decapitalize** rules:
- **getName()** → **name**.
- **getURL()** → **URL**, because the first two characters of "URL" are uppercase.
- **getEMail()** → **EMail**, not always **eMail**.
- **getX()** → **x**.

Naming methods according to convention is essential when writing beans so other libraries can discover them consistently.

## 3. Core APIs: Introspector, BeanInfo, PropertyDescriptor

### 3.1. Retrieving JavaBeans information

Simple usage:

~~~java
BeanInfo info = Introspector.getBeanInfo(Person.class);
PropertyDescriptor[] properties = info.getPropertyDescriptors();
~~~

The two statements above are an **illustrative snippet**, requiring imports for **java.beans.BeanInfo**, **java.beans.Introspector**, **java.beans.PropertyDescriptor**, and an actual **Person** class.

Key components:

| API | Responsibility |
| --- | --- |
| **Introspector.getBeanInfo(Class<?>)** | Discovers BeanInfo of the class and its inheritance hierarchy per JavaBeans mechanism |
| **Introspector.getBeanInfo(Class<?>, Class<?> stopClass)** | Excludes info from **stopClass** and its superclasses |
| **Introspector.getBeanInfo(Class<?>, Class<?> stopClass, int flags)** | Adds options to use/ignore explicitly provided BeanInfo classes |
| **BeanInfo.getPropertyDescriptors()** | List of property descriptors |
| **PropertyDescriptor.getName()** | Logical property name |
| **PropertyDescriptor.getPropertyType()** | Type of ordinary property |
| **PropertyDescriptor.getReadMethod()** | Getter **Method**, may be **null** |
| **PropertyDescriptor.getWriteMethod()** | Setter **Method**, may be **null** |
| **BeanInfo.getMethodDescriptors()** | Method metadata related to the JavaBean |
| **BeanInfo.getEventSetDescriptors()** | Event metadata per JavaBeans event convention |

**getBeanInfo(Person.class)** often includes property **class**, because public **Object.getClass()** looks like a getter. When a tool only needs business properties, use:

~~~java
BeanInfo info = Introspector.getBeanInfo(
        Person.class,
        Object.class,
        Introspector.IGNORE_ALL_BEANINFO);
~~~

**Object.class** is the stop point: properties/methods/events belonging to `Object` and classes above it are excluded from the result. The **IGNORE_ALL_BEANINFO** flag tells `Introspector` to ignore any explicit `BeanInfo` present on the class or superclasses; this makes learning getter/setter conventions more predictable. In production tools, you **should not ignore explicit BeanInfo by default** if the product intends to honor metadata configuration supplied by bean authors.

**JavaBeans is public API-level metadata.** Obtaining descriptors does not automatically grant permission to invoke private methods or access private fields.

### 3.2. Explicit BeanInfo classes and caching

Beyond method-name inference, JavaBeans lets authors supply explicit **BeanInfo** metadata, typically a class named **FooBeanInfo** alongside **Foo**. This metadata can adjust which properties are exposed to tools. Consequently, introspection output is not necessarily just the result of mechanical getter/setter naming rules.

**Introspector** maintains a cache to reduce re-analysis overhead. APIs **flushFromCaches(Class<?>)** or **flushCaches()** serve cases where cached data must be intentionally cleared. Do not flush the whole cache on every inspection; use the JDK's cache normally and avoid running introspection too frequently on hot paths.

## 4. How does direct field scanning with Reflection differ?

For class **Person**, Reflection provides these API families:

| Reflection API | Returns | Rules |
| --- | --- | --- |
| **getDeclaredFields()** | Fields declared directly on the class, including private | Does not automatically add fields inherited from superclasses |
| **getFields()** | Accessible **public** fields per inheritance rules | Does not list all private fields |
| **getDeclaredField("name")** | One directly declared field with exact name | Throws **NoSuchFieldException** if absent |
| **Field.getType()** | Raw runtime type of the field | For generics, **getGenericType()** may be needed |
| **Field.get(obj)** | Field value when access is permitted | Does not call JavaBeans getter |
| **Field.set(obj, value)** | Attempts to assign field per Reflection rules and access | Does not invoke bean setter/business validation |

Therefore:

- A field **private String internalCode** appears in **getDeclaredFields()**, yet is not necessarily a JavaBeans property.
- A method **getSummary()** computing a string from other data can create property **summary**, even if the class has no **summary** field.
- Field **public String raw** appears in a Reflection field scan, yet will not automatically create a JavaBeans property **raw** without a matching accessor.
- Property **id** from a superclass getter can appear via `Introspector`, whereas the subclass's **getDeclaredFields()** does not contain field **id**.
- Both APIs require explicit sorting if fixed reports are desired; never assume returned field order is guaranteed source order.

**Do not equate metadata visibility with usage permission:** **getDeclaredFields()** can describe private fields, yet calling **Field.get** or **Field.set** remains subject to access checks and Java module encapsulation. **setAccessible(true)** can be rejected; it is not the default way to build a JavaBeans inspector tool.

## 5. Runnable Java 17+ example: same class, two views

Save the following code to **BeanVsFieldDemo.java**. This is a standalone program using JDK APIs without external libraries.

~~~java
import java.beans.BeanInfo;
import java.beans.Introspector;
import java.beans.PropertyDescriptor;
import java.lang.reflect.Field;
import java.util.Arrays;
import java.util.Comparator;

public class BeanVsFieldDemo {
    public static class Base {
        private final String id;

        public Base(String id) {
            this.id = id;
        }

        public String getId() {
            return id;
        }
    }

    public static class Profile extends Base {
        public String raw = "raw-only";
        private String displayName = "Lan";
        private boolean active = true;
        private String internalCode = "hidden";

        public Profile() {
            super("P-1");
        }

        public String getDisplayName() {
            return displayName;
        }

        public void setDisplayName(String displayName) {
            this.displayName = displayName;
        }

        public boolean isActive() {
            return active;
        }

        public void setActive(boolean active) {
            this.active = active;
        }

        public String getSummary() {
            return displayName + " (" + getId() + ")";
        }
    }

    public static void main(String[] args) throws Exception {
        // 1. Retrieve fields declared directly in Profile.
        Field[] fields = Profile.class.getDeclaredFields();
        Arrays.sort(fields, Comparator.comparing(Field::getName));
        System.out.println("FIELDS: " + String.join(", ",
                Arrays.stream(fields).map(Field::getName).toList()));

        // 2. Discover properties via getter/setter, including inherited ones.
        BeanInfo beanInfo = Introspector.getBeanInfo(
                Profile.class,
                Object.class,
                Introspector.IGNORE_ALL_BEANINFO);

        PropertyDescriptor[] props = beanInfo.getPropertyDescriptors();
        Arrays.sort(props, Comparator.comparing(PropertyDescriptor::getName));

        System.out.println("PROPERTIES: " + String.join(", ",
                Arrays.stream(props).map(PropertyDescriptor::getName).toList()));

        for (PropertyDescriptor p : props) {
            System.out.println(p.getName() + ": read="
                    + (p.getReadMethod() == null
                        ? "-" : p.getReadMethod().getName())
                    + ", write="
                    + (p.getWriteMethod() == null
                        ? "-" : p.getWriteMethod().getName()));
        }

        // 3. Write property via setter, read computed property via getter.
        Profile profile = new Profile();

        for (PropertyDescriptor p : props) {
            if (p.getName().equals("displayName")) {
                p.getWriteMethod().invoke(profile, "Mai");
            }
            if (p.getName().equals("summary")) {
                System.out.println(
                        "summary=" + p.getReadMethod().invoke(profile));
            }
        }
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac -encoding UTF-8 BeanVsFieldDemo.java
java BeanVsFieldDemo
~~~

Verified output with JDK 17+:

~~~text
FIELDS: active, displayName, internalCode, raw
PROPERTIES: active, displayName, id, summary
active: read=isActive, write=setActive
displayName: read=getDisplayName, write=setDisplayName
id: read=getId, write=-
summary: read=getSummary, write=-
summary=Mai (P-1)
~~~

**Key explanations:**

1. **getDeclaredFields()** sees four fields **active**, **displayName**, **internalCode**, **raw** on **Profile**, whether private or public. Field **id** is declared in **Base**, so it is absent from this result.
2. **Introspector** recognizes **active** from **isActive/setActive**, and **displayName** from **getDisplayName/setDisplayName**.
3. **id** is an inherited property via **Base.getId()**, without needing an **id** field in **Profile**.
4. **summary** is a read-only property from **getSummary()**, with **no summary field**; its result depends on the object's current state.
5. **internalCode** is a private field without getter/setter; **raw** is a public field without accessor. Neither **becomes a property** under convention.
6. **PropertyDescriptor.getReadMethod/getWriteMethod** can return **null**. For instance, **id** and **summary** have no setter so they print **-**.
7. **setDisplayName("Mai")** is invoked via **Method.invoke**; afterwards, getter **getSummary()** produces the string **Mai (P-1)**. The example needs no private field access.

**Limitations of the example:** only operates on identified properties and public methods. In a real input-handling tool, verify property kind, permissions, writability, data types, and side-effect risks before calling setters.

## 6. Choosing Introspector or Field Reflection for each purpose

| Problem | Start with | Reason |
| --- | --- | --- |
| Rendering an edit form through a bean's public API | **PropertyDescriptor** | Reveals which properties are readable/writable via getter/setter |
| Tool discovering inherited properties | **Introspector** | Picks up public getters/setters in superclasses per JavaBeans rules |
| Inspecting field layout within the current class | **getDeclaredFields()** | Provides field metadata including private fields |
| Reading annotations placed directly on fields | **Field.getDeclaredAnnotations()** | Annotations may sit on the field, not on the getter |
| Reading annotations on getters | **PropertyDescriptor.getReadMethod()** then check method | Annotations on getters do not automatically appear on `Field` |
| Mapping through public setters with business validation | **Introspector** and invoke setters safely | Lets setter validation logic run; consider side effects |
| Low-level object debugger/inspector | **Reflection Field**, only when truly needed | Can inspect physical state not exposed by public API |
| Reading computed data like **summary** | **Introspector** | Does not require a field named **summary** |

A tool may use **both approaches** if each metadata source has a distinct meaning, yet it must clearly indicate whether it displays **physical fields**, **logical properties**, or two separate lists. Merging them by name and treating them as identical easily drops or misassigns data.

### Cases where naming conventions should not be treated as absolute inference

- Java records typically have accessors like **name()** instead of **getName()**; standard JavaBeans `Introspector` should not be assumed to treat every record accessor as a JavaBeans property automatically.
- Fluent APIs like **Person name(String value)** or **Person withName(...)** do not follow traditional **void setName(...)** setters; modern frameworks may support custom extended conventions.
- Getters may return computed results, query databases, or throw errors. **Seeing a getter** does not mean **calling the getter is always cheap and safe**.
- The same property name can arise from multiple overloaded or inherited methods; instead of manually pairing method strings, obtain the actual **PropertyDescriptor** and observe `Introspector`'s choice.

## 7. Filtering properties and reading/writing safely

A suitable workflow for a configuration or inspector tool:

1. Call **Introspector.getBeanInfo(type, Object.class)** to exclude `Object`'s **class** property if unneeded.
2. Obtain **PropertyDescriptor[]** and sort by name if deterministic output is wanted.
3. Filter properties against an explicit **allowlist**; do not automatically call getters/setters for every discovered property.
4. For read operations, check **getReadMethod() != null**; for write operations, check **getWriteMethod() != null**.
5. Before writing, check **getPropertyType()**, input type, compatibility, validation rules, and caller permissions.
6. Catch and classify operation errors such as **IllegalAccessException**, **InvocationTargetException**, **IllegalArgumentException**; when using **Method.invoke**, exceptions thrown by getters/setters usually reside in **InvocationTargetException.getCause()**.
7. Log enough details for diagnostics while avoiding exposing sensitive content from properties like passwords, tokens, or secrets.

Example filtering properties by name:

~~~java
for (PropertyDescriptor p : info.getPropertyDescriptors()) {
    if (!p.getName().equals("displayName")) {
        continue;
    }
    if (p.getWriteMethod() == null) {
        throw new IllegalStateException("Property is read-only");
    }
    // Only invoke setter after verifying object, input, and permissions.
}
~~~

This is an **illustrative snippet**, assuming **info** is an already obtained **BeanInfo**. In a real system, do not accept arbitrary property names from a request and allow writes across arbitrary objects: that can become a path to unwanted state mutation.

**Note on side effects:** invoking a JavaBeans getter via Reflection *executes code*. It can load data, mutate caches, execute business logic, or throw exceptions. By contrast, merely obtaining **PropertyDescriptor** to read name/getter metadata is essentially discovery and does not actively invoke the bean's getters.

## 8. Common mistakes when building introspection tools

### Confusing fields with properties

A class having **private String name** without getters/setters does not guarantee `Introspector` returns property **name**. Conversely, a property can exist without a same-named field. The fix is to clarify whether the tool needs to **represent internal state** or the **property interface**.

### Forgetting to exclude the `class` property

**Object.getClass()** matches getter syntax, so calling **getBeanInfo(SomeClass.class)** can surface property **class**. If you do not want it in business forms, use the overload with **stopClass=Object.class** or filter carefully; never treat it as a user-editable field.

### Invoking setter when write method is null

Read-only properties like **summary** lack a setter. **getWriteMethod()** returns **null**, so calling **invoke** unchecked causes **NullPointerException**. Likewise, write-only properties may lack a getter.

### Relying on default order

APIs listing fields, methods, and properties should not be used as output ordering contracts in docs/JSON. Use **Comparator.comparing(PropertyDescriptor::getName)** or an explicit criterion.

### Forgetting inheritance or treating JavaBeans as field-based

**getDeclaredFields()** excludes `Base`'s fields, while `Introspector` can still see inherited getters. Using **getFields()** yields only inherited/declared public fields per Reflection rules, still not equivalent to properties.

### Ignoring explicit BeanInfo

**Introspector** can use **FooBeanInfo** if the class supplies metadata. **IGNORE_ALL_BEANINFO** is only appropriate if you intentionally want convention-based inference ignoring that metadata. When integrating a tool supporting full JavaBeans, respect the library's `BeanInfo` contract.

### Using setAccessible to bypass encapsulation

If the goal is to call public getters/setters, directly accessing private fields often bypasses validation and breaks public contracts. In the Java module system, **setAccessible(true)** can also fail with **InaccessibleObjectException**. Prefer the right API for the job.

### Forgetting the `java.desktop` module

**java.beans** belongs to module **java.desktop**. In standard classpath applications on a full JDK, the API imports normally. In a **named module** with **module-info.java**, declare the dependency:

~~~java
module com.example.inspector {
    requires java.desktop;
}
~~~

The snippet above only illustrates module configuration; name modules/packages after your actual project.

## 9. Practice exercises

**Exercise 1 — Mismatched fields and properties.** Add **private String token** to **Profile** without adding accessors. Prediction: **getDeclaredFields()** will see **token**, whereas **Introspector** will not have a **token** property merely because the field exists.

**Exercise 2 — Computed property.** Add getter **getGreeting()** returning a string based on **displayName**; declare no **greeting** field. Re-run the inspector: the property list has **greeting**, while the field list lacks that name.

**Exercise 3 — Read-only vs write-only.** Add **setApiKey(String)** without **getApiKey()**. Inspect the actual **PropertyDescriptor**, **getReadMethod()**, and **getWriteMethod()** results. Do not print or record secrets in the exercise.

**Exercise 4 — Inheritance.** Add getter **getCode()** on **Base**; compare **Profile.class.getDeclaredFields()**, **Profile.class.getFields()**, and `Introspector` on **Profile** to explain when results include inherited members.

**Exercise 5 — Uppercase names.** Create **getURL()**, **setURL(String)** then run **Introspector.decapitalize("URL")** and check the property name. Explain why you shouldn't write an algorithm that always lowercases the first character.

**Exercise 6 — Distinguishing method and field annotations.** Place one runtime annotation on a field and one annotation on its corresponding getter. Query annotations via **Field** and via **PropertyDescriptor.getReadMethod()**. Prove they are two separate metadata locations.

## 10. Self-check and technical conclusion

**Question 1.** There is **private String name** with no getter/setter. Will `Introspector` definitely list property **name**?  
**Answer:** No. An internal field does not automatically create a property under JavaBeans convention.

**Question 2.** There is no **fullName** field, yet there is a public **getFullName()** with the right signature. Can `Introspector` return property **fullName**?  
**Answer:** Yes, that can be a computed read-only property.

**Question 3.** Why is **getDeclaredFields()** of a subclass insufficient to know all properties?  
**Answer:** It only scans directly declared fields, whereas JavaBeans properties come from getters/setters and can be inherited.

**Question 4.** When does **getWriteMethod()** return null?  
**Answer:** When the property descriptor has no recognized setter. The tool must treat it as read-only in that context.

**Question 5.** Is a public getter guaranteed to have no side effects?  
**Answer:** No. It is ordinary code, differing only in convention-based naming and signature.

**Question 6.** Why might **getBeanInfo(type, Object.class)** be needed?  
**Answer:** To exclude metadata from **Object**, especially the **class** property produced by **getClass()**.

**Question 7.** Are a JavaBeans property and a Spring bean the same concept?  
**Answer:** No. A property describes an object's read/write interface; a Spring bean is an object managed by a container.

**Completion criteria:** you can explain the sample program output, deliberately choose **PropertyDescriptor** or **Field**, check for null getters/setters, handle property names and inheritance accurately, and understand access limits and side effects when implementing a real inspector.

**Official references:** Oracle Java SE 21 API — **java.beans.Introspector**, **BeanInfo**, **PropertyDescriptor**, **java.lang.reflect.Field**, **java.lang.reflect.Method**, and *JavaBeans Specification*.