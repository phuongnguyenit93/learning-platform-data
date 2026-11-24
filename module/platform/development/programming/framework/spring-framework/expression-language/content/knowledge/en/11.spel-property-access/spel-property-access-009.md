# Controlling Accessible Properties via PropertyAccessor in Spring Expression Language (SpEL)

In SpEL, expressions can read or write properties of the root object. The **PropertyAccessor** mechanism determines whether a property name can be accessed on an object, how its value is retrieved, and whether writing is permitted.

PropertyAccessor is an important extension point when an application wants to represent data in a custom way, provide virtual properties, or restrict which fields expressions are allowed to see. For example, a Customer object may not have a displayName getter, yet SpEL can still read the displayName property through a custom accessor.

This lesson covers the role of PropertyAccessor, its API contract, registering it into an EvaluationContext, accessor selection order, controlling read/write permissions, and security considerations when evaluating expressions.

## 1. Where does PropertyAccessor fit in the SpEL workflow?

When SpEL encounters a property-access expression such as:

~~~text
name
customer.email
address.city
~~~

SpEL needs to determine the target object, the property name, and how to read the value. This is performed through the list of PropertyAccessors attached to the EvaluationContext.

General workflow:

1. The parser parses the string and creates an Expression object.
2. During evaluation, SpEL determines the target object and the property name to access.
3. SpEL sequentially asks the PropertyAccessors in the EvaluationContext which accessor can read or write that property.
4. The matching accessor performs the read or write operation.
5. The value is returned to expression evaluation.

For example, with the expression name and a Customer root object, SpEL looks for an accessor that can handle the name property on the Customer object. The accessor may use a getter, read a field, access a Map, or compute a virtual value.

PropertyAccessor does not parse expression syntax. It participates in the evaluation phase, when SpEL needs to access a specific property.

## 2. The PropertyAccessor interface

PropertyAccessor belongs to the org.springframework.expression package. This interface defines the target objects the accessor supports and the property read/write operations.

Key methods:

| Method | Role |
|---|---|
| getSpecificTargetClasses() | Declares the target types handled by the accessor. Returns null if the accessor applies to all target types. |
| canRead(context, target, name) | Checks whether the accessor can read property name on target. |
| read(context, target, name) | Reads the property value and returns a TypedValue. |
| canWrite(context, target, name) | Checks whether the accessor can write the property. |
| write(context, target, name, newValue) | Writes a new value into the property. |

General signature:

~~~java
public interface PropertyAccessor {

    Class<?>[] getSpecificTargetClasses();

    boolean canRead(
            EvaluationContext context,
            Object target,
            String name) throws AccessException;

    TypedValue read(
            EvaluationContext context,
            Object target,
            String name) throws AccessException;

    boolean canWrite(
            EvaluationContext context,
            Object target,
            String name) throws AccessException;

    void write(
            EvaluationContext context,
            Object target,
            String name,
            Object newValue) throws AccessException;
}
~~~

Related types:

- **EvaluationContext** provides the current evaluation environment, including the root object, variables, converters, and list of accessors.
- **TypedValue** wraps the read value along with optional type information.
- **AccessException** represents an error during property checking, reading, or writing.

If an accessor does not support a property, canRead or canWrite returns false. If the accessor accepted responsibility for handling it but the actual operation fails, it can throw AccessException to signal an error to SpEL.

## 3. getSpecificTargetClasses and scope of applicability

getSpecificTargetClasses() lets an accessor declare the object types it is designed to handle.

For example, an accessor exclusively for Customer:

~~~java
@Override
public Class<?>[] getSpecificTargetClasses() {
    return new Class<?>[] { Customer.class };
}
~~~

SpEL can use this information to select an accessor matching the target object. If an accessor handles multiple types, return an array containing those types.

If an accessor can genuinely handle any target type, the method may return null. However, do not declare a global scope if the accessor only understands a few object types. A specific scope prevents the accessor from being queried on incompatible objects.

Inside canRead, read, canWrite, and write, you must still validate the target and property name before operating. Do not rely solely on getSpecificTargetClasses() to skip input validation.

## 4. canRead and read: controlling read access

The two methods canRead and read have distinct responsibilities:

- canRead answers whether the accessor supports reading this property on the current target.
- read performs the value retrieval and returns a TypedValue.

Typically, canRead checks both the object type and the property name. Example:

~~~java
@Override
public boolean canRead(
        EvaluationContext context,
        Object target,
        String name) {

    return target instanceof Customer
            && "displayName".equals(name);
}
~~~

