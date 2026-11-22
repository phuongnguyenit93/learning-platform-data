# Enum, sealed type và tính đầy đủ của switch khi API mở rộng

Trong Java, enum và sealed type giúp mô hình hóa những tập giá trị hoặc kiểu con có thể xác định trước. Từ Java 21, pattern matching for switch đã trở thành tính năng chính thức, cho phép compiler kiểm tra nhiều switch expression dựa trên enum hoặc sealed hierarchy có bao phủ hết các trường hợp hay không.

Tuy nhiên, “đầy đủ” ở thời điểm biên dịch không có nghĩa tập giá trị của API sẽ không bao giờ thay đổi. Một thư viện có thể thêm enum constant hoặc thêm permitted subtype sau khi ứng dụng tiêu thụ đã được biên dịch. Khi đó, mã nguồn được biên dịch lại và binary cũ có thể phản ứng khác nhau. Nếu không thiết kế rõ chính sách xử lý giá trị mới, một thay đổi tưởng như nhỏ trong API có thể dẫn đến lỗi runtime hoặc bỏ sót nghiệp vụ.

Bài học này giải thích cách enum, sealed hierarchy và switch exhaustiveness tương tác với nhau; phân biệt source compatibility, binary compatibility và behavior compatibility; đồng thời đưa ra cách thiết kế fallback và kiểm thử khi API được mở rộng trong quá trình migration Java.

## 1. Vì sao tính đầy đủ của switch quan trọng trong migration?

Một switch được xem là exhaustive khi compiler xác định mọi giá trị có thể đi vào switch đều được xử lý bởi một nhánh. Điều này đặc biệt hữu ích với switch expression, vì biểu thức phải tạo ra một kết quả trên mọi đường đi.

Ví dụ, một hệ thống thanh toán có ba trạng thái:

```java
enum PaymentStatus {
    PENDING,
    AUTHORIZED,
    SETTLED
}

static String describe(PaymentStatus status) {
    return switch (status) {
        case PENDING -> "Waiting for payment";
        case AUTHORIZED -> "Payment authorized";
        case SETTLED -> "Payment completed";
    };
}
```

Compiler chấp nhận switch expression này vì tại thời điểm biên dịch, enum có đúng ba constant và cả ba đều được liệt kê. Nếu một phiên bản thư viện sau đó thêm constant REVERSED, tình huống trở nên khác:

- Khi biên dịch lại ứng dụng với phiên bản thư viện mới, switch expression thiếu nhánh REVERSED và compiler báo lỗi chưa bao phủ hết trường hợp.
- Khi chạy binary cũ đã biên dịch với enum cũ nhưng nạp enum mới, nếu giá trị mới đi vào switch expression, nhánh fallback do compiler sinh ra có thể ném IncompatibleClassChangeError.
- Nếu dùng switch statement không có default, giá trị mới có thể không khớp nhánh nào và phần xử lý bị bỏ qua.

Đây là khác biệt quan trọng giữa kiểm tra ở compile time và dữ liệu thực tế ở runtime. API có thể được nâng cấp độc lập với ứng dụng tiêu thụ; vì vậy, migration phải xem xét cả hai thời điểm.

## 2. Enum: tập constant có thể mở rộng theo phiên bản thư viện

### 2.1. Enum đóng trong một bản phát hành, nhưng API vẫn có thể tiến hóa

Enum biểu diễn một tập constant được khai báo trong kiểu:

```java
public enum DeliveryState {
    CREATED,
    PACKED,
    SHIPPED,
    DELIVERED
}
```

Trong một phiên bản cụ thể của thư viện, tập constant này là hữu hạn và compiler có thể liệt kê được. Nhưng nếu enum là API công khai, nhà cung cấp có thể thêm constant trong một phiên bản sau:

```java
public enum DeliveryState {
    CREATED,
    PACKED,
    SHIPPED,
    DELIVERED,
    RETURNED
}
```

Mã nguồn tiêu thụ đã biên dịch trước đó vẫn có thể liên kết với enum mới ở mức JVM. Việc thêm constant thường được xem là binary-compatible theo quy tắc tương thích Java, nhưng điều đó không bảo đảm logic nghiệp vụ của consumer xử lý được giá trị mới.

Một số API có thể trả về constant mới từ server, database, plugin hoặc dependency mà ứng dụng cũ chưa từng biết. Vì vậy, hãy coi enum công khai là một hợp đồng có thể tiến hóa nếu nhà cung cấp không cam kết giữ nguyên tập constant vĩnh viễn.

### 2.2. Switch expression và switch statement có hành vi khác nhau

**Switch expression** phải exhaustive. Nếu không có default, compiler kiểm tra các constant đã được bao phủ:

```java
static int calculateFee(DeliveryState state) {
    return switch (state) {
        case CREATED -> 0;
        case PACKED -> 5;
        case SHIPPED -> 10;
        case DELIVERED -> 0;
    };
}
```

Khi biên dịch lại với enum có thêm RETURNED, compiler yêu cầu xử lý constant mới. Đây là tín hiệu hữu ích: thay đổi API buộc developer xem lại logic.

