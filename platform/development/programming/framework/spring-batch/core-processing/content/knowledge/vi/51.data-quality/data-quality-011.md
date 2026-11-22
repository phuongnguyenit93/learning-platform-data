# Báo cáo chất lượng dữ liệu trong Spring Batch

## 1. Mục tiêu và bối cảnh

Một Spring Batch job có thể kết thúc với trạng thái `COMPLETED` nhưng dữ liệu đầu ra vẫn không đạt yêu cầu nghiệp vụ. Ví dụ, một job nhập 100.000 khách hàng chạy thành công về mặt kỹ thuật, nhưng 8% bản ghi không có email, 2% trùng mã khách hàng, hoặc 500 bản ghi có ngày sinh không hợp lệ. Nếu chỉ nhìn `BatchStatus` và `writeCount`, đội vận hành khó biết dữ liệu có đủ tốt để chuyển sang bước tiếp theo hay không.

**Báo cáo chất lượng dữ liệu** (data quality report) là tập hợp các số liệu, quy tắc đánh giá, bằng chứng và kết luận về chất lượng của dữ liệu được xử lý trong một kỳ batch. Báo cáo giúp trả lời:

- Job nhận bao nhiêu bản ghi và bao nhiêu bản ghi được chấp nhận, bị loại hoặc cần xem xét?
- Dữ liệu có thiếu trường bắt buộc, sai định dạng, vi phạm miền giá trị hoặc trùng khóa không?
- Những quy tắc chất lượng nào được áp dụng, ở phiên bản nào?
- Số liệu này thuộc file nguồn, ngày nghiệp vụ và JobExecution nào?
- Chất lượng đạt ngưỡng để xuất bản dữ liệu hay cần chặn các bước downstream?
- Sau khi job restart, báo cáo có bị cộng trùng số lỗi hay mất dấu vết bản ghi không?

Bài học thuộc nhóm **Data quality** của **Spring Batch Core Processing**. Bạn sẽ xây dựng cách đo chất lượng trong pipeline Reader → Processor → Writer, lưu kết quả có khả năng truy vết, tổng hợp báo cáo và dùng quality gate để kiểm soát luồng batch.

Ví dụ sử dụng Java 17+, Spring Boot 3.x, Spring Batch 5.x, JDBC và PostgreSQL. Những đoạn mã được chia theo trách nhiệm để dễ áp dụng vào dự án có cấu hình riêng.

## 2. Phân biệt thành công kỹ thuật với chất lượng nghiệp vụ

Spring Batch quản lý trạng thái thực thi thông qua `JobExecution` và `StepExecution`. Tuy nhiên:

- `COMPLETED` nghĩa là job hoàn thành theo luồng và các quy tắc xử lý đã cấu hình; nó không mặc định có nghĩa “dữ liệu sạch”.
- `FAILED` có thể xảy ra vì hạ tầng, exception hoặc quality gate không đạt.
- `filterCount` tăng khi processor trả về `null`, nhưng không tự giải thích vì sao một bản ghi bị loại.
- `skipCount` ghi nhận các lỗi được skip theo fault-tolerant policy, không thay thế thống kê tất cả vi phạm nghiệp vụ.
- `writeCount` là thống kê item writer trong step, không nhất thiết bằng số bản ghi chất lượng cao được công bố tại đích cuối cùng.

Ví dụ:

| Kịch bản | Kết quả kỹ thuật | Kết quả chất lượng |
| --- | --- | --- |
| 10.000 bản ghi, tất cả hợp lệ | `COMPLETED` | Đạt |
| 10.000 bản ghi, 3.000 bản ghi thiếu email nhưng được đưa vào vùng cách ly | `COMPLETED` ở bước nhập | Có thể không đạt ngưỡng xuất bản |
| 10.000 bản ghi, writer gặp lỗi kết nối | `FAILED` | Báo cáo cuối có thể chưa hoàn chỉnh |
| File hoàn toàn rỗng | Có thể `COMPLETED` | Đạt hoặc không đạt tùy chính sách nguồn dữ liệu |
| File nhập thành công nhưng duplicate vượt mức cho phép | Step nhập `COMPLETED` | Quality gate phải từ chối chuyển dữ liệu sang hệ thống đích |

Do đó báo cáo phải chứa **hai nhóm trạng thái**: trạng thái thực thi Spring Batch và trạng thái chất lượng dữ liệu, ví dụ `PASS`, `WARN`, `FAIL` hoặc `NO_DATA`.

## 3. Các chiều chất lượng nên đo

Chọn chỉ số theo yêu cầu nghiệp vụ và đặc điểm nguồn dữ liệu. Một nhóm thường dùng:

| Chiều chất lượng | Câu hỏi | Ví dụ quy tắc |
| --- | --- | --- |
| **Completeness** (đầy đủ) | Trường bắt buộc có dữ liệu không? | `customerId`, `email` không được rỗng |
| **Validity** (hợp lệ) | Giá trị có đúng kiểu, format và miền cho phép không? | `age` là số nguyên từ 18 đến 120 |
| **Uniqueness** (duy nhất) | Có bản ghi trùng khóa nghiệp vụ không? | Không có hai khách hàng cùng `customerId` sau chuẩn hóa |
| **Consistency** (nhất quán) | Các trường hay nguồn có mâu thuẫn nhau không? | `startDate <= endDate`; mã quốc gia phù hợp vùng |
| **Accuracy** (chính xác) | Giá trị có khớp thực tế hoặc nguồn tham chiếu đáng tin cậy không? | Mã khách hàng tồn tại ở master data |
| **Timeliness** (kịp thời) | Dữ liệu có thuộc kỳ xử lý và được cập nhật đúng hạn không? | Sự kiện không trễ quá 24 giờ |
| **Integrity** (toàn vẹn) | Quan hệ và khóa tham chiếu có hợp lệ không? | Mã cửa hàng có trong bảng danh mục |
| **Conformity** (tuân thủ cấu trúc) | File/schema có đúng hợp đồng không? | Đúng số cột, header, encoding và kiểu dữ liệu |

Không phải mọi job cần đủ tất cả chiều. Với import khách hàng CSV, **completeness, validity và uniqueness** là nhóm tối thiểu hữu ích. Với job đối soát tài chính, thêm consistency và tổng tiền đối soát có thể quan trọng hơn kiểm tra định dạng đơn lẻ.

### Quy tắc phải cụ thể và có phiên bản

Quy tắc “email hợp lệ” quá chung chung. Nên định nghĩa:

```text
Rule ID: EMAIL_FORMAT
Version: v2
Field: email
Condition: Không rỗng và khớp quy tắc email được ứng dụng chấp nhận
Severity: ERROR
Action: REJECT_RECORD
```

Một địa chỉ email có thể hợp lệ theo chuẩn rộng nhưng không khớp regex đơn giản của ứng dụng. Vì vậy dùng “hợp lệ theo quy tắc EMAIL_FORMAT v2”, không khẳng định regex minh họa bao phủ toàn bộ chuẩn email.

Khi thay đổi rule, lưu `ruleSetVersion` trong báo cáo để giải thích vì sao cùng dữ liệu nhưng hai lần chạy có kết quả khác nhau.

