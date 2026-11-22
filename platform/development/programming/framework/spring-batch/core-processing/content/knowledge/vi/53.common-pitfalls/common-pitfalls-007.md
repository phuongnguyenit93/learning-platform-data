# Retry lỗi vĩnh viễn trong Spring Batch: nhận diện và xử lý đúng

Trong một batch job, retry là công cụ hữu ích khi lỗi **có khả năng tự biến mất**: kết nối mạng bị gián đoạn, dịch vụ đối tác tạm trả lỗi quá tải hoặc một giao dịch bị deadlock. Nhưng nếu dữ liệu không hợp lệ, thiếu trường bắt buộc, mã định danh sai hoặc cấu hình xác thực bị hỏng, việc chạy lại đúng thao tác với đúng đầu vào thường chỉ tạo ra **cùng một lỗi**. Đây là lỗi rất hay gặp khi dùng Spring Batch: **retry cả những lỗi vĩnh viễn**.

Hậu quả không chỉ là tốn vài lần thử. Khi hàng trăm nghìn item có cùng lỗi, retry sai loại sẽ làm job chậm nhiều lần, tăng tải lên database và API, khiến SLA bị trễ, tạo log ồn ào và có thể gây tác dụng phụ trùng lặp nếu thao tác không idempotent.

Bài học thuộc **Spring Batch Core Processing → Lỗi thường gặp**, trình bày cách phân biệt lỗi vĩnh viễn và lỗi tạm thời; cấu hình retry/skip/fail trong chunk step; tránh retry ở cả nhiều tầng; kiểm soát backoff, giới hạn và timeout; bảo vệ side effect; quan sát lỗi và kiểm thử để bảo đảm dữ liệu không hợp lệ **không bị thử lại vô ích**. Ví dụ sử dụng **Java 17, Spring Boot 3.x, Spring Batch 5.x và JUnit 5**.

## 1. Thế nào là retry lỗi vĩnh viễn?

**Retry** là thực hiện lại một thao tác sau khi nó thất bại, với kỳ vọng điều kiện gây lỗi sẽ thay đổi. Một lỗi được coi là **vĩnh viễn đối với lần xử lý hiện tại** nếu thử lại cùng dữ liệu và môi trường mà không thay đổi gì sẽ không có khả năng thành công.

Ví dụ một batch nhập đơn hàng:

```text
Item A: amount = "120.00"    -> hợp lệ
Item B: amount = "abc"       -> số tiền không parse được
Item C: amount = "-10.00"    -> số tiền trái quy tắc nghiệp vụ
Item D: API đối tác timeout  -> có thể phục hồi
Item E: DB deadlock          -> có thể phục hồi
```

Nếu cấu hình retry tất cả exception với ba lần thử:

```text
Item B: parse("abc") -> FAIL
        parse("abc") -> FAIL
        parse("abc") -> FAIL

Item C: validate(-10) -> FAIL
        validate(-10) -> FAIL
        validate(-10) -> FAIL
```

Không có bất kỳ dữ liệu hay điều kiện nào thay đổi giữa các lần thử, nên hai item đó **không trở nên hợp lệ**. Chúng cần được phân loại thành lỗi dữ liệu, sau đó **skip/quarantine có kiểm soát** hoặc làm job **FAILED** tùy quy tắc nghiệp vụ.

Ngược lại:

```text
Item D: POST partner request -> HTTP 503
        wait 500 ms
        POST partner request -> success
```

Đây là tình huống retry có thể có ích. Tuy nhiên, ngay cả với lỗi tạm thời, retry chỉ an toàn khi hành động có thể lặp lại, có giới hạn và không làm phát sinh side effect trùng.

## 2. Ba nhóm lỗi và quyết định xử lý

| Nhóm | Dấu hiệu | Ví dụ | Hành động ưu tiên |
| --- | --- | --- | --- |
| **Permanent item error** | Dữ liệu item không đạt hợp đồng và sẽ không tự sửa | Sai ngày, amount âm, thiếu ID, giá trị enum không hỗ trợ | Skip/quarantine nếu được cho phép; nếu không thì fail |
| **Transient operational error** | Điều kiện hạ tầng có thể thay đổi sau một khoảng ngắn | Timeout, 503 có giới hạn, deadlock, lỗi connection ngắn hạn | Retry hữu hạn, backoff; hết lượt thì fail hoặc xử lý theo policy |
| **Permanent system/config error** | Toàn job không thể thành công cho tới khi có can thiệp | Sai credentials, schema DB không tương thích, thiếu bảng, API contract hỏng | Fail fast và cảnh báo; không skip tất cả item |

Điểm dễ nhầm là **permanent không có nghĩa luôn phải skip**. Một item sai dữ liệu có thể được phép đưa vào reject store; còn lỗi cấu hình xác thực là vấn đề **toàn hệ thống**, phải dừng job, không được biến nó thành hàng nghìn item bị skip.

### 2.1. Không phân loại chỉ bằng tên exception chung

| Tình huống | Thường nên hiểu thế nào? | Lưu ý |
| --- | --- | --- |
| `NumberFormatException` do field input `"abc"` | Dữ liệu không hợp lệ | Chuyển thành exception nghiệp vụ xác định |
| `IllegalArgumentException` | Chưa đủ thông tin | Có thể do input hoặc bug; không skip toàn bộ loại này |
| HTTP `400 Bad Request` | Thường là request không hợp lệ | Nếu payload đúng nhưng API đổi contract, cần fail hệ thống |
| HTTP `401`/`403` | Thường là quyền/cấu hình | Fail fast và sửa auth; không retry item hàng loạt |
| HTTP `404` | Phụ thuộc hợp đồng | Có thể là item không tồn tại hoặc sự cố định tuyến |
| HTTP `409` | Phụ thuộc nghiệp vụ | Có thể là duplicate idempotent hoặc conflict thật |
| HTTP `429` | Rate limit tạm thời | Retry theo `Retry-After`/backoff và ngân sách chung |
| HTTP `503` | Dịch vụ tạm không sẵn sàng | Retry có giới hạn; khi outage kéo dài nên fail/circuit break |
| SQL duplicate key | Thường là lỗi dữ liệu hoặc idempotency | Không retry vô ích; xác định đã ghi trước hay conflict |
| SQL deadlock/serialization failure | Có thể tạm thời | Retry transaction thích hợp nếu operation an toàn |
| Connection timeout | Có thể tạm thời | Không được retry vô hạn khi pool/DB đã quá tải |
| `NullPointerException` bất ngờ | Có thể là bug | Fail và điều tra; không tự skip mọi NPE |