Một switch expression exhaustive được biên dịch có thể chứa nhánh dự phòng tổng hợp để bảo vệ trường hợp binary được biên dịch riêng với phiên bản enum khác. Nếu runtime gặp constant mới không có trong tập đã biết lúc biên dịch, nhánh dự phòng này có thể ném IncompatibleClassChangeError. Đây là lỗi có chủ đích để không âm thầm tính toán sai.

**Switch statement** không bắt buộc phải liệt kê mọi enum constant. Ví dụ:

```java
static void updateInventory(DeliveryState state) {
    switch (state) {
        case CREATED -> reserveStock();
        case PACKED -> prepareShipment();
        case SHIPPED -> markInTransit();
        case DELIVERED -> closeOrder();
    }
}
```

Nếu runtime nhận RETURNED, không nhánh nào chạy. Code vẫn có thể hoàn tất bình thường, nhưng nghiệp vụ hoàn hàng không được xử lý. Đây là dạng lỗi khó phát hiện vì không nhất thiết có exception.

Nếu switch statement mang ý nghĩa xử lý bắt buộc, hãy thêm nhánh default với hành vi có chủ đích, chẳng hạn log và từ chối xử lý:

```java
static void processDeliveryState(DeliveryState state) {
    switch (state) {
        case CREATED -> reserveStock();
        case PACKED -> prepareShipment();
        case SHIPPED -> markInTransit();
        case DELIVERED -> closeOrder();
        default -> throw new IllegalArgumentException(
            "Unsupported delivery state: " + state
        );
    }
}
```

Cách này giúp binary cũ thất bại rõ ràng khi gặp trạng thái mới. Nếu nghiệp vụ cho phép bỏ qua hoặc chuyển tiếp giá trị chưa biết, default branch có thể ghi nhận telemetry và áp dụng chính sách fallback phù hợp. Không nên để nhánh mặc định rỗng nếu việc bỏ qua có thể làm sai dữ liệu.

### 2.3. Chọn giữa exhaustive switch và default fallback

Có hai mục tiêu thiết kế khác nhau:

- **Muốn buộc consumer xem xét mọi constant mới:** dùng switch expression liệt kê từng constant và không thêm default. Khi consumer biên dịch lại với API mới, compiler sẽ yêu cầu cập nhật.
- **Muốn binary cũ có thể xử lý an toàn constant chưa biết:** dùng default branch với chính sách rõ ràng, hoặc dùng một lớp chuyển đổi đầu vào để biểu diễn giá trị chưa biết.

Không có lựa chọn nào tốt cho mọi hệ thống. Nếu trạng thái mới ảnh hưởng đến tiền, quyền truy cập, dữ liệu hoặc workflow, thất bại rõ ràng thường an toàn hơn việc tự suy đoán. Nếu giá trị mới chỉ là một nhãn hiển thị không quan trọng, fallback có thể giữ trải nghiệm ổn định hơn.

Điều cần tránh là vừa dùng default để bỏ qua mọi giá trị lạ, vừa giả định compiler sẽ nhắc khi enum được mở rộng. Khi có default, compiler không còn buộc consumer liệt kê constant mới.

### 2.4. Null là trường hợp riêng

Default không đồng nghĩa với xử lý null. Với switch trên reference type, selector null thường gây NullPointerException nếu không có nhánh null được hỗ trợ.

Trong pattern switch từ Java 21, có thể xử lý null tường minh:

```java
static String display(DeliveryState state) {
    return switch (state) {
        case null -> "No state supplied";
        case CREATED -> "Created";
        case PACKED -> "Packed";
        case SHIPPED -> "Shipped";
        case DELIVERED -> "Delivered";
        default -> "Other state: " + state.name();
    };
}
```

Nếu API không cho phép null, có thể xác thực đầu vào trước switch và giữ invariant non-null. Điều quan trọng là null policy phải rõ ràng, không dựa vào default branch.

### 2.5. Enum constant và dữ liệu lưu trữ

Mở rộng enum có thể ảnh hưởng đến dữ liệu được lưu hoặc truyền ra ngoài:

- ordinal() là vị trí constant trong khai báo. Chèn constant ở giữa làm thay đổi ordinal của các constant phía sau.
- EnumType.ORDINAL trong JPA lưu số thứ tự; khi enum thay đổi thứ tự, dữ liệu cũ có thể bị diễn giải thành trạng thái khác.
- EnumType.STRING lưu tên constant, ổn định hơn ordinal nhưng vẫn bị ảnh hưởng nếu đổi tên constant.
- Java serialization của enum sử dụng tên constant. Đổi tên có thể làm dữ liệu serialize cũ không đọc được.
- JSON hoặc message broker thường serialize enum theo tên, nhưng hành vi cụ thể phụ thuộc thư viện và cấu hình.

Không nên dùng ordinal làm mã nghiệp vụ, mã database hoặc wire protocol. Nếu giá trị enum là một phần của hợp đồng lâu dài, hãy gắn mã ổn định riêng:

```java
public enum PaymentStatus {
    PENDING("P"),
    AUTHORIZED("A"),
    SETTLED("S");

    private final String code;

    PaymentStatus(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }
}
```

Khi đọc dữ liệu, hãy ánh xạ theo code và có chính sách cho code chưa biết. Ví dụ, một API nhận trạng thái từ dịch vụ mới có thể giữ nguyên raw value để log hoặc chuyển tiếp thay vì cố ép mọi chuỗi thành enum hiện tại.

```java
import java.util.Optional;

static Optional<PaymentStatus> findByCode(String code) {
    for (PaymentStatus status : PaymentStatus.values()) {
        if (status.code().equals(code)) {
            return Optional.of(status);
        }
    }
    return Optional.empty();
}
```

Optional.empty() giúp caller nhận biết giá trị chưa được hỗ trợ. Nếu hệ thống cần round-trip dữ liệu chưa biết, hãy lưu raw code riêng thay vì bỏ mất nó.

## 3. Sealed type: tập kiểu con được khai báo rõ ràng

### 3.1. Cách sealed hierarchy giới hạn kiểu con

Sealed class hoặc sealed interface cho phép khai báo những kiểu được phép kế thừa hoặc triển khai trực tiếp. Mỗi kiểu con trực tiếp phải thuộc một trong các dạng final, sealed hoặc non-sealed.

Ví dụ:

```java
public sealed interface PaymentCommand
        permits CapturePayment, CancelPayment {
}

public record CapturePayment(String transactionId)
        implements PaymentCommand {
}

public record CancelPayment(String transactionId)
        implements PaymentCommand {
}
```

Trong ví dụ này, PaymentCommand chỉ có hai permitted subtype trực tiếp. Compiler có thể dùng danh sách đó để kiểm tra switch pattern có bao phủ các nhánh hay không.

```java
static String route(PaymentCommand command) {
    return switch (command) {
        case CapturePayment capture ->
            "capture:" + capture.transactionId();
        case CancelPayment cancel ->
            "cancel:" + cancel.transactionId();
    };
}
```

Switch expression này exhaustive vì mọi subtype được phép đều đã có nhánh. Khi API được mở rộng, compiler và runtime cần được xem xét lại.

### 3.2. Thêm permitted subtype là một thay đổi hợp đồng

Giả sử phiên bản tiếp theo bổ sung lệnh hoàn tiền:

```java
public sealed interface PaymentCommand
        permits CapturePayment, CancelPayment, RefundPayment {
}

public record RefundPayment(String transactionId, long amount)
        implements PaymentCommand {
}
```

Consumer biên dịch lại với API mới sẽ thấy switch expression cũ không còn exhaustive và phải thêm nhánh cho RefundPayment hoặc một fallback có chủ đích.

Consumer binary đã biên dịch với danh sách subtype cũ có thể vẫn được nạp cùng thư viện mới. Tuy nhiên, nếu một instance RefundPayment đi vào switch expression cũ, nhánh dự phòng do compiler sinh ra cho switch exhaustive có thể ném IncompatibleClassChangeError. Do đó, việc thêm permitted subtype có thể gây thay đổi hành vi đáng kể dù code consumer không được build lại.

Với switch statement không có default, subtype mới có thể không khớp nhánh nào. Điều này có cùng rủi ro bỏ sót nghiệp vụ như enum switch statement.

### 3.3. sealed, final và non-sealed ảnh hưởng đến exhaustiveness

Ba trạng thái của subtype quyết định tập kiểu con có thể xuất hiện:

- final: nhánh kết thúc; không có subtype mới kế thừa tiếp.
- sealed: subtype tiếp tục công bố một tập permitted subtype riêng.
- non-sealed: mở lại nhánh cho phép kiểu khác kế thừa hoặc triển khai.

Ví dụ, API muốn cho phép plugin bên ngoài mở rộng một nhánh:

```java
public sealed interface PluginCommand
        permits BuiltInCommand, ExternalCommand {
}

public record BuiltInCommand(String name)
        implements PluginCommand {
}

public non-sealed interface ExternalCommand
        extends PluginCommand {
}
```

Khi switch trên PluginCommand, một nhánh cho ExternalCommand có thể bao phủ mọi implementation bên ngoài:

```java
static String handle(PluginCommand command) {
    return switch (command) {
        case BuiltInCommand builtIn ->
            "Built-in: " + builtIn.name();
        case ExternalCommand external ->
            "External command";
    };
}
```

Nếu một plugin mới triển khai ExternalCommand, consumer vẫn có thể xử lý qua nhánh này mà không cần sửa sealed parent. Đây là một cách thiết kế extension point có chủ đích.

Nếu tất cả nhánh đều sealed hoặc final, tập kiểu con có thể được kiểm tra đầy đủ ở compile time. Nếu có nhánh non-sealed, hãy xử lý chính nhánh đó như một nhóm mở thay vì cố liệt kê mọi implementation có thể xuất hiện trong tương lai.

