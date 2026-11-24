# MethodResolver and How to Restrict Allowed Methods in SpEL

SpEL can invoke methods on the root object, variables, properties, or beans that EvaluationContext permits access to. This capability is useful when an expression needs to perform a small calculation or lookup, yet it also significantly expands what an expression can do.

MethodResolver is the component that determines how SpEL locates and prepares a method for invocation. When an application wants to allow only specific methods, it is necessary to control the resolver and the candidate methods. This lesson explains the method resolution mechanism, how to use MethodFilter, how to replace the default resolver with an allowlist, and the security limits to take into account.

## 1. Objectives and prerequisites

After this lesson, you can:

- Explain the role of MethodResolver during method call evaluation.
- Distinguish MethodResolver from PropertyAccessor, ConstructorResolver, and BeanResolver.
- Identify the default ReflectiveMethodResolver of StandardEvaluationContext.
- Use MethodFilter to restrict allowed methods on a specific type.
- Replace the MethodResolver list with an application-controlled resolver.
- Build an allowlist based on target type, method name, and parameter types.
- Test method overloads, proxies, and behavior when a method is rejected.
- Restrict other EvaluationContext permissions so expressions do not become an arbitrary execution point.

You should already know how to invoke methods in SpEL, how to create StandardEvaluationContext, and how to pass root objects or variables into the context.

## 2. How does SpEL resolve a method call?

When encountering an expression like:

~~~text
#policy.calculateDiscount(#order.total)
~~~

SpEL needs to determine:

1. What the target object receiving the call is, here the value of the policy variable.
2. Whether there is a method named calculateDiscount on that object.
3. Which method overload matches the argument list.
4. Whether argument types can be converted to the method's parameter types.
5. Whether a MethodExecutor can be created to execute the call.

EvaluationContext provides a list of MethodResolvers. SpEL queries the resolvers in turn to find a way to execute the call. A resolver can return a MethodExecutor if a matching method is found, return null if it cannot handle that call, or throw an AccessException if an error occurs during resolution.

Overview flow:

~~~text
Expression containing method call
          |
          v
Identify target object and arguments
          |
          v
MethodResolver list
          |
          v
Find matching method
          |
          v
MethodExecutor
          |
          v
Execute method and receive result
~~~

MethodResolver participates in finding how to invoke a method. It is not the place that checks all application access permissions, nor does it replace business validation.

## 3. Default ReflectiveMethodResolver

StandardEvaluationContext is normally initialized with ReflectiveMethodResolver. This resolver uses reflection to find a matching method on the target object, including overload handling and argument conversion according to SpEL's mechanisms.

Example:

~~~java
public class PricingPolicy {
    public BigDecimal discount(BigDecimal total) {
        return total.multiply(new BigDecimal("0.10"));
    }

    public void resetAllRules() {
        // Mutate configuration state
    }
}
~~~

If PricingPolicy is the root object:

~~~java
PricingPolicy policy = new PricingPolicy();

StandardEvaluationContext context =
    new StandardEvaluationContext(policy);

ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("discount(new java.math.BigDecimal('100'))");

Object result = expression.getValue(context);
~~~

The method call is located and executed by the default resolver if the method is accessible and the arguments match.

The issue is that a general-purpose reflective resolver can find many public methods on an object. If the root object is a large service, the expression can see many more operations than actually needed. Simply putting a service into the context can significantly expand the behavioral surface.

Therefore, restrict the exposed objects and restrict the methods an expression can invoke.

## 4. How does MethodResolver differ from other access components?

EvaluationContext has multiple independent mechanisms:

| Component | Responsibility |
|---|---|
| PropertyAccessor | Read or write properties and fields |
| MethodResolver | Find how to invoke methods on target objects |
| ConstructorResolver | Find how to invoke constructors |
| TypeLocator | Resolve types in T(...) syntax |
| BeanResolver | Resolve beans in @beanName syntax |
| TypeConverter | Convert values between types |
| Variable/function registry | Provide registered variables and functions |

Restricting MethodResolver does not automatically restrict all remaining capabilities. For example, expressions can still read properties through PropertyAccessor; the T(...) syntax still depends on TypeLocator; the @beanName syntax depends on BeanResolver; and functions registered as variables can still be invoked through their own mechanism.

