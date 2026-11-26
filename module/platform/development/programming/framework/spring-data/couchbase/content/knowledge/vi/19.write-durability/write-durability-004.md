# Đánh đổi giữa độ an toàn dữ liệu, độ trễ và khả năng sẵn sàng trong Couchbase

> **Chương:** Độ bền ghi  
> **Học phần:** `SPRING_DATA_COUCHBASE` — xây dựng tầng truy cập Couchbase với document mapping, repository, `CouchbaseTemplate` và SQL++; thiết kế bucket/scope/collection, chỉ mục, TTL, CAS, transaction và API reactive để bảo đảm hiệu năng, tính nhất quán và khả năng vận hành.

## 1. Mục tiêu học tập

Sau bài học này, bạn có thể:

1. Phân biệt **độ an toàn của mutation đã được xác nhận** (*write durability*), **độ trễ** (*latency*) và **khả năng sẵn sàng của thao tác ghi** (*write availability*).
2. Giải thích vì sao chờ nhiều replica hoặc đợi persistence có thể tăng bảo vệ dữ liệu nhưng cũng làm ghi chậm hơn, thậm chí không thể hoàn tất khi cluster suy giảm.
3. Chọn `NONE`, `MAJORITY`, `MAJORITY_AND_PERSIST_TO_ACTIVE` hoặc `PERSIST_TO_MAJORITY` dựa trên lỗi cần chịu đựng, không chọn theo khẩu hiệu “càng mạnh càng tốt”.
4. Phân tích tác động của **số replica**, majority, failover, rebalance, disk/network saturation và tùy chọn fallback tới kết quả ghi.
5. Phân biệt **lỗi chắc chắn**, **lỗi durability không thể đạt** và **ambiguous outcome** để xử lý retry/idempotency an toàn.
6. Thiết kế SLI/SLO cho p95/p99 write latency, success rate, RPO/RTO, và kịch bản diễn tập sự cố có kiểm soát.
7. Áp dụng chính sách ghi trong Java SDK, Spring Data entity, `CouchbaseTemplate` và reactive API.
8. Trình bày một quyết định kiến trúc kèm **rủi ro, số đo và phương án rollback** thay vì chỉ cấu hình một enum.

## 2. Một mục tiêu có ba chiều: an toàn, nhanh và sẵn sàng

Giả sử `POST /orders` phải lưu đơn mới vào `commerce.sales.orders`. Product yêu cầu:

- **An toàn:** sau khi API báo “đã nhận đơn”, không muốn mutation biến mất nếu một Data node gặp sự cố theo kịch bản đã định.
- **Nhanh:** p99 của HTTP API nằm dưới ngân sách latency.
- **Sẵn sàng:** ứng dụng tiếp tục nhận đơn khi có một node không hoạt động.

Ba mong muốn này có thể **xung đột**. Nếu ghi chỉ cần active node phản hồi, có thể giảm thời gian chờ nhưng chưa đạt quorum/persistence. Nếu ghi bắt buộc có majority, một replica bị mất có thể khiến thao tác cần quorum **không thể xác nhận thành công**, dù active vẫn nhận được kết nối. Nếu yêu cầu persistence trên majority, disk chậm có thể làm p99 tăng.

~~~mermaid
flowchart TD
    Goal["Yêu cầu: ghi đơn hàng"]
    Safety["Độ an toàn dữ liệu<br/>RPO / failure scenarios"]
    Latency["Độ trễ<br/>p95 / p99 write latency"]
    Availability["Sẵn sàng ghi<br/>success / error rate khi có lỗi"]
    Config["Lựa chọn durability + replica + timeout + workload"]
    Goal --> Safety
    Goal --> Latency
    Goal --> Availability
    Config --> Safety
    Config --> Latency
    Config --> Availability
~~~

Không có một cấu hình ứng dụng bảo đảm đồng thời **không mất dữ liệu trước mọi lỗi**, **độ trễ thấp trong mọi tải** và **mọi mutation đều thành công khi cluster bất kỳ đang lỗi**. Cần nói rõ **loại lỗi nào**, **thời hạn nào** và **trạng thái được chấp nhận nào**.

### 2.1. Phải phân biệt tính sẵn sàng của đọc và ghi

Một cluster có thể vẫn trả `get(id)` hoặc trả kết quả `SQL++`, nhưng không hoàn tất được mutation `MAJORITY` vì thiếu replica cần thiết. Do vậy:

- **Read availability:** API đọc có còn phục vụ được không?
- **Write availability:** API ghi với **mức durability đã yêu cầu** có còn thành công không?
- **Business availability:** toàn bộ quy trình (ví dụ checkout) có còn đáp ứng hợp đồng người dùng không?

Chỉ thấy health check báo UP không đủ để kết luận checkout vẫn có thể ghi an toàn.

## 3. Ba mốc của đường ghi: active, replica, persistence

Couchbase phân phối document vào các **vBucket**, mỗi vBucket có một **active** và, tùy cấu hình, các **replica**. Active vBucket nằm trên một Data node; nhiều vBucket có active trên những Data node khác nhau. Không có một “master node” toàn cluster nhận mọi ghi.

~~~text
Document ID: tenant::42::order::1001
Bucket: commerce
Scope: sales
Collection: orders

vBucket V (minh họa):
  Data node A: active
  Data node B: replica
  Data node C: replica (nếu cấu hình có 2 replica)
~~~

~~~mermaid
flowchart LR
    App["Spring Data / Couchbase SDK"]
    Active["Data node A<br/>Active vBucket"]
    ReplicaB["Data node B<br/>Replica"]
    ReplicaC["Data node C<br/>Replica nếu có"]
    DiskA[("Disk A")]
    DiskB[("Disk B")]
    DiskC[("Disk C")]
    App -->|"KV mutation"| Active
    Active -->|"Replication"| ReplicaB
    Active -->|"Replication"| ReplicaC
    Active -->|"Persistence"| DiskA
    ReplicaB -->|"Persistence"| DiskB
    ReplicaC -->|"Persistence"| DiskC
    Active -.->|"Ack theo effective durability"| App
~~~

Có ba điều khác nhau:

1. **Active xử lý/ack mutation:** chưa đủ để khẳng định đã tới replica hoặc persist nếu không yêu cầu mức tương ứng.
2. **Replica xác nhận mutation:** tăng khả năng bảo toàn dữ liệu khi active gặp lỗi, nhưng một replica đã nhận trong bộ nhớ chưa chắc đã persist.
3. **Persistence:** mutation được lưu bền tới storage theo semantics của Couchbase Server/bucket; đây không phải một bản backup độc lập.

Replication/persistence có thể diễn ra đồng thời. **Durability level quyết định điều kiện phải đạt trước khi trả thành công**, không quy định một lịch cố định cho mọi bước nội bộ.

### 3.1. Một ghi “thành công” có thể mang các ý nghĩa khác nhau

- Với ghi thông thường không yêu cầu synchronous durability bổ sung, server có thể trả thành công mà không chờ majority/persistence.
- Với ghi `MAJORITY`, phải đạt ngưỡng majority theo giao thức durable write.
- Với level yêu cầu persist, phải đạt thêm điều kiện persistence tương ứng.
- Với timeout, client có thể **không biết** server đã hoàn tất mutation hay chưa.

Không dùng thời gian chờ cố định như `sleep(300 ms)` để “tạo durability”. Phải dùng option server-enforced và xử lý kết quả đúng semantics.

## 4. Bốn mức durability và những điều được bảo vệ

Với Couchbase Java SDK 3.x, enum thường dùng:

~~~java
import com.couchbase.client.core.msg.kv.DurabilityLevel;
~~~

