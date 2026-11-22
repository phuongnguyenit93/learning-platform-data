# Recovery bằng retry hoặc restart trong Spring Batch

## 1. Mục tiêu

Một batch job có thể đọc hàng triệu bản ghi, ghi dữ liệu theo từng chunk và chạy trong nhiều giờ. Trong khoảng thời gian đó, những lỗi như timeout cơ sở dữ liệu, mất kết nối API, khóa giao dịch, file bị gián đoạn hoặc dữ liệu nghiệp vụ không hợp lệ đều có thể xuất hiện. Nếu mọi lỗi đều khiến toàn bộ job chạy lại từ đầu, chi phí xử lý sẽ lớn và có nguy cơ ghi trùng dữ liệu. Nhưng nếu cứ retry vô hạn, job có thể chiếm tài nguyên, làm lỗi lan rộng và không thể hoàn tất đúng hạn.

**Failure recovery trong Spring Batch** là cách thiết kế để hệ thống khôi phục sau lỗi theo mức độ thích hợp: thử lại một thao tác trong cùng lần thực thi, bỏ qua một bản ghi lỗi có chủ đích hoặc khởi động lại job từ checkpoint đã lưu khi một lần chạy trước thất bại.

Bài học “Recovery bằng retry hoặc restart” thuộc nhóm *Failure recovery* của *Spring Batch Core Processing*, giúp bạn:

- Hiểu ranh giới giữa **retry**, **restart**, **skip** và **chạy lại một JobInstance mới**.
- Quyết định lỗi nào nên retry ngay trong step và lỗi nào cần để job thất bại rồi restart có kiểm soát.
- Cấu hình retry limit, backoff, exception classification và listener của chunk-oriented step.
- Dùng `JobRepository`, `JobParameters` và `ExecutionContext` để restart cùng JobInstance.
- Thiết kế reader/writer có tính restartable và idempotent, bảo đảm không nhân đôi tác động nghiệp vụ.
- Kiểm thử retry thành công, retry cạn, restart sau thất bại, job đã hoàn tất và các trường hợp dữ liệu thay đổi.
- Quan sát trạng thái cuối của job bằng metadata thay vì chỉ suy luận từ log exception.

Ví dụ sử dụng Java 17+, Spring Boot 3.x, Spring Batch 5.x và JUnit 5. Với ứng dụng dùng phiên bản Spring Batch khác, cấu hình API có thể thay đổi; các nguyên tắc về JobInstance, metadata, transaction và idempotency vẫn là nền tảng.

## 2. Retry, restart và recovery khác nhau thế nào?

Một lỗi có thể được xử lý ở nhiều cấp độ:

| Cơ chế | Phạm vi | Khi nào dùng | Có tạo JobExecution mới? |
| --- | --- | --- | --- |
| **Retry trong step** | Một lần thực hiện thao tác đọc/xử lý/ghi, thuộc cùng JobExecution | Lỗi tạm thời có khả năng tự hết, ví dụ timeout mạng | Không |
| **Skip** | Một item không thể hoặc không cần xử lý theo chính sách | Bản ghi không hợp lệ được phép loại khỏi kết quả | Không |
| **Fallback/recovery nghiệp vụ** | Đường xử lý thay thế do ứng dụng thiết kế | Chuyển bản ghi sang hàng đợi xử lý thủ công hoặc kết quả dự phòng hợp lệ | Thường không |
| **Restart** | JobInstance đã có lần thực thi không hoàn tất thành công | Lỗi kéo dài đã được khắc phục; muốn tiếp tục từ trạng thái đã lưu | Có JobExecution mới trong cùng JobInstance |
| **Tạo instance mới** | Một kỳ nghiệp vụ mới hoặc lần xử lý mới được định danh riêng | Xử lý ngày khác, file khác hoặc phiên bản dữ liệu mới | Có JobInstance và JobExecution mới |

Luồng tổng quát:

```text
                   JobExecution đang chạy
                            |
                            v
                   Step đọc/xử lý/ghi
                            |
                         Exception?
                       /            \
                     Không            Có
                      |                |
                      v                v
                Tiếp tục chunk    Retry policy?
                                    /       \
                                  Có       Không
                                  |          |
                                  v          v
                              Thử lại    Skip/fallback?
                               /  \        /       \
                          Thành  Vẫn lỗi  Có       Không
                          công     |      |          |
                            |      v      v          v
                            |    Retry   Skip hoặc  Step FAILED
                            |     cạn    recovery        |
                            |      |                     v
                            +------+----------------  Job FAILED
                                                       |
                                           Sửa nguyên nhân lỗi
                                                       |
                                                       v
                                             Restart cùng identity
                                                       |
                                                       v
                                               JobExecution mới
```

Sơ đồ minh họa ý tưởng. Với Spring Batch, quy tắc retry/skip thực tế còn phụ thuộc exception được ném ở reader, processor hay writer, transaction có rollback hay không, và cấu hình fault tolerance.

Một **retry thành công** có thể khiến job vẫn `COMPLETED` dù log xuất hiện nhiều lỗi tạm thời. Một **restart thành công** có nghĩa JobInstance đã có ít nhất một JobExecution trước đó chưa thành công và sau đó có execution mới hoàn tất.

## 3. Khi nào nên retry và khi nào nên restart?

Hãy phân loại lỗi dựa trên **khả năng tự phục hồi trong thời gian ngắn**, **mức độ an toàn khi thực hiện lại thao tác**, và **chi phí chiếm tài nguyên**.

