# Thiết kế bảng/tài liệu/khóa cho từng nhóm truy vấn

Khi thiết kế cơ sở dữ liệu NoSQL, chỉ biết hệ thống có những thực thể **Customer**, **Product**, **Order** hay **Inventory** là chưa đủ. Cùng một thực thể **Order** có thể cần được đọc theo mã đơn, liệt kê theo khách hàng, lọc đơn đang chờ xử lý của một cửa hàng, tìm theo nhiều điều kiện hoặc tổng hợp doanh thu. Mỗi cách đọc có khóa đầu vào, điều kiện lọc, thứ tự, kích thước kết quả và yêu cầu nhất quán khác nhau.

**Thiết kế theo truy vấn** (*query-driven data modeling*) là quá trình liệt kê các đường đọc–ghi quan trọng, nhóm chúng theo hình dạng truy cập, rồi chọn **bảng, tài liệu, khóa, index hoặc bản chiếu dữ liệu** đáp ứng từng nhóm. Một cấu trúc có thể phục vụ nhiều truy vấn có chung đường truy cập. Khi các truy vấn cần những khóa khác nhau, việc lưu dữ liệu được sao chép có chủ đích đôi khi có chi phí dễ kiểm soát hơn việc quét khối dữ liệu lớn.

Trong các hệ NoSQL, sự lựa chọn này mang hình thái khác nhau:

- **Mô hình cột rộng** như Cassandra/ScyllaDB: thiết kế **partition key**, **clustering key** và những bảng theo access pattern.
- **Mô hình tài liệu** như MongoDB: quyết định **embed hoặc reference**, ranh giới document và **compound index**.
- **Key–value/item** như Redis/DynamoDB: chọn **định dạng key**, item shape, sort key, TTL và đường truy cập phụ.
- **Mô hình đồ thị**: chọn nút bắt đầu, loại và chiều cạnh, điều kiện giới hạn traversal; đôi khi thêm cấu trúc đọc được tính trước.

Ví dụ trong bài mang tính minh họa để học phương pháp. Cú pháp, tính năng index và transaction cụ thể phải được đối chiếu với **sản phẩm, phiên bản, topology và cấu hình đang sử dụng**.

## 1. Từ lời yêu cầu đến danh mục truy vấn

Giả sử một ứng dụng thương mại có các chức năng sau:

| ID | Chức năng | Truy vấn hoặc thao tác điển hình | Dữ liệu đầu vào chính |
| --- | --- | --- | --- |
| **Q1** | Xem chi tiết đơn | GET /orders/{orderId} | tenantId, orderId |
| **Q2** | Xem lịch sử mua hàng | GET /customers/{customerId}/orders | tenantId, customerId, cursor |
| **Q3** | Xem đơn chờ xử lý ở cửa hàng | GET /stores/{storeId}/orders?status=PENDING | tenantId, storeId, status, cursor |
| **Q4** | Xem sản phẩm | GET /products/{productId} | tenantId, productId |
| **Q5** | Tìm sản phẩm theo bộ lọc | GET /products?category=...&priceMin=... | tenantId, category, giá, từ khóa |
| **Q6** | Xem và sửa giỏ hàng | GET/PATCH /customers/{customerId}/cart | tenantId, customerId |
| **Q7** | Giữ hàng để tạo đơn | POST /reservations | tenantId, orderId, SKU, quantity |
| **Q8** | Xem doanh thu theo ngày | GET /reports/daily-revenue | tenantId, storeId, date range |

Danh mục này là **đầu vào thiết kế**, không phải danh sách bảng bắt buộc phải tạo. Ví dụ Q1 và Q2 có thể được phục vụ bằng cùng collection MongoDB với hai index khác nhau; với Cassandra có thể cần **orders_by_id** và **orders_by_customer_month**; với DynamoDB có thể cần primary item và GSI hoặc item feed riêng.

### Những câu hỏi phải hỏi cho mỗi query

1. **Có thể xác định khóa chính từ request không?** Ví dụ Q1 có orderId; Q5 có thể chỉ có category và khoảng giá.
2. **Trả bao nhiêu dữ liệu?** Một item, 20–50 item một trang, tất cả dữ liệu của tháng hay báo cáo quét nhiều triệu bản ghi?
3. **Có phải sort không?** Mới nhất trước, giá tăng dần, độ liên quan, hay không cần thứ tự?
4. **Độ chọn lọc thế nào?** Một email khớp một người khác với status ACTIVE khớp 90% đơn.
5. **Tải đọc–ghi ra sao?** Một API phổ biến được gọi 2.000 lần/giây khác một báo cáo chạy hàng đêm.
6. **Phân bố khóa có lệch không?** Một cửa hàng lớn hoặc một sản phẩm khuyến mãi có thể là hot key.
7. **Độ mới dữ liệu phải tới đâu?** Đọc lại ngay sau ghi phải thấy thay đổi hay chấp nhận bản chiếu cập nhật trễ?
8. **Bất biến nghiệp vụ nằm ở đâu?** Không bán vượt tồn hay không tạo reservation trùng cần giải quyết ở đường ghi.
9. **Dữ liệu phát triển theo thời gian thế nào?** Một customer có 20 đơn, hay một tenant có hàng trăm triệu đơn?
10. **Phạm vi bảo mật ra sao?** Mỗi query có lọc theo tenant và kiểm tra quyền của caller không?

## 2. Nhóm các query theo hình dạng truy cập

Thay vì nói chung “truy vấn đơn hàng”, hãy phân nhóm theo **access pattern**:

| Nhóm | Đặc điểm | Cấu trúc thường cân nhắc |
| --- | --- | --- |
| **Lookup theo ID** | Một đầu vào định danh, một bản ghi | Key/item/document theo ID |
| **List theo chủ sở hữu** | Biết customer/store, cần thứ tự theo thời gian | Partition key + sort/clustering key, compound index |
| **List theo trạng thái** | Biết tenant/store/status | Bảng theo trạng thái, GSI hoặc secondary index phù hợp |
| **Lọc nhiều điều kiện** | Giá, tên, thương hiệu, category, sort linh hoạt | Compound/multikey index hoặc search engine |
| **Đọc aggregate** | Lấy giỏ và các dòng giỏ cùng nhau | Embed document, hash hoặc cấu trúc key có giới hạn |
| **Ghi có điều kiện** | Phải kiểm tra stock/version rồi ghi | Atomic item/document update, CAS, transaction |
| **Counter/rate limit** | Tăng giảm theo key hoặc cửa sổ thời gian | Atomic increment, TTL, key thống kê |
| **Analytics** | GROUP BY theo ngày, tổng hợp nhiều đơn | Pre-aggregation, streaming hoặc kho phân tích |
| **Duyệt quan hệ** | Tìm kết nối qua nhiều nút | Graph traversal, bảng quan hệ theo truy vấn |