## 4. Định nghĩa chỉ số và mẫu số

Các chỉ số phải dùng một **mẫu số rõ ràng**. Ví dụ với một kỳ nhập:

- `receivedRows`: số bản ghi logic thực sự nhận được từ nguồn theo định nghĩa nguồn.
- `evaluatedRows`: số bản ghi đã được đánh giá và lưu kết quả phân loại.
- `acceptedRows`: số bản ghi đáp ứng các quy tắc bắt buộc.
- `rejectedRows`: số bản ghi bị từ chối.
- `quarantinedRows`: số bản ghi được giữ lại để kiểm tra thủ công, nếu chính sách tách nhóm này.
- `duplicateRows`: số bản ghi không được chọn vì trùng khóa theo quy tắc đã định nghĩa.
- `missingEmailRows`: số bản ghi thiếu email bắt buộc.

Ví dụ công thức:

```text
acceptanceRate = acceptedRows / evaluatedRows × 100%
rejectionRate  = rejectedRows / evaluatedRows × 100%
emailMissingRate = missingEmailRows / evaluatedRows × 100%

Nếu evaluatedRows = 0:
    không thực hiện phép chia,
    báo cáo NO_DATA hoặc áp dụng chính sách nguồn rỗng.
```

Giả sử có 1.000 bản ghi được đánh giá, 900 được chấp nhận, 100 bị từ chối; trong 100 bản ghi đó có 60 thiếu email và 50 sai tuổi, với 10 bản ghi mắc cả hai lỗi.

```text
evaluatedRows      = 1.000
acceptedRows       = 900
rejectedRows       = 100
missingEmailRows   = 60
invalidAgeRows     = 50
totalViolationRows = 110 nếu đếm theo (bản ghi, quy tắc)
```

**Tổng số vi phạm có thể lớn hơn số bản ghi bị từ chối**, vì một bản ghi có thể vi phạm nhiều quy tắc. Báo cáo cần phân biệt “số bản ghi lỗi” với “số lần vi phạm quy tắc”.

### Cẩn thận khi lấy số từ StepExecution

`StepExecution.getReadCount()`, `getReadSkipCount()`, `getFilterCount()`, `getWriteCount()` hữu ích cho tình trạng xử lý. Nhưng không mặc định coi:

```text
sourceRows = readCount + readSkipCount
acceptedRows = writeCount
rejectedRows = filterCount + skipCount
```

là công thức đúng cho mọi job. Reader có thể bỏ qua header, dòng trống, record nhiều dòng; processor có thể filter bản ghi vì lý do khác; writer có thể ghi cả valid và invalid vào staging. Retry/rollback/restart cũng khiến cách diễn giải khác nhau. Với báo cáo chất lượng, nên **lưu kết quả đánh giá theo business key hoặc source row key** rồi tổng hợp từ dữ liệu đã commit.

## 5. Kiến trúc đề xuất: đánh giá, lưu bằng chứng, tổng hợp, quality gate

Một thiết kế phù hợp với Spring Batch:

```text
                File CSV / Database / API
                            |
                            v
                      ItemReader
                            |
                            v
                     Validation
                    ItemProcessor
                            |
                   QualityDecision
                    /            \
              ACCEPTED          REJECTED
                    \            /
                     v          v
                  Staging Writer
               (một dòng/source row,
                mã lỗi, rule version)
                            |
                            v
                        COMMIT
                            |
                            v
                 Finalize Quality Step
                - phát hiện duplicate
                - tổng hợp báo cáo
                - đánh giá quality gate
                            |
                +-----------+-----------+
                |                       |
               PASS                    FAIL
                |                       |
                v                       v
          Publish to target        Chặn publish,
          / downstream             lưu báo cáo và cảnh báo
```

Thiết kế này có một số ưu điểm:

1. Mỗi bản ghi được **đánh giá tường minh**; không dùng `processor.return null` cho mọi lỗi rồi mất lý do.
2. Kết quả được lưu vào staging trong cùng transaction của chunk.
3. Báo cáo tổng hợp từ những dòng đã commit, tránh bộ đếm in-memory không nhất quán khi rollback/restart.
4. Quy tắc như duplicate toàn file có thể đánh giá sau khi đã nạp đủ dữ liệu.
5. Quality gate có thể quyết định có cho bước publish chạy hay không.

Không nhất thiết triển khai một pipeline nhiều step cho tất cả dự án. Với batch nhỏ, có thể gom logic phù hợp. Nhưng nguyên tắc **đo chất lượng bằng kết quả bền vững và có thể đối soát** vẫn nên được giữ.

## 6. Phân biệt lỗi dữ liệu dự kiến với exception kỹ thuật

Một quyết định quan trọng là lỗi nào được xem như **kết quả kiểm tra chất lượng**, lỗi nào phải khiến step thất bại hoặc sử dụng fault tolerance.

| Loại lỗi | Cách xử lý điển hình | Cách ghi nhận |
| --- | --- | --- |
| Thiếu email, sai tuổi, định dạng mã không hợp lệ | Tạo `REJECTED` và danh sách rule vi phạm | Bảng staging/quality issue |
| Mã khách hàng trùng trong một batch | Đánh giá uniqueness, đánh dấu bản ghi trùng | Bảng staging + issue `DUPLICATE_ID` |
| Dữ liệu không parse được theo schema nhưng còn nhận diện được record | Quarantine với mã `MALFORMED_RECORD` | Lưu nguồn/an toàn và vị trí record |
| File thiếu, database mất kết nối, bảng đích không khả dụng | Fail hoặc retry theo loại exception | `JobExecution`/`StepExecution` và log kỹ thuật |
| Parser không thể xác định ranh giới record | Fail fast hoặc dùng reader/line mapper hỗ trợ fault tolerance phù hợp | Lỗi nguồn và `readSkipCount` nếu được skip |
| Không còn chỗ lưu staging | Fail step | Không tuyên bố đã đánh giá đủ dữ liệu |

Nếu `ItemProcessor` trả về `null` để filter, Spring Batch tăng `filterCount` nhưng bản ghi đó không đi tới writer. Nếu muốn báo cáo **chính xác lý do từng bản ghi bị loại**, processor nên trả về một kết quả có trạng thái, hoặc dùng một kênh lưu dữ liệu lỗi có transaction phù hợp.

**SkipListener** hữu ích khi exception được skip, nhưng không thay thế toàn bộ quality report. Một lỗi reader có thể xảy ra trước khi tạo được item; cần quy tắc riêng để lưu vị trí nguồn và lỗi đọc. Đừng cộng số lần retry vào số bản ghi vi phạm: một item có thể bị thử lại nhiều lần rồi thành công.

## 7. Mô hình dữ liệu cho bản ghi và báo cáo

Giả sử job import file khách hàng có ba cột:

```csv
customer_id,email,age
C001,alice@example.com,28
C002,,22
C003,bob@example.com,17
C001,other@example.com,31
C004,cara@example.com,45
```

Quy tắc mẫu:

