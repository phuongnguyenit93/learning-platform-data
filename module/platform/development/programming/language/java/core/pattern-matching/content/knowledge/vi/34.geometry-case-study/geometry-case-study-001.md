# Thiết kế Shape bằng sealed interface – Case study hình học trong Java 21

Một ứng dụng hình học thường xử lý nhiều loại hình có cùng ý nghĩa miền nghiệp vụ: **hình tròn**, **hình chữ nhật** và **tam giác vuông**. Chúng đều có thể được tính **diện tích**, **chu vi**, phân loại hoặc hiển thị, nhưng công thức khác nhau theo từng kiểu. Nếu chỉ dùng một lớp `Shape` chứa nhiều trường tùy chọn và một chuỗi kiểm tra kiểu thủ công, mô hình sẽ khó bảo trì, dễ tạo trạng thái không hợp lệ và khó phát hiện nhánh tính toán bị bỏ sót.

Từ Java 17, **`sealed interface`** cho phép công khai một kiểu chung mà **giới hạn trực tiếp những kiểu nào được phép triển khai nó**. Kết hợp `record` cho từng biến thể và **pattern matching cho `switch`** trong Java 21, ta có mô hình gọn, bất biến về dữ liệu cơ bản và được compiler kiểm tra tính **exhaustive** của các phép phân loại.

Bài tập trung vào cách thiết kế mô hình domain `Shape`, không chỉ vào cú pháp. Các ví dụ hoàn chỉnh dùng **Java 21+**, `record`, `sealed`, record patterns, `when` và `switch expression`; không cần `--enable-preview`.

## 1. Yêu cầu nghiệp vụ và lựa chọn mô hình

Giả sử thư viện hình học ban đầu hỗ trợ ba loại:

| Loại hình | Dữ liệu cần lưu | Diện tích | Chu vi |
| --- | --- | --- | --- |
| Hình tròn `Circle` | Bán kính `r` | `Math.PI * r * r` | `2 * Math.PI * r` |
| Hình chữ nhật `Rectangle` | Chiều rộng `w`, chiều cao `h` | `w * h` | `2 * (w + h)` |
| Tam giác vuông `RightTriangle` | Hai cạnh góc vuông `a`, `b` | `a * b / 2` | `a + b + Math.hypot(a, b)` |

Để biểu diễn miền một cách chính xác:

1. Chỉ ba loại trên được xem là `Shape` trong phiên bản đầu tiên.
2. Mỗi loại hình lưu **đúng những tham số** cần cho hình đó.
3. Kích thước phải là số thực **hữu hạn và lớn hơn 0** khi khởi tạo; không chấp nhận `NaN`, vô cực, giá trị 0 hay âm.
4. Mỗi thao tác tính diện tích hoặc chu vi phải xử lý **đủ cả ba loại hình**.
5. Khi bổ sung loại hình mới, những phép xử lý còn thiếu cần bị phát hiện sớm khi biên dịch thay vì âm thầm trả kết quả mặc định sai.
6. Quy tắc với `null` phải rõ ràng: các phép tính từ chối `null`, còn hàm phân loại có thể trả nhãn `missing`.

**Không phải mọi ứng dụng đều cần đúng ba loại hình này.** Đây là *case study* có tập biến thể được đóng có chủ đích. Nếu sản phẩm cho plugin bên ngoài tự định nghĩa bất kỳ hình nào, một `sealed` hierarchy khép kín hoàn toàn có thể không phù hợp.

## 2. Sơ đồ cấu trúc Shape

```text
                   sealed interface Shape
                            |
                  permits 3 record types
                /           |            \
               /            |             \
       record Circle    record Rectangle    record RightTriangle
        radius:double    width:double        legA:double
                         height:double       legB:double

       ShapeService:
         area(Shape)       -> exhaustive pattern switch
         perimeter(Shape)  -> exhaustive pattern switch
         kind(Shape)       -> guarded case / case null
```

Mỗi record là một **biến thể** (*variant*) mang dữ liệu; những phép tính có thể được đặt trong service/hàm độc lập và dùng pattern matching để chọn thuật toán. Đây là cách biểu diễn **algebraic data type (ADT)** ở mức ý tưởng: một tổng của các biến thể cố định, mỗi biến thể có cấu trúc dữ liệu riêng.

Có hai lợi ích chính:

- **Data model rõ ràng:** `Circle` không có các trường `width` hoặc `legA` thừa; `RightTriangle` không phải tự suy ra bán kính.
- **Compiler tham gia kiểm soát:** `switch` trên `Shape` có thể kiểm tra xem mọi biến thể được phép đã có case phù hợp chưa.

## 3. Khai báo sealed interface và các subtype record

Phần cốt lõi của mô hình:

```java
sealed interface Shape permits Circle, Rectangle, RightTriangle {}

record Circle(double radius) implements Shape {}

record Rectangle(double width, double height) implements Shape {}

record RightTriangle(double legA, double legB) implements Shape {}
```

Đây là **đoạn khai báo minh họa**, khi dùng trong chương trình Java thực tế phải đặt trong cùng phạm vi/package/module được phép theo quy tắc của Java. Toàn bộ lớp chạy được nằm ở mục 9.

