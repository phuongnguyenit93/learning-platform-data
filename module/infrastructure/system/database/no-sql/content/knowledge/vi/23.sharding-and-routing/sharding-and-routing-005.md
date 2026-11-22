# Định tuyến tại client, proxy hoặc nút điều phối

Một hệ NoSQL ban đầu có thể chỉ dùng một máy chủ. Ứng dụng gửi yêu cầu đọc order, máy chủ tìm dữ liệu rồi trả lời. Khi dữ liệu tăng, hệ phải **phân mảnh (sharding/partitioning)**: một nhóm order được lưu trên shard A, nhóm khác trên shard B, các shard có thể nằm trên những node và vùng khác nhau. Từ thời điểm ấy, một yêu cầu tưởng đơn giản như **GET order-1001** phải giải quyết thêm câu hỏi: **Ai biết order-1001 đang thuộc shard nào và ai chịu trách nhiệm đưa request tới đúng nơi?**

Có ba cách tổ chức trách nhiệm thường gặp:

1. **Định tuyến tại client (client-side routing):** driver hoặc thư viện của ứng dụng biết sơ đồ phân mảnh và gửi request đến node thích hợp.
2. **Định tuyến qua proxy/router (proxy-side routing):** ứng dụng gửi request đến một lớp trung gian; proxy tìm shard hoặc backend và chuyển tiếp.
3. **Định tuyến tại nút điều phối (coordinator-side routing):** ứng dụng kết nối với một node trong cụm; node đó trở thành coordinator của request, xác định replica/shard liên quan và phối hợp kết quả.

Ba cách **không nhất thiết loại trừ nhau**. Một driver có thể chọn node có locality tốt, gửi request tới proxy, còn một node bên trong vẫn điều phối việc truy vấn nhiều shard. Redis Cluster, MongoDB sharded cluster, Cassandra, các hệ search phân tán và dịch vụ NoSQL được quản lý minh họa những cách tổ chức khác nhau.

Bài học tập trung vào **đường đi của request, metadata định tuyến, thay đổi topology, phân biệt targeted query với scatter–gather, xử lý retry/failover, tác động tới consistency và vận hành**. Mục tiêu không phải tự viết lại driver của từng database, mà là biết chọn kiến trúc và tìm đúng nguyên nhân khi dữ liệu đã có nhưng request chậm, bị chuyển hướng hoặc đọc sai bản.

## 1. Phân mảnh trước, định tuyến sau

Giả sử dữ liệu order nằm trong ba shard:

~~~text
Ứng dụng
  |
  +-- order-1001 -> Shard S1
  +-- order-1002 -> Shard S3
  +-- order-1003 -> Shard S2
~~~

Định tuyến phải giải được ít nhất hai bài toán:

- **Logical routing:** từ key/query xác định **partition hoặc shard logic** nào cần truy cập.
- **Physical routing:** từ shard logic xác định **node/endpoint/replica** nào đang chịu trách nhiệm và có thể trả lời request theo mức nhất quán yêu cầu.

Hai tầng này khác nhau. Ví dụ:

~~~text
orderId
  -> hash/order partition
  -> shard S2
  -> replica set [node-3, node-7, node-9]
  -> chọn primary hoặc replica theo read/write policy
~~~

Node-3 hỏng **không nhất thiết** khiến order-1003 đổi shard logic: có thể chỉ thay node phục vụ hoặc leader của S2. Ngược lại, khi **split shard hoặc reshard**, bản thân ánh xạ key → shard cũng có thể đổi.

## 2. Từ khóa phân vùng đến nơi chứa dữ liệu

Một request điển hình cần các thành phần:

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| **Routing key / partition key** | Giá trị dùng để xác định partition | tenantId, orderId, customerId |
| **Partitioning function** | Biến key thành token/slot/range | hash(key), range lookup |
| **Shard map** | Ánh xạ token/range/slot tới shard | slots 0–5000 → S1 |
| **Placement metadata** | Ánh xạ shard tới node/replica | S1 → node A, B, C |
| **Replica selection** | Chọn node phù hợp cho read/write | primary, local replica, quorum |
| **Topology version/epoch** | Nhận diện mapping cũ/mới | version 42 |
| **Transport endpoint** | Địa chỉ thực sự kết nối | DNS, host, port, TLS identity |

Đừng đồng nhất **partition key** với **địa chỉ IP**. Partition key thuộc mô hình dữ liệu; placement có thể thay đổi vì thêm node, rebalance, failover hoặc bảo trì.

### Ví dụ mô hình hóa shard map

~~~yaml
# Ví dụ khái niệm, không phải cấu hình dùng được cho một sản phẩm cụ thể
topologyVersion: 42
partitions:
  - range: "slot 0..4095"
    shard: S1
  - range: "slot 4096..8191"
    shard: S2
  - range: "slot 8192..12287"
    shard: S3
  - range: "slot 12288..16383"
    shard: S4
placement:
  S1:
    primary: node-a
    replicas: [node-b, node-c]
~~~

Một route hợp lệ phải xét cả **mapping** và **quyền phục vụ hiện tại**, không chỉ lấy node đầu tiên trong danh sách replicas.

## 3. Phân mảnh bằng hash, range và các biến thể

### Hash partitioning

Ví dụ logic:

\[
\mathrm{partition}(key)=H(key)\bmod P
\]

với P là số bucket logic. Các key có hash phân bố tương đối đều thường trải qua nhiều bucket.

Lưu ý:

- Hash phải **ổn định**, nhất quán về kiểu dữ liệu, encoding và canonicalization.
- Thay P trực tiếp trong biểu thức modulo có thể làm **rất nhiều key đổi vị trí**.
- Hash không bảo đảm mọi shard cân bằng nếu kích thước/traffic của key khác nhau.
- Một key cực nóng vẫn là điểm nghẽn dù phân bố tổng số key đều.

### Range partitioning

~~~text
orderId từ 000000 đến 099999 -> S1
orderId từ 100000 đến 199999 -> S2
orderId từ 200000 trở lên    -> S3
~~~

Range thuận tiện cho một số truy vấn phạm vi, nhưng key tăng liên tục có thể dồn write vào shard cuối. Khi range split, router phải biết biên mới.

### Consistent hashing và virtual nodes

Một họ thiết kế đặt token/node trên vòng hash; key tìm node/replica theo vị trí token. **Virtual nodes (vnodes)** tạo nhiều token range nhỏ cho một node vật lý, giúp phân phối và chuyển tải khi thay đổi cluster.

Consistent hashing **giảm lượng dữ liệu cần di chuyển trong những mô hình thích hợp**, không có nghĩa không có migration, không có mất cân bằng hoặc mọi sản phẩm dùng cùng thuật toán.

**Quan trọng:** routing function thực tế là một phần của protocol database. Không tự dùng Java String.hashCode hoặc SHA-256 tùy ý rồi kỳ vọng nó chọn đúng Redis slot hay Cassandra token.

## 4. Shard key quyết định hiệu quả định tuyến

Giả sử collection order được phân theo **tenantId**:

~~~json
{
  "tenantId": "shop-a",
  "orderId": "order-1001",
  "status": "PAID",
  "total": 240000
}
~~~

Nếu query có:

~~~text
WHERE tenantId = 'shop-a' AND orderId = 'order-1001'
~~~

router có thể dùng shard key để thu hẹp số shard cần hỏi.

Nếu query chỉ có:

~~~text
WHERE status = 'PAID'
~~~

và không có index/routing metadata phù hợp, query có thể cần đi tới **nhiều shard**. Thực tế còn phụ thuộc schema, index, điều kiện query và khả năng tối ưu của engine.

Một shard key tốt không chỉ giúp phân bố lưu trữ, mà còn giúp **đường truy vấn chủ lực trở thành targeted**.

### Shard key và khóa định danh không luôn trùng nhau

Ví dụ shard key là **tenantId**, còn document ID là **orderId**. Nếu một API chỉ nhận orderId mà không biết tenantId, router có thể thiếu thông tin để định tuyến chính xác. Ứng dụng có thể:

1. Yêu cầu tenantId trong request và xác thực nó.
2. Duy trì mapping orderId → tenantId trong nguồn đáng tin.
3. Thiết kế lại shard key phù hợp các đường truy vấn.
4. Chấp nhận một lookup bổ sung hoặc scatter–gather có kiểm soát nếu thực sự cần.

**Đừng thêm tenantId giả từ client chỉ để query nhanh**: tenant scope phải xuất phát từ quyền truy cập đã xác thực.

## 5. Ba vị trí có thể ra quyết định định tuyến

