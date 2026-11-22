# Đặt hành vi ở kiểu con hoặc xử lý bằng `instanceof` trong thiết kế `sealed` (Java 17)

Một hệ phân cấp `sealed` giới hạn những kiểu có thể trực tiếp kế thừa hoặc triển khai kiểu cha. Khi đã biết các kiểu con, câu hỏi thiết kế quan trọng là: **mỗi kiểu con có nên tự thực hiện hành vi của mình, hay mã bên ngoài nên dùng `instanceof` để xác định kiểu rồi xử lý?**

Cả hai lựa chọn đều hợp lệ trong Java 17. Chúng phục vụ những nhu cầu khác nhau: **đa hình** giúp phân phối hành vi vốn thuộc về đối tượng; **`instanceof`** giúp mã bên ngoài phân loại các biến thể khi việc xử lý thuộc về một ngữ cảnh khác, chẳng hạn trình bày, ánh xạ dữ liệu hoặc tích hợp với hệ thống ngoài.

Bài học này tập trung vào cách lựa chọn, kết hợp và duy trì hai cách đó khi làm việc với `sealed class`, `sealed interface` và các kiểu con trong Java 17.

## 1. Nền tảng: `sealed` giới hạn loại đối tượng, không quyết định nơi đặt hành vi

Từ Java 17, `sealed` là tính năng chính thức của ngôn ngữ. Ví dụ:

```java
sealed interface Shape permits Circle, Rectangle {
}

record Circle(double radius) implements Shape {
}

record Rectangle(double width, double height) implements Shape {
}
```

`Shape` chỉ cho phép `Circle` và `Rectangle` trực tiếp triển khai nó. Hai `record` đều ngầm định là `final`, nên không thể có lớp con của chúng. Trong hệ phân cấp này, các biến thể cụ thể được đóng tại hai kiểu đã khai báo.

Một kiểu trực tiếp kế thừa/triển khai `sealed` phải thuộc một trong ba dạng:

- **`final`:** dừng mở rộng nhánh đó; `record` là `final` một cách ngầm định.
- **`sealed`:** tiếp tục kiểm soát những kiểu con được phép.
- **`non-sealed`:** mở nhánh cho những kiểu con khác kế thừa/triển khai theo quy tắc Java thông thường.

Ví dụ:

```java
sealed interface Document permits PdfDocument, ExtensibleDocument {
}

final class PdfDocument implements Document {
}

non-sealed class ExtensibleDocument implements Document {
}
```

Tuy `Document` chỉ có hai **kiểu trực tiếp** được cấp phép, bạn vẫn có thể tạo lớp con của `ExtensibleDocument`. Vì vậy, `sealed` không tự bảo đảm **mọi lớp cụ thể có thể xuất hiện** đều nằm trong một danh sách hữu hạn nếu có nhánh `non-sealed`.

Trong một **named module**, các kiểu con trực tiếp được cấp phép phải nằm trong cùng module với kiểu `sealed`. Nếu ở **unnamed module**, chúng phải nằm trong cùng package. Những ví dụ gọn dưới đây đặt các kiểu trong cùng tệp để dễ thực hành.

`sealed` giải đáp câu hỏi **“những kiểu nào được phép tồn tại trong hệ phân cấp?”**. Nó không tự giải đáp câu hỏi **“hành vi nên nằm ở đâu?”**.

## 2. Hai phương pháp xử lý biến thể

### Phương pháp A: đặt hành vi ở kiểu con, gọi qua đa hình

Kiểu cha công bố một hợp đồng hành vi. Mỗi kiểu con triển khai cách thực hiện phù hợp:

```java
sealed interface Shape permits Circle, Rectangle {
    double area();
}

record Circle(double radius) implements Shape {
    @Override
    public double area() {
        return Math.PI * radius * radius;
    }
}

record Rectangle(double width, double height) implements Shape {
    @Override
    public double area() {
        return width * height;
    }
}
```

Mã gọi không cần hỏi kiểu cụ thể:

```java
double calculate(Shape shape) {
    return shape.area();
}
```

JVM phân phối lời gọi `area()` đến triển khai của đối tượng thực tế. Đây là **đa hình theo phương thức** (*method overriding / dynamic dispatch*).

Lợi ích chính:

1. **Phân phối hành vi ở đúng nơi chứa dữ liệu và bất biến:** công thức diện tích của hình tròn nằm ở `Circle`, của hình chữ nhật nằm ở `Rectangle`.
2. **Mã sử dụng đơn giản:** nhiều nơi có thể gọi `shape.area()` mà không lặp lại chuỗi kiểm tra kiểu.
3. **Bổ sung biến thể được compiler hỗ trợ:** nếu thêm một kiểu con cụ thể nhưng chưa triển khai phương thức trừu tượng cần thiết, compiler báo lỗi.
4. **Đóng gói:** triển khai của kiểu con có thể sử dụng chi tiết riêng, thay đổi công thức mà không bắt các caller phải sửa.

Đổi lại, nếu cứ thêm nhiều **hành vi không cùng trách nhiệm** vào kiểu cha, mọi kiểu con phải mang thêm phương thức và phụ thuộc không phù hợp. Chẳng hạn, `Shape` không nhất thiết phải biết cách tạo HTML, ghi JSON hay gọi một API của giao diện người dùng.

### Phương pháp B: giữ kiểu con làm dữ liệu, xử lý từ bên ngoài bằng `instanceof`

Nếu một chức năng thuộc về **bộ phận sử dụng đối tượng**, mã bên ngoài có thể phân nhánh theo kiểu:

```java
static String label(Shape shape) {
    if (shape instanceof Circle circle) {
        return "Hình tròn, bán kính " + circle.radius();
    }
    if (shape instanceof Rectangle rectangle) {
        return "Hình chữ nhật " + rectangle.width()
                + " x " + rectangle.height();
    }
    throw new IllegalStateException("Kiểu hình chưa được xử lý");
}
```

Đây là **pattern matching for `instanceof`**, một tính năng ổn định trong Java 17. Biểu thức `shape instanceof Circle circle` đồng thời:

- Kiểm tra đối tượng có thuộc kiểu `Circle` hay không.
- Nếu đúng, ràng buộc biến `circle` đã có kiểu `Circle`; không cần viết `(Circle) shape`.
- Cho phép truy cập `circle.radius()` ở nhánh mà compiler xác định biến đó chắc chắn đã được gán.

Phần `label` có thể phục vụ một màn hình, một cách xuất dữ liệu, một báo cáo cụ thể. Việc đặt nó ngoài `Shape` tránh đưa nhu cầu trình bày vào hợp đồng miền (*domain contract*).

Đổi lại, **`if` / `else` kiểm tra kiểu không được Java 17 xác nhận là đầy đủ cho toàn bộ hệ phân cấp `sealed`**. Khi thêm biến thể, hàm xử lý ngoài có thể vẫn biên dịch thành công nhưng đi vào nhánh dự phòng lúc chạy. Người duy trì cần theo dõi các vị trí phân nhánh.

## 3. Ví dụ hoàn chỉnh: kết hợp hai cách trong cùng một thiết kế

Trong hệ thống thực tế, một mô hình có thể cần **hành vi miền ở kiểu con** và **hành vi trình bày ở bên ngoài**. Hai cơ chế không loại trừ nhau.

Tạo tệp **`ShapeDemo.java`**:

```java
import java.util.List;
import java.util.Objects;

sealed interface Shape permits Circle, Rectangle {
    double area();
}

record Circle(double radius) implements Shape {
    Circle {
        if (!Double.isFinite(radius) || radius <= 0) {
            throw new IllegalArgumentException("radius must be positive and finite");
        }
    }

    @Override
    public double area() {
        return Math.PI * radius * radius;
    }
}

record Rectangle(double width, double height) implements Shape {
    Rectangle {
        if (!Double.isFinite(width) || !Double.isFinite(height)
                || width <= 0 || height <= 0) {
            throw new IllegalArgumentException("width and height must be positive and finite");
        }
    }

    @Override
    public double area() {
        return width * height;
    }
}

public class ShapeDemo {
    // Hành vi phục vụ một màn hình: giữ ngoài mô hình miền.
    static String labelForUi(Shape shape) {
        Objects.requireNonNull(shape, "shape");

        if (shape instanceof Circle circle) {
            return "Hình tròn, r=" + circle.radius();
        }
        if (shape instanceof Rectangle rectangle) {
            return "Hình chữ nhật, w=" + rectangle.width()
                    + ", h=" + rectangle.height();
        }

        throw new IllegalStateException(
                "Chưa hỗ trợ kiểu: " + shape.getClass().getName());
    }

    public static void main(String[] args) {
        List<Shape> shapes = List.of(
                new Circle(2.0),
                new Rectangle(3.0, 4.0));

        for (Shape shape : shapes) {
            System.out.println(labelForUi(shape));
            System.out.println("Diện tích: " + shape.area());
        }
    }
}
```

