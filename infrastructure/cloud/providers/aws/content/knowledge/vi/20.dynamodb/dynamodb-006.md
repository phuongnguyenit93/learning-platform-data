# Read consistency và đánh đổi hiệu năng trong Amazon DynamoDB

Một ứng dụng Java/Spring Boot ghi trạng thái đơn hàng bằng `UpdateItem`, nhận response thành công rồi gọi `GetItem`. Tại sao đôi khi kết quả vẫn là trạng thái cũ? Nếu bật `ConsistentRead=true` cho mọi read, ứng dụng có chính xác hơn trong mọi tình huống không? Khi đọc qua **Global Secondary Index (GSI)** hoặc **Global Tables** thì sao? Những câu hỏi này không thể giải quyết chỉ bằng tăng read capacity.

**Read consistency** xác định độ mới mà ứng dụng có thể kỳ vọng khi đọc một item. Nó khác với **transaction isolation**, **cạnh tranh ghi**, **đồng bộ index**, **cache freshness**, **độ trễ mạng** và **chi phí RCU/RRU**. Hệ thống đúng phải nắm rõ bất biến nghiệp vụ và chọn consistency phù hợp cho từng access pattern.

Bài thuộc chương **DynamoDB** của mô-đun **CLOUD_PROVIDERS_AWS**, liên hệ Region/AZ, IAM, VPC, Lambda/ECS, DynamoDB Global Tables, DAX, CloudWatch, phục hồi và kiểm soát chi phí. Ví dụ dùng AWS SDK for Java 2.x và Region `ap-southeast-1`. Tất cả table/IDs chỉ để minh họa.

> **Nguyên tắc:** Một **strongly consistent read** trên **base table/LSI** thấy những writes đã thành công trước đó, nhưng **không khóa item**, không tạo snapshot toàn bảng, không khiến **GSI** strong và không thay thế **ConditionExpression** khi cập nhật.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **eventual**, **strong** và **transactional** reads.
2. Giải thích lý do DynamoDB mặc định eventual, và chọn strong khi cần.
3. Biết table, **LSI**, **GSI**, **Streams**, DAX và Global Tables hỗ trợ các mức consistency nào.
4. Sử dụng `ConsistentRead` trong `GetItem`, `Query`, `Scan`, `BatchGetItem`.
5. Giải thích `TransactGetItems` và giới hạn atomic multi-item reads.
6. Tính read capacity **RCU/RRU theo mỗi 4 KiB** cho eventual/strong/transactional.
7. Hiểu tác động của `FilterExpression`, `ProjectionExpression`, `Limit`, pagination và hot partition.
8. Phân biệt Global Tables **MREC** và **MRSC** trên AWS hiện hành.
9. Thiết kế read-after-write, cache/consistency, optimistic concurrency, transactional updates.
10. Viết Java SDK v2, AWS CLI read-only và đo CloudWatch metrics.
11. Đánh đổi tính đúng, độ trễ, throughput, availability và tổng chi phí.
12. Phân biệt stale read, throttle, index lag và lỗi application trong troubleshooting.

## 2. DynamoDB đã xác nhận write nhưng read vẫn cũ?

Một `PutItem`/`UpdateItem`/`DeleteItem` trả success nghĩa là DynamoDB đã **lưu bền vững** thay đổi theo cam kết. Tuy nhiên read mặc định có thể đi qua một bản sao chưa được đồng bộ đầy đủ. DynamoDB có **read-committed isolation**: read không trả dữ liệu từ một write chưa từng commit thành công. Read-committed **không** ngăn item bị sửa ngay sau read.

~~~mermaid
sequenceDiagram
    participant API as Order API
    participant DB as DynamoDB table
    participant E as Eventual read
    participant S as Strong read
    API->>DB: UpdateItem status=PAID
    DB-->>API: Success
    API->>E: GetItem default
    E-->>API: Có thể thấy PENDING tạm thời
    API->>S: GetItem ConsistentRead=true
    S-->>API: PAID (nếu không có write mới)
~~~

Nếu client **không nhận được response write** do timeout, đó là **unknown outcome**, không phải chứng minh write thất bại. Dùng business request ID, conditional writes và state query để tránh double update.

| Thuật ngữ | Ý nghĩa |
|---|---|
| **Durability** | Write thành công được lưu bền vững |
| **Eventually consistent** | Read có thể thấy phiên bản cũ, rồi hội tụ |
| **Strongly consistent** | Read thấy những successful writes trước khi read trong phạm vi hỗ trợ |
| **Read committed** | Không đọc state của write cuối cùng bị rollback/thất bại |
| **Transactional/serializable** | Đọc nhiều items theo semantics của transaction |
| **Read-after-write** | Muốn thấy kết quả write vừa thành công khi đọc sau |
| **Optimistic concurrency** | Chỉ update nếu version/state vẫn khớp mong đợi |

Không có SLA cố định kiểu “GSI đồng bộ trong đúng 100 ms” cho mọi tình huống; đừng biến độ trễ replication trung bình thành business guarantee.

## 3. Eventually consistent read: mặc định và ưu điểm

`GetItem`, `Query` và `Scan` mặc định dùng eventual read; có thể trả dữ liệu cũ sau một write vừa thành công.

~~~text
t0  Order.status = PENDING
t1  UpdateItem(status = PAID) → success
t2  GetItem (eventual)         → có thể PENDING
t3  Read sau khi hội tụ       → PAID
~~~

Điều này không có nghĩa DynamoDB mất dữ liệu hoặc mọi eventual read đều cũ. Một eventual read **có thể** nhận ngay phiên bản mới; chỉ không **bảo đảm** luôn nhận mới nhất.

Khi nào phù hợp? Product catalog, search listing, analytics gần thời gian thực, homepage, dashboards chấp nhận stale trong thời gian ngắn, nhiều read traffic cần giảm chi phí.

**Ưu điểm dung lượng:** Với item đến 4 KiB, một eventual read dùng khoảng **0,5 read units**, so với **1** của strong. Vì vậy có thể phục vụ khoảng gấp đôi lượng reads trên cùng capacity budget khi các giả định khác bằng nhau.

**Không dùng eventual read làm rào chắn duy nhất** cho hết stock, cấp coupon một lần, phát vé duy nhất hoặc trừ tiền. Những nghiệp vụ này cần **conditional writes**, optimistic lock hoặc transaction.

## 4. Strongly consistent read: độ mới nhưng không phải khóa

Với **base table** và **Local Secondary Index (LSI)**, đặt:

~~~text
ConsistentRead = true
~~~

cho `GetItem`/`Query`/`Scan` (theo API/target hỗ trợ). Strong read phản ánh successful writes hoàn thành trước đó. Nó tốn khoảng **hai lần read units** so với eventual với cùng item sizes và có thể có latency khác.

### 4.1. Strong không ngăn lost update

~~~text
1. Worker A GetItem(strong) → stock=1
2. Worker B GetItem(strong) → stock=1
3. A UpdateItem(stock=0)
4. B UpdateItem(stock=0)
~~~

Hai workers đều đọc mới nhất **tại thời điểm đọc**, nhưng giá trị đó không tự khóa trạng thái. Nếu mỗi worker đồng thời phát hành một vé từ stock=1, nghiệp vụ đã sai.

Giải pháp là atomic conditional update:

~~~text
UpdateItem:
  UpdateExpression: SET stock = stock - :q, version = version + :one
  ConditionExpression: stock >= :q AND version = :expected
~~~

Hoặc transaction đa item khi cần. Strong read giúp UX/thẩm định nhưng **không thay ConditionExpression**.

### 4.2. Strong Scan không có snapshot isolation

Một `Scan ConsistentRead=true` đảm bảo độ mới tại **mỗi item được đọc**, không tạo snapshot toàn bảng cùng một thời điểm. Nếu application đang ghi trong lúc scan nhiều pages, page đầu và page cuối có thể thấy các phiên bản ở những thời điểm khác nhau.

Nếu báo cáo kế toán đòi trạng thái “toàn bảng tại 12:00:00”, phải có thiết kế snapshot/export/event watermark hoặc cơ chế phù hợp; bật strong trên Scan **không đủ**.

## 5. Ma trận consistency: table, LSI, GSI, Streams, DAX

