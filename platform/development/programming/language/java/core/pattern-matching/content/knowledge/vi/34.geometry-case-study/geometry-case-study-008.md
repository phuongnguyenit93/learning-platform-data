# So sánh `instanceof` + cast cũ với Pattern Matching: Case study hình học (Java 21+)

## 1. Mục tiêu và vấn đề thực tế

Một ứng dụng hình học cần xử lý nhiều loại hình: **hình tròn**, **hình chữ nhật** và **tam giác**. Mỗi hình mang dữ liệu khác nhau:

- **Circle:** tâm `Point` và bán kính `radius`.
- **Rectangle:** điểm gốc `origin` cùng `width` và `height`.
- **Triangle:** ba đỉnh `a`, `b`, `c`.

Các thao tác thường gặp gồm tính **diện tích**, **chu vi** hoặc lấy tọa độ mốc để hiển thị. Trong Java cũ, lập trình viên hay dùng `instanceof`, sau đó **ép kiểu tường minh** để truy cập dữ liệu:

~~~java
if (shape instanceof Circle) {
    Circle circle = (Circle) shape;
    return Math.PI * circle.radius() * circle.radius();
}
~~~

Cách này đúng nếu kiểm tra kiểu trước khi cast, nhưng lặp lại tên kiểu và tăng số dòng khi các hình được xử lý liên tục. Java hiện đại bổ sung:

1. **Type pattern với `instanceof`**: kiểm tra kiểu và khai báo biến cùng lúc.
2. **Record pattern**: kiểm tra record và phân rã những component cần dùng.
3. **Pattern matching trong `switch`**: biểu diễn những nhánh theo subtype một cách tập trung; khi kết hợp với tập subtype `sealed`, compiler có thể kiểm tra tính **exhaustive**.

**Điều không thay đổi:** các cách viết vẫn phải tính **cùng công thức**, tuân thủ **cùng hợp đồng `null`** và bảo vệ **cùng invariant hình học**. Pattern matching làm rõ cấu trúc điều khiển, nhưng không tự thay thế validation hay bảo đảm hiệu năng vượt trội.

Bài dùng **Java 21+** để chạy record pattern và pattern `switch` ổn định. Type pattern của `instanceof` đã ổn định từ Java 16; `record` từ Java 16 và `sealed` từ Java 17. Nếu dự án còn ở Java 17, bạn có thể dùng type pattern và `sealed`, nhưng không thể chép nguyên cú pháp record pattern Java 21.

## 2. Mô hình hóa các hình bằng `sealed` và `record`

Thiết kế kiểu chung:

~~~java
sealed interface Shape permits Circle, Rectangle, Triangle {}

record Point(double x, double y) {}
record Circle(Point center, double radius) implements Shape {}
record Rectangle(Point origin, double width, double height)
        implements Shape {}
record Triangle(Point a, Point b, Point c) implements Shape {}
~~~

Đây là **khai báo minh họa** chưa có constructor validation. Ví dụ hoàn chỉnh ở mục 8 sẽ thêm kiểm tra dữ liệu.

`Shape` cho phép đúng ba direct subtype. Vì ba subtype là `record` nên chúng là `final` theo mặc định; ở mô hình minh họa này không có subtype khác được khai báo tùy ý. Điều này quan trọng cho `switch expression` không cần `default`.

### Công thức của từng loại hình

| Hình | Diện tích | Chu vi |
| --- | --- | --- |
| Hình tròn bán kính `r` | `π × r²` | `2 × π × r` |
| Hình chữ nhật rộng `w`, cao `h` | `w × h` | `2 × (w + h)` |
| Tam giác có ba đỉnh A, B, C | `abs(cross(B-A, C-A)) / 2` | `AB + BC + CA` |

Với tam giác có tọa độ `A(ax,ay)`, `B(bx,by)`, `C(cx,cy)`, đại lượng tích có hướng hai chiều (*signed cross product*) là:

~~~text
cross = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
area  = abs(cross) / 2
~~~

Để tính độ dài cạnh giữa hai điểm, dùng `Math.hypot(dx, dy)` thay vì trực tiếp viết `Math.sqrt(dx*dx + dy*dy)`. `hypot` thường xử lý việc scale số tốt hơn với các độ lớn khác nhau, nhưng vẫn phải kiểm tra dữ liệu hình học hợp lệ.

### Vì sao chọn `record`?

Record phù hợp với **dữ liệu dạng giá trị**: Java sinh accessor như `radius()`, `center()`, `width()` và triển khai `equals`, `hashCode`, `toString` theo component. Việc dùng record không tự cấm component tham chiếu `null` và không tự bảo đảm bán kính dương hay ba điểm không thẳng hàng. **Cần constructor validation.**

## 3. Cách cũ: `instanceof` rồi ép kiểu tường minh

Đây là phiên bản tính diện tích theo lối truyền thống:

~~~java
static double areaLegacy(Shape shape) {
    java.util.Objects.requireNonNull(shape, "shape");

    if (shape instanceof Circle) {
        Circle c = (Circle) shape;
        return Math.PI * c.radius() * c.radius();
    }
    if (shape instanceof Rectangle) {
        Rectangle r = (Rectangle) shape;
        return r.width() * r.height();
    }
    if (shape instanceof Triangle) {
        Triangle t = (Triangle) shape;
        return Math.abs(cross(
                t.a().x(), t.a().y(),
                t.b().x(), t.b().y(),
                t.c().x(), t.c().y())) / 2.0;
    }
    throw new IllegalStateException("Unknown shape");
}
~~~

