# So sánh phân cấp mở, `final` và `sealed` trong Java 17

**Chủ đề:** Java 17 — Sealed cơ bản  
**Bài học:** So sánh phân cấp mở, `final` và `sealed`

Khi thiết kế một hệ thống hướng đối tượng, câu hỏi quan trọng là: **ai được phép tạo lớp con hoặc triển khai interface của một kiểu?** Trong Java 17, có ba cách thường gặp để kiểm soát khả năng mở rộng của một phân cấp kiểu:

- **Phân cấp mở (open hierarchy):** Lớp hoặc interface cho phép những kiểu hợp lệ khác kế thừa, triển khai theo các quy tắc truy cập thông thường.
- **`final`:** Chặn mọi lớp khác kế thừa **lớp** được đánh dấu `final`.
- **`sealed`:** Giới hạn **những kiểu con trực tiếp** được phép kế thừa một lớp hoặc triển khai một interface, nhưng vẫn cho phép thiết kế nhiều nhánh con với các mức mở rộng khác nhau.

`final` đã tồn tại từ lâu trong Java. `sealed` class và interface được chuẩn hóa ở **Java 17** theo JEP 409, sau giai đoạn preview ở Java 15 và 16. Java 17 không có từ khóa `open` cho lớp thông thường; “phân cấp mở” là cách gọi một thiết kế có thể tiếp tục mở rộng.

## 1. Hình dung sự khác nhau

Giả sử ứng dụng cần biểu diễn nhiều loại kết quả xử lý yêu cầu:

```text
Phân cấp mở:
Result
├── Success
├── Failure
├── Waiting
└── ... (có thể xuất hiện thêm kiểu triển khai)

Lớp final:
FinalResult
└── (không được có lớp con)

Phân cấp sealed:
Result (sealed)
├── Success (final)
├── Failure (final)
└── Waiting (non-sealed)
    ├── WaitingForBank
    └── ... (nhánh này có thể được mở rộng)
```

Trong phân cấp mở, tác giả `Result` không kiểm soát toàn bộ các lớp con về sau. Với `final`, tác giả đóng hẳn khả năng tạo lớp con. Với `sealed`, tác giả chọn danh sách **các kiểu con trực tiếp**, rồi chỉ định xem từng nhánh đó được đóng, tiếp tục giới hạn hay mở trở lại.

Điểm then chốt: **`sealed` giới hạn một tầng kế thừa trực tiếp**. Nó không tự động làm cho mọi kiểu con ở tất cả các tầng đều đóng.

## 2. Bảng so sánh tổng quan

| Tiêu chí | Phân cấp mở | Lớp `final` | Phân cấp `sealed` |
|---|---|---|---|
| Cách khai báo điển hình | `class A`, `interface A` | `final class A` | `sealed class A permits ...` hoặc `sealed interface A permits ...` |
| Có được tạo kiểu con trực tiếp? | Có, nếu đáp ứng điều kiện kế thừa và truy cập | Không | Chỉ các kiểu con được cho phép |
| Có danh sách kiểu con trực tiếp cố định? | Không | Không có kiểu con | Có |
| Có thể cho phép mở rộng sâu hơn? | Có | Không qua chính lớp `final` | Có, thông qua nhánh `non-sealed` hoặc một phân cấp `sealed` tiếp theo |
| Dùng được cho `interface`? | Có | Không thể khai báo `final interface` | Có |
| Thích hợp khi | Muốn bên ngoài tự do bổ sung hành vi, tích hợp plugin | Muốn một kiểu không bị kế thừa | Muốn quản lý rõ các biến thể của mô hình miền |
| Rủi ro thiết kế thường gặp | Khó kiểm soát mọi kiểu con do bên ngoài bổ sung | Khó tùy biến bằng inheritance | Có thể hạn chế khả năng mở rộng API nếu danh sách `permits` quá chặt |
| Trạng thái trên Java 17 | Cơ chế có từ trước | Cơ chế có từ trước | Tính năng ngôn ngữ ổn định từ Java 17 |

Bảng so sánh khả năng kế thừa nói trên vẫn chịu các quy tắc nền tảng của Java: khả năng truy cập của lớp, constructor, package, module và các ràng buộc ngôn ngữ khác. “Mở” **không** có nghĩa mọi mã ở mọi nơi đều có thể kế thừa bất kỳ lớp nào.

