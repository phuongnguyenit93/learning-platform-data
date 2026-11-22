# Ghi log pattern đã chọn — Case study command (Java 21)

## 1. Vấn đề: biết chính xác nhánh nào đã xử lý command

Trong một hệ thống nhận lệnh (*command*), dữ liệu đầu vào thường được mô hình hóa bằng một **sealed hierarchy**: tạo đơn hàng, hủy đơn hàng, hoàn tiền, v.v. Java 21 cho phép dùng **pattern matching cho `switch`** và **record patterns** để phân loại mỗi command, lấy các component và áp dụng guard `when`.

Nhưng khi một request chạy qua `switch`, người vận hành có thể cần trả lời:

- Request này **đã chọn case nào**?
- Guard nào khiến `CreateOrder` vào nhánh **bulk** chứ không phải nhánh thông thường?
- Command bị từ chối bởi quy tắc nào?
- Có phải một command **đã được chọn để xử lý**, hay nghiệp vụ **thật sự thực hiện thành công**?
- Có thể truy vết bằng `traceId` mà **không ghi lộ access token, tài khoản ngân hàng hoặc nội dung riêng tư** không?

Nếu chỉ log `command.getClass().getSimpleName()`, ta sẽ biết subtype ngoài cùng nhưng **không biết nhánh có guard** được chọn. Nếu log toàn bộ `command` qua `toString()` của record, ta có nguy cơ tiết lộ các component nhạy cảm. Nếu chạy một `switch` thứ hai chỉ để “tìm lại nhánh”, ta có thể đánh giá lại guard, tạo chênh lệch kết quả hoặc side effect.

**Giải pháp trung tâm của bài:** Dùng một `switch expression` **chọn nhánh một lần**, trả về một `Decision` chứa **mã nhánh ổn định**, rồi ghi **một audit event** từ chính `Decision` đó. Tách rõ “pattern đã chọn” khỏi “tác vụ đã commit thành công”.

**Phiên bản:** Ví dụ dùng **Java 21**, nơi record patterns (JEP 440) và pattern matching cho `switch` (JEP 441) đã là tính năng chính thức. Không cần `--enable-preview`. Toàn bộ ví dụ chạy bằng Java SE; không cần thư viện logging bên ngoài cho phần demo.

Sau bài học, bạn có thể:
1. Thiết kế tên nhánh (*branch identifier*) phản ánh case thực sự được chọn.
2. Ghi log sau selection mà không lặp lại phép matching hoặc guard.
3. Phân biệt **selected**, **accepted/rejected** và **business execution succeeded/failed**.
4. Xử lý null, dominance, exhaustiveness và exception path đúng cách.
5. Tránh rò rỉ dữ liệu nhạy cảm và log injection.
6. Viết test để kiểm chứng cả **hành vi xử lý** lẫn **audit event**.

## 2. Domain model: một hierarchy command có nhiều nhánh logic

Giả sử hệ thống hỗ trợ ba loại lệnh:

```text
Command (sealed interface)
├── CreateOrder(orderId, quantity, accessToken)
├── CancelOrder(orderId, urgent, privateReason)
└── RefundOrder(orderId, cents, bankAccount)
```

Ba subtype là các record:

```java
// Đoạn minh họa; khai báo đầy đủ có trong chương trình phần 6.
sealed interface Command permits CreateOrder, CancelOrder, RefundOrder {}

record CreateOrder(String orderId, int quantity, String accessToken)
        implements Command {}

record CancelOrder(String orderId, boolean urgent, String privateReason)
        implements Command {}

record RefundOrder(String orderId, int cents, String bankAccount)
        implements Command {}
```

Trong ví dụ này:
- `quantity <= 0` làm `CreateOrder` bị từ chối.
- `quantity >= 10` là `CreateOrder` loại bulk.
- Những `CreateOrder` hợp lệ còn lại là standard.
- `CancelOrder.urgent == true` là nhánh hủy khẩn cấp.
- `RefundOrder.cents <= 0` bị từ chối; giá trị dương được chấp nhận để xử lý tiếp.
- Selector null được ghi nhận là `NO_COMMAND`.

**Giá trị `ACCEPTED` trong bài chỉ mô tả kết quả phân loại/chấp nhận ở tầng command decision. Nó không có nghĩa đơn hàng đã được tạo, tiền đã hoàn, transaction đã commit hoặc hệ thống bên ngoài đã phản hồi thành công.** Phần 10 bàn về log execution thực sự.

### Tại sao subtype không đủ để làm log label?

Hai lệnh này cùng kiểu `CreateOrder`:

```java
new CreateOrder("O1", 2, "token-secret-1");
new CreateOrder("O2", 10, "token-secret-2");
```

Nhưng chúng phải chọn **hai nhánh khác nhau**: `CREATE_STANDARD` và `CREATE_BULK`. Tên class `CreateOrder` không diễn tả điểm khác biệt đó.

Tương tự, một `RefundOrder` có `cents == 0` và một `RefundOrder` có `cents > 0` cần kết quả từ chối/chấp nhận khác nhau. Vì vậy **branch identifier** phải được gắn với nhánh cụ thể **sau khi guard được đánh giá**, chứ không chỉ với runtime class.

## 3. Pattern đã chọn là một sự kiện riêng

Tách các khái niệm giúp tránh log gây hiểu nhầm:

| Khái niệm | Ví dụ | Điều đã chắc chắn |
| --- | --- | --- |
| Command received | `type=CreateOrder` | Hệ thống đã nhận dữ liệu đầu vào |
| Pattern selected | `branch=CREATE_BULK` | Pattern và guard tương ứng đã được chọn |
| Decision outcome | `outcome=ACCEPTED` | Tầng decision đã đồng ý cho xử lý tiếp |
| Execution started | `operation=create-order` | Đã bắt đầu workflow có side effect |
| Execution succeeded | `status=SUCCEEDED` | Thao tác/transaction đã đạt tiêu chí thành công được định nghĩa |
| Execution failed | `status=FAILED` | Thao tác không đạt tiêu chí thành công, có failure reason thích hợp |

Nếu một request được gắn nhãn `CREATE_BULK` rồi repository ném lỗi trước khi commit, log `branch=CREATE_BULK` vẫn **đúng**, nhưng log `order.created=true` sẽ **sai**. Đừng biến mọi thông điệp sau `switch` thành “command xử lý thành công”.

Trong bài, ta chọn dùng một `Decision` đơn giản:

```java
enum Branch {
    CREATE_REJECTED, CREATE_BULK, CREATE_STANDARD,
    CANCEL_URGENT, CANCEL_STANDARD,
    REFUND_REJECTED, REFUND_APPROVED, NO_COMMAND
}

record Decision(Branch branch, String outcome) {}
```

`Branch` là **mã nội bộ có danh sách giá trị hữu hạn**, không chứa token, số tài khoản hay dữ liệu không tin cậy. `outcome` trong demo là `"ACCEPTED"` hoặc `"REJECTED"`. Với hệ thống lớn, có thể thay `String outcome` bằng một `enum Outcome` để hạn chế nhập sai.

Một audit event có thể chứa:

```java
record AuditEvent(String traceId, Branch branch, String outcome) {}
```

**`traceId`** trong demo là mã truy vết đã được hệ thống cấp, ví dụ `T01`. Ở production, phải kiểm soát nguồn, định dạng và độ dài trace/correlation ID: không tự đưa nguyên văn chuỗi tùy ý từ HTTP header vào text log mà không kiểm tra, vì có thể dẫn đến chèn xuống dòng và giả mạo bản ghi (*log injection*).

## 4. Cấu trúc lựa chọn nhánh đúng trong Java 21

Điểm cốt lõi là **mọi case trả cùng một kiểu kết quả** — `Decision`:

```java
// Đoạn minh họa trong một method nhận Command command:
return switch (command) {
    case CreateOrder(String id, int quantity, String token)
            when quantity <= 0 ->
        new Decision(Branch.CREATE_REJECTED, "REJECTED");

    case CreateOrder(String id, int quantity, String token)
            when isBulk(quantity) ->
        new Decision(Branch.CREATE_BULK, "ACCEPTED");

    case CreateOrder(String id, int quantity, String token) ->
        new Decision(Branch.CREATE_STANDARD, "ACCEPTED");

    case CancelOrder(String id, boolean urgent, String reason)
            when urgent ->
        new Decision(Branch.CANCEL_URGENT, "ACCEPTED");

    case CancelOrder(String id, boolean urgent, String reason) ->
        new Decision(Branch.CANCEL_STANDARD, "ACCEPTED");

    case RefundOrder(String id, int cents, String account)
            when cents <= 0 ->
        new Decision(Branch.REFUND_REJECTED, "REJECTED");

    case RefundOrder(String id, int cents, String account) ->
        new Decision(Branch.REFUND_APPROVED, "ACCEPTED");

    case null ->
        new Decision(Branch.NO_COMMAND, "REJECTED");
};
```

Ở đây:
- Mỗi **record pattern** giải cấu trúc record và ràng buộc biến ở đúng vị trí component.
- Guard `when` chỉ được đánh giá sau khi record pattern khớp.
- Nếu guard trả `false`, các case sau còn được xét.
- Case có guard đứng **trước** case cùng subtype không guard, tránh bị dominated.
- `case null` nhận chính selector null; nó không phải fallback chung cho ba kiểu command.
- `Command` là sealed và ba direct permitted subtype đều là record (final), nên các case không guard bao phủ từng subtype giúp `switch expression` exhaustive mà không cần `default`.

**Quan trọng về logging:** Mỗi nhánh **trả về branch ID**. Không có bước thứ hai suy đoán branch từ class hay kiểm tra lại `quantity`/`urgent`. Một guard có thể phụ thuộc vào dữ liệu thay đổi, thời điểm hoặc side effect; đánh giá lại không phải cách đáng tin để tái dựng nhánh đã chọn.

### Guard là điều kiện chọn case, không phải nơi tự ý log

Một cách viết không nên lạm dụng:

```java
// Anti-pattern minh họa:
case CreateOrder(String id, int q, String token)
    when logAndCheckBulk(q) -> ...;
```

Nếu `logAndCheckBulk` vừa log vừa quyết định điều kiện:
- Log có thể được phát **trước khi biết có chọn case hay không**.
- Khi guard trả false, một bản ghi như “selected CREATE_BULK” là không đúng.
- Nếu guard ném exception, quá trình chọn case kết thúc bất thường; case dự phòng không được coi là đã chọn.
- Test và đo hiệu năng khó tách phần kiểm tra nghiệp vụ khỏi side effect audit.

**Khuyến nghị:** Giữ guard thuần và dễ hiểu; tạo audit event sau khi nhận được `Decision`. Nếu cần metric về *guard evaluated*, đó là một loại instrumentation khác, không được gọi nhầm là *branch selected*.

## 5. Ba cách đặt logging: điểm mạnh và rủi ro

### Cách A — Ghi log trực tiếp trong mỗi case

Ví dụ:

```java
// Đoạn minh họa, không phải switch expression hoàn chỉnh:
case CreateOrder(String id, int quantity, String token) -> {
    audit.record(...); // log ngay trong case
    yield new Decision(Branch.CREATE_STANDARD, "ACCEPTED");
}
```

Ưu điểm: Vị trí log gần branch được chọn. Tuy nhiên, nếu nhiều case có body dài, dễ lặp boilerplate, bỏ sót một case, hoặc viết log với tên branch không khớp nhánh. Khi refactor, code business và audit bị đan xen.

Nếu nghiệp vụ cần **ghi nhận sự kiện đúng tại thời điểm vào nhánh** trước khi có side effect, có thể cân nhắc cách này, nhưng cần contract rõ và test từng case. Không xem cách này sai tuyệt đối.

### Cách B — Tạo Decision ở switch, ghi log một lần sau đó

```java
// Mẫu chung:
Decision decision = select(command);
sink.record(new AuditEvent(traceId,
    decision.branch(), decision.outcome()));
return decision;
```

Ưu điểm:
- Chính `Decision` là nguồn sự thật về branch đã chọn.
- Một nơi ghi log, tránh bỏ sót case khi thêm subtype.
- Dễ kiểm tra **mỗi call thành công có một event**.
- Không chạy lại guard; có thể dùng chính `Decision` cho handler bước tiếp theo.
- Logging có thể tách khỏi các rule chọn nhánh.

Đây là mẫu **được dùng trong chương trình chạy được** của bài.

### Cách C — Ghi log ở lớp điều phối/observability adapter

Một application service có thể gọi `select(command)`, rồi gửi event tới `AuditSink`, logger hoặc tracing span. Cách này giữ domain decision tương đối thuần; hạ tầng logging được đóng gói trong adapter.

