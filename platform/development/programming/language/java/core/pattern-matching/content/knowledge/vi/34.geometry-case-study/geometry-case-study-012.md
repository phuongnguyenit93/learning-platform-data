# Tổng kết lựa chọn thiết kế — Case study hình học với Java Pattern Matching

Khi mô hình hóa **hình học phẳng** trong Java, cùng một bài toán “tính diện tích và chu vi của nhiều loại hình” có thể được giải theo nhiều cách: **đa hình hướng đối tượng** (mỗi hình tự cung cấp hành vi), **`sealed interface` + `record` + pattern matching `switch`** (dữ liệu tách khỏi các phép toán), hoặc chuỗi `instanceof` cho trường hợp nhỏ. Không có một cách duy nhất luôn tốt nhất.

Bài này thuộc **Java Core Pattern Matching → Case study hình học**, là phần **tổng kết lựa chọn thiết kế**. Ta sẽ dùng cùng miền dữ liệu **hình tròn, hình chữ nhật và tam giác vuông** để đánh giá độ rõ ràng, tính an toàn kiểu, khả năng mở rộng, độ bao phủ của `switch`, quy tắc kiểm tra dữ liệu và nhu cầu bảo trì. Cuối bài có **hai chương trình Java độc lập đã chạy kiểm chứng**, một bảng quyết định và bài tập thực hành.

**Mốc phiên bản:** `record` ổn định từ Java 16 (JEP 395), `sealed` từ Java 17 (JEP 409), còn **record patterns** và **pattern matching for `switch`** hoàn thiện trong Java 21 (JEP 440, JEP 441). Chương trình so sánh theo phong cách Java 21+ **không cần `--enable-preview`**.

## 1. Bắt đầu từ yêu cầu, không bắt đầu từ cú pháp

Giả sử một module hình học cần:

- Mô tả ba dạng hình phẳng: **`Circle`** bằng bán kính `r`; **`Rectangle`** bằng chiều rộng `w`, chiều cao `h`; **`RightTriangle`** bằng hai cạnh góc vuông `a`, `b`.
- Tính `area` và `perimeter`, trả về `double`.
- Phân loại ngắn gọn để hiển thị: đường tròn lớn, hình chữ nhật vuông/có chiều ngang lớn/có chiều dọc lớn, tam giác vuông.
- Không cho tạo hình có kích thước âm, bằng 0, `NaN` hoặc `Infinity`.
- Có thể bổ sung một **phép toán mới** trong tương lai, hoặc bổ sung một **loại hình mới**.
- Có quy tắc tường minh khi đối tượng đầu vào bằng `null`.

Với hệ đơn giản, công thức là:

| Loại hình | Dữ liệu cần giữ | Diện tích | Chu vi |
| --- | --- | --- | --- |
| Hình tròn | Bán kính `r > 0` | \(\pi r^2\) | \(2\pi r\) |
| Hình chữ nhật | Rộng `w > 0`, cao `h > 0` | \(w h\) | \(2(w+h)\) |
| Tam giác vuông | Hai cạnh góc vuông `a > 0`, `b > 0` | \(ab/2\) | \(a+b+\sqrt{a^2+b^2}\) |

Trong Java, nên tính cạnh huyền bằng **`Math.hypot(a, b)`** thay vì tự viết `Math.sqrt(a*a + b*b)`, vì `hypot` được thiết kế để tính độ dài này với cách xử lý số thực đáng tin cậy hơn khi giá trị rất lớn/nhỏ.

**Giới hạn mô hình:** `RightTriangle` ở đây mô tả **tam giác vuông bằng độ dài hai cạnh góc vuông**, không phải mọi tam giác theo ba đỉnh tọa độ. `Rectangle` là hình chữ nhật không cần lưu góc quay; muốn hỗ trợ hình có vị trí, phép quay hoặc hình đa giác bất kỳ thì domain model phải được mở rộng phù hợp.

Vấn đề thiết kế quan trọng hơn việc có viết được `case Circle(var r)` hay không là: **hệ thống biến động theo hướng thêm hình mới hay thêm thao tác trên các hình hiện có?**

## 2. Hai hướng thiết kế chính

### A. Đa hình hướng đối tượng: hành vi nằm trên từng hình

Ta khai báo một interface `Shape` với các phương thức chung:

~~~java
// Trích đoạn Java, không phải chương trình độc lập.
interface Shape {
    double area();
    double perimeter();
}
~~~

Sau đó mỗi hình triển khai công thức tương ứng. Client chỉ gọi `shape.area()`, không biết hình là `Circle` hay `Rectangle`. Java chọn implementation bằng **dynamic dispatch**.

Ưu điểm:

- Mỗi class/record tự sở hữu các quy tắc tính toán thuộc loại hình của nó.
- Client chỉ phụ thuộc vào hợp đồng chung, không cần `switch` khi gọi `area()`.
- Với một **interface mở** và các phương thức chung tương đối ổn định, thêm một kiểu hình mới có thể được thực hiện bằng cách triển khai interface mà không phải sửa các lời gọi `shape.area()` hiện hữu.
- Gần gũi với lập trình hướng đối tượng truyền thống; thích hợp khi hình và hành vi đi cùng nhau.

Điểm đánh đổi:

- Thêm **phép toán bắt buộc mới** vào interface có thể yêu cầu cập nhật mọi implementation; cần cân nhắc binary/source compatibility của API.
- Nếu một thao tác thuộc tầng báo cáo, UI, xuất file, kiểm thử hoặc phân tích chuyên biệt, đặt nó lên interface `Shape` có thể làm phình bề mặt API và trộn trách nhiệm.
- Đa hình không tự xác nhận mọi hình dùng chung một công thức đúng; vẫn cần unit tests.

