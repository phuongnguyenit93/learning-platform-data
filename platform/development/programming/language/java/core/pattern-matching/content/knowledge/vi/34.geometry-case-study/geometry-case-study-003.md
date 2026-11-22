# Tính chu vi bằng pattern switch trong Java 21 — Case study hình học

## 1. Bài toán và mục tiêu

Một ứng dụng hình học có thể nhận nhiều loại hình: hình tròn, hình chữ nhật, tam giác. Mỗi hình có dữ liệu và **công thức chu vi** khác nhau. Nếu dùng kiểu chung `Shape`, ta cần một phương thức `perimeter(Shape shape)` xử lý đúng loại hình lúc chạy, trả về chu vi dưới dạng `double` và báo lỗi khi dữ liệu không hợp lệ.

Với Java 21, **pattern matching for `switch`** cho phép kết hợp phép chọn theo kiểu với **record patterns** để lấy trực tiếp các kích thước. Thay vì liên tiếp `instanceof`, ép kiểu rồi gọi accessor, một `switch expression` có thể diễn đạt trọn vẹn phép ánh xạ “hình → chu vi”.

Bài này hướng dẫn:

- Biểu diễn các hình bằng `record` và một `sealed interface Shape`.
- Áp dụng đúng công thức chu vi hình tròn, hình chữ nhật, trường hợp hình vuông và tam giác.
- Viết `return switch (shape) { ... };` với record patterns `Circle(var r)`, `Rectangle(var w, var h)` và `Triangle(var a, var b, var c)`.
- Hiểu `when`, thứ tự case, null và tính **exhaustive** khi hierarchy được `sealed`.
- Kiểm soát kích thước không hợp lệ: âm, bằng 0, `NaN`, vô cực, tam giác vi phạm bất đẳng thức và kết quả tính bị tràn thành infinity.
- Kiểm thử cả công thức đúng lẫn đường lỗi; định dạng số thực và lựa chọn sai số so sánh phù hợp.

**Mốc phiên bản:** `record` và type pattern cho `instanceof` là tính năng chuẩn từ Java 16; **record patterns** (JEP 440) và **pattern matching for switch** (JEP 441) là tính năng chuẩn ở **Java 21**. Chương trình đầy đủ trong bài dùng `javac --release 21`, **không cần `--enable-preview`**.

## 2. Công thức chu vi và giả định dữ liệu

Chu vi là độ dài đường biên của một hình phẳng. Trong ví dụ, các kích thước dùng chung một **đơn vị độ dài** (chẳng hạn cm), nên kết quả chu vi cũng theo đơn vị đó. Chúng ta không gắn nhãn cm cố định vào kiểu `double` vì API chưa có kiểu thể hiện đơn vị.

| Loại hình | Dữ liệu cần có | Công thức chu vi | Ví dụ |
| --- | --- | --- | --- |
| Hình tròn | Bán kính `r > 0` | `P = 2 × π × r` | `r = 2` → `4π ≈ 12,57` |
| Hình chữ nhật | Rộng `w > 0`, cao `h > 0` | `P = 2 × (w + h)` | `w = 3, h = 4` → `14` |
| Hình vuông | Cạnh `s > 0` | `P = 4 × s` | `s = 5` → `20` |
| Tam giác | Ba cạnh `a, b, c > 0` thỏa bất đẳng thức tam giác | `P = a + b + c` | `a = 3, b = 4, c = 5` → `12` |

Hình vuông là trường hợp đặc biệt của hình chữ nhật khi `width == height`. Trong mô hình chính, **không khai báo một record Square riêng**, mà minh họa cách dùng nhánh `Rectangle` có guard `when w == h` rồi áp dụng `4 * w`. Nhánh Rectangle không guard tiếp theo xử lý mọi hình chữ nhật còn lại.

Trong chương trình ví dụ, các kích thước được coi là **giá trị dương, hữu hạn**; tam giác phải không suy biến. Đây là chính sách dữ liệu của bài, không phải quy tắc bắt buộc cho mọi ứng dụng hình học. Nếu muốn cho phép hình suy biến hoặc đường tròn bán kính 0 trong một ứng dụng khác, cần điều chỉnh rõ hợp đồng và tests.

### 2.1. Bất đẳng thức tam giác

Ba cạnh dương tạo thành một tam giác không suy biến khi **đồng thời**:

```text
a + b > c
a + c > b
b + c > a
```

Ví dụ, `3, 4, 5` hợp lệ. Nhưng `1, 2, 3` không hợp lệ vì `1 + 2 == 3`: ba đoạn chỉ nằm thẳng hàng, không tạo thành tam giác không suy biến. Chỉ kiểm tra ba cạnh dương là **chưa đủ**.

### 2.2. Không trộn chu vi với diện tích

Đây là lỗi thường gặp trong case study hình học:

- Hình tròn: **chu vi** `2πr`, không phải **diện tích** `πr²`.
- Hình chữ nhật: **chu vi** `2(w+h)`, không phải **diện tích** `w × h`.
- Hình tam giác: **chu vi** `a+b+c`; không cần chiều cao hoặc công thức Heron.