Biên dịch và chạy bằng JDK 17:

```bash
javac --release 17 ShapeDemo.java
java ShapeDemo
```

Đầu ra minh họa:

```text
Hình tròn, r=2.0
Diện tích: 12.566370614359172
Hình chữ nhật, w=3.0, h=4.0
Diện tích: 12.0
```

Có hai quyết định thiết kế cần chú ý:

**Thứ nhất, `area()` là hành vi miền.** Hình tròn và hình chữ nhật tính diện tích bằng công thức riêng. Gọi `shape.area()` thể hiện đúng trách nhiệm của đối tượng, giúp người sử dụng không phải biết chi tiết từng kiểu.

**Thứ hai, `labelForUi()` là hành vi dành riêng cho ngữ cảnh hiển thị.** Nó phụ thuộc định dạng chuỗi và cách trình bày; miền hình học không có lý do phải chứa từng cách diễn đạt cho mỗi màn hình hoặc ngôn ngữ.

Các `record` cũng kiểm tra dữ liệu bất biến lúc khởi tạo. Dù hành vi nào đặt ở đâu, **tính hợp lệ của dữ liệu** thuộc về kiểu sở hữu dữ liệu: không nên trông chờ mọi caller đều tự kiểm tra bán kính dương và hữu hạn.

> Ví dụ sử dụng `double` phù hợp với phép toán hình học cơ bản. Nếu bài toán chuyển sang tiền tệ hoặc độ chính xác thập phân nghiêm ngặt, nên chọn biểu diễn phù hợp như `BigDecimal` thay vì sao chép trực tiếp các phép toán `double`.

## 4. Ví dụ: chỉ dùng `instanceof` cho một phép chiếu dữ liệu

Giả sử có kết quả thanh toán từ một tầng nghiệp vụ. Giao diện người dùng cần biến chúng thành thông báo. Kết quả thanh toán biểu diễn **các trạng thái**, trong khi câu chữ hiển thị thuộc về ứng dụng giao diện.

Tạo tệp **`PaymentViewDemo.java`**:

```java
import java.util.Objects;

public class PaymentViewDemo {
    sealed interface PaymentResult permits Paid, Rejected, Pending {
    }

    record Paid(String transactionId) implements PaymentResult {
    }

    record Rejected(String reasonCode) implements PaymentResult {
    }

    record Pending() implements PaymentResult {
    }

    static String toUserMessage(PaymentResult result) {
        Objects.requireNonNull(result, "result");

        if (result instanceof Paid paid) {
            return "Giao dịch " + paid.transactionId() + " đã hoàn tất.";
        }
        if (result instanceof Rejected rejected) {
            return "Thanh toán thất bại. Mã: " + rejected.reasonCode();
        }
        if (result instanceof Pending) {
            return "Giao dịch đang được xử lý.";
        }

        throw new IllegalStateException(
                "Chưa hỗ trợ kết quả: " + result.getClass().getName());
    }

    public static void main(String[] args) {
        PaymentResult result = new Paid("TX-17");
        System.out.println(toUserMessage(result));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 PaymentViewDemo.java
java PaymentViewDemo
```

Kết quả:

```text
Giao dịch TX-17 đã hoàn tất.
```

Ở đây, `PaymentResult` không bắt buộc khai báo `toUserMessage()` vì câu chữ trình bày không phải bản chất của trạng thái thanh toán. Sau này có thể có `toAdminMessage`, `toLogFields` hoặc `toCsvRow` trong những thành phần khác mà không thay đổi các kiểu dữ liệu.

