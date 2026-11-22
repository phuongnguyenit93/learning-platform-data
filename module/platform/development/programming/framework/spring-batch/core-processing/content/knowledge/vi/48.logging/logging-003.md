# Log item lỗi an toàn trong Spring Batch

Khi một batch job xử lý hàng nghìn hoặc hàng triệu bản ghi, việc biết **item nào thất bại, lỗi xảy ra ở step nào và có được retry/skip hay không** rất quan trọng để điều tra sự cố. Tuy nhiên, ghi thẳng toàn bộ item hoặc exception vào log có thể làm lộ thông tin khách hàng, số tài khoản, token, dữ liệu đơn hàng, nội dung file và các trường nhạy cảm khác. Log thường được chuyển tiếp sang hệ thống tập trung, lưu lâu hơn dữ liệu gốc và có nhiều người có quyền truy cập hơn.

Bài học thuộc **Spring Batch Core Processing → Logging**, hướng dẫn cách **log item lỗi an toàn** khi đọc, xử lý và ghi dữ liệu; xây dựng event có cấu trúc, nhận diện item bằng mã tham chiếu bảo vệ, chọn đúng listener theo trạng thái retry/skip, ngăn exception làm lộ payload, kiểm thử các trường dữ liệu cấm xuất hiện trong log và vận hành hệ thống log có kiểm soát.

Ví dụ dùng **Java 17, Spring Boot 3.x, Spring Batch 5.x, SLF4J và JUnit 5**. Tên class nghiệp vụ và chính sách dữ liệu minh họa phải được điều chỉnh theo ứng dụng thực tế.

## 1. Mục tiêu của log lỗi an toàn

Một dòng log tốt cần trả lời:

1. **Lỗi xảy ra ở đâu?** Job, step, giai đoạn `read`/`process`/`write`.
2. **Lỗi thuộc nhóm nào?** Mã lỗi ổn định, có thể thống kê, như `INVALID_ORDER`, `REMOTE_TIMEOUT`.
3. **Lần thực thi nào bị ảnh hưởng?** `JobExecutionId`, ngày nghiệp vụ hoặc correlation ID đã được cho phép ghi.
4. **Item nào cần điều tra?** Mã tham chiếu hoặc token có kiểm soát để tra cứu trong kho dữ liệu được cấp quyền.
5. **Kết quả xử lý ra sao?** Một lần retry, một item bị skip, hay toàn bộ step/job đã failed.

Đồng thời, log phải **không** cho phép tái tạo thông tin bí mật từ nội dung được ghi.

Ví dụ cách ghi có rủi ro:

```java
log.error("Failed order: {}", order);
log.error("Cannot process order {}", order, error);
log.warn("Customer email={}, card={}",
        order.customerEmail(), order.cardNumber());
```

Với Java `record`, `toString()` có thể in tất cả field. Với exception, `getMessage()`, `toString()` hoặc stack trace có thể chứa câu SQL, tham số truy vấn, HTTP URL hay response body nhạy cảm. Việc dùng placeholder `{}` của SLF4J **không tự động làm dữ liệu trở nên an toàn**.

Một log an toàn hơn:

```text
event=batch_item_skipped
job=dailyOrdersJob
step=validateOrdersStep
stage=process
business_date=2026-11-16
record_ref=8a62b97f4d21d5a7
error_code=INVALID_ORDER
```

`record_ref` ở ví dụ là mã tham chiếu đã được bảo vệ, **không phải** mã khách hàng hoặc nội dung dữ liệu gốc. Để điều tra chi tiết, người có quyền sử dụng token này trong công cụ tra cứu bảo mật hoặc tìm lại item từ nguồn gốc.

## 2. Phân loại dữ liệu trước khi đưa vào log

Quy tắc quan trọng nhất là **allowlist**: chỉ cho phép những trường đã được thẩm định đi vào log. Không lấy một object có nhiều trường rồi cố xóa vài trường nhạy cảm bằng blacklist.

| Dữ liệu | Cách xử lý đề xuất | Lý do |
| --- | --- | --- |
| Tên job/step cố định | Có thể log | Giúp khoanh vùng luồng lỗi |
| `JobExecutionId`, `StepExecutionId` | Có thể log theo chính sách nội bộ | Trỏ tới metadata batch |
| Mã lỗi cố định như `INVALID_ORDER` | Có thể log | Hỗ trợ tìm kiếm và thống kê |
| Giai đoạn `read`, `process`, `write` | Có thể log | Phân biệt vị trí lỗi |
| `businessDate`, `region` | Chỉ khi được phê duyệt và đã chuẩn hóa | Một số hệ thống coi tham số nghiệp vụ là nhạy cảm |
| ID bản ghi, customer ID, order ID | Cân nhắc token hóa/HMAC hoặc dùng ID công khai đã được phê duyệt | ID cũng có thể là dữ liệu cá nhân hoặc cho phép liên kết người dùng |
| Email, số điện thoại, địa chỉ, số tài khoản | Không ghi nguyên văn | Có thể xác định hoặc liên kết cá nhân |
| Mật khẩu, API key, access token, secret | Không log | Rủi ro lộ quyền truy cập |
| Nội dung CSV/JSON/XML, SQL parameter, HTTP body | Không log nguyên văn | Thường chứa nhiều trường chưa được phân loại |
| `Throwable.getMessage()`, raw stack trace | Chỉ đưa vào kênh được kiểm soát sau khi có biện pháp bảo vệ phù hợp | Exception thường mang theo input hoặc nội dung từ hệ thống khác |

