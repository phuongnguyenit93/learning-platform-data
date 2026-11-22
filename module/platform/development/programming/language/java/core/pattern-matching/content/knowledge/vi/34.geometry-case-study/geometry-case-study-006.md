# Thêm subtype mới và compiler feedback — Case study hình học (Java 21)

## 1. Vấn đề thực tế: một hình mới làm thay đổi nhiều phép xử lý

Giả sử ứng dụng hình học ban đầu chỉ nhận **hình tròn (Circle)** và **hình chữ nhật (Rectangle)**. Mã sử dụng một `sealed interface Shape` và các `switch expression` để tính diện tích, chu vi hoặc phân loại hình. Sau một thời gian, sản phẩm cần hỗ trợ thêm **tam giác (Triangle)**.

Trong Java 21, đây là một cơ hội tốt để sử dụng **compiler feedback** làm hàng rào bảo trì: khi thêm một subtype vào sealed hierarchy, những pattern `switch` chưa xử lý subtype mới có thể **báo lỗi ngay lúc biên dịch**, thay vì âm thầm rơi vào một nhánh không mong muốn lúc chạy.

Bài học theo dõi trọn vòng thay đổi:

1. Bắt đầu với `Shape` có hai subtype: `Circle` và `Rectangle`.
2. Bổ sung `Triangle` vào `permits` nhưng **cố ý chưa cập nhật các `switch`**.
3. Đọc chẩn đoán `javac` về **non-exhaustive switch**.
4. Thêm các `case Triangle(...)` cho tính diện tích, chu vi, phân loại.
5. Đọc một chẩn đoán khác về **case dominance** khi sắp guard sai.
6. Hoàn thiện chương trình Java 21, chạy **13 phép kiểm thử**, đánh giá điều compiler bảo đảm và điều phải kiểm thử nghiệp vụ.

**Phiên bản:** `sealed classes/interfaces` chính thức từ Java 17 (JEP 409). **Record patterns** (JEP 440) và **pattern matching cho `switch`** (JEP 441) chính thức từ **Java 21**, nên mọi ví dụ có `case Circle(double r)` hoặc guard `when` cần JDK 21 trở lên, không cần `--enable-preview`.

**Mục tiêu:** Biết thêm subtype mà vẫn bảo toàn đúng hành vi, dùng chẩn đoán của compiler như checklist thay đổi, viết pattern `switch` exhaustive, nhận diện lỗi dominated, xây test cho subtype mới và hiểu giới hạn của compile-time exhaustiveness.

## 2. Mô hình ban đầu: Shape chỉ có Circle và Rectangle

Ta chọn `record` vì đây là các value objects mang dữ liệu hình học đơn giản, và chọn `sealed interface` để kiểm soát tập subtype.

```text
Shape (sealed interface)
├── Circle(radius)           record, final
└── Rectangle(width, height) record, final
```

Khai báo ngắn gọn:

```java
// Đoạn minh họa mô hình trước khi mở rộng.
// Các declaration cần đặt cùng phạm vi class/package phù hợp.
sealed interface Shape permits Circle, Rectangle {}

record Circle(double radius) implements Shape {}
record Rectangle(double width, double height) implements Shape {}
```

Một switch expression tính diện tích:

```java
// Đoạn minh họa: shape có kiểu Shape trong một phương thức.
return switch (shape) {
    case Circle(double radius) -> Math.PI * radius * radius;
    case Rectangle(double width, double height) -> width * height;
};
```

Hai `case` cùng nhau bao phủ các subtype đã được khai báo. Java 21 có thể chứng minh `switch` **exhaustive** mà không cần `default`, vì các direct permitted subtype đều là record, tức các kiểu `final`; không có nhánh con mở rộng phía sau.

Tương tự, chu vi có thể được viết:

```java
return switch (shape) {
    case Circle(double r) -> 2.0 * Math.PI * r;
    case Rectangle(double w, double h) -> 2.0 * (w + h);
};
```

**Vì sao không cần `default`?** Trong hệ thống này, chúng ta **muốn compiler cảnh báo bằng lỗi** nếu một subtype hình học mới xuất hiện nhưng một phép xử lý chưa được cập nhật. Việc không thêm `default` là quyết định thiết kế chủ ý, không phải thiếu sót.

Cần phân biệt: Compiler chỉ biết các kiểu có thể xuất hiện. Nó **không biết** công thức `Math.PI*r*r` có đúng với nghiệp vụ hay không và không tự kiểm tra bán kính > 0.

## 3. Yêu cầu mới: thêm tam giác

Sản phẩm cần một tam giác tổng quát với ba cạnh `a`, `b`, `c`. Ta mở rộng mô hình:

```text
Shape (sealed interface)
├── Circle(radius)
├── Rectangle(width, height)
└── Triangle(a, b, c)   <-- subtype mới
```

Hai thay đổi đầu tiên:

```java
// Đoạn minh họa trạng thái SAU KHI thêm subtype, TRƯỚC
// KHI cập nhật các switch trong code cũ.
sealed interface Shape permits Circle, Rectangle, Triangle {}

record Circle(double radius) implements Shape {}
record Rectangle(double width, double height) implements Shape {}
record Triangle(double a, double b, double c) implements Shape {}
```

Khi sử dụng `permits` tường minh, phải thêm `Triangle` vào danh sách direct permitted subtypes. Vì `Triangle` là `record`, kiểu này mặc nhiên `final` và hợp lệ làm subtype của một sealed interface.

