# Theo dõi sức khỏe máy chủ, khả năng kết nối và tính sẵn sàng của Neo4j

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **sức khỏe tiến trình**, **khả năng kết nối Bolt**, **trạng thái database** và **khả năng thực hiện truy vấn nghiệp vụ**.
- Thiết kế các phép kiểm tra **startup**, **liveness**, **readiness** và **synthetic transaction** để tránh báo “khỏe” khi Neo4j không phục vụ được ứng dụng.
- Quan sát CPU, heap, GC, page cache, disk, transaction log, số transaction, Bolt connection và lỗi ở cả Neo4j lẫn Java Driver.
- Kiểm tra database online, các vai trò thành viên cluster và định tuyến đọc/ghi mà không nhầm **port mở** với **khả năng ghi thành công**.
- Thiết lập **SLI/SLO, dashboard, cảnh báo và runbook** dựa trên độ trễ, tỷ lệ lỗi, tài nguyên và triệu chứng thực tế.
- Vận hành giám sát khác nhau cho **self-managed Neo4j**, Docker/Kubernetes và **Aura**, chú ý version, edition, quyền và giới hạn truy cập metrics.
- Xây dựng quy trình xử lý các tình huống như database offline, thiếu disk, connection pool cạn, mất kết nối TLS hoặc cluster mất khả năng ghi.

Chương **Giám sát** của module **DATABASE_ENGINE_GRAPH_NEO4J** tập trung vào việc xác định hệ thống graph có **thực sự sẵn sàng** phục vụ truy vấn hay không. Neo4j lưu node, relationship, property và index, hỗ trợ Cypher để truy vấn liên kết, đường đi; Java Driver và Spring Data Neo4j kết nối qua Bolt. Vì thế, giám sát không chỉ xem một tiến trình Java còn chạy mà còn phải xác định database đúng tên đã online, có thể xác thực, đọc/ghi theo quyền và đáp ứng latency dưới tải.

> **Lưu ý tương thích:** Những ví dụ dưới đây sử dụng API Java Driver hiện đại và một số câu lệnh quản trị phổ biến ở Neo4j 5.x / các dòng Neo4j mới hơn. Tên setting, metrics, quyền DBMS, câu lệnh quản trị và dashboard của dịch vụ được quản lý có thể thay đổi theo **version, edition và mô hình triển khai**. Hãy đối chiếu tài liệu của chính môi trường đang chạy trước khi bật exporter hoặc tự động hóa restart.

## 1. Bốn tầng sức khỏe không nên đánh đồng

Một dịch vụ có thể vượt qua phép thử ping nhưng không xử lý được yêu cầu. Phân tích theo bốn tầng:

| Tầng | Câu hỏi | Phép kiểm tra điển hình | Giới hạn |
| --- | --- | --- | --- |
| **Host/process** | Tiến trình Neo4j có chạy? CPU/RAM/disk còn đủ? | Process status, host/container metrics, OS health | Tiến trình chạy không có nghĩa database online |
| **Transport/Bolt** | Client có mở kết nối tới cổng Bolt? TLS handshake có thành công? | TCP probe, TLS verification, Driver `verifyConnectivity()` | Cổng mở không chứng minh quyền hay query nghiệp vụ thành công |
| **Database** | Database đích đang `online`? Có thành viên phục vụ chế độ truy cập cần thiết? | `SHOW DATABASES`, cluster state, routing/read-write checks | Database online có thể vẫn chậm hoặc thiếu quyền |
| **Application operation** | `MATCH`, `MERGE` hoặc truy vấn đường đi có hoàn tất trong SLO? | Synthetic read/write có kiểm soát, API metrics, query log | Một synthetic query nhỏ không đại diện cho mọi workload |

Ví dụ:

- Cổng 7687 mở nhưng **chứng chỉ TLS hết hạn** → driver không kết nối an toàn được.
- TLS và xác thực hợp lệ nhưng database `orders` đang offline → không chạy được `MATCH` tới `orders`.
- Database online và `RETURN 1` nhanh, nhưng truy vấn khách hàng qua nhiều relationship có p99 = 8 giây → người dùng vẫn thấy lỗi hiệu năng.
- Database đọc được trên cluster, nhưng không có server **writer** khả dụng → các API có ghi bị lỗi.

**Kết luận sơ bộ:** Chỉ báo sức khỏe phải gắn với **mục tiêu sử dụng cụ thể**: đọc, ghi, thao tác quản trị hay thuật toán phân tích.

~~~mermaid
flowchart TD
    A["HTTP / Java Driver request"] --> B{"Network + TLS + Auth OK?"}
    B -->|Không| X["Lỗi kết nối"]
    B -->|Có| C{"Database đích ONLINE?"}
    C -->|Không| Y["Database unavailable"]
    C -->|Có| D{"Có read/write route phù hợp?"}
    D -->|Không| Z["Operation unavailable"]
    D -->|Có| E{"Cypher hoàn tất trong SLO?"}
    E -->|Không| W["Degraded / slow"]
    E -->|Có| F["Ứng dụng sẵn sàng"]
~~~

## 2. Từ tín hiệu hạ tầng tới trải nghiệm người dùng

Một hệ thống Neo4j phục vụ website bán hàng có những loại thao tác khác nhau:

| Loại request | Ví dụ Cypher | Điều người dùng kỳ vọng |
| --- | --- | --- |
| **Lookup** | `MATCH (c:Customer {customerId:$id}) RETURN c` | Thông tin khách hàng trả đúng và nhanh |
| **Traversal** | `(c)-[:PLACED]->(o)` | Danh sách đơn/quan hệ đầy đủ trong phạm vi yêu cầu |
| **Path query** | Tìm đường đi giữa các `Person` | Không timeout dưới đồ thị có fan-out lớn |
| **Write transaction** | `MERGE` Order + `PLACED` trong `executeWrite` | Tạo đơn nguyên tử, không báo thành công khi commit lỗi |
| **Import/batch** | `UNWIND` nhiều bản ghi trong nhiều transaction | Không bóp nghẹt các API online |

Một bảng điều khiển tốt phải bao gồm **bốn tín hiệu cốt lõi**:

1. **Traffic:** bao nhiêu yêu cầu đọc/ghi và transaction hoàn tất mỗi giây?
2. **Errors:** bao nhiêu yêu cầu thất bại, timeout, vi phạm constraint hoặc không kết nối được?
3. **Latency:** p50/p95/p99 từ **góc nhìn ứng dụng**, cùng thời gian xử lý database nếu quan sát được.
4. **Saturation:** CPU, heap/GC, page cache misses, disk I/O, pool đang đợi và lock contention.

Chỉ một đồ thị CPU cao **không đủ** chứng minh cần nâng cấu hình. Cần ghép CPU với traffic, latency, queue và lỗi ở **cùng mốc thời gian** để biết hệ thống đang làm nhiều việc hữu ích hay đang nghẽn.

## 3. Startup, liveness, readiness và synthetic probe

### 3.1. Startup probe

**Startup** trả lời “Neo4j đã khởi động tới bước có thể bắt đầu kiểm tra bình thường chưa?”. Sau restart, database có thể phải recovery transaction log, kiểm tra store hoặc bắt đầu xây dựng index.

Nếu startup mất nhiều thời gian hợp lệ nhưng liveness probe quá gắt, orchestrator có thể **kill/restart lặp vô hạn** trước khi DB hoàn tất recovery. Dùng startup budget/initial delay thích hợp và quan sát log khởi động thay vì đặt timeout vài giây cho mọi môi trường.

### 3.2. Liveness probe

**Liveness** trả lời “tiến trình có bị kẹt nghiêm trọng và cần khởi động lại không?”. Liveness nên là phép thử **nhẹ, ổn định**, tránh phụ thuộc vào hệ thống bên ngoài vốn có thể bị lỗi tạm thời.

Một port/TCP check có thể phù hợp để đánh giá **tầng transport** của tiến trình, nhưng **không đủ làm readiness của database**. Không nên tự động restart Neo4j chỉ vì một lần synthetic query đọc chậm hoặc một node cluster không có quyền ghi tại thời điểm đó.

### 3.3. Readiness probe

**Readiness** trả lời “instance/endpoint hiện có thể nhận lưu lượng công việc mà nó được giao không?”. Với API đọc:

- Client kết nối và xác thực thành công.
- Database cần đọc đã online.
- Một câu query nhẹ thực thi được với role ứng dụng.
- Độ trễ không vượt ngưỡng ngắn hạn của health probe.

Với **dịch vụ ghi**, readiness còn cần đường tới thành viên có thể xử lý transaction ghi. Một follower/secondary vẫn có thể là **readiness tốt cho READ** nhưng không thể nhận mọi WRITE trực tiếp.

### 3.4. Synthetic transaction

Synthetic probe chạy hành động tương tự người dùng, ví dụ `RETURN 1` và một truy vấn lookup có tham số đại diện. Nó bổ sung bằng chứng “dịch vụ đang làm được việc” ngoài tín hiệu process.

~~~cypher
// Phép đọc tối thiểu; kiểm tra quyền và đường chạy Cypher.
RETURN 1 AS ok;
~~~

~~~cypher
// Phép đọc nghiệp vụ nhẹ trên một fixture được phép tồn tại.
MATCH (c:HealthCheck {checkId: $checkId})
RETURN c.checkId AS checkId;
~~~

**Chú ý:** Đoạn thứ hai chỉ có ý nghĩa nếu hệ thống đã có fixture `HealthCheck` hợp lệ và bạn kiểm soát được vòng đời của nó. Fixture mất không nhất thiết có nghĩa database lỗi; cần phân biệt lỗi dữ liệu giám sát với lỗi nền tảng.

**Không dùng** `CREATE` hoặc `DELETE` trong liveness probe chạy mỗi vài giây: sẽ làm tăng transaction log, khóa và có thể gây bùng nổ dữ liệu. Nếu cần chứng minh **write availability end-to-end**, dùng một luồng synthetic riêng có lịch thưa, namespace riêng, ID ổn định và cơ chế cleanup/reconciliation.

## 4. Kiểm tra trạng thái database bằng Cypher quản trị

Trên môi trường và tài khoản có quyền thích hợp, Neo4j hỗ trợ quan sát database qua các lệnh `SHOW`.

~~~cypher
SHOW DATABASES
YIELD name, requestedStatus, currentStatus, statusMessage
RETURN name, requestedStatus, currentStatus, statusMessage
ORDER BY name;
~~~

Với các dòng version có các cột này, `requestedStatus` phản ánh trạng thái **mong muốn**, còn `currentStatus` phản ánh tình trạng hiện tại trên thành viên/ngữ cảnh đang kiểm tra. Quan sát cả **statusMessage** thay vì chỉ lấy tên DB. Trong cluster, kết quả có thể thay đổi theo server và quyền; không khẳng định một lần `SHOW DATABASES` từ một endpoint đã khảo sát mọi thành viên.

Ví dụ cách đọc:

| Tình trạng | Diễn giải | Bước kiểm tra |
| --- | --- | --- |
| Requested và current đều `online` | Database trên phạm vi được hỏi có vẻ sẵn sàng | Vẫn chạy synthetic query theo quyền ứng dụng |
| Requested `online` nhưng current khác `online` | Database chưa đạt trạng thái mong muốn | Xem statusMessage, log, disk, recovery/cluster |
| Requested `offline` | Có thể đã bị quản trị viên chủ động đưa offline | Kiểm tra thay đổi vận hành, không tự khởi động lại tùy tiện |
| DB không xuất hiện | Sai tên, thiếu quyền, chưa được tạo hoặc môi trường ẩn chi tiết | Kiểm tra database name/role và hệ thống quản trị |

Nếu chỉ cần xem danh sách:

~~~cypher
SHOW DATABASES;
~~~

**Lưu ý:** Không chạy các câu `START DATABASE`, `STOP DATABASE`, `DROP DATABASE` để “thử monitoring”. Chúng là thay đổi trạng thái thật, yêu cầu quyền quản trị và có thể gây outage.

### 4.1. Kiểm tra version/edition

~~~cypher
CALL dbms.components()
YIELD name, versions, edition
RETURN name, versions, edition;
~~~

Chạy khi quyền và deployment cho phép. Điều này giúp nhận diện môi trường có hỗ trợ các metric, role, cluster procedure hoặc chức năng quan sát chi tiết nào. Khi tự động hóa, đừng coi tên cột hoặc procedure là bất biến xuyên mọi version.

### 4.2. Cluster: quan sát máy chủ và vai trò

