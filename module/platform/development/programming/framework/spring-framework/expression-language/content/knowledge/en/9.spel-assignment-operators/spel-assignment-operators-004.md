# Conditions for a Property to Be Writable in SpEL

In Spring Expression Language (SpEL), not every expression that can read a value can be used as a write target. To assign a value to a property, SpEL must resolve the target object, find an access mechanism that supports writing, and convert the assigned value to a type the property accepts.

Understanding write conditions helps avoid errors when using the assignment operator or Expression.setValue(...), especially with getter-only JavaBeans, nested objects, immutable classes, custom PropertyAccessor implementations, and differing data types.

## 1. Objectives and Prerequisites

After this lesson, you will be able to:

- Distinguish between readable properties and writable properties.
- Understand the roles of getters, setters, fields, and PropertyAccessor.
- Check writability using Expression.isWritable(...).
- Assign values using Expression.setValue(...) or the = operator in SpEL.
- Handle nested properties and null intermediate objects.
- Understand type conversion during assignment and potential errors.
- Choose an appropriate EvaluationContext for update operations.
- Restrict write permissions to prevent untrusted expressions from unexpectedly modifying objects.

You should know JavaBeans, getters/setters, classes and objects, how to create a SpelExpressionParser, and how to use EvaluationContext.

## 2. Readable Does Not Mean Writable

A property may support reading without supporting writing. For example:

~~~java
public class Person {
    private String name;

    public String getName() {
        return name;
    }
}
~~~

SpEL can read the name property via its getter. However, this class has no setter for name, and the field is not provided as a valid write target by the accessor in use. Therefore, an expression that can read name cannot necessarily assign a value to it.

This is the core difference:

- **Readable:** PropertyAccessor can retrieve the property value from the object.
- **Writable:** PropertyAccessor can write a new value into the object's property.

For a standard JavaBean, the clearest way to provide writability is to have matching getter and setter methods:

~~~java
public class Person {
    private String name;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
~~~

Then the name property is both readable and writable through the default JavaBean accessor.

## 3. PropertyAccessor Determines Writability

SpEL does not assume every property name can be assigned. It uses the PropertyAccessor instances in EvaluationContext to determine how to access the target object.

A PropertyAccessor can support:

- Reading properties.
- Writing properties.
- Both reading and writing.
- Only a specific group of object types or property names.

With StandardEvaluationContext, the default reflective property accessor supports JavaBean properties via getters/setters and fields that the accessor can access. If the application adds a custom PropertyAccessor, writability depends on how that accessor implements the check and write operation.

By contract, a PropertyAccessor must report writability via canWrite(...) and perform the write via write(...). If canWrite returns false for the target and property under evaluation, SpEL cannot use that accessor to write the property.

This means the same object may be writable in one EvaluationContext yet not writable in another context, if the two contexts have different PropertyAccessor configurations.

## 4. Requirements for JavaBean Properties

### 4.1. Having a Matching Setter

For standard JavaBeans, a setter is the most common mechanism for writing a property:

~~~java
public class Account {
    private int age;

    public int getAge() {
        return age;
    }

    public void setAge(int age) {
        this.age = age;
    }
}
~~~

The age property has a getter for reading and a setter for writing. The method name setAge follows the JavaBean convention corresponding to the age property.

Writable example:

~~~java
Account account = new Account();

ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("age");

expression.setValue(account, 30);
~~~

After the operation, account.getAge() returns 30.

### 4.2. Getter-Only Properties

If a class only has a getter:

~~~java
public class Account {
    private final String accountNumber;

    public Account(String accountNumber) {
        this.accountNumber = accountNumber;
    }

