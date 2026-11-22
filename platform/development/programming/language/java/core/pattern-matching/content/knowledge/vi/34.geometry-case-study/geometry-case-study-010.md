# Đo khả năng mở rộng của hierarchy: case study hình học với Java Pattern Matching

## 1. Hiểu đúng “khả năng mở rộng”

Trong một hệ thống hình học, ta thường có nhiều **biến thể hình** (hình tròn, hình chữ nhật, tam giác, v.v.) và nhiều **phép toán** (diện tích, mô tả loại hình, hiển thị thông số, kiểm tra va chạm, xuất dữ liệu). Khi hệ thống phát triển, có hai yêu cầu khác nhau:

1. **Thêm một loại hình mới:** ví dụ bổ sung `Triangle` vào hierarchy trước đó chỉ có `Circle` và `Rectangle`.
2. **Thêm một thao tác mới:** ví dụ ngoài `area` và `category`, bổ sung `describeDimensions` để trình bày tham số hình.

Một thiết kế có thể rất dễ thêm thao tác nhưng lại đòi hỏi sửa nhiều nơi khi thêm subtype; thiết kế khác có thể dễ thêm subtype nhưng phải sửa từng lớp khi thêm thao tác. Vì vậy, câu hỏi “hierarchy có dễ mở rộng không?” chỉ có ý nghĩa nếu **chỉ rõ hướng mở rộng và cách đo**.

Trong Java Core Pattern Matching, đặc biệt với **`sealed interface` + `record` + `switch` theo pattern**, ta có một bộ công cụ để quan sát rõ các chi phí này:

- `sealed` quy định những subtype trực tiếp được phép.
- `record` giữ component hình học và có thể áp invariant tại constructor.
- `switch expression` trên kiểu sealed với record/type patterns buộc lập trình viên xử lý đủ các subtype phù hợp.
- Trình biên dịch giúp phát hiện nhánh bị bỏ sót khi một biến thể mới được thêm.
- Kiểm thử xác minh cả công thức hình học và sự khác biệt giữa các phương án thiết kế.

**Điều được đo chủ yếu trong bài là khả năng bảo trì/mở rộng mã nguồn**, không phải “thêm subtype làm chương trình chạy nhanh hơn bao nhiêu”. Benchmark hiệu năng là bài toán riêng.

**Yêu cầu phiên bản:** `record` chính thức từ Java 16 (JEP 395), `sealed` từ Java 17 (JEP 409), record patterns và pattern matching for `switch` chính thức từ **Java 21** (JEP 440/441). Chương trình đầy đủ trong bài dùng **JDK 21 trở lên**, không cần `--enable-preview`.

## 2. Mô hình thử nghiệm: tập hình có chủ đích

Giả sử phiên bản ban đầu có hai loại hình:

```java
sealed interface Shape permits Circle, Rectangle {}

record Circle(double radius) implements Shape {}
record Rectangle(double width, double height) implements Shape {}
```

Đây là **đoạn minh họa thiết kế ban đầu**, chưa phải chương trình Java độc lập; khi thử riêng phải đặt các kiểu đúng phạm vi và có phần xử lý cần thiết.

Ta cần hai thao tác độc lập, đều phụ thuộc vào biến thể:

- `area(Shape)` trả diện tích.
- `category(Shape)` trả nhãn hình học như `"circle"`, `"rectangle"`.

Với hai biến thể, một cách hiện thực Java 21 là:

```java
// Các phương thức minh họa đặt trong class có Shape, Circle, Rectangle.
static double area(Shape shape) {
    return switch (shape) {
        case Circle(var radius) -> Math.PI * radius * radius;
        case Rectangle(var width, var height) -> width * height;
        case null -> throw new IllegalArgumentException("shape required");
    };
}

static String category(Shape shape) {
    return switch (shape) {
        case Circle c -> "circle";
        case Rectangle r -> "rectangle";
        case null -> "missing";
    };
}
```

Ở `area`, **record pattern** tách component: `Circle(var radius)` lấy bán kính; `Rectangle(var width, var height)` lấy chiều rộng/chiều cao. Ở `category`, **type pattern** `Circle c`/`Rectangle r` chỉ chọn biến thể; không cần tách component vì kết quả không phụ thuộc kích thước.

Đây là phép đo đầu tiên: với hai biến thể và hai thao tác chứa `switch`, có **bốn nhánh xử lý subtype** (hai case trong `area`, hai case trong `category`). Các nhánh `case null` là chính sách đầu vào riêng nên **không tính vào số nhánh subtype**.

## 3. Bộ chỉ số đo mở rộng phải được định nghĩa trước

Ký hiệu:

