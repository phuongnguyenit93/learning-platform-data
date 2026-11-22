# Hot partition, throttling, backup và khôi phục DynamoDB

## Mục tiêu học tập

Sau bài này, người học có thể:

- Giải thích cách **partition key**, **sort key** và **physical partitions** liên hệ với khả năng mở rộng của Amazon DynamoDB.
- Phân biệt **hot item/hot partition**, **table-level throttling**, **GSI throttling**, **quota account-level** và **giới hạn on-demand do quản trị viên đặt**; không chữa mọi lỗi bằng cách tăng RCU/WCU.
- Tính gần đúng **RCU/WCU**, hiểu strongly consistent, eventually consistent, transactional reads/writes, giới hạn mỗi physical partition và cơ chế adaptive capacity.
- Đọc các **ThrottlingReasons** gồm resource ARN và loại giới hạn, liên hệ với CloudWatch metrics và Contributor Insights để tìm nguyên nhân.
- Lựa chọn **on-demand/provisioned capacity**, Auto Scaling, warm throughput và chiến lược pre-warm khi chuẩn bị flash sale hoặc tăng tải đột ngột.
- Chống hot key bằng **partition key cardinality, write sharding, aggregation, cache/DAX, backpressure**, đồng thời hiểu trade-off query fanout, order và transaction.
- Triển khai **exponential backoff + jitter** với AWS SDK for Java v2, xử lý `BatchWriteItem.UnprocessedItems`, `BatchGetItem.UnprocessedKeys` và tránh retry vô hạn.
- Phân biệt **on-demand backup**, **point-in-time recovery (PITR)**, **AWS Backup**, **Global Tables** và **PITR restore**, lựa chọn theo RPO/RTO và nhu cầu lưu trữ.
- Bật PITR, tạo backup, khôi phục sang **một DynamoDB table mới**, kiểm chứng dữ liệu, cấu hình bổ sung và cutover an toàn bằng AWS CLI.
- Thiết kế IAM, KMS, VPC endpoints, CloudWatch, alarm, diễn tập recovery và kiểm soát chi phí cho hệ thống sử dụng DynamoDB.

**Ngữ cảnh chương:** **DynamoDB** trong module **CLOUD_PROVIDERS_AWS** thuộc hành trình học AWS từ Region/AZ, IAM, VPC, compute, lưu trữ và database đến tích hợp/serverless. Bài tập trung vào việc chọn, thiết kế và vận hành DynamoDB **an toàn, theo dõi được, có khả năng phục hồi và kiểm soát chi phí**, đặc biệt khi kết hợp API Gateway/Lambda/ECS, SQS/EventBridge, CloudWatch và AWS Backup.

> **Ranh giới:** DynamoDB là dịch vụ quản lý; người dùng **không trực tiếp tạo/điều khiển physical partitions**. Các giới hạn, chế độ capacity, giá và tính năng restore có thể thay đổi theo Region/tài khoản và thời điểm. Lệnh CLI bên dưới dùng tên bảng lab và profile giả định; không chạy load test, restore hoặc delete trên bảng production.

## 1. Bài toán: table đủ capacity vẫn có request bị throttled?

Giả sử hệ thống thương mại điện tử có table `Orders`, dùng `tenantId` làm partition key và `orderId` làm sort key:

~~~text
PK = TENANT#tenant-a | SK = ORDER#1001
PK = TENANT#tenant-a | SK = ORDER#1002
PK = TENANT#tenant-a | SK = ORDER#1003
PK = TENANT#tenant-b | SK = ORDER#2001
...
~~~

Trong đợt flash sale, tenant A tạo rất nhiều đơn mỗi giây, còn những tenants khác ít traffic. Tổng read/write consumption của table vẫn thấp hơn capacity bạn đã provision, nhưng request của tenant A bắt đầu gặp throttling.

