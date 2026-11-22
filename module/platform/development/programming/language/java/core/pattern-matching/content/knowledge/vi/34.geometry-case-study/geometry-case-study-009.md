# Kiểm thử toàn bộ hình bằng Pattern Matching trong Java 21

## 1. Mục tiêu của case study

Trong một chương trình hình học, ta thường có nhiều loại hình nhưng muốn cung cấp **một giao diện xử lý thống nhất**: nhận một đối tượng hình, tính diện tích, chu vi, phân loại, phát hiện dữ liệu không hợp lệ và trả kết quả có thể kiểm chứng.

Java 21 hỗ trợ mô hình này bằng **sealed interfaces**, **records**, **record patterns**, **pattern matching for switch** và **guard `when`**. Tuy nhiên, viết được một `switch` đẹp chưa đồng nghĩa đã kiểm thử đầy đủ. Một bộ test đáng tin phải trả lời:

1. **Mỗi loại hình được xử lý chưa?** Có bỏ sót `Circle`, `Rectangle`, `Square` hoặc `Triangle`?
2. **Công thức có đúng không?** Diện tích/chu vi có đúng trên ví dụ đã biết và các quan hệ hình học?
3. **Dữ liệu biên có được định nghĩa không?** Bán kính 0/âm, cạnh âm, tam giác thẳng hàng hoặc trùng đỉnh?
4. **Dữ liệu đặc biệt của `double` được xử lý thế nào?** `NaN`, `Infinity`, tràn số, mất độ chính xác?
5. **`null` ở selector hoặc record lồng nhau có được xử lý không?**
6. **Các pattern có đúng thứ tự và exhaustive không?** Compiler có phát hiện dominated case hoặc thiếu subtype?
7. **Test có chứng minh hành vi quan sát được không?** Kết quả, ngoại lệ, nhánh có guard và các tính chất bất biến?

Bài này xây dựng một **bộ kiểm thử độc lập, chạy bằng JDK 21**, cho bốn loại hình cụ thể. Đây là mô hình ví dụ tự chứa; nếu dự án thực tế có tập hình khác, cần mở rộng cùng nguyên tắc và test theo hợp đồng riêng của từng hình.

**Yêu cầu Java:** `record patterns` (JEP 440) và `pattern matching for switch` (JEP 441) chính thức từ **Java 21**; không cần `--enable-preview`. `sealed` types chuẩn từ Java 17.

## 2. Mô hình miền dữ liệu: bốn loại hình có giới hạn

Đầu tiên khai báo một sealed interface và bốn subtype dạng record:

```java
sealed interface Shape permits Circle, Rectangle, Square, Triangle {}

record Circle(double radius) implements Shape {}
record Rectangle(double width, double height) implements Shape {}
record Square(double side) implements Shape {}
record Point(double x, double y) {}
record Triangle(Point a, Point b, Point c) implements Shape {}
```

Trong bài, các khai báo được đặt bên trong class `GeometryPatternTest` ở chương trình hoàn chỉnh, nên không phải mỗi record là một file riêng.

| Hình | Dữ liệu | Diện tích | Chu vi |
| --- | --- | --- | --- |
| Hình tròn — `Circle` | Bán kính `r` | \(\pi r^2\) | \(2\pi r\) |
| Hình chữ nhật — `Rectangle` | Rộng `w`, cao `h` | \(wh\) | \(2(w+h)\) |
| Hình vuông — `Square` | Cạnh `s` | \(s^2\) | \(4s\) |
| Tam giác — `Triangle` | Ba điểm `A,B,C` trong mặt phẳng | \(\lvert (B-A)\times(C-A)\rvert/2\) | \(\lvert AB\rvert+\lvert BC\rvert+\lvert CA\rvert\) |

**Vì sao `Square` và `Rectangle` là hai record khác nhau?** Đây là một quyết định mô hình hóa để kiểm tra đầy đủ từng nhánh của sealed hierarchy. Các record mặc định là `final`, nên không thể viết `record Square(...) extends Rectangle`. Hai kiểu có thể chia sẻ công thức hoặc helper nhưng không có quan hệ kế thừa record–record trong ví dụ.

**Vì sao dùng `Point` trong `Triangle`?** Để kiểm thử **nested record pattern**, ví dụ:

```java
case Triangle(
        Point(var ax, var ay),
        Point(var bx, var by),
        Point(var cx, var cy)) -> ...
```

Java chỉ vào nhánh này khi selector là `Triangle` và ba component `Point` đều khớp nested record pattern. Nếu một đỉnh bằng `null`, record pattern tại vị trí đó **không match**; cần nhánh `Triangle t` sau đó để xử lý trường hợp thiếu đỉnh.

## 3. Xác định hợp đồng trước khi viết test

Hình học toán học và máy tính có một số khác biệt. Ta cần quy định rõ **input hợp lệ**, **độ chính xác** và **kiểu lỗi** thay vì để test đoán.

### 3.1. Chính sách dữ liệu của bài

- `Circle`: bán kính **hữu hạn và lớn hơn 0**; diện tích/chu vi tính được phải hữu hạn và dương.
- `Rectangle`: chiều rộng/chiều cao **hữu hạn, lớn hơn 0**; diện tích/chu vi phải hữu hạn và dương.
- `Square`: cạnh **hữu hạn, lớn hơn 0**; diện tích/chu vi phải hữu hạn và dương.
- `Triangle`: cả ba đỉnh **khác `null`**, toàn bộ tọa độ là số hữu hạn; diện tích và chu vi tính được đều phải hữu hạn và dương. Tam giác thẳng hàng/trùng đỉnh bị coi là **suy biến**, không hợp lệ.
- Selector `null` trong phương thức tính diện tích/chu vi được xử lý rõ bằng `IllegalArgumentException("null shape")`.
- Dữ liệu hình không hợp lệ gây `IllegalArgumentException("invalid circle")`, `"invalid rectangle"`, `"invalid square"` hoặc `"invalid triangle"` tương ứng.
- Phương thức `classify` chỉ **phân loại runtime type/guard** chứ không xác nhận hình có kích thước hợp lệ; việc validate thuộc `measure`.

Chính sách này là **quy ước của ví dụ**, không phải nguyên tắc bắt buộc cho mọi thư viện hình học. Trong CAD hay đồ họa, đường thẳng, hình có diện tích 0 hoặc "đối tượng chưa hoàn thiện" có thể hợp lệ; khi đó phải thay hợp đồng, chứ không âm thầm đổi expected result.

