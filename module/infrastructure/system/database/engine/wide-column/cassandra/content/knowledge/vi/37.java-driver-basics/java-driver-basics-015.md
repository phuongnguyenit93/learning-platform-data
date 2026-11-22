# Giới hạn tài nguyên và tách cấu hình giữa môi trường

## 1. Tình huống: cấu hình Java Driver chạy tốt ở dev nhưng làm production quá tải

Một nhóm viết dịch vụ Java dùng **Apache Cassandra** để lưu sự kiện cảm biến. Ở môi trường phát triển, ứng dụng chỉ có một vài luồng, dữ liệu nhỏ và một node Cassandra. Để “tăng tốc”, người viết thử những thay đổi sau:

- Mỗi HTTP request tạo một `CqlSession` riêng rồi đóng lại.
- Tăng page size lên 10.000 vì không muốn fetch nhiều page.
- Tăng số kết nối và số request bất đồng bộ mà không giới hạn.
- Đặt timeout từ 2 giây thành 30 giây để giảm thông báo lỗi.
- Dùng cùng một file `application.conf`, tài khoản và địa chỉ Cassandra cho dev, staging, production.

Tất cả có thể “chạy được” trong máy phát triển. Nhưng khi production nhận 8.000 request/giây, hệ thống xuất hiện **in-flight requests phình to**, heap/GC tăng, các coordinator quá tải và p99 lên vài giây. Có những timeout mà client đã từ bỏ nhưng replica vẫn đang xử lý, rồi dịch vụ retry và tạo thêm tải.

**Vấn đề không chỉ là chỉnh vài con số.** Với Cassandra, Java Driver 4.x là **client phân tán có connection pooling, routing, request multiplexing, retry, paging và timeout**. Mỗi tham số thay đổi cả hiệu quả ứng dụng lẫn lượng việc gửi tới coordinator/replica. Cấu hình phải phản ánh **topology, consistency level, bảo mật và capacity** của từng môi trường.

Bài thuộc chương **Java driver cơ bản** trong mô-đun Cassandra, gắn kiến thức Java Driver với partition key, CQL, replication, đọc/ghi, lỗi, compaction và chẩn đoán vận hành.

**Kết quả mong đợi:**

1. Giải thích được vòng đời `CqlSession` và vì sao không tạo session cho từng request.
2. Phân biệt **connection count, in-flight requests, request throttling, page size, timeout, retry và tổng số byte đọc**.
3. Dự toán concurrency bằng workload và latency budget, không tăng connection pool mù quáng.
4. Cấu hình Java Driver 4.x bằng **HOCON, execution profiles** và cấu hình dev/staging/prod riêng, không nhúng secrets.
5. Viết CQL và Java sử dụng **prepared statement, `LOCAL_QUORUM`, bounded async concurrency**, xử lý lỗi và đo latency.
6. Thiết kế dashboard, cảnh báo, canary và quy trình thay đổi config có rollback.

> **Giới hạn phiên bản:** các ví dụ nhắm tới hệ API `com.datastax.oss.driver.api.*` của Apache Cassandra Java Driver 4.x. Tên option, giá trị mặc định, thuật toán pooling/throttling, metrics và khả năng reload khác theo **minor version hoặc bản phân phối**. Mọi con số là **giá trị thí nghiệm**, không phải khuyến nghị mặc định cho production. Xác minh tài liệu và cấu hình của phiên bản đang chạy trước khi áp dụng.

## 2. Driver nằm ở đâu trong đường đọc/ghi phân tán?

~~~mermaid
flowchart TD
    A["API / Java service"] --> B["Admission control / bounded queue"]
    B --> C["CqlSession, prepared statements, request profiles"]
    C --> D["Driver routing + connection pools + timeouts/retries"]
    D --> E["Coordinator Cassandra"]
    E --> F["Replica theo partition token + RF + CL"]
    F --> G["Memtable / SSTable / commit log / disk"]
    H["Metrics và tracing"] -.-> A
    H -.-> D
    H -.-> E
    H -.-> F
    I["JVM/OS resources"] -.-> C
    I -.-> G
~~~

Một thao tác `SELECT` theo partition key đi qua các lớp:

1. Ứng dụng nhận request, kiểm tra deadline và giới hạn concurrency.
2. Java Driver chọn execution profile, serialize/bind CQL, dùng route/connection tới một node phù hợp.
3. Node nhận request đóng vai trò **coordinator**, xác định natural replicas dựa trên token, RF và topology.
4. Coordinator thu thập phản hồi theo consistency level. Replica có thể phải quét SSTable, hòa giải phiên bản/tombstone và đọc disk.
5. Driver nhận response hoặc lỗi, decode rows và có thể fetch thêm page.

**Connection pool của driver không phải replica factor.** Thêm hai kết nối tới một coordinator không tạo hai bản sao dữ liệu; tăng RF cũng không tự cấp thêm connection pool. **CL không phải timeout**: `LOCAL_QUORUM` với RF = 3 cần hai phản hồi trong DC, nhưng mỗi phản hồi vẫn có thể chậm vì I/O, GC hoặc mạng.

### 2.1. Hai nhóm giới hạn độc lập

| Lớp | Giới hạn/điều khiển | Mục tiêu |
| --- | --- | --- |
| **Ứng dụng** | HTTP admission, request deadline, thread/queue pool, tenant quota. | Ngăn traffic ngoài khả năng ứng dụng và giữ SLO. |
| **Java Driver** | Pool/connection, in-flight/request throttler, page size, request timeout, retry policy. | Phân phối request tới Cassandra có kiểm soát. |
| **Cassandra coordinator** | Request handling, timeout, dropped tasks, tombstone/other guardrails. | Điều phối replica và bảo vệ node. |
| **Replica/JVM/OS** | CPU, heap, off-heap, commit log, SSTable, disk IOPS, network. | Giới hạn vật lý của đường thực thi. |
| **Hạ tầng** | Network policy, TLS, container quota, secret lifecycle, DC capacity. | Cô lập môi trường và bảo mật. |

Tăng một ngưỡng ở driver **không tăng** tài nguyên của node Cassandra. Cấu hình tốt cần phối hợp các lớp, không thay guardrail server bằng retry vô hạn ở client.

## 3. `CqlSession`: một đối tượng sống lâu, nhiều request

`CqlSession` giữ metadata cluster, topology/routing, connections, execution resources và prepared statements phục vụ nhiều request. Driver 4.x được thiết kế để tái sử dụng session an toàn từ nhiều luồng; cách dùng thông thường là **tạo một session cho một logical cluster/identity/cấu hình**, chia sẻ trong vòng đời service, rồi đóng có kiểm soát.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import java.net.InetSocketAddress;

public final class SessionLifecycleExample {
    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {
            // Dùng cùng session cho rất nhiều request trong vòng đời service.
            // Không tạo session mới trong từng handler HTTP.
            System.out.println("Cassandra session initialized");
        }  // Đóng session lúc service dừng hoặc khi chủ động thay thế.
    }
}
~~~

**Ví dụ trên chỉ dành cho lab.** Production cần TLS, authentication, contact points, local DC và tài nguyên cấu hình chuẩn. Với Spring hoặc framework DI, thường khai báo `CqlSession` là **singleton bean** do container quản lý; không đóng khi một request hoàn tất.

### 3.1. Vì sao tạo session cho mỗi request rất tốn?

Mỗi session mới có thể cần tạo connections, bắt tay TLS/authentication, tải metadata, khởi động tài nguyên của driver và chuẩn bị query. Khi traffic tăng, chúng gây:

- Nhiều TCP connections và TLS handshakes không cần thiết.
- Tăng heap, threads/buffers và chi phí garbage collection phía Java.
- Tăng metadata/control traffic tới Cassandra.
- Connection churn, `Too many open files` hoặc ephemeral port pressure.
- Mất lợi ích reuse prepared statements và khả năng chọn route ổn định.

**Không** có công thức “một `CqlSession` cho mỗi node”. Session có thể quản lý nhiều node và nhiều connection pools. Nếu ứng dụng thật sự truy cập **hai cluster độc lập, hai danh tính hoặc hai cấu hình an ninh khác nhau**, có thể cần những session riêng; phải tính riêng capacity và lifecycle cho mỗi session.

### 3.2. Prepared statement có thể tái sử dụng

~~~sql
-- CQL template; application sẽ bind các tham số.
SELECT event_time, event_id, payload
FROM telemetry_driver.events_by_device_day
WHERE device_id = ?
  AND event_day = ?
  AND event_time >= ?
  AND event_time < ?
LIMIT 100;
~~~

Nên chuẩn bị statement **một lần cho query template** (hoặc dùng cache có kiểm soát), rồi bind giá trị ở mỗi request. Tránh tạo CQL text khác nhau cho mỗi giá trị partition key: vừa tăng overhead, vừa có nguy cơ chèn dữ liệu không an toàn vào statement.

