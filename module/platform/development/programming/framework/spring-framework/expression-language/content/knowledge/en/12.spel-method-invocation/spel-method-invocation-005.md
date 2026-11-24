# Methods on Root Objects, Property Objects, and Collections in SpEL

## 1. How SpEL invokes methods

Spring Expression Language (SpEL) allows invoking Java methods directly inside expressions. The syntax closely resembles Java:

```text
methodName(argument1, argument2)
object.methodName(argument1, argument2)
```

SpEL can invoke methods on:

- **Root object**: the base object used to evaluate the expression. Methods can be called directly without an object prefix.
- **Property object**: an object retrieved from a property or from a nested property chain. Use dot notation to access the object and then invoke a method on that object.
- **Collection or array**: invoke a method on the collection/array itself, or access an element and invoke a method on the element. To apply a method across every element, use collection projection or selection.

Example of invoking a method on a string literal:

```java
ExpressionParser parser = new SpelExpressionParser();

String result = parser.parseExpression("'abc'.substring(1, 3)")
        .getValue(String.class);

// result = "bc"
```

Method invocation is resolved when the expression is evaluated. `ExpressionParser` parses the syntax; `EvaluationContext` provides the root object, method resolver, and strategies needed to locate and invoke the method.

## 2. Preparing the root object and EvaluationContext

A common usage pattern is to parse an expression once and evaluate it against a specific object. For example, suppose there are the following domain classes:

```java
public class Customer {
    private String name;
    private Address address;

    public String getName() {
        return name;
    }

    public Address getAddress() {
        return address;
    }

    public String displayName(String prefix) {
        return prefix + " " + name;
    }
}

public class Address {
    private String city;

    public String getCity() {
        return city;
    }

    public String formatLabel() {
        return "City: " + city;
    }
}

public class Order {
    private Customer customer;
    private List<LineItem> items;

    public Customer getCustomer() {
        return customer;
    }

    public List<LineItem> getItems() {
        return items;
    }

    public boolean canShip(int minimumItems) {
        return items != null && items.size() >= minimumItems;
    }

    public String referenceLabel(String prefix) {
        return prefix + "-ORDER";
    }
}

public class LineItem {
    private String sku;
    private boolean available;

    public String getSku() {
        return sku;
    }

    public boolean isAvailable() {
        return available;
    }
}
```

Create a parser and set Order as the root object:

```java
ExpressionParser parser = new SpelExpressionParser();

Order order = loadOrder();

StandardEvaluationContext context =
        new StandardEvaluationContext(order);
```

When an expression is evaluated with this context, an unprefixed property or method name is resolved against the root object. For example, `canShip(2)` invokes Order's `canShip(int)` method.

You can pass the root object directly to an overload of `getValue()` instead of setting it in the context constructor:

```java
Expression expression = parser.parseExpression("canShip(2)");

Boolean canShip = expression.getValue(
        context, order, Boolean.class);
```

Both ways tell SpEL which object to evaluate against. Choose the approach that fits whether the context needs to store additional variables, functions, or resolvers.

## 3. Invoking methods on the root object

When an expression is evaluated against a root object, you can invoke a method of the root directly using the method name and argument list:

```java
String label = parser.parseExpression(
        "referenceLabel('WEB')")
        .getValue(context, String.class);

// label = "WEB-ORDER"
```

Example of invoking a method returning Boolean:

```java
Boolean canShip = parser.parseExpression("canShip(2)")
        .getValue(context, Boolean.class);
```

Example of using a method inside a condition:

```java
String status = parser.parseExpression(
        "canShip(2) ? 'READY' : 'WAITING'")
        .getValue(context, String.class);
```

In the expressions above, `referenceLabel` and `canShip` are invoked on the root object `order`. There is no need to write `#root` if the method can be resolved directly on the root.

You can explicitly refer to the root object using the system variable `#root`:

```text
#root.canShip(2)
```

`#root` always references the original root context object. The `#this` variable references the current object being evaluated; in normal expressions outside collection operations, `#this` usually coincides with the root object.

## 4. Invoking methods on property objects

A property can return another object. Use a dot to access the property, then invoke a method on the returned object.

Example of invoking Customer's method through Order's `customer` property:

```java
String displayName = parser.parseExpression(
        "customer.displayName('Customer:')")
        .getValue(context, String.class);

// Customer: Lan
```

Example of invoking a method on a deeper nested object:

```java
String addressLabel = parser.parseExpression(
        "customer.address.formatLabel()")
        .getValue(context, String.class);
```

