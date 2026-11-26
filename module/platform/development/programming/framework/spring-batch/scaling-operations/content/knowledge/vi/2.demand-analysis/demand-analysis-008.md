# Đánh giá yêu cầu restart và idempotency khi mở rộng Spring Batch

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **restart cùng `JobInstance`**, chạy lại một job đã hoàn thành và tạo `JobInstance` mới.
- Xác định ranh giới commit/rollback, trạng thái checkpoint và những tác động đã phát sinh khi một chunk, worker hoặc JVM gặp lỗi.
- Đánh giá các phép ghi có **idempotency** (chạy lại không tạo thêm tác dụng ngoài ý muốn), phân biệt thao tác DB với API/message/file bên ngoài transaction.
- Xác định yêu cầu restart cho multi-threaded step, parallel steps, local/remote partitioning và remote chunking.
- Thiết kế khóa nghiệp vụ, snapshot, partition ổn định, writer chống ghi lặp, outbox và phép đối soát đầu ra.
- Lập bộ kiểm thử crash/retry/restart dựa trên bằng chứng dữ liệu thay vì chỉ nhìn trạng thái `COMPLETED` của job.

## 1. Vì sao restart và idempotency phải được đánh giá ngay từ đầu?

Trong module **SPRING_BATCH_SCALING_OPERATIONS**, mở rộng job cho dữ liệu lớn có thể dùng multi-threaded step, parallel steps, partitioning hoặc các worker chạy phân tán. Càng nhiều phần việc đồng thời, càng có nhiều điểm một phần dữ liệu đã commit trong khi phần khác đang chạy hoặc gặp lỗi. Khi đó, **restart** không đơn giản là bấm “chạy lại”; cần biết phần nào còn phải xử lý và phần đã làm có được thực hiện lại an toàn hay không.

Giả sử job nhập 8 triệu đơn hàng thành bốn partition. Sau 40 phút:

- Partition A và B hoàn thành, đã ghi kết quả vào DB.
- Partition C đã commit 120 chunk nhưng lỗi ở chunk kế tiếp.
- Partition D đang xử lý dở khi JVM bị dừng.
- Một số item đã phát lời gọi HTTP sang hệ thống khác.

Khi job được chạy lại, có ba câu hỏi riêng:

1. **Resume:** Có thể tiếp tục từ metadata/checkpoint đã lưu cho những step chưa hoàn thành không?
2. **Repeat safety:** Nếu một item hoặc chunk đã xử lý được chạy lại, output có giữ nguyên ý nghĩa nghiệp vụ không?
3. **Consistency:** Các side effect ở nhiều hệ thống có đang biểu diễn cùng một trạng thái nghiệp vụ không?

Chỉ trả lời “Spring Batch hỗ trợ restart” là chưa đủ. Spring Batch quản lý tốt trạng thái step và transaction mà framework kiểm soát; ứng dụng vẫn phải thiết kế đầu vào ổn định, phép ghi lặp lại an toàn và quy trình phục hồi khi process chết hoặc kết nối mạng bị đứt.

### Thuật ngữ cốt lõi

| Khái niệm | Nghĩa trong bài | Câu hỏi kiểm tra |
| --- | --- | --- |
| **Restartability** | Có thể tiếp tục một lần chạy logic thất bại bằng metadata/state phù hợp | Có thể tiếp tục từ checkpoint sau crash? |
| **Idempotency** | Thực hiện lại cùng một lệnh nghiệp vụ không tạo thêm hiệu ứng khác | Hai lần nhận cùng event có ghi thành hai đơn hàng không? |
| **Atomicity** | Những thay đổi trong một transaction hoặc đơn vị commit cùng thành công hoặc rollback | Ghi target và audit có cùng transaction DB không? |
| **Durability** | Dữ liệu đã commit tồn tại sau lỗi hệ thống | Bản ghi đã commit có còn sau khi worker chết? |
| **Exactly once effect** | Hiệu ứng nghiệp vụ cuối cùng chỉ xuất hiện một lần dù có retry | Có unique key/dedup/transaction bảo vệ? |
| **At least once delivery** | Một thông điệp hoặc yêu cầu có thể được giao lại | Worker có xử lý cùng key nhiều lần an toàn không? |

Không đồng nhất “đọc đúng một lần”, “message được giao đúng một lần”, “code chạy đúng một lần” và **“hiệu ứng nghiệp vụ đúng một lần”**. Trong hệ thống phân tán, code có thể chạy lặp nhưng trạng thái cuối vẫn đúng nhờ ràng buộc và idempotency.

## 2. JobInstance và JobExecution quyết định restart nào?

Spring Batch phân biệt:

- `Job`: định nghĩa công việc.
- `JobInstance`: công việc logic, xác định bởi **tên job + tập `JobParameters` có tính identifying**.
- `JobExecution`: một lần nỗ lực thực thi `JobInstance`; có thể có nhiều execution khi restart sau thất bại.
- `StepExecution`: bản ghi một lần thực thi step, bao gồm trạng thái, read/write/commit/rollback count và `ExecutionContext` để khôi phục.

~~~mermaid
flowchart TD
    J["Job: importOrdersJob"] --> I["JobInstance: businessDate=2026-11-25"]
    I --> E1["JobExecution 1: FAILED"]
    I --> E2["JobExecution 2: STARTED / restart"]
    E1 --> S1["StepExecution: worker:partition0 COMPLETED"]
    E1 --> S2["StepExecution: worker:partition1 FAILED"]
    E2 --> S3["StepExecution mới cho phần cần tiếp tục"]
~~~