### 3.2. Dữ liệu không hợp lệ khác thiếu subtype

Đây là phân biệt quan trọng:

- **Exhaustiveness của pattern switch:** compiler có thấy đầy đủ các subtype được phép của `Shape` không?
- **Validation của hình học:** từng đối tượng của một subtype có bán kính, cạnh, tọa độ và kết quả số học đúng hợp đồng không?

Một `switch` xử lý đủ bốn kiểu vẫn có thể trả diện tích `NaN` nếu không kiểm tra dữ liệu. Ngược lại, công thức từng kiểu có thể đúng nhưng `switch` expression không biên dịch vì thiếu subtype.

## 4. Viết bộ xử lý bằng record patterns và switch expression

### 4.1. Hàm kiểm tra số thực

```java
static boolean positiveFinite(double x) {
    return Double.isFinite(x) && x > 0.0;
}
```

Phép kiểm tra này từ chối `Double.NaN`, hai giá trị vô cực, số âm, `0.0` và `-0.0`. Đối với bài này, một kích thước dương nhưng **tính diện tích bị underflow về 0** cũng bị từ chối ở bước kiểm tra kết quả cuối cùng.

Tuyệt đối không dùng riêng `x <= 0` để phát hiện mọi giá trị sai: với `NaN`, phép so sánh `NaN <= 0` là `false`, nên dữ liệu xấu có thể lọt qua nếu không gọi `Double.isFinite`.

### 4.2. Dùng một kiểu kết quả rõ ràng

```java
record Metrics(double area, double perimeter) {}
```

Trả về record `Metrics` giúp test đọc được hai đại lượng theo tên, không nhầm phần tử đầu/second của mảng `double[]`. Bài không yêu cầu mọi object hình chứa sẵn `area` và `perimeter`; chúng là dữ liệu **được tính**.

### 4.3. Guard kết quả phép toán

```java
static Metrics checked(String kind, double area, double perimeter) {
    if (!positiveFinite(area) || !positiveFinite(perimeter)) {
        throw invalid(kind);
    }
    return new Metrics(area, perimeter);
}
```

Đây là bước cực kỳ quan trọng: một kích thước đầu vào có thể là số hữu hạn và dương nhưng phép nhân vẫn vượt phạm vi của `double`. Ví dụ `1e308 * 1e308` thành `Infinity`; chỉ kiểm tra input là chưa đủ.

### 4.4. Pattern switch phân phối tới công thức phù hợp

```java
static Metrics measure(Shape shape) {
    return switch (shape) {
        case Circle(var radius) -> circle(radius);
        case Rectangle(var w, var h) -> rectangle(w, h);
        case Square(var side) -> square(side);
        case Triangle(Point(var ax, var ay),
                      Point(var bx, var by),
                      Point(var cx, var cy)) ->
                triangle(ax, ay, bx, by, cx, cy);
        case Triangle t -> throw invalid("triangle");
        case null -> throw new IllegalArgumentException("null shape");
    };
}
```

Nhờ `sealed Shape`, compiler biết các subtype được phép và kiểm tra tính đầy đủ của switch expression **mà không cần `default`**.

Chú ý thứ tự hai nhánh tam giác:

1. Nested record pattern thử lấy đủ ba `Point`. Nếu match, tính diện tích/chu vi và validate.
2. `case Triangle t` là nhánh còn lại cho `Triangle` không match nested structure, chẳng hạn `a == null`.

Nếu đặt `case Triangle t` lên trên, nhánh nested phía sau bị **dominated** và compiler từ chối. Nếu chỉ viết nested case mà không có fallback `Triangle t`, ta không bảo đảm xử lý được tam giác chứa đỉnh `null`; switch cũng có thể không exhaustive đối với toàn bộ giá trị của `Triangle`.

## 5. Kiểm thử công thức theo từng hình

Mỗi hình cần ít nhất một mẫu có đáp án độc lập, dễ kiểm tra bằng toán học:

| Tên ca | Input | Diện tích kỳ vọng | Chu vi kỳ vọng |
| --- | --- | --- | --- |
| Circle chuẩn | `Circle(1)` | \(\pi\) | \(2\pi\) |
| Rectangle chuẩn | `Rectangle(2,3)` | \(6\) | \(10\) |
| Square chuẩn | `Square(2)` | \(4\) | \(8\) |
| Triangle 3–4–5 | `(0,0),(3,0),(0,4)` | \(6\) | \(12\) |
| Triangle đảo chiều | `(0,4),(3,0),(0,0)` | \(6\) | \(12\) |
| Triangle tịnh tiến | `(10,20),(13,20),(10,24)` | \(6\) | \(12\) |

### 5.1. Tam giác: kiểm tra nhiều đại lượng

Từ ba điểm `A(ax,ay)`, `B(bx,by)`, `C(cx,cy)`:

\[
2S = \left|(b_x-a_x)(c_y-a_y) - (b_y-a_y)(c_x-a_x)\right|.
\]

Với `A(0,0)`, `B(3,0)` và `C(0,4)`, định thức có trị tuyệt đối là `12` nên diện tích là `6`. Các cạnh dài `3,4,5`, nên chu vi là `12`.

Trong Java, dùng `Math.hypot(dx,dy)` cho chiều dài hai chiều thay vì tự viết `Math.sqrt(dx*dx + dy*dy)`. Hàm `Math.hypot` được thiết kế để hạn chế overflow/underflow không cần thiết khi tính căn của tổng bình phương, nhưng **không bảo đảm toàn bộ bài toán tọa độ luôn ổn định số học**.

### 5.2. Không so `double` bằng `==` khi test công thức

Do `Math.PI`, các phép nhân/chia và phép cộng chiều dài là số thực nhị phân, test công thức với **dung sai** thay vì đòi mọi phép tính khác đường đi sinh cùng bit.

Một helper đơn giản dùng trong chương trình:

```java
static void near(String name, double actual, double expected) {
    if (!Double.isFinite(actual) || !Double.isFinite(expected)
            || Math.abs(actual - expected)
                > 1e-10 * Math.max(1.0, Math.abs(expected))) {
        throw new AssertionError(name + ": got " + actual
                + ", expected " + expected);
    }
    assertions++;
}
```

Ở đây dung sai tương đối theo độ lớn kỳ vọng với mức sàn tuyệt đối là `1e-10`. Nó phù hợp với ví dụ số nhỏ ở bài, **không phải quy tắc mặc định an toàn cho mọi mô phỏng khoa học**, nhất là khi kết quả gần 0, cần kiểm soát ULP hoặc có điều kiện sai số chuyên biệt.