~~~mermaid
flowchart LR
    API[API Gateway / Lambda] --> DDB[(DynamoDB Orders)]
    DDB --> Hot[Partition/key range nóng: TENANT#A]
    DDB --> Cool1[Range B ít traffic]
    DDB --> Cool2[Range C ít traffic]
    DDB --> Cool3[Range D ít traffic]
    Hot --> Fail[Throttling dù table capacity còn dư]
    Fail --> Obs[ThrottlingReasons + CloudWatch]
~~~

Vấn đề thường là **phân bố tải không đồng đều**, không đơn thuần table thiếu tổng capacity. Chỉ tăng tổng WCU có thể **không giải quyết giới hạn một physical partition/key range**.

Một sự cố thứ hai: nhân viên chạy nhầm batch update làm mất dữ liệu. Read replica hoặc Global Tables có thể sao chép lỗi sang Regions khác. Để phục hồi, cần **PITR hoặc backup đúng thời điểm**, khôi phục **sang table mới**, rồi kiểm thử và chuyển traffic có kiểm soát.

Hai kỹ năng của bài vì vậy liên quan mật thiết: **ngăn hệ thống sập do tải phân bố sai** và **đảm bảo dữ liệu có thể khôi phục khi lỗi đã xảy ra**.

## 2. DynamoDB logical key và physical partition khác nhau thế nào?

Một DynamoDB table chứa **items**; mỗi item được xác định bằng primary key:

- **Simple primary key**: chỉ có **partition key (HASH)**, ví dụ `userId`.
- **Composite primary key**: **partition key + sort key (RANGE)**, ví dụ `PK=ORDER#1001` và `SK=METADATA`.

Partition key được DynamoDB băm để phân phối dữ liệu trên **physical partitions** do dịch vụ quản lý. Sort key hỗ trợ sắp xếp và truy vấn trong cùng một logical partition key.

### Logical partition key không đồng nghĩa physical partition

- Tất cả items có cùng partition key tạo thành một **item collection** (khi bảng có sort key).
- Một physical partition có thể chứa nhiều partition key values.
- DynamoDB có thể split/rebalance physical partitions theo dung lượng và mức tải.
- Nhiều items cùng partition key **không bảo đảm tất cả mãi nằm một physical partition** trong mọi điều kiện; adaptive capacity có thể split item collections theo sort key khi phù hợp.
- Có **Local Secondary Index (LSI)** làm thay đổi khả năng split item collection; không giả định các keys nóng luôn tự tách được.

**Hot key:** Một partition key value hoặc item nhận quá nhiều requests.

**Hot physical partition/key range:** Một vùng vật lý nhận quá nhiều RCU/WCU, có thể do một key quá nóng, nhiều keys tập trung hoặc access pattern phân bố không đều.

**Hot GSI:** Base table có partition key tốt nhưng GSI key kém, khiến một số write/read qua GSI bị nghẽn.

### Ví dụ key tốt và chưa tốt

| Access pattern | Khóa dễ nóng | Khóa nên cân nhắc |
| --- | --- | --- |
| Sự kiện mọi người cùng tạo hôm nay | `PK=DATE#2026-11-20` | `PK=DATE#2026-11-20#SHARD#N` hoặc chia theo entity |
| Hàng triệu likes trên một bài viết | `PK=POST#hot-post`, mỗi like update cùng item | Sharded counters + async aggregate |
| Ghi lượt truy cập sản phẩm | `PK=PRODUCT#popular-id` | Ghi event phân tán qua Kinesis/SQS rồi aggregate |
| Đơn hàng đa tenant | `PK=TENANT#large-tenant` | Tách theo tenant + bucket/shard nếu profile load cần |
| GSI theo trạng thái chung | `GSI_PK=STATUS#PENDING` | Phân tán theo tenant/time bucket/shard nếu query cho phép |

**Không tự động thêm random suffix cho mọi key.** Nó làm truy vấn đọc phải fanout, tăng số queries, thay đổi uniqueness và có thể làm mất thứ tự mong muốn. Chỉ shard khi đo thấy key range vượt khả năng và thiết kế được cách đọc/merge.

## 3. RCU, WCU và kích thước item: tính đúng trước khi scale

DynamoDB đo capacity tiêu thụ khác nhau theo **đọc/ghi** và **consistency**.

### 3.1. Đọc

Với item ≤ **4 KB**:

- **Strongly consistent read:** khoảng **1 RCU** cho một read/giây.
- **Eventually consistent read:** khoảng **0,5 RCU** cho một read/giây (hai reads/giây dùng 1 RCU).
- **Transactional read:** khoảng **2 RCUs** cho một read/giây.

Nếu item > 4 KB, tính theo bội số block 4 KB, làm tròn lên; số RCU còn tùy consistency.

Ví dụ item **6 KB**, đọc một lần:

| Cách đọc | Capacity tương đương |
| --- | --- |
| Strong | `ceil(6/4)=2 RCU` |
| Eventually consistent | `2 × 0,5 = 1 RCU` |
| Transactional | `2 × 2 = 4 RCU` |

### 3.2. Ghi

Mỗi item **≤1 KB** được ghi một lần tốn khoảng **1 WCU**; làm tròn lên bội số 1 KB. Transactional write thường tốn **gấp đôi** WCU thông thường.

Ví dụ một write item **2,2 KB**:

- Standard write: `ceil(2,2/1)=3 WCU`.
- Transactional write: `6 WCU` cho cùng kích thước theo mô hình tính đơn vị.

### 3.3. Query, Scan và FilterExpression

Một `Query` hoặc `Scan` có thể đọc nhiều items, tiêu thụ capacity theo **dữ liệu thực được đọc**, không phải chỉ số items cuối cùng trả về. **`FilterExpression` được áp dụng sau khi DynamoDB đọc items**, nên không giúp giảm RCU cho những items đã được quét/truy xuất.

**Lỗi điển hình:** `Scan` toàn bảng rồi lọc `status=NEW`, đồng thời số request tăng, dẫn tới cost/throttling lớn. Giải pháp là **thiết kế key/GSI theo access pattern**, phân trang, giới hạn concurrency và tránh Scan trên đường request nóng.

**On-demand mode** tính bằng **read request units/write request units (RRU/WRU)** theo cùng cơ sở kích thước và consistency, nhưng pricing/pay-per-request khác provisioned capacity.

## 4. Giới hạn throughput ở physical partition

Tài liệu DynamoDB nêu mốc tham khảo **mỗi physical partition**:

| Loại | Giới hạn thông thường |
| --- | --- |
| Write | Khoảng **1.000 WCU/giây** |
| Strongly consistent reads | Khoảng **3.000 RCU/giây** |
| Eventually consistent reads | Khoảng **6.000 reads 4 KB/giây**, tương đương 3.000 RCU |

Các mốc này đo theo **capacity units**, không phải mọi HTTP requests có giá trị như nhau; item lớn/transactional operations tiêu thụ nhiều units hơn.

**Đặc điểm quan trọng:**

1. **Read và write throttle độc lập** ở partition level.
2. **On-demand cũng chịu giới hạn partition**, dù tổng table throughput có thể rất lớn.
3. **Adaptive capacity** giúp phân phối capacity tới partition/key range nóng nhưng **không vượt giới hạn vật lý của một partition**.
4. Tự split/rebalance có thể giúp khi traffic pattern cho phép; một item được update đồng thời quá nhiều vẫn có bottleneck không dễ tách.
5. GSI có **partitioning/throughput riêng**, nên một key nóng ở GSI có thể tạo lỗi write ngay cả khi base table dùng khóa phân bố tốt.

### Ví dụ tính nhanh hot counter

Một item `PK=COUNTER#SALE` được update **1.800 lần/giây**, mỗi lần ≤1KB. Đòi hỏi khoảng **1.800 WCUs/giây vào đúng một item/key**.

Trong khi một partition chỉ đáp ứng khoảng **1.000 WCU/giây**, nâng table capacity từ 5.000 lên 20.000 WCU **không khiến một item duy nhất tự nhiên nhận được 20.000 WCU**. Giải pháp là **sharded counters**, aggregation hoặc đổi luồng xử lý.

## 5. Throttling không phải chỉ có một nguyên nhân

DynamoDB có bốn nhóm **ThrottlingReason** chính, mỗi nhóm kết hợp:

~~~text
<ResourceType><OperationType><LimitType>
Ví dụ: TableWriteKeyRangeThroughputExceeded
~~~

- `ResourceType`: `Table` hoặc `Index`.
- `OperationType`: `Read` hoặc `Write`.
- `LimitType`: một trong bốn nguyên nhân sau.

| LimitType | Khi nào gặp? | Hướng xử lý đầu tiên |
| --- | --- | --- |
| **`KeyRangeThroughputExceeded`** | Một physical partition/key range quá nóng | Xác định hot keys, partition key/GSI design, adaptive capacity, sharding/cache |
| **`ProvisionedThroughputExceeded`** | Table/GSI vượt RCU/WCU đã provision | Tối ưu request, tăng provisioned units/Auto Scaling, kiểm tra GSI |
| **`AccountLimitExceeded`** | On-demand table/GSI vượt quota throughput theo account/Region | Kiểm tra quotas, xin tăng quota, warm-up, giảm tải |
| **`MaxOnDemandThroughputExceeded`** | Vượt **maximum on-demand throughput** do người dùng cấu hình | Xem giới hạn chi phí, thay max nếu được duyệt hoặc giới hạn tải |

Các lỗi có thể xuất hiện dưới những exception như **`ProvisionedThroughputExceededException`**, **`ThrottlingException`** hoặc **`RequestLimitExceeded`** tùy tình huống. **Tên exception đơn lẻ không đủ để xác định hot partition.**

### Ví dụ thông tin lỗi

~~~json
{
  "code": "ProvisionedThroughputExceededException",
  "ThrottlingReasons": [
    {
      "reason": "IndexWriteKeyRangeThroughputExceeded",
      "resource": "arn:aws:dynamodb:ap-southeast-1:111122223333:table/OrdersLab/index/ByStatus"
    }
  ]
}
~~~

Ví dụ này chỉ đến **GSI `ByStatus`**, **write**, **key range throughput**. Tăng RCU của base table không giải quyết đúng nguyên nhân.

### Cách đọc chuỗi lỗi

~~~mermaid
flowchart TD
    Error[DynamoDB throttling response] --> Reason[Đọc ThrottlingReasons + resource ARN]
    Reason --> Res{Table hay Index?}
    Res --> Type{LimitType?}
    Type -->|KeyRange| Key[Hot key / sharding / Contributor Insights]
    Type -->|Provisioned| P[Provisioned RCUs/WCUs và Auto Scaling]
    Type -->|AccountLimit| Q[Service Quotas / account-Region limits]
    Type -->|MaxOnDemand| O[Configured on-demand maximum]
    Key --> Test[Đo lại latency + throttles + cost]
    P --> Test
    Q --> Test
    O --> Test
~~~

**Không retry vô hạn trước khi xác định loại lỗi.** Retry ngắn giúp lỗi transient nhưng không thể biến một key có tải cố định 3.000 writes/giây thành partition có capacity 3.000 WCU.

## 6. GSI hot key và write throttling/back-pressure

Một base table có PK `ORDER#uuid` phân bố rất tốt, nhưng có GSI:

~~~text
Table PK = orderId (UUID đa dạng)
GSI1 PK  = status (chỉ NEW / PAID / FAILED)
GSI1 SK  = createdAt
~~~

Trong đợt flash sale, gần như mọi writes đều gắn `status=NEW`. GSI dồn traffic vào cùng **logical partition key**. Khi GSI write không theo kịp, **base table writes có thể bị throttled do back-pressure từ GSI**, dù base table chính còn nhiều capacity.

### Dấu hiệu

- `ThrottlingReason` chứa **`IndexWriteKeyRangeThroughputExceeded`** hoặc **`IndexWriteProvisionedThroughputExceeded`**.
- ARN trong lỗi kết thúc bằng `/index/ByStatus`.
- GSI `WriteThrottleEvents` hoặc các throttling reason metrics tăng.
- Table write API latency/errors tăng theo, trong khi nhiều table-level gauges chưa chạm giới hạn.

### Thiết kế lại access pattern

Thay vì `GSI_PK=STATUS#NEW`, cân nhắc:

~~~text
GSI_PK = STATUS#NEW#DAY#2026-11-20#SHARD#03
GSI_SK = createdAt#orderId
~~~

Đọc danh sách tất cả orders trạng thái NEW cần **fanout Query trên N shards**, sau đó merge-sort và phân trang theo token của từng shard. Nếu dashboard chỉ cần đếm, có thể dùng **event-driven materialized counts** thay vì query toàn bộ GSI.

**Trade-off:** Sharding làm giảm hot writes nhưng **tăng read calls, complexity và cost**. Cần có migration plan, backfill và versioning; không đổi schema trên bảng production thiếu rollback.

## 7. Adaptive capacity, split-for-heat và những giới hạn không thể bỏ qua

DynamoDB tự quản **adaptive capacity** để sử dụng phần throughput còn dư của table cho những key ranges nóng, giảm throttle khi traffic không cân bằng.

### Adaptive capacity làm gì?

- Theo dõi hot partitions/keys và phân phối throughput hợp lý.
- Có thể **isolate hot items** hoặc **split partitions** theo mức tải và cấu trúc key.
- Hoạt động tự động, không yêu cầu developer bật một switch riêng.
- Có thể giúp khi một physical partition nóng nhưng tổng table còn unused capacity.

### Adaptive capacity không làm gì?

- **Không vượt trần khoảng 1.000 WCU/3.000 RCU của một physical partition**.
- Không bảo đảm split một **item duy nhất** chịu mọi writes.
- Với **LSI**, DynamoDB **không tự split item collection trên nhiều physical partitions** trong một số cách tổ chức, nên một partition key với item collection khổng lồ vẫn có thể hot.
- Với **sort key luôn tăng/giảm đơn điệu**, split-for-heat có thể kém hiệu quả vì writes luôn dồn về range mới nhất.
- Không cứu design GSI mà mọi bản ghi dùng cùng một low-cardinality partition key ở load quá cao.

### Khi nào nên đợi thích nghi, khi nào phải đổi key?

Nếu throttling xuất hiện ngắn khi traffic vừa tăng, rồi tự biến mất trong khi SLO vẫn đạt, adaptive capacity/split-for-heat có thể đã giải quyết. Nếu **cùng key/partition range tiếp tục throttle** và latency/retries tăng, cần chuyển sang thiết kế key phân tán/caching/backpressure.

**Đừng giả định mọi key hot sẽ tự được tách ngay**. Hãy đo với Contributor Insights và CloudWatch, xét LSI, sort key monotonic và workload thực.

## 8. Provisioned, on-demand, warm throughput và flash sale

### Provisioned capacity

Bạn đặt mức **RCU/WCU** cho table/GSI, có thể bật DynamoDB Auto Scaling. Throttling xuất hiện khi sử dụng vượt provisioned units, hoặc hot partition đạt trần dù còn table capacity.

**Auto Scaling không tăng tức thời** và bị ràng buộc bởi min/max config, target utilization và thời gian CloudWatch metrics. Flash sale tăng đột ngột có thể throttle trước khi Auto Scaling phản ứng.

### On-demand capacity

On-demand thanh toán theo request units, tự tăng/giảm theo traffic. Tuy nhiên:

- Table mới có baseline throughput được AWS công bố, ví dụ **tới khoảng 4.000 writes/giây và 12.000 strongly consistent reads/giây** cho workload đều, item nhỏ.
- Hệ thống có thể đáp ứng **gấp đôi previous peak** ngay lập tức theo điều kiện AWS.
- Nếu traffic vượt gấp đôi previous peak trong khoảng **30 phút**, vẫn có thể throttle khi hệ thống đang scale.
- Giới hạn theo **account/Region**, **user-set maximum throughput** và **physical partitions** vẫn áp dụng.
- On-demand **không miễn phí**: request pricing, storage, backup/PITR, streams, Global Tables, data transfer và monitoring vẫn tính phí theo tính năng.

### Warm throughput

AWS có khái niệm **warm throughput** cho table/GSI: mức read/write workload mà resource có thể hỗ trợ **ngay lập tức** dựa trên lịch sử/cấu hình. Có thể chủ động **pre-warm** chuẩn bị tăng tải dự kiến theo khả năng/giá.

**Warm throughput khác giới hạn tối đa của một partition.** Pre-warm table lên 50.000 WCUs không cho phép 50.000 writes cùng dồn vào một physical partition.

| Hiện tượng | Cách phản ứng |
| --- | --- |
| Table provisioned hết WCU, keys phân bố đều | Tăng provisioned WCU/Auto Scaling capacity |
| On-demand vượt previous peak nhanh | Pre-warm, ramp up có kiểm soát, dự báo peak |
| Vượt account-level quota | Service Quotas/AWS Support theo thủ tục |
| Đụng configured on-demand max | Xem max throughput và budget policy |
| `KeyRangeThroughputExceeded` dù table còn dư | Sửa partition key/GSI, sharding/cache/backpressure |
| GSI write back-pressure | Tăng GSI capacity nếu thiếu tổng; đổi GSI key nếu hot range |

## 9. Chẩn đoán hot keys bằng CloudWatch và Contributor Insights

### Những bước đầu tiên

1. Lấy **exception + ThrottlingReasons + resource ARN** từ SDK/log.
2. Phân biệt `Table` hay `Index`, `Read` hay `Write`, limit type cụ thể.
3. Mở DynamoDB Console → table/index → **Metrics/Monitoring** theo giao diện hiện hành.
4. So **ConsumedReadCapacityUnits/ConsumedWriteCapacityUnits**, provisioned levels, read/write throttle metrics, latency và request count.
5. Xác minh request pattern: GetItem/Query/Scan/BatchWrite, item size, consistency, index, concurrency.
6. Xem **CloudWatch Contributor Insights for DynamoDB** nếu được bật/phù hợp bảo mật.
7. Kiểm tra key cardinality và top hot keys, đặc biệt **GSI partition key**.
8. Cập nhật giả thuyết, chọn mitigation theo loại lý do, test trong lab/staging.

### Contributor Insights giúp gì?

Contributor Insights có thể báo **most accessed** và **most throttled** partition/sort key values, hỗ trợ tìm hot key. Tuy nhiên:

- Dữ liệu primary keys có thể là **PII/sensitive identifiers**, cần review IAM/retention/encryption policy trước khi bật.
- Contributor Insights có **phí**; không bật rộng trên mọi table/GSI nếu không có use case.
- Không phải mọi loại request (ví dụ PartiQL theo tài liệu) được hỗ trợ như nhau.
- Hot range có thể do traffic “rolling hot partitions”, Scan hay khóa monotonic, nên chỉ số top key không đủ giải thích toàn bộ.

**Khi log:** Thay vì ghi raw payload/token, ghi `tableName`, `indexName`, `operation`, `reason`, `requestId`, `itemSizeBucket` và **hash/key prefix không nhạy cảm** theo policy.

## 10. Write sharding: chia một key nóng ra nhiều buckets

Ví dụ mọi order events của một tenant đang nằm dưới:

~~~text
PK = TENANT#A
SK = EVENT#timestamp#uuid
~~~

Để chia write load, chọn `N` logical shards:

~~~text
PK = TENANT#A#SHARD#00
PK = TENANT#A#SHARD#01
...
PK = TENANT#A#SHARD#15
SK = EVENT#timestamp#uuid
~~~

### Chọn shard như thế nào?

- **Random sharding**: writer chọn bucket ngẫu nhiên. Phù hợp nếu không cần truy cập một entity duy nhất chỉ từ một shard.
- **Calculated sharding**: `shard = hash(eventId) mod N`. Cho phép xác định bucket ổn định từ eventId.
- **Time-bucket + shard**: giảm item collection không giới hạn và hỗ trợ queries theo ngày/giờ.

Một ví dụ giả mã:

~~~text
function shardFor(eventId, shardCount):
    return unsignedStableHash(eventId) modulo shardCount

pk = "TENANT#" + tenantId + "#DAY#" + date + "#SHARD#" + shardFor(eventId, 16)
sk = "EVENT#" + timestamp + "#" + eventId
PutItem(pk, sk, otherAttributes)
~~~

**Tuyệt đối không thay đổi `shardCount` thiếu versioning.** Nếu shard từ 16 sang 32, cùng eventId có thể tính PK khác; phải có key version hoặc migration/catalog để đọc cả dữ liệu cũ và mới.

### Đọc khi đã shard

Query theo tenant + ngày phải:

1. Query tất cả shard keys cần thiết.
2. Phân trang độc lập từng shard (LastEvaluatedKey theo Query).
3. Merge-sort kết quả theo timestamp và tạo composite pagination token.
4. Giới hạn concurrency, xử lý partial failures, timeouts và chi phí.

Nếu workload chủ yếu muốn **point lookup một event**, có thể duy trì mapping `eventId → shard` hoặc dùng calculated shard ổn định. Nếu workload cần **unique key toàn tenant**, dùng conditional write/transaction pattern hoặc index phù hợp; sharding làm uniqueness toàn cục khó hơn.

**Sharding là thay đổi data model**, không phải chỉ tăng tham số throughput.

## 11. Hot read: caching, denormalization và strongly consistent reads

Với một hot item phổ biến, như config hoặc catalog item được đọc hàng nghìn lần/giây:

- Dùng **application cache/ElastiCache** với TTL/invalidation rõ ràng.
- Cân nhắc **DynamoDB Accelerator (DAX)** khi access patterns/API và consistency requirements tương thích.
- Cho phép **eventually consistent reads** khi nghiệp vụ chấp nhận; giảm capacity tiêu thụ gần một nửa so với strong reads cùng item size.
- Denormalize read model hoặc publish snapshots qua S3/CloudFront cho dữ liệu công khai ít đổi.
- Giới hạn duplicate retries và cache misses, bảo vệ DB bằng backpressure.

### DAX không phải giải pháp cho mọi vấn đề

- DAX là cache nằm trước DynamoDB cho những access patterns được hỗ trợ, có **eventual consistency semantics** cho cache reads.
- Không tự sửa **hot writes**; write traffic vẫn phải tới DynamoDB.
- Không phù hợp để quyết định số dư/authorization/stock cần transaction-level correctness nếu không thiết kế cẩn trọng.
- Có chi phí cluster nodes, availability và vận hành riêng.

### Tránh cache stampede

Nếu cache của một item hết TTL, hàng nghìn clients có thể cùng miss rồi Query DynamoDB một key. Dùng **single-flight**, TTL jitter, stale-while-revalidate (nếu an toàn), rate limit và bảo vệ fallback; không chỉ tăng cache TTL vô hạn.

## 12. Retry đúng: exponential backoff + jitter và idempotency

Throttling thường là lỗi **retryable**, nhưng retry không giới hạn có thể làm **retry storm**, tăng latency và chi phí. AWS SDK for Java v2 có các retry strategies tích hợp; ứng dụng cần cấu hình hợp lý theo request SLO và workload.

### Nguyên tắc

1. Chỉ retry những lỗi thực sự **transient/retryable** theo SDK/service classification.
2. Dùng **exponential backoff + jitter** để nhiều clients không đồng loạt retry cùng nhịp.
3. Giới hạn số attempts và **deadline tổng**; frontend không nên chờ nhiều phút chỉ để đọc một item.
4. Dùng rate limiting, circuit breaker, queue/buffer cho spikes; đừng dựa vào retry thay partition key design.
5. Ghi `requestId`, `reason`, number of retries, latency và business outcome vào metrics.
6. Writes cần **idempotency** khi caller không biết lần trước đã commit chưa; chọn conditional writes/unique key hoặc transaction có idempotency token theo API hỗ trợ.

### Java SDK v2: ví dụ retry strategy

Ứng dụng cần dependency `software.amazon.awssdk:dynamodb` và BOM AWS SDK for Java v2, có credentials từ IAM role/profile.

~~~java
package com.example.dynamodb;

import java.time.Duration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.core.retry.RetryMode;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;

public final class DynamoClientFactory {

    public static DynamoDbClient create() {
        return DynamoDbClient.builder()
            .region(Region.AP_SOUTHEAST_1)
            // STANDARD hỗ trợ backoff/jitter và retry quota theo AWS SDK.
            // Chọn max attempts qua SDK configuration khi cần.
            .overrideConfiguration(c -> c
                .retryStrategy(RetryMode.STANDARD)
                .apiCallTimeout(Duration.ofSeconds(10))
                .apiCallAttemptTimeout(Duration.ofSeconds(3)))
            .build();
    }
}
~~~

**Chú ý phiên bản SDK:** Cấu hình `retryStrategy(RetryMode.STANDARD)` là một API được AWS SDK for Java v2 hỗ trợ; retry mode `STANDARD` có exponential backoff và jitter theo tài liệu AWS. Giá trị mặc định của `maxAttempts` có thể khác giữa các phiên bản SDK, nên hãy pin dependency, kiểm tra SDK Java v2 Developer Guide và đo retry behavior thực tế. **Không lồng thêm vòng retry thủ công ngoài SDK nếu đã có retry**, trừ khi cần policy riêng với deadline tổng và idempotency.

### Idempotency và retry outcome không rõ

Một `PutItem` có thể đã commit nhưng response về client bị timeout. Retry lệnh mà không có `ConditionExpression` có thể ghi đè dữ liệu hoặc tăng counter hai lần.

Ví dụ bảo vệ tạo order duy nhất:

~~~json
{
  "TableName": "OrdersLab",
  "Item": {
    "PK": {"S": "ORDER#501"},
    "SK": {"S": "META"},
    "status": {"S": "CREATED"}
  },
  "ConditionExpression": "attribute_not_exists(PK)"
}
~~~

Nếu retry gặp `ConditionalCheckFailedException`, không coi nó luôn là throttling; kiểm tra item đã tạo bởi lần trước hay bởi request khác, đối chiếu `eventId`/idempotency key trước khi trả kết quả.
## 13. BatchGetItem/BatchWriteItem: HTTP thành công chưa chắc đã xử lý hết

Với batch APIs, DynamoDB có thể **xử lý một phần** request và trả phần chưa xử lý trong response:

- `BatchWriteItem` → `UnprocessedItems`.
- `BatchGetItem` → `UnprocessedKeys`.

**Đừng coi HTTP 200 là mọi records đều đã thành công.**

### Batch write demo

~~~json
{
  "RequestItems": {
    "OrdersHotLab": [
      {
        "PutRequest": {
          "Item": {
            "PK": {"S": "ORDER#501"},
            "SK": {"S": "META"},
            "status": {"S": "CREATED"}
          }
        }
      },
      {
        "PutRequest": {
          "Item": {
            "PK": {"S": "ORDER#502"},
            "SK": {"S": "META"},
            "status": {"S": "CREATED"}
          }
        }
      }
    ]
  }
}
~~~

Nếu response chứa:

~~~json
{
  "UnprocessedItems": {
    "OrdersHotLab": [
      {
        "PutRequest": {
          "Item": {
            "PK": {"S": "ORDER#502"},
            "SK": {"S": "META"},
            "status": {"S": "CREATED"}
          }
        }
      }
    ]
  }
}
~~~

thì ứng dụng **chỉ retry `ORDER#502`**, không gửi lại cả batch một cách mù quáng.

### Retry pattern

~~~text
pending = initialRequests
attempts = 0

while pending != empty and attempts < maxAttempts and beforeDeadline:
    response = BatchWriteItem(pending)
    pending = response.UnprocessedItems
    if pending != empty:
        wait(exponentialBackoffWithFullJitter(attempts))
    attempts += 1

if pending != empty:
    store pending durably to retry queue / DLQ
    alert failure without pretending success
~~~

**Lưu ý quan trọng:**

- `BatchWriteItem` **không** hỗ trợ conditional write từng item như `PutItem.ConditionExpression`; không dùng batch write cho operations cần uniqueness/idempotency condition.
- `BatchWriteItem` giới hạn **25 requests/batch** và request payload size theo AWS limits; response có thể partial.
- `BatchGetItem` giới hạn **100 items/request** và các limits dữ liệu/truy cập; `UnprocessedKeys` có thể chứa keys do throughput/size.
- Với **AWS SDK Java v2 Enhanced Client**, phương thức batchGet có thể hỗ trợ retry unprocessed keys; batchWrite có thể trả danh sách unprocessed để ứng dụng tiếp tục. Luôn xem contract đúng SDK version.
- Tăng số threads retry không phải giải pháp khi hot partition không có capacity.

### Write transaction khác batch write

`TransactWriteItems` có atomicity trong phạm vi API hỗ trợ, tính capacity khác và có thể bị từ chối bởi conflict/throttling. Với transaction writes, **cần idempotency token `ClientRequestToken`** theo thời hạn/hợp đồng API; không tự thay nó bằng `BatchWriteItem` vì nghĩ cả hai đều “ghi nhiều items”.

## 14. DynamoDB Streams, Lambda, SQS và backpressure

DynamoDB thường đứng sau API Gateway/Lambda/ECS service. Nếu client ghi dồn vào **một partition key nóng**, scale Lambda concurrency vô hạn chỉ làm tăng số writes tới cùng key, khiến throttle nặng hơn.

~~~mermaid
flowchart LR
    Client[Web/Mobile] --> API[API Gateway]
    API --> Lambda[Lambda / ECS]
    Lambda --> Rate[Rate limit / batching]
    Rate --> DB[(DynamoDB)]
    DB --> Stream[DynamoDB Streams]
    Stream --> Processor[Lambda stream processor]
    Processor --> Queue[(SQS DLQ / failure destination)]
~~~

**Các lựa chọn chống bão tải:**

1. **Giới hạn concurrency** phía Lambda/ECS và token bucket per tenant/resource.
2. Đưa write-heavy asynchronous jobs qua **SQS** để buffer, giảm tốc độ consume phù hợp.
3. Gộp nhiều incremental updates thành **periodic aggregate write** khi business cho phép.
4. Shard writes bằng partition key model phù hợp; tránh một item counter ghi liên tục.
5. Dùng conditional writes, optimistic locking và idempotency để chống duplicates khi retry từ queue.
6. Dùng DynamoDB Streams để xử lý CDC/đồng bộ read models theo khả năng, **không nhầm Streams là bản backup khôi phục tùy thời điểm**.

### Streams không thay backup

DynamoDB Streams có **retention và semantics sự kiện** riêng, không phải ảnh chụp toàn table. Một event đã đi qua stream hoặc retention window không cung cấp lịch sử đầy đủ để khôi phục table do xóa nhầm. **PITR và on-demand backups** giải quyết nhu cầu khác hẳn.

### Throttle tại table có thể gây cascading failures

Một Lambda request nhận `ProvisionedThroughputExceededException` rồi retry nhiều lần, API Gateway timeout, client retry POST, SQS/Lambda tiêu thụ lại event và ghi trùng. Chống cascade bằng:

- End-to-end deadline/backoff.
- Idempotency ở database key/business event.
- Response 429/503 phù hợp khi từ chối tải; không hứa success giả.
- CloudWatch alarms cho table, GSI, Lambda errors và DLQ.
- Business metrics `orders_created_unique`, `orders_duplicate_ignored` và `hot_key_retry_attempts`.

## 15. Observability: CloudWatch, logs và chỉ số nghiệp vụ

| Tín hiệu | Ý nghĩa | Khi cần phản ứng |
| --- | --- | --- |
| `ConsumedReadCapacityUnits` / `ConsumedWriteCapacityUnits` | Năng lực thực sử dụng | Gần provisioned, chi phí tăng |
| `ProvisionedReadCapacityUnits` / `ProvisionedWriteCapacityUnits` | Tổng capacity đã provision | Sai sizing hoặc Auto Scaling max thấp |
| `ReadThrottleEvents` / `WriteThrottleEvents` | Các read/write requests bị throttle | Tăng bền vững và ảnh hưởng SLO |
| `ThrottledRequests` | Requests nhận throttling | So với application errors/retries |
| `SuccessfulRequestLatency` | Service-side latency cho request thành công | Truy cập chậm, hot path |
| `SystemErrors` / `UserErrors` | API error classifications | Phân biệt lỗi dịch vụ và client |
| **ThrottlingReason-specific metrics** | Chỉ ra table/index + read/write + limit type | Khoanh vùng nguyên nhân thật |
| Contributor Insights top keys | Key được access/throttled nhiều | Key schema/GSI hot |
| Application p95/p99 latency | Độ trễ người dùng thực | SLO bị ảnh hưởng dù backend retries thành công |
| SDK retry attempts | Retry overhead | Retry storm/hot key |
| DynamoDB `ReturnedItemCount`/consumed capacity logs | Hiệu quả query/read | Scan, filter sau đọc |
| Lambda Errors/Duration/Throttles | Backend reaction | Cascading failures |
| SQS queue age/DLQ | Job tồn đọng vì DynamoDB throttle | Phải giảm load trước redrive |

**Một số CloudWatch metrics được cung cấp theo tổng/average và dimension riêng**; không ép mọi metric có mọi dimension table/index. Với spike ngắn, metrics có độ trễ và độ hạt; kết hợp SDK `ThrottlingReasons` để thấy nguyên nhân tại request.

### Dashboard tối thiểu

~~~text
Top:
  requests per second, successful business writes, p95/p99 latency
  throttle count and throttle rate

Capacity:
  table/GSI consumed vs provisioned/on-demand max
  physical partition key-range throttling reasons
  warm throughput and previous peak where available

Workload:
  top hot key shapes (safely hashed)
  BatchWrite UnprocessedItems, SDK retries, Lambda concurrency
  queue backlog, DLQ, downstream API 429/503

Recovery:
  PITR enabled + Earliest/LatestRestorableDateTime
  last on-demand backup status/time
  last restore drill duration and validation result
~~~

**Bảo mật:** Throttling logs không nên chứa raw item body, plaintext secret, token hoặc partition key là email/PII. Contributor Insights có thể hiển thị primary keys; giới hạn quyền CloudWatch đọc và dùng key design không chứa dữ liệu nhạy cảm.

## 16. Lab: tạo table DynamoDB on-demand bằng CLI

> **Điều kiện:** AWS CLI v2, Region `ap-southeast-1`, profile IAM role `lab` có quyền phù hợp. Mọi table/backup/restore đều có chi phí; chỉ sử dụng account lab và dữ liệu giả, không gửi traffic đủ lớn để ảnh hưởng account quota. Dọn tài nguyên sau khi bảo đảm không còn dữ liệu cần lưu.

### 16.1. Kiểm tra identity

~~~bash
aws sts get-caller-identity \
  --profile lab

aws configure get region \
  --profile lab
~~~

### 16.2. Tạo table với composite key

~~~bash
aws dynamodb create-table \
  --table-name OrdersHotLab \
  --attribute-definitions AttributeName=PK,AttributeType=S AttributeName=SK,AttributeType=S \
  --key-schema AttributeName=PK,KeyType=HASH AttributeName=SK,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --region ap-southeast-1 \
  --profile lab
~~~

**Chỉ khai báo thuộc tính key trong `AttributeDefinitions`**. DynamoDB không yêu cầu khai báo trước tất cả attributes thường.

Chờ table sẵn sàng:

~~~bash
aws dynamodb wait table-exists \
  --table-name OrdersHotLab \
  --region ap-southeast-1 \
  --profile lab

aws dynamodb describe-table \
  --table-name OrdersHotLab \
  --region ap-southeast-1 \
  --profile lab \
  --query 'Table.{Name:TableName,Status:TableStatus,Billing:BillingModeSummary,Key:KeySchema,Arn:TableArn}'
~~~

### 16.3. Seed dữ liệu

~~~bash
aws dynamodb put-item \
  --table-name OrdersHotLab \
  --item '{"PK":{"S":"ORDER#501"},"SK":{"S":"META"},"status":{"S":"CREATED"},"amount":{"N":"120000"}}' \
  --condition-expression 'attribute_not_exists(PK)' \
  --region ap-southeast-1 \
  --profile lab
~~~

> **Shell note:** Ví dụ single quotes được viết cho Bash/macOS/Linux; Windows PowerShell có quy tắc quoting khác. Nếu gặp JSON quoting issues, tạo file JSON ngay trong dự án lab của người học rồi dùng `--item file://item.json`. Worker này **không** tạo bất kỳ file phụ nào trong module.

### 16.4. Đọc và xem consumed capacity

~~~bash
aws dynamodb get-item \
  --table-name OrdersHotLab \
  --key '{"PK":{"S":"ORDER#501"},"SK":{"S":"META"}}' \
  --consistent-read \
  --return-consumed-capacity TOTAL \
  --region ap-southeast-1 \
  --profile lab
~~~

Chạy thêm lần không có `--consistent-read`, so capacity theo yêu cầu và consistency; một mẫu đơn lẻ không dùng để suy peak throughput.

## 17. Lab: minh họa hot key mà không tạo bão tải

**Không hướng dẫn tạo lưu lượng 3.000+ writes/giây vào account thật**. Có thể dạy chính xác hiện tượng bằng **mô phỏng access pattern, phân tích toán và một ít requests an toàn**.

### Mô phỏng hai designs

**A. Unsharded counter:**

~~~json
{
  "PK": {"S": "COUNTER#PRODUCT-501"},
  "SK": {"S": "TOTAL"},
  "count": {"N": "150"}
}
~~~

Nếu 2.500 purchases/giây cùng cập nhật `count` của item đó, tất cả writes dồn vào một key. Tính đơn vị WCU theo item size và đối chiếu giới hạn partition. Đây là **phân tích trên giấy**, không chạy load thực tế.

**B. Sharded counter:**

~~~text
COUNTER#PRODUCT-501#SHARD#00
COUNTER#PRODUCT-501#SHARD#01
...
COUNTER#PRODUCT-501#SHARD#15
~~~

Mỗi purchase ghi một shard ổn định/ngẫu nhiên; tổng counter = sum của các shards. Cần xử lý duplicate purchases bằng `purchaseId` và transaction/idempotency ở writer, và lưu cache/materialized total cho dashboard nếu query fanout quá tốn.

### Kiểm thử logic

- Gửi 10–20 events giả với eventId duy nhất vào code/staging.
- Xác nhận hash-to-shard có phân phối hợp lý trên tập mẫu.
- Kiểm tra trùng eventId không tăng count lần nữa theo idempotency design.
- Đọc từng shard bằng Query và tính tổng.
- Kiểm tra retry sau timeout không làm ghi số liệu lần hai.

**Một test nhỏ không chứng minh throughput capacity production**, nhưng kiểm tra được key shape, consistency, read fanout và retry behavior trước khi load test được phê duyệt.

## 18. Quy trình kiểm tra một sự cố throttling thực tế

Giả sử error log:

~~~json
{
  "errorCode": "ThrottlingException",
  "reason": "IndexWriteMaxOnDemandThroughputExceeded",
  "resource": "arn:aws:dynamodb:ap-southeast-1:111122223333:table/OrdersHotLab/index/ByStatus",
  "requestId": "req-lab-129"
}
~~~

**Phân tích từng bước:**

1. `Index` → tài nguyên **GSI**, không phải base table.
2. `Write` → luồng cập nhật GSI từ writes đang bị chặn.
3. `MaxOnDemandThroughputExceeded` → configured max throughput của GSI, không phải physical hot partition.
4. Xác minh giới hạn GSI on-demand được thiết lập để **khống chế ngân sách**.
5. So GSI `ConsumedWriteCapacityUnits`, throttling metrics, application p99 và business request rate.
6. Chọn **giảm tải/backpressure** hoặc nâng max GSI sau khi có change approval/budget.
7. Kiểm tra có `ByStatus` hot partition **đồng thời** hay không; chỉ sửa max throughput không khắc phục hot key khác.
8. Retry có backoff + idempotency, không retry thất bại vô hạn.
9. Test lại và ghi nhận before/after.

**Ví dụ khác:** `TableWriteProvisionedThroughputExceeded` trong provisioned mode yêu cầu kiểm tra WCU/Auto Scaling của table; `TableWriteKeyRangeThroughputExceeded` yêu cầu **chẩn đoán hot keys** trước.

### Khi nào gọi AWS Support?

- Throttle kéo dài dù distribution/consumption hợp lý và đã kiểm tra metrics.
- Cần tăng service quota on-demand theo account/Region.
- Warm throughput/partition behavior không tương ứng dự kiến.
- Sự cố liên quan internal partition splits hoặc service incidents.

Cung cấp **Region, table/index ARN, request IDs, thời gian UTC, reason, metrics và scope**, không gửi plaintext data/credentials.

## 19. Migration key design khi production đã có dữ liệu

Không thể đơn giản “đổi partition key” của DynamoDB table đang có như đổi tên cột trong RDS. Thường cần **tạo table/GSI/key layout mới và di chuyển dữ liệu**.

### Kế hoạch migration an toàn

~~~mermaid
flowchart TB
    Old[(Old table schema)] --> Export[Export/Scan/Stream migration]
    Export --> New[(New sharded table)]
    App[Application] --> Mode{Migration mode}
    Mode -->|Read old, write old + new| Dual[Dual-write / outbox]
    Mode -->|Compare counts + checksums| Verify[Validate IDs, versions, aggregates]
    Verify --> Cut[Canary cutover reads/writes]
    Cut --> Full[Full cutover]
    Full --> Retire[Old table retention + cleanup approval]
~~~

**Các bước vận hành:**

1. Xác định patterns gây hot, đo `ThrottlingReasons` và key cardinality.
2. Thiết kế schema mới với `schemaVersion`, `eventId` và số shards có version.
3. Backfill bằng export/scan có giới hạn, không đè writes production hoặc làm tăng RCUs đột biến.
4. Dùng Streams/outbox/dual-write được kiểm soát để đồng bộ changes trong lúc backfill.
5. Đảm bảo updates/delete/TTL events được đồng bộ, không chỉ inserts.
6. Validate dữ liệu theo ID, counts, checksums, business constraints và sample queries.
7. Canary traffic + **shadow reads** rồi cutover theo feature flag/config.
8. Quan sát hot key throttles, p95 latency và capacity/chi phí ở schema mới.
9. Có rollback route đến bảng cũ **nếu dữ liệu vẫn đồng bộ**, không tự coi rollback config là rollback data.
10. Sau thời gian an toàn, dọn bảng cũ theo retention/backup policy.

### Điều khó nhất là dual-write

Hai DynamoDB tables không tự có một transaction nguyên tử chung cho mọi workflow phức tạp. Có thể dùng **DynamoDB transactions** trong giới hạn scope/account/Region và constraints khi phù hợp, hoặc **transactional outbox / DynamoDB Streams** để bảo đảm eventual replay. Mọi consumer/migration writer cần **idempotency**, xử lý update ordering và conflict.

**Tránh split-brain:** Không cho hai versions ứng dụng cập nhật cùng business record bằng hai key schemas mà không có source of truth và reconciliation.

## 20. Backup và restore: chọn loại nào cho loại rủi ro nào?

| Cơ chế | Mục đích | Điểm mạnh | Giới hạn cần nhớ |
| --- | --- | --- | --- |
| **DynamoDB on-demand backup** | Snapshot logic của table tại thời điểm tạo | Backup độc lập, giữ dài hạn cho tới khi bị xóa/quản lý | Không phải lịch sử theo từng giây |
| **DynamoDB PITR** | Khôi phục tới thời điểm trong **1–35 ngày** | Continuous backups, độ phân giải một giây, không cần lên lịch hàng ngày | Latest thường chậm ~5 phút, restore thành **table mới** |
| **AWS Backup for DynamoDB** | Backup plan/schedule, retention/cross-account/cross-Region | Quản trị tập trung, policies và vault | Tùy cấu hình/chi phí và quyền restore |
| **DynamoDB Global Tables** | Multi-Region reads/writes và availability theo loại global table | Khả dụng khu vực và dữ liệu replication | **Không phải backup**; xóa nhầm được replicate |
| **DynamoDB Streams** | CDC/event processing | Hỗ trợ read models/audit events trong retention | Không phải PITR hoặc full backup |
| **Export to S3** | Archival/analytics/backup data export | Tích hợp data lake, không tiêu thụ RCUs theo chức năng export | Restore về table cần import/mapping khác, không thay nguyên trạng toàn config |

### RPO/RTO phải được định nghĩa

- **RPO**: lượng dữ liệu tối đa có thể mất theo thời gian khi restore về một điểm.
- **RTO**: thời gian chấp nhận để table/restored application sẵn sàng hoạt động.

**PITR latest restorable time thường cách hiện tại khoảng 5 phút**, nên không cam kết RPO = 0 cho mọi sự cố. Restore bảng lớn có thể mất thời gian, còn cutover/reconciliation có thể dài hơn bản thân restore. Hãy đo **RTO end-to-end** bằng diễn tập thật.

## 21. PITR: liên tục, có cửa sổ thời gian, không phục hồi ghi đè

**Point-in-time recovery (PITR)** giữ continuous backups có thể dùng để khôi phục trạng thái bảng tới **một giây cụ thể** trong cửa sổ được cấu hình.

### Các trường cần biết

| Trường | Ý nghĩa |
| --- | --- |
| `PointInTimeRecoveryStatus` | `ENABLED` hoặc `DISABLED` |
| `RecoveryPeriodInDays` | **1–35 ngày**, mặc định 35 nếu không đặt |
| `EarliestRestorableDateTime` | Thời điểm xa nhất còn được restore |
| `LatestRestorableDateTime` | Thời điểm gần nhất có thể restore, **thường ~5 phút trước hiện tại** |
| `RestoreDateTime` | Thời điểm user chọn trong cửa sổ hợp lệ |
| `UseLatestRestorableTime` | Chọn thời điểm gần nhất mà service có thể khôi phục |

### Những điều dễ nhầm

1. **PITR restore luôn tạo bảng mới**, không ghi đè tại chỗ vào bảng nguồn.
2. Không phải bật `PITR` hôm nay rồi khôi phục dữ liệu từ tuần trước nếu tuần trước chưa có recovery window tương ứng.
3. Nếu **tắt rồi bật lại PITR**, cửa sổ phục hồi trước đó bị reset theo quy tắc dịch vụ; đừng tắt để tiết kiệm ngắn hạn mà không xét nhu cầu restore.
4. PITR và backup không sử dụng provisioned table RCUs/WCUs để chụp/restore theo mô hình AWS.
5. Nếu chọn timestamp sau `LatestRestorableDateTime` hoặc trước `EarliestRestorableDateTime`, restore bị từ chối.
6. PITR **phản ánh table data tại thời điểm phục hồi**, nhưng không khôi phục mọi cấu hình vận hành/IAM/alarms theo timestamp đó.
7. Với nghiệp vụ nhiều DynamoDB tables/services, restore một table **không bảo đảm causal/transactional consistency xuyên toàn hệ thống**; cần reconciliation.

### Ngữ cảnh dữ liệu bị xóa nhầm

~~~text
09:55:00 UTC  Đơn hàng bình thường
10:00:00 UTC  Script nhầm xóa 100.000 records
10:02:00 UTC  Sự cố được phát hiện
10:05:00 UTC  LatestRestorableDateTime có thể vẫn trước 10:00
                (phải xem giá trị thật của AWS)
Chọn restore timestamp hợp lệ TRƯỚC lỗi, ví dụ 09:59:50 UTC.
~~~

**Không đoán latest restorable chỉ từ đồng hồ.** Luôn đọc chính xác từ API; chọn timestamp ở UTC và document **vì sao chọn**. Giữa thời điểm restore và hiện tại còn các writes hợp lệ phải **replay/reconcile**, nếu không sẽ làm mất dữ liệu mới.

## 22. Lab: bật, kiểm tra và cảnh báo PITR

### 22.1. Bật PITR cho table lab

~~~bash
aws dynamodb update-continuous-backups \
  --table-name OrdersHotLab \
  --point-in-time-recovery-specification PointInTimeRecoveryEnabled=true,RecoveryPeriodInDays=35 \
  --region ap-southeast-1 \
  --profile lab
~~~

Lệnh làm thay đổi backup policy và có chi phí; cần quyền IAM và account lab được phê duyệt.

### 22.2. Đọc trạng thái + recovery window

~~~bash
aws dynamodb describe-continuous-backups \
  --table-name OrdersHotLab \
  --region ap-southeast-1 \
  --profile lab \
  --query 'ContinuousBackupsDescription.{Continuous:ContinuousBackupsStatus,PITR:PointInTimeRecoveryDescription}'
~~~

Kết quả minh họa:

~~~json
{
  "Continuous": "ENABLED",
  "PITR": {
    "PointInTimeRecoveryStatus": "ENABLED",
    "RecoveryPeriodInDays": 35,
    "EarliestRestorableDateTime": "2026-11-19T03:00:00+00:00",
    "LatestRestorableDateTime": "2026-11-20T03:45:00+00:00"
  }
}
~~~

**Các timestamps trên chỉ là ví dụ**. Các giá trị thực được AWS trả ở dạng timestamp và AWS CLI có thể format khác; cần sao chép **từ response thực** và bảo đảm chọn mốc trong window hợp lệ.

### 22.3. Thiết kế monitoring cho backup policy

Theo dõi/audit:

- PITR `ENABLED` cho mọi bảng production thuộc data classification cần bảo vệ.
- `RecoveryPeriodInDays` theo policy của tổ chức.
- Latest/Earliest restorable windows và sự thay đổi bất thường.
- CloudTrail của `UpdateContinuousBackups` và các thao tác backup/restore/delete.
- AWS Config/CloudWatch/AWS Backup compliance controls theo môi trường.
- Giám sát các KMS keys/grants liên quan, đặc biệt khi rotate/remove key.
- Restore drill gần nhất và trạng thái thành công; **backup tồn tại không chứng minh restore đã chạy được**.

## 23. PITR restore thực hành: luôn chọn tên table mới

> **Không chạy restore trên production nếu chưa có change approval.** Restore có thể phát sinh phí và tạo tài nguyên mới. Không dùng timestamp ví dụ nếu không nằm trong `EarliestRestorableDateTime..LatestRestorableDateTime` thực của table.

### 23.1. Khôi phục tới latest restorable time

~~~bash
aws dynamodb restore-table-to-point-in-time \
  --source-table-name OrdersHotLab \
  --target-table-name OrdersHotLab-PITR-Restore \
  --use-latest-restorable-time \
  --region ap-southeast-1 \
  --profile lab
~~~

### 23.2. Khôi phục tại mốc UTC rõ ràng

~~~bash
aws dynamodb restore-table-to-point-in-time \
  --source-table-name OrdersHotLab \
  --target-table-name OrdersHotLab-BeforeIncident \
  --restore-date-time "2026-11-20T03:00:00Z" \
  --region ap-southeast-1 \
  --profile lab
~~~

**Timestamp trên chỉ để minh họa**, phải thay mốc thực **trước sự cố** và nằm trong cửa sổ có thể restore. Chỉ một trong hai options `--restore-date-time` hoặc `--use-latest-restorable-time` được chọn theo nhu cầu.

### 23.3. Chờ bảng mới ACTIVE

~~~bash
aws dynamodb wait table-exists \
  --table-name OrdersHotLab-PITR-Restore \
  --region ap-southeast-1 \
  --profile lab

aws dynamodb describe-table \
  --table-name OrdersHotLab-PITR-Restore \
  --region ap-southeast-1 \
  --profile lab \
  --query 'Table.{Name:TableName,Status:TableStatus,Keys:KeySchema,Billing:BillingModeSummary,Indexes:GlobalSecondaryIndexes,Arn:TableArn}'
~~~

**Cẩn thận:** `wait table-exists` chỉ xác nhận table đã tồn tại theo waiter behavior; trong diễn tập, tiếp tục kiểm tra **`TableStatus=ACTIVE`** trước khi nhận production traffic. Không dùng table đang `CREATING` để so dữ liệu hoặc cutover.

### 23.4. Kiểm chứng dữ liệu

- So một tập business IDs quan trọng và counts có định nghĩa.
- Kiểm tra điều kiện uniqueness/transactions và order/payment relations.
- Kiểm tra GSI đã hoàn thành build và các query paths.
- Thử data access qua **read-only verifier** trước khi mở write.
- Đo RTO từ lúc quyết định restore đến lúc API dùng bảng mới thành công.
- Lập kế hoạch replay các writes hợp lệ sau restore timestamp; nếu bỏ qua, restored table **sẽ không tự chứa tất cả changes mới nhất**.

## 24. On-demand backup: snapshot và restore

PITR phù hợp khôi phục từng giây trong 1–35 ngày; **on-demand backup** phù hợp chụp điểm quan trọng trước migration và lưu trữ lâu dài theo retention policy.

### 24.1. Tạo backup

~~~bash
aws dynamodb create-backup \
  --table-name OrdersHotLab \
  --backup-name OrdersHotLab-before-schema-migration-20261120 \
  --region ap-southeast-1 \
  --profile lab
~~~

Lưu `BackupArn` từ response. Backup được tạo **asynchronously** và thường trở nên khả dụng sau khi xử lý; kiểm tra status trước restore.

### 24.2. Xem backup

~~~bash
aws dynamodb list-backups \
  --table-name OrdersHotLab \
  --region ap-southeast-1 \
  --profile lab

aws dynamodb describe-backup \
  --backup-arn "arn:aws:dynamodb:ap-southeast-1:111122223333:table/OrdersHotLab/backup/01234567890123-example" \
  --region ap-southeast-1 \
  --profile lab
~~~

Lệnh `describe-backup` dùng **BackupArn thực** từ `create-backup`/`list-backups`. Không copy literal ARN giả.

### 24.3. Restore backup thành bảng mới

~~~bash
aws dynamodb restore-table-from-backup \
  --target-table-name OrdersHotLab-BackupRestore \
  --backup-arn "arn:aws:dynamodb:ap-southeast-1:111122223333:table/OrdersHotLab/backup/01234567890123-example" \
  --region ap-southeast-1 \
  --profile lab
~~~

Đợi table `ACTIVE`, kiểm tra data, indexes, IAM/KMS/config và cutover giống PITR. **Backup/restore không thay đổi table nguồn** theo thao tác restore bình thường.

### 24.4. Retention và AWS Backup

- DynamoDB on-demand backups không tự hết hạn theo cùng cửa sổ PITR; cần **lifecycle/cleanup** hoặc AWS Backup plan phù hợp, tránh phí storage kéo dài.
- **AWS Backup for DynamoDB** có thể dùng policies cho lịch, retention, vault, cross-account/cross-Region backup và những controls được hỗ trợ.
- Nếu cần **long-term immutable/organizational retention**, xem AWS Backup Vault Lock/cross-account policies theo data governance.
- Tags, ABAC, KMS encryption và quyền backup/restore có quy tắc riêng; **không tự coi tags/permissions từ table được copy nguyên sang backup hoặc restored table**.

## 25. Restore xong: những cấu hình nào cần thiết lập lại?

**Restore tạo một table mới với dữ liệu tại thời điểm chọn và một số table settings được khôi phục**, nhưng **không mang nguyên vẹn toàn bộ môi trường vận hành**.

### Những thành phần data/schema cần kiểm tra

- Primary keys và table items/attributes.
- GSI/LSI/vector indexes khi hỗ trợ; xác minh **table/index status** và rebuild/restore behavior.
- Billing mode, provisioned capacity và encryption settings theo cách restore/config options.
- Index/provisioned settings có thể phản ánh **cấu hình nguồn tại thời điểm AWS quy định**, không phải lịch sử đầy đủ của từng setting tại timestamp PITR.
- Key policies/permissions của KMS customer managed key khi restore/cross-Region.
- DynamoDB item TTL attributes có thể vẫn hiện diện như dữ liệu, nhưng **TTL feature config** cần bật lại nếu cần.

### Những cấu hình thường phải dựng lại hoặc rà soát riêng

| Thành phần | Tại sao cần làm sau restore |
| --- | --- |
| **Auto Scaling policies** | Capacity không tự nhận policies đầy đủ của table cũ |
| **IAM/resource-based policies** | Table ARN mới; consumers/roles có thể không được phép |
| **CloudWatch alarms & dashboards** | Dimensions/resource references cũ |
| **CloudWatch Contributor Insights** | Cần bật/đánh giá bảo mật trên restored table |
| **Tags** | Restore không tự bảo toàn tags theo docs |
| **DynamoDB Streams settings** | Không tự giả định Streams được bật/có stream ARN cũ |
| **TTL settings** | Cần cấu hình lại nếu workload dựa vào expiration |
| **PITR settings** | Restored table cần bật PITR lại theo policy |
| **Deletion protection** | Cần kiểm tra và bật theo policy |
| **EventBridge Pipes/Lambda mappings** | Stream/table ARNs thay đổi, mappings phải được review |
| **VPC endpoints/IAM KMS network paths** | Kết nối/authorization vẫn phải đúng với resource mới |
| **Application table config** | Hardcoded table name hoặc ARN không tự đổi |
| **Global Tables replication** | Restore mới không tự là thành viên global table hiện tại theo mọi kịch bản |

**Quan trọng:** Không bật `Streams` rồi kỳ vọng tự tái phát toàn bộ historical stream events của table cũ. Sau PITR, nếu downstream cần backfill read models, phải lên kế hoạch **scan/export/reconciliation** hoặc replay events từ nguồn bền vững.

### Restore target nên tách traffic cho tới khi kiểm chứng

Một runbook tốt giữ restored table ở **quarantine/read-only verification** (thông qua quyền IAM và feature flags), sau đó mới cutover/canary. Tránh để ứng dụng tự chạy writes mới vào restored table khi indexes/mappings/backup chưa hoàn thiện.
## 26. Cutover sang table đã khôi phục: tránh làm mất các writes hợp lệ

**Restore thành công không đồng nghĩa production tự được khôi phục.** Vì table mới có tên/ARN mới và dữ liệu tại một mốc quá khứ, việc đổi app config thiếu quy trình có thể gây mất những cập nhật hợp lệ sau mốc đó.

### Các giai đoạn cutover

~~~mermaid
flowchart TB
    Incident[Sự cố: dữ liệu bị xóa / hỏng] --> Contain[Chặn destructive writes, lưu bằng chứng]
    Contain --> Point[Chọn PITR timestamp / backup ARN]
    Point --> Restore[(Restore to NEW DynamoDB table)]
    Restore --> Check[Verify keys, items, GSIs, IAM/KMS, TTL, PITR]
    Check --> Reconcile[Replay / reconcile valid writes after restore]
    Reconcile --> Canary[Canary reads / writes có kiểm soát]
    Canary --> Decide{Data + SLO + security pass?}
    Decide -->|Có| Cutover[Cutover application table config]
    Decide -->|Không| Hold[Giữ bảng mới isolated và điều tra]
    Cutover --> Monitor[Theo dõi consistency, errors, lag, cost]
    Monitor --> Cleanup[Backup/retire old table có approval]
~~~

### Vấn đề writes nằm sau restore timestamp

Giả sử:

~~~text
09:59:50Z   PITR restore point được chọn
10:00:00Z   Script xóa nhầm 100.000 rows
10:01:00Z   User tạo 200 orders hợp lệ ở source table
10:05:00Z   Incident response khóa ghi
10:20:00Z   Restored table ACTIVE tại trạng thái 09:59:50Z
~~~

Bảng khôi phục **không chứa 200 orders hợp lệ sau 09:59:50Z**. Không thể đơn giản đổi `TABLE_NAME` sang bảng mới và coi hệ thống đã hoàn tất phục hồi.

Cần một hoặc nhiều chiến lược theo kiến trúc:

- **Write-ahead/business event log** hoặc transactional outbox có đủ events để replay các thao tác hợp lệ sau mốc restore.
- So sánh **source table hiện tại** với restored table để chọn lọc rows hợp lệ và invalid updates, có khóa version/timestamp/actor để phân biệt.
- Replay idempotent, có thứ tự theo entity khi cần.
- Tạm ngừng writes hoặc đưa vào SQS buffer trong cutover window (có timeouts/DLQ/capacity).
- Chạy **read verification** và một đợt canary writes có cơ chế rollback.
- Ghi rõ những records không thể xác minh và quy trình điều tra thủ công.

**Không đơn giản “scan source rồi copy đè restored table”**, vì có thể đưa lại dữ liệu đã xóa nhầm hoặc ghi đè phiên bản chuẩn bằng trạng thái bị hỏng.

### Không rollback ứng dụng mù quáng

Nếu chuyển app sang table mới rồi lại rollback sang table cũ sau 30 phút, hai tables có thể đã diverge. Rollback config **không rollback data**. Trước khi mở dual writes hoặc chuyển lại, phải có source of truth và reconciliation logic.

## 27. Global Tables, cross-Region backup và disaster recovery

### 27.1. Global Tables phục vụ availability, không thay PITR

**DynamoDB Global Tables** phân phối dữ liệu giữa các Regions theo mô hình được hỗ trợ, giúp ứng dụng đọc/ghi gần người dùng và tiếp tục hoạt động khi có regional incident theo DR design.

~~~mermaid
flowchart LR
    Asia[Users Asia] --> RegionA[(DynamoDB Region A)]
    RegionA <-->|Global Tables replication| RegionB[(DynamoDB Region B)]
    Europe[Users Europe] --> RegionB
    RegionA --> BackupA[PITR / AWS Backup Region A]
    RegionB --> BackupB[PITR / AWS Backup Region B]
~~~

**Các vấn đề phải phân biệt:**

- Global Tables replication là **đồng bộ dữ liệu ứng dụng theo mô hình dịch vụ**, không phải backup bất biến.
- Nếu user/script xóa nhầm nhiều items, các deletions có thể **replicate sang các Regions khác**.
- Với **MREC Global Tables** thông thường, cross-Region replication mang tính eventual và conflict resolution theo mô hình; không hứa strong consistency cross-Region.
- DynamoDB cũng có lựa chọn **multi-Region strong consistency (MRSC)** cho những Regions/topology/tính năng được hỗ trợ. Không coi mọi Global Table là MRSC và không thiết kế dựa vào MRSC khi chưa kiểm tra constraints của tài khoản/Region.
- Global table replication và PITR/on-demand backups cần **recovery strategy riêng**, kể cả khi có nhiều replicas.

### 27.2. Backup cross-Region/cross-account

Với những yêu cầu compliance/DR, đánh giá **AWS Backup** để:

- Lập backup plan theo lịch/retention.
- Copy recovery points qua account/Region hỗ trợ.
- Dùng backup vault, resource policies và KMS keys phù hợp.
- Kiểm soát quyền tạo, xóa, copy, restore độc lập với application roles.
- Có quy trình test restore trong account/Region dự phòng.

**Không mặc định tài khoản DR đã đủ quyền KMS decrypt/restore** chỉ vì backup copy thành công; key policies, resource ARN, backup vault access và IAM roles của account đích phải được kiểm chứng.

### 27.3. DR runbook tối thiểu

1. Kiểm tra incident là **Region outage** hay **logical corruption**.
2. Region outage nhưng dữ liệu vẫn đúng → chọn Global Tables failover/traffic routing theo chiến lược.
3. Logical corruption replicated → **không dùng global replica bị corrupt làm nguồn truth**; dùng PITR hoặc backup an toàn.
4. Quarantine writes nếu cần, lưu CloudTrail/operation logs và chọn recovery point.
5. Restore/cutover, replay valid writes, kiểm chứng RPO/RTO.
6. Điều chỉnh Route 53/API Gateway/Lambda configs/IAM/KMS/VPC endpoints cho Region phục hồi.
7. Kiểm tra idempotency, conflict resolution và network/client retry.
8. Có kế hoạch failback, re-establish replication và cleanup có approval.

**RPO/RTO cuối cùng phải được đo bằng diễn tập nhiều thành phần**, không chỉ tính thời gian API `RestoreTableToPointInTime` trả về.

## 28. IAM, KMS, VPC và bảo vệ bản sao lưu

### 28.1. IAM cho ứng dụng và cho vận hành

Ứng dụng bình thường nên chỉ cần API data plane như `GetItem`, `Query`, `PutItem`, `UpdateItem`, `DeleteItem` trên table/index đúng nhu cầu.

**Không cấp cho application runtime quyền**:

- `dynamodb:DeleteTable`
- `dynamodb:RestoreTableToPointInTime`
- `dynamodb:RestoreTableFromBackup`
- `dynamodb:UpdateContinuousBackups`
- `dynamodb:DeleteBackup`

Các API quản trị backup/restore phải nằm ở **operator/backup service role** có MFA/change approval/audit khi phù hợp.

Policy ví dụ cho consumer đọc table lab:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadOrdersTable",
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:Query",
        "dynamodb:DescribeTable"
      ],
      "Resource": [
        "arn:aws:dynamodb:ap-southeast-1:111122223333:table/OrdersHotLab",
        "arn:aws:dynamodb:ap-southeast-1:111122223333:table/OrdersHotLab/index/*"
      ]
    }
  ]
}
~~~