### 2.1. Vì sao chỉ che một phần chuỗi chưa chắc đủ?

Ví dụ `email=a***@example.com` vẫn có thể giúp nhận diện người dùng nếu kết hợp với ngày, khu vực và ID khác. Tương tự, dùng `hashCode()`, MD5 hoặc SHA-256 trực tiếp trên email có thể bị dò ngược theo từ điển vì không gian giá trị email, số điện thoại hay ID có thể đoán được.

Nếu cần một mã ổn định để đối chiếu item giữa các dòng log, có thể dùng **HMAC-SHA-256 với khóa bí mật được quản lý riêng**, cắt ngắn một phần digest đủ dài cho quy mô dữ liệu, và kiểm soát quyền sử dụng khóa. HMAC giúp khó dò ra giá trị gốc hơn hash không khóa; tuy nhiên nó vẫn là **dữ liệu có thể liên kết** và phải chịu quy tắc lưu trữ, truy cập và thời hạn giữ log. Nếu không cần đối chiếu item, bỏ hẳn tham chiếu có thể là lựa chọn tốt hơn.

## 3. Thiết kế một sự kiện lỗi có cấu trúc

Nên định nghĩa một schema log rõ ràng thay cho những câu tự do chứa nguyên văn lỗi:

```json
{
  "event": "batch_item_skipped",
  "job": "dailyOrdersJob",
  "step": "validateOrdersStep",
  "job_execution_id": 78241,
  "stage": "process",
  "business_date": "2026-11-16",
  "record_ref": "8a62b97f4d21d5a7",
  "error_code": "INVALID_ORDER",
  "outcome": "SKIPPED"
}
```

Đây là **mẫu dữ liệu minh họa**, không phải output mặc định mà Spring Batch tự tạo. Có thể triển khai bằng JSON layout/structured logging hoặc thông điệp `key=value` với field cố định.

Các thuộc tính thiết kế:

- **Tên trường nhất quán:** luôn dùng `event`, `stage`, `error_code`, `record_ref` thay vì mỗi step đặt một kiểu.
- **Giá trị enum/allowlist:** chỉ dùng những giá trị an toàn như `PROCESS`, `READ`, `WRITE`, `INVALID_ORDER`, `REMOTE_TIMEOUT`, tránh đưa free text chưa kiểm duyệt.
- **Tham chiếu tối thiểu:** chỉ bổ sung `record_ref` khi cần truy vết item và có cơ chế xác minh quyền tra cứu.
- **Thông tin execution:** dùng ID trong `JobRepository` để liên kết log với lịch sử batch, không dump toàn bộ `JobParameters`.
- **Phân biệt event:** `batch_item_retry`, `batch_item_skipped`, `batch_step_failed`, `batch_step_completed` có ngữ nghĩa khác nhau.

Nếu log được đưa vào hệ thống metrics, **không sử dụng `record_ref`, `JobExecutionId` hoặc message exception làm label/tag**: số lượng giá trị quá lớn làm tăng cardinality, chi phí lưu trữ và có thể tiết lộ dữ liệu. Metrics nên tổng hợp theo `job`, `step`, `stage`, `error_code`.

## 4. Chọn đúng thời điểm log trong vòng đời chunk

Trong Spring Batch, lỗi có thể xuất hiện lúc `ItemReader.read()`, `ItemProcessor.process()` hoặc `ItemWriter.write(...)`. Với `faultTolerant()` và chính sách retry/skip, một exception ban đầu **không nhất thiết làm job thất bại**.

