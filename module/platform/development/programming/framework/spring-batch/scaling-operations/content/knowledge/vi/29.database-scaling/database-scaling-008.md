# Isolation level cho workload song song trong Spring Batch

> **Chương:** Database scaling
>
> **Module:** SPRING_BATCH_SCALING_OPERATIONS — Mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và mô hình xử lý phân tán. Bài học phân tích mức cô lập giao dịch khi nhiều worker cùng đọc/ghi database, cách cân bằng **tính đúng, contention, throughput, retry/restart và vận hành** theo tài nguyên thực tế.

Khi chuyển từ một step tuần tự sang 8–32 worker chạy đồng thời, lỗi không chỉ đến từ Java thread safety. Nhiều transaction database có thể cùng quan sát và thay đổi bản ghi: item bị đọc hai lần, kết quả đếm không nhất quán, một worker ghi đè worker khác, hoặc job chậm hẳn vì lock. **Isolation level** là một phần quan trọng của giải pháp, nhưng **không có một mức cô lập nào tự thay thế partition plan, ranh giới transaction, unique constraint, checkpoint và idempotency**.

## Mục tiêu học tập

Hoàn thành bài này, bạn có thể:

1. Giải thích `READ_UNCOMMITTED`, `READ_COMMITTED`, `REPEATABLE_READ` và `SERIALIZABLE` theo các hiện tượng dirty read, non-repeatable read, phantom và các bất thường cập nhật.
2. Phân biệt **isolation của transaction chunk** với **isolation của JobRepository khi tạo JobExecution** và với **snapshot toàn bộ input job**.
3. Nhận ra lost update, write skew, duplicate claim và input drift trong multi-threaded step, parallel steps, local/remote partitioning.
4. Áp dụng optimistic locking, unique business key, row claim và `FOR UPDATE SKIP LOCKED` đúng bối cảnh; hiểu giới hạn của chúng.
5. Cấu hình mức cô lập cho Spring Batch step, xây kế hoạch đọc snapshot/partition ổn định và thiết kế retry khi transaction bị deadlock hoặc serialization failure.
6. Đo throughput, lock wait, connection pool, rollback và kiểm thử cạnh tranh trên database thật trước khi tăng số worker.

## 1. Vì sao tăng số worker làm vấn đề isolation xuất hiện?

Giả sử bảng `orders` có bốn triệu đơn hàng. Job đọc dữ liệu, tính phí và ghi kết quả:

~~~text
Trước: 1 worker
  đọc 1..4.000.000 -> xử lý -> ghi

Sau: 8 worker
  W0 đọc [1, 500001)
  W1 đọc [500001, 1000001)
  ...
  W7 đọc [3500001, 4000001)

Đồng thời, API vận hành vẫn thêm/sửa orders
và một job khác cập nhật trạng thái thanh toán.
~~~

Vấn đề không dừng ở việc chia range không overlap. Trong lúc W0 đang đọc:

- Transaction khác đổi `status` từ `NEW` sang `CANCELLED`.
- Một worker khác cùng claim `order_id` do query sai hoặc message được giao lại.
- Một chunk `COMMIT` trước, chunk khác `ROLLBACK` rồi retry.
- Trang truy vấn tiếp theo nhìn thấy dữ liệu mới nếu nguồn không cố định.
- Writer và `JobRepository` dùng hai datasource hoặc transaction manager khác nhau.

Tăng `gridSize`/thread pool có thể làm **nhiều transaction cạnh tranh cùng các hàng/index**, khiến throughput giảm hoặc kết quả sai dù mã Java không có race trên biến bộ nhớ.

~~~mermaid
flowchart TB
    M["Batch manager"] --> A["Worker A / chunk TX A"]
    M --> B["Worker B / chunk TX B"]
    M --> C["Worker C / chunk TX C"]
    A --> DB[("Business database<br/>MVCC / locks / indexes")]
    B --> DB
    C --> DB
    API["API/OLTP transactions"] --> DB
    DB --> J["Tính nhất quán nhìn thấy<br/>và contention cần kiểm soát"]
~~~

**Phân biệt:** DB isolation kiểm soát **tương tác giữa các transaction**. Nó không tự sửa lỗi partitioner chia trùng range, reader không thread-safe hay writer gửi HTTP không có idempotency.

## 2. Isolation level là hợp đồng giữa các transaction

Một transaction T1 có thể đọc cùng hàng nhiều lần, đồng thời T2 cập nhật bảng. **Isolation level** quyết định T1 được nhìn thấy thay đổi của T2 như thế nào và những xung đột nào database phải ngăn hoặc phát hiện.

Các tên mức cô lập trong JDBC/Spring:

| SQL / JDBC | Ý tưởng chính | Đánh đổi thường gặp |
| --- | --- | --- |
| `READ_UNCOMMITTED` | Cho phép mức cô lập rất thấp; theo chuẩn có thể thấy thay đổi chưa commit | Rủi ro dirty read; **không phải DB nào cũng hỗ trợ đúng nghĩa** |
| `READ_COMMITTED` | Chỉ đọc dữ liệu đã commit; một câu SELECT mới có thể thấy snapshot mới | Throughput thường tốt; không bảo đảm snapshot ổn định qua nhiều lệnh |
| `REPEATABLE_READ` | Trong transaction, đọc lại một hàng ổn định theo bảo đảm của DB | Có thể giữ snapshot/locks lâu; anomalies còn lại tùy engine |
| `SERIALIZABLE` | Kết quả các transaction tương đương một thứ tự tuần tự hợp lệ | Nhiều xung đột phải chờ hoặc abort/retry; chi phí cao hơn ở workload tranh chấp |

**Tên mức cô lập giống nhau không bảo đảm implementation giống nhau giữa các database.** Ví dụ PostgreSQL dùng MVCC và coi yêu cầu `READ_UNCOMMITTED` như `READ_COMMITTED`; PostgreSQL `REPEATABLE_READ` có snapshot ổn định trong transaction và ngăn nhiều phantom theo mô hình của nó. MySQL InnoDB kết hợp MVCC và locking/next-key locks; SQL Server có tùy chọn row-versioning như `READ_COMMITTED_SNAPSHOT`. Cần kiểm tra **database/version/configuration thật** thay vì suy luận từ tên JDBC.

### Các hiện tượng cần biết