Đây là **phương thức minh họa**, cần `Shape` và hàm `cross` ở cùng phạm vi. Tệp độc lập ở mục 8 có đầy đủ.

Cơ chế:

1. `shape instanceof Circle` kiểm tra đối tượng tại runtime có phải `Circle` hay không.
2. Sau khi kiểm tra đúng, phép ép kiểu `(Circle) shape` an toàn với giá trị đã kiểm tra.
3. Nhánh tương ứng dùng accessor của record để tính diện tích.
4. Nếu không phải `Circle`, tiếp tục thử `Rectangle` rồi `Triangle`.

**Ưu điểm:** cú pháp dễ hiểu với người học Java cũ, hoạt động với mô hình kế thừa thông thường, không cần pattern `switch`. Khi chỉ có một nhánh đơn giản, viết `instanceof` theo kiểu cũ hoàn toàn chấp nhận được.

**Hạn chế:**

- Lặp tên kiểu: `instanceof Circle` rồi `(Circle) shape`.
- Dễ cast nhầm đối tượng hoặc nhầm kiểu nếu sửa code thủ công.
- Có thêm biến trung gian chỉ để chuyển đổi kiểu.
- Chuỗi `if` không tự nhận bảo đảm exhaustive của compiler như pattern `switch` trên `sealed Shape`. Nếu sau này thêm subtype mà quên cập nhật, nhánh cuối có thể ném `IllegalStateException` **khi chạy**, thay vì báo thiếu case **khi biên dịch**.

Ví dụ lỗi cast:

~~~java
Object value = new Circle(new Point(0, 0), 2);

// CỐ Ý SAI: Circle không phải Rectangle.
// Nếu chạy, dòng này ném ClassCastException.
Rectangle wrong = (Rectangle) value;
~~~

Đừng nhầm lỗi cast này với việc dùng `instanceof` có kiểm tra trước: bản thân cú pháp cast không nguy hiểm nếu đặt sau một kiểm tra kiểu đúng, nhưng nó tạo thêm bước mà người viết phải duy trì chính xác.

## 4. Cải tiến đầu tiên: type pattern với `instanceof`

Type pattern giữ nguyên ý tưởng kiểm tra kiểu nhưng bỏ phép ép kiểu thủ công:

~~~java
static double areaTypePattern(Shape shape) {
    java.util.Objects.requireNonNull(shape, "shape");

    if (shape instanceof Circle c) {
        return Math.PI * c.radius() * c.radius();
    }
    if (shape instanceof Rectangle r) {
        return r.width() * r.height();
    }
    if (shape instanceof Triangle t) {
        return Math.abs(cross(
                t.a().x(), t.a().y(),
                t.b().x(), t.b().y(),
                t.c().x(), t.c().y())) / 2.0;
    }
    throw new IllegalStateException("Unknown shape");
}
~~~

Mẫu `shape instanceof Circle c` làm hai việc **cùng lúc**:

- Kiểm tra đối tượng có phù hợp với `Circle`.
- Khi khớp, tạo biến mẫu `c` có kiểu tĩnh `Circle`.

Không phải lặp `Circle c = (Circle) shape`; compiler quản lý phạm vi biến dựa trên luồng điều khiển (*flow scoping*).

### Flow scoping trong thực tế

~~~java
Object input = new Circle(new Point(1, 2), 2);

if (input instanceof Circle c && c.radius() > 1) {
    System.out.println("large circle: " + c.radius());
}
~~~

Kết quả:

~~~text
large circle: 2.0
~~~

Biến `c` có phạm vi ở vế phải của `&&` vì khi Java đánh giá tới đó, mẫu ở vế trái đã khớp. Ngược lại, nếu `instanceof` trả false, `c` không được đưa vào sử dụng.

Cần tránh nhầm với biểu thức `||`, nơi vế phải có thể chạy khi mẫu bên trái không khớp; dùng biến mẫu không đúng phạm vi có thể bị compiler từ chối.

### Những gì type pattern chưa giải quyết

Type pattern vẫn giữ **nhiều nhánh `if` nối tiếp** và vẫn phải gọi accessor:

~~~java
if (shape instanceof Triangle t) {
    double ax = t.a().x();
    double ay = t.a().y();
    // ...
}
~~~

Khi cấu trúc là record lồng nhiều tầng và cần nhiều component, việc truy cập liên tiếp có thể làm code rườm rà. Đó là nơi **record pattern** phát huy tác dụng.

## 5. Record pattern: phân rã hình học ngay khi khớp

Java 21 cho phép sử dụng record pattern trực tiếp trong `instanceof`:

~~~java
Object value = new Circle(new Point(1, 2), 2);

if (value instanceof Circle(Point(var x, var y), var r)) {
    System.out.println("center=" + x + "," + y + "; radius=" + r);
}
~~~

Kết quả:

~~~text
center=1.0,2.0; radius=2.0
~~~

Cách đọc:

1. `Circle(...)` yêu cầu đầu vào là một `Circle`.
2. `Point(var x, var y)` là **record pattern lồng**, phân rã component `center` thành `x` và `y`.
3. `var r` nhận giá trị component `radius`, có kiểu suy ra là `double`.
4. Không cần cast `Circle`, lấy `circle.center()` rồi gọi `center.x()`/`center.y()` theo từng bước.

Một ưu điểm là **cấu trúc dữ liệu được diễn đạt ngay trong pattern**, giúp người đọc thấy thành phần nào đang được dùng.