| Nguồn | Eventual | Strong | Transactional read |
|---|---|---|---|
| **Base table** | Có | Có | Có qua `TransactGetItems` |
| **LSI** | Có | Có trong `Query/Scan` | Không phải target trực tiếp của `TransactGetItems` |
| **GSI** | **Có** | **Không** | Không |
| **DynamoDB Streams** | **Có** | **Không** | Không |
| **DAX cache** | Cache eventual | Strong chuyển thẳng về DynamoDB, **không cache result** | `TransactGetItems` pass-through |
| **Global Tables MREC replica** | Có | Chỉ đảm bảo latest **đã có mặt tại Region đọc** | Trong một Region, không atomic across Regions |
| **Global Tables MRSC replica** | Có | **Có across Regions với strong read** | **Không hỗ trợ transaction APIs** |

### 5.1. Local Secondary Index (LSI)

LSI **chung partition key** với base table, khác sort key/projection. Nó được tạo khi tạo table, có thể strongly consistent `Query`. LSI chịu giới hạn item collection **10 GiB cho một partition-key value** ở bảng có LSI; đọc những attributes không project vào LSI có thể kéo thêm dữ liệu từ bảng gốc.

### 5.2. Global Secondary Index (GSI)

GSI có thể dùng **partition key khác** để phục vụ access pattern mới. Dữ liệu GSI được cập nhật **bất đồng bộ** từ base table; vì thế:

- **Chỉ eventual read**, không có strong GSI Query.
- `ConsistentRead=true` cùng `IndexName=GSI1` gây **ValidationException**.
- Một item vừa ghi vào table có thể **chưa xuất hiện** khi Query GSI; attributes vừa sửa có thể chưa cập nhật.
- `ProjectionType` và index entry size ảnh hưởng read units, không thay consistency.

Không giải quyết stale GSI bằng cách cấp IAM admin, tăng SDK read timeout hay retry quá gấp.

### 5.3. DynamoDB Streams

Streams là change stream cho CDC/Lambda, không phải API tra giá trị item mới nhất. Dữ liệu stream được propagate bất đồng bộ, không hỗ trợ strongly consistent read. Hệ thống theo dõi thay đổi cần xử lý event delivery, ordering, duplicate/retry theo semantics của Streams/Lambda.

## 6. Các API đọc và mức consistency

### 6.1. `GetItem`

Chỉ định **đầy đủ primary key**, hỗ trợ `ConsistentRead=true`:

~~~json
{
  "TableName": "Orders",
  "Key": {
    "PK": {"S": "ORDER#101"},
    "SK": {"S": "META"}
  },
  "ConsistentRead": true,
  "ReturnConsumedCapacity": "TOTAL"
}
~~~

`ReturnConsumedCapacity` giúp quan sát capacity consumed. Response không có `Item` nghĩa là không thấy item trong yêu cầu, nhưng **không có item không đồng nghĩa “không tốn read units”**.

### 6.2. `Query`

Cần partition key equality và có thể có sort key condition. Query ở **base table/LSI** có thể strong; **GSI** chỉ eventual.

~~~json
{
  "TableName": "Orders",
  "KeyConditionExpression": "#pk = :pk",
  "ExpressionAttributeNames": {
    "#pk": "PK"
  },
  "ExpressionAttributeValues": {
    ":pk": {"S": "CUSTOMER#7"}
  },
  "ConsistentRead": true,
  "ReturnConsumedCapacity": "INDEXES"
}
~~~

`Query` có thể trả `LastEvaluatedKey`; nếu có, cần lấy page tiếp bằng `ExclusiveStartKey`.

### 6.3. `Scan`

Scan đọc nhiều items trên table/index và có thể rất tốn capacity. `ConsistentRead=true` chỉ khả dụng ở target hỗ trợ. **Parallel Scan** có thể tăng tốc migration nhưng tăng capacity pressure, không tạo snapshot isolation.

### 6.4. `BatchGetItem`

Cho phép đọc nhiều keys; với request mỗi table có thể đặt `ConsistentRead=true`. **Không bảo đảm thứ tự output khớp danh sách request**. `UnprocessedKeys` có thể xuất hiện khi bị throttling/size limits, cần retry với exponential backoff. Kể cả tất cả items đều strong, BatchGet vẫn **không phải atomic snapshot nhiều items**.

### 6.5. `TransactGetItems`

Đọc atomically nhiều items từ tables trong **cùng account và Region**, tối đa **100 item Get operations**, tổng response items tối đa **4 MiB**. Không đọc GSI/LSI qua index target. Có **serializable isolation** theo transaction semantics, nhưng có thể conflict và fail.

Với item đến 4 KiB, transactional read tiêu thụ **2 read units** (gấp đôi strong, bốn lần eventual). MREC transactions chỉ atomic trong Region nguồn; **MRSC global tables không hỗ trợ `TransactGetItems` hoặc `TransactWriteItems`**.

## 7. Tính RCU/RRU theo khối 4 KiB

- **Provisioned mode:** `1 RCU` hỗ trợ **1 strong read/giây** hoặc **2 eventual reads/giây** cho item đến `4 KiB`.
- **On-demand mode:** `1 RRU` tương ứng một strong read đến 4 KiB; eventual tốn **0,5 RRU**, transactional **2 RRUs**.
- `4 KiB = 4096 bytes`. Item lớn hơn sẽ làm tròn lên theo số khối 4 KiB.

Với một item kích thước `s` bytes:

\[
b=\left\lceil\frac{s}{4096}\right\rceil,\qquad
U_{\mathrm{strong}}=b,\qquad
U_{\mathrm{eventual}}=\frac{b}{2},\qquad
U_{\mathrm{transactional}}=2b
\]

Đây là mô hình tính cơ bản cho item reads; Query/Scan không có kết quả vẫn có thể có **minimum read charge** và mỗi operation có các điều kiện riêng. Chi phí không chỉ là item bytes **trả về sau filter**.

| Item size | Khối 4 KiB | Strong | Eventual | Transactional |
|---|---:|---:|---:|---:|
| 1 KiB | 1 | 1 | 0,5 | 2 |
| 4 KiB | 1 | 1 | 0,5 | 2 |
| 4 KiB + 1 byte | 2 | 2 | 1 | 4 |
| 8 KiB | 2 | 2 | 1 | 4 |
| 20 KiB | 5 | 5 | 2,5 | 10 |

### 7.1. Ví dụ 100 reads/giây

Với items 3 KiB và 100 `GetItem` mỗi giây:

~~~text
100 eventual reads × 0.5 unit =  50 read units/giây
100 strong reads   × 1   unit = 100 read units/giây
100 transactional  × 2   unit = 200 read units/giây
~~~

Nếu size tăng thành 5 KiB, mỗi item chiếm 2 khối:

~~~text
100 eventual reads × 1 unit = 100 units/giây
100 strong reads   × 2 unit = 200 units/giây
100 transactional  × 4 unit = 400 units/giây
~~~

Đây là capacity math, **chưa phải giá USD**: giá và phí data transfer/storage, global replication, backups tùy Region/table settings.

### 7.2. Tiết kiệm khi chỉ strong tại nơi cần

~~~text
1000 reads/s, item <= 4 KiB
950 catalog/profile eventual → 950 × 0,5 = 475 units/s
 50 checkout strong         →  50 × 1   =  50 units/s
Tổng                                      525 units/s

Nếu tất cả strong                       1000 units/s
~~~

Đây là ví dụ lý thuyết. Nếu 5% traffic là hot key còn 95% rải đều, throttling/hot partition và latency vẫn cần phân tích riêng.

## 8. Consistency không phải latency hay throughput

| Mục tiêu | Cách chọn | Rủi ro/đánh đổi |
|---|---|---|
| Low-latency catalog | Eventual/cache | Có thể stale |
| Read-after-write trên một item | Strong GetItem | Đọc capacity lớn hơn |
| Atomic nhiều items | `TransactGetItems` | Giao dịch và conflict/cost |
| Truy vấn theo thuộc tính thứ cấp | GSI eventual | Index propagation lag |
| Multi-Region với writes nhanh | MREC | Cross-Region stale, last-writer-wins |
| Multi-Region strict freshness | MRSC strong | Cross-Region coordination và feature limits |
| Rất nhiều repeated reads | DAX | Cache invalidation, cluster fees |

