# Dùng log thay cho control flow — anti-pattern trong Java Logging

## 1. Bản chất của anti-pattern

**Dùng log thay cho control flow** là lỗi thiết kế khi ứng dụng dựa vào một dòng log, mức log, khả năng ghi log hoặc việc đọc lại output log để **quyết định nhánh nghiệp vụ**. Trong ứng dụng Java, logging dùng để **quan sát** những gì chương trình đã quyết định hoặc thực hiện; nó không tự thay thế `if`, `return`, `throw`, validation, authorization, transaction hay state machine.

Ví dụ sai:

```java
// SAI: đã cảnh báo nhưng vẫn thực hiện side effect.
if (amount > balance) {
    logger.error("Insufficient funds");
}
debitAccount(amount);
```

`logger.error(...)` không làm method dừng, không tự rollback và không khiến caller nhận kết quả từ chối. Nếu không có guard khác, `debitAccount` vẫn chạy.

Ví dụ đúng về logic (snippet trong ứng dụng có các class được định nghĩa):

```java
if (amount > balance) {
    return TransferResult.rejected("INSUFFICIENT_FUNDS");
}

debitAccount(amount);
return TransferResult.succeeded();
```

Tầng điều phối có thể ghi log dựa trên `TransferResult`, nhưng việc **cho phép hay ngăn tác động** nằm ở decision logic, không ở logger. Nếu logging bị tắt hoàn toàn, quy tắc nghiệp vụ vẫn phải hoạt động đúng.

**Một phép thử tư duy hiệu quả:** đặt log level thành `OFF`, tháo appender hoặc giả lập collector không hoạt động. Nếu validation, phân quyền, commit, response, retry hay kết quả thao tác đổi theo, rất có thể ứng dụng phụ thuộc nhầm vào kênh log.

Bài học này tập trung vào các biểu hiện thực tế, cách sửa ở từng lớp, ví dụ Java 17 chạy độc lập và kiểm thử để đảm bảo logging không trở thành bộ điều khiển nghiệp vụ.

## 2. Logging có thể bị lọc, trễ, thất bại hoặc thay đổi cấu hình

Đường đi thông thường:

```text
Business code
    |
    v
SLF4J / Log4j2 / Logback / java.util.logging
    |
    v
Logger threshold / filter
    |
    v
Appender / encoder / Handler
    |
    +--> console / stdout
    +--> file
    +--> async memory queue -> worker
    +--> agent -> collector -> storage/index
```

Tại từng bước có thể có hiện tượng:

- `DEBUG` hoặc `INFO` bị chặn vì effective level quá cao.
- Filter trên logger/appender loại event dù code có gọi `logger.info(...)`.
- Appender bất đồng bộ mới nhận event vào RAM, worker chưa gửi tới sink.
- Buffer đầy khiến event bị drop hoặc thread ghi log bị block, tùy backend và cấu hình.
- File không ghi được vì hết disk, lỗi quyền hoặc rotation.
- Collector lỗi mạng, trả 429/5xx hoặc index chậm.
- Dashboard không hiện event do truy vấn, timezone, retention hoặc permission.

Do đó các suy luận sau **không hợp lệ**:

```text
Gọi logger.error(...) => nghiệp vụ tự thất bại.
Không thấy ERROR log => chắc chắn không có lỗi.
Thấy SUCCESS log => DB chắc chắn đã commit.
DEBUG đang bật => được phép thực hiện nghiệp vụ.
Collector đã nhận log => message broker chắc chắn ACK.
```

Một hệ thống đúng phải có **nguồn sự thật nghiệp vụ**: result/state trong domain, transaction status, durable message/event, hoặc trạng thái đã được đối soát. Log có thể giúp truy tìm nguồn sự thật ấy, nhưng không thay thế nó.

## 3. Các dấu hiệu đáng nghi trong code review

| Dấu hiệu trong Java | Lỗi cốt lõi | Rủi ro |
| --- | --- | --- |
| `if (invalid) logger.warn(...); save();` | Chỉ log thay vì dừng | Dữ liệu sai vẫn được lưu |
| `catch (Exception e) { logger.error(...); }` | Nuốt exception | Caller tưởng thành công |
| `if (logger.isDebugEnabled()) update();` | Level thành feature flag | Thay log config đổi nghiệp vụ |
| `if (logger.isErrorEnabled()) throw ...;` | Exception phụ thuộc logger | Behavior không ổn định |
| `logger.debug("saved={}", repository.save(x));` | Side effect nằm trong argument log | Mutation khó nhận diện, vẫn chạy khi DEBUG tắt |
| Phân tích regex stdout để phát lệnh thanh toán | Log text thành message bus | Trễ, mất, trùng, giả mạo |
| Log `SUCCEEDED` trước transaction commit | Quan sát báo sai mốc | Báo thành công dù rollback |
| Log `DENIED` nhưng vẫn trả dữ liệu | Log thay enforcement | Lỗ hổng authorization |
| Test chỉ `verify(logger).error(...)` | Chưa kiểm tra trạng thái | Bug nghiệp vụ lọt test |
| Quyết định retry vì không tìm thấy dòng log | Lệ thuộc ingest/index | Có thể thực hiện side effect lặp |

Không phải cứ log rồi ném exception là sai. Có những boundary chủ động log có kiểm soát rồi `throw` hoặc chuyển sang error response. Anti-pattern xảy ra khi **log bị coi là hành động xử lý chính**, hoặc code thiếu hành động quyết định tương ứng.

## 4. Trường hợp 1: ghi cảnh báo validation rồi tiếp tục xử lý

Ví dụ nhập số lượng:

```java
// SAI: không có return/throw.
if (quantity <= 0) {
    logger.warn("Invalid quantity {}", quantity);
}
orderRepository.save(new Order(quantity));
```