**Đừng sửa ngay mọi nơi bằng `default`:** Hãy để IDE/build chạy `javac` để biết các nơi dựa vào tập subtype cũ. Với domain có nhiều phương thức phân loại, những lỗi compiler này chính là một **danh sách các điểm cần review**.

Một điều cần thiết khác: Tam giác phải có dữ liệu hợp lệ. Ba cạnh dương bất kỳ **chưa chắc** tạo được tam giác; điều kiện cần theo bất đẳng thức tam giác là:

\[
a+b>c,\qquad a+c>b,\qquad b+c>a.
\]

Ở bước phát hiện compile error, ta có thể dùng khai báo record đơn giản như trên. Trước khi đưa vào sản phẩm, hãy thêm validation trong constructor; chương trình hoàn chỉnh ở phần 7 sẽ thực hiện việc đó.

## 4. Compiler feedback số 1: switch expression không exhaustive

Sau khi cập nhật `Shape permits ... Triangle` mà **giữ nguyên** công thức diện tích của hai hình cũ:

```java
// CỐ Ý THIẾU Triangle — không phải code hoàn chỉnh.
static double area(Shape shape) {
    return switch (shape) {
        case Circle(double radius) ->
            Math.PI * radius * radius;
        case Rectangle(double width, double height) ->
            width * height;
    };
}
```

Đối với Java 21, `Shape` nay có ba subtype có thể khớp. Hai `case` chỉ bao phủ `Circle` và `Rectangle`. Khi biên dịch lại, `javac` có thể báo:

```text
error: the switch expression does not cover all possible input values
```

Đây là **error**, không phải warning. Compiler từ chối biểu thức vì cần một giá trị kết quả với mọi selector hợp lệ, nhưng `Triangle` chưa có nhánh xử lý.

### Điều compiler đang nói

- `Shape` là kiểu selector tĩnh.
- `Triangle` là subtype được phép tồn tại của `Shape`.
- Không có case type/record pattern nào ở switch cũ bao phủ `Triangle`.
- Không có `default` hoặc pattern rộng có thể nhận nó.
- Vì vậy không thể xác nhận exhaustiveness.

**Sửa đúng:** Thêm case cụ thể cho `Triangle` và tính diện tích theo yêu cầu. Đừng lẩn tránh bằng cách dùng `default -> 0`, vì diện tích bằng 0 cho một tam giác hợp lệ là lỗi nghiệp vụ bị che khuất.

### Công thức diện tích cho Triangle(a, b, c)

Vì record chứa **độ dài ba cạnh**, không phải tọa độ đỉnh hoặc chiều cao, công thức phù hợp là công thức Heron:

\[
s=\frac{a+b+c}{2},\qquad
S=\sqrt{s(s-a)(s-b)(s-c)}.
\]

Một case có block và `yield`:

```java
case Triangle(double a, double b, double c) -> {
    double s = (a + b + c) / 2.0;
    yield Math.sqrt(s * (s - a) * (s - b) * (s - c));
}
```

`yield` trả giá trị từ nhánh block của **switch expression**. Nó không phải `return` của method bao quanh. Cần phân biệt với `break` của switch statement.

Ví dụ tam giác 3–4–5:

\[
s=6,\qquad S=\sqrt{6\cdot3\cdot2\cdot1}=6.
\]

**Lưu ý số học:** Với `double` cực lớn hoặc tam giác gần suy biến, phép tính Heron đơn giản có thể gặp overflow/underflow hoặc mất chính xác. Công thức ở đây phù hợp để dạy pattern matching và thử với đầu vào nhỏ; hệ thống hình học chính xác cao cần thuật toán ổn định số học và miền giá trị được định nghĩa rõ.

## 5. Compiler feedback số 2: enhanced switch statement cũng có thể không exhaustive

Không chỉ `switch expression` mới cần được cập nhật. Trong Java 21, một **enhanced switch statement** có pattern labels cũng được yêu cầu exhaustive.

Ví dụ một phương thức chỉ in loại hình:

```java
// CỐ Ý THIẾU Triangle.
static void printShape(Shape shape) {
    switch (shape) {
        case Circle(double r) ->
            System.out.println("circle");
        case Rectangle(double w, double h) ->
            System.out.println("rectangle");
    }
}
```

Với hierarchy sau khi thêm `Triangle`, compiler có thể báo:

```text
error: the switch statement does not cover all possible input values
```

Cách sửa là thêm `case Triangle(...)` hoặc một nhánh bao phủ thích hợp theo contract.

**Phân biệt quan trọng:** Một số `switch statement` truyền thống chỉ dùng constant case labels có quy tắc khác về tính exhaustive. Không áp dụng suy luận “statement không cần default” cho enhanced switch với pattern labels.

**Khi codebase lớn:** Có thể có nhiều switch trên cùng `Shape` ở các lớp mapping, tính giá, định dạng báo cáo, xuất JSON, phân loại UI, v.v. Mỗi switch có ngữ nghĩa riêng. Các compile errors sau khi thêm subtype là tín hiệu để **review từng operation**, không nên tự động thêm một nhánh `Triangle -> "other"` cho tất cả.

## 6. Compiler feedback số 3: case bị dominated khi đặt guard sai

Yêu cầu mới còn muốn phân loại tam giác:
- Ba cạnh bằng nhau: `EQUILATERAL`.
- Có đúng hai cạnh bằng nhau: `ISOSCELES`.
- Ba cạnh khác nhau: `TRIANGLE`.

