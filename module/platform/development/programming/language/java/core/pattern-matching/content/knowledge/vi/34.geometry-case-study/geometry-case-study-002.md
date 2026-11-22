# Biểu diễn Rectangle và Circle bằng record trong Java 21

## 1. Bài toán: mô hình hình học gọn, rõ và bảo vệ bất biến

Giả sử ta xây dựng một module hình học 2D, cần biểu diễn **hình tròn (Circle)** và **hình chữ nhật (Rectangle)**, tính diện tích/chu vi, kiểm tra một điểm có nằm trong hình hay không, và phân loại hình bằng Java Pattern Matching.

Ta muốn dữ liệu hình học:

- Có **tên kiểu rõ ràng**: `Circle` và `Rectangle` là các biến thể của `Shape`.
- Mang **đủ dữ liệu** để tính toán, không cần trường trạng thái tùy tiện.
- **Không bị thay đổi** sau khi khởi tạo; muốn phóng to sẽ tạo đối tượng mới.
- Có thể **kiểm tra invariant ngay khi tạo**: bán kính, chiều rộng, chiều cao phải hữu hạn và lớn hơn 0; tâm hình không được null.
- Dễ so sánh theo giá trị trong test, dễ in thông tin khi debug.
- Dùng được với `switch` type/record patterns để giải cấu trúc và xử lý hết các biến thể.

**Record** là lựa chọn phù hợp cho các **data carriers** như vậy. Java records trở thành tính năng chính thức từ **Java 16 (JEP 395)**. Khi kết hợp **record patterns (JEP 440)** và **pattern matching for switch (JEP 441)** — đều chính thức từ **Java 21** — ta có thể viết logic xử lý các hình bằng cú pháp ngắn gọn, không cần cast thủ công.

Bài học này đặt ra hợp đồng hình học cụ thể:

| Đối tượng | Trạng thái lưu trữ | Ý nghĩa |
| --- | --- | --- |
| `Point` | `x`, `y` | Tọa độ thực 2D theo hệ Descartes |
| `Circle` | `center: Point`, `radius: double` | Đường tròn và vùng đĩa tròn với tâm và bán kính |
| `Rectangle` | `center: Point`, `width: double`, `height: double` | Hình chữ nhật **các cạnh song song với trục tọa độ**, xác định bằng tâm và kích thước |
| `Shape` | Một `sealed interface` | Kiểu chung cho các hình được hỗ trợ |

**Giới hạn mô hình:** `Rectangle` ở đây **không có góc quay**; các cạnh song song trục X/Y (*axis-aligned rectangle*). “Nằm trong hình” tính cả **đường biên**. Các giá trị độ dài phải dùng cùng đơn vị, ví dụ mét hoặc pixel; không được tự trộn chúng. Để đơn giản hóa domain, hình có chiều dài bằng 0 bị xem là **không hợp lệ**. Một bài toán khác có thể chủ đích cho phép hình suy biến, nhưng khi đó phải sửa hợp đồng và test.

## 2. Từ class Java truyền thống đến record

### 2.1. Khai báo record tối thiểu

```java
record Point(double x, double y) {}
record Circle(Point center, double radius) {}
record Rectangle(Point center, double width, double height) {}
```

Mỗi record khai báo **record components** trong cặp ngoặc sau tên kiểu. Compiler tạo những thành phần chuẩn cho record, bao gồm:

- Các trường tương ứng có tính chất `private final`.
- **Canonical constructor** khớp thứ tự và kiểu của components (trừ khi tự khai báo constructor phù hợp).
- **Accessor** có cùng tên component: `point.x()`, `circle.radius()`, `rectangle.width()`. Record không tự tạo phương thức JavaBean `getWidth()`.
- Cài đặt `equals(Object)` và `hashCode()` theo các component.
- `toString()` hiển thị kiểu record cùng các giá trị component.

Ví dụ trong một phương thức:

```java
var a = new Point(1.0, 2.0);
var b = new Point(1.0, 2.0);

System.out.println(a.x());       // 1.0
System.out.println(a.equals(b));  // true
System.out.println(a);            // Point[x=1.0, y=2.0]
```

Đoạn này dùng cú pháp record đơn giản, không cần Java 21; nhưng ví dụ tổng hợp ở dưới dùng record patterns và pattern switch của Java 21.

### 2.2. Record không đồng nghĩa “mọi thứ đều bất biến sâu”

Record không cho phép gán lại trường component từ ngoài sau khi tạo:

```java
Point point = new Point(1, 2);
// point.x = 9;    // LỖI BIÊN DỊCH: x là private final.
// point.x(9);     // LỖI: không có setter x(double).
```

Tuy nhiên, đây là **shallow immutability**: record có thể giữ reference đến một đối tượng mutable. Nếu viết `record Image(byte[] pixels) {}`, một caller vẫn có thể thay đổi phần tử trong mảng, dù reference `pixels` là final. Điều này cũng có thể ảnh hưởng `equals`/`hashCode`, vì mảng được so sánh theo reference chứ không tự so phần tử.

Trong bài, `Point` chứa hai `double` bất biến; `Circle`/`Rectangle` giữ một `Point` record và các `double`. Vì vậy mô hình cụ thể này không có nội dung mutable lồng nhau. Nếu thay `Point` bằng một class mutable, phải cân nhắc **defensive copy**, immutable type hoặc ràng buộc chặt hơn.