| Tình huống lỗi | Hướng xử lý thường phù hợp | Lý do |
| --- | --- | --- |
| HTTP 503, lỗi mạng thoáng qua | Retry có giới hạn, kèm backoff | Có khả năng dịch vụ hồi phục sau vài giây |
| Deadlock hoặc lỗi DB transient | Retry transaction/chunk có giới hạn | Thường có thể thành công khi xung đột qua đi |
| API trả HTTP 429 | Retry theo giới hạn/thời gian chờ nếu hợp đồng API cho phép | Cần tránh gây quá tải thêm |
| Thiếu cột bắt buộc trong file | Fail sớm hoặc skip theo chính sách | Retry cùng dữ liệu không sửa được schema |
| Số tiền âm trong bản ghi | Skip/reject có báo cáo nếu nghiệp vụ cho phép | Dữ liệu không hợp lệ, không phải lỗi tạm thời |
| Thiếu credential hoặc cấu hình sai | Fail và sửa cấu hình trước khi restart | Retry nhanh thường vô ích |
| Database ngừng hoạt động lâu | Job fail sau retry hữu hạn, sau đó restart | Không nên giữ worker vô hạn chờ hạ tầng |
| JVM/container bị dừng đột ngột | Đối soát metadata và restart có kiểm soát | Process cũ có thể không kịp cập nhật trạng thái cuối |
| Đã ghi một phần dữ liệu vào dịch vụ ngoài rồi timeout | Kiểm tra idempotency và trạng thái đích trước retry | Response timeout không chứng minh thao tác chưa được thực hiện |

**Quy tắc quan trọng:** retry và restart chỉ an toàn khi việc thực hiện lại không tạo kết quả sai. Nếu writer gọi API trừ tiền, gửi email hoặc xuất bản sự kiện, cần thiết kế idempotency, khóa nghiệp vụ hoặc cơ chế đối soát trước khi cho phép thử lại.

Đừng xem retry là giải pháp chung cho mọi `Exception`. Ví dụ `NumberFormatException` do dữ liệu không hợp lệ sẽ lặp lại vô ích nếu vẫn dùng đầu vào cũ.

## 4. Metadata quyết định khả năng restart

Spring Batch lưu trạng thái qua `JobRepository`. Những thành phần quan trọng là:

- `Job`: định nghĩa công việc, ví dụ `importPaymentsJob`.
- `JobParameters`: tham số thực thi; một số tham số là **identifying**.
- `JobInstance`: tên Job kết hợp identifying parameters.
- `JobExecution`: một lần cố gắng thực thi JobInstance.
- `StepExecution`: trạng thái một step trong một JobExecution.
- `ExecutionContext`: trạng thái checkpoint cần cho restart.

Ví dụ:

```text
Job: importPaymentsJob

JobInstance ID=1201
  identifying: businessDate=2026-11-15
     |
     +-- JobExecution ID=9001: FAILED
     |      validateStep: COMPLETED
     |      persistStep: FAILED
     |
     +-- JobExecution ID=9002: COMPLETED
            validateStep: thường được bỏ qua khi restart
            persistStep: chạy lại theo trạng thái đã lưu

JobInstance ID=1202
  identifying: businessDate=2026-11-16
     |
     +-- JobExecution ID=9003: COMPLETED
```

Một JobInstance có thể có nhiều JobExecution do restart, nhưng khi JobInstance đã `COMPLETED`, yêu cầu chạy lại với **cùng identifying parameters** thường bị từ chối bằng `JobInstanceAlreadyCompleteException`.

### Identifying và non-identifying parameters

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addString("requestedBy", "scheduler", false)
    .toJobParameters();
```

`businessDate` xác định instance; `requestedBy` chỉ dùng truy vết. Nếu sửa `businessDate` hoặc bổ sung timestamp ngẫu nhiên dạng identifying ở lần thứ hai, bạn đang yêu cầu **instance khác**, không phải restart instance cũ.

Một lỗi phổ biến là:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15")
    .addLong("run.id", System.currentTimeMillis())
    .toJobParameters();
```

Trong cách sử dụng thông thường của `JobParametersBuilder`, tham số thêm vào mặc định là identifying. `run.id` thay đổi khiến mỗi lần gửi yêu cầu có thể thành một JobInstance mới, dễ lặp dữ liệu của cùng ngày.

## 5. Cấu hình retry ở chunk-oriented step

Giả sử job đọc dữ liệu thanh toán, processor chuẩn hóa bản ghi và writer ghi database. Một số lỗi truy cập dữ liệu tạm thời được phép retry.

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
Step paymentStep(
        JobRepository repository,
        PlatformTransactionManager transactionManager,
        ItemReader<PaymentRow> reader,
        ItemProcessor<PaymentRow, AcceptedPayment> processor,
        ItemWriter<AcceptedPayment> writer) {

    return new StepBuilder("paymentStep", repository)
        .<PaymentRow, AcceptedPayment>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
}
```

Đoạn code giả định các kiểu `PaymentRow`, `AcceptedPayment` và bean Reader/Processor/Writer đã được định nghĩa. Tên step và cách khởi tạo JobRepository phù hợp API Spring Batch 5.x.

Ý nghĩa:

- `chunk(100, transactionManager)` xử lý theo chunk tối đa 100 item và dùng transaction manager đã cấu hình.
- `faultTolerant()` chuyển builder sang kiểu hỗ trợ skip/retry.
- `retry(TransientDataAccessException.class)` khai báo nhóm exception có thể thử lại.
- `retryLimit(3)` giới hạn các lần thử theo RetryPolicy của step; nên xác minh số lần gọi thực tế trong test khi sử dụng policy hoặc phiên bản cụ thể.
- Nếu retry cạn mà không có chính sách xử lý lỗi tiếp theo phù hợp, step thường chuyển sang `FAILED`.

### Retry đọc, xử lý và ghi không hoàn toàn giống nhau

| Giai đoạn | Điểm lỗi | Rủi ro cần để ý |
| --- | --- | --- |
| `read()` | Kết nối/parse/truy vấn nguồn | Sau rollback có thể đọc lại dữ liệu; reader phải giữ vị trí đúng |
| `process()` | Validate, gọi API, chuyển đổi dữ liệu | Một item có thể được processor gọi nhiều lần; processor nên hạn chế side effect |
| `write()` | SQL/HTTP/file output | Writer có thể đã thực hiện một phần tác động trước khi ném lỗi |

Việc retry tại writer phải được đánh giá cẩn thận hơn nếu ghi ra hệ thống **không tham gia transaction của step**. Một HTTP request timeout có thể đã được phía nhận xử lý; nếu gọi lại mà không có idempotency key, tác động có thể bị lặp.

### Không retry mọi Exception

Cấu hình như `.retry(Exception.class)` có thể khiến lỗi dữ liệu, lỗi lập trình hoặc lỗi cấu hình cũng bị thử lại. Chỉ nên dùng khi ứng dụng có một exception hierarchy được kiểm soát và mỗi lớp lỗi trong nhóm đều thực sự retryable.

Trong hệ thống thực, hãy phân loại exception gần adapter truy cập hạ tầng: ví dụ chuyển lỗi timeout của HTTP client thành exception nghiệp vụ riêng `RemoteServiceTemporaryException`, đồng thời không đánh đồng HTTP 400 với lỗi 503.

## 6. Backoff và giới hạn tài nguyên

Retry liên tục ngay lập tức có thể tạo một *retry storm* khi dịch vụ đích đang suy yếu: hàng trăm worker cùng gửi lại request, làm hệ thống đích khó phục hồi hơn.

Spring Retry hỗ trợ backoff policy. Trong cấu hình fault-tolerant step, có thể dùng backoff theo hàm mũ:

```java
import org.springframework.retry.backoff.ExponentialBackOffPolicy;

