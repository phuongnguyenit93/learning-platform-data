# Điều kiện số bản sao và cấu hình cụm đáp ứng độ bền trong Couchbase

> **Chương:** Độ bền ghi  
> **Học phần:** `SPRING_DATA_COUCHBASE` — xây dựng tầng truy cập Couchbase bằng document mapping, repository, `CouchbaseTemplate` và SQL++; phối hợp bucket/scope/collection, chỉ mục, TTL, CAS, transaction và lựa chọn API reactive để bảo đảm hiệu năng, tính nhất quán và khả năng vận hành.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **số replica cấu hình trên bucket**, **bản replica vBucket thực sự được đặt trên Data node** và **majority cần đạt** đối với Sync Writes.
2. Nêu điều kiện để Couchbase đáp ứng `MAJORITY`, `MAJORITY_AND_PERSIST_TO_ACTIVE` và `PERSIST_TO_MAJORITY` trên từng loại bucket.
3. Giải thích vì sao **một cluster có nhiều node không đồng nghĩa một document có nhiều bản sao**, và tại sao Query/Index nodes không thay Data replicas.
4. Sử dụng đúng bảng giới hạn hiện hành: bucket có thể cấu hình 0–3 replica, nhưng **Sync Writes chỉ hỗ trợ 0–2 replica** trong Couchbase Server hiện hành.
5. Phân tích ảnh hưởng của failover, replica thiếu, rebalance, server groups, network/disk và điều kiện quorum tới độ sẵn sàng ghi.
6. Phân biệt **minimum replica count của cluster** với **minimum durability level của bucket**, tránh coi chúng là một thuộc tính.
7. Kiểm tra topology, policy và ứng dụng Spring Data/Java SDK trước khi rollout một yêu cầu durability mới.
8. Xây dựng kịch bản thử lỗi, xử lý kết quả ghi `ambiguous` bằng idempotency, và trao đổi được với DBA/SRE về RPO/RTO.

## 2. Bài toán: ghi đơn hàng cần sống sót sau lỗi node

Một ứng dụng `order-service` dùng Spring Data Couchbase, với keyspace:

~~~text
Bucket: commerce
Scope: sales
Collection: orders
Document ID: tenant::42::order::1001
~~~

Document minh họa:

~~~json
{
  "tenantId": "42",
  "status": "CONFIRMED",
  "total": 1490000,
  "currency": "VND",
  "schemaVersion": 1
}
~~~

Product đưa ra yêu cầu:

> Sau khi API đã báo nhận đơn thành công, dữ liệu phải có cơ sở tồn tại khi một Data node gặp sự cố trong phạm vi bảo đảm đã chọn; nếu không thể xác nhận mức đó, API không được giả vờ thành công.

Một developer thêm vào lệnh ghi:

~~~java
insertOptions().durability(DurabilityLevel.MAJORITY)
~~~

Nhưng code này **chưa tự giải quyết** các câu hỏi về hạ tầng:

- Bucket `commerce` có bao nhiêu replica được cấu hình?
- Có đủ **Data nodes** để đặt các bản lên các node khác nhau không?
- Có replica nào đang missing hoặc bị failover không?
- Bucket thuộc loại **Couchbase** hay **Ephemeral**; mức yêu cầu có cần persistence không?
- Nếu một Data node lỗi, số bản còn hoạt động có thể tạo majority không?
- Auto-failover có thể loại bỏ những node chứa các bản vừa commit không?
- Bucket có minimum durability hoặc một cấu hình suy giảm bảo đảm như durability fallback không?
- SDK có thể nhận `ambiguous` do timeout dù server đã commit không?

Đây là lý do bài học tập trung vào **điều kiện hạ tầng làm cho durability thực sự khả thi**, thay vì chỉ lặp lại tên enum.

## 3. Document được ghi vào active vBucket, không phải mọi Data node

Couchbase phân vùng bucket thành những **vBucket**. Mỗi vBucket có một bản **active** và, tùy cấu hình, những bản **replica**. Các bản được bố trí trên những Data node khác nhau để phục vụ khả năng chịu lỗi.

~~~mermaid
flowchart LR
    App["Spring Data / Java SDK"]
    Router["SDK cluster/vBucket map"]
    A["Data node A<br/>active V42"]
    B["Data node B<br/>replica V42"]
    C["Data node C<br/>replica V42"]
    Q["Query Service"]
    I["Index Service"]
    App --> Router
    Router -->|"KV mutation"| A
    A -->|"Replication"| B
    A -->|"Replication"| C
    App -.->|"SQL++"| Q
    Q -.-> I
~~~

Sơ đồ minh họa **hai replica** của vBucket V42. Các vBucket khác có active ở B hoặc C; **không có một “master node” của toàn cluster**.

Quy tắc cần nhớ:

- KV theo `document ID` sử dụng **Data Service**, định tuyến tới active owner của vBucket.
- Replica là bản sao của **vBucket**, không phải một copy đầy đủ độc lập trên mọi Data node.
- Query Service và Index Service có nhiệm vụ khác; thêm một **Query-only node** không tạo thêm Data replica.
- Index replica và Data replica là **hai cấu hình khác nhau**. Có GSI replica không làm `MAJORITY` dễ đạt hơn.
- SDK chính thức nhận cluster map và quản lý routing; ứng dụng không nên tự tính node đích từ tiền tố tenant.

### 3.1. Bốn câu hỏi để hiểu số bản thực

Đối với một vBucket liên quan đến đơn hàng, hãy hỏi:

1. Bucket mong muốn `replicaNumber` là bao nhiêu?
2. Cluster hiện có bao nhiêu Data node đủ điều kiện bố trí bản?
3. Active và từng replica **đã được đặt và khỏe** ở những node nào?
4. Các node có thuộc những failure domain khác nhau không?

Chỉ nhìn mục “Replicas: 2” trong cấu hình bucket mà bỏ qua các câu 2–4 là chưa đủ cho durability production.

## 4. Replica count của bucket: giá trị mong muốn và trạng thái thực tế

Couchbase Server hiện hành cho phép cấu hình `replicaNumber` trên bucket là **0, 1, 2 hoặc 3**. Giá trị này mô tả số bản replica mà hệ thống **muốn bố trí**, không phải bằng chứng tức thời rằng toàn bộ replica đã tồn tại và sẵn sàng.

Tài liệu Couchbase Server REST API nêu một chi tiết dễ bỏ qua: nếu số replica yêu cầu **vượt quá khả năng bố trí vì thiếu node**, thao tác cấu hình có thể vẫn được chấp nhận; hệ thống chỉ tạo số bản tối đa có thể và bổ sung bản còn thiếu khi có node mới.

| Cấu hình mong muốn | Số Data node tối thiểu để bố trí đủ active + replica trên node riêng | Phải xác minh |
|---|---:|---|
| `replicaNumber=0` | 1 | Không có Data replica cho vBucket |
| `replicaNumber=1` | 2 | Active và replica khác node, replica khỏe |
| `replicaNumber=2` | 3 | Active và hai replica khác node, đủ tài nguyên |
| `replicaNumber=3` | 4 | Có thể dùng replication thông thường, **Sync Writes không hỗ trợ** theo docs Server hiện hành |

**Điểm phân biệt quan trọng:** hệ thống có thể chấp nhận cấu hình `replicaNumber=2` khi cluster chưa có ba Data node, nhưng không nên hiểu như đã có ba bản dữ liệu an toàn và luôn sẵn sàng. Cần kiểm tra vBucket distribution, replica missing và trạng thái rebalance.

### 4.1. Ba node toàn cluster chưa chắc là ba Data node

Ví dụ:

~~~text
Node A: Data Service
Node B: Query Service
Node C: Index Service

Bucket commerce: replicaNumber = 2
~~~

Cluster có ba node nhưng chỉ **một Data node**. Đây không phải topology có đủ ba bản cho vBucket. Muốn đặt 1 active và 2 Data replicas, cần **ít nhất ba node chạy Data Service** đủ điều kiện.

### 4.2. Một Data node có thể giữ nhiều vai trò