Một dòng WARN chỉ mô tả vi phạm, không ngăn lệnh `save`. Cách đúng là trả kết quả hoặc ném exception có kiểu:

```java
// Hướng Result:
if (quantity <= 0) {
    return PlaceOrderResult.rejected("INVALID_QUANTITY");
}

Order order = orderRepository.save(new Order(quantity));
return PlaceOrderResult.succeeded(order.id());
```

Hoặc:

```java
// Hướng exception:
if (quantity <= 0) {
    throw new InvalidOrderQuantityException(quantity);
}
```

Các đoạn là **mã minh họa**, cần những class và dependency ứng dụng tương ứng, không biên dịch độc lập. Chọn `Result` khi trường hợp từ chối là nhánh nghiệp vụ thường gặp; chọn typed exception khi contract muốn thoát đường thực thi và để boundary xử lý. Dù chọn cách nào, lệnh thay đổi trạng thái không được tiếp tục sau một guard thất bại.

### Không dùng message text để phân loại kết quả

Sai:

```java
// Không nên quyết định theo câu chữ tự do.
if (lastLogLine.contains("Invalid quantity")) {
    return badRequest();
}
```

Đúng: giữ `reasonCode=INVALID_QUANTITY` hoặc enum/typed error làm dữ liệu nghiệp vụ. Message có thể được bản địa hóa hay đổi cách diễn đạt mà không làm flow thay đổi.

## 5. Trường hợp 2: catch exception, log rồi nuốt

```java
// SAI: void method hoàn tất bình thường dù DB không lưu.
void updateProfile(Profile profile) {
    try {
        repository.save(profile);
    } catch (SQLException ex) {
        logger.error("Cannot update profile", ex);
    }
}
```

Caller không nhìn thấy exception. Một controller có thể trả HTTP 200, dù thao tác thất bại. Trong transaction, việc nuốt exception có thể khiến một số thay đổi khác được commit tùy transaction policy.

Nếu không thể phục hồi, hãy **propagate** lỗi với cause:

```java
void updateProfile(Profile profile) {
    try {
        repository.save(profile);
    } catch (SQLException ex) {
        throw new ProfileStorageException(
                "PROFILE_STORAGE_FAILURE", ex);
    }
}
```

Nếu có nhánh xử lý lỗi dự kiến, trả kết quả:

```java
UpdateResult updateProfile(Profile profile) {
    try {
        repository.save(profile);
        return UpdateResult.succeeded();
    } catch (KnownVersionConflictException ex) {
        return UpdateResult.conflict("VERSION_CONFLICT");
    }
}
```

Các ví dụ chỉ là snippet với class giả định. Không gán mọi exception thành business rejection: lỗi DB offline khác với conflict hợp lệ; timeout sau khi lệnh được gửi có thể để lại kết quả **UNKNOWN** chứ không chắc rollback.

### Log and rethrow ở mọi tầng cũng gây hại

```text
Repository -> log ERROR, throw
Service    -> log ERROR, throw
Controller -> log ERROR, map HTTP
```

Ba stack trace có thể biểu diễn **một lỗi duy nhất**. Để giảm nhiễu, nên chọn một boundary chịu trách nhiệm ghi exception và context đầy đủ; tầng dưới có thể bổ sung typed exception/cause. Event audit riêng có thể cần ghi thêm, nhưng phải tách event type và mục đích.

## 6. Trường hợp 3: dùng logger level làm feature flag

Sai:

```java
// SAI nghiêm trọng:
if (logger.isDebugEnabled()) {
    transferMoney(source, target, amount);
}
```

Khi đội vận hành đổi level từ INFO sang DEBUG để điều tra, code sẽ bắt đầu thực thi chuyển tiền. Khi DEBUG tắt, nghiệp vụ không chạy. Đây là sự phụ thuộc nguy hiểm giữa **quan sát** và **quyết định**.

Cần dùng policy riêng:

```java
if (!authorization.canTransfer(actor, source)) {
    return TransferResult.denied("NOT_AUTHORIZED");
}

if (!featurePolicy.isTransferEnabled(actor)) {
    return TransferResult.rejected("FEATURE_DISABLED");
}

TransferResult result =
        transferService.transfer(source, target, amount);

if (logger.isDebugEnabled()) {
    logger.debug(
        "transfer resultCode={}", result.reasonCode());
}

return result;
```

Đây là snippet ứng dụng, không phải class độc lập. `featurePolicy` cần có nguồn cấu hình/ủy quyền phù hợp; nó không phải một alias của log level. Guard `isDebugEnabled()` chỉ nên bao **việc tính toán thông tin chẩn đoán không có side effect bắt buộc**.

Một số đội dùng logger để quyết định sampling quan sát — điều đó hợp lý nếu sampling chỉ ảnh hưởng **telemetry**. Nhưng nếu nó ảnh hưởng retry, commit, quyền hoặc response, đó không còn là sampling đơn thuần.

## 7. Trường hợp 4: đặt side effect trong tham số logging

Java đánh giá các đối số trước khi gọi method. Vì vậy:

```java
logger.debug("stored entity={}", repository.save(entity));
```

**`repository.save(entity)` vẫn được gọi ngay cả khi DEBUG đang tắt**, vì nó phải được đánh giá để làm argument. Đây không phải lazy evaluation.

Ngược lại, đưa side effect vào phần chỉ chạy khi DEBUG bật cũng sai:

```java
// SAI nếu persist() là hoạt động nghiệp vụ bắt buộc.
if (logger.isDebugEnabled()) {
    logger.debug("saved={}", persist());
}
```

Cách đúng: tách mutation và logging:

```java
SavedEntity saved = repository.save(entity);
logger.debug("savedEntityId={}", saved.safeId());
```

Nếu tạo diagnostic summary tốn chi phí nhưng **thuần túy**, có thể bảo vệ bằng guard:

```java
if (logger.isDebugEnabled()) {
    logger.debug("diagnostic={}",
            computeSummaryWithoutSideEffects(saved));
}
```

Trong SLF4J 2.x có API fluent/lazy supplier, JUL có một số overload nhận `Supplier<String>`. Chúng giúp tránh tính toán **nội dung log** khi level bị tắt; không phải cơ chế để thực thi nghiệp vụ theo điều kiện log.

**Quy tắc review:** mọi biểu thức nằm trong argument/supplier của logger phải được xem như **quan sát không có side effect nghiệp vụ**. Nếu biểu thức gọi repository, RPC hoặc mutate state, hãy đưa nó ra ngoài.

## 8. Trường hợp 5: ghi success trước commit hoặc ACK

```java
// SAI: đã tuyên bố thành công trước khi commit.
logger.info("action=ROLE_CHANGE outcome=SUCCEEDED");
repository.updateRole(userId, role);
transaction.commit();
```

Nếu transaction rollback hoặc lỗi khi commit, bản ghi log mô tả sai sự kiện.

Quy trình khái niệm đúng:

```text
Request
   |
   v
Authorize + validate
   |
   +-- DENIED / REJECTED --> return outcome
   |
   v
Execute mutation
   |
   +-- rollback confirmed --> FAILED
   +-- commit ambiguous   --> UNKNOWN / reconciliation
   |
   v
COMMIT confirmed
   |
   v
SUCCEEDED (business outcome đã xác minh)
   |
   v
Observe result / durable audit protocol (tùy yêu cầu)
```

Tuy nhiên, **log sau commit không bảo đảm log được lưu**. Process có thể crash sau DB commit trước lời gọi logger. Nếu phải bảo đảm audit hoặc phát domain event, cần transaction outbox hoặc cơ chế event persistence có hợp đồng bền vững riêng (phần 16), không chỉ di chuyển `logger.info`.

Tương tự, một message consumer có thể ghi `"ACK_SENT"` nhưng mất kết nối trước khi broker ghi nhận ACK. Log `ACK_ATTEMPTED` là quan sát về việc thử, không tự chứng minh delivery thành công. Với Kafka, `commitAsync` được gọi không có nghĩa callback đã báo commit success.

## 9. Log level không phải business outcome

Severity và kết quả nghiệp vụ là hai trục độc lập:

| Business outcome | Mức log có thể dùng | Diễn giải |
| --- | --- | --- |
| `SUCCEEDED` | INFO hoặc audit store | Thao tác đạt mốc xác minh |
| `REJECTED` | INFO/DEBUG/audit | Quy tắc miền từ chối |
| `DENIED` | Security audit, INFO/WARN tùy policy | Authorization từ chối |
| `NO_CHANGE` | DEBUG/INFO | Request idempotent, không mutation |
| `FAILED` | ERROR nếu sự cố cần trực | Thất bại kỹ thuật đã xác nhận |
| `UNKNOWN` | WARN/ERROR theo tác động | Chưa biết side effect có xảy ra không |
| `PENDING` | INFO hoặc lifecycle event | Chưa có terminal result |

`logger.error` không tự trả HTTP 500. `logger.warn` không tự chuyển response thành 409. `logger.info` không tự đánh dấu transaction đã commit.

Khi dashboard dùng số dòng ERROR làm “số giao dịch thất bại”, có thể đếm sai: business rejection thường log INFO, exception sau commit có thể là ERROR nhưng nghiệp vụ đã thành công, một lỗi có thể tạo ba log nếu nhiều layer cùng log.

Để thống kê nghiệp vụ, đo từ **result/event có cấu trúc** và mốc commit/processing đã xác minh. Dùng log level như một tín hiệu vận hành, không phải mã trạng thái chính.

## 10. Thiết kế tốt: decision trước, observation sau

Một kiến trúc thuận chiều:

```text
HTTP / message / scheduled job
        |
        v
Authorization + validation
        |
        v
Domain / application service
        |
        +--> Result / typed exception / state transition
                      |
                      v
             Boundary/policy mapping
             HTTP response / ACK / NACK
             transaction / retry
                      |
                      v
               Logging, metric, tracing
               phản ánh quyết định thực tế
```

Các thành phần có vai trò khác nhau:

- **Command:** yêu cầu tạo side effect, chịu guard và policy.
- **Domain result:** kết quả `SUCCEEDED`, `REJECTED`, `DENIED`, `NO_CHANGE` hoặc trạng thái tương ứng.
- **Exception:** thông báo thất bại bất thường hoặc đường xử lý không thể tiếp tục theo contract.
- **State machine:** quản lý nhiều bước và trạng thái bất đồng bộ.
- **Domain event:** sự kiện nghiệp vụ có schema/ID/delivery riêng.
- **Operational log:** dấu vết quan sát có thể filter/sampling, không mặc định bền vững.
- **Audit event:** có thể đòi hỏi lưu trữ, integrity, retention và quyền truy cập riêng.

Một event `outcome=SUCCEEDED` nên được tạo **từ kết quả nghiệp vụ**, không phải parse câu “payment succeeded” trong message logger để suy ra kết quả.

### Một operation qua nhiều tầng

Tầng domain có thể trả `TransferResult`; application service quyết định transaction; HTTP boundary map kết quả sang response, đồng thời phát event logging; monitoring theo outcome/latency. Nhờ vậy thay Logback bằng Log4j2 hoặc thay text pattern bằng JSON không làm logic nghiệp vụ đổi.

## 11. Java 17 độc lập: INFO bị tắt nhưng nghiệp vụ vẫn chạy đúng