### Ý nghĩa của sealed

Trong:

```java
sealed interface Shape permits Circle, Rectangle, RightTriangle {}
```

- Từ khóa `sealed` giới hạn **những lớp/interface con trực tiếp** được phép triển khai `Shape`.
- `permits` liệt kê danh sách biến thể được phép.
- Một lớp khác cố viết `implements Shape` mà không thuộc danh sách `permits` sẽ bị compiler từ chối.
- Kiểu con trực tiếp của một sealed interface cần khai báo rõ định hướng mở rộng: **`final`**, **`sealed`**, hoặc **`non-sealed`** (theo những quy tắc tương ứng).
- `record` vốn **`final` ngầm định**, nên `Circle`, `Rectangle`, `RightTriangle` ở đây là các biến thể cuối; không thể tạo lớp con kế thừa chúng.

**Quan trọng:** `sealed` không tự bảo đảm mọi thành phần dữ liệu hợp lệ. Nó **đóng tập subtype**, chứ không thay thế việc kiểm tra `radius > 0` hoặc `Double.isFinite(radius)`. Các bất biến đó cần được thiết kế trong từng record.

### Vì sao dùng record?

Record phù hợp với hình được xác định bằng dữ liệu ít thay đổi:

```java
record Circle(double radius) implements Shape {}
```

Java tự sinh constructor chính, accessor `radius()`, `equals`, `hashCode` và `toString` có ý nghĩa theo trạng thái của record. Thành phần của record là `private final`; không có setter mặc định.

Ví dụ:

```java
Circle c = new Circle(2.0);
System.out.println(c.radius()); // 2.0
```

Trong case study, các thành phần đều là kiểu nguyên thủy `double` nên dữ liệu kích thước của mỗi instance không bị thay đổi qua tham chiếu mutable. Tuy nhiên, **record nói chung chỉ bất biến nông** (*shallowly immutable*): nếu một record có thành phần là `List` có thể sửa, đối tượng được tham chiếu vẫn có thể thay đổi; điều đó không tự bị cấm chỉ vì dùng record.

## 4. Áp đặt invariants: kích thước hữu hạn và dương

Một mô hình dùng số `double` có những giá trị đặc biệt: `Double.NaN`, `Double.POSITIVE_INFINITY` và `Double.NEGATIVE_INFINITY`. Các giá trị đó không phải bán kính hay cạnh hợp lệ của bài toán. Tương tự, `0` và giá trị âm không biểu diễn hình có kích thước dương trong mô hình đã chọn.

Nên kiểm tra ngay lúc khởi tạo:

```java
private static void checkDimension(double value, String field) {
    if (!Double.isFinite(value) || value <= 0.0) {
        throw new IllegalArgumentException(
                field + " must be finite and positive");
    }
}
```

Với record dùng **compact constructor**:

```java
record Circle(double radius) implements Shape {
    Circle {
        checkDimension(radius, "radius");
    }
}
```

Cách tương tự cho hình chữ nhật và tam giác vuông:

```java
record Rectangle(double width, double height) implements Shape {
    Rectangle {
        checkDimension(width, "width");
        checkDimension(height, "height");
    }
}

record RightTriangle(double legA, double legB) implements Shape {
    RightTriangle {
        checkDimension(legA, "legA");
        checkDimension(legB, "legB");
    }
}
```

Các khối trên là **thành phần của cùng lớp demo**: `checkDimension` được khai báo trong lớp bao bên ngoài. Không phải các tệp riêng có thể biên dịch mà thiếu hàm này.

Khi code gọi:

```java
new Circle(0.0);
new Rectangle(Double.NaN, 2.0);
new RightTriangle(3.0, Double.POSITIVE_INFINITY);
```

mỗi lời gọi đều ném `IllegalArgumentException` tại constructor tương ứng. Việc từ chối sớm giúp các hàm xử lý phía sau không phải lặp lại kiểm tra “kích thước có tồn tại và hợp lệ hay không” ở mọi case.

**Giới hạn số học:** kiểm tra `Double.isFinite` cho **đầu vào** không đảm bảo kết quả nhân/chia luôn hữu hạn nếu số cực lớn làm phép tính tràn `double`. Với ứng dụng kỹ thuật thực tế, cần lựa chọn miền kích thước, đơn vị đo, tolerance và chính sách overflow/precision phù hợp. Bài dùng kích thước nhỏ, có kết quả ổn định để tập trung vào mô hình và pattern matching.

## 5. Tính diện tích bằng exhaustive pattern switch

Một cách triển khai dễ bảo trì là giữ dữ liệu trong `record` và thuật toán ở phương thức nhận `Shape`:

```java
static double area(Shape shape) {
    Objects.requireNonNull(shape, "shape");
    return switch (shape) {
        case Circle(double r) -> Math.PI * r * r;
        case Rectangle(double w, double h) -> w * h;
        case RightTriangle(double a, double b) -> a * b / 2.0;
    };
}
```

Trong đoạn trên cần `import java.util.Objects;` hoặc dùng `java.util.Objects.requireNonNull`. Đây là **phương thức minh họa**, có cùng định nghĩa trong chương trình hoàn chỉnh ở mục 9.

