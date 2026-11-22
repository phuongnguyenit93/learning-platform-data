# Endpoint, topology discovery và định tuyến yêu cầu

Khi một ứng dụng Java kết nối với **Database No SQL**, lập trình viên thường bắt đầu từ một chuỗi URI, một danh sách host hoặc một region. Nhưng đó mới là **điểm khởi tạo kết nối (bootstrap)**. Trong một cluster phân tán, node nhận request, node giữ bản sao dữ liệu và node thực sự thực thi truy vấn có thể là những thành phần khác nhau.

Ví dụ, một ứng dụng đặt hàng cấu hình:

~~~text
mongodb://db-a.internal:27017,db-b.internal:27017,db-c.internal:27017
~~~

Không có nghĩa Java sẽ gửi một phần ba write tới từng host. MongoDB driver cần khám phá replica set, nhận biết primary/secondary và chọn server theo yêu cầu của operation. Nếu kết nối tới sharded cluster, ứng dụng lại thường liên hệ **mongos**, còn mongos mới định tuyến tới các shard.

Tương tự, Cassandra driver dùng contact points để khám phá ring và có thể định tuyến token-aware theo partition key; Redis Cluster client cần hiểu hash slots và các phản hồi MOVED/ASK; DynamoDB SDK gọi endpoint theo region nhưng không cho ứng dụng tự chọn physical partition của dịch vụ.

Bài học thuộc chương **Kết nối Java** của **Database No SQL**. Mục tiêu là hiểu sự khác nhau giữa **endpoint**, **topology discovery**, **server selection** và **request routing**, từ đó cấu hình driver đúng, xử lý failover, bảo vệ tính nhất quán và giải thích lỗi “kết nối được seed host nhưng query vẫn timeout”.

> **Quy tắc quan trọng:** Một địa chỉ kết nối hoạt động chưa chứng minh toàn bộ cluster reachable; một node healthy chưa chắc có quyền ghi; và một query nhắm đúng server chưa chắc đã nhắm đúng shard dữ liệu.

## 1. Bốn câu hỏi phải tách riêng

Khi nhìn vào code Java:

~~~java
var client = createClient(connectionString);
var result = client.read(key);
~~~

Cần hỏi:

1. **Bootstrap endpoint:** Java gặp hệ thống ở đâu lần đầu?
2. **Topology discovery:** Driver học được những node/role/partition nào?
3. **Server selection:** Với một operation cụ thể, driver chọn nơi gửi request dựa trên policy nào?
4. **Data routing:** Thành phần nào quyết định shard/partition sở hữu key cần đọc hoặc ghi?

Các câu trả lời phụ thuộc engine. Không phải driver nào cũng thấy topology lưu trữ nội bộ; một số chỉ thấy managed regional API endpoint.

## 2. Endpoint là gì?

**Endpoint** là địa chỉ mạng của một dịch vụ có thể nhận kết nối hoặc request. Dạng thường gặp:

~~~text
db-a.internal:27017
cassandra-a.internal:9042
redis-a.internal:6379
https://dynamodb.us-east-1.amazonaws.com
mongodb+srv://cluster.example.com
~~~

Endpoint có thể là:

- Một process database cụ thể.
- Một router/proxy đặt phía trước các node.
- Một DNS name ánh xạ đến nhiều addresses.
- Một contact point dùng để khám phá topology.
- Một managed regional service endpoint.
- Một Kubernetes Service hoặc load balancer.
- Một cluster-level endpoint nhưng không lộ node vật lý.

**Endpoint không đồng nghĩa data owner**. Một request tới proxy có thể được chuyển tiếp nhiều bước.

## 3. Endpoint, seed, router và replica

| Khái niệm | Chức năng | Có nhất thiết chứa dữ liệu không? |
|---|---|---|
| Bootstrap/seed host | Địa chỉ ban đầu để hỏi cluster | Không bắt buộc |
| Contact point | Node đầu tiên driver có thể liên hệ | Thường là node thật ở một số engine |
| Router/proxy | Nhận request rồi chọn backend | Có thể không |
| Primary/leader | Điều phối write của một nhóm dữ liệu | Thường có data state/log |
| Secondary/follower | Giữ bản sao hoặc phục vụ read phù hợp | Thường có |
| Shard | Một phần dữ liệu theo shard key | Có |
| Coordinator | Node phối hợp request đến replicas | Có thể là node dữ liệu nhưng không phải owner duy nhất |
| Managed API endpoint | Cổng vào do nhà cung cấp quản lý | Không lộ physical placement |

Một URI duy nhất có thể dẫn tới nhiều node qua discovery; nhiều seed hosts cũng có thể cùng giới thiệu **một replica set**.

## 4. Ba lớp routing của một request

Sơ đồ tổng quát:

~~~mermaid
flowchart LR
    A["Java API"] --> B["Driver / Connection pool"]
    B --> C["Server / Router được chọn"]
    C --> D["Shard / Partition đích"]
    D --> E["Replica hoặc leader xử lý"]
    E --> D
    D --> C
    C --> B
    B --> A
~~~

Tùy hệ, một số lớp hợp nhất:

- MongoDB replica set: driver chọn primary/secondary của replica set.
- MongoDB sharded cluster: driver thường gửi tới mongos; mongos route tới shards.
- Cassandra: driver có thể chọn coordinator phù hợp, coordinator trao đổi với replicas.
- Redis Cluster: client chọn node sở hữu hash slot, xử lý redirect.
- DynamoDB: SDK gửi HTTPS tới regional endpoint, dịch vụ định tuyến nội bộ.

Không tự áp một thuật toán client-side consistent hashing lên mọi loại NoSQL nếu nhà cung cấp đã có tầng routing riêng.

## 5. Tại sao ứng dụng không nên pin cứng một node?

Nếu Java chỉ biết:

~~~text
db-a.internal
~~~

và tự mặc định A là primary vĩnh viễn, sau failover A có thể:

- Trở thành secondary.
- Ngừng phục vụ.
- Bị đổi IP/pod.
- Không còn là member hợp lệ.
- Không còn leader cho partition.
- Không có bản dữ liệu phù hợp với read consistency.

Driver hỗ trợ discovery có thể chọn backend mới theo protocol. Nhưng việc đó đòi **khả năng kết nối tới các endpoint được cluster công bố**, không chỉ seed đầu tiên.

## 6. Bootstrap khác steady state

Một phiên kết nối thường có hai giai đoạn:

~~~text
BOOTSTRAP
  read connection settings
  resolve DNS / SRV
  connect to a reachable seed/router
  authenticate / negotiate protocol
  learn topology if supported

STEADY STATE
  watch topology/health/role changes
  select node(s) for each operation
  manage connection pools
  retry or reroute when allowed
  refresh metadata after failover/rebalance
~~~

Mất một seed host sau bootstrap có thể không gây outage nếu driver còn biết các node khác. Ngược lại, **kết nối được seed** nhưng không kết nối được địa chỉ discovered nodes có thể làm ứng dụng không gửi request thành công.

## 7. Topology discovery thu thập gì?

Tùy engine/protocol, driver có thể biết:

- Member IDs/addresses.
- Primary, secondary, leader hoặc coordinator candidates.
- Datacenter, rack, zone.
- Replica-set name hoặc cluster ID.
- Shard/node health.
- Token ring/partition ownership.
- Hash-slot mapping.
- Server capabilities và protocol versions.
- Tags/labels dùng cho read preference.
- Latency/round-trip estimates.
- Metadata generation/epoch hoặc topology version.

Đây là **topology được driver quan sát tại một thời điểm**, không phải chân lý bất biến. Node có thể thay vai trò sau khi lựa chọn nhưng trước khi command đến.

## 8. Discovery không thay phân quyền

Một Java driver có thể biết địa chỉ node, nhưng **không có nghĩa client được phép truy cập mọi database/key**.

Tách:

