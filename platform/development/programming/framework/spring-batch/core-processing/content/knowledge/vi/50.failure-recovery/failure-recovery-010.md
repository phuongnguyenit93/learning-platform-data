# Dữ liệu lỗi hàng loạt trong Spring Batch: phát hiện, cô lập và phục hồi

Một batch job nhập dữ liệu mỗi đêm có thể gặp vài bản ghi không hợp lệ, nhưng cũng có lúc **hàng nghìn bản ghi cùng lỗi** vì hệ thống nguồn đổi định dạng, file bị cắt ngang, dữ liệu bị xuất sai phiên bản hoặc một phụ thuộc bên ngoài ngừng hoạt động. Nếu chỉ cấu hình `skip` thật lớn để job luôn báo `COMPLETED`, kết quả có thể mất phần lớn dữ liệu. Nếu lập tức dừng job khi gặp lỗi đầu tiên, những bản ghi hợp lệ còn lại không được xử lý và đội vận hành khó biết phạm vi sự cố.

Bài học này thuộc **Spring Batch Core Processing → Failure recovery**, tập trung vào cách xử lý **dữ liệu lỗi hàng loạt**: phân loại nguyên nhân, xác định ngưỡng chấp nhận, cấu hình retry/skip/fail, cô lập bản ghi lỗi trong quarantine, ngăn công bố kết quả chưa đầy đủ, thiết kế restart/replay và kiểm thử tình huống nhiều lỗi liên tiếp. Các ví dụ sử dụng **Java 17, Spring Boot 3.x, Spring Batch 5.x, JDBC và JUnit 5**.

## 1. “Dữ liệu lỗi hàng loạt” nghĩa là gì?

Giả sử `importOrdersJob` nhập 100.000 đơn hàng từ CSV. Một ngày thông thường có 12 dòng sai định dạng số tiền. Ngày hôm sau, đơn vị cung cấp đổi tên cột và 78.000 dòng không còn khớp quy tắc đọc. Hai hiện tượng đều tạo exception nhưng **cần phản ứng khác nhau**.

| Tình huống | Dấu hiệu | Cách xử lý hợp lý |
| --- | --- | --- |
| Một vài item sai nghiệp vụ | Phân tán, tỷ lệ thấp, nguyên nhân rõ | Skip theo giới hạn, lưu bản ghi lỗi, xử lý dữ liệu còn lại |
| Lỗi theo cả một nhóm dữ liệu | Cùng `sourceFile`, tenant, partition hoặc ngày nghiệp vụ | Cô lập nhóm lỗi, giữ nhóm khác nếu kiến trúc cho phép |
| Đổi schema/định dạng nguồn | Header sai, nhiều dòng có số cột không hợp lệ | Dừng sớm trước khi ghi output, xác minh hợp đồng dữ liệu |
| File hỏng hoặc chưa ghi xong | Thiếu phần cuối, checksum sai, số dòng bất thường | Từ chối nguồn, yêu cầu gửi lại file/snapshot đầy đủ |
| Cơ sở dữ liệu đích bị lỗi | Nhiều writer call cùng gặp timeout/deadlock | Retry có giới hạn, điều tra hạ tầng; **không skip tất cả item** |
| API phụ trợ ngừng hoạt động | Hàng loạt processor cùng gặp 503/timeout | Backoff, giới hạn retry/concurrency, có thể fail/stop để chạy lại |
| Mất dữ liệu nguồn ở một partition | Một phân vùng không có item | Kiểm tra completeness/manifest, không coi `COMPLETED` là đủ |

Một nguyên tắc: **lỗi dữ liệu ổn định** (ví dụ amount âm, ngày sai định dạng) thường không biến mất khi retry lại cùng item; **lỗi hạ tầng tạm thời** có thể phục hồi sau vài lần thử. Không nên dùng cùng một chính sách cho cả hai nhóm.

### 1.1. Các trạng thái cần phân biệt

```text
Item được đọc
    |
    +--> hợp lệ ------------------------------> xử lý / ghi
    |
    +--> sai dữ liệu --------------------------> SKIP + quarantine?
    |                                                |
    |                                                +--> còn ngân sách?
    |                                                       |       |
    |                                                       Có      Không
    |                                                       |       |
    |                                                  tiếp tục    FAILED
    |
    +--> lỗi tạm thời --> RETRY hữu hạn --> thành công? ----> ghi
                                             |
                                             Không
                                             |
                                        fail/skip theo policy
```

**Retry** thử lại thao tác lỗi trong một execution; **skip** bỏ qua item theo luật; **restart** tạo một `JobExecution` mới cho cùng `JobInstance` sau khi job bị thất bại hoặc dừng; **replay/backfill** là một quy trình chủ động xử lý lại dữ liệu nguồn hoặc tập bản ghi đã bị từ chối. Chúng phục vụ các tình huống khác nhau.

## 2. Xác định hợp đồng chất lượng dữ liệu trước khi chạy

Không thể chọn `skipLimit` phù hợp nếu chưa biết tập dữ liệu được coi là **đủ và đúng**. Với mỗi nguồn batch, nên định nghĩa:

1. **Định danh lô nguồn:** `sourceBatchId`, phiên bản file/snapshot, ngày nghiệp vụ và vùng dữ liệu.
2. **Số bản ghi dự kiến:** manifest cung cấp số dòng, tổng tiền, checksum hoặc một bộ chỉ số kiểm soát khác.
3. **Quy tắc item hợp lệ:** trường bắt buộc, kiểu dữ liệu, khóa duy nhất, khoảng giá trị và quan hệ tham chiếu.
4. **Ngưỡng lỗi cho phép:** số lỗi tuyệt đối, tỷ lệ lỗi, nhóm lỗi không được bỏ qua.
5. **Điều kiện publish:** khi nào output được công bố cho downstream; có chấp nhận kết quả thiếu một phần không.
6. **Cơ chế sửa và gửi lại:** ai sở hữu dữ liệu lỗi, thời hạn sửa, cách chạy lại và cách xác nhận đã phục hồi.

Ví dụ policy nghiệp vụ:

```text
Source: orders-import
Batch: sourceBatchId=orders-20261116-v1
Expected records: 100,000

Fail immediately:
  - missing/invalid header
  - invalid manifest or checksum
  - incompatible schema version

Allowed row rejects:
  - at most 100 invalid records
  - at most 0.5% of input
  - invalid monetary total must not exceed business tolerance

Publish:
  - only after reconciliation passes
  - accepted records and rejected records are accounted for
```

Đây là một **ví dụ về chính sách**, không phải giá trị Spring Batch tự cung cấp. Với 100.000 bản ghi, giới hạn 0,5% tương đương 500 bản ghi nhưng giới hạn tuyệt đối 100 nghiêm ngặt hơn. Nếu yêu cầu *đồng thời thỏa cả hai*, chỉ 100 lỗi cũng có thể là ngưỡng quyết định. Với file 1.000 dòng, 10 lỗi là 1% dù chưa vượt giới hạn 100; chính sách tỷ lệ có thể từ chối lô.

Các bước kiểm tra header, manifest và version thường nên diễn ra **trước khi step ghi dữ liệu**. Một file sai cấu trúc hàng loạt không nên được xử lý như hàng chục nghìn item độc lập cần thử skip.

## 3. Chuẩn bị fixture cho lỗi hàng loạt

Tách dữ liệu nghiệp vụ khỏi mô tả kịch bản lỗi giúp test dễ lặp lại. Ví dụ một tập CSV nhỏ:

```text
src/test/resources/bulk-errors/
├── mostly-valid.csv
├── too-many-invalid.csv
├── invalid-header.csv
├── truncated-file.csv
└── manifest.json
```

`mostly-valid.csv`:

```csv
order_id,customer_id,amount
o-101,c-01,120.00
o-102,c-02,NOT_A_NUMBER
o-103,c-03,0.00
o-104,c-04,77.50
o-105,c-05,25.00
```

Tập này có **năm record nguồn**, ba record hợp lệ và hai record sai `amount`. Một test có `skipLimit >= 2` và cho phép skip đúng loại exception validation sẽ có thể hoàn thành step, với ba item ghi và hai item bị skip ở processor.

`too-many-invalid.csv` có thể chứa hàng trăm dòng như:

```csv
order_id,customer_id,amount
o-201,c-01,BAD
o-202,c-02,BAD
o-203,c-03,BAD
o-204,c-04,BAD
o-205,c-05,BAD
```

Mẫu trên rút gọn để minh họa. Khi tạo fixture thực tế, có thể sinh 1.000 record với 300 record sai rồi đối chiếu với ngưỡng 100, 0,5% hoặc ngưỡng nội bộ. Dữ liệu test nên dùng ID tổng hợp, không lấy dữ liệu khách hàng thực đưa vào repository hay log.

`invalid-header.csv`:

```csv
id_customer,total_amount,currency_code
c-01,120.00,VND
```

File có tên cột khác với hợp đồng `order_id,customer_id,amount`. Để **phát hiện thay đổi header**, cần thực hiện kiểm tra header tường minh trước khi xử lý; việc cấu hình `FlatFileItemReader.linesToSkip(1)` đơn thuần chỉ bỏ qua dòng đầu và không đảm bảo tên cột đúng.

Manifest ví dụ:

```json
{
  "sourceBatchId": "orders-20261116-v1",
  "schemaVersion": 3,
  "recordCount": 5,
  "businessDate": "2026-11-16",
  "checksumSha256": "example-only-replace-with-real-checksum"
}
```

Trường checksum trên chỉ là placeholder, không phải digest hợp lệ. Khi chạy thật, cần kiểm tra checksum trên đúng nội dung đã thỏa thuận với nguồn, xác minh file đã được ghi xong (ví dụ qua file `.done` hoặc publish atomically) và tránh đọc file khi nguồn còn thay đổi.

## 4. Phân loại exception để không skip lỗi hệ thống

Spring Batch cho phép cấu hình fault tolerance trong chunk step qua `faultTolerant()`. Có thể chia:

| Loại lỗi | Ví dụ exception | Chính sách đề xuất |
| --- | --- | --- |
| Dữ liệu nghiệp vụ không hợp lệ | `InvalidOrderException` | Skip giới hạn + quarantine |
| Dòng CSV parse sai | `FlatFileParseException` | Skip có giới hạn nếu được phép, hoặc fail sớm nếu xuất hiện hàng loạt |
| Kết nối/API timeout tạm thời | `TransientDataAccessException`, exception dịch vụ tùy chỉnh | Retry có giới hạn và backoff |
| Vi phạm hợp đồng toàn file | `SourceSchemaMismatchException` | Fail trước khi ingest |
| Sai cấu hình, thiếu schema đích | Exception config/SQL không thể phục hồi | Fail, điều tra trước khi chạy lại |
| Ràng buộc unique ở DB | `DuplicateKeyException` | Theo quy tắc idempotency/duplicate riêng, không tự động skip mọi lỗi DB |

Không nên viết:

```java
.skip(Exception.class)
.skipLimit(1000000)
```

Vì cách này có thể che lỗi hệ thống hoặc lỗi lập trình, khiến job tiếp tục với output thiếu dữ liệu. Tương tự, retry tất cả exception vô hạn sẽ khiến dữ liệu lỗi ổn định bị xử lý lại liên tục mà không có khả năng thành công.

### 4.1. `skipLimit` đếm gì?

Với cấu hình:

```java
.faultTolerant()
.skip(InvalidOrderException.class)
.skip(FlatFileParseException.class)
.skipLimit(20)
```

Spring Batch cho phép **tối đa 20 item bị skip trong một StepExecution**, tính chung các trường hợp skip ở read/process/write theo policy. Khi xuất hiện item cần skip thứ 21, step thường chuyển sang `FAILED` do vượt giới hạn. `skipLimit(20)` không có nghĩa “cho phép 20 lỗi ở mỗi pha”, cũng không có nghĩa “20 lần retry”.

`readSkipCount`, `processSkipCount`, `writeSkipCount` và `skipCount` trong `StepExecution` giúp quan sát lỗi đã được skip. Một attempt lỗi rồi retry thành công không nhất thiết tăng `skipCount`. Cần kiểm tra số lần retry bằng listener/metric riêng nếu muốn biết chính xác.