ExponentialBackOffPolicy backoff = new ExponentialBackOffPolicy();
backoff.setInitialInterval(500);
backoff.setMultiplier(2.0);
backoff.setMaxInterval(5_000);

Step step = new StepBuilder("paymentStep", repository)
    .<PaymentRow, AcceptedPayment>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .retry(TransientDataAccessException.class)
    .retryLimit(3)
    .backOffPolicy(backoff)
    .build();
```

Các khoảng minh họa ở đây là 500 ms, tăng dần với hệ số 2 và giới hạn 5 giây. Backoff chỉ áp dụng khi thực sự có lần thử tiếp theo. Giới hạn retry, thời gian chờ của API, số worker và SLA của job cần được thiết kế cùng nhau.

Với hệ thống phân tán, có thể cần **jitter** (dao động ngẫu nhiên của thời gian chờ) để tránh tất cả instance thử lại đồng thời. Nên chọn chiến lược backoff hỗ trợ jitter hoặc thiết kế retry ở tầng client phù hợp; không nên tùy tiện tạo lại thread/Timer cho mỗi item.

Nếu một step xử lý nhiều loại exception, hãy kiểm tra retry policy có phân loại đúng theo lỗi và có giới hạn tổng thời gian hợp lý. Một job xử lý hàng triệu item không nên dành hàng giờ chờ retry cho một lỗi hạ tầng đã kéo dài.

## 7. Retry và skip: hai đường hồi phục khác nhau

Trong Spring Batch, **skip** có nghĩa item bị lỗi được phép bỏ qua để step tiếp tục xử lý các item khác. Skip không đồng nghĩa retry đã thành công.

Ví dụ:

```java
Step step = new StepBuilder("paymentStep", repository)
    .<PaymentRow, AcceptedPayment>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .retry(TransientDataAccessException.class)
    .retryLimit(3)
    .skip(InvalidPaymentException.class)
    .skipLimit(5)
    .build();
```

Trong ví dụ:

- Lỗi hạ tầng tạm thời thuộc nhóm `TransientDataAccessException` được retry.
- Lỗi dữ liệu nghiệp vụ `InvalidPaymentException` có thể được skip trong giới hạn.
- Khi vượt `skipLimit`, step có thể thất bại.
- Nếu processor trả về `null` để filter item, `filterCount` tăng; đó **không phải** skip và không tiêu thụ giới hạn skip.

Một bảng quyết định:

| Dữ liệu/lỗi | Retry? | Skip? | Kết quả kỳ vọng |
| --- | --- | --- | --- |
| Bản ghi hợp lệ | Không | Không | Xử lý thành công |
| Timeout tạm thời rồi hết | Có | Không | Xử lý tiếp cùng execution |
| Bản ghi sai format cho phép loại | Thường không | Có | Ghi nhận skip, step tiếp tục |
| Lỗi mạng kéo dài vượt retry | Đã thử hữu hạn | Theo policy, thường không | Step `FAILED` |
| Bản ghi sai bắt buộc phải sửa | Không | Không | Step `FAILED`, sửa nguồn rồi restart theo quy trình |

**Quy tắc nghiệp vụ phải rõ:** có job được phép hoàn tất với 5 bản ghi lỗi bị skip; có job đối soát tài chính phải fail nếu bất kỳ bản ghi nào sai. Cấu hình skip là quyết định về tính đầy đủ của dữ liệu, không chỉ là một kỹ thuật tăng khả năng thành công của job.

## 8. Recovery callback không đồng nghĩa cơ chế restart

Khi một thao tác dùng `RetryTemplate` trực tiếp, Spring Retry có thể áp dụng `RecoveryCallback` sau khi các lần retry không thành công:

```java
import org.springframework.retry.support.RetryTemplate;

RetryTemplate template = RetryTemplate.builder()
    .maxAttempts(3)
    .retryOn(RemoteServiceTemporaryException.class)
    .build();

String status = template.execute(
    context -> remoteClient.lookupStatus(paymentId),
    context -> {
        // Phương án thay thế được ứng dụng định nghĩa.
        return "MANUAL_REVIEW";
    }
);
```

Ví dụ giả định `remoteClient`, `paymentId` và exception nghiệp vụ đã tồn tại. Chuỗi `MANUAL_REVIEW` không phải một trạng thái chuẩn của Spring Batch; chỉ là giá trị fallback do ứng dụng thiết kế.

Nếu gọi `RetryTemplate` bên trong một `ItemProcessor` **đã được Batch cấu hình retry**, có thể xảy ra retry lồng nhau. Ví dụ outer retry 3 lần và inner retry 3 lần có thể khiến một operation được gọi nhiều hơn dự kiến. Nên quyết định rõ tầng nào chịu trách nhiệm retry.

Trong khi đó, **restart** tạo JobExecution mới dựa trên metadata đã lưu; nó không chạy một `RecoveryCallback` của Spring Retry. Khi muốn khôi phục cả job sau lỗi kéo dài, cần dùng cơ chế restart của Spring Batch.

## 9. Điều kiện restart một JobInstance

Một restart thường áp dụng khi:

1. JobInstance đã có một JobExecution trước đó.
2. Lần thực thi trước kết thúc trong trạng thái cho phép restart, chẳng hạn `FAILED` hoặc `STOPPED`, tùy tình huống.
3. Job được cấu hình restartable (mặc định theo cách xây dựng thông thường).
4. JobLauncher nhận **cùng tên Job và cùng identifying parameters**.
5. Metadata của JobRepository vẫn còn và nhất quán.
6. Các reader/writer/step có khả năng khôi phục theo trạng thái đã commit.

Ví dụ:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .toJobParameters();

// Lần đầu: JobExecution 9001 có thể FAILED.
JobExecution first = jobLauncher.run(importPaymentsJob, parameters);

// Sau khi sửa lỗi hạ tầng, gọi lại cùng parameters:
// Tạo execution 9002 nếu instance đủ điều kiện restart.
JobExecution restarted = jobLauncher.run(importPaymentsJob, parameters);
```

