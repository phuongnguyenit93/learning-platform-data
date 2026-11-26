# ANSI JOIN giữa các collection theo trường dữ liệu trong Spring Data Couchbase

Trong Couchbase, quan hệ giữa hai document không nhất thiết được biểu diễn bằng khóa ngoại có ràng buộc như trong cơ sở dữ liệu quan hệ. Tuy nhiên, **SQL++ hỗ trợ ANSI JOIN theo các biểu thức và trường dữ liệu** để kết hợp document từ những collection khác nhau. Đây là khả năng hữu ích khi hai nguồn chia sẻ một business key, chẳng hạn đơn hàng giữ mã khách hàng, còn hồ sơ khách hàng lưu mã tương ứng; hoặc đơn hàng và vận đơn cùng có mã đơn nhưng được tạo và cập nhật độc lập.

Khó khăn của ANSI JOIN không chỉ là viết đúng cú pháp `JOIN ... ON`. Người phát triển còn phải hiểu:

- Trường nào thực sự xác định quan hệ và **có duy nhất theo phạm vi nghiệp vụ** hay không.
- Mỗi bên có bao nhiêu document phù hợp: `1:1`, `1:N` hay có trùng dữ liệu.
- Điều kiện `tenantId`, soft delete và trạng thái nên nằm ở `ON` hay `WHERE`, đặc biệt với `LEFT JOIN`.
- Query Service truy cập collection ở mỗi phía bằng chỉ mục nào, `Fetch` bao nhiêu document, và tạo ra bao nhiêu hàng trung gian.
- Lúc nào nên sử dụng `JOIN ... ON KEYS` hoặc KV lookup thay vì ANSI JOIN theo field.

Bài thuộc chương **Quan hệ và JOIN** của module **SPRING_DATA_COUCHBASE** — xây dựng tầng truy cập Couchbase bằng Spring Data với document mapping, repository, `CouchbaseTemplate` và SQL++; tổ chức bucket/scope/collection, index, TTL, CAS, giao dịch và API reactive. Các ví dụ dùng SQL++ trên Couchbase hỗ trợ collection và ANSI JOIN; tên toán tử trong `EXPLAIN`, API framework và tùy chọn optimizer cần được đối chiếu với phiên bản thực tế.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Viết ANSI `INNER JOIN` và `LEFT JOIN` giữa các collection theo một hoặc nhiều field, sử dụng keyspace `bucket.scope.collection` rõ ràng.
2. Phân biệt ANSI `JOIN ... ON` theo thuộc tính với lookup `JOIN ... ON KEYS` theo document ID.
3. Hiểu **cardinality**, sự nhân hàng, giá trị `NULL`/`MISSING`, kiểu dữ liệu, quy tắc duy nhất và lý do cần đưa `tenantId` vào điều kiện join.
4. Xử lý đúng `ON` và `WHERE` để không vô tình biến outer join thành inner join.
5. Thiết kế secondary/composite index cho mỗi phía, đọc `EXPLAIN` và đo Query Profile trước khi tối ưu.
6. Đối chiếu SQL++ thực từ Spring Data repository/`@Query`/`CouchbaseTemplate` hoặc Java SDK, ánh xạ kết quả join vào DTO.
7. Kiểm soát phân trang, quyền truy cập, scan consistency, TTL, CAS, giao dịch và thay đổi schema khi join qua nhiều document.

## 2. Dữ liệu ví dụ: Order, Customer và Shipment

Giả sử ứng dụng sử dụng bucket `commerce`, hai scope `sales` và `crm`:

```text
commerce
├── sales
│   ├── orders
│   └── shipments
└── crm
    └── customers
```

Ba collection có nhiệm vụ độc lập:

| Collection | Document ID minh họa | Khóa nghiệp vụ quan trọng |
| --- | --- | --- |
| `commerce.sales.orders` | `order::TENANT-A::1001` | `tenantId`, `orderNumber`, `customerCode` |
| `commerce.crm.customers` | `customer::TENANT-A::42` | `tenantId`, `customerCode` |
| `commerce.sales.shipments` | `shipment::TENANT-A::S-7` | `tenantId`, `orderNumber` |

Document Order:

```json
{
  "_class": "salesOrder",
  "tenantId": "TENANT-A",
  "orderNumber": "ORD-1001",
  "customerCode": "C-42",
  "status": "PAID",
  "createdAt": "2026-11-20T08:15:00Z",
  "total": 1500000,
  "deleted": false
}
```

Document Customer:

```json
{
  "_class": "customer",
  "tenantId": "TENANT-A",
  "customerCode": "C-42",
  "displayName": "Nguyen An",
  "accountStatus": "ACTIVE",
  "email": "an@example.test"
}
```

Document Shipment:

```json
{
  "_class": "shipment",
  "tenantId": "TENANT-A",
  "orderNumber": "ORD-1001",
  "trackingNumber": "TRACK-7001",
  "carrier": "Carrier-A",
  "shippedAt": "2026-11-21T08:00:00Z",
  "state": "IN_TRANSIT"
}
```

Trong ví dụ:

- Một Order thường tương ứng **tối đa một Customer theo cặp** `(tenantId, customerCode)`. Đó là **quy tắc do nghiệp vụ và dữ liệu phải bảo đảm**, không phải unique constraint do GSI tự tạo.
- Một Order có thể có **nhiều Shipment** mang cùng cặp `(tenantId, orderNumber)`. Đây là quan hệ 1:N; phép join có thể sinh nhiều hàng cho cùng Order.
- `customerCode` và `orderNumber` là **trường dữ liệu JSON**, không phải Couchbase document ID. `META(...).id` mới thể hiện ID của document.
- Thời gian đang được minh họa bằng chuỗi ISO-8601 UTC có chuẩn hóa. Nếu ứng dụng dùng `Instant` và converter khác, hãy kiểm tra giá trị JSON thực trước khi lập index hoặc sắp xếp.

## 3. SQL++ ANSI JOIN hoạt động như thế nào?

### 3.1. Cú pháp tổng quát

```sql
SELECT ...
FROM `bucket`.`scope_a`.`collection_a` AS a
JOIN `bucket`.`scope_b`.`collection_b` AS b
  ON a.joinField = b.joinField
WHERE ...;
```

`JOIN ... ON` sử dụng **biểu thức điều kiện** để xác định một cặp document có khớp hay không. Điều kiện có thể gồm nhiều field hoặc phép so sánh khác, miễn thuộc dạng SQL++ và phép join được phiên bản hỗ trợ.

Cách viết tên keyspace đầy đủ giúp tránh nhầm query context. Hai collection tên `orders` ở hai scope khác nhau vẫn là hai keyspace độc lập; index và quyền đọc của chúng cũng không tự dùng chung.

### 3.2. INNER JOIN theo business key

Tìm các đơn `PAID` cùng tên khách:

```sql
SELECT META(o).id AS orderId,
       o.orderNumber,
       o.status,
       o.createdAt,
       c.displayName AS customerName
FROM `commerce`.`sales`.`orders` AS o
INNER JOIN `commerce`.`crm`.`customers` AS c
  ON o.customerCode = c.customerCode
 AND o.tenantId = c.tenantId
WHERE o.tenantId = "TENANT-A"
  AND o.status = "PAID"
ORDER BY o.createdAt DESC
LIMIT 20;
```

Ở đây:

1. `o` là alias của Order; `c` là alias của Customer.
2. Hai điều kiện trong `ON` tạo **khóa ghép nghiệp vụ**: mã khách chỉ có ý nghĩa bên trong tenant.
3. `WHERE` chọn các Order thuộc tenant và có trạng thái cần hiển thị.
4. Nếu một Order không tìm được Customer tương ứng, **inner join không giữ Order đó**.
5. Nếu dữ liệu Customer chứa hai document có cùng `tenantId/customerCode`, một Order có thể khớp cả hai và **bị nhân thành hai hàng**.

Kết quả minh họa:

```json
{
  "orderId": "order::TENANT-A::1001",
  "orderNumber": "ORD-1001",
  "status": "PAID",
  "createdAt": "2026-11-20T08:15:00Z",
  "customerName": "Nguyen An"
}
```

