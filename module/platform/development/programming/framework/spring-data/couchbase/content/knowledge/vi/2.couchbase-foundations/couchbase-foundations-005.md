# Bản sao, chuyển đổi dự phòng và tái cân bằng cụm Couchbase

> **Chương:** Nền tảng Couchbase  
> **Ngữ cảnh:** `SPRING_DATA_COUCHBASE` — xây dựng tầng truy cập Couchbase qua document mapping, repository, `CouchbaseTemplate` và SQL++; hiểu tác động của hạ tầng đến TTL, CAS, transaction, chỉ mục, độ bền ghi, tính nhất quán và API reactive.

## 1. Mục tiêu bài học

Sau bài học, bạn có thể:

1. Phân biệt **data replica**, **index replica**, **XDCR** và **backup**; xác định chính xác loại sự cố mỗi cơ chế có thể giải quyết.
2. Giải thích bản **active** và **replica** của vBucket, điều kiện để tiếp quản khi Data node lỗi và giới hạn về độ mới của bản sao.
3. Phân biệt **failover**, **recovery** và **rebalance**; hiểu quá trình chuyển node bị lỗi thành topology khỏe mạnh trở lại.
4. Đánh giá sự khác nhau giữa failover có kế hoạch, failover khẩn cấp và cấu hình tự động failover.
5. Chọn yêu cầu **durability**, retry/idempotency và chiến lược đọc nhất quán khi thao tác ghi có thể bị gián đoạn.
6. Liên hệ hành vi cluster với **Spring Data Couchbase**: `save`, `findById`, repository query SQL++, `@Version`, CouchbaseTemplate và reactive API.
7. Lập kế hoạch năng lực dự phòng, theo dõi hệ thống và diễn tập một node không khả dụng.

## 2. Vì sao cần bản sao và cơ chế chuyển đổi dự phòng?

Một cluster Couchbase thường chạy trên nhiều node. Để cung cấp dịch vụ ổn định khi phần cứng hoặc mạng lỗi, Couchbase có thể tạo **replica dữ liệu** trên những Data node khác. Khi một Data node không còn phục vụ, cluster có thể chuyển vai trò của các phân vùng dữ liệu liên quan sang bản sao đủ điều kiện.

Điều này hỗ trợ mục tiêu **high availability** (tính sẵn sàng cao), nhưng cần phân biệt ba mục tiêu:

| Mục tiêu | Câu hỏi | Cơ chế liên quan |
|---|---|---|
| **Availability** | Khi một node lỗi, ứng dụng có tiếp tục truy cập được không? | Replica, failover, nhiều node cho các service, routing SDK |
| **Durability** | Một ghi đã được xác nhận sẽ tồn tại qua những sự cố nào? | Durability level, trạng thái replica/persistence |
| **Recoverability** | Sau xóa nhầm, hỏng logic hoặc sự cố lớn, có thể lấy lại dữ liệu không? | Backup/restore, kế hoạch DR, có thể thêm XDCR |

Chỉ tạo replica không tự đáp ứng đủ cả ba mục tiêu. Ví dụ, nếu ứng dụng xóa nhầm một đơn hàng, thao tác xóa đó có thể được sao chép sang replica. **Replica không phải bản lưu lịch sử để undo.**

Một bài toán cụ thể:

> Hệ thống bán hàng cần chịu được lỗi một Data node mà vẫn phục vụ thao tác tìm đơn theo ID, truy vấn đơn đã thanh toán và tránh ghi trùng khi client retry.

Ta phải xem xét ít nhất **Data replica, Query/Index Service availability, durability và semantics retry**. Nắm rõ từng lớp giúp thiết kế đúng yêu cầu mà không nhầm một cơ chế thành giải pháp cho mọi lỗi.

## 3. Cơ sở kỹ thuật: vBucket active và replica

Couchbase chia dữ liệu của một bucket thành các **vBucket**, tức phân vùng logic. Tại một thời điểm, một vBucket có một **active** chịu trách nhiệm chính cho thao tác KV và có thể có một số **replica** theo cấu hình bucket và điều kiện cluster.

Ví dụ minh họa cluster ba Data node A, B, C với một data replica:

| vBucket minh họa | Active | Replica |
|---|---|---|
| `V0` | A | B |
| `V1` | B | C |
| `V2` | C | A |
| `V3` | A | C |
| `V4` | B | A |
| `V5` | C | B |

**Các tên V0–V5 chỉ là ví dụ**, không phải số vBucket thực tế hoặc bản đồ do Couchbase trả về. Một Data node thực tế có thể chứa nhiều active và replica vBucket; chúng được phân phối để đáp ứng topology.

~~~mermaid
flowchart LR
    subgraph A["Data node A"]
        A0["V0 active"]
        A2["V2 replica"]
    end
    subgraph B["Data node B"]
        B0["V0 replica"]
        B1["V1 active"]
    end
    subgraph C["Data node C"]
        C1["V1 replica"]
        C2["V2 active"]
    end
    A0 -->|"Data replication"| B0
    B1 -->|"Data replication"| C1
    C2 -->|"Data replication"| A2
~~~

Document `order::1001` trong `commerce.sales.orders` được SDK ánh xạ vào một vBucket dựa trên khóa. Khi SDK gọi `get("order::1001")`, nó sử dụng **vBucket map** để định tuyến tới Data node giữ bản active. Collection là không gian tên logic; ứng dụng không tự chọn node lưu document.

### Active và replica khác nhau ở đâu?