Một exception cụ thể cũng có thể bị **bọc** trong `RuntimeException`, `CompletionException` hoặc lớp exception của HTTP client. Vì vậy nơi chuyển đổi lỗi tại ranh giới giao tiếp cần phân loại đủ chính xác, giữ nguyên ngữ nghĩa retryable/non-retryable, thay vì bắt mọi `Exception` rồi ném `TemporaryException` hoặc `RuntimeException` chung.

### 2.2. “Permanent” có thể phụ thuộc vào thời điểm

Đơn hàng tham chiếu tới khách hàng chưa được đồng bộ có thể không hợp lệ **trong snapshot hiện tại**, nhưng dữ liệu upstream có thể được cập nhật sau một giờ. Retry sau vài mili giây trong cùng chunk không giải quyết được; đó có thể là một **deferred record** cần đợi dữ liệu tham chiếu rồi replay về sau.

Do đó nên tách:

- Retry **ngay trong execution** cho sự cố ngắn hạn.
- **Defer/replay có lịch** cho dữ liệu phụ thuộc có thể xuất hiện về sau.
- **Quarantine để sửa dữ liệu** cho lỗi xác thực quy tắc.
- **Fail job** cho cấu hình hoặc hợp đồng hệ thống bị hỏng.

## 3. Vì sao cấu hình retry quá rộng nguy hiểm?

Ví dụ cấu hình không nên áp dụng tùy tiện:

```java
.faultTolerant()
.retry(Exception.class)
.retryLimit(10)
```

Nếu một file có 50.000 item sai định dạng, mười lần thử cho mỗi item có thể tạo **hàng trăm nghìn lần xử lý lỗi**, chưa kể rollback và các lần gọi lại tùy transaction của framework. Kết quả thường vẫn thất bại hoặc bị skip, nhưng tài nguyên và thời gian đã bị tiêu tốn.

Nguy hiểm hơn:

```java
.retry(RuntimeException.class)
.skip(Exception.class)
.skipLimit(1_000_000)
```

Với policy quá rộng này, lỗi lập trình, lỗi JDBC, lỗi auth và invalid item đều có nguy cơ bị che khuất hoặc xử lý sai ngữ nghĩa. `skipLimit` lớn làm job dễ `COMPLETED` dù thực tế đã mất gần hết input. Một batch **hoàn thành kỹ thuật** không đồng nghĩa dữ liệu đầu ra đủ và đúng.

### 3.1. Tác động đến throughput và deadline

Giả sử mỗi lần thử một item mất 80 ms, có 20.000 item lỗi vĩnh viễn:

| Cấu hình | Số attempt lý thuyết | Thời gian xử lý attempt |
| --- | ---: | ---: |
| Không retry lỗi permanent | 20.000 | 1.600 giây |
| `retryLimit(3)` trên lỗi permanent | 60.000 | 4.800 giây |
| `retryLimit(5)` trên lỗi permanent | 100.000 | 8.000 giây |

Đây chỉ là **phép tính minh họa nếu mọi attempt đều mất đúng 80 ms, chạy tuần tự và bỏ qua overhead**; Spring Batch có thể thực hiện thêm thao tác do rollback và chính sách fault tolerance. Nhưng xu hướng rõ ràng: retry sai loại làm tăng độ trễ, tải lên dependency và khả năng trễ deadline mà không tăng tỷ lệ item hợp lệ.

## 4. Thiết kế exception theo ngữ nghĩa nghiệp vụ

Một thiết kế dễ quản lý là đặt các loại lỗi ở ranh giới của processor/gateway và **chỉ retry các loại đã xác định là tạm thời**.

Ví dụ model:

```java
package com.example.batch;

import java.math.BigDecimal;

public record IncomingOrder(
        String orderId,
        String amountText) {}

public record AcceptedOrder(
        String orderId,
        BigDecimal amount,
        String partnerReference) {}
```

Trong dự án Java, mỗi `public record` ở một file cùng tên. Các class phía dưới cũng nên được tách thành file độc lập.

### 4.1. Exception lỗi dữ liệu vĩnh viễn

```java
package com.example.batch;

public class InvalidOrderException extends RuntimeException {

    private final String reasonCode;

    public InvalidOrderException(String reasonCode) {
        super(reasonCode);
        this.reasonCode = reasonCode;
    }

    public String reasonCode() {
        return reasonCode;
    }
}
```

`reasonCode` cần là mã cố định trong tập cho phép, ví dụ `MISSING_ORDER_ID`, `INVALID_AMOUNT`, `NON_POSITIVE_AMOUNT`. Không đưa nguyên payload, email hoặc số tài khoản vào exception message vì chúng có thể bị ghi vào log/metadata lỗi.

### 4.2. Exception lỗi tạm thời và cấu hình

```java
package com.example.batch;

public class TransientPartnerException extends RuntimeException {

    public TransientPartnerException(String safeCode) {
        super(safeCode);
    }
}
```

```java
package com.example.batch;

public class PartnerConfigurationException
        extends RuntimeException {

    public PartnerConfigurationException(String safeCode) {
        super(safeCode);
    }
}
```

`TransientPartnerException` được dùng cho lỗi có thể retry như `PARTNER_TIMEOUT` hoặc `PARTNER_UNAVAILABLE`. `PartnerConfigurationException` đại diện cho lỗi cần sửa cấu hình như `INVALID_CREDENTIALS`; loại này phải fail fast. Không coi một thông điệp lỗi HTTP bất kỳ là tạm thời chỉ vì đến từ mạng.

### 4.3. Chuyển lỗi ở ranh giới gọi đối tác

Giả sử ứng dụng có interface:

```java
package com.example.batch;

public interface PartnerGateway {
    String registerOrder(String orderId);
}
```

Implementation thực tế chịu trách nhiệm chuyển HTTP/DB exceptions thành các exception đã phân loại, ví dụ:

```text
HTTP timeout / 503 / 429 có thể phục hồi
    -> TransientPartnerException

HTTP 401 / 403 vì credential sai
    -> PartnerConfigurationException

HTTP 400 vì input item sai được xác nhận
    -> InvalidOrderException

HTTP 409 đã xử lý theo idempotency contract
    -> success hoặc lỗi conflict được phân loại rõ
```

Một số status cần xử lý theo **hợp đồng cụ thể của API**. Với HTTP 429, cần tôn trọng `Retry-After` và giới hạn rate; với 409, cần xác minh cùng idempotency key có đại diện cho một kết quả đã thực hiện thành công hay không. Không suy ra điều đó chỉ từ status code.

Nếu code gateway đang dùng `catch (Exception ex) { throw new TransientPartnerException(...); }`, mọi lỗi validation, bug và cấu hình đều bị biến thành retryable. Đây là anti-pattern cần loại bỏ. Nên bắt **những exception cụ thể** của client tại một lớp adapter và để exception không biết/không mong đợi làm job thất bại để được điều tra.

## 5. Validate trước khi gọi thao tác có side effect

Đặt validation sớm giúp tránh gọi API hoặc ghi DB rồi mới phát hiện record chắc chắn không hợp lệ.

```java
package com.example.batch;

import java.math.BigDecimal;
import org.springframework.batch.item.ItemProcessor;

public class OrderProcessor
        implements ItemProcessor<IncomingOrder, AcceptedOrder> {

    private final PartnerGateway partnerGateway;

    public OrderProcessor(PartnerGateway partnerGateway) {
        this.partnerGateway = partnerGateway;
    }

    @Override
    public AcceptedOrder process(IncomingOrder order) {
        if (order.orderId() == null || order.orderId().isBlank()) {
            throw new InvalidOrderException("MISSING_ORDER_ID");
        }

        BigDecimal amount;
        try {
            amount = new BigDecimal(order.amountText());
        } catch (NumberFormatException | NullPointerException ex) {
            throw new InvalidOrderException("INVALID_AMOUNT");
        }

        if (amount.signum() <= 0) {
            throw new InvalidOrderException("NON_POSITIVE_AMOUNT");
        }

        // Gọi đối tác chỉ sau khi validation tại chỗ thành công.
        String partnerReference =
                partnerGateway.registerOrder(order.orderId());

        return new AcceptedOrder(
                order.orderId(), amount, partnerReference);
    }
}
```

Code trên phân biệt hai đường đi:

```text
amount="invalid"
    |
    v
InvalidOrderException
    |
    +--> skip/quarantine nếu policy cho phép
    +--> không gọi PartnerGateway

amount="120.00"
    |
    v
PartnerGateway
    |
    +--> TransientPartnerException -> có thể retry
    +--> PartnerConfigurationException -> fail ngay
    +--> success -> AcceptedOrder
```

**Giới hạn cần nhớ:** processor trong chunk-oriented step có thể được gọi lại khi retry hoặc rollback. Nếu `registerOrder(...)` tạo một giao dịch bên ngoài mà không có idempotency key, retry lỗi mạng có thể tạo **đơn hàng đối tác trùng** dù Spring Batch chỉ ghi một output. Phần 8 giải thích cách bảo vệ.

## 6. Cấu hình `retry`, `noRetry` và `skip` trong Spring Batch 5

Với fault-tolerant chunk step, một chính sách rõ ràng có thể là:

- `InvalidOrderException`: **không retry**, chỉ skip khi được cho phép và còn ngân sách reject.
- `TransientPartnerException`: retry có giới hạn và backoff.
- `PartnerConfigurationException`: không retry, không skip, khiến step/job thất bại.
- Lỗi khác không được phân loại: fail để phát hiện bug hoặc lỗi hệ thống chưa được xử lý.

Ví dụ cấu hình:

```java
package com.example.batch;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.retry.backoff.FixedBackOffPolicy;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class ImportOrdersBatchConfig {

    @Bean
    FixedBackOffPolicy partnerBackOffPolicy() {
        FixedBackOffPolicy policy = new FixedBackOffPolicy();
        policy.setBackOffPeriod(500L);
        return policy;
    }

    @Bean
    OrderProcessor orderProcessor(PartnerGateway gateway) {
        return new OrderProcessor(gateway);
    }

    @Bean
    Step importOrdersStep(
            JobRepository repository,
            PlatformTransactionManager transactionManager,
            ItemReader<IncomingOrder> reader,
            OrderProcessor processor,
            ItemWriter<AcceptedOrder> writer,
            FixedBackOffPolicy partnerBackOffPolicy) {

        return new StepBuilder("importOrdersStep", repository)
                .<IncomingOrder, AcceptedOrder>chunk(
                        100, transactionManager)
                .reader(reader)
                .processor(processor)
                .writer(writer)
                .faultTolerant()
                .retry(TransientPartnerException.class)
                .retryLimit(3)
                .noRetry(InvalidOrderException.class)
                .noRetry(PartnerConfigurationException.class)
                .backOffPolicy(partnerBackOffPolicy)
                .skip(InvalidOrderException.class)
                .skipLimit(20)
                .build();
    }

    @Bean
    Job importOrdersJob(
            JobRepository repository, Step importOrdersStep) {
        return new JobBuilder("importOrdersJob", repository)
                .start(importOrdersStep)
                .build();
    }
}
```

Reader và writer trong ví dụ là bean do ứng dụng cung cấp; cần cấu hình JDBC/file reader, writer, schema và transaction theo dự án. `org.springframework.retry.backoff.FixedBackOffPolicy` thuộc thư viện Spring Retry được Spring Batch sử dụng cho retry policy.

### 6.1. Đọc cấu hình theo đúng nghĩa

| Dòng | Tác dụng |
| --- | --- |
| `.retry(TransientPartnerException.class)` | Chỉ định exception được retry |
| `.retryLimit(3)` | Cho phép tối đa **ba attempt tổng cộng**, tính cả lần đầu, theo retry policy |
| `.noRetry(InvalidOrderException.class)` | Đảm bảo lỗi dữ liệu được đánh dấu không retry |
| `.noRetry(PartnerConfigurationException.class)` | Không thử đi thử lại lỗi cấu hình |
| `.backOffPolicy(...)` | Chèn khoảng đợi giữa các lần retry theo chính sách |
| `.skip(InvalidOrderException.class)` | Cho phép bỏ qua loại lỗi dữ liệu này |
| `.skipLimit(20)` | Giới hạn số item bị skip trong một `StepExecution` |

