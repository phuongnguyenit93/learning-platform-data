# vBucket, phân vùng dữ liệu và định tuyến yêu cầu theo khóa trong Couchbase

> **Chương:** Nền tảng Couchbase  
> **Học phần:** `SPRING_DATA_COUCHBASE` — xây dựng tầng truy cập bằng document mapping, repository, `CouchbaseTemplate`, SQL++; liên hệ phân vùng với thiết kế collection, CAS, TTL, giao dịch, tính nhất quán và API reactive.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **vBucket**, **bucket**, **Data node**, **active vBucket** và **replica vBucket**.
2. Diễn giải hành trình một document ID được ánh xạ đến phân vùng, rồi tới Data node để phục vụ thao tác key-value (KV).
3. Hiểu vai trò **cluster configuration / vBucket map** của SDK khi cluster rebalance hoặc failover.
4. Giải thích vì sao một document ID không cần đổi khi được di chuyển giữa các node.
5. Phân biệt đường KV theo ID và đường SQL++ theo thuộc tính; xác định đúng lớp gây chậm.
6. Nhận diện hot key, replica lag, timeout, retry ambiguous và các yêu cầu durability.
7. Áp dụng kiến thức vào Spring Data Couchbase đồng bộ hoặc reactive mà không tự viết logic phân vùng.

## 2. Từ document đến phân vùng logic

Couchbase lưu document trong **bucket → scope → collection → document**. Ví dụ, tài liệu `order::1001` có thể nằm trong collection `commerce.sales.orders`.

~~~text
Bucket: commerce
└── Scope: sales
    └── Collection: orders
        ├── order::1001
        ├── order::1002
        └── order::1003
~~~

Dù một collection có tên logic duy nhất, các document của nó không phải nằm trên một máy. **Data Service** phân phối dữ liệu của bucket trên nhiều Data node bằng các phân vùng logic gọi là **vBucket** (*virtual bucket*).

~~~mermaid
flowchart TD
    B["Bucket commerce"]
    V0["vBucket V0"]
    V1["vBucket V1"]
    V2["vBucket V2"]
    V3["vBucket V3"]
    A["Data node A"]
    C["Data node B"]
    D["Data node C"]
    B --> V0
    B --> V1
    B --> V2
    B --> V3
    V0 --> A
    V1 --> C
    V2 --> D
    V3 --> A
~~~

*Chỉ có bốn vBucket được vẽ để minh họa; số lượng và phân bố trong hệ thống thực do Couchbase quản lý.*

| Khái niệm | Vai trò | Điều không nên nhầm |
|---|---|---|
| **Bucket** | Không gian dữ liệu/tài nguyên ở cấp cao | Không phải một Data node |
| **Scope** | Nhóm collection theo miền logic | Không tự có vùng phân vùng vật lý riêng |
| **Collection** | Keyspace để lưu/truy vấn document | Không bắt buộc nằm cùng một node |
| **Document ID** | Định danh document trong collection | Không phải vBucket ID |
| **vBucket** | Phân vùng logic chứa một phần dữ liệu bucket | Không do ứng dụng tạo thủ công |
| **Active vBucket** | Bản đang phục vụ KV thông thường | Không đồng nghĩa với mọi bản replica |
| **Replica vBucket** | Bản sao phân vùng trên node khác | Không phải bản sao lưu độc lập |
| **Data node** | Máy chạy Data Service, giữ nhiều phân vùng | Không quyết định bằng tiền tố của ID |

**Một vBucket có thể chứa document thuộc nhiều collection trong cùng bucket.** Collection xác định không gian tên của document; vBucket giải quyết bài toán phân phối dữ liệu và định tuyến. Đường dẫn đầy đủ của một bản ghi vẫn gồm **bucket, scope, collection và document ID**.

## 3. Vì sao Couchbase dùng vBucket?

Giả sử ứng dụng tự ánh xạ trực tiếp mỗi document vào máy chủ:

~~~text
order::1001 → server-1
order::1002 → server-2
~~~

Khi thêm hoặc loại bỏ server, các khóa phải đổi vị trí; ứng dụng có nguy cơ lưu logic định tuyến bị lỗi thời.

