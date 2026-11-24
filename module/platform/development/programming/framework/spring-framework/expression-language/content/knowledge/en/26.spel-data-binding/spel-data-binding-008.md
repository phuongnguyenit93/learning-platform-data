# Restricting Writable Properties

## Objective

After this lesson, you will be able to restrict which properties Spring Expression Language (SpEL) expressions are allowed to modify; distinguish read permissions from write permissions; choose DataBindingPropertyAccessor or a custom PropertyAccessor; and design an allowlist for updatable properties. You will also know how to distinguish assignment in expressions from Java's setValue API, handle nested properties, and test rejected write operations.

## 1. Why Restrict Writable Properties?

SpEL can read properties and, depending on the EvaluationContext, modify properties of an object. For example:

~~~text
displayName = 'An'
~~~

If the expression is evaluated on a JavaBean with a public setter for displayName and the context allows writing, the object's value can be changed.

Broad write permissions can create risk when expressions come from configuration, users, or a source not fully controlled by the application. An expression could unintentionally overwrite important state such as role, ownerId, balance, status, or fields used in authorization.

Not every property should be writable merely because the JavaBean provides a setter. The application must clearly define:

- Which properties are allowed to be read.
- Which properties are allowed to be written.
- Which objects or data types are allowed to be accessed.
- Which write operations must go through a service to enforce validation and business rules.

An important principle is to grant only the minimum permissions an expression needs. If an expression is only used for filtering or calculation, a read-only context is usually the right choice.

## 2. PropertyAccessor Determines Read and Write Capabilities

SpEL uses PropertyAccessor to access object properties. An accessor can support reading, writing, or both.

The main methods of PropertyAccessor include:

- `canRead(...)`: indicates whether the accessor can read the requested property.
- `read(...)`: reads the property value.
- `canWrite(...)`: indicates whether the accessor can write the property.
- `write(...)`: writes the value into the property.

When evaluating a property-reading expression, SpEL locates a matching accessor and calls the read operation. When an expression requests a write, SpEL needs an accessor that supports writing and the target property must be updatable.

For example:

~~~text
customer.displayName
~~~

is a normal read access.

~~~text
customer.displayName = 'An'
~~~

is a write operation on displayName. Being able to read a property does not mean the accessor also allows writing that property.

This is an important control point: write-permission policy can be enforced in the accessor instead of relying on expression authors remembering to avoid sensitive properties.

## 3. Read-Only and Read-Write Data Binding

SimpleEvaluationContext provides factories to configure data binding in two modes.

Read-only context:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();
~~~

Read-and-write context:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadWriteDataBinding().build();
~~~

The two configurations use DataBindingPropertyAccessor with different permissions:

| Configuration | Read Property | Write Property |
|---|---|---|
| forReadOnlyDataBinding() | Yes | No |
| forReadWriteDataBinding() | Yes | Yes, if the property supports writing |

DataBindingPropertyAccessor is designed for data binding and accesses eligible public properties. It does not open all reflection access capabilities of StandardEvaluationContext. Certain sensitive types or properties, such as properties related to Class and ClassLoader, are restricted by the accessor's design.

However, read-write mode can still allow writing many public properties of the supplied object. If you only want to allow a small set of properties, use a custom PropertyAccessor with an allowlist instead of treating read-write data binding as a per-field authorization policy.

## 4. Assigning Properties via Expressions

When the context supports assignment and the accessor allows writing, SpEL can assign properties using the equals operator:

~~~text
displayName = 'An'
~~~

Java example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("displayName = 'An'");

Profile profile = new Profile();

EvaluationContext context =
    SimpleEvaluationContext.forReadWriteDataBinding().build();

expression.getValue(context, profile);
~~~

The expression is evaluated with profile as the root object. SpEL finds the displayName property and uses the accessor to write the value.

If the context was created with forReadOnlyDataBinding(), the assignment operation is not accepted. If the accessor does not permit writing displayName, the operation is also rejected even if the object has a public setter.

The exact outcome also depends on property type and value conversion capability. If the property is String and the expression produces a String, no complex conversion is needed. If types do not match, a TypeConverter may be required before the accessor writes the value.

## 5. Assigning via Expression.setValue()

Besides the assignment operator inside a SpEL string, Java code can request writing a property through the Expression.setValue() API:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("displayName");

Profile profile = new Profile();

EvaluationContext context =
    SimpleEvaluationContext.forReadWriteDataBinding().build();

expression.setValue(context, profile, "An");
~~~

In this example, the expression only identifies the displayName property. Java code calls setValue to write the value into that property.