### Pattern deconstruction hoạt động ra sao?

Với `case Rectangle(double w, double h)`:

1. `switch` kiểm tra selector có khớp kiểu record `Rectangle` không.
2. Nếu khớp, record pattern tách hai thành phần theo thứ tự khai báo.
3. `double w` và `double h` ràng buộc biến đã được suy luận/kiểm tra kiểu.
4. Phần thân case tính `w * h`; không cần `(Rectangle) shape` rồi gọi `width()` và `height()` thủ công.

Nếu không cần tách ngay các thành phần, vẫn có thể dùng **type pattern** như `case Rectangle rectangle -> rectangle.width() * rectangle.height();`. Chọn record pattern khi cấu trúc được dùng trực tiếp, và type pattern khi cần cả instance hoặc hành vi trên instance.

### Vì sao switch không cần default?

Vì `Shape` chỉ cho phép ba subtype record `final` đang liệt kê, compiler có đủ dữ kiện để chứng minh rằng mỗi giá trị `Shape` **khác `null`** đều thuộc một case. Do đó `switch expression` **exhaustive**.

Việc không viết `default` là có chủ đích: khi thêm biến thể mới, compiler có thể chỉ ra ngay những hàm còn thiếu case. Nếu dùng `default -> 0`, hàm diện tích có nguy cơ trả `0` âm thầm cho hình mới mà không có công thức đúng.

### Vì sao có requireNonNull trước switch?

`Shape` là kiểu tham chiếu; người gọi vẫn có thể truyền `null`. Ở phương thức `area`, ta quyết định **`null` là dữ liệu không hợp lệ** và từ chối ngay bằng `Objects.requireNonNull(shape,"shape")`, giúp lỗi có thông điệp rõ ràng.

Nếu bỏ guard đó, pattern switch Java 21 không có `case null` thường cũng ném `NullPointerException` khi selector null; nhưng guard rõ ràng diễn đạt hợp đồng của phương thức và ổn định vị trí báo lỗi.

## 6. Tính chu vi: thuật toán thứ hai trên cùng sealed model

Không cần thêm phương thức `area()` hoặc `perimeter()` vào mỗi record chỉ để mô hình hoạt động. Ta có thể định nghĩa thao tác mới bằng một pattern switch khác:

```java
static double perimeter(Shape shape) {
    Objects.requireNonNull(shape, "shape");
    return switch (shape) {
        case Circle(double r) -> 2.0 * Math.PI * r;
        case Rectangle(double w, double h) -> 2.0 * (w + h);
        case RightTriangle(double a, double b) ->
                a + b + Math.hypot(a, b);
    };
}
```

Với `RightTriangle`, hai trường `legA` và `legB` được định nghĩa là **hai cạnh tạo góc vuông**, nên cạnh huyền là `Math.hypot(a,b)` và chu vi là `a + b + cạnhHuyen`. Đây là lý do nên đặt tên cụ thể `RightTriangle` thay vì `Triangle` nếu chỉ lưu hai cạnh.

`Math.hypot` tính độ dài cạnh huyền bằng thuật toán được thiết kế để xử lý số thực tốt hơn cách tính trực tiếp `Math.sqrt(a*a + b*b)` trong nhiều trường hợp biên số học. Tuy vậy, tổng chu vi vẫn có thể tràn nếu kích thước vượt phạm vi hợp lý.

Ví dụ với tam giác vuông cạnh 3 và 4:

```text
diện tích = 3 * 4 / 2 = 6
cạnh huyền = hypot(3, 4) = 5
chu vi = 3 + 4 + 5 = 12
```

**Điểm mạnh về kiến trúc:** thêm thao tác mới như `perimeter` không đòi hỏi chỉnh sửa các khai báo record. Mỗi thao tác được kiểm tra exhaustive riêng, giúp dễ tổ chức service và test theo hành vi.

**Đánh đổi:** khi thêm một loại hình mới vào `Shape`, phải cập nhật **tất cả** những exhaustive switches đang xử lý nó. Với domain đóng, việc compiler buộc sửa là một lợi thế; với plugin mở, đây có thể là chi phí không mong muốn.

## 7. Guard when, thứ tự case và phân loại hình

Ngoài công thức toán học, domain có thể có những **nhóm hình đặc biệt**:

- `Circle` với bán kính đúng `1.0` gọi là **unit circle**.
- `Rectangle` có `width == height` được gọi là hình chữ nhật có hai cạnh bằng nhau, tương ứng một **hình vuông** trong mô hình.
- `RightTriangle` với `legA == legB` là **tam giác vuông cân**.
- `null` có thể được phân loại là **missing** thay vì ném lỗi, khác chính sách của `area`/`perimeter`.

```java
static String kind(Shape shape) {
    return switch (shape) {
        case null -> "missing";
        case Circle(double r) when r == 1.0 -> "unit circle";
        case Circle(double r) -> "circle r=" + r;
        case Rectangle(double w, double h) when w == h ->
                "square rectangle";
        case Rectangle(double w, double h) -> "rectangle";
        case RightTriangle(double a, double b) when a == b ->
                "isosceles right triangle";
        case RightTriangle(double a, double b) -> "right triangle";
    };
}
```

