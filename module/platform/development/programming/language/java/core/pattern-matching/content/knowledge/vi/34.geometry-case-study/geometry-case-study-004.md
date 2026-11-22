# Tính diện tích bằng record pattern

## 1. Bài toán hình học và mục tiêu của case study

Giả sử một ứng dụng Java cần biểu diễn nhiều hình phẳng và tính **diện tích** theo loại hình: hình tròn, hình chữ nhật và tam giác. Cách truyền thống có thể dùng chuỗi `if (shape instanceof ...)`, ép kiểu thủ công, sau đó lấy bán kính hoặc cạnh tương ứng. Với **record patterns** trong Java 21, ta có thể diễn đạt trực tiếp cấu trúc của từng hình trong một `switch`.

Ý tưởng:

```java
return switch (shape) {
    case Circle(var center, double radius) ->
            Math.PI * radius * radius;
    case Rectangle(double width, double height) ->
            width * height;
    // Các trường hợp khác ...
};
```

Đây chỉ là đoạn minh họa nằm trong phương thức; các kiểu `Circle`, `Rectangle` sẽ được khai báo đầy đủ bên dưới.

Case study này hướng tới năm kỹ năng:

1. **Mô hình hóa domain hình học** bằng `sealed interface` và các `record`.
2. **Dùng record pattern** để kiểm tra kiểu đồng thời lấy component mà không ép kiểu thủ công.
3. **Dùng nested record pattern** để trích xuất tọa độ ba đỉnh của tam giác.
4. **Viết công thức diện tích đúng** và xử lý giá trị `null`, số âm, `NaN`, vô cực, trường hợp suy biến và tràn số.
5. **Kiểm thử đúng ngữ nghĩa**, bao gồm giá trị biên và sai số số thực, không chỉ xem code có chạy hay không.

Trong bài, các tọa độ, bán kính, cạnh và diện tích đều dùng `double`. Đơn vị có thể hiểu là mét và mét vuông nếu tất cả dữ liệu đầu vào đều dùng mét. Một công thức đúng vẫn cho kết quả vô nghĩa nếu trộn centimet với mét mà không chuyển đổi.

## 2. Công thức diện tích cần biết

| Hình | Dữ liệu đầu vào | Công thức | Điều kiện quan trọng |
| --- | --- | --- | --- |
| Hình tròn | Bán kính `r` | `A = πr²` | `r > 0` và hữu hạn; tâm không ảnh hưởng diện tích. |
| Hình chữ nhật | Chiều rộng `w`, chiều cao `h` | `A = w × h` | `w > 0`, `h > 0` và hữu hạn. |
| Tam giác từ đáy/chiều cao | Đáy `b`, chiều cao vuông góc `h` | `A = b × h / 2` | `h` phải là **đường cao**, không phải cạnh xiên. |
| Tam giác từ ba điểm | `P₁(x₁,y₁)`, `P₂(x₂,y₂)`, `P₃(x₃,y₃)` | `A = \| (x₂-x₁)(y₃-y₁) - (y₂-y₁)(x₃-x₁) \| / 2` | Ba đỉnh phải có tọa độ hữu hạn; ba đỉnh thẳng hàng cho `A = 0`. |

Ở trường hợp tam giác theo ba điểm, biểu thức trong dấu trị tuyệt đối là **định thức/cross product hai chiều** của hai vector `P₁P₂` và `P₁P₃`. Giá trị có dấu phụ thuộc chiều sắp xếp đỉnh, nhưng diện tích hình học thông thường phải **không âm**, nên cần `Math.abs`.

Ví dụ với ba đỉnh `(0,0)`, `(4,0)` và `(0,3)`:

```text
A = abs((4 - 0) * (3 - 0) - (0 - 0) * (0 - 0)) / 2
  = abs(12 - 0) / 2
  = 6
```

Đây là tam giác vuông có hai cạnh góc vuông dài `4` và `3`. Nếu dịch cả ba đỉnh thêm cùng một vector, diện tích vẫn bằng `6`. Tính bất biến khi tịnh tiến là một tính chất hữu ích để kiểm thử.

## 3. Thiết kế Shape bằng sealed interface và record

Một mô hình đủ nhỏ cho case study:

```java
sealed interface Shape permits Circle, Rectangle, Triangle {}

record Point(double x, double y) {}

record Circle(Point center, double radius) implements Shape {}

record Rectangle(double width, double height) implements Shape {}

record Triangle(Point a, Point b, Point c) implements Shape {}
```

Đây là khai báo minh họa, **chưa có validation**. Phần chương trình hoàn chỉnh sẽ thêm constructor để ngăn nhiều dữ liệu bất hợp lệ.

### Vì sao chọn record?

Record mô tả dữ liệu có các component cố định: `Point` có `x` và `y`, `Circle` có `center` và `radius`, `Rectangle` có `width` và `height`, `Triangle` có ba điểm. Java tạo sẵn constructor, accessor, `equals`, `hashCode` và `toString` phù hợp với record, trừ khi ta tùy chỉnh những thành phần được phép.