Với một `InvalidOrderException` tại processor, thông thường không phát sinh retry theo retry policy, sau đó framework xử lý theo skip policy. Nếu tổng skip vượt 20, step sẽ thất bại khi item tiếp theo cần skip. **Skip và retry là hai policy khác nhau**; thêm `.skip(...)` không biến một lỗi permanent thành retryable.

Với `TransientPartnerException`, Spring Batch thử lại tối đa ba attempt theo policy. Nếu vẫn lỗi và không có skip policy phù hợp, step có thể `FAILED`. Đây thường là kết quả đúng cho outage bên ngoài: không nên âm thầm loại toàn bộ đơn hàng chỉ vì đối tác đang gặp sự cố.

### 6.2. Vì sao có cả allowlist retry và `noRetry`?

Nếu chỉ cấu hình `.retry(TransientPartnerException.class)`, các exception khác vốn không nằm trong retry allowlist. `noRetry(...)` giúp **thể hiện chủ đích** và đặc biệt hữu ích khi cấu hình chung được mở rộng bằng một superclass retryable ở nơi khác. Tuy nhiên, với các policy tùy biến, thứ tự và mức ưu tiên phân loại phải được kiểm tra theo API/version cụ thể.

Không nên đồng thời cấu hình một retry superclass quá rộng như `.retry(RuntimeException.class)` rồi dựa vào vài `.noRetry(...)` để bảo vệ tất cả lỗi còn lại. Khi thêm exception mới, chúng dễ bị retry ngoài ý muốn. **Allowlist hẹp** dễ vận hành hơn.

### 6.3. Backoff không biến lỗi vĩnh viễn thành lỗi tạm thời

`FixedBackOffPolicy` trong ví dụ chờ 500 ms giữa các lần retry; với lỗi tạm thời có thể dùng exponential backoff có giới hạn và jitter khi gọi dịch vụ lớn. Nhưng với `INVALID_AMOUNT`, chờ 500 ms hay 50 giây vẫn không sửa được input.

Backoff cần được phối hợp với:

- Timeout của HTTP/JDBC để mỗi attempt không treo vô hạn.
- Run window và finish deadline của batch.
- Rate limit hoặc `Retry-After` của đối tác.
- Tổng ngân sách retry khi nhiều item cùng lỗi.
- Chính sách retry của API client, message broker và orchestrator.

## 7. Trường hợp lỗi permanent ở reader, processor và writer

### 7.1. Lỗi ở reader

Ví dụ một dòng CSV sai định dạng khiến `FlatFileItemReader` ném `FlatFileParseException`. Nếu reader **có thể bỏ qua dòng hỏng** và nghiệp vụ cho phép mất một số record, có thể thêm ngoại lệ parse vào skip allowlist với giới hạn rõ:

```java
.skip(org.springframework.batch.item.file.FlatFileParseException.class)
.skipLimit(20)
```

Tuy nhiên, nếu header bị đổi, file sai schema hoặc checksum không khớp, việc skip từng dòng có thể gây mất dữ liệu hàng loạt. Các lỗi **ở cấp toàn file** nên được phát hiện trong `validateSourceStep` và fail trước khi import.

Retry một dòng CSV đã có số cột sai mà không sửa file **không giúp gì**. Bên cạnh đó, `onSkipInRead(Throwable)` của `SkipListener` không có item đã parse thành công, vì vậy cần lưu vị trí nguồn đã được xác minh thay vì in nguyên dòng có thể chứa dữ liệu nhạy cảm.

### 7.2. Lỗi ở processor

Đây là tình huống thường gặp nhất: validation phát hiện dữ liệu không hợp lệ. Nếu lỗi là `InvalidOrderException`, có thể skip và gửi record vào quarantine. Nếu input bị thiếu trường định danh quan trọng hoặc vi phạm quy định nghiệp vụ nghiêm trọng, policy có thể buộc **fail job**, dù loại lỗi này chỉ xuất hiện một lần.

Nếu code processor `catch (Exception e) { return null; }`, framework sẽ hiểu đó là **filtered item**, không phải skipped item. Khi ấy `filterCount` có thể tăng còn `skipCount` không tăng, làm mất dấu vết lỗi. Vì vậy `return null` chỉ dành cho những filter **có chủ đích**, không phải cách xử lý mọi exception.

### 7.3. Lỗi ở writer

Writer thường xử lý một `Chunk` có nhiều item. Lỗi `DuplicateKeyException` cần được xem xét theo hợp đồng:

- Nếu record đã được ghi thành công trước đó với cùng business/idempotency key, có thể cần **nhận diện lại kết quả đã tồn tại**, không nhất thiết coi là lỗi.
- Nếu dữ liệu xung đột với record khác, cần reject/fail theo policy và đưa trường hợp xung đột tới quy trình xử lý.
- Nếu writer ném lỗi hạ tầng, không tự coi item là invalid. Một lỗi của cả chunk không xác định ngay item cụ thể gây vấn đề.

Spring Batch fault-tolerant step có thể retry/rollback và trong một số trường hợp tách item để phát hiện item gây lỗi ghi khi skip được cấu hình. Vì vậy phải thiết kế writer có transaction và idempotency đúng; không suy ra một row trong chunk là nguyên nhân chỉ dựa trên callback của một lần writer error.

Không gọi `.skip(DataAccessException.class)` hoặc `.retry(DataAccessException.class)` trên mọi lỗi JDBC khi chưa phân loại, vì loại gốc có thể chứa cả lỗi tạm thời, duplicate key và lỗi cấu trúc không thể phục hồi.

## 8. Retry chỉ an toàn khi thao tác có thể lặp lại

Giả sử `registerOrder(orderId)` gửi request tạo đơn hàng tới đối tác. Server đã tạo thành công nhưng response bị timeout:

```text
Batch Processor       Partner API
      | POST order-1       |
      |------------------->|
      |                    | CREATE SUCCESS
      |<-- response lost --X
      |
      | retry POST order-1 |
      |------------------->|
      |                    | CREATE AGAIN?
```

Nếu API không có idempotency, một retry đúng về mặt **loại lỗi** vẫn có thể tạo duplicate. Cần xác định:

1. `orderId` hoặc một key khác có thể làm **idempotency key ổn định** không?
2. API có cam kết rằng cùng key trả về cùng một kết quả hay không?
3. Khi gặp timeout, có cách truy vấn trạng thái giao dịch trước khi gửi lại không?
4. Có thể đặt external call ở bước riêng, sau staging/outbox, để không nằm giữa transaction database đang giữ lock không?
5. Nếu mất kết nối sau khi đã gửi request, trạng thái thực tế là **unknown** chứ không chắc `FAILED`.

Ví dụ contract của gateway được mở rộng:

```java
package com.example.batch;

public interface PartnerGateway {
    String registerOrder(
            String orderId,
            String idempotencyKey);
}
```

Processor có thể tạo idempotency key từ **business identity bất biến**, chẳng hạn `"import-order:" + orderId`, miễn partner đồng ý về format, phạm vi duy nhất và retention của key. **Không dùng timestamp ngẫu nhiên hoặc retry attempt number làm idempotency key**, vì chúng làm mỗi lần retry có định danh khác.

Với Spring Batch, transaction nội bộ của chunk **không tự rollback được tác dụng phụ ở hệ thống ngoài**. Một giải pháp đáng tin cậy hơn trong nhiều hệ thống là:

```text
Chunk transaction:
    validate item
    write staging + outbox event
    COMMIT

Outbox worker:
    send partner request with stable idempotency key
    record confirmed result
    retry transient errors with bounded budget
```

Outbox cũng cần cơ chế xử lý duplicate và trạng thái gửi bất định, nhưng tránh việc retry chunk vô tình gọi external side effect nhiều lần trước commit.

## 9. Retry ở nhiều tầng tạo ra số attempt lớn ngoài dự kiến

Một lỗi cấu hình phổ biến là client HTTP tự retry ba lần, Spring Batch retry ba lần và orchestrator restart job ba lần:

```text
HTTP client attempts: 3
Spring Batch attempts: 3
Orchestrator executions: 3

Worst-case nominal attempts: 3 x 3 x 3 = 27
```

Con số 27 là **minh họa trong trường hợp mỗi tầng đều thực hiện đủ số lần tối đa**, chưa tính rollback, phân mảnh writer hay các hệ thống khác. Nếu item lỗi vĩnh viễn, tất cả 27 lần vẫn thất bại. Nếu có 10.000 item cùng lỗi, tải có thể tăng mạnh.

Nên quyết định **tầng nào sở hữu retry** cho từng loại lỗi:

| Tầng | Vai trò gợi ý | Điều cần tránh |
| --- | --- | --- |
| HTTP/database client | Retry rất ngắn cho lỗi kết nối trước khi gửi hoặc transient phù hợp | Retry mọi HTTP status |
| Spring Batch fault-tolerant step | Retry item/transaction với policy rõ và metadata batch | Retry validation/configuration error |
| Scheduler/orchestrator | Restart execution khi dependency đã phục hồi | Tạo instance mới liên tục, retry không có backoff |
| Manual replay/backfill | Xử lý nguồn sửa hoặc item đã quarantine | Trộn replay với restart cùng checkpoint |

Ngoài số lượt, cần giới hạn **tổng thời gian retry** so với deadline nghiệp vụ. Nếu batch phải hoàn tất trước 04:00, không nên để từng item giữ 30 giây x 3 lần trong khi vài chục nghìn item cùng bị lỗi hệ thống.

## 10. Quyết định skip, quarantine hay fail khi lỗi vĩnh viễn

Không retry là **bước đầu**, chưa phải toàn bộ chiến lược phục hồi. Một item lỗi vĩnh viễn vẫn cần một kết quả rõ ràng:

```text
Permanent failure
      |
      v
Error classifier
      |
      +-- item lỗi nhỏ, được phép loại?
      |        |
      |        +--> YES: SkipListener -> Quarantine -> Reconciliation
      |
      +-- critical item / source-wide error?
      |        |
      |        +--> YES: Step FAILED / no publish
      |
      +-- configuration/system permanent?
               |
               +--> YES: Fail fast + alert / fix config
```

### 10.1. Skip phải có ngân sách

Ví dụ:

```text
Expected source rows: 20.000
Maximum invalid items: 25
Maximum invalid ratio: 0,1%
Critical error: MISSING_ORDER_ID
```

Với 20.000 record, 0,1% tương ứng **20** item. Nếu có 21 invalid items, batch phải bị quality gate từ chối publish dù `skipLimit(25)` chưa vượt. Nếu có một `MISSING_ORDER_ID` critical, vẫn có thể fail dù tổng reject chỉ là 1.

**`skipLimit` của Spring Batch không thay thế quality gate** có tỷ lệ lỗi, kiểm tra manifest, logic critical và đối soát output.

### 10.2. Quarantine thay vì mất dấu bản ghi

Một reject record có thể lưu:

| Trường | Ý nghĩa |
| --- | --- |
| `source_batch_id` | Định danh phiên bản nguồn |
| `record_locator` | ID/offset nguồn ổn định để tìm lại record |
| `stage` | READ / PROCESS / WRITE |
| `reason_code` | Mã lỗi an toàn như INVALID_AMOUNT |
| `job_execution_id` | Lần chạy phát hiện lỗi |
| `payload_pointer` | Đường dẫn tới dữ liệu gốc có kiểm soát truy cập |
| `review_status` | NEW / CORRECTED / REPLAYED / DISMISSED |

Không in nguyên payload hoặc exception message vào log thông thường. Một số exception parse có chứa cả dòng CSV; nếu cần điều tra thì sử dụng kho nguồn/quarantine được bảo vệ.

Ghi quarantine cũng phải đáng tin cậy: nếu reject store thất bại, job không nên âm thầm báo dữ liệu đầu ra đã đạt chất lượng. Nên có transaction/outbox, unique key theo source/version/record và bước reconciliation để kiểm soát việc ghi trùng khi restart.