**ANSI JOIN không xác thực dữ liệu đầu vào như ràng buộc khóa ngoại.** Nó tìm những cặp document có biểu thức `ON` thỏa điều kiện tại thời điểm query.

### 3.3. Vì sao join một field thường chưa đủ?

Một truy vấn nguy hiểm trong hệ thống nhiều tenant:

```sql
-- Không đủ nếu customerCode chỉ duy nhất trong từng tenant.
SELECT META(o).id AS orderId, c.displayName
FROM `commerce`.`sales`.`orders` AS o
JOIN `commerce`.`crm`.`customers` AS c
  ON o.customerCode = c.customerCode
WHERE o.tenantId = "TENANT-A";
```

Nếu tenant B cũng có `customerCode = "C-42"`, Order của tenant A có thể kết hợp với Customer tenant B. Không chỉ sai thống kê: nó còn tạo **nguy cơ lộ dữ liệu giữa tenant**.

Phiên bản đúng phải ràng buộc cả:

```sql
ON o.tenantId = c.tenantId
AND o.customerCode = c.customerCode
```

Đồng thời, ứng dụng phải lấy tenant được phép truy cập từ **ngữ cảnh xác thực đáng tin cậy**, không tin chuỗi `tenantId` bất kỳ do client cung cấp. Predicate trong SQL++ là một lớp kiểm soát dữ liệu; nó không thay thế authorization.

## 4. ANSI JOIN khác `JOIN ... ON KEYS` như thế nào?

### 4.1. Khi Order lưu document ID của Customer

Giả sử Order thay `customerCode` bằng `customerId`:

```json
{
  "tenantId": "TENANT-A",
  "customerId": "customer::TENANT-A::42"
}
```

Khi đó có thể dùng **lookup join theo key**:

```sql
SELECT META(o).id AS orderId,
       c.displayName AS customerName
FROM `commerce`.`sales`.`orders` AS o
JOIN `commerce`.`crm`.`customers` AS c
  ON KEYS o.customerId
WHERE o.tenantId = "TENANT-A";
```

`ON KEYS o.customerId` đọc giá trị khóa document phía Customer. Không cần tạo một secondary index cho field `customerCode` ở Customer **chỉ để tìm document có ID đã biết**.

### 4.2. Khi chỉ có business key

Nếu Order chỉ lưu `customerCode = "C-42"` còn ID Customer là `customer::TENANT-A::42`, hai giá trị không trùng nhau. `ON KEYS o.customerCode` sẽ không tự hiểu phải dò field `c.customerCode`.

Trong tình huống này, ANSI JOIN:

```sql
ON o.tenantId = c.tenantId
AND o.customerCode = c.customerCode
```

thực hiện ghép theo **field dữ liệu**. Đường truy cập có thể cần secondary index phù hợp ở Customer và cách optimizer chọn nested-loop/index join hoặc hash join sẽ phụ thuộc phiên bản, thống kê và workload.

### 4.3. Bảng so sánh

| Tiêu chí | Lookup `JOIN ... ON KEYS` | ANSI `JOIN ... ON` |
| --- | --- | --- |
| Điều kiện liên kết | ID document phía được join | Biểu thức trên field/giá trị |
| Điều kiện tiên quyết | Bên trái có ID hợp lệ của document đích | Các field ghép phải tương thích và dữ liệu bảo đảm quan hệ |
| Cần GSI bên phải để tìm theo ID? | Thường không | Có thể cần GSI theo field khi kế hoạch sử dụng index join |
| Dữ liệu có thể trùng match? | Một ID trỏ một document trong collection | Có thể khớp nhiều document do business key trùng |
| Tính linh hoạt | Phù hợp tham chiếu document ID | Phù hợp legacy schema, business key hoặc nhiều biểu thức |
| Điểm rủi ro | ID không tồn tại/sai collection/sai tenant | Trùng key, `NULL`/`MISSING`, đổi kiểu, fan-out, scan rộng |

Không nên tuyên bố ANSI JOIN luôn chậm hơn key join. Nếu predicate chọn lọc, index phù hợp và tập dữ liệu nhỏ, ANSI JOIN có thể đáp ứng tốt. Quyết định cần có số liệu thực.

## 5. `LEFT JOIN`: giữ dữ liệu gốc khi chưa có match

### 5.1. INNER JOIN có thể làm mất Order hợp lệ

Trong thực tế, Customer có thể bị xóa theo retention, đơn hàng nhập từ hệ thống cũ có `customerCode` chưa đối soát hoặc dữ liệu CRM tạm chưa đồng bộ. Nếu endpoint là danh sách giao dịch cần hiển thị mọi Order, inner join có thể làm Order biến mất.

`LEFT JOIN` giữ các Order thuộc phía trái ngay cả khi không tìm được Customer:

```sql
SELECT META(o).id AS orderId,
       o.orderNumber,
       o.customerCode,
       o.customerNameAtPurchase,
       c.displayName AS currentCustomerName
FROM `commerce`.`sales`.`orders` AS o
LEFT JOIN `commerce`.`crm`.`customers` AS c
  ON o.tenantId = c.tenantId
 AND o.customerCode = c.customerCode
WHERE o.tenantId = "TENANT-A"
ORDER BY o.createdAt DESC
LIMIT 20;
```

Trường `currentCustomerName` có thể vắng hoặc `MISSING` nếu không match. `customerNameAtPurchase` là **snapshot** nằm trong Order; trường này có thể được dùng làm fallback theo hợp đồng nghiệp vụ.

### 5.2. `ON` và `WHERE` không thay thế được cho nhau trong outer join

Giả sử chỉ muốn ghép Customer có `accountStatus = "ACTIVE"` nhưng **vẫn giữ mọi Order**.

**Đúng với yêu cầu giữ phía trái:**

```sql
SELECT META(o).id AS orderId,
       c.displayName AS activeCustomerName
FROM `commerce`.`sales`.`orders` AS o
LEFT JOIN `commerce`.`crm`.`customers` AS c
  ON o.tenantId = c.tenantId
 AND o.customerCode = c.customerCode
 AND c.accountStatus = "ACTIVE"
WHERE o.tenantId = "TENANT-A";
```

`c.accountStatus = "ACTIVE"` đặt ở `ON` là **điều kiện để Customer được coi là match**, không phải điều kiện chọn Order.

**Câu sau có ngữ nghĩa khác:**

```sql
SELECT META(o).id AS orderId,
       c.displayName AS activeCustomerName
FROM `commerce`.`sales`.`orders` AS o
LEFT JOIN `commerce`.`crm`.`customers` AS c
  ON o.tenantId = c.tenantId
 AND o.customerCode = c.customerCode
WHERE o.tenantId = "TENANT-A"
  AND c.accountStatus = "ACTIVE";
```

Khi Customer không match, điều kiện `c.accountStatus = "ACTIVE"` trong `WHERE` không thỏa và có thể **loại Order khỏi kết quả**. Đây là lỗi thường gặp làm `LEFT JOIN` hành xử gần như inner join với predicate không chấp nhận giá trị vắng.

### 5.3. Xử lý `MISSING`/`NULL` trong projection

Trong SQL++, một field không tồn tại có thể là `MISSING`; field JSON chứa giá trị `null` là `NULL`. Cần kiểm tra sự khác nhau khi ánh xạ kết quả sang DTO và khi đặt predicate.

Nếu endpoint cần luôn trả một chuỗi tên, có thể dùng biểu thức fallback tương thích với phiên bản:

```sql
SELECT META(o).id AS orderId,
       IFMISSINGORNULL(
           c.displayName,
           o.customerNameAtPurchase,
           "Unknown customer"
       ) AS customerName
FROM `commerce`.`sales`.`orders` AS o
LEFT JOIN `commerce`.`crm`.`customers` AS c
  ON o.tenantId = c.tenantId
 AND o.customerCode = c.customerCode
WHERE o.tenantId = "TENANT-A";
```

`IFMISSINGORNULL` minh họa hợp đồng fallback; trong nghiệp vụ thực, có thể cần phân biệt **“khách đã xóa”**, **“CRM chưa đồng bộ”** và **“không có quyền xem”** thay vì gộp tất cả vào một tên mặc định.

## 6. Kiểu dữ liệu và chuẩn hóa business key

### 6.1. Giá trị nhìn giống nhưng không khớp

Hai tài liệu:

