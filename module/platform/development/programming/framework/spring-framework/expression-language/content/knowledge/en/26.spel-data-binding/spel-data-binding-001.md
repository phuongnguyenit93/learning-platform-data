# SpEL in Object Property Binding

## 1. What Is Property Binding with SpEL?

Spring Expression Language (SpEL) not only reads object properties, but can also write values to a property if the property accessor allows writing.

For example, with a Customer object that has a name property:

    ExpressionParser parser = new SpelExpressionParser();

    Customer customer = new Customer();

    Expression nameExpression =
        parser.parseExpression("name");

    nameExpression.setValue(customer, "Lan");

After the expression is evaluated, the name property of customer receives the value Lan.

SpEL can do this through the setValue API or the assignment operator in an expression. Using setValue is usually clearer when the new value comes from Java code.

Two operations should be distinguished:

- **Property access for reading:** retrieving a value from an object, for example name or address.city.
- **Property binding for writing:** updating a value on an object, for example setValue(..., "Lan").

Writing depends on the PropertyAccessor, whether the property is writable, and data type conversion.

## 2. Property Expressions and the Root Object

When an expression does not have a # or @ prefix, SpEL usually resolves the property name relative to the root object.

For example:

    public class Customer {
        private String name;

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }
    }

Setting the root object:

    Customer customer = new Customer();

    StandardEvaluationContext context =
        new StandardEvaluationContext(customer);

    ExpressionParser parser =
        new SpelExpressionParser();

    Expression expression =
        parser.parseExpression("name");

Reading a property:

    String currentName =
        expression.getValue(context, String.class);

Writing a property:

    expression.setValue(context, "Lan");

    // customer.getName() == "Lan"

Here name is a property of the root object customer. There is no need to write #customer because the object has already been set as the root.

It is also possible to pass the root object directly into an overload of Expression:

    Expression expression =
        parser.parseExpression("name");

    expression.setValue(context, customer, "Lan");

This approach is useful when the same expression is used on multiple different objects.

## 3. Writing Properties Using Expression.setValue

The setValue API is the direct way to assign a value to a property expression.

Syntax:

    expression.setValue(context, rootObject, newValue);

Or when the context already has a root object:

    expression.setValue(context, newValue);

For example:

    Expression cityExpression =
        parser.parseExpression("address.city");

    cityExpression.setValue(
        context,
        customer,
        "Da Nang"
    );

SpEL traverses the property path and writes the value to the final property.

You can check whether a property is writable before assigning:

    if (cityExpression.isWritable(context, customer)) {
        cityExpression.setValue(
            context,
            customer,
            "Da Nang"
        );
    }

isWritable helps determine whether an expression can write to the target according to the current accessor. It does not replace data validation, business rule checks, or type conversion error handling when setValue actually runs.

If the property cannot be written, SpEL may throw an EvaluationException or a specialized exception from the property access process.

## 4. Conditions for a Property to Be Writable

A property can only be updated if the current PropertyAccessor supports the write operation on that target.

For a standard JavaBean, a property usually has a getter and a setter:

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

In reflective property access, SpEL can recognize properties through getters/setters and supported public fields.

Cases where a property may not be writable:

- The property only has a getter and no matching setter.
- The property is immutable or has no write mechanism supported by the accessor.
- The current PropertyAccessor only allows reading.
- The target object is not of a type supported by the accessor.
- The new value cannot be converted to the property type.
- An intermediate object in the path is null.

You should not assume that being able to read a property means you can definitely write to that property. Read and write are two separate capabilities.

## 5. Binding Nested Properties

SpEL supports multi-level property paths using dot notation.

Example object model:

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

If customer already has an address, city can be written:

    Expression cityExpression =
        parser.parseExpression("address.city");

    cityExpression.setValue(
        context,
        customer,
        "Da Nang"
    );

The path address.city means:

1. Read the address property on Customer.
2. Get the returned Address object.
3. Write the city property on that Address object.

Each intermediate step must return an appropriate object for the next step to execute.

## 6. Handling Null Intermediate Objects

If address is null, SpEL does not have an Address object to write city to along the normal path.

For example:

    Customer customer = new Customer();
    customer.setAddress(null);

    Expression expression =
        parser.parseExpression("address.city");

    expression.setValue(
        new StandardEvaluationContext(customer),
        "Da Nang"
    );