vBucket đưa thêm một lớp trung gian:

~~~text
Document ID → hàm phân vùng → vBucket → Data node active
~~~

Khi cluster thêm hoặc bớt Data node, Couchbase có thể di chuyển các vBucket thay vì yêu cầu ứng dụng đổi document ID. Lớp trung gian này giúp:

- **Mở rộng ngang:** trải active vBucket và tải KV lên nhiều Data node.
- **Cân bằng dữ liệu:** di chuyển các phân vùng để phân bố lại dung lượng và tài nguyên.
- **Khôi phục lỗi:** một replica đủ điều kiện có thể được đưa lên làm active khi failover.
- **Định tuyến có mục tiêu:** SDK gửi yêu cầu KV tới node đang giữ active vBucket thay vì phát tán tới tất cả Data node.

Số vBucket trong một bucket được quản lý bởi Couchbase; một bucket Couchbase thông thường có rất nhiều vBucket (thường được mô tả với 1.024 phân vùng trong triển khai phổ biến). **Không hard-code số này trong ứng dụng** hoặc tự giả định mọi loại bucket/phiên bản đều có cùng cấu hình.

## 4. Cách Couchbase xác định nơi lưu document

### 4.1. Từ document key tới vBucket

Khi gọi `get("order::1001")`, Couchbase Java SDK dựa trên **khóa** và thông tin phân vùng được hỗ trợ bởi giao thức để tính ra vBucket của thao tác. SDK tra **vBucket map** của bucket để biết node nào giữ bản active.

Có thể hình dung bằng mã giả:

~~~text
vBucketId = partitionFunction(documentKey, bucketConfiguration)
dataNode = clusterMap.activeOwner[vBucketId]
sendKvRequest(dataNode, collection, documentKey)
~~~

Đoạn trên chỉ mô tả **logic khái niệm**, không phải hàm API thực tế. Đừng thay bằng `String.hashCode() % nodeCount` hoặc một phép băm tùy ý; thuật toán/giao thức định tuyến do Couchbase SDK quản lý.

Ngoài document ID, SDK cũng xử lý thông tin **bucket, scope và collection**, bao gồm metadata collection được giao thức cần tới. Hai collection có thể dùng ID giống nhau mà vẫn là hai document khác nhau. Không tự suy đoán placement của document từ tên collection hoặc tiền tố ID.

### 4.2. Vòng đời một thao tác KV

~~~mermaid
sequenceDiagram
    participant A as Ứng dụng Spring Data
    participant S as Couchbase SDK
    participant M as vBucket map
    participant D as Data node active
    A->>S: findById("order::1001")
    S->>M: Tính vBucket + tra node
    M-->>S: vBucket Vx → Data node B
    S->>D: KV Get(keyspace, ID)
    D-->>S: JSON body + CAS
    S-->>A: OrderDocument
~~~

SDK thường lấy và cập nhật cluster configuration khi bootstrap/kết nối và khi topology thay đổi. SDK được thiết kế để quản lý routing/retry theo giao thức, giúp lớp business không phải biết địa chỉ lưu trữ vật lý của document.

### 4.3. Tiền tố khóa không phải phép nhóm vật lý

Các ID:

~~~text
tenant::42::order::1001
tenant::42::order::1002
tenant::42::order::1003
~~~

không mặc nhiên nằm trong một vBucket hoặc một node. Hàm phân vùng dựa trên khóa có thể phân tán các document dù chúng có chung prefix. Vì vậy:

- Prefix có ích cho **quy ước định danh**, không phải công cụ ép dữ liệu cùng server.
- Muốn lọc theo tenant, trạng thái hoặc thời gian thì dùng **trường JSON + SQL++ + index** phù hợp.
- Đừng dựa vào thứ tự từ vựng của ID để thực hiện quét “tất cả order mới nhất”.
- Một **hot key** có tần suất truy cập cao vẫn có thể tạo nút thắt tại vBucket/node active của nó.

## 5. Bản đồ vBucket và định tuyến khi topology thay đổi