```json
{ "customerCode": "00042" }
```

và:

```json
{ "customerCode": 42 }
```

không nên được coi là cùng một khóa khi join chỉ vì biểu diễn nhìn giống. Tương tự, `"C-42"` và `"c-42"` có thể khác về chữ hoa/thường, hay `" C-42 "` khác do khoảng trắng.

**Ưu tiên chuẩn hóa lúc ghi:** cùng kiểu JSON, quy tắc case và dấu cách, phạm vi duy nhất, quy tắc biến đổi dữ liệu legacy. Không tùy tiện thêm `LOWER(...)`, `TRIM(...)` hoặc ép kiểu vào `ON` khi chưa kiểm tra ngữ nghĩa và tác động đến index.

### 6.2. Nếu bắt buộc chuẩn hóa khi truy vấn

Ví dụ legacy data lưu mã khách không cùng quy tắc:

```sql
SELECT META(o).id AS orderId, c.displayName
FROM `commerce`.`sales`.`orders` AS o
JOIN `commerce`.`crm`.`customers` AS c
  ON o.tenantId = c.tenantId
 AND LOWER(TRIM(o.customerCode)) = LOWER(TRIM(c.customerCode))
WHERE o.tenantId = "TENANT-A";
```

Query có thể cần index biểu thức tương thích hoặc phải đánh giá biểu thức trên nhiều document. Nếu dữ liệu lớn và endpoint nóng, **backfill một field đã chuẩn hóa** như `customerCodeNormalized` thường dễ tối ưu/giám sát hơn việc tính lại trên mọi lần join. Dù chọn cách nào, phải bảo đảm hai key ban đầu khác nhau không vô tình bị gom thành cùng giá trị, tạo match sai.

### 6.3. `NULL`, `MISSING` và key không hợp lệ

Với điều kiện bằng thông thường:

```sql
ON o.customerCode = c.customerCode
```

không nên mặc định hai document thiếu `customerCode` sẽ ghép thành một quan hệ hợp lệ. Trước khi chọn join strategy:

- Đếm tỷ lệ document không có field, có `null` hoặc có chuỗi rỗng.
- Định nghĩa chính sách khi thiếu key: loại khỏi join hay giữ Order bằng `LEFT JOIN`.
- Nếu cần đối soát dữ liệu legacy, tạo báo cáo riêng thay vì ghép các bản ghi không có key.
- Kiểm thử khác biệt kiểu số/chuỗi; không dựa vào ép kiểu ngầm.

## 7. Quan hệ 1:1, 1:N và sự nhân hàng khi ANSI JOIN

### 7.1. Giả định một Customer cho mỗi mã

Với `customers` có duy nhất cặp `(tenantId, customerCode)`, một Order khớp tối đa một Customer. `INNER JOIN` thông thường không làm tăng số hàng do phía Customer.

Tuy nhiên, chỉ tạo index:

```sql
CREATE INDEX ix_customers_by_tenant_code
ON `commerce`.`crm`.`customers`(
    `tenantId`,
    `customerCode`
);
```

**không biến cặp đó thành unique constraint**. Couchbase GSI hỗ trợ tìm kiếm; tính duy nhất business key vẫn phải được ứng dụng, quy tắc ID hoặc quy trình kiểm soát dữ liệu bảo đảm.

### 7.2. Nếu Customer bị trùng, một Order thành nhiều hàng

Giả sử có hai Customer cùng cặp `(TENANT-A, C-42)`. Order `ORD-1001` có thể sinh hai hàng:

| orderNumber | customerCode | Customer match |
| --- | --- | --- |
| ORD-1001 | C-42 | Customer X |
| ORD-1001 | C-42 | Customer Y |

Thêm `DISTINCT` ở `SELECT` có thể làm kết quả trông bớt trùng trong một số projection, nhưng không giải quyết việc **không biết Customer nào đúng**. Cần tìm nguyên nhân trùng business key, quyết định bản ghi chuẩn và sửa dữ liệu/quy trình ghi.

### 7.3. Order–Shipment là quan hệ 1:N có chủ đích

Một đơn có thể chia thành hai kiện hàng và hai Shipment:

```json
{
  "tenantId": "TENANT-A",
  "orderNumber": "ORD-1001",
  "trackingNumber": "TRACK-7002",
  "state": "IN_TRANSIT"
}
```

Join:

```sql
SELECT META(o).id AS orderId,
       o.orderNumber,
       s.trackingNumber,
       s.state
FROM `commerce`.`sales`.`orders` AS o
JOIN `commerce`.`sales`.`shipments` AS s
  ON o.tenantId = s.tenantId
 AND o.orderNumber = s.orderNumber
WHERE o.tenantId = "TENANT-A"
  AND o.orderNumber = "ORD-1001";
```

có thể trả **hai hàng cho một Order**. Đây không phải bug nếu endpoint là danh sách Shipment; là bug nếu endpoint muốn mỗi Order đúng một dòng.

### 7.4. Khi cần số Shipment chứ không cần từng Shipment

Sử dụng aggregation có chủ đích:

```sql
SELECT META(o).id AS orderId,
       COUNT(s.trackingNumber) AS shipmentCount
FROM `commerce`.`sales`.`orders` AS o
LEFT JOIN `commerce`.`sales`.`shipments` AS s
  ON o.tenantId = s.tenantId
 AND o.orderNumber = s.orderNumber
WHERE o.tenantId = "TENANT-A"
GROUP BY META(o).id;
```

Với `LEFT JOIN`, dùng `COUNT(s.trackingNumber)` để đếm những giá trị trackingNumber thực sự hiện diện; `COUNT(*)` có thể đếm cả hàng phía trái được giữ khi không có Shipment, dẫn tới kết quả không mong muốn cho số Shipment. Nếu trackingNumber có thể `NULL`/`MISSING` trên một Shipment hợp lệ, cần chọn một định danh không vắng hoặc phương án đếm khác và kiểm thử dữ liệu rỗng.

## 8. JOIN nhiều collection: kiểm soát fan-out và logic nghiệp vụ

Tình huống màn hình cần một Order cùng tên Customer và các Shipment:

```sql
SELECT META(o).id AS orderId,
       o.orderNumber,
       c.displayName AS customerName,
       s.trackingNumber
FROM `commerce`.`sales`.`orders` AS o
LEFT JOIN `commerce`.`crm`.`customers` AS c
  ON o.tenantId = c.tenantId
 AND o.customerCode = c.customerCode
LEFT JOIN `commerce`.`sales`.`shipments` AS s
  ON o.tenantId = s.tenantId
 AND o.orderNumber = s.orderNumber
WHERE o.tenantId = "TENANT-A"
  AND o.status = "PAID";
```

Nếu mỗi Order có một Customer và ba Shipment, kết quả có thể chứa ba hàng Order–Customer–Shipment. Nếu Customer lại bị trùng hai bản ghi theo key, có thể tạo **sáu hàng**. Kết quả nhân hàng qua nhiều phép join có thể gây:

- Tổng hợp doanh thu sai nếu cộng `o.total` trực tiếp trên các hàng sau join.
- Phân trang thiếu Order duy nhất.
- Trả JSON nhiều hàng/trùng trường và tăng chi phí mạng.
- Sort/aggregate ở Query Service lớn hơn dự đoán.

### 8.1. Không cộng giá trị ở cấp Order trên hàng Shipment

Ví dụ sai về ngữ nghĩa:

```sql
-- Một Order có 3 Shipment có thể làm total bị đếm 3 lần.
SELECT SUM(o.total) AS revenue
FROM `commerce`.`sales`.`orders` AS o
JOIN `commerce`.`sales`.`shipments` AS s
  ON o.tenantId = s.tenantId
 AND o.orderNumber = s.orderNumber
WHERE o.tenantId = "TENANT-A";
```

Nếu báo cáo cần doanh thu theo Order, hãy tổng hợp trên **tập Order đúng** hoặc chọn một chiến lược loại trùng ở cấp định danh Order trước khi sum, thay vì tính thẳng trên các hàng đã fan-out.

### 8.2. Khi API muốn mảng Shipment trong mỗi Order