Trong hệ thống hỗ trợ multi-server và quyền quản trị, câu lệnh:

~~~cypher
SHOW SERVERS;
~~~

có thể cung cấp thông tin các server được biết đến trong topology tương ứng. Tính sẵn có và nội dung của lệnh tùy **version/edition và cấu hình cluster**; một instance đơn lẻ hoặc Aura có thể không cho dùng theo cùng cách.

Đừng đồng nhất:

- **Server process healthy:** máy chủ Neo4j còn chạy.
- **Database available:** database đích có bản phục vụ hoạt động.
- **Read route available:** ứng dụng có thể thực hiện đọc.
- **Write route available:** ứng dụng có thể commit transaction ghi.
- **Causal read satisfied:** một phiên đọc phụ thuộc đã thấy transaction ghi trước đó theo bookmark.

Ở Neo4j cluster có cơ chế đồng thuận, **mất quorum hoặc thiếu primary phù hợp** có thể khiến ghi không thực hiện được dù nhiều thành viên vẫn trả lời ping. Quan sát topology/role, thành viên không đồng bộ và lỗi routing cùng lúc.

## 5. Kiểm tra kết nối từ Java Driver: đừng dừng ở mở cổng

Trong ứng dụng Java, `Driver` là đối tượng được tạo để dùng chung, có connection pool. `Session` nên dùng theo request/đơn vị công việc và không chia sẻ một Session giữa nhiều luồng.

### 5.1. Khởi tạo Driver và xác minh connectivity

~~~java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;

public final class Neo4jConnectivity {
    public static void main(String[] args) {
        String uri = System.getenv("NEO4J_URI");
        String username = System.getenv("NEO4J_USERNAME");
        String password = System.getenv("NEO4J_PASSWORD");

        try (Driver driver = GraphDatabase.driver(
                uri, AuthTokens.basic(username, password))) {
            driver.verifyConnectivity();
            System.out.println("Neo4j driver connectivity OK");
        }
    }
}
~~~

Ví dụ yêu cầu khai báo ba biến môi trường trước khi chạy; không dùng URI/secret được hard-code trong source. `verifyConnectivity()` hữu ích để phát hiện vấn đề **network/TLS/auth/routing** sớm, nhưng **không chứng minh một transaction ghi nghiệp vụ sẽ thành công**, hoặc chứng minh mọi database đều online.

### 5.2. Chạy synthetic read trên đúng database

~~~java
import java.util.concurrent.TimeUnit;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class Neo4jReadHealth {
    public record HealthResult(boolean ready, long latencyMillis) {}

    public static HealthResult check(
            Driver driver, String databaseName) {
        long started = System.nanoTime();

        try (Session session = driver.session(
                SessionConfig.forDatabase(databaseName))) {
            int result = session.executeRead(tx ->
                    tx.run("RETURN 1 AS ok")
                      .single()
                      .get("ok")
                      .asInt());

            long elapsedMillis = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - started);
            return new HealthResult(result == 1, elapsedMillis);
        }
    }
}
~~~

Đoạn code là **phần kiểm tra thành công**, không phải endpoint readiness hoàn chỉnh. Caller cần **bắt exception và phân loại lỗi** (ví dụ timeout, authentication, service unavailable) để đưa ra trạng thái health thích hợp, đồng thời tránh trả chi tiết bí mật cho HTTP client.

**Quan trọng:** `executeRead` có thể thử lại callback khi gặp lỗi transient phù hợp. Latency đo bên ngoài phản ánh thời gian người dùng chờ bao gồm cả phần retry này; một lần `RETURN 1` nhanh sau retry không phủ nhận hệ thống đang có dấu hiệu chập chờn.

### 5.3. URI routing và TLS

| URI kiểu | Ý nghĩa sử dụng | Lưu ý |
| --- | --- | --- |
| `neo4j://host:7687` | Định tuyến bằng routing driver | Phù hợp khi client cần khám phá read/write route |
| `neo4j+s://host:7687` | Routing với TLS và xác minh chứng chỉ của CA tin cậy | Thường phù hợp cho kết nối production có CA tin cậy |
| `neo4j+ssc://host:7687` | Routing TLS chấp nhận chứng chỉ tự ký theo semantics driver | Chỉ dùng khi đã đánh giá chính sách bảo mật; không thay cho xác thực đầy đủ |
| `bolt://host:7687` | Kết nối trực tiếp tới một endpoint Bolt | Không tự có lợi ích routing của scheme `neo4j://` |

Scheme là lựa chọn theo môi trường và phiên bản driver; không chuyển sang kết nối thiếu xác minh TLS chỉ để “giải quyết” lỗi chứng chỉ. Kiểm tra hostname, SAN, CA chain, thời hạn chứng chỉ, cổng và proxy/LB.

Trong cluster, một `bolt://` nhắm nhầm vào thành viên chỉ đọc có thể khiến write thất bại; với routing URI, driver có thể chọn đích phù hợp dựa trên routing table. Cần quan sát **loại operation READ/WRITE** chứ không chỉ số lượng connection.

## 6. Readiness của Java API và readiness của Neo4j khác nhau

Với Spring Boot, ứng dụng có thể cung cấp endpoint `/actuator/health` qua Spring Boot Actuator nếu được cấu hình. Một số phiên bản/framework cung cấp health indicator cho Neo4j; khả năng auto-configuration và chi tiết kết quả phụ thuộc dependency, version, settings và quyền tài khoản.

Nên phân tách ít nhất:

- **App liveness:** HTTP server và tiến trình còn hoạt động, không cần chờ database trong mọi lần probe.
- **App readiness:** các dependency **bắt buộc để xử lý request** sẵn sàng, trong đó có Neo4j nếu API phụ thuộc Neo4j.
- **Neo4j synthetic operations:** kiểm tra đọc và, nếu có nhu cầu, ghi ở một kênh/chu kỳ riêng.

Ví dụ kiến trúc:

~~~mermaid
flowchart TB
    K["Kubernetes / Load Balancer"] --> L["App /health/liveness"]
    K --> R["App /health/readiness"]
    R --> C["Neo4j Driver + query nhẹ"]
    M["Monitoring job"] --> W["Read/Write synthetic có kiểm soát"]
    W --> N[("Neo4j cluster")]
    C --> N
~~~