~~~mermaid
flowchart TD
    REQ["Client yêu cầu key K"] --> CHOICE{"Ai biết vị trí K?"}
    CHOICE -->|"SDK/driver"| A["Client tính token / tra shard map"]
    CHOICE -->|"Proxy/router"| B["Proxy tra metadata và forward"]
    CHOICE -->|"Database node"| C["Coordinator tra placement nội bộ"]
    A --> D["Shard/replica phù hợp"]
    B --> D
    C --> D
    D --> RESULT["Thực thi và trả response"]
~~~

Định tuyến ở đâu tác động tới:

- **Số network hops** và độ trễ.
- **Số kết nối** mà ứng dụng phải duy trì.
- **Cách cập nhật topology** khi reshard/failover.
- **Bề mặt bảo mật** giữa app và database nodes.
- **Điểm nghẽn và điểm lỗi** ở proxy hoặc coordinator.
- **Khả năng quan sát** request đã đi qua đâu.
- **Cách xử lý truy vấn nhiều shard**.

Không có một lựa chọn tối ưu cho mọi workload. Cần nhìn cả **topology, driver, mạng, đội vận hành và bất biến nghiệp vụ**.

## 6. Client-side routing: driver biết shard map

Trong mô hình **smart client**, ứng dụng dùng một driver có đủ metadata để tìm đúng shard/replica:

~~~mermaid
sequenceDiagram
    participant APP as Application
    participant SDK as Smart Driver
    participant META as Metadata/Discovery
    participant S1 as Node S1
    participant S2 as Node S2
    APP->>SDK: Get(order-1001)
    SDK->>META: Lấy/refresh topology khi cần
    META-->>SDK: Key range -> S2
    SDK->>S2: Request trực tiếp
    S2-->>SDK: Order
    SDK-->>APP: Kết quả
~~~

Thực tế metadata thường được **cache**, không tải lại từ một server cho mỗi request. Driver có thể dùng:

- Danh sách seed nodes.
- Cluster membership gossip hoặc endpoint discovery.
- Shard map/slot map version.
- Token map và routing key do protocol cung cấp.
- Event/redirect khi topology đổi.
- Read preference, region/DC locality và replica health.

### Lợi thế

- Có thể tránh một proxy hop trên mỗi request.
- Driver có thể lựa chọn node gần nhất hoặc replica phù hợp.
- Phân tán tải request trực tiếp tới nhiều node.
- Có thể kết hợp metadata cache với connection pooling theo node.

### Đánh đổi

- Ứng dụng/driver phải cập nhật topology đúng.
- Có thể cần kết nối mạng trực tiếp đến nhiều database nodes.
- Mỗi phiên bản driver phải tương thích protocol, auth và routing rules.
- Số kết nối có thể tăng theo số application instances × nodes.
- Tải metadata/refresh có thể tạo **thundering herd** nếu tất cả client đồng loạt refresh.

**Client-side routing không có nghĩa tự viết bộ định tuyến trong business code.** Khi database có driver chính thức hiểu topology, hãy để driver quản lý metadata, retry và node selection theo khả năng của nó.

## 7. Ví dụ Redis Cluster: client theo hash slot và redirect

Redis Cluster là ví dụ điển hình cho client cần hiểu routing theo **hash slots**. Hệ sử dụng **16.384 slots logic** cho phân mảnh key. Mỗi slot được gán cho một primary/shard, và slot ownership có thể thay đổi trong quá trình rebalance.

Ví dụ khái niệm:

~~~text
Key:
  order:1001

Redis Cluster slot:
  slot = CRC16(key hoặc hash tag theo quy tắc Redis) mod 16384

Slot ownership:
  slot 9123 -> node B

Client:
  gửi GET order:1001 đến node B
~~~

**Hash tag** trong Redis Cluster cho phép nhiều key dùng một đoạn nằm trong ngoặc nhọn để tính slot:

~~~redis
SET order:{order-1001}:status PENDING
SET order:{order-1001}:owner shop-a
~~~

Trong Redis Cluster, các key trên dùng cùng nội dung hash tag **order-1001**, nên có cùng slot theo quy tắc sản phẩm. Điều này có thể hữu ích cho một số multi-key operations yêu cầu cùng slot, nhưng **cùng slot không tự bảo đảm toàn bộ workflow nhiều bước có transaction và rollback nghiệp vụ**.

### MOVED

Nếu client gửi request tới node không còn sở hữu slot, node có thể trả **MOVED** kèm endpoint đích. Client nên cập nhật slot map và retry theo cơ chế driver.

### ASK

Trong quá trình **migrating/importing slot**, Redis Cluster có thể trả **ASK** để chuyển hướng một thao tác trong giai đoạn di chuyển. Đây là tín hiệu chuyển hướng tạm thời, không đồng nghĩa client phải coi node đích là owner vĩnh viễn của slot.

**Không xử lý MOVED và ASK y hệt nhau bằng cách sửa slot map vĩnh viễn trong mọi trường hợp.** Dùng cluster-aware client để tuân thủ protocol hiện hành.

~~~text
Client cache: slot 9123 -> node A
Cluster thực: slot 9123 -> node B

Client -> A: GET key
A -> Client: MOVED 9123 B
Client refresh/retry -> B
~~~

Trong các lệnh ghi không idempotent, việc redirect/retry phải dựa trên **loại lỗi có chắc chắn chưa thực thi hay không**. Timeout sau khi đã gửi lệnh khác với một redirect rõ ràng trước khi lệnh được xử lý.

## 8. Tại sao tự dùng modulo số node là một anti-pattern?

Một đoạn mã hấp dẫn:

~~~java
// Chỉ minh họa cách làm dễ sai; KHÔNG dùng để route một DB cluster thật.
int nodeIndex = Math.floorMod(orderId.hashCode(), servers.size());
String node = servers.get(nodeIndex);
~~~

Vấn đề:

1. Khi số node từ 3 thành 4, nhiều key đổi node dù không có quy trình chuyển dữ liệu.
2. Danh sách node khác thứ tự giữa các application instances có thể dẫn tới **routing inconsistency**.
3. Hash Java không đồng nghĩa với hash/encoding chính thức của database.
4. Một node có thể chứa **nhiều shards**; node hiện tại không phải đơn vị phân mảnh bền vững.
5. Một shard có nhiều replicas, cần chọn primary/quorum theo operation.
6. Không có metadata version, redirect, migration hoặc failover logic.

Nếu ứng dụng tự quản lý sharding thật sự, nên xây một lớp **logical partition ID → placement metadata có version**, cùng kế hoạch chuyển dữ liệu và cập nhật routing. Không dùng chỉ số trong danh sách địa chỉ như định danh dữ liệu.

## 9. Routing tại proxy: một địa chỉ logic cho ứng dụng

Thay vì để mỗi ứng dụng hiểu shards, ta đặt proxy/router trước các node:

~~~mermaid
flowchart LR
    A["App instance A"] --> P["Routing Proxy"]
    B["App instance B"] --> P
    C["Worker / Batch"] --> P
    P --> S1["Shard S1"]
    P --> S2["Shard S2"]
    P --> S3["Shard S3"]
~~~

Ứng dụng chỉ cần biết **endpoint của proxy**, còn proxy:

- Xác thực/thiết lập connection backend theo cơ chế hỗ trợ.
- Lấy shard key từ request hoặc protocol.
- Tra shard map và placement.
- Chọn replica phù hợp với read/write policy.
- Forward request và response.
- Xử lý một phần redirect/retry/topology changes.
- Thu thập metrics và tracing ở điểm tập trung.

### Lợi thế

- Ít thông tin topology phải lộ cho application hosts.
- Dễ thay backend nodes, thêm shards hoặc thay driver trong một số kiến trúc.
- Có một nơi thực thi network policy, rate limit hoặc quan sát traffic.
- Thuận tiện trong môi trường ứng dụng không kết nối trực tiếp mọi data node.

### Đánh đổi

- Thêm **network hop** và CPU/memory/protocol processing.
- Proxy có thể trở thành bottleneck hoặc failure domain nếu không được nhân bản đúng.
- Connection pooling ở proxy có thể gây queueing/head-of-line blocking.
- Đường logic có thể khó truy vết nếu proxy ẩn metadata và lỗi backend.
- Dùng proxy generic TCP không có nghĩa proxy hiểu shard key và tự route đúng.

**Proxy định tuyến phải hiểu đủ giao thức hoặc nhận routing hint đáng tin**. Một load balancer chỉ round-robin TCP connection không tự giải quyết key-to-shard placement.

## 10. MongoDB mongos: router chuyên dụng trong sharded cluster

Trong MongoDB sharded cluster, **mongos** là tiến trình query router; ứng dụng thường kết nối tới mongos thay vì trực tiếp tự tìm node chứa từng document. Metadata sharding được quản lý qua thành phần cấu hình của cluster.

Luồng khái quát:

~~~text
Application
    |
    v
  mongos
    |
    +-- metadata/chunk ranges
    |
    +-- targeted query -> shard thích hợp
    |
    +-- query thiếu shard key -> có thể broadcast nhiều shards
~~~

Ví dụ document:

~~~javascript
{
  tenantId: "shop-a",
  orderId: "order-1001",
  status: "PAID",
  createdAt: ISODate("2026-11-14T09:00:00Z")
}
~~~

Giả sử collection được shard theo một shard key chứa **tenantId**. Query:

~~~javascript
db.orders.find({
  tenantId: "shop-a",
  orderId: "order-1001"
});
~~~

có thể có đủ thông tin để mongos **target shard** theo mapping. Ngược lại:

~~~javascript
db.orders.find({ status: "PAID" });
~~~

có thể phải gửi tới nhiều shards nếu planner không thể thu hẹp phạm vi dựa trên shard key và metadata.

### Những điều cần ghi nhớ

- **mongos không phải một shard chứa toàn bộ dữ liệu**; nó định tuyến và phối hợp yêu cầu.
- Có thể triển khai nhiều mongos instances để tránh một router đơn làm điểm lỗi.
- **Shard key**, index, query shape và metadata quyết định targeted hay scatter–gather.
- Một shard có thể là **replica set** với primary/secondary; routing logic và replica selection là những tầng riêng.
- Khi chunks/ranges được di chuyển, mongos phải cập nhật metadata hoặc xử lý trạng thái routing đã cũ.
- Transaction và aggregation nhiều shards có cơ chế phối hợp riêng, không được coi là một find targeted đơn giản.

Ví dụ trên mô tả logic; khả năng target chính xác phụ thuộc shard key thật, query predicates, index, version và planner.

## 11. Proxy gateway tự xây khác router gốc của database

Một ứng dụng microservices có thể tạo **Data Access Gateway**:

~~~text
Order API
  -> Data Gateway
      -> Database Router/Driver
          -> Shard
~~~

Gateway này có thể bổ sung:

- Chuẩn hóa định danh tenant/order và permission.
- Hạn chế query không có shard key.
- Rate limiting theo tenant.
- Theo dõi latency và lỗi theo logical shard.
- Cache một số lookup hoặc mapping.
- Routing tới vùng dữ liệu theo data residency policy.

Nhưng gateway **không nên tự giả định là nguồn truth của placement** nếu database đã có routing authority riêng. Nó có thể giữ cache về home region, còn driver/mongos vẫn xử lý vị trí shard và failover bên trong vùng ấy.

Hai cấp routing là hợp lệ khi **trách nhiệm được tách rõ**. Ví dụ gateway quyết định tenant thuộc cluster nào; mongos quyết định collection chunk thuộc shard nào.

## 12. Coordinator tại node dữ liệu

Trong mô hình **coordinator-side routing**, request được gửi tới một node trong cluster; node đó phối hợp các replica/shard:

~~~mermaid
sequenceDiagram
    participant App as Application
    participant Co as Coordinator Node
    participant A as Replica A
    participant B as Replica B
    participant C as Replica C
    App->>Co: Read/Write partition K
    par Liên hệ replicas
        Co->>A: Request
        Co->>B: Request
        Co->>C: Request
    end
    A-->>Co: Response/version
    B-->>Co: Response/version
    C-->>Co: Response/version
    Note over Co: Chọn result theo consistency policy
    Co-->>App: Result
~~~

Coordinator có thể là node client kết nối, không nhất thiết chứa trực tiếp partition đó và **không nhất thiết có quyền leader lâu dài**. Nó biết hoặc có thể tra replica placement theo metadata/membership của cluster.

Định tuyến qua coordinator có thể đơn giản hóa client, nhưng thêm một hop giữa coordinator và replica thích hợp nếu client chọn node không gần data.

## 13. Cassandra: coordinator và token-aware driver

Trong Cassandra, mỗi node có thể nhận request làm coordinator. Với partition key, token map và replication strategy, coordinator có thể biết các replicas chịu trách nhiệm. Driver hiện đại còn có thể **token-aware**, ưu tiên kết nối tới node chứa replica phù hợp khi có đủ thông tin về partition key và topology.

Ví dụ bảng:

~~~sql
CREATE TABLE orders_by_id (
  tenant_id text,
  order_id text,
  status text,
  total_minor bigint,
  PRIMARY KEY ((tenant_id, order_id))
);
~~~

Với partition key ghép **(tenant_id, order_id)**, yêu cầu:

~~~sql
SELECT status, total_minor
FROM orders_by_id
WHERE tenant_id = 'shop-a'
  AND order_id = 'order-1001';
~~~

cho driver/coordinator đủ giá trị partition key để định vị replicas theo protocol.

### Token-aware routing làm được gì?

- Driver hiểu token của partition khi có **partition key được bind đầy đủ và metadata hợp lệ**.
- Có thể ưu tiên replica trong **local datacenter**, giảm hop và hỗ trợ locality.
- Nếu node được chọn không thể phục vụ, policy retry/failover chọn node phù hợp khác.

### Những điều không được suy ra

- Token-aware **không biến client thành leader**.
- Chọn một replica phù hợp không đồng nghĩa consistency level tự thành **ONE**; coordinator vẫn phải đáp ứng ngưỡng được yêu cầu.
- Driver **không có partition key đầy đủ** cho mọi query; câu lệnh và schema ảnh hưởng khả năng routing.
- **LOCAL_QUORUM** là chính sách số/tập replicas tham gia, không phải tên một thuật toán định tuyến client.
- Ordinary CQL reads/writes và **LWT** có ngữ nghĩa khác nhau; routing không tự bảo vệ bất biến read–modify–write.

Đối với Java driver, nên dùng **prepared statements và typed bound values** để driver suy ra routing key theo khả năng hỗ trợ. Không tự tính Murmur3 token bằng cách hash chuỗi hiển thị đơn giản nếu không làm đúng encoding của Cassandra.

## 14. Một read tại Cassandra có thể đi qua hai tầng

~~~text
Java Driver
  |
  | biết token map và local DC
  v
Node A (được chọn làm coordinator)
  |
  | consistency level QUORUM
  +----> Replica A
  +----> Replica B
  +----> Replica C (có thể được liên hệ tùy yêu cầu)
  |
  v
Tổng hợp đủ phản hồi theo protocol
  |
  v
Trả application
~~~

Driver đã **định tuyến có ý thức vị trí** mà server vẫn làm **coordinator**. Vì thế câu hỏi “client-side hay coordinator-side?” đôi khi có đáp án **cả hai, ở hai tầng khác nhau**.

Phân tích performance phải hỏi:

- Driver chọn coordinator nào?
- Coordinator có nằm trong local DC không?
- Replica nào chứa token range?
- Consistency level cần bao nhiêu phản hồi?
- Coordinator có phải chuyển tiếp qua WAN không?
- Hot partition/compaction/repair đang ảnh hưởng replica nào?

## 15. Nút điều phối trong hệ search phân tán

Một truy vấn tìm kiếm có thể cần truy cập **nhiều shards**. Các hệ search phân tán thường có khái niệm coordinating node nhận query, gửi tới shards thích hợp rồi hợp nhất kết quả.

~~~mermaid
flowchart TD
    Q["Search query"] --> CO["Coordinating node"]
    CO --> A["Shard A: tìm top results"]
    CO --> B["Shard B: tìm top results"]
    CO --> C["Shard C: tìm top results"]
    A --> M["Merge/rank/fetch"]
    B --> M
    C --> M
    M --> R["Top K cuối cùng"]
~~~

Trong họ Elasticsearch/OpenSearch, một search có thể gồm giai đoạn **query** trên các shards và **fetch** documents liên quan, với cơ chế phân bổ shard copies và coordinator. Chi tiết tùy API/phiên bản.

**Định tuyến một query tới tất cả shard cần thiết khác với replication:** shard A và B có thể chứa **hai phân đoạn dữ liệu khác nhau**; replica A1/A2 chứa những bản sao của **cùng shard A**.

Nếu truy vấn lọc được routing key, có thể giảm phạm vi shards; nếu không, hệ phải fan-out. Nhưng không nên tự lạm dụng custom routing làm dữ liệu không thể truy vấn đúng khi client quên cung cấp cùng routing key.

## 16. Ba mô hình so sánh trực tiếp

