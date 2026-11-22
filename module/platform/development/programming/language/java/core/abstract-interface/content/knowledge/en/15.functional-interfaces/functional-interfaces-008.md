# Parameter Types, Return Types, and Checked Exceptions in Function Contracts

A **functional interface** defines a contract that can be implemented using a lambda or a method reference. This contract specifies what arguments the function accepts, what value it must return, and which checked exceptions it is permitted to propagate. When assigning a lambda to a functional interface type, Java uses the target type to check those three parts at compile time.

## 1. Distinguishing Method Signatures from Function Contracts

A functional interface has exactly one abstract method (SAM — *single abstract method*). You can use **@FunctionalInterface** to have the compiler verify this condition. The SAM is the function descriptor that a lambda or method reference must satisfy.

In the terminology of the Java Language Specification, a method signature is primarily based on the method name, type parameters, and the types of its formal parameters. **The return type and the throws clause do not create a distinct signature for overloading**, yet they remain an important part of the contract and are checked by the compiler when overriding a method or assigning a lambda.

For example, if an interface declares the method **String convert(String input)**, you cannot declare another overload simply by changing the return type to **Object**, or simply by adding **throws IOException**. To overload the method, the parameter list must differ according to Java's rules.

## 2. Parameter Types

- **Number and order:** a lambda must accept the exact number of parameters of the SAM and use them in the exact order. **BiFunction&lt;String, Integer, String&gt;** has two parameters: **String** followed by **Integer**.
- **Inferred parameter types:** in the expression **s -> s.trim()**, the type of **s** is inferred from the target type. You can write it explicitly, such as **(String s) -> s.trim()**, when you want to clarify the type or when the syntax requires it.
- **Implementing methods must match:** when a class implements an interface or overrides a method, you cannot replace a parameter with a broader or narrower type. If the contract requires **load(String id)**, a **load(Object id)** method does not implement that contract; it is another overload.
- **Generics:** parameter types also depend on how the interface is parameterized. For example, **Consumer&lt;String&gt;** accepts **String**, whereas **Consumer&lt;Integer&gt;** accepts **Integer**. The compiler checks types after applying the appropriate type arguments.

Do not confuse the fact that one type can accept values of another type with being able to replace a parameter type in an overriding method. Overriding rules require the corresponding parameters to match the overridden signature.

## 3. Return Types

If the SAM returns a value, the lambda body must produce a value compatible with that return type. With a block body, use **return** on all branches that can complete normally. If the SAM returns **void**, the lambda can execute a suitable statement without returning a value.

When overriding a method:

- For **reference types**, the return type of the implementing method can be a compatible subtype (*covariant return type*). For example, an interface method returning **CharSequence** can be implemented by a method returning **String**, because **String** is a **CharSequence**.
- For **primitive types**, the return type must match; you cannot change **int** to **long** in an overriding method.
- For **void**, the overriding method must also return **void**.
- You cannot overload a method merely by changing its return type. Java selects overloads based on the parameter list, not on the return type.

For a lambda, the returned expression must be compatible according to Java's type conversion rules. For example, a lambda can return a **String** when the target type requires **CharSequence**.

## 4. Checked Exceptions in the Contract

A checked exception is an exception that the compiler requires code to either handle with **try/catch** or declare further with **throws**. A **throws** clause does not handle an exception; it declares the exceptions that may propagate to the caller.

### Rules When Implementing or Overriding

Suppose an interface method declares **throws IOException**:

- The implementing method can declare **throws IOException**.
- It can declare a narrower checked exception, such as **FileNotFoundException**, because it is a subclass of **IOException**.
- It can omit the **throws** clause if the implementing method does not need to let any checked exception propagate out.
- It cannot declare a broader checked exception such as **Exception**, or an incompatible checked exception such as **SQLException**.
- It can throw a **RuntimeException** or one of its subclasses without declaring it in **throws**, because these are unchecked exceptions.

If the interface method does not declare any checked exceptions, an overriding method cannot add new checked exceptions to the contract on its own. This rule ensures that callers can continue using the interface without having to handle new exceptions that the original contract did not promise.

### Rules for Lambdas and Method References

A lambda does not have its own **throws** syntax. Any checked exceptions that can escape from the lambda body must be compatible with the SAM's **throws** clause, or they must be caught directly inside the lambda body. Method references follow this same rule.

For example, with a functional interface whose method is **load(String id) throws IOException**, a lambda calling **Files.readString(Path.of(id))** can propagate **IOException** outward. However, that same call cannot be assigned directly to **Runnable**, because **Runnable.run()** does not declare any checked exceptions. When you need to use an API that does not declare checked exceptions, you must handle the exception inside the lambda or deliberately convert it to an appropriate unchecked exception; you should not silently swallow the exception.

### Callers Must Follow the Target Type

The compiler checks calls based on the declared type of the variable, not on whether the actual object might throw fewer exceptions. If the variable has type **TextLoader** and the SAM declares **throws IOException**, the caller must still catch or declare **IOException**, even when the current object is an implementing class that never throws that exception.