## 5. Xây dựng job mẫu để xử lý record lỗi có giới hạn

Giả sử nguồn là CSV ba cột, đầu ra là bảng `accepted_orders`. Ta đọc toàn bộ giá trị ban đầu dưới dạng chuỗi và chuyển đổi/validate trong processor, nhờ đó phân biệt được **lỗi parse cấu trúc** với **lỗi nghiệp vụ**.

### 5.1. Model và exception nghiệp vụ

File `OrderModels.java` (các kiểu dùng trong package ví dụ):

```java
package com.example.batch;

import java.math.BigDecimal;

record RawOrder(
        String orderId,
        String customerId,
        String amountText) {}

record ValidOrder(
        String orderId,
        String customerId,
        BigDecimal amount) {}

class InvalidOrderException extends RuntimeException {
    InvalidOrderException(String reasonCode) {
        super(reasonCode);
    }
}
```

Trong ứng dụng thật, `reasonCode` cần nằm trong một tập mã được duyệt. Không truyền nguyên dòng CSV, email, số tài khoản hoặc dữ liệu nhạy cảm vào message của exception vì stack trace có thể bị ghi ra log.

### 5.2. Reader nhận tên file từ `JobParameters`

Ví dụ cấu hình bean theo step scope:

```java
package com.example.batch;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;

@Configuration
class OrderReaderConfig {

    @Bean
    @StepScope
    FlatFileItemReader<RawOrder> orderReader(
            @Value("#{jobParameters['inputFile']}") String inputFile) {

        return new FlatFileItemReaderBuilder<RawOrder>()
                .name("orderReader")
                .resource(new FileSystemResource(inputFile))
                .linesToSkip(1)
                .delimited()
                .names("order_id", "customer_id", "amount")
                .fieldSetMapper(fields -> new RawOrder(
                        fields.readString("order_id"),
                        fields.readString("customer_id"),
                        fields.readString("amount")))
                .build();
    }
}
```

`@StepScope` cho phép lấy `inputFile` ở thời điểm job chạy. Với `DelimitedLineTokenizer` ở cấu hình mặc định, dòng có sai số cột có thể gây lỗi đọc như `FlatFileParseException`; giá trị `amount=NOT_A_NUMBER` vẫn được đọc thành `String` và sẽ bị processor xác định là không hợp lệ.

**Lưu ý vận hành:** tên file từ `JobParameters` phải được kiểm tra theo allowlist thư mục, phiên bản nguồn và quyền đọc; không dùng đường dẫn tùy ý từ nguồn không tin cậy. Ví dụ chỉ minh họa cơ chế đọc file. Cần bước preflight xác thực header, checksum, manifest và tình trạng file đã hoàn tất trước khi cho job ghi dữ liệu.

### 5.3. Processor kiểm tra dữ liệu

```java
package com.example.batch;

import java.math.BigDecimal;

import org.springframework.batch.item.ItemProcessor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderProcessorConfig {

    @Bean
    ItemProcessor<RawOrder, ValidOrder> orderProcessor() {
        return row -> {
            if (row.orderId() == null || row.orderId().isBlank()) {
                throw new InvalidOrderException("ORDER_ID_REQUIRED");
            }
            if (row.customerId() == null
                    || row.customerId().isBlank()) {
                throw new InvalidOrderException("CUSTOMER_ID_REQUIRED");
            }

            BigDecimal amount;
            try {
                amount = new BigDecimal(row.amountText());
            } catch (NumberFormatException | NullPointerException ex) {
                throw new InvalidOrderException("INVALID_AMOUNT");
            }

            if (amount.signum() <= 0) {
                throw new InvalidOrderException("NON_POSITIVE_AMOUNT");
            }

            return new ValidOrder(
                    row.orderId(), row.customerId(), amount);
        };
    }
}
```

Với fixture `mostly-valid.csv`, item `o-102` có `INVALID_AMOUNT`, item `o-103` có `NON_POSITIVE_AMOUNT`; các item còn lại sẽ được chuyển sang `ValidOrder`. Nếu cùng một lô có quá nhiều lỗi, chính sách step phải dừng hoặc chặn publish thay vì âm thầm bỏ toàn bộ item.

### 5.4. Writer và step fault-tolerant

Ví dụ writer dùng Spring JDBC và cùng datasource/transaction manager để ghi database:

```java
package com.example.batch;

import javax.sql.DataSource;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.batch.item.file.FlatFileParseException;

@Configuration
class ImportOrdersJobConfig {

    @Bean
    JdbcBatchItemWriter<ValidOrder> orderWriter(DataSource dataSource) {
        return new JdbcBatchItemWriterBuilder<ValidOrder>()
                .dataSource(dataSource)
                .sql("""
                     INSERT INTO accepted_orders
                         (order_id, customer_id, amount)
                     VALUES (:orderId, :customerId, :amount)
                     """)
                .itemSqlParameterSourceProvider(item ->
                        new MapSqlParameterSource()
                                .addValue("orderId", item.orderId())
                                .addValue("customerId", item.customerId())
                                .addValue("amount", item.amount()))
                .build();
    }

    @Bean
    Step importOrdersStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            FlatFileItemReader<RawOrder> orderReader,
            @Qualifier("orderProcessor")
            ItemProcessor<RawOrder, ValidOrder> processor,
            JdbcBatchItemWriter<ValidOrder> writer) {

        return new StepBuilder("importOrdersStep", jobRepository)
                .<RawOrder, ValidOrder>chunk(100, transactionManager)
                .reader(orderReader)
                .processor(processor)
                .writer(writer)
                .faultTolerant()
                .retry(TransientDataAccessException.class)
                .retryLimit(3)
                .skip(InvalidOrderException.class)
                .skip(FlatFileParseException.class)
                .skipLimit(20)
                .build();
    }

    @Bean
    Job importOrdersJob(
            JobRepository jobRepository,
            @Qualifier("importOrdersStep") Step step) {

        return new JobBuilder("importOrdersJob", jobRepository)
                .start(step)
                .build();
    }
}
```

Code giả định bảng `accepted_orders` và schema `BATCH_*` đã có trong database. Trong hệ thống thật, bảng đích cần ràng buộc khóa nghiệp vụ và cơ chế idempotency để restart/replay không ghi trùng. Có thể dùng staging table thay cho bảng đã publish như phần 8.