Tách role readers, writers, deployers, backup admins. **Một role chỉ có `GetItem` không thể tự restore table**; đó là nguyên tắc least privilege có chủ đích.

### 28.2. AWS KMS

DynamoDB dùng encryption at rest; tùy compliance có thể chọn **AWS owned key, AWS managed key hoặc customer managed KMS key**. Với customer managed key:

- Giới hạn key administration và key usage.
- Xác minh KMS key còn active/khả dụng cho restore và cross-Region backup plan.
- Đảm bảo backup vault/customer-managed key policy và target table encryption phù hợp.
- Tránh vô hiệu hóa/xóa KMS key khi còn backup, table hoặc restore phụ thuộc.
- CloudTrail audit các thao tác liên quan đến khóa theo khả năng cấu hình.

### 28.3. VPC endpoint

Lambda/ECS/EC2 chạy trong private VPC muốn gọi DynamoDB API có thể dùng:

- **Gateway VPC endpoint cho DynamoDB** qua route tables và endpoint policies theo Region; hoặc
- network egress được phê duyệt theo kiến trúc.

**DynamoDB API sử dụng HTTPS/443**. Không có “database port 5432/3306” để kết nối trực tiếp tới DynamoDB như RDS. DynamoDB table không chạy trong private subnet của bạn; endpoint giúp **private resource trong VPC truy cập API** phù hợp.