| Mức | Điều kiện ghi phải đạt | Tác động thường gặp | Không giải quyết |
|---|---|---|---|
| **`NONE`** | Không yêu cầu synchronous durability bổ sung từ mutation; tùy bucket minimum | Đường ghi ít điều kiện chờ hơn | Mất mutation gần lúc lỗi, thiếu quorum |
| **`MAJORITY`** | Majority bản dữ liệu liên quan xác nhận mutation trong bộ nhớ theo giao thức | Chờ replication/quorum | Không yêu cầu persist trên active |
| **`MAJORITY_AND_PERSIST_TO_ACTIVE`** | Majority xác nhận **và** active persist | Thêm phụ thuộc vào persistence của active | Không yêu cầu mọi replica đã persist |
| **`PERSIST_TO_MAJORITY`** | Persistence trên majority bản dữ liệu liên quan | Có thể có tail latency cao nhất khi storage chậm | Không thay thế backup hoặc transaction |

Level cao hơn đặt thêm điều kiện trước khi server ack thành công, nhưng dữ liệu vẫn có thể mất trong **những lỗi nằm ngoài phạm vi bảo đảm**, ví dụ thao tác xóa nhầm hợp lệ, sự cố nhiều failure domain hoặc phục hồi từ backup quá cũ.

### 4.1. `NONE` không có nghĩa “không có replica”

Server có thể vẫn sao chép và persist. `NONE` chỉ có nghĩa **client không yêu cầu các mốc synchronous durability đó** trước khi coi mutation hoàn tất, trừ minimum policy ở server.

### 4.2. `MAJORITY` bảo vệ điều gì?

Nếu active node hỏng sau khi một ghi majority đã commit và replica phù hợp còn dữ liệu, cluster có cơ sở để failover mà không mất mutation trong các điều kiện bảo đảm được mô tả. Tuy nhiên, `MAJORITY` **không yêu cầu đồng bộ xuống đĩa** trước khi trả success.

### 4.3. Level có persistence không phải bảo đảm tuyệt đối

`MAJORITY_AND_PERSIST_TO_ACTIVE` giúp active có bản persisted. `PERSIST_TO_MAJORITY` tăng yêu cầu persistence trên nhiều bản. Nhưng nếu mất toàn bộ site, bị xóa dữ liệu do thao tác hợp lệ hoặc cần khôi phục phiên bản cũ, phải có **backup/DR** chứ không thể chỉ dựa vào durability của một mutation.

### 4.4. Chi phí không tuyến tính

Không thể nói mọi môi trường luôn chậm đúng 2x hoặc 3x khi nâng level. Độ trễ còn phụ thuộc disk I/O, network giữa Data node, replica health, transaction contention, sizing và tải đồng thời. Cần đo p95/p99 trên workload đại diện.

## 5. Majority và số replica: điểm quyết định write availability

Couchbase Server hiện hành mô tả majority theo số replica được cấu hình cho bucket. Với các cấu hình hỗ trợ synchronous durability trong tài liệu hiện hành:

| Số replica | Số bản active + replica | Majority cần | Nhận xét |
|---|---:|---:|---|
| **0** | 1 | 1 | Chỉ một bản: quorum không cung cấp bảo vệ khỏi mất Data node đó |
| **1** | 2 | 2 | Một trong hai bản không khả dụng có thể khiến durable write không hoàn tất cho vBucket bị ảnh hưởng |
| **2** | 3 | 2 | Có thể vẫn đạt majority về số học nếu chỉ một trong ba bản không khả dụng |
| **3 trở lên** | Không được hỗ trợ cho synchronous durability theo tài liệu Server hiện hành | — | Không lập kế hoạch dựa trên giả định sẽ có majority 3/4 |

**Lưu ý quan trọng:** phép tính `floor(N/2)+1` giúp hiểu quorum khi N là số bản tham gia, nhưng **tài liệu Couchbase hiện hành giới hạn durable writes cho bucket tối đa hai replica**. Vì vậy không mở rộng bảng sang 3 replica như một cấu hình khả dụng. Cần kiểm tra version/edition/bucket thực tế khi triển khai.

### 5.1. Ví dụ cấu hình một replica

~~~text
A = active vBucket
B = replica vBucket
Required majority = 2

A và B khỏe:
  MAJORITY -> có thể hoàn tất.

B bị lỗi:
  A vẫn nhận KV connection,
  nhưng mutation yêu cầu MAJORITY có thể không đạt quorum.
~~~

Trong thời gian này, **ghi thông thường** có thể còn làm việc theo giới hạn cluster, nhưng **ghi durable ở mức yêu cầu** có thể báo lỗi. Đó là sự đánh đổi availability để không giả vờ đã bảo vệ dữ liệu đúng như hợp đồng.

### 5.2. Hai replica không phải “chống mọi kiểu mất hai node”

Với một active và hai replica, majority về số học là hai bản. Nhưng nếu active failover, một replica stale, network bị chia hoặc các bản cùng failure domain, kết quả phụ thuộc trạng thái cluster và tiến trình recovery. Không hứa “chịu mất hai node” chỉ vì có hai replica.

### 5.3. Quorum là theo vBucket, không phải số node toàn cluster

Cluster có tám Data node không có nghĩa một order được sao chép sang cả tám. Một vBucket cụ thể vẫn có active và số replica được cấu hình; chỉ những bản liên quan tham gia điều kiện durability của mutation đó.

## 6. Khi node lỗi: sẵn sàng đọc và sẵn sàng ghi tách nhau

Xét một vBucket có active A và replica B, mutation dùng `MAJORITY`.

~~~mermaid
sequenceDiagram
    participant App as order-service
    participant A as Active vBucket A
    participant B as Replica B
    App->>A: insert(orderId, MAJORITY)
    A->>B: Replicate / chờ ack
    Note over B: Replica bị mất kết nối
    B--xA: Không có ack đáp ứng
    A-->>App: Có thể timeout / durability impossible
    Note over App: Không tự hạ durability rồi trả thành công
~~~

Ứng dụng phải biết: **không xác nhận được mức an toàn không đồng nghĩa document chắc chắn chưa tồn tại**. Một số lỗi có thể cho biết thao tác chưa thể hoàn tất; một số có outcome ambiguous. Phân loại theo exception/result thực tế.

### 6.1. Active lỗi, replica còn sống

Nếu active A lỗi sau mutation đã commit với majority, bản sao còn dữ liệu có thể được promote theo cơ chế failover khi đủ điều kiện. Nhưng việc failover có được bật, mất bao lâu và cluster còn bảo đảm gì sau đó là vấn đề topology/operations.

### 6.2. Replica lỗi, active vẫn phục vụ

Một số thao tác KV không yêu cầu synchronous durability có thể vẫn thực hiện được; thao tác đòi majority có thể bị ảnh hưởng. Không dùng `get(id)` thành công để kết luận `insert(..., MAJORITY)` cũng chắc chắn thành công.

### 6.3. Disk chậm nhưng replica/network bình thường

Level `MAJORITY` có thể không phải chờ persistence, còn `MAJORITY_AND_PERSIST_TO_ACTIVE` và `PERSIST_TO_MAJORITY` phụ thuộc I/O bền. Khi disk saturation, write p99 có thể tăng mạnh riêng với những operation yêu cầu persist.

### 6.4. Mất mạng hoặc response

Server có thể commit rồi response mất. Đây là tình huống **ambiguous outcome** ở client, ngay cả khi mức durability yêu cầu đã được đáp ứng. Không retry bằng business ID mới.

## 7. Trường hợp ngoại lệ: durability-impossible fallback

Theo tài liệu Couchbase Server hiện hành, bucket có tùy chọn vận hành `durabilityImpossibleFallback` trong một số môi trường để **cho phép báo thành công đối với một số durable write khi majority không khả dụng**.

