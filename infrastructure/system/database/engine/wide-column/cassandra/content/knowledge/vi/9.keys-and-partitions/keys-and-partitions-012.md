# Khóa tenant và giới hạn tenant có quy mô quá lớn

Trong hệ thống **đa khách hàng** (*multi-tenant*) dùng Apache Cassandra, một bảng có thể phục vụ từ vài chục đến hàng nghìn tenant. Mỗi tenant có thể là một doanh nghiệp, tổ chức hoặc khách hàng sử dụng cùng dịch vụ. Các tenant thường không có cùng quy mô: một khách hàng nhỏ có vài trăm sự kiện mỗi ngày, trong khi một khách hàng rất lớn có thể phát sinh hàng triệu sự kiện mỗi giờ.

Khi thiết kế bảng wide-column phân tán, **`tenant_id` thường là thành phần quan trọng của partition key**, nhưng dùng riêng `tenant_id` làm partition key cho mọi dữ liệu của tenant là một bẫy phổ biến. Nếu tenant lớn, toàn bộ dữ liệu và lưu lượng của họ có thể dồn vào **một phân vùng logic**, dẫn tới *large partition*, *hot partition* và hiện tượng *noisy neighbor* làm ảnh hưởng tenant khác.

Bài này tập trung vào việc sử dụng khóa tenant **đúng phạm vi**, thiết kế partition key có thêm miền nghiệp vụ, time bucket hoặc shard khi cần, đồng thời xác lập **giới hạn tài nguyên và kiểm soát tải theo tenant**. Các quyết định đó liên quan trực tiếp đến replication, consistency level, compaction, repair, truy vấn CQL và Java Driver.

Sau bài học, bạn có thể:

- Phân biệt **tenant identity**, **partition key** và **ranh giới phân quyền**.
- Giải thích vì sao một partition key chỉ có `tenant_id` có thể trở thành nút thắt.
- Thiết kế các bảng phục vụ truy vấn theo tenant–thiết bị–ngày và timeline toàn tenant.
- Ước lượng kích thước phân vùng, mức lệch tải và fan-out khi dùng time bucket hoặc shard.
- Đặt hạn mức ghi, đọc, lưu trữ và truy vấn cho tenant lớn mà không dựa vào một tính năng giả định của Cassandra.
- Giữ định tuyến bucket/shard ổn định trong Java khi retry, backfill hoặc đổi chính sách tenant.

## 1. `tenant_id` đại diện cho điều gì?

Một tenant là một **miền sở hữu và sử dụng dữ liệu** trong ứng dụng. Ví dụ:

```text
Tenant acme
  ├── user A
  ├── user B
  ├── device D1
  └── device D2

Tenant beta
  ├── user C
  └── device D3
```

Ứng dụng thường phải bảo đảm rằng yêu cầu của tenant `acme` không thể đọc hay sửa dữ liệu của tenant `beta`. Vì vậy, mọi đường truy cập cần mang ngữ cảnh tenant rõ ràng.

Trong Cassandra, có ba khái niệm **không được đồng nhất**:

| Khái niệm | Ý nghĩa | Điều nó không tự bảo đảm |
| --- | --- | --- |
| **Tenant identity** | Mã tenant do ứng dụng quản lý và xác thực. | Không tự chỉ ra dữ liệu nằm trên node nào. |
| **Partition key** | Tổ hợp giá trị được Cassandra hash thành token để định vị phân vùng. | Không tự cấp quyền truy cập hay tự giới hạn dung lượng. |
| **Quyền truy cập tenant** | Chính sách xác thực, phân quyền và kiểm soát truy vấn. | Không mặc nhiên được thực thi chỉ vì bảng có cột `tenant_id`. |

Cassandra có cơ chế xác thực/phân quyền đối với những tài nguyên được hỗ trợ như keyspace và table, nhưng **không nên xem việc đưa `tenant_id` vào một bảng dùng chung là cơ chế row-level authorization tự động**. Lớp ứng dụng phải xác định tenant từ ngữ cảnh đã xác thực, kiểm tra quyền và **bind tenant_id từ ngữ cảnh tin cậy**, thay vì tin nguyên giá trị tenant do client gửi.

Ví dụ, một request API tự ý truyền `tenant_id = 'beta'` không được phép đổi phạm vi truy cập của người dùng đã đăng nhập vào `acme`. Thiết kế partition key hữu ích cho việc định tuyến và tổ chức dữ liệu; việc cô lập bảo mật cần được thiết kế riêng.

## 2. Vì sao `PRIMARY KEY (tenant_id, ...)` có thể nguy hiểm?

Giả sử dịch vụ ghi mọi sự kiện của tenant theo thời gian:

```sql
CREATE TABLE events_by_tenant_all_time (
    tenant_id   text,
    occurred_at timestamp,
    event_id    uuid,
    event_type  text,
    payload     text,
    PRIMARY KEY (tenant_id, occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
```

Cú pháp `PRIMARY KEY (tenant_id, occurred_at, event_id)` có nghĩa:

- Partition key **chỉ là** `tenant_id`.
- Clustering columns là `occurred_at` và `event_id`.
- Mọi sự kiện của tenant `acme` cùng thuộc **một phân vùng logic**, bất kể thời gian và người phát sinh.

```text
Partition key 'acme'
│
├── (2026-11-21T10:03Z, E3)
├── (2026-11-21T10:02Z, E2)
├── (2026-11-21T10:01Z, E1)
│   ...
└── hàng triệu sự kiện trong nhiều tháng

Partition key 'beta'
│
└── một số sự kiện ít hơn nhiều
```

**Điểm dễ nhầm:** việc `event_id` có cardinality cao không tạo thêm partition keys. Chỉ có `tenant_id` được hash để chọn tập replica; hai clustering columns chỉ phân biệt hàng **trong phân vùng ấy**.

Nếu `acme` tạo phần lớn dữ liệu và truy vấn, tập replica của partition `acme` phải phục vụ phần lớn công việc. Tăng số node hoặc tăng replication factor có thể bổ sung năng lực toàn cluster, nhưng **không tự chia một partition key duy nhất thành nhiều partition keys**.