## 4. Connection pool của Cassandra không giống JDBC relational database pool

JDBC pool thường gán một connection cho transaction/request theo kiểu request “mượn–trả”. Cassandra native protocol hỗ trợ **nhiều request đồng thời trên cùng connection** (multiplexing) theo khả năng protocol/driver. Vì vậy:

| Câu hỏi | Hiểu đúng đối với Java Driver |
| --- | --- |
| “Một request cần một connection riêng?” | **Không.** Một connection có thể xử lý nhiều request in-flight. |
| “Tăng connection lên 100 lần thì throughput tăng 100 lần?” | **Không.** Coordinator/replica, network, queue, CPU và disk mới quyết định giới hạn. |
| “Một `CqlSession` chỉ kết nối tới contact point đầu tiên?” | **Không.** Contact point là điểm khám phá ban đầu; driver theo dõi topology và mở pools theo cấu hình/chính sách. |
| “Remote DC cần pool như local DC?” | **Không mặc định.** Routing và kết nối tới remote DC cần cân nhắc latency/chi phí, local DC và chính sách failover. |
| “Pool có thể giải quyết hot partition?” | **Không.** Một partition key vẫn định tuyến tới nhóm replica của token đó. |

### 4.1. Những gì phải đo trước khi tăng pool

- Số `CqlSession` trong process, **connections mở theo node**, in-flight requests theo connection/session.
- Request queue/throttler backlog, request acquire/wait time và timeout.
- p50/p95/p99 **phía client**, throughput, retry attempts và coordinator distribution.
- CPU/GC, direct memory/heap, file descriptors và network phía ứng dụng.
- CPU/GC, `nodetool tpstats`, SSTable/disk latency và dropped messages trên **replica**.

Pool thiếu thực sự và node dư capacity có thể là lý do để điều chỉnh. Nhưng nếu `tpstats` hoặc disk đang bão hòa, tăng pool thường chỉ giúp **đẩy thêm traffic tới nút nghẽn**.

## 5. In-flight, queue và deadline: ba đại lượng khác nhau

Một request có thể đi qua các trạng thái:

~~~mermaid
flowchart LR
    A["API request arrived"] --> B{"Admission có chỗ?"}
    B -->|Không| X["Reject/429/503 theo hợp đồng API"]
    B -->|Có| C["Chờ permit/concurrency budget"]
    C --> D["Driver dispatch / in-flight"]
    D --> E["Coordinator + replicas"]
    E --> F["Response hoặc timeout"]
    F --> G["Release permit + metrics"]
~~~

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **In-flight** | Số request đã được nhận/đang xử lý nhưng chưa hoàn tất trong ranh giới đo. |
| **Queue** | Request còn chờ được dispatch hoặc chờ permit; queue cũng chiếm RAM/thời gian. |
| **Concurrency limit** | Trần số request được xử lý đồng thời trong một scope; có thể theo process, query class, tenant. |
| **Request timeout** | Khoảng driver cho phép một request/attempt phù hợp hoàn tất theo semantics phiên bản. |
| **API deadline** | Thời điểm **toàn bộ công việc** của một request nghiệp vụ phải kết thúc, gồm chờ queue, nhiều CQL statement/page và xử lý ứng dụng. |
| **Retry budget** | Số lần/thời gian/phần trăm traffic dành cho việc retry; không đồng nghĩa timeout. |

**Một lỗi thường gặp:** giới hạn 100 in-flight trong driver nhưng đặt **queue không giới hạn** phía HTTP hoặc message consumer. Khi Cassandra chậm, bộ nhớ ứng dụng vẫn có thể tăng vì **hàng chục nghìn request chờ permit**. Phải có giới hạn **cả in-flight lẫn queue**, và chính sách trả overload ở đầu vào.

### 5.1. Dự toán concurrency bằng Little's Law

Ở trạng thái ổn định:

~~~text
L ≈ λ × W

L = request tồn tại trung bình trong hệ thống
λ = throughput hoàn tất/giây
W = thời gian trung bình từ lúc vào hệ thống đến lúc ra, tính bằng giây

Ví dụ λ = 600 requests/s:
  W = 0,05 s => L ≈ 30 request
  W = 0,50 s => L ≈ 300 request
  W = 2,00 s => L ≈ 1.200 request
~~~

Đây là phép tính minh họa chứ **không phải số lượng kết nối cần mở**. Nó cho thấy khi latency tăng 10 lần, cùng mức throughput có thể giữ số request chưa hoàn tất lớn gấp 10. Trong overload, thông lượng hoàn tất có thể giảm, queue tiếp tục phình và hệ không còn ổn định; không được dùng công thức như lời hứa capacity.

### 5.2. Hệ quả của tăng timeout

Giả sử gateway chỉ có deadline 1 giây nhưng driver timeout đặt 20 giây. Khi query chậm:

1. Gateway trả timeout cho người dùng sau 1 giây.
2. Nếu ứng dụng không kiểm soát cancellation/budget, request driver có thể **vẫn tiếp tục** theo semantics hiện tại.
3. Phần việc cũ còn chiếm in-flight trong khi request mới tiếp tục tới.
4. Nếu client/gateway retry mù, traffic khuếch đại; p99 của người dùng khác có thể xấu đi.

**Tăng timeout không làm replica đọc SSTable nhanh hơn, không khôi phục node down và không giải quyết guardrail tombstone.** Nó chỉ cho phép chờ lâu hơn khi các tầng khác vẫn còn thời gian và capacity.

## 6. Page size và giới hạn bytes: đếm hàng không đủ

Trong Cassandra, `LIMIT 100` là giới hạn **hàng logic trả về** bởi statement phù hợp. `page size = 50` là cách driver chia tập kết quả thành **các page**. Chúng không có nghĩa mọi lần đọc chỉ xử lý 50 cell trên disk.

| Tham số | Điều khiển | Rủi ro nếu đặt quá lớn |
| --- | --- | --- |
| `LIMIT` trong CQL | Số hàng kết quả của một statement. | Nếu chọn cột payload rất lớn, 100 rows vẫn có thể là hàng trăm MB. |
| Driver page size | Số rows mục tiêu trong một page theo cơ chế paging. | Buffers/network/decode/GC tăng; mỗi page có thể chậm. |
| Chọn cột `SELECT` | Byte/row và công việc decode. | `SELECT *` trên bảng có payload lớn làm tốn RAM/network. |
| Clustering range | Số phần dữ liệu cần xét trong một partition. | Range rộng có thể quét nhiều SSTable/tombstone. |
| Số bucket/partition | Fan-out của một API query. | Mỗi bucket tạo request/merge; nhiều bucket cùng lúc dễ quá tải. |

### 6.1. Tính byte budget

~~~text
Ví dụ:
  1 row trả về trung bình ~8 KiB
  500 rows/page
  payload mỗi page ≈ 4.000 KiB ≈ 3,9 MiB

Nếu 200 page/request đồng thời:
  lượng data đang được xử lý có thể rất lớn,
  tùy số page đã nhận, buffering, decode và bộ nhớ thực tế.
~~~

Page size đếm **rows**, không bảo đảm trần byte chính xác. Có hàng đặc biệt lớn, nhiều collections hoặc UDT khiến một page vượt ước lượng. Hãy đo **bytes/read**, phân phối kích thước hàng và áp giới hạn payload ở data model/ingestion nếu cần.

### 6.2. `ResultSet` và paging trong Java

Với driver 4.x, duyệt một `ResultSet` đồng bộ có thể **kích hoạt fetch trang tiếp theo**. Nếu phép đo bắt đầu trước `session.execute()` nhưng dừng ngay sau khi nhận trang đầu, nó **không bao gồm** toàn bộ thời gian tải/duyệt các page tiếp theo. Hãy xác định rõ:

- **Time to first page** khác **time to consume all rows**.
- Một driver request timeout không nhất thiết là **deadline tổng cho tất cả page và tất cả statement**.
- Đọc nhiều bucket phải giới hạn số bucket, số hàng và thời gian tổng, không chỉ `setPageSize`.
- Nếu muốn response từ API dưới 300 ms, không nên cho một request fetch hàng trăm page trong hot path.

## 7. Timeout, retry và speculative execution cần ngân sách chung

### 7.1. Các tầng thời gian

| Tầng | Ví dụ | Tác động |
| --- | --- | --- |
| Gateway/API | Deadline 800 ms | Người dùng không chờ lâu hơn. |
| Java service | Budget truy vấn và xử lý còn lại 600 ms | Có thể cần chừa thời gian serialize HTTP. |
| Java Driver | `basic.request.timeout` | Giới hạn request của driver theo phiên bản; không thay timeout server. |
| Cassandra coordinator | Read/write/range timeouts | Chờ phản hồi replica theo loại request. |
| Replica/OS | GC, queue, compaction, disk, mạng | Nguyên nhân có thể làm chậm thực thi. |

