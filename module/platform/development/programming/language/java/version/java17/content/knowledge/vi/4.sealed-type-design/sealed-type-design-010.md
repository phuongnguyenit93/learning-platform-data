# Khi nên dùng enum, sealed hoặc thành phần kết hợp trong Java 17

Trong thiết kế Java 17, `enum` và `sealed` đều giúp mô hình hóa **một tập khả năng có giới hạn**, nhưng hai công cụ giới hạn **hai thứ khác nhau**:

- **`enum`** mô tả một tập **giá trị hằng được đặt tên**, mỗi hằng là một thể hiện đã được khai báo sẵn.
- **`sealed class` / `sealed interface`** giới hạn **những kiểu con trực tiếp** có thể kế thừa hoặc triển khai kiểu cha. Mỗi kiểu con có thể có dữ liệu và cách hoạt động riêng; chương trình có thể tạo nhiều đối tượng thuộc cùng một kiểu con.
- **Kết hợp bằng composition** nghĩa là đặt enum, sealed type, record và đối tượng thông thường vào các vai trò khác nhau, thay vì ép toàn bộ thông tin của một miền nghiệp vụ thành một hệ phân cấp.

Không có công cụ nào luôn tốt hơn công cụ còn lại. Câu hỏi thiết kế quan trọng là: **“Đây là những giá trị cố định, những hình dạng dữ liệu khác nhau, hay nhiều chiều thông tin độc lập?”**

Bài học này dùng cú pháp có sẵn và ổn định ở **Java 17**. `sealed` được chuẩn hóa trong Java 17; `record`, `switch expression` và pattern matching cho `instanceof` cũng đã chính thức ở Java 17. **Pattern matching trong `switch` còn là preview ở Java 17**, vì vậy các ví dụ sử dụng `switch` với enum hoặc `instanceof` mà không cần `--enable-preview`.

## 1. Bảng so sánh để chọn hướng thiết kế

| Tiêu chí | `enum` | `sealed interface/class` | Kết hợp bằng composition |
| --- | --- | --- | --- |
| Đại diện cho | Một tập **giá trị hằng** như `NEW`, `PAID`, `CANCELLED`. | Một tập **nhóm kiểu** như `Success`, `Failure` có cấu trúc khác nhau. | Nhiều chiều dữ liệu hoặc nhiều trách nhiệm trong cùng mô hình. |
| Số đối tượng | Mỗi enum constant là một đối tượng được định nghĩa sẵn; không tạo hằng mới khi chạy. | Có thể tạo bao nhiêu instance tùy ý của các lớp con được phép. | Tùy thành phần: enum hữu hạn, bản ghi/đối tượng có thể có nhiều instance. |
| Dữ liệu riêng từng trường hợp | Có thể lưu trường và phương thức cho mỗi constant, nhưng constant mang giá trị cố định, không nhận dữ liệu mới cho từng sự kiện. | Mỗi kiểu con có trường, hàm tạo, bất biến và hành vi riêng; record thường phù hợp cho dữ liệu. | Đặt các thuộc tính độc lập vào các field; dùng sealed chỉ ở nơi thực sự có biến thể cấu trúc. |
| Chính sách mở rộng | Không thể thêm enum constant từ bên ngoài định nghĩa enum. | Chỉ các direct subclasses được phép; nhánh `non-sealed` có thể mở rộng tiếp. | Có thể chọn giới hạn hoặc mở rộng độc lập cho từng thành phần. |
| Xử lý nhánh trong Java 17 | `switch` trên enum hoạt động ổn định, bao gồm `switch expression`. | `instanceof` kết hợp pattern variable, method đa hình hoặc visitor; type-pattern `switch` vẫn preview ở Java 17. | Thường dùng `switch` cho enum và đa hình/`instanceof` cho biến thể sealed. |
| Trường hợp điển hình | Quyền truy cập, trạng thái, mức độ ưu tiên, loại thông báo cố định. | Kết quả thành công/thất bại, lệnh có payload khác nhau, nút cây cú pháp, biến thể của thông điệp. | Phương thức thanh toán + trạng thái đơn hàng; nhóm kết quả sealed + mã lỗi enum; event có kiểu và metadata. |