- **Active vBucket:** nhận và phục vụ những thao tác KV bình thường với document thuộc phân vùng đó.
- **Replica vBucket:** nhận bản sao thay đổi dữ liệu để phục vụ tính sẵn sàng và phục hồi, tùy điều kiện replication/durability.
- **SDK cluster map:** ánh xạ mỗi vBucket đến node active hiện tại, giúp client chuyển đường truy cập khi phân vùng đổi owner.

Replica dữ liệu được duy trì từ hoạt động sao chép thay đổi nội bộ (các cơ chế như DCP tùy vai trò và phiên bản). Mặc định không nên coi replica **luôn đồng bộ tức thì** với active ở mọi thời điểm. Vì thế, khả năng chịu lỗi và mức mất dữ liệu tiềm tàng còn phụ thuộc vào tình trạng sao chép và yêu cầu độ bền của từng mutation.

## 4. Bốn cơ chế thường bị gọi chung là “replication”

| Cơ chế | Cấp dữ liệu / tác dụng | Hỗ trợ tình huống | Không tự giải quyết |
|---|---|---|---|
| **Data replica** | Bản sao vBucket trong cluster | Mất Data node, failover dữ liệu khi có bản sao phù hợp | Backup; lỗi logic; truy vấn SQL++ nếu mất Query/Index Service |
| **Index replica** | Bản sao Global Secondary Index (GSI) | Tăng availability của index khi Index node lỗi | Sao lưu body document hoặc xử lý lỗi Data Service |
| **XDCR** | Cross Datacenter Replication giữa các bucket/cluster theo cấu hình | Sao chép dữ liệu qua cluster/region, hỗ trợ chiến lược DR | Transaction xuyên cluster; bảo đảm không mất dữ liệu trong mọi trường hợp; backup lịch sử |
| **Backup/restore** | Bản lưu độc lập có quy trình phục hồi | Xóa nhầm, lỗi logic, mất dữ liệu diện rộng, phục hồi điểm đã sao lưu | Đáp ứng truy vấn online ngay khi node hỏng |

### 4.1. Data replica nằm trong phạm vi bucket

Cấu hình số lượng data replica gắn với bucket và phải phù hợp số Data node/failure domain khả dụng. **Replica của bucket này không tự bảo vệ bucket khác**; mỗi bucket có cấu hình riêng.

Vì active và replica cần được phân phối hợp lý, không thể kết luận một bucket có thể chịu hỏng bất kỳ số node nào chỉ từ số replica khai báo. Cần kiểm tra placement, dung lượng, nhóm server và trạng thái sức khỏe thực tế.

### 4.2. Index replica không phải data replica

Để truy vấn theo thuộc tính, Query Service thường dùng các GSI của Index Service. Một cluster có đủ data replica nhưng chỉ một bản GSI trên một Index node vẫn có nguy cơ **KV hoạt động trong khi SQL++ bị gián đoạn** nếu index không khả dụng.

Khi cần HA cho SQL++, cân nhắc số **Query node**, replica cho **GSI** và các yêu cầu capacity của Index Service. Chỉ mục có thể được tạo với cấu hình replica phù hợp phiên bản/server; ví dụ cấu hình `num_replica` trong tùy chọn tạo index thường cần đủ Index node khả dụng.

### 4.3. XDCR và backup không đồng nghĩa HA nội cụm

XDCR chủ yếu phục vụ replication giữa các cluster theo topology và chính sách đã thiết kế. Nó thường có tính bất đồng bộ, phụ thuộc lag, conflict resolution và môi trường triển khai. Truyền dữ liệu sang cluster khác **không tự chuyển ứng dụng sang cluster DR**; cần kế hoạch điều phối ứng dụng, DNS, credentials và kiểm tra consistency khi chuyển vùng.

Backup cung cấp điểm khôi phục độc lập, nên phải được kiểm thử restore, bảo vệ quyền và lưu theo chính sách. Một thiết kế trưởng thành có thể dùng **replica + backup**, và bổ sung **XDCR** khi có yêu cầu DR giữa các cluster.

## 5. Failover là gì?

**Failover** là quá trình đưa một node không còn khả năng phục vụ ra khỏi vai trò đang đảm nhiệm và cho cluster tiếp tục hoạt động qua các node còn lại. Với Data Service, cluster có thể **promote** replica vBucket thành active mới khi điều kiện phù hợp.

Ví dụ, trước sự cố:

~~~text
Document ID: order::1001
vBucket: V4 (minh họa)
Active:  node B
Replica: node A
~~~

Khi B lỗi, failover thành công có thể dẫn tới:

~~~text
Active mới của V4: node A
Cluster map được cập nhật
SDK định tuyến get("order::1001") tới A
Document ID và keyspace không thay đổi
~~~

~~~mermaid
sequenceDiagram
    participant App as Spring Data / API
    participant SDK as Couchbase SDK
    participant B as Node B (active cũ)
    participant A as Node A (replica)
    participant C as Cluster management
    App->>SDK: get(order::1001)
    SDK->>B: KV Get theo map cũ
    Note over B: Node B không khả dụng
    SDK-->>App: Có thể timeout/lỗi tạm
    C->>A: Failover và promote vBucket khi đủ điều kiện
    C-->>SDK: Cluster configuration mới
    App->>SDK: Retry có kiểm soát
    SDK->>A: KV Get theo map mới
    A-->>SDK: JSON + metadata
    SDK-->>App: OrderDocument
~~~

Sơ đồ không có nghĩa tất cả các bước diễn ra tức thời. Trong sự cố thật có thể có một khoảng gián đoạn, các thao tác timeout hoặc kết quả mutation không rõ ràng (*ambiguous result*).

