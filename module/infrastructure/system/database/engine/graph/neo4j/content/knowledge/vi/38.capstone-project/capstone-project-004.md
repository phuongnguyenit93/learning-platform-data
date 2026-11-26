# Xây dựng bộ truy vấn đọc, ghi, tổng hợp và tìm đường — Đồ án thực hành Neo4j

## 1. Đề bài và mục tiêu đầu ra

Đồ án này yêu cầu xây dựng **một bộ truy vấn Cypher hoàn chỉnh** cho hệ thống thương mại và vận chuyển B2B sử dụng Neo4j. Thay vì học rời rạc từng mệnh đề `MATCH`, `MERGE`, `WITH` hoặc `shortestPath`, người học phải giải quyết các tình huống nghiệp vụ có **dữ liệu mẫu, ràng buộc tính đúng, giới hạn kết quả, transaction và tiêu chí kiểm thử rõ ràng**.

Bối cảnh: một công ty có nhà cung cấp, sản phẩm, khách hàng, đơn hàng và các kho trung chuyển. Ứng dụng Java/Spring Data Neo4j cần:

1. **Đọc**: xem sản phẩm theo nhà cung cấp, tồn kho theo kho, danh sách/chi tiết đơn hàng theo khách.
2. **Ghi**: tạo đơn và dòng hàng theo khóa nghiệp vụ, tránh tạo trùng khi ứng dụng retry, cập nhật trạng thái theo quy tắc.
3. **Tổng hợp**: tính số đơn đã thanh toán, doanh thu theo SKU/khoảng thời gian và những đơn có tổng tiền lớn.
4. **Tìm đường**: tìm đường ít chặng và đường có tổng thời gian nhỏ nhất giữa hai kho, giải thích khi nào hai đáp án khác nhau.
5. **Tích hợp**: ánh xạ kết quả thành DTO Java, quản lý session/transaction, bảo vệ tenant và quan sát hiệu năng bằng `EXPLAIN`/`PROFILE`.

Bài viết tự chứa về nghiệp vụ, schema, dữ liệu seed và mẫu lời giải. Bạn có thể làm từng mục rồi so kết quả với phần giải thích; không bắt buộc dùng GDS hoặc APOC cho phần nền tảng.

**Đầu ra cần nộp** của một đồ án thật: sơ đồ graph, script tạo constraint/index và seed; truy vấn Cypher có tham số; API/repository Java; bảng kết quả kỳ vọng và kiểm thử âm tính; execution plan được đo; tài liệu giới hạn và cách chạy lại.

> **Phạm vi phiên bản:** cú pháp cơ bản theo Neo4j 5.23+ và các bản hiện hành; ví dụ Java dựa trên Java Driver 6.x, Java 17+; cú pháp `CALL (variable)` và khả năng GDS phụ thuộc phiên bản. Khi áp dụng trên database khác, kiểm tra edition, quyền và tương thích phiên bản. Không chạy các script ghi thử trên dữ liệu production.

## 2. Chuyển yêu cầu thành hợp đồng truy vấn

Trước khi tạo node, hãy định nghĩa mỗi truy vấn cần **đầu vào, đầu ra, giới hạn và bất biến** gì.

| Mã | Ca sử dụng | Đầu vào | Đầu ra | Bất biến quan trọng |
| --- | --- | --- | --- | --- |
| R1 | Danh sách đơn theo khách | `tenantId, clientId, limit` | Danh sách đơn mới nhất | Không lộ đơn tenant/khách khác |
| R2 | Chi tiết đơn và dòng hàng | `tenantId, clientId, orderId` | Một DTO đơn kèm các dòng | Không làm nhân bội tổng tiền |
| R3 | Xem tồn kho và nhà cung cấp | `tenantId, depotId, sku` | Sản phẩm, số tồn, nhà cung cấp | Chỉ duyệt quan hệ phù hợp |
| W1 | Tạo đơn một dòng | Khóa nghiệp vụ, request ID, SKU, số lượng, giá | ID đơn, dòng và trạng thái | Retry cùng request không tạo trùng |
| W2 | Chuyển trạng thái đơn | `tenantId, orderId, trạng thái hiện tại` | Trạng thái mới hoặc từ chối | Không làm thay đổi đơn ngoài quyền |
| A1 | Top SKU theo doanh thu | `tenantId, from, to, topN` | SKU, số lượng, tổng tiền | Chỉ tính đơn `PAID` trong kỳ |
| A2 | Tổng tiền từng đơn | Tenant, khoảng ngày | Order, tổng tiền | Không đếm nhân khi join |
| P1 | Đường ít chặng | Tenant, kho xuất/đích, maxDepth | Danh sách kho, số chặng | Không đi xuyên tenant |
| P2 | Đường ít phút nhất | Tenant, kho xuất/đích, maxDepth | Path, tổng phút | Trọng số khác số chặng |

**Phạm vi đa tenant:** `tenantId` trong mọi query phải đến từ **định danh đã được xác thực và kiểm tra quyền**, không tin một tham số client tự khai. Các query ví dụ có filter tenant, nhưng một query có filter không thay thế mọi chính sách RBAC/authorization.

### 2.1. Tiêu chí phi chức năng của bài lab

- Mỗi truy vấn đọc trả đúng số bản ghi cho bộ seed, không thực hiện `MATCH (n) RETURN n` để ứng dụng lọc sau.
- Trang danh sách có `LIMIT` được ứng dụng kiểm soát và thứ tự ổn định.
- Các bản ghi sử dụng **khóa nghiệp vụ**, không dùng `id(node)` hoặc `elementId` như khóa public của API.
- Truy vấn ghi theo `MERGE`/constraint và **managed transaction** có điều kiện kiểm tra dữ liệu đầu vào.
- Truy vấn thống kê không gom toàn bộ graph thành `List` Java.
- Query tìm đường giới hạn chiều sâu khi dùng Cypher variable-length pattern; biết khi nào chuyển sang GDS.
- Có ít nhất một test cho tenant khác, một test ID không tồn tại và một test retry cùng request.

## 3. Mô hình property graph cho đồ án

### 3.1. Node và relationship

```text
(:CapClient {tenantId, clientId, name})
       |
    CAP_PLACED
       v
(:CapOrder {tenantId, orderId, clientId, requestId?, createdAt, status})
       |
    CAP_HAS_LINE
       v
(:CapLine {tenantId, lineId, orderId, sku, quantity, unitPrice})
       |
    CAP_OF_ITEM
       v
(:CapItem {tenantId, sku, title})
       ^
       | CAP_OFFERS
(:CapVendor {tenantId, vendorId, name})

(:CapDepot {tenantId, depotId, city})
    |  \ 
    |   \ CAP_ROUTE_TO {travelMinutes}
    |    ----------------------------> (:CapDepot)
    |
    +--[CAP_STOCKS {available}]--> (:CapItem)
```

| Label | Khóa duy nhất trong tenant | Các thuộc tính chính | Ý nghĩa |
| --- | --- | --- | --- |
| `CapClient` | `(tenantId, clientId)` | `name` | Khách đặt đơn |
| `CapVendor` | `(tenantId, vendorId)` | `name` | Nhà cung cấp sản phẩm |
| `CapItem` | `(tenantId, sku)` | `title` | Danh mục hàng |
| `CapDepot` | `(tenantId, depotId)` | `city` | Kho và điểm trung chuyển |
| `CapOrder` | `(tenantId, orderId)` | `clientId, status, createdAt, requestId?` | Đơn hàng |
| `CapLine` | `(tenantId, lineId)` | `orderId, sku, quantity, unitPrice` | Dòng hàng, giá tại thời điểm mua |

**Vì sao `CapLine` là node?** Một đơn có thể có nhiều dòng, thậm chí nhiều dòng cùng SKU theo lô/giá. Nếu dùng duy nhất quan hệ trực tiếp `Order-[:CONTAINS]->Item` và `MERGE` theo hai đầu, có thể vô tình gộp hai dòng hợp lệ. Node `CapLine` cho phép khóa riêng, thuộc tính định lượng rõ và đơn giản hóa kiểm thử.

**Vì sao `clientId` có trên cả `CapOrder` và relationship `CAP_PLACED`?** Đây là một thuộc tính phục vụ truy vấn danh sách đơn bằng index. Đổi lại, mọi thao tác ghi phải duy trì hai biểu diễn nhất quán. Trong hệ thống thật có thể chọn chỉ relationship hoặc tạo read model riêng tùy nhu cầu.

### 3.2. Ngữ nghĩa dữ liệu

- `quantity` là số nguyên dương.
- `unitPrice` là đơn vị tiền **VND** dạng số nguyên không âm; tránh dùng `float` cho dữ liệu tiền nhạy cảm.
- `available` là số tồn minh họa trên relationship `CAP_STOCKS`, **chưa có cơ chế giữ chỗ đồng thời** trong bài nền tảng.
- `travelMinutes` là số nguyên dương dùng làm trọng số đường đi; quan hệ `CAP_ROUTE_TO` **có hướng**.
- `status` của đơn thuộc một tập hữu hạn như `NEW`, `PAID`, `CANCELLED`.
- `createdAt` dùng kiểu `DATETIME` (có timezone).
- `tenantId` phải nhất quán trên hai đầu relationship nghiệp vụ; Neo4j không tự kiểm tra quy tắc xuyên nhiều node bằng uniqueness constraint đơn giản.

## 4. Chuẩn bị môi trường và cách thực hiện

Có thể dùng Neo4j Browser, Cypher Shell hoặc Java Driver. Để an toàn:

1. Dùng **database lab riêng**, tránh chạy chung với dữ liệu production.
2. Tạo constraint/index trước khi seed để dễ phát hiện trùng khóa.
3. Thực thi **từng khối Cypher theo thứ tự**. Những mẫu `UNWIND`/`MERGE` được thiết kế để chạy lại mà không tự tạo trùng node/relationship cùng cặp.
4. Đối chiếu số liệu **trước khi chạy thao tác W1 tạo đơn mới**, hoặc dùng dataset lab mới.
5. Nếu chạy trong Neo4j Browser, truyền tham số theo cú pháp Browser, ví dụ:

```cypher
:param tenantId => 't1'
:param clientId => 'c01'
:param limit => 20
```

`:param` là **lệnh của Browser**, không phải câu Cypher để gửi qua Java Driver; khi gọi từ Java dùng `Map<String,Object>`. Các lệnh bên dưới sử dụng tham số có dấu `$`, trừ script seed sử dụng hằng số cố định.

### Điều kiện dữ liệu và phiên bản

- Có quyền tạo constraint/index và đọc/ghi graph trong database lab.
- Một database Neo4j có Cypher tương thích; các ví dụ nền tảng không yêu cầu APOC/GDS.
- Có Java 17+ và Java Driver 6.x nếu làm mục tích hợp.
- Nên dùng một connection string `neo4j+s://...` cho dịch vụ bảo mật thực; địa chỉ local tự quản lý có thể dùng `bolt://localhost:7687` nếu phù hợp cấu hình và môi trường lab.

## 5. Khởi tạo constraints và indexes

### 5.1. Composite uniqueness constraints

Thực thi **sáu lệnh riêng**:

```cypher
CREATE CONSTRAINT cap_client_key IF NOT EXISTS
FOR (n:CapClient)
REQUIRE (n.tenantId, n.clientId) IS UNIQUE;
```

```cypher
CREATE CONSTRAINT cap_vendor_key IF NOT EXISTS
FOR (n:CapVendor)
REQUIRE (n.tenantId, n.vendorId) IS UNIQUE;
```

```cypher
CREATE CONSTRAINT cap_item_key IF NOT EXISTS
FOR (n:CapItem)
REQUIRE (n.tenantId, n.sku) IS UNIQUE;
```

```cypher
CREATE CONSTRAINT cap_depot_key IF NOT EXISTS
FOR (n:CapDepot)
REQUIRE (n.tenantId, n.depotId) IS UNIQUE;
```

```cypher
CREATE CONSTRAINT cap_order_key IF NOT EXISTS
FOR (n:CapOrder)
REQUIRE (n.tenantId, n.orderId) IS UNIQUE;
```

```cypher
CREATE CONSTRAINT cap_line_key IF NOT EXISTS
FOR (n:CapLine)
REQUIRE (n.tenantId, n.lineId) IS UNIQUE;
```

Những constraint này ngăn hai node trong cùng tenant có cùng khóa. **Uniqueness không bắt buộc mọi node phải có property**: nếu nghiệp vụ yêu cầu existence, đánh giá node key/existence constraint theo edition hoặc kiểm tra qua service/schema import.

### 5.2. Constraint cho idempotency key

Để hai request khác nhau không vô tình dùng lại `requestId` trong cùng tenant:

```cypher
CREATE CONSTRAINT cap_order_request_key IF NOT EXISTS
FOR (n:CapOrder)
REQUIRE (n.tenantId, n.requestId) IS UNIQUE;
```

Trong seed ban đầu, các đơn lịch sử không có `requestId`; uniqueness constraint không làm chúng thất bại chỉ vì property vắng mặt. Những đơn tạo bằng API W1 sẽ có `requestId` riêng.

### 5.3. Index theo đường truy cập

```cypher
CREATE RANGE INDEX cap_order_client_feed IF NOT EXISTS
FOR (o:CapOrder)
ON (o.tenantId, o.clientId, o.createdAt, o.orderId);
```

```cypher
CREATE RANGE INDEX cap_order_paid_period IF NOT EXISTS
FOR (o:CapOrder)
ON (o.tenantId, o.status, o.createdAt);
```

Index feed giúp cân nhắc kế hoạch tìm đơn của một khách theo thời gian; index báo cáo giúp lọc đơn `PAID` theo tenant và khoảng thời gian. **Không bảo đảm planner luôn dùng index hay tránh mọi phép sort**; cần `EXPLAIN`/`PROFILE` trên dữ liệu có quy mô phù hợp.

Kiểm tra:

```cypher
SHOW CONSTRAINTS;
```

```cypher
SHOW INDEXES;
```

## 6. Seed dữ liệu mẫu — node

### 6.1. Khách hàng

```cypher
UNWIND [
  {tenantId: 't1', clientId: 'c01', name: 'Linh'},
  {tenantId: 't1', clientId: 'c02', name: 'Minh'},
  {tenantId: 't2', clientId: 'c01', name: 'Khách T2'}
] AS r
MERGE (c:CapClient {
  tenantId: r.tenantId,
  clientId: r.clientId
})
SET c.name = r.name;
```

### 6.2. Nhà cung cấp

```cypher
UNWIND [
  {tenantId: 't1', vendorId: 'v01', name: 'Nhà cung cấp Bắc'},
  {tenantId: 't1', vendorId: 'v02', name: 'Nhà cung cấp Nam'},
  {tenantId: 't2', vendorId: 'v01', name: 'Nhà cung cấp T2'}
] AS r
MERGE (v:CapVendor {
  tenantId: r.tenantId,
  vendorId: r.vendorId
})
SET v.name = r.name;
```

### 6.3. Sản phẩm

```cypher
UNWIND [
  {tenantId: 't1', sku: 'skuA', title: 'Bàn phím'},
  {tenantId: 't1', sku: 'skuB', title: 'Chuột'},
  {tenantId: 't1', sku: 'skuC', title: 'Màn hình'},
  {tenantId: 't2', sku: 'skuA', title: 'Hàng riêng của T2'}
] AS r
MERGE (p:CapItem {
  tenantId: r.tenantId,
  sku: r.sku
})
SET p.title = r.title;
```

### 6.4. Kho trung chuyển

```cypher
UNWIND [
  {tenantId: 't1', depotId: 'HN', city: 'Hà Nội'},
  {tenantId: 't1', depotId: 'DN', city: 'Đà Nẵng'},
  {tenantId: 't1', depotId: 'SG', city: 'TP.HCM'},
  {tenantId: 't1', depotId: 'CT', city: 'Cần Thơ'},
  {tenantId: 't2', depotId: 'HN', city: 'Kho riêng T2'}
] AS r
MERGE (d:CapDepot {
  tenantId: r.tenantId,
  depotId: r.depotId
})
SET d.city = r.city;
```

Các ID `HN`/`DN`/`SG`/`CT` là **ký hiệu kho hư cấu trong dataset**, không đại diện tọa độ hoặc thời gian vận chuyển thật. Đặc biệt, `travelMinutes` ở phần sau chỉ là trọng số giả định cho bài toán thuật toán, không phải ước tính giao thông thực tế.

## 7. Seed dữ liệu mẫu — relationship cung ứng và tuyến kho

### 7.1. Nhà cung cấp bán sản phẩm

```cypher
UNWIND [
  {tenantId: 't1', vendorId: 'v01', sku: 'skuA'},
  {tenantId: 't1', vendorId: 'v01', sku: 'skuB'},
  {tenantId: 't1', vendorId: 'v02', sku: 'skuC'},
  {tenantId: 't2', vendorId: 'v01', sku: 'skuA'}
] AS r
MATCH (v:CapVendor {
  tenantId: r.tenantId,
  vendorId: r.vendorId
})
MATCH (p:CapItem {tenantId: r.tenantId, sku: r.sku})
MERGE (v)-[:CAP_OFFERS]->(p);
```

### 7.2. Tồn kho theo sản phẩm

```cypher
UNWIND [
  {depotId: 'HN', sku: 'skuA', available: 120},
  {depotId: 'DN', sku: 'skuA', available: 60},
  {depotId: 'SG', sku: 'skuB', available: 150},
  {depotId: 'CT', sku: 'skuC', available: 40}
] AS r
MATCH (d:CapDepot {tenantId: 't1', depotId: r.depotId})
MATCH (p:CapItem {tenantId: 't1', sku: r.sku})
MERGE (d)-[stock:CAP_STOCKS]->(p)
SET stock.available = r.available;
```

Khi chạy seed lần nữa, `SET stock.available` **đặt lại số tồn về giá trị mẫu**. Đây là hành vi có chủ đích trong lab, **không thích hợp cho quy trình seed production** đang có thao tác tồn kho thực.

### 7.3. Mạng tuyến vận chuyển có hướng

```cypher
UNWIND [
  {from: 'HN', to: 'DN', travelMinutes: 60},
  {from: 'HN', to: 'SG', travelMinutes: 150},
  {from: 'DN', to: 'SG', travelMinutes: 60},
  {from: 'DN', to: 'CT', travelMinutes: 170},
  {from: 'SG', to: 'CT', travelMinutes: 45}
] AS r
MATCH (a:CapDepot {tenantId: 't1', depotId: r.from})
MATCH (b:CapDepot {tenantId: 't1', depotId: r.to})
MERGE (a)-[route:CAP_ROUTE_TO]->(b)
SET route.travelMinutes = r.travelMinutes;
```

Sơ đồ mạng:

```text
HN ----60----> DN -----60----> SG -----45----> CT
 |              |                              ^
 |              +-------------170--------------+
 |
 +-------------------150-----> SG
```

Dữ liệu cố ý làm cho đường **ít chặng nhất** và đường có **tổng phút ít nhất** không nhất thiết trùng nhau. Quan hệ có hướng: `HN→DN` không tự ngụ ý có `DN→HN`.

## 8. Seed dữ liệu mẫu — đơn hàng và dòng hàng