Hãy ưu tiên mô hình **ít loại và ít ràng buộc nhất nhưng diễn đạt đúng nghiệp vụ**. Không nhất thiết dùng sealed chỉ vì dự án đã ở Java 17.

## 2. Khi `enum` là lựa chọn phù hợp

Chọn `enum` khi bạn có **một nhóm giá trị hữu hạn, tên rõ ràng**, không cần tạo thêm từng giá trị khi chạy:

- Trạng thái quy trình: `CREATED`, `PROCESSING`, `DONE`, `FAILED`.
- Mức độ ưu tiên: `LOW`, `NORMAL`, `HIGH`.
- Loại kênh: `EMAIL`, `SMS`, `PUSH`.
- Một bộ phân loại hoặc mã lý do đã được quy định trong hệ thống.

### 2.1. Ví dụ: enum có thuộc tính và `switch expression`

Tạo file **`PriorityDemo.java`**:

```java
enum Priority {
    LOW(1),
    NORMAL(5),
    URGENT(10);

    private final int weight;

    Priority(int weight) {
        this.weight = weight;
    }

    public int weight() {
        return weight;
    }
}

public class PriorityDemo {
    static String label(Priority priority) {
        return switch (priority) {
            case LOW -> "Thấp";
            case NORMAL -> "Bình thường";
            case URGENT -> "Khẩn cấp";
        };
    }

    public static void main(String[] args) {
        for (Priority priority : Priority.values()) {
            System.out.println(
                    label(priority) + " (weight=" + priority.weight() + ")"
            );
        }
    }
}
```

```bash
javac --release 17 PriorityDemo.java
java PriorityDemo
```

Ví dụ minh họa rằng một enum có thể chứa **trường, constructor và phương thức**, chứ không chỉ là tên hằng. Tuy nhiên, chỉ có ba giá trị `Priority.LOW`, `Priority.NORMAL`, `Priority.URGENT`: chương trình không thể tạo `new Priority(...)`.

`switch expression` ở Java 17 phải bao quát các trường hợp phù hợp. Với enum, liệt kê đủ constant giúp compiler hỗ trợ phát hiện sự thay đổi tập giá trị khi biên dịch lại mã nguồn. Một `default` viết sẵn có thể che mất cảnh báo thiết kế quan trọng khi enum được mở rộng; chỉ dùng `default` khi thực sự có chủ đích xử lý chung.

### 2.2. Enum có hành vi riêng cho từng giá trị

Nếu mỗi giá trị có một quy tắc hành vi nhỏ, ổn định, có thể để hành vi ngay trong enum:

```java
enum PricePolicy {
    STANDARD {
        @Override
        int apply(int basePrice) {
            return basePrice;
        }
    },
    PROMOTION {
        @Override
        int apply(int basePrice) {
            return basePrice * 90 / 100;
        }
    };

    abstract int apply(int basePrice);
}
```

Đây là **constant-specific class body**, một khả năng có từ lâu và vẫn dùng được trong Java 17. Không cần tạo hệ sealed chỉ để mô tả hai chiến lược hằng đơn giản. Nếu quy tắc trở nên dài, phụ thuộc database hoặc cấu hình động, nên tách phần xử lý sang service/strategy thay vì đẩy quá nhiều logic vào enum.

### 2.3. Khi không nên ép dữ liệu vào enum

Giả sử mỗi yêu cầu hỗ trợ có `id`, người tạo, thời điểm mở, lời nhắn và mức ưu tiên. Enum `Priority` chỉ diễn đạt **loại ưu tiên**; nó không thể giữ an toàn dữ liệu riêng của từng yêu cầu bằng cách thay đổi field của `URGENT`, vì đó là **một đối tượng dùng chung**.

Mô hình phù hợp là:

```java
import java.time.Instant;

record SupportTicket(
        long id,
        String requester,
        Priority priority,
        Instant createdAt
) {}
```