Accessor mang tên component, chẳng hạn:

```java
Point p = new Point(2, 3);
double x = p.x();
double y = p.y();
```

Trong Java 21, **record pattern** dùng metadata của record và các accessor tương ứng để kiểm tra và lấy giá trị component.

### Vì sao chọn sealed interface?

`Shape` là kiểu chung và chỉ cho phép trực tiếp ba record `Circle`, `Rectangle` và `Triangle` triển khai nó. Vì record mặc nhiên là `final`, tập subtype của ví dụ được kiểm soát.

Compiler có thể kiểm tra **exhaustiveness** của `switch expression` khi ta xử lý hết các nhánh đã được `permits`. Nếu sau này domain thêm `Ellipse`, những `switch` không có `default` mà thiếu nhánh mới có thể được compiler báo cần cập nhật khi biên dịch lại. Điều này giúp tránh việc một hình mới bị âm thầm gán diện tích `0`.

Tuy nhiên, `sealed` **không tự xác thực** rằng chiều rộng dương, tọa độ hữu hạn, hay ba đỉnh tam giác tạo thành một hình không suy biến. Đó là trách nhiệm của constructor hoặc tầng nhập dữ liệu.

## 4. Tính diện tích bằng switch và record patterns

Hàm lõi trong Java 21 có thể viết như sau:

```java
static double area(Shape shape) {
    double result = switch (shape) {
        case Circle(var center, double radius) ->
                Math.PI * radius * radius;

        case Rectangle(double width, double height) ->
                width * height;

        case Triangle(
                Point(double ax, double ay),
                Point(double bx, double by),
                Point(double cx, double cy)) ->
                Math.abs((bx - ax) * (cy - ay)
                        - (by - ay) * (cx - ax)) / 2.0;

        case null ->
                throw new IllegalArgumentException(
                        "shape must not be null");
    };

    if (!Double.isFinite(result)) {
        throw new ArithmeticException("area is not finite");
    }
    return result;
}
```

Đây là phương thức độc lập về logic, nhưng cần các record/interface được khai báo ở cùng ngữ cảnh. Bản đầy đủ ở phần 8 có thêm validation.

### Nhánh Circle

`case Circle(var center, double radius)` là **record pattern** với hai component. Biến `center` được suy luận kiểu `Point`, còn `radius` có kiểu `double`. Công thức chỉ dùng bán kính vì **dời tâm không làm thay đổi diện tích hình tròn**.

Mã nguồn không cần cast như `(Circle) shape`. Khi case khớp, trình biên dịch biết component `radius` có kiểu `double`.

Lưu ý về hiệu năng: pattern này vẫn phân rã cả `center` dù giá trị không dùng trong công thức. Với nhiệm vụ chỉ cần bán kính, một type pattern `case Circle circle -> Math.PI * circle.radius() * circle.radius()` cũng có thể phù hợp; đừng cố dùng record pattern cho mọi tình huống nếu không làm mã rõ hơn.

### Nhánh Rectangle

`case Rectangle(double width, double height)` kiểm tra đúng record `Rectangle` và lấy hai component theo thứ tự khai báo. `width * height` trả diện tích; hai chiều dương được kiểm tra bởi constructor trong ví dụ đầy đủ.

Không nhầm `record Rectangle(double width, double height)` với một rectangle có góc xoay hoặc với hai điểm đường chéo mà chưa có định nghĩa hình học rõ. Trong bài, `width` và `height` là độ dài hai cạnh vuông góc đã được cho.

### Nhánh Triangle: nested record pattern

`Triangle` có ba component kiểu `Point`. Ta viết:

```java
case Triangle(
        Point(double ax, double ay),
        Point(double bx, double by),
        Point(double cx, double cy)) ->
        Math.abs((bx - ax) * (cy - ay)
                - (by - ay) * (cx - ax)) / 2.0;
```

Đây là **nested record pattern**: Java kiểm tra kiểu `Triangle`, rồi phân rã từng `Point` để ràng buộc sáu tọa độ. Các tên `ax`, `ay`, `bx`, `by`, `cx`, `cy` chỉ có ý nghĩa trong nhánh đã khớp.

Không có cú pháp `new Point(...)` ở đây vì pattern **không tạo object mới**. Nó kiểm tra đối tượng đang có và lấy component qua accessor.

Trong chương trình đầy đủ, constructor của `Triangle` yêu cầu cả ba `Point` không null, còn `Point` yêu cầu tọa độ hữu hạn. Điều này bảo đảm dữ liệu đầu vào bình thường của model phù hợp với nested pattern.

### Nhánh null và tính đầy đủ

`case null` biểu diễn chính sách **không chấp nhận Shape null** bằng một exception có thông báo rõ. Đừng mặc định `default` sẽ xử lý null giống vậy.

Với tập `Shape` đã `sealed` và ba subtype đều là record, `switch expression` có thể xử lý đủ các biến thể. Ta không cần `default -> 0.0`, vì nếu có hình chưa được xử lý thì trả về diện tích bằng 0 sẽ che giấu lỗi thiết kế hoặc thay đổi domain.