- **V** (*variants*): số loại hình cụ thể mà thiết kế muốn xử lý.
- **O** (*variant-sensitive operations*): số thao tác thực sự cần phân nhánh theo loại hình.
- **B** (*branch implementations*): tổng số case dành cho subtype trên các thao tác đó.
- **ΔV**: số subtype bổ sung.
- **ΔO**: số thao tác phụ thuộc subtype bổ sung.
- **S** (*semantic edit sites*): số vị trí code độc lập về trách nhiệm cần được bổ sung hoặc cập nhật trong một thay đổi.
- **F** (*files touched*): số file thực sự được sửa trong repository; phải đo từ diff, không đoán từ số case.
- **T** (*tests affected*): số test thêm/sửa và tỷ lệ ca kiểm thử vượt qua sau khi đổi.

Khi **mỗi thao tác có đúng một case cho mỗi subtype** và không có nhánh gộp, chi phí nhánh được mô hình hóa đơn giản bằng:

\[
B = V \times O
\]

Đây là **mô hình đếm cấu trúc**, không phải định luật Java hay độ phức tạp thời gian chạy. Trong code thật, một thao tác có thể dùng polymorphism, chia sẻ logic, một case tổng quát, hoặc không cần phân nhánh; khi đó phải **đếm thực tế**, không áp công thức máy móc.

Một phương pháp đo hữu ích là thực hiện **hai change scenarios** rồi so sánh:

| Thay đổi | Chỉ số cần ghi | Kiểm tra bổ sung |
| --- | --- | --- |
| Thêm một loại hình | `ΔV`, case thêm ở các switch, vị trí sửa, file sửa, test mới | Compiler có phát hiện switch thiếu case không? |
| Thêm một thao tác phụ thuộc loại hình | `ΔO`, số case phải viết, vị trí/file sửa | Có trùng lặp công thức, vi phạm invariant hoặc bỏ sót hình không? |
| Sửa một công thức chung | Vị trí thay đổi và phạm vi test ảnh hưởng | Có thể tái sử dụng logic hay phải sửa lặp lại? |
| Nhận subtype không dự kiến | Tình huống compile/runtime, fallback policy | Có `default` làm che cảnh báo thiếu subtype không? |

Một hierarchy nhiều subtype **không nhất thiết xấu**; vấn đề là thay đổi phổ biến nhất của domain dẫn đến bao nhiêu chỗ phải sửa và bao nhiêu lỗi dễ bỏ sót.

## 4. Thí nghiệm A — thêm Triangle vào hierarchy

Giả sử ban đầu có `V = 2`, `O = 2`, vậy `B = 4` nhánh subtype. Yêu cầu mới là hỗ trợ một tam giác **có đáy và chiều cao dương**, đủ để tính **diện tích**, chưa đủ để tính chu vi.

### 4.1. Các thay đổi cần làm

**(1) Mở rộng `permits`:**

```java
sealed interface Shape permits Circle, Rectangle, Triangle {}
```

**(2) Thêm record:**

```java
record Triangle(double base, double height) implements Shape {}
```

**(3) Bổ sung case trong `area`:**

```java
case Triangle(var base, var height) -> base * height / 2;
```

**(4) Bổ sung case trong `category`:**

```java
case Triangle t -> "triangle";
```

Các đoạn trên minh họa **thay đổi cần ghép vào cùng mô hình**; chương trình ở mục 6 đã chứa phiên bản đầy đủ sau khi mở rộng.

Theo cách đếm `S` đã định nghĩa, đây là **bốn vị trí thay đổi logic**: danh sách `permits`, khai báo record mới và hai case mới. Chúng **không đồng nghĩa bốn file**: nếu các type và switch cùng nằm trong một file học tập thì `F = 1`; trong codebase nhiều file, giá trị `F` phụ thuộc tổ chức dự án.

Sau thay đổi:

| Chỉ số | Trước khi thêm Triangle | Sau khi thêm Triangle | Chênh lệch |
| --- | ---: | ---: | ---: |
| Biến thể `V` | 2 | 3 | +1 |
| Thao tác có switch `O` | 2 | 2 | 0 |
| Nhánh subtype `B = V × O` | 4 | 6 | +2 |
| Nhánh mới cần thêm trong switch | — | 2 | +2 |
| Vị trí mã mang ý nghĩa cần thêm/sửa `S` | — | 4 | 4 vị trí |
| Test cho Triangle | Chưa có | Phải bổ sung | Đếm trong test diff thực |

**Kết quả quan trọng:** mỗi thao tác phân nhánh theo kiểu hình có thể tạo ra một điểm cần cập nhật khi thêm subtype. Nếu có 12 thao tác riêng biệt đều chứa switch exhaustive, thêm một subtype có thể đòi hỏi **12 case mới**, không phải một. Nhưng đó là số nhánh được thiết kế theo mô hình này, **không phải số file**, không phải `O(12)` thời gian chạy của một request.

### 4.2. Tại sao sealed + switch exhaustive có lợi cho phép đo?

Với `switch expression` trên `Shape` có ba final record subtype, nếu quên `case Triangle...` trong `area`, compiler có thể bác chương trình là **không bao phủ đủ giá trị**. Điều này biến “nơi cần cập nhật” từ rủi ro dễ quên thành một lỗi build quan sát được.