**Không có quy tắc “mỗi query tạo một bảng”.** Nên hợp nhất những query có thể dùng chung khóa và đường đọc, nhưng không ép những query có thứ tự hoặc phạm vi khác nhau vào một cấu trúc khiến phải quét toàn bộ dữ liệu.

## 3. Viết hợp đồng truy vấn có thể đo lường

Ví dụ đặc tả Q2:

~~~yaml
queryId: Q2
purpose: "Lịch sử đơn gần nhất của một khách"
requiredInputs:
  - tenantId
  - customerId
optionalInputs:
  - cursor
sort: "createdAt DESC, orderId DESC"
pageSize: 50
cardinality:
  medianOrdersPerCustomer: 20
  highestOrdersPerCustomer: 100000
workload:
  peakRequestsPerSecond: 800
consistency: "Độ mới được thống nhất với nghiệp vụ"
retentionYears: 5
acceptance:
  p95LatencyMs: 150
  p99LatencyMs: 400
~~~

Các con số là **giả định minh họa**, không phải SLO được chấp thuận cho sản phẩm nào. Đặc tả cần bổ sung vùng đo, topology, số bản ghi toàn hệ, điều kiện retry và cách tính latency. Tuy vậy, nó đã cho thấy ba quyết định quan trọng:

- **tenantId + customerId** là phạm vi bắt buộc để định vị dữ liệu.
- **createdAt + orderId** tạo thứ tự có điểm phân biệt khi hai đơn trùng timestamp.
- Có khách hàng lịch sử rất lớn, nên cần cân nhắc **bucket thời gian** và cursor, thay vì để một partition tăng vô hạn.

Mỗi query cần có **đường truy cập cụ thể**, **ngưỡng đo**, **phương án xử lý dữ liệu mới/xóa** và **cách phục hồi read model**.

## 4. Một dữ liệu nguồn có thể cần nhiều cách nhìn

Giả sử một đơn hàng:

~~~json
{
  "orderId": "o-9001",
  "tenantId": "tenant-a",
  "storeId": "store-12",
  "customerId": "customer-42",
  "createdAt": "2026-11-14T10:10:30Z",
  "status": "PENDING",
  "currency": "VND",
  "totalAmount": 250000,
  "items": [
    {
      "sku": "P-100",
      "quantity": 2,
      "unitPrice": 125000
    }
  ]
}
~~~

Đơn này cần truy cập dưới nhiều cách:

~~~text
Q1: orderId
       -> Đọc đúng một đơn.

Q2: tenantId + customerId + thời gian
       -> Danh sách các đơn của khách, mới nhất trước.

Q3: tenantId + storeId + status + thời gian
       -> Hàng đợi đơn theo cửa hàng.

Q8: tenantId + storeId + ngày
       -> Tổng hợp doanh thu và số đơn.
~~~

Nếu chỉ lưu đơn theo **orderId**, Q1 có thể nhanh nhưng Q2, Q3, Q8 cần thêm index, bản sao đọc hoặc thuật toán tổng hợp. Nếu lưu tất cả dưới **storeId** để phục vụ Q3, Q1 và Q2 lại khó định vị.

Đây là lý do xuất hiện **denormalization**: lưu một phần thông tin của cùng order ở nhiều đường đọc được xác định trước.

### Nguồn sự thật và read model

Một ví dụ:

~~~text
orders_by_id                 -> bản ghi trạng thái nguồn
orders_by_customer_month     -> lịch sử mua hàng
orders_by_store_status_day   -> danh sách chờ xử lý
daily_revenue                -> số liệu tổng hợp
orders_search               -> tìm kiếm linh hoạt
~~~

Không phải nơi nào cũng cần lưu đủ tất cả field. Bảng danh sách thường chỉ cần ID, trạng thái, tiền, ngày và tên ngắn; khi người dùng mở một đơn cụ thể, Q1 lấy chi tiết đầy đủ.

Cần trả lời rõ: **bản ghi nào là source of truth, bản nào là projection, và ai chịu trách nhiệm đồng bộ khi order đổi trạng thái?**

## 5. Thiết kế bảng cho nhóm truy vấn trong Cassandra/ScyllaDB

Với mô hình CQL, một bảng thường được bố trí theo **partition key** (để định vị nhóm dữ liệu) và **clustering key** (để xác định thứ tự trong nhóm). Ví dụ minh họa ở đây dùng cú pháp kiểu Cassandra. Khả năng và giới hạn cụ thể phải xem sản phẩm và phiên bản đang chạy.

### 5.1. Q1 — Lookup đơn theo ID

~~~sql
CREATE TABLE orders_by_id (
    tenant_id text,
    order_id uuid,
    store_id text,
    customer_id text,
    created_at timestamp,
    status text,
    total_amount decimal,
    PRIMARY KEY ((tenant_id, order_id))
);
~~~

Query:

~~~sql
SELECT store_id, customer_id, status, total_amount
FROM orders_by_id
WHERE tenant_id = ? AND order_id = ?;
~~~

Ở đây mỗi tổ hợp **tenant_id + order_id** xác định một partition nhỏ. Nếu chỉ dùng tenant_id làm partition key cho mọi order của tenant, tenant lớn có thể tạo partition quá to và tạo điểm nóng. Nhưng bảng theo order_id lại **không hỗ trợ trực tiếp** liệt kê đơn theo customerId hoặc trạng thái.

### 5.2. Q2 — Lịch sử đơn theo khách, sắp từ mới đến cũ

~~~sql
CREATE TABLE orders_by_customer_month (
    tenant_id text,
    customer_id text,
    month_bucket text,
    placed_at timeuuid,
    order_id uuid,
    store_id text,
    status text,
    total_amount decimal,
    PRIMARY KEY (
        (tenant_id, customer_id, month_bucket),
        placed_at,
        order_id
    )
) WITH CLUSTERING ORDER BY (
    placed_at DESC,
    order_id ASC
);
~~~

Đường đọc:

~~~sql
SELECT placed_at, order_id, store_id, status, total_amount
FROM orders_by_customer_month
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?
LIMIT 50;
~~~

**month_bucket** có thể ở dạng **YYYY-MM** theo timezone được quy định (thường UTC khi lưu trữ). Nó giới hạn số dòng của một khách trong từng partition. Khi đọc lịch sử xuyên nhiều tháng, ứng dụng lấy từ tháng mới nhất rồi chuyển sang tháng trước. Cursor phải giữ **bucket và vị trí đang đọc**, không chỉ số trang.

Không nên chia bucket theo ngày cho mọi khách nếu đa số chỉ có vài đơn mỗi năm, vì như vậy tạo quá nhiều partition nhỏ và làm đường đọc phức tạp. Ngược lại, một khách có vài triệu đơn mỗi tháng có thể cần bucket nhỏ hơn. Mức chia phải dựa vào **kích thước partition ở nhóm cực trị**.