- Authentication: ai đang kết nối?
- Authorization: được đọc/ghi collection, keyspace, table hoặc tenant nào?
- Encryption/TLS: có bảo vệ traffic và xác minh server không?
- Topology discovery: node nào đang phục vụ?
- Request routing: gửi operation đến đâu?
- Domain authorization: actor có quyền thao tác entity không?

Một tenant ID trong shard key không tự cấp quyền đọc tenant khác. Driver routing và business authorization là hai lớp riêng.

## 9. DNS name không luôn có nghĩa duy nhất một server

Một hostname có thể có nhiều A/AAAA records; DNS SRV có thể công bố service targets. DNS cache TTL và JVM/network environment ảnh hưởng thời điểm ứng dụng nhìn thấy thay đổi.

Ví dụ:

~~~text
db.example.internal
  A -> 10.0.0.10
  A -> 10.0.0.11
  A -> 10.0.0.12
~~~

Nhưng việc có nhiều A records không biến một client không hỗ trợ cluster thành client topology-aware. Nhiều engine cần **protocol discovery** và routing rules ngoài DNS.

## 10. MongoDB: replica set topology

Trong MongoDB replica set, các member thường có một primary và những secondary:

~~~mermaid
flowchart TD
    Java["Java MongoDB driver"] --> A["Primary A"]
    Java -. "Read preference" .-> B["Secondary B"]
    Java -. "Read preference" .-> C["Secondary C"]
    A -->|"Oplog replication"| B
    A -->|"Oplog replication"| C
~~~

Driver quan sát topology và chọn server theo operation:

- Write thông thường tới primary.
- Read theo read preference và các giới hạn.
- Failover có thể đổi primary.
- Các member quảng bá địa chỉ dùng để driver liên hệ.
- Session và causal guarantees là tầng khác với việc chọn host.

Không nên tự round-robin write tới ba thành viên của replica set.

## 11. MongoDB connection string với nhiều seed hosts

Ví dụ URI cho một replica set nội bộ:

~~~text
mongodb://db-a.internal:27017,db-b.internal:27017,db-c.internal:27017/orders?replicaSet=orders-rs&readPreference=primary
~~~

Ý nghĩa:

- Danh sách hosts: **seed list**, không phải ba destinations luân phiên bắt buộc.
- `replicaSet=orders-rs`: yêu cầu nhận đúng replica set name.
- `readPreference=primary`: read mặc định đến primary theo semantics phù hợp.
- `/orders`: default database trong URI, không phải selector quyết định node giữ dữ liệu.

URI cần encode đúng password nếu có credentials. Trong ví dụ production nên đưa chuỗi URI qua secret manager/environment variable, không commit vào source code.

## 12. Java: dùng MongoClient một lần cho ứng dụng

Với MongoDB Java sync driver, một ví dụ:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public final class OrderRepository implements AutoCloseable {
    private final MongoClient client;
    private final MongoCollection<Document> orders;

    public OrderRepository(String uri) {
        this.client = MongoClients.create(uri);
        MongoDatabase db = client.getDatabase("orders");
        this.orders = db.getCollection("orders");
    }

    public Document findById(String orderId) {
        return orders.find(new Document("_id", orderId)).first();
    }

    @Override
    public void close() {
        client.close();
    }
}
~~~

Ví dụ dùng API cơ bản của MongoDB sync driver. Dependency/version, TLS, timeout, credentials và exception handling cần được cấu hình theo dự án thực tế.

Điểm chính: **MongoClient thường là object có pool và topology monitoring**, nên dùng chung theo lifecycle của ứng dụng; không tạo/đóng client cho từng HTTP request.

## 13. Java: connection pool khác topology discovery

Một client có thể quản lý nhiều **connection pools**, mỗi pool ứng với một server đã được chọn/biết.

Pool quyết định:

- Có kết nối socket/TLS sẵn không?
- Có phải đợi connection checkout không?
- Bao nhiêu connections được giữ?
- Idle/max lifetime và kết nối chết được xử lý sao?
- Có bị nghẽn vì concurrency quá cao không?

Topology discovery quyết định **server candidates**. Một server đã được chọn vẫn có thể làm request đợi vì pool exhausted; ngược lại pool còn rảnh nhưng không có server đáp ứng read preference thì operation vẫn fail.

## 14. MongoDB SRV URI

Một URI dạng:

~~~text
mongodb+srv://cluster.example.com/orders
~~~

có thể dùng DNS SRV/TXT theo quy tắc MongoDB driver để tìm seed targets và một số options. Nó giúp quản lý topology endpoint thuận tiện, đặc biệt với managed clusters.

Tuy nhiên:

- DNS SRV record phải hợp lệ.
- Resolver/network phải hỗ trợ truy vấn.
- Các targets được công bố phải reachable.
- TLS certificate/hostname phải đúng.
- SRV không tự cung cấp permission hoặc read consistency.
- DNS seedlist không thay protocol monitoring sau bootstrap.

Không giả định đổi một DNS record là mọi connection đang mở lập tức di chuyển.

## 15. Tại sao directConnection dễ gây nhầm?

Trong một số môi trường development, ứng dụng chỉ expose **một cổng** của MongoDB qua tunnel hoặc Docker port mapping, khiến developer bật `directConnection=true`.

Cấu hình này có thể thích hợp cho **kết nối trực tiếp một node** theo nhu cầu thử nghiệm; nhưng nó không thay thế việc driver khám phá nhiều member/primary trong deployment mà ứng dụng cần tự failover.

Đừng sửa lỗi “không reachable discovered host” ở production bằng cách ép directConnection tới một node bất kỳ rồi tuyên bố HA đã hoạt động. Cần giải quyết DNS, advertised hostnames, network routes hoặc cách triển khai access được hỗ trợ.

## 16. MongoDB: advertised member addresses

Một node có thể được kết nối qua:

~~~text
localhost:37017 (port-forward)
~~~

nhưng replica set config công bố:

~~~text
mongo-0.db.svc.cluster.local:27017
mongo-1.db.svc.cluster.local:27017
mongo-2.db.svc.cluster.local:27017
~~~

Java chạy **ngoài Kubernetes** có thể không resolve hoặc route tới những tên nội bộ ấy. Vì vậy seed endpoint reachable không đủ.

Giải pháp kiến trúc có thể là:

- Chạy Java trong mạng resolve/reach các địa chỉ công bố.
- Cấu hình topology hostnames theo kiến trúc mạng được hỗ trợ.
- Dùng gateway/proxy/managed endpoint có semantics phù hợp.
- Dùng topology dành riêng cho môi trường development.
- Không ép driver tự đoán IP từ kết nối seed nếu protocol không hỗ trợ.

## 17. MongoDB server selection

Một read/write operation thường được chọn server dựa trên:

- Server type: primary/secondary/mongos.
- Read preference và tags nếu dùng.
- Server health/topology state.
- Latency window/server selection logic.
- Session/transaction constraints.
- Timeout.
- Cluster mode: replica set, sharded hoặc standalone.

**Server selection timeout** có thể xảy ra ngay cả khi ứng dụng resolve DNS và mở socket tới một host. Ví dụ không có primary eligible, hoặc read preference chỉ cho phép secondary trong khi không có secondary đáp ứng.

## 18. Read preference không phải read concern

| Cấu hình | Trả lời câu hỏi |
|---|---|
| Read preference | Đọc từ loại node nào? |
| Read concern | Đọc mức dữ liệu/consistency nào? |
| Write concern | Khi nào write được xác nhận? |
| Retry reads/writes | Khi gặp lỗi phù hợp có thể thử lại không? |
| Session/causal context | Các operation liên quan có phụ thuộc thứ tự quan sát không? |
| Transaction options | Những read/write có thuộc một transaction không? |

Chọn `secondary` không tự bảo đảm read-your-writes. Chọn primary không tự giải quyết mọi vấn đề linearizability hoặc snapshot isolation; phải dựa trên semantics read concern và thời điểm election.