| Hiện tượng | Mô tả | Ví dụ ảnh hưởng Batch |
| --- | --- | --- |
| **Dirty read** | T1 đọc thay đổi của T2 trước khi T2 commit | Ghi kết quả từ order sau đó bị rollback |
| **Non-repeatable read** | T1 đọc lại cùng hàng và thấy giá trị khác đã commit | Validator và writer đánh giá hai phiên bản khác nhau |
| **Phantom** | T1 chạy lại cùng predicate, thấy tập hàng khác | Đếm `NEW` orders ở đầu và cuối transaction không khớp |
| **Lost update** | Hai luồng cập nhật dựa trên cùng giá trị cũ và một kết quả bị ghi đè | Hai worker cộng dồn total bằng read–modify–write không có guard |
| **Write skew** | Hai transaction đọc cùng điều kiện tổng hợp rồi cập nhật hai hàng khác nhau, làm vỡ invariant | Hai worker cùng thấy “chưa có ai trực” và cùng đổi người trực thành nghỉ |
| **Serialization failure** | DB từ chối commit một transaction để giữ tính serializable | Chunk phải rollback và retry an toàn |

Chú ý: Bảng các “phenomena” theo chuẩn SQL **không mô tả đầy đủ** lost update, write skew và mọi khác biệt MVCC/locking giữa nhà cung cấp. Không mặc định `REPEATABLE_READ` loại bỏ mọi race nghiệp vụ.

## 3. Ví dụ READ COMMITTED: cùng transaction nhìn hai phiên bản

Giả sử sử dụng PostgreSQL `READ COMMITTED`; transaction A đang kiểm tra đơn hàng `42`, còn transaction B cập nhật nó:

~~~sql
-- Session A
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;
SELECT status FROM orders WHERE id = 42;
-- Kết quả: NEW

-- Session B, chạy đồng thời
BEGIN;
UPDATE orders SET status = 'CANCELLED' WHERE id = 42;
COMMIT;

-- Session A
SELECT status FROM orders WHERE id = 42;
-- Bây giờ có thể thấy CANCELLED
COMMIT;
~~~

Đây là **non-repeatable read**. Không có dirty read: Session A không thấy thay đổi **chưa commit** của B. Nhưng việc đọc đã commit không đồng nghĩa đọc **một snapshot cố định** cho toàn transaction.

### Trong Spring Batch còn có ranh giới chunk

Với `chunk(200, transactionManager)`:

~~~text
Chunk 1 transaction: read/process/write 200 item -> COMMIT
Chunk 2 transaction: read/process/write 200 item -> COMMIT
Chunk 3 transaction: read/process/write 200 item -> COMMIT
...
~~~

Ngay cả khi đặt mức `REPEATABLE_READ` cho **mỗi transaction chunk**, chunk 2 và chunk 3 vẫn là **các transaction mới**, có thể thấy các dữ liệu khác với chunk 1. Vì vậy:

> **Isolation ổn định trong một chunk không đồng nghĩa snapshot ổn định của toàn job.**

Nếu đầu vào thay đổi giữa các chunk/partition, phải dùng input snapshot bất biến, manifest, watermark hoặc business versioning. Tăng isolation của từng chunk đơn lẻ **không tạo transaction kéo dài qua toàn bộ job**.

## 4. Lost update: isolation không thay thế optimistic locking

Giả sử hai worker cùng đọc `processed_count=100` rồi đều cộng 1 trong Java:

~~~text
Worker A: SELECT processed_count -> 100
Worker B: SELECT processed_count -> 100
Worker A: UPDATE ... SET processed_count=101
Worker B: UPDATE ... SET processed_count=101

Kết quả 101, nhưng đã có hai sự kiện thành công.
~~~

Đừng coi `READ_COMMITTED` tự bảo vệ được mẫu **read → compute in memory → UPDATE giá trị tuyệt đối**.

### Cách 1: atomic SQL update

~~~sql
UPDATE batch_metrics
SET processed_count = processed_count + 1
WHERE metric_id = :id;
~~~

Một câu SQL cập nhật theo giá trị hiện tại trên hàng được lock phù hợp có thể tránh lost update do hai transaction cùng ghi `101`. Nhưng **nếu cùng message/operation được xử lý lại**, câu UPDATE vẫn có thể tăng **hai lần**: atomicity không thay thế idempotency theo business event.

### Cách 2: optimistic version check

~~~sql
UPDATE orders
SET status = 'PROCESSING',
    version = version + 1
WHERE id = :orderId
  AND status = 'NEW'
  AND version = :expectedVersion;
~~~

Ứng dụng phải kiểm tra **số hàng update**:

- `1`: đã claim/chuyển trạng thái theo version dự kiến.
- `0`: row đã bị thay đổi, không tồn tại hoặc không còn `NEW`; **đọc lại và phân loại**, không tự coi là thành công.

Optimistic locking hợp với workload có xung đột thấp. Khi contention cao, retry lặp nhiều có thể làm giảm throughput; cần đo conflict rate. Khi operation gây side effect ngoài DB, không retry với key mới mà không reconcile.

### Cách 3: unique business operation key

Nếu job xử lý giao dịch tài chính, unique constraint trên `(tenant_id, operation_id)` có thể bảo vệ khỏi **duplicate commit** dù retry/restart hoặc hai workers cùng đọc:

~~~sql
CREATE TABLE operation_result (
    tenant_id VARCHAR(80) NOT NULL,
    operation_id VARCHAR(160) NOT NULL,
    payload_hash VARCHAR(128) NOT NULL,
    result_status VARCHAR(30) NOT NULL,
    PRIMARY KEY (tenant_id, operation_id)
);
~~~

Khi nhận key đã tồn tại, phải kiểm tra payload và trạng thái; không `ON CONFLICT DO NOTHING` mù nếu cùng key có amount khác. Unique key là hàng rào **nghiệp vụ**, khác với mức cô lập transaction.

## 5. Write skew: snapshot không luôn bảo vệ invariant tổng hợp

Tình huống có hai bác sĩ A và B đang trực, chính sách yêu cầu **ít nhất một người trực**. Hai transaction cùng nhìn thấy A và B đang trực; mỗi transaction cho một người nghỉ.

~~~text
T1 (worker 1): SELECT COUNT(on_call)=2 → đổi A thành OFF
T2 (worker 2): SELECT COUNT(on_call)=2 → đổi B thành OFF

T1 và T2 cập nhật hai rows khác nhau,
nhưng sau cùng số bác sĩ trực có thể bằng 0.
~~~