| Tiêu chí | Client-side routing | Proxy/router | Coordinator-side routing |
|---|---|---|---|
| Ai chọn đích? | Driver/SDK | Lớp trung gian | Node dữ liệu nhận request |
| Client biết topology? | Thường biết một phần | Có thể không | Có thể chỉ biết seed/contact nodes |
| Extra hop | Có thể ít | Có proxy hop | Có thể có coordinator-to-replica hop |
| Connection count tại app | Có thể kết nối nhiều nodes | Thường ít endpoints hơn | Tùy driver/contact nodes |
| Cache shard map | Thường tại driver | Tại proxy | Trong cluster node/coordinator |
| Topology change | Driver refresh/redirect | Proxy refresh và forward | Coordinator refresh membership/metadata |
| Tập trung auth/policy | Tại SDK/service | Dễ thêm tập trung | Theo database protocol |
| Bottleneck | App connections/metadata | Proxy CPU/queues | Coordinator hot nodes |
| Ví dụ khái niệm | Redis Cluster-aware SDK | mongos/router gateway | Cassandra coordinator, search node |

Đây là **vai trò**, không phải hệ thống phải chọn độc quyền một cột. MongoDB mongos là router chuyên dụng có thể phối hợp query nhiều shard; Cassandra token-aware driver và coordinator cùng tham gia routing.

## 17. Truy vấn một shard và truy vấn nhiều shard

### Targeted query

~~~text
GET order-1001 với shard key đầy đủ
  -> một shard logic
  -> replica phù hợp
  -> response
~~~

Chi phí gần đúng gồm lookup routing, network tới shard, thực thi query và response.

### Scatter–gather

~~~text
GET tất cả orders có status=PAID
  -> shard S1
  -> shard S2
  -> shard S3
  -> merge/filter/sort
  -> response
~~~

Một proxy hay coordinator có thể fan-out song song; thời gian hoàn tất thường bị ảnh hưởng bởi shard chậm nhất cần thiết, đồng thời tiêu thụ tài nguyên trên nhiều shard.

Nếu có **P shards** và mỗi query fan-out toàn P, chi phí tổng thể có thể tăng đáng kể khi P lớn. Không thể coi query chỉ dùng một HTTP call nên là truy vấn rẻ.

### Đếm đúng số shard bị truy cập

Với workload thực, ghi nhận:

~~~text
queryName = searchPaidOrders
targetedShards = 12
totalShards = 12
scatterGather = true
latencyP99 = ...
~~~

Nếu endpoint theo ID nhưng vẫn fan-out, có thể shard key, index hoặc routing hint đang thiếu.

## 18. Scatter–gather và sort/pagination

Một query:

~~~text
SELECT orders
WHERE status = PAID
ORDER BY createdAt DESC
LIMIT 20
~~~

trên nhiều shards không thể luôn lấy 20 bản tùy ý của mỗi shard rồi nối lại đơn giản. Coordinator phải tuân thủ cơ chế **top-k merge** và thứ tự sort toàn cục.

Vấn đề tăng khi pagination sâu:

- Mỗi shard có thể cần tìm nhiều candidates.
- Coordinator giữ heap/buffer để merge.
- Nếu sort fields không có tie-breaker ổn định, cùng một record có thể xuất hiện hoặc bị bỏ qua giữa các trang.
- Nếu data thay đổi giữa hai page requests, việc dùng offset có thể tạo duplicates/skips.
- Cursor/search-after/continuation token hoặc snapshot/pit semantics có thể phù hợp hơn tùy engine.

Một routing layer có thể đưa request tới đúng shards nhưng **không tự bảo đảm pagination nhất quán qua nhiều shard**. Cần đặc tả snapshot, độ mới và stable sort.

## 19. Định tuyến dựa vào tenant và quyền truy cập

Trong SaaS nhiều tenant, tenantId thường là thành phần quan trọng của shard key:

~~~text
tenantId=shop-a -> cluster-east / shard S2
tenantId=shop-b -> cluster-west / shard S7
~~~

Điều này hỗ trợ data locality, giới hạn tải và có thể hỗ trợ data residency. Nhưng:

1. **TenantId phải được xác thực**, không tin thẳng query parameter do client bên ngoài cung cấp.
2. Nếu proxy cache mapping tenant→cluster, cache phải được phân tách đúng tenant và policy.
3. Không đưa dữ liệu nhạy cảm vào routing logs/metrics một cách không kiểm soát.
4. Nếu tenant chuyển vùng, cập nhật mapping cần phối hợp với authorization và cutover.
5. Tenant lớn có thể thành hotspot khi toàn bộ dữ liệu bám một partition; cần chiến lược subpartition hợp lý.

**Routing đúng shard chưa chứng minh người gọi được phép đọc dữ liệu đó.** Kiểm tra authorization vẫn cần ở nơi có thẩm quyền theo kiến trúc bảo mật.

## 20. Shard key thiếu, NULL hoặc không đúng kiểu

Một yêu cầu:

~~~json
{
  "orderId": "order-1001"
}
~~~

nhưng collection được shard theo **tenantId + orderId**. Nếu tenantId thiếu, hệ có thể:

- Từ chối request theo contract.
- Tra mapping bổ sung.
- Fan-out theo khả năng của database.
- Đưa dữ liệu vào partition mặc định/null nếu schema cho phép — tạo nguy cơ hotspot và sai tenant.

Đối với application API nhạy quyền, lựa chọn tốt thường là **validation fail-fast** khi routing identity không đủ. Không được âm thầm gán tenantId='default' cho mọi request thiếu.

### Canonicalization

Những biểu diễn tưởng như cùng key có thể hash khác:

~~~text
tenantId "Shop-A" vs "shop-a"
orderId dạng số 1001 vs chuỗi "1001"
Unicode dạng chuẩn hóa khác nhau
Byte encoding khác nhau
~~~

Với shard key, phải có quy tắc canonicalization/schema thống nhất giữa client, proxy và database; nếu không, cùng logical object có thể bị định tuyến vào hai nơi khác nhau trong những thiết kế tự quản lý.

## 21. Topology thay đổi: shard map cũ là chuyện bình thường

Một cluster đang chạy sẽ có:

- Thêm hoặc xóa node.
- Replica mới được tạo.
- Leader/primary thay vì failover.
- Shard split/merge.
- Di chuyển chunk/slot/partition range.
- Chuyển tenant từ cluster cũ sang cluster mới.

Router có thể cache:

~~~text
Topology version 41:
  key K -> shard S1 / node A
~~~

Trong khi nguồn thẩm quyền đã đổi:

~~~text
Topology version 42:
  key K -> shard S2 / node B
~~~

Một router tốt phải có cơ chế:

1. Phát hiện mapping không còn hợp lệ.
2. Refresh metadata hoặc nhận redirect hợp lệ.
3. Thử lại đúng đích với **retry budget**.
4. Tránh vòng lặp redirect hoặc stale topology vô hạn.
5. Phân biệt lỗi chắc chắn chưa xử lý với timeout **không rõ outcome**.

Không bắt buộc mọi mapping thay đổi đều được push ngay tới mọi client; cache + invalidation/redirect là một thiết kế hợp lệ nếu protocol xử lý stale an toàn.

## 22. Epoch/version của shard map giúp gì?

Đặt mỗi phiên bản mapping một số tăng đơn điệu:

~~~text
epoch 41: range R -> S1
epoch 42: range R -> S2
~~~

Một router gửi request với epoch 41 có thể bị từ chối hoặc chuyển hướng theo protocol. Điều này hỗ trợ tránh ghi nhầm vào owner đã hết quyền.

Nhưng **version ở client không tự bảo vệ mọi ghi**. Node đích phải kiểm tra quyền sở hữu hiện tại, route theo metadata có thẩm quyền hoặc dùng fencing đúng cơ chế.

### Ví dụ race khi di chuyển

~~~text
T1: Router A cache R -> S1.
T2: Cluster bắt đầu move R sang S2.
T3: Router B refresh và gửi write tới S2.
T4: Router A gửi write theo mapping cũ tới S1.
~~~

Nếu S1 và S2 đều nhận write tùy tiện mà không có quy tắc migration/ownership, dữ liệu có thể phân kỳ. Một protocol reshard phù hợp phải định nghĩa:

- Node nào đang owner.
- Ghi nào cần forward/reject/dual-write có kiểm soát.
- Khi nào đọc từ nguồn/đích.
- Khi nào được chuyển mapping chính thức.
- Làm sao xử lý ghi in-flight và rollback migration.

## 23. Resharding là chuyển dữ liệu và chuyển quyền

Một kế hoạch chuyển range R từ S1 sang S2 có thể gồm các giai đoạn:

~~~mermaid
flowchart TD
    A["Đánh dấu phạm vi cần chuyển"] --> B["Tạo bản dữ liệu ban đầu ở đích"]
    B --> C["Theo kịp delta/change log"]
    C --> D["Chặn hoặc phối hợp ghi in-flight"]
    D --> E["Chuyển quyền owner + tăng epoch"]
    E --> F["Refresh routes / redirect"]
    F --> G["Xác nhận dữ liệu và gỡ bản cũ khi an toàn"]
~~~