A safe design must review the full set of context permissions per use case, rather than only blocking one group of methods.

## 5. Using MethodFilter to filter allowed methods

With StandardEvaluationContext and ReflectiveMethodResolver, Spring provides MethodFilter. The filter receives the list of candidate methods and returns the list of retained methods.

For example, PricingPolicy only allows calling discount with a single BigDecimal parameter:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext(policy);

context.registerMethodFilter(
    PricingPolicy.class,
    methods -> methods.stream()
        .filter(method -> method.getName().equals("discount"))
        .filter(method -> Arrays.equals(
            method.getParameterTypes(),
            new Class<?>[] { BigDecimal.class }))
        .filter(method -> method.getReturnType().equals(BigDecimal.class))
        .toList()
);
~~~

The filter excludes resetAllRules and overloads not in the allowlist. When SpEL resolves a method call on PricingPolicy, the reflective resolver can only choose from the methods remaining after filtering.

Registering a MethodFilter requires ReflectiveMethodResolver to be present in the resolver list. StandardEvaluationContext provides this resolver by default. If the application has replaced the resolver list, check the actual resolvers before registering a filter; Spring may report an error if no matching ReflectiveMethodResolver is found.

### 5.1. Allowlists should check signatures, not just names

Do not filter only by method name:

~~~java
.filter(method -> method.getName().equals("discount"))
~~~

If the class has multiple overloads with the same name, the filter above could retain signatures that the application did not intend to expose. Consider:

- Method name.
- Parameter types and parameter count.
- Return type.
- Modifiers and accessibility.
- Actual target class.
- Inherited or overridden methods.

The example above precisely filters a single signature taking BigDecimal and returning BigDecimal. For systems with many methods, create a dedicated signature-checking function so the allowlist is easy to read and test.

### 5.2. MethodFilter applies by registered target type

MethodFilter is registered for a specific type. If the target is a proxy or a framework-generated subclass, verify how the resolver determines the method's declaring type and ensure the filter applies to the actual runtime object.

With Spring AOP proxies, test against the exact proxy that the application puts into EvaluationContext. Do not test only on a plain class in a unit test and assume all proxies behave identically.

MethodFilter is a convenient approach when the application still wants to use reflective method resolution yet needs to filter methods on known target types.

## 6. Replacing the MethodResolver list

If stricter control is needed, you can replace StandardEvaluationContext's MethodResolver list:

~~~java
context.setMethodResolvers(List.of(customResolver));
~~~

When doing so, the new list replaces the existing resolver list. If you only want to use an allowlist resolver, do not keep a general-purpose ReflectiveMethodResolver behind it, because that resolver could continue resolving methods that the earlier resolver rejected.

A custom resolver can:

- Accept only certain target classes.
- Accept only certain method names.
- Check exact parameter types.
- Reject static methods or methods with side effects.
- Return a MethodExecutor built from a defined set of methods.
- Record the rejection reason in a way that does not leak sensitive data.

The resolve(...) contract returns a MethodExecutor when the resolver can handle the call. Returning null means this resolver does not resolve the call; subsequent resolvers may still try. Therefore, if you want to definitively reject a method, ensure no other general-purpose resolver can re-allow that call. One way is to place only the allowlist resolver in the context. For genuine resolution errors, the resolver can throw AccessException per the API contract.

### 6.1. Sketch of an allowlist resolver

A practical resolver should check both target type and signature. The following structure illustrates how to organize it:

~~~java
public final class RestrictedMethodResolver
        implements MethodResolver {

    private final ReflectiveMethodResolver delegate =
        new ReflectiveMethodResolver();

    private final Set<MethodKey> allowedMethods;

    public RestrictedMethodResolver(Set<MethodKey> allowedMethods) {
        this.allowedMethods = Set.copyOf(allowedMethods);
    }

    @Override
    public MethodExecutor resolve(
            EvaluationContext context,
            Object target,
            String name,
            List<TypeDescriptor> argumentTypes)
            throws AccessException {

        if (target == null) {
            return null;
        }

        MethodKey key = MethodKey.from(
            target.getClass(), name, argumentTypes);

        if (!allowedMethods.contains(key)) {
            return null;
        }

        return delegate.resolve(
            context, target, name, argumentTypes);
    }
}
~~~