Ngoài việc so gần đúng, test kiểm tra `Double.isFinite` để tránh tình trạng `NaN` đi qua phép so sai số theo cách không mong muốn.

## 6. Kiểm thử toàn bộ subtype và nhánh guard

Một sealed hierarchy hỗ trợ kiểm tra exhaustive tại compile time, nhưng **test vẫn cần kiểm tra hành vi của mỗi subtype**:

```java
static String classify(Shape shape) {
    return switch (shape) {
        case Circle(var radius) when radius > 10.0 -> "large-circle";
        case Circle c -> "circle";
        case Rectangle r -> "rectangle";
        case Square s -> "square";
        case Triangle t -> "triangle";
        case null -> "missing";
    };
}
```

Bộ test kiểm tra sáu nhãn/kết quả:

| Input | Output |
| --- | --- |
| `Circle(11)` | `"large-circle"` |
| `Circle(1)` | `"circle"` |
| `Rectangle(1,2)` | `"rectangle"` |
| `Square(2)` | `"square"` |
| `Triangle(...)` | `"triangle"` |
| `null` | `"missing"` |

**Nhánh có guard đặt trước nhánh Circle tổng quát:** Nếu viết `case Circle c` trước `case Circle(var radius) when radius > 10`, nhánh có guard bị dominated. Đây là lỗi compiler, khác với test sai diện tích.

**`classify` không làm validation:** `Circle(-1)` vẫn được phân loại là `"circle"` dù `measure` sẽ từ chối. Phân loại kiểu và chứng minh kích thước hợp lệ là hai trách nhiệm riêng biệt. Không dùng test `classify` để kết luận tính đúng đắn của `measure`.

### 6.1. Vì sao nên có cả compile test và runtime test?

- Compile-time: đảm bảo switch expression được compiler chấp nhận, không thiếu subtype bắt buộc và không có pattern bị dominated.
- Runtime: đảm bảo từng nhánh trả kết quả, ném exception và tính toán theo hợp đồng, kể cả dữ liệu biên.

Việc compiler chấp nhận một switch exhaustive **không xác nhận** rằng `Rectangle(2,3)` sẽ có chu vi 10. Việc test thấy chu vi đúng trên một Rectangle **không xác nhận** rằng Triangle cũng đã được xử lý.

## 7. Các ca không hợp lệ cần kiểm tra

### 7.1. Hình tròn

- `Circle(0)`: bán kính 0 bị từ chối.
- `Circle(Double.NaN)`: từ chối dữ liệu không phải số hữu hạn.
- `Circle(Double.POSITIVE_INFINITY)`: từ chối vô cực.
- Có thể bổ sung `Circle(-1)`, `Circle(-0.0)` và bán kính dương cực lớn gây overflow.
- Bán kính cực nhỏ có thể làm diện tích underflow thành 0 trong `double`; theo chính sách của bài, kết quả không hữu hạn hoặc không dương đều không hợp lệ.

### 7.2. Hình chữ nhật và hình vuông

- `Rectangle(-1,2)`: một chiều âm.
- `Rectangle(1e308,1e308)`: các đầu vào là số hữu hạn dương, nhưng diện tích/chu vi overflow.
- `Square(-0.0)`: dấu âm của zero không biến nó thành kích thước hợp lệ; phép so `>0` trả false.
- `Square(Double.POSITIVE_INFINITY)`: từ chối vô cực.
- Test mở rộng có thể gồm một chiều bằng 0, độ lớn rất nhỏ, `NaN` ở từng chiều.

### 7.3. Tam giác

- **Ba điểm thẳng hàng:** diện tích bằng 0, ví dụ `(0,0),(1,1),(2,2)`.
- **Hai đỉnh trùng nhau:** diện tích bằng 0, ví dụ `(0,0),(0,0),(1,0)`.
- **Một đỉnh null:** nested `Point(...)` không match; `case Triangle t` báo invalid.
- **Tọa độ NaN/vô cực:** từ chối trước khi dùng công thức.
- **Độ lớn cực đại:** ví dụ hai cạnh dùng tọa độ `1e308` có thể làm định thức hoặc tổng độ dài vượt ngưỡng `double`.
- **Tam giác gần thẳng hàng:** cần thêm test sai số số học theo hợp đồng nếu ứng dụng thực sự xử lý loại này.

Một tam giác có ba đỉnh non-null và tọa độ hữu hạn **chưa chắc hợp lệ**. Ví dụ ba điểm thẳng hàng vẫn là một `Triangle` record có thể khởi tạo bình thường; record là carrier dữ liệu, không tự áp đặt tiên đề hình học.

### 7.4. Selector null

Test `measure(null)` phải xác nhận **`IllegalArgumentException("null shape")`**, vì ví dụ cố ý có `case null -> throw ...`. Nếu bỏ nhánh `case null`, behavior thay đổi; không giả định `default` tự xử lý null.

Một API khác có thể chọn `NullPointerException` hoặc Optional/Result; điều quan trọng là **hợp đồng phải rõ**, test phải phản ánh đúng quyết định đó.

## 8. Negative compiler tests: kiểm tra những ví dụ phải bị từ chối

Bộ test runnable chỉ chứa mã hợp lệ. Để dạy quy tắc Java, nên giữ các đoạn **cố ý sai** riêng biệt và xác minh compiler từ chối chúng.

### 8.1. Bỏ sót subtype của sealed Shape

```java
// CỐ Ý SAI: Shape còn có Triangle nhưng switch expression không xử lý.
static String missing(Shape shape) {
    return switch (shape) {
        case Circle c -> "circle";
        case Rectangle r -> "rectangle";
        case Square s -> "square";
    };
}
```

Java 21 báo lỗi tương đương: `the switch expression does not cover all possible input values`. Điều này là bằng chứng của **exhaustiveness check**. Khi thêm `Ellipse` hoặc loại hình mới vào danh sách permitted subtype, biên dịch lại sẽ giúp phát hiện các `switch` expression trước đây chưa xử lý subtype đó, miễn không có nhánh tổng quát đang che trường hợp mới.

### 8.2. Nhánh tổng quát che nhánh cụ thể

```java
// CỐ Ý SAI:
return switch (shape) {
    case Shape any -> "any";
    case Circle c -> "circle"; // dominated
    case null -> "null";
};
```