Both assignment in an expression and setValue require an accessor with write capability. Therefore, an allowlist properly implemented in a PropertyAccessor can control both write paths.

Distinguish the accessor's write permission from the flag allowing assignment in expressions. SimpleEvaluationContext's builder may support withAssignmentDisabled() in corresponding Spring versions to disable the assignment operator in expressions. That flag restricts assignment syntax; the accessor's canWrite policy remains what controls which properties are permitted to be written through property access.

Do not use disabling assignment as a replacement for a property allowlist if the application still calls setValue from Java.

## 6. Restricting Writes with an Allowlist

If the application only wants to allow updating displayName while forbidding updates to role, balance, and ownerId, you can create a custom PropertyAccessor.

Idea of an allowlist:

| Property | Read | Write |
|---|---|---|
| displayName | Allowed | Allowed |
| locale | Allowed | Allowed if business logic requires |
| role | Allowed or restricted | Denied |
| balance | Allowed or restricted | Denied |
| ownerId | Allowed or restricted | Denied |
| passwordHash | Denied or provided only via dedicated API | Denied |

The allowlist should clearly specify read permissions and write permissions separately. A property may need to be read for display or condition checking while not being allowed to be modified through SpEL.

In a custom accessor:

- `canRead(...)` returns true only for properties permitted to be read.
- `read(...)` returns values only for approved properties.
- `canWrite(...)` returns true only for properties in the write allowlist.
- `write(...)` performs the update and rejects any property name outside the allowlist.

Do not check property names only in the UI or in the expression string. The final decision should be enforced in the accessor because every expression goes through this mechanism when accessing properties.

## 7. Custom PropertyAccessor Example

The example below illustrates an accessor for a Profile. The accessor allows reading displayName and role, but only allows writing displayName.

~~~java
import org.springframework.expression.AccessException;
import org.springframework.expression.EvaluationContext;
import org.springframework.expression.PropertyAccessor;
import org.springframework.expression.TypedValue;

public class ProfilePropertyAccessor implements PropertyAccessor {

    @Override
    public Class<?>[] getSpecificTargetClasses() {
        return new Class<?>[] { Profile.class };
    }

    @Override
    public boolean canRead(
            EvaluationContext context, Object target, String name) {
        return target instanceof Profile
            && ("displayName".equals(name) || "role".equals(name));
    }

    @Override
    public TypedValue read(
            EvaluationContext context, Object target, String name)
            throws AccessException {

        Profile profile = (Profile) target;

        if ("displayName".equals(name)) {
            return new TypedValue(profile.getDisplayName());
        }

        if ("role".equals(name)) {
            return new TypedValue(profile.getRole());
        }

        throw new AccessException("Property is not readable: " + name);
    }

    @Override
    public boolean canWrite(
            EvaluationContext context, Object target, String name) {
        return target instanceof Profile
            && "displayName".equals(name);
    }

    @Override
    public void write(
            EvaluationContext context,
            Object target,
            String name,
            Object newValue) throws AccessException {

        if (!canWrite(context, target, name)) {
            throw new AccessException("Property is not writable: " + name);
        }

        if (!(newValue instanceof String)) {
            throw new AccessException("displayName must be a String");
        }

        Profile profile = (Profile) target;
        profile.setDisplayName((String) newValue);
    }
}
~~~

Registering the accessor with SimpleEvaluationContext:

~~~java
EvaluationContext context =
    SimpleEvaluationContext
        .forPropertyAccessors(new ProfilePropertyAccessor())
        .build();
~~~

This example illustrates an allowlist policy. In a real application, the accessor must properly handle permitted null types, type conversion if needed, and any setter errors that may arise.

If there are multiple object types, you can write separate accessors per type or one accessor with explicit rules by target type. Do not create a generic accessor that allows writing every property just because a property name is not on a short blocklist.

## 8. Denylist and Allowlist

There are two common ways to define writable properties:

**Denylist** lists forbidden properties. Remaining properties can be written.

**Allowlist** explicitly lists permitted properties. Any property not on the list is rejected.

| Approach | Default Behavior | Risk |
|---|---|---|
| Denylist | Allow except forbidden fields | New properties added to the model may unintentionally become writable |
| Allowlist | Deny except approved fields | Must update the list when adding new properties |

For sensitive data or expressions coming from external sources, an allowlist is usually easier to control. When new properties are added to the model, write permissions do not expand automatically.

Consider aliases or nested paths as well. If an accessor allows writing a property on a child object, an expression may reach it through multiple paths. Policy must be enforced on the actual target object and property name the accessor receives.