`retryLimit(3)` trong Spring Batch là **tổng tối đa ba lần thử tính cả lần đầu** theo policy; lỗi DB tạm thời có thể được thử lại. Hai loại exception dữ liệu được phép skip trong giới hạn 20. Không thêm `Exception.class` vào `skip` hoặc `retry` chỉ để job “chạy hết file”.

### 5.5. Khi phải fail sớm thay vì skip

Với header sai, checksum không khớp, schema version không tương thích hoặc manifest bất thường, **không nên đưa toàn bộ file vào step với `skipLimit` rất lớn**. Hãy chạy bước preflight trước khi import:

```text
validateSourceStep
    |
    +-- schema/manifest invalid --> JOB FAILED, no import
    |
    +-- source valid -----------> importOrdersStep
                                       |
                                       v
                               reconcileAndPublishStep
```

`validateSourceStep` có thể là tasklet xác nhận header, checksum, version và số bản ghi dự kiến. Nếu preflight thất bại, ném exception phù hợp để job dừng trước khi ghi output. Một job có nhiều step cần thiết kế luồng và điều kiện chuyển trạng thái theo quy tắc nghiệp vụ, không chỉ dựa vào tên step.

## 6. Giới hạn số lỗi: ngưỡng tuyệt đối và tỷ lệ

Giới hạn **tuyệt đối** của Spring Batch được xử lý trực tiếp qua `skipLimit`. Nhưng giới hạn **tỷ lệ lỗi** (ví dụ quá 0,5%) phải được triển khai thêm vì `skipLimit` không tự biết tổng số bản ghi dự kiến.

### 6.1. Dựa trên nguồn đã biết tổng số item

Giả sử manifest khai báo `recordCount=1000` và chính sách cho phép tối đa 0,5% lỗi:

```text
expectedRows = 1000
maxRejectedByRatio = floor(expectedRows * 0.005) = 5
maxRejectedAbsolute = 100
effectiveAllowed = min(5, 100) = 5
```

Trong một step nhập file, có thể thiết lập giới hạn skip theo chính sách đã tính trước, ví dụ `skipLimit(5)` cho lô đó. Nhưng khi giới hạn thay đổi theo `JobParameters`/manifest, cần tạo policy theo scope phù hợp thay vì hardcode số 5 trong shared singleton step.

### 6.2. Khi chưa biết tổng chính xác lúc bắt đầu

Nếu không có manifest tin cậy, có thể kiểm tra tỷ lệ sau khi step kết thúc, hoặc ghi counter theo thời gian và phát cảnh báo theo cửa sổ quan sát. Cần đặc biệt thận trọng với mẫu số:

- `readCount`: số item đọc thành công, không phải số dòng nguồn trong mọi reader.
- `readSkipCount`: số lỗi đọc được skip.
- `processSkipCount`: item bị skip ở processor.
- `writeSkipCount`: item bị skip ở writer.
- `skipCount`: tổng skip ở mức step, theo logic framework.

Với file line-oriented đơn giản, `readCount + readSkipCount` có thể gần với số record đã thử đọc, nhưng có trường hợp header, filtered item, multi-line record, retry hoặc reader tùy biến khiến phép tính không đại diện chính xác số record nghiệp vụ. Đối với reconciliation có yêu cầu chặt chẽ, nên dùng **manifest hoặc counter nguồn có định nghĩa rõ**.

Nếu kiểm tra tỷ lệ **sau** khi import và thấy không đạt, cần ngăn publish dữ liệu dù job đã ghi staging. Một `StepExecutionListener.afterStep` chỉ thay `ExitStatus` chưa tự hoàn tác các chunk đã commit; với output chính thức, nên dùng mô hình staging và bước publish có điều kiện.

### 6.3. Tại sao phải có ngưỡng nhiều cấp?

Chính sách thực tế có thể kết hợp:

| Điều kiện | Ví dụ | Phản ứng |
| --- | --- | --- |
| Một item lỗi | 1 bản ghi invalid | Skip + quarantine |
| Tăng nhanh nhưng chưa vượt mức | 0,3% lỗi trong 10.000 item | Cảnh báo và tăng mức quan sát |
| Vượt tỷ lệ lỗi | 1,2% lỗi, ngưỡng 0,5% | Không publish; fail luồng theo policy |
| Vượt số lượng lỗi | 101 reject, ngưỡng 100 | Dừng xử lý step |
| Lỗi cấu trúc toàn nguồn | Thiếu header/schema sai | Fail ngay ở preflight |
| Lỗi hệ thống hàng loạt | DB unavailable, API 503 liên tục | Hạn chế retry, dừng/restart có kiểm soát |

Không cần áp dụng một công thức cho mọi lô: dữ liệu tài chính hoặc đối soát có thể yêu cầu **zero reject**, trong khi lô thu thập dữ liệu không quan trọng có thể chấp nhận một tỷ lệ lỗi nhỏ.

## 7. Quarantine: giữ bản ghi lỗi để điều tra và sửa

**Quarantine** là vùng lưu trữ có kiểm soát dành cho dữ liệu bị từ chối. Mục tiêu là không mất bằng chứng cần thiết để sửa nguồn, đồng thời không đưa item không hợp lệ vào bảng đích chính thức.

Một bản ghi quarantine có thể chứa:

| Trường | Vai trò |
| --- | --- |
| `source_batch_id` | Định danh lô file/snapshot ban đầu |
| `record_locator` | Vị trí nguồn hoặc ID dòng ổn định để tìm lại |
| `stage` | `READ`, `PROCESS` hoặc `WRITE` |
| `reason_code` | Mã lỗi cố định như `INVALID_AMOUNT` |
| `rejected_at` | Thời điểm lỗi được ghi nhận |
| `status` | `NEW`, `REVIEWED`, `CORRECTED`, `REPLAYED` ... |
| `payload_pointer` hoặc encrypted payload | Đường dẫn/khóa tra cứu dữ liệu gốc trong kho hạn chế quyền |
| `job_execution_id` | Liên kết với metadata của lần chạy |

