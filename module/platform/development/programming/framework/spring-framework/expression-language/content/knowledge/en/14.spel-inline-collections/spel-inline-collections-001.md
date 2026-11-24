# Creating Inline Arrays in SpEL

SpEL can create collection data directly within an expression. However, an inline list must be distinguished from an actual Java array. The syntax {1, 2, 3} creates a List; the syntax new int[]{1, 2, 3} creates an array of type int[]. Both results may contain the same values, but they have different data types and behave differently when passed to a Java method, assigned to a property, or processed further in an expression.

When you need a structure with a fixed element type and fixed size, create an array. When you need a flexible list to filter, iterate, or add elements to, an inline list is usually more suitable.

## 1. Distinguishing an inline list from a Java array

An inline list in SpEL uses curly braces:

    {10, 20, 30}

This expression creates a List object containing three elements. It does not automatically become an int[] just because all the elements are integers.

To create a Java array, use the new operator with the element type and square brackets:

    new int[]{10, 20, 30}

The result is a primitive int[] array. For a reference type, such as a String array:

    new java.lang.String[]{'SPRING', 'SpEL'}

The result is a String[] array.

Comparison:

| Expression | Result type | Characteristics |
|---|---|---|
| {10, 20, 30} | List | Resizable collection |
| new int[]{10, 20, 30} | int[] | Primitive array, fixed size |
| new java.lang.String[]{'A', 'B'} | String[] | Reference array, fixed size |
| new int[3] | int[] | Three-element array, each element initially 0 |
| new java.lang.String[2] | String[] | Two-element array, each element initially null |

Choosing the syntax depends on the type that the downstream Java code expects. If a method accepts int[], passing an inline list may not satisfy the type contract. Create the proper array or convert explicitly before calling the method.

## 2. Syntax for creating an array with initialized elements

Basic syntax:

    new elementType[]{value1, value2, value3}

Where:

- new tells SpEL to create a new object.
- elementType is the type of each element in the array.
- [] declares that the result is an array.
- {...} contains the initial values in order.

Integer array example:

    new int[]{3, 5, 8, 13}

Floating-point array:

    new double[]{1.5, 2.0, 3.75}

Boolean array:

    new boolean[]{true, false, true}

String array:

    new java.lang.String[]{'ACTIVE', 'PENDING', 'CLOSED'}

The number of elements in the initializer determines the array length. Therefore, new int[]{} creates an empty int array of length 0. If you need to declare the length without initial values yet, use the syntax for creating an array by size.

The type name can be a primitive type such as int, long, double, boolean or a reference type such as java.lang.String, java.time.LocalDate, and classes in the application. For classes outside java.lang, use the fully qualified name so TypeLocator resolves it accurately.

## 3. Creating an array by size

SpEL supports creating an array with a specified size:

    new int[3]

The result is an int array with three slots. Primitive elements are initialized with the default value of their type:

- Integer types such as byte, short, int, and long have a default value of 0.
- Floating-point types such as float and double have a default value of 0.0.
- boolean has a default value of false.
- char has a default value of the null character.

For a reference-type array:

    new java.lang.String[2]

both elements are initially null. Java does not automatically create two empty strings.

The create-by-size syntax and the element-initializer syntax serve two different purposes:

    new int[3]

    new int[]{10, 20, 30}

The first creates slots with default values. The second creates the array and fills in the three specified values. Do not write an explicit size together with an initializer list such as new int[3]{10, 20, 30}; choose one of the two syntax forms.

The array size must be a non-negative integer. A negative size or an invalid size expression will cause evaluation to fail.

## 4. Primitive arrays and reference-type arrays

Primitive arrays store primitive values directly:

    new int[]{10, 20, 30}
    new boolean[]{true, false}

Reference-type arrays store references to objects:

    new java.lang.String[]{'Spring', 'Framework'}
    new java.math.BigDecimal[]{
        new java.math.BigDecimal('10.50'),
        new java.math.BigDecimal('20.00')
    }

This difference affects element values and the ability to hold null:

| Characteristic | Primitive array | Reference array |
|---|---|---|
| Examples | int[], boolean[] | String[], BigDecimal[] |
| Element value | Primitive value | Reference to object |
| Can contain null | No | Yes |
| Default value | 0, false, 0.0... | null |
| Element type | Fixed to declared primitive | Fixed to declared class |

If an input element can be null, it cannot be stored in a primitive array. When you need to represent missing data, consider using a wrapper type such as Integer[] instead of int[]:

    new java.lang.Integer[]{1, null, 3}

This array can contain null at the second position. With int[], every position always holds a primitive integer value.

## 5. Initializer values must match the element type

When creating an array, each element must be compatible with the declared element type. For example:

    new int[]{1, 2, 3}
    new java.lang.String[]{'A', 'B'}

You cannot create an int[] containing arbitrary strings:

    new int[]{1, 'two', 3}

A value that cannot be converted to the element type will cause an error during expression evaluation. SpEL has a type conversion mechanism in appropriate contexts, but you should not rely on implicit, unclear conversions to define input data.

If initial data comes from configuration or users, validate and convert it at the Java layer before creating the array. For numeric types, dates, or domain types, use explicit literals and constructors so readers see the exact data type being created.

Example of creating a BigDecimal array:

    new java.math.BigDecimal[]{
        new java.math.BigDecimal('12.50'),
        new java.math.BigDecimal('99.90')
    }

This expression creates two BigDecimal objects and then places them into a BigDecimal[] array.

## 6. Accessing array elements

After creating an array, you can access elements using an index in square brackets:

    new int[]{10, 20, 30}[0]

The expression above returns 10. Array indexing starts at 0, just like in Java:

    new int[]{10, 20, 30}[1]

returns 20.

In practice, the resulting array is often stored in a context variable or a property of the root object, and then accessed:

    #codes[0]
    #codes[1]

If the index is negative or greater than the last index, SpEL cannot retrieve the element and will throw an evaluation error. Before accessing a dynamically computed position, make sure the array is not null and the index is within bounds.

An array has a fixed size after creation. You can modify the value at a position if appropriate write permissions exist, but you cannot add or remove elements to change the array length. If you need resizing operations, use a List.

## 7. Using inline arrays in Spring configuration

A common use case is initializing an array for a bean property using @Value and SpEL:

    @Component
    public class RetrySettings {

        private final int[] retryDelays;

        public RetrySettings(
                @Value("#{new int[]{100, 500, 1000}}")
                int[] retryDelays) {
            this.retryDelays = retryDelays;
        }

        public int[] getRetryDelays() {
            return retryDelays;
        }
    }

The expression is inside #{...} because @Value is instructing Spring to parse a SpEL expression. Inside #{...}, the new int[]{...} syntax creates an actual int array and Spring passes the result into the constructor parameter of type int[].

Reference arrays can be used similarly:

    @Value("#{new java.lang.String[]{'VN', 'SG', 'TH'}}")
    private String[] supportedRegions;

Arrays are suitable when configuration has a stable number of elements and the bean specifically needs an array type. If the list needs to change flexibly or requires add/remove operations, consider binding the configuration to a List using configuration properties.

You should not put important configuration values into fixed SpEL strings if they need to change independently. In that case, use a property source or configuration properties to manage the data; SpEL should only handle the expression part that is truly necessary.

## 8. Evaluating inline arrays with ExpressionParser

You can create and evaluate arrays directly in Java:

    ExpressionParser parser = new SpelExpressionParser();

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    Expression expression =
            parser.parseExpression("new int[]{10, 20, 30}");

    int[] values = expression.getValue(context, int[].class);

    int firstValue = values[0];

StandardEvaluationContext is used because the new syntax is an object-creation feature of SpEL. SimpleEvaluationContext intentionally restricts advanced features and does not support constructor references like the standard context.

If you only create an inline list:

    Expression listExpression =
            parser.parseExpression("{10, 20, 30}");

    java.util.List<?> values =
            listExpression.getValue(context, java.util.List.class);

then the result is a List rather than an int[]. The target type in getValue helps Java receive the exact result type that the application expects.