Điều này giải quyết một rào cản về **write availability**, nhưng phá vỡ phần cốt lõi của bảo đảm mà ứng dụng tưởng đang nhận được: write báo success **không còn có nghĩa đã đạt quorum được yêu cầu** trong tình trạng fallback. Couchbase cảnh báo mức an toàn của những ghi này có thể tương đương ghi thông thường không yêu cầu synchronous durability.

### 7.1. Ma trận đánh đổi minh họa

Giả sử một bucket có 1 replica, một Data node đã failover:

| Chế độ | Mutation đòi `MAJORITY` | Tác động |
|---|---|---|
| Fallback **tắt** | Có thể không hoàn tất do thiếu quorum | Giữ contract: không báo success khi không đạt bảo đảm |
| Fallback **bật** và trường hợp được hỗ trợ | Server có thể báo success dù majority không đủ | Duy trì một phần khả năng ghi, nhưng **tăng nguy cơ mất dữ liệu** |
| Node chứa active cũng không phục vụ | Không thể giả định fallback cứu được mọi ghi | Vẫn phụ thuộc vBucket owner và trạng thái cluster |

**Đây không phải giải pháp mặc định nên bật** để chữa timeout. Trong hệ thống quan trọng, bật fallback có thể khiến API trả success ở mức thực tế thấp hơn yêu cầu nghiệp vụ. Ngoài ra, transaction dựa trên durable writes cũng chịu ảnh hưởng tới bảo đảm dữ liệu.

### 7.2. Chính sách khi buộc phải cân nhắc fallback

1. Ghi rõ **ai có quyền phê duyệt** việc suy giảm bảo đảm.
2. Xác định **loại dữ liệu nào** có thể chịu rủi ro mất mutation.
3. Theo dõi thời gian áp dụng, affected vBuckets, mutation count và business impact.
4. Đặt cảnh báo rõ ràng để nhóm ứng dụng biết contract đang thay đổi.
5. Có kế hoạch **tắt lại fallback và phục hồi redundancy** ngay khi phù hợp.
6. Hậu kiểm/đối soát những nghiệp vụ đã ghi trong thời gian suy giảm.

Tùy chọn này chỉ nên được thao tác bởi người sở hữu cluster theo runbook; bài học **không khuyến nghị developer tự bật trong production**. Khả năng và chi tiết cấu hình phụ thuộc phiên bản/triển khai thực tế.

## 8. CAP và PACELC: cách tư duy, không phải công thức thay API

Trong hệ phân tán, đôi khi người ta nói “muốn consistency thì hy sinh availability”. Có thể dùng tinh thần này để hiểu vì sao **không báo success khi không có quorum** là một lựa chọn bảo vệ hợp đồng an toàn.

Nhưng không nên áp dụng slogan CAP trực tiếp để giải thích mọi chi tiết của Couchbase:

- **CAP** nói về consistency/availability dưới network partition theo một mô hình cụ thể, không trực tiếp quy định mỗi level `DurabilityLevel` hoặc RPO.
- **PACELC** nhắc rằng **ngay cả khi không xảy ra partition**, giảm latency thường đòi đánh đổi một số yêu cầu consistency/coordination.
- **Durability**, **transaction isolation**, **business invariants** và **GSI freshness** không phải cùng một khái niệm.

Trong bài này, câu hỏi thiết thực là: **mutation cần bao nhiêu bản xác nhận trước success, và nếu không đủ bản thì trả kết quả gì?** Dùng điều kiện cụ thể của Couchbase thay vì chỉ gọi cluster là “AP” hoặc “CP”.

## 9. RPO, RTO, SLO: biến khẩu hiệu thành yêu cầu đo được

### 9.1. Recovery Point Objective — RPO

**RPO** là lượng dữ liệu (thường diễn đạt bằng thời gian hoặc phạm vi giao dịch) mà tổ chức chấp nhận có thể mất sau một sự cố/khôi phục.

Ví dụ:

- Cache có thể xây lại: cho phép mất một phần mutation mới nhất.
- Order được báo đã nhận: yêu cầu không mất những order đã xác nhận durable trong **kịch bản một Data node lỗi** theo phạm vi bảo đảm đã định.
- Phục hồi sau mất toàn region: cần chính sách DR và replication/backup riêng, không thể suy ra chỉ từ `PERSIST_TO_MAJORITY` trong một cluster.

### 9.2. Recovery Time Objective — RTO

**RTO** là mục tiêu thời gian khôi phục dịch vụ sau sự cố. Thao tác ghi có mức durability rất cao nhưng phải dừng lâu khi replica không đủ có thể chưa phù hợp RTO của checkout. Cần cả kế hoạch phục hồi redundancy và phương án vận hành khi ghi bị chặn.

### 9.3. SLI/SLO cho ứng dụng

| Chỉ số | Ví dụ mục tiêu nội bộ (minh họa) | Điều cần đo |
|---|---|---|
| **Write p95/p99** | p99 KV write < 250 ms khi khỏe | Từ ứng dụng và SDK |
| **API p99** | POST /orders p99 < 800 ms | Toàn bộ validation/DB/response |
| **Write success rate** | ≥ 99.9% trên kỳ đo được định nghĩa | Lỗi theo loại và trạng thái cluster |
| **Ambiguous rate** | Duy trì gần 0; mọi case được đối soát | Request có outcome chưa rõ |
| **Durability compliance** | 100% critical writes dùng level đã phê duyệt | Code path, policy và telemetry |
| **RPO/RTO** | Theo kịch bản node/zone/DR đã định nghĩa | Failure drill và restore test |

Những con số trên **chỉ minh họa**, không phải mức Couchbase công bố. Mỗi SLO phải xác định mẫu đo, thời điểm healthy/degraded, phân vị và cửa sổ tính toán.

### 9.4. Không lấy trung bình để hứa p99

Một endpoint có nhiều mutation nối tiếp cần xét **tail latency** của từng bước và mối liên hệ giữa các bước. Không lấy p99 của từng operation rồi cộng như công thức chắc chắn cho p99 HTTP; phải đo request end-to-end theo workload đại diện.

## 10. Ngân sách độ trễ cho đường ghi

Ví dụ checkout có budget 800 ms ở p99 (chỉ để minh họa):

~~~text
Client -> API gateway -> Order service
  Auth + validate                  ~40 ms (minh họa)
  Query/lookup business state      ~80 ms
  KV mutation với durability       cần đo thực tế
  Event/response                   ~30 ms
  Network + GC + tail headroom     phần còn lại
~~~

Nếu API yêu cầu `PERSIST_TO_MAJORITY` và disk/network ở giờ cao điểm khiến mutation p99 tăng, endpoint có thể vượt SLO mặc dù dữ liệu vẫn được bảo vệ tốt. Không đơn giản hạ level ngay, vì như vậy bạn đang **chuyển chi phí từ latency sang nguy cơ mất dữ liệu**.

### 10.1. Năm hướng giảm latency không thay đổi durability contract

1. **Giảm round trip tuần tự** không cần thiết: gom dữ liệu vào document khi phù hợp, tránh N+1 query.
2. **Đặt app gần cluster** hoặc trong region/network hợp lý, giảm RTT.
3. **Tối ưu kích thước document và write amplification**; hạn chế update khối JSON quá lớn khi có API phù hợp.
4. **Sửa bottleneck thật:** replica/network/disk saturation, capacity, failure domain.
5. **Giới hạn concurrency/retry storm**, dùng connection reuse, timeout phù hợp.

Reactive có thể giúp phục vụ nhiều I/O đồng thời, nhưng không rút ngắn thời gian server cần chờ replica/disk cho **một durable write**.

## 11. Khả năng sẵn sàng phải đo theo thao tác và level