### Khóa ghép không phải phép tìm theo tiền tố

Nếu sửa thành:

```sql
PRIMARY KEY ((tenant_id, device_id), occurred_at, event_id)
```

mỗi cặp `(tenant_id, device_id)` là một partition key riêng. Điều này giúp tách dữ liệu giữa các thiết bị, nhưng câu truy vấn chỉ có `WHERE tenant_id = 'acme'` **không xác định được một partition key hoàn chỉnh**.

Cassandra hash **toàn bộ** tổ hợp khóa ghép; việc đặt `tenant_id` trước `device_id` không tạo một dải index cho phép quét mọi thiết bị của tenant một cách hiệu quả theo mặc định. Muốn truy vấn toàn tenant, cần mô hình dữ liệu hoặc đường truy cập phục vụ mục đích đó.

## 3. Tenant lớn làm lệch tải như thế nào?

Giả sử một nền tảng có **1.000 tenant**:

- 999 tenant phổ thông, mỗi tenant phát sinh trung bình **5 sự kiện/giây**.
- Một tenant lớn `whale` phát sinh **6.000 sự kiện/giây**.
- Mỗi sự kiện chứa trung bình **600 byte payload logic**.

Tổng tải ghi ước tính:

```text
Tenant phổ thông:
  999 × 5 = 4.995 sự kiện/giây

Tenant whale:
  6.000 sự kiện/giây

Toàn hệ thống:
  4.995 + 6.000 = 10.995 sự kiện/giây

Tỷ trọng tenant whale:
  6.000 / 10.995 ≈ 54,6% tổng ghi
```

Tenant `whale` chỉ chiếm khoảng **0,1% số tenant** nhưng phát sinh **hơn một nửa** tải ghi. Nếu partition key chỉ là `tenant_id`, toàn bộ 6.000 ghi/giây đi vào một phân vùng của tenant ấy.

Trong **một phút**, tenant lớn tạo:

```text
Số hàng mới (giả sử mỗi sự kiện có full primary key khác nhau):
  6.000 × 60 = 360.000 hàng

Payload logic:
  360.000 × 600 byte = 216.000.000 byte
                      = 216 MB ≈ 206 MiB
```

Con số trên **chưa** bao gồm clustering keys, metadata, collection, tombstone, compression và các bản sao replica. Nếu tốc độ giữ nguyên trong 24 giờ, số hàng và byte của một partition key không bucket sẽ tăng rất nhanh.

### Ba dạng giới hạn phải tính riêng

| Rủi ro | Biểu hiện | Vì sao khóa tenant đơn có thể là nguyên nhân |
| --- | --- | --- |
| **Dung lượng phân vùng** | Một partition chứa quá nhiều hàng/cell/byte. | Dữ liệu của tenant tích lũy vào cùng khóa theo thời gian. |
| **Write/read hotspot** | p95/p99 latency và timeout tăng trên một số replica. | Tenant lớn liên tục ghi/đọc đúng một tập replica. |
| **Noisy neighbor** | Tenant nhỏ bị ảnh hưởng dù dữ liệu của họ ít. | Tenant lớn có thể tiêu thụ CPU, I/O, mạng, queue, compaction và tài nguyên chung trên node. |

Một partition lớn chưa chắc nóng, và một partition nóng có thể chưa lớn. Phải quan sát **kích thước và tần suất truy cập**, không chỉ tổng số tenant hay trung bình toàn bảng.

## 4. Thiết kế khóa tenant bắt đầu từ truy vấn

Trước khi chọn schema, hãy liệt kê những câu hỏi mà sản phẩm cần hỗ trợ:

| Truy vấn | Các giá trị ứng dụng có khi đọc | Partition key gợi ý |
| --- | --- | --- |
| Q1: Lấy 100 bản đo gần nhất của một thiết bị trong ngày | Tenant, thiết bị, ngày | `(tenant_id, device_id, event_day)` |
| Q2: Lấy sự kiện mới nhất **toàn tenant** trong một phút | Tenant, phút; biết các shard được cấu hình | `(tenant_id, minute_bucket, shard_id)` |
| Q3: Tra cứu một event từ ID | Tenant, event ID | `(tenant_id, event_id)` |
| Q4: Liệt kê các thiết bị của tenant | Tenant, có thể cần các device shards | `(tenant_id, device_shard)` với `device_id` làm clustering key |
| Q5: Thống kê tổng số sự kiện của tenant trong tháng | Tenant, tháng | Bảng tổng hợp theo tenant/tháng với semantics cập nhật phù hợp |

Một bảng duy nhất khó phục vụ mọi truy vấn tối ưu. Cassandra thường ưu tiên **thiết kế bảng theo truy vấn**, chấp nhận sao chép có kiểm soát và định nghĩa cơ chế ghi/khôi phục khi một nghiệp vụ cần cập nhật nhiều bảng.

**Không suy ra dữ liệu được cập nhật nguyên tử trên nhiều bảng chỉ vì chúng cùng chứa `tenant_id`.** Các thao tác khác partition key hay bảng có thể thành công hoặc thất bại riêng; ứng dụng cần xử lý retry, backfill và đối chiếu.

## 5. Mẫu 1: phân vùng theo tenant–thiết bị–ngày

Nếu truy vấn chính là lịch sử của **một thiết bị trong một ngày**, một bảng tự nhiên là:

```sql
CREATE TABLE device_events_by_day (
    tenant_id   text,
    device_id   uuid,
    event_day   date,
    occurred_at timestamp,
    event_id    uuid,
    event_type  text,
    payload     text,
    PRIMARY KEY (
        (tenant_id, device_id, event_day),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
```

Ba cột `(tenant_id, device_id, event_day)` cùng tạo **partition key ghép**. Các hàng cùng tenant nhưng khác thiết bị hoặc khác ngày thuộc **các phân vùng logic khác nhau**.

### Ghi CQL đúng bucket