| Callback / cơ chế | Khi nào gọi | Nên ghi thông tin gì? |
| --- | --- | --- |
| `ItemReadListener.onReadError(Exception)` | Lần đọc phát sinh lỗi | Sự kiện thử đọc lỗi, mã lỗi an toàn; chưa chắc có ID item |
| `ItemProcessListener.onProcessError(item, exception)` | Một lần processor lỗi | Sự kiện attempt thất bại, tránh kết luận item đã bị skip |
| `ItemWriteListener.onWriteError(exception, chunk)` | Một lần writer lỗi | Sự kiện lần ghi thất bại; chú ý chunk có thể gồm nhiều item |
| `SkipListener.onSkipInRead(Throwable)` | Framework quyết định bỏ qua lỗi đọc | Sự kiện skip ở pha read, thường không có item |
| `SkipListener.onSkipInProcess(item, Throwable)` | Một item bị skip ở processor | Sự kiện skip của item và mã tham chiếu bảo vệ |
| `SkipListener.onSkipInWrite(item, Throwable)` | Một item bị skip ở writer | Sự kiện skip của item và mã tham chiếu bảo vệ |
| `StepExecutionListener.afterStep(stepExecution)` | Step đã kết thúc | Tổng hợp `readCount`, `writeCount`, `skipCount`, `rollbackCount`, trạng thái |
| `JobExecutionListener.afterJob(jobExecution)` | Job đã kết thúc | Kết quả tổng thể, execution ID, trạng thái và mã lỗi tổng hợp |

**Không đánh đồng “một attempt thất bại” với “một item đã bị skip”.** Ví dụ một API timeout ở lần đầu, retry lần hai thành công; nếu log ở `onProcessError`, có event xử lý lỗi dù item cuối cùng được ghi thành công. Nếu mục tiêu là danh sách item bị bỏ qua cuối cùng, dùng `SkipListener` phù hợp hơn.

Với fault-tolerant step, Spring Batch gọi `SkipListener` theo cơ chế dành cho item bị skip, thường ngay trước commit của transaction liên quan. Tuy nhiên, **log không nằm trong transaction nghiệp vụ**: khi transaction rollback, thông điệp đã gửi tới hệ thống log không tự rollback. Không thiết kế báo cáo kế toán hay thông tin cần chính xác tuyệt đối dựa vào việc đếm số dòng log.

```text
Item → process
          |
          ├── attempt 1: lỗi tạm thời → retry diagnostic (nếu bật)
          ├── attempt 2: thành công   → writer
          |                               └── không có skip
          |
          └── lỗi không khôi phục / hết giới hạn retry
                                      |
                            skip được cấu hình?
                             |           |
                            Có          Không
                             |           |
                        SkipListener    Step FAILED
```

## 5. Tạo mã tham chiếu item bằng HMAC thay vì log ID gốc

Ví dụ mô hình đầu vào cho một job xử lý đơn hàng:

```java
package com.example.batch;

import java.math.BigDecimal;

record OrderInput(
        String orderId,
        String customerEmail,
        BigDecimal amount) {}

record OrderOutput(
        String orderId,
        BigDecimal approvedAmount) {}
```

**Không gọi `log.info("{}", order)` trên hai record này**: `record.toString()` sẽ đưa toàn bộ thành phần vào log. Ta chỉ dùng `orderId` ở trong code để tính token, còn output log không chứa giá trị gốc.

File `SafeRecordToken.java`:

```java
package com.example.batch;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class SafeRecordToken {

    private final SecretKeySpec secretKey;

    public SafeRecordToken(byte[] keyBytes) {
        if (keyBytes == null || keyBytes.length < 32) {
            throw new IllegalArgumentException(
                    "HMAC key must contain at least 32 bytes");
        }
        this.secretKey = new SecretKeySpec(
                keyBytes.clone(), "HmacSHA256");
    }

    public String fromIdentifier(String identifier) {
        if (identifier == null || identifier.isBlank()) {
            return "unavailable";
        }
        try {
            // Tạo Mac mới cho mỗi lần gọi: Mac không thread-safe.
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(secretKey);
            byte[] digest = mac.doFinal(
                    identifier.getBytes(StandardCharsets.UTF_8));

            // 12 byte đầu = 96 bit; chọn độ dài theo quy mô sử dụng.
            return HexFormat.of().formatHex(digest, 0, 12);
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException(
                    "Could not calculate record reference");
        }
    }
}
```

Mỗi `orderId` cho ra cùng một token khi dùng cùng khóa, giúp truy vết mà không in ID gốc. 96 bit được dùng làm ví dụ có không gian lớn cho phần lớn nhu cầu đối chiếu log; vẫn cần đánh giá va chạm, khối lượng bản ghi và chính sách bảo mật cụ thể.

Vận hành cần:

- Tạo khóa ngẫu nhiên đủ mạnh trong secret manager; **không hardcode** khóa vào source hoặc test fixture sản xuất.
- Không log khóa, giá trị cấu hình hay HMAC input.
- Giới hạn phạm vi sử dụng khóa và quyền tra cứu token; phân biệt môi trường test/production.
- Có kế hoạch rotation: đổi khóa sẽ làm token của cùng ID thay đổi. Nếu cần tra cứu log qua nhiều đợt rotation, ghi **phiên bản khóa không nhạy cảm** trong schema log và có công cụ đối chiếu được kiểm soát.
- Cân nhắc thêm định danh không gian (`tenant`, `job`) vào dữ liệu đầu vào HMAC để không liên kết cùng một ID qua các hệ thống ngoài ý muốn.