Trước khi viết `switch`, hãy chốt công thức ở mức toán học; pattern matching chỉ quyết định **chọn công thức nào**, không tự bảo đảm công thức chính xác.

## 3. Mô hình hóa hình học bằng sealed interface và records

Ta định nghĩa một kiểu cha chung:

```java
sealed interface Shape permits Circle, Rectangle, Triangle {}

record Circle(double radius) implements Shape {}
record Rectangle(double width, double height) implements Shape {}
record Triangle(double a, double b, double c) implements Shape {}
```

Ý nghĩa:

1. `Shape` thể hiện một nhóm hình mà API có thể xử lý.
2. `sealed` và `permits Circle, Rectangle, Triangle` xác định những loại triển khai trực tiếp được cho phép.
3. Mỗi `record` giữ đúng những dữ liệu cần cho công thức chu vi, tự cung cấp accessor như `radius()`, `width()`, `a()`.
4. Các record là final theo đặc tính của record, nên bộ ba này tạo một hệ kiểu đóng rõ ràng để compiler phân tích exhaustiveness.

Định nghĩa trên chỉ minh họa cấu trúc, **chưa có validation**. Chương trình đầy đủ ở mục 7 sẽ thêm compact constructors để chặn kích thước không hợp lệ ngay khi tạo hình.

### Vì sao chọn sealed?

Nếu viết một `switch expression` trên tham số kiểu `Shape` và cung cấp case cho cả ba record, Java 21 có thể kết luận các giá trị `Shape` khác null đều được xử lý, **không cần `default`**.

Nếu sau này mở rộng hierarchy thêm `Polygon` vào `permits` và biên dịch lại, compiler có thể buộc cập nhật các `switch expression` đang thiếu case. Đây là lợi thế đáng kể so với một chuỗi `if/else` có nhánh fallback im lặng.

Nếu `Shape` là interface mở cho vô số implementation, compiler không thể dựa vào danh sách đóng như vậy; khi đó `switch expression` cần được thiết kế có nhánh bao quát phù hợp (ví dụ `default`) hoặc dùng một mô hình phân phối khác.

## 4. Cốt lõi: tính chu vi bằng switch expression và record patterns

Với các record `Shape` đã khai báo, phương thức chính có thể viết như sau:

```java
static double perimeter(Shape shape) {
    return switch (shape) {
        case null -> throw new IllegalArgumentException("shape must not be null");
        case Circle(var r) -> 2.0 * Math.PI * r;
        case Rectangle(var w, var h) when w == h -> 4.0 * w;
        case Rectangle(var w, var h) -> 2.0 * (w + h);
        case Triangle(var a, var b, var c) -> a + b + c;
    };
}
```

Đây là **`switch expression`**, không phải một `switch statement` thông thường. Toàn bộ biểu thức `switch (shape) { ... }` có kiểu kết quả `double`, được trả thẳng bằng `return`. Mỗi nhánh mũi tên `->` cung cấp một biểu thức tính chu vi hoặc ném ngoại lệ.

### 4.1. Record patterns lấy trực tiếp kích thước

- `case Circle(var r)` kiểm tra `shape` có dạng `Circle`, đồng thời ràng buộc `r` từ component `radius`.
- `case Rectangle(var w, var h)` lấy hai component `width` và `height`.
- `case Triangle(var a, var b, var c)` lấy đúng ba component cạnh.

Từ khóa `var` ở đây **không có nghĩa dữ liệu trở thành dynamic type**. Compiler suy luận các biến là `double` từ khai báo record. Các biến pattern chỉ có hiệu lực trong guard và nhánh phù hợp, không tự lan sang case khác.

Record pattern phải có **đúng số vị trí component, đúng thứ tự**. `Rectangle(var w)` không hợp lệ vì Rectangle có hai component. Nếu chỉ dùng một component, Java 21 có thể viết `var ignoredHeight` cho vị trí còn lại; unnamed pattern `_` chỉ trở thành chuẩn từ Java 22.

### 4.2. Tại sao có hai case Rectangle?

```java
case Rectangle(var w, var h) when w == h -> 4.0 * w;
case Rectangle(var w, var h) -> 2.0 * (w + h);
```

Cả hai type pattern đều nhận Rectangle. Nhánh đầu có **guard `when w == h`** để làm rõ tình huống hình vuông. Nếu điều kiện sai, Java tiếp tục xét nhánh Rectangle không guard phía sau.

Ví dụ:

- `Rectangle(5,5)` → guard đúng → `4 × 5 = 20`.
- `Rectangle(3,4)` → guard sai → `2 × (3+4) = 14`.

**Thứ tự quan trọng:** Nhánh Rectangle không guard phải nằm **sau** nhánh có guard. Nếu đặt case Rectangle tổng quát trước, nó bao phủ mọi Rectangle; case có `when` phía sau bị **dominated** và compiler có thể từ chối.