### 3.4. Pattern guard không nhất thiết bao phủ toàn bộ subtype

Một pattern có điều kiện chỉ xử lý những instance thỏa điều kiện. Ví dụ:

```java
static String classify(PaymentCommand command) {
    return switch (command) {
        case CapturePayment capture
                when capture.transactionId().startsWith("VIP-") ->
            "Priority capture";
        case CapturePayment capture ->
            "Regular capture";
        case CancelPayment cancel ->
            "Cancellation";
    };
}
```

Nhánh đầu chỉ xử lý capture có transaction ID bắt đầu bằng VIP-. Nhánh thứ hai xử lý các capture còn lại. Nếu bỏ nhánh thứ hai, switch có thể không còn exhaustive vì guard không bao phủ toàn bộ kiểu CapturePayment.

Khi rà soát pattern switch, hãy kiểm tra cả guard và thứ tự nhánh. Compiler phát hiện các pattern bị dominate bởi pattern tổng quát hơn. Ví dụ, đặt nhánh PaymentCommand command trước nhánh CapturePayment capture làm nhánh sau không thể được chọn. Đây thường là lỗi biên dịch hữu ích, nhưng cũng là dấu hiệu cần thiết kế lại thứ tự hoặc mức độ cụ thể của pattern.

### 3.5. Null và sealed pattern switch

Default xử lý các giá trị không khớp pattern khác, nhưng không nên mặc định rằng nó xử lý null. Nếu null là một đầu vào hợp lệ, hãy thêm nhánh rõ ràng:

```java
static String routeNullable(PaymentCommand command) {
    return switch (command) {
        case null -> "No command";
        case CapturePayment capture -> "Capture";
        case CancelPayment cancel -> "Cancel";
        case RefundPayment refund -> "Refund";
    };
}
```

Nếu API cam kết non-null, hãy thực thi điều đó ở biên hệ thống bằng validation hoặc constructor. Không để chính sách null rải rác trong từng switch.

## 4. Source compatibility, binary compatibility và behavior compatibility

Khi API thay đổi, cần đánh giá riêng ba khái niệm:

| Loại tương thích | Câu hỏi | Ví dụ với enum/sealed type |
|---|---|---|
| Source compatibility | Mã nguồn consumer có biên dịch lại được với API mới không? | Switch expression không có default thiếu enum constant hoặc permitted subtype mới nên biên dịch thất bại |
| Binary compatibility | Binary consumer cũ có thể liên kết với API mới không? | Thêm enum constant thường không làm hỏng linkage; thay đổi hierarchy và các kiểu được tham chiếu cần được đánh giá riêng |
| Behavior compatibility | Khi chạy, chương trình có xử lý đúng dữ liệu mới không? | Switch expression cũ có thể ném ICCE; switch statement có thể bỏ qua nhánh mới |

Một API có thể tương thích ở mức binary nhưng không tương thích về hành vi. Vì vậy, nhãn “binary compatible” trong release note không đủ để kết luận consumer không cần thay đổi.

### 4.1. Thêm enum constant

Thêm constant vào enum thường không làm các binary cũ mất khả năng liên kết với kiểu enum. Tuy nhiên:

- Switch expression exhaustive được biên dịch cũ có thể ném ICCE khi gặp constant mới.
- Switch statement không có default có thể bỏ qua constant mới.
- Logic dựa vào values().length, ordinal() hoặc thứ tự khai báo có thể thay đổi.
- Parser hoặc serializer có thể từ chối tên constant chưa biết.

Khi biên dịch lại, switch expression không có default sẽ buộc consumer xem xét constant mới. Đây là một hình thức kiểm tra source compatibility hữu ích.

### 4.2. Thêm permitted subtype

Với sealed API, thêm một kiểu vào danh sách permits mở rộng tập instance có thể xuất hiện ở runtime. Consumer biên dịch lại sẽ cần cập nhật switch expression exhaustive. Binary cũ có thể gặp nhánh synthetic fallback và ném ICCE khi subtype mới được truyền vào.

Điều này đặc biệt quan trọng khi API là public library hoặc SPI được nhiều ứng dụng triển khai độc lập. Một nhà cung cấp thư viện có thể phát hành subtype mới trong phiên bản minor, nhưng consumer cũ chưa chắc xử lý được. Hãy xác định rõ chính sách versioning và thông báo thay đổi cho người dùng API.

### 4.3. Đổi tên hoặc loại bỏ enum constant

Đổi tên constant không tương đương với thêm constant. Mã nguồn tham chiếu tên cũ sẽ không biên dịch. Binary cũ có thể gặp lỗi khi truy cập field constant không còn tồn tại. Dữ liệu Java serialization hoặc JSON lưu theo tên cũng có thể không đọc được.

Nếu cần thay tên hiển thị, hãy tách label khỏi tên constant. Nếu cần thay mã giao tiếp, dùng explicit stable code và hỗ trợ alias hoặc migration mapping trong một khoảng thời gian.

### 4.4. Thay đổi sealed hierarchy

