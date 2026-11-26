# Hành vi ứng dụng khi failover, rebalance hoặc gián đoạn mạng

## 1. Vì sao “Couchbase tự phục hồi” không có nghĩa mọi request đều thành công?

Một hệ thống **Spring Data Couchbase** đang phục vụ đơn hàng gặp một trong ba tình huống: node Couchbase đột ngột mất kết nối, quản trị viên rebalance để thêm/bớt node, hoặc mạng giữa một nhóm ứng dụng và cluster bị gián đoạn. Java SDK có cơ chế theo dõi topology và xử lý một số lỗi tạm thời, nhưng trong lúc chuyển tiếp vẫn có thể có request timeout, retry, bị từ chối hoặc **không xác định kết quả mutation**.

Ví dụ:

- `GET /orders/{id}` theo key có thể thành công lại sau khi vBucket đổi chủ và SDK cập nhật cấu hình.
- `POST /orders` có thể đã được server áp dụng nhưng client mất ACK giữa đường, khiến retry tạo thêm Order nếu thiết kế sai.
- `GET /customers/{id}/orders` có thể chậm dù KV đã hồi phục, vì Query Service, Index Service hoặc GSI vẫn đang chịu tải/cập nhật.
- Một pod Kubernetes có thể không truy cập được các endpoints mới được quảng bá sau topology change dù pod khác vẫn ổn.

Bài thuộc chương **Quan sát và vận hành** của module **SPRING_DATA_COUCHBASE**, tập trung xây dựng tầng truy cập với document mapping, repository, `CouchbaseTemplate`, SQL++, bucket/scope/collection, index, TTL, CAS, transaction, API reactive và yêu cầu hiệu năng/nhất quán trong thực tế.

**Mục tiêu học tập:**

1. Giải thích khác nhau giữa **failover**, **rebalance**, **network partition** và **cluster-wide outage**.
2. Hiểu vai trò vBucket ownership, replicas, bootstrap, configuration refresh và endpoint discovery của Java SDK.
3. Phân biệt phản hồi đọc, ghi, query/index, Search/Analytics và transaction khi dịch vụ bị gián đoạn.
4. Xây chính sách timeout, retry, backoff, idempotency, CAS và durability đúng cho một mutation có kết quả không rõ.
5. Thiết kế Spring Boot readiness/liveness và circuit breaker/bulkhead để tránh khuếch đại sự cố.
6. Đo các tín hiệu SDK/client/Server, diễn giải p95/p99, error contexts, topology events và độ mới GSI.
7. Tạo kịch bản kiểm thử failover/rebalance/network trong **cluster lab** và runbook khôi phục.

> Một hệ thống chịu lỗi không phải hệ thống “không bao giờ gặp exception”, mà là hệ thống biết **từ chối hoặc chờ đúng lúc, không nhân đôi nghiệp vụ và phục hồi khi đường kết nối trở lại**.

## 2. Mô hình cluster: Data, Query, Index và các node không nhất thiết giống nhau

~~~mermaid
flowchart TD
    APP["Orders API / Spring Data"] --> SDK["Couchbase Java SDK"]
    SDK --> CONFIG["Bootstrap / topology configuration"]
    SDK --> DATA[("Data Service / vBuckets")]
    SDK --> Q[("Query Service / SQL++")]
    Q --> IDX[("Index Service / GSI")]
    Q --> DATA
    SDK --> S[("Search Service nếu được dùng")]
    DATA --> REPL["Active + replica vBuckets trong cluster"]
~~~

Đây là sơ đồ quan hệ ở mức khái niệm, không phải khẳng định mọi cluster đều triển khai mọi dịch vụ, node, đường kết nối hoặc cơ chế đồng bộ giống nhau.

Trong Couchbase, **Data/KV** được tổ chức theo các vBuckets có active owner và có thể có replica owners tùy cấu hình bucket. Khi một node gặp sự cố hoặc khi rebalance, việc phân bố/định tuyến vBucket có thể thay đổi. SQL++ lại dùng **Query Service**, thường phối hợp **Index Service** để quét GSI, và có thể fetch document body qua Data Service.

| Đường ứng dụng | Phụ thuộc chính | Hệ quả khi một thành phần lỗi |
| --- | --- | --- |
| `repository.findById(id)` | Data/KV và routing vBucket | Có thể lỗi tạm thời khi owner/reachability thay đổi |
| `repository.save(order)` | KV mutation, CAS/durability nếu có | Cần phân biệt ACK, timeout và ambiguous outcome |
| Derived query theo field | Query, GSI Index và đôi khi Data fetch | KV phục hồi chưa bảo đảm SQL++ phục hồi cùng lúc |
| `CouchbaseTemplate.findByQuery(...)` | Query/Index path | Cần query consistency/index plan và Query Service health |
| Full-text Search | Search Service/index nếu dùng | Có lifecycle/tình trạng khác GSI |
| Analytics, Eventing nếu dùng | Dịch vụ và pipeline riêng | Backlog/freshness có thể phục hồi chậm hơn KV |

### 2.1. “Cluster UP” là nhận định quá thô

Một SDK ping tới một số KV endpoints thành công không chứng minh Query Service, named index hoặc toàn bộ vBuckets sẵn sàng. Ngược lại, Query Service `SELECT RAW 1` thành công không bảo đảm một Order cụ thể đọc được theo KV, hay một GSI đã cập nhật đến mốc mutation mới nhất.

### 2.2. Active/replica không phải bản sao giao dịch đa vùng

Replica vBucket trong **một Couchbase cluster** là cơ chế dự phòng dữ liệu khác với **XDCR/cross-cluster replication**. Khả năng tự động định tuyến trong cùng cluster không được suy thành failover đa vùng/đa cluster tự động; kịch bản đó cần chính sách routing, replication và RTO/RPO riêng.

## 3. Phân biệt bốn loại biến cố

| Biến cố | Bản chất | Quan sát từ ứng dụng |
| --- | --- | --- |
| **Failover** | Một node không còn phục vụ vai trò trước đó, ownership/availability phải được xử lý theo cluster config | Có thể có lỗi tạm thời, refresh topology, một số KV/Query operations timeout |
| **Rebalance** | Cluster chủ động chuyển dữ liệu/partitions và phân bố resource khi membership/topology đổi | Latency/resource pressure có thể tăng; nhiều requests vẫn thành công |
| **Network partition** | Đường mạng chia cắt client ↔ node hoặc node ↔ node, không nhất thiết node chết | Một số pods/endpoints truy cập được, số khác timeout; outcome ghi có thể không rõ |
| **Service degradation/outage** | Chỉ Data, Query, Index hoặc dịch vụ cụ thể bị ảnh hưởng | KV có thể hoạt động trong khi SQL++/Search lỗi hoặc ngược lại |

### 3.1. Failover không phải lúc nào cũng “nút chuyển chủ tức thời”

Failover detection, admission, promotion và các điều kiện an toàn phụ thuộc topology, cấu hình/phiên bản Server và khả năng replica đáp ứng. Ứng dụng phải có khả năng chịu khoảng thời gian chưa phục vụ hoặc lỗi tạm thời; **đừng thiết kế hợp đồng HTTP dựa trên giả định zero downtime**.

### 3.2. Rebalance là hoạt động phục vụ online nhưng không miễn phí

Rebalance có thể dùng network, disk, memory, CPU và thay đổi ownership/placements. Một workload SQL++/GSI dưới tải cao có thể tăng p99 trong thời gian rebalance, ngay cả khi requests phần lớn vẫn thành công. Đó là lý do cần capacity headroom và theo dõi hiệu năng trước–trong–sau thay đổi.

### 3.3. Network partition không cho phép suy “server chưa nhận mutation”

Client không nhận ACK có thể do đường phản hồi bị cắt **sau khi server áp dụng write**. Retry an toàn là bài toán protocol/identity, không chỉ cấu hình một timeout lớn hơn.

## 4. Timeline minh họa của một sự cố

~~~text
10:00:00  Orders API gửi KV replace cho order::o-42
10:00:01  Đường mạng tới Data node mất gói hoặc bị ngắt
10:00:02  Một số requests xuất hiện timeout/retry
10:00:04  Cluster topology/ownership có thay đổi
10:00:06  SDK đã nhận cấu hình mới ở một số pods
10:00:08  KV get theo key phục vụ ổn định hơn
10:00:10  Query theo customerId vẫn có timeout/p99 cao
10:00:20  Index backlog/Query latency giảm dần
~~~

Đây là **timeline giả định để phân tích**, không phải một mốc thời gian bảo đảm của Couchbase.

Các câu hỏi phải trả lời riêng:

1. Mutation ở 10:00:00 có được server áp dụng hoặc đạt durability đã yêu cầu chưa?
2. SDK nhận cấu hình mới ở mỗi pod khi nào?
3. Những lỗi timeout là ambiguous hay unambiguous theo SDK/error context?
4. Có pod nào không route được các endpoints được cluster quảng bá không?
5. Query/Index đã trở lại SLO và độ mới dữ liệu chưa?
6. Hệ thống có retry/queue bùng nổ gây tải thứ cấp không?

**Không coi thời điểm KV get phục hồi là thời điểm mọi chức năng nghiệp vụ đã phục hồi.**

## 5. Bootstrap, discovery và cập nhật topology trong Java SDK

Một Spring Boot application có thể dùng connection configuration minh họa:

~~~yaml
spring:
  couchbase:
    connection-string: couchbases://couchbase.internal.example
    username: YOUR_COUCHBASE_USERNAME
    password: YOUR_COUCHBASE_PASSWORD
  data:
    couchbase:
      bucket-name: shop
~~~

Trong production, inject credentials từ secret manager/configuration được bảo vệ, không commit password literal. `couchbases://` định hướng TLS theo cấu hình phù hợp, phải kiểm tra trust/hostname theo deployment.