- `CUSTOMER_ID_REQUIRED`: mã khách hàng không được rỗng.
- `EMAIL_REQUIRED`: email không được rỗng.
- `EMAIL_FORMAT`: email phải khớp quy tắc email của ứng dụng.
- `AGE_RANGE`: tuổi là số nguyên từ 18 đến 120.
- `DUPLICATE_ID`: mã đã chuẩn hóa không được xuất hiện nhiều hơn một lần trong tập bản ghi hợp lệ của cùng batch.

Một record có thể có nhiều mã lỗi. Không gộp tất cả thành câu mô tả khó tổng hợp; dùng **rule code ổn định**.

### Bảng staging và bảng báo cáo

Ví dụ DDL cho PostgreSQL:

```sql
CREATE TABLE customer_import_row (
    batch_key       VARCHAR(120) NOT NULL,
    source_line     BIGINT NOT NULL,
    customer_id     VARCHAR(100),
    email           VARCHAR(320),
    age             INTEGER,
    status          VARCHAR(20) NOT NULL,
    issue_codes     TEXT NOT NULL DEFAULT '',
    rule_version    VARCHAR(30) NOT NULL,
    PRIMARY KEY (batch_key, source_line)
);

CREATE INDEX idx_customer_import_row_status
    ON customer_import_row (batch_key, status);

CREATE INDEX idx_customer_import_row_customer
    ON customer_import_row (batch_key, customer_id);

CREATE TABLE customer_quality_report (
    batch_key       VARCHAR(120) PRIMARY KEY,
    rule_version    VARCHAR(30) NOT NULL,
    evaluated_rows  BIGINT NOT NULL,
    accepted_rows   BIGINT NOT NULL,
    rejected_rows   BIGINT NOT NULL,
    duplicate_rows  BIGINT NOT NULL,
    quality_status  VARCHAR(20) NOT NULL,
    generated_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Trong ví dụ này, `status` nhận `VALID` hoặc `REJECTED`. Khi áp dụng mô hình thực tế, có thể bổ sung `QUARANTINED`, `WARNING` hoặc lưu các vấn đề chất lượng trong một bảng `customer_quality_issue(batch_key, source_line, rule_code, severity)`.

Lưu một dòng cho mỗi cặp (bản ghi, quy tắc) thường là lựa chọn tốt khi cần thống kê sâu, vì một bản ghi có thể vi phạm nhiều quy tắc. Trường `issue_codes` phân tách bằng dấu `|` chỉ là phương án gọn cho ví dụ; nó không tối ưu cho tìm kiếm, phân tích và versioning quy tắc ở quy mô lớn.

**Khóa chính `(batch_key, source_line)` có ý nghĩa cho idempotency:** cùng một bản ghi nguồn được viết lại sau rollback/restart sẽ cập nhật đúng một dòng staging, không tạo bản sao. `source_line` phải có nghĩa ổn định với phiên bản file nguồn tương ứng.

## 8. ItemReader giữ vị trí nguồn để giải thích lỗi

Nếu chỉ đọc một chuỗi và bỏ mất vị trí dòng, việc giải thích “bản ghi nào bị từ chối?” trở nên khó khăn. Ta có thể cho reader trả về nội dung thô kèm số dòng.

```java
public record SourceRow(
        long lineNumber,
        String rawLine) {
}
```

Cấu hình `FlatFileItemReader`:

```java
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;

@Bean
@StepScope
FlatFileItemReader<SourceRow> customerReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<SourceRow>()
        .name("customerQualityReader")
        .resource(new FileSystemResource(inputFile))
        .linesToSkip(1)
        .lineMapper((line, lineNumber) ->
            new SourceRow(lineNumber, line))
        .saveState(true)
        .strict(true)
        .build();
}
```

Trong ví dụ, `linesToSkip(1)` bỏ qua header; `lineNumber` là vị trí được line mapper cung cấp. Nếu nguồn có record CSV nhiều dòng, encoding đặc biệt hoặc cách nhận diện record phức tạp, cần kiểm tra chính xác ý nghĩa vị trí trong reader/record separator đang dùng. Không mặc định một dòng vật lý luôn bằng một bản ghi logic cho mọi định dạng CSV.

`saveState(true)` và tên reader ổn định giúp Spring Batch lưu vị trí phục vụ restart. Cũng cần giữ nội dung nguồn không thay đổi giữa các lần thực thi của cùng JobInstance, bằng file snapshot, checksum hoặc version nguồn.

## 9. ItemProcessor đánh giá rule và trả về quyết định chất lượng

Không nên để các lỗi nghiệp vụ dự kiến luôn biến thành exception làm job `FAILED`. Thay vào đó, processor có thể trả một kết quả tường minh:

```java
public record QualityDecision(
        long sourceLine,
        String customerId,
        String email,
        Integer age,
        String status,
        String issueCodes) {
}
```

Ví dụ processor dùng `DelimitedLineTokenizer` để xử lý ba cột CSV theo quy tắc tokenization của Spring Batch:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.regex.Pattern;

import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.file.transform.DelimitedLineTokenizer;
import org.springframework.batch.item.file.transform.FieldSet;
import org.springframework.stereotype.Component;

@Component
public class CustomerQualityProcessor
        implements ItemProcessor<SourceRow, QualityDecision> {

    private static final Pattern EMAIL_PATTERN =
        Pattern.compile("^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$");

    private final DelimitedLineTokenizer tokenizer =
        new DelimitedLineTokenizer();

    public CustomerQualityProcessor() {
        tokenizer.setNames("customer_id", "email", "age");
        tokenizer.setStrict(true);
    }

    @Override
    public QualityDecision process(SourceRow row) {
        List<String> issues = new ArrayList<>();

        String customerId = null;
        String email = null;
        Integer age = null;

        try {
            FieldSet fields = tokenizer.tokenize(row.rawLine());

            customerId =
                fields.readString("customer_id").trim()
                    .toUpperCase(Locale.ROOT);

            email = fields.readString("email").trim();

            String ageText = fields.readString("age").trim();

            if (customerId.isEmpty()) {
                issues.add("CUSTOMER_ID_REQUIRED");
            }
            if (email.isEmpty()) {
                issues.add("EMAIL_REQUIRED");
            } else if (!EMAIL_PATTERN.matcher(email).matches()) {
                issues.add("EMAIL_FORMAT");
            }

            try {
                age = Integer.valueOf(ageText);
                if (age < 18 || age > 120) {
                    issues.add("AGE_RANGE");
                }
            } catch (NumberFormatException ex) {
                issues.add("AGE_RANGE");
            }

        } catch (RuntimeException ex) {
            // Ví dụ: sai số cột hoặc cú pháp không thể đọc.
            // Chỉ chuyển lỗi parse dự kiến thành kết quả dữ liệu,
            // không nên nuốt mọi exception hạ tầng/lỗi lập trình.
            issues.add("MALFORMED_RECORD");
        }

        String status = issues.isEmpty() ? "VALID" : "REJECTED";

        return new QualityDecision(
            row.lineNumber(),
            customerId,
            email,
            age,
            status,
            String.join("|", issues)
        );
    }
}
```

Các điểm cần hiểu:

- `process()` **không trả `null`** cho bản ghi không hợp lệ; writer sẽ nhận cả valid và rejected để lưu kết quả.
- Mỗi rule có code ổn định. Báo cáo có thể đếm theo code mà không phụ thuộc ngôn ngữ diễn giải.
- Chuẩn hóa `customerId` trước khi kiểm tra uniqueness để `c001` và `C001` được đối xử nhất quán.
- Regex email chỉ là quy tắc demo; với production, dùng validator phù hợp hợp đồng nghiệp vụ và test các trường hợp Unicode, quoted values, domain đặc biệt.
- Exception do sai số cột được chuyển thành `MALFORMED_RECORD` ở ví dụ; khi áp dụng thực tế nên bắt **đúng loại lỗi parse dự kiến** thay vì catch mọi `RuntimeException` rồi che giấu bug.
- Nếu dữ liệu chứa PII, cần chính sách bảo mật cho bảng staging. Không ghi nguyên `rawLine` vào log hoặc bảng lỗi khi không có nhu cầu và quyền truy cập phù hợp.

Ở thiết kế phức tạp, nên tách `QualityRule` thành các thành phần riêng trả về danh sách `Violation(ruleCode, severity, fieldName)`. Processor chỉ điều phối các rule; report aggregator không phụ thuộc vào chuỗi thông báo lỗi.

## 10. ItemWriter lưu kết quả có thể đối soát và restart

Writer dưới đây ghi cả valid và rejected vào staging. Ví dụ dùng cú pháp PostgreSQL `ON CONFLICT` để việc ghi lại cùng source row không nhân đôi dữ liệu.

```java
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.List;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.ItemWriter;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.BatchPreparedStatementSetter;
import org.springframework.jdbc.core.JdbcTemplate;

@Bean
@StepScope
ItemWriter<QualityDecision> customerStagingWriter(
        JdbcTemplate jdbc,
        @Value("#{jobParameters['batchKey']}") String batchKey) {

    return chunk -> {
        List<? extends QualityDecision> rows = chunk.getItems();

        jdbc.batchUpdate(
            """
            INSERT INTO customer_import_row
                (batch_key, source_line, customer_id, email,
                 age, status, issue_codes, rule_version)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'v1')
            ON CONFLICT (batch_key, source_line)
            DO UPDATE SET
                customer_id = EXCLUDED.customer_id,
                email = EXCLUDED.email,
                age = EXCLUDED.age,
                status = EXCLUDED.status,
                issue_codes = EXCLUDED.issue_codes,
                rule_version = EXCLUDED.rule_version
            """,
            new BatchPreparedStatementSetter() {
                @Override
                public int getBatchSize() {
                    return rows.size();
                }

                @Override
                public void setValues(
                        PreparedStatement ps,
                        int i) throws SQLException {

                    QualityDecision d = rows.get(i);

                    ps.setString(1, batchKey);
                    ps.setLong(2, d.sourceLine());
                    ps.setString(3, d.customerId());
                    ps.setString(4, d.email());

                    if (d.age() == null) {
                        ps.setNull(5, java.sql.Types.INTEGER);
                    } else {
                        ps.setInt(5, d.age());
                    }

                    ps.setString(6, d.status());
                    ps.setString(7, d.issueCodes());
                }
            }
        );
    };
}
```

Writer cần dùng cùng transaction manager với datasource staging để mỗi chunk commit/rollback nhất quán. Nếu chạy nhiều datasource hoặc gọi API bên ngoài transaction, không được mặc định việc ghi chất lượng và dữ liệu nghiệp vụ là nguyên tử.

`ON CONFLICT` hỗ trợ idempotency **trong một batch key và vị trí nguồn**. Nó không tự giải quyết câu hỏi một file đổi nội dung nhưng giữ nguyên batch key; đây là lý do phải version hóa nguồn và xác nhận checksum khi restart.

Trong production, nếu có yêu cầu giữ lịch sử mọi lần thay đổi trạng thái, có thể bổ sung bảng sự kiện append-only hoặc bảng issue chi tiết. Ví dụ sử dụng upsert để minh họa đường ghi bền vững qua chunk/restart.

## 11. Tìm duplicate trên toàn bộ batch

Một processor xử lý từng item không nhất thiết có đủ thông tin để kết luận item là bản ghi trùng **trong toàn file**. Dùng một `HashSet` trong singleton processor để nhớ tất cả ID không phải lúc nào cũng phù hợp: tăng bộ nhớ theo số bản ghi, khó restart, và dễ sai khi parallel processing.

Một cách khác là kiểm tra trên staging sau khi đã đọc hết nguồn. Quy tắc demo: trong các bản ghi **đạt các validation rule ban đầu**, giữ bản ghi đầu tiên theo `source_line`, những bản ghi hợp lệ xuất hiện sau với cùng `customer_id` bị gắn `DUPLICATE_ID`.

PostgreSQL:

```sql
WITH ranked AS (
    SELECT
        batch_key,
        source_line,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY source_line
        ) AS position_in_group
    FROM customer_import_row
    WHERE batch_key = :batchKey
      AND status = 'VALID'
      AND customer_id IS NOT NULL
)
UPDATE customer_import_row AS r
SET status = 'REJECTED',
    issue_codes = CASE
        WHEN r.issue_codes = '' THEN 'DUPLICATE_ID'
        ELSE r.issue_codes || '|DUPLICATE_ID'
    END
FROM ranked AS x
WHERE r.batch_key = x.batch_key
  AND r.source_line = x.source_line
  AND x.position_in_group > 1;
```

Lựa chọn này chỉ so sánh những record đã đạt các rule ban đầu. Nếu nghiệp vụ muốn **bản ghi trùng mã bất kể các lỗi khác**, phải đổi tiêu chí candidate và lưu được nhiều violation trên cùng một record; đừng dùng truy vấn này mà suy ra nó đã bao phủ mọi quy tắc uniqueness.

Một đặc điểm quan trọng: nếu quy trình finalize chạy lại sau khi đã đánh dấu các dòng trùng thành `REJECTED`, các dòng ấy không còn tham gia CTE do lọc `status='VALID'`; thao tác hiện tại không thêm `DUPLICATE_ID` lần nữa. Nếu cần tái tính toàn bộ báo cáo từ đầu sau khi đổi rule, hãy tái đánh giá staging hoặc dùng bảng issue độc lập với trạng thái tạm thời.

## 12. Tổng hợp báo cáo từ dữ liệu đã commit

Sau khi xử lý và đánh dấu duplicate, có thể tổng hợp bằng SQL thay vì giữ các counter trong memory:

```sql
SELECT
    COUNT(*) AS evaluated_rows,
    COUNT(*) FILTER (WHERE status = 'VALID') AS accepted_rows,
    COUNT(*) FILTER (WHERE status = 'REJECTED') AS rejected_rows,
    COUNT(*) FILTER (
        WHERE issue_codes LIKE '%DUPLICATE_ID%'
    ) AS duplicate_rows
FROM customer_import_row
WHERE batch_key = :batchKey;
```