Đặc biệt hữu ích khi cần:
- Structured JSON logs.
- Correlation với request/trace/span.
- Chính sách lọc/masking dữ liệu.
- Logging mức độ INFO/WARN/ERROR theo outcome.
- Kiểm soát sampling, retention và quyền truy cập log.

**Điều kiện:** API tầng selection phải trả đủ metadata để adapter biết **branch thực sự đã chọn**. Nếu adapter chỉ nhận lại `Command` rồi tự pattern-match lần nữa, ta đã quay về rủi ro của việc đánh giá lại logic.

## 6. Chương trình Java 21 hoàn chỉnh: 8 branch events, không lộ bí mật

Tạo file **`CommandPatternAuditDemo.java`**. Mã chỉ dùng Java SE và ghi audit ra stdout theo định dạng cố định để **kiểm thử kết quả chính xác**. `MemoryAuditSink` là test double, không phải hệ thống lưu log production có độ bền/transaction.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class CommandPatternAuditDemo {
    sealed interface Command
            permits CreateOrder, CancelOrder, RefundOrder {}

    record CreateOrder(String orderId, int quantity, String accessToken)
            implements Command {}

    record CancelOrder(String orderId, boolean urgent,
                       String privateReason)
            implements Command {}

    record RefundOrder(String orderId, int cents, String bankAccount)
            implements Command {}

    enum Branch {
        CREATE_REJECTED, CREATE_BULK, CREATE_STANDARD,
        CANCEL_URGENT, CANCEL_STANDARD,
        REFUND_REJECTED, REFUND_APPROVED, NO_COMMAND
    }

    record Decision(Branch branch, String outcome) {}

    record AuditEvent(String traceId, Branch branch, String outcome) {}

    interface AuditSink {
        void record(AuditEvent event);
    }

    static final class MemoryAuditSink implements AuditSink {
        final List<AuditEvent> events = new ArrayList<>();

        @Override
        public void record(AuditEvent event) {
            events.add(event);
            System.out.printf("AUDIT trace=%s branch=%s outcome=%s%n",
                    event.traceId(), event.branch(), event.outcome());
        }
    }

    static int bulkGuardCalls;

    static boolean isBulk(int quantity) {
        bulkGuardCalls++;
        return quantity >= 10;
    }

    static Decision select(Command command) {
        return switch (command) {
            case CreateOrder(String id, int quantity, String token)
                    when quantity <= 0 ->
                new Decision(Branch.CREATE_REJECTED, "REJECTED");

            case CreateOrder(String id, int quantity, String token)
                    when isBulk(quantity) ->
                new Decision(Branch.CREATE_BULK, "ACCEPTED");

            case CreateOrder(String id, int quantity, String token) ->
                new Decision(Branch.CREATE_STANDARD, "ACCEPTED");

            case CancelOrder(String id, boolean urgent, String reason)
                    when urgent ->
                new Decision(Branch.CANCEL_URGENT, "ACCEPTED");

            case CancelOrder(String id, boolean urgent, String reason) ->
                new Decision(Branch.CANCEL_STANDARD, "ACCEPTED");

            case RefundOrder(String id, int cents, String account)
                    when cents <= 0 ->
                new Decision(Branch.REFUND_REJECTED, "REJECTED");

            case RefundOrder(String id, int cents, String account) ->
                new Decision(Branch.REFUND_APPROVED, "ACCEPTED");

            case null ->
                new Decision(Branch.NO_COMMAND, "REJECTED");
        };
    }

    static Decision handle(Command command, String traceId, AuditSink sink) {
        Objects.requireNonNull(traceId, "traceId");
        Objects.requireNonNull(sink, "sink");

        Decision decision = select(command);
        sink.record(new AuditEvent(
            traceId, decision.branch(), decision.outcome()));
        return decision;
    }

    static void verify(
            MemoryAuditSink sink, String traceId, Command command,
            Branch expectedBranch, String expectedOutcome,
            int expectedGuards) {
        int beforeEvents = sink.events.size();
        int beforeGuards = bulkGuardCalls;
        Decision decision = handle(command, traceId, sink);

        if (decision.branch() != expectedBranch ||
                !decision.outcome().equals(expectedOutcome)) {
            throw new AssertionError(
                "Wrong decision for " + traceId);
        }
        if (sink.events.size() != beforeEvents + 1) {
            throw new AssertionError(
                "Must emit exactly one audit event");
        }

        AuditEvent recorded = sink.events.get(beforeEvents);
        if (!recorded.traceId().equals(traceId) ||
                recorded.branch() != expectedBranch ||
                !recorded.outcome().equals(expectedOutcome)) {
            throw new AssertionError(
                "Audit does not match selected branch");
        }
        if (bulkGuardCalls - beforeGuards != expectedGuards) {
            throw new AssertionError(
                "Guard evaluated wrong number of times");
        }
    }

    public static void main(String[] args) {
        MemoryAuditSink sink = new MemoryAuditSink();

        verify(sink, "T01",
            new CreateOrder("O1", 2, "token-secret-1"),
            Branch.CREATE_STANDARD, "ACCEPTED", 1);
        verify(sink, "T02",
            new CreateOrder("O2", 10, "token-secret-2"),
            Branch.CREATE_BULK, "ACCEPTED", 1);
        verify(sink, "T03",
            new CreateOrder("O3", 0, "token-secret-3"),
            Branch.CREATE_REJECTED, "REJECTED", 0);

        verify(sink, "T04",
            new CancelOrder("O4", true, "cancel-confidential"),
            Branch.CANCEL_URGENT, "ACCEPTED", 0);
        verify(sink, "T05",
            new CancelOrder("O5", false, "cancel-confidential"),
            Branch.CANCEL_STANDARD, "ACCEPTED", 0);

        verify(sink, "T06",
            new RefundOrder("O6", 500, "account-777"),
            Branch.REFUND_APPROVED, "ACCEPTED", 0);
        verify(sink, "T07",
            new RefundOrder("O7", 0, "account-888"),
            Branch.REFUND_REJECTED, "REJECTED", 0);

        verify(sink, "T08", null,
            Branch.NO_COMMAND, "REJECTED", 0);

        String recorded = sink.events.toString();
        if (recorded.contains("token-secret") ||
                recorded.contains("cancel-confidential") ||
                recorded.contains("account-")) {
            throw new AssertionError(
                "Sensitive data leaked to audit");
        }

        System.out.println("EVENTS=" + sink.events.size());
        System.out.println("BULK_GUARD_CALLS=" + bulkGuardCalls);
        System.out.println("SECRETS_PRESENT=false");
    }
}
```

Biên dịch và chạy trên **JDK 21 trở lên**:

```bash
javac --release 21 CommandPatternAuditDemo.java
java CommandPatternAuditDemo
```

**Stdout chính xác:**

```text
AUDIT trace=T01 branch=CREATE_STANDARD outcome=ACCEPTED
AUDIT trace=T02 branch=CREATE_BULK outcome=ACCEPTED
AUDIT trace=T03 branch=CREATE_REJECTED outcome=REJECTED
AUDIT trace=T04 branch=CANCEL_URGENT outcome=ACCEPTED
AUDIT trace=T05 branch=CANCEL_STANDARD outcome=ACCEPTED
AUDIT trace=T06 branch=REFUND_APPROVED outcome=ACCEPTED
AUDIT trace=T07 branch=REFUND_REJECTED outcome=REJECTED
AUDIT trace=T08 branch=NO_COMMAND outcome=REJECTED
EVENTS=8
BULK_GUARD_CALLS=2
SECRETS_PRESENT=false
```

### Tại sao stdout ổn định?

Demo dùng `System.out.printf` với dữ liệu và thứ tự cố định, không tự thêm timestamp hay thread ID. Trong production, logger thường thêm timestamp, level, thread name, trace/span context và có thể ghi bất đồng bộ; khi đó không nên hứa **toàn bộ dòng log** giống chính xác mỗi lần.

Chương trình sử dụng một test double in-memory để chứng minh **event schema và đường chọn nhánh**, không thay cho dịch vụ lưu audit thực sự.

## 7. Phân tích từng test: branch ID chính là case đã chọn

| Request | Command | Case được chọn | Outcome |
| --- | --- | --- | --- |
| `T01` | `CreateOrder(quantity=2)` | `CREATE_STANDARD` | `ACCEPTED` |
| `T02` | `CreateOrder(quantity=10)` | `CREATE_BULK` | `ACCEPTED` |
| `T03` | `CreateOrder(quantity=0)` | `CREATE_REJECTED` | `REJECTED` |
| `T04` | `CancelOrder(urgent=true)` | `CANCEL_URGENT` | `ACCEPTED` |
| `T05` | `CancelOrder(urgent=false)` | `CANCEL_STANDARD` | `ACCEPTED` |
| `T06` | `RefundOrder(cents=500)` | `REFUND_APPROVED` | `ACCEPTED` |
| `T07` | `RefundOrder(cents=0)` | `REFUND_REJECTED` | `REJECTED` |
| `T08` | `null` | `NO_COMMAND` | `REJECTED` |

`verify` không chỉ so kết quả trả về. Nó còn đối chiếu:
1. **`Decision.branch`** bằng giá trị mong đợi.
2. **`Decision.outcome`** bằng giá trị mong đợi.
3. `sink.events.size()` chỉ tăng **một** sau mỗi lần `handle` hoàn tất bình thường.
4. **Bản ghi lưu** mang đúng `traceId`, branch và outcome.
5. Guard `isBulk` được gọi đúng số lần dự kiến trong **đường xử lý đơn luồng của bài**.

Vì các điều kiện này đều được kiểm bằng `AssertionError`, demo **không cần** bật `java -ea`.

### Guard được đánh giá bao nhiêu lần?

Trong ví dụ:
- `T01`: `quantity=2` không thỏa guard đầu `quantity <= 0`, rồi `isBulk(2)` chạy **một lần** và trả false; case standard được chọn.
- `T02`: `quantity=10` khiến `isBulk(10)` chạy **một lần** và trả true; case bulk được chọn.
- `T03`: `quantity=0` khớp case bị từ chối **ngay lập tức**; `isBulk` không được gọi.
- Các subtype `CancelOrder`, `RefundOrder` và selector null không cần chạy `isBulk`.

Tổng `BULK_GUARD_CALLS=2`. Bộ đếm ở đây **chỉ dành cho test**, bởi một biến `static int` mutable không bảo đảm thread safety nếu nhiều thread đồng thời xử lý command.

Từ đây rút ra hai điều:
- Không đặt audit bên trong `isBulk` rồi gọi đó là “đã chọn bulk”.
- Nếu cần metric số lần guard được kiểm tra, hãy tách metric đó khỏi **audit event của nhánh được chọn**.

### Vì sao log chỉ chứa traceId, branch và outcome?

Trong `CreateOrder` có `accessToken`, trong `CancelOrder` có `privateReason`, còn `RefundOrder` có `bankAccount`. Chúng được đưa vào command để cho thấy record pattern **có thể ràng buộc những dữ liệu nhạy cảm** nhưng **không nên mặc định log chúng**.

Phần test cố ý tìm các chuỗi đánh dấu nhạy cảm trong danh sách sự kiện audit và thất bại nếu có rò rỉ. Đây chỉ là một kiểm tra bằng ví dụ; production cần chính sách masking, allowlist, schema review và kiểm thử cho toàn bộ nguồn dữ liệu thực tế.

## 8. Anti-pattern: ghi log nguyên record hoặc chạy switch lần hai

### 8.1. Log `command.toString()` có thể rò rỉ dữ liệu

Một record mặc định có `toString()` hiển thị tên record và giá trị component. Với những record như:

```java
// Ví dụ cố ý không nên dùng cho audit:
System.out.println("command=" + command);
```

chuỗi kết quả có thể chứa `accessToken`, `bankAccount` hoặc lý do hủy riêng tư. Dù không in trực tiếp các trường đó trong `switch`, chúng vẫn có thể xuất hiện gián tiếp qua `toString()` hoặc một logger nhận object rồi tự format.

**Cách tốt hơn:** Dùng **allowlist** các field được phép ghi: `traceId` do hệ thống quản lý, `branch` từ enum, `outcome` từ enum/string hữu hạn, và metadata đã duyệt như duration hoặc error code. Không đưa object command nguyên vẹn vào log event.

### 8.2. Log tên class không đủ phân biệt nhánh có guard

`command.getClass().getSimpleName()` chỉ có thể nói đây là `CreateOrder`, chứ không thể nói branch là `CREATE_REJECTED`, `CREATE_BULK` hay `CREATE_STANDARD`. Nếu command null, `getClass()` còn ném `NullPointerException`.

**Cách tốt hơn:** Lấy `Decision.branch()` từ **chính switch đã chọn case**.

### 8.3. Chạy lại pattern matching chỉ để log

Đừng tạo một switch cho nghiệp vụ, rồi tạo switch thứ hai “tương đương” để quyết định nhãn log:

```java
// Anti-pattern ở mức thiết kế (chỉ minh họa):
Decision decision = select(command);
String branchForLog = selectAgain(command);
```

Nếu `selectAgain` có guard, nó có thể **đánh giá lại điều kiện**. Điều kiện có thể phụ thuộc đồng hồ, trạng thái bên ngoài, cấu hình vừa thay đổi hoặc side effect. Ngay cả khi hai switch giống nhau hôm nay, chúng có thể lệch khi một branch mới được thêm mà người viết quên cập nhật switch dùng để log.

**Cách tốt hơn:** Log `decision.branch()` sau `select`; không tái diễn selection.

### 8.4. Log trước khi guard trả true

Ví dụ:

```java
// Anti-pattern trong một guard:
case CreateOrder(String id, int quantity, String token)
        when traceBulkCandidate(quantity) -> ...