### B. `sealed` + `record` + exhaustive `switch`: dữ liệu và phép toán tách nhau

Ta định nghĩa tập biến thể hình học được phép:

~~~java
// Trích đoạn Java 21+, có thể đặt cùng một phạm vi/module phù hợp.
sealed interface Shape permits Circle, Rectangle, RightTriangle {}

record Circle(double radius) implements Shape {}
record Rectangle(double width, double height) implements Shape {}
record RightTriangle(double legA, double legB) implements Shape {}
~~~

Và một phép toán `area` ở ngoài record:

~~~java
// Trích đoạn Java 21+; shape có kiểu Shape, non-null.
return switch (shape) {
    case Circle(var r) -> Math.PI * r * r;
    case Rectangle(var w, var h) -> w * h;
    case RightTriangle(var a, var b) -> a * b / 2.0;
};
~~~

Ưu điểm:

- `record` tập trung biểu diễn **dữ liệu hình học** và các invariant khi cần.
- `switch expression` tập trung các quy tắc của **một phép toán** vào cùng một nơi: xem toàn bộ công thức diện tích rất nhanh.
- Có thể thêm một phép toán như tính chu vi, diện tích phần tô màu, tạo mô tả hoặc xuất thông tin mà **không phải thêm phương thức vào từng kiểu dữ liệu**.
- Với một **sealed hierarchy đóng** và các case bao phủ hết các biến thể, compiler kiểm tra tính **exhaustive**; khi bổ sung một kiểu được phép mới và biên dịch lại, các `switch` còn thiếu case sẽ được chỉ ra.

Điểm đánh đổi:

- Khi thêm một **loại hình mới**, phải cập nhật tập `permits` và **mọi phép toán dạng `switch` exhaustive có liên quan**. Đây vừa là chi phí thay đổi, vừa là lợi ích nếu muốn compiler bắt buộc xem xét từng phép toán.
- `sealed` giới hạn kiểu triển khai trực tiếp theo quy tắc ngôn ngữ/module, nên không phù hợp nguyên trạng nếu yêu cầu các plugin ngoài hệ thống tự thêm subtype bất kỳ.
- Nếu mỗi phép toán `switch` trở nên dài hoặc đầy side effect, có thể cần tách sang strategy/service hay một thiết kế hướng hành vi khác.

**Không nên mặc định** mọi domain object là `record` hay mọi xử lý phải dùng `switch`. Chọn theo tính ổn định của tập loại hình và hướng phát triển của nghiệp vụ.

## 3. Chương trình 1: hình học bằng đa hình

Ví dụ nhỏ, độc lập, tập trung vào **dynamic dispatch**. Nó chỉ gồm hai loại hình để tránh lặp lại nhiều code khi đang giải thích nguyên tắc.

Tạo tệp **`PolymorphicGeometryDemo.java`**:

~~~java
public class PolymorphicGeometryDemo {
    interface Shape {
        double area();
        double perimeter();
    }

    record Circle(double radius) implements Shape {
        public double area() {
            return Math.PI * radius * radius;
        }
        public double perimeter() {
            return 2 * Math.PI * radius;
        }
    }

    record Rectangle(double width, double height) implements Shape {
        public double area() {
            return width * height;
        }
        public double perimeter() {
            return 2 * (width + height);
        }
    }

    public static void main(String[] args) {
        Shape[] shapes = {new Circle(2), new Rectangle(3, 4)};
        for (Shape shape : shapes) {
            System.out.printf(java.util.Locale.ROOT,
                    "area=%.2f perimeter=%.2f%n",
                    shape.area(), shape.perimeter());
        }
    }
}
~~~

Chạy bằng JDK 16+ (ví dụ dùng JDK 21+ với target 21):

~~~bash
javac --release 21 -encoding UTF-8 PolymorphicGeometryDemo.java
java PolymorphicGeometryDemo
~~~

Stdout:

~~~text
area=12.57 perimeter=12.57
area=12.00 perimeter=14.00
~~~

**Giải thích:**

1. `Shape` là interface chứa các phép toán chung. Nó **không `sealed`**, nên bản thân interface này không khóa danh sách implementation.
2. Hai record đều cung cấp hai phương thức `public` tương ứng. Trên interface, `area()` và `perimeter()` là phương thức công khai; implementation phải giữ quyền truy cập phù hợp.
3. Client chỉ duyệt `Shape[]` và gọi phương thức, không kiểm tra subtype hay cast.
4. `Locale.ROOT` giúp dấu thập phân trong `printf` nhất quán giữa môi trường, tránh stdout phụ thuộc locale hệ điều hành.

**Điểm cố ý giản lược:** Chương trình đa hình này **chưa validate đầu vào**. Nếu dùng để phát triển API thực, cần thêm invariant cho record như ở chương trình thứ hai, hoặc một lớp validation tương ứng. Đừng so sánh bản này với bản có validation rồi kết luận một thiết kế “an toàn hơn về mặt toán học” chỉ do cú pháp.

## 4. Chương trình 2: `sealed record` + pattern `switch`

Chương trình tiếp theo dùng ba hình và ba phép toán **`area`**, **`perimeter`**, **`label`** để thấy rõ việc tách dữ liệu với chức năng. Nó cũng đặt invariant ngay trong **compact constructor** của record, nhờ đó hình sai kích thước bị từ chối khi xây dựng.

Tạo tệp **`GeometryDesignChoicesDemo.java`**:

~~~java
public class GeometryDesignChoicesDemo {
    sealed interface Shape permits Circle, Rectangle, RightTriangle {}

    record Circle(double radius) implements Shape {
        Circle { positive(radius, "radius"); }
    }

    record Rectangle(double width, double height) implements Shape {
        Rectangle {
            positive(width, "width");
            positive(height, "height");
        }
    }

