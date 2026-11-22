# Tách calculation khỏi model khi cần: case study hình học với Java 21 Pattern Matching

## 1. Bài toán thiết kế: hình học là dữ liệu hay phép tính?

Một ứng dụng bản đồ, CAD hoặc dựng hình có các đối tượng: hình tròn, hình chữ nhật và tam giác. Mỗi hình mang **dữ liệu mô tả nó**: tâm và bán kính, gốc và kích thước, hoặc ba đỉnh. Ứng dụng còn phải tính **diện tích, chu vi, đường bao, giao nhau, mức độ gần nhau**, và có thể áp dụng những quy tắc làm tròn hoặc hệ đơn vị khác nhau.

Một thiết kế thường thấy là đặt tất cả phương thức tính trực tiếp vào mỗi model:

```java
record Circle(double radius) {
    double area() {
        return Math.PI * radius * radius;
    }

    double perimeter() {
        return 2 * Math.PI * radius;
    }
}
```

Cách này **không sai**. Khi công thức đơn giản, bất biến và gắn chặt với một giá trị, đặt phương thức thuần trên record có thể rất dễ hiểu. Nhưng nếu nhiều phép tính ngày càng phức tạp, các thuật toán thay đổi theo ngữ cảnh hoặc cần phối hợp nhiều loại hình, model có nguy cơ trở thành nơi chứa quá nhiều chính sách và xử lý kỹ thuật.

Một hướng khác:

- **Model:** định nghĩa hình là gì, trạng thái cần lưu và invariant để tạo một hình hợp lệ.
- **Calculator/service thuần:** tính toán từ model, với giả định đầu vào và chính sách số học được nói rõ.
- **Pattern matching:** điều phối tới công thức tương ứng với loại hình.
- **Application boundary:** chọn hệ đơn vị, format kết quả, lưu dữ liệu, cache hoặc xử lý lỗi hạ tầng.

Ví dụ:

```java
// Minh họa cấu trúc trong một class/service.
double area(Shape shape) {
    return switch (shape) {
        case Circle circle -> circleArea(circle.radius());
        case Rectangle rect -> rect.width() * rect.height();
        case Triangle triangle -> triangleArea(
            triangle.a(), triangle.b(), triangle.c());
    };
}
```

Đoạn trên giả sử `Shape` là một sealed hierarchy đủ ba subtype và các helper đã khai báo. Mỗi case **chọn công thức** chứ không nhúng repository, HTTP, logging hoặc thay đổi state. Model có thể được dùng cho nhiều thuật toán mà không buộc mỗi record chứa tất cả thuật toán.

**Mục tiêu bài:** hiểu **khi nào nên tách calculation khỏi model, khi nào giữ bên trong**, cách thiết kế value record có invariant, cách dùng Java 21 `switch` pattern matching một cách exhaustive, kiểm thử công thức và các vấn đề số học như đơn vị, giá trị suy biến, sai số dấu phẩy động.

Phiên bản: `record` là tính năng chuẩn từ **Java 16**; pattern matching cho `switch` (JEP 441) và record patterns (JEP 440) ổn định từ **Java 21**. Ví dụ chạy độc lập dùng **JDK 21+** và không cần `--enable-preview`.

## 2. Phân biệt state, invariant, calculation và presentation

Bốn trách nhiệm thường bị trộn lẫn:

| Trách nhiệm | Câu hỏi | Ví dụ trong hình học | Vị trí thường phù hợp |
| --- | --- | --- | --- |
| **State** | Đối tượng là gì? | `Circle(center, radius)` | Record/model |
| **Invariant** | Dữ liệu nào tạo thành đối tượng hợp lệ? | Bán kính dương và hữu hạn; tâm không null | Canonical constructor/factory |
| **Calculation** | Có thể suy ra điều gì từ state? | Diện tích, chu vi, khoảng cách, giao nhau | Method thuần trong model **hoặc** calculator riêng |
| **Presentation / I/O** | Kết quả được dùng/hiển thị/lưu thế nào? | Làm tròn 2 chữ số, ghi JSON, vẽ trên màn hình | UI/application/adapter |

Phần dễ nhầm nhất là **invariant so với calculation**. Invariant cần được kiểm tra khi tạo object để ngăn trạng thái vô nghĩa; calculation có thể thực hiện sau đó theo một yêu cầu cụ thể.

Ví dụ, constructor `Circle` kiểm tra `radius > 0` là một phần của model, dù nó có tính toán một phép so sánh. Không phải cứ có toán tử số học là phải chuyển sang calculator. Ngược lại, tính diện tích giao của hai đa giác phụ thuộc thuật toán phức tạp và có thể phải xét tolerance; cách đó thường hợp lý hơn trong service riêng.

### Vì sao không nên tách máy móc?

Nếu chỉ có:

```java
record Square(double side) {
    double area() {
        return side * side;
    }
}
```

và không có chính sách tính toán nào thay đổi, gọi `square.area()` có thể rõ ràng hơn `squareAreaCalculator.calculate(square)`. Tách thành hàng loạt lớp/hàm một dòng chỉ để tuân theo một khẩu hiệu “model chỉ chứa data” đôi khi tạo **anemic domain model** và nhiều tầng điều hướng.

**Tiêu chí đúng là trách nhiệm và biến thiên**, không phải “model tuyệt đối không được có method”.

## 3. Khi nào nên chuyển calculation sang component riêng?

Các dấu hiệu thực tế:

1. **Nhiều thuật toán trên cùng tập shape.** Không chỉ area/perimeter mà còn rasterization, intersection, collision detection, export SVG, clipping, hit testing.
2. **Chính sách có nhiều phiên bản.** Tính trên mặt phẳng Euclid khác với trên tọa độ địa lý; kết quả xấp xỉ khác kết quả cần kiểm soát sai số.
3. **Tính toán liên quan nhiều đối tượng.** Khoảng cách giữa hai shape, giao nhau, hợp/hiệu đa giác; không có một “chủ sở hữu” tự nhiên của logic.
4. **Chi phí cao hoặc tài nguyên bên ngoài.** Phân tích giao cắt trên tập hình lớn, dựng mesh, truy vấn dữ liệu độ cao, GPU, I/O.
5. **Cần test thuật toán độc lập.** So sánh nhiều implementation hoặc benchmark mà không tạo hệ thống ứng dụng đầy đủ.
6. **Đang làm model phụ thuộc framework.** Model giá trị chỉ nên phản ánh state/invariant; không bắt buộc biết DB, logger, mapper, UI hay thư viện đồ họa cụ thể.
7. **Một record phải biết quá nhiều đối tượng không liên quan.** Thêm thuật toán mới luôn đòi sửa nhiều record dù state của chúng không đổi.
8. **Caching/độ chính xác có vòng đời riêng.** Cache theo zoom, hệ tọa độ, tolerance hoặc thiết bị nên có owner và invalidation rõ.

Tuy nhiên, mỗi dấu hiệu cần xem trong ngữ cảnh. Một method thuần, ổn định trên một value type không tự tạo “sai kiến trúc”. Khi chuyển đi, cần hỏi **đối tượng nào sở hữu chính sách** và **sẽ đo lường được lợi ích gì** (testability, reuse, cohesion, dependency control).

## 4. Thiết kế model hình học bằng sealed hierarchy và record

Với Java 21, một lựa chọn gọn là:

```java
sealed interface Shape permits Circle, Rectangle, Triangle {}

record Point(double x, double y) {}

record Circle(Point center, double radius) implements Shape {}

record Rectangle(Point origin, double width, double height)
        implements Shape {}

record Triangle(Point a, Point b, Point c) implements Shape {}
```

Đây là **phác họa type definitions**, chưa có validation. `sealed interface` thể hiện tập subtype biết trước. Mỗi `record` chứa state cần mô tả hình; các component có accessor (`center()`, `radius()`, `a()`...) do compiler sinh.

Đặc tính hữu ích:
- Record cung cấp value equality theo component và `toString` mặc định.
- State của component là final; muốn thay kích thước tạo record mới.
- Sealed hierarchy hỗ trợ **exhaustive `switch`** trên các subtype permitted.
- Pattern matching phân loại không cần `instanceof` rồi cast thủ công.

Nhưng **không nên chỉ khai báo record rỗng cho domain có invariant**. `new Circle(null, -1)` vẫn biên dịch và tạo object nếu constructor không kiểm tra. Model phải quyết định điều gì hợp lệ.

### Constructor bảo vệ invariant, calculator bảo vệ hợp đồng tính

Ví dụ:

```java
record Circle(Point center, double radius) implements Shape {
    Circle {
        java.util.Objects.requireNonNull(center, "center");
        if (!Double.isFinite(radius) || radius <= 0) {
            throw new IllegalArgumentException(
                "radius must be positive and finite");
        }
    }
}
```

Đây là đúng trách nhiệm model: **không tạo Circle với tâm null hoặc bán kính không hợp lệ**.

Với `Point`, hãy kiểm tra `Double.isFinite(x)` và `Double.isFinite(y)` nếu bài toán cần tọa độ hữu hạn. Chỉ dùng `x < min || x > max` có thể bỏ lọt `NaN` vì so sánh với NaN trả false.

**Quan trọng:** Dù tọa độ và kích thước hữu hạn, một phép nhân rất lớn vẫn có thể overflow thành `Infinity`. Constructor chặn NaN/Infinity của input **không tự bảo đảm** mọi kết quả calculation là hữu hạn. Calculator phải có chính sách cho miền số và tolerance nếu domain đòi tính chính xác cao.

## 5. Java 21 Pattern Matching ở ranh giới tính toán

Một calculator có thể dùng `switch expression` trên kiểu `Shape`:

```java
static double area(Shape shape) {
    java.util.Objects.requireNonNull(shape, "shape");

    return switch (shape) {
        case Circle c ->
            Math.PI * c.radius() * c.radius();

        case Rectangle r ->
            r.width() * r.height();

        case Triangle t ->
            triangleArea(t.a(), t.b(), t.c());
    };
}
```

Đoạn minh họa này giả sử `Shape` sealed và `triangleArea` đã có.

### Vì sao type pattern thường đủ?

`case Circle c` ràng buộc một Circle có kiểu chính xác hơn `Shape`; `c.radius()` đã được compiler type-check. Nếu chỉ cần radius, không nhất thiết phải viết `Circle(var center, var radius)` để deconstruct cả center. Bỏ một record pattern quá sâu giúp:
- Giảm coupling vào toàn bộ header;
- Không vô tình thêm ràng buộc non-null cho nested record không cần thiết;
- Giữ calculation gần công thức cần đọc.

Đổi lại, **record pattern** có thể rất rõ khi các component cần thiết đều được dùng:

```java
// Nhãn case minh họa, cần đặt trong switch nhận Shape.
case Triangle(Point(var ax, var ay),
              Point(var bx, var by),
              Point(var cx, var cy)) ->
    Math.abs((bx - ax) * (cy - ay)
           - (by - ay) * (cx - ax)) / 2.0;
```

Ở đây các biến coordinate là dữ liệu của công thức shoelace/determinant cho tam giác. Với công thức đơn giản, người đọc thấy trực tiếp nguồn và phép tính. Nhưng khi cần xử lý tolerance, overflow hoặc thuật toán ổn định hơn, nên gọi helper `triangleArea` có tên rõ.

**Tránh quy tắc “luôn deconstruct sâu nhất”**: một pattern không phải mục đích tự thân. Chỉ lấy những thành phần thực sự liên quan tới nhánh.