Nếu chỉ log `row invalid` rồi bỏ qua, không có cách biết bản ghi nào cần sửa khi số lượng lỗi lớn. Mặt khác, **không nên in nguyên payload vào log** chỉ để dễ debug; payload có thể chứa email, số tài khoản hoặc dữ liệu nhạy cảm. Kho quarantine cần quyền truy cập, mã hóa, retention và dấu vết thao tác phù hợp.

### 7.1. Dùng `SkipListener` để ghi nhận item bị bỏ qua

`SkipListener<I,O>` trong Spring Batch 5 cung cấp:

```java
void onSkipInRead(Throwable error);
void onSkipInProcess(I item, Throwable error);
void onSkipInWrite(O item, Throwable error);
```

Ví dụ listener ghi sự kiện có cấu trúc và tham chiếu an toàn, **không in item/exception gốc**:

```java
package com.example.batch;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.SkipListener;

public class SafeRejectLogListener
        implements SkipListener<RawOrder, ValidOrder> {

    private static final Logger log =
            LoggerFactory.getLogger(SafeRejectLogListener.class);

    @Override
    public void onSkipInRead(Throwable error) {
        // Khi parse lỗi, chưa chắc có một RawOrder hợp lệ để lấy key.
        log.warn("event=order_rejected stage=read "
                + "record_ref=unavailable reason=BAD_SOURCE_RECORD");
    }

    @Override
    public void onSkipInProcess(RawOrder item, Throwable error) {
        log.warn("event=order_rejected stage=process "
                + "reason={}", safeReason(error));
    }

    @Override
    public void onSkipInWrite(ValidOrder item, Throwable error) {
        log.warn("event=order_rejected stage=write "
                + "reason=WRITE_REJECTED");
    }

    private String safeReason(Throwable error) {
        if (error instanceof InvalidOrderException) {
            // Mã cố định, không lấy Throwable.getMessage().
            return "INVALID_ORDER";
        }
        return "UNCLASSIFIED_FAILURE";
    }
}
```

Listener trên minh họa **khi nào một item thực sự bị skip**; nó không phải toàn bộ quarantine store. Có thể gắn listener bằng `.listener(rejectListener)` sau `faultTolerant()` trong builder của step ở phần 5. Nếu cần ghi item gốc hoặc vị trí cụ thể để sửa, một `RejectRepository`/quarantine writer riêng phải xử lý việc đó theo cơ chế transaction và quyền truy cập được kiểm soát.

### 7.2. Vì sao `onSkipInRead` không có `item`?

Nếu parser không tạo được `RawOrder`, callback skip ở read không có một item hợp lệ để truyền vào. Một số reader có thể cung cấp line number hoặc source offset trong exception, nhưng `FlatFileParseException` còn có thể giữ **nguyên dòng đầu vào**. Không nên gọi `getInput()` hoặc log toàn bộ exception trong kênh phổ thông. Muốn replay, hãy dùng định danh file/version và offset đã được kiểm duyệt để tra cứu nội dung trong kho nguồn bảo vệ.

### 7.3. Quarantine có transaction và idempotency

`SkipListener` được Spring Batch gọi theo lifecycle của fault-tolerant step. Khi ghi quarantine vào database, nên làm rõ:

- Bảng reject dùng **cùng datasource và transaction manager** hay một transaction riêng?
- Nếu chunk rollback, bản ghi reject có rollback theo không?
- Nếu process crash ngay sau commit, có cơ chế đối chiếu để tìm reject chưa được đồng bộ không?
- Khi restart/replay, làm sao tránh insert trùng reject hoặc duplicate output?

Đối với quarantine cần độ tin cậy cao, có thể ghi reject/outbox cùng transaction với dữ liệu staging, dùng khóa duy nhất theo `(source_batch_id, record_locator, reason_code)` hoặc business key phù hợp. Sau commit, một worker khác có thể đẩy dữ liệu vào kho quarantine bảo mật. Tùy nguồn và cơ chế skip, cần test lỗi ở cả read/process/write; đừng mặc định tất cả event log hoặc callback tạo đúng một record bền vững trong mọi tình huống.

## 8. Dùng staging và bước publish có điều kiện

Với nhiều lỗi hàng loạt, vấn đề lớn không chỉ là `FAILED` hay `COMPLETED`, mà là **downstream có được phép đọc dữ liệu thiếu hay không**. Một kiến trúc an toàn là:

```text
Incoming source + manifest
        |
        v
ValidateSourceStep  ---- invalid ---> FAILED + alert
        |
        v
ImportToStagingStep
        |            \
        |             \-- invalid rows --> Quarantine (restricted)
        v
ReconcileStep
        |
        +-- rejected > allowed ------> No publish, FAILED
        +-- counts/checksum mismatch -> No publish, FAILED
        |
        v
PublishStep
        |
        v
Published snapshot / ready marker
        |
        v
Downstream consumers
```

Staging gắn `sourceBatchId`/`runId` để phân biệt dữ liệu đang xử lý với dữ liệu đã công bố. Chỉ khi tất cả điều kiện chất lượng đạt, `PublishStep` mới chuyển snapshot mới thành phiên bản đang phục vụ người dùng (ví dụ cập nhật con trỏ phiên bản trong một transaction hoặc publish file hoàn chỉnh bằng thao tác atomic phù hợp).

Nếu step nhập dữ liệu ghi trực tiếp vào bảng production, một lỗi ở item thứ 20.001 có thể khiến những chunk trước đó đã commit; việc `JobExecution` chuyển `FAILED` **không tự rollback toàn bộ các chunk đã hoàn thành trước đó**. Chính vì vậy, staging/publish gate đặc biệt hữu ích khi lỗi hàng loạt làm hỏng tính đầy đủ của kết quả.

### 8.1. Phân biệt hoàn thành kỹ thuật và hoàn thành nghiệp vụ

Một step có thể `COMPLETED` với 20 item bị skip vì đang trong `skipLimit`. Điều đó có nghĩa framework xử lý theo policy kỹ thuật, **không chắc output được chấp nhận**. Có thể cần một `reconcileAndPublishStep` kiểm tra:

```text
source_expected_count
  = accepted_count
  + rejected_count
  + filtered_count (nếu có, theo quy tắc riêng)
```