## 3. Phân cấp mở: ưu tiên khả năng mở rộng

### 3.1. Khai báo đơn giản

```java
interface PaymentMethod {
    String code();
}

class CardPayment implements PaymentMethod {
    @Override
    public String code() {
        return "CARD";
    }
}

class BankTransfer implements PaymentMethod {
    @Override
    public String code() {
        return "BANK_TRANSFER";
    }
}
```

Ở đây, `PaymentMethod` là interface thông thường. Sau này có thể bổ sung một kiểu triển khai khác:

```java
class WalletPayment implements PaymentMethod {
    @Override
    public String code() {
        return "WALLET";
    }
}
```

Không cần sửa `PaymentMethod` để đưa thêm một lớp triển khai hợp lệ vào hệ thống. Một thư viện tích hợp hoặc một module plugin có thể dùng cơ chế này nếu interface được công khai đúng cách.

Lớp thông thường cũng có thể mở rộng:

```java
class Notification {
    public String message() {
        return "Thông báo chung";
    }
}

class EmailNotification extends Notification {
    @Override
    public String message() {
        return "Thông báo qua email";
    }
}
```

Trong ví dụ trên, `Notification` không có `final` hoặc `sealed`, nên có thể được kế thừa khi các điều kiện thông thường được đáp ứng.

### 3.2. Khi nào nên giữ phân cấp mở?

Phân cấp mở phù hợp khi **khả năng có thêm kiểu con là yêu cầu thiết kế có chủ ý**:

- API thư viện cần để ứng dụng khác tự cung cấp kiểu triển khai.
- Cơ chế plugin, driver, adapter hoặc chiến lược xử lý do người dùng mở rộng.
- Abstraction được thiết kế như một extension point ổn định và có tài liệu rõ ràng.

Ví dụ, hệ thống thanh toán hỗ trợ nhà cung cấp bên ngoài có thể cho phép các đối tác triển khai `PaymentMethod` tùy nhu cầu. Việc một kiểu không bị `sealed` không bảo đảm extension point tốt: nếu hợp đồng API mơ hồ, quá nhiều phương thức bắt buộc, hoặc class có logic phụ thuộc chi tiết nội bộ, kiểu con vẫn dễ làm sai các giả định.

### 3.3. Giới hạn của phân cấp mở

Giả sử có đoạn xử lý:

```java
static String describe(PaymentMethod method) {
    if (method instanceof CardPayment) {
        return "Thanh toán thẻ";
    }
    if (method instanceof BankTransfer) {
        return "Chuyển khoản";
    }
    return "Phương thức khác";
}
```

`PaymentMethod` có thể có `WalletPayment` hoặc những lớp chưa được định nghĩa khi viết hàm. Nếu nhóm phát triển **giả định chỉ có hai loại**, giả định đó không được hệ thống kiểu bảo vệ.

Khi công khai một lớp có thể kế thừa, cần xác định phương thức nào có thể override, invariant nào phải được duy trì và cách nâng cấp API sao cho không phá vỡ các lớp con của bên thứ ba. Nếu không thực sự cần cho phép kế thừa, việc để lớp mở một cách vô thức có thể gây phức tạp.

## 4. `final`: đóng khả năng kế thừa của một lớp

### 4.1. Cách khai báo

```java
final class ReceiptNumber {
    private final String value;

    ReceiptNumber(String value) {
        this.value = java.util.Objects.requireNonNull(value);
    }

    String value() {
        return value;
    }
}
```

Lớp `ReceiptNumber` không thể được mở rộng bằng `extends`:

```java
// KHÔNG HỢP LỆ: không thể kế thừa lớp final.
class SpecialReceiptNumber extends ReceiptNumber {
    SpecialReceiptNumber() {
        super("SP-001");
    }
}
```

Trình biên dịch Java từ chối lớp con này vì `ReceiptNumber` được đánh dấu `final`. Đây là quyết định trên **cấu trúc kiểu**, không phải cơ chế quản lý quyền truy cập của người dùng.

### 4.2. `final` bảo vệ điều gì?

Một lớp `final` thường được chọn khi:

- Kiểu có ý nghĩa độc lập và không có nhu cầu thiết kế lớp con.
- Tác giả muốn tránh lớp con thay đổi hành vi hoặc phá vỡ các bất biến mà lớp cần duy trì.
- Đối tượng được thiết kế như một value object, dùng composition thay vì inheritance.
- API công khai không muốn cam kết hỗ trợ hành vi override trong các bản cập nhật.

Ví dụ, nhiều lớp biểu diễn giá trị như `String` và `Integer` là `final`. Một `record` cũng ngầm định là `final`, vì vậy không được kế thừa lớp record.

Cần phân biệt ba cách dùng từ khóa `final`:

| Khai báo | Điều bị giới hạn |
|---|---|
| `final class X` | Không lớp nào được `extends X` |
| `final void process()` | Lớp con không được override phương thức `process` |
| `final int n = 10` | Biến chỉ được gán một lần theo quy tắc của Java |

**`final class` không tự động bảo đảm object bất biến.** Một lớp `final` vẫn có thể chứa field thay đổi, setter hoặc tham chiếu đến collection có thể chỉnh sửa:

```java
final class Counter {
    private int count;

    void increment() {
        count++;
    }

    int getCount() {
        return count;
    }
}
```

`Counter` là `final` nhưng vẫn có trạng thái thay đổi. Nếu cần bất biến, phải thiết kế thêm về field, object được tham chiếu, constructor và phương thức.

### 4.3. Những điều `final` không cấm

`final` **không** có nghĩa lớp không được thực thi interface:

```java
interface Exporter {
    void exportData();
}

final class CsvExporter implements Exporter {
    @Override
    public void exportData() {
        System.out.println("Xuất CSV");
    }
}
```

`CsvExporter` vẫn triển khai `Exporter` hợp lệ; chỉ có lớp khác là không được `extends CsvExporter`.

Java không hỗ trợ `final interface` vì interface vốn biểu diễn hợp đồng cho các kiểu triển khai. Nếu muốn **giới hạn những kiểu được triển khai**, hãy xem xét `sealed interface`.

Không thể khai báo một lớp đồng thời là `final` và `abstract`: `abstract` cần được kế thừa để hoàn thiện hành vi, còn `final` cấm kế thừa lớp đó.

## 5. `sealed`: đóng danh sách kiểu con trực tiếp

### 5.1. Ví dụ với `sealed interface`

```java
sealed interface PaymentResult permits Paid, Rejected, Pending {}

record Paid(String transactionId) implements PaymentResult {}

record Rejected(String reason) implements PaymentResult {}

final class Pending implements PaymentResult {}
```

Có ba kiểu triển khai **trực tiếp** của `PaymentResult` được cho phép:

- `Paid` là record, ngầm định `final`.
- `Rejected` là record, ngầm định `final`.
- `Pending` được khai báo `final` một cách tường minh.

Một kiểu thứ tư không có trong `permits` sẽ bị từ chối khi biên dịch:

```java
// KHÔNG HỢP LỆ: OutsideResult không được PaymentResult cho phép.
class OutsideResult implements PaymentResult {}
```

Với một `sealed interface`, từ khóa `implements` trong các lớp triển khai chính là cách tạo kiểu con trực tiếp. Với `sealed class`, kiểu con trực tiếp dùng `extends`.

### 5.2. Ví dụ với `sealed class`

```java
abstract sealed class Document permits PdfDocument, TextDocument {
    abstract String format();
}

final class PdfDocument extends Document {
    @Override
    String format() {
        return "PDF";
    }
}

final class TextDocument extends Document {
    @Override
    String format() {
        return "TEXT";
    }
}
```

Trong ví dụ, `Document` vừa `abstract` vừa `sealed`. Điều này hợp lệ: `abstract` ngăn tạo trực tiếp một instance của `Document`, trong khi `sealed` hạn chế **lớp nào được extends Document**.

`sealed` **không tự động làm kiểu trở thành `abstract`**. Một lớp `sealed` không `abstract` vẫn có thể khởi tạo trực tiếp nếu constructor truy cập được và các quy tắc Java khác cho phép.

### 5.3. Quy tắc của `permits`

Trong Java 17, những điểm cần nắm là:

1. Danh sách `permits` nói về **kiểu con trực tiếp**, không liệt kê tất cả hậu duệ ở mọi cấp.
2. Mỗi kiểu được nêu phải thực sự `extends` hoặc `implements` trực tiếp kiểu `sealed` tương ứng.
3. Trong một **named module**, kiểu `sealed` và các kiểu con trực tiếp được phép phải cùng module; chúng có thể ở các package khác nhau trong module đó.
4. Trong **unnamed module** (ví dụ các file Java thông thường chưa khai báo module), các kiểu con trực tiếp được phép phải ở cùng package với kiểu `sealed`.
5. Mỗi kiểu con trực tiếp phải lựa chọn cách tiếp tục phân cấp bằng `final`, `sealed` hoặc `non-sealed`. Record được phép làm kiểu con trực tiếp và đã ngầm định `final`.
6. Có thể bỏ mệnh đề `permits` khi các kiểu con trực tiếp hợp lệ được khai báo trong cùng đơn vị biên dịch với kiểu `sealed`; trình biên dịch sẽ suy ra danh sách. Viết `permits` tường minh vẫn giúp người đọc thấy ranh giới mô hình ngay tại khai báo.

Ví dụ cấu trúc hợp lệ trong unnamed module:

```text
src/com/example/payments/
├── PaymentResult.java       (sealed interface PaymentResult)
├── Paid.java                (record Paid implements PaymentResult)
└── Rejected.java            (record Rejected implements PaymentResult)
```

Nếu chuyển `Rejected` sang một package khác, chỉ giữ ba file trong cùng source folder là chưa đủ. Phải xét quy tắc module/package tương ứng.

## 6. Ba lựa chọn cho từng kiểu con của `sealed`

Java 17 yêu cầu nhánh con trực tiếp quyết định rõ khả năng mở rộng tiếp theo.

### 6.1. `final`: kết thúc nhánh

```java
sealed interface TaskState permits Completed, Running {}

final class Completed implements TaskState {}

final class Running implements TaskState {}
```

`Completed` và `Running` đều là các nhánh cuối, không có lớp con phía dưới.

### 6.2. `sealed`: tiếp tục giới hạn ở tầng kế tiếp

```java
sealed interface Message permits UserMessage, SystemMessage {}

sealed interface UserMessage extends Message
        permits TextMessage, ImageMessage {}

final class TextMessage implements UserMessage {}

final class ImageMessage implements UserMessage {}

final class SystemMessage implements Message {}
```

Cây phân cấp có hai tầng giới hạn:

```text
Message (sealed)
├── UserMessage (sealed)
│   ├── TextMessage (final)
│   └── ImageMessage (final)
└── SystemMessage (final)
```

Mỗi kiểu `sealed` quản lý **chính danh sách con trực tiếp của mình**. Nhờ vậy, phân cấp có thể phát triển theo cấu trúc rõ ràng mà không cần đặt toàn bộ biến thể trong một danh sách duy nhất ở gốc.

### 6.3. `non-sealed`: mở lại một nhánh

```java
sealed interface Delivery permits InHouseDelivery, PartnerDelivery {}

final class InHouseDelivery implements Delivery {}

non-sealed class PartnerDelivery implements Delivery {}

class ExpressPartnerDelivery extends PartnerDelivery {}

class EconomyPartnerDelivery extends PartnerDelivery {}
```

Mặc dù `Delivery` chỉ cho phép hai kiểu con trực tiếp, `PartnerDelivery` lại cho phép các lớp khác tiếp tục kế thừa. Như vậy, tập **mọi đối tượng có kiểu `Delivery`** không chỉ gồm hai lớp cụ thể.

`non-sealed` có ý nghĩa khi muốn **gốc mô hình được kiểm soát** nhưng vẫn dành một nhánh cho extension point. Trong hệ thống tích hợp đối tác, đây có thể là lựa chọn cân bằng giữa quản lý domain và cho phép plugin mở rộng.

Không nên dùng `non-sealed` như một từ khóa trang trí cho lớp bất kỳ. Nó chỉ phù hợp với kiểu con trực tiếp của một kiểu `sealed` (theo quan hệ `extends` hoặc `implements` trực tiếp) để tháo giới hạn kế thừa trên nhánh đó.