Chương trình sau mô phỏng hai tài khoản trong RAM, không cần thư viện ngoài:

1. Nguồn bắt đầu có 100 đơn vị, đích có 0.
2. Chuyển 150 bị từ chối vì không đủ số dư, event INFO được in.
3. Hạ log level để INFO bị lọc.
4. Chuyển 30 vẫn thành công; dù không có INFO event mới, số dư vẫn thay đổi đúng.

Code dùng JUL `java.util.logging` và Handler thử có output xác định, không phụ thuộc thời gian hoặc ConsoleHandler mặc định.

### 11.1. Tạo file `LogIsNotControlFlowDemo.java`

```java
import java.text.MessageFormat;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LogIsNotControlFlowDemo {
    enum Status { SUCCEEDED, REJECTED }

    record TransferResult(Status status, String reasonCode) {}

    static final class Accounts {
        private int sourceBalance = 100;
        private int targetBalance = 0;

        TransferResult transfer(int amount) {
            if (amount <= 0) {
                return new TransferResult(
                        Status.REJECTED, "INVALID_AMOUNT");
            }

            if (amount > sourceBalance) {
                return new TransferResult(
                        Status.REJECTED, "INSUFFICIENT_FUNDS");
            }

            // Side effect do business rule điều khiển,
            // không phụ thuộc logger có bật hay không.
            sourceBalance -= amount;
            targetBalance += amount;

            return new TransferResult(
                    Status.SUCCEEDED, "APPLIED");
        }

        int sourceBalance() { return sourceBalance; }
        int targetBalance() { return targetBalance; }
    }

    private static final Logger LOG =
            Logger.getLogger("example.controlflow.demo");

    private static void observe(TransferResult result) {
        // Quyết định đã có; logger chỉ quan sát.
        LOG.log(Level.INFO,
                "action=TRANSFER outcome={0} reasonCode={1}",
                new Object[] {
                    result.status(), result.reasonCode()
                });
    }

    public static void main(String[] args) {
        Level originalLevel = LOG.getLevel();
        boolean originalParentHandlers =
                LOG.getUseParentHandlers();

        AtomicInteger captured = new AtomicInteger();

        Handler sink = new Handler() {
            @Override
            public void publish(LogRecord event) {
                if (!isLoggable(event)) {
                    return;
                }

                captured.incrementAndGet();

                String rendered = MessageFormat.format(
                        event.getMessage(),
                        event.getParameters());

                System.out.println(
                        "LOG " + event.getLevel().getName()
                                + " " + rendered);
            }

            @Override
            public void flush() {}

            @Override
            public void close() {}
        };

        sink.setLevel(Level.ALL);
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);
        LOG.addHandler(sink);

        try {
            Accounts accounts = new Accounts();

            System.out.println(
                    "infoEnabledBefore="
                            + LOG.isLoggable(Level.INFO));

            TransferResult first = accounts.transfer(150);
            observe(first);

            System.out.println(
                    "first=" + first.status()
                            + " source=" + accounts.sourceBalance()
                            + " target=" + accounts.targetBalance());

            // Chỉ đổi chính sách logging.
            LOG.setLevel(Level.WARNING);

            System.out.println(
                    "infoEnabledAfter="
                            + LOG.isLoggable(Level.INFO));

            TransferResult second = accounts.transfer(30);
            observe(second); // INFO bị filter, transfer đã chạy.

            System.out.println(
                    "second=" + second.status()
                            + " source=" + accounts.sourceBalance()
                            + " target=" + accounts.targetBalance());

            System.out.println(
                    "capturedEvents=" + captured.get());
        } finally {
            LOG.removeHandler(sink);
            sink.close();
            LOG.setLevel(originalLevel);
            LOG.setUseParentHandlers(originalParentHandlers);
        }
    }
}
```

### 11.2. Biên dịch và chạy

Sử dụng JDK 17 trở lên:

```bash
javac LogIsNotControlFlowDemo.java
java LogIsNotControlFlowDemo
```

**Stdout chính xác** khi chạy riêng chương trình:

```text
infoEnabledBefore=true
LOG INFO action=TRANSFER outcome=REJECTED reasonCode=INSUFFICIENT_FUNDS
first=REJECTED source=100 target=0
infoEnabledAfter=false
second=SUCCEEDED source=70 target=30
capturedEvents=1
```

### 11.3. Vì sao output này quan trọng?

- Khi INFO đang bật, `TransferResult(REJECTED, INSUFFICIENT_FUNDS)` được xác định bởi điều kiện số dư. Logger chỉ in kết quả đó.
- Sau khi hạ logging xuống WARNING, `LOG.isLoggable(Level.INFO)` trả false. Lời gọi `observe(second)` vẫn diễn ra nhưng không có event INFO mới ở Handler.
- `Accounts.transfer(30)` không phụ thuộc logger, nên vẫn đưa số dư nguồn về 70 và đích lên 30.
- `capturedEvents=1` chỉ đếm **LogRecord tới Handler trong RAM**, không phải số business transaction hoặc bảo đảm collector đã lưu.
- JUL dùng placeholder kiểu `{0}`/`{1}` với `MessageFormat`; SLF4J dùng placeholder `{}`. Không trộn hai cú pháp.
- `finally` tháo Handler và khôi phục configured level/parent-handler flag, tránh để trạng thái test ảnh hưởng code khác.

**Giới hạn:** đây là mô phỏng một thread, dùng số nguyên, không có auth, ACID transaction, DB hay concurrency. Không sử dụng `Accounts` này cho chuyển tiền thật. Code đủ để hiểu **business control flow độc lập với sự tồn tại của log**, không chứng minh hệ thống logging bền vững hoặc chống duplicate.