Record pattern không bắt buộc phải phân rã mọi cấp: `Circle(var center, var radius)` vẫn hợp lệ và giữ `center` như một `Point`. **Chỉ nên destructure sâu khi thực sự dùng dữ liệu bên trong**, không phải lúc nào cũng mở hết mọi component.

### Record pattern khác constructor call

~~~java
new Circle(new Point(1, 2), 2);  // Tạo một record mới.

value instanceof Circle(Point(var x, var y), var r); // Khớp record có sẵn.
~~~

Pattern **không tạo bản sao** của record. Nó kiểm tra và lấy các component của đối tượng đã tồn tại. Vì vậy, đừng giả định record pattern làm phát sinh một `new Circle` hay có chi phí cấp phát riêng chỉ vì biểu thức có dấu ngoặc giống constructor.

## 6. `switch` trên `sealed Shape`: loại bỏ chuỗi `if` dài

Khi biết tập subtype là đóng, có thể biểu diễn hàm diện tích thành một `switch expression`:

~~~java
static double areaRecordSwitch(Shape shape) {
    java.util.Objects.requireNonNull(shape, "shape");

    return switch (shape) {
        case Circle(var center, var radius) ->
                Math.PI * radius * radius;

        case Rectangle(var origin, var width, var height) ->
                width * height;

        case Triangle(Point(var ax, var ay),
                      Point(var bx, var by),
                      Point(var cx, var cy)) ->
                Math.abs(cross(ax, ay, bx, by, cx, cy)) / 2.0;
    };
}
~~~

Mỗi `case` ánh xạ trực tiếp một hình sang công thức. `Triangle` dùng record pattern lồng để lấy tọa độ ba đỉnh; công thức cross product không cần các accessor dài.

**Vì sao không có `default`?** `Shape` là sealed với đúng ba subtype record: `Circle`, `Rectangle`, `Triangle`. Các nhánh không có guard bao phủ chúng, nên compiler Java 21 có thể xác nhận tính **exhaustive** đối với các subtype hiện được phép.

Điều này mang một lợi ích bảo trì quan trọng. Nếu sau này bổ sung subtype `Ellipse` vào `permits` và biên dịch lại, một `switch expression` chưa có nhánh phù hợp có thể bị compiler báo **không bao phủ đủ**. Với chuỗi `if` truyền thống, bạn thường chỉ thấy hành vi fallback hoặc lỗi tại runtime nếu quên xử lý.

### Không phải lúc nào `switch` cũng là đáp án duy nhất

- Nếu chỉ có **một phép kiểm tra**, `if (obj instanceof Circle c)` có thể ngắn và dễ hiểu hơn.
- Nếu có **một tập variant đóng** và cần tính một kết quả cho mọi variant, `switch expression` rất phù hợp.
- Nếu hành vi thuộc trách nhiệm tự nhiên của mỗi subtype, có thể đặt method trừu tượng trên interface và triển khai bằng **đa hình**, không cần một `switch` tập trung cho mọi thao tác.
- Nếu hệ thống cần plugin bên ngoài bổ sung shape tự do, `sealed` có thể không phù hợp vì nó cố tình giới hạn tập subtype.

Pattern matching là một lựa chọn thiết kế, không phải mệnh lệnh phải loại bỏ mọi `if`/cast hoặc mọi phương thức đa hình.

## 7. Chu vi và tọa độ mốc: áp dụng linh hoạt nhiều kiểu pattern

Với chu vi, ta có thể giữ lại ba biến điểm của tam giác thay vì phân rã hết thành sáu tọa độ:

~~~java
static double perimeter(Shape shape) {
    java.util.Objects.requireNonNull(shape, "shape");

    return switch (shape) {
        case Circle(var center, var radius) ->
                2 * Math.PI * radius;

        case Rectangle(var origin, var width, var height) ->
                2 * (width + height);

        case Triangle(var a, var b, var c) ->
                Math.hypot(a.x() - b.x(), a.y() - b.y())
                + Math.hypot(b.x() - c.x(), b.y() - c.y())
                + Math.hypot(c.x() - a.x(), c.y() - a.y());
    };
}
~~~

Hãy chú ý `Triangle(var a, var b, var c)` dùng **component pattern nông**: ba biến `a`, `b`, `c` có kiểu `Point`. Vì phép tính chu vi cần từng điểm để tính khoảng cách, cách này dễ đọc hơn việc bung cả sáu tọa độ ngay trong `case`.

Còn khi chỉ cần tọa độ mốc để hiển thị, record pattern lồng có ích:

~~~java
static String anchor(Shape shape) {
    java.util.Objects.requireNonNull(shape, "shape");

    return switch (shape) {
        case Circle(Point(var x, var y), var radius) ->
                "circle-center:" + x + "," + y;

        case Rectangle(Point(var x, var y), var w, var h) ->
                "rect-origin:" + x + "," + y;

        case Triangle(Point(var ax, var ay), var b, var c) ->
                "triangle-a:" + ax + "," + ay;
    };
}
~~~

Các hàm ở mục này là **thành phần minh họa** trong lớp có các record và hàm phụ trợ tương ứng. Bản chương trình độc lập đầy đủ ở mục 8.

### Ba nguyên tắc chọn độ sâu của pattern

1. **Cần cả object?** Dùng `var point` hoặc type pattern `Point p`, không phân rã không cần thiết.
2. **Chỉ cần vài component?** Dùng record pattern lồng ở mức vừa đủ.
3. **Có quy tắc tính toán phức tạp?** Cân nhắc trích thành method có tên rõ để tránh biến `case` thành một biểu thức khổng lồ.