Giả sử cluster vừa mất một node:

~~~text
GET /orders/{id}           -> có thể thành công
SELECT ... WHERE status    -> có thể chạy, tùy Query/Index
INSERT order with NONE     -> có thể thành công
INSERT order with MAJORITY -> có thể lỗi vì thiếu quorum
~~~

Đây không phải mâu thuẫn. Các operation có **phụ thuộc service và điều kiện xác nhận khác nhau**.

### 11.1. Bảng phân tích theo failure scenario

| Sự cố | Rủi ro dữ liệu | Ảnh hưởng latency | Ảnh hưởng write availability |
|---|---|---|---|
| **Replica B mất liên lạc**, bucket 1 replica | Ghi không quorum có rủi ro cao hơn | Retry/wait tăng | Durable writes cho vBucket liên quan có thể không hoàn tất |
| **Active lỗi** | Mutation pending/ambiguous cần xác minh | Failover/routing tăng latency | Có thể gián đoạn trước khi owner mới phục vụ |
| **Disk saturation trên active** | Không tự suy ra mất dữ liệu | Persistence-level p99 tăng | Timeout khi quá budget |
| **Disk saturation ở replica** | Ảnh hưởng mức persist-to-majority | Độ trễ tail tăng | Có thể không đáp ứng level |
| **Network jitter** | Response có thể bị mất sau commit | p99/timeout tăng | Client có thể báo ambiguous |
| **Rebalance** | Có thể có ambiguous mutation hiếm gặp | Load/RTT thay đổi tạm thời | Cần kiểm tra durability và retry |
| **Xóa nhầm hợp lệ** | Replica cũng lan truyền xóa | Không liên quan trực tiếp | Write có thể thành công, nhưng dữ liệu sai |
| **Mất toàn region** | Cần DR/backup ngoài cluster | RTO lớn nếu không có kế hoạch | Cluster cục bộ không phục vụ được |

Bảng mô tả xu hướng. Kết quả thực tế phụ thuộc version, bucket type, replica placement, failover mode và network.

## 12. Chọn level theo giá trị nghiệp vụ, không theo tên entity

| Loại dữ liệu | Khả năng tái tạo | RPO gợi ý để bàn luận | Chọn mức như thế nào? |
|---|---|---|---|
| Cache kết quả tìm kiếm | Dựng lại được | Chấp nhận một phần mất gần nhất | `NONE` có thể hợp lý khi không có policy mạnh hơn |
| Session đăng nhập | Có thể bắt đăng nhập lại | Thường chấp nhận một số mất mát nhưng phải cân nhắc UX | So sánh chi phí với `MAJORITY` |
| Giỏ hàng | Có thể khôi phục một phần | Tùy UX/kinh doanh | Kiểm tra yêu cầu số lượng replica |
| Đơn nháp | Có thể cho nhập lại | Rủi ro trung bình | `MAJORITY` có thể là baseline cần đánh giá |
| Đơn đã được xác nhận | Khó tái tạo chính xác | Yêu cầu rõ với failure scenarios | So sánh `MAJORITY` và persistence levels |
| Trạng thái thanh toán | Rất nhạy cảm với sai lệch | RPO nghiêm ngặt và reconciliation | Durability + idempotency + workflow consistency |
| Audit event | Tùy pháp lý/retention | Có thể nghiêm ngặt | Durability cùng backup/retention, không một mình |

Đây **không phải bảng cấu hình bắt buộc**. Một session chứa công việc chưa lưu có thể quan trọng hơn cache, và một đơn hàng có thể được tái tạo an toàn nếu hệ thống upstream giữ log chuẩn. Phải hiểu dữ liệu có thể **tái tạo chính xác** không, không chỉ “có bản ghi khác để xem lại”.

### 12.1. Ghi ít quan trọng không đồng nghĩa vô trách nhiệm

Nếu dùng level nhẹ cho cache, vẫn cần TTL, backfill, source-of-truth rõ ràng và cơ chế xây lại khi node lỗi. Không nên để người dùng nhận một sự kiện không thể tái tạo rồi bí mật xử lý như cache.

### 12.2. Ghi quan trọng cần hơn một level

Một payment record có thể dùng level persist mạnh, nhưng để tránh double charge còn cần:

- ID/idempotency key ổn định.
- Business state machine và CAS hoặc transaction phù hợp.
- Hệ thống reconciliation với gateway.
- Backup/restore và DR.
- Giám sát mutation ambiguous.
- Quy trình xử lý trường hợp không thể ghi durable trong incident.

## 13. Bảng quyết định từ yêu cầu sang cấu hình

Trước khi chọn level, trả lời các câu hỏi:

1. **Mutation đã được báo thành công được phép mất trong lỗi nào?** Active restart, mất một node, mất nhiều node, mất zone hay mất region?
2. **Có bao nhiêu replica và chúng nằm ở failure domain nào?**
3. **Có cần persistence lên storage hay chỉ majority acknowledgement?**
4. **Khi không đạt quorum, hệ thống phải báo lỗi, xếp hàng chờ hay cho phép ghi với bảo đảm thấp hơn theo policy?**
5. **Write p99 và HTTP deadline là bao nhiêu?**
6. **Có thể đối soát hoặc tái tạo từ nguồn khác không?**
7. **Ai có quyền quyết định thay đổi RPO khi có incident?**
8. **Backup/DR có đáp ứng sự cố ngoài phạm vi cluster không?**

### 13.1. Ví dụ một quyết định có thể review

~~~text
Use case: xác nhận đơn PAID
Rủi ro: mutation đã báo success không được mất khi một Data node lỗi
Target: p99 API < 800 ms ở tải đã định nghĩa
Data topology: bucket có 2 replicas, failure domains phù hợp
Selected candidate: PERSIST_TO_MAJORITY
Fallback: không bật trong vận hành bình thường
On quorum failure: trả trạng thái kiểm tra được, xếp reconciliation
Retry: idempotency key + stable document ID
Review: app owner + DBA/SRE + product
Validation: load test và failure drill ở staging
~~~

Tất cả số và lựa chọn trên là **ví dụ ra quyết định**, không phải khuyến nghị mặc định cho mọi hệ thống. Cần benchmark thực tế trước rollout.

## 14. Hai cách tạo availability mà không “giả vờ” write đã bền

Khi một durable write không thể hoàn tất, ứng dụng không nhất thiết phải dùng fallback hoặc hạ level để duy trì giao diện người dùng.

### 14.1. Trả trạng thái tạm chờ nếu nghiệp vụ cho phép

Ví dụ checkout có thể trả một kết quả **không xác nhận thanh toán hoàn tất**, kèm operation ID để tra cứu khi hạ tầng phục hồi — nhưng chỉ khi có **nguồn lưu trạng thái yêu cầu đáng tin cậy** ngoài đường ghi đang lỗi.

Không trả HTTP 201 “đơn đã được lưu bền” khi chưa có bảo đảm. Nếu ứng dụng không thể lưu cả operation ID một cách tin cậy, phải nói rõ không thể tiếp nhận yêu cầu và hướng dẫn retry với cùng idempotency key.

### 14.2. Thiết kế queue/workflow trước sự cố

Nếu upstream có queue bền độc lập và được vận hành đúng, ứng dụng có thể nhận lệnh vào queue rồi xử lý Couchbase khi phục hồi. Tuy nhiên:

- Ack của queue có **contract riêng**, không được gọi là Couchbase write success.
- Có thể có duplicate delivery; consumer phải idempotent.
- Queue cũng cần availability, retention, security và DR.
- Status UI phải phân biệt **đã nhận yêu cầu** và **đã hoàn tất ghi order**.