Mọi `Circle` đều là `Shape`. Nhánh `case Shape any` không guard đứng trước khiến nhánh Circle phía sau không thể được chọn. Compiler Java 21 báo `this case label is dominated by a preceding case label`.

**Sửa:** đặt nhánh cụ thể trước nhánh kiểu cha, hoặc bỏ nhánh không cần thiết. Đừng dùng dấu `->`/`break` để cố sửa dominance: đây là quy tắc bao phủ pattern.

### 8.3. Record pattern sai số component

```java
// CỐ Ý SAI: Circle có một component radius.
case Circle(var radius, var extra) -> "circle";
```

Compiler báo `incorrect number of nested patterns`. Số component pattern phải tương ứng với record header. Nếu record thêm/bớt component, các record pattern liên quan có thể cần sửa ở compile time.

### 8.4. Pattern không phải validator tự động

Đoạn dưới **biên dịch được** nhưng có thể trả `NaN`:

```java
static double unsafeArea(Shape s) {
    return switch (s) {
        case Circle(var r) -> Math.PI * r * r;
        case Rectangle(var w, var h) -> w * h;
        case Square(var a) -> a * a;
        case Triangle t -> 0.0; // Sai nếu là diện tích thực của tam giác!
        case null -> 0.0;
    };
}
```

Đây là ví dụ **logic sai nhưng cú pháp hợp lệ**, không phải negative compilation test. Compiler kiểm tra cấu trúc và kiểu chứ không tự chứng minh công thức hình học. Test behavior phải bắt được lỗi `Triangle t -> 0.0` và các giá trị `NaN`/Infinity.

## 9. Chương trình Java 21 hoàn chỉnh

Tạo file **`GeometryPatternTest.java`**. Đây là chương trình kiểm thử khép kín, chỉ dùng JDK. Nó không có dependency JUnit: các phép kiểm tra dùng `AssertionError` trực tiếp nên chạy cả khi JVM **không bật `-ea`**.

Chương trình gồm: sealed hierarchy bốn hình; tính diện tích/chu vi với kiểm tra số hữu hạn; phân loại bằng guard; 6 ca hình hợp lệ; 6 ca phân loại; 13 ca không hợp lệ; 8 phép kiểm tra tính chất (tổng **39 assertions**).

```java
import java.util.Locale;
import java.util.Objects;

public class GeometryPatternTest {
    sealed interface Shape permits Circle, Rectangle, Square, Triangle {}

    record Circle(double radius) implements Shape {}
    record Rectangle(double width, double height) implements Shape {}
    record Square(double side) implements Shape {}
    record Point(double x, double y) {}
    record Triangle(Point a, Point b, Point c) implements Shape {}
    record Metrics(double area, double perimeter) {}

    static int assertions;

    static boolean positiveFinite(double x) {
        return Double.isFinite(x) && x > 0.0;
    }

    static IllegalArgumentException invalid(String kind) {
        return new IllegalArgumentException("invalid " + kind);
    }

    static Metrics checked(String kind, double area, double perimeter) {
        if (!positiveFinite(area) || !positiveFinite(perimeter)) {
            throw invalid(kind);
        }
        return new Metrics(area, perimeter);
    }

    static Metrics circle(double radius) {
        if (!positiveFinite(radius)) throw invalid("circle");
        return checked("circle", Math.PI * radius * radius,
                2 * Math.PI * radius);
    }

    static Metrics rectangle(double width, double height) {
        if (!positiveFinite(width) || !positiveFinite(height)) {
            throw invalid("rectangle");
        }
        return checked("rectangle", width * height, 2 * (width + height));
    }

    static Metrics square(double side) {
        if (!positiveFinite(side)) throw invalid("square");
        return checked("square", side * side, 4 * side);
    }

    static Metrics triangle(double ax, double ay, double bx, double by,
                            double cx, double cy) {
        if (!Double.isFinite(ax) || !Double.isFinite(ay)
                || !Double.isFinite(bx) || !Double.isFinite(by)
                || !Double.isFinite(cx) || !Double.isFinite(cy)) {
            throw invalid("triangle");
        }
        double twiceArea = Math.abs((bx - ax) * (cy - ay)
                - (by - ay) * (cx - ax));
        double perimeter = Math.hypot(ax - bx, ay - by)
                + Math.hypot(bx - cx, by - cy)
                + Math.hypot(cx - ax, cy - ay);
        return checked("triangle", twiceArea / 2.0, perimeter);
    }

    static Metrics measure(Shape shape) {
        return switch (shape) {
            case Circle(var radius) -> circle(radius);
            case Rectangle(var w, var h) -> rectangle(w, h);
            case Square(var side) -> square(side);
            case Triangle(Point(var ax, var ay),
                          Point(var bx, var by),
                          Point(var cx, var cy)) ->
                    triangle(ax, ay, bx, by, cx, cy);
            case Triangle t -> throw invalid("triangle");
            case null -> throw new IllegalArgumentException("null shape");
        };
    }

    static String classify(Shape shape) {
        return switch (shape) {
            case Circle(var radius) when radius > 10.0 -> "large-circle";
            case Circle c -> "circle";
            case Rectangle r -> "rectangle";
            case Square s -> "square";
            case Triangle t -> "triangle";
            case null -> "missing";
        };
    }

    static void near(String name, double actual, double expected) {
        if (!Double.isFinite(actual) || !Double.isFinite(expected)
                || Math.abs(actual - expected) >
                    1e-10 * Math.max(1.0, Math.abs(expected))) {
            throw new AssertionError(name + ": got " + actual
                    + ", expected " + expected);
        }
        assertions++;
    }

    static void equal(String name, Object actual, Object expected) {
        if (!Objects.equals(actual, expected)) {
            throw new AssertionError(name + ": got " + actual
                    + ", expected " + expected);
        }
        assertions++;
    }

    static Metrics testValid(
            String name, Shape shape, double area, double perimeter) {
        Metrics result = measure(shape);
        near(name + ".area", result.area(), area);
        near(name + ".perimeter", result.perimeter(), perimeter);
        System.out.printf(Locale.ROOT,
                "%s -> area=%.2f, perimeter=%.2f%n",
                name, result.area(), result.perimeter());
        return result;
    }

    static void testInvalid(String name, Shape shape, String message) {
        try {
            measure(shape);
            throw new AssertionError(
                    name + ": expected IllegalArgumentException");
        } catch (IllegalArgumentException ex) {
            equal(name + ".message", ex.getMessage(), message);
            System.out.println(name + " -> " + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        Metrics circle = testValid(
                "circle", new Circle(1), Math.PI, 2 * Math.PI);
        Metrics rectangle = testValid(
                "rectangle", new Rectangle(2, 3), 6, 10);
        Metrics square = testValid(
                "square", new Square(2), 4, 8);
        Triangle abc = new Triangle(
                new Point(0, 0), new Point(3, 0), new Point(0, 4));
        Metrics triangle = testValid("triangle", abc, 6, 12);
        Triangle cba = new Triangle(
                new Point(0, 4), new Point(3, 0), new Point(0, 0));
        Metrics reversed = testValid("reversed", cba, 6, 12);
        Triangle translated = new Triangle(
                new Point(10, 20), new Point(13, 20), new Point(10, 24));
        Metrics shifted = testValid("translated", translated, 6, 12);

        equal("classify-guard", classify(new Circle(11)), "large-circle");
        equal("classify-fallback", classify(new Circle(1)), "circle");
        equal("classify-rectangle",
                classify(new Rectangle(1, 2)), "rectangle");
        equal("classify-square", classify(new Square(2)), "square");
        equal("classify-triangle", classify(abc), "triangle");
        equal("classify-null", classify(null), "missing");
        System.out.println("CLASSIFY PASS: 6");

        testInvalid("circle-zero", new Circle(0), "invalid circle");
        testInvalid("circle-nan",
                new Circle(Double.NaN), "invalid circle");
        testInvalid("circle-infinite",
                new Circle(Double.POSITIVE_INFINITY), "invalid circle");
        testInvalid("rectangle-negative",
                new Rectangle(-1, 2), "invalid rectangle");
        testInvalid("rectangle-overflow",
                new Rectangle(1e308, 1e308), "invalid rectangle");
        testInvalid("square-zero", new Square(-0.0), "invalid square");
        testInvalid("square-infinite",
                new Square(Double.POSITIVE_INFINITY), "invalid square");
        testInvalid("triangle-collinear",
                new Triangle(new Point(0, 0),
                        new Point(1, 1), new Point(2, 2)),
                "invalid triangle");
        testInvalid("triangle-duplicate",
                new Triangle(new Point(0, 0),
                        new Point(0, 0), new Point(1, 0)),
                "invalid triangle");
        testInvalid("triangle-null-vertex",
                new Triangle(null, new Point(1, 0), new Point(0, 1)),
                "invalid triangle");
        testInvalid("triangle-nan",
                new Triangle(new Point(Double.NaN, 0),
                        new Point(1, 0), new Point(0, 1)),
                "invalid triangle");
        testInvalid("triangle-overflow",
                new Triangle(new Point(0, 0),
                        new Point(1e308, 0), new Point(0, 1e308)),
                "invalid triangle");
        testInvalid("null-selector", null, "null shape");
        System.out.println("INVALID CASES PASS: 13");

        near("triangle-winding.area",
                reversed.area(), triangle.area());
        near("triangle-winding.perimeter",
                reversed.perimeter(), triangle.perimeter());
        near("triangle-translation.area",
                shifted.area(), triangle.area());
        near("triangle-translation.perimeter",
                shifted.perimeter(), triangle.perimeter());
        near("square-vs-rectangle.area",
                square.area(), measure(new Rectangle(2, 2)).area());
        near("square-vs-rectangle.perimeter",
                square.perimeter(),
                measure(new Rectangle(2, 2)).perimeter());
        Metrics scaledCircle = measure(new Circle(2));
        near("circle-scale.area",
                scaledCircle.area(), 4 * circle.area());
        near("circle-scale.perimeter",
                scaledCircle.perimeter(), 2 * circle.perimeter());
        System.out.println("PROPERTIES PASS: 8");
        System.out.println("ALL ASSERTIONS PASS: " + assertions);
    }
}
```