Đây là ví dụ điển hình của **write skew** dưới một số dạng snapshot isolation. Chỉ lock hàng mình sắp sửa chưa chắc đã bảo vệ điều kiện tổng hợp.

Trong Batch, bất biến tương tự có thể là:

- Tổng số đơn đang claim của một account không vượt quota.
- Một invoice không được tạo nhiều khoản capture xung đột.
- Một tenant phải có đúng một active batch owner cho cùng kỳ xử lý.
- Số lượng tồn kho luôn đủ khi nhiều worker cùng trừ kho.

Giải pháp tùy nghiệp vụ:

1. **`SERIALIZABLE`** cho transaction cập nhật bất biến, với retry serialization failure có kiểm soát.
2. **Lock một hàng đại diện cho invariant** hoặc claim/lease có atomic guard.
3. **Constraint tại DB** khi bất biến có thể biểu diễn bằng unique/check/exclusion constraint.
4. **Optimistic versioning** trên một aggregate root mà mọi worker cùng phải cập nhật.

Không dùng `SELECT COUNT(*)` rồi kiểm tra trong Java như bằng chứng an toàn chỉ vì đang dùng `REPEATABLE_READ`.

## 6. SERIALIZABLE không có nghĩa “không bao giờ lỗi”

`SERIALIZABLE` buộc kết quả tương đương một thứ tự tuần tự hợp lệ cho các transaction, nhưng database có thể thực hiện điều đó bằng **abort/retry** chứ không phải bằng cách xếp hàng chờ tất cả operations.

Ví dụ PostgreSQL có thể trả `SQLSTATE 40001` cho serialization failure. Transaction phải được **rollback toàn bộ**, rồi thử lại thao tác/đơn vị công việc phù hợp từ dữ liệu đầu vào và trạng thái nhất quán.

### Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
| --- | --- |
| `SERIALIZABLE` sẽ luôn nhanh và đúng nên dùng cho toàn job | Có thể tăng conflict, lock wait và abort; throughput có thể giảm |
| Bật serializable rồi khỏi cần unique business key | Retry sau crash/JobExecution mới vẫn có thể ghi operation trùng nếu business key không bảo vệ |
| Serializable trên mỗi chunk tạo một snapshot toàn job | Không; các chunk là các transaction khác nhau |
| Serialization failure là lỗi dữ liệu cần skip | Không; đó là tín hiệu transaction phải retry/fail, **không loại item hợp lệ** |
| Serializable bảo vệ HTTP/API ngoài DB | Không; HTTP side effect không nằm trong transaction DB |
| Retry serialization failure lúc nào cũng an toàn | Chỉ khi thao tác transaction và mọi side effects đi kèm có thể replay/idempotent |

**Nguyên tắc vận hành:** Dùng mức cô lập cao khi **bất biến cụ thể cần nó**, rồi benchmark dưới concurrency thực. Nếu xung đột là do nhiều worker cùng một hot key, giảm concurrency/phân vùng theo key đôi khi hiệu quả hơn tăng isolation toàn bộ.

## 7. Isolation của JobRepository khác isolation của dữ liệu nghiệp vụ

Spring Batch có hai lớp dữ liệu thường bị nhầm:

| Lớp | Vai trò | Transaction nào cần xem? |
| --- | --- | --- |
| **JobRepository metadata** | Tạo/tra `JobInstance` và `JobExecution`, lưu `StepExecution`, counters và `ExecutionContext` | Repository transaction, đặc biệt ở thao tác tạo execution/instance |
| **Business reader/writer** | Đọc input, biến đổi và ghi business output | Chunk/tasklet transaction do step cấu hình |

Spring Batch thường sử dụng isolation chặt cho **thao tác tạo JobExecution/JobInstance** (trong cấu hình tham khảo truyền thống là `SERIALIZABLE` cho create) để tránh hai tiến trình cùng khởi tạo một job instance không hợp lệ. Nhưng điều đó **không** có nghĩa các câu `SELECT` và `UPDATE` của worker tự chạy ở `SERIALIZABLE`.

### Hai datasource có thể khác nhau

~~~mermaid
flowchart TB
    L["JobLauncher / Manager"] --> R[("JobRepository DB<br/>job/step metadata")]
    L --> W["Worker Step"]
    W --> T["Chunk TransactionManager"]
    T --> B[("Business DB<br/>orders / output / work queue")]
    W --> R
    N["Other OLTP transactions"] --> B
~~~

Nếu `JobRepository` và business data dùng **hai database/transaction managers độc lập**, metadata checkpoint và business write **không mặc nhiên atomic**. Khi một bên commit còn bên kia lỗi, restart có thể đọc lại item đã ghi hoặc bỏ sót item nếu checkpoint bị cập nhật sai.

Giải pháp còn cần reader restartable, business idempotency, outbox/reconciliation khi có external effects. Đừng tăng isolation của repository với hy vọng sửa mọi race ở business database.

### Thay isolation cho create không phải bước tối ưu đầu tiên

Khi có lock contention ở JobRepository, trước hết xác định:

- Contention xảy ra ở **tạo JobExecution** hay ở **cập nhật StepExecution/context**?
- Có quá nhiều worker cùng cập nhật metadata trên cùng DB/pool không?
- Job có bị khởi chạy trùng với identifying `JobParameters` không?
- Backend DB và transaction manager đang dùng đúng cấu hình framework không?

Chỉ cân nhắc thay `isolation-level-for-create` của repository sau khi hiểu cơ chế bảo vệ uniqueness/launch concurrency và kiểm thử trên phiên bản Spring Batch đang dùng. Nó là **thiết lập riêng**, không thay đổi isolation của tất cả business transactions.

## 8. Cấu hình isolation cho chunk step Spring Batch 5.x

Với `TaskletStep`/chunk-oriented step, có thể đặt `TransactionAttribute` trên builder. Ví dụ chọn `READ_COMMITTED` cho transaction chunk, sau khi đã bảo vệ business effect bằng unique key và input partition ổn định:

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.interceptor.DefaultTransactionAttribute;

@Bean
Step ordersWorkerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderRow> reader,
        ItemWriter<OrderRow> writer) {

    DefaultTransactionAttribute tx = new DefaultTransactionAttribute();
    tx.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRED);
    tx.setIsolationLevel(TransactionDefinition.ISOLATION_READ_COMMITTED);

    return new StepBuilder("ordersWorkerStep", jobRepository)
            .<OrderRow, OrderRow>chunk(200, transactionManager)
            .reader(reader)
            .writer(writer)
            .transactionAttribute(tx)
            .build();
}
~~~