~~~mermaid
flowchart LR
    A["Seed DNS/connection string"] --> B["Bootstrap / TLS / auth"]
    B --> C["Cluster config và endpoints"]
    C --> D["KV vBucket map / active owners"]
    C --> E["Query/Search service endpoints"]
    D --> F["Operation routing"]
    E --> F
    F --> G{"Topology change?"}
    G -->|Có| C
~~~

SDK Java 3.x quản lý connection lifecycle, routing và cơ chế cập nhật topology. Nhưng **khả năng tự phát hiện không có nghĩa mọi request được retry mãi hoặc không bao giờ lỗi**. Các tình huống giới hạn:

- Seed ban đầu reachable nhưng SDK không reach được các node addresses được quảng bá sau bootstrap.
- Node bị loại/chuyển role, client đang sử dụng config cũ trong một cửa sổ ngắn.
- TLS trust/hostnames hoặc alternate addresses không phù hợp mạng của một pod.
- Cluster config đổi nhưng ứng dụng đang bị network partition, chưa nhận config mới.
- Query Service nodes không sẵn sàng dù KV vBucket map đã phục hồi.

### 5.1. Không kết nối mới mỗi request

Dùng `Cluster`/`Bucket`/`Collection` được Spring quản lý và tái sử dụng. Tạo `Cluster.connect(...)` trên mỗi operation, retry hoặc health probe làm tăng bootstrap/TLS/network overhead và có thể gây **reconnect storm** khi cluster đang phục hồi.

### 5.2. Không hard-code chỉ một node đích làm toàn bộ topology

Connection string có thể nêu seed address, không phải danh sách mọi Data/Query/Index endpoint phục vụ runtime. Để kiểm tra network partition, phải kiểm tra đường mạng từ **pod thực** tới các endpoints SDK/server quảng bá theo topology hiện tại, không chỉ ping một hostname seed.

## 6. Hành vi KV read trong failover, rebalance và network partition

Với `repository.findById("order::o-42")`, SDK thường xác định đường KV theo document key/vBucket routing. Khi active owner thay đổi hoặc endpoint cũ không còn phục vụ, một operation có thể:

1. Thành công ngay nhờ route còn hợp lệ.
2. Gặp phản hồi/điều kiện thúc đẩy cập nhật config/routing và thử lại theo khả năng SDK.
3. Bị timeout trước khi tìm được endpoint phục vụ.
4. Bị từ chối bởi lỗi quyền, keyspace, TLS hoặc trạng thái dịch vụ.
5. Trả not found nếu document thật sự không tồn tại/expired — **không đồng nghĩa network outage**.

### 6.1. Failover có replica không tự biến API đọc thành “luôn nhất quán”

Khả năng promotion của replica, số replica đã được cấu hình, độ mới của replica và policy failover/durability quyết định trạng thái dữ liệu. Không khẳng định **mọi write vừa ACK đều sống sót mọi failover** mà không nói tới durability, replicas, topology và thời điểm nhận ACK.

### 6.2. KV read và replica read là lựa chọn khác nhau

SDK có thể có những API đọc từ replica trong phạm vi/version hỗ trợ, nhưng đọc replica có semantics về độ mới và failure behavior khác với đọc active owner. Không biến tất cả `findById` tự động thành replica read để “giải quyết availability” nếu ứng dụng đòi dữ liệu mới nhất. Phân tích consistency contract và SDK API thật trước khi chọn fallback.

### 6.3. Không gộp not found, expired và timeout

Một Order đã hết TTL hoặc key sai có thể không tồn tại mà Data Service vẫn khỏe. Tách HTTP 404 nghiệp vụ khỏi timeout/unavailable; nếu biến mọi lỗi thành empty response, dashboard và người dùng sẽ tưởng hệ thống bình thường.

## 7. Hành vi KV write: ACK, durability và kết quả không chắc chắn

~~~mermaid
sequenceDiagram
    participant APP as Orders API
    participant SDK as Java SDK
    participant DATA as Data Service
    APP->>SDK: upsert order::o-42
    SDK->>DATA: mutation request
    DATA->>DATA: có thể áp dụng mutation
    DATA--xSDK: response/ACK bị mất trên mạng
    SDK-->>APP: timeout hoặc failure context
    Note over APP,DATA: Client chưa chắc biết mutation đã thành công hay chưa
~~~

**Không có ACK ở phía client không chứng minh server chưa viết.** SDK có thể phân biệt những trường hợp timeout không mơ hồ và timeout mơ hồ theo exception/context API, nhưng độ chắc chắn cần dựa vào semantics của operation, retry, thời điểm lỗi và Server version.

| Outcome quan sát | Điều được phép kết luận | Điều không được suy |
| --- | --- | --- |
| SDK trả ACK cho write với durability đã chọn | Operation đã được xác nhận theo contract mức durable hiện tại | Mọi failover/thiên tai trong tương lai không thể mất dữ liệu |
| Client nhận ambiguous timeout | Chưa đủ bằng chứng biết mutation có commit/áp dụng không | Chắc chắn không ghi, có thể tạo ID mới |
| Client nhận unambiguous failure theo SDK | Có thông tin để phân loại mức chắc chắn của operation cụ thể | Mọi lỗi “timeout” khác đều cùng semantics |
| SDK không đến được endpoint | Có lỗi kết nối/routing | Mọi service/node của cluster chết |
| CAS mismatch/conflict | Có cạnh tranh/điều kiện mutation không khớp | Network outage hoặc write chắc chắn chưa từng thành công |

### 7.1. Ghi idempotent không đồng nghĩa “retry ngẫu nhiên”

Nếu tạo một Order mới bằng UUID khác ở mỗi retry, cùng một command nghiệp vụ có thể tạo hai Order. Cần **một idempotency key ổn định** cho logical request, với trạng thái và xác minh kết quả; chính sách này nằm ở application/domain chứ không chỉ Java SDK.

### 7.2. Write ambiguity không biến mất chỉ vì timeout dài hơn

Timeout lớn hơn có thể giảm số lần hết deadline nhưng không loại trừ phân đoạn mạng đúng lúc server đã xử lý write. Cần thiết kế kết quả “pending/unknown”, verify/idempotency, và khả năng reconciliation trong kịch bản không thể quyết định ngay.

## 8. Mẫu tạo Order idempotent theo một key ổn định

Giả sử mỗi yêu cầu đặt hàng từ client gửi `idempotencyKey` đã được xác thực. Ứng dụng tạo document ID từ một token opaque/đã chuẩn hóa ổn định, không trực tiếp ghép dữ liệu PII vào key/log.

~~~java
import com.couchbase.client.core.error.DocumentExistsException;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;

public final class OrderCreationGateway {
    private final Collection orders;

    public OrderCreationGateway(Collection orders) {
        this.orders = orders;
    }

    public String createOnce(
            String safeOrderKey,
            String commandFingerprint,
            String customerId) {

        String docId = "order::" + safeOrderKey;

        JsonObject body = JsonObject.create()
                .put("commandFingerprint", commandFingerprint)
                .put("customerId", customerId)
                .put("status", "CREATED");

        try {
            orders.insert(docId, body);
            return docId;
        } catch (DocumentExistsException alreadyExists) {
            // Duplicate key không đủ để coi cùng yêu cầu.
            var existing = orders.get(docId)
                    .contentAsObject();

            String stored = existing.getString("commandFingerprint");
            if (!commandFingerprint.equals(stored)) {
                throw new IllegalStateException(
                        "Idempotency key used by another command");
            }

            return docId;
        }
    }
}
~~~

**Ví dụ chỉ là một lát cắt của pattern**, không phải giải pháp production đầy đủ:

- `safeOrderKey` phải được tạo/xác minh theo chính sách identity/tenant và chống đoán/collision.
- `commandFingerprint` là digest/đại diện ổn định cho **nội dung request canonical**; không log raw payload hoặc để lộ bí mật.
- `insert` theo key không ghi đè document tồn tại; `DocumentExistsException` phải phân biệt reuse cùng command với collision/đổi nội dung.
- **Network timeout trước ACK** có thể ambiguous; code trên chưa bắt timeout để tự khẳng định thành công. Caller phải dùng cùng key để verify/retry có kiểm soát.
- Nếu có Inventory, Payments hoặc downstream side effects, một document Order tồn tại **không tự chứng minh** các bước khác đã hoàn tất; cần workflow/outbox/saga hoặc transaction phù hợp.
- Có thể có cuộc đua giữa xác minh và update; nghiệp vụ cần CAS/transaction/immutable fields để bảo toàn idempotency record.

### 8.1. Dùng đúng key khi retry

Một retry hợp lệ của **logical create operation** phải dùng cùng token/key, không sinh mới. Nếu insert của request đầu đã thành công, lần sau gặp DocumentExists và có thể xác minh fingerprint; nếu request đầu chưa thành công, insert cùng key có thể tạo một Order. Hai đường đều không đòi tạo bản ghi thứ hai với ID mới.

### 8.2. Phân biệt tầng domain và tầng transport

Retry an toàn hơn khi mã định danh logical operation được lưu trước khi gửi request, tồn tại qua API gateway/client retry và được áp dụng ở nơi có tính duy nhất. Đừng giả định SDK tự hiểu “đây là cùng một đơn hàng” chỉ vì SQL++/KV payload giống nhau.

## 9. CAS và `@Version` trong lúc failover/retry

Couchbase dùng CAS để hỗ trợ optimistic concurrency; Spring Data Couchbase có `@Version` ở entity mapping tương ứng. CAS bảo vệ điều kiện **nội dung chưa bị thay đổi so với version đã đọc**, không biến network timeout thành kết quả chắc chắn.

Một entity minh họa:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Document;

@Document
public class OrderDocument {
    @Id
    private String id;

    @Version
    private Long version;

    private String status;
    private String customerId;

    // Constructors/getters/setters được lược bỏ.
}
~~~

Một service update theo phiên bản:

~~~java
public OrderDocument markPaid(String id) {
    OrderDocument current = repository.findById(id)
            .orElseThrow();

    current.setStatus("PAID");
    return repository.save(current);
}
~~~

**Ví dụ trên chưa phải workflow thanh toán hoàn chỉnh** — đặc biệt khi tiền đã thu tại hệ thống khác; không gọi payment API trực tiếp trong vòng retry mù.

### 9.1. CAS mismatch là một kết quả riêng

Nếu hai tác vụ cùng đọc Order v1 rồi cố ghi, một tác vụ có thể nhận conflict/optimistic locking exception thay vì âm thầm overwrite. Đây có thể là **tín hiệu bảo vệ correctness**, không phải thất bại kết nối.

### 9.2. Timeout sau khi write dùng CAS cũng có thể ambiguous

Nếu server áp dụng replace nhưng response mất, caller không nên sửa CAS tùy tiện rồi lặp write. Cần đọc lại trạng thái bằng key, so command/state/version và áp dụng policy idempotency. Một CAS conflict sau retry có thể do **lần ghi trước của chính request** đã thành công, hoặc do một writer khác; chỉ nhìn exception không biết trường hợp nào.

### 9.3. Không retry optimistic lock vô hạn

Đọc lại state mới, kiểm tra business preconditions và đặt bound cho attempts. Với việc chuyển `CREATED → PAID`, state machine và external payment confirmation quan trọng hơn việc chỉ `save` lại cho qua conflict.

## 10. Durability là một hợp đồng riêng với topology/failover

Mutation durability quy định mức xác nhận liên quan đến replication/persistence trong Couchbase theo SDK/Server version và cấu hình bucket/cluster. Ví dụ về intent cấu hình SDK 3.x (kiểm tra package enum `DurabilityLevel` theo phiên bản SDK):

~~~java
import com.couchbase.client.java.kv.InsertOptions;
// Import enum DurabilityLevel từ package được SDK version dùng.

orders.insert(
        docId,
        body,
        InsertOptions.insertOptions()
                .durability(DurabilityLevel.MAJORITY));
~~~

### 10.1. Ý nghĩa của durability cao hơn

Mức durability mạnh hơn có thể yêu cầu nhiều xác nhận hơn trước khi client nhận ACK, cải thiện một số đảm bảo về tồn tại của mutation trong các trường hợp failure được hỗ trợ, nhưng cũng có thể tăng latency, resource use hoặc gặp timeout/unavailability khi topology không đáp ứng điều kiện.

### 10.2. Không nói “MAJORITY bảo đảm không bao giờ mất dữ liệu”

Độ bền thực tế phụ thuộc Server version, số replica/vBucket placement, cấu hình durability, trạng thái nodes, loại sự cố và ACK đã thực sự đến caller hay chưa. Một cụm chỉ có một node hoặc cấu hình replica không phù hợp không mang các đặc tính HA của cụm được sizing đúng.

### 10.3. Durability không phải transaction hay idempotency

Durability không bảo vệ một quy trình gồm nhiều documents khỏi business partial completion, cũng không ngăn gửi cùng command hai lần. Transaction và idempotency giải quyết các lớp vấn đề khác.

### 10.4. “Ghi thành công” và “query lập tức thấy” là hai hợp đồng

KV mutation có thể đạt ACK/durability nhưng GSI vẫn cần thời gian cập nhật. Query SQL++ `NOT_BOUNDED` có thể tạm chưa thấy Order; `REQUEST_PLUS` hoặc mutation-based consistency có thể yêu cầu chờ mốc index phù hợp, với tác động tới latency/timeout.

## 11. SQL++/GSI khi Query node hoặc Index node thay đổi

Một query repository như `findByCustomerId(customerId)` có đường đi khác KV get:

~~~mermaid
flowchart LR
    APP["Orders Repository / Template"] --> Q[("Query Service")]
    Q --> IDX[("Index Service / GSI")]
    Q --> DATA[("Data Service khi fetch body")]
    IDX --> Q
    DATA --> Q
    Q --> APP
~~~

Trong failover/rebalance:

- Query endpoint có thể unavailable hoặc chuyển placement.
- Index ownership/replicas/index build/recovery có thể ảnh hưởng scan path.
- Query plan có thể không dùng được index mong muốn hoặc query lỗi vì index không online.
- Workload di chuyển có thể làm Query/Index CPU, disk I/O, memory và p99 tăng.
- GSI index có thể chưa bắt kịp mutation sau thời gian gián đoạn.
- Data fetch path vẫn có thể gặp KV routing/resource pressure riêng.

### 11.1. Query Service healthy không bảo đảm named GSI healthy

SQL++ `SELECT RAW 1` có thể thành công mà Query theo `customerId` thất bại. Cần `EXPLAIN`, named index state, Index Service scan/update metrics và query thật có bound input/pagination.

### 11.2. Query có thể thành công nhưng result chưa đủ mới

Một Index Service đang cập nhật GSI sau topology change có thể phục vụ một query `NOT_BOUNDED` với index state chưa phản ánh mutation mới. Đây là **freshness issue**, không thể định nghĩa bằng chỉ error rate.

### 11.3. Không tự xây query failover bằng hard-code Query node

SDK biết service endpoints được khám phá theo cluster config. Cấu hình URI cố định tới một Query node riêng trong code ứng dụng có thể đánh mất lợi ích discovery/recovery; chỉ làm nếu kiến trúc đã có lý do cụ thể, cơ chế routing và kiểm thử riêng.

## 12. Scan consistency sau failover: đọc thấy mutation nào?

| SQL++ consistency | Điều khoản cần hiểu | Trong gián đoạn |
| --- | --- | --- |
| `NOT_BOUNDED` | Không buộc index chờ mốc request mới nhất | Có thể trả dữ liệu chưa mới, nhưng đôi khi nhanh |
| `REQUEST_PLUS` | Query chờ index đạt mốc consistency của request theo semantics hỗ trợ | Có thể tăng latency/timeout khi backlog |
| `consistentWith(MutationState)` | Query chờ những mutation tokens đã cho theo API hỗ trợ | Hữu ích cho read-after-specific-writes nhưng không loại bỏ outage |

Một SQL++ diagnostic có lựa chọn consistency:

~~~java
import java.time.Duration;

import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryOptions;
import com.couchbase.client.java.query.QueryScanConsistency;

public class OrderListDiagnostic {
    private final Cluster cluster;

    public OrderListDiagnostic(Cluster cluster) {
        this.cluster = cluster;
    }

    public void checkQuery(String customerId) {
        String sql = """
            SELECT RAW META(o).id
            FROM `shop`.`sales`.`orders` AS o
            WHERE o.customerId = $customerId
            LIMIT 10
            """;

        cluster.query(
                sql,
                QueryOptions.queryOptions()
                        .parameters(JsonObject.create()
                                .put("customerId", customerId))
                        .scanConsistency(
                                QueryScanConsistency.NOT_BOUNDED)
                        .timeout(Duration.ofSeconds(2)));
    }
}
~~~

**Đây là test Query/Index path, không phải test freshness.** Để kiểm tra read-after-write, dùng fixture và consistency mode phù hợp, không suy rằng `NOT_BOUNDED` phải stale: index có thể đã bắt kịp rất nhanh.

### 12.1. Không “chữa timeout” bằng thay consistency vô điều kiện

Nếu endpoint tạo Order xong hiển thị danh sách bắt buộc phải có Order vừa tạo, đổi `REQUEST_PLUS` sang `NOT_BOUNDED` có thể trả response nhanh nhưng thiếu item. Đây là **hạ correctness contract**, không chỉ tuning performance.

### 12.2. Mutation tokens và replay cần đúng phạm vi

Mutation-state consistency dựa trên token/metadata mà SDK nhận được từ write theo API và Server hỗ trợ. Nếu write timeout không có ACK/token, đừng tạo token giả để bảo đảm độ mới; phải xác minh write theo idempotency/key state.

## 13. Transaction nhiều document dưới gián đoạn

Một workflow tạo Order và cập nhật Inventory có thể cần transaction thay vì hai `save` độc lập. Couchbase transactions hỗ trợ cơ chế điều phối/retry theo SDK và cấu hình tương ứng; nhưng **transaction không làm mạng trở nên đáng tin cậy**.

Một mô hình logic:

~~~text
begin transaction
  read inventory
  assert available >= quantity
  decrement inventory
  create order with stable command ID
commit transaction
~~~

Trong thực tế, transaction callback có thể được SDK chạy lại trong một số trường hợp conflict/transient failure theo phiên bản/transaction mechanism. **Không đặt side effect không idempotent** (gửi email, charge thẻ, gọi hệ thống ngoài) bên trong callback rồi giả định nó chỉ chạy đúng một lần.

### 13.1. Commit outcome cũng có thể chưa rõ với caller

Nếu đường mạng ngắt đúng lúc commit/ACK, kết quả ở client có thể không xác định ngay. Application cần idempotency/reconciliation cho **logical transaction**, không chỉ tin rằng mọi exception nghĩa rollback chắc chắn.

### 13.2. Tránh retry toàn transaction ở hai lớp không kiểm soát

Nếu SDK transaction đã quản lý retries, một vòng `@Retryable` ngoài service có thể nhân thêm attempts. Phải hiểu retry policy/version, giới hạn tổng latency và đảm bảo các bước outside-transaction không bị lặp.

### 13.3. Transaction dữ liệu không bao trùm email/payment ngoại vi

Nếu cần phát event sau commit, cân nhắc outbox/persistent state machine, publisher idempotent hoặc saga với compensation. Tránh gửi thông báo “đặt hàng thành công” trước khi outcome được xác minh.

## 14. Mỗi timeout nằm trong một ngân sách thời gian tổng

Một request HTTP có thể có nhiều deadlines:

~~~text
Client/Gateway HTTP deadline          ví dụ 3.0s
  App validation/auth                  một phần
  App admission/bulkhead wait          một phần
  SDK KV/SQL++ operation               ví dụ tối đa 1.5s
  Retry/backoff (nếu có)               một phần
  Mapping/serialization                một phần
~~~

Các con số chỉ là **minh họa**, không phải cấu hình mặc định của Couchbase hoặc đề xuất SLA áp mọi ứng dụng.

### 14.1. Timeout được lựa chọn theo thao tác

- KV read theo ID có latency profile khác SQL++ query có GSI.
- KV write với durability cao có thể cần budget khác một read.
- Transaction nhiều bước có tổng budget khác một KV mutation.
- Query `REQUEST_PLUS` có thể phải đợi index, cần căn chỉnh với yêu cầu freshness.
- Admission waiting đã tiêu tốn một phần HTTP budget trước SDK call.

### 14.2. Timeout quá dài cũng có chi phí

Nếu mỗi request bị giữ nhiều giây khi dependency unavailable, số in-flight/connection/memory và thread/scheduler pressure tăng. Ngược lại timeout quá ngắn dưới workload bình thường tạo lỗi giả, retries và hiệu năng xấu.

### 14.3. Liveness/readiness không nên đợi lâu hơn deadline probe

Một health indicator thực hiện Query 10 giây khi Kubernetes `timeoutSeconds=2` sẽ bị đánh fail trước khi operation hoàn tất. Đặc biệt không gọi `REQUEST_PLUS` query nặng trong mỗi readiness probe vì có thể làm Index Service lag và gây **all-pods-NotReady**.

## 15. Retry sau failover: phân biệt những gì an toàn để thử lại

**Không có một quy tắc “retry tất cả lỗi Couchbase ba lần” đúng cho mọi operation.**

| Loại thao tác | Retry có thể phù hợp khi | Phải chú ý |
| --- | --- | --- |
| KV read-only | Lỗi transient/reachability, còn budget | TTL/not-found, consistency/fallback |
| SQL++ read-only | Query/transport transient và query budget cho phép | Scan consistency, index freshness, tải Query Service |
| KV insert ổn định key | Domain idempotency thực sự tồn tại | Ambiguous insert, DocumentExists, verify fingerprint |
| KV upsert/replace | Chứng minh mutation idempotent/conditional | CAS, side effects, state transitions |
| Transaction | Theo policy SDK/transaction và domain | Callback replay, commit outcome, external side effects |
| DDL/index management | Gần như không dùng retry request tự động ở app | Quyền, trạng thái build, migration job |
| Payment/email/external action | Cần idempotency của **hệ thống ngoài** | Không lặp charge/gửi mail vô kiểm soát |

### 15.1. SDK có thể tự retry một số lỗi

Java SDK có cơ chế xử lý một số lỗi transient và retry theo chính sách/version. Application cần hiểu semantics này trước khi thêm Spring Retry/Resilience4j ở ngoài, vì **nhân đôi retry layers** gây request amplification và hết budget.

### 15.2. Retry không sửa RBAC, keyspace sai hoặc index thiếu

Authentication failure, permission denied, collection không tồn tại hoặc Query thiếu index thường không phải lỗi tự hồi phục bằng chờ vài mili giây. Phân loại exception/status trước khi retry.

### 15.3. Exponential backoff có jitter và attempt budget

Thay vì mọi pod retry đồng thời mỗi 100 ms, dùng backoff tăng dần, jitter và giới hạn attempts/elapsed time. Dù read-only, retry quá nhiều trong outage vẫn có thể giữ Query/Index dưới tải khi chúng đang cố phục hồi.

## 16. Những giới hạn cần đặt cho retry và queue

Một policy chịu lỗi tốt có nhiều chốt:

1. **Per-operation timeout:** không để DB call chạy vô hạn.
2. **HTTP deadline:** tổng request không kéo dài mãi.
3. **Max attempts:** có trần và không tạo duplicate operation.
4. **Backoff + jitter:** giảm đồng bộ giữa pods.
5. **Concurrency/bulkhead:** giới hạn số DB calls đang ở trong hệ thống.
6. **Queue budget:** chờ permit có timeout; quá tải có thể từ chối sớm.
7. **Circuit breaker:** ngừng gọi đường đang lỗi nặng trong một cửa sổ nếu policy yêu cầu.
8. **Recovery probes:** thăm dò có giới hạn khi dependency phục hồi.
9. **Observability:** ghi original failure, retry attempts, cancellation, final outcome.
10. **Fallback correctness:** không trả dữ liệu sai/giả thành công khi dependency mất.

### 16.1. Đừng để mỗi tầng retry ba lần

Nếu gateway retry HTTP 3 lần, service retry DB 3 lần, SDK cũng retry một số attempts, tổng số network operations có thể lớn hơn số người dùng tưởng. Ví dụ về **request amplification** này là lý do phải có một **logical attempt budget** và correlation ID xuyên các lớp, không phải phép nhân chính xác áp mọi implementation.

### 16.2. Circuit breaker không tự nhận biết commit outcome

Một circuit breaker có thể ngắt calls mới khi DB timeout nhiều, nhưng không phân biệt mutation phía server đã thành công hay chưa. Đối với create/payment/inventory, application vẫn cần idempotency + trạng thái “chưa xác định”/reconciliation.

### 16.3. Retry storm trong thời gian rebalance

Khi cluster di chuyển ownership và có spikes tạm thời, hàng trăm pods cùng retry mạnh có thể khiến Query/Index/Data Service khó hồi phục. Đo retry rate, in-flight, admission rejects và HTTP p99 cùng nhau.

## 17. Ma trận hành vi theo operation và loại biến cố

| Đường truy cập | Failover Data node | Rebalance | Mất kết nối từ một pod | Cần xác minh |
| --- | --- | --- | --- | --- |
| **KV get** | Routing có thể đổi, timeout/not-found phải phân biệt | Có thể tăng tail latency | Pod không reach Data endpoint | vBucket map, endpoint, TTL |
| **KV insert** | Có ACK hoặc ambiguous | Mutation có thể chậm | ACK thất lạc | Idempotency, durability |
| **KV replace CAS** | Conflict hoặc ambiguous | Contention tăng | Không rõ update đã áp dụng | Readback, version/state |
| **Repository SQL++** | Fetch Data có thể ảnh hưởng | Query/Index resource pressure | Query endpoint không reachable | GSI state, EXPLAIN |
| **SQL++ REQUEST_PLUS** | Có thể phụ thuộc Index lag | Index backlog/consistency wait | Timeout ở Query path | Freshness SLO |
| **Search query** | Index/data pipeline khác tùy topology | Search workload riêng | Search endpoint bị chia cắt | Search index/readiness |
| **Transaction** | Retry/conflict hoặc commit outcome chưa rõ | Latency/resource impact | Mất commit ACK | Reconciliation/outbox |
| **Eventing/Analytics** | Pipeline có thể lag | Backlog hoặc processing trễ | Xử lý/ingestion lỗi | Service metrics |

Đây là **những kết quả có thể xảy ra**, không phải khẳng định cố định cho mọi topology và SDK/Server version. Một pod bị network policy chặn và một Data node đã failover có thể tạo exception tương tự nhưng cách xử lý khác nhau.

### 17.1. Tách các thuộc tính phục vụ

- **Availability:** API hoàn tất thành công?
- **Latency:** HTTP/SDK/Query p95/p99 có còn trong SLO?
- **Freshness:** GSI/Search/replica đã thấy mutation đến mốc nào?
- **Correctness:** CAS, durability, transaction và idempotency có giữ bất biến?
- **Recovery:** khi cluster/nền mạng ổn định, lỗi, hàng đợi và dữ liệu đã hồi phục chưa?

Một health `UP` hay ping thành công không đủ trả lời cả năm.

## 18. SDK ping và diagnostics khi topology thay đổi

Java SDK 3.x cung cấp `Cluster.ping()` và `Cluster.diagnostics()`; kết quả có ý nghĩa theo **dịch vụ, endpoint và thời điểm**.

~~~java
import com.couchbase.client.java.Cluster;

public final class ClusterDiagnosticSampler {
    private final Cluster cluster;

    public ClusterDiagnosticSampler(Cluster cluster) {
        this.cluster = cluster;
    }

    public void sampleForOnCall() {
        var ping = cluster.ping();
        var snapshot = cluster.diagnostics();

        // Chuyển trạng thái theo service/endpoint thành
        // metric hoặc log được redacted, có timestamp.
        // Không trả raw report trên public HTTP endpoint.
    }
}
~~~

- `ping` có thể thử reachability những service types/endpoints mà SDK hỗ trợ trong scope call.
- `diagnostics` là snapshot client view, không tự thực hiện một business SQL++ hoặc KV operation tương đương.
- Report thiếu Search có thể chỉ vì service không triển khai/chưa được SDK sử dụng, không phải chắc chắn DOWN.
- Pod A và B có thể có client view khác nhau do routing, TLS/trust, thời điểm topology refresh hoặc network partition.
- Một Query endpoint responsive không chứng minh named GSI online.

### 18.1. Tránh reconnect storm do probe

Không gọi `Cluster.connect(...)` liên tục trong health handler để lấy diagnostics. Dùng `Cluster` do Spring quản lý, giới hạn tần suất/kích thước log và không công khai IP, port, certificate hoặc topology chi tiết.

### 18.2. Ping không thay request thật

Một check `Collection.exists` trên đúng collection thử được một KV operation; `SELECT RAW 1` thử Query Engine cơ bản; SQL++ theo `customerId` và `EXPLAIN` thử Query/Index path. Ba kết quả có phạm vi khác nhau.

## 19. Mapping lỗi ứng dụng và HTTP status

Không biến mọi lỗi từ repository thành HTTP 200/danh sách rỗng:

~~~java
// Phản ví dụ: che giấu lỗi vận hành.
try {
    return orderService.customerHistory(customerId);
} catch (RuntimeException ignored) {
    return java.util.List.of();
}
~~~