### Exhaustiveness và sự phát triển của model

Với `sealed interface Shape permits Circle, Rectangle, Triangle`, ba case `Circle`, `Rectangle` và `Triangle` là exhaustive cho mọi Shape non-null thuộc hệ. Có thể không cần `default`:

```java
return switch (shape) {
    case Circle c -> circleArea(c.radius());
    case Rectangle r -> r.width() * r.height();
    case Triangle t -> triangleArea(t.a(), t.b(), t.c());
};
```

Khi bổ sung subtype permitted như `Polygon` và không có case bao phủ, compiler sẽ nhắc cập nhật `switch expression`. Đó là **đánh đổi quan trọng**:
- Tốt khi **tập biến thể tương đối ổn định** và dự kiến thường thêm thuật toán mới;
- Tốn công hơn khi **thường xuyên thêm subtype Shape mới**, vì nhiều calculator/switch phải cập nhật.

Nếu hệ thống là plugin cho phép loại Shape được thêm từ module bên ngoài, một sealed hierarchy đóng có thể không phù hợp. Lúc đó xem xét polymorphism, visitor, registry theo class hoặc một abstraction hỗ trợ extensibility, thay vì cố ép mọi yêu cầu vào switch.

### Null là một hợp đồng API riêng

Trong ví dụ calculator, `Objects.requireNonNull(shape, "shape")` từ chối selector null bằng NPE có message cụ thể **trước `switch`**. Đây là lựa chọn hợp lệ khi input không được phép null.

Nếu ứng dụng muốn trả giá trị mặc định hoặc `Result` lỗi, có thể dùng `case null` trong `switch` thay vì ném exception; nhưng **đừng mặc định `default` sẽ nhận null** trong enhanced switch. Phải nhất quán với contract của phương thức.

## 6. Case study tam giác: đặt công thức ở đâu cho rõ?

Tam giác được xác định bởi ba đỉnh trên mặt phẳng:

```java
record Triangle(Point a, Point b, Point c) implements Shape {}
```

Diện tích có thể tính bằng định thức (tích có hướng 2D):

\[
A = \frac{1}{2}\left| (x_b-x_a)(y_c-y_a) - (y_b-y_a)(x_c-x_a) \right|
\]

Chu vi:

\[
P = d(a,b) + d(b,c) + d(c,a),
\quad d(u,v)=\sqrt{(u_x-v_x)^2+(u_y-v_y)^2}
\]

Trong Java:

```java
static double triangleArea(Point a, Point b, Point c) {
    double dx1 = b.x() - a.x();
    double dy1 = b.y() - a.y();
    double dx2 = c.x() - a.x();
    double dy2 = c.y() - a.y();
    return Math.abs(dx1 * dy2 - dy1 * dx2) / 2.0;
}

static double distance(Point a, Point b) {
    return Math.hypot(b.x() - a.x(), b.y() - a.y());
}
```

**`Math.hypot`** thường đáng dùng hơn tự viết `Math.sqrt(dx * dx + dy * dy)` vì nó được thiết kế để giảm nguy cơ overflow/underflow trung gian trong một số miền giá trị. Tuy nhiên, nếu hiệu tọa độ đã overflow hoặc đầu vào quá cực đoan, phép tính hình học vẫn có thể tạo giá trị không hữu hạn. Không nên khẳng định `Math.hypot` giải quyết mọi vấn đề số học.

### Tam giác suy biến là quyết định domain

Ba điểm thẳng hàng cho diện tích bằng 0. Một ứng dụng vẽ hình có thể cho phép “tam giác suy biến” như trạng thái thao tác tạm thời; một ứng dụng tính khối lượng vật liệu có thể **cấm** nó.

Hai hợp đồng khác nhau:

- **Model cho phép ba đỉnh bất kỳ** (non-null, finite): calculator có thể trả diện tích 0.
- **Model bắt buộc tam giác có diện tích dương**: constructor hoặc factory cần từ chối ba điểm trùng/thẳng hàng theo tiêu chí số học được xác định.

Một phép kiểm tra “ba đỉnh không thẳng hàng” đòi tính toán hình học, nhưng vì đó là **invariant của model**, việc gọi một helper kiểm tra ở constructor/factory vẫn hợp lý. “Tách calculation” không có nghĩa cấm model kiểm tra invariant.

### Tolerance không chỉ là một số EPS cố định

Với double, kiểm tra `cross == 0` có thể nhạy với sai số, nhưng thay bằng `Math.abs(cross) < 1e-9` cũng không luôn đúng trên mọi tỉ lệ kích thước. Một độ sai số tuyệt đối có ý nghĩa khác nhau giữa tọa độ centimet và toạ độ hàng triệu mét.

Nếu ứng dụng cần xử lý geometry robust:
- Định nghĩa hệ tọa độ, đơn vị và miền tọa độ.
- Chọn tolerance có thể phụ thuộc scale hoặc thuật toán chính xác hơn.
- Kiểm tra overflow/underflow và sự triệt tiêu số học.
- Tách precision policy khỏi type `Point`/`Triangle` khi có nhiều bối cảnh.
- Đặt test cho các điểm gần thẳng hàng, kích thước cực lớn/rất nhỏ, và đảo thứ tự đỉnh.

Bài minh họa dùng công thức cơ bản với tọa độ nhỏ để đầu ra có thể xác định và tự kiểm tra.

## 7. Diện tích và chu vi: trách nhiệm chung nhưng phép tính khác nhau

Cả diện tích và chu vi dùng cùng tập shape, nhưng là **hai thao tác khác nhau**. Có thể đặt hai phương thức trong `PlanarCalculator`:

```java
double area(Shape shape) { /* switch theo loại hình */ }

double perimeter(Shape shape) { /* switch theo loại hình */ }
```