### 10.3. Không công bố output thiếu một cách âm thầm

Thiết kế flow:

```text
validateSourceStep
        |
        v
importToStagingStep
      /   \
     /     \--> skipped item --> quarantine
    v
reconcileAndQualityGateStep
        |
        +-- không đạt ngưỡng --> FAILED / NOT_PUBLISHED
        |
        v
publishStep
        |
        v
Downstream đọc bản dữ liệu đã được duyệt
```

Một job có thể hoàn thành step import với nhiều item skip trong ngân sách kỹ thuật, nhưng bước gate vẫn từ chối publish nếu tỷ lệ lỗi, các tổng nghiệp vụ hoặc dữ liệu nguồn không đầy đủ. Những chunk đã commit vào staging không tự rollback khi gate thất bại; chúng phải được cô lập theo `source_batch_id` và không hiển thị cho downstream.

## 11. Lưu ý về retry state, rollback và checkpoint

Trong Spring Batch, **retry một item** không phải cùng khái niệm với **restart một job**:

- Retry xảy ra bên trong quá trình xử lý một lần thực thi step theo `RetryPolicy`.
- Rollback có thể làm framework đọc/xử lý/ghi lại một số item; số lần callback thực tế không nhất thiết bằng số item bị lỗi.
- Restart tạo `JobExecution` mới cho cùng `JobInstance` nếu execution trước có thể restart và identifying `JobParameters` được giữ nguyên.
- Replay dữ liệu nguồn đã sửa nên quản lý bằng version nguồn mới và chiến lược idempotency riêng.

Nếu job fail do `PartnerConfigurationException` (chẳng hạn credentials không hợp lệ), quy trình đúng có thể là:

1. **Dừng retry**, báo `FAILED`.
2. Vận hành sửa cấu hình/secret.
3. Xác minh dependency sẵn sàng.
4. **Restart** cùng identifying parameters nếu job và nguồn cho phép, sử dụng `JobRepository` bền vững.
5. Đối soát output và side effect đã xảy ra trước khi lỗi.

Không tự thay `run.id` identifying chỉ để “thử lại” job đã fail: đổi tham số nhận diện có thể tạo một instance mới, làm mất ý nghĩa checkpoint và gây duplicate. Ngược lại, nếu sửa file nguồn từ v1 sang v2, không nên restart với checkpoint của file v1 mà giả định các offset không đổi.

### 11.1. `noRollback` không có nghĩa không retry

Trong một số cấu hình lỗi validation, có thể cân nhắc chính sách `noRollback` để giảm rollback không cần thiết ở processor. Tuy nhiên `noRollback(...)`, `noRetry(...)` và `skip(...)` là **ba điều khiển khác nhau**:

- `noRetry`: không thử lại lỗi thuộc loại chỉ định.
- `skip`: cho phép item bị bỏ qua nếu còn ngân sách.
- `noRollback`: ảnh hưởng đến cách giao dịch rollback trước exception thuộc loại chỉ định, tùy vị trí lỗi và cấu hình step.

Không thêm `noRollback` chỉ để tăng performance mà chưa xác minh transactional consistency, nhất là với writer có side effect. Phần lớn bài toán “retry lỗi permanent” nên được giải quyết trước bằng **exception classification** và retry allowlist.

## 12. Logging và metric: nhìn thấy retry sai loại

Một hệ thống vận hành cần trả lời: có bao nhiêu attempt retry? Loại lỗi nào chiếm ưu thế? Bao nhiêu item cuối cùng bị reject? Job fail vì lý do dữ liệu hay hạ tầng?

| Chỉ số | Dùng để nhận biết |
| --- | --- |
| `retry_attempts_total` theo job/step/error code | Retry đang tăng mạnh ở loại lỗi nào |
| `retry_exhausted_total` | Bao nhiêu thao tác hết ngân sách retry |
| `readSkipCount` | Lỗi đọc được skip |
| `processSkipCount` | Item bị skip tại processor |
| `writeSkipCount` | Item bị skip tại writer |
| `filterCount` | Item bị processor filter, không phải skip |
| `rollbackCount` | Số rollback của step |
| `job_duration` | Job có trễ run window/deadline do retry không |
| `quarantine_pending` | Số reject còn cần sửa |
| `quality_gate_status` | Output có được phép publish không |

`StepExecution` có sẵn nhiều counter như `getSkipCount()`, `getProcessSkipCount()` và `getRollbackCount()`, **không có nghĩa framework tự cung cấp một “attempt count của từng item” phù hợp mọi loại retry**. Nếu muốn đo retry attempts cụ thể, có thể quan sát qua listener hoặc metric được tích hợp với retry mechanism. Không lấy số exception log làm số item thất bại cuối.

Một log có cấu trúc nên có các field an toàn:

```text
event=batch_item_retry
job=importOrdersJob
step=importOrdersStep
job_execution_id=8521
stage=process
error_code=PARTNER_UNAVAILABLE
attempt=2
```

Nếu item thật sự bị skip:

```text
event=batch_item_skipped
job=importOrdersJob
stage=process
item_ref=b99c60d44e81a247
reason_code=INVALID_AMOUNT
```

Tránh `log.error("failed item {}", item, exception)` nếu record có dữ liệu nhạy cảm; `toString()` và message/stack trace của exception có thể lộ payload, SQL parameters hoặc API response. Dùng `item_ref` được bảo vệ và error code allowlist; đừng đặt item ID làm metric label có cardinality cao.

### 12.1. Alert khi retry storm xuất hiện

Ví dụ quy tắc vận hành:

```text
WARN:
  retry attempts / minute tăng gấp 5 lần baseline

CRITICAL:
  error_code=INVALID_AMOUNT xuất hiện trong retry metrics
  OR retry_exhausted tăng liên tục nhiều phút
  OR Partner API 503 lan ra > 50% items trong cửa sổ
```

Đây là ngưỡng minh họa. Điều quan trọng là phát hiện **permanent error đang bị retry**, vì đó thường là dấu hiệu retry policy hoặc exception mapping bị cấu hình sai. Với outage diện rộng, cần có cách fail/stop có kiểm soát chứ không để hàng nghìn item retry đồng loạt.

## 13. Kiểm thử không retry lỗi permanent