Một policy cần phân biệt:

| Nhóm | Response có thể phù hợp | Không được làm |
| --- | --- | --- |
| Input invalid | 400/contract-specific | Retry Couchbase |
| Document not found | 404 nếu đúng semantics | Coi Data Service down |
| CAS/business conflict | 409/domain error | Gộp vào timeout |
| Backend auth/RBAC lỗi | 5xx + alert nội bộ | Trả nguyên stacktrace/secret |
| Dependency unavailable | 503 hoặc contract tương ứng | Trả success giả |
| Gateway/backend deadline exceeded | 504/503 tùy architecture | Cho phép retry tạo ID mới |
| Mutation outcome chưa rõ | Error/pending status có mã truy vết, theo contract | Khẳng định chắc chưa commit |

Không có một HTTP status cố định bắt buộc cho mọi deployment. Đối với API tạo Order, cần diễn giải rõ cho client: **retry cùng idempotency key** và có endpoint/trạng thái để kiểm chứng kết quả.

### 19.1. Phân loại qua SDK API thay vì parse text

Dựa trên exception class, error context hoặc retry reason thực của SDK/Spring Data version. Không phân loại bằng `exception.getMessage().contains("timeout")`, vì format thay đổi và message có thể chứa chi tiết nhạy cảm.

### 19.2. 202 Accepted không phải cách che lỗi ghi

202 phù hợp khi ứng dụng đã **ghi nhận command đáng tin cậy** nhưng xử lý chưa hoàn tất. Nếu bản thân ghi nhận đã ambiguous, không tùy tiện trả 202 mà không có contract cho việc tra trạng thái.

## 20. Spring Boot liveness và readiness lúc cluster suy giảm

Spring Boot Actuator có thể cung cấp:

~~~text
/actuator/health
/actuator/health/liveness
/actuator/health/readiness
~~~

Ví dụ cấu hình:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
  endpoints:
    web:
      exposure:
        include: health,info
~~~

**Liveness** trả lời process/JVM có còn vận hành không. Nó **không nên phụ thuộc Couchbase** khi restart pod không sửa được shared database outage.

**Readiness** quyết định pod có nên nhận traffic theo deployment contract. Có thể đưa một dependency thiết yếu vào readiness khi phù hợp, nhưng nếu cả cluster Query Service cùng lỗi, đưa Query vào readiness của mọi Orders pod có thể gây **all-pods-NotReady** dù KV detail routes vẫn phục vụ được.

### 20.1. Custom groups theo capability

Nếu có custom HealthIndicator bean `queryEngine` được đăng ký thực trong context, có thể xuất group giám sát riêng:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        query-path:
          include: queryEngine
~~~

Cần xác minh contributor ID và Spring Boot version; tên này không mặc định có sẵn. Không dùng Query/Index synthetic test nặng trong liveness.

### 20.2. Readiness không thay request-level resilience

Probe chạy định kỳ; một vBucket có thể lỗi giữa hai lần probe hoặc chỉ một Query endpoint lỗi. Controller/service vẫn cần deadline, error mapping, cancellation và idempotency.

## 21. Kubernetes probes và restart storm

Một ví dụ Deployment khi Actuator chạy cùng cổng HTTP phục vụ ứng dụng:

~~~yaml
containers:
  - name: orders-api
    image: registry.example.invalid/orders-api:TAG
    ports:
      - containerPort: 8080

    startupProbe:
      httpGet:
        path: /actuator/health/liveness
        port: 8080
      periodSeconds: 2
      timeoutSeconds: 2
      failureThreshold: 30

    livenessProbe:
      httpGet:
        path: /actuator/health/liveness
        port: 8080
      periodSeconds: 10
      timeoutSeconds: 2
      failureThreshold: 3

    readinessProbe:
      httpGet:
        path: /actuator/health/readiness
        port: 8080
      periodSeconds: 5
      timeoutSeconds: 2
      failureThreshold: 3
~~~

Giá trị chỉ minh họa, phải chọn theo workload/SLO.

- `startupProbe` cho app thời gian khởi động.
- `livenessProbe` có thể kích hoạt container restart khi process không khỏe.
- `readinessProbe` điều khiển Service endpoints/traffic admission.

### 21.1. Mất Couchbase không nhất thiết cần restart JVM

Một lần restart toàn bộ pods có thể tạo hàng loạt reconnect/TLS/bootstrap requests đúng lúc cluster đang phục hồi. Nếu SDK có thể refresh cấu hình và reconnect, giữ liveness độc lập dependency và alert riêng cho outage.

### 21.2. Đọc health ở đúng cổng

Một management port vẫn UP khi cổng HTTP chính bị nghẽn/hỏng. Dùng additional health endpoints trên main serving port khi phù hợp và Spring Boot version hỗ trợ; không lấy management-only status làm chứng minh toàn bộ business API chạy.

### 21.3. Graceful shutdown và request đang dở

Khi rollout/scale down, drain traffic, graceful shutdown và termination grace period giúp giảm requests bị cắt giữa chừng. Nhưng failover/network partition bất ngờ vẫn có thể ngắt write đúng lúc ACK, nên correctness policy vẫn bắt buộc.

## 22. Circuit breaker, bulkhead và rate limiting theo capability

Đề xuất các capability riêng:

~~~text
orders.kv.read
orders.kv.write
orders.list.sqlpp
products.search
reports.analytics
~~~

Nếu Query Service lỗi, breaker của `orders.list.sqlpp` có thể mở trong khi đường KV detail vẫn chạy. Một breaker gộp “Couchbase” có thể làm tê liệt cả chức năng khỏe khi một subsystem lỗi.

### 22.1. Đừng tính mọi 404/409 thành dependency failure

Order không có key hoặc optimistic lock conflict có thể là business outcome hợp lệ. Breaker/alerts nên phân loại **timeout/unavailable/permission** khác **not-found/conflict/validation** theo contract. Cần thử classifier.

### 22.2. Bulkhead và queue budget

Một concurrency limit cho SQL++ reports ngăn reports chiếm toàn bộ tài nguyên service, nhưng khi hết permit phải có wait timeout hoặc reject policy. Không xếp hàng vô hạn vì queue delay cộng SDK timeout vượt HTTP budget.

### 22.3. Half-open probes nhẹ

Khi thử đóng breaker sau outage, không cho mọi pod chạy SQL++ `REQUEST_PLUS` sắp xếp hàng triệu rows. Dùng read-only/short-deadline checks có giới hạn, sau đó theo dõi error rate/p99 thật.

### 22.4. Breaker không bảo đảm exactly-once

Nó ngăn calls mới, không biết mutation timeout đã commit chưa. Domain vẫn cần stable operation ID, command fingerprint, state machine và reconciliation.

## 23. Reactive Spring Data khi mạng chập chờn

Với `ReactiveCouchbaseRepository`/`ReactiveCouchbaseTemplate`, một `Mono`/`Flux` thường thực hiện I/O lúc subscribe. Mẫu retry **chỉ cho KV read-only**, với classifier riêng theo SDK version:

~~~java
import java.time.Duration;

import com.couchbase.client.java.ReactiveCollection;
import com.couchbase.client.java.kv.GetResult;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

public final class ReactiveOrderRead {
    private final ReactiveCollection orders;
    private final ReadFailureClassifier classifier;

    public ReactiveOrderRead(
            ReactiveCollection orders,
            ReadFailureClassifier classifier) {
        this.orders = orders;
        this.classifier = classifier;
    }

    public Mono<GetResult> get(String id) {
        return orders.get(id)
                .retryWhen(
                    Retry.backoff(2, Duration.ofMillis(50))
                        .maxBackoff(Duration.ofMillis(300))
                        .jitter(0.5)
                        .filter(classifier::isRetriableReadFailure));
    }
}

// ReadFailureClassifier là abstraction ứng dụng:
// cần triển khai và unit-test theo taxonomy exception thật.
~~~

**Không áp dụng nguyên mẫu này cho write/transaction.** Nó cũng cần giới hạn HTTP/SDK budget; SDK có thể đã tự retry một số lỗi trước khi Reactor thấy exception.

### 23.1. Không block WebFlux event loop

~~~java
// Phản ví dụ:
var result = reactiveOrders.get(id).block();
~~~

Khi dependency chậm, blocking event loop làm HTTP p99 xấu và có thể khiến liveness timeout giả. Dùng reactive chain, timeouts/backpressure và cancellation được xử lý đúng.

### 23.2. Cancellation không tự đồng nghĩa rollback

Client đóng kết nối HTTP hoặc cancel `Mono` không bảo đảm mutation phía server bị hủy kịp trước khi áp dụng. Với write, vẫn cần xác minh outcome và idempotency.

### 23.3. Timer trước/sau retry khác nghĩa

Một Timer bên trong `retryWhen` có thể đo các attempts; Timer ngoài có thể đo logical call gồm backoff/retry. Ghi nhãn rõ để không biến một HTTP request thành nhiều business requests trong dashboard.

## 24. Chẩn đoán network partition theo tầng

Một pod timeout không có nghĩa toàn cluster đã failover. Điều tra:

1. DNS resolution từ đúng **pod bị lỗi**.
2. TCP/TLS reachability tới endpoints SDK khám phá, không chỉ seed.
3. Firewall, NetworkPolicy, NAT/alternate addresses và service mesh.
4. Certificate trust, hostname/SAN, secret rotation, identity.
5. SDK `ping`/`diagnostics` giữa pod lỗi và pod lành.
6. Node/zone routing, packet loss/latency và endpoint status.
7. CPU/GC, thread starvation và application admission queues.
8. Quyền RBAC đúng bucket/scope/collection và operation.
9. Query vs KV service type, namespace/index state khác nhau.
10. Server cluster events/status từ công cụ quản trị được cấp quyền.

### 24.1. Seed reachable chưa có nghĩa cluster endpoints reachable

