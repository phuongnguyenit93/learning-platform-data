# Assigning Simple Properties and Nested Properties

## 1. What Is Property Assignment in SpEL?

Spring Expression Language (SpEL) does not only read data from objects. When a property accessor allows writing, SpEL can also update a property of the root object or an object referenced from the evaluation context.

There are two common ways to perform an assignment:

- **Assigning via API:** parse a property expression and then call the setValue method.
- **Assigning via an operator in an expression:** use the assignment operator = inside a SpEL expression and then evaluate the expression.

For example, if the root object is a Customer with a name property:

    name = 'Lan'

The expression above assigns the string Lan to the name property of the root object.

If Customer has an address property and Address has a city property:

    address.city = 'Da Nang'

SpEL traverses the address property first, and then writes the value to city on the Address object.

Distinguishing between simple properties and nested properties helps identify the exact target object, the requirements for a successful write, and the cause when an assignment fails.

## 2. Simple Properties: Writing Directly on the Root Object

A simple property is a property accessed directly from the root object. For example, Customer has the properties name, email, and age.

A simple JavaBean:

    public class Customer {
        private String name;
        private String email;
        private int age;

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public String getEmail() {
            return email;
        }

        public void setEmail(String email) {
            this.email = email;
        }

        public int getAge() {
            return age;
        }

        public void setAge(int age) {
            this.age = age;
        }
    }

Create an expression for the name property and assign a value:

    ExpressionParser parser = new SpelExpressionParser();

    Customer customer = new Customer();

    Expression nameExpression =
        parser.parseExpression("name");

    nameExpression.setValue(
        new StandardEvaluationContext(),
        customer,
        "Lan"
    );

    System.out.println(customer.getName());

Output:

    Lan

Here:

- name is the property expression.
- customer is the root object passed to setValue.
- Lan is the new value.
- SpEL finds a property accessor capable of writing the name property.

Calling setValue separates the property path from the value to assign. This is readable when the application wants to update a specific property.

## 3. Assigning with the Assignment Operator

SpEL supports the assignment operator = directly inside an expression.

Example:

    ExpressionParser parser = new SpelExpressionParser();

    Customer customer = new Customer();

    Expression expression =
        parser.parseExpression("name = 'Lan'");

    Object assignedValue = expression.getValue(
        new StandardEvaluationContext(),
        customer
    );

After evaluation, customer's name property is updated to Lan. The value of the expression is the assigned value.

You must distinguish between these two forms:

    name = 'Lan'

    name == 'Lan'

The = sign is assignment. It updates the property if access rights allow writing.

The == sign is equality comparison. It checks whether the two values are equal and returns a boolean result; it does not update the property.

Do not confuse SpEL's assignment operator with assignment in Java source code. In the example above, the entire expression is passed as a string to the SpEL parser.

## 4. What Is a Nested Property?

A nested property is a path consisting of multiple property access steps. Each subsequent step uses the object returned by the previous step.

Example object model:

    public class Address {
        private String city;
        private String country;

        public String getCity() {
            return city;
        }

        public void setCity(String city) {
            this.city = city;
        }

        public String getCountry() {
            return country;
        }

        public void setCountry(String country) {
            this.country = country;
        }
    }

    public class Customer {
        private String name;
        private Address address;

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public Address getAddress() {
            return address;
        }

        public void setAddress(Address address) {
            this.address = address;
        }
    }

If the root object is Customer, the path:

    address.city

means:

1. Read the address property from Customer.
2. Obtain the returned Address object.
3. Write the city property on that Address object.

Example:

    Customer customer = new Customer();

    Address address = new Address();
    customer.setAddress(address);

    ExpressionParser parser = new SpelExpressionParser();

    Expression cityExpression =
        parser.parseExpression("address.city");

    cityExpression.setValue(
        new StandardEvaluationContext(),
        customer,
        "Da Nang"
    );

    System.out.println(customer.getAddress().getCity());

Output:

    Da Nang

The address property must return an accessible Address object. The city property on that object must be writable according to the accessor being used.

## 5. Assigning a Nested Property with the = Operator

You can write the same operation using the assignment operator:

    Expression expression =
        parser.parseExpression("address.city = 'Da Nang'");

    expression.getValue(
        new StandardEvaluationContext(),
        customer
    );