Cần hiểu đây là minh họa cơ chế `when`. Trong ứng dụng thực, `2.0*(w+h)` cũng đúng cho hình vuông; nếu không cần phân biệt hình vuông, một case Rectangle duy nhất **đơn giản hơn và không làm mất tính đúng đắn**.

**Lưu ý so sánh số thực:** `w == h` chỉ phù hợp để minh họa khi hai giá trị được tạo chính xác như `5.0` và `5.0`. Với số đo thực nghiệm có sai số, không nên dùng so sánh chính xác để kết luận hai cạnh bằng nhau. Có thể dùng một quy tắc dung sai được định nghĩa từ yêu cầu nghiệp vụ, hoặc bỏ hoàn toàn nhánh phân biệt hình vuông vì công thức tổng quát đã đúng.

### 4.3. Nhánh null

```java
case null -> throw new IllegalArgumentException("shape must not be null");
```

Đây là quyết định thiết kế API: truyền `null` là lỗi của caller, nên phương thức **ném ngoại lệ có thông báo rõ ràng**. Một API hiển thị có thể chọn trả 0 hay một `OptionalDouble` thay vì ném lỗi; cách nào cũng phải xác định hợp đồng và kiểm thử.

Không mặc định `default` xử lý null. Trong Java 21, một pattern switch thiếu xử lý null thường ném `NullPointerException` khi selector null.

### 4.4. Exhaustiveness trên sealed Shape

Các pattern không guard `Circle(...)`, `Rectangle(...)` và `Triangle(...)` cùng bao phủ toàn bộ hierarchy `Shape` đã được phép. Nhánh Rectangle với `when` chỉ xử lý trường hợp cụ thể; **nhánh Rectangle không guard** mới bảo đảm không bỏ sót các hình chữ nhật có cạnh khác nhau.

Nếu xóa nhánh `Triangle` mà không thêm cách bao phủ khác, `switch expression` không còn exhaustive và compiler báo lỗi. Nếu chỉ giữ nhánh Rectangle `when w==h` mà bỏ nhánh Rectangle tổng quát, các Rectangle không vuông có thể không có case và compiler cũng có thể phát hiện thiếu tính đầy đủ.

## 5. Tại sao cần kiểm tra kích thước trước khi tính?

Một `record Circle(double radius)` không tự cấm `radius=-2` hoặc `Double.NaN`. Một `record Triangle(double a,double b,double c)` cũng không tự đảm bảo bất đẳng thức tam giác. Nếu không kiểm tra, công thức có thể tạo chu vi âm, `NaN` hay infinity, khiến lỗi xuất hiện muộn ở downstream.

Trong Java, compact constructor của record là nơi thích hợp để xác lập invariant:

```java
record Circle(double radius) implements Shape {
    Circle {
        positiveFinite("radius", radius);
        finitePerimeter(2.0 * Math.PI * radius);
    }
}
```

Các phương thức helper trong lớp bao ngoài:

```java
static void positiveFinite(String field, double value) {
    if (!Double.isFinite(value) || value <= 0) {
        throw new IllegalArgumentException(field + " must be positive and finite");
    }
}

static void finitePerimeter(double value) {
    if (!Double.isFinite(value)) {
        throw new IllegalArgumentException("perimeter overflow");
    }
}
```

Hàm `Double.isFinite(value)` loại `NaN`, `Double.POSITIVE_INFINITY` và `Double.NEGATIVE_INFINITY`. Điều kiện `value <= 0` loại 0, -0.0 và số âm theo chính sách bài toán. Sau đó, kiểm tra chu vi để loại kết quả phép tính tràn thành infinity dù từng kích thước ban đầu còn là số hữu hạn.

Với hình chữ nhật:

```java
record Rectangle(double width, double height) implements Shape {
    Rectangle {
        positiveFinite("width", width);
        positiveFinite("height", height);
        finitePerimeter(2.0 * (width + height));
    }
}
```

Với tam giác:

```java
record Triangle(double a, double b, double c) implements Shape {
    Triangle {
        positiveFinite("a", a);
        positiveFinite("b", b);
        positiveFinite("c", c);
        if (!(a + b > c && a + c > b && b + c > a)) {
            throw new IllegalArgumentException("triangle inequality violated");
        }
        finitePerimeter(a + b + c);
    }
}
```

Đây là các **đoạn code cấu thành chương trình đầy đủ ở mục 7**, không phải các file Java tách rời. Phần kiểm tra nằm ở constructor khiến mọi đối tượng hình được tạo qua các constructor này đều được xác thực ngay lúc khởi tạo.

### 5.1. Vì sao vẫn cần kiểm tra kết quả phép tính hữu hạn?

Một `double` dương hữu hạn có thể rất lớn. Ví dụ `Double.MAX_VALUE` là giá trị hữu hạn nhưng `2 * Math.PI * Double.MAX_VALUE` thành infinity do vượt phạm vi `double`. Nếu chỉ xác thực bán kính bằng `Double.isFinite`, chu vi vẫn có thể không hữu hạn.