### Tại sao case có when phải đứng trước?

Nhánh `case Circle(double r)` không có guard khớp **mọi** `Circle`, bao gồm cả bán kính 1. Nếu đặt nhánh này trước `case Circle(double r) when r == 1.0`, compiler phát hiện nhánh sau bị **dominated case** (bị che hoàn toàn).

Tương tự, `case Rectangle(...)` rộng phải đứng sau nhánh `Rectangle(...) when w == h`; `RightTriangle(...)` rộng đứng sau nhánh tam giác vuông cân.

Guard `when` chỉ được đánh giá **sau khi pattern khớp**, do đó `r`, `w`, `h`, `a`, `b` đã được ràng buộc và có kiểu `double` hợp lệ theo khai báo record.

### So sánh số thực trong guard

`w == h` là phép so sánh **bằng chính xác** hai giá trị `double`. Trong case study, các kích thước được cung cấp trực tiếp như `2.0` và `2.0` nên điều này phù hợp với phân loại “hai kích thước lưu trong record có giá trị bằng nhau”.

Nếu kích thước là **kết quả tính toán đo đạc**, hai giá trị gần nhau có thể không bằng nhau theo bit. Khi đó cần **quy tắc tolerance có giải thích** (chẳng hạn dựa trên sai số tuyệt đối/tương đối của miền ứng dụng) thay vì tự suy ra `==` là kiểm tra gần bằng. Đừng thay `==` bằng một ngưỡng tùy ý khi chưa xác định đơn vị, độ chính xác và giá trị biên.

### Tại sao null được xử lý khác nhau?

`kind(null)` trả `missing` vì phân loại có thể dùng trong UI/diagnostics. `area(null)` lại ném NPE có chủ đích vì tính toán không có dữ liệu đầu vào là sai hợp đồng.

**Không có quy tắc buộc mọi phương thức xử lý `null` giống hệt nhau.** Quan trọng là viết rõ hợp đồng, nhất quán với mục tiêu từng thao tác, và kiểm thử đúng hành vi đã quyết định.

## 8. instanceof với Shape và flow scoping

Không phải mọi kiểm tra đều cần `switch`. Nếu chỉ cần phát hiện một loại hình cụ thể, `instanceof` với record pattern là đủ:

```java
static boolean hasLargeCircle(Shape shape) {
    return shape instanceof Circle(double radius) && radius >= 2.0;
}
```

Ở đây:

- Nếu `shape == null`, `instanceof` là `false`.
- Nếu `shape` là `Rectangle` hoặc `RightTriangle`, record pattern `Circle(...)` không khớp.
- Nếu `shape` là `Circle`, biến `radius` được tạo và có kiểu tĩnh `double`.
- Vế phải `radius >= 2.0` chỉ được đánh giá khi phép khớp ở vế trái thành công nhờ `&&` short-circuit, nên compiler cho phép dùng biến `radius`.
- Với `new Circle(2.0)`, phương thức trả `true`; với `new Circle(1.0)`, trả `false`.

Đây là **flow scoping/definite matching**: phạm vi có thể sử dụng biến pattern phụ thuộc vào luồng điều khiển đã chứng minh pattern khớp.

### Khi nào dùng instanceof, khi nào dùng switch?

- Chỉ một câu hỏi “đây có phải Circle đạt điều kiện không?” → `instanceof` ngắn và rõ.
- Cần kết quả cho **mọi biến thể Shape** → `switch expression` dễ kiểm soát tính đầy đủ hơn.
- Cần tác vụ trải qua nhiều trạng thái bên trong một subtype → có thể dùng phương thức riêng hoặc Visitor; không buộc mọi thuật toán phải là một `switch` lớn.

Không nên lạm dụng `switch` cho một điều kiện đơn giản hoặc viết nhiều cast tay khi đã có type/record pattern hỗ trợ.

## 9. Chương trình Java 21 hoàn chỉnh – SealedShapeDemo.java

Lưu toàn bộ mã sau vào tệp **`SealedShapeDemo.java`**. Đây là ví dụ độc lập, có kiểm tra dữ liệu và các ca thử thành công/thất bại.