Các thay đổi như bỏ permitted subtype, đổi kiểu con từ final sang non-sealed hoặc chuyển nhánh sang sealed có thể tác động đến cả consumer và extension code. Một class bên ngoài đang triển khai nhánh non-sealed có thể không còn hợp lệ nếu nhánh đó bị thay đổi. Một consumer dùng exhaustive switch cũng cần xem lại giả định về tập kiểu.

Khi công bố sealed hierarchy như một phần public API, hãy coi danh sách permits và trạng thái mở/đóng của từng nhánh là một phần hợp đồng. Đừng thay đổi nó mà không xem xét source consumer, binary consumer và plugin bên ngoài.

## 5. Thiết kế API để mở rộng an toàn

### 5.1. Khi nào nên dùng enum?

Enum phù hợp khi tập giá trị thuộc quyền kiểm soát của cùng một module hoặc khi miền nghiệp vụ có một tập lựa chọn tương đối ổn định. Ví dụ:

- Trạng thái nội bộ của workflow.
- Loại phép toán được một service duy nhất quản lý.
- Chế độ cấu hình có tập giá trị đóng.
- Kết quả phân loại do chính ứng dụng tạo.

Nếu enum là public API và nhà cung cấp có thể thêm constant, tài liệu phải nêu rõ consumer cần xử lý giá trị mới thế nào. Với các trạng thái có tác động nghiệp vụ, cân nhắc fail-fast hoặc biểu diễn unknown rõ ràng.

### 5.2. Khi nào nên dùng sealed type?

Sealed hierarchy phù hợp khi muốn mô hình hóa một tập biến thể có cấu trúc khác nhau, ví dụ các loại command, event, expression hoặc kết quả xử lý. Nó cho phép compiler kiểm tra nhánh switch dựa trên tập subtype được công bố.

Hãy chọn trạng thái subtype theo ý định mở rộng:

- Dùng final cho biến thể không cần mở rộng.
- Dùng sealed cho nhánh có một tập biến thể con được kiểm soát.
- Dùng non-sealed khi chủ động cho phép extension bên ngoài.

Một hierarchy được thiết kế để đóng hoàn toàn sẽ mang lại exhaustiveness tốt, nhưng việc thêm nhánh sau này cần được xem là thay đổi hợp đồng đối với consumer.

### 5.3. Tạo fallback có ý nghĩa

Fallback nên phản ánh nghiệp vụ, không chỉ làm compiler hết báo lỗi.

Một số lựa chọn:

| Chính sách | Khi phù hợp | Ví dụ hành vi |
|---|---|---|
| Fail fast | Giá trị mới có thể gây sai tiền, quyền, trạng thái hoặc workflow | Ném exception có thông tin constant/type chưa hỗ trợ |
| Unknown bucket | Giá trị mới có thể được hiển thị hoặc ghi nhận mà chưa cần hiểu | Hiển thị “Trạng thái chưa hỗ trợ” và log raw value |
| Preserve raw value | Gateway hoặc proxy cần chuyển tiếp dữ liệu chưa biết | Giữ nguyên code hoặc payload để round-trip |
| Ignore with telemetry | Sự kiện phụ, không ảnh hưởng tính đúng đắn | Bỏ qua có đếm metric và log có kiểm soát |
| Delegate extension | API plugin cần cho bên ngoài mở rộng | Chuyển qua interface non-sealed hoặc registry |

Đừng chọn ignore mặc định cho những thao tác quan trọng. Nếu hệ thống nhận một payment status mới, bỏ qua nó có thể làm đơn hàng treo hoặc đối soát sai. Fallback cần có owner, log/metric và quy tắc xử lý lại khi ứng dụng được nâng cấp.

### 5.4. Mô hình hóa giá trị mở bằng wrapper

Nếu dữ liệu đến từ hệ thống ngoài có thể thêm giá trị mới, một enum thuần có thể quá đóng. Có thể giữ cả giá trị đã nhận và kết quả parse:

```java
import java.util.Optional;

enum KnownStatus {
    PENDING,
    PAID,
    CANCELLED
}

record StatusValue(String raw, Optional<KnownStatus> known) {
    static StatusValue parse(String raw) {
        Optional<KnownStatus> known;
        try {
            known = Optional.of(KnownStatus.valueOf(raw));
        } catch (IllegalArgumentException ex) {
            known = Optional.empty();
        }
        return new StatusValue(raw, known);
    }
}
```

Ví dụ này giữ lại chuỗi gốc khi chưa nhận diện được. Trong hệ thống thực tế, cần xác định cách xử lý null, chuẩn hóa code và phân biệt giá trị không hợp lệ với giá trị mới hợp lệ nhưng chưa được ứng dụng hỗ trợ.

Có thể dùng wrapper này tại biên API, message consumer hoặc adapter database. Phần nghiệp vụ bên trong có thể chỉ nhận các trạng thái đã được xác thực; phần tích hợp chịu trách nhiệm giữ và ghi nhận raw value.

## 6. Rà soát switch khi API được mở rộng

### 6.1. Tìm tất cả switch liên quan đến enum và sealed type