```sql
INSERT INTO device_events_by_day (
    tenant_id, device_id, event_day,
    occurred_at, event_id, event_type, payload
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21',
    '2026-11-21T08:30:15Z',
    8817a208-1858-4144-86e9-b24d9083e478,
    'reading',
    'temperature=38.1'
);
```

Quy ước của ví dụ: `event_day` là **ngày UTC** của `occurred_at`. Writer và reader phải thống nhất cách tính bucket; ngày theo giờ địa phương không nhất thiết trùng ngày UTC.

### Đọc đúng một phân vùng

```sql
SELECT occurred_at, event_id, event_type, payload
FROM device_events_by_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND occurred_at >= '2026-11-21T08:00:00Z'
  AND occurred_at <  '2026-11-21T09:00:00Z'
LIMIT 100;
```

Đã cung cấp **đầy đủ partition key** và một khoảng clustering column. Cassandra có thể đọc đúng slice trong phân vùng. `LIMIT 100` giới hạn **số hàng kết quả**, không giới hạn kích thước vật lý của partition hay bảo đảm chỉ đọc 100 cell nếu có tombstone.

### Mẫu này có giải quyết mọi tenant lớn không?

**Không.** Nếu một thiết bị của tenant `whale` chiếm 90% lưu lượng, partition `(whale, thiết_bị_đó, hôm_nay)` vẫn có thể cực nóng. Chia theo thực thể và ngày giảm mức tập trung tổng thể, nhưng không bảo đảm từng partition nhận tải vừa phải.

Nếu cần lịch sử nhiều ngày, ứng dụng phải truy vấn các bucket liên quan rồi tổng hợp theo thứ tự thời gian; clustering order chỉ có phạm vi **một phân vùng**.

## 6. Mẫu 2: timeline toàn tenant theo phút và shard

Một yêu cầu khác là **“lấy 100 sự kiện mới nhất của tenant T trong phút M, bất kể thiết bị”**. Bảng theo thiết bị ở trên không phù hợp để truy vấn trực tiếp vì thiếu `device_id` trong partition key.

Với tenant lớn, có thể tạo **bảng chuyên dụng**:

```sql
CREATE TABLE tenant_events_by_minute_shard (
    tenant_id     text,
    minute_bucket timestamp,
    shard_id      smallint,
    occurred_at   timestamp,
    event_id      uuid,
    device_id     uuid,
    event_type    text,
    payload       text,
    PRIMARY KEY (
        (tenant_id, minute_bucket, shard_id),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
```

Mỗi tenant có **nhiều partition keys đồng thời trong một phút**:

```text
('whale', 08:30Z, shard 0) -> partition A
('whale', 08:30Z, shard 1) -> partition B
...
('whale', 08:30Z, shard 11) -> partition L

Sự kiện được chia vào các shard theo thuật toán ổn định.
```

Giả sử có **12 shard**, và sự kiện được phân bố gần đều:

```text
6.000 sự kiện/giây / 12 shard
  ≈ 500 sự kiện/giây cho mỗi shard

Số hàng mỗi shard/phút:
  500 × 60 = 30.000 hàng

Payload mỗi shard/phút:
  30.000 × 600 byte = 18.000.000 byte
                      = 18 MB ≈ 17,2 MiB
```

Đây là ước lượng lý tưởng, **không** có nghĩa 12 shard chắc chắn nằm trên 12 node khác nhau. Hash token, topology, replication strategy và lượng tải khác trên node vẫn quyết định phân phối thực tế.

### Chọn shard dựa trên ID ổn định

Một quy tắc ví dụ:

```text
shard_id = floorMod(stableHash(event_id), 12)

Partition key =
  (tenant_id, minute_bucket, shard_id)
```

`event_id` phải đại diện **ổn định cho sự kiện nghiệp vụ**, được giữ nguyên khi retry. Không nên chọn shard ngẫu nhiên mới ở mỗi lần gửi lại: nếu shard đổi, toàn bộ primary key có thể đổi và Cassandra sẽ tạo hàng khác cho cùng một sự kiện.

### Ghi và đọc một shard bằng CQL

```sql
INSERT INTO tenant_events_by_minute_shard (
    tenant_id, minute_bucket, shard_id,
    occurred_at, event_id, device_id, event_type, payload
) VALUES (
    'whale',
    '2026-11-21T08:30:00Z',
    7,
    '2026-11-21T08:30:15Z',
    8817a208-1858-4144-86e9-b24d9083e478,
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    'reading',
    'temperature=38.1'
);
```

`shard_id = 7` ở trên chỉ là **giá trị minh họa**. Trong triển khai thực tế, nó phải đúng kết quả hash đã được định nghĩa.

```sql
SELECT occurred_at, event_id, device_id, event_type
FROM tenant_events_by_minute_shard
WHERE tenant_id = 'whale'
  AND minute_bucket = '2026-11-21T08:30:00Z'
  AND shard_id = 7
  AND occurred_at >= '2026-11-21T08:30:00Z'
  AND occurred_at <  '2026-11-21T08:31:00Z'
LIMIT 100;
```

Câu trên đọc **một partition**, không phải toàn tenant. Để lấy top 100 toàn tenant trong phút, phải đọc đủ các shard liên quan, dùng cùng comparator `occurred_at DESC, event_id ASC` để **merge kết quả**, rồi chọn 100 hàng đầu tiên.

Lấy tối đa 100 hàng đầu mỗi shard là cách đủ để tìm top 100 chung nếu tất cả luồng có cùng thứ tự và cùng phạm vi thời gian; tuy nhiên, làm thế có thể đọc dư nhiều dữ liệu. Với dữ liệu lớn, nên merge theo trang và giới hạn concurrency.

## 7. Giới hạn tenant lớn: bucket không thay thế quota

Tăng số phân vùng giúp **phân phối dữ liệu/tải**, nhưng không giải quyết câu hỏi: “Một tenant được phép tiêu thụ bao nhiêu tài nguyên chung?”. Cần có **hạn mức và kiểm soát tải ở tầng dịch vụ**.