```java
import java.util.Locale;
import java.util.Objects;

public class SealedShapeDemo {
    sealed interface Shape permits Circle, Rectangle, RightTriangle {}

    record Circle(double radius) implements Shape {
        Circle {
            checkDimension(radius, "radius");
        }
    }

    record Rectangle(double width, double height) implements Shape {
        Rectangle {
            checkDimension(width, "width");
            checkDimension(height, "height");
        }
    }

    record RightTriangle(double legA, double legB) implements Shape {
        RightTriangle {
            checkDimension(legA, "legA");
            checkDimension(legB, "legB");
        }
    }

    private static void checkDimension(double value, String field) {
        if (!Double.isFinite(value) || value <= 0.0) {
            throw new IllegalArgumentException(field + " must be finite and positive");
        }
    }

    static double area(Shape shape) {
        Objects.requireNonNull(shape, "shape");
        return switch (shape) {
            case Circle(double r) -> Math.PI * r * r;
            case Rectangle(double w, double h) -> w * h;
            case RightTriangle(double a, double b) -> a * b / 2.0;
        };
    }

    static double perimeter(Shape shape) {
        Objects.requireNonNull(shape, "shape");
        return switch (shape) {
            case Circle(double r) -> 2.0 * Math.PI * r;
            case Rectangle(double w, double h) -> 2.0 * (w + h);
            case RightTriangle(double a, double b) -> a + b + Math.hypot(a, b);
        };
    }

    static String kind(Shape shape) {
        return switch (shape) {
            case null -> "missing";
            case Circle(double r) when r == 1.0 -> "unit circle";
            case Circle(double r) -> "circle r=" + r;
            case Rectangle(double w, double h) when w == h -> "square rectangle";
            case Rectangle(double w, double h) -> "rectangle";
            case RightTriangle(double a, double b) when a == b ->
                    "isosceles right triangle";
            case RightTriangle(double a, double b) -> "right triangle";
        };
    }

    static boolean hasLargeCircle(Shape shape) {
        return shape instanceof Circle(double radius) && radius >= 2.0;
    }

    static void assertClose(String name, double actual, double expected) {
        if (Math.abs(actual - expected) > 1e-9) {
            throw new AssertionError(name + ": " + actual + " != " + expected);
        }
    }

    public static void main(String[] args) {
        Shape[] shapes = {
            new Circle(2.0),
            new Rectangle(3.0, 4.0),
            new RightTriangle(3.0, 4.0)
        };
        for (Shape shape : shapes) {
            System.out.printf(
                    Locale.ROOT, "%s | area=%.2f | perimeter=%.2f%n",
                    kind(shape), area(shape), perimeter(shape));
        }
        System.out.println(kind(new Circle(1.0)));
        System.out.println(kind(new Rectangle(2.0, 2.0)));
        System.out.println(kind(new RightTriangle(3.0, 3.0)));
        System.out.println(kind(null));
        System.out.println("circle>=2: " + hasLargeCircle(shapes[0]));

        assertClose("circle", area(shapes[0]), 4.0 * Math.PI);
        assertClose("rectangle", area(shapes[1]), 12.0);
        assertClose("triangle", area(shapes[2]), 6.0);
        System.out.println("passed area checks=3");

        try {
            new Circle(0.0);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid circle rejected");
        }
        try {
            new Rectangle(Double.NaN, 2.0);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid rectangle rejected");
        }
        try {
            new RightTriangle(3.0, Double.POSITIVE_INFINITY);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid triangle rejected");
        }
        try {
            area(null);
        } catch (NullPointerException ex) {
            System.out.println("null area rejected=" + ex.getMessage());
        }
    }
}
```

Biên dịch và chạy bằng **JDK 21+** (không cần preview flag):

```bash
javac --release 21 -encoding UTF-8 -Xlint:all -Werror SealedShapeDemo.java
java SealedShapeDemo
```

**Stdout chính xác sau khi chạy:**

```text
circle r=2.0 | area=12.57 | perimeter=12.57
rectangle | area=12.00 | perimeter=14.00
right triangle | area=6.00 | perimeter=12.00
unit circle
square rectangle
isosceles right triangle
missing
circle>=2: true
passed area checks=3
invalid circle rejected
invalid rectangle rejected
invalid triangle rejected
null area rejected=shape
```

Chương trình được biên dịch thành công bằng `javac --release 21 -Xlint:all -Werror`, chạy thực tế và cho đúng **13 dòng stdout** như trên. Dùng `Locale.ROOT` trong `printf` giúp cách viết số thập phân có dấu chấm nhất quán, không phụ thuộc locale mặc định của hệ thống.

### Giải thích từng nhóm kết quả

- Ba dòng đầu: tính cả **diện tích và chu vi** của `Circle(2.0)`, `Rectangle(3.0,4.0)`, `RightTriangle(3.0,4.0)`; số liệu được làm tròn hai chữ số thập phân khi in, không làm tròn dữ liệu nội bộ.
- `unit circle`, `square rectangle` và `isosceles right triangle`: xác nhận các guard `when` cho nhóm hình đặc biệt được chọn **trước** case tổng quát.
- `missing`: `kind(null)` đi vào `case null`.
- `circle>=2: true`: `instanceof Circle(double radius)` kết hợp `&&`.
- `passed area checks=3`: ba phép so sánh `assertClose` cho diện tích hợp lệ đều qua ngưỡng sai số `1e-9` trên dữ liệu thử đã chọn.
- Ba dòng `invalid ... rejected`: compact constructor từ chối các giá trị `0.0`, `NaN`, `Infinity`. Trong unit test sản phẩm nên dùng `assertThrows` để đảm bảo một test **thất bại nếu ngoại lệ không xảy ra**, thay vì chỉ in ở `catch` như minh họa ở đây.
- `null area rejected=shape`: hàm `area` từ chối selector null bằng `Objects.requireNonNull` với thông điệp `shape`.