Khi nâng phiên bản thư viện, hãy tìm switch trên các kiểu public API có thể thay đổi. Có thể bắt đầu bằng tìm kiếm từ khóa:

```shell
rg -n "switch\\s*\\(" src
rg -n "case\\s+[A-Z][A-Z0-9_]*\\s*->" src
rg -n "sealed\\s+(interface|class)|permits\\s+" src
```

Các lệnh trên là điểm khởi đầu; cần điều chỉnh đường dẫn và pattern theo cấu trúc dự án. Một số switch được tạo trong generated source hoặc nằm trong module khác, vì vậy cần kiểm tra cả code generated nếu nó được biên dịch vào artifact.

Lập inventory với các cột:

| Vị trí | Selector type | Dạng switch | Có default? | Rủi ro khi API mở rộng |
|---|---|---|---|---|
| OrderService.java | OrderStatus | Expression | Không | Recompile sẽ báo thiếu constant; binary cũ có thể ICCE |
| EventRouter.java | DomainEvent sealed | Pattern expression | Không | Subtype mới có thể làm binary cũ ném ICCE |
| AuditService.java | AuditLevel | Statement | Không | Giá trị mới có thể không được xử lý |
| LabelFormatter.java | DisplayState | Expression | Có | Fallback có thể xử lý giá trị mới nhưng cần kiểm tra semantics |

Bảng trên chỉ minh họa cách ghi inventory, không đại diện cho file của dự án.

### 6.2. Phân biệt switch expression và statement

Đừng chỉ tìm số lượng switch. Cần phân loại:

- Switch expression trả về giá trị và phải exhaustive.
- Switch statement thực hiện side effect và có thể không liệt kê hết mọi giá trị.
- Pattern switch dùng type pattern và guard; coverage phụ thuộc loại pattern.
- Switch có default đã có fallback nhưng có thể che việc API được mở rộng.
- Switch có nhánh null cần được kiểm tra riêng.

Với switch statement dùng để thực hiện các hành động nghiệp vụ, hãy cân nhắc chuyển sang switch expression nếu kết quả có thể biểu diễn thành giá trị. Compiler sẽ giúp phát hiện các trường hợp chưa được xử lý khi API thay đổi.

Ví dụ:

```java
static String actionFor(OrderStatus status) {
    return switch (status) {
        case CREATED -> "reserve";
        case PAID -> "fulfill";
        case SHIPPED -> "track";
        case CANCELLED -> "release";
    };
}
```

Nếu một trạng thái mới được thêm, lỗi biên dịch buộc developer quyết định hành vi. Đây là lợi thế của switch expression khi domain được quản lý chặt chẽ.

### 6.3. Kiểm tra guard và pattern dominance

Với sealed hierarchy, hãy xác nhận:

- Mỗi permitted subtype được bao phủ.
- Nhánh non-sealed được xử lý như một nhóm mở.
- Guard không bị nhầm là bao phủ toàn bộ subtype.
- Pattern tổng quát không đặt trước pattern cụ thể khiến nhánh sau bị dominate.
- Null có chính sách rõ ràng.
- Default có ý nghĩa nghiệp vụ và có quan sát được.

Nếu switch trở nên phức tạp với nhiều guard và pattern lồng nhau, cân nhắc tách logic thành method riêng để dễ kiểm thử. Không cần biến mọi switch thành một cấu trúc pattern phức tạp chỉ để sử dụng tính năng mới.

## 7. Kiểm thử tương thích khi API tăng phiên bản

Kiểm thử thông thường trên cùng một phiên bản dependency không đủ để phát hiện mọi vấn đề do API mở rộng. Cần kiểm tra cả consumer cũ và consumer được biên dịch lại.

### 7.1. Ma trận phiên bản producer và consumer

| Consumer | API runtime | Mục đích |
|---|---|---|
| Consumer build với API cũ | API cũ | Baseline hiện tại |
| Consumer build với API cũ | API mới có enum constant/subtype mới | Phát hiện runtime fallback, ICCE hoặc nhánh bị bỏ qua |
| Consumer build lại với API mới | API mới | Phát hiện compile error do switch expression thiếu nhánh |
| Consumer build với API mới | API cũ | Phát hiện consumer tham chiếu constant hoặc subtype chỉ có ở API mới |

Không phải tổ hợp nào cũng là cấu hình được hỗ trợ. Tuy nhiên, ma trận này giúp phân biệt lỗi source, linkage và behavior.

### 7.2. Kiểm thử enum được mở rộng

Một kịch bản kiểm thử hữu ích:

1. Tạo phiên bản API 1 với enum chỉ có các constant hiện tại.
2. Biên dịch consumer có switch expression exhaustive và switch statement không default.
3. Tạo phiên bản API 2 có thêm một enum constant.
4. Chạy binary consumer cũ với API 2.
5. Truyền constant mới vào từng switch và xác nhận hành vi.
6. Biên dịch lại consumer với API 2 và ghi nhận lỗi compile cần xử lý.
7. Thêm hoặc xác nhận fallback nếu consumer cần forward compatibility.