Mục tiêu là giúp người đọc nhận ra ngay **loại hình → dữ liệu được lấy → công thức được áp dụng**.

## 8. Chương trình Java 21 hoàn chỉnh — so sánh ba cách viết

Lưu nguyên mã sau vào tệp **`GeometryPatternComparisonDemo.java`**. Chương trình không cần thư viện ngoài JDK.

~~~java
public class GeometryPatternComparisonDemo {
    sealed interface Shape permits Circle, Rectangle, Triangle {}

    record Point(double x, double y) {
        Point {
            if (!Double.isFinite(x) || !Double.isFinite(y)
                    || Math.abs(x) > 1_000_000
                    || Math.abs(y) > 1_000_000) {
                throw new IllegalArgumentException("coordinates");
            }
        }
    }

    record Circle(Point center, double radius) implements Shape {
        Circle {
            requirePoint(center, "center");
            requireSize(radius, "radius");
        }
    }

    record Rectangle(Point origin, double width, double height)
            implements Shape {
        Rectangle {
            requirePoint(origin, "origin");
            requireSize(width, "width");
            requireSize(height, "height");
        }
    }

    record Triangle(Point a, Point b, Point c) implements Shape {
        Triangle {
            requirePoint(a, "a");
            requirePoint(b, "b");
            requirePoint(c, "c");
            double cross = cross(
                    a.x(), a.y(), b.x(), b.y(), c.x(), c.y());
            if (cross == 0.0 || !Double.isFinite(cross)) {
                throw new IllegalArgumentException(
                        "degenerate triangle");
            }
        }
    }

    static Point requirePoint(Point p, String field) {
        if (p == null) {
            throw new IllegalArgumentException(field);
        }
        return p;
    }

    static void requireSize(double size, String field) {
        if (!Double.isFinite(size) || size <= 0 || size > 1_000_000) {
            throw new IllegalArgumentException(field);
        }
    }

    static double cross(double ax, double ay, double bx, double by,
                        double cx, double cy) {
        return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax);
    }

    static double areaLegacy(Shape shape) {
        java.util.Objects.requireNonNull(shape, "shape");
        if (shape instanceof Circle) {
            Circle c = (Circle) shape;
            return Math.PI * c.radius() * c.radius();
        }
        if (shape instanceof Rectangle) {
            Rectangle r = (Rectangle) shape;
            return r.width() * r.height();
        }
        if (shape instanceof Triangle) {
            Triangle t = (Triangle) shape;
            return Math.abs(cross(
                    t.a().x(), t.a().y(),
                    t.b().x(), t.b().y(),
                    t.c().x(), t.c().y())) / 2.0;
        }
        throw new IllegalStateException("Unknown shape");
    }

    static double areaTypePattern(Shape shape) {
        java.util.Objects.requireNonNull(shape, "shape");
        if (shape instanceof Circle c) {
            return Math.PI * c.radius() * c.radius();
        }
        if (shape instanceof Rectangle r) {
            return r.width() * r.height();
        }
        if (shape instanceof Triangle t) {
            return Math.abs(cross(
                    t.a().x(), t.a().y(),
                    t.b().x(), t.b().y(),
                    t.c().x(), t.c().y())) / 2.0;
        }
        throw new IllegalStateException("Unknown shape");
    }

    static double areaRecordSwitch(Shape shape) {
        java.util.Objects.requireNonNull(shape, "shape");
        return switch (shape) {
            case Circle(var center, var radius) ->
                    Math.PI * radius * radius;
            case Rectangle(var origin, var width, var height) ->
                    width * height;
            case Triangle(Point(var ax, var ay),
                          Point(var bx, var by),
                          Point(var cx, var cy)) ->
                    Math.abs(cross(
                            ax, ay, bx, by, cx, cy)) / 2.0;
        };
    }

    static double perimeter(Shape shape) {
        java.util.Objects.requireNonNull(shape, "shape");
        return switch (shape) {
            case Circle(var center, var radius) ->
                    2 * Math.PI * radius;
            case Rectangle(var origin, var width, var height) ->
                    2 * (width + height);
            case Triangle(var a, var b, var c) ->
                    Math.hypot(a.x() - b.x(), a.y() - b.y())
                    + Math.hypot(b.x() - c.x(), b.y() - c.y())
                    + Math.hypot(c.x() - a.x(), c.y() - a.y());
        };
    }

    static String anchor(Shape shape) {
        java.util.Objects.requireNonNull(shape, "shape");
        return switch (shape) {
            case Circle(Point(var x, var y), var radius) ->
                    "circle-center:" + x + "," + y;
            case Rectangle(Point(var x, var y), var w, var h) ->
                    "rect-origin:" + x + "," + y;
            case Triangle(Point(var ax, var ay), var b, var c) ->
                    "triangle-a:" + ax + "," + ay;
        };
    }

    static int passed = 0;

    static void checkClose(
            String label, double actual, double expected) {
        if (!Double.isFinite(actual) ||
                Math.abs(actual - expected) > 1e-9) {
            throw new AssertionError(
                    label + ": " + actual + " != " + expected);
        }
        ++passed;
        System.out.println("PASS " + label);
    }

    static void check(String label, boolean ok) {
        if (!ok) {
            throw new AssertionError(label);
        }
        ++passed;
        System.out.println("PASS " + label);
    }

    static void invalid(String label, Runnable run) {
        try {
            run.run();
            throw new AssertionError(
                    "Expected IllegalArgumentException: " + label);
        } catch (IllegalArgumentException expected) {
            check(label, true);
        }
    }

    static void expectNull(String label, Runnable run) {
        try {
            run.run();
            throw new AssertionError(
                    "Expected NullPointerException: " + label);
        } catch (NullPointerException expected) {
            check(label, true);
        }
    }

    public static void main(String[] args) {
        Shape circle = new Circle(new Point(1, 2), 2);
        Shape rect = new Rectangle(new Point(-1, 1), 3, 4);
        Shape triangle = new Triangle(
                new Point(0, 0), new Point(3, 0),
                new Point(0, 4));

        Shape[] shapes = { circle, rect, triangle };
        String[] labels = { "circle", "rect", "triangle" };
        double[] areas = { 4 * Math.PI, 12, 6 };
        double[] perimeters = { 4 * Math.PI, 14, 12 };
        String[] anchors = {
            "circle-center:1.0,2.0",
            "rect-origin:-1.0,1.0",
            "triangle-a:0.0,0.0"
        };

        for (int i = 0; i < shapes.length; ++i) {
            String label = labels[i];

            checkClose(label + "-legacy",
                    areaLegacy(shapes[i]), areas[i]);
            checkClose(label + "-type",
                    areaTypePattern(shapes[i]), areas[i]);
            checkClose(label + "-record",
                    areaRecordSwitch(shapes[i]), areas[i]);
            checkClose(label + "-perimeter",
                    perimeter(shapes[i]), perimeters[i]);
            check(label + "-anchor",
                    anchor(shapes[i]).equals(anchors[i]));
        }

        Object unknown = "not a shape";
        check("unrelated-instanceof",
                !(unknown instanceof Circle c));

        Object missing = null;
        check("null-instanceof",
                !(missing instanceof Circle c));

        check("record-value-equality",
                new Circle(new Point(1, 2), 2).equals(circle));

        invalid("zero-radius",
                () -> new Circle(new Point(0, 0), 0));
        invalid("negative-width",
                () -> new Rectangle(new Point(0, 0), -2, 3));
        invalid("nan-height",
                () -> new Rectangle(new Point(0, 0), 2, Double.NaN));
        invalid("infinite-coordinate",
                () -> new Point(Double.POSITIVE_INFINITY, 0));
        invalid("null-center",
                () -> new Circle(null, 2));
        invalid("collinear-triangle",
                () -> new Triangle(
                        new Point(0, 0),
                        new Point(1, 1),
                        new Point(2, 2)));
        invalid("null-triangle-point",
                () -> new Triangle(
                        new Point(0, 0), null, new Point(1, 1)));
        expectNull("null-area",
                () -> areaRecordSwitch(null));

        System.out.println("ALL PASSED: " + passed);
    }
}
~~~