HMAC **không mã hóa** ID và không phải cơ chế cho phép giải mã. Muốn tra cứu chi tiết từ token, phải có một công cụ có quyền truy cập dữ liệu nguồn và cùng thuật toán/khóa để đối chiếu, hoặc lưu bản ánh xạ bảo vệ trong kho riêng.

## 6. Chỉ phân loại exception thành mã lỗi an toàn

Các exception phát sinh từ JDBC, HTTP hoặc business validation có thể chứa payload gốc trong `getMessage()`. Thay vì log message, ta xây dựng classifier chỉ trả về những mã lỗi được định nghĩa trước.

```java
package com.example.batch;

final class InvalidOrderException extends RuntimeException {
    InvalidOrderException(String detail) {
        super(detail);
    }
}

final class TemporaryPartnerException extends RuntimeException {
    TemporaryPartnerException(String detail) {
        super(detail);
    }
}

public final class SafeErrorCodes {
    private SafeErrorCodes() {}

    public static String of(Throwable error) {
        Throwable current = error;

        // Kiểm tra vài lớp wrapper có kiểm soát.
        for (int depth = 0; depth < 4 && current != null; depth++) {
            if (current instanceof InvalidOrderException) {
                return "INVALID_ORDER";
            }
            if (current instanceof TemporaryPartnerException) {
                return "PARTNER_TEMPORARY_FAILURE";
            }
            current = current.getCause();
        }

        return "UNCLASSIFIED_FAILURE";
    }
}
```

Code trên cố ý **không trả về** `error.getMessage()`, class name không được duyệt hoặc nội dung lỗi SQL/HTTP. Với lỗi thực tế, có thể mở rộng map theo exception type đã được kiểm duyệt, SQLState hay HTTP status code nếu những trường đó được xác nhận an toàn. Lỗi chưa biết đi vào mã chung `UNCLASSIFIED_FAILURE`, đồng thời được theo dõi trong kênh điều tra thích hợp.

Nếu cần stack trace để chẩn đoán sâu, không nên chỉ bật `log.error(..., exception)` trên cùng logger phổ thông. Nên sử dụng kênh restricted với thời hạn lưu ngắn, quyền truy cập hạn chế và cơ chế loại bỏ dữ liệu nhạy cảm; ngay cả stack trace cũng phải được đánh giá vì một số exception chứa request/response hoặc thông tin truy vấn.

## 7. Log item bị skip bằng `SkipListener`

Với Spring Batch 5, `SkipListener<I, O>` có ba callback cho các pha đọc, xử lý và ghi. Một implementation an toàn:

```java
package com.example.batch;

import java.time.LocalDate;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.SkipListener;

public final class SafeOrderSkipListener
        implements SkipListener<OrderInput, OrderOutput> {

    private static final Logger log =
            LoggerFactory.getLogger(SafeOrderSkipListener.class);

    private final SafeRecordToken recordToken;
    private final String businessDate;

    public SafeOrderSkipListener(
            SafeRecordToken recordToken, String businessDate) {
        this.recordToken = recordToken;
        // Chuẩn hóa ngày theo ISO, tránh đưa chuỗi CLI tùy ý vào log.
        this.businessDate = LocalDate.parse(businessDate).toString();
    }

    @Override
    public void onSkipInRead(Throwable error) {
        // Không có item đáng tin cậy để lấy ID trong callback này.
        logSkip("read", "unavailable", error);
    }

    @Override
    public void onSkipInProcess(OrderInput item, Throwable error) {
        logSkip("process",
                recordToken.fromIdentifier(item.orderId()), error);
    }

    @Override
    public void onSkipInWrite(OrderOutput item, Throwable error) {
        logSkip("write",
                recordToken.fromIdentifier(item.orderId()), error);
    }

    private void logSkip(
            String stage, String reference, Throwable error) {

        // Không truyền item hoặc Throwable vào logger.
        log.warn(
                "event=batch_item_skipped job=dailyOrdersJob "
                + "step=validateOrdersStep business_date={} "
                + "stage={} record_ref={} error_code={}",
                businessDate,
                stage,
                reference,
                SafeErrorCodes.of(error));
    }
}
```

Các `stage`, `job`, `step` trong ví dụ là giá trị cố định. Nếu ứng dụng có nhiều job/step, hãy cung cấp tên qua cấu hình hoặc metadata đã được chuẩn hóa, thay vì ghi trực tiếp một tham số không kiểm soát của người dùng. Nếu cần `jobExecutionId`, có thể lấy từ `StepExecution` trong step context hoặc truyền qua một listener theo đúng scope; **không đặt `StepExecution` mutable của nhiều lượt chạy vào một singleton rồi chia sẻ giữa các job song song**.