### Failover không tự động đồng nghĩa zero data loss

Nếu một mutation đã được active xác nhận nhưng chưa đạt độ bền theo yêu cầu, bản sao được promote có thể chưa có thay đổi cuối cùng. **RPO/RTO** (mức mất dữ liệu và thời gian phục hồi chấp nhận được) phải được định nghĩa và kiểm chứng bằng cấu hình, durability, giám sát và diễn tập.

Failover khác biệt với việc chỉ restart một process. Đặc biệt khi mạng bị phân vùng, quyết định cho node nào làm active phải dựa trên cơ chế quản lý cluster nhằm tránh xung đột owner và dữ liệu không nhất quán.

## 6. Các cách failover và tình huống sử dụng

Couchbase có các cơ chế failover được điều phối bởi quản trị viên hoặc cấu hình tự động, với chi tiết và điều kiện theo phiên bản.

| Kiểu | Bối cảnh | Điểm cần kiểm tra |
|---|---|---|
| **Graceful failover** | Chủ động đưa node khỏe mạnh ra khỏi cluster theo kế hoạch | Khả năng di chuyển/chuyển vai trò an toàn, trạng thái replica, thời gian hoàn thành |
| **Hard failover** | Node đã lỗi hoặc không thể phục vụ bình thường | Replica phù hợp, rủi ro thay đổi chưa được sao chép, capacity sau lỗi |
| **Automatic failover** | Cluster được cấu hình tự phát hiện điều kiện lỗi và thực hiện failover khi đáp ứng ngưỡng | Điều kiện kích hoạt, giới hạn, quorum/chính sách an toàn và tránh failover nhầm khi mạng chập chờn |
| **Manual failover** | Người vận hành quyết định hành động sau khi kiểm tra | Chứng cứ lỗi, sức khỏe cluster, tác động dữ liệu và kế hoạch recovery |

**Graceful** diễn đạt mục tiêu rời node có kiểm soát khi node còn hoạt động và cơ chế hỗ trợ; **hard** dành cho tình huống không thể chờ một quá trình chuyển có phối hợp bình thường. Automatic/manual mô tả **ai kích hoạt**, nên không phải các cặp thuật ngữ có thể thay thế trực tiếp.

Điều kiện khả dụng và giao diện tác vụ khác nhau theo loại service, phiên bản Couchbase Server/Capella và cấu hình. Đừng tự động áp dụng quy trình Data Service cho mọi service khác.

### Những điều cần tránh khi failover

- Không tuyên bố node đã “chết” chỉ vì một API client không kết nối được; kiểm tra DNS, mạng, authentication, advertised addresses và cluster health.
- Không hard failover hàng loạt node khi chưa đánh giá replica, quorum và capacity.
- Không giả định automatic failover sẽ luôn kích hoạt trong mọi tình huống; các điều kiện an toàn có thể ngăn thao tác.
- Không coi việc SDK timeout là bằng chứng transaction/mutation chắc chắn thất bại.
- Không quên phục hồi mức redundancy sau khi cluster đã hoạt động trở lại.

## 7. Sau failover: recovery và rebalance

Failover giúp lấy lại khả năng phục vụ trên các node còn lại, nhưng cluster có thể đang **thiếu replica hoặc mất cân bằng phân vùng**. Thường phải tiếp tục xử lý recovery/rebalance.

### 7.1. Recovery là gì?

**Recovery** là quá trình đưa node từng failover hoặc node thay thế trở lại tham gia cluster phù hợp với trạng thái mới. Tùy loại service, tình trạng dữ liệu và phiên bản, Couchbase có thể hỗ trợ các lựa chọn như:

- **Delta recovery:** tái sử dụng dữ liệu có sẵn trên node khi đủ điều kiện để giảm dữ liệu phải sao chép.
- **Full recovery:** khôi phục bằng cách đồng bộ lại đầy đủ phần dữ liệu cần thiết theo cơ chế recovery của cluster.

Không phải node nào cũng hỗ trợ delta recovery trong mọi trường hợp. Mức an toàn và điều kiện cụ thể phải được kiểm tra qua quản trị cluster; không lựa chọn chỉ vì mong muốn “nhanh hơn”.

### 7.2. Rebalance là gì?

**Rebalance** phân phối lại dữ liệu/vBucket và các tài nguyên service liên quan dựa trên topology hiện hành. Các trường hợp phổ biến:

1. **Thêm Data node:** phân phối một phần active/replica vBucket sang node mới.
2. **Rời Data node có kế hoạch:** chuyển phân vùng để node cũ có thể được loại khỏi cluster.
3. **Sau failover/recovery:** phân bổ lại phân vùng, xây dựng lại mức replica mong muốn khi có đủ điều kiện.
4. **Thay đổi topology các service khác:** ví dụ Index Service có quy trình phân phối tài nguyên chỉ mục riêng.

~~~mermaid
flowchart TD
    S["Cluster 3 Data node"]
    F["Node B failover"]
    P["Replica phù hợp được promote"]
    H["Cluster phục vụ trên các node còn lại"]
    N["Thêm/khôi phục node và lập kế hoạch recovery"]
    R["Rebalance"]
    V["Kiểm tra placement, replica, health và tải"]
    S --> F
    F --> P
    P --> H
    H --> N
    N --> R
    R --> V
~~~

Lưu ý: **failover, recovery và rebalance là ba hành động khác nhau**. Failover có thể xảy ra trước, còn rebalance có thể được thực hiện sau khi sửa lỗi hạ tầng. Một node được thêm vào cluster chưa chắc đã giữ phân vùng mong muốn cho tới khi quá trình rebalance hoàn thành.