**Ghi chú về kiểm thử số thực:** `assertClose` trong demo phù hợp với ba giá trị nhỏ và hữu hạn được thử. Nếu tính toán có thể trả `NaN` hoặc `Infinity`, cần kiểm tra `Double.isFinite(actual)` hoặc thiết kế assertion riêng, vì so sánh `Math.abs(NaN - expected) > epsilon` không tự tạo lỗi. Một thư viện hình học thực tế nên dùng chiến lược so sánh ổn định và test giá trị cực trị.

## 10. Điều gì xảy ra khi thêm một loại Shape mới?

Giả sử sản phẩm cần hỗ trợ **hình bình hành**:

```java
record Parallelogram(double base, double height, double side)
        implements Shape {}
```

Dòng trên chỉ là một phác thảo: trước hết cần **cập nhật `permits`** của `Shape` để cho phép subtype mới, rồi bổ sung validation tương ứng. Nếu không có nó trong `permits`, Java không cho `Parallelogram implements Shape`.

Sau khi thêm subtype mới, các switch expression như `area`, `perimeter` và `kind` không còn xử lý đủ biến thể. Compiler Java 21 có thể báo lỗi:

```text
error: the switch expression does not cover all possible input values
```

Để kiểm chứng độc lập, xét một phiên bản nhỏ **cố ý thiếu case RightTriangle**. Lưu thành `MissingShapeCase.java` nếu muốn xem lỗi:

```java
public class MissingShapeCase {
    sealed interface Shape permits Circle, Rectangle, RightTriangle {}
    record Circle(double r) implements Shape {}
    record Rectangle(double w, double h) implements Shape {}
    record RightTriangle(double a, double b) implements Shape {}

    static double area(Shape s) {
        return switch (s) {
            case Circle(var r) -> Math.PI * r * r;
            case Rectangle(var w, var h) -> w * h;
        };
    }
}
```

Biên dịch:

```bash
javac --release 21 -encoding UTF-8 MissingShapeCase.java
```

`javac` đã được thử với mã này và từ chối:

```text
error: the switch expression does not cover all possible input values
1 error
```

Đây là **compiler error**, không phải cảnh báo. `-Xlint` hay `-Werror` không phải nguyên nhân; mã chưa thỏa quy tắc `switch expression` exhaustive.

### Cách sửa khi mở rộng domain

1. Xác định kiểu mới là một phần của miền hình học được hỗ trợ; cập nhật `permits` có chủ đích.
2. Bổ sung invariant cho các tham số mới.
3. Thêm case tính diện tích, chu vi và phân loại với công thức nghiệp vụ chính xác.
4. Viết test cho hình mới, bao gồm đầu vào hợp lệ, không hợp lệ, vùng biên và `null` nếu có.
5. Biên dịch lại trên mức Java đã cam kết; **không thêm `default -> 0` chỉ để che lỗi không exhaustive**.
6. Xác minh các case có guard vẫn đứng trước case rộng để tránh `dominated case`.

**Điểm cần hiểu:** `sealed` đóng các **subtype trực tiếp**. Nếu một subtype được khai báo `non-sealed`, chính nhánh đó có thể cho phép mở rộng sâu hơn; trong khi các record của bài đều `final` nên cây subtype thực sự đóng tại ba lá. Việc dùng `non-sealed` nên là quyết định kiến trúc có lý do, không phải cách né bảo trì exhaustive switches.

## 11. So sánh với thiết kế không sealed và polymorphism

### Một interface Shape không sealed

```java
interface Shape {
    double area();
}
```

Thiết kế đó cho phép nhiều implementation tùy ý (theo các ràng buộc visibility/module thông thường). Đó là ưu điểm khi thư viện cần extensibility qua plugin. Nhưng khi viết một `switch` bên ngoài trên một hierarchy mở, compiler thường **không thể biết mọi loại Shape sẽ tồn tại**, nên không thể xác minh exhaustive chỉ từ ba record ban đầu.

### Đưa behavior vào từng subtype

Một hướng khác là polymorphism cổ điển:

```java
interface Shape {
    double area();
    double perimeter();
}
```

Trong hướng này, `Circle` tự triển khai công thức của nó, `Rectangle` tự triển khai, và code gọi `shape.area()`. Không cần switch mỗi lần tính toán.

**Chọn cách nào?**

| Tiêu chí | Sealed Shape + pattern switch | Interface + polymorphism |
| --- | --- | --- |
| Tập biến thể | Đóng hoặc giới hạn có chủ đích | Có thể mở cho implementation mới |
| Thêm một thao tác mới | Viết switch/service mới, không nhất thiết sửa các record | Thường thêm method vào interface và sửa implementation |
| Thêm một loại hình | Cập nhật permits/case, compiler hỗ trợ phát hiện thiếu nhánh | Thêm implementation mới cho hợp đồng interface |
| Logic hình học | Tập trung theo thao tác `area`/`perimeter` | Phân tán theo từng loại hình |
| Compiler kiểm tra toàn bộ subtype | Có lợi khi hierarchy thực sự đóng | Không suy luận toàn bộ implementation tương lai |
| Phù hợp | Domain model đóng, DSL, AST, rule engine | Domain mở, plugin API, subtype có hành vi riêng |