Đây là flow mô hình hóa; một số engine có protocol migration riêng và không diễn ra đúng thứ tự từng hộp trên.

Vấn đề cần giải:

- **Backfill** mất bao lâu?
- Ghi phát sinh trong khi copy được capture bằng cách nào?
- Có cần source snapshot và change stream/log position?
- Ranh giới cutover có atomic theo key/range không?
- Router cũ phải được xử lý ra sao?
- Nếu node đích lỗi giữa migration, hệ có đường rollback nào?
- Nếu xóa nguồn quá sớm, data loss có thể xảy ra?

**Đổi config router không tự di chuyển dữ liệu.** **Di chuyển dữ liệu không tự chuyển quyền ghi.** Hai thao tác phải được phối hợp theo protocol.

## 24. Không dùng dual-write tự phát để thay protocol migration

Một chiến thuật nghe có vẻ tiện:

~~~text
Trong migration:
  client ghi đồng thời vào S1 và S2.
~~~

Rủi ro:

- Ghi S1 thành công, S2 timeout; client không biết trạng thái.
- Hai write đến S1/S2 theo thứ tự khác nhau.
- Retry tạo side effect kép với increment/list append.
- Một bản được xóa trong khi bản kia được ghi lại.
- Read từ hai nơi có thể trả hai trạng thái không cùng version.

Nếu cần dual-write, nó phải thuộc **quy trình migration được thiết kế** với log/sequence, idempotency key, target version, reconcile và rollback. Nhiều trường hợp tốt hơn là dùng change stream/backfill + cutover có kiểm soát hoặc cơ chế reshard chính thức của database.

Không tự triển khai một proxy ghi hai shard chỉ vì “gửi hai nơi sẽ an toàn hơn”.

## 25. Failover khác resharding

**Failover** thường thay **node/leader phục vụ shard cũ**:

~~~text
Logical shard S1:
  trước: primary node A
  sau:   primary node B
~~~

**Resharding** thay **ranh giới key/partition hoặc owner shard logic**:

~~~text
Range R:
  trước: shard S1
  sau:   shard S2
~~~

Router cần biết sự khác biệt:

- Với failover, cùng key có thể vẫn thuộc S1, nhưng replica selection phải cập nhật.
- Với reshard, key-to-shard mapping thay đổi; cache shard map có thể stale.
- Hai quá trình có thể xảy ra cùng lúc, làm lỗi định tuyến khó hơn.

Không được suy rằng **DNS đổi IP** là mọi routing problem đã được giải quyết; cả logical partition ownership và role của replicas đều phải đúng.

## 26. Retry, redirect và kết quả chưa rõ

Một request có thể thất bại theo nhiều cách:

| Tín hiệu | Có biết mutation đã áp dụng không? | Hướng xử lý |
|---|---|---|
| Router trả shard-moved rõ trước khi thực hiện | Thường có ngữ nghĩa chưa thực thi theo protocol cụ thể | Refresh route và retry đúng quy tắc |
| Node báo không còn leader/owner | Tùy mã lỗi và protocol | Refresh epoch/leader, retry có giới hạn |
| Connection refused trước khi gửi bytes | Có thể biết chưa gửi, tùy tầng transport | Reconnect/chọn node khác |
| Timeout sau khi request đã gửi | **UNKNOWN** | Verify bằng logical ID, retry idempotent |
| Conditional conflict | Thao tác không được áp dụng theo bảo đảm điều kiện | Đọc lại trạng thái, không retry mù |
| Duplicate ID cùng payload | Có thể là retry của thành công cũ | Trả/truy vấn kết quả đã có |
| Duplicate ID khác payload | Xung đột ý định | Từ chối hoặc điều tra |

**MOVED/ASK không giống một socket timeout**. Ở timeout sau khi write đã đi tới server, client không được giả định chưa có side effect.

Ví dụ đặt hàng:

~~~text
operationId = "checkout-req-9001"
orderId = "order-9001"

Client gửi CreateOrder.
Shard leader commit.
Response bị mất.
Client refresh route và gửi lại.
~~~

Nếu thao tác **create-only với unique logical key** và xử lý idempotency đúng, retry có thể nhận lại kết quả cũ. Nếu client tạo orderId mới hoặc làm increment không có dedup, việc route đúng shard **không ngăn duplicate order**.

## 27. Định tuyến không tự quyết định consistency level

Giả sử driver biết chính xác shard S1 và gửi read tới replica gần nhất. Câu hỏi còn lại là replica ấy có đủ điều kiện trả dữ liệu theo hợp đồng không?

- **Leader/primary read:** cần xem protocol, quyền leader và mức read concern.
- **Follower/secondary read:** có thể stale, session token hoặc snapshot constraint.
- **Quorum read:** coordinator phải thu đủ replica và chọn result đúng policy.
- **Linearizable read:** cần cơ chế bảo vệ real-time order phù hợp engine.
- **Transaction snapshot:** nhiều operation có thể cần một snapshot chung.

**Routing đúng vị trí** là cần thiết nhưng chưa đủ để chứng minh **đọc giá trị mới nhất**. Một targeted read từ đúng shard nhưng chọn follower trễ vẫn có thể stale.

## 28. Cross-shard transaction và điều phối ghi

Order chứa hai sản phẩm ở hai shards:

~~~text
Inventory BOOK-01 -> Shard S1
Inventory PEN-02  -> Shard S3
Order order-9001  -> Shard S2
~~~

Một checkout muốn giữ cả hai SKU và tạo order. Dù router đưa mỗi write tới đúng shard, hệ vẫn phải giải:

~~~text
Giữ BOOK-01 thành công.
Giữ PEN-02 thất bại.
Tạo order chưa thực hiện.
~~~

Có thể cần:

- **Multi-shard transaction** nếu database hỗ trợ và giới hạn phù hợp.
- **Reservation/Saga** với bước bù có điều kiện.
- **Đổi aggregate/shard key** để những dữ liệu cần atomicity thật sự nằm cùng ranh giới.
- **Outbox/inbox** để đồng bộ read models khi có side effects liên dịch vụ.

Coordinator của transaction có thể khác router của query. **Biết nơi chứa từng key không tự tạo atomic commit trên nhiều shard.**

Nếu database hỗ trợ distributed transaction, cần cân nhắc lock, conflict, coordinator failure, timeout, recovery và chi phí nhiều mạng; không coi transaction nhiều shard là miễn phí.

## 29. Multi-key operations và cùng slot/shard

Trong một số engine, thao tác nhiều key có giới hạn **phải cùng partition/slot** để được xử lý trong một phạm vi.

Ví dụ Redis Cluster dùng hash tag:

~~~redis
SET balance:{wallet-9001}:available 100
SET balance:{wallet-9001}:reserved 0
~~~

Hai key trên có cùng hash tag, nên cùng slot. Điều đó giúp một số lệnh/script multi-key của Redis Cluster đáp ứng ràng buộc routing.

Nhưng:

- **Cùng slot** chỉ là điều kiện routing quan trọng, không tự tạo transaction business qua nhiều lệnh riêng.
- Cùng slot có thể gây **hotspot** nếu gom mọi dữ liệu lớn vào một hash tag.
- Key cùng tenant không nhất thiết cần ở cùng slot nếu access patterns không dùng multi-key operations.
- Với database khác, điều kiện đồng vị trí và transaction scope có thể dựa trên partition key hoặc schema khác.

Không dùng mẹo hash tag để thay thế việc định nghĩa bất biến.

## 30. Scatter–gather và transaction là hai bài toán khác nhau

**Scatter–gather read**:

~~~text
Query status=PAID
  -> shard S1: results
  -> shard S2: results
  -> shard S3: results
  -> merge
~~~

Có thể trả những result đã được đọc ở các thời điểm khác nhau nếu không có snapshot semantics tương ứng.

**Distributed transaction**:

~~~text
Update order in S1
Update inventory in S2
Commit all-or-nothing theo transaction protocol
~~~

Đây là yêu cầu khác. Một coordinator có thể thực hiện fan-out read giỏi mà không cung cấp transaction xuyên shard; ngược lại, database có transaction nhiều shards vẫn có thể có query broadcast đắt.

Nên ghi rõ: query **single-shard targeted**, **multi-shard read**, **multi-shard write** hay **cross-shard transaction**. Mỗi loại có performance và correctness contract riêng.

## 31. Kết nối và connection pooling

Client-side routing có thể mở pool tới nhiều nodes:

~~~text
100 application instances
x 20 data nodes
x tối đa 10 connections/node
= khả năng xuất hiện nhiều nghìn connections
~~~

Số ở trên là ví dụ tính cấu hình, không phải dự báo chính xác số connections mở thực tế.

Với proxy:

~~~text
Applications -> vài proxy endpoints
Proxy -> nhiều backend pooled connections
~~~