## 5. Runnable Example on Java 17+

Save the following code in a file named **ContractDemo.java**. The example demonstrates a lambda, an implementing class with a covariant return type (**String** instead of **CharSequence**), and a checked exception declared in the contract.

    import java.io.IOException;
    
    @FunctionalInterface
    interface TextLoader {
        CharSequence load(String id) throws IOException;
    }
    
    final class CachedLoader implements TextLoader {
        @Override
        public String load(String id) {
            return "cached:" + id;
        }
    }
    
    public class ContractDemo {
        public static void main(String[] args) throws IOException {
            TextLoader lambda = id -> "lambda:" + id;
            TextLoader cached = new CachedLoader();
            TextLoader checked = id -> {
                if (id.isBlank()) {
                    throw new IOException("empty id");
                }
                return "loaded:" + id;
            };
    
            System.out.println(lambda.load("A-1"));
            System.out.println(cached.load("B-2"));
            try {
                checked.load("");
            } catch (IOException e) {
                System.out.println("checked: " + e.getMessage());
            }
        }
    }

Compile and run:

    javac ContractDemo.java
    java ContractDemo

Standard output (stdout):

    lambda:A-1
    cached:B-2
    checked: empty id

The calls **lambda.load(...)** and **cached.load(...)** are still written inside **main** with **throws IOException**, because the declared type of both variables is **TextLoader**. The **CachedLoader** class is allowed to omit **throws**, but that does not change the contract visible through the interface type. The **checked** lambda can throw **IOException** because the SAM declared this exception; the caller catches the exception and prints the message.

## 6. Invalid Implementations

For **TextLoader** in the example above, the following declarations are invalid:

    // Invalid: Object is broader than CharSequence.
    // @Override public Object load(String id) { return id; }

    // Invalid: parameter Object does not override load(String).
    // @Override public CharSequence load(Object id) { return id.toString(); }

    // Invalid: Exception is broader than IOException.
    // @Override public CharSequence load(String id) throws Exception { return id; }

Conversely, the following conform to the contract:

    // Return type String is a subtype of CharSequence.
    @Override
    public String load(String id) {
        return "value:" + id;
    }

    // Omitting the throws declaration is still valid.
    @Override
    public CharSequence load(String id) {
        return id;
    }

The snippets above illustrate the rules; do not place all of them in the same class, as doing so would create duplicate or conflicting declarations.

## 7. Generics, Inherited Interfaces, and Built-in Function Types

- **SAM with type parameters:** an interface such as **Decoder&lt;T, E extends Exception&gt;** can return **T** and declare **throws E**. When using **Decoder&lt;String, IOException&gt;**, the return type and checked exception are determined by the chosen type arguments.
- **Multiple superinterfaces:** if superinterfaces declare abstract methods with compatible signatures, the return type must be compatible with all relevant declarations. The implementing method must also adhere to the checked exception bounds of each contract; you cannot use a broader **throws** clause to violate the contract of one of the superinterfaces.
- **Default methods:** they have a default body but still form part of the interface's public behavior; if overridden, the implementing class must follow the rules for parameters, return type, and checked exceptions.
- **Static and private methods in interfaces:** they are not the abstract SAM that an implementing class must implement.
- **java.util.function.Function&lt;T, R&gt;:** its **apply** method does not declare any checked exceptions. Therefore, you cannot directly pass a lambda that lets an **IOException** escape from **apply**. If checked exceptions are a necessary part of the API, consider defining a custom functional interface with **throws IOException**, or using another function type with a matching exception contract, such as **Callable&lt;V&gt;** (which declares **throws Exception**).

## 8. Common Mistakes and How to Self-Check

1. **Changing parameter types when overriding:** check the SAM signature and make sure the parameter types match; replacing them with **Object** or a subtype does not make the method a valid override.
2. **Trying to overload using return type or throws:** a validly different parameter list is required; the return type and **throws** do not create a separate overload.
3. **Returning a type that is too broad:** when overriding, choose a compatible return type and use a subtype only for reference types.
4. **Declaring a checked exception that is too broad:** compare each exception against the interface's **throws** clause; you can omit or narrow exceptions, but you cannot broaden them arbitrarily.
5. **Forgetting to handle exceptions at the call site:** read the contract through the variable's type and catch or declare the checked exceptions that type permits.
6. **Using Function for an API that throws checked exceptions:** handle the exception inside the lambda or design a functional interface with an explicit **throws** clause.
7. **Assuming throws makes an exception disappear:** **throws** only delegates handling responsibility to the caller; only **catch** catches the exception locally.

When designing a function contract, choose parameter types specific enough to define the inputs, a return type that expresses a useful result for the caller, and a **throws** clause that declares only the checked exceptions API users actually need to know about. This ensures that lambdas, method references, implementing classes, and callers all adhere to one clear contract.