### 5.3. Q3 — Đơn theo cửa hàng và trạng thái

~~~sql
CREATE TABLE orders_by_store_status_day (
    tenant_id text,
    store_id text,
    status text,
    day_bucket date,
    placed_at timeuuid,
    order_id uuid,
    customer_id text,
    total_amount decimal,
    PRIMARY KEY (
        (tenant_id, store_id, status, day_bucket),
        placed_at,
        order_id
    )
) WITH CLUSTERING ORDER BY (
    placed_at DESC,
    order_id ASC
);
~~~

Query:

~~~sql
SELECT placed_at, order_id, customer_id, total_amount
FROM orders_by_store_status_day
WHERE tenant_id = ?
  AND store_id = ?
  AND status = ?
  AND day_bucket = ?
LIMIT 50;
~~~

Bảng này phục vụ truy vấn **store + status + ngày** bằng đường truy cập trực tiếp. Khi trạng thái đổi PENDING → PAID, dữ liệu phải rời partition cũ và xuất hiện ở partition mới. Nếu ứng dụng dùng hai thao tác xóa/chèn độc lập, sẽ có nguy cơ một thao tác thành công và thao tác kia thất bại.

**Một bảng theo truy vấn không tự đảm bảo dữ liệu giữa nhiều bảng nhất quán.** Cần quy định nguồn sự thật, thứ tự event, idempotency, retry, cách đối soát và độ trễ chấp nhận được. Không hiểu nhầm **BATCH** trong Cassandra là transaction nhiều partition với isolation và rollback tổng quát của RDBMS.

### 5.4. Chọn partition key phải tính cả độ lệch tải

| Khóa | Đường đọc thuận lợi | Rủi ro |
| --- | --- | --- |
| (tenantId) | Liệt kê dữ liệu tenant | Tenant lớn tạo partition khổng lồ |
| (tenantId, orderId) | Lookup một order | Không liệt kê theo khách trực tiếp |
| (tenantId, customerId) | Lịch sử khách | Khách có lịch sử lớn làm partition tăng vô hạn |
| (tenantId, customerId, month) | Lịch sử theo bucket | Query dài phải đọc nhiều bucket |
| (tenantId, status) | Đơn theo trạng thái | Giá trị phổ biến tạo hot partition |
| (tenantId, storeId, status, day) | Hàng đợi của cửa hàng theo ngày | Chuyển status gây ghi/xóa; có thể cần nhiều bucket |

**Bảng được đặt đúng khóa theo query nhưng phân vùng quá lệch vẫn có thể chậm.** Trong benchmark phải đo kích thước partition, request trên từng key, tombstone và node nóng, không chỉ tổng số hàng.

### 5.5. Vì sao không dùng ALLOW FILTERING thay cho mô hình đúng?

~~~sql
SELECT *
FROM orders_by_tenant
WHERE status = 'PENDING'
ALLOW FILTERING;
~~~

Tùy schema và phiên bản, kiểu truy vấn này có thể dẫn đến việc phải đọc nhiều hàng trước khi lọc. **ALLOW FILTERING không phải cơ chế tạo index** và không làm scan trở thành đường truy cập có chi phí nhỏ. Nếu truy vấn status quan trọng và chạy thường xuyên, nên cân nhắc bảng theo query, secondary index phù hợp đúng engine/phiên bản hoặc hệ search.

## 6. MongoDB: dùng document shape và index phục vụ nhiều query

MongoDB cho phép đọc theo document ID, tạo compound index và thực hiện các truy vấn điều kiện phong phú hơn nhiều key–value engine. **Không bắt buộc mỗi query có collection riêng.** Cùng collection **orders** có thể phục vụ Q1 và Q2 bằng index khác nhau.

### 6.1. Q1/Q2 trên một collection

~~~javascript
db.orders.createIndex(
  { tenantId: 1, orderId: 1 },
  { unique: true }
);

db.orders.createIndex({
  tenantId: 1,
  customerId: 1,
  createdAt: -1,
  orderId: -1
});

// Q1: lookup
db.orders.findOne({
  tenantId: "tenant-a",
  orderId: "o-9001"
});

// Q2: lịch sử khách
db.orders.find({
  tenantId: "tenant-a",
  customerId: "customer-42"
})
.sort({ createdAt: -1, orderId: -1 })
.limit(50);
~~~

Index thứ hai phản ánh các điều kiện bằng theo tenant/customer và thứ tự theo createdAt/orderId. Nó không mặc nhiên tối ưu cho **mọi** bộ lọc và sort, như query theo amount hoặc theo tên sản phẩm. Cần dùng **explain** trên workload thực, xem số document examined và kết quả trả về.

Đối với phân trang sâu, cursor dựa trên cặp **(createdAt, orderId)** thường giúp tránh chi phí skip lớn và giảm lỗi lặp/bỏ sót khi dữ liệu mới được chèn. Tuy nhiên, các trang không tự tạo snapshot nhất quán nếu DB không cung cấp hợp đồng như vậy.

### 6.2. Q4 — Đọc sản phẩm và các field hay dùng

~~~javascript
db.products.insertOne({
  _id: "tenant-a:P-100",
  tenantId: "tenant-a",
  productId: "P-100",
  name: "Bình giữ nhiệt",
  categoryId: "drinkware",
  price: 125000,
  tags: ["steel", "vacuum"],
  updatedAt: ISODate("2026-11-14T10:10:30Z")
});

db.products.findOne(
  { _id: "tenant-a:P-100" },
  { name: 1, categoryId: 1, price: 1, tags: 1 }
);
~~~

Ở đây ID có tenant để tránh va chạm. Nếu sản phẩm có mô tả lớn hoặc dữ liệu ít dùng, có thể tách riêng để giảm payload; nhưng việc tách phát sinh lần đọc khác hoặc nhu cầu join. Cần chọn theo nhóm field mà API thực sự cần.

### 6.3. Q5 — Tìm theo category và khoảng giá

~~~javascript
db.products.createIndex({
  tenantId: 1,
  categoryId: 1,
  price: 1,
  _id: 1
});

db.products.find({
  tenantId: "tenant-a",
  categoryId: "drinkware",
  price: { $gte: 100000, $lte: 250000 }
})
.sort({ price: 1, _id: 1 })
.limit(30);
~~~

Đây là một đường truy cập cho **category + price range**. Nếu người dùng muốn **full-text**, nhiều filter tùy chọn, sort theo độ liên quan, faceting và query theo tag, cần xem index bổ sung hoặc search engine. Tạo compound index cho mọi tổ hợp có thể làm tăng disk và write amplification không kiểm soát.

### 6.4. Q6 — Embed giỏ hàng khi được đọc/ghi cùng nhau