Tuy nhiên, nếu ứng dụng tạo rất nhiều hàm kiểu `toUserMessage` với các chuỗi `instanceof` gần như giống nhau, đó là dấu hiệu nên đánh giá lại thiết kế: nhóm hành vi nào thực sự thuộc về kiểu dữ liệu, nhóm nào nên gom ở một lớp xử lý riêng, hoặc có cần một cơ chế phân phối tập trung hay không.

Trong ứng dụng thực tế, còn cần **xác thực dữ liệu** (`transactionId` không rỗng, `reasonCode` hợp lệ), **quốc tế hóa thông báo** và tránh hiển thị mã lỗi nội bộ nhạy cảm trực tiếp. Những chi tiết đó là trách nhiệm của mô hình và tầng trình bày tương ứng, không do `sealed` tự giải quyết.

## 5. So sánh hai cách dưới góc nhìn thiết kế

| Câu hỏi | Hành vi ở kiểu con (đa hình) | Xử lý bằng `instanceof` ở bên ngoài |
| --- | --- | --- |
| Ai sở hữu cách thực hiện? | Chính kiểu con. | Thành phần xử lý/phân loại đối tượng. |
| Mã sử dụng nhìn thấy gì? | `shape.area()`, không cần biết lớp cụ thể. | `if (shape instanceof Circle c) ...`. |
| Thêm một **kiểu con** mới? | Compiler yêu cầu kiểu con cụ thể hiện thực hợp đồng trừu tượng; caller thường giữ nguyên. | Phải kiểm tra từng nơi phân nhánh; Java 17 không kiểm tra tính đầy đủ của chuỗi `if`. |
| Thêm một **loại thao tác** mới? | Có thể phải thêm phương thức vào kiểu cha và sửa tất cả kiểu con. | Có thể viết hàm/lớp xử lý mới mà không đổi kiểu con. |
| Đóng gói quy tắc miền? | Rất phù hợp khi hành vi gắn chặt với dữ liệu/bất biến của biến thể. | Dễ làm rò rỉ logic miền ra nhiều caller nếu lạm dụng. |
| Phụ thuộc vào UI, file, framework, API ngoài? | Có nguy cơ làm mô hình miền phụ thuộc vào hạ tầng. | Có thể giữ phụ thuộc trong thành phần chuyên trách. |
| Kiểm thử | Kiểm thử hành vi mỗi biến thể qua hợp đồng chung. | Kiểm thử mọi nhánh của bộ xử lý và trường hợp không hỗ trợ. |
| Mức độ kết dính với các biến thể | Mã gọi ít phụ thuộc lớp cụ thể. | Bộ xử lý cần biết tên và dữ liệu của các lớp cụ thể. |

Không có quy tắc “luôn ưu tiên đa hình” hoặc “`sealed` thì luôn phải dùng `instanceof`”. Điều quan trọng là xác định **ai chịu trách nhiệm về hành vi** và **loại thay đổi nào xảy ra thường xuyên**.

## 6. Đặt hành vi ở kiểu con khi nào?

Ưu tiên một phương thức trong kiểu cha và triển khai ở các kiểu con khi có các dấu hiệu sau.

### 6.1. Hành vi là năng lực tự nhiên của biến thể

Ví dụ:

- `Shape.area()`: mỗi hình biết công thức diện tích.
- `TaxRule.calculateTax(...)`: mỗi quy tắc thuế xác định cách tính theo chính sách của nó.
- `Expression.evaluate(...)`: mỗi nút biểu thức biết cách đánh giá theo toán hạng của nó, nếu đây là trách nhiệm được chọn cho mô hình.
- `ValidationRule.validate(...)`: mỗi quy tắc kiểm tra điều kiện của chính nó.

Mã caller thường chỉ cần **yêu cầu kết quả**, không cần hiểu lớp cụ thể và thuật toán từng biến thể.

### 6.2. Thêm kiểu con nhưng giữ ổn định tập hành vi

Nếu hệ thống thường mở rộng danh sách biến thể, ví dụ thêm một cách tính chiết khấu, một bộ lọc hay một loại quy tắc, giao diện có phương thức đa hình giúp định vị việc triển khai tại kiểu mới.

Với hệ `sealed`, việc thêm biến thể còn đòi hỏi cập nhật danh sách `permits` hoặc cây kế thừa phù hợp. Điều này tạo ra một điểm kiểm soát cấu trúc rõ ràng.