`ReadTimeout`, `WriteTimeout`, `Unavailable`, driver request timeout và lỗi `Unauthorized` là **những tình huống khác nhau**. Thay một cấu hình timeout không sửa hết những lỗi đó.

### 7.2. Retry không miễn phí

~~~mermaid
flowchart TD
    A["Request chậm"] --> B["Timeout hoặc retry trigger"]
    B --> C["Client gửi thêm attempt"]
    C --> D["Coordinator/replica thêm công việc"]
    D --> E["Queue + disk/CPU/GC pressure tăng"]
    E --> A
~~~

**Read** có thể retry trong một số tình huống, nhưng mọi lần retry làm tăng traffic; **write timeout** có thể xảy ra **sau khi một hoặc nhiều replica đã ghi**. Nếu ứng dụng retry `INSERT` với `event_id` mới, nó có thể tạo duplicate logic. Với counter, LWT hoặc read-modify-write, semantics retry phức tạp hơn.

Đặt **retry policy và speculative execution** theo hướng dẫn phiên bản, có **retry budget, backoff/jitter, idempotency và metrics**. Không bật speculative execution toàn bộ write hay mọi query chậm; một speculative request có thể cần **coordinator thứ hai** và tăng tải. Driver cần biết statement nào **idempotent**; đánh dấu sai là nguy hiểm.

### 7.3. Backpressure tốt hơn queue vô hạn

Một đường xử lý vững cần:

1. **Admission control** ở HTTP/message consumer, có trần pending requests và policy `429/503` hoặc defer có kiểm soát.
2. **Bounded in-flight** theo process, và có thể theo tenant/query type để tránh một workload chiếm hết slot.
3. **Request timeout nhỏ hơn deadline nghiệp vụ** khi phù hợp, tính cả chờ queue.
4. **Retry budget hữu hạn** và chỉ cho lỗi có thể retry an toàn.
5. **Metrics** về thời gian chờ permit, in-flight, queue, reject, driver requests và server latency.

Không tăng số thread không giới hạn để “giải quyết” blocked requests. Nếu giới hạn là disk I/O hoặc hot partition, nhiều concurrency chỉ làm nghẽn mạnh hơn.

## 8. Phân biệt giới hạn của driver với guardrail của Cassandra

| Hiện tượng | Bên chịu trách nhiệm chính | Không giải quyết bằng |
| --- | --- | --- |
| App giữ 100.000 `CompletableFuture` chờ Cassandra | Admission/bounded queue/concurrency phía app | Chỉ tăng pool size. |
| Driver request throttler đang queue/reject | Driver/app budget | Tăng queue vô hạn. |
| Replica quét quá nhiều tombstone | CQL data model, TTL/delete, SSTable/compaction và server guardrails | Chỉ tăng timeout hoặc page size. |
| `Unavailable` ở `LOCAL_QUORUM` | RF, node/DC availability, topology | Chỉ tăng request timeout. |
| Read theo partition key bị nóng | Partition/token distribution, workload/rate | Thêm kết nối Java Driver. |
| Node đầy disk do SSTable/compaction | Storage capacity và maintenance | Tăng driver concurrency. |
| Driver không đăng nhập được | Auth/TLS/credentials và role | Retry vô hạn mọi lỗi. |

Ví dụ `SELECT ... LIMIT 20` vẫn có thể quét hàng nghìn tombstone để tìm đủ hàng còn sống. Nếu server phát cảnh báo hoặc từ chối vì ngưỡng tombstone, driver **không có tuỳ chọn page size nào làm tombstone biến mất**. Cần sửa partition/range/TTL và cơ chế bảo trì dữ liệu.

## 9. Tách cấu hình giữa dev, staging và production

Chia cấu hình thành hai loại:

1. **Chính sách chung có version:** tên query/profile, serialization, timeout class, logging/metrics contract, nguyên tắc TLS và retry. Lưu trong source control khi không chứa bí mật.
2. **Giá trị môi trường:** contact points/DNS, local datacenter, RF/CL theo topology, số lượng connection/throttling budget, credentials/certificates, feature flags và limits. Cấp bằng deployment/secret store riêng, có audit.

### 9.1. Ma trận môi trường

| Thuộc tính | Dev/laptop | Staging | Production |
| --- | --- | --- | --- |
| **Topology** | Có thể một node lab hoặc container; có dữ liệu giả. | Gần production về số DC/RF/CL, hardware và workload shape khi thử capacity. | Topology thật, DC/rack đã duyệt, RF theo SLA. |
| **Contact points** | DNS/loopback của lab. | DNS riêng staging. | DNS nội bộ production, không lấy từ mặc định dev. |
| **Local DC** | Đúng tên do snitch lab báo. | Đúng DC staging. | Đúng DC nơi app chạy; không nhầm DC khi failover. |
| **Role/secret** | Tài khoản lab ít quyền, dữ liệu không nhạy cảm. | Identity staging độc lập. | Identity theo service và least privilege; rotate qua secret manager. |
| **TLS** | Nên thử đúng chính sách dự kiến; có CA lab. | Kiểm thử đầy đủ trust/hostname/cert rotation. | TLS/peer validation, network policy và audit theo chuẩn. |
| **Timeout** | Phục vụ debug/test, tránh che lỗi. | Giống hoặc có profile thử nghiệm so với production. | SLO-driven, tách interactive/batch. |
| **Page/concurrency** | Nhỏ để không quá tải lab. | Load test có kiểm soát, theo cấu hình gần production. | Dựa trên benchmark/capacity từng DC và tail latency. |
| **Retry/logging** | Có thể log chi tiết trên dữ liệu giả. | Test failure injection và retry budgets. | Logging đã redact, sampling, alert, kiểm soát overhead. |

**Không dùng staging làm production chỉ vì cùng Docker image.** Môi trường cần khác ở **identity, address/cluster, secrets, dữ liệu, permissions, mạng và telemetry labels**. Một pipeline deploy nhầm endpoint production từ dev có thể gây thay đổi dữ liệu thật.

### 9.2. Chia file theo môi trường và kiểm soát “nguồn sự thật”

Ví dụ cấu trúc **khái niệm** của ứng dụng:

~~~text
src/main/resources/
  cassandra-dev.conf
  cassandra-staging.conf
  cassandra-prod.conf

Deployment:
  APP_ENV=dev|staging|prod
  CASSANDRA_CONTACT_POINT=...
  CASSANDRA_LOCAL_DC=...
  secret reference: Cassandra service credential / TLS trust
~~~

Trên hệ thống lớn, file môi trường có thể được **render khi deploy** từ ConfigMap/IaC/secret management thay vì nằm sẵn trong JAR. Quan trọng là:

- File tracked trong Git **không chứa password, access token, private key hoặc dữ liệu người dùng**.
- Có **schema validation/allowlist** cho `APP_ENV`; không tự fallback từ `prod` về `dev` hoặc ngược lại.
- Mỗi giá trị quan trọng có một nguồn cấu hình rõ ràng: tránh nhiều lớp override không có thứ tự được ghi nhận.
- Khi rotate secrets/cert, không bắt ứng dụng release source mới nếu hệ thống quản lý secret hỗ trợ cấp phát động phù hợp.
- Log lúc khởi động chỉ ghi **environment, config version/hash, cluster identity/local DC, profile và giới hạn không nhạy cảm**; không echo toàn bộ config.

## 10. HOCON Java Driver 4.x: nền tảng cấu hình dùng chung

Java Driver 4.x dùng mô hình cấu hình với namespace thường là `datastax-java-driver`. Ví dụ **một bộ giá trị tham khảo cho staging/lab**, chưa phải hướng dẫn chọn ngưỡng production:

~~~hocon
datastax-java-driver {
  basic.request {
    timeout = 2 seconds
    consistency = LOCAL_QUORUM
    page-size = 100
  }

  advanced.connection.pool {
    local.size = 1
  }

  advanced.request-throttler {
    class = ConcurrencyLimitingRequestThrottler
    max-concurrent-requests = 200
    max-queue-size = 400
  }
}
~~~

**Giải thích quan trọng:**

- `basic.request.timeout` là thời gian chờ **client**, không sửa `read_request_timeout_in_ms` trên Cassandra server.
- `page-size` đặt kích thước page mặc định; không thay `LIMIT` trong CQL.
- `advanced.connection.pool.local.size` điều khiển số connection theo node **local** trong phạm vi phiên bản/driver; không phải trần tổng request của service.
- `advanced.request-throttler` dùng cơ chế throttling của driver khi phiên bản hỗ trợ. `max-concurrent-requests` và `max-queue-size` là **budget client**, không tăng năng lực replica.
- Tên lớp throttler, key, mặc định và thời điểm áp dụng phải được **xác nhận theo version driver**. Nếu driver/bản phân phối không nhận option, không được lặng lẽ bỏ qua rồi tuyên bố hệ thống đã rate-limit.
- Con số `200/400` chỉ minh họa. Nếu service chạy 20 pod, tổng concurrency **có thể lớn hơn 20 lần budget mỗi pod**; cần tính giới hạn toàn fleet.

