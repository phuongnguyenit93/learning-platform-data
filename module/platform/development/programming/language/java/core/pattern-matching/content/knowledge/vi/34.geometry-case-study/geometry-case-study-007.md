# Dùng guard cho hình có điều kiện trong Java 21

## 1. Mục tiêu và bối cảnh

Trong **Case study hình học**, không phải lúc nào ta chỉ cần phân loại một giá trị là hình tròn, hình chữ nhật hay tam giác. Nhiều yêu cầu còn phụ thuộc **điều kiện hình học**: bán kính phải dương, hình chữ nhật có phải hình vuông hay hình rộng, ba cạnh có tạo thành tam giác hợp lệ, tam giác thuộc loại đều/cân/thường, hoặc các giá trị số có phải hữu hạn.

Java 21 hỗ trợ pattern matching for `switch` với **guard `when`**. Guard cho phép diễn đạt “đối tượng có cấu trúc này **và** đáp ứng điều kiện bổ sung” bằng một `case` rõ nghĩa. Khi kết hợp **sealed hierarchy**, **record patterns**, và một thứ tự `case` hợp lý, mã có thể vừa type-safe vừa dễ review.

Sau bài này, bạn có thể:

- Dùng `case Circle(double radius) when ...`, `case Rectangle(double width, double height) when ...`, `case Triangle(double a, double b, double c) when ...` trong `switch expression` Java 21.
- Tách **khớp kiểu/cấu trúc** ra khỏi **guard đúng/sai**; hiểu rằng guard chỉ được đánh giá sau khi pattern match.
- Sắp các điều kiện từ **kiểm tra hợp lệ → trường hợp đặc biệt → trường hợp chung**, tránh nhánh bị che (*dominance*) hoặc fallback không đúng.
- Định nghĩa rõ việc xử lý `null`, kích thước âm/0, `NaN`, `Infinity`, tỷ lệ hình, điều kiện tam giác và ranh giới số học.
- Biên dịch/chạy một ví dụ Java 21 độc lập gồm ba loại hình, **22 test cases** so với expected độc lập, đồng thời biết cách kiểm tra những mẫu compile-time sai.
- Phân biệt guard trong `switch` với `instanceof` kết hợp `&&` và với các phương thức nghiệp vụ có tên.

**Phiên bản:** `switch` pattern matching và record patterns chính thức ở **Java 21** (JEP 441, JEP 440), không cần `--enable-preview`. Type pattern `instanceof T t` đã chính thức từ Java 16 (JEP 394); không dùng `when` sau `instanceof`.

## 2. Mô hình hình học và hợp đồng phân loại

Định nghĩa một phân cấp hình học đóng:

```java
sealed interface Shape permits Circle, Rectangle, Triangle {}

record Circle(double radius) implements Shape {}
record Rectangle(double width, double height) implements Shape {}
record Triangle(double a, double b, double c) implements Shape {}
```

Đây là **khai báo minh họa**; ở chương trình đầy đủ mục 6, các kiểu được đặt bên trong một public class để chỉ cần một tệp Java.

- `sealed Shape` giới hạn các subtype trực tiếp được phép: `Circle`, `Rectangle`, `Triangle`.
- `record` tự tạo constructor, component accessors và hành vi giá trị cơ bản; **record constructor mặc định không tự xác nhận tính hợp lệ hình học**.
- `double` có thể nhận `NaN` hoặc vô cực; `new Circle(-2.0)` hay `new Triangle(1, 2, 3)` **vẫn được tạo** trong mô hình này.
- Vì vậy, việc shape có **đúng Java type** chưa đồng nghĩa với shape **hợp lệ theo hình học**.

Chính sách phân loại giả định cho bài học:

| Kiểu | Điều kiện | Nhãn trả về |
|---|---|---|
| Không có shape | `shape == null` | `MISSING` |
| Circle | Bán kính không phải số hữu hạn dương | `INVALID_CIRCLE` |
| Circle | Bán kính hữu hạn dương và `radius >= 10` | `LARGE_CIRCLE` |
| Circle | Bán kính hữu hạn dương dưới 10 | `CIRCLE` |
| Rectangle | Width hoặc height không hữu hạn dương | `INVALID_RECTANGLE` |
| Rectangle | Hai cạnh hợp lệ, `width == height` | `SQUARE` |
| Rectangle | Hợp lệ, không vuông, `width / height >= 2` | `WIDE_RECTANGLE` |
| Rectangle | Hợp lệ, không thuộc hai nhóm trên | `RECTANGLE` |
| Triangle | Cạnh không hữu hạn dương hoặc vi phạm bất đẳng thức tam giác nghiêm ngặt | `INVALID_TRIANGLE` |
| Triangle | Hợp lệ và `a == b == c` | `EQUILATERAL_TRIANGLE` |
| Triangle | Hợp lệ, có ít nhất hai cạnh bằng nhau | `ISOSCELES_TRIANGLE` |
| Triangle | Hợp lệ, ba cạnh khác nhau | `SCALENE_TRIANGLE` |

Đây là **quy tắc demo**, không phải tiêu chuẩn chung bắt buộc cho mọi thư viện hình học. Ví dụ, ngưỡng “hình tròn lớn” bằng 10 là một giả định; dự án thật phải định nghĩa đơn vị đo, tolerance và độ chính xác riêng.

Mục tiêu của case study là làm rõ: **guard có thể chắt lọc một kiểu record thành nhiều nhánh có điều kiện** mà không cần tạo subtype cho mọi trường hợp như `Square`, `WideRectangle`, `InvalidCircle`.

## 3. Cú pháp guard trong switch

Một guarded case có dạng:

```java
case Pattern p when booleanExpression -> result;
```

Trong ví dụ:

```java
case Circle(double radius) when radius >= 10.0 -> "LARGE_CIRCLE";
```

**Trình tự thực thi:**