## 19. Write concern và routing

Một write được driver route tới primary không có nghĩa đã bền vững trên đa số replica.

Ví dụ conceptual:

~~~text
Java -> Primary -> local acknowledgment
                -> secondary replication continues
~~~

So với một write concern yêu cầu majority theo MongoDB semantics. Phải hiểu acknowledgment/durability policy, driver retry và lỗi failover. Không tự dùng số host trong URI làm bằng chứng `w=majority`.

## 20. Session và read-your-writes

Một khách vừa cập nhật profile rồi lập tức đọc lại. Nếu read đi tới secondary còn lag, khách có thể thấy bản cũ.

Các cách xử lý tùy engine:

- Read trên primary khi yêu cầu và semantics phù hợp.
- Causal session với read/write concerns được hỗ trợ.
- Chờ projection theo source version.
- Trả response từ write result thay vì lập tức đọc qua cache cũ.
- Nếu API chấp nhận stale, công bố rõ giới hạn.

**Topology-aware driver không tự biến mọi read thành strongly consistent read**.

## 21. MongoDB sharded cluster: mongos là điểm vào

Ở một MongoDB sharded cluster:

~~~mermaid
flowchart LR
    Java["Java MongoDB driver"] --> M1["mongos router A"]
    Java --> M2["mongos router B"]
    M1 --> S1["Shard 1"]
    M1 --> S2["Shard 2"]
    M1 --> S3["Shard 3"]
    M2 --> S1
    M2 --> S2
    M2 --> S3
~~~

Ứng dụng thường gửi request đến **mongos**, không tự tìm primary của tất cả shards. Mongos dùng routing metadata/chunk placement để gửi tới shard liên quan, và mỗi shard có replication topology riêng.

Khi có nhiều mongos, driver chọn router theo protocol, còn **mongos mới quyết định shard targeting**.

## 22. Shard key và targeted query

Ví dụ collection `orders` có shard key `{ tenantId: 1, orderId: 1 }` trong một cấu hình minh họa.

Query:

~~~javascript
db.orders.findOne({
  tenantId: "t-17",
  orderId: "o-100"
});
~~~

cung cấp điều kiện đầy đủ để router có thể nhắm một shard theo mapping hiện hành.

Query:

~~~javascript
db.orders.find({ status: "PENDING" });
~~~

không có shard key và có thể scatter-gather trên nhiều shard.

Điều quan trọng:

- Java driver chọn mongos.
- Mongos dùng shard key/chunk metadata.
- Trong shard, index/query planner mới xử lý local query.
- Một IXSCAN tốt không tự biến query thiếu shard key thành single-shard targeted.

## 23. Phân biệt routing một key và routing một transaction

Một `findById` theo full shard key có thể nhắm một shard, nhưng transaction tạo Order, giữ Inventory và cập nhật Coupon có thể liên quan nhiều shard.

Nếu một operation nhiều document:

- Xác định shard keys của tất cả entity.
- Hiểu transaction scope của engine/version.
- Đo coordinator/cross-shard overhead.
- Bảo vệ invariant tại write-time.
- Không dùng cache/search để quyết định đặt hàng cuối cùng.
- Dùng idempotency khi client timeout.

Không kết luận “API đến cùng một mongos” đồng nghĩa “mọi write đều ở cùng một shard”.

## 24. MongoDB failover trong Java

Khi primary lỗi:

~~~text
t0: A primary, B/C secondaries
t1: Java gửi write
t2: A crash hoặc step down
t3: Replica-set election chọn B nếu điều kiện hợp lệ
t4: Driver topology monitor cập nhật primary
t5: Write mới được route tới B
~~~

Trong khoảng t1–t5, request có thể timeout, bị từ chối hoặc có kết quả chưa rõ. Không có một thời gian failover cố định cho mọi deployment.

Retryable writes theo driver/operation/cluster support giúp một số lỗi, nhưng **không làm mọi business operation exactly-once**. Một request tạo đơn hàng nên có stable idempotency key hoặc unique constraint phù hợp.

## 25. Khi server selection timeout, cần kiểm tra gì?

Ví dụ Java ghi log “no server suitable for write within deadline”. Kiểm tra theo thứ tự có ích:

1. Client đang dùng URI của môi trường nào?
2. DNS của seed và discovered member có resolve không?
3. Các địa chỉ advertised có reachable từ runtime Java không?
4. TLS handshake và hostname verification có đạt không?
5. Credentials/permissions có hợp lệ?
6. Replica set có primary eligible không?
7. Driver có đang yêu cầu sai replicaSet name hoặc read preference?
8. Có network partition/firewall/NAT/Kubernetes port mismatch?
9. Pool có bị cạn hoặc request timeout quá nhỏ?
10. Server/driver logs có chỉ ra election hoặc topology changes?

Không phản xạ tăng timeout vô hạn; nếu tên node nội bộ không resolve thì timeout dài hơn chỉ kéo dài thất bại.

## 26. Cassandra: contact points không phải danh sách cố định mọi query

Cassandra Java driver được cấu hình một số **contact points** để bắt đầu khám phá các node trong cluster. Sau bootstrap, driver có thể xây metadata về datacenter, rack, token và ownership.

~~~mermaid
flowchart TD
    Java["Java Cassandra Driver"] --> CP["Initial Contact Point"]
    CP --> Meta["Cluster metadata"]
    Meta --> N1["Node A / token ranges"]
    Meta --> N2["Node B / token ranges"]
    Meta --> N3["Node C / token ranges"]
    Java -->|"Token-aware selection"| N2
~~~

Contact points nên là các node đáng tin, reachable, trải các failure domains khi hợp lý. Nhưng ba contact points không có nghĩa ba write replicas cố định cho mọi key.

## 27. Cassandra partition key quyết định token

Một bảng CQL:

~~~sql
CREATE TABLE orders_by_tenant (
    tenant_id text,
    bucket text,
    created_at timestamp,
    order_id text,
    status text,
    PRIMARY KEY ((tenant_id, bucket), created_at, order_id)
);
~~~

Partition key ở đây là cặp `(tenant_id, bucket)`. Driver/protocol có thể xác định token từ key khi prepared statement mang đủ partition-key values.

~~~sql
SELECT *
FROM orders_by_tenant
WHERE tenant_id = ?
  AND bucket = ?;
~~~

Nếu query không cung cấp partition key đầy đủ, token-aware routing có thể không áp dụng theo cách mong muốn, hoặc query không hợp lệ/đắt theo quy tắc CQL.

**Partition key phục vụ cả data placement và query routing**, khác với việc Java chỉ biết IP của một node.

## 28. Cassandra: driver chọn coordinator

Với Cassandra, node nhận CQL request là **coordinator** của request. Nó liên hệ các replicas liên quan theo replication strategy và consistency level.

Một token-aware driver có thể ưu tiên coordinator phù hợp với token/replicas và policy datacenter; việc này giảm network hops trong những điều kiện nhất định.

Nhưng:

- Coordinator không phải leader toàn cluster.
- Consistency level quyết định số replica responses phù hợp, không do số contact points.
- Một logical partition có thể được sao chép trên nhiều nodes.
- Coordinator có thể thay đổi mỗi request.
- Node routing phụ thuộc driver load-balancing policy, topology metadata và query key.

## 29. Cassandra Java Driver: ví dụ kết nối

Ví dụ theo API DataStax/Apache Cassandra Java Driver 4.x-style:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import java.net.InetSocketAddress;

public final class CassandraConnector {
    public static CqlSession connect() {
        return CqlSession.builder()
            .addContactPoint(
                new InetSocketAddress("cass-a.internal", 9042))
            .addContactPoint(
                new InetSocketAddress("cass-b.internal", 9042))
            .withLocalDatacenter("dc1")
            .build();
    }
}
~~~