Đây là thay đổi kiến trúc có chi phí, không phải cấu hình một dòng. Nếu yêu cầu đơn giản hơn, thất bại rõ ràng + retry idempotent có thể phù hợp hơn.

## 15. Java SDK: chọn mức cho từng mutation

Couchbase Java SDK 3.x cho phép đặt `DurabilityLevel` trực tiếp vào options. Ví dụ dùng collection `commerce.sales.orders`:

~~~java
import static com.couchbase.client.java.kv.InsertOptions.insertOptions;
import com.couchbase.client.core.msg.kv.DurabilityLevel;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;

String orderId = "tenant::42::checkout::checkout-abc";

JsonObject order = JsonObject.create()
        .put("tenantId", "42")
        .put("status", "NEW")
        .put("total", 1490000);

// orders: Collection đã cấu hình kết nối đến commerce.sales.orders
var result = orders.insert(
        orderId,
        order,
        insertOptions().durability(DurabilityLevel.MAJORITY)
);
~~~

Lưu ý:

- `insert` là **create-only**; ID đã tồn tại sẽ gây lỗi thay vì âm thầm thay.
- `MAJORITY` là yêu cầu xác nhận replication; không bảo đảm active đã persist.
- Nếu cluster không đáp ứng durability level, request có thể lỗi, không nên tự động báo HTTP 201.
- `orderId` ổn định theo checkout để các lần thử lại không tạo ID ngẫu nhiên khác.

### 15.1. CAS và persistence cùng một operation

~~~java
import static com.couchbase.client.java.kv.ReplaceOptions.replaceOptions;
import com.couchbase.client.core.msg.kv.DurabilityLevel;

var before = orders.get(orderId);

if (!"NEW".equals(before.contentAsObject().getString("status"))) {
    throw new IllegalStateException("Đơn không còn ở trạng thái NEW");
}

var next = before.contentAsObject().put("status", "PAID");

var result = orders.replace(
        orderId,
        next,
        replaceOptions()
                .cas(before.cas())
                .durability(DurabilityLevel.MAJORITY_AND_PERSIST_TO_ACTIVE)
);
~~~

Ví dụ có hai điều kiện độc lập:

1. **CAS:** document chưa bị writer khác cập nhật kể từ lần đọc.
2. **Durability:** mutation được chấp nhận đạt majority và active persistence.

Ngay cả khi cả hai đạt, ứng dụng vẫn phải xác minh kết quả thanh toán ngoài Couchbase và có idempotency ở gateway; một KV replace không tạo transaction xuyên nhiều hệ thống.

### 15.2. Chọn `PERSIST_TO_MAJORITY`

~~~java
import static com.couchbase.client.java.kv.UpsertOptions.upsertOptions;

orders.upsert(
        "tenant::42::checkpoint::1001",
        JsonObject.create().put("state", "COMMITTED"),
        upsertOptions().durability(DurabilityLevel.PERSIST_TO_MAJORITY)
);
~~~

`upsert` có thể ghi đè body của ID đã có, nên không phù hợp cho một create-once nếu không có thêm logic kiểm soát. Mức persist mạnh không thay thế lựa chọn đúng operation.

### 15.3. TTL không hủy bỏ trade-off durability

~~~java
import java.time.Duration;
import static com.couchbase.client.java.kv.UpsertOptions.upsertOptions;

sessions.upsert(
        "session::abc123",
        sessionBody,
        upsertOptions()
                .expiry(Duration.ofMinutes(30))
                .durability(DurabilityLevel.MAJORITY)
);
~~~

Session vẫn hết hạn sau khoảng thời gian TTL dù mutation đã đạt majority. `expiry` quản lý vòng đời; `durability` quản lý điều kiện xác nhận. Không dùng TTL thay backup, hoặc durability để tránh document hết hạn.

### 15.4. Timeout là một phần của thiết kế

SDK và server có những timeout liên quan mutation/durability. Cần chọn deadline dựa trên workload thật; timeout quá thấp có thể gây nhiều ambiguous outcomes, nhưng timeout cực dài làm API không đáp ứng SLO. Không chỉnh timeouts chỉ để làm biểu đồ success rate đẹp hơn.

## 16. Spring Data Couchbase: đặt default trên entity

Spring Data giúp ánh xạ document và CRUD qua repository. Với phiên bản hỗ trợ:

~~~java
import com.couchbase.client.core.msg.kv.DurabilityLevel;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document(durabilityLevel = DurabilityLevel.MAJORITY)
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

    // Constructors và accessors được lược bỏ.
}
~~~

~~~java
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {
}
~~~

~~~java
OrderDocument saved = orderRepository.save(order);
~~~

**Mặc định entity** phù hợp nếu phần lớn mutation của entity cần cùng mức. Spring Data có metadata durability trên `@Document`; tuy nhiên `save` không tự bộc lộ effective level ở call site, và bucket minimum có thể mạnh hơn.

`@Version` dùng CAS, **không phải** durability. `@Scope`/`@Collection` chọn keyspace, không chọn replica count.

### 16.1. Override cho một thao tác bằng CouchbaseTemplate

~~~java
import com.couchbase.client.core.msg.kv.DurabilityLevel;
import org.springframework.data.couchbase.core.CouchbaseTemplate;

public class CriticalOrderWriter {

    private final CouchbaseTemplate template;

    public CriticalOrderWriter(CouchbaseTemplate template) {
        this.template = template;
    }

    public OrderDocument persistCriticalOrder(OrderDocument order) {
        return template
                .upsertById(OrderDocument.class)
                .withDurability(DurabilityLevel.PERSIST_TO_MAJORITY)
                .one(order);
    }
}
~~~

`withDurability(...)` nêu một mức riêng cho operation qua template thay vì default entity. Nhưng `upsertById` vẫn có thể thay document hiện có. Với tạo đơn duy nhất, cân nhắc `insertById`; với update cần CAS/business transition, chọn phương thức phù hợp.

### 16.2. Khi entity và operation khác yêu cầu

| Tầng | Giá trị minh họa | Lưu ý |
|---|---|---|
| Entity `@Document` | `MAJORITY` | Default cho đường Spring Data mapping |
| Template ở endpoint PAID | `PERSIST_TO_MAJORITY` | Override operation cụ thể |
| Bucket minimum | `MAJORITY` | Chính sách server vẫn có hiệu lực |
| SDK direct write | Có thể không truyền option | Không tự đọc annotation Spring Data |

Theo tài liệu hiện hành, nếu client và bucket đều yêu cầu level, server thực thi mức mạnh hơn. Khi có bất đồng chính sách, cần kiểm tra khả năng hỗ trợ và effective behavior của version/bucket type.

### 16.3. Không thay đổi policy trong incident một cách tự phát

Nếu một endpoint quan trọng dùng `PERSIST_TO_MAJORITY` và gặp timeout, đừng lập tức chuyển sang `MAJORITY` trong exception handler. Thay đổi level có nghĩa là **chấp nhận loại lỗi/mất dữ liệu khác**; cần review với product/SRE, không phải chỉ là tối ưu code.

## 17. Reactive: throughput cao không loại bỏ thời gian chờ quorum

Reactive Spring Data Couchbase và Couchbase Java SDK cho phép pipeline bất đồng bộ:

~~~java
import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;

public interface ReactiveOrderRepository
        extends ReactiveCouchbaseRepository<OrderDocument, String> {
}
~~~

Ví dụ Java SDK reactive mutation:

~~~java
import static com.couchbase.client.java.kv.InsertOptions.insertOptions;
import com.couchbase.client.java.kv.MutationResult;
import reactor.core.publisher.Mono;

Mono<MutationResult> write = orders.reactive().insert(
        orderId,
        order,
        insertOptions().durability(DurabilityLevel.MAJORITY)
);
~~~