## 12. Exception, Result và state machine: chọn công cụ thực thi control flow

### Result có kiểu cho nhánh dự kiến

Trong Java 17 có thể mô hình hóa kết quả:

```java
sealed interface CancelResult
        permits CancelResult.Cancelled,
                CancelResult.NoChange,
                CancelResult.Rejected {

    record Cancelled() implements CancelResult {}
    record NoChange() implements CancelResult {}
    record Rejected(String reasonCode)
            implements CancelResult {}
}
```

Đây là khai báo Java 17 hợp lệ trong ngữ cảnh file/type thích hợp. Nó thể hiện ba outcome có nghĩa khác nhau; logger không cần quyết định cái nào đã xảy ra.

### Exception có kiểu cho đường xử lý lỗi

```java
if (!policy.canCancel(actor, order)) {
    throw new AccessDeniedException("POLICY_DENIED");
}
```

Snippet phụ thuộc class ứng dụng. `throw` làm thay đổi control flow; `logger.warn` không làm điều đó. Handler phía ngoài có thể chuyển `AccessDeniedException` thành 403 hoặc audit `DENIED`.

### State machine cho tác vụ bất đồng bộ

Một job dài có thể đi qua `ACCEPTED -> RUNNING -> SUCCEEDED/FAILED/CANCELED`. Không suy `SUCCEEDED` chỉ vì thấy dòng log “worker started”. State nên nằm trong domain/job store, có transition rules và khả năng đối soát. Logger phát event quan sát **sau mỗi transition đã xác minh**.

Khi việc ghi log thất bại, state machine vẫn được kiểm soát bởi transaction/state store; nếu bản thân audit/event là bắt buộc, dùng protocol lưu có độ bền chứ không hy vọng log luôn tồn tại.

## 13. Anti-pattern: dùng console log làm message bus

Một tích hợp tạm thời đôi khi có dạng:

```text
Service A:
  logger.info("SEND_EMAIL orderId=O-42")
       |
       v
Log agent / collector
       |
       v
Regex parser
       |
       v
Service B gửi email
```

Đây là cách điều khiển công việc bằng text log, rất dễ hỏng:

- Đổi level/filter → “lệnh” mất.
- Đổi pattern, newline hoặc JSON encoder → parser không nhận dạng.
- Async queue/sink chậm → công việc trễ không có deadline xác định.
- Retry duplicate log → gửi email hai lần.
- Raw input chứa CR/LF → có thể giả dòng log.
- Retention/index/permission thay đổi → workflow bị ảnh hưởng khó đoán.
- Không có ACK, retry budget, DLQ hoặc idempotency theo nghĩa business.

Nếu hệ thống B bắt buộc thực hiện hành động, hãy dùng **API/message broker/domain event** có schema, event ID, delivery acknowledgement và idempotency phù hợp. Vẫn có thể log `EmailDispatchRequested` để chẩn đoán, nhưng logger không được là nguồn lệnh duy nhất.

**Ngoại lệ cần phân biệt:** một nền tảng *change data capture* (CDC) đọc **database transaction log** theo giao thức riêng có thể phát domain events. Đây không phải log text của `logger.info`, và không hợp thức hóa việc grep stdout để thực thi nghiệp vụ.

## 14. Message consumer: log không thay ACK/NACK, retry hay DLQ

Trong một consumer:

```java
// SAI: thất bại nhưng không làm gì với delivery state.
try {
    processBusinessMessage(message);
} catch (Exception ex) {
    logger.error("Processing failed", ex);
}
// Framework có thể coi handler hoàn thành tùy cấu hình.
```

Khi handler kết thúc bình thường, một số framework/cấu hình auto-ack có thể coi message đã xử lý. Lần thử sẽ không được retry dù thao tác nghiệp vụ thất bại. Cần xác định policy:

```text
Receive
   |
   +-- VALIDATION REJECTED --> ACK hoặc DLQ theo contract
   |
   +-- TRANSIENT FAILURE --> retry/backoff, NACK/requeue có kiểm soát
   |
   +-- BUSINESS COMMITTED --> ACK/commit offset theo broker contract
   |
   +-- COMMIT UNKNOWN --> reconcile/idempotency trước khi lặp
```

Lựa chọn ACK/NACK khác nhau giữa RabbitMQ, Kafka và framework. RabbitMQ có consumer acknowledgment; Kafka thường commit offset/position, không có per-message NACK cùng semantics. Không viết logic chung chỉ dựa trên dòng log `"Processed"`.

Một lời gọi `logger.info("ACK_SENT")` có thể xảy ra trước khi broker ghi nhận; nếu connection chết, broker có thể redeliver. Dùng `messageId`/`operationId`, idempotency store và nguồn sự thật để phát hiện side effect đã xảy ra hay chưa.

**Không dùng log ERROR làm tín hiệu retry.** Retry cần classification của lỗi, budget, backoff, timeout và kiểm tra side effect. Một log lỗi ở lần thử đầu có thể đi kèm logical operation cuối thành công; ngược lại không có ERROR log không chứng minh đã ACK.

## 15. Async logging làm anti-pattern càng khó phát hiện

Logback `AsyncAppender` hoặc các backend async có thể đẩy event vào memory queue và worker mới ghi xuống sink.

```text
Business thread:
  DB commit -> logger.info("SUCCEEDED") -> response
                      |
                      v
                Async log queue
                      |
                      v
                Agent / collector
```

Vì thế:

- API logging trả về không đồng nghĩa event đã bền vững.
- Event có thể xuất hiện trên dashboard sau response hoặc sau một request khác.
- Queue đầy có thể discard event hoặc block producer tùy policy.
- Crash trước khi drain queue có thể làm mất log.
- Nhiều thread, nhiều pod và collector batching có thể làm thay đổi thứ tự quan sát.
- Dữ liệu ở sink có thể bị index trễ hoặc thiếu trường do parser lỗi.