Node chạy cả Data + Query/Index vẫn tính là **một Data node**, không phải hai hoặc ba bản sao khác failure domain. Điều quan trọng là số **host độc lập** có thể giữ active/replica, không phải số lượng service trên một host.

## 5. Bảng majority và giới hạn Sync Writes hiện hành

**Couchbase Server hiện hành hỗ trợ Sync Writes trên bucket với tối đa hai replica.** Tài liệu chính thức công bố:

| Replica đã cấu hình | Tổng bản active + replica dự kiến | Số Data node cần để đạt majority | Khả năng Sync Writes |
|---|---:|---:|---|
| **0** | 1 | **1** | Có, nhưng không bảo vệ khi Data node duy nhất mất hẳn |
| **1** | 2 | **2** | Có |
| **2** | 3 | **2** | Có |
| **3** | 4 | Không áp dụng | **Không hỗ trợ Sync Writes** |

Về trực giác, majority với `N` thành viên có thể hiểu:

~~~text
majority(N) = floor(N / 2) + 1
~~~

Nhưng **không áp dụng công thức này để suy ra `3 replicas → quorum 3/4` là một cấu hình durable write được hỗ trợ**. Couchbase Server hiện hành giới hạn Sync Writes ở 0, 1 hoặc 2 replica. Nếu cố Sync Write trên bucket có ba replica, server có thể trả lỗi `EDurabilityImpossible`.

### 5.1. Vì sao 0 replica vẫn có “majority = 1”?

Vì 1/1 là majority về toán học. Tuy nhiên, khi toàn bộ dữ liệu của vBucket chỉ ở **một Data node**, đạt majority không cung cấp bản sao để failover nếu node đó mất hẳn.

Do vậy:

> **“Đạt majority” chỉ có ý nghĩa bảo vệ lỗi khi kết hợp với topology/replica thực tế.**

Nếu nghiệp vụ đòi sống qua mất một Data node, không dùng một replica-less bucket chỉ vì `MAJORITY` trả success.

### 5.2. Một replica: điều kiện 2/2

Giả sử active trên A, replica trên B:

~~~text
vBucket V42: active A + replica B

Cần MAJORITY = 2 bản.
A khỏe, B khỏe → có thể đáp ứng.
B không khả dụng → chỉ A còn; 1/2 chưa đủ.
~~~

Ứng dụng có thể vẫn đọc/ghi một số KV thông thường, nhưng **durable write `MAJORITY` cho vBucket bị ảnh hưởng không thể mặc định tiếp tục thành công** trong khi thiếu quorum.

### 5.3. Hai replica: điều kiện 2/3

Giả sử A active, B và C là replica:

~~~text
vBucket V42: active A + replica B + replica C

Cần MAJORITY = 2 bản.
A và B sẵn sàng, C tạm lỗi → có thể đủ 2.
A và C sẵn sàng, B tạm lỗi → có thể đủ 2.
Chỉ A còn → không đủ 2.
~~~

Đây là **mô hình quorum logic**, không phải lời hứa mọi thao tác sẽ thành công sau mọi failover. Nếu active bị mất, replica cần được promote, cluster map và membership phải được cập nhật; trạng thái các durable write đang chờ có thể khác.

### 5.4. Hai replica có lợi gì so với một?

Với cùng majority=2, hai replica tạo cơ hội còn **hai trong ba** bản khi một replica không khả dụng. Điều này cải thiện khả năng đáp ứng quorum trong một số failure scenario. Nhưng đổi lại:

- Cần ít nhất **ba Data node** để bố trí đầy đủ.
- Tăng sử dụng disk/memory và lưu lượng replication.
- Cần thiết kế placement trên các failure domain khác nhau.
- Vẫn không đảm bảo chịu mất **hai bản chứa majority** ngay sau commit trước khi bản thứ ba bắt kịp.

## 6. Kiến thức nền: Sync Write chỉ nhìn thấy bản đã commit

Ở mức khái niệm, durable write có các giai đoạn chuẩn bị, xác nhận và commit. Khi một mutation vẫn đang pending và chưa đạt điều kiện cần thiết, những client khác không được xem nó như đã commit.

~~~mermaid
sequenceDiagram
    participant App as order-service
    participant A as Active vBucket A
    participant B as Replica B
    App->>A: replace(orderId, MAJORITY)
    A->>B: Prepare/replicate pending mutation
    Note over A,B: Chờ majority theo protocol
    B-->>A: Xác nhận
    Note over A,B: Điều kiện đạt và commit
    A-->>App: MutationResult thành công
~~~

Trong khi durable write chưa hoàn tất:

- Đọc document có thể thấy **giá trị cũ đã commit**.
- Mutation khác tới cùng key có thể gặp trạng thái `SYNC_WRITE_IN_PROGRESS`.
- Nếu quá timeout hoặc failure khiến không thể hoàn tất, server có cơ chế abort/rollback theo protocol.
- Nếu client mất kết nối đúng thời điểm bất định, kết quả có thể là **ambiguous**.

Như vậy không nên “tự thêm polling để chờ replica” trong Spring application. Hãy sử dụng **DurabilityLevel chính thức** và xử lý lỗi.

## 7. Chọn bucket type phù hợp level

Couchbase Server hiện hành phân biệt **Couchbase bucket** (có persistence) và **Ephemeral bucket** (lưu trên bộ nhớ, không có persistence thông thường như Couchbase bucket).

| Bucket type | `NONE` | `MAJORITY` | `MAJORITY_AND_PERSIST_TO_ACTIVE` | `PERSIST_TO_MAJORITY` |
|---|---|---|---|---|
| **Couchbase** | Theo default/policy | Hỗ trợ khi đủ điều kiện | Hỗ trợ khi đủ điều kiện | Hỗ trợ khi đủ điều kiện |
| **Ephemeral** | Theo default/policy | Hỗ trợ khi đủ điều kiện | **Không hỗ trợ vì yêu cầu disk persistence** | **Không hỗ trợ vì yêu cầu disk persistence** |

Điều này liên quan trực tiếp đến thiết kế môi trường:

- Session/cache có thể phù hợp Ephemeral trong một số use case nhưng phải chấp nhận semantics dữ liệu.
- Order/payment cần persistence theo RPO nghiêm ngặt thường đòi Couchbase bucket có storage phù hợp.
- Chỉ đổi `DurabilityLevel` ở client **không biến Ephemeral bucket thành Couchbase bucket**.
- Một bucket có thể có minimum durability; mức đó cũng phải hợp lệ cho bucket type.

Các tính năng, edition và storage engine thực tế cần kiểm tra theo phiên bản Couchbase Server/Capella đã chọn.

## 8. Phân biệt ba thuộc tính có tên dễ nhầm

Một trong những lỗi cấu hình nguy hiểm là đồng nhất **replica count**, **replica minimum** và **durability minimum**.

| Thuộc tính | Phạm vi | Ý nghĩa | Không nên hiểu là |
|---|---|---|---|
| `replicaNumber` | **Bucket** | Số Data replicas mong muốn của mỗi vBucket | Số replica đã thực sự được đặt/khỏe |
| `minReplicasCount` | **Cluster policy** cho việc tạo bucket mới | Số replica tối thiểu được phép cấu hình **cho bucket tạo sau khi đổi policy** | Bắt mọi bucket cũ tự tăng replica, hoặc yêu cầu Sync Write |
| `durabilityMinLevel` | **Bucket** | Level durability tối thiểu của các mutation thuộc bucket | Số replica hoặc số Data node tối thiểu |

### 8.1. `minReplicasCount` có thể gây bẫy với Sync Writes

Couchbase Server có policy tối thiểu số replica cho bucket mới, `minReplicasCount`, có thể nhận các giá trị trong phạm vi server hỗ trợ. Nếu tổ chức đặt minimum replica bằng **3** để tăng sao chép cho những bucket mới, thì bucket mới với ba replica **không thể dùng Sync Writes** theo giới hạn hiện hành.

Đây là hai quyết định khác nhau, phải phối hợp: **số bản sao nhiều hơn không phải lúc nào cũng tương thích với cơ chế durability đang chọn**.

### 8.2. Policy cluster không tự sửa bucket đã có

Theo REST docs, thay `minReplicasCount` ảnh hưởng **bucket được tạo sau đó**; bucket hiện có không tự bị sửa theo policy mới.