`Priority` ở đây là **một thuộc tính của `SupportTicket`**, không phải bản thân ticket. Tránh dùng field mutable của enum để cất trạng thái riêng của người dùng, request hoặc transaction; thay đổi đó sẽ ảnh hưởng tới mọi nơi đang dùng cùng enum constant.

## 3. Khi `sealed` phù hợp hơn enum

Chọn `sealed interface` hoặc `sealed class` khi tập biến thể được quản lý có **cấu trúc dữ liệu khác nhau**, mỗi biến thể có thể có **nhiều instance**, hoặc cần hành vi và bất biến riêng.

Ví dụ:

- `Success<T>` giữ một giá trị `T`; `Failure<T>` giữ mã và thông điệp lỗi.
- `EmailNotification` giữ địa chỉ nhận và chủ đề; `SmsNotification` giữ số điện thoại và nội dung.
- `TransferCommand` giữ tài khoản nguồn/đích; `RefundCommand` giữ mã giao dịch cần hoàn tiền.

### 3.1. Ví dụ: `sealed` + `record` cho các biến thể có payload khác nhau

Tạo file **`LookupDemo.java`**:

```java
import java.util.Objects;

sealed interface LookupResult
        permits Found, NotFound, LookupFailed {}

record Found(String value) implements LookupResult {
    Found {
        Objects.requireNonNull(value, "value");
    }
}

record NotFound(long requestedId) implements LookupResult {}

record LookupFailed(String reason) implements LookupResult {
    LookupFailed {
        Objects.requireNonNull(reason, "reason");
    }
}

public class LookupDemo {
    static String describe(LookupResult result) {
        if (result instanceof Found found) {
            return "Tìm thấy: " + found.value();
        }
        if (result instanceof NotFound notFound) {
            return "Không có id=" + notFound.requestedId();
        }
        if (result instanceof LookupFailed failed) {
            return "Lỗi tra cứu: " + failed.reason();
        }
        throw new IllegalStateException("Unhandled result: " + result);
    }

    public static void main(String[] args) {
        LookupResult a = new Found("Alice");
        LookupResult b = new NotFound(404);
        LookupResult c = new LookupFailed("Service unavailable");

        System.out.println(describe(a));
        System.out.println(describe(b));
        System.out.println(describe(c));
    }
}
```

```bash
javac --release 17 LookupDemo.java
java LookupDemo
```

Điểm thiết kế quan trọng:

1. `LookupResult` chỉ cho phép ba **kiểu con trực tiếp**. Không thể tự ý tạo `class UnexpectedResult implements LookupResult` ở một nơi khác nếu không thuộc tập kiểu được phép.
2. `Found`, `NotFound` và `LookupFailed` là các `record`; record ngầm định `final` nên có thể trực tiếp triển khai sealed interface. Mỗi record giữ **dữ liệu riêng của từng instance**, khác với enum singleton.
3. Biến `LookupResult` có thể trỏ tới bất kỳ instance nào thuộc ba biến thể. Không có giới hạn chỉ một đối tượng `Found` hoặc `LookupFailed`.
4. `instanceof` có pattern variable là tính năng chính thức trong Java 17. Không dùng `switch (result) { case Found f -> ... }` trong ví dụ vì type-pattern `switch` lúc đó vẫn là preview.

**Lưu ý về tính đầy đủ:** đoạn `if/instanceof` trên không được Java 17 xác minh tính exhaustive theo sealed hierarchy. Nếu thêm một kiểu mới vào `permits`, compiler Java 17 không nhất thiết bắt bạn thêm một `if` tương ứng; phần xử lý cuối giúp phát hiện trường hợp chưa được hỗ trợ lúc chạy. Khi cần hành vi theo biến thể mà tránh thao tác phân nhánh ở nhiều nơi, có thể thiết kế phương thức đa hình hoặc visitor phù hợp.

### 3.2. `sealed` không đồng nghĩa toàn bộ cây luôn đóng