Đây là mẫu minh họa; tùy phiên bản/nhà phân phối có thể cần dependency và cấu hình tương ứng. `CqlSession` thường được chia sẻ qua vòng đời ứng dụng và đóng khi shutdown, không tạo theo request.

`withLocalDatacenter("dc1")` **không phải tên bất kỳ để điền cho có**: nó phải khớp metadata datacenter thật. Datacenter mismatch có thể khiến driver không có node local đủ điều kiện cho policy.

## 30. Cassandra Java: prepared statement và routing key

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;

public final class OrdersByTenant {
    private final CqlSession session;
    private final PreparedStatement query;

    public OrdersByTenant(CqlSession session) {
        this.session = session;
        this.query = session.prepare(
            "SELECT order_id, status FROM orders_by_tenant "
          + "WHERE tenant_id = ? AND bucket = ?");
    }

    public ResultSet list(String tenantId, String bucket) {
        BoundStatement bound = query.bind(tenantId, bucket);
        return session.execute(bound);
    }
}
~~~

Khi driver có đủ partition key metadata và policy phù hợp, prepared/bound statement có thể hỗ trợ token-aware routing. Không giả định mọi arbitrary query string tự cung cấp routing key đúng.

## 31. Cassandra: local datacenter và multi-DC

Một cluster có thể sao chép dữ liệu qua nhiều datacenter:

~~~text
DC1: A1, B1, C1
DC2: A2, B2, C2
~~~

Driver có thể ưu tiên local DC để tránh WAN latency. Consistency levels như `LOCAL_QUORUM`, `QUORUM` hoặc chính sách khác ảnh hưởng semantics của read/write.

Nhưng **local DC không đồng nghĩa toàn cầu strongly consistent** trong mọi tình huống concurrent multi-DC writes. Cần hiểu replication factor per DC, coordinator placement, consistency levels và conflict resolution của Cassandra.

Không chọn `dc1` chỉ vì service Java đang chạy ở vùng gần đó; tên phải đúng với thông tin của cluster.

## 32. Cassandra topology changes

Khi node bootstrap/decommission, token ownership có thể thay đổi. Driver cần refresh topology; những prepared statements, connection pools và request routing có thể bị ảnh hưởng.

Các điểm quan sát:

- Node up/down và native transport availability.
- Topology/metadata refresh.
- Token map và datacenter/rack.
- Request coordinator được chọn.
- Speculative execution/retries theo policy.
- Consistency level errors, timeouts.
- Partition hot spots và large partitions.

**Driver metadata cần hội tụ**, nhưng ứng dụng không được coi token map tự viết trong cache là bất biến.

## 33. Cassandra: không chữa query thiếu partition key bằng thêm contact points

Một query chỉ lọc `status='PENDING'` trong bảng partition theo `(tenant_id,bucket)` có thể không được hỗ trợ hiệu quả; thêm 10 contact points không biến nó thành targeted read.

Cần access pattern khác:

- Bảng materialized theo status nếu thiết kế cho read.
- Index phù hợp theo khả năng engine/version.
- Query có đủ partition key.
- Application fan-out theo bucket có giới hạn.
- Analytics/read model riêng.

**Contact points giải quyết bootstrap; partition key giải quyết data access**.

## 34. Redis có nhiều mode topology

Phải phân biệt:

| Mode | Endpoint/Discovery | Routing |
|---|---|---|
| Standalone | Một server endpoint | Mọi command tới server đó |
| Primary/replica với Sentinel | Sentinel endpoints giúp khám phá primary | Client theo master hiện hành/read policy |
| Redis Cluster | Cluster node seeds và slot topology | Key → hash slot → owning node |
| Managed proxy endpoint | Service/proxy cung cấp endpoint ổn định | Phụ thuộc contract nhà cung cấp |

Một Redis client cấu hình standalone không tự hiểu Sentinel hoặc Redis Cluster chỉ vì hostname chứa chữ “cluster”.

## 35. Redis Sentinel: tìm primary mới

Trong Sentinel architecture, client có thể liên hệ các Sentinel nodes để khám phá primary của một **master name**. Khi failover xảy ra, master address có thể đổi.

~~~text
Java Redis client
  -> Sentinel A/B/C
  -> discover master "orders-cache"
  -> connect to Redis primary
  -> refresh after failover
~~~

Chỉ pin Java tới địa chỉ Redis primary hiện tại sẽ làm ứng dụng dễ mất write path khi Sentinel chọn primary khác.

Cần dùng client/library **hỗ trợ Sentinel mode**, không tự lập script polling và gán một IP cũ vô thời hạn.

## 36. Redis Cluster: 16.384 hash slots

Redis Cluster chia không gian khóa thành **16.384 hash slots**. Client dùng key để tìm slot và node đang sở hữu nó.

~~~text
key = order:1001
slot = CRC16(key) mod 16384
slot owner = Redis node X
```

Với key hash tag, phần trong cặp `{...}` được dùng cho slot calculation theo Redis rules:

~~~text
cart:{tenant-17}:items
cart:{tenant-17}:count
```

Hai key cùng tag `tenant-17` có thể nằm cùng slot, thuận tiện cho một số multi-key commands. Nhưng dồn quá nhiều key/workload vào một tag cũng có thể tạo **hot slot**.

Đừng tự đặt công thức routing tùy ý khác Redis Cluster protocol; client cluster-aware phải xử lý slot map và redirects.

## 37. MOVED và ASK

Trong Redis Cluster, node có thể trả:

- **MOVED:** slot được sở hữu ở node khác; client cần cập nhật route/slot map.
- **ASK:** redirect tạm thời trong quá trình slot migration, theo protocol yêu cầu bước tương ứng như `ASKING`.

Một cluster-aware client như Lettuce có thể thực hiện logic redirect và topology refresh theo khả năng/configuration.

Không coi MOVED là lỗi nghiệp vụ “not found”; cũng không retry vô hạn khi slot migration liên tục. Cần bounded retry, topology refresh và monitoring.

## 38. Java Lettuce Redis Cluster: ví dụ

Ví dụ API Lettuce dạng cluster:

~~~java
import io.lettuce.core.RedisURI;
import io.lettuce.core.cluster.RedisClusterClient;
import io.lettuce.core.api.StatefulRedisConnection;
import io.lettuce.core.cluster.api.StatefulRedisClusterConnection;

public final class RedisClusterConnector {
    public static RedisClusterClient createClient() {
        RedisURI seed = RedisURI.create(
            "redis://redis-a.internal:6379");
        return RedisClusterClient.create(seed);
    }

    public static void sample() {
        RedisClusterClient client = createClient();
        try (StatefulRedisClusterConnection<String, String> conn =
                 client.connect()) {
            String value = conn.sync().get("order:1001");
            System.out.println(value);
        } finally {
            client.shutdown();
        }
    }
}
~~~

Import hoặc auxiliary types có thể thay đổi theo Lettuce version; đây là hình thức minh họa basic lifecycle. Trong ứng dụng thực, chia sẻ `RedisClusterClient` và connection theo concurrency contract, cấu hình authentication/TLS, auto-reconnect, topology refresh và timeout phù hợp.

Một kết nối thử nghiệm mở/đóng trong `sample` không phải khuyến nghị tạo cluster client cho từng HTTP request.

## 39. Redis Cluster: multi-key và cross-slot

Một transaction hoặc Lua script trên nhiều keys có thể bị giới hạn bởi quy tắc **cùng hash slot** của Redis Cluster.

Ví dụ:

~~~text
cart:{t17}:items
cart:{t17}:total
```

Hai key dùng cùng hash tag, có thể cùng slot.

Nhưng:

~~~text
cart:{t17}:items
inventory:{sku-1}
```

khác hash tags, có thể nằm khác slots. Không kỳ vọng một `MULTI` hoặc script trên nhiều slots tự thành distributed transaction.

Không ép mọi key dùng một hash tag duy nhất để “giải quyết cross-slot”, vì điều đó phá phân tán tải.

