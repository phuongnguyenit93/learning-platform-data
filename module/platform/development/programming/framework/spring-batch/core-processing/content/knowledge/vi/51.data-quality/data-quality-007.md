# Missing record detection trong Spring Batch

## 1. Missing record là gì?

Trong hệ thống xử lý dữ liệu bằng Spring Batch, **missing record** là một bản ghi **được yêu cầu xuất hiện ở đầu ra theo hợp đồng xử lý**, nhưng không tìm thấy ở đầu ra đã ghi nhận hoặc công bố tại thời điểm đối soát. Việc phát hiện bản ghi thiếu là một phần quan trọng của **data quality**: job có thể chạy hết các Step và báo \`COMPLETED\` nhưng một số record vẫn không đến đích.

Ví dụ job nhập đơn hàng:

~~~text
Nguồn đầu vào                 Đầu ra
-------------                -------------
O101 (hợp lệ) -------------> O101
O102 (hợp lệ) -------------> O102
O103 (CANCELLED)             [lọc hợp lệ]
O104 (hợp lệ) -------------> [không có]
O105 (INVALID)               [loại theo policy]
O106 (hợp lệ) -------------> [không có]
~~~

Trong ví dụ này **O104 và O106 là missing records**, nếu hợp đồng yêu cầu mỗi đơn hợp lệ, ở trạng thái cần xử lý, phải có đúng một kết quả trong bảng đích.

Việc không thấy một record ở output **chưa đủ** để kết luận record đó bị thiếu do lỗi. Trước khi kiểm tra phải trả lời:

- Record có **thuộc tập dữ liệu phải xử lý** không?
- Có được lọc hoặc loại bỏ **đúng chính sách** không?
- Job/Step đã hoàn tất và output đã **commit** chưa?
- Output nằm trong bảng, file, topic, partition, version hoặc batch nào?
- Có độ trễ xử lý hợp lệ hoặc sự kiện chưa được bên nhận xác nhận không?

Vì vậy, missing record detection cần định nghĩa rõ **tập kỳ vọng (expected set)**, **tập đầu ra quan sát được (actual set)** và **thời điểm đối soát**.

## 2. Phân biệt missing, filtered, skipped, duplicate và unexpected

| Trường hợp | Ý nghĩa | Được xem là missing? |
|---|---|---|
| **Missing** | Record phải có output nhưng không thấy | **Có** |
| **Filtered** | Processor chủ động trả \`null\` theo quy tắc hợp lệ | Không, nếu hợp đồng cho phép không xuất |
| **Skipped** | Framework bỏ qua record sau exception theo skip policy | Tùy hợp đồng: có thể là lỗi chất lượng hoặc loại bỏ được chấp thuận |
| **Duplicate** | Một khóa đầu ra xuất hiện nhiều lần ngoài dự kiến | Là lỗi khác; có thể đồng thời tồn tại với missing |
| **Unexpected/extra** | Output chứa record không thuộc tập được phép xuất | Là lỗi khác; không bù được record thiếu |
| **Late** | Record chưa đến do cơ chế bất đồng bộ trong cửa sổ trễ cho phép | Chưa kết luận missing khi chưa hết deadline |
| **Rejected** | Record bị từ chối theo quy tắc có audit và lý do rõ ràng | Không nếu contract quy định excluded set |

**Không đánh đồng \`filterCount\` hoặc \`skipCount\` với số record thiếu.** Các bộ đếm Spring Batch mô tả hoạt động xử lý, còn missing detection cần so sánh khóa/dữ liệu thực tế với yêu cầu nghiệp vụ.

Một ví dụ lỗi hay bị bỏ sót: output có cùng tổng số dòng như nguồn nhưng một đơn bị thiếu và một đơn khác bị ghi trùng. \`COUNT(*)\` bằng nhau, nhưng bộ dữ liệu vẫn không đầy đủ.

## 3. Xây dựng hợp đồng kỳ vọng trước khi kiểm tra

Giả sử hệ thống nhập dữ liệu từ bảng \`staging_order\` và xuất ra \`processed_order\`. Hợp đồng nghiệp vụ:

1. Chỉ xét record thuộc **batchId** cần kiểm tra.
2. Chỉ các record có \`status = 'READY'\` và \`is_valid = TRUE\` mới phải xuất.
3. Mỗi \`(batch_id, source_id)\` thuộc tập hợp lệ phải có **đúng một** record ở đích.
4. Record ở đích phải giữ đúng \`amount\` và \`currency\` theo phép biến đổi đã công bố.
5. Dữ liệu nguồn phải là **snapshot ổn định** của batch. Không thay đổi expected set giữa lúc job chạy và lúc verify.
6. Batch chỉ được đánh dấu **READY_FOR_CONSUMPTION** sau khi đối soát thành công.

Một mô hình logic:

- \(E\): tập các khóa **được kỳ vọng** có output.
- \(A\): tập các khóa **thực tế** tìm thấy ở output đã commit.
- \(M = E \setminus A\): tập **missing**.
- \(U = A \setminus E\): tập **unexpected**.

Với quan hệ 1:1, yêu cầu đủ dữ liệu là **\(|M| = 0\)**. Nếu hợp đồng còn yêu cầu không phát sinh bản ghi lạ và không trùng, ta cần cả \(|U| = 0\) và không có khóa xuất hiện quá một lần.

Lưu ý rằng \`A\` ở công thức là **tập khóa duy nhất**. Khi kiểm tra duplicate phải nhìn thêm số lần xuất hiện của từng khóa, vì phép trừ tập hợp không thể biểu diễn số bản sao.

### Tại sao phải khoanh vùng theo batch?

Giả sử có hai lần chạy cùng ghi vào một bảng:

~~~text
batchId=B20261116: O101, O102, O104, O106
batchId=B20261117: O201, O202
~~~

Nếu chỉ so tổng dòng toàn bảng hoặc chỉ join theo \`source_id\` mà không có \`batch_id\`, record thuộc batch khác có thể làm sai kết quả. Với hệ thống đa tenant, khóa đối soát có thể phải gồm **tenantId + businessDate + batchId + sourceId + outputVersion**.

Không nên dùng duy nhất \`jobExecutionId\` làm khóa nghiệp vụ của output khi một JobInstance có thể restart nhiều lần: một lô logic có thể được ghi bởi nhiều JobExecution nhưng phải đối soát như **một tập kết quả cuối**.

## 4. Ví dụ dữ liệu đầu vào và đầu ra

Giả sử bảng nguồn có:

| batch_id | source_id | status | is_valid | amount |
|---|---|---|---|---:|
| B42 | O101 | READY | TRUE | 100.00 |
| B42 | O102 | READY | TRUE | 45.50 |
| B42 | O103 | CANCELLED | TRUE | 20.00 |
| B42 | O104 | READY | TRUE | 80.00 |
| B42 | O105 | READY | FALSE | 15.00 |
| B42 | O106 | READY | TRUE | 25.00 |

Expected set là **O101, O102, O104, O106**. Bảng đầu ra thực tế sau khi job kết thúc:

| batch_id | source_id | amount |
|---|---|---:|
| B42 | O101 | 100.00 |
| B42 | O102 | 45.50 |
| B42 | O102 | 45.50 |
| B42 | O107 | 12.00 |

Số lượng record kỳ vọng và số dòng đích đều là **4**, nhưng:

- **Missing:** O104 và O106.
- **Unexpected:** O107.
- **Duplicate:** O102 xuất hiện hai lần.
- **Số record đích hợp lệ và duy nhất:** chỉ có O101, O102.

Bộ dữ liệu minh họa cố ý cho phép duplicate ở đích để thấy tình huống. Trong production nên có unique constraint theo khóa nghiệp vụ và thiết kế writer idempotent; constraint sẽ ngăn duplicate vật lý nhưng **không tự bảo đảm những record khác đều đã xuất hiện**.

## 5. Thiết kế schema hỗ trợ phát hiện bản ghi thiếu

Ví dụ DDL PostgreSQL:

~~~sql
CREATE TABLE staging_order (
    batch_id   VARCHAR(64) NOT NULL,
    source_id  VARCHAR(64) NOT NULL,
    status     VARCHAR(20) NOT NULL,
    is_valid   BOOLEAN NOT NULL,
    amount     NUMERIC(18, 2) NOT NULL,
    currency   VARCHAR(3) NOT NULL,
    PRIMARY KEY (batch_id, source_id)
);

CREATE TABLE processed_order (
    batch_id   VARCHAR(64) NOT NULL,
    source_id  VARCHAR(64) NOT NULL,
    amount     NUMERIC(18, 2) NOT NULL,
    currency   VARCHAR(3) NOT NULL,
    PRIMARY KEY (batch_id, source_id)
);

CREATE INDEX idx_staging_order_expected
    ON staging_order (batch_id, status, is_valid, source_id);
~~~

Trong môi trường test muốn mô phỏng duplicate, có thể dùng bảng không có primary key tạm thời hoặc một staging output riêng. Trong hệ thống thật, unique constraint giúp ngăn duplicate ngay lúc ghi.

Nếu key nguồn chưa duy nhất, phải quyết định record trùng nguồn là **dữ liệu bẩn phải fail**, hay được gộp theo quy tắc nghiệp vụ; đừng để một câu \`DISTINCT\` âm thầm che giấu lỗi.

Các chỉ mục nên phù hợp với câu truy vấn đối soát thực tế. Với batch lớn, thứ tự cột trong index, partitioning theo ngày và kích thước index cần được xem xét dựa trên workload cụ thể.

## 6. SQL phát hiện missing record bằng anti-join

### 6.1. Xác định số record kỳ vọng

~~~sql
SELECT COUNT(*) AS expected_count
FROM staging_order
WHERE batch_id = :batchId
  AND status = 'READY'
  AND is_valid = TRUE;
~~~

Với batch B42 ở ví dụ, expected_count là **4**.

Đối soát sơ bộ với tổng đích:

~~~sql
SELECT COUNT(*) AS actual_count
FROM processed_order
WHERE batch_id = :batchId;
~~~

Nếu hai số khác nhau, chắc chắn có điều kiện cần điều tra khi contract là 1:1. Nhưng **bằng nhau chưa chứng minh đủ dữ liệu**, vì có thể thiếu/thừa/trùng bù nhau.

### 6.2. Truy vấn \`NOT EXISTS\` — cách thông dụng

~~~sql
SELECT s.source_id, s.amount, s.currency
FROM staging_order s
WHERE s.batch_id = :batchId
  AND s.status = 'READY'
  AND s.is_valid = TRUE
  AND NOT EXISTS (
      SELECT 1
      FROM processed_order t
      WHERE t.batch_id = s.batch_id
        AND t.source_id = s.source_id
  )
ORDER BY s.source_id;
~~~

Ý nghĩa: mỗi record nguồn hợp lệ phải tìm được ít nhất một record có cùng khóa ở bảng đích. Nếu không có, đó là missing. Kết quả ví dụ là **O104, O106**.

Ưu điểm của \`NOT EXISTS\` là diễn đạt trực tiếp phép kiểm tra vắng mặt và tránh một số vấn đề liên quan tới \`NULL\` của \`NOT IN\`. Với khóa nghiệp vụ nullable, hãy chuẩn hóa hoặc quy định chính sách null trước khi đối soát; các key cần thiết tốt nhất nên \`NOT NULL\`.

### 6.3. \`LEFT JOIN ... IS NULL\`

Truy vấn tương đương khi cột khóa bên phải không nullable:

~~~sql
SELECT s.source_id
FROM staging_order s
LEFT JOIN processed_order t
  ON t.batch_id = s.batch_id
 AND t.source_id = s.source_id
WHERE s.batch_id = :batchId
  AND s.status = 'READY'
  AND s.is_valid = TRUE
  AND t.source_id IS NULL;
~~~

Điều kiện lọc record của bảng đích phải đặt trong \`ON\` thích hợp nếu có thêm \`output_version\`, \`tenant_id\` hoặc trạng thái publish. Đưa sai điều kiện của bảng đích xuống \`WHERE\` có thể vô tình biến left join thành inner join và làm mất record cần phát hiện.

### 6.4. Đếm missing

~~~sql
SELECT COUNT(*) AS missing_count
FROM staging_order s
WHERE s.batch_id = :batchId
  AND s.status = 'READY'
  AND s.is_valid = TRUE
  AND NOT EXISTS (
      SELECT 1
      FROM processed_order t
      WHERE t.batch_id = s.batch_id
        AND t.source_id = s.source_id
  );
~~~

Để lưu bằng chứng điều tra, có thể ghi lại **số lượng đầy đủ** cùng một số khóa missing làm mẫu. Đừng giới hạn \`COUNT\` bằng \`LIMIT 100\` rồi báo rằng chỉ có 100 record thiếu. Nếu dataset quá lớn, dùng truy vấn count riêng và lấy mẫu giới hạn riêng.

## 7. Kiểm tra unexpected, duplicate và sai giá trị cùng lúc

Missing detection thường là một phần của phép đối soát toàn bộ tập kết quả. Khi input kỳ vọng bốn record, output có bốn dòng nhưng thiếu hai, một phép đếm đơn thuần không phát hiện được nguyên nhân.

### 7.1. Unexpected output

~~~sql
SELECT t.source_id
FROM processed_order t
WHERE t.batch_id = :batchId
  AND NOT EXISTS (
      SELECT 1
      FROM staging_order s
      WHERE s.batch_id = t.batch_id
        AND s.source_id = t.source_id
        AND s.status = 'READY'
        AND s.is_valid = TRUE
  );
~~~

Kết quả phải rỗng. Nếu có, đó có thể là output từ dữ liệu không thuộc input hợp lệ, record dư của lần chạy trước hoặc lỗi phân vùng batch.

### 7.2. Duplicate output

~~~sql
SELECT batch_id, source_id, COUNT(*) AS occurrences
FROM processed_order
WHERE batch_id = :batchId
GROUP BY batch_id, source_id
HAVING COUNT(*) > 1;
~~~

Kết quả phải rỗng trong contract 1:1. Nếu bảng có primary key \`(batch_id, source_id)\`, duplicate không thể tồn tại theo hai cột đó; test vẫn cần xử lý lỗi writer khi replay dữ liệu đã ghi.

### 7.3. Mismatch của các trường dữ liệu

~~~sql
-- Ví dụ PostgreSQL: giả định amount và currency được copy nguyên.
SELECT s.source_id,
       s.amount   AS expected_amount,
       t.amount   AS actual_amount,
       s.currency AS expected_currency,
       t.currency AS actual_currency
FROM staging_order s
JOIN processed_order t
  ON t.batch_id = s.batch_id
 AND t.source_id = s.source_id
WHERE s.batch_id = :batchId
  AND s.status = 'READY'
  AND s.is_valid = TRUE
  AND (
      s.amount IS DISTINCT FROM t.amount
      OR s.currency IS DISTINCT FROM t.currency
  );
~~~

\`IS DISTINCT FROM\` hỗ trợ so sánh có nhận biết \`NULL\` trên PostgreSQL; tùy hệ quản trị cơ sở dữ liệu có thể cần cú pháp tương đương. Nếu processor có quy tắc làm tròn, đổi đơn vị tiền tệ hoặc chuẩn hóa trạng thái, hãy so với **giá trị expected sau transform** chứ không so máy móc với input gốc.

Với dữ liệu tiền tệ, có thể đối soát thêm \`SUM(amount)\` **theo từng currency**. Tổng giá trị bằng nhau vẫn có thể có hai dòng sai bù trừ; kiểm tra theo khóa vẫn cần thiết khi hợp đồng yêu cầu độ chính xác từng record.

## 8. Tránh false positive: snapshot, watermark và thời điểm verify

Một lỗi phổ biến là job đọc một phiên bản input nhưng đối soát với phiên bản input đã thay đổi:

~~~text
10:00  Job bắt đầu, reader thấy 1.000 record
10:03  Upstream thêm 25 record mới vào bảng nguồn
10:05  Job hoàn tất, ghi đúng 1.000 record đã đọc
10:06  Verification query thấy 1.025 record nguồn
       -> Báo thiếu 25 record dù chúng chưa thuộc lần chạy
~~~

Để không tạo **false positive**, cần đóng băng tập input theo một trong các chiến lược:

- **Staging snapshot:** copy record của batch vào bảng riêng, gắn \`batchId\`, đóng trạng thái snapshot trước khi Job chạy.
- **Watermark:** lưu thời điểm/sequence/offset chốt dữ liệu, reader và verifier cùng sử dụng ranh giới đó.
- **Source version:** dùng \`sourceVersion\`, file checksum hoặc manifest cố định.
- **Snapshot transaction:** có thể dùng transaction isolation phù hợp trong một khoảng ngắn, nhưng không mặc định giữ một transaction đọc nguồn trong suốt job dài.

Nếu reader dùng \`JdbcPagingItemReader\` và nguồn bị cập nhật trong lúc xử lý, cần sort key ổn định và quy tắc xử lý thay đổi; offset/paging hoặc thứ tự không ổn định có thể gây thiếu/trùng record.

**Điểm chốt nguồn phải được lưu như một phần của hợp đồng batch**, không chỉ là một timestamp tùy ý lấy tại thời điểm verify.

### Dữ liệu cuối chỉ nên verify khi sẵn sàng

Nếu writer ghi file đang mở, event lên broker hoặc dữ liệu đến hệ đích có độ trễ, đối soát ngay lúc một Step nội bộ hoàn tất có thể thấy output thiếu tạm thời. Cần quy định rõ:

1. Producer đã kết thúc và commit/đóng artifact.
2. Bên nhận đã xác nhận ở cấp độ cần thiết, nếu hợp đồng bao gồm xử lý downstream.
3. Cửa sổ chờ eventual consistency đã hết hoặc có marker READY.
4. Version output và phạm vi đối soát được xác định bất biến.

Không chờ vô hạn để “hợp thức hóa” một record chưa xuất; phải có deadline và trạng thái **PENDING/FAILED** rõ ràng.

## 9. Liên hệ với read, process, write, skip và filter của Spring Batch

Giả sử một Step đọc 1.000 item, filter 100, cho phép skip 5 và writer dự kiến xuất một record cho mỗi item còn lại. Số output kỳ vọng **có thể là 895** nếu cả 100 filter và 5 skip đều được hợp đồng chấp nhận.

Tuy nhiên, không thể áp dụng công thức này một cách mù quáng:

\[
\text{expectedWriteCount} =
\text{readCount} - \text{filterCount} - \text{skipCount}
\]

Công thức trên không luôn đúng vì \`readSkipCount\` có thể liên quan đến item không nằm trong \`readCount\`, processor có thể tạo 1:n output, writer có thể thực hiện upsert/aggregation, transaction có rollback hoặc các thành phần giữ state.

Trong Spring Batch:

- \`readCount\`: số item đọc thành công theo thống kê Step.
- \`readSkipCount\`: các lỗi đọc được bỏ qua theo cấu hình.
- \`processSkipCount\`: item lỗi trong processor được bỏ qua.
- \`writeSkipCount\`: item lỗi ghi được bỏ qua theo cơ chế phù hợp.
- \`filterCount\`: item processor trả \`null\`, không đi tới writer.
- \`writeCount\`: số item được framework ghi nhận ở writer, không phải số dòng unique đã commit tại mọi hệ thống ngoài.
- \`rollbackCount\`: số lần rollback Step ghi nhận.

Các counter là **tín hiệu để điều tra**. Muốn tìm đúng bản ghi thiếu, vẫn phải có **expected key list** và **actual key list**.

### Khi nào skip làm thiếu record?

Nếu nghiệp vụ yêu cầu mọi đơn hợp lệ phải được đưa tới đích, một item bị skip do lỗi API hoặc parse dữ liệu sẽ tạo **thiếu output theo yêu cầu nghiệp vụ**. Job có thể vẫn \`COMPLETED\` nếu \`skipLimit\` cho phép, nhưng verification phải fail hoặc ghi nhận reject được chấp thuận theo policy.

Nếu contract cho phép loại bỏ bản ghi không hợp lệ, cần có một **rejection register** chứa \`batchId\`, \`sourceId\`, mã lý do và quyết định chấp nhận. Khi đó expected set được định nghĩa từ snapshot nguồn **trừ các rejection đã được chính sách cho phép**. Không dùng “mọi record không xuất ở đích đều là skipped hợp lệ” để tự chứng minh kết quả.

## 10. Chuyển phép kiểm tra thành một Step xác minh output

Một cách triển khai mạnh trong Spring Batch là chạy Step **verifyMissingRecordsStep** sau Step xử lý chính. Nếu thiếu dữ liệu, tasklet ném exception để **Step verification FAILED**, từ đó job không kết thúc bình thường ở trạng thái \`COMPLETED\` trong flow tuần tự mặc định.

~~~text
importOrdersStep
       |
       v
verifyMissingRecordsStep
       |
       +------ Có missing/unexpected/duplicate ----> FAILED
       |
       +------ Đủ và đúng -------------------------> publishOutputStep
                                                         |
                                                         v
                                                     COMPLETED
~~~

Đặt verification trong Step chính thức giúp status job có ý nghĩa hơn. Nếu chỉ kiểm tra sau khi job đã \`COMPLETED\` trong \`JobExecutionListener.afterJob\`, một exception từ listener không phải cơ chế đáng tin cậy để đổi kết quả job đã kết thúc thành FAILED.

### Ví dụ Step kiểm tra database

Giả sử hai bảng \`staging_order\` và \`processed_order\` dùng cùng datasource có thể truy vấn bằng \`JdbcTemplate\`. Đây là ví dụ Spring Batch 5+:

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
public Step verifyMissingRecordsStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        JdbcTemplate jdbcTemplate) {

    return new StepBuilder("verifyMissingRecordsStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                Object rawBatchId = chunkContext.getStepContext()
                        .getJobParameters().get("batchId");
                if (!(rawBatchId instanceof String batchId)
                        || batchId.isBlank()) {
                    throw new IllegalArgumentException(
                            "Missing job parameter batchId");
                }

                Long expected = jdbcTemplate.queryForObject(
                        """
                        SELECT COUNT(*)
                        FROM staging_order
                        WHERE batch_id = ?
                          AND status = 'READY'
                          AND is_valid = TRUE
                        """,
                        Long.class, batchId);

                Long actual = jdbcTemplate.queryForObject(
                        """
                        SELECT COUNT(*)
                        FROM processed_order
                        WHERE batch_id = ?
                        """,
                        Long.class, batchId);

                Long missing = jdbcTemplate.queryForObject(
                        """
                        SELECT COUNT(*)
                        FROM staging_order s
                        WHERE s.batch_id = ?
                          AND s.status = 'READY'
                          AND s.is_valid = TRUE
                          AND NOT EXISTS (
                              SELECT 1
                              FROM processed_order t
                              WHERE t.batch_id = s.batch_id
                                AND t.source_id = s.source_id
                          )
                        """,
                        Long.class, batchId);

                Long unexpected = jdbcTemplate.queryForObject(
                        """
                        SELECT COUNT(*)
                        FROM processed_order t
                        WHERE t.batch_id = ?
                          AND NOT EXISTS (
                              SELECT 1
                              FROM staging_order s
                              WHERE s.batch_id = t.batch_id
                                AND s.source_id = t.source_id
                                AND s.status = 'READY'
                                AND s.is_valid = TRUE
                          )
                        """,
                        Long.class, batchId);

                Long duplicates = jdbcTemplate.queryForObject(
                        """
                        SELECT COUNT(*)
                        FROM (
                            SELECT source_id
                            FROM processed_order
                            WHERE batch_id = ?
                            GROUP BY source_id
                            HAVING COUNT(*) > 1
                        ) d
                        """,
                        Long.class, batchId);

                if (expected == null || actual == null
                        || missing == null || unexpected == null
                        || duplicates == null
                        || !expected.equals(actual)
                        || missing != 0L
                        || unexpected != 0L
                        || duplicates != 0L) {
                    throw new IllegalStateException(
                            "Output reconciliation failed for batchId="
                                    + batchId
                                    + ", expected=" + expected
                                    + ", actual=" + actual
                                    + ", missing=" + missing
                                    + ", unexpected=" + unexpected
                                    + ", duplicateKeys=" + duplicates);
                }

                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
}
~~~

Trong ứng dụng thật, phương thức \`@Bean\` nằm trong \`@Configuration\` và cần các bean Batch infrastructure phù hợp. Tasklet trên kiểm tra quan hệ 1:1 và giả định **input snapshot đã chốt**. Nó chưa kiểm tra các trường \`amount\`, \`currency\`; nếu contract yêu cầu, phải bổ sung phép so sánh dữ liệu như ở mục 7.

**Một lỗi verification không tự rollback các chunk của Step trước đó đã commit.** Vì vậy, batch cần giữ output ở trạng thái staging/chưa READY để consumer không sử dụng dữ liệu thiếu trong lúc chờ sửa và chạy đối soát lại.

### Đưa verification vào flow

~~~java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;

@Bean
public Job importOrdersJob(
        JobRepository jobRepository,
        @Qualifier("importOrdersStep") Step importOrdersStep,
        @Qualifier("verifyMissingRecordsStep") Step verifyMissingRecordsStep,
        @Qualifier("publishOutputStep") Step publishOutputStep) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .start(importOrdersStep)
            .next(verifyMissingRecordsStep)
            .next(publishOutputStep)
            .build();
}
~~~

\`importOrdersStep\` và \`publishOutputStep\` là Step giả định đã được định nghĩa ở cấu hình khác. Với flow tuần tự bình thường, Step sau chỉ chạy khi Step trước kết thúc theo điều kiện chuyển tiếp phù hợp.

Nếu muốn kiểm tra từ hệ thống bên ngoài sau khi job kết thúc, dùng JobExplorer để đọc trạng thái và service đối soát riêng. Khi đó phải có trạng thái business batch như **VERIFICATION_PENDING**, **VERIFIED** hoặc **REJECTED**, bởi \`BatchStatus.COMPLETED\` một mình chưa chứng minh output đã đạt hợp đồng ngoài Batch.

## 11. Phát hiện missing từ file CSV, JSON hoặc XML

Đối với file output, phép so khớp cần đọc **record logic** chứ không chỉ đếm dòng vật lý:

~~~csv
batchId,sourceId,amount
B42,O101,100.00
B42,O102,45.50
~~~

Những kiểm tra thường dùng:

1. File output phải thuộc đúng **batchId/version**; không đọc nhầm file cũ.
2. Writer đã đóng file và output đã được công bố theo contract.
3. Parser đọc được toàn bộ CSV/JSON/XML, schema và encoding đúng.
4. Lấy tập **sourceId** thực tế từ record đã parse.
5. So expected keys với actual keys để tìm missing/unexpected; kiểm tra trùng key.
6. Đối soát các giá trị quan trọng và checksum khi cần.
7. Chỉ phát hành manifest/READY marker khi verification thành công.

**Không dùng cách đếm ký tự xuống dòng để đo số record CSV**: một trường được quote hợp lệ có thể chứa newline; JSON có thể chứa nhiều record trong một mảng trên cùng dòng.

Với file lớn, nếu không thể nạp toàn bộ key vào RAM, có thể:

- Trích các khóa expected/actual ra hai file đã sắp xếp rồi **merge-diff** theo thứ tự.
- Nạp key vào bảng staging tạm để chạy anti-join bằng SQL.
- Chia hash partition theo key rồi đối soát từng partition.
- Sử dụng checksum/tổng số để phát hiện nhanh, nhưng sau đó vẫn cần đối soát khóa nếu contract yêu cầu phát hiện chính xác missing.

**Checksum không đủ để cho biết record nào thiếu**. Bloom filter có thể hữu ích để tiết kiệm RAM khi kiểm tra membership sơ bộ, nhưng có false positive nên không phải bằng chứng tuyệt đối rằng không có record thiếu.

### Quy trình xuất file an toàn

~~~text
orders-B42.csv.part
       |
       v
Writer đóng file
       |
       v
Parse + count + exact-key reconciliation
       |
       +------ FAIL --> Quarantine / giữ version tạm
       |
       v
Publish orders-B42-v1.csv + manifest READY
       |
       v
Consumer bắt đầu đọc
~~~

Rename nguyên tử chỉ có thể giả định trong điều kiện filesystem phù hợp; khi dùng object storage, nên công bố một object/version ổn định và sau đó tạo marker/manifest.

## 12. Missing record trong Kafka, API và hệ thống bất đồng bộ

Không phải mọi output đều có mặt ngay sau một lời gọi writer thành công:

- Kafka producer có thể xác nhận đã ghi message vào broker, nhưng consumer chưa xử lý xong.
- HTTP service có thể trả \`202 Accepted\` và xử lý bất đồng bộ sau đó.
- Data warehouse hoặc search index có thể có độ trễ ingest/refresh.
- Một Step phát outbox event, trong khi publisher độc lập chưa chuyển event đi.

Trong những trường hợp này phải định nghĩa **cấp độ được xem là đã có output**:

| Cấp độ | Tín hiệu | Có đủ để xác nhận record đã đến đích cuối không? |
|---|---|---|
| Writer gọi API mà không lỗi | Method return bình thường | Không chắc; phụ thuộc semantics API |
| Broker xác nhận publish | Message được broker nhận | Chưa chứng minh consumer xử lý |
| Downstream ACK theo business key | Consumer xác nhận record | Có thể đủ, nếu ACK là bền vững theo contract |
| Record xuất hiện ở hệ đích | Truy vấn được theo key/version | Có thể dùng nếu trạng thái đã commit và nguồn đọc nhất quán |
| Manifest READY sau đối soát | Batch version được công bố | Phù hợp nếu manifest chỉ được tạo sau validation |

Ví dụ với HTTP service, hãy tạo request có **idempotency key** ổn định, lưu receipt ID và kiểm tra trạng thái theo receipt trước khi kết luận missing. Không liên tục gửi lại request thay vì kiểm tra vì có thể tạo side effect lặp.

Với Kafka, có thể cần một bảng acknowledgement theo \`batchId + sourceId\` tại consumer hoặc một audit sink bền vững. **Kafka offset đã commit** không luôn đồng nghĩa record đã được ghi vào một business database khác, trừ khi kiến trúc/transaction semantics bảo đảm điều đó.

### Cửa sổ cho phép trễ

Nếu contract cho downstream tối đa năm phút sau publish:

~~~text
10:00  Producer phát event
10:02  Consumer chưa ghi output -> PENDING
10:04  Consumer ghi thành công -> PRESENT
10:05  Deadline; nếu chưa có mới kết luận MISSING
~~~

Khi đã hết deadline, verification cần báo thiếu thật và tạo sự kiện điều tra hoặc recovery; không tự tăng thời gian chờ vô hạn để che giấu lỗi.

## 13. Partitioning, parallel steps và restart

### Missing do xử lý song song

Một job có thể chia input theo range:

~~~text
Partition 0: source_id 0000..2499
Partition 1: source_id 2500..4999
Partition 2: source_id 5000..7499
Partition 3: source_id 7500..9999
~~~

Nếu một partition bị lỗi, không trả kết quả về manager hoặc được đánh dấu nhầm là hoàn thành, output có thể thiếu cả một dải record. Vì vậy, ngoài exact-set reconciliation toàn batch, nên lưu:

- Partition ID và ranh giới input.
- Expected record count/keys per partition.
- StepExecution status, read/write/skip/rollback counters theo partition.
- Thời điểm commit và marker hoàn tất partition.
- Số missing per partition sau verification.

Tránh cộng kết quả partition rồi coi đủ nếu ranh giới partition chồng lấn hoặc bỏ sót key. Một partition ghi 100 record trùng với partition khác có thể làm tổng count đúng dù record ở partition thứ ba thiếu.

### Missing sau restart

JobInstance có thể có nhiều JobExecution:

~~~text
JobInstance B42
  |
  +-- JobExecution #701
  |      Chunk 1..5 committed
  |      Chunk 6 failed
  |
  +-- JobExecution #705 (restart)
         Resume từ checkpoint
         Ghi phần còn lại
~~~

Khi đối soát **output cuối của batch**, phải tính tất cả record hợp lệ đã commit từ những execution thuộc cùng lô, không chỉ \`writeCount\` của execution mới nhất. Nếu chỉ đếm dòng ghi trong restart, dễ báo missing giả.

Ngược lại, nếu checkpoint đi xa hơn output vì metadata và database nghiệp vụ không cùng transaction, restart có thể bỏ qua những record chưa được ghi. Nếu output đi xa hơn checkpoint, restart có thể ghi lặp. Cơ chế missing record detection sẽ phát hiện thiếu; cần kết hợp duplicate detection và writer idempotent để xử lý chiều còn lại.

### Không sửa input khi restart theo vị trí

Với FlatFileItemReader hoặc paging reader có checkpoint theo vị trí, input bị chèn/xóa/sắp xếp lại giữa hai execution có thể khiến record bị bỏ qua hoặc xử lý hai lần. Hãy giữ snapshot, watermark hoặc file/version input bất biến trong phạm vi JobInstance, rồi đối soát theo chính version đó.

## 14. Khi mapping không phải 1:1

Không phải mọi item nguồn đều phải có một hàng output:

| Dạng xử lý | Cách định nghĩa expected |
|---|---|
| **1:1** | Mỗi source_id hợp lệ có đúng một output |
| **1:n** | Mỗi source_id phải có đủ các khóa con mong đợi, ví dụ \`(orderId, lineNo)\` |
| **n:1** | Nhóm input được tổng hợp thành một record theo group key, ví dụ \`(businessDate, currency)\` |
| **Filter hợp lệ** | Expected chỉ gồm input thỏa quy tắc filter |
| **Soft delete/update** | Có thể yêu cầu record có trạng thái cuối đúng thay vì insert record mới |
| **Event stream** | Có thể kỳ vọng event type và event version, không chỉ business key |

### Ví dụ 1:n

Một đơn O101 gồm ba dòng hàng, đầu ra phải có các khóa:

~~~text
(O101, line1)
(O101, line2)
(O101, line3)
~~~

Nếu output chỉ có \`line1\` và \`line3\`, phép kiểm tra đơn thuần “O101 tồn tại” sẽ **không phát hiện missing line2**. Expected key phải là \`(orderId, lineNo)\`, không chỉ \`orderId\`.

### Ví dụ n:1

Một job tổng hợp giao dịch theo ngày và loại tiền tệ có thể xuất một record cho mỗi \`(date, currency)\`. Missing detection kiểm tra **group key kỳ vọng**, tổng số record, số giao dịch đóng góp, tổng tiền và công thức transform. Không thể lấy từng transaction ID để đối chiếu trực tiếp với bảng tổng hợp.

Trước khi xây query, hãy viết rõ **cardinality** và **khóa kết quả**. Nếu không, hệ thống có thể báo sai hàng nghìn missing record chỉ vì nhầm mô hình dữ liệu.

## 15. Tối ưu đối soát cho batch lớn

Với hàng triệu record, thực hiện đối soát chậm hoặc chiếm khóa DB quá lâu có thể ảnh hưởng throughput. Một số cách thiết kế:

**1. Giới hạn phạm vi bằng batch/version.** Luôn có predicate \`batch_id = ?\`, ngày hoặc partition phù hợp. Tránh đối chiếu toàn bộ lịch sử mỗi lần chạy.

**2. Dùng khóa và index ổn định.** Index trên \`(batch_id, source_id)\` thường quan trọng cho anti-join. Với bảng nguồn, index có thể bổ sung các cột điều kiện lọc expected set.

**3. Chia verification theo partition.** Chỉ khi các partition có ranh giới không chồng lấn và bao phủ đủ expected set, mới tổng hợp kết quả thành đánh giá batch toàn cục.

**4. Phân tầng kiểm tra.** Count và checksum có thể giúp phát hiện nhanh, nhưng đối soát key vẫn cần thiết khi yêu cầu tính đầy đủ tuyệt đối.

**5. Tránh tải toàn bộ ID về JVM.** Dùng SQL \`NOT EXISTS\`, bảng staging, set-based operations hoặc streaming sort/merge thay vì \`List<String>\` cho hàng triệu khóa.

**6. Ghi audit có giới hạn.** Lưu \`missingCount\` đầy đủ cùng ví dụ tối đa N khóa; xuất danh sách đầy đủ ra artifact riêng nếu cần xử lý hàng loạt.

**7. Đảm bảo tính nhất quán khi đọc.** Đối soát nhiều câu query trong khi writer khác còn cập nhật có thể thấy các trạng thái khác nhau. Chốt output version và dùng transaction isolation/snapshot hợp lý.

**8. Có kế hoạch timeout.** Verification truy vấn lớn có thể bị timeout; không coi timeout là “không có missing”. Kết quả phải ở trạng thái chưa xác minh hoặc FAILED.

### Kiểm tra theo tầng

~~~text
Stage 1: Is batch/output version finalized?
          |
          v
Stage 2: Count + high-level business totals
          |
          v
Stage 3: Exact missing/extra/duplicate keys
          |
          v
Stage 4: Value/schema checks
          |
          v
Stage 5: READY + audit
~~~

Với dữ liệu ít, có thể thực hiện đủ các tầng mỗi lần. Với dữ liệu rất lớn, có thể chạy những kiểm tra rẻ theo từng partition và kiểm tra sâu ở cuối, nhưng không đánh đổi mức đảm bảo mà hợp đồng nghiệp vụ yêu cầu.

## 16. Ghi audit, metric và cảnh báo missing record

Một kết quả verification phải liên kết được với job, input và output cụ thể:

~~~text
event=output.reconciliation.completed
jobName=importOrdersJob
jobInstanceId=301
jobExecutionId=910
batchId=B42
sourceVersion=2026-11-16-v1
outputVersion=v3
expectedCount=400000
actualCount=399998
missingCount=2
unexpectedCount=0
duplicateKeyCount=0
valueMismatchCount=0
verificationStatus=FAILED
verifiedAt=2026-11-16T09:30:00+07:00
~~~

Đây là dữ liệu minh họa. Khi thiếu record, có thể ghi một số key đã được cho phép xuất log, reason code và partition liên quan. Không ghi nguyên dữ liệu cá nhân hoặc payload nhạy cảm vào log và metrics.

Metric đề xuất:

| Metric | Ý nghĩa |
|---|---|
| \`batch_expected_records\` | Số record được yêu cầu có output |
| \`batch_actual_records\` | Số record output quan sát được |
| \`batch_missing_records\` | Số record expected vắng mặt |
| \`batch_unexpected_records\` | Số output ngoài expected set |
| \`batch_duplicate_keys\` | Số khóa bị lặp |
| \`batch_reconciliation_failures_total\` | Số lần đối soát không đạt |
| \`batch_last_verified_timestamp\` | Lần đối soát hoàn tất gần nhất |
| \`batch_verification_duration_seconds\` | Thời gian chạy verification |

Tên trên là đề xuất cho ứng dụng, **không phải metric mặc định của Spring Batch**. Để tránh high cardinality trong Prometheus, không dùng \`sourceId\`, \`jobExecutionId\` hoặc \`batchId\` làm nhãn trên mọi time series. Chúng phù hợp hơn trong log, trace hoặc audit database.

### Chính sách cảnh báo

Với batch tài chính hoặc dữ liệu bắt buộc đầy đủ, **missingCount > 0** sau deadline thường phải chặn publish và cảnh báo. Với một số pipeline best-effort, có thể có ngưỡng dung sai được quy định, nhưng phải nêu rõ tập bản ghi và mức độ ảnh hưởng; tỷ lệ 0,01% vẫn có thể nghiêm trọng nếu rơi vào một khách hàng hoặc giao dịch quan trọng.

Các cảnh báo thường dùng:

- Expected set đã chốt nhưng không có output sau deadline.
- Verification thất bại vì missing/duplicate/unexpected.
- Verification không chạy hoặc lỗi truy cập dữ liệu.
- Số missing tăng đột ngột theo source/partition/job.
- Job \`COMPLETED\` nhưng không có marker VERIFIED/READY sau thời gian cho phép.

## 17. Kiểm thử missing record detection

Để kiểm thử cơ chế này, nên dùng **database test có schema thật** và fixture có key cụ thể. Một test phải chứng minh rằng phép kiểm tra bắt được trường hợp có bản ghi thiếu **ngay cả khi tổng số dòng bằng nhau**.

### Ma trận tình huống

| Fixture | Expected | Actual | Kết quả |
|---|---|---|---|
| Đủ, đúng mọi key | O1,O2,O3 | O1,O2,O3 | PASS |
| Thiếu một key | O1,O2,O3 | O1,O2 | Missing O3; FAIL |
| Thiếu một và thừa một | O1,O2,O3 | O1,O2,O4 | Missing O3, unexpected O4; FAIL dù count bằng |
| Thiếu một và trùng một | O1,O2,O3 | O1,O2,O2 | Missing O3, duplicate O2; FAIL dù count bằng |
| Record bị filter hợp lệ | O1,O2 | O1,O2 (record CANCELLED không expected) | PASS |
| Skip không được chấp nhận | O1,O2,O3 | O1,O2 | Missing O3; FAIL |
| Skip có audit được chấp nhận | O1,O2 sau policy loại O3 | O1,O2 | PASS nếu contract cho phép |
| Một record khác batch | B42: O1,O2 | B42: O1; B43: O2 | Missing O2 ở B42 |
| Restart đã ghi một phần | Expected O1..O6 | Output từ hai execution hợp lại đủ O1..O6 | PASS |
| Value mismatch | Key đủ nhưng amount sai | Key đủ | FAIL theo phép kiểm tra giá trị |
| Output chưa READY | Expected đủ nhưng downstream còn xử lý | Chưa quan sát đủ | PENDING tới deadline, chưa công bố |
| Không thể query đích | Expected đủ | DB unavailable | Verification FAILED/UNKNOWN, không tự PASS |

### Ví dụ integration test cho Step xác minh

Ví dụ dưới dùng Spring Batch Test và Spring Boot, giả định test context đã đăng ký **verifyMissingRecordsStep** và database đã tạo hai bảng ở mục 5. Test khởi chạy **Step xác minh** riêng để kiểm tra đúng thuật toán đối soát, không cần chạy toàn bộ import job.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.UUID;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class MissingRecordVerificationIT {

    @Autowired
    JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @BeforeEach
    void resetFixtures() {
        // Dùng database test cô lập; không chạy trên DB dùng chung.
        jdbcTemplate.update("DELETE FROM processed_order");
        jdbcTemplate.update("DELETE FROM staging_order");
    }

    @Test
    void failsWhenAnExpectedRecordIsMissing() throws Exception {
        insertExpected("B-TEST-1", "O1", "10.00");
        insertExpected("B-TEST-1", "O2", "20.00");
        insertExpected("B-TEST-1", "O3", "30.00");

        insertActual("B-TEST-1", "O1", "10.00");
        insertActual("B-TEST-1", "O2", "20.00");

        JobExecution result = launchVerification("B-TEST-1");
        assertEquals(BatchStatus.FAILED, result.getStatus());

        Long missing = jdbcTemplate.queryForObject(
                """
                SELECT COUNT(*)
                FROM staging_order s
                WHERE s.batch_id = ? AND s.status = 'READY'
                  AND s.is_valid = TRUE
                  AND NOT EXISTS (
                      SELECT 1 FROM processed_order t
                      WHERE t.batch_id = s.batch_id
                        AND t.source_id = s.source_id
                  )
                """,
                Long.class, "B-TEST-1");
        assertEquals(1L, missing);
    }

    @Test
    void completesWhenExpectedAndActualKeysMatch() throws Exception {
        insertExpected("B-TEST-2", "O1", "10.00");
        insertExpected("B-TEST-2", "O2", "20.00");
        insertActual("B-TEST-2", "O1", "10.00");
        insertActual("B-TEST-2", "O2", "20.00");

        JobExecution result = launchVerification("B-TEST-2");
        assertEquals(BatchStatus.COMPLETED, result.getStatus());
    }

    private JobExecution launchVerification(String batchId)
            throws Exception {
        JobParameters params = new JobParametersBuilder()
                .addString("batchId", batchId)
                .addString("testRunId", UUID.randomUUID().toString())
                .toJobParameters();
        return jobLauncherTestUtils.launchStep(
                "verifyMissingRecordsStep", params);
    }

    private void insertExpected(
            String batchId, String orderId, String amount) {
        jdbcTemplate.update(
                """
                INSERT INTO staging_order
                    (batch_id, source_id, status, is_valid, amount, currency)
                VALUES (?, ?, 'READY', TRUE, ?, 'USD')
                """,
                batchId, orderId, new java.math.BigDecimal(amount));
    }

    private void insertActual(
            String batchId, String orderId, String amount) {
        jdbcTemplate.update(
                """
                INSERT INTO processed_order
                    (batch_id, source_id, amount, currency)
                VALUES (?, ?, ?, 'USD')
                """,
                batchId, orderId, new java.math.BigDecimal(amount));
    }
}
~~~

Với \`@SpringBatchTest\`, cần có hạ tầng test và các bean Job/Step phù hợp, đồng thời cấu hình \`JobLauncherTestUtils\` nếu context có nhiều Job. \`spring.batch.job.enabled=false\` ngăn Spring Boot tự khởi chạy job khi dựng context. Test trên dùng **database test riêng**, bởi \`DELETE\` toàn bảng không an toàn khi test chạy song song hoặc môi trường dùng chung.

Sau khi kiểm tra Step riêng, thêm integration test chạy **toàn bộ Job flow**: cố tình làm Step import bỏ sót O3, xác nhận verify Step FAILED và Step publish không chạy. Test này kiểm tra hợp đồng giữa xử lý, đối soát và công bố output.

## 18. Quy trình xử lý khi phát hiện record thiếu

Khi verification phát hiện missing, không nên chỉ ghi cảnh báo rồi để consumer đọc output:

1. **Khoanh vùng batch/version:** jobExecutionId, jobInstanceId, batchId, source snapshot và nơi chứa output.
2. **Chặn publish:** đặt trạng thái output ở mức INVALID/QUARANTINED hoặc không tạo marker READY.
3. **Thu thập bằng chứng:** missing count đầy đủ, một số key mẫu, StepExecution và partition liên quan.
4. **Xác định nguyên nhân:** reader không nhận record, filter/skip sai, writer lỗi, commit/rollback, checkpoint, partition mất hoặc downstream chậm.
5. **Chọn cách phục hồi:** restart đúng JobInstance, replay các key thiếu bằng writer idempotent hoặc tạo batch correction rõ ràng.
6. **Không gây duplicate:** kiểm tra business key, output đã commit và side effect API trước khi gửi lại.
7. **Chạy lại verification:** kiểm tra missing/unexpected/duplicate và giá trị cần thiết sau khi sửa.
8. **Công bố bản verified:** chỉ chuyển sang READY khi mọi điều kiện bắt buộc đạt và lưu audit.

### Ví dụ thiếu do checkpoint và output không đồng bộ

Nếu JobRepository và dữ liệu nghiệp vụ dùng transaction khác nhau, một chunk có thể cập nhật checkpoint thành công nhưng writer chưa commit hoặc ngược lại:

~~~text
Expected: O001..O200
Output đã commit: O001..O100
Checkpoint ghi nhận: đã đọc tới O150

Restart từ checkpoint:
  Tiếp tục O151..O200
  O101..O150 vẫn thiếu
~~~

Missing detection trên expected set sẽ phát hiện O101..O150; chỉ tin vào trạng thái restart \`COMPLETED\` là không đủ. Khi phát hiện, cần reconcile từng khóa và đảm bảo không có job khác cùng xử lý lô trước khi replay.

### Ví dụ thiếu vì phân loại sai filtered record

Nếu processor trả \`null\` khi gọi external service bị timeout (thay vì ném exception để retry/fail), item có thể bị **filter nhầm** và job vẫn thành công. Nếu contract chỉ cho phép filter đơn \`CANCELLED\`, record hợp lệ sẽ thiếu ở output. Việc đối soát expected keys với output giúp phát hiện lỗi ngay cả khi counter \`filterCount\` vẫn có vẻ hợp lý.

## 19. Những sai lầm thường gặp

**Chỉ so sánh \`COUNT(*)\`.** Một record thiếu có thể bị bù bởi record thừa hoặc duplicate. Dùng anti-join và kiểm tra unexpected/duplicate.

**Dùng toàn bộ nguồn làm expected mà bỏ qua quy tắc filter.** Sinh false positive cho record vốn không cần xuất. Chốt điều kiện expected theo hợp đồng.

**Coi mọi skip là hợp lệ.** Một record bị skip do lỗi hệ thống có thể là missing nghiêm trọng. Chỉ loại khỏi expected nếu có policy và audit cụ thể.

**Lấy input hiện tại thay vì snapshot của lần chạy.** Record mới thêm vào sau khi job bắt đầu sẽ bị báo thiếu sai. Dùng watermark/version bất biến.

**Không phân biệt batchId và jobExecutionId.** Một batch có thể restart nhiều lần; output cuối thường phải đối soát trên toàn batch, không chỉ execution cuối.

**Chỉ kiểm tra đầu ra trước khi writer commit/đóng file.** Gây thiếu tạm thời hoặc đọc file dở dang. Xác định trạng thái output ready.

**Dùng \`NOT IN\` trên cột có thể NULL mà không xét semantics SQL.** \`NULL\` có thể làm predicate trả UNKNOWN. Dùng \`NOT EXISTS\` hoặc chuẩn hóa khóa.

**Dùng phép join thiếu một phần khóa composite.** Record của tenant hoặc batch khác có thể che lấp missing thật. Join đầy đủ các chiều nhận diện.

**Định nghĩa expected theo đúng dữ liệu writer đã ghi.** Nếu writer bỏ sót item, cùng một nguồn sai được dùng cho expected và actual sẽ tự xác nhận kết quả. Expected phải dựa trên nguồn đã chốt độc lập phù hợp.

**Xem checksum bằng nhau là bằng chứng đủ mọi key.** Checksum có thể không cho biết record nào bị thiếu hoặc có collision. Dùng exact-key reconciliation khi yêu cầu tính đầy đủ.

**Không xác minh trạng thái consumer với hệ bất đồng bộ.** Broker đã nhận message không chứng minh hệ đích business đã ghi xong. Định nghĩa ACK/receipt và deadline rõ ràng.

**Không chặn publish khi verification FAILED.** Job có thể để lại một phần output đã commit; consumer không nên coi đó là dữ liệu cuối.

**Dùng \`writeCount\` thay cho truy vấn output thực tế.** Writer có thể cập nhật nhiều dòng, writer ngoài transaction có thể phát sinh side effect, hoặc restart tích lũy output qua nhiều execution.

**Không kiểm tra mapping 1:n hoặc n:1.** So một khóa nguồn với một khóa đích sai mô hình và bỏ sót record con hoặc kết quả tổng hợp.

**Chỉ báo số missing, không giữ key và phạm vi.** Khi sửa lỗi, kỹ sư cần biết batch/version/partition nào và những record nào thiếu.

## 20. Nguyên tắc triển khai missing record detection

Một cơ chế missing record detection đáng tin cậy trong Spring Batch cần:

1. **Expected set rõ ràng** từ snapshot nguồn và quy tắc nghiệp vụ được chốt.
2. **Khóa đối soát chính xác**, gồm batch/tenant/version và khóa business phù hợp với cardinality.
3. **Actual set bền vững**, chỉ kiểm tra output đã commit hoặc bên nhận xác nhận.
4. **Phép kiểm tra exact-key**, kết hợp missing, unexpected, duplicate và kiểm tra giá trị khi cần.
5. **Verification Step hoặc quy trình audit có trạng thái**, để lỗi chất lượng dữ liệu ngăn output được công bố.
6. **Thiết kế restart/idempotency**, giúp khôi phục bản ghi thiếu mà không tạo dữ liệu trùng.
7. **Monitoring và runbook**, ghi số lượng, mẫu khóa, nguồn lỗi và thời hạn phục hồi.

Ý nghĩa của **missing record detection** là bảo đảm rằng record có nghĩa vụ xuất hiện thực sự có mặt ở kết quả cuối, bất kể job đã đọc bao nhiêu item hoặc báo trạng thái gì. Khi expected set được đóng băng, output được đối soát theo khóa và publish phụ thuộc vào verification, hệ thống batch có thể phát hiện mất dữ liệu âm thầm và phục hồi trước khi dữ liệu không đầy đủ lan sang downstream.