### 6.4. So sánh hai mô hình sealed

**Đóng toàn bộ cây:**

```text
Result (sealed)
├── Success (final)
├── Failure (final)
└── Timeout (final)
```

Khi mọi nhánh đều kết thúc ở `final`, ứng dụng có thể xem tập kiểu cụ thể là một danh sách hữu hạn được kiểm soát.

**Đóng gốc, mở một nhánh:**

```text
Result (sealed)
├── Success (final)
├── Failure (final)
└── ExtensionResult (non-sealed)
    ├── PluginResultA
    └── PluginResultB
```

Trong cách thứ hai, người dùng API vẫn có thể tạo thêm loại kết quả qua `ExtensionResult`. Vì vậy, câu nói “`sealed` luôn đóng toàn bộ cây phân cấp” là **không chính xác**.

## 7. Ví dụ hoàn chỉnh chạy bằng Java 17

Ví dụ sau đặt cả ba lựa chọn vào cùng một chương trình. Tạo file **`HierarchyComparisonDemo.java`**:

```java
public class HierarchyComparisonDemo {

    // 1. PHÂN CẤP MỞ: class thông thường cho phép extends.
    static class OpenNotification {
        String text() {
            return "Thông báo chung";
        }
    }

    static class EmailNotification extends OpenNotification {
        @Override
        String text() {
            return "Thông báo email";
        }
    }

    // 2. FINAL: không thể extends lớp này.
    static final class NotificationId {
        private final String value;

        NotificationId(String value) {
            this.value = value;
        }

        String value() {
            return value;
        }
    }

    // 3. SEALED: chỉ ba kiểu con trực tiếp được phép.
    sealed interface ProcessResult
            permits Success, Failure, Pending {}

    // Record ngầm định final (tính năng ổn định từ Java 16).
    record Success(String receipt) implements ProcessResult {}
    record Failure(String reason) implements ProcessResult {}

    // Mở nhánh Pending cho các loại pending cụ thể.
    static non-sealed class Pending implements ProcessResult {
        String description() {
            return "Đang xử lý";
        }
    }

    static final class PendingAtBank extends Pending {
        @Override
        String description() {
            return "Đang chờ ngân hàng";
        }
    }

    static String describe(ProcessResult result) {
        // Pattern matching cho instanceof ổn định từ Java 16.
        if (result instanceof Success success) {
            return "Thành công: " + success.receipt();
        }
        if (result instanceof Failure failure) {
            return "Thất bại: " + failure.reason();
        }
        if (result instanceof Pending pending) {
            return pending.description();
        }
        throw new IllegalStateException("Kiểu kết quả không hỗ trợ");
    }

    public static void main(String[] args) {
        OpenNotification notification = new EmailNotification();
        NotificationId id = new NotificationId("NTF-17");

        System.out.println(id.value() + ": " + notification.text());
        System.out.println(describe(new Success("PAY-001")));
        System.out.println(describe(new Failure("Sai dữ liệu")));
        System.out.println(describe(new PendingAtBank()));
    }
}
```

Biên dịch và chạy với JDK 17:

```bash
javac --release 17 HierarchyComparisonDemo.java
java HierarchyComparisonDemo
```

Kết quả:

```text
NTF-17: Thông báo email
Thành công: PAY-001
Thất bại: Sai dữ liệu
Đang chờ ngân hàng
```

Ví dụ dùng `sealed` ổn định trên Java 17, `record` và pattern matching cho `instanceof` đã ổn định từ Java 16. **Không cần bật preview**.

**Lưu ý về `switch`:** Java 17 đã có `switch` expression ổn định (từ Java 14), nhưng **pattern matching for `switch`** trong Java 17 vẫn là *preview* (JEP 406). Vì vậy, ví dụ sử dụng `instanceof` để phân biệt biến thể thay vì viết `switch (result) { case Success s -> ... }` như cú pháp Java 17 mặc định.

## 8. Khi nào chọn cách nào?

Bài toán thiết kế quyết định hướng chọn, thay vì mặc định mọi class đều phải là `sealed` hoặc `final`.

