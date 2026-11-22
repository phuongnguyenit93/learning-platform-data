# The rectangle and square counterexample in Java OOP

In geometry, **a square is a special case of a rectangle**: both have four right angles, while a square also requires all four sides to be equal. However, when translating this mathematical statement into Java:

~~~java
class Square extends Rectangle {
    // ...
}
~~~

we can create a design that **compiles but violates its behavioral contract**.

The issue is not geometric knowledge. It is **the client-facing contract** exposed by `Rectangle`. If a rectangle allows its width and height to be changed **independently**, then a square cannot simultaneously satisfy both requirements:

1. Changing the width must not silently change the height, and vice versa.
2. After every valid operation, width must equal height.

This well-known counterexample illustrates **the “is-a” relationship** and **the Liskov Substitution Principle (LSP)**: *a subclass must be usable wherever clients rely on its superclass contract without violating promised behavior*.

## 1. The real issue is the `Rectangle` contract

Suppose a graphics system has a **resizable** `Rectangle` class. We publish this contract:

| Operation | Input conditions | Guarantee after success |
|---|---|---|
| `new Rectangle(w, h)` | `w > 0`, `h > 0` | Width is `w`, height is `h` |
| `setWidth(w)` | `w > 0` | New width equals `w`; **height stays unchanged** |
| `setHeight(h)` | `h > 0` | New height equals `h`; **width stays unchanged** |
| `getWidth()` | None | Returns current width |
| `getHeight()` | None | Returns current height |
| `area()` | None | Returns width × height |

The superclass invariant:

\[
width > 0 \quad\text{and}\quad height > 0
\]

For any valid `Rectangle` object, the two statements:

~~~java
rectangle.setWidth(5);
rectangle.setHeight(3);
~~~

must produce dimensions **5 × 3** and area **15**.

This is not merely an implementation's “coding style”; it is **what clients are entitled to expect** when the contract specifies independent setters.

## 2. Runnable Java example: inheritance violates the contract

Save the file as **`DemoBad.java`**. The program compiles and runs on Java 17+. It intentionally contains an **inheritance design flaw** to demonstrate the problem.

~~~java
public class DemoBad {
    public static void main(String[] args) {
        Rectangle rectangle = new Rectangle(2, 2);
        Rectangle squareAsRectangle = new Square(2);

        System.out.println(
                "Rectangle: " + resizeAndCalculate(rectangle)
        );
        System.out.println(
                "Square: " + resizeAndCalculate(squareAsRectangle)
        );

        System.out.println(
                "Rectangle giữ hợp đồng: "
                + respectsIndependentSetters(new Rectangle(2, 2))
        );
        System.out.println(
                "Square giữ hợp đồng: "
                + respectsIndependentSetters(new Square(2))
        );
    }

    // Client chỉ biết kiểu Rectangle.
    private static int resizeAndCalculate(Rectangle rectangle) {
        rectangle.setWidth(5);
        rectangle.setHeight(3);
        return rectangle.area();
    }

    // Contract test thu gọn cho hai setter độc lập.
    private static boolean respectsIndependentSetters(Rectangle rectangle) {
        int oldHeight = rectangle.getHeight();
        rectangle.setWidth(5);

        if (rectangle.getWidth() != 5
                || rectangle.getHeight() != oldHeight) {
            return false;
        }

        int oldWidth = rectangle.getWidth();
        rectangle.setHeight(3);

        return rectangle.getHeight() == 3
                && rectangle.getWidth() == oldWidth;
    }
}

class Rectangle {
    private int width;
    private int height;

    Rectangle(int width, int height) {
        // Không gọi setter có thể bị override trong constructor.
        requirePositive(width);
        requirePositive(height);
        this.width = width;
        this.height = height;
    }

    public int getWidth() {
        return width;
    }

    public int getHeight() {
        return height;
    }

    public void setWidth(int width) {
        requirePositive(width);
        this.width = width;
    }