If target is a Customer and the property name is displayName, the accessor handles it. For any other name or target type, it returns false so SpEL can try the next accessor.

The read method retrieves the value:

~~~java
@Override
public TypedValue read(
        EvaluationContext context,
        Object target,
        String name) throws AccessException {

    if (!canRead(context, target, name)) {
        throw new AccessException("Unsupported property: " + name);
    }

    Customer customer = (Customer) target;
    String displayName =
            customer.getFirstName() + " " + customer.getLastName();

    return new TypedValue(displayName);
}
~~~

TypedValue can hold null if the property has a null value. When explicit type information needs to be supplied, the corresponding TypeDescriptor APIs can be used.

An accessor should be consistent between canRead and read: if canRead returns true for a target/property pair, read must know how to handle that pair or report a specific error.

## 5. canWrite and write: controlling write access

Reading and writing are two separate permissions. A property may be readable without being modifiable.

- canWrite checks whether the property can accept a new value.
- write performs the value assignment.

For example, displayName is computed from firstName and lastName, so it is read-only. The alias property can be allowed for reading and updating.

~~~java
@Override
public boolean canWrite(
        EvaluationContext context,
        Object target,
        String name) {

    return target instanceof Customer
            && "alias".equals(name);
}
~~~

Implementing write:

~~~java
@Override
public void write(
        EvaluationContext context,
        Object target,
        String name,
        Object newValue) throws AccessException {

    if (!canWrite(context, target, name)) {
        throw new AccessException("Property is read-only: " + name);
    }

    if (newValue != null && !(newValue instanceof String)) {
        throw new AccessException("alias must be a String");
    }

    Customer customer = (Customer) target;
    customer.setAlias((String) newValue);
}
~~~

In the example, alias only accepts String or null. If the application needs type conversion, the accessor can use TypeConverter from EvaluationContext and validate the target type before writing.

Do not allow writing simply because a property is readable. A read allowlist and a write allowlist may differ depending on business requirements.

## 6. Complete example: creating virtual properties and writable properties

Suppose Customer stores firstName, lastName, and alias. The application wants SpEL to access displayName as a virtual property while allowing alias to be updated.

Domain class:

~~~java
public class Customer {

    private final String firstName;
    private final String lastName;
    private String alias;

    public Customer(String firstName, String lastName, String alias) {
        this.firstName = firstName;
        this.lastName = lastName;
        this.alias = alias;
    }

    public String getFirstName() {
        return firstName;
    }

    public String getLastName() {
        return lastName;
    }

    public String getAliasValue() {
        return alias;
    }

    public void setAlias(String alias) {
        this.alias = alias;
    }
}
~~~

Custom accessor:

~~~java
import org.springframework.expression.AccessException;
import org.springframework.expression.EvaluationContext;
import org.springframework.expression.PropertyAccessor;
import org.springframework.expression.TypedValue;

public class CustomerPropertyAccessor implements PropertyAccessor {

    @Override
    public Class<?>[] getSpecificTargetClasses() {
        return new Class<?>[] { Customer.class };
    }

    @Override
    public boolean canRead(
            EvaluationContext context,
            Object target,
            String name) {

        return target instanceof Customer
                && ("displayName".equals(name) || "alias".equals(name));
    }

    @Override
    public TypedValue read(
            EvaluationContext context,
            Object target,
            String name) throws AccessException {

        if (!canRead(context, target, name)) {
            throw new AccessException("Unsupported property: " + name);
        }

        Customer customer = (Customer) target;

        if ("displayName".equals(name)) {
            return new TypedValue(
                    customer.getFirstName() + " " + customer.getLastName()
            );
        }

        return new TypedValue(customer.getAliasValue());
    }

    @Override
    public boolean canWrite(
            EvaluationContext context,
            Object target,
            String name) {

        return target instanceof Customer && "alias".equals(name);
    }

    @Override
    public void write(
            EvaluationContext context,
            Object target,
            String name,
            Object newValue) throws AccessException {

        if (!canWrite(context, target, name)) {
            throw new AccessException("Property is read-only: " + name);
        }

        if (newValue != null && !(newValue instanceof String)) {
            throw new AccessException("alias must be a String");
        }

        ((Customer) target).setAlias((String) newValue);
    }
}
~~~

Registering the accessor and evaluating:

~~~java
import java.util.Collections;

import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

Customer customer = new Customer("An", "Nguyen", "an01");

