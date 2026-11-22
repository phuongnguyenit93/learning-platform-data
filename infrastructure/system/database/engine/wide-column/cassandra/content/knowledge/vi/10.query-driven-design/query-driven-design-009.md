# Truy vấn phụ hiếm gặp và nhu cầu kho tìm kiếm/phân tích

## Mục tiêu bài học

Apache Cassandra được thiết kế để phục vụ tốt những đường truy cập **có thể xác định trước partition key và thứ tự đọc trong partition**. Vì vậy, thiết kế theo truy vấn thường tạo những bảng chuyên biệt cho các API quan trọng. Nhưng không phải mọi yêu cầu đều đáng có một bảng mới: nhiều yêu cầu chỉ phát sinh trong điều tra sự cố, báo cáo định kỳ, tìm kiếm tùy ý hoặc thao tác quản trị hiếm khi thực hiện.

Trong chương **Thiết kế theo truy vấn** thuộc module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`, bài này bàn về quyết định: **khi nào chấp nhận một truy vấn phụ có giới hạn, khi nào thêm bảng phục vụ truy vấn, và khi nào chuyển nhu cầu sang hệ thống tìm kiếm hoặc phân tích riêng?** Quyết định phải dựa trên đường đọc, khối lượng dữ liệu, độ trễ, độ mới, replication/consistency, chi phí ghi nhân bản và khả năng phục hồi khi lỗi. Ví dụ minh họa dùng CQL và kết nối từ ứng dụng Java.

Sau khi học, bạn có thể:

- Phân loại **truy vấn chủ đạo**, **truy vấn phụ hiếm gặp** và **truy vấn khám phá/phân tích** theo đầu vào, phạm vi, SLA và tần suất.
- Giải thích vì sao một câu `SELECT` hợp lệ hoặc có `LIMIT` chưa chắc là một truy vấn Cassandra rẻ.
- So sánh bốn lựa chọn: **fan-out có giới hạn**, **bảng query-driven riêng**, **index phù hợp**, và **kho tìm kiếm/phân tích bên ngoài**.
- Xác định yêu cầu cần hệ thống tìm kiếm toàn văn, lọc nhiều thuộc tính, facet hoặc thống kê tổng hợp theo lịch sử.
- Phác thảo pipeline từ dữ liệu nguồn sang search/analytics, xử lý đồng bộ trễ, update/delete, replay, backfill và đối soát.
- Đề xuất hợp đồng API, kiểm thử tải và cách Java định tuyến truy vấn sang hệ thống thích hợp.

## 1. Truy vấn phụ hiếm gặp không đồng nghĩa truy vấn rẻ

Giả sử ứng dụng bán hàng nhiều tenant dùng Cassandra để lưu đơn hàng. Hầu hết người dùng chỉ thực hiện hai hành vi:

1. Xem chi tiết một đơn bằng `order_id`.
2. Xem 50 đơn gần nhất của một khách hàng trong một tháng.

Trong khi đó, bộ phận hỗ trợ đôi khi cần “tìm đơn có từ `hỏng bao bì` trong ghi chú, có trạng thái `RETURNED` và tổng tiền trong khoảng 500.000–2.000.000 đồng”. Phòng phân tích muốn “tính tổng doanh thu theo tỉnh và nhóm sản phẩm mỗi tuần trong hai năm”.

Cả hai yêu cầu sau có thể ít được gọi, nhưng **phạm vi dữ liệu phải xem xét lại rất rộng** và **khóa truy cập không rõ**. Tần suất nhỏ không làm chúng trở nên an toàn trên Cassandra đang phục vụ hệ thống giao dịch.

| Đặc điểm | Truy vấn chủ đạo | Truy vấn phụ có ranh giới | Tìm kiếm/khám phá/phân tích |
| --- | --- | --- | --- |
| Đầu vào | Khóa chính biết trước | Một số partition/bucket biết trước | Từ khóa, nhiều filter tùy ý, phạm vi rộng |
| Mẫu truy cập | Ổn định, thường xuyên | Ít dùng, có phạm vi cụ thể | Khó dự đoán, thay đổi theo người dùng |
| Phạm vi | Một partition hoặc số nhỏ cố định | Số partition tối đa được chặn | Nhiều tenant/ngày/thuộc tính, có thể toàn dữ liệu |
| Sắp xếp | Theo clustering key | Có thể merge kết quả từ vài partition | Sort theo nhiều cột, relevance, thống kê |
| Kỳ vọng | Độ trễ thấp, thường cần dữ liệu mới | Có thể chịu độ trễ cao hơn | Có thể ưu tiên linh hoạt hoặc tổng hợp dữ liệu |
| Hướng thiết kế | Cassandra table theo truy vấn | Fan-out có chặn hoặc bảng bổ sung | Search index/OLAP/data lake tùy nhu cầu |

**Truy vấn phụ hiếm gặp** nên được đánh giá bằng **chi phí tệ nhất trên một yêu cầu**, không chỉ bằng tổng số request mỗi ngày. Một báo cáo duy nhất có thể làm quá tải cụm nếu nó bắt buộc quét hàng triệu partition hoặc tạo nhiều tombstone scan.

## 2. Phân loại theo hợp đồng truy vấn

Trước khi viết `CREATE TABLE` hay index, tạo danh mục query shape. Ví dụ:

| ID | Yêu cầu nghiệp vụ | Caller biết gì? | Sort/aggregation | Độ trễ mong đợi | Hướng sơ bộ |
| --- | --- | --- | --- | --- | --- |
| Q01 | Lấy chi tiết đơn | Tenant, order ID | Một kết quả | Thấp | Cassandra lookup |
| Q02 | Lấy 50 đơn gần nhất của khách trong tháng UTC | Tenant, customer ID, tháng | `created_at DESC` | Thấp | Cassandra time-ordered table |
| Q03 | Lấy đơn của một khách trong tối đa 3 tháng | Tenant, customer ID, tháng bắt đầu/kết thúc | Mới nhất trước | Trung bình | Fan-out hữu hạn qua bucket |
| Q04 | Lọc `FAILED` trong một partition khách/tháng đã biết | Tenant, customer ID, tháng, status | Cùng thứ tự thời gian | Không gắt | Lọc có chặn hoặc đánh giá index |
| Q05 | Tìm từ khóa trong ghi chú trên toàn tenant, kết hợp status/giá | Tenant, text và filter tùy chọn | Relevance hoặc ngày mới nhất | Thấp–trung bình | Search engine |
| Q06 | Tổng hợp doanh thu theo tỉnh/tuần trong 2 năm | Tenant, khoảng năm, chiều nhóm | `GROUP BY` và `SUM` | Có thể bất đồng bộ | Kho phân tích/OLAP |
| Q07 | Phục vụ hàng đợi `PENDING` toàn tenant/ngày ở tải cao | Tenant, status, ngày | Mới nhất trước | Thấp | Bảng projection Cassandra nếu tải cho phép |

Trong thực tế phải hỏi thêm **QPS đỉnh**, tỷ lệ tăng dữ liệu, kích thước đối tượng, tenant lớn nhất, mức độ mới của kết quả, thời gian lưu và quyền truy cập. Một Q05 được gọi 10 lần/ngày nhưng đòi dưới 200 ms khác hoàn toàn với Q05 được phép hoàn thành như một job vài phút.

### 2.1. Ma trận phân loại đầu vào

Với mỗi truy vấn, ghi:

- **Trường bắt buộc:** có đủ partition key hiện tại hay không?
- **Phạm vi tối đa:** bao nhiêu partition, khoảng thời gian, hàng và byte có thể đọc?
- **Điều kiện:** lọc theo clustering column hay regular column? Có điều kiện toàn văn, khoảng trên nhiều cột, phủ định hoặc toán tử OR phức tạp không?
- **Kết quả:** `LIMIT`, phân trang, đếm chính xác, facet, tổng hợp, sắp xếp theo relevance?
- **Độ mới:** thấy ngay sau ghi, vài giây, vài phút, hay báo cáo cuối ngày?
- **Tương tác:** request đồng bộ, export bất đồng bộ, hay truy vấn nội bộ của quản trị viên?

Không được xếp hai truy vấn vào cùng nhóm chỉ vì chúng cùng đọc bảng `orders`. **Đường định vị và biến đổi dữ liệu** mới là yếu tố quyết định.

## 3. Một schema Cassandra phục vụ truy vấn chủ đạo

Ví dụ hai bảng phục vụ Q01 và Q02:

```sql
CREATE TABLE orders_by_id (
    tenant_id text,
    order_id uuid,
    customer_id uuid,
    created_at timestamp,
    status text,
    total_amount decimal,
    note text,
    revision bigint,
    PRIMARY KEY ((tenant_id, order_id))
);