Đừng dùng chung một readiness endpoint rất tốn thời gian để probe liên tục ở hàng trăm pod. Nếu 200 pod gọi Neo4j mỗi giây, health checking có thể tự gây tải. Có thể cache kết quả health ngắn hạn, dùng connection pool hợp lý và tạo một synthetic job riêng theo lịch.

**Không đưa** tên server nội bộ, stack trace, credential, routing table hay kết quả query nhạy cảm vào response health công khai. Giới hạn truy cập hoặc cấu hình chi tiết dành riêng cho hệ thống giám sát nội bộ.

## 7. Bộ chỉ số tài nguyên cần quan sát

### 7.1. CPU, heap, GC và native memory

| Chỉ số | Khi thay đổi bất thường | Nguyên nhân khả dĩ |
| --- | --- | --- |
| CPU tiến trình Neo4j / host | Cao kéo dài và throughput không tăng | Cypher mở rộng quan hệ quá nhiều, load cao, query/GC contention |
| Heap used/committed/max | Gần giới hạn và GC nhiều | Query lớn, nhiều result/transaction, GDS hoặc plugin sử dụng heap |
| GC pause/time | Có pause dài, p99 tăng | Áp lực tạo object, heap không phù hợp, allocation lớn |
| Native/direct memory | Tăng ngoài heap | Memory mapping, network/driver, các cấu trúc ngoài heap tùy runtime |
| OS memory pressure / swap | Swap hoặc OOM | Tổng RAM dành cho heap + page cache + OS quá cao |

Một tiến trình Java có heap chưa đầy vẫn có thể bị OOM-kill nếu **page cache, native memory và các container khác** làm cạn tổng RAM. Đừng chỉ theo dõi `jvm.heap.used` rồi khẳng định hệ thống đủ bộ nhớ.

### 7.2. Page cache

Neo4j dùng **page cache** để hỗ trợ đọc/ghi dữ liệu lưu trữ. Các khái niệm cần xem:

- **Page cache hits/misses**: liệu trang dữ liệu được tìm trong cache hay không.
- **Page faults / I/O**: phải nạp trang từ storage bao nhiêu, trên workload nào.
- **Dung lượng page cache đã cấu hình** so với RAM và working set thực tế.

Tỷ lệ hit cao có thể tốt, nhưng **không đồng nghĩa query tối ưu**. Một traversal không cần thiết qua hàng triệu relationship có thể tạo nhiều lần chạm cache, gây CPU và DB Hits cao dù dữ liệu đã ở RAM.

### 7.3. Disk, store và transaction log

Theo dõi:

- **Dung lượng trống và tốc độ tăng** của filesystem chứa database, transaction logs và backup/staging.
- **Latency I/O đọc/ghi**, queue depth, throughput và IOPS khi workload tăng.
- **Checkpoint**, khối lượng transaction ghi, các đợt import/batch.
- **Dung lượng log** và chính sách retention/pruning tương ứng.

Database có thể từ chối ghi hoặc trở nên không ổn định khi ổ đĩa gần đầy. Alert cần có cả **phần trăm dùng** và **dung lượng tuyệt đối**: còn 5% trên đĩa 10 TB rất khác còn 5% trên đĩa 20 GB. Nên tính **thời gian dự kiến tới ngưỡng** từ tốc độ tăng và quan sát backup/import cùng lúc.

### 7.4. Bolt connections, transaction và khóa

Các nhóm metric hữu ích:

- Bolt connections đang mở/đang bận, số connection mới và các lỗi kết nối.
- Transaction đang hoạt động, commit/rollback, thời gian thực thi và lỗi transient.
- Connection pool của **Java Driver phía ứng dụng**: số connection đang dùng, đang chờ, chờ quá lâu và timeout (nếu instrumentation hỗ trợ).
- Query latency, query count, loại READ/WRITE, wait time/lock contention khi có.

**Server Bolt connection count khác client pool queue.** Nếu pool phía ứng dụng cạn, nhiều request có thể chờ trước khi bắt đầu một query; database lúc đó chưa chắc có CPU cao. Ngược lại, mở pool quá lớn có thể làm tăng tranh chấp và khiến server bão hòa.

## 8. Thu thập metrics: self-managed, Prometheus và Aura

Trong **self-managed Neo4j**, bản Enterprise và các dòng version hỗ trợ có cơ chế xuất metrics. Một cấu hình phổ biến ở Neo4j 5.x dùng:

~~~properties
# neo4j.conf - minh họa trên bản hỗ trợ các setting này
server.metrics.enabled=true
server.metrics.prometheus.enabled=true
server.metrics.prometheus.endpoint=127.0.0.1:2004
~~~