Một người mới có thể viết:

```java
// CỐ Ý SAI THỨ TỰ trong cùng switch:
case Triangle(double a, double b, double c) -> "TRIANGLE";
case Triangle(double a, double b, double c)
    when a == b && b == c -> "EQUILATERAL";
```

Case `Triangle` **không guard** nằm trước, đã bao phủ mọi `Triangle`. Vì vậy case có guard phía sau không thể được chọn. `javac` có thể phát ra:

```text
error: this case label is dominated by a preceding case label
```

**Cách sửa:** Đặt nhánh có điều kiện cụ thể trước, nhánh tổng quát sau:

```java
// Các case minh họa trong switch trên Shape:
case Triangle(double a, double b, double c)
    when a == b && b == c -> "EQUILATERAL";
case Triangle(double a, double b, double c)
    when a == b || b == c || a == c -> "ISOSCELES";
case Triangle(double a, double b, double c) -> "TRIANGLE";
```

Với tam giác đều, điều kiện isosceles cũng đúng, nên **case đều phải đứng trước case cân** để đáp ứng kết quả mong muốn. Nếu guard thứ nhất `false`, Java mới xét tiếp các case phù hợp.

Ở đây các cạnh là các giá trị `double` được nhập trực tiếp như 2.0, 3.0, 5.0; so sánh `==` minh họa phân loại theo **bằng nhau chính xác**. Với số đo hình học qua phép tính thực nghiệm, cần quy định tolerance/cách so sánh và test tương ứng; không tự dùng một epsilon tùy ý thay cho yêu cầu nghiệp vụ.

### Dominance không phải “lỗi hiệu năng”

Một case bị dominated là lỗi về **khả năng khớp / thứ tự lựa chọn nhánh**, không phải compiler cảnh báo rằng code có thể chậm. Sửa bằng cách xem quan hệ bao phủ của pattern/guard, **không** dùng ép kiểu, preview flag hoặc tắt warning.

## 7. Chương trình Java 21 hoàn chỉnh sau khi thêm Triangle

Tạo file **`GeometrySubtypeEvolutionDemo.java`**. Chương trình dưới đây có:
- Sealed hierarchy gồm ba record.
- Validation cạnh dương hữu hạn, bất đẳng thức tam giác.
- `area` và `perimeter` dùng exhaustive switch expressions, không có `default`.
- `kind` có ba guard/case cho tam giác và `case null`.
- Bộ kiểm thử nhỏ **13 ca** dựa trên expected values và expected exceptions.

```java
import java.util.Locale;

public class GeometrySubtypeEvolutionDemo {
    sealed interface Shape permits Circle, Rectangle, Triangle {}

    static void requirePositive(String field, double value) {
        if (!Double.isFinite(value) || value <= 0) {
            throw new IllegalArgumentException(
                field + " must be finite and positive");
        }
    }

    record Circle(double radius) implements Shape {
        Circle {
            requirePositive("radius", radius);
        }
    }

    record Rectangle(double width, double height) implements Shape {
        Rectangle {
            requirePositive("width", width);
            requirePositive("height", height);
        }
    }

    record Triangle(double a, double b, double c) implements Shape {
        Triangle {
            requirePositive("a", a);
            requirePositive("b", b);
            requirePositive("c", c);
            if (a + b <= c || a + c <= b || b + c <= a) {
                throw new IllegalArgumentException(
                    "triangle inequality violated");
            }
        }
    }

    static double area(Shape shape) {
        return switch (shape) {
            case Circle(double r) -> Math.PI * r * r;
            case Rectangle(double w, double h) -> w * h;
            case Triangle(double a, double b, double c) -> {
                double s = (a + b + c) / 2.0;
                yield Math.sqrt(s * (s - a) * (s - b) * (s - c));
            }
        };
    }

    static double perimeter(Shape shape) {
        return switch (shape) {
            case Circle(double r) -> 2.0 * Math.PI * r;
            case Rectangle(double w, double h) -> 2.0 * (w + h);
            case Triangle(double a, double b, double c) -> a + b + c;
        };
    }

    static String kind(Shape shape) {
        return switch (shape) {
            case Circle(double r) -> "CIRCLE";
            case Rectangle(double w, double h) -> "RECTANGLE";
            case Triangle(double a, double b, double c)
                when a == b && b == c -> "EQUILATERAL";
            case Triangle(double a, double b, double c)
                when a == b || b == c || a == c -> "ISOSCELES";
            case Triangle(double a, double b, double c) -> "TRIANGLE";
            case null -> "NONE";
        };
    }

    static int passed;

    static void expectClose(String name, double expected, double actual) {
        if (!Double.isFinite(actual)
                || Math.abs(expected - actual) > 1e-9) {
            throw new AssertionError(
                name + ": expected " + expected + ", got " + actual);
        }
        passed++;
        System.out.println("PASS " + name);
    }

    static void expectText(String name, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                name + ": expected " + expected + ", got " + actual);
        }
        passed++;
        System.out.println("PASS " + name);
    }

    static void expectIllegalArgument(String name, Runnable action) {
        try {
            action.run();
        } catch (IllegalArgumentException expected) {
            passed++;
            System.out.println("PASS " + name);
            return;
        }
        throw new AssertionError(
            name + ": expected IllegalArgumentException");
    }

    static void expectNullPointer(String name, Runnable action) {
        try {
            action.run();
        } catch (NullPointerException expected) {
            passed++;
            System.out.println("PASS " + name);
            return;
        }
        throw new AssertionError(
            name + ": expected NullPointerException");
    }

    public static void main(String[] args) {
        Shape circle = new Circle(2);
        Shape rectangle = new Rectangle(3, 4);
        Shape triangle = new Triangle(3, 4, 5);

        for (Shape s : new Shape[]{circle, rectangle, triangle}) {
            System.out.printf(Locale.ROOT,
                "%s area=%.2f perimeter=%.2f%n",
                kind(s), area(s), perimeter(s));
        }

        System.out.println("equilateral="
            + kind(new Triangle(2, 2, 2)));
        System.out.println("isosceles="
            + kind(new Triangle(2, 2, 3)));
        System.out.println("null=" + kind(null));

        expectClose("circle-area", 4 * Math.PI, area(circle));
        expectClose("circle-perimeter", 4 * Math.PI,
            perimeter(circle));
        expectClose("rectangle-area", 12, area(rectangle));
        expectClose("rectangle-perimeter", 14,
            perimeter(rectangle));
        expectClose("triangle-area", 6, area(triangle));
        expectClose("triangle-perimeter", 12,
            perimeter(triangle));

        expectText("triangle-guard", "TRIANGLE", kind(triangle));
        expectText("equilateral-guard", "EQUILATERAL",
            kind(new Triangle(2, 2, 2)));
        expectText("isosceles-guard", "ISOSCELES",
            kind(new Triangle(2, 2, 3)));
        expectText("null-kind", "NONE", kind(null));

        expectIllegalArgument("invalid-triangle",
            () -> new Triangle(1, 2, 3));
        expectIllegalArgument("invalid-circle",
            () -> new Circle(0));
        expectNullPointer("null-area", () -> area(null));

        System.out.println("TESTS=" + passed);
    }
}
```