Với rule code được kiểm soát và không có mã chứa chồng lên nhau, cách tìm chuỗi có thể đủ cho ví dụ. Đối với dữ liệu chất lượng lớn, hãy dùng bảng `quality_issue` với một dòng cho mỗi vi phạm để không phụ thuộc `LIKE`.

Để báo cáo hiển thị tỷ lệ:

```sql
SELECT
    batch_key,
    evaluated_rows,
    accepted_rows,
    rejected_rows,
    CASE
        WHEN evaluated_rows = 0 THEN NULL
        ELSE ROUND(
            accepted_rows * 100.0 / evaluated_rows,
            2
        )
    END AS acceptance_pct,
    quality_status
FROM customer_quality_report;
```

Khi mẫu số bằng 0, `NULL` thể hiện “không có tỷ lệ có ý nghĩa”, khác với tỷ lệ 0% của một bộ dữ liệu có bản ghi nhưng không có bản ghi hợp lệ.

### Báo cáo ví dụ

Với CSV ở phần trước, giả sử quy tắc xử lý xác định `C001` ở dòng sau là duplicate:

| Chỉ số | Giá trị |
| --- | ---: |
| Evaluated rows | 5 |
| Accepted rows | 2 |
| Rejected rows | 3 |
| Missing email | 1 |
| Invalid age | 1 |
| Duplicate customer ID | 1 |
| Acceptance rate | 40% |
| Quality gate | `FAIL` nếu yêu cầu tối thiểu 98% |

Dòng `C002` thiếu email; `C003` có tuổi 17; `C001` lần hai bị gắn duplicate. `C001` lần đầu và `C004` được chấp nhận. Đây là ví dụ minh họa cho một bộ rule cố định, không phải ngưỡng bắt buộc của mọi hệ thống.

## 13. Tạo báo cáo và quality gate ở một step riêng

Nên để ingestion step **hoàn thành và commit staging** trước, sau đó một step tổng hợp có thể chạy trong transaction riêng. Điều này cho phép vẫn giữ báo cáo khi quality gate không đạt và chặn bước publish.

### Ví dụ tasklet tổng hợp

Code sau dùng PostgreSQL và lưu báo cáo với chính sách: nguồn rỗng ⇒ `NO_DATA`; nếu acceptance rate nhỏ hơn 98% ⇒ `FAIL`; ngược lại ⇒ `PASS`.

```java
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@Bean
@StepScope
Tasklet summarizeQuality(
        JdbcTemplate jdbc,
        @Value("#{jobParameters['batchKey']}") String batchKey) {

    return (contribution, chunkContext) -> {
        jdbc.update(
            """
            INSERT INTO customer_quality_report (
                batch_key, rule_version, evaluated_rows,
                accepted_rows, rejected_rows, duplicate_rows,
                quality_status, generated_at
            )
            SELECT
                ?, 'v1',
                COUNT(*),
                COUNT(*) FILTER (WHERE status = 'VALID'),
                COUNT(*) FILTER (WHERE status = 'REJECTED'),
                COUNT(*) FILTER (
                    WHERE issue_codes LIKE '%DUPLICATE_ID%'
                ),
                CASE
                    WHEN COUNT(*) = 0 THEN 'NO_DATA'
                    WHEN COUNT(*) FILTER (WHERE status = 'VALID')
                         * 100.0 / COUNT(*) < 98.0 THEN 'FAIL'
                    ELSE 'PASS'
                END,
                CURRENT_TIMESTAMP
            FROM customer_import_row
            WHERE batch_key = ?
            ON CONFLICT (batch_key)
            DO UPDATE SET
                rule_version = EXCLUDED.rule_version,
                evaluated_rows = EXCLUDED.evaluated_rows,
                accepted_rows = EXCLUDED.accepted_rows,
                rejected_rows = EXCLUDED.rejected_rows,
                duplicate_rows = EXCLUDED.duplicate_rows,
                quality_status = EXCLUDED.quality_status,
                generated_at = EXCLUDED.generated_at
            """,
            batchKey, batchKey
        );

        return RepeatStatus.FINISHED;
    };
}
```

Đây là phần tổng hợp, giả định bước đánh dấu duplicate đã chạy trước đó. Nếu muốn hai thao tác thuộc một bước duy nhất, có thể đặt SQL duplicate và SQL summary trong cùng transaction của một tasklet. Khi đó một execution thành công sẽ để lại kết quả nhất quán.

### Quality gate nên kiểm soát bước publish

Một lựa chọn là để step quality report hoàn tất thành công dù trạng thái nghiệp vụ là `FAIL`, rồi đặt `ExitStatus` tùy biến và điều hướng flow để **không chạy publish step**.

Ví dụ listener minh họa:

```java
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;
import org.springframework.jdbc.core.JdbcTemplate;

public class QualityGateListener implements StepExecutionListener {

    private final JdbcTemplate jdbc;
    private final String batchKey;

    public QualityGateListener(
            JdbcTemplate jdbc,
            String batchKey) {
        this.jdbc = jdbc;
        this.batchKey = batchKey;
    }

    @Override
    public ExitStatus afterStep(StepExecution step) {
        String status = jdbc.queryForObject(
            """
            SELECT quality_status
            FROM customer_quality_report
            WHERE batch_key = ?
            """,
            String.class,
            batchKey
        );

        return switch (status) {
            case "PASS" -> new ExitStatus("QUALITY_PASS");
            case "NO_DATA" -> new ExitStatus("QUALITY_NO_DATA");
            default -> new ExitStatus("QUALITY_FAIL");
        };
    }
}
```

Phần cấu hình Job flow có thể ánh xạ `QUALITY_PASS` sang bước publish; `QUALITY_FAIL` và `QUALITY_NO_DATA` sang nhánh kết thúc hoặc xử lý cảnh báo thích hợp. **ExitStatus tùy biến không tự động làm BatchStatus thành `FAILED`**. Nếu nghiệp vụ yêu cầu job thất bại về mặt kỹ thuật khi chất lượng không đạt, cần thiết kế flow/bước fail tường minh, tránh chỉ đổi exit code rồi mặc định hệ thống giám sát sẽ thấy `FAILED`.

Với dự án có nhiều loại báo cáo, nên đưa ngưỡng quality gate vào cấu hình rule đã version hóa, không hardcode 98% trong tất cả job.

## 14. Cấu hình Job/Step trong Spring Batch

Một cấu trúc ba bước cho ví dụ:

1. `importCustomerStep`: đọc từng dòng, đánh giá rule, ghi staging.
2. `qualityFinalizeStep`: đánh dấu duplicate và tổng hợp báo cáo.
3. `publishCustomerStep`: chỉ chạy khi quality gate đạt.

Minh họa step ingest:

```java
@Bean
Step importCustomerStep(
        JobRepository repository,
        PlatformTransactionManager tx,
        @Qualifier("customerReader") ItemReader<SourceRow> reader,
        CustomerQualityProcessor processor,
        @Qualifier("customerStagingWriter")
            ItemWriter<QualityDecision> writer) {

    return new StepBuilder("importCustomerStep", repository)
        .<SourceRow, QualityDecision>chunk(200, tx)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .build();
}
```