Cassandra không nên được giả định có sẵn một hạn mức tự động “mỗi `tenant_id` tối đa X byte/giây” khi nhiều tenant cùng dùng một bảng. Schema với cột `tenant_id` không tự thực thi quota nghiệp vụ.

Có thể xác định chính sách theo các chiều:

| Hạn mức/kiểm soát | Ví dụ chính sách ở ứng dụng | Mục tiêu |
| --- | --- | --- |
| **Tốc độ ghi** | Token bucket theo tenant, cho phép burst ngắn có giới hạn | Chặn tenant lớn dồn toàn bộ tài nguyên ghi. |
| **Số truy vấn đồng thời** | Giới hạn outstanding requests theo tenant | Tránh một tenant chiếm hàng đợi coordinator/replica. |
| **Khối lượng dữ liệu đọc** | Giới hạn cửa sổ thời gian, số trang, số byte trả về | Chặn quét lịch sử quá rộng. |
| **Fan-out** | Giới hạn số bucket × shard phải quét trong một API request | Kiểm soát tổng số partition lookups. |
| **Dung lượng lưu trữ** | Quota theo tổng byte/row ước tính và thời gian retention | Tránh tăng trưởng không kiểm soát. |
| **TTL/retention** | Gói tiêu chuẩn giữ 7 ngày, gói đặc biệt giữ 30 ngày | Cân bằng dịch vụ với chi phí lưu trữ. |
| **Backfill/ingest đột biến** | Queue, điều tiết tốc độ, phân bổ ngân sách riêng | Tránh ảnh hưởng truy vấn tương tác. |
| **Cảnh báo và điều phối** | Cảnh báo p95/p99, tỷ trọng ghi, partition max, node skew | Phát hiện tenant quá lớn trước khi gây sự cố. |

**Các con số trong chính sách phải được quyết định từ SLO và đo tải thực**, không có một giới hạn số hàng hoặc MB chuẩn áp dụng cho mọi Cassandra cluster.

### Token bucket hạn chế ghi theo tenant

Ví dụ chính sách giả định:

```text
Tenant standard:
  rate = 50 write/s
  burst = 200 request

Tenant enterprise:
  rate = 2.000 write/s
  burst = 5.000 request

Tenant whale đặc biệt:
  rate được thương lượng theo tài nguyên riêng
  + shard/bucket phù hợp
  + ngân sách backfill riêng
```

Đây **không phải cấu hình CQL**; nó là logic điều tiết ở cổng API, dịch vụ ingest hoặc hệ thống kiểm soát tải. Nếu nhiều instance cùng phục vụ tenant, phải có **phối hợp hoặc phân bổ quota dùng chung**; mỗi instance tự cho phép đầy đủ quota có thể khiến tổng tải vượt ngân sách.

Khi vượt hạn mức, ứng dụng có thể trả lỗi phù hợp, đưa vào hàng đợi, áp dụng backpressure hoặc yêu cầu retry với độ trễ. Không dùng retry vô hạn vì sẽ khuếch đại sự cố.

### Không dùng một static counter ngây thơ để tính quota chính xác

Ví dụ đọc `total_events` rồi cộng 1 và `UPDATE` vào một cột thường/static có thể **mất cập nhật** khi nhiều writer cùng xử lý. Nếu cần quota hoặc bộ đếm chính xác dưới tải lớn, cần thiết kế cơ chế điều phối, atomicity và tổng hợp tương ứng; không coi một cell Cassandra bình thường là bộ đếm nguyên tử đa tác nhân.

## 8. Phân biệt bucket, shard và giới hạn tenant

Các cơ chế có mục đích khác nhau:

| Biện pháp | Giải quyết chủ yếu | Không tự giải quyết |
| --- | --- | --- |
| **Domain partition key** `(tenant_id, device_id)` | Tách dữ liệu giữa các thực thể của tenant | Một thiết bị cực nóng. |
| **Time bucket** `(tenant_id, device_id, event_day)` | Giới hạn lịch sử tích lũy theo thời gian | Tải cực cao trong **ngày đang hoạt động**. |
| **Shard** `(tenant_id, minute_bucket, shard_id)` | Tạo nhiều partition keys đồng thời để chia tải | Truy vấn top-N không cần merge; chi phí đọc tăng. |
| **TTL** | Giới hạn vòng đời của cell theo thời gian ghi | Chia một partition đang nóng hoặc xóa SSTable tức thời. |
| **Quota/rate limit** | Giới hạn tài nguyên tenant tiêu thụ | Phân phối tốt một partition quá lớn đã có. |
| **Tách cluster/keyspace** | Tăng khả năng phân tách tài nguyên/chính sách | Tự sửa schema partition kém trong từng môi trường. |

Một tenant cực lớn có thể cần **nhiều biện pháp cùng lúc**: schema có bucket/shard, ingest được điều tiết, truy vấn có ngân sách fan-out, retention rõ ràng và giám sát theo tenant.

### Thay đổi số shard cần chính sách phiên bản

Nếu thay `SHARD_COUNT = 12` thành `24`, cùng một `event_id` có thể ánh xạ sang shard khác. Dữ liệu đã ghi **không tự chuyển** sang partition mới. Reader cần biết **cấu hình áp dụng cho dữ liệu lịch sử** hoặc phải thực hiện migration.

Trường hợp tenant lớn cần số shard khác tenant thường cũng có rủi ro tương tự. Không được tự đổi số shard dựa trên số đo tức thời rồi bỏ quên cách đọc các bucket cũ. Một thiết kế tốt sẽ có **chính sách shard theo tenant kèm thời điểm/phiên bản hiệu lực**, đồng thời định nghĩa đường truy vấn cho dữ liệu được ghi dưới cấu hình cũ.

## 9. Truy vấn tenant lớn: chi phí fan-out và quản lý trang

Giả sử `whale` có 12 shard mỗi phút, và dashboard muốn đọc **24 giờ sự kiện**:

```text
24 giờ × 60 phút/giờ × 12 shard/phút
= 17.280 partition keys
```

Một API request đơn lẻ không nên mở 17.280 truy vấn song song để tải về toàn bộ dữ liệu thô. Khi truy vấn có fan-out lớn, hãy xét:

1. **Thu hẹp cửa sổ đọc** (ví dụ tối đa 15 phút cho giao diện tương tác).
2. **Phân trang hoặc streaming kết quả** với giới hạn số hàng/byte.
3. **Giới hạn concurrency** trên driver và tầng dịch vụ.
4. **Dùng bảng tổng hợp chuyên biệt** cho báo cáo theo ngày/tháng thay vì quét event thô.
5. **Cân nhắc dữ liệu lưu trữ ngoài Cassandra** cho truy vấn phân tích dài hạn, nếu yêu cầu và khối lượng phù hợp.
6. **Trả về continuation token/cursor** chứa trạng thái truy vấn hợp lệ; phân trang nhiều shard cần biết tiến độ từng shard hoặc một chiến lược cursor ổn định.

`LIMIT 100` trong một truy vấn shard chỉ giới hạn kết quả của **shard đó**. `ORDER BY` ở Cassandra không tạo thứ tự toàn cục giữa các phân vùng. Khi cần top 100 trên tenant, ứng dụng phải merge theo timestamp và ID sau khi nhận các luồng đã được sắp trong từng partition.

### Các truy vấn không phù hợp

Bảng `device_events_by_day` **không** phù hợp để chạy:

```sql
-- Thiếu device_id và event_day của partition key ghép:
SELECT *
FROM device_events_by_day
WHERE tenant_id = 'whale';
```

Thêm `ALLOW FILTERING` có thể thay đổi khả năng Cassandra chấp nhận một số câu lệnh, nhưng không biến chúng thành truy vấn định vị partition hiệu quả. Nếu API cần “mọi event của tenant”, hãy sử dụng bảng timeline tenant chuyên dụng hoặc cơ chế tổng hợp.

## 10. Tenant isolation: vận hành và bảo mật

Có nhiều mức cô lập giữa tenant:

| Mô hình | Ưu điểm | Hạn chế |
| --- | --- | --- |
| **Shared table/keyspace** với `tenant_id` trong primary key | Ít schema, dễ quản lý số lượng tenant lớn, dùng chung tài nguyên | Cần phân quyền tenant ở ứng dụng, dễ noisy neighbor, quota phải do dịch vụ thực thi. |
| **Keyspace hoặc bảng riêng cho nhóm tenant** | Có thể tách quyền truy cập, cấu hình retention/compaction ở phạm vi tài nguyên được hỗ trợ | Tăng số lượng schema/metadata và chi phí vận hành; vẫn dùng chung node nếu cùng cluster. |
| **Cluster riêng cho tenant đặc biệt** | Cô lập tài nguyên, lịch nâng cấp và công suất rõ ràng hơn | Chi phí hạ tầng, quản trị, migration và giám sát cao hơn. |

Không có mô hình nào mặc nhiên tốt nhất. Tenant rất lớn có thể được **chuyển sang hạ tầng riêng** khi quota và sharding của shared cluster không còn đáp ứng SLO, nhưng việc tách cluster không sửa được một partition key tạo quá nhiều dữ liệu trên chính cluster riêng đó.

### Không dùng `tenant_id` của request làm nguồn tin cậy

Trong một dịch vụ Java nhận JWT/session:

```text
1. Xác thực token/session.
2. Xác định tenant được cấp quyền từ claims/quan hệ tin cậy.
3. Kiểm tra người dùng có quyền với device/event được yêu cầu.
4. Bind tenant_id đã kiểm tra vào prepared statement.
5. Áp dụng quota và ngân sách query theo tenant.
6. Ghi audit log phù hợp khi truy vấn/điều chỉnh dữ liệu.
```

Nếu hệ thống dùng một tài khoản Cassandra chung cho ứng dụng, quyền CQL của tài khoản đó có thể rộng hơn quyền của người dùng cuối. Do đó, bảo vệ ở tầng API/service không phải tính năng tùy chọn. Khi yêu cầu cô lập mạnh hơn, cân nhắc kiến trúc tài khoản, keyspace hoặc cluster riêng tùy threat model.

## 11. TTL, compaction, repair và consistency của tenant lớn

Bucket/shard giải quyết **hình dạng phân vùng**, còn vòng đời lưu trữ và semantics đọc/ghi cần chính sách riêng.

### TTL theo gói tenant

Ví dụ lệnh ghi giữ dữ liệu **7 ngày kể từ thời điểm ghi**:

```sql
INSERT INTO tenant_events_by_minute_shard (
    tenant_id, minute_bucket, shard_id,
    occurred_at, event_id, device_id, event_type, payload
) VALUES (
    'whale',
    '2026-11-21T08:30:00Z',
    7,
    '2026-11-21T08:30:15Z',
    8817a208-1858-4144-86e9-b24d9083e478,
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    'reading',
    'temperature=38.1'
) USING TTL 604800;
```

Khi tenant có retention khác nhau, ứng dụng có thể đặt TTL phù hợp cho mỗi thao tác ghi (nếu schema và phiên bản Cassandra hỗ trợ theo nhu cầu), thay vì giả định toàn bảng có cùng thời hạn. TTL **không đồng nghĩa xóa vật lý ngay**: dữ liệu hết hạn và tombstone có thể còn trên SSTable đến khi compaction dọn theo điều kiện an toàn.

Với **sự kiện đến trễ**, TTL 7 ngày tính từ lúc ghi không giống giữ đến “7 ngày sau event time”. Nếu chính sách retention dựa trên thời điểm nghiệp vụ, phải xác định rõ cách tính TTL và hành vi với event đến trễ.

### Compaction và repair

- Dữ liệu time-series có TTL có thể thích hợp để đánh giá `TimeWindowCompactionStrategy` khi kiểu ghi/TTL phù hợp, nhưng TWCS **không tự chia** một partition lớn.
- Nhiều tombstone, ghi ngược thời gian hoặc cập nhật dữ liệu cũ có thể làm chi phí compaction/đọc tăng.
- Repair đồng bộ trạng thái dữ liệu giữa các replica, không chuyển `tenant_id` sang partition khác hoặc sửa skew.
- Khi xoá dữ liệu, thời gian sửa chữa replica và cấu hình an toàn liên quan tombstone phải được tính đến; không tùy ý giảm `gc_grace_seconds` để dọn nhanh mà bỏ qua nguy cơ dữ liệu xóa xuất hiện trở lại.