Nếu model chứa cả hai phép tính:

```java
record Rectangle(Point origin, double width, double height)
        implements Shape {
    double area() { return width * height; }
    double perimeter() { return 2.0 * (width + height); }
}
```

điều đó vẫn ổn khi mô hình nhỏ và mỗi loại hình chỉ có vài công thức. Nhưng khi app cần thêm **bounding box**, **point containment**, **intersection**, **distance to edge**, **transform**, **rasterize**, **serialize to SVG**..., không nhất thiết phải sửa tất cả record mỗi lần thêm chức năng.

**Thiết kế theo chiều biến thiên:**
- **Thêm nhiều phép toán, ít thêm Shape subtype:** sealed hierarchy + calculator + switch thường là lựa chọn rõ.
- **Thêm nhiều Shape subtype, ít phép toán:** polymorphism với `Shape.area()`/`Shape.perimeter()` có thể đơn giản hơn, vì subtype mới tự triển khai.
- **Cả hai chiều thay đổi nhiều:** cân nhắc visitor, double dispatch, strategy hoặc registry; đánh giá độ phức tạp thay vì tự động chọn một kỹ thuật.

Pattern matching làm calculator điều phối theo kiểu ngắn gọn, nhưng không loại bỏ đánh đổi này.

## 8. Chương trình Java 21 đầy đủ: model thuần và calculation service

Đây là một chương trình **tự chứa, không cần thư viện ngoài**, biểu diễn ba loại hình bằng record và sealed interface. Các record có constructor bảo vệ trạng thái cơ bản. Một `PlanarCalculator` đảm nhiệm diện tích/chu vi; ứng dụng dùng nó để tạo báo cáo.

Tệp: **`GeometryCalculationSeparationDemo.java`**

```java
import java.util.Locale;
import java.util.Objects;

public class GeometryCalculationSeparationDemo {

    sealed interface Shape permits Circle, Rectangle, Triangle {}

    record Point(double x, double y) {
        Point {
            if (!Double.isFinite(x) || !Double.isFinite(y)) {
                throw new IllegalArgumentException(
                    "Coordinates must be finite");
            }
        }
    }

    record Circle(Point center, double radius) implements Shape {
        Circle {
            Objects.requireNonNull(center, "center");
            if (!Double.isFinite(radius) || radius <= 0) {
                throw new IllegalArgumentException(
                    "Radius must be positive and finite");
            }
        }
    }

    record Rectangle(Point origin, double width, double height)
            implements Shape {
        Rectangle {
            Objects.requireNonNull(origin, "origin");
            if (!Double.isFinite(width) || width <= 0
                    || !Double.isFinite(height) || height <= 0) {
                throw new IllegalArgumentException(
                    "Width and height must be positive and finite");
            }
        }
    }

    // Contract: ba điểm không-null, hữu hạn.
    // Cho phép ba điểm thẳng hàng để phục vụ công cụ chỉnh sửa.
    record Triangle(Point a, Point b, Point c) implements Shape {
        Triangle {
            Objects.requireNonNull(a, "a");
            Objects.requireNonNull(b, "b");
            Objects.requireNonNull(c, "c");
        }
    }

    // Calculation tách khỏi các record lưu trạng thái.
    static final class PlanarCalculator {

        double area(Shape shape) {
            Objects.requireNonNull(shape, "shape");
            return switch (shape) {
                case Circle circle ->
                    Math.PI * circle.radius() * circle.radius();

                case Rectangle rectangle ->
                    rectangle.width() * rectangle.height();

                case Triangle triangle ->
                    triangleArea(
                        triangle.a(), triangle.b(), triangle.c());
            };
        }

        double perimeter(Shape shape) {
            Objects.requireNonNull(shape, "shape");
            return switch (shape) {
                case Circle circle ->
                    2.0 * Math.PI * circle.radius();

                case Rectangle rectangle ->
                    2.0 * (rectangle.width() + rectangle.height());

                case Triangle triangle ->
                    distance(triangle.a(), triangle.b())
                    + distance(triangle.b(), triangle.c())
                    + distance(triangle.c(), triangle.a());
            };
        }

        private double triangleArea(Point a, Point b, Point c) {
            double dx1 = b.x() - a.x();
            double dy1 = b.y() - a.y();
            double dx2 = c.x() - a.x();
            double dy2 = c.y() - a.y();

            return Math.abs(dx1 * dy2 - dy1 * dx2) / 2.0;
        }

        private double distance(Point a, Point b) {
            return Math.hypot(
                b.x() - a.x(),
                b.y() - a.y());
        }
    }

    // Record pattern chỉ dùng khi cần đọc cấu trúc.
    static String describe(Shape shape) {
        Objects.requireNonNull(shape, "shape");
        return switch (shape) {
            case Circle(Point(var x, var y), var radius) ->
                String.format(
                    Locale.ROOT,
                    "Circle center=(%.0f,%.0f) radius=%.0f",
                    x, y, radius);

            case Rectangle rectangle ->
                "Rectangle has width and height";

            case Triangle triangle ->
                "Triangle has three vertices";
        };
    }

    static void show(String label, Shape shape,
                     PlanarCalculator calculator) {
        System.out.printf(
            Locale.ROOT,
            "%s: area=%.2f, perimeter=%.2f%n",
            label,
            calculator.area(shape),
            calculator.perimeter(shape));
    }

    public static void main(String[] args) {
        PlanarCalculator calculator = new PlanarCalculator();

        Shape circle = new Circle(new Point(0, 0), 2);
        Shape rectangle = new Rectangle(new Point(1, 1), 3, 4);
        Shape triangle = new Triangle(
            new Point(0, 0),
            new Point(3, 0),
            new Point(0, 4));
        Shape degenerate = new Triangle(
            new Point(0, 0),
            new Point(1, 1),
            new Point(2, 2));

        show("Circle", circle, calculator);
        show("Rectangle", rectangle, calculator);
        show("Triangle", triangle, calculator);
        show("Degenerate", degenerate, calculator);

        System.out.println(describe(circle));
        System.out.println(describe(triangle));

        System.out.println("Equivalent value: "
            + circle.equals(new Circle(new Point(0, 0), 2)));

        try {
            new Circle(new Point(0, 0), -1);
        } catch (IllegalArgumentException ex) {
            System.out.println("Invalid radius rejected");
        }

        try {
            calculator.area(null);
        } catch (NullPointerException ex) {
            System.out.println("Null shape rejected");
        }
    }
}
```