Strong reads tiêu thụ gấp đôi read units so với eventual với cùng item sizes; **không có quy tắc latency nhất thiết đúng bằng 2×**. Đo P50/P95/P99 từ client và `SuccessfulRequestLatency` tại AWS, kiểm tra SDK retry và network path.

### 8.1. Hot partition vẫn tồn tại

Read consistency không cứu được một partition key rất nóng. Nếu 90% reads dồn vào `PK=GLOBAL`, có thể throttling dù table tổng còn capacity. Cân nhắc redesign keys, caching, distributed reads và sharding có chủ đích. Với throttling, SDK backoff/jitter có thể tăng latency; phân biệt nó với eventual staleness.

## 9. Chọn consistency theo nghiệp vụ

| Tình huống | Khuyến nghị |
|---|---|
| Product catalog, recommendation | Eventual/GSI/cache |
| User vừa cập nhật profile, reload ngay | Strong base-table GetItem hoặc phản ánh write response |
| Dashboard gần thời gian thực | Eventual, ghi rõ staleness tolerance |
| Checkout kiểm tra stock | Conditional write; strong read chỉ hỗ trợ UI |
| Coupon chỉ dùng một lần | Conditional write/transaction |
| Lọc orders theo status qua GSI | Eventual và UX xử lý index lag |
| Payment ledger | Idempotency + conditional write/transaction khi được hỗ trợ |
| Báo cáo snapshot tại một thời điểm | Export/backup/event watermark, không dựa strong Scan |
| Read khác Region ngay sau write | MRSC strong hoặc định tuyến đọc về Region đã ghi |

### 9.1. Read-your-write UX không nhất thiết cần read lần nữa

`UpdateItem` có `ReturnValues=ALL_NEW` để trả item mới sau update. UI có thể render từ response, giảm một read API call. Nếu client dùng `GetItem` sau đó, bật strong khi business cần thấy write và đọc base table. Nếu tra qua GSI, index vẫn có lag; UI có thể giữ item vừa ghi vào local state cho tới khi GSI hội tụ.

### 9.2. Monotonic reads theo session

Ứng dụng có thể giữ `lastSeenVersion` trong session; nếu một eventual read trả version thấp hơn đã hiển thị, đừng overwrite UI. Có thể retry có giới hạn hoặc fallback strong base-table read. Đây là application-level session guarantee, không phải một consistency mode riêng mà DynamoDB tự bật.

## 10. GSI, LSI và thiết kế access pattern

Một table có thể lưu:

~~~text
PK = ORDER#101
SK = META
status = PAID
customerId = CUSTOMER#7
updatedAt = 2026-11-20T09:30:00Z
~~~

GSI phục vụ Query theo customer:

~~~text
GSI1PK = CUSTOMER#7
GSI1SK = UPDATED#2026-11-20T09:30:00Z#ORDER#101
~~~

Ngay sau base-table write, GSI entry có thể chưa cập nhật. **Không** bật strong GSI. Nếu cần read-your-write theo customer, các chiến lược:

1. Nếu biết `ORDER#101`, đọc base table bằng `GetItem ConsistentRead=true`.
2. Trả item vừa ghi trong response, UI giữ trong danh sách tạm.
3. Thiết kế base table item dạng `PK=CUSTOMER#7`, `SK=ORDER#101` để Query strong nếu access pattern quan trọng hơn.
4. Xem xét LSI khi partition key đã phù hợp và item collection không vượt 10 GiB.
5. Với nhiều projections cần atomic update, cân nhắc denormalized records + `TransactWriteItems` trong một Region (không MRSC).
6. Chấp nhận eventual với UI “đang đồng bộ” và retry có deadline nếu chỉ cần độ trễ ngắn.

### 10.1. `FilterExpression` và `ProjectionExpression` không giảm capacity như tưởng

`Query` đọc items thỏa KeyConditionExpression **trước**, rồi mới chạy FilterExpression. Bất kể filter trả 5 hay 500 items, read units dựa vào dữ liệu **được đọc**, không chỉ output. ProjectionExpression giảm response payload/network nhưng không làm giảm item size DynamoDB đã đọc từ base table.

Ví dụ đọc 200 KiB items rồi lọc còn 4 KiB: vẫn trả read units theo **dữ liệu 200 KiB đã đọc**, không theo 4 KiB. GSI projections có thể làm index entry nhỏ hơn, nhưng đó là **index item size** khác, không phải filter giảm capacity.

### 10.2. Pagination và ảnh chụp trạng thái

- Một Query/Scan request đọc tối đa **1 MiB dữ liệu trước filter**; nếu `LastEvaluatedKey` có mặt phải paginate.
- `Limit=10` nghĩa là đọc tối đa 10 items trước filter, không đảm bảo trả 10 items sau filter.
- Một page có thể trả **0 items và LastEvaluatedKey** khi tất cả items trong page bị filter.
- Strong Query/Scan không bảo đảm một **consistent snapshot** giữa nhiều pages trong lúc writes đang diễn ra.

Đừng nhầm `Count=0` từ Query GSI với chứng minh item không tồn tại; có thể do propagation, key expression, filter, hoặc chưa đọc hết pages.

## 11. Global Tables: MREC và MRSC trên AWS hiện hành

**DynamoDB Global Tables** nhân bản dữ liệu giữa các AWS Regions. Hiện có **hai consistency modes**: **Multi-Region Eventual Consistency (MREC)** (mặc định) và **Multi-Region Strong Consistency (MRSC)**. MRSC được AWS đưa vào sử dụng từ năm 2025; không còn đúng khi nói “mọi Global Tables đều chỉ hỗ trợ eventual xuyên Regions”.

### 11.1. MREC: replication bất đồng bộ

~~~mermaid
sequenceDiagram
    participant API as Client Region A
    participant A as Replica Region A
    participant B as Replica Region B
    participant USER as Client Region B
    API->>A: UpdateItem status=PAID
    A-->>API: Success
    USER->>B: GetItem ConsistentRead=true
    B-->>USER: Có thể vẫn PENDING
    A-->>B: Async replication
    USER->>B: GetItem ConsistentRead=true
    B-->>USER: PAID sau khi replication đến
~~~

Với MREC, `ConsistentRead=true` ở Region B chỉ đọc latest state **đã có ở B**. Nó không bắt B “nhìn thấy” một write thành công ở A **trước khi replication tới B**. Nếu hai Regions cùng cập nhật một item, MREC áp **last-writer-wins**, có nguy cơ làm mất business update. Cần thiết kế **single-writer per aggregate**, region ownership hoặc logic xử lý xung đột.

`TransactWriteItems` trong Region A là atomic ở A; replica B có thể tạm thấy vài items đã replicate và vài items chưa. **MREC không có cross-Region atomic transaction**.

### 11.2. MRSC: strong consistency xuyên Regions

MRSC đồng bộ update tới **ít nhất một Region khác trước khi trả write success**; strong read tại **bất kỳ replica Region** nào phản ánh latest successful write của item, hỗ trợ **RPO=0** theo mô hình dịch vụ.

MRSC đòi **chính xác ba Regions**: hoặc ba replicas, hoặc hai replicas + một **witness**. Witness lưu thông tin phục vụ đồng bộ/quorum nhưng **không cho application đọc/ghi items**. AWS có danh sách Region MRSC-supported, bao gồm Asia Pacific (Singapore) tại thời điểm tài liệu được đối chiếu; không tự giả định mọi Region hỗ trợ.

| Tiêu chí | MREC (mặc định) | MRSC |
|---|---|---|
| Replication | Asynchronous | Synchronous tới tối thiểu một Region khác |
| Cross-Region strong read | Không, nếu write chưa tới replica | Có, với `ConsistentRead` trên replica |
| Concurrent writes | Last-writer-wins | Có thể `ReplicatedWriteConflictException` |
| Write/strong-read latency | Thường thấp hơn | Cross-Region coordination/RTT, thường cao hơn |
| Transactions | Chỉ atomic trong Region | **Không hỗ trợ transaction APIs** |
| LSI | Theo table design | **Không hỗ trợ** |
| GSI | Eventual | **Vẫn eventual** |
| TTL | Có | **Không hỗ trợ** |
| `ReplicationLatency` metric | Có | **Không phát metric này** |
| Topology | Có thể thêm/bớt replica theo quy tắc | Đúng 3 Regions, hạn chế sửa |
| Đổi mode sau khi tạo | Không hỗ trợ chuyển trực tiếp | Không hỗ trợ chuyển trực tiếp |