1. Selector của `switch` được đánh giá.
2. Pattern `Circle(double radius)` được kiểm tra: đối tượng có phải Circle (khác null) và component `radius` có thể deconstruct không?
3. Nếu pattern khớp, biến `radius` có scope trong biểu thức guard `when`.
4. Guard `radius >= 10.0` trả `true` thì nhánh được chọn; nếu `false` thì xét các case tiếp theo.
5. Nếu pattern không khớp, guard **không được đánh giá**.

Nên hiểu một guarded case như **“pattern match AND guard true”**, nhưng guard và pattern là **hai giai đoạn**. Điều này giúp phân biệt một hình đúng loại nhưng thiếu điều kiện với một hình sai loại hoàn toàn.

Ví dụ:

```java
return switch (shape) {
    case null -> "MISSING";
    case Circle(double radius) when radius >= 10.0 -> "LARGE_CIRCLE";
    case Circle(double radius) -> "CIRCLE";
    // Các kiểu Shape khác cũng cần được xử lý nếu switch expression
    // phải exhaustive, chẳng hạn Rectangle và Triangle.
};
```

**Đây là snippet cố ý chưa exhaustive** nếu `Shape` còn Rectangle/Triangle, nên không được dùng như chương trình chạy độc lập. Chương trình ở mục 6 cung cấp đủ nhánh và đã được biên dịch.

## 4. Định nghĩa các predicate hình học an toàn

### 4.1. Số hữu hạn dương

Một kích thước hợp lệ trong demo phải thỏa:

```java
static boolean positiveFinite(double value) {
    return Double.isFinite(value) && value > 0.0;
}
```

Giải thích:

- `Double.isFinite(value)` loại trừ `NaN`, `Double.POSITIVE_INFINITY` và `Double.NEGATIVE_INFINITY`.
- `value > 0.0` loại `0.0`, `-0.0`, giá trị âm.
- Một so sánh như `value <= 0.0` **không phát hiện được `NaN`**, vì các phép so sánh thứ tự với NaN trả false.
- Hệ thống đo đạc thực tế có thể muốn ràng buộc cả giá trị tối đa hoặc đơn vị; hãy áp dụng bổ sung ở boundary nếu có yêu cầu.

Nếu không kiểm tra `isFinite`, ví dụ `Double.POSITIVE_INFINITY >= 10.0` trả true và một bán kính vô hạn có thể bị dán nhãn `LARGE_CIRCLE` dù policy nói chỉ chấp nhận bán kính hữu hạn.

### 4.2. Bất đẳng thức tam giác

Với ba cạnh `a`, `b`, `c`, kiểm tra:

```java
static boolean validTriangle(double a, double b, double c) {
    return positiveFinite(a) && positiveFinite(b) && positiveFinite(c)
            && a + b > c && a + c > b && b + c > a;
}
```

Các điều kiện là **nghiêm ngặt**: `1, 2, 3` không tạo thành tam giác có diện tích dương; trường hợp suy biến bị coi là invalid.

Vì Java dùng `double`, hãy nhớ phép cộng có thể bị ảnh hưởng bởi làm tròn hoặc overflow thành infinity trong những trường hợp cực trị. Với **dữ liệu số đo thực tế** cần chính sách chính xác/tolerance và có thể dùng dạng kiểm tra đã được phân tích số học kỹ hơn hoặc một representation decimal phù hợp. Bài này chỉ kiểm thử các giá trị tiêu biểu và không tuyên bố giải quyết mọi vấn đề computational geometry.

Một guard điều kiện tam giác có thể viết:

```java
case Triangle(double a, double b, double c)
        when !validTriangle(a, b, c) -> "INVALID_TRIANGLE";
```

Tách thành phương thức có tên giúp code ngắn **vì ý nghĩa rõ hơn**, không phải cố nhét sáu phép so sánh vào một `when`.

### 4.3. Hình vuông và hình chữ nhật rộng

Với Rectangle đã hợp lệ:

```java
case Rectangle(double width, double height)
        when width == height -> "SQUARE";
case Rectangle(double width, double height)
        when width / height >= 2.0 -> "WIDE_RECTANGLE";
case Rectangle(double width, double height) -> "RECTANGLE";
```

**Thứ tự mang tính chính sách:**

- Điều kiện `width == height` được xét trước để nhận diện SQUARE.
- Điều kiện “rộng” lấy **tỷ số chiều rộng/chiều cao từ 2 trở lên**; tại `width=4`, `height=2`, nhãn là WIDE_RECTANGLE.
- Nhánh không guard là fallback cho Rectangle hợp lệ còn lại, ví dụ `3×2` hoặc `2×5`.

Tỷ số chỉ được đánh giá **sau** nhánh INVALID_RECTANGLE trong chương trình đầy đủ, nên `height > 0` và hữu hạn. Điều này tránh chia cho 0 và giảm rủi ro đưa dữ liệu không hợp lệ vào phân loại. Tuy nhiên chia `double` có thể cho Infinity nếu tỷ lệ quá lớn dù cả hai kích thước hữu hạn; nếu domain yêu cầu tránh overflow của tỷ số, cần chính sách số học riêng.

Cũng cần làm rõ: so sánh `width == height` là so sánh `double` **chính xác**, phù hợp với số literal trong demo. Với số đo hoặc số tính toán, việc dùng exact equality hay gần bằng phải được domain quy định; không tự gắn một epsilon tùy ý.

## 5. Thiết kế thứ tự case để điều kiện rõ ràng

Guarded switch không chỉ là cú pháp. Nó biểu đạt **một thứ tự ưu tiên**. Một thứ tự hữu ích cho từng loại hình là:

1. **Kiểm tra hình có dữ liệu hợp lệ** để phân loại invalid trước.
2. **Xử lý trường hợp hẹp nhất** như hình tròn lớn, hình vuông, tam giác đều.
3. **Xử lý trường hợp ít đặc biệt hơn** như hình chữ nhật rộng hoặc tam giác cân.
4. **Nhánh không guard cùng kiểu** nhận mọi trường hợp còn lại.
5. **Không thêm `default` vô cớ** nếu sealed hierarchy đã được xử lý exhaustive.