### Consistency level

Cả dữ liệu tenant nhỏ và tenant lớn đều dùng semantics consistency level của keyspace/truy vấn. Chọn `LOCAL_ONE`, `LOCAL_QUORUM` hoặc mức khác ảnh hưởng xác nhận đọc/ghi, độ trễ và khả năng quan sát dữ liệu mới; **không** thay đổi token, kích thước phân vùng hay giới hạn throughput trên tenant.

Nếu một tenant lớn gây quá tải replica, chỉ đổi consistency level thường không đủ. Cần giảm hotspot, quản lý concurrency/quota, kiểm tra topology và quan sát thực tế.

## 12. Java Driver: tenant-aware routing, bucket và shard

Ví dụ Java Driver 4.x dưới đây giả định `CqlSession` đã kết nối với keyspace chứa bảng `tenant_events_by_minute_shard`. `tenantId` đã được **xác thực/ủy quyền ở lớp dịch vụ**, không phải chuỗi do người gọi tùy ý chọn.

`eventId` và `occurredAt` phải được tạo **một lần cho sự kiện nghiệp vụ**, rồi giữ nguyên khi retry.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.UUID;

public final class TenantEventRepository {
    private static final int SHARD_COUNT = 12;

    private final CqlSession session;
    private final PreparedStatement insert;
    private final PreparedStatement readOneShard;

    public TenantEventRepository(CqlSession session) {
        this.session = session;

        this.insert = session.prepare(
            "INSERT INTO tenant_events_by_minute_shard " +
            "(tenant_id, minute_bucket, shard_id, occurred_at, " +
            "event_id, device_id, event_type, payload) " +
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        );

        this.readOneShard = session.prepare(
            "SELECT occurred_at, event_id, device_id, event_type " +
            "FROM tenant_events_by_minute_shard " +
            "WHERE tenant_id = ? AND minute_bucket = ? AND shard_id = ? " +
            "AND occurred_at >= ? AND occurred_at < ? LIMIT 100"
        );
    }

    public void writeEvent(
            String verifiedTenantId,
            UUID deviceId,
            Instant occurredAt,
            UUID eventId,
            String eventType,
            String payload) {

        // Dùng event time UTC để xác định bucket.
        Instant minuteBucket = occurredAt.truncatedTo(ChronoUnit.MINUTES);

        // Hash ổn định cho cùng UUID trong Java.
        short shardId = (short) Math.floorMod(eventId.hashCode(), SHARD_COUNT);

        session.execute(insert.bind(
            verifiedTenantId, minuteBucket, shardId,
            occurredAt, eventId, deviceId, eventType, payload
        ));
    }

