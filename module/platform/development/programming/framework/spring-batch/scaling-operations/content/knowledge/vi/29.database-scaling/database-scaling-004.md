# Connection pool khi nhiều worker trong Spring Batch

## 1. Tại sao tăng worker lại khiến job chậm hơn?

Giả sử một job Spring Batch xử lý 20 triệu đơn hàng mỗi ngày. Khi chạy một worker, job mất 90 phút. Nhóm vận hành chuyển sang **8 worker pod**, mỗi pod có **8 thread**, kỳ vọng thời gian giảm mạnh. Nhưng sau khi scale:

- CPU worker chỉ hoạt động 25–40%, dù nhiều thread đang chạy.
- HikariCP báo `Connection is not available, request timed out`.
- PostgreSQL có nhiều session, tăng lock wait và transaction duration.
- `JobRepository` cập nhật checkpoint chậm; lỗi retry/restart dẫn tới xử lý lại.
- Tổng thời gian xử lý tăng từ 90 lên 110 phút thay vì giảm.

**Worker concurrency không phải database concurrency miễn phí.** Mỗi pod có thể sở hữu một hoặc nhiều connection pool; khi scale ngang, trần số connection **có thể mở** tăng theo số pod. Reader cursor, writer transaction và metadata repository có cách mượn/trả connection khác nhau.

Bài **“Connection pool khi nhiều worker”** nằm trong chương **Database scaling** của module `SPRING_BATCH_SCALING_OPERATIONS`. Module tập trung mở rộng Spring Batch cho workload dữ liệu lớn qua multi-threaded step, parallel steps, partitioning và các mô hình phân tán, đồng thời đo nút thắt, bảo đảm thread safety, retry/restart và chọn kiến trúc theo tài nguyên thực tế.

Sau bài học, bạn có thể:

1. Phân biệt **worker thread**, **StepExecution**, **JDBC connection** và **connection pool**.
2. Tính ngân sách connection trên **mỗi process** và **toàn cụm**, kể cả manager, worker và `JobRepository`.
3. Cấu hình HikariCP có giới hạn; hiểu `maximumPoolSize`, `minimumIdle`, `connectionTimeout`, `maxLifetime` và metric.
4. Nhận diện **pool starvation**, transaction quá lâu, reader cursor giữ connection và nested transactions.
5. Chọn concurrency/chunk size phù hợp thay vì chỉ tăng pool.
6. Xây benchmark và runbook đo CPU, I/O, lock wait, connection pending, retry/restart và tính đúng dữ liệu.

Ví dụ chính dùng **Java 17+, Spring Batch 5.2.x, Spring Boot 3.x, HikariCP và PostgreSQL**. Với Spring Batch 6.x/Spring Boot 4.x, cần đối chiếu API/import và cách cấu hình repository theo phiên bản đang chạy.

## 2. Mental model: một thread không nhất thiết giữ đúng một connection

`DataSource` cung cấp JDBC connection. HikariCP quản lý một **pool có giới hạn** và cho code ứng dụng mượn/trả connection qua `getConnection()`/`close()`. Khi dùng pool, `close()` ở tầng ứng dụng thường là **trả connection về pool**, không đóng socket vật lý ngay.

~~~mermaid
flowchart LR
    subgraph Worker["Một worker process"]
        T1["Chunk thread A"] --> P[Business Hikari pool]
        T2["Chunk thread B"] --> P
        T3["Chunk thread C"] --> P
        RD["Reader / writer"] --> P
        T1 --> M[Metadata Hikari pool]
    end
    P --> DB[(Business database)]
    M --> META[(Batch metadata database)]
~~~

**Không có quan hệ một-một cố định giữa thread và connection:**

- Thread làm CPU work thuần túy có thể **không giữ JDBC connection**.
- Transaction có thể giữ connection từ lần thực hiện SQL đầu tiên cho tới commit/rollback.
- `JdbcCursorItemReader` có thể giữ connection/cursor xuyên nhiều chunk, **khác** connection transaction của writer tùy cấu hình.
- Gọi service `@Transactional(propagation = REQUIRES_NEW)` khi transaction bên ngoài đang giữ connection có thể cần **thêm một connection**.
- Một worker có thể kết nối cả business DB và metadata DB bằng **hai DataSource/pool khác nhau**.
- `StepExecution` và thread là hai khái niệm khác nhau; partitioning tạo nhiều execution, multi-threaded step có thể dùng nhiều thread trong một execution.

Connection pool là **bộ điều tiết tài nguyên**, không tạo thêm CPU/IOPS. Pool quá nhỏ làm thread chờ; pool quá lớn tăng session, bộ nhớ server, tranh chấp lock và context switching. Tăng `maximumPoolSize` không tự làm SQL chạy nhanh hơn.

### Những con số thường bị nhầm

| Tham số / metric | Đơn vị | Ý nghĩa |
|---|---|---|
| `gridSize` | Gợi ý số partition khi lập plan | Không tự tạo bấy nhiêu thread hoặc pod |
| Worker replicas | Process/container | Mỗi replica thường có pool riêng |
| Executor `maxPoolSize` | Thread tối đa trong một executor | Không bằng số connection đang active |
| Hikari `maximumPoolSize` | Connection tối đa của **một pool instance** | Không phải trần connection toàn cụm |
| Hikari `minimumIdle` | Idle connections mà pool cố duy trì | Không phải số connection đang thực hiện SQL |
| `active connections` | Connection đang được mượn | DB có thể vẫn nhàn nếu client giữ lâu |
| `idle connections` | Connection sẵn để mượn | Không chứng minh worker logic đã xong |
| `pending/awaiting` | Thread chờ mượn connection | Dấu hiệu pool nghẽn nếu kéo dài |
| `connection timeout` | Thời gian chờ lấy connection từ pool | Khác query/transaction/network timeout |
| `max_connections` | Giới hạn session tại database | Bao gồm nhiều ứng dụng, không chỉ batch |

## 3. Phân tích connection theo mô hình chạy Spring Batch