### 7.3. Điều gì thay đổi ở SDK?

SDK duy trì cấu hình topology/vBucket map. Khi active owner thay đổi, một yêu cầu có thể đi tới node cũ và nhận phản hồi như `NOT_MY_VBUCKET` hoặc lỗi/timeout tùy tình huống. SDK chính thức làm mới cấu hình và retry theo chính sách.

Ứng dụng **không cần đổi document ID, không tự tính lại hash và không tự sửa bảng server chứa khóa**. Điều cần thiết là quản lý timeout, idempotency và trạng thái nghiệp vụ khi một mutation có kết quả chưa xác định.

## 8. Rebalance có chi phí và có thể ảnh hưởng hiệu năng

Di chuyển phân vùng là công việc thực. Couchbase có thể cần truyền dữ liệu qua mạng, đọc/ghi đĩa và phối hợp trạng thái active/replica. Vì vậy trong quá trình rebalance:

- CPU, memory, disk I/O và network của Data node có thể tăng.
- Độ trễ KV p95/p99, số timeout hoặc retry có thể tăng trong lúc tải cao.
- Chỉ mục/truy vấn có thể bị ảnh hưởng nếu đồng thời thay đổi Index node hoặc cluster thiếu tài nguyên.
- Các công việc lớn như import, backup, xây dựng index hoặc batch mutation có thể cạnh tranh tài nguyên.

Rebalance **không phải bản sao lưu** và cũng không tự tối ưu mọi SQL++ query. Một chỉ mục tệ vẫn có thể khiến truy vấn chậm sau khi Data Service đã được cân bằng tốt.

### 8.1. Kế hoạch capacity khi mất một node

Giả sử cluster có ba Data node và thiết kế chịu lỗi một node. Cần trả lời:

- Nếu một node hỏng, hai node còn lại có **đủ RAM, đĩa, CPU và network** để tiếp tục phục vụ không?
- Replica đã được phân bổ trên những node/failure domain độc lập chưa?
- Query/Index Service có đủ bản hoạt động và tài nguyên dự phòng không?
- SLA latency dưới tải khi thiếu một node là bao nhiêu? Có giới hạn mức ghi/đọc hoặc cơ chế giảm tải không?
- Khi rebuild replica, hệ thống còn đủ dung lượng trống cho quá trình chuyển không?

Không có tỷ lệ “dự phòng 20% là luôn đủ” áp dụng cho mọi workload. Phải đo N-1 capacity trên dữ liệu đại diện, đặc biệt với key nóng và index maintenance lớn.

### 8.2. Failure domain: node, rack, availability zone

Nếu active và replica nằm ở hai node nhưng cùng điểm lỗi mạng/nguồn điện, chúng có thể cùng mất. Khi nền tảng hỗ trợ **server groups/placement awareness**, hãy xét cấu hình phân bố replica qua failure domain phù hợp.

Một cấu hình ba node trên cùng một host vật lý hoặc cùng một ổ đĩa nền chưa chắc thực sự chịu được lỗi host/rack. Kiểm tra kiến trúc hạ tầng thực tế thay vì chỉ đếm số process Couchbase.

## 9. Durability: “ghi thành công” được bảo đảm tới đâu?

Replica mặc định có thể nhận thay đổi không đồng thời với phản hồi mà ứng dụng thấy. Khi cần bảo đảm cao hơn, Couchbase hỗ trợ những mức **synchronous durability** cho mutation, tùy loại bucket, server và SDK.

| Mức | Ý nghĩa khái quát | Ảnh hưởng vận hành |
|---|---|---|
| Không yêu cầu synchronous durability bổ sung | Thao tác được ack theo semantics mặc định | Độ trễ thấp hơn nhưng có thể chưa đạt mục tiêu replica/persistence cao |
| `MAJORITY` | Cần xác nhận bởi đa số thành viên dữ liệu liên quan theo cơ chế durability | Có thể chờ sao chép lâu hơn |
| `MAJORITY_AND_PERSIST_TO_ACTIVE` | Đa số xác nhận, active đã persist theo yêu cầu | Tăng ràng buộc storage I/O |
| `PERSIST_TO_MAJORITY` | Đã persist tới đa số theo semantics hỗ trợ | Chi phí/độ trễ có thể cao hơn |

Các mức này **không phải cam kết tuyệt đối** trước mọi lỗi thảm họa hoặc lỗi logic; cần đối chiếu cấu hình, số replica, failure domain và kết quả kiểm thử.

### 9.1. Ví dụ Java SDK yêu cầu durability

~~~java
import static com.couchbase.client.java.kv.InsertOptions.insertOptions;
import com.couchbase.client.core.msg.kv.DurabilityLevel;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;

String orderId = "tenant::42::order::1001";
JsonObject body = JsonObject.create()
        .put("tenantId", "42")
        .put("status", "NEW")
        .put("total", 1490000);

orders.insert(
        orderId,
        body,
        insertOptions().durability(DurabilityLevel.MAJORITY)
);
~~~

Ở đây `orders` là `Collection` trỏ tới `commerce.sales.orders`. Ví dụ dùng **Java SDK** trực tiếp để chỉ rõ durability; khi dùng Spring Data repository/template, cần kiểm tra API và cấu hình của phiên bản thực tế để truyền chính sách phù hợp.

Dùng `insert` với ID ổn định cho phép phát hiện duplicate, có ích khi client retry. Tuy nhiên thao tác không tự trở thành giao dịch nhiều document.

### 9.2. CAS khác durability