After evaluation, Address's city is updated.

Nested paths can be longer:

    address.city = 'Da Nang'
    address.country = 'Vietnam'

Or if the object model has multiple levels:

    order.customer.address.city = 'Hue'

SpEL sequentially accesses order, customer, and address, then writes city on the final object.

The depth of the path does not change the principle. Each intermediate step must return an appropriate object so that the next step can proceed.

## 6. Root Object and Variables in EvaluationContext

A property expression without a # prefix is typically resolved relative to the root object.

Example:

    parser.parseExpression("address.city")
        .setValue(context, customer, "Hue");

In this case, customer is the root object.

If you want to access an object via a variable, set the variable in EvaluationContext and use the # prefix:

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("customer", customer);

    Expression expression = parser.parseExpression(
        "#customer.address.city = 'Hue'"
    );

    expression.getValue(context);

As a result, the city property of Customer's Address is updated to Hue.

The following two paths can point to the same property if customer is used as the root object or the corresponding variable:

    address.city

    #customer.address.city

The difference lies in how SpEL locates the starting object. The first path uses the root object; the second path looks up the customer variable in the context.

When writing expressions for multiple objects, variables help explicitly identify the target object and avoid relying on an implicit root object.

## 7. Conditions for a Property to Be Writable

A successful parse does not guarantee that a property is writable. When evaluation performs an assignment, SpEL needs to find a property accessor capable of writing the value to the target property.

For a typical JavaBean, the factors to check include:

- The target object is not null.
- The property can be identified by name.
- There is a suitable setter or another write mechanism supported by the accessor.
- The new value can be converted to the property type.
- The EvaluationContext has an accessor that permits write operations.
- Application permissions allow updating that object.

StandardEvaluationContext uses reflective property access by default, supporting read and write operations appropriate for the object. If the application modifies the PropertyAccessor list, write behavior may differ.

Example of a getter-only property:

    public String getCode() {
        return code;
    }

If there is no setter and the accessor has no alternative write mechanism, assigning code may fail.

Do not assume every readable property is writable. Reading and writing are two separate capabilities of a property accessor.

## 8. Assigning a Nested Property When an Intermediate Object Is null

This is the most common error when assigning nested properties.

Example:

    Customer customer = new Customer();
    customer.setAddress(null);

    Expression expression =
        parser.parseExpression("address.city = 'Hue'");

    expression.getValue(
        new StandardEvaluationContext(),
        customer
    );

SpEL needs to access address before writing city. However, address is null, so there is no Address object to receive the city value.

In a typical configuration, do not assume SpEL automatically creates the entire object graph just because the expression has a nested path.

The most proactive approach is to initialize the intermediate object beforehand:

    Customer customer = new Customer();

    Address address = new Address();
    customer.setAddress(address);

    parser.parseExpression("address.city = 'Hue'")
        .setValue(
            new StandardEvaluationContext(),
            customer,
            "Hue"
        );

Some SpEL configurations support auto-expanding null references during property navigation. This behavior is controlled by parser configuration, such as the autoGrowNullReferences option. It only works in cases where the framework can instantiate the appropriate object and is not a substitute for clear object model design.

When enabling auto-grow, consider constructors, side effects of object creation, and collection size limits. Do not enable it merely to hide an improperly initialized object graph.

## 9. Type Conversion During Assignment

An expression's value does not always have the same type as the target property. SpEL uses the TypeConverter in EvaluationContext to convert types when possible.

For example, the age property is an int:

    public class Customer {
        private int age;

        public int getAge() {
            return age;
        }

        public void setAge(int age) {
            this.age = age;
        }
    }

You can assign a string literal:

    parser.parseExpression("age = '35'")
        .getValue(context, customer);

If the current TypeConverter supports converting String to the corresponding numeric type, the age property can receive the numeric value 35.

A more explicit approach is passing a numeric value from Java:

    parser.parseExpression("age")
        .setValue(context, customer, 35);

If no suitable conversion exists, or the value cannot be converted, evaluation will fail.

With nested properties, the conversion rule also applies at the final property:

    address.postalCode = '700000'

The value is converted according to the type of postalCode if the converter supports it.