| Tình huống thực tế | Lựa chọn nên cân nhắc | Lý do |
|---|---|---|
| Thư viện công khai cho lập trình viên bên ngoài tự viết adapter | Interface thông thường | Cho phép thêm triển khai mà không phải sửa thư viện |
| Lớp biểu diễn mã định danh, cần ngăn tạo lớp con với ý nghĩa khác | `final class` hoặc `record` nếu phù hợp | Không cho kế thừa lớp biểu diễn giá trị |
| Kết quả xử lý chỉ có vài nhóm nghiệp vụ do module chủ quản định nghĩa | `sealed interface` với các nhánh `final` | Biến tập kiểu con trực tiếp thành hợp đồng rõ ràng |
| Mô hình sự kiện có nhóm hệ thống kiểm soát và nhóm dành cho plugin | `sealed` ở gốc, một nhánh `non-sealed` | Giới hạn nhóm cấp cao nhưng vẫn hỗ trợ extension |
| Cây biểu thức có nhiều tầng, mỗi tầng chỉ nhận biến thể xác định | `sealed` lồng nhiều cấp | Quản lý ranh giới mở rộng ở từng tầng |
| Tập lựa chọn đơn giản, cố định, mỗi lựa chọn không cần kiểu dữ liệu riêng | `enum` | Dễ biểu diễn tập hằng và xử lý theo giá trị |
| Muốn thay đổi hành vi mà không muốn ràng buộc vào cây kế thừa | Composition qua field/interface | Tái sử dụng hành vi không cần mở rộng class |

### 8.1. Đặt `sealed` cạnh `enum`

Một `enum` phù hợp cho tập lựa chọn hữu hạn mà mỗi trường hợp có cùng kiểu dữ liệu:

```java
enum RequestStatus {
    NEW, PROCESSING, DONE, FAILED
}
```

`sealed` phù hợp khi các biến thể **mang dữ liệu hoặc hành vi khác nhau**:

```java
sealed interface ApiResponse permits OkResponse, ErrorResponse {}

record OkResponse(String data) implements ApiResponse {}

record ErrorResponse(int statusCode, String detail)
        implements ApiResponse {}
```

Thay vì tạo một enum chứa nhiều field có thể rỗng tùy trường hợp, các record khác nhau giúp mô tả dữ liệu bắt buộc ở từng biến thể. Tuy nhiên, `sealed` không luôn tốt hơn `enum`; hãy chọn cấu trúc đơn giản nhất phản ánh đúng miền nghiệp vụ.

### 8.2. Đặt `final` cạnh composition

Muốn mở rộng hành vi không nhất thiết phải dùng `extends`. Ví dụ:

```java
interface PricingRule {
    long calculate(long basePrice);
}

final class OrderPricing {
    private final PricingRule rule;

    OrderPricing(PricingRule rule) {
        this.rule = rule;
    }

    long total(long basePrice) {
        return rule.calculate(basePrice);
    }
}
```

`OrderPricing` là `final`, nhưng hành vi có thể tùy biến qua `PricingRule`. Như vậy, **đóng kế thừa của một class không đồng nghĩa đóng khả năng cấu hình hoặc thay thế hành vi**.

## 9. Tác động lên API và bảo trì mã nguồn

### 9.1. Phân cấp mở là một cam kết mở rộng

Nếu phát hành `public class BaseService` mà cho phép kế thừa, mã bên ngoài có thể đã tạo lớp con và override phương thức. Đổi lớp này thành `final` hoặc `sealed` trong phiên bản thư viện sau có thể khiến mã người dùng **không biên dịch** hoặc không còn tương thích khi liên kết/chạy.

Trước khi siết phân cấp, cần biết có những lớp con hợp lệ nào đang phụ thuộc API, chúng thuộc module/package nào và có đường di chuyển nào. Đây là thay đổi hợp đồng kế thừa, không chỉ là sửa từ khóa.

### 9.2. `sealed` giúp rõ mô hình nhưng không tự động xử lý mọi trường hợp

Một phân cấp `sealed` có thể giúp kiểm soát dạng dữ liệu và rà soát nơi xử lý các nhánh. Tuy nhiên:

- Tính đúng đắn của nghiệp vụ vẫn phụ thuộc vào validation và logic của từng lớp.
- Nếu có nhánh `non-sealed`, tập lớp con sâu hơn vẫn có thể được mở rộng.
- Java 17 **chưa có pattern matching for switch ổn định** để viết đầy đủ kiểu `switch` theo mẫu với mọi biến thể. Đừng lấy khả năng exhaustiveness của cú pháp Java mới hơn làm mặc định cho Java 17.
- `sealed` không thay thế cơ chế xác thực, phân quyền, kiểm soát input hoặc bảo mật khi giải tuần tự hóa.

### 9.3. Giới hạn module/package ảnh hưởng cách đóng gói thư viện

Một API `sealed` có thể dùng trong nhiều dự án, nhưng **các kiểu con trực tiếp được liệt kê không được tùy ý nằm ở module khác**. Nếu muốn plugin ở module bên ngoài có thể tạo loại mới, cần thiết kế một nhánh `non-sealed` công khai phù hợp hoặc lựa chọn interface mở ở extension point.

### 9.4. Thêm hoặc bớt kiểu được phép là thay đổi thiết kế

Mỗi lần thay đổi danh sách `permits`, cần đánh giá mã phụ thuộc, hệ thống serialization, logic xử lý các biến thể và khả năng tương thích. Việc thêm kiểu con trực tiếp có thể khiến những đoạn xử lý vốn dựa vào tập biến thể cũ cần được cập nhật, ngay cả khi mã nguồn Java 17 chưa dùng `switch` theo mẫu.

## 10. Lỗi thường gặp khi học `sealed`

### Lỗi 1: Cho rằng `sealed` giống `final`

`final` cấm kế thừa lớp. `sealed` cho phép **những kiểu con trực tiếp được chỉ định**. Một `sealed class` vẫn có thể có nhiều kiểu con và nhánh `non-sealed` có thể được mở rộng thêm.

### Lỗi 2: Quên chỉ định trạng thái tiếp tục của lớp con

```java
sealed class Vehicle permits Car {}

// KHÔNG HỢP LỆ: Car phải quyết định final, sealed hoặc non-sealed.
class Car extends Vehicle {}
```

Sửa, ví dụ:

```java
sealed class Vehicle permits Car {}

final class Car extends Vehicle {}
```

Nếu `Car` còn cần tạo lớp con với danh sách giới hạn, dùng `sealed class Car ...`; nếu cần mở tự do, cân nhắc `non-sealed class Car`.

### Lỗi 3: Đặt tên trong `permits` nhưng không có quan hệ kế thừa trực tiếp

```java
// KHÔNG HỢP LỆ: Sedan không trực tiếp extends Vehicle.
sealed class Vehicle permits Car, Sedan {}

non-sealed class Car extends Vehicle {}

class Sedan extends Car {}
```

Trong mô hình này, `Sedan` là lớp con **gián tiếp** của `Vehicle`. Mệnh đề `permits` của `Vehicle` chỉ cần liệt kê `Car`; `Sedan` được phép tồn tại nhờ `Car` là `non-sealed`.

### Lỗi 4: Dùng `non-sealed` ở nơi không có cha trực tiếp là `sealed`

```java
class Base {}

// KHÔNG HỢP LỆ: Base không phải kiểu sealed.
non-sealed class Child extends Base {}
```

`non-sealed` chỉ có ý nghĩa khi tháo giới hạn kế thừa được đặt ở kiểu cha trực tiếp là `sealed`.

### Lỗi 5: Dùng `final interface`

Java không có cú pháp `final interface`. Nếu muốn giới hạn các kiểu triển khai hợp lệ, dùng `sealed interface`; nếu muốn cho phép mở rộng, dùng interface thông thường.

### Lỗi 6: Dùng `sealed` ở Java 17 nhưng dự án biên dịch cho Java 11

Dù máy có JDK 17, build cấu hình `--release 11` không cho phép dùng cú pháp `sealed`. Cần bảo đảm release target tương ứng với ngôn ngữ/API mong muốn và runtime triển khai có thể chạy class file Java 17.

## 11. Tự luyện chọn thiết kế

**Bài 1.** Một thư viện logger cần để ứng dụng tự viết `FileAppender`, `DatabaseAppender` hoặc `CloudAppender` trong những module độc lập. Nên sử dụng phân cấp nào cho interface extension point?