### 10.1. Execution profiles cho query class

Một ứng dụng vừa có API tương tác vừa có backfill không nên dùng chung tất cả timeout/page size. Có thể định nghĩa **execution profiles** theo workload trong namespace driver, ví dụ:

~~~hocon
datastax-java-driver {
  basic.request {
    timeout = 2 seconds
    consistency = LOCAL_QUORUM
    page-size = 100
  }

  profiles {
    interactive {
      basic.request {
        timeout = 500 milliseconds
        page-size = 50
      }
    }
    batch-read {
      basic.request {
        timeout = 5 seconds
        page-size = 200
      }
    }
  }
}
~~~

Đây là **ví dụ cấu trúc** của profile trong HOCON 4.x; phải so với version cụ thể. Profiles giúp chọn timeout/CL/page size cho **từng statement**, nhưng **không tự cô lập tài nguyên phía replica**. Một batch read có timeout 5 giây vẫn phải được giới hạn rate/concurrency ở ứng dụng/driver hoặc bằng hệ thống batch riêng.

### 10.2. Tránh lẫn profile với môi trường

**Environment** trả lời: “Ứng dụng đang chạy ở cluster, DC, IAM và capacity nào?”; **execution profile** trả lời: “Statement này thuộc loại workload nào?”. Production có thể dùng `interactive` và `batch-read`, còn staging cũng dùng hai profile ấy nhưng **giá trị được benchmark phù hợp**. Không tạo profile tên `prod` chỉ để né việc phân biệt query class.

## 11. Chuẩn bị CQL lab: partition key để mỗi request có chi phí dự đoán

Giả sử cluster lab có DC `dc1`, ba full replicas và được phép tạo schema:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry_driver
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS telemetry_driver.events_by_device_day (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  payload text,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

Ở đây, `(device_id, event_day)` là **partition key kép** để giới hạn số sự kiện tích lũy trong partition. `event_time`, `event_id` là **clustering columns**; một event có timestamp trùng vẫn có thể phân biệt bằng ID ổn định.

### 11.1. Ghi dữ liệu mẫu

~~~sql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO telemetry_driver.events_by_device_day
  (device_id, event_day, event_time, event_id, payload)
VALUES
  ('device-7', '2026-11-21', '2026-11-21T09:00:00Z',
   123e4567-e89b-42d3-a456-426614174001, 'temperature:21.5');

INSERT INTO telemetry_driver.events_by_device_day
  (device_id, event_day, event_time, event_id, payload)
VALUES
  ('device-7', '2026-11-21', '2026-11-21T09:01:00Z',
   123e4567-e89b-42d3-a456-426614174002, 'temperature:21.6');
~~~

### 11.2. Truy vấn phù hợp, không cần `ALLOW FILTERING`

~~~sql
SELECT event_time, event_id, payload
FROM telemetry_driver.events_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T09:00:00Z'
  AND event_time < '2026-11-21T10:00:00Z'
LIMIT 100;
~~~

Không nên chỉ dùng `WHERE event_time >= ... ALLOW FILTERING` trên bảng này: thiếu partition key khiến truy vấn có thể quét lượng dữ liệu rất lớn. **Chỉnh pool/timeout/page size không sửa được query shape sai**. Với query trải nhiều ngày, ứng dụng phải đọc các bucket phù hợp rồi merge/sort, giới hạn số bucket.

## 12. Java: chọn file config đúng môi trường và fail-closed

Ví dụ Java Driver 4.x dưới đây chọn **file config theo allowlist**. Contact point, local DC và credential được cấp qua môi trường triển khai để không hardcode địa chỉ production vào source.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.config.DriverConfigLoader;
import java.net.InetSocketAddress;
import java.util.Map;
import java.util.Objects;

public final class EnvironmentAwareCassandraSession {
    public static CqlSession open() {
        String environment = Objects.requireNonNull(
            System.getenv("APP_ENV"), "APP_ENV is required");

        Map<String, String> configFiles = Map.of(
            "dev", "cassandra-dev.conf",
            "staging", "cassandra-staging.conf",
            "prod", "cassandra-prod.conf");

        String config = configFiles.get(environment);
        if (config == null) {
            throw new IllegalArgumentException(
                "Unsupported APP_ENV: " + environment);
        }

        String host = Objects.requireNonNull(
            System.getenv("CASSANDRA_CONTACT_POINT"),
            "contact point is required");
        String dc = Objects.requireNonNull(
            System.getenv("CASSANDRA_LOCAL_DC"),
            "local DC is required");
        String username = Objects.requireNonNull(
            System.getenv("CASSANDRA_APP_USER"),
            "CQL user is required");
        String password = Objects.requireNonNull(
            System.getenv("CASSANDRA_APP_PASSWORD"),
            "CQL password is required");

        DriverConfigLoader loader = DriverConfigLoader.fromClasspath(config);
        return CqlSession.builder()
            .withConfigLoader(loader)
            .addContactPoint(new InetSocketAddress(host, 9042))
            .withLocalDatacenter(dc)
            .withAuthCredentials(username, password)
            .build();
    }
}
~~~

**Lưu ý về code:**

1. `Map.of` cần Java 9+. Nếu môi trường theo bản JDK khác, đổi sang cấu trúc tương thích.
2. Đây là **khung bootstrap**, chưa cấu hình TLS đầy đủ. Production phải bật **TLS với truststore/CA/hostname validation thích hợp**, có thể qua driver SSL settings hoặc `withSslContext(...)` được kiểm chứng, trước khi gửi credential.
3. Password trong biến môi trường chỉ để minh họa cách không hardcode; biến môi trường vẫn có thể bị đọc bởi runtime/admin có quyền. Production ưu tiên **secret manager**, workload identity hoặc cơ chế phù hợp với triển khai.
4. Không tự fallback `APP_ENV` hoặc contact point sang production; thiếu biến phải **fail-fast**.
5. `CqlSession` được tạo **một lần lúc khởi động service**, rồi chia sẻ; phải đóng khi shutdown.
6. Địa chỉ `host` đại diện một điểm discovery: hệ thống thật có thể dùng nhiều contact points, DNS/port cấu hình riêng, proxy/tunnel hoặc service discovery theo policy.
7. Thử hiệu lực role/tên cluster/DC sau khi connect, không chỉ dựa vào `APP_ENV=staging`. Tránh hiển thị user/password hoặc toàn bộ config trong log.

### 12.1. Tránh trùng nguồn cấu hình

Nếu cùng lúc HOCON và builder đều đặt `local-datacenter`, contact points hoặc credential nhưng giá trị khác nhau, người vận hành dễ hiểu sai config nào có hiệu lực. Nên quy định **một chủ thể sở hữu mỗi giá trị**, test startup assertions và in ra **fingerprint không nhạy cảm**.

Ví dụ:

~~~text
APP_ENV                = staging
CONFIG_ID              = cassandra-staging-v17
CONTACT_POINT_SET_ID   = staging-dc1-cql
LOCAL_DC               = dc1
REQUEST_PROFILE        = interactive
DRIVER_MAJOR           = 4.x
TLS_EXPECTED           = true
SECRET_REFERENCE       = vault/path/version-only

Không log: password, private key, access token, full CQL literals nhạy cảm.
~~~

## 13. Java: đọc có giới hạn, đo cả thời gian consume kết quả

Với cùng bảng lab, xây một truy vấn đọc có **đầy đủ partition key, clustering range và `LIMIT`**. Dùng `System.nanoTime()` để đo duration (không phải mốc UTC).

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Instant;
import java.time.LocalDate;
import java.util.concurrent.TimeUnit;

public final class BoundedReadExample {
    public static void read(CqlSession session) {
        PreparedStatement select = session.prepare(
            "SELECT event_time, event_id, payload " +
            "FROM telemetry_driver.events_by_device_day " +
            "WHERE device_id = ? AND event_day = ? " +
            "AND event_time >= ? AND event_time < ? LIMIT 100");

        BoundStatement statement = select.bind(
                "device-7",
                LocalDate.of(2026, 11, 21),
                Instant.parse("2026-11-21T09:00:00Z"),
                Instant.parse("2026-11-21T10:00:00Z"))
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setPageSize(50);

        long started = System.nanoTime();
        int rowCount = 0;
        try {
            ResultSet result = session.execute(statement);
            for (Row row : result) {
                rowCount++;
                // Chỉ xử lý các cột cần thiết; không gom payload vào list lớn.
                row.getInstant("event_time");
                row.getString("payload");
            }
        } finally {
            long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - started);
            System.out.println("query=read_recent_events"
                + " rows=" + rowCount
                + " elapsed_ms=" + elapsedMs);
        }
    }
}
~~~

