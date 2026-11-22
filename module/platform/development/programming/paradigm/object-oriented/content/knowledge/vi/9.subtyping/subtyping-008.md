# Phản ví dụ hình chữ nhật và hình vuông trong Java OOP

Trong hình học, **hình vuông là một trường hợp đặc biệt của hình chữ nhật**: cả hai đều có bốn góc vuông, và hình vuông có thêm điều kiện bốn cạnh bằng nhau. Tuy nhiên, khi chuyển phát biểu toán học này sang mã Java:

~~~java
class Square extends Rectangle {
    // ...
}
~~~

ta có thể tạo ra một thiết kế **biên dịch được nhưng sai về hành vi**.

Vấn đề không nằm ở kiến thức hình học. Nó nằm ở **hợp đồng sử dụng** mà kiểu `Rectangle` công bố. Nếu một hình chữ nhật cho phép thay đổi chiều rộng và chiều cao **độc lập**, thì hình vuông không thể đồng thời giữ hai yêu cầu sau:

1. Thay chiều rộng không tự ý đổi chiều cao, và ngược lại.
2. Sau mọi thao tác hợp lệ, chiều rộng luôn bằng chiều cao.

Đây là phản ví dụ nổi tiếng giúp hiểu **quan hệ “là một” (is-a)** và **Nguyên tắc thay thế Liskov (Liskov Substitution Principle – LSP)**: *một lớp con phải có thể dùng thay lớp cha trong những ngữ cảnh dựa vào hợp đồng lớp cha, mà không làm sai các điều đã được bảo đảm*.

## 1. Bài toán thật sự là hợp đồng của `Rectangle`

Giả sử hệ thống đồ họa có một lớp `Rectangle` **có thể thay đổi kích thước**. Ta công bố hợp đồng như sau:

| Thao tác | Điều kiện đầu vào | Cam kết sau khi thành công |
|---|---|---|
| `new Rectangle(w, h)` | `w > 0`, `h > 0` | Chiều rộng `w`, chiều cao `h` |
| `setWidth(w)` | `w > 0` | Chiều rộng mới bằng `w`; **chiều cao không đổi** |
| `setHeight(h)` | `h > 0` | Chiều cao mới bằng `h`; **chiều rộng không đổi** |
| `getWidth()` | Không | Trả chiều rộng hiện tại |
| `getHeight()` | Không | Trả chiều cao hiện tại |
| `area()` | Không | Trả tích chiều rộng × chiều cao |

Bất biến của lớp cha:

\[
width > 0 \quad\text{và}\quad height > 0
\]

Với bất kỳ đối tượng `Rectangle` hợp lệ, hai câu lệnh:

~~~java
rectangle.setWidth(5);
rectangle.setHeight(3);
~~~

phải dẫn đến kích thước **5 × 3**, diện tích **15**.

Đó không chỉ là “cách viết code” của một implementation: nó là **điều mà code sử dụng quyền kỳ vọng**, nếu hợp đồng định nghĩa hai setter độc lập.

## 2. Ví dụ Java chạy được: kế thừa gây vi phạm hợp đồng

Lưu file **`DemoBad.java`**. Chương trình này biên dịch và chạy được với Java 17+. Nó cố ý chứa một lỗi **thiết kế kế thừa** để quan sát hiện tượng.

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

Chạy:

~~~bash
javac DemoBad.java
java DemoBad
~~~

Kết quả:

~~~text
Rectangle: 15
Square: 9
Rectangle giữ hợp đồng: true
Square giữ hợp đồng: false
~~~

### Vì sao nhận được 9 thay vì 15?

Hàm `resizeAndCalculate` chỉ nhận một tham chiếu kiểu `Rectangle`. Nó không biết người gọi đưa vào `Rectangle` thông thường hay `Square`.

Với `new Rectangle(2, 2)`:

1. `setWidth(5)` → chiều rộng = 5; chiều cao vẫn = 2.
2. `setHeight(3)` → chiều cao = 3; chiều rộng vẫn = 5.
3. `area()` → 5 × 3 = **15**.