Biên dịch và chạy với JDK 21 trở lên:

```bash
javac --release 21 -encoding UTF-8 GeometryCalculationSeparationDemo.java
java GeometryCalculationSeparationDemo
```

**Kết quả dự kiến:**

```text
Circle: area=12.57, perimeter=12.57
Rectangle: area=12.00, perimeter=14.00
Triangle: area=6.00, perimeter=12.00
Degenerate: area=0.00, perimeter=5.66
Circle center=(0,0) radius=2
Triangle has three vertices
Equivalent value: true
Invalid radius rejected
Null shape rejected
```

### Vì sao kết quả đúng?

**Circle:** bán kính 2, nên diện tích là `π × 2² = 4π ≈ 12.5664`; chu vi là `2π × 2 = 4π ≈ 12.5664`. `printf(Locale.ROOT, "%.2f")` đưa cả hai thành `12.57`, dấu thập phân là dấu chấm, không phụ thuộc locale mặc định của máy.

**Rectangle:** width 3, height 4; diện tích `3×4=12`, chu vi `2×(3+4)=14`. Component `origin` mô tả vị trí hình, nhưng không tham gia công thức diện tích/chu vi cho rectangle song song trục như mô hình này.

**Triangle:** ba đỉnh (0,0), (3,0), (0,4) tạo tam giác vuông. Diện tích `3×4/2=6`, cạnh lần lượt 3, 5, 4 nên chu vi 12.

**Degenerate:** ba điểm (0,0), (1,1), (2,2) thẳng hàng; định thức bằng 0 và diện tích bằng 0. Chu vi theo cách **cộng ba đoạn nối đỉnh** vẫn là `√2 + √2 + 2√2 = 4√2 ≈ 5.65685`, format thành `5.66`. Một domain khác có thể từ chối tam giác suy biến; chương trình này cố ý cho phép để minh họa chính sách.

**describe(circle):** nested record pattern deconstruct tâm `Point` vì phần mô tả cần tọa độ, không phải vì mọi công thức cần mở mọi component. Với Rectangle/Triangle, dùng type pattern đơn giản. Đây là ví dụ **chọn mức deconstruction theo mục tiêu**.

**Equivalent value:** hai record `Circle` chứa `Point(0,0)` và radius 2 như nhau, nên `equals` của record so sánh component đúng ý nghĩa trong trường hợp này. Với `double`, cần lưu ý các trường hợp đặc biệt như `-0.0` và NaN; ở đây model kiểm tra finite input và dữ liệu demo nhỏ.

**Invalid radius / Null shape:** record từ chối bán kính âm khi tạo; calculator từ chối `Shape` null trước khi tính. Đây là hai lớp hợp đồng khác nhau.

**Đây là ví dụ toán học phẳng đơn giản**, chưa xử lý giao đa giác, phép quay, hệ tọa độ địa lý, phép chiếu, đơn vị kích thước, lỗi làm tròn nghiêm ngặt hoặc phép tính robust trong miền cực đoan.

## 9. Khi nào kết quả tính toán nên có type riêng?

`double` tiện cho demo nhưng nhiều hệ thống cần contract rõ hơn:

```java
record Area(double squareMeters) {
    Area {
        if (!Double.isFinite(squareMeters)
                || squareMeters < 0) {
            throw new IllegalArgumentException(
                "Area must be finite and non-negative");
        }
    }
}

record Length(double meters) {
    Length {
        if (!Double.isFinite(meters) || meters < 0) {
            throw new IllegalArgumentException(
                "Length must be finite and non-negative");
        }
    }
}
```

Các record này giúp tránh nhầm **mét** và **mét vuông**, đồng thời từ chối những kết quả không hữu hạn. Đây là **mẫu khai báo minh họa**, không phải phần của chương trình chính.

Một calculator nghiêm ngặt có thể trả `Area`/`Length` thay `double`, nhưng phải tính đến phép toán có thể overflow trước khi tạo object. Ví dụ:

```java
double computed = /* công thức diện tích */;
if (!Double.isFinite(computed)) {
    throw new ArithmeticException("Non-finite geometry result");
}
Area area = new Area(computed);
```

Đoạn trên là mẫu cấu trúc trong phương thức có biến và công thức phù hợp. Việc ném exception hay trả typed error tùy nghiệp vụ.

**Không trộn đơn vị:** Một `Point` có tọa độ pixel thì độ dài tính ra là pixel, diện tích là pixel². Nếu tọa độ là kinh/vĩ độ, công thức Euclid trực tiếp trên độ thường **không** cho diện tích/chu vi thực theo mét. Trong hệ GIS phải có hệ quy chiếu/phép chiếu phù hợp hoặc thuật toán địa lý riêng.

Khi chính sách đơn vị/precision thay đổi theo context, đó là một lý do mạnh để tách calculation khỏi record thuần.

## 10. Các chính sách tính khác nhau: strategy thay vì nhét vào model

Giả sử ứng dụng có hai chính sách:
- **Planar geometry:** tính diện tích/chu vi trên mặt phẳng.
- **GIS/geodesic geometry:** tính trên mặt cong với hệ quy chiếu cụ thể.