### 2.3. Record phù hợp dữ liệu, không thay thế mọi class

Record **implicitly final**: không thể khai báo `class ColoredCircle extends Circle`. Record cũng không thể kế thừa một class ứng dụng tùy ý; record luôn kế thừa `java.lang.Record`. Nhưng record **có thể implements interface** và khai báo method, constructor, static member theo quy tắc cho phép.

Vì thế ta có thể dùng `Circle` và `Rectangle` làm biến thể của `Shape`. Nếu domain cần nhiều tầng kế thừa hành vi hoặc identity thay vì value semantics, một class bình thường có thể phù hợp hơn.

## 3. Thiết kế invariant trước khi viết tính toán

Khai báo record chưa đủ để bảo vệ hình học. Mặc định Java cho phép tạo:

```java
// Với record CHƯA có validation:
new Circle(null, -10.0);
new Rectangle(new Point(0, 0), Double.NaN, 2.0);
new Rectangle(new Point(0, 0), Double.POSITIVE_INFINITY, 1.0);
```

Các giá trị này gây khó giải thích diện tích, khoảng cách hoặc kiểm tra thuộc vùng. Ta cần một **compact canonical constructor** để chặn chúng.

### 3.1. Compact constructor cho record

```java
record Circle(Point center, double radius) {
    Circle {
        java.util.Objects.requireNonNull(center, "center");
        if (!Double.isFinite(radius) || radius <= 0.0) {
            throw new IllegalArgumentException(
                    "radius must be finite and > 0");
        }
    }
}
```

Cú pháp `Circle { ... }` là **compact constructor**, không khai báo lại danh sách tham số. Trong constructor, tên `center` và `radius` tương ứng với tham số canonical. Compiler gán các giá trị sau validation vào các trường của record.

Tương tự, `Rectangle` nên kiểm tra **cả width và height**. `Point` cần kiểm tra tọa độ hữu hạn, không phải dương (tọa độ âm là hợp lệ).

**Quy tắc đáng nhớ:**

- `Double.isFinite(x)` loại `NaN` và hai giá trị vô cực.
- `x > 0.0` yêu cầu kích thước **dương**; `0.0` và `-0.0` không hợp lệ.
- `Objects.requireNonNull(center, "center")` ném `NullPointerException` rõ nguyên nhân khi tâm null.
- Constructor của record có thể ném exception; “record” **không mặc định validate** invariant cho bạn.
- Validation ở constructor giúp mọi đối tượng hợp lệ theo kiểu này; nhưng các phép tính sau đó vẫn có thể bị **floating-point overflow** nếu kích thước cực lớn.

Không lẫn validation của hình với validation của dữ liệu ngoài: nếu cần tiếp nhận input chưa hợp lệ, parse và trả lỗi nghiệp vụ trước khi tạo record, thay vì ghi một record mang trạng thái không hợp lệ rồi sửa dần.

### 3.2. Thiết kế thông báo lỗi

Thông báo như `radius must be finite and > 0` hoặc `center` giúp developer tìm đúng field khi test/đọc log. Trong API công khai, nên đổi lỗi constructor thành response có cấu trúc ở tầng biên nếu domain yêu cầu, nhưng giữ nguyên invariant trong model để ngăn object không hợp lệ xâm nhập luồng tính toán.

## 4. Sealed Shape: mô hình hóa hai biến thể hợp lệ

Khai báo:

```java
sealed interface Shape permits Circle, Rectangle {}

record Circle(Point center, double radius) implements Shape {}
record Rectangle(Point center, double width, double height)
        implements Shape {}
```

Ở đây `Circle` và `Rectangle` là record **final**, do đó phù hợp làm các implementor của `sealed interface Shape`. `sealed` đã final từ Java 17 (JEP 409); không cần Java 21 nếu chỉ muốn khai báo hierarchy.

Điểm mạnh khi kết hợp với Java 21:

```java
// Một phần của method nhận Shape shape:
return switch (shape) {
    case Circle(var center, double radius) ->
            Math.PI * radius * radius;
    case Rectangle(var center, double width, double height) ->
            width * height;
    case null ->
            throw new IllegalArgumentException("shape required");
};
```

Đây là **switch expression dùng record patterns**. Compiler biết hai biến thể được phép của `Shape` và kiểm tra tính bao phủ (*exhaustiveness*). Không cần `default` để “bắt mọi thứ” khi tập Shape đóng đã được bao phủ.

Khi thêm một biến thể mới như `Triangle` vào `permits`, những switch chưa xử lý Triangle có thể trở thành **không exhaustive** lúc biên dịch lại; compiler sẽ yêu cầu cập nhật. Đây là ưu điểm quan trọng khi miền kiểu được sở hữu bởi cùng một module.

Nếu domain mở cho plugin tạo hình mới từ module ngoài, một `sealed interface` có thể là **hạn chế không mong muốn**. Khi đó cần cân nhắc interface mở và chiến lược dispatch khác. Chọn `sealed` vì hợp đồng domain khép kín, không chỉ vì muốn giảm số nhánh.