    public String getAccountNumber() {
        return accountNumber;
    }
}
~~~

accountNumber is a readable property with no setter. With the standard reflective property accessor, this is not a valid write target. Calling setValue(...) on this property will fail unless another accessor provides write capability.

Do not attempt to modify an immutable class by assuming SpEL will mutate a final field. If an object is designed as immutable, create a new object via a constructor or factory in Java and replace the reference where appropriate.

### 4.3. Accessible Fields

In addition to JavaBean setters, a reflective property accessor can access fields that it is permitted to read or write. Thus, a class with an accessible field can sometimes support writing even without a setter.

However, field access depends on reflection accessibility, field modifiers, module/access restrictions, and the accessor in use. A final field is not a safe or valid write target for normal update operations. In application design, prefer setters or custom accessors with an explicit contract rather than relying on direct field writes.

### 4.4. The Setter Must Accept a Compatible Type

The setter must accept the value after SpEL performs type conversion. For example, if the age property is of type int, the resulting value must be convertible to int.

~~~java
public class Account {
    private int age;

    public int getAge() {
        return age;
    }

    public void setAge(int age) {
        this.age = age;
    }
}
~~~

If the input value cannot be converted to an integer, the write operation will raise a conversion error. In addition, the setter itself may perform validation and throw an exception if the value violates business rules.

## 5. Checking Property Writability with isWritable

Expression provides the isWritable method to check whether an expression can be used as a write target with the current root object and context.

Example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression("name");

Person person = new Person();

if (expression.isWritable(person)) {
    expression.setValue(person, "An");
}
~~~

When using an explicit EvaluationContext:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext(person);

Expression expression = parser.parseExpression("name");

boolean writable =
    expression.isWritable(context, person);

if (writable) {
    expression.setValue(context, person, "An");
}
~~~

isWritable helps check beforehand before writing, especially when property paths are configured dynamically. However, the check result only reflects the context, target object, and state at the time of the check. It does not guarantee that a subsequent write will always succeed: a setter can still throw an exception, data can change, or conversion can fail.

Treat isWritable as an accessibility check, not complete business validation.

## 6. Writing Values with setValue

### 6.1. Writing a Simple Property

Full example:

~~~java
public class Person {
    private String name;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}

ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("name");

Person person = new Person();

if (!expression.isWritable(person)) {
    throw new IllegalStateException("Property name is not writable");
}

expression.setValue(person, "An");

System.out.println(person.getName());
~~~

setValue accepts the target object and the value to assign. SpEL locates the appropriate accessor, performs type conversion if needed, and invokes the corresponding write mechanism.

### 6.2. Writing with EvaluationContext

You can pass a context to control PropertyAccessor and TypeConverter:

~~~java
Person person = new Person();

StandardEvaluationContext context =
    new StandardEvaluationContext(person);

Expression expression = parser.parseExpression("name");

expression.setValue(context, person, "An");
~~~

This approach is useful when the application has custom PropertyAccessor implementations, a custom TypeConverter, or different access configurations for each use case.

### 6.3. Using the Assignment Operator in an Expression

SpEL supports the = assignment operator. Example:

~~~java
Expression assignment =
    parser.parseExpression("name = 'An'");

Object assignedValue = assignment.getValue(person);
~~~

The expression both writes the name property and returns the assigned value. This differs from the equality comparison operator ==.

There are two common ways to operate:

- Parse a property path and call setValue(...): suitable when you want to clearly express the write target and the value supplied from Java.
- Parse an expression containing the = operator: suitable when the assignment is part of a configured expression.

In applications, setValue is usually easier to control because Java code explicitly shows the target property and input value.

## 7. Conditions When Writing Nested Properties

A property path can consist of multiple levels:

~~~text
address.city
~~~

To write city, SpEL must traverse address first. Therefore:

1. The root object must exist.
2. The intermediate property address must be readable to obtain the Address object.
3. The Address object must exist, or the parser must be configured to auto grow null references and have sufficient information to create it.
4. The final property city must be writable via a suitable accessor.
5. The assigned value must be convertible to the type of city.

Example:

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

public class Person {
    private Address address;

    public Address getAddress() {
        return address;
    }