SDK có thể nhận topology với địa chỉ node khác seed; trong NAT/Kubernetes, địa chỉ được quảng bá có thể không route từ pod. Kiểm tra đường thực tế của **app → endpoints**, không chỉ DNS seed.

### 24.2. TLS, authentication và authorization khác nhau

TLS handshake failed, password/token không hợp lệ và permission denied là các tầng khác nhau. Đừng tăng retry hoặc index quota để sửa certificate SAN mismatch hay thiếu role `SELECT`.

### 24.3. Không public raw diagnostics

Host/IP, certificate details, connection strings và Query parameters phải nằm trong operator logs/diagnostics có RBAC, audit, retention. HTTP response cho end user chỉ cần mã lỗi an toàn và request ID.

## 25. XDCR/đa cluster: failover vùng khác failover node

~~~mermaid
flowchart LR
    W["Writer region A"] --> A[("Cluster A")]
    A --> XD["XDCR replication"]
    XD --> B[("Cluster B")]
    R["Reader after regional failover"] --> B
~~~

**Phải tách rõ:**

- Failover vBucket/Data node **trong một cluster**.
- Chuyển traffic ứng dụng sang **cluster khác**, thường cần DNS/config/routing/orchestration; SDK refresh topology của A không tự thay Cluster A bằng Cluster B.
- Replication status, backlog, target freshness và conflict resolution.
- Read-after-write qua các regions và multi-writer idempotency.
- Query/GSI consistency **trên cluster đích**, không suy từ cluster nguồn.

### 25.1. RTO và RPO

**RTO** là mục tiêu thời gian phục hồi phục vụ; **RPO** là mức mất dữ liệu/trễ dữ liệu chấp nhận được. Chúng không tự được bảo đảm bởi cấu hình durability của cluster A hay `REQUEST_PLUS` trên A. Phải có kiến trúc, monitoring và disaster-recovery drills riêng.

### 25.2. Tránh duplicate Orders xuyên region

Nếu hai clusters tạm xử lý cùng idempotency key trước khi replicate, có thể tạo hai trạng thái độc lập. Cần chính sách multi-region identity, write ownership, reconciliation và conflict resolution, không mặc định XDCR là transaction toàn cầu.

## 26. Quan sát thời điểm lỗi, quá trình chuyển trạng thái và hồi phục

Một dashboard hữu ích trong failover/rebalance không chỉ có một biểu đồ “Couchbase UP”. Nó phải đủ để trả lời **đường nào lỗi, ở node/pod nào, trong bao lâu, sau đó đã thực sự phục hồi chưa**.

| Lớp quan sát | Tín hiệu cần có | Ý nghĩa |
| --- | --- | --- |
| **HTTP/user impact** | Request rate, 5xx, p95/p99, retry từ client | Người dùng bị ảnh hưởng ra sao |
| **Spring application** | Logical commands, in-flight, admission wait/rejected | Có overload/retry amplification? |
| **KV SDK** | Get/insert/replace latency, timeout, ambiguous outcomes | Data path và write correctness |
| **SQL++ SDK** | Query duration/errors, client context ID | Query path và correlation |
| **SDK endpoints** | Ping/diagnostics theo service và pod | Topology/reachability recovery |
| **Data Service** | Node/vBucket state, KV latency, failover events | Ownership/replica health |
| **Query Service** | Active/queued, errors, CPU/memory, slow requests | SQL++ recovery |
| **Index Service** | Named GSI state, mutation backlog, scan latency | Index availability/freshness |
| **Kubernetes/network** | Pod restarts, readiness transitions, DNS/TLS errors | Pod-local so với shared outage |
| **Business correctness** | Duplicate prevention, pending commands, reconciliation | Không mất/nhân đôi Order |

Tên meter/field cụ thể phụ thuộc Couchbase Server, SDK, Micrometer và monitoring stack version; **không giả định** một time-series name tồn tại ở mọi triển khai.

### 26.1. Ghi thời điểm bằng correlation và mốc UTC

Một event log do ứng dụng tự thiết kế:

~~~text
timestamp=2026-11-25T10:05:07Z
traceId=...
route=POST /orders
logicalCommand=opaque-id
db.service=kv
db.operation=insert
db.outcome=ambiguous_timeout
elapsedMs=1400
pod=orders-api-a
~~~

Không log customerId, payment token, Order JSON hay private topology ra kênh công khai. ID này dùng cho logs/traces có retention và quyền truy cập phù hợp, **không làm metric label**.

### 26.2. Phân biệt request attempts với logical business operations

Trong outage, một logical create command có thể tạo nhiều attempts vì SDK, service hoặc gateway retry. Dashboard phải có **operations_requested**, **attempts**, **committed/verified**, **ambiguous_pending**, **deduplicated**, **rejected** theo policy. Không tính attempts là số đơn hàng thực sự đã tạo.

### 26.3. Định nghĩa “đã hồi phục” có nhiều mức

- Mạng/SDK lại reach được endpoints.
- KV get và mutations phục vụ đúng deadline.
- SQL++/Index Service theo named index phục vụ lại.
- GSI freshness đáp ứng SLO.
- Pending write/transaction outcomes được reconcile.
- 5xx, retry rate và p99 trở lại mục tiêu.
- Không còn queue/pod flapping do probe hoặc reconnect storm.

Một cluster UI xanh không thay thế các kiểm tra functional SLO này.

## 27. Incident A: failover khi một Order đang được tạo

**Kịch bản giả định:**

~~~text
09:00:00  Client gửi POST /orders kèm idempotencyKey=A1
09:00:01  API dùng document key ổn định từ A1
09:00:02  SDK gửi KV insert
09:00:03  Mạng/owner bị gián đoạn trước khi client nhận ACK
09:00:04  API ghi ambiguous outcome, không tạo ID mới
09:00:07  Cluster/SDK bắt đầu phục hồi đường KV
09:00:10  Client kiểm tra trạng thái hoặc retry với A1
~~~

**Hướng điều tra và xử lý:**

1. Kiểm tra account, collection, quyền, durable write options và loại timeout thực từ SDK.
2. Ghi nhận command fingerprint + idempotency key, không log raw payload.
3. Nếu write outcome chưa rõ, không khẳng định Order chưa tồn tại.
4. Khi KV path khả dụng, đọc lại **đúng document key**.
5. Nếu document tồn tại và fingerprint khớp, xác minh business state rồi trả trạng thái tương ứng.
6. Nếu không có document, cân nhắc retry insert với **cùng key** theo policy; tránh ID mới.
7. Nếu document tồn tại nhưng fingerprint khác, trả conflict và điều tra collision/reuse.
8. Đối chiếu Inventory, Payment hoặc downstream events qua transaction/outbox/reconciliation.
9. Quan sát failover events, SDK endpoint recovery, ambiguous write rate và số deduplicated commands.
10. Kiểm tra user-visible outcome, không chỉ hết exception.

**Tiêu chí đúng:** Cùng một command không tự tạo hai Orders và hệ thống không báo xác nhận thanh toán khi chưa có bằng chứng nghiệp vụ tương ứng.

### 27.1. Nếu client rời đi trong lúc chưa rõ kết quả?

Ứng dụng cần API truy vấn trạng thái theo stable operation ID, hoặc một background workflow/reconciliation đã được thiết kế **trong chính ứng dụng**, không dựa vào một SDK retry bất tận. Đội vận hành phải có số lượng pending và age distribution để phát hiện các yêu cầu mắc kẹt.

### 27.2. Replica promotion và dữ liệu mới nhất

Không mặc định document được bảo vệ giống nhau trong mọi durability/replica topology. Đối chiếu cấu hình durability của write, số replica và sự kiện cluster để phân tích nguy cơ mất dữ liệu theo contract đã chọn.

## 28. Incident B: rebalance làm SQL++ p99 tăng

**Kịch bản giả định:**

~~~text
10:00  Rebalance được khởi động theo kế hoạch
10:04  Data/Index network và disk I/O tăng
10:06  Query p99 tăng, một số request timeout
10:08  Index mutation backlog tăng
10:09  REQUEST_PLUS query chờ lâu
10:11  KV get vẫn gần latency baseline
10:20  Rebalance hoàn tất
10:24  Query p99 và backlog giảm dần
~~~

Một Query timeout trong cửa sổ này **không đủ để kết luận toàn cluster down**.

Các bước:

1. Lấy timeline rebalance và phạm vi nodes/services/indexes tham gia.
2. So Index Service updates/s, scans/s, memory, disk I/O, named-index states.
3. So Query Service CPU/memory, queued/active, errors và request profiling khi có.
4. Xác minh `EXPLAIN` của SQL++ thực, index có bị thay đổi không.
5. Tách consistency wait của `REQUEST_PLUS` khỏi sort/fetch/query queue.
6. Kiểm tra client retries/timeout budgets và API admission waiting.
7. Cân nhắc giảm reports non-critical trong maintenance window theo policy.
8. Đo **thời gian sau khi rebalance kết thúc** để backlog và SLO quay về baseline.

**Không khắc phục mù** bằng cách chuyển toàn bộ sang `NOT_BOUNDED`, tăng mọi timeout hoặc build thêm indexes khi cluster đã chịu áp lực. Quyết định cần giữ business freshness và có khả năng rollback.

### 28.1. Quản lý kỳ vọng trong maintenance

Ngay cả planned rebalance cũng cần một capacity/performance budget và kênh thông báo. Nếu một lớp API có SLO nghiêm ngặt, thử khả năng chịu rebalance trên lab có topology tương tự và chọn maintenance window/traffic policies trước khi áp dụng.

## 29. Incident C: chỉ một pod không kết nối được sau topology change

**Tình huống giả định:**

~~~text
Pod orders-a  KV get OK, SQL++ OK
Pod orders-b  KV get timeout, SQL++ có thể OK
Pod orders-c  KV get OK, SQL++ OK
Cluster UI    nodes healthy / rebalance done
~~~