Reactive giúp giảm việc chặn thread khi đang đợi I/O, nhưng một durable mutation vẫn phải đạt quorum/persistence theo level. **Tăng số subscription không làm replica nhanh hơn**; concurrency quá cao còn có thể tăng queue, latency p99 và timeout.

### 17.1. Cẩn thận với retryWhen

Khi publisher ghi được subscribe lại, mutation có thể chạy thêm lần. Nếu server đã commit nhưng response thất lạc, lần retry có thể gặp duplicate/CAS conflict hoặc gây side effect mới.

Quy tắc:

1. Tính `orderId`/idempotency key **trước** subscription.
2. Không tự sinh ID mới trong một callback có thể retry.
3. Phân loại duplicate, CAS conflict, timeout ambiguous và lỗi kết nối.
4. Hạn chế số lần retry, backoff, deadline và concurrency.
5. Khi kết quả không chắc chắn, **đọc/đối soát** thay vì lặp lại vô hạn.

Reactive là lựa chọn phong cách lập trình và quản trị I/O, không phải một durability level.

## 18. Khi kết quả ghi không chắc chắn: an toàn phải gồm idempotency

Giả sử client dùng `insert(orderId, MAJORITY)`:

~~~mermaid
sequenceDiagram
    participant API as order-service
    participant SDK as Java SDK
    participant A as Active Data node
    participant B as Replica
    API->>SDK: insert(orderId, MAJORITY)
    SDK->>A: Mutation
    A->>B: Replicate / chờ ack
    B-->>A: Đã đáp ứng majority
    Note over A,B: Mutation có thể đã hoàn tất
    A--xSDK: Response mất do sự cố
    SDK-->>API: Timeout / ambiguous result
~~~

Từ phía client, timeout có thể xảy ra **trước hoặc sau commit**. Kết quả không chắc chắn phải được xử lý như một trạng thái riêng, không gộp vào “thất bại chắc chắn”.

### 18.1. Bảng phân loại kết quả

| Kết quả | Có thể suy ra | Cách xử lý |
|---|---|---|
| Success rõ ràng | Operation đã hoàn tất theo level hiệu lực | Tiếp tục workflow |
| Duplicate ID ở `insert` | Document cùng ID đang tồn tại | Đọc và so payload/idempotency |
| CAS mismatch | Document đã được sửa | Đọc lại, kiểm tra business invariant |
| Durability impossible | Mức yêu cầu không thể đạt trong điều kiện hiện tại | Báo lỗi/cảnh báo, phối hợp vận hành |
| Durability ambiguous/timeout | Chưa chắc mutation đã commit hay chưa | Kiểm tra theo ID, reconciliation |
| Không thấy document khi đọc lại | Có thể chưa ghi, hoặc còn sự cố/trạng thái chưa rõ | Không kết luận chắc chắn thao tác cũ không bao giờ xảy ra |

Spring Data có thể dịch các SDK exception sang các loại `DataAccessException` tùy API và phiên bản; cần kiểm tra exception translation ở đúng abstraction.

### 18.2. Idempotency key cố định

~~~text
POST /checkout
Idempotency-Key: checkout-abc

orderId = tenant::42::checkout::checkout-abc
Mọi retry cùng checkout đều dùng orderId này.
~~~

Không làm như sau:

~~~text
Lần 1 insert order::random-A -> timeout
Lần 2 insert order::random-B -> success
Có thể tồn tại hai đơn cho một checkout
~~~

Để tránh duplicate cần:

- ID ổn định cho cùng business command.
- Dùng `insert` khi create-only; nếu ID đã có, xác minh đó là cùng request.
- Lưu hoặc so sánh fingerprint để key không tái sử dụng với payload khác.
- Retry có giới hạn; nếu không thể xác minh, đưa vào reconciliation.
- Với payment gateway, dùng **idempotency tại gateway** và trạng thái workflow riêng.

### 18.3. Flow kiểm tra trước khi retry

~~~mermaid
flowchart TD
    A["Nhận request với idempotency key"]
    B["Sinh ID ổn định"]
    C["INSERT với required durability"]
    D{"Kết quả?"}
    S["Success -> trả order"]
    U["Duplicate -> đọc và đối chiếu"]
    X["Ambiguous -> kiểm tra theo ID"]
    H{"Có bản ghi khớp?"}
    Y["Trả kết quả đã có"]
    N["Retry có điều kiện hoặc reconciliation"]
    A --> B --> C --> D
    D -->|"Success"| S
    D -->|"Duplicate"| U
    D -->|"Timeout/ambiguous"| X
    U --> H
    X --> H
    H -->|"Có"| Y
    H -->|"Chưa rõ"| N
~~~

Không phát email/charge hoặc sự kiện ngoài dựa trên giả định “ghi không thành công” khi outcome vẫn ambiguous.

## 19. Durability, transaction và business consistency không thay thế nhau

Nếu một order cần giữ tồn kho:

~~~text
1. insert order::1001
2. replace inventory::sku-A1
3. insert payment-record::1001
~~~

Ba lệnh riêng, dù đều `PERSIST_TO_MAJORITY`, **không tạo atomicity cho cả ba**. Nếu bước 3 lỗi, bước 1 và 2 có thể đã commit.

Nếu nhiều document Couchbase phải cùng thành công/rollback, cân nhắc **Couchbase Transactions** theo version/SDK và các điều kiện hỗ trợ.

- Transaction có durability, timeout, isolation và retry semantics **riêng**.
- Callback transaction có thể được chạy lại. Không gọi external payment/email/broker không idempotent bên trong callback.
- CAS giúp tránh lost update trên document, nhưng không thay multi-document transaction.
- Durability cao không làm một business rule sai trở nên đúng.

### 19.1. Tác động tới availability

Một transaction có nhiều mutation và cần durability đủ mạnh có thể chịu tác động hơn dưới failover/contension so với một KV mutation đơn. Do đó thiết kế **aggregate nhỏ gọn** và hạn chế transaction cần thiết có thể giúp latency/availability, nhưng không được tách invariant bắt buộc chỉ để tăng throughput.

### 19.2. Sự cố của hệ thống ngoài

Một Couchbase mutation durable không bảo đảm gateway đã charge đúng một lần; một transaction Couchbase cũng không bao trùm hệ thống ngoài. Cần saga/outbox và idempotency khi nghiệp vụ vượt nhiều service.

## 20. Độ mới GSI và read availability là vấn đề riêng

Một order được ghi `PERSIST_TO_MAJORITY` thành công nhưng câu SQL++:

~~~sql
SELECT META(o).id AS id, o.status
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = "42"
  AND o.status = "PAID";
~~~

có thể chưa thấy document ngay nếu GSI chưa bắt kịp mutation ở Data Service.

| Nhu cầu | Cơ chế |
|---|---|
| Đọc chính order có ID | KV `get(id)` hoặc repository `findById` |
| Danh sách chấp nhận trễ | SQL++ `not_bounded` |
| Cần index theo kịp mutation trước query | `request_plus` |
| Chỉ cần thấy mutation token đã biết | `consistentWith(MutationState)` |

Đừng tăng durability để chữa index lag, hoặc bật `request_plus` với mục tiêu tăng an toàn ghi. Chờ index có thể tăng **query latency**, trong khi durability ảnh hưởng **mutation latency và điều kiện ack**.

Trong incident, Query/Index Service và Data Service cũng có thể suy giảm theo cách khác nhau. SLI đọc và ghi nên được đo riêng.

## 21. Backup/DR và durability: hai lớp phục hồi khác nhau

Replica và synchronous durability bảo vệ những failure scenario ở tầng cluster. Chúng **không** phải backup độc lập và không đảm bảo khôi phục đúng trạng thái trước khi xóa nhầm.