### 6.3. Nhiều nơi cùng cần một quy tắc nghiệp vụ

Nếu màn hình, batch job và API đều cần tính cùng một giá trị theo kiểu đối tượng, đặt logic đó trong kiểu con tránh việc mỗi tầng tự lặp lại một chuỗi `instanceof` rồi tính lại theo cách riêng.

### 6.4. Muốn compiler nhắc việc triển khai hợp đồng

Ví dụ:

```java
sealed interface Rule permits AllowRule, DenyRule {
    boolean matches(String input);
}
```

Một lớp cụ thể triển khai `Rule` phải cung cấp `matches`, trừ khi kế thừa được một cách triển khai hợp lệ. Điều này hữu ích hơn việc để từng caller nhớ kiểm tra từng loại `Rule`.

Lưu ý: nếu khai báo `default` method trong interface hoặc cung cấp implementation ở lớp cha, compiler sẽ không buộc mỗi kiểu con ghi đè. Hãy thiết kế hợp đồng có chủ ý, tránh một implementation mặc định chỉ ném `UnsupportedOperationException` để che việc một biến thể chưa được xử lý.

## 7. Dùng `instanceof` khi nào?

`instanceof` phù hợp nếu thao tác **chủ động cần biết biến thể cụ thể** và đặt ở nơi bên ngoài mô hình có ý nghĩa hơn.

### 7.1. Chuyển đổi sang biểu diễn khác

Các tác vụ như trình bày trên UI, ánh xạ sang DTO, định dạng thông điệp hay xuất báo cáo có thể phụ thuộc kênh truyền hoặc người đọc. Mô hình miền thường không nên chứa riêng phương thức `toHtmlForAdmin()`, `toPdfForCustomer()`, `toKafkaPayload()` cho từng kênh.

### 7.2. Viết một chức năng bổ sung mà chưa muốn mở rộng hợp đồng miền

Ví dụ một chức năng debug tạm thời phân loại các biến thể để in thông tin, hoặc một bộ chuyển đổi ở ranh giới tích hợp. Nếu phạm vi nhỏ và số kiểu ít, một hàm `instanceof` rõ ràng dễ đọc hơn nhiều lớp trừu tượng phụ.

### 7.3. Kiểu dữ liệu được sở hữu bởi module hoặc thư viện khác

Nếu không được thay đổi khai báo kiểu cha/kiểu con, việc xử lý từ bên ngoài có thể phù hợp. Với thư viện bên ngoài, vẫn phải tôn trọng **API công khai** của các kiểu và tính ổn định của hợp đồng khi thư viện nâng cấp.

### 7.4. Tập biến thể ổn định, nhưng hay bổ sung thao tác

Giả sử một mô hình cây cú pháp có những loại nút cố định, nhưng phải thêm các phép xử lý như in đẹp, thống kê, dịch sang định dạng khác. Mỗi phép xử lý có thể được tổ chức trong một thành phần chuyên trách thay vì liên tục bổ sung phương thức vào mọi lớp nút.

Khi số thao tác hoặc độ phức tạp tăng mạnh, có thể cân nhắc **Visitor/double dispatch**. Tuy nhiên, Visitor tạo thêm interface và phương thức điều phối; với một vài trường hợp trong Java 17, `instanceof` pattern matching thường đơn giản và đủ rõ ràng.

## 8. Vấn đề mở rộng: thêm biến thể khác với thêm thao tác

Hãy tưởng tượng hệ `sealed` ban đầu chỉ có `Circle` và `Rectangle`.

**Trường hợp A — thêm `Triangle`:** 

- Với thiết kế đa hình, `Triangle` phải cung cấp `area()` nếu hợp đồng yêu cầu.
- Những caller chỉ gọi `shape.area()` thường không đổi.
- Những hàm kiểu `labelForUi` cần được xem lại để biết cách hiển thị `Triangle`.

**Trường hợp B — thêm xuất bản vẽ sang một định dạng mới:**

- Nếu có một tầng xuất bản vẽ riêng, bạn có thể thêm hàm xuất dữ liệu ở tầng đó.
- Không nhất thiết sửa `Circle` và `Rectangle` nếu xuất định dạng không phải trách nhiệm miền.
- Bộ xuất dữ liệu mới sẽ cần xử lý các biến thể mà nó hỗ trợ.