Trong code production, cần xem trạng thái execution đầu và chỉ yêu cầu restart khi phù hợp. Nếu JobInstance đã hoàn tất, lần gọi thứ hai sẽ bị từ chối. Nếu execution trước vẫn đang chạy, launcher cũng từ chối yêu cầu trùng.

### Những ngoại lệ thường gặp

| Ngoại lệ | Ý nghĩa điển hình |
| --- | --- |
| `JobInstanceAlreadyCompleteException` | Instance đã hoàn tất, không được chạy lại với danh tính đó |
| `JobExecutionAlreadyRunningException` | Một execution của instance đang hoạt động |
| `JobRestartException` | Restart không hợp lệ, ví dụ job không cho phép restart hoặc trạng thái không phù hợp |
| `JobParametersInvalidException` | Tham số không thỏa validation của job |

Không nên catch mọi ngoại lệ rồi tự tăng `run.id` để “cho job chạy được”. Cách đó đổi danh tính instance và có thể xử lý trùng dữ liệu của kỳ cũ.

## 10. Step nào sẽ chạy lại khi restart?

Spring Batch có thể bỏ qua những step đã `COMPLETED` trong JobExecution trước, rồi chạy lại step chưa hoàn tất. Ví dụ job có hai bước:

```text
validateInputStep -> persistPaymentsStep
```

Lần đầu:

```text
JobExecution 9001: FAILED
  validateInputStep: COMPLETED
  persistPaymentsStep: FAILED
```

Sau restart với cùng JobInstance:

```text
JobExecution 9002: COMPLETED
  validateInputStep: thường được bỏ qua
  persistPaymentsStep: chạy lại, dựa trên checkpoint/state của step
```

Điều này có ý nghĩa lớn nếu validate step tốn 30 phút: cơ chế restart giúp tránh thực hiện lại phần đã thành công khi không cần thiết.

### allowStartIfComplete và startLimit

Nếu một step cần chạy lại **kể cả khi đã hoàn tất** trong lần thực thi cũ, có thể cấu hình:

```java
Step validationStep = new StepBuilder("validateInputStep", repository)
    .tasklet(validationTasklet, transactionManager)
    .allowStartIfComplete(true)
    .build();
```

Đây là lựa chọn có chủ đích, chẳng hạn khi step chỉ kiểm tra điều kiện hiện tại hoặc chuẩn bị tài nguyên cho các step sau. Không dùng `allowStartIfComplete(true)` cho step ghi dữ liệu không idempotent chỉ vì muốn “chạy lại mọi thứ”.

`startLimit(n)` giới hạn số lần một step được khởi chạy trong vòng đời JobInstance, theo quy tắc của framework. Nó là công cụ ngăn step bị start quá nhiều lần, khác với `retryLimit` cho lỗi tạm thời trong step.

Một job có thể tắt restart:

```java
Job job = new JobBuilder("oneTimeImportJob", repository)
    .start(step)
    .preventRestart()
    .build();
```

Job vẫn chạy lần đầu với bộ tham số mới; khi instance đã có execution và cần restart, Spring Batch có thể ném `JobRestartException`.

## 11. ExecutionContext và checkpoint cho restart

Một checkpoint giúp restart từ trạng thái đã được lưu thay vì luôn bắt đầu lại từ dòng đầu. Spring Batch sử dụng `ExecutionContext` để lưu các thông tin phục vụ khôi phục, chẳng hạn số item đã đọc, vị trí file, hoặc state do reader quản lý.

Trong chunk-oriented step, khái niệm tổng quát:

```text
Đọc 1..100   -> process/write -> commit -> lưu state
Đọc 101..200 -> process/write -> commit -> lưu state
Đọc 201..300 -> lỗi trước commit -> rollback

Restart:
  tiếp tục từ state đã commit gần nhất,
  có thể đọc lại item thuộc chunk bị rollback
```

Ví dụ minh họa dùng `FlatFileItemReader` có khả năng lưu trạng thái khi triển khai như một `ItemStream`:

```java
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.core.io.FileSystemResource;

@Bean
@StepScope
FlatFileItemReader<PaymentRow> paymentReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<PaymentRow>()
        .name("paymentCsvReader")
        .resource(new FileSystemResource(inputFile))
        .linesToSkip(1)
        .delimited()
        .names("paymentId", "amount")
        .fieldSetMapper(fieldSet -> new PaymentRow(
            fieldSet.readString("paymentId"),
            fieldSet.readBigDecimal("amount")
        ))
        .saveState(true)
        .strict(true)
        .build();
}
```

Trong ví dụ, cần import `@Bean`, `@StepScope`, `@Value` và định nghĩa record/DTO `PaymentRow` phù hợp. `inputFile` là đường dẫn từ JobParameters; phải bảo đảm cùng một file nguồn được cung cấp khi restart, không đổi nội dung hay thứ tự dòng ngoài chính sách đã thiết kế.

Khi sử dụng reader chuẩn, nên dựa trên khả năng restart có sẵn, cung cấp tên reader ổn định, bảo đảm `saveState(true)` được bật và scope phù hợp. Tự viết reader mà không triển khai quản lý checkpoint có thể khiến lần restart đọc lại từ đầu hoặc bỏ sót dữ liệu.

### ExecutionContext không phải nơi giữ toàn bộ dữ liệu

Chỉ lưu trạng thái nhỏ cần thiết để khôi phục, ví dụ offset, vị trí file hoặc khóa sau cùng đã commit:

```java
executionContext.putLong("lastCommittedId", lastId);
executionContext.putString("sourceFileKey", fileKey);
```

Không đưa danh sách hàng triệu item vào ExecutionContext. Điều đó gây áp lực heap/serialization và làm chậm metadata repository.

Quan trọng hơn, một `lastCommittedId` tự thiết kế chỉ có ích nếu ordering của dữ liệu nguồn ổn định và checkpoint được cập nhật đúng lúc giao dịch commit. Khi dữ liệu có thể thay đổi thứ tự, một cơ chế “đọc sau ID” tự viết có thể bỏ sót bản ghi mới hoặc ghi trùng.

## 12. Transaction, rollback và tác động ngoài database

Một chunk có thể đọc và xử lý nhiều item, gọi writer, rồi commit transaction. Khi lỗi xảy ra trước commit, transaction database có thể rollback; khi retry hoặc restart, các item trong chunk đó có thể được thực hiện lại.

Ví dụ:

```text
Chunk 1: items 1..100
  DB write -> COMMIT

Chunk 2: items 101..200
  DB write một phần -> lỗi
  DB transaction -> ROLLBACK

Restart:
  Chunk 1 vẫn đã commit
  Chunk 2 có thể được xử lý lại
```

Trên cùng datasource/transaction manager, rollback có thể bảo vệ các thay đổi database do writer thực hiện trong transaction đó. Nhưng tác động đến hệ thống ngoài (HTTP, email, message broker không phối hợp transaction, file hoặc dịch vụ thanh toán) có thể **không rollback**.

### Ví dụ nguy cơ ghi trùng

Writer gửi yêu cầu tới API bên ngoài. API đã lưu thanh toán nhưng kết nối timeout trước khi trả response. Spring Batch nhìn thấy exception, retry và gửi cùng yêu cầu lần nữa. Nếu API không hỗ trợ idempotency, giao dịch có thể bị xử lý hai lần.

Cách xử lý có thể gồm:

- Dùng **idempotency key** ổn định theo business key của item và thao tác, không phụ thuộc JobExecution ID.
- Ghi dữ liệu vào database/outbox cùng transaction, rồi phát thông điệp sau commit.
- Dùng unique constraint tại bảng đích, ví dụ `UNIQUE(business_date, payment_id)`.
- Định nghĩa API có khả năng truy vấn trạng thái của request trước khi thử lại.
- Đối soát kết quả của hệ thống ngoài khi exception không khẳng định thao tác đã thất bại.

**Mục tiêu là kết quả nghiệp vụ đúng sau bất kỳ số lần retry/restart hợp lệ nào.** Spring Batch giúp quản lý metadata và transaction của step, nhưng không tự tạo bảo đảm exactly-once trên mọi hệ thống ngoài.

### Không chuyển JobExecution ID thành khóa idempotency

Restart tạo JobExecution ID mới cho cùng JobInstance. Nếu dùng execution ID để quyết định một thanh toán đã được thực hiện chưa, lần restart có thể trông như “request mới” với hệ thống ngoài.

Idempotency key nên gắn với thực thể nghiệp vụ như `paymentId` cộng loại operation/kỳ xử lý, theo quy định của hệ thống đích.

## 13. Recovery khi JVM hoặc container bị dừng đột ngột

Nếu một step tự ném exception trong tiến trình còn hoạt động, Spring Batch thường có cơ hội cập nhật metadata thành `FAILED`. Nhưng nếu JVM bị kill cưỡng bức hoặc mất kết nối repository khi đang chạy, metadata có thể vẫn ở trạng thái `STARTED` hoặc `STARTING`.

Khi đó, gọi lại `JobLauncher.run(...)` ngay có thể gặp `JobExecutionAlreadyRunningException` vì repository vẫn cho rằng execution trước chưa kết thúc.

Đây không phải lý do để xóa hoặc sửa metadata tùy tiện. Quy trình recovery cần:

1. Xác nhận execution cũ thực sự không còn chạy trên node khác.
2. Kiểm tra JobExecution/StepExecution, transaction, log và tình trạng dữ liệu đích.
3. Dùng quy trình vận hành được hỗ trợ để phân loại execution cũ và quyết định khả năng restart.
4. Kiểm tra checkpoint và các tác động ngoài transaction.
5. Phát yêu cầu restart với cùng identifying parameters.
6. Theo dõi trạng thái cuối và đối soát số liệu nghiệp vụ.

Spring Batch cung cấp API như `JobOperator` và metadata qua `JobExplorer` phục vụ vận hành, nhưng sự cố crash cần được đánh giá theo phiên bản và cách triển khai. Không tự cập nhật các bảng `BATCH_JOB_EXECUTION`/`BATCH_STEP_EXECUTION` bằng câu SQL tùy tiện để ép một job chạy lại nếu chưa có quy trình xử lý được kiểm chứng.

### Recovery ở scheduler và recovery ở step

Một scheduler có thể phát trigger định kỳ để khởi chạy các JobInstance chưa hoàn tất. Nhưng nếu cứ phát lại ngay khi thất bại mà không phân loại lỗi, có thể tạo vòng restart vô hạn:

```text
Scheduler phát trigger D
       |
       v
JobExecution FAILED
       |
       v
Scheduler thử lại ngay với D
       |
       v
JobExecution FAILED
       |
       +--> lặp vô hạn, chiếm tài nguyên
```

Nên có giới hạn số lần restart, khoảng chờ, phân loại lỗi và cơ chế chuyển cho người vận hành khi không thể tự phục hồi. Với lỗi cấu hình hoặc dữ liệu chắc chắn sai, chỉ restart sau khi nguyên nhân đã được sửa.

## 14. Log và metric để biết recovery có thực sự thành công

Một hệ thống tốt cần phân biệt **attempt failed** với **job ultimately failed**.

Thông tin nên theo dõi:

| Nhóm | Trường dữ liệu |
| --- | --- |
| Danh tính | Job name, JobInstance ID, JobExecution ID, businessDate |
| Retry | Step, phase READ/PROCESS/WRITE, loại exception, số lần thử gây lỗi |
| Skip | Read/process/write skip count, mã lý do dữ liệu |
| Transaction | Commit count, rollback count |
| Kết quả step | `BatchStatus` và `ExitStatus` của StepExecution |
| Kết quả job | `BatchStatus`, `ExitStatus`, thời gian bắt đầu/kết thúc |
| Restart | Execution mới liên kết cùng JobInstance với execution cũ |
| Nghiệp vụ | Số bản ghi ở đầu ra, tổng tiền, khóa idempotency và sai lệch đối soát |

Một `RetryListener` có thể log lỗi từng attempt; `SkipListener` log item thực sự bị bỏ qua; `StepExecutionListener` và `JobExecutionListener` log trạng thái cuối.

**Không đếm số dòng exception thành số bản ghi lỗi.** Một item có thể ném exception nhiều lần trong retry, thậm chí được xử lý lại sau rollback/restart. Nếu cần thống kê số item cuối cùng bị loại, dùng số đếm skip, bảng lỗi và logic đối soát nghiệp vụ.

Ví dụ log minh họa:

```text
WARN event=batch.retry.error jobExecutionId=9001 step=paymentStep retryFailureCount=1 exceptionType=TransientDataAccessResourceException

WARN event=batch.retry.error jobExecutionId=9001 step=paymentStep retryFailureCount=2 exceptionType=TransientDataAccessResourceException

INFO event=batch.step.finished jobExecutionId=9001 step=paymentStep status=COMPLETED readCount=1000 writeCount=1000 skipCount=0

INFO event=batch.job.finished jobInstanceId=1201 jobExecutionId=9001 status=COMPLETED
```

Các log `WARN` đầu không đồng nghĩa job thất bại. Kết quả cuối cho thấy retry đã giúp thực thi hoàn tất.

Nếu step thật sự `FAILED`, cần log thêm nguyên nhân và correlation ID, đồng thời hạn chế stack trace lặp lại hàng nghìn lần. Không ghi token, dữ liệu cá nhân, payload thanh toán hoặc toàn bộ `JobParameters` nếu không cần.

## 15. Ví dụ tích hợp: restart sau khi một step thất bại

Ví dụ sau dùng một job có hai step:

1. `validateStep` luôn thành công và đếm số lần gọi.
2. `persistStep` có thể được cấu hình thất bại đúng một lần, sau đó thành công.

Test xác minh restart tạo **JobExecution mới của cùng JobInstance** và mặc định không chạy lại step đã `COMPLETED`.

Dependency test với Gradle:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-batch'
testImplementation 'org.springframework.boot:spring-boot-starter-test'
testImplementation 'org.springframework.batch:spring-batch-test'
testRuntimeOnly 'com.h2database:h2'
```

JUnit 5 integration test:

```java
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.batch.test.JobRepositoryTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

import static org.junit.jupiter.api.Assertions.*;

@SpringBatchTest
@SpringBootTest(
    classes = RestartIntegrationTest.TestApplication.class,
    properties = {
        "spring.batch.job.enabled=false",
        "spring.batch.jdbc.initialize-schema=always",
        "spring.datasource.url=jdbc:h2:mem:restart_test;DB_CLOSE_DELAY=-1",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.datasource.username=sa",
        "spring.datasource.password="
    }
)
class RestartIntegrationTest {

    @Autowired
    private JobLauncher jobLauncher;

    @Autowired
    private JobExplorer jobExplorer;

    @Autowired
    private JobRepositoryTestUtils repositoryTestUtils;

    @Autowired
    @Qualifier("recoveryDemoJob")
    private Job job;

    @Autowired
    @Qualifier("validationCalls")
    private AtomicInteger validationCalls;

    @Autowired
    @Qualifier("persistCalls")
    private AtomicInteger persistCalls;

    @Autowired
    private AtomicBoolean failNextPersist;

    @BeforeEach
    void reset() {
        repositoryTestUtils.removeJobExecutions();
        validationCalls.set(0);
        persistCalls.set(0);
        failNextPersist.set(false);
    }