SpEL sequentially:

1. Reads the `customer` property on the root Order.
2. Reads the `address` property on Customer.
3. Invokes `formatLabel()` on Address.

You can invoke a method that returns an object and continue accessing properties or invoking methods on the result:

```text
customer.getAddress().getCity().toUpperCase()
```

In this example, SpEL calls `getAddress()`, then calls `getCity()`, and then calls `toUpperCase()` on the resulting String.

### 4.1. Property access and method invocation are different

The following two forms can return the same value:

```text
customer.name
customer.getName()
```

`customer.name` is property access. SpEL uses its property accessor mechanism to read a JavaBean property (typically through a getter). `customer.getName()` is method invocation, resolved by the method resolver.

Use property syntax when the intent is to read data. Use method syntax when you want to invoke a clearly named behavior or a method taking arguments. Do not mistake `name` for a method call without parentheses.

## 5. Invoking methods on collections

Collections are also Java objects, so SpEL can invoke methods provided by the concrete collection type. For List, common methods include `size()`, `isEmpty()`, `get(index)`, and `contains(value)`. For Map, you can invoke `size()`, `isEmpty()`, `containsKey(key)`, `containsValue(value)`, and `get(key)`.

Example of invoking methods on Order's collection property:

```java
Integer itemCount = parser.parseExpression("items.size()")
        .getValue(context, Integer.class);

Boolean hasItems = parser.parseExpression("items.isEmpty()")
        .getValue(context, Boolean.class);
```

Example of retrieving an element and invoking a method on the element:

```java
String firstSku = parser.parseExpression(
        "items.get(0).getSku()")
        .getValue(context, String.class);
```

Example with a collection as the root object:

```java
List<String> names = List.of("An", "Binh", "Chi");

StandardEvaluationContext listContext =
        new StandardEvaluationContext(names);

Integer count = parser.parseExpression("size()")
        .getValue(listContext, Integer.class);

String firstName = parser.parseExpression("get(0).toUpperCase()")
        .getValue(listContext, String.class);
```

If the root object is a List, `size()` and `get(0)` are invoked directly on that list. If the root object is a Map, you can invoke map methods directly:

```java
Map<String, Object> settings = Map.of(
        "region", "ap-southeast-1",
        "enabled", true);

StandardEvaluationContext mapContext =
        new StandardEvaluationContext(settings);

Boolean hasRegion = parser.parseExpression(
        "containsKey('region')")
        .getValue(mapContext, Boolean.class);

String region = parser.parseExpression(
        "get('region')")
        .getValue(mapContext, String.class);
```

A map can also be accessed using index syntax such as `settings['region']`. The `get('region')` method is a Java method call; `settings['region']` is a key-based access. Choose the syntax that makes the intent clearest.

## 6. Invoking methods on each element of a collection

Calling `items.size()` only invokes one method on the collection. It does not automatically invoke a method on every element. To filter a collection by a method on each element or transform each element using a method, use collection selection and projection.

### 6.1. Selection: filtering elements by condition

Selection uses the `?[selectionExpression]` syntax. SpEL evaluates the condition on each element and returns a new collection containing the matching elements.

Example of retrieving only available LineItems:

```java
List<?> availableItems = parser.parseExpression(
        "items.?[#this.isAvailable()]")
        .getValue(context, List.class);
```

Inside selection, `#this` represents the current element. You can invoke a method directly on it:

```text
items.?[isAvailable()]
```

Or use the explicit syntax:

```text
items.?[#this.isAvailable()]
```

The form with `#this` is often easier to read when the expression has multiple nested references.

### 6.2. Projection: invoking a method to build a result collection

Projection uses the `![projectionExpression]` syntax. SpEL evaluates the sub-expression for each element and returns a new collection containing the results.

Example of getting SKUs and converting them to uppercase:

```java
List<?> skus = parser.parseExpression(
        "items.![#this.getSku().toUpperCase()]")
        .getValue(context, List.class);
```

Each element of the result is an uppercase SKU string; the result is no longer a list of LineItems.

### 6.3. Combining selection and projection

You can filter first and project the results afterward:

```java
List<?> availableSkus = parser.parseExpression(
        "items.?[#this.isAvailable()].![#this.getSku().toUpperCase()]")
        .getValue(context, List.class);
```

Execution flow:

1. `items.?[#this.isAvailable()]` keeps items whose `isAvailable()` returns true.
2. `![#this.getSku().toUpperCase()]` invokes `getSku()` on each remaining item, then invokes `toUpperCase()` on the SKU.
3. The result is a List of normalized SKU strings.

