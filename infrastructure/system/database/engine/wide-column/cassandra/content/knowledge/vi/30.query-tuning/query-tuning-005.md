# Giảm projection, kích thước kết quả và số lần trao đổi mạng

## Mục tiêu bài học

Khi tối ưu truy vấn Apache Cassandra, nhiều nhóm chỉ chú ý câu `WHERE` có dùng **partition key** hay không. Đây là điều kiện cần, nhưng chưa đủ: một truy vấn đã định vị đúng partition vẫn có thể chậm vì trả quá nhiều **cột**, quá nhiều **hàng**, phải chuyển nhiều **trang kết quả** hoặc bị ứng dụng Java gọi lặp lại theo kiểu **N+1 queries**.

Trong chương **Tối ưu truy vấn** của module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`, bài này tập trung vào ba đòn bẩy liên quan nhưng không đồng nhất:

1. **Giảm projection:** chỉ `SELECT` những cột thực sự cần cho màn hình hoặc API.
2. **Giảm kích thước kết quả:** giới hạn khoảng clustering, số hàng, độ lớn từng giá trị và số trang cần đọc.
3. **Giảm trao đổi mạng:** tránh gọi nhiều câu CQL liên tiếp khi một đường đọc có giới hạn hoặc một bảng theo truy vấn có thể đáp ứng; quản lý paging, đồng thời và round-trip ở Java Driver.

Sau bài học, bạn có thể:

- Phân biệt lượng dữ liệu **Cassandra phải xử lý**, lượng dữ liệu **server gửi về client**, và số **request/response** qua mạng.
- Viết CQL chỉ lấy cột cần thiết, có đủ partition key, clustering range và `LIMIT` hợp lý.
- Hiểu vì sao `SELECT *`, JSON/blob lớn, phân trang quá nhỏ, hoặc nạp hàng loạt chi tiết từng dòng làm p95/p99 latency tăng.
- Thiết kế hai dạng bảng phục vụ **danh sách ngắn** và **chi tiết khi người dùng yêu cầu**.
- Sử dụng **prepared statement, page size, asynchronous paging** và giới hạn tổng số hàng với Cassandra Java Driver 4.x.
- Xây thí nghiệm so sánh số byte, số trang, tổng round-trip, CPU/GC, thời gian và độ trễ ứng dụng.
- Liên hệ tối ưu query với RF, consistency level, replication, compaction, tombstone và vận hành đa datacenter.

## 1. Một truy vấn có thể tốn chi phí ở ba tầng

Giả sử API cần hiển thị **20 đơn hàng mới nhất** của một khách hàng. Mỗi đơn hàng có trạng thái, số tiền và một blob biên nhận vài trăm KiB. Nếu dùng `SELECT *`, API có thể tải cả blob về để rồi bỏ đi khi tạo JSON danh sách.

~~~mermaid
flowchart LR
    A["HTTP GET /orders"] --> B["Java service"]
    B --> C["Cassandra coordinator"]
    C --> D["Replica: đọc partition / SSTable"]
    D --> C
    C -->|"CQL response: cột + hàng đã chọn"| B
    B -->|"JSON cho client"| A
~~~

Phân biệt rõ:

| Tầng | Nguồn chi phí | Tối ưu chính |
| --- | --- | --- |
| **Replica / storage** | Định vị partition, đọc memtable/SSTable, giải mã, tombstone, reconciliation | Chọn đúng partition key/clustering range; hạn chế quét rộng và partition quá lớn |
| **Cassandra protocol / mạng** | Serialize giá trị trả về, truyền coordinator ↔ client, có thể qua WAN | Projection cột nhỏ, giới hạn số hàng và số trang, đặt client gần DC |
| **Ứng dụng Java / HTTP** | Giải mã Row, cấp phát bộ nhớ, tạo DTO/JSON, gọi CQL nhiều lượt | Tối ưu DTO, lazy details, chuẩn hóa paging, tránh N+1, backpressure |

**Giảm projection thường giảm kích thước response và công giải mã**, nhất là khi bỏ các cột text/blob lớn. Nhưng Cassandra **không phải** một engine columnar OLAP và chi phí đọc SSTable vật lý không giảm tuyến tính với số cột trả ra. Việc giảm `SELECT` từ 10 cột xuống 4 cột **không bảo đảm** I/O đĩa giảm đúng 60%.

Tương tự, giảm số **lệnh CQL phía client** không có nghĩa số thông điệp giữa coordinator và replica luôn bằng số lệnh CQL. Một lần đọc ở `LOCAL_QUORUM` có thể tạo data/digest requests và read repair; CL, RF và speculative execution quyết định thêm chi phí trong cluster.

## 2. Projection: SELECT đúng những cột API cần

### 2.1. Schema minh họa: một hàng có cả dữ liệu danh sách và chi tiết

Giả sử ứng dụng lưu đơn hàng theo **tenant + khách hàng + tháng**, sắp theo thời gian tạo:

~~~sql
-- Chỉ chạy trong lab. Thay datacenter1 bằng tên DC thực tế.
CREATE KEYSPACE IF NOT EXISTS query_tuning_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'datacenter1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS query_tuning_lab.orders_by_customer_month (
    tenant_id text,
    customer_id uuid,
    month_bucket text,
    created_at timestamp,
    order_id uuid,
    status text,
    total_minor bigint,
    details_json text,
    receipt_blob blob,
    PRIMARY KEY ((tenant_id, customer_id, month_bucket),
                 created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC);
~~~

Giải thích:

- `(tenant_id, customer_id, month_bucket)` là **composite partition key**. Một màn hình biết đủ ba thành phần sẽ truy vấn **đúng một partition**.
- `created_at` và `order_id` là clustering columns theo thứ tự giảm dần. Bổ sung `order_id` để phân biệt những đơn có timestamp trùng nhau.
- `status`, `total_minor` đủ để hiển thị danh sách; `details_json` và `receipt_blob` chỉ cần khi mở chi tiết đơn.
- Số tiền dùng đơn vị nhỏ nhất trong `bigint` để tránh lỗi số thực; `month_bucket` là `YYYY-MM` được ứng dụng chuẩn hóa theo cùng timezone.
- Đây là một bảng minh họa tác động của projection. Nếu phần chi tiết rất lớn hoặc truy cập hoàn toàn khác, mục 6 sẽ tách thành **bảng theo truy vấn**.

Nạp một hàng ví dụ:

~~~sql
INSERT INTO query_tuning_lab.orders_by_customer_month
    (tenant_id, customer_id, month_bucket, created_at, order_id,
     status, total_minor, details_json, receipt_blob)
VALUES (
    'tenant-a', 11111111-1111-4111-8111-111111111111,
    '2026-11', '2026-11-21T09:30:00Z',
    22222222-2222-4222-8222-222222222222,
    'PAID', 20500,
    '{"shipping":"standard","notes":"sample"}',
    0x01020304
);
~~~

`receipt_blob` chỉ có 4 byte trong ví dụ để thực hành CQL. Trong môi trường thật, blob lớn cần được đánh giá: nhiều hệ thống nên lưu object ở object storage, chỉ lưu metadata/URI/quyền truy cập trong Cassandra, tùy yêu cầu bảo mật và vòng đời dữ liệu.

### 2.2. Không nên SELECT *

~~~sql
-- Chạy được nhưng không phù hợp nếu API chỉ hiển thị danh sách:
SELECT *
FROM query_tuning_lab.orders_by_customer_month
WHERE tenant_id = 'tenant-a'
  AND customer_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
LIMIT 20;
~~~

`SELECT *` trả mọi cột được truy vấn cho các hàng đã chọn, bao gồm `details_json` và `receipt_blob`. Thêm cột mới vào bảng có thể làm payload của cùng API tăng mà client không hề thay code.

Thay bằng projection tường minh:

~~~sql
SELECT created_at, order_id, status, total_minor
FROM query_tuning_lab.orders_by_customer_month
WHERE tenant_id = 'tenant-a'
  AND customer_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
LIMIT 20;
~~~

Màn hình có thể biết `tenant_id`, `customer_id` và `month_bucket` từ request nên không cần trả lại ba giá trị đó ở mọi hàng nếu không có yêu cầu cụ thể. `ORDER BY` mặc định đã theo clustering order của bảng; với một partition, có thể viết `ORDER BY created_at DESC, order_id DESC` để nêu rõ ý định nếu cần, nhưng không phải để sắp xếp tùy ý trên nhiều partition.

**Quy tắc:** projection phản ánh **hợp đồng trả dữ liệu** của API, không chỉ schema. Khi có nhiều màn hình, định nghĩa những câu `SELECT` riêng thay vì một DTO “siêu lớn” chứa tất cả cột.

### 2.3. Đừng nhầm projection với điều kiện lọc

`SELECT order_id, status` chỉ thay **cột trả ra**. Nó không thu hẹp **hàng** phải tìm nếu `WHERE` vẫn quá rộng.

Ví dụ không nên coi là tối ưu chỉ vì trả hai cột:

~~~sql
-- Ví dụ truy vấn không thiết kế đúng khóa:
SELECT order_id, status
FROM query_tuning_lab.orders_by_customer_month
WHERE status = 'PAID'
ALLOW FILTERING;
~~~

Tùy phiên bản/schema, truy vấn có thể bị từ chối hoặc chấp nhận với nguy cơ quét rộng; `ALLOW FILTERING` không tự tạo partition key và không bảo đảm ít I/O. Cần thiết kế bảng theo **truy vấn tìm đơn theo trạng thái** nếu đây là chức năng thường xuyên.

## 3. Giảm số hàng và phạm vi dữ liệu

### 3.1. Khoanh đúng partition và clustering range

Với bucket một tháng, một khách hàng có thể có nhiều đơn. Nếu chỉ xem đơn trong ngày:

~~~sql
SELECT created_at, order_id, status, total_minor
FROM query_tuning_lab.orders_by_customer_month
WHERE tenant_id = 'tenant-a'
  AND customer_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
  AND created_at >= '2026-11-21T00:00:00Z'
  AND created_at <  '2026-11-22T00:00:00Z'
LIMIT 20;
~~~

Khi truy vấn đã biết partition key và khoảng clustering, Cassandra có thể giới hạn phạm vi đọc hiệu quả hơn so với việc truy vấn một khoảng thời gian không có thiết kế khóa phù hợp. Với bảng có clustering `DESC`, các hàng mới nằm trước theo thứ tự mặc định.

Không bỏ `month_bucket` rồi mong `created_at` thay thế được partition key. Nếu yêu cầu trải qua nhiều tháng, ứng dụng phải lập danh sách **số bucket có giới hạn** và hợp nhất kết quả có kiểm soát, hoặc thiết kế một bảng khác phù hợp với màn hình.

### 3.2. LIMIT hữu ích nhưng không phải giới hạn byte hay I/O tuyệt đối

`LIMIT 20` giới hạn **số hàng kết quả**, không phải “20 KiB” hoặc “chỉ xử lý 20 SSTable entries”.

- Hai mươi hàng có `receipt_blob` rất lớn vẫn có thể tạo payload nhiều MiB nếu dùng `SELECT *`.
- Nhiều tombstone hoặc dữ liệu hết TTL có thể khiến server kiểm tra nhiều dữ liệu hơn 20 hàng sống.
- Một query thiếu partition key nhưng có `LIMIT` vẫn có thể quá tốn kém.
- `LIMIT` không tự bảo đảm partition không bị nóng hoặc quá rộng.

Thêm giới hạn ở **API**: `pageSize` tối đa, khoảng ngày tối đa, số bucket tối đa và tổng số phần tử được phép trả. Client không nên được tùy ý yêu cầu hàng trăm nghìn hàng chỉ bằng tham số `?limit=999999`.

### 3.3. Không phân trang kiểu OFFSET

SQL quan hệ có mẫu `LIMIT 20 OFFSET 100000`, nhưng Cassandra CQL không hỗ trợ mô hình OFFSET tùy ý như một engine scan/sort toàn tập. Ngay cả trong các hệ hỗ trợ OFFSET, bỏ qua lượng lớn hàng trước trang hiện tại cũng thường tốn tài nguyên.

Với Cassandra, dùng:

1. **Driver/server paging state** để đọc trang kế tiếp của **cùng truy vấn**.
2. **Cursor theo clustering key** khi đã thiết kế và kiểm chứng chính xác thứ tự, điều kiện biên, timestamp trùng và hành vi khi dữ liệu thay đổi.

**Paging state là một token opaque**, không phải số trang và không phải hợp đồng snapshot bất biến giữa các lần gọi. Nếu API gửi paging token cho client, phải ràng buộc nó với user/tenant, câu truy vấn, bộ tham số, thời hạn và bảo vệ chống giả mạo/đọc chéo; không nhận token tùy ý như một khóa tin cậy.

## 4. Ước lượng kích thước kết quả thay vì chỉ đếm hàng

Giả sử một hàng đơn hàng có:

| Thành phần | Kích thước *minh họa* |
| --- | ---: |
| `order_id`, thời gian, trạng thái, tổng tiền và overhead | 200 byte |
| `details_json` | 4 KiB |
| `receipt_blob` | 256 KiB |

Với 50 hàng:

- Projection danh sách: khoảng `50 × 200 = 10.000 byte`, chưa tính framing/compression và overhead khác.
- `SELECT *` gồm chi tiết: khoảng `50 × (200 + 4.096 + 262.144) ≈ 13,3 MB` dữ liệu giá trị thô.

Đây là **số minh họa để ước lượng**, không phải benchmark Cassandra. Kích thước thực phụ thuộc dữ liệu, null, kiểu cột, encoding, protocol, nén giao tiếp, metadata và cách driver biểu diễn giá trị. Mục đích: **50 hàng không phải lúc nào cũng “nhỏ”**.

Một cách lập ngân sách:

~~~text
estimated_response_bytes
    ≈ rows_returned × average_selected_cell_bytes
      + CQL_protocol_overhead

estimated_pages
    ≈ ceil(rows_returned / effective_page_size)
      (đây chỉ là ước lượng; server có thể trả trang ngắn hơn)
~~~

Nếu API có SLO p95 80 ms và payload 13 MB, tối ưu một vài mili giây ở Java thường không bù được chi phí truyền/giải mã payload. Cần đo thực tế; không dùng một công thức byte để suy ra latency cố định.

## 5. Paging: giảm bộ nhớ nhưng đừng tăng round-trip quá mức

Cassandra phân trang kết quả để tránh phải giữ toàn bộ tập dữ liệu trong bộ nhớ rồi truyền một lần. Java Driver 4.x cho phép đặt `pageSize`, tương ứng gợi ý số hàng mỗi trang kết quả trên server.

| Cấu hình | Lợi ích | Rủi ro/đánh đổi |
| --- | --- | --- |
| Trang rất nhỏ, ví dụ 5 hàng | Mỗi response nhỏ, hiển thị nhanh vài hàng đầu | Nếu người dùng cần 100 hàng sẽ phát sinh nhiều request fetch-next-page |
| Trang trung bình, ví dụ 25–100 hàng | Cân bằng payload và số lần fetch cho danh sách | Vẫn phải giám sát độ lớn từng hàng |
| Trang rất lớn, ví dụ 5.000 hàng | Ít trang hơn nếu thực sự cần đọc rất nhiều | Payload lớn, bộ nhớ/GC, network, p99 và mất kiểm soát API |

**Page size không phải giới hạn tổng số hàng.** `setPageSize(25)` có thể trả nhiều trang 25 hàng khi driver/ứng dụng tiếp tục fetch; nó không tương đương `LIMIT 25`. Dùng song song:

- `LIMIT` hoặc phạm vi clustering để có **trần số hàng trả ra**.
- `setPageSize` để điều chỉnh **số hàng mỗi lượt fetch**.
- **Giới hạn ứng dụng** về số trang, số hàng và tổng byte chấp nhận.

### Mỗi lần fetch trang là một bước trao đổi bổ sung

~~~mermaid
sequenceDiagram
    participant UI as UI/API
    participant Java as Java Driver
    participant C as Cassandra coordinator
    UI->>Java: Danh sách 25 đơn đầu
    Java->>C: SELECT ... LIMIT 100 (page size 25)
    C-->>Java: Trang 1 + paging state
    Java-->>UI: 25 đơn đầu
    Note over UI: Người dùng yêu cầu xem tiếp
    UI->>Java: Trang kế tiếp
    Java->>C: Fetch page 2 (cùng truy vấn)
    C-->>Java: Trang 2 + trạng thái tiếp
    Java-->>UI: 25 đơn kế
~~~

**Không tải trước mọi trang vô điều kiện** nếu người dùng chỉ mở trang đầu. Ngược lại, nếu một báo cáo thực sự cần quét tập dữ liệu có giới hạn và thường mất thời gian giữa mỗi round-trip, trang quá nhỏ có thể làm tổng thời gian tăng. Chọn page size bằng benchmark cùng dữ liệu/tải thật, không theo một giá trị “tối ưu cho mọi hệ thống”.

Một số truy vấn có thể trả trang ngắn hơn page size do giới hạn server, partition/tombstone hoặc điều kiện truy vấn. **Chỉ dùng tín hiệu `hasMorePages`/paging state của driver**, không suy ra “trang ít hơn 25 hàng nghĩa là đã hết”.

## 6. Thiết kế bảng list/detail để tránh đưa dữ liệu nặng qua mỗi request

Nếu danh sách được đọc nhiều nhưng chi tiết hiếm khi mở, có thể tách **bảng theo truy vấn**:

~~~sql
CREATE TABLE IF NOT EXISTS query_tuning_lab.orders_list_by_customer_month (
    tenant_id text,
    customer_id uuid,
    month_bucket text,
    created_at timestamp,
    order_id uuid,
    status text,
    total_minor bigint,
    PRIMARY KEY ((tenant_id, customer_id, month_bucket),
                 created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC);

CREATE TABLE IF NOT EXISTS query_tuning_lab.order_details_by_id (
    tenant_id text,
    order_id uuid,
    details_json text,
    receipt_blob blob,
    PRIMARY KEY ((tenant_id, order_id))
);
~~~

Bảng `orders_list_by_customer_month` chỉ chứa các cột danh sách. Bảng `order_details_by_id` cho phép tìm chi tiết đúng bằng **partition key gồm tenant và order ID**, không đòi quét tất cả đơn của tenant.

Luồng CQL:

~~~sql
-- Danh sách 20 đơn gần nhất:
SELECT created_at, order_id, status, total_minor
FROM query_tuning_lab.orders_list_by_customer_month
WHERE tenant_id = 'tenant-a'
  AND customer_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
LIMIT 20;

-- Chỉ khi người dùng mở một đơn:
SELECT details_json, receipt_blob
FROM query_tuning_lab.order_details_by_id
WHERE tenant_id = 'tenant-a'
  AND order_id = 22222222-2222-4222-8222-222222222222;
~~~

**Đánh đổi:** Cassandra tối ưu nhờ **denormalization và bảng theo truy vấn**, nhưng phải ghi dữ liệu liên quan vào nhiều bảng; không được giả định các ghi ở **hai partition/bảng** là một transaction nguyên tử chung. Khi ghi một đơn hàng, cần có chính sách retry idempotent, event/outbox hoặc đối soát để list và detail không lệch. Nếu mọi trang danh sách luôn phải hiển thị `details_json`, tách bảng có thể lại tạo nhiều request hơn và không có lợi.

### Vì sao không dùng một bảng detail với partition chỉ theo tenant?

Nếu `order_details_by_id` có `PRIMARY KEY ((tenant_id), order_id)`, một tenant rất lớn có thể sở hữu partition khổng lồ. Khóa `PRIMARY KEY ((tenant_id, order_id))` trong ví dụ cho một **partition theo cặp tenant + order**, giúp đọc một đơn cụ thể bằng hai giá trị có sẵn và tránh partition không giới hạn.

Để hỗ trợ truy vấn “xem các đơn của customer trong tháng” và “xem một đơn theo order ID”, **hai bảng với hai khóa khác nhau** là cách phổ biến hơn việc ép một truy vấn không khớp partition key vào `ALLOW FILTERING`.

## 7. Số lần trao đổi mạng và bài toán N+1 trong Java

Giả sử API danh sách trả 20 đơn và một lập trình viên viết:

~~~text
1 câu CQL: SELECT 20 order_id trong tháng.
20 câu CQL tiếp: với mỗi order_id, SELECT details_json/receipt_blob.

Tổng: 21 lệnh CQL phía client cho một request HTTP.
~~~

Ngay cả nếu mỗi query đều có partition key và rất nhanh trong lab, tổng số request và kết nối cạnh tranh tăng theo số đơn. Các request có thể phải đi qua network, coordinator, replica và cấp phát đối tượng kết quả riêng.

**Hướng chọn phụ thuộc giao diện:**

- Nếu **màn hình chỉ hiển thị status/tổng tiền**: một câu CQL projection trên bảng list thường đủ, không tải chi tiết.
- Nếu **người dùng mở một đơn**: thêm đúng một query detail khi thật sự cần.
- Nếu **màn hình luôn hiển thị 20 chi tiết**: cân nhắc bảng/query tối ưu riêng hoặc cấu trúc danh sách có sẵn phần cần thiết, thay vì 20 query tùy tiện.
- Nếu cần nhiều partition: lập **giới hạn fan-out** và xử lý concurrency có kiểm soát; một câu `IN` lớn hoặc vòng lặp hàng nghìn request không phải phép tối ưu tự động.

**CQL BATCH không phải batch SELECT.** `BEGIN BATCH ... APPLY BATCH` phục vụ nhóm thao tác ghi, không gom 20 câu `SELECT` thành một lần query. Không dùng logged batch để “tối ưu N+1 reads”; nó chỉ có thể tăng tải ghi và batchlog.

### Round-trip thực tế không chỉ là 21/1

Số lệnh CQL phía client là một chỉ số hữu ích, nhưng một yêu cầu ở `LOCAL_QUORUM` thường liên lạc với nhiều replica; retry/speculative execution có thể tạo thêm request vật lý. Với nhiều DC, định tuyến client sai DC tạo latency WAN dù mỗi API chỉ chạy một câu CQL.

Hãy đo:

- **Client CQL requests per HTTP request**, số retry và speculative executions.
- **Server pages fetched per request**, số hàng và kích thước response.
- **p95/p99** thời gian CQL, HTTP tổng, serialization/deserialization.
- **Bytes gửi/nhận**, băng thông network, pool saturation, GC, timeout.

Giảm số query nhưng làm một query lớn tới hàng chục MiB có thể **tệ hơn** nhiều query nhỏ có giới hạn; cần cân bằng bằng dữ liệu thực nghiệm.

## 8. Java Driver 4.x: projection, paging bất đồng bộ và giới hạn

### 8.1. Truy vấn danh sách gọn và an toàn

Ví dụ sau dùng **Cassandra Java Driver 4.x**, Java 17 và bảng `orders_list_by_customer_month`. Nó giữ `CqlSession` dùng lại, chuẩn bị câu lệnh một lần, dùng `LOCAL_QUORUM` và trả tối đa **hai trang**, mỗi trang mục tiêu **25 hàng**. CQL cũng giới hạn **100 hàng** để tránh truy vấn không kiểm soát.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

public final class OrderListReader {
    private static final int PAGE_SIZE = 25;
    private static final int MAX_PAGES = 2;
    private static final int MAX_ROWS = 50;

    public record OrderSummary(
        Instant createdAt, UUID orderId, String status, long totalMinor) {}

    private final CqlSession session;
    private final PreparedStatement readList;

    public OrderListReader(CqlSession session) {
        this.session = session;
        this.readList = session.prepare(
            "SELECT created_at, order_id, status, total_minor " +
            "FROM query_tuning_lab.orders_list_by_customer_month " +
            "WHERE tenant_id = ? AND customer_id = ? " +
            "AND month_bucket = ? LIMIT 100");
    }

    public CompletionStage<List<OrderSummary>> readBounded(
            String tenantId, UUID customerId, String monthBucket) {
        if (tenantId == null || tenantId.isBlank()
                || customerId == null
                || monthBucket == null
                || !monthBucket.matches("\\d{4}-\\d{2}")) {
            throw new IllegalArgumentException("Khóa đọc không hợp lệ");
        }

        BoundStatement statement = readList.bind(
                tenantId, customerId, monthBucket)
            .setPageSize(PAGE_SIZE)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotence(true);

        return session.executeAsync(statement)
            .thenCompose(first -> collect(first, new ArrayList<>(), 1));
    }

    private CompletionStage<List<OrderSummary>> collect(
            AsyncResultSet page, ArrayList<OrderSummary> rows, int pageNo) {
        for (Row row : page.currentPage()) {
            if (rows.size() >= MAX_ROWS) {
                return CompletableFuture.completedFuture(List.copyOf(rows));
            }
            rows.add(new OrderSummary(
                row.getInstant("created_at"),
                row.getUuid("order_id"),
                row.getString("status"),
                row.getLong("total_minor")));
        }

        if (pageNo >= MAX_PAGES || !page.hasMorePages()) {
            return CompletableFuture.completedFuture(List.copyOf(rows));
        }
        return page.fetchNextPage()
            .thenCompose(next -> collect(next, rows, pageNo + 1));
    }
}
~~~

**Giải thích trọng tâm:**

- Java `SELECT` **chỉ trả bốn cột** cần cho `OrderSummary`, không tải `details_json` hoặc `receipt_blob`.
- `WHERE` có đầy đủ ba thành phần partition key. Câu CQL giới hạn tổng số hàng ở `LIMIT 100`; hàm còn có **trần ứng dụng 2 trang/50 hàng**.
- `setPageSize(25)` điều khiển kích thước trang server, **không phải** `LIMIT 25`. `currentPage()` duyệt các hàng đã nhận của trang hiện tại.
- `fetchNextPage()` là request bổ sung. Ví dụ chỉ gọi nếu cần một trang thứ hai và `hasMorePages()` còn đúng; không fetch vô hạn.
- `CompletionStage` giữ luồng bất đồng bộ, không gọi `join()` trong vòng lặp để chặn một thread cho từng trang. Ứng dụng HTTP vẫn phải quản lý concurrency/backpressure và timeout phía ngoài.
- `setIdempotence(true)` phù hợp câu `SELECT` đọc thuần; không sao chép cho thao tác ghi có side effect mà chưa đánh giá.
- `LOCAL_QUORUM` giả định cấu hình RF/DC phù hợp. Nếu client được route đến DC khác, latency và độ mới dữ liệu có thể khác.

Đây là **mẫu thu thập tối đa 50 hàng** cho một tác vụ có giới hạn. Nếu UI chỉ cần trang đầu, **nên dừng ở `currentPage()` đầu tiên** và chỉ fetch sau khi nhận thao tác “xem tiếp”. Ví dụ thu hai trang để minh họa cách đếm round-trip; không có ý khuyên luôn tải trước trang hai.

### 8.2. Không dùng “đọc tất cả rồi subList”

Một cách viết không tối ưu là:

~~~java
// Ví dụ phản mẫu: có thể kéo nhiều trang, tăng memory và network.
// KHÔNG dùng với tập dữ liệu có thể tăng không giới hạn.
List<Row> allRows = session.execute(statement).all();
List<Row> firstTwenty = allRows.subList(0, Math.min(20, allRows.size()));
~~~

`ResultSet.all()` có thể kích hoạt fetch nhiều trang để thu đủ kết quả rồi mới cắt tại Java. Nếu người dùng chỉ cần 20 hàng, hãy **giới hạn từ CQL và pagination ngay tại server**, không cắt sau khi đã tải về.

### 8.3. Prepared statement có giúp giảm round-trip không?

`PreparedStatement` hữu ích cho việc tái sử dụng query shape, bind tham số an toàn và tránh gửi lại toàn bộ quá trình chuẩn bị cho mỗi request. Tuy nhiên:

- Lần `prepare` đầu tiên vẫn cần trao đổi với server; driver có cache và có thể phải reprepare khi cần.
- Prepared statement **không biến 20 lệnh SELECT thành 1 lệnh**.
- Bind tham số giúp tránh ghép query string mỗi lượt, nhưng cải thiện chính vẫn là **khóa truy vấn, payload, page size và số request**.

## 9. Mối liên hệ với replication, consistency, tombstone và compaction

### Consistency level và số replica tham gia

Giả sử RF=3 tại một DC:

| Read CL | Số phản hồi tối thiểu cần trong DC local | Tác động kỳ vọng |
| --- | --- | --- |
| `LOCAL_ONE` | 1 | Có thể ít round-trip/độ trễ hơn, nhưng đọc từ replica có thể cũ |
| `LOCAL_QUORUM` | 2 | Tăng điều kiện phản hồi; có thể cần data/digest comparison, read repair |
| `ALL` | 3 | Nhạy với replica chậm/down; không phải mặc định để “tối ưu tốc độ” |

**Giảm projection không làm giảm số ACK/phản hồi mà CL yêu cầu.** Projection xử lý lượng cột trả về; CL quyết định phạm vi đáp ứng về replica. Với workload nhạy độ mới, không tự đổi `LOCAL_QUORUM` xuống `LOCAL_ONE` chỉ để cải thiện benchmark.

### Tombstone, TTL và SELECT nhỏ nhưng chậm

Một `SELECT ... LIMIT 20` có thể phải duyệt nhiều tombstone hoặc hàng đã hết TTL trước khi đủ 20 hàng sống. Vì vậy:

- Đo **tombstone scanned**, số SSTable cần xét, partition size và read latency.
- Xem chính sách TTL, `gc_grace_seconds`, compaction strategy và cách xóa dữ liệu.
- Đừng tăng `LIMIT` vô hạn hoặc hạ grace tùy tiện để che dấu truy vấn chậm.

### Compaction và SSTable

Nếu dữ liệu cùng partition nằm ở nhiều SSTable, đường đọc có thể cần kiểm tra nhiều nơi. STCS, LCS, TWCS và UCS (ở phiên bản hỗ trợ) thay đổi read/write/space amplification theo workload. Dù đã giảm response từ 13 MB xuống 10 KB, **độ trễ vẫn có thể cao** nếu replica phải xét nhiều SSTable/tombstone hoặc có compaction tranh disk I/O.

### Multi-datacenter

Với RF theo DC và Java Driver cấu hình local datacenter, `LOCAL_QUORUM` tính từ DC của coordinator. Nếu client bị route sai DC, request nhỏ vẫn có thể phải đi qua WAN. Cấu hình contact points, driver local DC, token-aware routing và p95 theo DC trước khi kết luận “Cassandra chậm vì dữ liệu trả lớn”.

## 10. Quy trình benchmark từng đòn bẩy

Một bài đo hữu ích phải chỉ rõ **biến nào được thay đổi**, không đổi schema, dữ liệu, workload và CL cùng lúc rồi tuyên bố projection là nguyên nhân toàn bộ cải thiện.

### Chuẩn bị baseline

1. Tạo dữ liệu trong lab với số lượng hàng và phân phối **kích thước blob/text** gần thực tế. Không cần tạo dữ liệu khổng lồ khi ổ đĩa không đủ.
2. Cố định partition/bucket, cùng danh sách order và tỷ lệ truy vấn list/detail.
3. Giữ nguyên RF, CL, các node đang sống, phiên bản Cassandra, read/write load và cấu hình compression.
4. Ghi p50/p95/p99, số CQL requests, số pages, tổng bytes, số hàng và lỗi timeout/unavailable.
5. Chạy đủ lần để giảm ảnh hưởng warm-up/cache; tách đo khi cluster rảnh và lúc có workload nền.

### Thử nghiệm có kiểm soát

| Lượt | Query / thay đổi | Kỳ vọng cần kiểm chứng |
| --- | --- | --- |
| A | `SELECT *` một partition, `LIMIT 20` | Đường cơ sở về payload và latency |
| B | Chỉ `created_at, order_id, status, total_minor`, cùng WHERE/LIMIT | Payload giảm; p95 có thể giảm tùy mạng/serialization |
| C | Projection như B + clustering range theo ngày | Ít dữ liệu cần xét hơn nếu phạm vi thu hẹp thực sự |
| D | Page size 5 vs 25 vs 100, cùng trần tổng hàng | Đánh đổi số fetch và bytes/page |
| E | API list kiểu N+1 so với list-only + detail-on-click | Giảm số CQL requests cho đường list phổ biến |
| F | Bảng list/detail theo truy vấn | Đánh đổi ít payload list với thêm ghi/đối soát |

### Mẫu biên bản

| Chỉ số | Baseline | Sau tối ưu | Ghi chú |
| --- | ---: | ---: | --- |
| CQL requests / API call | Điền số đo | Điền số đo | Ghi retries/speculative |
| Pages fetched / API call | Điền số đo | Điền số đo | Không đồng nhất với số câu SELECT |
| Rows returned | Điền số đo | Điền số đo | Đảm bảo cùng chức năng |
| Response bytes | Điền số đo | Điền số đo | Đo sau encoding, có thể có compression |
| p95 / p99 CQL | Điền số đo | Điền số đo | Cùng mức tải/CL |
| p95 / p99 HTTP | Điền số đo | Điền số đo | Gồm JSON serialization và network ngoài Cassandra |
| CPU / heap / GC | Điền số đo | Điền số đo | Phân biệt bottleneck Java |
| Cassandra timeouts | Điền số đo | Điền số đo | Không bỏ qua lỗi khi thống kê latency |

**Đừng chỉ đo trên những request thành công** mà bỏ timeout: một tối ưu trả nhanh trong 99 request nhưng làm 1 request timeout có thể làm trải nghiệm p99/SLO tệ hơn. Lưu latency theo từng phân nhóm kích thước payload và số trang, không chỉ trung bình.

## 11. Chẩn đoán khi tối ưu không có tác dụng

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Bỏ blob khỏi SELECT nhưng p95 gần như không đổi | Nút nghẽn nằm ở disk/tombstone/CL/network RTT cố định | Tracing, `nodetool tablestats`, page count, server/client latency |
| Page size 5 khiến request chậm hơn | Fetch quá nhiều trang, nhiều round-trip | Đếm `fetchNextPage` và network RTT |
| Page size 5.000 tăng p99/GC | Page payload quá lớn | Đo heap, row size, bytes/page, giảm page size |
| Query chỉ trả 20 hàng nhưng quá chậm | Partition quá rộng, tombstone nhiều, quét không khớp khóa | Kiểm tra primary key, clustering range, TTL, compaction |
| API list gọi hàng chục CQL | N+1 lấy chi tiết cho từng hàng | Trả projection list, lazy detail, tối ưu schema theo UI |
| Có `LIMIT` nhưng timeout đọc trên nhiều node | Filtering/quét rộng, CL, replica chậm, network | `WHERE` theo partition, tracing, metrics theo node/DC |
| Prepared statement không làm giảm nhiều latency | Vấn đề chính là payload hoặc số page, không phải parse CQL | Đo tổng request/bytes/tracing thay vì chỉ prepare |
| Thay bảng list/detail rồi dữ liệu lệch | Ghi nhiều bảng không nguyên tử cross-partition | Idempotency, event log/outbox, đối soát và backfill |
| Tăng throughput nhưng nhiều timeout hơn | Quá nhiều request đồng thời, pool/replica quá tải | Rate limit, backpressure, timeout và số in-flight |

### Dùng tracing có chọn lọc

Trong `cqlsh`:

~~~text
TRACING ON
~~~

~~~sql
SELECT created_at, order_id, status, total_minor
FROM query_tuning_lab.orders_by_customer_month
WHERE tenant_id = 'tenant-a'
  AND customer_id = 11111111-1111-4111-8111-111111111111
  AND month_bucket = '2026-11'
LIMIT 20;
~~~

~~~text
TRACING OFF
~~~

Trace giúp xem coordinator, các replica, thời gian và những hoạt động đọc cần thiết. **Không bật tracing đại trà trên production** vì thêm tải và dữ liệu hệ thống. So sánh với metrics:

~~~bash
nodetool status
nodetool tablestats query_tuning_lab.orders_by_customer_month
nodetool compactionstats
~~~

`nodetool` hữu ích để hiểu node/bảng, nhưng muốn đo **bytes thực sự trả về client và số trang Java fetch**, phải quan sát ở tầng driver/proxy hoặc instrumentation của ứng dụng. Không suy luận mọi giá trị này từ riêng `tablestats`.

## 12. Checklist trước khi đưa tối ưu lên production

- [ ] Từng request có partition key hoặc kế hoạch index/truy vấn được benchmark; không quét rộng chỉ vì `SELECT` ít cột.
- [ ] Định nghĩa DTO/list projection theo đúng dữ liệu UI cần; không dùng `SELECT *` mặc định.
- [ ] Có giới hạn khoảng thời gian, số partition/bucket, tổng hàng và kích thước dữ liệu của API.
- [ ] Page size được chọn bằng đo đạc; UI không tự động fetch tất cả trang không cần thiết.
- [ ] Nếu expose paging token, đã ràng buộc với tenant, quyền truy cập, tham số truy vấn, thời hạn và kiểm tra tính toàn vẹn.
- [ ] Không còn N+1 bất hợp lý; số CQL requests/API đã được đo, kể cả retry/speculative.
- [ ] Java dùng `CqlSession`, prepared statement tái sử dụng và concurrency/backpressure có giới hạn.
- [ ] Tối ưu không hạ consistency level tùy tiện; RF/local DC/routing được kiểm tra.
- [ ] Đã đo bytes, rows, pages, latency p95/p99, timeout, CPU/GC và ảnh hưởng lên Cassandra.
- [ ] Nếu denormalize bảng list/detail, đã có chiến lược ghi idempotent, theo dõi lệch dữ liệu và đối soát.
- [ ] Có phương án rollback về schema/query cũ và test chức năng với dữ liệu thật trước khi rollout.

## 13. Bài tập thực hành

**Bài 1 — Projection.** Tạo bảng `orders_by_customer_month`, nạp dữ liệu có `details_json` và `receipt_blob`. Chạy `SELECT *` và câu `SELECT` bốn cột cùng `WHERE/LIMIT`. Thu số byte nhận ở driver và latency; giải thích vì sao chênh lệch bytes có thể lớn hơn chênh lệch disk I/O.

**Bài 2 — LIMIT không giới hạn bytes.** Với 20 hàng có blob 256 KiB và 20 hàng không có blob, tính xấp xỉ kích thước thô của hai câu SELECT. Nêu những yếu tố thực tế khiến response bytes khác phép nhân đơn giản.

**Bài 3 — Page size.** Dữ liệu có 100 hàng vừa đủ; thử page size 5, 25 và 100. Đếm số lần fetch thực tế và so p95 dưới RTT mạng nhân tạo khác nhau. Vì sao trang ít hàng hơn page size không chắc đã là trang cuối?

**Bài 4 — N+1.** API danh sách 50 đơn đang gọi thêm một SELECT detail cho mỗi đơn. Đếm CQL requests tối thiểu. Thiết kế phương án list projection + detail-on-click, mô tả lúc nào phương án này có thể không tối ưu.

**Bài 5 — Thiết kế theo partition.** Yêu cầu mới là “xem 30 đơn mới nhất của một khách hàng qua sáu tháng”. Vì sao một `month_bucket` không đủ? Đề xuất giới hạn fan-out/merge hoặc một bảng theo truy vấn khác; không dùng `ALLOW FILTERING` để thay schema.

**Bài 6 — Java async paging.** Sửa `OrderListReader` để chỉ trả trang đầu cho UI và tải trang tiếp khi được yêu cầu. Giải thích cách lưu/bảo vệ paging token và vì sao không dùng `ResultSet.all()` cho request list ngắn.

**Bài 7 — Consistency và tracing.** Với RF=3, so sánh `LOCAL_ONE` và `LOCAL_QUORUM` về số replica phải đáp ứng. Nếu cùng query chỉ trả 200 byte nhưng latency khác nhau, có thể kết luận chênh lệch do projection không? Nêu dữ liệu phải thu thập để tìm nguyên nhân.

**Bài 8 — Ghi nhiều bảng.** Khi tách list/detail, ghi list thành công nhưng detail timeout. Vì sao không được coi timeout là “chắc chắn chưa ghi”? Đề xuất operation ID, retry idempotent, outbox/đối soát và cảnh báo lệch dữ liệu.

## Ghi nhớ

**Tối ưu query Cassandra không dừng ở partition key: phải giảm cả dữ liệu trả về và số lượt trao đổi mạng.** Chọn rõ cột bằng projection thay vì `SELECT *`, giới hạn hàng/khoảng clustering, cân bằng `LIMIT` với page size, tránh tải trang/chi tiết không cần thiết và loại bỏ N+1 queries. Dùng bảng thiết kế theo truy vấn khi hợp lý, nhưng theo dõi chi phí ghi nhiều bản sao. Cuối cùng, benchmark bằng **bytes, pages, round-trips, p95/p99, lỗi và tài nguyên** dưới cùng RF/CL/workload; một response nhỏ không tự chữa truy vấn thiếu partition key, tombstone hay replica chậm.