## 5. Validation: hình hợp lệ là điều kiện của công thức

Một công thức diện tích chính xác vẫn có thể nhận dữ liệu không có nghĩa về hình học.

### Tọa độ hữu hạn

Một `Point` dùng `double` có thể chứa `Double.NaN` hoặc vô cực nếu không kiểm tra. Các giá trị này làm phép tính diện tích cho kết quả không thể dùng như một số thực hình học. Có thể xác thực ngay trong compact constructor:

```java
record Point(double x, double y) {
    Point {
        if (!Double.isFinite(x) || !Double.isFinite(y)) {
            throw new IllegalArgumentException(
                    "coordinates must be finite");
        }
    }
}
```

Đoạn trên là khai báo record minh họa. Compact constructor được chạy khi tạo record theo cách thông thường và sẽ từ chối giá trị không hữu hạn trước khi object hợp lệ được tạo.

### Bán kính và cạnh phải dương

`Circle` cần tâm không null và `radius > 0`; `Rectangle` cần hai cạnh `> 0`:

```java
record Circle(Point center, double radius) implements Shape {
    Circle {
        java.util.Objects.requireNonNull(center, "center");
        if (!Double.isFinite(radius) || radius <= 0.0) {
            throw new IllegalArgumentException(
                    "radius must be positive and finite");
        }
    }
}

record Rectangle(double width, double height) implements Shape {
    Rectangle {
        if (!Double.isFinite(width) || width <= 0.0
                || !Double.isFinite(height) || height <= 0.0) {
            throw new IllegalArgumentException(
                    "rectangle dimensions must be positive and finite");
        }
    }
}
```

Việc cấm bán kính và kích thước bằng `0` là **quyết định của domain trong bài này**. Một phần mềm CAD có thể cho phép hình suy biến để biểu diễn trạng thái đang kéo thả; khi đó hợp đồng validation có thể khác.

### Ba đỉnh tam giác và trường hợp suy biến

`Triangle` yêu cầu ba điểm tồn tại:

```java
record Triangle(Point a, Point b, Point c) implements Shape {
    Triangle {
        java.util.Objects.requireNonNull(a, "a");
        java.util.Objects.requireNonNull(b, "b");
        java.util.Objects.requireNonNull(c, "c");
    }
}
```

Nếu ba điểm thẳng hàng, công thức định thức cho diện tích `0.0`. Trong ví dụ này, **tam giác suy biến được chấp nhận** và `area` trả `0.0`; đây là một chính sách minh họa hợp lý cho các bài toán dữ liệu hình học. Nếu domain yêu cầu tam giác phải có diện tích dương, cần thêm validation bằng một tiêu chí được định nghĩa rõ, đồng thời xem xét sai số dấu phẩy động khi kiểm tra tính thẳng hàng.

Không nên gộp tất cả lỗi thành `default -> 0`; phải phân biệt **hình hợp lệ nhưng diện tích bằng 0 theo hợp đồng** với **hình không xác định hoặc dữ liệu đầu vào sai**.

## 6. Chi tiết số thực: Double, tràn số và sai số

### Double không biểu diễn mọi số chính xác

`double` dùng số chấm động nhị phân IEEE 754. Một số giá trị thập phân không có biểu diễn nhị phân chính xác; `Math.PI` là một xấp xỉ của số π; phép nhân/trừ có thể tích lũy sai số.

Vì vậy, khi so sánh kết quả tính diện tích, **không nên dùng `expected == actual` một cách máy móc** với các công thức có π hoặc nhiều phép toán trên `double`. Hãy so sánh sai số theo ngưỡng có ý nghĩa đối với đơn vị và kích thước dữ liệu.

Ví dụ trong test:

```java
static void assertNear(double expected, double actual) {
    double tolerance = 1e-9 * Math.max(1.0, Math.abs(expected));
    if (!Double.isFinite(actual)
            || Math.abs(expected - actual) > tolerance) {
        throw new AssertionError(
                "expected " + expected + ", actual " + actual);
    }
}
```

Hàm này là mẫu kiểm tra phù hợp với những diện tích cỡ vừa của bài; giá trị tolerance cần được chọn theo yêu cầu chính xác của ứng dụng. Đối với các bài toán hình học tính toán đòi hỏi tính bền vững số cao, có thể cần thuật toán định hướng/định thức ổn định hơn, không chỉ điều chỉnh một epsilon cố định.

### Giá trị component hữu hạn chưa bảo đảm diện tích hữu hạn

`new Rectangle(1e308, 1e308)` có hai cạnh hữu hạn theo `Double.isFinite`, nhưng tích `width * height` có thể tràn thành `Infinity`. Vì vậy, ví dụ có kiểm tra kết quả cuối:

```java
if (!Double.isFinite(result)) {
    throw new ArithmeticException("area is not finite");
}
```

Kiểm tra này không tự làm phép tính trở nên chính xác; nó chỉ **không để kết quả vô cực/NaN bị trả như diện tích hợp lệ**.