Không có thiết kế nào mặc nhiên tốt hơn trong mọi ứng dụng. Nếu ưu tiên **thêm thao tác** trên một nhóm biến thể ổn định, sealed + pattern switch dễ mở rộng theo chiều hành vi. Nếu ưu tiên **thêm loại hình mới** bởi nhiều module bên ngoài, polymorphism có thể hợp lý hơn.

### Visitor là một lựa chọn thứ ba

Với sealed model nhiều biến thể, **Visitor pattern** có thể tách thao tác thành interface `Visitor<R>` và dùng `accept` để dispatch. Visitor hữu ích khi đã có hệ thống khách hàng dùng Visitor hoặc muốn đóng gói thuật toán thành đối tượng có trạng thái. Tuy nhiên, với ba record đơn giản và Java 21, pattern switch có thể ít boilerplate hơn.

## 12. Debugging thường gặp với sealed Shape

### Lỗi khi triển khai Shape không nằm trong permits

Nếu tạo:

```java
// Đoạn minh họa SAI nếu Ellipse không nằm trong Shape permits:
// record Ellipse(double a, double b) implements Shape {}
```

compiler từ chối vì subtype trực tiếp không được cho phép. Đúng cách là xác định có thực sự cần `Ellipse` trong domain không, cập nhật `permits` và thuật toán liên quan, rồi kiểm tra lỗi compile thiếu case.

### Lỗi dominated case

```java
// SAI: nhánh tổng quát che nhánh có guard.
return switch (shape) {
    case Circle(double r) -> "circle";
    case Circle(double r) when r == 1.0 -> "unit circle";
    case Rectangle(double w, double h) -> "rectangle";
    case RightTriangle(double a, double b) -> "right triangle";
};
```

Nhánh `Circle(double r)` tổng quát đã bao phủ mọi `Circle` nên case `when r == 1.0` phía sau không thể được chọn. Đặt case guard trước case tổng quát như `kind` trong chương trình chính.

### NPE do selector null

Nếu dùng `switch(shape)` mà không có `case null`, selector null gây `NullPointerException` trong pattern switch Java 21. Chọn xử lý rõ như `kind` hoặc từ chối bằng `Objects.requireNonNull` như `area`.

### Sai công thức tam giác

Hai cạnh bất kỳ của một tam giác thường **không đủ** để xác định diện tích và chu vi. `RightTriangle` ở đây có ý nghĩa hình học cụ thể: `legA` và `legB` là **cạnh góc vuông**, nên dùng được công thức `a*b/2` và `Math.hypot(a,b)`. Nếu muốn hỗ trợ tam giác bất kỳ, cần mô hình ba cạnh hoặc thông tin khác đủ để xác định hình và kiểm tra bất đẳng thức tam giác.

### Tràn số thực hoặc kết quả không hữu hạn

Một constructor chỉ kiểm tra các cạnh hữu hạn dương nhưng không giới hạn độ lớn vẫn có thể cho phép giá trị làm `area` hoặc `perimeter` trả `Infinity`. Nếu điều đó không chấp nhận được với domain thực tế, cần định nghĩa phạm vi kích thước, xử lý số học phù hợp và test biên.

### Nhầm equals/hashCode của record với “cùng loại hình”

`Circle(2.0)` và `Circle(2.0)` có thể bằng nhau theo `record.equals`; nhưng một `Rectangle` có diện tích bằng `Circle` **không** trở thành cùng một record hay cùng một hình. Equality của record phản ánh **giá trị các component và kiểu record**, không có nghĩa “diện tích bằng nhau”.

## 13. Quy trình kiểm thử domain model

Một bộ test nên kết hợp **kiểm tra dữ liệu**, **kiểm tra công thức** và **kiểm tra phân nhánh**:

| Nhóm test | Ví dụ đầu vào | Điều cần xác nhận |
| --- | --- | --- |
| Hình hợp lệ | `Circle(2)`, `Rectangle(3,4)`, `RightTriangle(3,4)` | Công thức đúng |
| Guard đặc biệt | `Circle(1)`, `Rectangle(2,2)`, `RightTriangle(3,3)` | Case `when` đúng được chọn |
| Guard không thỏa | `Circle(2)`, `Rectangle(3,4)`, `RightTriangle(3,4)` | Case chung chạy đúng |
| Giá trị bằng 0 | `Circle(0)` | Constructor từ chối |
| Giá trị âm | `Rectangle(-1,2)` | Constructor từ chối |
| NaN | `Rectangle(NaN,2)` | Constructor từ chối |
| Infinity | `RightTriangle(3,+Infinity)` | Constructor từ chối |
| Null selector | `area(null)`, `kind(null)` | Một bên ném lỗi có chủ đích, một bên trả `missing` |
| Bổ sung subtype | Thêm một record vào `permits` | Compiler yêu cầu cập nhật các switch không exhaustive |
| Số thực rất lớn | Kích thước tiến gần miền tối đa | Kiểm tra chính sách overflow/precision |

Trong JUnit có thể dùng `assertEquals(expected, actual, delta)` cho kết quả `double` và `assertThrows(IllegalArgumentException.class, ...)` cho các constructor bất hợp lệ. Khi viết test thực tế, không nên chỉ xem stdout; phải có **assert** để test thất bại khi kết quả không đúng.