## 5. Chương trình Java 21 hoàn chỉnh: khai báo, tính toán và pattern matching

Chương trình sau gồm **mô hình hình học, validation, area, perimeter, contains, scale, phân loại SQUARE**, và các ca kiểm tra đầu vào sai. Chỉ dùng Java SE, **không cần dependency và không cần `--enable-preview`**.

Lưu thành **`GeometryRecordsDemo.java`**:

```java
public class GeometryRecordsDemo {
    sealed interface Shape permits Circle, Rectangle {}

    record Point(double x, double y) {
        Point {
            checkFinite(x, "x");
            checkFinite(y, "y");
        }
    }

    record Circle(Point center, double radius) implements Shape {
        Circle {
            java.util.Objects.requireNonNull(center, "center");
            checkPositiveFinite(radius, "radius");
        }
    }

    record Rectangle(Point center, double width, double height)
            implements Shape {
        Rectangle {
            java.util.Objects.requireNonNull(center, "center");
            checkPositiveFinite(width, "width");
            checkPositiveFinite(height, "height");
        }
    }

    static void checkFinite(double value, String name) {
        if (!Double.isFinite(value)) {
            throw new IllegalArgumentException(name + " must be finite");
        }
    }

    static void checkPositiveFinite(double value, String name) {
        if (!Double.isFinite(value) || value <= 0.0) {
            throw new IllegalArgumentException(
                    name + " must be finite and > 0");
        }
    }

    static double finiteMeasure(double value) {
        if (!Double.isFinite(value)) {
            throw new ArithmeticException(
                    "geometry measure overflow");
        }
        return value;
    }

    static double area(Shape shape) {
        return finiteMeasure(switch (shape) {
            case Circle(Point center, double radius) ->
                    Math.PI * radius * radius;
            case Rectangle(Point center, double width, double height) ->
                    width * height;
            case null ->
                    throw new IllegalArgumentException("shape required");
        });
    }

    static double perimeter(Shape shape) {
        return finiteMeasure(switch (shape) {
            case Circle(Point center, double radius) ->
                    2.0 * Math.PI * radius;
            case Rectangle(Point center, double width, double height) ->
                    2.0 * (width + height);
            case null ->
                    throw new IllegalArgumentException("shape required");
        });
    }

    static String kind(Shape shape) {
        return switch (shape) {
            case Circle(Point center, double radius) -> "CIRCLE";

            case Rectangle(Point center, double width, double height)
                    when width == height -> "SQUARE";

            case Rectangle(Point center, double width, double height) ->
                    "RECTANGLE";

            case null -> "MISSING";
        };
    }

    static boolean contains(Shape shape, Point point) {
        java.util.Objects.requireNonNull(point, "point");

        return switch (shape) {
            case Circle(Point(double cx, double cy), double r) ->
                    Math.hypot(point.x() - cx, point.y() - cy) <= r;

            case Rectangle(
                    Point(double cx, double cy),
                    double w, double h) ->
                    Math.abs(point.x() - cx) <= w / 2.0
                            && Math.abs(point.y() - cy) <= h / 2.0;

            case null ->
                    throw new IllegalArgumentException("shape required");
        };
    }

    static Shape scale(Shape shape, double factor) {
        checkPositiveFinite(factor, "factor");

        return switch (shape) {
            case Circle(Point center, double radius) ->
                    new Circle(center, radius * factor);

            case Rectangle(Point center, double width, double height) ->
                    new Rectangle(
                            center,
                            width * factor,
                            height * factor);

            case null ->
                    throw new IllegalArgumentException("shape required");
        };
    }

    // Chỉ dùng để minh họa tên exception trong ví dụ.
    static String outcome(Runnable operation) {
        try {
            operation.run();
            return "accepted";
        } catch (RuntimeException ex) {
            return ex.getClass().getSimpleName();
        }
    }

    public static void main(String[] args) {
        var origin = new Point(0.0, 0.0);

        Circle circle = new Circle(origin, 2.0);
        Rectangle rectangle = new Rectangle(
                new Point(1.0, 1.0), 4.0, 6.0);
        Rectangle square = new Rectangle(origin, 4.0, 4.0);

        System.out.printf(
                java.util.Locale.ROOT,
                "circle area=%.2f perimeter=%.2f%n",
                area(circle), perimeter(circle));

        System.out.printf(
                java.util.Locale.ROOT,
                "rectangle area=%.2f perimeter=%.2f%n",
                area(rectangle), perimeter(rectangle));

        System.out.println(
                "kinds=" + kind(circle) + ","
                        + kind(rectangle) + "," + kind(square));

        System.out.println(
                "circle boundary="
                        + contains(circle, new Point(2, 0))
                        + " outside="
                        + contains(circle, new Point(2.1, 0)));

        System.out.println(
                "rectangle corner="
                        + contains(rectangle, new Point(3, 4))
                        + " outside="
                        + contains(rectangle, new Point(3.01, 4)));

        Rectangle scaled = (Rectangle) scale(rectangle, 2.0);

        System.out.printf(
                java.util.Locale.ROOT,
                "scaled rectangle area=%.2f perimeter=%.2f%n",
                area(scaled), perimeter(scaled));

        System.out.println(
                "original width=" + rectangle.width()
                        + " scaled width=" + scaled.width());

        System.out.println(
                "records equal="
                        + circle.equals(
                                new Circle(new Point(0, 0), 2.0)));

        System.out.println(
                "invalid radius="
                        + outcome(() -> new Circle(origin, 0.0)));

        System.out.println(
                "invalid center="
                        + outcome(() -> new Circle(null, 2.0)));

        System.out.println(
                "invalid NaN="
                        + outcome(() ->
                                new Rectangle(origin, Double.NaN, 2.0)));

        System.out.println("null shape kind=" + kind(null));
    }
}
```