Không nên mặc định cho `Circle.area()` phải tự biết đang nằm trên hệ nào nếu model chỉ chứa tọa độ `x,y` không có semantics địa lý. Một abstraction có thể là:

```java
interface GeometryCalculator {
    double area(Shape shape);
    double perimeter(Shape shape);
}
```

Với hệ thống thật, triển khai `PlanarCalculator` và `GeodesicCalculator` cần **hợp đồng dữ liệu phù hợp**: không được tự coi Point trên tọa độ phẳng là kinh/vĩ độ hoặc thêm geodesic formula mà thiếu datum/projection. Có thể dùng model khác `GeoPoint` và một service có rõ chính sách hệ quy chiếu.

Ví dụ inject calculator vào use case:

```java
// Mẫu trong ứng dụng, không phải chương trình độc lập.
double calculateArea(Shape shape, GeometryCalculator calculator) {
    return calculator.area(shape);
}
```

**Lợi ích:** cùng một model value có thể được tính theo các chính sách khác nhau, và các service được test độc lập. **Giới hạn:** abstraction này sẽ làm app phức tạp nếu thực tế chỉ có một công thức ổn định; không cần tạo strategy interface trước khi xuất hiện nhu cầu biến thiên.

### Lưu ý về tích hợp

Một calculator thuần có thể trả kết quả mà không:
- Ghi database;
- Gọi HTTP;
- Tạo log nhạy cảm;
- Đổi tọa độ của shape;
- Thay đổi static state.

Điều này giúp unit test xác định và dễ parallelize. Nếu cần caching cho tính toán đắt, cache nên có owner, key và chính sách invalidation rõ. Record immutable có thể dùng làm key tốt nếu toàn bộ component có equality/hash ổn định; nếu component là array hoặc collection mutable thì phải thận trọng.

## 11. Precision, NaN, Infinity và overflow

Các giá trị `double` không làm hình học tự động chính xác trong mọi miền.

### 11.1. Input finite nhưng output có thể overflow

`radius = 1e308` là giá trị `double` hữu hạn và dương; tuy nhiên `Math.PI * radius * radius` có thể thành `Infinity`. Nếu domain cấm kết quả không hữu hạn, calculator phải kiểm tra output hoặc áp dụng công thức, biểu diễn và miền input phù hợp.

### 11.2. Sai số do phép trừ gần nhau

Định thức cho ba điểm gần thẳng hàng có thể chịu **cancellation**, nhất là khi tọa độ lớn và khác biệt nhỏ. Một cách làm tròn đầu ra chỉ che phần hiển thị, không chữa sai số của phép tính.

### 11.3. Tolerance phải có ngữ cảnh

Một epsilon cố định như `1e-9` không phải “chuẩn đúng” cho mọi hệ đo. Nếu tọa độ ở mét với giá trị lớn, chuẩn tương đối, tolerance theo scale hoặc thuật toán robust predicates có thể thích hợp hơn. Chính sách này nên được kiểm thử độc lập, một động cơ rõ ràng để tách calculation khỏi model.

### 11.4. Số học double không phải BigDecimal cho mọi tình huống

`BigDecimal` hữu ích cho một số bài toán số thập phân cần kiểm soát độ chính xác, nhưng các phép toán hình học (căn bậc hai, π, lượng giác) cần chính sách numeric rõ; chuyển mọi `double` thành BigDecimal không tự động tạo nghiệm đúng tuyệt đối. Chọn thư viện/thuật toán theo yêu cầu, không áp dụng một kiểu số bất kể bài toán.

### 11.5. Làm tròn là quyết định presentation hoặc reporting

Trong chương trình chính, `PlanarCalculator` trả số `double` chưa được làm tròn. `show` mới format `%.2f`. Nếu làm tròn ngay trong calculator rồi tiếp tục dùng giá trị đó cho phép tính khác, sai số tích lũy có thể lớn hơn. Một chính sách reporting nghiệp vụ đôi khi yêu cầu làm tròn tại bước khác; cần ghi rõ contract.

## 12. Tối ưu hiệu năng: tính khi cần và đo trước khi cache

Tách calculation có thể giúp xác định **chỗ tốn tài nguyên**:

- Diện tích hình tròn/hình chữ nhật là phép toán nhỏ; không cần cache mù.
- Tam giác với vài phép tính là tương đối rẻ; tính lại có thể đơn giản hơn duy trì cache.
- Giao cắt giữa hai đa giác lớn, clipping hay spatial index có thể đắt; lúc ấy cần profiler và dữ liệu thực tế.
- Với hàng nghìn hình, tạo intermediate objects hoặc truy cập hệ thống ngoài trong mỗi branch có thể gây chi phí.
- Cache theo input cần tính tới equality/hash và vòng đời shape. Shape có mutable component sẽ là key nguy hiểm nếu nội dung thay đổi.

**Không dùng số dòng source code làm benchmark.** `switch` ngắn hơn `if` không chứng minh nhanh hơn. Với Java, benchmark nên xét warmup/JIT/GC, dữ liệu nhiều loại shape và đầu ra có sử dụng thật. Có thể dùng JMH hoặc profiler phù hợp, tránh đo thời gian `println`.

### Accessor và record pattern cũng có chi phí

Record pattern lấy component qua accessor. Với accessor mặc định thường là thao tác rất nhỏ, nhưng một record có custom accessor làm tính toán/I/O nặng thì deconstruction không còn “miễn phí”. Hãy giữ accessor của value record ổn định, ít side effect, và chỉ deconstruct component thực sự cần. Nếu helper lấy lại các component lặp, cân nhắc đọc vào local hoặc snapshot theo yêu cầu consistency.

Tối ưu phải bảo toàn hành vi với input bình thường, null, shape suy biến và các biến thể tương lai.