`onSkipInRead` khác `onSkipInProcess` và `onSkipInWrite`: khi lỗi đọc xảy ra, reader chưa chắc trả về một item, nên callback không nhận ID. Tự log dòng dữ liệu thô, file line hoặc input buffer ở đây có thể làm lộ dữ liệu; có thể log tên resource đã được kiểm duyệt và vị trí kỹ thuật được cho phép nếu reader hỗ trợ.

### 7.1. Gắn listener vào fault-tolerant step

Ví dụ cấu hình bean để dùng trong một job:

```java
package com.example.batch;

import java.util.Base64;

import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class OrdersStepConfig {

    @Bean
    SafeRecordToken safeRecordToken(
            @Value("${batch.logging.hmac-key-base64}") String keyBase64) {
        return new SafeRecordToken(
                Base64.getDecoder().decode(keyBase64));
    }

    @Bean
    @StepScope
    SafeOrderSkipListener safeOrderSkipListener(
            SafeRecordToken token,
            @Value("#{jobParameters['businessDate']}")
            String businessDate) {
        return new SafeOrderSkipListener(token, businessDate);
    }

    @Bean
    Step validateOrdersStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ItemReader<OrderInput> reader,
            ItemProcessor<OrderInput, OrderOutput> processor,
            ItemWriter<OrderOutput> writer,
            SafeOrderSkipListener skipListener) {

        return new StepBuilder("validateOrdersStep", jobRepository)
                .<OrderInput, OrderOutput>chunk(100, transactionManager)
                .reader(reader)
                .processor(processor)
                .writer(writer)
                .faultTolerant()
                .retry(TemporaryPartnerException.class)
                .retryLimit(3)
                .skip(InvalidOrderException.class)
                .skipLimit(20)
                .listener(skipListener)
                .build();
    }
}
```

`ItemReader`, `ItemProcessor`, `ItemWriter` ở đây là các bean nghiệp vụ **giả định đã được cung cấp** trong ứng dụng. Tên job `dailyOrdersJob` được đặt trong listener cần khớp với job thực tế của ví dụ.

Tham số cấu hình khóa HMAC có thể khai báo:

```properties
# Chỉ chứa tên biến môi trường tham chiếu; không đưa giá trị secret vào Git.
batch.logging.hmac-key-base64=${BATCH_LOG_REF_KEY_B64}
```

Biến môi trường cần được cấp từ secret manager hoặc cơ chế quản lý secret của hạ tầng. Với Spring Boot, cần kiểm soát endpoint cấu hình/actuator và quyền đọc environment để không lộ khóa. Trong một hệ thống bảo mật cao, nên cấp khóa qua một secret provider có kiểm soát và giới hạn việc giữ key trong bộ nhớ.

Cấu hình ví dụ có hai chính sách khác nhau:

- `TemporaryPartnerException` được **retry** tối đa ba lần thử, tính cả lần đầu. Nếu cuối cùng xử lý thành công, không có event skip cho item đó.
- `InvalidOrderException` được phép **skip** tối đa 20 item theo policy. Khi item thực sự bị skip, `SafeOrderSkipListener` ghi event an toàn.

Khi không thể retry/skip theo chính sách, step có thể `FAILED`. Không nên cố bắt mọi exception rồi trả về `null` để “job vẫn chạy”: như vậy dễ đánh mất trạng thái lỗi và không phân biệt được item đã bị loại với dữ liệu hợp lệ.

## 8. Logging khi retry, fail và rollback

### 8.1. Retry là một lần thử, chưa phải kết quả cuối

Giả sử `order-007` gọi service ngoài:

```text
attempt 1: TemporaryPartnerException
attempt 2: TemporaryPartnerException
attempt 3: success
```

Ở lần ba, item được ghi thành công. Nếu log `ERROR: item failed` ở hai attempt trước mà không mô tả đó là **retry attempt**, người vận hành dễ hiểu nhầm hai item đã thất bại. Với log từng attempt, dùng event rõ ngữ nghĩa như:

```text
event=batch_retry_attempt stage=process
error_code=PARTNER_TEMPORARY_FAILURE attempt=2
record_ref=8a62b97f4d21d5a7
```

`attempt` ở đây là ví dụ minh họa cho một giá trị được lấy từ retry context hoặc bộ đếm tin cậy, **không tự suy ra từ số dòng log**. Tùy chính sách, có thể log mức `DEBUG` hoặc `INFO` cho retry và chỉ `WARN` khi đạt ngưỡng cảnh báo; tránh sinh quá nhiều log khi lỗi tạm thời lặp lại hàng loạt.