    record RightTriangle(double legA, double legB) implements Shape {
        RightTriangle {
            positive(legA, "legA");
            positive(legB, "legB");
        }
    }

    static void positive(double value, String name) {
        if (!Double.isFinite(value) || value <= 0.0) {
            throw new IllegalArgumentException(
                    name + " must be finite and > 0");
        }
    }

    static double area(Shape shape) {
        java.util.Objects.requireNonNull(shape, "shape");
        return switch (shape) {
            case Circle(var r) -> Math.PI * r * r;
            case Rectangle(var w, var h) -> w * h;
            case RightTriangle(var a, var b) -> a * b / 2.0;
        };
    }

    static double perimeter(Shape shape) {
        java.util.Objects.requireNonNull(shape, "shape");
        return switch (shape) {
            case Circle(var r) -> 2.0 * Math.PI * r;
            case Rectangle(var w, var h) -> 2.0 * (w + h);
            case RightTriangle(var a, var b) ->
                    a + b + Math.hypot(a, b);
        };
    }

    static String label(Shape shape) {
        java.util.Objects.requireNonNull(shape, "shape");
        return switch (shape) {
            case Circle(var r) when r >= 3.0 -> "large circle";
            case Circle(var r) -> "circle";

            case Rectangle(var w, var h) when w == h ->
                    "square rectangle";
            case Rectangle(var w, var h) when w > h ->
                    "landscape rectangle";
            case Rectangle(var w, var h) -> "portrait rectangle";

            case RightTriangle(var a, var b) -> "right triangle";
        };
    }

    public static void main(String[] args) {
        Shape[] shapes = {
            new Circle(2),
            new Circle(3),
            new Rectangle(3, 4),
            new Rectangle(8, 3),
            new Rectangle(4, 4),
            new RightTriangle(3, 4)
        };

        for (Shape shape : shapes) {
            System.out.printf(java.util.Locale.ROOT,
                    "%s | area=%.2f | perimeter=%.2f%n",
                    label(shape), area(shape), perimeter(shape));
        }

        try {
            area(null);
        } catch (NullPointerException e) {
            System.out.println("Null rejected");
        }

        try {
            new Circle(Double.NaN);
        } catch (IllegalArgumentException e) {
            System.out.println("Invalid: " + e.getMessage());
        }
    }
}
~~~

Biên dịch/chạy với JDK 21 trở lên:

~~~bash
javac --release 21 -encoding UTF-8 GeometryDesignChoicesDemo.java
java GeometryDesignChoicesDemo
~~~

Stdout:

~~~text
circle | area=12.57 | perimeter=12.57
large circle | area=28.27 | perimeter=18.85
portrait rectangle | area=12.00 | perimeter=14.00
landscape rectangle | area=24.00 | perimeter=22.00
square rectangle | area=16.00 | perimeter=16.00
right triangle | area=6.00 | perimeter=12.00
Null rejected
Invalid: radius must be finite and > 0
~~~

### 4.1. Vì sao compiler biết mỗi case trả về `double`?

Mỗi `switch expression` của `area` và `perimeter` được sử dụng làm giá trị trả về của phương thức `double`. Các record patterns phân rã component có kiểu tĩnh `double`. Java kiểm tra khả năng sinh kết quả và tính tương thích kiểu trong các nhánh. Một nhánh cố ý trả `"unknown"` sẽ không phù hợp với phương thức trả `double`.

### 4.2. Tại sao không có `default`?

`Shape` là một sealed interface và ba record là các kiểu được phép trong mô hình. `area` và `perimeter` xử lý `Circle`, `Rectangle` và `RightTriangle`. `label` cũng xử lý tất cả biến thể nhờ nhánh không guard cho từng kiểu sau các nhánh có guard chuyên biệt.

Bỏ một nhánh tổng quát, chẳng hạn `case RightTriangle(...)`, sẽ làm `switch expression` không còn **exhaustive**. Compiler giúp phát hiện thiếu trường hợp. Một `default` trả về `0.0` có thể làm lỗi thiết kế này không xuất hiện khi thêm hình mới, và dễ khiến công thức bị thiếu trở thành kết quả không hợp lý.

### 4.3. Vì sao nhánh có `when` đứng trước?

Trong `label`, nhánh `Circle(var r) when r >= 3.0` đứng trước nhánh `Circle(var r)` tổng quát. Tương tự, nhánh hình chữ nhật vuông đứng trước nhánh ngang, và cả hai đứng trước nhánh `Rectangle` không guard.

Nếu đặt `case Circle(var r) -> "circle"` **trước** case cùng pattern có guard, nhánh có guard bị **dominated**, bởi nhánh rộng đã bao phủ tất cả `Circle`. Đây là một điều compiler có thể kiểm tra.

**`when` nên chứa phép kiểm tra thuần túy.** Ở đây phép so sánh kích thước là đủ; không nên gọi database hay gây side effect chỉ để xác định nhãn hiển thị.

### 4.4. Vì sao phải kiểm tra `null` và kích thước trong constructor?

Trong Java, record mặc định **không tự cấm** `new Circle(-2)` hoặc `new Circle(Double.NaN)`. Trong ví dụ, compact constructor gọi `positive(...)` để từ chối giá trị không phải số hữu hạn dương, bao gồm `0.0`, `-0.0`, số âm, `NaN` và vô cực.

`Objects.requireNonNull(shape, "shape")` xác định rõ **hợp đồng đầu vào của các phép toán**. Nếu người dùng đưa selector `null`, phương thức từ chối trước khi đi vào `switch`; `null` không được coi là một “hình thứ tư”. Nếu nghiệp vụ muốn `null` mang ý nghĩa riêng, có thể chọn `case null`, nhưng phải thiết kế chủ động.