Ví dụ bài học chặn tình huống này bằng `finitePerimeter(...)`. Khi hệ thống cần xử lý kích thước cực lớn hoặc đòi hỏi độ chính xác khác thường, có thể phải xem lại miền dữ liệu và kiểu số; không nên giả định `double` biểu diễn chính xác mọi độ dài.

### 5.2. Validate trước hay tính rồi báo lỗi?

Hai cách thiết kế thường thấy:

- **Validation trong constructor:** object hợp lệ được đảm bảo tại lúc tạo; phương thức tính chu vi có thể ngắn gọn và tập trung công thức. Đây là cách chương trình đầy đủ sử dụng.
- **Validation trong phương thức perimeter:** tiện khi nhận record không kiểm soát constructor hoặc API legacy, nhưng phải lặp kiểm tra nếu có nhiều phép tính trên cùng hình.

Không nên dùng cả hai một cách không cần thiết. Nếu constructor luôn được dùng đúng cách và dữ liệu record không bị thay đổi sau khi khởi tạo, validation ở constructor là một lựa chọn tự nhiên. Nếu dữ liệu có thể đi qua phản xạ, serialization/framework hoặc tương tác khác, vẫn cần thiết kế kiểm tra tại ranh giới tin cậy phù hợp.

## 6. Đường đi của một hình qua pattern switch

Xét:

```java
Shape shape = new Rectangle(3, 4);
double value = perimeter(shape);
```

Quá trình:

1. Constructor `Rectangle(3,4)` xác thực hai cạnh dương, hữu hạn và chu vi không overflow.
2. `switch (shape)` kiểm tra các pattern theo thứ tự.
3. `case null` không khớp; `Circle(...)` không khớp.
4. `Rectangle(var w,var h)` khớp và lấy `w=3`, `h=4`.
5. Guard `w == h` false, nên Java không chọn nhánh `4*w`.
6. Nhánh `Rectangle(var w,var h)` không guard tiếp theo khớp và trả `2*(3+4)=14`.
7. `return switch(...)` trả về `double` có giá trị `14.0`.

Với `new Triangle(3,4,5)`, nhánh Triangle nhận ba cạnh và trả `12.0`. Với `new Circle(2)`, công thức trả `4π ≈ 12.566370614...`; phần hiển thị có thể làm tròn thành `12.57`.

**Phân biệt tính toán và định dạng:** Hãy giữ kết quả dạng `double` cho các phép tính tiếp theo. Chỉ định dạng hai chữ số thập phân khi xuất cho người đọc; không tự thay chu vi thật bằng chuỗi hay làm tròn sớm nếu hệ thống cần tính tiếp.

## 7. Chương trình Java 21 hoàn chỉnh: tính chu vi và kiểm thử đầu vào

Tạo một tệp duy nhất **`ShapePerimeterDemo.java`**:

```java
public class ShapePerimeterDemo {
    sealed interface Shape permits Circle, Rectangle, Triangle {}

    static void positiveFinite(String field, double value) {
        if (!Double.isFinite(value) || value <= 0) {
            throw new IllegalArgumentException(field + " must be positive and finite");
        }
    }

    static void finitePerimeter(double value) {
        if (!Double.isFinite(value)) {
            throw new IllegalArgumentException("perimeter overflow");
        }
    }

    record Circle(double radius) implements Shape {
        Circle {
            positiveFinite("radius", radius);
            finitePerimeter(2.0 * Math.PI * radius);
        }
    }

    record Rectangle(double width, double height) implements Shape {
        Rectangle {
            positiveFinite("width", width);
            positiveFinite("height", height);
            finitePerimeter(2.0 * (width + height));
        }
    }

    record Triangle(double a, double b, double c) implements Shape {
        Triangle {
            positiveFinite("a", a);
            positiveFinite("b", b);
            positiveFinite("c", c);
            if (!(a + b > c && a + c > b && b + c > a)) {
                throw new IllegalArgumentException("triangle inequality violated");
            }
            finitePerimeter(a + b + c);
        }
    }

    static double perimeter(Shape shape) {
        return switch (shape) {
            case null -> throw new IllegalArgumentException("shape must not be null");
            case Circle(var r) -> 2.0 * Math.PI * r;
            case Rectangle(var w, var h) when w == h -> 4.0 * w;
            case Rectangle(var w, var h) -> 2.0 * (w + h);
            case Triangle(var a, var b, var c) -> a + b + c;
        };
    }

    static int passed;

    static void assertNear(String label, double expected, double actual) {
        if (Math.abs(expected - actual) > 1e-9) {
            throw new AssertionError(
                label + ": expected " + expected + ", got " + actual
            );
        }
        passed++;
        System.out.println(
            "PASS " + label + " = "
            + String.format(java.util.Locale.ROOT, "%.2f", actual)
        );
    }

    static void assertReject(String label, Runnable code, String expectedMessage) {
        try {
            code.run();
            throw new AssertionError(label + ": expected rejection");
        } catch (IllegalArgumentException error) {
            if (!expectedMessage.equals(error.getMessage())) {
                throw new AssertionError(
                    label + ": wrong message " + error.getMessage()
                );
            }
            passed++;
            System.out.println("PASS " + label + " -> " + error.getMessage());
        }
    }

    public static void main(String[] args) {
        assertNear("circle r=2", 4.0 * Math.PI, perimeter(new Circle(2)));
        assertNear("rectangle 3x4", 14.0, perimeter(new Rectangle(3, 4)));
        assertNear("square rectangle 5x5", 20.0, perimeter(new Rectangle(5, 5)));
        assertNear("triangle 3-4-5", 12.0, perimeter(new Triangle(3, 4, 5)));

        assertReject(
            "zero radius", () -> new Circle(0),
            "radius must be positive and finite"
        );
        assertReject(
            "negative width", () -> new Rectangle(-2, 3),
            "width must be positive and finite"
        );
        assertReject(
            "invalid triangle", () -> new Triangle(1, 2, 3),
            "triangle inequality violated"
        );
        assertReject(
            "NaN radius", () -> new Circle(Double.NaN),
            "radius must be positive and finite"
        );
        assertReject(
            "overflow", () -> new Circle(Double.MAX_VALUE),
            "perimeter overflow"
        );
        assertReject(
            "null shape", () -> perimeter(null),
            "shape must not be null"
        );

        System.out.println("checks=" + passed);
    }
}
```