Ví dụ:

~~~text
Hôm qua:
  bucket commerce đã có replicaNumber=1

Hôm nay:
  cluster minReplicasCount=2

Kết quả:
  commerce không tự đổi thành replicaNumber=2.
  Các bucket được tạo mới phải thỏa minimum=2.
~~~

### 8.3. Policy bucket không tạo thêm bản sao

Nếu `durabilityMinLevel=persistToMajority` nhưng bucket thiếu replica hoặc disk không đáp ứng, policy không “tự tạo” điều kiện thành công. Mutation có thể lỗi hoặc timeout. Cần đủ topology, storage và network thực tế.

## 9. Minimum durability và effective level

Couchbase Server cho phép đặt minimum durability ở bucket; các mutation Java SDK cũng có thể chỉ rõ level. **Server thực thi level mạnh hơn** giữa yêu cầu client và mức tối thiểu của bucket khi áp dụng.

| SDK / Spring Data yêu cầu | Bucket minimum | Mức hiệu lực cần đánh giá |
|---|---|---|
| `NONE` | `MAJORITY` | Ít nhất `MAJORITY` |
| `MAJORITY` | `NONE` | `MAJORITY` |
| `MAJORITY` | `PERSIST_TO_MAJORITY` | `PERSIST_TO_MAJORITY` |
| `PERSIST_TO_MAJORITY` | `MAJORITY` | `PERSIST_TO_MAJORITY` |

Mức mạnh hơn không thay thế điều kiện replica. **Một bucket có 1 replica và chỉ active còn khỏe không thể đạt 2/2 về quorum** trong điều kiện bình thường, dù minimum level đã được đặt.

### 9.1. Vì sao minimum level ở bucket cần review cùng ứng dụng?

Một bucket có thể có nhiều collection và service dùng chung:

~~~text
commerce
├── sales.orders      (business critical)
├── sales.sessions    (có thể tái tạo)
└── catalog.cache     (tạm thời)
~~~

Nếu minimum durability mạnh áp dụng toàn bucket, mutation session/cache cũng có thể phải chờ mức mạnh đó. Có thể dẫn tới p99 latency và lỗi ghi nhiều hơn khi replica suy giảm. Ngược lại, nếu chỉ dùng per-operation config, một đường code quên truyền option có thể dùng mức yếu hơn.

Quyết định giữa **bucket minimum** và **per-operation** phụ thuộc rủi ro dữ liệu, số service, workload và quy trình review.

## 10. Khi nào cần ít nhất 2 hoặc 3 Data nodes?

### 10.1. Lab một Data node

~~~text
Node A: Data Service
Bucket: replicaNumber=0
Durability: MAJORITY có thể đạt 1/1 theo semantics hỗ trợ
~~~

Phù hợp để học API nhưng **không mô phỏng khả năng sống sót sau mất Data node**. Nếu node/hạ tầng duy nhất mất hoàn toàn, không có bản để promote.

### 10.2. Lab hai Data nodes

~~~text
Node A: Data Service
Node B: Data Service
Bucket: replicaNumber=1
Durability majority: 2/2
~~~

Có bản sao phục vụ failover, nhưng nếu A hoặc B không còn khả dụng với vBucket liên quan, durable writes yêu cầu majority có thể bị chặn. Và **automatic failover còn có các điều kiện cluster riêng**; không mặc định cluster hai node sẽ tự failover như ba node.

### 10.3. Lab ba Data nodes

~~~text
Node A: Data Service
Node B: Data Service
Node C: Data Service
Bucket: replicaNumber=2
Durability majority: 2/3
~~~

Cung cấp thêm một bản so với cấu hình một replica, có thể đạt quorum khi mất khả dụng một trong các bản trong một số tình huống. Tuy nhiên, trong production vẫn cần lưu ý:

- Data node đủ CPU, RAM, disk, network để chịu **N-1 load**.
- Active/replica được đặt ở những failure domain phù hợp.
- Auto-failover settings không loại bỏ cả majority chứa mutation mới commit.
- Rebalance hoàn tất sau thay topology để khôi phục distribution.
- Latency và error rate có thể tăng trong maintenance/failure.

### 10.4. Một node nhiều service không tăng số bản Data

Ví dụ A chạy Data+Query+Index, B chạy Data+Index, C chỉ Query: cluster có ba node nhưng **hai Data nodes**, nên không có ba host Data riêng cho 2 replicas của vBucket. Cần kiểm tra service assignment, không chỉ số ô hiển thị trên dashboard.

## 11. Server Groups và failure domains

Một active và replica đặt trên **các Data nodes khác nhau** giúp chống lỗi của một node. Nhưng nếu cả hai cùng rack hoặc cùng vùng nguồn điện, một lỗi tập trung có thể mất cả hai.

Couchbase Server hỗ trợ **Server Groups** để nâng cao awareness về failure domain. Theo tài liệu, active/replica của cùng vBucket có thể được đặt trên các nhóm riêng khi cấu hình phù hợp.

~~~mermaid
flowchart LR
    App["App / SDK"]
    G1["Group / Zone A<br/>Data node A<br/>Active V42"]
    G2["Group / Zone B<br/>Data node B<br/>Replica V42"]
    G3["Group / Zone C<br/>Data node C<br/>Replica V42"]
    App --> G1
    G1 -->|"Replication"| G2
    G1 -->|"Replication"| G3
~~~

Với 2 replicas, lý tưởng cần đủ các nhóm/failure domains phù hợp để đặt **mỗi bản ở vị trí độc lập**, trong phạm vi tính năng và topology được hỗ trợ.

### 11.1. Đặt replica theo zone chưa đủ để có DR liên vùng

Server Groups tăng khả năng chống lỗi khu vực/host trong một cluster, nhưng không tự tạo **backup lịch sử**, transaction liên vùng hoặc zero-RPO DR. Khi mất toàn khu vực chứa cluster hoặc xóa nhầm dữ liệu, cần backup/restore, replication liên cluster/XDCR theo khả năng và diễn tập.

### 11.2. Cấu hình groups không thay majority

Dù active/replica nằm trên ba zone, với 2 replicas majority vẫn là **2** theo cấu hình. Server Groups tác động đến **loại lỗi độc lập có thể chịu**; nó không tự sửa quorum formula.

### 11.3. Sizing có ảnh hưởng đến độ bền ghi

Nếu một nhóm chứa quá ít Data nodes, replica placement có thể tạo áp lực CPU/memory/disk và replication traffic không cân bằng. Một durable write `PERSIST_TO_MAJORITY` phải chờ storage ở số bản yêu cầu, nên bottleneck ở nhóm nhỏ có thể làm p99 tăng.

## 12. Kiểm tra Data replica, không nhầm Index replica

Số bản liên quan durability là **Data replicas của bucket**. Những khái niệm khác không thay đổi số bản dữ liệu đang tham gia Sync Writes:

| Cơ chế | Mục đích | Có tính vào majority Data durability không? |
|---|---|---|
| Data vBucket replica | Sao chép document theo vBucket | **Có**, theo semantics và trạng thái |
| GSI index replica | Bảo vệ availability của secondary index | **Không** |
| View index replica (nếu dùng) | Bản sao cho hệ thống view index | **Không** |
| XDCR sang cluster khác | Sao chép bất đồng bộ liên cluster | **Không** |
| Backup snapshot | Khôi phục trạng thái từ điểm lưu | **Không** |
| Client retry | Thử lại operation sau lỗi | **Không** |

Ví dụ một cluster có 1 Data replica và 2 index replicas vẫn cần **2 Data copies** để đạt `MAJORITY` trên một vBucket có 1 replica; index replicas không thể xác nhận mutation thay Data node.

## 13. Thay số replica hoặc node cần rebalance và kiểm tra lại

Couchbase Server cho phép chỉnh `replicaNumber` của bucket. Thay số bản mong muốn có thể đòi **rebalance** để bố trí vBucket mới hoặc phân phối lại.

Các bước kiểm tra có thể dùng trong review thay đổi:

1. Chụp trạng thái trước: danh sách Data nodes, server groups, bucket replica setting, vBucket availability.
2. Xác nhận đủ node/capacity cho số replica dự kiến.
3. Review bucket type, minimum durability và conflict với mức 3 replicas.
4. Chọn maintenance window và dự trù chi phí data movement.
5. Thực hiện theo runbook của DBA/SRE, không thao tác bừa trên production.
6. Theo dõi rebalance tiến độ, active/replica vBuckets, KV p95/p99 và durability errors.
7. Khi rebalance hoàn tất, xác nhận **số bản thực tế** và failure-domain placement.
8. Chạy smoke/integration tests write theo level và kiểm tra không còn under-replicated vBuckets.

### 13.1. “Đổi replica count thành công” không phải “tất cả bản đã khỏe”

Theo tài liệu REST, khi thiếu node, Couchbase có thể chỉ bố trí **maximum số bản có thể** rồi đợi thêm node. Vì vậy kiểm tra response của thao tác quản trị hoặc UI setting chưa đủ. Cần kiểm tra cluster map/replica status sau rebalance.

### 13.2. Rebalance và durable writes

Couchbase duy trì phục vụ thao tác trong rebalance, nhưng có trường hợp hiếm khi một active vBucket được chuyển đúng lúc durable write đang chạy, client nhận **ambiguous result**. Ứng dụng phải xử lý như kết quả chưa xác minh, không tự tạo ID khác để thử lại.

## 14. Failover: bảo toàn majority mới là mục tiêu

Khi active node bị lỗi, cluster có thể promote replica phù hợp thành active. Cơ chế này hỗ trợ availability, nhưng những bảo đảm durable write còn phụ thuộc **bản sao nào giữ mutation** và hành vi failover.

### 14.1. Một majority vừa commit có thể chưa tới replica thứ ba

Ví dụ bucket với 2 replicas:

~~~text
A: active, đã có mutation M
B: replica, đã có mutation M
C: replica, chưa kịp nhận M

MAJORITY = 2 (A + B)
Client được báo durable write success.
~~~

Nếu **cả A và B** bị failover trước khi C nhận M, dữ liệu có thể mất dù M đã từng được xác nhận majority. Đây là giới hạn được tài liệu Couchbase mô tả; **majority bảo vệ trước một số lỗi được định nghĩa, không phải mọi chuỗi nhiều node failover**.

### 14.2. Auto-failover và việc bảo vệ majority

Couchbase Server Enterprise Edition cung cấp cơ chế kiểm soát auto-failover như:

- `maxCount`: giới hạn số lần/node auto-failover liên tiếp trước khi cần can thiệp quản trị.
- `failoverPreserveDurabilityMajority`: ngăn auto-failover một Data node nếu có thể làm mất bảo đảm durable writes.

Theo docs, cấu hình preserve-durable-writes áp giới hạn riêng cho **Data nodes** và có thể nghiêm ngặt hơn về failover để bảo vệ dữ liệu. Tùy chính sách, nó có thể **giảm availability tạm thời** bằng cách từ chối một failover đáng ngại.

### 14.3. Trade-off giữa availability và dữ liệu mới commit

| Chọn chính sách | Lợi ích | Rủi ro/chi phí |
|---|---|---|
| Tích cực failover node lỗi | Có thể phục hồi khả năng phục vụ nhanh | Nếu failover nhiều bản chứa majority trước replication hoàn tất, có thể mất mutation |
| Giới hạn auto-failover | Giữ được nhiều bản chứa mutation hơn | Một số node lỗi vẫn không được auto-failover |
| Bật preserve durability majority | Ưu tiên không làm mất các bản giữ durable write | Có thể ngăn một số failover cần cho availability |
| Manual failover thiếu review | Có thể can thiệp khẩn cấp | Có thể loại bỏ nhầm bản cuối chứa mutation mới |

Đừng dựa vào một setting để khẳng định “không bao giờ mất dữ liệu”. Cần lập runbook cụ thể và diễn tập theo failure scenarios.

## 15. Khi đa số không khả dụng: không hạ yêu cầu một cách âm thầm

Nếu cluster không thể tạo majority, một durable write có thể lỗi hoặc có outcome ambiguous. Việc giảm level trong code ngay khi exception xuất hiện là thay đổi điều kiện mà API hứa với nghiệp vụ.

Couchbase Server hiện hành có tùy chọn đặc biệt `durabilityImpossibleFallback` ở bucket, với các giá trị kiểu `disabled` hoặc `fallbackToActiveAck` trong REST API. Khi bật fallback trong trường hợp được hỗ trợ, server có thể báo success dựa trên active ack dù majority không khả dụng.

### 15.1. Fallback là tình huống suy giảm bảo đảm

Ví dụ bucket có một replica; một node failover khiến thiếu majority. Với fallback:

- API có thể nhận báo success khi chỉ active đáp ứng.
- Nhưng ghi được báo success lúc này **không còn có bảo đảm majority** như khi không suy giảm.
- Những transaction dựa trên durable writes cũng bị ảnh hưởng về bảo đảm.
- Phải xem đây là **thay đổi rủi ro dữ liệu**, không chỉ bật một công tắc “fix availability”.

Nên giữ mặc định **disabled** trừ khi quy trình tổ chức cho phép ngoại lệ, có owner RPO, cảnh báo, thời hạn áp dụng, reconciliation và cách tắt lại.

### 15.2. Khi nào không có “khả năng cứu” bằng fallback?

Nếu active owner của vBucket cũng không thể phục vụ hoặc cluster không có đường định tuyến Data Service hợp lệ, không thể suy ra fallback sẽ giúp mọi thao tác thành công. Đây là cơ chế ngoại lệ của điều kiện majority, **không phải giải pháp cho mọi sự cố hạ tầng**.

## 16. Couchbase Server tự quản lý và Capella: khác trách nhiệm, cùng yêu cầu

Dù dùng **Couchbase Server self-managed** hay **Couchbase Capella**, logic ứng dụng vẫn phải xác định yêu cầu durability và xử lý lỗi. Khác biệt chính nằm ở **ai cấu hình và vận hành cluster**.

| Công việc | Server tự quản lý | Capella |
|---|---|---|
| Số Data nodes và placement | DBA/SRE chủ động thiết kế, vận hành | Chọn cấu hình/tier/deployment được dịch vụ hỗ trợ |
| Replica count trên bucket | DBA/SRE có quyền cấu hình theo phiên bản | Qua công cụ/API/tùy chọn mà deployment cung cấp |
| Server Groups/failure domain | Nhóm vận hành cấu hình theo topology | Phụ thuộc mô hình HA và khả năng dịch vụ |
| Rebalance/failover | DBA/SRE xử lý theo runbook | Nhà cung cấp quản lý nhiều tác vụ, ứng dụng vẫn theo dõi ảnh hưởng |
| Durability per mutation | Java SDK/Spring Data code | Java SDK/Spring Data code |
| Minimum bucket durability | Chính sách bucket do admin quản lý | Theo tính năng và quyền của deployment |
| Backup/RPO/RTO | Tự tổ chức và diễn tập | Chọn policy hỗ trợ, vẫn phải kiểm chứng restore |

Không mặc định mọi Capella deployment có cùng số replica, region, tính năng HA hoặc quyền chỉnh sâu; cần kiểm tra khả năng **được cung cấp cho tier hiện tại**.

### 16.1. Nguyên tắc quan trọng khi chuyển môi trường

Một ứng dụng dùng `MAJORITY` trên self-managed cluster 3 Data nodes với 2 replicas không thể chỉ đổi connection string sang deployment khác rồi coi **mức bảo vệ và khả năng ghi trong sự cố đã tương đương**.

Phải đối chiếu bucket type, replica settings, placement/failure domains, minimum durability, Java SDK version, latency và support matrix.

## 17. Spring Boot và Spring Data Couchbase: cấu hình đúng keyspace

Ví dụ cấu hình `application.yml` trong Spring Boot hiện đại:

~~~yaml
spring:
  couchbase:
    connection-string: "${CB_CONNECTION_STRING}"
    username: "${CB_USERNAME}"
    password: "${CB_PASSWORD}"
  data:
    couchbase:
      bucket-name: "${CB_BUCKET}"
~~~