Một `JobInstance` bị lỗi hoặc dừng có thể được restart **nếu job cho phép restart và trạng thái hợp lệ**. Một instance đã `COMPLETED` thường không được launch lại cùng identifying parameters; dùng identifying parameter mới tạo **công việc logic mới**, không phải restart checkpoint cũ. Hai execution của **cùng instance** cũng không được chạy đồng thời khi dùng chung `JobRepository` được cấu hình đúng.

| Yêu cầu | Cách tiếp cận | Hệ quả |
| --- | --- | --- |
| Tiếp tục nhập ngày 25 sau khi lỗi | Giữ nguyên tên job và identifying `businessDate=2026-11-25` | Restart cùng `JobInstance`, tận dụng metadata nếu hợp lệ |
| Chạy lại toàn bộ dữ liệu ngày 25 như một đợt xử lý mới | Tạo **định danh run mới có chủ đích** kèm quy tắc ghi đích | Tạo `JobInstance` mới; checkpoint cũ không tự được kế thừa |
| Sửa dữ liệu đã nhập ngày 25 | Quy trình correction/reconciliation được thiết kế riêng | Không tùy tiện thay `run.id` để vượt kiểm tra instance đã hoàn thành |
| Gọi lại một request launch đang chạy | Dùng lại identifying parameters và `JobRepository` chung | Framework kiểm tra trạng thái trùng cùng instance |

**Lỗi thiết kế thường gặp:** scheduler thêm timestamp/UUID nhận diện mỗi lần gọi, sau đó tưởng rằng retry sẽ “tiếp tục phần còn lại”. Thực chất đó có thể là một `JobInstance` mới; nếu writer không idempotent thì toàn bộ dữ liệu có thể bị ghi lại.

Một tham số để truy vết request, nhưng không thay đổi định nghĩa công việc logic, có thể khai báo **non-identifying**. Ngược lại, mọi giá trị ảnh hưởng tập dữ liệu đầu vào hoặc cách tính kết quả cần được ổn định và quản lý như một phần định danh/version của lần chạy.

## 3. Hiểu checkpoint theo ranh giới transaction

Chunk-oriented step thường xử lý một số lượng item rồi commit. Với step cấu hình `chunk(200, transactionManager)`, một chu kỳ đơn giản là:

~~~mermaid
sequenceDiagram
    participant W as Worker Step
    participant R as ItemReader
    participant P as Processor
    participant DB as Business DB
    participant M as JobRepository
    W->>DB: Bắt đầu transaction chunk
    loop Đến 200 item hoặc EOF
        W->>R: read()
        R-->>W: item
        W->>P: process(item)
    end
    W->>DB: writer ghi các item
    W->>M: Lưu state/metadata theo cơ chế Batch
    W->>DB: Commit transaction chunk
    Note over W,M: Phạm vi nguyên tử thực tế phụ thuộc transaction manager và repository
~~~

Sơ đồ thể hiện **ý tưởng checkpoint theo chunk**, không khẳng định mọi cách cấu hình `JobRepository`, reader và business DB đều thuộc **một transaction vật lý**. Khi dùng hai datasource hoặc transaction manager khác nhau, commit dữ liệu nghiệp vụ và commit metadata có thể tách rời. Cần kiểm thử tình huống crash giữa hai thời điểm này.

### Điều gì có thể tồn tại sau lỗi?

Giả sử partition C xử lý `chunk(200)`:

~~~text
chunk 1 .. 120  : COMMITTED
chunk 121       : đọc/xử lý/ghi được một phần rồi gặp lỗi -> ROLLBACK
partition C     : FAILED
partition A/B   : COMPLETED từ trước
~~~

Khi restart:

- Những chunk **đã commit** không tự rollback chỉ vì job chung thất bại.
- Chunk chưa commit có thể được **đọc/xử lý lại**.
- `ItemStream` reader có thể mở từ state đã persist, nhưng chỉ đúng khi reader tham gia lifecycle `open/update/close` và đầu vào, thứ tự, khóa state vẫn phù hợp.
- Step hoàn thành trước đó thường **được bỏ qua** ở restart theo chính sách mặc định; có thể khác nếu cấu hình `allowStartIfComplete`, flow transition hoặc metadata không tương ứng.
- Tác dụng ngoài transaction (gửi email, gọi HTTP, publish message) có thể đã phát sinh dù chunk DB bị rollback.

Vì vậy, **checkpoint giúp xác định điểm tiếp tục**, còn **idempotency giúp thực thi lại phần không chắc chắn mà không gây sai dữ liệu**. Hai cơ chế bổ sung cho nhau.

### Reader và state

Một reader giữ cursor, index hoặc offset là đối tượng **có trạng thái**. Nó cần tên checkpoint ổn định, cách đọc theo thứ tự xác định và `ItemStream` lifecycle được framework quản lý. Với partitioning, reader `@StepScope` nhận boundary từ `stepExecutionContext` để mỗi `StepExecution` có trạng thái riêng.

Nếu query đọc bằng offset trên bảng đang bị insert/delete, khôi phục offset có thể bỏ sót hoặc đọc lặp. Nếu reader không hỗ trợ resume hiệu quả, đôi khi chiến lược an toàn hơn là **đọc lại toàn bộ phần chưa đối soát** bằng writer idempotent, thay vì giả lập checkpoint không đáng tin cậy.

## 4. Đánh giá yêu cầu nghiệp vụ trước khi viết code

Trước khi quyết định dùng `saveState(true)`, retry hoặc `UPSERT`, hãy chốt các câu hỏi:

| Câu hỏi | Một đáp án minh họa | Ảnh hưởng thiết kế |
| --- | --- | --- |
| **Đơn vị xử lý logic** là gì? | `(businessDate, orderId)` | Khóa idempotency và đối soát |
| Tập đầu vào có cố định không? | Snapshot theo `businessDate` và `runVersion` | Tránh drift khi restart |
| Một record có phải xử lý đúng thứ tự không? | Theo thời gian trong cùng account | Chia partition theo account, sort ổn định |
| Chấp nhận ghi lại không? | Ghi trùng **không** chấp nhận; update cùng dữ liệu thì được | Unique constraint, upsert hoặc dedup |
| Side effect có thể rollback không? | JDBC cùng transaction: có; HTTP: không | Outbox/idempotency key/cơ chế bù |
| **RPO**: chấp nhận mất bao nhiêu công việc? | Không mất đơn hàng đã commit | Metadata bền vững, reconciliation |
| **RTO**: phục hồi trong bao lâu? | 30 phút sau khi worker lỗi | Snapshot, checkpoint, tự động retry/backfill |
| Lỗi nào được retry? | Deadlock/timeout nhất thời | Retry có giới hạn và backoff |
| Lỗi nào phải cách ly? | Record vi phạm schema | Validation, skip có chủ đích hoặc đưa vào bảng lỗi |
| Ai quyết định khi job bị kẹt? | Operator kiểm chứng worker chết trước restart | Runbook và giám sát |

**RPO** (recovery point objective) là mức mất dữ liệu/công việc được chấp nhận; **RTO** (recovery time objective) là thời gian phục hồi mục tiêu. Trong batch, cả hai cần được gắn với **kết quả nghiệp vụ**. Một JobExecution `COMPLETED` nhưng mất 300 đơn hàng không đạt yêu cầu RPO.

### Chọn semantics cho từng loại output

| Output | Yêu cầu thường gặp | Cơ chế khuyến nghị |
| --- | --- | --- |
| Bảng đích, một dòng mỗi order | Không có duplicate; rerun giữ trạng thái đúng | PK/unique `(businessDate, orderId)`, insert-if-absent hoặc upsert có điều kiện |
| Bảng tổng hợp | Không cộng hai lần khi retry | Lưu partial result theo business key rồi reduce; update có version/transaction |
| File export | Không có hai file “final” mâu thuẫn | Ghi file tạm theo run ID, xác nhận checksum, publish/rename có kiểm soát |
| HTTP payment/fulfillment | Không gọi hiệu ứng tiền bạc hai lần | Idempotency key được phía nhận hỗ trợ; đối soát trạng thái khi timeout |
| Message/event | Có thể giao lại, không làm thay đổi nghiệp vụ nhiều lần | Outbox + inbox/deduplication ở consumer |
| Email/thông báo | Hạn chế gửi hai lần | Dedupe key/sổ cái gửi; quy định hành vi khi ack không chắc chắn |

Idempotency phải được định nghĩa ở **hiệu ứng cuối**. Ví dụ lệnh `UPDATE total = total + 100` không idempotent, nhưng `UPSERT total = 100 WHERE version = 3` có thể idempotent nếu được khóa/điều kiện hóa đúng. Nếu dữ liệu thay đổi hợp lệ qua các phiên bản, phải đưa version vào logic, không dùng một key cố định để chặn mọi cập nhật tương lai.

## 5. Tính idempotent có thể chứng minh bằng ví dụ

Xét một item với business key `K=(2026-11-25, order-1001)`, payload `P`. Gọi `F(K,P)` là phép ghi.

Phép ghi idempotent nếu thực hiện cùng yêu cầu hai lần có cùng **hiệu ứng quan sát được** lên trạng thái nghiệp vụ:

~~~text
F(K, P); F(K, P)  tương đương  F(K, P)
~~~

Điều này không nói hai lời gọi phải có cùng thời gian chạy hoặc cùng số lệnh SQL, mà nói kết quả nghiệp vụ cuối cùng không đổi. Cũng phải xét trigger, audit, modified timestamp, API callback: nếu mỗi lần upsert tạo một email, thao tác **toàn hệ thống** chưa idempotent.

### Các cách ghi thường gặp

~~~sql
-- Không idempotent nếu retry cùng item:
UPDATE daily_revenue
SET total_amount = total_amount + :amount
WHERE business_date = :date;
~~~

~~~sql
-- Idempotent cho snapshot bất biến: một key chỉ insert một lần.
INSERT INTO imported_order(business_date, order_id, payload)
VALUES (:businessDate, :orderId, :payload)
ON CONFLICT (business_date, order_id) DO NOTHING;
~~~

~~~sql
-- Upsert giá trị xác định (PostgreSQL).
-- Điều kiện WHERE hạn chế update không cần thiết nếu dữ liệu không đổi.
INSERT INTO imported_order(business_date, order_id, payload)
VALUES (:businessDate, :orderId, :payload)
ON CONFLICT (business_date, order_id) DO UPDATE
SET payload = EXCLUDED.payload
WHERE imported_order.payload IS DISTINCT FROM EXCLUDED.payload;
~~~

**Lưu ý:** `DO NOTHING` với cùng key nhưng **payload khác** có thể che giấu dữ liệu bất nhất. Chỉ sử dụng khi snapshot đã bất biến và có reconciliation kiểm tra nội dung. Với dữ liệu sửa đổi hợp lệ, cần version/source offset/updated_at và quy tắc tránh bản cũ ghi đè bản mới; đừng chỉ “bật upsert” rồi coi là đã đủ an toàn.

Một cách khác cho operation mang tính tích lũy là bảng **ledger** có unique `operation_id`: ghi một operation đã được chấp nhận rồi mới áp dụng tổng hợp từ các operation duy nhất. Việc “kiểm tra đã tồn tại rồi update” phải nằm trong transaction/ràng buộc nguyên tử, tránh race giữa nhiều worker.

## 6. Ví dụ: snapshot bất biến, reader có checkpoint và writer idempotent