`rowCount` chỉ là số hàng **ứng dụng duyệt**, không phải số tombstone server quét. Trong production, đưa log latency vào metrics với `query_name`, `status`, `dc` và `profile`, tránh gắn mỗi `device_id` làm label (cardinality và dữ liệu nhạy cảm).

**Đọc sâu hơn:** nếu API gọi nhiều CQL statements hoặc có paging, tổng thời gian API phải được đo riêng, có deadline tổng; `LIMIT 100` không đảm bảo replica chỉ đọc 100 cell vật lý.

## 14. Java: ghi bất đồng bộ có giới hạn in-flight

`executeAsync()` cho phép ứng dụng không chặn một thread chỉ để đợi từng response Cassandra. Tuy nhiên, **async không có nghĩa vô hạn tài nguyên**. Gửi 100.000 `CompletableFuture` ngay lập tức có thể làm app và các coordinator cạn memory/queue.

Ví dụ sau tạo **50 mutation mẫu** có event ID ổn định cho một lần chạy, nhưng chỉ cho phép **tối đa 8 request đang chờ hoàn tất** tại một thời điểm. Mã chạy ở **lab**, sử dụng producer thread thông thường; không dùng logic blocking `Semaphore.acquire()` bên trong event-loop/driver I/O callback.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicInteger;

public final class BoundedAsyncWrites {
    private static final int MAX_IN_FLIGHT = 8;
    private static final int LAB_EVENTS = 50;

    public static void run(CqlSession session)
            throws InterruptedException {

        PreparedStatement insert = session.prepare(
            "INSERT INTO telemetry_driver.events_by_device_day " +
            "(device_id, event_day, event_time, event_id, payload) " +
            "VALUES (?, ?, ?, ?, ?)");

        Semaphore permits = new Semaphore(MAX_IN_FLIGHT);
        List<CompletableFuture<Void>> futures = new ArrayList<>();
        AtomicInteger acknowledged = new AtomicInteger();
        AtomicInteger failures = new AtomicInteger();

        for (int i = 0; i < LAB_EVENTS; i++) {
            // Chỉ block producer riêng, KHÔNG block driver I/O thread.
            permits.acquire();

            Instant when = Instant.parse("2026-11-21T09:00:00Z")
                                  .plusSeconds(i);
            UUID eventId = UUID.nameUUIDFromBytes(
                ("device-7-lab-" + i).getBytes(StandardCharsets.UTF_8));

            BoundStatement write = insert.bind(
                    "device-7",
                    LocalDate.of(2026, 11, 21),
                    when,
                    eventId,
                    "temperature:" + i)
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

            CompletableFuture<Void> done = new CompletableFuture<>();
            futures.add(done);

            try {
                session.executeAsync(write).whenComplete((result, error) -> {
                    try {
                        if (error == null) {
                            acknowledged.incrementAndGet();
                            done.complete(null);
                        } else {
                            failures.incrementAndGet();
                            done.completeExceptionally(error);
                        }
                    } finally {
                        // Callback chỉ cập nhật trạng thái, không chặn I/O.
                        permits.release();
                    }
                });
            } catch (RuntimeException dispatchFailure) {
                failures.incrementAndGet();
                permits.release();
                done.completeExceptionally(dispatchFailure);
            }
        }

        try {
            CompletableFuture.allOf(
                futures.toArray(new CompletableFuture[0])).join();
        } catch (CompletionException ex) {
            // Production: ghi error_type và xử lý DLQ/reconciliation,
            // không tự retry mọi WriteTimeout bằng event ID mới.
            System.err.println("Some lab writes did not ACK: "
                + ex.getCause().getClass().getSimpleName());
        }

        System.out.println("writes_acknowledged=" + acknowledged.get()
            + " writes_failed_or_unknown=" + failures.get());
    }
}
~~~

### 14.1. Vì sao ví dụ giới hạn được request nhưng chưa phải ingestion pipeline?

- `Semaphore` chỉ giữ tối đa **8 async writes** đồng thời **trong phạm vi lời gọi/process này**. Nếu có 20 pod cùng chạy, toàn fleet có thể có tới 160 writes tương tự, chưa tính các luồng khác.
- `permits.acquire()` **chặn producer** khi hết slot. Đây là backpressure có chủ đích ở lab; production cần **bounded input queue, cancellation/deadline** và chính sách trả overload cho nguồn phát.
- Callback gọi `complete(...)` và `release()` nhanh; không thực hiện file I/O, gọi API blocking hoặc `join()` trong callback driver.
- ID được dựng ổn định cho lần chạy lab; cùng `event_id` giúp tránh **nhân đôi hàng** khi gửi lại cùng key. Tuy nhiên, nếu TTL, timestamp hoặc payload thay đổi thì retry **không mặc nhiên idempotent ở mọi khía cạnh**.
- `acknowledged` đếm những request nhận thành công theo `LOCAL_QUORUM`; nó không chứng minh mọi replica cùng có dữ liệu. `failures` gồm các yêu cầu thất bại/không xác nhận, **không đồng nghĩa mutation chưa được ghi**.
- `executeAsync` trả về `CompletionStage`; đối với truy vấn `SELECT` có nhiều page phải tiêu thụ/truy vấn từng page theo API `AsyncResultSet`, không coi response đầu tiên là toàn bộ kết quả.
- Ví dụ không có durable retry log/DLQ, service-level deadline, tracing hay metrics chuẩn. **Không dùng nguyên xi cho dữ liệu nghiệp vụ không thể mất**.

### 14.2. Nếu có driver request throttler thì còn cần semaphore không?

**Có thể cần.** Chúng bảo vệ những ranh giới khác nhau:

| Công cụ | Scope | Tác dụng |
| --- | --- | --- |
| **API admission** | Người dùng/tenant/toàn service | Chặn traffic không nên nhận trước khi tạo thêm công việc. |
| **Semaphore/concurrency gate** | Một query class/producer/process | Giới hạn số request mà producer cho chạy đồng thời. |
| **Driver request throttler** | Request đi qua một session/driver theo semantics cấu hình | Giới hạn request dispatch và queue ở tầng driver. |
| **Server guardrail** | CQL/schema/việc xử lý trên Cassandra | Chặn các query/data pattern được coi nguy hiểm. |
| **Cassandra queue/OS capacity** | Node/replica, disk/CPU/network | Giới hạn thực tế nơi dữ liệu được xử lý. |

Chỉ cài throttler ở driver không ngăn ứng dụng nhận vô hạn HTTP requests và giữ chúng trong RAM trước khi gọi driver. Ngược lại, một semaphore theo request handler **không tự biết** tổng số request ở các pod khác hoặc công việc của ứng dụng khác.

## 15. Execution profile trong Java và đường đọc/ghi tách biệt

Đoạn dưới giả định HOCON đã định nghĩa profile `interactive` và `batch-read` như mục 10.1:

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Instant;
import java.time.LocalDate;

// "session" là CqlSession sống lâu được DI quản lý.
PreparedStatement query = session.prepare(
    "SELECT event_time, event_id, payload " +
    "FROM telemetry_driver.events_by_device_day " +
    "WHERE device_id = ? AND event_day = ? " +
    "AND event_time >= ? AND event_time < ? LIMIT 100");

BoundStatement interactive = query.bind(
        "device-7",
        LocalDate.of(2026, 11, 21),
        Instant.parse("2026-11-21T09:00:00Z"),
        Instant.parse("2026-11-21T10:00:00Z"))
    .setExecutionProfileName("interactive")
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

// Dùng session.execute(interactive) tại lớp service phù hợp.
// Với batch jobs, có thể chọn profile "batch-read"
// nhưng vẫn phải có bounded concurrency/rate và deadline tổng.
~~~

Đoạn này là **trích dẫn trong method** để minh họa call site, không phải một `class` đầy đủ. Không cần tạo session khác chỉ để chọn timeout/page size khác. Tuy nhiên, nếu batch có rủi ro ảnh hưởng API chính, profile **không phải phép cách ly vật lý**: vẫn cần rate limit, admission, lịch chạy hoặc cluster/tenant resource policy phù hợp.

**Không tách profile theo từng `device_id` hay `request_uuid`**. Các profile nên đại diện cho **ít nhóm workload ổn định**, dễ đo và kiểm soát, tránh cấu hình có cardinality vô hạn.

## 16. Tính ngân sách khi scale nhiều instance Java

Một giới hạn `MAX_IN_FLIGHT=50` trong **một** instance không phải giới hạn 50 cho **cả dịch vụ**:

~~~text
Ví dụ:
  30 Java service instances
  mỗi instance cho tối đa 50 request Cassandra đang chạy
  => trần lý thuyết: 30 × 50 = 1.500 request đồng thời

Nếu mỗi logical API request đọc 3 bucket song song:
  cần tính thêm fan-out và khả năng chạm cùng replica/node.
~~~