In a real application, parse configuration expressions once at startup or when loading rules, then reuse the Expression. There is no need to recreate the parser and parse the same string on every request if the expression does not change.

## 9. Nested arrays and multidimensional structures

Java supports multidimensional arrays by using multiple pairs of square brackets in the type declaration. In SpEL, when you need to represent matrix-style data, clearly define the element type and each dimension before using it.

Example of creating a two-dimensional array with two rows and three columns:

    new int[2][3]

Each element of the outer array is an int array with three elements. The initial values are 0.

If the data has an irregular structure, such as each row having a different number of elements, Java represents it as an array of arrays. In that situation, each row must be initialized and checked according to the actual data. You should not assume every row has the same length just because the variable is declared as a two-dimensional array.

For nested data that only needs iterating or filtering, nested inline lists may be easier to read. Only create multidimensional arrays when the Java contract actually requires an array type and the size of each dimension is already determined.

## 10. Choosing an array or a List?

| Criterion | Array | List |
|---|---|---|
| Data type | Fixed element type | Collection containing objects |
| Size | Fixed after creation | Can change with a mutable List |
| Element access | Use [index] | Use [index] in SpEL or get(index) |
| Add/remove elements | Cannot change length | May support add/remove depending on implementation |
| Primitives | Can use int[], double[] directly | List contains wrappers such as Integer, Double |
| Passing to Java API | Fits array parameters | Fits Collection/List parameters |

Use an array when you need a specific type such as int[], byte[], or String[], or when an API accepts an array parameter. Use a List when you need flexible collection operations, data filtering and transformation, or when the number of elements may change.

Do not choose an array just because the syntax looks more like Java. Base the choice on the type that the component receiving the result needs to use.

## 11. Common errors when creating inline arrays

| Expression or situation | Cause | Resolution |
|---|---|---|
| {1, 2, 3} when Java expects int[] | Inline list creates a List | Use new int[]{1, 2, 3} |
| new int[3]{1, 2, 3} | Mixing size syntax and initializer | Use new int[]{1, 2, 3} |
| new int[]{1, 'two'} | Element incompatible with int type | Convert and validate data beforehand |
| new int[-1] | Negative size | Check that size is non-negative |
| #codes[5] on an array with only three elements | Index out of bounds | Check length before accessing |
| Assigning null to an int[] element | Primitives cannot hold null | Use Integer[] if null is a valid state |
| Creating an array with new in SimpleEvaluationContext | Context does not support constructor references | Use an appropriate context and restrict access permissions |

When an error occurs, determine whether it happened at the parse or evaluate step. Syntax errors usually relate to brackets, types, or initializers. Evaluation errors may relate to element conversion, size, object creation permissions, or index access.

## 12. Safety controls when using the new operator

Creating an inline array uses SpEL's new syntax. The new operator can also be used to invoke constructors of Java classes. Therefore, untrusted expressions can broaden object-creation permissions if evaluated in a context with broad capabilities.

Some principles:

- Only evaluate expressions controlled by the application or a trusted configuration source.
- Do not accept raw SpEL strings from external users and evaluate them arbitrarily.
- Use a defined element type; avoid allowing expressions to pick arbitrary classes.
- Choose an EvaluationContext with the minimal set of features that meets the requirement.
- Validate the size and element data before creating large arrays.
- Handle parse errors, conversion errors, and memory allocation errors explicitly.

Large arrays can consume significant memory. If the size comes from dynamic data, enforce business limits in Java before passing the value into the expression.

## Conclusion

To create an inline Java array in SpEL, use the syntax new elementType[]{...} when you want to initialize specific elements, or new elementType[size] when you want to create an array by size and receive default values. The syntax {...} alone creates an inline List, not a Java array.

The element type determines what data the array can hold: primitives cannot hold null, while reference arrays can hold null. After creation, an array has a fixed size and is accessed using 0-based indexing. Choose an array when a Java API requires the exact array type; if you need a flexible collection, use a List. When evaluating expressions with the new operator, choose an appropriate context and only process expressions from trusted sources.