Tình huống: mỗi ngày job import order từ staging sang bảng đích; phần dữ liệu được chia theo khoảng ID và xử lý bằng nhiều worker. Ví dụ dùng cú pháp PostgreSQL và API phổ biến của **Spring Batch 5.x**. Giả sử `DataSource`, `JdbcTemplate`, `JobRepository`, `PlatformTransactionManager` đã được cấu hình chung và mapping business date được xác định trước.

### 6.1. Định nghĩa dữ liệu có khóa nghiệp vụ

~~~sql
CREATE TABLE staging_order (
    business_date DATE NOT NULL,
    order_id BIGINT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (business_date, order_id)
);

CREATE TABLE imported_order (
    business_date DATE NOT NULL,
    order_id BIGINT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (business_date, order_id)
);
~~~

Bảng `staging_order` là snapshot nghiệp vụ **đã đóng** trước khi manager bắt đầu chạy và không bị thay đổi trong suốt lần chạy/restart. Đối với hệ thật, nên có `snapshot_id` hoặc `run_version` đủ định danh một tập dữ liệu bất biến; chỉ `business_date` là chưa đủ nếu ngày đó được làm mới nhiều lần.

Các partition có `startId` và `endExclusive`, dùng cùng quy ước `[startId, endExclusive)`, ví dụ `[1,250001)` và `[250001,500001)`. Tên partition và boundary phải ổn định khi restart cùng `JobInstance`.

### 6.2. Reader thuộc `StepExecution`, lấy range theo partition

~~~java
import java.time.LocalDate;
import javax.sql.DataSource;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderRow(LocalDate businessDate, long orderId, String payload) {}

@Configuration
class OrderReaderConfiguration {

    @Bean
    @StepScope
    JdbcCursorItemReader<OrderRow> orderReader(
            DataSource dataSource,
            @Value("#{jobParameters['businessDate']}") String dateParam,
            @Value("#{stepExecutionContext['startId']}") Long startId,
            @Value("#{stepExecutionContext['endExclusive']}") Long endExclusive) {

        if (dateParam == null || startId == null || endExclusive == null
                || startId >= endExclusive) {
            throw new IllegalArgumentException(
                    "Missing businessDate or partition bounds");
        }

        LocalDate businessDate = LocalDate.parse(dateParam);

        return new JdbcCursorItemReaderBuilder<OrderRow>()
                .name("stableOrderReader")
                .dataSource(dataSource)
                .sql("""
                    SELECT order_id, payload
                    FROM staging_order
                    WHERE business_date = ?
                      AND order_id >= ?
                      AND order_id < ?
                    ORDER BY order_id
                    """)
                .preparedStatementSetter(ps -> {
                    ps.setObject(1, businessDate);
                    ps.setLong(2, startId);
                    ps.setLong(3, endExclusive);
                })
                .rowMapper((rs, rowNum) -> new OrderRow(
                        businessDate,
                        rs.getLong("order_id"),
                        rs.getString("payload")))
                .saveState(true)
                .build();
    }
}
~~~

`@StepScope` tạo instance reader riêng cho mỗi `StepExecution` và giải quyết late binding `stepExecutionContext`; nó **không** tự tạo transaction hay đảm bảo an toàn khi nhiều thread cùng sử dụng một reader bên trong **cùng** `StepExecution`. Việc khai báo return type cụ thể `JdbcCursorItemReader<OrderRow>` giúp Spring Batch nhận diện `ItemStream` để quản lý `open/update/close` và checkpoint.

### 6.3. Writer chống ghi trùng theo business key

~~~java
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@Bean // Đặt method trong @Configuration class.
ItemWriter<OrderRow> importedOrderWriter(JdbcTemplate jdbc) {
    return chunk -> {
        for (OrderRow order : chunk) {
            jdbc.update("""
                INSERT INTO imported_order(business_date, order_id, payload)
                VALUES (?, ?, ?)
                ON CONFLICT (business_date, order_id) DO NOTHING
                """,
                java.sql.Date.valueOf(order.businessDate()),
                order.orderId(),
                order.payload());
        }
    };
}
~~~

Writer không giữ counter/cursor mutable nên có thể được dùng trong các worker nếu mọi dependency cũng an toàn. `JdbcTemplate` dùng connection do transaction manager của worker quản lý **khi được cấu hình cùng DataSource và transaction phù hợp**. Nếu ghi bằng connection khác hoặc service ngoài, transaction chunk không bao phủ tự động.

`DO NOTHING` phù hợp với yêu cầu **“snapshot bất biến; một business key xuất hiện tối đa một lần trong đích”**. Sau job cần đối soát số khóa và payload; ở hệ thống thay đổi dữ liệu theo phiên bản, chuyển sang upsert có kiểm tra version hoặc xử lý correction riêng.

Một worker step kiểu chunk có thể dùng:

~~~java
@Bean
Step orderWorkerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        JdbcCursorItemReader<OrderRow> orderReader,
        ItemWriter<OrderRow> importedOrderWriter) {

    return new StepBuilder("orderWorkerStep", jobRepository)
            .<OrderRow, OrderRow>chunk(200, transactionManager)
            .reader(orderReader)
            .writer(importedOrderWriter)
            .build();
}
~~~

Phần import của đoạn step đến từ `org.springframework.batch.core.Step`, `org.springframework.batch.core.repository.JobRepository`, `org.springframework.batch.core.step.builder.StepBuilder` và `org.springframework.transaction.PlatformTransactionManager`. Manager có thể cấu hình `.partitioner("orderWorkerStep", partitioner).step(orderWorkerStep).gridSize(4).taskExecutor(executor)`. Partitioner chỉ tạo `ExecutionContext` cho từng range; đừng bỏ reader/connection vào context.

### 6.4. Reconciliation sau khi hoàn tất

Đếm `readCount`/`writeCount` trong metadata là chưa đủ vì reader có thể retry và writer có thể `DO NOTHING` khi key đã tồn tại. Đối soát trực tiếp dữ liệu:

~~~sql
-- Nguồn có nhưng đích thiếu (PostgreSQL).
SELECT order_id
FROM staging_order
WHERE business_date = :businessDate
EXCEPT
SELECT order_id
FROM imported_order
WHERE business_date = :businessDate;
~~~

~~~sql
-- Cùng key nhưng payload sai.
SELECT s.order_id
FROM staging_order s
JOIN imported_order t
  ON t.business_date = s.business_date
 AND t.order_id = s.order_id
WHERE s.business_date = :businessDate
  AND t.payload IS DISTINCT FROM s.payload;
~~~

Hai truy vấn phải trả về **0 dòng** nếu nghiệp vụ kỳ vọng mọi input được copy nguyên vẹn. Nếu đích có thể chứa record từ nguồn khác, cần thêm truy vấn kiểm tra output thừa với phạm vi đúng. Cũng nên đối chiếu checksum/count tổng theo partition để phát hiện sai ở ranh giới.

## 7. Các kiểu lỗi phải có kịch bản phục hồi riêng

| Điểm lỗi | Thay đổi nào có thể đã xảy ra? | Hành vi cần thiết |
| --- | --- | --- |
| Trước khi chunk bắt đầu | Chưa có write của chunk | Chạy chunk bình thường |
| Đang đọc/xử lý, trước commit | Một phần work ở memory; các external calls có thể đã chạy | Rollback transaction nội bộ, retry có giới hạn; dedup external effect |
| Writer thực hiện DB update rồi ném exception trước commit | DB write trong cùng transaction thường rollback | Reader quay về checkpoint trước commit; writer phải an toàn nếu có retry |
| DB commit thành công nhưng cập nhật trạng thái/ack gặp lỗi | Kết quả đã bền vững nhưng caller có thể nghĩ chưa thành công | Replay có thể xảy ra; unique key, outbox/inbox và reconciliation |
| Một partition lỗi sau khi partition khác `COMPLETED` | Dữ liệu partition khác đã commit | Restart phần cần thiết, không có rollback toàn job |
| Worker bị mất kết nối mạng | Job/manager có thể không biết worker đã commit hay chưa | Kiểm tra metadata, idempotency key và trạng thái nguồn đích trước khi nhận lại |
| JVM chết khi `JobExecution` `STARTED` | Metadata có thể còn `STARTED` dù process đã chết | Runbook xác minh không còn worker ghi, sau đó phục hồi trạng thái theo quy trình |

Với retry/skip, không có câu trả lời “mọi exception đều retry”. Lỗi deadlock/timeout có thể tạm thời, còn schema vi phạm hoặc khóa nghiệp vụ không hợp lệ là lỗi cần xử lý dữ liệu. Số lần retry quá lớn có thể khuếch đại tải DB/API và khiến SLA bị trễ.

### Khi nào không nên skip?

Nếu một đơn hàng phải được xử lý đủ để đối soát tài chính, việc `skip` sau nhiều lỗi rồi vẫn hoàn thành job có thể làm mất dữ liệu nghiệp vụ. Khi đó nên lưu record lỗi vào kênh riêng, cảnh báo và chặn bước publish đến khi số lượng thiếu được xử lý. `SkipPolicy` và trạng thái `COMPLETED` chỉ là cơ chế kỹ thuật; kết quả nghiệp vụ phải được định nghĩa riêng.

## 8. Phân tán và song song làm idempotency khó hơn ra sao?

### 8.1. Local partitioning

Mỗi partition có `StepExecution` riêng, ranh giới từ `ExecutionContext` và các chunk commit riêng. Nếu A hoàn thành, B lỗi, transaction đã commit của A không tự rollback. Khi restart, A thường được bỏ qua nếu hoàn tất; B được phục hồi theo metadata.

**Yêu cầu:** tên partition và tập dữ liệu tái lập, reader riêng theo step, writer có unique business key, đúng transaction và kiểm thử rollback ở từng worker.

### 8.2. Parallel steps

Hai flow độc lập có transaction và trạng thái riêng. Khi hai flow được chạy bằng `split`, bước sau join chỉ chạy theo transition thích hợp sau khi các nhánh kết thúc; join **không** biến chúng thành một transaction toàn cục.

**Yêu cầu:** các flow không dựa trên side effect chưa ổn định của flow khác; dữ liệu chung cần merge/reconciliation theo contract rõ ràng. Restart phải xét từng step đã hoàn thành và bước tổng hợp chưa chạy.

### 8.3. Multi-threaded step

Độ an toàn phụ thuộc cơ chế multi-threaded step của **phiên bản Spring Batch**. Không mặc định mọi reader/writer thread-safe, hay transaction trong thread điều phối tự truyền sang worker. Tham khảo tài liệu đúng release; đặc biệt cần kiểm tra vị trí chạy processor, reader/writer và transaction boundary.

**Yêu cầu:** state mutable, checkpoint, reader ordering, writer và transaction được kiểm chứng dưới concurrency thực. `@StepScope` chỉ cô lập **theo `StepExecution`**, không tạo một reader cho mỗi thread nếu nhiều thread dùng chung execution.

### 8.4. Remote partitioning và remote chunking

Khi manager gửi công việc qua mạng, một yêu cầu có thể:

1. Được worker thực hiện và commit.
2. Bị mất acknowledgement do timeout hoặc crash.
3. Được manager/broker gửi lại.
4. Tới một worker khác, hoặc tới chính worker cũ.

~~~mermaid
sequenceDiagram
    participant M as Manager
    participant Q as Broker
    participant W as Worker
    participant D as Business DB
    M->>Q: Gửi workKey=K
    Q->>W: Giao K
    W->>D: Commit hiệu ứng với key K
    Note over W,M: ACK thất lạc / timeout
    Q->>W: Giao lại K
    W->>D: Thử xử lý K lần nữa
    D-->>W: Dedupe/UPSERT, không tạo hiệu ứng trùng
    W-->>Q: ACK kết quả