    public void setHeight(int height) {
        requirePositive(height);
        this.height = height;
    }

    public int area() {
        return Math.multiplyExact(width, height);
    }

    private static void requirePositive(int value) {
        if (value <= 0) {
            throw new IllegalArgumentException(
                    "Kích thước phải lớn hơn 0"
            );
        }
    }
}

class Square extends Rectangle {
    Square(int side) {
        super(side, side);
    }

    @Override
    public void setWidth(int side) {
        super.setWidth(side);
        super.setHeight(side); // Giữ hai cạnh bằng nhau.
    }

    @Override
    public void setHeight(int side) {
        super.setHeight(side);
        super.setWidth(side);  // Giữ hai cạnh bằng nhau.
    }
}
~~~

Run:

~~~bash
javac DemoBad.java
java DemoBad
~~~

Output:

~~~text
Rectangle: 15
Square: 9
Rectangle giữ hợp đồng: true
Square giữ hợp đồng: false
~~~

### Why is the result 9 instead of 15?

The `resizeAndCalculate` function receives only a `Rectangle` reference. It does not know whether the caller supplies a regular `Rectangle` or a `Square`.

With `new Rectangle(2, 2)`:

1. `setWidth(5)` → width = 5; height remains 2.
2. `setHeight(3)` → height = 3; width remains 5.
3. `area()` → 5 × 3 = **15**.

With `new Square(2)`, Java invokes **overridden methods of the runtime object**:

1. `setWidth(5)` → `Square.setWidth` changes **both** sides to 5.
2. `setHeight(3)` → `Square.setHeight` changes **both** sides to 3.
3. `area()` → 3 × 3 = **9**.

~~~mermaid
flowchart TD
    A["Client nhận Rectangle"] --> B["setWidth(5)"]
    B --> C["setHeight(3)"]
    C --> D{"Đối tượng thực tế?"}
    D -->|"Rectangle"| E["width=5, height=3<br/>area=15"]
    D -->|"Square"| F["width=3, height=3<br/>area=9"]
    F --> G["Sai hợp đồng<br/>setter độc lập"]
~~~

There are **no Java syntax errors**: `Square` overrides validly, maintains `public` access, and returns the correct `void` type. Nevertheless, **the behavioral contract is violated**.

Note: the class name `Square` does not cause the compiler to prove geometric theorems automatically. The conflict appears when the client's setter calls occur after construction and must be identified through design and testing. The `Rectangle` constructor **validates and assigns fields directly**, avoiding calls to overridable setters before subclass construction completes. Thus, the example isolates the violation of the client-call contract.

## 3. Where is the Liskov Substitution Principle violated?

The **Liskov Substitution Principle** requires that a subtype not make programs using the supertype incorrect, as long as those programs rely only on valid supertype guarantees.

This counterexample conflicts at two levels.

### 3.1. The subclass changes a postcondition

The `Rectangle.setWidth(w)` contract states:

> After a successful call, the width equals `w` and **height remains unchanged**.

But `Square.setWidth(w)` also changes the height. It has **weakened or violated the guarantee after the call** (*postcondition*) of the superclass.

Similarly, `Square.setHeight(h)` also changes width and violates the postcondition of `Rectangle.setHeight(h)`.

This matters more than both methods being named `setWidth` or sharing signatures.

### 3.2. Subtype invariants conflict with supertype capabilities

Invariant of `Square`:

\[
width = height > 0
\]

Invariant of `Rectangle`:

\[
width > 0,\quad height > 0
\]

Considering invariants alone, `Square` has a **stricter** condition that is compatible with valid `Rectangle` values. The problem lies in **the transformations permitted by the supertype**.

`Rectangle` permits dimensions of `5 × 3`. But `Square` cannot represent those dimensions while remaining a square.

To preserve `width == height`, `Square` must change setter semantics. To preserve independent setter semantics, `Square` must stop being square after some operations.