Một kiểu con trực tiếp của sealed interface phải khai báo phương án tiếp tục:

```java
sealed interface Command permits BuiltInCommand, ExtensionCommand {}

sealed interface BuiltInCommand extends Command
        permits StartCommand, StopCommand {}

non-sealed interface ExtensionCommand extends Command {}

record StartCommand() implements BuiltInCommand {}
record StopCommand() implements BuiltInCommand {}

record CustomCommand(String pluginName) implements ExtensionCommand {}
```

`BuiltInCommand` duy trì danh sách biến thể giới hạn. `ExtensionCommand` mở nhánh cho các kiểu mới. Cách này có ích khi chỉ **một phần** của hệ phân cấp cần khả năng mở rộng. Tuy vậy, với kiến trúc plugin mà bên thứ ba phải triển khai trực tiếp interface gốc, **interface thường** có thể đơn giản và phù hợp hơn sealed interface.

Trong Java 17, các kiểu con được phép trực tiếp của sealed type phải ở **cùng named module** với kiểu cha; nếu dùng **unnamed module**, chúng phải ở **cùng package**. Thiết kế các sealed hierarchy xuyên qua module độc lập vì thế cần cân nhắc cẩn thận.

## 4. Khi nên kết hợp enum và sealed

Kết hợp thường hợp lý khi một kiểu biểu diễn **hình dạng thông điệp**, còn enum biểu diễn một **phân loại lặp lại giữa các thông điệp**.

Ví dụ: hệ thống trả kết quả thanh toán gồm:

- `Approved`: có mã giao dịch đã chấp thuận và số tiền.
- `Rejected`: có mã lý do và thông báo chi tiết.
- `Pending`: có thời điểm dự kiến xác nhận.

Các kết quả này khác nhau về payload, nên có thể dùng **sealed interface + record**. Nhưng danh sách lý do từ chối `INSUFFICIENT_FUNDS`, `INVALID_DETAILS`, `RISK_REVIEW` là các **giá trị phân loại**, nên phù hợp với **enum**.

### 4.1. Ví dụ hoàn chỉnh: sealed cho kết quả, enum cho mã lý do

Tạo file **`PaymentResultDemo.java`**:

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;

enum RejectReason {
    INSUFFICIENT_FUNDS,
    INVALID_DETAILS,
    RISK_REVIEW
}

sealed interface PaymentResult
        permits Approved, Rejected, Pending {}