### Công thức tam giác có thể mất độ chính xác với tọa độ cực lớn

Biểu thức:

```java
Math.abs((bx - ax) * (cy - ay)
        - (by - ay) * (cx - ax)) / 2.0
```

thường đơn giản và đúng cho dữ liệu ở phạm vi bình thường. Với tọa độ rất lớn hoặc các vector gần song song, phép trừ và nhân có thể gây **cancellation**, tràn số hoặc mất chữ số có nghĩa. Sau cùng, `Math.abs` không khôi phục thông tin đã mất.

Nếu ứng dụng xử lý bản đồ quy mô lớn, CAD chính xác cao hoặc các hình gần suy biến, cân nhắc thư viện hình học với các phép thử định hướng robust, hệ tọa độ thích hợp và dữ liệu đã được chuẩn hóa. Đây là vấn đề số học, không phải bản thân record pattern.

### Tránh tràn số nguyên trước khi đổi sang double

Nếu component dùng `int` và ta viết:

```java
int width = 100_000;
int height = 100_000;
double area = width * height;
```

thì phép nhân hai `int` được thực hiện **trước**, có thể tràn số ngay cả khi đích nhận kết quả là `double`. Có thể chuyển một toán hạng sang double **trước khi nhân**:

```java
double area = (double) width * height;
```

Trong case study chính, `Rectangle` khai báo `double width` và `double height` nên không gặp hiện tượng overflow kiểu `int` đó, nhưng vẫn có giới hạn phạm vi của `double`.

## 7. Một chương trình Java 21 hoàn chỉnh

Lưu nội dung dưới tên **`ShapeAreaRecordPatternDemo.java`**. File này có thể biên dịch độc lập với JDK 21, không cần preview hoặc thư viện ngoài.

```java
import java.util.Locale;
import java.util.Objects;

public class ShapeAreaRecordPatternDemo {
    sealed interface Shape permits Circle, Rectangle, Triangle {}

    record Point(double x, double y) {
        Point {
            if (!Double.isFinite(x) || !Double.isFinite(y)) {
                throw new IllegalArgumentException(
                        "coordinates must be finite");
            }
        }
    }

    record Circle(Point center, double radius) implements Shape {
        Circle {
            Objects.requireNonNull(center, "center");
            if (!Double.isFinite(radius) || radius <= 0.0) {
                throw new IllegalArgumentException(
                        "radius must be positive and finite");
            }
        }
    }

    record Rectangle(double width, double height) implements Shape {
        Rectangle {
            if (!Double.isFinite(width) || width <= 0.0
                    || !Double.isFinite(height) || height <= 0.0) {
                throw new IllegalArgumentException(
                        "rectangle dimensions must be positive and finite");
            }
        }
    }

    record Triangle(Point a, Point b, Point c) implements Shape {
        Triangle {
            Objects.requireNonNull(a, "a");
            Objects.requireNonNull(b, "b");
            Objects.requireNonNull(c, "c");
        }
    }

    static double area(Shape shape) {
        double result = switch (shape) {
            case Circle(var center, double radius) ->
                    Math.PI * radius * radius;

            case Rectangle(double width, double height) ->
                    width * height;

            case Triangle(
                    Point(double ax, double ay),
                    Point(double bx, double by),
                    Point(double cx, double cy)) ->
                    Math.abs((bx - ax) * (cy - ay)
                            - (by - ay) * (cx - ax)) / 2.0;

            case null ->
                    throw new IllegalArgumentException(
                            "shape must not be null");
        };

        if (!Double.isFinite(result)) {
            throw new ArithmeticException("area is not finite");
        }
        return result;
    }

    static void printArea(String label, Shape shape) {
        System.out.printf(
                Locale.ROOT, "%s = %.2f%n", label, area(shape));
    }

    public static void main(String[] args) {
        printArea("Circle",
                new Circle(new Point(1, 2), 2));

        printArea("Rectangle", new Rectangle(3, 4));

        printArea("Triangle",
                new Triangle(
                        new Point(0, 0),
                        new Point(4, 0),
                        new Point(0, 3)));

        printArea("Triangle translated",
                new Triangle(
                        new Point(10, 10),
                        new Point(14, 10),
                        new Point(10, 13)));

        printArea("Degenerate triangle",
                new Triangle(
                        new Point(0, 0),
                        new Point(1, 1),
                        new Point(2, 2)));

        printArea("Circle moved",
                new Circle(new Point(100, 200), 2));

        try {
            area(null);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "null -> IllegalArgumentException: "
                            + ex.getMessage());
        }

        try {
            new Circle(new Point(0, 0), -1);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "bad radius -> IllegalArgumentException: "
                            + ex.getMessage());
        }

        try {
            area(new Rectangle(1e308, 1e308));
        } catch (ArithmeticException ex) {
            System.out.println(
                    "overflow -> ArithmeticException: "
                            + ex.getMessage());
        }
    }
}
```

Biên dịch và chạy bằng JDK 21 trở lên:

```bash
javac --release 21 -encoding UTF-8 ShapeAreaRecordPatternDemo.java
java ShapeAreaRecordPatternDemo
```

**Đầu ra chuẩn:**

```text
Circle = 12.57
Rectangle = 12.00
Triangle = 6.00
Triangle translated = 6.00
Degenerate triangle = 0.00
Circle moved = 12.57
null -> IllegalArgumentException: shape must not be null
bad radius -> IllegalArgumentException: radius must be positive and finite
overflow -> ArithmeticException: area is not finite
```

### Phân tích chính xác các trường hợp

**Circle:** bán kính `2` cho diện tích `Math.PI × 4 ≈ 12.56637`, định dạng `%.2f` thành `12.57`. Tâm ở `(1,2)` hoặc `(100,200)` không làm công thức thay đổi.

**Rectangle:** cạnh `3` và `4` tạo diện tích chính xác trong ví dụ là `12`, in `12.00`.

**Triangle:** các điểm `(0,0)`, `(4,0)`, `(0,3)` cho định thức `12`, chia hai là `6`. Bộ ba điểm tịnh tiến tới `(10,10)`, `(14,10)`, `(10,13)` cũng có định thức `12`, nên vẫn `6`.

**Degenerate triangle:** ba điểm `(0,0)`, `(1,1)`, `(2,2)` thẳng hàng. Hai vector cùng phương, định thức bằng `0`, nên diện tích `0.00`; đây là trường hợp được phép bởi validation của bài.

**Null:** `area(null)` chọn `case null` và ném `IllegalArgumentException` với thông báo xác định. Đây là lỗi đầu vào có chủ đích, không phải một subtype `Shape` mới.

**Bad radius:** constructor `Circle` phát hiện `radius <= 0` và từ chối trước khi cần tính diện tích. Nó không tạo object `Circle` hợp lệ với bán kính âm.

**Overflow:** `1e308` vẫn là số `double` hữu hạn, nên constructor `Rectangle` chấp nhận. Nhưng tích hai cạnh vượt phạm vi hữu hạn của `double`; `area` ném `ArithmeticException` thay vì trả vô cực.

Các ví dụ hiển thị diện tích bằng hai chữ số thập phân để người đọc dễ quan sát; trong xử lý nghiệp vụ, phương thức `area` vẫn trả `double` chưa qua làm tròn. Không dùng chuỗi đã định dạng để tiếp tục tính toán chính xác.

## 8. Vì sao record pattern phù hợp với case study này?

### Đọc được hình dạng của dữ liệu ngay tại case

Nhìn vào:

```java
case Rectangle(double width, double height) -> width * height;
```

người đọc thấy ngay: đây là hình chữ nhật, cần hai kích thước và phép nhân. Không phải dò sang nhiều dòng cast, khai báo biến trung gian hoặc accessor.

Với tam giác:

```java
case Triangle(
        Point(double ax, double ay),
        Point(double bx, double by),
        Point(double cx, double cy)) -> ...
```

nested pattern cho thấy ba đỉnh đều là `Point` và giải cấu trúc thành tọa độ. Cách biểu diễn khớp trực tiếp với công thức định thức hai chiều.

### Compiler theo dõi các biến pattern

`width`, `height`, `ax`, `ay` ... có kiểu `double` nhờ cấu trúc record. Chúng chỉ tồn tại ở phạm vi case tương ứng. Không thể đem `radius` của case `Circle` sang case `Rectangle` để sử dụng.

Các case là **switch rules** với `->`, không có fall-through; khi một case đã được chọn, phần tính diện tích của case khác không được chạy.

### Dễ nhận biết thiếu subtype khi mở rộng domain

Nếu mở rộng `Shape` bằng `Ellipse`, một `switch` exhaustive không có `default` là cơ hội để compiler báo thiếu xử lý mới. Đó là lý do tránh viết:

```java
// Không nên lấy 0 làm fallback cho loại hình chưa được xử lý.
default -> 0.0;
```

Đoạn trên là ví dụ nhánh minh họa, không phải chương trình độc lập. Với các bài toán hình học, diện tích bằng 0 có nghĩa riêng (hình suy biến), nên dùng nó thay cho “không biết hình gì” đặc biệt nguy hiểm.

### Không bắt buộc record pattern cho mọi hành vi

Một phương án khác là khai báo `double area()` trong interface `Shape` và để mỗi record triển khai phương thức của mình. Đó là **polymorphism**, cũng có thể là thiết kế tốt nếu tính diện tích là hành vi lõi của mỗi hình và không cần kiểm tra toàn bộ subtype ở một chỗ.

Pattern matching thích hợp khi ta muốn viết một **phép biến đổi/phân loại bên ngoài** cho một tập record đóng; polymorphism có thể hợp lý hơn nếu các kiểu có nhiều hành vi ổn định và cần thêm subtype thường xuyên. Case study dùng record pattern vì trọng tâm là **khớp cấu trúc hình học trong Java 21**, không tuyên bố nó luôn là kiến trúc duy nhất đúng.