**CAS** là token phiên bản để phát hiện cập nhật cạnh tranh trên một document:

~~~java
import static com.couchbase.client.java.kv.ReplaceOptions.replaceOptions;

var old = orders.get(orderId);
var nextBody = old.contentAsObject().put("status", "PAID");

orders.replace(
        orderId,
        nextBody,
        replaceOptions()
                .cas(old.cas())
                .durability(DurabilityLevel.MAJORITY)
);
~~~

Trong ví dụ:

- `cas(old.cas())` bảo vệ khỏi ghi đè khi có một mutation khác xảy ra.
- `durability(MAJORITY)` đặt yêu cầu độ bền cho mutation được chấp nhận.
- Hai cơ chế giải quyết **hai loại rủi ro khác nhau**.

CAS không bảo đảm dữ liệu đã được sao lưu, và durability không thay thế kiểm tra trạng thái nghiệp vụ trước khi đổi `NEW → PAID`.

## 10. Kết quả ghi không xác định và retry an toàn

Khi node failover hoặc mạng gián đoạn, ứng dụng có thể nhận timeout dù request đã tới server. Có ba tình huống:

~~~text
Trường hợp A: request chưa được thực hiện
Trường hợp B: mutation đã thực hiện, response bị mất
Trường hợp C: mutation bị gián đoạn khi thay đổi owner, trạng thái không rõ
~~~

**Timeout không đồng nghĩa “chắc chắn chưa ghi”.** Nếu API tạo đơn mới rồi retry bằng một ID ngẫu nhiên khác, cùng một yêu cầu nghiệp vụ có thể tạo hai đơn.

### Thiết kế idempotency

Giả sử client gửi `Idempotency-Key: checkout-abc`. Ứng dụng ánh xạ nó sang ID nghiệp vụ ổn định, ví dụ:

~~~text
tenant::42::checkout::checkout-abc
~~~

Sau khi `insert` báo timeout hoặc duplicate:

1. Đọc lại bằng ID đã xác định.
2. Kiểm tra nội dung và trạng thái xử lý có khớp request ban đầu không.
3. Trả kết quả đã lưu hoặc tiếp tục workflow bằng bước có điều kiện.
4. Nếu dữ liệu không khớp, báo xung đột thay vì âm thầm ghi đè.

Với thao tác thanh toán nhiều document, một **transaction** hoặc mẫu xử lý nghiệp vụ có idempotency/saga phù hợp sẽ cần thiết hơn một lệnh KV đơn lẻ.

SDK có logic retry cho một số lỗi mạng/routing, nhưng **ứng dụng vẫn chịu trách nhiệm semantics nghiệp vụ**. Không đặt vòng retry vô hạn ở tầng controller chỉ vì thấy failover xảy ra.

## 11. Read path sau failover: KV, replica read và SQL++

### 11.1. KV theo document ID

~~~java
OrderDocument order = orderRepository
        .findById("tenant::42::order::1001")
        .orElseThrow();
~~~

Tương ứng với `get(id)` thông thường: SDK tìm active vBucket để đọc từ **Data Service**. Khi failover thay owner, SDK cập nhật map và có thể retry. Việc mất Data node vẫn có thể gây lỗi/timeout tạm thời trong khoảng chuyển trạng thái.

### 11.2. Đọc replica không có cùng semantics mặc định

Một số API SDK cho phép `getAnyReplica(id)` hay `getAllReplicas(id)`. Do replica có thể chưa cập nhật theo active, dữ liệu trả về **có thể cũ hơn**. Đọc replica có ích khi nghiệp vụ chấp nhận trade-off độ mới; không tùy tiện dùng cho xác nhận thanh toán hoặc kiểm soát số dư.

### 11.3. SQL++ cần cả Query và Index Service

~~~sql
SELECT META(o).id AS orderId, o.status, o.total
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = "42"
  AND o.status = "PAID";
~~~

Đường này thường cần Query Service, GSI ở Index Service và có thể Fetch dữ liệu từ Data Service. **Data replica không tự thay thế index replica.**

Ngay sau một mutation KV, GSI có thể chưa bắt kịp. Vì vậy kết quả query phụ thuộc **scan consistency**. Với luồng cần read-after-write, có thể dùng KV theo ID, hoặc cấu hình `request_plus`/mutation state khi API hỗ trợ. Tăng scan consistency có thể tăng latency khi chỉ mục đang cập nhật chậm.

Tất cả các vấn đề trên đều tách biệt với việc document ID được định tuyến theo vBucket map.

## 12. Liên hệ trực tiếp với Spring Data Couchbase

Spring Data Couchbase giúp chuyển Java object thành document, truy cập qua `CouchbaseRepository` và `CouchbaseTemplate`. Framework không tự thay thế trách nhiệm HA của cluster; hoạt động còn phụ thuộc SDK, cấu hình service và lifecycle ứng dụng.

### 12.1. Entity mapping và optimistic locking

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

    // Constructor, getter/setter được lược bỏ để tập trung vào mapping.
}
~~~

`@Id` ánh xạ document ID; `@Version` thường dùng CAS để optimistic locking. Khi failover xảy ra, **entity không đổi annotation để chọn node mới**. SDK quản lý cluster map, còn business code phải xử lý lỗi/timeout, CAS conflict và tính idempotent.

### 12.2. Repository theo ID so với theo thuộc tính

~~~java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {

    List<OrderDocument> findByTenantIdAndStatus(
            String tenantId, String status);
}
~~~