Do not rely on implicit conversion for critical data without clearly defining the application's format, locale, and conversion rules.

## 10. Property Paths with Collections or Maps

A property path can also be combined with an indexer to write collection or map elements when supported by the accessor and object.

Example with a map:

    preferences['language'] = 'vi'

Example with a list:

    scores[0] = 95

With a nested object containing a collection:

    customer.addresses[0].city = 'Hue'

These paths follow the same principle: SpEL navigates to the target object or element and then performs the write operation.

However, the element at the corresponding index must exist, or the collection must be configured to allow expansion according to SpEL behavior. An out-of-bounds index can cause an evaluation error without appropriate auto-grow settings.

For maps, the key must be valid for the key type used by the map. Collection and map access also depends on the actual data type and configured accessors.

## 11. When Should You Use setValue vs. an Assignment Expression?

The two approaches have similar goals but express different intents.

| Criterion | setValue | = Operator in SpEL |
| --- | --- | --- |
| Property path | Expression contains only the path | Path and value are in the same expression |
| Assigned value | Passed via Java parameter | Written inside the SpEL expression |
| Dynamic data from Java | Clear, easy to pass types | Can reference variables in the context |
| Reusability | Can keep property expression and pass different values | Keep assignment expression that already includes assignment logic |
| Best suited for | Data binding and updating properties from Java | Rules or expressions that need to express the assignment itself |

Example using setValue:

    Expression property =
        parser.parseExpression("address.city");

    property.setValue(context, customer, newCity);

Example using assignment:

    context.setVariable("newCity", newCity);

    Expression assignment = parser.parseExpression(
        "address.city = #newCity"
    );

    assignment.getValue(context, customer);

If the value comes from Java code, setValue usually makes the boundary between the path and the data to write clearer. If the assignment logic is part of a configured expression, the = operator may be more suitable.

## 12. Troubleshooting Errors When Assigning Properties

When an assignment fails, determine whether the error occurred during parsing or evaluation.

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Parse error | Invalid path or assignment syntax | Check property names, dots, brackets, and operators |
| Property cannot be written | No accessor supports writing | Check setter and PropertyAccessor list |
| Null reference | An intermediate object in the path is null | Check each step such as customer.address |
| Type conversion error | The new value cannot be converted to the target type | Check property type and TypeConverter |
| Index out of bounds | Collection element does not exist yet | Check list size and auto-grow configuration |
| Variable not found | Context does not contain the referenced variable | Check setVariable and the name after # |

For example, the following expression can parse successfully:

    address.city = 'Hue'

Yet if customer has no address, evaluation still fails. That shows valid syntax and data writability are two separate steps.

When debugging, check in order: the root object, each intermediate property, the final property, the accessor, and the data types.

## 13. Side Effects and Safety When Using Assignment

Assignment modifies objects. It has side effects and can affect other components holding the same reference.

Therefore:

- Do not evaluate expressions with assignments on shared objects without controlling the impact.
- Do not allow untrusted expressions to arbitrarily write properties.
- Provide only objects with the necessary write scope to the evaluation context.
- Restrict PropertyAccessor instances and access rights according to business requirements.
- Do not assume SimpleEvaluationContext is automatically safe in every case; properly configure the allowed features.
- For important business data updates, consider performing them through a method or service with validation and transactions rather than letting expressions write arbitrarily.

If an expression contains multiple operations with side effects and a later operation fails, earlier changes may have already occurred. SpEL assignment itself does not create transactions or rollback mechanisms.

## 14. Key Points to Remember

- A simple property is a direct path on the root object, such as name.
- A nested property is an access chain, such as address.city.
- Properties can be written using Expression.setValue or the assignment operator =.
- The = operator is assignment; == is equality comparison.
- A property accessor must support writing, and the value must be compatible with the target type.
- All intermediate objects in a nested path must exist, unless an appropriate auto-grow configuration handles them.
- Variables in EvaluationContext can be accessed using the # prefix.
- TypeConverter can convert values during assignment if conversion is supported.
- Assignment has side effects; restrict objects and write permissions when evaluating expressions.

When designing a SpEL assignment, identify the root object, property path, intermediate objects, writability, and value type before evaluation. That helps separate syntax errors from object access errors and data conversion errors.