**Giới hạn số thực:** Dù kích thước là `double` hữu hạn dương, diện tích hoặc chu vi tính từ những số quá lớn vẫn có thể tràn thành `Infinity`. Validation đầu vào trên không chứng minh mọi kết quả tính toán là hữu hạn. Với bài toán nhạy cảm, cần thêm range validation và cách xử lý overflow theo hợp đồng.

### 4.5. Vì sao dùng `Math.hypot` cho tam giác vuông?

Với hai cạnh góc vuông `a` và `b`, cạnh huyền có độ dài \(\sqrt{a^2+b^2}\). `Math.hypot(a, b)` là API Java chuyên dụng cho phép tính này, thường tránh được những vấn đề số học trung gian của `Math.sqrt(a*a+b*b)`. Không nên dùng `Math.pow(a, 2)` cho ví dụ tối thiểu khi phép nhân hoặc `hypot` rõ hơn.

Kết quả với `a=3`, `b=4`: cạnh huyền bằng 5; diện tích bằng 6 và chu vi bằng 12. Đây là trường hợp dễ xác minh bằng tay và bằng test.

## 5. Khi thêm một loại hình mới: ai phải sửa?

Giả sử sản phẩm muốn thêm **ellipse** với bán trục lớn/bé. Trong thiết kế B, cần mở rộng tập permitted subtypes và thêm record:

~~~java
// MINH HỌA thay đổi cấu trúc, không phải tệp chạy độc lập.
// Sửa danh sách permits theo cấu trúc đang dùng:
sealed interface Shape permits Circle, Rectangle, RightTriangle, Ellipse {}

// Thêm một record vào cùng module/package phù hợp.
record Ellipse(double semiMajor, double semiMinor) implements Shape {
    Ellipse {
        positive(semiMajor, "semiMajor");
        positive(semiMinor, "semiMinor");
    }
}
~~~

Sau thay đổi đó, những `switch expression` trên `Shape` vốn chỉ xử lý ba kiểu cũ, **không còn đầy đủ** khi biên dịch lại. Compiler có thể yêu cầu cập nhật `area`, `perimeter` và `label`. Đó là **ưu điểm về kiểm soát tiến hóa mô hình**: không thể dễ dàng quên một phép toán trên hình mới.

Nhưng cũng là **chi phí bảo trì**: mỗi lần thêm một biến thể, nhiều `switch` phân bố trong dự án có thể cần sửa. Với ellipse, diện tích đơn giản là `Math.PI * semiMajor * semiMinor`, còn **chu vi ellipse không có công thức sơ cấp đơn giản như hình tròn**. Vì vậy, compiler đúng khi buộc người thiết kế quyết định cách tính xấp xỉ, độ chính xác và hợp đồng API trước khi triển khai. Đừng “vá” bằng `default -> 0.0` chỉ để build xanh.

Với thiết kế A dùng **interface mở** có `area()` và `perimeter()`, có thể thêm một implementation `Ellipse` triển khai hai phương thức mà không thay đổi client chỉ gọi những phương thức trên. Đó là lợi thế khi **tập loại hình mở rộng thường xuyên nhưng danh sách phép toán cốt lõi ổn định**.

**Không được bỏ qua điều kiện “interface mở”:** Nếu bản hướng đối tượng cũng khai báo `sealed interface`, việc thêm implementation vẫn cần tuân theo `permits`; đa hình không tự xóa giới hạn của sealed hierarchy.

## 6. Khi thêm một phép toán mới: ai phải sửa?

Giả sử UI cần một phép phân loại hình để hiển thị, hoặc module phân tích cần tính bounding box. Trong thiết kế B, có thể thêm một hàm mới nhận `Shape` và dùng `switch`:

~~~java
// Java 21+, trích đoạn bổ sung một phép toán không sửa record.
// shape có kiểu Shape và đã được kiểm tra non-null.
static String uiCategory(Shape shape) {
    return switch (shape) {
        case Circle(var r) -> "round";
        case Rectangle(var w, var h) -> "four-sided";
        case RightTriangle(var a, var b) -> "triangle";
    };
}
~~~

Để thêm chức năng này, **không cần thay khai báo component hoặc constructor của `Circle`/`Rectangle`/`RightTriangle`**. Với nhiều phép toán độc lập do các nhóm khác nhau quản lý (rendering, pricing, báo cáo, phân tích), điều đó có thể hữu ích.

Trong thiết kế A, nếu `uiCategory()` là hành vi bắt buộc của **mọi** `Shape`, thêm nó vào interface sẽ ảnh hưởng các implementation. Có thể tránh sửa interface bằng utility, service, adapter hoặc visitor phù hợp — vì vậy không nên kết luận “OOP không thể thêm phép toán mới”. Khác biệt là **nơi phát sinh thay đổi và cơ chế kiểm tra tính đầy đủ**.

### Sự đánh đổi về hai chiều phát triển

| Câu hỏi | Đa hình với interface mở | Sealed records + pattern `switch` |
| --- | --- | --- |
| Thường xuyên thêm loại hình mới, cùng các phép toán đã định nghĩa | Thuận tiện: loại hình mới triển khai hợp đồng | Cần cập nhật hierarchy và các switch exhaustive |
| Thường xuyên thêm phép toán mới trên tập hình gần như cố định | Có thể phải thêm interface method hoặc dùng external service | Thuận tiện: bổ sung hàm `switch` mới |
| Muốn compiler báo nơi chưa xử lý subtype mới | Interface mở không mặc định làm điều này cho các hàm ngoài | Sealed + exhaustive `switch` phát huy thế mạnh |
| Cho phép plugin bên thứ ba thêm hình | Interface mở phù hợp hơn | Sealed trực tiếp thường quá hạn chế |
| Muốn domain object tự mang hành vi cốt lõi | Tự nhiên với phương thức trên đối tượng | Phải quyết định có giữ hành vi ở service hay không |
| Muốn dữ liệu đơn giản, dễ serialize/test | Có thể dùng record nhưng interface chứa hành vi | Record biểu diễn dữ liệu rất rõ; serializer vẫn cần cấu hình polymorphism |
| Cần nhiều thao tác bên ngoài, báo cáo/hiển thị | Có thể dùng service/visitor; cân nhắc thiết kế | Tách được từng operation khỏi shape model |
| Chi phí runtime | Dynamic dispatch có thể được JIT tối ưu | Pattern checks và switch cũng có thể được JIT tối ưu |