| Kiến trúc | Đơn vị concurrency | Hệ quả đối với connection pool |
|---|---|---|
| **Step tuần tự** | Một execution, tuần tự | Ít hoạt động đồng thời nhưng reader có thể giữ cursor lâu |
| **Multi-threaded step** | Nhiều chunk thread trong một `StepExecution` | Nhiều transaction trên cùng pool; reader cần thread safety |
| **Parallel steps/flows** | Nhiều `StepExecution` trong cùng JVM | Các step chia pool và cạnh tranh connection |
| **Local partitioning** | Nhiều worker `StepExecution` trong một JVM | Nhiều reader/cursor + writer transaction trên cùng pool process |
| **Remote partitioning** | Nhiều partition ở nhiều process | Trần pool **nhân với số pod**, metadata traffic cũng tăng |
| **Remote chunking** | Manager đọc, worker xử lý/ghi chunk | Manager có pool reader; các worker có pool writer; tính toàn cụm |
| **Remote step (Spring Batch 6.x)** | Một logical step được thực thi từ xa | Dịch vị trí dùng connection, không tự chia step thành N partition |

Với remote partitioning, manager tạo 64 partition, có 4 worker pod và mỗi pod xử lý tối đa 2 execution cùng lúc:

\[
C_{\mathrm{active}}\le \min(64,4\times 2)=8
\]

Đây là trần số **execution đang thực thi**, không phải cam kết DB chỉ cần 8 connection. Mỗi execution có thể giữ cursor và dùng writer transaction ở những thời điểm khác nhau; metadata pool có traffic riêng.

~~~mermaid
flowchart TB
    M[Partition manager] --> Q[(Request broker)]
    Q --> W1["Worker pod 1: pool max 12"]
    Q --> W2["Worker pod 2: pool max 12"]
    Q --> W3["Worker pod 3: pool max 12"]
    Q --> W4["Worker pod 4: pool max 12"]
    W1 --> D[(Business DB)]
    W2 --> D
    W3 --> D
    W4 --> D
    M --> R[(JobRepository)]
    W1 --> R
    W2 --> R
    W3 --> R
    W4 --> R
~~~

Bốn pool `max=12` có trần cấu hình **48 connection** tới business DB, không phải 12. Tăng lên 16 pod giữ nguyên pool max tạo trần 192, dù mỗi pod thực tế chỉ có ít thread active.

## 4. Lập ngân sách connection toàn cụm

Xem mỗi **database instance** là một ngân sách hữu hạn. Một trần cấu hình bảo thủ:

\[
C_{\mathrm{configured}}=
\sum_{r \in \mathrm{roles}}
N_r\times P_r + C_{\mathrm{other}}
\]

Trong đó `N_r` là số pod có thể cùng tồn tại của role `r`, `P_r` là pool max của mỗi pod tới DB instance đang xét, còn `C_{\mathrm{other}}` là phần dành cho ứng dụng khác. Phải thỏa:

\[
C_{\mathrm{configured}}\le C_{\mathrm{usable}}
\]

`C_{\mathrm{usable}}` là số connection DBA thực sự cho workload sử dụng **sau khi chừa headroom** cho admin, monitoring, failover và biến động. Đây là **upper bound budgeting**, không phải số connection active hay số session luôn được pool mở.

### Ví dụ business DB

Giả sử PostgreSQL cho phép 250 connection; chừa 50 cho vận hành và burst nên ngân sách còn **200**.

| Nguồn kết nối | Số instance | Pool max mỗi instance | Trần |
|---|---:|---:|---:|
| Web/API và ứng dụng khác | — | — | 50 |
| Manager có business query | 2 | 6 | 12 |
| Worker | 8 | 14 | 112 |
| **Tổng** | | | **174** |

Headroom còn `200-174=26`. Nếu worker tăng từ 8 lên 12 pod mà giữ `max=14`, riêng worker được phép mở tới 168 connection; tổng là `50+12+168=230`, **vượt ngân sách 200**. Đừng vội tăng `max_connections`: nếu DB CPU/IO/lock đã bão hòa, thêm session thường làm contention xấu hơn.

### Ví dụ metadata DB tách biệt

Metadata database có ngân sách riêng 100 connection:

| Nguồn | Số instance | Pool max | Trần |
|---|---:|---:|---:|
| Manager | 2 | 5 | 10 |
| Worker | 8 | 3 | 24 |
| Monitoring/ops/khác | — | — | 20 |
| **Tổng** | | | **54** |

Metadata DB còn headroom 46. **Không cộng** 54 connection metadata vào 174 business rồi so với một `max_connections` duy nhất nếu đó là hai DB instance độc lập. Nếu business và metadata chỉ là hai schema/database trên **cùng một PostgreSQL instance**, mọi pool vào instance đó vẫn phải tính chung giới hạn.

### Những tình huống phải tăng hệ số an toàn

- **HPA/autoscaling:** tính theo `maxReplicas` có thể xảy ra, không theo pod hiện tại.
- **Rolling deployment:** trong thời gian ngắn có cả pod cũ/mới; tính cả `maxSurge`.
- **Manager HA:** có thể có hai manager application cùng tạo pool ngay cả khi chỉ một manager launch job.
- **Nhiều DataSource:** một pod có thể mở business pool, metadata pool và read-replica pool.
- **Nhiều application context/tenant:** có nguy cơ tạo thêm HikariDataSource ngoài ý muốn.
- **Migration/monitoring:** cần connection ngay trong lúc hệ thống đang cao tải.
- **Database proxy/PgBouncer:** thay đổi tính toán server sessions tùy mode; không tự xóa bỏ lock/contention hoặc checkpoint semantics.

## 5. Chọn worker concurrency theo connection thực tế

Một phép ước lượng sơ bộ ở **mỗi pod**:

\[
T_{\mathrm{active}}\times K_{\mathrm{conn/exec}}
\lesssim P_{\mathrm{businessPool}}
\]

`T_{\mathrm{active}}` là số execution có thể đồng thời cần DB; `K_{\mathrm{conn/exec}}` là số connection **có thể bị giữ đồng thời theo pattern đo được**, không phải hằng số do Spring Batch cam kết. Nếu mỗi partition giữ cursor connection và writer mượn thêm một transaction connection thì `K` có thể lớn hơn 1. Nếu reader đọc file, processor CPU-bound và writer chỉ mượn DB trong thời gian ngắn thì usage khác.

### Đừng áp “hai connection mỗi worker” cho mọi job

Ví dụ một pod có 6 partition active, mỗi reader giữ một cursor connection trong suốt step và sáu writer transaction có thể active cùng lúc. Pool max 6 có thể khiến writer đợi connection dù reader đang đọc bình thường. Ngược lại, một file reader có thể không mượn business DB connection nào trong giai đoạn đọc.

Thay vì đặt pool theo một công thức cứng:

1. Đo **thời gian giữ connection** của reader, writer và transaction.
2. Đo `active/idle/pending` trong các đỉnh tải, không chỉ trung bình.
3. Tính ngân sách toàn cụm và giới hạn DB.
4. Giảm concurrency hoặc sửa transaction khi DB quá tải.
5. Chỉ tăng pool khi còn capacity **và** số liệu chứng minh chờ pool là bottleneck.

## 6. Cấu hình HikariCP cơ bản với Spring Boot

Với **một `DataSource`** do Spring Boot auto-configure và HikariCP làm pool:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/business
    username: ${DB_USER}
    password: ${DB_PASSWORD}
    hikari:
      pool-name: business-batch-pool
      maximum-pool-size: 12
      minimum-idle: 2
      connection-timeout: 30000
      validation-timeout: 5000
      idle-timeout: 600000
      max-lifetime: 1800000
      keepalive-time: 120000
~~~

Đây là **giá trị minh họa**, không phải baseline tốt nhất cho mọi workload. Các duration property Hikari trong ví dụ dùng millisecond. Cần so với database/network/proxy timeout và kiểm thử với số pod thực tế. Không đưa credential thật vào source; chỉ tham chiếu environment variable.

| Property | Vai trò | Lỗi cấu hình thường gặp |
|---|---|---|
| `maximumPoolSize` | Giới hạn tổng connection của **một pool** | Quá thấp gây wait, quá cao làm DB quá tải |
| `minimumIdle` | Mức idle pool cố duy trì | Nhiều replica giữ idle connection gây lãng phí |
| `connectionTimeout` | Thời gian chờ mượn connection trước khi báo lỗi | Quá dài che nghẽn, quá ngắn dễ timeout transient |
| `validationTimeout` | Giới hạn thời gian xác thực connection | Không đặt dài hơn acquisition timeout |
| `idleTimeout` | Thời gian một idle connection có thể bị rút khỏi pool | Không dùng để giới hạn transaction |
| `maxLifetime` | Giới hạn tuổi physical connection, không ngắt connection đang dùng ngay lập tức | Quá dài so với network idle lifetime gây stale connection |
| `keepaliveTime` | Giữ kết nối idle còn sống theo thời gian | Phải phù hợp maxLifetime và hạ tầng |
| `leakDetectionThreshold` | Cảnh báo connection giữ lâu | Long cursor/transaction hợp lệ có thể bị báo nhầm |
| `poolName` | Định danh pool trong log/metric | Trùng tên làm khó phân biệt business/metadata |

HikariCP có default riêng; không nên mặc định số `minimumIdle` nhỏ nếu chưa cấu hình rõ. Nhiều pod với pool cố duy trì số idle cao có thể chiếm nhiều connection dù chưa làm việc.

### Pool timeout không phải SQL timeout

~~~text
Hikari connectionTimeout:
    Mượn connection từ pool kịp hay không?

JDBC queryTimeout / PostgreSQL statement_timeout:
    Một câu SQL được chạy tối đa bao lâu?

Spring transaction timeout:
    Transaction nghiệp vụ có thời hạn bao lâu?

Driver socket/network timeout:
    Đợi I/O từ database bao lâu?
~~~

Khi gặp `Connection is not available, request timed out`, điều tra acquisition/pool starvation trước; tăng `statement_timeout` không tạo thêm connection.

## 7. Tách business pool và JobRepository pool

Business workload có thể giữ connection lâu do cursor và writer, trong khi `JobRepository` cần cập nhật trạng thái/chunk checkpoint. Nếu cả hai dùng chung một pool nhỏ, business SQL có thể khiến metadata cũng chậm. Một thiết kế là **hai Hikari pool** với budget riêng:

~~~mermaid
flowchart TB
    J[Manager / Worker Spring Batch] --> BP[Business Hikari pool]
    J --> MP[Metadata Hikari pool]
    BP --> DB[(Business DB)]
    MP --> META[(JobRepository metadata DB)]
    T[TaskExecutor / StepExecution] --> BP
    T --> MP
~~~

**Tách pool không tự động tách database instance**: nếu cả hai pool cùng trỏ một PostgreSQL instance, chúng vẫn sử dụng chung giới hạn `max_connections`. Lợi ích là phân bổ budget và tránh một loại workload mượn toàn bộ slot của loại còn lại **trong một JVM**.

### Java config tạo hai HikariDataSource

~~~java
import com.zaxxer.hikari.HikariDataSource;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class BatchDataSourcesConfiguration {

    @Bean(name = "businessDataSource", destroyMethod = "close")
    @ConfigurationProperties(prefix = "app.datasource.business")
    public HikariDataSource businessDataSource() {
        return new HikariDataSource();
    }

    @Bean(name = "batchMetadataDataSource", destroyMethod = "close")
    @ConfigurationProperties(prefix = "app.datasource.metadata")
    public HikariDataSource batchMetadataDataSource() {
        return new HikariDataSource();
    }
}
~~~

Ví dụ custom properties:

~~~yaml
app:
  datasource:
    business:
      jdbc-url: jdbc:postgresql://business-db:5432/app
      username: ${BUSINESS_DB_USER}
      password: ${BUSINESS_DB_PASSWORD}
      pool-name: business-pool
      maximum-pool-size: 12
      minimum-idle: 2
      connection-timeout: 30000
    metadata:
      jdbc-url: jdbc:postgresql://metadata-db:5432/batch
      username: ${BATCH_DB_USER}
      password: ${BATCH_DB_PASSWORD}
      pool-name: metadata-pool
      maximum-pool-size: 4
      minimum-idle: 1
      connection-timeout: 30000
~~~

**Lưu ý:** đoạn này **chỉ tạo hai pool**, chưa cấu hình `JobRepository`. Phải wiring rõ datasource/transaction manager của metadata theo Spring Batch/Boot version đang dùng, đồng thời business step phải dùng đúng business datasource/transaction manager. Không thêm `@Primary` ngẫu nhiên rồi giả định repository tự chọn pool đúng.

Một integration test cần chứng minh:

1. Manager và worker remote truy cập cùng **metadata DB/schema**, các `BATCH_*` tables nằm đúng nơi.
2. Writer/reader dùng **businessDataSource**, không bị tự động nối vào metadata datasource.
3. Khi business pool bị giữ hết connection, metadata pool vẫn có headroom phù hợp.
4. Spring Boot không âm thầm tạo **một pool thứ ba** do cấu hình auto-configuration chồng nhau.