Ví dụ cho Circle:

```java
case Circle(double radius) when !positiveFinite(radius)
        -> "INVALID_CIRCLE";
case Circle(double radius) when radius >= 10.0
        -> "LARGE_CIRCLE";
case Circle(double radius) -> "CIRCLE";
```

Nếu đảo nhánh `case Circle(double radius) -> "CIRCLE";` lên trước, các nhánh Circle có guard phía sau bị **dominated** theo quy tắc Java 21 và có thể làm code không biên dịch. Compiler giúp phát hiện lỗi thứ tự cơ bản này.

Với Triangle, thứ tự cũng bảo vệ ý nghĩa:

```java
case Triangle(double a, double b, double c)
        when !validTriangle(a, b, c) -> "INVALID_TRIANGLE";
case Triangle(double a, double b, double c)
        when a == b && b == c -> "EQUILATERAL_TRIANGLE";
case Triangle(double a, double b, double c)
        when a == b || b == c || a == c -> "ISOSCELES_TRIANGLE";
case Triangle(double a, double b, double c)
        -> "SCALENE_TRIANGLE";
```

Tam giác đều cũng đáp ứng điều kiện “có ít nhất hai cạnh bằng nhau”. Nếu xét nhánh cân trước, tam giác đều sẽ được dán nhãn cân, dù chương trình vẫn có thể biên dịch: **compiler không chứng minh toàn bộ quan hệ đại số giữa hai guard này để buộc lỗi**. Vì thế **test nghiệp vụ và code review** vẫn cần thiết.

## 6. Chương trình Java 21 độc lập, đã kiểm chứng

Lưu toàn bộ mã dưới tên **`GeometryGuardDemo.java`**. Bài dùng sealed interface và ba record lồng trong public class. Không cần thư viện ngoài.

```java
import java.util.Objects;

public class GeometryGuardDemo {
    sealed interface Shape permits Circle, Rectangle, Triangle {}
    record Circle(double radius) implements Shape {}
    record Rectangle(double width, double height) implements Shape {}
    record Triangle(double a, double b, double c) implements Shape {}

    static boolean positiveFinite(double value) {
        return Double.isFinite(value) && value > 0.0;
    }

    static boolean validTriangle(double a, double b, double c) {
        return positiveFinite(a) && positiveFinite(b) && positiveFinite(c)
                && a + b > c && a + c > b && b + c > a;
    }

    static String classify(Shape shape) {
        return switch (shape) {
            case null -> "MISSING";

            case Circle(double radius) when !positiveFinite(radius)
                    -> "INVALID_CIRCLE";
            case Circle(double radius) when radius >= 10.0
                    -> "LARGE_CIRCLE";
            case Circle(double radius) -> "CIRCLE";

            case Rectangle(double width, double height)
                    when !positiveFinite(width) || !positiveFinite(height)
                    -> "INVALID_RECTANGLE";
            case Rectangle(double width, double height)
                    when width == height -> "SQUARE";
            case Rectangle(double width, double height)
                    when width / height >= 2.0 -> "WIDE_RECTANGLE";
            case Rectangle(double width, double height) -> "RECTANGLE";

            case Triangle(double a, double b, double c)
                    when !validTriangle(a, b, c) -> "INVALID_TRIANGLE";
            case Triangle(double a, double b, double c)
                    when a == b && b == c -> "EQUILATERAL_TRIANGLE";
            case Triangle(double a, double b, double c)
                    when a == b || b == c || a == c -> "ISOSCELES_TRIANGLE";
            case Triangle(double a, double b, double c)
                    -> "SCALENE_TRIANGLE";
        };
    }

    // Doi chung if/else: khong dung guarded switch, nhung van co
    // instanceof type pattern de lay bien dung kieu.
    static String withoutPatterns(Shape shape) {
        if (shape == null) return "MISSING";
        if (shape instanceof Circle circle) {
            double radius = circle.radius();
            if (!positiveFinite(radius)) return "INVALID_CIRCLE";
            if (radius >= 10.0) return "LARGE_CIRCLE";
            return "CIRCLE";
        }
        if (shape instanceof Rectangle rectangle) {
            double width = rectangle.width();
            double height = rectangle.height();
            if (!positiveFinite(width) || !positiveFinite(height)) {
                return "INVALID_RECTANGLE";
            }
            if (width == height) return "SQUARE";
            if (width / height >= 2.0) return "WIDE_RECTANGLE";
            return "RECTANGLE";
        }
        Triangle triangle = (Triangle) shape;
        double a = triangle.a();
        double b = triangle.b();
        double c = triangle.c();
        if (!validTriangle(a, b, c)) return "INVALID_TRIANGLE";
        if (a == b && b == c) return "EQUILATERAL_TRIANGLE";
        if (a == b || b == c || a == c) return "ISOSCELES_TRIANGLE";
        return "SCALENE_TRIANGLE";
    }

    static void test(String label, Shape shape, String expected) {
        String actual = classify(shape);
        String oldStyle = withoutPatterns(shape);
        if (!Objects.equals(expected, actual)
                || !Objects.equals(expected, oldStyle)) {
            throw new AssertionError(label + ": expected=" + expected
                    + ", guard=" + actual + ", ordinary=" + oldStyle);
        }
        System.out.println(label + " => " + actual);
    }

    public static void main(String[] args) {
        test("null", null, "MISSING");
        test("circle zero", new Circle(0.0), "INVALID_CIRCLE");
        test("circle negative", new Circle(-1.0), "INVALID_CIRCLE");
        test("circle NaN", new Circle(Double.NaN), "INVALID_CIRCLE");
        test("circle infinity", new Circle(Double.POSITIVE_INFINITY),
                "INVALID_CIRCLE");
        test("circle small", new Circle(9.5), "CIRCLE");
        test("circle threshold", new Circle(10.0), "LARGE_CIRCLE");
        test("circle large", new Circle(12.0), "LARGE_CIRCLE");

        test("rectangle zero", new Rectangle(0.0, 2.0),
                "INVALID_RECTANGLE");
        test("rectangle NaN", new Rectangle(2.0, Double.NaN),
                "INVALID_RECTANGLE");
        test("rectangle square", new Rectangle(3.0, 3.0), "SQUARE");
        test("rectangle wide boundary", new Rectangle(4.0, 2.0),
                "WIDE_RECTANGLE");
        test("rectangle wide", new Rectangle(5.0, 2.0),
                "WIDE_RECTANGLE");
        test("rectangle ordinary", new Rectangle(3.0, 2.0), "RECTANGLE");
        test("rectangle tall", new Rectangle(2.0, 5.0), "RECTANGLE");

        test("triangle degenerate", new Triangle(1.0, 2.0, 3.0),
                "INVALID_TRIANGLE");
        test("triangle negative", new Triangle(-3.0, 4.0, 5.0),
                "INVALID_TRIANGLE");
        test("triangle infinity",
                new Triangle(Double.POSITIVE_INFINITY, 3.0, 3.0),
                "INVALID_TRIANGLE");
        test("triangle equilateral", new Triangle(3.0, 3.0, 3.0),
                "EQUILATERAL_TRIANGLE");
        test("triangle isosceles", new Triangle(4.0, 4.0, 5.0),
                "ISOSCELES_TRIANGLE");
        test("triangle scalene", new Triangle(3.0, 4.0, 5.0),
                "SCALENE_TRIANGLE");
        test("triangle NaN", new Triangle(Double.NaN, 2.0, 3.0),
                "INVALID_TRIANGLE");
    }
}
```