Bảng này là **hướng dẫn lựa chọn**, không phải kết quả benchmark hay quy tắc bất biến.

## 7. `instanceof`, visitor và `enum` nằm ở đâu?

Hai thiết kế chính không phải lựa chọn duy nhất.

### 7.1. `instanceof` cho một phép kiểm tra nhỏ

Nếu code chỉ cần nhận biết một subtype:

~~~java
// Trích đoạn Java 16+, shape có kiểu Shape thích hợp.
if (shape instanceof Circle circle) {
    System.out.println(circle.radius());
}
~~~

`instanceof` type pattern **đủ rõ**; không cần tạo `switch` cho một nhánh duy nhất. Nhưng nếu có ba bốn nhánh `if/else if` xử lý tất cả hình và muốn compiler bắt buộc xử lý mọi subtype, `switch expression` trên sealed hierarchy có lợi hơn. Chuỗi `if` không mang cùng yêu cầu exhaustive như `switch expression`.

### 7.2. Visitor/double dispatch

**Visitor** có thể tách operation khỏi các shape trong codebase truyền thống, kể cả trước Java 21. Nó thường hữu ích khi có nhiều operation, cần double dispatch hoặc nhóm đã dùng visitor nhất quán. Đánh đổi là thêm interface, overload và phương thức `accept`, khiến một case study ba hình có thể trở nên nhiều boilerplate.

Với Java 21 và tập subtype đóng, **pattern `switch` thường trực tiếp hơn visitor** cho việc phân nhánh đơn giản. Nhưng đừng thay visitor đã ổn định chỉ vì cú pháp mới ngắn hơn; hãy cân nhắc compatibility, API khách hàng và khả năng kiểm thử.

### 7.3. `enum` cho tập trạng thái nhỏ

Nếu chỉ cần phân biệt một số **nhãn** không mang payload riêng, `enum` + `switch` có thể đơn giản hơn sealed hierarchy. Nhưng `Circle(radius)` và `Rectangle(width, height)` có số lượng và ý nghĩa component khác nhau. Ép chúng vào một `enum` với các trường tùy chọn thường tạo **những trạng thái dữ liệu không hợp lệ** và làm suy yếu type safety.

Một API có thể dùng `enum ShapeKind` để phục vụ UI, song điều đó không thay thế mô hình dữ liệu hình học cần bán kính/cạnh.

## 8. Không nên lưu mọi hình vào một record có trường `type`

Thiết kế sau tưởng đơn giản:

~~~java
// CỐ Ý MINH HỌA THIẾT KẾ YẾU, không phải phương án khuyến nghị.
record AnyShape(
    String type,
    Double radius,
    Double width,
    Double height,
    Double legA,
    Double legB
) {}
~~~

Nó cho phép nhiều tổ hợp vô nghĩa: `type="CIRCLE"` nhưng `radius==null`; `type="RECTANGLE"` nhưng lại mang `legA`; hoặc `type` là chuỗi lạ. Compiler không suy ra rằng trường nào bắt buộc cho từng `type`.

Các **record theo từng biến thể** làm dữ liệu cụ thể hơn:

~~~java
record Circle(double radius) implements Shape {}
record Rectangle(double width, double height) implements Shape {}
record RightTriangle(double legA, double legB) implements Shape {}
~~~

Kiểu `double` trên component giúp tránh dữ liệu `null` cho chính thành phần số nguyên thủy; **không** tự bảo đảm số dương hay hữu hạn, vì vậy constructor validation vẫn quan trọng.

Nếu dữ liệu đến từ JSON hoặc API bên ngoài, cần có **deserialization/validation** trước khi chuyển thành domain shapes; `sealed` không tự giải mã giá trị `"type"` và không tự chống được mọi payload lỗi.

## 9. Khía cạnh hình học mà compiler không thể quyết định

### 9.1. Cách biểu diễn hình vuông

Trong ví dụ, **hình vuông** là một `Rectangle` có `width == height`. Điều này có ưu điểm là không cần một subtype mới. Tuy nhiên, nếu nghiệp vụ coi hình vuông là thực thể riêng, với invariant riêng và hành vi khác biệt, có thể cân nhắc `record Square(double side) implements Shape` rồi bổ sung phép toán.

**Nên chọn theo ý nghĩa domain**, không phải vì muốn minh họa thêm một case. Nếu thêm `Square`, mọi switch exhaustive cũng cần xem xét — đó chính là một phần của quyết định dùng sealed hierarchy.

### 9.2. So sánh số thực

`when w == h` trong demo là phép so sánh **chính xác** giữa hai `double`. Nó phù hợp để minh họa khi input đơn giản là các giá trị chính xác như `4.0` và `4.0`. Nếu chiều dài lấy từ phép đo vật lý hoặc tính toán tích lũy, sai số biểu diễn có thể khiến hai giá trị *gần bằng nhau* không thỏa `==`.

Để kiểm tra “gần vuông”, cần một quy tắc tolerance phù hợp độ lớn/đơn vị và hợp đồng sản phẩm; không nên tự động dùng `Math.abs(w-h) < 0.001` cho mọi bài toán. Khi tolerance là quy tắc nghiệp vụ quan trọng, có thể đặt trong một helper thuần túy như `isSquareLike(rectangle)`.