Trong cấu hình thật, các placeholder được cung cấp qua môi trường hoặc secret manager. Không commit credentials trong source code. Với endpoint TLS, scheme có thể là `couchbases://` theo cấu hình cluster/Capella và truststore phù hợp.

### 17.1. Entity mặc định yêu cầu majority

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

    // Constructor và accessors được lược bỏ.
}
~~~

### 17.2. Repository

~~~java
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {
}
~~~

~~~java
OrderDocument saved = orderRepository.save(order);
~~~

Khi đường repository dùng metadata của entity, `@Document(durabilityLevel = MAJORITY)` mô tả yêu cầu mặc định. **Nhưng nó không tự thay số replica** trên bucket và không tạo Data node. Vì vậy:

- Nếu bucket có 0 replicas, majority chỉ có 1 bản, không tự bảo vệ mất Data node.
- Nếu bucket có 1 replica nhưng node giữ bản đó offline, write majority có thể không hoàn tất.
- Nếu bucket có 3 replicas, Sync Writes không được hỗ trợ theo giới hạn hiện hành dù annotation vẫn hợp lệ Java.
- Nếu bucket có minimum durability mạnh hơn, server áp chính sách hiệu lực đó.

`@Version`/CAS có tác dụng **phát hiện ghi dựa trên phiên bản cũ**, không phải xác nhận replication hoặc persistence.

### 17.3. Đừng xử lý bằng cách “bật durability trong mọi query”

`@Document(durabilityLevel = ...)` liên quan **mutation**. SQL++ `findByStatus` đi qua Query/Index Service và có **scan consistency** riêng. Không chọn một durability level để khắc phục vấn đề index lag hoặc truy vấn thiếu GSI.

## 18. Java SDK: mutation với DurabilityLevel

Dưới đây là ví dụ Java SDK 3.x. Giả định `orders` là `com.couchbase.client.java.Collection` trỏ tới `commerce.sales.orders`.

~~~java
import static com.couchbase.client.java.kv.InsertOptions.insertOptions;

import com.couchbase.client.core.msg.kv.DurabilityLevel;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.MutationResult;

String orderId = "tenant::42::checkout::checkout-abc";
JsonObject body = JsonObject.create()
        .put("tenantId", "42")
        .put("status", "NEW")
        .put("total", 1490000);

MutationResult result = orders.insert(
        orderId,
        body,
        insertOptions().durability(DurabilityLevel.MAJORITY)
);
~~~

Lựa chọn `insert` thay `upsert` không phải vì durability, mà vì **create-only**. Nếu document ID đã tồn tại, ứng dụng cần kiểm tra liệu nó có khớp business command trước hay không.

### 18.1. Replace với CAS và persistence trên active

~~~java
import static com.couchbase.client.java.kv.ReplaceOptions.replaceOptions;
import com.couchbase.client.core.msg.kv.DurabilityLevel;

var previous = orders.get(orderId);
var oldBody = previous.contentAsObject();

if (!"NEW".equals(oldBody.getString("status"))) {
    throw new IllegalStateException("Order không còn ở trạng thái NEW");
}

var next = oldBody.put("status", "PAID");

var saved = orders.replace(
        orderId,
        next,
        replaceOptions()
                .cas(previous.cas())
                .durability(DurabilityLevel.MAJORITY_AND_PERSIST_TO_ACTIVE)
);
~~~

Đoạn code minh họa **CAS** và **durability** là hai lựa chọn độc lập:

- CAS kiểm tra không có writer khác đổi order sau lần đọc.
- Durability yêu cầu điều kiện majority/persistence theo level.
- Validation kiểm tra business invariant, cần logic nghiệp vụ đầy đủ hơn trong ứng dụng thực tế.

### 18.2. Persistence trên majority

~~~java
import static com.couchbase.client.java.kv.UpsertOptions.upsertOptions;

var checkpoint = JsonObject.create()
        .put("jobId", "close-day-2026-11-25")
        .put("state", "DONE");

orders.upsert(
        "checkpoint::close-day-2026-11-25",
        checkpoint,
        upsertOptions().durability(DurabilityLevel.PERSIST_TO_MAJORITY)
);
~~~

Ví dụ này yêu cầu bucket type/storage engine và replica topology hỗ trợ. `upsert` có thể thay body đã tồn tại, nên dùng cho checkpoint khi nghiệp vụ cho phép; không dùng tùy tiện cho create-once.

### 18.3. Điều kiện hạ tầng vẫn quyết định thành công

Code với `PERSIST_TO_MAJORITY` không thể bắt disk của replica hoàn tất nếu:

- Replica chưa được đặt trên một Data node hoạt động.
- Storage không hỗ trợ persistence level.
- Network replication bị gián đoạn.
- Data Service đang quá tải hoặc cluster thiếu majority.
- Bucket không hỗ trợ Sync Writes với số replica hiện tại.

Khi đó ứng dụng phải xử lý lỗi, không coi compile thành công là đáp ứng RPO.

## 19. CouchbaseTemplate override theo use case

Spring Data Couchbase fluent template hỗ trợ chỉ định durability cho operation trong các phiên bản phù hợp:

~~~java
import com.couchbase.client.core.msg.kv.DurabilityLevel;
import org.springframework.data.couchbase.core.CouchbaseTemplate;

public class CriticalOrderWriter {

    private final CouchbaseTemplate template;

    public CriticalOrderWriter(CouchbaseTemplate template) {
        this.template = template;
    }

    public OrderDocument persistCritical(OrderDocument order) {
        return template
                .upsertById(OrderDocument.class)
                .withDurability(DurabilityLevel.PERSIST_TO_MAJORITY)
                .one(order);
    }
}
~~~

Giả sử default entity là `MAJORITY`, operation này yêu cầu level khác. Tuy vậy:

- `upsertById` có semantics tạo-hoặc-thay, không tự chống duplicate.
- `withDurability` chỉ điều chỉnh **mutation hiện tại** theo API, không sửa bucket `replicaNumber`.
- Minimum durability tại bucket vẫn có hiệu lực.
- Các API/template methods phụ thuộc Spring Data version; kiểm tra dependencies và integration test.

### 19.1. Chọn chính sách ở đâu?

| Chiến lược | Khi phù hợp | Rủi ro |
|---|---|---|
| `@Document(durabilityLevel=MAJORITY)` | Entity có mức mặc định giống nhau | Đường SDK trực tiếp có thể bỏ qua annotation |
| Template `withDurability(...)` | Một số operation cần khác mức mặc định | Có thể quên override trong một code path |
| Java SDK `*Options.durability(...)` | Cần kiểm soát KV per-operation | Phải giữ mapping/CAS/TTL nhất quán với Spring Data |
| Bucket `durabilityMinLevel` | Muốn policy bao trùm các client dùng chung bucket | Tăng latency/giảm write availability của mọi workload khi suy giảm |

Nếu minimum ở bucket được nâng lên `PERSIST_TO_MAJORITY`, mọi mutation chịu chính sách đó có thể chờ storage dù code application gửi `NONE` hoặc không truyền option.

## 20. Reactive API không thay điều kiện majority

Với reactive Java SDK, mutation vẫn được thực hiện theo level tương tự:

~~~java
import static com.couchbase.client.java.kv.InsertOptions.insertOptions;

import com.couchbase.client.java.kv.MutationResult;
import reactor.core.publisher.Mono;

Mono<MutationResult> pendingWrite = orders.reactive().insert(
        orderId,
        body,
        insertOptions().durability(DurabilityLevel.MAJORITY)
);
~~~

Reactive cho phép không block thread trong lúc đợi I/O. Nhưng **không làm quorum dễ đạt hơn** khi thiếu Data replica, và không tự làm disk nhanh hơn.

### 20.1. Resubscribe nguy hiểm với ambiguous outcome

Nếu dùng `retryWhen` mà response của một mutation đã commit bị mất, Reactor có thể thực hiện lại thao tác. Khi business ID được sinh mới trong mỗi lần retry, có thể tạo hai order.

Quy tắc an toàn:

1. Sinh order ID/idempotency key ổn định trước khi subscription.
2. Chọn `insert` cho create-only.
3. Phân loại lỗi duplicate, CAS conflict, durability impossible và timeout ambiguous.
4. Giới hạn concurrency, backoff và retry budget.
5. Khi outcome chưa rõ, đọc/đối soát document, không tự tạo ID mới.
6. Giữ trạng thái business workflow rõ ràng khi chưa thể xác nhận ghi.

`ReactiveCouchbaseRepository` và template reactive cũng dựa trên cùng Data Service và điều kiện durability server-enforced.

## 21. Phân loại lỗi khi replica/topology không đáp ứng

| Triệu chứng | Nguyên nhân có thể | Điều developer nên làm | DBA/SRE kiểm tra |
|---|---|---|---|
| `EDurabilityImpossible` trên bucket 3 replicas | Sync Writes không hỗ trợ 3 replicas theo docs hiện hành | Đánh giá lại topology/policy, không retry vô hạn | Bucket config và phương án migration |
| Durability impossible/not available | Thiếu replica, bucket không tương thích hoặc level không đáp ứng | Báo lỗi rõ, giữ level đã phê duyệt | Replica, storage, Data nodes, network |
| Timeout/ambiguous | Response thất lạc, pending write hoặc node failover | ID/idempotency, reconciliation | Logs, failover/rebalance, durability timeout |
| `SYNC_WRITE_IN_PROGRESS` | Key đang có durable write pending | Retry có điều kiện hoặc trả conflict | Contention/hot key nếu kéo dài |
| CAS mismatch | Writer khác sửa document | Đọc lại, kiểm tra business state | Chỉ khi contention vượt thiết kế |
| Ghi mặc định vẫn được nhưng `MAJORITY` lỗi | Active sống nhưng quorum không đủ | Đừng hạ level tự động | Replica health và quorum |
| `MAJORITY` ổn, persist level chậm | Disk/persistence bottleneck | Đo p99, deadline, retry | Disk I/O/storage engine/placement |
| `findById` được, SQL++ thiếu row | Index lag, filter, index status | Kiểm tra scan consistency | Query/Index Service |
| Sau failover số bản ít hơn mong muốn | Under-replication hoặc chưa rebalance | Gửi metric, giới hạn traffic nếu policy cần | Recovery/rebalance và placement |

Tên exception chính xác phụ thuộc Java SDK/Spring Data exception translation. Không viết catch-all chuyển mọi lỗi thành success hoặc retry vô hạn.

### 21.1. Vì sao timeout không chứng minh thất bại?

~~~mermaid
sequenceDiagram
    participant Client as order-service
    participant A as Active Data node
    participant B as Replica
    Client->>A: INSERT with MAJORITY
    A->>B: Replicate
    B-->>A: Majority condition reached
    Note over A,B: Có thể đã commit
    A--xClient: Response thất lạc
    Note over Client: Timeout, trạng thái chưa rõ
~~~

Server có thể commit, nhưng client không nhận phản hồi. Nếu retry bằng ID mới, sẽ có nguy cơ duplicate. Nếu server chưa commit, có thể retry phù hợp; client phải xử lý **cả hai khả năng**.

### 21.2. Idempotency cho API tạo đơn

~~~text
POST /orders
Idempotency-Key: checkout-abc

orderId = tenant::42::checkout::checkout-abc

Lần 1: insert với MAJORITY -> timeout ambiguous
Lần 2: không tự tạo orderId khác
       -> kiểm tra document cùng ID
       -> nếu có, so fingerprint của yêu cầu
       -> nếu không rõ, retry có kiểm soát / reconciliation
~~~

Nếu workflow có payment gateway, cần idempotency ở gateway theo khả năng dịch vụ. Durability của Couchbase không tự bảo đảm external payment được thực hiện đúng một lần.

## 22. Read-only checks: kiểm tra cấu hình gì trước khi ghi code?

Ứng dụng runtime không cần admin password; **DBA/SRE** hoặc một kênh monitoring có quyền phù hợp có thể lấy thông tin config để cung cấp cho developer.

### 22.1. Danh sách dữ liệu cần thu thập

| Thành phần | Giá trị cần xác nhận | Lý do |
|---|---|---|
| Bucket `commerce` | `bucketType` | Có hỗ trợ persistence-level không? |
| Bucket `commerce` | `replicaNumber` | Có 0, 1, 2 hay 3 replica? |
| Bucket `commerce` | `durabilityMinLevel` | Mức tối thiểu mọi mutation |
| Bucket `commerce` | `durabilityImpossibleFallback` | Có nguy cơ success bị downgrade khi mất quorum không? |
| Cluster | Số node chạy Data Service | Có đủ host để đặt active + replicas? |
| vBucket map/status | Active/replica thực sự khỏe | Bucket config có được hiện thực đầy đủ? |
| Server Groups | Failure domain placement | Active và replica có thể cùng rủi ro không? |
| Auto-failover | `maxCount` / `failoverPreserveDurabilityMajority` | Có bảo vệ khỏi loại bỏ cả majority chứa mutation không? |
| Rebalance | Tiến độ, lỗi, thay đổi owner | Có đang trong giai đoạn data movement? |
| Storage/network | Disk latency, utilization, inter-node reachability | Level persistence có đủ performance không? |

### 22.2. Những REST endpoints để DBA/SRE tham khảo

Các endpoint đọc cấu hình Couchbase Server tự quản lý (quyền và cách truy cập phụ thuộc triển khai):

~~~text
GET /pools/default/buckets/commerce
    -> bucket settings, replicaNumber, durabilityMinLevel...

GET /settings/dataService
    -> minReplicasCount (policy cho bucket mới)

GET /settings/autoFailover
    -> enabled, timeout, maxCount,
       failoverPreserveDurabilityMajority...
~~~

Không đưa mật khẩu admin vào mã hoặc log. Endpoint/response cụ thể cần được đối chiếu version. Trên Capella có thể phải dùng console/API managed được cho phép thay vì REST admin tương tự self-managed.

### 22.3. Ví dụ báo cáo trạng thái giả lập

~~~text
Cluster:
  Data nodes: A, B, C
  Server groups: Zone A, Zone B, Zone C

Bucket commerce:
  type: couchbase
  replicaNumber: 2
  minimum durability: majority
  actual active/replica placement: 3 copies for sampled vBuckets
  missing replica: 0 (trong mẫu kiểm tra)
  fallback: disabled

Application:
  order-service write: MAJORITY
  critical settlement: PERSIST_TO_MAJORITY
  SDK/server compatible: verified in staging
~~~

Các giá trị là **ví dụ**, không phải dữ liệu đã được đọc từ hệ thống thật. Production review cần đối chiếu toàn bucket, không chỉ lấy một vBucket mẫu rồi khẳng định mọi vBucket khỏe.

## 23. RPO, RTO và write availability: yêu cầu cần được viết rõ

Thay vì nói “cluster có nhiều replica nên an toàn”, hãy mô tả bằng kịch bản:

| Mục tiêu | Câu hỏi cần trả lời |
|---|---|
| **RPO** | Trong lỗi nào cho phép mất bao nhiêu mutation đã được báo success? |
| **RTO** | Khi Data node lỗi, API ghi khôi phục trong bao lâu? |
| **Write SLO** | Bao nhiêu phần trăm writes với đúng durability level thành công? |
| **Latency SLO** | p95/p99 của KV mutation và HTTP API là bao nhiêu? |
| **Failure domains** | Chịu được mất host, rack/zone hay region? |
| **Ambiguous outcome** | Mỗi request chưa xác nhận được sẽ đối soát thế nào? |
| **DR** | Backup/restore hoặc XDCR xử lý mất cluster/site thế nào? |

### 23.1. Ví dụ tiêu chí chấp nhận ở staging

Một nhóm chọn bucket với **2 replicas** và `MAJORITY` cho đơn hàng. Test acceptance có thể gồm:

1. Khi cluster khỏe, request tạo đơn với ID ổn định trả success theo contract.
2. Khi một replica không khả dụng, ghi trên những vBucket vẫn có đủ majority tiếp tục; nếu không đủ, lỗi phải được phân loại.
3. Khi failover, không tạo duplicate do retry.
4. Sau khi recovery/rebalance, số bản active/replica đạt cấu hình mong muốn.
5. Không xuất hiện việc silently trả success ở level yếu hơn nếu fallback không được phê duyệt.
6. HTTP p95/p99 đáp ứng SLO đã thống nhất hoặc có lý do không đáp ứng được ghi nhận.
7. Sau restore/DR drill, dữ liệu quan trọng được đối soát theo RPO.