Mô hình lựa chọn:

```text
Hành vi đang thiết kế
        |
        +-- Thuộc quy tắc/invariant của chính biến thể?
        |       |
        |       +-- Có --> Xem xét phương thức đa hình trong kiểu cha
        |
        +-- Phụ thuộc ngữ cảnh bên ngoài (UI, DTO, tích hợp...)?
                |
                +-- Có --> Xem xét bộ xử lý bên ngoài với instanceof

Sau đó hỏi tiếp:
  - Những nơi nào sẽ cần cùng hành vi?
  - Dự án thường thêm biến thể hay thêm thao tác?
  - Hợp đồng giữa các module cần ổn định ở mức nào?
  - Nhánh nào phải được cập nhật khi mô hình thay đổi?
```

Một hệ thống tốt thường phân chia **nhiều hành vi khác nhau** theo trách nhiệm tương ứng, thay vì ép tất cả vào duy nhất một kỹ thuật.

## 9. Những điều cần lưu ý riêng với Java 17

### 9.1. `instanceof` pattern matching đã ổn định

Bạn có thể dùng:

```java
if (shape instanceof Circle circle) {
    System.out.println(circle.radius());
}
```

Không cần ép kiểu thủ công:

```java
if (shape instanceof Circle) {
    Circle circle = (Circle) shape;
    System.out.println(circle.radius());
}
```

Đoạn thứ hai vẫn là Java hợp lệ nhưng dài hơn và dễ khiến bạn viết hai lần biểu thức phân loại. Trong mã Java 17 mới, dạng đầu tiên thường dễ đọc hơn.

Biến pattern chỉ dùng được ở những vùng mà compiler xác định phép kiểm tra kiểu đã thành công (*flow scoping*). Ví dụ:

```java
if (!(shape instanceof Circle circle)) {
    return;
}

// Sau nhánh return, compiler biết shape là Circle ở luồng còn lại.
System.out.println(circle.radius());
```

Ví dụ dùng dạng trên **bên trong một phương thức trả về `void`**; nếu phương thức cần trả giá trị, hãy điều chỉnh câu lệnh `return` cho phù hợp.

### 9.2. `null` và xử lý không được hỗ trợ

`instanceof` trả về `false` khi giá trị đối tượng là `null`. Do đó:

```java
if (shape instanceof Circle circle) {
    // Chỉ vào đây khi shape là một Circle thực sự.
}
```

Nếu chức năng không chấp nhận `null`, kiểm tra rõ ngay đầu hàm:

```java
Objects.requireNonNull(shape, "shape");
```

Sau các nhánh, có thể ném `IllegalStateException` khi gặp biến thể chưa được hỗ trợ để phát hiện thay đổi chưa được cập nhật. Tránh trả về một giá trị “có vẻ hợp lệ” nhằm che việc quên xử lý kiểu mới.

### 9.3. `sealed` không biến chuỗi `if` thành kiểm tra exhaustiveness ở compile time

Java 17 **không tự bắt buộc** một chuỗi:

```java
if (value instanceof A a) {
    // ...
} else if (value instanceof B b) {
    // ...
}
```

phải có nhánh cho mọi kiểu đã khai báo trong `permits`. Bởi vậy, khi sửa hệ phân cấp, cần cập nhật các bộ xử lý ngoài và kiểm thử các biến thể liên quan.

Đừng nhầm với **pattern matching for `switch`**: trong Java 17, tính năng này vẫn ở dạng **preview** (JEP 406), cần chế độ bật preview; ví dụ kiểu `switch (shape) { case Circle c -> ... }` không phải cú pháp chuẩn được bật mặc định của Java 17. Để bài thực hành Java 17 sử dụng các tính năng ổn định, các ví dụ ở đây dùng `if` với `instanceof`.

Ngoài ra, **record patterns** dùng cú pháp giải cấu trúc như `instanceof Circle(double radius)` không thuộc tập tính năng ổn định của Java 17; hãy truy cập thành phần `record` bằng accessor như `circle.radius()`.

### 9.4. `non-sealed` mở rộng tập trường hợp thực tế

Nếu một nhánh là `non-sealed`, không thể mặc định rằng chỉ vài kiểu cụ thể bạn biết lúc viết code là tất cả các kiểu có thể gặp. Một hàm `instanceof` liệt kê vài lớp cụ thể có thể bỏ sót lớp con mới của nhánh mở đó.