Biên dịch và chạy với **JDK 21+**:

```bash
javac --release 21 GeometryRecordsDemo.java
java GeometryRecordsDemo
```

**Stdout chính xác:**

```text
circle area=12.57 perimeter=12.57
rectangle area=24.00 perimeter=20.00
kinds=CIRCLE,RECTANGLE,SQUARE
circle boundary=true outside=false
rectangle corner=true outside=false
scaled rectangle area=96.00 perimeter=40.00
original width=4.0 scaled width=8.0
records equal=true
invalid radius=IllegalArgumentException
invalid center=NullPointerException
invalid NaN=IllegalArgumentException
null shape kind=MISSING
```

Đây là một chương trình độc lập, được kiểm tra chạy trên JDK 24 bằng cú pháp tương thích Java 21. Dùng `Locale.ROOT` trong `printf` để dấu thập phân nhất quán là dấu chấm. Chương trình chỉ in **hai chữ số thập phân**, không khẳng định giá trị `double` gốc đã được làm tròn và lưu như vậy.

**Tóm tắt điều được kiểm tra:** 2 loại Shape, nested record patterns, guard `when` nhận diện hình vuông, phép tính hình học, biên nằm trong hình, scale tạo bản sao, so sánh theo giá trị và validation cho các đối tượng không hợp lệ.

## 6. Cơ chế hình học sau các record

### 6.1. Công thức diện tích và chu vi

Với `Circle(center, radius)`:

\[
A_{\text{circle}} = \pi r^2,\qquad
P_{\text{circle}} = 2\pi r
\]

Với `Rectangle(center, width, height)`:

\[
A_{\text{rectangle}} = w h,\qquad
P_{\text{rectangle}} = 2(w+h)
\]

Tâm `center` **không tham gia** diện tích/chu vi của một hình tròn hoặc hình chữ nhật song song trục; nó chỉ quyết định vị trí. Vì vậy `area` và `perimeter` có thể deconstruct toàn bộ record nhưng không dùng biến `center`, hoặc dùng `var` để thấy rõ đây là dữ liệu không cần tính toán.

**Trường hợp kiểm thử:**

- Circle có `r=2` → diện tích `4π ≈ 12.57`, chu vi `4π ≈ 12.57`.
- Rectangle có `w=4`, `h=6` → diện tích `24`, chu vi `20`.
- Scale rectangle hệ số `2` → `w=8`, `h=12`; diện tích `96`, chu vi `40`.

### 6.2. Kiểm tra điểm thuộc Circle

Một điểm `Q(x,y)` thuộc **đĩa tròn** tâm `C(cx,cy)`, bán kính `r` nếu:

\[
\sqrt{(x-c_x)^2+(y-c_y)^2}\le r
\]

Trong Java:

```java
// Phần thân case của switch:
case Circle(Point(double cx, double cy), double r) ->
        Math.hypot(point.x() - cx, point.y() - cy) <= r;
```

`Math.hypot(a,b)` được thiết kế để tính khoảng cách dạng căn tổng bình phương với tính ổn định số tốt hơn việc viết `Math.sqrt(a*a+b*b)` trực tiếp, nhất là khi các số có độ lớn cực trị. Tuy nhiên, phép **trừ tọa độ trước khi gọi hypot** vẫn có thể overflow khi hai tọa độ hữu hạn nhưng quá xa nhau; vì thế một hệ thống đòi hỏi độ chính xác cực cao cần xem xét mô hình số và giới hạn miền tọa độ.

Trong ví dụ, `new Point(2,0)` nằm đúng biên của Circle tâm 0 bán kính 2 nên trả `true`; `new Point(2.1,0)` nằm ngoài nên trả `false`.

### 6.3. Kiểm tra điểm thuộc Rectangle song song trục

Rectangle được biểu diễn theo tâm, nên một điểm nằm trong vùng (kể cả cạnh) khi:

\[
|x-c_x|\le \frac{w}{2}
\quad\land\quad
|y-c_y|\le \frac{h}{2}
\]

Trong Java:

```java
case Rectangle(Point(double cx, double cy), double w, double h) ->
        Math.abs(point.x() - cx) <= w / 2.0
                && Math.abs(point.y() - cy) <= h / 2.0;
```

Với Rectangle tâm `(1,1)`, rộng `4`, cao `6`:

- Miền X từ `-1` đến `3`.
- Miền Y từ `-2` đến `4`.
- Điểm `(3,4)` nằm ở góc trên bên phải và **được chấp nhận** do dùng `<=`.
- Điểm `(3.01,4)` nằm ngoài ở trục X, nên bị từ chối.