## 9. Nested Properties and Write Permissions at Each Level

A property path can have multiple levels:

~~~text
customer.address.city
~~~

When reading, SpEL retrieves customer, then address, then city. When assigning:

~~~text
customer.address.city = 'Da Nang'
~~~

SpEL must be able to read the intermediate objects and write the final city property.

Permission to write city does not mean every property on customer or address is allowed to be written. The accessor must decide based on each target object and property name it receives.

For example, the application might allow updating address.city while forbidding replacing the entire customer or address. Design the allowlist by specific object type and property, and also control which paths are permitted to appear in expressions.

If an intermediate object is null, reading the path can fail before reaching the final property. Auto-grow can alter behavior in some parser configurations, yet automatic creation of intermediate objects must also be enabled and bounded intentionally. Do not enable auto-grow merely to avoid data errors without reviewing the impact on the object graph.

## 10. Properties with Setters Can Still Be Rejected

A JavaBean having a public setter does not automatically mean every EvaluationContext allows writing.

The following cases can occur:

- A read-only context rejects writing despite a public setter.
- A custom accessor rejects properties not on the allowlist.
- A property has no setter or cannot be updated.
- A property has a target type incompatible with the new value.
- The setter throws an exception due to validation or object state.
- The object or property is not supported by the accessor.

For example, Profile has a setter for role, yet the accessor only permits displayName. When an expression tries to write role, canWrite returns false and SpEL does not perform the update through that accessor.

This is the desired behavior when role is sensitive data. Having the technical capability for an object to mutate does not mean an expression is granted permission to mutate it.

## 11. Conversion Does Not Replace Write Permission or Validation

When assigning a property, SpEL may need a TypeConverter to convert the source value to the target property type. However, these three concerns are independent:

1. **Conversion:** can the value be converted to the property type?
2. **Write permission:** does the accessor allow writing that property?
3. **Validation:** does the new value satisfy business conditions?

For example, the string "25" can convert to Integer 25. Yet if the age property is forbidden from being written via SpEL, the operation must still be rejected. If the age property is allowed to be written, the value 25 may still be invalid under the application's policy.

Do not rely on setters to perform all authorization. Setters should usually protect the object's internal consistency; user permissions and business rules should be checked at the service or appropriate application layer.

## 12. Distinguishing Property Write Permission from Method Invocation Permission

PropertyAccessor controls reading and writing properties. It is not the only mechanism deciding what actions an expression can perform.

An expression can invoke a method on an object if EvaluationContext provides a matching MethodResolver:

~~~text
profile.changeRole('ADMIN')
~~~

Even if the accessor forbids directly writing the role property, the changeRole method can modify role if methods are allowed to be called.

Therefore, restricting property writes is not enough to guarantee an object cannot be mutated. You must also examine:

- Which methods are allowed to be called.
- Whether methods have side effects or mutate state.
- Whether BeanResolver allows accessing sensitive services.
- Whether the root object contains objects with broad permissions.
- Whether registered functions can mutate data.

If the goal is only to let expressions read data, use a read-only context and restrict method resolvers, functions, and bean references as needed. If certain update operations must be allowed, design a narrow API with clear names and effects.

## 13. SimpleEvaluationContext and StandardEvaluationContext

The two context types have different capability scopes:

| Capability | SimpleEvaluationContext | StandardEvaluationContext |
|---|---|---|
| Choose PropertyAccessor | Yes | Yes |
| Read-only data binding | Yes | Configurable |
| Read-write data binding | Yes | Configurable |
| Custom PropertyAccessor | Yes | Yes |
| Method invocation | Only when an appropriate mechanism is enabled | Has default resolvers and customization capability |
| Type references and constructors | Not fully supported | Configurable |
| Bean references | Not supported | Can configure BeanResolver |

SimpleEvaluationContext suits expressions that need a restricted feature set and selected property permissions. StandardEvaluationContext is more flexible, yet requires tight control over resolvers and supplied objects.

If the goal is only writing specific defined properties, a custom PropertyAccessor in SimpleEvaluationContext is usually the clearest way to express the policy. Do not switch to StandardEvaluationContext merely to bypass a permission restriction that the application intentionally established.

## 14. Disabling Assignment in Expressions

Some Spring versions provide a builder configuration to disable assignment in expressions:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext
        .forReadWriteDataBinding()
        .withAssignmentDisabled()
        .build();
~~~

This configuration lets the data binding accessor read and write, while disabling assignment operators in expressions according to the capabilities of the corresponding Spring version.