### 28.4. Encryption không thay authorization

Dữ liệu mã hóa ở rest vẫn có thể bị xóa nếu principal có `DeleteItem`/`DeleteTable` hoặc được gọi bằng API credentials hợp lệ. Để bảo vệ chống thao tác xóa phá hoại:

- Least privilege, conditions/tags phù hợp, resource-based policies và SCP.
- **Deletion protection** trên tables quan trọng theo hỗ trợ.
- PITR và AWS Backup/Vault policies.
- CloudTrail/audit, alarms khi PITR bị tắt hoặc table bị delete.
- Separate backup administrator role/account và quy trình change control.

## 29. Chi phí: hot partitions có thể làm mất tiền cả hai hướng

DynamoDB có những khoản chi phí chính:

| Thành phần | Cost driver |
| --- | --- |
| **On-demand reads/writes** | RRUs/WRUs tiêu thụ theo item size/consistency |
| **Provisioned table/GSI capacity** | RCU/WCU configured (và auto scaling output) |
| **Storage** | Table + indexes data size |
| **GSI** | Index storage + write/read throughput |
| **PITR** | Continuous backup theo dung lượng được bảo vệ; recovery period cấu hình không mặc nhiên giảm giá theo số ngày |
| **On-demand backups** | Backup storage và restore operations |
| **AWS Backup** | Backup vault/copy/cold tiers/restore theo tính năng |
| **Global Tables** | Replicated writes/storage/cross-region components theo loại Global Table |
| **Export/Import to S3** | Data export/import, S3 storage/requests |
| **CloudWatch/Contributor Insights** | Metrics, Contributor Insights rules, logs/alarms |
| **Lambda/ECS/SQS/DAX** | Compute, queues, retries, cache |
| **KMS/network** | KMS API calls/key usage, VPC endpoints/traffic theo config |