`OrderRow` và các bean reader/writer là thành phần ứng dụng. Đây là ví dụ hướng tới Spring Batch **5.x** và Spring Framework tương thích; cấu hình worker thật còn cần `Job`, `Partitioner` và `PlatformTransactionManager` đúng datasource. Code chưa bao gồm các bean hay `@Configuration` để chạy độc lập.

### Điểm phải kiểm tra

1. `transactionAttribute(tx)` điều khiển **transaction do step tạo cho chunk/tasklet**, không ép mọi method JDBC trong ứng dụng bỏ qua các transaction khác.
2. Nếu code mở một transaction riêng bằng `REQUIRES_NEW` hoặc gọi service có `@Transactional` qua Spring proxy, cần xem **transaction nào thực sự bao bọc SQL**.
3. Nếu sử dụng JPA, connection pooling hoặc transaction manager tùy biến, mức isolation được hỗ trợ và cách set phải được xác nhận bằng driver/DB; không suy ra database chắc chắn áp dụng chỉ vì giá trị được gán trong Java.
4. Nếu resource đọc qua cursor hoặc connection ngoài transaction chunk, câu SQL reader có thể chạy dưới **isolation của connection/transaction khác**. Đừng tự kết luận toàn bộ reader chịu cùng snapshot của writer.
5. Không đặt `SERIALIZABLE` trên toàn bộ job bằng một transaction dài; Spring Batch chunking được thiết kế cho checkpoint/commit từng chunk phù hợp, không giữ lock hàng giờ.

### @Transactional ở service helper có thay chunk transaction không?

~~~java
@Transactional(isolation = Isolation.SERIALIZABLE)
public void applyBusinessRule(...) {
    // SQL nghiệp vụ
}
~~~

Đoạn trên thuộc Spring Framework và được áp dụng khi gọi qua transaction proxy. Nếu method **tham gia transaction hiện có** với propagation mặc định `REQUIRED`, không thể giả định nó nâng isolation của transaction chunk đã bắt đầu; thiết lập isolation chủ yếu có hiệu lực khi tạo transaction mới, tùy cấu hình quản lý transaction và validateExistingTransactions.

Vì vậy, xác định rõ **transaction boundary ở cấp step** hoặc tạo một transaction độc lập thực sự có chủ đích; không rải `@Transactional(isolation = SERIALIZABLE)` trên các helper rồi tin rằng DB sẽ tự nâng mức cô lập của mọi chunk.

## 9. Đọc snapshot nhất quán khi job kéo dài nhiều giờ

Giả sử worker dùng `JdbcPagingItemReader` để đọc bảng `orders` trong khi OLTP tiếp tục thêm/sửa orders. Mỗi page query có thể thấy một trạng thái dữ liệu khác, đặc biệt nếu chạy ở `READ_COMMITTED` và reader không có snapshot toàn job.

### Vấn đề với OFFSET pagination trên dữ liệu biến động

~~~text
SELECT ... ORDER BY id LIMIT 100 OFFSET 0
SELECT ... ORDER BY id LIMIT 100 OFFSET 100
~~~

Nếu dữ liệu bị chèn/xóa giữa hai lần SELECT, offset có thể trỏ vào vùng đã thay đổi, gây **đọc lặp hoặc bỏ sót item**. Dùng sort key ổn định và keyset/cursor có thể giảm một số sai lệch, nhưng **không tự biến nguồn biến động thành snapshot bất biến**.

### Ba chiến lược thường dùng

| Chiến lược | Cách làm | Lưu ý |
| --- | --- | --- |
| **Materialized input manifest** | Chốt tập primary keys/phiên bản cần xử lý ở đầu job, rồi worker đọc theo manifest | Nếu bản thân giá trị row có thể đổi, cần capture version/payload hoặc kiểm tra snapshot |
| **Watermark + stable key** | Chỉ đọc `id <= maxId` tại thời điểm xác định; sort unique | Chặn item mới có ID lớn, nhưng **không** chặn update/delete hay insert cũ |
| **Nguồn bất biến / snapshot export** | Đọc từ bảng snapshot, bản sao file hoặc dữ liệu versioned | Thường dễ đối soát nhất; tốn dung lượng/công chuẩn bị |

Một **long-lived REPEATABLE_READ transaction** giữ qua toàn bộ job có thể cung cấp snapshot ổn định trong một số DB, nhưng thường không thích hợp cho pipeline kéo dài hàng giờ: connection/transaction giữ lâu, MVCC history có thể phình to, lock/maintenance bị ảnh hưởng. Ưu tiên snapshot/manifest bền vững rồi xử lý nhiều chunk độc lập.

### Ví dụ manifest

~~~sql
-- PostgreSQL, schema ví dụ
CREATE TABLE batch_input_manifest (
    snapshot_id VARCHAR(120) NOT NULL,
    tenant_id VARCHAR(80) NOT NULL,
    order_id BIGINT NOT NULL,
    source_version BIGINT NOT NULL,
    PRIMARY KEY (snapshot_id, tenant_id, order_id)
);
~~~

Manifest chỉ lưu `order_id`/`source_version` thì tập identity ổn định, **không bảo đảm nội dung row giữ nguyên**. Khi đọc nghiệp vụ, có thể:

- Copy những trường input cần thiết vào staging snapshot;
- Dùng bảng temporal/versioned để lấy đúng `source_version`;
- Hoặc từ chối xử lý nếu version thay đổi, ghi conflict để reconcile.

Không dùng manifest key cũ để đọc tùy ý nội dung `orders` mới mà vẫn gọi đó là snapshot nhất quán.

## 10. Partitioning: isolation không sửa overlap range

Một `Partitioner` có thể tạo các `ExecutionContext` với `minId` và `maxIdExclusive`:

| Partition | minId | maxIdExclusive |
| --- | ---: | ---: |
| `range-0000` | 1 | 250001 |
| `range-0001` | 250001 | 500001 |
| `range-0002` | 500001 | 750001 |
| `range-0003` | 750001 | 1000001 |

Reader phải áp dụng **cùng predicate nửa mở**:

~~~sql
SELECT id, tenant_id, status
FROM orders
WHERE id >= :minId
  AND id < :maxIdExclusive