Biên dịch và chạy bằng JDK21 trở lên từ thư mục có file:

```bash
javac --release 21 GeometrySubtypeEvolutionDemo.java
java GeometrySubtypeEvolutionDemo
```

**Stdout chính xác:**

```text
CIRCLE area=12.57 perimeter=12.57
RECTANGLE area=12.00 perimeter=14.00
TRIANGLE area=6.00 perimeter=12.00
equilateral=EQUILATERAL
isosceles=ISOSCELES
null=NONE
PASS circle-area
PASS circle-perimeter
PASS rectangle-area
PASS rectangle-perimeter
PASS triangle-area
PASS triangle-perimeter
PASS triangle-guard
PASS equilateral-guard
PASS isosceles-guard
PASS null-kind
PASS invalid-triangle
PASS invalid-circle
PASS null-area
TESTS=13
```

Chương trình chỉ dùng Java SE, không cần JUnit hay dependency bên ngoài. Các helper `expect...` tự ném `AssertionError` khi kết quả không đúng, nên không cần bật `java -ea`.

## 8. Phân tích mã: nơi compiler giúp, nơi test phải giúp

### 8.1. Area và perimeter: một case cho mỗi hình

`area(Shape)` và `perimeter(Shape)` đều liệt kê ba record patterns. Khi `Triangle` được đưa vào hierarchy và case tương ứng đã được thêm, compiler xác nhận coverage. Nếu sau này thêm `Pentagon`, những switch không có nhánh bao phủ `Pentagon` sẽ tiếp tục báo lỗi khi biên dịch lại.

**Nhưng công thức đúng là việc của test.** Ví dụ compiler sẽ chấp nhận sai lầm:

```java
// Sai NGHIỆP VỤ nhưng vẫn hợp lệ về cú pháp/kiểu:
case Triangle(double a, double b, double c) -> a * b;
```

Một `case` như vậy khiến switch exhaustive, nhưng diện tích tam giác tổng quát không phải `a*b`. Test tam giác 3–4–5 với expected area = 6 giúp phát hiện lỗi.

Tương tự, nếu chu vi hình chữ nhật bị viết `w+h` thay vì `2*(w+h)`, compiler vẫn compile; test `rectangle-perimeter` mới chứng minh hành vi đúng.

### 8.2. Constructor validation: dữ liệu hợp lệ trước khi matching

Trong record `Triangle`:

```java
Triangle {
    requirePositive("a", a);
    requirePositive("b", b);
    requirePositive("c", c);
    if (a + b <= c || a + c <= b || b + c <= a) {
        throw new IllegalArgumentException(
            "triangle inequality violated");
    }
}
```

Quy tắc được kiểm tra **khi tạo object**. Nhờ vậy `area` không cần lặp lại bất đẳng thức tam giác trong mỗi case.

Bộ test `invalid-triangle` tạo `Triangle(1,2,3)` để kiểm tra trường hợp suy biến (1+2 không lớn hơn 3). Bộ test `invalid-circle` xác nhận radius0 bị từ chối.

**Điểm giới hạn:** Với những cạnh `double` cực lớn, phép cộng và công thức Heron có thể mất độ chính xác hoặc overflow dù từng cạnh đều hữu hạn. Đây là model minh họa cho giá trị cỡ thông thường. Nếu yêu cầu numerical robustness nghiêm ngặt, cần đặt giới hạn miền đầu vào hoặc dùng công thức/thuật toán ổn định hơn và test số học chuyên biệt.