Nếu hai DataSource trỏ đến hai database/resource manager khác nhau, commit business data và metadata không tự động thuộc **một distributed transaction**. Retry/restart, outbox/idempotency phải tính ranh giới này.

## 8. JDBC cursor reader có thể giữ connection xuyên nhiều chunk

`JdbcCursorItemReader` có state: JDBC cursor, connection và vị trí checkpoint. Với nhiều partition, mỗi reader target riêng có thể giữ một connection **từ `open()` đến `close()`**. Writer transaction cùng lúc có thể sử dụng connection khác.

~~~mermaid
sequenceDiagram
    participant R as JdbcCursorItemReader
    participant P as Business HikariCP
    participant D as PostgreSQL
    participant W as Chunk Writer
    R->>P: open(), lấy connection cursor
    P->>D: Mở cursor/query
    loop Qua nhiều chunk
        R->>D: read() từ cursor
        W->>P: Mượn connection transaction
        P->>D: INSERT/UPDATE batch
        W->>P: Commit, trả connection transaction
    end
    R->>P: close(), trả cursor connection
~~~

Sơ đồ thể hiện **một khả năng tài nguyên**, không khẳng định mọi driver/cấu hình giữ đúng hai connection. `JdbcCursorItemReader` có `useSharedExtendedConnection` và tùy chọn `ExtendedConnectionDataSourceProxy`; không tự bật chỉ để tiết kiệm slot khi chưa hiểu holdability/transaction semantics của JDBC driver.

### Các phép đo bắt buộc

- Mỗi reader giữ connection bao lâu giữa `open` và `close`?
- Có bao nhiêu `StepExecution` đồng thời giữ cursor?
- Driver streaming theo `fetchSize` hay buffer toàn bộ result set?
- `JdbcCursorItemReader` có dùng connection riêng khỏi writer transaction không?
- Pool active gần max dù CPU thấp vì cursor đang giữ connection?
- Reader được đóng khi exception/stop/restart không?

### Cursor, paging và keyset

| Reader | Ưu điểm | Rủi ro |
|---|---|---|
| `JdbcCursorItemReader` | Quét tuần tự, giữ vị trí đọc | Giữ connection lâu; kiểm tra driver/fetch/checkpoint |
| `JdbcPagingItemReader` | Đọc theo page, có thể trả connection sớm hơn | Phải có sort key duy nhất/ổn định và snapshot dữ liệu |
| Custom keyset reader | `WHERE id > :lastId ORDER BY id` | Cần tự thiết kế checkpoint key đã commit |
| File/object reader | Giảm nhu cầu DB connection của reader | Writer và metadata vẫn cần DB; có thể nghẽn object storage |

Không thay reader chỉ để giảm active connection rồi mất restartability. Paging/offset trên dữ liệu bị insert/update/delete có thể đọc trùng/thiếu; keyset cần cutoff/snapshot và checkpoint rõ ràng.

## 9. Chunk size và thời gian giữ connection

Chunk-oriented step thường xử lý một nhóm item rồi commit:

~~~text
begin transaction
  read chunk items (theo reader semantics)
  process items
  write batch
commit transaction + checkpoint
~~~

Đây là sơ đồ đơn giản; read-ahead, buffering, retry, skip và cursor lifecycle có thể làm chi tiết khác. **`chunk(200)` không tạo 200 JDBC connection**. Chunk size ảnh hưởng thời gian transaction giữ connection, lock, bộ nhớ và chi phí rollback.

| Chunk size | Lợi ích có thể có | Rủi ro |
|---|---|---|
| 10 | Transaction ngắn, ít item đọc lại sau rollback | Nhiều commit/metadata updates |
| 100 | Điểm xuất phát dễ benchmark | Phụ thuộc row size/SQL/processor |
| 1000 | Giảm overhead commit, tận dụng batch write | Buffer/transaction lớn, lock lâu |
| 10000 | Hiệu quả với thao tác rẻ, memory đủ | Retry/rollback lớn và pool hold time cao |

Nếu một processor gọi HTTP bên trong transaction sau khi đã thực hiện SQL, connection có thể bị giữ trong suốt thời gian chờ mạng. Đây là một nguyên nhân Hikari active cao mà PostgreSQL CPU vẫn thấp.

~~~java
// Anti-pattern minh họa: network call chậm bên trong DB transaction.
@Transactional
public void saveAndNotify(Order order) {
    repository.save(order);        // Transaction có thể đã giữ connection.
    externalApi.send(order);       // Chờ mạng; connection chưa trả.
}
~~~

Đoạn code chỉ minh họa một method/service với các dependency ứng dụng; không phải class Java hoàn chỉnh. Tùy transaction manager, connection có thể được mượn khi SQL đầu tiên xảy ra, không nhất thiết ngay đầu method. Giải pháp thường là **rút ngắn transaction**, dùng outbox/idempotent event delivery và đặt downstream timeout/backpressure phù hợp.

## 10. Nested transactions và pool starvation

Một trường hợp nguy hiểm là tất cả worker thread đang giữ connection transaction A, rồi đồng thời gọi service cần một connection mới qua `PROPAGATION_REQUIRES_NEW`:

~~~text
Business pool max = 8
8 threads đang giữ 8 transaction connections
Mỗi thread gọi @Transactional(REQUIRES_NEW)
Mỗi lời gọi phải mượn connection thứ hai
Pool còn 0 idle -> 8 threads chờ
Transaction ngoài không kết thúc để trả connection
=> acquisition timeout / pool starvation
~~~

Hướng giải quyết:

1. Giảm số transaction ngoài đồng thời.
2. Thiết kế lại transaction boundary nếu không cần `REQUIRES_NEW`.
3. Khi bắt buộc dùng nested transaction, **dành thêm connection budget**, tính trường hợp tất cả thread cùng đi vào nhánh này.
4. Không mở thêm `CompletableFuture`/`@Async` làm DB work ngoài kiểm soát của TaskExecutor/partition handler.
5. Đo Hikari pending, acquire p95, thread dump và database wait trước khi thay đổi pool.

Một executor queue **không giới hạn** còn có thể giữ rất nhiều request/in-flight items trong heap dù số thread active bị chặn. Cần giới hạn thread, queue và request dispatch để tạo **backpressure**.

## 11. Cấu hình TaskExecutor có giới hạn