## 9. Cải tiến và mở rộng

### 9.1. Tam giác theo đáy và chiều cao

Nếu domain đã biết đáy và **chiều cao vuông góc** chứ không có ba tọa độ, có thể mô hình hóa riêng:

```java
record BaseHeightTriangle(double base, double height) {}
```

Với:

```java
case BaseHeightTriangle(double base, double height) ->
        base * height / 2.0;
```

đây là một nhánh minh họa trong `switch` với selector có kiểu phù hợp. Nếu muốn thêm nó làm `Shape` chính thức, cần điều chỉnh `permits`, validation và mọi nơi đang xử lý hierarchy; không chỉ tự ý thêm một case không khớp type hệ thống.

Chú ý: `height` phải là đường cao vuông góc với đáy. Nếu truyền một cạnh xiên dưới tên `height`, công thức cho kết quả sai về hình học dù mã vẫn biên dịch.

### 9.2. Phân loại hình theo diện tích bằng guard

Có thể kết hợp `when` khi cần phân loại kích thước, ví dụ một hình chữ nhật lớn:

```java
return switch (shape) {
    case Rectangle(double width, double height)
            when width * height >= 100.0 -> "LARGE_RECTANGLE";
    case Rectangle rectangle -> "OTHER_RECTANGLE";
    case null -> "MISSING";
    default -> "OTHER_SHAPE";
};
```

Đây là minh họa một phương thức trả về chuỗi, không phải hàm `area` chính. Guard được xét sau khi record pattern khớp. Với đầu vào không phải `Rectangle`, guard không chạy. Nhánh `Rectangle rectangle` không guard đứng sau để xử lý những rectangle có diện tích nhỏ.

Nếu tính toán diện tích tốn kém, tránh lặp lại phép tính nhiều lần ở các guard; cân nhắc tính `area(shape)` một lần rồi phân loại kết quả, đồng thời giữ chính sách lỗi riêng cho giá trị không hợp lệ hoặc tràn số.

### 9.3. Hình có lỗ hoặc hình phức hợp

Diện tích hình vành khăn có thể là `π(R²-r²)` khi `R >= r >= 0`; diện tích hình phức hợp có thể cần cộng hoặc trừ những vùng chồng nhau. Đừng tự cho rằng cộng diện tích mọi thành phần sẽ luôn đúng: nếu các hình con chồng nhau, tổng diện tích đơn giản có thể **đếm trùng phần giao**.

Khi thêm subtype như `Ring` hay `CompositeShape`, cần định nghĩa rõ invariant và công thức của subtype rồi cập nhật sealed hierarchy cùng kiểm thử. Đây là ví dụ tại sao một tập subtype được kiểm soát giúp nhận diện tác động khi thay đổi domain.

## 10. Kiểm thử công thức, pattern và các bất biến

Một bộ test tốt phải kiểm tra **nhiều khía cạnh khác nhau**:

| Ca test | Đầu vào | Kết quả/ý nghĩa cần kiểm tra |
| --- | --- | --- |
| Tròn, bán kính nhỏ | `Circle(center, 2)` | Diện tích gần `4π`. |
| Tròn tịnh tiến tâm | Cùng bán kính `2`, tâm khác | Diện tích không đổi. |
| Chữ nhật | `Rectangle(3,4)` | Diện tích `12`. |
| Đổi thứ tự hai cạnh | `Rectangle(4,3)` | Diện tích vẫn `12`. |
| Tam giác vuông | `(0,0),(4,0),(0,3)` | Diện tích `6`. |
| Tam giác đổi chiều đỉnh | Đổi `b` và `c` | Diện tích vẫn `6` do `Math.abs`. |
| Tam giác tịnh tiến | Cộng cùng vector vào ba điểm | Diện tích không đổi. |
| Tam giác suy biến | `(0,0),(1,1),(2,2)` | `0` theo chính sách bài này. |
| Tâm/đỉnh null | `Circle(null, 2)` hoặc `Triangle(null, b, c)` | Bị từ chối khi tạo record. |
| Bán kính âm/zero | `radius = -1` hoặc `0` | `IllegalArgumentException`. |
| Tọa độ vô cực/NaN | `Point(Double.NaN, 0)` | `IllegalArgumentException`. |
| Đối tượng Shape null | `area(null)` | `IllegalArgumentException`. |
| Tích diện tích tràn | `Rectangle(1e308,1e308)` | `ArithmeticException`. |

### Unit test mẫu với JUnit Jupiter

Ví dụ dưới đây giả định lớp `ShapeAreaRecordPatternDemo` từ phần 7 có trong cùng package với tệp test. Cần thêm JUnit Jupiter vào build; đây **không phải** tệp có thể biên dịch bằng lệnh `javac` độc lập khi thiếu dependency.