### 9.3. Đơn vị đo và độ chính xác

Demo giả định cùng một đơn vị độ dài, ví dụ centimet, và diện tích đo bằng đơn vị **bình phương** tương ứng. Nếu bên gọi có thể nhập cả mét lẫn centimet, kiểu `double` không chứa metadata đơn vị; cần quy định API hoặc dùng value objects có đơn vị rõ ràng.

`double` phù hợp cho nhiều phép tính hình học. Nếu bài toán yêu cầu tính chính xác theo phân số/tọa độ nguyên hoặc ràng buộc kiểm chứng hình học, có thể cần mô hình số khác và thuật toán phù hợp. `BigDecimal` không tự giải quyết công thức có \(\pi\) hay căn bậc hai mà không có chính sách xấp xỉ.

### 9.4. Hình không hợp lệ và hình suy biến

`Circle(0)`, `RightTriangle(-1, 4)`, `Rectangle(Double.POSITIVE_INFINITY, 2)` là đầu vào bị compact constructor của demo từ chối. Trong một số ứng dụng toán học, hình suy biến (diện tích 0) có thể là giá trị hợp lệ. Nếu yêu cầu đó tồn tại, đừng sao chép invariant `value > 0` mà không kiểm tra contract.

**Compiler kiểm tra kiểu; constructor/validation kiểm tra invariant.** `case Circle(var r)` chỉ xác nhận record có kiểu phù hợp và lấy component, không tự chứng minh `r > 0` nếu không có bảo đảm từ constructor.

## 10. Điều gì xảy ra nếu bỏ một case khi mở rộng mô hình?

Với ba kiểu `Circle`, `Rectangle`, `RightTriangle`, `switch expression` trong `area` phải xử lý đầy đủ các biến thể được phép. Ví dụ dưới đây **cố ý thiếu** tam giác vuông:

~~~java
// CỐ Ý SAI, trích đoạn trong phương thức trả double;
// shape có kiểu Shape với ba permitted subtype.
return switch (shape) {
    case Circle(var r) -> Math.PI * r * r;
    case Rectangle(var w, var h) -> w * h;
    // Thiếu RightTriangle.
};
~~~

Compiler Java 21 sẽ báo **không exhaustive**. Đây là tín hiệu hữu ích khi kiểm soát thay đổi domain model.

Không nên “sửa” bằng:

~~~java
// KHÔNG KHUYẾN NGHỊ: ngụy trang thiếu công thức.
default -> 0.0;
~~~

Nếu một hình mới được thêm nhưng chưa có công thức, trả 0.0 có thể tạo kết quả sai âm thầm. Nếu thực sự muốn fallback (ví dụ selector kiểu `Object` chứa dữ liệu lạ), hãy nêu rõ nó nghĩa là “không hỗ trợ” và chọn cách báo lỗi/phản hồi phù hợp, thay vì một giá trị số tưởng như hợp lệ.

**Giới hạn của compiler:** Nó không chứng minh công thức `Math.PI*r*r` là đúng về mặt toán học, không bắt lỗi nhầm `2*Math.PI*r*r` với diện tích, cũng không chứng minh các giá trị floating-point luôn hữu hạn. Exhaustiveness chỉ giúp biết **đã có nhánh xử lý**, không chứng minh **nhánh xử lý đúng**.

## 11. Chọn thiết kế qua ba kịch bản thực tế

### Kịch bản A: thư viện hình học lõi, đối tượng tự cung cấp phép đo

Một thư viện công khai muốn hỗ trợ người dùng viết `shape.area()` và `shape.perimeter()`. Hai phép toán này là một phần **hợp đồng cốt lõi**; các ứng dụng có thể tự tạo thêm implementation.

**Nghiêng về interface mở + đa hình** nếu thực sự cần khả năng mở rộng bởi người dùng và danh sách phép toán chung tương đối ổn định. Đưa validation vào constructor/nhà máy tạo đối tượng hoặc lớp data phù hợp.

### Kịch bản B: engine nội bộ có ba hình cố định nhưng nhiều bước phân tích

Một engine chỉ xử lý `Circle`, `Rectangle`, `RightTriangle`, nhưng có nhiều phép tính: diện tích, chu vi, render metadata, phân loại, báo cáo, so sánh hay chuyển đổi.

**Nghiêng về sealed records + exhaustive switch** nếu tập hình thực sự được sở hữu và kiểm soát bởi một module. Thêm operation riêng mà không cần thay đổi record; compiler buộc xem xét nơi xử lý khi thêm subtype.

### Kịch bản C: API xử lý dữ liệu bên ngoài, tập hình chưa biết trước

Một service nhận JSON có type discriminator từ nhiều nhà cung cấp; có thể xuất hiện type mới mà module chưa được cập nhật.

Không nên mặc định đặt mọi payload chưa biết vào một sealed hierarchy rồi cho rằng code luôn exhaustive. Cần **boundary layer** giải mã và xác thực, một chính sách cho unknown type/version, có thể chuyển dữ liệu đã biết thành các record domain nội bộ. Tại ranh giới đó, một mô hình mở/adapter có thể phù hợp hơn.

**Quyết định thực tế thường là kết hợp:** lớp nhận JSON linh hoạt bên ngoài → chuẩn hóa thành các domain record rõ kiểu bên trong → dùng exhaustive switch trong module xử lý. Không cần buộc mọi lớp của hệ thống theo cùng một phong cách.

## 12. Quy trình chọn thiết kế cho một case study hình học