record Approved(String transactionId, BigDecimal amount)
        implements PaymentResult {
    Approved {
        Objects.requireNonNull(transactionId, "transactionId");
        Objects.requireNonNull(amount, "amount");
        if (amount.signum() <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
    }
}

record Rejected(RejectReason reason, String message)
        implements PaymentResult {
    Rejected {
        Objects.requireNonNull(reason, "reason");
        Objects.requireNonNull(message, "message");
    }
}

record Pending(Instant nextCheckAt) implements PaymentResult {
    Pending {
        Objects.requireNonNull(nextCheckAt, "nextCheckAt");
    }
}

public class PaymentResultDemo {
    static String render(PaymentResult result) {
        if (result instanceof Approved approved) {
            return "Approved #" + approved.transactionId()
                    + ": " + approved.amount();
        }
        if (result instanceof Rejected rejected) {
            return "Rejected [" + rejected.reason() + "]: "
                    + rejected.message();
        }
        if (result instanceof Pending pending) {
            return "Pending until " + pending.nextCheckAt();
        }
        throw new IllegalStateException("Unexpected result: " + result);
    }

    public static void main(String[] args) {
        PaymentResult a = new Approved(
                "TX-101", new BigDecimal("125.00")
        );
        PaymentResult b = new Rejected(
                RejectReason.INSUFFICIENT_FUNDS,
                "Account balance is too low"
        );
        PaymentResult c = new Pending(
                Instant.parse("2026-12-01T09:00:00Z")
        );

        System.out.println(render(a));
        System.out.println(render(b));
        System.out.println(render(c));
    }
}
```

```bash
javac --release 17 PaymentResultDemo.java
java PaymentResultDemo
```

Sơ đồ:

```text
PaymentResult                (sealed interface)
├── Approved                 (record: transactionId, amount)
├── Rejected                 (record: reason, message)
│   └── reason               (enum RejectReason)
└── Pending                  (record: nextCheckAt)
```

`RejectReason` **không phải kiểu con** của `PaymentResult`; nó là **thành phần dữ liệu bên trong** `Rejected`. Nếu thêm một mã lý do mới, về mặt kiểu dữ liệu không phải tạo lớp kết quả thanh toán mới. Nếu thêm một loại kết quả với cấu trúc khác, phải thay đổi danh sách các kiểu con được phép của `PaymentResult`.

Đây là một cách tránh thiết kế cồng kềnh như `RejectedInsufficientFunds`, `RejectedInvalidDetails`, `RejectedRiskReview` khi các trường hợp từ chối đều chia sẻ cấu trúc `reason + message`. Trong trường hợp từng lý do cần payload hoàn toàn khác nhau hoặc bất biến riêng, mới cân nhắc đưa chúng thành các biến thể sealed độc lập.

### 4.2. Enum cũng có thể trực tiếp triển khai sealed interface

Không có quy định bắt buộc kiểu con của sealed interface phải là `record`. Nếu một nhánh thật sự là các **giá trị hằng không có payload động**, có thể sử dụng enum làm kiểu con được phép:

```java
sealed interface UserAction permits NavigationAction, SendMessage {}

enum NavigationAction implements UserAction {
    BACK,
    HOME,
    REFRESH
}

record SendMessage(String text) implements UserAction {}
```

`UserAction` có một nhánh gồm các hành động điều hướng cố định và một nhánh có payload mới theo từng lần gửi tin. `NavigationAction` là **một kiểu con trực tiếp** của `UserAction`, không phải ba kiểu con `BACK`, `HOME`, `REFRESH`. Theo quy tắc Java 17, enum là kiểu đặc biệt với ngữ nghĩa đóng phân cấp; không cần gắn modifier `final` hay `sealed` thủ công lên khai báo enum.

Tuy nhiên, chỉ chọn cách kết hợp này khi việc gọi cả hai nhóm là `UserAction` thực sự mang ý nghĩa nghiệp vụ. Không cần tạo sealed root cho mọi enum trong dự án.

## 5. Khi composition đơn giản hơn hệ phân cấp

Một mô hình có nhiều **chiều thay đổi độc lập** không nên sinh lớp con cho mọi tổ hợp. Ví dụ, đơn hàng có hai chiều:

- **Trạng thái:** `CREATED`, `PAID`, `CANCELLED`.
- **Kênh thanh toán:** `CARD`, `BANK_TRANSFER`, `WALLET`.

Nếu tạo class riêng cho mỗi tổ hợp, số biến thể tăng tới `3 × 3 = 9` kiểu, rồi còn tăng khi bổ sung trạng thái hoặc kênh. Trong khi đó, hai chiều này có thể biểu diễn bằng hai field enum của một record:

```java
import java.util.Objects;

enum OrderStatus {
    CREATED, PAID, CANCELLED
}

enum PaymentChannel {
    CARD, BANK_TRANSFER, WALLET
}

record Order(
        long id,
        OrderStatus status,
        PaymentChannel channel
) {
    Order {
        if (id <= 0) {
            throw new IllegalArgumentException("id must be positive");
        }
        Objects.requireNonNull(status, "status");
        Objects.requireNonNull(channel, "channel");
    }
}
```

Ví dụ một đối tượng: `new Order(42, OrderStatus.PAID, PaymentChannel.CARD)`. Khi thêm kênh thanh toán, không phải thêm một kiểu con cho mỗi trạng thái. **Composition biểu diễn những gì đối tượng có** (`status`, `channel`) thay vì biến mọi tổ hợp thành quan hệ **is-a**.

Không phải mọi tổ hợp đều hợp lệ theo nghiệp vụ. Nếu có trạng thái chỉ được phép với một số kênh, cần đặt **quy tắc kiểm tra** tại nơi tạo hoặc chuyển trạng thái, không giả định vì Java cho phép hai enum values xuất hiện cùng nhau nên giao dịch đó hợp lệ.

### 5.1. Kết hợp dữ liệu và hành vi ở đúng mức

Với miền nghiệp vụ lớn hơn, có thể chia trách nhiệm:

| Thành phần | Mục đích |
| --- | --- |
| `enum OrderStatus` | Tên các trạng thái nghiệp vụ hữu hạn. |
| `enum PaymentChannel` | Phân loại kênh thanh toán. |
| `record Order` | Dữ liệu riêng từng đơn hàng và các bất biến cục bộ. |
| `sealed interface PaymentResult` | Các hình dạng kết quả xử lý có payload khác nhau. |
| `PaymentService` | Điều phối nghiệp vụ, giao tiếp hệ thống bên ngoài, áp dụng quy tắc chuyển trạng thái. |

Tránh đẩy mọi logic nghiệp vụ vào enum hoặc tạo một cây sealed rất lớn chỉ để gom các chức năng không cùng một quan hệ kiểu. Sealed thường tốt khi biến thể thực sự có **nghĩa khác nhau**; enum tốt khi các lựa chọn cùng một dạng dữ liệu; composition tốt khi có **nhiều thuộc tính khác nhau**.

## 6. Quy trình ra quyết định

Có thể dùng chuỗi câu hỏi sau để thiết kế:

```text
Bài toán đang mô tả điều gì?
│
├─ Một danh sách giá trị tên cố định?
│  └─ enum
│
├─ Các loại đối tượng có payload/bất biến khác nhau?
│  ├─ Tập loại con trực tiếp được quản lý rõ ràng?
│  │  └─ sealed interface/class + record/class/enum phù hợp
│  └─ Cần bên thứ ba tự triển khai trực tiếp?
│     └─ interface thông thường (hoặc chọn nhánh non-sealed rõ ràng)
│
└─ Nhiều trục phân loại/thuộc tính độc lập?
   └─ composition: record/class chứa enum, sealed types hoặc đối tượng khác
```

Sau khi chọn hướng chính, tự hỏi tiếp:

1. **Từng trường hợp có mang dữ liệu mới không?** Nếu cần `transactionId` khác nhau theo mỗi lần gọi, không nên cố đặt nó trong enum constant.
2. **Có bao nhiêu loại biến thể và ai được phép thêm?** Sealed phù hợp khi có người kiểm soát tập con trực tiếp; interface mở phù hợp cho extension point công khai.
3. **Các trường hợp có cùng một hình dạng không?** Nếu đều có `code + description` thì một record với field enum có thể đủ.
4. **Hai chiều có độc lập không?** Nếu thêm một giá trị ở chiều A không nên kéo theo tạo nhiều loại ở chiều B, composition thường tự nhiên hơn.
5. **Người dùng API sẽ xử lý các trường hợp ra sao?** Enum phù hợp với `switch` Java 17; sealed có thể dùng method đa hình hoặc `instanceof`, nhưng type-pattern `switch` của Java 17 là preview.

## 7. Các lỗi mô hình hóa thường gặp

### 7.1. Dùng enum để giữ trạng thái riêng từng request

```java
enum ConnectionState {
    CONNECTED, DISCONNECTED;

    // Tránh thêm field mutable như:
    // String currentUserId;
}
```

Mỗi constant được chia sẻ. `ConnectionState.CONNECTED` không đại diện cho **một phiên kết nối cụ thể**; nên có `record Session(String userId, ConnectionState state)` hoặc một class đối tượng session phù hợp.

### 7.2. Tạo hàng chục subclass cho những phân loại đơn thuần

Nếu khác biệt duy nhất giữa các trường hợp là `severity` (`INFO`, `WARN`, `ERROR`), một `enum Severity` và `record LogEntry(Severity severity, String message)` có thể dễ hiểu hơn `InfoLog`, `WarnLog`, `ErrorLog`.

Chỉ nâng thành sealed hierarchy nếu từng trường hợp có **payload hoặc bất biến riêng đáng kể** hoặc sự khác biệt đó thật sự cần được biểu diễn bằng kiểu tĩnh.

### 7.3. Dùng `sealed` cho điểm mở rộng công khai

Thư viện cung cấp `sealed interface Plugin` sẽ ngăn module của người dùng tạo lớp trực tiếp triển khai `Plugin` nếu lớp đó không thuộc tập `permits` hợp lệ. Nếu mục tiêu là cho bất kỳ người dùng nào viết plugin, một interface thường là lựa chọn tự nhiên hơn.

Có thể dùng **sealed root + nhánh `non-sealed`** khi muốn chỉ định rõ điểm mở rộng, nhưng phải đánh giá kỹ yêu cầu module/package và trải nghiệm của người dùng thư viện.

### 7.4. Cho rằng sealed tự động cho `switch` phân nhánh theo subtype trong Java 17

```java
// Đây là cú pháp pattern matching cho switch từng ở preview trong Java 17:
// return switch (result) {
//     case Found f -> f.value();
//     case NotFound n -> "...";
//     case LookupFailed e -> "...";
// };
```

Với Java 17 không bật preview, dùng `instanceof` pattern hoặc đa hình. Đừng lấy ví dụ của Java 21+ rồi coi là cú pháp ổn định trên Java 17.

### 7.5. Xem `permits` là danh sách mọi instance

`sealed interface Result permits Success, Failure` chỉ hạn chế **hai kiểu con trực tiếp**. Chương trình vẫn có thể tạo một triệu `Success` với một triệu payload khác nhau. Đây là khác biệt căn bản với tập constant của enum.

### 7.6. Lưu enum theo `ordinal()` hoặc tin rằng tên enum không bao giờ đổi

Không lưu `ordinal()` làm mã nghiệp vụ bền vững vì chỉ cần chèn hoặc sắp thứ tự lại constant là số thứ tự có thể thay đổi. Nếu phải giao tiếp API hoặc lưu database, dùng mã rõ ràng:

```java
enum DeliveryStatus {
    CREATED("created"),
    IN_TRANSIT("in_transit"),
    DELIVERED("delivered");

    private final String code;

    DeliveryStatus(String code) {
        this.code = code;
    }

    String code() {
        return code;
    }
}
```

Đặt chính sách tương thích khi thêm, đổi tên hoặc bỏ enum constant. Việc bổ sung một constant hoặc một kiểu con sealed có thể khiến code phía sử dụng cần cập nhật các nhánh xử lý; trong Java 17, đặc biệt cần chú ý các nhánh `switch` trên enum và logic `instanceof` trên sealed.

## 8. Khác biệt giữa `sealed class` và `sealed interface` khi thiết kế

Nếu chọn sealed, vẫn phải quyết định dùng class hay interface:

| `sealed interface` | `sealed class` |
| --- | --- |
| Phù hợp khi các biến thể chỉ cần chia sẻ một **hợp đồng kiểu**, không cần dữ liệu nền chung. | Phù hợp khi các lớp con có **trạng thái/constructor/triển khai chung** đáng kể. |
| Một class có thể triển khai nhiều interface, nếu đáp ứng quy tắc `permits`. | Java chỉ cho một class kế thừa trực tiếp một superclass. |
| Record và enum có thể trực tiếp implement interface (và dùng được khi là kiểu được phép). | Record và enum không thể `extends` một sealed class thông thường do đã có superclass đặc biệt. |
| Thường tự nhiên cho `sealed interface Result permits Success, Failure`. | Hữu ích cho một họ class có constructor hoặc thành phần bảo vệ được chia sẻ. |

Ví dụ đơn giản với sealed class:

```java
sealed abstract class ReportItem permits TextItem, ImageItem {
    private final String id;

    protected ReportItem(String id) {
        this.id = java.util.Objects.requireNonNull(id);
    }

    public String id() {
        return id;
    }
}

final class TextItem extends ReportItem {
    private final String text;

    TextItem(String id, String text) {
        super(id);
        this.text = text;
    }

    String text() {
        return text;
    }
}

final class ImageItem extends ReportItem {
    ImageItem(String id) {
        super(id);
    }
}
```

Trong ví dụ này, sealed class giữ chung `id` và constructor để bảo đảm mỗi phần tử có định danh. Nếu các biến thể không cần trạng thái nền, sealed interface + record thường gọn hơn.

## 9. Bài tập thiết kế

**Bài 1 — Phân loại thiết kế.** Với từng mô hình sau, chọn `enum`, `sealed` hoặc composition, rồi giải thích lựa chọn:

1. Mức ưu tiên `LOW/MEDIUM/HIGH`.
2. Kết quả tải tệp: `Success(bytes)`, `NotFound(path)`, `Failure(cause)`.
3. Bản ghi đơn hàng gồm trạng thái, kênh đặt hàng, mã đơn và thời điểm tạo.
4. Loại thông báo gồm `Email(to, subject)` và `Sms(phoneNumber)`.

**Bài 2 — Refactor mô hình.** Một hệ thống có chín class: `CardPending`, `CardApproved`, `CardRejected`, `WalletPending`, `WalletApproved`, v.v. Nếu trạng thái và kênh thanh toán độc lập, hãy thiết kế lại thành một record chứa hai enum. Nếu trạng thái `Rejected` phải có lý do cụ thể, hãy cân nhắc tách phần **kết quả xử lý** thành sealed type có payload thay vì tạo chín class như ban đầu.

**Bài 3 — Kết hợp enum với sealed.** Thiết kế `sealed interface Notification` gồm `EmailNotification` và `SmsNotification`. Đưa `enum Urgency { NORMAL, HIGH }` vào dữ liệu chung cần thiết của mỗi notification. Xác định kiểu nào quyết định hình dạng payload, kiểu nào phân loại độ khẩn cấp.

**Bài 4 — Chọn sealed hay interface thường.** Xây dựng SDK cho phép khách hàng tự tạo nhiều `StorageProvider` trong các module khác nhau. Hãy phân tích vì sao `sealed interface StorageProvider` có thể làm khó nhu cầu mở rộng và khi nào một nhánh `non-sealed` có thể hữu ích.

## 10. Tài liệu Java 17 chính thức để tra cứu

- [JLS Java SE 17, §8.9 — Enum Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.9): enum constant, constructor, thành viên và ngữ nghĩa enum.
- [JLS Java SE 17, §8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): record component, constructor và tính `final` của record.
- [JLS Java SE 17, §9.1.1.4 — Sealed and Non-Sealed Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.1.4): điều kiện mở rộng của sealed interface.
- [JLS Java SE 17, §9.1.4 — Permitted Direct Subclasses and Subinterfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.4): quy tắc `permits`, module và package.
- [JLS Java SE 17, §8.1.1.2 — Sealed, Non-Sealed, and Final Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.1.2): giới hạn class con.
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): bối cảnh thiết kế và trạng thái chính thức trong JDK 17.
- [JEP 361 — Switch Expressions](https://openjdk.org/jeps/361): `switch expression` chính thức từ Java 14 và dùng ổn định trong Java 17.
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394): pattern matching cho `instanceof` đã chính thức trước Java 17.
- [JEP 406 — Pattern Matching for switch (Preview)](https://openjdk.org/jeps/406): trạng thái preview của type-pattern `switch` ở Java 17.

**Cách nhớ để thiết kế:** dùng **enum** cho *những giá trị cố định*, dùng **sealed** cho *những loại đối tượng có cấu trúc và quy tắc riêng*, và dùng **composition** khi các phần dữ liệu thay đổi theo *những chiều độc lập*. Có thể kết hợp chúng trong cùng một mô hình, miễn mỗi công cụ chịu trách nhiệm đúng phần mà nó thể hiện rõ nhất.