### 8.1. Đơn hàng, khách đặt và thời điểm

```cypher
UNWIND [
  {tenantId: 't1', clientId: 'c01', orderId: 'o101',
   at: '2026-11-01T09:00:00+07:00', status: 'PAID'},
  {tenantId: 't1', clientId: 'c01', orderId: 'o102',
   at: '2026-11-02T09:00:00+07:00', status: 'PAID'},
  {tenantId: 't1', clientId: 'c02', orderId: 'o103',
   at: '2026-11-03T09:00:00+07:00', status: 'NEW'},
  {tenantId: 't2', clientId: 'c01', orderId: 'o201',
   at: '2026-11-02T09:00:00+07:00', status: 'PAID'}
] AS r
MATCH (c:CapClient {
  tenantId: r.tenantId,
  clientId: r.clientId
})
MERGE (o:CapOrder {tenantId: r.tenantId, orderId: r.orderId})
SET o.clientId = r.clientId,
    o.createdAt = datetime(r.at),
    o.status = r.status
MERGE (c)-[:CAP_PLACED]->(o);
```

### 8.2. Dòng hàng

```cypher
UNWIND [
  {tenantId: 't1', orderId: 'o101', lineId: 'l101a',
   sku: 'skuA', quantity: 2, unitPrice: 100000},
  {tenantId: 't1', orderId: 'o101', lineId: 'l101b',
   sku: 'skuB', quantity: 1, unitPrice: 50000},
  {tenantId: 't1', orderId: 'o102', lineId: 'l102a',
   sku: 'skuA', quantity: 1, unitPrice: 100000},
  {tenantId: 't1', orderId: 'o103', lineId: 'l103a',
   sku: 'skuC', quantity: 3, unitPrice: 200000},
  {tenantId: 't2', orderId: 'o201', lineId: 'l201a',
   sku: 'skuA', quantity: 4, unitPrice: 999000}
] AS r
MATCH (o:CapOrder {tenantId: r.tenantId, orderId: r.orderId})
MATCH (p:CapItem {tenantId: r.tenantId, sku: r.sku})
MERGE (li:CapLine {tenantId: r.tenantId, lineId: r.lineId})
SET li.orderId = r.orderId,
    li.sku = r.sku,
    li.quantity = r.quantity,
    li.unitPrice = r.unitPrice
MERGE (o)-[:CAP_HAS_LINE]->(li)
MERGE (li)-[:CAP_OF_ITEM]->(p);
```

**Ghi chú:** các lệnh seed có `SET` để tái tạo một trạng thái demo xác định. Chỉ chạy trên môi trường lab được phép làm mới dữ liệu; seed không phải cơ chế giữ nguyên thay đổi nghiệp vụ sau các bài test ghi.

### 8.3. Kết quả nền tảng dự kiến

Trên database lab sạch chỉ có các label `Cap*`:

| Thành phần | Tenant t1 | Tenant t2 |
| --- | ---: | ---: |
| `CapClient` | 2 | 1 |
| `CapVendor` | 2 | 1 |
| `CapItem` | 3 | 1 |
| `CapDepot` | 4 | 1 |
| `CapOrder` | 3 | 1 |
| `CapLine` | 4 | 1 |
| Tổng node theo tenant | 18 | 6 |

Các quan hệ `CAP_PLACED` trong t1 là 3, `CAP_HAS_LINE` là 4, `CAP_OF_ITEM` là 4, `CAP_OFFERS` là 3, `CAP_STOCKS` là 4 và `CAP_ROUTE_TO` là 5.

Kiểm tra đếm theo label/tenant:

```cypher
MATCH (n)
WHERE n:CapClient OR n:CapVendor OR n:CapItem
   OR n:CapDepot OR n:CapOrder OR n:CapLine
RETURN n.tenantId AS tenantId, count(*) AS nodeCount
ORDER BY tenantId;
```

**Dự kiến:** `t1 = 18` và `t2 = 6` nếu chưa chạy thao tác tạo đơn mới và không có dữ liệu lab từ lần trước. Sau bài W1, số node t1 tăng; khi đó đối soát theo **ID seed cụ thể**, không cứng nhắc dựa trên tổng.

## 9. R1 — Đọc danh sách đơn của khách hàng

Yêu cầu: lấy tối đa 20 đơn của khách `c01` trong tenant `t1`, thứ tự mới nhất trước.

```cypher
MATCH (o:CapOrder {
  tenantId: $tenantId,
  clientId: $clientId
})
RETURN
  o.orderId AS orderId,
  o.createdAt AS createdAt,
  o.status AS status
ORDER BY createdAt DESC, orderId DESC
LIMIT $limit;
```

Tham số:

```json
{
  "tenantId": "t1",
  "clientId": "c01",
  "limit": 20
}
```

Kết quả trên seed:

| orderId | status | Vị trí |
| --- | --- | --- |
| `o102` | `PAID` | Mới hơn |
| `o101` | `PAID` | Cũ hơn |

Không được xuất `o103` (thuộc c02) hay `o201` (thuộc t2).

### Tại sao query này tốt hơn tải toàn graph?

- Có **điểm neo** là tenant và client.
- Chỉ lấy ba property cần hiển thị.
- Có `ORDER BY` ổn định với `orderId` làm tie-breaker.
- Giới hạn đầu ra ở Neo4j, không gom mọi node về Java.
- Composite index `cap_order_client_feed` có thể hỗ trợ lọc và thứ tự; xác minh bằng query plan.

**Trong API**, `$clientId` phải được so với danh tính/ủy quyền người dùng hiện tại. Không cho phép khách tùy ý thay `clientId` trên URL để truy xuất đơn của người khác cùng tenant.

## 10. R2 — Chi tiết một đơn và tổng tiền

Yêu cầu: xem đơn `o101` của khách `c01`, bao gồm các SKU, số lượng và giá gốc trong từng dòng.

```cypher
MATCH (c:CapClient {
  tenantId: $tenantId,
  clientId: $clientId
})-[:CAP_PLACED]->(o:CapOrder {
  tenantId: $tenantId,
  orderId: $orderId
})
OPTIONAL MATCH (o)-[:CAP_HAS_LINE]->(li:CapLine)
                 -[:CAP_OF_ITEM]->(p:CapItem {tenantId: $tenantId})
WHERE li.tenantId = $tenantId
WITH o, li, p
ORDER BY li.lineId
RETURN
  o.orderId AS orderId,
  o.status AS status,
  collect(
    CASE WHEN li IS NULL THEN NULL ELSE {
      lineId: li.lineId,
      sku: p.sku,
      title: p.title,
      quantity: li.quantity,
      unitPrice: li.unitPrice
    } END
  ) AS items,
  sum(
    CASE WHEN li IS NULL THEN 0
         ELSE li.quantity * li.unitPrice END
  ) AS totalVnd;
```

Tham số:

```json
{
  "tenantId": "t1",
  "clientId": "c01",
  "orderId": "o101"
}
```

**Dự kiến:**
- `orderId = "o101"`, `status = "PAID"`.
- Hai dòng: `skuA × 2 × 100000` và `skuB × 1 × 50000`.
- `totalVnd = 250000`.

`OPTIONAL MATCH` giúp trả đơn ngay cả khi không có dòng hàng. `collect` bỏ qua `NULL` nên trường `items` thường là list rỗng khi không có dòng. Đây là tập dữ liệu nhỏ; với đơn hàng hàng chục nghìn dòng, nên tạo **API phân trang dòng hàng** thay vì một `collect` quá lớn.

**Lưu ý tính đúng:** điều kiện tenant trên sản phẩm và dòng hàng là phòng vệ bổ sung; một graph chứa relationship nối sai tenant vẫn cần kiểm tra toàn vẹn riêng. Nếu `CAP_PLACED` thiếu, query trả 0 dòng dù `CapOrder` có thể tồn tại; đó là cách **không cho qua kiểm tra ownership**.

### 10.1. Kiểm thử âm tính

Thay `clientId = "c02"` nhưng giữ `orderId = "o101"`. Query phải trả **0 dòng**. Thay `tenantId = "t2"` với order ID của t1 cũng phải trả 0 dòng.

Không phân biệt được “đơn không tồn tại” và “không có quyền” bằng việc chỉ thấy một query trả 0 dòng. API có thể trả `404` để không tiết lộ sự tồn tại của đơn cho người không có quyền, tùy chính sách bảo mật.

## 11. R3 — Sản phẩm có sẵn ở một kho và nhà cung cấp

Query tồn kho ở kho `HN`:

```cypher
MATCH (d:CapDepot {
  tenantId: $tenantId,
  depotId: $depotId
})-[stock:CAP_STOCKS]->(p:CapItem {tenantId: $tenantId})
WHERE stock.available > 0
RETURN p.sku AS sku,
       p.title AS title,
       stock.available AS available
ORDER BY sku
LIMIT $limit;
```

Tham số ví dụ `{tenantId:'t1', depotId:'HN', limit:20}` dự kiến trả `skuA`, số tồn `120`.

Tìm các nhà cung cấp của SKU:

```cypher
MATCH (p:CapItem {tenantId: $tenantId, sku: $sku})
MATCH (v:CapVendor {tenantId: $tenantId})-[:CAP_OFFERS]->(p)
RETURN v.vendorId AS vendorId, v.name AS vendorName
ORDER BY vendorId
LIMIT $limit;
```

Với `t1/skuA`, dự kiến chỉ có `v01`. Với `t2/skuA`, tuy SKU trùng tên, chỉ được trả vendor t2 tương ứng.

**Phân biệt vấn đề nghiệp vụ:** `stock.available > 0` chỉ cho thấy snapshot tồn kho; không tự giữ chỗ hàng cho một đơn mới. Nếu nhiều client đồng thời mua hàng, cần thêm **transaction ghi tồn kho an toàn trước race condition**, không xem câu read trên là xác nhận đặt hàng.