Có thể cân nhắc `NEST` phù hợp hoặc một truy vấn riêng lấy Shipment theo `orderNumber` rồi nhóm tại service. ANSI NEST (nếu phiên bản hỗ trợ và thiết kế phù hợp) có thể làm hình dạng kết quả tự nhiên hơn. Nhưng **NEST không tự giảm số document phải tìm**; vẫn cần index, kiểm soát kích thước mảng và hiểu cách Query Service xử lý dữ liệu.

Nếu một Order có hàng trăm nghìn Shipment/events và chỉ muốn trang đầu, ưu tiên **phân trang collection con** thay vì gom tất cả vào một mảng kết quả rất lớn.

## 9. Phân trang khi ANSI JOIN: trang Order hay trang cặp khớp?

### 9.1. `LIMIT 20` sau join không đồng nghĩa 20 Order

```sql
SELECT META(o).id AS orderId, s.trackingNumber
FROM `commerce`.`sales`.`orders` AS o
JOIN `commerce`.`sales`.`shipments` AS s
  ON o.tenantId = s.tenantId
 AND o.orderNumber = s.orderNumber
WHERE o.tenantId = "TENANT-A"
ORDER BY o.createdAt DESC
LIMIT 20;
```

Nếu mỗi Order có nhiều Shipment, 20 hàng đầu có thể chỉ đại diện cho vài Order. Với hợp đồng “20 Order mới nhất”, phải định nghĩa **đơn vị phân trang là Order trước**.

### 9.2. Phân trang Order trước rồi join

Một cách tiếp cận là chọn trước 20 Order bằng subquery, sau đó kết hợp Customer:

```sql
SELECT o.orderId,
       o.orderNumber,
       o.createdAt,
       c.displayName AS customerName
FROM (
    SELECT META(x).id AS orderId,
           x.tenantId,
           x.customerCode,
           x.orderNumber,
           x.createdAt
    FROM `commerce`.`sales`.`orders` AS x
    WHERE x.tenantId = "TENANT-A"
      AND x.status = "PAID"
    ORDER BY x.createdAt DESC, META(x).id DESC
    LIMIT 20
) AS o
LEFT JOIN `commerce`.`crm`.`customers` AS c
  ON o.tenantId = c.tenantId
 AND o.customerCode = c.customerCode
ORDER BY o.createdAt DESC, o.orderId DESC;
```

Subquery chọn một tập Order cố định trước khi tham gia outer join. Tuy nhiên, nếu Customer có key trùng, **một Order vẫn có thể tạo nhiều hàng sau join**. Cần đảm bảo tính duy nhất dữ liệu. Kết quả/plan tùy cơ chế optimizer, nên xác nhận bằng `EXPLAIN` và kiểm thử phân trang.

Đối với màn hình có các Shipment 1:N, một phương án đơn giản là lấy **trang Order**, sau đó lấy Shipment cho những `orderNumber` đã chọn bằng truy vấn thứ hai (có index theo tenant/orderNumber) và nhóm trong Java. Việc này đổi từ một SQL++ JOIN lớn sang hai bước, có đánh đổi độ mới và số lượt query.

### 9.3. Pagination ổn định cần khóa phụ

`ORDER BY createdAt DESC` không đảm bảo thứ tự tương đối khi nhiều Order trùng timestamp. Dùng thêm `META(o).id` hoặc một khóa duy nhất phù hợp làm tie-breaker; khi đổi `ORDER BY`, phải kiểm tra lại index và plan.

Offset sâu cũng có thể buộc Query Service xử lý nhiều hàng trung gian. Với trang khối lượng lớn, cân nhắc keyset/cursor pagination theo bộ khóa thứ tự đã định, và kiểm thử điều kiện trang kế tiếp.

## 10. Thiết kế index cho ANSI JOIN theo field

### 10.1. Index cho phía Order được lọc và sắp xếp

Nếu endpoint lọc theo tenant và status, sắp xếp đơn mới nhất:

```sql
CREATE INDEX ix_orders_tenant_status_created
ON `commerce`.`sales`.`orders`(
    `tenantId`,
    `status`,
    `createdAt` DESC
);
```

Đây là index ứng viên để **giảm số Order đi vào join** và có thể phục vụ `ORDER BY` khi tiền tố equality phù hợp. Không có nghĩa optimizer luôn chọn nó cho mọi truy vấn, nhất là khi join hoặc projection thay đổi.

### 10.2. Index cho phía Customer theo join key

```sql
CREATE INDEX ix_customers_tenant_code
ON `commerce`.`crm`.`customers`(
    `tenantId`,
    `customerCode`
);
```

Đường truy cập phù hợp cho `o.tenantId = c.tenantId AND o.customerCode = c.customerCode` khi optimizer sử dụng index join vào Customer. Nếu chỉ có index `customerCode` và dữ liệu multi-tenant, phạm vi đọc/ghép có thể rộng hơn; điều kiện tenant vẫn phải có để đảm bảo đúng.

Nếu query cần trả `c.displayName`, Query Service có thể phải `Fetch` Customer sau khi scan index. Một index thêm `displayName` có thể cover projection trong một số tình huống, nhưng tăng dung lượng và chi phí duy trì khi tên thay đổi. **Không thêm field projection chỉ để bỏ `Fetch` trước khi đo.**

### 10.3. Index cho phía Shipment theo cặp khóa

```sql
CREATE INDEX ix_shipments_tenant_order_shipped
ON `commerce`.`sales`.`shipments`(
    `tenantId`,
    `orderNumber`,
    `shippedAt` DESC
);
```

Hữu ích khi tìm những Shipment của một Order và phân trang theo thời gian:

```sql
SELECT META(s).id AS shipmentId,
       s.trackingNumber,
       s.shippedAt
FROM `commerce`.`sales`.`shipments` AS s
WHERE s.tenantId = "TENANT-A"
  AND s.orderNumber = "ORD-1001"
ORDER BY s.shippedAt DESC
LIMIT 20;
```

Index này không tự giúp `customers` và cũng không thay thế index Order. Mỗi collection là một keyspace riêng.

### 10.4. Quan hệ tiền tố và thứ tự khóa

Với index `(tenantId, customerCode)`, truy vấn theo cả hai equality thường có cơ hội dùng dải scan hẹp. Nếu index là `(customerCode, tenantId)`, nó vẫn có thể hữu ích cho hai equality nhưng hiệu quả với **những query chỉ có tenant** sẽ khác.

Với `(tenantId, status, createdAt DESC)`, bỏ `status` khỏi `WHERE` có thể làm khả năng tận dụng thứ tự `createdAt` trên toàn tenant khác đi. Vì vậy, thứ tự khóa phải được chọn theo **workload**, không đơn thuần theo số field được dùng trong `ON`.

### 10.5. Partial index và điều kiện discriminator

Một ứng dụng Spring Data có thể thêm bộ lọc entity `_class` vào SQL++ do repository sinh ra. Có thể cân nhắc partial index:

```sql
CREATE INDEX ix_active_customers_tenant_code
ON `commerce`.`crm`.`customers`(
    `tenantId`,
    `customerCode`
)
WHERE `_class` = "customer"
  AND `accountStatus` = "ACTIVE";
```

Index này chỉ chứa những Customer thỏa predicate. Nó **không phục vụ đầy đủ** cho query cần cả Customer inactive, và prepared query với trạng thái động chưa chắc hàm ý predicate. Giá trị `_class` phải khớp dữ liệu thực và bộ lọc Spring Data, không đoán từ tên class Java.

## 11. `EXPLAIN` và Query Profile: đọc kế hoạch join bằng chứng cứ

### 11.1. Chạy `EXPLAIN` trên đúng câu SQL++

```sql
EXPLAIN
SELECT META(o).id AS orderId,
       o.createdAt,
       c.displayName
FROM `commerce`.`sales`.`orders` AS o
JOIN `commerce`.`crm`.`customers` AS c
  ON o.tenantId = c.tenantId
 AND o.customerCode = c.customerCode
WHERE o.tenantId = "TENANT-A"
  AND o.status = "PAID"
ORDER BY o.createdAt DESC
LIMIT 20;
```

Trong plan, cần tìm:

| Dấu hiệu | Câu hỏi cần trả lời |
| --- | --- |
| `IndexScan` hoặc `IndexScan3` ở Orders | Có dùng index theo tenant/status/createdAt không? `spans` hẹp đến đâu? |
| Scan/index phía Customers | Có đường tìm kiếm phù hợp theo tenant/customerCode không? |
| Operator Join | Dạng index/nested-loop/hash join hay kế hoạch khác? Fan-out thế nào? |
| `Fetch` | Có bao nhiêu document được đọc vì projection hoặc predicate nằm ngoài index? |
| `Filter` | Điều kiện nào còn lọc sau khi quét/join? |
| `Order` | Có sort ngoài index không? Tốn bao nhiêu hàng trung gian? |
| `Limit` | Giới hạn 20 được áp vào những hàng nào, tại giai đoạn nào? |
| `Group`/`Aggregate` | Có đang đếm/sum trên hàng đã bị nhân bởi join không? |

Tên operator và JSON plan có thể khác giữa các phiên bản và chiến lược thực thi. Không suy ra một thuật toán join cố định chỉ từ từ khóa `JOIN` trong SQL++.

### 11.2. Optimizer có thể dùng chiến lược khác dự tính

Trong ANSI JOIN theo field, Query Service có thể chọn đường truy cập dựa trên thống kê, độ chọn lọc và kích thước mỗi nguồn. Chẳng hạn với Customer rất nhỏ, một chiến lược quét/build phía Customer có thể hợp lý; với Customer lớn và rất ít Order sau filter, index lookup phía Customer có thể hợp lý hơn.

Hãy tránh khẳng định “tạo index phía phải là optimizer sẽ dùng ngay”. Thay vào đó:

1. Xác định index đã `online` trên đúng keyspace.
2. Đọc plan và dải scan.
3. Đo thời gian, số entry/documents và cardinality thực tế.
4. Kiểm tra dữ liệu và phân bố tenant/status thực tế.
5. Chỉ sử dụng hints để chẩn đoán/thử nghiệm khi cần, theo cú pháp phiên bản hỗ trợ; không ghim join strategy mù quáng trong production.

### 11.3. Query Profile mới cho biết chi phí thực

`EXPLAIN` cung cấp **kế hoạch dự kiến**, không phải thời gian thực thi đáng tin cậy cho một request production. Khi benchmark, cần thêm Query Profile và metrics:

| Nhóm chỉ số | Ý nghĩa |
| --- | --- |
| Entries scanned ở Orders/Customers | Mỗi phía quét bao nhiêu entry |
| Rows into/out of Join | Có phát sinh fan-out bất thường không |
| Documents fetched | Chi phí đọc JSON gốc |
| Sort/Group time | `ORDER BY`/aggregate có tốn sau join không |
| Query p50/p95/p99 và timeout | Có đạt SLA dưới tải không |
| Index Service CPU/memory/disk | Thêm index làm thay đổi chi phí tài nguyên thế nào |
| KV mutation/index lag | Index có bắt kịp khi ghi nhiều không |

So sánh cùng dataset/cluster, tỷ lệ tenant lớn–nhỏ và tham số đại diện. Một query với tenant chỉ có 10 Order không đủ để dự báo chi phí của tenant có 10 triệu Order.

## 12. Spring Data Couchbase mapping: quan hệ field không tự thành JOIN

### 12.1. Entity Order và Customer

Ví dụ dùng hai collection độc lập:

```java
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.TypeAlias;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;
import org.springframework.data.couchbase.core.mapping.Collection;

@Document
@TypeAlias("salesOrder")
@Scope("sales")
@Collection("orders")
public class SalesOrder {
    @Id
    private String id;

    private String tenantId;
    private String orderNumber;
    private String customerCode;
    private String status;
    private Instant createdAt;
    private long total;

    // Constructor, getter, setter được lược bỏ.
}
```

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.TypeAlias;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;
import org.springframework.data.couchbase.core.mapping.Collection;

@Document
@TypeAlias("customer")
@Scope("crm")
@Collection("customers")
public class Customer {
    @Id
    private String id;

    private String tenantId;
    private String customerCode;
    private String displayName;
    private String accountStatus;

    // Constructor, getter, setter được lược bỏ.
}
```

Bucket `commerce` được xác định từ cấu hình Couchbase/operations mapping của ứng dụng. `@Scope` và `@Collection` chỉ định nơi lưu entity theo mô hình được hỗ trợ, **không tự suy ra bucket hoặc tạo relation**.

Field `customerCode` trong cả hai Java class không làm Spring Data tự JOIN hay tự kiểm tra uniqueness. Đây là hai thuộc tính JSON có cùng ý nghĩa nghiệp vụ; service phải viết rõ khi cần kết hợp chúng.

### 12.2. Derived repository query chỉ truy vấn entity đích

```java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface SalesOrderRepository
        extends CouchbaseRepository<SalesOrder, String> {

    List<SalesOrder> findByTenantIdAndStatusOrderByCreatedAtDesc(
        String tenantId, String status
    );
}
```

Method này có thể được Spring Data chuyển thành SQL++ trên `orders`, nhưng **không tự lấy `Customer.displayName`**. Nếu cần DTO kết hợp, có thể chọn hai bước (query Order, rồi lookup Customer) hoặc một SQL++ ANSI JOIN tường minh.

Repository trả entity đầy đủ có thể sinh projection và bộ lọc `_class` khác câu SQL++ viết tay. Khi tối ưu index, hãy lấy **SQL++ thực**, không kết luận chỉ từ tên method.

### 12.3. `@Query` cho entity không đồng nghĩa projection đa nguồn

```java
import java.util.List;
import org.springframework.data.couchbase.repository.Query;

public interface SalesOrderRepository
        extends CouchbaseRepository<SalesOrder, String> {

    @Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} " +
           "AND tenantId = $1 AND status = $2")
    List<SalesOrder> findOrdersForTenant(
        String tenantId, String status
    );
}
```

Macro `#{#n1ql.selectEntity}` và `#{#n1ql.filter}` hỗ trợ ánh xạ một entity, bao gồm metadata/điều kiện phân biệt kiểu. Chúng không tạo JOIN giúp trả một cấu trúc mới gồm Order và Customer. Với SQL++ kết hợp nhiều nguồn, cần thiết kế `SELECT`/alias/DTO tương ứng và kiểm tra khả năng mapping của phiên bản Spring Data Couchbase.

### 12.4. `CouchbaseTemplate` và Java SDK cho projection tùy chỉnh

`CouchbaseTemplate` cho phép làm việc với document và truy vấn qua các API được hỗ trợ của phiên bản đang dùng. Khi muốn kiểm soát SQL++ join và DTO nhiều nguồn, một cách rõ ràng là dùng Java SDK qua bean `Cluster`:

```java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryResult;

import java.util.List;

import static com.couchbase.client.java.query.QueryOptions.queryOptions;

public final class OrderCustomerReadService {
    private final Cluster cluster;

    public OrderCustomerReadService(Cluster cluster) {
        this.cluster = cluster;
    }

    public List<OrderCustomerRow> findPaidOrders(
            String tenantId, int limit) {
        String sql = """
            SELECT META(o).id AS orderId,
                   o.orderNumber AS orderNumber,
                   c.displayName AS customerName
            FROM `commerce`.`sales`.`orders` AS o
            LEFT JOIN `commerce`.`crm`.`customers` AS c
              ON o.tenantId = c.tenantId
             AND o.customerCode = c.customerCode
            WHERE o.tenantId = $tenantId
              AND o.status = "PAID"
            ORDER BY o.createdAt DESC, META(o).id DESC
            LIMIT $limit
            """;

        JsonObject parameters = JsonObject.create()
            .put("tenantId", tenantId)
            .put("limit", limit);

        QueryResult result = cluster.query(
            sql, queryOptions().parameters(parameters)
        );

        return result.rowsAsObject().stream()
            .map(row -> new OrderCustomerRow(
                row.getString("orderId"),
                row.getString("orderNumber"),
                row.containsKey("customerName")
                    ? row.getString("customerName")
                    : null
            ))
            .toList();
    }

    public record OrderCustomerRow(
        String orderId,
        String orderNumber,
        String customerName
    ) {}
}
```