**Cluster map** mô tả dịch vụ và vị trí active/replica của vBucket theo trạng thái hiện hành. Khi khởi tạo kết nối, SDK dùng các địa chỉ seed để bootstrap, khám phá node và nhận cấu hình. Seed address là **điểm bắt đầu**, không phải Data node duy nhất phục vụ toàn bộ KV operation.

Giả sử một bản đồ giả định:

| vBucket minh họa | Active owner | Replica owner |
|---|---|---|
| `V0` | A | B |
| `V1` | B | C |
| `V2` | C | A |
| `V3` | A | C |
| `V4` | B | A |
| `V5` | C | B |

Đây là **bảng giảng dạy**, không phải số lượng vBucket và thuật toán phân bố thật. Giả sử `order::1001` trỏ tới `V4`; khi đó SDK định tuyến KV đến B. Nếu cluster chuyển active `V4` sang C, document ID vẫn là `order::1001`. Chỉ có bản đồ owner thay đổi.

### 5.1. Cấu hình cũ và phản hồi NOT_MY_VBUCKET

Trong lúc rebalance hoặc failover:

~~~text
Map cũ: V4 → node B
Map mới: V4 → node C
SDK gửi yêu cầu tới B với map cũ
B có thể báo NOT_MY_VBUCKET
SDK cập nhật cấu hình, retry theo chính sách
Yêu cầu kế tiếp được định tuyến tới C
~~~

**`NOT_MY_VBUCKET` (NMVB)** có thể xuất hiện khi bản đồ client chưa bắt kịp cluster. Đây là tín hiệu về quyền sở hữu phân vùng, **không có nghĩa document bị xóa**.

SDK chính thức có cơ chế làm mới topology/retry. Ứng dụng vẫn cần deadline, idempotency và xử lý lỗi cuối cùng; không nên bắt NMVB rồi tự viết vòng retry vô hạn trên tầng nghiệp vụ.

### 5.2. Khi gặp lỗi bootstrap/routing

Nếu SDK có thể kết nối seed node nhưng không kết nối được các Data node khác, request KV có thể gặp timeout. Cần kiểm tra DNS, TLS, firewall, published/advertised addresses và khả năng kết nối tới **mọi dịch vụ/node cần thiết**, nhất là khi triển khai sau NAT, Kubernetes, container hoặc qua mạng riêng.

## 6. Active và replica vBucket

Trong một bucket có cấu hình replica dữ liệu, mỗi vBucket active có thể có một hoặc nhiều **replica vBucket** được phân phối tới Data node khác, tùy khả năng/số node và chính sách cluster.

~~~text
vBucket X
  active  → Data node A
  replica → Data node B

vBucket Y
  active  → Data node B
  replica → Data node C
~~~

### 6.1. Active phục vụ thao tác KV thông thường

`get`, `insert`, `upsert`, `replace` và `remove` thường nhắm đến **active owner**. Phần lớn code Spring Data không cần biết replica đang nằm đâu.

Có replica không có nghĩa `get(id)` tự chia đều request giữa active và replica. Nếu ứng dụng muốn đọc replica, phải dùng API tương ứng và chấp nhận ràng buộc nhất quán của thao tác đó.

### 6.2. Replica read có thể trả dữ liệu cũ

Các API Java SDK như `getAnyReplica`/`getAllReplicas` (khi phiên bản SDK hỗ trợ) có thể trả kết quả từ các bản sao, và bản sao có thể chưa bắt kịp active.

| Thao tác | Đường đọc thường gặp | Lưu ý |
|---|---|---|
| `collection.get(id)` | Active vBucket | Đường KV chuẩn cho một ID |
| `collection.getAnyReplica(id)` | Một bản active/replica khả dụng theo API | Có thể thấy bản cũ |
| `collection.getAllReplicas(id)` | Các bản khả dụng theo API | Có thể có độ mới khác nhau |
| Truy vấn SQL++ | Query + Index, có thể Fetch ở Data | Bị ảnh hưởng bởi scan consistency và index lag |