StandardEvaluationContext context =
        new StandardEvaluationContext(customer);

// This list only allows properties provided by the custom accessor.
context.setPropertyAccessors(
        Collections.singletonList(new CustomerPropertyAccessor())
);

ExpressionParser parser = new SpelExpressionParser();

Expression displayName = parser.parseExpression("displayName");
String display = displayName.getValue(context, String.class);

// display = "An Nguyen"

Expression alias = parser.parseExpression("alias");
alias.setValue(context, "premium");

String currentAlias = alias.getValue(context, String.class);

// currentAlias = "premium"
~~~

In this example:

- displayName does not need a getter of the same name in Customer; the accessor computes the value from firstName and lastName.
- alias is read via getAliasValue and updated via setAlias.
- canWrite only permits writing alias.
- displayName is a read-only property.
- setPropertyAccessors replaces the context's accessor list with the specified list. Therefore, other properties not supported by the custom accessor will not have the default reflective accessor to handle them.

This code demonstrates how to control the set of properties visible to an expression. If the application wants to retain standard Java property access, configure additional appropriate accessors in the list.

## 7. Registering PropertyAccessor in EvaluationContext

A PropertyAccessor does not automatically apply to every expression. It must be registered in the EvaluationContext used during evaluation.

### 7.1. StandardEvaluationContext

StandardEvaluationContext supports registering custom accessors:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(customer);

context.addPropertyAccessor(new CustomerPropertyAccessor());
~~~

addPropertyAccessor appends the accessor to the existing list. This is the way to extend it when the accessor handles a new property unknown to default accessors.

If you need to control the order or replace the entire list, use setPropertyAccessors:

~~~java
context.setPropertyAccessors(Arrays.asList(
        new CustomerPropertyAccessor(),
        new ReflectivePropertyAccessor()
));
~~~

The supplied list determines which accessors are used and the order in which they are tried. When a custom accessor needs priority over a property also supported by the reflective accessor, place the custom accessor before the reflective accessor.

If you use setPropertyAccessors, remember that you are replacing the current list. Omitting default accessors can change which properties existing expressions can access.

### 7.2. SimpleEvaluationContext

SimpleEvaluationContext is appropriate when you want to restrict SpEL's feature set, such as in data binding or user-configured expressions.

This context allows choosing specific PropertyAccessors via a builder, for example:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forPropertyAccessors(
                new CustomerPropertyAccessor()
        ).build();
~~~

SimpleEvaluationContext does not provide all capabilities of StandardEvaluationContext. It is designed to remove or restrict advanced capabilities such as type references, object instantiation, and bean references; method invocation must also be configured as needed.

If only reading data is needed, choose a read-only configuration. If writing properties is needed, choose a writable mode and provide only accessors that can control that operation.

## 8. Accessor selection order and handling conflicts

An EvaluationContext can contain multiple PropertyAccessors. SpEL must find an accessor that supports the target object and the property being accessed.

For example, a context has:

1. CustomerPropertyAccessor
2. ReflectivePropertyAccessor

If an expression reads displayName on Customer, the custom accessor can handle that virtual property. If the custom accessor returns false from canRead, SpEL can continue trying the subsequent accessor.

If both accessors support the same property, ordering matters. The accessor tried first can decide how the property is read or written. Therefore:

- Place the custom accessor first when custom interpretation needs priority.
- Keep the reflective accessor after it if standard JavaBean access is still desired.
- Omit the reflective accessor when you want to allow only an application-defined list of properties.
- Avoid having two accessors claim support for the same property if they read/write differently without clear precedence rules.

canRead and canWrite should return true only for properties the accessor genuinely controls. Do not return true too broadly and let read or write handle unrelated cases.

## 9. ReflectivePropertyAccessor and custom accessors

Spring supplies ReflectivePropertyAccessor to access Java properties via reflection. This is the accessor commonly used in StandardEvaluationContext and supports appropriate JavaBean properties via getters, setters, or fields according to its rules.

The reflective accessor is useful when expressions need to access standard Java properties:

~~~text
name
address.city
account.balance
~~~

A custom accessor is appropriate when:

- The property does not exist directly on the Java class, but can be computed or fetched from another source.
- Property names in expressions need to map to a custom data structure.
- Only a specific set of properties is allowed to appear in expressions.
- Read permissions and write permissions differ.
- The application needs to control returned data, normalize values, or apply custom conversion rules.

You can combine a custom accessor with ReflectivePropertyAccessor. This lets the application extend access for certain properties while keeping standard JavaBean properties.