ORDER BY id;
~~~

Nếu hai workers dùng overlapping predicates, `SERIALIZABLE` vẫn không biến hai lần **đọc** cùng item thành một tác vụ duy nhất; nó có thể bảo vệ một số xung đột ghi nhưng không tự hiểu business semantics của duplicate processing.

### Yêu cầu đối với partition plan

1. Mọi khoảng phải **không giao nhau**, bao phủ đúng snapshot theo yêu cầu.
2. Partition key → range/input version ổn định trên restart cùng `JobInstance`.
3. Sort/paging key là **unique, deterministic**; nếu sort theo `created_at` không unique, thêm `id` làm tie-breaker.
4. Worker `@StepScope` nhận đúng context riêng, không dùng singleton mutable `currentMinId`.
5. Writer chịu được replay theo **business operation key**, không dựa vào `StepExecutionId`.
6. Không đổi `gridSize` rồi gán lại cùng partition key cho phạm vi mới khi còn checkpoint cũ.

### @StepScope không phải transaction isolation

`@StepScope` cách ly target bean theo `StepExecution` trong Spring Batch, nhưng **không** thay đổi database isolation level; nhiều worker vẫn dùng chung bảng/index và có thể cạnh tranh rows. Với multi-threaded chunks **trong cùng một StepExecution**, scoped target còn có thể bị nhiều threads sử dụng đồng thời; stateful reader/writer phải được đánh giá riêng.

## 11. Hai kiểu chia công việc: range tĩnh và dynamic claim queue

### Range tĩnh

Nếu `Partitioner` chia dữ liệu bất biến thành các phạm vi không overlap, mỗi worker có thể đọc theo range với `READ_COMMITTED` kết hợp stable snapshot, unique key và checkpoint đúng. Cách này thường giảm việc tranh nhau claim cùng hàng.

### Dynamic claim queue

Nếu nhiều worker cần lấy việc chưa xử lý từ **một bảng chung**, mẫu nguy hiểm là:

~~~text
Worker A: SELECT id FROM work_queue WHERE state='PENDING' LIMIT 100
Worker B: SELECT id FROM work_queue WHERE state='PENDING' LIMIT 100
Worker A và B đều thấy cùng 100 rows -> xử lý trùng
~~~

`READ_COMMITTED` không tự ngăn hai SELECT này đọc cùng tập. Cần **atomic claim** hoặc cơ chế lock phù hợp.

## 12. PostgreSQL FOR UPDATE SKIP LOCKED để claim công việc

Trong một queue table, PostgreSQL hỗ trợ `FOR UPDATE SKIP LOCKED` cho phép nhiều consumer lấy những rows chưa bị transaction khác lock. Ví dụ:

~~~sql
-- PostgreSQL: thực thi trong transaction claim NGẮN.
WITH picked AS (
    SELECT id
    FROM batch_work_queue
    WHERE state = 'PENDING'
    ORDER BY id
    FOR UPDATE SKIP LOCKED
    LIMIT :batchSize
)
UPDATE batch_work_queue AS q
SET state = 'CLAIMED',
    worker_id = :workerId,
    claimed_at = CURRENT_TIMESTAMP
FROM picked
WHERE q.id = picked.id
RETURNING q.id;
~~~

**Giả định schema** có `id` là khóa duy nhất, `state`, `worker_id` và `claimed_at`. `:batchSize` và `:workerId` là parameter placeholder thuộc tầng ứng dụng; cú pháp tham số và SQL bên trên là **PostgreSQL-specific**. Không sao chép nguyên sang Oracle/MySQL/SQL Server nếu chưa tra đúng cơ chế tương ứng.

### Vì sao phải giữ transaction claim ngắn?

- Row locks giữ đến khi **transaction claim commit/rollback**.
- Khi commit claim, rows mang `CLAIMED` và worker khác sẽ không lấy chúng qua predicate `state='PENDING'`.
- Nếu worker chết **sau khi claim commit, trước khi xử lý**, rows có thể mắc ở `CLAIMED` mãi. Cần **lease/claim expiry, heartbeat, requeue** hoặc cơ chế phục hồi khác.
- Không giữ DB transaction và row locks suốt một HTTP request kéo dài nhiều phút chỉ để đảm bảo worker không chạy lại.

### SKIP LOCKED không phải giải pháp tổng quát

| Rủi ro | Giới hạn |
| --- | --- |
| Row bị worker giữ lock lâu | Worker khác bỏ qua row đó, có thể gây starvation |
| Query `ORDER BY` + locks | Thứ tự tuyệt đối không luôn được bảo đảm như queue tuần tự duy nhất |
| Lease hết hạn trong lúc worker cũ còn xử lý | Hai workers có thể chạy cùng công việc |
| Worker ghi external API | DB row lock không rollback request API đã gửi |
| Một message cùng operation được giao lại | Cần idempotency ở đích, không chỉ row claim |
| Queue rất lớn và hot state index | Lock contention/index writes có thể giảm throughput |

Khi cần single active owner mạnh, dùng **fencing token hoặc version generation** mà nơi ghi kết quả kiểm tra; cùng với business idempotency để xử lý request trùng ngoài transaction.

## 13. READ COMMITTED + claim + unique key: một kiến trúc thực dụng

Với queue công việc chuyển dữ liệu:

~~~mermaid
flowchart LR
    Q[("Work queue<br/>PENDING/CLAIMED/DONE")] --> C["Worker: atomic claim<br/>READ COMMITTED"]
    C --> P["Process input<br/>stable operation ID"]
    P --> D[("Business output<br/>unique operation key")]
    D --> A["Commit / outcome"]
    A --> Q
    A --> R[("JobRepository<br/>StepExecution/checkpoint")]
~~~

Luồng logic này chỉ an toàn khi các chuyển trạng thái được thiết kế nhất quán. Nếu `business output` và `queue DONE` nằm **cùng DB transaction**, có thể commit cả hai. Nếu ở hai DB khác nhau, cần durable intent/reconciliation và writer idempotent.

### Luật trạng thái tối thiểu

~~~text
PENDING -> CLAIMED -> DONE
               |
               +--> RETRYABLE / PENDING khi lease hết và đã xác minh
               +--> FAILED_FINAL / QUARANTINED khi lỗi nghiệp vụ rõ
               +--> UNKNOWN khi side effect ngoài DB chưa xác nhận
~~~