Trong phương thức có tên `withoutPatterns`, phần “không dùng pattern” được hiểu là **không dùng record patterns kèm `when` trong `switch`**; nó **vẫn sử dụng type patterns của `instanceof`** cho Circle/Rectangle và một cast thủ công cho Triangle. Tên phương thức ở đây được giữ để đối chiếu với kết quả chạy kiểm thử; nếu đưa vào production, nên đặt tên rõ nghĩa hơn, chẳng hạn `classifyImperatively`.

### Cách chạy

Với JDK 21 trở lên:

```bash
javac --release 21 GeometryGuardDemo.java
java GeometryGuardDemo
```

**Stdout chính xác đã được kiểm tra:**

```text
null => MISSING
circle zero => INVALID_CIRCLE
circle negative => INVALID_CIRCLE
circle NaN => INVALID_CIRCLE
circle infinity => INVALID_CIRCLE
circle small => CIRCLE
circle threshold => LARGE_CIRCLE
circle large => LARGE_CIRCLE
rectangle zero => INVALID_RECTANGLE
rectangle NaN => INVALID_RECTANGLE
rectangle square => SQUARE
rectangle wide boundary => WIDE_RECTANGLE
rectangle wide => WIDE_RECTANGLE
rectangle ordinary => RECTANGLE
rectangle tall => RECTANGLE
triangle degenerate => INVALID_TRIANGLE
triangle negative => INVALID_TRIANGLE
triangle infinity => INVALID_TRIANGLE
triangle equilateral => EQUILATERAL_TRIANGLE
triangle isosceles => ISOSCELES_TRIANGLE
triangle scalene => SCALENE_TRIANGLE
triangle NaN => INVALID_TRIANGLE
```

Tổng cộng có **22 test cases**. Mỗi lượt kiểm tra so đồng thời:

1. Kết quả guarded switch `classify(shape)`.
2. Kết quả đối chứng if/else `withoutPatterns(shape)`.
3. Chuỗi expected **được ghi rõ từ hợp đồng phân loại**, không chỉ so hai cách triển khai với nhau.

Nếu sai một trong ba, chương trình ném `AssertionError`. Điều này cho phép đánh giá **tính tương đương hành vi** của guarded switch và cách phân loại tuần tự, nhưng không tuyên bố đã bao phủ mọi số thực/biến thể đầu vào trong ứng dụng thực tế.

## 7. Đọc từng kết quả theo thứ tự guard

### 7.1. Circle: kiểm tra bất hợp lệ trước kích thước lớn

Xét:

```java
case Circle(double radius) when !positiveFinite(radius)
        -> "INVALID_CIRCLE";
case Circle(double radius) when radius >= 10.0
        -> "LARGE_CIRCLE";
case Circle(double radius) -> "CIRCLE";
```

- `Circle(0.0)` và `Circle(-1.0)`: guard bất hợp lệ đúng → `INVALID_CIRCLE`.
- `Circle(Double.NaN)`: `Double.isFinite` false → `INVALID_CIRCLE`. Nếu bỏ kiểm tra hữu hạn và chỉ dùng `radius <= 0`, NaN **không được nhận là nhỏ hơn hoặc bằng 0**.
- `Circle(Double.POSITIVE_INFINITY)`: bị loại trước khi xét `radius >= 10`.
- `Circle(9.5)`: hợp lệ, không lớn → `CIRCLE`.
- `Circle(10.0)`: đúng tại biên và được nhận là `LARGE_CIRCLE`.

Đây là lý do bài test cần cả **dưới ngưỡng**, **bằng ngưỡng**, **trên ngưỡng**, **NaN**, **Infinity**. Nếu chỉ thử bán kính 5 và 12, không phát hiện được lỗi khi người viết thay `>= 10` bằng `> 10`.

### 7.2. Rectangle: invalid, square, wide, ordinary

Xét:

```java
case Rectangle(double width, double height)
        when !positiveFinite(width) || !positiveFinite(height)
        -> "INVALID_RECTANGLE";
case Rectangle(double width, double height)
        when width == height -> "SQUARE";
case Rectangle(double width, double height)
        when width / height >= 2.0 -> "WIDE_RECTANGLE";
case Rectangle(double width, double height) -> "RECTANGLE";
```

- `Rectangle(0, 2)`: invalid; tránh phân loại như rectangle hợp lệ.
- `Rectangle(3, 3)`: square; guard wide không được xét tiếp sau khi chọn nhánh.
- `Rectangle(4, 2)`: tỷ số đúng bằng 2 → wide, vì policy dùng `>= 2.0`.
- `Rectangle(5, 2)`: wide.
- `Rectangle(3, 2)`: thông thường, tỷ số 1.5.
- `Rectangle(2, 5)`: thông thường, vì chính sách wide phụ thuộc **width/height**, không phụ thuộc cạnh nào dài hơn.

**Chính sách về hướng cạnh:** “rộng” có nghĩa chiều ngang dài gấp ít nhất hai lần chiều cao. Nếu domain muốn xét tỷ lệ cạnh lớn nhất/cạnh nhỏ nhất, cần viết lại predicate và bổ sung test cho trường hợp hình cao; **đó là thay đổi nghiệp vụ**, không phải chỉ format guard.

### 7.3. Triangle: invalid trước, đều trước cân

Xét:

```java
case Triangle(double a, double b, double c)
        when !validTriangle(a, b, c) -> "INVALID_TRIANGLE";
case Triangle(double a, double b, double c)
        when a == b && b == c -> "EQUILATERAL_TRIANGLE";
case Triangle(double a, double b, double c)
        when a == b || b == c || a == c -> "ISOSCELES_TRIANGLE";
case Triangle(double a, double b, double c) -> "SCALENE_TRIANGLE";
```

- `Triangle(1,2,3)`: suy biến vì `1 + 2 == 3`; không thỏa điều kiện nghiêm ngặt `>`.
- `Triangle(3,3,3)`: đều, nên chọn EQUILATERAL trước.
- `Triangle(4,4,5)`: cân nhưng không đều.
- `Triangle(3,4,5)`: thường.
- Cạnh âm, NaN, Infinity: invalid dù ba biến đều có kiểu `double` hợp lệ đối với Java.

**Điểm dễ sai:** điều kiện “hai cạnh bằng nhau” sẽ **cũng đúng cho tam giác đều**. Nếu đặt guarded case cân trước case đều, Java thường không báo dominance cho quan hệ logic giữa hai guard; lỗi thể hiện ở **kết quả phân loại**. Đây là lý do test `Triangle(3,3,3)` cực kỳ quan trọng.

## 8. Guard trong switch và && của instanceof khác nhau thế nào?

Trong `switch` Java 21:

```java
case Rectangle(double width, double height)
        when width == height -> "SQUARE";
```

Ở đây `when` nối **pattern của nhãn case** với một boolean condition. Dùng `when` giúp xét nhiều trường hợp cùng record type trong một `switch`.

Khi dùng `instanceof`, ta không viết `when` sau pattern. Dạng đúng là:

```java
if (shape instanceof Rectangle(double width, double height)
        && width == height) {
    System.out.println("square");
}
```

Dạng **cố ý sai**:

```java
// Không hợp lệ trong Java 21:
if (shape instanceof Rectangle(double width, double height)
        when width == height) {
    System.out.println("square");
}
```

`javac --release 21` **từ chối** cú pháp `when` ở biểu thức `instanceof`; trong Java 21, `when` là guard của pattern `case` trong `switch`.

Đồng thời, `&&` có đặc tính short-circuit: nếu pattern `Rectangle(...)` không khớp, vế sau không được chạy và các biến pattern không được sử dụng trái scope. Nếu vế sau là một lời gọi có khả năng ném exception, cần giữ guard kiểm tra non-null hoặc điều kiện hợp lệ cần thiết trước lời gọi đó.

**Khác biệt về mục tiêu:** `instanceof` phù hợp một nhánh kiểm tra đơn giản. Guarded `switch` phù hợp khi có **nhiều trường hợp cùng kiểu nhưng điều kiện khác nhau**, hoặc nhiều biến thể trong một sealed hierarchy.

## 9. Vì sao không có default trong chương trình đầy đủ?

`Shape` là một `sealed interface` chỉ cho phép ba subtype trực tiếp Circle, Rectangle, Triangle. Trong `switch expression` ở mục 6, ta có:

- `case null` để nêu rõ chính sách selector null.
- Các guarded cases và **một unguarded record pattern** cuối cùng cho mỗi subtype.
- Không có `default` bao trùm.

Compiler có thể chứng minh các record patterns không guard bao phủ toàn bộ các giá trị khác null của ba subtype có component primitive. Khi **thêm một permitted subtype** như `Polygon` và biên dịch lại, compiler có thể yêu cầu bổ sung cách xử lý kiểu mới.

Nếu thêm:

```java
default -> "UNKNOWN";
```

một cách vô cớ, ta có thể làm mất lợi ích **exhaustiveness checking**: kiểu hình mới có thể âm thầm bị đưa vào nhánh UNKNOWN. Dùng default là hợp lý khi domain **cố tình định nghĩa fallback** cho tập kiểu mở, chẳng hạn selector có kiểu `Object` hoặc một API nhận input ngoài phạm vi hình học.

**Lưu ý:** record pattern trong Java 21 có các quy tắc liên quan component null và tính exhaustive không nên suy đoán máy móc. Ví dụ này dùng component `double` primitive để đơn giản hóa. Nếu record chứa nested reference record, một nested pattern có thể không khớp khi component là null, dù root object thuộc subtype đó; cần có fallback tương ứng.

### Null trong pattern switch

Một selector `null` **không** tự động đi vào `default` thông thường. Vì chính sách demo muốn trả `MISSING` nên khai báo:

```java
case null -> "MISSING";
```