MethodKey here is an application-defined data type representing the target type, method name, and parameter types. This is an architectural sketch, not a complete class that can be copied without defining MethodKey.

When using it:

~~~java
context.setMethodResolvers(
    List.of(new RestrictedMethodResolver(allowedMethods))
);
~~~

Because only the allowlist resolver is in the list, a rejected method will not be passed on to another general-purpose reflective resolver.

In a real implementation, handle proxy classes, exposed interfaces, bridge methods, generic methods, and overload rules. When possible, allowlist against a stable application-owned interface/facade instead of depending on runtime-generated proxy classes.

## 7. Restricting methods right in the object design

An effective way to reduce permissions is not to place general-purpose services into the context. Instead, create a small facade containing only the operations that expressions need.

Example:

~~~java
public class PricingExpressionFacade {
    private final PricingPolicy policy;

    public PricingExpressionFacade(PricingPolicy policy) {
        this.policy = policy;
    }

    public BigDecimal calculateDiscount(BigDecimal total) {
        return policy.discount(total);
    }

    public boolean isEligible(BigDecimal total) {
        return total.compareTo(new BigDecimal("100")) >= 0;
    }
}
~~~

The facade does not expose resetAllRules, updatePolicy, or administrative operations. The root object of the expression is only PricingExpressionFacade.

This measure has several benefits:

- The method contract for expressions is small and stable.
- Does not expose the full service API.
- Easy to write allowlists and unit tests.
- Easy to review changes when adding a new method.
- Parameters and results can be validated directly at the facade.

Even so, the facade still needs to restrict exposed methods and data. A public method can perform many actions internally; a method name is not enough to conclude it is safe.

## 8. SimpleEvaluationContext and method invocation

SimpleEvaluationContext is designed for scenarios requiring restricted SpEL capabilities. By default, it does not provide all features of StandardEvaluationContext and does not enable broad method invocation.

If the use case genuinely requires certain methods, the builder can be configured with specific MethodResolvers:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext
        .forReadOnlyDataBinding()
        .withMethodResolvers(restrictedResolver)
        .build();
~~~

Check the Spring Framework version in use and the corresponding builder API. Add only controlled resolvers; do not register a general-purpose reflective resolver just to make an expression work.

If only property reading is needed, do not add a method resolver. If method invocation is needed, expose a facade with a narrow contract and explicitly test allowed calls.

## 9. MethodResolver is not the only security boundary

A method allowlist is not enough to turn SpEL into a sandbox. Evaluate independent capabilities:

- **Property access:** PropertyAccessor can read sensitive data or write data if the context allows it.
- **Type references:** TypeLocator affects the T(...) syntax.
- **Constructor calls:** ConstructorResolver controls the ability to instantiate objects with new.
- **Bean references:** BeanResolver controls the @beanName syntax.
- **Functions:** Functions registered in the context can invoke exposed methods.
- **Method calls:** MethodResolver decides which methods are resolved.
- **Auto grow and assignment:** Parser configuration along with property write permissions can mutate the object graph.

If expressions come from users or tenants, consider a dedicated restricted condition language instead of allowing general-purpose SpEL. If still using SpEL, create a dedicated context for the use case, a small root DTO, an explicit allowlist, and an expression length limit.

Do not place repositories, EntityManager, ApplicationContext, administrative services, or objects holding secrets into the root object merely for convenience.

## 10. Handling overloads, parameter types, and results

A method can have multiple overloads:

~~~java
public String format(String value) { ... }

public String format(BigDecimal value) { ... }

public String format(Object value) { ... }
~~~

If the allowlist only checks the name format, all three methods may be retained. This makes behavior depend on overload resolution and conversion.

Define the permitted signature explicitly:

- Which target type/interface.
- Method name.
- Parameter count.
- Exact parameter types or accepted type set.
- Return type.
- Whether varargs are allowed.
- Whether inherited methods are allowed.