`RetryListener` của Spring Retry có thể dùng để quan sát vòng retry. Cần cẩn thận vì cùng một chunk có thể rollback hoặc replay một phần thao tác, và cùng item có thể có nhiều callback. Không lấy số lời gọi của `onProcessError` làm số item thất bại cuối cùng.

### 8.2. Log mức tổng hợp sau step

Một `StepExecutionListener` giúp báo kết quả tổng thể mà không phải in từng item:

```java
package com.example.batch;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;

public class SafeStepSummaryLogger implements StepExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(SafeStepSummaryLogger.class);

    @Override
    public ExitStatus afterStep(StepExecution step) {
        log.info(
                "event=batch_step_finished step={} execution_id={} "
                + "status={} read={} write={} skip={} rollback={}",
                step.getStepName(),
                step.getJobExecutionId(),
                step.getStatus(),
                step.getReadCount(),
                step.getWriteCount(),
                step.getSkipCount(),
                step.getRollbackCount());

        return null; // Không thay đổi ExitStatus của step.
    }
}
```

`StepExecution` cung cấp các chỉ số kỹ thuật, không tiết lộ nội dung item. Tuy vậy, các field như tên step hoặc exit description do ứng dụng tự tạo vẫn cần kiểm tra nguồn. Trong một step có retry, `readCount`, `writeCount`, `rollbackCount` hay `skipCount` **không phải** số lần gọi processor/writer theo nghĩa đen.

### 8.3. Ghi nhận thất bại cần điều tra sâu

Với job `FAILED`, nên log tổng hợp như:

```text
event=batch_job_failed job=dailyOrdersJob
execution_id=78241 error_code=UNCLASSIFIED_FAILURE
action=REVIEW_RESTRICTED_DIAGNOSTICS
```

Người vận hành có thể mở `JobRepository` và hệ thống chẩn đoán nội bộ dựa vào `execution_id`. Nếu cần lưu bản ghi lỗi gốc cho bộ phận nghiệp vụ sửa dữ liệu, hãy đưa nó vào **quarantine/dead-letter store** có mã hóa, quyền truy cập riêng và thời hạn lưu, rồi log tham chiếu an toàn. Không thay thế quarantine bằng cách dump toàn bộ item vào hệ thống logging phổ thông.

Log thường không được transaction manager của step rollback. Nếu yêu cầu **mỗi item lỗi chỉ có đúng một sự kiện audit được commit**, nên thiết kế bảng audit hoặc transactional outbox có khóa idempotency, transaction phù hợp và cơ chế xuất event sau commit. Dòng log thông thường chủ yếu dùng để chẩn đoán, không phải nguồn sự thật duy nhất về trạng thái item.

## 9. Kiểm thử rằng log không lộ dữ liệu

Một bài test an toàn cần xác nhận cả **trường bắt buộc có mặt** và **dữ liệu nhạy cảm không xuất hiện**. Ví dụ test đơn vị listener với Logback `ListAppender`, thường có sẵn khi dùng `spring-boot-starter-test` và Spring Boot logging mặc định:

```java
package com.example.batch;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;

class SafeOrderSkipListenerTest {

    @Test
    void logsReferenceAndCodeWithoutRawItemOrExceptionMessage() {
        byte[] testKey = new byte[32];
        Arrays.fill(testKey, (byte) 7);

        var token = new SafeRecordToken(testKey);
        var listener = new SafeOrderSkipListener(
                token, "2026-11-16");

        Logger logger = (Logger) LoggerFactory.getLogger(
                SafeOrderSkipListener.class);

        ListAppender<ILoggingEvent> capture = new ListAppender<>();
        capture.start();
        logger.addAppender(capture);

        try {
            String privateId = "order-007-secret";
            String privateEmail = "sample.user@example.test";

            var item = new OrderInput(
                    privateId,
                    privateEmail,
                    new BigDecimal("123.45"));

            // Mô phỏng lỗi chứa thông tin nhạy cảm trong message.
            var error = new InvalidOrderException(
                    "Invalid data for " + privateEmail);

            listener.onSkipInProcess(item, error);

            assertThat(capture.list).hasSize(1);
            String message = capture.list.get(0)
                    .getFormattedMessage();

            assertThat(message)
                    .contains("event=batch_item_skipped")
                    .contains("stage=process")
                    .contains("error_code=INVALID_ORDER")
                    .contains("record_ref=" + token.fromIdentifier(privateId));

            assertThat(message)
                    .doesNotContain(privateId)
                    .doesNotContain(privateEmail)
                    .doesNotContain("123.45")
                    .doesNotContain("Invalid data for");
        } finally {
            logger.detachAppender(capture);
            capture.stop();
        }
    }
}
```