### Throttle tốn tiền như thế nào?

Một hot key có thể khiến:

- SDK retry nhiều, Lambda duration tăng, client timeout rồi lại gửi request.
- Cùng một transaction bị tính nhiều lần ở downstream nếu thiếu idempotency.
- WCU/GSI capacity provisioned cao nhưng unused vì một key bottleneck.
- Cache miss storm làm read request units tăng mạnh.
- SQS backlog lớn, DLQ/re-drive và alert costs tăng.

**Một cải tiến key design có thể rẻ hơn gấp nhiều lần việc tăng tổng WCU**, nhưng cần tính thêm fanout reads và migration costs.

### Mô hình ước lượng

\[
C_{\text{monthly}} \approx C_{\text{throughput}}
+ C_{\text{table+GSI storage}}
+ C_{\text{PITR/backup}}
+ C_{\text{restore drills}}
+ C_{\text{Global Tables}}
+ C_{\text{compute+monitoring+KMS}}
\]

Đừng bịa giá USD cố định cho mọi Region. Dùng **AWS Pricing Calculator**, **Cost Explorer**, **AWS Budgets** và tagging; so chi phí trên **một business operation thành công** thay vì chỉ giá một request.

## 30. Troubleshooting: đọc triệu chứng trước khi thay capacity