### 11.3. Những đánh đổi MRSC khó bỏ qua

- GSI **vẫn eventual**, dù base replica có global strong reads.
- MRSC **không hỗ trợ `TransactGetItems` và `TransactWriteItems`**.
- MRSC **không có TTL hoặc LSI**.
- Write và strongly consistent reads có thể phải chờ liên vùng → ảnh hưởng P99 latency.
- Phải chọn mode/topology lúc tạo. Không thể đổi Global Table từ MREC sang MRSC chỉ bằng update flag; chuyển một table đã có dữ liệu sang MRSC cũng bị hạn chế, cần migration strategy.
- Không có một DynamoDB global endpoint tự route; clients vẫn gọi **regional endpoints**. Failover application/API và dependencies phải được thiết kế riêng.

Nếu business chỉ ở một Region hoặc cho phép stale cross-Region, MREC có thể đơn giản và kinh tế hơn. Chọn MRSC khi cần cross-Region strong item reads và RPO zero, đã chấp nhận tradeoffs/limits.

## 12. DAX và read consistency: cache không biến dữ liệu thành strong

**DynamoDB Accelerator (DAX)** là managed in-memory cache dành cho các truy vấn đọc lặp lại, thường giúp giảm latency và DynamoDB read units khi eventual cache hit.

~~~mermaid
flowchart LR
    APP["Java application"] --> DAX["DAX cluster: item/query cache"]
    DAX -->|"Cache hit eventual"| APP
    DAX -->|"Cache miss / strong pass-through"| DB["DynamoDB"]
    WRITER["Direct DynamoDB writer"] --> DB
~~~

### 12.1. DAX item cache và query cache

- `GetItem` eventual: DAX tìm item cache; nếu hit, trả cached result; nếu miss, đọc eventual từ DynamoDB rồi cache.
- DAX cluster nodes đồng bộ cache bất đồng bộ, vì thế có thể có chênh lệch ngắn giữa các nodes.
- Write qua DAX đi qua DynamoDB (write-through), làm mới item cache theo behavior DAX.
- Write trực tiếp tới DynamoDB **bỏ qua DAX** có thể khiến cached item stale tới TTL/eviction.
- `Query`/`Scan` dùng **query cache**, có thể stale ngay cả sau khi item cache được update; thay đổi item **không tự invalidate query cache**.

### 12.2. Strong/transactional requests qua DAX

Với `ConsistentRead=true`, DAX **pass-through** `GetItem`/`BatchGetItem`/`Query`/`Scan` sang DynamoDB và **không cache kết quả strong**. `TransactGetItems` cũng pass-through. Nếu phần lớn workloads bắt buộc strong, DAX không tạo hit-rate lợi ích tương đương eventual read, trong khi còn phí cluster.

### 12.3. Khi nào đáng dùng DAX?

Phù hợp read-heavy hot keys, nhiều repeated eventual reads, có thể chịu stale TTL và có cache hit ratio cao. Không nên dùng DAX chỉ để che hot partition, SDK network sai Region hoặc read API đang bị retry/throttle. Đo actual cache-hit, memory, latency và DynamoDB read consumption.

## 13. Java AWS SDK for Java 2.x: một key, hai mức read

Ví dụ Java 21, dependency `software.amazon.awssdk:dynamodb` với AWS SDK BOM. Dùng default credentials provider chain (IAM role Lambda/ECS/EC2 hoặc profile local), không hardcode credentials.

~~~java
import java.util.Map;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.GetItemRequest;
import software.amazon.awssdk.services.dynamodb.model.GetItemResponse;
import software.amazon.awssdk.services.dynamodb.model.ReturnConsumedCapacity;

public final class ReadConsistencyExample {
    public static void main(String[] args) {
        Map<String, AttributeValue> key = Map.of(
            "PK", AttributeValue.fromS("ORDER#101"),
            "SK", AttributeValue.fromS("META")
        );

        try (DynamoDbClient db = DynamoDbClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build()) {
            GetItemResponse eventual = db.getItem(GetItemRequest.builder()
                    .tableName("Orders")
                    .key(key)
                    .consistentRead(false)
                    .returnConsumedCapacity(ReturnConsumedCapacity.TOTAL)
                    .build());

            GetItemResponse strong = db.getItem(GetItemRequest.builder()
                    .tableName("Orders")
                    .key(key)
                    .consistentRead(true)
                    .returnConsumedCapacity(ReturnConsumedCapacity.TOTAL)
                    .build());

            // Không log toàn bộ item chứa PII trên production.
            System.out.println("Eventual hasItem=" + eventual.hasItem());
            System.out.println("Strong hasItem=" + strong.hasItem());
            System.out.println("Eventual units=" +
                    eventual.consumedCapacity().capacityUnits());
            System.out.println("Strong units=" +
                    strong.consumedCapacity().capacityUnits());
        }
    }
}
~~~

Code chỉ **đọc** DynamoDB (có tiêu thụ capacity và cần `dynamodb:GetItem`). `Orders` và keys phải tồn tại. Hai reads diễn ra ở **hai thời điểm khác nhau**; nếu có concurrent writers, so sánh response một lần không chứng minh strong/cost “nhanh hơn” hay “đúng hơn” cho mọi trường hợp. Benchmark cần repeat và theo dõi business version.

`ReturnConsumedCapacity.TOTAL` trả số capacity units dùng trong một API call. Với `Query` đọc indexes, `ReturnConsumedCapacity.INDEXES` cung cấp breakdown phù hợp; không ghi raw request/response có dữ liệu nhạy cảm vào logs.

## 14. Java Query: base table strong, GSI eventual và pagination

### 14.1. Strong Query trên base table

~~~java
import java.util.Map;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.QueryRequest;
import software.amazon.awssdk.services.dynamodb.model.QueryResponse;
import software.amazon.awssdk.services.dynamodb.model.ReturnConsumedCapacity;

public final class StrongQueryPager {
    public static void readPages(DynamoDbClient db, String partitionValue) {
        Map<String, AttributeValue> cursor = null;
        int pageCount = 0;

        do {
            QueryRequest.Builder request = QueryRequest.builder()
                    .tableName("Orders")
                    .keyConditionExpression("#pk = :pk")
                    .expressionAttributeNames(Map.of("#pk", "PK"))
                    .expressionAttributeValues(Map.of(
                            ":pk", AttributeValue.fromS(partitionValue)))
                    .consistentRead(true)
                    .returnConsumedCapacity(ReturnConsumedCapacity.TOTAL)
                    .limit(100);

            if (cursor != null && !cursor.isEmpty()) {
                request.exclusiveStartKey(cursor);
            }

            QueryResponse page = db.query(request.build());
            System.out.println("Page " + (++pageCount)
                    + ": count=" + page.count()
                    + " scanned=" + page.scannedCount());

            // Xử lý page.items() theo business schema; không log PII.
            cursor = page.lastEvaluatedKey();
        } while (cursor != null && !cursor.isEmpty());
    }
}
~~~

`Limit=100` là **số items xử lý ở mỗi page trước FilterExpression**, không đảm bảo 100 returned. `LastEvaluatedKey` thể hiện còn dữ liệu để tiếp tục. Trong lúc paginate, các writes vẫn diễn ra và strong consistency không cho snapshot toàn bộ pages.

### 14.2. Eventual Query trên GSI

~~~java
import java.util.Map;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.QueryRequest;
import software.amazon.awssdk.services.dynamodb.model.QueryResponse;

public final class CustomerOrdersGsi {
    public static QueryResponse query(DynamoDbClient db) {
        return db.query(QueryRequest.builder()
                .tableName("Orders")
                .indexName("GSI1")
                .keyConditionExpression("#g = :v")
                .expressionAttributeNames(Map.of("#g", "GSI1PK"))
                .expressionAttributeValues(Map.of(
                        ":v", AttributeValue.fromS("CUSTOMER#7")))
                // GSI không hỗ trợ strong reads.
                .consistentRead(false)
                .build());
    }
}
~~~