Ví dụ sử dụng Java text block/record, Java SDK 3.x và cú pháp SQL++ tham số. Trong ứng dụng thật cần thêm validation cho `limit`, timeout/error handling, cấu hình consistency và lifecycle bean `Cluster`. `LEFT JOIN` có thể tạo field phía Customer vắng nên DTO cho phép `null`, hoặc áp dụng fallback theo hợp đồng API.

Truy vấn phải được **tham số hóa**; không ghép `tenantId`/`customerCode` từ request trực tiếp vào SQL++. Với API template tương đương, kiểm tra đúng version và cách ánh xạ DTO; không giả định mọi phương thức của Java SDK cũng hiện diện y hệt trên `CouchbaseTemplate`.

### 12.5. Khi nào chuyển sang lookup theo ID?

Nếu mọi Order đều lưu được `customerId` chính xác và Customer thường được truy cập bằng ID, việc chuyển `customerCode` join sang `ON KEYS o.customerId` có thể giảm nhu cầu index phía Customer theo business key. Nhưng quá trình chuyển schema cần backfill/đối soát để không tạo tham chiếu sai, không chỉ thay câu SQL++.

## 13. KV, ANSI JOIN và read model: lựa chọn cho các mẫu đọc

| Mục tiêu | Ứng viên triển khai | Đánh đổi chính |
| --- | --- | --- |
| Xem một Order đã biết document ID | KV `findById` | Đơn giản, không JOIN; chưa có Customer hiện tại |
| Xem một Order và Customer đã biết ID | Hai KV reads hoặc lookup join | Cần xử lý Customer thiếu/độ mới |
| Danh sách Order và Customer theo business key | ANSI JOIN theo tenant/customerCode | Cần index, bảo đảm key hợp lệ/unique |
| Danh sách Order có nhiều Shipment | Query hai bước, join + group, hoặc read model | Cần kiểm soát fan-out và phân trang |
| Dashboard đọc cực thường xuyên, projection ổn định | Read model phi chuẩn hóa | Tốn storage, event sync, backfill, consistency |
| Báo cáo tổng hợp Order không cần field Customer | Query Orders độc lập | Tránh JOIN không tạo giá trị |

**Không JOIN theo thói quen.** Nếu màn hình chỉ cần `status` và `total`, Customer không tham gia kết quả, việc thêm join có thể làm tăng chi phí mà không cải thiện dữ liệu.

Nếu chọn read model, phải xác định nguồn chân lý, trường sao chép, độ trễ chấp nhận và cách xử lý event trễ/lặp. Không coi denormalization là bản sao luôn đồng bộ tự động.

## 14. Tính nhất quán, TTL, CAS và giao dịch quanh join

### 14.1. GSI cập nhật bất đồng bộ

Secondary index của Couchbase được duy trì bất đồng bộ với KV mutation. Sau khi ghi Order hoặc Customer, một truy vấn SQL++ join có thể chưa phản ánh ngay một thay đổi mới trên tất cả đường scan nếu sử dụng consistency không yêu cầu chờ.

| Scan consistency | Ý nghĩa |
| --- | --- |
| `NOT_BOUNDED` | Không yêu cầu chờ GSI bắt kịp mutation trước khi truy vấn; có thể thấy kết quả tạm cũ |
| `REQUEST_PLUS` | Chờ index bắt kịp mutation liên quan ở thời điểm query; độ mới cao hơn nhưng có thể tăng latency |

Đừng đồng nhất “`CREATE INDEX` đã online” với “dữ liệu vừa ghi luôn xuất hiện trong JOIN”. Trạng thái build index và scan consistency giải quyết **hai bài toán khác nhau**.

### 14.2. JOIN không tạo snapshot giao dịch nhiều document mặc định

Một Order đã được ghi `status = "PAID"`, Customer đang đổi tên, Shipment đang cập nhật trạng thái. SQL++ JOIN thông thường không tự có cam kết rằng tất cả document ở nhiều collection là **một snapshot nghiệp vụ nguyên tử**.

Nếu cần bất biến mạnh trên nhiều document, phải thiết kế transaction/cơ chế ghi phù hợp SDK và phiên bản Couchbase. Nếu chỉ cần hiển thị tên Customer hiện hành trên danh sách Order, có thể chấp nhận tính nhất quán cuối cùng với fallback/snapshot và chỉ số độ mới rõ ràng.

### 14.3. CAS chỉ kiểm soát xung đột ghi của document

`CAS` và `@Version` có thể giúp phát hiện hai cập nhật cạnh tranh trên Order hoặc Customer. Nhưng chúng không tự đặt ràng buộc `o.customerCode = c.customerCode`, không làm hai document có cùng business key trở nên duy nhất và không tự đảm bảo JOIN trả kết quả tại cùng thời điểm.

Khi Customer đổi mã, Order cũ giữ mã trước đó có thể trở thành **orphan về mặt business key**. Cần kế hoạch quản lý đổi mã, version/reference hoặc migration; một JOIN nhanh không sửa dữ liệu bị lệch.

### 14.4. TTL và xóa không tạo cascade

Customer hết hạn hoặc bị xóa theo retention không khiến Order tự biến mất hay `customerCode` tự thay. Với `LEFT JOIN`, Order có thể còn nhưng field phía Customer vắng. Nếu Order giữ snapshot `customerNameAtPurchase`, snapshot đó cũng cần tuân thủ chính sách dữ liệu cá nhân và retention áp dụng.

Tương tự, Shipment hết hạn sẽ thay đổi số hàng của JOIN/COUNT. Khi nghiệp vụ cần lưu lịch sử không thay đổi, cần thiết kế snapshot hoặc collection lịch sử riêng thay vì dựa hoàn toàn vào liên kết tới dữ liệu có TTL ngắn.

### 14.5. Duy nhất business key cần cơ chế khác GSI

Một index trên `(tenantId, customerCode)` giúp tìm nhanh, **không cấm insert một Customer thứ hai với cùng cặp giá trị**. Khi cần uniqueness nghiêm ngặt, có thể thiết kế document ID xác định từ khóa đã chuẩn hóa và dùng thao tác **insert-if-absent**, hoặc một cơ chế quản lý phân bổ khóa/transaction phù hợp với nghiệp vụ. Quy tắc phải được mọi writer tuân thủ và có kiểm tra dữ liệu legacy.

## 15. Reactive API và JOIN có nhiều hàng

### 15.1. Reactive không làm chi phí join biến mất

`ReactiveCouchbaseRepository` hoặc reactive SDK có thể cải thiện cách Java service sử dụng luồng I/O và giới hạn tài nguyên thread. Nhưng Query Service vẫn phải thực hiện index scan, join, fetch, sort và trả dữ liệu.

Nếu một Order join ra 100 Shipment, reactive vẫn nhận 100 hàng khi SQL++ trả 100 hàng. Muốn một DTO Order duy nhất, cần thiết kế projection/aggregate/group hoặc thực hiện quá trình gom có chủ đích trong service.

### 15.2. N+1 và giới hạn concurrency

Một cách thay ANSI JOIN là tải trang Order rồi gọi query tìm Customer theo `customerCode` cho **mỗi Order**:

```java
ordersFlux.flatMap(order ->
    customerLookupByTenantAndCode(
        order.getTenantId(),
        order.getCustomerCode()
    ).map(customer -> new OrderWithCustomer(order, customer)),
    8
);
```

Đây là giả mã reactive với các hàm/DTO của ứng dụng, không phải API có sẵn nguyên văn. Nó có thể tạo N lượt SQL++/KV lookup. Concurrency `8` chỉ minh họa việc **giới hạn song song**, không phải giá trị tối ưu.

Cân nhắc khử trùng lặp các cặp `(tenantId, customerCode)` trong một trang, batch query, ANSI JOIN hoặc read model. Đo p95 latency, số request đến KV/Query Service và tỷ lệ Customer được dùng lại; không chỉ tăng concurrency để che fan-out.

### 15.3. Nhớ ranh giới phân quyền

Một truy vấn join Customer để hiển thị dashboard phải kiểm tra quyền truy cập các field Customer, không chỉ quyền xem Order. Nếu UI chỉ cần `displayName`, tránh `SELECT c.*` khiến email hoặc thông tin nhạy cảm vô tình đi qua DTO/response.

Ở hệ thống đa tenant, lỗi thiếu `tenantId` trong `ON` có thể làm rò dữ liệu nhanh hơn khi áp dụng reactive concurrency lớn. Tính đúng và bảo mật phải được kiểm tra trước khi tối ưu hiệu năng.

