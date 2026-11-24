# Partition key trong message flow với Apache Cassandra và Spring Integration

## 1. Bài toán: message đi đúng luồng nhưng Cassandra vẫn chậm

Một ứng dụng nhận sự kiện `OrderPaid` từ HTTP hoặc JMS, đưa vào Spring Integration `MessageChannel` rồi lưu vào Apache Cassandra. Ban đầu mọi thứ chạy tốt với vài nghìn sự kiện mỗi ngày. Khi một khách hàng lớn phát sinh hàng triệu sự kiện, một số Cassandra nodes báo timeout, độ trễ p99 tăng mạnh và backlog của JMS bắt đầu tích tụ. Thêm consumer hoặc tăng thread pool không giải quyết được vấn đề, thậm chí làm cluster quá tải nhanh hơn.

Nguyên nhân có thể nằm ở **partition key**: tất cả sự kiện của khách hàng đó bị ghi vào cùng một Cassandra partition quá rộng, hoặc workload không được phân bố đều giữa các token ranges/nodes.

Trong Cassandra, **partition key quyết định nhóm dữ liệu cùng partition và ảnh hưởng đến vị trí lưu/định tuyến request**. Trong Spring Integration, một **message key** có thể chỉ là header để router/aggregator hoặc Kafka/JMS sử dụng. Hai khái niệm liên quan đến nhau về mặt thiết kế nhưng **không tự đồng nhất**. Nếu không lập hợp đồng rõ, message được chuyển thành công qua channel mà Cassandra vẫn ghi sai partition hoặc mất tính đúng đắn của truy vấn.

Bài **Partition key trong message flow**, thuộc chương **Adapter Cassandra** của module **SPRING_INTEGRATION_ADAPTERS**, giải thích cách thiết kế khóa để kết nối hệ thống ngoài bằng inbound/outbound adapter, gateway, poller và `MessageChannel`; thực hành hợp đồng message, lỗi và vòng đời kết nối với JMS, Kafka, HTTP cùng Cassandra.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **Cassandra partition key**, **clustering columns**, **full primary key**, **Kafka partition key**, **JMS message group** và Spring message headers.
2. Thiết kế bảng Cassandra theo **query pattern**, phân bố workload và giới hạn kích thước partition.
3. Dùng **composite partition key** và **time bucketing/sharding** đúng ràng buộc đọc, ghi, ordering.
4. Mapping `@PrimaryKeyClass`, `@PrimaryKeyColumn`, `PrimaryKeyType.PARTITIONED/CLUSTERED` với Spring Data Cassandra.
5. Xây Spring Integration flow từ message hợp lệ tới Cassandra outbound adapter hoặc gateway.
6. Giữ khóa ổn định qua retry/redelivery, tránh nhầm sự kiện trùng và bảo vệ ordering/idempotency.
7. Đo hotspots, partition size, latency, backlog; xây integration tests trên Cassandra thật.

## 2. Ba loại khóa dễ bị gọi chung là “partition key”

| Khái niệm | Nằm ở đâu? | Mục đích chính | Có tự đồng bộ với Cassandra không? |
|---|---|---|---|
| **Cassandra partition key** | CQL schema, `PRIMARY KEY` | Chọn partition, tính token, xác định replica placement | Là **đích lưu**, không đến từ Spring header một cách tự động |
| **Kafka record key** | Kafka record metadata, thường `KafkaHeaders.KEY` trong Spring | Chọn Kafka partition theo partitioner, hỗ trợ ordering theo partition | **Không**; cần transformer/mapper rõ ràng |
| **JMS `JMSXGroupID`** | JMS message property khi broker hỗ trợ message groups | Gắn message group để giảm nguy cơ nhiều consumer xử lý cùng group đồng thời | **Không**; không quyết định Cassandra token |
| **Spring `correlationId`** | `MessageHeaders` | Ghép các message trong aggregator/request flow | **Không**; có thể là UUID của flow chứ không phải business ID |
| **Business `eventId`** | Payload contract | Định danh sự kiện qua producer retry, broker redelivery và DLQ replay | Chỉ khi mapping thành PK/unique mechanism phù hợp |
| **Business `aggregateId/orderId`** | Payload contract | Gom các sự kiện cùng đơn hàng, bảo vệ version/ordering | Chỉ khi schema hoặc routing dùng nó một cách tường minh |

Một ứng dụng có thể chọn **cùng khóa nghiệp vụ** làm Kafka key và một phần Cassandra partition key để giảm độ phức tạp về ordering, nhưng **không được suy ra** hai hệ sẽ cùng số partition, cùng thuật toán hash, cùng node hoặc cùng thứ tự vật lý.

### 2.1. Sơ đồ đi từ sự kiện tới hai dạng partition

~~~mermaid
flowchart LR
    A["OrderPaid event: tenantId, orderId, eventId, occurredAt"] --> B["Spring Integration validation/transform"]
    B --> C["MessageHeaders: routing/tracing/key hint"]
    C --> D["Kafka/JMS message metadata nếu có"]
    B --> E["Entity / BoundStatement có đủ CQL primary key fields"]
    E --> F["Cassandra partition key: tenantId + orderId + month"]
    F --> G["Murmur3 token / partitioner"]
    G --> H[("Replica nodes và partition data")]
    D -. "Không tự tạo CQL partition key" .-> E
~~~

**Điểm quan trọng:** Cassandra nhận CQL write có partition-key values qua entity hoặc statement. Broker headers có thể mang cùng `tenantId`/`orderId`, nhưng Cassandra **không đọc JMS/Kafka header** nếu flow không map chúng vào CQL.

## 3. Cấu trúc CQL `PRIMARY KEY`

Trong Cassandra, full primary key gồm **partition key** và, nếu có, **clustering columns**.