| Triệu chứng | Nguyên nhân có khả năng | Hành động |
| --- | --- | --- |
| Table capacity còn dư nhưng write throttle | Hot key/physical partition | `TableWriteKeyRangeThroughputExceeded`, key cardinality, Contributor Insights |
| Base table khỏe nhưng PutItem chậm/lỗi | GSI write back-pressure | `IndexWrite...` reason + index ARN + GSI metrics |
| Provisioned table throttle gần mức RCU/WCU | Provisioned capacity thấp | Tối ưu query, tăng provisioned, Auto Scaling min/max |
| On-demand workload spike 10× | Previous peak/warm throughput thiếu | Pre-warm/ramp-up, throttle metrics |
| On-demand bị throttle dù key phân bố tốt | Account limit / configured max | `AccountLimitExceeded` / `MaxOnDemandThroughputExceeded` |
| `BatchWriteItem` HTTP 200 nhưng thiếu records | Có `UnprocessedItems` | Retry riêng unprocessed với backoff, lưu thất bại bền vững |
| SDK retries quá lâu | Max attempts/deadline quá cao | Retry strategy, timeout, queue/backpressure |
| GSI Query quá tốn RCUs | Key design/Scan/FilterExpression sai | Query KeyCondition, pagination, projection/index design |
| Adaptive capacity không giải quyết key nóng | Một item cực nóng, LSI/monotonic sort key | Sharding/aggregation, revise model |
| Backup tồn tại nhưng không restore được | KMS/IAM/backup status/ARN sai | DescribeBackup, key policy, admin role |
| PITR không có timestamp muốn chọn | Ngoài Earliest/Latest window hoặc PITR vừa bật | DescribeContinuousBackups, recovery period |
| Restore được nhưng app vẫn đọc bảng cũ | Hardcoded table name/env/ARN | Config cutover, deployment/feature flag |
| Restored table thiếu stream/TTL | Cấu hình không được restore tự động | Enable Streams/TTL và mapping lại |
| GSI không query được ngay sau restore | Index đang build, thiếu GSI/config | DescribeTable/index status, test query |
| IAM AccessDenied sau restore | Table ARN mới, ABAC tags chưa áp | Update policies/tags, review IAM |
| PITR đã bật nhưng báo không có dữ liệu gần hiện tại | LatestRestorableDateTime trễ ~5 phút | Chọn mốc hợp lệ, reconcile newer writes |
| Restore có dữ liệu cũ nhưng thiếu orders mới | Timestamp chọn trước writes hợp lệ | Replay events/outbox, reconcile |
| Global Tables vẫn có dữ liệu bị xóa nhầm | Logical deletion replicated | PITR/backup, không dùng replica như backup |
| Restore mất nhiều thời gian hơn SLO | Bảng lớn, index build, cutover/reconciliation | Restore drill, RTO, DR runbook, capacity plans |
| PITR bị tắt ngoài dự kiến | Configuration drift/permission issues | CloudTrail, AWS Config, backup policy guardrail |
| CloudWatch Contributor Insights hiển thị PII | Primary keys chứa dữ liệu nhạy cảm | Key redesign/IAM/review trước khi bật |
| Chi phí tăng dù QPS không tăng | Item size/GSI/retries/backup/streams | Cost Explorer, SDK consumed capacity, table size |