Nếu dùng `default -> 0.0` chỉ để compiler hết báo thiếu nhánh, code có thể vẫn biên dịch nhưng **âm thầm trả diện tích sai** cho subtype mới. Vì vậy, trong một hierarchy cố ý đóng, tránh `default` thừa nếu muốn tận dụng **exhaustiveness**.

Phần `case null` xử lý selector null theo chính sách riêng. Null không phải là một subtype được liệt kê trong `permits`.

## 5. Thí nghiệm B — thêm một thao tác mới

Giữ `V = 3` với Circle, Rectangle, Triangle. Thêm `describeDimensions(Shape)` để trình bày **tham số đặc trưng của từng hình**, khác với `category` chỉ trả tên.

Một cách viết minh họa:

```java
static String describeDimensions(Shape shape) {
    return switch (shape) {
        case Circle(var r) -> "radius=" + r;
        case Rectangle(var w, var h) -> "width=" + w + ",height=" + h;
        case Triangle(var b, var h) -> "base=" + b + ",height=" + h;
        case null -> "missing";
    };
}
```

Đây là **phương thức minh họa thêm**, không nằm trong chương trình chính của mục 6. Nó tạo ra **một thao tác phụ thuộc variant** với **ba nhánh subtype mới**:

- Trước: `V=3`, `O=2`, `B=6`.
- Sau: `V=3`, `O=3`, `B=9`.
- `ΔB=3`, thêm **một hàm** và **ba nhánh case** theo quy ước đếm semantic edit sites.

Đây là thế mạnh tương đối của pattern switch: có thể thêm **một phép toán mới tập trung tại một nơi**, đọc và so sánh xử lý mọi subtype trong cùng hàm. Ta không phải mở từng record để thêm method riêng chỉ vì một báo cáo mới.

**Nhưng không phải thao tác mới nào cũng cần thêm switch.** Ví dụ `isLarge(Shape shape)` có thể viết `return area(shape) >= 100;`, tái sử dụng `area`, không có ba nhánh mới. Nếu áp dụng `B=V×O`, hãy chỉ tính những thao tác **thực sự cần dispatch riêng theo variant**.

## 6. Chương trình Java hoàn chỉnh để tái hiện

Tạo file **`ShapeExtensibilityDemo.java`**:

```java
public class ShapeExtensibilityDemo {
    sealed interface Shape permits Circle, Rectangle, Triangle {}

    private static void positive(double number, String component) {
        if (!Double.isFinite(number) || number <= 0) {
            throw new IllegalArgumentException(
                    component + " must be finite and positive");
        }
    }

    record Circle(double radius) implements Shape {
        public Circle {
            positive(radius, "radius");
        }
    }

    record Rectangle(double width, double height) implements Shape {
        public Rectangle {
            positive(width, "width");
            positive(height, "height");
        }
    }

    record Triangle(double base, double height) implements Shape {
        public Triangle {
            positive(base, "base");
            positive(height, "height");
        }
    }

    static double area(Shape shape) {
        return switch (shape) {
            case Circle(var r) -> Math.PI * r * r;
            case Rectangle(var w, var h) -> w * h;
            case Triangle(var b, var h) -> b * h / 2;
            case null -> throw new IllegalArgumentException("shape required");
        };
    }

    static String category(Shape shape) {
        return switch (shape) {
            case Circle c -> "circle";
            case Rectangle r -> "rectangle";
            case Triangle t -> "triangle";
            case null -> "missing";
        };
    }

    static String report(Shape shape) {
        return category(shape) + ":" +
                String.format(java.util.Locale.ROOT, "%.2f", area(shape));
    }

    static void check(String label, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(label + ": " + actual);
        }
        System.out.println(label + " -> " + actual);
    }

    public static void main(String[] args) {
        check("circle", "circle:3.14", report(new Circle(1)));
        check("rectangle", "rectangle:6.00",
                report(new Rectangle(2, 3)));
        check("triangle", "triangle:6.00",
                report(new Triangle(4, 3)));
        check("missing", "missing", category(null));

        System.out.println("sealed:" + Shape.class.isSealed());
        System.out.println("permitted:"
                + Shape.class.getPermittedSubclasses().length);

        try {
            new Rectangle(-1, 2);
            throw new AssertionError("invalid dimensions accepted");
        } catch (IllegalArgumentException expected) {
            System.out.println("invalid:" + expected.getMessage());
        }

        try {
            area(null);
            throw new AssertionError("null area accepted");
        } catch (IllegalArgumentException expected) {
            System.out.println("null-area:" + expected.getMessage());
        }
    }
}
```

**Biên dịch và chạy bằng JDK 21+:**

```bash
javac --release 21 ShapeExtensibilityDemo.java
java ShapeExtensibilityDemo
```

**Stdout chính xác của chương trình:**

