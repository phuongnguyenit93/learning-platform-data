# Distinguishing Assignment in SpEL from Framework Data Binding

SpEL has an assignment operator to change the value of a property on an object accessed by an expression. Spring also has a data binding mechanism to populate input data, such as request parameters or form fields, into an object's properties. Both can modify an object, yet they differ in purpose, execution timing, control mechanisms, and data-handling responsibilities.

Assignment in SpEL is an action that occurs when an expression is evaluated in an EvaluationContext. Data binding is a framework workflow: the framework receives input data, maps field names to properties, converts types, applies binding rules, and can run validation. The two mechanisms should not be treated as interchangeable.

## 1. The Assignment Operator in SpEL

SpEL uses a single equals sign to assign a value:

~~~text
name = 'Lan'
quantity = 3
address.city = 'Ho Chi Minh City'
~~~

When the expression is evaluated, SpEL locates the target property via the EvaluationContext's property access mechanism and writes the new value to that property. The object to modify is typically the root object or an object reachable from the root object.

Example with a Java bean:

~~~java
public class Profile {

    private String displayName;

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
~~~

You can assign the property using an expression:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Profile profile = new Profile();
StandardEvaluationContext context =
        new StandardEvaluationContext(profile);

Expression assignment = parser.parseExpression(
        "displayName = 'Lan'"
);

assignment.getValue(context);

System.out.println(profile.getDisplayName()); // Lan
~~~

The parseExpression call only parses the string and creates an Expression. Modifying the object happens when calling getValue with the context, because that is when the expression is evaluated. If you only parse without evaluating, the property has not been changed yet.

For the assignment to succeed, the target property must be writable through the accessor used by the context. If the property does not exist, lacks a suitable setter, or the accessor only permits reading, SpEL cannot perform that assignment.

## 2. Assigning Nested Properties

An expression can traverse nested properties and then assign to a property on a child object:

~~~java
Expression assignment = parser.parseExpression(
        "address.city = 'Ho Chi Minh City'"
);

assignment.getValue(context);
~~~

The path address.city requires the root object to have an address property, and the returned object to have a writable city property. If any link in the path is null or inaccessible, the assignment can fail.

When assigning to a nested object, note that the expression can directly mutate the state of the referenced child object. If that object is shared in multiple places, changes can be observed by other code holding the same reference.

Do not pass an overly broad object graph into the context just for the convenience of one assignment. Choose a root object with a small scope that contains only the properties the expression actually needs to modify.

## 3. Distinguishing Assignment Equals from Comparison Equals

In SpEL, a single equals sign and a double equals sign have different meanings:

| Syntax | Meaning | Example |
|---|---|---|
| = | Assign a value | name = 'Lan' |
| == | Compare equality | name == 'Lan' |
| != | Compare inequality | status != 'DISABLED' |

Example:

~~~text
status = 'ACTIVE'
~~~

This expression writes the value ACTIVE to the status property if the property is writable.

Meanwhile:

~~~text
status == 'ACTIVE'
~~~

only checks whether status equals ACTIVE and returns a Boolean result. It does not change the property.

Confusing = and == can lead to unintended side effects. When writing conditional expressions, use comparison operators. Use a single equals sign only when you genuinely intend to update data during evaluation.

## 4. Using Expression.setValue to Write a Property

SpEL also provides the setValue API on Expression. This API is suited when the expression only describes the path to the property to write:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Profile profile = new Profile();
EvaluationContext context =
        new StandardEvaluationContext(profile);

Expression displayName = parser.parseExpression("displayName");

displayName.setValue(context, "Minh");

System.out.println(profile.getDisplayName()); // Minh
~~~

Here, the string displayName specifies the target property. The value is passed separately into setValue, so there is no need to embed the new value into the expression string.

You can use the same approach for nested properties:

~~~java
Expression city = parser.parseExpression("address.city");
city.setValue(context, "Da Nang");
~~~

Both the assignment operator in an expression and Expression.setValue can mutate the object. The main difference lies in how they are expressed:

- The = operator places both the target property and the value to assign in the SpEL content.
- setValue separates the property path expression from the new value passed from Java.

If the application already has the value in Java and only needs to write it to a property, setValue usually makes data boundaries clearer. If you are building an expression whose update goal is described within the rule itself, the assignment operator can fit, provided the context and expression source are clearly controlled.

## 5. EvaluationContext Determines Whether a Property Is Writable

Read and write capabilities depend on the property accessors provided by EvaluationContext.

### 5.1. StandardEvaluationContext

StandardEvaluationContext supports configuring a root object, variables, functions, property accessors, and other resolvers. The default property accessors use reflection to access matching Java properties, including write capability if the property supports it.

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(profile);

parser.parseExpression("displayName = 'Lan'")
        .getValue(context);
~~~

This context has a broad feature scope. If an expression is untrusted, allowing it access to a large object or methods with side effects can expand the expression's privileges beyond the original intent.

### 5.2. Read-Only SimpleEvaluationContext

If you only need to read data, you can use:

~~~java
EvaluationContext readOnly =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();
~~~

A read-only context fits expressions that filter or display data. Do not expect property assignment to work in this context because its accessor is configured for reading.

### 5.3. Read-Write SimpleEvaluationContext

When a use case genuinely needs data binding within a restricted feature set, you can use:

~~~java
EvaluationContext readWrite =
        SimpleEvaluationContext.forReadWriteDataBinding()
                .build();
~~~

This context uses a property accessor intended for data binding and permits property writes within the scope supported by the accessor. It is still an EvaluationContext for SpEL to evaluate expressions.

The name forReadWriteDataBinding can remind readers of Spring MVC's WebDataBinder or DataBinder. However, this builder only creates a SpEL context with appropriate property access configuration; it does not automatically receive requests, map form fields, create a BindingResult, or run the full MVC validation workflow.

## 6. Spring Framework Data Binding Is a Separate Workflow

Data binding populates external data into a target object based on property names. A data source can be request parameters, form submissions, a map of values, or a data structure supplied by the application.

In Spring MVC, WebDataBinder supports binding request data into a model attribute. The framework typically performs steps such as:

1. Receiving input data from the request or binding source.
2. Identifying target properties based on field names.
3. Converting text values into the required Java types.
4. Applying allowed/disallowed field rules and binder configuration.
5. Writing values into the target object if binding succeeds.
6. Collecting binding errors and validation results for the controller to handle.

Example of a form object:

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

Spring MVC can bind the displayName and age request parameters into ProfileForm when handling a model attribute. The initial age value usually arrives from HTTP as a string; the binder and conversion service are responsible for converting it to Integer.

There is no need to write a SpEL expression like age = ... for the framework to perform that binding. Binding is part of Spring MVC's request-handling workflow.

## 7. WebDataBinder and Validation Example

In a controller, you can configure WebDataBinder to restrict which fields are allowed to be bound:

~~~java
@Controller
public class ProfileController {