Với `new Square(2)`, Java thực hiện **phương thức override của đối tượng thực tế**:

1. `setWidth(5)` → `Square.setWidth` đổi **cả hai** cạnh thành 5.
2. `setHeight(3)` → `Square.setHeight` đổi **cả hai** cạnh thành 3.
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

**Không có lỗi cú pháp Java** ở đây: `Square` override hợp lệ, giữ quyền truy cập `public` và trả về đúng kiểu `void`. Tuy nhiên, **hợp đồng hành vi đã bị phá vỡ**.

Lưu ý: tên class `Square` không làm compiler tự động kiểm tra các định lý hình học. Hai lần gọi setter sau khi đối tượng hoàn thành khởi tạo là điểm phát sinh mâu thuẫn mà developer phải nhận ra qua thiết kế và kiểm thử. Constructor của `Rectangle` được viết **kiểm tra và gán field trực tiếp**, tránh gọi setter overridable khi constructor lớp con chưa hoàn tất; như vậy phản ví dụ tập trung đúng vào sự vi phạm hợp đồng của các lời gọi client.

## 3. Vi phạm nguyên tắc Liskov ở chỗ nào?

**Nguyên tắc thay thế Liskov** yêu cầu một subtype không khiến những chương trình dùng supertype bị sai, miễn là chương trình đó chỉ dựa vào các cam kết hợp lệ của supertype.

Với phản ví dụ trên, xung đột xảy ra ở hai mức.

### 3.1. Lớp con thay đổi postcondition

Hợp đồng `Rectangle.setWidth(w)` nói:

> Sau khi gọi thành công, chiều rộng bằng `w` và **chiều cao giữ nguyên**.

Nhưng `Square.setWidth(w)` làm chiều cao đổi theo. Nó đã **làm yếu hoặc vi phạm điều bảo đảm sau lời gọi** (*postcondition*) của lớp cha.

Tương tự, `Square.setHeight(h)` đổi cả chiều rộng, vi phạm postcondition của `Rectangle.setHeight(h)`.

Điều này quan trọng hơn việc cả hai phương thức đều có tên `setWidth` hoặc có cùng chữ ký.

### 3.2. Bất biến của subtype xung đột với khả năng của supertype

Bất biến của `Square`:

\[
width = height > 0
\]

Bất biến của `Rectangle`:

\[
width > 0,\quad height > 0
\]

Nhìn riêng các bất biến, điều kiện của `Square` **chặt hơn** và không mâu thuẫn với các giá trị hợp lệ của `Rectangle`. Vấn đề nằm ở các **phép biến đổi mà supertype cho phép**.

`Rectangle` cho phép đạt trạng thái kích thước `5 × 3`. Nhưng `Square` không thể có trạng thái đó mà vẫn là hình vuông.

Nếu cố giữ `width == height`, `Square` phải đổi ngữ nghĩa setter. Nếu giữ ngữ nghĩa setter độc lập, `Square` sẽ không còn là hình vuông sau một số thao tác.

**Không tồn tại implementation thỏa đồng thời cả hai hợp đồng này** nếu vẫn giữ nguyên thiết kế mutable với hai setter độc lập.

## 4. Có thể sửa bằng cách ném exception khi hai cạnh khác nhau không?

Một đề xuất thường gặp là:

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

Cách này giữ được invariant hình vuông, nhưng **không giải quyết tính thay thế**.

Ví dụ, đối với `Rectangle(2, 2)`, `setWidth(5)` hợp lệ vì `5 > 0`. Nhưng với `Square(2)`, cùng lời gọi lại ném lỗi.

Tức là subtype đã **siết chặt precondition**: đòi thêm `width == getHeight()` trong khi supertype không đòi.

Trong thiết kế hợp đồng, subtype không nên tự ý yêu cầu điều kiện đầu vào **mạnh hơn** hợp đồng cha hoặc cung cấp bảo đảm đầu ra **yếu hơn** hợp đồng cha.

