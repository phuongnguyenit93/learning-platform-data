# Testing Bean References with a Minimal Context

In Spring Expression Language (SpEL), the **@beanName** expression references a bean through a **BeanResolver** registered in the **EvaluationContext**. When testing this feature, it is not always necessary to start the entire Spring ApplicationContext.

A SpEL-focused test can use:

- **StandardEvaluationContext** to evaluate the expression.
- **BeanFactoryResolver** to connect bean references to a BeanFactory.
- **StaticListableBeanFactory** to pre-register the instances to test.
- **SpelExpressionParser** to parse expressions with @beanName syntax.

This approach tests the exact bean resolution flow of SpEL while keeping tests small and fast. It is suitable when confirming that an expression locates the right bean, invokes a method, or reads a property of that bean.

## 1. What components does a bean reference need?

An expression like:

~~~text
@pricingService.calculate(#amount)
~~~

has three components to distinguish:

1. **@pricingService** is a bean reference. SpEL asks the BeanResolver to look up the bean named pricingService.
2. **calculate(...)** is a method invoked on the object returned by the resolver.
3. **#amount** is a variable read from the EvaluationContext.

Merely having the bean in a container is not enough. The EvaluationContext used to evaluate the expression must also be configured with a BeanResolver. Without a resolver, SpEL does not know how to look up bean names.

In Java, the basic configuration is:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setBeanResolver(
        new BeanFactoryResolver(beanFactory)
);
~~~

BeanFactoryResolver implements BeanResolver and delegates lookups to the BeanFactory passed to its constructor. When an expression requests pricingService, the resolver calls beanFactory.getBean("pricingService") and returns the instance to SpEL.

## 2. Why use StaticListableBeanFactory in unit tests?

**StaticListableBeanFactory** is a lightweight BeanFactory that allows registering pre-created singleton instances using addBean(name, bean).

Example:

~~~java
StaticListableBeanFactory beanFactory =
        new StaticListableBeanFactory();

beanFactory.addBean("pricingService", new PricingService());
~~~

Then attach the factory to the EvaluationContext:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setBeanResolver(
        new BeanFactoryResolver(beanFactory)
);
~~~

Advantages of this approach:

- No need to start an ApplicationContext.
- No need for component scanning or @Configuration setup.
- No need to create bean definitions for a service used only in tests.
- Real services can be replaced with test instances or fakes.
- Tests focus on SpEL resolving the bean name and invoking the corresponding member.

Understand the exact scope: StaticListableBeanFactory manages already-registered instances. It does not instantiate beans from definitions, perform dependency injection, manage prototype scope, or support aliases. Therefore, it is a good choice for unit testing bean references, but does not replace Spring container integration testing.

## 3. Complete example: registering a bean and evaluating an expression

Suppose there is a service:

~~~java
public class PricingService {

    public BigDecimal calculateDiscount(BigDecimal amount) {
        return amount.multiply(new BigDecimal("0.90"));
    }
}
~~~

It can be tested with SpEL as follows:

~~~java
import java.math.BigDecimal;

import org.springframework.beans.factory.support.StaticListableBeanFactory;
import org.springframework.context.expression.BeanFactoryResolver;
import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

public class BeanReferenceTestExample {

    public static void main(String[] args) {
        PricingService pricingService = new PricingService();

        StaticListableBeanFactory beanFactory =
                new StaticListableBeanFactory();

        beanFactory.addBean("pricingService", pricingService);

        StandardEvaluationContext context =
                new StandardEvaluationContext();

        context.setBeanResolver(
                new BeanFactoryResolver(beanFactory)
        );
        context.setVariable("amount", new BigDecimal("100.00"));

        ExpressionParser parser = new SpelExpressionParser();

        Expression expression = parser.parseExpression(
                "@pricingService.calculateDiscount(#amount)"
        );

        BigDecimal result = expression.getValue(
                context,
                BigDecimal.class
        );

        System.out.println(result); // 90.0000
    }
}
~~~

Execution flow:

1. Create a PricingService instance.
2. Register the instance under the name pricingService in StaticListableBeanFactory.
3. Create a StandardEvaluationContext.
4. Attach BeanFactoryResolver to the context.
5. Register the amount variable.
6. Parse the expression containing @pricingService.
7. Call getValue() so SpEL resolves the bean, invokes calculateDiscount(), and returns the result.

The key point is that the name in addBean() must match the name in the expression. If pricingService is registered while the expression writes @priceService, resolution will fail.

## 4. Writing a JUnit test for bean references

The following example illustrates a test focused on the important behavior:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.support.StaticListableBeanFactory;
import org.springframework.context.expression.BeanFactoryResolver;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

class BeanReferenceSpelTest {

    private final ExpressionParser parser =
            new SpelExpressionParser();

    @Test
    void resolvesBeanAndInvokesItsMethod() {
        StaticListableBeanFactory beanFactory =
                new StaticListableBeanFactory();

        beanFactory.addBean(
                "pricingService",
                new PricingService()
        );

        StandardEvaluationContext context =
                new StandardEvaluationContext();

        context.setBeanResolver(
                new BeanFactoryResolver(beanFactory)
        );
        context.setVariable("amount", new BigDecimal("100.00"));

        BigDecimal result = parser
                .parseExpression(
                    "@pricingService.calculateDiscount(#amount)"
                )
                .getValue(context, BigDecimal.class);

        assertEquals(
                0,
                new BigDecimal("90.00").compareTo(result.setScale(2))
        );
    }

    public static class PricingService {

        public BigDecimal calculateDiscount(BigDecimal amount) {
            return amount.multiply(new BigDecimal("0.90"));
        }
    }
}
~~~

The test confirms three things at once:

- Bean name pricingService is resolved.
- Method calculateDiscount() is invoked on the registered instance.
- Variable amount is fetched from EvaluationContext and passed into the method.

In a real project, place test services in separate classes or use shared fixtures so tests remain readable. The example above nests the service inside the test class for standalone illustration.

## 5. Separating bean references from root objects and variables

A common mistake is confusing the following three ways of accessing data:

| Syntax | Meaning | Source |
| --- | --- | --- |
| **@pricingService** | Bean reference | BeanResolver / BeanFactory |
| **#amount** | Variable | EvaluationContext |
| **total** | Property on current root object | Root object passed to getValue() |

All three can be tested in the same expression:

~~~java
Order order = new Order(new BigDecimal("100.00"));

context.setRootObject(order);
context.setVariable("minimumTotal", new BigDecimal("50.00"));
~~~

Expression:

~~~text
@pricingService.calculateDiscount(total + #minimumTotal)
~~~

Here, total is read from the Order root object, minimumTotal is a variable, and pricingService is a bean reference.

When a test fails, identify which data source the error lies in. BeanResolver does not register variables, and setVariable() does not create beans in the BeanFactory.

## 6. Testing bean-not-found scenarios

A good test should verify both when the bean exists and when the bean name is wrong.

Example:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.support.StaticListableBeanFactory;
import org.springframework.context.expression.BeanFactoryResolver;
import org.springframework.expression.EvaluationException;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

class MissingBeanReferenceTest {

    @Test
    void reportsFailureWhenBeanDoesNotExist() {
        StaticListableBeanFactory beanFactory =
                new StaticListableBeanFactory();

        StandardEvaluationContext context =
                new StandardEvaluationContext();

        context.setBeanResolver(
                new BeanFactoryResolver(beanFactory)
        );

        assertThrows(EvaluationException.class, () ->
                new SpelExpressionParser()
                        .parseExpression("@missingService")
                        .getValue(context)
        );
    }
}
~~~

BeanFactoryResolver asks the BeanFactory to look up the bean by name. If there is no matching bean, the lookup error is translated into a SpEL bean resolution error.

Do not depend on the full exception message text in assertions because message details can change across Spring versions. Check the exception family or root cause if the test needs to confirm a specific error type.

## 7. Checking the missing BeanResolver scenario

The bean may already be registered in the factory, yet the EvaluationContext has no resolver attached. This case must also fail:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

Expression expression =
        new SpelExpressionParser().parseExpression("@pricingService");

assertThrows(EvaluationException.class, () ->
        expression.getValue(context)
);
~~~

This test confirms that bean references require configuring a resolver in the context. Merely creating a BeanFactory or registering beans does not automatically link that factory to every EvaluationContext.

In a real Spring application, integration points such as @Value or other modules may configure resolvers for their expression contexts automatically. Standalone parser tests must configure those components themselves.

## 8. When to use SimpleEvaluationContext?

StandardEvaluationContext cannot be replaced with SimpleEvaluationContext if the expression needs @beanName syntax.

SimpleEvaluationContext is designed for a subset of SpEL features and excludes bean references, type references, and constructor invocations. Therefore, the following expression is not suitable for that context:

~~~text
@pricingService.calculateDiscount(#amount)
~~~

For bean references, use StandardEvaluationContext and register only the required BeanResolver.

If the goal is solely reading properties or filtering data, SimpleEvaluationContext may be more suitable. Choose the context based on the features the expression actually uses.

## 9. When is a real ApplicationContext needed?

StaticListableBeanFactory is sufficient for a unit test that only needs to look up a pre-existing instance. However, it does not test the full behavior of the Spring container.

Use AnnotationConfigApplicationContext, GenericApplicationContext, or a Spring test context when needing to verify:

- Component scanning or @Bean methods register the right bean names.
- Constructor injection and setter injection work.
- Beans are created from a BeanDefinition.
- Scopes, lazy initialization, or FactoryBean work properly.
- AOP proxies or transaction proxies are returned as expected.
- The application's actual configuration produces the right BeanResolver.
- Integration points like @Value, Cache, or Method Security supply the appropriate context.

An integration test can initialize a real context, obtain the BeanFactory from the context, and attach BeanFactoryResolver to StandardEvaluationContext. If the goal is only to confirm @beanName syntax and method invocation, keep the test minimal to avoid unnecessary startup overhead.

## 10. Using a custom BeanResolver when BeanFactory is not needed

SpEL does not strictly require BeanFactoryResolver. EvaluationContext only requires a BeanResolver implementation.

If a test wants to verify only the parser and expression, a small resolver mapping names to instances can be provided:

~~~java
BeanResolver resolver = (evaluationContext, beanName) -> {
    if ("pricingService".equals(beanName)) {
        return pricingService;
    }
    throw new AccessException("Unknown bean: " + beanName);
};

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setBeanResolver(resolver);
~~~

This approach is suitable when wanting to isolate SpEL from BeanFactory. However, if the test's goal is to test BeanFactoryResolver itself, use StaticListableBeanFactory as in the earlier example.

A custom resolver needs to clearly define which names are allowed, how non-existent names are handled, and what type of exception is thrown. Do not write a resolver that simply returns one object regardless of beanName, because the test would then fail to verify name-based resolution behavior.

## 11. Special bean names and FactoryBean

If a bean name contains dots or special characters, SpEL requires enclosing the name in a string literal:

~~~text
@'billing.pricing-service'
~~~

This name must match the name that the resolver can look up.

If the bean is a FactoryBean and the factory itself is needed rather than the object created by the factory, SpEL supports the **&** prefix:

~~~text
@&pricingFactory
~~~

This capability is only meaningful when the BeanFactory and actual bean configuration support FactoryBean. StaticListableBeanFactory is suited for regular singleton instances and is not the choice for thoroughly testing FactoryBean lifecycle.

## 12. Common mistakes when testing bean references

1. **Forgetting setBeanResolver():** the expression uses @beanName, yet the EvaluationContext has no resolver.
2. **Mismatched bean name:** the name in addBean() differs from the name after the @ symbol.
3. **Using SimpleEvaluationContext:** this context does not support bean references.
4. **Confusing beans with variables:** #pricingService is a variable, whereas @pricingService is a bean reference.
5. **Inaccessible method:** the bean is resolved, but the method does not exist, is not public, or has incompatible arguments.
6. **Registering the wrong instance:** the factory holds a different object from what the test expects.
7. **Expecting StaticListableBeanFactory to instantiate beans:** this factory only holds pre-registered instances.
8. **Testing too many things in one test:** DI, proxy, scope, and SpEL errors can get mixed up if starting the whole application for a small assertion.
9. **Overly strict exception message assertions:** messages can change across Spring versions.
10. **Assuming unit tests replace integration tests:** resolver tests do not prove component scanning, bean lifecycle, or production proxies are configured properly.

## 13. Quick takeaways

- Bean references in SpEL use the **@beanName** syntax.
- EvaluationContext must have a BeanResolver to resolve bean references.
- **BeanFactoryResolver** connects SpEL to a BeanFactory and calls getBean() by name.
- **StaticListableBeanFactory** allows registering pre-existing singleton instances with addBean().
- Combine StaticListableBeanFactory, BeanFactoryResolver, and StandardEvaluationContext to write lean unit tests.
- Register variables using setVariable() if the expression needs arguments like #amount.
- SimpleEvaluationContext does not support bean references.
- Test missing beans and contexts lacking a resolver to verify configuration errors.
- StaticListableBeanFactory does not test dependency injection, bean definitions, prototype scope, aliases, or ApplicationContext lifecycle.
- Use a real ApplicationContext for integration tests needing component scanning, proxies, scopes, or application wiring.
- Use a custom BeanResolver if you want to isolate the expression from BeanFactory.
- Do not put side effects or real production operations in bean reference tests; use fakes or test instances with deterministic behavior.

## 14. Official references

- [Spring Framework — Bean References in SpEL](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/bean-references.html)
- [Spring Framework — EvaluationContext](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [BeanFactoryResolver Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/expression/BeanFactoryResolver.html)
- [BeanResolver Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/BeanResolver.html)
- [StaticListableBeanFactory Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/support/StaticListableBeanFactory.html)
- [StandardEvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardEvaluationContext.html)