```text
circle -> circle:3.14
rectangle -> rectangle:6.00
triangle -> triangle:6.00
missing -> missing
sealed:true
permitted:3
invalid:width must be finite and positive
null-area:shape required
```

Chương trình đã được thực thi bằng **JDK 24/JShell** và kiểm tra đúng tám dòng này; các cú pháp chính dùng ở đây đều đã chính thức trong Java 21. `java.util.Locale.ROOT` bảo đảm dấu thập phân trong `String.format` là dấu chấm như output, thay vì phụ thuộc locale máy.

### 6.1. Đọc test và bảo đảm dữ liệu

- `Circle(1)` có diện tích `π×1×1`; làm tròn hai chữ số sau dấu thập phân là `3.14`.
- `Rectangle(2,3)` có diện tích `2×3=6.00`.
- `Triangle(4,3)` có diện tích `4×3/2=6.00`.
- `category(null)` trả `"missing"`; trong khi `area(null)` **ném `IllegalArgumentException`**, theo hai hợp đồng đã chọn.
- `Shape.class.isSealed()` trả `true`; `getPermittedSubclasses().length` trả `3` vì có đúng ba subtype trực tiếp được phép.
- Kích thước `-1` bị constructor từ chối. Hàm `positive` cũng từ chối `0`, `NaN` và ±vô cực thông qua điều kiện `Double.isFinite` và `>0`.
- `report` không chứa một `switch` thứ ba: nó **gọi lại** `category` và `area`. Vì vậy, `O=2` trong phép đo hiện tại, không phải `3`.

**Giới hạn của mô hình tam giác:** `Triangle(base,height)` đủ để tính **diện tích**, nhưng không mô tả đầy đủ ba cạnh/ba đỉnh, nên **không đủ để tính chu vi tam giác bất kỳ**. Nếu bài toán cần chu vi, cần thay model (ví dụ ba cạnh hợp lệ hoặc ba đỉnh) và bổ sung kiểm tra bất đẳng thức tam giác/độ suy biến. Không tự chế công thức chu vi chỉ từ base và height.

### 6.2. Vì sao dùng constructor validation?

Nếu chấp nhận `Circle(-2)`, công thức `πr²` vẫn cho số dương, che mất lỗi dữ liệu hình học. Một thử nghiệm khả năng mở rộng cần **mô hình có invariant rõ**, nếu không phép so sánh giữa các subtype sẽ bị nhiễu bởi những đầu vào không hợp lệ.

Trong ví dụ, chỉ xét hình có kích thước **hữu hạn và dương**. Một ứng dụng CAD có thể cho kích thước bằng 0 để biểu diễn hình suy biến; khi ấy phải thay đổi invariant và test theo domain, không coi quy tắc ở đây là chân lý cho mọi phần mềm hình học.

## 7. Negative compile tests: đo khả năng compiler bảo vệ việc mở rộng

Ngoài test runtime, hãy viết các đoạn **cố tình sai** để xem compiler hỗ trợ tới đâu. Không đặt các đoạn này trong file hoàn chỉnh ở mục 6.

### 7.1. Thiếu case Triangle trong switch expression

Nếu đã thêm `Triangle` vào `permits` nhưng quên bổ sung case trong `area`:

```java
// CỐ TÌNH SAI; đặt trong class có Shape, Circle, Rectangle.
static double areaMissing(Shape s) {
    return switch (s) {
        case Circle(var r) -> Math.PI * r * r;
        case Rectangle(var w, var h) -> w * h;
        case null -> 0.0;
    };
}
```

Với `Shape` chỉ gồm ba record permitted, compiler JDK 24 đã từ chối đoạn tương đương bằng thông báo:

```text
the switch expression does not cover all possible input values
```

Đây là **chỉ báo trực tiếp cho khả năng phát hiện nơi cần sửa** của pattern switch khi thêm subtype. Không nên viết `default -> 0` để né lỗi, vì compiler có thể không còn báo thiếu case mà phép toán trả giá trị sai.

### 7.2. Subtype không được cho phép

```java
// CỐ TÌNH SAI: Shape.permits không có Pentagon.
class Pentagon implements Shape {}
```

Compiler từ chối vì `Pentagon` không nằm trong danh sách permitted direct subtypes của sealed `Shape`. Đây là **ràng buộc mở rộng hierarchy**, không phải chuyện dữ liệu bên trong Pentagon hợp lệ hay không.

Trong thư viện mở rộng qua plugin bên ngoài, mô hình sealed đóng hoàn toàn có thể là lựa chọn **không thích hợp**. Ta cần quyết định rõ đâu là điểm extension được phép, không chỉ xem compiler error là một lợi ích.

### 7.3. Sai số component khi thêm record mới

`Triangle` có **hai** component, nên đoạn sau sai:

```java
// CỐ TÌNH SAI: Triangle cần hai nested patterns.
static boolean wrongParts(Object input) {
    return input instanceof Triangle(var base);
}
```