In the default configuration, this operation may fail because address is null.

There are two ways to handle this:

**Initialize the object before binding:**

    customer.setAddress(new Address());

    expression.setValue(
        new StandardEvaluationContext(customer),
        "Da Nang"
    );

**Configure SpEL auto-grow null references:**

    SpelParserConfiguration configuration =
        new SpelParserConfiguration(true, true);

    ExpressionParser parser =
        new SpelExpressionParser(configuration);

The configuration above enables automatic initialization of null references and automatic collection growth as supported by SpEL. When enabled, SpEL can create intermediate objects if the property type can be instantiated appropriately.

Auto-grow is not magic that can create every object. The data type needs an appropriate way to be instantiated, and creating objects can have side effects. Enable it explicitly when needed, while also controlling collection indices and sizes if input data can vary.

Do not confuse SpEL auto-grow with DataBinder auto-grow. These are two independent configuration mechanisms.

## 7. Binding List and Map Elements

Indexers allow writing to collection or Map elements.

Example with List:

    public class Customer {
        private List<String> tags =
            new ArrayList<>();

        public List<String> getTags() {
            return tags;
        }

        public void setTags(List<String> tags) {
            this.tags = tags;
        }
    }

Writing the first element:

    Expression tagExpression =
        parser.parseExpression("tags[0]");

    tagExpression.setValue(
        context,
        customer,
        "premium"
    );

Example with Map:

    Expression themeExpression =
        parser.parseExpression("preferences['theme']");

    themeExpression.setValue(
        context,
        customer,
        "dark"
    );

Nested paths can also combine indexers:

    addresses[0].city
    attributes['displayName']

The target collection or Map must exist and the index/key operation must match the actual data, unless the parser is configured with auto-grow for supported cases.

For a List or array, indices start at 0. For a Map, the value inside square brackets is the key.

## 8. Type Conversion During Binding

The new value does not necessarily have the same Java type as the target property. SpEL uses the TypeConverter in EvaluationContext to convert when possible.

Example of a boolean property inside a List:

    public class Preferences {
        public List<Boolean> flags =
            new ArrayList<>();
    }

    Preferences preferences = new Preferences();
    preferences.flags.add(true);

    EvaluationContext context =
        SimpleEvaluationContext
            .forReadOnlyDataBinding()
            .build();

    parser.parseExpression("flags[0]")
        .setValue(context, preferences, "false");

The String value "false" is converted to Boolean false through Spring's conversion service.

SpEL is also generic-type aware in appropriate cases. If the property is List<Boolean>, the conversion service can convert each input value to Boolean to preserve the element type.

If conversion is not supported or the data is malformed, evaluation may fail.

Do not rely on implicit conversion without defining format, locale, and value ranges. For data from forms or APIs, validate the input data before binding.

## 9. SimpleEvaluationContext for Data Binding

If the use case only needs to read or write data properties without needing the full capabilities of SpEL, you can use SimpleEvaluationContext.

Reading properties:

    SimpleEvaluationContext readOnlyContext =
        SimpleEvaluationContext
            .forReadOnlyDataBinding()
            .build();

Writing properties:

    SimpleEvaluationContext readWriteContext =
        SimpleEvaluationContext
            .forReadWriteDataBinding()
            .build();

For example:

    Customer customer = new Customer();

    Expression nameExpression =
        parser.parseExpression("name");

    nameExpression.setValue(
        readWriteContext,
        customer,
        "Lan"
    );

forReadWriteDataBinding() enables reading and writing properties through DataBindingPropertyAccessor.

SimpleEvaluationContext only provides a limited set of SpEL features. It does not support type references, constructor invocation, or bean references like StandardEvaluationContext.

If the goal is property binding on data objects, this is usually a more suitable choice than the full context. However, it does not automatically guarantee safety for every expression or every exposed object. Getters, setters, and custom accessors can still have side effects.

## 10. Distinguishing SpEL Binding from Spring DataBinder

A common point of confusion: Spring DataBinder is not a SpEL parser.

Both mechanisms can write properties onto an object, but they work differently.

