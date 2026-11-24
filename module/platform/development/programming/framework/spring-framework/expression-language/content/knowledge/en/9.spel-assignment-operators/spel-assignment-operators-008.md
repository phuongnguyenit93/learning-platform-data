# Only Allow Assignment When the Context Contract Explicitly Confirms It in SpEL

Spring Expression Language (SpEL) can read and write object properties. Therefore, an expression can change the state of an object if EvaluationContext provides appropriate write permissions. When expressions come from configuration, users, or a process that may change over time, allowing assignment must be based on an explicit contract: which context is used, which target is modified, which properties are writable, and which conditions must be satisfied.

Do not treat the parser accepting assignment syntax as proof that the operation is permitted by business rules. The parser handles syntax; EvaluationContext and PropertyAccessor instances determine how data is accessed; application policy must decide whether a specific write is authorized.

## 1. Two Ways to Write Data in SpEL

SpEL can write properties in two common ways:

**Using the assignment operator in an expression:**

    ExpressionParser parser = new SpelExpressionParser();
    Expression expression = parser.parseExpression("status = 'APPROVED'");
    expression.getValue(context);

This expression instructs SpEL to assign the value `'APPROVED'` to the `status` property of the root object in the context. The assignment succeeds only if the configured property accessor can write that property.

**Using the setValue API:**

    Expression property = parser.parseExpression("status");
    property.setValue(context, "APPROVED");

Here the expression only identifies the property path; the application calls `setValue` to write the value to that path. This is an explicit write API from Java. It still goes through the write capabilities of EvaluationContext and PropertyAccessor.

Both approaches can modify objects. Apply the same write-permission policy to both paths, especially if the application allows multiple components to share a context.

## 2. PropertyAccessor Is Where Write Permissions Are Enforced

EvaluationContext holds a list of PropertyAccessor instances. Each accessor can declare the target classes it supports, check read/write capability, and perform the corresponding operation:

| Method | Role |
|---|---|
| `getSpecificTargetClasses()` | Declares the target classes supported by the accessor |
| `canRead(context, target, name)` | Checks property readability |
| `read(context, target, name)` | Reads the property value |
| `canWrite(context, target, name)` | Checks property writability |
| `write(context, target, name, newValue)` | Performs writing the value |

When SpEL needs to write a property, the accessor must confirm writability and then execute `write`. With a reflective accessor, writability is typically based on a setter or an accessible field. If a property has only a getter, or the accessor does not support that target/property, the assignment will fail.

Distinguish two questions:

- **Can it be written?** This is the technical capability checked by `canWrite`.
- **Is it allowed to be written?** This is the application's policy decision based on the caller, target, property, business state, and purpose of the operation.

The existence of a setter does not mean every expression user is allowed to call that setter. Likewise, `canWrite` returning true should not be used as the sole proof of authorization to update.

## 3. What Must the Context Contract Specify?

Before enabling write permissions, the application should define a clear contract for EvaluationContext. The contract should answer at least the following questions:

1. **Who is requesting expression evaluation?** Identify the principal, role, or process performing the update.
2. **Which object is the target?** Specify the root object and the scope of objects reachable from the root.
3. **Which properties are allowed to be modified?** Define a property allowlist, or group properties by business purpose.
4. **Which conditions must hold?** For example, the record is still in draft state, the user owns the record, or the workflow has been approved.
5. **Which value types are accepted?** Specify target types, conversion rules, bounds, and data validation.
6. **How are changes recorded?** Specify required transactions, audit logs, validation, and error handling.

This contract must be verified on the application side before creating or selecting a context with write permissions. Never take a flag supplied by the expression itself to grant permissions to that expression.

## 4. Read-Only by Default, Grant Write Permissions as Needed

For expressions used solely for filtering, display, or calculation, choose a read-only context. SimpleEvaluationContext provides a builder intended for read-only data binding:

    SimpleEvaluationContext readOnlyContext =
            SimpleEvaluationContext.forReadOnlyDataBinding()
                    .withRootObject(order)
                    .build();

    ExpressionParser parser = new SpelExpressionParser();
    Expression expression = parser.parseExpression("status = 'APPROVED'");

A read-only context does not provide standard property write capability, so an assignment expression cannot complete the write operation. This is the appropriate configuration when expressions do not need to update data.

When a use case has been confirmed to require updating properties via data binding, you can create a read-write context:

    SimpleEvaluationContext writableContext =
            SimpleEvaluationContext.forReadWriteDataBinding()
                    .withRootObject(order)
                    .build();

Choose a read-write context only after the application has verified the caller's permissions and the update target. This context opens write capability for properties supported by the data-binding accessor; if business rules allow only a narrow set of properties, add an accessor with an allowlist policy or an equivalent control layer.

SimpleEvaluationContext restricts many SpEL capabilities such as type references, constructor invocation, and bean references. However, choosing SimpleEvaluationContext does not automatically prove that every writable property is safe. You still need to clearly define which properties and targets are allowed to be updated.

## 5. Do Not Use StandardEvaluationContext as a Default Write Permission

StandardEvaluationContext provides reflection-based access and includes ReflectivePropertyAccessor by default. That is convenient for trusted internal expressions, yet it can open broader read/write permissions than a use case requires.

For example, if the root object is a business object with many setters, an expression could access properties the application did not intend to allow modifying in the current flow. Just because a property has a public setter does not mean end users are permitted to update it through SpEL.