Selection and projection are SpEL-specific syntax. They are not calls to a method like `stream().filter(...).map(...)` in Java, although they can solve similar needs.

### 6.4. Selection and projection on Maps

When selection or projection is applied to a Map, the sub-expression is evaluated on each entry of type `Map.Entry`. You can access the `key` and `value` properties.

Example of filtering entries whose value is less than 100:

```text
settings.?[value < 100]
```

Projection creating a list of keys:

```text
settings.![key]
```

Projection creating a list of values:

```text
settings.![value]
```

Distinguish the original collection from the resulting collection. Selection returns the selected elements or entries; projection returns the values computed from each element or entry.

## 7. Method arguments, overloading, and varargs

SpEL supports methods with arguments. Arguments can be literals, variables, properties, calculations, or other expressions:

```java
context.setVariable("prefix", "ORDER");

String label = parser.parseExpression(
        "referenceLabel(#prefix)")
        .getValue(context, order, String.class);
```

SpEL uses the method resolver in EvaluationContext to find a method matching the name and arguments. With `StandardEvaluationContext`, the default method resolver is reflection-based. Type conversion can be applied when arguments have compatible types via ConversionService.

If a class has multiple methods with the same name (overloads), argument types and counts influence which method is selected. Example:

```java
public String format(String value) {
    return "text:" + value;
}

public String format(Integer value) {
    return "number:" + value;
}
```

The expressions `format('12')` and `format(12)` supply arguments with different types. When overloads are complex or multiple converters exist, explicitly verify the runtime types of variables and choose non-ambiguous method signatures.

SpEL also supports varargs:

```java
public String joinLabels(String... labels) {
    return String.join(", ", labels);
}
```

You can pass individual arguments:

```text
joinLabels('NEW', 'PAID', 'SHIPPED')
```

Or pass an array/inline list as the variable argument list according to the syntax the method expects. SpEL can convert each argument to the varargs element type if an appropriate converter is configured.

## 8. Method invocation with null and safe navigation

If the object receiving a method call is null, a normal call can raise an evaluation error:

```text
customer.getName()
```

When `customer` can be null, use safe navigation:

```text
customer?.getName()
```

If customer is null, the safe method call returns null instead of attempting to invoke a method on null. For an access chain with multiple segments that can be null, apply safe navigation at each potentially null segment:

```text
customer?.getAddress()?.formatLabel()
```

Safe navigation only handles the object immediately preceding the `?.` operator. If a method returns null and the expression continues calling another method using a normal dot, the subsequent part can still fail.

In collection projection, an element may be null. You can use safe navigation for the current element:

```text
items.![#this?.getSku()]
```

If the method returns null, projection may retain the corresponding null value in the result collection. If null elements must be removed, use selection first to filter them out.

## 9. MethodResolver and EvaluationContext

`EvaluationContext` participates in resolving method invocations. With `StandardEvaluationContext`, SpEL provides `ReflectiveMethodResolver` to locate Java methods via reflection. The context can also be configured with custom method resolvers if the application needs specific method invocation rules.

Common APIs:

| API | Role |
|---|---|
| `addMethodResolver(resolver)` | Adds a resolver to the existing list. |
| `setMethodResolvers(resolvers)` | Replaces the entire resolver list. |
| `getMethodResolvers()` | Reads the current resolver list. |
| `registerMethodFilter(type, filter)` | Registers a method filter for the reflective method resolver. |

When replacing the entire list with `setMethodResolvers()`, make sure the new list still includes necessary resolvers. If you only want to add a new capability, `addMethodResolver()` is usually more appropriate.

`SimpleEvaluationContext` is designed for a limited feature set and requires explicitly choosing the level of method invocation support when creating the context. Do not assume all contexts permit method invocation in the same way.

## 10. Security when expressions can invoke methods

Method invocation can expose object behavior to expressions. A method can read data, mutate state, access external systems, or perform expensive operations. Therefore:

- Only evaluate SpEL expressions from trusted sources.
- Do not use `StandardEvaluationContext` to evaluate expressions supplied by untrusted users or external systems.
- Use DTOs or dedicated types that expose only the necessary methods.
- Avoid using entities or infrastructure objects with many sensitive methods as the root object.
- Inspect objects returned from properties, methods, and collection elements; they can also be traversed further from expressions.
- Avoid methods with side effects in filtering or projection expressions if invoking a method multiple times could cause unintended changes.

Restricting the root object is not enough if the root object returns a child object with many sensitive behaviors. Design rules must apply across the entire object graph accessible to expressions.