Không nên áp dụng công thức này máy móc nếu có record nhiều dòng, duplicate đã được loại, ghi đè/upsert hoặc một record tạo nhiều dòng đích. Hợp đồng đối soát phải định nghĩa rõ mỗi counter đếm đối tượng nào.

Ngoài count, dữ liệu tài chính có thể cần tổng amount, checksum theo khóa, phiên bản nguồn và tổng theo nhóm. Một tổng count khớp vẫn có thể che việc mất một record và lặp một record khác.

## 9. Restart và replay khi dữ liệu đã được sửa

Giả sử ngày 16/11 có `sourceBatchId=orders-20261116-v1`, job nhập thất bại vì vượt `skipLimit`. Sau khi đội nguồn sửa file, có hai lựa chọn:

### 9.1. Restart cùng `JobInstance`

Khi source input và checkpoint vẫn phù hợp, có thể **restart** job đã `FAILED` bằng cùng các identifying `JobParameters`:

```text
JobInstance(importOrdersJob, sourceBatchId=orders-20261116-v1)
├── JobExecution #1: FAILED
└── JobExecution #2: restart attempt
```

Điều kiện:

- `JobRepository` còn metadata và step/job cho phép restart.
- Reader có trạng thái checkpoint đúng; input nguồn vẫn **bất biến** so với vị trí đã đọc.
- Writer/quarantine có idempotency, không ghi trùng khi một chunk được xử lý lại.
- Chính sách không thay đổi nguồn dưới cùng ID một cách âm thầm.

Nếu file nguồn đã bị thay nội dung nhưng vẫn dùng cùng đường dẫn và checkpoint cũ, reader có thể tiếp tục từ vị trí không còn tương ứng với bản ghi ban đầu. Với dữ liệu lỗi hàng loạt do file hỏng, đây là rủi ro nghiêm trọng.

### 9.2. Replay từ nguồn đã sửa hoặc lô mới

Khi dữ liệu nguồn đã được sửa hoặc thay thế, cách an toàn thường là tạo **phiên bản nguồn mới**:

```text
orders-20261116-v1  -> REJECTED / NOT_PUBLISHED
orders-20261116-v2  -> VALIDATED -> INGESTED -> PUBLISHED
```

Chạy lại với `sourceBatchId` nhận diện mới, lưu quan hệ `supersedes=v1`, và quyết định rõ xử lý dữ liệu staging cũ thế nào. Nếu chỉ replay những item trong quarantine, cần:

- Có khóa business/source ổn định để biết item được sửa là item nào.
- Không đưa record đã được chấp nhận trước đó vào lại một cách vô tình.
- Áp dụng upsert hoặc unique constraint theo hợp đồng dữ liệu.
- Đối soát lại tổng số record và tổng nghiệp vụ sau khi replay.
- Đánh dấu item reject đã sửa, đã replay và có kết quả cuối.

**Đổi identifying parameters tạo `JobInstance` mới**, không phải một restart của instance cũ. Đây là cách phù hợp khi cần nhập lại một phiên bản nguồn khác, nhưng phải quản lý dữ liệu đích để không tạo duplicate.

### 9.3. Không xóa bảng `BATCH_*` để chạy lại

Xóa metadata có thể làm mất khả năng đối chiếu, checkpoint và tính nhất quán của restart. Trong vận hành, hãy dùng API và chính sách của Spring Batch, version nguồn rõ ràng và quy trình replay được kiểm soát; không sửa thủ công trạng thái `JobExecution` chỉ để ép job chạy.

## 10. Lỗi hạ tầng hàng loạt cần xử lý khác lỗi dữ liệu

Khi database không kết nối được hoặc API trả 503 cho mọi item, việc đưa hàng nghìn item vào quarantine với lý do “invalid” là sai ngữ nghĩa. Các item **có thể hợp lệ**, lỗi nằm ở phụ thuộc bên ngoài.

Ví dụ processor gọi dịch vụ:

```text
item 1: HTTP 503 -> retry -> HTTP 503
item 2: HTTP 503 -> retry -> HTTP 503
item 3: HTTP 503 -> retry -> HTTP 503
...
```

Nếu mỗi item retry ba lần, một đợt outage dễ tạo hàng triệu request vô ích. Cần:

1. Phân loại lỗi phụ thuộc bằng exception riêng, ví dụ `PartnerUnavailableException`.
2. Dùng retry có `retryLimit` và backoff phù hợp, không retry lỗi validation.
3. Giới hạn số request đồng thời và tổng ngân sách retry theo job/run window.
4. Khi tỷ lệ lỗi hạ tầng tăng cao, áp dụng fail/stop/circuit breaker ở tầng điều phối hoặc service để tránh gây thêm tải.
5. Restart sau khi phụ thuộc phục hồi bằng **cùng identifying parameters** nếu mục tiêu là tiếp tục instance cũ.

Spring Batch hỗ trợ retry ở fault-tolerant step; các chính sách circuit breaker và ngưỡng lỗi theo toàn job thường cần logic bổ sung hoặc công cụ phù hợp. Không giả định `.retryLimit(3)` tự ngăn sự cố lan rộng khi mỗi item có thể được retry ba lần.

## 11. Quan sát phạm vi lỗi hàng loạt bằng metric và log

Một dashboard nên hiển thị **mức độ ảnh hưởng**, thay vì chỉ in exception từng item:

| Metric | Ý nghĩa |
| --- | --- |
| `source_expected_count` | Tổng record dự kiến từ manifest |
| `read_count` | Item reader đã đọc thành công theo Spring Batch |
| `read_skip_count` | Lỗi đọc được skip |
| `process_skip_count` | Item bị skip ở processor |
| `write_skip_count` | Item bị skip ở writer |
| `skip_count` | Tổng số skip của step |
| `accepted_count` | Item nghiệp vụ được chấp nhận theo hợp đồng |
| `quarantined_count` | Record được lưu bền vững trong quarantine |
| `retry_attempt_count` | Số attempt retry do listener/metric riêng đo |
| `unpublished_batch_count` | Lô chưa đạt điều kiện publish |
| `error_rate_by_reason` | Tỷ lệ lỗi theo mã đã phân loại |

`StepExecution` cung cấp các chỉ số:

```java
for (var step : jobExecution.getStepExecutions()) {
    log.info(
            "event=batch_step_summary step={} status={} "
            + "read={} write={} skip={} read_skip={} "
            + "process_skip={} write_skip={} rollback={}",
            step.getStepName(),
            step.getStatus(),
            step.getReadCount(),
            step.getWriteCount(),
            step.getSkipCount(),
            step.getReadSkipCount(),
            step.getProcessSkipCount(),
            step.getWriteSkipCount(),
            step.getRollbackCount());
}
```

Đây là đoạn minh họa trong scope có `jobExecution` và logger `log`. Không suy ra số lần retry trực tiếp từ `readCount`, `writeCount` hoặc `rollbackCount`, vì transaction và fault tolerance có thể gọi lại một số thao tác mà không tăng các counter theo cách người đọc dự đoán.

Không log toàn bộ `item.toString()`, dòng CSV hay `Throwable` chưa lọc. Exception parse có thể chứa input gốc, và `JobParameters` có thể chứa thông tin nhạy cảm. Nên log mã lỗi cố định, job/step execution ID và reference đã được phê duyệt. Hạn chế gắn `record_id` hoặc `sourceBatchId` có cardinality cao vào metric labels; dùng chúng làm field tìm kiếm có kiểm soát trong log/audit.

### 11.1. Cảnh báo sớm khi lỗi bùng phát

Một ngưỡng skip tuyệt đối chỉ chặn được sau khi đủ số item lỗi. Với file rất lớn, có thể cần thêm giám sát theo **cửa sổ quan sát**, ví dụ 500 item gần nhất có hơn 20% lỗi hoặc 50 lỗi cùng một mã trong 60 giây. Quy tắc này cần một bộ đếm thread-safe hoặc công cụ giám sát theo thời gian và phải tránh false positive khi số item còn ít.

Metric/cảnh báo cấp job không thay thế `skipLimit`: cả hai nên phối hợp. Cảnh báo có thể đưa job vào trạng thái `STOPPING` hoặc đánh dấu nguồn cần kiểm tra theo policy vận hành, nhưng phải có cơ chế stop/rollback an toàn để không gây thêm dữ liệu dở dang.

## 12. Kiểm thử recovery với nhiều record lỗi

Cần kiểm thử cả **số lượng** và **kết quả nghiệp vụ**, không chỉ assert `BatchStatus.COMPLETED`.

### 12.1. Ma trận kiểm thử

| Kịch bản | Dữ liệu test | Kỳ vọng |
| --- | --- | --- |
| Không có lỗi | 1.000 record hợp lệ | `COMPLETED`, đủ output |
| Ít lỗi validation | 1.000 record, 2 sai | `COMPLETED` nếu policy chấp nhận; 2 quarantine |
| Đúng giới hạn skip | 100 record, 20 sai với `skipLimit(20)` | Có thể `COMPLETED` khi những điều kiện khác đạt |
| Vượt giới hạn skip | 100 record, 21 sai | Step/job `FAILED` tại lỗi skip tiếp theo |
| Header/schema sai | File version không phù hợp | Preflight `FAILED`, không nhập vào staging |
| File chưa hoàn tất | Checksum/số dòng không khớp | Từ chối file trước khi publish |
| DB/API outage | Tất cả item gặp lỗi tạm thời | Retry/backoff giới hạn, cuối cùng fail/stop |
| Writer lỗi một chunk | Transaction lỗi sau khi một số chunk đã commit | Không publish dữ liệu staging chưa đủ |
| Restart sau lỗi | Cùng identifying parameters, metadata còn | Tiếp tục đúng checkpoint và không duplicate |
| Replay nguồn đã sửa | File v2 có source batch mới | Dữ liệu đúng, quarantine được đối soát |
| Quarantine writer thất bại | Không lưu được rejected record | Không âm thầm báo xử lý thành công khi mất bằng chứng |

### 12.2. Ví dụ integration test với `JobLauncherTestUtils`

Trong dự án dùng Spring Boot, có thể thêm:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}
```

Ví dụ lớp test dưới đây giả định các bean job ở phần 5 đã được nạp, H2 đã tạo bảng `BATCH_*` và `accepted_orders`, và `src/test/resources/bulk-errors/mostly-valid.csv` chứa năm record của phần 3:

```java
package com.example.batch;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBatchTest
@SpringBootTest(properties = {
        "spring.batch.job.enabled=false",
        "spring.batch.jdbc.initialize-schema=always"
})
class BulkInvalidOrdersTest {

    @Autowired
    private JobLauncherTestUtils launcher;

    @Autowired
    @Qualifier("importOrdersJob")
    private Job job;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @BeforeEach
    void prepare() {
        launcher.setJob(job);
        // Chỉ dọn bảng output trong database test riêng biệt.
        jdbcTemplate.update("DELETE FROM accepted_orders");
    }