## 16. Quy trình triển khai một ANSI JOIN mới trong production

### 16.1. Thu thập mẫu truy vấn thực

Xác định API nào cần Customer/Shipment, tần suất, projection, điều kiện tenant/status, số record mỗi tenant và cardinality của business key. Lưu câu SQL++ thật từ repository/template/SDK, gồm tham số và query context.

### 16.2. Kiểm tra chất lượng dữ liệu trước DDL

Đối soát:

- Cặp `(tenantId, customerCode)` có trùng Customer không?
- Order có customerCode trống, `NULL` hoặc `MISSING` không?
- Hai phía cùng lưu chuỗi hay có sự khác biệt kiểu/case/space?
- Tenant B có code trùng tenant A không?
- Có Customer inactive/deleted cần xử lý khác nhau không?
- Khả năng một Order có nhiều Shipment thực tế lớn đến đâu?

Nếu nguồn dữ liệu không bảo đảm quy tắc, một index mới chỉ giúp **tìm những bản ghi sai nhanh hơn**, không sửa được kết quả.

### 16.3. Tạo index có kiểm soát

Chọn index trên các keyspace theo `WHERE` và `ON`, chạy DDL trong pipeline với quyền phù hợp. Kiểm tra index đã build và `online`:

```sql
SELECT name, state, index_key, condition,
       bucket_id, scope_id, keyspace_id
FROM system:indexes
WHERE bucket_id = "commerce"
  AND (
      (scope_id = "sales" AND keyspace_id = "orders")
      OR
      (scope_id = "crm" AND keyspace_id = "customers")
  );
```

Nếu có cùng tên index trên collection khác, không được coi đó là index của query mới. Với index lớn, cần dự trù Index Service capacity và thời điểm build; không bật code dựa duy nhất vào kết quả `CREATE INDEX` được chấp nhận.

### 16.4. Kiểm tra `EXPLAIN`, dữ liệu và tải thực

Chạy `EXPLAIN` của SQL++ tương đương runtime, rồi Query Profile trên tenant lớn/nhỏ. Kiểm thử:

1. Một Order có đúng một Customer.
2. Order thiếu Customer.
3. Customer inactive.
4. Hai Customer trùng business key (lab).
5. Mã khách trùng ở hai tenant.
6. Order có một và nhiều Shipment.
7. Field kiểu số/chuỗi không đồng nhất.
8. `NULL`/`MISSING`, dữ liệu đã xóa mềm.
9. Phân trang và thứ tự với timestamp trùng.

Nếu số hàng kết quả không đáp ứng hợp đồng API, **không bật production** chỉ vì latency tốt.

### 16.5. Canary, rollback và thu hồi index

Triển khai query qua feature flag/canary khi phù hợp; giám sát lỗi, timeout, số row, p95/p99, Index Service và write latency. Giữ đường đọc cũ trong giai đoạn chuyển tiếp. Nếu cần rollback, có thể tắt query mới mà chưa xóa index vừa tạo; thu hồi index là một bước riêng khi chắc chắn không còn query/job khác phụ thuộc.

Không cấp quyền tạo/drop index cho mọi runtime instance chỉ để bootstrap; có thể dùng công cụ migration/đội vận hành chuyên trách. Những annotation index tự động của Spring Data có ích cho phát triển nhưng không thay thế một quy trình DDL có readiness gate và rollback production.

## 17. Khi cần chuyển từ business key sang document ID

Nếu liên tục phải join theo `customerCode`, dữ liệu đổi mã thường xuyên hoặc khó bảo đảm uniqueness, có thể cân nhắc bổ sung `customerId` là document ID ổn định:

```json
{
  "customerCode": "C-42",
  "customerId": "customer::TENANT-A::42"
}
```

Quy trình chuyển đổi:

1. Chốt quy tắc ID Customer và kiểm tra tenant/uniqueness của dữ liệu legacy.
2. Thêm field `customerId` cho các Order mới; vẫn duy trì `customerCode` theo yêu cầu tương thích.
3. Backfill `customerId` cho Order cũ; ghi nhận các trường hợp Customer thiếu/trùng và **không đoán ID**.
4. Đồng bộ những Order và Customer thay đổi trong lúc backfill.
5. So sánh kết quả ANSI JOIN cũ với `JOIN ... ON KEYS` mới trên tập dữ liệu đại diện.
6. Tạo/kiểm tra index cho các query khác còn dùng `customerCode`.
7. Chuyển đọc qua canary, đối soát số hàng, latency và quyền tenant.
8. Chỉ bỏ field/index cũ sau khi mọi phiên bản ứng dụng/job đã chuyển và có đường rollback.

**Tham chiếu ID thường giúp xác định document đích rõ ràng hơn**, nhưng không tự bảo đảm referential integrity hay chính sách xóa. ID vẫn có thể sai, document đã bị xóa hoặc thuộc tenant khác; cần validation và authorization tương ứng.

## 18. Chẩn đoán các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Kiểm tra/hướng xử lý |
| --- | --- | --- |
| JOIN trả trống dù hai document “có mã giống nhau” | Khác kiểu chuỗi/số, case, space, `NULL`/`MISSING` | Kiểm tra JSON thực, chuẩn hóa dữ liệu và so sánh predicate |
| Order tenant A ghép Customer tenant B | Chỉ join theo `customerCode` | Thêm tenant trong `ON`, kiểm tra phân quyền |
| Một Order thành hai hàng | Business key Customer không duy nhất | Tìm duplicate, xử lý uniqueness thay vì chỉ `DISTINCT` |
| `LEFT JOIN` làm mất Order thiếu Customer | Lọc field Customer trong `WHERE` | Chuyển điều kiện match vào `ON` theo ngữ nghĩa |
| Query nhanh trên dữ liệu test nhưng chậm ở production | Tenant lớn, join fan-out hoặc plan khác | Benchmark đại diện, Query Profile, index spans |
| `LIMIT 20` nhưng chỉ có vài Order khác nhau | Join với nhiều Shipment tạo nhiều hàng | Phân trang Order trước, xử lý tập Shipment riêng |
| Doanh thu tổng hợp cao gấp nhiều lần | `SUM(o.total)` sau join 1:N | Tổng hợp ở cấp Order trước hoặc khử trùng lặp đúng |
| SQL++ dùng index không mong đợi | Không khớp `WHERE`/`ON`, index chưa online hoặc cost khác | `system:indexes`, `EXPLAIN`, kiểm tra plan |
| Repository query đúng nhưng Java DTO thiếu field | Projection/alias khác cấu trúc DTO, `MISSING` | Ánh xạ rõ alias và fallback, kiểm tra `@Query` |
| JOIN theo `customerCode` chậm dù Customer có index | Index chưa phù hợp thứ tự key hoặc optimizer chọn hash/scan | Xem hai phía, Query Profile, thống kê |
| Vừa cập nhật Customer nhưng list chưa phản ánh | GSI không bắt kịp/độ mới không đủ | Xác định scan consistency hoặc KV |
| Customer bị xóa, Order còn reference | Không có cascade FK/TTL tự động | Chính sách snapshot, cleanup, retention |
| Cập nhật mã khách gây Order mồ côi | Business key thay đổi nhưng reference cũ giữ nguyên | ID ổn định hoặc migration/versioning |
| Fan-out reactive gây timeout | N+1 lookups hoặc join trả quá nhiều hàng | Giới hạn concurrency, batch/DTO/đổi query |

## 19. Bài thực hành: từ một JOIN đúng đến một JOIN hiệu quả

### 19.1. Chuẩn bị dữ liệu lab

Trong môi trường thử nghiệm, tạo ít nhất:

| Collection | Bản ghi | Điểm kiểm tra |
| --- | --- | --- |
| `sales.orders` | `ORD-1001` / tenant A / customer C-42 | Có Customer khớp |
| `sales.orders` | `ORD-1002` / tenant A / customer C-99 | Không có Customer |
| `sales.orders` | `ORD-2001` / tenant B / customer C-42 | Trùng mã giữa tenant |
| `crm.customers` | Tenant A / C-42 / ACTIVE | Match hợp lệ |
| `crm.customers` | Tenant B / C-42 / ACTIVE | Dùng để test thiếu điều kiện tenant |
| `sales.shipments` | Hai Shipment cho `ORD-1001` | Test fan-out 1:N |