**Gợi ý:** Một interface thông thường sẽ phù hợp nếu việc thêm triển khai từ bên ngoài là yêu cầu chính. `sealed` ở gốc có thể cản trở các triển khai ngoài module.

**Bài 2.** Hệ thống trả về `Approved`, `Rejected` hoặc `Pending`. Mỗi biến thể có các trường dữ liệu riêng, không chấp nhận biến thể thứ tư. Nên dùng gì?

**Gợi ý:** Dùng `sealed interface Decision permits Approved, Rejected, Pending` và các lớp `record` tương ứng. Các record đều ngầm định `final`.

**Bài 3.** Bạn cần khóa một lớp thực thi thuật toán vì không muốn bên ngoài override các bất biến quan trọng, nhưng vẫn cho phép truyền chiến lược xử lý khác nhau.

**Gợi ý:** Dùng `final class`, kết hợp một interface chiến lược và composition. Khóa lớp không cản trở việc sử dụng các đối tượng phụ thuộc khác nhau.

**Bài 4.** Một `sealed interface Notification` chỉ cho phép `InternalNotification` và `ThirdPartyNotification`. Hệ thống muốn tự quản lý toàn bộ internal notifications, đồng thời cho plugin tự tạo notification trong nhánh đối tác.

**Gợi ý:** Đặt `InternalNotification` là `final` hoặc tiếp tục `sealed` tùy số biến thể nội bộ; đặt `ThirdPartyNotification` là `non-sealed`, với kiểu/constructor có khả năng truy cập phù hợp để plugin mở rộng.

**Bài 5.** Có thể nói rằng `sealed interface Event permits A, B` bảo đảm trong toàn bộ chương trình chỉ có hai lớp cụ thể triển khai `Event` không?

**Đáp án:** Chưa chắc. Nó chỉ nêu hai **kiểu con trực tiếp**. Nếu `A` hoặc `B` là `non-sealed`, các lớp khác có thể mở rộng qua nhánh tương ứng. Nếu cần toàn bộ cây hữu hạn, phải kiểm soát các tầng tiếp theo.

## 12. Ghi nhớ để áp dụng

- **Phân cấp mở:** Dành cho các kiểu được thiết kế để người khác mở rộng; Java không cần khai báo từ khóa `open`.
- **`final class`:** Khóa kế thừa của đúng lớp đó. Lớp vẫn có thể triển khai interface và có trạng thái thay đổi.
- **`sealed class/interface`:** Kiểm soát danh sách **kiểu con trực tiếp**. Đây là tính năng ngôn ngữ được chuẩn hóa ở Java 17.
- **`final` / `sealed` / `non-sealed` trên kiểu con:** Lần lượt đóng nhánh, giới hạn thêm tầng kế tiếp, hoặc mở nhánh lại.
- **Quy tắc module/package:** Kiểu con trực tiếp được cho phép phải cùng named module; nếu dùng unnamed module, phải cùng package.
- **Java 17:** Có thể dùng `sealed` ổn định mà không bật preview. Pattern matching for `switch` vẫn là preview trong Java 17.

### Tài liệu tham khảo chính thức

- [OpenJDK JEP 409 — Sealed Classes](https://openjdk.org/jeps/409) — đề xuất đã được chuẩn hóa ở Java 17, động cơ thiết kế và ngữ nghĩa `permits`.
- [Oracle Java 17 — Sealed Classes and Interfaces](https://docs.oracle.com/en/java/javase/17/language/sealed-classes-and-interfaces.html) — cú pháp và ví dụ `sealed`, `final`, `non-sealed`.
- [Java Language Specification, Java SE 17 — Class Modifiers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.1) — quy tắc ngôn ngữ cho lớp, `final` và `sealed`.
- [Java Language Specification, Java SE 17 — Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html) — các ràng buộc tương ứng đối với interface.

**Nguyên tắc lựa chọn:** Bắt đầu từ hợp đồng mở rộng mà hệ thống thật sự cần. **Cho mở** khi hệ thống phải chấp nhận kiểu triển khai mới; **dùng `final`** khi lớp không cần lớp con; **dùng `sealed`** khi cần mô hình hóa một tập nhóm kiểu con được kiểm soát nhưng vẫn muốn giữ khả năng thiết kế nhiều nhánh kế thừa.
