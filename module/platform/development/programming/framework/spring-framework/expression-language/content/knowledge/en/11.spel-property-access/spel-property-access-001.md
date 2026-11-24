# Property Access via Getters Following JavaBean Convention in Spring Expression Language

Spring Expression Language (SpEL) allows reading properties of a Java object using property syntax such as name or customer.address.city. When evaluating a property on a standard JavaBean, SpEL uses the PropertyAccessor mechanism to find how to read the value; the default reflection accessor can resolve properties through getters following the JavaBean convention.

The key point is that a SpEL expression writes the property name, while the getter is the actual Java method invoked to retrieve the data. For example, the expression name is typically mapped to the getName() method of the current object.

## 1. What is a property in a JavaBean?

A JavaBean typically represents data using properties and provides access methods following naming conventions.

A property can have:

- **Getter:** reads the current value.
- **Setter:** writes a new value.
- **Both getter and setter:** supports reading and writing.
- **Getter only:** supports reading, commonly used for read-only properties.

Example:

~~~java
public class Customer {
    private String name;
    private boolean active;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public boolean isActive() {
        return active;
    }

    public void setActive(boolean active) {
        this.active = active;
    }
}
~~~

In this example:

- The name property is read via getName().
- The active property is read via isActive().
- The corresponding setters allow updating the values.

SpEL uses the property name in expressions; you do not need to write the full getter name when you only want to read a property.

## 2. JavaBean getter naming conventions

Common conventions for getters are:

| Property type | Getter | Property name in SpEL |
|---|---|---|
| Regular property | getName() | name |
| Multi-word property | getFirstName() | firstName |
| Count property | getItemCount() | itemCount |
| Primitive boolean | isActive() | active |
| Boolean with get | getEnabled() | enabled |

For getters of the form getXxx(), the Xxx part is converted into the property name according to JavaBeans rules. For example, getFirstName() corresponds to the firstName property.

For names starting with two uppercase letters, JavaBeans rules preserve the leading uppercase characters. Thus, getURL() corresponds to the URL property, not uRL.

For primitive boolean, the isXxx() form is the common convention, such as isActive(). For the Boolean wrapper type, using getActive() is often clearer and compatible with broader getter conventions.

A typical getter is a method with no parameters that returns a value. You should provide public getters with consistent names so properties are clearly accessible through JavaBean tools.

## 3. How does SpEL map a property name to a getter?

Suppose the root object is a Customer:

~~~java
Customer customer = new Customer();
customer.setName("Linh");
customer.setActive(true);
~~~

You can parse and evaluate the properties:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression nameExpression =
    parser.parseExpression("name");

Expression activeExpression =
    parser.parseExpression("active");

String name =
    nameExpression.getValue(customer, String.class);

Boolean active =
    activeExpression.getValue(customer, Boolean.class);
~~~

Result:

~~~text
name = Linh
active = true
~~~

During this evaluation:

1. customer is used as the root object.
2. SpEL receives the name property and looks for how to read the property on the current object.
3. The default ReflectivePropertyAccessor can locate the corresponding JavaBean getter, getName().
4. The getter is invoked and the value Linh is returned to the expression.
5. For active, the getter isActive() is used according to the boolean convention.
6. The resulting values are returned to the Java code.

Therefore, a property name in SpEL is a logical name resolved by an accessor into the actual read mechanism on the object.

## 4. Using StandardEvaluationContext to read properties

When you need to register variables or configure additional access mechanisms, you can create a StandardEvaluationContext:

~~~java
Customer customer = new Customer();
customer.setName("Linh");
customer.setActive(true);

StandardEvaluationContext context =
    new StandardEvaluationContext(customer);

context.setVariable("prefix", "Customer: ");

ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("#prefix + name");

String result =
    expression.getValue(context, String.class);
~~~

Result:

~~~text
Customer: Linh
~~~

In this example:

- name is read from the root object customer through the property accessor.
- #prefix is read from the variable registered in the EvaluationContext.
- The + operator combines the two values into a new string.

Property syntax still works together with variables and operators within an expression.

## 5. Accessing nested properties

A property can return another object. SpEL allows chaining multiple properties with dots to traverse an object path.

Suppose there is a structure:

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

You can read the city via the expression:

~~~spel
address.city
~~~

The access process happens as follows:

1. SpEL reads the address property on the root object Customer using the getAddress() getter.
2. The returned value is an Address object.
3. SpEL reads the city property on Address using the getCity() getter.
4. The city value is returned as the expression result.

A longer path also works according to the same principle:

~~~spel
order.customer.address.city
~~~

Each property segment is resolved on the object returned by the previous segment.

## 6. Handling nullable properties

If an intermediate property returns null, continuing to access further properties can cause an evaluation error. For example, if customer.getAddress() returns null, the expression address.city cannot read city on a nonexistent Address object.

SpEL supports null-safe navigation using the ?. operator:

~~~spel
address?.city
customer?.address?.city
~~~

When the object on the left of ?. is null, the expression returns null at that access step instead of continuing to dereference.

It is important to distinguish:

- The property exists and the getter returns null: that can be a valid result.
- The property cannot be resolved: an access error can occur.
- An intermediate object is null and is then accessed normally: an evaluation error can occur.

Null-safe navigation helps expressions handle optional data more clearly.

## 7. Getters can be inherited

A Java class can inherit getters from a parent class or receive getters through interfaces and appropriate implementation mechanisms.

Example:

~~~java
public class BaseEntity {
    private String code;

    public String getCode() {
        return code;
    }
}

public class Product extends BaseEntity {
}
~~~

If the root object is Product, the expression:

~~~spel
code
~~~

can read the code property through the inherited getter getCode().

This is useful when domain classes share common properties such as id, code, createdAt, or audit metadata in a base class.