Đây chỉ là **ví dụ minh họa**, không phải hợp đồng cấu hình của mọi version/edition. Kiểm tra các tên setting trong [Neo4j Operations Manual — Monitoring](https://neo4j.com/docs/operations-manual/current/monitoring/) tương ứng với bản đang chạy. Trước khi dùng exporter, cần xác nhận port, địa chỉ bind, quyền và **mức hỗ trợ metrics của edition**.

**Bảo mật exporter:** Không mở Prometheus endpoint ra Internet công khai. Ưu tiên bind địa chỉ nội bộ, network policy/firewall hoặc proxy có xác thực/TLS theo kiến trúc mạng. Metrics có thể lộ topology và thông tin vận hành.

Ví dụ một sơ đồ thu thập:

~~~mermaid
flowchart LR
    N1[("Neo4j node A")] -->|metrics endpoint| P["Prometheus scraper"]
    N2[("Neo4j node B")] -->|metrics endpoint| P
    APP["Java / Spring API"] -->|Micrometer metrics| P
    OS["Node exporter / cAdvisor"] --> P
    P --> D["Dashboard / alert rules"]
    D --> ON["On-call / Incident response"]
~~~

### 8.1. Tại sao phải kết hợp metrics từ nhiều nguồn?

Neo4j database metric có thể cho biết page cache misses, nhưng không trực tiếp cho biết HTTP p99 của ứng dụng. OS metric biết disk gần đầy, nhưng không phân biệt truy vấn `MATCH` nào đã gây tải. App metric thấy số lần timeout, nhưng không giải thích server đang full heap hay connection pool đang chờ.

Ghép ba phạm vi:

1. **Application:** request type, latency, error/timeout, client-side pool.
2. **Neo4j process/database:** Bolt, transaction, CPU/heap/page cache, query log, state/routing.
3. **Host/container/network:** RAM, disk, I/O, OOM event, TLS, DNS, packet loss/latency.

Nếu hệ thống có nhiều database/cluster, gắn nhãn metric phù hợp như **environment, instance, database, operation**; tránh dùng `customerId`/`orderId` làm nhãn vì cardinality lớn và có nguy cơ lộ dữ liệu.

### 8.2. Aura: môi trường được quản lý

Với **Neo4j Aura**, hạ tầng và một phần giám sát nội bộ do nhà cung cấp quản lý. Người thuê thường sử dụng **dashboard/metrics/logs mà Aura hiển thị hoặc tích hợp được gói thuê hỗ trợ**, chứ không sửa trực tiếp `neo4j.conf` hay mở port exporter trên host.

Điều ứng dụng vẫn cần tự đo:

- API read/write latency, error rate và retry.
- Driver connection/routing/TLS failures.
- Freshness của read model hoặc các job đồng bộ với hệ thống khác.
- Các synthetic query theo role ứng dụng và trạng thái truy cập sau thay đổi mạng/quyền.

Không giả định mọi gói Aura có cùng quyền truy cập metrics chi tiết, cluster views hoặc custom exporter. Kiểm tra dashboard và API thực tế của gói triển khai.

## 9. Theo dõi query, log và sự cố hiệu năng

Query chậm không nhất thiết khiến tiến trình ngừng hoặc database offline. Khi một API traversal quá thời hạn:

~~~cypher
EXPLAIN
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
RETURN o.orderId
LIMIT 20;
~~~

`EXPLAIN` lập kế hoạch mà **không chạy phần query chính**, phù hợp để xem `NodeIndexSeek`/`NodeByLabelScan`/`Expand` và ước lượng số hàng.

~~~cypher
PROFILE
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
RETURN o.orderId
LIMIT 20;
~~~

`PROFILE` **thực sự chạy query**, bổ sung `Rows`/`DB Hits` và thông tin runtime tùy version. Không chạy `PROFILE` của query có ghi trên production chỉ để “xem plan”; lệnh ghi vẫn sẽ được thực thi.

### Những triệu chứng điển hình

| Dấu hiệu | Giả thuyết | Kiểm tra tiếp |
| --- | --- | --- |
| p99 tăng nhưng CPU Neo4j thấp | Client đợi pool, network, lock hoặc route | Driver pool pending, lock wait, TLS/network |
| CPU tăng, throughput không tăng | Query scan/expand nhiều hàng hoặc bão hòa | `PROFILE`, `Rows`/`DB Hits`, traffic mix |
| GC pause tăng và heap sát max | Graph projection/batch query quá lớn | Heap, allocation, plugin/GDS, query memory |
| Page cache misses và disk latency cùng tăng | Working set không nằm đủ trong cache | Page cache sizing, I/O, pattern query |
| Write timeout nhưng read vẫn tốt | Writer unavailable, lock contention, disk/log nghẽn | Routing, cluster, write transaction errors |
| Chỉ request một vài customer rất chậm | Node có bậc quan hệ cao, dữ liệu lệch | Fan-out, query plan theo tham số thực tế |
| Nhiều `ServiceUnavailable` sau rollout | Sai URI, cert, DNS hoặc routing | TLS handshake, driver config, logs |

**Không bật verbose query logging vô hạn**: có thể làm tăng I/O và lưu tham số chứa dữ liệu nhạy cảm. Dùng threshold, sampling, redaction và retention theo cấu hình version/edition tương ứng.

## 10. SLI, SLO và alerting theo mục tiêu dịch vụ

### 10.1. Định nghĩa SLI có phạm vi rõ

**Service Level Indicator (SLI)** là chỉ số đo chất lượng trải nghiệm của một operation. Ví dụ:

\[
\text{Availability SLI} =
\frac{\text{Số request hợp lệ đáp ứng tiêu chí thành công}}
{\text{Tổng request hợp lệ được ghi nhận}}
\]

Một request có thể phải đáp ứng **cả kết quả đúng và thời hạn latency** để được tính thành công. Không loại tất cả timeout khỏi mẫu số rồi công bố availability đẹp hơn thực tế.

Định nghĩa riêng:

- **Read availability SLI:** các lookup/traversal quan trọng trả kết quả đúng trong thời hạn.
- **Write availability SLI:** các transaction ghi quan trọng commit đúng và được ứng dụng xác nhận trong thời hạn.
- **Latency SLI:** p95/p99 end-to-end của từng operation.
- **Data freshness SLI:** thời gian từ source commit tới graph projection khi dùng CDC/outbox.

Một server có uptime gần 100% nhưng write availability thấp **không đạt mục tiêu người dùng**.

### 10.2. SLO minh họa

| Operation | SLO ví dụ | Cách đo |
| --- | --- | --- |
| Lookup Customer | 99,9% request hợp lệ hoàn tất thành công trong 200 ms | HTTP/APM + kết quả query |
| Create Order | 99,95% request hợp lệ commit đúng trong 500 ms | API metric + transaction result |
| Read graph traversal | p95 dưới 400 ms tại mức tải mục tiêu | Load test + production metric |
| Graph projection freshness | 99% sự kiện xuất hiện trong 10 giây | Source commit timestamp + apply timestamp |

Các ngưỡng này là **giả định để học**, không phải tiêu chuẩn do Neo4j bảo đảm. Chọn dựa trên nhu cầu sản phẩm, năng lực hệ thống và cách tính error budget.

### 10.3. Quy tắc cảnh báo tốt

- **Impact-based alert:** tỷ lệ lỗi read/write hoặc p95/p99 vượt SLO trong một cửa sổ đủ mẫu.
- **Saturation alert:** disk tiến tới đầy, GC liên tục, pool pending kéo dài, page cache/memory pressure.
- **Topology alert:** không có write route hoặc database mong muốn online nhưng không online.
- **Silent failure alert:** metrics không tới hệ thống giám sát, synthetic job không chạy hoặc không còn sample hợp lệ.
- **Recovery alert:** sau khi một thành viên trở lại, backlog/read model vẫn tăng hoặc reconciliation phát hiện dữ liệu thiếu.

Hạn chế cảnh báo theo **một sample** CPU > 80% vì dễ nhiễu. Dùng cửa sổ thời gian, ngưỡng kéo dài, mức độ ảnh hưởng, tỷ lệ request và nhóm triệu chứng. Các mức cảnh báo có thể chia:

| Mức | Ví dụ | Hành động |
| --- | --- | --- |
| **Critical** | Write request fail diện rộng, database offline, disk đầy gây ngừng ghi | Gọi on-call ngay, ưu tiên phục hồi |
| **Warning** | Page cache miss tăng, disk sắp đạt ngưỡng, p95 xấu dần | Điều tra/capacity planning |
| **Info** | Một restart có kế hoạch hoặc thay đổi version | Gắn annotation vào dashboard để giải thích biến động |

## 11. Kiểm tra health theo chu kỳ mà không tạo tải nguy hiểm

Tần suất probe là một phần kiến trúc:

- **Liveness:** nhẹ, không ghi, chu kỳ phù hợp orchestrator.
- **Readiness:** query rất nhỏ trên database bắt buộc, có timeout ngắn và caching nếu số instance lớn.
- **Synthetic nghiệp vụ:** chu kỳ dài hơn; dùng fixture/nội dung được kiểm soát, ghi nhận latency/lỗi.
- **Deep diagnostics:** `PROFILE`, query log chi tiết, heap dump, cluster inspection chỉ khi cần và theo quyền, **không chạy mỗi vài giây**.

Ví dụ thiết kế kiểm tra:

~~~text
Every 10s: app liveness (process)
Every 15s: app readiness (Driver read probe, cached briefly)
Every 60s: central synthetic lookup (read + latency)
Every 5m: dedicated synthetic write/delete workflow (if permitted)
Every 1m: scrape host/process metrics
Every 1h: reconcile selected business graph counts/freshness
~~~

Các mốc là **lịch gợi ý minh họa**, không phải bắt buộc. Chúng phải dựa trên số lượng pod, SLO, quy mô DB, thời gian startup và chi phí kiểm tra. Nếu một công ty có 500 API replicas, một probe tới Neo4j mỗi 5 giây từ mỗi replica có thể tạo 100 query/s **chỉ từ health checks**.

Một synthetic write cần:

1. Dùng **database/namespace/label canary riêng** được duyệt và service account tối thiểu.
2. Ghi với **ID ổn định**, TTL/cleanup có giám sát; không sửa dữ liệu người dùng.
3. Kiểm tra commit thành công và sau đó đọc lại theo yêu cầu.
4. Không dựa vào việc transaction write sẽ “tự rollback” nếu callback thành công.
5. Có cơ chế dừng nếu Neo4j đang quá tải để monitoring không làm outage nặng hơn.

## 12. Docker/Kubernetes: không dùng một probe cho mọi trách nhiệm

Trong container, restart tự động giúp phục hồi một số lỗi tiến trình nhưng cũng có thể làm tình hình tệ hơn khi lỗi xuất phát từ **disk, cấu hình hoặc mất quorum**.

### 12.1. Mẫu kiến trúc probe

~~~mermaid
flowchart TD
    K["Kubernetes probes"] --> ST["startupProbe: thời gian recovery"]
    K --> LV["livenessProbe: process/transport nhẹ"]
    K --> RD["readinessProbe: database/role + query nhẹ"]
    RD --> TRAFFIC["Cho phép nhận traffic"]
    MON["Prometheus / Monitoring"] --> MET["Neo4j + JVM + host metrics"]
    MON --> SY["Synthetic app read/write"]
~~~

**Startup** bảo vệ giai đoạn recovery; **liveness** phát hiện tiến trình kẹt; **readiness** giúp ngừng điều phối request đến thành viên chưa phục vụ được. Tránh để một database offline có chủ đích khiến orchestrator liên tục khởi động lại container dù tiến trình đang làm đúng nhiệm vụ vận hành.

### 12.2. TCP socket probe là cần nhưng chưa đủ

Một cấu hình Kubernetes minh họa **kiểm tra transport**:

~~~yaml
# Chỉ là fragment minh họa trong một container spec;
# tcpSocket không xác minh TLS, auth, database, routing hoặc query.
livenessProbe:
  tcpSocket:
    port: 7687
  periodSeconds: 30
  timeoutSeconds: 3
  failureThreshold: 5
~~~

Đây không phải manifest hoàn chỉnh và các giá trị cần điều chỉnh theo thời gian startup/recovery. **Không copy TCP probe này sang readiness rồi kết luận Neo4j sẵn sàng cho mọi API**. Với cluster, thiết kế health của từng workload đọc/ghi ở tầng ứng dụng hoặc dùng cơ chế chính thức mà chart/edition cung cấp.

### 12.3. Không dùng health check để “tự chữa” bằng thay đổi nguy hiểm

Một phản ứng tự động khi fail thường là **loại khỏi load balancing** hoặc **khởi động lại tiến trình nếu có bằng chứng bị kẹt**. Không nên tự động:

- `DROP` database hoặc xóa transaction log.
- Đổi toàn cluster sang writable mà không hiểu role/quorum.
- Tắt xác minh TLS, tăng quyền role hoặc vô hiệu hóa security.
- Xóa index đang xây dựng vì readiness báo chậm.
- Khởi động lại mọi primary đồng thời, gây mất khả năng phục vụ lớn hơn.

Tự động hóa recovery phải dựa trên runbook và điều kiện an toàn được phê duyệt.

## 13. Runbook: sự cố kết nối Neo4j từ ứng dụng

### Tình huống A — Không thể thiết lập Bolt connection

Triệu chứng: `ServiceUnavailable`, connection refused, DNS failure hoặc TLS handshake error.

Quy trình:

1. **Xác định phạm vi:** mọi client hay một nhóm pod/host? Neo4j Browser, Java API và synthetic probe có cùng thất bại?
2. **Kiểm tra mạng:** DNS, routing, firewall/network policy, endpoint/port và load balancer.
3. **Kiểm tra TLS:** scheme `neo4j+s`/`bolt+s`, tên host, chứng chỉ CA, thời hạn, thay đổi mới.
4. **Kiểm tra auth:** user, secret rotation, quyền truy cập DB, lỗi xác thực; không in password vào log.
5. **Kiểm tra server:** process, database currentStatus và logs.
6. **Khôi phục:** sửa cấu hình/deployment/secret/route theo nguyên nhân, thử lại một synthetic read an toàn và theo dõi p95/error rate.

Không “khắc phục” lỗi bằng cách chuyển từ TLS được xác minh sang plaintext trước khi xác định nguyên nhân.

### Tình huống B — Đọc được nhưng không ghi được

Triệu chứng: `executeRead` chạy, `executeWrite` trả unavailable, read-only hoặc routing error.

Điều tra:

- Kết nối bằng `bolt://` trực tiếp tới read-only member hay bằng routing URI?
- Database/cluster có writable route và quorum không?
- User có quyền WRITE với label/relationship/properties tương ứng không?
- Disk/transaction log còn chỗ để commit không?
- Có transaction dài/lock contention hoặc constraint error hay không?

**Không chuyển thẳng quyền admin cho API** chỉ vì lỗi permission. Phải xác định quyền chính xác cần cấp và kiểm tra transaction.

### Tình huống C — Kết nối OK nhưng p99 tăng mạnh

1. Xem traffic/rate, số errors/timeouts, pool pending và Bolt connection.
2. Đối chiếu CPU, GC, heap, page cache, disk I/O tại cùng thời điểm.
3. Xác định query family gây tải bằng logging/tracing đã kiểm soát.
4. Chạy `EXPLAIN` và khi an toàn `PROFILE` với tham số **đại diện**.
5. Kiểm tra fan-out, index, `Sort`, `Expand`, transaction dài và tỷ lệ đọc/ghi.
6. Cân nhắc giảm offered load, giãn batch, giới hạn kết quả hoặc cải thiện Cypher/index; đo lại trước khi nâng pool vô hạn.

### Tình huống D — Disk gần đầy

1. Xác định **phân vùng nào** gần đầy: data store, transaction log, backup hay import.
2. Kiểm tra tốc độ tăng và các job vừa khởi chạy (import, CDC, backup, GDS write).
3. Tạm dừng workload không thiết yếu theo runbook; mở rộng dung lượng nếu cần.
4. Không xóa thủ công transaction log hoặc file store khi database đang chạy.
5. Phục hồi cấu hình/retention/backup policy đúng chuẩn rồi kiểm tra consistency và khả năng ghi.

### Tình huống E — Thành viên cluster mất kết nối

1. Xác định server, database và vai trò bị ảnh hưởng.
2. Kiểm tra network giữa các thành viên, thay đổi chứng chỉ và cluster logs.
3. Đánh giá **còn đủ thành viên/đa số cần thiết** cho chức năng ghi hay không.
4. Tránh restart đồng loạt hoặc thay đổi membership không có kế hoạch.
5. Khi thành viên trở lại, theo dõi routing, replication/đồng bộ, latency và kết quả synthetic read/write.

## 14. Bảng phân biệt lỗi thường gặp

| Triệu chứng | Không nên kết luận vội | Kiểm tra đúng |
| --- | --- | --- |
| TCP 7687 mở | “Database chắc chắn healthy” | TLS, auth, database online, Cypher read/write |
| `verifyConnectivity()` thành công | “Mọi nghiệp vụ ghi sẽ thành công” | Quyền WRITE, write route, transaction commit |
| `RETURN 1` nhanh | “Mọi traversal graph đều nhanh” | p95/p99 và `PROFILE` query thực |
| CPU thấp | “Không có nghẽn” | Pool, lock wait, disk, network, routing |
| Page cache hit ratio cao | “Không cần tối ưu query” | DB Hits, fan-out, sort, actual rows |
| Một node cluster online | “Cluster ghi được” | Topology, quorum, writer, role |
| Driver retry thành công | “Không có outage” | Retry count, latency end-to-end, error budget |
| `SHOW DATABASES` trả online | “Không cần giám sát ứng dụng” | SLI từ HTTP/transaction thực |
| GDS job chạy nặng | “Database đã bị lỗi” | Bảo vệ workload online, resource, lịch phân tích |

Một hệ thống **sẵn sàng** là hệ thống có thể cung cấp **đúng chức năng được cam kết** dưới tải mục tiêu, không đơn thuần là không có exception trong một lần ping.

## 15. Bài thực hành xây dashboard sức khỏe Neo4j

### Bối cảnh

Ứng dụng Spring Boot quản lý `Customer` và `Order` trong Neo4j; một API đọc theo `customerId` và một API ghi `Order`/`PLACED`. Hệ thống có thể chạy self-managed hoặc Aura.

### Bước 1 — Xác định SLI

Đặt hai phép đo **tách biệt**:

1. `GET /customers/{id}/orders`: tỷ lệ thành công và latency p50/p95/p99.
2. `POST /orders`: tỷ lệ transaction commit thành công và latency từ API đến commit.

Ghi rõ timeout, lỗi client được loại khỏi SLI theo tiêu chí nào và lỗi server nào vẫn phải tính. Không giấu timeout hoặc retry trong dashboard.

### Bước 2 — Cài synthetic read

Dùng `Neo4jReadHealth.check(driver, databaseName)` ở phần 5, có exception handling tại caller. Chạy một query `RETURN 1` theo chu kỳ an toàn và ghi trạng thái/latency. Nếu có canary node, thêm lookup theo khóa có constraint/index.

### Bước 3 — Kiểm tra database state

Khi môi trường cho phép:

~~~cypher
SHOW DATABASES
YIELD name, requestedStatus, currentStatus, statusMessage
RETURN name, requestedStatus, currentStatus, statusMessage;
~~~

So sánh trạng thái của DB nghiệp vụ với kết quả synthetic read. Ghi nhận “DB online nhưng synthetic read bị permission denied” là **lỗi truy cập/config**, không phải lý do phải restart.

### Bước 4 — Tạo dashboard ba nguồn

Hiển thị cùng time axis:

- **Application:** HTTP traffic, errors, latency p50/p95/p99 và driver pool.
- **Neo4j:** transactions, Bolt, page cache, heap/GC, query latency hoặc slow query khi hỗ trợ.
- **Host/container:** CPU, RAM, disk space/latency, restart/OOM, network.

Gắn annotation vào timeline khi deploy code, đổi index, thay plugin, restart cluster hoặc nhập dữ liệu lớn. Những thay đổi này có thể giải thích biến động metrics.

### Bước 5 — Kiểm tra sự cố có kiểm soát

Trong môi trường **lab**, chọn các tình huống không gây hư hỏng dữ liệu:

| Tình huống thử | Kết quả mong đợi |
| --- | --- |
| Đổi tạm URI thành endpoint giả lập không truy cập được | Synthetic connectivity fail, lỗi được phân loại |
| Dùng credential sai | Phân biệt authentication error với database offline |
| Chọn database name không tồn tại | DB unavailable/không tìm thấy DB, không tự tạo DB mới |
| Giới hạn concurrency của máy tạo tải | Dashboard thấy throughput, latency, pool pending |
| Chạy truy vấn traversal trên customer bậc cao | p95 tăng, có dữ liệu để chẩn đoán plan |
| Chạy import batch nhỏ | Quan sát write transaction rate, heap/CPU và disk |

Không thử **làm đầy disk**, **xóa transaction log**, **tắt đa số cluster** hoặc **đổi role production** để chứng minh alert.

### Bước 6 — Đề xuất alert

Thử tạo ba rule:

1. **Critical:** read hoặc write success rate xuống dưới SLO trong một cửa sổ phù hợp.
2. **Warning:** disk usage và tốc độ tăng cho thấy gần đạt ngưỡng trước thời gian xử lý dự kiến.
3. **Warning:** p95 tăng đồng thời pool pending hoặc GC pause tăng trong nhiều cửa sổ.

Mỗi alert cần đi kèm **người chịu trách nhiệm, mức độ ảnh hưởng, link dashboard, runbook và cách xác minh đã hồi phục**.

### Câu hỏi tự kiểm tra

**1. Neo4j process còn chạy có đủ để đánh dấu dịch vụ healthy?**

Không. Cần xác minh kết nối, database đích, quyền, route và thao tác nghiệp vụ theo yêu cầu.

**2. Vì sao không nên đặt một truy vấn traversal nặng làm liveness probe?**

Vì tải lớn/GC/network có thể khiến probe timeout tạm thời và orchestrator khởi động lại database đang hoạt động, làm tình trạng xấu hơn.

**3. `Driver.verifyConnectivity()` có thay thế `executeRead` trên database nghiệp vụ không?**

Không hoàn toàn. `verifyConnectivity` kiểm tra phần kết nối; synthetic transaction xác minh việc thực thi trên database đích và quyền cụ thể.

**4. Một secondary/follower đọc tốt nhưng ghi không được có nhất thiết là lỗi?**

Không. Điều đó có thể đúng theo vai trò trong topology. Kiểm tra write route của ứng dụng và trạng thái cluster trước khi kết luận có sự cố.

**5. Vì sao cần cả driver pool pending và server CPU?**

Vì nhiều request có thể bị kẹt ở pool phía ứng dụng trước khi server nhận query; CPU Neo4j thấp không phủ nhận lỗi latency.

**6. `PROFILE` có thay thế được đo p99 API không?**

Không. `PROFILE` giúp phân tích toán tử query nhưng không bao trùm HTTP, pool, routing, retry và thời gian trả response thực tế.

**7. Sau một đợt restart, chỉ cần `SHOW DATABASES` trả online là đủ đóng incident?**

Chưa đủ. Cần kiểm tra traffic, read/write synthetic, error rate, p95/p99, backlog và dữ liệu nghiệp vụ theo phạm vi incident.

## 16. Checklist vận hành

- [ ] Phân biệt **process, Bolt, database state và operation availability**.
- [ ] Chia rõ startup, liveness, readiness và synthetic probe; không restart liên tục khi startup/recovery hợp lệ.
- [ ] Chạy `Driver.verifyConnectivity()` và một phép `executeRead` nhẹ trên **đúng database** với role ứng dụng.
- [ ] Quan sát **write route** riêng khi dịch vụ có các transaction ghi quan trọng.
- [ ] Thu CPU, heap, GC, native memory, page cache, disk I/O/space và transaction log.
- [ ] Thu Bolt connections, driver pool pending, transaction count, retries, errors và timeout.
- [ ] Xác định vị trí lấy metrics theo **version/edition**: self-managed exporter hay Aura dashboards.
- [ ] Không công khai metrics endpoint, health diagnostics, URL/credential hoặc query parameter nhạy cảm.
- [ ] Đặt SLI/SLO theo **read và write operations**; tính cả request lỗi/timeout.
- [ ] Dùng cảnh báo theo **tác động và cửa sổ thời gian**, tránh báo động chỉ vì một giá trị CPU.
- [ ] Khi query chậm, kết hợp `EXPLAIN`/`PROFILE` với thông tin Rows/DB Hits và tải thực tế.
- [ ] Kiểm tra topology, writer/quorum và network khi cluster xuất hiện lỗi chỉ ở thao tác ghi.
- [ ] Thiết kế probe đủ nhẹ để monitoring không trở thành nguồn tải lớn.
- [ ] Có runbook cho TLS/auth, database offline, pool cạn, disk gần đầy, slow queries và cluster disruption.
- [ ] Diễn tập lỗi trong lab, đối soát sau recovery và lưu lịch sử deploy/config để điều tra.

## Tài liệu tham khảo

- [Neo4j Operations Manual — Monitoring](https://neo4j.com/docs/operations-manual/current/monitoring/)
- [Neo4j Operations Manual — Metrics](https://neo4j.com/docs/operations-manual/current/monitoring/metrics/)
- [Neo4j Operations Manual — Clustering](https://neo4j.com/docs/operations-manual/current/clustering/)
- [Neo4j Cypher Manual — Database administration](https://neo4j.com/docs/cypher-manual/current/database-administration/)
- [Neo4j Java Driver Manual — Connect to the database](https://neo4j.com/docs/java-manual/current/connect/)
- [Neo4j Java Driver Manual — Transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Spring Boot Actuator — Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Neo4j Aura Documentation](https://neo4j.com/docs/aura/)

**Kết luận:** Giám sát sức khỏe Neo4j không dừng ở việc xem tiến trình còn sống hoặc cổng Bolt 7687 đang mở. **Tính sẵn sàng** phải được xác nhận theo đúng database, quyền, kết nối bảo mật, đường đọc/ghi và khả năng hoàn tất truy vấn nghiệp vụ dưới tải. Kết hợp **synthetic probe, metrics hạ tầng/database/ứng dụng, SLI/SLO, cảnh báo có ngữ cảnh và runbook** giúp phát hiện đúng nút thắt, tránh khởi động lại nguy hiểm và phục hồi hệ thống graph một cách có kiểm soát.