Đối chiếu với biểu thức `shape instanceof Circle c`: nếu `shape == null`, `instanceof` trả false. Null trong `switch` và `instanceof` không nên được xử lý như cùng một cú pháp.

## 10. Những lỗi Java compiler có thể phát hiện

### 10.1. Đặt case tổng quát trước case có guard

**Sai:**

```java
return switch (shape) {
    case Rectangle rectangle -> "ANY";
    case Rectangle(double width, double height)
            when width == height -> "SQUARE";
    // Các nhánh khác...
};
```

Cấu trúc này được minh họa để thấy thứ tự, **không phải một switch expression đầy đủ**. `javac --release 21` từ chối nhánh SQUARE vì `case Rectangle rectangle` đã bao phủ mọi Rectangle khác null: guarded case phía sau là **dominated case label**.

**Sửa:** đặt các nhánh hẹp/guarded trước, `case Rectangle...` không guard sau cùng. Ví dụ đầy đủ trong mục 6 thể hiện thứ tự này.

### 10.2. Thiếu nhánh exhaustive

Nếu chỉ xử lý Circle và Rectangle mà quên Triangle trong một `switch expression` trên `Shape`, compiler có thể báo expression không exhaustive. Không dùng `default` chỉ để làm build xanh; hãy thêm nhánh Triangle theo chính sách.

### 10.3. Dùng sai kiểu component pattern

Nếu `record Circle(double radius)`, pattern `Circle(String radius)` không applicable tại component `double`. Đó là **lỗi compile time**, không phải “Circle hiện tại không khớp String” ở runtime.

### 10.4. Dùng biến pattern ngoài nơi được bind

Biến `width` của `case Rectangle(double width, double height)` chỉ có phạm vi thích hợp trong guard và phần thân nhánh được chọn. Không thể tự ý dùng nó ở một case Circle hoặc sau switch như biến local đã khai báo trước.

### 10.5. Dùng bản Java thấp hơn 21

Guard `when` trong pattern switch và record patterns như các ví dụ ở đây được chuẩn hóa ở Java 21. Nếu project build bằng `--release 17` không bật preview theo đúng giai đoạn, ví dụ sẽ không biên dịch. Không nhầm cú pháp này với type pattern `instanceof` đã chính thức từ Java 16.

## 11. Những sai lầm nghiệp vụ/compiler không tự bắt được

### 11.1. Guard kiểm tra số hợp lệ đặt sau điều kiện kích thước

`Double.POSITIVE_INFINITY >= 10.0` là true. Nếu xét nhánh LARGE_CIRCLE trước INVALID_CIRCLE, một hình tròn có bán kính vô hạn bị phân loại sai.

Cách phòng: **validity guard trước, threshold guard sau**; có test NaN/Infinity.

### 11.2. Đổi dấu >= thành >

Với `Circle(10.0)` hoặc `Rectangle(4.0,2.0)`, đổi `>=` thành `>` làm thay đổi nhãn. Những mốc biên phải xuất hiện trong test độc lập, không chỉ test ví dụ “rõ ràng lớn” và “rõ ràng nhỏ”.

### 11.3. Nhận tam giác cân trước tam giác đều

Khi dùng `a == b || b == c || a == c` trước `a == b && b == c`, tam giác đều có thể bị phân loại thành cân. Vì các guard là boolean expressions có ý nghĩa nghiệp vụ, compiler không thay review và test để suy luận thứ tự mong muốn.

### 11.4. Quên phân biệt số thực và số nguyên

`double` không mang nghĩa “độ dài chính xác”. Kết quả so sánh bằng nhau có thể bị ảnh hưởng bởi dữ liệu đo hoặc các phép tính. Nếu policy yêu cầu “gần vuông”, hãy đặt tên và định nghĩa một predicate `approximatelyEqual` với tolerance dựa theo quy mô và miền dữ liệu, đồng thời kiểm tra quanh biên. Không thay `==` bằng epsilon bất kỳ mà không xác định yêu cầu.

### 11.5. Lạm dụng guard dài

Guard có quá nhiều logic tạo khó khăn khi đọc, test và bảo trì. `validTriangle(a,b,c)` là ví dụ tách một **quy tắc có tên**. Tuy nhiên cũng không nên chia thành helper một dòng vô nghĩa cho mọi dấu so sánh; mục tiêu là làm rõ ý định.

### 11.6. Đưa side effect vào guard

Ví dụ `when chargeCreditCard() && ...` hoặc `when logAndChangeState(...)` có thể khiến hành vi phụ thuộc thứ tự đánh giá, số lần xét case và exception. Guard nên **thuần, ngắn và dự đoán được** khi có thể. Nếu một thao tác thực sự thay đổi trạng thái, hãy làm rõ nó trong phần thân nhánh hoặc service phù hợp.

### 11.7. Nhầm “không match guard” với “sai shape type”

`Rectangle(3,2)` là Rectangle hợp lệ nhưng không thỏa guard square/wide, nên nhánh RECTANGLE tổng quát được chọn. Đây là **hành vi đúng**, không phải record pattern không match. Cần phân biệt *root type match* và *guard false* khi debug.

## 12. So sánh viết if/else và guarded switch

Ở mục 6, phương thức đối chứng dùng:

```java
if (shape instanceof Circle circle) {
    double radius = circle.radius();
    if (!positiveFinite(radius)) return "INVALID_CIRCLE";
    if (radius >= 10.0) return "LARGE_CIRCLE";
    return "CIRCLE";
}
```

Đây là trích đoạn của phương thức đối chứng: nó **vẫn dùng instanceof type pattern**, chỉ không dùng guarded switch/record deconstruction. Nó phù hợp khi chỉ xử lý một kiểu và có vài điều kiện, hoặc khi cần dùng source level khác.

Guarded switch:

```java
case Circle(double radius) when !positiveFinite(radius)
        -> "INVALID_CIRCLE";
case Circle(double radius) when radius >= 10.0
        -> "LARGE_CIRCLE";
case Circle(double radius) -> "CIRCLE";
```