| Cách viết `Square` | Có giữ bất biến hình vuông? | Có giữ hợp đồng setter độc lập của `Rectangle`? |
|---|---|---|
| Đổi cả hai cạnh trong mỗi setter | Có | **Không** |
| Từ chối đổi một cạnh khi làm hai cạnh khác nhau | Có | **Không** |
| Chỉ đổi một cạnh như `Rectangle` | **Không** | Có cho setter, nhưng mất nghĩa `Square` |
| Bỏ hai setter khỏi hợp đồng chung và thiết kế abstraction khác | Có thể | **Có thể**, với hợp đồng mới phù hợp |

Không thể “chữa” lỗi LSP bằng việc ném thêm `UnsupportedOperationException` cho những thao tác mà lớp cha đã hứa hỗ trợ.

## 5. Quan hệ toán học không tự động là quan hệ kiểu tốt

Phát biểu toán học:

> Hình vuông là hình chữ nhật có các cạnh bằng nhau.

khác với phát biểu OOP:

> Mọi thao tác được cung cấp cho một **đối tượng Rectangle mutable** đều có thể sử dụng với một **đối tượng Square mutable** và giữ nguyên ý nghĩa.

Một số tình huống cần phân biệt:

- **Hình học thuần túy:** square thuộc tập rectangle nếu định nghĩa rectangle có bốn góc vuông.
- **Đối tượng bất biến biểu diễn hình:** có thể là một trường hợp đặc biệt với tập khả năng chung `area()`, `perimeter()`.
- **Đối tượng mutable với hai setter độc lập:** Square không thể giữ cùng hợp đồng thay đổi kích thước với Rectangle.
- **Đối tượng chỉ đọc:** nếu API chỉ cung cấp truy vấn như `area()`, `width()`, `height()`, thì không có xung đột do setter độc lập. Tuy nhiên, vẫn phải giữ toàn bộ hợp đồng truy vấn khác nếu có.

**Bài học:** quyết định `extends` dựa trên **hành vi quan sát được và hợp đồng sử dụng**, không chỉ dựa vào tên lớp hoặc câu “trong đời thực A là một B”.

## 6. Thiết kế tốt hơn: một interface chỉ nói về khả năng đo hình

Nếu client chỉ cần tính diện tích, không nên bắt nó phụ thuộc vào API thay đổi chiều rộng/chiều cao.

Ta có thể biểu diễn hai hình dạng như hai **value object bất biến** độc lập, cùng thực hiện interface `Shape`.

Lưu vào **`DemoGood.java`**, Java 17+:

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

Chạy:

~~~bash
javac DemoGood.java
java DemoGood
~~~

Kết quả:

~~~text
Rectangle: area=15
Square: area=9
Original: 5 x 3
Changed: 7 x 3
~~~

### Vì sao cách này không mắc cùng lỗi?

`Shape` chỉ cam kết những gì cả hai loại hình đều đáp ứng:

- `name()` trả tên loại hình có ý nghĩa.
- `area()` trả diện tích theo các tham số hợp lệ.

Nó **không hứa** rằng mọi hình đều có hai chiều độc lập hoặc cho phép cập nhật chiều rộng/chiều cao bằng setter.

`RectShape` và `SquareShape` cài đặt cùng một vai trò `Shape`, nhưng không cần kế thừa implementation và trạng thái của nhau.

Các record giữ dữ liệu bất biến về mặt component. Để “thay kích thước”, chúng trả một đối tượng mới với các giá trị được constructor kiểm tra. Khi đó `SquareShape` chỉ có thao tác `withSide()`, tránh giả vờ hỗ trợ `withWidth()` thay đổi độc lập.

`Math.multiplyExact` ngăn overflow âm thầm. Nếu diện tích vượt phạm vi `long`, phương thức sẽ ném `ArithmeticException`. Đây là điều phải tính đến nếu hợp đồng `area()` được dùng cho dữ liệu rất lớn.

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

Không phải “giải pháp chính xác duy nhất” là dùng record. Ý chính là **thu hẹp hợp đồng chung thành những khả năng thật sự chia sẻ được**, thay vì ép hình vuông tuân theo một API setter không phù hợp.