**Không sửa thành `.consistentRead(true)`:** DynamoDB sẽ reject vì consistency mode không hỗ trợ trên GSI. Nếu index query thiếu dữ liệu vừa ghi, dùng base table read theo known key hoặc session UX strategy, không busy-loop GSI không giới hạn.

## 15. Đảm bảo correctness khi có concurrent writes

Một `GetItem` strong trước `UpdateItem` vẫn có race condition. Dùng **atomic conditional write** trực tiếp khi cập nhật số lượng tồn kho.

~~~java
import java.util.Map;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.ConditionalCheckFailedException;
import software.amazon.awssdk.services.dynamodb.model.UpdateItemRequest;

public final class InventoryUpdater {
    public static boolean reserveOne(DynamoDbClient db) {
        try {
            db.updateItem(UpdateItemRequest.builder()
                    .tableName("Inventory")
                    .key(Map.of(
                            "PK", AttributeValue.fromS("SKU#7"),
                            "SK", AttributeValue.fromS("STOCK")))
                    .updateExpression("SET available = available - :one")
                    .conditionExpression("available >= :one")
                    .expressionAttributeValues(Map.of(
                            ":one", AttributeValue.fromN("1")))
                    .build());
            return true;
        } catch (ConditionalCheckFailedException insufficient) {
            return false;
        }
    }
}
~~~

**Đây là write có tác động thật** nếu được gọi với IAM/table hợp lệ, có thể thay đổi inventory và phát sinh phí. Không chạy trên production để thử học. Điều kiện bảo vệ `available >=1` trước concurrent writes, nhưng còn một lỗ hổng khác: cùng client retry sau mất ACK có thể trừ lần thứ hai nếu stock vẫn đủ. Cần thêm **idempotency key theo order** và operation record/transaction khi nghiệp vụ yêu cầu.

### 15.1. Optimistic locking

Một application có field `version`. Update chỉ thành công khi version vẫn như kỳ vọng:

~~~text
ConditionExpression: #v = :expected
UpdateExpression: SET #status = :newStatus, #v = :next
~~~

Nếu worker A và B đều đọc version 7, chỉ một người update version 8 với điều kiện version 7 thành công. Worker còn lại nhận `ConditionalCheckFailedException` và phải resolve conflict; không retry vô hạn bằng state cũ.

### 15.2. CAS vs strong read

| Mục tiêu | Công cụ |
|---|---|
| Hiển thị bản ghi vừa ghi | Strong `GetItem` hoặc write response |
| Không cấp hai coupon cùng một key | Conditional `PutItem` với `attribute_not_exists(PK)` |
| Không oversell stock | `UpdateItem` condition trên stock/version |
| Đổi đồng thời hai items atomically | `TransactWriteItems` trong phạm vi hỗ trợ |
| Đọc nhiều items cùng transaction snapshot | `TransactGetItems` trên bảng hỗ trợ |
| Cross-Region strong single-item read | MRSC strong; không dùng transaction APIs |

Chọn theo invariant, không theo một nhãn “data is important”.

## 16. TransactGetItems và transaction isolation

### 16.1. API request JSON

Một trang kiểm tra order và payment ở hai items:

~~~json
{
  "TransactItems": [
    {
      "Get": {
        "TableName": "Orders",
        "Key": {
          "PK": {"S": "ORDER#101"},
          "SK": {"S": "META"}
        }
      }
    },
    {
      "Get": {
        "TableName": "Orders",
        "Key": {
          "PK": {"S": "ORDER#101"},
          "SK": {"S": "PAYMENT"}
        }
      }
    }
  ],
  "ReturnConsumedCapacity": "TOTAL"
}
~~~

`TransactGetItems` đọc atomically tối đa 100 items/tổng 4 MiB, trong cùng account và Region, **không đọc index trực tiếp**. Đây là một **read operation** nhưng dùng khoảng **hai RCU/RRU cho item đến 4 KiB**, có thể thất bại do concurrent transaction conflict hoặc capacity.

### 16.2. Isolation scope

DynamoDB transactions có serializable isolation giữa transactional operations và những item-level write/get operations được AWS tài liệu hóa. Tuy nhiên `Query`/`Scan` hay `BatchGetItem` như một nhóm **không** trở thành serializable snapshot chỉ vì các items nằm trong table có transaction.

Với Global Tables MREC, transaction atomic trong Region gọi, không atomic xuyên Regions sau replication. Với **MRSC**, transaction APIs **không được hỗ trợ**. Nếu thiết kế đòi ACID multi-item qua Regions, phải xem lại architecture/data ownership.

### 16.3. ClientRequestToken và idempotency

`TransactWriteItems` có `ClientRequestToken` để chống retry cùng transaction trong cửa sổ được DynamoDB hỗ trợ, nhưng business operation ID vẫn cần giữ lâu hơn nếu có delayed retries, SQS redelivery hoặc manual recovery. Nếu request timeout sau write commit, outcome unknown; đừng tự tăng operation key cho lần retry kế tiếp.

## 17. Các nguồn stale data khác: TTL, Streams và cache

### 17.1. TTL không xóa đúng từng giây

DynamoDB TTL cleanup là **bất đồng bộ**. Một item có `expiresAt` đã qua vẫn có thể tồn tại tới khi TTL process xóa. **Strong GetItem có thể trả item đã hết hạn mà chưa bị xóa**. Business logic phải kiểm tra `expiresAt <= now` tại lúc quyết định, kết hợp condition nếu cần. **Global Tables MRSC không hỗ trợ TTL**.

### 17.2. Streams và downstream projections

Một Lambda đọc DynamoDB Streams rồi cập nhật Elasticsearch/OpenSearch, S3 hay cache là **event-driven asynchronous process**. Base table strong read không làm những projections đó cập nhật ngay. Cần idempotent consumer, retry/DLQ, `IteratorAge` monitoring và business correlation ID.

### 17.3. Nhiều lớp stale độc lập

~~~text
Write to base DynamoDB table (success)
  ├─ Base table eventual read: có thể stale ngắn
  ├─ GSI replication: eventual và lag riêng
  ├─ DAX item cache: TTL/eviction, nhất là direct writes
  ├─ DAX query cache: không invalidate ngay theo writes
  ├─ DynamoDB Streams → Lambda projection: async processing
  └─ Global Tables MREC: async cross-Region propagation
~~~

Không thể sửa tất cả bằng một cờ `ConsistentRead=true`. Tìm đúng **đường đọc** và nguồn staleness trước khi thay kiến trúc.

## 18. IAM, VPC Endpoint và Region đúng

### 18.1. IAM quyền tối thiểu

Ví dụ policy cho application đọc table và index:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadOrders",
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:Query",
        "dynamodb:BatchGetItem"
      ],
      "Resource": [
        "arn:aws:dynamodb:ap-southeast-1:111122223333:table/Orders",
        "arn:aws:dynamodb:ap-southeast-1:111122223333:table/Orders/index/GSI1"
      ]
    }
  ]
}
~~~

Các ARNs là placeholders. Thêm `dynamodb:Scan` hay quyền transaction khi thật cần; hạn chế actions và table/index resources, không cấp `dynamodb:*`. Có thể dùng IAM conditions `dynamodb:LeadingKeys`/`dynamodb:Attributes` cho tenant isolation khi business policy phù hợp. **IAM không quyết định eventual vs strong**; đó là read request/API/data source.

### 18.2. Gateway endpoint trong VPC

Worker ECS/Lambda trong private subnet có thể gọi DynamoDB cùng Region qua **Gateway VPC Endpoint**:

~~~text
com.amazonaws.ap-southeast-1.dynamodb
~~~

Gateway endpoint gắn với route tables của các private subnets và endpoint policy; thường **không có phí endpoint-hour/data processing** cho gateway endpoint chuẩn, nhưng DynamoDB read units, storage và data transfer liên quan vẫn có chi phí.

**DynamoDB cũng hỗ trợ Interface VPC Endpoint (AWS PrivateLink)**, phù hợp khi client ở on-premises, kết nối qua VPC peering/Transit Gateway hoặc cần endpoint private IP theo kiến trúc được hỗ trợ. Interface endpoint có Security Group/Private DNS và **phí endpoint-hour/data processing**; khác với Gateway Endpoint miễn phí bổ sung cho use case nội VPC/cùng Region. Cả hai loại endpoint đều **không thay đổi read consistency semantics** của DynamoDB.