Compiler JDK 24 từ chối vì `incorrect number of nested patterns`. Khi thay đổi cấu trúc record, các pattern tham chiếu trực tiếp có thể cần cập nhật. Điều này là **chi phí coupling với cấu trúc** chứ không chỉ chi phí thêm subtype.

Các negative compile tests trên đã được đối chiếu bằng JShell JDK 24. Chúng minh họa lỗi mà compiler phát hiện; không phải file Java có thể chạy để tạo stdout.

## 8. Reflection cho biết điều gì, và không cho biết điều gì?

Java 17+ có các API reflection liên quan tới sealed class:

```java
boolean sealed = Shape.class.isSealed();
Class<?>[] direct = Shape.class.getPermittedSubclasses();
System.out.println(sealed);
System.out.println(direct.length);
```

Đây là **đoạn minh họa** trong một class có `Shape` đã định nghĩa. Trong chương trình chính, kết quả được in với tiền tố `sealed:` và `permitted:`.

Giá trị `getPermittedSubclasses().length` là **số direct permitted subclasses/interfaces**, không tự động là:

- Tổng số lớp con **gián tiếp** ở mọi độ sâu.
- Số loại hình hiện tồn tại dưới một nhánh `non-sealed` có thể được mở rộng bên ngoài.
- Số case trong mọi `switch` của codebase.
- Số lượng test đủ bao phủ hay số file cần sửa khi thêm một loại hình.

Trong ví dụ, tất cả subtype trực tiếp đều là final records, nên `3` cũng là số biến thể cụ thể của model đang xét. Với hierarchy nhiều tầng, cần phân biệt **độ rộng** (số nhánh trực tiếp), **độ sâu** (số tầng kế thừa) và các điểm **mở** do `non-sealed`.

**Quan trọng:** reflection có thể xác nhận trạng thái runtime của hierarchy, còn **đếm các switch sites phải làm ở cấp mã nguồn/AST/code review hoặc công cụ phân tích tĩnh**. Không lấy kết quả `permitted:3` rồi suy ra compiler chắc chắn đã kiểm tra mọi logic nghiệp vụ trong ứng dụng.

## 9. So sánh pattern switch với polymorphism

Có thể chuyển các phép toán vào kiểu hình:

```java
// Minh họa một lựa chọn thiết kế khác, không ghép vào file ở mục 6.
sealed interface Shape permits Circle, Rectangle, Triangle {
    double area();
    String category();
}

record Circle(double radius) implements Shape {
    @Override
    public double area() { return Math.PI * radius * radius; }

    @Override
    public String category() { return "circle"; }
}

// Rectangle và Triangle cần triển khai các phương thức tương ứng.
```

Đây là **phương án polymorphism**. Nếu thêm một subtype mới và mở rộng `permits`, class mới phải triển khai các method đã cam kết, nhưng **các class hiện có và một switch dispatcher trung tâm không nhất thiết phải sửa**.

Nếu thêm một **thao tác trừu tượng mới** vào `Shape`, những subtype hiện tại sẽ cần triển khai method mới (trừ khi có một default implementation chung phù hợp). Mô hình này do đó thường thuận lợi cho hệ thống **liên tục có loại hình mới nhưng ít thay đổi bộ thao tác chung**.

So sánh hướng thay đổi:

| Tiêu chí | Sealed hierarchy + các pattern switch | Polymorphism đặt method trên Shape |
| --- | --- | --- |
| Thêm subtype mới | Thêm type, cập nhật `permits`, thêm case ở mỗi switch cần xử lý | Thêm type, cập nhật `permits`, triển khai các method bắt buộc trong subtype mới |
| Thêm thao tác mới phụ thuộc subtype | Thêm một switch operation, các case tập trung trong hàm mới | Thêm method vào interface/abstract class và triển khai ở các subtype |
| Khả năng compiler nhắc thiếu nơi xử lý | Exhaustiveness của switch expression, thiếu case báo lỗi | Interface/abstract method chưa implement cũng báo lỗi |
| Tổ chức code theo thao tác | Dễ đọc tất cả hình của một phép tính ở cùng một nơi | Logic của một phép tính phân tán giữa các subtype |
| Tổ chức code theo loại hình | Mỗi hình là dữ liệu, một số logic ở hàm ngoài | Dữ liệu và logic riêng thường nằm cùng một subtype |
| Mở rộng bằng plugin ngoài | Sealed đóng cản việc thêm direct subtype tùy ý | Vẫn bị giới hạn nếu interface cũng sealed; muốn mở cần thay thiết kế |
| Rủi ro khi thêm subtype | Có thể phải sửa nhiều switch; `default` che cảnh báo | Có thể phải triển khai nhiều method; code base class lớn |
| Hiệu năng | Tùy compiler, workload và JIT | Tùy dispatch, JIT và workload; không mặc nhiên nhanh hơn |