```

Nếu `traceBulkCandidate` ghi “CREATE_BULK selected” rồi trả false, sự kiện audit sai. Guard **được đánh giá** không đồng nghĩa case đó **được chọn**.

## 9. Exhaustiveness, dominance và null: ba quy tắc cần bảo vệ

### 9.1. Thêm subtype phải review branch log

Giả sử thêm:

```java
// Minh họa thay đổi model:
record RescheduleOrder(String orderId, String slot)
        implements Command {}
```

Cần cập nhật `permits RescheduleOrder` trong sealed interface. Với `select` đang liệt kê từng subtype nhưng không có `default`, compiler Java 21 có thể báo `switch expression` không exhaustive khi thiếu case mới.

Đây là **cơ chế nhắc cập nhật nhánh và event schema**:
- Chọn business behavior cho `RescheduleOrder`.
- Đặt một Branch ID riêng nếu có ý nghĩa.
- Thêm test khẳng định nhánh mới và audit event tương ứng.
- Review data classification để không log nhầm `slot` hoặc các field riêng tư.
- Cập nhật dashboard/metric/documentation theo schema mới.

Không tự thêm `default -> new Decision(OTHER, "ACCEPTED")` chỉ để làm build xanh nếu yêu cầu là phân loại từng command một cách tường minh.

### 9.2. Case có guard phải đứng trước case bao phủ toàn subtype

Ví dụ sai:

```java
// CỐ Ý SAI, đặt trong cùng một switch:
case CreateOrder(String id, int quantity, String token) ->
    new Decision(Branch.CREATE_STANDARD, "ACCEPTED");