## 12. Phân trang đúng đối tượng: trang đơn trước, dòng sau

Một lỗi thiết kế phổ biến:

```cypher
// SAI cho mục tiêu "lấy 20 đơn":
MATCH (o:CapOrder)-[:CAP_HAS_LINE]->(li:CapLine)
RETURN o.orderId AS orderId, li.lineId AS lineId
LIMIT 20;
```

`LIMIT 20` này giới hạn **dòng kết quả sau mở rộng**, không phải 20 đơn. Một đơn có 25 dòng có thể chiếm cả trang và làm mất các đơn khác.

Sửa bằng cách chọn đơn trước:

```cypher
MATCH (o:CapOrder {
  tenantId: $tenantId,
  clientId: $clientId
})
WITH o
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT $limit
OPTIONAL MATCH (o)-[:CAP_HAS_LINE]->(li:CapLine)
WITH o, li
ORDER BY o.createdAt DESC, o.orderId DESC, li.lineId
RETURN o.orderId AS orderId,
       o.status AS status,
       o.createdAt AS createdAt,
       collect(
         CASE WHEN li IS NULL THEN NULL ELSE {
           lineId: li.lineId,
           sku: li.sku,
           quantity: li.quantity
         } END
       ) AS items
ORDER BY createdAt DESC, orderId DESC;
```

Trong truy vấn trên, `WITH o ... LIMIT` chọn tối đa `$limit` **order nodes** trước. Lưu ý: `LIMIT` vẫn **không giới hạn số dòng của từng đơn**; nếu rất nhiều dòng, tách API dòng hàng.

### 12.1. Keyset pagination cho tập đơn lớn

Với nhiều triệu đơn, `SKIP` sâu có thể tốn chi phí bỏ qua nhiều hàng và chịu thay đổi khi có insert/delete. Dùng cursor thời điểm + khóa:

```cypher
MATCH (o:CapOrder {
  tenantId: $tenantId,
  clientId: $clientId
})
WHERE o.createdAt < datetime($cursorAt)
   OR (
       o.createdAt = datetime($cursorAt)
       AND o.orderId < $cursorOrderId
   )
RETURN o.orderId AS orderId,
       o.createdAt AS createdAt,
       o.status AS status
ORDER BY createdAt DESC, orderId DESC
LIMIT $limit;
```

Đây là **query trang tiếp theo**; trang đầu bỏ điều kiện cursor. Keyset cần thứ tự ổn định và có tie-breaker duy nhất; nó không cung cấp snapshot toàn bộ các request nếu dữ liệu thay đổi đồng thời.

## 13. W1 — Ghi đơn hàng idempotent trong một transaction

### 13.1. Yêu cầu ghi

Tạo đơn `o900` cho khách `c01` trong tenant `t1`, một dòng `skuA`, số lượng `2`, đơn giá `100000`, trạng thái `NEW`. Nếu API được gọi lại với **cùng requestId và payload**, kết quả phải tương đương, không phát sinh thêm đơn/dòng/quan hệ.

Input ví dụ:

```json
{
  "tenantId": "t1",
  "clientId": "c01",
  "orderId": "o900",
  "requestId": "req-900",
  "createdAt": "2026-11-25T10:00:00+07:00",
  "lineId": "l900a",
  "sku": "skuA",
  "quantity": 2,
  "unitPrice": 100000
}
```

Trong triển khai thật:
- `tenantId` và `clientId` được xác thực/ủy quyền.
- `quantity > 0`, `unitPrice >= 0`, mọi ID hợp lệ và độ dài có giới hạn.
- `requestId` có phạm vi tenant và phải được quản lý theo nguyên tắc idempotency.
- Giá sản phẩm có thể cần tra từ bảng giá đã được phê duyệt, **không tin `unitPrice` do browser đưa lên** trong nghiệp vụ thanh toán.

### 13.2. Truy vấn dùng bên trong managed transaction

```cypher
MATCH (c:CapClient {
  tenantId: $tenantId,
  clientId: $clientId
})
MATCH (p:CapItem {
  tenantId: $tenantId,
  sku: $sku
})
MERGE (o:CapOrder {
  tenantId: $tenantId,
  orderId: $orderId
})
ON CREATE SET
  o.clientId = $clientId,
  o.requestId = $requestId,
  o.createdAt = datetime($createdAt),
  o.status = 'NEW'
WITH c, p, o
WHERE o.clientId = $clientId
  AND o.requestId = $requestId
MERGE (c)-[:CAP_PLACED]->(o)
MERGE (li:CapLine {
  tenantId: $tenantId,
  lineId: $lineId
})
ON CREATE SET
  li.orderId = $orderId,
  li.sku = $sku,
  li.quantity = $quantity,
  li.unitPrice = $unitPrice
WITH o, p, li
WHERE li.orderId = $orderId
  AND li.sku = $sku
  AND li.quantity = $quantity
  AND li.unitPrice = $unitPrice
MERGE (o)-[:CAP_HAS_LINE]->(li)
MERGE (li)-[:CAP_OF_ITEM]->(p)
RETURN o.orderId AS orderId,
       o.status AS status,
       li.lineId AS lineId;
```

**Quan trọng:** đoạn trên được thiết kế để chạy trong **managed transaction của ứng dụng**, rồi ứng dụng **bắt buộc phải yêu cầu đúng một record**. Nếu client/SKU không tồn tại, orderId có requestId khác hoặc lineId bị tái sử dụng với payload khác, query có thể trả **0 dòng**. Tầng Java phải coi đó là lỗi và ném exception **trước commit** để rollback mọi thao tác trung gian.

Chạy riêng query như một câu auto-commit trong Browser mà không kiểm tra số record có thể khiến **một phần thay đổi đã thực hiện vẫn được commit** khi query lọc hết dòng ở cuối. Vì vậy bài W1 nhấn mạnh **query + transaction callback + kiểm tra kết quả là một đơn vị thiết kế**.

### 13.3. Vì sao `MERGE` không thay thế constraint?

Một lời gọi `MERGE` theo khóa nghiệp vụ giúp idempotency khi retry, nhưng hai writer đồng thời có thể tạo tình huống cạnh tranh. Composite uniqueness constraints ở mục 5 mới tạo chốt bảo vệ dữ liệu khỏi trùng khóa; business code vẫn phải bắt lỗi phù hợp, không coi mọi constraint violation là transient.

**Không có “exactly once HTTP delivery” miễn phí.** Lỗi mạng có thể xuất hiện sau khi DB đã commit nhưng trước khi client nhận ACK. Request ID, unique constraint và kiểm tra trạng thái là nền tảng để retry an toàn. Callback `executeWrite` có thể được driver gọi lại vì transient error, nên **không gửi email, tạo hóa đơn ở hệ thống ngoài hoặc trừ tiền trực tiếp bên trong callback**.

## 14. W2 — Chuyển trạng thái có điều kiện

Đối với đơn `NEW`, bài tập là chuyển sang `PAID` theo đúng quyền và quy tắc nghiệp vụ.

```cypher
MATCH (o:CapOrder {
  tenantId: $tenantId,
  orderId: $orderId
})
WHERE o.clientId = $clientId
  AND o.status = 'NEW'
SET o.status = 'PAID',
    o.paidAt = datetime($paidAt)
RETURN o.orderId AS orderId,
       o.status AS status,
       o.paidAt AS paidAt;
```

Tầng ứng dụng phải kiểm tra **đúng một record**. Nếu trả 0 record, có thể không có đơn, sai owner hoặc trạng thái không cho phép chuyển. Trong service production, cần:
- Kiểm tra authorization từ identity và quyền chuyển trạng thái.
- Xác minh sự kiện thanh toán có thật và chưa được áp dụng trước đó.
- Có **payment/event ID riêng với unique constraint** để chống lặp.
- Kiểm tra đồng thời khi hai request chuyển trạng thái cạnh tranh; chỉ dùng `WHERE status = 'NEW'` trong query không tự chứng minh một workflow thanh toán đạt exactly-once business effect.
- Đặt side effect bên ngoài Neo4j vào outbox/consumer idempotent nếu có tích hợp hệ thống khác.

Bản đồ trạng thái tối thiểu:

```text
NEW -------PAID
  \
   \------CANCELLED

PAID không tự chuyển lại NEW.
```

**Không chạy W2 trước các bài test thống kê có expected baseline**; chuyển trạng thái `o103` từ NEW sang PAID sẽ làm doanh thu kỳ thay đổi.

## 15. Java Driver 6.x — đọc và ghi trong session đúng vòng đời

### 15.1. Phụ thuộc và kết nối

Sử dụng dependency `org.neo4j.driver:neo4j-java-driver` phiên bản **6.x tương thích với Neo4j server và stack Spring** đang dùng; tránh hardcode version “mới nhất” không được kiểm chứng trong dự án thực.

```java
import java.time.ZonedDateTime;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Record;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

record OrderSummary(
    String orderId,
    ZonedDateTime createdAt,
    String status
) {}

record OrderWriteResult(
    String orderId,
    String status,
    String lineId
) {}
```

Ví dụ khởi tạo ở lớp bootstrap/CLI:

```java
String uri = System.getenv("NEO4J_URI");
String username = System.getenv("NEO4J_USER");
String password = System.getenv("NEO4J_PASSWORD");

try (Driver driver = GraphDatabase.driver(
        uri, AuthTokens.basic(username, password))) {
    driver.verifyConnectivity();
    // Gọi các hàm truy vấn bên dưới.
}
```