**Kết luận lựa chọn:** Pattern matching phù hợp khi **tập hình tương đối ổn định, thường xuyên thêm các phép phân tích mới**. Polymorphism phù hợp khi **nhiều subtype mới xuất hiện, bộ thao tác chung tương đối ổn định**. Mô hình kết hợp cũng hợp lệ: giữ `area()` có tính bất biến mạnh trên subtype, còn các thao tác báo cáo/serialization dùng pattern switch tập trung.

Không nên tranh luận “`switch` luôn xấu” hay “pattern matching thay thế OOP”. Cả hai đều có chi phí mở rộng theo hai trục khác nhau.

## 10. Đo bằng change experiment trong một repository thực tế

Để có số liệu có thể so sánh giữa hai thiết kế, tổ chức một thử nghiệm có kiểm soát:

1. **Chọn baseline giống nhau:** cùng số hình, cùng phép toán, cùng invariant và bộ test. Ví dụ `V=2`/`O=2`.
2. **Đặt yêu cầu thay đổi cụ thể:** “thêm Triangle tính diện tích và category”, không vừa đổi thuật toán, vừa rename package và refactor unrelated code.
3. **Thực hiện ở hai nhánh Git riêng** cho thiết kế pattern-switch và polymorphism.
4. **Đo diff thực tế:** file bị sửa, vị trí logic thêm/sửa, số case/method, dòng code mới và dòng code đổi.
5. **Biên dịch ngay sau khi thêm subtype nhưng trước khi xử lý hết:** ghi số lỗi compile tại các switch exhaustive hoặc subclass chưa implement method.
6. **Cập nhật đủ và chạy test:** công thức diện tích, input null, giá trị không hợp lệ, kiểu mới. Đo test bổ sung và những test bị ảnh hưởng.
7. **Lặp lại với thay đổi ở trục kia:** thêm `describeDimensions` mà không thêm subtype; so sánh số vị trí phải sửa.
8. **Review kết quả:** chi phí thay đổi, mức dễ phát hiện lỗi, khả năng đọc hiểu, xung đột merge, module boundaries và compatibility.
9. **Ghi số liệu kèm điều kiện:** version Java, cấu trúc file, compiler flags, kích thước model và quy tắc đếm. Tránh kết luận chung từ một chương trình đồ chơi.

Một báo cáo đo lường nên có cấu trúc:

| Metric | Baseline | Thêm Triangle | Thêm phép toán mới |
| --- | --- | --- | --- |
| Số biến thể `V` | 2 | 3 | 3 |
| Số thao tác có dispatch `O` | 2 | 2 | 3 |
| Số nhánh subtype lý thuyết `B` | 4 | 6 | 9 |
| Số nhánh mới | 0 | 2 | 3 |
| Số vị trí chỉnh sửa mã | Đặt baseline | Đếm diff thực tế | Đếm diff thực tế |
| Số file bị sửa | Đặt baseline | Đếm diff thực tế | Đếm diff thực tế |
| Kết quả compile/test | Pass baseline | Phải pass sau cập nhật | Phải pass sau cập nhật |

Ở hàng “thêm phép toán”, mô hình `O=3` giả định `describeDimensions` có ba case. Nếu triển khai phép toán mới bằng cách tái sử dụng `area` mà không dispatch, `O` không tăng và bảng cần được điều chỉnh.

### 10.1. Khi số biến thể và thao tác lớn hơn

Nếu thiết kế dùng một switch riêng cho **mỗi** thao tác và **một** case cho **mỗi** subtype, thì:

- `V=10`, `O=8` dẫn tới `B=80` case subtype.
- Thêm một subtype (`ΔV=1`) cần tới **8 case mới**, nếu cả tám thao tác đều cần phân biệt subtype.
- Thêm một thao tác phụ thuộc subtype (`ΔO=1`) cần tới **10 case mới**.

Đây là **phép ngoại suy theo mô hình đếm**, không phải kết quả benchmark hay đo một repository cụ thể. Với nhiều case dùng chung công thức, trừu tượng hóa hoặc thuật toán không cần subtype, có thể giảm chi phí. Với một số trường hợp, thêm subtype cũng cần thay serialization, validation, documentation, tests hoặc logic ở module khác; tổng tác động có thể **cao hơn** số case.

Nếu có nhiều thay đổi lặp lại, chỉ số có ý nghĩa hơn “số class” là **số vị trí logic mà một thay đổi nghiệp vụ buộc developer phải nhớ cập nhật**.

## 11. Exhaustiveness, compatibility và giới hạn của compiler

### 11.1. Compiler kiểm tra cấu trúc, không kiểm tra đúng công thức

`switch` exhaustive bảo đảm xử lý đủ trường hợp kiểu theo quy tắc ngôn ngữ, nhưng không xác minh `Math.PI*r*r` hay `b*h/2` là công thức phù hợp với domain. Trong `Triangle` chỉ lưu base/height, công thức diện tích đúng; nếu ứng dụng sau đó coi những biến này là độ dài hai cạnh không vuông góc, cùng một nhánh có thể sai về nghiệp vụ dù compiler hoàn toàn hài lòng.