~~~

Không dựa vào số lần message được giao để khẳng định hiệu ứng đúng một lần. Đặt idempotency key ổn định ở **hệ nhận cuối**, duy trì retry/visibility timeout phù hợp và đối soát trạng thái khi ack không rõ. Nếu remote worker vẫn còn sống khi lease hết hạn, có thể cần **fencing token** để tránh worker mất quyền tiếp tục ghi.

## 9. Tác dụng ngoài DB: outbox, inbox và key idempotency

Giả sử một chunk cần vừa lưu đơn hàng vừa gửi sự kiện `OrderImported` sang broker.

Mẫu rủi ro:

~~~java
// Anti-pattern khi cần atomicity giữa DB và message.
jdbc.update("INSERT INTO imported_order ...");
messageClient.publish("OrderImported", order); // Broker ngoài DB transaction
// Nếu chunk rollback sau publish, message vẫn có thể đã đến consumer.
~~~

Không thể giả định transaction JDBC tự rollback một message đã tới broker hoặc HTTP request đã thành công.

### 9.1. Transactional outbox

Trong **cùng transaction DB**, lưu cả bản ghi nghiệp vụ và bản ghi outbox:

~~~sql
CREATE TABLE order_outbox (
    event_key VARCHAR(150) PRIMARY KEY,
    business_date DATE NOT NULL,
    order_id BIGINT NOT NULL,
    event_type VARCHAR(80) NOT NULL,
    payload TEXT NOT NULL,
    published_at TIMESTAMP NULL
);
~~~

~~~sql
-- Chạy trong cùng transaction với ghi imported_order.
INSERT INTO order_outbox(
    event_key, business_date, order_id, event_type, payload
)
VALUES (
    :eventKey, :businessDate, :orderId, 'OrderImported', :payload
)
ON CONFLICT (event_key) DO NOTHING;
~~~

`eventKey` nên phát sinh **deterministic**, ví dụ `OrderImported:2026-11-25:1001:v1`; không dùng UUID mới mỗi lần retry. Một tiến trình publisher riêng đọc outbox chưa gửi, phát message, đánh dấu đã publish. Nếu publisher crash sau publish nhưng trước đánh dấu, message có thể phát lại; **consumer phải có inbox/deduplication** theo `event_key`. Outbox giải quyết cửa sổ commit DB–publish, nhưng không tự bảo đảm broker không giao lặp.

### 9.2. HTTP/API có hiệu ứng bên ngoài

Khi gọi API thanh toán hoặc fulfillment, mỗi request cần **idempotency key ổn định** và phía server hỗ trợ semantics phù hợp. Nếu client timeout sau khi server đã xử lý, không thể kết luận request thất bại; cần query status theo key hoặc gửi lại cùng key theo contract API. Nếu API không có cơ chế này, phải thiết kế ledger/reconciliation hoặc compensating action rõ ràng.

### 9.3. File export

Nếu job ghi thẳng file cuối rồi chết giữa chừng, lần restart có thể ghi nối sai hoặc ghi trùng. Một phương án là tạo file theo `(businessDate, runVersion)` vào đường dẫn tạm, ghi checksum và count, sau đó publish/rename theo điều kiện nguyên tử của **filesystem/object storage thực tế**. Không giả định thao tác rename/upload nào cũng atomic trên mọi nền tảng; cần xác nhận contract của hệ lưu trữ.

## 10. Restart có thể sai dù dữ liệu không bị duplicate

Một số tình huống thường bị bỏ qua:

- **Bỏ sót dữ liệu:** offset checkpoint được phục hồi trên bảng nguồn đã chèn/xóa record, khiến reader nhảy qua item.
- **Ghi sai phiên bản:** upsert không có điều kiện cho phép event cũ tới muộn ghi đè dữ liệu mới.
- **Sai thứ tự:** các giao dịch cùng tài khoản được xử lý bởi nhiều worker, dẫn tới kết quả số dư phụ thuộc timing.
- **Mất event:** writer đã ghi bảng chính nhưng event không được publish vì process chết trước lệnh gửi.
- **Chờ vô hạn:** JobExecution kẹt `STARTED` sau crash, scheduler liên tục từ chối restart.
- **Chia lại partition sai:** số partition/boundary thay đổi giữa các attempt, nhưng tên/checkpoint vẫn dùng state cũ.
- **Side effect lặp:** retry cùng chunk khiến một email được gửi lần hai hoặc API tăng số dư hai lần.
- **Cập nhật trạng thái không đúng:** chương trình bắt exception rồi trả thành công; Batch commit chunk dù nghiệp vụ chưa được xử lý.

Như vậy, không có duplicate trong bảng chính **chưa đủ để kết luận restart thành công**. Cần kiểm tra **đúng tập khóa, đúng payload/version, đúng ordering và đúng các side effect**.

## 11. Quy trình đánh giá trước khi chọn kiến trúc

### Bước 1 — Xác định “một lần chạy logic”

Ghi rõ tên job, identifying parameters, business date, snapshot ID, run version và khi nào một run được phép tạo mới. Phân biệt retry/restart với correction/rehydration.

### Bước 2 — Vẽ transaction boundary và checkpoint

Đặt ranh giới chunk, nguồn transaction manager, reader `ItemStream`, nơi update `ExecutionContext`, bảng metadata, các hệ thống ngoài DB và những thao tác có thể commit độc lập. Ghi nhận độ lớn công việc phải chạy lại sau một lần rollback.

### Bước 3 — Liệt kê tất cả side effect