Trong service Spring, `Driver` nên là một **bean dùng chung** cho ứng dụng, không tạo/đóng mỗi HTTP request. Trong cluster dùng routing URI phù hợp (thường `neo4j+s://`), chọn database bằng `SessionConfig.forDatabase(...)`.

### 15.2. API đọc danh sách đơn

```java
static List<OrderSummary> findOrders(
        Driver driver, String tenantId,
        String clientId, int requestedLimit) {

    int limit = Math.max(1, Math.min(requestedLimit, 50));

    String query = """
        MATCH (o:CapOrder {
          tenantId: $tenantId, clientId: $clientId
        })
        RETURN o.orderId AS orderId,
               o.createdAt AS createdAt,
               o.status AS status
        ORDER BY createdAt DESC, orderId DESC
        LIMIT $limit
        """;

    try (Session session = driver.session(
            SessionConfig.forDatabase("neo4j"))) {
        return session.executeRead(tx ->
            tx.run(query, Map.of(
                "tenantId", tenantId,
                "clientId", clientId,
                "limit", limit
            )).list(r -> new OrderSummary(
                r.get("orderId").asString(),
                r.get("createdAt").asZonedDateTime(),
                r.get("status").asString()
            ))
        );
    }
}
```

Ở đây `list()` an toàn vì có `LIMIT` nhỏ. Với export hàng triệu bản ghi, phân trang/stream theo batch; không tải toàn bộ graph vào Java heap.

### 15.3. API tạo đơn và kiểm tra record trước commit

```java
static OrderWriteResult createSingleLineOrder(
        Driver driver,
        String tenantId,
        String clientId,
        String orderId,
        String requestId,
        String lineId,
        String sku,
        long quantity,
        long unitPrice,
        String createdAt) {

    if (quantity <= 0 || unitPrice < 0) {
        throw new IllegalArgumentException(
            "Invalid quantity or unitPrice");
    }

    String query = """
        MATCH (c:CapClient {
          tenantId: $tenantId, clientId: $clientId
        })
        MATCH (p:CapItem {
          tenantId: $tenantId, sku: $sku
        })
        MERGE (o:CapOrder {
          tenantId: $tenantId, orderId: $orderId
        })
        ON CREATE SET
          o.clientId = $clientId,
          o.requestId = $requestId,
          o.createdAt = datetime($createdAt),
          o.status = 'NEW'
        WITH c, p, o
        WHERE o.clientId = $clientId
          AND o.requestId = $requestId
        MERGE (c)-[:CAP_PLACED]->(o)
        MERGE (li:CapLine {
          tenantId: $tenantId, lineId: $lineId
        })
        ON CREATE SET
          li.orderId = $orderId,
          li.sku = $sku,
          li.quantity = $quantity,
          li.unitPrice = $unitPrice
        WITH o, p, li
        WHERE li.orderId = $orderId
          AND li.sku = $sku
          AND li.quantity = $quantity
          AND li.unitPrice = $unitPrice
        MERGE (o)-[:CAP_HAS_LINE]->(li)
        MERGE (li)-[:CAP_OF_ITEM]->(p)
        RETURN o.orderId AS orderId,
               o.status AS status,
               li.lineId AS lineId
        """;

    try (Session session = driver.session(
            SessionConfig.forDatabase("neo4j"))) {

        return session.executeWrite(tx -> {
            Record r = tx.run(query, Map.of(
                "tenantId", tenantId,
                "clientId", clientId,
                "orderId", orderId,
                "requestId", requestId,
                "lineId", lineId,
                "sku", sku,
                "quantity", quantity,
                "unitPrice", unitPrice,
                "createdAt", createdAt
            )).single();  // 0 hoặc >1 record -> exception -> rollback.

            return new OrderWriteResult(
                r.get("orderId").asString(),
                r.get("status").asString(),
                r.get("lineId").asString()
            );
        });
    }
}
```

Đặc tính:
- Cùng một transaction ghi order, line và hai relationship.
- `.single()` bắt buộc đúng một record; nếu không có record, callback ném exception và driver **rollback** thay vì commit phần giữa.
- `executeWrite` có thể tự retry transient failures. Input và request ID phải giữ ổn định khi callback bị gọi lại.
- Unique constraints chặn trùng ID. Phần ứng dụng phải bắt riêng lỗi xung đột idempotency/business và trả HTTP `409`/`422` khi phù hợp, không lặp vô hạn.
- Không đặt side effect ngoài database trong callback.

**Ví dụ chỉ tạo một dòng**. Mở rộng nhiều dòng có thể dùng `UNWIND $lines` trong cùng transaction nhưng phải **kiểm tra mọi SKU và số dòng hợp lệ**; nếu một SKU không tồn tại, cần rollback *toàn bộ order*. Không trả “thành công một phần” trừ khi đó là yêu cầu nghiệp vụ có chủ đích.

### 15.4. Ánh xạ lỗi và timeout

| Tình huống | Hướng trả API |
| --- | --- |
| Thiếu client/SKU hoặc sai owner | Không tạo đơn; lỗi nghiệp vụ/404/403 theo policy |
| orderId gắn requestId khác | Conflict; không sửa đơn cũ |
| requestId tái sử dụng cho orderId khác | Unique constraint violation → conflict |
| Database tạm thời unavailable | Retry hữu hạn theo driver/gateway budget |
| Ghi có kết quả commit không rõ vì mất ACK | Đối chiếu bằng requestId/orderId; không tự nhân đôi thanh toán |
| DBMS trả lỗi syntax/permission | Sửa code/role; không retry như lỗi transient |

## 16. A1 — Tổng hợp doanh thu theo sản phẩm và thời gian

Yêu cầu: trong tenant `t1`, từ ngày 1 tới trước ngày 4 tháng 11/2026, lấy top SKU có **đơn đã thanh toán** theo tổng số tiền.

```cypher
MATCH (o:CapOrder {
  tenantId: $tenantId,
  status: 'PAID'
})
WHERE o.createdAt >= datetime($from)
  AND o.createdAt < datetime($to)
MATCH (o)-[:CAP_HAS_LINE]->(li:CapLine)
         -[:CAP_OF_ITEM]->(p:CapItem {tenantId: $tenantId})
WHERE li.tenantId = $tenantId
WITH p.sku AS sku,
     p.title AS title,
     sum(li.quantity) AS unitsSold,
     sum(li.quantity * li.unitPrice) AS revenueVnd
RETURN sku, title, unitsSold, revenueVnd
ORDER BY revenueVnd DESC, sku
LIMIT $topN;
```

Tham số:

```json
{
  "tenantId": "t1",
  "from": "2026-11-01T00:00:00+07:00",
  "to": "2026-11-04T00:00:00+07:00",
  "topN": 10
}
```

**Đáp án trên seed chưa có W2:**

| sku | unitsSold | revenueVnd |
| --- | ---: | ---: |
| `skuA` | 3 | 300000 |
| `skuB` | 1 | 50000 |

`skuC` thuộc đơn `NEW` nên không được tính. `skuA` của t2 cũng không được tính vì khác tenant. Tổng doanh thu các đơn PAID của t1 là **350000 VND**, tương ứng `o101 = 250000` và `o102 = 100000`.

### 16.1. Những điểm dễ sai khi tổng hợp

- **Không dùng giá hiện tại của `CapItem`** thay cho `CapLine.unitPrice` tại thời điểm mua.
- `LIMIT 10` sau `ORDER BY revenue` không có nghĩa engine chỉ đọc mười dòng hàng; nó phải tổng hợp các dòng phù hợp trước.
- Tránh join thêm nhiều nhánh một-nhiều (vendor, depot, reviews) trong cùng phép `sum` vì dễ **nhân bội row**.
- Với tiền tệ lớn, số nguyên 64-bit có thể overflow; production cần chính sách numeric/exact amount rõ ràng.
- Với dashboard tải lớn, xem xét pre-aggregation/read model định kỳ, đối soát số liệu gốc và độ trễ.

## 17. A2 — Tổng tiền theo đơn và tổng số đơn

Truy vấn tổng tiền đơn đã thanh toán trong tenant:

```cypher
MATCH (o:CapOrder {
  tenantId: $tenantId,
  status: 'PAID'
})
MATCH (o)-[:CAP_HAS_LINE]->(li:CapLine)
WITH o.orderId AS orderId,
     sum(li.quantity * li.unitPrice) AS totalVnd
RETURN orderId, totalVnd
ORDER BY totalVnd DESC, orderId;
```

Kết quả seed t1:

| orderId | totalVnd |
| --- | ---: |
| `o101` | 250000 |
| `o102` | 100000 |

Nếu cần **số đơn đã thanh toán**, không đếm số dòng hàng:

```cypher
MATCH (o:CapOrder {tenantId: $tenantId, status: 'PAID'})
RETURN count(o) AS paidOrders;
```

Dự kiến `paidOrders = 2`. Nếu một đơn có năm dòng hàng, `count(li)` sẽ đếm **năm dòng**, không phải một đơn.

### 17.1. Hai nhánh nhiều quan hệ và nguy cơ nhân bội

Một query muốn đếm cả đơn và vendor đã tương tác có thể tạo tích số dòng khi viết hai `OPTIONAL MATCH` độc lập. Trong Cypher 5.23+ có thể tách từng phép đếm vào subquery:

```cypher
MATCH (c:CapClient {tenantId: $tenantId, clientId: $clientId})
CALL (c) {
  MATCH (c)-[:CAP_PLACED]->(o:CapOrder)
  RETURN count(o) AS orderCount
}
RETURN c.clientId AS clientId, orderCount;
```

Đây là ví dụ cấu trúc cho một nhánh. Nếu thêm nhánh thứ hai, đặt **`CALL (c) { ... }` độc lập** thay vì nhân hai quan hệ trước khi đếm. `count(DISTINCT ...)` có thể sửa sai số đếm nhưng không nhất thiết tránh chi phí trung gian.