Không nên dùng replica read cho giao dịch thanh toán hoặc thao tác yêu cầu read-your-writes nếu chưa có cơ chế kiểm chứng độ mới và quy tắc xử lý riêng.

### 6.3. Đừng nhầm các loại bản sao

- **Data replica:** bản sao vBucket phục vụ failover/khôi phục Data Service.
- **Index replica:** bản sao Global Secondary Index, phục vụ tính sẵn sàng của SQL++.
- **Backup:** bản sao dữ liệu độc lập để khôi phục xóa nhầm, ghi sai hoặc sự cố lớn.

Replica dữ liệu **không** thay thế index replica hay backup. Nếu Query/Index Service thiếu khả năng chịu lỗi, SQL++ vẫn có thể không khả dụng khi KV hoạt động.

## 7. Rebalance: di chuyển phân vùng giữa các node

**Rebalance** là quá trình phân phối lại vBucket/service khi thêm, rời hoặc sắp xếp node trong cluster. Với Data Service, nó có thể di chuyển active và replica vBucket.

~~~text
Trước: active V4 ở node B
Sau:   active V4 ở node C

Document ID không đổi: order::1001
Bucket/scope/collection không đổi: commerce.sales.orders
SDK dùng map cập nhật để chuyển yêu cầu KV tới C
~~~

Khi rebalance, cluster phải di chuyển dữ liệu và phối hợp cập nhật trạng thái; hoạt động này có thể tốn CPU, bộ nhớ, đĩa, mạng và làm tăng latency/timeout tạm thời. Mức ảnh hưởng phụ thuộc tải thực tế và sức khỏe cluster.

Hãy theo dõi:

1. Tiến độ/trạng thái rebalance của cluster.
2. Sức chứa đĩa và bộ nhớ Data node hiện có và node mới.
3. KV p95/p99 latency, timeout, retry và lỗi cập nhật topology.
4. Việc đồng thời tạo index, import dữ liệu hoặc chạy batch lớn.
5. Các ràng buộc replica/durability khi di chuyển vBucket.

**Thêm Query-only node** có thể tăng khả năng xử lý SQL++ mà không trực tiếp bổ sung Data node giữ vBucket. Không đồng nhất “tăng node trong cluster” với “vBucket dữ liệu đã được phân bố lên node mới”; cần biết node chạy những service nào.

## 8. Failover và thay đổi active owner khi node lỗi

Giả sử vBucket `V4` có active trên node B và replica trên node A. Khi B không thể phục vụ, cluster có thể thực hiện **failover** và đưa bản sao đủ điều kiện thành active, tùy trạng thái dữ liệu, cấu hình, điều kiện an toàn và chính sách vận hành.

~~~mermaid
flowchart TD
    K["Document ID → vBucket V4"]
    B["Node B: active V4"]
    A["Node A: replica V4"]
    F["Node B lỗi / failover"]
    P["Replica phù hợp được promote thành active"]
    M["Cluster map mới"]
    S["SDK cập nhật owner và định tuyến lại"]
    K --> B
    B --> F
    A --> P
    F --> P
    P --> M
    M --> S
~~~

Không mặc định rằng failover sẽ **tự động, tức thời, không gián đoạn hoặc không mất dữ liệu** trong mọi tình huống. Việc có đủ bản sao hợp lệ, đủ node, quorum/điều kiện hệ thống và cấu hình failover là quan trọng.

| Hoạt động | Mục tiêu chính | Vấn đề cần theo dõi |
|---|---|---|
| **Failover** | Chuyển vai trò khi node không còn phục vụ an toàn | Độ mới replica, khả năng hoạt động, RPO/RTO |
| **Rebalance** | Điều chỉnh phân phối vBucket/service | Chi phí di chuyển, thời gian và tải bổ sung |
| **Recovery** | Đưa node/dữ liệu trở lại trạng thái vận hành được | Đồng bộ lại dữ liệu, capacity, replica placement |
| **Backup/restore** | Khôi phục từ bản lưu độc lập | Tính đầy đủ và khả năng khôi phục dữ liệu |