If you must use StandardEvaluationContext, create a dedicated context for the specific purpose and control the root object, accessors, method resolvers, and other registered services. Do not share a broadly privileged context across expressions with different trust levels. In particular, do not let user-supplied expressions freely use reflection, method invocation, or constructor invocation capabilities that the application has not permitted.

## 6. Use an Allowlist for Writable Properties

When only certain properties are allowed to change, express that list in application policy. For example, an order update flow might allow only `note` and `deliveryComment`, while properties such as `id`, `owner`, `total`, or `paymentStatus` must not be modified via expressions.

A custom PropertyAccessor can check both the target class and property name:

    public final class PolicyPropertyAccessor implements PropertyAccessor {

        private final Set<String> writableProperties;

        public PolicyPropertyAccessor(Set<String> writableProperties) {
            this.writableProperties = Set.copyOf(writableProperties);
        }

        @Override
        public Class<?>[] getSpecificTargetClasses() {
            return new Class<?>[] { Order.class };
        }

        @Override
        public boolean canRead(
                EvaluationContext context, Object target, String name) {
            return target instanceof Order
                    && isReadableOrderProperty(name);
        }

        @Override
        public TypedValue read(
                EvaluationContext context, Object target, String name)
                throws AccessException {
            // Read the property through the mechanism allowed by the application.
            return readAllowedProperty((Order) target, name);
        }

        @Override
        public boolean canWrite(
                EvaluationContext context, Object target, String name) {
            return target instanceof Order
                    && writableProperties.contains(name);
        }

        @Override
        public void write(
                EvaluationContext context, Object target,
                String name, Object newValue) throws AccessException {
            if (!(target instanceof Order)
                    || !writableProperties.contains(name)) {
                throw new AccessException("Property is not writable: " + name);
            }

            // Validate type, value, and business rules before writing.
            writeValidatedProperty((Order) target, name, newValue);
        }
    }

The functions `isReadableOrderProperty`, `readAllowedProperty`, and `writeValidatedProperty` in the example represent processing implemented by the application according to its actual model; they are not built-in Spring APIs. The key point is that the accessor must check both the target and the property, and `write` must re-verify before mutating data.

In real applications, policy often also requires caller information and business state. You can pass a validated policy object into the accessor instead of only a Set of property names. Do not obtain the allowlist from the expression content or from data self-declared by an untrusted caller.

## 7. Validate Values Before Writing

Being allowed to write a property is still not enough to accept any value. Before calling a setter or updating a field, verify:

- Can the new value be converted to the target property type?
- Is the value within the valid domain, such as string length, numeric bounds, or status set?
- Is it necessary to check relationships with other properties?
- Is the update valid for the current state of the entity?
- Does the setter cause side effects or trigger external actions?

SpEL can use EvaluationContext's TypeConverter to convert values to the target type in appropriate situations. Type conversion only solves data representation; it does not replace business validation.

For example, a string might convert into a valid number yet still exceed the allowed quantity limit. A status might have the right String type yet not belong to the statuses accepted by the current workflow. Check both type and business meaning before writing.

## 8. Isolate Contexts by Purpose

Do not create a single global read-write context and reuse it for every expression. Create contexts per specific use case and target:

- Expressions for displaying or filtering data use a read-only context.
- Update expressions use a context with write permissions only when the use case has been authorized.
- Different update flows can have different property allowlists.
- Do not share contexts across requests if the root object, principal, or policy can change.

A clean implementation is having a service that builds the context:

    EvaluationContext createContext(
            User principal,
            Order order,
            UpdatePurpose purpose) {

        authorization.requireCanUpdate(principal, order, purpose);

        return buildContextFor(
                order,
                policyFor(principal, order, purpose)
        );
    }

This is an illustrative structure: `authorization`, `UpdatePurpose`, `policyFor`, and `buildContextFor` are application-defined components. The service must verify permissions before returning a writable context.

If an expression only needs to update a single field, consider calling the setter or a business service directly in Java rather than letting a general-purpose expression mutate objects. Dedicated APIs are usually easier to control for authorization, validation, and auditing.

## 9. Error Handling and Change Recording

An assignment can fail for many reasons: the property does not exist, the accessor does not support writing, the property is read-only, the value cannot be converted, or the policy rejects the update. Distinguish syntax/expression-parsing errors from evaluation errors and business errors.

When an assignment is permitted, the application should verify the outcome and record the change as required by the system. For critical data, the operation should run within an appropriate transaction to ensure consistency if a validation or persistence step fails.

Do not catch errors and ignore them to proceed as if the update succeeded. If policy rejects the change, return a clear error to the calling layer and log at an appropriate level. Avoid including sensitive data or full expressions containing private information in logs unnecessarily.

## 10. Checklist Before Enabling Assignment

Before letting an expression perform assignment, confirm:

1. The purpose of the expression genuinely requires mutating state.
2. The caller is authorized to perform that update use case.
3. The root object and scope of reachable objects are restricted.
4. The selected context has only the necessary level of write permissions.
5. The property being written is in the use case's allowlist.
6. The new value is checked for type, value domain, and business rules.
7. Side effects, transactions, and auditing are handled explicitly.
8. Both allowed and rejected cases are tested.

## 11. Key Takeaways

SpEL supports assignment via the `=` operator and the `Expression.setValue` API; both can mutate objects through PropertyAccessor. Use a read-only context by default for query expressions. Create a context with write permissions only after the application explicitly confirms the caller, target, property, and update purpose. For cases that allow editing only certain properties, use an allowlist checked in the accessor and revalidate the value immediately before writing. The technical ability to write a property does not substitute for the business authorization to write that property.