```java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ShapeAreaRecordPatternDemoTest {
    @Test
    void rectangleArea() {
        var rectangle =
                new ShapeAreaRecordPatternDemo.Rectangle(3, 4);
        assertEquals(12.0,
                ShapeAreaRecordPatternDemo.area(rectangle),
                1e-9);
    }

    @Test
    void triangleAreaIsTranslationInvariant() {
        var t1 = new ShapeAreaRecordPatternDemo.Triangle(
                new ShapeAreaRecordPatternDemo.Point(0, 0),
                new ShapeAreaRecordPatternDemo.Point(4, 0),
                new ShapeAreaRecordPatternDemo.Point(0, 3));
        var t2 = new ShapeAreaRecordPatternDemo.Triangle(
                new ShapeAreaRecordPatternDemo.Point(10, 10),
                new ShapeAreaRecordPatternDemo.Point(14, 10),
                new ShapeAreaRecordPatternDemo.Point(10, 13));

        assertEquals(6.0,
                ShapeAreaRecordPatternDemo.area(t1), 1e-9);
        assertEquals(ShapeAreaRecordPatternDemo.area(t1),
                ShapeAreaRecordPatternDemo.area(t2), 1e-9);
    }

    @Test
    void negativeRadiusIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> new ShapeAreaRecordPatternDemo.Circle(
                        new ShapeAreaRecordPatternDemo.Point(0, 0),
                        -1));
    }

    @Test
    void nullShapeIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> ShapeAreaRecordPatternDemo.area(null));
    }
}
```

JUnit có overload `assertEquals(double expected, double actual, double delta)`, giúp kiểm thử số thực theo sai số thay vì so sánh object hoặc chuỗi đã làm tròn.

### Property-based testing

Ngoài các ví dụ cụ thể, có thể kiểm tra các tính chất tổng quát:

- **Không âm:** diện tích của hình hợp lệ không âm theo hợp đồng.
- **Tịnh tiến:** dời tâm hình tròn hay cả ba đỉnh tam giác không làm đổi diện tích.
- **Đổi thứ tự:** hoán đổi chiều rộng/chiều cao hình chữ nhật không đổi tích; đổi thứ tự hai đỉnh tam giác không đổi diện tích tuyệt đối.
- **Co giãn đồng đều:** nếu mọi độ dài nhân với hệ số `k > 0`, diện tích lý tưởng nhân với `k²`, trong phạm vi số học không bị tràn hoặc mất chính xác đáng kể.

Những tính chất này thường bắt được lỗi công thức mà một test với dữ liệu “đẹp” không phát hiện. Khi dùng số thực, cần ngưỡng sai số phù hợp, tránh các giá trị cực đoan nếu phép thử không được thiết kế để xử lý chúng.

## 11. Lỗi phổ biến khi tính diện tích bằng record pattern

### 11.1. Quên Math.abs ở tam giác

`(bx - ax) * (cy - ay) - (by - ay) * (cx - ax)` có thể âm khi thứ tự đỉnh đảo chiều. Nếu mục tiêu là diện tích hình học **không âm**, phải lấy trị tuyệt đối trước khi chia `2`.

### 11.2. Dùng sai dữ liệu: chiều cao không vuông góc với đáy

`base * height / 2` đúng khi `height` là đường cao vuông góc. Nếu người dùng cung cấp độ dài cạnh bất kỳ, cần công thức khác hoặc tọa độ đỉnh. Record pattern giúp đọc component đúng tên, nhưng **không chứng minh ngữ nghĩa của component**.

### 11.3. Coi record pattern là constructor

`case Rectangle(double width, double height)` không tạo `Rectangle` mới và không thay constructor validation. Nó kiểm tra runtime object rồi truy cập các component của record.

### 11.4. Nhầm null selector với null component

`case null` xử lý chính `shape == null`. Trong khi đó, `Triangle(Point(...), ...)` đòi hỏi các component kiểu Point tương ứng khớp; một đỉnh `null` sẽ làm nested pattern không khớp. Trong ví dụ, constructor `Triangle` đã từ chối đỉnh null trước, nên dữ liệu hợp lệ theo model không gặp trường hợp ấy.

Một record với `var` pattern có thể ràng buộc giá trị tham chiếu null; đừng dùng `center.x()` nếu chưa chắc `center` khác null khi model cho phép thiếu tâm.

### 11.5. Dùng default = 0 cho hình chưa biết

Đó là kết quả dễ che lỗi. Nếu thêm subtype mà chưa có công thức, ưu tiên cập nhật `switch` hoặc báo lỗi có ý nghĩa, thay vì trả diện tích 0 giả.

### 11.6. Dùng số nguyên và bị overflow trước khi ép kiểu

`double area = width * height` với `width`/`height` là `int` có thể nhận một giá trị đã tràn số. Ép một toán hạng sang `double` trước phép nhân hoặc chọn kiểu dữ liệu hợp lý.

### 11.7. Quên rằng double có NaN/Infinity

Chỉ kiểm tra `value > 0` không đủ để mô tả mọi chính sách số thực. `Double.isFinite` giúp loại trừ `NaN` và vô cực ở đầu vào; kiểm tra kết quả cuối còn cần thiết khi phép toán có thể overflow.