    @Test
    void restartKeepsInstanceAndSkipsCompletedStep()
            throws Exception {

        JobParameters parameters = new JobParametersBuilder()
            .addString("businessDate", "2026-11-15", true)
            .toJobParameters();

        // Lần đầu: validate thành công, persist thất bại.
        failNextPersist.set(true);
        JobExecution first = jobLauncher.run(job, parameters);

        assertEquals(BatchStatus.FAILED, first.getStatus());
        assertEquals(1, validationCalls.get());
        assertEquals(1, persistCalls.get());

        // Lần hai: restart cùng JobInstance.
        JobExecution second = jobLauncher.run(job, parameters);

        assertEquals(BatchStatus.COMPLETED, second.getStatus());

        assertEquals(
            first.getJobInstance().getInstanceId(),
            second.getJobInstance().getInstanceId()
        );
        assertNotEquals(first.getId(), second.getId());

        // validateStep đã COMPLETED nên mặc định được bỏ qua.
        assertEquals(1, validationCalls.get());

        // persistStep thất bại ở execution đầu, chạy lại ở execution sau.
        assertEquals(2, persistCalls.get());

        assertEquals(
            2,
            jobExplorer.getJobExecutions(
                second.getJobInstance()
            ).size()
        );
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApplication {

        @Bean("validationCalls")
        AtomicInteger validationCalls() {
            return new AtomicInteger();
        }

        @Bean("persistCalls")
        AtomicInteger persistCalls() {
            return new AtomicInteger();
        }

        @Bean
        AtomicBoolean failNextPersist() {
            return new AtomicBoolean(false);
        }

        @Bean
        Step validateStep(
                JobRepository repository,
                PlatformTransactionManager transactionManager,
                @Qualifier("validationCalls")
                    AtomicInteger validationCalls) {

            return new StepBuilder("validateStep", repository)
                .tasklet((contribution, context) -> {
                    validationCalls.incrementAndGet();
                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .build();
        }

        @Bean
        Step persistStep(
                JobRepository repository,
                PlatformTransactionManager transactionManager,
                @Qualifier("persistCalls")
                    AtomicInteger persistCalls,
                AtomicBoolean failNextPersist) {

            return new StepBuilder("persistStep", repository)
                .tasklet((contribution, context) -> {
                    persistCalls.incrementAndGet();

                    if (failNextPersist.getAndSet(false)) {
                        throw new IllegalStateException(
                            "Simulated transient failure"
                        );
                    }

                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .build();
        }

        @Bean("recoveryDemoJob")
        Job recoveryDemoJob(
                JobRepository repository,
                @Qualifier("validateStep") Step validateStep,
                @Qualifier("persistStep") Step persistStep) {

            return new JobBuilder("recoveryDemoJob", repository)
                .start(validateStep)
                .next(persistStep)
                .build();
        }
    }
}
```

Test dùng `AtomicBoolean` chỉ để **điều khiển lỗi trong test**; không phải chiến lược tự khôi phục lỗi sản xuất. Lớp job của dự án thật nên triển khai nghiệp vụ trong reader/processor/writer/tasklet, có transaction và khả năng idempotency phù hợp.

Ở ví dụ này, lần đầu có `JobExecution FAILED`, lần hai `COMPLETED`, JobInstance ID giữ nguyên và Step `validateStep` không thực thi lại. Sự khác biệt giữa **retry** và **restart** hiện rõ: test tạo hai JobExecution khác nhau, thay vì chỉ thử lại một operation bên trong một execution.

## 16. Kiểm thử retry với lỗi tạm thời có kiểm soát

Đối với retry trong chunk step, một test có thể dùng `AtomicInteger` để đếm số lần dependency được gọi.

Ví dụ minh họa một processor gọi service giả lập:

```java
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.dao.TransientDataAccessResourceException;

AtomicInteger calls = new AtomicInteger();

ItemProcessor<PaymentRow, PaymentRow> flakyProcessor = item -> {
    int attempt = calls.incrementAndGet();

    if (attempt == 1) {
        throw new TransientDataAccessResourceException(
            "Temporary database outage"
        );
    }

    return item;
};
```

Khi dùng cùng fault-tolerant step có `.retry(TransientDataAccessException.class)` và giới hạn phù hợp, test cần xác minh:

- JobExecution cuối cùng `COMPLETED`.
- Dependency được gọi lại sau lỗi.
- Item được ghi một lần theo kết quả nghiệp vụ.
- Không có item bị skip nếu retry đã thành công.
- Metadata phản ánh số item được đọc/ghi theo quy tắc của framework.
- Không có JobExecution thứ hai chỉ vì retry xảy ra trong step.

Nếu step xử lý nhiều item, `AtomicInteger` dùng chung chỉ đo tổng số lời gọi; khi muốn đo riêng từng item, cần map theo business key hoặc tạo một fixture chỉ có một item để tránh nhầm lẫn.

Một phép thử khác cho dependency **luôn ném exception** sẽ kiểm tra trường hợp retry hết giới hạn và step chuyển sang `FAILED`. Không nên viết assertion dựa vào số lần gọi được phỏng đoán nếu retry policy, rollback hoặc reader có thể thay đổi số lần thực thi; xác định chính sách và kiểm tra theo cấu hình thực tế.

## 17. Ma trận kiểm thử recovery

| Kịch bản | Thiết lập | Assertion cốt lõi |
| --- | --- | --- |
| Không có lỗi | Reader/processor/writer đều thành công | `COMPLETED`, output đúng, không có restart |
| Lỗi transient một lần | Dependency ném lỗi rồi trả thành công | Retry trong cùng JobExecution, không duplicate |
| Lỗi transient kéo dài | Dependency luôn ném lỗi retryable | Retry cạn, Step/Job `FAILED` |
| Lỗi không retryable | Exception ngoài retry policy | Không retry vô ích, trạng thái đúng |
| Bản ghi invalid được skip | Cấu hình `skip(InvalidPaymentException.class)` | Skip count tăng, các bản ghi hợp lệ vẫn ghi |
| Vượt giới hạn skip | Nhiều lỗi hơn `skipLimit` | Step `FAILED`, dữ liệu đã commit đúng |
| Restart sau `FAILED` | Dùng lại identifying parameters | JobInstance ID giữ nguyên, JobExecution ID mới |
| Step trước đã hoàn tất | Job nhiều step, step cuối fail | Step `COMPLETED` trước thường không chạy lại |
| `allowStartIfComplete(true)` | Step cần chạy lại có chủ đích | Step đã hoàn tất được start theo cấu hình |
| Job `preventRestart()` | Thất bại rồi gọi lại cùng instance | Restart bị từ chối |
| Instance đã `COMPLETED` | Gọi lại cùng identifying parameters | `JobInstanceAlreadyCompleteException` |
| Execution đang chạy | Trigger trùng trong lúc chạy | `JobExecutionAlreadyRunningException` |
| Restart nhưng file nguồn thay đổi | Thay file/ordering giữa hai lần chạy | Test phát hiện kết quả thiếu/trùng; áp dụng nguồn immutable |
| Container chết đột ngột | Metadata chưa về `FAILED` | Quy trình đối soát, không ép SQL trực tiếp |
| API đã xử lý nhưng response timeout | Writer gọi hệ ngoài | Idempotency key ngăn tác động trùng |

Khi test concurrent execution, dùng tín hiệu như `CountDownLatch` để biết job đầu đã thực sự chạy trước khi gửi yêu cầu thứ hai, tránh dùng `Thread.sleep` với thời gian đoán trước.

## 18. Những lỗi phổ biến khi triển khai recovery

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Mỗi lần restart tạo JobInstance mới | `run.id`/timestamp là identifying | Giữ ổn định khóa định danh nghiệp vụ |
| Job đã thành công nhưng vẫn cố chạy lại | Hiểu nhầm restart với reprocess | Dùng quy trình tái xử lý riêng cho instance đã hoàn tất |
| Retry hàng nghìn lần rồi vẫn fail | Exception không thể tự phục hồi hoặc limit quá lớn | Phân loại lỗi, backoff, giới hạn retry hữu hạn |
| API bị gọi trùng sau timeout | Side effect ngoài transaction, không có idempotency | Idempotency key và đối soát hệ thống đích |
| Restart đọc lại toàn bộ file | Reader không lưu checkpoint hoặc file state sai | Sử dụng ItemStream, saveState, tên reader ổn định |
| Restart bỏ sót bản ghi | Input/sort order thay đổi sau checkpoint | Dùng snapshot nguồn bất biến và sort key ổn định |
| Step đã hoàn tất vẫn ghi dữ liệu lần nữa | Cấu hình `allowStartIfComplete(true)` không phù hợp | Xem lại chính sách restart step và writer |
| Step cũ vẫn `STARTED` sau crash | Process chết trước khi cập nhật metadata | Xác minh execution không còn chạy, thực hiện quy trình vận hành |
| Dùng `System.out` để xác định thành công | Log không phải nguồn trạng thái cuối | Đọc JobExecution, StepExecution và dữ liệu đích |
| Có log lỗi retry nhưng job `COMPLETED` | Lỗi đã được retry thành công | Phân biệt attempt error và final outcome |
| Retry cạn nhưng toàn job vẫn treo | Lỗi tầng client không có timeout | Đặt timeout mạng/DB và giới hạn retry |
| RetryTemplate và Batch cùng retry | Hai lớp retry lồng nhau | Chỉ rõ tầng retry, đếm tổng attempts |
| Job restart thành công nhưng kết quả bị nhân đôi | Writer không idempotent, rollback không bao phủ hệ ngoài | Unique key, outbox, transaction/compensation |
| Xóa metadata để “chạy lại từ đầu” | Bỏ mất state/checkpoint của JobInstance | Giữ metadata và quản lý reprocess riêng |
| Bài test chạy riêng đạt nhưng chạy suite thất bại | DB metadata và fixture không cô lập | Database/schema riêng hoặc dọn trạng thái có kiểm soát |

## 19. Quy trình ra quyết định cho một failure thực tế

Giả sử `paymentImportJob` đang xử lý 2 triệu giao dịch, bị timeout ở writer sau khi 900.000 giao dịch đã commit. Đội vận hành cần quyết định khôi phục thế nào.

**Bước 1 — Xác định trạng thái thực:** đọc JobExecution, StepExecution, thời gian lỗi và metadata checkpoint. Không chỉ dựa vào một thông báo `ERROR`.

**Bước 2 — Phân loại lỗi:** timeout là lỗi transient hay API đã ngừng lâu? Có thể retry an toàn không? Có nguy cơ write đã thành công trước timeout không?

**Bước 3 — Xem transaction và checkpoint:** 900.000 item đã commit ở database nào? Chunk cuối có rollback không? Có external side effect không nằm trong transaction?

**Bước 4 — Kiểm tra tính idempotent:** business key có ngăn duplicate không? Writer có thể ghi lại chunk bị rollback không? Đã có outbox hoặc idempotency token chưa?

**Bước 5 — Chọn retry hoặc restart:** lỗi thoáng qua có thể được xử lý ngay bằng step retry trong lần chạy hiện tại; nếu job đã `FAILED`, sửa hạ tầng và dùng lại identifying parameters để restart.

**Bước 6 — Xác minh kết quả cuối:** JobInstance có execution mới `COMPLETED`; số bản ghi đích, tổng giá trị và số lượng lỗi đúng như yêu cầu. Nếu cần reprocess dữ liệu đã hoàn tất, dùng quy trình riêng với audit và chiến lược thay thế dữ liệu.

**Bước 7 — Bổ sung phòng ngừa:** cập nhật retry policy, timeout, backoff, alert hoặc quy tắc kiểm tra nguồn bất biến để lần sau tự hồi phục tốt hơn.

Một recovery được coi là thành công khi **kết quả nghiệp vụ đúng và trạng thái xử lý có thể truy vết**, không đơn giản vì log không còn exception.

## 20. Bài tập thực hành

Hãy tạo một job `dailySettlementJob` có hai step: `validateFileStep` và `persistSettlementStep`.

Yêu cầu:

1. Step thứ nhất kiểm tra file nguồn, tính checksum và lưu thông tin nguồn để lần restart có thể xác nhận file không thay đổi.
2. Step thứ hai dùng chunk size 50, đọc thanh toán và ghi kết quả vào bảng H2 có khóa duy nhất theo `businessDate + paymentId`.
3. Giả lập lỗi DB tạm thời ở một item rồi cấu hình retry có giới hạn/backoff để job vẫn hoàn tất.
4. Giả lập lỗi DB kéo dài để execution đầu `FAILED`; sau khi sửa lỗi, restart cùng `businessDate` và xác minh JobInstance không đổi.
5. Cho một bản ghi dữ liệu invalid. Chọn chính sách skip hoặc fail có chủ đích, rồi kiểm tra read/write/skip counts.
6. Cho `persistSettlementStep` gặp lỗi giữa chunk và kiểm tra số item ở bảng đích trước và sau restart; không được có duplicate.
7. Phát yêu cầu chạy lần nữa khi instance đã `COMPLETED` và giải thích ngoại lệ.
8. Đổi `businessDate` sang kỳ khác để xác nhận tạo instance mới đúng ý nghĩa nghiệp vụ.

Trong báo cáo test, ghi rõ từng tình huống dùng **retry trong cùng execution**, **skip**, **restart một instance cũ** hay **tạo instance mới**. Cùng một lỗi có thể cần chiến lược khác nhau tùy transaction, side effect và SLA.

## 21. Kết luận

**Retry** xử lý lỗi có khả năng phục hồi nhanh trong phạm vi một step/execution; **restart** khôi phục một JobInstance sau khi lần thực thi trước chưa hoàn tất thành công, thông qua JobExecution mới và metadata checkpoint. Spring Batch cung cấp `JobRepository`, `ExecutionContext`, fault-tolerant chunk, skip/retry policies và listener để xây dựng hai cơ chế này.

Chiến lược recovery đáng tin cậy cần phân loại lỗi, giới hạn số lần thử, kiểm soát thời gian chờ, bảo vệ transaction và idempotency, giữ identifying parameters ổn định khi restart, đồng thời xác minh dữ liệu đầu ra sau mọi lần khôi phục. Khi những điều kiện này rõ ràng, batch job có thể vượt qua lỗi hạ tầng tạm thời hoặc tiếp tục sau sự cố mà không phải đánh đổi tính đúng đắn của dữ liệu.