After the resolver picks a method, SpEL still needs to convert arguments if applicable. Conversion can fail when runtime values are incompatible. The method can also throw an exception during execution. The allowlist only controls invocability; it does not guarantee the method always succeeds or the result is always valid.

Prefer pure methods that take clear inputs and return deterministic results. Avoid exposing methods that perform I/O, write to databases, send messages, or mutate global state.

## 11. Testing the allowlist

A useful test suite should verify both allowed and rejected methods:

| Case | Result to verify |
|---|---|
| Call method with matching name and signature | Succeeds |
| Call method not in allowlist | Cannot be resolved or is rejected |
| Call overload with different parameter type | Rejected |
| Call method on a different target class | Not accidentally allowlisted |
| Call method through runtime proxy | Filter/resolver applies properly |
| Method receives non-convertible argument | Evaluation fails clearly |
| Method throws exception | Error handled per contract |
| General-purpose resolver present behind | Test proves rejected method is not re-allowed by later resolver |
| Use read-only SimpleEvaluationContext without resolver | Method invocation is not granted |
| Register restricted resolver | Only declared calls work |

In addition to unit tests, test the actual context used when the application evaluates expressions. A test with a freshly created StandardEvaluationContext may not reflect the context customized by Spring at runtime.

## 12. Common errors and diagnostics

| Symptom | Common cause | How to handle |
|---|---|---|
| Valid method is not found | Resolver does not support target or signature | Check target type, argument types, and resolver list |
| Blocked method can still be called | General-purpose reflective resolver remains behind | Replace the entire resolver list or filter the right resolver |
| registerMethodFilter reports an error | No ReflectiveMethodResolver in context | Check the MethodResolver list before registering |
| Unintended overload is invoked | Filter only checks method name | Check exact parameter types and return type |
| Filter does not apply to proxy | Target runtime type differs from registered type | Test proxies and use a stable interface/facade or custom resolver |
| Method is found but evaluate fails | Conversion or method execution failed | Check arguments and method exceptions |
| Method is restricted but other data can still be read | PropertyAccessor and other capabilities are independent | Restrict the entire EvaluationContext per use case |

When debugging, verify the context in use, resolver list, actual target object, method signature, and resolver order. Do not add a general-purpose resolver to fix an error before knowing why the allowlist rejected the call.

## 13. Practice exercises

1. Create PricingPolicy with two methods: calculateDiscount and resetAllRules.
2. Put PricingPolicy into StandardEvaluationContext and try calling both methods with the default reflective resolver.
3. Register a MethodFilter allowing only calculateDiscount with the BigDecimal signature.
4. Try calling resetAllRules and a disallowed overload; verify they cannot be resolved.
5. Replace MethodFilter with a custom allowlist MethodResolver and replace the entire resolver list.
6. Create PricingExpressionFacade exposing only two safe read operations and use the facade as the root object.
7. Test the same expressions with a proxy target if the application uses Spring AOP.
8. Write tests confirming that no other resolver re-allows a rejected method.

## 14. Checklist before exposing methods to SpEL

- [ ] Is the root object a small DTO or facade?
- [ ] Have the methods truly needed to be called been identified?
- [ ] Does the allowlist check both target type and method signature?
- [ ] Are there overloads or inherited methods that need to be excluded?
- [ ] Does MethodFilter attach to the right target class/runtime proxy?
- [ ] If using a custom resolver, is the general-purpose resolver removed from the list?
- [ ] Do the exposed methods have side effects or I/O?
- [ ] Have PropertyAccessor, TypeLocator, ConstructorResolver, and BeanResolver been restricted?
- [ ] Have allowed methods, rejected methods, and conversion failures been tested?
- [ ] Do expressions come from trusted sources and have a length limit?

## 15. Conclusion

MethodResolver determines how SpEL finds and executes method calls. StandardEvaluationContext typically uses ReflectiveMethodResolver, so the application must proactively restrict methods if expressions are not allowed to call every API on the target object. MethodFilter is a convenient way to filter reflection methods by type; a custom MethodResolver is appropriate when full control over the resolution strategy is needed. Allowlist by target type and signature, remove general-purpose resolvers that could reopen blocked permissions, expose a small facade, and restrict other EvaluationContext capabilities as well.