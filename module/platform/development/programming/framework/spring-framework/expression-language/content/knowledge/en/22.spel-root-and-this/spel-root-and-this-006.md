# Avoiding Confusion Between #this and #root in SpEL

## 1. Why distinguish #this and #root?

Spring Expression Language (SpEL) provides two system variables for referencing objects during evaluation:

- `#root` is the root context object, i.e., the original object used to evaluate the expression.
- `#this` is the active evaluation object, i.e., the current object SpEL is processing at that position in the expression.

At the normal expression level, when no context-changing operation such as selection or projection has occurred, `#this` usually coincides with `#root`. However, when SpEL enters a collection operation, `#this` switches to the current element, while `#root` keeps the original root object.

This is the most important difference:

| Variable | Scope | Does it change during a collection operation? |
|---|---|---|
| `#root` | The initial root object of the evaluation pass. | No. |
| `#this` | The current object at the position where the expression is being evaluated. | Yes; in selection/projection it is the current element. |

If the two variables are confused, an expression can read a property from the wrong object, call a method on the wrong type, or return a result inconsistent with business data.

## 2. Root object in EvaluationContext

The root object can be configured when creating EvaluationContext:

```java
Order order = loadOrder();

StandardEvaluationContext context =
        new StandardEvaluationContext(order);
```

In an expression, properties and methods of the root object can be accessed directly:

```text
orderNumber
customer.name
canShip(2)
```

Or specify root explicitly with `#root`:

```text
#root.orderNumber
#root.customer.name
#root.canShip(2)
```

Both ways are equivalent when the expression is at the root level. Use `#root` when you want to emphasize that the property or method belongs to the root object, especially when the expression may enter a collection operation and change `#this`.

You can also pass the root object when calling `getValue()`:

```java
Expression expression = parser.parseExpression("#root.orderNumber");

String number = expression.getValue(
        context, order, String.class);
```

The root object passed for this evaluation is the object that `#root` references. This approach is useful when a parser/context is reused with multiple different root objects.

## 3. #this at the normal expression level

When an expression is evaluated directly on the root object and has not switched into a child context, `#this` is usually the root object itself:

```java
Customer customer = loadCustomer();

StandardEvaluationContext context =
        new StandardEvaluationContext(customer);

String name = parser.parseExpression("#this.name")
        .getValue(context, String.class);

String rootName = parser.parseExpression("#root.name")
        .getValue(context, String.class);
```

Both expressions read the `name` property of Customer.

Unprefixed property names are also resolved on the current object:

```text
name
#this.name
#root.name
```

At the outermost level, all three forms can yield the same result. However, when an expression is nested inside selection/projection, only `#root` continues referencing the original root; `#this` and unprefixed property names follow the current object.

## 4. #this changes in collection selection

Selection uses the `.?[predicate]` syntax to filter elements. Inside the predicate, `#this` is the element currently being checked.

Suppose the root object is Company, which has an `employees` property of type List<Employee> and a `name` property for the company name:

```java
public class Company {
    private String name;
    private List<Employee> employees;

    public String getName() {
        return name;
    }

    public List<Employee> getEmployees() {
        return employees;
    }
}

public class Employee {
    private String name;
    private String department;

    public String getName() {
        return name;
    }

    public String getDepartment() {
        return department;
    }
}
```

To select employees belonging to the IT department:

```text
#root.employees.?[#this.department == 'IT']
```

Inside the predicate:

- `#root` is Company.
- `#root.employees` gets the list of employees from Company.
- `#this` is each Employee being checked.
- `#this.department` reads the department of the current Employee.

It can be written more concisely:

```text
employees.?[department == 'IT']
```

Because unprefixed property names inside a predicate are resolved on the current element. The form with `#root` and `#this` is more explicit when data needs to be compared between the root object and an element.

## 5. Using #root and #this together

A common case is filtering a collection using data from the root object. For example, Company has a `preferredDepartment` property; we want to select employees belonging to that department:

```text
#root.employees.?[#this.department == #root.preferredDepartment]
```

Meaning:

1. `#root.employees` gets the collection from Company.
2. SpEL iterates through each Employee.
3. `#this.department` reads the department of the current Employee.
4. `#root.preferredDepartment` reads the preferred department on Company.
5. Only Employees where the two values are equal are kept.

If you mistakenly write `#this.preferredDepartment`, SpEL will look for that property on Employee. If Employee does not have this property, the expression will error or fail to match your intent.

Example projection combining root and element data:

```text
#root.employees.![#root.name + ': ' + #this.name]
```

The result is a list of labels combining the company name with each employee's name.

## 6. #this changes at each level of nested projection

Projection uses the `.![expression]` syntax to transform each element into a new value. When projections are nested, `#this` switches to the element of the inner collection.

For example, Company has Departments and each Department has Employees:

```text
#root.departments.![#this.name + ': ' + #this.employees.![#this.name]]
```

There are two context levels:

- In the outer projection, `#this` is the current Department.
- In the inner projection, `#this` is the current Employee.

`#root` at both levels remains the original Company.

If you need to get the Department name inside the inner projection's expression, you cannot assume `#this` is still Department; at that point `#this` is already Employee. You can design the data or expression to store the parent value in a named variable before moving to the child collection, or split the calculation into clear steps in Java if the logic becomes too complex.

## 7. #this in Map selection/projection

When selection or projection runs on a Map, SpEL processes each entry of type `Map.Entry`. Therefore, `#this` is the current entry rather than the value directly.

Example:

```java
Map<String, Integer> scores = Map.of(
        "Ada", 95,
        "Grace", 91);

context.setVariable("scores", scores);
```

Get the names of entries with a score of 90 or higher:

```text
#scores.?[#this.value >= 90].![#this.key]
```

In selection and projection:

- `#root` remains the root context object of the expression.
- `#this.key` is the key of the current Map.Entry.
- `#this.value` is the value of the current Map.Entry.

If you want to get the values, use:

```text
#scores.![#this.value]
```

Do not write `#this.name` if the current object is Map.Entry and the entry has no `name` property. Determine the exact type of the active object before accessing properties.

## 8. #root, #this, and application-registered variables

System variables and application-registered variables serve different purposes:

| Syntax | Source | Meaning |
|---|---|---|
| `#root` | Provided by SpEL | Root context object. |
| `#this` | Provided by SpEL | Active evaluation object. |
| `#customer` | Registered by application | Value registered with `setVariable("customer", ...)`. |
| `#threshold` | Registered by application | Configuration value or supplementary data. |

Example:

```java
context.setVariable("threshold", 100);
context.setVariable("customer", customer);

List<?> result = parser.parseExpression(
        "#root.orders.?[#this.total >= #threshold and " +
        "#this.customerId == #customer.id]")
        .getValue(context, company, List.class);
```

In the expression, `#threshold` and `#customer` are application variables; `#root` is Company; `#this` is the Order being checked. There is no need to register `#root` or `#this` via `setVariable()`.

Variable names and function names share the same namespace in EvaluationContext. Avoid registering a variable with the same name as a function that the expression needs to call.

## 9. Test example to see the scope clearly

You can test the difference between root and current object directly with JUnit:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

class RootAndThisTest {

    private final ExpressionParser parser =
            new SpelExpressionParser();

    @Test
    void rootStaysCompanyWhileThisChangesPerEmployee() {
        Company company = new Company("Acme", List.of(
                new Employee("Ada", "IT"),
                new Employee("Grace", "HR")));

        StandardEvaluationContext context =
                new StandardEvaluationContext(company);

        List<?> result = parser.parseExpression(
                "#root.employees.![#root.name + ': ' + #this.name]")
                .getValue(context, List.class);

        assertEquals(
                List.of("Acme: Ada", "Acme: Grace"),
                result);
    }

    @Test
    void selectionUsesThisForCurrentEmployee() {
        Company company = new Company("Acme", List.of(
                new Employee("Ada", "IT"),
                new Employee("Grace", "HR")));

        StandardEvaluationContext context =
                new StandardEvaluationContext(company);

        List<?> result = parser.parseExpression(
                "#root.employees.?[#this.department == 'IT']")
                .getValue(context, List.class);

        assertEquals(1, result.size());
        assertEquals("Ada",
                parser.parseExpression("name")
                        .getValue(
                                new StandardEvaluationContext(result.get(0)),
                                String.class));
    }
}
```

The example above assumes the constructors of Company and Employee accept the corresponding parameters. The projection test proves `#root.name` keeps Company's value while `#this.name` changes per Employee. The selection test proves the predicate is evaluated on each Employee.