Trong Spring Batch 5.2.x, một multi-threaded step có thể sử dụng `TaskExecutor`. Ví dụ cấu hình một pool 4 chunk thread có queue giới hạn:

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class BoundedChunkConcurrencyConfiguration {

    @Bean("chunkTaskExecutor")
    public ThreadPoolTaskExecutor chunkTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("batch-chunk-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(60);
        return executor;
    }

    @Bean
    public Step transformStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ItemReader<InputRow> reader,
            ItemProcessor<InputRow, OutputRow> processor,
            ItemWriter<OutputRow> writer,
            TaskExecutor chunkTaskExecutor) {

        return new StepBuilder("transformStep", jobRepository)
                .<InputRow, OutputRow>chunk(200, transactionManager)
                .reader(reader)
                .processor(processor)
                .writer(writer)
                .taskExecutor(chunkTaskExecutor)
                .build();
    }
}
~~~

`InputRow` và `OutputRow` là các kiểu DTO của ứng dụng; reader/processor/writer/transaction manager phải là các bean phù hợp. Ví dụ này giải thích cách nối executor, **không phải job hoàn chỉnh chỉ cần copy-paste là chạy**.

**Cảnh báo:** `taskExecutor(...)` có thể chạy nhiều chunk thread trong **cùng một `StepExecution`**. Nếu dùng `FlatFileItemReader` hoặc `JdbcCursorItemReader` không thread-safe, việc tăng thread có thể làm trùng/thiếu item và hỏng checkpoint. `@StepScope` tạo instance theo **StepExecution**, không tự tạo instance riêng cho mỗi chunk thread.

Khi dữ liệu chia được theo ID/file/range thời gian, **partitioning** với nhiều `StepExecution` và reader `@StepScope` riêng thường dễ quản lý cursor/checkpoint hơn. Trong local partitioning, executor giới hạn số partition đồng thời; trong remote partitioning, giới hạn consumer/process concurrency và pool budget trên từng pod.

### Executor và pool không cần bằng nhau

Nếu executor có 4 chunk thread nhưng Hikari pool max 12, điều đó không có nghĩa cần tăng executor lên 12. Nếu CPU, DB lock hoặc I/O đang nghẽn, thêm thread làm hiệu năng xấu hơn. Ngược lại, nếu 4 partition active đều giữ cursor và còn writer transaction, business pool max 4 có thể thiếu. **Chọn cả hai theo thời gian giữ connection thực tế**.

## 12. Quan sát HikariCP và Spring Batch cùng lúc

HikariCP có các chỉ số active, idle, total và waiting; khi tích hợp Spring Boot Actuator/Micrometer, một số metric thường có tiền tố `hikaricp.connections.*` tùy binder/version. Metric chỉ có ý nghĩa khi gắn với **đúng pool name và worker role**.

| Metric | Câu hỏi chính | Cách diễn giải |
|---|---|---|
| Hikari active | Bao nhiêu connection đang được mượn? | So với max và thời lượng; không chỉ một spike |
| Hikari idle | Có connection sẵn sàng không? | Xem cùng pending |
| Hikari pending | Bao nhiêu thread chờ connection? | Pending kéo dài là dấu hiệu cần điều tra |
| Hikari total/max | Pool mở và cho phép bao nhiêu connection? | Nhân theo số pod toàn cụm |
| Connection acquire time | Mượn connection mất bao lâu? | So p95/p99 trước và sau scale |
| Connection usage time | Connection được giữ trong bao lâu? | Phân biệt cursor lâu với transaction chậm |
| Acquire timeout errors | Bao nhiêu lần không mượn kịp? | Không nên tăng khi tăng concurrency |
| Batch read/write/commit/rollback | Các partition có tiến lên không? | Đối soát output và tỷ lệ retry |
| JDBC query latency | DB chậm hay app giữ connection lúc chờ việc khác? | Xem SQL plan, wait event và CPU/IO |

**Không dùng `active == max` làm tiêu chí lỗi duy nhất.** Khi active=max nhưng pending gần 0 và throughput ổn định, pool có thể đang sử dụng tài nguyên hiệu quả. Khi pending kéo dài, acquire p95 tăng và timeout tăng, mới có bằng chứng về áp lực pool.

### Đọc Hikari MXBean để chẩn đoán

~~~java
import com.zaxxer.hikari.HikariDataSource;
import com.zaxxer.hikari.HikariPoolMXBean;

record PoolSnapshot(
        int active, int idle, int total, int waiting) {}

public final class PoolInspector {
    public static PoolSnapshot snapshot(HikariDataSource ds) {
        HikariPoolMXBean bean = ds.getHikariPoolMXBean();
        return new PoolSnapshot(
                bean.getActiveConnections(),
                bean.getIdleConnections(),
                bean.getTotalConnections(),
                bean.getThreadsAwaitingConnection());
    }
}
~~~

Đây là code **đọc metric**, không phải logic tự thay pool size trong mỗi request. `getHikariPoolMXBean()` đòi hỏi datasource đã được khởi tạo; với Spring Boot, nên ưu tiên Micrometer/Actuator thay vì tự poll liên tục. Không nhầm `businessDataSource` với `batchMetadataDataSource` khi thu số liệu.

### Tránh metric cardinality quá cao

~~~text
jobName, stepName, poolName, workerRole
  -> time series metrics: throughput, active, pending, latency

jobExecutionId, stepExecutionId, partitionName, workerInstanceId
  -> structured logs / traces để tương quan sự cố
~~~

Execution IDs thường tăng liên tục; nếu thêm mỗi ID thành một label lâu dài của mọi metric, số chuỗi thời gian có thể bùng nổ. Dùng các tag có cardinality kiểm soát để so sánh pool và job types, đưa ID cụ thể vào log/trace.

### Cùng số active, hai nguyên nhân khác nhau

- **A:** Hikari active=max, PostgreSQL CPU cao, nhiều SQL chạy. Nút thắt có thể là query/index/I/O hoặc CPU DB; thêm connection thường không giải quyết.
- **B:** Hikari active=max, PostgreSQL CPU thấp, nhiều thread chờ mạng hoặc transaction `idle in transaction`. Nút thắt có thể là code giữ connection quá lâu; cần xem transaction boundary.
- **C:** Hikari active thấp, pending=0, job chậm. Bottleneck có thể nằm ở CPU processor, broker queue, file/object storage hoặc upstream API, không phải pool.

## 13. Chẩn đoán bằng PostgreSQL