Với write quan trọng, có replica thôi chưa đủ để bảo đảm ghi đã đồng bộ bền vững trước khi phản hồi thành công. Cần hiểu **durability semantics** của mutation và kiểm tra theo yêu cầu nghiệp vụ.

## 9. Durability, timeout và retry

### 9.1. Synchronous durability

Trong các phiên bản Couchbase hỗ trợ, thao tác mutation có thể yêu cầu mức durability đồng bộ:

| Mức | Ý nghĩa khái quát |
|---|---|
| Mặc định, không yêu cầu durability đồng bộ bổ sung | Ack theo semantics ghi thông thường, có thể chưa đáp ứng mục tiêu replicate/persist nâng cao |
| `MAJORITY` | Xác nhận theo đa số bản liên quan của cơ chế durability |
| `MAJORITY_AND_PERSIST_TO_ACTIVE` | Đa số xác nhận và active được persist |
| `PERSIST_TO_MAJORITY` | Dữ liệu được persist ở đa số theo yêu cầu của cơ chế durability |

Durability tăng mức bảo đảm của mutation trong kịch bản lỗi phù hợp, nhưng làm tăng yêu cầu phối hợp và có thể tăng độ trễ. Nó không thay thế **transaction, backup hoặc idempotency**, và phụ thuộc loại bucket/replica/version.

### 9.2. Timeout không chứng minh ghi đã thất bại

Tưởng tượng API:

~~~text
POST /orders
  → gửi insert(order::1001)
  → server đã ghi, nhưng response bị mất trên mạng
  → client thấy timeout
~~~

Nếu client tạo một ID mới mỗi lần retry, có thể tạo hai đơn cho một yêu cầu. Nếu client dùng cùng ID rồi thử `insert`, kết quả duplicate có thể giúp xác định trạng thái và quyết định phản hồi đúng cho nghiệp vụ.

Phân biệt:

- Retry yêu cầu **đọc KV** thường dễ quản lý hơn retry thao tác có hiệu ứng ghi.
- Với **mutation ambiguous**, cần xác minh trạng thái bằng document ID/idempotency key trước khi thực hiện lại hành động.
- SDK có retry policy ở tầng transport/routing; business layer phải xử lý semantics retry/idempotency riêng.
- Không biến mọi lỗi thành vòng lặp thử lại vô hạn; cần deadline, giới hạn số lần thử và metric.

### 9.3. CAS và document ID

CAS là metadata phiên bản do Couchbase quản lý để phát hiện **ghi đè cạnh tranh trên một document**. Nó khác vBucket ID:

~~~java
import static com.couchbase.client.java.kv.ReplaceOptions.replaceOptions;
import com.couchbase.client.java.kv.GetResult;

GetResult current = orders.get("order::1001");
orders.replace(
    "order::1001",
    current.contentAsObject().put("status", "SHIPPED"),
    replaceOptions().cas(current.cas())
);
~~~

Nếu document đã được sửa sau lần đọc, CAS có thể không còn khớp và thao tác bị từ chối. CAS không chỉ ra Data node/vBucket nào đang chứa document, và một CAS không cung cấp tính nguyên tử cho nhiều document.

## 10. Phân biệt KV routing và SQL++ routing

Đây là điểm rất quan trọng khi xây dựng tầng truy cập dữ liệu bằng Spring Data Couchbase.

~~~mermaid
flowchart LR
    A["Spring Data / Couchbase SDK"]
    D["Data Service<br/>active vBucket"]
    Q["Query Service<br/>SQL++"]
    I["Index Service<br/>GSI"]
    A -->|"get / insert / replace theo ID"| D
    A -->|"truy vấn theo thuộc tính"| Q
    Q -->|"index scan"| I
    Q -->|"Fetch document khi cần"| D
~~~

### 10.1. KV theo ID

~~~java
OrderDocument found = orderRepository.findById("order::1001")
        .orElseThrow();
~~~

Thao tác `findById` điển hình dùng KV đến active vBucket. Nó không cần primary index hoặc GSI.

### 10.2. SQL++ theo trường

~~~sql
SELECT META(o).id AS id, o.status, o.total
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = $tenantId
  AND o.status = "PAID"