## 13. Kiểm thử model và calculator riêng biệt

Một ưu điểm lớn của việc tách là mỗi loại test trả lời một nhóm câu hỏi.

### 13.1. Test model invariant

- `new Point(Double.NaN, 0)` bị từ chối theo contract finite.
- `new Circle(new Point(0,0), 0)` bị từ chối vì radius phải dương.
- `new Rectangle(new Point(0,0), -1, 2)` bị từ chối.
- `new Triangle(null, b, c)` bị từ chối.
- Ba điểm thẳng hàng **được cho phép trong model demo** và area service trả 0.

Những test này không cần gọi calculator để biết constructor có bảo vệ state không.

### 13.2. Test công thức

| Hình và tham số | Diện tích kỳ vọng | Chu vi kỳ vọng |
| --- | ---: | ---: |
| Circle radius 2 | `4π` | `4π` |
| Rectangle width 3, height 4 | 12 | 14 |
| Triangle (0,0),(3,0),(0,4) | 6 | 12 |
| Triangle thẳng hàng (0,0),(1,1),(2,2) | 0 | `4√2` |

Với floating-point, so sánh tolerance có lý do thay vì chỉ `expected == actual` cho công thức có π/căn bậc hai. Trong ví dụ output có format 2 chữ số để dễ đọc, nhưng **test thuật toán** nên so giá trị double trước khi format.

### 13.3. Test tính chất (property-based hoặc kiểm thử ví dụ có hệ thống)

- Dịch chuyển mọi đỉnh cùng một vector không đổi diện tích/chu vi.
- Đổi thứ tự hai đỉnh tam giác không làm diện tích tuyệt đối đổi.
- Với scale dương `k`, độ dài nhân `k`, diện tích nhân `k²` khi không overflow và hình học vẫn nằm trong miền số.
- Hình chữ nhật có width/height hoán đổi vẫn giữ diện tích/chu vi.
- Các hình hợp lệ có diện tích và chu vi không âm trong miền số mà thuật toán hỗ trợ.

Đây là các **tính chất toán học**, không tự thành luật tuyệt đối với mọi `double` cực đoan; phải đặt tolerance và kiểm tra input hợp lệ.

### 13.4. Test exhaustiveness khi model phát triển

Nếu thêm `Polygon implements Shape` vào danh sách permitted của sealed interface, các `switch expression` area/perimeter/describe có thể không còn exhaustive. Compiler buộc cập nhật nếu không có case bao trùm. Đó là lợi thế để chắc rằng shape mới không âm thầm được đưa vào hệ mà không có công thức.

Trường hợp dùng `default -> 0` làm fallback có thể che một shape chưa có công thức: app vẫn chạy nhưng trả diện tích sai. Với sealed hierarchy có tập subtype rõ, **tránh `default` tùy tiện** là một lựa chọn đáng cân nhắc.

## 14. Refactor từ model có nhiều phép tính sang calculator

Giả sử hiện tại mỗi model có `area()` và `perimeter()`, nhưng team muốn tách vì nhiều thuật toán mới.

Một quy trình bảo toàn hành vi:

**Bước 1. Liệt kê các công thức và chính sách đang dùng.** Ghi chú đơn vị, precision, làm tròn, điều kiện shape suy biến, ngoại lệ, và có side effect hay không.

**Bước 2. Chốt contract model.** Constructor nên bảo vệ dữ liệu tạo hình hợp lệ; không thay validation vì chỉ muốn di chuyển phương thức.

**Bước 3. Tạo calculator riêng với API rõ.** Thí dụ `double area(Shape)`/`double perimeter(Shape)`. Nếu cần policies, quyết định abstraction ở đây; chưa cần strategy interface nếu chỉ một chính sách.

**Bước 4. Chuyển công thức giữ nguyên semantics.** Dùng `switch` theo subtype, trích helper cho triangle hoặc công thức dài. Không đổi công thức và quy tắc rounding cùng lúc trừ khi có yêu cầu nghiệp vụ riêng.

**Bước 5. Giữ tầng hiển thị ra khỏi calculator.** Di chuyển `printf/String.format` tới reporter/adaptor, để test giá trị số trước formatting.

**Bước 6. Viết regression tests.** So sánh trước/sau trên hình thông thường, biên, null, suy biến, khác đơn vị; bao gồm exception khi input không hợp lệ.

**Bước 7. Cập nhật call sites và public API có kế hoạch.** Xóa `shape.area()` khỏi interface công khai có thể là breaking change; cân nhắc deprecate/adapter trong một giai đoạn nếu API có người dùng bên ngoài.

**Bước 8. Đo khi có mục tiêu hiệu năng cụ thể.** Tránh gộp refactor sạch code với tối ưu số học phức tạp trong cùng thay đổi.

Đừng coi refactor thành công chỉ vì `Circle` còn ba dòng. Thành công là **logic ở đúng nơi, hành vi rõ ràng và test độc lập dễ hơn**.

## 15. Các lỗi phổ biến