### Property tests hữu ích

Ngoài kết quả mẫu, có thể xác nhận:

- **Tính dương:** với kích thước hợp lệ trong miền số học của hệ thống, diện tích và chu vi phải dương.
- **Đổi chỗ hai cạnh hình chữ nhật:** `area(Rectangle(w,h)) == area(Rectangle(h,w))` trong giới hạn sai số cho phép.
- **Đổi chỗ hai cạnh góc vuông:** `perimeter(RightTriangle(a,b))` bằng kết quả với `(b,a)` trong độ chính xác chấp nhận được.
- **Tính đồng nhất của phép tỉ lệ:** nếu nhân mọi kích thước với `k > 0` và không tràn số, chu vi tỉ lệ theo `k`, diện tích tỉ lệ theo `k*k`.
- **Test compile-time:** thêm subtype trong một nguồn test phụ để xác nhận switch thiếu case bị từ chối, nhưng không đưa nguồn cố ý lỗi vào module production.

## 14. Bài tập tự luyện

**Bài 1.** Vì sao `sealed interface Shape` trong bài có thể dùng `switch expression` không cần `default`?

*Đáp án:* Vì các subtype trực tiếp được giới hạn ở `Circle`, `Rectangle`, `RightTriangle` và cả ba record đều là các lớp cuối. Mỗi giá trị `Shape` khác null đều thuộc một trong ba case.

**Bài 2.** Khi thêm `record Ellipse(double a,double b) implements Shape`, bước đầu tiên cần làm gì?

*Đáp án:* Xác định nó thuộc domain, cập nhật `permits` của `Shape`, áp đặt validation cho hai bán trục, rồi bổ sung những case xử lý đầy đủ (diện tích, chu vi nếu có công thức/thuật toán phù hợp và chính sách sai số, phân loại) cùng test. Không chỉ thêm một record rồi bỏ qua compiler error.

**Bài 3.** Vì sao `case Circle(double r) when r == 1.0` phải đặt trước `case Circle(double r)`?

*Đáp án:* Nhánh Circle không guard khớp mọi Circle, sẽ che nhánh chỉ xử lý bán kính 1 nếu đứng trước. Java có thể báo lỗi dominance ngay lúc biên dịch.

**Bài 4.** `kind(null)` và `area(null)` khác nhau ra sao trong ví dụ?

*Đáp án:* `kind(null)` trả `missing` bởi `case null`; `area(null)` cố ý ném `NullPointerException` bởi `Objects.requireNonNull(shape,"shape")`. Đây là hai hợp đồng nghiệp vụ riêng.

**Bài 5.** Vì sao dùng `Math.hypot(legA,legB)` cho `RightTriangle`?

*Đáp án:* Hai trường của record là hai cạnh góc vuông, nên cạnh huyền bằng `sqrt(a²+b²)`; `Math.hypot` hỗ trợ tính toán ổn định hơn cho nhiều trường hợp so với công thức bình phương thủ công.

**Bài 6.** Trong `area`, có nên dùng `default -> 0` để khỏi sửa mã khi thêm hình mới?

*Đáp án:* Không nên nếu mô hình là closed domain và mỗi loại hình phải có công thức đúng. `default` rộng có thể che việc bỏ sót subtype mới; thêm case cụ thể giúp compiler và test phát hiện thiếu hành vi.

**Bài 7.** Dùng JDK 17 đã có `sealed` và `record`; có thể chạy nguyên chương trình bài này không?

*Đáp án:* Không. Chương trình dùng **record patterns**, **pattern switch** và `when` final từ Java 21. Nếu dự án phải giữ Java 17, cần triển khai tính toán bằng polymorphism hoặc `instanceof` type patterns với accessor, không copy nguyên cú pháp Java 21.

**Bài 8.** Nếu một hình có bán kính `1e308` nhưng constructor chỉ kiểm tra `isFinite` và dương, có an toàn để dùng diện tích không?

*Đáp án:* Không được bảo đảm. Bán kính hữu hạn nhưng `r*r` sẽ tràn `double` thành `Infinity`. Domain thật cần giới hạn phạm vi hoặc dùng chính sách số học phù hợp và có test tràn.

## 15. Tài liệu chính thức

- [JEP 409 – Sealed Classes (final trong Java 17)](https://openjdk.org/jeps/409)
- [JEP 395 – Records (final trong Java 16)](https://openjdk.org/jeps/395)
- [JEP 440 – Record Patterns (final trong Java 21)](https://openjdk.org/jeps/440)
- [JEP 441 – Pattern Matching for switch (final trong Java 21)](https://openjdk.org/jeps/441)
- [Oracle Java 21 – Sealed Classes and Interfaces](https://docs.oracle.com/en/java/javase/21/language/sealed-classes-and-interfaces.html)
- [Oracle Java 21 – Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Oracle Java 21 – Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [JLS Java 21 `8.1.1.2 – sealed/final/non-sealed class modifiers](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.1.1.2)
- [JLS Java 21 `9.1.1.4 – sealed interfaces](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.1.1.4)
- [JLS Java 21 `14.11 – Switch statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