Với application `AccessDenied`, kiểm tra execution role, table policy/KMS/endpoint policy. Với `TimeoutException`, kiểm tra VPC route table, DNS, SDK region, SG/NACL theo kiến trúc. Nếu response có stale value, đó có thể là **consistency semantics**, không nhất thiết lỗi mạng.

### 18.3. Sai Region có thể giống stale read

DynamoDbClient dùng **regional endpoint**. Nếu application ở `ap-southeast-1` vô tình trỏ `us-east-1`, có thể gọi **table khác cùng tên** hoặc một replica MREC chưa cập nhật, đồng thời tăng latency. Ghi vào logs metadata như account, region, table ARN/index name, requestId, item business version — **không ghi credentials/PII**.

## 19. Benchmark eventual vs strong và MRSC một cách có ý nghĩa

Một thử nghiệm nghiêm túc phải cố định:

1. Cùng table, keys, item size và phân bố partition keys.
2. Cùng Region/VPC/SDK HTTP settings; reuse clients/connections.
3. Có warm-up và đủ mẫu thay vì so **một** GetItem.
4. Đo **client end-to-end P50/P95/P99 latency**, AWS service latency, retries, throttle events.
5. Ghi `ReturnConsumedCapacity`, item size, read mode, index, table billing mode.
6. Với consistency test, theo dõi `version`/commit timestamp để tính stale rate; không dựa vào “có vẻ nhanh”.
7. Với DAX, tách cache-hit và cache-miss latency, TTL, query cache và direct writes.
8. Với MREC, đo `ReplicationLatency`/business lag giữa Regions.
9. Với MRSC, đo writes/strong reads ở các Regions khác nhau và cross-Region failover.
10. Test trong sandbox, giới hạn request rate và chi phí; không làm production hot keys bị throttled.

### 19.1. Template ghi kết quả

| Metric | Table eventual | Table strong | GSI eventual | DAX eventual | MRSC strong |
|---|---:|---:|---:|---:|---:|
| P50/P95/P99 latency | Đo | Đo | Đo | Đo | Đo |
| Capacity units/request | Đo | Đo | Đo index | Tách cache hit | Đo |
| Stale reads / version lag | Đo | Kỳ vọng không stale trong scope | Đo | Đo | Kỳ vọng không stale với successful writes |
| SDK retries/throttles | Đo | Đo | Đo | Đo | Đo |
| Infra/mode/Region | Ghi rõ | Ghi rõ | Ghi rõ | DAX node/cache | Global topology |

Không bịa số đo latency hoặc giá USD vì chưa có workload thực nghiệm. Kết luận chỉ dựa trên các metrics quan sát được từ môi trường test.

## 20. Quan sát CloudWatch và kiểm soát vận hành

| Nguồn | Metric / signal | Diễn giải |
|---|---|---|
| DynamoDB | `ConsumedReadCapacityUnits` | Tổng read units sử dụng |
| DynamoDB | `ProvisionedReadCapacityUnits` | Read capacity được provisioned |
| DynamoDB | `ReadThrottleEvents` / `ThrottledRequests` | Yêu cầu bị throttle, có thể tăng latency |
| DynamoDB | `SuccessfulRequestLatency` | Service-side latency theo operation |
| DynamoDB | `SystemErrors` / `UserErrors` | Phân biệt lỗi service/client |
| DynamoDB | `TransactionConflict` | Transaction contention |
| Global Tables MREC | `ReplicationLatency` | Cross-Region replication delay |
| Global Tables MRSC | Không có `ReplicationLatency` theo MREC semantics | Dùng latency/conflict/service metrics phù hợp |
| DAX | Cache hits/misses, evictions, CPU | Cache value thực tế |
| Application | P99/stale-read-rate/version lag, retry attempts | UX và business consistency |
| Event processor | Lambda `IteratorAge`, DLQ count | Downstream projections stale |

### 20.1. Cách phân biệt sự cố

- **Stale read không exception:** kiểm tra `ConsistentRead`, table vs GSI, DAX cache, Global Tables mode/Region.
- **`ValidationException` trên GSI strong:** remove `ConsistentRead=true` và thiết kế access pattern khác.
- **Throttling:** đọc CloudWatch, SDK retries, hot partition và capacity/burst.
- **Conflict/ConditionalCheckFailed:** business concurrency, version mismatch, không phải replication lag.
- **TransactionCanceledException:** xem cancellation reasons, optimistic locks và capacity.
- **`ResourceNotFoundException`:** sai Region/table/index ARN hoặc table chưa ACTIVE.
- **Network timeout/AccessDenied:** VPC endpoint/IAM/endpoint policy, khác với read consistency.

## 21. AWS CLI chỉ đọc: kiểm tra table, indexes và consistency

Các lệnh trong mục này dùng AWS CLI v2, profile `dev`, Region `ap-southeast-1` và table `Orders` làm ví dụ. Chúng **không thay đổi items**, nhưng `GetItem`/`Query`/`TransactGetItems` vẫn **tiêu thụ read capacity và có thể phát sinh phí**; chỉ chạy trong account được cấp quyền và với workload giới hạn.

### 21.1. Identity, Region và table metadata

~~~bash
aws sts get-caller-identity \
  --profile dev \
  --query '{Account:Account,Arn:Arn}' \
  --output json

aws dynamodb list-tables \
  --profile dev \
  --region ap-southeast-1 \
  --output json

aws dynamodb describe-table \
  --table-name Orders \
  --profile dev \
  --region ap-southeast-1 \
  --query 'Table.{Name:TableName,Status:TableStatus,KeySchema:KeySchema,Mode:BillingModeSummary.BillingMode,GlobalConsistency:MultiRegionConsistency,GSIs:GlobalSecondaryIndexes[].IndexName,LSIs:LocalSecondaryIndexes[].IndexName}' \
  --output json
~~~

`MultiRegionConsistency` có thể là `EVENTUAL` (MREC), `STRONG` (MRSC) ở Global Table; một table single-Region có thể không có field đó. `GlobalSecondaryIndexes` và `LocalSecondaryIndexes` giúp nhận diện đường Query được hỗ trợ mạnh/yếu.

**Không đoán mode MRSC chỉ vì thấy `Replicas`:** kiểm tra metadata consistency mode và topologies. Nếu table vừa tạo, `DescribeTable` có thể chưa nhìn thấy metadata ngay lập tức; chờ table ACTIVE thay vì thao tác ngẫu nhiên.

### 21.2. Eventual GetItem (mặc định)

~~~bash
aws dynamodb get-item \
  --table-name Orders \
  --key '{"PK":{"S":"ORDER#101"},"SK":{"S":"META"}}' \
  --return-consumed-capacity TOTAL \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

Lệnh này dùng default **eventual consistency**. Nó không tự sửa dữ liệu nếu item chưa thấy.

### 21.3. Strong GetItem trên base table

~~~bash
aws dynamodb get-item \
  --table-name Orders \
  --key '{"PK":{"S":"ORDER#101"},"SK":{"S":"META"}}' \
  --consistent-read \
  --return-consumed-capacity TOTAL \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

Cờ `--consistent-read` áp dụng cho table. Cú pháp JSON được quote theo **Bash**; PowerShell yêu cầu escaping/quoting khác, có thể dùng `file://key.json` khi làm việc trong môi trường Windows. Đừng lưu credentials hoặc business PII trong các file mẫu.

### 21.4. Strong Query trên base table

~~~bash
aws dynamodb query \
  --table-name Orders \
  --key-condition-expression '#pk = :pk' \
  --expression-attribute-names '{"#pk":"PK"}' \
  --expression-attribute-values '{":pk":{"S":"CUSTOMER#7"}}' \
  --consistent-read \
  --return-consumed-capacity TOTAL \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

Cần có access pattern/query key thật. Nếu table có PK `ORDER#id` chứ không phải `CUSTOMER#id`, Query sẽ không trả nhóm orders theo customer; **đó là data modeling**, không phải read consistency bug. CLI có thể tự paginate nếu có `LastEvaluatedKey`, còn code SDK nên xử lý pagination rõ ràng.

### 21.5. GSI Query: không được dùng strong