case CreateOrder(String id, int quantity, String token)
        when quantity >= 10 ->
    new Decision(Branch.CREATE_BULK, "ACCEPTED");
```

Case không guard nhận toàn bộ `CreateOrder`; case bulk phía sau bị **dominated**. Compiler báo lỗi, nên không thể coi đó là hai case có thể lựa chọn như nhau.

Trong demo, các guard `quantity <= 0`, `isBulk(quantity)` đứng trước case `CreateOrder` không guard. Nhờ vậy, branch ID ghi trong log phản ánh đúng chính sách từ cụ thể đến tổng quát.

### 9.3. `case null` không giống `default`

`case null -> new Decision(Branch.NO_COMMAND, "REJECTED")` xử lý selector null theo contract minh họa. Trong pattern switch Java 21, `default` đơn thuần không có nghĩa selector null sẽ được nhận.

Một component record null cũng khác selector null. Ví dụ `new CreateOrder("O1", 2, null)` vẫn là một `CreateOrder` khác null và có thể khớp record pattern. Trong Java 21, type pattern unconditional tại vị trí component khai báo `String` có thể ràng buộc null; vì vậy không suy diễn component null tự làm record pattern fail.

**Domain design:** Trong production có thể cấm token null/blank ở constructor hoặc boundary; bài giữ dữ liệu đơn giản để minh họa audit không lộ token. Không hiểu nhầm việc “không ghi log token” với việc “không cần validate token”.

## 10. Ghi log pattern selection khác với ghi log kết quả thực thi

Một thực hành quan trọng của hệ thống command là tách **phase**:

```text
request received
   |
   v
select(Command) --> Decision(branch, outcome)
   |
   +--> audit: COMMAND_PATTERN_SELECTED
   |
   v
business handler / transaction / external service
   |
   +--> audit: COMMAND_EXECUTION_SUCCEEDED
   |                 hoặc
   +--> audit: COMMAND_EXECUTION_FAILED
```

Trong demo, `ACCEPTED` chỉ là phân loại đầu vào. Nếu muốn log kết quả thực thi, một application service có thể làm theo **mẫu minh họa**:

```java
// Pseudocode Java-style: các hàm execute(...) và audit... được
// cung cấp bởi application service/adapter, không chạy độc lập.
Decision decision = select(command);
auditSelection(traceId, decision.branch(), decision.outcome());

if ("REJECTED".equals(decision.outcome())) {
    return;
}