Không chỉ kiểm tra writer chính: audit row, aggregate, file, email, queue, HTTP, cache invalidation và webhook đều có thể được gọi lại khi retry.

### Bước 4 — Gắn key dedup/version cho mỗi hiệu ứng

Chọn business key và phạm vi bảo vệ phù hợp:

| Hiệu ứng | Key khả thi | Điều phải kiểm tra |
| --- | --- | --- |
| Copy một đơn hàng | `(snapshotId, orderId)` | Snapshot không thay đổi khi restart |
| Tạo event từ order | `(orderId, eventType, sourceVersion)` | Không phát lại hiệu ứng với cùng version |
| Ghi tổng theo ngày | `(businessDate, aggregateVersion)` | Không cộng delta hai lần |
| Gọi API fulfillment | `(orderId, fulfillmentAction, version)` | Đầu nhận thật sự bảo đảm idempotency |
| Ghi báo cáo | `(reportDate, reportVersion)` | Không publish hai bản final mâu thuẫn |

### Bước 5 — Thiết kế ranh giới partition và concurrency

Mọi phần việc phải bao phủ đúng nguồn, không overlap ngoài chủ ý, có tên và boundary tái lập. Kiểm tra trạng thái dùng chung, lock và thứ tự. Với remote execution, xác định ai là owner và cách nhận lại công việc nếu timeout.

### Bước 6 — Định nghĩa chính sách lỗi

Xác định exception được retry, số lần, backoff, lỗi dữ liệu nào được skip, khi nào fail toàn job, cơ chế dừng worker, điều kiện bù hoặc chạy lại. Đánh giá RTO/RPO và nhu cầu tài nguyên khi nhiều partition retry đồng thời.

### Bước 7 — Định nghĩa phép đối soát

Không dùng duy nhất `BatchStatus.COMPLETED`. Cần xác nhận toàn bộ business key cần thiết đã có ở đích, checksum/version đúng, không có side effect trùng và mọi event bắt buộc được publish/consume.

### Bước 8 — Chạy fault injection trên dữ liệu đại diện

Cố tình làm hỏng job ở các thời điểm trước/giữa/sau commit, khi đang gửi API, khi mất ack và khi một partition khác đã hoàn tất. Sau mỗi lần restart, so sánh kết quả với chạy không lỗi.

## 12. Bảng kiểm thử restart và idempotency

| Kịch bản | Cách kích hoạt trong staging | Kỳ vọng |
| --- | --- | --- |
| Lỗi processor trước write | Ném exception cho item xác định | Chunk rollback/fail theo policy; không mất business key |
| Lỗi JDBC trước commit | Ném exception sau một số `jdbc.update` trong chunk | Thay đổi cùng transaction rollback; retry không sinh duplicate |
| Crash sau khi vài chunk commit | Dừng process/worker có kiểm soát | Commit cũ tồn tại, checkpoint và writer giúp tiếp tục đúng |
| Một partition fail, partition khác complete | Làm lỗi một worker | Chỉ phần cần restart theo metadata; không rollback phần đã commit |
| Trùng input message | Giao cùng `event_key` hai lần | Consumer ghi một hiệu ứng nghiệp vụ |
| Broker ack thất lạc | Publish thành công rồi mô phỏng timeout | Publisher gửi lại an toàn; inbox dedup |
| API xử lý xong nhưng client timeout | Mock response mất sau commit server | Cùng idempotency key không tạo operation thứ hai |
| Source bị thay đổi trước restart | Thử chèn/xóa item sau checkpoint | Cảnh báo hoặc snapshot chặn, không silently skip |
| Đổi `gridSize` lúc restart | Thử sửa boundary có chủ đích | Quy trình phát hiện không tương thích hoặc dùng mapping đã persist |
| Job metadata `STARTED` nhưng process chết | Mô phỏng ungraceful shutdown | Operator xác minh worker không còn ghi trước xử lý recovery |
| Retry storm khi DB quá tải | Tăng deadlock/timeout có kiểm soát | Backoff/limit, job không làm DB sụp thêm |
| Writer gặp cùng key khác payload | Tạo dữ liệu source version mâu thuẫn | Phát hiện conflict, không im lặng coi là thành công |

Kết quả cần được kiểm định trên cả **metadata** (`JobExecution`, `StepExecution`, `ExecutionContext`) và **dữ liệu nghiệp vụ**. Với hệ phân tán, bổ sung tracing bằng `businessKey`/`eventKey` để liên kết các lần giao lại.

## 13. Chi phí restart: trade-off với thông lượng và tài nguyên

Số lượng chunk nhỏ giúp giới hạn công việc phải làm lại khi lỗi, nhưng tăng commit và metadata overhead. Chunk lớn giảm overhead trên mỗi item nhưng giữ transaction lâu, có thể tăng RAM, lock contention và khối lượng rollback.

Một mô hình đơn giản: nếu commit mỗi `C` item, công việc phải chạy lại sau một lỗi ngẫu nhiên trong chunk (nếu không có side effect ngoài transaction và reader resume đúng) có thể lên đến khoảng `C` item của chunk chưa commit. Không dùng `C/2` làm bảo đảm nghiệp vụ; đó chỉ là giá trị trung bình dưới giả định vị trí lỗi phân bố đều.

| Lựa chọn | Lợi ích | Rủi ro khi restart |
| --- | --- | --- |
| Chunk nhỏ, checkpoint dày | Ít item trong chunk chưa commit | Nhiều commit và metadata; throughput có thể thấp |
| Chunk lớn | Giảm overhead theo item | Rollback/làm lại nhiều item hơn, transaction dài |
| Partition nhỏ và nhiều | Phân bổ tải, hạn chế retry theo miền | Metadata/connection/coordination tăng |
| Partition lớn và ít | Ít overhead | Một partition lỗi kéo dài thời gian phục hồi, skew |
| `saveState(true)` | Resume nhanh nếu input ổn định | Checkpoint sai nếu dữ liệu thay đổi hoặc state không được quản lý |
| Chạy lại từ đầu + writer idempotent | Dễ suy luận nếu nguồn nhỏ/bất biến | Chi phí đọc/xử lý lại có thể quá cao với dữ liệu lớn |