~~~json
{
  "_id": "tenant-a:customer-42:cart",
  "tenantId": "tenant-a",
  "customerId": "customer-42",
  "version": 7,
  "items": [
    {"sku": "P-100", "quantity": 2, "unitPrice": 125000},
    {"sku": "P-200", "quantity": 1, "unitPrice": 89000}
  ]
}
~~~

Nếu người dùng thường mở **toàn giỏ** và một giỏ có số dòng giới hạn, **embed** các dòng vào một document có thể giảm số lần đọc và giúp cập nhật nhiều field cùng một đơn vị atomic. Nhưng không nên embed vô hạn hoặc gom các phần dữ liệu thay đổi độc lập ở tốc độ rất cao vào một document nóng.

Khi hai tab cùng cập nhật giỏ, cần **conditional update/version** hoặc primitive cập nhật array phù hợp để tránh lost update. **Tồn kho toàn cục** của SKU là dữ liệu dùng chung nhiều giỏ; không thể đảm bảo không bán vượt tồn chỉ vì một giỏ được sửa atomic.

### Embed hay reference?

| Đặc điểm | Embed phù hợp hơn | Reference phù hợp hơn |
| --- | --- | --- |
| Đọc cùng nhau | Thường xuyên | Ít khi |
| Kích thước tập con | Nhỏ, có giới hạn | Lớn hoặc tăng không giới hạn |
| Vòng đời | Gắn với cha | Độc lập |
| Cập nhật | Cần atomic trong cùng document | Nhiều thực thể cập nhật riêng |
| Quan hệ | Một–vài, sở hữu rõ | Nhiều–nhiều, dùng chung |
| Phân trang tập con | Ít cần | Thường xuyên |

Không phải chỉ cần “dữ liệu có quan hệ” là phải embed. Quan trọng là **đường đọc, đường ghi và giới hạn kích thước**.

## 7. DynamoDB: PK/SK/GSI là phần trực tiếp của thiết kế truy vấn

Với DynamoDB, **GetItem** đọc theo khóa đầy đủ; **Query** dùng partition key và có thể giới hạn sort key. **Scan** không phải chiến lược mặc định cho API có tải lớn. Cần xác định đủ access pattern trước khi thiết kế khóa chính và index phụ.

### 7.1. Một bảng chứa nhiều kiểu item

Ví dụ bảng **Commerce** có hai thuộc tính khóa **PK** và **SK** dạng string:

| Kiểu item | PK | SK | Ý nghĩa |
| --- | --- | --- | --- |
| ORDER | TENANT#t1#ORDER#o9001 | META | Chi tiết đơn theo ID |
| CUSTOMER_ORDER | TENANT#t1#CUSTOMER#c42 | ORDER#2026-11-14T10:10:30Z#o9001 | Feed lịch sử khách |
| STORE_PENDING_ORDER | TENANT#t1#STORE#s12#PENDING#2026-11-14 | ORDER#2026-11-14T10:10:30Z#o9001 | Danh sách PENDING của cửa hàng/ngày |
| PRODUCT | TENANT#t1#PRODUCT#p100 | META | Chi tiết sản phẩm |

Q1 dùng GetItem với đúng **PK/SK** của ORDER. Q2 dùng Query trên **PK=TENANT#t1#CUSTOMER#c42**, điều kiện begins_with SK với ORDER#, **ScanIndexForward=false** nếu định dạng timestamp được chuẩn hóa để sort chuỗi khớp với thời gian. Q3 query partition chứa tenant/store/status/day.

Đây là ví dụ **read model nhiều item trong một bảng**, không phải một thao tác tự động đồng bộ. Nếu cùng một order tồn tại dưới ba item, cần đảm bảo các item được tạo/cập nhật có kiểm soát. Có thể dùng **TransactWriteItems** trong giới hạn và phạm vi transaction mà API hỗ trợ, hoặc dùng event/CDC và cho phép read model cập nhật trễ theo hợp đồng.

### 7.2. GSI thay cho item feed riêng

Một phương án khác: order item chứa thuộc tính dùng làm khóa GSI:

~~~json
{
  "PK": "TENANT#t1#ORDER#o9001",
  "SK": "META",
  "GSI1PK": "TENANT#t1#CUSTOMER#c42",
  "GSI1SK": "ORDER#2026-11-14T10:10:30Z#o9001",
  "status": "PENDING",
  "totalAmount": 250000
}
~~~

GSI1 với khóa **GSI1PK/GSI1SK** cho phép liệt kê đơn theo khách từ order item. Ưu điểm là ít logic tự duy trì feed, nhưng GSI tạo thêm dung lượng/chi phí ghi; các bản cập nhật vào GSI **bất đồng bộ** và **Query trên GSI dùng eventually consistent reads**. Nếu UX cần đọc thấy đơn mới ngay sau ghi, phải định nghĩa đường đọc có bảo đảm phù hợp hoặc chấp nhận trạng thái đang đồng bộ.

### 7.3. Các bẫy thiết kế PK/SK

- Chỉ dùng **PK=TENANT#t1** cho mọi order có thể tạo traffic tập trung vào ít partition key.
- Dùng PK là orderId phân tán tốt cho Q1 nhưng không giải quyết Q2; cần GSI hoặc read model khác.
- Sort key theo thời gian phải có định dạng timezone/độ chính xác thống nhất và **tie-breaker** như orderId.
- GSI theo **STATUS#PENDING** chung cho toàn hệ có thể tập trung quá nhiều lượt đọc/ghi. Cân nhắc tenant/store/time bucket hoặc cấu trúc khác theo workload.
- GSI projection quyết định dữ liệu nào sẵn có trên index; đọc field ngoài projection có thể cần đường đọc khác.
- Đổi status có thể làm item đổi khóa GSI hoặc yêu cầu xóa/tạo feed item; phải xét độ trễ và trạng thái cũ.
- GSI và LSI có giới hạn khác nhau, không thể thay tên rồi coi tính năng giống nhau.
- Transaction trong một Region không tự mở rộng thành atomic transaction giữa mọi Region hoặc giữa DynamoDB và hệ khác.

**Single-table design** là một lựa chọn có thể hiệu quả khi access pattern đã rõ, không phải yêu cầu bắt buộc cho mọi dịch vụ.

## 8. Redis: thiết kế key theo thao tác, TTL và cấu trúc dữ liệu

Redis thường phục vụ cache, session, counter hoặc những đường truy cập cần lookup nhanh. **Tên key** phải được thiết kế cùng kiểu dữ liệu và vòng đời.