1. **Liệt kê kiểu hình thật sự cần có.** Đừng tạo `Square` hoặc `Polygon` chỉ vì dễ viết ví dụ; kiểm tra xem chúng có invariant khác biệt không.
2. **Liệt kê những phép toán cốt lõi.** `area`, `perimeter` có thuộc hợp đồng chung cho mọi shape không? Phép phân loại UI có thuộc domain không?
3. **Xác định chiều thay đổi thường xuyên.** Thêm subtype hay thêm operation? Ai sở hữu quyền mở rộng?
4. **Quyết định mở/đóng hierarchy.** Nếu bên thứ ba được thêm hình tùy ý, interface mở tự nhiên hơn. Nếu module cần kiểm soát danh sách, dùng `sealed`.
5. **Chọn hình thức dữ liệu.** `record` hợp với những dữ liệu hình học dạng value object và component bất biến ở mức field; nếu cần identity, vòng đời, trạng thái mutable phức tạp, class thường có thể hợp lý hơn.
6. **Đặt invariant rõ ràng.** Số hữu hạn dương, đơn vị đo, tolerance, hình suy biến; đừng phó mặc cho pattern matching.
7. **Viết một implementation nhỏ của từng hướng.** So sánh độ rõ ràng khi tính công thức, khi thêm một hình, khi thêm một operation.
8. **Kiểm tra compiler.** Với sealed switch, cố ý thiếu một case và xác nhận build bị từ chối; đừng dùng `default` chỉ để làm build xanh.
9. **Kiểm tra runtime và số học.** Chạy input hợp lệ, không hợp lệ, null và giá trị biên; xem overflow/precision nếu domain cần.
10. **Chọn theo chi phí bảo trì của nhóm.** Code ngắn không tự bảo đảm dễ đọc, và thiết kế giàu pattern nhất chưa chắc là thiết kế đơn giản nhất.

Trong codebase lớn, đừng thay đổi cả mô hình API công khai chỉ để chuyển một chuỗi `if/else` thành pattern `switch`. Có thể triển khai từng bước: refactor tính toán thuần túy, thêm tests, đánh giá compatibility, rồi mới cân nhắc đổi hierarchy khi có nhu cầu thật.

## 13. Bảng kiểm thử cho cả hai hướng

Một bộ test nhỏ nên bao phủ **công thức**, **quy tắc dữ liệu** và **hợp đồng mở rộng**:

| Trường hợp | Expected |
| --- | --- |
| `Circle(2)` | Diện tích \(4\pi\); chu vi \(4\pi\) |
| `Rectangle(3,4)` | Diện tích 12; chu vi 14 |
| `RightTriangle(3,4)` | Diện tích 6; chu vi 12 |
| `Rectangle(4,4)` | Diện tích 16; nhãn hình vuông theo cách phân loại của demo |
| `Circle(3)` | Nhánh guard `r >= 3` được chọn |
| `Rectangle(8,3)` | Nhánh `w > h` được chọn |
| `Circle(0)` hoặc `Circle(-1)` | Bị constructor validation của demo từ chối |
| `Circle(Double.NaN)` | Bị constructor validation từ chối |
| `area(null)` | Bị `Objects.requireNonNull` từ chối |
| Thêm subtype mới nhưng không bổ sung `switch` exhaustive | Compiler báo thiếu nhánh khi biên dịch lại |
| Thêm phép toán mới trên sealed hierarchy | Compiler yêu cầu cung cấp các case cần thiết |
| Giá trị cực lớn | Cần kiểm tra chính sách overflow/precision riêng |

### Assertions không nên chỉ so sánh bằng `==` cho phép tính xấp xỉ

~~~java
// Trích đoạn kiểm thử ý tưởng, khi area(...) đã khai báo.
// Không dùng assert Java trần nếu dự án không bật -ea.
double expected = 4.0 * Math.PI;
double actual = area(new Circle(2));
double tolerance = 1e-10;
if (Math.abs(expected - actual) > tolerance) {
    throw new AssertionError("Unexpected area: " + actual);
}
~~~

Tolerances là chính sách kiểm thử, không phải hằng số đúng cho mọi giá trị hay mọi đơn vị. Với giá trị lớn, có thể cần xét sai số tương đối; với `NaN`, phép so sánh bằng `>` đặc biệt dễ gây bỏ sót. Các demo đã validate `NaN` khi tạo shape, nhưng một hệ thống thực cần thiết kế rõ tất cả trường hợp số học quan trọng.

**Đừng gộp nhiều thay đổi trong một test:** kiểm thử exhaustiveness là kiểm thử compile-time; kiểm thử công thức là runtime; kiểm thử serialization là integration test. Ba lớp test bổ sung cho nhau.

## 14. Lỗi thiết kế thường gặp sau khi học Pattern Matching

| Lỗi | Vì sao không phù hợp | Hướng sửa |
| --- | --- | --- |
| Dùng `default -> 0.0` trong switch sealed | Che thiếu loại hình và tạo kết quả sai | Exhaustive switch với case cụ thể |
| Cho rằng `record` tự chặn kích thước âm | Kiểu `double` chấp nhận nhiều giá trị không hợp lệ | Compact constructor, validation theo domain |
| Đưa mọi UI formatting lên interface `Shape` | Làm tăng coupling giữa domain và presentation | Tách operation/service nếu không thuộc domain |
| Chuyển mọi logic sang `switch` dù chỉ gọi `shape.area()` | Lặp lại phân nhánh không cần thiết | Giữ polymorphism nếu hành vi đã thuộc đối tượng |
| Dùng interface mở nhưng đòi compiler liệt kê hết subtype không biết trước | Hai mục tiêu mâu thuẫn | Chọn sealed nếu cần closed-world exhaustiveness |
| Dùng sealed khi plugin cần thêm subtype tùy ý | Không phù hợp mục tiêu mở rộng | Interface mở hoặc adapter/plugin boundary |
| Coi `==` trên `double` luôn là kiểm tra “gần bằng” | Sai với dữ liệu có sai số đo | Thiết kế tolerance phù hợp |
| Dùng `Math.sqrt(a*a+b*b)` cho mọi độ lớn | Tính trung gian có thể overflow/underflow | Cân nhắc `Math.hypot(a,b)` |
| Tin compiler chứng minh công thức toán học đúng | Exhaustiveness chỉ nói đã có case | Unit tests và kiểm chứng công thức |
| Dùng `ShapeKind` và hàng loạt field nullable | Tạo tổ hợp payload vô nghĩa | Dùng record từng biến thể khi phù hợp |
| Refactor từ OOP sang sealed và hứa tăng hiệu năng | Không có dữ liệu đo | Benchmark/profiler sau khi xác định hot path |
| Thêm loại hình mới mà không xem lại ý nghĩa domain | Ví dụ ellipse, square có quy tắc riêng | Đặc tả invariant và công thức trước khi mở rộng |