~~~sql
CREATE TABLE IF NOT EXISTS shop_integration.events_by_order_month (
    tenant_id text,
    order_id text,
    bucket_month text,
    occurred_at timestamp,
    event_id text,
    event_type text,
    payload_json text,
    PRIMARY KEY (
        (tenant_id, order_id, bucket_month),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (
    occurred_at DESC,
    event_id ASC
);
~~~

Phân tích:

- `(tenant_id, order_id, bucket_month)` là **composite partition key**. Cả ba giá trị kết hợp định danh một Cassandra partition.
- `occurred_at` và `event_id` là **clustering columns**. Chúng sắp xếp các hàng **bên trong partition** và cùng tạo tính duy nhất của row.
- Full primary key là `(tenant_id, order_id, bucket_month, occurred_at, event_id)`, **không chỉ** ba partition columns.
- `event_type` và `payload_json` là regular columns; chúng **không quyết định** token/placement.

Ví dụ ba rows:

~~~text
partition = (tenant-42, ORD-9001, 2026-11)
    occurred_at=2026-11-23T03:02:00Z, event_id=evt-03
    occurred_at=2026-11-23T03:01:00Z, event_id=evt-02
    occurred_at=2026-11-23T03:00:00Z, event_id=evt-01

partition = (tenant-42, ORD-9001, 2026-12)
    occurred_at=2026-12-01T00:01:00Z, event_id=evt-04

partition = (tenant-42, ORD-9002, 2026-11)
    occurred_at=2026-11-23T03:03:00Z, event_id=evt-05
~~~

Trong một partition, `occurred_at DESC` giúp trả sự kiện mới trước. **Không có thứ tự toàn cục giữa các Cassandra partitions**, và clustering order **không phải bảo đảm** rằng message được xử lý nghiệp vụ theo thứ tự khi nhiều consumers ghi đồng thời.

### 3.1. Dấu ngoặc kép có ý nghĩa trong PRIMARY KEY

So sánh:

~~~sql
-- Chỉ tenant_id là partition key; order_id, event_id là clustering.
PRIMARY KEY (tenant_id, order_id, event_id)

-- tenant_id + order_id là composite partition key; event_id là clustering.
PRIMARY KEY ((tenant_id, order_id), event_id)

-- Toàn bộ ba cột tạo composite partition key; không có clustering.
PRIMARY KEY ((tenant_id, order_id, event_id))
~~~

Ba khai báo trên có tính chất **distribution và query** khác nhau. Việc thiếu một cặp ngoặc trong migration có thể khiến một khách hàng lớn bị gom vào một partition khổng lồ.

### 3.2. Partition key khác clustering key về mục đích

| Thuộc tính | Partition key | Clustering column |
|---|---|---|
| Quyết định token/replica | **Có** | Không |
| Gom rows cùng partition | **Có** | Sắp xếp/định danh rows trong partition |
| Truy vấn hiệu quả | Thường cần biết đầy đủ partition key | Có thể range/order theo quy tắc clustering |
| Làm nóng một partition nếu chọn key kém | **Có** | Không sửa được skew của partition key |
| Số lượng unique keys tăng | Tăng số partitions | Tăng số rows trong cùng partition |
| Đổi sau khi tạo bảng | Cần chiến lược migration/table mới | Cũng là phần schema PK, không tùy ý UPDATE |

**Tính đúng đắn:** các cột primary key không được đổi như một regular column trong UPDATE. Muốn chuyển một event từ bucket sai sang bucket đúng, thường cần **ghi row ở khóa mới** rồi xử lý xóa/cleanup row cũ theo kế hoạch; không có phép `UPDATE bucket_month = ...` đổi primary key trực tiếp.

## 4. Token-aware routing và replica placement

Với **Murmur3Partitioner** thông dụng, Cassandra tính token từ bytes của **toàn bộ partition key**. Composite key có serialization và thứ tự cột được xác định bởi schema; không phải nối đơn giản bằng dấu `-` rồi hash text.

~~~mermaid
flowchart TD
    K["partition key tuple"] --> H["Partitioner: tính token"]
    H --> R["Token ranges trong ring"]
    R --> P["Replication strategy + topology"]
    P --> N1[("Replica node A")]
    P --> N2[("Replica node B")]
    P --> N3[("Replica node C")]
    D["Token-aware Java driver"] --> H
    D --> C["Chọn coordinator phù hợp"]
    C --> N1
~~~

Các node trong sơ đồ chỉ minh họa một replication topology. Với RF=1 hoặc nhiều datacenters, số replicas và placement có thể khác. Một partition lưu nhiều rows nhưng được replica trên **một tập nodes** theo strategy; nó không được chia ngẫu nhiên cho mọi node chỉ vì có nhiều clustering rows.

### 4.1. Token-aware routing phụ thuộc câu lệnh bind đủ key

Driver có thể xác định routing key khi:

1. Prepared statement có metadata nhận diện partition-key columns.
2. Người gọi bind đúng kiểu/đủ các partition values.
3. Driver dùng token-aware load balancing policy và cluster metadata phù hợp.

Khi không có đủ metadata hoặc key không được bind, driver vẫn có thể gửi request tới coordinator, nhưng **không được kỳ vọng token-aware routing tối ưu**.

### 4.2. Vì sao Cassandra partition key khác Kafka key?

Kafka partitioner ánh xạ record key tới **Kafka topic partition**, có thể chịu ảnh hưởng của cấu hình partition count/partitioner/version. Cassandra phân vùng dữ liệu theo **token range + replication strategy** và keyspace schema. Cùng chuỗi `orderId="ORD-9001"` không tạo mối quan hệ một-một giữa Kafka partition 5 và Cassandra node A.

Nếu Kafka topic tăng số partitions, một số record keys có thể được map lại theo partitioner mới; nếu Cassandra cluster thay đổi nodes/token ranges, replica placement có thể đổi. Do đó **đừng lấy số Kafka partition làm tham số phân vùng Cassandra** nếu không có một hợp đồng dữ liệu được phân tích rõ.

## 5. Thiết kế key theo truy vấn trước, không theo tên trường

Cassandra được thiết kế theo **query-driven data modeling**: xác định các câu hỏi phải trả lời, rồi chọn partition/clustering key. Một event có thể được lưu ở **nhiều bảng phục vụ nhiều query patterns**; denormalization là một chiến lược có chủ đích, không tự là lỗi.

### 5.1. Ba câu hỏi nghiệp vụ khác nhau

| Query | Partition key khả dĩ | Cần clustering? | Rủi ro |
|---|---|---|---|
| Tìm đúng một event theo `eventId` | `(event_id)` | Không | Phải có bảng lookup riêng nếu bảng timeline dùng key khác |
| Lấy sự kiện mới nhất của một order trong tháng | `(tenant_id, order_id, bucket_month)` | `occurred_at DESC, event_id` | Truy vấn nhiều tháng phải fan-out nhiều partitions |
| Lấy mọi sự kiện tenant trong ngày | `(tenant_id, bucket_day)` | `occurred_at` | Tenant lớn dễ tạo wide/hot partition |
| Theo dõi lỗi theo một status | Không nên chỉ dùng status cardinality thấp | Tùy mục tiêu | Một partition `status='ERROR'` có thể quá nóng |

Một partition key lý tưởng phải **phục vụ đúng truy vấn**, có phân bố phù hợp và tạo các partitions có kích thước quản lý được. Chỉ chọn một UUID ngẫu nhiên làm key có thể phân bố tốt nhưng **không phù hợp** truy vấn theo orderId/time.

### 5.2. Cặp bảng cho cùng một nguồn sự kiện

~~~sql
-- Lookup trực tiếp một event.
CREATE TABLE IF NOT EXISTS shop_integration.event_by_id (
    event_id text PRIMARY KEY,
    tenant_id text,
    order_id text,
    occurred_at timestamp,
    payload_json text
);

-- Timeline per-order theo tháng (đã khai báo ở mục 3).
-- shop_integration.events_by_order_month
~~~

Đọc theo `eventId` dùng `event_by_id`; đọc timeline theo order+month dùng `events_by_order_month`. **Hai bảng không được Cassandra tự commit atomically như một ACID transaction liên-bảng mặc định.** Nếu ghi hai bảng từ cùng event, cần chiến lược retry/idempotency và xử lý trường hợp một ghi thành công còn ghi kia thất bại.

## 6. Bucketing theo thời gian: giữ partition hữu hạn

Một order ít sự kiện có thể dùng `(tenant_id, order_id)` làm partition key và `occurred_at` làm clustering. Nhưng một “aggregate” rất lớn, dữ liệu IoT/log hoặc đơn hàng có hàng triệu changes có thể khiến partition phình theo thời gian. **Time bucketing** thêm `bucket_month` hoặc `bucket_day` vào partition key để giới hạn dữ liệu trong một partition.

~~~text
Không bucket:
  (tenant-42, device-08) -> toàn bộ dữ liệu nhiều năm

Bucket theo tháng:
  (tenant-42, device-08, 2026-09)
  (tenant-42, device-08, 2026-10)
  (tenant-42, device-08, 2026-11)

Bucket theo ngày (mật độ cao):
  (tenant-42, device-08, 2026-11-21)
  (tenant-42, device-08, 2026-11-22)
  (tenant-42, device-08, 2026-11-23)
~~~

### 6.1. Tính bucket bằng timezone cố định

Nếu nguồn gửi `occurredAt` dạng `Instant`, tính bucket bằng **UTC** hoặc timezone đã được quy định trong contract:

~~~java
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;

public final class PartitionBuckets {
    private static final DateTimeFormatter MONTH =
            DateTimeFormatter.ofPattern("uuuu-MM");

    private PartitionBuckets() {}

    public static String utcMonth(Instant occurredAt) {
        if (occurredAt == null) {
            throw new IllegalArgumentException("occurredAt is required");
        }
        return MONTH.format(occurredAt.atOffset(ZoneOffset.UTC));
    }
}
~~~

Ví dụ `2026-11-30T23:59:59Z` thuộc `2026-11`, còn `2026-12-01T00:00:00Z` thuộc `2026-12`. **Không dùng `LocalDate.now()` hoặc timezone mặc định của máy consumer** để tính bucket: khi message được replay vào tháng khác hoặc chạy ở node khác timezone, nó sẽ chuyển sang partition khác, phá định danh event.

### 6.2. Bucket size không có đáp án chung

Giả sử một thiết bị phát 600 sự kiện/phút, payload trung bình khoảng 1 KiB chỉ tính JSON:

~~~text
600 events/phút × 60 × 24 = 864.000 events/ngày.
Payload JSON xấp xỉ 843,75 MiB/ngày (864.000 KiB) trước overhead/index/replication.
~~~

Một bucket **mỗi ngày** như vậy vẫn có thể quá rộng/hot. Ngược lại một thiết bị phát một sự kiện/ngày mà bucket theo phút sẽ tạo quá nhiều partitions nhỏ. Cần đo:

- Số rows/cells trung bình và p99 trong một partition.
- Kích thước thực trên đĩa (data + tombstones + overhead).
- Mức read/write throughput vào một partition key.
- TTL/retention, compaction, clustering scan và repair.
- Số partitions cần đọc khi truy vấn một khoảng thời gian.

Apache Cassandra đưa ra **khuyến nghị tổng quát** thường cố gắng giữ partitions dưới khoảng **100.000 values/cells và 100 MB**; đây **không phải hard limit áp cho mọi workload**. Kích thước phù hợp cần được benchmark cùng cluster, schema, payload và query plan.

## 7. Hot partition và kỹ thuật sharding có kiểm soát

Time bucketing giới hạn kích thước theo thời gian nhưng **không tự phân bổ writes trong một khoảng thời gian**. Nếu tenant `tenant-42` ghi 50.000 events/giây vào `(tenant-42, 2026-11-23)`, tất cả các write trong ngày vẫn đi tới **cùng một partition key**. Thêm clustering column `event_id` làm các rows khác nhau nhưng **không chia tải ra nhiều tokens**.

### 7.1. Một thiết kế có thể tạo hot partition

~~~sql
CREATE TABLE shop_integration.events_by_tenant_day (
    tenant_id text,
    bucket_day date,
    occurred_at timestamp,
    event_id text,
    event_type text,
    PRIMARY KEY ((tenant_id, bucket_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
~~~

Truy vấn theo tenant+day rất tự nhiên nhưng có thể gây **skew**: tenant nhỏ vài events/ngày, tenant lớn hàng triệu events/ngày. Không nên chọn schema chỉ dựa trên dữ liệu trung bình.

### 7.2. Thêm shard vào composite partition key

~~~sql
CREATE TABLE shop_integration.events_by_tenant_day_shard (
    tenant_id text,
    bucket_day date,
    shard tinyint,
    occurred_at timestamp,
    event_id text,
    event_type text,
    PRIMARY KEY (
        (tenant_id, bucket_day, shard),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
~~~

Giả sử `shard` nhận các giá trị 0–15, một tenant/ngày có tối đa **16 partition keys** (không phải 16 Cassandra nodes). Các partition keys được hash ra tokens, tạo cơ hội phân bố writes tốt hơn. **Không có bảo đảm 16 shards sẽ nằm trên 16 nodes riêng** hoặc throughput tăng đúng 16 lần.

Đổi lại, để đọc **tất cả events trong ngày của tenant**, cần query các shards liên quan, sau đó merge/sort kết quả nếu cần một timeline duy nhất. Sharding giải quyết write skew bằng **trade-off đọc phức tạp hơn**.

### 7.3. Chọn shard bằng thuật toán ổn định

Nếu chọn shard theo `eventId`, phải dùng một hàm hash **ổn định giữa ngôn ngữ và các lần replay**. Ví dụ tối giản với SHA-256 và 16 shards:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

public final class StableShards {
    private StableShards() {}

    public static int shard16(String eventId) {
        if (eventId == null || eventId.isBlank()) {
            throw new IllegalArgumentException("eventId is required");
        }
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(eventId.getBytes(StandardCharsets.UTF_8));
            return (digest[0] & 0xff) % 16;
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }
}
~~~

Thuật toán ở đây **không phải Cassandra Murmur3 token**. Nó chỉ tạo một trường shard có phân bố tương đối đều, sau đó Cassandra lại hash **toàn bộ composite partition key** theo partitioner. Mọi producer/consumer/backfill phải dùng **chính cùng thuật toán và số shards**.

**Quan trọng:** tự đổi 16 thành 32 shards sau deploy mà không version hóa/migrate dữ liệu sẽ khiến cùng `eventId` có thể được ghi vào shard mới khác với shard cũ. Khi cần mở rộng, thiết kế `shard_scheme_version`, migrate/read cả schema cũ và mới, hoặc dùng table mới với chiến lược chuyển đổi được kiểm soát.

### 7.4. Shard theo event có thể phá ordering theo order

Nếu các events `OrderCreated`, `OrderPaid`, `OrderCancelled` của cùng `orderId` có `eventId` khác nhau, chúng có thể rơi vào **ba Cassandra shards**. Timeline sẽ không còn nằm trong một partition. Muốn giữ mọi sự kiện của một order trong cùng một partition, phải chọn key chứa `orderId` và bucket phù hợp, hoặc một shard function **theo orderId** (mà khi đó một order cực nóng vẫn có thể là điểm nghẽn).

**Không có một partition key vừa tối ưu mọi loại read vừa phân tán mọi ghi:** cần cân bằng truy vấn, tải, ordering và chi phí duy trì bảng.

## 8. Hợp đồng message phải mang đủ các thành phần của partition key

Một input event dùng làm nguồn dữ liệu:

~~~json
{
  "eventId": "evt-5001",
  "tenantId": "tenant-42",
  "orderId": "ORD-9001",
  "eventType": "OrderPaid",
  "schemaVersion": 1,
  "occurredAt": "2026-11-23T03:00:00Z",
  "payload": {"amountMinor": 250000, "currency": "VND"}
}
~~~

Trong bảng `events_by_order_month`, một key đầy đủ cần:

~~~text
tenant_id     <- tenantId
order_id      <- orderId
bucket_month  <- UTC month của occurredAt
occurred_at   <- occurredAt
event_id      <- eventId
~~~

**Không lấy khóa từ dữ liệu tạm thời** như current JVM clock, số thứ tự delivery của broker hoặc random UUID sinh trong mỗi consumer attempt.

### 8.1. Phân biệt khóa nghiệp vụ và thông tin chỉ phục vụ routing

| Trường | Contract | Dùng ở Cassandra? | Mục đích |
|---|---|---|---|
| `eventId` | Bất biến qua retry/replay | Clustering trong timeline; partition key của lookup table | Business deduplication |
| `tenantId` | Được xác thực từ producer/context | Partition component | Tenant isolation và query scope |
| `orderId` | Bất biến, thuộc tenant | Partition component | Timeline theo đơn |
| `occurredAt` | Timestamp sự kiện, có quy ước timezone | Clustering + nguồn tính bucket | Order lịch sử và bucketing |
| `bucketMonth` | Được tính hoặc kiểm chứng từ `occurredAt` | Partition component | Giới hạn partition theo tháng |
| `schemaVersion` | Contract serializer | Regular column hoặc header | Versioned deserialization |
| `JMSMessageID` | Provider-generated | Chỉ lưu cho audit nếu có | Không thay `eventId` |
| `KafkaHeaders.RECEIVED_PARTITION` | Metadata Kafka consumer | Không mặc định | Quan sát broker partition, không phải Cassandra partition |

### 8.2. Dữ liệu thiếu khóa phải fail trước Cassandra

Giả sử `orderId` rỗng hoặc `occurredAt` không parse được. Đừng tự đưa tất cả errors về một bucket `"unknown"`: điều đó có thể tạo **hot partition**, rò dữ liệu cross-tenant và làm truy vấn sai.

Nên validate:

1. `eventId` duy nhất/ổn định và đúng format đã quy định.
2. `tenantId` và `orderId` không rỗng, có độ dài hợp lý, đúng quyền sender.
3. `occurredAt` có timezone/format và nằm trong giới hạn thời gian chấp nhận (có chính sách cho late events).
4. `bucketMonth` được **tính lại từ timestamp** hoặc kiểm tra chéo với trường producer gửi.
5. `schemaVersion` được hỗ trợ và payload không vượt giới hạn bytes.

Một event lỗi contract nên đi vào **quarantine/đường lỗi** theo thiết kế, không ghi dữ liệu với partition key “dự phòng” thiếu kiểm soát.

### 8.3. Key không nên là bí mật

Partition key xuất hiện trong CQL statements, logs, tracing, monitoring và có thể lộ qua công cụ vận hành. Không đặt token xác thực, password hoặc dữ liệu nhạy cảm không cần thiết vào key. `tenantId` phải được xác thực bằng service identity/authorization; một header do client tự khai báo không đủ làm bằng chứng quyền truy cập.

## 9. Spring Data Cassandra: mapping composite partition key

Spring Data Cassandra hỗ trợ **`@PrimaryKeyClass`** cùng `@PrimaryKeyColumn` để phân biệt partition columns và clustering columns. Với bảng `events_by_order_month` ở mục 3, cấu hình rõ `ordinal` và `type` của từng field.

### 9.1. Key class có đầy đủ equals/hashCode

~~~java
import java.io.Serializable;
import java.time.Instant;
import java.util.Objects;
import org.springframework.data.cassandra.core.cql.Ordering;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyType;

@PrimaryKeyClass
public class OrderTimelineKey implements Serializable {

    private static final long serialVersionUID = 1L;

    @PrimaryKeyColumn(name = "tenant_id", ordinal = 0,
            type = PrimaryKeyType.PARTITIONED)
    private String tenantId;

    @PrimaryKeyColumn(name = "order_id", ordinal = 1,
            type = PrimaryKeyType.PARTITIONED)
    private String orderId;

    @PrimaryKeyColumn(name = "bucket_month", ordinal = 2,
            type = PrimaryKeyType.PARTITIONED)
    private String bucketMonth;

    @PrimaryKeyColumn(name = "occurred_at", ordinal = 3,
            type = PrimaryKeyType.CLUSTERED, ordering = Ordering.DESCENDING)
    private Instant occurredAt;

    @PrimaryKeyColumn(name = "event_id", ordinal = 4,
            type = PrimaryKeyType.CLUSTERED, ordering = Ordering.ASCENDING)
    private String eventId;

    public OrderTimelineKey() {}

    public OrderTimelineKey(
            String tenantId, String orderId, String bucketMonth,
            Instant occurredAt, String eventId) {
        this.tenantId = tenantId;
        this.orderId = orderId;
        this.bucketMonth = bucketMonth;
        this.occurredAt = occurredAt;
        this.eventId = eventId;
    }

    public String getTenantId() { return tenantId; }
    public void setTenantId(String tenantId) { this.tenantId = tenantId; }

    public String getOrderId() { return orderId; }
    public void setOrderId(String orderId) { this.orderId = orderId; }

    public String getBucketMonth() { return bucketMonth; }
    public void setBucketMonth(String bucketMonth) { this.bucketMonth = bucketMonth; }

    public Instant getOccurredAt() { return occurredAt; }
    public void setOccurredAt(Instant occurredAt) { this.occurredAt = occurredAt; }

    public String getEventId() { return eventId; }
    public void setEventId(String eventId) { this.eventId = eventId; }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof OrderTimelineKey key)) return false;
        return Objects.equals(tenantId, key.tenantId)
                && Objects.equals(orderId, key.orderId)
                && Objects.equals(bucketMonth, key.bucketMonth)
                && Objects.equals(occurredAt, key.occurredAt)
                && Objects.equals(eventId, key.eventId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(
                tenantId, orderId, bucketMonth, occurredAt, eventId);
    }
}
~~~

Theo Spring Data Cassandra, **`@PrimaryKeyClass` cần `Serializable` và value equality semantics**. Các `ordinal` sắp xếp key columns theo thứ tự CQL; đặt `PARTITIONED` cho cả ba cột trước, `CLUSTERED` cho hai cột sau.

**Không đánh đồng `equals/hashCode` của Java với Cassandra token hash:** Java equality dùng cho entity identity và map/repository code, còn Cassandra token do partitioner tính trên serialized partition key. Việc hai thuật toán hash khác nhau là bình thường.

### 9.2. Entity dùng @PrimaryKey

~~~java
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("events_by_order_month")
public class OrderTimelineEvent {

    @PrimaryKey
    private OrderTimelineKey key;

    @Column("event_type")
    private String eventType;

    @Column("payload_json")
    private String payloadJson;

    public OrderTimelineEvent() {}

    public OrderTimelineEvent(
            OrderTimelineKey key, String eventType, String payloadJson) {
        this.key = key;
        this.eventType = eventType;
        this.payloadJson = payloadJson;
    }

    public OrderTimelineKey getKey() { return key; }
    public void setKey(OrderTimelineKey key) { this.key = key; }

    public String getEventType() { return eventType; }
    public void setEventType(String eventType) { this.eventType = eventType; }

    public String getPayloadJson() { return payloadJson; }
    public void setPayloadJson(String payloadJson) {
        this.payloadJson = payloadJson;
    }
}
~~~

`@Table` chỉ định target table, `@PrimaryKey` gắn composite key class, `@Column` đặt mapping regular fields. Spring Data sẽ map partition/clustering fields từ `OrderTimelineKey` vào CQL columns.

### 9.3. Converter: từ event sang entity

~~~java
import java.time.Instant;
import java.time.temporal.ChronoUnit;

public record OrderEvent(
        String eventId,
        String tenantId,
        String orderId,
        String eventType,
        int schemaVersion,
        Instant occurredAt,
        String payloadJson) {}

public final class TimelineMapper {

    private TimelineMapper() {}

    public static OrderTimelineEvent toEntity(OrderEvent event) {
        if (event == null
                || event.eventId() == null || event.eventId().isBlank()
                || event.tenantId() == null || event.tenantId().isBlank()
                || event.orderId() == null || event.orderId().isBlank()
                || event.occurredAt() == null) {
            throw new IllegalArgumentException(
                    "OrderEvent thiếu trường khóa bắt buộc");
        }

        // Cassandra timestamp lưu đến millisecond; chuẩn hóa key trước khi ghi.
        Instant canonicalTime = event.occurredAt()
                .truncatedTo(ChronoUnit.MILLIS);
        String bucketMonth = PartitionBuckets.utcMonth(canonicalTime);

        OrderTimelineKey key = new OrderTimelineKey(
                event.tenantId(),
                event.orderId(),
                bucketMonth,
                canonicalTime,
                event.eventId());

        return new OrderTimelineEvent(
                key, event.eventType(), event.payloadJson());
    }
}
~~~

Ví dụ này giả định `schemaVersion` đã được validator kiểm tra trước khi convert. Không tự loại bỏ `schemaVersion` khỏi hợp đồng ứng dụng chỉ vì bảng timeline chưa có cột lưu nó; nếu cần điều tra schema migration, hãy bổ sung cột/metadata tương ứng theo policy.

**Quy tắc trọng tâm:** tạo key **một cách deterministic từ business event**. Khi cùng event được redeliver, transformer phải tạo **cùng tenantId/orderId/bucketMonth/occurredAt/eventId**; nếu chỉ đổi `eventId` hoặc bucket theo current time, Cassandra sẽ xem đây là **row khác**.

Trong ví dụ, `occurred_at` dùng CQL `timestamp` có độ chính xác millisecond; `Instant` từ Java có thể chứa nanosecond. Mapper chuẩn hóa bằng `truncatedTo(MILLIS)` để so sánh key trong Java, Cassandra và các lần đọc lại nhất quán hơn. **Contract xuyên ngôn ngữ cũng cần thống nhất độ chính xác timestamp**, không chỉ timezone.

## 10. Java DSL: từ MessageChannel tới Cassandra outbound adapter

Spring Integration Cassandra (từ 6.0) cung cấp `Cassandra.outboundChannelAdapter(operations, Type.INSERT)`. Adapter dùng `CassandraMessageHandler` và `ReactiveCassandraOperations` của Spring Data Cassandra; nó **không** nhận imperative `CqlTemplate` trực tiếp.

### 10.1. Dependency tối thiểu cho lab

~~~xml
<!-- Giả định Spring Boot BOM quản lý các versions tương thích. -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-cassandra</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-cassandra-reactive</artifactId>
</dependency>
~~~

Ví dụ `application.yml` cho Cassandra test node:

~~~yaml
spring:
  cassandra:
    contact-points: 127.0.0.1
    port: 9042
    local-datacenter: datacenter1
    keyspace-name: shop_integration
~~~

Địa chỉ, datacenter và keyspace phải khớp cluster thật. Keyspace/test table cần được provision trước bằng migration/test setup. Đừng dùng `SimpleStrategy/replication_factor=1` của lab cho production multi-datacenter.

### 10.2. Flow nhận OrderEvent và tạo Cassandra entity

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.cassandra.outbound.CassandraMessageHandler;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
public class OrderTimelineIntegrationConfiguration {

    @Bean
    public IntegrationFlow orderEventsToCassandra(
            ReactiveCassandraOperations operations) {

        return IntegrationFlow.from("validatedOrderEvents")
                .transform(OrderEvent.class, TimelineMapper::toEntity)
                .handle(Cassandra.outboundChannelAdapter(
                                operations, CassandraMessageHandler.Type.INSERT),
                        endpoint -> endpoint.async(false))
                .get();
    }
}
~~~

Ở đây `validatedOrderEvents` nhận Spring Message có **payload kiểu `OrderEvent`**; transformer tạo entity với composite key; adapter viết Cassandra theo Spring Data mapping. `endpoint.async(false)` khiến handler chờ kết quả operation trong đường gọi đồng bộ, phù hợp cho lab/nhận lỗi rõ ràng. Theo Spring Integration, **mặc định handler async=true**; `async(false)` không tự tạo transaction giữa Cassandra và JMS/Kafka.

**Adapter là một chiều:** không gửi kết quả CQL quay lại flow chỉ vì source Spring Message có `replyChannel`. Nếu cần kết quả SELECT/LWT hoặc xác nhận write ở một downstream stage, hãy dùng Cassandra **outbound gateway** có reply contract phù hợp.

### 10.3. Tạo và gửi message từ service

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class OrderEventFlowPublisher {

    private final MessageChannel validatedOrderEvents;

    public OrderEventFlowPublisher(
            @Qualifier("validatedOrderEvents")
            MessageChannel validatedOrderEvents) {
        this.validatedOrderEvents = validatedOrderEvents;
    }

    public void publish(OrderEvent event) {
        boolean accepted = validatedOrderEvents.send(
                MessageBuilder.withPayload(event)
                        .setHeader("eventId", event.eventId())
                        .setHeader("tenantId", event.tenantId())
                        .setHeader("orderId", event.orderId())
                        .build());
        if (!accepted) {
            throw new IllegalStateException("No subscriber accepted event");
        }
    }
}
~~~

Message headers trên đây **phục vụ tracing/định tuyến Spring**, không phải nguồn dữ liệu Cassandra mặc định. `TimelineMapper` đọc payload; kể cả nếu header `tenantId` bị gắn sai thì key vẫn lấy từ `OrderEvent.tenantId()`. Ứng dụng phải kiểm tra **header và payload không mâu thuẫn**, nhất là khi header do gateway bên ngoài cung cấp.

`send(true)` chỉ cho biết cách bàn giao/handler được cấu hình đã hoàn tất theo semantics của channel. Khi channel bất đồng bộ hoặc Cassandra handler ở mode mặc định async, caller **không thể suy ra Cassandra đã commit write** chỉ từ boolean này.

## 11. Truy vấn theo partition key và kết quả của bucketing

### 11.1. Truy vấn một partition

~~~sql
SELECT event_id, event_type, occurred_at, payload_json
FROM shop_integration.events_by_order_month
WHERE tenant_id = 'tenant-42'
  AND order_id = 'ORD-9001'
  AND bucket_month = '2026-11'
LIMIT 50;
~~~

Query chỉ định **đủ ba partition-key columns**. Vì bảng được tạo với `CLUSTERING ORDER BY (occurred_at DESC, event_id ASC)`, các rows trong cùng partition được lưu/phục vụ theo clustering order; query giới hạn 50 events mới nhất **trong bucket**.

Kết quả **không tự gồm events ở tháng 10 hoặc tháng 12**. Caller muốn timeline xuyên ba tháng phải xác định những buckets cần đọc và ghép các kết quả một cách có kiểm soát.

### 11.2. Truy vấn một khoảng thời gian trong một bucket

~~~sql
SELECT event_id, event_type, occurred_at
FROM shop_integration.events_by_order_month
WHERE tenant_id = ?
  AND order_id = ?
  AND bucket_month = ?
  AND occurred_at >= ?
  AND occurred_at < ?
LIMIT 100;
~~~

Các dấu `?` được bind theo đúng thứ tự. Range predicate nằm trên **clustering column đầu tiên** `occurred_at`. Một client muốn có timeline trên nhiều buckets nên **query từng bucket cần thiết**, có giới hạn concurrency, paging và merge theo sort key rõ ràng.

### 11.3. Không thể lọc tùy ý một phần composite partition key

Đối với bảng có `PRIMARY KEY ((tenant_id, order_id, bucket_month), ...)`, truy vấn:

~~~sql
-- Không phải query đúng partition; thường không được hỗ trợ hiệu quả.
SELECT * FROM events_by_order_month
WHERE tenant_id = 'tenant-42';
~~~

`tenant_id` chỉ là **một phần** của composite partition key, không đủ xác định token và partition. Cassandra có thể từ chối query thiếu các thành phần khóa hoặc yêu cầu một cơ chế scan/filter tốn kém. **Không dùng `ALLOW FILTERING` làm giải pháp mặc định**: hãy thiết kế bảng dành riêng cho truy vấn theo tenant nếu đó là use case thật.

### 11.4. Query nhiều buckets: fan-out có giới hạn

~~~mermaid
flowchart LR
    Q["Tra cứu order ORD-9001 trong 90 ngày"] --> B1["Bucket 2026-09"]
    Q --> B2["Bucket 2026-10"]
    Q --> B3["Bucket 2026-11"]
    B1 --> M["Merge theo occurredAt DESC + eventId"]
    B2 --> M
    B3 --> M
    M --> R["Page kết quả và cursor an toàn"]
~~~

Nếu mỗi bucket cần một CQL query, không nên song song hàng trăm requests không giới hạn chỉ vì API cho phép. Hãy chọn **maximum lookback window**, giới hạn số buckets mỗi lần truy vấn, xác định cursor/continuation rules và memory cap.

**Time bucketing làm read phức tạp hơn nhưng giữ partitions có thể quản lý được.** Đây là một trade-off chủ động, không phải sai lầm cần sửa bằng một truy vấn `IN` khổng lồ.

### 11.5. Debug token trên Cassandra

Trên cluster test có dữ liệu:

~~~sql
SELECT token(tenant_id, order_id, bucket_month)
FROM shop_integration.events_by_order_month
WHERE tenant_id = 'tenant-42'
  AND order_id = 'ORD-9001'
  AND bucket_month = '2026-11'
LIMIT 1;
~~~

`token(...)` giúp quan sát token ứng với **composite partition key** theo partitioner thực tế. Không hash thủ công chuỗi `"tenant-42:ORD-9001:2026-11"` rồi khẳng định nó là Cassandra token; Cassandra serialize các key components theo protocol/type/schema.

Nếu partition trống, query trên bảng trả **không có row**, không có nghĩa token “không tồn tại” về mặt toán học. Trong lab có thể tạo row trước khi kiểm tra. Mỗi node/replica có thể được xác định theo token ranges/topology; không có mối quan hệ một-một bắt buộc giữa “một token” và “một Kafka partition”.

## 12. Java DSL cho truy vấn dùng Cassandra outbound gateway

Cassandra outbound channel **gateway** là biến thể cần dùng khi flow muốn trả kết quả SELECT/statement. Nó vẫn dùng `ReactiveCassandraOperations` nhưng bật reply.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean
public IntegrationFlow orderTimelineQueryFlow(
        ReactiveCassandraOperations operations) {

    return IntegrationFlow.from("orderTimelineQueries")
            .handle(Cassandra.outboundGateway(operations)
                    .query("SELECT event_id, event_type, occurred_at "
                           + "FROM events_by_order_month "
                           + "WHERE tenant_id = :tenantId "
                           + "AND order_id = :orderId "
                           + "AND bucket_month = :bucketMonth LIMIT :maxRows")
                    .parameter("tenantId", message ->
                            ((TimelineQuery) message.getPayload()).tenantId())
                    .parameter("orderId", message ->
                            ((TimelineQuery) message.getPayload()).orderId())
                    .parameter("bucketMonth", message ->
                            ((TimelineQuery) message.getPayload()).bucketMonth())
                    .parameter("maxRows", message ->
                            ((TimelineQuery) message.getPayload()).maxRows()))
            .channel(c -> c.flux("orderTimelineResults"))
            .get();
}
~~~

Input của gateway là DTO:

~~~java
public record TimelineQuery(
        String tenantId,
        String orderId,
        String bucketMonth,
        int maxRows) {

    public TimelineQuery {
        if (tenantId == null || tenantId.isBlank()
                || orderId == null || orderId.isBlank()
                || bucketMonth == null || !bucketMonth.matches("\\d{4}-\\d{2}")
                || maxRows < 1 || maxRows > 100) {
            throw new IllegalArgumentException("Invalid timeline query");
        }
    }
}
~~~

`.parameter(...)` có thể dùng **SpEL String** hoặc **`Function<Message<?>, ?>`** để lấy giá trị từ message; ví dụ trên chọn Java function để truy cập Java record `TimelineQuery` có type rõ ràng. `:tenantId`, `:orderId`... trong CQL là **named bind markers**, không phải Spring headers. Gateway không ghép payload trực tiếp vào query syntax. Input vẫn cần được **xác thực tenant/authorization**, vì prepared parameters chỉ xử lý giá trị chứ không kiểm tra quyền truy cập.

`FluxMessageChannel` ở ví dụ hỗ trợ kịch bản reactive; consumer của `orderTimelineResults` phải được cấu hình để xử lý payload/reply theo loại Publisher/Result tương ứng với phiên bản Spring Integration. Nếu cần hành vi request/reply **imperative**, có thể chọn `async(false)` nhưng phải xem xét blocking và reply contract.

**Đừng dùng outbound adapter một chiều cho SELECT rồi chờ `replyChannel` được trả tự động.** Adapter `producesReply=false` sẽ không phát reply như một gateway.

### 12.1. Tham số lấy từ headers: dùng có kiểm soát

Trong một flow, `bucketMonth` có thể được đặt ở Spring header sau khi transform:

~~~java
// Fragment Java DSL, khi headers đã được kiểm tra/chuẩn hóa.
.handle(Cassandra.outboundGateway(operations)
        .query("SELECT event_id FROM events_by_order_month "
               + "WHERE tenant_id = :tenantId "
               + "AND order_id = :orderId "
               + "AND bucket_month = :bucketMonth LIMIT 25")
        .parameter("tenantId", "headers['verifiedTenantId']")
        .parameter("orderId", message ->
                ((TimelineQuery) message.getPayload()).orderId())
        .parameter("bucketMonth", "headers['canonicalBucketMonth']"))
~~~

Đặt tên `verifiedTenantId` để thể hiện header này được **tạo sau authentication/authorization**; không chỉ đổi tên một giá trị client tự khai báo rồi coi nó là đáng tin.

### 12.2. CQL statement trực tiếp

Khi cần tùy biến CQL ngoài Spring Data entity mapping, adapter cũng hỗ trợ mode `STATEMENT` và `statementFunction(...)` nhận Spring Message, trả driver `Statement<?>`:

~~~java
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean
public IntegrationFlow timelineBoundStatementFlow(
        ReactiveCassandraOperations operations) {
    return IntegrationFlow.from("timelineStatementWrites")
            .handle(Cassandra.outboundChannelAdapter(operations)
                    .statementFunction(message -> {
                        OrderTimelineEvent entity =
                                (OrderTimelineEvent) message.getPayload();
                        OrderTimelineKey k = entity.getKey();
                        return SimpleStatement.newInstance(
                                "INSERT INTO events_by_order_month "
                                + "(tenant_id, order_id, bucket_month, "
                                + "occurred_at, event_id, event_type, payload_json) "
                                + "VALUES (?, ?, ?, ?, ?, ?, ?)",
                                k.getTenantId(), k.getOrderId(), k.getBucketMonth(),
                                k.getOccurredAt(), k.getEventId(),
                                entity.getEventType(), entity.getPayloadJson());
                    }),
                    endpoint -> endpoint.async(false))
            .get();
}
~~~

`SimpleStatement.newInstance(query, args...)` tách CQL text khỏi bind values. Với hệ thống muốn chủ động dùng `PreparedStatement`/`BoundStatement` từ Java Driver, có thể prepare cùng CQL một lần trên `CqlSession` và gọi `prepared.bind(...)` theo từng event trước khi trả về `statementFunction`. Không nối keyspace, table name hoặc event values từ untrusted source vào CQL string.

**Chọn một con đường nhất quán:** entity `Type.INSERT` (mục 10) hoặc mode `STATEMENT` (mục 12.2) cho một endpoint. Không cài hai adapters nhận cùng input channel rồi kỳ vọng mỗi event chỉ được ghi một lần.

## 13. Liên hệ với Kafka partition key và JMS message group

Khóa Cassandra thuộc **data model**, còn khóa Kafka/JMS có thể quyết định **thứ tự/định tuyến tại broker**. Chúng có thể dùng chung `orderId` ở mức business contract nhưng không tự động ghép vào nhau.

### 13.1. Kafka: gửi record key ổn định theo order

~~~java
import org.springframework.kafka.core.KafkaTemplate;

public final class OrderKafkaPublisher {

    private final KafkaTemplate<String, String> kafka;

    public OrderKafkaPublisher(KafkaTemplate<String, String> kafka) {
        this.kafka = kafka;
    }

    public void send(String tenantId, String orderId, String json) {
        String kafkaKey = tenantId + ":" + orderId;
        kafka.send("order-events", kafkaKey, json);
    }
}
~~~

Với partitioner Kafka key-based và **topic partition count ổn định**, các records cùng key thường vào cùng một Kafka partition, giúp consumer xử lý theo thứ tự log khi thiết kế consumer concurrency/offset đúng. Tuy nhiên:

- Việc tăng số partitions hoặc đổi partitioner có thể thay đổi mapping key→partition.
- Một consumer có thể thực hiện xử lý bất đồng bộ, phá thứ tự side effects dù log có thứ tự.
- Cassandra không dùng Kafka partition index làm token hoặc partition key.
- Gửi Kafka record thành công không xác nhận Cassandra write đã xong.

Khi một Kafka inbound adapter đặt metadata `KafkaHeaders.KEY`/`RECEIVED_PARTITION` trong Spring Message headers, **CassandraMessageHandler không tự lấy những headers đó làm khóa**. Transformer phải tạo entity `OrderTimelineKey` từ payload và context đã validate.

### 13.2. JMS: message groups có phạm vi khác

Nếu broker JMS hỗ trợ message grouping (ví dụ một số ActiveMQ implementations), producer có thể đặt `JMSXGroupID` bằng business group key:

~~~java
// Fragment dùng JmsTemplate đã được cấu hình.
jmsTemplate.convertAndSend("orders.events.in", jsonBody, message -> {
    message.setStringProperty(
            "JMSXGroupID", tenantId + ":" + orderId);
    return message;
});
~~~

`JMSXGroupID` là JMSX property được một số providers dùng cho **message groups**. Chính sách gắn một group với consumer, failover và ordering là **provider-specific**, cần kiểm thử trên broker thực tế. Đừng giả định mọi JMS broker hỗ trợ cùng một chính sách hay Cassandra tự dùng JMSXGroupID để chọn partition.

### 13.3. Chọn khóa Kafka/JMS theo aggregate hay theo event?

| Khóa message | Thuận lợi | Đánh đổi |
|---|---|---|
| `eventId` | Phân bố records tương đối đều | Events cùng order có thể bị xử lý song song, không giữ thứ tự nghiệp vụ |
| `orderId` (kèm tenant) | Events cùng aggregate dễ đi cùng broker partition/group | Một order rất nóng có thể gây skew |
| `tenantId` | Đơn giản khi workload cân bằng các tenants | Tenant lớn tạo hot broker partition/consumer |
| `tenantId + bucketDay` | Phân đoạn theo ngày | Mất continuity ordering khi qua ngày, tenant lớn trong ngày vẫn có thể nóng |

**Quyết định broker partitioning và Cassandra partitioning phải được phân tích riêng**: Kafka thường ưu tiên ordering/concurrency của consumption; Cassandra ưu tiên query performance, data placement và partition size. Khi cần cả hai, dùng event contract chung với mapper riêng cho mỗi hệ.

## 14. Ordering: clustering order không phải message processing order

Ba loại “thứ tự” khác nhau:

1. **Broker log/group ordering:** Kafka partition hoặc JMS message group quyết định thứ tự delivery theo semantics của provider.
2. **Processing order:** consumer threads, async channels, retries và downstream callbacks có thể hoàn tất **không theo thứ tự nhận**.
3. **Cassandra clustering order:** các rows **đã được ghi** được sắp theo clustering columns trong cùng partition.

~~~mermaid
sequenceDiagram
    participant Broker as Kafka/JMS
    participant C1 as Consumer 1
    participant C2 as Consumer 2
    participant DB as Cassandra timeline
    Broker->>C1: event v1, occurredAt 03:00
    Broker->>C2: event v2, occurredAt 03:01
    C2->>DB: INSERT event v2
    DB-->>C2: Success
    C1->>DB: INSERT event v1 (retry muộn)
    DB-->>C1: Success
    Note over DB: Query có thể trả v2 trước v1 theo clustering
    Note over DB: Nhưng side effect state ở handler khác có thể đã sai thứ tự
~~~

Nếu mục tiêu chỉ là **event history**, lưu cả v1 và v2 với clustering timestamp/version có thể đủ. Nếu mục tiêu là **cập nhật current order state**, phải kiểm tra **aggregate version** hoặc dùng conditional write; không dựa vào thứ tự INSERT đến Cassandra.

### 14.1. Vì sao event ID là tie-breaker hữu ích?

Hai sự kiện có thể cùng `occurredAt` đến millisecond, ví dụ event service timestamp bị làm tròn. Nếu full PK chỉ là `((tenant_id, order_id, month), occurred_at)`, hai events cùng timestamp sẽ **đụng row key**. Thêm `event_id` làm clustering column tiếp theo để phân biệt hai sự kiện. Tuy nhiên:

- Event ID phải ổn định qua retries.
- Timestamp phải là event timestamp được chuẩn hóa, không lấy current time lúc consumer replay.
- Khi cả timestamp và ID bằng nhau nhưng payload khác, đó là **conflicting duplicate** cần phát hiện.

### 14.2. Version guard trên bảng state

Ví dụ bảng phục vụ **trạng thái hiện tại**, khác bảng timeline:

~~~sql
CREATE TABLE IF NOT EXISTS shop_integration.order_current_state (
    tenant_id text,
    order_id text,
    version bigint,
    state text,
    last_event_id text,
    PRIMARY KEY ((tenant_id, order_id))
);
~~~

Một conditional update:

~~~sql
UPDATE order_current_state
SET version = ?, state = ?, last_event_id = ?
WHERE tenant_id = ? AND order_id = ?
IF version = ?;
~~~

Ứng dụng chỉ chấp nhận event v3 khi stored version = v2 theo contract. Với row chưa tồn tại, cần **khởi tạo có điều kiện `IF NOT EXISTS`** hoặc chiến lược tương đương. Đọc `[applied]` của lightweight transaction (LWT) để phân biệt phiên bản không còn hợp lệ. LWT có chi phí cao và không tự là transaction nguyên tử giữa bảng state và bảng timeline khác partition.

**Không đơn giản dùng `occurredAt` của client để giải quyết mọi race**: đồng hồ các producers có thể lệch. Một `aggregateVersion` tăng đơn điệu do một authority quản lý thường phù hợp hơn cho business state, kèm policy với duplicate/out-of-order events.

### 14.3. Grouping ở broker và Cassandra key không thay thế version check

Ngay cả khi Kafka cùng orderId nằm một partition, một consumer có thể:

- Gửi hai asynchronous Cassandra writes song song.
- Retry một event muộn sau khi event mới hơn đã thành công.
- Phát lại offset cũ sau crash.
- Replay từ DLQ sau nhiều ngày.

Do đó, nếu nghiệp vụ đòi hỏi state không bị ghi lùi, **bảo vệ tại database/domain layer** vẫn cần thiết.

## 15. Retry, redelivery và khóa ổn định

Cassandra và JMS/Kafka là các tài nguyên khác nhau. Không có một Spring Integration annotation tự tạo distributed transaction atomic giữa broker acknowledgment và Cassandra write.

### 15.1. Vòng đời một event qua lỗi

~~~mermaid
flowchart TD
    A["Broker deliver eventId=evt-5001"] --> B["Validate event contract"]
    B --> C["Tính bucketMonth từ occurredAt UTC"]
    C --> D["Tạo OrderTimelineKey deterministic"]
    D --> E["Cassandra outbound handler"]
    E --> F{"Write completed?"}
    F -->|"Có"| G["Commit/ack nguồn theo policy"]
    F -->|"Lỗi hoặc kết quả không chắc"| H["Retry/redelivery có giới hạn"]
    H --> B
    H --> I{"Permanent error hoặc quá ngưỡng?"}
    I -->|"Có"| J["DLQ/quarantine + điều tra"]
~~~

Trong production, luồng xử lý error/retry còn phụ thuộc sync/async channel và acknowledgment mode. Sơ đồ thể hiện **mục tiêu kiến trúc**, không phải một cấu hình mặc định có sẵn tự chuyển message từ Cassandra sang JMS DLQ.

### 15.2. Hai cửa sổ lỗi khó tránh

| Cửa sổ | Có thể xảy ra | Cách bảo vệ |
|---|---|---|
| Cassandra ghi xong → JVM crash trước JMS commit/Kafka offset | Broker redeliver cùng event | Key deterministic, idempotent write |
| Broker ack/commit trước Cassandra async completion | Cassandra ghi lỗi mà nguồn không tự phát lại | Chờ completion trước ack hoặc durable handoff/recovery độc lập |
| Cassandra timeout sau khi server đã ghi | Retry thêm một lần dù row đã có | Cùng khóa, read-back/conditional semantics |
| Event đến trễ nhiều tháng | Bucket dựa vào thời điểm xử lý nếu code sai | Derive bucket từ `occurredAt` của event |
| Backfill từ archive với event ID mới tạo | Trùng business event dưới khóa khác | Preserve original `eventId` hoặc mapping ID có audit |

### 15.3. `async(false)` giúp nhìn thấy lỗi, không tạo exactly-once

Với JMS message-driven inbound adapter sử dụng session transacted, `DirectChannel` và Cassandra handler `async(false)`, một số lỗi Cassandra đồng bộ có thể truyền về listener để rollback. Tuy nhiên, nếu Cassandra đã ghi rồi JMS commit thất bại, event vẫn có thể được nhận lại.

Khi dùng `ExecutorChannel`, `QueueChannel` in-memory hoặc Cassandra handler async mặc định, JMS listener có thể kết thúc trước khi Cassandra write thực sự hoàn thành. **Một lỗi xảy ra sau source commit không thể rollback lại việc nhận JMS đã commit.**

### 15.4. `errorChannel`, DLQ và quarantine là các cơ chế khác nhau

- **Spring `errorChannel`**: mang `ErrorMessage` trong Spring Integration, không phải JMS DLQ.
- **JMS broker DLQ**: broker/provider chuyển message chưa xử lý được sau redelivery policy thích hợp.
- **Kafka dead-letter topic**: ứng dụng/handler hoặc retry topic infrastructure gửi record sang topic khác.
- **Application quarantine**: kho bền vững để điều tra lỗi data contract hoặc conflicting event ID.

Nếu error handler nhận exception rồi trả thành công, inbound listener có thể commit theo cấu hình dù Cassandra chưa ghi. Muốn rollback/redelivery phải đảm bảo exception **thực sự đi tới acknowledgment boundary**; không chỉ ghi log lỗi.

### 15.5. Hai kiểu idempotency khác nhau

**Idempotent timeline INSERT:** cùng đầy đủ full PK và cùng values có thể được gửi nhiều lần; Cassandra upsert thường không tạo một row thứ hai. Nhưng nếu `occurredAt` hoặc bucket thay đổi, full PK thay đổi và có thể tạo bản ghi trùng.

**Deduplication theo eventId toàn cục:** bảng `event_by_id(event_id PRIMARY KEY, ...)` có thể giúp lookup/claim event. Tuy nhiên một claim `IF NOT EXISTS` ở bảng A rồi ghi timeline ở bảng B **không phải transaction nguyên tử liên-bảng**. Nếu crash sau claim mà trước timeline write, cần **reconciler/replay** để lấp row thiếu. Không dùng một “idempotency gate” thiếu recovery rồi bỏ qua mọi retry như thể hai writes luôn cùng commit.

### 15.6. Khi nào nên dùng LWT?

`IF NOT EXISTS` hoặc `IF version = ...` thích hợp khi cần compare-and-set chặt trong **phạm vi Cassandra hỗ trợ**, ví dụ bảo vệ `order_current_state` theo aggregate version. Tuy nhiên:

- LWT chậm/đắt hơn write thông thường.
- Không giải quyết atomicity với JMS/Kafka source.
- Không bảo đảm hai bảng khác partition cùng được thay đổi một cách cô lập như SQL transaction.
- Khi response timeout, cần xử lý trạng thái không chắc chắn theo khóa/condition.

Đừng bật LWT cho mọi event chỉ vì muốn “chắc chắn”: hãy xác định invariant nghiệp vụ và benchmark.

## 16. Chiến lược migration khi cần đổi partition key

Một sai lầm thường gặp là phát hiện hot partition rồi **thay một annotation `@PrimaryKeyColumn` hoặc sửa CQL DDL** và cho rằng Cassandra sẽ tự phân bố dữ liệu cũ. Primary key của bảng Cassandra **không được biến đổi tùy ý bằng UPDATE**. Một chiến lược an toàn thường cần **bảng mới + backfill + dual-read/dual-write có kiểm soát**.

### 16.1. Ví dụ chuyển từ per-tenant/day sang per-order/month

~~~text
Schema cũ:
  events_by_tenant_day
  partition key = (tenant_id, bucket_day)

Schema mới:
  events_by_order_month
  partition key = (tenant_id, order_id, bucket_month)
~~~

Runbook:

1. **Xác định query workloads/partition metrics:** vì sao schema cũ nóng, truy vấn nào sẽ bị ảnh hưởng khi đổi.
2. **Tạo bảng mới** với CQL schema/replication/TTL phù hợp, không DROP bảng cũ.
3. **Triển khai transformer mới** tính key deterministic từ bản ghi gốc; version hóa quy ước bucket.
4. **Backfill theo lô nhỏ** từ dữ liệu cũ/archive/source-of-truth; giới hạn concurrency, giữ nguyên business `eventId`/`occurredAt`.
5. **Dual-write hoặc CDC/replay** từ một nguồn đáng tin; theo dõi trường hợp một write thành công còn write kia lỗi.
6. **Shadow-read và đối soát** số sự kiện, conflict, key boundaries, query p95 và partitions mới.
7. **Chuyển traffic đọc** theo từng tenant/percentage, có rollback plan.
8. **Dừng ghi cũ** sau khi dữ liệu đồng nhất và có kế hoạch khôi phục, sau đó archive/drop theo chính sách retention.

### 16.2. Đừng đổi hash/bucket scheme âm thầm

Giả sử producer trước đây tính bucket bằng timezone `Asia/Ho_Chi_Minh` còn consumer mới tính UTC. Những sự kiện gần ranh giới ngày/tháng có thể chuyển sang partition khác sau replay. Migration phải **ghi rõ quy tắc timezone/version**, có tests cho ranh giới và, nếu cần, đọc cả key scheme cũ trong giai đoạn chuyển tiếp.

Tương tự, đổi số shards từ 16 sang 32 làm kết quả `hash(eventId) % shards` khác cho nhiều events; cần version hóa và kế hoạch backfill/read fallback. **Partition key là một phần của hợp đồng dữ liệu bền vững**, không chỉ là một optimization hint trong code.

### 16.3. Không tạo một hot migration job

Backfill toàn bộ 5 năm events đồng thời bằng hàng nghìn Cassandra writes/s vào một hot partition có thể làm hỏng SLA của production. Chia tải theo partition ranges/key ranges, giới hạn retry, dừng khi latency/error rate vượt ngưỡng, và có thể tạm giảm tốc khi cluster đang compaction/repair.

## 17. Observability: nhận biết hot partition thay vì chỉ đo CPU

Khi throughput giảm, đừng chỉ tăng số threads của Spring Integration. Cần đo từ nguồn message tới Cassandra cluster.

| Metric/quan sát | Nguồn | Dấu hiệu cần điều tra |
|---|---|---|
| JMS queue depth / Kafka consumer lag | Broker | Backlog tăng khi Cassandra chậm |
| Message ingress rate, handler success/error | Spring Integration | Message vào nhanh hơn writes hoàn tất |
| Cassandra write latency p50/p95/p99 | Driver/cluster | p99 tăng mạnh dù p50 bình thường |
| In-flight Cassandra requests | Driver | Quá nhiều requests đang chờ, thiếu backpressure |
| Per-node request distribution | Driver/cluster | Một hoặc vài nodes chịu tải vượt trội |
| Hot partition/top partitions | Cassandra diagnostics | Một partition key chiếm phần lớn writes/reads |
| Estimated/maximum partition sizes | Cassandra table stats | Wide partitions hoặc skew |
| SSTables, compaction, tombstones | Cluster | TTL/delete hoặc repair gây read pressure |
| Timeout/Unavailable/Overloaded | Driver exceptions | Cluster mất năng lực đáp ứng |
| Duplicate `eventId`, conflicting payload | Business metrics | Redelivery hoặc contract lỗi |
| Buckets/shards per tenant, p99 rows/partition | Application analytics | Bucketing không đủ hoặc shard function phân bố kém |
| Backfill write rate và mismatch count | Migration tool | Migration gây tải hoặc thiếu dữ liệu |

### 17.1. Diagnostic tools với Cassandra thật

Trong môi trường test hoặc runbook đã được phê duyệt, sử dụng:

- `nodetool tablestats` để xem thống kê bảng, kích thước partition ước tính và read/write metrics (field cụ thể tùy version Cassandra).
- Công cụ quan sát hot partitions/top keys hoặc sampling/tracing mà phiên bản Cassandra hỗ trợ; tránh chạy thao tác quét toàn bảng không giới hạn trên production.
- `TRACING ON` trong `cqlsh` cho truy vấn test để hiểu coordinator/replica routing; tracing có overhead, không bật đại trà.
- Driver metrics về request latency, in-flight requests, connection saturation, timeouts và retries.
- Application logs có `eventId`, **logical partition-key fields đã được kiểm soát**, operation type và exception class; tránh log payload nhạy cảm.

Không dùng `SELECT COUNT(*) FROM huge_table` như một cách “đếm partition nhanh”; nó có thể tạo scan đắt đỏ. Nếu cần thống kê quy mô dữ liệu, dùng metrics/table stats hoặc bảng thống kê được thiết kế riêng.

### 17.2. Đo phân bố shard trước khi deploy

Ví dụ chọn 16 shards theo `eventId`. Trong môi trường thử nghiệm:

1. Sinh tập event IDs có phân bố giống production.
2. Tính `StableShards.shard16(eventId)`, đếm số events ở mỗi shard.
3. So sánh min/max/p95 của số events/shard, không chỉ trung bình.
4. Kiểm thử một tenant có tải cao đột biến và các tenants nhỏ.
5. Đo latency và Cassandra coordinator load khi ghi thật, không chỉ phân bố hash offline.

Một hash function nhìn cân bằng trên 1 triệu UUID ngẫu nhiên **không bảo đảm** dữ liệu thực cân bằng nếu event IDs có cấu trúc đặc biệt hoặc workload tập trung theo các key khác.

### 17.3. Alert hữu ích

Nên có cảnh báo cho backlog nguồn tăng liên tục, Cassandra p99 write latency vượt SLA, hotspot ở một partition quá ngưỡng benchmark, timeout/error burst, số events bị quarantine tăng, và tỷ lệ replay/duplicate bất thường. Một alert chỉ nhìn Cassandra CPU trung bình toàn cluster có thể bỏ sót **một partition/nút nóng**.

## 18. Các lỗi thiết kế thường gặp

| Vấn đề | Triệu chứng | Nguyên nhân | Cách sửa |
|---|---|---|---|
| Dùng `tenantId` đơn độc làm partition key | Tenant lớn timeout, nhiều rows cùng partition | Cardinality/skew cao | Thêm business discriminator và bucket/shard theo query |
| Dùng `eventId` ngẫu nhiên làm PK cho mọi bảng | Ghi phân bố tốt nhưng query order history khó | Key không theo query | Tạo bảng theo order/time bên cạnh lookup by event |
| Đặt `orderId` thành clustering thay vì partition component | Một tenant giữ mọi orders trong một partition | CQL `PRIMARY KEY` thiếu ngoặc | Dùng composite partition key với ngoặc đôi |
| Chỉ thêm clustering `occurredAt` để chữa hot partition | Partition vẫn nóng | Clustering không đổi token | Bucket/shard partition key |
| Bucket bằng ngày lúc consumer xử lý | Replay sang ngày mới tạo duplicate row | Key không deterministic | Bucket từ event timestamp/UTC |
| Bucket không version hóa | Dữ liệu cũ/mới nằm ở partition khác | Đổi granularity/timezone | Versioned migration + backfill |
| Hash shard từ `UUID.randomUUID()` ở consumer | Same event mỗi lần một shard | Khóa biến đổi qua retry | Hash `eventId` ổn định |
| Thay 16 shards bằng 32 không migration | Read không thấy events cũ | Modulo thay mapping | Version scheme, dual-read/backfill |
| Dùng Kafka partition index làm Cassandra shard | Tăng partitions topic làm dữ liệu chia lại | Nhầm hai partitioners | Stable app-level shard function |
| Dùng Spring header `tenantId` chưa xác thực | Ghi nhầm tenant hoặc đọc trái quyền | Header client tự khai | AuthZ + validate payload/context |
| Query chỉ theo `tenant_id` trên composite PK | CQL lỗi hoặc filtering rất tốn | Thiếu các partition columns | Bảng mới theo query pattern |
| Query toàn bộ timeline bằng một bucket | Thiếu tháng khác | Time bucketing chia partitions | Fan-out buckets có giới hạn |
| Hai events cùng timestamp ghi đè | Mất event có cùng clustering key | Thiếu tie-breaker | Thêm `event_id` vào clustering |
| Cassandra timeline có thứ tự nhưng state sai | Event cũ cập nhật sau event mới | Clustering order ≠ processing order | Aggregate version/conditional state update |
| Source JMS ack trước Cassandra write | Mất cơ chế redelivery khi DB lỗi | Async boundary không rõ | Sync completion/durable handoff |
| Redelivery tạo eventId mới | Một sự kiện thành hai rows | Consumer sinh ID mới | Giữ ID từ original event |
| Cassandra LWT false bị coi là success vô điều kiện | Bỏ qua conflicting payload | Không kiểm tra row hiện có | Phân biệt duplicate và conflict |
| Ghi hai Cassandra tables rồi coi là ACID | Một table thiếu dữ liệu sau crash | Không có cross-partition transaction SQL | Repair/reconciliation/idempotent replay |
| Logging full partition key/payload nhạy cảm | Dữ liệu lộ trong logs | Thiếu masking/ACL | Audit/tracing tối thiểu, giữ log an toàn |
| Tăng consumer concurrency để chữa DB hotspot | Timeout tăng, backlog lớn hơn | Node/partition đã saturated | Sửa data model/limit in-flight |

### 18.1. Checklist khi review một partition-key design

1. **Query-first:** liệt kê các queries buộc phải trả lời, với giới hạn latency và kết quả.
2. **Partition identity:** viết chính xác CQL `PRIMARY KEY` có ngoặc đôi và thứ tự fields.
3. **Data distribution:** giả lập top tenants/orders, average/p95/p99 partition size.
4. **Bounded partitions:** có bucket/shard phù hợp, TTL và retention nếu cần.
5. **Deterministic key:** retry/backfill có tạo đúng cùng key không?
6. **Ordering:** dùng clustering cho timeline hay version guard cho current state?
7. **Security:** tenantId xác thực, key không chứa bí mật; không ghép user input thành table name.
8. **Mapping:** `@PrimaryKeyClass`/`@PrimaryKeyColumn` có trùng CQL schema không?
9. **Flow:** transformer chạy trước adapter, payload là đúng entity hoặc BoundStatement?
10. **Ack/error:** message nguồn chỉ commit sau thời điểm nào, có recovery nếu DB timeout?
11. **Observability:** đo hot partitions, p99 latency, backlog, duplicate/conflict.
12. **Migration:** nếu đổi bucketing/sharding/PK, có backfill/dual-read/rollback plan?

## 19. Bài thực hành: từ message flow đến partition key an toàn

**Môi trường:** Java 17+, Spring Integration Cassandra 6+ tương thích, Spring Data Cassandra reactive, một Cassandra test cluster hoặc container; JMS/Kafka broker test cho phần nâng cao. Không chạy destructive/backfill load test trên production.

### Phần A — So sánh ba cách đặt PRIMARY KEY

1. Tạo ba bảng thử nghiệm cùng fields nhưng có cấu hình PK khác nhau:

~~~sql
CREATE TABLE shop_integration.lab_by_tenant (
    tenant_id text, order_id text, event_id text, payload text,
    PRIMARY KEY (tenant_id, order_id, event_id)
);

CREATE TABLE shop_integration.lab_by_tenant_order (
    tenant_id text, order_id text, event_id text, payload text,
    PRIMARY KEY ((tenant_id, order_id), event_id)
);

CREATE TABLE shop_integration.lab_by_event (
    event_id text PRIMARY KEY, tenant_id text, order_id text, payload text
);
~~~

2. Ghi 500 events cho 5 tenants, có một tenant chiếm 80% workload.
3. Dùng `DESCRIBE TABLE` và CQL `token(...)` trên dữ liệu đã ghi để so sánh các partition keys.
4. Truy vấn theo tenant+order và theo eventId. Xem bảng nào hỗ trợ query trực tiếp, bảng nào cần lookup riêng.
5. Giải thích tại sao **nhiều clustering rows không làm một partition tách thành nhiều tokens**.

**PASS:** Nêu đúng partition key của từng table và hệ quả về query/hotspot.

### Phần B — Bucketing đúng ranh giới tháng UTC

1. Gọi `PartitionBuckets.utcMonth(...)` với:

~~~text
2026-11-30T23:59:59Z -> 2026-11
2026-12-01T00:00:00Z -> 2026-12
2026-12-01T07:00:00+07:00 -> 2026-12 (cùng Instant 00:00Z)
~~~

2. Tạo một `OrderEvent` vào cuối tháng 11 và một event vào đầu tháng 12.
3. Chạy `TimelineMapper.toEntity(...)` rồi kiểm tra `bucketMonth`.
4. Giả lập replay vào tháng khác nhưng giữ `occurredAt` cũ; key phải **không đổi**.
5. Cố ý tính bucket bằng `LocalDate.now()` trong test âm tính; chỉ ra nguy cơ duplicate.

**PASS:** cùng event luôn cho cùng partition key theo quy ước UTC.

### Phần C — Mapping composite key

1. Tạo bảng `events_by_order_month` từ mục 3.
2. Đăng ký `OrderTimelineKey` với `@PrimaryKeyClass`, ba trường `PARTITIONED` và hai trường `CLUSTERED`.
3. Dùng `OrderTimelineEvent` đã gắn `@PrimaryKey` và `@Table`.
4. Gửi một entity qua `ReactiveCassandraOperations` hoặc outbound adapter.
5. Query bằng **đủ ba partition-key fields** và xác minh row đúng `event_id`.
6. Kiểm tra `equals/hashCode` của hai key objects cùng values; chúng phải bằng nhau theo Java identity semantics.

**PASS:** annotation đúng vị trí/thứ tự/kiểu với CQL schema; Spring Data ghi đúng partition.

### Phần D — Java DSL và JSON contract

1. Cấu hình `orderEventsToCassandra` ở mục 10.
2. Biến đổi JSON `OrderPaid` thành `OrderEvent` có `occurredAt` kiểu `Instant`; validate payload.
3. Gửi qua `validatedOrderEvents`; truy vấn lại Cassandra.
4. Gửi JSON thiếu `orderId` và kiểm tra message bị từ chối **trước CQL write**.
5. Gửi header `tenantId` mâu thuẫn với authenticated context trong test; endpoint phải phân loại lỗi authorization/contract, không viết qua tenant khác.
6. Thử thay handler `async(false)` bằng async default, đo lúc `send()` trả về và lúc Cassandra write hoàn thành.

**PASS:** không có row với key rỗng/`unknown`, và caller hiểu khác biệt completion.

### Phần E — Time bucketing và truy vấn nhiều buckets

1. Ghi sự kiện của một order qua ba tháng liên tiếp.
2. Query từng `bucket_month` riêng, mỗi query có `LIMIT` và phân trang phù hợp.
3. Merge kết quả theo `occurredAt DESC, eventId ASC`.
4. Xác minh query trong một tháng **không** trả events tháng khác.
5. Cố ý dùng query chỉ có `tenant_id` rồi ghi nhận lỗi hoặc chi phí; sửa bằng query đúng key/table.

**PASS:** timeline xuyên nhiều tháng không thiếu rows, không quét toàn bảng.

### Phần F — Sharding và hotspot

1. Dùng `StableShards.shard16` cho 100.000 event IDs ngẫu nhiên và một tập event IDs gần giống production.
2. Đếm số events mỗi shard; quan sát skew.
3. Tạo `events_by_tenant_day_shard` với `shard` là một thành phần partition key.
4. Ghi một tenant lớn trong cùng ngày, so sánh p95 write latency và phân bố node so với bảng `events_by_tenant_day` không shard.
5. Query toàn bộ ngày bằng 16 shards với **fan-out có giới hạn**, merge theo sort key.
6. Thử đổi shard count sang 32 trong nhánh thử nghiệm; xác minh không thể đọc đúng dữ liệu cũ nếu không có migration/compatibility layer.

**PASS:** giải thích đúng trade-off write distribution vs read fan-out và tính ổn định hash.

### Phần G — Kafka/JMS grouping và Cassandra key

1. Producer Kafka gửi ba events cùng `tenantId + orderId` key; kiểm tra broker partition được chọn.
2. Tăng số partitions **trên broker test**, quan sát mapping có thể thay đổi theo partitioner/version.
3. Với JMS broker hỗ trợ groups, gửi các events mang cùng `JMSXGroupID` và kiểm tra consumer assignment.
4. Đưa events từ hai nguồn qua transformer sang `OrderTimelineKey`; xác minh cùng một business event tạo cùng Cassandra key bất kể broker metadata.
5. Bật xử lý async trong flow để thấy thứ tự completion có thể khác thứ tự delivery.

**PASS:** không nhầm Kafka partition/JMS group với Cassandra token/partition.

### Phần H — Redelivery, version guard và migration

1. Dùng một JMS transacted listener → `DirectChannel` → Cassandra handler sync.
2. Cho Cassandra write hoàn tất rồi mô phỏng crash trước JMS commit; redeliver cùng event.
3. Xác minh `eventId`/`occurredAt`/`bucketMonth` không đổi, không tạo row timeline mới.
4. Gửi event v2 rồi v1; kiểm chứng clustering timeline khác với việc bảo vệ current state.
5. Tạo conditional update `IF version = ...` cho bảng `order_current_state`; phân biệt `applied=true/false`.
6. Viết migration plan chuyển schema cũ sang schema mới gồm backfill, dual-read và kiểm soát tải.

**PASS:** có chiến lược idempotent redelivery, không giả định Cassandra và JMS commit atomic, và biết cách đổi partition key không mất dữ liệu.

### Ma trận kiểm thử cuối bài

| Trường hợp | Kết quả cần đạt |
|---|---|
| Composite partition key | CQL và annotation mapping đồng nhất |
| Clustering | Rows sắp trong một partition, không suy ra processing order |
| Bucket UTC | Replay cùng event tạo đúng bucket cũ |
| Shard function | Hash ổn định và có cách version hóa khi đổi |
| Query-first schema | Truy vấn dùng đủ partition columns |
| Kafka/JMS | Broker key không tự tạo Cassandra key |
| Cassandra adapter | Entity được transform trước khi viết |
| Cassandra gateway | Named parameters bind từ message đúng key |
| Duplicate event | Cùng full PK không tạo row mới do current time |
| LWT | Condition được kiểm tra, không lẫn applied=false với system error |
| Async boundary | Error/ack semantics được quan sát đúng |
| Backpressure | Không tạo unbounded fan-out/retry khi cluster chậm |
| Migration | Có backfill/reconciliation và rollback plan |
| Security | Tenant key được xác thực, không dùng khóa client tự khai tùy ý |

Với partition placement, token-aware routing, hotspot, LWT và timeout, **phải kiểm thử trên Cassandra thật hoặc test container**. Mock `ReactiveCassandraOperations` chỉ chứng minh mapper/flow gọi API; không thể kiểm chứng phân bố token, replication, consistency hoặc dữ liệu có nằm đúng partition sau failover.

## 20. Câu hỏi tự đánh giá

1. Cassandra partition key khác full primary key và clustering columns như thế nào?
2. `PRIMARY KEY (tenant_id, order_id, event_id)` khác gì với `PRIMARY KEY ((tenant_id, order_id), event_id)`?
3. Tại sao hai rows có chung partition key thường được lưu bởi cùng một tập replicas?
4. Murmur3 token trong Cassandra được tính từ phần nào của primary key?
5. Kafka record key và Cassandra partition key có tự chọn cùng node/partition khi dùng chung `orderId` không?
6. `JMSXGroupID` có tự trở thành Cassandra partition key không?
7. Vì sao mô hình query-first cần thiết trong Cassandra hơn kiểu chuẩn hóa bảng của RDBMS truyền thống?
8. Khi nào `eventId` là partition key phù hợp? Khi nào nó khiến query theo order khó?
9. Vì sao `tenantId` đơn độc có thể tạo hot partition cho tenant lớn?
10. Clustering column `occurredAt` có giảm hot partition do cùng tenant không?
11. Tại sao time bucketing giúp giữ partition hữu hạn nhưng không tự phân tán writes trong một ngày?
12. Cách chọn bucket theo UTC khác gì với chọn bằng timezone JVM mặc định?
13. Vì sao consumer không được dùng `LocalDate.now()` để tính bucket của một sự kiện replay?
14. Một partition có 500.000 rows nhưng chỉ một partition key thì có được tự chia cho 500.000 tokens không?
15. Lợi ích và đánh đổi của việc thêm `shard` vào composite partition key là gì?
16. Nếu đổi số shards từ 16 sang 32, phải xử lý dữ liệu cũ thế nào?
17. Nếu shard theo `eventId`, sự kiện của cùng order có còn bảo đảm ở cùng một Cassandra partition không?
18. `@PrimaryKeyClass` và `@PrimaryKeyColumn(type=PARTITIONED/CLUSTERED)` dùng để làm gì?
19. Tại sao `equals/hashCode` của composite key class cần đầy đủ và nhất quán?
20. Vì sao phải chuẩn hóa `Instant` về độ chính xác millisecond khi CQL column là `timestamp`?
21. Khi dùng Cassandra outbound adapter, Spring message headers có tự được map thành partition key không?
22. Vì sao payload của `Type.INSERT` nên là entity `@Table` thay vì raw JSON `String`?
23. Khi nào dùng Cassandra outbound gateway thay vì outbound channel adapter?
24. `.query(...).parameter("tenantId","payload.tenantId")` chuyển dữ liệu theo hai cơ chế nào?
25. Vì sao truy vấn `WHERE tenant_id = ?` không tương đương truy vấn đúng composite partition key ba cột?
26. Khi đọc timeline 3 tháng, vì sao cần fan-out và merge có giới hạn?
27. Clustering order có đảm bảo business state được cập nhật theo thứ tự events không?
28. `aggregateVersion` và conditional Cassandra update có thể bảo vệ current state ra sao?
29. Tại sao redelivery cùng event phải tạo **cùng full PK**, không chỉ cùng `tenantId`?
30. Vì sao một idempotency claim ở bảng A rồi ghi bảng B không tự tạo cross-table ACID transaction?
31. Điều gì xảy ra nếu nguồn JMS commit trước một Cassandra async write thất bại?
32. `errorChannel` có tự kích hoạt Cassandra retry/JMS DLQ không?
33. Vì sao không thể chỉ sửa `@PrimaryKeyColumn` để thay partition key cho dữ liệu đã lưu?
34. Metrics nào giúp phát hiện một partition nóng dù CPU trung bình toàn cluster chưa cao?
35. Kế hoạch migration thay partition key cần tối thiểu những bước nào?

## 21. Tài liệu tham khảo chính thức

- [Apache Cassandra — Data Modeling Introduction](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html): query-first model, partition size, redundancy và trade-offs.
- [Apache Cassandra — Logical Data Modeling](https://cassandra.apache.org/doc/latest/cassandra/developing/data-modeling/data-modeling_logical.html): thiết kế bảng theo queries và chọn partition/clustering keys.
- [Apache Cassandra — Evaluating and Refining Data Models](https://cassandra.apache.org/doc/latest/cassandra/developing/data-modeling/data-modeling_refining.html): bucketing, đánh giá kích thước partition và cải thiện schema.
- [Apache Cassandra — CQL Data Definition](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/ddl.html): PRIMARY KEY, composite partition keys, clustering order và token/placement semantics.
- [Spring Data Cassandra — Object Mapping](https://docs.spring.io/spring-data/cassandra/reference/object-mapping.html): `@PrimaryKeyClass`, `@PrimaryKeyColumn`, `PrimaryKeyType.PARTITIONED`, `CLUSTERED` và entity identity.
- [Spring Data Cassandra — PrimaryKeyColumn Javadoc](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/mapping/PrimaryKeyColumn.html): `ordinal`, `type` và `ordering`.
- [Spring Data Cassandra — Reactive Cassandra](https://docs.spring.io/spring-data/cassandra/reference/cassandra/reactive-cassandra.html): `ReactiveCassandraOperations`, reactive execution và error handling.
- [Spring Integration — Apache Cassandra Support](https://docs.spring.io/spring-integration/reference/cassandra.html): `CassandraMessageHandler`, outbound channel adapter/gateway, `query`, `parameter` và `statementFunction`.
- [Spring Integration — Cassandra DSL Javadoc](https://docs.spring.io/spring-integration/api/org/springframework/integration/cassandra/dsl/Cassandra.html): các factory `outboundChannelAdapter(...)` và `outboundGateway(...)`.
- [Apache Cassandra Java Driver — Prepared Statements](https://apache.github.io/cassandra-java-driver/4.19.0/core/statements/prepared/): bind values, routing metadata, preparation/repreparation.
- [Apache Kafka — Documentation](https://kafka.apache.org/documentation/): Kafka record keys/partitions/consumer semantics để đối chiếu với Cassandra keys.
- [ActiveMQ Classic — Message Groups](https://activemq.apache.org/components/classic/documentation/message-groups): `JMSXGroupID` và broker-specific message grouping.

**Ghi nhớ:** Cassandra **partition key** quyết định **partition/tokens/replica placement**, còn **clustering key** sắp xếp rows trong một partition. Trong Spring Integration, message headers, Kafka key hoặc JMS group **không tự trở thành Cassandra partition key**: transformer phải tạo entity/statement mang đủ các field theo CQL schema. Thiết kế đúng bắt đầu từ **query pattern**, kiểm soát **skew, partition size, bucket/shard**, tạo khóa **deterministic qua retry/replay**, và phân biệt **clustering order với business processing order**. Khi thay đổi partition key, cần migration/backfill và kiểm thử thực tế, không chỉ sửa annotation.