Không nên chỉ viết test “job `COMPLETED`” mà bỏ qua số lần gọi processor/gateway. Mục tiêu là chứng minh:

1. Item sai dữ liệu **không gọi API** và không retry.
2. Lỗi tạm thời được thử lại trong giới hạn rồi thành công.
3. Lỗi cấu hình không bị skip hoặc retry hàng loạt.
4. Khi hết ngân sách retry, step/job thất bại theo đúng policy.
5. Skip và quarantine không biến dữ liệu lỗi thành mất dữ liệu im lặng.

### 13.1. Test đơn vị: validation sai không gọi gateway

```java
package com.example.batch;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

class OrderProcessorTest {

    @Test
    void invalidAmountFailsBeforeGatewayCall() {
        PartnerGateway gateway = Mockito.mock(PartnerGateway.class);
        OrderProcessor processor = new OrderProcessor(gateway);

        IncomingOrder invalid = new IncomingOrder("o-001", "not-a-number");

        assertThatThrownBy(() -> processor.process(invalid))
                .isInstanceOf(InvalidOrderException.class)
                .hasMessage("INVALID_AMOUNT");

        verifyNoInteractions(gateway);
    }
}
```

Đây là **unit test processor**, chỉ xác nhận validation trước gateway. Nó chưa kiểm tra retry policy của Spring Batch, vì retry nằm ở fault-tolerant step, không tự hoạt động khi gọi trực tiếp `processor.process(...)`.

### 13.2. Test gateway có lỗi tạm thời theo kịch bản xác định

Một stub dùng bộ đếm để mô phỏng hai lần lỗi rồi thành công:

```java
package com.example.batch;

import java.util.concurrent.atomic.AtomicInteger;

public class ScriptedPartnerGateway implements PartnerGateway {

    private final AtomicInteger calls = new AtomicInteger();

    @Override
    public String registerOrder(String orderId) {
        int current = calls.incrementAndGet();
        if (current <= 2) {
            throw new TransientPartnerException("PARTNER_UNAVAILABLE");
        }
        return "partner-ref-ok";
    }

    public int callCount() {
        return calls.get();
    }
}
```

Nếu dùng bean stub này trong một **integration test chạy đúng Spring Batch step**, với `retryLimit(3)` và không có rollback/restart phụ làm tăng số lần ngoài kịch bản, item có thể thành công ở lần thứ ba. Vì các callback có thể phát sinh thêm trong các tình huống transaction phức tạp, test cần cô lập nguồn dữ liệu, transaction, step và policy; không lấy unit test thuần `OrderProcessor` làm bằng chứng retry đã được cấu hình.

### 13.3. Integration test với `@SpringBatchTest`

Trong dự án Gradle dùng Spring Boot, các dependency test thường gồm:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}
```

Một bộ test Spring Batch có thể dùng `JobLauncherTestUtils` và `JobRepositoryTestUtils` với database test riêng:

```java
@SpringBatchTest
@SpringBootTest(properties = {
    "spring.batch.job.enabled=false",
    "spring.batch.jdbc.initialize-schema=always"
})
class RetryClassificationIT {

    @Autowired
    JobLauncherTestUtils launcher;