### 9.1. Biên dịch và chạy

Trong thư mục chứa file, dùng JDK 21+:

```bash
javac --release 21 GeometryPatternTest.java
java GeometryPatternTest
```

**Kết quả stdout đã kiểm chứng:**

```text
circle -> area=3.14, perimeter=6.28
rectangle -> area=6.00, perimeter=10.00
square -> area=4.00, perimeter=8.00
triangle -> area=6.00, perimeter=12.00
reversed -> area=6.00, perimeter=12.00
translated -> area=6.00, perimeter=12.00
CLASSIFY PASS: 6
circle-zero -> invalid circle
circle-nan -> invalid circle
circle-infinite -> invalid circle
rectangle-negative -> invalid rectangle
rectangle-overflow -> invalid rectangle
square-zero -> invalid square
square-infinite -> invalid square
triangle-collinear -> invalid triangle
triangle-duplicate -> invalid triangle
triangle-null-vertex -> invalid triangle
triangle-nan -> invalid triangle
triangle-overflow -> invalid triangle
null-selector -> null shape
INVALID CASES PASS: 13
PROPERTIES PASS: 8
ALL ASSERTIONS PASS: 39
```

**Không có dòng benchmark.** Chương trình này kiểm tra tính đúng đắn, không đo hiệu năng.

### 9.2. Cách đọc kết quả

- Sáu dòng đầu xác nhận **diện tích và chu vi của cả bốn hình**, thêm hai biến thể tam giác.
- `CLASSIFY PASS: 6` xác nhận các nhánh type patterns, guard và `null` trong phương thức phân loại.
- 13 trường hợp không hợp lệ đều ném **`IllegalArgumentException` với thông điệp chính xác**. Test không chỉ kiểm tra "có exception bất kỳ".
- `PROPERTIES PASS: 8` xác nhận tịnh tiến và đảo chiều đỉnh tam giác giữ nguyên area/perimeter, hình vuông bằng hình chữ nhật có hai cạnh bằng nhau, và scaling của hình tròn.
- Tổng **39 phép khẳng định** được đếm thực tế: \(6\times2+6+13+8=39\).
- Mọi lỗi kiểm tra sẽ ném `AssertionError`. Dòng cuối chỉ được in khi toàn bộ kiểm tra đi đến cuối.

## 10. Property-based và metamorphic testing cho hình học

Một bộ ví dụ cụ thể rất hữu ích, nhưng hình học còn có các **quan hệ bất biến** có thể tạo ra nhiều test mạnh hơn. Đây là phần giúp phát hiện lỗi công thức ngay cả khi ta không có sẵn giá trị diện tích cho mọi hình.

### 10.1. Đổi thứ tự đỉnh tam giác