Trong một nhánh mở, cách xử lý dự phòng, hợp đồng đa hình ở kiểu cơ sở hoặc giao diện extension rõ ràng càng quan trọng.

### 9.5. Đặt quy tắc đúng tầng khi cần dịch vụ ngoài

Không phải mọi hành vi nghiệp vụ đều nhất thiết là phương thức trên `record` hay entity. Nếu quy tắc cần truy cập database, gửi HTTP, phát sự kiện hoặc dùng nhiều repository, một **application/domain service** với dependency injection thường phù hợp hơn việc nhồi mọi phụ thuộc vào kiểu con chỉ để “có đa hình”.

Khi xử lý trong service, bạn vẫn có thể dùng:

- **Đa hình** để lấy những thông tin/hành vi nội tại của biến thể.
- **`instanceof`** để phân nhánh khi tích hợp theo từng trường hợp.
- **Strategy/registry** nếu cần các bộ xử lý thay thế được hoặc đăng ký theo cấu hình.

Sự lựa chọn giữa đa hình và `instanceof` phụ thuộc trách nhiệm thiết kế, không phải chỉ vào việc hành vi có tên là “nghiệp vụ” hay “kỹ thuật”.

## 10. Những lỗi thiết kế hay gặp

### Lỗi 1: Lặp một chuỗi `instanceof` để thực hiện cùng quy tắc miền

Ví dụ không nên nhân rộng:

```java
double calculateArea(Shape shape) {
    if (shape instanceof Circle c) {
        return Math.PI * c.radius() * c.radius();
    }
    if (shape instanceof Rectangle r) {
        return r.width() * r.height();
    }
    throw new IllegalStateException("Unknown shape");
}
```

Nếu đây là một quy tắc miền cần ở nhiều nơi, có thể thay bằng `shape.area()`. Khi mỗi caller tự tính, rất dễ có chỗ quên biến thể, tính sai công thức hoặc áp dụng quy tắc không nhất quán.

### Lỗi 2: Ép tất cả cách trình bày vào kiểu con

Ví dụ một interface `PaymentResult` có `renderHtml()`, `renderMobileScreen()`, `toCsv()`, `createEmailBody()`... thường khiến mô hình phụ thuộc định dạng và công nghệ bên ngoài.

Nếu những thao tác này do các tầng khác sở hữu và thay đổi độc lập với trạng thái thanh toán, hãy cân nhắc bộ chuyển đổi/formatter riêng.

### Lỗi 3: Coi `sealed` là một cơ chế tự động xử lý mọi biến thể

`sealed` chỉ **kiểm soát tập kiểu con trực tiếp** theo quy tắc ngôn ngữ. Nó không tự cài logic, không chạy vòng qua các kiểu con, và không làm một chuỗi `if` thiếu nhánh trở thành lỗi compile.

### Lỗi 4: Thêm `default` method chỉ để khỏi sửa lớp con

```java
sealed interface Action permits SaveAction, DeleteAction {
    default void execute() {
        throw new UnsupportedOperationException("Not implemented");
    }
}
```

Thiết kế này có thể đẩy lỗi thiếu triển khai đến runtime. Nếu mọi biến thể buộc phải có `execute`, cân nhắc khai báo phương thức trừu tượng:

```java
sealed interface Action permits SaveAction, DeleteAction {
    void execute();
}
```

Lúc đó các kiểu con cụ thể phải triển khai hợp đồng, trừ khi đã kế thừa được một triển khai hợp lệ ở nhánh cha.

### Lỗi 5: Trộn điều kiện theo trạng thái và phân loại theo kiểu một cách tùy tiện

`instanceof` hỏi đối tượng thuộc **kiểu nào**, không phải “trạng thái nghiệp vụ hiện tại là gì”. Ví dụ một `Order` có thể thay đổi trạng thái từ đang xử lý sang hoàn tất mà không cần biến thành lớp khác. Không nên tạo vô số subtype chỉ vì muốn thay mọi câu lệnh `if (status == ...)` bằng kiểm tra kiểu.