| Cơ chế | Vai trò | Không tự bảo đảm |
|---|---|---|
| Data replica | Bản sao phân vùng để phục vụ HA | Khôi phục trước xóa nhầm |
| Synchronous durability | Điều kiện xác nhận mutation trước success | Không mất dữ liệu trước mọi lỗi |
| Backup/restore | Khôi phục dữ liệu từ restore point | Không có downtime hay zero RPO tự động |
| XDCR/DR (khi hỗ trợ) | Replication/khôi phục liên cluster/region | Transaction xuyên region hoặc backup lịch sử |
| Business reconciliation | Sửa lệch trạng thái nghiệp vụ sau outcome bất định | Thay thế server-enforced durability |

Ví dụ hóa đơn đã được ghi `PERSIST_TO_MAJORITY` nhưng có thao tác xóa hợp lệ sai phạm vi: mutation xóa có thể được replica ghi nhận theo cơ chế thông thường. Backup/restore hoặc audit log riêng mới có thể giúp phục hồi.

### 21.1. Server tự quản lý và Capella

- **Self-managed:** nhóm vận hành chịu trách nhiệm sâu hơn về node, replica, storage, topology, backup và DR.
- **Capella:** dịch vụ quản lý nhiều thành phần hạ tầng; nhóm ứng dụng vẫn phải chọn level, timeout, backup policy khi khả dụng, network, RBAC và chỉ tiêu RPO/RTO.

Không suy rằng Capella tự dùng durability mạnh nhất cho mọi SDK mutation, hoặc tự khôi phục mọi loại xóa nhầm.

## 22. Observability: phải nhìn được “đã trả success với điều kiện nào”

Các metric cần chia theo **nghiệp vụ**, **ứng dụng**, **SDK** và **cluster**.

### 22.1. Ở tầng ứng dụng

- HTTP API p50/p95/p99, success rate/error rate.
- Số KV mutation theo operation type và requested durability.
- Lỗi duplicate/CAS conflict/durability impossible/ambiguous.
- Retry count, deadline exceeded, số request chờ reconciliation.
- Business duplicate, double charge, đơn bị mất trạng thái hoặc sai chuyển trạng thái.
- Correlation ID và thời điểm incident, không ghi password/PII.

### 22.2. Ở tầng cluster

- Active/replica vBucket health, số replica sẵn sàng.
- Data Service CPU, memory, disk latency/IOPS, network.
- Failover/rebalance, index/query health và queue/backlog.
- Tỷ lệ timeout/latency của durable writes khi telemetry hỗ trợ.
- Backup success, thời gian restore và DR readiness.
- Tình trạng các cấu hình làm suy giảm bảo đảm như fallback, nếu có.

Tên metric và dashboard cụ thể tùy server version, Capella tier và SDK; không tự sáng tạo một metric chỉ vì tên nghe hợp lý.

### 22.3. Mẫu log có khả năng đối soát

~~~text
timestamp=2026-11-25T03:10:00Z
service=order-api
operation=KV_INSERT
keyspace=commerce.sales.orders
requestId=checkout-abc
documentIdHash=redacted
requestedDurability=MAJORITY
outcome=AMBIGUOUS
attempt=1
elapsedMs=...
sdkException=...
~~~

Log chỉ là mẫu. Không đưa password, payment token hay JSON body chứa PII vào log.

## 23. Benchmark ba chiều trên workload đại diện

Đừng so mức durability chỉ bằng một lệnh insert khi cluster rảnh. Cần benchmark chung:

| Biến giữ cố định | Ví dụ |
|---|---|
| Data model | Cùng keyspace và kích thước document |
| Tải | Cùng ops/s, concurrency, tỷ lệ insert/replace |
| SDK | Cùng version, connection reuse và retry policy |
| Cluster | Cùng topology, replica, storage và network |
| Key distribution | Cùng tỷ lệ hot key vs phân bố rộng |
| Metric | p95/p99, throughput, timeout, ambiguous, CPU/disk/network |
| Môi trường | Healthy và các degraded scenarios được phép |

### 23.1. Ma trận chạy test

| Test | Điều muốn thấy |
|---|---|
| `NONE`, cluster khỏe | Baseline throughput/latency và default ack |
| `MAJORITY`, cluster khỏe | Tăng thời gian chờ replication như thế nào? |
| `MAJORITY_AND_PERSIST_TO_ACTIVE` | Active storage ảnh hưởng p99 ra sao? |
| `PERSIST_TO_MAJORITY` | Disk/network trên nhiều bản tác động thế nào? |
| 1 replica, một thành viên mất | Durable writes xử lý thiếu quorum ra sao? |
| 2 replica, một thành viên mất | Điều kiện majority và availability thực tế thế nào? |
| Failover/rebalance được điều phối | Có ambiguous outcomes và retry tăng không? |
| Tăng tải đồng thời | Có saturation, tail latency hoặc queue buildup không? |
| Network jitter | Deadline/idempotency có tránh duplicate không? |

Không cần benchmark với fallback **bật** trong production để thử nghiệm; nếu cần đánh giá cơ chế này, sử dụng test cluster và runbook được chấp thuận.

### 23.2. Kiểm chứng nghiệp vụ thay vì chỉ metric máy chủ

Một test checkout cần xác nhận:

- Một idempotency key không sinh hai order.
- Operation trả success chỉ khi đáp ứng contract đã chọn.
- Khi timeout ambiguous, có trạng thái chờ đối soát thay vì trả kết luận sai.
- Khi cluster chưa phục hồi, không tự hạ level trái policy.
- Sau failover/restore, xác minh RPO/RTO đối với dữ liệu quan trọng.

## 24. Case study A — checkout không ghi được sau khi mất replica

### Bối cảnh

Bucket có một replica. Order API dùng `MAJORITY`. Replica B bị mất kết nối, active A vẫn nhận các KV requests.

**Lỗi phổ biến:** người vận hành thấy active khỏe và yêu cầu developer giảm level xuống `NONE` để “API hết lỗi”.

Phân tích:

1. Với một replica, majority cần cả active và replica trong cấu hình minh họa.
2. Giảm level làm thay đổi bảo đảm được trả cho khách hàng.
3. Nếu đơn đã nhận không thể tái tạo an toàn, việc báo success yếu hơn có thể nghiêm trọng hơn trả lỗi/“chưa tiếp nhận”.
4. Cần kiểm tra replication, failure domain, capacity và phương án phục hồi.
5. Nếu được phép, có thể dùng cơ chế nhận yêu cầu vào queue **độc lập và bền** với trạng thái “đang xử lý”, nhưng không gọi đó là order đã commit trong Couchbase.

**Bài học:** write availability phải được đo **cùng yêu cầu durability**, không chỉ khả năng TCP kết nối Data Service.

## 25. Case study B — p99 tăng sau khi bật PERSIST_TO_MAJORITY

### Bối cảnh

Trước thay đổi, API tạo order dùng `MAJORITY` và đáp ứng p99 latency. Sau khi đổi sang `PERSIST_TO_MAJORITY`, p99 tăng đáng kể.

Hướng điều tra:

1. Kiểm tra thay đổi được áp dụng ở entity, per-operation hay bucket minimum.
2. So sánh cùng workload, data size, topology và concurrency.
3. Theo dõi disk I/O trên active/replicas, replication lag và network.
4. Kiểm tra có query/transaction khác làm tăng tải không.
5. Đo deadline của SDK và HTTP, số ambiguous outcomes.
6. Nếu cần level này theo RPO, tối ưu năng lực lưu trữ/đường mạng hoặc kiến trúc, không tự hạ level ngay.
7. Chỉ đổi level sau khi có quyết định rõ về mục tiêu mất dữ liệu.

