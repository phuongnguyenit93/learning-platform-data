# Load balancing, định tuyến theo token và locality

> **Chương:** Java driver cơ bản  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — Apache Cassandra, mô hình wide-column phân tán, thiết kế bảng theo khóa phân vùng và truy vấn, mức nhất quán đọc/ghi, CQL, replication, compaction, repair, xử lý sự cố và kết nối từ ứng dụng Java.

Một ứng dụng Java gửi `SELECT ... WHERE tenant_id = ?` vào Cassandra không nhất thiết đi thẳng đến node đang lưu partition ấy. **Java Driver chọn coordinator**, còn coordinator gửi yêu cầu đến các **replica** theo partition key, replication strategy và consistency level (CL). Nếu driver chọn coordinator không phải replica, request có thêm một bước chuyển tiếp internode. Nếu chọn coordinator ở datacenter (DC) xa, request còn phải chịu độ trễ WAN và rủi ro định tuyến nhầm vùng.

**Load balancing**, **token-aware routing** và **datacenter locality** phối hợp để giải bài toán đó, nhưng chúng không đồng nghĩa:

- **Load balancing:** chọn node nào sẽ làm coordinator, thứ tự ưu tiên và phương án dự phòng trong *query plan*.
- **Token-aware routing:** nếu biết partition key và replica placement, đưa **replica phù hợp** lên đầu query plan để giảm đường chuyển tiếp.
- **Locality:** giới hạn/ưu tiên node ở DC gần ứng dụng, tránh kéo lưu lượng CQL sang vùng xa không cần thiết.

Bài này sử dụng **Apache Cassandra Java Driver 4.x**, đặc biệt hành vi được mô tả trong tài liệu Driver **4.19**. Các phiên bản Driver 3.x có cơ chế cấu hình khác (ví dụ wrapper `TokenAwarePolicy` và `DCAwareRoundRobinPolicy`); **không sao chép mã Driver 3.x vào Driver 4.x**. Các ví dụ yêu cầu một cluster lab có topology đúng như mô tả; không có kết quả benchmark giả định được trình bày như số đo thực tế.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt **partition owner/replica**, **coordinator**, **contact point**, **local DC** và **driver query plan**.
2. Giải thích thuật toán chọn node khi có đủ hoặc thiếu routing key; dự đoán chi phí khi coordinator không là replica.
3. Cấu hình `DefaultLoadBalancingPolicy` và `local-datacenter`, hiểu các distance `LOCAL`, `REMOTE`, `IGNORED`.
4. Dùng `PreparedStatement`/`BoundStatement` để driver tự suy routing key từ **toàn bộ thành phần partition key**.
5. Hiểu vì sao `SimpleStatement` thường **không tự suy** routing metadata và cách kiểm tra/đặt thông tin định tuyến.
6. Quan sát coordinator thực tế bằng `ExecutionInfo` và tập replica dự kiến bằng `TokenMap` trong Java Driver 4.x.
7. Phân tích quan hệ giữa locality, CL như `LOCAL_QUORUM`, cross-DC failover, retry và speculative execution.
8. Viết lab và bảng metric để nhận diện sai local DC, mất token metadata, hot partition và phân bố tải lệch.

## 2. Dòng chảy một request từ Java đến các replica

### 2.1. Tách coordinator khỏi replica

Với bảng:

~~~sql
CREATE TABLE route_lab.events_by_tenant_day (
    tenant_id uuid,
    event_day date,
    event_time timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((tenant_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

**Partition key** là cặp `(tenant_id, event_day)`. Cassandra hash các byte của khóa phân vùng thành một **token**. Từ token, keyspace replication strategy và topology (DC/rack), metadata chỉ ra **những node làm replica** cho partition. `event_time` và `event_id` là clustering columns, ảnh hưởng thứ tự trong partition **nhưng không thay đổi token** khi `tenant_id` và `event_day` giữ nguyên.

~~~mermaid
flowchart TD
    A["Java: SELECT theo tenant_id + event_day"] --> B["Driver có routing key?"]
    B -->|Có| C["TokenMap tìm replicas theo keyspace, token, RF, DC"]
    B -->|Không| D["Ưu tiên node local theo query plan"]
    C --> E["Ưu tiên replica trong local DC"]
    D --> F["Coordinator local, có thể không là replica"]
    E --> G["Coordinator được chọn"]
    F --> G
    G --> H["Cassandra gửi đọc đến các replica cần thiết theo CL"]
    H --> I["Kết quả/tombstone merge và trả về Java"]
~~~

**Coordinator** có thể là replica hoặc node không lưu partition. Mọi node Cassandra thích hợp đều có thể làm coordinator cho nhiều CQL requests; replica là các node được giao giữ dữ liệu theo token/RF. Driver lựa chọn **coordinator**, không tự quyết định “replica nào đã trả ACK để thỏa CL”; việc đó thuộc coordinator và giao thức nhất quán của Cassandra.

### 2.2. Hai con đường cho cùng một partition

Giả sử trong DC cục bộ có bốn node A, B, C, D; keyspace RF=3 và token của partition K được sao chép tại A, B, C.

**Đường thuận lợi:** Driver biết K và đưa A/B/C lên đầu query plan; request tới A, A vừa làm coordinator vừa có thể đọc bản sao cục bộ và liên hệ B/C khi cần.

**Đường kém trực tiếp:** Driver không biết routing key nên chọn D; D làm coordinator, liên hệ A/B/C và trả dữ liệu cho client. Nó vẫn có thể đúng về consistency, nhưng phát sinh network hop/CPU coordinator bổ sung.

~~~text
Local DC: A, B, C, D     RF=3     replicas(K) = {A, B, C}

Token-aware:
  Java ---> A [coordinator + replica] ---> B/C theo CL

Không có routing metadata:
  Java ---> D [coordinator khác replica] ---> A/B/C

Không phải mọi lần A được chọn thì request chỉ chạm A.
Đạt LOCAL_QUORUM với RF=3 vẫn cần mức phản hồi/quy tắc CL của Cassandra.
~~~

Token-aware routing **không thay đổi consistency level**, không tạo thêm replica và không sửa hot partition. Nó tối ưu đường đưa CQL tới coordinator. Với RF bằng số node trong DC, ví dụ 3 node/RF=3, **mọi node local đều là replica**; một lab như vậy không chứng minh rõ khác biệt giữa token-aware và round-robin.

## 3. Load balancing policy trong Java Driver 4.x

### 3.1. Query plan là danh sách ưu tiên, không phải một node cố định

`LoadBalancingPolicy` xây một **query plan** mỗi khi thực thi request: danh sách những node driver ưu tiên thử, theo thứ tự. Nó quyết định:

1. Những node nào cần giữ kết nối.
2. Node nào ưu tiên làm coordinator cho statement.
3. Khi có lỗi, retry hoặc speculative execution, node nào là ứng viên tiếp theo theo chính sách tương ứng.

| Khái niệm | Vai trò | Hiểu lầm hay gặp |
|---|---|---|
| **Contact points** | Địa chỉ bootstrap để driver kết nối ban đầu, lấy topology/schema metadata | “Driver chỉ gửi CQL đến contact points” — sai sau khi khám phá cluster |
| **Node distance** | Kết quả phân loại node để quản lý kết nối: `LOCAL` / `REMOTE` / `IGNORED` | Không đồng nghĩa khoảng cách địa lý tính bằng km |
| **Query plan** | Thứ tự coordinator ứng viên cho **từng query** | Không phải danh sách bản sao chắc chắn trả kết quả |
| **Token-aware** | Ưu tiên replica cho keyspace + partition key biết trước | Không phải sharding ở phía Java |
| **Slow replica avoidance** | Cơ chế tránh replica bị đánh giá chậm trong default policy | Không thay thế monitoring hoặc khắc phục node yếu |
| **Retry policy** | Quyết định có thử lại/tiếp tục khi gặp lỗi tương ứng | Không mặc định được phép retry mọi loại ghi |
| **Speculative execution** | Có thể gửi bản thực thi bổ sung theo cấu hình cho request thích hợp | Không tạo thêm replica hoặc giải quyết CL sai |

Trong Java Driver 4.x, `DefaultLoadBalancingPolicy` là **chính sách mặc định và thường nên giữ**. Nó tích hợp token awareness và có cơ chế tránh slow replica theo hành vi/phiên bản. Không cần bọc thủ công `TokenAwarePolicy` quanh `DCAwareRoundRobinPolicy` như một số ví dụ Driver 3.x.

### 3.2. Distance LOCAL, REMOTE, IGNORED

- **`LOCAL`:** driver giữ kết nối và có thể ưu tiên node này trong query plans. Với policy mặc định và local DC được chọn, thường là các node phù hợp thuộc DC đó.
- **`IGNORED`:** driver không chủ động kết nối với node cho các request thuộc policy; remote DC thường bị bỏ qua theo mặc định.
- **`REMOTE`:** chỉ xuất hiện khi chính sách hoặc cơ chế failover được cấu hình cho phép dùng node ngoài DC local; có thể có pool/chi phí khác.

Mặc định, policy tích hợp Java Driver 4.x hướng lưu lượng vào **một DC cục bộ**. Kể cả hai DC có RF đầy đủ, driver không tự chọn remote replicas chỉ vì chúng lưu cùng partition. Đó là quyết định chủ đích nhằm tránh WAN traffic. Chi tiết thay đổi trong các phiên bản Driver 4.x: tính năng driver-level cross-DC failover được bổ sung lại từ **Driver 4.10** nhưng **tắt mặc định**.

### 3.3. Hành vi khi thiếu/đủ routing metadata

Theo hướng dẫn Java Driver 4.19:

| Thông tin của statement | Query plan mặc định |
|---|---|
| Không biết keyspace hoặc routing key | Chọn luân phiên/trộn các node kết nối được ở local DC, không đảm bảo coordinator là replica |
| Có routing keyspace + routing key và TokenMap dùng được | Đưa **các local replicas của partition** lên trước (có hoán đổi để cân tải), sau đó mới đến local non-replicas |
| Một local replica Down/chậm | Các replica/local nodes khác có thể được dùng theo query plan, retry và slow avoidance |
| Tất cả local nodes không khả dụng, failover chưa bật | Driver không tự chuyển request sang DC khác |
| Cross-DC failover đã được bật | Một số remote nodes có thể ở **sau local nodes** theo cấu hình và ràng buộc CL |

Đừng kỳ vọng mỗi request của một partition luôn đi vào **cùng một replica**. Driver có thể thay đổi thứ tự để phân bố coordinator giữa các replica; lỗi, latency, metadata chưa cập nhật, speculative execution và retry cũng ảnh hưởng node cuối cùng trả kết quả.

## 4. Datacenter locality: ứng dụng nên kết nối vùng nào?

### 4.1. local-datacenter là một quyết định triển khai

Nếu ứng dụng Java đặt tại **vùng 1** và Cassandra có `dc1` ở vùng 1, `dc2` ở vùng 2, nên đặt local DC của session là `dc1`. Một phiên Java khác chạy ở vùng 2 nên có local DC là `dc2`, với điều kiện keyspace có RF và dữ liệu đầy đủ tại DC đó.

~~~mermaid
flowchart LR
    subgraph R1["Region 1"]
      A1["Java app: local-dc = dc1"] --> D1["Cassandra dc1"]
    end
    subgraph R2["Region 2"]
      A2["Java app: local-dc = dc2"] --> D2["Cassandra dc2"]
    end
    D1 -. "Replication / internode WAN" .- D2
~~~

**Local DC của driver là ưu tiên định tuyến coordinator**, còn keyspace RF quyết định DC nào thật sự có replica. Bạn có thể cấu hình `local-datacenter = dc2` nhưng keyspace chỉ có RF ở `dc1` — khi đó chọn coordinator ở dc2 **không giúp dữ liệu có bản sao cục bộ**. Hãy kiểm tra schema replication và topology.

### 4.2. Cấu hình HOCON cơ bản

Ví dụ `application.conf` cho Java Driver 4.x:

~~~hocon
datastax-java-driver {
  basic.contact-points = [
    "db1.dc1.internal.example:9042",
    "db2.dc1.internal.example:9042"
  ]

  basic.load-balancing-policy {
    class = DefaultLoadBalancingPolicy
    local-datacenter = dc1
  }

  advanced.metadata {
    schema.enabled = true
    token-map.enabled = true
  }
}
~~~

Các hostname chỉ là mẫu; phải là endpoint DNS/IP của cluster thực và được phép kết nối. Bổ sung TLS truststore, credentials và secret injection **ngoài ví dụ** nếu cluster yêu cầu. Không để username/password, token, private key plaintext trong file source.

Giải thích từng trường:

- `basic.contact-points` chỉ định các endpoint ban đầu; chúng **không** khóa request vào hai node đó.
- `basic.load-balancing-policy.class` chọn policy. Có thể bỏ nếu giữ default.
- `local-datacenter` chọn DC logic dựa trên metadata node; **phải khớp chính xác tên DC** do cluster báo cáo, ví dụ `dc1` khác `DC1`.
- `advanced.metadata.schema.enabled` và `token-map.enabled` bật metadata cần để tính replica theo keyspace; các giá trị thường đã bật mặc định, ở đây khai báo để người học thấy phụ thuộc.

Với application production dùng contact points cụ thể, nên **khai báo local DC tường minh**. Policy `DcInferringLoadBalancingPolicy` có thể suy DC từ contact points và chủ yếu phục vụ công cụ ETL. Không nên cố ý bỏ local DC để “load balance đều hai vùng”: làm vậy có thể tăng WAN traffic và độ trễ.

### 4.3. Tạo session bằng Java

Nếu không dùng HOCON, có thể cấu hình programmatically:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import java.net.InetSocketAddress;

try (CqlSession session = CqlSession.builder()
        .addContactPoint(new InetSocketAddress("db1.dc1.internal.example", 9042))
        .addContactPoint(new InetSocketAddress("db2.dc1.internal.example", 9042))
        .withLocalDatacenter("dc1")
        // Cấu hình auth/TLS từ secure config của môi trường triển khai.
        .build()) {

    session.execute("SELECT release_version FROM system.local");
}
~~~

**Một session dài hạn cho ứng dụng** thường tốt hơn tạo một session cho từng request: driver quản lý pool, metadata, prepared statement cache, heartbeat và topology trên session. Ví dụ `try-with-resources` chỉ minh họa lifecycle cho một chương trình độc lập; trong web service, khởi tạo ở startup và đóng khi shutdown.

Nếu khai báo local DC cả trong code lẫn HOCON, giá trị **programmatic được ưu tiên** theo Driver 4.x. Khi một deployment vẫn gửi request sang vùng khác, kiểm tra **cả hai nguồn config**, không chỉ file HOCON.

## 5. Token-aware routing cần những dữ liệu nào?

### 5.1. Điều kiện đồng thời

Driver chỉ suy được replica phù hợp khi có:

1. **Keyspace** mà statement thuộc về, để lấy replication strategy/RF. Cùng token có thể có replica khác nhau ở hai keyspace.
2. **Routing key** — byte representation của **toàn bộ partition key** theo CQL types/codec và đúng thứ tự thành phần.
3. **Token map và schema metadata** đủ mới, có partitioner, ring token và thông tin replicas theo keyspace.
4. **Load balancing policy** hỗ trợ token awareness và các local replicas đang eligible/connected.

~~~text
partition key: (tenant_id UUID, event_day DATE)
      |
      v  CQL type encoding + composite key encoding
routing key (byte buffer)
      |
      v  partitioner, ví dụ Murmur3Partitioner
token (số)
      |
      v  token map + replication strategy + DC/rack
replicas cho keyspace route_lab
      |
      v  filter local/eligible + query-plan policy
candidate coordinator ưu tiên
~~~

**Không tự hash UUID sang token trong ứng dụng bằng một hàm tùy tiện.** Với partition key nhiều thành phần, byte encoding có quy tắc riêng. Thường nên **để prepared statement và Driver làm việc đó**. Token map phản ánh topology/schema mà driver đã học được; khi vừa thay RF, bootstrap, decommission hoặc schema, metadata có thể cập nhật sau một khoảng ngắn.

### 5.2. BoundStatement: cách dễ nhất để có routing key

Giả sử bảng có:

~~~sql
PRIMARY KEY ((tenant_id, event_day), event_time, event_id)
~~~

Một prepared query:

~~~java
PreparedStatement prepared = session.prepare(
    "SELECT event_time, event_id, payload " +
    "FROM route_lab.events_by_tenant_day " +
    "WHERE tenant_id = ? AND event_day = ? " +
    "AND event_time >= ? AND event_time < ? LIMIT ?");

BoundStatement bound = prepared.bind(
    tenantId, eventDay, from, until, 50);
~~~

Driver biết `tenant_id` và `event_day` là **các biến thuộc partition key** từ metadata PREPARED. Khi cả hai được bind với giá trị hợp lệ, driver có thể suy `routing keyspace` và `routing key` tự động. Các tham số `from`/`until` trong điều kiện clustering **không** góp phần tính token.

**Điểm tinh tế trong tài liệu Driver:** ngay cả một câu truy vấn cố định đầy đủ partition key ở dạng:

~~~java
PreparedStatement onlySomeBound = session.prepare(
    "SELECT * FROM route_lab.events_by_tenant_day " +
    "WHERE tenant_id = 11111111-1111-4111-8111-111111111111 " +
    "AND event_day = ?");
~~~

vẫn có thể **không** tự tính routing key do `tenant_id` được hard-code thay vì bind. Theo Driver 4.x, routing key chỉ tự suy khi **mọi thành phần partition key đều được bind thành variables**. Cố định bằng literal trong SQL không tương đương prepared routing metadata đầy đủ.

### 5.3. SimpleStatement: không tự suy key chỉ từ CQL string

Khi gọi:

~~~java
SimpleStatement simple = SimpleStatement.newInstance(
    "SELECT * FROM route_lab.events_by_tenant_day " +
    "WHERE tenant_id = 11111111-1111-4111-8111-111111111111 " +
    "AND event_day = '2026-11-21'");
~~~

Driver **không parse tùy ý câu CQL simple để tự tính routing key**. Kể cả text có cả hai thành phần partition key, `simple.getRoutingKey()` mặc định vẫn là `null`. Khi đó query plan thường ưu tiên các node local theo round-robin, không được bảo đảm token-aware.

Bạn có thể cung cấp thủ công `routing keyspace` và `routing key` (hoặc routing token) đã mã hóa đúng, nhưng việc đóng gói composite key **phải dùng API/codec của Driver**, không nối chuỗi UUID + date rồi hash thủ công. Trong đa số nghiệp vụ, **PreparedStatement với các partition components được bind** rõ ràng hơn, giảm lỗi CQL injection và tiết kiệm parsing ở server.

### 5.4. Những trường hợp routing key không có hoặc sai

| Pattern | Driver có routing key tự động? | Nguyên nhân |
|---|---|---|
| `SELECT ... WHERE tenant_id = ? AND event_day = ?` trong prepared query | Thường **có** | Cả hai partition key components là bound variables |
| Prepared query chỉ bind `event_day`, còn `tenant_id` viết literal | Thường **không** | Thiếu metadata biến cho một partition key component |
| `SimpleStatement.newInstance("SELECT ...")` với đủ literal key | **Không tự suy** | Driver không parse simple text để tính |
| Prepared query đọc theo **index** mà không khóa partition | Thường không xác định một partition cụ thể | Query có thể chạm nhiều token ranges |
| Query `IN` trên nhiều partition keys | Không mặc định có một routing key duy nhất | Một request nhắm nhiều partition; cần thiết kế riêng |
| `BatchStatement` nhiều partition | Không thể coi batch là một partition routing đơn giản | Driver có thể lấy routing metadata từ child; **không** biến cross-partition batch thành tối ưu |
| Schema/token map bị tắt | Không có dữ liệu tính replicas | Policy phải chọn fallback mà không biết ownership |

**Cảnh báo:** Có routing key đúng không làm một truy vấn xấu trở nên rẻ. Ví dụ partition cực lớn, rất nhiều tombstone hoặc `ALLOW FILTERING` vẫn có thể tạo p99 cao dù request đi đến local replica.

## 6. CQL partition key, RF và locality liên hệ ra sao?

### 6.1. Partition key quyết định locality của dữ liệu

Trong `NetworkTopologyStrategy`, RF được khai báo **theo DC**:

~~~sql
CREATE KEYSPACE route_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3,
    'dc2': 3
}
AND durable_writes = true;
~~~

Schema này chỉ hợp lệ để **thực sự đạt RF mục tiêu** khi mỗi DC có đủ node/rack theo topology. Nếu DC chỉ có hai node mà khai RF=3, cấu hình không tạo ra node thứ ba. Khi xét routing, cần đọc:

- Node nào **thực sự** có mặt và đang Up/Normal.
- Danh sách replica của partition K theo **keyspace cụ thể**.
- RF ở DC của application và DC phụ.
- CL của query: `LOCAL_ONE`, `LOCAL_QUORUM`, `EACH_QUORUM` v.v., với semantics riêng.

**Locality của client** không có nghĩa mọi request chỉ cần một replica local để phục vụ. Với `LOCAL_QUORUM` và RF=3 ở DC local, coordinator cần mức xác nhận/quy tắc quorom tương ứng trong DC ấy. Chọn coordinator là local replica có thể giảm hop, **không thay đổi điều kiện đạt CL**.

### 6.2. Ba tình huống cùng query nhưng khác topology

| Topology | Routing ưu tiên | Cần lưu ý |
|---|---|---|
| `dc1` 4 node/RF=3, app ở `dc1` | 3 local replicas của partition | Có thể giảm hop so với node local thứ tư |
| `dc1` 3 node/RF=3, app ở `dc1` | Cả 3 node đều replica | Test dễ không thấy lợi ích token-awareness |
| App ở `dc2` nhưng keyspace chỉ RF tại `dc1` | Có thể chọn coordinator `dc2` theo local policy, nhưng dữ liệu ở `dc1` | “Local coordinator” **không** biến dữ liệu thành local; xem lại replication/data placement |

Muốn xây một hệ thống đa vùng ít WAN traffic, phải kết hợp **placement của ứng dụng**, **local-datacenter của driver** và **RF của keyspace**. Chỉ sửa một trong ba mà không kiểm chứng hai phần còn lại sẽ không đảm bảo locality.

### 6.3. Contact points không phải danh sách replica

Một service có thể bootstrap bằng node A nhưng sau khi load metadata, driver mở connections tới các node local khác theo policy. Nếu A tạm ngừng, các kết nối đã có vẫn có thể phục vụ request trên node B/C/D. Không cần liệt kê **mọi node** làm contact point; nên có nhiều contact points ổn định trong DC thích hợp để tăng xác suất khởi động.

**Đừng dùng load balancer TCP chung che nhiều node** mà không kiểm tra mô hình address discovery/NAT: Cassandra Driver thường muốn biết/tiếp cận được các địa chỉ **advertised** của từng node sau bootstrap. Trong Kubernetes, cloud hoặc NAT phải đảm bảo address resolver/transport được cấu hình phù hợp. Đây là lỗi infrastructure dễ bị nhầm với “token-aware không hoạt động”.

## 7. Java Driver: kiểm tra routing key, replicas và coordinator

### 7.1. Ví dụ Java Driver 4.x có đủ metadata

Đoạn sau giả định:

- Đã tạo một `CqlSession session` nối cluster lab, local DC đúng.
- Keyspace `route_lab` và bảng `events_by_tenant_day` tồn tại.
- Token map/schema metadata được bật.
- Các dữ liệu mẫu có partition key `(tenant_id, event_day)`.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.ExecutionInfo;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.metadata.Node;
import com.datastax.oss.driver.api.core.metadata.TokenMap;
import java.time.Instant;
import java.time.LocalDate;
import java.util.Set;
import java.util.UUID;

void inspectRouting(CqlSession session,
                    UUID tenantId, LocalDate day,
                    Instant from, Instant until) {
    PreparedStatement prepared = session.prepare(
        "SELECT event_time, event_id, payload " +
        "FROM route_lab.events_by_tenant_day " +
        "WHERE tenant_id = ? AND event_day = ? " +
        "AND event_time >= ? AND event_time < ? LIMIT ?");

    BoundStatement request = prepared.bind(
            tenantId, day, from, until, 100)
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .setPageSize(50);

    System.out.println("Routing keyspace = " + request.getRoutingKeyspace());
    System.out.println("Routing key available = " +
        (request.getRoutingKey() != null));

    if (request.getRoutingKey() != null) {
        session.getMetadata().getTokenMap().ifPresent(tokenMap -> {
            Set<Node> expectedReplicas = tokenMap.getReplicas(
                "route_lab", request.getRoutingKey());
            for (Node replica : expectedReplicas) {
                System.out.println("Replica: " + replica.getEndPoint()
                    + ", DC=" + replica.getDatacenter());
            }
        });
    }

    ResultSet rows = session.execute(request);
    ExecutionInfo info = rows.getExecutionInfo();
    Node coordinator = info.getCoordinator();
    System.out.println("Coordinator: " +
        (coordinator == null ? "(unknown)" : coordinator.getEndPoint()));
    System.out.println("Speculative executions started: " +
        info.getSpeculativeExecutionCount());

    rows.forEach(row -> row.getUuid("event_id"));
}
~~~

**Giải thích những điều code có và không chứng minh:**

1. `getRoutingKey() != null` xác nhận Driver đã biết **routing bytes** của statement, không chứng minh chính sách chắc chắn chọn replica. Cần xem coordinator và query plan/metadata.
2. `TokenMap.getReplicas("route_lab", routingKey)` trả **replicas dự kiến theo metadata của driver**, có thể gồm các node ở nhiều DC, bất kể trạng thái kết nối. Nó **không** chứng minh dữ liệu của mọi node đã đồng bộ hay node đó nhận request lần này.
3. `ExecutionInfo.getCoordinator()` phản ánh node làm coordinator cho **lần thực thi có kết quả**; nó không cho biết toàn bộ các replica đã tham gia phục vụ CL. `ResultSet.getExecutionInfo()` đại diện thông tin thực thi hiện có tại thời điểm truy cập; với paging, các trang sau có thể có execution info riêng.
4. Nếu code luôn in một node, đừng vội kết luận policy bị lỗi: một số replica có thể Down/slow/ignored, tải chưa đủ mẫu, cluster chỉ có một eligible node, hoặc mọi request dùng chung routing partition nhưng chỗ chạy ít biến.

Không cần tự gọi `setRoutingKey(...)` cho prepared query đủ bind. Gọi manual với composite key sai có thể làm routing xấu hoặc dẫn đến quan sát replica sai. Việc quản lý query plan và retry nên để policy tích hợp xử lý trừ khi có nhu cầu được kiểm thử rõ.

### 7.2. Tại sao không đọc một metadata snapshot mãi mãi?

Driver metadata thay đổi khi cluster bootstrap/decommission, node Up/Down, đổi RF/schema hoặc topology; `session.getMetadata()` trả snapshot bất biến tại thời điểm gọi. **Không cache metadata snapshot vô hạn** rồi dùng nó đánh giá replica trong khi cluster thay đổi. Gọi lại khi cần kiểm chứng và theo dõi node events/schema agreement.

Trong những đợt sửa topology, `TokenMap` có thể tạm thời **không khớp** với view của một node chưa cập nhật. Đây là lý do đo routing ở nhiều thời điểm sau khi schema/token metadata đã ổn định, thay vì dựa vào một mẫu ngay khi bootstrap.

### 7.3. Quan sát kiểu query khác: SimpleStatement

~~~java
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

SimpleStatement statement = SimpleStatement.newInstance(
    "SELECT event_time, event_id FROM route_lab.events_by_tenant_day " +
    "WHERE tenant_id = 11111111-1111-4111-8111-111111111111 " +
    "AND event_day = '2026-11-21'");

System.out.println("Routing keyspace: " + statement.getRoutingKeyspace());
System.out.println("Routing key: " + statement.getRoutingKey());

// Có thể chỉ cung cấp keyspace:
statement = statement.setRoutingKeyspace("route_lab");
// Chỉ set keyspace vẫn CHƯA đủ để token-aware chọn replicas nếu thiếu routing key.
~~~

Nhớ rằng statements của Driver 4.x **bất biến (immutable)**: phương thức `setRoutingKeyspace` trả một instance mới; nếu quên gán lại, statement cũ không đổi. Không lấy lệnh này làm bài hướng dẫn để chạy trên production: đây là **phép quan sát metadata**, còn code dùng prepared query để định tuyến tự động.

## 8. Cross-datacenter failover và tính nhất quán

### 8.1. Mặc định không tự failover qua DC

Theo tài liệu Java Driver 4.19, mặc định `DefaultLoadBalancingPolicy` kết nối tới **local DC** và các node remote bị bỏ qua. Nếu toàn bộ local DC lỗi, driver **không tự động** chuyển sang DC khác.

Điều này hợp lý trong kiến trúc ứng dụng đa vùng: thường application đặt gần Cassandra cùng vùng; nếu cả vùng lỗi, **application/load balancer cấp hạ tầng** cũng cần failover sang vùng khác, nơi có application instance và Cassandra replica sẵn sàng. Dùng driver-level failover phải chủ động vì có thể tạo WAN traffic/latency và thay đổi semantics CL.

### 8.2. Tùy chọn failover của Driver 4.10+

**Chỉ minh họa cho lab đã hiểu topology và CL**, không bật theo mặc định cho production:

~~~hocon
datastax-java-driver {
  basic.load-balancing-policy.local-datacenter = dc1

  advanced.load-balancing-policy.dc-failover {
    max-nodes-per-remote-dc = 2
    # Mặc định KHÔNG failover LOCAL_ONE/LOCAL_QUORUM/LOCAL_SERIAL.
    allow-for-local-consistency-levels = false
  }
}
~~~

Với `max-nodes-per-remote-dc = 0` (mặc định), remote failover bị tắt. Giá trị lớn hơn 0 khiến một số remote nodes có kết nối và có thể xuất hiện **sau local nodes** trong query plan khi policy quyết định. Điều này **không** chuyển keyspace replication tự động và **không** đảm bảo tất cả queries sẽ hoạt động nếu RF/CL sai.

### 8.3. Vì sao không bật failover cho LOCAL_QUORUM một cách máy móc?

Giả sử keyspace có:

~~~sql
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3,
    'dc2': 1
}
~~~

Đối với `LOCAL_QUORUM`, số replica cần phản hồi phụ thuộc **DC của coordinator** và RF tại DC ấy. Nếu coordinator chuyển từ `dc1` (RF=3) sang `dc2` (RF=1), quorum local của mỗi DC **khác nhau**. Vì vậy Driver 4.x **mặc định không cho failover remote** với các local consistency levels.

Có lựa chọn `allow-for-local-consistency-levels = true` cho chuyên gia đã chấp nhận semantics/rủi ro, nhưng **không dùng làm cách sửa nhanh một DC bị lỗi**. Trước tiên cần kế hoạch DR, RF theo DC, chính sách stale reads, data reconciliation, kiểm thử lỗi mạng và năng lực tải ở vùng dự phòng.

### 8.4. Failover không có nghĩa luôn dữ liệu mới nhất

Ngay cả khi remote coordinator nhận query, Cassandra vẫn tuân theo CL/RF, timestamp conflict và trạng thái replication. Nếu remote DC chưa có bản sao đầy đủ hoặc partition bị lệch vì sự cố, việc route request thành công qua TLS không bảo đảm business-level freshness. Thiết kế sản phẩm phải mô tả rõ **RPO, RTO, read/write consistency và sự lệch chấp nhận được**.

## 9. Retry, speculative execution, idempotence và locality

### 9.1. Query plan không phải lịch sử thực thi

Khi statement có replicas ưu tiên [A, B, C] rồi local non-replica D:

- Request bình thường có thể thành công tại A; B/C/D không nhận request trực tiếp từ driver.
- Nếu A không sẵn sàng, retry policy có thể cho phép thử tiếp node khác trong query plan.
- Nếu speculative execution được bật và query đủ điều kiện, driver có thể khởi chạy bản thực thi bổ sung tới coordinator khác trước khi lần đầu trả kết quả.
- Cassandra coordinator vẫn giao tiếp replicas theo CL; số **driver executions** không bằng số **replica messages**.

**Không ép mọi request “idempotent=true” để bật retry/speculative**. LWT, counter updates hoặc thao tác không idempotent có thể bị thực hiện lặp ngoài ý muốn. Chỉ đánh dấu khi ngữ nghĩa câu lệnh thực sự an toàn và team đã xem retry/speculation policy.

### 9.2. Hot partition: token-aware có thể gom tải

Giả sử 80% request cùng partition K; RF=3 tại A/B/C. Token-aware khiến request ưu tiên ba replica đó. Đây là đúng theo mục tiêu tránh hop nhưng cũng có thể làm A/B/C chịu tải nhiều hơn D, vì D không giữ K. Không phải lỗi “load balancing không đều”.

| Phương án | Tác động | Giới hạn |
|---|---|---|
| Giữ token-aware, sửa partition key/bucket | Phân tán dữ liệu và request sang nhiều token/ranges | Cần đổi schema/query model, có thể tăng fan-out |
| Giảm hot read bằng cache phù hợp | Giảm pressure vào replica cho một số access pattern | Cache không giải quyết hot writes hoặc RF không đủ |
| Điều tiết client concurrency | Bảo vệ p99/timeout dưới tải đỉnh | Không tăng năng lực xử lý dài hạn |
| Tăng node + cân đối token | Tăng tổng capacity cluster | Partition K vẫn chỉ nằm ở số replica do RF quyết định |
| Chọn coordinator non-replica để “chia tải” | Có thể chuyển một phần CPU coordinator sang node D | Thường tăng network hop và vẫn đụng replicas A/B/C; không phải giải pháp gốc |

Tách **load balancing coordinator** khỏi **load balancing dữ liệu**. Dữ liệu phân tán theo partition key/RF; driver không di chuyển partition sang node rảnh khi gọi query.

## 10. Lab CQL + Java: đo routing thật thay vì suy từ giả định

### 10.1. Chuẩn bị topology phân biệt được replica và non-replica

Lab lý tưởng có **ít nhất bốn node trong cùng `dc1`, RF=3**; khi đó một partition thường có ba local replicas và ít nhất một node không giữ partition. Có thể thêm `dc2` nếu muốn thử locality. Trên cluster ít node hơn, bài thực hành vẫn chạy được nhưng sự khác biệt về coordinator có/không là replica có thể không thể quan sát rõ.

~~~bash
nodetool status
nodetool describecluster
nodetool version
~~~

**Cẩn trọng:** tên DC trong ví dụ phải đúng metadata thực; các hostnames là mẫu. Không tạo keyspace RF=3 trong cluster chỉ có một node rồi coi CL=LOCAL_QUORUM sẽ hoạt động. Dùng môi trường riêng, không làm thí nghiệm failover trên production.

### 10.2. Tạo bảng và dữ liệu mẫu

Trong `cqlsh` của **cluster lab**, khi `dc1` thực sự có bốn node:

~~~sql
CREATE KEYSPACE IF NOT EXISTS route_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS route_lab.events_by_tenant_day (
    tenant_id uuid,
    event_day date,
    event_time timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((tenant_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

INSERT INTO route_lab.events_by_tenant_day
    (tenant_id, event_day, event_time, event_id, payload)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21',
    '2026-11-21T08:15:00Z',
    22222222-2222-4222-8222-222222222222,
    'temperature=21'
);

SELECT event_time, event_id, payload
FROM route_lab.events_by_tenant_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21';
~~~

`IF NOT EXISTS` sẽ **không sửa** keyspace/table đã có nhưng khác RF/schema. Nếu chạy lại lab, kiểm tra `DESCRIBE KEYSPACE route_lab` và `DESCRIBE TABLE route_lab.events_by_tenant_day`. Dữ liệu một row chỉ kiểm tra câu lệnh; đo tải thật cần nhiều partition keys và nhiều lần lặp.

### 10.3. Kiểm tra replicas từ metadata phía node

Với **composite partition key**, `nodetool getendpoints` có yêu cầu biểu diễn khóa/serialization tùy phiên bản và kiểu CQL; không tự ghép UUID và date thành một string rồi coi đã tính đúng token. Để xác định replica của khóa mẫu, ưu tiên:

1. `TokenMap.getReplicas(keyspace, BoundStatement.getRoutingKey())` trong Java.
2. Metadata topology và `nodetool status` trên node.
3. Chỉ dùng `nodetool getendpoints` khi đã xác nhận cú pháp và cách biểu diễn partition key composite của release đang chạy.

Nếu đối chiếu DC/rack từ nhiều node, chú ý trạng thái node, token ring và RF sau một phiên bootstrap/repair. **Replica placement theo metadata** không chứng minh đồng bộ giá trị 100% giữa các replicas.

### 10.4. Chạy ba biến thể điều kiện

| Biến thể | Input/statement | Dự đoán trước khi đo |
|---|---|---|
| **A — prepared/bound** | Bind cả `tenant_id` và `event_day` | `getRoutingKey()!=null`; local replicas được ưu tiên |
| **B — simple literal** | Text chứa cùng hai partition keys nhưng không gắn routing key | Không tự có routing key; coordinator có thể là non-replica |
| **C — bound với metadata token-map tắt** | Giữ prepared query, tắt token map trên **session lab riêng** | Có thể vẫn có routing key ở statement nhưng policy không có token map để tìm replicas |

Ví dụ HOCON của **biến thể C**, không dùng trong production nếu cần token awareness:

~~~hocon
datastax-java-driver {
  basic.load-balancing-policy.local-datacenter = dc1
  advanced.metadata.schema.enabled = true
  advanced.metadata.token-map.enabled = false
}
~~~

**Điều quan trọng:** biến thể C không chứng minh driver “sai partition key”; nó cô lập vai trò của TokenMap. Nếu tắt schema metadata, token map cũng mất khả năng dựa vào replication strategy để tìm replicas. Đừng dùng CQL latency của một request duy nhất để kết luận chính sách nào tốt hơn.

### 10.5. Chạy nhiều partition và ghi coordinator

Để tính tỷ lệ coordinator là local replica, với **mỗi request**:

~~~text
known = bound.getRoutingKey() != null && tokenMap is present
expected_replicas = tokenMap.getReplicas("route_lab", bound.getRoutingKey())
coordinator = resultSet.getExecutionInfo().getCoordinator()

if known && coordinator != null:
    coordinator_is_replica = expected_replicas.contains(coordinator)
    coordinator_dc = coordinator.getDatacenter()
    local_replica = coordinator_is_replica && coordinator_dc == "dc1"
~~~

Thống kê trên **nhiều tenant_id khác nhau và nhiều lần lặp**, ví dụ 1.000 partitions × 10 requests khi cluster lab đủ tài nguyên. Không đưa raw tenant identifiers nhạy cảm vào log; có thể nhóm theo hash/anonymized labels.

Đo đồng thời:

- Tỷ lệ **coordinator thuộc local replicas** trên các request có routing key.
- Phân bố coordinator theo node và theo DC.
- p50/p95/p99 end-to-end và local read latency.
- Network bytes/packets internode, CPU coordinator và replica.
- Retry count, speculative execution count, timeout/reconnection.
- Số node Up/Down, độ mới metadata và SSTables/tombstone/hot partitions.

**Lý do cần nhiều node:** nếu RF=3 mà local DC chỉ có đúng 3 node, tỷ lệ “coordinator là replica” đạt 100% **cho cả variant B**; một kết quả như vậy không chứng minh token awareness tốt hay xấu.

### 10.6. Bảng kết quả — chỉ điền số đo từ cluster

| Biến thể | Tỷ lệ có routing key | % coordinator là local replica | Coordinator entropy/distribution | p99 đọc (ms) | Bytes internode/request | Errors/retries |
|---|---|---|---|---|---|---|
| A: prepared + TokenMap | _điền_ | _điền_ | _điền_ | _điền_ | _điền_ | _điền_ |
| B: simple literal | _điền_ | _điền_ | _điền_ | _điền_ | _điền_ | _điền_ |
| C: prepared, tắt TokenMap | _điền_ | _điền_ | _điền_ | _điền_ | _điền_ | _điền_ |

Lặp thử nghiệm nhiều lần, thay đổi thứ tự A/B/C, giữ cùng partitions, CL, payload, query count, warm-up, page size và concurrency. Bảng không kèm số **giả định** để tránh biến ví dụ thành bằng chứng không được đo.

## 11. Quan sát và xử lý sự cố routing

### 11.1. Checklist chẩn đoán khi p99 tăng hoặc traffic sai DC

1. **Đọc cấu hình driver thực:** phiên bản, local-datacenter, policy, có profile riêng không, connection point và address resolution.
2. **Đối chiếu topology:** `nodetool status`, DC/rack và keyspace RF thật; không dựa vào tên DC trong một file config mẫu.
3. **Kiểm tra routing metadata:** Simple hay BoundStatement? Đã bind đủ partition key components chưa? `getRoutingKey()` có null không?
4. **Kiểm tra TokenMap:** schema/token-map có bật không, keyspace có trong metadata không, topology vừa thay đổi có được cập nhật chưa?
5. **Xem coordinator thật:** `ExecutionInfo.getCoordinator()` theo node/DC; có retries/speculative executions hoặc node bị đánh giá chậm không?
6. **So CL/replicas:** LOCAL_QUORUM có đủ RF trong local DC không? Replica có Down, đang bootstrap hoặc dữ liệu lệch không?
7. **Kiểm tra hot keys và query model:** partition key skew, large partitions, tombstone, compaction/repair backlog.
8. **Kiểm tra network/JVM:** DNS, TLS/SAN, firewall, native port, GC, pool saturation, event loop backlog, RTT vùng xa.

### 11.2. Dấu hiệu và nguyên nhân hay gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm chứng |
|---|---|---|
| BoundStatement vẫn không token-aware | Không bind đủ partition components, routing key null | In `getRoutingKeyspace()/getRoutingKey()` và CQL prepared |
| Routing key có nhưng coordinator không là replica | TokenMap tắt/cũ, replicas Down/slow, policy/failover hoặc retry | So `getReplicas`, coordinator và topology |
| App ở `dc1` nhưng truy vấn qua `dc2` | Local DC sai, profile khác, remote failover mở, app placement đổi | Đọc config runtime và coordinator DC |
| Query latency WAN cao | App không colocate DC, keyspace RF chỉ tại remote DC | So local DC, replication và packet latency |
| Các contact points trong config đều ổn nhưng app không tới node khác | Advertised addresses không reach được, firewall/TLS/DNS | Kiểm tra driver discovery logs và native connections |
| Load không đều giữa node | Hot partition, replicas cụ thể của keys, slow avoidance hoặc down node | Histogram token/keys, coordinator/replica load |
| Tắt TokenMap mà p99 không đổi | Cache/hot data, RF=all, workload nhẹ hoặc test thiếu power | Đổi lab 4 node RF3, đo nhiều keys và internode bytes |
| LOCAL_QUORUM gặp Unavailable dù 1 node Up | RF=3 yêu cầu 2 replica local phản hồi | So CL, local RF và trạng thái replicas |
| Chuyển DC failover nhưng kết quả không như mong đợi | Local CL failover tắt mặc định hoặc remote RF khác | Kiểm tra DC failover options, consistency và kế hoạch DR |
| Node vừa thêm làm query plan lạ | Metadata/schema agreement đang chuyển đổi | Chờ topology ổn định, refresh/quan sát token map |

Không tự sửa `Request.setNode()` để ép mọi câu truy vấn vào một host. API này **bỏ qua load balancing policy** cho statement, thường chỉ hợp lý với các truy vấn node-local như `system.local` hoặc quy trình quản trị đặc biệt. Ép node cho workload nghiệp vụ có thể làm mất cân tải/token locality và gây lỗi khi node ấy Down.

## 12. Bài tập tình huống

### Bài 1 — Phân biệt coordinator và replica

DC có A/B/C/D, RF=3. Partition K nằm ở A/B/C. Java gửi query tới D và đọc thành công. D có phải replica của K không? Vì sao request vẫn đúng?

**Gợi ý:** D là **coordinator không giữ K**; nó có thể liên hệ A/B/C để đọc theo CL. Kết quả thành công không chứng minh định tuyến tối ưu.

### Bài 2 — Vì sao prepared query bị mất routing key?

Table có `PRIMARY KEY ((tenant_id, event_day), event_time)`. Developer chuẩn bị query với `tenant_id` viết literal và chỉ bind `event_day`. Driver trả `getRoutingKey() == null`. Có phải bug?

**Gợi ý:** theo hành vi Driver 4.x, chỉ tự suy routing key nếu **mọi thành phần partition key được bind thành biến**. Hãy prepare `tenant_id = ? AND event_day = ?` rồi bind cả hai.

### Bài 3 — Local DC sai

Service chạy gần `dc2` nhưng config driver có `local-datacenter = dc1`. RF bằng nhau ở cả hai DC. Điều gì có thể xảy ra?

**Gợi ý:** coordinator bị ưu tiên ở `dc1`, thêm RTT WAN cho request; cần cấu hình DC gần ứng dụng, kiểm tra cert/address/replica và CL. Không chỉ đổi contact points rồi quên local DC.

### Bài 4 — RF bằng số node

Lab có ba node/RF=3. Cả SimpleStatement lẫn BoundStatement đều cho 100% coordinator là replica. Có chứng minh token-aware không có ích?

**Gợi ý:** không. Mọi local node đều là replica, nên test thiếu nhóm non-replica để so. Thêm node lab thứ tư với RF=3 hoặc chọn một topology có node không giữ partition.

### Bài 5 — Kích hoạt failover qua DC

Cluster có `dc1` RF=3, `dc2` RF=1. Service dùng `LOCAL_QUORUM`. Đội vận hành muốn bật `allow-for-local-consistency-levels=true` để failover nhanh. Rủi ro gì?

**Gợi ý:** quorum local phụ thuộc RF tại coordinator DC: dc1 yêu cầu 2, dc2 chỉ 1. Đây là thay đổi semantics nhất quán, có thể tăng WAN load/staleness. Cần DR design, thử lỗi thực tế và phê duyệt trước khi bật.

### Bài 6 — Hot partition vẫn quá tải

Prepared token-aware đúng, nhưng A/B/C nóng và D rảnh. Nên ép coordinator sang D không?

**Gợi ý:** không phải cách xử lý gốc. Replicas của hot partition vẫn là A/B/C; chuyển coordinator sang D còn tăng hop. Hãy cân nhắc key/bucket, caching và concurrency limits theo access pattern.

### Bài 7 — Keyspace và routing token

Cùng một partition token nhưng keyspace X RF=2, keyspace Y RF=3. Driver biết token nhưng không có routing keyspace. Có chắc chọn được tập replica đúng không?

**Gợi ý:** không. Tập replica cần **keyspace replication metadata**; routing token không đủ để xác định phạm vi bản sao nếu thiếu keyspace.

### Bài 8 — Contact point là seed hay pin coordinator?

Driver khởi động bằng `db1` rồi sau đó các request được xử lý tại `db2` và `db3`. Điều này có bất thường không?

**Gợi ý:** bình thường. Contact points là đầu mối bootstrap, driver khám phá các node và policy chọn coordinator cho mỗi query.

### Checklist hoàn thành bài

- [ ] Phân biệt được coordinator, replica, contact point và query plan.
- [ ] Hiểu partition key (toàn bộ components) quyết định token; clustering columns không đổi token.
- [ ] Biết `DefaultLoadBalancingPolicy` của Driver 4.x đã token-aware theo mặc định.
- [ ] Chọn đúng `local-datacenter` theo vị trí ứng dụng và topology Cassandra.
- [ ] Có `routing keyspace + routing key + token map` để ưu tiên local replicas.
- [ ] Dùng prepared/bound và bind đủ partition components thay vì kỳ vọng SimpleStatement tự parse key.
- [ ] Đo được `getRoutingKey()`, `TokenMap.getReplicas()` và `ExecutionInfo.getCoordinator()`.
- [ ] Biết query plan có fallback/retry và coordinator không quyết định số ACK CL.
- [ ] Hiểu cross-DC failover **tắt mặc định**, local CL failover có giới hạn riêng.
- [ ] Có lab đủ node để so token-aware với round-robin mà không bị RF=all che kết quả.
- [ ] Biết điều tra hot partition, topology, token metadata, WAN traffic và p99 bằng số liệu.

## 13. Tài liệu tham khảo

1. Apache Java Driver 4.19 — [Load Balancing](https://apache.github.io/cassandra-java-driver/4.19.0/core/load_balancing/): policy mặc định, local DC, node distance, token-aware query plans và cross-DC failover.
2. Apache Java Driver 4.19 — [Prepared Statements](https://apache.github.io/cassandra-java-driver/4.19.0/core/statements/prepared/): metadata partition key, bind variables và routing key tự động.
3. Apache Java Driver 4.19 — [Statements](https://apache.github.io/cassandra-java-driver/4.19.0/core/statements/): routing keyspace/key/token, tính bất biến của Statement và CL.
4. Apache Java Driver 4.19 — [TokenMap API](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/metadata/TokenMap.html): lấy tập replica theo keyspace và partition key bytes/token.
5. Apache Java Driver 4.19 — [Performance](https://apache.github.io/cassandra-java-driver/4.19.0/core/performance/): prepared queries, schema/token map metadata và chi phí CPU/memory.
6. Apache Java Driver 4.19 — [Configuration](https://apache.github.io/cassandra-java-driver/4.19.0/core/configuration/): HOCON, execution profiles, policy và driver options.
7. Apache Java Driver 4.19 — [ExecutionInfo API](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/cql/ExecutionInfo.html): coordinator và thông tin thực thi.
8. Apache Cassandra Documentation — [Dynamo Architecture](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html): partitioning, token ring, replication và consistency.
9. Apache Cassandra Documentation — [CQL Data Definition](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html): partition/clustering key và `NetworkTopologyStrategy`.