| Nhóm | Key minh họa | Cấu trúc gợi ý | Thao tác |
| --- | --- | --- | --- |
| Chi tiết sản phẩm cache | product:t1:p100 | String/Hash | GET/HGETALL |
| Giỏ hàng | cart:t1:c42 | Hash/String | Đọc/ghi aggregate |
| Số lượt xem | views:article:42 | Integer string | INCR |
| Rate limit cửa sổ | rate:t1:u42:20261114T10 | Counter + TTL | Atomic check/increment |
| Đơn gần nhất của khách | recent-orders:t1:c42 | Sorted set | ZRANGE/ZREVRANGE |
| Chống gửi trùng | idempotency:t1:order:o9001 | String/Hash | SET NX + trạng thái |

Ví dụ:

~~~redis
INCR views:article:42
SET idempotency:t1:order:o9001 "PROCESSING" NX EX 600
~~~

**INCR** atomic trên key nhưng không idempotent nếu request bị retry. **SET NX EX** tạo claim tạm có TTL trong một lệnh, nhưng một claim PROCESSING không tự đảm bảo transaction với nơi trừ tồn kho hoặc thanh toán. Thiết kế phải nêu cách tra cứu kết quả nếu timeout, cách giải phóng claim, khi nào retry và liệu key hết hạn có cho phép duplicate quá muộn không.

Đừng thiết kế API thường xuyên chạy **KEYS product:\*** để tìm theo category: key pattern không phải index thuộc tính. Nếu cần **category → list of productIds**, cân nhắc set/sorted set phụ, index của database khác hoặc search engine tùy phạm vi truy vấn.

Cũng cần tránh tập trung mọi request cập nhật một key tổng rất nóng. Có thể dùng sharded counter cho **thống kê được phép hội tụ**, nhưng không dùng đơn giản cho quota/tồn kho đòi hỏi điều kiện atomic trên tổng.

## 9. Truy vấn tìm kiếm linh hoạt cần đường riêng

Q5 có thể phát triển thành:

~~~text
/products?
  category=drinkware&
  brand=alpha&
  minPrice=100000&
  maxPrice=300000&
  name=thermal&
  sort=relevance&
  pageSize=30
~~~

Nếu tạo bảng chuyên biệt cho **mọi tổ hợp** category, brand, khoảng giá, tên, rating và thứ tự, số cấu trúc đọc có thể tăng không kiểm soát. Nên chia nhóm:

1. **Một vài filter ổn định, có chọn lọc:** compound index trên document database có thể đủ.
2. **Đường đọc cố định, QPS cao:** bảng theo truy vấn hoặc index có khóa sắp xếp rõ.
3. **Full-text, faceting, ranking, lọc tự do:** search engine chuyên dụng thường thuận lợi hơn, nhưng phát sinh pipeline đồng bộ.

Search index thường là **bản chiếu từ nguồn sản phẩm**. API tìm kiếm có thể cho phép staleness vài giây; bước đặt hàng cần xác minh tồn kho và giá trên nguồn có bảo đảm phù hợp trước khi xác nhận. Không dùng độ mới của index tìm kiếm thay cho điều kiện giao dịch.

## 10. Báo cáo tổng hợp: đọc từ dữ liệu tiền tính

Q8 “doanh thu theo ngày” không nên mặc định scan mọi order mỗi khi mở dashboard. Có thể có read model:

~~~text
daily_revenue:
  tenantId
  storeId
  day
  currency
  paidOrderCount
  grossAmount
  refundedAmount
  netAmount
  computedAt
  sourceWatermark
~~~

Read model được cập nhật từ **sự kiện thanh toán và hoàn tiền** theo policy định nghĩa trước. Nếu consumer nhận cùng event nhiều lần, cộng vô điều kiện sẽ đếm trùng; phải dùng **eventId/idempotency/version** hoặc khả năng rebuild từ ledger chuẩn.

Trước khi thiết kế schema, cần thống nhất:

- Đơn PENDING có được tính doanh thu không, hay chỉ tính PAID/COMPLETED?
- Hoàn tiền ở ngày phát sinh giao dịch gốc hay ngày hoàn tiền?
- Ngày theo timezone nào?
- Có nhiều tiền tệ và tỷ giá không?
- Báo cáo có thể trễ bao lâu?
- Khi read model lệch, đối soát và tính lại từ nguồn nào?

Đây là ví dụ cho thấy **mô hình dữ liệu đúng** còn phụ thuộc ngữ nghĩa nghiệp vụ, không chỉ phép GROUP BY hay tên khóa.

## 11. Luồng ghi: nhiều read model phải có cơ chế đồng bộ

Một order có thể xuất hiện trong nhiều nơi:

~~~text
                       +--> orders_by_customer_month
orders_by_id --event---+--> orders_by_store_status_day
                       +--> search_orders
                       +--> daily_revenue
~~~

Sơ đồ logic đầy đủ hơn:

~~~mermaid
flowchart LR
    API[API ghi đơn] --> SRC[Kho dữ liệu nguồn]
    SRC --> EVT[Outbox / CDC / Event log]
    EVT --> CON[Consumer idempotent]
    CON --> H[Lịch sử khách]
    CON --> S[Danh sách cửa hàng]
    CON --> X[Search index]
    CON --> R[Daily revenue]
    H --> READ[API đọc]
    S --> READ
    X --> READ
    R --> READ
~~~

Các hướng thường gặp:

- **Ghi đồng bộ trong một transaction:** sử dụng khi các thay đổi nằm trong phạm vi transaction được hỗ trợ và chi phí chấp nhận được.
- **Transactional outbox:** ghi thay đổi nghiệp vụ và outbox trong cùng transaction cục bộ, worker phát event; cần consumer idempotent vì có thể gửi lại.
- **CDC/change stream:** lấy thay đổi từ nguồn nếu sản phẩm có khả năng/giới hạn phù hợp; cần quản lý checkpoint, mất kết nối và replay.
- **Dual write không có transaction:** dễ xuất hiện lỗi một bên thành công, bên kia thất bại. Phải có giao thức phục hồi/đối soát nếu dùng.
- **Batch/rebuild:** có thể hợp lý cho báo cáo hoặc search index không đòi cập nhật tức thì.

### Cập nhật trạng thái cần version

~~~json
{
  "orderId": "o-9001",
  "status": "PAID",
  "version": 5,
  "updatedAt": "2026-11-14T10:12:00Z"
}
~~~

Nếu event v5 đến trước v4 do retry hoặc mất kết nối, consumer không được âm thầm ghi đè PAID trở lại PENDING. Có thể áp dụng quy tắc **chỉ chấp nhận version mới hơn**, lưu trạng thái xử lý, dùng idempotency hoặc logic chuyển trạng thái có kiểm chứng.

Khi status thay đổi, bảng **orders_by_store_status_day** cần bỏ entry PENDING cũ và thêm entry PAID mới. Nếu thao tác tách rời, có thể cần thời gian hội tụ; API phải định nghĩa kết quả quan sát trong khoảng đó.

### Read-your-writes từ đâu?