## 7. Nếu vẫn cần các hình có thể thay đổi thì thiết kế thế nào?

Có hệ thống đồ họa thật sự cần thao tác kéo thả, resize và thay kích thước tại chỗ. Không phải cứ gặp phản ví dụ này là phải cấm mutable object.

Một cách là phân tách **hợp đồng chung** khỏi **hợp đồng chỉnh sửa riêng**.

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

- Đối tượng hình chữ nhật mutable có thể thực hiện `AreaMeasurable` và `RectangleResizer`.
- Đối tượng hình vuông mutable có thể thực hiện `AreaMeasurable` và `SquareResizer`.
- Một client chỉ tính diện tích phụ thuộc vào `AreaMeasurable`.
- Một client cần thay chiều rộng **độc lập** phụ thuộc vào `RectangleResizer`, và không yêu cầu đối tượng hình vuông phải làm điều ấy.

Có thể triển khai độc lập hai class, hoặc dùng **composition** để tái sử dụng công thức tính diện tích/thẩm định kích thước. Không cần đặt `Square extends Rectangle` chỉ để tái sử dụng vài dòng mã.

Điều quan trọng là không ép `Square` implements `RectangleResizer` rồi ném lỗi hoặc tự sửa chiều cao trái lời hứa.

### Một API resize với tỉ lệ cố định có thể dùng chung không?

Có thể, **nếu hợp đồng được thiết kế phù hợp**. Ví dụ một interface chỉ có:

~~~java
interface Scalable {
    void scaleBy(double factor);
}
~~~

Nếu cả hai loại hình đều hỗ trợ phép phóng to/thu nhỏ đồng dạng với `factor > 0`, việc cùng implements `Scalable` có thể hợp lý.

Nhưng phải xác định rõ cách làm tròn, trường hợp kích thước bằng 0, overflow và các quy tắc khác. Với kích thước nguyên, phóng tỉ lệ không nguyên có thể gây mất chính xác: một ví dụ triển khai thật cần cam kết nhất quán về điều này.

**Tính thay thế phụ thuộc hợp đồng được chọn**, không phụ thuộc một khẩu hiệu “hình vuông phải hay không được kế thừa hình chữ nhật”.

## 8. Khi nào `Square extends Rectangle` vẫn có thể chấp nhận được?

Không phải mọi mô hình có quan hệ `Square extends Rectangle` đều sai tuyệt đối. Cần xem `Rectangle` định nghĩa **khả năng nào**.

Ví dụ nếu `Rectangle` là kiểu bất biến, chỉ cho đọc chiều rộng/chiều cao và diện tích, thì `Square` có thể là subtype về hành vi mà không đụng vào mâu thuẫn setter. Tuy nhiên:

- Các constructor và invariant phải đảm bảo `Square` luôn là hình vuông.
- Không được để lộ phương thức nào từ lớp cha cho phép biến một square thành hình không vuông.
- Các API đọc khác như `equals()`, `hashCode()`, `compareTo()` hoặc `perimeter()` phải được xem xét nếu hợp đồng cha công bố chúng.
- Nếu quan hệ kế thừa khiến thiết kế khó thay đổi, hai kiểu riêng cùng implements `Shape` vẫn có thể đơn giản và rõ hơn.

**Kết luận đúng không phải “Square không bao giờ là Rectangle”, mà là “Square không thay thế được Rectangle nếu hợp đồng Rectangle cho phép chỉnh hai chiều độc lập”.**

## 9. Hệ thống kiểu Java kiểm tra được gì, không kiểm tra được gì?

Ví dụ phản chứng cho thấy giới hạn của compiler:

~~~java
Rectangle value = new Square(2); // Upcasting: hợp lệ.
value.setWidth(5);               // Hợp lệ về mặt chữ ký.
value.setHeight(3);              // Hợp lệ về mặt chữ ký.
~~~

Java biết `Square` là subtype của `Rectangle` vì `extends`, và biết hai phương thức công khai tồn tại. Java **không chứng minh** postcondition “đặt width không đổi height”.

Các loại kiểm tra:

| Kiểm tra | Java compiler thường làm được? | Cần thêm gì? |
|---|---|---|
| Kiểu con có thể gán cho kiểu cha | Có | Thiết kế subtype đúng nghĩa |
| Method override đúng chữ ký và quyền truy cập | Có, đặc biệt khi dùng `@Override` | Kiểm thử ý nghĩa thực tế |
| `setWidth` không đổi `height` | Không tự động | Contract test, code review, thiết kế API |
| `Square` luôn giữ hai cạnh bằng nhau | Không tự động | Invariant, validation, kiểm thử |
| Lời gọi không siết precondition so với lớp cha | Không chứng minh tổng quát | Tài liệu hợp đồng và test |
| Code client dùng subtype vẫn đúng | Không chứng minh tổng quát | Kiểm thử thay thế qua supertype |

Vì thế, một hệ thống có thiết kế kế thừa tốt thường đi kèm **contract tests**: cùng một bộ kiểm thử đặt lên mọi subtype dự kiến có thể thay thế nhau.

Ví dụ `respectsIndependentSetters` trong `DemoBad.java` là một contract test rất nhỏ. Nó minh họa rõ hành vi lớp cha và lớp con khác nhau tại cùng một lời gọi.

## 10. Kiểm thử phản ví dụ một cách hệ thống

Khi đánh giá một lớp con, hãy kiểm tra **những điều mà code dùng lớp cha được quyền kỳ vọng**, không chỉ kiểm tra giá trị cuối cùng trên một case.

Với `Rectangle` mutable, nên có những kiểm tra như:

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

Đặt phương thức này trong `DemoBad` hoặc một test class có quyền sử dụng `Rectangle`, rồi gọi:

~~~java
verifyRectangleContract(new Rectangle(2, 2)); // Thành công.
verifyRectangleContract(new Square(2));       // AssertionError.
~~~

Lời gọi thứ hai thất bại ngay ở bước `setWidth`, vì `Square` tự thay đổi chiều cao.

Đây không phải kiểm thử “hình vuông có diện tích đúng hay không”; `Square.area()` trả 9 cho hình vuông 3×3 là **đúng toán học**. Thứ sai là việc một instance được quảng bá là `Rectangle` lại không giữ được hợp đồng setter độc lập.

Một contract test thực tế cần thêm tình huống biên (0, số âm, giới hạn kiểu số, ngoại lệ) nếu hợp đồng công bố các quy tắc đó.

## 11. Có nên phát hiện Square bằng `instanceof` trong client?

Một giải pháp tình thế dễ gặp:

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

Cách này **né lỗi ở một nơi**, nhưng tạo vấn đề thiết kế:

1. Client phải biết cụ thể có subtype `Square`.
2. Khi xuất hiện `FixedRatioRectangle` hoặc kiểu mới, client phải thêm nhánh đặc biệt.
3. Nơi khác nhận `Rectangle` vẫn có thể vi phạm hợp đồng.
4. Cách sửa được thực hiện ở phía người dùng, trong khi **hợp đồng lớp cha và quan hệ subtype vẫn bất nhất**.

`instanceof` không phải lúc nào cũng xấu. Nó hữu ích trong một số bài toán phân loại kiểu có chủ đích. Nhưng dùng nó **liên tục để sửa các hành vi mà subtype đáng ra phải cung cấp đúng** là dấu hiệu mô hình kế thừa cần được thay đổi.

## 12. So sánh các hướng thiết kế

| Phương án | Có giữ hình vuông đúng nghĩa? | Có đáp ứng setter Rectangle độc lập? | Đánh giá |
|---|---|---|---|
| `Square extends MutableRectangle`, hai setter đổi đồng thời hai cạnh | Có | Không | **Phản ví dụ LSP** |
| `Square extends MutableRectangle`, từ chối setter phá invariant | Có | Không | **Siết precondition** |
| `Square extends MutableRectangle`, setter đổi một cạnh | Không | Có | Mất invariant của Square |
| Hai class độc lập cùng implements `Shape.area()` | Có | Không bắt buộc | Thiết kế hợp đồng chung phù hợp |
| Hai class immutable, thao tác thay kích thước tạo object mới | Có | Không có setter trái ngữ nghĩa | Dễ giữ invariant và kiểm thử |
| Mutable rectangle và mutable square có API resize riêng | Có | Chỉ rectangle cần hai setter độc lập | Phân tách vai trò rõ |
| Immutable `Square` là subtype của immutable `Rectangle` chỉ đọc | Có thể | Không áp dụng | Khả thi nếu **mọi** hợp đồng cha đều được giữ |