Một truy vấn **read-only** để tổng hợp session/wait event (nếu user có quyền quan sát phù hợp):

~~~sql
SELECT state,
       wait_event_type,
       wait_event,
       count(*) AS connection_count
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY state, wait_event_type, wait_event
ORDER BY connection_count DESC;
~~~

Có thể thêm `application_name` vào JDBC connection properties và nhóm theo ứng dụng:

~~~sql
SELECT application_name,
       state,
       count(*) AS connections
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY application_name, state
ORDER BY connections DESC;
~~~

Những state/wait event cần phân biệt:

| PostgreSQL signal | Diễn giải |
|---|---|
| `state = 'active'` | Session đang xử lý query hoặc hoạt động |
| `state = 'idle'` | Connection đang sẵn để nhận lệnh; không tự động là lỗi |
| `state = 'idle in transaction'` | Transaction mở nhưng đang chờ, có thể giữ lock/snapshot |
| `wait_event_type = 'Lock'` | Chờ khóa; tăng pool có thể làm tệ hơn |
| `wait_event_type = 'IO'` | Chờ I/O; xem query plan, storage và cache |
| Nhiều session nhưng CPU DB thấp | Cần đối chiếu transaction hold time và client activity |

Nếu Hikari active cao nhưng PostgreSQL `state='idle'`, có thể ứng dụng đã mượn connection rồi chưa chạy SQL trong thời điểm đo. Kết luận cần dựa trên **thread dump, transaction/connection usage time và query traces**, không suy đoán từ duy nhất một snapshot.

Không công khai raw `pg_stat_activity.query` nếu SQL text có thể chứa dữ liệu nhạy cảm; áp quyền DB và logging tối thiểu.

## 14. Phân biệt leak, long transaction và retry storm

| Anti-pattern | Triệu chứng | Cách khắc phục |
|---|---|---|
| Mỗi item tạo `new HikariDataSource()` | Nhiều pool/socket, không kiểm soát budget | Một pool theo process/role, đóng qua lifecycle |
| Scale pod không cập nhật ngân sách | DB hết connection | Nhân replicas × pool max, tính HPA/surge |
| HTTP call chậm trong transaction | Hikari active cao, DB CPU thấp | Outbox/async delivery, rút ngắn transaction |
| `REQUIRES_NEW` nested trên mọi thread | Mượn connection thứ hai không được | Giảm concurrency hoặc bỏ nested transaction |
| Quá nhiều cursor reader | Connection active gần max lúc step start | Giảm partition active, xem paging và driver |
| Pool lớn, writer tranh hot rows | DB lock wait tăng | Giảm đồng thời, tối ưu SQL/transaction |
| Retry ngay khi timeout | Retry storm, pool càng nghẽn | Backoff/jitter/rate limit và circuit breaker phù hợp |
| Metadata chung pool business | Checkpoint chậm khi business nghẽn | Tách pool/budget, kiểm tra transaction semantics |
| Executor queue không giới hạn | Heap tăng, shutdown lâu | Bounded queue và backpressure |
| Leak threshold quá thấp | Log “possible leak” ồ ạt | Kiểm tra cursor/transaction trước khi kết luận |

### Leak thật và connection giữ lâu

**Leak thật** xảy ra khi một đường code không trả connection/resource theo lifecycle, chẳng hạn quên `close()` sau khi tự gọi `getConnection()` hoặc cất connection trong field singleton. Nhưng `JdbcCursorItemReader` cố ý giữ cursor đến cuối step có thể kích hoạt `leakDetectionThreshold` dù `close()` vẫn được gọi khi hoàn tất.

Trong code JDBC tự quản lý resource, dùng `try-with-resources`:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import javax.sql.DataSource;

public long countRows(DataSource ds) throws Exception {
    try (Connection connection = ds.getConnection();
         PreparedStatement ps = connection.prepareStatement(
                 "SELECT count(*) FROM business_events");
         ResultSet rs = ps.executeQuery()) {
        rs.next();
        return rs.getLong(1);
    }
}
~~~

Đoạn này là **một method minh họa trong class Java**. Trong transaction do Spring quản lý, ưu tiên `JdbcTemplate`/transaction-aware APIs, không tự đóng một connection do transaction manager đang kiểm soát. Không cất connection mượn từ pool vào field singleton để nhiều thread cùng dùng.

### Khi nào tăng `maximumPoolSize` có hại?

Nếu mọi transaction đang chờ cùng một row lock, tăng từ 10 lên 40 connection có thể tạo thêm 30 transaction tranh chấp và tăng latency, không thêm throughput. Nếu DB storage có IOPS giới hạn, thêm reader cursor có thể làm các phiên đọc cạnh tranh nhau. Nếu CPU worker mới là nút thắt, tăng DB pool thường không có tác dụng.

## 15. Pool timeout, retry và restart Spring Batch

Khi không mượn được JDBC connection trước `connectionTimeout`, một chunk có thể rollback, một partition có thể `FAILED` hoặc step có thể retry tùy fault-tolerance configuration. Connection pool ảnh hưởng **hiệu năng lẫn khả năng phục hồi**.

~~~mermaid
flowchart TD
    A[Concurrent StepExecutions] --> B{Borrow DB connection}
    B -->|Thành công| C[Read/write + commit]
    B -->|Vượt connectionTimeout| D[Acquisition exception]
    D --> E[Rollback / FAILED / retry theo policy]
    E --> F{DB/pool còn nghẽn?}
    F -->|Có| G[Retry storm, pending tăng]
    F -->|Không| H[Restart đúng JobInstance]
    H --> I[Checkpoint + idempotent writer]
    I --> C
~~~

Khi restart job lỗi:

1. Giữ **cùng identifying `JobParameters`** của `JobInstance` bị lỗi nếu muốn resume bằng metadata.
2. Giữ partition plan, input snapshot/cutoff, tên step và tên `ItemStream` ổn định.
3. Kiểm tra writer idempotency; chunk có thể đã tạo side effect trước khi metadata update.
4. Không coi pool timeout là bằng chứng mọi transaction nghiệp vụ đã rollback hoặc chưa ghi gì.
5. Nếu là remote worker, xác minh execution cũ đã dừng trước khi re-dispatch, tránh chạy song song.

### Chặn retry storm