This is useful when the application wants to allow certain write operations initiated from Java via API, yet does not want expression strings themselves to perform assignment.

Distinguish three layers of control:

- Read-only accessor: forbids writing properties through the accessor.
- Read-write accessor with allowlist: only allows writing approved properties.
- Assignment disabled: blocks assignment syntax in expressions.

If a per-property allowlist is needed, you still must implement appropriate canWrite and write. Disabling assignment does not automatically create a list of writable properties.

Check the Javadoc of the Spring version you use to confirm the builder supports withAssignmentDisabled() before applying it.

## 15. Handling Errors When Property Writing Is Rejected

When an expression tries to write to an unpermitted property, SpEL may throw SpelEvaluationException or an evaluation error related to property writing. If a custom accessor throws AccessException, the cause may be included in SpEL's exception.

At the layer invoking the expression, handle errors intentionally:

~~~java
try {
    expression.getValue(context, profile);
}
catch (EvaluationException ex) {
    // Log the error and convert it into an appropriate response.
}
~~~

Do not catch every exception and ignore it. Distinguish:

- Property is not permitted to be written.
- Property does not exist.
- Missing setter or matching accessor.
- Value cannot be converted.
- Setter throws an exception.
- Intermediate object is null.
- Method or resolver caused an error in a complex expression.

With a custom accessor, error messages should state the rejected property and needed target type, while avoiding logging sensitive object data. In external APIs, internal details of the object model do not necessarily need to be exposed.

## 16. Designing Objects Suitable for Data Binding

One way to reduce risk is to create a dedicated input object containing only the properties that expressions need to modify.

For example, instead of passing a full User entity that has role, passwordHash, and account status, the application can create a DTO:

~~~java
public class ProfileUpdate {

    private String displayName;
    private String locale;

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getLocale() {
        return locale;
    }

    public void setLocale(String locale) {
        this.locale = locale;
    }
}
~~~

SpEL only receives ProfileUpdate as its root object. Sensitive properties are absent from the DTO and therefore cannot be modified through normal property paths on that object.

A dedicated DTO does not replace an allowlist or validation, yet narrows the data surface that expressions can affect. After binding, the Java service still needs to check permissions, formats, value ranges, and business rules before updating the real entity.

## 17. Testing Writable Property Policies

Test both allowed properties and rejected properties:

| Case | Expected Outcome |
|---|---|
| Read displayName | Succeeds if in read allowlist |
| Write displayName | Succeeds if in write allowlist |
| Read role | Follows configured read policy |
| Write role | Rejected if not in write allowlist |
| Write balance | Rejected if sensitive property |
| Write nonexistent property | Property access error |
| Write wrong-type value | Conversion or write error |
| Setter throws exception | Evaluation error propagated |
| Null root object | Handled according to data contract |
| Null nested property | Cannot write without target object |
| Expression assignment disabled | Assignment syntax rejected |
| Expression.setValue on forbidden property | Accessor still rejects write |
| Invoking state-mutating method | MethodResolver and invocation permissions must be controlled |

Test the custom PropertyAccessor directly and run integration tests through SpEL. Direct tests confirm the allowlist; integration tests confirm the parser, EvaluationContext, TypeConverter, and accessor work together properly.

## 18. Takeaways

PropertyAccessor decides whether a property can be read or written. Read permission does not imply write permission. SimpleEvaluationContext provides forReadOnlyDataBinding() and forReadWriteDataBinding() to choose data binding modes; read-write mode can allow many public properties, so a custom PropertyAccessor is needed if only specific properties are permitted to be updated.

An allowlist should separate read permissions and write permissions. canRead/read control readable properties; canWrite/write control modifiable properties. A public setter does not automatically grant write permission in every context. For nested paths, SpEL needs to read intermediate objects and the accessor must permit writing the target property.

Assignment in expression strings and Expression.setValue() both require accessor write permission. The withAssignmentDisabled() flag can disable assignment syntax in supported versions, yet does not replace an allowlist for write operations invoked from Java. Conversion also neither grants write permission nor replaces validation.

Grant least privilege, use dedicated DTOs or accessor allowlists, control method invocation alongside property writes, and test both allowed and rejected operations. Sensitive business changes such as role, balance, or ownership should go through Java services with explicit authorization and validation.

## References

- [Spring Framework Reference — Evaluation Context](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [SimpleEvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/SimpleEvaluationContext.html)
- [DataBindingPropertyAccessor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/DataBindingPropertyAccessor.html)
- [PropertyAccessor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/PropertyAccessor.html)