Nếu domain định nghĩa rectangle bằng **góc trái trên** trong hệ tọa độ màn hình (trục Y đi xuống), công thức và tên trường cần được thiết kế lại cho khớp. Đừng dùng lẫn hai cách quy ước mà không chuyển đổi tọa độ.

### 6.4. Scale làm hình mới, không thay object hiện có

Với hệ số `k > 0`:

- Circle: `r' = k*r`.
- Rectangle: `w' = k*w`, `h' = k*h`.
- Tâm `center` được giữ nguyên trong mô hình scale này.

`scale` dùng `switch` trả về **record mới**. Không có setter để chỉnh `radius`, `width`, `height` của record cũ.

Nội dung ví dụ có dòng:

```text
original width=4.0 scaled width=8.0
```

cho thấy Rectangle gốc vẫn giữ chiều rộng `4` trong khi bản scale có chiều rộng `8`.

**Lưu ý:** nếu cần scale quanh **gốc tọa độ** thay vì quanh **tâm của chính hình**, tâm phải được scale/di chuyển theo. Hai hành vi khác nhau; tên method và hợp đồng phải nói rõ scale quanh điểm nào.

## 7. Từ record data đến record pattern Java 21

### 7.1. Type pattern chỉ lấy đối tượng

Với `switch` trên `Shape`:

```java
return switch (shape) {
    case Circle circle ->
            Math.PI * circle.radius() * circle.radius();
    case Rectangle rectangle ->
            rectangle.width() * rectangle.height();
    case null -> 0.0; // Chỉ là chính sách minh họa.
};
```

Đây là **type patterns**: `case Circle circle` chỉ binding đối tượng và dùng accessors. Đoạn này là **minh họa** trong method có biến `shape` kiểu `Shape`; giá trị `0.0` với selector null là lựa chọn giả định, **không phải** chính sách của chương trình đầy đủ ở mục 5 (chương trình đó từ chối `area(null)`).

### 7.2. Record pattern lấy trực tiếp component

```java
return switch (shape) {
    case Circle(Point center, double radius) ->
            Math.PI * radius * radius;
    case Rectangle(Point center, double width, double height) ->
            width * height;
    case null -> throw new IllegalArgumentException("missing shape");
};
```

Các component được deconstruct ngay tại nhãn `case`. Người đọc thấy rõ **hình Circle có tâm + bán kính**, **Rectangle có tâm + chiều rộng + chiều cao**. Điều này đặc biệt hữu ích trong case study có nhiều thao tác đơn giản trên cùng bộ record.

### 7.3. Nested record pattern lấy tọa độ tâm

```java
case Circle(Point(double cx, double cy), double radius) ->
        Math.hypot(point.x() - cx, point.y() - cy) <= radius;
```

Pattern `Point(double cx,double cy)` lồng bên trong `Circle(...)`, nên Java không cần gọi thủ công:

```java
Circle circle = (Circle) shape;
double cx = circle.center().x();
double cy = circle.center().y();
double radius = circle.radius();
```

Khi dùng record patterns, **thứ tự component phải đúng** với khai báo record. Nếu `Rectangle` có thứ tự `(Point center, double width, double height)`, không được tráo vị trí theo cảm giác mà không cập nhật toàn bộ pattern.

### 7.4. Null của selector và record component

**Hai trường hợp khác nhau:**

- `shape == null`: `case null` ở cấp `switch` có thể bắt selector null; nếu không có nhánh thích hợp, có thể ném `NullPointerException`.
- `new Circle(null, 2)`: trong bài **không thể tạo thành công** do constructor `requireNonNull`. Vì vậy các nested record patterns được phép giả định `center` khác null đối với object Circle hợp lệ.

Nếu **bỏ validation** và tạo được một `Circle` có center null, nested record pattern `Circle(Point(...),r)` không khớp phần `Point(...)`. Một switch được compiler coi exhaustive trong một số tình huống nested pattern nhưng không tìm được nhánh runtime có thể ném `MatchException`. Vì vậy **bất biến của record và chiến lược case fallback phải được thiết kế cùng nhau**.

## 8. Guard when: nhận diện Square từ Rectangle

Trong mô hình này, **hình vuông** là một Rectangle có `width == height`. Không cần bắt buộc tạo một record `Square` riêng nếu Square không có hành vi/validation độc lập.

```java
static String kind(Shape shape) {
    return switch (shape) {
        case Circle(Point center, double radius) -> "CIRCLE";

        case Rectangle(Point center, double width, double height)
                when width == height -> "SQUARE";

        case Rectangle(Point center, double width, double height) ->
                "RECTANGLE";

        case null -> "MISSING";
    };
}
```

**Điểm quan trọng khi review:**

1. Nhánh `Rectangle ... when width == height` đứng **trước** nhánh Rectangle không guard, vì nhánh không guard bao phủ mọi Rectangle hợp lệ.
2. Guard `when` chỉ chạy sau khi pattern Rectangle khớp, biến `width`/`height` đã được binding.
3. Nếu hai kích thước được nhập trực tiếp và hợp đồng định nghĩa “bằng nhau chính xác”, `==` là một lựa chọn có chủ đích.
4. Nếu width/height được tính từ những phép toán floating-point trước đó, các giá trị về toán học “bằng nhau” có thể khác bit do rounding. Khi đó phải định nghĩa **độ dung sai** hoặc chuyển sang kiểu đo/đơn vị phù hợp; **không tự thay `==` bằng epsilon cố định** cho mọi thang đo.
5. Circle cũng là một Shape nhưng không phải một Rectangle; không được coi mọi hình có diện tích tương đương là cùng kiểu hình.

