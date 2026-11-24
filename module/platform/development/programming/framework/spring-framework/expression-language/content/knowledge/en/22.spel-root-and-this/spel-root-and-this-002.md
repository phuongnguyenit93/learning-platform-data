# #root and the Root Evaluation Object

In SpEL, the root object is the object from which an expression begins reading data or invoking methods when evaluated. SpEL provides the special variable #root to reference this root object at any position in an expression. The #this variable represents the object currently being evaluated at the current position and can change when an expression enters a collection operation such as selection or projection.

Understanding the difference between #root and #this helps expressions access the right data, especially when working with nested objects, collections, method calls, and multiple processing levels. At the same time, distinguish the root object from variables registered in EvaluationContext: the root object is the base object of the evaluation pass, whereas context variables are data referenced by a variable name with the # prefix.

## 1. What is the root object?

When creating an EvaluationContext, an application can supply an object as the root object. If an expression uses a property or method without a variable prefix, SpEL looks for it on the current object, which is typically the root object at the start of the evaluation pass.

For example, the Customer class:

~~~java
public class Customer {

    private final String name;
    private final int age;

    public Customer(String name, int age) {
        this.name = name;
        this.age = age;
    }

    public String getName() {
        return name;
    }

    public int getAge() {
        return age;
    }

    public boolean isAdult() {
        return age >= 18;
    }
}
~~~

A Customer can be set as the root object:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Customer customer = new Customer("Lan", 25);

StandardEvaluationContext context =
        new StandardEvaluationContext(customer);

Expression expression = parser.parseExpression("name");

String name = expression.getValue(context, String.class);

System.out.println(name); // Lan
~~~

In this example, the expression name is resolved on the root object customer. There is no need to write customer.name because customer is already the context's root object.

The root object can be a domain object, DTO, Map, collection, or another object that the application wants the expression to work with. Choose an object whose data scope is just enough for the expression.

## 2. Explicit reference with #root

The #root variable always points to the root object of the evaluation pass. It can be used to state the data source explicitly, even when the expression is inside a nested context.

~~~text
#root.name
#root.age
#root.isAdult()
~~~

Example:

~~~java
Expression expression = parser.parseExpression(
        "#root.name + ' (' + #root.age + ')'"
);

String description = expression.getValue(context, String.class);
~~~

The result is a descriptive string built from the properties of the root object.

In a simple expression working only with the root object, name and #root.name usually reference the same property. Writing #root explicitly is useful when the expression involves multiple objects, multiple collection operations, or overlapping property names and you need to indicate clearly which data belongs to the root object.

#root is a special variable provided by SpEL; there is no need to call setVariable("root", ...). You should not manually create a context variable named root to replace this special variable.

## 3. Differences between #root and #this

These two special variables serve different purposes:

| Variable | Meaning | Scope |
|---|---|---|
| #root | Root object of the evaluation pass | Keeps referencing the root object |
| #this | Object currently being evaluated at the current position | Can change in nested expressions |

At the start of an expression, before switching into a collection evaluation context or another object, #this usually points to the same object as #root.

Example:

~~~text
#root.name
#this.name
name
~~~

If the root object is Customer, all three forms can read the name property in the initial context.

The difference becomes clear when SpEL evaluates each element of a collection. In a selection predicate or a projection expression, #this is the current element, while #root remains the original root object.

## 4. #this changes in selection

Suppose the root object is a Department that has a list of Employee instances and a department code:

~~~java
public class Department {

    private final String code;
    private final List<Employee> employees;

    public Department(String code, List<Employee> employees) {
        this.code = code;
        this.employees = employees;
    }

    public String getCode() {
        return code;
    }

    public List<Employee> getEmployees() {
        return employees;
    }
}
~~~

Employees can be filtered by the root department code:

~~~text
employees.?[#this.departmentCode == #root.code]
~~~

Inside the predicate:

- #this is the Employee currently being checked.
- #root is the initial Department.
- #this.departmentCode reads the department code on the current employee.
- #root.code reads the department code on the root object.

Java example:

~~~java
Expression expression = parser.parseExpression(
        "employees.?[#this.departmentCode == #root.code]"
);

List<?> result = expression.getValue(context, List.class);
~~~

If you write #root.departmentCode inside the predicate, the expression will look for the departmentCode property on Department, not on Employee. This is a common mistake when confusing the root object with the current element.

When a predicate only involves a single collection and has no overlapping property names, #this can be omitted and departmentCode can be written directly. Using #this explicitly makes the expression easier to read when there are multiple levels of data.

## 5. #this in projection

Projection uses the .![...] operator to build a result collection from each element of the source collection. Inside the projection expression, #this is the current element being transformed.

Example:

~~~text
employees.![#this.name]
~~~

Each Employee is replaced by its corresponding name value. #root still retains its reference to the initial Department.

Data from the current element can be combined with data from the root object:

~~~text
employees.![#root.code + '-' + #this.name]
~~~

The result is a list of strings consisting of the department code and each employee's name.

Example:

~~~java
Expression expression = parser.parseExpression(
        "employees.![#root.code + '-' + #this.name]"
);

List<?> labels = expression.getValue(context, List.class);
~~~

This style is useful when the projection result needs to combine element data with metadata from the root object. If the expression only needs properties of the current element, #this helps show clearly that the value comes from each element.

## 6. Root object and context variables are two different sources

An EvaluationContext can hold a root object and separate variables. The access syntax differs:

- Property on the root object: name or #root.name.
- Context variable: #currentUser, #minimumAge, or #settings.
- Property of an object variable: #currentUser.name.

Example:

~~~java
Customer customer = new Customer("Lan", 25);

StandardEvaluationContext context =
        new StandardEvaluationContext(customer);

context.setVariable("minimumAge", 18);
context.setVariable("label", "Customer");

Expression expression = parser.parseExpression(
        "#root.age >= #minimumAge and #root.name != null"
);

Boolean accepted = expression.getValue(context, Boolean.class);
~~~

Here customer is the root object. minimumAge and label are separately registered context variables.

Do not confuse a property name with a variable name. Writing age accesses the age property on the current object; writing #age references a variable named age in the context. If no variable named age has been registered, the expression #age does not automatically read the age property of the root object.

You can set an object as a variable without changing the root object:

~~~java
context.setVariable("reviewer", anotherCustomer);
~~~

The expression can then compare #root.name with #reviewer.name. This lets the expression work with multiple objects while keeping a clear root object.

## 7. Choosing the root object when calling getValue

You can supply the root object right when creating the context:

~~~java
EvaluationContext context =
        new StandardEvaluationContext(customer);
~~~

You can also pass the root object per evaluation through an Expression overload:

~~~java
Expression expression = parser.parseExpression("name");

String first = expression.getValue(
        context,
        customer,
        String.class
);

String second = expression.getValue(
        context,
        anotherCustomer,
        String.class
);
~~~

The overload that accepts a root object allows reusing a single Expression with different root objects. The root object passed to that getValue call becomes the root object for that corresponding evaluation pass.

This approach is useful when an expression has the same structure but needs to run against multiple records. Ensure each evaluation pass receives the matching object and context variables.

If the context holds variables that depend on a specific root object, update the related variables when changing the root object to avoid using out-of-sync data.

## 8. Changing the root object in EvaluationContext

With StandardEvaluationContext, you can set or replace the root object using the corresponding API:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setRootObject(customer);
~~~

Afterward, expressions without a variable prefix are resolved against customer and #root also points to customer.

You can replace the root object when reusing the context in a sequential flow:

~~~java
context.setRootObject(anotherCustomer);
~~~

However, do not share the same mutable context across multiple requests or multiple threads if the root object and variables can change. One evaluation pass could observe another pass's root object if the context is updated concurrently.

Typically, creating a separate context per processing pass or per request keeps data boundaries clear and easier to control.

## 9. The root object can be a Map or collection

The root object does not have to be a JavaBean. If the root is a Map, keys can be accessed directly or via #root:

~~~java
Map<String, Object> data = new HashMap<>();
data.put("name", "Lan");
data.put("active", true);

StandardEvaluationContext context =
        new StandardEvaluationContext(data);
~~~

The expressions:

~~~text
name
#root['name']
#root['active']
~~~

all access data from the root Map in a way appropriate for property/indexer resolution.

If the root object is a List, an indexer or collection operation can be used:

~~~text
#root[0]
#root.?[#this != null]
~~~

In a selection on a root List, #this is the current element, while #root remains the root List.

Determine the root object type before writing expressions. The syntax for accessing properties, keys, or indices depends on the object type and the property accessors provided by EvaluationContext.

## 10. Root object in nested expressions

An expression can traverse multiple levels of properties or collections. When it does, #this reflects the object being evaluated at the current level, while #root continues referencing the initial object.

For example, the root object is Company, which contains departments, and each Department contains employees:

~~~text
departments.?[
    #this.employees.?[
        #this.active and #root.name == 'Acme'
    ].size() > 0
]
~~~

In the outer selection, #this is Department. In the inner selection, #this is the Employee being examined. #root remains the initial Company.

Nested expressions can be hard to read because the same #this variable changes at each level. Use #root when accessing root data, and use #this explicitly wherever object levels could be confused.

If logic becomes too deep, move part of the condition into a pure method with a descriptive name or prepare the data before evaluation.

## 11. Root object is not a BeanResolver or Spring bean

The root object is the object set as the base for an evaluation pass. It is not synonymous with a Spring bean, nor does it automatically grant access to every bean in ApplicationContext.

To call a bean by name in SpEL, EvaluationContext needs an appropriate BeanResolver. For example, a manually created context can be configured with BeanFactoryResolver:

~~~java
context.setBeanResolver(
        new BeanFactoryResolver(beanFactory)
);
~~~

Once a resolver is configured, an expression can reference a bean using the @beanName syntax. This is a separate mechanism from accessing the root object via #root.

Similarly, methods on the root object can be invoked by method name, whereas methods on a bean must be resolved through the bean resolver and the corresponding bean object.

Distinguish clearly among root object, context variables, and Spring beans to avoid putting too many objects into the context or assuming that once an object is the root, all other beans are automatically accessible.

## 12. Null and the root object

If the root object is null, expressions that read properties or call methods on the root can fail during evaluation:

~~~text
#root.name
isActive()
~~~

Check the root object before evaluation or normalize the input data. You can use Java APIs to verify that the object is non-null before calling getValue.

For a context variable that may be null, check it explicitly:

~~~text
#reviewer == null
#reviewer != null and #reviewer.active
~~~

Do not confuse #root == null with a property on the root having a null value. The root object can exist while one or more of its properties are null.

In collection operations, the current element #this can also be null. Check #this before accessing properties of the element.

## 13. Side effects and access scope

The root object determines what data and behavior an expression can reach. If the root object is a service or an object with many state-mutating methods, an expression can perform actions far beyond a simple data read.

Some practical guidelines:

1. Choose a small root object containing only the necessary data.
2. Use a DTO or projection object for read-only expressions.
3. Supply additional data through clearly named context variables.
4. Avoid setting a repository, payment service, or object with broad write permissions as the root unless needed.
5. Keep methods invoked from expressions pure and low in side effects.
6. Create a separate context per evaluation pass if the root object or variables change.
7. Do not rely on #root to enforce authorization; check permissions in the application/service layer.

If expressions come from an untrusted source, restrict PropertyAccessor, MethodResolver, TypeLocator, BeanResolver, and other capabilities provided by the context. Changing the root object alone is not a security sandbox.

## 14. Common mistakes

| Symptom | Common cause | How to fix |
|---|---|---|
| Property not found | Root object does not have that property or context uses a different root | Check the object passed into getValue |
| #root returns an unexpected object | A getValue overload received a different root object | Check the root object of each evaluation call |
| #this changes inside a predicate | #this is the current element of the collection operation | Use #root to reference the root object |
| #variable does not read a root property | Confusing a context variable with a property on root | Use the property name or #root.property |
| Variable holds stale value after changing root | Context variable was not updated for the new root | Update related variables or create a new context |
| Calling a method on root fails | Method does not exist, is inaccessible, or resolver is unsuitable | Check the object, method, and MethodResolver |
| Accessing a bean with @name fails | Context does not have a BeanResolver | Configure an appropriate resolver if the use case needs it |
| Error on deep access | Root, an intermediate property, or #this is null | Check for null before reading further |

When debugging, first verify the actual root object, then inspect the values of #root, #this, and registered variables separately. You can evaluate smaller parts before combining them into a nested expression.

## 15. Takeaways

#root references the root object of the evaluation pass; #this references the object currently being evaluated at the current position. At the start of an expression, both variables usually point to the root object. In selection and projection, #this switches to the current element, while #root keeps the root object.

The root object is supplied when creating EvaluationContext, set with setRootObject, or passed into a getValue overload for each evaluation call. Context variables are separate data accessed by a `#`-prefixed name; they do not automatically change when the root object changes. The root object is also not synonymous with a Spring bean accessed through a BeanResolver.

Choose a root object with an appropriately narrow scope, use #this for the current element and #root for root data, check for null at each level, and create an appropriate context for each evaluation pass. Distinguishing these data sources clearly makes SpEL expressions easier to read, test, and control for access.