Biên dịch và chạy với JDK 21 trở lên:

```bash
javac --release 21 ShapePerimeterDemo.java
java ShapePerimeterDemo
```

**Đầu ra chính xác** (dấu thập phân được cố định bằng `Locale.ROOT`):

```text
PASS circle r=2 = 12.57
PASS rectangle 3x4 = 14.00
PASS square rectangle 5x5 = 20.00
PASS triangle 3-4-5 = 12.00
PASS zero radius -> radius must be positive and finite
PASS negative width -> width must be positive and finite
PASS invalid triangle -> triangle inequality violated
PASS NaN radius -> radius must be positive and finite
PASS overflow -> perimeter overflow
PASS null shape -> shape must not be null
checks=10
```

Đây là một chương trình tự kiểm tra **không cần JUnit hoặc dependency bên ngoài**. Helper `assertNear` ném `AssertionError` khi độ lệch vượt `1e-9` trong các ví dụ có kích thước nhỏ; chỉ in `PASS` khi công thức đúng theo kết quả dự kiến. Helper `assertReject` xác nhận một phép tạo hình hoặc lời gọi `perimeter` thực sự ném `IllegalArgumentException` với thông báo mong đợi.

**10 checks** gồm bốn ca tính chu vi và sáu ca lỗi: bán kính 0, rộng âm, tam giác suy biến, bán kính NaN, kết quả overflow và selector null. Dòng `checks=10` không khẳng định toàn bộ miền `double` hay tất cả hình học đã được kiểm thử; nó xác nhận những ca cụ thể mà chương trình định nghĩa.

### 7.1. Giải thích 4 ca chu vi thành công

- `Circle(2)`: `2π × 2 = 4π ≈ 12.566...` → hiển thị `12.57`.
- `Rectangle(3,4)`: `2(3+4) = 14` → `14.00`.
- `Rectangle(5,5)`: guard `w==h` true, `4 × 5 = 20` → `20.00`.
- `Triangle(3,4,5)`: hợp lệ vì cả ba tổng hai cạnh đều lớn hơn cạnh còn lại, `3+4+5=12` → `12.00`.

### 7.2. Giải thích 6 ca đầu vào không hợp lệ

- `Circle(0)` không được tạo thành công; compact constructor bác bỏ 0 theo chính sách bán kính dương.
- `Rectangle(-2,3)` bị từ chối do cạnh rộng âm.
- `Triangle(1,2,3)` bị từ chối vì `1+2 == 3`, không thỏa `>`.
- `Circle(Double.NaN)` bị từ chối qua `Double.isFinite`.
- `Circle(Double.MAX_VALUE)` có bán kính hữu hạn nhưng kết quả `2πr` vượt miền `double`, nên bị từ chối vì overflow.
- `perimeter(null)` vào `case null` rồi ném lỗi theo hợp đồng. Nó **không** được hiểu như một hình chu vi 0.

Việc xác thực kích thước nằm trong constructor còn việc xử lý `null shape` nằm trong `switch`, vì `null` không phải một record instance có constructor để kiểm tra.

## 8. So sánh pattern switch với instanceof và virtual dispatch

### 8.1. Cách cũ dùng instanceof

Nếu không dùng record patterns trong switch, có thể viết:

```java
// Snippet nằm trong class cùng Shape/Circle/Rectangle/Triangle.
static double perimeterWithIf(Shape shape) {
    if (shape == null) throw new IllegalArgumentException("shape must not be null");
    if (shape instanceof Circle circle) {
        return 2.0 * Math.PI * circle.radius();
    }
    if (shape instanceof Rectangle rectangle) {
        return 2.0 * (rectangle.width() + rectangle.height());
    }
    if (shape instanceof Triangle triangle) {
        return triangle.a() + triangle.b() + triangle.c();
    }
    throw new IllegalStateException("Unknown shape");
}
```

Cách này có thể đúng và thậm chí phù hợp với code yêu cầu Java 17. Nó dùng type patterns cho `instanceof` và accessor, không dùng deconstruction patterns. Nhược điểm: nhánh cuối cần fallback bằng tay, và compiler không chứng minh rõ tính exhaustive của chuỗi `if` khi hierarchy thay đổi.

Bản `switch expression` Java 21 liệt kê tập hình trên cùng mặt phẳng và được compiler kiểm tra exhaustiveness nhờ sealed hierarchy.

### 8.2. Virtual dispatch có phải luôn kém hơn không?

Không. Thiết kế đối tượng truyền thống cũng có thể khai báo `double perimeter()` trong `Shape` rồi để mỗi record tính bằng implementation riêng. Đó là **polymorphism**, thích hợp khi tính chu vi là hành vi cốt lõi của từng hình và hệ kiểu thường được mở rộng bằng các lớp mới.

Pattern `switch` đặc biệt tiện khi có **một phép phân loại/biến đổi dựa trên tập subtype đóng**, hoặc muốn xử lý dữ liệu record trong một lớp dịch vụ độc lập với mô hình. Nếu ứng dụng thêm nhiều phép toán như diện tích, chu vi, serialize và render, hãy cân nhắc trách nhiệm và kiến trúc: đừng vội tạo hàng loạt switch khổng lồ lặp trên cùng hierarchy.

Chọn pattern switch để tăng tính rõ ràng và exhaustiveness, **không phải vì luôn nhanh hơn** virtual dispatch hoặc `if`. Nếu hiệu năng quan trọng, cần đo với workload thật.

## 9. `when`, `yield` và những biến thể switch

Trong chương trình chính, mỗi case là một biểu thức ngắn nên không cần `yield`. Nếu một case cần nhiều câu lệnh để tính trung gian, Java 21 cho phép block với `yield`:

```java
// Snippet thay cho nhánh Triangle trong một switch expression:
case Triangle(var a, var b, var c) -> {
    double sum = a + b + c;
    yield sum;
}
```

`yield` trả **giá trị cho switch expression**, còn `return` trả về từ **phương thức**. Không dùng `return sum;` để thay `yield sum;` bên trong block của switch expression. Với các case chỉ có một biểu thức, dạng `-> expression` dễ đọc hơn.

Guard `when` thuộc về **case label**, không phải một `if` chạy bên ngoài:

```java
case Rectangle(var w, var h) when w == h -> 4.0 * w;
case Rectangle(var w, var h) -> 2.0 * (w + h);
```

Nếu guard false, nhánh Rectangle tổng quát phía sau vẫn có cơ hội được chọn. Vì vậy **bản phân tích nhánh** cần test cả hai: hình vuông và hình chữ nhật không vuông.

### Khi nào nên dùng default?

Với `Shape` sealed gồm ba records và đã xử lý tất cả, không cần default. Nếu thêm:

```java
default -> throw new IllegalArgumentException("unknown shape");
```

thì compiler không còn buộc bạn xử lý một subtype mới khi hierarchy thay đổi, vì default có thể bao phủ nó. Nếu mục tiêu chính là **exhaustiveness compile-time**, giữ các case tường minh và bỏ default khi hệ kiểu cho phép.

Ngược lại, nếu đầu vào là `Object` đến từ dữ liệu bên ngoài, không chỉ giới hạn trong sealed `Shape`, thì cần quyết định fallback thích hợp cho các kiểu ngoài Shape. Không thể tự áp dụng cách bỏ default của selector Shape cho selector Object.

## 10. Sai số double và cách kiểm thử chu vi

### 10.1. Math.PI là xấp xỉ số thực

Java cung cấp `Math.PI` dưới dạng một hằng double gần đúng với π. Do đó `perimeter(new Circle(2))` là một `double` gần `12.566370614...`, không phải số vô hạn chữ số chính xác tuyệt đối.

Khi hiển thị:

```java
System.out.println(
    String.format(java.util.Locale.ROOT, "%.2f", 4.0 * Math.PI)
);
```

kết quả là `12.57`. Chọn `Locale.ROOT` trong ví dụ giúp dấu thập phân và định dạng dễ đối chiếu giữa môi trường khác nhau; cấu hình hiển thị cho người dùng thực tế có thể cần locale theo người dùng.

### 10.2. Không nên so double bằng == khi test phép toán xấp xỉ

Với phép tính có π hoặc nhiều phép cộng trừ số thực, một bộ test có thể dùng sai số cho phép:

```java
double actual = perimeter(new Circle(2));
double expected = 4.0 * Math.PI;

if (Math.abs(expected - actual) > 1e-9) {
    throw new AssertionError("perimeter mismatch");
}
```