Một row bị lock không có nghĩa đã thực thi nghiệp vụ. Một row `DONE` phải có bằng chứng đã commit output; nếu API ngoài chưa xác nhận, không tự chuyển `DONE`.

### Khóa và version

Ví dụ cập nhật trạng thái có owner token:

~~~sql
UPDATE batch_work_queue
SET state = 'DONE',
    completed_at = CURRENT_TIMESTAMP
WHERE id = :workId
  AND state = 'CLAIMED'
  AND worker_id = :workerId
  AND claim_version = :claimVersion;
~~~

Chỉ khi update count = `1` thì worker được quyền hoàn tất row trong phiên claim đó. Nếu `0`, owner đã đổi hoặc row không còn ở trạng thái dự kiến; không ghi đè bừa. Để chống worker cũ **tiếp tục external side effect**, vẫn cần provider idempotency/fencing ở đích.

## 14. Retry deadlock và serialization failure

Khi tăng concurrency, một transaction có thể không commit vì **deadlock**, **serialization failure** hoặc lock timeout. Đây là **lỗi cạnh tranh/transaction**, không phải item hỏng cần skip.

### Phân biệt các loại lỗi

| Lỗi | Nguyên nhân có thể | Hành động phù hợp |
| --- | --- | --- |
| Deadlock victim | Hai hoặc nhiều transactions giữ locks theo thứ tự xung đột | Rollback và retry transaction với backoff nếu an toàn |
| Serialization failure | DB không thể giữ lịch biểu serializable cho các transactions | Retry toàn transaction/đơn vị công việc |
| Lock timeout | Chờ lock vượt ngưỡng | Phân tích hot rows/queries, giới hạn concurrency, retry có budget |
| Connection pool exhaustion | Quá nhiều workers/transactions cần connection | Giảm concurrency, pool sizing, kiểm tra transaction dài |
| Unique key violation | Duplicate replay hợp lệ hoặc conflict payload | Kiểm tra operation key + payload; không skip cả nhóm |
| SQL/schema error permanent | Câu query/migration sai | Fail fast và sửa code/schema |

### Retry phải bao phủ transaction hợp lý

Sau serialization failure, không được chỉ retry **một câu UPDATE cuối cùng** trong transaction đã bị đánh dấu rollback. Thường phải:

1. Rollback transaction thất bại.
2. Mở transaction mới.
3. Đọc lại dữ liệu/condition cần thiết dưới snapshot mới.
4. Thực hiện lại toàn bộ quyết định và ghi trong transaction mới.
5. Giữ business operation ID ổn định và bảo vệ external side effects.

Với Spring Batch fault-tolerant step, đánh giá exception translation và semantics của retry với read/process/write/rollback. Cần test **số attempts và state thực tế**; không suy ra mọi lỗi được framework retry ở đúng nơi mong muốn.

### Đặt giới hạn rõ

~~~java
// Mẫu khai báo tùy thuộc exception cụ thể mà DB/driver dịch ra.
.faultTolerant()
.retry(ConcurrencyFailureException.class)
.retryLimit(3)
~~~

`ConcurrencyFailureException` là loại trong Spring DAO dùng cho nhiều tình huống lỗi concurrency. Đây là **mảnh cấu hình minh họa**, không thể thay cho việc kiểm tra exception thực tế của JDBC/JPA. Nếu cùng operation còn gọi API ngoài transaction, retry phải đi kèm idempotency/reconciliation hoặc dừng an toàn.

Đừng dùng `skip(ConcurrencyFailureException.class)` chỉ để job vượt qua deadlock: item có thể hoàn toàn hợp lệ, và việc skip làm thiếu output.

## 15. Isolation và hiệu năng: mức cao hơn không luôn nhanh hơn

Giả sử 16 workers cùng ghi một bảng `orders_output`:

- `READ_COMMITTED` thường giảm thời gian giữ snapshot/lock tương đối so với giao dịch đọc kéo dài, nhưng vẫn có row/index contention.
- `REPEATABLE_READ` giữ một góc nhìn nhất quán hơn **trong transaction**, có thể làm xung đột update/lock theo semantics riêng DB.
- `SERIALIZABLE` có thể tăng rollback do serialization conflicts; throughput thực tế có thể **giảm khi worker count tăng**.
- Mức isolation không xóa giới hạn CPU, I/O, WAL/redo log, connection pool hoặc kích thước index.

### Thử nghiệm trước khi chọn isolation

| Thử nghiệm | Biến thay đổi | Đo gì? |
| --- | --- | --- |
| Baseline | 1 worker, `READ_COMMITTED` | Throughput, latency, dữ liệu đúng |
| Scale dần | 4, 8, 16 workers | Throughput tăng hay lock waits tăng? |
| Isolation khác | READ COMMITTED / REPEATABLE READ / SERIALIZABLE | Abort/retry/deadlock và correctness |
| Chunk size | 50, 200, 500 item | Commit overhead vs rework/lock time |
| Hot-key mix | Phần lớn workers cập nhật cùng tenant/aggregate | Conflict rate và fairness |
| Outage / restart | DB failover, kill worker | Checkpoint, idempotency và số effect thực |
| Pool constraint | Pool nhỏ/đủ/oversubscribed | Queue wait và transaction duration |

### Các metric quan trọng

- Items/s, chunks/s và P95/P99 thời gian commit.
- Số active DB connections, pool wait/timeouts.
- Lock waits, deadlocks, serialization failures, retry attempts và rollback rate.
- Buffer cache hit, I/O, CPU, WAL/redo throughput, index contention.
- `StepExecution.readCount`, `writeCount`, `rollbackCount`, `commitCount` theo worker.
- Số business operation IDs **duy nhất** đã commit, duplicate prevented và source/output mismatches.

**Đừng chỉ tối ưu items/s.** Job chạy nhanh nhưng bỏ sót item hoặc phát lại charge hai lần là thất bại về tính đúng. Cần đo cả **throughput lẫn correctness dưới lỗi thực**.

## 16. Connection pool và giới hạn tài nguyên

Mỗi worker không nhất thiết giữ đúng một connection duy nhất suốt job. Reader, writer, transaction, metadata repository và HTTP client có thể dùng những pool/resource khác nhau.

~~~text
12 worker threads đang ghi business DB
  + connection của manager/OLTP
  + job repository transactions
  + admin/monitoring connections