- `findById(id)` thường dùng KV đến active Data vBucket.
- `save(order)` thường là mutation KV; độ bền cụ thể cần kiểm tra theo API/configuration.
- `findByTenantIdAndStatus(...)` thường sinh SQL++ và cần GSI phù hợp.
- Spring Data có thể thêm điều kiện phân biệt loại entity (như `_class`) vào query, nên tạo chỉ mục dựa trên SQL++ thực tế.

Trong tình huống KV hoạt động nhưng phương thức query theo thuộc tính thất bại, hãy kiểm tra **Query/Index Service availability và chỉ mục** trước khi quy lỗi cho Data replica.

### 12.3. CouchbaseTemplate và API reactive

`CouchbaseTemplate` cho phép thao tác entity ở mức kiểm soát sâu hơn. Tương tự, `ReactiveCouchbaseRepository` hoặc reactive template vẫn dựa trên SDK và cluster topology giống các API đồng bộ.

~~~java
import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;
import reactor.core.publisher.Flux;

public interface ReactiveOrderRepository
        extends ReactiveCouchbaseRepository<OrderDocument, String> {

    Flux<OrderDocument> findByTenantIdAndStatus(
            String tenantId, String status);
}
~~~

Reactive API có thể giúp xử lý lượng I/O đồng thời lớn hơn, nhưng không làm failover “vô hình” hoặc tự bảo đảm mutation đã hoàn tất. Khi retry reactive stream, hãy đặt giới hạn, phân biệt thao tác đọc/ghi và tránh thực thi mutation không idempotent nhiều lần do resubscribe.

**Quan sát quan trọng:** retry ở tầng Reactor/Spring có thể kích hoạt lại publisher nguồn. Với một pipeline có side effect, `retryWhen` không tự biết kết quả mutation trước đó đã được server xử lý hay chưa.

### 12.4. Cấu hình kết nối ứng dụng

Ứng dụng cần kết nối tới cluster qua endpoint/connection string hợp lệ và dùng Couchbase SDK được hỗ trợ. Trong thực tế:

- Tái sử dụng cluster connection do Spring Boot quản lý; tránh khởi tạo mới cho mỗi HTTP request.
- Bảo đảm SDK có thể kết nối các node/service trong topology, kể cả sau failover.
- Dùng TLS và secret manager/biến môi trường cho credentials.
- Cấu hình KV/query timeout, retry và logging theo SLO; theo dõi lỗi ambiguous.
- Không hard-code một Data node làm nơi duy nhất chứa mọi document.

Một connection string chứa một seed node không đảm bảo cluster luôn bootstrap được nếu seed đó ngừng hoạt động. Hãy sử dụng cơ chế endpoint/DNS hoặc nhiều seed phù hợp môi trường và hướng dẫn triển khai.

## 13. Kịch bản vận hành: mất một trong ba Data node

Giả sử:

- Cluster có ba Data node A, B, C.
- Bucket `commerce` có một data replica.
- Query Service chạy trên ít nhất hai node và các GSI quan trọng có bản sao phù hợp.
- Ứng dụng dùng Spring Data Couchbase để ghi đơn và truy vấn đơn.

### Trạng thái bình thường

~~~text
A/B/C: phân bố active và replica vBucket
Query: có hơn một instance khả dụng
Index: GSI cần thiết có replica khi điều kiện cho phép
Ứng dụng: KV + SQL++ hoạt động
~~~

### Node B bị lỗi

Một số active vBucket nằm trên B bị ảnh hưởng. Cluster phát hiện lỗi, đánh giá điều kiện failover và có thể promote replica trên A/C. Trong lúc chuyển:

- Một số `findById` có thể timeout tạm thời.
- Mutation đã gửi có thể có kết quả ambiguous.
- Query SQL++ có thể chịu ảnh hưởng do thiếu Data node hoặc thay đổi Query/Index availability nếu B chạy nhiều service.
- Khi owner được cập nhật, SDK định tuyến tới active mới.
- A và C có thể chịu tải cao hơn.

### Sau khi service được khôi phục

Cluster vẫn có thể thiếu mức replica mong muốn và capacity dự phòng. Người vận hành cần:

1. Xác minh dữ liệu và tình trạng cluster trên các node còn lại.
2. Kiểm tra GSI replica/Query Service, không chỉ số vBucket active.
3. Sửa hoặc thay node B, chọn phương án recovery phù hợp.
4. Rebalance để phân phối lại dữ liệu/tài nguyên và khôi phục redundancy.
5. Kiểm tra ứng dụng dưới tải đại diện: KV, SQL++, mutation durability và latency.
6. Đối chiếu các mutation ambiguous với ID nghiệp vụ, không ghi lại hàng loạt một cách mù quáng.

**Một cluster hai node còn hoạt động sau failover không nhất thiết còn khả năng chịu lỗi thêm một node.** Vì vậy hệ thống chỉ thật sự quay lại trạng thái mong muốn khi capacity, replica và các service quan trọng đã được phục hồi/kiểm chứng.

## 14. Runbook cho failover có kế hoạch và sự cố

### 14.1. Rời node theo kế hoạch

Trước đợt bảo trì:

1. Xác nhận node/service cần rời, tình trạng replica và placement trong cluster.
2. Kiểm tra tải hiện tại, dự trữ dung lượng và mức ảnh hưởng dự kiến.
3. Chọn cơ chế rời node/graceful failover hoặc remove/rebalance phù hợp với server/version.
4. Theo dõi tiến trình và lỗi; hạn chế triển khai các công việc nặng không cần thiết đồng thời.
5. Xác nhận các active owner, index, query endpoint và ứng dụng hoạt động ổn định.
6. Chỉ tiếp tục bước nâng cấp/bảo trì kế tiếp khi kiểm tra sau chuyển trạng thái đạt yêu cầu.