phù hợp khi tập hình đóng gồm nhiều loại và mỗi loại có những tình huống con. Điều giá trị không nằm ở số dòng ít hơn mà là:

- Các nhánh loại hình có thể đọc như một **bảng quyết định**.
- Compiler đảm bảo kiểu của biến trong mỗi guard.
- Có thể loại bỏ cast thủ công.
- Với sealed hierarchy và unguarded fallback cho từng subtype, có thể tận dụng exhaustive checking.
- Mỗi nhánh có thể được test bằng input/expected độc lập.

Tuy nhiên, khi guard dài và lồng nhau phức tạp, một method domain như `rectangle.isSquare()` hoặc `triangle.isValid()` đôi khi dễ hiểu hơn. Đừng dùng `switch` chỉ để rút ngắn code.

## 13. Ma trận kiểm thử theo loại điều kiện

Để reviewer thấy rõ “điều kiện nào khiến nhánh được chọn”, nên có test matrix:

| Ca | Input | Nhãn mong đợi | Mục đích |
|---|---|---|---|
| Null root | `null` | MISSING | `case null` |
| Circle zero | `Circle(0)` | INVALID_CIRCLE | Biên giá trị bằng 0 |
| Circle NaN | `Circle(NaN)` | INVALID_CIRCLE | Phân loại số không hợp lệ |
| Circle Infinity | `Circle(+Inf)` | INVALID_CIRCLE | Chặn threshold guard sai |
| Circle small | `Circle(9.5)` | CIRCLE | Dưới ngưỡng |
| Circle threshold | `Circle(10)` | LARGE_CIRCLE | `>=` gồm điểm biên |
| Rectangle zero | `Rectangle(0,2)` | INVALID_RECTANGLE | Guard kiểm tra kích thước |
| Rectangle square | `Rectangle(3,3)` | SQUARE | Guard square trước |
| Rectangle wide boundary | `Rectangle(4,2)` | WIDE_RECTANGLE | Tỷ số bằng đúng 2 |
| Rectangle ordinary | `Rectangle(3,2)` | RECTANGLE | Nhánh không guard |
| Rectangle tall | `Rectangle(2,5)` | RECTANGLE | Hướng width/height |
| Triangle degenerate | `Triangle(1,2,3)` | INVALID_TRIANGLE | Bất đẳng thức nghiêm ngặt |
| Triangle equilateral | `Triangle(3,3,3)` | EQUILATERAL_TRIANGLE | Ưu tiên đều |
| Triangle isosceles | `Triangle(4,4,5)` | ISOSCELES_TRIANGLE | Cân nhưng không đều |
| Triangle scalene | `Triangle(3,4,5)` | SCALENE_TRIANGLE | Còn lại hợp lệ |

Chương trình mục 6 triển khai thêm nhiều ca âm/NaN/Infinity/normal để tổng số là 22. **Một tập test không bao giờ thay thế được việc xác định chính sách số học**, nhưng các ca biên có tên giúp nhìn thấy lỗi guard rõ hơn.

### Gợi ý kiểm thử tự động trong dự án

Với JUnit 5, mỗi input có thể được đưa vào `@ParameterizedTest` kèm một expected label. Cần có cả assertion về không ném exception bất ngờ ở dữ liệu invalid. Cũng nên test trường hợp có subtype mới nếu team sở hữu sealed hierarchy, để bảo vệ cách sử dụng exhaustive switch.

Đừng chỉ so hai implementation với nhau: cả hai có thể cùng chứa một lỗi logic. Chương trình đã sử dụng **expected độc lập** để tránh rủi ro đó.

## 14. Checklist review guard cho hình học

1. **Hình và kiểu:** selector là interface/class/record nào? Có đúng Java 21 cho record pattern/guard không?
2. **Root null:** muốn xử lý riêng hay chấp nhận exception? Nếu muốn riêng, khai báo `case null`.
3. **Validation:** các kích thước là hữu hạn dương chưa? Có chặn NaN, Infinity, 0 và âm không?
4. **Thứ tự:** invalid trước special, special trước general; Triangle đều trước Triangle cân.
5. **Short-circuit:** có kiểm tra điều kiện an toàn trước khi chia hoặc gọi method không?
6. **Boundary:** dấu `>=`, `>`, `==` đã khớp chính sách tại điểm ngưỡng chưa?
7. **Tính exhaustive:** sealed hierarchy có unguarded case cho mỗi subtype không? Có tránh default thừa làm che biến thể mới?
8. **Nhánh bị che:** đã đặt case tổng quát sau case có guard chưa?
9. **Độ chính xác:** đơn vị và tolerance của `double` đã được quy định chưa?
10. **Thuần tính:** guard có side effects, logging nhạy cảm, exceptions hoặc truy cập dữ liệu ngoài không cần thiết không?
11. **Đọc dễ hiểu:** predicate phức tạp có tên như `validTriangle` chưa?
12. **Test:** đủ valid/invalid, NaN/Infinity, hai bên ngưỡng, dữ liệu suy biến và fallback không guard chưa?
13. **Version:** đã chạy đúng `javac --release 21` và JVM phù hợp chưa?
14. **Review thay đổi:** có vô tình thay chính sách hình học khi refactor từ `if/else` sang `switch` không?

## 15. Bài tập tự kiểm tra

### Bài A — Biên bán kính

Đoán kết quả với:

```java
new Circle(9.99)
new Circle(10.0)
new Circle(Double.NaN)
```

**Đáp án:** lần lượt CIRCLE, LARGE_CIRCLE, INVALID_CIRCLE. Ngưỡng có `>=`; NaN bị chặn bởi `isFinite` trước.

### Bài B — Trật tự Triangle

Một bạn viết:

```java
case Triangle(double a, double b, double c)
        when a == b || b == c || a == c -> "ISOSCELES_TRIANGLE";
case Triangle(double a, double b, double c)
        when a == b && b == c -> "EQUILATERAL_TRIANGLE";
```

Chương trình có thể biên dịch nhưng phân loại `Triangle(3,3,3)` thế nào?

**Đáp án:** ISOSCELES_TRIANGLE do nhánh đầu tiên có guard true đã được chọn. Phải đảo lại hai nhánh, và đặt guard validation ở trước cả hai để không nhận một tam giác vô hiệu.

### Bài C — Hình chữ nhật ở tỷ số biên

Nếu input `Rectangle(4,2)` thì output nào?

**Đáp án:** WIDE_RECTANGLE; `4 / 2 == 2` và policy là `>= 2.0`. Nếu `Rectangle(2,4)` thì RECTANGLE vì width/height chỉ bằng 0.5.

### Bài D — Sai chỗ của khi dùng when

Một bạn viết:

```java
if (shape instanceof Circle(double radius) when radius >= 10) {
    // ...
}
```

Có hợp lệ trong Java 21 không?

**Đáp án:** Không. `when` chỉ được dùng trong guarded `case` của pattern `switch`, không phải là toán tử của `instanceof`. Dùng:

```java
if (shape instanceof Circle(double radius) && radius >= 10) {
    // ...
}
```

### Bài E — Case bị dominated

Vì sao không đặt `case Rectangle r -> ...` trước `case Rectangle(double w, double h) when w == h -> ...`?

**Đáp án:** Case Rectangle tổng quát bao phủ mọi Rectangle không null, nên nhánh sau không thể tới được; Java 21 báo dominated case label.

### Bài F — Bổ sung hình mới

Nếu thêm `record Polygon(...) implements Shape` và cập nhật `permits`, tại sao không nên vội thêm `default -> "UNKNOWN"`?

**Đáp án:** Nếu domain cần phân loại Polygon riêng, `default` có thể che việc cần cập nhật. Hãy đưa một case Polygon theo chính sách thực tế vào switch để giữ lợi ích exhaustiveness.

### Bài G — Điều kiện không phải chỉ type checking

Vì sao `new Circle(-1)` vẫn compile mặc dù được phân loại INVALID_CIRCLE?

**Đáp án:** Type checking chỉ xác nhận một `double` hợp lệ về mặt ngôn ngữ. Điều kiện bán kính dương là invariant thuộc domain. Có thể bảo vệ ngay trong record constructor nếu ứng dụng muốn **không cho phép tạo** hình không hợp lệ; nhưng khi đó chương trình kiểm thử cần thay đổi chính sách vì các input invalid có thể ném exception tại constructor.

## 16. Mở rộng hợp lý trong dự án thật

- **Validate tại constructor:** nếu domain không chấp nhận hình không hợp lệ tồn tại, viết compact constructor kiểm tra kích thước. Khi đó nhánh INVALID có thể không còn cần thiết với dữ liệu nội bộ đã xác thực, nhưng input từ ngoài vẫn cần error mapping rõ ràng.
- **Bộ đo chuẩn:** nếu dữ liệu từ API với đơn vị khác nhau, chuẩn hóa về một đơn vị trước khi xét threshold; không để `when` đoán ngầm.
- **Tolerance cho double:** nếu tính toán hình học dựa trên số đo, xem xét gần bằng với tolerance phù hợp độ lớn và nghiệp vụ, thay vì đòi chính xác nhị phân.
- **Tách policy:** ngưỡng bán kính và tỷ số wide có thể là tham số cấu hình, không hardcode trong nhiều nhánh.
- **Phép toán diện tích/chu vi:** có thể bổ sung phương thức domain riêng; không nên gộp đồng thời mọi công thức tính toán và logic phân loại vào một guarded switch khổng lồ.
- **Quan sát lỗi:** ghi rõ “invalid dimension”, “degenerate triangle” tại boundary hoặc layer chẩn đoán nếu cần, nhưng tránh side effects trong guard.
- **Bộ regression tests:** khi thêm subtype vào sealed hierarchy, biên dịch lại và rà soát mọi switch exhaustive; test từng biến thể.

Cần giữ sự phân biệt giữa ba vấn đề: **Java có biết kiểu shape không**, **hình có hợp lệ theo chính sách không**, và **nhánh phân loại có đúng ưu tiên không**. Guard giải quyết vấn đề thứ hai và thứ ba, trong khi pattern matching xử lý cấu trúc và kiểu.

## Kết luận

**Dùng guard cho hình có điều kiện** là một cách tự nhiên để biểu đạt các nhánh hình học trong Java 21: pattern nhận diện loại hình và bind các component; `when` bổ sung điều kiện như kích thước hữu hạn dương, ngưỡng bán kính, hình vuông, tỷ số hình rộng hoặc tam giác cân/đều.

Hãy viết các case theo thứ tự **invalid → đặc biệt nhất → đặc biệt hơn → fallback cùng kiểu**. Giữ guard ngắn, dùng helper có tên cho điều kiện hình học, xử lý `null` rõ ràng, hiểu các giới hạn của `double` và kiểm thử biên. Với sealed hierarchy và các nhánh không guard bao phủ từng loại, compiler còn giúp theo dõi những subtype mới thay vì che chúng bằng một `default` thừa.

## Tài liệu tham khảo chính thức

- [JEP 441 — Pattern Matching for switch (JDK 21)](https://openjdk.org/jeps/441)
- [JEP 440 — Record Patterns (JDK 21)](https://openjdk.org/jeps/440)
- [JEP 409 — Sealed Classes (JDK 17)](https://openjdk.org/jeps/409)
- [JEP 394 — Pattern Matching for instanceof (JDK 16)](https://openjdk.org/jeps/394)
- [Java Language Specification SE 21 — Switch Statements §14.11](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Java Language Specification SE 21 — Patterns §14.30](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [Oracle Java SE 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Oracle Java SE 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