Hãy test **giá trị biên, đơn vị và invariant**, không chỉ test rằng mọi switch có case.

### 11.2. Tác động đến client khi library thêm permitted subtype

Khi sealed library công khai được cập nhật để có thêm subtype, những client đã viết `switch expression` exhaustive theo tập variant cũ có thể cần biên dịch lại và cập nhật logic. Compiler giúp phát hiện lỗi nếu client được build với bản API mới; **không có bảo đảm** mọi binary client cũ tự hiểu biến thể mới chỉ nhờ library cập nhật.

Tùy tình huống chạy khác phiên bản giữa client/library, pattern switch thiếu nhánh có thể dẫn đến lỗi runtime thay vì một xử lý có ý nghĩa. Vì vậy, thay đổi permitted subtype phải đi cùng **versioning, kiểm tra binary/source compatibility, regression tests và release notes**.

### 11.3. `default`: lựa chọn policy, không phải luôn sai

Trong một hierarchy đóng, không dùng `default` có thể hữu ích để compiler chỉ ra nhánh còn thiếu. Nhưng đôi khi API thực sự yêu cầu một fallback có ý nghĩa cho biến thể lạ hoặc hierarchy mở. Lúc đó `default` là quyết định có chủ đích; phải test fallback và chấp nhận rằng khả năng compiler nhắc thiếu subtype sẽ giảm.

Đừng đưa ra quy tắc tuyệt đối “không bao giờ có default”; hãy hỏi **điều gì xảy ra khi biến thể mới xuất hiện**.

### 11.4. Độ mở của hierarchy

Một sealed parent có thể cho phép một direct subtype `non-sealed`; những subtype phía dưới nhánh ấy có thể mở rộng thêm theo quy tắc Java. Khi đó chỉ lấy `getPermittedSubclasses().length` **không cho biết đầy đủ số concrete runtime types**. Thậm chí nhiều mức `sealed` lồng nhau còn tạo độ sâu phân cấp khác nhau.

Với case study hình học ở đây, tất cả permitted subtypes đều là record final: số lượng variant trực tiếp và tập biến thể ở cấp xét trùng nhau. Đó là **giới hạn có chủ ý** để phép đo minh bạch.

## 12. Những sai lầm thường gặp khi “đo khả năng mở rộng”

| Sai lầm | Hướng xử lý |
| --- | --- |
| Đếm tổng số class rồi kết luận dễ mở rộng | Tách trục thêm subtype và thêm operation; dùng change experiment thực tế |
| Lấy `permitted:3` suy ra có đúng ba class trong mọi hierarchy | Đây chỉ là direct permitted subtypes; kiểm tra non-sealed và các tầng |
| Coi `B=V×O` luôn đúng | Chỉ đúng trong mô hình mỗi operation có case riêng cho từng variant; đếm thực tế |
| Đếm hai case mới như hai file sửa | Case/site/file là ba đơn vị khác nhau; đo diff cho `F` |
| Thêm `default` để biên dịch nhanh | Có thể giấu trường hợp subtype mới chưa được xử lý đúng |
| Kết luận compiler bảo đảm đúng diện tích | Compiler kiểm tra kiểu/exhaustiveness, không chứng minh công thức |
| Dùng `Triangle(base,height)` để tính luôn chu vi | Thiếu thông tin hình học; cần ba cạnh/đỉnh hoặc một định nghĩa tam giác đặc biệt |
| Bỏ qua `NaN` hoặc số âm | Thêm invariant và negative tests cho dimensions |
| Dùng benchmark thời gian chạy để đo extensibility | Tốc độ thực thi khác chi phí bảo trì và rủi ro thay đổi |
| Dựa vào một bản build thành công trên JDK mới để nói source tương thích 17 | Record patterns và pattern switch chính thức từ Java 21; test đúng target |
| Dùng `sealed` dù hệ thống cần plugin tự thêm subtype | Thiết kế điểm mở rộng, `non-sealed` hoặc SPI nếu domain đòi hỏi |
| Chỉ tính case mà bỏ test/docs/serializer | Đo đầy đủ tác động thay đổi ở production |

## 13. Checklist QA của case study

Một phép đo có thể tin cậy nên kiểm tra:

- **Model:** các biến thể có tên đúng ý nghĩa; mỗi constructor kiểm tra các invariant mong muốn.
- **Source/target:** JDK 21+, không bật preview cho tính năng final; command build và stdout phù hợp.
- **Tập biến thể:** `Shape.class.isSealed()==true`; `getPermittedSubclasses().length==3` trong mô hình thử.
- **Phép toán:** `area` có ba công thức đúng cho dữ liệu hợp lệ; `category` phân loại đúng ba subtype.
- **Null:** `category(null)` và `area(null)` có chính sách khác nhau nhưng đã được khai báo/test rõ.
- **Exhaustiveness:** bỏ case `Triangle` trong một switch expression gây lỗi compile như mong đợi.
- **Permits:** một class không nằm trong danh sách permitted không thể trực tiếp implement `Shape`.
- **Record arity:** pattern `Triangle(var b)` không khớp số component, bị compiler từ chối.
- **Đo lường:** ghi riêng `V`, `O`, `B`, `S`, `F` và `T`; không lấy một số thay cho tất cả.
- **Thử thay đổi:** đo cả hai kịch bản thêm hình và thêm thao tác, cùng một baseline.
- **Tác động sản phẩm:** nếu là public API, kiểm tra tương thích nguồn/nhị phân và thay đổi docs.

**Đã kiểm chứng thực nghiệm trong môi trường học tập:** chương trình Java ở mục 6 có đúng tám dòng stdout; ba ví dụ cố tình sai ở mục 7 được JDK 24 từ chối theo đúng lý do dự kiến. Những số như `B=4/6/9` là tính toán cấu trúc cho ví dụ, còn số file sửa trên repository thật cần được đo riêng.

## 14. Bài tập thực hành

### Bài tập 1 — thêm Square

Từ chương trình hoàn chỉnh, thêm `Square(double side)`. Cập nhật `Shape.permits`, thêm record có invariant `side>0` và hai case trong `area`, `category`.

Hãy dự đoán:

- Sau khi thêm `Square`, `V` tăng từ `3` lên `4`.
- Giữ `O=2`, `B` tăng từ `6` lên `8`.
- Số case mới là `2`, chưa tính case `null` vì không phải một variant.

**Ca kiểm thử gợi ý:** `Square(5)` cho diện tích `25.00`, `Square(0)` bị constructor từ chối. Trước khi bổ sung đủ các case, hãy thử build để xem compiler phản hồi ở những switch expression nào.

### Bài tập 2 — thêm thao tác có dispatch riêng

Sau khi có `Square`, thêm `describeDimensions(Shape)`. Với `V=4`, mỗi hình cần một case trình bày tham số. Khi đó, nếu không gộp nhánh và vẫn có `O=3`, `B=4×3=12`. Ghi số file, số case và số tests bổ sung **thật**, rồi so sánh với phương án polymorphism.

### Bài tập 3 — tránh dispatch không cần thiết

Viết:

```java
static boolean isLarge(Shape shape) {
    return area(shape) >= 100.0;
}
```

Đây là **phương thức minh họa** nằm trong class có `Shape` và `area`. Vì logic dùng lại `area`, nó **không tạo thêm một switch mới**. Trong cách định nghĩa `O` của bài, `isLarge` không cần tăng `O` nếu ta chỉ đếm những thao tác phân nhánh trực tiếp theo variant. Thảo luận xem cách tái sử dụng có làm giảm coupling khi thêm subtype hay không.

### Bài tập 4 — lựa chọn thiết kế cho một dự án thật

Giả sử thư viện hình học có:

- 15 loại hình và mỗi năm chỉ thêm 1 loại.
- 20 thuật toán báo cáo/phân tích, mỗi quý thêm vài thuật toán.

Hãy so sánh pattern switch và polymorphism theo **tần suất thay đổi**. Ghi một giả thuyết dựa trên `ΔV`/`ΔO`, rồi xác thực bằng một change experiment trong codebase mẫu. Không kết luận chỉ từ phép nhân `V×O`; cân nhắc tính tái sử dụng, đóng gói, độ phức tạp thuật toán và cách test.

## 15. Kết luận

**Đo khả năng mở rộng của hierarchy là đo chi phí và rủi ro của các thay đổi cụ thể.** Với case study hình học:

- Ban đầu có **2 biến thể × 2 thao tác = 4 nhánh subtype**.
- Khi thêm `Triangle`: **3 × 2 = 6**, cần **2 case mới** và một record/permits change.
- Khi thêm tiếp thao tác phụ thuộc subtype: **3 × 3 = 9**, thêm **3 case** trong một hàm mới.
- `sealed` + `switch expression` exhaustive giúp compiler báo thiếu nhánh, nhưng **không chứng minh công thức đúng**, không thay thế test, và không tự đo số file sửa.
- Polymorphism thường có ưu thế khi thêm subtype thường xuyên; pattern switch thường thuận tiện khi tập subtype ổn định nhưng liên tục thêm các thao tác độc lập.

Mọi kết luận nên dựa trên **baseline, diff thực tế, test và chính sách mở rộng của domain**, thay vì một khẩu hiệu về OOP hay pattern matching.

### Tài liệu chính thức

- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409)
- [JEP 395 — Records](https://openjdk.org/jeps/395)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Java SE 21 API — Class.getPermittedSubclasses](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#getPermittedSubclasses())