## 11. Comprehensive example: root, nested object, and collection

The following example illustrates three method call locations within a single expression:

```java
// Root Order, nested Customer, and List<LineItem>.
Expression expression = parser.parseExpression(
        "canShip(1) ? " +
        "customer.displayName('For:').toUpperCase() + " +
        "': ' + items.?[#this.isAvailable()].![#this.getSku()] " +
        ": 'WAITING'");

String summary = expression.getValue(
        context, order, String.class);
```

- `canShip(1)` invokes a method on the root Order.
- `customer.displayName('For:')` invokes a method on the object retrieved from the `customer` property.
- `items.?[...]` invokes `isAvailable()` on each LineItem element.
- `items.![...]` invokes `getSku()` on each retained element.

If the condition `canShip(1)` is false, the summary-building branch is not evaluated. If true, only the methods in the selected branch are executed. This example shows how a single expression can combine method invocation, property navigation, selection, projection, and a ternary operator.

## 12. Common errors and how to handle them

| Symptom | Common cause | How to handle |
|---|---|---|
| Method not found | Wrong name, wrong argument count, method unavailable through resolver, or target object has wrong type. | Check target object, method signature, and method resolver. |
| Invoking method on root without a root object | Expression evaluated without passing an appropriate root/context. | Use `new StandardEvaluationContext(root)` or overload `getValue(context, root, type)`. |
| Method on nested object fails | Intermediate property is null or does not return expected type. | Check each property; use safe navigation on potentially null segments. |
| Calling `items.getName()` does not work | Collection does not have that method; the method belongs to each element. | Use `items.get(0).getName()` or projection `items.![getName()]`. |
| `items.size()` is not the expected element count | `items` property is not a collection or data may be null. | Check runtime type and collection state before invoking. |
| Projection returns a different type than original collection | Projection creates a new collection from sub-expression results. | Check the type of values in the projection. |
| Selection does not filter properly | Selection condition does not return Boolean as expected. | Use a clear Boolean expression and check each element's method/property. |
| Overload calls the wrong method | Multiple methods share the same name and argument types are convertible. | Use explicitly typed arguments or design less ambiguous signatures. |
| Varargs does not receive arguments properly | Way of passing array/list or element type does not match. | Check varargs signature and converter for each argument. |
| Error invoking method on null | Object receiving the call is null. | Use safe navigation `?.` or check for null beforehand. |
| Method invoked multiple times in projection | Projection runs sub-expression for each element. | Keep method pure (no side effects) or move processing to Java. |
| Expression invokes unintended methods | Root/nested object exposes too much behavior. | Narrow the object model and only evaluate trusted expressions. |

## 13. Method invocation testing workflow

1. Identify the object receiving the call: root object, nested property object, collection, or collection element.
2. Confirm the runtime type of that object and that the method is accessible.
3. Check method name, argument count, argument types, and overload/varargs cases.
4. Test the method directly with a simple expression before combining it into a long expression.
5. For nested objects, check each property segment and null cases.
6. For collections, test empty collection, one element, multiple elements, and null elements if possible.
7. For selection/projection, check each element and the sub-expression result.
8. Check whether the method has side effects; do not assume the expression is evaluated only once.
9. Use the same EvaluationContext and root object as the application environment to confirm the final result.

## 14. Summary

- Invoke methods with Java syntax: `method(args)` on root or `object.method(args)` on a specific object.
- Root methods can be invoked without a prefix; use `#root` if you want to specify the root context object explicitly.
- Property navigation can traverse multiple objects: `customer.address.formatLabel()`.
- `object.name` is property access; `object.getName()` is method invocation.
- Collections have their own methods like `size()`, `get()`, `contains()`; element methods require accessing an element or using selection/projection.
- Selection `.?[...]` filters; projection `.![...]` builds a collection from results on each element.
- Method arguments can be expressions; overloading and varargs are supported.
- Safe navigation `?.` helps avoid calling methods on null objects.
- `EvaluationContext` and method resolvers determine which methods are resolved.
- Do not evaluate untrusted expressions on an object graph that can invoke sensitive behaviors.

## References

- [Spring Framework Reference — Methods](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/methods.html)
- [Spring Framework Reference — Varargs Invocations](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/varargs.html)
- [Spring Framework Reference — Collection Selection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-selection.html)
- [Spring Framework Reference — Collection Projection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-projection.html)
- [Spring Framework Reference — EvaluationContext and Security](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework Reference — Variables, #this and #root](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/variables.html)