    @Test
    void skipsTwoInvalidOrdersAndWritesThree() throws Exception {
        String path = new ClassPathResource(
                "bulk-errors/mostly-valid.csv")
                .getFile()
                .getAbsolutePath();

        JobParameters params = new JobParametersBuilder()
                .addString("inputFile", path)
                .addString("sourceBatchId", "fixture-mostly-valid")
                .addString("run.id", UUID.randomUUID().toString())
                .toJobParameters();

        JobExecution result = launcher.launchJob(params);

        assertThat(result.getStatus()).isEqualTo(BatchStatus.COMPLETED);
        StepExecution step = result.getStepExecutions()
                .iterator().next();

        assertThat(step.getReadCount()).isEqualTo(5);
        assertThat(step.getProcessSkipCount()).isEqualTo(2);
        assertThat(step.getSkipCount()).isEqualTo(2);
        assertThat(step.getWriteCount()).isEqualTo(3);

        Integer saved = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM accepted_orders",
                Integer.class);
        assertThat(saved).isEqualTo(3);
    }
}
```

`ClassPathResource.getFile()` phù hợp trong test khi resource thực sự nằm trên filesystem; không áp dụng nguyên xi cho resource đóng gói trong executable JAR. Test dùng `run.id` riêng cho mỗi lần chạy để tránh đụng `JobInstance` đã hoàn thành; **không thay đổi identifying parameters khi kiểm thử restart cùng instance**.

Ví dụ trên chỉ kiểm tra trường hợp số lỗi **chưa vượt** `skipLimit(20)` và output của một bảng thử nghiệm. Để kiểm tra ngưỡng hàng loạt, tạo thêm test với 21 dòng invalid, xác nhận `FAILED` và dữ liệu chưa được publish. Khi dùng staging, test phải kiểm tra trạng thái publish ngoài các counter kỹ thuật.

### 12.3. Kiểm thử restart và tính bất biến của nguồn

Một kịch bản đầy đủ:

1. Tạo file phiên bản `v1`, manifest có checksum và batch ID ổn định.
2. Chạy job, cho writer lỗi ở một chunk đã chọn rồi xác nhận execution `FAILED`.
3. Giữ nguyên file `v1`, `JobRepository` và **cùng identifying `JobParameters`**; chạy lại để kiểm tra restart.
4. Xác nhận số record output không trùng, quarantine không lặp và checkpoint phản ánh đúng phần đã xử lý.
5. Thay dữ liệu file bằng `v2`, tạo `sourceBatchId` mới; chạy replay theo chính sách thay thế/chỉnh sửa output.
6. Đối soát input, accepted, rejected và output published. Không chỉ kiểm tra `COMPLETED`.

Nếu dùng database chung cho nhiều test, cần cô lập dữ liệu/metadata theo schema hoặc test container. Không gọi lệnh xóa toàn bộ metadata batch vào database có execution đang hoạt động.

## 13. Những lỗi thiết kế thường gặp

| Sai lầm | Tác hại | Hướng xử lý |
| --- | --- | --- |
| `skip(Exception.class)` với limit rất lớn | Che lỗi hệ thống và lỗi lập trình | Skip allowlist lỗi dữ liệu cụ thể |
| Retry validation vô hạn | Tốn CPU, I/O và thời gian mà dữ liệu không đổi | Đưa vào reject/quarantine |
| Không kiểm tra header/manifest | Có thể reject hàng loạt vì đổi schema | Preflight file trước khi nhập |
| Chỉ đặt số lượng skip, không xét tỷ lệ | Lô nhỏ có thể mất phần lớn dữ liệu | Thêm tỷ lệ dựa trên tổng được định nghĩa rõ |
| Job `COMPLETED` nên publish ngay | Output có thể thiếu nhiều item đã skip | Reconcile và publish theo gate |
| Ghi trực tiếp bảng chính rồi job fail | Chunk trước đã commit, downstream thấy dữ liệu dở | Staging + phiên bản + publish atomic |
| Không lưu item lỗi | Không có đầu vào để sửa/replay | Quarantine có source locator và reason code |
| Log nguyên CSV/exception | Lộ thông tin khách hàng | Mã lỗi cố định và reference được bảo vệ |
| Thay file nguồn nhưng giữ checkpoint cũ | Restart đọc sai vị trí/nội dung | Giữ nguồn bất biến, dùng version mới khi file thay đổi |
| Đổi `run.id` khi muốn restart | Tạo instance mới, có thể xử lý lặp | Giữ nguyên identifying parameters |
| Coi sự cố API 503 là item invalid | Quarantine dữ liệu hợp lệ hàng loạt | Retry/backoff có giới hạn, fail khi hạ tầng lỗi |
| Replay không có idempotency | Ghi trùng dữ liệu và tạo reject trùng | Unique key/upsert, versioning, audit và reconciliation |
| Chỉ đếm dòng log là số item lỗi | Retry/rollback có thể sinh log trùng | Dùng StepExecution và kho audit có transaction |

## 14. Bài thực hành

Hãy mở rộng `importOrdersJob` trong một database thử nghiệm riêng:

1. Tạo ba file: 1.000 record hợp lệ, 1.000 record với 10 lỗi phân tán và 1.000 record với 300 lỗi. Bảo đảm ID và dữ liệu đều là dữ liệu giả.
2. Viết bước preflight kiểm tra header, manifest, checksum, số record và schema version. Với header sai, job phải thất bại trước khi ghi staging.
3. Cấu hình skip đúng `InvalidOrderException` và lỗi parse được cho phép, đặt `skipLimit(20)`. Quan sát kết quả khi có 10, 20 và 21 item lỗi.
4. Thêm một policy tỷ lệ lỗi 0,5%. Với 1.000 record, giải thích vì sao 10 lỗi đã vượt mức, dù chưa vượt giới hạn tuyệt đối 20.
5. Xây dựng quarantine có `sourceBatchId`, source locator, reason code và trạng thái xử lý. Kiểm tra không ghi payload nhạy cảm vào log.
6. Thay writer ghi bảng chính thành writer ghi staging, chỉ publish khi điều kiện count/tổng nghiệp vụ đạt. Cho job lỗi ở chunk sau và kiểm tra downstream chưa thấy snapshot mới.
7. Mô phỏng API outage trả 503 cho mọi item: áp dụng retry có backoff và ngân sách hữu hạn, theo dõi số request và dừng đúng chính sách.
8. Tạo job `FAILED`, khởi chạy lại với cùng identifying `JobParameters` để kiểm tra restart không ghi trùng.
9. Tạo file sửa lỗi `v2`, dùng `sourceBatchId` mới để replay. Đối soát snapshot mới với file v2 và đánh dấu lô cũ không được publish.
10. Viết báo cáo vận hành cho từng lô: tổng đầu vào, số accepted, rejected, lỗi theo loại, batch status, publish status và phương án xử lý tiếp.

**Điểm cần ghi nhớ:** Khi dữ liệu lỗi xuất hiện hàng loạt, chiến lược phục hồi không chỉ là tăng `skipLimit`. Hệ thống phải **phân biệt sai dữ liệu với lỗi hạ tầng, kiểm tra hợp đồng nguồn, giới hạn mức loại bỏ, lưu dấu vết để sửa, và chỉ công bố output khi đã đối soát**. Kết hợp fault tolerance của Spring Batch với staging, quarantine, version nguồn và restart/replay có kiểm soát giúp phục hồi an toàn mà không âm thầm đánh mất dữ liệu nghiệp vụ.