Nếu tổng nhu cầu > DB/pool capacity:
  -> pool wait -> timeout -> retry storm -> throughput giảm
~~~

Không đặt pool size bằng `gridSize` một cách máy móc. Hãy quan sát:

1. Mức song song thực tế của chunks và partition workers.
2. Số datasource và transaction managers độc lập.
3. Reader có giữ cursor/connection ngoài chunk không.
4. Transaction duration và khả năng trả connection đúng hạn.
5. Headroom cho OLTP và các dịch vụ dùng chung DB.

Một concurrency limit ở `TaskExecutor`, `PartitionHandler` hoặc worker consumer nên đi cùng **pool size, backpressure và database capacity**, tránh làm OLTP suy giảm khi Batch scale.

## 17. Kiểm thử isolation trên database thật

Unit test một repository mock không chứng minh isolation. Các hiện tượng transaction cần **ít nhất hai connection và hai transaction độc lập**, tốt nhất trên database engine/phiên bản giống production.

### 17.1. Test READ COMMITTED nhìn bản ghi mới giữa hai SELECT

Với PostgreSQL Testcontainers hoặc DB test thật:

~~~text
T1: BEGIN READ COMMITTED
T1: SELECT status WHERE id=42 -> NEW

T2: BEGIN
T2: UPDATE orders SET status='CANCELLED' WHERE id=42
T2: COMMIT

T1: SELECT status WHERE id=42 -> CANCELLED
T1: COMMIT
~~~

Test cần điều phối hai transactions bằng latch/barrier để bảo đảm **T2 commit nằm giữa hai SELECT của T1**. Với `REPEATABLE_READ` trên PostgreSQL, hai SELECT trong cùng T1 thường thấy snapshot cũ nếu transaction không tự update row đó. Với Oracle/MySQL/SQL Server, hãy xác minh semantics của cấu hình cụ thể.

### 17.2. Test optimistic locking

Hai worker đọc cùng `version=4`:

~~~text
Worker A: UPDATE ... WHERE version=4 -> updateCount=1
Worker B: UPDATE ... WHERE version=4 -> updateCount=0
~~~

Kết quả mong đợi:

- Không lost update.
- Worker B **không** coi `updateCount=0` là thành công.
- Worker B đọc lại record và quyết định retry/skip/fail theo business rule.
- Nếu có operation event replay, unique business key không bị thay đổi.

### 17.3. Test serializable/write skew

Hai connection/transaction cùng:

1. Đọc cùng invariant tổng hợp.
2. Cập nhật hai rows khác nhau để tạo write skew nếu chạy dưới snapshot isolation thích hợp.
3. Thử ở isolation tương ứng với DB engine.
4. Khi dùng `SERIALIZABLE`, xác minh invariant cuối cùng giữ đúng và transaction có thể bị abort/retry.

**Không viết test chấp nhận cả hai transactions commit** rồi khẳng định serializable đang hoạt động. Kiểm tra kết quả business invariant và exception thực tế.

### 17.4. Test SKIP LOCKED có hai consumers

Chuẩn bị 100 `PENDING` work rows, chạy hai transactions song song claim tối đa 40 rows mỗi transaction:

- Tập rows trả cho worker A và B **không giao nhau** trong cùng lượt claim.
- Sau commit, số `CLAIMED` phù hợp với số rows đã claim.
- Khi một claim transaction rollback, rows của nó vẫn có thể được worker khác claim.
- Worker crash sau claim commit được xử lý bằng lease recovery, không mắc `CLAIMED` vĩnh viễn.
- Thử hot rows/low pool capacity và đo lock waits thực tế.

### 17.5. Test Spring Batch chunk/restart

Giả sử reader lấy manifest snapshot bất biến, chunk size 200 và worker writer dùng unique operation key:

1. Chạy job cho một vài chunks commit.
2. Gây lỗi DB ở chunk tiếp theo, xác minh worker `FAILED`/metadata khi repository vẫn hoạt động.
3. Khôi phục DB, **restart cùng JobInstance** với partition key → range không đổi.
4. Kiểm tra mọi source key expected có outcome hợp lệ.
5. Kiểm tra số business effects unique, không bị nhân đôi khi replay.
6. Đối chiếu `readCount/writeCount/rollbackCount` nhưng không lấy counters thay cho business ledger.

Nếu outage xảy ra ở **JobRepository DB**, framework có thể không ghi được trạng thái cuối ngay lúc lỗi; test recovery và vận hành phải xử lý riêng tình huống metadata chưa nhất quán, không sửa thủ công để ép restart.

### 17.6. Ma trận test lỗi và cạnh tranh

| Kịch bản | Điều cần chứng minh |
| --- | --- |
| Hai workers cập nhật cùng version | Không lost update, `updateCount`/conflict được xử lý |
| Hai workers claim một work row | Không cùng owner hợp lệ sau atomic claim |
| Worker chết sau claim commit | Lease/recovery không bỏ quên row |
| Worker cũ chạy sau lease expiry | Fencing/idempotency ngăn stale effect |
| Transaction `SERIALIZABLE` bị abort | Retry toàn transaction an toàn, không skip item |
| DB deadlock | Rollback/retry có giới hạn, không tạo write duplicate |
| Chunk commit rồi manager mất reply | Replay không tạo thêm business operation |
| Job restart với input đang thay đổi | Phát hiện snapshot/version drift thay vì bỏ sót |
| Partition ranges overlap | Test phát hiện trùng source keys dù isolation cao |
| Mỗi chunk dùng `REPEATABLE_READ` | Test chứng minh **không** tạo snapshot toàn job |
| Hai datasource business/repository | Kiểm tra crash window và idempotency khi commit không atomic |
| 16 workers với pool nhỏ | Thấy backpressure/timeout thay vì retry vô hạn |
| SQL update count bằng 0 | Không coi đó là business success |
| HTTP side effect và DB rollback | Same-key retry/reconciliation không nhân đôi external effect |

## 18. Runbook khi workload song song xuất hiện lock/duplicate/missing

Khi tăng worker mà job chậm hẳn hoặc dữ liệu sai:

1. **Đóng băng input identity:** JobInstance, identifying parameters, input snapshot, partition keys và source ranges.
2. **Xác minh transaction:** Business DB/JobRepository có chung hay khác datasource? Isolation thực tế được driver áp dụng là gì? Có transaction dài không?
3. **Đọc lỗi DB:** Deadlock, serialization failure, lock timeout, pool timeout hay schema error? Không đánh đồng chúng thành bad record.
4. **Kiểm tra query:** Stable sort key, range nửa mở, predicate tenant, indexes và snapshot/watermark có đúng?
5. **Kiểm tra claim:** Nếu dùng work queue, claim có atomic không, `SKIP LOCKED` có starving rows, lease có được requeue?
6. **Kiểm tra writer:** Unique operation key, optimistic lock/version, constraint conflict handling và idempotent external effects.
7. **Xem metadata:** `JobExecution`/`StepExecution` statuses, rollback/commit counts, checkpoint và retry history.
8. **Đo bottleneck:** Active connections, lock waits, transaction duration, DB CPU/I/O, pool queues và throughput theo worker count.
9. **Giảm concurrency có kiểm soát:** Không tăng `gridSize` khi DB đã bão hòa; đặt backpressure rồi thử lại với workload nhỏ.
10. **Khôi phục đúng đường:** Restart cùng JobInstance khi phù hợp, giữ partition plan ổn định, reconcile các effects chưa rõ, không tự sửa JobRepository schema/counters.
11. **Đối soát trước publish:** Manifest source keys, business output unique keys, skip/filter/quarantine, pending/unknown và amounts/checksum cần khớp invariant.
12. **Lưu bài học vận hành:** Ghi cấu hình isolation/DB version, retry policy, benchmark và fault-injection case để ngăn lặp sự cố.

### Khi nào nên chọn isolation cao hơn?

Chỉ tăng isolation sau khi xác định một **invariant không được bảo vệ** bởi constraint/version/atomic claim hoặc khi workload thật sự cần snapshot ổn định **trong một transaction cụ thể**. Nếu vấn đề là input biến động qua nhiều chunks, giải pháp thường là **manifest/snapshot** chứ không phải bật `SERIALIZABLE` cho mọi chunk.

### Khi nào nên giảm worker thay vì tăng isolation?

Nếu lock wait, serialization abort, pool wait hoặc WAL/redo I/O tăng nhanh trong khi items/s không tăng tương ứng, bottleneck đã ở database. Giảm concurrency, phân vùng theo hot key, tối ưu index/query, giảm thời gian giữ transaction hoặc thiết kế staging/merge có thể hiệu quả hơn.

## 19. Bài tập tình huống

Một job nhập **3 triệu transactions** chia thành 12 partitions. Mỗi worker `chunk(500)` và đọc `orders WHERE status='NEW'` qua paging, trong khi OLTP liên tục đổi `NEW → PAID`. Nhóm vận hành thấy:

- Một số order không xuất hiện trong output, dù `readCount` của toàn job khá cao.
- Hai workers cùng update `account_balance` dựa trên giá trị đã SELECT, dẫn tới lost update.
- Cấu hình `SERIALIZABLE` cho mọi chunk làm tăng serialization failures và giảm throughput.
- Một worker restart sau khi database đích đã commit nhưng JobRepository chưa có checkpoint mới.
- Manager đang dùng `isolation-level-for-create=SERIALIZABLE` nên nhóm cho rằng mọi worker đã ở serializable.

**Câu hỏi:**

1. Vì sao `READ_COMMITTED` cùng paging trên bảng OLTP biến động có thể làm tập input thay đổi?
2. `REPEATABLE_READ` trên mỗi chunk có tạo một snapshot ổn định cho cả 3 triệu rows không?
3. Nên thay query/đầu vào thế nào để mọi worker xử lý một tập dữ liệu cố định?
4. Làm sao chặn lost update mà không đặt mọi operation ở `SERIALIZABLE`?
5. Vì sao mức isolation cho `JobRepository` khi tạo JobExecution không xác định isolation của business writer?
6. Khi một chunk đã commit nhưng checkpoint chưa lưu, điều gì bảo vệ khỏi side effect trùng?
7. Bạn sẽ đo và kiểm thử gì để chọn số workers, chunk size và isolation phù hợp?

**Định hướng trả lời:** Paging trên nguồn đang thay đổi không đảm bảo tập dữ liệu bất biến; cần materialized manifest/staging snapshot hoặc watermark cộng quy tắc version rõ ràng. `REPEATABLE_READ` chỉ duy trì góc nhìn trong **transaction hiện tại**, không nối các chunks. Dùng `UPDATE ... WHERE version=:expected`, atomic SQL update và unique business operation key để bảo vệ ghi; khi cần invariant tổng hợp, cân nhắc serializable transaction **hẹp** có retry. Cấu hình create-isolation của repository là thiết lập metadata riêng. Worker replay cần idempotent writer và reconciliation. Đo lock wait, rollback/serialization failures, pool wait, throughput, missing/duplicate business IDs và kiểm thử crash windows.

## Tài liệu tham khảo

- [Spring Batch Reference — Chunk-Oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): transaction boundary và commit chunk.
- [Spring Batch Reference — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html): checkpoint và `ItemStream`.
- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): multi-threaded step, parallel steps, partitioning.
- [Spring Batch Reference — JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html): cấu hình repository, isolation khi tạo execution.
- [Spring Batch Reference — Metadata Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): bảng `BATCH_STEP_EXECUTION` và các metadata.
- [Spring Framework Reference — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): `@Transactional`, propagation, isolation và transaction managers.
- [Spring Framework API — TransactionDefinition](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/TransactionDefinition.html): các isolation constants trong Spring.
- [PostgreSQL Documentation — Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): READ COMMITTED, REPEATABLE READ và SERIALIZABLE theo PostgreSQL.
- [PostgreSQL Documentation — SELECT / Locking Clause](https://www.postgresql.org/docs/current/sql-select.html): `FOR UPDATE SKIP LOCKED` và giới hạn.
- [MySQL InnoDB — Transaction Isolation Levels](https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-isolation-levels.html): khác biệt MVCC và locking của InnoDB.

> **Ghi nhớ:** **Isolation level là công cụ kiểm soát transaction, không phải nút “bật an toàn cho cả job”.** Trong Spring Batch song song, hãy xác định ranh giới chunk/repository, giữ input snapshot và partition plan ổn định, dùng atomic claim/optimistic locking/unique business key cho các invariant cần thiết, retry transaction bị xung đột có giới hạn và đo database contention thực tế. Không hy sinh tính đúng khi tăng throughput, và không coi `SERIALIZABLE` ở một transaction là bảo đảm exactly-once cho mọi side effect phân tán.