ORDER BY o.createdAt DESC;
~~~

Truy vấn này đi qua Query Service; thường cần Index Service và secondary index phù hợp, chẳng hạn:

~~~sql
CREATE INDEX ix_orders_tenant_status_created
ON `commerce`.`sales`.`orders`(
    tenantId, status, createdAt DESC
);
~~~

**Thêm Data node có thể hỗ trợ năng lực KV**, nhưng không tự chữa truy vấn SQL++ thiếu index. Ngược lại, thêm Index node không nhất thiết cải thiện `get(id)`. Để phân tích truy vấn SQL++, hãy dùng `EXPLAIN` và xem query plan.

Cập nhật GSI có thể trễ sau một mutation KV. Do đó query ở scan consistency mặc định có thể chưa thấy document vừa ghi; tùy nhu cầu, có thể dùng `request_plus`/mutation state với API hỗ trợ, hoặc đọc KV nếu đã biết ID. Đây là vấn đề độ mới index, không nhất thiết là lỗi định tuyến vBucket.

## 11. Spring Data Couchbase và vBucket

### 11.1. Entity mapping

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("sales")
@Collection("orders")
public class OrderDocument {
    @Id
    private String id;

    @Version
    private Long version;

    private String tenantId;
    private String status;
    private Long total;

    // Constructor/getter/setter được lược bỏ.
}
~~~

`@Scope` và `@Collection` chỉ rõ keyspace theo version Spring Data hỗ trợ. `@Id` xác định document ID; `@Version` thường gắn với CAS optimistic locking. **Không annotation nào chỉ định document phải ở node A hay node B**.

### 11.2. Repository synchronous

~~~java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {

    List<OrderDocument> findByTenantIdAndStatus(
            String tenantId, String status);
}
~~~

- `findById(id)`, `save(entity)` và `deleteById(id)` thuộc nhóm thao tác theo ID (thường dùng KV; semantics chi tiết theo framework).
- `findByTenantIdAndStatus(...)` là derived query theo thuộc tính (thường dùng SQL++ và GSI).
- Khi tối ưu, xem SQL++ thực được Spring Data sinh; một số mapping có thể thêm điều kiện phân biệt entity như `_class`.

### 11.3. CouchbaseTemplate

`CouchbaseTemplate` cho phép thao tác entity với mức kiểm soát sâu hơn. Dù API nằm ở template thay vì repository, **Couchbase SDK vẫn đảm nhiệm** tính toán key partition và chọn Data node cho thao tác KV. Khi template thực thi SQL++, hiệu năng còn phụ thuộc Query/Index Service.

Kết nối cluster nên được quản lý và tái sử dụng theo lifecycle ứng dụng Spring Boot, không tạo một cluster connection cho mỗi request.

### 11.4. Repository reactive

~~~java
import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;
import reactor.core.publisher.Flux;

public interface ReactiveOrderRepository
        extends ReactiveCouchbaseRepository<OrderDocument, String> {

    Flux<OrderDocument> findByTenantIdAndStatus(
            String tenantId, String status);
}
~~~

~~~java
reactor.core.publisher.Mono<OrderDocument> result =
        reactiveOrderRepository.findById("order::1001");
~~~

API reactive thay đổi cách xử lý I/O và pipeline bất đồng bộ, **không thay đổi thuật toán định tuyến vBucket**. Nhiều thao tác đồng thời có thể tăng throughput, nhưng cũng tăng áp lực lên Data node và hot key nếu không giới hạn concurrency, deadline và backpressure phù hợp.

## 12. Hot key, hot vBucket và lệch tải

### 12.1. Hot key

Một document `product::homepage` được đọc 100.000 lần/giây sẽ tiếp tục được định tuyến đến active owner của vBucket tương ứng trong đường KV thông thường. Thêm Data node **không tự chia một document nóng thành nhiều active owner**.

Giải pháp cần xét:

- Cache tại tầng ứng dụng/CDN khi dữ liệu có chính sách stale phù hợp.
- Tối ưu kích thước document và tần suất gọi mạng.
- Có thể cân nhắc replica read nếu nghiệp vụ chấp nhận độ mới thấp hơn.
- Với counter/tần suất ghi cao, thiết kế **sharded counter** và cơ chế tổng hợp nếu phù hợp.
- Dùng rate limit/concurrency limit khi endpoint có thể bị gọi dồn.

### 12.2. Hot vBucket không luôn do một key

Một vBucket có thể vô tình chứa nhiều document lớn, nhóm key được truy cập nhiều, hoặc phân bố tenant/tải lệch. Số active vBucket trên các node tương đương **chưa bảo đảm CPU, memory và disk I/O bằng nhau**.

Cần quan sát tải thực tế theo node/collection/operation và cân nhắc hành vi khách hàng. Đừng chỉ dựa vào số node để kết luận đã cân bằng.

### 12.3. Tenant ID có giúp ghim dữ liệu cùng node?

ID như `tenant::42::order::1001` giúp tránh va chạm và duy trì quy ước. Nhưng prefix `tenant::42` **không phải chỉ dẫn đặt tất cả document tenant 42 vào cùng node**.

Muốn tìm đơn của tenant, lưu `tenantId` trong JSON và tạo GSI theo mẫu truy vấn. Nếu hệ thống muốn cách ly tài nguyên cho tenant đặc biệt, phải đánh giá bucket, scope/collection, RBAC và topology riêng, không chỉ đổi cách đặt prefix.

## 13. Troubleshooting theo đúng lớp

| Dấu hiệu | Nơi cần kiểm tra | Hướng xác minh |
|---|---|---|
| KV timeout tăng khi thêm Data node | Rebalance, Data CPU/đĩa/mạng, SDK retry | Đối chiếu thời điểm, p95/p99 và tiến độ chuyển vBucket |
| `NOT_MY_VBUCKET` lặp lại | SDK configuration, routing/advertised address | Kiểm tra map refresh, network giữa client và các Data node |
| Một số ID đặc biệt chậm | Hot key, vBucket/node đang tải cao | Quan sát request distribution, body size và hệ thống cache |
| Replica read trả trạng thái cũ | Replica lag/semantics đọc replica | Kiểm tra yêu cầu nhất quán, đổi đường đọc khi cần |
| `get(id)` nhanh, SQL++ rất chậm | Query/Index Service, GSI, scan/sort | Dùng `EXPLAIN`, đo query latency riêng |
| Không thấy doc vừa ghi qua SQL++ | GSI chưa bắt kịp; scan consistency | Dùng KV hoặc request_plus phù hợp |
| Timeout sau mutation, retry tạo duplicate | Thiếu idempotency | Dùng ID xác định, kiểm tra trạng thái sau kết quả ambiguous |
| Lỗi khi node mất | Replica/failover/durability, network | Kiểm tra cluster health, mục tiêu RPO/RTO |
| SDK thấy seed nhưng không thấy node còn lại | Firewall, DNS, TLS, routing | Kiểm tra các địa chỉ node được cluster công bố |
| `DocumentNotFound` ở một ID | Sai keyspace/ID, TTL hoặc dữ liệu bị xóa | Xác minh bucket/scope/collection trước khi quy lỗi vBucket |

Quy trình chẩn đoán đề xuất:

1. Xác định đây là **KV theo ID** hay **SQL++ theo field**.
2. Xác minh bucket, scope, collection, ID, RBAC và TTL.
3. Kiểm tra cluster có rebalance, failover, thay đổi network hoặc node lỗi không.
4. Xác nhận SDK có thể kết nối toàn bộ Data node cần thiết và cập nhật topology.
5. Đo CPU, memory, disk, network và latency theo từng Data node.
6. So sánh nhóm ID bị lỗi với các ID khác để tìm hot key/vBucket.
7. Điều chỉnh retry, deadline, tài nguyên hoặc mô hình truy cập dựa trên bằng chứng; theo dõi lại SLO.

## 14. Bài tập thực hành

### Bài tập A — đường đi theo document ID

Ứng dụng gọi `repository.findById("order::1001")`. Biết document thuộc active vBucket ở node B.