~~~bash
aws dynamodb query \
  --table-name Orders \
  --index-name GSI1 \
  --key-condition-expression '#g = :v' \
  --expression-attribute-names '{"#g":"GSI1PK"}' \
  --expression-attribute-values '{":v":{"S":"CUSTOMER#7"}}' \
  --return-consumed-capacity INDEXES \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

**Không thêm `--consistent-read`** vào GSI query. DynamoDB không hỗ trợ strong GSI read; nếu cố bật sẽ báo ValidationException. Nếu cần lấy item mới nhất khi biết base key, đọc bảng gốc với `get-item --consistent-read`.

### 21.6. Transactional read: có chi phí cao hơn

~~~bash
# READ-ONLY nhưng sử dụng transactional read capacity; KHÔNG dùng MRSC table.
aws dynamodb transact-get-items \
  --transact-items '[{"Get":{"TableName":"Orders","Key":{"PK":{"S":"ORDER#101"},"SK":{"S":"META"}}}},{"Get":{"TableName":"Orders","Key":{"PK":{"S":"ORDER#101"},"SK":{"S":"PAYMENT"}}}}]' \
  --return-consumed-capacity TOTAL \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

Bảng `Orders` phải tồn tại và hỗ trợ transactions; MRSC Global Table **không hỗ trợ API này**. Transaction may conflict và fail với `TransactionCanceledException`. Nếu cần kiểm tra một item đơn giản, không dùng transaction chỉ vì “nó mạnh hơn”.

### 21.7. Đo capacity nhưng không scan production

Có thể dùng `ConsumedCapacity` của từng request, CloudWatch ReadThrottleEvents/ConsumedReadCapacityUnits, và logs SDK (loại bỏ PII) để so read modes. **Không chạy `Scan --consistent-read` trên table lớn chỉ để khảo sát**: nó có thể tiêu thụ rất nhiều capacity, tăng throttling của production.

## 22. Write APIs và thử nghiệm read-after-write (có tác động)

Để kiểm chứng consistency trong sandbox, một nhóm có thể tạo item version 1 rồi update thành version 2 và đọc ngay bằng hai modes. **Các lệnh phần này thật sự ghi dữ liệu**, không được chạy trong production nếu chưa được duyệt.

~~~bash
# CHỈ SANDBOX - ghi/ghi đè một item vào DynamoDB table.
aws dynamodb put-item \
  --table-name OrdersLab \
  --item '{"PK":{"S":"ORDER#LAB101"},"SK":{"S":"META"},"status":{"S":"PENDING"},"version":{"N":"1"}}' \
  --condition-expression 'attribute_not_exists(PK)' \
  --profile dev \
  --region ap-southeast-1

# CHỈ SANDBOX - update một item có version 1.
aws dynamodb update-item \
  --table-name OrdersLab \
  --key '{"PK":{"S":"ORDER#LAB101"},"SK":{"S":"META"}}' \
  --update-expression 'SET #s = :paid, #v = :v2' \
  --condition-expression '#v = :v1' \
  --expression-attribute-names '{"#s":"status","#v":"version"}' \
  --expression-attribute-values '{":paid":{"S":"PAID"},":v1":{"N":"1"},":v2":{"N":"2"}}' \
  --return-values ALL_NEW \
  --profile dev \
  --region ap-southeast-1
~~~

Chọn bảng `OrdersLab` trong account lab, có IAM `PutItem/UpdateItem` và đủ capacity. Conditional write bảo vệ phiên bản khỏi race; `ReturnValues=ALL_NEW` trả mới nhất sau update mà không cần đọc riêng.

**Không thử “ép GSI strong” bằng cách sửa CloudFormation/IAM**: tính chất index là service-level behavior.

## 23. Decision tree: chọn consistency mà không lãng phí

~~~mermaid
flowchart TD
    A["Ứng dụng cần đọc dữ liệu"] --> B{"Cần phản ánh ngay successful write?"}
    B -->|"Không"| EV["Eventual: table/GSI/cache"]
    B -->|"Có"| C{"Truy vấn được base key hoặc LSI?"}
    C -->|"Có"| D{"Chỉ cần đọc hay quyết định update?"}
    D -->|"Chỉ đọc"| STR["Strong GetItem/Query"]
    D -->|"Update correctness"| CAS["Conditional write / transaction"]
    C -->|"Chỉ GSI"| F["Redesign base-key access; fallback/versioned UX"]
    A --> G{"Có cross-Region writes/reads?"}
    G -->|"Có"| H{"Cần global strong single-item reads/RPO0?"}
    H -->|"Không"| MREC["MREC + conflict policy"]
    H -->|"Có"| MRSC["MRSC + đánh đổi latency/features"]
~~~

### 23.1. Checklist cho review kiến trúc

1. **Đường đọc thực tế** là base table, LSI, GSI, DAX, Streams projection hay replica?
2. Business chấp nhận stale tối đa bao lâu? Có SLA/requirement rõ không?
3. Mẫu access là point read, partition query, index query, scan hay multi-item transaction?
4. Có thể dùng **write response** hoặc strong GetItem theo known key thay vì GSI Query không?
5. Invariant được kiểm soát bằng **conditional write** hay chỉ `SELECT rồi UPDATE`?
6. Có Global Tables không? MREC hay MRSC, thuộc những Regions nào?
7. Nếu MRSC, có phụ thuộc **LSI/TTL/transaction APIs** vốn không hỗ trợ không?
8. Workload item sizes, projected attributes, RCU/RRU, hot partitions và retries thế nào?
9. DAX cache hit ratio và invalidation có giúp giảm read units không?
10. IAM/VPC endpoints, cross-Region network và CloudWatch có đủ để vận hành không?

## 24. Bài lab chỉ đọc và tình huống phân tích

### 24.1. Lab 1 — Đọc metadata và consistency settings

Dùng CLI `describe-table` và `get-item`/`query` **chỉ đọc** ở mục 21 với bảng được phép xem, giới hạn read requests. Nếu không có AWS account, dùng bảng dữ liệu minh họa:

| Thông tin | Giá trị ví dụ |
|---|---|
| Table name | `Orders` |
| Base PK | `PK`, SK `SK` |
| GSI1 PK | `GSI1PK` |
| Table Region | `ap-southeast-1` |
| Global mode | Không (single-Region) |
| Read pattern A | `GetItem(PK=ORDER#101, SK=META)` |
| Read pattern B | `Query GSI1PK=CUSTOMER#7` |

**Câu hỏi:** Read pattern nào có thể bật strong? **A**, vì GetItem base table; **B** không, vì target GSI. Nếu UI vừa ghi order mà B chưa thấy, nên fallback GetItem theo orderId hoặc phản ánh write response.

### 24.2. Lab 2 — Tính read units

1. Đọc 200 items/s, mỗi item 3 KiB, dùng eventual: `200 × 0,5 = 100 units/s`.
2. Cùng workload strong: `200 × 1 = 200 units/s`.
3. Mỗi item tăng lên 4 KiB + 1 byte: strong `200 × 2 = 400 units/s`.
4. Đọc transactional 20 items/s, mỗi item 6 KiB: `20 × (2 blocks × 2) = 80 units/s`.

Tại sao có bước nhảy khi item vượt 4 KiB? Vì DynamoDB làm tròn số blocks cho tính capacity. Giải thích vì sao FilterExpression không tự làm giảm số items/bytes đã đọc từ base table.

### 24.3. Lab 3 — Race condition

Hai workers cùng muốn trừ stock=1. Cả hai đều GetItem strong và thấy 1. Có ngăn oversell không? **Không**. Viết `UpdateItem` với `ConditionExpression=available >= 1` và thiết kế `operationId` chống retry sau ACK mất. Phân biệt **stale read** với **concurrent update**.

### 24.4. Lab 4 — GSI lag

Ứng dụng tạo Order#101 với GSI1PK=CUSTOMER#7. Sau write thành công, GSI Query chưa thấy item. Vì sao? GSI asynchronous propagation. Có nên bật ConsistentRead=true trên GSI? **Không hỗ trợ**. Hãy đề xuất base GetItem fallback và UI hiển thị trạng thái đồng bộ.

### 24.5. Lab 5 — Global Tables MREC

Client Region A update Order#101 status=PAID, client Region B ngay lập tức gọi strong GetItem. Có bảo đảm thấy PAID không? **Không** với MREC, vì B chưa chắc đã có update. Giải pháp có thể là route read về A, chờ propagation với version check hoặc cân nhắc MRSC nếu cần global strong.