Cú pháp `when` trong `switch` pattern là cú pháp final từ Java 21. Nó khác với `if (shape instanceof Rectangle r && r.width() == r.height())`, nơi `&&` là toán tử Boolean và pattern variables có flow scoping.

## 9. Equals, hashCode và toString trong case study hình học

Record cung cấp **value semantics** dựa trên component:

```java
var c1 = new Circle(new Point(0, 0), 2);
var c2 = new Circle(new Point(0, 0), 2);

System.out.println(c1.equals(c2)); // true
System.out.println(c1 == c2);      // false (hai object khác nhau)
System.out.println(c1.radius());   // 2.0
```

Hai Circle được so sánh bằng **tâm và bán kính**, không chỉ bán kính. Hai Rectangle chỉ bằng nhau theo record value semantics nếu **center, width và height** tương ứng bằng nhau theo quy tắc so sánh component. Điều này phù hợp khi đối tượng biểu diễn **trạng thái hình học**.

Nhưng “bằng nhau theo record” **không giống** “bằng nhau về hình học” trong mọi domain:

- Một Rectangle `width=4,height=6` xoay 90 độ (không được mô hình hóa ở đây) có thể tạo cùng tập điểm với Rectangle `width=6,height=4` sau biến đổi phù hợp, nhưng hai records khác components.
- Hai Circle có sai số tọa độ cực nhỏ thường không `equals` dù thuật toán hình học coi chúng tương đương với tolerance.
- `double` có ngữ nghĩa đặc biệt với `NaN`, `Infinity` và signed zero; bài học chặn NaN/Infinity ở constructor nhưng tọa độ `0.0` và `-0.0` vẫn có thể gây khác biệt ở value equality. Không dùng `equals` để thay một thuật toán “hình học gần bằng”.

**Gợi ý thiết kế:** giữ `equals`/`hashCode` được record sinh cho **giá trị dữ liệu chính xác**; khi cần so gần đúng, viết phương thức `geometricallyEquivalent(a,b,tolerance)` với hợp đồng riêng, không tùy tiện làm `equals` bỏ qua sai số vì sẽ phức tạp hóa hợp đồng hash collections.

Record cũng sinh `toString()` có dạng dễ debug:

```text
Circle[center=Point[x=0.0, y=0.0], radius=2.0]
```

Đây là dạng hiển thị chuẩn được tạo bởi record class trong ví dụ. Tuy nhiên **không dùng `toString()` làm định dạng serialization/API ổn định**: nếu thay đổi tên component hoặc schema, chuỗi cũng thay đổi.

## 10. Vì sao validate double vẫn chưa đủ?

Có ba mức an toàn số cần phân biệt:

### 10.1. Tránh số không hợp lệ ngay tại component

Constructor chặn:

- Radius `0` hoặc âm.
- Width/height `0` hoặc âm.
- `NaN` và `Infinity` cho vị trí và kích thước.
- Center null.

Đó là bảo vệ **dữ liệu đầu vào**.

### 10.2. Tránh overflow khi tính toán

Một `double` hữu hạn vẫn có thể quá lớn để bình phương. Ví dụ `radius = 1e200` là hữu hạn, nhưng `π * radius * radius` có thể overflow thành `Infinity`. Vì vậy chương trình dùng:

```java
static double finiteMeasure(double value) {
    if (!Double.isFinite(value)) {
        throw new ArithmeticException("geometry measure overflow");
    }
    return value;
}
```

Hàm này từ chối **kết quả không hữu hạn** trong `area`/`perimeter`. Nó không phát hiện **underflow** về 0 ở kích thước cực nhỏ, hay mọi sai số làm tròn. Nếu domain cần độ chính xác cao, phải định nghĩa khoảng giá trị được phép, đơn vị, và độ chính xác trước khi triển khai.

### 10.3. Chọn epsilon đúng domain khi so hình

`width == height` có ý nghĩa phân loại dữ liệu đúng theo bit/giá trị double trong demo. Nhưng khi dữ liệu đến từ phép biến đổi liên tục, ví dụ lấy kết quả phép chia, quy tắc “tương đương trong sai số đo” phải có chính sách:

\[
|w-h|\le \varepsilon_{\text{abs}}
\]

hoặc kết hợp tolerance tuyệt đối/tương đối khi thang đo biến thiên rộng. Không có một `epsilon=1e-9` phổ quát cho mọi đơn vị (mm, pixel, km) và miền dữ liệu. Bài toán CAD/đo đạc, tài chính hoặc đồ họa có những yêu cầu khác nhau.

**Không nên dùng `BigDecimal` cho mọi hình học theo phản xạ.** Các công thức chứa π/căn bậc hai và các phép toán hình học sẽ cần chiến lược precision/rounding riêng. `double` phù hợp với nhiều bài toán 2D thông thường nếu invariant và tolerance được thiết kế rõ.