Proxy có thể giảm số connection backend lặp lại từ hàng trăm ứng dụng, nhưng cũng có thể làm **queue congestion** nếu pooling hoặc concurrency limit không cân đối.

Các chỉ số quan trọng:

- Active/idle connections theo node.
- Connection establishment và TLS handshake rate.
- Time spent waiting in pool.
- In-flight requests/queue length.
- Retries sau timeout.
- Per-shard p95/p99 latency.
- Proxy CPU, memory và saturation.

Không nên chỉ tăng pool size để chữa query chậm vì thiếu shard key.

## 32. Load balancing tại các tầng routing

Cần phân biệt:

1. **L7 HTTP load balancing** giữa các API instances.
2. **Routing proxy** hiểu shard key và database protocol.
3. **Replica selection** giữa các bản sao của một shard.
4. **Coordinator distribution** để các node không bị dồn request.

Nếu một TCP load balancer chỉ gửi connection tới node ngẫu nhiên, nó không tự biết key nào thuộc shard nào. Điều này có thể vẫn dùng được **nếu server nhận request là coordinator biết forward**; không dùng được nếu endpoint chỉ nhận dữ liệu mà nó sở hữu.

Vì vậy một L4 load balancer trước Cassandra nodes có thể hợp lý cho một số workload/môi trường, nhưng có thể làm mất lợi thế token-aware driver hoặc tăng hop. Với Redis Cluster, một proxy cần hiểu cluster protocol hoặc cluster-aware client phải theo redirect — generic round-robin không thay thế được điều đó.

## 33. Fault domain của proxy và coordinator

Một proxy duy nhất:

~~~text
All apps -> proxy-1 -> all shards
~~~

có thể là **single point of failure**, dù các shards đều có ba replicas.

Thiết kế thường cần:

- Nhiều proxy instances.
- Health checks và chuyển tuyến đúng.
- Metadata cache/lookup bền vững ở mức cần thiết.
- Giới hạn request và backpressure.
- Graceful draining khi deploy.
- Circuit breakers/retry budgets tránh khuếch đại lỗi.
- Giám sát toàn bộ proxy-to-shard path.

Với coordinator:

- Node bất kỳ có thể tiếp nhận quá nhiều traffic.
- Một coordinator bị overload có thể làm shard khỏe trông như lỗi.
- Cross-shard query khiến coordinator tốn CPU/memory merge.
- Connection locality không phù hợp tạo thêm inter-node traffic.

**Cụm có nhiều data nodes không có nghĩa routing layer tự động không có điểm nghẽn.**

## 34. Retry storm và thundering herd khi topology đổi

Khi node A rời cluster:

~~~text
10.000 client connections cùng báo lỗi.
Tất cả cùng refresh metadata.
Tất cả cùng retry đến leader mới.
Leader mới lại quá tải.
~~~

Những nguyên tắc giảm tác động:

1. **Exponential backoff và jitter** cho retry có thể trì hoãn.
2. **Retry budget** giới hạn tổng lượng request thử lại.
3. **Topology refresh có rate limit/coalescing**, tránh mỗi request đều tải metadata.
4. **Connection pooling và circuit breaker** tránh tiếp tục gửi vào node hỏng.
5. **Deadline propagation** từ API đến proxy và database.
6. **Idempotency** cho những write có thể gửi lặp.
7. **Load shedding/backpressure** khi cluster không thể đáp ứng SLO.

Nhiều retry không có kiểm soát có thể làm failover vốn tạm thời thành outage kéo dài. Không đánh đồng “retry nhiều” với “khả năng phục hồi tốt”.

## 35. Deadline và cancellation xuyên nhiều hop

Giả sử API có timeout 300 ms:

~~~text
API -> Proxy -> Coordinator -> Replica
~~~

Nếu mỗi tầng tự chờ 300 ms, tổng latency và tài nguyên có thể vượt ngân sách. Nên truyền **deadline/remaining budget** hoặc timeout hợp lý theo từng tầng.

Khi client hủy một read:

- Proxy nên ngừng công việc không cần thiết khi protocol hỗ trợ.
- Coordinator có thể còn những RPC nội bộ đang chạy; cần resource control.
- Một write đã commit **không tự rollback vì HTTP request bị hủy**.

Đây là lý do cần phân biệt **cancellation ở tầng transport** với **hủy thao tác nghiệp vụ**. Một CreateOrder timeout ở proxy vẫn có thể đã commit ở shard.

## 36. Routing và bảo mật mạng

**Client-side routing** có thể cần app hosts được kết nối tới nhiều data nodes. Trong môi trường zero-trust hoặc mạng nhiều vùng, mở rộng firewall rules và certificates không phải chuyện nhỏ.

**Proxy-side routing** có thể giới hạn database nodes chỉ nhận kết nối từ proxy. Nhưng proxy nắm quyền mạnh nên cần:

- TLS/mTLS và xác minh danh tính backend.
- Authn/authz theo user/tenant phù hợp, không chỉ tin rằng caller ở mạng nội bộ.
- Không chấp nhận routing hint có thể giúp bypass tenant isolation.
- Hạn chế secret logging và SQL/CQL/query payload nhạy cảm.
- Rotation credentials, certificate và endpoint.
- Audit các thao tác hành chính/migration.

**Routing isolation không tương đương authorization.** Request có thể được chuyển chính xác đến shard chứa dữ liệu người khác nhưng vẫn phải bị từ chối.

## 37. Tenant migration giữa clusters

Ví dụ tenant shop-a chuyển từ Cluster East sang Cluster West:

~~~text
Trước:
  tenant shop-a -> east / shard E3

Sau:
  tenant shop-a -> west / shard W2
~~~

Một kế hoạch cần xác định:

1. Ai là nguồn truth của **tenant→cluster mapping**?
2. Có backfill snapshot và change-log catch-up không?
3. Trong migration, **writes** đi một nơi hay được phối hợp?
4. Dữ liệu nào được đối soát: count, checksum, versions, invariants?
5. Khi cutover, mapping version tăng và routers refresh thế nào?
6. Các request in-flight tại cluster cũ được reject/forward/dedup ra sao?
7. Có thể rollback về cụm cũ không và trong điều kiện nào?
8. Data residency, encryption keys và quyền truy cập có thay đổi không?

Nếu routing proxy lưu mapping cũ trong cache, nó có thể tiếp tục gửi request tới East sau cutover. **Chỉ đổi DNS sang West** chưa giải quyết mapping lưu ở các SDKs, workers hoặc cache khác.

## 38. Hot shard và hot key

Một shard key hợp lý về phân bố dữ liệu vẫn có thể tạo hotspot:

~~~text
tenantId = very-large-tenant
  chiếm 60% request toàn cluster
~~~

Hoặc:

~~~text
counter:global-views
  chỉ một key nhưng rất nhiều increments
~~~

Khi p99 tăng, phải phân biệt:

- Router phân bố request sai?
- Một shard chứa quá nhiều keys?
- Một key bị tranh chấp quá mạnh?
- Query thiếu shard key dẫn tới fan-out?
- Một replica/leader có CPU hoặc disk chậm?
- Cross-region routing đang làm tăng RTT?
- Coordinator nóng do aggregation?

Các hướng xử lý gồm **split tenant/bucket, salted partition key phù hợp, sharded counters, cache/read model hoặc đổi access pattern**. Nhưng việc salt key có thể làm queries phải fan-out nhiều bucket; cần thiết kế cách tổng hợp, idempotency và consistency.

## 39. Routing key và quy tắc không thể đổi tùy tiện

Một shard key không đơn thuần là một index tăng tốc. Nó ảnh hưởng:

- Physical placement.
- Query targeting.
- Uniqueness scope.
- Khả năng đặt dữ liệu liên quan cùng shard.
- Cross-shard transaction cost.
- Khả năng mở rộng khi tenant hoặc partition nóng.
- Cách thực hiện reshard/tenant migration.

Ví dụ chọn **createdAt** làm routing key cho order tăng đều theo thời gian có thể khiến write mới dồn vào range cuối. Chọn **hash(orderId)** phân bố write tốt hơn nhưng query theo khoảng thời gian có thể phải đi nhiều shards.

Một chiến lược cân bằng:

~~~text
Primary access: GET order theo tenantId + orderId
Secondary access: list order theo customer + thời gian

Source:
  shard theo khóa phục vụ write/lookup chính

Read model:
  orders_by_customer và time bucket phục vụ listing
~~~

Denormalization/read model tăng công việc đồng bộ; phải có version/event ID và reconciliation. Đừng thay đổi shard key chỉ vì một dashboard query chậm nếu workload chủ đạo yêu cầu khác.

## 40. Query planning và routing hints