Trong remote partitioning, chi phí phục hồi còn gồm thời gian nhận biết worker chết, lease/visibility timeout, khởi tạo worker mới và chuyển state. Đặt timeout quá ngắn có thể tạo **hai worker đồng thời xử lý cùng key** khi worker cũ vẫn sống; cần cơ chế ngăn side effect trùng hoặc fencing.

Đừng tăng concurrency chỉ để bù lỗi restart: nhiều worker có thể gây thêm deadlock/retry và làm giảm throughput bền vững. Theo dõi rollback count, retry rate, p95/p99 chunk duration, thời gian restart, số job mắc kẹt và số duplicate bị unique constraint chặn.

## 14. Quy trình vận hành khi job bị lỗi

Một runbook thực tế nên có thứ tự:

1. **Xác nhận phạm vi lỗi:** job, `JobInstance`, execution ID, step/partition, batch status, thời điểm commit cuối, worker đang hoạt động.
2. **Kiểm tra ownership:** đảm bảo process, pod và remote worker cũ không còn ghi vào cùng business key trước khi cho phép execution mới.
3. **Đánh giá dữ liệu đã commit:** từ bảng đích, ledger, outbox và các dịch vụ ngoài DB; không suy luận chỉ từ log.
4. **Xác nhận điều kiện restart:** snapshot còn tồn tại và bất biến, partition mapping còn đúng, reader state có thể sử dụng, job cho phép restart.
5. **Chọn hành động:** restart cùng instance khi phù hợp; correction/rebuild thành instance mới khi cần tái tính đầy đủ theo chính sách riêng.
6. **Theo dõi đến khi hoàn tất:** chunk/partition đã resume, số lỗi retry, backlog outbox, thời gian so với SLA.
7. **Đối soát cuối:** đủ business keys và phiên bản, không thiếu/trùng side effect, publish event đúng và kết quả được phép công bố.
8. **Ghi nhận nguyên nhân:** cập nhật timeout, index, retry policy, idempotency key hoặc checkpoint nếu lỗi lặp.

Không sửa trực tiếp `BATCH_JOB_EXECUTION` từ `STARTED` sang `FAILED`, xóa metadata để “mở khóa” hoặc thay `run.id` để ép chạy lại khi chưa điều tra worker cũ. Các thao tác đó có thể tạo execution trùng và phá trạng thái restart; dùng quy trình vận hành phù hợp với version và repository thực tế.

## 15. Bài tập tình huống

Một job xử lý ba partition từ snapshot đã đóng, mỗi partition có 1.000 đơn hàng, chunk size 100:

- Partition A: hoàn thành 1.000 đơn hàng, status `COMPLETED`.
- Partition B: đã commit 600 đơn hàng, lỗi trước commit chunk tiếp theo.
- Partition C: đã commit 500 đơn hàng; worker gửi 30 HTTP request sang đối tác rồi chết, chưa biết đối tác đã nhận request nào.
- Output DB dùng unique `(businessDate, orderId)`. API đối tác cho phép truyền `Idempotency-Key`.

**Câu hỏi:**

1. Vì sao không thể rollback cả 1.000 đơn hàng của A khi B lỗi?
2. Nếu restart cùng identifying parameters, dự kiến A, B và C được xử lý theo metadata ra sao?
3. Có nên tạo `Idempotency-Key` mới bằng UUID trong mỗi lần retry request C không?
4. Unique key ở DB đã đủ chứng minh không có 30 HTTP side effect trùng chưa?
5. Nếu snapshot bị sửa trước restart, điều gì có thể sai ngay cả khi unique key chặn duplicate?

**Gợi ý phân tích:** A đã commit những transaction độc lập; restart thường bỏ qua step hoàn tất và tiếp tục những step chưa xong theo checkpoint phù hợp. HTTP request phải dùng **cùng key xác định** qua retry và đối soát status đối tác; unique key DB không bảo vệ API. Snapshot thay đổi có thể dẫn đến bỏ sót/sai payload, nên phải đóng băng input hoặc có version/watermark được quản lý.

## Tài liệu tham khảo

- [Spring Batch Reference – Job Restart](https://docs.spring.io/spring-batch/reference/job.html): `JobInstance`, `JobExecution` và semantics restart.
- [Spring Batch Reference – Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): partitioning, worker và các cách song song hóa.
- [Spring Batch Reference – Item Readers and Writers](https://docs.spring.io/spring-batch/reference/readers-and-writers/index.html): readers, writers và `ItemStream`.
- [Spring Batch Reference – Batch Processing and Transactions](https://docs.spring.io/spring-batch/reference/transaction-appendix.html): ranh giới commit, rollback và retry.
- [Spring Framework – Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): transaction manager và các mức propagation.

## Ghi nhớ

**Restartability xác định khả năng tiếp tục một `JobInstance` từ metadata/checkpoint; idempotency bảo đảm phần việc bị thực hiện lại không tạo kết quả nghiệp vụ sai.** Hai yêu cầu phải được đánh giá cùng nhau trước khi scale Spring Batch. Với multi-threaded step, parallel steps, partitioning hoặc worker phân tán, hãy cố định snapshot và business key, hiểu transaction nào thật sự commit, thiết kế writer/outbox/API chống lặp, kiểm thử crash tại ranh giới commit và đối soát toàn bộ output trước khi tuyên bố job đã phục hồi thành công.