## 11. Mở rộng thiết kế mà không phá hợp đồng

### 11.1. Nếu chỉ cần kích thước, có thể bỏ center

Một bài toán chỉ tính area/perimeter và không quan tâm vị trí có thể đơn giản hóa:

```java
record Circle(double radius) {}
record Rectangle(double width, double height) {}
```

Đây là **một mô hình khác** và cần constructor validation nếu muốn chặn số không hợp lệ. Không nên thêm `Point center` nếu không có thao tác nào dùng đến vị trí. Trong chương trình đầy đủ, center tồn tại vì ta kiểm tra **point containment**.

### 11.2. Nếu cần xoay Rectangle

Rectangle song song trục không mô tả một rectangle tùy ý đã xoay. Một lựa chọn khác là:

```java
// Chỉ minh họa schema, chưa có validation/phép toán.
record RotatedRectangle(
        Point center,
        double width,
        double height,
        double angleRadians) {}
```

Phải định nghĩa góc quay, quy ước tọa độ, normalize angle và công thức chuyển hệ tọa độ trước khi dùng record này. Không dùng thuật toán `contains` cho axis-aligned Rectangle trực tiếp lên rectangle xoay vì sẽ sai.

### 11.3. Nếu cần Square là kiểu độc lập

Nếu Square có quy tắc nghiệp vụ riêng (ví dụ giá bán, ràng buộc riêng, API riêng), có thể cân nhắc:

```java
// Ví dụ một mô hình khác; phải cập nhật sealed permits tương ứng.
record Square(Point center, double side) implements Shape {}
```

**Đoạn này KHÔNG biên dịch khi ghép nguyên văn vào chương trình mục 5** vì sealed `Shape` hiện chỉ permits Circle/Rectangle. Muốn thêm Square thì phải cập nhật `permits`, area/perimeter/kind/contains/scale và test. Đó là hành vi **mong muốn** của exhaustiveness check: compiler nhắc xử lý một biến thể domain mới.

### 11.4. Nếu model là API public

Trong chương trình demo, `Shape`, `Point`, `Circle` và `Rectangle` là kiểu lồng package-private để chạy từ một file. Trong một thư viện thật, có thể đặt từng record ở một file riêng, có package tường minh, chú thích Javadoc, và khai báo `public` nếu thuộc public API. Cần xét đến:

- Tương thích nhị phân và source của **record component list** (đổi thứ tự/kiểu có thể phá constructor/pattern callers).
- Quy tắc serialization (nếu cần), schema version, JSON mapper, module boundaries.
- Đơn vị đo được khai báo trong API; nếu cần có thể dùng `Length` value type thay vì `double` trần.
- Không đưa logic tính toán phức tạp vào accessor record vì record patterns có thể gọi accessor khi deconstruct.

## 12. Test các trường hợp biên, không chỉ kiểm tra công thức

Một bộ test có giá trị nên bao phủ ít nhất:

| Tình huống | Kết quả mong đợi theo hợp đồng bài |
| --- | --- |
| Circle `r=2` | `area≈12.566` và `perimeter≈12.566` |
| Rectangle `w=4,h=6` | `area=24`, `perimeter=20` |
| Rectangle `w=h=4` | `kind(...) = "SQUARE"` |
| Circle point trên biên `(2,0)` | `contains == true` |
| Circle point ngoài `(2.1,0)` | `contains == false` |
| Rectangle point ở góc `(3,4)` | `contains == true` |
| Rectangle point ngoài `(3.01,4)` | `contains == false` |
| Scale factor `2` | Tạo record mới, bản gốc không đổi; area ×4, perimeter ×2 |
| Radius `0` hoặc âm | `IllegalArgumentException` |
| Width/height `NaN`/`Infinity` | `IllegalArgumentException` |
| Center null | `NullPointerException` ngay tại constructor |
| Selector null trong `kind` | `"MISSING"` |
| Selector null trong `area`/`perimeter` | `IllegalArgumentException` |
| Point null trong `contains` | `NullPointerException` |
| Kích thước hữu hạn nhưng tích quá lớn | `ArithmeticException` trong `area`/`perimeter` nếu kết quả không hữu hạn |

**Lưu ý về số thực:** Khi test diện tích Circle, kiểm tra với tolerance thích hợp thay vì `assertEquals(12.57, area(circle))`, vì giá trị thực xấp xỉ `12.5663706...` và chuỗi hiển thị đã bị format hai chữ số.

### 12.1. Property-based tests cho mô hình record

Một số property hữu ích:

- Với mọi Circle hợp lệ: `area > 0`, `perimeter > 0` nếu kết quả hữu hạn và không underflow.
- Với mọi Rectangle hợp lệ: đổi chỗ width/height **không đổi area/perimeter**, dù record `equals` có thể khác.
- Với hệ số `k > 0` hợp lệ và không overflow/underflow: `area(scale(s,k)) ≈ k² * area(s)`, `perimeter(scale(s,k)) ≈ k * perimeter(s)`.
- Với cùng center, tăng radius của Circle không thể khiến một point **đã nằm trong Circle nhỏ** rơi ra ngoài Circle lớn, nếu phép tính số phù hợp.
- Với Rectangle axis-aligned, điểm tại center luôn nằm trong hình hợp lệ.