### Biên dịch và chạy

Dùng JDK 21 trở lên:

~~~bash
javac --release 21 GeometryPatternComparisonDemo.java
java GeometryPatternComparisonDemo
~~~

**Output chính xác:**

~~~text
PASS circle-legacy
PASS circle-type
PASS circle-record
PASS circle-perimeter
PASS circle-anchor
PASS rect-legacy
PASS rect-type
PASS rect-record
PASS rect-perimeter
PASS rect-anchor
PASS triangle-legacy
PASS triangle-type
PASS triangle-record
PASS triangle-perimeter
PASS triangle-anchor
PASS unrelated-instanceof
PASS null-instanceof
PASS record-value-equality
PASS zero-radius
PASS negative-width
PASS nan-height
PASS infinite-coordinate
PASS null-center
PASS collinear-triangle
PASS null-triangle-point
PASS null-area
ALL PASSED: 26
~~~

### Cách đọc bộ kiểm thử

Mỗi shape có **năm** phép kiểm tra: ba cách tính diện tích, một cách tính chu vi và một cách xác định tọa độ mốc. Ba shape tạo thành **15 phép kiểm tra đầu tiên**.

Các phép kiểm tra còn lại bao gồm:

- `unrelated-instanceof`: chuỗi không phải hình tròn thì `instanceof Circle` trả false.
- `null-instanceof`: selector null với `instanceof` trực tiếp cũng trả false.
- `record-value-equality`: record bằng nhau theo các component; hai `Circle` có cùng tâm và bán kính được xem là bằng nhau theo `equals`.
- `zero-radius`, `negative-width`, `nan-height`, `infinite-coordinate`: constructor từ chối kích thước/toạ độ không hợp lệ.
- `null-center` và `null-triangle-point`: constructor từ chối record lồng bị thiếu.
- `collinear-triangle`: tam giác có ba điểm thẳng hàng không có diện tích và bị loại trong mô hình.
- `null-area`: `areaRecordSwitch(null)` từ chối null tường minh bằng `Objects.requireNonNull`.

Hàm `checkClose` dùng sai số tuyệt đối `1e-9` để so số thực, tránh yêu cầu mọi phép toán floating-point phải có biểu diễn chính xác tuyệt đối. Các phép kiểm tra thất bại sẽ ném `AssertionError` nên dòng `ALL PASSED: 26` chỉ xuất hiện nếu mọi ca đều đạt.

**Lưu ý:** Bộ kiểm thử xác minh các kết quả mẫu và đường xử lý quan trọng, không thay thế bộ test tính toán hình học chuyên sâu cho dữ liệu có độ lớn cực đoan.

## 9. So sánh ba kỹ thuật theo tiêu chí kỹ thuật