Một lựa chọn thực dụng cho ứng dụng đồ họa là:

- Kiểu/hợp đồng chung nêu khả năng như `area()`, `bounds()`, `render()`.
- Từng hình giữ invariant và quy tắc resize phù hợp riêng.
- Dùng composition khi chỉ muốn tái sử dụng tính toán hoặc thành phần hiển thị.
- Tránh kế thừa một API mutable quá rộng khi subtype không hỗ trợ đúng.

## 13. Bài tập tự kiểm tra

**Câu 1.** Trong `DemoBad`, vì sao `Square` trả về diện tích 9 thay vì 15 sau `setWidth(5)` và `setHeight(3)`?

**Đáp án:** Hai setter được override để giữ hai cạnh bằng nhau. Cuối cùng cả width và height đều bằng 3. Kết quả 9 đúng cho hình vuông 3×3, nhưng sai với hợp đồng `Rectangle` cho phép thay hai chiều độc lập.

**Câu 2.** Một `Square` ném exception nếu `setWidth(w)` khác chiều cao hiện tại. Điều này giải quyết LSP chưa?

**Đáp án:** Chưa. Đối với `Rectangle`, mọi `w > 0` đều hợp lệ; subtype tự thêm điều kiện `w == height`. Đây là siết precondition.

**Câu 3.** Nếu `Rectangle` chỉ cung cấp `area()` và không có setter, việc dùng `Square` thay thế có nhất thiết sai không?

**Đáp án:** Không. Nếu hai kiểu cùng giữ mọi cam kết của abstraction chỉ đọc, không có mâu thuẫn setter độc lập. Cần xét hợp đồng thực tế, không chỉ tên hình.

**Câu 4.** Dùng `private` field trong `Rectangle` có tự giải quyết lỗi không?

**Đáp án:** Không. `private` giúp bảo vệ truy cập dữ liệu trực tiếp, nhưng nếu public setter được override để thay đổi ý nghĩa, client vẫn gặp lỗi hành vi. Đóng gói field không thay cho thiết kế hợp đồng đúng.

**Câu 5.** Có nên dùng `extends` chỉ để tận dụng vài dòng code tính diện tích?

**Đáp án:** Không nên nếu quan hệ hành vi không thật sự phù hợp. Có thể dùng interface chung, utility method, một collaborator hoặc composition để tái sử dụng logic mà không gánh thêm hợp đồng cha sai.

**Câu 6.** Phần nào của LSP bị vi phạm trong `Square.setWidth` đổi luôn chiều cao?

**Đáp án:** Postcondition của `Rectangle.setWidth` là chiều cao giữ nguyên sau khi đặt chiều rộng. Subclass không giữ được lời hứa này.

## Kết luận cần nhớ

Phản ví dụ **Rectangle–Square** không phủ nhận quan hệ hình học “hình vuông là hình chữ nhật”. Nó minh họa rằng **quan hệ kiểu trong phần mềm được đánh giá bằng các thao tác và cam kết mà client có thể quan sát**.

Nếu `Rectangle` cho phép thay đổi width và height độc lập, `Square` không thể vừa kế thừa đúng hai hành vi ấy vừa duy trì invariant hai cạnh bằng nhau. Hãy xem xét hợp đồng từ góc nhìn người sử dụng, dùng contract tests để phát hiện vi phạm và thiết kế abstraction nhỏ, đúng vai trò. **Chỉ dùng quan hệ subtype khi đối tượng con thật sự có thể thay thế kiểu cha theo những lời hứa mà kiểu cha công bố.**