Không nên tự động hard failover một node đang khỏe chỉ vì muốn hoàn thành thao tác nhanh hơn.

### 14.2. Node mất đột ngột

Khi xuất hiện cảnh báo:

1. Khoanh vùng: lỗi node, mạng, storage hay client routing?
2. Kiểm tra cluster health và data/index replicas còn khả dụng.
3. Xác định failover đã xảy ra tự động chưa, có bị chặn do điều kiện an toàn không.
4. Đánh giá RPO/RTO, cấp độ incident và tính nhất quán của mutation quan trọng.
5. Nếu cần thao tác thủ công, thực hiện theo quy trình đã diễn tập và điều kiện chính thức của môi trường.
6. Sau khi hệ thống phục vụ trở lại, lập kế hoạch recovery/rebalance, backup verification và postmortem.

**Không dùng lệnh xóa node, reset cluster hoặc buộc failover khi chưa xác định phạm vi tác động.** Bài học này cung cấp quy trình quyết định; cú pháp CLI/API quản trị thay đổi theo Couchbase Server/Capella và phiên bản, nên không áp dụng một lệnh cố định cho mọi môi trường.

### 14.3. Một mẫu bảng quyết định sự cố

| Câu hỏi | Nếu câu trả lời là “không” | Hệ quả |
|---|---|---|
| Có replica dữ liệu hợp lệ? | Không chắc promote được active mới | Điều tra dữ liệu/khả năng phục hồi trước thao tác mạnh |
| Các node còn lại đủ tài nguyên? | Có thể phục vụ chậm hoặc tiếp tục lỗi | Giảm tải/cấp thêm capacity theo kịch bản |
| Query Service còn endpoint hoạt động? | SQL++ có thể không khả dụng | Khôi phục Query capacity/routing |
| GSI quan trọng có replica khả dụng? | Query có thể lỗi hoặc xuống hiệu năng | Khôi phục/tạo lại chỉ mục theo kế hoạch |
| Mutation có ID/idempotency? | Retry có nguy cơ tạo bản ghi trùng | Bổ sung kiểm tra trạng thái nghiệp vụ |
| Có backup đã thử restore? | Khó khôi phục lỗi logic/mất dữ liệu nặng | Ưu tiên hoàn thiện phục hồi độc lập |

## 15. Metrics và cảnh báo nên theo dõi

Đừng chỉ nhìn cluster “xanh”. Hãy đo liên tục **sức khỏe hạ tầng** và **hành vi ứng dụng**:

| Nhóm | Chỉ số gợi ý | Vì sao cần |
|---|---|---|
| Topology | Node/service status; failover events; rebalance progress | Phát hiện biến động và trạng thái chưa hoàn tất |
| Data redundancy | Active/replica vBucket placement; trạng thái replica | Biết mức chịu lỗi thực tế của bucket |
| Data resource | CPU, RAM, disk usage/I/O, network, queue | Phát hiện thiếu tài nguyên sau failover |
| KV API | Số request, p50/p95/p99, timeout, retry, ambiguous outcomes | Đánh giá khả năng phục vụ và rủi ro mutation |
| Query Service | Query latency, timeout, concurrent requests | Tách lỗi SQL++ khỏi lỗi KV |
| Index Service | Index availability, replicas, index lag / backlog | Đánh giá độ mới và năng lực truy vấn |
| Durability | Durability failures/timeouts; replication-related health | Xác định ghi quan trọng có đạt yêu cầu không |
| DR | Backup success, restore drill, XDCR lag nếu dùng | Bảo đảm có đường khôi phục ngoài HA trong cluster |

Tên metric và API theo dõi có thể khác theo Couchbase Server, Capella và phiên bản SDK. Trước khi đặt ngưỡng cảnh báo, cần hiểu một số metric là **trạng thái tuyệt đối**, một số là **rate**, và một số là **histogram latency**.

### SLO quan sát trên ứng dụng

Một dashboard hữu ích có thể phân tách:

~~~text
Order API
  - KV read by ID: p95, p99, error/timeout
  - KV create/replace: p95, ambiguous outcomes
  - SQL++ list orders: p95, query timeout, index scan
  - Business duplicates/conflicts: insert duplicate, CAS conflict
~~~

Độ trễ tốt lúc cluster bình thường chưa chứng minh HA thành công. Nên đo cả **trong failover**, **sau failover thiếu một node** và **trong rebalance phục hồi**.

## 16. Diễn tập và kiểm chứng thiết kế

Một kế hoạch diễn tập có kiểm soát nên sử dụng **môi trường thử nghiệm hoặc quy trình được phê duyệt**, có lưu baseline và tiêu chí thành công:

| Bài thử | Hành động | Điều cần xác minh |
|---|---|---|
| Mất một Data node | Mô phỏng failure theo cơ chế kiểm thử của môi trường | Failover điều kiện phù hợp; KV phục hồi; không có nhân bản nghiệp vụ |
| Mất Query node | Dừng một Query instance trong môi trường thử | SQL++ còn đường phục vụ nếu có node khác |
| Mất Index node | Mô phỏng một Index node không khả dụng | Chỉ mục replica được phục vụ; query quan trọng không lỗi dài |
| Rebalance thêm node | Thêm Data node và rebalance | vBucket distribution, độ trễ và capacity sau chuyển |
| Mutation ambiguous | Ngắt kết nối có kiểm soát giữa write và response | Retry giữ nguyên ID/idempotency, không tạo trùng |
| CAS conflict | Hai request cùng cập nhật document | Một request bị từ chối hoặc xử lý conflict theo nghiệp vụ |
| Restore drill | Khôi phục một tập dữ liệu từ backup | Dữ liệu, index, quyền và ứng dụng hoạt động trên môi trường khôi phục |