| Lỗi | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| “Tách mọi phép tính khỏi model” | Method thuần, đơn giản bị đẩy qua lớp trung gian vô nghĩa | Chỉ tách khi có sự biến thiên/độ phức tạp rõ |
| Cho model chỉ là bag of fields không invariant | Tạo `Circle(-1)`, `Rectangle(NaN)` | Validate trong canonical constructor/factory |
| Calculator vừa tính diện tích vừa ghi database | Trộn numeric logic và side effect | Tách application boundary, giữ calculation thuần |
| Dùng công thức Euclid trên kinh/vĩ độ và gọi kết quả mét² | Sai hệ đơn vị/hệ tọa độ | Xác định projection/geodesic policy |
| Dùng `default -> 0` cho mọi Shape chưa biết | Che việc thiếu thuật toán khi thêm subtype | Dùng sealed/exhaustive switch hoặc lỗi tường minh |
| Lồng record pattern sâu dù chỉ cần radius | Coupling và null constraints thừa | Dùng type pattern và accessor cần thiết |
| Guard có side effect hoặc gọi I/O | Phân loại có thể thay đổi state/timeout | Precompute ở service, dùng guard thuần |
| Tưởng constructor finite bảo đảm kết quả finite | Phép nhân vẫn có thể overflow | Kiểm tra output hoặc miền số/algorithm |
| Dùng epsilon cố định cho mọi kích thước | Sai với scale khác nhau | Chính sách tolerance có ngữ cảnh |
| Làm tròn area trong calculator rồi tiếp tục tính | Mất độ chính xác không cần thiết | Chỉ format ở boundary khi phù hợp |
| Không xác định tam giác suy biến hợp lệ hay không | Code và test có kỳ vọng khác nhau | Ghi rõ contract; validate nếu domain cấm |
| Cache theo shape có mutable component | Key/hash có thể đổi, cache sai | Immutable snapshot, ownership, invalidation |
| Tách nhưng không test khi thay công thức | Refactor làm thay đổi kết quả/exception | Regression + property tests |
| Thêm Shape mới nhưng bỏ qua các algorithm | Một phép tính bị thiếu | Exhaustive switch không default tùy tiện |
| Benchmark bằng `println` hoặc một input | Kết luận hiệu năng sai | JMH/profiler và nhiều kích thước input |

## 16. Bài tập thực hành

**Bài 1 — Phân loại trách nhiệm.** Với `Circle(center, radius)`, xác định trách nhiệm của constructor, `PlanarCalculator.area`, `show` và lớp lưu database. Vì sao validation radius vẫn thuộc model dù có phép so sánh số học?

**Bài 2 — Thêm Square.** Thêm `record Square(Point origin, double side) implements Shape` với invariant side dương và hữu hạn. Cập nhật `permits`, diện tích và chu vi. Quan sát compiler yêu cầu cập nhật những `switch expression` nào khi chưa thêm case.

**Bài 3 — So sánh thiết kế.** Trong một app chỉ có Circle và một công thức area đơn giản, giải thích lợi/hại của `circle.area()` so với `calculator.area(circle)`. Không dùng lý do “clean architecture luôn cấm domain method”.

**Bài 4 — Tam giác suy biến.** Chạy `GeometryCalculationSeparationDemo.java`. Thay đỉnh (2,2) bằng (2,3) để tam giác không còn thẳng hàng; tính diện tích và chu vi mới. Nếu cần cấm suy biến, bạn sẽ thực hiện kiểm tra ở constructor, factory hay service nào? Nêu contract.

**Bài 5 — Đơn vị.** `Point` hiện là tọa độ pixel. Nếu hệ thống mới báo cáo khoảng cách theo mét, những thông tin và bước chuyển đổi nào cần có? Vì sao không thể chỉ đổi tên method `perimeter()` thành `perimeterMeters()`?

**Bài 6 — Precision.** Thử Circle với radius lớn gần `Double.MAX_VALUE`. Kiểm tra `Double.isFinite(calculator.area(circle))`. Đề xuất chính sách lỗi hoặc miền input cho một API không cho phép area vô hạn.

**Bài 7 — Record patterns.** Viết một case cho `Triangle(Point(var ax,var ay),Point(var bx,var by),Point(var cx,var cy))` để trích tọa độ rồi tính area. So sánh với `case Triangle t -> triangleArea(t.a(),t.b(),t.c())` khi công thức trở nên phức tạp.

**Bài 8 — Property test.** Tạo tam giác mới bằng cách cộng `(+100, -50)` cho cả ba đỉnh. Diện tích/chu vi có thay đổi không? Dùng tolerance hợp lý để so giá trị `double`.

**Bài 9 — Thêm phép tính mới.** Tạo `boundingBox(Shape)` trong một calculator riêng hoặc cùng service, không sửa record nếu không cần. Đưa ra input và output mong muốn cho ba loại hình, đặc biệt xác định hình chữ nhật có được xoay hay luôn song song trục.

**Bài 10 — Thiết kế nhiều chính sách.** App bản đồ dùng cả điểm trên mặt phẳng và điểm địa lý. Đề xuất cách phân biệt model hoặc calculator để tránh nhầm đơn vị; giải thích khi nào strategy interface có giá trị thực.

## 17. Tổng kết

**Tách calculation khỏi model khi cần** là lựa chọn dựa trên trách nhiệm, mức độ thay đổi và khả năng kiểm thử — không phải quy tắc ép mọi record chỉ chứa field.

Trong case study hình học Java 21:

- **Record model** lưu dữ liệu và bảo vệ invariant (`Point` hữu hạn, `Circle` radius dương, `Rectangle` width/height dương).
- **Calculator thuần** triển khai công thức diện tích/chu vi, có thể mở rộng theo policy và được test riêng.
- **`switch` pattern matching** trên sealed `Shape` giúp chọn đúng thuật toán, tránh cast, cho exhaustiveness khi tập hình đóng.
- **Record pattern** dùng khi cần thật sự deconstruct component; không nên mở các tầng không liên quan.
- **Null, tam giác suy biến, đơn vị, tolerance, overflow và formatting** phải có contract rõ; không được để mặc định mơ hồ.
- **Không tách quá mức:** một method đơn giản và ổn định nằm trong model đôi khi vẫn là lựa chọn tốt nhất.

### Tài liệu tham khảo

- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html).
- [Oracle Java 21 — Record Classes](https://docs.oracle.com/en/java/javase/21/language/records.html).
- [JEP 395 — Records](https://openjdk.org/jeps/395).
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440).
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
- [Java SE 21 — `Math.hypot`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html#hypot(double,double)).
