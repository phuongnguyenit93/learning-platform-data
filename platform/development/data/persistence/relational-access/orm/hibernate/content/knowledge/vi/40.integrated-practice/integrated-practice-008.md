# Nhập dữ liệu theo lô với batching, flush, clear và khả năng chạy lại

Một job import có thể phải ghi hàng trăm nghìn hoặc hàng triệu bản ghi vào database. Nếu mỗi entity được persist rồi commit riêng, ứng dụng tạo rất nhiều round-trips, transaction overhead và áp lực lên connection pool. Nếu giữ tất cả entities trong một persistence context tới cuối job, heap có thể tăng liên tục và Hibernate phải quản lý lượng lớn managed state.

Để xử lý workload này, cần kết hợp đúng bốn cơ chế:

- **JDBC batching** gom nhiều câu INSERT/UPDATE/DELETE tương thích vào một batch để giảm số lần gửi statement tới database.
- **Chunking** chia input thành các nhóm hữu hạn, ví dụ 500 hoặc 1.000 records mỗi chunk.
- **flush()** yêu cầu Hibernate đồng bộ các thay đổi đang chờ trong persistence context xuống JDBC.
- **clear()** detach các entities khỏi persistence context để giảm memory và dirty-checking overhead.

Một job chạy bền vững còn cần **transaction boundary, checkpoint, idempotency và retry policy**. Batching làm thao tác ghi nhanh hơn; nó không tự bảo đảm job có thể chạy lại an toàn khi process chết giữa chừng.

Bài thuộc chương **Thực hành tổng hợp** của Data Persistence Relational Access ORM Hibernate. Ta sẽ thiết kế một pipeline import có thể vận hành được: đọc dữ liệu, validate, ghi theo chunk, flush/clear, commit, lưu tiến độ, xử lý lỗi và tiếp tục từ checkpoint.

---

## 1. Bốn khái niệm cần tách biệt

| Cơ chế | Giải quyết vấn đề | Không tự giải quyết |
| --- | --- | --- |
| JDBC batching | Giảm round-trips khi nhiều statements có thể được gom | Không giảm số entity cần hydrate; không chia transaction |
| Chunking | Giới hạn số records xử lý trong một đơn vị công việc | Không tự bật JDBC batching |
| flush() | Gửi pending ORM changes xuống JDBC/database trong transaction hiện tại | Không commit transaction, không giải phóng persistence context |
| clear() | Detach toàn bộ managed entities khỏi persistence context | Không commit, không xóa dữ liệu DB, không đóng transaction |
| Checkpoint | Ghi nhận tiến độ đã hoàn thành để restart | Không tự làm một chunk idempotent |
| Idempotency | Cho phép xử lý lại cùng input mà không tạo sai dữ liệu | Không tự xác định điểm restart |

Ví dụ:

~~~java
for (int i = 0; i < records.size(); i++) {
    entityManager.persist(map(records.get(i)));

    if ((i + 1) % 500 == 0) {
        entityManager.flush();
        entityManager.clear();
    }
}
~~~

Đoạn code trên giới hạn số managed entities được giữ trong persistence context. Tuy nhiên, nếu không cấu hình Hibernate/JDBC batching, 500 lần persist vẫn có thể tạo 500 INSERT executions riêng. Nếu method chỉ commit ở cuối, toàn bộ records vẫn nằm trong một transaction dài.

Một pipeline hoàn chỉnh cần quyết định riêng:

1. Batch size cho JDBC.
2. Chunk size cho bộ nhớ và transaction.
3. Thời điểm flush/clear.
4. Transaction commit boundary.
5. Checkpoint được cập nhật ở đâu.
6. Khi lỗi, chunk được rollback hay ghi một phần.
7. Khi restart, records đã xử lý được nhận diện thế nào.

## 2. Phân biệt JDBC batch size và chunk size

Hai con số thường giống nhau trong ví dụ đơn giản nhưng mang ý nghĩa khác nhau.

### 2.1. JDBC batch size

JDBC batch size là số parameter sets/statements được gom trước khi driver gửi batch execution. Ví dụ Hibernate batch size 50 nghĩa là Hibernate có thể gom tối đa khoảng 50 statements tương thích trước khi execute batch; chi tiết phụ thuộc SQL shape, driver và thao tác flush.

### 2.2. Chunk size

Chunk size là số input records được xử lý trong một transaction/chunk. Ví dụ chunk size 1.000 nghĩa là job đọc, validate, ghi và commit tối đa 1.000 records trong một đơn vị công việc.

Một chunk 1.000 records có thể được gửi qua 20 JDBC batches nếu batch size là 50.

\[
\text{Batches per chunk} \approx
\left\lceil\frac{\text{Chunk size}}{\text{JDBC batch size}}\right\rceil
\]

Công thức chỉ là ước lượng. Nếu các entity tạo SQL khác nhau, Hibernate có thể chia thành nhiều nhóm batch; inserts bị xen kẽ theo entity type cũng ảnh hưởng số batch thực tế.

### 2.3. Ví dụ

| Tham số | Giá trị |
| --- | ---: |
| Tổng input | 100.000 records |
| Chunk size | 1.000 records |
| JDBC batch size | 50 statements |
| Số chunks dự kiến | 100 |
| Batches gần đúng mỗi chunk cho một SQL shape | 20 |
| Tổng JDBC batch executions gần đúng | 2.000 |

Không có một cặp số tối ưu cho mọi hệ thống. Batch size lớn có thể giảm round-trips nhưng tăng driver memory, thời gian giữ locks và giới hạn parameter. Chunk size lớn giảm số commits nhưng tăng transaction duration, rollback cost và memory.

## 3. Kiến trúc một pipeline import có thể restart

Một pipeline điển hình:

~~~mermaid
flowchart TD
    A["Input source"] --> B["Read next chunk"]
    B --> C["Validate + normalize"]
    C --> D["Map to entities"]
    D --> E["Persist / update"]
    E --> F["flush()"]
    F --> G["Commit chunk transaction"]
    G --> H["Save committed checkpoint"]
    H --> I{"More input?"}
    I -->|Yes| B
    I -->|No| J["Mark job completed"]
    C -->|Invalid record| X["Reject/quarantine policy"]
    E -->|Transient failure| R["Rollback chunk + retry"]
    R --> B
~~~

Các bước cần có semantics rõ ràng:

- Input phải có thứ tự ổn định hoặc key nhận diện record.
- Một chunk phải có transaction boundary được xác định.
- Checkpoint chỉ phản ánh công việc đã commit.
- Retry phải xử lý được trường hợp commit thành công nhưng worker chưa kịp ghi checkpoint.
- Invalid records cần policy: fail cả chunk, reject từng record hay chuyển sang quarantine.
- Job cần phân biệt RUNNING, COMPLETED, FAILED và RESTARTABLE states.

## 4. Cấu hình Hibernate JDBC batching

Với Hibernate, cấu hình phổ biến:

~~~properties
hibernate.jdbc.batch_size=50
hibernate.order_inserts=true
hibernate.order_updates=true
hibernate.jdbc.batch_versioned_data=true
~~~

Trong Spring Boot, cấu hình thường đặt dưới prefix Hibernate:

~~~properties
spring.jpa.properties.hibernate.jdbc.batch_size=50
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.properties.hibernate.order_updates=true
spring.jpa.properties.hibernate.jdbc.batch_versioned_data=true
~~~

Ý nghĩa:

| Property | Tác dụng |
| --- | --- |
| jdbc.batch_size | Batch size mục tiêu cho JDBC statements |
| order_inserts | Sắp xếp INSERT theo entity type/SQL shape để tăng khả năng gom batch |
| order_updates | Sắp xếp UPDATE để gom batch và có thể giảm deadlock trong một số workload |
| jdbc.batch_versioned_data | Cho phép batch các versioned statements khi driver row-count semantics phù hợp |

Tên property và behavior cần kiểm tra theo Hibernate version đang dùng. Spring Boot BOM quản lý Hibernate version; không copy cấu hình từ blog cũ mà chưa xác nhận provider hiện tại.

### 4.1. Bắt đầu bằng batch size vừa phải

Các giá trị 25, 50 hoặc 100 thường được dùng làm điểm benchmark ban đầu, không phải default tối ưu. Thử trên database, driver và network thực tế.

Batch size quá lớn có thể tăng memory trong driver, kéo dài statement execution, tăng lock duration, vượt parameter/packet limits, làm batch failure khó xác định record gây lỗi và không cải thiện throughput nếu DB đã bão hòa.

### 4.2. Ordering có trade-off

`hibernate.order_inserts=true` và `hibernate.order_updates=true` có thể tăng số statement cùng loại được gom vào batch. Hibernate có thể phải sắp xếp action queue trước khi thực thi, làm tăng CPU/memory nhỏ và thay đổi thứ tự SQL.

Không dựa vào thứ tự INSERT/UPDATE ngẫu nhiên để bảo đảm business ordering hoặc trigger behavior. Nếu thứ tự có ý nghĩa, biểu diễn nó bằng dữ liệu, constraint hoặc transaction semantics.

### 4.3. Batch versioned data

Entity có `@Version` thường cần kiểm tra affected row count để xác định optimistic locking conflict. Một số JDBC drivers có thể trả row counts không tương thích với batch optimistic locking expectations. `hibernate.jdbc.batch_versioned_data` phải được bật dựa trên driver behavior/version và integration tests, không phải bật mù quáng.

## 5. Identifier generation có thể làm batching mất hiệu lực

Một trong những nguyên nhân phổ biến khiến INSERT batching không hoạt động là strategy sinh ID.

### 5.1. IDENTITY

~~~java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
~~~

Với IDENTITY, database sinh ID khi INSERT. Hibernate thường cần thực thi INSERT để lấy generated key ngay, vì vậy batching INSERT theo kiểu thông thường có thể bị vô hiệu hóa hoặc bị hạn chế tùy provider/version/driver.

Nếu bulk import cần throughput cao, hãy đánh giá sequence-based identifiers khi database hỗ trợ.

### 5.2. SEQUENCE

~~~java
@Id
@GeneratedValue(
    strategy = GenerationType.SEQUENCE,
    generator = "order_seq"
)
@SequenceGenerator(
    name = "order_seq",
    sequenceName = "purchase_order_seq",
    allocationSize = 50
)
private Long id;
~~~

Sequence cho phép lấy identifier trước khi INSERT. Hibernate có thể gom các INSERT sau đó vào JDBC batch.

Cần căn chỉnh sequence tồn tại và quyền truy cập, allocation size của mapping và database sequence, schema migration, dialect support và hiệu ứng gaps trong ID khi rollback/restart.

ID có gaps là bình thường với sequence allocation; không dùng ID liên tục như business sequence nếu domain yêu cầu số không bị thiếu.

### 5.3. UUID

UUID có thể tạo ở application side trước INSERT, do đó không cần round-trip lấy generated ID. Nhưng UUID random có thể làm index locality kém hơn một số key strategies; UUID storage type/ordering phụ thuộc database. Benchmark cả insert throughput và index size.

### 5.4. Bảng quyết định

| ID strategy | Có thể batch INSERT? | Điểm cần chú ý |
| --- | --- | --- |
| IDENTITY | Thường bị hạn chế/vô hiệu hóa với Hibernate insert batching | Cần lấy generated key ngay |
| SEQUENCE | Thường phù hợp | Sequence allocation và preallocation |
| Application-assigned ID | Phù hợp | Đảm bảo unique và retry stable |
| UUID generated in application | Phù hợp | Index/storage trade-off |
| TABLE generator | Có thể có overhead cạnh tranh khóa | Generator table có thể trở thành bottleneck |

Nếu batching không có hiệu quả dù đã cấu hình, kiểm tra identifier strategy trước khi tăng batch size.

## 6. Mapping entity cho import

Ví dụ dữ liệu sản phẩm nhập từ file đối tác:

~~~java
@Entity
@Table(
    name = "catalog_items",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_catalog_source_key",
        columnNames = {"source_system", "source_key"}
    )
)
public class CatalogItem {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "catalog_item_seq"
    )
    @SequenceGenerator(
        name = "catalog_item_seq",
        sequenceName = "catalog_item_seq",
        allocationSize = 50
    )
    private Long id;

    @Column(name = "source_system", nullable = false, length = 40)
    private String sourceSystem;

    @Column(name = "source_key", nullable = false, length = 120)
    private String sourceKey;

    @Column(nullable = false, length = 240)
    private String name;

    @Column(nullable = false, precision = 19, scale = 4)
    private BigDecimal price;

    @Version
    private long version;

    protected CatalogItem() {}

    public CatalogItem(
            String sourceSystem,
            String sourceKey,
            String name,
            BigDecimal price) {
        this.sourceSystem = sourceSystem;
        this.sourceKey = sourceKey;
        this.name = name;
        this.price = price;
    }
}
~~~

Unique key theo nguồn là nền tảng cho idempotency: cùng một record đối tác không được tạo thành nhiều catalog items khi job chạy lại.

### 6.1. Tạo business key ổn định

Không dùng line number trong file làm unique key nếu file có thể được sắp xếp lại. Tốt hơn là dùng source system, external record ID, version hoặc event ID nếu nguồn gửi các thay đổi, và import batch ID khi nghiệp vụ cần lưu từng lần import.

Business key phải có semantics ổn định qua restart và re-delivery.

### 6.2. Validate trước khi persist

Không đợi database báo lỗi cho mọi dữ liệu sai. Kiểm tra format, required fields, độ dài, decimal scale, enum values và business rules trước khi tạo entity. Database constraints vẫn cần để bảo vệ integrity trước concurrent writers.

## 7. Flush và clear theo batch

Ví dụ cơ bản:

~~~java
@Transactional
public void persistChunk(List<CatalogRow> rows) {
    int flushInterval = 50;

    for (int i = 0; i < rows.size(); i++) {
        entityManager.persist(toEntity(rows.get(i)));

        if ((i + 1) % flushInterval == 0) {
            entityManager.flush();
            entityManager.clear();
        }
    }

    entityManager.flush();
    entityManager.clear();
}
~~~

Ở đây method nhận một chunk và flush/clear mỗi 50 entities. Nếu chunk có 1.000 records, persistence context không giữ toàn bộ 1.000 managed entities cùng lúc.

### 7.1. flush() làm gì?

`entityManager.flush()` yêu cầu persistence provider đồng bộ pending changes của persistence context với database thông qua JDBC. Với batching, các statement tương thích có thể được gom và execute theo batch.

Flush có thể phát INSERT cho entities mới, UPDATE cho managed entities dirty, DELETE cho entities bị remove, collection table/join table updates và SQL phụ thuộc cascade/mapping.

Flush không phải commit. SQL có thể đã chạy nhưng transaction vẫn rollback được.