Đoạn này minh họa test với giá trị cỡ nhỏ. Một dung sai tuyệt đối cố định `1e-9` **không phù hợp cho mọi thang đo**. Với giá trị lớn hoặc nhiều phép tính, có thể kết hợp sai số tuyệt đối và tương đối theo hợp đồng miền dữ liệu:

```java
// Snippet minh họa với hai kết quả double hữu hạn.
double tolerance = Math.max(1e-9, Math.abs(expected) * 1e-12);
if (Math.abs(actual - expected) > tolerance) {
    throw new AssertionError("perimeter mismatch");
}
```

Nếu có khả năng actual/expected là `NaN` hoặc vô cực, hãy kiểm tra `Double.isFinite` riêng; phép so sánh dựa trên `Math.abs` không tự phát hiện mọi tình huống NaN. Chương trình chính đặt validation trong các constructor để chặn các kích thước hoặc chu vi phi hữu hạn.

### 10.3. Giữ nguyên đơn vị

Nếu bán kính nhập bằng cm còn cạnh hình chữ nhật nhập bằng m, không thể so chu vi trực tiếp mà không đổi về cùng đơn vị. Kiểu `double` tự nó **không chứa thông tin đơn vị**. Trong hệ thống lớn, có thể tạo value object biểu diễn chiều dài/đơn vị và chuyển đổi ở ranh giới API.

Không nhầm công thức chu vi `2πr` với `πr²` khi test. Việc kiểm thử một kết quả như `12.57` cho r=2 giúp bắt nhầm công thức, nhưng vẫn cần ca có kích thước khác để tránh trùng hợp ngẫu nhiên.

## 11. Các lỗi thường gặp trong case study

| Lỗi | Hậu quả | Cách sửa/kiểm thử |
| --- | --- | --- |
| Dùng `Math.PI * r * r` để tính chu vi | Tính diện tích hình tròn. | Dùng `2 * Math.PI * r`; test `r=2`. |
| Dùng `w * h` cho hình chữ nhật | Tính diện tích thay vì chu vi. | Dùng `2 * (w+h)`; test `3×4 → 14`. |
| Dùng `a+b+c` khi không kiểm tra tam giác hợp lệ | Chấp nhận `1,2,3` như tam giác không suy biến. | Kiểm tra cả ba cạnh dương và bất đẳng thức tam giác. |
| Chỉ kiểm tra kích thước `>0` mà không xét `NaN` | Với NaN, các so sánh thứ tự có thể không phát hiện giá trị không hợp lệ. | Dùng `Double.isFinite(value)` cùng điều kiện dương. |
| Chỉ kiểm tra đầu vào hữu hạn, bỏ qua overflow kết quả | Chu vi có thể thành infinity. | Xác thực `Double.isFinite(perimeter)` trong miền cần hỗ trợ. |
| Đặt Rectangle tổng quát trước Rectangle có `when` | Case có guard bị bao phủ, lỗi compile-time. | Đặt case đặc thù trước case bao quát. |
| Chỉ có `case Rectangle(...) when w==h` | Bỏ sót hình chữ nhật không vuông, có thể non-exhaustive. | Thêm nhánh Rectangle không guard. |
| Bỏ `Triangle` mà không có cách bao phủ | Switch expression trên sealed Shape không đầy đủ. | Xử lý mọi subtype. |
| Thêm `default` để che thiếu subtype | Bỏ qua khả năng compiler nhắc xử lý khi thêm hình mới. | Với hierarchy đóng, ưu tiên case tường minh. |
| Không xử lý null selector theo hợp đồng | Có thể phát sinh NPE khó diễn giải. | `case null` với lỗi hoặc kết quả chủ đích, và test. |
| Dùng `w == h` để suy luận từ dữ liệu đo đạc có sai số | Phân loại sai hình vuông gần đúng. | Dùng công thức Rectangle chung hoặc quy tắc dung sai rõ ràng. |
| Dùng `return` thay `yield` trong block của switch expression | Sai mô hình trả giá trị của biểu thức switch. | Dùng `yield` cho block nhiều lệnh, expression cho case ngắn. |
| Test bằng chuỗi đã làm tròn thay vì giá trị số | Che sai số hoặc thất bại do locale không mong muốn. | Assert kết quả double với tolerance, chỉ format ở lớp hiển thị. |
| Dùng Java 17 để biên dịch record pattern chuẩn Java 21 | Compiler không hỗ trợ deconstruction pattern ở source 17. | Dùng JDK/source 21 hoặc type pattern + accessor. |

## 12. Bài tập thực hành: mở rộng case study

### Bài A — Tự thêm hình vuông thành một subtype

Giả sử ứng dụng muốn biểu diễn `Square` là một loại hình riêng, không chỉ là `Rectangle` có hai cạnh bằng nhau.

Yêu cầu:

1. Thêm `record Square(double side) implements Shape` và kiểm tra cạnh dương hữu hạn, kết quả `4*side` hữu hạn.
2. Bổ sung `Square` vào danh sách `permits` của `Shape`.
3. Thêm `case Square(var side) -> 4.0*side;` vào `switch expression` tính chu vi.
4. Test `Square(5) -> 20.0` và `Square(0)` bị từ chối.

Gợi ý code cấu phần (không phải tệp độc lập; cần thay đổi sealed interface và switch của ví dụ chính):

```java
record Square(double side) implements Shape {
    Square {
        positiveFinite("side", side);
        finitePerimeter(4.0 * side);
    }
}

// Trong switch expression tính chu vi:
case Square(var side) -> 4.0 * side;
```

**Vì sao phải sửa cả `permits`?** Sealed interface chỉ cho phép các implementation đã khai báo. Việc thêm subtype khiến compiler cần biết phạm vi mới, và switch exhaustive có thể yêu cầu cập nhật theo subtype mới. Đó là một ưu điểm của mô hình đóng.

### Bài B — Tính chu vi tam giác đều bằng case có guard

Một ứng dụng muốn phân biệt tam giác đều trong logic hiển thị. Đặt:

```java
case Triangle(var a, var b, var c) when a == b && b == c -> 3.0 * a;
case Triangle(var a, var b, var c) -> a + b + c;
```

Các case này là snippet thay thế cho case Triangle trong switch expression hiện có, không phải hai lệnh độc lập. Với tam giác đều có cạnh bằng đúng nhau trong dữ liệu, hai công thức đồng nghĩa. Tuy nhiên, như với hình vuông, so sánh bằng tuyệt đối không nên dùng để phân loại số đo thực nghiệm có sai số mà không có hợp đồng về dung sai.

Test:

- `Triangle(3,3,3)` → `9.0`, guard đúng.
- `Triangle(3,4,5)` → `12.0`, guard sai nhưng case tổng quát khớp.
- `Triangle(1,2,3)` → constructor từ chối; không thể kiểm thử chu vi của object không được tạo thành công bằng API này.

### Bài C — Không lẫn chu vi với diện tích

Viết thêm phương thức `area(Shape shape)`, dùng các công thức riêng:
- Circle: `πr²`.
- Rectangle: `w×h`.
- Triangle: công thức Heron với nửa chu vi `s=(a+b+c)/2`.

**Lưu ý:** đây là bài tập mở rộng, khác mục tiêu **tính chu vi**. Công thức Heron khi áp dụng với số thực và hình rất dẹt có các vấn đề ổn định số cần xem xét thêm. Không dùng phương thức `area` thay thế cho `perimeter` và không đưa công thức diện tích vào các case tính chu vi.

## 13. Checklist thiết kế và review

Khi hoàn thiện một API tính chu vi dựa trên pattern switch:

1. Xác nhận các loại hình và **công thức chu vi**, thống nhất đơn vị.
2. Dùng `record` để giữ các kích thước và cân nhắc `sealed Shape` nếu tập loại hình đóng.
3. Đặt validation cho cạnh/bán kính ngay tại ranh giới tạo object hoặc phương thức nhận dữ liệu, không tin rằng record tự chặn kích thước âm/NaN.
4. Viết `switch expression` trả `double` với record patterns đủ component.
5. Nếu dùng `when`, đặt case có guard trước case cùng type không guard, bảo đảm bao phủ cả hai đường true/false.
6. Với sealed hierarchy đã có đủ case, không thêm `default` vô điều kiện nếu muốn compiler báo thiếu subtype mới.
7. Quyết định rõ hành vi khi `shape == null`; test đúng ngoại lệ hoặc kết quả theo hợp đồng.
8. Kiểm tra overflow và đặc tính số thực của `double`; chỉ format ở lớp hiển thị.
9. Có tests cho hình tròn, chữ nhật không vuông, hình vuông, tam giác hợp lệ, các giá trị biên và kích thước không hợp lệ.
10. Biên dịch bằng Java 21 cho record patterns chuẩn, chạy tests trên runtime phù hợp và review hành vi khi thêm subtype.

**Ghi nhớ:** Pattern `switch` giúp biến **hệ kiểu Shape** thành một phép ánh xạ **từng loại hình → công thức chu vi** rõ ràng, dễ kiểm tra exhaustiveness. Nhưng tính đúng đắn hình học vẫn phụ thuộc vào **công thức**, **bất biến dữ liệu**, **đơn vị**, **giới hạn số thực** và **kiểm thử trường hợp lỗi**. Một thiết kế tốt tận dụng sức mạnh của compiler mà không đánh đồng “code biên dịch được” với “chu vi luôn đúng”.

**Tài liệu tham khảo:**
- [JEP 440 — Record Patterns (Java 21)](https://openjdk.org/jeps/440).
- [JEP 441 — Pattern Matching for switch (Java 21)](https://openjdk.org/jeps/441).
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [Java SE 21 Language Specification — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30).
- [Java SE 21 Math API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html).