**No implementation can satisfy both contracts simultaneously** if the mutable design with independent setters remains unchanged.

## 4. Could throwing exceptions for unequal sides fix the design?

A common proposal is:

~~~java
@Override
public void setWidth(int width) {
    if (width != getHeight()) {
        throw new IllegalArgumentException(
                "Hình vuông phải có hai cạnh bằng nhau"
        );
    }
    super.setWidth(width);
}
~~~

This preserves the square invariant but **does not solve substitutability**.

For example, on `Rectangle(2, 2)`, `setWidth(5)` is valid because `5 > 0`. But the same call on `Square(2)` throws.

The subtype has **strengthened the precondition** by requiring `width == getHeight()` when the supertype does not.

Under contract design, subtypes must not arbitrarily require **stronger** input conditions or provide **weaker** output guarantees than the parent contract.

| `Square` implementation | Preserves the square invariant? | Preserves the independent-setter contract of `Rectangle`? |
|---|---|---|
| Change both sides in every setter | Yes | **No** |
| Reject a one-sided change that would produce unequal sides | Yes | **No** |
| Change only one side as `Rectangle` does | **No** | Yes for setters, but no longer a `Square` |
| Remove the two setters from the shared contract and design a different abstraction | Possible | **Possible**, under a suitable new contract |

You cannot “fix” an LSP violation by throwing additional `UnsupportedOperationException` errors for operations that the superclass promises to support.

## 5. A mathematical relationship is not automatically a good type relationship

The mathematical statement:

> A square is a rectangle with equal sides.

differs from the OOP statement:

> Every operation offered by a **mutable Rectangle object** works on a **mutable Square object** with the same meaning.

Several cases should be distinguished:

- **Pure geometry:** a square belongs to the set of rectangles when a rectangle is defined by four right angles.
- **Immutable shape objects:** they can share capabilities such as `area()` and `perimeter()`.
- **Mutable objects with independent setters:** a Square cannot preserve the same resizing contract as a Rectangle.
- **Read-only objects:** if the API only offers queries such as `area()`, `width()`, and `height()`, there is no conflict from independent setters. Other query contracts must still be preserved.

**Lesson:** choose `extends` based on **observable behavior and client contracts**, not just class names or the phrase “A is a B in the real world.”

## 6. Better design: an interface exposing only shape-measurement capabilities

If clients only need area calculations, they should not depend on an API for modifying width and height.

Represent the shapes as two independent **immutable value objects** that implement the same `Shape` interface.

Save as **`DemoGood.java`** (Java 17+):

~~~java
public class DemoGood {
    public static void main(String[] args) {
        Shape rectangle = new RectShape(5, 3);
        Shape square = new SquareShape(3);

        show(rectangle);
        show(square);

        RectShape original = new RectShape(5, 3);
        RectShape changed = original.withWidth(7);

        System.out.println(
                "Original: " + original.width() + " x "
                + original.height()
        );
        System.out.println(
                "Changed: " + changed.width() + " x "
                + changed.height()
        );
    }

    private static void show(Shape shape) {
        System.out.println(shape.name()
                + ": area=" + shape.area());
    }
}

interface Shape {
    String name();
    long area();
}

record RectShape(long width, long height) implements Shape {
    RectShape {
        if (width <= 0 || height <= 0) {
            throw new IllegalArgumentException(
                    "Chiều rộng và chiều cao phải dương"
            );
        }
    }

    @Override
    public String name() {
        return "Rectangle";
    }

    @Override
    public long area() {
        return Math.multiplyExact(width, height);
    }

    // Tạo một RectShape mới, không sửa object ban đầu.
    public RectShape withWidth(long newWidth) {
        return new RectShape(newWidth, height);
    }

    public RectShape withHeight(long newHeight) {
        return new RectShape(width, newHeight);
    }
}