**Bài học:** đòi persistence trên majority có thể là đúng về an toàn nhưng cần đủ capacity để đạt SLO.

## 26. Case study C — server commit, client timeout và tạo đơn trùng

### Bối cảnh

Client tạo `order::random-A` với `MAJORITY`, nhưng response mất khi server đã hoàn tất. API thấy timeout rồi tạo `order::random-B` và retry.

Hai mutation đều có thể thành công, tạo **hai đơn cho một checkout**. Durability tốt không sửa được lỗi idempotency.

Thiết kế lại:

1. Dùng một `Idempotency-Key` của checkout xuyên mọi lần thử.
2. Sinh document ID ổn định từ tenant + checkout ID.
3. Dùng `insert` cho create-once; duplicate thì đọc và xác minh payload.
4. Nếu trạng thái chưa rõ, ghi nhận reconciliation.
5. Nếu có payment gateway, dùng idempotency ở gateway và workflow state riêng.
6. Đo số ambiguous outcomes và double-charge thay vì chỉ KV success.

**Bài học:** dữ liệu được bảo vệ tốt mà logic retry sai vẫn có thể tạo hậu quả nghiệp vụ nghiêm trọng.

## 27. Bài tập thực hành

### Bài A — chọn hướng đánh đổi

Một API session cho phép người dùng đăng nhập lại nếu mất session. Một API thanh toán không được phát sinh trạng thái “đã trả tiền” không thể đối soát. Hãy nêu khác biệt RPO, latency, mức durability ứng viên và cơ chế khôi phục.

### Bài B — majority

Với bucket có 0, 1 và 2 replica, hãy điền số bản cần cho majority theo tài liệu Couchbase hiện hành. Giải thích vì sao một bucket có 1 replica bị mất một Data node có thể ngừng durable writes trên vBucket liên quan.

### Bài C — availability

API `get(id)` vẫn thành công, nhưng `insert(... MAJORITY)` lỗi sau replica failure. Tại sao đây không phải mâu thuẫn? Gợi ý cách phân biệt read availability, write availability và business availability.

### Bài D — fallback

Giải thích rủi ro khi bật `durabilityImpossibleFallback`. Trong những điều kiện nào cần phê duyệt, audit và tắt lại? Tại sao không thể nói fallback “giữ an toàn như MAJORITY”?

### Bài E — code Java

Viết `insert` dùng `MAJORITY` và `replace` kết hợp CAS + `MAJORITY_AND_PERSIST_TO_ACTIVE`. Mỗi điều kiện giải quyết rủi ro nào?

### Bài F — Spring Data

Entity `@Document(durabilityLevel = MAJORITY)` và một operation `withDurability(PERSIST_TO_MAJORITY)` cùng tồn tại. Phân biệt default, override và bucket minimum. Lệnh SDK direct có tự nhận annotation không?

### Bài G — reactive retry

Một `Mono` được subscribe lại sau timeout ambiguous. Hãy thiết kế ID ổn định, retry budget và reconciliation để không tạo duplicate.

### Bài H — SQL++ và durability

`findById` thấy order nhưng SQL++ `WHERE status="PAID"` chưa thấy sau durable write. Đây là lỗi durability hay index freshness? Chọn API/scan consistency phù hợp.

### Bài I — SLO và RPO

Viết một quyết định kiến trúc gồm: failure scenario cần chịu, RPO/RTO, p99 write SLA, replica policy, level ứng viên, cách benchmark, owner và rollback.

### Bài J — failure drill

Thiết kế diễn tập mất một replica trong test cluster. Cần giám sát điều gì, làm thế nào biết một request đã trả success đúng contract, và xử lý ambiguous outcomes ra sao?

## 28. Checklist triển khai

- [ ] Định nghĩa loại lỗi cần chịu và RPO/RTO cho từng dữ liệu quan trọng.
- [ ] Phân biệt durability, latency và write availability trong SLO.
- [ ] Chọn level dựa trên replication/persistence thực tế, không chọn theo tên dữ liệu.
- [ ] Kiểm tra bucket type, server/SDK version và số replica được hỗ trợ.
- [ ] Không giả định bucket với 3+ replica có Sync Writes như một cấu hình hợp lệ theo docs hiện hành.
- [ ] Kiểm tra minimum durability tại bucket và option per-operation.
- [ ] Không bật fallback theo thói quen; nếu có, cần phê duyệt và theo dõi suy giảm bảo đảm.
- [ ] Tạo ID/idempotency key ổn định cho create-once; không retry bằng ID mới.
- [ ] Dùng CAS cho concurrency, transaction cho invariant nhiều document.
- [ ] Không dùng durability để thay TTL, SQL++ scan consistency hoặc backup.
- [ ] Đo write/API p95/p99, timeout, ambiguous, retry và throughput.
- [ ] Có observability replica/disk/network và failure-domain placement.
- [ ] Với reactive, giới hạn concurrency và retry/resubscribe side effects.
- [ ] Có kế hoạch failover, restore/DR và reconciliation.
- [ ] Diễn tập failure scenarios ở môi trường được phép, không thử hard failover tùy tiện trên production.
- [ ] Review mọi quyết định thay đổi level với owner RPO và nhóm vận hành.

## 29. Tổng kết

Trong Couchbase, **độ an toàn dữ liệu, độ trễ và khả năng sẵn sàng của thao tác ghi** là ba mục tiêu phải được thiết kế cùng nhau. `MAJORITY`, `MAJORITY_AND_PERSIST_TO_ACTIVE` và `PERSIST_TO_MAJORITY` yêu cầu các mức xác nhận replica/persistence khác nhau; điều kiện mạnh hơn có thể kéo dài write latency hoặc làm một mutation không thể xác nhận thành công khi cluster thiếu thành viên.

Một hệ thống tốt không phải hệ thống **luôn trả success**, mà là hệ thống chỉ trả success khi đáp ứng **hợp đồng dữ liệu đã cam kết**. Nếu thiếu quorum, phải quyết định rõ có trả lỗi, chờ, nhận yêu cầu vào một hệ thống bền độc lập hay chấp nhận fallback được phê duyệt; không âm thầm hạ mức rồi coi như không đổi RPO.

Trong **Spring Data Couchbase**, entity default, `CouchbaseTemplate.withDurability(...)`, SDK mutation options và bucket minimum cùng ảnh hưởng effective durability. Hãy phối hợp **CAS, idempotency, timeout classification, reactive backpressure, SQL++ scan consistency, backup/DR và quan sát vận hành**, sau đó kiểm thử bằng workload và failure scenario thực tế. Đó là cách đánh đổi có ý thức thay vì chỉ chọn enum mạnh nhất.

## Tài liệu tham khảo chính thức

- [Couchbase Server — Durability](https://docs.couchbase.com/server/current/learn/data/durability.html): các mức, giới hạn replica, điều kiện majority, xử lý ambiguous và durability-impossible fallback.
- [Couchbase Java SDK — Data Operations](https://docs.couchbase.com/java-sdk/current/howtos/kv-operations.html): mutation options, Sync Writes và lựa chọn durability.
- [Couchbase Java SDK — Data Modelling, Durability, and Consistency](https://docs.couchbase.com/java-sdk/current/concept-docs/data-durability-acid-transactions.html): đánh đổi write performance với mức xác nhận.
- [Spring Data Couchbase — Template & direct operations](https://docs.spring.io/spring-data/couchbase/reference/couchbase/template.html): `@Document` default và `CouchbaseTemplate.withDurability(...)`.

Các ví dụ và giới hạn phản ánh tài liệu tham khảo hiện hành; trước khi vận hành hãy đối chiếu **phiên bản Couchbase Server/Capella, bucket type, Java SDK và Spring Data** đang dùng.