    @Test
    void invalidInputIsSkippedWithoutRetries() throws Exception {
        // Arrange:
        // - Reader trả một IncomingOrder(amountText="bad").
        // - Processor và gateway được instrument để đếm attempts.
        // - Step dùng retry allowlist và skipLimit từ phần 6.
        // - Writer/quarantine chạy trên database test riêng.

        JobExecution execution = launcher.launchJob(testParameters());

        // Assert:
        // - Job/step có trạng thái phù hợp hợp đồng test.
        // - processSkipCount == 1.
        // - gatewayCallCount == 0.
        // - reject record được ghi đúng một lần.
        // - Không có retry event cho INVALID_AMOUNT.
    }
}
```

Đây là **khung test minh họa**: các field của test, bean cấu hình và phương thức `testParameters()` phải được dự án định nghĩa để test có thể chạy. Mục tiêu là chỉ rõ những assertion cần có thay vì đưa ra một đoạn test giả định đã đủ các dependency và fixture.

Có thể mở rộng bằng ma trận:

| Kịch bản | Retry dự kiến | Kết quả cuối |
| --- | --- | --- |
| `INVALID_AMOUNT` ở processor | 0 lần retry | Skip/quarantine nếu policy cho phép |
| `MISSING_ORDER_ID` critical | 0 lần retry | Fail hoặc quality gate từ chối publish |
| Partner timeout 2 lần, lần 3 thành công | Có retry trong giới hạn | Item được ghi |
| Partner 503 liên tục | Retry hữu hạn | Step `FAILED` khi exhausted và không skip |
| Partner 401 credentials sai | 0 lần retry | Fail fast, báo cấu hình |
| HTTP 409 do order đã được tạo trước | Theo contract idempotency, không retry mù | Xác minh trạng thái và tránh duplicate |
| CSV header sai toàn file | Không retry từng dòng | Preflight `FAILED` |
| DB duplicate key do record đã ghi từ trước | Không retry mù | Đối soát/upsert hoặc lỗi đã phân loại |
| Lỗi writer làm rollback chunk | Theo transaction/retry policy | Không xuất bản snapshot chưa đủ |
| Job restart sau sửa config | Không đổi identifying params | Không duplicate, kiểm tra checkpoint |

### 13.4. Test lỗi exception bị bọc

Trong ứng dụng thật, client có thể ném `CompletionException` chứa `InvalidOrderException` hoặc `TransientPartnerException`. Nếu adapter bọc **mọi lỗi** thành `RuntimeException`, fault-tolerance classifier có thể hiểu sai. Cần test việc adapter trả đúng loại exception mà step xử lý hoặc cấu hình classifier được kiểm thử cho exception chain cụ thể.

Đừng mặc định Spring Batch sẽ tự phân tích mọi nested cause theo ý muốn của ứng dụng. Hãy thiết kế một ranh giới chuyển đổi lỗi tường minh và kiểm thử đường từ HTTP/JDBC response tới exception mà step nhận.

## 14. Sự cố thực tế và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| Một item sai parse được xử lý nhiều lần | `.retry(Exception.class)` hoặc `.retry(RuntimeException.class)` | Retry allowlist cho exception tạm thời, validate và skip/fail permanent |
| Job chậm đột ngột, log lỗi tăng hàng loạt | Retry storm do file sai schema | Preflight header/manifest, giới hạn skip và fail fast |
| HTTP 401 được retry cho mọi item | Adapter ánh xạ mọi HTTP error thành transient | Phân loại auth/config lỗi permanent và fail |
| Item hợp lệ bị skip khi đối tác 503 | `.skip(Exception.class)` hoặc `.skip(TransientPartnerException.class)` quá rộng | Không skip outage; retry hữu hạn rồi fail/stop |
| Job có `COMPLETED` nhưng output thiếu nhiều item | Skip limit lớn, không có quality gate | Quarantine, count reconciliation, publish gate |
| API nhận nhiều lệnh tạo cùng một order | External call không idempotent | Stable idempotency key, query status hoặc outbox |
| Retry ba lần nhưng API nhận chín request | HTTP client và batch cùng retry | Chọn tầng sở hữu retry, budget chung |
| Một item bị log ERROR ba lần nhưng vẫn thành công | Attempt logging không phân biệt final outcome | Dùng event `retry_attempt`, `skipped`, `failed` rõ nghĩa |
| Retry mãi sau khi sửa config vẫn thất bại | Job không reload cấu hình/secret, source không hợp lệ | Dừng execution, sửa config, restart có kiểm soát |
| Restart xử lý lại toàn bộ file | Đổi `run.id` hoặc mất `JobRepository` | Giữ identifying params và metadata bền vững |
| Exception chưa phân loại bị skip | Policy dùng superclass quá rộng | Fail unknown errors và bổ sung classifier sau điều tra |
| Retry hết hạn nhưng scheduler vẫn báo thành công | Exit code của JVM không phản ánh status job | Ánh xạ `JobExecution`/ExitStatus sang process exit code phù hợp |

## 15. Quy trình vận hành khi phát hiện retry lỗi vĩnh viễn

Khi dashboard báo lượng retry bất thường, có thể xử lý theo chuỗi:

1. **Xác định lỗi nổi trội** theo `job`, `step`, `error_code`, thời gian, tỷ lệ lỗi và số attempt; không đọc thô payload nhạy cảm trong log phổ thông.
2. **Phân loại nguyên nhân**: input item, nguồn toàn file, cấu hình, API, database hay bug code.
3. **Đánh giá side effect** đã xảy ra ở writer/API và khả năng duplicate khi retry.
4. **Ngăn retry storm** bằng policy fail/stop có kiểm soát, giảm concurrency hoặc mở circuit breaker nếu dependency outage.
5. **Sửa đúng nơi**: sửa nguồn/schema/config hoặc mapper ngoại lệ, không chỉ tăng `retryLimit`.
6. **Xác định đường phục hồi**: restart cùng instance khi nguồn và checkpoint vẫn phù hợp; replay nguồn phiên bản mới nếu item đã được sửa; quarantine item lỗi được phép loại.
7. **Đối soát output** với input, accepted/rejected/filtered và nguồn ngoài trước khi publish.
8. **Bổ sung test hồi quy** bảo đảm loại lỗi permanent đó không bị retry trong những lần triển khai sau.

Không nên tự xóa metadata `BATCH_*`, thay `JobExecution` status bằng SQL thủ công hoặc sửa identifying parameters ngẫu nhiên chỉ để job “chạy được”. Những cách này dễ phá checkpoint và làm mất khả năng giải thích lịch sử xử lý.

## 16. Bài thực hành

Hãy tạo `importOrdersJob` với các fixture sau:

```csv
order_id,amount
o-001,150.00
o-002,not-a-number
o-003,-10.00
o-004,25.00
o-005,80.00
```

`o-002` và `o-003` là lỗi dữ liệu permanent. Gateway đối tác được cấu hình cho `o-004` timeout hai lần rồi thành công; `o-005` trả `PARTNER_UNAVAILABLE` liên tục. Mục tiêu:

1. Viết processor validate amount trước khi gọi gateway; lỗi permanent ném `InvalidOrderException` với reason code cố định.
2. Cấu hình step chỉ `.retry(TransientPartnerException.class)`, `.retryLimit(3)` và `.skip(InvalidOrderException.class)` với giới hạn phù hợp.
3. Dùng stub/counter chứng minh `o-002`, `o-003` không gọi gateway và không phát sinh retry attempt.
4. Chứng minh `o-004` có thể phục hồi khi lỗi tạm thời trong ngân sách; phân biệt số retry với số item bị skip.
5. Cho `o-005` lỗi liên tục, xác nhận job/step thất bại khi retry exhausted thay vì âm thầm skip.
6. Thay gateway trả `PartnerConfigurationException` (auth sai), xác nhận fail fast và không retry mỗi item.
7. Dùng một `SkipListener` ghi reject vào quarantine, rồi đối soát số accepted, rejected và filtered theo manifest.
8. Cho writer/partner mất response sau khi đã tạo thành công, kiểm tra idempotency key hoặc outbox ngăn xử lý trùng.
9. Mô phỏng nhiều item lỗi permanent cùng lúc. So sánh số attempt và duration giữa retry allowlist với cấu hình thử nghiệm quá rộng; không đưa cấu hình quá rộng vào production.
10. Tạo lỗi cấu hình khiến job `FAILED`, sửa cấu hình rồi restart bằng cùng identifying parameters; kiểm tra không tạo duplicate và dữ liệu chỉ được publish khi quality gate đạt.

**Điểm cốt lõi:** retry là phản ứng với **điều kiện có khả năng thay đổi**, không phải cách sửa dữ liệu hoặc cấu hình sai. Với Spring Batch, hãy **phân loại lỗi ở ranh giới rõ ràng**, chỉ retry exception tạm thời trong ngân sách hữu hạn, **không retry lỗi permanent**, quyết định skip/quarantine hay fail theo hợp đồng dữ liệu, và đảm bảo retry/restart không gây side effect trùng. Khi đó batch mới thực sự chịu lỗi mà không che giấu lỗi hoặc làm giảm độ tin cậy của dữ liệu đầu ra.