### 8.3. Pattern guard: compiler không quyết định taxonomy hình

Trong `kind`, các case tam giác được viết từ riêng đến chung:

1. Ba cạnh bằng nhau → `EQUILATERAL`.
2. Có ít nhất một cặp cạnh bằng nhau (nhưng không phải trường hợp đều vì case trước đã nhận) → `ISOSCELES`.
3. Các tam giác còn lại → `TRIANGLE`.

Javac kiểm tra case nào bị che, nhưng **không biết** business naming mong muốn. Nếu đảo hai guard thứ nhất/thứ hai, chương trình có thể vẫn hợp lệ về mặt kiểu nhưng tam giác đều sẽ bị gọi `ISOSCELES` do guard này trả true trước. Test `equilateral-guard` mới bảo vệ thứ tự đúng theo nghiệp vụ.

Ở ví dụ, việc dùng `double == double` là so sánh chính xác, phù hợp những cạnh đầu vào literal nguyên (2, 3, 5). Với tọa độ đo lường hoặc số đã qua phép tính dấu phẩy động, quy định phân loại theo tolerance phải rõ ràng hơn.

### 8.4. Null selector: compiler không đọc quy ước nghiệp vụ thay bạn

`kind(null)` trả `NONE` vì có `case null`. Nhưng `area(null)` **không** có case null, nên theo quy tắc pattern switch của Java 21, selector null ném `NullPointerException`. Test `null-area` xác nhận điều này.

Một ứng dụng thực cần quyết định:
- Null là dữ liệu hợp lệ và có ý nghĩa riêng?
- Hay phải từ chối ngay tại boundary bằng `Objects.requireNonNull(shape)`?
- Có muốn dùng exception nghiệp vụ riêng cho thiếu hình không?

**Không** thêm `default` rồi nghĩ nó tự xử lý selector null. Null handling phải được viết theo contract; `case null` dành cho selector null.

## 9. Đọc chính xác diagnostic của javac

Với ví dụ non-exhaustive, định dạng chẩn đoán thường như sau (tên file/dòng/caret là **minh họa**, tùy bản JDK):

```text
Geometry.java:XX: error: the switch expression does not cover all possible input values
        return switch (shape) {
               ^
1 error
```

Điều cần đọc:
- **File/dòng:** Code của `switch` nào thiếu coverage?
- **Thông điệp:** Là lỗi `switch expression` hay `switch statement`?
- **Kiểu selector:** `Shape` có thể nhận subtype mới nào?
- **Danh sách case:** Case nào đã bao phủ các subtype? Có case rộng/default che thiếu sót không?
- **Điểm thay đổi của hierarchy:** `permits` vừa được sửa? Một subtype đã chuyển nhánh hay được mở rộng thành `non-sealed`?

Khi compiler nói:

```text
error: this case label is dominated by a preceding case label
```

thường cần xem **case phía trước**, không chỉ case bị gạch chân. Ví dụ một `case Shape s` đặt trước `case Triangle(...)` sẽ bao phủ cả tam giác và khiến case sau bị dominated.

### Các lỗi dễ nhầm với exhaustiveness

| Thông điệp/triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `switch expression does not cover...` | Thiếu subtype/case bao phủ | Thêm case, rà logic và test |
| `switch statement does not cover...` | Enhanced switch statement thiếu coverage | Bổ sung case tương ứng |
| `case label is dominated...` | Case tổng quát hoặc case không guard đứng trước | Sắp case cụ thể/guard trước |
| `cannot find symbol: Triangle` | Chưa khai báo/import type hoặc sai phạm vi | Sửa khai báo/import, không phải thêm default |
| `class is not allowed to extend sealed class...` | Subtype không được phép hoặc `permits`/module/package không phù hợp | Cập nhật direct permits và quan hệ subtype |
| `invalid permits clause` | `permits` liệt kê sai direct subclass/subinterface | Kiểm quan hệ kế thừa/implements trực tiếp |
| `cannot be converted to...` | Pattern/record component không tương thích kiểu | Sửa kiểu component hoặc pattern |
| `NullPointerException` runtime | Selector null không được nhận | Thống nhất null policy |
| `MatchException` runtime | Không có case khớp trong tình huống mà compiler từng xem là exhaustive; có thể liên quan separate compilation/nested patterns | Đồng bộ build và rà invariant/null |

Đừng áp dụng **một sửa chữa duy nhất** cho mọi diagnostic. Lỗi compile-time về coverage khác với exception tại runtime và khác với sai kết quả diện tích.

## 10. Hành vi khi thêm subtype ở nhiều module

Trong một project nhỏ, `Shape` và các `switch` có thể nằm cùng module nên thao tác thêm subtype và biên dịch lại khiến compiler phản hồi ngay.

Trong hệ thống nhiều module:
- **Model module:** Chứa sealed `Shape` và các record.
- **Geometry service:** Tính diện tích/chu vi.
- **Rendering module:** Tạo text, JSON, SVG, hoặc giao diện cho từng hình.
- **Analytics module:** Tổng hợp loại hình, thống kê.
- **Integration module:** Mapping sang dữ liệu đối tác.

Nếu chỉ compile lại model module nhưng **không** recompile các consumer, không thể dựa vào compiler để chắc chắn mọi handler đã được cập nhật. Một switch cũ đã được compile theo hierarchy cũ có thể gặp `MatchException` khi chạy với biến thể mà nó chưa nhận, tùy điều kiện binary compatibility và runtime.