### 7.2. clear() làm gì?

`entityManager.clear()` detach toàn bộ managed entities trong persistence context. Hibernate không còn giữ chúng như managed state của context hiện tại.

Sau clear:

- Entity Java references vẫn tồn tại nếu code còn giữ.
- Các entity đó trở thành detached.
- Lazy associations chưa load có thể không truy cập được ngoài Session.
- Thay đổi tiếp theo trên detached object không tự được dirty-check.
- Muốn tiếp tục quản lý cần load lại hoặc merge theo use case.

### 7.3. Luôn flush trước clear

Nếu clear trước flush, pending changes có thể bị detach khỏi persistence context và không được đồng bộ. Thứ tự an toàn:

~~~java
entityManager.flush();
entityManager.clear();
~~~

### 7.4. Không clear khi còn cần managed references

~~~java
CatalogItem item = entityManager.find(CatalogItem.class, id);
entityManager.clear();

item.rename("New name");
// item detached; mutation không tự được persist.
~~~

Sau clear, cần dùng transaction/persistence context mới hoặc merge có chủ đích. Trong bulk import, tốt nhất xử lý xong một nhóm entity, flush, clear và không giữ reference cũ để sửa tiếp.

### 7.5. flush/clear không thay transaction boundary

Có thể flush/clear nhiều lần trong một transaction dài. Điều đó giảm persistence-context memory nhưng không giải phóng database locks hoặc kết thúc transaction. Nếu transaction kéo dài một giờ, lock/snapshot/connection có thể vẫn được giữ một giờ.

## 8. Một chunk nên là một transaction như thế nào?

Có hai mô hình thường gặp.

### Mô hình A: một transaction cho toàn bộ job

~~~java
@Transactional
public void importEverything(List<CatalogRow> rows) {
    for (CatalogRow row : rows) {
        entityManager.persist(toEntity(row));
        // Có thể flush/clear theo interval.
    }
}
~~~

Ưu điểm:

- Atomicity toàn job: hoặc tất cả commit, hoặc tất cả rollback.
- Đơn giản về checkpoint.
- Không có trạng thái import một phần nếu rollback thực sự bao phủ mọi writes.

Nhược điểm:

- Transaction rất dài.
- Giữ connection lâu.
- Locks và MVCC snapshots kéo dài.
- Rollback sau nhiều giờ có thể tốn kém.
- Không thể restart từ chunk đã xử lý vì chưa commit.
- Nếu process chết, toàn bộ job có thể phải chạy lại.

Flush/clear không làm transaction này ngắn hơn.

### Mô hình B: transaction riêng cho mỗi chunk

~~~text
Chunk 1: BEGIN -> write -> flush -> COMMIT
Chunk 2: BEGIN -> write -> flush -> COMMIT
Chunk 3: BEGIN -> write -> flush -> COMMIT
...
~~~

Ưu điểm: transaction ngắn và bounded; mỗi chunk commit độc lập; có thể checkpoint sau từng commit; retry chỉ cần chunk chưa commit; lock duration và rollback cost nhỏ hơn.

Nhược điểm: job có thể hoàn thành một phần; cần restart/checkpoint/idempotency; các chunk không còn atomic với nhau; business rules cần dữ liệu toàn job phải được thiết kế lại hoặc xử lý ở bước finalize.

Với import lớn, transaction per chunk thường thực tế hơn nếu domain cho phép partial progress.

### 8.1. Spring proxy và transaction boundary

Không nên gọi method có `@Transactional` qua self-invocation rồi nghĩ mỗi lần gọi tạo transaction mới. Spring proxy-based transaction thường không intercept lời gọi nội bộ cùng instance.

Một thiết kế rõ ràng là đặt chunk writer ở bean riêng:

~~~java
@Service
public class CatalogChunkWriter {

    @Transactional
    public void writeChunk(List<CatalogRow> rows) {
        // persist + flush + clear
    }
}
~~~

Job coordinator gọi bean này một lần cho mỗi chunk. Mỗi lời gọi qua Spring proxy có thể tạo/commit transaction theo propagation phù hợp.

### 8.2. Không dùng REQUIRES_NEW như mẹo mà không hiểu outer transaction

`Propagation.REQUIRES_NEW` tạo transaction độc lập, tạm suspend transaction ngoài. Nếu outer transaction vẫn giữ connection/locks trong khi inner transaction lấy connection khác, pool nhỏ có thể cạn connection hoặc deadlock ở tầng application. Ưu tiên thiết kế coordinator không mở transaction bao trùm toàn job.

## 9. Thiết kế chunk writer bằng Spring

Ví dụ writer:

~~~java
@Service
public class CatalogChunkWriter {

    private static final int FLUSH_INTERVAL = 50;

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void writeChunk(List<CatalogRow> rows) {
        int count = 0;

        for (CatalogRow row : rows) {
            entityManager.persist(toEntity(row));
            count++;

            if (count % FLUSH_INTERVAL == 0) {
                entityManager.flush();
                entityManager.clear();
            }
        }

        entityManager.flush();
        entityManager.clear();
    }

    private CatalogItem toEntity(CatalogRow row) {
        return new CatalogItem(
            row.sourceSystem(),
            row.sourceKey(),
            row.name(),
            row.price()
        );
    }
}
~~~

Chunk coordinator:

~~~java
@Service
public class CatalogImportJob {

    private final CatalogChunkWriter writer;
    private final CatalogSource source;

    public CatalogImportJob(
            CatalogChunkWriter writer,
            CatalogSource source) {
        this.writer = writer;
        this.source = source;
    }

    public void runImport(String jobId) {
        while (true) {
            List<CatalogRow> chunk = source.nextChunk(jobId, 1000);

            if (chunk.isEmpty()) {
                break;
            }

            writer.writeChunk(chunk);
            // Cần ghi checkpoint atomic với chunk data;
            // phần sau trình bày cách làm.
        }
    }
}
~~~

Đây là skeleton để giải thích boundary. Trong production, checkpoint không nên được ghi bởi source theo kiểu không có atomicity với DB commit; cần một transaction/resource design như phần sau.

## 10. Checkpoint phải gắn với chunk đã commit

Giả sử job có 100 chunks. Chunk 1–40 đã commit. Khi chunk 41 commit thành công, process chết trước khi checkpoint ghi nhận 41. Khi restart, coordinator vẫn nghĩ đã hoàn thành tới 40 và chạy lại chunk 41.

Đây là **at-least-once processing**: một chunk có thể được gửi lại. Muốn chạy lại an toàn, writes phải idempotent.

### 10.1. Checkpoint theo source offset

Một checkpoint có thể lưu:

~~~sql
CREATE TABLE import_job (
    job_id              VARCHAR(80) PRIMARY KEY,
    source_name         VARCHAR(120) NOT NULL,
    status              VARCHAR(20) NOT NULL,
    last_committed_key  VARCHAR(200),
    committed_chunks    BIGINT NOT NULL DEFAULT 0,
    processed_records   BIGINT NOT NULL DEFAULT 0,
    updated_at          TIMESTAMP NOT NULL
);
~~~

`last_committed_key` cần phản ánh vị trí input ổn định: event sequence, source ID hoặc composite key. File offset chỉ ổn định khi file immutable và encoding/record framing được xác định.

### 10.2. Ghi checkpoint cùng transaction với dữ liệu

Nếu bảng target và checkpoint cùng database, tốt nhất ghi cả target rows và checkpoint trong **cùng một transaction**:

~~~text
BEGIN
  INSERT/UPDATE target records
  UPDATE import_job checkpoint
COMMIT
~~~

Khi transaction commit, cả dữ liệu và checkpoint cùng có hiệu lực. Khi rollback, cả hai cùng rollback.

Nếu checkpoint được ghi vào file/object storage hoặc database khác, không có atomicity tự nhiên. Khi đó phải chấp nhận at-least-once và thiết kế idempotency/deduplication; hoặc dùng transactional outbox/coordinator phù hợp.

### 10.3. Không ghi checkpoint trước khi dữ liệu commit

Sai thứ tự:

~~~text
save checkpoint = chunk 41
write target rows
process crashes
~~~

Restart sẽ bỏ qua chunk 41 dù target data chưa commit. Checkpoint phải được commit cùng dữ liệu hoặc sau khi xác nhận commit, với idempotency xử lý crash window.

### 10.4. Job lock và ownership

Hai worker không nên cùng chạy một jobId nếu không có cơ chế partition/lease. Có thể lưu status, owner/worker ID, lease expiry, heartbeat, attempt number và last committed source key.

Dùng optimistic locking/atomic claim để tránh hai coordinator cùng nhận một chunk.

## 11. Idempotency: nền tảng của restart an toàn

Một import có thể chạy lại cùng record vì process chết sau commit trước checkpoint, message queue redelivery, scheduler chạy trùng, operator bấm restart, network timeout khiến client không biết commit đã thành công hoặc chunk retry sau deadlock/serialization failure.

Nếu mỗi lần chạy đều INSERT mới, duplicate rows sẽ xuất hiện.

### 11.1. Unique business key

Ví dụ:

~~~sql
ALTER TABLE catalog_items
ADD CONSTRAINT uk_catalog_source_key
UNIQUE (source_system, source_key);
~~~

Cùng source key không thể tạo hai rows. Nhưng unique constraint chỉ ngăn duplicate; nó không tự quyết định update existing row hay bỏ qua record.

### 11.2. Chọn semantics khi record đã tồn tại

| Policy | Hành vi | Phù hợp |
| --- | --- | --- |
| Insert-only | Duplicate key là lỗi | Input phải unique; duplicate là data corruption |
| Ignore duplicate | Giữ row đã có | Event immutable, replay chỉ cần dedupe |
| Upsert | Update theo business key | Source gửi snapshot hiện tại |
| Version-aware upsert | Chỉ nhận source version mới hơn | Event có ordering/version |
| Append-only | Mỗi event có event ID riêng | Event history/audit |

Policy phải do domain quyết định. Không dùng generic save/merge rồi hy vọng provider tự hiểu business upsert.

### 11.3. Upsert ở database

PostgreSQL ví dụ:

~~~sql
INSERT INTO catalog_items (
    source_system, source_key, name, price
)
VALUES (
    :source_system, :source_key, :name, :price
)
ON CONFLICT (source_system, source_key)
DO UPDATE SET
    name = EXCLUDED.name,
    price = EXCLUDED.price
WHERE catalog_items.source_version < :source_version;
~~~

Cú pháp và semantics upsert khác nhau theo database. Native upsert có thể hiệu quả hơn SELECT-then-INSERT nhưng bypass một số Hibernate lifecycle callbacks, cascades, automatic version handling và persistence-context synchronization. Sau native DML, cần clear/refresh entities bị ảnh hưởng hoặc dùng persistence context mới.

### 11.4. Version-aware processing

Nếu source gửi version/sequence:

~~~text
source_key = ITEM-42
source_version = 18
payload = ...
~~~

Chỉ apply nếu version mới hơn version đang lưu. Điều này ngăn message cũ được redeliver sau message mới và ghi đè dữ liệu mới hơn.

## 12. Upsert qua JPA/Hibernate: SELECT rồi persist/merge

Một cách đơn giản:

~~~java
CatalogItem existing = repository
    .findBySourceSystemAndSourceKey(
        row.sourceSystem(),
        row.sourceKey()
    )
    .orElse(null);

if (existing == null) {
    entityManager.persist(toEntity(row));
} else {
    existing.updateFrom(row);
}
~~~

Cách này dễ tích hợp domain methods nhưng có thể tạo một SELECT cho mỗi record và gặp race condition:

1. Worker A SELECT thấy chưa có.
2. Worker B SELECT cũng thấy chưa có.
3. Cả hai INSERT.
4. Một worker vi phạm unique constraint.

Cần unique constraint ở database và chiến lược xử lý conflict. Nếu dữ liệu lớn, có thể preload existing keys theo chunk hoặc dùng database upsert.

### 12.1. persist() và merge() không giống upsert

- `persist()` đăng ký transient entity mới để insert.
- `merge()` copy state từ detached object vào managed instance và trả về managed instance.
- `merge()` không phải native atomic upsert theo unique business key.
- `save()` của Spring Data JPA chọn persist/merge dựa trên entity new-state detection; nó không tự đảm bảo idempotency theo external key.

Đừng dùng merge cho hàng triệu detached entities mà không đo SELECT/merge cost và persistence-context behavior.

## 13. Xử lý lỗi trong một chunk

Giả sử chunk 1.000 records có một record vi phạm unique constraint.

Nếu tất cả ghi trong một transaction và constraint được kiểm tra ngay khi INSERT/flush, transaction có thể bị đánh dấu rollback-only hoặc trở thành failed. Tiếp tục ghi trong cùng transaction thường không an toàn.

### 13.1. Fail-fast cả chunk

- Rollback chunk.
- Ghi lỗi và chunk key/attempt.
- Sửa input hoặc xử lý theo retry policy.
- Restart chunk từ đầu.
- Idempotency giúp tránh duplicate nếu commit outcome không chắc.

Đây là lựa chọn phù hợp khi chunk phải atomic.

### 13.2. Reject record riêng

Nếu yêu cầu giữ records hợp lệ và cách ly records lỗi, không nên chỉ catch exception quanh từng persist rồi tiếp tục cùng transaction. Database transaction có thể đã aborted.

Có thể validate trước khi ghi, ghi reject records vào bảng quarantine riêng, tách record lỗi ra rồi retry chunk hợp lệ trong transaction mới, dùng savepoint/JDBC strategy khi DB/driver và transaction manager hỗ trợ, hoặc dùng Spring Batch skip/retry policies với transaction semantics đã hiểu.

### 13.3. Không swallow exception rồi commit

Sai:

~~~java
try {
    entityManager.flush();
} catch (Exception ex) {
    log.warn("Import failed", ex);
}
// Tiếp tục và trả success.
~~~

Flush failure có thể khiến transaction không còn usable. Không báo job success khi transaction rollback hoặc trạng thái commit chưa xác định.

## 14. Retry chỉ với lỗi phù hợp

| Nhóm lỗi | Ví dụ | Chính sách |
| --- | --- | --- |
| Transient database | Deadlock, serialization failure, temporary connection issue | Rollback và retry chunk có giới hạn |
| Constraint/data error | Not-null, FK, unique violation do input | Không retry nguyên trạng; reject/fix/dedupe |
| Mapping/programming | Invalid enum conversion, wrong column mapping | Fail job và sửa code |
| Optimistic conflict | Version mismatch | Re-read/reconcile theo domain |
| Unknown commit outcome | Connection lost trong/near commit | Replay idempotently và xác minh DB state |
| Source failure | File unavailable, API timeout | Retry read theo source policy |
| Resource exhaustion | DB pool exhausted, heap pressure | Backoff, giảm concurrency/chunk hoặc stop |