try {
    execute(command, decision);
    auditExecution(traceId, decision.branch(), "SUCCEEDED");
} catch (RuntimeException ex) {
    auditExecution(traceId, decision.branch(), "FAILED");
    throw ex;
}
```

Đây là **mẫu kiến trúc, không phải chương trình đã biên dịch**; tùy hệ thống thực, exception có thể được chuyển thành domain result hoặc được xử lý tại boundary khác. Điều quan trọng là:
- Event `PATTERN_SELECTED` ghi lại sự thật về case được chọn.
- Event `EXECUTION_SUCCEEDED` chỉ ghi khi đạt **định nghĩa success** của use case, không phải ngay khi guard đúng.
- Event `EXECUTION_FAILED` ghi khi thao tác thất bại, và exception gốc được bảo toàn theo chính sách lỗi.
- Cả ba có thể dùng cùng `traceId` nhưng **khác event type/phase**.

**Cảnh báo về atomicity:** Nếu transaction commit và log sink gửi sang hệ thống khác không nằm trong một giao dịch, event có thể được gửi nhưng transaction rollback hoặc ngược lại. Nếu nghiệp vụ đòi audit bền vững/đúng một lần ở mức lưu trữ, cần thiết kế transactional outbox, idempotency key, retry hoặc cơ chế audit transactional phù hợp. Một lần gọi `sink.record(...)` trong code **không** bảo đảm event chỉ được lưu đúng một lần trên hệ thống phân tán.

## 11. Exception path: khi nào không có pattern được chọn?

Không phải mọi lần gọi `select` đều trả về một `Decision`. Ví dụ:
- Biểu thức tạo selector ném lỗi **trước khi vào switch**.
- Record accessor do người dùng định nghĩa ném exception trong quá trình deconstruction (Java 21 có thể bọc thành `MatchException` kèm cause).
- Một guard `when` ném exception. Khi đó không xem guard “false” để thử case sau; exception lan truyền.
- Code trong case body ném exception trước khi `yield`/trả `Decision`.
- Khác biệt trong quá trình biên dịch và runtime hierarchy có thể dẫn đến `MatchException` ngoài dự kiến.

**Hệ quả:** Nếu `select(command)` chưa tạo ra `Decision`, không được ghi một branch ID cụ thể như thể branch đó đã được chọn. Hãy ghi một **event lỗi selection** riêng, ví dụ `COMMAND_SELECTION_FAILED` với error class/cause được lọc, thay vì bịa `CREATE_STANDARD` hoặc `OTHER`.

### Mẫu xử lý lỗi đúng tầng

```java
// Đoạn minh họa khi đã có AuditSink sink, traceId và Command command.
// Đây là policy về error events, không phải code dùng nguyên xi trong demo.
Decision decision;

try {
    decision = select(command);
} catch (RuntimeException ex) {
    // Ghi event loại SELECTION_FAILED ở boundary riêng;
    // KHÔNG gọi lại select() và KHÔNG coi lỗi là một case đã chọn.
    reportSelectionFailure(traceId, ex.getClass().getSimpleName());
    throw ex;
}

sink.record(new AuditEvent(
    traceId, decision.branch(), decision.outcome()));