Không thể kết luận Data Service chết toàn cluster chỉ vì `orders-b` timeout.

**Cây nguyên nhân cần kiểm tra:**

- Pod B nằm ở node/zone có routing khác?
- DNS seed resolve khác, service discovery/SDK endpoint view khác?
- Các discovered Data endpoints có địa chỉ không reach được từ B?
- Pod B có NetworkPolicy/egress rules, mesh sidecar hoặc NAT khác?
- TLS truststore/certificate/secret của B có lỗi/mất đồng bộ?
- SDK Cluster bean của B có tạo nhiều lần hoặc đang bootstrap liên tục?
- JVM B bị starvation/GC hoặc blocking event loop?
- Một vBucket owner nhất định không reachable từ B?
- Application cache/chính sách retry của B khác image/config rollout?

### 29.1. Phép thử có kiểm soát

Từ **pod B** hoặc debug pod cùng network context được ủy quyền, xác minh DNS, TCP/TLS tới **đúng service endpoints**. Sau đó dùng SDK `ping`/`diagnostics` và read-only KV operation trên đúng collection. Không chỉ test seed hostname.

### 29.2. Mức ảnh hưởng và phục hồi

Có thể cho B NotReady nếu nó không còn phục vụ được traffic contract, nhưng liveness restart có thể chỉ làm sự cố tệ hơn nếu network path không đổi. Khôi phục NetworkPolicy/route/secret/config là cách sửa root cause; đo lại theo **pod B**, không chỉ cluster aggregate.

## 30. Unit tests cho retry, idempotency và error classification

Các tests không cần Couchbase thật có thể dùng fake gateway để mô phỏng failure sequences mà không phá hoại cluster.

| Trường hợp | Hành vi cần xác minh |
| --- | --- |
| Read-only KV bị transient timeout một lần | Retry có giới hạn theo classifier, giữ cùng logical request |
| KV read trả not-found hợp lệ | Không retry vô ích, trả 404/domain outcome |
| Backend permission denied | Không retry vô hạn; error/alert phân loại đúng |
| Create Order nhận ambiguous write | Không sinh key mới; giữ status chưa rõ |
| Retry create cùng key và document đã tồn tại | Verify fingerprint/state, không tạo duplicate |
| Key giống nhưng payload fingerprint khác | Báo conflict thay vì coi idempotent success |
| CAS mismatch | Re-read và kiểm tra business precondition trước retry |
| Transaction callback bị chạy lại | Không gọi payment/email không-idempotent trong callback |
| Query/Index outage, KV khỏe | Circuit breaker Query không chặn route KV lành |
| Breaker open | Từ chối/fallback phù hợp, không gọi SDK liên tục |
| Reactive cancellation | Không log write chắc chắn chưa thực thi |
| Retry attempts quá budget | Fail bounded, không giữ request vô hạn |

### 30.1. Mẫu JUnit với fake phân loại lỗi

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class RetryPolicyContractTest {

    private final RetryDecisionPolicy policy =
            new RetryDecisionPolicy();

    @Test
    void readOnlyTransientFailureMayRetryWithBudget() {
        assertTrue(policy.shouldRetry(
                "kv_get",
                FailureCategory.TRANSIENT_UNAVAILABLE,
                1,
                true));
    }

    @Test
    void permissionFailureMustNotRetry() {
        assertFalse(policy.shouldRetry(
                "kv_get",
                FailureCategory.PERMISSION_DENIED,
                1,
                true));
    }

    @Test
    void ambiguousNonIdempotentWriteMustNotRetryBlindly() {
        assertFalse(policy.shouldRetry(
                "create_order",
                FailureCategory.AMBIGUOUS_OUTCOME,
                1,
                false));
    }
}

// RetryDecisionPolicy / FailureCategory là abstraction
// của ứng dụng cần tự triển khai; ví dụ mô tả contract test.
~~~

Mục tiêu là chứng minh **chính sách của application**, không giả định SDK có chính những enum/classes này. Test phải bổ sung deadline/attempt cap và state verification logic, không chỉ một boolean.

### 30.2. Test log và metrics không được lộ PII

Dùng sample customer/email giả rồi assert logs/tags không chứa raw values. Đo `retry_attempts`, `ambiguous_pending` và `deduplicated_commands` bằng labels service/operation/outcome hữu hạn, không dùng idempotencyKey làm Prometheus label.

## 31. Integration/fault tests trên cluster lab có kiểm soát

Trên **cluster thử nghiệm được ủy quyền**, có số nodes/replicas và service placement gần production, thiết kế các pha:

1. Baseline: healthy KV read/write và SQL++ query trên GSI online.
2. Warm-up SDK/Java application, ghi p95/p99 và error baseline.
3. Tạo một Order với key cố định/fixture riêng, xác nhận trạng thái.
4. Bắt đầu rebalance **trên lab**, vừa thực hiện workload có giới hạn.
5. Theo dõi SDK endpoint reports, KV errors, Query p99, Index backlog.
6. Thử ngắt kết nối từ **một client/pod lab**, phân biệt với node failover.
7. Thử node failover lab khi cluster được thiết kế đủ replica và có rollback.
8. Trong write ambiguity test, kiểm tra hệ thống không tạo duplicate với cùng key.
9. Trong transaction test, kiểm tra callbacks không thực hiện side effect ngoài.
10. Sau recovery, kiểm tra query freshness, outstanding operations và latency.
11. Thu metadata cần thiết, cleanup fixtures, khôi phục topology.
12. Báo RTO/RPO thực đo và những giới hạn của thí nghiệm.

### 31.1. Bảng kỳ vọng trước khi thử

| Phép thử | Điều cần ghi nhận | Không được giả định |
| --- | --- | --- |
| Data node bị mất trong lab | KV routing recovery/error/latency | Mọi write đều survived nếu không xét durability |
| Rebalance | Tail latency, Index backlog, recovery time | Zero latency impact |
| Client network partition | SDK config/endpoint errors ở một pod | Cluster chắc đã failover |
| Query Service unavailable | SQL++ failure, KV có thể còn OK | Tất cả service chết |
| GSI rebuild/lag | Query plan/freshness/REQUEST_PLUS wait | Query Engine `SELECT RAW 1` fail |
| Commit response thất lạc | Unknown transaction outcome handling | Exception đồng nghĩa chắc rollback |
| Full outage | Circuit breaker/bulkhead/load shedding | Retry vô hạn giúp phục hồi |

### 31.2. Không fault-inject lên production

Các thao tác network cut, rebalance, failover, kill node, shrink disk hoặc thay NetworkPolicy có thể gây data availability/correctness impact. Chỉ làm trong lab theo authorization, plan và rollback. Không tự kích hoạt destructive operations chỉ để xem metrics.

### 31.3. Không assert thời gian phục hồi cố định

Một test `Thread.sleep(500)` rồi assert phải phục hồi có thể flaky/thiếu thực tế. Dùng bounded eventual assertions theo budget test, ghi thời gian thực tế và xem lỗi nếu quá limit; cluster size, workload và topology khác nhau cho hành vi khác nhau.

## 32. Runbook cho on-call: từ triệu chứng đến phục hồi

~~~mermaid
flowchart TD
    A["Orders API gặp timeout/5xx"] --> B{"KV, Query hay nhiều dịch vụ?"}
    B --> K["KV: key/vBucket, active owner, SDK endpoints"]
    B --> Q["SQL++: Query engine, GSI, consistency"]
    B --> M["Nhiều dịch vụ: network, auth, topology"]
    K --> C{"Write outcome ambiguous?"}
    C -->|Có| V["Giữ key, verify state, reconciliation"]
    C -->|Không| D["Xem timeout/retry/failure classification"]
    Q --> D
    M --> D
    V --> E["Xem failover/rebalance timeline"]
    D --> E
    E --> F["Đo latency/errors/backlog và sửa root cause"]
    F --> G["Kiểm chứng SLO + business correctness"]
~~~

**Thứ tự thực hiện:**

1. Xác định thời điểm, route, error rate, p95/p99, phạm vi pod/node/service.
2. Phân loại KV read, KV mutation, SQL++/GSI, transaction, Search/Analytics.
3. Đối chiếu failover/rebalance events, SDK topology/endpoint diagnostics, network/DNS/TLS/RBAC.
4. Với KV, xem vBucket owner/reachability và read-only operation trên đúng collection.
5. Với write timeout, xác định ambiguous/unambiguous từ SDK/error context, **không tự kết luận chưa ghi**.
6. Khoanh logical command/idempotency key; tránh tạo ID mới hoặc gọi side effects lần nữa.
7. Với SQL++, thử Query Engine tối thiểu, query thực và `EXPLAIN`; xem Index online/backlog.
8. Đo Query/Index CPU, memory, disk I/O, Query queue và Index mutation backlog riêng.
9. Xem timeout budget, retry amplification, app waiting/breaker/half-open probes.
10. Nếu chỉ một pod lỗi, kiểm tra đường mạng và secrets/config đúng pod đó.
11. Nếu nhiều pods lỗi vì shared dependency, không dùng restart hàng loạt làm cách sửa mặc định.
12. Thực hiện fix đúng root cause: routing, cert, RBAC, capacity, index plan, resource pressure.
13. Giảm tải/retry theo policy nếu cần, nhưng giữ consistency và durability contract.
14. Sau phục hồi, xác minh command pending, duplicates, transaction outcomes và user-visible state.
15. Đo lại KV/SQL++ p95/p99, error rates, SDK retry rates, Index freshness và readiness.
16. Tắt debug/profiling tạm, lưu postmortem với các trường đã redacted.

### 32.1. Khi nào escalation?

Escalate sang DBA/cluster operator khi cần xác minh failover state, replica topology, GSI rebuild, resource quotas hoặc dữ liệu không thể truy cập. Sang network/SRE khi lỗi chỉ một zone/pod/route. Sang nhóm ứng dụng khi idempotency, duplicate payment, CAS state machine hoặc external side effects có nguy cơ sai.