Một số engine/driver cho phép ứng dụng cung cấp **routing hint** hoặc shard key để tránh broadcast. Hint giúp routing nhanh nhưng phải:

1. Phù hợp schema và protocol.
2. Được xác minh với quyền truy cập.
3. Không mâu thuẫn với filter thực tế.
4. Chịu được topology changes.
5. Không thay thế việc kiểm tra điều kiện ghi tại nguồn.

Nếu một search index sử dụng custom routing theo customerId, ứng dụng phải dùng cùng routing khi **ghi, cập nhật, xóa và các truy vấn muốn target**. Nếu router gửi delete tới shard khác với nơi document được index, kết quả có thể là document không bị xóa như mong muốn.

Khi nghi ngờ, cần xem query plan/profile và thực tế shard IDs được truy cập, không chỉ dựa vào code tưởng đã truyền routing key.

## 41. Observability: phải nhìn thấy hop và shard nào chậm

Một trace hữu ích:

~~~text
HTTP GET /orders/order-1001
  traceId: t-001
  tenantId: shop-a

  DataAccessGateway  3 ms
    shardMap v42
    targetShard S2

  DatabaseRouter  2 ms
    route S2 -> node-b

  Node-b           8 ms
    query execution 5 ms

  Total response  17 ms
~~~

Các con số chỉ minh họa.

Nên phân biệt:

| Metric/field | Ý nghĩa |
|---|---|
| logicalShard / partition token | Phạm vi dữ liệu được chọn |
| topologyVersion / epoch | Router đang dùng mapping nào |
| targetNode / replicaRole | Node nào thực sự phục vụ |
| routingDecisionLatency | Mất bao lâu để xác định đích |
| redirectCount / MOVED / ASK | Có mapping stale hoặc migration không |
| scatterGatherFanout | Một query chạm bao nhiêu shards |
| coordinatorQueueTime | Request bị chờ ở node nhận không |
| poolWaitTime | Thiếu kết nối hay backend chậm |
| backendLatency | Thời gian thực thi trên shard |
| crossRegionHopCount | Request có đi qua WAN không |
| retryCount / outcomeUnknown | Có hiệu ứng lặp hoặc response chưa rõ không |
| slowestShardLatency | Shard nào quyết định p99 của query |
| authTenantScope | Filter/routing có đúng tenant đã xác thực |

Không đưa tenantId có cardinality cực lớn hoặc PII tùy tiện vào metric labels. Trace có thể mang ID đã kiểm soát và sampling phù hợp.

## 42. Chẩn đoán lỗi: “Dữ liệu có nhưng query không tìm thấy”

Khi có triệu chứng:

~~~text
GET order-1001 trả NOT_FOUND
trong khi một job khác vừa ghi order-1001 thành công.
~~~

Điều tra theo thứ tự:

1. **Logical identity** có trùng tenantId/orderId không?
2. Lần ghi có **ACK commit** thật hay chỉ accepted/timeout?
3. Query có gửi **đủ shard key** không?
4. Router/driver dùng **shard map version** nào?
5. Có **tenant migration/reshard** đang diễn ra không?
6. Read tới primary/replica nào, có **replica lag** không?
7. Có read từ **cache/GSI/search index** eventual không?
8. Có TTL/delete/compensation hoặc một write mới ghi đè không?
9. Có lỗi pagination/filter/serialization khiến record bị loại không?
10. Đọc authoritative bằng đúng khóa có thấy record không?

Không nên lập tức rebuild toàn cluster hoặc tắt consistency checks. Bắt đầu bằng việc **phân biệt routing sai, stale read, data loss và quyền truy cập**.

## 43. Chẩn đoán lỗi: một query đơn giản nhưng p99 rất cao

Các nguyên nhân có thể:

- Query không có shard key nên **broadcast toàn P shards**.
- Một shard hoặc một replica là **straggler**.
- Proxy queue quá dài hoặc connection pool đã cạn.
- Client chuyển hướng nhiều lần do slot map stale.
- Request bị gửi qua region xa.
- Coordinator làm sorting/aggregation lớn.
- Retry storm do topology thay đổi.
- Một hot partition bị compaction/GC/lock contention.

Chẩn đoán:

~~~text
1. Xác định targeted hay scatter–gather.
2. Đếm số shard được gọi thực tế.
3. So phân bố latency theo node/shard.
4. Đo pool wait, queue, redirect, retries.
5. Kiểm tra replication lag/role changes.
6. So query plan, index và filter.
7. Đo lại với cùng workload sau thay đổi có kiểm soát.
~~~

**Đổi proxy sang client-side routing không tự chữa một query broadcast 200 shards.** Phải sửa shard key/query pattern hoặc tạo read model thích hợp.

## 44. Những hiểu nhầm thường gặp

| Hiểu nhầm | Vì sao không đúng | Cách suy luận đúng |
|---|---|---|
| “Shard key chỉ ảnh hưởng phân bố lưu trữ” | Nó quyết định query targeting | Thiết kế theo access patterns |
| “Hash trực tiếp modulo số node là đủ” | Rebalance thay vị trí hàng loạt | Dùng routing metadata/protocol đúng |
| “Client-side routing là business code tự chọn host” | Driver chính thức thường đã biết topology | Dùng cluster-aware driver |
| “Proxy TCP round-robin biết key ở shard nào” | Không hiểu shard key/protocol | Cần router/proxy có nhận thức partition |
| “Có proxy thì database không cần coordinator” | Proxy có thể chỉ chọn node, còn node phối hợp replicas | Xem trách nhiệm từng tầng |
| “Coordinator luôn giữ dữ liệu” | Nó có thể forward tới replica khác | Phân biệt coordinator và owner |
| “Token-aware driver tạo strong consistency” | Chọn node không định nghĩa mức đọc/ghi | Consistency level là hợp đồng riêng |
| “MOVED và ASK như nhau” | Một cái phản ánh ownership mới, một cái có thể tạm thời | Để driver xử lý protocol |
| “Cùng Redis hash slot nghĩa là transaction nghiệp vụ” | Đồng vị trí không tự có rollback nhiều bước | Chọn atomic command/script/transaction đúng |
| “Query chỉ có một network request là rẻ” | Router có thể fan-out nhiều shards | Đo fanout và slowest shard |
| “Read từ đúng shard luôn mới nhất” | Replica có thể stale | Chọn read mode và role đúng |
| “Shard map cache phải luôn mới tuyệt đối” | Cache stale có thể xử lý bằng redirect/version | Thiết kế refresh an toàn |
| “Đổi routing config cũng di chuyển dữ liệu” | Mapping và bytes khác nhau | Migration/backfill/cutover phối hợp |
| “Dual-write hai shard luôn an toàn hơn” | Partial success/out-of-order/double effects | Protocol migration có ID và reconcile |
| “Timeout là write chưa thực hiện” | Response có thể mất sau commit | UNKNOWN + verify/idempotency |
| “Có replication thì proxy không thể là SPOF” | Proxy riêng có thể lỗi toàn bộ đường | HA proxy/coordinator |
| “Càng nhiều retry càng phục hồi tốt” | Retry storm làm cụm quá tải | Budget, backoff, jitter |
| “Routing theo tenant là đủ bảo mật” | Tenant scope vẫn cần authz | Xác thực và enforce ở nguồn |
| “Thêm nhiều shards luôn giảm latency” | Fan-out, metadata và network overhead tăng | Chọn shard count theo tải |
| “Cross-shard query là distributed transaction” | Đọc hợp nhất khác atomic commit | Phân biệt read/write/transaction |

## 45. Quy trình ra quyết định chọn điểm định tuyến

~~~mermaid
flowchart TD
    A["Liệt kê workload và shard keys"] --> B["Đọc/ghi targeted hay fan-out?"]
    B --> C{"Ứng dụng có cluster-aware driver phù hợp?"}
    C -->|"Có"| D["Đánh giá client-side token/slot awareness"]
    C -->|"Không hoặc mạng bị giới hạn"| E["Đánh giá proxy/router"]
    D --> F{"DB node vẫn làm coordinator?"}
    E --> F
    F --> G["Xác định authoritative metadata/epoch"]
    G --> H["Thiết kế failover, reshard, refresh, redirects"]
    H --> I["Chốt consistency/read/write/transaction contracts"]
    I --> J["Retry idempotent và xử lý UNKNOWN"]
    J --> K["Benchmark p99, fanout, connections, queue"]
    K --> L["Runbook và fault injection"]
~~~

Trình tự áp dụng:

1. **Vẽ ba loại request chính:** single-key lookup, list/range query, cross-shard transaction.
2. **Chốt key và identity scope:** tenant, user, order, time bucket; validate đầy đủ.
3. **Xác định ai sở hữu shard map:** driver cache, router, config service hay database metadata.
4. **Xác định route vật lý:** primary/replica, local DC, read/write consistency.
5. **Chọn kiến trúc:** smart client, proxy, coordinator hoặc phối hợp nhiều tầng.
6. **Định nghĩa stale metadata behavior:** MOVED/ASK, invalidation, refresh hoặc retry có giới hạn.
7. **Thiết kế reshard/failover:** quyền owner, epoch, cutover và ghi in-flight.
8. **Bảo vệ retries:** operation ID, idempotency, conditional write và xác minh unknown outcome.
9. **Kiểm soát hiệu năng:** pool, proxy saturation, coordinator fan-out, p99, WAN hops.
10. **Kiểm tra quyền:** tenant scope, mTLS/credentials, routing hints và audit.
11. **Đo đúng đường đi:** route, shard, node, redirects, pool wait và query plan.
12. **Kiểm thử lỗi:** stale map, node down, topology change, timeout và rollback migration.

## 46. Bài tập thực hành

### Bài tập 1 — Từ key đến replica

Với orderId=order-1001, hãy vẽ đường **routing key → partition token/slot → logical shard → replica set → node được chọn**, chỉ ra tầng nào có thể đổi khi failover và tầng nào đổi khi reshard.

### Bài tập 2 — Shard key thiếu

Collection được shard theo tenantId nhưng API chỉ nhận orderId. Hãy đề xuất ba cách giải quyết, phân tích số query, quyền truy cập và rủi ro scatter–gather.

### Bài tập 3 — Modulo node count

Một đội dùng Java String.hashCode() mod số server. Khi từ 4 lên 5 server, dữ liệu bị NOT_FOUND. Giải thích cơ chế sai và đề xuất shard map versioned cùng kế hoạch migration.

### Bài tập 4 — Redis Cluster slot

Hai key order:{order-1001}:status và order:{order-1001}:owner có quan hệ slot thế nào? Tại sao điều đó hỗ trợ một số multi-key operations nhưng không tự tạo một workflow ACID xuyên mọi side effect?

### Bài tập 5 — MOVED và ASK

Trong lúc slot đang migrate, client nhận ASK; sau cutover, client nhận MOVED. Giải thích điểm khác trong cách refresh slot map và vì sao driver phải phân biệt redirect tạm/thường.

### Bài tập 6 — Smart client

Thiết kế một driver cache topology version 42, route theo key, nhận invalidation/redirect khi version 43 xuất hiện. Nêu retry budget, refresh coalescing và hành vi khi một write đã gửi bị timeout.

### Bài tập 7 — Proxy hay client routing?

Có 500 ứng dụng trong mạng riêng, backend có 30 nodes, chính sách bảo mật không cho app kết nối trực tiếp tới data nodes. Chọn architecture ứng viên, lý giải proxy HA, pool size, latency và quyền backend.

### Bài tập 8 — MongoDB mongos

Với collection orders shard theo tenantId, so sánh find có tenantId với find chỉ có status. Làm thế nào kiểm tra targeted hay broadcast thực tế? Vì sao mongos không phải một shard lưu tất cả orders?

### Bài tập 9 — Cassandra coordinator

Bảng có partition key (tenant_id, order_id). Mô tả token-aware Java driver chọn coordinator local, coordinator hỏi replica theo QUORUM. Vì sao chọn replica không làm mất yêu cầu QUORUM?

### Bài tập 10 — Search scatter–gather

Một search query đòi top 20 orders mới nhất từ 12 shards. Hãy thiết kế bước fan-out, local top-k, global merge và xử lý sort tie-breaker. Nêu rủi ro offset pagination khi dữ liệu thay đổi.

### Bài tập 11 — Query thiếu shard key

API GET /orders/{id} hiện phải hỏi 40 shards. Hãy chỉ ra những hướng tối ưu: bổ sung tenantId, lookup mapping, đổi shard key hoặc read model. Phân tích đánh đổi consistency và storage.

### Bài tập 12 — Stale shard map

Router A dùng epoch 8 (range R→S1) trong khi owner mới là S2 ở epoch 9. Nếu A gửi write tới S1, những kiểm tra nào tại nguồn ngăn split ownership?

### Bài tập 13 — Resharding

Viết kế hoạch chuyển range R từ S1 sang S2: backfill, catch-up, quyền owner, cutover, redirect, verify và cleanup. Làm rõ thời điểm có thể rollback.

### Bài tập 14 — Dual-write

Một proxy trong migration gửi mọi update tới shard cũ và mới. Ghi ở shard cũ thành công, shard mới timeout. Nêu các tình huống partial success, lost update và duplicate increments; thiết kế cơ chế có thể phục hồi.

### Bài tập 15 — Failover vs reshard

S1 chuyển primary node A→B, sau đó range R chuyển S1→S2. Những cache/map/metadata nào của driver và proxy cần cập nhật trong từng tình huống?

### Bài tập 16 — Unknown write

CreateOrder commit tại shard S2 rồi response bị mất. Client refresh route và retry. Thiết kế idempotency key, unique constraint và verify để không tạo hai order.

### Bài tập 17 — Two-SKU checkout

Một order dùng hai SKU ở S1 và S3, order record ở S2. Vì sao route chính xác từng key chưa đủ để đảm bảo cả ba thay đổi all-or-nothing? Đề xuất transaction hoặc Saga với reservation/compensation.

### Bài tập 18 — Proxy SPOF

Database có ba replicas/shard nhưng chỉ một proxy routing. Khi proxy chết, tất cả API lỗi. Thiết kế HA proxy, health check, backpressure, failover và metrics.

### Bài tập 19 — Token-aware locality

Cassandra có hai datacenters, driver ở DC-A, các replicas có vị trí khác nhau. Trình bày cách chọn coordinator theo local DC và những câu hỏi cần đặt khi request LOCAL_QUORUM.

### Bài tập 20 — Tenant security

Client gửi tenantId=shop-b trong khi token xác thực thuộc shop-a. Router vẫn target đúng S7 của shop-b. Giải thích vì sao routing chính xác vẫn là lỗi bảo mật, và đề xuất cách enforce tenant scope.

### Bài tập 21 — Hot tenant

Một tenant chiếm 70% lưu lượng nhưng mọi key của tenant đều ở cùng shard. Hãy đề xuất subpartition, bucket hoặc read model, và nêu tác động tới targeted query và cross-bucket aggregation.

### Bài tập 22 — Retry storm

Khi primary shard chuyển leader, 2.000 application instances cùng refresh topology và retry. Hãy đề xuất backoff/jitter, budget, pool control và metrics để tránh quá tải leader mới.

### Bài tập 23 — Routing trace

Thiết kế trace cho request từ HTTP → gateway → mongos/coordinator → shard, với topologyVersion, shard IDs, replica role, redirects, pool wait và latency. Phân biệt lỗi chậm router và lỗi chậm backend.

### Bài tập 24 — Test chaos có kiểm soát

Tạo test plan cho bốn tình huống: stale slot map, proxy down, shard moving, network timeout sau commit. Với mỗi test, ghi **trạng thái đầu, sự kiện gây lỗi, kết quả được phép, bất biến cần giữ và cách quan sát**.

### Bài tập 25 — Quyết định architecture

Một dịch vụ NoSQL có ứng dụng Java, 50 data nodes, 10.000 requests/giây, đọc theo ID 95%, 5% tìm kiếm đa shard, cần tenant isolation và p99 thấp. Đề xuất lựa chọn client-side, proxy hay coordinator (có thể kết hợp), nêu **routing authority, connection topology, sharding-aware queries, failover behavior, consistency contract, performance budget và runbook**. Không chọn chỉ dựa trên số lượng node.

---

**Kết luận:** Trong NoSQL đã phân mảnh, một request đúng không chỉ cần đúng **key**, mà còn phải đi qua đúng **ánh xạ partition → shard → node/replica** ở đúng thời điểm. **Client-side routing** giúp driver đi thẳng tới đích và tận dụng locality, nhưng phải quản lý topology cache và nhiều kết nối. **Proxy/router** tập trung đường vào, chính sách và định tuyến, nhưng thêm hop và cần HA/backpressure. **Coordinator-side routing** cho phép database node phối hợp replicas/shards theo protocol, thường vẫn kết hợp được với client token-aware. Dù dùng mô hình nào, phải phân biệt **targeted query với scatter–gather, routing với consistency, failover với resharding, redirect với timeout có outcome chưa rõ**. Thiết kế tốt bắt đầu từ **access patterns và shard key**, có **metadata/version có thẩm quyền**, retry idempotent, migration an toàn, kiểm soát quyền và khả năng quan sát từng hop; nhờ đó ứng dụng mở rộng số shard mà vẫn biết **yêu cầu đang tới đâu, tại sao và điều gì đã thực sự được xác nhận**.