record SquareShape(long side) implements Shape {
    SquareShape {
        if (side <= 0) {
            throw new IllegalArgumentException(
                    "Cạnh hình vuông phải dương"
            );
        }
    }

    @Override
    public String name() {
        return "Square";
    }

    @Override
    public long area() {
        return Math.multiplyExact(side, side);
    }

    public SquareShape withSide(long newSide) {
        return new SquareShape(newSide);
    }
}
~~~

Run:

~~~bash
javac DemoGood.java
java DemoGood
~~~

Output:

~~~text
Rectangle: area=15
Square: area=9
Original: 5 x 3
Changed: 7 x 3
~~~

### Why does this design avoid the same flaw?

`Shape` promises only what both shape types can fulfill:

- `name()` returns a meaningful shape name.
- `area()` returns the area for valid dimensions.

It **does not promise** that all shapes have two independent dimensions or allow width/height changes through setters.

`RectShape` and `SquareShape` fulfill the same `Shape` role without inheriting one another's state or implementation.

The records store immutable component values. To “change dimensions,” they return a new object whose constructor validates the new values. `SquareShape` therefore offers only `withSide()`, avoiding the pretense of supporting independent `withWidth()` changes.

`Math.multiplyExact` prevents silent overflow. If an area exceeds the `long` range, it throws `ArithmeticException`. This must be considered if the `area()` contract permits very large dimensions.

~~~mermaid
classDiagram
    class Shape {
        <<interface>>
        +name() String
        +area() long
    }
    class RectShape {
        +width() long
        +height() long
        +withWidth(long) RectShape
        +withHeight(long) RectShape
        +area() long
    }
    class SquareShape {
        +side() long
        +withSide(long) SquareShape
        +area() long
    }
    Shape <|.. RectShape
    Shape <|.. SquareShape
~~~

Using a record is not “the only correct solution.” The main idea is to **narrow the common contract to genuinely shared capabilities** instead of forcing squares to follow an unsuitable setter API.

## 7. What if mutable shapes are still needed?

Real graphics systems may need dragging, resizing, and in-place dimension changes. This counterexample does not require prohibiting mutable objects.

One approach is to separate **the shared contract** from **specialized editing contracts**.

~~~java
interface AreaMeasurable {
    long area();
}

interface RectangleResizer {
    void setWidth(long width);
    void setHeight(long height);
}

interface SquareResizer {
    void setSide(long side);
}
~~~

- A mutable rectangle can implement `AreaMeasurable` and `RectangleResizer`.
- A mutable square can implement `AreaMeasurable` and `SquareResizer`.
- A client that only calculates area depends on `AreaMeasurable`.
- A client that needs to change width **independently** depends on `RectangleResizer`, without requiring squares to do so.

Implement the two classes independently or use **composition** to reuse area calculations/dimension validation. There is no need for `Square extends Rectangle` merely to reuse a few lines of code.

The key is not to make `Square` implement `RectangleResizer` and then either throw an error or silently change height contrary to its promise.

### Can an API for proportional resizing be shared?

Yes, **if the contract is designed accordingly**. For example, an interface offering only:

~~~java
interface Scalable {
    void scaleBy(double factor);
}
~~~

If both shapes support proportional scaling with `factor > 0`, it may be reasonable for both to implement `Scalable`.

However, rounding, dimensions of 0, overflow, and other rules must be explicitly defined. For integer dimensions, noninteger scale factors may lose precision: a real implementation needs a consistent guarantee.

**Substitutability depends on the chosen contract**, not on a slogan about whether a square should inherit from a rectangle.

## 8. When might `Square extends Rectangle` still be acceptable?

Not every model using `Square extends Rectangle` is categorically wrong. Examine **the capabilities** provided by `Rectangle`.

For instance, if `Rectangle` is immutable and only exposes width/height and area queries, then `Square` may be a behavioral subtype without conflicting setter contracts. However:

- Constructors and invariants must ensure that `Square` remains square.
- No inherited method may allow turning a square into a nonsquare shape.
- Other read APIs such as `equals()`, `hashCode()`, `compareTo()`, or `perimeter()` must also be considered if they are part of the parent contract.
- If inheritance makes evolution difficult, separate types implementing the same `Shape` interface may remain simpler and clearer.

**The proper conclusion is not “Square can never be Rectangle,” but “Square cannot substitute for Rectangle when the Rectangle contract permits changing two dimensions independently.”**

## 9. What can Java's type system check, and what can it not?

This counterexample illustrates the compiler's limits:

~~~java
Rectangle value = new Square(2); // Upcasting: hợp lệ.
value.setWidth(5);               // Hợp lệ về mặt chữ ký.
value.setHeight(3);              // Hợp lệ về mặt chữ ký.
~~~

Java knows `Square` is a subtype of `Rectangle` because of `extends`, and that both public methods exist. Java **does not prove** the postcondition that “setting width leaves height unchanged.”

What can be checked?

| Check | Can the Java compiler usually do this? | What else is needed? |
|---|---|---|
| Assign a subtype to a supertype | Yes | Correctly designed subtyping |
| Override method signatures and accessibility | Yes, especially with `@Override` | Tests of actual meaning |
| Ensure `setWidth` leaves `height` unchanged | Not automatically | Contract tests, code review, API design |
| Ensure `Square` always has equal sides | Not automatically | Invariants, validation, tests |
| Prove subtype does not strengthen preconditions | Cannot prove this generally | Contract documentation and tests |
| Prove client code remains correct when using a subtype | Cannot prove this generally | Substitution tests through the supertype |

Thus, a well-designed inheritance hierarchy often includes **contract tests**: the same test suite is applied to every subtype expected to be substitutable.

For example, `respectsIndependentSetters` in `DemoBad.java` is a small contract test. It clearly demonstrates how superclass and subclass behavior differs for the same calls.

## 10. Testing the counterexample systematically

When assessing a subclass, test **what code using the superclass is entitled to expect**, rather than checking only a final value in one case.

For mutable `Rectangle`, useful checks include:

~~~java
static void verifyRectangleContract(Rectangle rectangle) {
    rectangle.setWidth(7);
    int oldHeight = rectangle.getHeight();

    rectangle.setWidth(5);

    if (rectangle.getWidth() != 5) {
        throw new AssertionError("Sai chiều rộng sau setWidth");
    }
    if (rectangle.getHeight() != oldHeight) {
        throw new AssertionError(
                "setWidth đã tự ý thay đổi chiều cao"
        );
    }

    int oldWidth = rectangle.getWidth();
    rectangle.setHeight(4);

    if (rectangle.getHeight() != 4) {
        throw new AssertionError("Sai chiều cao sau setHeight");
    }
    if (rectangle.getWidth() != oldWidth) {
        throw new AssertionError(
                "setHeight đã tự ý thay đổi chiều rộng"
        );
    }
}
~~~

Place this method in `DemoBad` or a test class that can access `Rectangle`, then call:

~~~java
verifyRectangleContract(new Rectangle(2, 2)); // Thành công.
verifyRectangleContract(new Square(2));       // AssertionError.
~~~

The second call fails at `setWidth`, because `Square` changes the height as well.

This is not a test of whether “the square has the correct area.” The value 9 returned by `Square.area()` for a 3×3 square is **mathematically correct**. The error is that an instance presented as a `Rectangle` does not preserve the independent-setter contract.

A practical contract test should also cover boundaries (0, negative numbers, numeric type limits, exceptions) if the published contract includes those rules.

## 11. Should clients detect Square with `instanceof`?

A common workaround:

~~~java
static int resize(Rectangle shape) {
    if (shape instanceof Square) {
        // Xử lý hình vuông riêng.
        shape.setWidth(3);
        return shape.area();
    }

    shape.setWidth(5);
    shape.setHeight(3);
    return shape.area();
}
~~~