### 24.6. Lab 6 — Global Tables MRSC

Một nhóm muốn MRSC cho hệ thống ledger và cũng muốn dùng TransactWriteItems, TTL, LSI. Có tương thích không? **Không**, MRSC không hỗ trợ các tính năng đó. Cần thiết kế lại dữ liệu hoặc chọn kiến trúc khác. MRSC chỉ giúp global strongly consistent item reads, không là multi-item ACID cross-Region engine.

### 24.7. Lab 7 — DAX

DAX item cache chứa status=PENDING. Một service khác dùng direct DynamoDB UpdateItem sang PAID. User đọc qua DAX nhận PENDING. Tại sao? Cache stale do write bypass DAX. Một strong GetItem qua DAX có cache hit không? **Không**, request đi DynamoDB rồi trả response nhưng không cache strong result.

### 24.8. Kết quả lab

Lập bảng review:

| Access pattern | Data source | Consistency | Units ước tính | Rủi ro | Biện pháp |
|---|---|---|---|---|---|
| Order detail sau write | Base table | Strong | Theo item 4 KiB | Concurrent overwrite | Conditional version |
| Customer orders listing | GSI | Eventual | Theo GSI entry | GSI lag | Session fallback |
| Daily dashboard | Table/GSI | Eventual | Theo read bytes | Stale chấp nhận | Label độ trễ |
| Inventory reserve | Atomic UpdateItem | Write condition | Theo write units | Duplicate retries | Operation ID |
| Multi-item regional snapshot | Table transaction | TransactGet | 2× strong | Conflict/cost | Retry bounded |
| Global read immediate | MRSC replica | Strong | Đo Region/cost | Cross-Region latency | Failover test |

## 25. Câu hỏi tự đánh giá

1. Eventual read có thể trả item trước khi write được commit thành công không?
2. Vì sao một successful write có thể chưa hiển thị qua eventual read?
3. `ConsistentRead` mặc định bằng giá trị nào?
4. Table/LSI/GSI/Streams khác nhau về strong read ra sao?
5. `GetItem ConsistentRead=true` có ngăn item bị writer khác cập nhật ngay sau read không?
6. Strong `Scan` có cho snapshot isolation toàn table không?
7. `BatchGetItem` với strong per table có là atomic snapshot nhiều items không?
8. Khi nào chọn `TransactGetItems`?
9. Transactional read một item 4 KiB tốn bao nhiêu read units?
10. Item 4 KiB + 1 byte tốn bao nhiêu strong/eventual units?
11. Với 100 item reads/s, 3 KiB mỗi item, eventual tiết kiệm bao nhiêu so với strong?
12. FilterExpression có giảm RCU của base table Query không?
13. ProjectionExpression có làm item size được tính RCU nhỏ đi không?
14. `Limit=10` nghĩa là DynamoDB chắc chắn trả 10 items sau filter?
15. `LastEvaluatedKey` có ý nghĩa gì?
16. Có thể bật strong Query trên GSI bằng CLI/SDK không?
17. Tại sao một item vừa ghi có thể chưa hiển thị khi Query GSI?
18. DAX có cache strongly consistent reads không?
19. DAX query cache có tự invalidates sau item update không?
20. MREC global table có bảo đảm Region B đọc thấy write vừa commit ở A ngay không?
21. MREC giải quyết concurrent cross-Region writes thế nào?
22. MRSC khác MREC về replication/write latency ra sao?
23. MRSC có hỗ trợ GSI strong reads, TTL, LSI và transactions không?
24. MRSC cần bao nhiêu Regions và witness dùng để làm gì?
25. `TransactWriteItems` ở MREC có atomic giữa các Regions không?
26. Khi trừ tồn kho, tại sao conditional write quan trọng hơn chỉ strong read?
27. DynamoDB TTL có xóa item ngay chính xác lúc expiresAt không?
28. Làm cách nào phân biệt stale read, throttling và sai Region?
29. CloudWatch metric nào theo dõi replication lag của MREC?
30. Khi nào nên dùng strong read cho mọi access pattern của một ứng dụng?

### Định hướng đáp án

- **Eventual:** default, có thể stale tạm thời; đọc các giá trị đã commit, dùng khoảng **0,5 unit/4 KiB**.
- **Strong:** base table/LSI, **1 unit/4 KiB**, không khóa item hoặc tạo snapshot toàn Scan.
- **Transactional:** `TransactGetItems` **2 units/4 KiB**, giới hạn 100 items/4 MiB, same account/Region và không hỗ trợ MRSC.
- **GSI/Streams:** eventual-only; FilterExpression/ProjectionExpression không làm giảm dữ liệu base table đã đọc.
- **Global Tables:** MREC cross-Region eventual; MRSC strong xuyên Regions nhưng có latency và feature limits.
- **Correctness:** dùng `ConditionExpression`, optimistic version và idempotency cho concurrent updates; đừng thay bằng một read strong trước write.

## 26. Tài liệu AWS chính thức

1. [DynamoDB read consistency](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.ReadConsistency.html) — Default eventual, strong table/LSI, GSI/Streams eventual, global modes.
2. [DynamoDB read and write operations](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/read-write-operations.html) — Capacity units theo item size/consistency.
3. [DynamoDB provisioned capacity](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/provisioned-capacity-mode.html) — RCU/WCU và capacity planning.
4. [On-demand capacity mode](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/on-demand-capacity-mode.html) — RRUs và traffic behavior.
5. [DynamoDB Query API](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_Query.html) — `ConsistentRead`, pagination, consumed capacity.
6. [Query and FilterExpression](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.FilterExpression.html) — Filter sau khi đọc items.
7. [Other Query considerations](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.Other.html) — RCUs, limits, index consistency.
8. [DynamoDB Scan API](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_Scan.html) — Scan strong không snapshot.
9. [GetItem API](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_GetItem.html) — Point reads.
10. [BatchGetItem API](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_BatchGetItem.html) — Batch strong flag, UnprocessedKeys.
11. [TransactGetItems API](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_TransactGetItems.html) — Atomic multi-item read và limits.
12. [DynamoDB transactions: how they work](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis.html) — Isolation, conflicts, consumed units.
13. [Global tables architecture and consistency modes](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/V2globaltables_HowItWorks.html) — MREC/MRSC, replication, limitations, supported Regions.
14. [Best practices for Global Tables](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-global-table-design.html) — Topology, consistency/availability tradeoffs.
15. [DescribeTable API](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_DescribeTable.html) — `MultiRegionConsistency` table metadata.
16. [Global secondary indexes](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/GSI.html) — GSI replication/access patterns.
17. [Local secondary indexes](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/LSI.html) — LSI constraints và strong consistency.
18. [DAX consistency models](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/DAX.consistency.html) — Item/query cache, strong pass-through.
19. [DAX how it works](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/DAX.concepts.html) — Read caching behavior.
20. [Conditional writes](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Expressions.ConditionExpressions.html) — Protecting invariants.
21. [DynamoDB Java SDK 2.x examples](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/java_dynamodb_code_examples.html) — GetItem, Query và SDK design.
22. [DynamoDB CloudWatch metrics](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/metrics-dimensions.html) — Capacity, throttle, latency.
23. [DynamoDB VPC endpoints](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/privatelink-interface-endpoints.html) — Private access options.
24. [DynamoDB pricing](https://aws.amazon.com/dynamodb/pricing/) — On-demand/provisioned reads, storage, global replication.
25. [AWS DynamoDB Service Quotas](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/ServiceQuotas.html) — Item sizes, limits và capacity.

> **Ghi nhớ cuối bài:** **Eventual reads** thường tối ưu cho dữ liệu có thể stale ngắn, còn **strong table/LSI reads** dùng khi cần read-after-write trong phạm vi hỗ trợ. **GSI/Streams chỉ eventual**, **DAX strong reads pass-through**, **MREC không cho global strong read**, trong khi **MRSC** làm được nhưng đánh đổi latency và không hỗ trợ transaction/TTL/LSI. Với mọi bài toán cập nhật có race, vẫn phải dựa vào **conditional writes, idempotency và transactions phù hợp**. Hãy đo units, P99 latency, replication/index lag và chi phí trước khi quyết định.