Vì vậy sau khi thêm subtype:
1. **Build lại toàn bộ các consumer** dùng `Shape`.
2. Chạy unit/integration tests trên các artifact tương thích.
3. Review các serialization, database mappings, UI và API public bị ảnh hưởng.
4. Tránh deploy model mới trước khi các consumer cần xử lý kiểu mới đã sẵn sàng, trừ khi contract có fallback rõ ràng.

**Compile-time feedback chỉ có hiệu lực với những đơn vị được biên dịch trong lần build đó**. “Build một module thành công” khác với “hệ thống nhiều module đã xử lý hết subtype mới”.

## 11. Khi nào không nên giữ sealed hierarchy đóng hoàn toàn?

`sealed` phù hợp khi tập biến thể do bạn kiểm soát, tương đối ổn định và các operation cần exhaustive matching. Nhưng nếu ứng dụng cần plugin bên thứ ba tự định nghĩa hình mới, danh sách kiểu có thể **mở**.

Ví dụ một direct permitted subtype là `non-sealed`:

```java
// Đoạn minh họa riêng, không ghép vào chương trình phần 7.
sealed interface Shape permits BuiltInShape, PluginShape {}

sealed interface BuiltInShape extends Shape
        permits Circle, Rectangle {}
non-sealed interface PluginShape extends Shape {}
```

Bên thứ ba có thể triển khai các subtype của `PluginShape`. Một switch muốn exhaustive cần bao phủ **toàn nhánh `PluginShape`** bằng type pattern hoặc fallback có chủ đích; không thể liệt kê trước vô hạn implementation do plugin cung cấp.

**Mẹo thiết kế:**
- Nếu phép tính diện tích/chu vi là contract cho mọi hình và plugin phải tự định nghĩa logic, có thể cân nhắc `double area()`/`double perimeter()` trên interface (đa hình) thay vì để mọi consumer liệt kê kiểu.
- Nếu tập kiểu đóng và nhiều operation độc lập thường xuyên được thêm (formatter, exporter, renderer), pattern switch trên sealed types rất hữu ích.
- Chọn sealed hay open hierarchy dựa vào khả năng mở rộng mong muốn, không chỉ vì compiler feedback dễ chịu.

### Một lựa chọn khác: generic fallback có chủ ý

Với một thao tác logging chỉ cần tên class, có thể chấp nhận fallback tổng quát. Khi đó một case như `case Shape s -> ...` có nghĩa hợp lý. Nhưng với **tính diện tích**, silent fallback `0` thường che lỗi nghiệp vụ; nên yêu cầu mỗi subtype có một công thức đúng.

## 12. Test matrix khi thêm Triangle

Không nên dừng lại ở việc `javac` báo hết lỗi. Bổ sung test cho **subtype mới** và test hồi quy cho các subtype cũ.

| Hạng mục | Input/điều kiện | Kỳ vọng |
| --- | --- | --- |
| Circle area | `Circle(2)` | `4π` |
| Circle perimeter | `Circle(2)` | `4π` |
| Rectangle area | `Rectangle(3,4)` | `12` |
| Rectangle perimeter | `Rectangle(3,4)` | `14` |
| Triangle area | `Triangle(3,4,5)` | `6` |
| Triangle perimeter | `Triangle(3,4,5)` | `12` |
| Triangle general | `Triangle(3,4,5)` | `TRIANGLE` |
| Triangle equilateral | `Triangle(2,2,2)` | `EQUILATERAL` |
| Triangle isosceles | `Triangle(2,2,3)` | `ISOSCELES` |
| Null selector for kind | `null` | `NONE` |
| Invalid triangle | `Triangle(1,2,3)` | `IllegalArgumentException` |
| Invalid circle | `Circle(0)` | `IllegalArgumentException` |
| Null selector for area | `null` | `NullPointerException` |

Đây chính là 13 test cases trong chương trình chạy được. Đối với production, thêm nhiều trường hợp:
- Radius/width/height âm, zero, NaN, Infinity.
- Tam giác không thỏa bất đẳng thức ở các hoán vị cạnh.
- Tam giác gần suy biến; cạnh rất lớn/rất nhỏ để kiểm định tính ổn định số học.
- Giá trị đầu vào dẫn đến area/perimeter không hữu hạn.
- Các hành vi UI/API/serialization cho subtype mới.
- Regression test cho mọi subtype cũ, không chỉ Triangle.

**Test trước-sau:** Khi thêm `Triangle`, không chỉ sửa logic mới; các operation có thể chia sẻ nhánh hoặc dùng guard nên việc sắp xếp có thể vô tình làm đổi kết quả cũ. Test cho Circle và Rectangle giúp phát hiện regression.

### Compiler feedback không phải test coverage

Compiler có thể xác nhận mỗi subtype được **một case** bao phủ. Nó không kiểm tra:
- Nhánh có guard nào thật sự được chạy?
- Công thức được viết đúng?
- Validation có loại bỏ tất cả dạng dữ liệu sai?
- Có case nào cố ý trả lỗi nghiệp vụ dù compile thành công?
- Code có đúng theo yêu cầu UI/đối tác?
- Test đã bao phủ các cạnh miền giá trị?

Bởi vậy cần phối hợp **compile-time exhaustiveness + runtime tests + review nghiệp vụ**.

## 13. Có thể dùng reflection để bảo vệ tập subtype không?

