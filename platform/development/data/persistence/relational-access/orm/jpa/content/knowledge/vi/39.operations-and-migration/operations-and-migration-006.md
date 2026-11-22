# Theo dõi lỗi khóa, timeout và lỗi đồng bộ dữ liệu khi vận hành JPA

Ứng dụng sử dụng JPA/Hibernate có thể chạy ổn trong môi trường phát triển nhưng phát sinh lỗi khi lượng giao dịch tăng, nhiều tiến trình cập nhật cùng một bản ghi, tác vụ di trú chạy song song với người dùng, hoặc dữ liệu được đồng bộ giữa database và các hệ thống khác. Những lỗi này thường chỉ xuất hiện ngắt quãng, rất khó tái hiện nếu không thu thập được ngữ cảnh của **giao dịch, câu SQL, đối tượng bị tranh chấp và tiến trình đang chờ**.

Bài này tập trung vào cách phát hiện, phân loại, quan sát và xử lý **lỗi khóa (lock contention/deadlock), timeout và sai lệch đồng bộ dữ liệu** trong hệ thống Spring Data JPA; đồng thời nêu các biện pháp vận hành an toàn khi migrate schema hoặc backfill dữ liệu.

> Nguyên tắc vận hành: xem exception của Hibernate/Spring là dấu hiệu ở tầng ứng dụng; để xác định nguyên nhân thực tế cần đối chiếu với transaction, SQL và thông tin giám sát ở database. Một timeout không tự chứng minh database đang bị deadlock, và một lỗi cập nhật đồng thời không nhất thiết là lỗi kết nối.

## 1. Phân loại triệu chứng trước khi can thiệp

| Triệu chứng | Khả năng liên quan | Dấu hiệu xác minh | Hướng xử lý ban đầu |
| --- | --- | --- | --- |
| Request cập nhật chờ lâu rồi lỗi | Row lock bị giữ, truy vấn chậm, pool hết kết nối | Wait event, blocking session, duration, pool metrics | Xác định transaction đang chặn và nơi giữ lock |
| Database báo deadlock | Hai hay nhiều giao dịch chờ vòng tròn | Deadlock report, SQL và thứ tự truy cập bản ghi | Sửa thứ tự khóa, rút ngắn transaction; retry có điều kiện |
| `OptimisticLockException` hoặc lỗi version | Dữ liệu đã bị transaction khác thay đổi | ID, version trước/sau, số dòng update | Báo xung đột, đọc lại dữ liệu, retry theo nghiệp vụ |
| Hết thời gian chờ nhận connection | Pool cạn, connection rò rỉ, truy vấn giữ connection lâu | Active/idle/pending, connection acquisition time | Phân tích pool, transaction và số connection DB |
| Query timeout | SQL quá chậm, bị chờ lock, deadline truy vấn | SQL duration, execution plan, database wait | Phân biệt chờ lock với kế hoạch truy vấn kém |
| Transaction timeout | Công việc trong transaction vượt giới hạn | Transaction start/end, số query, network call | Thu hẹp transaction, chia batch phù hợp |
| API đọc thấy dữ liệu cũ | Persistence context cache, cache tầng 2, replica lag | Source database, entity state, cache hit, replica lag | Kiểm tra nguồn đọc và chiến lược nhất quán |
| Dữ liệu giữa các hệ thống lệch nhau | Event thất lạc/trùng/thứ tự sai, CDC lag, backfill lỗi | Event ID, offset, checkpoint, số bản ghi, tổng tiền | Khoanh vùng sai lệch, replay idempotent, đối soát |
| Migration đột nhiên làm tăng latency | DDL chờ lock, backfill giữ transaction dài | Migration ID, lock wait, DDL activity | Dừng/giảm nhịp tác vụ phù hợp và xem lock graph |

Cùng một request có thể để lại nhiều lỗi ở các tầng khác nhau. Ví dụ một transaction giữ row lock lâu khiến query khác chờ, request bị gateway timeout, rồi hệ thống lại báo connection pool cạn vì các request đang giữ connection. Hãy phân biệt **sự kiện gốc** và **hậu quả dây chuyền** trước khi thay cấu hình timeout hoặc tăng pool size.

## 2. Hiểu vòng đời transaction và vị trí phát sinh lỗi

Trong JPA, entity được quản lý bởi **persistence context**. Thay đổi trạng thái entity có thể chỉ được gửi thành câu SQL khi Hibernate thực hiện **flush** hoặc commit transaction. Vì vậy:

1. Service gọi `repository.findById(...)` và lấy entity.
2. Code sửa các thuộc tính; Hibernate ghi nhận thay đổi.
3. Hibernate thực hiện `UPDATE` khi flush hoặc commit, có thể lúc thực thi một truy vấn cần đồng bộ trạng thái.
4. Database kiểm tra version, constraint và lock; lỗi có thể xuất hiện ở bước 3, không nhất thiết tại dòng setter.
5. Transaction được commit hoặc rollback; transaction đã bị đánh dấu rollback-only không thể tiếp tục commit thành công.

Điều này giải thích vì sao stack trace đôi khi chỉ vào `saveAndFlush`, `flush`, `TransactionInterceptor` hoặc thời điểm kết thúc `@Transactional` dù logic thực hiện thay đổi trước đó.

### 2.1. Ví dụ cập nhật cạnh tranh

Giả sử hai giao dịch cùng điều chỉnh tồn kho của sản phẩm ID 42:

```text
T1: BEGIN ── đọc tồn kho ── sửa ── UPDATE/giữ lock ───────── COMMIT
T2:        BEGIN ── đọc tồn kho ── sửa ── chờ T1 ── UPDATE hoặc lỗi
                                    ↑
                           chờ khóa tại database
```

