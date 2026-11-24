# Read-Write Data Binding and Updating Objects

SpEL can read and update an object's properties through EvaluationContext. When only reading data is needed, the context can be configured in read-only mode. When writing values is needed, SimpleEvaluationContext.forReadWriteDataBinding() provides a property accessor for read/write access within the limited scope of data binding.

Updating objects with SpEL is usually done via Expression.setValue(context, value) or an overload taking a root object. This approach fits when the application has already identified the target object and wants to use a property path in an expression to read or write a value. You must clearly define which properties are allowed to be written, the target data types, the object's mutability state, and how errors are handled.

## 1. Read-Write Data Binding in SpEL

EvaluationContext controls how SpEL accesses properties and other capabilities during expression evaluation. SimpleEvaluationContext is designed for data binding use cases that need a restricted feature set.

You can create a context that supports reading and writing properties:

~~~java
EvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding()
                .build();
~~~

This context configures the property accessor for data binding in read-write mode. Expressions can read properties and write to writable properties through the provided accessor.

If only reading is needed:

~~~java
EvaluationContext readOnly =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();
~~~

A read-only context suits display or data-filtering expressions. A read-write context is for situations that need to update objects. Choose the right mode according to the actual operation of the expression.

## 2. Reading Properties from the Root Object

When creating or using a context, an object can be supplied as the root object. Property expressions without a variable prefix are resolved on that root object.

For example:

~~~java
public class Profile {

    private String displayName;
    private int age;

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public int getAge() {
        return age;
    }

    public void setAge(int age) {
        this.age = age;
    }
}
~~~

Reading a property:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Profile profile = new Profile();
profile.setDisplayName("Lan");
profile.setAge(25);

EvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding()
                .build();

Expression nameExpression =
        parser.parseExpression("displayName");

String name = nameExpression.getValue(
        context,
        profile,
        String.class
);
~~~

This getValue overload takes the context, root object, and result type. The root object in this evaluation is profile. The same Expression can be used with different objects if their property paths are compatible.

## 3. Updating Properties with Expression.setValue

Expression.setValue lets you write a value to the property specified by the expression:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Profile profile = new Profile();
profile.setDisplayName("Lan");

EvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding()
                .build();

Expression nameExpression =
        parser.parseExpression("displayName");

nameExpression.setValue(context, profile, "Minh");

System.out.println(profile.getDisplayName()); // Minh
~~~

The expression displayName identifies the target property. The new value is passed separately via setValue. This style keeps input data in Java and lets the SpEL string describe only the property path.

If the root object has already been attached to StandardEvaluationContext or another suitable context, you can use the setValue(context, value) overload. When using SimpleEvaluationContext without an attached root object, pass the root object to the corresponding overload.

Parsing the expression does not modify the object yet. The modification occurs when setValue is called and the property accessor performs the write operation.

## 4. Reading Back the Value After Updating

After writing, you can use the same Expression to read the property back:

~~~java
nameExpression.setValue(context, profile, "Minh");

String updatedName = nameExpression.getValue(
        context,
        profile,
        String.class
);

System.out.println(updatedName); // Minh
~~~

Reading back helps the application retrieve the current value from the object. If the property has a setter that normalizes data or logic in the accessor, the read-back value can reflect the post-update state.

Do not assume every setter only performs direct assignment. A setter can validate conditions, normalize strings, update related properties, or throw exceptions. Design setters so update behavior is clear and testable in Java.

## 5. Updating Nested Properties

A property path can traverse multiple objects:

~~~text
address.city
customer.profile.displayName
settings.notification.emailEnabled
~~~

For example:

~~~java
public class Address {

    private String city;

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }
}

public class Customer {

    private Address address;

    public Address getAddress() {
        return address;
    }

    public void setAddress(Address address) {
        this.address = address;
    }
}
~~~

Updating city:

~~~java
Customer customer = new Customer();
Address address = new Address();
customer.setAddress(address);

Expression cityExpression =
        parser.parseExpression("address.city");

cityExpression.setValue(context, customer, "Da Nang");
~~~

Intermediate objects along the path must exist and be accessible. If customer.address is null, SpEL does not automatically create a new Address just because the expression requests writing address.city. The application needs to initialize the intermediate object first or update the entire child object in a separate operation.

For long property paths, check each link to know which objects can be null and which properties have setters.

## 6. Writing to a Map by Key

An indexer can be used to update a Map entry if the Map is mutable and the context allows write operations.

For example:

~~~java
Map<String, Object> settings = new HashMap<>();
settings.put("theme", "light");

EvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding()
                .build();

Expression themeExpression =
        parser.parseExpression("#settings['theme']");