Đây là **mẫu acceptance criteria**, không phải đảm bảo kỹ thuật cho mọi Couchbase cluster.

## 24. Tài nguyên phải đủ để duy trì replica và durability

Chỉ tăng `replicaNumber` mà không dự trù RAM/disk/network có thể tạo áp lực lên hệ thống.

### 24.1. Sizing theo dữ liệu

Với nhiều replica, cluster phải lưu và duy trì nhiều bản dữ liệu. Điều này ảnh hưởng:

- **Disk capacity:** bản sao trên các node; cộng thêm index, tombstone, compaction và headroom.
- **RAM:** active/replica metadata, cache và hoạt động Data Service.
- **Network:** replication giữa Data nodes.
- **Disk throughput:** persistence ở active/replica, đặc biệt `PERSIST_TO_MAJORITY`.
- **Recovery/rebalance:** di chuyển nhiều dữ liệu hơn.
- **Operational cost:** thêm Data nodes, vùng/host để phân bố failure domains.

Không dùng một công thức đơn giản “dataSize × (replicas+1)” làm sizing production duy nhất, bởi compression, metadata, index, disk headroom, churn, storage engine và load làm thay đổi nhu cầu thật.

### 24.2. N-1 capacity

Nếu mục tiêu là hoạt động khi mất một Data node, hãy thử tải khi **mất node được phép mô phỏng**:

- Những Data nodes còn lại có chịu được active ownership tăng không?
- Replica đủ điều kiện có còn sau failover/rebalance không?
- Query/Index Service có nghẽn không (nếu app cần SQL++)?
- KV write p99 có vượt deadline không?
- Có backlog replication và under-replication không?
- Khi khôi phục node và rebalance, latency có ổn định không?

Điều này nên được tính vào **capacity planning trước sự cố**, không đợi production down rồi mới đo.

## 25. Test matrix cho replica count và lỗi

Các bài test sau dùng **môi trường thử nghiệm được phê duyệt**, không hard failover production chỉ để học.

| Test | Topology | Mục tiêu |
|---|---|---|
| 0 replica + `MAJORITY` | 1 Data node | Hiểu majority=1 nhưng không có failover copy |
| 1 replica + `MAJORITY` | 2 Data nodes | Hiểu điều kiện 2/2 và cách báo lỗi khi thiếu replica |
| 2 replicas + `MAJORITY` | 3 Data nodes | Hiểu điều kiện 2/3 và ảnh hưởng khi một replica không khả dụng |
| 3 replicas + Sync Write | 4 Data nodes | Xác minh giới hạn không hỗ trợ trong Server hiện hành |
| Couchbase bucket + persist level | Disk/persistence có hỗ trợ | Xác minh level và latency |
| Ephemeral bucket + persist level | Không có persistence tương ứng | Xác minh từ chối level không hỗ trợ |
| Bucket minimum mạnh hơn SDK | SDK yêu cầu `NONE` | Không thể bỏ qua policy |
| Đổi `replicaNumber` khi thiếu node | Under-replicated deployment | Không suy ra từ config rằng mọi bản đã đặt |
| Rebalance trong lúc durable write | Test cluster đang data movement | Phân loại ambiguous, không duplicate |
| Failover nhiều Data nodes | Theo runbook có kiểm soát | Hiểu nguy cơ mất majority chứa mutation mới |
| Fallback được bật theo test case | Test cluster với 1 replica | Đo suy giảm bảo đảm, không dùng như success an toàn |
| Reactive retry / mất response | Mutation có thể đã commit | Một business command không tạo hai order |
| Backup/restore | Khôi phục sang cluster riêng | RPO/RTO và dữ liệu sau restore |

### 25.1. Không mô phỏng lỗi bằng cách chỉ dừng Java client

Dừng client hoặc giảm HTTP timeout chủ yếu tạo **lỗi phía caller**. Nó không chứng minh cluster đã mất replica. Muốn kiểm tra quorum, phải có điều kiện hạ tầng được DBA/SRE điều phối và xác minh vBucket distribution.

### 25.2. Không dùng SQL++ làm bằng chứng đã persist

Một query `SELECT WHERE status='PAID'` có thể chưa thấy write mới do GSI lag. Một query có thể thấy row nhưng vẫn không chứng minh điều kiện persistence majority nếu mutation trước không yêu cầu level đó.

Hãy phân biệt **durability**, **KV visibility**, **GSI scan consistency** và **backup/restore**.

## 26. Case study A — cluster ba node nhưng thiếu Data replica

**Bối cảnh:** dashboard cho thấy ba node:

~~~text
A: Data + Query
B: Query + Index
C: Index

commerce.replicaNumber = 2
App yêu cầu MAJORITY
~~~

Một developer suy ra có ba node nên đã có active + 2 replicas. Nhưng chỉ A chạy **Data Service**, nên không có ba host để đặt đủ bản.

**Phân tích và xử lý:**

1. Kiểm tra service assignment, không chỉ node count.
2. Xem actual vBucket replica placement và cảnh báo under-replication.
3. Thiết kế thêm Data nodes đủ capacity/failure domains với DBA/SRE.
4. Rebalance và kiểm tra bản sao thực tế.
5. Chạy lại integration/failure tests ở đúng topology.

**Bài học:** số node cluster và replica setting **không thay thế bằng chứng placement**.

## 27. Case study B — một replica làm durable writes ngừng trong bảo trì

**Bối cảnh:** bucket có một replica, active A và replica B cho một số vBucket. Đội vận hành graceful failover B để bảo trì, app vẫn kết nối A.

Với majority=2/2, durable writes ở những vBucket thiếu replica có thể không hoàn tất. Có người đề xuất bật fallback.

Đánh giá:

- Nếu bật `durabilityImpossibleFallback=fallbackToActiveAck`, một số writes có thể được báo success nhưng **không đạt quorum**.
- Nếu sản phẩm hứa đơn không được mất sau node failure, fallback không phù hợp nếu chưa được duyệt rủi ro.
- Có thể chủ động lên kế hoạch capacity/topology, tạm dừng ghi critical hoặc xếp hàng vào hệ thống bền độc lập đã được thiết kế trước.
- Cần phục hồi replica và tắt fallback ngay sau thời gian ngoại lệ được phê duyệt.

**Bài học:** bảo trì node phải tính đến **majority của từng vBucket**, không chỉ số Data nodes còn bật.

## 28. Case study C — hai replica nhưng failover hai node chứa mutation

**Bối cảnh:** bucket có hai replica; mutation M được xác nhận trên active A và replica B, nhưng chưa tới replica C. API được báo success theo `MAJORITY`.

Nếu A và B cùng bị failover trước khi C nhận M, bản cuối có thể chưa có mutation. Tài liệu Couchbase cảnh báo trường hợp này; đây là lý do auto-failover cần được cấu hình bảo vệ majority.

Cách đánh giá:

1. Xác định scope bảo đảm yêu cầu: mất **một node** hay **nhiều node gần đồng thời**?
2. Thiết lập policy auto-failover, chẳng hạn giới hạn `maxCount` và/hoặc `failoverPreserveDurabilityMajority` theo edition.
3. Cấu hình failure domains sao cho lỗi tập trung ít khả năng cùng xóa cả majority.
4. Có backup/DR cho lỗi vượt scope.
5. Diễn tập các kịch bản được phép và đo RPO/RTO.

**Bài học:** đạt majority không đồng nghĩa chịu mọi chuỗi failover, và chính sách failover có thể đánh đổi availability để tránh mất dữ liệu mới commit.

## 29. Bài tập thực hành

### Bài A — tính majority

Bucket `commerce` có 0, 1 hoặc 2 replica. Hãy xác định số Data copies và số bản để đạt majority. Với 3 replicas, tại sao không được chỉ áp công thức `floor(4/2)+1` rồi khẳng định Sync Write được hỗ trợ?