**Không dùng phép nhân đó làm số kết nối TCP**: request có thể multiplex trên connection. Con số 1.500 cũng là **trần các yêu cầu được cấp slot**, không phải throughput 1.500 request/s.

### 16.1. Công thức định hướng capacity

~~~text
Giả sử:
  20 pods
  target throughput mỗi pod = 150 logical API requests/s
  mỗi API thường gửi 2 CQL statements

Tổng CQL request rate ước tính:
  20 × 150 × 2 = 6.000 statements/s

Nếu p99 của statement = 0,25 s:
  KHÔNG thể suy trực tiếp in-flight chuẩn chỉ bằng 6000 × p99.
  Little's Law dùng W trung bình, không dùng p99 thay thế.

Nếu mean W ước lượng = 0,06 s và tải ổn định:
  L ≈ 6.000 × 0,06 = 360 in-flight trung bình toàn fleet.

Budget in-flight đỉnh phải đánh giá burst, tail, retry,
fan-out theo partition/DC và capacity coordinator/replica.
~~~

**Đây là bài toán sizing sơ bộ.** Thông số thực phải đo bằng load test có data shape giống production. Nếu retry rate 10% và mỗi retry là request bổ sung, tổng traffic tới Cassandra có thể lớn hơn 6.000 statements/s; nếu shadow read/canary, backfill hoặc speculative execution cùng chạy, cần cộng thêm nguồn tải ấy.

### 16.2. Tránh hotspot và phân bố sai DC

Đặt `localDatacenter` đúng giúp routing theo topology dự kiến, đặc biệt với `LOCAL_QUORUM`. Nhưng **driver không sửa data modeling**. Nếu 90% request đều dùng cùng `device_id` và cùng ngày, cùng partition token có thể làm một nhóm replica nóng dù cluster có hàng trăm node.

| Thay đổi | Điều có thể cải thiện | Điều không tự cải thiện |
| --- | --- | --- |
| Tăng instance Java | Capacity ứng dụng, nếu backend còn dư. | Hot partition và IOPS Cassandra. |
| Tăng connections/local pool | Có thể giảm client-side bottleneck thật. | Replica đang disk-saturated. |
| Dùng `LOCAL_QUORUM` đúng DC | Hạn chế phụ thuộc remote DC trong yêu cầu local. | Một replica local bị GC/compaction nặng. |
| Time bucket partition | Giới hạn lịch sử và có thể phân tán các partition theo ngày. | Read lịch sử có thể phải fan-out nhiều bucket. |
| Shard bucket nóng | Phân tán write hotspot theo nhiều token. | Số read cần merge tăng theo shard count. |
| Cắt bớt payload/page | Giảm network/memory/decode per request. | `ALLOW FILTERING` hoặc tombstone scan chưa sửa. |

## 17. Cấu hình bảo mật phải tách theo môi trường, không chỉ tên server

Một bản `cassandra-prod.conf` có timeout/pool tốt vẫn không đạt yêu cầu nếu ứng dụng gửi credentials qua kết nối thiếu TLS hoặc dùng tài khoản có quyền superuser.

### 17.1. Những điều phải khác giữa môi trường

- **Auth identity:** `telemetry_api_dev`, `telemetry_api_staging`, `telemetry_api_prod` hoặc cấu trúc định danh phù hợp; không dùng chung secret.
- **Quyền CQL:** chỉ `SELECT`/`MODIFY` ở đúng bảng cần thiết. Tài khoản ứng dụng không cần `CREATE ROLE`, `ALTER KEYSPACE` hay quyền JMX.
- **TLS trust anchors:** CA/certificate đúng cluster, hostname/SAN validation; không `trust-all` để né lỗi staging.
- **Network:** prod cluster không cho phép kết nối trực tiếp từ dev laptop khi không được duyệt; staging không cùng seed/gossip identity production.
- **Backup/logging:** không log password, access token hoặc payload/partition key nhạy cảm; phân quyền truy cập telemetry.
- **Data lifecycle:** staging dùng dữ liệu giả hoặc được masking đúng; không copy production SSTable chứa PII vào môi trường có chính sách yếu hơn.

### 17.2. Thực hành fail-closed lúc khởi động

Kiểm tra **trước khi service nhận traffic**:

~~~text
[ ] APP_ENV thuộc allowlist dev/staging/prod, không dùng default mơ hồ.
[ ] Contact point và local DC đúng cluster kỳ vọng.
[ ] Driver major/minor version và config ID được ghi rõ.
[ ] TLS và kiểm tra certificate peer thật sự được bật theo policy.
[ ] Secret lấy từ nguồn được duyệt, không có fallback hardcoded password.
[ ] App role truy cập bảng cần thiết nhưng không có quyền schema/admin.
[ ] Prepared statements chuẩn bị thành công; keyspace/schema đã đúng.
[ ] Driver timeout và throttling config được load, không bị bỏ qua.
[ ] Metrics/health endpoint phản ánh tình trạng kết nối và in-flight.
[ ] Shutdown đóng session và dừng nhận request mới có trật tự.
~~~

Một phép `SELECT` heartbeat lúc startup có thể phát hiện vấn đề rõ ràng nhưng **không chứng minh mọi partition/replica đều khỏe**. Health check cần có deadline và tần suất phù hợp; không thực hiện một truy vấn nóng nhiều lần mỗi giây chỉ để kiểm tra kết nối.

## 18. Giám sát: đo từ application tới replica

Chỉ nhìn `p99` của HTTP không đủ biết request chậm do Java, driver queue, coordinator, tombstone, disk hay network.

### 18.1. Dashboard tối thiểu

| Tầng | Metric hữu ích | Câu hỏi |
| --- | --- | --- |
| **API/gateway** | Request rate, p50/p95/p99, error/timeout, queue và reject. | Người dùng bị ảnh hưởng tới đâu? |
| **Ứng dụng Java** | In-flight theo query class, pending queue, permit wait, heap/RSS, GC pause, thread usage. | App bị nghẽn trước khi gọi Cassandra? |
| **Driver** | Request latency/error/timeout, per-node in-flight, open connections, throttler delays/queue/reject, retry attempts (nếu metrics hỗ trợ). | Có bottleneck trên client hoặc route sai node? |
| **Coordinator** | Read/write latency, timeout/unavailable, dropped messages, `tpstats`. | Cluster có nhận quá nhiều request? |
| **Replica/SSTable** | Read latency, tombstones scanned, SSTable count, compaction backlog, disk await/IOPS. | Chi phí truy vấn phía server quá cao? |
| **Network/DC** | Connection failures, retransmits, cross-DC traffic, node membership. | Driver đang chọn sai DC hoặc mạng bị lỗi? |
| **Security/config** | TLS/auth failures, credential rotation, config versions, drift. | Một rollout đã vô tình đổi cluster/quyền? |

### 18.2. Lệnh `nodetool` tham khảo

~~~bash
nodetool status
nodetool info
nodetool tpstats
nodetool compactionstats
nodetool gcstats
nodetool netstats
nodetool proxyhistograms
nodetool tablestats telemetry_driver.events_by_device_day
nodetool tablehistograms telemetry_driver events_by_device_day
~~~

Tên lệnh/đối số và metric phụ thuộc phiên bản Cassandra; kiểm tra `nodetool help`. Một số counter tích lũy từ lúc node chạy, một số histogram chứa số liệu theo scope riêng. Đừng cộng trung bình p99 giữa node để có p99 toàn cluster. Đặt client metrics và server metrics trên **cùng trục UTC** với request rate/traffic deploy để thấy nguyên nhân hợp lý.

### 18.3. Tracing có chọn lọc

~~~sql
CONSISTENCY LOCAL_QUORUM;
TRACING ON;

SELECT event_time, event_id, payload
FROM telemetry_driver.events_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T09:00:00Z'
  AND event_time < '2026-11-21T10:00:00Z'
LIMIT 100;

TRACING OFF;
~~~

`TRACING` và `CONSISTENCY` là lệnh của **cqlsh**, không gửi nguyên văn qua Java Driver. Trace của một truy vấn có thể giúp nhận diện coordinator/replica và các bước tốn thời gian; **không bật tracing 100% traffic production** vì bản thân tracing tạo thêm tải/metadata.

### 18.4. Metrics cardinality và log redaction

Label ổn định nên là `query_name`, `environment`, `local_dc`, `status`, `profile` và node identity ở mức được phép. Không gắn `event_id`, `device_id`, `request_uuid` hay toàn bộ CQL literal vào metrics hàng loạt: cardinality lớn và rủi ro PII. Với log lỗi, ghi **exception class, timestamp, request correlation ID, query template** đã redact và retry attempt count, không ghi credentials/payload.

## 19. Case study: tăng timeout khiến số lỗi có vẻ giảm nhưng p99 xấu đi