| Criterion | SpEL Expression.setValue | Spring DataBinder |
| --- | --- | --- |
| Input | Expression string and new value | PropertyValues or binding data |
| Syntax | SpEL property expression | JavaBeans property path |
| Example | address.city | address.city |
| Execution | Expression and EvaluationContext | DataBinder with BeanWrapper/property access |
| Type conversion | TypeConverter in EvaluationContext | Binding ConversionService/PropertyEditor |
| Purpose | Evaluate an expression and read/write via expression | Bind input data into a target object |
| Validation | Does not automatically run business validation | Can integrate Validator and BindingResult |

The address.city syntax looks similar, but that does not mean DataBinder evaluates the entire SpEL language.

DataBinder handles property paths according to JavaBeans conventions. It does not automatically understand SpEL syntax such as:

    #customer.name
    @pricingService
    name ?: 'Guest'
    new com.example.Customer()

If an application receives form or request data from users and wants to update a DTO, DataBinder is usually a more appropriate tool than parsing expression strings yourself.

## 11. Example of Using DataBinder for an Object

Suppose we have a form object:

    public class CustomerForm {
        private String displayName;
        private Address address;

        public String getDisplayName() {
            return displayName;
        }

        public void setDisplayName(String displayName) {
            this.displayName = displayName;
        }

        public Address getAddress() {
            return address;
        }

        public void setAddress(Address address) {
            this.address = address;
        }
    }

Property values can be bound as follows:

    CustomerForm form = new CustomerForm();

    DataBinder binder = new DataBinder(form);

    binder.setAllowedFields(
        "displayName",
        "address.city"
    );

    MutablePropertyValues values =
        new MutablePropertyValues();

    values.add("displayName", "Lan");
    values.add("address.city", "Da Nang");

    binder.bind(values);

    BindingResult result =
        binder.getBindingResult();

In this example, DataBinder receives property paths and corresponding values. It uses Spring's property binding mechanism to update the object.

With the standard DataBinder, auto-grow nested paths is enabled by default in typical configurations; this can be changed with setAutoGrowNestedPaths(false). Collection auto-grow also has configurable limits to avoid creating overly large collections from input indices.

If you need to check binding errors, read BindingResult. Binding errors and validation errors can be handled before saving the object.

## 12. Restricting Allowed Binding Fields

When binding data from untrusted requests, users should not be allowed to update every property of a large entity.

For example, an entity might contain:

- id or ownerId.
- roles and administrative permissions.
- payment status.
- internal information.
- relationships to other objects.
- audit fields such as createdBy or approvedBy.

If all property paths are bound without restriction, users can send additional fields beyond the intended form. This belongs to the mass assignment or over-posting risk category.

With DataBinder, declare an allow-list:

    binder.setAllowedFields(
        "displayName",
        "address.city"
    );

Only allowed property paths are bound.

With SpEL, keep property path expressions controlled by the application:

    Expression expression =
        parser.parseExpression("displayName");

Do not take an arbitrary expression string sent by a user and directly parse and evaluate it.

If dynamic field selection is needed, map external field names to a predefined list of expressions:

    Map<String, Expression> writableProperties = ...;

Then only retrieve expressions from the application's allow-list; do not directly parse arbitrary strings from requests.

## 13. Validation After Binding

Binding is only the step of transferring input values into an object. It does not prove that the data is valid from a business perspective.

For example:

    age = -10

Can be successfully assigned to an int property, yet still violates business rules.

Similarly:

    email = 'not-an-email'

Can be successfully written to a String property, yet is not a valid email address.

After binding, perform validation:

- Check required fields.
- Check value ranges and numeric limits.
- Check formats for email, phone number, or codes.
- Check relationships between fields.
- Check permission to update the object for the current user.
- Check business state before saving.

DataBinder can integrate a Validator and return errors via BindingResult. With SpEL setValue, the application needs to invoke a Validator or separate checking logic after updating the object.

Do not treat a successful setValue as passing validation.

## 14. Binding with Side Effects

setValue updates the object immediately when called. If a setter has additional logic, that logic can also execute.

For example, a setter might:

- Normalize data.
- Update another field.
- Write an audit log.
- Invoke a callback.
- Perform unexpected checks or interactions.

If an expression performs multiple assignments, one assignment may have already modified the object before the next assignment fails. SpEL does not automatically create a transaction or rollback for a chain of assignments.