### Bài B — số node thực tế

Một cluster có bốn node, chỉ hai node chạy Data Service. Bucket mong muốn hai replicas. Có đủ nơi để đặt ba bản trên ba host độc lập không? Những số liệu nào cần xem để chứng minh?

### Bài C — phân biệt ba config

Giải thích `replicaNumber`, `minReplicasCount` và `durabilityMinLevel`. Policy `minReplicasCount=2` được bật hôm nay có tự tăng replica của bucket cũ hay không?

### Bài D — persistence và bucket type

Một application yêu cầu `PERSIST_TO_MAJORITY` trên Ephemeral bucket. Tại sao đây là lựa chọn không hợp lệ? Cần đổi gì trong thiết kế storage/bucket thay vì retry?

### Bài E — failover

Một write `MAJORITY` vừa được xác nhận ở A và B trong bucket hai replicas. C chưa nhận mutation, A và B bị failover. Rủi ro gì xảy ra? Cấu hình auto-failover nào giúp hạn chế tình huống này theo edition hỗ trợ?

### Bài F — Spring Data

Entity `@Document(durabilityLevel = MAJORITY)` đã được lưu bằng `repository.save`. Từ đó có thể suy ra node B có mặt và khỏe không? Cần kiểm tra gì từ topology và bucket policy?

### Bài G — Java SDK

Viết `orders.insert(..., insertOptions().durability(MAJORITY))` và `orders.replace(..., replaceOptions().cas(...).durability(MAJORITY_AND_PERSIST_TO_ACTIVE))`. Giải thích hai điều kiện CAS và durability giải quyết hai vấn đề nào.

### Bài H — phản ứng với lỗi

Một mutation timeout sau khi active có thể đã commit. Tại sao retry với ID mới nguy hiểm? Thiết kế idempotency key, readback và reconciliation.

### Bài I — performance

Với cùng workload, so p99 của `MAJORITY` và `PERSIST_TO_MAJORITY`. Nếu mức persistence chậm hơn, có nên giảm level ngay không? Liệt kê dữ liệu về disk/network/replica và RPO cần xem trước.

### Bài J — cùng một bucket nhiều service

Order, cache và session cùng bucket có `durabilityMinLevel=persistToMajority`. Phân tích tác động tới p99 và availability của cache/session. Khi nào nên phân chia keyspace hoặc policy?

### Bài K — server groups

Một active và hai replicas được đặt lên ba Data nodes nhưng cùng rack/nguồn điện. Đây có bảo vệ tốt trước mất rack không? Đề xuất bố trí failure domains và kiểm tra quota.

### Bài L — change management

Thiết kế kế hoạch nâng bucket từ một replica lên hai replicas: trước, trong, sau rebalance cần kiểm tra gì; rollback ra sao; ai có quyền quyết định và test failure nào cần chạy?

## 30. Checklist trước production

- [ ] Xác nhận số replicas trong bucket **và** số Data nodes đủ điều kiện đặt bản.
- [ ] Đọc actual vBucket distribution; không chỉ tin `replicaNumber`.
- [ ] Với Sync Writes theo docs Server hiện hành, chỉ dùng bucket 0–2 replicas; tránh 3 replicas.
- [ ] Hiểu majority 1/1, 2/2, 2/3 và khả năng ghi khi thiếu bản.
- [ ] Không dùng majority với 0 replicas để hứa bảo vệ mất cả Data node.
- [ ] Kiểm tra bucket type: Couchbase vs Ephemeral trước khi chọn persist level.
- [ ] Phân biệt `minReplicasCount` (cluster policy cho bucket mới) và `durabilityMinLevel` (bucket policy).
- [ ] Đối chiếu mức client và bucket minimum theo quy tắc level hiệu lực.
- [ ] Kiểm tra Server Groups/failure domains và placement active/replica trên các host riêng.
- [ ] Có N-1 capacity, disk/network headroom, monitoring dưới-replication.
- [ ] Bảo đảm rebalance sau đổi node/replica count và xác minh kết quả.
- [ ] Review auto-failover `maxCount`/`failoverPreserveDurabilityMajority` theo edition và RPO.
- [ ] Không bật `durabilityImpossibleFallback` để che lỗi khi chưa được phê duyệt.
- [ ] Dùng ID ổn định, CAS và idempotency cho critical writes.
- [ ] Xử lý `ambiguous` bằng xác minh/reconciliation, không retry tạo ID mới.
- [ ] Với Spring Data, kiểm tra `@Document` và template/SDK options thực sự có hiệu lực.
- [ ] Với reactive, hạn chế concurrent durable writes/retry storms.
- [ ] Đo KV write p95/p99, failures, replica health, disk I/O và business errors.
- [ ] Phân biệt Data replicas với Index replicas, XDCR và backup.
- [ ] Có restore/DR plan cho xóa nhầm, mất nhiều node hoặc toàn region.
- [ ] Thử failure cases ở staging/test cluster được phép, không hard failover production để học.

## 31. Tổng kết

**Điều kiện số bản sao và cấu hình cụm là một phần của hợp đồng độ bền ghi**, không chỉ là chi tiết hậu trường. Trong Couchbase, mutation đi đến active vBucket và có thể được sao chép tới những Data replicas. Theo tài liệu Server hiện hành, Sync Writes hỗ trợ bucket có **0, 1 hoặc 2 replicas** với majority tương ứng **1, 2 hoặc 2**; bucket cấu hình **3 replicas không hỗ trợ Sync Writes**.

Một bucket có `replicaNumber=2` nhưng không đủ ba Data nodes hoặc chưa hoàn tất rebalance **không tự có ba bản khỏe**. Tương tự, minimum durability không tự tạo replica, auto-failover không tự bảo vệ mọi chuỗi lỗi và server groups không thay thế backup/DR.

Với **Spring Data Couchbase**, `@Document(durabilityLevel=...)`, `CouchbaseTemplate.withDurability(...)` hoặc Java SDK mutation options chỉ là một phần. Để thật sự đạt RPO và SLO, hãy kiểm tra **bucket type, actual replica placement, failure domains, quorum, disk/network, auto-failover, retry/idempotency và cách đối soát kết quả ambiguous**. Đó là cách biến yêu cầu “ghi bền” thành điều kiện kỹ thuật có thể chứng minh, đo đạc và vận hành.

## Tài liệu tham khảo chính thức

1. [Couchbase Server — Durability](https://docs.couchbase.com/server/current/learn/data/durability.html): majority table 0/1/2 replicas, giới hạn 3 replicas, Sync Writes, failure scenarios và failover protection.
2. [Couchbase Server — Creating and Editing Buckets (REST)](https://docs.couchbase.com/server/current/rest-api/rest-bucket-create.html): `replicaNumber`, `durabilityMinLevel`, `durabilityImpossibleFallback` và cảnh báo không đủ node để đặt replicas.
3. [Couchbase Server — Setting a Replica-Minimum](https://docs.couchbase.com/server/current/rest-api/setting-minimum-replicas.html): `minReplicasCount` áp dụng cho bucket mới.
4. [Couchbase Server — Server Group Awareness](https://docs.couchbase.com/server/current/learn/clusters-and-availability/groups.html): placement theo failure domains.
5. [Couchbase Server — Cluster Manager](https://docs.couchbase.com/server/current/learn/clusters-and-availability/cluster-manager.html): vBucket map và active/replica placement.
6. [Couchbase Server — Auto-Failover Settings](https://docs.couchbase.com/server/current/rest-api/rest-cluster-autofailover-enable.html): `maxCount` và `failoverPreserveDurabilityMajority`.
7. [Couchbase Java SDK — Data Operations](https://docs.couchbase.com/java-sdk/current/howtos/kv-operations.html): `DurabilityLevel` trong mutation options.
8. [Spring Data Couchbase — Template & Direct Operations](https://docs.spring.io/spring-data/couchbase/reference/couchbase/template.html): entity default và `withDurability(...)`.

Các mô hình node, mã và con số độ trễ trong bài là ví dụ giáo dục. Khi thiết kế production cần đối chiếu **version Couchbase Server hoặc Capella, bucket type, edition, SDK, Spring Data và topology thực tế**.