## 15. Bài tập thực hành có hướng dẫn

### Bài 1 — Chọn giữa OOP và pattern switch

Một thư viện cho phép người dùng định nghĩa `Hexagon`, `Star` và các hình tùy ý, nhưng mọi hình đều cần `area()`, `perimeter()`. Nên nghiêng về thiết kế nào?

**Gợi ý đáp án:** **Interface mở + đa hình** vì các implementation đến từ bên ngoài và phép toán cốt lõi đã cố định. Có thể dùng record/class tùy kiểu hình; xác thực dữ liệu ở nơi xây dựng. Một sealed hierarchy đóng với danh sách subtype cố định không phù hợp yêu cầu plugin mở.

### Bài 2 — Chọn khi cần thêm operation

Một engine chỉ có ba hình, ít khi thêm subtype, nhưng liên tục bổ sung operation xuất SVG, tính chu vi, diện tích và hiển thị nhãn. Chọn hướng nào?

**Gợi ý đáp án:** **Sealed records + switch** là lựa chọn đáng cân nhắc vì tập hình ổn định, các operation có thể đặt tách biệt. Tuy nhiên, nếu rendering cần state phức tạp hay có framework visitor sẵn, có thể chọn một architecture khác; phân tích coupling chứ không máy móc.

### Bài 3 — Cảnh báo lỗi tính bao phủ

Trong `area(Shape shape)`, xóa `case RightTriangle(...)` rồi biên dịch lại. Điều gì xảy ra?

**Đáp án:** `switch expression` trên sealed hierarchy không còn exhaustive nên compiler từ chối. Không nên thêm `default -> 0.0` để xóa lỗi, vì khi đó phép tính cho tam giác sẽ sai.

### Bài 4 — Công thức và số học

Với `RightTriangle(5,12)`, diện tích và chu vi mong đợi là gì? Vì sao dùng `Math.hypot`?

**Đáp án:** Diện tích \(5\times12/2=30\); cạnh huyền 13; chu vi \(5+12+13=30\). `Math.hypot` là API dành cho tính căn của tổng bình phương, hữu ích để giảm rủi ro số học trung gian.

### Bài 5 — Mô hình hình vuông

Hệ thống muốn phân biệt hình vuông với hình chữ nhật ở mức thống kê, nhưng công thức diện tích/chu vi giống nhau. Có nhất thiết thêm `record Square`?

**Gợi ý đáp án:** Không. Nếu “vuông” chỉ là một **thuộc tính suy ra** từ `Rectangle` và không cần invariant/identity riêng, có thể giữ `Rectangle` và hàm phân loại phù hợp. Nếu nghiệp vụ có hợp đồng riêng cho hình vuông (như chỉ cần một cạnh, thao tác tạo hình riêng), `Square` là một thiết kế hợp lý nhưng sẽ tác động tới exhaustive switches.

### Bài 6 — Sai số floating-point

`Rectangle(4.0, 4.0)` được gắn nhãn `square rectangle`. Nếu width và height đến từ hai phép đo gần bằng nhau, có nên dùng đúng `when w == h`?

**Gợi ý đáp án:** Chỉ khi yêu cầu thực sự là **bằng nhau chính xác**. Với dữ liệu đo, cần định nghĩa “gần bằng” theo đơn vị và tolerance phù hợp; không mặc định một ngưỡng cố định cho mọi bài toán.

## 16. Kết luận lựa chọn thiết kế

**Hỏi hai câu trước khi chọn cú pháp:**

1. **Tập loại hình có đóng và được một module kiểm soát không?**
2. **Trong tương lai, thứ thay đổi nhiều hơn là các loại hình hay các phép toán?**

Nếu **loại hình mở, hành vi chung ổn định**, interface + đa hình là một lựa chọn tự nhiên. Nếu **tập loại hình đóng, nhiều phép toán độc lập và cần compiler bắt thiếu trường hợp**, `sealed` + `record` + exhaustive pattern `switch` là một lựa chọn mạnh. Nếu chỉ kiểm tra một kiểu trong một phương thức nhỏ, `instanceof` pattern có thể đơn giản nhất. Visitor, adapter hoặc service có thể cần thiết khi kiến trúc đòi hỏi.

Trên hết, **công thức đúng, invariant rõ ràng, ý nghĩa hình học nhất quán, API dễ bảo trì và test tái lập** quan trọng hơn việc sử dụng tính năng Java mới ở mọi nơi. Java Pattern Matching đem lại công cụ diễn đạt phân nhánh an toàn và dễ đọc hơn, nhưng **không thay thế việc chọn đúng domain model**.

**Tài liệu chính thức:**
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394).
- [JEP 395 — Records](https://openjdk.org/jeps/395).
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409).
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440).
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
- [Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [Java SE 21 — `Math.hypot`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html#hypot(double,double)).