Chọn `sealed` khi các biến thể thực sự có bản sắc và hợp đồng khác nhau; chọn thuộc tính trạng thái khi đó là dữ liệu có thể thay đổi của cùng một thực thể.

## 11. Bài tập áp dụng

### Bài tập 1: Thiết kế hệ quy tắc giảm giá

Bạn có `DiscountRule` với hai kiểu `FixedDiscount` và `PercentageDiscount`. Cả hệ thống bán hàng và batch job đều cần tính số tiền sau giảm theo cùng một quy tắc.

**Hướng thiết kế phù hợp:** khai báo một phương thức như `applyTo(BigDecimal originalPrice)` trong `DiscountRule`; mỗi kiểu triển khai tính toán của mình. Đưa kiểm tra các tham số như “số tiền không âm” hoặc “tỷ lệ hợp lệ” vào lớp/record sở hữu dữ liệu. Không cần để từng caller tự rẽ nhánh theo `instanceof` để tính lại công thức.

### Bài tập 2: Xuất trạng thái đơn hàng sang các kênh

Bạn có các trạng thái kết quả `Accepted`, `Rejected`, `Pending` và cần tạo thông điệp cho màn hình web, log vận hành và tệp CSV. Các cách biểu diễn thay đổi theo kênh.

**Hướng thiết kế phù hợp:** giữ thông tin trạng thái trong các biến thể `sealed`, xây dựng formatter/mapper trong các tầng chịu trách nhiệm cho từng kênh. `instanceof` có thể dùng để đọc dữ liệu của từng biến thể trong một bộ xử lý nhỏ, rõ ràng. Nếu số bộ xử lý nhiều và có nhiều nhánh trùng nhau, đánh giá lại kiến trúc hoặc cân nhắc Visitor.

### Bài tập 3: Thêm biến thể mới

Giả sử bạn thêm `Triangle` vào ví dụ `Shape`.

1. Cần cập nhật `permits` của `Shape`.
2. `Triangle` phải triển khai `area()` nếu là kiểu cụ thể và không kế thừa một implementation.
3. `ShapeDemo.labelForUi` cần biết cách hiển thị `Triangle`.
4. Các caller chỉ gọi `shape.area()` không cần thay vì bổ sung một nhánh kiểm tra kiểu mới.

Đây là khác biệt rõ nhất giữa việc **mở rộng hệ kiểu con** và **mở rộng các phép xử lý bên ngoài**.

## 12. Ghi nhớ khi thiết kế

- **Dùng đa hình** khi đó là hành vi tự nhiên, nhất quán và có ý nghĩa đối với mọi biến thể của kiểu cha.
- **Dùng `instanceof` pattern matching** khi một chức năng bên ngoài cần phân biệt các kiểu cụ thể để chuyển đổi, trình bày hoặc tích hợp.
- **Kết hợp hai cách** khi đối tượng vừa có hành vi miền, vừa được nhiều thành phần bên ngoài tiêu thụ.
- **Không dựa vào `sealed` để giả định chuỗi `if` đã bao phủ hết các kiểu.** Xem lại mọi bộ xử lý khi danh sách biến thể thay đổi, đặc biệt nếu có nhánh `non-sealed`.
- **Với Java 17**, `sealed` và pattern matching for `instanceof` đều là tính năng ổn định; tránh phụ thuộc vào cú pháp pattern matching for `switch` ở chế độ preview khi không có chủ đích bật preview.

## Tài liệu tham khảo chính thức

- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): mô hình giới hạn lớp con, `permits`, `sealed` và `non-sealed` trong Java 17.
- [JEP 394 — Pattern Matching for `instanceof`](https://openjdk.org/jeps/394): cú pháp kiểm tra kiểu kèm biến pattern và quy tắc phạm vi biến.
- [JEP 395 — Records](https://openjdk.org/jeps/395): kiểu dữ liệu `record`, tính `final` và accessor.
- [Java Language Specification, Java SE 17 — Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html): khai báo lớp, phương thức và phân cấp `sealed`.
- [Java Language Specification, Java SE 17 — Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html): `sealed interface` và các quy tắc triển khai.
- [JEP 406 — Pattern Matching for `switch` (Preview)](https://openjdk.org/jeps/406): phân biệt tính năng thử nghiệm ở Java 17 với các cú pháp ngôn ngữ đã ổn định.