API tạo đơn có thể trả **SUCCESS** ngay sau ghi nguồn; read model lịch sử chưa kịp đồng bộ. Nếu client ngay lập tức đọc lịch sử và không thấy đơn, trải nghiệm dễ gây hiểu nhầm.

Các hướng xử lý gồm:

- Trả orderId và cho API trạng thái đọc trực tiếp từ nguồn chuẩn.
- Dùng cơ chế session/read consistency phù hợp sản phẩm.
- Hiển thị trạng thái “đang cập nhật” có giới hạn thay vì nói đơn biến mất.
- Đợi bản chiếu tới watermark/version theo hợp đồng nếu chi phí cho phép.

Không có một mức nhất quán chung cho mọi read model; phải thiết kế theo chức năng.

## 12. Bất biến nghiệp vụ không được gửi cho read model tự bảo vệ

Giả sử hai khách đồng thời giữ sản phẩm cuối cùng. Cả hai đọc stock = 1 rồi cùng ghi stock = 0 nếu code dùng read-then-write không có điều kiện. Việc có các bảng **orders_by_customer** và **orders_by_store** không giải quyết cuộc đua này.

Cần primitive đúng tại nơi bảo vệ tồn kho:

~~~text
Reserve(sku, qty, orderId):
    Nếu orderId đã được xử lý:
        trả kết quả cũ, không trừ thêm.

    Nếu stock >= qty:
        nguyên tử trừ stock và ghi nhận reservation
    Ngược lại:
        trả OUT_OF_STOCK.
~~~

Đoạn trên là ý định nghiệp vụ, không phải một API dùng chung. Nếu stock và reservation ở **cùng item/document** và DB hỗ trợ điều kiện atomic, có thể bảo vệ trong phạm vi đó. Nếu ở **nhiều item/document**, cần transaction phù hợp. Nếu thuộc **nhiều dịch vụ**, cần state machine/saga, idempotency, compensation và đối soát.

Một read model theo query có thể chậm hội tụ trong phạm vi cho phép; **bất biến không oversell** thường không được phép chỉ dựa trên bản chiếu bất đồng bộ.

## 13. Sort và pagination phải được thiết kế từ đầu

Một danh sách cần thứ tự ổn định. Chỉ sort theo createdAt có thể không đủ khi nhiều đơn cùng timestamp:

~~~text
2026-11-14T10:10:30.000Z -> o1
2026-11-14T10:10:30.000Z -> o2
~~~

Sử dụng khóa sắp xếp gồm **(createdAt DESC, orderId DESC)** hoặc một khóa thứ tự tương đương, nếu engine và schema hỗ trợ. Với key–value, string timestamp phải theo format thống nhất, cùng timezone và độ chính xác; với CQL clustering key cần bám thứ tự truy vấn dự kiến.

### Keyset/cursor pagination

~~~text
Trang đầu: lấy 50 đơn mới nhất theo (createdAt DESC, orderId DESC).

Cursor:
    lastCreatedAt
    lastOrderId

Trang kế:
    lấy bản ghi có cặp khóa nhỏ hơn cursor
    theo cùng thứ tự.
~~~

DynamoDB có **LastEvaluatedKey** cần được truyền đúng theo API, không thể thay thế trực tiếp bằng timestamp. Trong bảng CQL có bucket, cursor cần mang thông tin bucket và vị trí đọc. Trong MongoDB có thể dùng predicate seek với index phù hợp.

**Offset lớn** thường kém hiệu quả trên nhiều mô hình dữ liệu và dễ bị lệch khi có bản ghi mới chen vào. Cursor giúp quản lý đường đọc, nhưng **không tự tạo snapshot nhất quán giữa nhiều request** nếu database không cung cấp bảo đảm đó.

## 14. TTL, trạng thái và xóa dữ liệu là một phần của schema

Nhiều thiết kế chỉ mô tả lúc **INSERT**, bỏ qua các tình huống **UPDATE/DELETE/EXPIRE**.

| Thay đổi | Hệ quả cần xử lý |
| --- | --- |
| Order PENDING → PAID | Xóa/mở khóa entry cũ theo status, tạo entry mới, cập nhật bản chiếu. |
| Product đổi category | Cập nhật index hoặc danh sách theo category; tránh còn entry cũ. |
| Cart hết hạn | TTL phải đúng với vòng đời giỏ; tránh stale cart hiển thị lại. |
| Customer bị xóa | Xóa/ẩn thông tin theo chính sách ở bản gốc, cache, index và read model. |
| Event đến trễ sau khi xóa | Tránh vô tình tạo lại bản ghi đã bị xóa. |
| Hết thời gian retention | Xác định dữ liệu còn trong backup/index bao lâu. |

Mỗi read model cần kế hoạch vòng đời: tạo khi nào, cập nhật theo version nào, xóa thế nào, có TTL riêng không, có thể backfill hoặc rebuild từ nguồn nào. **TTL ở một hệ không tự đồng bộ TTL của hệ khác**. Xóa source document cũng không chắc tự xóa key Redis hay search index độc lập.

## 15. Hot key, partition lớn và tải không đồng đều

Một schema theo truy vấn có thể đúng về mặt câu lệnh nhưng sai khi traffic bị lệch:

~~~text
Tenant nhỏ: 500 đơn/ngày
Tenant lớn: 2.000.000 đơn/ngày

Nếu PK = tenantId:
  tenant lớn tập trung nhiều dữ liệu và request.

Nếu PK = (tenantId, status):
  trạng thái PENDING/PAID phổ biến có thể thành hot partition.
~~~

Chọn khóa phải xét cả **số bản ghi** và **lưu lượng trên mỗi khóa**, không chỉ cardinality toàn hệ.

Các chiến lược thường cân nhắc:

- Bucket theo ngày/tháng khi query luôn có phạm vi thời gian.
- Thêm storeId/customerId hoặc chiều phân vùng đúng với API.
- Phân phối key theo hash/suffix khi cần giảm hot partition, nhưng chấp nhận query phải đọc nhiều bucket.
- Tách read model thống kê/đọc nhiều khỏi bản ghi giao dịch quan trọng.
- Dùng cache với chính sách invalidation và độ tươi rõ.
- Giới hạn page size và chi phí query lớn.
- Đo p95/p99 của những tenant và key cực trị.

Thêm shard nhân tạo có thể giảm điểm nghẽn ghi nhưng khiến truy vấn đọc phải fan-out và hợp nhất kết quả. Quyết định phải dựa trên workload thật.

## 16. Ước lượng chi phí nhân bản dữ liệu

Giả sử có 10 triệu đơn:

~~~text
Bản ghi nguồn trung bình:          1.024 byte / order
Feed lịch sử khách:                 250 byte / order
Feed cửa hàng và trạng thái:        220 byte / order
Search projection:                  400 byte / order
~~~