Mục tiêu không phải làm mọi consumer cũ tự động hiểu giá trị mới. Mục tiêu là đảm bảo hành vi khi gặp giá trị mới đã được quyết định và kiểm thử.

### 7.3. Kiểm thử sealed hierarchy được mở rộng

Thực hiện kịch bản tương tự:

1. API 1 công bố sealed interface với hai permitted subtype.
2. Consumer build switch expression bao phủ cả hai subtype.
3. API 2 bổ sung permitted subtype thứ ba.
4. Chạy binary consumer cũ với instance subtype mới.
5. Biên dịch lại consumer với API 2 để kiểm tra compiler yêu cầu nhánh mới.
6. Xác nhận fallback, non-sealed extension point hoặc chính sách versioning phù hợp.

Nếu API có plugin bên ngoài, thêm test cho implementation của nhánh non-sealed. Đảm bảo code consumer không giả định chỉ có các implementation built-in.

### 7.4. Kiểm thử serialization và protocol

Ngoài switch, hãy kiểm tra các đường đi của dữ liệu:

- JSON chứa enum constant mới.
- Message broker gửi code chưa được consumer biết.
- Database có giá trị trạng thái mới.
- Java serialization đọc dữ liệu được ghi bằng phiên bản mới.
- REST client và server được deploy lệch phiên bản.
- Cache hoặc event replay chứa giá trị từ một release sau.

Nếu protocol có khả năng mở rộng, kiểm tra cách thư viện serialization xử lý unknown enum value. Một số thư viện có tùy chọn map về default constant; một số khác ném lỗi. Không dựa vào default của thư viện mà chưa có test xác nhận.

## 8. Chiến lược versioning cho API có enum và sealed type

### 8.1. Xem việc thêm constant/subtype là thay đổi cần thông báo

Nếu API được dùng bởi nhiều consumer độc lập, thêm enum constant hoặc permitted subtype có thể yêu cầu consumer cập nhật logic. Hãy ghi rõ trong release note:

- Constant hoặc subtype mới là gì.
- Khi nào giá trị mới có thể xuất hiện.
- Consumer cũ sẽ gặp hành vi nào nếu nhận giá trị đó.
- Có fallback được khuyến nghị hay không.
- Có cần tăng major version theo chính sách compatibility của sản phẩm không.

Không nên chỉ nói “thêm một trạng thái mới” nếu nó có thể khiến switch expression cũ ném ICCE hoặc switch statement bỏ qua nghiệp vụ.

### 8.2. Dùng major version khi hợp đồng thực sự thay đổi

Không phải mọi enum addition đều bắt buộc tăng major version theo mọi chính sách versioning. Quyết định phụ thuộc vào cam kết của API và khả năng xử lý unknown value.

Tuy nhiên, nếu consumer được kỳ vọng phải hiểu mọi constant/subtype và không có fallback an toàn, việc mở rộng tập giá trị là thay đổi có thể phá vỡ source hoặc behavior compatibility. Cần xem xét major version hoặc một giai đoạn chuyển tiếp có thông báo trước.

### 8.3. Tạo extension point thay vì liên tục sửa sealed parent

Nếu một API cần cho phép plugin hoặc bên thứ ba mở rộng, hãy thiết kế nhánh non-sealed rõ ràng. Khi đó consumer có thể xử lý built-in variants riêng và gom mọi implementation bên ngoài vào một nhánh chung.

Nếu domain cần giá trị từ hệ thống bên ngoài thay đổi độc lập, hãy cân nhắc dùng string code hoặc wrapper có raw value thay cho enum đóng. Sealed hierarchy phù hợp với tập biến thể do API kiểm soát; open value model phù hợp với protocol có thể xuất hiện giá trị mới.

### 8.4. Không dùng default để che giấu sai lệch nghiệp vụ

Default branch có thể giúp binary cũ tiếp tục chạy, nhưng nó cũng có thể che mất trạng thái chưa được xử lý. Hãy xác định rõ:

- Có được phép tiếp tục xử lý không?
- Có cần fail request hoặc reject event không?
- Có cần lưu raw value để replay sau này không?
- Có cần metric để phát hiện tần suất giá trị chưa biết không?
- Ai sẽ cập nhật consumer khi giá trị mới xuất hiện?

Một fallback tốt có hành vi an toàn, có log/metric và có hướng khôi phục. Một fallback rỗng chỉ biến lỗi rõ ràng thành dữ liệu sai khó truy tìm.

## 9. Kịch bản triển khai nâng cấp API an toàn

### Trường hợp A: Enum nội bộ trong một ứng dụng

Nếu enum chỉ dùng trong một module và mọi consumer được build cùng lúc:

1. Thêm constant mới.
2. Biên dịch toàn bộ module.
3. Sửa các switch expression theo lỗi compiler.
4. Kiểm tra switch statement có side effect.
5. Chạy test serialization và database mapping.
6. Phát hành đồng bộ application artifact.