Kết quả cụ thể phụ thuộc mức isolation, điều kiện cập nhật, version column và loại lock sử dụng. Nếu không có biện pháp bảo vệ, ứng dụng có thể gặp **lost update**. Nếu bật optimistic locking, một bên có thể nhận lỗi version và cần xử lý xung đột.

### 2.2. Tránh transaction dài

Những việc làm transaction kéo dài thường gồm gọi HTTP sang hệ thống khác, xử lý file lớn, gửi email, sleep/retry trong transaction, đọc tập dữ liệu không phân trang hoặc backfill hàng trăm nghìn bản ghi trong một transaction.

Một transaction dài có thể kéo theo:

- Giữ lock và connection lâu.
- Khiến giao dịch khác chờ.
- Tăng kích thước vùng quản lý entity và chi phí dirty checking.
- Làm hệ thống giữ snapshot lâu, gây áp lực lên cơ chế quản lý phiên bản dữ liệu của DB.
- Khó rollback hoặc phục hồi nếu migration bị gián đoạn.

Đặt ranh giới transaction quanh **một đơn vị công việc cần tính nguyên tử**, không bao quanh toàn bộ luồng điều phối kéo dài.

## 3. Quan sát và xử lý lỗi khóa

### 3.1. Pessimistic locking

Pessimistic lock yêu cầu database bảo vệ tài nguyên ngay lúc truy cập. JPA có các chế độ như `PESSIMISTIC_READ` và `PESSIMISTIC_WRITE`. Trong nhiều hệ quản trị, `PESSIMISTIC_WRITE` được hiện thực bằng một dạng `SELECT ... FOR UPDATE` hoặc cơ chế khóa tương đương.

Ví dụ Spring Data JPA:

~~~java
public interface InventoryRepository extends JpaRepository<Inventory, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select i from Inventory i where i.id = :id")
    Optional<Inventory> findForUpdate(@Param("id") Long id);
}
~~~

~~~java
@Service
public class InventoryService {
    private final InventoryRepository repository;