Test trên kiểm tra **thông điệp do listener tạo ra**; nó không tự kiểm tra mọi log từ reader/processor/writer, dependency, JDBC driver hay appender của hệ thống. Với kiểm thử tích hợp, nên chạy một dữ liệu tổng hợp có marker nhạy cảm dễ nhận diện (ví dụ `SENSITIVE_MARKER_001`) qua đường đọc, lỗi, retry, skip và ghi, sau đó tìm marker trong **toàn bộ log output** của ứng dụng thử nghiệm.

Khi có JSON encoder hoặc hệ thống log tập trung, cần kiểm tra dữ liệu **sau encoder và pipeline thu thập**, bởi MDC, exception layout, tracing baggage hoặc cấu hình APM có thể vô tình bổ sung payload dù message gốc đã an toàn.

### Các trường hợp cần test

| Kịch bản | Điều cần xác nhận |
| --- | --- |
| Item hợp lệ | Không sinh event skip không cần thiết |
| Item validation lỗi | Chỉ log `record_ref` và `INVALID_ORDER`; không có email, ID gốc, amount |
| Retry hai lần rồi thành công | Log attempt (nếu bật) được phân biệt với skip; không sinh skip cuối |
| Lỗi vĩnh viễn vượt retry, không skip | Step/job có trạng thái thất bại; error event không lộ payload |
| Lỗi đọc không có item | `record_ref=unavailable`, không dump dòng CSV/JSON |
| Lỗi ghi cả chunk | Không in toàn bộ collection item; xác định skip của từng item theo callback |
| Exception message có dữ liệu nhạy cảm | Không xuất hiện message và stack trace trên log phổ thông |
| Chạy nhiều execution song song | Không trộn MDC/record reference của hai execution |
| Key HMAC không hợp lệ | Hệ thống báo lỗi cấu hình, không fallback sang log ID thô |
| Pipeline log tập trung | JSON encoder/collector không thêm trường nhạy cảm |

## 10. Tránh rò rỉ qua MDC, tracing và hệ thống giám sát

`MDC` (Mapped Diagnostic Context) giúp gắn `jobExecutionId` hoặc correlation ID vào mọi dòng log của một đoạn xử lý. Nhưng MDC thường liên quan đến **thread hiện tại**; thread trong pool có thể được tái sử dụng. Nếu tự thiết lập MDC, phải dọn sạch trong `finally`:

```java
import org.slf4j.MDC;

try {
    MDC.put("job_execution_id", Long.toString(executionId));
    MDC.put("stage", "process");

    // Các lệnh log trong phạm vi này nhận các field MDC.
    runOperation();
} finally {
    MDC.remove("job_execution_id");
    MDC.remove("stage");
}
```

Đây là một **đoạn mã minh họa**: `executionId` và `runOperation()` do ứng dụng cung cấp. Với bất đồng bộ, `TaskExecutor`, partitioning hoặc multi-threaded step, cần cơ chế truyền context đúng qua thread boundary; không giả định MDC tự lan truyền giữa các thread.

Ngoài logger, còn những điểm có thể lưu thông tin vô tình:

- APM/tracing tự động thu HTTP URL, query parameter, request body hoặc exception message.
- JDBC logging ở mức `TRACE` có thể in câu SQL kèm bind values.
- `toString()` của các DTO xuất hiện trong log framework.
- Bộ ghi log của reader/writer tự in item hoặc dòng file lỗi.
- `JobParameters` hay `ExecutionContext` bị dump nguyên object khi debug.
- HTTP client ghi response body có dữ liệu khách hàng.
- Log aggregation bổ sung metadata hoặc giữ log lâu hơn quy định.

Phạm vi rà soát cần bao gồm **toàn pipeline log**, không chỉ code trong `SkipListener`. Trong production, quyền xem log nên theo vai trò, truyền/lưu có mã hóa, có chính sách retention và cơ chế xử lý sự cố lộ dữ liệu.

## 11. Giữ log hữu ích mà không tạo quá nhiều dữ liệu

Một job xử lý 10 triệu item có thể gây ra hàng trăm nghìn retry khi một service bên ngoài gặp sự cố. Nếu mỗi lần thử đều log stack trace, hệ thống logging có thể quá tải đúng lúc cần quan sát nhất.

Có thể áp dụng:

1. **Log event cấp item khi thực sự bị skip**, với trường được cho phép.
2. **Retry diagnostic theo cấu hình**, dùng log level phù hợp hoặc lấy mẫu; luôn giữ metric tổng hợp và số lần retry đáng tin cậy.
3. **Log summary sau step**: `read`, `write`, `skip`, `rollback`, `BatchStatus` và thời lượng.
4. **Phát alert theo ngưỡng**: skip ratio, lỗi theo `error_code`, số job `FAILED`, độ trễ, deadline miss.
5. **Không dùng item ID làm metrics label**; dùng event/job/step/error code có cardinality thấp.