Khi viết property tests, sinh boundary values (0, số dương rất nhỏ, số rất lớn, NaN, Infinity, giá trị vừa đủ qua điều kiện) và phân biệt miền input **hợp lệ** với miền test constructor rejection. Test thuộc tính số học cần quy tắc tolerance/overflow rõ ràng để không tạo false positive.

### 12.2. Đừng dùng exception-swallowing trong production

Hàm `outcome` của chương trình mẫu bắt `RuntimeException` chỉ để **in tên exception trong demo**. Trong ứng dụng thật, không nên nuốt toàn bộ lỗi rồi trả về một chuỗi chung. Nếu đang xử lý request ngoài, map các lỗi validation sang phản hồi API hợp lệ và giữ stack trace/log ở nơi thích hợp.

## 13. Những lỗi phổ biến khi biểu diễn hình bằng record

1. **Không kiểm tra radius/width/height**, dẫn đến hình có diện tích âm/NaN/Infinity.
2. **Cho rằng record tự bất biến sâu**, trong khi component có thể tham chiếu đến mảng/list/object mutable.
3. **Trộn hai cách biểu diễn Rectangle:** `(x,y)` là tâm trong code nhưng lại đọc như góc trái trên.
4. **Không nói rõ hình chữ nhật có xoay hay không**, sau đó áp dụng công thức contains axis-aligned cho hình xoay.
5. **Dùng `double ==` cho mọi phép so gần đúng**, nhất là dữ liệu qua phép tính hoặc phép đo.
6. **Nhầm record component accessors với getter JavaBean**: `width()` không phải `getWidth()`.
7. **Đặt nhánh Rectangle không guard trước nhánh Square `when`**, gây dominated pattern.
8. **Thêm `default` vô điều kiện cho sealed switch** và mất cảnh báo khi thêm biến thể Shape mới.
9. **Quên null ở selector so với record component**, dẫn đến `NullPointerException` hoặc `MatchException` không mong muốn.
10. **Scale bằng cách cố sửa field final**, thay vì tạo record mới.
11. **Tính bình phương bằng phép nhân double không kiểm tra overflow**, rồi truyền Infinity sang phần khác của hệ thống.
12. **So sánh `Circle` bằng radius duy nhất**, bỏ qua tâm dù model định nghĩa chúng là component của giá trị.
13. **Dùng `toString()` của record làm JSON/schema công khai**, khiến đổi record component làm hỏng downstream.
14. **Coi `sealed` luôn tốt hơn interface mở**, ngay cả khi có plugin cần implement Shape ngoài module.
15. **Tách Square thành subclass của Rectangle record**, điều không thể vì record là final.

## 14. Checklist code review

- [ ] Có mô tả rõ `Circle`, `Rectangle`, cách định nghĩa vị trí/tâm, trục và đơn vị đo?
- [ ] Có bảo vệ invariant của `Point`, `Circle`, `Rectangle` bằng compact constructor không?
- [ ] Các kiểu tham chiếu trong record có thật sự bất biến hoặc đã có defensive-copy policy?
- [ ] `Shape` nên là sealed hierarchy hay domain cần extension bên ngoài?
- [ ] Tính area/perimeter/contains có đúng công thức của mô hình, kể cả đường biên?
- [ ] Cú pháp Java 21 record patterns có đúng thứ tự/kiểu component?
- [ ] `when` Square đứng trước Rectangle fallback và có test width==height?
- [ ] Chính sách đối với null selector và null component đã rõ ràng?
- [ ] Có phân biệt value equality với gần bằng theo hình học và tolerance?
- [ ] Có kiểm tra overflow/precision khi sử dụng double ở domain thực tế?
- [ ] Scale có làm rõ tâm bất biến hay scale quanh gốc tọa độ?
- [ ] Đã có test constructor rejection, số thực, cực trị, case fallback và exhaustiveness chưa?

**Kết luận:** `record` rất thích hợp để biểu diễn các hình có **dữ liệu cố định và value semantics** như `Circle` và `Rectangle`. Hãy **định nghĩa invariant trước**, chọn hệ tọa độ và đơn vị rõ ràng, dùng `sealed Shape` khi tập hình đóng, rồi khai thác **record patterns và pattern switch Java 21** để xử lý dữ liệu gọn, kiểm tra exhaustiveness và tránh cast thủ công. Chính quy tắc hình học và độ an toàn số — không chỉ cú pháp record — quyết định mô hình này có đáng tin cậy hay không.

### Tài liệu tham khảo

- OpenJDK JEP 395 — Records (final trong Java 16): https://openjdk.org/jeps/395
- OpenJDK JEP 409 — Sealed Classes (final trong Java 17): https://openjdk.org/jeps/409
- OpenJDK JEP 440 — Record Patterns (final trong Java 21): https://openjdk.org/jeps/440
- OpenJDK JEP 441 — Pattern Matching for switch (final trong Java 21): https://openjdk.org/jeps/441
- Oracle Java 21 — Record Classes: https://docs.oracle.com/en/java/javase/21/language/records.html
- Oracle Java 21 — Record Patterns: https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
- Oracle Java 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- Java Language Specification SE 21 — Record Classes `8.10: https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10