context.setVariable("settings", settings);

themeExpression.setValue(context, "dark");

System.out.println(settings.get("theme")); // dark
~~~

The indexer #settings['theme'] identifies the value by the key theme. When the key already exists, writing updates the entry's value. With a mutable Map, a new entry can be created by writing to a nonexistent key if the implementation and property accessor support it.

Unmodifiable Maps or Maps wrapped in a read-only view may reject the operation. When writing to a Map from an expression, determine the key type, value type, and mutability of the Map.

If the key is computed from a variable, a dynamic expression can be used:

~~~text
#settings[#selectedKey]
~~~

In that case, selectedKey must be registered in the context and have a type compatible with the Map's key.

## 7. Updating Elements in a List or Array

A positional indexer can access elements in a List or array. If the element is an object with writable properties, the indexer can be combined with a property path:

~~~text
items[0].name
addresses[1].city
~~~

For example:

~~~java
Expression firstName =
        parser.parseExpression("items[0].name");

firstName.setValue(context, rootObject, "New name");
~~~

The path requires the List to have an element at the corresponding index and that element to have a writable name property. Writing to an existing index is different from adding a new element to the List.

An indexer does not automatically expand a List to create nonexistent positions. If the index is out of bounds or the collection does not support updates, the operation may fail. Add or modify the collection structure in Java before using SpEL to update a specific element.

For arrays, the size is fixed. Existing elements can be updated if the component type and access permissions allow it, but an indexer cannot be used to grow an array's size.

## 8. Type Conversion When Writing Properties

The target property may have a different type from the value object passed to setValue. SpEL uses EvaluationContext's TypeConverter to convert when a suitable converter exists.

Example of an Integer property age:

~~~java
public class Member {

    private Integer age;

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }
}
~~~

A String value can be written if the TypeConverter supports converting String to Integer:

~~~java
Member member = new Member();

Expression ageExpression = parser.parseExpression("age");

ageExpression.setValue(context, member, "30");
~~~

The result depends on the configured converter and the input data. A string that is not a valid number can cause a conversion error. Do not assume all types convert automatically.

When a property has a custom domain type, configure an appropriate converter or convert the data in Java before calling setValue. Type conversion does not replace business validation.

## 9. Configuring TypeConverter or ConversionService

SimpleEvaluationContext.Builder allows configuring a TypeConverter when the application needs custom conversion rules.

Example using ConversionService:

~~~java
DefaultConversionService conversionService =
        new DefaultConversionService();

EvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding()
                .withTypeConverter(
                        new StandardTypeConverter(conversionService)
                )
                .build();
~~~

Domain converters can be registered into ConversionService before creating the context. When SpEL writes a property, TypeConverter will be used to convert the value to the target type if a matching converter exists.

Keep converters focused on type conversion. Rules such as age must be positive, status allowed to be updated, or amount limits should be checked in the validation or service layer.

## 10. Properties Must Be Writable

Not every readable property can be written. For an update to succeed, the property accessor must find a way to write the value to the target.

Common situations:

- The property has a corresponding getter and setter.
- The property only has a getter, so it is read-only.
- The setter is not accessible with the current accessor.
- The property is read-only or protected by the object's structure.
- The property path goes through a null intermediate object.
- The value type cannot be converted to the property type.

Example of a property with only a getter:

~~~java
public class ImmutableProfile {

    private final String name;

    public ImmutableProfile(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }
}
~~~

The expression name can read the value, but there is no setter to update via normal JavaBean property access. For immutable objects, create a new object via a constructor, factory, or copy method in Java instead of trying to write to the property.

## 11. A Read-Write Context Does Not Mean Every Action Is Allowed

SimpleEvaluationContext.forReadWriteDataBinding() provides property read/write capabilities within a limited feature set. It does not automatically enable all features of StandardEvaluationContext.

SimpleEvaluationContext does not support type references T(...), constructor invocation, bean references, or broad method invocation features like the full context. If a use case needs other features, carefully evaluate the scope and configuration rather than switching contexts by default.

Read-write only states that the configured property accessor allows writing. It does not mean every object or every property in the application should be placed into the context. Supply a small root object and expose only the data the expression needs to update.

## 12. Distinguishing SpEL Updates from Spring's DataBinder

SpEL setValue writes to the property path specified in the Expression. DataBinder or WebDataBinder performs the process of binding input data into an object by field name.