Step tổng hợp có thể sử dụng tasklet và transaction manager:

```java
@Bean
Step qualityFinalizeStep(
        JobRepository repository,
        PlatformTransactionManager tx,
        @Qualifier("qualityFinalizeTasklet") Tasklet tasklet) {

    return new StepBuilder("qualityFinalizeStep", repository)
        .tasklet(tasklet, tx)
        .build();
}
```

`qualityFinalizeTasklet` là thành phần ứng dụng gồm hai thao tác: thực hiện truy vấn xác định duplicate, sau đó cập nhật `customer_quality_report`. Ví dụ ở hai phần trên cung cấp logic SQL tương ứng; một cấu hình hoàn chỉnh cần kết nối chúng và gắn listener quality gate.

Job flow có thể được biểu diễn:

```text
importCustomerStep
      |
      v
qualityFinalizeStep
      |
      +-- QUALITY_PASS --> publishCustomerStep --> END
      |
      +-- QUALITY_FAIL ------------------------> STOP/FAIL theo chính sách
      |
      +-- QUALITY_NO_DATA ---------------------> END/FAIL theo chính sách
```

Không nhất thiết publish ngay trong writer ở bước ingest. Nếu ghi vào bảng đích ngay từ đầu rồi mới phát hiện toàn bộ nguồn không đạt quality gate, việc chặn publish về sau sẽ khó thực hiện. Staging giúp tách **nhận dữ liệu** khỏi **công bố dữ liệu đã được kiểm tra**.

## 15. Ngưỡng chất lượng và mức độ nghiêm trọng

Một quality gate thường không chỉ có một tỷ lệ hợp lệ. Ví dụ:

| Rule | Severity | Ngưỡng | Chính sách |
| --- | --- | --- | --- |
| Header/schema nguồn đúng | `CRITICAL` | Bắt buộc 100% | Fail ingest trước khi đánh giá |
| `customer_id` không rỗng | `ERROR` | 100% | Reject bản ghi hoặc fail job tùy nghiệp vụ |
| `email` không rỗng | `ERROR` | Tỷ lệ thiếu tối đa 1% | Gate fail nếu vượt |
| Tuổi hợp lệ | `ERROR` | Tỷ lệ sai tối đa 0,5% | Gate fail nếu vượt |
| Trùng mã khách hàng | `ERROR` | 0 duplicate | Gate fail nếu có duplicate |
| Viết hoa mã khách hàng không đồng đều | `WARNING` | Tùy ngưỡng | Chuẩn hóa và cảnh báo |
| Tổng bản ghi giảm bất thường | `WARNING`/`CRITICAL` | Ví dụ giảm trên 30% so với baseline | Điều tra thiếu dữ liệu |

Ngưỡng 0,5%, 1% hay 98% chỉ là ví dụ. Với pipeline tài chính, một duplicate có thể phải chặn hoàn toàn. Với nguồn marketing, tỷ lệ thiếu thuộc tính tùy chọn có thể chấp nhận được.

Một **quality score** tổng hợp có trọng số có thể hỗ trợ dashboard, nhưng không nên để score cao che giấu một lỗi critical. Chẳng hạn điểm tổng 99/100 vẫn phải fail khi sai khóa tham chiếu ảnh hưởng đến thanh toán. Cần kiểm tra rule bắt buộc riêng trước khi xét điểm tổng.

## 16. Data quality khi job restart hoặc chạy lại

Spring Batch sử dụng `JobRepository` và `ExecutionContext` để quản lý restart. Trong quality reporting, phải phân biệt:

- Một **JobInstance**: định danh kỳ xử lý, ví dụ `batchKey=crm-2026-11-15-v1`.
- Một **JobExecution**: một lần cố gắng chạy của instance.
- Một **source row**: bản ghi vật lý hoặc logic của snapshot nguồn.
- Một **violation**: kết quả của một rule trên một source row.

Không nên tăng một counter singleton trong `ItemProcessor`:

```java
private long invalidRows;

public QualityDecision process(SourceRow row) {
    if (invalid(row)) {
        invalidRows++;
    }
    // ...
}
```

Counter như vậy không nhất thiết rollback khi chunk thất bại, có thể tăng lặp sau retry và gây race condition khi xử lý đa luồng. Nếu bean sống xuyên nhiều JobExecution, giá trị còn có thể lẫn giữa các lần chạy.

Thay vào đó:

1. Mỗi source row có khóa ổn định `(batchKey, sourceLine)`.
2. Writer upsert kết quả đánh giá trong transaction của chunk.
3. Bước tổng hợp tính lại từ staging đã commit.
4. Báo cáo được upsert theo `batchKey`, không cộng dồn các lần chạy.
5. Snapshot file, mapping và `ruleSetVersion` được giữ nhất quán trong một lần restart.
6. Với reprocess có thay đổi nguồn/rule, tạo version dữ liệu hoặc quy trình riêng thay vì giả vờ đang restart cùng một snapshot.

### Chọn identifying JobParameters

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("batchKey", "crm-2026-11-15-v1", true)
    .addString("ruleSetVersion", "v1", true)
    .addString("inputFile", "/data/snapshots/customers-20261115.csv", false)
    .toJobParameters();
```

Đường dẫn có thể là non-identifying, nhưng ứng dụng phải **khóa được nội dung nguồn** của batch key bằng checksum hoặc version trong manifest. Nếu ai đó thay file ở cùng đường dẫn rồi restart, vị trí checkpoint không còn bảo đảm tương ứng với dữ liệu ban đầu.

Nếu job đã `COMPLETED` và muốn đánh giá lại với bộ rule mới, cần quản lý reprocess: xác định khóa định danh mới, cách ghi đè/bảo lưu báo cáo cũ, và hành vi đối với dữ liệu đã publish.

## 17. Báo cáo từ StepExecution và báo cáo từ dữ liệu

Có thể bổ sung metadata Spring Batch vào quality report để phân biệt hiệu quả vận hành và chất lượng:

| Loại thông tin | Nguồn | Ví dụ |
| --- | --- | --- |
| Job/Step status | `JobExecution`, `StepExecution` | `COMPLETED`, `FAILED` |
| Thời gian xử lý | Metadata execution | 120 giây |
| Read/Write/Skip/Filter counts | `StepExecution` | `readCount=1000` |
| Accepted/rejected per business rule | Staging/quality_issue | `EMAIL_REQUIRED=30` |
| Source checksum, rule version | Manifest/JobParameters | `sha256=...`, `v1` |
| Report quality status | Quality gate | `PASS`, `WARN`, `FAIL` |
| Publish status | Step downstream/đích | Đã publish 970 record |

Một số lượng `writeCount=1.000` có thể hoàn toàn hợp lý nếu writer ghi **1.000 bản ghi kết quả đánh giá** vào staging, dù chỉ 970 khách hàng được chấp nhận. Do đó không được gắn tên “acceptedRows” cho `writeCount` trong thiết kế này.

Nếu có skip do lỗi reader, số record thực đánh giá trong staging có thể nhỏ hơn số record cố gắng đọc. Khi đó báo cáo nên có trường riêng `unparsedRows` hoặc `readErrorRows`, với phương pháp xác định đúng record nguồn. Không tuyên bố “đã đánh giá 100% nguồn” khi parser không đọc được một phần dữ liệu.

## 18. Thiết kế đầu ra báo cáo cho vận hành

Một báo cáo nên có các nhóm sau:

### Thông tin định danh

```text
reportId:      quality-crm-2026-11-15-v1
jobName:       importCustomersJob
batchKey:      crm-2026-11-15-v1
businessDate:  2026-11-15
sourceUri:     s3://bucket/snapshots/customers-20261115.csv
sourceHash:    sha256:...
ruleVersion:   v1
executionId:   2042
generatedAt:   2026-11-16T01:45:00Z
```

Đây là dữ liệu minh họa. Đường dẫn nguồn phải được lưu theo chính sách bảo mật; không đưa signed URL, access token hoặc bí mật truy cập vào báo cáo.

### Kết quả tổng hợp

```text
evaluatedRows: 10000
acceptedRows:  9880
rejectedRows:  120
acceptancePct: 98.80
duplicateRows: 15
qualityStatus: FAIL
gateReasons:
  - "DUPLICATE_ID vượt ngưỡng 0"