Nếu logic nghiệp vụ dựa vào **“đã thấy log”** để chốt trạng thái, sẽ phát sinh race condition và failure coupling. Khi cần business synchronization, dùng transaction, broker, future/ack hoặc state store với semantics rõ. Không suy từ một thứ tự log toàn cục khi backend không hứa thứ tự đó.

**Đặc biệt:** mất operational log và mất business message là hai vấn đề khác nhau. Message có thể được xử lý/ACK nhưng log mất; cũng có thể log `ACK_ATTEMPTED` tồn tại mà broker chưa nhận ACK.

## 16. Audit bắt buộc và transactional outbox không phải log text thông thường

Một số thao tác như thay đổi quyền hoặc nghiệp vụ có nghĩa vụ kiểm toán có thể yêu cầu **lưu bằng chứng** trước khi báo thành công. Không nên phản ứng bằng cách:

```java
logger.info("AUDIT action=ROLE_CHANGE outcome=SUCCEEDED");
return success();
```

nếu chính sách yêu cầu audit bền vững: logger có thể bị filter, async queue có thể mất khi crash.

Một phương án là **transactional outbox** cho mutation cùng event chờ phát:

```text
BEGIN DB transaction
  update business state
  insert audit_outbox(eventId, operationId, action, outcome)
COMMIT
       |
       v
Outbox dispatcher -> sink (retry / ACK / dedup)
```

Nếu DB rollback, cả mutation và outbox record rollback. Nếu dispatcher gửi rồi mất ACK, event có thể gửi lại; consumer/sink cần dedup theo `eventId`. Outbox **không tự mang exactly-once toàn hệ thống**, nhưng làm rõ ranh giới bền vững giữa business commit và event chờ giao.

Với event `DENIED/REJECTED` không có mutation commit, nếu ghi trong transaction rồi rollback thì event cũng có thể mất. Có thể cần audit transaction/kênh riêng. Nếu audit không khả dụng, tổ chức phải chọn policy: fail closed cho thao tác nhạy cảm, retry/spool bền vững hoặc cơ chế xử lý sự cố. **Đó là quyết định được thiết kế và kiểm thử**, không phải control flow ẩn trong một lời gọi `logger.error`.

## 17. Bảo mật: log không thay authorization enforcement

Ví dụ lỗi nghiêm trọng:

```java
// SAI: vẫn trả dữ liệu nhạy cảm.
if (!isAuthorized(actor, resource)) {
    logger.warn("Unauthorized access");
}
return loadSensitiveData(resource);
```

Phải chặn access:

```java
if (!isAuthorized(actor, resource)) {
    throw new AccessDeniedException("POLICY_DENIED");
}
return loadSensitiveData(resource);
```

Đây là snippet cần class của dự án. Audit `DENIED` có thể được ghi theo policy nhưng **không phải lý do duy nhất** khiến truy cập bị từ chối. Nếu audit sink gặp lỗi, đường bảo vệ tài nguyên vẫn phải đảm bảo người không có quyền không nhận dữ liệu; nếu policy yêu cầu fail closed, làm điều đó bằng enforcement rõ ràng.

Những rủi ro liên quan:

- Người dùng có thể chèn `\r`/`\n` vào message và tạo log injection nếu formatter/encoder không escape.
- Log parser coi dòng giả `"ADMIN_APPROVED"` thành tín hiệu quyền là vô cùng nguy hiểm.
- Không lấy `actorId`/`outcome` từ body do client tự khai rồi tin như bằng chứng server.
- Không log password, access/refresh token, cookie, private key hoặc raw request body.
- Không dùng dữ liệu `toString()` của DTO làm input log nếu chưa rà soát PII.
- Đọc log/dashboard phải có quyền riêng; việc được phép xem log không trao quyền nghiệp vụ.

Một hệ thống đọc log để kích hoạt hành động tự động (ví dụ SIEM/SOAR) cần policy, xác thực nguồn, kiểm soát false positive và quyền riêng. Nó không nên coi mọi dòng text tự do là một command có đặc quyền.

## 18. Kiểm thử phát hiện anti-pattern: logger OFF vẫn cho cùng kết quả

**Metamorphic test** có ích: chạy cùng một thao tác trên **hai trạng thái ban đầu tương đương**, một lần bật logging, một lần tắt INFO/DEBUG, sau đó so kết quả nghiệp vụ. Logging có thể khác, nhưng result/state phải như nhau.

Ma trận:

| Kịch bản | Logging | Kết quả nghiệp vụ bắt buộc |
| --- | --- | --- |
| Transfer 30 khi có đủ số dư | INFO | SUCCEEDED, trừ/cộng đúng |
| Transfer 30 trên fixture tương đương | OFF | SUCCEEDED, trừ/cộng đúng |
| Transfer 150 khi chỉ có 100 | INFO | REJECTED, không mutation |
| Transfer 150 trên fixture tương đương | OFF | REJECTED, không mutation |
| Actor không có quyền | OFF | Không truy cập/mutate dữ liệu |
| Dependency không khả dụng | OFF | Exception/result failure không bị nuốt |
| Business transaction rollback | INFO | Không có success commit giả |
| Sink/collector hỏng | INFO | Business policy vẫn được áp dụng, đường audit có policy riêng |
| Message redelivery | INFO/OFF | Idempotency vẫn ngăn double side effect |

### JUnit 5: kiểm tra domain behavior