    public ResultSet readShard(
            String verifiedTenantId,
            Instant minuteBucket,
            short shardId,
            Instant fromInclusive,
            Instant toExclusive) {

        Instant bucketEnd = minuteBucket.plus(1, ChronoUnit.MINUTES);

        if (shardId < 0 || shardId >= SHARD_COUNT ||
            fromInclusive.isBefore(minuteBucket) ||
            !fromInclusive.isBefore(toExclusive) ||
            toExclusive.isAfter(bucketEnd)) {
            throw new IllegalArgumentException(
                "Khoang doc hoac shard khong hop le");
        }

        BoundStatement statement = readOneShard.bind(
            verifiedTenantId, minuteBucket, shardId,
            fromInclusive, toExclusive
        ).setPageSize(50);

        return session.execute(statement);
    }
}
```

Trong triển khai thực:

1. **Không lấy `verifiedTenantId` trực tiếp từ tham số URL** nếu chưa kiểm tra nó gắn với danh tính/role của người gọi.
2. Luôn bind đủ `tenant_id`, `minute_bucket` và `shard_id` để truy vấn xác định được một partition key.
3. `UUID.hashCode()` ổn định theo Java cho cùng UUID, nhưng nếu hệ thống đa ngôn ngữ phải đặc tả thuật toán hash trên bytes và số shard thống nhất.
4. `SHARD_COUNT` là một phần của thiết kế lưu trữ. Khi tenant có chính sách shard riêng, đọc/ghi phải dùng đúng **phiên bản policy** áp dụng cho dữ liệu đó.
5. `LIMIT 100` hạn chế kết quả trong một shard; `setPageSize(50)` là số hàng mong muốn mỗi trang driver. Chúng không thay thế việc kiểm soát tổng số truy vấn fan-out.
6. Không dùng `now()` tạo clustering `timeuuid` mới mỗi lần retry nếu sự kiện cần idempotency. Giữ nguyên **toàn bộ primary key và payload** giữa các lần gửi lại.
7. Đối với throughput cao, áp dụng backpressure, giới hạn số request đồng thời và ngân sách tenant bên ngoài repository; không gửi requests vô hạn vì đã có shard.

Ví dụ dùng thao tác đồng bộ để dễ đọc. Trong hệ thống lớn, API bất đồng bộ của driver có thể cải thiện throughput nếu quản lý concurrency, timeout, retry và paging đúng cách.

## 13. Quan sát tenant lớn và phát hiện noisy neighbor

Không thể suy ra một tenant quá lớn chỉ từ tổng số byte của keyspace. Cần đo **độ lệch theo tenant và partition**, đồng thời theo dõi tài nguyên node:

| Chỉ số | Câu hỏi cần trả lời |
| --- | --- |
| **Event/write rate theo tenant** | Một tenant có chiếm tỷ trọng bất thường trên tổng tải không? |
| **Top read/write partition keys** | Có một số partition key/tenant bucket được truy cập quá nhiều? |
| **Partition size/cell count histogram** | Có outlier về byte hoặc số cell trong partition? |
| **p95/p99 latency và timeout theo tenant/query** | Tenant lớn có kéo đuôi độ trễ của tenant nhỏ tăng? |
| **CPU, I/O, GC, network theo node** | Replica hoặc coordinator nào chịu hotspot? |
| **SSTables per read, tombstones scanned** | Đọc chậm do nhiều dữ liệu/tombstone hay không? |
| **Pending compactions, repair/streaming load** | Công việc nền có bị tăng chi phí bởi tenant lớn? |
| **Quota/rate-limit rejects, queue depth** | Cơ chế kiểm soát tải đang hoạt động hay bị quá tải? |
| **Số bucket/shard được đọc cho một API** | Fan-out có vượt ngân sách đọc đã đặt không? |

Ví dụ công cụ quản trị ở mức bảng, tùy phiên bản:

```bash
nodetool tablestats app_ks.tenant_events_by_minute_shard
nodetool tablehistograms app_ks tenant_events_by_minute_shard
```

Các thống kê đó **không tự phân rã theo tenant**. Để tìm tenant tạo tải lớn, cần kết hợp métrics từ API/ingest, sampling có kiểm soát và các khả năng thống kê hot partition của phiên bản Cassandra đang chạy.

Đừng đưa toàn bộ tenant/user/event ID thành label metric không giới hạn, vì chính hệ thống metrics có thể gặp vấn đề **high-cardinality labels**. Có thể giám sát các nhóm tenant, các top-N tenant, hoặc dùng cách tổng hợp có kiểm soát.

Tránh `SELECT COUNT(*)` trên phân vùng lớn hoặc quét toàn bảng dưới tải cao để ước lượng quota; việc đếm có thể tạo tải đáng kể. Số liệu dung lượng nên lấy từ công cụ thống kê, luồng ingest và công tác đo/đối chiếu được thiết kế có kiểm soát.

## 14. Khi một tenant phải chuyển khỏi shared cluster

Không phải tenant lớn nào cũng cần cluster riêng. Quyết định nên dựa trên **chi phí cô lập tài nguyên** và mục tiêu sản phẩm.

Cân nhắc mô hình riêng khi:

- Tenant đó liên tục chiếm phần lớn CPU, I/O, network hoặc dung lượng dù đã bucket/shard và giới hạn tải.
- SLA, retention, quyền truy cập hoặc vùng dữ liệu khác biệt đáng kể.
- Quá trình repair/backup/khôi phục của một tenant làm ảnh hưởng nhiều tenant khác.
- Chi phí tách tenant hợp lý hơn chi phí liên tục mở rộng shared cluster và quản lý noisy neighbor.

### Quy trình di chuyển có kiểm soát

1. Xác định phạm vi tenant, bảng, partition keys và dữ liệu phụ trợ cần di chuyển.
2. Chuẩn hóa schema, bucket/shard policy, replication strategy và quyền truy cập tại môi trường mới.
3. Chuyển dữ liệu lịch sử có checkpoint, giới hạn throughput và bảo toàn event ID, thời gian, TTL/vòng đời.
4. Dùng dual-write hoặc replay nguồn sự kiện nếu cần, nhưng **không giả định giao dịch nguyên tử giữa hai cluster**.
5. Đọc đối chiếu theo key/bucket/shard, kiểm tra dữ liệu đến trễ, tombstone và ranh giới chuyển đổi.
6. Chuyển định tuyến ghi/đọc của tenant, theo dõi timeout, p99 và độ đầy đủ của dữ liệu.
7. Chỉ ngừng đường cũ và xử lý dữ liệu cũ khi đã xác minh không còn request phụ thuộc.

Việc đổi số shard, TTL hoặc cấu hình consistency trong quá trình di chuyển cần quy ước tường minh. Nếu các reader không biết policy cũ, chúng có thể không tìm thấy dữ liệu lịch sử dù dữ liệu vẫn tồn tại.

## 15. Những sai lầm phổ biến

| Nhận định | Vì sao chưa đúng? | Hướng giải quyết |
| --- | --- | --- |
| “Thêm `tenant_id` vào bảng là đã cô lập bảo mật.” | Một cột không tự thực thi quyền truy cập theo người dùng cuối. | Xác thực/ủy quyền ở API, role phù hợp, cân nhắc tách tài nguyên. |
| “Nhiều tenant thì hash sẽ cân bằng tải.” | Một tenant có thể chiếm phần lớn request/byte. | Đo skew, chia entity/bucket/shard và giới hạn tải. |
| “`PRIMARY KEY (tenant_id, event_time, event_id)` có ba partition keys.” | Chỉ `tenant_id` là partition key; hai cột sau là clustering columns. | Kiểm tra cú pháp dấu ngoặc. |
| “Đưa `device_id` vào partition key ghép thì truy vấn tenant-only vẫn nhanh.” | Hash toàn bộ tuple; không có phép quét prefix tenant mặc định. | Tạo bảng/đường truy cập chuyên dụng. |
| “Bucket ngày đủ vì sau mỗi ngày có partition mới.” | Ngày hiện tại có thể vẫn nhận lượng ghi khổng lồ. | Chọn bucket ngắn hơn hoặc shard khi cần. |
| “12 shard bằng 12 node, chắc chắn hết hotspot.” | Replica placement có thể trùng và tải lệch. | Đo node/replica, thử tải và giới hạn concurrency. |
| “Quota lưu trữ tự bật khi có `tenant_id`.” | Cassandra không tự áp hạn mức nghiệp vụ theo từng giá trị cột trong shared table. | Thực thi quota ở tầng dịch vụ/hệ thống điều phối. |
| “Thay `SHARD_COUNT` ngay trong code không ảnh hưởng lịch sử.” | Cùng event ID có thể hash sang partition khác. | Versioning và migration policy. |
| “Ghi vào hai bảng cùng tenant là transaction nguyên tử.” | Có thể partial failure giữa bảng/partition. | Retry idempotent, reconciliation và giám sát. |
| “TTL xóa dữ liệu vật lý ngay khi hết hạn.” | Dữ liệu hết hạn/tombstone còn phụ thuộc compaction. | Theo dõi retention và tombstone. |
| “Tăng RF/consistency đủ xử lý tenant nóng.” | Không chia nhỏ partition key hoặc tạo quota. | Sửa schema và kiểm soát workload. |

## 16. Bài tập tình huống

Một nền tảng SaaS có **800 tenant**. Một tenant `mega` gửi **9.000 event/giây**, còn 799 tenant khác gửi trung bình **4 event/giây/tenant**. Mỗi event có **700 byte payload**. Sản phẩm hỗ trợ:

- Q1: lấy 50 event mới nhất của **một thiết bị trong một ngày**.
- Q2: lấy 100 event mới nhất của **toàn tenant trong một phút**.
- Q3: báo cáo tổng số event của tenant theo **tháng**.
- Tenant lớn có nguy cơ làm tăng p99 của các tenant nhỏ.

Nhóm thiết kế đề xuất:

```sql
-- A: một partition key cho toàn tenant và mọi thời gian.
PRIMARY KEY (tenant_id, occurred_at, event_id)

