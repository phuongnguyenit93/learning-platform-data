# Accessing Fields and Exposed Properties in SpEL

## 1. What is property access in SpEL?

Spring Expression Language (SpEL) allows reading and, when a property is writable, updating an object's data via property names in an expression. Instead of calling getters or setters directly in Java, you can write a path such as:

~~~text
customer.name
order.total
product.sku
account.active
~~~

SpEL needs a root object or an evaluation context to know which object to look up the property on. The parser parses the property name into an expression; when getValue is called, a property accessor in the evaluation context resolves how to read the value. When setValue is called, the accessor must support writing to the target property.

Basic example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Customer customer = new Customer("Lan");

Expression expression = parser.parseExpression("name");
String name = expression.getValue(customer, String.class);

System.out.println(name); // Lan
~~~

In this example, customer is the root object and name is the property being accessed. No # prefix is needed because name is looked up on the root object. The # prefix is used when referencing a variable in EvaluationContext, such as #customerName.

## 2. JavaBean properties: getters and setters

A JavaBean typically exposes properties through getter and setter methods following naming conventions:

- getName() provides the value of the name property.
- setName(String name) updates the name property.
- isActive() is commonly used as the getter for the Boolean property active.
- setActive(boolean active) updates the active property.

Example:

~~~java
public class Customer {
    private String name;
    private boolean active;

    public Customer(String name) {
        this.name = name;
        this.active = true;
    }

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

You can read the properties without calling the getters directly:

~~~java
Customer customer = new Customer("Lan");

Expression nameExpression = parser.parseExpression("name");
Expression activeExpression = parser.parseExpression("active");

String name = nameExpression.getValue(customer, String.class);
Boolean active = activeExpression.getValue(customer, Boolean.class);
~~~

SpEL resolves name through a property accessor. For a standard JavaBean, the getter is the read interface of the property and the setter is the write interface of the property. This allows a class to keep its fields private while still exposing a clear property API.

The property name in an expression is the logical name of the property, not the method name. Write name, not getName(), to read a JavaBean property. If you want to call a method as a method, the expression uses method-call syntax with parentheses, such as getName(); however, when the intent is property access, use the property name.

## 3. Direct field access

SpEL can also access fields when the property accessor in use permits it and the field is accessible. With the default ReflectivePropertyAccessor in StandardEvaluationContext, property resolution can use the corresponding accessor method or field. JavaBean-convention getters/setters are generally the preferred interface when a class already exposes properties that way; fields are another access path when appropriate.

Example with public fields:

~~~java
public class Product {
    public String sku;
    public int quantity;

    public Product(String sku, int quantity) {
        this.sku = sku;
        this.quantity = quantity;
    }
}

Product product = new Product("SKU-100", 4);

Expression skuExpression = parser.parseExpression("sku");
Expression quantityExpression = parser.parseExpression("quantity");

String sku = skuExpression.getValue(product, String.class);
Integer quantity = quantityExpression.getValue(product, Integer.class);
~~~

In the case of private fields, accessibility depends on the property accessor, reflection permissions, and runtime/module restrictions. You should not rely on SpEL being able to read a private field as a guarantee that the field is part of a stable class API. For application code, JavaBean getters/setters or a clearly designed property accessor are generally easier to maintain.

Fields and properties are not strictly synonymous:

- A field is a data member declared in a class.
- A property is a data access name exposed via getters/setters or a property accessor.
- A property may not have a field with the same name; a getter can compute its value from multiple fields.
- A field may exist without being exposed through an accessor permitted by the evaluation context.

## 4. Reading properties from the root object

When an object is passed directly to getValue, that object becomes the root object for the evaluation:

~~~java
public class Order {
    private String code;
    private double total;

    public Order(String code, double total) {
        this.code = code;
        this.total = total;
    }

    public String getCode() {
        return code;
    }