Nếu 100 worker cùng timeout và retry ngay lập tức, số request chờ có thể tăng nhanh hơn tốc độ DB phục hồi. Cần **giới hạn retry**, backoff/jitter và giảm concurrency khi downstream quá tải. Pool starvation do `REQUIRES_NEW` không được chữa bằng lặp retry vô hạn.

### Metadata DB và business DB không tự có transaction toàn cục

`JobRepository` ghi checkpoint metadata; writer có thể ghi business DB; broker có ACK riêng. Không mặc định ba hệ thống tham gia cùng **distributed transaction**. Với DB writer, dùng unique constraint/upsert và đối soát; với event/API side effect, cân nhắc transactional outbox và idempotency key.

## 16. Benchmark tìm điểm cân bằng giữa worker và pool

Thiết kế benchmark trên **cùng immutable input snapshot**, schema/index, CPU/IO capacity và transaction policy. Thay đổi **một biến mỗi lượt** để biết chính xác nguyên nhân.

| Lần thử minh họa | Active worker executions | Pool max mỗi worker | Phép đo |
|---|---:|---:|---|
| A | 1 | 8 | Throughput gốc, query latency, connection usage |
| B | 2 | 8 | Speedup và DB lock/IO |
| C | 4 | 8 | Acquire p95 và pending |
| D | 8 | 8 | Reader cursor và writer connection có tranh slot không? |
| E | 16 | 8 | Timeout/lock/IO có vượt lợi ích concurrency không? |

**Các con số là cấu hình thí nghiệm, không phải kết quả đo.** Nếu 16 execution cùng giữ cursor và còn cần writer transaction, pool 8 có thể bị starvation ngay từ đầu. Nếu mỗi execution hiếm khi cần DB, pool 8 có thể vẫn đủ.

### Tiêu chí đánh giá kết quả

Một thay đổi chỉ được xem là cải thiện khi:

- Wall-clock giảm hoặc throughput tăng với **cùng tập input**.
- Database CPU, IOPS, lock wait, memory trong ngưỡng an toàn.
- Hikari acquire p95/p99, pending và timeout không tăng bất thường.
- Không tạo retry storm, deadlock hoặc partition skew mới.
- Tập business keys output/chunk checkpoint vẫn chính xác, restart vẫn an toàn.

Nếu tăng từ 8 lên 16 worker chỉ khiến pending và lock wait tăng mà throughput không đổi, giảm concurrency có thể là phương án tốt hơn tăng pool.

### Little's Law chỉ là công cụ ước lượng

Trong hệ thống tương đối ổn định:

\[
L\approx \lambda \times W
\]

Với `L` là số request/transaction đang ở hệ thống trung bình, `\lambda` throughput và `W` thời gian trung bình. Khi SQL chậm làm connection hold time tăng, số connection cần để giữ cùng throughput cũng có thể tăng.

Tuy nhiên, không dùng công thức này để **ấn định pool max** khi workload bursty, có cursor giữ lâu, nested transactions hay DB đang bão hòa. Cần đo p95/p99, concurrency distribution và headroom.

## 17. Runbook khi Hikari báo hết connection

### Bước 1 — Xác định đúng pool và đúng worker

Lấy `poolName`, pod/instance, `jobExecutionId`, `stepExecutionId`, số worker replicas và executor active. Xác định business pool hay metadata pool bị cạn; có thể chỉ một bên nghẽn.

### Bước 2 — Ghép số liệu client với database

Đọc Hikari active/idle/total/pending, acquire time, connection usage, timeout count. Đối chiếu PostgreSQL `pg_stat_activity`, `wait_event`, lock wait, query latency và DB CPU/IO. Không kết luận bằng một metric duy nhất.

### Bước 3 — Kiểm tra lifecycle connection

- Có cursor reader giữ connection quá lâu không?
- Có transaction mở rồi gọi HTTP/gRPC hoặc chờ `Future.get()` không?
- Có nested `REQUIRES_NEW` hoặc async work cần connection thứ hai không?
- Có JDBC code tự quản lý nhưng quên `close()` không?
- Có hơn một HikariDataSource ngoài ý muốn do Boot auto-configuration không?

### Bước 4 — Kiểm soát tốc độ

Tạm giảm số worker/chunk threads/partition concurrency để bảo vệ DB, sau đó kiểm tra throughput có phục hồi. Không tăng `max_connections` chỉ để vượt qua tình huống overload.

### Bước 5 — Chọn giải pháp theo nguyên nhân

- Pool budget sai: điều chỉnh `maximumPoolSize`, `minimumIdle` và concurrency theo toàn cụm.
- SQL chậm: tối ưu index, query plan, partition pruning và IO.
- Long transaction: rút ngắn boundary, tách HTTP/event qua outbox.
- Cursor giữ lâu: giảm partition active hoặc đánh giá paging/keyset có checkpoint.
- Lock contention: giảm writer concurrency, tối ưu transaction và unique key.
- Retry storm: backoff, jitter, giới hạn retry và rate limiting.

### Bước 6 — Restart và đối soát

Khi hạ tầng ổn định, restart các execution lỗi theo `JobRepository`; giữ input/partition plan và writer idempotent. **Đối soát tập khóa output**, không chỉ tổng `readCount` hay `writeCount`, vì một ID trùng và một ID thiếu có thể triệt tiêu nhau về số lượng.

### Bước 7 — Ngăn lặp lỗi

Đưa budget pool vào kiểm tra khi thay đổi HPA/rolling update. Bật cảnh báo pending/timeout, DB connection headroom và benchmark theo mức concurrency an toàn. Mọi thay đổi pool max phải được xét cùng **maxReplicas**, không chỉ replica hiện tại.

## 18. Ma trận kiểm thử cần có

| Test | Cách tạo điều kiện | Tiêu chí đạt |
|---|---|---|
| Pool nhỏ hơn executor | 8 chunk threads, business pool max 4 | Có backpressure/timeout theo policy, không âm thầm sai dữ liệu |
| DB lock contention | Nhiều writer cập nhật cùng row | Nhận diện lock wait, không tăng pool mù quáng |
| Cursor giữ lâu | Nhiều `JdbcCursorItemReader` trên dataset lớn | Biết connection hold time, resource được đóng |
| Nested transaction | Mỗi thread giữ outer transaction và gọi `REQUIRES_NEW` | Phát hiện starvation, có thiết kế khắc phục |
| Hai datasource | Business pool max 12, metadata pool max 4 | `JobRepository` dùng đúng DB/pool |
| HPA 4 → 12 pod | Pool max cố định | Không vượt ngân sách connection toàn cụm |
| Rolling deploy | Pod cũ và mới cùng tồn tại | Budget vẫn đủ headroom |
| JDBC resource leak | Cố ý bỏ `close` trong test | Leak/usage cảnh báo, sửa và xác nhận cleanup |
| False leak warning | Cursor dài nhưng đóng ở cuối step | Không phân loại sai, vẫn đo tác động pool |
| Worker crash | Kill giữa chunk | Restart/checkpoint đúng, không trùng side effect |
| Broker redelivery | Giao lại một partition | Không xử lý trùng dữ liệu |
| DB outage | Tạm ngắt database | Retry có giới hạn, không tạo storm |
| Benchmark nhiều mức | 1/2/4/8/16 worker, cùng snapshot | So sánh throughput và output correctness |