## 10. How to read a complex expression

When encountering a multi-level expression, read it in this order:

1. Identify the object passed into `getValue()` or the root of EvaluationContext. That is `#root`.
2. Find the selections `.?[...]` and projections `.![...]`.
3. At each predicate/projection, identify which collection is being iterated over.
4. Inside the collection operation's sub-expression, `#this` is the current element or entry.
5. If collection operations are nested, update what `#this` means for the inner level.
6. Use `#root` when you need to refer back to the root object.
7. Use variable names such as `#threshold` for registered application data.
8. Check the type of the current object before accessing a property or calling a method.

You can temporarily annotate the expression to avoid scope confusion:

```text
#root.employees
    .?[#this.department == #root.preferredDepartment]
    .![#root.name + ': ' + #this.name]
```

In both selection and projection in the example, `#this` is the current Employee. `#root` remains Company.

## 11. Common mistakes and fixes

| Symptom | Common cause | How to fix |
|---|---|---|
| `#this.name` reads the wrong name | Active object has switched from root to a collection element. | Identify the current scope; use `#root.name` if root's name is needed. |
| `#root.department` does not exist | Root object lacks that property; property belongs to the element. | Use `#this.department` inside selection/projection. |
| Expression works outside but fails in projection | `#this` changed type to the collection element. | Check element type and rewrite the property path. |
| Nested projection reads wrong parent property | `#this` in the inner projection is the inner collection's element. | Use `#root` for root or put the parent value in a variable beforehand. |
| Using #root but getting an unexpected object | Root passed to the `getValue(context, root, type)` overload differs from the initial context object. | Check the overload and root object of that evaluation pass. |
| Map predicate cannot find value | `#this` is Map.Entry. | Use `#this.key` and `#this.value`. |
| Using `#root` or `#this` like an application variable | Confusing system variables with registered variables. | Do not call `setVariable()` for the two system variables. |
| Unprefixed property name points to wrong object | Unprefixed names are resolved on the active object. | Write `#root.property` or `#this.property` explicitly. |
| Long expression makes scope hard to determine | Many nested collection operations. | Split the expression or use named variables, add annotations, and test parts individually. |

## 12. Testing workflow for #root and #this

1. Create a root object with an easily recognizable property, e.g. Company name `Acme`.
2. Create collection elements with distinct properties, e.g. Employee names `Ada` and `Grace`.
3. Use an expression combining `#root.name` and `#this.name` in projection.
4. Verify the root value does not change and the current value changes for each element.
5. Add selection to verify predicates use `#this` on the right element type.
6. Add nested projection if the application has hierarchical collections; re-identify scope at each level.
7. For Map, test `#this.key` and `#this.value`.
8. Try passing a different root object via the `getValue()` overload to confirm `#root` is bound to the current evaluation pass.
9. Test null and potentially null intermediate objects.
10. Run tests with the same EvaluationContext and root object as the real application.

## 13. Takeaways

- `#root` always references the root context object of the evaluation pass.
- `#this` references the current object at the position where the expression is running.
- At the outer expression level, #this usually matches #root.
- In selection/projection, #this is the current element; in Map operations, it is Map.Entry.
- Nested projection/selection causes #this to switch to the inner collection.
- Unprefixed property names are resolved on the active object, so their meaning can change when scope changes.
- Use #root to access the root object from any collection operation level.
- Use named variables like #threshold for registered application data.
- Write #root and #this explicitly in complex expressions to reduce scope-confusion bugs.

## References

- [Spring Framework Reference — Variables, #this and #root](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/variables.html)
- [Spring Framework Reference — Collection Selection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-selection.html)
- [Spring Framework Reference — Collection Projection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-projection.html)
- [EvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/EvaluationContext.html)