Đặt document ID khác nhau giữa các bản ghi, và thêm một field `createdAt` chuẩn hóa cho Order. Những thao tác xóa/sửa và tạo duplicate sau đây chỉ được thực hiện trong **lab**, không trên dữ liệu production.

### 19.2. Bài A — Đối chiếu INNER và LEFT JOIN

Chạy:

```sql
SELECT META(o).id AS orderId,
       o.orderNumber,
       c.displayName AS customerName
FROM `commerce`.`sales`.`orders` AS o
INNER JOIN `commerce`.`crm`.`customers` AS c
  ON o.tenantId = c.tenantId
 AND o.customerCode = c.customerCode
WHERE o.tenantId = "TENANT-A";
```

Đổi `INNER JOIN` thành `LEFT JOIN`. Ghi số Order và giá trị `customerName` của Order thiếu Customer. Sau đó thêm điều kiện `c.accountStatus = "ACTIVE"` lần lượt vào `ON` và `WHERE`, giải thích khác biệt.

### 19.3. Bài B — Kiểm tra join tenant và duplicate

Tạm bỏ `o.tenantId = c.tenantId` khỏi `ON` và quan sát Order tenant A có thể match Customer tenant B. Khôi phục điều kiện ngay sau khi ghi nhận kết quả.

Thêm một Customer lab thứ hai có cùng `(TENANT-A, C-42)` và chạy lại inner join. Ghi số hàng tăng và giải thích tại sao index `(tenantId, customerCode)` không tự ngăn trùng.

### 19.4. Bài C — Kiểm tra 1:N fan-out và báo cáo

```sql
SELECT o.orderNumber,
       s.trackingNumber
FROM `commerce`.`sales`.`orders` AS o
JOIN `commerce`.`sales`.`shipments` AS s
  ON o.tenantId = s.tenantId
 AND o.orderNumber = s.orderNumber
WHERE o.tenantId = "TENANT-A"
  AND o.orderNumber = "ORD-1001";
```

Vì `ORD-1001` có hai Shipment, hãy giải thích số hàng và hệ quả nếu chạy `SUM(o.total)` trực tiếp trên tập hàng sau join. Thiết kế phương án trả một Order với danh sách Shipment nhưng vẫn phân trang ở cấp Order đúng.

### 19.5. Bài D — Tạo index và đọc `EXPLAIN`

Trong lab, tạo:

```sql
CREATE INDEX ix_lab_orders_tenant_status_created
ON `commerce`.`sales`.`orders`(
    `tenantId`, `status`, `createdAt` DESC
);

CREATE INDEX ix_lab_customers_tenant_code
ON `commerce`.`crm`.`customers`(
    `tenantId`, `customerCode`
);

CREATE INDEX ix_lab_shipments_tenant_order
ON `commerce`.`sales`.`shipments`(
    `tenantId`, `orderNumber`
);
```

Chờ index ở trạng thái khả dụng, kiểm tra `system:indexes` rồi chạy `EXPLAIN` cho JOIN Order–Customer và Order–Shipment. Ghi:

- Đúng keyspace và index ở mỗi phía.
- Index spans theo tenant/status/customerCode/orderNumber.
- `Fetch`/`Filter`/`Order`, nếu có.
- Số hàng đầu vào và đầu ra của phép join khi chạy Query Profile.
- Latency khi tăng số Order và số Shipment.

### 19.6. Bài E — Thử hai chiến lược liên kết

Thêm `customerId` chuẩn cho Order sau khi đối soát. Thử:

```sql
EXPLAIN
SELECT META(o).id AS orderId, c.displayName
FROM `commerce`.`sales`.`orders` AS o
JOIN `commerce`.`crm`.`customers` AS c
  ON KEYS o.customerId
WHERE o.tenantId = "TENANT-A";
```

So sánh với ANSI JOIN theo `customerCode`. Không chỉ đo thời gian: xác minh tập Order, Customer ID được ghép, tenant và hành vi khi Customer không tồn tại. Nêu các điều kiện phải hoàn thành trước khi cân nhắc migration production.

### Mẫu sổ đo thực nghiệm

| Phương án | Số Order đầu vào | Số hàng kết quả | Index scan chính | `Fetch` / `Order` | p95 latency | Đánh giá |
| --- | --- | --- | --- | --- | --- | --- |
| Inner ANSI JOIN | Chưa đo | Chưa đo | Chưa đo | Chưa đo | Chưa đo | Có loại Order thiếu Customer không? |
| Left ANSI JOIN | Chưa đo | Chưa đo | Chưa đo | Chưa đo | Chưa đo | Giữ phía trái? |
| ANSI JOIN thiếu tenant | Chưa đo | Chưa đo | Chưa đo | Chưa đo | Chưa đo | Kiểm tra rò ghép dữ liệu |
| Order–Shipment 1:N | Chưa đo | Chưa đo | Chưa đo | Chưa đo | Chưa đo | Fan-out |
| Lookup `ON KEYS` | Chưa đo | Chưa đo | Chưa đo | Chưa đo | Chưa đo | So với business key |

Các giá trị “Chưa đo” là vị trí để người học ghi kết quả thực nghiệm; không phải số liệu từ một cluster đã chạy.

### Câu hỏi tự kiểm tra

1. Vì sao `o.customerCode = c.customerCode` không nhất thiết đủ trong môi trường multi-tenant?
2. ANSI JOIN theo field khác lookup `JOIN ... ON KEYS` ở đâu?
3. Khi một Order không tìm thấy Customer, `INNER JOIN` và `LEFT JOIN` trả gì?
4. Vì sao điều kiện `c.accountStatus = "ACTIVE"` ở `ON` và ở `WHERE` có thể tạo kết quả khác?
5. `NULL` và `MISSING` ảnh hưởng thế nào đến join key?
6. Nếu hai Customer trùng business key, một Order có thể xuất hiện bao nhiêu hàng? Vì sao `DISTINCT` không sửa được nguyên nhân?
7. Một Order có ba Shipment: vì sao `LIMIT 20` không đảm bảo chọn 20 Order duy nhất?
8. Vì sao `SUM(o.total)` trên kết quả join với Shipment có thể sai?
9. Hai index nào thường được cân nhắc khi query lọc Order theo tenant/status và JOIN Customer theo tenant/customerCode?
10. Vì sao index `(tenantId,customerCode)` không phải unique constraint?
11. Khi một JOIN chậm, phải kiểm tra những operator/số liệu nào từ `EXPLAIN` và Query Profile?
12. Tại sao repository Spring Data có field `customerCode` không tự JOIN Customer?
13. Khi nào hai KV reads hoặc read model phù hợp hơn ANSI JOIN?
14. CAS, transaction và scan consistency giải quyết ba nhóm vấn đề gì khác nhau?
15. Cần làm những gì trước khi chuyển từ join business key sang tham chiếu document ID?

## 20. Kết luận

**ANSI JOIN trong Couchbase SQL++ cho phép kết hợp các collection bằng biểu thức trên trường dữ liệu, nhưng không tạo ra foreign key hoặc bảo đảm tính duy nhất.** Khi viết `JOIN ... ON`, hãy xác định business key đúng, gắn tenant vào điều kiện liên kết, chuẩn hóa kiểu/giá trị, kiểm thử trường hợp thiếu và trùng key, rồi quyết định `INNER` hay `LEFT` dựa trên hợp đồng API.

Để triển khai với **Spring Data Couchbase**, hãy dùng repository cho những truy vấn entity phù hợp, SQL++ tường minh và DTO cho projection đa nguồn khi cần, phân biệt join theo business key với lookup `ON KEYS` hoặc KV theo ID. Thiết kế secondary index cho từng collection, xác nhận `EXPLAIN` và Query Profile, theo dõi fan-out/phân trang, đồng thời bảo vệ quyền tenant, TTL, CAS, transaction và scan consistency. Một phép join thành công không chỉ **chạy nhanh**: nó phải **trả đúng đối tượng, đúng số hàng và giữ vững ý nghĩa dữ liệu khi hệ thống thay đổi**.