Dung lượng payload logic sơ bộ:

| Cấu trúc | Ước lượng |
| --- | ---: |
| Nguồn đơn hàng | ~9,54 GiB |
| Feed theo khách | ~2,33 GiB |
| Feed theo store/status | ~2,05 GiB |
| Search projection | ~3,73 GiB |
| **Tổng payload minh họa** | **~17,65 GiB** |

Con số này **không phải dung lượng disk thực tế**: còn metadata, index nội bộ, replication, nén, journal, tombstone và backup. Nhưng nó cho thấy read model bổ sung có chi phí. Khi trạng thái đơn đổi bốn lần, bảng theo status còn phát sinh nhiều thao tác xóa/chèn chứ không chỉ một bản ghi cuối cùng.

~~~text
Ít read model:
    Ít ghi/ít storage hơn
    Nhưng query phụ có thể scan nhiều hoặc cần nhiều round trip.

Nhiều read model:
    Các truy vấn chính dễ định tuyến, latency dễ dự báo
    Nhưng ghi/update/delete, đối soát và backfill phức tạp hơn.
~~~

Mục tiêu là **tổng chi phí phù hợp với tỷ lệ đọc/ghi và SLO**, không phải tạo ít bảng nhất hay nhiều index nhất.

## 17. Multi-tenancy và phân quyền trong đường truy cập

Nếu ứng dụng phục vụ nhiều tenant, mỗi query phải đảm bảo không trả dữ liệu của tenant khác.

~~~text
Request:
  GET /orders/o-9001

Backend:
  Xác thực caller và xác định tenant tin cậy.
  Lookup order theo (tenantId, orderId).
  Kiểm tra quyền theo hợp đồng nghiệp vụ.
~~~

Đặt tenantId vào partition key hoặc compound index giúp định vị và cách ly logic, **không thay thế authorization**. Nếu client có thể tự gửi tenantId bất kỳ, backend phải xác minh quyền của caller với tenant đó.

Trong MongoDB, unique index trên email có thể là unique toàn collection hoặc unique theo **(tenantId, email)**; cần chọn đúng hợp đồng. Trong Redis, prefix key theo tenant giảm va chạm tên nhưng không tự mang cơ chế kiểm tra quyền. Với các read model, phải giữ tenantId và giới hạn dữ liệu ngay từ đầu đường truy cập, kể cả search index.

## 18. Benchmark từng nhóm query và toàn bộ workload

Một mô hình đạt Q1 nhưng không đạt Q3 vẫn có thể không đáp ứng ứng dụng. Cần đo riêng các query shape, rồi thử hỗn hợp khi ghi và tác vụ nền chạy đồng thời.

| Query | Tải đỉnh giả định | Kích thước kết quả | Ngưỡng minh họa |
| --- | ---: | --- | --- |
| Q1 Order lookup | 1.000 req/s | 1 item | p95 ≤ 80 ms |
| Q2 Customer history | 600 req/s | 50 items | p95 ≤ 150 ms |
| Q3 Pending by store | 250 req/s | 50 items | p95 ≤ 180 ms |
| Q4 Product lookup | 1.500 req/s | 1 item | p95 ≤ 100 ms |
| Q5 Product filters | 400 req/s | 30 items | p95 ≤ 300 ms |
| Q7 Reserve stock | 150 req/s | 1 kết quả ghi | Không oversell; latency theo hợp đồng |
| Q8 Daily revenue | 30 req/s | Theo ngày/store | Freshness ≤ 60 giây nếu được chấp nhận |

Đây là bộ số **giả lập để minh họa cách đặt tiêu chí**, không phải kết quả đo từ Cassandra, MongoDB, DynamoDB hay Redis.

### Những gì phải đo

1. **Offered RPS, successful RPS và error rate** theo từng nhóm query.
2. **Latency p50, p95, p99**, timeout và độ trễ từ client tới khi nhận đủ kết quả.
3. **Rows/items scanned** so với số dòng trả về.
4. **Phạm vi partition/shard/node** mà một truy vấn chạm tới.
5. **Chi phí read/write**, CPU, RAM, network, disk I/O và cache.
6. **Hot partition**, mức sử dụng tài nguyên của node nóng nhất và độ lệch theo tenant.
7. **Chi phí cập nhật read model**, backlog consumer và độ trễ index.
8. **Tính đúng của kết quả**, không oversell, không duplicate khi retry.
9. **Khả năng phục hồi** khi build lại index, reprocess event hoặc failover.
10. **Chi phí lưu trữ và tăng trưởng** khi dữ liệu lớn hơn RAM và nhiều năm retention.

MongoDB có explain để quan sát kế hoạch index và số document examined. Cassandra/ScyllaDB có tracing/metrics theo query và partition. DynamoDB có capacity consumption, kết quả Query/Filter và số liệu partition nóng. Redis có latency, memory và command/network metrics. Tên công cụ khác nhau theo sản phẩm; mục tiêu đo là **chi phí truy cập thực**, không chỉ thời gian chạy một demo nhỏ.

**Tránh benchmark với tất cả khóa phân bố đều** nếu production có một vài tenant cực lớn hoặc sản phẩm đang khuyến mãi nhận phần lớn request.

## 19. Khi nhu cầu truy vấn thay đổi, phát triển schema thế nào?

Giả sử sau sáu tháng ứng dụng thêm query “tất cả đơn bị hoàn tiền theo khoảng thời gian và mã đối tác”. Không nhất thiết sửa ngay bảng nguồn cho phù hợp một query mới. Quy trình nên là:

1. Ghi rõ query shape, đầu vào, sort, limit, QPS và độ tươi.
2. Kiểm tra index/cấu trúc hiện hữu có hỗ trợ hiệu quả không.
3. So sánh secondary index, GSI, bảng denormalized hoặc search model.
4. Chọn nguồn dữ liệu và luồng phát thay đổi cho cấu trúc mới.
5. **Backfill** dữ liệu lịch sử từ nguồn đáng tin cậy.
6. Kiểm chứng version, số bản ghi, tính đúng và sự bắt kịp của consumer.
7. Chuyển traffic theo từng bước, theo dõi latency, lỗi và resource.
8. Giữ kế hoạch rollback; loại bỏ cấu trúc cũ chỉ khi không còn query phụ thuộc.

Một **CREATE INDEX** hoặc một bảng mới chưa đảm bảo dữ liệu quá khứ đã được nạp, chưa đảm bảo index xây xong hay pipeline cập nhật kịp nguồn. Cần có trạng thái “ready” dựa trên **bằng chứng** chứ không chỉ metadata schema.

## 20. Ma trận chọn cấu trúc cho từng nhóm truy vấn