```

`acceptancePct` vượt 98% nhưng gate vẫn `FAIL` vì duplicate phải bằng 0. Đây là ví dụ cho việc một rule critical có thể phủ quyết kết luận tổng thể.

### Chi tiết theo quy tắc

| Rule code | Severity | Số dòng vi phạm | Tỷ lệ trên evaluated rows | Ngưỡng | Kết luận |
| --- | --- | ---: | ---: | ---: | --- |
| `EMAIL_REQUIRED` | ERROR | 60 | 0,60% | ≤1% | PASS |
| `AGE_RANGE` | ERROR | 45 | 0,45% | ≤0,5% | PASS |
| `DUPLICATE_ID` | CRITICAL | 15 | 0,15% | 0 | FAIL |

Tổng số dòng vi phạm ở bảng có thể trùng với rejected rows hoặc lớn hơn, tùy bản ghi có nhiều lỗi và cách nhóm. Nên luôn ghi rõ định nghĩa chỉ số ở đầu báo cáo.

### Mẫu bản ghi lỗi

Nếu cần hỗ trợ điều tra, báo cáo có thể chỉ chứa số lượng và đường dẫn tới kho lưu dữ liệu cách ly có phân quyền. Tránh đính kèm nguyên email, địa chỉ, số tài khoản hoặc toàn bộ CSV lỗi vào email thông báo vận hành. Có thể sử dụng source row key, mã lỗi và vị trí dòng.

## 19. Kiểm thử báo cáo chất lượng dữ liệu

Cần kiểm thử ở cả cấp rule và cấp pipeline. **Unit test** cho processor để xác nhận phân loại; **integration test** cho writer, SQL aggregation và gate để xác nhận transaction, checkpoint và kết quả cuối.

### 19.1. Unit test cho processor

Ví dụ JUnit 5:

```java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class CustomerQualityProcessorTest {

    private final CustomerQualityProcessor processor =
        new CustomerQualityProcessor();

    @Test
    void acceptsValidRow() throws Exception {
        QualityDecision result = processor.process(
            new SourceRow(2, "C001,alice@example.com,28")
        );

        assertEquals("VALID", result.status());
        assertEquals("", result.issueCodes());
        assertEquals("C001", result.customerId());
        assertEquals(28, result.age());
    }

    @Test
    void reportsMultipleViolationsForOneRow() throws Exception {
        QualityDecision result = processor.process(
            new SourceRow(3, "C002,,17")
        );

        assertEquals("REJECTED", result.status());
        assertTrue(result.issueCodes().contains("EMAIL_REQUIRED"));
        assertTrue(result.issueCodes().contains("AGE_RANGE"));
    }

    @Test
    void marksMalformedRecordWithoutThrowing() throws Exception {
        QualityDecision result = processor.process(
            new SourceRow(4, "C003,only-two-columns")
        );

        assertEquals("REJECTED", result.status());
        assertTrue(result.issueCodes().contains("MALFORMED_RECORD"));
    }

    @Test
    void normalizesBusinessKey() throws Exception {
        QualityDecision result = processor.process(
            new SourceRow(5, " c001 ,a@example.com,30")
        );

        assertEquals("C001", result.customerId());
    }
}
```

Unit test chỉ xác minh processor với từng source row. Nó **chưa kiểm tra duplicate**, vì duplicate được phát hiện sau khi staging đã có nhiều bản ghi.

### 19.2. Integration test với staging và report

Các kịch bản nên có:

| Đầu vào | Kỳ vọng |
| --- | --- |
| File rỗng hoặc chỉ header | `evaluatedRows=0`, báo cáo `NO_DATA` hoặc policy đã định |
| Một bản ghi hợp lệ | `accepted=1`, `rejected=0` |
| Bản ghi thiếu email | `EMAIL_REQUIRED`, rejected |
| Bản ghi sai tuổi | `AGE_RANGE`, rejected |
| Một bản ghi lỗi hai rule | Một rejected row, hai violations |
| Hai mã trùng sau chuẩn hóa | Bản ghi đầu được giữ, bản ghi sau bị gắn `DUPLICATE_ID` theo chính sách |
| Số record ngay dưới/bằng/trên chunk size | Không mất/nhân bản bản ghi cuối chunk |
| Lỗi writer trước commit | Không có dòng staging đã rollback |
| Restart sau lỗi giữa file | Không nhân đôi staging; báo cáo tổng đúng |
| Chạy lại finalize step | Duplicate không bị cộng trùng; report được upsert |
| Rule critical vượt ngưỡng | Report `FAIL`, publish step không chạy |
| Quality gate đạt ngưỡng đúng bằng giới hạn | Kết quả theo điều kiện `<` hay `<=` được định nghĩa rõ |
| File nguồn thay đổi trước restart | Chặn hoặc báo lỗi checksum, không dùng checkpoint sai |
| Nhiều partition/worker | Tổng số dòng đúng, khóa staging vẫn duy nhất |

Khi test với PostgreSQL-specific SQL như `ON CONFLICT` và `FILTER (WHERE ...)`, nên dùng môi trường test tương thích với PostgreSQL, chẳng hạn container database dành cho integration test. Không mặc định mọi câu SQL sẽ tương thích hoàn toàn với H2.

### 19.3. Test quality gate bằng số liệu cụ thể

Ví dụ gate chấp nhận khi acceptance rate **ít nhất 98%** và duplicate bằng 0:

| evaluated | accepted | duplicate | Kết luận |
| ---: | ---: | ---: | --- |
| 100 | 98 | 0 | `PASS` |
| 100 | 97 | 0 | `FAIL` |
| 100 | 100 | 1 | `FAIL` |
| 0 | 0 | 0 | `NO_DATA` |
| 10.000 | 9.800 | 0 | `PASS` |

Kiểm tra riêng đường `NO_DATA`, vì phép chia cho 0 có thể gây lỗi hoặc tạo kết luận sai nếu chương trình tự gán 100% cho nguồn rỗng.

## 20. Giám sát, cảnh báo và xu hướng theo thời gian

Báo cáo một lần chạy cho biết chất lượng của kỳ đó. Để phát hiện suy giảm dần, nên lưu lịch sử các kỳ và vẽ xu hướng:

- Acceptance rate theo ngày/nguồn/tenant.
- Số bản ghi lỗi theo rule code và rule version.
- Duplicate rate, missing rate, số bản ghi hoàn toàn không parse được.
- Số lượng nguồn nhận được so với baseline kỳ trước.
- Các kỳ có quality gate `FAIL` hoặc `NO_DATA`.
- Độ trễ từ khi nhận dữ liệu đến khi báo cáo được sinh.
- Chênh lệch giữa source count, evaluated rows và số record publish.

Nếu acceptance rate đột ngột giảm từ 99,9% xuống 85%, cần phân biệt thay đổi dữ liệu thật với việc triển khai rule version mới. Vì vậy báo cáo phải ghi version của rule set và schema.

### Phân loại cảnh báo

- **Thông tin:** báo cáo sẵn sàng, chất lượng đạt.
- **Cảnh báo:** một chỉ số chạm ngưỡng nhưng chưa chặn publish.
- **Nghiêm trọng:** lỗi schema, thiếu dữ liệu bắt buộc hoặc gate không đạt theo chính sách.
- **Lỗi kỹ thuật:** không tạo được báo cáo vì job `FAILED`, writer lỗi hoặc metadata không nhất quán.

Không gửi hàng nghìn email cho từng record lỗi; gửi một thông báo tổng hợp theo kỳ và một đường dẫn đến khu vực điều tra có quyền truy cập. Metric nên dùng các label có cardinality vừa phải như job, source, rule và status; tránh đưa UUID từng record làm label.

## 21. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách cải thiện |
| --- | --- | --- |
| Chỉ dùng `BatchStatus.COMPLETED` làm “dữ liệu đạt” | Bỏ qua lỗi nghiệp vụ | Quality gate riêng |
| Cộng `filterCount` và `skipCount` thành rejected mà không có định nghĩa | Số liệu sai, thiếu nguyên nhân | Lưu quyết định và violation theo source row |
| Counter lỗi nằm trong singleton processor | Sai khi retry, rollback, restart hoặc multi-thread | Tổng hợp từ staging đã commit |
| Dùng một exception cho cả lỗi dữ liệu và lỗi hạ tầng | Job fail không cần thiết hoặc che giấu lỗi kỹ thuật | Phân loại rõ |
| Nạp toàn bộ nguồn vào bộ nhớ để tìm duplicate | Heap tăng, khó restart và parallel | Kiểm tra uniqueness trong staging/database |
| Không lưu rule version | Báo cáo các ngày khó so sánh | Lưu version trong report và nguồn |
| Duplicate sau restart bị đếm hai lần | Ghi append thay vì upsert | Khóa `batchKey + sourceLine`, thao tác idempotent |
| Dùng sample email regex như chuẩn tuyệt đối | Loại nhầm dữ liệu hợp lệ | Định nghĩa hợp đồng validation và test |
| Không phân biệt số record lỗi với số violation | Tổng lỗi có thể lớn hơn số dòng | Có bảng issue hoặc hai chỉ số riêng |
| File chỉ có header bị tính 100% hợp lệ | Mẫu số bằng 0 | Chính sách `NO_DATA` |
| Chỉ đo dữ liệu nguồn trước khi publish | Không thấy mất/trùng khi ghi đích | Đối soát số record và khóa ở đích |
| Report lỗi nhưng dữ liệu đã publish | Gate chạy quá muộn | Staging trước, publish sau gate |
| Lưu toàn bộ dữ liệu cá nhân vào log/email báo cáo | Rủi ro bảo mật | Chỉ giữ key/mã lỗi, phân quyền bảng quarantine |
| Ngưỡng quality gate đổi ngầm | Không giải thích được thay đổi chất lượng | Version hóa cấu hình threshold |
| File nguồn bị sửa khi restart | Checkpoint chỉ vào dữ liệu khác | Snapshot + checksum |
| Rule critical bị che bởi điểm tổng cao | Báo cáo “PASS” dù lỗi nghiêm trọng | Kiểm tra điều kiện bắt buộc riêng |
| SQL báo cáo gộp nhiều execution không đúng | Số liệu không gắn với một kỳ nguồn | Khóa batch ổn định và định danh rõ |

## 22. Bài tập thực hành

Hãy xây dựng `importCustomersJob` gồm bước ingest, bước finalize quality và bước publish:

1. Đọc file CSV gồm `customer_id`, `email` và `age`.
2. Triển khai ít nhất bốn rule: ID bắt buộc, email bắt buộc, tuổi từ 18–120 và mã khách hàng duy nhất sau chuẩn hóa.
3. Mỗi record phải có kết quả `VALID` hoặc `REJECTED`; bản ghi bị từ chối được lưu mã vi phạm.
4. Bảng staging cần có khóa duy nhất theo batch key và source row để hỗ trợ restart.
5. Báo cáo phải có evaluated/accepted/rejected rows, số vi phạm theo rule và acceptance rate.
6. Gate chỉ cho publish nếu acceptance rate ≥ 98% và không có duplicate. Nguồn rỗng phải có kết luận riêng.
7. Giả lập writer lỗi giữa chunk rồi restart. Báo cáo cuối và dữ liệu staging không được nhân đôi.
8. Thay đổi một rule, tăng `ruleSetVersion` và so sánh hai lần đánh giá trên cùng snapshot nguồn theo quy trình reprocess rõ ràng.
9. Đối soát số bản ghi publish với số accepted của báo cáo và xác nhận không có khóa trùng ở đích.

Đầu ra mong đợi gồm một file hoặc bản ghi báo cáo theo kỳ, danh sách vi phạm có thể truy xuất bằng source row key và một bảng kiểm thử chứng minh quality gate hoạt động ở các ngưỡng.

## 23. Tổng kết

**Báo cáo chất lượng dữ liệu** trong Spring Batch phải được xây dựng từ **quy tắc nghiệp vụ rõ ràng, dữ liệu đánh giá có thể truy vết và kết quả đã commit**, thay vì chỉ lấy số đếm của StepExecution rồi suy ra dữ liệu đạt hay không. Spring Batch cung cấp Reader, Processor, Writer, Step/Job metadata và cơ chế restart; ứng dụng cần bổ sung mô hình violation, staging, aggregation và quality gate để phân biệt thành công kỹ thuật với chất lượng nghiệp vụ.

Một thiết kế tốt xác định đúng mẫu số, ghi rule/version và source snapshot, xử lý nhiều lỗi trên một bản ghi, chống cộng trùng sau retry/restart và chặn publish khi vi phạm điều kiện quan trọng. Khi kết hợp báo cáo từng kỳ với theo dõi xu hướng, đội vận hành có thể phát hiện lỗi dữ liệu sớm, điều tra nguyên nhân và chỉ đưa dữ liệu đáng tin cậy sang các bước downstream.