Với `LogIsNotControlFlowDemo` ở phần 11, thêm JUnit Jupiter vào dự án và đặt test cùng package:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class LogControlFlowTest {
    @Test
    void transferResultIsIndependentOfObservation() {
        var withLogging = new LogIsNotControlFlowDemo.Accounts();
        var withoutLogging = new LogIsNotControlFlowDemo.Accounts();

        var a = withLogging.transfer(30);
        var b = withoutLogging.transfer(30);

        assertEquals(a, b);
        assertEquals(70, withLogging.sourceBalance());
        assertEquals(70, withoutLogging.sourceBalance());
        assertEquals(30, withLogging.targetBalance());
        assertEquals(30, withoutLogging.targetBalance());
    }

    @Test
    void rejectDoesNotMutateBalances() {
        var accounts = new LogIsNotControlFlowDemo.Accounts();
        var result = accounts.transfer(150);

        assertEquals(
                LogIsNotControlFlowDemo.Status.REJECTED,
                result.status());
        assertEquals("INSUFFICIENT_FUNDS", result.reasonCode());
        assertEquals(100, accounts.sourceBalance());
        assertEquals(0, accounts.targetBalance());
    }
}
```

**Phạm vi:** đoạn test này kiểm tra domain logic đã được tách logger; nó **không thực sự bật/tắt logger**. Để test end-to-end tính độc lập, hãy gọi qua application boundary có logging thật, đổi logger level với fixture độc lập, so DB/result, đồng thời capture event ở appender để xác minh khác biệt kênh quan sát. Không hiểu nhầm một unit test đơn giản thành đã kiểm chứng toàn bộ pipeline.

### Test được gì ngoài happy path?

1. **Validation:** input sai không tạo mutation dù logger OFF.
2. **Authorization:** policy chặn trước khi repository đọc/ghi dữ liệu nhạy cảm.
3. **Exception:** dependency exception không bị nuốt chỉ vì catch đã log.
4. **Transaction:** rollback được xác nhận và không có event `SUCCEEDED` giả.
5. **Concurrency:** nhiều request không dựa vào global `lastLogMessage` hay trạng thái logger.
6. **Async:** message ACK/retry theo state thật, không theo text log.
7. **Collector outage:** operational logging lỗi nhưng policy business/audit vẫn đúng.
8. **Security:** input chứa CR/LF hoặc token giả không biến thành business command từ parser.

Với appender async, dùng latch/queue/ack và timeout hữu hạn để đợi; không `Thread.sleep(200)` rồi suy ra event đã đến hoặc bị filter. Nếu cần assert **không có event**, xác định cách drain/barrier phù hợp với backend.

## 19. Test oracle: log assertion không thay kiểm tra trạng thái

Những assertion thiếu căn cứ:

```java
verify(logger).error("Insufficient funds");
assertTrue(logText.contains("ROLLBACK"));
assertTrue(logText.contains("ACK_SENT"));
```

Chúng chỉ cho biết một lời gọi hoặc chuỗi ký tự, không chứng minh transaction rollback hoặc broker ACK. Nên dùng oracle đúng:

| Yêu cầu | Oracle chính | Log test bổ trợ |
| --- | --- | --- |
| Thiếu tiền không được trừ | Account/DB state + Result | `REJECTED/INSUFFICIENT_FUNDS` |
| Unauthorized không lấy được dữ liệu | Authorization outcome/response | Audit `DENIED` |
| Lỗi phải truyền tới caller | `assertThrows` hoặc API error result | Throwable/cause |
| Transaction rollback | DB state sau rollback | Không có success giả |
| Job retry có giới hạn | Retry scheduler/broker attempt state | `RETRY_SCHEDULED` |
| Broker nhận ACK | Client/broker contract | `ACK_ATTEMPTED/CONFIRMED` |
| Event outbox đã commit | DB outbox cùng transaction | Log về dispatcher |
| Logger không quyết định nghiệp vụ | State/result khi level khác nhau | Đếm event ở sink |
| Collector nhận log | Sink query/receipt theo event ID | Appender status |
| Error budget logging | Source-to-sink reconciliation | Metric về drop/latency |

Bài test logging nên kiểm tra `level`, `message template`, `arguments`, `MDC`, `Throwable` và các structured fields khi những thuộc tính ấy là contract. Không khóa toàn bộ timestamp, thread name hoặc stack frame để giả vờ kiểm tra business outcome.

## 20. Tránh ràng buộc logic vào lỗi logging backend

Cần phân biệt ba loại hệ thống:

**Operational logging best-effort:** khi ghi log thất bại, thường không thay đổi kết quả transaction nghiệp vụ. Cần metric/health và cảnh báo riêng về mất log.

**Audit bắt buộc:** nếu một thao tác nhạy cảm bắt buộc có bằng chứng durable mới được xác nhận, phải xây transaction/ack/fail-closed policy. Việc audit store unavailable có thể khiến thao tác bị chặn theo contract, nhưng đó là **điều kiện thực thi được thiết kế**, không phải ngẫu nhiên logger throw.

**Domain event delivery:** khi downstream phải hành động, dùng outbox/broker/API có event ID, retry, dedup và khả năng đối soát. Không dựa vào việc consumer “thấy INFO log” trong collector.

### Một số tình huống lỗi cần hỏi

- Nếu collector ngừng hoạt động 20 phút, request nghiệp vụ có được phép tiếp tục không?
- Nếu một log `DENIED` bị drop, authorization có còn chặn đúng không?
- Nếu logging appender throw từ custom implementation, ứng dụng phải bắt, giảm cấp hay fail closed ở boundary nào?
- Nếu transaction commit nhưng event audit chưa gửi, có durable outbox nào giữ lại không?
- Nếu event đến collector hai lần vì retry, ai dedup và bằng ID nào?
- Nếu log level bị đổi lúc incident, có case nào đột nhiên bật/tắt mutation?
- Nếu log đã format khác vì cập nhật thư viện, có hệ thống nào dùng regex để ra quyết định nghiệp vụ không?

Một câu trả lời rõ ràng cho từng câu là dấu hiệu kiến trúc đã phân tách concern đúng.

## 21. Quy trình refactor anti-pattern trong codebase

1. **Tìm code path đáng ngờ:** `logger.error` trong guard nhưng thiếu return/throw; `catch` chỉ log; `isDebugEnabled` bao lệnh mutate; side effect trong argument; service parse log text.
2. **Xác định nghĩa vụ nghiệp vụ:** phép kiểm tra nào phải chặn, lỗi nào cần propagate, trạng thái nào phải commit/rollback?
3. **Tạo contract kết quả:** `Result`/enum/typed exception với `reasonCode` ổn định, không lấy từ formatted log message.
4. **Di chuyển side effect đúng vị trí:** guard chạy trước mutation, transaction boundary rõ, không đặt action bắt buộc trong logger.
5. **Đưa log về vai trò quan sát:** event có `action/outcome/reasonCode/operationId` được lấy từ quyết định đã xác minh.
6. **Chọn đúng boundary logging:** tránh ba tầng log cùng exception; giữ root cause cho technical errors.
7. **Thay log-driven workflow:** domain event/outbox/message broker/API có ACK và idempotency khi cần.
8. **Bổ sung regression tests:** logger OFF, unexpected exceptions, rollback, conflict, retry, authorization, concurrency, collector outage.
9. **Kiểm tra tương thích monitoring:** nếu alert hiện dựa vào text message, di chuyển có kế hoạch sang structured fields/metrics.
10. **Theo dõi sau triển khai:** tỷ lệ business outcomes, duplicate effects, error rate, audit backlog và tình trạng logging pipeline.

Không biến mọi `logger.warn` thành `throw` một cách máy móc: có warning chỉ mang tính thông tin, hoặc fallback đã xử lý thành công. Cần hiểu **hợp đồng side effect và kết quả** trước khi sửa.

## 22. Những hiểu lầm phổ biến

| Hiểu lầm | Thực tế |
| --- | --- |
| Ghi log ERROR làm phương thức thất bại | Logger không đổi control flow; cần return/throw/state. |
| Không có ERROR log là không có lỗi | Log có thể bị filter/mất, hoặc lỗi không được ghi. |
| Dùng DEBUG như feature flag | Runtime log policy không phải quyền nghiệp vụ. |
| Logger tự rollback transaction | Commit/rollback do transaction manager. |
| Catch rồi log là caller biết lỗi | Exception đã bị nuốt nếu không propagate/map. |
| Bật lazy supplier sẽ chạy nghiệp vụ khi cần | Supplier có thể không chạy; chỉ dùng cho diagnostic thuần. |
| Log trong argument khi DEBUG tắt thì không chạy | Java đánh giá argument trước lời gọi logger. |
| Parse `SUCCESS` từ stdout là integration đủ tin cậy | Log text không có delivery, schema, idempotency contract phù hợp. |
| INFO vào async queue nghĩa đã durable | Enqueue khác collector ACK hoặc storage commit. |
| Test thấy log là nghiệp vụ đúng | Phải kiểm tra state/result/exception/side effect. |
| Bất kỳ retry nào cũng an toàn nếu có ERROR log | Có thể side effect đã xảy ra, cần idempotency/reconciliation. |
| Audit chỉ cần `logger.info` | Có thể cần durable store, retention, integrity và quyền riêng. |

## 23. Checklist code review

- [ ] Guard nghiệp vụ dùng `return`, `throw`, typed result hoặc state transition; không chỉ log rồi tiếp tục.
- [ ] `isDebugEnabled`, log level hoặc filter không điều khiển authorization, validation, mutation và transaction.
- [ ] Không có side effect quan trọng trong argument/lazy supplier của logger.
- [ ] Exception được propagate, map hoặc xử lý phục hồi có chủ đích; không bị nuốt vì đã log.
- [ ] `SUCCEEDED` chỉ ghi khi hiệu lực nghiệp vụ đã được xác minh; không báo trước commit.
- [ ] Không dùng text log/grep/regex để quyết định retry, ACK, DLQ, API response hoặc command.
- [ ] Kết quả nghiệp vụ có mã/enum ổn định, không suy từ severity hoặc message string.
- [ ] Có boundary logging rõ, không ghi lặp exception ở mọi tầng.
- [ ] Authorization vẫn chặn đúng khi logging OFF hoặc audit sink không khả dụng.
- [ ] Audit/event bắt buộc có delivery/durability contract riêng khi phù hợp.
- [ ] Test so state và outcome giữa các mức logging khác nhau trên fixture tương đương.
- [ ] Test exception/rollback, concurrency, idempotency, broker lost ACK và collector outage theo phạm vi.
- [ ] Logging không chứa token, raw request body, user input chưa escape hoặc dữ liệu nhạy cảm không cần thiết.
- [ ] Metrics/alerts cho business và logging reliability tách biệt, có runbook khi sink lỗi.
- [ ] Refactor giữ tương thích monitor và báo cáo đúng thay đổi đối với log schema.

**Kết luận:** logging chỉ nên **mô tả điều đã xảy ra**. Việc bật/tắt log, lỗi appender hay chậm collector không được tự ý quyết định quy tắc nghiệp vụ. Dùng `Result`/exception/state machine/transaction/domain event để thực thi và kiểm soát hành động; sau đó dùng log như một kênh quan sát được kiểm soát. Nếu cần audit hoặc delivery bắt buộc, thiết kế hợp đồng lưu bền vững riêng, thay vì dùng chuỗi log như một nút điều khiển ngầm.