Giả lập dịch vụ có 24 Java pods; mỗi pod mở một session, dùng cùng bảng sự kiện. Mỗi pod nhận trung bình 200 API requests/s, mỗi API gửi một SELECT. Ở thời điểm tắc disk/compaction, latency mean tăng từ 40 ms lên 300 ms.

| Chỉ số | Baseline | Trong sự cố | Hệ quả |
| --- | ---: | ---: | --- |
| Tổng request rate | 4.800/s | 4.800/s | Đầu vào chưa giảm. |
| Mean DB latency | 40 ms | 300 ms | Request giữ tài nguyên lâu hơn. |
| In-flight trung bình lý thuyết (Little's Law) | ~192 | ~1.440 | Tăng khoảng 7,5 lần dù throughput không đổi. |
| Driver request timeout | 2 s | Nếu tăng lên 20 s | Không tự giảm mean DB latency. |
| JVM heap/GC | Ổn định | Heap và pause tăng | Có thể do queue/buffers tồn đọng. |
| Server compaction/disk | Bình thường | Disk await và pending compaction tăng | Phải điều tra capacity/maintenance. |

**Cách xử lý sai:** tăng pool lên 10 lần, tăng timeout lên 20 giây, tăng page size 10 lần và bật retry không giới hạn. Điều này có thể làm error rate client trông thấp hơn trong ít phút, nhưng tăng queue và đẩy thêm việc lên disk đang nghẽn.

**Cách xử lý có căn cứ:**

1. Đo client p99, driver queue/in-flight và retry; so cùng mốc với disk await, compactionstats và `tpstats` của các replica.
2. Giữ admission/queue hữu hạn; nếu backend đã quá tải, giảm traffic batch/backfill hoặc trả overload có kiểm soát.
3. Kiểm tra query có đủ partition key, clustering range, `LIMIT`, page size phù hợp và không quét tombstone bất thường.
4. Chỉ điều chỉnh timeout/profile **cho workload có SLA dài hơn** nếu benchmark chứng minh hữu ích và không ảnh hưởng API tương tác.
5. Canary với một số pod, theo dõi throughput, p99, GC, queue và disk; rollback ngay khi regression xảy ra.

**Chú ý:** 1.440 là số **in-flight trung bình ước tính**, không phải kết quả đo hoặc số kết nối driver. Nếu system đã overload, công thức trạng thái ổn định không mô tả đầy đủ queue đang phình.

## 20. Trường hợp môi trường lệch cấu hình dẫn đến lỗi khó chẩn đoán

### 20.1. Staging có RF = 1 nhưng Java dùng `LOCAL_QUORUM`

Với RF = 1 trong một DC, `LOCAL_QUORUM` yêu cầu **một** replica; nên nó có thể chạy, nhưng **không thử được hành vi quorum RF = 3 của production**. Không suy từ staging một node rằng ứng dụng xử lý được một replica chậm hoặc node down trong cụm nhiều replica.

Nếu staging chỉ có **một node** nhưng keyspace vẫn khai báo RF = 3 và client dùng `LOCAL_QUORUM`, replica availability có thể không đáp ứng; lỗi có thể là `Unavailable` chứ không phải driver timeout. Cần test topology có chủ đích thay vì tùy tiện hạ consistency level để “cho chạy”.

### 20.2. Local DC nhập sai

Java service trong `dc1` cấu hình `localDatacenter("dc2")` có thể khiến driver không route theo placement dự định, hoặc không xác lập đường kết nối hợp lệ tùy topology/contact points/config. Độ trễ WAN và auth/network policy có thể biểu hiện như timeout. Kiểm tra **tên DC do snitch báo**, metadata driver và nơi pod đang chạy; không chỉ nhìn IP contact point.

### 20.3. Credentials staging bị dùng ở production

Một cấu hình sai có thể dẫn tới:

- Kết nối bị `AuthenticationException` hoặc `Unauthorized` do role khác.
- Tệ hơn, nếu credential dùng chung, ứng dụng vô tình truy cập dữ liệu production bằng role quá rộng.
- Monitoring mất phân biệt actor/environment và incident response phải rotate nhiều service cùng lúc.

**Cần identity riêng, secret references riêng, kiểm soát endpoint/network và fail-fast khi environment mismatch.** Không chữa lỗi auth bằng đổi sang superuser hoặc tắt TLS.

## 21. Quy trình thay đổi cấu hình Driver có kiểm soát

~~~mermaid
flowchart TD
    A["Cần đổi driver limits / environment config"] --> B["Chốt SLO, RF/CL, workload, version và topology"]
    B --> C["Đo baseline client/driver/server metrics"]
    C --> D["Chọn thay đổi tối thiểu, viết giả thuyết"]
    D --> E["Test staging có traffic, data shape và TLS/RBAC phù hợp"]
    E --> F{"Đạt p99, errors, throughput, resource budgets?"}
    F -->|Không| G["Giữ cấu hình cũ, sửa gốc/đánh giá lại"]
    F -->|Có| H["Canary một nhóm pods, không thay toàn fleet"]
    H --> I["Đo in-flight, queue, GC, disk, coordinator, retry"]
    I --> J{"Mọi workload đều ổn?"}
    J -->|Không| K["Rollback config / giảm rate có kiểm soát"]
    J -->|Có| L["Mở rộng rollout, ghi change ID và review"]
~~~

### 21.1. Mẫu experiment log

~~~text
Experiment ID:
Driver exact version:
Cassandra version, JDK:
Environment / cluster / DC / RF / CL:
Config before/after (đã redact):
Query types, data shape, request rate, burst:
Load test duration, sample count:
Client p50/p95/p99, timeout, retry:
Driver connections, in-flight, throttler queue/reject:
Server tpstats, GC, disk latency, compaction:
Application JVM heap/RSS, thread/CPU:
Decision GO/NO-GO:
Rollback trigger:
Owner and UTC change time:
~~~

**Một bài test 100 request** khó đủ để đo p99 có ý nghĩa; cần đủ mẫu và tải đại diện, bao gồm peak/burst, dữ liệu TTL/tombstone và các tác vụ compaction/repair có thể trùng cao điểm.

### 21.2. Những điều cần giữ khi tăng instance

- Theo dõi **total request budget trên toàn fleet**, không chỉ limit từng pod.
- Kiểm tra quota của keyspace/tenant, số connection theo node và coordinator distribution.
- Khi scale 10 lên 50 pod, có thể giữ mỗi pod 100 in-flight nhưng tổng theoretical budget từ 1.000 lên 5.000. Capacity backend không tự tăng tương ứng.
- Cân nhắc áp **global rate limiting** hoặc controller sử dụng telemetry để điều tiết ingress.
- Đảm bảo shutdown/drain không làm mất queued writes; kết quả write timeout vẫn phải được xử lý theo idempotency/reconciliation.

## 22. Những quan niệm sai phổ biến

| Nhận định | Kết luận | Lý do |
| --- | --- | --- |
| “Cứ tạo `CqlSession` mỗi request là an toàn hơn.” | **Sai** | Session giữ connections/metadata/resources và nên tái sử dụng. |
| “Connection pool Cassandra có một connection độc quyền cho mỗi request như JDBC.” | **Sai** | Native protocol hỗ trợ multiplexing. |
| “Tăng pool hoặc tăng pod là sửa được hot partition.” | **Sai** | Partition token/replica không đổi. |
| “`executeAsync` không tốn memory/thread.” | **Sai** | Future, queue, buffers, callback và server work vẫn tốn tài nguyên. |
| “Semaphore 100 trong một pod nghĩa toàn dịch vụ có tối đa 100 request.” | **Sai** | Nhiều pod và query class cộng dồn. |
| “Page size 10.000 luôn nhanh hơn page size 100.” | **Sai** | Byte/page, GC/network và timeout có thể xấu đi. |
| “`LIMIT 20` đồng nghĩa Cassandra đọc tối đa 20 cells vật lý.” | **Sai** | Tombstone và SSTable version có thể làm scan nhiều hơn. |
| “Driver timeout 20 giây sẽ sửa `Unavailable`.” | **Sai** | Không tạo thêm replica đủ quorum. |
| “`LOCAL_QUORUM` với RF = 3 đòi cả ba replica.” | **Sai** | Cần hai phản hồi trong DC. |
| “Profile `batch-read` đã tách tài nguyên batch khỏi API chính.” | **Sai** | Profile chỉ chọn thông số statement; backend vẫn có thể chung. |
| “Chia file dev/prod nhưng dùng chung password vẫn là tách môi trường tốt.” | **Sai** | Identity và secret phải riêng để giảm blast radius. |
| “CQL RBAC và TLS tự thay cho bounded concurrency.” | **Sai** | Bảo mật không tự giải quyết overload. |
| “Dùng p99 của từng node rồi lấy trung bình ra p99 cluster.” | **Sai** | Phân vị không cộng theo cách đó. |
| “Bật tracing mọi request giúp tăng throughput khi lỗi.” | **Sai** | Tracing tạo overhead. |
| “Cấu hình cần được benchmark và canary theo workload/phiên bản.” | **Đúng** | Tránh biến tối ưu cục bộ thành hồi quy toàn hệ thống. |

## 23. Bài tập tự kiểm tra có đáp án

**Bài 1.** Java service hiện tạo một `CqlSession` trong từng HTTP handler. Lưu lượng 3.000 request/s. Rủi ro và sửa đổi quan trọng nhất là gì?

**Đáp án:** Session churn, TCP/TLS/auth handshakes, metadata load và tài nguyên JVM tăng mạnh. Tạo session **sống lâu dùng chung** (ví dụ singleton do DI quản lý) và đóng khi service shutdown.

**Bài 2.** Một connection Cassandra chỉ phục vụ một request tại một thời điểm như một connection JDBC đang nằm trong transaction. Nhận định này đúng không?

**Đáp án:** **Sai.** Cassandra native protocol/Java Driver hỗ trợ nhiều request multiplexed trên một connection; phải đo in-flight và throughput trước khi tăng connection count.

**Bài 3.** Một dịch vụ có 12 pods, mỗi pod giới hạn 80 in-flight Cassandra statements. Trần lý thuyết toàn fleet là bao nhiêu nếu tất cả đều đạt giới hạn?

**Đáp án:** `12 × 80 = 960` statements đồng thời. Đây không phải số kết nối TCP hoặc throughput/s và chưa tính những luồng khác.

**Bài 4.** Ứng dụng có request rate 400/s và mean DB latency 50 ms ở trạng thái ổn định. In-flight trung bình ước tính? Nếu mean tăng 500 ms thì sao?

**Đáp án:** `400 × 0,05 = 20` và `400 × 0,5 = 200` in-flight trung bình. Không dùng p99 thay mean trong Little's Law.

**Bài 5.** Query có `LIMIT 100`, driver page size 20. Về mặt logic, có thể có bao nhiêu page nếu đủ 100 hàng trả về?

**Đáp án:** Khoảng **5 page** theo target row count; nhưng số request/page thực có thể phụ thuộc paging implementation, row size, server limits và kết quả. `LIMIT` không giảm tombstone scan thành 100.

**Bài 6.** Driver timeout 30 giây, API gateway deadline 800 ms. Chỉ tăng timeout driver có giúp API trả một read mất 4 giây không?

**Đáp án:** **Không.** Gateway hết deadline trước. Cần giảm query cost/queue hoặc đổi hợp đồng API, thiết kế time budget phù hợp.

**Bài 7.** Staging một node với RF = 1 chạy `LOCAL_QUORUM` thành công. Có chứng minh cách service chịu được một replica down ở RF = 3 của production không?

**Đáp án:** **Không.** Môi trường một node không kiểm tra được routing/quorum, speculative execution hay failure handling của RF = 3. Cần staging topology/load phù hợp khi kiểm thử resilience.

**Bài 8.** 20 pods đều `MAX_IN_FLIGHT=100`; traffic tăng khiến Cassandra `tpstats` pending tasks và disk latency tăng. Có nên tăng pool/limit lên gấp đôi?

**Đáp án:** **Không nên tự động.** Backend có dấu hiệu bão hòa; tăng limit có thể đẩy thêm tải. Hãy điều tra query shape, compaction/disk, hot partition, retry rate và giới hạn ingress.

**Bài 9.** Vì sao phân chia `cassandra-dev.conf` và `cassandra-prod.conf` chưa đủ nếu hai môi trường cùng dùng một tài khoản superuser?

**Đáp án:** Credential leak hoặc nhầm endpoint có blast radius cả hai môi trường, khó rotate và quy trách nhiệm. Mỗi service/environment cần identity riêng và least privilege/TLS.

**Bài 10.** Với bảng `PRIMARY KEY ((device_id,event_day),event_time,event_id)`, ứng dụng đọc tuần trước chỉ cung cấp `device_id` và `event_time`. Tăng page size có giúp truy vấn thành partition lookup rẻ không?

**Đáp án:** **Không.** Thiếu `event_day` của partition key. Cần xác định các ngày bucket liên quan, đọc từng partition có giới hạn rồi merge; hoặc dùng projection phù hợp.

**Bài 11.** Async write timeout nhưng một replica đã áp dụng mutation. Nếu retry với `event_id` mới thì rủi ro gì?

**Đáp án:** Duplicate logic vì write cũ có thể đã thành công một phần. Cần stable ID, retry budget, hiểu CL/idempotency và reconciliation phù hợp.

**Bài 12.** Một nhóm đã cấu hình driver request throttler nhưng queue HTTP không giới hạn. Khi Cassandra chậm, app vẫn OOM. Vì sao?

**Đáp án:** Request chờ ở **tầng ứng dụng** trước khi vào driver vẫn chiếm RAM. Cần bounded admission/queue và backpressure ngay từ đầu vào.

## 24. Checklist triển khai production và sơ đồ quyết định

~~~text
CQL / DATA MODEL
[ ] Query hot path có đầy đủ partition key và clustering range.
[ ] Time-series bucket size và read fan-out được benchmark.
[ ] Prepared statements tái sử dụng, không ghép dữ liệu nhạy cảm vào CQL.
[ ] LIMIT, page size, bytes/row và tombstone scan được đo.

JAVA DRIVER LIFECYCLE
[ ] Một CqlSession sống lâu cho logical cluster/identity/config cần thiết.
[ ] Session được DI quản lý; đóng có trật tự khi shutdown.
[ ] Không tạo session mỗi request hoặc tăng pool theo cảm tính.
[ ] Driver version, HOCON option names và effective config được xác minh.

RESOURCE BUDGET
[ ] Bounded admission/queue và concurrency theo workload.
[ ] Tổng budget được tính trên tất cả instances/pods.
[ ] Request/page/API deadline và retry budget rõ ràng.
[ ] Async callbacks không block driver I/O thread.
[ ] Batch/backfill có rate limit và retry/reconciliation bền vững.
[ ] Không bật speculative execution hoặc retry vô hạn.

ENVIRONMENT / SECURITY
[ ] Dev, staging, production có cluster/contact point/DC rõ ràng.
[ ] APP_ENV được allowlist, không có fallback mơ hồ.
[ ] TLS peer validation và truststore/secret manager đúng môi trường.
[ ] Identity và quyền CQL tách theo service, không dùng superuser.
[ ] Config không chứa password/private key, audit/version rõ.
[ ] Staging thử RF/CL, node failure và dữ liệu gần production khi cần.

OBSERVABILITY / ROLLOUT
[ ] p50/p95/p99, throughput, error/retry, queue/permit wait được giám sát.
[ ] Connections/in-flight/driver throttler, JVM GC, server tpstats/disk được đo.
[ ] Metrics labels không chứa device/event IDs hoặc raw payload.
[ ] Load test đủ sample, đo cả peak, compaction và tombstone.
[ ] Canary giới hạn pods/traffic, có stop criteria và rollback.
~~~

~~~mermaid
flowchart TD
    A["Ứng dụng Java Cassandra cần điều chỉnh tài nguyên"] --> B["Kiểm tra query shape, partition key, CL/RF/DC"]
    B --> C["Đo p99, retry, in-flight, queue, GC, disk và nodetool"]
    C --> D{"Bottleneck chính ở client hay replica?"}
    D -->|Client/pool| E["Điều chỉnh có kiểm soát pool/throttler/admission"]
    D -->|Replica/query| F["Sửa CQL/model dữ liệu, rate, compaction/capacity"]
    E --> G["Tính budget toàn fleet và timeout theo API SLO"]
    F --> G
    G --> H["Tách HOCON, TLS, credentials, local DC theo môi trường"]
    H --> I["Staging load test + chaos/failure case"]
    I --> J{"SLO, data correctness, security và resource budgets đạt?"}
    J -->|Không| K["Giữ config cũ, điều tra nguyên nhân"]
    J -->|Có| L["Canary production + quan sát + rollback plan"]
~~~

**Tổng kết:** Java Driver giúp ứng dụng Java giao tiếp với Cassandra hiệu quả nhờ **một `CqlSession` tái sử dụng, routing theo topology, prepared statements, paging và async requests**. Nhưng hiệu quả không đến từ việc nới mọi giới hạn: **connection pool, in-flight, queue, page size, timeout và retry** phải được quản lý theo ngân sách tài nguyên ở **ứng dụng, driver, coordinator và replica**. Đồng thời cần tách rõ **dev/staging/production** về cluster, DC, profile, RF/CL, TLS, credentials và quyền, không dùng chung secret hay fallback mơ hồ. Phương án tốt nhất là **đo workload thật, giới hạn concurrency toàn fleet, sửa query shape khi cần, thử staging và canary có rollback**, thay vì dùng timeout hoặc connection count để che một hệ Cassandra đang quá tải.