CREATE TABLE orders_by_customer_month (
    tenant_id text,
    customer_id uuid,
    month_bucket text,
    created_at timestamp,
    order_id uuid,
    status text,
    total_amount decimal,
    note text,
    revision bigint,
    PRIMARY KEY ((tenant_id, customer_id, month_bucket),
                 created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC);
```

`month_bucket` là chuỗi `YYYY-MM` tính từ `created_at` theo UTC. `order_id` làm tie-breaker khi nhiều đơn có cùng millisecond tạo. Ở bảng theo ID, `order_id` thuộc partition key; ở bảng theo khách/tháng, nó là clustering column. Hai bảng phải được cập nhật đúng khi tạo/sửa đơn, bởi Cassandra **không tự đồng bộ các projection theo nghiệp vụ**.

Q01:

```sql
SELECT customer_id, created_at, status, total_amount, note, revision
FROM orders_by_id
WHERE tenant_id = ? AND order_id = ?;
```

Q02:

```sql
SELECT created_at, order_id, status, total_amount
FROM orders_by_customer_month
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?
LIMIT 50;
```

Các câu trên có đủ partition key. Cassandra đọc một partition và dùng clustering order của bảng khách/tháng để phục vụ danh sách mới nhất trước.

Ngược lại, ý tưởng sau **không phải** giải pháp truy vấn toàn tenant hiệu quả:

```sql
-- KHÔNG sử dụng như cách tìm kiếm tổng quát trên tenant.
-- Câu này thiếu customer_id và month_bucket của composite partition key.
SELECT order_id, created_at, total_amount
FROM orders_by_customer_month
WHERE tenant_id = 'tenant-A'
  AND status = 'FAILED';
```

Đây không phải tình huống chỉ cần thêm `ORDER BY` hoặc `LIMIT 50`. Schema đang hướng tới `(tenant_id, customer_id, month_bucket)`, trong khi query chỉ biết tenant và status. Phải phân loại lại Q05/Q07 theo access pattern.

## 4. Bốn lựa chọn cho truy vấn phụ

### 4.1. Lựa chọn A: fan-out nhỏ, có giới hạn

Q03 hỏi lịch sử một khách trong **ba tháng UTC đã biết**. Ứng dụng có thể tính ba giá trị `month_bucket` rồi đọc từng partition theo Q02 và hợp nhất kết quả theo `(created_at DESC, order_id DESC)`.

```text
Request: customer=C, from=2026-09, to=2026-11
   |-- partition (tenant, C, 2026-09)
   |-- partition (tenant, C, 2026-10)
   |-- partition (tenant, C, 2026-11)
   +-- merge theo created_at DESC, order_id DESC
       trả tối đa 50 đơn + trạng thái trang tiếp theo
```

**Điều kiện để cách này chấp nhận được:**

1. Biết trước **toàn bộ** partition key của từng nhánh.
2. Fan-out tối đa nhỏ và được **chặn bằng hợp đồng API**, ví dụ không quá ba tháng lịch trong một request.
3. Sắp xếp/hợp nhất trong bộ nhớ có giới hạn; không tải toàn bộ lịch sử trước rồi mới áp `LIMIT`.
4. Quản lý paging cho từng partition và cách tạo token tiếp tục khi hợp nhất.
5. Đo p95/p99 với khách hàng có nhiều dữ liệu nhất, gồm tình huống tombstone hoặc bucket rỗng.

**Bẫy về thời gian:** một cửa sổ trượt ba tháng tính theo số ngày không nhất thiết chạm đúng ba bucket tháng lịch. API cần thống nhất khái niệm “ba tháng lịch” và khoảng nửa mở `[from, to)`; sau đó tính số bucket thực tế.

Fan-out có giới hạn thường đáng chọn hơn tạo thêm một bảng nếu yêu cầu thật sự hiếm, số partition rất nhỏ và vẫn đạt SLA.

### 4.2. Lựa chọn B: bảng projection cho truy vấn phụ trở thành quan trọng

Nếu Q07 — danh sách `PENDING` theo tenant/ngày — trở thành một đường đọc thường xuyên, thấp trễ và caller luôn có tenant, status, ngày, có thể tạo:

```sql
CREATE TABLE orders_by_status_day (
    tenant_id text,
    status text,
    day_bucket date,
    created_at timestamp,
    order_id uuid,
    customer_id uuid,
    total_amount decimal,
    PRIMARY KEY ((tenant_id, status, day_bucket),
                 created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC);

SELECT created_at, order_id, customer_id, total_amount
FROM orders_by_status_day
WHERE tenant_id = ?
  AND status = 'PENDING'
  AND day_bucket = ?
LIMIT 50;
```

`day_bucket` ở đây là **ngày UTC của `created_at`**. Truy vấn có nghĩa “các đơn được tạo trong ngày X và hiện đang PENDING”; không phải “các đơn chuyển sang PENDING trong ngày X”.

Bảng mới giảm fan-out đọc, nhưng:

- Mỗi lần tạo đơn phát sinh thêm một mutation.
- Đổi `PENDING → PAID` cần `DELETE` hàng trong partition trạng thái cũ và `INSERT` vào partition mới; phát sinh tombstone.
- Nếu cập nhật projection chậm hoặc thất bại, danh sách có thể tạm thời sai.
- Một tenant rất lớn có thể tạo **hot partition** ở `(tenant, PENDING, day)`; cần đo kích thước/throughput và có thể thêm shard với chi phí đọc nhiều partition hữu hạn.

**Không nên tạo bảng mới chỉ vì Q05 có một tổ hợp filter tình cờ được hỏi một lần.** Một projection đáng có khi query shape ổn định, có giá trị rõ ràng và chi phí ghi/phục hồi chấp nhận được.

### 4.3. Lựa chọn C: index phù hợp cho bộ lọc có phạm vi

Với một số phiên bản/triển khai Cassandra, **Storage-Attached Index (SAI)** có thể hỗ trợ những điều kiện lọc theo cột không nằm trong primary key. Ví dụ minh họa khi môi trường hỗ trợ SAI:

```sql
-- Chỉ sử dụng sau khi xác nhận phiên bản Cassandra/triển khai hỗ trợ SAI.
CREATE CUSTOM INDEX IF NOT EXISTS orders_customer_month_status_sai
ON orders_by_customer_month (status)
USING 'StorageAttachedIndex';

-- Trường hợp đã biết chính xác partition customer/month.
SELECT created_at, order_id, status, total_amount
FROM orders_by_customer_month
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?
  AND status = 'FAILED';
```

Trong Q04, caller **đã biết partition** và chỉ cần lọc thêm status; nếu partition có rất ít hàng, ứng dụng có thể chấp nhận đọc một tập nhỏ rồi lọc thay vì tạo index. Nếu partition lớn, cần so sánh truy vấn không index, index và một bảng chuyên biệt với workload thực tế.

**Giới hạn quan trọng:**

- Hỗ trợ cú pháp/khả năng SAI phụ thuộc **phiên bản Cassandra và môi trường triển khai**. Không mặc định nó có mặt ở mọi cụm.
- SAI không biến một cột regular thành clustering column và **không tự cho phép `ORDER BY` toàn cục tùy ý**.
- Index có chi phí tạo, lưu trữ, cập nhật và tiêu thụ tài nguyên. Điều kiện có độ chọn lọc thấp trên phạm vi quá rộng vẫn có thể đắt.
- Index không tự biến truy vấn theo nhiều filter, text relevance, facet và sort tùy ý thành trải nghiệm công cụ tìm kiếm chuyên dụng.

Những dạng secondary index khác nhau có tính năng/giới hạn khác nhau tùy phiên bản. Đừng coi `ALLOW FILTERING` là index: nó là cơ chế cho phép Cassandra chấp nhận một số truy vấn phải lọc dữ liệu mà độ lớn công việc có thể khó dự đoán. Câu lệnh chạy được **không chứng minh** query shape an toàn ở tenant lớn.

### 4.4. Lựa chọn D: kho tìm kiếm hoặc kho phân tích chuyên biệt

Khi yêu cầu vượt khỏi những đường truy cập có thể định trước, hãy tách **nguồn dữ liệu giao dịch** khỏi **mô hình tìm kiếm/phân tích**:

| Nhu cầu | Hệ thống đáng khảo sát | Lợi thế chính |
| --- | --- | --- |
| Từ khóa toàn văn, relevance, filter kết hợp, facet | Search engine như OpenSearch/Elasticsearch hoặc dịch vụ tìm kiếm phù hợp | Inverted index và truy vấn linh hoạt |
| Thống kê theo nhiều chiều, tổng hợp trên hàng tỷ hàng, xu hướng lịch sử | Kho phân tích/OLAP như ClickHouse, BigQuery hoặc hệ tương đương | Columnar scan, aggregation và lịch sử |
| Khám phá dữ liệu thô, batch ETL, truy vấn ad hoc dài | Data lake/warehouse và công cụ SQL như Spark/Trino tùy kiến trúc | Tách tải báo cáo khỏi truy vấn giao dịch |
| Hàng đợi trực tuyến với khóa/sort ổn định | Cassandra projection theo query shape | Định tuyến tới partition đã biết, độ trễ thấp |

Tên công nghệ chỉ là ví dụ **loại hệ thống**, không phải khuyến nghị bắt buộc. Quyết định còn phụ thuộc khối lượng, chi phí vận hành, độ mới dữ liệu, bảo mật, kết nối hiện có và SLA.

Một search engine thường thích hợp cho Q05; một kho phân tích thường thích hợp cho Q06. Không nên buộc Cassandra giao dịch phải chịu truy vấn tổng hợp có phạm vi rộng nếu nhu cầu đó có thể được chạy trên dữ liệu sao chép dành riêng cho phân tích.

## 5. Khi nào cần kho tìm kiếm?

Kho tìm kiếm đáng đánh giá nếu API yêu cầu đồng thời nhiều đặc tính:

- **Full-text search** trên tiêu đề, ghi chú, mô tả; có tokenize/analyzer, ngôn ngữ, ranking.
- Kết hợp filter theo status, loại sản phẩm, khoảng tiền, địa lý hoặc thuộc tính tùy chọn.
- Sắp xếp theo **relevance**, giá, ngày tạo hoặc nhiều khóa mà clustering của một bảng Cassandra không bao phủ.
- Trả facet: đếm theo trạng thái, danh mục, giá hoặc trường được đánh chỉ mục.
- Phân trang kết quả tìm kiếm rộng, với giới hạn và tính ổn định kết quả được quy định rõ.

Ví dụ API:

```text
GET /tenants/tenant-A/orders/search
    ?q=vo-hop
    &status=RETURNED
    &minAmount=500000
    &maxAmount=2000000
    &sort=createdAtDesc
    &pageSize=30
```

Một **search document** có thể là:

```json
{
  "document_id": "tenant-A:order-123",
  "tenant_id": "tenant-A",
  "order_id": "order-123",
  "customer_id": "customer-45",
  "created_at": "2026-11-21T09:30:00Z",
  "status": "RETURNED",
  "total_amount": 1250000,
  "title": "Hộp bị móp khi giao",
  "note": "Khách báo vỏ hộp bị hỏng",
  "revision": 17
}
```

Đây là **document minh họa**, không phải định dạng khóa Cassandra. `document_id` nên duy nhất trong không gian index; khi nhiều tenant dùng chung index, thường cần ghép tenant/order ID để tránh trùng. Tùy yêu cầu bảo mật, không nhất thiết copy dữ liệu cá nhân nhạy cảm sang search.

Một query DSL mang tính khái niệm cho hệ hỗ trợ kiểu truy vấn tương tự OpenSearch:

```json
{
  "size": 30,
  "query": {
    "bool": {
      "must": [
        {"multi_match": {"query": "vỏ hộp", "fields": ["title", "note"]}}
      ],
      "filter": [
        {"term": {"tenant_id": "tenant-A"}},
        {"term": {"status": "RETURNED"}},
        {"range": {"total_amount": {"gte": 500000, "lte": 2000000}}}
      ]
    }
  },
  "sort": [
    {"created_at": {"order": "desc"}},
    {"document_id": {"order": "desc"}}
  ]
}
```

**Lưu ý:** đây là cấu trúc minh họa; tính hợp lệ phụ thuộc mapping (ví dụ `keyword` cho tenant/status/document ID, `date` cho created_at, kiểu số cho amount) và API/version của search engine thực tế. Một trường dùng để sort cần kiểu và mapping cho phép sort. Phân trang sâu thường cần cơ chế phù hợp như `search_after`, có thể kết hợp point-in-time, thay vì tùy tiện tăng offset. Kết quả có thể thay đổi khi index cập nhật.

**Quyền tenant phải được cưỡng chế ở server.** Không được tin chỉ vào một `tenant_id` do client tự truyền; dịch vụ phải xác nhận người dùng thuộc tenant và áp điều kiện vào tất cả truy vấn, kể cả facet/export. Khi search chỉ trả ID, có thể dùng Cassandra `orders_by_id` để xác minh chi tiết hiện hành và quyền truy cập trước khi hiển thị.

## 6. Khi nào cần kho phân tích?

Kho phân tích trả lời câu hỏi như:

- Doanh thu theo tỉnh, nhóm sản phẩm và tuần trong hai năm?
- Tỷ lệ giao chậm theo đơn vị vận chuyển, cohort khách hàng?
- Đếm số đơn thất bại theo giờ và so sánh nhiều tháng?
- Tìm xu hướng dài hạn, tổng hợp dữ liệu từ đơn hàng, thanh toán và vận chuyển?

Đây là những phép **scan và aggregation trên phạm vi rộng**, thường đòi `GROUP BY` trên nhiều chiều và `JOIN` nhiều nguồn. CQL không phải ngôn ngữ SQL phân tích tổng quát, và `COUNT(*)` trên một phạm vi lớn cũng không trở thành rẻ chỉ vì câu lệnh ngắn.

Một bảng fact trong hệ phân tích có thể chứa:

| Cột | Vai trò phân tích |
| --- | --- |
| `tenant_id` | Bảo đảm phạm vi tenant |
| `order_id` | Khóa đối soát/khử trùng bản ghi |
| `created_at`, `created_date` | Trục thời gian và partition dữ liệu phân tích |
| `region`, `product_category` | Chiều nhóm |
| `status` | Trạng thái hiện tại hoặc trạng thái tại thời điểm sự kiện, phải định nghĩa rõ |
| `total_amount` | Metric cần tổng hợp |
| `revision`, `ingested_at` | Theo dõi bản sửa và độ mới dữ liệu |

Ví dụ SQL **mang tính minh họa cho hệ OLAP**, không phải CQL:

```sql
SELECT tenant_id,
       DATE_TRUNC('week', created_at) AS week_start,
       region,
       product_category,
       SUM(total_amount) AS revenue
FROM order_facts
WHERE tenant_id = ?
  AND created_at >= ?
  AND created_at < ?
  AND status = 'PAID'
GROUP BY tenant_id, DATE_TRUNC('week', created_at),
         region, product_category;
```

Chi tiết cú pháp `DATE_TRUNC`, placeholder và kiểu thời gian thay đổi theo SQL engine. Quan trọng hơn cú pháp là **định nghĩa metric**: tổng tiền đơn được tạo trong tuần hay được thanh toán trong tuần? Có trừ hoàn tiền không? Một đơn thay status có được cập nhật lại fact hay lưu thêm event? Kho phân tích cần quy định rõ logic để tránh kết quả khác Cassandra chỉ vì hai hệ dùng hai định nghĩa.

Các báo cáo dài có thể chạy dưới dạng **job bất đồng bộ** với giới hạn tài nguyên, lưu kết quả và trả link tải qua hệ thống ứng dụng, thay vì giữ kết nối HTTP mở trong nhiều phút. Không bắt cụm Cassandra giao dịch gánh batch scan của báo cáo nếu có kiến trúc phù hợp hơn.

## 7. Kiến trúc tách tải đọc giao dịch và truy vấn khám phá

Một thiết kế tổng quát:

```text
                          +--> Cassandra: orders_by_id
API / Order Service -------+--> Cassandra: orders_by_customer_month
             |             +--> Cassandra: projection cho query shape ổn định
             |
             +--> nguồn thay đổi bền vững (event log / CDC có vận hành)
                           |
                           +--> Consumer search -> Search index
                           |
                           +--> ETL/streaming -> Kho phân tích/OLAP
                           |
                           +--> Dedupe / retry / đối soát / giám sát lag

Read API:
  xem theo ID / khách-tháng -> Cassandra
  tìm từ khóa/filter/facet  -> Search index
  thống kê lịch sử         -> OLAP / job báo cáo
```

**Không nên xem sơ đồ là bảo đảm tự động chống mất dữ liệu.** Nếu ứng dụng ghi Cassandra rồi phát event bằng hai thao tác không có cơ chế bền vững, sự cố ở giữa có thể làm search/OLAP **vĩnh viễn thiếu thay đổi**. Chọn kiến trúc nguồn sự kiện với bảo đảm cụ thể: event log bền vững, outbox phù hợp với công nghệ nguồn, CDC có connector vận hành được hoặc quy trình replay/backfill có kiểm chứng.

### 7.1. Cách đưa thay đổi sang search/OLAP

| Cách | Ưu điểm | Rủi ro/câu hỏi phải trả lời |
| --- | --- | --- |
| Ứng dụng ghi song song Cassandra và search | Đường đi đơn giản về mặt ý tưởng | Dual-write gap: nguồn thành công, search thất bại hoặc ngược lại |
| Phát sự kiện nghiệp vụ đã chấp nhận | Consumer tách biệt, có thể retry/replay | Phải bảo đảm **event được phát bền vững**, giữ thứ tự/ID |
| CDC từ Cassandra | Bắt thay đổi dữ liệu đã ghi ở nguồn | Cần connector, quản lý log/offset, initial snapshot, schema evolution |
| Backfill định kỳ | Dễ tái tạo theo lô khi có nguồn đầy đủ | Độ trễ cao; phải xử lý sửa/xóa/trùng và chi phí quét |

CDC của Cassandra và mức hỗ trợ connector có điều kiện theo phiên bản/triển khai. Không mặc định bật một cấu hình CDC là đủ để có **exactly-once** và cả bản chụp dữ liệu quá khứ. CDC cũng không tự hiểu tất cả quy tắc chuyển trạng thái nghiệp vụ; consumer phải chọn đúng event/revision và xử lý xóa hoặc TTL theo hợp đồng.

### 7.2. Dữ liệu tìm kiếm là bản sao có thể trễ

Giả sử một đơn vừa chuyển `PENDING → PAID`:

```text
10:00:00.000  Ghi trạng thái PAID vào nguồn giao dịch.
10:00:00.200  API tra cứu theo ID đã thấy PAID.
10:00:02.000  Consumer mới cập nhật search document thành PAID.
```

Trong khoảng giữa, tìm kiếm theo `status=PENDING` có thể còn trả đơn đó. Đây là **độ trễ projection/search** khác với nhất quán giữa replica Cassandra.

Cần xác định:

- Search có được phép trễ vài giây/phút không?
- Kết quả có cần xác nhận lại trạng thái/ACL từ Cassandra trước khi thực hiện hành động không?
- Người dùng có được thông báo dữ liệu tìm kiếm không tức thời không?
- Nếu consumer lỗi kéo dài, API trả kết quả cũ, tạm dừng tìm kiếm hay chuyển sang chế độ khác?

**Consistency level** như `LOCAL_QUORUM` có thể hỗ trợ các yêu cầu nhất quán đọc/ghi ở Cassandra với topology phù hợp; nó **không** làm search index tự nhận được mutation chưa xử lý.

### 7.3. Trùng sự kiện và sự kiện đến sai thứ tự

Nếu search consumer nhận revision 18 trước revision 17, không được cho revision 17 ghi đè trạng thái mới. Thiết kế cần:

1. `document_id` ổn định, ví dụ `tenant_id + order_id`.
2. `event_id` để nhận diện event đã áp dụng; `revision` hoặc version tăng theo đối tượng.
3. Quy tắc chỉ áp dụng mutation mới hợp lệ; dùng **external versioning/conditional update** nếu search engine hỗ trợ và đúng ngữ nghĩa, hoặc xử lý thứ tự theo khóa ở consumer.
4. Retry idempotent; không sinh document ID mới khi replay cùng một event.
5. Có tombstone/delete event rõ ràng và xử lý delete sau khi đã kiểm tra thứ tự version.

Không giả định “at-least-once” đồng nghĩa dữ liệu cuối cùng luôn đúng. Nếu event cũ được phát lại sau event mới và consumer không kiểm tra phiên bản, search có thể bị ghi lùi.

## 8. Backfill, đối soát và cắt chuyển hệ thống

Tạo search/analytics mới cho dữ liệu đã tồn tại là một bài toán riêng, không chỉ bật consumer từ hôm nay.

### 8.1. Initial load và thay đổi đang diễn ra

Một quy trình tổng quát có thể là:

1. Chọn **nguồn đầy đủ, có thể duyệt** để lấy các đơn đã tồn tại: snapshot/export, manifest/đường ETL được thiết kế hoặc log sự kiện có đủ lịch sử. **Không** chạy scan toàn Cassandra trên request thông thường.
2. Xác định checkpoint/watermark của luồng thay đổi trước hoặc trong quá trình backfill bằng cơ chế đồng bộ phù hợp.
3. Nạp dữ liệu cũ theo batch có giới hạn và `document_id` ổn định, theo dõi revision mỗi đối tượng.
4. Áp dụng thay đổi mới từ log/CDC, xử lý các event bị trùng hoặc đến sai thứ tự.
5. Đối soát số lượng và một mẫu có ý nghĩa theo tenant, trạng thái, khoảng thời gian, record ID và revision.
6. Cho API đọc thử/canary, kiểm tra độ mới, bảo mật và latency trước khi chuyển traffic.

Điểm quan trọng: trong lúc backfill, nếu revision 20 của một đơn đã vào search nhưng job backfill còn đang chuẩn bị revision 17, không được cho bản cũ ghi đè. Cơ chế version/checkpoint phải bảo vệ cả **đường đồng bộ live** lẫn **đường nạp dữ liệu cũ**.

### 8.2. Đối soát không chỉ so COUNT(*)

Đếm tổng số document chỉ là một phép kiểm thô. Một hệ thống có thể cùng tổng số lượng nhưng vừa **thiếu** một đơn, vừa **trùng** một đơn khác.

| Invariant sau khi hội tụ | Cách kiểm chứng |
| --- | --- |
| Mỗi order còn hiệu lực có một document tìm kiếm tương ứng | So ID theo manifest/batch, kiểm tra key và revision |
| Status/amount/tenant trong search khớp nguồn được xác nhận | So các trường được định nghĩa đồng bộ, không dùng search làm nguồn sửa Cassandra |
| Document bị xóa/ẩn theo chính sách không còn lộ trong search | Replay delete/tombstone, đối soát retention và ACL |
| Dữ liệu phân tích không nhân đôi do replay | Khử trùng bằng event ID/revision, kiểm tra khóa fact |
| Aggregation phản ánh định nghĩa metric đã chốt | Đối chiếu với tập dữ liệu chuẩn và công thức |
| Độ trễ đồng bộ nằm trong SLO | Đo thời gian accepted → indexed/queryable |

**Repair của Cassandra** đồng bộ replica theo cơ chế database; nó không tìm và sửa document thiếu trong search/OLAP. Việc đó cần **reconciliation ở tầng pipeline nghiệp vụ**.

### 8.3. Delete, TTL và bảo vệ dữ liệu

Nếu đơn bị xóa, bị ẩn hoặc hết thời hạn lưu:

- Source of truth cần phát quy tắc xóa/ẩn sang search và kho phân tích theo policy.
- TTL ở Cassandra **không tự xóa** một document đã được sao chép sang hệ thống ngoài.
- Các bảng/index/backup có thể có vòng đời khác nhau. Đòi hỏi xóa dữ liệu phải được thiết kế xuyên toàn pipeline, kể cả cache/export nếu chính sách yêu cầu.
- Search phải kiểm tra quyền tenant và có thể cần kiểm tra lại quyền trước khi hiển thị chi tiết, vì quyền truy cập cũng có thể thay đổi nhanh hơn tốc độ cập nhật index.

Không được đưa dữ liệu nhạy cảm sang công cụ phân tích chỉ vì bảng Cassandra nguồn đang lưu chúng. Dữ liệu trong search/warehouse là một bản sao bổ sung cần phân quyền, mã hóa, audit và retention phù hợp.

## 9. Java: định tuyến đúng loại truy vấn

Ví dụ dưới dùng API của **DataStax Java Driver 4.x** cho Q01/Q02, còn tìm kiếm Q05 được trừu tượng hóa thành gateway riêng. Mẫu này phân tách trách nhiệm thay vì xây một câu CQL động cho mọi bộ lọc.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.YearMonth;
import java.util.UUID;

public final class OrderReadService {
    private final CqlSession session;
    private final PreparedStatement byId;
    private final PreparedStatement byCustomerMonth;
    private final OrderSearchGateway searchGateway;

    public OrderReadService(CqlSession session, OrderSearchGateway searchGateway) {
        this.session = session;
        this.searchGateway = searchGateway;
        this.byId = session.prepare(
            "SELECT customer_id, created_at, status, total_amount, note, revision " +
            "FROM orders_by_id WHERE tenant_id = ? AND order_id = ?"
        );
        this.byCustomerMonth = session.prepare(
            "SELECT created_at, order_id, status, total_amount " +
            "FROM orders_by_customer_month " +
            "WHERE tenant_id = ? AND customer_id = ? AND month_bucket = ? " +
            "LIMIT 50"
        );
    }

    public Row getById(String authorizedTenantId, UUID orderId) {
        return session.execute(
            byId.bind(authorizedTenantId, orderId)
        ).one();
    }

    public ResultSet latestForCustomer(
        String authorizedTenantId, UUID customerId, YearMonth utcMonth
    ) {
        return session.execute(
            byCustomerMonth.bind(
                authorizedTenantId, customerId, utcMonth.toString()
            )
        );
    }

    public SearchPage search(String authorizedTenantId, SearchCriteria criteria) {
        return searchGateway.search(authorizedTenantId, criteria);
    }

    // Các giao diện dưới được triển khai bởi adapter search cụ thể của dự án.
    // Chúng minh họa ranh giới trách nhiệm; không thay thế xác thực/phân quyền.
    public interface OrderSearchGateway {
        SearchPage search(String authorizedTenantId, SearchCriteria criteria);
    }

    public interface SearchCriteria {}
    public interface SearchPage {}
}
```

Ví dụ trên có chủ đích **không** gắn một thư viện OpenSearch/Elasticsearch cụ thể. Adapter thực tế phải kiểm soát query DSL, bộ lọc tenant bắt buộc, paging token, timeout, kích thước kết quả, kiểu tìm kiếm được phép và xử lý search unavailable.

Trong API thực tế:

1. `authorizedTenantId` phải lấy từ ngữ cảnh đã xác thực, **không tin thẳng vào tenant ID của query string**.
2. `YearMonth` không có timezone; nếu tạo từ `Instant created_at`, hãy chuyển sang UTC trước khi tính bucket.
3. `ResultSet` đồng bộ có thể tự tải thêm trang khi lặp. `LIMIT 50` ở ví dụ là **tổng số hàng của truy vấn preview**, không phải cơ chế phân trang nhiều lần.
4. Với search, `pageSize` và số filter phải có giới hạn. Khi dữ liệu index đang thay đổi, cần xác định semantics của phân trang; không hứa snapshot bất biến nếu không triển khai cơ chế phù hợp.
5. Không tự động chuyển toàn bộ search thất bại thành **scan Cassandra**; fallback như vậy có thể làm sập cụm giao dịch khi hệ search đang gặp sự cố.

### 9.1. Cách trả lời khi kết quả search cần dữ liệu mới nhất

Một API tìm kiếm có thể:

- Trả document đã index và hiển thị thời gian cập nhật/độ mới phù hợp với sản phẩm.
- Lấy danh sách `order_id` từ search, rồi **đọc có giới hạn** `orders_by_id` để xác minh trạng thái cuối và quyền truy cập trước khi trả kết quả/hành động.
- Nếu xác nhận lại phát hiện document đã cũ, bỏ kết quả sai và để hệ đồng bộ cập nhật index; không hứa vẫn đủ 30 kết quả nếu nhiều document bị stale mà chưa thiết kế nạp bù.

Đọc xác nhận lại thêm chi phí N lookups và vẫn cần chính sách về thứ tự, phân trang, trạng thái nguồn. Chỉ thực hiện với tập kết quả có giới hạn, không biến search thành danh sách hàng triệu ID rồi đọc tất cả từ Cassandra.

## 10. Chi phí tổng thể: không chỉ đo latency của một câu SELECT

Khi cân nhắc thêm bảng hay hệ thống phụ, ước lượng ít nhất bốn loại chi phí:

| Loại chi phí | Câu hỏi |
| --- | --- |
| **Read amplification** | Mỗi request chạm bao nhiêu partition, đọc bao nhiêu byte/tombstone, merge bao nhiêu luồng? |
| **Write amplification** | Mỗi thay đổi nguồn tạo bao nhiêu mutation/projection/index update và được nhân bản tới bao nhiêu replica? |
| **Storage/retention** | Bao nhiêu bản sao logic và vật lý, index, tombstone, backup và dữ liệu lưu quá hạn? |
| **Operational correctness** | Đồng bộ trễ bao lâu, lỗi từng phần, replay, backfill, xóa và đối soát khó đến mức nào? |

Ví dụ giả định:

```text
Hệ thống có 10 triệu đơn
Q05 được gọi 20 lần/ngày
Q07 (hàng đợi PENDING) được gọi 2.000 lần/phút

Nếu Q05 phải quét phần đáng kể 10 triệu đơn:
  - ít gọi vẫn có thể chiếm nhiều CPU/I/O trong từng lần
  - nên xét search hoặc job phân tích, không quét nguồn giao dịch

Nếu Q07 luôn có tenant, status, ngày:
  - projection Cassandra có đường đọc rõ ràng có thể đáng giá
  - cần đo chi phí mutation mỗi lần đổi status và hotspot partition
```

Đây là ví dụ để **so sánh cấu trúc tải**, không phải benchmark hay ngưỡng chung. Lựa chọn cuối cần dữ liệu thử nghiệm đại diện trên cụm mục tiêu.

### 10.1. Fan-out, tombstone và LIMIT

`LIMIT 50` giới hạn **số hàng được trả về** của câu CQL, không làm một truy vấn thiếu partition key tự nhiên chỉ đọc 50 hàng vật lý. Ngay cả khi chỉ đọc một partition, TTL, xóa và cập nhật có thể để lại tombstone khiến hệ thống phải đọc nhiều dữ liệu không còn hiển thị.

Với fan-out nhiều bucket, mỗi nhánh có `LIMIT 50` vẫn có thể tạo tổng lượng đọc lớn hơn 50 hàng. API phải giới hạn **số partition, số hàng/byte trung gian và thời gian** trước khi gửi truy vấn, không chỉ cắt kết quả ở cuối.

### 10.2. Replication/consistency, compaction và repair

Replication factor quyết định số bản sao dữ liệu Cassandra theo cấu hình keyspace. Consistency level quyết định mức phản hồi replica cho thao tác; nó không tạo thêm đường lọc toàn tenant hay làm search index nhận event mới. Compaction có thể ảnh hưởng cách SSTable và tombstone được xử lý; repair duy trì nhất quán giữa replica Cassandra, **không** sửa lệch logic giữa Cassandra và warehouse.

Nếu tạo bảng projection mới, chi phí còn gồm thao tác tạo/xóa hàng khi khóa trạng thái đổi, compaction và khả năng partition nóng. Nếu tạo search/analytics mới, chi phí chuyển thành indexing, storage, connector, lỗi pipeline, bảo mật, đối soát và SLA độ mới. Không có phương án “miễn phí”.

## 11. Checklist chọn nơi thực thi truy vấn

| Câu hỏi quyết định | Nếu câu trả lời là... | Hướng xử lý |
| --- | --- | --- |
| Caller biết toàn bộ partition key? | Có | Ưu tiên bảng Cassandra hiện có |
| Chỉ cần 2–3 bucket xác định? | Có, có giới hạn rõ | Đọc fan-out hữu hạn và merge |
| Query shape ổn định, tần suất/SLA cao? | Có | Cân nhắc bảng projection riêng |
| Lọc một regular column trong phạm vi nhỏ? | Có | So sánh đọc lọc có chặn/index/bảng riêng |
| Cần text relevance, facet và filter tùy ý? | Có | Search engine chuyên dụng |
| Cần tổng hợp nhiều chiều trên lịch sử dài? | Có | OLAP/warehouse hoặc job phân tích |
| Cần nhìn thấy dữ liệu ngay sau ghi? | Có | Xác định đường nguồn, độ mới và cách kiểm tra kết quả |
| Có dữ liệu nhạy cảm/đa tenant? | Có | Thiết kế authorization, isolation và retention xuyên các bản sao |
| Có nguồn thay đổi bền vững để đồng bộ? | Chưa | Không hứa eventual consistency tự hội tụ; thiết kế event/CDC/backfill |
| Có thể đo và đối soát kết quả? | Có | Đặt SLO lag, kiểm thử lỗi và rollout có giám sát |

## 12. Những sai lầm cần tránh

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Vì query hiếm nên cho phép scan lớn trên Cassandra | Một request có thể làm tăng độ trễ của toàn cụm | Giới hạn phạm vi hoặc chạy trên hệ search/analytics |
| Dùng `ALLOW FILTERING` như cách thay partition key | Tải đọc khó dự đoán, có thể không được CQL chấp nhận | Phân loại lại query shape và đo truy cập |
| Tạo bảng Cassandra cho mọi filter UI | Tăng write amplification và đồng bộ dữ liệu khó kiểm soát | Giữ projection cho mẫu ổn định, filter linh hoạt đưa sang search |
| Dùng SAI rồi cho rằng mọi `ORDER BY` được hỗ trợ | Cú pháp/hiệu năng không đáp ứng yêu cầu | Kiểm tra phiên bản, query cụ thể và workload |
| Tưởng `LIMIT 50` khiến truy vấn rộng an toàn | Vẫn có nhiều partition/tombstone phải đọc | Chặn fan-out, byte, khoảng thời gian và đo thực tế |
| Chỉ ghi song song vào Cassandra/search rồi nói “sẽ tự hội tụ” | Dual-write gap có thể tạo lệch vĩnh viễn | Durable event/CDC, retry và reconciliation |
| Để backfill bản cũ ghi đè live revision mới | Search/warehouse hiển thị trạng thái lùi | Áp dụng version/sequence và checkpoint đúng |
| Dùng `LOCAL_QUORUM` để “đồng bộ” external search | Search vẫn trễ do consumer/index | Đo lag và cơ chế đọc nguồn khi cần |
| Cập nhật Cassandra nhưng quên delete ở search | Lộ dữ liệu đã xóa/hết quyền | Propagate delete, retention và đối soát |
| Khi search hỏng, tự fallback sang scan Cassandra | Lỗi thứ cấp làm quá tải database nguồn | Degrade có kiểm soát, trả lỗi/queue report phù hợp |
| Trộn logic doanh thu theo ngày tạo và ngày thanh toán | Báo cáo không khớp dù pipeline đầy đủ | Chốt định nghĩa fact và metric trước khi ETL |

## 13. Bài tập thực hành

Một ứng dụng Java quản lý ticket hỗ trợ lưu:

```text
tenant_id, ticket_id, requester_id, created_at,
status, priority, title, description, assigned_team, revision
```

API cần:

1. **R1:** Xem một ticket bằng ID — truy vấn thường xuyên, cần kết quả mới.
2. **R2:** Xem 30 ticket của một requester trong tháng UTC, mới nhất trước.
3. **R3:** Mỗi ngày vài lần, trưởng nhóm xem ticket của requester qua tối đa hai tháng.
4. **R4:** Tìm từ khóa trong title/description, lọc theo nhiều status/priority/team và sort theo relevance.
5. **R5:** Báo cáo thời gian xử lý trung bình theo team và tháng trong ba năm.
6. **R6:** Hàng đợi 50 ticket `OPEN` của tenant/ngày được mở liên tục với SLA thấp.

**Yêu cầu:**

1. Đề xuất Cassandra table và partition/clustering key cho R1/R2.
2. Giải thích vì sao R3 có thể dùng fan-out hữu hạn mà chưa nhất thiết có bảng mới; giới hạn số bucket và cách phân trang.
3. So sánh R4 với R6: yêu cầu nào phù hợp search engine, yêu cầu nào đáng khảo sát Cassandra projection? Nêu điều kiện về tải/hot partition.
4. Với R5, chọn một hệ OLAP/warehouse và định nghĩa rõ “thời gian xử lý” đo từ mốc nào đến mốc nào.
5. Phác thảo pipeline giữ Cassandra làm nguồn giao dịch, đưa thay đổi sang search và warehouse, gồm các bước xử lý revision cũ/trùng, xóa và backfill.
6. Một ticket được sửa `priority` ở Cassandra lúc 10:00 nhưng search mới nhận lúc 10:00:05. Giải thích đây là loại nhất quán nào và vì sao tăng `LOCAL_QUORUM` ở truy vấn Cassandra không làm mất khoảng trễ đó.
7. Mô tả ít nhất ba phép đối soát trước khi công bố search mới đã sẵn sàng: ID/revision, tenant ACL, delete và kết quả filter/aggregation.

**Gợi ý đối chiếu:** R1 dùng partition key `(tenant_id, ticket_id)`; R2 dùng `(tenant_id, requester_id, month_bucket)` và clustering `(created_at DESC, ticket_id DESC)`. R3 có thể đọc tối đa hai bucket tháng lịch đã biết rồi merge với giới hạn kết quả. R4 cần text search + filter linh hoạt; R6 có thể cần bảng `(tenant_id, status, day_bucket)`, nhưng phải đo tenant lớn nhất và xử lý di chuyển khóa khi status đổi. R5 phù hợp kho phân tích với event/fact được định nghĩa chính xác; kết quả không tự đúng chỉ vì dùng SQL. Search cập nhật chậm là **projection lag**, không phải lỗi replication của cùng partition Cassandra; cần đo SLO độ mới, retry, versioning và đối soát.

## Kết luận

Truy vấn phụ hiếm gặp không nên tự động dẫn tới một bảng Cassandra mới, nhưng cũng không được phép quét dữ liệu vô hạn chỉ vì ít người gọi. Hãy chọn nơi thực thi dựa trên **đầu vào định vị partition, giới hạn fan-out, yêu cầu lọc/sắp xếp/tổng hợp, SLA và độ mới dữ liệu**. Cassandra thích hợp cho đường truy cập có khóa rõ; fan-out nhỏ có kiểm soát giải quyết nhiều truy vấn phụ; search index phục vụ khám phá linh hoạt; kho phân tích phục vụ tổng hợp lịch sử. Khi sao chép dữ liệu ra hệ thống khác, kiến trúc chỉ hoàn chỉnh nếu có **nguồn thay đổi bền vững, version, retry, backfill, đối soát, bảo mật và chính sách xóa** được kiểm chứng bằng dữ liệu và tải thực tế.