    public double getTotal() {
        return total;
    }
}

Order order = new Order("ORD-1001", 1250.0);

Expression codeExpression = parser.parseExpression("code");
Expression totalExpression = parser.parseExpression("total");

String code = codeExpression.getValue(order, String.class);
Double total = totalExpression.getValue(order, Double.class);
~~~

You can read nested properties using dots:

~~~text
customer.name
customer.address.city
order.customer.email
~~~

Example:

~~~java
Expression cityExpression =
        parser.parseExpression("customer.address.city");

String city = cityExpression.getValue(order, String.class);
~~~

The path evaluates only if each intermediate property exists and provides an appropriate object. If customer or address is null, subsequent access can raise an evaluation error.

## 5. Using EvaluationContext to provide the root object

Instead of passing the root object to every getValue call, you can set the root object in StandardEvaluationContext:

~~~java
Customer customer = new Customer("Lan");

StandardEvaluationContext context =
        new StandardEvaluationContext(customer);

Expression expression = parser.parseExpression("name");

String name = expression.getValue(context, String.class);
~~~

The context also allows setting variables:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(customer);

context.setVariable("prefix", "Customer");

Expression expression =
        parser.parseExpression("#prefix + ': ' + name");

String label = expression.getValue(context, String.class);
System.out.println(label); // Customer: Lan
~~~

Within the same expression:

- name is resolved from the root object.
- #prefix is resolved from the variable named prefix.
- #root represents the current root object.
- #this represents the object being processed at the current position in expression constructs such as collection selection/projection.

Distinguishing root-object properties from variables avoids confusion when a name could appear in both places.

## 6. Writing properties with setValue

If a property is writable, Expression supports updating its value using setValue:

~~~java
Customer customer = new Customer("Lan");

Expression nameExpression = parser.parseExpression("name");
nameExpression.setValue(customer, "Minh");

System.out.println(customer.getName()); // Minh
~~~

You can use an evaluation context instead of passing the root object directly:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(customer);

Expression activeExpression = parser.parseExpression("active");
activeExpression.setValue(context, false);

System.out.println(customer.isActive()); // false
~~~

Writability depends on the property accessor and the target object. A JavaBean property with an appropriate setter can usually be updated. Getter-only properties, final fields, immutable objects, or read-only accessors may disallow writing. When writing is not possible, SpEL raises an evaluation error rather than fabricating a setter or altering the class design.

Use setValue only when the application intentionally mutates object state. An expression that reads a property can be used for computation; an expression that writes a property is an operation with side effects and needs to be explicitly controlled.

## 7. Accessing properties of nested objects

SpEL supports property paths across multiple object levels:

~~~java
public class Address {
    private String city;

    public Address(String city) {
        this.city = city;
    }

    public String getCity() {
        return city;
    }
}

public class Customer {
    private String name;
    private Address address;

    public Customer(String name, Address address) {
        this.name = name;
        this.address = address;
    }

    public String getName() {
        return name;
    }