Không có diễn tập nào bảo đảm 100% mọi loại sự cố; cần cập nhật lại khi thay topology, dữ liệu, SDK hay chính sách durability.

## 17. Bài tập tự đánh giá

### Bài tập A — bản sao bảo vệ điều gì?

Bucket `commerce` có một data replica. Một Data node hỏng; replica còn tốt. Một người vận hành nói: “Không cần backup nữa vì đã có replica.”

**Hãy phản biện:** replica giúp giữ availability khi mất node, nhưng xóa nhầm, corruption logic hoặc thảm họa ảnh hưởng toàn cluster vẫn cần backup/restore và kế hoạch DR.

### Bài tập B — KV vẫn chạy nhưng SQL++ bị lỗi

Sau khi mất một Index node, `repository.findById(id)` vẫn trả document, còn `repository.findByTenantIdAndStatus(...)` thất bại.

**Giải thích:** `findById` thường dùng Data Service/KV; derived query thường dùng SQL++ và GSI. Kiểm tra Query Service, Index Service, index replica và câu SQL++ sinh thực tế trước khi tăng Data replica.

### Bài tập C — tính nhất quán sau failover

Ứng dụng thực hiện `insert(orderId, ...)` và nhận timeout. Ngay sau đó retry bằng ID ngẫu nhiên khác tạo hai đơn. Thiết kế lại luồng tạo đơn để bảo đảm **idempotent theo yêu cầu** và nêu cách xác minh mutation có kết quả ambiguous.

### Bài tập D — dự phòng công suất

Cluster ba Data node, một data replica, hoạt động bình thường gần hết dung lượng đĩa. Có thể tuyên bố chắc chắn chịu được lỗi một node và rebalance an toàn không?

**Gợi ý:** không; phải đánh giá dung lượng, placement, tốc độ ghi, index services và khả năng chuyển dữ liệu sau failover. Replica cấu hình không thay thế capacity planning.

### Bài tập E — failover và recovery

Sắp xếp và giải thích các thao tác sau: node B lỗi, replica phù hợp trở thành active, SDK cập nhật map, node thay thế gia nhập, rebalance khôi phục phân phối và mức replica.

### Bài tập F — Spring Data + CAS + durability

Entity có `@Id` và `@Version`. Nghiệp vụ yêu cầu không ghi đè trạng thái đơn khi có hai request song song và hạn chế mất dữ liệu sau node failure. Hãy chỉ ra cơ chế cần cho **concurrency**, cơ chế cần cho **durability**, và lý do vì sao cả hai vẫn chưa thay thế transaction đa document hoặc idempotency.

## 18. Checklist triển khai

- [ ] Xác định RPO, RTO và availability cho KV, SQL++ và nghiệp vụ quan trọng.
- [ ] Cấu hình **data replica** theo bucket, kiểm tra active/replica placement và failure domain.
- [ ] Bố trí đủ **Query/Index availability**, tạo index replica cho truy vấn thiết yếu.
- [ ] Có **backup/restore** độc lập và lịch diễn tập; đánh giá XDCR khi cần DR liên cluster.
- [ ] Đo khả năng phục vụ dưới tải khi mất một Data node (**N-1 capacity**).
- [ ] Phân biệt failover, recovery, rebalance; có runbook cho từng loại.
- [ ] Xác nhận automatic failover và giới hạn của nó trên phiên bản triển khai.
- [ ] Đặt durability level phù hợp cho mutation quan trọng.
- [ ] Xử lý timeout/ambiguous write bằng ID/idempotency và kiểm tra trạng thái.
- [ ] Dùng CAS optimistic locking cho cập nhật cạnh tranh; transaction cho nghiệp vụ nhiều document khi thích hợp.
- [ ] Phân biệt KV theo ID với SQL++ theo thuộc tính và scan consistency.
- [ ] Theo dõi replica health, failover/rebalance, SDK retry, p95/p99 KV/query latency và index lag.
- [ ] Với reactive repository, kiểm soát `retryWhen`, concurrency và resubscribe có side effect.
- [ ] Sau sự cố, khôi phục capacity và replica trước khi tuyên bố trạng thái HA đã hoàn toàn phục hồi.

## 19. Kết luận

**Bản sao dữ liệu giúp một cluster Couchbase có cơ sở để tiếp tục phục vụ khi Data node lỗi; failover đưa phân vùng sang owner còn hoạt động; recovery và rebalance phục hồi topology và mức dự phòng mong muốn.** Ba nhóm thao tác phục vụ những giai đoạn khác nhau của một sự cố. Để truy vấn SQL++ tiếp tục hoạt động, hệ thống còn cần Query/Index Service và replica chỉ mục tương ứng; để khôi phục mất dữ liệu do lỗi logic cần backup/restore độc lập.

Trong **Spring Data Couchbase**, repository, `CouchbaseTemplate` và API reactive dựa trên Couchbase SDK để nhận cluster map và định tuyến tới active vBucket. Nhiệm vụ của ứng dụng là duy trì semantics nghiệp vụ: document ID ổn định, retry idempotent, CAS chống xung đột, durability theo RPO và scan consistency đúng nhu cầu. Kết hợp thiết kế phần mềm với monitoring, capacity và diễn tập failover mới giúp hệ thống vừa nhanh vừa có khả năng phục hồi thực tế.