## 8. Property access differs from direct method invocation

The two syntaxes below can return the same value:

~~~spel
name
getName()
~~~

However, they represent two different access mechanisms:

- name is property access. SpEL asks a PropertyAccessor to resolve the property, and the default reflection accessor typically invokes the corresponding JavaBean getter.
- getName() is method invocation. SpEL asks a MethodResolver to find and call the method named getName.

When the intent is to read data following the JavaBean model, using property syntax such as name keeps the expression focused on the meaning of the data rather than method-name details.

When the actual intent is to invoke a behavior or business method, use method-call syntax with parentheses.

## 9. PropertyAccessor is responsible for property access

An EvaluationContext can contain one or more PropertyAccessors. Accessors determine how properties are read from or written to an object.

In StandardEvaluationContext, the default ReflectivePropertyAccessor supports accessing many Java properties via reflection. For a standard JavaBean, the accessor can find the appropriate getter and call it to read the value.

Applications can also register custom accessors to map properties to other data sources. For example, an accessor can read data from a proxy object, a custom data structure, or a specialized domain model.

Therefore, the result of property access depends not only on the name in the expression, but also on the configured accessors and the runtime object.

## 10. Reading and writing a property are two different operations

Getters support reading values. If an application wants to write a property, a corresponding write mechanism is needed.

Example:

~~~java
Expression property =
    parser.parseExpression("name");

Object currentName =
    property.getValue(context);

if (property.isWritable(context)) {
    property.setValue(context, "Minh");
}
~~~

In normal cases, the reflection accessor can use the setName() setter to write the name property. A getter-only property can be read, but is not necessarily writable.

Writability also depends on the context and PropertyAccessor. A read-only context may allow getValue while rejecting setValue.

## 11. Data type of the value returned by a getter

The runtime type of a property value generally corresponds to the return type of the getter.

Example:

~~~java
public BigDecimal getPrice() {
    return price;
}

public boolean isActive() {
    return active;
}
~~~

When SpEL reads:

~~~spel
price
active
~~~

the values obtained are BigDecimal and Boolean respectively (a boolean value is boxed when returned through general Java APIs).

You can request a target result type when calling getValue:

~~~java
BigDecimal price =
    expression.getValue(context, BigDecimal.class);
~~~

If the runtime type does not match the target type, the EvaluationContext's TypeConverter can perform conversion when supported. If conversion is not possible, the call can raise an error.

## 12. Getters should not produce side effects

By JavaBean convention, getters are primarily used to provide data. An ideal getter does not mutate object state and does not perform business actions that cause side effects.

However, technically, a getter is still a Java method. It can contain computation logic, data access, or even modify state if implemented that way.

Example of a getter with side effects:

~~~java
public String getStatus() {
    accessCount++;
    return status;
}
~~~

When SpEL evaluates the status property, the getter can cause accessCount to increase.

Therefore, if an expression is evaluated multiple times, you should not assume that reading a property is always completely side-effect-free. Designing simple and stable getters makes expressions more predictable.

## 13. Common errors when accessing properties

Several situations can cause property access to fail:

- The property name is misspelled or does not exist on the current object.
- There is no suitable getter, and the accessor in use has no alternative access mechanism.
- An intermediate object in the path is null.
- The getter throws an exception during execution.
- The context has no suitable PropertyAccessor.
- The return type cannot be converted to the type requested by the application.

When investigating, check in the following order:

1. Is the root object of the right type?
2. Does the property name match the JavaBean property?
3. Can the getter be found and invoked by the accessor?
4. Are any intermediate objects null?
5. Does the getter itself throw an error?
6. Is the result type compatible with the target type?

## 14. Complete example: property getters combined with variables and conditions

Suppose Product has getters getName(), getPrice(), and isAvailable(). The application wants to build a display label based on price and availability.

~~~java
public class Product {
    private final String name;
    private final BigDecimal price;
    private final boolean available;

    public Product(String name, BigDecimal price, boolean available) {
        this.name = name;
        this.price = price;
        this.available = available;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public boolean isAvailable() {
        return available;
    }
}
~~~

Evaluating the expression:

~~~java
Product product = new Product(
    "Keyboard",
    new BigDecimal("750000"),
    true
);

StandardEvaluationContext context =
    new StandardEvaluationContext(product);

context.setVariable(
    "maximumPrice",
    new BigDecimal("1000000")
);

ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "available && price <= #maximumPrice ? name.toUpperCase() : 'NOT ELIGIBLE'"
);

String label =
    expression.getValue(context, String.class);
~~~

Result:

~~~text
KEYBOARD
~~~

SpEL reads available via isAvailable(), reads price via getPrice(), retrieves maximumPrice from the context variable, and reads name via getName() in the chosen branch. Logical and conditional operators combine those values to produce the final string.

## 15. Key takeaways

- Property access uses the property name in the expression; the accessor resolves how to read the value from the object.
- Common JavaBean getters are getXxx() and isXxx() for primitive boolean.
- The property name is derived from the getter name according to JavaBeans rules; for example, getFirstName() corresponds to firstName.
- The root object is the starting point when reading properties without a variable prefix.
- #root and #this help identify the root object and the current object in complex expressions.
- PropertyAccessor determines how properties are read or written; custom accessors can change how access works.
- Getters return runtime values, and those values can be combined with variables, operators, or method calls.
- getValue can return Object or request a target type; conversion depends on TypeConverter.
- Getters should avoid side effects so evaluation results are predictable.
- Property access errors can come from property names, getters, null objects, accessors, or result types.

When reading a SpEL expression that contains properties, trace the property name to the corresponding getter, identify the object on which the getter is called, and then follow how the returned value is used in the rest of the expression.