## 18. P1 — Tìm đường ít chặng giữa hai kho

Trong Neo4j, đường có số relationship ít nhất là **shortest path theo số chặng**, không phải đường có thời gian/chi phí tổng nhỏ nhất.

Neo4j Cypher hỗ trợ `shortestPath` với một mẫu quan hệ có độ dài biến thiên. Ví dụ cho hai kho `HN` và `CT` trong tenant `t1`:

```cypher
MATCH (src:CapDepot {tenantId: $tenantId, depotId: $from})
MATCH (dst:CapDepot {tenantId: $tenantId, depotId: $to})
MATCH p = shortestPath(
  (src)-[:CAP_ROUTE_TO*1..4]->(dst)
)
WHERE all(n IN nodes(p) WHERE n.tenantId = $tenantId)
RETURN
  [n IN nodes(p) | n.depotId] AS depots,
  length(p) AS hops,
  reduce(minutes = 0, r IN relationships(p) |
         minutes + r.travelMinutes) AS travelMinutes;
```

Tham số `{tenantId:'t1', from:'HN', to:'CT'}`.

Trong seed có ít nhất hai đường **2 chặng**:
- `HN → SG → CT`: `150 + 45 = 195` phút.
- `HN → DN → CT`: `60 + 170 = 230` phút.

`shortestPath` trả **một** đường có số chặng nhỏ nhất; nếu có nhiều đường cùng số chặng, đường được trả **không nhất thiết là đường có trọng số nhỏ nhất**. Nếu cần tất cả đường cùng ít chặng, xem `allShortestPaths`/`ALL SHORTEST` theo version, rồi mới so các tiêu chí phụ.

**Cảnh báo về tenant:** `WHERE all(n IN nodes(p) ...)` bảo vệ output trên bộ seed có các cạnh không xuyên tenant, nhưng **không thay thế mô hình graph đã ngăn cross-tenant routes**. Với graph nhiều tenant có liên kết chéo, điều kiện hậu kiểm có thể loại một đường ngắn vừa tìm thấy mà bỏ qua đường hợp lệ khác. Production cần ràng buộc tenant trong phạm vi traversal/projection và kiểm thử cả node trung gian.

### 18.1. Không tạo path không giới hạn

Câu như sau **không phù hợp** với hệ thống lớn:

```cypher
// Tránh dùng trên graph rộng, giàu chu trình:
MATCH p = (a)-[:CAP_ROUTE_TO*]->(b)
RETURN p;
```

Số path tăng rất nhanh theo độ phân nhánh và chu trình. Bài lab đặt giới hạn `1..4`; sản phẩm thực phải giới hạn search space, thời gian và tài nguyên, hoặc dùng thuật toán shortest path tối ưu cho bài toán.

## 19. P2 — Tìm đường có tổng thời gian nhỏ nhất

### 19.1. Với graph demo nhỏ: duyệt path hữu hạn và cộng trọng số

```cypher
MATCH (src:CapDepot {tenantId: $tenantId, depotId: $from})
MATCH (dst:CapDepot {tenantId: $tenantId, depotId: $to})
MATCH p = (src)-[:CAP_ROUTE_TO*1..4]->(dst)
WHERE all(n IN nodes(p) WHERE n.tenantId = $tenantId)
WITH p,
     reduce(minutes = 0, r IN relationships(p) |
            minutes + r.travelMinutes) AS totalMinutes
RETURN
  [n IN nodes(p) | n.depotId] AS depots,
  length(p) AS hops,
  totalMinutes
ORDER BY totalMinutes ASC, hops ASC, depots
LIMIT 1;
```

**Dự kiến trên seed:**

```text
depots          = ["HN", "DN", "SG", "CT"]
hops            = 3
totalMinutes    = 165
```

Đường này có **3 chặng** nhưng `60 + 60 + 45 = 165` phút, ít hơn cả hai đường 2 chặng ở mục P1.

Vì ràng buộc `*1..4`, query chỉ tìm đường tối ưu **trong tập đường có tối đa bốn relationship**, không chứng minh đường tối ưu tuyệt đối nếu network lớn hơn. Query trên duyệt nhiều path và sắp xếp để chọn một đường; **không mở rộng trực tiếp cách này sang hàng triệu node**.

### 19.2. Khi nào cần Neo4j Graph Data Science?

Đối với mạng lớn, bài toán tìm đường có **trọng số dương** thường phù hợp Dijkstra trong **Neo4j Graph Data Science (GDS)**. Cần:

1. Cài đúng GDS plugin/version, license và role/procedure privileges phù hợp.
2. **Project** một graph chỉ chứa các `CapDepot` và `CAP_ROUTE_TO` của **tenant cần xử lý**, không mặc định lấy toàn bộ nhiều tenant.
3. Nạp property `travelMinutes` làm `relationshipWeightProperty`.
4. Ước lượng bộ nhớ projection/algorithm và theo dõi job.
5. Chạy `gds.shortestPath.dijkstra.stream`; giải phóng projection khi không dùng nữa.

Ví dụ cú pháp **khi đã có** named graph `cap_t1_routes` chứa đúng các kho/cạnh của t1:

```cypher
MATCH (src:CapDepot {tenantId: 't1', depotId: 'HN'})
MATCH (dst:CapDepot {tenantId: 't1', depotId: 'CT'})
CALL gds.shortestPath.dijkstra.stream('cap_t1_routes', {
  sourceNode: src,
  targetNodes: dst,
  relationshipWeightProperty: 'travelMinutes'
})
YIELD totalCost, nodeIds
RETURN totalCost,
       [nodeId IN nodeIds |
          gds.util.asNode(nodeId).depotId] AS depots;
```

Đây là **phần nâng cao có điều kiện**, chưa thể chạy chỉ với script seed Cypher; phải tạo graph projection GDS và bảo đảm source/target thuộc projection. GDS Dijkstra yêu cầu trọng số phù hợp (không âm/đặc biệt là dương theo thuật toán được dùng). Không dùng `shortestPath` ít chặng rồi cộng thời gian sau và tuyên bố đó là đường nhanh nhất.

## 20. Tích hợp Spring Data Neo4j: phân tách write model và read query

Spring Data Neo4j (SDN) có thể dùng entity để quản lý aggregate và custom Cypher cho các read model phẳng.

### 20.1. Đề xuất phân lớp

```text
REST Controller
    |
    +-- Validation + authorization
    |
    v
OrderApplicationService
    |
    +-- OrderWriteAdapter (transaction + idempotency)
    +-- OrderReadAdapter  (Cypher + DTO)
    +-- ReportReadAdapter (aggregate)
    +-- RouteReadAdapter (bounded Cypher hoặc GDS)
    |
    v
Neo4j Driver / Spring Data Neo4j
    |
    v
CapClient / CapOrder / CapLine / CapDepot ...
```

Có thể dùng `Neo4jClient`/`ReactiveNeo4jClient` cho các truy vấn trả scalar/map/DTO để tránh hydrate toàn entity graph khi UI chỉ cần vài property. Với repository:
- `Neo4jRepository` phù hợp mô hình imperative.
- `ReactiveNeo4jRepository` phù hợp Reactor/WebFlux và backpressure.
- `@Query` có thể mô tả truy vấn tùy biến; ánh xạ projection/DTO cần kiểm thử trên phiên bản SDN đang dùng.
- Không trộn transaction tự quản lý bằng `Driver.session(...)` với `@Transactional` của Spring rồi mặc định hai giao dịch là một.

### 20.2. Thiết kế API gợi ý

| HTTP endpoint | Truy vấn dùng | Dạng response |
| --- | --- | --- |
| `GET /clients/me/orders?limit=20` | R1 | `List<OrderSummary>` |
| `GET /orders/{orderId}` | R2 | `OrderDetail` |
| `GET /depots/{depotId}/stock` | R3 | `List<StockSummary>` |
| `POST /orders` | W1 | `OrderWriteResult` |
| `POST /orders/{orderId}/pay` | W2 | `PaymentResult` |
| `GET /reports/top-items?from=&to=` | A1 | `List<ItemRevenue>` |
| `GET /routes?from=HN&to=CT` | P1/P2 | `RouteResult` |

Từng endpoint cần giới hạn số bản ghi/độ sâu, timeout và schema đầu vào; không trả toàn bộ object graph không cần thiết. HTTP code chỉ là gợi ý, không thay thế authorization, payment workflow và API contract thực tế.

## 21. Bảo mật nhiều tenant và kiểm soát dữ liệu

### 21.1. Quy tắc tối thiểu

1. `tenantId` đến từ security context đáng tin cậy.
2. `clientId`/owner của đơn phải được đối chiếu với danh tính/nghiệp vụ.
3. Mọi lookup node bằng composite business key `(tenantId, id)`.
4. Relationship traversal không được đi xuyên tenant nếu nghiệp vụ không cho phép.
5. Java service dùng credential Neo4j ít quyền; không dùng admin cho CRUD.
6. Không nối raw input vào chuỗi Cypher; truyền property values bằng parameters.
7. Nếu cần label/type/sort field động, sử dụng **allowlist** phù hợp phiên bản Cypher, không nội suy input tự do.
8. Đặt bounds cho `LIMIT`, `maxDepth`, số dòng mỗi đơn và kích thước request `UNWIND`.
9. Log request ID/query name/duration, không log toàn bộ PII/secret hoặc dữ liệu thanh toán.
10. Kiểm thử cả role/privilege ở Neo4j và quyền application.

### 21.2. Kiểm tra relationship xuyên tenant