Java cung cấp `Class::isSealed` và `Class::getPermittedSubclasses`. Trong một test riêng, ta có thể kiểm tra chính xác các direct permitted types:

```java
// Đoạn minh họa trong cùng class có Shape/Circle/Rectangle/Triangle:
if (!Shape.class.isSealed()) {
    throw new AssertionError("Shape must stay sealed");
}

java.util.Set<Class<?>> expected = java.util.Set.of(
    Circle.class, Rectangle.class, Triangle.class);

java.util.Set<Class<?>> actual =
    java.util.Set.of(Shape.class.getPermittedSubclasses());

if (!expected.equals(actual)) {
    throw new AssertionError("Shape hierarchy changed");
}
```

`getPermittedSubclasses()` trả các **direct permitted subclasses/subinterfaces**. Với hierarchy có nhiều cấp sealed/non-sealed, phải kiểm tra các nút trung gian để biết toàn bộ leaf variants mà ứng dụng sở hữu.

Test reflection giúp phát hiện khi một kiểu mới xuất hiện mà ma trận test chưa cập nhật. Nó **không** chứng minh case toán học đúng. Khi thêm subtype hợp lệ, expected set phải được cập nhật cùng với test và handler liên quan.

Một số IDE/CI có công cụ kiểm tra exhaustiveness sớm, nhưng **javac là kiểm tra nền tảng khi build**. Reflection test là lớp bổ sung chứ không thay thế compile-time checking.

## 14. Lỗi thiết kế thường gặp khi tiếp nhận subtype mới

### 14.1. “Sửa cho hết compiler error” bằng default rộng

```java
// Hành vi có thể che thiếu implementation:
return switch (shape) {
    case Circle(double r) -> Math.PI * r * r;
    case Rectangle(double w, double h) -> w * h;
    default -> 0.0;
};
```

Sau khi có Triangle, code biên dịch nhưng trả 0.0. Nếu hành vi cần chính xác với từng hình, đây là bug nghiệp vụ.

**Chọn:** Thêm `case Triangle(...)` thực sự tính đúng, hoặc ném exception rõ ràng nếu type chưa được hỗ trợ theo một policy chuyển tiếp có kiểm soát. Không coi giá trị giả là kết quả hợp lệ.

### 14.2. Bỏ qua phép tính thứ hai

Một developer chỉ sửa `area` vì compiler đang báo nó, nhưng quên `perimeter` ở module khác không được build. Kết quả là diện tích chạy đúng, chu vi có thể fail khi runtime gặp Triangle.

**Chọn:** Tìm mọi consumer của `Shape`, build toàn bộ và áp dụng danh sách kiểm toán các operation liên quan.

### 14.3. Đưa case cụ thể sau case tổng quát

`case Shape s` đặt đầu switch làm các case Circle/Rectangle/Triangle phía sau dominated. Tương tự, `case Triangle(...)` không guard đứng trước guard `EQUILATERAL`.

**Chọn:** Sắp nhánh chuyên biệt trước, fallback rộng sau; viết test cho guard có giá trị trùng nhau.

### 14.4. Thay đổi data model mà bỏ qua invariant

Thêm `Triangle` chỉ với ba `double` không có nghĩa mọi bộ ba là tam giác. `Triangle(1,2,3)` không hợp lệ; `Triangle(0,4,5)` cũng vậy.

**Chọn:** Validate trong constructor hoặc factory/domain service sở hữu rule. Khi ứng dụng nhận dữ liệu không đáng tin từ JSON/API, kiểm tra ở boundary và bảo đảm domain object không bị tạo sai.

### 14.5. Mong compiler phát hiện mọi sai số học

`sqrt(s*(s-a)*(s-b)*(s-c))` có thể có lỗi làm tròn hoặc overflow. Compiler không chứng minh tính ổn định số học chỉ từ kiểu `double`.

**Chọn:** Dùng các bài test numerical có ý nghĩa, tolerance đúng contract và thuật toán phù hợp nếu xử lý giá trị cực đoan.

### 14.6. Giả định exhaustive nghĩa là không bao giờ có runtime exception

Pattern `switch` exhaustiveness dựa trên cấu trúc kiểu tại compile time. Runtime vẫn có thể ném `NullPointerException` với selector null, hoặc `MatchException` trong một số tình huống bất thường như separate compilation hoặc record pattern lồng nhau không khớp vì null. Guard/case body cũng có thể ném exception riêng.

**Chọn:** Thiết kế null policy và lỗi nghiệp vụ rõ ràng; build và test cùng artifact/dependency sẽ deploy.

## 15. Quy trình nhóm phát triển: thay đổi sealed model không để lọt consumer

Một quy trình thêm subtype đáng tin cậy:

1. **Định nghĩa nghiệp vụ subtype:** Triangle có ba cạnh, công thức area/perimeter, các invariant và cách phân loại cụ thể.
2. **Cập nhật hierarchy:** Thêm record subtype vào `permits` đúng quan hệ trực tiếp. Xác định subtype là final/sealed/non-sealed theo thiết kế.
3. **Build ngay:** Ghi nhận các lỗi exhaustive/dominance từ `javac` trước khi sửa. Đây là những điểm consumer phải review.
4. **Cập nhật từng operation:** Thêm công thức thật, không thêm default che thiếu logic. Sắp xếp guard đúng thứ tự.
5. **Bổ sung tests:** Test subtype mới, giá trị biên, dữ liệu không hợp lệ; giữ các test Circle/Rectangle.
6. **Build lại toàn bộ module phụ thuộc:** Đảm bảo không có consumer chỉ dùng bytecode cũ.
7. **Review API và integration:** DTO, serialization, persistence, UI, báo cáo và các hệ thống bên ngoài phải hiểu Triangle theo contract.
8. **Kiểm thử deployment:** Với nhiều service có version khác nhau, xác nhận khả năng xử lý subtype mới khi cập nhật theo từng đợt.
9. **Đánh giá tính mở rộng:** Nếu liên tục thêm plugin hình dạng mà vẫn phải sửa hàng chục switch, cân nhắc đa hình/domain service hoặc một extension point phù hợp.
10. **Chỉ phát hành sau khi QA:** Compile-time feedback là lớp bảo vệ đầu tiên, không phải điều kiện duy nhất.

### Ví dụ tình huống mở rộng thêm một kiểu nữa

Nếu sau Triangle muốn thêm `Square(double side)`, cần xem `Square` là subtype riêng hay một loại `Rectangle` về mặt domain. Nếu chọn record subtype riêng:
- Thêm `Square` vào hierarchy và `permits`.
- Javac có thể báo thiếu coverage tại `area`/`perimeter`/`kind`.
- Thêm công thức `side*side`, `4*side` và nhãn phù hợp.
- Test các giá trị side âm/0/dương.
- Kiểm tra xem các consumer có chính sách đối xử Square như Rectangle không.

Không nên tạo subtype mới chỉ vì có thể: cấu trúc hierarchy phải phản ánh **khái niệm domain và cách thay đổi được mong đợi**.

## 16. Bài tập thực hành

**Bài tập 1 — Tái tạo lỗi non-exhaustive:** Sao chép đoạn `Shape` có Circle/Rectangle/Triangle nhưng cố tình bỏ `case Triangle(...)` khỏi `area`. Biên dịch bằng `javac --release 21`, ghi lại thông điệp. Sau đó thêm case Heron và chạy `Triangle(3,4,5)`.

**Bài tập 2 — Sửa chu vi:** Bỏ tạm `case Triangle(...)` khỏi `perimeter`. Compiler nhắc gì? Thêm case trả `a+b+c`, kiểm tra expected12 với bộ cạnh 3–4–5.

**Bài tập 3 — Dominance và guard:** Đặt case Triangle không guard trước case `when a==b && b==c`. Quan sát lỗi dominated. Khôi phục thứ tự; rồi đảo guard isosceles/equilateral để thấy test logic nào thất bại dù compiler vẫn có thể chấp nhận.

**Bài tập 4 — Thêm Square:** Thêm `record Square(double side) implements Shape` với validation dương hữu hạn. Cập nhật `permits`, các switch và test. Ghi danh sách các compile errors được phát hiện trước khi sửa.

**Bài tập 5 — Null policy:** So sánh `kind(null)` với `area(null)`. Tại sao một method trả `NONE` còn method kia ném `NullPointerException`? Đề xuất một contract thống nhất cho ứng dụng và test tương ứng.

**Bài tập 6 — Dữ liệu gần suy biến:** Tạo tam giác có tổng hai cạnh chỉ nhỉnh hơn cạnh còn lại. Quan sát điều kiện validation và tính ổn định của công thức Heron. Xác định một miền dữ liệu thích hợp cho production và chiến lược làm tròn/tolerance.

**Bài tập 7 — Multi-module:** Tách `Shape` và các record vào module domain, `area/perimeter` vào module service, `kind` vào adapter. Thêm `Square` rồi chỉ compile module domain. Giải thích vì sao build một module không bảo đảm tất cả consumers đã được kiểm tra; hoàn thiện CI để build toàn bộ.

## 17. Tổng kết

**Sealed hierarchy + pattern switch ở Java 21 tạo ra một vòng phản hồi quan trọng khi mở rộng domain model.** Khi thêm `Triangle` vào `Shape`, compiler có thể báo lỗi ở những `switch expression` hoặc enhanced `switch statement` chưa xử lý subtype mới. Đây là phương pháp bảo vệ **exhaustiveness ở compile time** rất hữu ích cho những tập biến thể được kiểm soát.

Nhưng compiler **không chứng minh công thức diện tích/chu vi đúng**, không tự kiểm tra bất đẳng thức tam giác, guard nghiệp vụ hay tất cả tình huống runtime. Cần kết hợp **cập nhật `permits` → xử lý compiler feedback → thêm case chính xác → kiểm thử subtype mới và subtype cũ → build lại các consumer**.

Đừng xem `default` là cách nhanh nhất làm build xanh. Khi một operation phải xử lý tường minh từng hình, việc compiler buộc bạn quay lại viết case cho subtype mới chính là một lợi ích của thiết kế.

## Tài liệu tham khảo

- Oracle Java SE 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- Oracle Java SE 21 — Record Patterns: https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
- Oracle Java SE 21 — Sealed Classes and Interfaces: https://docs.oracle.com/en/java/javase/21/language/sealed-classes-and-interfaces.html
- Java Language Specification SE 21 — `14.11 switch Statements`: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11
- Java Language Specification SE 21 — `15.28 switch Expressions`: https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28
- OpenJDK JEP 409 — Sealed Classes: https://openjdk.org/jeps/409
- OpenJDK JEP 440 — Record Patterns: https://openjdk.org/jeps/440
- OpenJDK JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