-- B: phân vùng theo thiết bị và ngày.
PRIMARY KEY (
    (tenant_id, device_id, event_day),
    occurred_at, event_id
)

-- C: phân vùng theo tenant, phút và shard.
PRIMARY KEY (
    (tenant_id, minute_bucket, shard_id),
    occurred_at, event_id
)
```

**Câu hỏi:**

1. Với A, `tenant_id` là partition key hay một thành phần của clustering key?
2. Tenant `mega` chiếm bao nhiêu phần trăm tổng lưu lượng ghi, xấp xỉ?
3. Theo A, một phút của tenant lớn tạo bao nhiêu hàng và bao nhiêu MB payload logic?
4. B phù hợp nhất với Q1 hay Q2?
5. C với **18 shard** phân phối lý tưởng sẽ nhận bao nhiêu ghi/giây/shard?
6. Nếu đọc top 100 toàn tenant bằng C, có thể chỉ truy vấn shard số 0 không?
7. Q3 có nên quét mọi partition phút/shard của cả tháng mỗi lần mở dashboard không?
8. Vì sao quota theo tenant và chia shard là hai giải pháp có mục tiêu khác nhau?
9. Nếu ứng dụng tin `tenant_id` gửi từ client mà không kiểm tra quyền, rủi ro nào xuất hiện?
10. Đổi số shard từ 18 thành 36 mà không versioning ảnh hưởng gì tới dữ liệu đã ghi?

**Đáp án giải thích:**

1. `tenant_id` là **partition key đơn**; `occurred_at` và `event_id` là clustering columns.
2. Tổng `9.000 + 799 × 4 = 12.196 ghi/giây`. Tenant `mega` chiếm `9.000/12.196 ≈ 73,8%` tải ghi.
3. `9.000 × 60 = 540.000 hàng/phút`; `540.000 × 700 = 378.000.000 byte = 378 MB ≈ 360,5 MiB` payload, chưa overhead/replica.
4. **B phù hợp Q1**; vì Q2 không biết một `device_id` cụ thể, cần đường truy cập timeline tenant khác.
5. `9.000 / 18 = 500 ghi/giây/shard` theo giả định lý tưởng, chưa chắc tương ứng 18 node hay replica sets khác nhau.
6. **Không.** Phải đọc các shard liên quan, merge theo thứ tự thời gian/ID rồi lấy top 100.
7. Thường **không**. Q3 phù hợp bảng tổng hợp/công cụ phân tích hoặc quy trình báo cáo riêng với độ chính xác và độ trễ được xác định rõ.
8. **Shard phân tán** ghi của một bucket ra nhiều partition keys; **quota kiểm soát** tổng tài nguyên tenant được phép dùng. Cần phối hợp hai cơ chế.
9. Có thể xảy ra **truy cập hoặc thao tác dữ liệu xuyên tenant trái phép**; tenant ID trong schema không thay cho ủy quyền.
10. Event cũ vẫn ở shard theo hash 18; reader dùng 36 có thể tìm sai partition, hoặc retry ghi cùng sự kiện sang khóa mới. Cần policy versioning/migration.

## 17. Ghi nhớ

- Trong multi-tenancy, `tenant_id` là **thành phần nhận diện miền nghiệp vụ**, nhưng **không nên tự động dùng nó làm partition key duy nhất** cho dữ liệu tăng liên tục của tenant lớn.
- Partition key ghép như `(tenant_id, device_id, event_day)` giúp chia dữ liệu theo thực thể và thời gian; một tenant có nhiều phân vùng thay vì một phân vùng khổng lồ.
- Câu truy vấn phải **biết đủ thành phần partition key** hoặc có đường truy cập khác. Composite key không tạo chỉ mục tìm theo prefix tenant mặc định.
- Tenant rất lớn có thể cần **time bucketing, shard, TTL và chính sách quota/rate limit** đồng thời; mỗi biện pháp giải quyết một nguyên nhân khác nhau.
- Shard làm tăng fan-out đọc và phải có **thuật toán định tuyến ổn định**, policy versioning và merge kết quả.
- `tenant_id` **không tự bảo đảm phân quyền hay cô lập tài nguyên**. Lớp dịch vụ phải thực thi tenant-aware authorization, quota và backpressure.
- Replication, consistency level, compaction và repair ảnh hưởng độ bền, hiệu năng và vận hành, nhưng **không tự chia một hot partition hoặc giới hạn một tenant quá lớn**.
- Quyết định giữ tenant chung hay tách cluster cần dựa trên **SLO, skew, chi phí vận hành và yêu cầu cô lập**, được chứng minh bằng metrics thực tế.

Thiết kế khóa tenant đúng giúp Cassandra phục vụ nhiều khách hàng trên một kiến trúc phân tán mà vẫn kiểm soát phân vùng, độ trễ và quyền truy cập. Khi số tenant và mức sử dụng tăng, mô hình dữ liệu, chính sách quota, vận hành replica và ứng dụng Java phải cùng tuân theo một quy tắc định tuyến/giới hạn rõ ràng.