Vì tất cả consumer được build cùng nhau, compiler có thể giúp tìm nhiều điểm cần cập nhật.

### Trường hợp B: Enum trong thư viện dùng chung

Nếu thư viện phát hành độc lập:

1. Kiểm tra consumer đang dùng version nào.
2. Quyết định constant mới có thể xuất hiện ngay sau khi nâng provider hay không.
3. Nếu consumer cũ phải sống cùng provider mới, thêm fallback có chính sách rõ ràng hoặc duy trì contract không gửi giá trị mới đến consumer cũ.
4. Cập nhật release note và compatibility matrix.
5. Chạy thử binary cũ với provider mới.

Đây là trường hợp dễ gặp lỗi runtime nhất vì provider và consumer được phát hành độc lập.

### Trường hợp C: Sealed hierarchy cho plugin API

Nếu sealed hierarchy là một phần SPI:

1. Xác định nhánh nào do thư viện sở hữu và nhánh nào dành cho extension.
2. Giữ nhánh non-sealed nếu bên thứ ba cần triển khai thêm.
3. Tránh thêm permitted subtype làm consumer exhaustive switch cũ nhận instance mới mà không có fallback.
4. Nếu thêm subtype mới, cập nhật versioning và test consumer cũ.
5. Xác nhận plugin loader không từ chối implementation hợp lệ.

### Trường hợp D: Protocol hoặc event schema mở rộng

Nếu enum đại diện cho giá trị từ REST, Kafka, database hoặc message schema:

1. Định nghĩa stable code độc lập với tên enum.
2. Cho phép parser nhận diện giá trị chưa biết.
3. Giữ raw value nếu cần chuyển tiếp hoặc replay.
4. Chỉ chuyển thành enum known sau khi xác thực.
5. Kiểm thử consumer cũ khi producer gửi giá trị mới.

Không nên phụ thuộc vào ordinal hoặc tên constant Java như một protocol contract nếu hệ thống cần tiến hóa độc lập.

## 10. Checklist rà soát enum và sealed switch trong migration

### API và mô hình domain

- [ ] Đã liệt kê enum public có thể được mở rộng.
- [ ] Đã liệt kê sealed class/interface và toàn bộ permitted subtype.
- [ ] Đã xác định nhánh nào là final, sealed hoặc non-sealed.
- [ ] Đã xác định API nào được cam kết đóng và API nào có thể mở rộng.
- [ ] Đã ghi rõ chính sách khi nhận constant hoặc subtype chưa biết.

### Switch và logic nghiệp vụ

- [ ] Đã tìm switch expression và switch statement trên enum.
- [ ] Đã tìm pattern switch trên sealed hierarchy.
- [ ] Đã phân loại switch có default và không có default.
- [ ] Đã kiểm tra guarded pattern và pattern dominance.
- [ ] Đã xác định null policy.
- [ ] Đã thay fallback rỗng bằng hành vi có chủ đích ở các nhánh quan trọng.

### Dữ liệu và tích hợp

- [ ] Không dùng enum ordinal làm mã lưu trữ hoặc protocol.
- [ ] Đã kiểm tra JPA mapping, JSON, message broker và serialization.
- [ ] Đã có stable code nếu tên enum có thể thay đổi.
- [ ] Đã xác định cách giữ hoặc từ chối unknown raw value.
- [ ] Đã kiểm thử producer/consumer lệch phiên bản.

### Kiểm thử và phát hành

- [ ] Đã compile consumer với phiên bản API mới.
- [ ] Đã chạy binary consumer cũ với API mới trong môi trường kiểm thử.
- [ ] Đã kiểm tra switch expression khi gặp enum constant mới.
- [ ] Đã kiểm tra switch statement khi gặp enum constant hoặc subtype mới.
- [ ] Đã kiểm tra sealed hierarchy mở rộng và nhánh non-sealed.
- [ ] Release note nêu rõ tác động đến source, binary và behavior compatibility.
- [ ] Có kế hoạch rollback và xử lý dữ liệu đã được ghi bằng giá trị mới.

## Kết luận

Enum và sealed type giúp compiler kiểm tra tính đầy đủ của switch, nhưng exhaustiveness chỉ dựa trên tập giá trị và kiểu con mà compiler biết tại thời điểm biên dịch. Khi API được mở rộng, consumer biên dịch lại có thể nhận lỗi compile hữu ích; binary cũ có thể ném IncompatibleClassChangeError trong switch expression hoặc bỏ qua nhánh mới trong switch statement.

Khi migration và phát hành API, hãy phân biệt source compatibility, binary compatibility và behavior compatibility. Chọn enum cho tập giá trị được kiểm soát, sealed hierarchy cho tập biến thể có chủ đích, và thiết kế non-sealed branch hoặc raw-value wrapper khi cần mở rộng. Cuối cùng, kiểm thử cả consumer cũ lẫn consumer mới với provider mới, đồng thời quy định rõ fallback, logging và versioning. Nhờ vậy, việc mở rộng API không âm thầm làm sai workflow của ứng dụng đang chạy.