### Vì sao test tổng số item chưa đủ?

Giả sử đầu vào có 1.000 ID; worker A ghi lặp ID 500, worker B bỏ ID 700. Tổng `writeCount` có thể vẫn bằng 1.000 nhưng dữ liệu **sai**. Test nên so sánh tập unique business keys, checksum/aggregate và trạng thái sau retry/restart, không chỉ cộng số đếm.

## 19. Checklist production

- [ ] Đã biết số worker pods tối đa, kể cả HPA và rolling update surge.
- [ ] Đã liệt kê mọi Hikari pool trên manager, worker và các service khác dùng cùng DB instance.
- [ ] Đã tính `replicas × maximumPoolSize` với reserved headroom.
- [ ] Đã phân biệt business DB và metadata DB (cùng hay khác instance).
- [ ] `JobRepository` thực sự dùng đúng metadata datasource/pool.
- [ ] `maximumPoolSize`, `minimumIdle`, `connectionTimeout`, `maxLifetime` có cơ sở đo.
- [ ] Không tạo pool theo từng item/chunk/request.
- [ ] Cursor reader được đóng đúng lifecycle `ItemStream`.
- [ ] Executor/partition handler giới hạn concurrency; không đồng nhất `gridSize` với số thread.
- [ ] Đã xem xét `REQUIRES_NEW`, long transaction, network call trong transaction.
- [ ] Reader/processor/writer có thread safety đúng mô hình.
- [ ] Đo active/idle/pending, connection usage/acquire p95, DB lock/IO/CPU và throughput.
- [ ] Retry/backoff giới hạn, không gây storm khi pool cạn.
- [ ] JobParameters, partition plan, checkpoint và input snapshot ổn định khi restart.
- [ ] Writer/side effect idempotent, có cơ chế chống trùng.
- [ ] Benchmark nhiều mức worker và đối soát tập business keys.

## 20. Bài tập thực hành

### Bài tập 1 — Tính budget toàn cụm

PostgreSQL cho phép 240 connection, chừa 40 cho vận hành, 35 cho API và 15 cho monitoring. Manager có 2 pod pool max 5, worker có 6 pod pool max 18. Tính trần connection và headroom. Nếu HPA tăng lên 10 worker thì có vượt giới hạn? Thiết kế lại pool/concurrency để còn dự phòng.

### Bài tập 2 — Cursor + writer

Một pod chạy 5 partition đồng thời. Mỗi `JdbcCursorItemReader` giữ một connection, writer transaction có thể cần thêm một connection trong lúc commit. Với business pool max 6, dự đoán pending và timeout. Đo bằng Hikari metrics, so sánh khi chuyển sang paging reader có checkpoint ổn định.

### Bài tập 3 — REQUIRES_NEW starvation

Tạo 4 worker threads và pool max 4. Mỗi thread mở transaction, chạy một SQL rồi gọi `@Transactional(propagation = REQUIRES_NEW)` trên cùng datasource. Quan sát acquisition wait; thử hai hướng sửa: giảm concurrency và thiết kế lại transaction để bỏ nested borrow.

### Bài tập 4 — Business/metadata pools

Cấu hình business pool max 12, metadata pool max 4. Wiring `JobRepository` vào metadata datasource theo version đang dùng. Viết integration test chứng minh `BATCH_STEP_EXECUTION` ở đúng DB và output nghiệp vụ ở business DB. Nếu hai pool dùng chung một PostgreSQL instance, tính lại tổng connection.

### Bài tập 5 — Benchmark 1/2/4/8 worker

Chạy cùng snapshot 2 triệu row với SQL/index không đổi. Thu wall-clock, throughput, Hikari pending/acquire p95, DB CPU/IO, PostgreSQL wait event, commit/rollback và unique output keys. Tìm mức concurrency hợp lý, chỉ rõ bottleneck nằm ở pool, SQL, IO hay lock contention.

### Bài tập 6 — Runbook production

Job báo `HikariPool - Connection is not available, request timed out after 30000ms` khi tăng replicas từ 5 lên 15. Viết runbook: xác định pool, tính max connections theo pod, kiểm tra transaction hold, truy `pg_stat_activity`, giảm concurrency, restart lỗi an toàn và đối soát dữ liệu.

**Tự kiểm tra:** Vì sao `maximumPoolSize=10` không có nghĩa toàn cụm chỉ có 10 connection? Một chunk thread có luôn giữ đúng một connection không? `connectionTimeout` khác `statement_timeout` ra sao? Vì sao cursor reader có thể giữ connection lâu? Khi nào tăng pool làm throughput giảm? Tại sao metadata cần budget riêng? Vì sao retry ngay sau pool timeout có thể làm tình trạng xấu hơn? Làm sao chứng minh tăng worker không làm dữ liệu trùng/thiếu?

## 21. Tổng kết

**Connection pool khi nhiều worker** phải được thiết kế theo **toàn hệ thống**, không tối ưu riêng một pod. Trần connection tăng theo số process và pool; số connection active phụ thuộc transaction/cursor lifecycle, chunk size, SQL latency và concurrency. Không có công thức **“mỗi worker đúng một connection”** cho mọi Spring Batch job.

Để scale an toàn, cần **ngân sách connection cho business DB và `JobRepository`, HikariCP có giới hạn, concurrency/backpressure phù hợp, reader/writer đúng lifecycle, transaction ngắn, restart/idempotency và bộ metric nối được worker → pool → database → kết quả nghiệp vụ**. Chỉ tăng worker hoặc `maximumPoolSize` sau khi đã đo bottleneck thực tế và xác minh tính đúng dữ liệu.