| Tiêu chí | `instanceof` + cast cũ | `instanceof` type pattern | Record pattern + `switch` |
| --- | --- | --- | --- |
| Cách nhận kiểu | `instanceof Circle` rồi cast | `instanceof Circle c` | `case Circle(...)` |
| Ép kiểu bằng tay | Có | Không | Không |
| Lấy dữ liệu | Gọi accessor trên object cast | Gọi accessor trên biến mẫu | Lấy trực tiếp các component qua pattern |
| Nested data | Nhiều accessor như `t.a().x()` | Vẫn có thể cần accessor | `Triangle(Point(var ax,...),...)` |
| Cấu trúc điều khiển | Chuỗi `if`/`else` | Chuỗi `if`/`else` | `switch` theo các subtype |
| Exhaustive với sealed shape | Không được kiểm tra tự động như `switch expression` | Không được kiểm tra tự động như `switch expression` | Compiler có thể kiểm tra đủ subtype |
| Hợp đồng null | Phải xác định riêng | `instanceof null` trả false; method tùy chính sách | Pattern switch cần xử lý null riêng |
| Dễ đọc khi vài subtype | Khá rõ nhưng lặp cast | Gọn, rõ | Có thể hơi nhiều cú pháp nếu chỉ một trường hợp |
| Dễ đọc khi nhiều variant đóng | Dễ dài và dễ quên case | Giảm cast nhưng vẫn nhiều nhánh | Tập trung và dễ rà soát |
| Hiệu năng | Phụ thuộc bytecode/JIT | Phụ thuộc bytecode/JIT | Phụ thuộc bytecode/JIT và workload |

### Kết luận lựa chọn

- **Một nhánh kiểm tra kiểu:** type pattern với `instanceof` thường là bản thay thế tự nhiên, ít thay đổi logic.
- **Nhiều subtype cùng cần một kết quả:** pattern `switch` trên `sealed` có lợi thế rõ rệt về tính đầy đủ.
- **Record có dữ liệu lồng:** record pattern đáng giá khi giúp giảm accessor và biểu thị cấu trúc cần xử lý.
- **Hành vi sở hữu bởi từng hình:** cân nhắc đưa `area()` hoặc `perimeter()` vào từng subtype bằng đa hình thay vì dồn mọi thứ vào một utility switch.

Đây là quyết định **thiết kế và tính dễ bảo trì**; không nên tự coi ít dòng code hơn là hiệu năng chạy nhanh hơn.

## 10. Null, validation và những tình huống dễ hiểu sai

### 10.1. Selector null với `instanceof`

~~~java
Object value = null;
System.out.println(value instanceof Circle c); // false
~~~

`instanceof` trực tiếp trả false nếu selector null. Biến mẫu `c` không có giá trị dùng được ở nhánh không khớp.

### 10.2. Selector null với pattern `switch`

Trong Java 21:

~~~java
// Mô tả hành vi của pattern switch:
// nếu không có case null và không kiểm tra trước,
// null selector có thể dẫn đến NullPointerException.
~~~

Bài chính chọn `Objects.requireNonNull(shape, "shape")` trước mỗi `switch`, vì API tính hình học **không chấp nhận null như một hình hợp lệ**. Cũng có thể viết `case null` khi null mang ý nghĩa nghiệp vụ cần xử lý; đừng giả định `default` tự nhận null.

### 10.3. Record component có thể null

Ngay cả một mẫu như `Circle(Point(var x, var y), var radius)` cũng không thay thế kiểm tra constructor. Nếu `center` null, pattern `Point(...)` lồng **không khớp**. Một component `String` hay `Point` được phân rã bằng `var` vẫn có thể nhận null nếu record cho phép. Riêng component pattern unconditional có ngữ nghĩa null khác với `instanceof` bên ngoài; không nên suy luận tổng quát rằng mọi type pattern đều loại null ở mọi vị trí.

Trong chương trình chính, `Circle`, `Rectangle` và `Triangle` có constructor từ chối các `Point` null. Điều đó giúp những chỗ tính toán có thể dựa vào **invariant domain**, chứ không phải một bảo đảm null tự động của record pattern.

### 10.4. Dữ liệu hình học phải hợp lệ

`Point` trong ví dụ từ chối `NaN`, vô cực và tọa độ có độ lớn hơn `1_000_000`. `Circle`/`Rectangle` yêu cầu kích thước dương, hữu hạn, tối đa `1_000_000`. `Triangle` yêu cầu đủ ba điểm và cross product hữu hạn, khác zero.

Giới hạn `1_000_000` là **quy ước phạm vi dữ liệu của case study** để phép tính đơn giản có giới hạn dễ dự đoán, không phải hằng số của hình học hay Java. Dự án bản đồ, CAD hoặc GIS có thể cần thang đo và thuật toán ổn định số khác.

## 11. Độ chính xác hình học: pattern không sửa lỗi số thực

Thử nghiệm hình học với `double` có các bẫy không liên quan đến cú pháp `instanceof`:

1. **Sai số floating-point:** không phải số thực nào cũng biểu diễn chính xác trong `double`. Dùng tolerance phù hợp khi so sánh diện tích/chu vi thay vì `==` một cách máy móc.
2. **Tam giác gần thẳng hàng:** ví dụ kiểm tra `cross == 0.0` để loại trường hợp thẳng hàng chính xác trong phạm vi demo. Các thuật toán tính toán hình học thực tế có thể cần **robust orientation predicates** hoặc chính sách tolerance dựa trên scale.
3. **Độ lớn tọa độ:** hiệu tọa độ và phép nhân có thể bị tràn số thực nếu cho input cực lớn. Demo đặt giới hạn tọa độ, kiểm tra `Double.isFinite(cross)`.
4. **Dấu của cross:** thứ tự đỉnh theo chiều kim đồng hồ hay ngược chiều tạo dấu khác nhau. Dùng `Math.abs(cross) / 2` để diện tích không âm.
5. **Chu vi tam giác:** cần cả ba độ dài cạnh; `Math.hypot` tính khoảng cách Euclidean từ hai hiệu tọa độ.
6. **Hình chữ nhật:** ví dụ định nghĩa rectangle trục song song với các trục, không mô hình hóa góc quay. Nếu cần hình xoay, cần thêm rotation hoặc các đỉnh.
7. **Đơn vị:** bán kính, kích thước và tọa độ phải dùng đơn vị nhất quán; diện tích có đơn vị bình phương, chu vi có đơn vị chiều dài.

Pattern matching giúp tổ chức code. **Công thức, invariant, đơn vị và độ chính xác** vẫn là trách nhiệm của thuật toán hình học.

## 12. Khi thêm một hình mới, cách nào bảo trì tốt hơn?

Giả sử bổ sung `Ellipse(Point center, double radiusX, double radiusY)`.

Với chuỗi `if` của `areaLegacy` hoặc `areaTypePattern`, compiler Java không tự báo rằng bạn **quên nhánh Ellipse**; các phương thức có thể tiếp tục tới nhánh lỗi `IllegalStateException`.

Với `areaRecordSwitch` và `perimeter` là `switch expression` exhaustive, nếu thêm `Ellipse` vào `Shape.permits` nhưng chưa thêm nhánh, việc **biên dịch lại** có thể báo lỗi thiếu trường hợp. Đây là lợi ích về tính an toàn khi phát triển với tập variant đóng.

Một subtype minh họa, **không được chép nguyên vào chương trình ở mục 8** nếu chưa sửa `permits` và các `switch`:

~~~java
record Ellipse(Point center, double radiusX, double radiusY)
        implements Shape {
    Ellipse {
        requirePoint(center, "center");
        requireSize(radiusX, "radiusX");
        requireSize(radiusY, "radiusY");
    }
}
~~~

Nếu thêm Ellipse, diện tích có công thức `π × radiusX × radiusY`. Chu vi ellipse tổng quát không có công thức sơ cấp đơn giản như chu vi hình tròn, nên cần chọn thuật toán xấp xỉ hoặc thư viện phù hợp và kiểm thử sai số.

**Không thêm `default -> 0` chỉ để làm compiler im lặng.** Điều đó có thể che lỗi khi thêm subtype mới. Nếu hệ thống thật cần xử lý variant chưa biết theo hợp đồng, fallback có thể hợp lý, nhưng phải được thiết kế và tài liệu hóa rõ ràng.

## 13. Khi nào dùng đa hình thay vì pattern matching?

Cả ba cách trong bài đều là dạng **phân nhánh theo kiểu ở phía consumer**. Một lựa chọn khác là đưa hành vi vào contract:

~~~java
interface MeasurableShape {
    double area();
    double perimeter();
}
~~~

Đây là một interface **minh họa**. Mỗi implementation tự tính diện tích và chu vi của mình; caller chỉ gọi `shape.area()` mà không cần `switch`. Cách này thường hợp lý khi:

- `area()` và `perimeter()` là trách nhiệm cốt lõi của từng shape.
- Có nhiều nơi sử dụng các hành vi này.
- Dự kiến thêm subtype thường xuyên, còn số loại thao tác ít thay đổi.

Ngược lại, pattern `switch` có thể phù hợp khi:

- Tập subtype ổn định và **đóng**.
- Có nhiều phép chuyển đổi/biểu diễn độc lập (render, serialize, export, report) mà không muốn đặt mọi biến thể hành vi vào domain object.
- Cần viết một phép chuyển đổi trên các variant tại một điểm tập trung và muốn compiler kiểm tra exhaustiveness.

Một hệ thống tốt có thể kết hợp cả hai: hành vi cốt lõi ở subtype, còn logic xuất báo cáo hoặc thích ứng tầng UI sử dụng pattern `switch`.

**Không có quy tắc tuyệt đối “pattern matching tốt hơn OOP”.** Chúng giải quyết các bài toán thiết kế khác nhau.

## 14. Hiệu năng: đừng suy luận từ số lần viết cast

Việc bỏ cast tường minh khỏi mã nguồn không bảo đảm CPU bỏ đi một thao tác runtime tương ứng. `javac` và JIT có thể sinh và tối ưu các phép kiểm tra kiểu, cast và truy cập record theo các cách rất giống nhau.

Với case study này, những yếu tố có thể ảnh hưởng hiệu năng bao gồm:

- Tỉ lệ từng loại shape trong input.
- Branch prediction của CPU và thứ tự nhánh.
- JIT inlining/accessor optimizations.
- Chi phí `Math.PI`, `Math.abs` và `Math.hypot`.
- Tần suất tạo shape mới, allocation và GC.
- Kích thước dữ liệu, cache và thiết kế API.

Vì phép tính chu vi tam giác dùng các phép `Math.hypot` tương đối đáng kể, chênh lệch nếu có giữa cú pháp kiểm tra kiểu có thể chỉ là phần nhỏ.

Muốn kết luận về tốc độ, cần **benchmark có kiểm soát** (ví dụ JMH), kiểm tra ba phương án **tính đúng cùng kết quả**, giữ cùng workload, warm-up và nhiều fork. Bài này **không đưa ra con số ns/op chưa đo**.