Với tam giác không suy biến, hoán vị thứ tự ba đỉnh không đổi hình tam giác về mặt hình học, nên **diện tích không đổi**. Chu vi cũng không đổi vì tập ba cạnh như nhau.

Nếu bỏ `Math.abs` trong định thức, đổi chiều `A,B,C` thành `C,B,A` có thể làm diện tích đổi dấu; test `reversed` bắt được lỗi này.

**Không nhầm hướng với diện tích:** Trong bài, diện tích luôn không âm; nếu ứng dụng cần *signed area* để xét clockwise/counterclockwise thì đó là API khác, không nên dùng chung kỳ vọng.

### 10.2. Tịnh tiến

Dịch cả ba đỉnh cùng một vector \((u,v)\) không đổi cạnh hoặc diện tích/chu vi:

\[
S(A+v,B+v,C+v)=S(A,B,C).
\]

Với bộ tọa độ nguyên nhỏ trong bài, việc cộng 10/20 không gây rủi ro đáng kể về sai số. Nhưng với số rất lớn hoặc rất nhỏ, phép tính `double` vẫn có thể mất chính xác; property test thực tế nên sinh input trong khoảng hữu hạn có kiểm soát.

### 10.3. Phóng to hình tròn

Nếu bán kính nhân hệ số \(k>0\), diện tích nhân \(k^2\) và chu vi nhân \(k\). Bài kiểm tra từ `Circle(1)` sang `Circle(2)`:

- `area(2r) ≈ 4 × area(r)`.
- `perimeter(2r) ≈ 2 × perimeter(r)`.

Đây là quan hệ rất hữu ích để bắt lỗi công thức nhầm giữa bán kính, đường kính và bình phương.

### 10.4. Quan hệ giữa hình vuông và hình chữ nhật

`Square(2)` có diện tích/chu vi bằng `Rectangle(2,2)`. Test này giúp kiểm tra consistency giữa **hai nhánh pattern khác nhau** trong sealed hierarchy, dù chúng là hai kiểu record độc lập.

### 10.5. Bổ sung generator có điều kiện

Nếu dùng thư viện property-based testing, có thể sinh dữ liệu:

- Radius/cạnh dương hữu hạn không quá lớn để tránh overflow.
- Tam giác có ba điểm không thẳng hàng.
- Các điểm hoán vị/tịnh tiến theo vector nhỏ.
- Các bộ dữ liệu **cố tình sai**: radius âm, tọa độ vô cực, null vertex, collinear points.

Cần giữ random seed để tái hiện lỗi và lưu một trường hợp tối giản gây regression. Không tạo hoàn toàn ngẫu nhiên rồi chỉ kiểm tra "không ném exception": một công thức sai vẫn có thể trả về số hợp lệ.

## 11. Tích hợp JUnit 5 cho dự án thật