    public Address getAddress() {
        return address;
    }
}

Customer customer = new Customer("Lan", new Address("Da Nang"));

Expression expression =
        parser.parseExpression("address.city");

String city = expression.getValue(customer, String.class);
System.out.println(city); // Da Nang
~~~

Each segment after a dot is a property access on the object returned by the previous segment. This keeps expressions concise, but it also means the data must have the expected structure. If a property does not exist or an intermediate object is null, that case must be handled.

## 8. Null-safe property access

SpEL provides the null-safe navigation operator ?. to avoid accessing a property on a null target:

~~~java
Expression expression =
        parser.parseExpression("address?.city");

String city = expression.getValue(customer, String.class);
~~~

If address is null, address?.city returns null instead of trying to read city on a nonexistent object.

For multi-level paths, use the null-safe operator at each leg that can be null:

~~~text
customer?.address?.city
~~~

Example:

~~~java
Expression expression =
        parser.parseExpression("address?.city ?: 'Unknown city'");

String cityOrDefault = expression.getValue(customer, String.class);
~~~

Here ?. handles the case where address is null; the Elvis operator ?: supplies a default string if the left-hand result has no suitable value. The null-safe operator does not automatically make every property in a path safe; clearly identify which objects can be null and place ?. at the corresponding positions.

## 9. Accessing Maps, Lists, and arrays

Maps, Lists, and arrays have their own element access syntax. For a Map, use a key inside square brackets; for a List or array, use an index:

~~~java
Expression mapExpression = parser.parseExpression("['city']");
Expression listExpression = parser.parseExpression("items[0]");
Expression arrayExpression = parser.parseExpression("codes[1]");
~~~

If the root object is a Map, you can use:

~~~java
Map<String, Object> data = new HashMap<>();
data.put("city", "Da Nang");

Expression expression = parser.parseExpression("['city']");
String city = expression.getValue(data, String.class);
~~~

For an object whose items property is a List, items[0] accesses the first element of that property. Indexer syntax is not the same as dot property access. Use customer.name to read the name property; use map['name'] to read the value for key name in a Map.

## 10. PropertyAccessor and how SpEL resolves properties

SpEL uses the PropertyAccessor interface to determine how to read/write properties on an object. An accessor can indicate what target types it supports, which properties can be read, and which properties can be written.

The core methods of an accessor include:

- getSpecificTargetClasses(): declares the target types supported by the accessor; may return null if broadly applicable.
- canRead(...) and read(...): check and perform reading.
- canWrite(...) and write(...): check and perform writing.

StandardEvaluationContext uses a reflective property accessor by default to operate on Java objects. You can add custom accessors when you need to expose data under different conventions, such as objects from external libraries or specialized data structures:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(customer);

context.addPropertyAccessor(customPropertyAccessor);
~~~

When multiple accessors are present, their order and target/property support affect which accessor is used. Custom accessors should clearly restrict supported target types and allowed properties to avoid unexpectedly broadening access.

## 11. SimpleEvaluationContext and limiting property access

StandardEvaluationContext provides fuller SpEL capabilities, including reflection and configurable resolvers. If an application only needs data binding or restricted property access, consider SimpleEvaluationContext.

Example creating a context for read-only data binding:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();
~~~

Or a context for read/write data binding:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding().build();
~~~

This type of context is designed to restrict certain SpEL capabilities compared to StandardEvaluationContext. Choose the builder that matches the required permissions: read-only when the expression only needs to inspect data; read/write when updating properties is actually needed. If a custom property accessor is needed, you can configure the builder with the corresponding accessor.

Do not treat using SimpleEvaluationContext as a substitute for input validation. Enable only the capabilities required by the expression and avoid evaluating strings submitted by untrusted users with a broadly privileged context.

## 12. Getters can execute code

When SpEL reads a JavaBean property, the accessor may invoke a getter. A getter does not necessarily just return a field; it may compute, query data, or execute other code.

~~~java
public class Account {
    public BigDecimal getAvailableBalance() {
        // May compute from multiple fields or other state.
        return calculateAvailableBalance();
    }
}
~~~

The expression availableBalance can invoke the corresponding getter. Therefore, property access is not always a simple memory read. Avoid placing heavy side effects or surprising behavior in getters used by expressions. For operations that must mutate state, use a method whose name clearly describes the action and call it at the appropriate Java layer.

## 13. Common mistakes

**Using the method name instead of the property name**

With the JavaBean getter getName(), the property is normally accessed using name. Use getName() if you genuinely want to call the method; you do not need to use the method name to read a property.

**Property not exposed or unsupported by accessor**

If there is no suitable getter, field, or property accessor supporting the target, SpEL cannot resolve the property name. Check the root object, property name, and evaluation context being used.

**Accessing through null**

A nested path segment can fail when an intermediate object is null. Use the null-safe operator on legs that can be null or check conditions first.

**Trying to write to a read-only property**

setValue requires a writable property accessor. Getter-only properties or read-only accessors cannot be updated automatically.

**Confusing properties with Map keys or collection indexes**

Use dots for property paths and square brackets for Map keys and List/array indexes. Using the appropriate syntax helps the parser resolve data properly.

**Granting overly broad access**

StandardEvaluationContext can support reflection, method resolution, and type access depending on configuration. For untrusted expressions, restrict the evaluation context and accessors.

## 14. Combined example

The following example reads a property of the root object, nested properties, and uses null-safe access along with a default value:

~~~java
public class Address {
    private String city;

    public Address(String city) {
        this.city = city;
    }

    public String getCity() {
        return city;
    }
}

public class Customer {
    private String name;
    private Address address;

    public Customer(String name, Address address) {
        this.name = name;
        this.address = address;
    }

    public String getName() {
        return name;
    }

    public Address getAddress() {
        return address;
    }
}

ExpressionParser parser = new SpelExpressionParser();

Customer customer = new Customer("Lan", new Address("Da Nang"));

StandardEvaluationContext context =
        new StandardEvaluationContext(customer);
context.setVariable("prefix", "Customer");

Expression expression = parser.parseExpression(
        "#prefix + ': ' + name + ' / ' + (address?.city ?: 'Unknown')");

String description = expression.getValue(context, String.class);
System.out.println(description);
// Customer: Lan / Da Nang
~~~

If address is null, address?.city evaluates to null and the Elvis operator supplies Unknown. The name property is still read from the root object customer, while #prefix comes from the variable in the context.

## 15. Key takeaways

- SpEL reads properties via PropertyAccessor; StandardEvaluationContext includes reflective property access by default.
- JavaBean properties are typically exposed via getters and setters; the name in an expression is the property name such as name, not getName().
- Fields can be accessed if the accessor and runtime permit; internal fields should not be treated as a stable API.
- The root object is accessed directly; variables in the context use the # prefix.
- Dots are used for property paths; square brackets are used for Map keys and collection/array indexes.
- setValue works only when the property accessor allows writing.
- Use ?. for intermediate objects that may be null and ?: when a default value is needed.
- Choose SimpleEvaluationContext when access needs to be restricted; do not evaluate untrusted expressions with a full-privilege context.