Thông thường, nếu benchmark không chứng minh chênh lệch đáng kể, hãy ưu tiên mã dễ hiểu, bảo trì thuận tiện và ít lỗi.

## 15. Lỗi thường gặp khi chuyển từ cast sang pattern

**Lỗi 1 — bỏ kiểm tra kiểu nhưng vẫn cast trực tiếp.** `(Rectangle) value` khi value là Circle sẽ ném `ClassCastException`. Type pattern loại bỏ nhu cầu cast thủ công sau khi khớp.

**Lỗi 2 — nhầm record pattern với constructor.** `Circle(Point(var x,...),var r)` không tạo object mới; nó phân rã một object có sẵn.

**Lỗi 3 — phân rã quá sâu.** Nếu chỉ cần `Point` để tính `Math.hypot`, giữ `var a` tốt hơn bung sáu tọa độ làm nhánh khó đọc.

**Lỗi 4 — dùng `switch` trên `Object` rồi quên xử lý kiểu khác.** Exhaustive chỉ dễ kiểm tra khi tập selector được mô hình hóa bằng kiểu thích hợp, chẳng hạn `sealed Shape`. Với `Object`, phải có fallback phù hợp.

**Lỗi 5 — nhầm `null` trong selector với null trong component.** `obj instanceof Type x` trực tiếp trả false khi selector null, nhưng component record vẫn có thể null; và pattern switch cần xử lý null theo hợp đồng.

**Lỗi 6 — nghĩ `sealed` xác thực dữ liệu hình học.** `sealed` giới hạn subtype, không cấm bán kính âm hay ba đỉnh thẳng hàng. Constructor/factory mới bảo vệ invariant này.

**Lỗi 7 — đưa `default` vào exhaustive switch vô điều kiện.** Nó có thể che việc quên xử lý subtype mới. Với tập variant đóng, để compiler cảnh báo là lợi thế.

**Lỗi 8 — quên chú ý độ chính xác `double`.** Diện tích tam giác gần suy biến, tọa độ quá lớn và phép nhân có thể cho kết quả không như mong đợi. Test số học độc lập với cú pháp pattern.

**Lỗi 9 — thay logic khi refactor.** Nếu bản cũ tính diện tích bằng cross product còn bản mới dùng một công thức thiếu `Math.abs`, kết quả khác không phải lỗi của pattern matching. Cần kiểm thử tương đương.

**Lỗi 10 — ép mọi nghiệp vụ vào một `switch` lớn.** Nếu mỗi shape có hành vi cốt lõi riêng, đa hình có thể rõ hơn. Pattern nên được dùng khi giúp biểu đạt cấu trúc, không chỉ vì nó mới.

## 16. Checklist code review và bài tập

Trước khi chuyển đoạn mã hình học từ cách cũ sang pattern:

1. Có xác định chính xác tập subtype và hợp đồng của `Shape` không?
2. Các công thức diện tích/chu vi đã được kiểm tra độc lập chưa?
3. Phiên bản cast, type pattern và record pattern có cùng hành vi với null, subtype lạ và dữ liệu hợp lệ không?
4. Constructor có từ chối bán kính/kích thước không dương, `NaN`, vô cực và tam giác suy biến theo yêu cầu domain?
5. Có dùng nested record pattern ở đúng mức cần thiết?
6. `switch expression` có exhaustive và không có `default` che thiếu variant không?
7. Nếu mở rộng `Shape`, compiler và test có giúp phát hiện các phép xử lý cần cập nhật không?
8. Có tách các quy tắc số học khó đọc ra helper rõ nghĩa?
9. Đã xét trường hợp null ở selector và component?
10. Có bằng chứng benchmark thực tế trước khi khẳng định cách mới nhanh hơn?

### Bài tập tự luyện

- **Bài 1:** Viết hàm `diameter(Shape shape)` chỉ nhận `Circle`; so sánh cách cũ, type pattern và cách trả về kết quả khi shape không phải Circle.
- **Bài 2:** Chuyển hàm `perimeter` từ pattern `switch` sang chuỗi `if (shape instanceof ...)` rồi đối chiếu kết quả với các test trong bài.
- **Bài 3:** Thêm `Ellipse` vào `permits`, quan sát lỗi compile ở các `switch` chưa exhaustive, cập nhật diện tích và thử một công thức xấp xỉ chu vi có kiểm thử sai số.
- **Bài 4:** Tạo một `Triangle` có tọa độ gần thẳng hàng. Nêu giới hạn của kiểm tra `cross == 0.0` và đề xuất cách thử số học vững hơn.
- **Bài 5:** Thiết kế `translate(Shape s, double dx, double dy)` trả shape đã dịch tọa độ; dùng nested record pattern để giữ đúng dữ liệu, thử cả trường hợp dịch vượt giới hạn tọa độ của domain.
- **Bài 6:** Chuyển `area()` và `perimeter()` sang các method đa hình trong từng subtype rồi so độ dài, độ rõ và khả năng thêm shape/operation so với pattern `switch`.

**Ghi nhớ:** `instanceof` + cast cũ hợp lệ nhưng lặp thao tác chuyển kiểu; type pattern loại bỏ cast tường minh; record pattern cho phép phân rã dữ liệu hình học ngay khi khớp; và pattern `switch` kết hợp `sealed Shape` giúp compiler kiểm tra việc xử lý đủ các loại hình. **Chọn cách viết phù hợp với độ phức tạp của domain, bảo vệ invariant, kiểm tra công thức và ưu tiên tính dễ đọc trước những kết luận hiệu năng chưa được đo.**