| Aspect | SpEL read-write | DataBinder/WebDataBinder |
|---|---|---|
| Purpose | Read or write properties by expression | Bind source data into an object |
| Update target | Property path in Expression | Field/property named in binding data |
| Trigger | Calling getValue or setValue | Calling the binder's bind process |
| Type conversion | EvaluationContext's TypeConverter | Binder's ConversionService/property editor |
| Validation | Does not automatically run validation | Can combine Validator and Bean Validation |
| Errors | Exception during access or conversion | Can be recorded in BindingResult |
| Field restriction | Accessors and objects supplied to context | Allowed/disallowed fields and binder configuration |

If updating a specific property in an internal rule, Expression.setValue may fit. If receiving form or request data, DataBinder/WebDataBinder provides a more suitable binding and error-handling workflow.

## 13. Controlling Which Fields Are Allowed to Be Updated

A read-write context can write to properties permitted by the accessor on the provided object. Therefore, you should not supply an entity with many sensitive fields as the root object for an untrusted expression.

For example, a User has properties such as displayName, role, enabled, and accountBalance. If expressions can write arbitrarily, providing the entire User could allow modifying more fields than the use case intended.

Some principles:

1. Use DTOs or command objects containing only properties allowed to be updated.
2. Do not put entities or objects with extensive internal state into the context if unnecessary.
3. Only use a read-write context for use cases that truly need writing.
4. Check update permissions at the application/service layer.
5. Validate the object after updating and before saving.
6. Do not treat the property accessor as a business authorization mechanism.

With user-supplied data, also control which property paths they are allowed to select. Do not let users freely send property names and use them directly as write expressions.

## 14. Updating Objects Can Create Side Effects

Writing a property can invoke a setter. A setter can change other state, raise internal events, or throw exceptions. If the property path points to a shared object, changes can become visible from multiple places holding the same reference.

Clearly identify the object's lifecycle before updating. If the object is temporary data within a single request, updating is usually easier to control than modifying a singleton or shared cached object.

Do not use SpEL to perform multi-step complex business updates in one long expression. Split operations into clearly named Java steps so transactions, authorization, validation, and error handling can be controlled.

## 15. Handling Errors During Read/Write

Errors can occur at multiple steps:

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Property not found | Typo or target object lacks the property | Check the property path and root object type |
| Cannot write property | Property is read-only or lacks a matching setter | Use a writable property or create a new object |
| Cannot read property | Accessor does not support the object type or property | Check the accessor and context configuration |
| Error on nested property | Intermediate object is null | Initialize the child object before updating |
| Index out of bounds | List/array lacks an element at that position | Check size and index before writing |
| Map rejects update | Map is immutable or read-only | Use a mutable Map if the use case needs writing |
| Conversion failed | Missing converter or malformed value | Check source type, target type, and TypeConverter |
| Setter throws exception | Rules inside the setter rejected the value | Inspect the root cause and check invariants |
| Data updated but invalid | Conversion succeeded but validation is missing | Validate before saving |

ParseException usually indicates a syntax error when creating the Expression. EvaluationException or SpelEvaluationException usually appears during evaluation, property access, conversion, or data writing. Separate the two phases when diagnosing.

## 16. Complete Example: Controlled Object Update

The following example uses a form object containing only the fields allowed to be updated:

~~~java
public class ProfileForm {

    private String displayName;
    private Integer age;

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }
}
~~~

Creating the context and updating:

~~~java
ExpressionParser parser = new SpelExpressionParser();

ProfileForm form = new ProfileForm();

EvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding()
                .build();

Expression displayName =
        parser.parseExpression("displayName");

Expression age =
        parser.parseExpression("age");

displayName.setValue(context, form, "Lan Nguyen");
age.setValue(context, form, 30);

String savedName = displayName.getValue(
        context,
        form,
        String.class
);

Integer savedAge = age.getValue(
        context,
        form,
        Integer.class
);
~~~

After updating, the application still needs to validate the form against business rules before transferring data to an entity or saving to the database. The fact that SpEL succeeded in writing both properties only confirms that the accessor and conversion performed the operation; it does not confirm that the entire object is valid.

## 17. Takeaways

SimpleEvaluationContext.forReadWriteDataBinding() creates an EvaluationContext with property access supporting reading and writing within the scope of data binding. Use Expression.setValue(context, rootObject, value) to update a property path and getValue to read it back. You can update nested properties, Map entries, or collection elements if intermediate objects exist, the target is mutable, and the accessor supports it.

Writing may require a TypeConverter to convert the value to the property type. Read-only properties, null intermediate objects, out-of-bounds indices, or immutable collections can all cause the operation to fail. Conversion does not replace validation.

A read-write context does not automatically provide all capabilities of StandardEvaluationContext and does not replace DataBinder/WebDataBinder. Restrict the exposed objects and properties, check permissions at the service layer, validate after updating, and handle errors at appropriate boundaries.