    public void setAddress(Address address) {
        this.address = address;
    }
}
~~~

If address is already initialized:

~~~java
Person person = new Person();
person.setAddress(new Address());

Expression expression =
    parser.parseExpression("address.city");

expression.setValue(person, "Da Nang");
~~~

If address is null, the expression cannot proceed in the normal way. You can enable auto grow null references:

~~~java
SpelParserConfiguration configuration =
    new SpelParserConfiguration(true, false);

ExpressionParser configuredParser =
    new SpelExpressionParser(configuration);

Expression expression =
    configuredParser.parseExpression("address.city");

Person person = new Person();
expression.setValue(person, "Da Nang");
~~~

Instantiation capability also depends on whether the Address type can be constructed at runtime. If Address is an interface, abstract class, or requires constructor arguments that SpEL has no way to supply, auto grow cannot automatically infer a suitable instance.

## 8. SimpleEvaluationContext and Write Permissions

StandardEvaluationContext provides broad reflection, method, type, and bean access depending on configuration. In use cases that only need data binding, SimpleEvaluationContext helps limit capabilities.

Example of a context allowing property reads and writes via the data-binding accessor:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadWriteDataBinding().build();
~~~

Read-only context:

~~~java
SimpleEvaluationContext readOnlyContext =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();
~~~

With a read-only context, properties can be read, while write operations are not permitted. With a read-write context, properties supported by the data-binding accessor can be written.

The choice of context should accurately reflect the use case:

- Displaying or checking data only: prefer read-only.
- Updating a DTO via controlled expressions: consider read-write data binding.
- Needing custom accessors or resolvers: explicitly configure each required capability.
- Do not evaluate untrusted expressions with a broadly privileged context.

## 9. Type Conversion and Validation During Writing

A property may be writable, yet the input value may still be invalid. SpEL uses EvaluationContext's TypeConverter to convert the value to the target type when necessary.

For example, the age property has type int, while the supplied value is the string "30". If the conversion service in use supports this conversion, the assignment can succeed. If the string is "thirty", conversion will fail.

Distinguish three layers of checking:

1. **Writable check:** can the accessor write the property?
2. **Type conversion:** can the value be converted to the property type?
3. **Business validation:** is the value valid according to application rules?

For example, age can convert into an integer yet still be invalid if negative. SpEL does not automatically know business age limits; validate in the setter, DTO validation, or corresponding service.

If the setter throws an exception, that error can surface during evaluate/setValue. Catch and handle it at the appropriate boundary, and do not hide the cause by ignoring all write errors.

## 10. Collections, Maps, and Indexed Properties

Properties are not the only write targets in SpEL. With an accessor supporting them, expressions can also write elements by index or key.

List example:

~~~text
items[0]
~~~

Map example:

~~~text
settings['theme']
~~~

These targets have their own conditions:

- A List needs a valid index, or the parser must be configured to auto grow collections when the use case allows it.
- A Map must support key access and allow adding or replacing values according to the accessor.
- An Array has a fixed size; an array cannot grow automatically like a List.
- Nested elements may be null, requiring intermediate objects to exist or appropriate auto grow null references configuration.

Do not infer that because a JavaBean property is writable, every collection element inside it is also writable. Check the exact target expression with isWritable using the actual object and context.

## 11. Custom PropertyAccessor

When an object does not follow JavaBean conventions or the application needs to restrict writable properties, you can implement a custom PropertyAccessor.

The accessor needs to define:

- Which target types it supports.
- Which property names can be read.
- Which property names can be written.
- How to retrieve the value.
- How to update the value.
- How to report errors when a property is invalid or a value is inappropriate.

In principle, canWrite(...) should return true only for cases the accessor can genuinely update. write(...) performs the update after SpEL selects the accessor.

Design example: a configuration DTO only allows updating displayName and enabled. A custom accessor can reject all other property names, even if the target object has additional internal fields. This creates an explicit allowlist for data permitted to be modified.

After registering the accessor in EvaluationContext, check isWritable for allowed and disallowed properties, then test both successful writes and failures.

## 12. Common Errors and Diagnostics

| Symptom | Common Cause | How to Resolve |
|---|---|---|
| Property is readable but setValue fails | Has getter without setter or accessor only supports reading | Add an appropriate setter or use an accessor that supports writing |
| isWritable returns false | Context lacks a write accessor for target/property | Check PropertyAccessor and EvaluationContext type |
| Cannot write nested property | Intermediate object is null or unreadable | Initialize the object or configure auto grow appropriately |
| Type conversion error | Value cannot be converted to the target type | Pass the right type or configure a controlled TypeConverter |
| Setter throws an exception | Validation or logic inside setter rejects the value | Check business conditions and handle the error clearly |
| Immutable property cannot be updated | No setter or field is not writable | Create a new object and replace the reference |
| SimpleEvaluationContext does not allow writing | Using read-only data binding | Choose a read-write context if the use case is permitted to update |
| Unexpected properties are writable | Context/accessor grants overly broad permissions | Use a small DTO and a property allowlist |

When debugging, check in order: root object, property path, isWritable, accessor, intermediate objects, conversion, and setter validation. This approach helps distinguish permission/write errors from data errors.

## 13. Safety When Allowing Writes with SpEL

Writing a property is a side effect: the object in memory changes after the expression is evaluated. If the expression comes from a request or externally controlled configuration, allowing arbitrary writes can cause unwanted state changes.

Apply these principles:

- Allow only properties on an allowlist.
- Use small DTOs, avoiding passing entity graphs or sensitive services as the root object.
- Prefer SimpleEvaluationContext with minimal data-binding capabilities.
- Do not enable method resolvers, bean resolvers, or type/constructor access unless needed.
- Validate values before saving them into the system.
- Do not share mutable objects being updated across multiple requests without synchronization.
- Log enough for diagnostics while avoiding exposing sensitive data.
- Do not use untrusted expressions to arbitrarily update properties.

In particular, isWritable is not a security mechanism. It only indicates whether the expression can write with the current accessor/context; granted permissions must still be restricted via context design and input validation.

## 14. Practice Exercises

1. Create a Person class with name having a getter and setter. Parse the expression name, check isWritable, and then call setValue.
2. Remove the setter for name and observe isWritable along with the error when writing.
3. Create an Account class with age of type int. Assign a convertible string value, then try an invalid string.
4. Create a property address.city with address initially null. Try writing with auto grow disabled and enabled.
5. Create read-only and read-write SimpleEvaluationContext instances, and compare reading and writing capabilities.
6. Create a custom PropertyAccessor that allows only displayName and enabled.
7. Try assigning a property outside the allowlist and verify that the accessor rejects it.
8. Write tests for setter validation, null intermediate, conversion failure, and immutable property.

## 15. Checklist Before Writing a Property

- [ ] Do the root object and property path exist?
- [ ] Does the final property have a setter or valid write mechanism?
- [ ] Does the current PropertyAccessor support write?
- [ ] Are intermediate properties readable and do intermediate objects already exist?
- [ ] If using auto grow, can the object type be instantiated?
- [ ] Is the assigned value convertible to the target type?
- [ ] Does the setter or business layer have appropriate validation?
- [ ] Has isWritable been checked with the right context and target?
- [ ] Does the EvaluationContext grant only the necessary write permissions?
- [ ] Could the expression cause unexpected state changes?

## 16. Conclusion

A property is writable only when EvaluationContext has a PropertyAccessor that supports writing for that target and property. For standard JavaBeans, a setter is the common mechanism; accessible fields or custom accessors can also provide writability. For safe updates, check isWritable, use setValue with an appropriate context, ensure intermediate objects exist, and handle type conversion and validation. With untrusted input, restrict writable properties and prefer a least-privilege data-binding context.