Chương trình mục 9 chạy bằng JDK thuần. Khi dự án đã có JUnit Jupiter, hãy chuyển các test thành test methods/parameterized tests để CI báo rõ test nào thất bại. Mảnh code sau **minh họa**, yêu cầu test dependency và đặt cùng package với class production `GeometryPatternTest`:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class GeometryPatternJUnitTest {
    @Test
    void circleHasCorrectAreaAndPerimeter() {
        var value = GeometryPatternTest.measure(
                new GeometryPatternTest.Circle(1));
        assertEquals(Math.PI, value.area(), 1e-10);
        assertEquals(2 * Math.PI, value.perimeter(), 1e-10);
    }

    @Test
    void nullVertexIsRejected() {
        var invalid = new GeometryPatternTest.Triangle(
                null,
                new GeometryPatternTest.Point(1, 0),
                new GeometryPatternTest.Point(0, 1));
        var ex = assertThrows(IllegalArgumentException.class,
                () -> GeometryPatternTest.measure(invalid));
        assertEquals("invalid triangle", ex.getMessage());
    }

    @Test
    void allPermittedShapesProduceMetrics() {
        GeometryPatternTest.Shape[] shapes = {
            new GeometryPatternTest.Circle(1),
            new GeometryPatternTest.Rectangle(2, 3),
            new GeometryPatternTest.Square(2),
            new GeometryPatternTest.Triangle(
                new GeometryPatternTest.Point(0, 0),
                new GeometryPatternTest.Point(3, 0),
                new GeometryPatternTest.Point(0, 4))
        };
        for (var shape : shapes) {
            var metrics = GeometryPatternTest.measure(shape);
            assertTrue(Double.isFinite(metrics.area()));
            assertTrue(metrics.area() > 0);
            assertTrue(Double.isFinite(metrics.perimeter()));
            assertTrue(metrics.perimeter() > 0);
        }
    }
}
```

**Giới hạn snippet:** Giả định `GeometryPatternTest` và test cùng package, JUnit Jupiter được cấu hình và các record/methods vẫn có mức truy cập phù hợp. Nếu chuyển class production sang package khác, cần mở các API cần test hoặc tổ chức lại package/test fixtures. Đừng đưa JUnit import vào file JDK thuần ở mục 9 khi chưa khai báo dependency.

### 11.1. Parameterized tests

Bốn loại hình và nhiều ca sai được trình bày rất hợp với bảng dữ liệu `@MethodSource`/`@CsvSource`. Những ca chứa record lồng nhau, null và exception nên dùng `@MethodSource` với test cases được đặt tên, không dùng chuỗi CSV khó biểu diễn object phức tạp.

**Ví dụ tổ chức ca:** tạo record `ValidCase(String name, Shape input, double area, double perimeter)` hoặc `InvalidCase(String name, Shape input, String message)` trong test. Dùng cùng một helper để kiểm tra kết quả hoặc exception, tránh copy nhiều assertions thiếu nhất quán.

### 11.2. Test coverage không đồng nghĩa đúng công thức

Một test có thể chạy hết bốn nhánh và đạt 100% branch coverage nhưng không phát hiện lỗi nếu chỉ assert `result != null`. Với mỗi hình, bắt buộc có **oracle độc lập** cho công thức, ngưỡng sai số và những tình huống bác bỏ dữ liệu.

Ngược lại, chỉ test công thức của `Circle` và `Triangle` cũng chưa đảm bảo hai subtype khác đã xử lý; cần kết hợp **behavior coverage** và **exhaustiveness/compiler gate**.

## 12. Độ chính xác số học và các giới hạn của ví dụ

### 12.1. Floating-point không phải hình học chính xác tuyệt đối

Số `double` dùng chuẩn IEEE 754 với tập giá trị hữu hạn. Khi tính định thức tam giác, phép nhân và phép trừ có thể bị làm tròn; hai số gần nhau có thể làm mất chữ số có nghĩa. Với tam giác cực hẹp hoặc tọa độ cỡ `1e308`, kết quả có thể bị overflow hoặc trở về 0 do underflow/cancellation.

Bộ xử lý trong bài chủ động **từ chối kết quả không hữu hạn hoặc không dương**, nhưng vẫn có thể gặp sai số tương đối lớn trong một số tam giác gần suy biến. Vì vậy:

- Không dùng đoạn mã này làm engine hình học chính xác cho CAD/GIS mà không đánh giá thêm.
- Với nghiệp vụ cần robust orientation, xét các thuật toán *adaptive precision* hoặc predicate hình học chính xác được thiết kế riêng.
- Kiểm thử giới hạn vùng tọa độ và sai số được chấp nhận; không đặt một epsilon cố định chung cho mọi kích thước.
- Nếu dùng số tiền hoặc yêu cầu chính xác thập phân, `BigDecimal` có thể phù hợp cho một số phép tính, nhưng xử lý hình học tổng quát (căn bậc hai, góc, định thức) vẫn cần phương pháp và định nghĩa sai số riêng.

### 12.2. Tràn số không chỉ xuất hiện khi input Infinity

`Rectangle(1e308,1e308)` có cả hai chiều **hữu hạn** nhưng diện tích nhân lại không hữu hạn. Test riêng cho output overflow giúp phân biệt lỗi input validation và lỗi số học.

`Math.hypot` có thể xử lý các trường hợp tránh overflow trung gian tốt hơn `Math.sqrt(dx*dx + dy*dy)`, nhưng nếu **khoảng cách toán học thật vượt phạm vi double**, kết quả vẫn có thể là Infinity; vì vậy `checked(...)` phải kiểm tra lại kết quả.

### 12.3. Giá trị âm zero

`-0.0` khác `0.0` ở bit dấu nhưng bằng nhau trong phép so sánh `==`; cả hai đều **không lớn hơn 0**. Bài test `Square(-0.0)` như một trường hợp không hợp lệ. Nếu hệ thống cho phép hình suy biến, hợp đồng phải nêu rõ cách biểu diễn zero/negative zero.

### 12.4. Exception và side effects từ record accessor

Record mặc định có accessor đơn giản, nhưng Java cho phép record khai báo accessor tường minh. Record deconstruction có thể gọi accessor; nếu accessor gây side effect hoặc ném exception, runtime pattern matching có thể có hành vi khác type-only check. Với hình học production có custom records, nên test số lần gọi và exception (có thể liên quan `MatchException` trong quá trình deconstruction) thay vì chỉ so diện tích.

Trong bài, các `record Point/Circle/...` dùng accessor mặc định, không có side effect. Các quan sát ở đây chỉ chứng minh logic trên mô hình này.

## 13. Các lỗi thường gặp khi kiểm thử toàn bộ hình

### Lỗi 1 — Chỉ test một loại hình

Một `Circle(1)` trả đúng \(\pi\) không chứng minh `Rectangle`, `Square` hay `Triangle` đúng. Cần một ma trận bao đủ subtype và nhiều tình huống invalid khác nhau.

### Lỗi 2 — Cho rằng `sealed` tự validate kích thước

`sealed` chỉ giới hạn subtype. Nó không cấm `Circle(-1)` hoặc `Triangle(null,...)`. Validation và domain policy vẫn phải được thiết kế.

### Lỗi 3 — Quên nhánh nested record null

`case Triangle(Point(...),Point(...),Point(...))` không match khi một đỉnh `Point` bằng null. Nếu không có `case Triangle t` phía sau, switch có thể không xử lý đủ các giá trị Triangle theo hợp đồng.

### Lỗi 4 — Đặt pattern rộng trước pattern hẹp

`case Shape any` trước `case Circle c` làm Circle bị dominated. Tương tự, `case Triangle t` trước `case Triangle(Point(...))` che nested pattern. Compiler Java 21 từ chối các trường hợp này.

### Lỗi 5 — So diện tích bằng `==`

`double` có làm tròn; so sánh tuyệt đối bằng `==` có thể khiến test sai hoặc che lỗi khó xác định. Dùng tolerance phù hợp và kiểm tra `NaN`/Infinity.

### Lỗi 6 — Chỉ test positive numbers, bỏ qua overflow

Radius/cạnh dương nhưng quá lớn có thể sinh Infinity. Test output sau phép tính, không chỉ kiểm tra dữ liệu ban đầu.

### Lỗi 7 — Bắt mọi exception rồi coi test pass

Nếu test kỳ vọng `IllegalArgumentException` nhưng code ném `NullPointerException`, đây có thể là bug cần phát hiện. Dùng `assertThrows(IllegalArgumentException.class, ...)` hoặc catch chính xác rồi so message nếu message là một phần hợp đồng.

### Lỗi 8 — Chỉ in stdout mà không assert

Một chương trình in kết quả sai vẫn có exit code 0 nếu không kiểm tra. Dùng assertions thực sự chạy; demo ném `AssertionError` khi expected khác actual.

### Lỗi 9 — Coi tất cả hình đều hợp lệ với chu vi 0

Hợp đồng của bài không cho phép hình suy biến. Nếu ứng dụng cần đoạn thẳng, điểm hoặc tam giác collinear, hãy xây kiểu/hợp đồng riêng thay vì sửa kỳ vọng test trong im lặng.

### Lỗi 10 — Dùng test coverage làm bằng chứng chính xác hình học

Coverage không kiểm tra công thức. Cần test với oracle độc lập và các quan hệ biến đổi hình học.

## 14. Quy trình xây test suite khi thêm hình mới

Giả sử yêu cầu có thêm một `Ellipse` hoặc `Parallelogram`. Không chỉ thêm một nhánh `case` rồi kết luận hoàn tất.

**Quy trình:**

1. Định nghĩa subtype mới và các tham số hình học đủ để tính metric.
2. Cập nhật `permits` của `sealed Shape`.
3. Biên dịch: xem những `switch` expressions đang thiếu subtype. Đây là lợi ích quan trọng của sealed type + exhaustive switch.
4. Xác định hợp đồng input hợp lệ (cạnh, trục, góc, tọa độ, độ chính xác).
5. Thêm công thức có tài liệu chứng minh và unit tests có expected values độc lập.
6. Thêm invalid cases: zero, âm, NaN, Infinity, overflow và các trường hợp suy biến đặc thù.
7. Thêm property/metamorphic tests khi có tính chất bảo toàn.
8. Kiểm tra `null`, dominance và thứ tự guard sau khi sửa switch.
9. Chạy lại bộ test toàn bộ hình và CI trên JDK 21.
10. Nếu cần tối ưu hiệu năng, benchmark riêng; **không thay thế correctness test bằng benchmark**.

**Cảnh báo:** Thay đổi danh sách permitted subtype là thay đổi mô hình API. Với thư viện được phân phối ở nhiều binary version, hãy kiểm tra tương thích khi các module biên dịch lại ở thời điểm khác nhau; exhaustiveness tại compile time không tự giải quyết mọi vấn đề runtime/binary evolution.

## 15. Checklist kiểm thử toàn bộ hình

- [ ] Danh sách permitted subtype của `Shape` được nêu rõ; có test cho mỗi subtype.
- [ ] Với mỗi hình có ít nhất một ví dụ diện tích và chu vi với oracle độc lập.
- [ ] Record pattern lồng nhau đã xử lý cả ba đỉnh có giá trị và đỉnh `null`.
- [ ] `switch` expression exhaustive và không có nhánh dominated.
- [ ] Nhánh có guard đứng trước nhánh tổng quát cùng kiểu.
- [ ] Null selector có behavior/exception tường minh; không coi `default` tự bắt null.
- [ ] Có test bán kính/cạnh/chiều dài âm, 0, `-0.0`, NaN, Infinity.
- [ ] Có test kết quả phép toán overflow, không chỉ kiểm tra input hữu hạn.
- [ ] Có test tam giác thẳng hàng, trùng đỉnh, gần suy biến nếu cần.
- [ ] Có test đảo thứ tự đỉnh, tịnh tiến hoặc các tính chất hình học phù hợp.
- [ ] Dùng so sánh `double` với dung sai phù hợp và xác minh giá trị hữu hạn.
- [ ] Exception test kiểm tra đúng loại lỗi và thông điệp nếu là hợp đồng.
- [ ] Code dùng `javac --release 21`, không phụ thuộc preview.
- [ ] Unit/regression tests chạy tự động, không chỉ xem stdout.
- [ ] Khi thêm subtype mới, biên dịch lại tất cả switch handlers và mở rộng ma trận tests.
- [ ] Những giới hạn của mô hình `double` được ghi rõ cho người dùng API.

**Tiêu chí hoàn tất:** Bộ test phải kiểm tra **đầy đủ các loại hình được phép**, các công thức, dữ liệu hợp lệ/không hợp lệ, các hành vi `null`/guard và các tính chất số học quan trọng. Chương trình có thể biên dịch/chạy được với JDK mục tiêu; các thay đổi hình học mới phải có test chứng minh tính đúng đắn.

## 16. Câu hỏi tự kiểm tra

**1. `sealed Shape` giúp kiểm thử toàn bộ hình như thế nào?**  
Compiler biết các subtype được phép và kiểm tra exhaustiveness của `switch` expression; khi có subtype mới, các switch thiếu nhánh có thể bị báo lỗi khi biên dịch lại.

**2. Compiler có biết `Circle(-1)` là dữ liệu không hợp lệ không?**  
Không. Đây là điều kiện domain, phải validate và test.

**3. Vì sao `case Triangle t` đặt sau nested Triangle case?**  
Vì nó xử lý những Triangle không match cấu trúc lồng nhau, ví dụ một đỉnh null. Nếu đặt lên trước, nested case bị dominated.

**4. `Rectangle(1e308, 1e308)` có hai input hữu hạn. Tại sao vẫn bị từ chối?**  
Vì diện tích/chu vi tính bằng `double` có thể overflow thành Infinity; bài kiểm tra cả kết quả.

**5. Vì sao dùng `Math.hypot` cho độ dài cạnh tam giác?**  
Nó giúp hạn chế overflow/underflow không cần thiết khi tính căn tổng bình phương, nhưng không loại bỏ mọi vấn đề số học.

**6. Vì sao tam giác đảo chiều đỉnh nên có cùng diện tích?**  
Diện tích hình học là trị tuyệt đối của định thức, không phụ thuộc thứ tự hướng của đỉnh.

**7. `Double.NaN > 0` có true không?**  
Không. Để bảo đảm input hợp lệ, kiểm tra `Double.isFinite` cùng dấu và điều kiện kích thước.

**8. Nếu `classify(Circle(-1))` trả `"circle"`, đó có phải bug không?**  
Không theo hợp đồng ví dụ: classify chỉ xác định loại, measure mới xác minh kích thước. Nếu API cần phân loại trạng thái invalid, phải đổi hợp đồng và bổ sung test.

**9. Tại sao `assertEquals(6.0, area)` không luôn là test số học tốt?**  
Vì các phép toán floating point có sai số; nên dùng delta/ULP phù hợp và test `isFinite` khi cần.

**10. Bộ test có output `ALL ASSERTIONS PASS: 39` đã chứng minh mọi tam giác trên Trái Đất đúng chưa?**  
Không. Đây là kết luận trong miền dữ liệu và 39 assertions đã kiểm tra; hình học tính toán còn có vấn đề precision, độ lớn và các cấu trúc chưa được xét.

**11. Nếu thêm `Ellipse` vào `Shape` nhưng quên cập nhật switch expression, điều gì xảy ra?**  
Khi biên dịch lại mã liên quan với sealed hierarchy cập nhật, compiler có thể báo switch không exhaustive; cần thêm nhánh và test công thức.

**12. Tại sao cần cả negative compiler tests và runtime unit tests?**  
Compiler phát hiện những vi phạm ngôn ngữ như dominated case, thiếu subtype, sai record arity; runtime tests phát hiện công thức/ngoại lệ/giá trị không đúng.

## Tài liệu tham khảo

- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409)
- [JEP 395 — Records](https://openjdk.org/jeps/395)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [JLS SE 21 §14.11 — Switch Blocks, exhaustiveness/dominance](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [JLS SE 21 §14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [Java SE 21 API — Double.isFinite](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Double.html#isFinite(double))
- [Java SE 21 API — Math.hypot](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html#hypot(double,double))
- [JUnit 5 User Guide — Assertions and Test Interfaces](https://junit.org/junit5/docs/current/user-guide/)