### 32.2. Phân biệt mitigation và khắc phục nguyên nhân

Giảm report concurrency có thể giúp Query Service phục hồi tạm thời nhưng không sửa missing index hoặc storage quota. Tăng timeout có thể giảm lỗi ở workload hợp lý nhưng không sửa RBAC/hostname TLS sai. Ghi rõ mitigation tạm và action lâu dài.

## 33. Những ngộ nhận vận hành cần tránh

1. “Có replica là không bao giờ mất write.” — Phụ thuộc durability, placement, ACK và sự cố.
2. “Network timeout nghĩa server chưa ghi.” — Có thể mất ACK sau khi commit.
3. “Retry POST với UUID mới luôn an toàn.” — Có thể tạo Order trùng.
4. “CAS conflict là lỗi kết nối.” — Thường là optimistic concurrency.
5. “Tăng retry vô hạn làm failover nhanh hơn.” — Có thể tạo retry storm.
6. “SDK tự retry nên application không cần deadline.” — Vẫn cần HTTP budget và domain error handling.
7. “Transaction callback chạy đúng một lần.” — Có thể được chạy lại; tránh external side effects.
8. “SDK transaction exception chắc chắn rollback.” — Một số commit outcomes cần xác minh.
9. “KV UP nghĩa SQL++/GSI cũng UP.” — Đường dịch vụ khác.
10. “Index online nghĩa Query thấy ngay mutation mới.” — Có thể có backlog.
11. “REQUEST_PLUS chậm thì đổi NOT_BOUNDED vô điều kiện.” — Có thể vi phạm freshness.
12. “Failover trong cluster đồng nghĩa chuyển sang region B.” — XDCR/multi-cluster cần routing/DR riêng.
13. “Ping seed host thành công chứng minh mọi discovered endpoint reachable.” — Chưa đủ.
14. “Một pod timeout nghĩa cluster chết.” — Có thể NetworkPolicy/secret/zone issue.
15. “Liveness phải DOWN mỗi khi database lỗi.” — Restart storm có thể làm outage nặng hơn.
16. “Đưa mọi dependency vào readiness là luôn đúng.” — Có thể làm mọi pod NotReady.
17. “Breaker có thể giải quyết exactly-once.” — Cần idempotency/reconciliation.
18. “404 do TTL là database outage.” — Có thể là expected expiry.
19. “Health `UP` nghĩa dữ liệu đã đủ mới.” — Freshness SLO riêng.
20. “Tăng permits luôn cải thiện throughput.” — Khi server saturation có thể làm p99 xấu.
21. “Cắt network trên production là phép thử bình thường.” — Rủi ro dữ liệu và availability.
22. “Query Engine SELECT RAW 1 pass nghĩa named GSI online.” — Câu query không dùng GSI.
23. “Một môi trường test 1 node chứng minh HA.” — Không có topology tương đương.
24. “Rebalance kết thúc là mọi request pending đã reconcile.” — Cần theo dõi domain state.
25. “Không thấy exception tức mọi order đúng.” — Có thể có duplicate/missing side effects.
26. “Có thể log raw SDK diagnostics ra public API.” — Rò rỉ topology/credentials.
27. “Reactive cancel đồng nghĩa server dừng write.” — Không chắc.
28. “HTTP 202 có thể che một mutation chưa xác định.” — Chỉ dùng khi có durable accepted state.

## 34. Bài tập tình huống

### A. POST /orders timeout trong failover

Client retry với UUID mới và thấy hai đơn hàng.

**Hướng giải:** Dùng idempotency key ổn định, insert theo key duy nhất, verify fingerprint, xử lý ambiguous outcome. Thiết kế status query/reconciliation cho logical command.

### B. Rebalance làm SQL++ p99 tăng, KV vẫn nhanh

**Hướng giải:** Kiểm tra Query/Index capacity, named GSI state, Index mutation backlog, `EXPLAIN` và consistency wait. Không gọi toàn cluster DOWN.

### C. Pod A kết nối tốt, pod B bị timeout sau topology change

**Hướng giải:** So DNS/TLS, discovered endpoints, NetworkPolicy/zone, alternate addresses và SDK diagnostics ở từng pod.

### D. CAS conflict sau retry

Một update PAID đã có thể thành công nhưng caller không nhận ACK; retry gặp CAS mismatch.

**Hướng giải:** Đọc lại trạng thái bằng key và xác minh command/state, không tự coi tất cả conflict là writer khác hoặc đổi CAS để ghi đè.

### E. Query REQUEST_PLUS timeout sau một đợt write lớn

**Hướng giải:** Đo GSI update backlog/Index Service pressure, freshness SLO và query latency. Không hạ consistency nếu API cần read-after-write.

### F. Liveness restart mọi pods khi Data node offline

**Hướng giải:** Tách liveness process khỏi database dependency; readiness/alerts theo traffic contract, tránh reconnect storm.

### G. Transaction callback gọi payment gateway

Failover làm callback được chạy lại.

**Hướng giải:** Chuyển side effect ra state machine/outbox sau commit có xác minh và idempotency với payment provider.

### H. Query breaker mở nhưng KV vẫn khỏe

**Hướng giải:** Chia breaker theo capability; Query outage không tự chặn KV detail route.

### I. Một client hủy reactive HTTP request

**Hướng giải:** Đừng coi `Mono` cancel là rollback của KV write; nếu mutation đã gửi, cần idempotency/reconciliation.

### J. Cross-region switch sang B có data stale

**Hướng giải:** XDCR freshness/RPO, conflict policy và routing sang cluster B là bài toán DR riêng; `REQUEST_PLUS` ở A không làm B bắt kịp.

## 35. Checklist trước production

- [ ] Mỗi use case có dependency map KV, Query, Index, Search và service khác khi cần?
- [ ] Biết khác nhau giữa failover, rebalance, client network partition và service outage?
- [ ] SDK Cluster/Bucket/Collection được tái sử dụng, không connect mới mỗi request?
- [ ] Seed DNS, discovered endpoints, TLS và alternate addresses được kiểm chứng?
- [ ] Replica/vBucket placement và failover policy được hiểu đúng topology?
- [ ] KV read not-found/TTL được tách khỏi timeout/unavailable?
- [ ] Write outcome ambiguous có state và reconciliation, không trả success/failure giả?
- [ ] Create Order có idempotency key ổn định, fingerprint và collision handling?
- [ ] Client retry dùng cùng key, không sinh UUID mới?
- [ ] CAS/`@Version` và business state machine ngăn lost update?
- [ ] Durability level và backup/replica contract được ghi theo version/topology?
- [ ] Transaction callback không thực hiện side effect ngoại vi không-idempotent?
- [ ] Transaction unknown commit outcome được xử lý bằng logic domain?
- [ ] Query/Index availability và Index freshness được giám sát riêng?
- [ ] `NOT_BOUNDED`, `REQUEST_PLUS` và mutation-based consistency phù hợp SLO?
- [ ] Không dùng SQL++ REQUEST_PLUS query nặng trong readiness?
- [ ] HTTP/SDK/retry/queue timeout budgets được tính như một tổng?
- [ ] Retry classifier loại permission/validation/not-found, có backoff+jitter?
- [ ] Biết SDK retries và application retries có thể chồng nhau?
- [ ] Có circuit breaker/bulkhead/rate limit theo capability thiết yếu?
- [ ] Half-open probe có concurrency/timeout giới hạn?
- [ ] Liveness độc lập Couchbase shared outage?
- [ ] Readiness contract tránh vô ý all-pods-NotReady?
- [ ] Kubernetes probe chạy đúng serving port và có startup/graceful shutdown?
- [ ] Reactive code không `block()` event loop, ghi cancellation riêng?
- [ ] Không coi reactive cancellation là rollback?
- [ ] SDK ping/diagnostics được hiểu theo service/endpoint, không public raw report?
- [ ] Metrics có p95/p99, timeout, ambiguous, retry, in-flight/queue, readiness?
- [ ] Có theo dõi GSI mutation backlog/Index state sau failover/rebalance?
- [ ] Monitoring không dùng document ID/idempotency key làm metric labels?
- [ ] Multi-cluster XDCR/region switch có RTO/RPO và conflict/idempotency plan?
- [ ] Fault-injection tests chỉ chạy trên lab có authorization/rollback?
- [ ] Tests kiểm tra no-duplicate, CAS, transaction, rollback/unknown outcome?
- [ ] Sau recovery có xác minh pending commands, HTTP SLO và data freshness?
- [ ] Có runbook phối hợp SRE/DBA/application và security redaction?

## 36. Kết luận

**Failover, rebalance và gián đoạn mạng không có một hành vi duy nhất cho mọi thao tác Spring Data Couchbase.** KV read có thể phục hồi khi SDK cập nhật topology, trong khi một số writes vẫn có outcome chưa xác định. Query/Index và GSI có thể chậm hoặc chưa mới sau khi KV trở lại bình thường. Transaction và reactive code vẫn phải tôn trọng timeout, retry và cancellation semantics.

Trong **SPRING_DATA_COUCHBASE**, điều quan trọng không chỉ là tự reconnect mà là **giữ đúng bất biến nghiệp vụ khi không thể biết ngay thao tác đã xảy ra hay chưa**: stable idempotency keys, CAS/`@Version`, durability hợp lý, transaction callback không chứa side effect không-idempotent, retry có budget/backoff/jitter và reconciliation cho kết quả chưa rõ. Dùng liveness cho process, readiness cho traffic contract, circuit breaker theo capability và observability theo KV, Query, Index, network và business state.

Một hệ thống được vận hành tốt chỉ được xem là phục hồi khi **khả năng phục vụ, độ trễ, độ mới dữ liệu và tính đúng đắn của các Order đang xử lý** đều đã được xác minh — chứ không chỉ khi node status hoặc health check trở lại màu xanh.