| Yêu cầu | Cột rộng | Document | Key–value/item |
| --- | --- | --- | --- |
| Lấy một bản ghi theo ID | Partition key chính xác | _id hoặc unique compound index | GetItem/GET theo key |
| Lịch sử theo khách và thời gian | Bảng theo customer + time bucket, clustering | Compound index customer/time | PK customer + SK time; GSI/feed nếu key gốc khác |
| Đơn theo store + status | Bảng theo store/status/day | Compound index nếu workload phù hợp | GSI hoặc feed item theo store/status/day |
| Đọc giỏ cùng toàn bộ dòng | Có thể gom theo partition, tùy workload | Embed các dòng có giới hạn | Hash/item hoặc một value aggregate |
| Tìm sản phẩm nhiều filter | Bảng theo query shape hữu hạn hoặc search phụ | Compound/multikey/search index | Index phụ/GSI cho query cố định; search phụ cho linh hoạt |
| Trừ tồn nếu đủ | Điều kiện/transaction phù hợp engine | Atomic conditional document update | Conditional UpdateItem hoặc script/primitive atomic |
| Counter thống kê | Counter/model theo hệ | $inc trên document | INCR/ADD theo key/item |
| Báo cáo tổng hợp | Bảng aggregate được cập nhật | Aggregate/precompute/index tùy tải | Counter/summary item, pipeline analytics |

Bảng là **bản đồ lựa chọn**, không phải cam kết mọi sản phẩm trong cùng nhóm hỗ trợ cùng tính năng. Quyết định cuối cùng phải dựa trên query thực, phiên bản, consistency, benchmark và khả năng vận hành.

## 21. Bài tập áp dụng: hệ thống đặt vé

Giả sử cần quản lý **Event**, **Seat**, **Reservation** với yêu cầu:

- Xem chi tiết một vé theo ticketId.
- Liệt kê vé gần nhất của một người dùng.
- Liệt kê ghế còn trống theo event và khu vực.
- Giữ một ghế trong năm phút, không được giữ trùng.
- Thống kê vé bán theo ngày.
- Tìm sự kiện theo tên, địa điểm và khung giờ.

### Nhóm truy vấn thành read/write model

| Nhóm | Gợi ý đường truy cập | Vấn đề chính |
| --- | --- | --- |
| Chi tiết vé | ticketId → ticket | Lookup, tenant/security |
| Vé theo user | userId + time → danh sách | Sort, cursor, nhiều năm dữ liệu |
| Ghế trống | eventId + section + trạng thái → danh sách | Hot event, thay đổi nhanh |
| Giữ ghế | eventId + seatId → conditional claim | Không giữ trùng, TTL/idempotency |
| Vé bán theo ngày | daily_sales summary | Aggregate, event replay |
| Tìm sự kiện | search/index theo filter | Full-text, geospatial, freshness |

### Bất biến và vòng đời

~~~text
Một (eventId, seatId) có tối đa một reservation còn hiệu lực.
Một reservationId không được giữ ghế thêm lần nữa khi retry.
Reservation hết hạn phải được giải phóng an toàn.
Đơn đã thanh toán hợp lệ phải được ghi nhận trên nguồn chuẩn.
Search index có thể chậm cập nhật,
nhưng quyết định giữ ghế không được tin duy nhất vào search.
~~~

Nếu khóa giữ ghế có TTL nhưng event tự hết hạn, cần làm rõ **ai cập nhật trạng thái ghế và đơn hàng**; TTL trên một key không tự động thực hiện transaction ở mọi cấu trúc liên quan. Một sự kiện rất nổi tiếng có thể tạo hot partition khi mọi khách cùng cố giữ ghế trong một khu; có thể cần partition theo section/seat, song vẫn phải giữ đúng bất biến tại cấp ghế.

Học viên có thể phác thảo ba thiết kế: **MongoDB với conditional document update và index**, **Cassandra với bảng theo event/seat và bảng đọc theo user**, **DynamoDB/Redis với conditional key và read model phụ**. Sau đó so sánh số round trip, xung đột, transaction scope, TTL, recovery và chi phí ở tải đỉnh.

## 22. Quy trình quyết định cuối cùng

~~~mermaid
flowchart TD
    A[Liệt kê API và query shape] --> B[Nhóm theo khóa, filter, sort, limit]
    B --> C[Đánh dấu bất biến và consistency]
    C --> D[Chọn document / partition / item / key]
    D --> E{Có query cần đường truy cập khác?}
    E -->|Có| F[Index, GSI, bảng read model hoặc search]
    E -->|Không| G[Đường đọc hiện có]
    F --> H[Thiết kế cập nhật, xóa, TTL, replay]
    G --> I[Benchmark workload đại diện]
    H --> I
    I --> J{Đạt latency, correctness, chi phí?}
    J -->|Không| D
    J -->|Có| K[Ghi hợp đồng và vận hành]
~~~

Tóm lược các quyết định cần có trong tài liệu thiết kế:

1. Mỗi query quan trọng phải nêu **đầu vào, key, đường truy cập và thứ tự**.
2. Mỗi cấu trúc phải có **một hoặc nhiều query được phục vụ trực tiếp**.
3. Mỗi bản sao/read model phải có **nguồn sự thật và quy tắc đồng bộ**.
4. Mỗi thao tác nghiệp vụ quan trọng phải có **bất biến, ranh giới atomic và retry/idempotency**.
5. Mỗi partition/key phải được đánh giá với **dữ liệu và traffic cực trị**.
6. Mỗi thay đổi schema/index cần **backfill, rollout, recovery và rollback**.
7. Mọi quyết định cần được nghiệm thu bằng **latency, throughput, correctness, freshness và chi phí**, không chỉ bằng số lượng bảng hay index.

## Kết luận

Thiết kế **bảng, tài liệu và khóa theo từng nhóm truy vấn** giúp hệ NoSQL định vị dữ liệu theo đúng cách ứng dụng sử dụng: lookup trực tiếp, liệt kê theo owner/thời gian, lọc theo trạng thái, tìm kiếm linh hoạt, đọc aggregate hoặc cập nhật có điều kiện. Với cột rộng, trọng tâm là **partition/clustering key và bảng theo access pattern**; với document, trọng tâm là **ranh giới document, embed/reference và index**; với key–value/item, trọng tâm là **key pattern, PK/SK, TTL và những đường truy cập phụ**.

Một thiết kế đạt yêu cầu khi trả lời rõ: **truy vấn tìm dữ liệu nhanh bằng cách nào, dữ liệu được cập nhật và xóa ở những nơi nào, độ mới của bản chiếu ra sao, bất biến nghiệp vụ được bảo vệ ở đâu và cách khôi phục khi đồng bộ thất bại**. Số bảng ít nhất hoặc số index nhiều nhất không phải mục tiêu; mục tiêu là phục vụ đúng workload với hiệu năng, tính đúng đắn và chi phí đã được xác định.