For critical business data, consider:

- Binding into an intermediate DTO.
- Validating the entire DTO.
- Passing valid data to a service.
- Updating the entity within a transaction.
- Recording audits and enforcing permissions at the business layer.

Do not use expressions to replace a complex business update workflow.

## 15. Distinguishing Property Paths from User-Entered Expressions

A property path such as:

    address.city

only identifies the location of the property to read or write.

A SpEL expression can do much more:

    #customer.address.city = #newCity

    @customerService.update(#customerId, #newCity)

    new com.example.Address()

Therefore, if users only need to select which field to update, accept a property identifier or form field against an allow-list. Do not ask them to send a general-purpose SpEL expression.

For untrusted data:

- Do not parse and evaluate arbitrary expressions.
- Do not expose services, beans, or objects with broad permissions.
- Do not allow method invocation or constructors if the use case does not require them.
- Use DTOs containing only bindable properties.
- Use allowedFields in DataBinder.
- Limit nested paths and collection auto-grow.
- Check data types, validation, and update permissions.

SimpleEvaluationContext can restrict features compared to StandardEvaluationContext, but it should not be treated as an absolute security boundary.

## 16. Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Property is not writable | No setter or accessor is read-only | Check the setter and PropertyAccessor |
| Nested path fails | Intermediate object is null | Initialize the object or configure controlled auto-grow |
| Index out of bounds | List/array lacks the corresponding element | Check the index or auto-grow limits |
| Conversion error | Value cannot be converted to the property type | Check TypeConverter and input format |
| SimpleEvaluationContext rejects write | Used the read-only builder | Choose forReadWriteDataBinding() if writing is needed |
| Bean or constructor expression does not work | SimpleEvaluationContext does not support those full features | Only use the full context when the use case is trusted and requires it |
| DataBinder does not understand #variable or @bean | DataBinder processes property paths, not SpEL parsing | Use the right API for the right kind of expression |
| Unexpected field gets updated | Binding has no allow-list | Configure setAllowedFields and narrow DTOs |
| Binding succeeds but data violates business rules | Validation has not been run | Validate after binding |
| Object is partially modified on error | Assignment already executed before a later step failed | Bind into an intermediate DTO and update in a controlled manner |

When debugging, identify which step the error belongs to:

1. Parsing the expression.
2. Checking whether the property is writable.
3. Accessing the root object and nested objects.
4. Type conversion.
5. Writing the value.
6. Validating the object after binding.

If using DataBinder, check BindingResult and allowed property paths instead of looking for errors in the SpEL parser.

## 17. Key Takeaways

- SpEL can write properties via Expression.setValue().
- Property expressions are resolved relative to the root object or an object referenced via a variable.
- You can check isWritable() before writing.
- PropertyAccessor must support write; being able to read a property does not mean it is writable.
- Nested properties, List indices, and Map keys can be used as write paths.
- Null intermediate objects must be initialized or configured with appropriate auto-grow settings.
- EvaluationContext's TypeConverter supports converting values when possible.
- SimpleEvaluationContext.forReadWriteDataBinding() enables property read/write with a limited feature set.
- Spring DataBinder is a separate property binding mechanism, not a SpEL parser.
- DataBinder uses JavaBeans property paths and can be restricted using setAllowedFields().
- Binding does not replace business validation.
- Do not parse arbitrary user-supplied expressions; use DTOs, allow-lists, and narrowly scoped contexts.
- setValue mutates the object immediately and does not automatically provide transactions or rollback.

When you need to write properties using SpEL, use application-controlled expressions, choose the right EvaluationContext, and check writability, conversion, and intermediate objects. When the goal is binding forms or requests into DTOs, use DataBinder with an allow-list and validation. Both approaches can operate on JavaBeans, but they serve two different types of data flows.

## References

- Spring Framework Reference — Evaluation and Expression.setValue: https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html
- Spring Framework Reference — Data Binding: https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html
- Spring Framework Reference — Model Design and Allowed Fields: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html
- Spring Framework Javadoc — SimpleEvaluationContext: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/SimpleEvaluationContext.html
- Spring Framework Javadoc — DataBindingPropertyAccessor: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/DataBindingPropertyAccessor.html