## 10. Using PropertyAccessor to build a property allowlist

An important purpose of PropertyAccessor is restricting which properties an expression can access.

For example, a configuration rule is only allowed to read:

~~~text
customerName
accountStatus
creditLimit
~~~

The application can create an accessor supporting strictly those three names. Other properties return false from canRead and cannot be accessed if no other accessor handles them.

To truly restrict the property set:

1. Select specific target types in getSpecificTargetClasses.
2. Check exact property names in canRead and canWrite.
3. Implement read or write only for allowed properties.
4. Configure the accessor list so that no broader accessor accidentally re-opens blocked properties.
5. Also verify method invocation permissions and other SpEL features enabled in the context.

If you only add an allowlist accessor to StandardEvaluationContext while keeping ReflectivePropertyAccessor, properties rejected by the allowlist accessor can still be accessed by the reflective accessor. Therefore, to truly restrict access, you must control the entire list of accessors in use.

## 11. Error handling and value conversion

When writing a custom accessor, handle the following cases:

- Null target or wrong target type.
- Unsupported property name.
- Property has no value.
- New value has an incompatible type.
- Error accessing the underlying data source.
- Property is read-only, yet the expression requests a write.

AccessException is used to report errors at the property-access layer. SpEL can translate this error into an expression evaluation error. Therefore, application code should handle errors at the appropriate evaluation boundary.

If the accessor needs type conversion, use TypeConverter from EvaluationContext. Do not perform arbitrary casts when data may come from external expressions or configuration sources.

For example, if the alias property only accepts String, the accessor should clearly define behavior for null and non-String types. Conversion rules must match the application's data contract.

## 12. Security considerations when permitting property access

PropertyAccessor directly affects what data expressions can read and modify. If expressions are user-supplied or come from untrusted sources, registering an overly broad accessor can expose data or allow unintended state mutations.

Some principles:

1. **Restrict target types:** support only the necessary classes.
2. **Use a property-name allowlist:** allow only properties required by business rules.
3. **Separate read and write permissions:** allow write only for properties permitted to change.
4. **Be cautious with reflection:** ReflectivePropertyAccessor can expand the attack surface to regular Java properties.
5. **Control method access:** PropertyAccessor does not control all method invocations. If method invocation remains enabled, expressions can reach behavior beyond the property set.
6. **Choose an appropriate EvaluationContext:** consider SimpleEvaluationContext when full features of StandardEvaluationContext are unnecessary.
7. **Do not treat an accessor as a complete sandbox:** also restrict the root object, variables, functions, method resolvers, type locators, bean resolvers, and other features exposed to expressions.

PropertyAccessor is an important control layer, but security policy must encompass all capabilities of the EvaluationContext.

## 13. Common mistakes

| Error | Cause | Resolution |
|---|---|---|
| Property not found | No accessor supports the target and property name. | Check canRead, target type, and accessor list. |
| Accessor not called | Another accessor earlier in the list already handled the property. | Check list order and use setPropertyAccessors when needed. |
| canRead returns true but read fails | Checks in canRead do not fully reflect read conditions. | Align conditions between canRead and read. |
| Property is readable but not writable | canWrite returns false or write is not implemented. | Check write permissions separately. |
| Writing wrong type | Accessor does not validate or convert newValue. | Check type or use TypeConverter. |
| Blocked property is still accessible | Another accessor, such as the reflective accessor, still permits access. | Control the entire accessor list. |
| Using accessor for every target | getSpecificTargetClasses returns null or scope is too broad. | Declare specific target types whenever possible. |
| Assuming PropertyAccessor blocks all behavior | Method calls and other SpEL features lie outside the accessor's scope. | Restrict EvaluationContext and relevant resolvers. |

## 14. Key takeaways

- PropertyAccessor determines how SpEL reads or writes properties on a target object.
- canRead and canWrite check capability; read and write perform the operation.
- read returns TypedValue; access errors can be reported with AccessException.
- getSpecificTargetClasses declares the target types supported by the accessor.
- StandardEvaluationContext allows adding or replacing the accessor list.
- Accessor ordering matters when multiple accessors support the same property.
- ReflectivePropertyAccessor handles regular Java properties; custom accessors extend or restrict access.
- To enforce a true allowlist, control the entire accessor list so no broader accessor re-opens blocked properties.
- PropertyAccessor only controls property access; additional EvaluationContext features must be restricted when handling untrusted expressions.