```

Các helper `reportSelectionFailure` và đầu vào được cung cấp ở tầng application/observability; đoạn này chỉ minh họa luồng xử lý. Đừng đưa nguyên exception message/stack trace vào audit log nhạy cảm nếu chúng có thể chứa token, URL riêng tư hoặc dữ liệu cá nhân. Có thể gửi stack trace vào error log có quyền truy cập hạn chế theo chính sách riêng.

**Đừng để lỗi logging tự động biến thành “logic branch fail”:** Nếu sink ném exception khi phát event, đó là một lỗi hạ tầng audit, khác với lỗi selection. Cần có policy rõ: audit bắt buộc thì fail closed; telemetry best effort thì xử lý lỗi ở adapter và tiếp tục nghiệp vụ khi an toàn. Không dùng một `catch` quá rộng bao trùm cả `select`, `sink.record` và `execute` rồi tự gắn mọi lỗi thành “không match”.

## 12. Tổ chức structured logging trong production

Demo in ra dòng:

```text
AUDIT trace=T02 branch=CREATE_BULK outcome=ACCEPTED
```

Trong hệ thống thật, nên lưu dưới dạng **event có trường riêng**, chẳng hạn:

```json
{
  "event": "command.pattern_selected",
  "traceId": "T02",
  "branch": "CREATE_BULK",
  "outcome": "ACCEPTED"
}
```

Đây là JSON minh họa schema, không phải yêu cầu phụ thuộc một công nghệ logging cụ thể.

Một adapter logging có thể chuyển `AuditEvent` thành các trường của SLF4J/Logback, Log4j, java.util.logging, OpenTelemetry hoặc nền tảng quan sát của tổ chức. **Thư viện không tự làm log an toàn**; cần định nghĩa schema, field allowlist, sanitization và quyền truy cập.

### Những field nên và không nên ghi

| Trường | Có thể ghi? | Điều kiện |
| --- | --- | --- |
| `event`/`phase` | Có | Enum/tên sự kiện ổn định và nhất quán |
| `traceId` | Có | ID do hệ thống quản lý, chuẩn hóa và kiểm soát độ dài |
| `branch` | Có | Mã nhánh hữu hạn, không chứa payload |
| `outcome` | Có | Tập giá trị được định nghĩa rõ |
| `durationMs` | Có khi hữu ích | Đo bằng clock phù hợp, hiểu ý nghĩa từng phase |
| `commandType` | Có thể | Dùng nhãn tĩnh, không thay cho branch |
| `errorCode` | Có khi cần | Danh mục lỗi đã phân loại, không chứa PII |
| `accessToken`/mật khẩu/khóa API | **Không** | Dữ liệu bí mật phải bị loại khỏi audit/telemetry |
| Số tài khoản, thông tin thanh toán | Theo chính sách nghiêm ngặt | Mặc định tránh; masking/tokenization và kiểm soát quyền |
| `privateReason`/nội dung tự do | Thường không | Có thể chứa PII, nội dung nhạy cảm và ký tự injection |
| Toàn bộ `command.toString()` | Không mặc định | Record `toString` có thể in mọi component |

**Mẹo giảm rủi ro:** Thiết kế log schema theo **allowlist từ đầu**, không log mọi field rồi mới tìm cách xóa những trường nhạy cảm.

### Mã nhánh nên ổn định qua refactor

Nếu dùng `Branch.CREATE_BULK`, dashboard có thể query theo `branch="CREATE_BULK"`. Khi đổi tên class hoặc thêm record component, không nhất thiết phải đổi branch ID nếu ý nghĩa nghiệp vụ không đổi.

Khi thật sự đổi semantics, hãy coi việc đổi mã nhánh như một thay đổi **event schema**: cân nhắc versioning, cập nhật alert/dashboard, và hỗ trợ một khoảng chuyển tiếp nếu hệ thống downstream phụ thuộc.

### Cardinality và chi phí

`branch` từ enum có cardinality nhỏ, thích hợp cho metrics. Ngược lại, `orderId`, token, request payload hoặc `traceId` có cardinality lớn: đưa chúng thành metric labels có thể làm bùng nổ số time series. Tracing ID hữu ích cho log/trace nhưng không nên gắn mọi giá trị trace ID thành label của metric tổng hợp.

Nếu command traffic rất lớn, log mọi lần match có thể tạo chi phí I/O, CPU, lưu trữ và retention đáng kể. Cần phân biệt **audit bắt buộc** với **diagnostic logs có thể sampling**; sampling không phù hợp khi chính sách pháp lý/kiểm toán yêu cầu bản ghi đầy đủ.

## 13. Thread safety và correlation khi nhiều command xử lý đồng thời

Trong chương trình phần 6 có:

```java
static int bulkGuardCalls;
```

Đây là biến đếm **phục vụ bài test đơn luồng**, không phải thiết kế telemetry đồng thời. Khi nhiều thread chạy `select` cùng lúc, phép `++` không atomic; số đếm có thể sai.

Trong ứng dụng thật:
- Dùng metrics SDK hoặc counter thread-safe nếu muốn đếm guard/branch.
- Giữ `traceId` trong request context hoặc truyền tường minh theo call chain.
- Đừng dùng một biến `static String currentBranch` để nhớ branch của request hiện tại; request khác có thể ghi đè.
- Nếu dùng MDC/ThreadLocal, phải thiết lập và dọn context đúng lifecycle; các tác vụ async/virtual threads cần xem cơ chế truyền context được framework hỗ trợ.
- Audit event nên là object chứa đầy đủ metadata của request, rồi chuyển đến sink; đừng khôi phục branch bằng trạng thái global.

Đặc biệt với async processing, event `PATTERN_SELECTED` có thể xuất hiện trước event `EXECUTION_SUCCEEDED` rất lâu. Một request correlation ID giúp ghép chúng, nhưng không hứa thứ tự ghi nhận tuyệt đối nếu sink bất đồng bộ hoặc dữ liệu đến từ nhiều tiến trình.

## 14. Kiểm thử logging đúng cách

Bộ test nên xác nhận cả **business decision** lẫn **audit semantics**. Chỉ kiểm tra stdout có chứa từ `CreateOrder` là chưa đủ.

### 14.1. Ma trận test nhánh

| Case | Dữ liệu biên | Điều cần assert |
| --- | --- | --- |
| Create invalid | `quantity=0`, có thể thêm -1 | `CREATE_REJECTED`, `REJECTED`, không gọi bulk guard |
| Create standard | `quantity=1` hoặc 9 | `CREATE_STANDARD`, `ACCEPTED` |
| Create bulk | `quantity=10` hoặc 11 | `CREATE_BULK`, `ACCEPTED` |
| Cancel urgent | `urgent=true` | `CANCEL_URGENT` |
| Cancel normal | `urgent=false` | `CANCEL_STANDARD` |
| Refund invalid | `cents=0`, có thể thêm -1 | `REFUND_REJECTED` |
| Refund approved | `cents=1` hoặc 500 | `REFUND_APPROVED` |
| Null command | `command=null` | `NO_COMMAND`, `REJECTED` |

Với guard `quantity >= 10`, hai phía **9/10** là cặp kiểm thử quan trọng. Một test bulk với số 100 không tự phát hiện lỗi viết `> 10` thay vì `>= 10`.

### 14.2. Số event đúng cho một lần selection

Sau một lần `handle` bình thường trong demo, `events.size()` phải tăng **đúng một**. Test kiểm cả metadata của event mới, không chỉ đếm tổng.

Nhưng **“một event object được thêm vào in-memory list” không tương đương với exactly-once delivery** trong hệ thống bất đồng bộ/phân tán. Ở production cần thêm integration tests cho retry, duplicate, audit sink failure và khả năng lưu trữ.

### 14.3. Guard không bị đánh giá lại

`verify` so số lần gọi `isBulk` trước và sau `handle`:
- `CreateOrder` hợp lệ được kiểm tra bulk guard một lần.
- `CreateOrder` không hợp lệ bị xử lý bởi case từ chối trước, bulk guard không chạy.
- Các subtype khác không gọi bulk guard.

Nếu handler chạy lại `select` chỉ để logging, bộ đếm sẽ tăng nhiều hơn dự kiến và test bắt được sai lệch.

### 14.4. Không lộ secret

Dữ liệu test cố ý chứa `"token-secret-1"`, `"cancel-confidential"` và `"account-777"`. Test tìm dấu hiệu xuất hiện của những marker này trong sự kiện đã ghi. Nếu sau này ai đó thay `AuditEvent` bằng một trường `Command` hoặc log cả record, test có thể phát hiện rò rỉ.

Đối với production, cần thêm:
- Kiểm tra định dạng ID do client cung cấp (CR/LF, ký tự điều khiển).
- Kiểm thử với nội dung Unicode và payload dài.
- Kiểm quy tắc masking của các adapter logging.
- Kiểm quyền truy cập và thời gian lưu log.
- Kiểm tập field cho từng loại command, kể cả subtype mới.

### 14.5. Kiểm exception path

Cần thêm những test mà demo không mô phỏng trực tiếp:
- Guard ném exception → không phát một event `PATTERN_SELECTED` sai.
- Record accessor thất bại → lỗi được phân loại là selection failure, không được log là “nhánh đã chọn”.
- Sink ghi log ném lỗi → xử lý theo policy audit bắt buộc hay best effort, không tự chạy lại lệnh nghiệp vụ.
- Business execution thất bại sau selection → có event `EXECUTION_FAILED` thay vì `EXECUTION_SUCCEEDED`.
- Runtime nhận subtype mới sau thay đổi hierarchy → review exhaustive switches và xử lý lỗi build/deploy.

## 15. Các lỗi thường gặp trong code review

| Sai lầm | Rủi ro | Cách sửa |
| --- | --- | --- |
| Log `command.toString()` | Lộ toàn bộ record component, có thể có secret | Log schema allowlist với branch ID |
| Chỉ log class name | Không phân biệt các guard của cùng subtype | Trả `Branch` từ case thực sự chọn |
| Ghi “selected” trong guard | Guard false vẫn có log gây hiểu nhầm | Tách instrumentation guard và branch selected |
| Chạy switch thứ hai để lấy branch | Guard bị đánh giá lại, hai switch có thể lệch | Dùng `Decision.branch()` một lần |
| Log “success” ngay sau case selection | Nghiệp vụ chưa commit/hoàn thành | Tách event selection, execution success/failure |
| `default` rộng cho mọi command lạ | Subtype mới không được review đầy đủ | Giữ exhaustive sealed switch khi cần |
| Case không guard đứng trước guard cùng type | Guard case bị dominated | Case cụ thể trước, fallback sau |
| Quên xử lý selector null | Có thể ném NPE thay vì event mong muốn | `case null` hoặc validation tại boundary |
| Catch mọi exception thành “OTHER branch” | Che lỗi guard/accessor/handler | Phân biệt selection failure và real branch |
| Gắn `traceId` lên mọi metrics label | Cardinality cao | Dùng traceId cho log/trace, labels thấp cardinality |
| Coi một lần gọi sink là exactly-once | Retry/transport có thể tạo duplicate hoặc mất event | Idempotency, outbox, transaction policy |
| Sử dụng biến global lưu currentBranch | Race condition giữa request | Decision/event immutable và request context |
| Log exception message nguyên văn | Có thể lộ PII hoặc dữ liệu hệ thống | Error code/type đã lọc, quyền truy cập phù hợp |
| Ghi tất cả vào INFO với traffic lớn | Tốn CPU/I/O/storage | Tách audit bắt buộc và logs có thể sampling |

## 16. Quy trình triển khai case study command

Một workflow thực tế để đưa branch audit vào hệ thống command:

1. **Liệt kê command hierarchy:** Xác định các permitted subtype và các điều kiện `when` có ý nghĩa nghiệp vụ.
2. **Định nghĩa branch taxonomy:** Đặt mã nhánh có ý nghĩa ổn định như `CREATE_BULK` và `REFUND_REJECTED`; không dùng thông tin người dùng làm tên branch.
3. **Tạo result type:** `Decision(branch, outcome)` hoặc một domain result riêng có metadata audit, giữ nguyên kết quả nghiệp vụ cần trả về.
4. **Chọn branch đúng một lần:** Giữ `switch`/guard có semantics rõ; không chạy lại để logging.
5. **Gửi event sau selection:** Ghi branch từ `Decision` qua adapter; bảo đảm không đưa raw command vào schema.
6. **Tách execution outcome:** Nếu action có side effect, ghi một event riêng khi thành công/thất bại thật sự.
7. **Xử lý failure paths:** Phân loại lỗi selector, guard, accessor, sink và handler; không biến tất cả thành “case khác”.
8. **Kiểm thử subtype và guard:** Thêm boundary cases, null, audit event count và metadata correctness.
9. **Kiểm thử an toàn log:** Secret, CR/LF injection, high-cardinality fields, retention và access policy.
10. **Tích hợp observability:** Dùng trace/correlation ID được quản lý, event schema rõ và metrics labels phù hợp.
11. **Đánh giá reliability:** Nếu audit bắt buộc không được mất, thiết kế transactional/outbox và kiểm duplicate.
12. **Review khi mở rộng hierarchy:** Thêm subtype buộc cập nhật decision logic, branch ID, test và dashboard/schema downstream.

Điểm quan trọng là **mỗi audit event phải mô tả một sự kiện đã thật sự xảy ra**. “Pattern đã chọn” là dữ kiện ở tầng selection; “command đã hoàn tất” là dữ kiện ở tầng execution.

## 17. Bài tập thực hành

**Bài tập 1 — Ngưỡng bulk 9/10:** Thêm `CreateOrder("O9", 9, ...)` và `CreateOrder("O10", 10, ...)` vào các test. Kỳ vọng các branch `CREATE_STANDARD` và `CREATE_BULK`, đồng thời `isBulk` được gọi đúng một lần mỗi request.

**Bài tập 2 — Thêm command mới:** Tạo `record RescheduleOrder(String orderId, String slot) implements Command`, cập nhật `permits`. Quan sát `javac` báo non-exhaustive nếu `select` thiếu case. Thêm Branch ID `RESCHEDULE_STANDARD` và test audit event. Không thêm `default` chỉ để tránh xử lý subtype.

**Bài tập 3 — Chứng minh vì sao log class name không đủ:** Cho hai `CreateOrder` có quantity 2 và 10. In `getClass().getSimpleName()` ở một đoạn thử độc lập rồi so với `Decision.branch()`. Giải thích sự khác biệt.

**Bài tập 4 — Phân tách selection và execution:** Viết một `execute` minh họa ném exception khi gọi repository. Sau khi `Decision` trả `ACCEPTED`, log `PATTERN_SELECTED` rồi log `EXECUTION_FAILED` tại failure boundary. Đảm bảo không log nhầm `EXECUTION_SUCCEEDED`.

**Bài tập 5 — Guard thất bại bất thường:** Tạo guard `when` gọi method ném `IllegalArgumentException` trong một thử nghiệm riêng. Chứng minh không có branch ID thành công được tạo và case fallback không được thử như thể guard trả false. Thiết kế event `SELECTION_FAILED` để quan sát lỗi.

**Bài tập 6 — Ngăn lộ dữ liệu:** Cố ý sửa `MemoryAuditSink` để in cả `command.toString()` trong một nhánh thử nghiệm; quan sát test secret fail. Khôi phục logging theo allowlist. Thử payload chứa ký tự xuống dòng và xác định nơi cần normalize correlation ID.

**Bài tập 7 — Audit reliability:** Giả sử audit sink gửi event đến message broker nhưng broker không phản hồi sau timeout. Hãy thiết kế idempotency key và policy retry để tránh “một lần gọi method” bị hiểu sai thành “exactly once delivered”. Chỉ rõ khi nào cần outbox.

## 18. Kết luận

**Muốn ghi log pattern đã chọn, hãy để chính nhánh được chọn tạo metadata về branch.** Với Java 21, sealed command hierarchy và record patterns cho phép `switch` phân loại command rõ ràng. Guard `when` quyết định nhánh cụ thể; một `Decision` chứa `Branch` giúp tầng ngoài ghi audit **một lần** mà không chạy lại logic matching.

Đừng đồng nhất **pattern selected** với **business execution succeeded**, đừng log nguyên record chứa dữ liệu nhạy cảm và đừng tin rằng một lời gọi logging đồng nghĩa với exactly-once delivery. Thiết kế đáng tin cậy phải tách **selection, decision, execution và audit delivery**, có test về branch correctness, null, guard, secret leakage và failure paths.

## Tài liệu tham khảo

- Oracle Java SE 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- Oracle Java SE 21 — Record Patterns: https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
- Java Language Specification SE 21 — `14.11 switch Statements`: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11
- Java Language Specification SE 21 — `14.30 Patterns`: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30
- Java Language Specification SE 21 — `15.28 switch Expressions`: https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28
- Java SE 21 — java.util.logging: https://docs.oracle.com/en/java/javase/21/docs/api/java.logging/java/util/logging/package-summary.html
- OpenJDK JEP 440 — Record Patterns: https://openjdk.org/jeps/440
- OpenJDK JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