This **avoids the error in one place** but introduces design problems:

1. The client must know the concrete `Square` subtype.
2. When `FixedRatioRectangle` or another type appears, the client must add a special branch.
3. Other code accepting `Rectangle` can still violate the contract.
4. The fix is in the client, while **the superclass contract and subtype relationship remain inconsistent**.

`instanceof` is not always bad. It is useful in some deliberate type-classification tasks. But using it **repeatedly to repair behavior that a subtype should provide correctly** signals that the inheritance model needs to change.

## 12. Comparing design alternatives

| Option | Preserves a true square? | Satisfies independent Rectangle setters? | Assessment |
|---|---|---|---|
| `Square extends MutableRectangle` with both setters updating both sides | Yes | No | **LSP counterexample** |
| `Square extends MutableRectangle` rejecting setters that violate its invariant | Yes | No | **Strengthens preconditions** |
| `Square extends MutableRectangle` with one-sided setters | No | Yes | Violates the Square invariant |
| Independent classes implementing `Shape.area()` | Yes | Not required | Suitable shared contract |
| Two immutable classes returning new objects on resizing | Yes | No contradictory setters | Easier invariants and testing |
| Mutable rectangles and squares with separate resizing APIs | Yes | Only rectangles need two independent setters | Clear role separation |
| Immutable `Square` as subtype of read-only immutable `Rectangle` | Possible | Not applicable | Feasible if **every** superclass contract is preserved |

A pragmatic option for graphics applications is:

- Shared types/contracts expose capabilities such as `area()`, `bounds()`, and `render()`.
- Each shape maintains its own invariant and resizing rules.
- Use composition when only computations or rendering components need reuse.
- Avoid inheriting an overly broad mutable API that the subtype cannot fulfill.

## 13. Self-assessment exercises

**Question 1.** In `DemoBad`, why does `Square` return area 9 instead of 15 after `setWidth(5)` and `setHeight(3)`?

**Answer:** The setters are overridden to maintain equal sides. Ultimately both width and height equal 3. Area 9 is correct for a 3×3 square, but wrong under the `Rectangle` contract allowing independent changes to dimensions.

**Question 2.** A `Square` throws an exception if `setWidth(w)` differs from its current height. Does this solve LSP?

**Answer:** No. For `Rectangle`, every `w > 0` is valid; the subtype adds the condition `w == height`. This strengthens its precondition.

**Question 3.** If `Rectangle` only exposes `area()` and has no setter, is substituting `Square` necessarily wrong?

**Answer:** No. If both types fulfill all promises of the read-only abstraction, there is no conflict from independent setters. Examine the actual contract, not just shape names.

**Question 4.** Would `private` fields in `Rectangle` automatically fix the error?

**Answer:** No. `private` protects direct field access, but a public setter overridden with different semantics still violates clients' behavioral expectations. Field encapsulation does not replace sound contract design.

**Question 5.** Should you use `extends` solely to reuse a few lines of area-calculation code?

**Answer:** Not when the behavioral relationship is unsuitable. A shared interface, utility method, collaborator, or composition can reuse logic without adopting the wrong superclass contract.

**Question 6.** Which part of LSP is violated when `Square.setWidth` also changes height?

**Answer:** The postcondition of `Rectangle.setWidth` promises that height remains unchanged after setting width. The subclass does not preserve that promise.

## Conclusion to remember

The **Rectangle–Square** counterexample does not deny the geometric fact that “a square is a rectangle.” It shows that **software type relationships must be evaluated using observable operations and guarantees that clients rely on**.

If `Rectangle` allows width and height to change independently, `Square` cannot both inherit those behaviors correctly and maintain the invariant of equal sides. Review the contract from the client's perspective, use contract tests to detect violations, and design small abstractions that express appropriate roles. **Use a subtype relationship only when the child object can genuinely replace the supertype under its published promises.**