```cypher
MATCH (c:CapClient)-[:CAP_PLACED]->(o:CapOrder)
WHERE c.tenantId <> o.tenantId
RETURN count(*) AS crossTenantPlaced;
```

```cypher
MATCH (o:CapOrder)-[:CAP_HAS_LINE]->(li:CapLine)
WHERE o.tenantId <> li.tenantId
RETURN count(*) AS crossTenantOrderLines;
```

```cypher
MATCH (a:CapDepot)-[:CAP_ROUTE_TO]->(b:CapDepot)
WHERE a.tenantId <> b.tenantId
RETURN count(*) AS crossTenantRoutes;
```

Trên bộ seed, cả ba phải bằng `0`. Nếu thêm relationship xuyên tenant trong các bài kiểm thử, query đường đi và query read cần xử lý theo policy, không âm thầm trả dữ liệu.

## 22. Đo chất lượng truy vấn bằng `EXPLAIN` và `PROFILE`

Với query R1:

```cypher
EXPLAIN
MATCH (o:CapOrder {
  tenantId: $tenantId,
  clientId: $clientId
})
RETURN o.orderId, o.createdAt
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT $limit;
```

Sau đó đo trên dataset đại diện:

```cypher
PROFILE
MATCH (o:CapOrder {
  tenantId: $tenantId,
  clientId: $clientId
})
RETURN o.orderId, o.createdAt
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT $limit;
```

Các thành phần phải ghi vào báo cáo:

| Chỉ số/Operator | Ý nghĩa |
| --- | --- |
| `NodeIndexSeek` / `NodeByLabelScan` | Có tận dụng đường vào theo khóa hoặc scan không? |
| `Estimated Rows` so với `Rows` | Planner ước lượng cardinality tốt không? |
| `DB Hits` | Mức truy cập storage engine; **không đồng nghĩa disk reads vật lý** |
| `Expand(All)` / `VarLengthExpand` | Có bị fan-out hoặc bùng nổ path không? |
| `Sort`, `EagerAggregation` | Có nhiều dữ liệu trung gian phải giữ trong memory không? |
| `Rows` trước/sau `LIMIT` | Giới hạn có được đẩy sớm đủ cho use case không? |
| Kích thước response | Có cần gom cả node/relationship không? |
| Latency p50/p95/p99 | Trải nghiệm thực dưới tải và phân phối tham số |

**Không chạy `PROFILE` cho query W1/W2 trên production**: `PROFILE` thực thi cả thao tác ghi, không phải dry run. Với bài lab, chạy trên dữ liệu test và biết rõ transaction có thể tạo/sửa gì.

### 22.1. So sánh query có ý nghĩa

Một query có `LIMIT 20` và một query tải 20 triệu record **không làm cùng công việc**; chỉ có thể so sau khi khẳng định cả hai đáp ứng cùng contract. Một `PROFILE` trên ba đơn hàng demo không chứng minh kế hoạch tốt cho ba triệu đơn.

Bài nộp nên có:
- Một bộ dữ liệu nhỏ để xác minh tính đúng.
- Một tập dữ liệu lớn/mô phỏng phân phối high-degree để đánh giá plan.
- Số đo ứng dụng và database trên cùng khoảng tải.
- Phân tích vì sao chọn index và chiều duyệt, không chỉ ảnh chụp plan.

## 23. Kiểm thử tự động và đối soát kết quả

### 23.1. Bộ test đọc/tổng hợp

| Test ID | Hành động | Kết quả kỳ vọng trên seed |
| --- | --- | --- |
| T01 | R1 tenant t1, client c01 | `o102, o101` theo thời gian giảm |
| T02 | R1 tenant t1, client c02 | Chỉ `o103` |
| T03 | R1 tenant t2, client c01 | Chỉ `o201` |
| T04 | R2 t1/c01/o101 | Hai dòng, tổng `250000` |
| T05 | R2 t1/c02/o101 | 0 dòng |
| T06 | R3 kho HN t1 | `skuA` với `available=120` |
| T07 | Vendor của t1/skuC | Chỉ `v02` |
| T08 | A1 tenant t1, 01–04/11 | `skuA=300000`, `skuB=50000` |
| T09 | A2 paid orders tenant t1 | `o101=250000`, `o102=100000` |
| T10 | Đếm đơn paid tenant t1 | `2` |
| T11 | P1 HN → CT | Có một đường `2` chặng, phút có thể `195` hoặc `230` |
| T12 | P2 HN → CT, maxDepth 4 | `[HN,DN,SG,CT]`, tổng `165` |
| T13 | Kiểm tra quan hệ xuyên tenant | Tất cả count bằng `0` |
| T14 | Query tenant t2 theo SKU trùng `skuA` | Chỉ thấy dữ liệu của t2 |

Nếu seed có thêm dữ liệu từ trước, hãy reset **môi trường lab** theo quy trình được phê duyệt hoặc lọc theo ID test, không dùng `MATCH (n) DETACH DELETE n` trên một database dùng chung.

### 23.2. Bộ test transaction ghi

1. **T15 — First write**: gọi W1 với `o900 / req-900 / l900a` → một order, một line và hai loại quan hệ cần thiết.
2. **T16 — Retry y hệt**: gửi lại cùng payload → vẫn một order và một line.
3. **T17 — Conflict request ID**: cùng `requestId` nhưng `orderId` khác → unique constraint từ chối; không tạo đơn mới.
4. **T18 — Conflict line ID**: dùng lại `lineId` với SKU/số lượng khác → managed transaction trả lỗi và rollback.
5. **T19 — Client không tồn tại**: phải không tạo order/line.
6. **T20 — SKU tenant khác**: không có item phù hợp, không tạo order.
7. **T21 — Số lượng 0/âm hoặc giá âm**: validation từ chối trước truy vấn.
8. **T22 — Lỗi mạng sau commit**: ứng dụng có thể tra theo `requestId/orderId` và retry an toàn.
9. **T23 — Cùng orderId hai request khác nhau đồng thời**: chỉ một được chấp nhận theo business rule.
10. **T24 — Chuyển trạng thái trái phép**: không thay đổi order khi sai owner/trạng thái.

**Test concurrent writes phải chạy trên instance lab có nhiều kết nối**, kiểm tra constraint và kết quả sau khi tất cả request hoàn thành. Không suy “có `MERGE` là chống race hoàn toàn” nếu business logic còn có kiểm tra tồn kho, gửi side effect hoặc trạng thái liên quan.

### 23.3. Mẫu test Cypher cho W1

Sau khi gọi API W1 (không tự chạy nếu chưa tạo dữ liệu):

```cypher
MATCH (o:CapOrder {tenantId: 't1', orderId: 'o900'})
OPTIONAL MATCH (o)-[:CAP_HAS_LINE]->(li:CapLine)
RETURN count(DISTINCT o) AS orders,
       count(DISTINCT li) AS lines;
```

**Dự kiến:** `orders=1, lines=1`. Kiểm tra thêm `requestId`, `li.quantity` và relationship `CAP_OF_ITEM`. Hai giá trị trên chưa đủ để xác nhận tất cả invariant nghiệp vụ.

## 24. Xử lý lỗi, hiệu năng và vận hành

| Lỗi/sự cố | Nguồn có thể | Phản ứng đúng |
| --- | --- | --- |
| `ConstraintValidationFailed` | Trùng composite key hoặc request ID | Báo conflict, không retry vô hạn |
| `ClientException` do cú pháp | Query sai version/parameter | Sửa code, test lại |
| `TransientException` | Cluster leader đổi, network hoặc khóa tạm thời | Retry có giới hạn, idempotent |
| Timeout ở Java | DB chậm, pool chờ, network, commit không rõ | Phân biệt request/transaction; đối soát khi write |
| `OutOfMemoryError` trên Java client | `list()` gom dữ liệu lớn | Page/stream/DTO và đo JVM client |
| Neo4j transaction memory limit | Query `collect`/`UNWIND` quá lớn | Giảm batch/fan-out; không tăng limit tùy ý |
| Đường đi quá chậm | Graph có nhiều nhánh, `*1..N` lớn | Giới hạn search, GDS Dijkstra, profile |
| Dashboard aggregate chậm | Quét nhiều dòng lịch sử | Index, read model, lịch pre-aggregation |
| Một request trả data tenant khác | Thiếu authorization hoặc traversal scope | Khóa API, sửa query và test âm tính |
| Retry tạo đơn trùng | Thiếu business ID/constraint/outbox | Unique keys, kiểm tra commit outcome |

Khi triển khai production:
- Sử dụng Driver pool chung, session ngắn.
- Chọn `executeRead`/`executeWrite` theo nghiệp vụ để hưởng routing/retry phù hợp.
- Có transaction timeout và budget retry dựa trên SLO; không mở transaction trong khi chờ HTTP/Kafka.
- Quan sát p95/p99, errors, pool wait, Rows/DB Hits, page cache, heap/GC.
- Backup/restore và kiểm thử RBAC là các yêu cầu ngoài bộ truy vấn, không thể bỏ qua khi đồ án trở thành dịch vụ thật.

## 25. Quy trình làm đồ án theo các chặng

### Chặng 1 — Mô hình và dữ liệu

- Vẽ graph, giải thích vì sao có `CapLine` và vì sao route có hướng.
- Tạo 7 uniqueness constraints và 2 index.
- Seed node/relationship theo thứ tự, đối chiếu count seed t1/t2.
- Thử seed lại để kiểm tra không tạo duplicate, nhưng lưu ý các `SET` reset property về trạng thái mẫu.

### Chặng 2 — Đọc đúng use case

- Hoàn thành R1, R2, R3 với parameter và DTO.
- Bổ sung giới hạn kết quả và test âm tính tenant/client.
- Giải thích lựa chọn index/traversal.