    public InventoryService(InventoryRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void reserve(Long inventoryId, int quantity) {
        Inventory inventory = repository.findForUpdate(inventoryId)
            .orElseThrow(() -> new IllegalArgumentException("Inventory not found"));
        inventory.reserve(quantity);
    }
}
~~~

Khóa có ý nghĩa khi truy vấn chạy **trong transaction đủ dài để thực hiện cập nhật**. Nếu thao tác đọc khóa ở một transaction rồi cập nhật ở transaction khác, khóa trước đó có thể đã được giải phóng. Không gọi API chậm hoặc chờ người dùng trong lúc giữ khóa.

JPA hỗ trợ hint `jakarta.persistence.lock.timeout` nhưng cách dịch sang database, việc hỗ trợ giá trị và đặc biệt hành vi “không chờ” đều phụ thuộc provider và dialect. Hãy kiểm tra Hibernate và database cụ thể thay vì xem hint là cam kết độc lập với nền tảng.

### 3.2. Deadlock khác với lock wait

**Lock wait:** T2 cần bản ghi đang được T1 giữ. Nếu T1 commit kịp thời, T2 có thể tiếp tục.

**Deadlock:** T1 đã khóa A rồi muốn B, trong khi T2 đã khóa B rồi muốn A. Hai giao dịch chờ lẫn nhau; database thường phát hiện chu trình và chọn một transaction làm nạn nhân để rollback.

~~~text
Transaction A                  Transaction B
LOCK order 10                  LOCK order 20
request LOCK order 20 ─┐   ┌─ request LOCK order 10
                       └───┘
                  DEADLOCK
```

Hướng phòng tránh:

- Khi cần khóa nhiều bản ghi cùng loại, lấy theo **thứ tự cố định** (ví dụ ID tăng dần) ở mọi code path.
- Tránh cập nhật nhiều bảng theo thứ tự khác nhau ở các use case.
- Chỉ khóa tập bản ghi thực sự cần; query phải có index phù hợp để giảm phạm vi scan và thời gian giữ lock.
- Giữ transaction ngắn, tách tác vụ I/O hoặc tính toán nặng khỏi transaction.
- Khi retry deadlock, thực hiện lại **toàn bộ đơn vị công việc trong transaction mới**, với giới hạn số lần và khoảng dừng phù hợp.

Không nên chỉ tăng timeout: deadlock là vòng chờ, tăng thời gian chờ không loại bỏ nguyên nhân.

### 3.3. Phân biệt nhóm exception

Tên exception có thể thay đổi theo Hibernate version, database và cơ chế chuyển đổi exception của Spring. Một số trường hợp thường gặp:

| Lớp/lỗi | Ý nghĩa gợi ý | Cách phản ứng |
| --- | --- | --- |
| `jakarta.persistence.OptimisticLockException` | Cập nhật dựa trên phiên bản cũ | Đọc lại và giải quyết xung đột |
| `ObjectOptimisticLockingFailureException` | Spring phát hiện thất bại optimistic locking | Trả lỗi xung đột hoặc retry có kiểm soát |
| `jakarta.persistence.LockTimeoutException` | Thao tác chờ lock vượt giới hạn trong trường hợp nhà cung cấp hỗ trợ | Kiểm tra blocking session và thời gian chờ |
| `jakarta.persistence.PessimisticLockException` | Thất bại khi lấy pessimistic lock | Kiểm tra khả năng transaction đã bị rollback |
| `CannotAcquireLockException` | Spring chuyển đổi một số lỗi không lấy được lock | Tìm SQLState, mã lỗi DB và deadlock report |
| `DeadlockLoserDataAccessException` | Tên exception Spring từng dùng cho nạn nhân deadlock | Đối chiếu version/framework, không phụ thuộc riêng tên này |
| `org.springframework.dao.QueryTimeoutException` | Truy vấn vượt timeout | Kiểm tra query duration và thời gian chờ |
| `CannotGetJdbcConnectionException` hoặc lỗi pool | Không lấy được connection JDBC | Kiểm tra pool và khả năng kết nối DB |

**Không ánh xạ tất cả lỗi khóa thành cùng một “retry ngay”**. Một số lỗi khiến transaction đã bị rollback hoặc bị đánh dấu rollback-only; tiếp tục xử lý trong transaction đó không an toàn. Số lần retry phải bị chặn và phải dựa trên mã lỗi thực tế cũng như tính idempotent của thao tác.

## 4. Timeout có nhiều tầng độc lập

Một hệ thống thường có nhiều đồng hồ:

| Timeout | Nơi phát sinh | Câu hỏi cần trả lời |
| --- | --- | --- |
| HTTP gateway/client deadline | Gateway, API consumer | Người gọi có còn chờ response không? |
| Connection acquisition timeout | HikariCP hoặc connection pool | Lấy connection từ pool có quá lâu không? |
| JDBC connect/login/socket timeout | Driver và mạng | Kết nối hoặc đọc kết quả từ DB có bị nghẽn không? |
| Query/statement timeout | ORM, JDBC, database | Một câu SQL được phép chạy bao lâu? |
| Lock wait timeout | Database hoặc hint lock | Một giao dịch được phép chờ khóa bao lâu? |
| Transaction timeout | Spring transaction manager/DB | Toàn bộ transaction đã vượt thời gian cho phép chưa? |
| Idle transaction timeout | Database | Session mở transaction nhưng không chạy SQL bao lâu? |

Timeout request 10 giây không đồng nghĩa mọi query sẽ dừng ở 10 giây. Việc cancel query và rollback còn phụ thuộc JDBC driver, database, hạ tầng mạng và cách framework xử lý interrupt/cancellation.

### 4.1. Ví dụ cấu hình Spring Boot

~~~yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 20
      connection-timeout: 3000  # ms: thời gian chờ mượn connection
  jpa:
    properties:
      jakarta.persistence.query.timeout: 5000  # ms: hint query mặc định, phụ thuộc provider
~~~

Các con số là **minh họa**, không phải ngưỡng áp dụng chung. `maximum-pool-size` phải được quyết định dựa trên giới hạn connection của database, số instance và năng lực xử lý. Tăng pool quá lớn có thể làm database bão hòa nhanh hơn.

Với Spring, có thể giới hạn transaction theo nghiệp vụ:

~~~java
@Transactional(timeout = 10)
public void updatePrice(Long productId, BigDecimal price) {
    Product product = repository.findById(productId).orElseThrow();
    product.changePrice(price);
}
~~~

`@Transactional(timeout = 10)` sử dụng đơn vị **giây**. Mức độ enforcement phụ thuộc transaction manager và việc chuyển deadline đến các statement. Không dùng transaction timeout để thay thế kiểm soát truy vấn, lock và pool.

### 4.2. Cách chẩn đoán timeout theo đường đi

~~~text
Request bắt đầu
    |
    v
Chờ connection từ pool? ── Có ──> kiểm tra Hikari active / idle / pending
    |
   Không
    v
Có SQL đang thực thi? ────── Không ──> kiểm tra code khác trong transaction
    |
    v
SQL đang chờ lock? ───────── Có ──> tìm blocker, tuổi transaction, loại lock
    |
   Không
    v
SQL đang chạy CPU/I/O? ───── Có ──> EXPLAIN, index, số dòng và thống kê
    |
    v
Kiểm tra mạng/driver và thời gian lấy kết quả
```

Một transaction bị lock wait cũng chiếm connection, nên sự cố khóa kéo dài có thể biến thành pool timeout của nhiều request khác. Đó là lý do cần correlation ID để ghép log request với transaction và dữ liệu theo thời điểm từ database.

## 5. Theo dõi ở tầng ứng dụng: log, metric và trace

### 5.1. Log có cấu trúc để điều tra

Mỗi request hoặc job ghi dữ liệu nên có tối thiểu:

- `traceId`, `requestId` hoặc `jobId`.
- Tên thao tác nghiệp vụ, tên repository/query (không bắt buộc toàn bộ SQL ở production).
- Thời gian bắt đầu và kết thúc, `durationMs`, số lần thử lại.
- Loại exception, root cause, SQLState và vendor error code nếu được cung cấp.
- Loại tác vụ: API, batch, migration, CDC consumer, reconciliation.
- Entity type, khóa nghiệp vụ đã chuẩn hóa hoặc hash khi cần; giới hạn thông tin nhạy cảm.
- `transactionId` hoặc database session ID khi thu thập được và an toàn.

Ví dụ bản ghi log mô tả một lần cập nhật thất bại:

~~~json
{
  "level": "WARN",
  "event": "inventory.reserve.failed",
  "traceId": "7dd8c1a2",
  "operation": "reserveInventory",
  "entityType": "Inventory",
  "entityId": "42",
  "durationMs": 1840,
  "retryAttempt": 1,
  "exception": "ObjectOptimisticLockingFailureException",
  "sqlState": null,
  "outcome": "CONFLICT"
}
~~~

Không ghi password, access token, chuỗi kết nối có secret, giá trị cá nhân hoặc toàn bộ tham số SQL nhạy cảm. Nếu cần truy vết khóa của một đối tượng, có thể lưu ID nội bộ đã được phê duyệt hoặc một định danh đã hash phù hợp.

### 5.2. Nhóm metric nên có

| Metric | Ý nghĩa | Ví dụ cách sử dụng |
| --- | --- | --- |
| `http.server.requests` latency p95/p99 | Request đang chậm lên ở endpoint nào | Kết hợp với trace và dependency |
| Hikari active/idle/pending connections | Áp lực pool | Pending tăng cùng active gần mức tối đa |
| Hikari connection acquire time | Độ trễ mượn kết nối | Tăng khi pool cạn hoặc connection bị giữ lâu |
| `db.lock.wait.duration` và số lỗi khóa (custom) | Mức tranh chấp khóa | Phân nhóm theo operation và loại DB error |
| `db.deadlock.count` (DB metric) | Tần suất deadlock | Theo dõi thay đổi so với baseline |
| `db.query.duration` p95/p99 | Câu SQL chậm | Theo fingerprint query, tránh raw SQL làm label |
| `transaction.rollback.count` | Tỷ lệ rollback bất thường | Phân tách business reject và lỗi hệ thống |
| `sync.consumer.lag` | Độ trễ đồng bộ event/CDC | Theo consumer/topic hoặc pipeline |
| `sync.reconciliation.mismatch` | Số bản ghi/giá trị đối soát sai | Cần điều tra dữ liệu thực tế |

Với Spring Boot Actuator và Micrometer, thường có metric của HikariCP và HTTP nếu cấu hình instrumentation tương ứng. Custom metric có thể dùng `Counter` hoặc `Timer`. Không dùng ID người dùng, order ID, exception message hoặc SQL nguyên văn làm label vì tạo quá nhiều tổ hợp (high cardinality).

### 5.3. Theo dõi trace trên ranh giới transaction

Gắn các span hoặc event cho:

~~~text
HTTP POST /reservations
 ├─ application.reserveInventory
 │   ├─ tx.begin
 │   ├─ repository.findForUpdate
 │   ├─ repository.flush
 │   └─ tx.commit
 └─ response
```

Tên và cấu trúc span cụ thể phụ thuộc thư viện tracing. Thời gian giữa các span giúp phân biệt thời gian chạy code Java với lúc chờ JDBC hoặc database. Kết nối thời điểm lỗi với snapshot lock trong DB có giá trị hơn việc chỉ đọc một stack trace sau khi blocker đã biến mất.

## 6. Chẩn đoán trực tiếp ở database

### 6.1. PostgreSQL: tìm session đang chờ và session chặn

Truy vấn sau giúp nhận diện các session hiện đang bị chặn, thời lượng transaction và tiến trình chặn:

~~~sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.state,
    now() - a.xact_start AS transaction_age,
    now() - a.query_start AS query_age,
    a.wait_event_type,
    a.wait_event,
    pg_blocking_pids(a.pid) AS blocking_pids,
    left(a.query, 200) AS query_sample
FROM pg_stat_activity AS a
WHERE cardinality(pg_blocking_pids(a.pid)) > 0
ORDER BY a.query_start NULLS LAST;
~~~

Truy vấn dựa trên `pg_stat_activity` và `pg_blocking_pids`; quyền xem SQL của session khác phụ thuộc quyền PostgreSQL. `query_sample` có thể chứa thông tin nhạy cảm, vì vậy cần giới hạn quyền truy cập và không đẩy tự động câu SQL chưa xử lý vào nơi công khai.

Để xem transaction mở lâu hoặc đang idle trong transaction:

~~~sql
SELECT
    pid,
    application_name,
    state,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start ASC;
~~~

Các metric/chỉ số đáng chú ý:

- `pg_stat_database.deadlocks`: bộ đếm deadlock theo database, cần tính chênh lệch theo thời gian.
- `pg_locks`: các lock đang được giữ/yêu cầu; kết hợp với session để điều tra sâu hơn.
- `pg_stat_statements` (nếu cài extension và cấp quyền): thống kê câu SQL theo dạng chuẩn hóa.
- PostgreSQL log: bật ghi nhận lock wait/deadlock phù hợp, cấu hình `log_lock_waits` và `deadlock_timeout` cần cân nhắc overhead.
- `lock_timeout`, `statement_timeout`, `idle_in_transaction_session_timeout`: ba giới hạn khác nhau.

Ví dụ minh họa cấu hình theo **một transaction**:

~~~sql
BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '8s';
-- thao tác cập nhật cần kiểm soát
COMMIT;
~~~

`SET LOCAL` có hiệu lực trong transaction hiện tại. Nếu `lock_timeout` lớn hơn hoặc bằng `statement_timeout`, statement timeout có thể xảy ra trước, khiến khó quan sát riêng nguyên nhân khóa. Chọn cấu hình theo SLO và bằng chứng thực tế.

**Không tùy tiện kết thúc backend của người khác.** Hủy query hoặc terminate session có thể rollback công việc quan trọng. Trong sự cố production, cần xác nhận owner, tuổi transaction và tác động trước khi can thiệp. Cách sửa bền vững là tìm code path giữ khóa lâu.

### 6.2. MySQL / InnoDB

Với MySQL 8, có thể tra cứu trạng thái lock tại `performance_schema.data_locks` và `performance_schema.data_lock_waits`. Trên các hệ thống có schema `sys`, view `sys.innodb_lock_waits` cung cấp cách đọc thuận tiện hơn:

~~~sql
SELECT *
FROM sys.innodb_lock_waits;
~~~

Các nguồn bổ sung thường dùng:

- `SHOW ENGINE INNODB STATUS`: tình trạng InnoDB và thông tin deadlock gần đây.
- `performance_schema.events_statements_*`: dấu vết statement khi được cấu hình.
- `information_schema.innodb_trx`: trạng thái transaction InnoDB.
- Bộ đếm deadlock, lock wait và số connection từ monitoring database.

Nhớ phân biệt `innodb_lock_wait_timeout` với statement timeout hoặc timeout ở ứng dụng. Lock wait timeout có thể rollback statement hiện tại, còn deadlock thường khiến InnoDB rollback transaction bị chọn; ứng dụng phải kiểm tra rõ transaction còn hợp lệ trước khi tiếp tục.

### 6.3. Oracle Database và các hệ quản trị khác

Với Oracle, các view như `V$SESSION`, `V$LOCK` và `V$SQL` giúp xác định session đang chờ, blocker và SQL liên quan; cần quyền phù hợp. Những lỗi như `ORA-00060` (deadlock detected) hoặc `ORA-00054` (resource busy trong trường hợp thao tác yêu cầu lock không lấy được) là tín hiệu hữu ích, nhưng phải đối chiếu thông báo và hoạt động thực tế. Không dùng SQL/PostgreSQL timeout hay mã lỗi của một DB để suy đoán trực tiếp hành vi của DB khác.

Khi thay đổi dialect, driver hoặc database, hãy lưu lại bảng ánh xạ **mã lỗi vendor/SQLState → loại sự cố → chính sách xử lý** theo môi trường đang vận hành.

## 7. Optimistic locking để phát hiện cập nhật mất dữ liệu

### 7.1. Dùng `@Version`

Đây là cách phổ biến để phát hiện hai transaction cùng ghi một entity mà không giữ pessimistic lock từ lúc đọc.

~~~java
@Entity
@Table(name = "inventories")
public class Inventory {
    @Id
    private Long id;

    @Version
    private long version;

    @Column(nullable = false)
    private int availableQuantity;

    public void reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        if (availableQuantity < quantity) {
            throw new IllegalStateException("insufficient stock");
        }
        availableQuantity -= quantity;
    }
}
~~~

Ở mức khái niệm, ORM sẽ phát sinh phép cập nhật tương đương:

~~~sql
UPDATE inventories
SET available_quantity = :next_quantity,
    version = :next_version
WHERE id = :id
  AND version = :expected_version;
~~~

Nếu số bản ghi được cập nhật không khớp kỳ vọng vì version đã thay đổi, Hibernate/JPA có thể ném lỗi optimistic locking. Hệ quả nghiệp vụ:

- Không ghi đè âm thầm bản cập nhật khác.
- Trả về xung đột cho client để nạp lại dữ liệu, hoặc retry có kiểm soát.
- Nếu sử dụng retry, phải đọc lại entity ở **transaction mới** và chạy lại kiểm tra nghiệp vụ, không chỉ ghi lại giá trị cũ.

Với API công khai, `409 Conflict` thường thích hợp cho xung đột trạng thái nghiệp vụ. Với lỗi thiếu phiên bản/điều kiện request như `If-Match`, có thể áp dụng chiến lược HTTP precondition tương ứng nếu API đã định nghĩa; HTTP status không nên được quyết định duy nhất bởi tên exception.

### 7.2. Cẩn trọng với JPQL bulk update và native update

Bulk JPQL như:

~~~java
@Modifying
@Query("update Inventory i set i.availableQuantity = :value where i.id = :id")
int overwriteQuantity(@Param("id") Long id, @Param("value") int value);
~~~

không thực hiện dirty checking từng entity như cập nhật entity được quản lý; bulk update cũng **không tự áp dụng kiểm tra optimistic version trên từng entity** theo cách cập nhật entity thông thường. Nếu ứng dụng phụ thuộc version, phải thiết kế điều kiện version và cập nhật version tường minh, hoặc dùng managed entity.

Ví dụ compare-and-set theo version:

~~~java
@Modifying(clearAutomatically = true, flushAutomatically = true)
@Query("""
    update Inventory i
       set i.availableQuantity = :newValue,
           i.version = i.version + 1
     where i.id = :id
       and i.version = :expectedVersion
    """)
int compareAndSetQuantity(
    @Param("id") Long id,
    @Param("expectedVersion") long expectedVersion,
    @Param("newValue") int newValue
);
~~~

Nếu trả về 0 dòng cập nhật, service phải coi đó là dấu hiệu cần điều tra: ID có thể không tồn tại hoặc version đã thay đổi. Với một số dạng version (ví dụ timestamp), phép tăng số học không phù hợp; thiết kế câu query theo kiểu dữ liệu version thực tế.

Sau bulk update/native DML, các entity cùng ID đã được nạp trong persistence context có thể **không phản ánh dữ liệu mới**. `clearAutomatically = true` có thể dọn context sau thao tác, nhưng cần chú ý thay đổi chưa flush; ở ví dụ trên `flushAutomatically = true` yêu cầu flush trước. Khi cần giữ các object khác, cân nhắc `refresh` hoặc ranh giới transaction thay vì clear toàn bộ tùy tiện.

## 8. “Lỗi đồng bộ dữ liệu” có thể nằm ở nhiều tầng

Trước khi sửa, cần xác định dữ liệu nào đang được đồng bộ và mô hình nhất quán mong muốn.

| Tầng đồng bộ | Ví dụ sai lệch | Nguyên nhân thường gặp |
| --- | --- | --- |
| Entity và persistence context | Entity đang quản lý giữ giá trị cũ sau bulk update | First-level cache, truy vấn bulk bỏ qua entity state |
| Transaction song song | Hai request cùng ghi và mất cập nhật | Thiếu version hoặc điều kiện nguyên tử |
| Cache và database | Cache ứng dụng trả bản cũ | TTL, invalidation, cache key hoặc thời điểm xóa cache |
| Primary và read replica | Đọc sau ghi thấy trạng thái cũ | Replica lag và định tuyến truy vấn đọc |
| Database và message broker | DB đã commit nhưng không phát sự kiện | Dual-write không nguyên tử |
| Nhiều consumer/hệ thống | Nhận event trùng hoặc đảo thứ tự | Retry delivery, redelivery, consumer cạnh tranh |
| Job migration/backfill | Thiếu dòng, ghi đè dữ liệu mới | Checkpoint sai, race với giao dịch online, batch rollback |

### 8.1. Đọc sau ghi ở replica

Một giao dịch ghi thành công trên primary không bảo đảm query đi vào read replica ngay sau đó nhìn thấy cùng dữ liệu. Trong API yêu cầu **read-your-writes**, nên dùng primary cho bước đọc xác nhận hoặc có cơ chế consistency token phù hợp. Đặt TTL cache nhỏ không giải quyết được replica lag ở nguồn dữ liệu.

Theo dõi độ trễ replica, error của replication, vị trí WAL/binlog, backlog và thời gian catch-up. Cách lấy metric phụ thuộc engine và dịch vụ database.

### 8.2. Đồng bộ DB và event: Transactional Outbox

Một thiết kế dễ lỗi:

~~~text
1. UPDATE order trong DB
2. COMMIT DB
3. publish OrderConfirmed lên broker
   ↳ process chết ở bước 3 => DB đã đổi nhưng event mất
```

Với **Transactional Outbox**, cùng một transaction ghi dữ liệu nghiệp vụ và bản ghi sự kiện vào bảng outbox:

~~~text
BEGIN
  UPDATE purchase_orders ...;
  INSERT INTO outbox_events(event_id, aggregate_id, event_type, payload, ...)
    VALUES (...);
COMMIT

Outbox publisher / CDC:
  đọc bản ghi đã commit → publish event → ghi nhận tiến độ
```

Cơ chế này bảo đảm ý định phát sự kiện được lưu atomically cùng thay đổi database, nhưng **không tự tạo bảo đảm exactly-once ở phía consumer**. Publisher có thể gửi trùng sau crash/retry, do đó consumer cần deduplicate theo `event_id` hoặc một khóa idempotency, xử lý thứ tự theo aggregate khi nghiệp vụ yêu cầu và có cơ chế replay.

Lưu ý: không mặc định ghi dấu “đã publish” trước khi broker xác nhận. Nếu dùng polling publisher, phải thiết kế chuyển trạng thái/retry trong trường hợp crash giữa publish và cập nhật bảng outbox; nếu dùng CDC, cần quản lý offset và trạng thái connector.

### 8.3. Đối soát và phục hồi sai lệch

Các metric “consumer đang chạy” và “không có exception” chưa chứng minh dữ liệu đúng. Cần đối soát định kỳ giữa nguồn chuẩn và nơi nhận:

- Số lượng bản ghi theo khoảng thời gian/trạng thái.
- Tổng giá trị nghiệp vụ (ví dụ tổng tiền), có kiểm soát sai số/đơn vị tiền.
- Checksum/hash theo nhóm bản ghi nếu có chuẩn hóa dữ liệu đầu vào.
- Mốc `updated_at`, version hoặc sequence/offset để phát hiện cập nhật bỏ sót.
- Số event pending, retry, dead-letter và độ trễ lâu nhất.
- Kết quả reconcile theo `jobId`, khoảng dữ liệu và số bản ghi đã sửa.

Khi phát hiện mismatch, trước tiên lưu dấu **nguồn sự thật (source of truth)**, khóa nghiệp vụ, khoảng thời gian, checkpoint và loại sai lệch. Một job sửa chữa nên có chế độ dry-run, log từng batch, có khả năng chạy lại an toàn, và không ghi đè giao dịch mới hơn.

## 9. Vận hành an toàn trong schema migration và backfill

Migration là giai đoạn nhạy cảm vì ứng dụng cũ/mới có thể chạy đồng thời và DDL có thể đợi lock hoặc chặn DML tùy database. Dưới đây là các nguyên tắc thực tế.

### 9.1. Expand → Backfill → Switch → Contract

1. **Expand:** thêm bảng/cột hoặc cấu trúc mới theo hướng tương thích với phiên bản ứng dụng đang chạy; xem ảnh hưởng DDL lock.
2. **Deploy ứng dụng tương thích:** ghi/đọc theo chiến lược đã xác định; tránh giả định mọi instance được cập nhật cùng lúc.
3. **Backfill:** chuyển dữ liệu lịch sử theo batch nhỏ có checkpoint; giới hạn tài nguyên.
4. **Validate:** đối soát số dòng và giá trị, kiểm tra dữ liệu mới được ghi trong lúc backfill.
5. **Switch:** chuyển ứng dụng sang đường đọc/ghi mới sau khi xác minh.
6. **Contract:** xóa cấu trúc cũ ở đợt sau khi không còn code phụ thuộc và có phương án phục hồi.

Ví dụ: thay vì thêm cột NOT NULL có tính toán phức tạp rồi cập nhật toàn bảng trong một transaction, có thể thêm cột nullable trước, backfill dần, xác minh và sau đó mới siết constraint theo khả năng của DB. Việc thêm constraint hoặc index có thể cần chiến thuật online riêng của từng engine.

### 9.2. Backfill theo batch có checkpoint

Pseudo-code thể hiện hướng triển khai:

~~~java
long cursor = checkpointRepository.lastProcessedId(jobId);

while (true) {
    List<Long> ids = sourceRepository.findNextIdsAfter(cursor, 500);
    if (ids.isEmpty()) {
        break;
    }

    // Thực hiện batch trong một transaction riêng.
    batchService.migrateIds(ids);

    // Ghi checkpoint tương ứng với batch đã commit thành công;
    // checkpoint cần được thiết kế để phục hồi an toàn sau crash.
    cursor = ids.get(ids.size() - 1);
    checkpointRepository.saveProgress(jobId, cursor);
}
~~~

Đây là pseudo-code minh họa, không phải implementation hoàn chỉnh: việc đọc ID, commit batch và lưu checkpoint cần được thiết kế theo thứ tự an toàn. Nếu checkpoint được lưu sau commit riêng biệt, crash có thể khiến batch chạy lại, nên phép backfill phải **idempotent**. Nếu checkpoint ở cùng transaction, cần cân nhắc isolation và cách resume. Không dùng offset pagination cho dữ liệu đang biến động nếu có nguy cơ bỏ sót hoặc đọc trùng; keyset theo khóa ổn định thường dễ resume hơn.

Từng batch nên:

- Giới hạn số dòng và thời gian transaction.
- Chỉ ghi dữ liệu chưa migrate hoặc có điều kiện chống ghi đè cập nhật mới.
- Ghi số bản ghi đọc/cập nhật/bỏ qua/thất bại cùng checkpoint.
- Có ngưỡng giảm tốc hoặc tạm dừng khi production latency/lock wait vượt giới hạn.
- Tách retry cho các batch bị deadlock/timeout sau rollback.
- Phân biệt “đã thử” với “đã commit thành công”.

### 9.3. Migration tool có thể tự dùng lock

Flyway và Liquibase có cơ chế điều phối việc áp dụng migration; việc khóa schema history/changelog hoặc database lock phụ thuộc công cụ và engine. Nếu chạy nhiều instance cùng startup, cần quan sát instance nào đang migrate, lỗi lock và thời gian chờ. Đừng đồng thời chạy migration bằng script thủ công mà không có quy trình phối hợp.

Ví dụ PostgreSQL hỗ trợ `CREATE INDEX CONCURRENTLY` để giảm ảnh hưởng ghi trong nhiều tình huống, nhưng lệnh này **không chạy trong một transaction block thông thường**. Migration runner phải được cấu hình phù hợp từng migration và database. Không áp dụng nguyên văn cho MySQL/Oracle vì cú pháp và tính chất lock khác nhau.

### 9.4. Tín hiệu cần dừng hoặc giảm nhịp backfill

Nếu đang chạy backfill mà p99 request tăng đột biến, lock wait xuất hiện nhiều, pool gần cạn, replica lag tăng liên tục hoặc deadlock vượt mức nền, cần ưu tiên giảm concurrency/batch size và xác định nguyên nhân. Đừng tăng số worker “để chạy cho xong” khi database đã có dấu hiệu bão hòa.

## 10. Thiết kế chính sách retry đúng ranh giới

Không phải lỗi tạm thời nào cũng nên retry tự động. Với deadlock hoặc một số lỗi lock/transient connection, retry có thể hữu ích khi:

- Transaction lỗi đã kết thúc và phiên thử mới dùng **transaction mới**.
- Toàn bộ hành động có thể thực hiện lại an toàn hoặc có idempotency key.
- Có số lần thử giới hạn, backoff và jitter.
- Không giữ nguyên entity stale hoặc sử dụng lại persistence context hỏng.
- Có metric về lần thử, tỷ lệ phục hồi và tác động đến database.

Ví dụ ranh giới service:

~~~java
@Service
public class ReservationCommandService {
    private final ReservationTxService txService;

    public ReservationCommandService(ReservationTxService txService) {
        this.txService = txService;
    }

    public void reserve(String requestId, Long inventoryId, int quantity) {
        // Lớp ngoài điều phối retry theo chính sách đã cấu hình.
        // Mỗi lần gọi qua Spring proxy bên dưới mở transaction mới.
        txService.reserveOnce(requestId, inventoryId, quantity);
    }
}

@Service
public class ReservationTxService {
    @Transactional
    public void reserveOnce(String requestId, Long inventoryId, int quantity) {
        // Kiểm tra requestId để chống xử lý trùng; nạp lại Inventory;
        // kiểm tra tồn kho; ghi reservation và dữ liệu nghiệp vụ.
    }
}
~~~

Cấu trúc này chỉ minh họa **ranh giới transaction**; chưa cài đặt chính sách retry. Nếu dùng Spring Retry hay Resilience4j, phải xác định thứ tự advice/transaction, loại exception cần retry và test các trường hợp crash sau commit. Đặc biệt, nếu request bị timeout sau khi DB đã commit nhưng response thất lạc, client retry có thể tạo giao dịch trùng; idempotency key phải được xác thực và ràng buộc bằng unique constraint hoặc cơ chế tương đương.

### 10.1. Chuyển lỗi thành phản hồi API phù hợp

Có thể phân chia thành:

| Trường hợp | Phản hồi thường cân nhắc | Nội dung gửi client |
| --- | --- | --- |
| Xung đột optimistic version | `409 Conflict` | Dữ liệu đã thay đổi; yêu cầu tải lại hoặc hòa giải |
| Trạng thái nghiệp vụ không hợp lệ | `409` hoặc `422` tùy API contract | Lý do nghiệp vụ, mã lỗi ổn định |
| Lỗi lock tạm thời đã retry hết | `503 Service Unavailable` hoặc mã đã quy ước | Có thể thử lại sau nếu request idempotent |
| DB không sẵn sàng / connection pool cạn | `503` | Lỗi tạm thời; không lộ thông tin nội bộ |
| Query chậm hoặc timeout ở upstream | `504` ở gateway hoặc status theo trách nhiệm tầng xử lý | Thông báo timeout và request ID |

Đây là hướng thiết kế, không phải mapping HTTP bắt buộc cho mọi application. Không tiết lộ SQL, stack trace, connection string hoặc chi tiết lock của hệ thống trong response.

## 11. Runbook xử lý sự cố production

### Bước 1 — Xác định phạm vi ảnh hưởng

Ghi thời điểm bắt đầu, môi trường, version ứng dụng, DB node, migration/release gần nhất, endpoint, tỷ lệ lỗi, p95/p99, pool status và retry rate. Kiểm tra sự cố xảy ra mọi request hay chỉ các ID/tenant/partition cụ thể.

### Bước 2 — Khoanh vùng loại lỗi

Từ exception và mã lỗi database, xác định đó là optimistic conflict, deadlock, lock timeout, query timeout, pool timeout, lỗi mạng hay sai lệch dữ liệu. Nếu hiện chỉ có `TimeoutException` chung, bổ sung log correlation và root cause thay vì giả định.

### Bước 3 — Lấy bằng chứng theo cùng thời điểm

Trích trace, slow query/transaction, danh sách blocker/victim, execution plan, bản ghi deadlock và trạng thái migration/consumer. Lock graph thay đổi rất nhanh nên cần số liệu gần thời điểm xảy ra lỗi.

### Bước 4 — Giảm tác động

Nếu có backfill hoặc report làm nghẽn DB, giới hạn concurrency hoặc tạm dừng job theo quy trình vận hành. Với endpoint nóng, kiểm tra query/index, phạm vi transaction và số request cùng tranh chấp. Chỉ can thiệp session SQL khi hiểu tác động rollback.

### Bước 5 — Phục hồi và xác minh tính đúng đắn

Nếu là deadlock/timeout, kiểm tra transaction thất bại đã rollback trước khi retry có điều kiện. Nếu là lỗi đồng bộ, đối soát nguồn và đích rồi replay/rebuild đúng phạm vi. Luôn xác nhận không có xử lý trùng, mất dữ liệu hoặc cập nhật ghi đè bản mới.

### Bước 6 — Sửa nguyên nhân và đặt cảnh báo

Sửa thứ tự lấy khóa, tối ưu query/index, tách transaction, thêm version, chỉnh chiến lược pool/timeout hoặc bổ sung outbox/idempotency. Đặt alert theo tỷ lệ lỗi và thời gian bị ảnh hưởng so với baseline; tránh cảnh báo chỉ vì một lần optimistic conflict vốn có thể là kết quả nghiệp vụ bình thường.

## 12. Bộ chỉ số cho dashboard vận hành

Một dashboard hữu ích nên ghép số liệu **theo thời gian** để người vận hành thấy quan hệ nhân quả:

| Nhóm | Chỉ số ưu tiên | Câu hỏi trả lời |
| --- | --- | --- |
| Traffic/API | Requests/s, error rate, p95/p99 | Sự cố ảnh hưởng người dùng từ lúc nào? |
| Transaction | Commit/rollback, thời lượng, số transaction mở lâu | Có giao dịch giữ tài nguyên quá lâu không? |
| SQL/Lock | Slow query, lock wait, deadlock, blocker count | Query hoặc đối tượng nào bị tranh chấp? |
| Pool/DB | Connection active/idle/pending, DB CPU/IO, session count | Nút nghẽn nằm tại pool hay DB? |
| Migration | Batch progress, checkpoint age, batch latency, retry rate | Job có đang kẹt, chạy lại hoặc gây tải bất thường không? |
| Đồng bộ | Event backlog, oldest event age, replica lag, mismatch count | Dữ liệu đã theo kịp và đúng chưa? |

Ngưỡng cần được xác lập theo SLA/SLO, traffic và mùa vụ của hệ thống. Ví dụ “p99 tăng gấp đôi so với baseline cùng khung giờ”, “deadlock xuất hiện liên tục trong khoảng quan sát”, hoặc “oldest pending event age vượt mục tiêu đồng bộ” thường hữu ích hơn một ngưỡng cứng áp cho mọi service. Kết hợp burn rate hoặc khoảng thời gian duy trì giúp giảm alert nhiễu.

### Gợi ý quy trình thử nghiệm trước khi phát hành

Có thể dựng một môi trường tích hợp với database thật và chạy các kịch bản song song: hai transaction sửa cùng entity có `@Version`; hai transaction lấy khóa ngược thứ tự; một session cố tình giữ lock trong lúc session khác truy vấn; consumer nhận lại cùng event; batch backfill bị kill giữa các lần checkpoint. Theo dõi **kết quả nghiệp vụ**, số bản ghi, transaction rollback và metric; không chỉ xem có exception hay không.

## 13. Các nhầm lẫn cần tránh

**“Bị timeout thì tăng timeout là hết lỗi.”** Tăng giới hạn có thể chỉ trì hoãn lỗi và giữ connection lâu hơn. Cần biết timeout xảy ra ở pool, query, lock hay transaction.

**“Optimistic locking đã bật thì không còn conflict.”** `@Version` giúp **phát hiện** cập nhật đồng thời; conflict vẫn xảy ra và phải được xử lý theo nghiệp vụ.

**“Một deadlock nghĩa là database bị hỏng.”** Deadlock là hiện tượng tranh chấp có thể xuất hiện trong hệ thống transaction. Vấn đề là tỷ lệ deadlock, khả năng hồi phục và thứ tự truy cập dữ liệu.

**“Có thể retry ngay bên trong transaction đã thất bại.”** Nhiều lỗi dẫn đến rollback hoặc transaction rollback-only. Retry phải thực hiện với trạng thái mới và transaction hợp lệ.

**“Dữ liệu trong entity luôn khớp DB.”** Persistence context có thể giữ trạng thái cũ sau bulk update hoặc khi transaction khác đã commit. Cache và replica còn tạo các hình thức stale read khác.

**“Event publish thành công nghĩa là dữ liệu mọi service đã đồng bộ.”** Một event có thể chưa được consumer xử lý, xử lý trùng hoặc thất bại. Cần theo dõi lag, checkpoint, DLQ và đối soát.

**“Backfill chỉ cần chạy lại từ đầu khi lỗi.”** Nếu dữ liệu nguồn đang thay đổi, chạy lại không có idempotency/version guard có thể ghi đè dữ liệu mới hoặc tạo bản ghi trùng.

## Kết luận

Vận hành JPA ổn định đòi hỏi quan sát xuyên ba tầng: **ứng dụng** (trace, exception, transaction), **database** (lock graph, slow query, session, connection) và **luồng dữ liệu** (version, event, checkpoint, đối soát). Với lỗi khóa, xác định ai giữ khóa và giảm thời gian tranh chấp; với timeout, tìm đúng lớp đã hết hạn; với sai lệch đồng bộ, xác định nguồn sự thật và khôi phục bằng thao tác có thể chạy lại an toàn. Trong giai đoạn migration, transaction ngắn, batch có checkpoint, schema tương thích và kiểm chứng dữ liệu giúp hạn chế sự cố lan sang hệ thống đang phục vụ người dùng.