### Quy trình điều tra 10 bước

~~~text
1. Xác nhận account, Region, table ARN và GSIs.
2. Lấy DynamoDB exception + ThrottlingReasons + request ID.
3. Phân loại Table/Index, Read/Write, KeyRange/Provisioned/Account/MaxOnDemand.
4. Đọc CloudWatch + workload shape (Query/Scan/Batch/size/consistency).
5. Nếu KeyRange, tìm hot key qua Contributor Insights hoặc app metrics.
6. Nếu GSI, xem write back-pressure và index partition key design.
7. Áp dụng backoff/jitter + idempotency + concurrency cap để giảm tác động.
8. Chọn solution dài hạn: sharding, cache, index redesign, capacity mode.
9. Nếu data corruption: xác minh PITR window/backup, restore new table,
   reconcile/cutover; không xóa nguồn trước kiểm chứng.
10. Đo lại throughput, throttle rate, p99 latency, RPO/RTO, chi phí.
~~~

## 31. Kiến trúc thực tế: flash sale có thể phục hồi sau lỗi

~~~mermaid
flowchart TB
    Users[Web/Mobile] --> Gateway[API Gateway]
    Gateway --> Lambda[Lambda Order API]
    Lambda --> Limit[Per-tenant rate limiter]
    Limit --> DDB[(DynamoDB Orders with good PK)]
    Lambda --> Queue[(SQS OrderEvents)]
    DDB --> Stream[DynamoDB Streams]
    Stream --> Enrich[EventBridge Pipes / Lambda]
    Enrich --> ReadModel[(Read model / aggregates)]
    DDB --> PITR[PITR 1-35 days]
    DDB --> Backup[AWS Backup / recovery vault]
    PITR --> Restore[(New restored table)]
    Backup --> Restore
    DDB --> CloudWatch[CloudWatch metrics + alarm]
    Lambda --> CloudWatch
    Queue --> CloudWatch
~~~

### Trước flash sale

- Kiểm tra hot keys ở table và GSIs; tránh `PK=EVENT#TODAY` một giá trị.
- Tính WCU/RCU theo item size, dự báo traffic bursts và warm throughput.
- Kiểm tra on-demand previous peak hoặc provisioned Auto Scaling min/max, account quota.
- Load test được duyệt với concurrency cap, staging/canary data.
- Bật PITR, xác minh backup policy, IaC và alarms.

### Trong flash sale

- Giám sát `ThrottlingReasons`, GSI back-pressure, SDK retries và p95/p99.
- Ưu tiên business commands/critical reads.
- Có backpressure: API rate limit, SQS buffer, bounded retries.
- Tạm giảm analytics Scan/costly queries khi cần.
- Dùng idempotency để không ghi trùng đơn khi client retry.

### Sau sự cố

- Nếu chỉ throttling: chẩn đoán hot key/capacity, chưa cần restore.
- Nếu data corruption: cô lập lỗi, chọn PITR/backup trước mốc xóa nhầm.
- Restore **table mới**, xác minh key/index/tags/permissions.
- Replay valid writes và chuyển app qua feature flag/canary.
- Ghi lại RTO/RPO, dữ liệu cần reconcile và nguyên nhân gốc.

**Không dùng restore để “sửa” throttling do partition key xấu.** Bảng mới giữ nguyên key model gây hot nếu không thay đổi data schema.

## 32. Case study A — Counter của sản phẩm bán chạy

**Dữ kiện:**

- Table provisioned 15.000 WCUs.
- Mỗi purchase update một item `PK=PRODUCT#X, SK=COUNTER`.
- 2.000 purchases/giây, item <1KB.
- `TableWriteKeyRangeThroughputExceeded` tăng, tổng consumed WCU chỉ khoảng vài nghìn.

**Phân tích:** Không phải provisioned 15.000 WCU thiếu; một item cần ~2.000 writes/giây vào một key vượt khả năng partition. Adaptive capacity không thể vượt trần physical partition của item.

**Giải pháp:**

1. Xác định idempotency theo `purchaseId` để một purchase không tăng counter hai lần.
2. Tạo **16 shards** cho count (hoặc kiến trúc event aggregation phù hợp), phân phối writes.
3. Query sum shards phục vụ số liệu gần realtime, cache aggregated total.
4. Kiểm tra mất/thừa purchases bằng SQS/event log và reconciliation.
5. Đo write throttle, unique successful purchase count, read cost và latency.

**Tại sao không chỉ thêm GSI?** GSI trên trạng thái/tên sản phẩm không thay cách writes cập nhật cùng một hot item.

## 33. Case study B — Xóa nhầm dữ liệu từ batch job

**Dữ kiện:**

- 09:00 UTC batch job dùng sai filter và xóa 30.000 orders.
- PITR enabled từ tháng trước, window 35 ngày.
- 09:03 UTC phát hiện lỗi, đã có một số orders mới hợp lệ từ 09:00–09:03.
- Doanh nghiệp yêu cầu khôi phục dữ liệu bị xóa mà không mất orders mới.

**Runbook gợi ý:**

1. Disable job/credentials gây lỗi, giữ logs/CloudTrail và snapshot state.
2. Describe PITR để xác minh mốc `08:59:55Z` có nằm trong recovery window.
3. Restore new table `OrdersBeforeIncident`; chưa cutover ngay.
4. So sánh ID/versions giữa bảng restore và source; phân loại 30.000 orders bị xóa và các orders mới.
5. Nếu còn nguồn events/outbox, replay valid writes sau `08:59:55Z` **theo thứ tự và idempotent**; kiểm tra status transitions.
6. Bảo đảm tags/IAM/KMS/TTL/streams/PITR/alarms/indexes cho bảng mới.
7. Canary query/business operations; chọn phương án selective repair hoặc full cutover đã được review.
8. Ghi lại **RPO thực đạt, RTO thực**, những giao dịch không thể khôi phục tự động.
9. Duy trì bằng chứng và backup cũ theo retention; dọn tài nguyên theo approval.

**Bài học:** PITR phục hồi bản dữ liệu quá khứ nhưng không tự biết thao tác nào sau đó là hợp lệ. **Reconciliation** mới bảo đảm business continuity.

## 34. Bài tập thực hành và tự kiểm tra

### Bài tập 1 — Phân tích capacity units