### 14.1. Exponential backoff và jitter

Ví dụ thời gian chờ tăng dần:

~~~text
attempt 1: 200 ms
attempt 2: 400 ms
attempt 3: 800 ms
attempt 4: 1600 ms
~~~

Thêm jitter để nhiều workers không retry cùng lúc. Giới hạn số attempts và tổng retry duration.

### 14.2. Retry transaction mới

Sau deadlock/serialization failure, rollback transaction lỗi và mở transaction mới. Không cố tiếp tục dùng EntityManager/Session trong transaction đã failed.

### 14.3. Không retry lỗi vĩnh viễn

Nếu record có giá trị bắt buộc null, retry 10 lần không sửa được dữ liệu. Phân loại exception theo SQLState/vendor code và domain validation.

## 15. Restart bằng checkpoint keyset

Với input database/source có monotonic key, có thể đọc:

~~~sql
SELECT source_id, source_key, name, price, source_version
FROM incoming_catalog
WHERE source_id > :last_source_id
ORDER BY source_id
LIMIT :chunk_size;
~~~

Checkpoint lưu last_source_id.

### 15.1. Keyset tốt hơn offset cho job dài

Offset pagination:

~~~sql
SELECT ...
FROM incoming_catalog
ORDER BY source_id
LIMIT 1000 OFFSET 900000;
~~~

có thể phải scan/skip nhiều rows khi offset lớn và dễ lệch khi source thay đổi. Keyset dùng điều kiện source_id > last_id, thường phù hợp hơn với thứ tự ổn định và index.

### 15.2. Source phải ổn định

Nếu records mới được thêm trong lúc import, cần xác định job có lấy cả records mới không. Có thể chốt high-water mark khi bắt đầu:

~~~sql
SELECT MAX(source_id) FROM incoming_catalog;
~~~

Sau đó mỗi chunk đọc trong khoảng:

~~~sql
WHERE source_id > :last_id
  AND source_id <= :high_water_mark
ORDER BY source_id
LIMIT :chunk_size;
~~~

Nếu source records có thể bị update/delete trong khi job chạy, cần snapshot, immutable staging table hoặc version/change tracking.

### 15.3. Checkpoint composite key

Nếu ordering theo (created_at, source_id):

~~~sql
WHERE created_at > :last_created_at
   OR (
       created_at = :last_created_at
       AND source_id > :last_source_id
   )
ORDER BY created_at, source_id
LIMIT :chunk_size;
~~~

Checkpoint phải lưu cả hai phần của sort key.

## 16. Transactional checkpoint trong cùng database

Có thể lưu checkpoint theo job:

~~~sql
CREATE TABLE import_job (
    job_id VARCHAR(80) PRIMARY KEY,
    status VARCHAR(20) NOT NULL,
    last_source_id BIGINT NOT NULL DEFAULT 0,
    high_water_mark BIGINT NOT NULL,
    processed_count BIGINT NOT NULL DEFAULT 0,
    rejected_count BIGINT NOT NULL DEFAULT 0,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    version BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMP NOT NULL
);
~~~

Chunk writer cập nhật dữ liệu và checkpoint cùng transaction:

~~~java
@Transactional
public void writeChunkAndCheckpoint(
        String jobId,
        List<IncomingRow> rows,
        long nextSourceId) {

    for (IncomingRow row : rows) {
        entityManager.persist(toEntity(row));
    }

    entityManager.flush();
    entityManager.clear();

    ImportJob job = entityManager.find(ImportJob.class, jobId);
    job.advanceTo(nextSourceId, rows.size());
}
~~~

Ví dụ trên cần lưu ý: sau clear(), mọi entity đã load trước đó đều detached. Ở đây job được load sau clear để cập nhật checkpoint. Trước khi transaction commit, Hibernate flush checkpoint update tự động hoặc explicit flush.

### 16.1. Checkpoint phải tăng theo thứ tự đã xử lý

Nếu chunk có source IDs 101–200, checkpoint có thể tăng tới 200 chỉ khi mọi records trong range đã được xử lý theo policy. Nếu bỏ qua invalid records, checkpoint vẫn có thể đi qua chúng nếu reject record đã được ghi bền vững trong cùng transaction.

### 16.2. Không lưu checkpoint chỉ theo số lượng

processed_count=5000 không xác định record nào đã xử lý nếu input thay đổi hoặc có gaps. Lưu source key/offset có nghĩa, kèm count để quan sát.

### 16.3. Optimistic locking cho checkpoint

Nếu nhiều workers có thể cập nhật cùng job, dùng version/conditional update hoặc row lock. Không để hai worker ghi đè checkpoint lùi về giá trị cũ.

## 17. Bản ghi reject/quarantine

~~~sql
CREATE TABLE import_reject (
    job_id VARCHAR(80) NOT NULL,
    source_key VARCHAR(200) NOT NULL,
    error_code VARCHAR(80) NOT NULL,
    error_message VARCHAR(1000),
    payload_reference VARCHAR(500),
    rejected_at TIMESTAMP NOT NULL,
    PRIMARY KEY (job_id, source_key)
);
~~~

Có thể lưu raw payload trong storage riêng và chỉ lưu reference/hash trong database để tránh bảng reject quá lớn hoặc lưu PII không cần thiết.

### 17.1. Reject phải idempotent

Nếu cùng một invalid source record được đọc lại, không nên tạo hàng reject vô hạn. Dùng unique key (job_id, source_key) hoặc event ID.

### 17.2. Phân biệt rejected và skipped

- REJECTED: record không hợp lệ và đã được ghi nhận.
- SKIPPED_DUPLICATE: record đã được xử lý trước theo policy.
- PROCESSED: record được ghi thành công.
- RETRY_PENDING: chưa hoàn thành, có thể retry.
- FAILED_PERMANENT: lỗi không thể tự phục hồi.

Status rõ ràng giúp operator biết có thể restart toàn job hay cần sửa dữ liệu trước.

## 18. Spring Batch và chunk-oriented processing

Với import lớn, Spring Batch cung cấp mô hình chunk-oriented processing:

~~~text
ItemReader -> ItemProcessor -> ItemWriter
                   |
                 chunk
                   |
             transaction commit
~~~

Một step có thể cấu hình chunk size và transaction manager:

~~~java
@Bean
Step importCatalogStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<CatalogRow> reader,
        ItemProcessor<CatalogRow, CatalogItem> processor,
        ItemWriter<CatalogItem> writer) {

    return new StepBuilder("importCatalog", jobRepository)
        .<CatalogRow, CatalogItem>chunk(1000, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .build();
}
~~~

Đây là skeleton theo Spring Batch generation hiện đại; constructor/configuration cụ thể tùy version. Spring Batch quản lý chunk transactions, job/step execution metadata và restart mechanisms theo cấu hình.

### 18.1. Spring Batch không tự biến JPA writer thành JDBC batch tối ưu

Nếu writer gọi repository.save() từng entity, cần hiểu Hibernate JDBC batching có được bật và SQL shape có gom được không. JPA writer cần quản lý flush/clear để persistence context không tăng vô hạn trong chunk lớn.

### 18.2. Chunk size của Spring Batch khác Hibernate batch size

~~~text
Spring Batch chunk size = 1,000
Hibernate JDBC batch size = 50
~~~

Một chunk transaction xử lý 1.000 items; Hibernate có thể gửi nhiều JDBC batches bên trong transaction.

### 18.3. Retry/skip policy

Spring Batch hỗ trợ retry và skip theo exception classification. Cần phân loại exception rõ ràng, giới hạn attempts và bảo đảm writer idempotent khi chunk được replay.

### 18.4. Restart metadata và external side effects

Spring Batch lưu job/step execution state trong JobRepository. Nếu writer còn gửi email, gọi API hoặc publish message, các side effects đó không tự atomic với database chunk transaction. Dùng outbox/idempotency keys hoặc thiết kế delivery riêng.

## 19. JPA batching và JDBC batching trực tiếp

Hibernate JDBC batching phù hợp khi cần ORM lifecycle, mapping, cascades và managed entities.

Nếu import cực lớn, schema đơn giản và không cần entity lifecycle, JDBC batch trực tiếp có thể giảm ORM overhead:

~~~java
jdbcTemplate.batchUpdate(
    """
    INSERT INTO catalog_items
        (source_system, source_key, name, price)
    VALUES (?, ?, ?, ?)
    """,
    rows,
    500,
    (ps, row) -> {
        ps.setString(1, row.sourceSystem());
        ps.setString(2, row.sourceKey());
        ps.setString(3, row.name());
        ps.setBigDecimal(4, row.price());
    }
);
~~~

### 19.1. JDBC batch vẫn cần transaction

Gọi batchUpdate không tự quyết định transaction boundary. Bọc chunk trong transaction manager phù hợp nếu cần atomicity của chunk.

### 19.2. JDBC bypass persistence context

Sau JDBC/native DML, các entities đã managed trong cùng persistence context có thể stale. Nếu dùng chung context, clear/refresh các affected entities trước khi đọc lại.

### 19.3. Không dùng JPA và JDBC cùng lúc mà bỏ qua ordering

Nếu cùng transaction vừa persist entity bằng JPA vừa batch insert/update cùng bảng bằng JDBC, flush order và persistence-context state cần được kiểm soát. Flush ORM trước khi JDBC cần thấy các pending changes; clear/refresh sau JDBC nếu managed entities có thể bị ảnh hưởng.

### 19.4. Chọn công cụ theo semantics

| Yêu cầu | Cách tiếp cận |
| --- | --- |
| Domain callbacks, cascades, entity validation | Hibernate/JPA batching |
| Bảng đơn giản, import rất lớn, SQL kiểm soát rõ | JDBC batch |
| Database-specific upsert/bulk merge | Native SQL/JDBC |
| Job restart/skip/retry/chunk metadata | Spring Batch hoặc coordinator tương đương |
| Không cần persistence context/ORM lifecycle | JDBC hoặc Hibernate StatelessSession |

## 20. StatelessSession cho bulk workloads

Hibernate StatelessSession không duy trì persistence context/automatic dirty checking như Session thông thường:

~~~java
try (StatelessSession session =
         sessionFactory.openStatelessSession()) {

    Transaction tx = session.beginTransaction();

    try {
        for (CatalogRow row : rows) {
            session.insert(toEntity(row));
        }
        tx.commit();
    } catch (RuntimeException ex) {
        tx.rollback();
        throw ex;
    }
}
~~~

StatelessSession có thể giảm persistence-context memory nhưng bỏ nhiều semantics như identity map, cascades và collection management theo cách Session thông thường. Cần kiểm tra API batch behavior và transaction integration theo Hibernate version.

Không chọn StatelessSession chỉ vì tên có chữ stateless. Nếu workload cần aggregate invariants, lifecycle callbacks, Envers hoặc cascade behavior, kiểm tra xem những cơ chế đó có còn hoạt động như mong muốn hay không.

## 21. Xử lý duplicate và concurrency giữa nhiều job

Unique constraint là lớp bảo vệ cuối cùng khi hai worker cùng import một business key.

### 21.1. Claim job atomically

Ví dụ cập nhật status chỉ khi chưa có worker claim:

~~~sql
UPDATE import_job
SET status = 'RUNNING',
    owner_id = :worker_id,
    lease_until = :lease_until,
    version = version + 1
WHERE job_id = :job_id
  AND status IN ('READY', 'RESTARTABLE');
~~~

Kiểm tra affected rows. Nếu bằng 0, worker không sở hữu job và không được tiếp tục.

### 21.2. Lease expiry

Nếu worker chết, lease hết hạn để worker khác có thể claim. Lease cần heartbeat và thời gian đủ dài cho chunk. Tránh hai worker cùng nghĩ mình sở hữu job sau pause/GC/network partition; fencing token/version giúp từ chối worker cũ.

### 21.3. Concurrent imports cùng source key

Có thể serialize theo source system/job, partition input theo business key, dùng unique constraints + upsert, dùng optimistic version hoặc database lock/claim rows.

Không chỉ dựa vào SELECT-then-INSERT vì race condition.

## 22. Memory, transaction duration và chunk size

Chunk size cần cân bằng nhiều chi phí:

| Chunk nhỏ | Chunk lớn |
| --- | --- |
| Transaction ngắn | Ít commit hơn |
| Rollback ít records | Rollback tốn hơn |
| Checkpoint thường xuyên | Ít checkpoint hơn |
| Overhead commit tăng | Lock duration tăng |
| Ít memory mỗi chunk | Có thể tăng memory/driver buffers |
| Restart ít phải replay | Replay chunk lớn hơn |

### 22.1. Flush/clear interval có thể nhỏ hơn chunk size

Ví dụ:

~~~text
Chunk size: 2,000
JDBC batch size: 50
flush/clear interval: 200
Transaction: 2,000 records
~~~

Trong một transaction, có thể flush/clear mỗi 200 entities, rồi commit sau 2.000. Điều này giới hạn persistence context nhưng không giới hạn transaction size.

### 22.2. Đừng clear quá thường xuyên một cách máy móc

Mỗi clear detach toàn bộ entities. Nếu cần relationship references hoặc managed parent trong cùng chunk, clear giữa chừng có thể làm code khó hơn và khiến associations detached.

Thiết kế chunk để mỗi record có thể được xử lý độc lập hoặc chỉ giữ IDs/DTOs giữa các intervals.

### 22.3. Theo dõi heap và GC

Metrics nên có heap used/committed, allocation rate, GC pause/time, managed entity count/first-level context growth nếu đo được, JDBC batch execution count, chunk processing duration, transaction duration, connection pool active/pending và rows/second/records/second.

Không chọn chunk size chỉ dựa trên số rows. Entity graph nặng và payload JSON lớn có memory profile khác entity nhỏ.

## 23. Validation và database constraints

Validation nên chia hai lớp.

### 23.1. Application validation

Trước persist, kiểm tra required fields, length/format, decimal precision/scale, enum mapping, referential business rules, source version monotonicity, duplicate source key trong chunk và normalization/canonicalization.

### 23.2. Database constraints

Database vẫn cần NOT NULL, UNIQUE, FOREIGN KEY, CHECK và indexes. Application validation cải thiện error reporting; DB constraints bảo vệ dữ liệu trước race conditions và các writer khác.

### 23.3. Không SELECT từng reference cho từng record

Nếu mỗi row cần kiểm tra một category/customer, SELECT mỗi record sẽ tạo N+1 ở phía import. Có thể preload reference IDs theo chunk, dùng cache bounded hoặc join staging data trong SQL. Tránh preload toàn bộ bảng lớn vào heap.

## 24. Import qua staging table

Với dataset rất lớn hoặc cần reconciliation, staging table có thể đơn giản hóa pipeline.

~~~text
Raw file/API
    |
    v
Staging rows (source key, raw values, job id)
    |
    v
Validate / deduplicate / normalize
    |
    v
INSERT ... SELECT / MERGE / UPSERT
    |
    v
Target tables
    |
    v
Checkpoint + reject report
~~~

Ưu điểm: có thể load raw rows bằng bulk loader/CSV COPY; validation/reconciliation thực hiện bằng SQL set-based; dễ tìm duplicate/missing references; tách raw source khỏi target domain schema; có thể restart từng phase.

Nhược điểm: cần cleanup/retention policy; staging data có thể chứa PII/sensitive fields; native merge/upsert phụ thuộc database; cần unique keys và job isolation.

Với hàng triệu rows, database-native bulk loading (ví dụ PostgreSQL COPY hoặc công cụ tương ứng) có thể nhanh hơn ORM batching nhiều lần. Hibernate không phải công cụ tối ưu cho mọi ETL workload.

## 25. Ghi tiến độ và observability

Một job import nên log theo job/chunk, không log từng row ở INFO.

~~~text
job=CATALOG-2026-11
chunk=42
source_from=41001
source_to=42000
read=1000
processed=997
rejected=3
inserted=750
updated=247
duration_ms=1840
jdbc_batches=20
status=COMMITTED
~~~

### 25.1. Metrics

| Metric | Ý nghĩa |
| --- | --- |
| import_records_read_total | Input records đã đọc |
| import_records_processed_total | Records thành công |
| import_records_rejected_total | Records bị reject |
| import_chunks_committed_total | Chunks commit thành công |
| import_chunk_duration_seconds | Thời gian mỗi chunk |
| import_records_per_second | Throughput |
| import_retry_total | Số lần retry |
| import_batch_failure_total | Batch failures |
| import_checkpoint_lag | Khoảng cách tới high-water mark |
| jdbc_batch_execute_total | JDBC batches thực thi |
| db_connection_wait_seconds | Chờ connection |
| heap_used_bytes | Memory pressure |

Tránh labels có cardinality cao như raw source key, order ID hoặc payload. Dùng job ID trong logs/traces; metrics labels nên là source type/status/operation có tập giá trị hữu hạn.

### 25.2. Phân biệt commit time và processing time

Chunk có thể mất 1 giây để parse/map và 4 giây để flush/commit. Đo từng phase giúp xác định bottleneck là source, validation, Hibernate, JDBC, database lock hay commit.

### 25.3. Checkpoint lag

Nếu source phát 10.000 events/phút nhưng import chỉ commit 6.000 records/phút, lag tăng. Theo dõi lag theo source offset/time để cảnh báo trước khi backlog quá lớn.

## 26. Một coordinator có checkpoint rõ ràng

Mô hình code khái quát với checkpoint cùng database:

~~~java
@Service
public class CatalogImportCoordinator {

    private final ImportReader reader;
    private final CatalogChunkWriter writer;

    public CatalogImportCoordinator(
            ImportReader reader,
            CatalogChunkWriter writer) {
        this.reader = reader;
        this.writer = writer;
    }

    public void run(String jobId) {
        while (true) {
            ImportChunk chunk = reader.readNext(jobId, 1000);

            if (chunk.rows().isEmpty()) {
                writer.markCompleted(jobId);
                return;
            }

            writer.writeChunkAndCheckpoint(
                jobId,
                chunk.rows(),
                chunk.lastSourceId()
            );
        }
    }
}
~~~

Coordinator không mở transaction bao trùm toàn job. Reader lấy checkpoint đã commit, chunk writer ghi target rows và checkpoint trong cùng transaction.

### 26.1. Race condition giữa read và claim

Nếu chỉ có một worker/job, ví dụ trên có thể đủ. Nếu nhiều worker, việc đọc checkpoint rồi write cần claim/lease hoặc atomic partition assignment. Nếu không, hai workers có thể đọc cùng chunk.

### 26.2. Reader consistency

Nếu source và target cùng database nhưng query reader nằm ngoài transaction của writer, input có thể thay đổi giữa read và write. Dùng immutable input, high-water mark hoặc staging snapshot để xác định tập dữ liệu của job.

### 26.3. Mark completed

Chỉ mark COMPLETED khi checkpoint đạt high-water mark và mọi rejected records đã được xử lý theo policy. Có thể có trạng thái COMPLETED_WITH_REJECTS để operator phân biệt.

## 27. Checklist thiết kế import job

- [ ] Input có stable key/order hoặc immutable snapshot.
- [ ] Chunk size được xác định bằng benchmark.
- [ ] Hibernate JDBC batch size được cấu hình và đo.
- [ ] Identifier strategy cho phép insert batching.
- [ ] Envers/cascade/lifecycle requirements đã được tính đến.
- [ ] flush() trước clear().
- [ ] Persistence context được giới hạn theo interval.
- [ ] Transaction boundary rõ: per chunk hay whole job.
- [ ] Không dựa vào self-invocation để tạo transaction mới.
- [ ] Checkpoint chỉ tiến sau khi target data commit.
- [ ] Target data và checkpoint cùng transaction nếu cùng DB.
- [ ] Unique business key/idempotency policy được định nghĩa.
- [ ] Retry chỉ transient failures, có backoff/jitter/max attempts.
- [ ] Failed transaction không được tiếp tục sử dụng.
- [ ] Reject/quarantine có schema và idempotency.
- [ ] Job ownership/lease xử lý duplicate workers.
- [ ] Restart kiểm thử sau process crash và unknown commit outcome.
- [ ] JDBC/DB metrics, heap, GC và chunk latency được theo dõi.
- [ ] Có cleanup/retention cho staging/reject/checkpoint data.
- [ ] Có runbook cho pause, retry, restart và manual reconciliation.

## 28. Bài tập thực hành

### Bài 1 — Phân biệt batch và chunk

Một job xử lý 120.000 records, chunk size 1.200, Hibernate JDBC batch size 60. Ước lượng số chunks và số JDBC batches cho một SQL shape đồng nhất.

### Bài 2 — flush và clear

Vì sao gọi flush() mỗi 100 records nhưng không clear() vẫn có thể làm persistence context tăng memory tới cuối chunk/job?

### Bài 3 — clear trước flush

Điều gì có thể xảy ra nếu gọi entityManager.clear() trước khi flush các pending inserts?

### Bài 4 — Flush không phải commit

Một chunk đã flush thành công rồi process ném exception trước commit. Database state sẽ thế nào nếu transaction rollback đúng?

### Bài 5 — Transaction boundary

So sánh một transaction cho toàn job với transaction per chunk về locks, rollback cost, checkpoint và restart.

### Bài 6 — IDENTITY

Vì sao IDENTITY có thể làm Hibernate INSERT batching bị vô hiệu hóa hoặc hạn chế? Strategy nào nên benchmark thay thế?

### Bài 7 — SEQUENCE allocation

Mapping sequence có allocationSize 50. Điều gì cần căn chỉnh với database sequence? Vì sao ID có gaps sau rollback không phải lỗi?

### Bài 8 — order_inserts

`hibernate.order_inserts=true` giúp gì? Vì sao không được dựa vào SQL order tình cờ để đảm bảo business order?

### Bài 9 — Batch versioned data

Vì sao batch updates có @Version cần kiểm tra JDBC driver row-count semantics?

### Bài 10 — Spring self-invocation

Một method @Transactional gọi method @Transactional khác trong cùng class. Vì sao transaction per chunk có thể không được tạo như kỳ vọng?

### Bài 11 — Checkpoint crash window

Chunk đã commit nhưng process chết trước khi checkpoint được lưu ở external file. Restart nên xử lý thế nào?

### Bài 12 — Checkpoint ordering

Vì sao không được cập nhật last_source_id trước khi target rows commit?

### Bài 13 — Idempotency

Thiết kế unique business key cho import catalog từ hai source systems có thể trùng external ID.

### Bài 14 — Upsert

So sánh SELECT-then-INSERT với database upsert về race condition, round-trips và Hibernate lifecycle.

### Bài 15 — merge()

Vì sao Spring Data save()/EntityManager.merge() không phải native upsert theo external business key?

### Bài 16 — Retry

Một chunk gặp deadlock. Mô tả retry đúng transaction lifecycle và backoff. Vì sao không retry validation error?

### Bài 17 — Reject records

Một record vi phạm unique constraint trong batch. Vì sao catch exception rồi tiếp tục cùng transaction có thể thất bại? Nêu chiến lược quarantine.

### Bài 18 — Keyset restart

Thiết kế checkpoint cho input được sort theo (created_at, source_id). Vì sao chỉ lưu created_at không đủ?

### Bài 19 — High-water mark

Một import cần xử lý snapshot input hiện tại nhưng source vẫn nhận records mới. Dùng high-water mark thế nào?

### Bài 20 — Spring Batch

Chunk size Spring Batch là 1.000, Hibernate batch size là 50. Hai cấu hình tác động ở những layer nào?

### Bài 21 — JDBC batch

Khi nào JDBC batch trực tiếp phù hợp hơn Hibernate? Sau native/JDBC writes, persistence context cần xử lý thế nào?

### Bài 22 — Staging table

Với 10 triệu rows và validation nhiều điều kiện, khi nào staging + set-based SQL đáng cân nhắc hơn ORM batching?

### Bài 23 — Concurrency

Hai workers cùng claim một job và xử lý cùng source range. Thiết kế lease/version/fencing để tránh duplicate processing.

### Bài 24 — Benchmark

Thiết kế benchmark thay đổi JDBC batch size 25/50/100 và chunk size 500/1.000/2.000. Nêu metrics và điều kiện giữ ổn định.

### Gợi ý đáp án

- **Bài 1:** 100 chunks; khoảng 20 JDBC batches/chunk, tổng khoảng 2.000 executions nếu một SQL shape và batch được lấp đầy.
- **Bài 2:** Flush đồng bộ SQL nhưng managed entities vẫn nằm trong first-level persistence context; clear mới detach và giải phóng references do context giữ.
- **Bài 3:** Pending changes có thể bị detach trước khi synchronize và không được ghi.
- **Bài 4:** Flush đã gửi SQL nhưng transaction rollback sẽ hoàn tác các writes transactional.
- **Bài 5:** Whole-job atomic nhưng transaction dài, rollback lớn, restart khó; per-chunk có partial progress nhưng checkpoint/retry cần idempotency.
- **Bài 6:** DB phải sinh ID và provider cần generated key ngay; benchmark SEQUENCE/application UUID.
- **Bài 7:** Sequence allocation và mapping phải tương thích; sequence preallocation/rollback tạo gaps là bình thường.
- **Bài 8:** Gom inserts cùng SQL shape để tăng batch; business ordering phải được biểu diễn bằng domain/schema.
- **Bài 9:** Hibernate cần affected-row count để phát hiện stale version; driver phải trả semantics batch count phù hợp.
- **Bài 10:** Self-invocation bypass Spring proxy; đặt chunk writer ở bean khác hoặc dùng transaction template.
- **Bài 11:** Replay chunk theo at-least-once; unique key/idempotent upsert ngăn duplicate.
- **Bài 12:** Có thể checkpoint bỏ qua rows chưa commit; checkpoint phải atomic với target data hoặc chỉ sau commit và idempotent.
- **Bài 13:** Unique(source_system, source_key), không chỉ external ID.
- **Bài 14:** SELECT-then-INSERT có race và query thêm; DB upsert atomic theo constraint nhưng có thể bypass ORM lifecycle.
- **Bài 15:** merge theo entity identity/ID, không tự tìm và atomic upsert theo arbitrary business key.
- **Bài 16:** Rollback transaction lỗi, mở transaction mới, backoff/jitter và giới hạn attempts; validation error cần sửa/quarantine.
- **Bài 17:** DB có thể đánh dấu transaction aborted; rollback chunk rồi tách record lỗi hoặc dùng skip/quarantine policy có transaction rõ.
- **Bài 18:** Lưu cả created_at và source_id làm tie-breaker trong checkpoint.
- **Bài 19:** Chốt MAX(source_id) lúc bắt đầu và đọc tới high-water mark theo keyset.
- **Bài 20:** Spring Batch size điều khiển số items trong chunk transaction; Hibernate size điều khiển số statements mỗi JDBC batch.
- **Bài 21:** SQL đơn giản/bulk cần throughput cao, không cần cascades/lifecycle; flush ORM trước JDBC khi cần ordering, clear/refresh sau JDBC DML.
- **Bài 22:** Khi set-based validation/merge và bulk loader giảm ORM object overhead; staging cần retention/security/transaction design.
- **Bài 23:** Atomic claim, lease expiry, heartbeat và fencing token/version để worker cũ không ghi sau khi lease mất.
- **Bài 24:** Đo records/sec, chunk latency, commit/flush time, batch count, DB CPU/locks, pool waits, heap/GC, retries và correctness; giữ dataset, DB, indexes, driver, JVM và concurrency ổn định.

---

## Tổng kết

**Import bền vững cần batching, chunking, transaction boundaries và restart semantics phối hợp với nhau.**

1. JDBC batch size giảm round-trips; chunk size giới hạn phạm vi công việc/transaction. Hai giá trị không đồng nghĩa.
2. Hibernate batching cần SQL shape tương thích và identifier strategy phù hợp. IDENTITY thường hạn chế INSERT batching; sequence/application-assigned IDs đáng benchmark.
3. Gọi flush() để gửi pending changes, sau đó clear() để detach managed entities và kiểm soát persistence-context memory. Flush không commit; clear không rollback.
4. Transaction per chunk cho phép commit/checkpoint từng phần nhưng tạo yêu cầu idempotency và restart. Transaction toàn job atomic hơn nhưng có thể rất dài và tốn rollback.
5. Checkpoint nên commit cùng target data nếu cùng database. Khi crash window không thể loại bỏ, replay at-least-once phải an toàn nhờ unique business keys, upsert hoặc deduplication.
6. Retry chỉ transient failures trong transaction mới; data errors cần reject/quarantine và reconciliation.
7. Đo records/sec, JDBC batches, rows, chunk/commit duration, database locks, pool wait, heap và GC. Chọn batch/chunk size bằng benchmark trên database/driver thật.
8. Với import rất lớn, staging table, database-native bulk loader hoặc JDBC batch có thể phù hợp hơn việc hydrate hàng triệu Hibernate entities.

**Một job import chỉ thật sự có thể chạy lại khi nó biết chính xác chunk nào đã commit, nhận diện được record đã xử lý, và có thể replay phần chưa chắc chắn mà không tạo dữ liệu trùng hoặc ghi đè dữ liệu mới hơn.**