### 11.8. So sánh double bằng == trong mọi test

Một phép tính có π hoặc nhiều phép nhân/trừ thường tạo sai số dấu phẩy động. Dùng tolerance có ý nghĩa theo quy mô của dữ liệu.

### 11.9. Quá lạm dụng nested pattern

Với domain có record rất sâu và chỉ cần một component, nested pattern dài có thể làm khó đọc hoặc phân rã những component không dùng tới. Có thể dùng type pattern và accessor cần thiết; thiết kế tốt ưu tiên **ý nghĩa code và tính đúng** trước khi tối ưu cú pháp.

### 11.10. Nhầm hiệu năng của record pattern với của công thức

Một phép đo cho thấy hàm diện tích chậm không chứng minh lỗi nằm ở pattern: chi phí có thể nằm ở tính toán số thực, cấp phát object, guard phức tạp hoặc workload kiểm thử. Dùng profiler/JMH nếu thực sự cần phân tích hiệu năng; không suy đoán chỉ từ số dòng Java.

## 12. Bài tập tự kiểm tra

**Câu 1.** Hình tròn có bán kính `3`. Công thức diện tích và giá trị xấp xỉ là gì?

**Đáp án:** `A = π × 3² = 9π ≈ 28.27433388`. Nếu định dạng hai chữ số sau dấu thập phân, được `28.27`.

**Câu 2.** Ba đỉnh `(0,0)`, `(0,4)`, `(3,0)` cho kết quả âm hay dương trước `Math.abs`?

**Đáp án:** Với `a=(0,0)`, `b=(0,4)`, `c=(3,0)`: `(bx-ax)(cy-ay)-(by-ay)(cx-ax) = 0*0 - 4*3 = -12`. Lấy trị tuyệt đối rồi chia hai cho diện tích `6`.

**Câu 3.** Tại sao `case Triangle(Point(double ax, double ay), ... )` được gọi là nested record pattern?

**Đáp án:** Vì pattern ngoài kiểm tra record `Triangle` và mỗi component `Point` tiếp tục được khớp bằng một **record pattern con** để lấy tọa độ.

**Câu 4.** Khi thêm `record Ellipse(double a, double b) implements Shape` vào domain, cần làm gì?

**Đáp án:** Trước hết mở rộng `permits Shape`, định nghĩa invariant `a,b > 0`, bổ sung công thức `A = πab` vào `switch` và thêm test. Với sealed hierarchy, việc chưa xử lý subtype mới trong `switch expression` không có `default` có thể được compiler phát hiện khi biên dịch lại.

**Câu 5.** `Triangle(0,0),(1,1),(2,2)` có phải là lỗi không?

**Đáp án:** Đây là ba điểm thẳng hàng, có diện tích bằng `0`. Có bị từ chối hay không phụ thuộc hợp đồng domain. Chương trình minh họa chấp nhận tam giác suy biến và trả `0.00`.

**Câu 6.** `case Circle(var center, double radius)` có bảo đảm `center != null` không?

**Đáp án:** Bản thân `var center` có thể ràng buộc giá trị tham chiếu null. Trong chương trình này, **constructor `Circle`** có `Objects.requireNonNull(center)` mới là lý do các đối tượng hợp lệ có tâm khác null. Record pattern không thay thế validation.

## 13. Checklist áp dụng thực tế

Trước khi triển khai một bộ tính diện tích sử dụng record patterns:

1. Xác định hệ tọa độ, đơn vị độ dài và đơn vị diện tích thống nhất.
2. Định nghĩa subtype hình và **invariant dữ liệu** rõ ràng; chọn `sealed` khi tập hình thuộc quyền kiểm soát.
3. Ghi đúng công thức toán học; với tam giác theo ba điểm dùng định thức và `Math.abs`.
4. Chọn record pattern/nested record pattern khi giúp người đọc thấy cấu trúc dữ liệu cần xử lý.
5. Kiểm tra `null` ở selector và những component tham chiếu có thể thiếu.
6. Không dùng `default -> 0.0` chỉ để hợp thức hóa một subtype chưa có công thức.
7. Kiểm tra `Double.isFinite` cho dữ liệu và kết quả khi hợp đồng yêu cầu diện tích hữu hạn.
8. Test giá trị mẫu, hình suy biến, đổi thứ tự đỉnh, tịnh tiến và lỗi đầu vào.
9. Dùng tolerance có căn cứ khi so sánh diện tích `double`.
10. Biên dịch với JDK 21 và chạy test; record patterns cùng pattern matching for `switch` đã chính thức từ Java 21, không cần `--enable-preview`.

**Ghi nhớ:** Với Java 21, record pattern giúp viết phép tính diện tích gần với mô hình toán học: `Circle(radius)` dùng `πr²`, `Rectangle(width,height)` dùng `width×height`, còn `Triangle(Point,Point,Point)` dùng định thức tọa độ. **Đúng công thức** chỉ là một phần; **đúng kiểu, đúng null, đúng validation và đúng số học** mới làm bộ tính diện tích đáng tin cậy.