    @InitBinder("profileForm")
    void configureProfileBinder(WebDataBinder binder) {
        binder.setAllowedFields("displayName", "age");
    }

    @PostMapping("/profile")
    public String update(
            @Valid @ModelAttribute("profileForm") ProfileForm form,
            BindingResult bindingResult) {

        if (bindingResult.hasErrors()) {
            return "profile-edit";
        }

        return "profile-result";
    }
}
~~~

In the example, the binder allows only the two specified fields. Conversion or validation errors are reflected in BindingResult so the controller can decide how to respond.

This is a responsibility that a standalone SpEL assignment does not provide automatically. SpEL can write properties if the context allows it, but it does not automatically apply allowed fields, check validation annotations, create a BindingResult, or coordinate the HTTP response.

For sensitive data, use a dedicated form/DTO and restrict bindable fields. Do not bind all request fields directly onto an entity with many internal properties such as role, status, ownerId, or permission flags.

## 8. Comparing SpEL Assignment with Framework Data Binding

| Aspect | Assignment in SpEL | Spring DataBinder/WebDataBinder |
|---|---|---|
| Purpose | Update a property as part of an expression | Map input data into an object |
| How it is triggered | Evaluating an Expression or calling Expression.setValue | The framework or application invokes the binding workflow |
| Value source | Literals, variables, root object, or expression results | Request parameters, form data, property values, or binding source |
| Property path | Specified by the SpEL expression | Determined by field/property names in the binding data |
| Type conversion | Via EvaluationContext's TypeConverter | Via conversion/property editors and binder configuration |
| Validation | Does not automatically run bean validation | Can integrate Validator and Bean Validation |
| Field control | Via accessors and context configuration | Via allowed/disallowed fields and binder configuration |
| Errors | Usually surface during evaluation or property writing | Collected in BindingResult when using MVC |
| Scope | A specific expression | The framework's binding workflow |

Both mechanisms can mutate an object, yet you should not use a SpEL assignment to replace MVC's binding workflow. Conversely, DataBinder is not a parser for evaluating arbitrary SpEL expressions.

## 9. Type Conversion Is Not Equivalent to Validation

When assigning a property with SpEL, EvaluationContext's TypeConverter can convert the value if needed and if supported by a converter. For example, an expression's value can be converted to the target property's type.

DataBinder also has type conversion mechanisms, yet it can additionally record binding errors and integrate validation. Both mechanisms may share Spring's conversion components, but their error-handling and business-rule checking workflows are not the same.

Distinguish three activities:

- Conversion: transforming a value from a source type to a target type.
- Binding: mapping a source value to a specific property of an object.
- Validation: checking whether an object or field satisfies business rules.

A successful assignment does not prove the object is valid. For example, assigning age = -5 can succeed if the property is an Integer, yet the data can still violate the application's age rule. Validation must be performed explicitly after data is updated.

## 10. Side Effects and Write Permissions

Assignment in SpEL is a state-mutating action. If an expression is evaluated multiple times, the same assignment may be executed multiple times. If the root object is shared, changes can affect other places using that object.

Example:

~~~text
account.balance = 0
~~~

If the context permits writing, the expression can change balance as soon as it is evaluated. This is not a pure check.

For expressions taken from editable configuration or from users, restrict:

1. Root objects to contain only necessary properties.
2. Property accessors to allow only required operations.
3. Not providing objects containing services/repositories capable of writing data unless necessary.
4. Preferring read-only contexts for filtering and display expressions.
5. Not using user-supplied expressions to update entities directly.
6. Performing authorization and validation in the application/service layer before saving changes.

If data must be updated from a request, use a DTO, a configured binder, and appropriate validation. If a value needs to be computed or assigned in a controlled internal rule, SpEL assignment can be used with a clearly scoped context.

## 11. When Should Each Approach Be Used?

### Use SpEL assignment when

- An internal expression needs to update a specific property on a provided object.
- The assigned value is determined by the expression itself.
- The context and property accessors are controlled.
- A full request binding or validation workflow is not required.

Example:

~~~java
Expression assignment = parser.parseExpression(
        "displayName = #normalizedName"
);

StandardEvaluationContext context =
        new StandardEvaluationContext(profile);

context.setVariable("normalizedName", "Lan Nguyen");

assignment.getValue(context);
~~~

### Use Expression.setValue when

- Java already has the new value and only needs to write it to a property path.
- You want to separate the data value from the expression string.
- You need an API that explicitly expresses a property write operation.

~~~java
parser.parseExpression("displayName")
        .setValue(context, normalizedName);
~~~

### Use DataBinder or WebDataBinder when

- Data comes from an HTTP form, request parameters, or a binding source.
- Field-based type conversion is needed.
- Bindable fields need to be restricted.
- Binding errors need to be collected and combined with validation.
- Spring MVC's request-handling lifecycle needs to be followed.

Choose the mechanism according to the data source and the application layer's responsibility, not merely because both can invoke setters.

## 12. Common Errors

| Symptom | Common Cause | How to Resolve |
|---|---|---|
| SpEL assignment does not change property | Expression was only parsed and not evaluated | Call getValue(context) or setValue(context, value) |
| Error saying property cannot be written | Property has no setter or accessor is read-only | Check property accessors and context |
| Used = when intending to compare | Confused assignment with equality | Use == for comparison |
| SimpleEvaluationContext does not allow writing | Using a read-only builder | Use forReadWriteDataBinding only when writing is genuinely needed |
| Expecting SpEL to run Bean Validation automatically | Confused assignment with binding workflow | Invoke validation in the application flow |
| Request field is not updated | Binder disallows the field or field name does not match | Check allowed fields and property names |
| External input modifies sensitive fields | Binding directly to an object with too many properties | Use a form DTO and a field allowlist |
| Assignment succeeds but data is invalid | Conversion is not equivalent to validation | Validate the object after updating |

## 13. Key Takeaways

The = operator in SpEL writes a value to a property when the expression is evaluated and EvaluationContext permits writing. Expression.setValue also writes a property while separating the property path from the new value. The == sign is used for comparison and does not mutate the object.

DataBinder/WebDataBinder is Spring's binding workflow: receiving source data, mapping properties, converting types, controlling fields, and optionally integrating validation. SimpleEvaluationContext.forReadWriteDataBinding() is still only a way to configure property access for a SpEL EvaluationContext, not a WebDataBinder workflow.

Use SpEL assignment for small, controlled expression updates. Use DataBinder/WebDataBinder for input data requiring binding, error handling, and validation. For every write operation, clearly identify which object is modified, who is allowed to modify it, and where validation is performed.