Item kích thước 6 KB, read strong vs eventual vs transactional. Hãy tính RCUs tương ứng; đối chiếu `ceil(6/4)`. Một write item 2,2 KB tiêu thụ bao nhiêu WCU, và vì sao transaction write tốn hơn?

### Bài tập 2 — Table chưa hết WCU nhưng vẫn throttle

Table provisioned 20.000 WCU; một hot partition key nhận 1.800 writes/giây, mỗi item ≤1KB. Error reason `TableWriteKeyRangeThroughputExceeded`.

**Yêu cầu:** Vì sao tăng WCU lên 40.000 chưa chắc giải quyết? Thiết kế write sharding 16 buckets, mô tả cost query fanout và idempotency.

### Bài tập 3 — GSI hot

Base table PK là order UUID phân bố đều, nhưng GSI PK=`status` chỉ có `NEW`/`PAID`/`FAILED`. Logs cho thấy `IndexWriteKeyRangeThroughputExceeded`.

**Yêu cầu:** Chỉ ra source ARN có `/index/...` và đề xuất GSI key mới có tenant/time/shard; mô tả cách query paging/merging.

### Bài tập 4 — On-demand throttling

Một on-demand table có request spike lớn trong <30 phút, trước đó chạy ít tải. ThrottlingReasons lần lượt là `TableReadAccountLimitExceeded` và `TableReadMaxOnDemandThroughputExceeded` trên hai môi trường.

**Yêu cầu:** Phân biệt service quota và user-defined max; đề xuất warm throughput/peak ramp-up, kiểm soát ngân sách và khi nào cần quota increase.

### Bài tập 5 — Batch partial success

`BatchWriteItem` gửi 20 PutRequests nhưng `UnprocessedItems` chứa 4 requests.

**Yêu cầu:** Viết pseudocode chỉ retry 4 items với backoff+jitter, deadline, DLQ và metrics; giải thích vì sao HTTP 200 không đủ, và vì sao BatchWriteItem không phải nơi kiểm tra unique constraints.

### Bài tập 6 — PITR timestamp

`EarliestRestorableDateTime=2026-11-19T00:00:00Z`, `LatestRestorableDateTime=2026-11-20T03:45:00Z`. Script xóa nhầm lúc `2026-11-20T03:00:00Z`.

Hãy chọn timestamp hợp lệ **trước sự cố**, chỉ ra lý do `2026-11-20T03:50:00Z` không hợp lệ, viết lệnh `restore-table-to-point-in-time` với tên target table mới.

### Bài tập 7 — Restore xong nhưng ứng dụng lỗi

Restored table có dữ liệu và GSI, nhưng API Lambda trả `AccessDeniedException`, consumer Streams không nhận events, TTL không xóa items.

**Yêu cầu:** Liệt kê IAM/resource policy/table ARN mới, Streams configuration/ARN/mapping, TTL settings, tags, alarms và PITR cần thiết lập lại.

### Bài tập 8 — DR và Global Tables

Một ứng dụng dùng DynamoDB Global Tables hai Regions. Một operator xóa nhầm toàn bộ `TENANT#A` ở Region A, deletion replicate sang B.

**Yêu cầu:** Vì sao Region B không phải backup? Chọn PITR/AWS Backup và quy trình restore/reconciliation, cross-Region KMS/IAM, failover traffic và old data fencing.

### Bài tập 9 — Chi phí

Ứng dụng sau migration có 4 triệu eventual reads/ngày, 500 nghìn writes/ngày, ba GSIs, PITR 35 ngày, AWS Backup weekly và CloudWatch Contributor Insights.

**Yêu cầu:** Lập cost model theo item size, consistency, GSI write amplification, PITR table size, retention, backups, logs, KMS và retries. Không gán một giá USD cố định khi chưa biết Region.

### 15 câu hỏi ngắn

1. **Hot partition là gì?** Partition/key range nhận quá nhiều read/write traffic so với throughput xử lý.
2. **Có thể hot ngay cả khi table còn capacity?** Có, do giới hạn physical partition.
3. **Khoảng 1 partition chịu bao nhiêu WCU/RCU?** Thường 1.000 WCU hoặc 3.000 RCU/giây theo AWS.
4. **GSI có thể throttle writes base table không?** Có, do GSI write back-pressure.
5. **Adaptive capacity có tự bật không?** Có.
6. **Adaptive capacity có vượt trần một partition không?** Không.
7. **On-demand có bao giờ throttle không?** Có, hot partition/peak/quotas/configured max.
8. **`ThrottlingReasons` quan trọng hơn exception name?** Có; nó chỉ resource và loại limit.
9. **`FilterExpression` có tiết kiệm RCU cho items đã đọc?** Không.
10. **`BatchWriteItem` HTTP 200 chứng minh tất cả items đã ghi?** Không; cần xem UnprocessedItems.
11. **PITR giữ được dữ liệu tối đa bao nhiêu ngày?** 35, configurable 1–35.
12. **PITR có restore ghi đè source table không?** Không; luôn tạo table mới.
13. **`LatestRestorableDateTime` có thường là ngay giây hiện tại không?** Không, thường chậm khoảng 5 phút.
14. **Global Tables có thay backup/PITR không?** Không; xóa nhầm cũng có thể replicate.
15. **Restore table mới có tự giữ tất cả TTL/Streams/tags/PITR/alarms không?** Không; phải cấu hình/kiểm tra lại.

## 35. Checklist trước production

- [ ] Đã đánh giá access patterns và partition key/cardinality của **table và mọi GSIs**.
- [ ] Có thể phân biệt hot item, hot key range, provisioned throughput, account limits và configured on-demand max.
- [ ] Có logging của **ThrottlingReasons + resource ARN** nhưng không lộ sensitive primary keys/payloads.
- [ ] Có CloudWatch consumed/provisioned/throttled/latency metrics theo table/index và SLO.
- [ ] Có Contributor Insights khi phù hợp bảo mật/chi phí, theo dõi most accessed/throttled keys.
- [ ] Đã tính RCU/WCU theo item size và consistency; không lạm dụng Scan/FilterExpression.
- [ ] Đã xem adaptive capacity/split-for-heat, LSI restrictions và monotonic sort-key limitations.
- [ ] Hot write counter hoặc low-cardinality GSI đã có giải pháp sharding/aggregation phù hợp.
- [ ] Read sharding có giới hạn fanout/concurrency, paging, merge-sort và idempotency.
- [ ] Đã chọn on-demand/provisioned đúng traffic, warm throughput/previous peak và Auto Scaling/quotas.
- [ ] Có backoff+jitter, bounded attempts/deadline, API throttling và SQS backpressure.
- [ ] Có xử lý BatchWrite UnprocessedItems/BatchGet UnprocessedKeys, business unique keys.
- [ ] Có PITR `ENABLED` cho bảng cần bảo vệ và window recovery period được phê duyệt.
- [ ] On-demand backups/AWS Backup có schedule, retention, vault/cross-account/Region policy theo yêu cầu.
- [ ] Có alert khi PITR bị disable, table deletion, backup/restore failure hoặc quyền backup bị thay đổi.
- [ ] Đã kiểm chứng `EarliestRestorableDateTime`/`LatestRestorableDateTime` và UTC timestamps.
- [ ] Có **restore drill vào table mới**, xác nhận dữ liệu, indexes, status ACTIVE, RTO/RPO thực đo.
- [ ] Sau restore có checklist IAM/ABAC/tags, KMS, autoscaling, TTL, Streams, alarms, PITR, deletion protection.
- [ ] Có kế hoạch replay/reconciliation của valid writes sau PITR timestamp, không copy corrupt data mù quáng.
- [ ] Application cutover dùng feature flag/config, canary, rollback **cùng chiến lược dữ liệu**.
- [ ] Global Tables/Region DR có thể xử lý delete replicate, conflict và cross-Region network/iam/kms.
- [ ] Database runtime IAM least privilege tách biệt backup/restore/deletion permission.
- [ ] DynamoDB VPC gateway endpoint/routes/policies hoặc egress bảo đảm HTTPS.
- [ ] Có AWS Budgets, Cost Explorer và tags cho throughput, GSI storage, PITR, backups, logs, KMS.
- [ ] Đã diễn tập hot partition, GSI throttling, batch partial failure, PITR restore và Region recovery.
- [ ] Runbooks có owner, change approval, metrics cần xem, data validation và cleanup sau incident.

## 36. Tổng kết

**Hot partition và throttling** là bài toán phân phối tải đúng với **partition key và GSI key**, kết hợp sizing capacity và retry có giới hạn. Một table có nhiều RCUs/WCUs nhưng bị dồn writes vào một item vẫn có thể throttle. Cần đọc **`ThrottlingReasons` và ARN**, phân biệt **KeyRange / Provisioned / AccountLimit / MaxOnDemand**, rồi chọn đúng giải pháp: **key redesign, write sharding, caching, warm throughput, scaling hoặc quota increase**.

**Backup và khôi phục** là bài toán khác: **PITR 1–35 ngày** giúp chọn thời điểm phục hồi với độ phân giải giây; **on-demand backups** hỗ trợ các snapshot lưu giữ lâu hơn; **AWS Backup** quản lý lịch/retention/copy/vault. **Restore luôn tạo bảng mới**, nên phải kiểm chứng dữ liệu, thiết lập lại các cấu hình còn thiếu và **replay/reconcile các writes hợp lệ** trước khi cutover. **Global Tables không thay backup** vì lỗi/xóa nhầm có thể được replicate.

Một hệ thống DynamoDB vận hành tốt kết hợp **data modeling, idempotency, giới hạn tải, IAM/KMS/VPC, CloudWatch/Contributor Insights, PITR, backup drills và AWS Budgets** để vừa chịu được flash sale vừa khôi phục được sau sai sót vận hành.

### Tài liệu AWS chính thức

- [DynamoDB partitions and partition keys](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.Partitions.html)
- [Adaptive capacity and burst capacity](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/burst-adaptive-capacity.html)
- [Key design best practices](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-partition-key-design.html)
- [Write sharding data modeling](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/data-modeling-blocks.html)
- [Troubleshooting DynamoDB throttling](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/TroubleshootingThrottling.html)
- [Throttling reasons diagnostic workflow](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/throttling-diagnosing-workflow.html)
- [Key range throttling mitigation](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/throttling-key-range-limit-exceeded-mitigation.html)
- [GSI write throttling and back pressure](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/gsi-throttling.html)
- [On-demand capacity mode](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/on-demand-capacity-mode.html)
- [Warm throughput](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/warm-throughput.html)
- [CloudWatch Contributor Insights DynamoDB](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/contributorinsights_HowItWorks.html)
- [DynamoDB CloudWatch metrics](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/metrics-dimensions.html)
- [DynamoDB error handling and batch retries](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Programming.Errors.html)
- [AWS SDK Java v2 retry strategies](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/retry-strategy.html)
- [DynamoDB backup and restore overview](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Backup-and-Restore.html)
- [DynamoDB on-demand backups](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/CreateBackup.html)
- [DynamoDB point-in-time recovery](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Point-in-time-recovery.html)
- [Enable PITR](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/PointInTimeRecovery_Howitworks.html)
- [Restore DynamoDB table](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/pointintimerecovery_restores.html)
- [RestoreTableToPointInTime API](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_RestoreTableToPointInTime.html)
- [DynamoDB with AWS Backup](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/GettingStartedBackupsAWS.html)
- [DynamoDB Global Tables](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/GlobalTables.html)
- [DynamoDB pricing](https://aws.amazon.com/dynamodb/pricing/)
- [AWS CLI DynamoDB reference](https://docs.aws.amazon.com/cli/latest/reference/dynamodb/)

**Lưu ý vận hành:** Các hạn mức throughput, giá, on-demand scaling, warm throughput, Global Tables consistency modes, AWS SDK defaults và hành vi restore có thể thay đổi. Đối chiếu hướng dẫn AWS hiện hành theo **engine feature, Region và account của bạn**, thử trên account lab trước khi thay table production hoặc quyết định RPO/RTO.