1. Request có cần Query/Index Service không?
2. Nếu thêm một Query node, active vBucket có tự chuyển vị trí không?
3. Cần thay đổi document ID khi active vBucket chuyển sang C không?

**Gợi ý:** đường KV tới Data Service không cần GSI; thêm Query-only node không tự thêm Data capacity; ID được giữ nguyên.

### Bài tập B — SDK dùng map cũ

Trong rebalance, vBucket `V4` chuyển từ B sang C. SDK vẫn gửi tới B theo map cũ.

1. Phản hồi nào có thể xuất hiện?
2. Thành phần nào cập nhật cluster map và retry?
3. Có nên sửa business code để tự hash ID chọn C không?

**Gợi ý:** `NOT_MY_VBUCKET`; SDK xử lý topology, application quản lý timeout và semantics retry.

### Bài tập C — so sánh active và replica

Một document vừa đổi trạng thái `NEW → PAID`. Ngay sau đó, `get(id)` trả PAID nhưng một lần replica read có thể còn NEW. Giải thích nguyên nhân và đề xuất đường đọc cho chức năng xác nhận thanh toán.

### Bài tập D — tăng node nhưng vẫn chậm

Cluster có sáu Data node, chỉ document `product::homepage` gây tải cực cao. Vì sao thêm Data node thứ bảy chưa chắc cải thiện? Hãy đề xuất chiến lược cache và giới hạn truy cập; nêu rủi ro nhất quán khi dùng replica read.

### Bài tập E — retry an toàn

Ứng dụng tạo document đơn hàng, nhận timeout sau khi gửi `insert`. So sánh hai cách retry: sinh ID mới và dùng lại ID/idempotency key cũ. Đề xuất xử lý lỗi trùng document sau retry.

### Bài tập F — KV và SQL++

API A đọc đơn theo ID, API B lọc theo `tenantId` và `status`. Xác định vai trò Data/Query/Index Service, loại index cần thiết và những metric thích hợp cho từng API.

## 15. Checklist triển khai

- [ ] Dùng SDK/Spring Data được hỗ trợ, để SDK quản lý vBucket map và routing.
- [ ] Định nghĩa chính xác bucket/scope/collection và document ID.
- [ ] Không tự hash document ID hoặc chọn Data node bằng business code.
- [ ] Kiểm tra DNS, TLS, firewall và kết nối tới các node/service SDK cần dùng.
- [ ] Dùng KV cho truy cập theo ID; dùng SQL++ và GSI cho truy vấn theo thuộc tính.
- [ ] Thiết kế document ID ổn định và idempotency cho thao tác tạo mới.
- [ ] Cấu hình replica và durability theo mục tiêu chịu lỗi của nghiệp vụ.
- [ ] Không mặc định replica read có cùng độ mới như active.
- [ ] Hiểu sự khác nhau giữa failover, rebalance, recovery và backup.
- [ ] Theo dõi p95/p99 KV latency, timeout, NMVB/retry, tài nguyên node và trạng thái rebalance.
- [ ] Phân tích hot key/hot vBucket khi tải lệch; không chỉ tăng số node.
- [ ] Phân biệt CAS, scan consistency và transaction với logic phân vùng.
- [ ] Với reactive, kiểm soát concurrency và backpressure khi số request lớn.

## 16. Tổng kết

**vBucket là phân vùng logic giúp Couchbase ánh xạ document ID đến Data node mà vẫn cho phép di chuyển dữ liệu khi cluster thay đổi.** SDK tính vBucket từ khóa, tra cluster map để tìm active owner và định tuyến KV. Khi rebalance hoặc failover làm thay đổi vị trí vBucket, document ID giữ nguyên và SDK cập nhật thông tin routing.

Trong **Spring Data Couchbase**, repository, `CouchbaseTemplate` và API reactive cùng dựa trên cơ chế phân vùng của Couchbase SDK. Kiến thức vBucket đặc biệt hữu ích khi phân tích lỗi sau failover, timeout trong rebalance, key nóng và sự khác biệt giữa thao tác KV theo ID với truy vấn SQL++ theo thuộc tính.