### Chặng 3 — Ghi an toàn

- Triển khai W1 bằng managed transaction.
- Bắt buộc xác nhận số record, test idempotency và uniqueness.
- Thêm W2 với validation và phân quyền; không tích hợp thanh toán thật trong lab.

### Chặng 4 — Tổng hợp

- Hoàn thành A1/A2, so expected `300000`/`50000` và tổng `350000`.
- Chứng minh không nhân bội row do join.
- Ghi lại khi nào cần pre-aggregation ở quy mô lớn.

### Chặng 5 — Tìm đường

- Hoàn thành P1/P2.
- So đường 2 chặng với đường 3 chặng 165 phút.
- Giải thích giới hạn `maxDepth`, độ phân nhánh, dữ liệu xuyên tenant và lúc cần GDS.

### Chặng 6 — Tích hợp và chứng minh

- Có Java Driver/SDN code chạy đúng trên môi trường.
- Thực hiện test được liệt kê, chụp `EXPLAIN`/`PROFILE` cho read/aggregate/path khi an toàn.
- Ghi rõ lỗi, dữ liệu test, cách reset, thời gian và giả thuyết tối ưu.
- Nộp README hướng dẫn khởi chạy và một bảng kết quả đo (nếu làm thành dự án thực).

## 26. Rubric chấm điểm đồ án (100 điểm)

| Hạng mục | Điểm tối đa | Điều kiện đạt |
| --- | ---: | --- |
| Mô hình graph, key, constraint, index và seed | 15 | Schema hợp lý, seed lặp lại có kiểm soát |
| R1/R2/R3, pagination, bảo vệ tenant | 20 | Đúng dữ liệu, không tải dư, test ownership |
| W1/W2, managed transaction, idempotency | 20 | Không tạo trùng, rollback khi sai input |
| A1/A2, số liệu và tính đúng aggregation | 15 | Đúng tổng `350000`, giải thích fan-out |
| P1/P2 và phân biệt hops/trọng số | 15 | Có path đúng, hiểu giới hạn và GDS |
| Query plan, security, performance và negative tests | 10 | Có bằng chứng đo, nhận diện nguy cơ |
| Tài liệu cách chạy, kết quả, giới hạn | 5 | Người khác tái hiện được bài |
| **Tổng** | **100** | |

Rubric nhấn mạnh **tính đúng và khả năng giải thích thiết kế**, không chấm theo số dòng Cypher. Một hệ thống có 30 endpoint nhưng sai quyền truy cập tenant hoặc retry tạo trùng đơn không đạt mục tiêu đồ án.

## 27. Các sai lầm cần nhận diện trong bài nộp

| Sai lầm | Vì sao sai | Sửa thế nào |
| --- | --- | --- |
| `MATCH (n) RETURN n` rồi lọc Java | Quét graph, tốn network/heap, rủi ro lộ dữ liệu | Bắt đầu từ composite business key |
| Dùng `id(n)` làm API ID | Không ổn định theo vòng đời store | `tenantId + businessId` có constraint |
| Không tách dòng hàng khỏi sản phẩm | Không mô tả được nhiều dòng cùng SKU | `CapLine` node với `lineId` |
| `CREATE` mọi lần retry | Tạo trùng nếu commit ACK bị mất | `MERGE` + request ID + unique constraints |
| Query W1 trả 0 record nhưng Java vẫn commit | Partial side effect trước filter | `.single()` trong managed tx để rollback |
| Tính doanh thu bằng giá danh mục hiện tại | Sai lịch sử giá | `CapLine.unitPrice` |
| Đếm `count(li)` thành số đơn | Một đơn có nhiều line | `count(o)` hoặc aggregation đúng scope |
| `LIMIT` sau khi expand dòng hàng | Cắt dở đơn | Page `CapOrder` trước rồi mở rộng |
| Dùng `shortestPath` để tìm phút nhỏ nhất | Chỉ tối ưu số hops | Weighted search / GDS Dijkstra |
| Dùng `*` không giới hạn | Bùng nổ số path | Bounded traversal, chọn thuật toán |
| Chỉ lọc tenant ở endpoint path | Có thể đi qua tenant khác | Bảo vệ toàn traversal/projection |
| Không chạy test tenant t2 | SKU/ID có thể trùng tenant | Negative tests bắt buộc |
| Trộn Driver transaction với Spring transaction | Mất tính nguyên tử giả định | Quản lý một ranh giới rõ |
| `PROFILE` query ghi trên production | Thực sự sửa data | Chỉ profile write trên lab |
| Gọi GDS mà chưa project graph | Named graph không tồn tại | Project riêng tenant, estimate memory |
| Nạp mọi kết quả vào `List`/`collectList` | Client có thể OOM | LIMIT, DTO, batch/stream |

## 28. Câu hỏi phản biện khi bảo vệ đồ án

1. Vì sao chọn `CapLine` là node thay vì chỉ dùng property trên relationship trực tiếp?
2. Composite uniqueness constraint khác gì index thông thường?
3. Nếu hai người đặt cùng `orderId` đồng thời thì `MERGE` và constraint xử lý thế nào?
4. Trong W1, nếu SKU không tồn tại mà query đã tạo order thì làm sao bảo đảm rollback?
5. Vì sao không được thực hiện một thanh toán ngoài Neo4j trong callback `executeWrite`?
6. Nếu client timeout sau commit, làm sao xác minh đơn `o900` đã được tạo?
7. Tại sao danh sách 20 đơn cần `LIMIT` **trước** khi đi sang các dòng?
8. Vì sao `o103` không được tính trong tổng doanh thu ban đầu?
9. Vì sao top 10 vẫn có thể đọc hàng triệu dòng từ graph lớn?
10. Tại sao P1 có thể trả path 195/230 phút mà P2 trả 165 phút?
11. Điều gì xảy ra khi có đường hợp lệ dài 5 hops nhưng query P2 chỉ cho tối đa 4?
12. Vì sao một điều kiện tenant đặt sau `shortestPath` có thể chưa đủ cho bảo mật và tính đầy đủ?
13. Trong hệ nhiều tenant, một người có `tenantId='t1'` có thể tự chọn `clientId='c02'` không?
14. Vì sao `PROFILE` không được xem là “giả lập” khi query chứa `SET`?
15. Nếu đổi sang Spring WebFlux, cách tiêu thụ record và quản lý session thay đổi thế nào?

## 29. Tổng kết kiến thức rút ra

Một hệ thống Neo4j tốt không chỉ biết tạo nhiều node và nối relationship. **Trọng tâm là biến từng ca sử dụng thành một truy vấn có điểm bắt đầu rõ ràng, dữ liệu trả về vừa đủ, transaction đúng và khả năng kiểm chứng.**

- **Đọc:** bám business key + tenant, chọn property/DTO, phân trang trước khi mở rộng.
- **Ghi:** kiểm soát validation và authorization, dùng uniqueness constraints, `MERGE`, managed transaction, idempotency key và rollback khi kết quả không hợp lệ.
- **Tổng hợp:** gom đúng cấp dữ liệu, phân biệt số đơn và số dòng, dùng giá lịch sử và không nhân row bởi nhiều nhánh quan hệ.
- **Tìm đường:** phân biệt ít hops với ít trọng số; bounded Cypher phù hợp lab nhỏ, GDS Dijkstra phù hợp bài toán weighted graph lớn đã được project đúng phạm vi.
- **Vận hành:** quan sát `EXPLAIN`/`PROFILE`, memory/pool, kiểm thử multi-tenant và document rõ giới hạn, thay vì giả định câu query chạy nhanh trên seed nhỏ cũng đủ tốt cho production.

Đồ án hoàn thành khi có **dữ liệu, truy vấn, API, test positive/negative, số liệu kỳ vọng và lời giải thích về trade-off**, không chỉ một tập câu Cypher chạy thành công.

### Tài liệu tham khảo chính thức

- [Neo4j Cypher Manual — MATCH](https://neo4j.com/docs/cypher-manual/current/clauses/match/)
- [Neo4j Cypher Manual — MERGE](https://neo4j.com/docs/cypher-manual/current/clauses/merge/)
- [Neo4j Cypher Manual — UNWIND](https://neo4j.com/docs/cypher-manual/current/clauses/unwind/)
- [Neo4j Cypher Manual — WITH](https://neo4j.com/docs/cypher-manual/current/clauses/with/)
- [Neo4j Cypher Manual — CALL subqueries](https://neo4j.com/docs/cypher-manual/current/subqueries/call-subquery/)
- [Neo4j Cypher Manual — Aggregating functions](https://neo4j.com/docs/cypher-manual/current/functions/aggregating/)
- [Neo4j Cypher Manual — List functions: reduce, nodes, relationships](https://neo4j.com/docs/cypher-manual/current/functions/list/)
- [Neo4j Cypher Manual — Shortest paths](https://neo4j.com/docs/cypher-manual/current/patterns/shortest-paths/)
- [Neo4j Cypher Manual — Create constraints](https://neo4j.com/docs/cypher-manual/current/schema/constraints/create-constraints/)
- [Neo4j Cypher Manual — Create indexes](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/create-indexes/)
- [Neo4j Cypher Manual — Execution plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/)
- [Neo4j Java Driver Manual — Transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Java Driver Manual — Performance recommendations](https://neo4j.com/docs/java-manual/current/performance/)
- [Neo4j GDS — Dijkstra Source-Target shortest path](https://neo4j.com/docs/graph-data-science/current/algorithms/dijkstra-source-target/)
- [Neo4j GDS — Graph projection](https://neo4j.com/docs/graph-data-science/current/management-ops/graph-creation/graph-project/)
- [Spring Data Neo4j — Reference](https://docs.spring.io/spring-data/neo4j/reference/)