## 40. DynamoDB: regional API endpoint

Với DynamoDB, Java SDK thường gọi một **regional HTTPS endpoint**. DynamoDB là managed service, SDK không cung cấp một danh sách physical storage nodes để ứng dụng tự chọn theo partition key.

~~~text
Java application
   -> AWS SDK v2
   -> DynamoDB region endpoint
   -> service internal routing
   -> managed partitions and replicas
```

Ứng dụng quyết định:

- Region.
- Credentials/IAM và request signing.
- Table name.
- Partition key/sort key.
- Consistency option được API hỗ trợ.
- Retry/timeout/HTTP pooling.

Không tự tạo một Cassandra-style token map cho DynamoDB.

## 41. Java AWS SDK v2: DynamoDB client

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.GetItemRequest;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;

import java.util.Map;

public final class DynamoExample {
    public static void main(String[] args) {
        try (DynamoDbClient client = DynamoDbClient.builder()
                .region(Region.US_EAST_1)
                .build()) {

            GetItemRequest request = GetItemRequest.builder()
                .tableName("Orders")
                .key(Map.of(
                    "pk", AttributeValue.fromS("TENANT#t17"),
                    "sk", AttributeValue.fromS("ORDER#o100")
                ))
                .consistentRead(true)
                .build();

            var response = client.getItem(request);
            System.out.println(response.hasItem());
        }
    }
}
~~~

Đây là ví dụ minimal cho một table có composite primary key `pk`/`sk`, chạy trong region cấu hình, với IAM credentials chain phù hợp. Đối với GSI, không thể áp `ConsistentRead=true` tùy ý; API/consistency support phải được kiểm tra.

Trong server production, thường tạo client dùng chung thay vì trong mỗi request.

## 42. DynamoDB endpointOverride dùng khi nào?

Trong local development hoặc test, SDK có thể dùng `endpointOverride` để trỏ tới DynamoDB Local hoặc emulator.

~~~java
// Minh họa: chỉ dùng với endpoint test được kiểm soát.
DynamoDbClient client = DynamoDbClient.builder()
    .region(Region.US_EAST_1)
    .endpointOverride(
        java.net.URI.create("http://localhost:8000"))
    .build();
~~~

Không đem local endpoint hoặc credentials giả vào cấu hình production. Khi override endpoint, vẫn cần hiểu region/signing/credentials theo SDK và emulator.

## 43. DynamoDB key design vẫn quyết định access pattern

DynamoDB tự quản lý physical partitions, nhưng cách chọn **partition key/sort key** ảnh hưởng query efficiency và hot keys.

~~~text
PK = TENANT#t17
SK = ORDER#2026-11#o100
```

Có thể Query các Order cùng tenant theo sort key range nếu schema phù hợp. Nhưng một tenant rất nóng có thể gây tải cao lên một logical key.

Một kiểu bucket:

~~~text
PK = TENANT#t17#MONTH#2026-11
SK = ORDER#o100
```

có thể phân tán theo tháng nhưng query nhiều tháng phải fan-out nhiều logical keys. Không báo “đã chạm 12 physical partitions” chỉ vì ứng dụng Query 12 buckets; dịch vụ không công bố ánh xạ vật lý đơn giản đó.

## 44. DynamoDB Global Tables và chọn region

Trong môi trường nhiều region, cần phân biệt:

- Endpoint theo region.
- Dữ liệu được replication qua region.
- Consistency model của Global Tables theo chế độ/version.
- Conflict resolution và concurrent multi-region writes.
- Failover của client/ứng dụng giữa các endpoints.
- IAM, quotas và mạng từng region.

**Đổi endpoint sang region khác không tự là strong failover an toàn** cho mọi workflow. Phải xác định data replication lag, request identity, write conflict và business invariant trước khi chuyển region.

## 45. GSI và read model có đường dữ liệu khác

Một Query trên DynamoDB Global Secondary Index có thể có semantics eventual consistency và được duy trì theo cơ chế riêng. Nó không đồng nhất với GetItem mạnh được hỗ trợ trên base table.

Nếu ứng dụng dùng GSI để tìm một booking rồi ghi, cần kiểm tra authoritative table/conditional write tại commit khi invariant quan trọng.

**Routing theo index** khác **tính mới nhất của dữ liệu**.

## 46. Search engines và topology discovery

Elasticsearch/OpenSearch Java clients có thể kết nối qua endpoint của cluster/proxy; một số triển khai hỗ trợ discover/sniff nodes theo cấu hình/client.

Cần xem môi trường mạng:

- Node có thể công bố private IP unreachable từ client ngoài cluster.
- Load balancer endpoint ổn định có thể là đường truy cập được nhà cung cấp khuyến nghị.
- Node sniffing có thể phá mạng NAT nếu client cố mở tới advertised IP.
- Search shard routing do search engine xử lý, không phải MongoDB shard key.
- Security, HTTPS và auth phải áp ở mọi node endpoint được truy cập.

Không bật sniffing chỉ vì “có nhiều nodes” nếu client nằm ngoài mạng có thể reach những node ấy.

## 47. Neo4j routing URI là một đối chiếu hữu ích

Trong graph database dùng Bolt routing, các URI kiểu `neo4j://` thường biểu thị routing driver trong những cấu hình hỗ trợ; `bolt://` có semantics direct endpoint khác. Driver có thể khám phá readers/writers và chọn backend theo access mode.

Điểm rút ra không phải thuộc lòng URI một sản phẩm, mà là **cùng hostname có thể có semantics routing khác nhau tùy scheme, driver và topology**. Cần đọc contract của URI chứ không chỉ thay protocol string theo kinh nghiệm.

## 48. Kubernetes: Service DNS có thể che topology

Một service:

~~~text
mongodb.database.svc.cluster.local
```

có thể load-balance tới nhiều pods, nhưng database protocol có thể yêu cầu driver nói chuyện với những member identity/role cụ thể.

Những lựa chọn thường thấy:

- Headless Service để mỗi StatefulSet member có stable DNS.
- Service endpoint cho router như mongos.
- Managed database endpoint ngoài Kubernetes.
- Proxy tương thích protocol.
- Cấu hình node advertised names phù hợp.
- NetworkPolicy cho đúng ports và pod traffic.

Không đặt một TCP load balancer ngẫu nhiên phía trước mọi primary/secondary rồi kỳ vọng driver nhìn thấy một replica set đúng nếu protocol không hỗ trợ cách đó.

## 49. DNS, NAT và advertised endpoint mismatch

Một sơ đồ lỗi:

~~~text
Java outside cluster
  -> public gateway:27017 (reachable)
  -> db-a.private.svc:27017 (advertised)
  -> Java cannot resolve db-a.private.svc
  -> server selection fails
```

Triệu chứng thường là **connect bootstrap được nhưng operation timeout**.

Cần kiểm tra từ đúng runtime Java:

- DNS resolution cho từng advertised name.
- TCP connectivity trên từng port.
- TLS certificate SAN/hostname.
- Firewall/NetworkPolicy.
- Pod churn và DNS TTL.
- Proxy/NAT mappings.
- IPv4/IPv6 behavior.

Đừng lấy kết quả `ping` từ laptop làm bằng chứng một pod Java có network route tương tự.

## 50. TLS và hostname verification

Một địa chỉ IP có thể mở TCP được nhưng TLS handshake thất bại vì certificate không có tên tương ứng.

Ví dụ:

~~~text
Endpoint used: db-a.internal
Certificate SAN: db-a.example.com
```

Nếu hostname không khớp theo policy, driver có thể từ chối kết nối.

Cách xử lý đúng:

- Cấp chứng chỉ có SAN phù hợp hostname được sử dụng.
- Sử dụng trust store và CA chain đúng.
- Kiểm soát certificate rotation.
- Đảm bảo secret không nằm trong logs.
- Dùng authentication/authorization của engine.
- Không tắt TLS hostname verification trong production chỉ để “kết nối cho được”.

## 51. Connection timeout không giống operation timeout

Một số timeout khác nhau:

| Timeout | Ý nghĩa |
|---|---|
| DNS resolution | Chờ hostname được phân giải |
| TCP connect | Chờ mở socket |
| TLS handshake | Chờ bảo mật phiên |
| Server selection | Chờ tìm node đủ điều kiện |
| Connection checkout | Chờ pool có connection |
| Socket/read | Chờ phản hồi I/O |
| Per-operation timeout | Giới hạn một command |
| Transaction timeout | Giới hạn cả transaction |
| Application request deadline | Giới hạn end-to-end HTTP |
| Retry budget | Tổng thời gian/attempt retry |

Nếu HTTP deadline là 2 giây mà driver server-selection timeout là 30 giây, cancellation và request queue có thể gây khó quản trị. Cần phối hợp **deadline truyền xuyên suốt** và timeout phù hợp; không chỉ tăng mọi timeout để giấu lỗi topology.

## 52. Retry và routing sau failover

Khi client gửi write tới leader cũ:

~~~text
Java -> Old leader A
A steps down
Java receives NotLeader / timeout
Driver discovers leader B
Java retries when allowed
~~~

Nhưng có trường hợp lệnh **đã commit trước khi response bị mất**. Vì thế:

- Retry chỉ các lỗi/operation mà SDK cho phép.
- Giữ idempotency key ổn định cho cùng business intent.
- Tách unknown commit outcome khỏi confirmed aborted.
- Với conditional writes, đọc lại state và invariant khi cần.
- Không gửi lại external payment/email vô điều kiện.
- Có backoff+jitter và retry budget.

Driver topology recovery giúp chọn đường gửi mới, **không thay business idempotency**.

## 53. Transaction routing không đồng nghĩa single-node transaction

Một transaction có thể chạm nhiều shards/partitions:

~~~text
Create Order -> Shard A
Reserve Inventory -> Shard B
Record Coupon -> Shard C
```

Việc Java có một `ClientSession` hoặc một connection không tự biến toàn bộ operation thành atomic trong mọi NoSQL. Cần hiểu phạm vi transaction engine hỗ trợ, coordinator, isolation và commit behavior.

Khi operation không thể thực hiện atomically qua nhiều sources, có thể cần saga, outbox, reservation hoặc bounded reconciliation.

## 54. Async và reactive client có khác routing không?

Java sync, async và reactive APIs khác nhau về concurrency/call mechanics:

- Sync: thread chờ kết quả.
- Async: callback/future, event loop hoặc non-blocking I/O.
- Reactive: Publisher/Subscriber với demand/backpressure semantics.

Nhưng server selection/topology discovery vẫn do driver/SDK implementation quyết định. Dùng reactive không tự giải quyết lỗi DNS/primary unavailable.

Một ứng dụng reactive phải tránh blocking call trên event-loop thread và quản lý cancellation/timeout đúng, nếu không một pool khỏe vẫn có thể bị nghẽn từ tầng ứng dụng.

## 55. Lifecycle và dependency injection

Trong Spring hoặc Java server, nên quản lý các client như shared resources:

~~~text
Application startup:
  load secrets and endpoints
  create MongoClient/CqlSession/RedisClusterClient/DynamoDbClient
  initialize repositories
  start health/metrics

Each HTTP request:
  reuse client
  execute operation with key/consistency requirements
  handle errors/retry according to policy

Application shutdown:
  stop accepting new traffic
  drain in-flight operations if possible
  close clients and pools
```

Không tạo mới client/tạo TLS handshake cho từng request nếu SDK không yêu cầu; điều đó làm tăng socket churn và latency. Đồng thời không giữ client sau shutdown khiến thread/pool rò rỉ.

## 56. Cấu hình ứng dụng theo môi trường

Ví dụ YAML khái niệm:

~~~yaml
database:
  engine: mongodb
  endpointSource: secretManager
  mode: replicaSet
  readPreference: primary
  writeConcern: majority
  serverSelectionTimeoutMs: 3000
  connectionPool:
    maxSize: 100
  tls:
    enabled: true
    verifyHostname: true
  retry:
    useDriverPolicies: true
    appIdempotencyRequired: true
observability:
  - topologyChanges
  - serverSelectionFailures
  - poolCheckoutWait
  - operationLatency
  - retryCount
~~~

Các thông số là **giá trị minh họa**, không phải cấu hình Spring Boot hoặc MongoDB driver được áp dụng trực tiếp. Thay `mode` và semantics theo engine thực tế.

Cần tách `dev`, `test`, `staging`, `prod` nhưng đảm bảo test có topology tương ứng khi kiểm chứng failover.

## 57. Endpoint được quản lý bằng secrets

Không commit những URI dạng:

~~~text
mongodb://admin:plaintext-password@db.example.com
```

Nên dùng biến môi trường, secret manager hoặc external configuration. Mặc dù URI có thể chứa username/password, không log toàn bộ URI khi có lỗi.

Nên audit:

- Who can read/rotate secrets?
- TLS certificates được cấp và rotate thế nào?
- Endpoint có thể tới production từ test hay không?
- IAM/service accounts có least privilege không?
- Mỗi tenant có authorization ở data layer không?
- Connection string có bị leak qua error pages hoặc traces không?

## 58. Topology-aware health check

Một endpoint `/health` trả `200 OK` chỉ vì có process Java đang chạy chưa đủ.

Cần phân biệt:

- **Liveness:** process hoạt động, chưa deadlocked.
- **Readiness:** có đủ dependencies để phục vụ một loại traffic?
- **Database connectivity:** có thể thực hiện operation nào?
- **Write capability:** có primary/quorum phù hợp không?
- **Read capability:** có server đáp ứng read preference không?
- **Lag/freshness:** projections/replicas theo kịp policy không?

Không dùng một write probe tạo document thật quá thường xuyên mà không có idempotency/cleanup. Readiness nên tránh gây cascading overload khi database đang chậm.

## 59. Connection pool metrics

Các chỉ số có ích:

- Active/idle connections.
- Connection creation/close rate.
- Connection checkout wait time.
- Pool wait queue depth.
- Max pool reached.
- Connection acquisition timeout.
- TLS reconnect rate.
- Per-server pool distribution.
- In-flight requests và HTTP concurrency.

Pool hết không phải lúc nào do pool quá nhỏ. Có thể do query chậm, transaction dài, leak session hoặc blocked threads. Tăng pool vô hạn có thể khiến database quá tải hơn.

## 60. Topology và routing metrics

Cần quan sát:

| Metric | Diễn giải |
|---|---|
| Topology state changes | Primary/leader/slots/token map thay đổi |
| Server selection time/failures | Driver có chọn được nơi gửi request không? |
| Discovered vs reachable nodes | Các địa chỉ cluster công bố có liên lạc được không? |
| Coordinator/server selected | Operation đã được gửi tới đâu? |
| Redis MOVED/ASK rate | Slot migration/routing cache drift |
| Cassandra local vs remote requests | Policy locality có hợp lý? |
| MongoDB targeted shards | Query có shard pruning? |
| Replica lag | Read preference có thể trả dữ liệu trễ |
| Retry and timeout counts | Failover/bottleneck biểu hiện ra sao |
| Connection pool saturation | Cạn connection hoặc query giữ lâu |
| DNS/TLS failures | Network/cert issues |
| Regional endpoint errors | Managed service availability |

Nhãn metrics nên có engine, operation type, region/DC và cluster ID. Tránh gắn PII hoặc raw tenant IDs có cardinality cực cao một cách tùy tiện.

## 61. Đo route của một request cụ thể

Một trace tốt gồm:

~~~text
traceId
operationName
databaseEngine
configuredEndpointLabel (redacted)
discoveredClusterId
selectedCoordinatorOrRouter
partitionKeyPresent (boolean)
consistencyMode
attemptNo
latencyMs
errorCategory
```

Không phải engine nào cũng lộ exact shard/physical partition. Khi thiếu quan sát, hãy ghi `unknown` thay vì đoán.

Ví dụ:

- MongoDB: driver command/topology monitoring + explain query để xem shard targeting.
- Cassandra: request tracing/driver metrics và token-aware routing metadata.
- Redis: slot mapping, redirect counters.
- DynamoDB: regional API metrics, consumed capacity, throttling; không tự nói biết physical partition ID.

## 62. Troubleshooting bằng bảng triệu chứng

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra trước |
|---|---|---|
| Connect seed thành công, query timeout | Discovered nodes không reachable | Advertised names, DNS, firewall |
| Không có primary eligible | Election hoặc sai replica set name | Replica set status, URI |
| Read trả dữ liệu cũ | Secondary/Cache/Projection lag | Read preference/concern/sourceVersion |
| Cassandra không tìm local nodes | Sai local DC hoặc mạng | DC metadata, load-balancing policy |
| CQL scan quá chậm | Query thiếu partition key | Schema/access pattern |
| Redis nhiều MOVED | Slot map cũ hoặc migration | Cluster topology refresh |
| Redis CROSSSLOT | Multi-key khác slot | Hash tag/command scope |
| DynamoDB request đúng endpoint nhưng throttled | Capacity/hot partition key | Consumed capacity, key distribution |
| TLS handshake fails | CA/SAN/cert rotation | Trust/hostname/chain |
| Pool checkout timeout | Concurrency/query chậm/leak | Pool metrics và in-flight ops |
| Timeout ngay sau failover | Driver rediscovery + retry budget | Topology events, error labels |
| Search node sniffing failures | Advertised private IP qua NAT | Connectivity và proxy mode |

Không xem bảng là quy trình tự động thay thế điều tra sự cố; cùng symptom có thể có nhiều nguyên nhân.

## 63. Một lỗi phổ biến: cân bằng tải TCP thay cho discovery

Tưởng tượng MongoDB replica set có A primary, B/C secondary. Một TCP load balancer chuyển connection ngẫu nhiên tới A/B/C:

~~~text
Java write -> TCP LB -> Secondary B -> rejects write
```

Một driver với protocol topology-aware cần biết **role và membership**, không thể giả định một LB không hiểu protocol sẽ luôn đưa write đúng primary.

Một proxy được nhà cung cấp thiết kế cho database có thể giải quyết vai trò này; nhưng một generic TCP round-robin không tự là database router. Tương tự Redis Cluster cần slot routing, Cassandra cần key/token/locality awareness.

## 64. Một lỗi phổ biến: client-side hash tự chế

Ứng dụng:

~~~java
int nodeIndex = Math.abs(key.hashCode()) % 3;
sendTo(configuredNodes[nodeIndex], command);
~~~

Cách này nguy hiểm nếu engine tự quản lý shard placement: thêm node, rebalance, replication factor hoặc membership change có thể làm mapping sai.

Chỉ dùng application sharding khi đó là **kiến trúc sở hữu của ứng dụng**, với placement directory, migration, failover và versioning do ứng dụng quản lý. Đừng chèn client hash lên MongoDB sharded cluster, Cassandra token ring hay Redis Cluster khi driver đã có protocol định tuyến chính thức.

## 65. Một lỗi phổ biến: retry gây tác dụng phụ trùng

Client gửi CreateOrder tới primary A, A commit nhưng response mất. Driver/network retry đến B sau election; ứng dụng không có idempotency key nên có thể tạo đơn thứ hai.

Cần:

- Stable operation ID cho một business intent.
- Unique/idempotency record trong source.
- Retry theo error classification.
- Reconciliation khi outcome chưa rõ.
- Không gọi payment/email trong callback có thể bị retry.
- Cân nhắc transaction/outbox cho event.

**Tìm đúng node sau failover không đảm bảo execute exactly-once ở tầng nghiệp vụ.**

## 66. Phân quyền tenant phải độc lập routing

Một query đủ shard key:

~~~text
tenantId=t-17
orderId=o-100
```

có thể target đúng shard nhưng vẫn không được phép nếu actor thuộc tenant khác.

Ứng dụng phải lấy tenant identity từ authenticated context, kiểm tra policy và dùng điều kiện tenant trong read/write. Không tin raw client-provided tenant ID như bằng chứng quyền.

## 67. Tách endpoint của control plane và data plane

Một hệ có thể có:

- Admin/metadata API.
- Cluster manager/quorum metadata.
- Data node endpoint.
- Router/proxy data endpoint.
- Metrics/health endpoint.

Không dùng endpoint admin làm data routing endpoint nếu protocol không cho phép. Khi debug, phải biết **node nào điều phối metadata** và **node nào nhận query**; hai vai trò có thể nằm cùng host nhưng semantics khác.

## 68. Ứng dụng đa region và vùng dữ liệu

Khi Java được chạy ở nhiều region:

- Mỗi instance nên có endpoint/region strategy phù hợp.
- Không tự suy region gần nhất từ hostname nếu policy phức tạp.
- Cross-region reads có thể tăng latency và stale risk.
- Failover giữa region cần đánh giá data consistency.
- Quorum/leader ownership có thể giới hạn write region.
- Data residency và compliance có thể cấm route dữ liệu sang nơi khác.
- Retry sau region failover cần idempotency và conflict reconciliation.

Một “DNS global” không tự cung cấp multi-region transactional consistency.

## 69. Những lựa chọn kiến trúc cần ghi vào ADR

Một Architecture Decision Record cho Java/NoSQL connection nên có:

1. Engine và deployment mode.
2. Endpoint bootstrap trong mỗi environment.
3. Discovered topology và khả năng reach các member.
4. Router/server selection owner.
5. Data placement/partition key owner.
6. TLS/auth/secrets policy.
7. Read/write consistency modes.
8. Connection pool và concurrency limits.
9. Timeout/deadline hierarchy.
10. Retryable errors, unknown outcomes và idempotency.
11. Multi-DC/region routing và residency.
12. Failover/rebalance expectations.
13. Metrics, runbook và acceptance tests.

Mục tiêu là để người đọc không nhầm “chúng tôi có ba host trong URI” với “hệ HA đã được thiết kế và kiểm thử”.

## 70. Bài tập A — MongoDB seed list

URI có ba seed hosts A/B/C. A là primary, B/C secondary.

**Hỏi:** write được gửi round-robin qua ba hosts không?

**Hướng giải:** không. Driver chọn server theo topology và operation; write thông thường được route tới primary eligible.

## 71. Bài tập B — Seed reachable, topology unreachable

Java từ máy ngoài cluster kết nối tới port-forward A nhưng replica set công bố `mongo-0.svc`, `mongo-1.svc`, `mongo-2.svc`.

**Hỏi:** vì sao `ping` seed OK nhưng query timeout?

**Hướng giải:** discovered addresses không resolve/reachable từ client. Cần giải quyết DNS/network/topology, không chỉ tăng server-selection timeout.

## 72. Bài tập C — Shard key

MongoDB sharded collection theo tenant/order; query chỉ lọc status.

**Hỏi:** driver chọn mongos đúng có giúp query single-shard không?

**Hướng giải:** không. Mongos vẫn phải dùng shard key; thiếu điều kiện có thể scatter-gather.

## 73. Bài tập D — Cassandra contact points

Java cấu hình ba contact points. Query có partition key đầy đủ.

**Hỏi:** ba contact points có phải ba replicas mà mỗi query luôn đọc không?

**Hướng giải:** không. Contact points dùng bootstrap; replica placement và consistency level quyết định các node tham gia.

## 74. Bài tập E — Cassandra local DC

Driver cấu hình `withLocalDatacenter("dc1")`, trong cluster chỉ có DC tên `asia-south`.

**Hỏi:** có thể xảy ra điều gì?

**Hướng giải:** load balancing không tìm local nodes phù hợp hoặc kết nối thất bại/không như dự kiến. Cần dùng đúng DC metadata.

## 75. Bài tập F — Redis MOVED

Redis Cluster client nhận MOVED cho slot 9000.

**Hỏi:** đó là lỗi “key không tồn tại” hay tín hiệu routing?

**Hướng giải:** tín hiệu slot owner thay đổi; cluster-aware client cần cập nhật route/redirect theo protocol.

## 76. Bài tập G — Redis hash tag

Hai keys `cart:{t17}:items` và `cart:{t17}:total` có cùng hash tag.

**Hỏi:** lợi ích và rủi ro?

**Hướng giải:** cùng slot thuận tiện multi-key operations; nhưng dùng một hash tag cho quá nhiều hot keys gây tập trung tải.

## 77. Bài tập H — DynamoDB endpoint

SDK Java gọi DynamoDB regional endpoint.

**Hỏi:** Java có thể lấy danh sách physical partition leaders rồi chọn thủ công như Cassandra không?

**Hướng giải:** không theo public API thông thường; dịch vụ managed routing nội bộ. Ứng dụng quan tâm region, key design, consumed capacity, throttling và consistency options.

## 78. Bài tập I — Connection pool hết

Driver biết primary chính xác nhưng requests vẫn chờ rất lâu để lấy connection.

**Hỏi:** đây là topology discovery hay pool problem?

**Hướng giải:** có thể là connection pool saturation do query chậm, concurrency cao hoặc leak. Cần pool metrics, in-flight ops và query latency.

## 79. Bài tập J — Primary failover và retry

Client gửi CreateOrder, commit có thể thành công nhưng response mất; driver chọn primary mới.

**Hỏi:** có nên gửi CreateOrder mới không có idempotency key?

**Hướng giải:** không an toàn. Cần stable operation ID, kiểm tra outcome/unique constraint và retry theo SDK/operation contract.

## 80. Bài tập K — Secondary stale read

Một user vừa write thành công nhưng GET từ secondary trả state cũ.

**Hỏi:** chỉ sửa DNS endpoint có giải quyết được không?

**Hướng giải:** không trực tiếp. Cần read preference/concern, causal session hoặc sourceVersion/freshness policy phù hợp.

## 81. Bài tập L — Generic TCP Load Balancer

Một LB gửi write ngẫu nhiên tới secondary của replica set.

**Hỏi:** LB đó có thay thế mongos hoặc topology-aware driver không?

**Hướng giải:** không; nó không tự hiểu role/partition/write authority.

## 82. Bài tập M — Timeout hierarchy

HTTP request deadline 2 giây, driver chờ chọn server 30 giây.

**Hỏi:** rủi ro?

**Hướng giải:** request quá thời hạn, task/connection có thể vẫn chờ nếu cancellation không hợp lý. Cần thống nhất deadline, không chỉ tăng timeout.

## 83. Bài tập N — Same endpoint, different consistency

Hai query cùng được gửi tới MongoDB primary, một dùng read concern khác hoặc session context khác.

**Hỏi:** có thể có guarantees khác nhau không?

**Hướng giải:** có. Endpoint/server role không tự quyết định mọi consistency guarantee.

## 84. Checklist tích hợp Java và NoSQL

1. Đã xác định đúng deployment mode: standalone, replica set, sharded, cluster, Sentinel hay managed service?
2. URI/endpoint là seed, router, primary, proxy hay regional API?
3. Java chạy từ đâu; resolve/reach được **mọi discovered endpoint cần thiết** không?
4. DNS SRV/TXT và TTL có phù hợp không?
5. TLS hostname verification, CA và credentials đúng chưa?
6. Secrets có bị log/commit vào source không?
7. Driver/SDK version có tương thích server/protocol không?
8. Client có được chia sẻ qua lifecycle ứng dụng thay vì tạo mỗi request không?
9. Connection pools có đo và giới hạn không?
10. Topology changes có được monitor không?
11. Server selection/read preference có đúng operation không?
12. Shard/partition key có đủ cho những truy vấn quan trọng không?
13. MongoDB đang dùng mongos đúng thay vì client-side hash tự chế không?
14. Cassandra contact points và local DC đúng metadata không?
15. Redis client có đúng mode standalone/Sentinel/Cluster không?
16. Redis MOVED/ASK và slot migrations có được xử lý không?
17. DynamoDB region/global table consistency contract rõ chưa?
18. Timeout DNS/connect/selection/pool/operation/request có phối hợp không?
19. Retry có phân loại lỗi và retry budget không?
20. Unknown write outcome có idempotency/reconciliation không?
21. Transaction scope và cross-shard behavior được hiểu đúng không?
22. Read-after-write và replica lag có contract rõ không?
23. Có metrics về pool, routing, topology, retries và SLO không?
24. Có test leader failover, node crash, DNS/NAT mismatch, pool saturation không?
25. Health/readiness có kiểm tra đúng capability thay vì chỉ process alive không?
26. Multi-region routing và data residency có được kiểm soát không?
27. Có runbook cho server selection timeout và topology refresh không?

## 85. Mẫu tài liệu thiết kế kết nối

~~~yaml
service: OrdersJavaApi
database:
  engine: MongoDB
  deployment: shardedCluster
  bootstrap:
    uriFrom: secretManager
    addressType: mongosRouters
  routing:
    firstHop: javaDriverServerSelection
    dataPlacement: mongosShardKeyRouting
  shardKey:
    fields: [tenantId, orderId]
    requiredForGetOrder: true
  consistency:
    reads: primaryAsRequired
    writes: majorityAsRequired
  security:
    tls: enabled
    hostnameVerification: required
    tenantAuthorization: enforcedAtApi
  connectionLifecycle:
    clientScope: applicationSingleton
    closeOnShutdown: true
  resilience:
    useDriverRetryRules: true
    operationIdForBusinessWrites: required
    boundedDeadline: required
    failoverTest: required
  observability:
    - serverSelectionFailures
    - poolCheckoutLatency
    - topologyChanges
    - queryLatency
    - targetedShardCount
    - unknownWriteOutcomes
~~~

Đây là **YAML mô tả kiến trúc**, không phải file cấu hình được MongoDB Java driver hoặc Spring Boot tự chấp nhận. Trường và giá trị phải ánh xạ theo SDK/server version thực tế.

## 86. Kết luận

**Endpoint** cho Java biết nơi bắt đầu giao tiếp; **topology discovery** cho driver biết những node hoặc roles đang tồn tại; **server selection** chọn nơi nhận operation; còn **data routing** xác định shard/partition và replica liên quan tới dữ liệu.

Trong MongoDB, driver chọn primary/secondary hoặc mongos; mongos route tới shard. Trong Cassandra, contact points hỗ trợ bootstrap, token-aware driver và coordinator phối hợp các replicas. Trong Redis Cluster, hash slot, MOVED/ASK và topology refresh quyết định node sở hữu key. Trong DynamoDB, Java SDK gọi regional endpoint và dịch vụ tự quản lý physical routing.

Các cơ chế đó chỉ hoạt động bền vững khi:

- Endpoint được công bố **reachable và có TLS/auth hợp lệ**.
- Client/pool được sử dụng đúng lifecycle.
- Partition/shard key phù hợp query shape.
- Read/write consistency được đặt theo nghiệp vụ.
- Failover có bounded retry và idempotency.
- Metrics và fault tests chứng minh đường đi thật.

> **Đừng nhầm “Java đã kết nối được một host” với “ứng dụng đã kết nối đúng cluster và định tuyến đúng mọi yêu cầu”.**

Thiết kế kết nối NoSQL tốt là thiết kế trong đó người vận hành có thể chỉ ra chính xác **request bắt đầu ở đâu, ai khám phá topology, ai chọn server, ai định tuyến key, ai có quyền ghi và điều gì xảy ra khi tất cả những điều đó thay đổi trong lúc request đang chạy**.