Nếu giới hạn số dòng log hoặc dùng sampling, cần nói rõ sự kiện nào có thể không được ghi. Không thể lấy log đã sampling để đếm chính xác từng item bị lỗi. Muốn số lượng chính xác, dùng counter/metadata hoặc audit store được thiết kế cho mục đích đó.

## 12. Những lỗi phổ biến và cách sửa

| Lỗi thực hiện | Rủi ro | Cách sửa |
| --- | --- | --- |
| `log.error("item={}", item)` | Gọi `toString()` làm lộ mọi field | Log allowlist và token tham chiếu |
| `log.error("failed", throwable)` ở kênh chung | Stack trace/message mang payload hoặc SQL params | Mã lỗi ổn định; diagnostics riêng được kiểm soát |
| Log email/ID rồi thay bằng SHA-256 không khóa | Có thể dò giá trị từ từ điển | Không log hoặc dùng HMAC/token có chính sách |
| Log toàn bộ `JobParameters` | Có thể chứa secret và thông tin nghiệp vụ | Chỉ chọn field đã phê duyệt |
| Ghi `ERROR` cho mọi retry | Hiểu nhầm item cuối cùng đã thất bại | Phân biệt attempt với final skip/fail |
| Log mọi phần tử của chunk khi writer lỗi | Phơi bày dữ liệu nhiều item, tăng lưu lượng | Log event kỹ thuật; dùng skip callback phù hợp để nhận diện item |
| Gọi `SkipListener` như nguồn audit tuyệt đối | Log không transaction và có thể mất/nhân bản trong failure | Dùng bảng audit hoặc outbox nếu cần chính xác |
| Dùng `record_ref` làm metrics label | Cardinality cao và liên kết dữ liệu | Chỉ dùng `error_code`, `job`, `step`, `stage` |
| Bỏ quên MDC trên thread pool | Dòng log của job khác mang context cũ | Dọn MDC trong `finally`, cấu hình propagation đúng |
| Tự động log message exception chưa biết | Input nhạy cảm lẫn vào log | Fallback mã `UNCLASSIFIED_FAILURE` |
| Kênh quarantine không giới hạn truy cập | Lộ dữ liệu gốc qua hệ thống phụ | Mã hóa, phân quyền, retention, audit access |

## 13. Bài thực hành

Hãy tạo một chunk step `validateOrdersStep` xử lý danh sách đơn hàng thử nghiệm, trong đó có đơn hàng hợp lệ, đơn hàng sai quy tắc nghiệp vụ và đơn hàng gặp lỗi đối tác tạm thời.

1. Tạo `OrderInput` có `orderId`, `customerEmail`, `amount`. Cài đặt `toString()` mặc định nhưng **không** gọi nó trong logger.
2. Tạo `SafeRecordToken` dùng HMAC-SHA-256 và khóa riêng cho môi trường test. Kiểm tra cùng ID tạo cùng token, hai ID khác nhau tạo token khác nhau.
3. Tạo `SafeErrorCodes` chỉ trả về `INVALID_ORDER`, `PARTNER_TEMPORARY_FAILURE`, `UNCLASSIFIED_FAILURE`.
4. Đăng ký `SafeOrderSkipListener` với step có `.faultTolerant()`, `.skip(InvalidOrderException.class)` và `.retry(TemporaryPartnerException.class)`.
5. Cho một item invalid bị skip, xác nhận log chỉ có event an toàn, không chứa `orderId`, email, amount hay exception message.
6. Cho một item lỗi tạm thời hai lần rồi thành công ở lần ba; phân biệt log retry attempt với event skip cuối.
7. Cho lỗi đọc không tạo được item; xác nhận `onSkipInRead` không cố in dòng dữ liệu gốc.
8. Thêm `SafeStepSummaryLogger` và so sánh số `skipCount` với số item thực sự bị loại theo metadata batch.
9. Chạy test tích hợp thu tất cả log với một marker dữ liệu nhạy cảm giả, kiểm tra marker không xuất hiện sau JSON encoder, MDC và tracing.
10. Thiết kế một quarantine store chỉ người có quyền mới xem được payload lỗi; log ngoài chỉ chứa mã tham chiếu cho việc tra cứu an toàn.

Khi log item lỗi trong Spring Batch, nguyên tắc là **giữ thông tin đủ để tìm nguyên nhân và trạng thái xử lý, nhưng không đưa dữ liệu nghiệp vụ nhạy cảm vào log**. Phân loại lỗi thành mã cố định, log theo lifecycle callback đúng mục đích, dùng tham chiếu có bảo vệ và kiểm thử toàn bộ đường đi của log giúp batch vừa dễ vận hành vừa giảm rủi ro lộ dữ liệu.
