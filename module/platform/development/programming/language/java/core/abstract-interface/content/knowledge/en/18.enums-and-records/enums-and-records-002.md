# `abstract` Methods in `enum` and Responsibilities of Constants

In Java, an `enum` represents a finite set of constants known in advance, such as operations, states, or event types. When the behavior of each constant differs, an enum can declare an `abstract` method and assign each constant the responsibility of implementing that method. The compiler checks this contract at compile time.

## 1. An Abstract Method Creates a Compile-Time Obligation

An `abstract` method in an enum body declares only the signature and has no implementation. In that case, each constant must have a *constant-specific class body* implementing the corresponding method. If it is missing on a constant, has the wrong name, or has the wrong signature, the entire enum fails to compile.

This differs from writing a regular method in an enum: a method with a body provides shared behavior, and only the constants that actually need to change it have to override it. `@Override` helps the compiler detect signature errors when defining a constant's own implementation.

The next section uses this exact constraint to separate the shared validation rule from each constant's individual fee calculation formula.

## 2. Complete Runnable Example

Save the content below to the file `EnumAbstractMethodDemo.java`. Each delivery option must provide a way to calculate its fee, but all of them share the quantity validation step. Use Java 17 or later.

~~~java
public class EnumAbstractMethodDemo {
    enum DeliveryFee {
        STANDARD {
            @Override
            protected int feeInCents(int itemCount) {
                return 200 + itemCount * 100;
            }
        },
        EXPRESS {
            @Override
            protected int feeInCents(int itemCount) {
                return 500 + itemCount * 200;
            }
        },
        PICKUP {
            @Override
            protected int feeInCents(int itemCount) {
                return 0;
            }
        };

        protected abstract int feeInCents(int itemCount);

        public final int quote(int itemCount) {
            if (itemCount <= 0) {
                throw new IllegalArgumentException("itemCount must be positive");
            }
            return feeInCents(itemCount);
        }
    }

    public static void main(String[] args) {
        for (DeliveryFee delivery : DeliveryFee.values()) {
            System.out.printf(
                "%s: %d cents%n",
                delivery,
                delivery.quote(2)
            );
        }
    }
}
~~~

Compile and run:

~~~text
javac EnumAbstractMethodDemo.java
java EnumAbstractMethodDemo
~~~

Output:

~~~text
STANDARD: 400 cents
EXPRESS: 900 cents
PICKUP: 0 cents
~~~

The line `delivery.quote(2)` runs the shared input check before calling the current constant's `feeInCents(2)` method. STANDARD calculates `200 + 2 × 100 = 400`, EXPRESS calculates `500 + 2 × 200 = 900`, while PICKUP charges no fee. If `0` is passed, `quote` throws `IllegalArgumentException` before performing the calculation.

Here `feeInCents` is `abstract`, so **each constant is required to implement it**. `quote` is a `final` concrete method, so constants cannot bypass the shared validation policy by overriding it. If you add a `DRONE` constant and forget to implement `feeInCents`, the compiler reports an error immediately.

The example uses `int` and fees in cents to focus on the enum mechanism. A real billing application must also check quantity limits and avoid overflow, or choose a monetary representation suited to the business requirements.

## 3. Responsibilities of Each Constant

- **Implement the exact signature:** each constant provides `feeInCents(int)` with an appropriate access level; `@Override` helps check the contract at compile time.
- **Keep only constant-specific logic:** STANDARD, EXPRESS, and PICKUP calculate fees according to three different rules. The `itemCount` check appears only once, in `quote`.
- **Dispatch behavior polymorphically:** the caller only needs the `DeliveryFee` type and the `quote` method; the `feeInCents` implementation is selected based on the constant in use.
- **Force handling when extending:** a new constant without a fee calculation will cause a compile error, rather than silently using an inappropriate default value.

Enum constants remain pre-declared objects. They can have their own class bodies, but additional instances cannot be created with `new` from outside.

## 4. Abstract Methods and Methods with a Default Body

| Design approach | Responsibilities of constants |
| --- | --- |
| `abstract` method | Every constant must implement the method. Use when each constant is required to have its own behavior. |
| Regular method with a body | Constants inherit the default behavior; any constant that needs to differ can override it. |
| `switch` at the call site | The call site must select behavior per constant; when adding a constant, multiple call sites may need to be updated. |

Not every enum needs an abstract method. If all constants have the same behavior, a regular method is usually simpler. If only a few constants need to differ and there is a reasonable default, a method with a body may also be suitable. Use an abstract method when you want the compiler to ensure that every constant defines the required behavior.

## 5. Common Mistakes

1. **Omitting the implementation on a constant:** the enum fails to compile if a constant does not implement the abstract method.
2. **Wrong signature:** changing parameters, return type, or access level in an invalid way can cause overriding to fail. Keep `@Override` for the compiler to check.
3. **Forgetting `;` after the constant list:** when the enum also declares methods, fields, or constructors afterward, the constant list must end with a semicolon.
4. **Writing a body for an abstract method:** an abstract method only declares the signature and does not contain a body in `{ ... }`.
5. **Using incompatible modifiers:** an abstract method cannot simultaneously be `private`, `static`, or `final`, because these modifiers are incompatible with overriding the implementation.
6. **Putting branching logic back at every call site:** if the enum already models behavior with a method, consider calling that method directly instead of repeating `switch` in multiple places.

## 6. When to Use

Abstract methods in an enum are appropriate when the set of choices is finite and stable, and each choice needs to perform the same operation in its own way, for example fee calculation policies by type, state-handling rules, or output formatting by event type.

If the behavior is complex, changes frequently, or needs to be extended with externally provided implementations, consider an interface along with separate strategy classes. An enum works best when the list of constants is controlled and adding a new constant should force the source code to explicitly handle that constant's behavior.

## 7. Key Takeaways

- Declare an abstract method in an enum when every constant must provide a specific behavior.
- Each constant implements the method with its own class body and must match the signature.
- Calling code uses the shared enum type; polymorphism selects the right implementation at runtime.
- Use a method with a default body when there is no need to require each constant to implement it.
- Recompile after adding a new constant to detect missing implementations.
