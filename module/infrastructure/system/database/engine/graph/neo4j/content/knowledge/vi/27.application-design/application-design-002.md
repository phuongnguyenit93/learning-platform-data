# Thiết kế truy vấn theo ca sử dụng thay vì tải toàn bộ đồ thị trong Neo4j

## 1. Vì sao “lấy toàn bộ graph rồi lọc ở Java” là một thiết kế nguy hiểm?

Neo4j quản lý **property graph** gồm node, relationship và thuộc tính. Sức mạnh của graph database là đi từ một **điểm bắt đầu được xác định rõ** rồi khám phá những liên kết **liên quan đến câu hỏi nghiệp vụ**, chứ không phải luôn nạp tất cả node và relationship vào bộ nhớ ứng dụng.

Giả sử một nền tảng thương mại B2B có 20 triệu đơn hàng, 5 triệu khách hàng, hàng chục triệu dòng sản phẩm và hàng trăm triệu relationship. Một màn hình chi tiết đơn hàng chỉ cần:

> “Cho khách hàng hiện tại xem đơn hàng `o101` thuộc tenant `t1`, tối đa các mặt hàng trong đúng đơn đó và trạng thái thanh toán.”

Nếu ứng dụng thực hiện:

```cypher
// KHÔNG phù hợp cho API nghiệp vụ thông thường:
MATCH (n)
RETURN n;
```

rồi tải tất cả node về Java để tìm đơn hàng, ứng dụng sẽ gặp nhiều vấn đề:

- **Chi phí không tỷ lệ với nhu cầu:** màn hình cần một đơn nhưng database và mạng phải xử lý dữ liệu của toàn bộ graph.
- **Heap phía Java tăng:** `Result.list()`, ánh xạ entity và serialization có thể giữ hàng triệu phần tử.
- **Tăng số lần đọc storage:** quét graph có thể tạo rất nhiều `DB Hits`, tiêu tốn page cache và CPU.
- **Tăng rủi ro dữ liệu:** tải cả những khách hàng/tenant không thuộc phạm vi quyền truy cập.
- **Khó phân trang:** áp `LIMIT` ở cuối sau khi mở rộng nhiều quan hệ có thể giới hạn **số dòng**, không phải số đơn hàng.
- **Không tận dụng index có chủ đích:** lấy toàn bộ graph khiến index và constraint khóa nghiệp vụ ít được phát huy.

Nguyên tắc quan trọng: **thiết kế truy vấn bắt đầu từ ca sử dụng (use case), ranh giới quyền truy cập, đầu ra API và lượng dữ liệu cho phép trả về**. Sau đó mới quyết định label, relationship, hướng duyệt, index, cách phân trang và kiểu ánh xạ Java/Spring Data Neo4j.

## 2. Đi từ yêu cầu màn hình/API đến “hình dạng dữ liệu”

Trước khi viết Cypher, hãy tạo một **query contract** cho mỗi ca sử dụng.

| Ca sử dụng | Điểm bắt đầu | Quan hệ cần duyệt | Đầu ra API | Giới hạn |
| --- | --- | --- | --- | --- |
| Xem danh sách đơn của khách | `tenantId` + `customerId` | `Customer-[:PLACED]->Order` | ID, ngày tạo, trạng thái | Tối đa 20–50 đơn/trang |
| Xem chi tiết một đơn | `tenantId` + `customerId` + `orderId` | `Order-[:HAS_LINE]->Product` | Thông tin đơn và dòng sản phẩm | Một đơn, số dòng giới hạn theo nghiệp vụ |
| Thống kê sản phẩm bán chạy | Tenant và khoảng ngày | `Order-[:HAS_LINE]->Product` | SKU và tổng số lượng | Top N, cân nhắc tổng hợp trước |
| Kiểm tra khách có quyền thấy đơn | Identity đã xác thực + tenant | `Customer-[:PLACED]->Order` | Boolean hoặc ID cho phép | Chỉ một đối tượng đích |
| Phân tích PageRank trên mạng nhà cung cấp | Một tập nhãn/loại quan hệ được chọn | Toàn hoặc phần lớn graph phân tích | Điểm số theo node | Dùng job phân tích/GDS riêng |

**Hình dạng dữ liệu** (*result shape*) là thiết kế của dữ liệu được trả về: một object, một danh sách ngắn, một summary hay stream lớn. Đừng trả toàn bộ node và mọi relationship chỉ để lấy hai thuộc tính.

### Quy trình 6 câu hỏi

1. **Ai yêu cầu?** Người dùng, service nội bộ, job phân tích; tenant và role nào?
2. **Đối tượng gốc là gì?** Khách hàng/đơn hàng/sản phẩm được xác định bằng khóa nào?
3. **Cần đi mấy bước?** Loại relationship nào, hướng nào, có giới hạn độ sâu và fan-out không?
4. **Cần thuộc tính nào?** Những field nào phục vụ API, báo cáo hoặc giao diện?
5. **Giới hạn bao nhiêu?** `LIMIT`, khoảng thời gian, pagination, sampling, max depth, timeout.
6. **Yêu cầu nhất quán?** Dữ liệu transaction mới nhất, báo cáo theo snapshot hay read model cập nhật theo lô?

Trong nhiều trường hợp, **một use case tương ứng một truy vấn đọc tối ưu**, chứ không nhất thiết tương ứng việc “đọc toàn bộ aggregate object” trong ORM.

## 3. Mô hình graph thực hành: khách hàng, đơn hàng và sản phẩm

### 3.1. Lược đồ phục vụ các cách truy cập

Giả sử hệ thống có:

```text
(:ShopCustomer {tenantId, customerId, name})
          |
        PLACED
          |
          v
(:ShopOrder {tenantId, orderId, customerId, createdAt, status})
          |
        HAS_LINE {quantity, unitPrice}
          |
          v
(:ShopProduct {tenantId, sku, title})
```

Trong mô hình này:

- `ShopCustomer` thuộc tenant, được xác định bằng cặp `(tenantId, customerId)`.
- `ShopOrder` có cặp khóa `(tenantId, orderId)`; `customerId` được lưu thêm để hỗ trợ **một cách truy cập đọc trực tiếp bằng index**.
- `HAS_LINE` lưu số lượng và đơn giá tại thời điểm mua; giá này khác giá niêm yết hiện tại của `ShopProduct`.
- Relationship `PLACED` giữ ý nghĩa liên kết nghiệp vụ, cho phép kiểm tra khách nào sở hữu đơn.
- Tất cả truy vấn đều bắt đầu từ **tenant được xác định từ danh tính đã xác thực**, không tin tưởng một tenantId tùy ý do client truyền vào.

Đây là mô hình minh họa: nếu một đơn có **nhiều dòng cho cùng SKU**, cần mô hình hóa `OrderLine` thành node có `lineId` riêng hoặc có cơ chế định danh dòng phù hợp, thay vì giả định chỉ một relationship `HAS_LINE` giữa một cặp node.

### 3.2. Constraint và index được định hướng bởi use case

```cypher
CREATE CONSTRAINT shop_customer_key IF NOT EXISTS
FOR (c:ShopCustomer)
REQUIRE (c.tenantId, c.customerId) IS UNIQUE;
```

```cypher
CREATE CONSTRAINT shop_order_key IF NOT EXISTS
FOR (o:ShopOrder)
REQUIRE (o.tenantId, o.orderId) IS UNIQUE;
```

```cypher
CREATE CONSTRAINT shop_product_key IF NOT EXISTS
FOR (p:ShopProduct)
REQUIRE (p.tenantId, p.sku) IS UNIQUE;
```

Để tìm danh sách đơn hàng mới nhất bằng các thuộc tính trên chính node `ShopOrder`:

```cypher
CREATE RANGE INDEX shop_order_customer_feed IF NOT EXISTS
FOR (o:ShopOrder)
ON (o.tenantId, o.customerId, o.createdAt, o.orderId);
```

Để thống kê đơn theo trạng thái/khoảng thời gian, có thể đánh giá thêm:

```cypher
CREATE RANGE INDEX shop_order_status_time IF NOT EXISTS
FOR (o:ShopOrder)
ON (o.tenantId, o.status, o.createdAt);
```

**Không tạo mọi index chỉ vì “có thể dùng”.** Các index có chi phí lưu trữ và cập nhật. Chỉ giữ index cho những đường truy cập được đo là cần thiết; đối chiếu `SHOW INDEXES` và `EXPLAIN`/`PROFILE`. Nếu query bắt đầu từ `ShopCustomer` rồi duyệt `PLACED`, planner không nhất thiết sử dụng index `shop_order_customer_feed`.

### 3.3. Dữ liệu thử nghiệm có thể chạy lại

Tạo khách hàng:

```cypher
UNWIND [
  {tenantId: 't1', customerId: 'c1', name: 'An'},
  {tenantId: 't1', customerId: 'c2', name: 'Bình'},
  {tenantId: 't2', customerId: 'c1', name: 'Khách T2'}
] AS row
MERGE (c:ShopCustomer {
  tenantId: row.tenantId,
  customerId: row.customerId
})
SET c.name = row.name;
```

Tạo sản phẩm:

```cypher
UNWIND [
  {tenantId: 't1', sku: 'sku01', title: 'Bàn phím'},
  {tenantId: 't1', sku: 'sku02', title: 'Chuột'},
  {tenantId: 't1', sku: 'sku03', title: 'Màn hình'}
] AS row
MERGE (p:ShopProduct {tenantId: row.tenantId, sku: row.sku})
SET p.title = row.title;
```

Tạo đơn hàng và quan hệ với khách:

```cypher
UNWIND [
  {tenantId: 't1', customerId: 'c1', orderId: 'o101',
   at: '2026-10-03T09:30:00+07:00', status: 'PAID'},
  {tenantId: 't1', customerId: 'c1', orderId: 'o102',
   at: '2026-10-04T11:00:00+07:00', status: 'NEW'},
  {tenantId: 't1', customerId: 'c2', orderId: 'o103',
   at: '2026-10-05T08:00:00+07:00', status: 'PAID'}
] AS row
MATCH (c:ShopCustomer {
  tenantId: row.tenantId,
  customerId: row.customerId
})
MERGE (o:ShopOrder {tenantId: row.tenantId, orderId: row.orderId})
SET o.customerId = row.customerId,
    o.createdAt = datetime(row.at),
    o.status = row.status
MERGE (c)-[:PLACED]->(o);
```

Tạo các dòng sản phẩm:

```cypher
UNWIND [
  {orderId: 'o101', sku: 'sku01', quantity: 2, unitPrice: 550000},
  {orderId: 'o101', sku: 'sku02', quantity: 1, unitPrice: 250000},
  {orderId: 'o102', sku: 'sku03', quantity: 1, unitPrice: 3000000},
  {orderId: 'o103', sku: 'sku01', quantity: 1, unitPrice: 550000}
] AS row
MATCH (o:ShopOrder {tenantId: 't1', orderId: row.orderId})
MATCH (p:ShopProduct {tenantId: 't1', sku: row.sku})
MERGE (o)-[line:HAS_LINE]->(p)
SET line.quantity = row.quantity,
    line.unitPrice = row.unitPrice;
```

Trong database thử nghiệm sạch, `t1` có 2 khách hàng, 3 đơn hàng và 4 relationship `HAS_LINE`. Lệnh `MERGE` giúp tránh tạo lặp các cặp node quan hệ mẫu khi chạy lại, nhưng không thay thế constraint cho mọi trường hợp ghi đồng thời hay mô hình dòng hàng phức tạp.

## 4. Use case 1 — Danh sách đơn: truy vấn có điểm bắt đầu và đầu ra gọn

### 4.1. Phản ví dụ: lấy tất cả đơn của cả hệ thống

```cypher
// Truy vấn tệ cho màn hình đơn hàng của MỘT khách:
MATCH (o:ShopOrder)
RETURN o;
```

Ngay cả khi Java chỉ chọn các đơn có `customerId = 'c1'`, database vẫn phải gửi tất cả đơn. Khi graph có nhiều tenant, cách này còn tăng rủi ro lộ dữ liệu.

### 4.2. Cách 1: từ khách hàng rồi duyệt một loại quan hệ

```cypher
MATCH (c:ShopCustomer {
  tenantId: $tenantId,
  customerId: $customerId
})-[:PLACED]->(o:ShopOrder)
WHERE o.tenantId = $tenantId
RETURN
  o.orderId AS orderId,
  o.createdAt AS createdAt,
  o.status AS status
ORDER BY createdAt DESC, orderId DESC
LIMIT $limit;
```

Giá trị tham số ví dụ:

```json
{
  "tenantId": "t1",
  "customerId": "c1",
  "limit": 20
}
```

Câu lệnh này:

- Dùng **khóa nghiệp vụ cụ thể** để neo truy vấn vào một khách hàng.
- Chỉ duyệt quan hệ **`PLACED` theo đúng chiều**.
- Trả về **ba thuộc tính** cần cho UI thay vì toàn bộ node.
- Sắp xếp ổn định nhờ `orderId` là khóa phụ khi nhiều đơn cùng thời điểm.
- Áp giới hạn số kết quả; phía API cần **validate limit** (ví dụ từ 1 tới 50).

### 4.3. Cách 2: tra cứu trực tiếp đơn hàng theo read path

Nếu khách hàng có **rất nhiều đơn**, có thể cân nhắc truy vấn trực tiếp bằng thuộc tính đã được lưu trên node `ShopOrder`:

```cypher
MATCH (o:ShopOrder {
  tenantId: $tenantId,
  customerId: $customerId
})
RETURN o.orderId AS orderId,
       o.createdAt AS createdAt,
       o.status AS status
ORDER BY createdAt DESC, orderId DESC
LIMIT $limit;
```

Index tổng hợp `(tenantId, customerId, createdAt, orderId)` **có thể giúp lọc và tận dụng thứ tự** khi các thuộc tính đầu được ràng buộc bằng đẳng thức. Planner quyết định dựa trên thống kê/chi phí; phải xác nhận bằng `EXPLAIN` và `PROFILE`.

**Đánh đổi mô hình:** `customerId` trên đơn hàng là thuộc tính **denormalized** bên cạnh relationship `PLACED`. Ứng dụng phải duy trì hai biểu diễn nhất quán trong transaction ghi, nhất là khi nghiệp vụ cho phép chuyển quyền sở hữu đơn. Nếu không chấp nhận được độ phức tạp này, dùng đường duyệt quan hệ có index neo khách, hoặc xây read model riêng.

**Bảo mật:** truy vấn trực tiếp theo `customerId` chỉ an toàn khi giá trị được suy ra/kiểm chứng từ identity và authorization. Một khách hàng không được tự thay `customerId` trong URL để xem đơn của người khác. Chỉ lọc theo `tenantId` chưa đủ nếu nhiều khách cùng tenant.

## 5. Use case 2 — Chi tiết đơn và dòng hàng: mở rộng đúng một phạm vi

Đối với API `GET /orders/{orderId}`, thường cần một đơn và danh sách các mặt hàng của đơn đó:

```cypher
MATCH (c:ShopCustomer {
  tenantId: $tenantId,
  customerId: $customerId
})-[:PLACED]->(o:ShopOrder {
  tenantId: $tenantId,
  orderId: $orderId
})
OPTIONAL MATCH (o)-[line:HAS_LINE]->(p:ShopProduct)
WHERE p.tenantId = $tenantId
WITH o, line, p
ORDER BY p.sku
RETURN
  o.orderId AS orderId,
  o.createdAt AS createdAt,
  o.status AS status,
  collect(
    CASE WHEN p IS NOT NULL THEN {
      sku: p.sku,
      title: p.title,
      quantity: line.quantity,
      unitPrice: line.unitPrice
    } END
  ) AS items;
```

**Vì sao đây là query theo use case?**

1. `MATCH` đầu tiên đồng thời xác định **tenant, customer và order**, tức ranh giới quyền sở hữu.
2. `OPTIONAL MATCH` lấy mặt hàng của **đúng một đơn**, không mở rộng toàn bộ đồ thị sản phẩm.
3. `collect(...)` gom các dòng hàng thành **một danh sách** cho DTO. Cypher `collect` bỏ qua giá trị `null`, nên nếu không có mặt hàng có thể nhận `[]` thay vì một phần tử `null`.
4. Các property được chọn rõ; không cần dùng `RETURN c, o, p` nếu giao diện không hiển thị đầy đủ các node.

**Lưu ý nghiệp vụ:** danh sách dòng hàng của một đơn có thể lớn. Nếu hàng nghìn mặt hàng hoặc có lịch sử thay đổi, thiết kế API **phân trang dòng hàng riêng** thay vì luôn gom thành một response rất lớn.

### N+1 query khi xử lý ở Java

Một anti-pattern phổ biến:

1. Query 1 lấy 20 đơn hàng.
2. Java lặp 20 đơn, mỗi lần gửi thêm một query để lấy dòng hàng.
3. Tổng cộng **21 round-trip** tới Neo4j cho một màn hình.

Cách giảm N+1:

- Nếu màn hình chỉ cần summary, **không tải dòng hàng**.
- Nếu màn hình cần dòng hàng của 20 đơn, chọn trước 20 đơn rồi mở rộng và gom dòng hàng trong **một truy vấn có giới hạn**.
- Nếu dòng hàng nhiều, dùng **hai truy vấn theo batch** (truy vấn danh sách đơn, rồi truy vấn tất cả dòng hàng của tập ID được phép). Hai round-trip đôi khi dễ kiểm soát bộ nhớ và cache hơn một query có một `collect` quá lớn.

**Không mặc định “càng ít query càng tốt”**: một query khổng lồ với nhiều nhánh một-nhiều có thể tạo Cartesian product và tốn tài nguyên hơn vài query nhỏ được thiết kế đúng.

## 6. Phân trang **trước** khi mở rộng quan hệ

### 6.1. Sai lầm: giới hạn số dòng sau khi join

```cypher
// Có thể cắt dở dòng hàng và không lấy đủ $limit đơn:
MATCH (c:ShopCustomer {
  tenantId: $tenantId,
  customerId: $customerId
})-[:PLACED]->(o:ShopOrder)-[:HAS_LINE]->(p:ShopProduct)
RETURN o.orderId AS orderId, p.sku AS sku
ORDER BY orderId DESC
LIMIT $limit;
```

Nếu một đơn có 30 dòng sản phẩm, `LIMIT 20` ở trên có thể trả **20 dòng hàng của một đơn**, không phải 20 đơn. Phần relationship đã mở rộng trước khi `LIMIT` cũng có thể tạo nhiều dòng trung gian.

### 6.2. Đúng hơn: chọn trang đơn hàng rồi lấy dòng hàng

```cypher
MATCH (c:ShopCustomer {
  tenantId: $tenantId,
  customerId: $customerId
})-[:PLACED]->(o:ShopOrder)
WHERE o.tenantId = $tenantId
WITH o
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT $limit
OPTIONAL MATCH (o)-[line:HAS_LINE]->(p:ShopProduct)
WHERE p.tenantId = $tenantId
RETURN
  o.orderId AS orderId,
  o.createdAt AS createdAt,
  o.status AS status,
  collect(
    CASE WHEN p IS NOT NULL THEN {
      sku: p.sku,
      quantity: line.quantity
    } END
  ) AS items
ORDER BY createdAt DESC, orderId DESC;
```

`WITH ... ORDER BY ... LIMIT` giới hạn **node đơn hàng** trước khi mở rộng `HAS_LINE`. Kết quả tương ứng tối đa `$limit` đơn hàng (giả sử không có dữ liệu vi phạm mô hình khiến một đơn gắn nhiều lần với khách), mỗi đơn có danh sách items.

Lưu ý:

- `LIMIT` ở trang đơn hàng **không giới hạn số dòng hàng bên trong một đơn**. Nếu một đơn có 100.000 dòng thì `collect` vẫn có thể dùng nhiều bộ nhớ.
- `ORDER BY` trước `LIMIT` có thể cần xem xét/sort nhiều đơn nếu plan không tận dụng thứ tự index; chỉ số đầu ra nhỏ **không đảm bảo chi phí đọc nhỏ**.
- Nếu cần thứ tự items, thêm bước sắp xếp phù hợp trước `collect` và kiểm tra plan; `ORDER BY` cuối cùng chỉ sắp xếp **các đơn**.
- Nếu dữ liệu đồng thời được thêm/sửa, nhiều request phân trang không mặc nhiên tạo một snapshot nhất quán của toàn bộ danh sách.

## 7. Khi danh sách rất lớn: offset và keyset pagination

### 7.1. Offset bằng `SKIP`

```cypher
MATCH (o:ShopOrder {
  tenantId: $tenantId,
  customerId: $customerId
})
RETURN o.orderId AS orderId,
       o.createdAt AS createdAt
ORDER BY createdAt DESC, orderId DESC
SKIP $skip
LIMIT $limit;
```

Cách này đơn giản cho trang gần đầu. Tuy nhiên, một trang có `SKIP 500000` có thể buộc engine xem xét rất nhiều ứng viên trước khi lấy trang tiếp theo. Khi có thêm/xóa đơn giữa các lần gọi, offset dễ khiến người dùng thấy **trùng hoặc bỏ sót** item.

### 7.2. Keyset (seek) pagination

Dùng cặp giá trị cursor của bản ghi cuối trang trước: `(createdAt, orderId)`. Với thứ tự giảm dần, trang kế tiếp chỉ lấy những bản ghi nhỏ hơn cursor theo thứ tự từ điển:

```cypher
MATCH (o:ShopOrder {
  tenantId: $tenantId,
  customerId: $customerId
})
WHERE o.createdAt < datetime($cursorTime)
   OR (
      o.createdAt = datetime($cursorTime)
      AND o.orderId < $cursorOrderId
   )
RETURN o.orderId AS orderId,
       o.createdAt AS createdAt,
       o.status AS status
ORDER BY createdAt DESC, orderId DESC
LIMIT $limit;
```

Ví dụ cursor được tạo từ bản ghi cuối trang trước:

```json
{
  "tenantId": "t1",
  "customerId": "c1",
  "cursorTime": "2026-10-04T11:00:00+07:00",
  "cursorOrderId": "o102",
  "limit": 20
}
```

Trang đầu không dùng `WHERE` cursor; ứng dụng nên có **hai câu query** riêng cho trang đầu/trang tiếp, giúp điều kiện rõ và planner dễ tối ưu hơn một truy vấn đầy `OR $cursor IS NULL`.

Điểm cần bảo đảm:

- `orderId` là **tie-breaker** duy nhất trong phạm vi tenant/khách theo mô hình. Nếu không, hai đơn có cùng `createdAt` có thể bị bỏ sót.
- Cursor phải được kiểm soát/định dạng ở server; không đưa input người dùng trực tiếp vào chuỗi Cypher.
- Keyset thường tránh chi phí bỏ qua offset sâu và giảm lỗi trùng/bỏ sót do thêm dữ liệu **trước cursor**, nhưng **không phải snapshot isolation giữa nhiều request**. Thay đổi khóa sắp xếp, xóa hoặc đổi trạng thái vẫn có thể thay đổi kết quả.
- Với `createdAt` và `orderId` dạng dữ liệu tương thích, xem `PROFILE` để kiểm tra index có giúp điều kiện và thứ tự không; predicate nhiều nhánh `OR` có thể thay đổi lựa chọn của planner.

## 8. Tránh nhân bội dòng với nhiều nhánh một-nhiều

Giả sử cần hiển thị **số đơn hàng** và **số sản phẩm yêu thích** của khách hàng. Nếu nối cả hai nhánh cùng lúc:

```cypher
// Dễ làm số dòng phình to theo tích hai nhánh:
MATCH (c:ShopCustomer {tenantId: $tenantId, customerId: $customerId})
OPTIONAL MATCH (c)-[:PLACED]->(o:ShopOrder)
OPTIONAL MATCH (c)-[:FAVORITED]->(p:ShopProduct)
RETURN c.customerId,
       count(o) AS orderCount,
       count(p) AS favoriteCount;
```

Nếu khách có 10 đơn và 5 sản phẩm yêu thích, luồng trung gian có thể thành **50 dòng**. `count(o)` và `count(p)` đều có thể bị phóng đại, không chỉ chậm mà còn **sai về nghiệp vụ**.

Trong Cypher 5.23+, sử dụng **subquery với variable scope** để tổng hợp mỗi nhánh độc lập:

```cypher
MATCH (c:ShopCustomer {tenantId: $tenantId, customerId: $customerId})
CALL (c) {
  MATCH (c)-[:PLACED]->(o:ShopOrder)
  RETURN count(o) AS orderCount
}
CALL (c) {
  MATCH (c)-[:FAVORITED]->(p:ShopProduct)
  RETURN count(p) AS favoriteCount
}
RETURN c.customerId AS customerId, orderCount, favoriteCount;
```

Hai câu `count` được tính trên từng nhánh riêng, tránh tích Descartes. Dạng này trả `0` cho nhánh không có bản ghi trong ngữ cảnh aggregation không grouping. Nếu chạy Neo4j/Cypher cũ hơn, dùng cú pháp `CALL { WITH c ... }` phù hợp phiên bản.

**`count(DISTINCT o)` có thể sửa số đếm nhưng chưa chắc sửa hiệu năng**, vì tích dòng đã xuất hiện trước khi khử trùng. Khi có hai nhánh độc lập, subquery phân tách thường làm ý định rõ hơn.

## 9. Thiết kế đúng các truy vấn tổng hợp và tìm đường đi

### 9.1. Top sản phẩm bán chạy là use case đọc toàn bộ *tập phù hợp*

```cypher
MATCH (o:ShopOrder {tenantId: $tenantId, status: 'PAID'})
WHERE o.createdAt >= datetime($from)
  AND o.createdAt < datetime($to)
MATCH (o)-[line:HAS_LINE]->(p:ShopProduct {tenantId: $tenantId})
WITH p.sku AS sku, p.title AS title,
     sum(line.quantity) AS unitsSold
RETURN sku, title, unitsSold
ORDER BY unitsSold DESC, sku
LIMIT $top;
```

Query này không lấy “toàn bộ graph”, mà xử lý **các đơn đã thanh toán của một tenant trong một khoảng ngày**. Dù chỉ trả top 10, engine vẫn có thể phải đọc và tính tổng cho **rất nhiều dòng** trước khi có thể xếp hạng.

Nếu dashboard được gọi rất thường xuyên trên hàng trăm triệu dòng, cân nhắc **read model tổng hợp theo ngày/tháng hoặc theo SKU**, cập nhật từ quy trình ghi/sự kiện với chính sách độ trễ và đối soát rõ ràng. Đây là một lựa chọn **denormalization cho use case**, không phải thay thế bất kỳ báo cáo chi tiết nào.

### 9.2. Truy vấn đường đi cần loại, hướng và độ sâu

Dạng truy vấn nguy hiểm khi graph lớn:

```cypher
// Tránh mở rộng vô hạn nếu không thật sự cần:
MATCH p = (a)-[*]-(b)
RETURN p;
```

Duyệt đường đi với độ dài không giới hạn và không xác định điểm neo có thể tạo khối lượng path rất lớn; với graph giàu chu trình số ứng viên tăng nhanh.

Nếu bài toán là **“tìm tối đa ba bước quan hệ hợp lệ từ một khách hàng đã xác thực”**, thiết kế pattern ràng buộc rõ:

```cypher
MATCH (c:ShopCustomer {
  tenantId: $tenantId,
  customerId: $customerId
})
MATCH p = (c)-[:REFERRED_TO*1..3]->(other:ShopCustomer)
WHERE other.tenantId = $tenantId
RETURN other.customerId AS relatedCustomer, length(p) AS hops
ORDER BY hops, relatedCustomer
LIMIT 50;
```

Ví dụ `REFERRED_TO` là quan hệ **minh họa**, không có trong dữ liệu đơn hàng ở trên. Trước khi dùng production:

- Quy định `max depth` hợp lý, loại và chiều relationship rõ.
- Kiểm tra các node **trung gian** cũng thuộc tenant nếu graph hỗn hợp tenant; chỉ kiểm tra node cuối không đủ để bảo đảm đường đi không băng qua dữ liệu tenant khác.
- Phân biệt mục tiêu **trả mọi path** với mục tiêu **trả các node duy nhất** hoặc **một đường đi ngắn nhất**. Có nhiều path tới cùng một node; `LIMIT` cuối không ngăn mọi thao tác mở rộng phía trước.
- Sử dụng cú pháp đường đi có giới hạn đúng phiên bản Cypher đang triển khai, hoặc thuật toán GDS chuyên biệt khi yêu cầu.

**Use case định nghĩa search space**, không phải sử dụng cú pháp `*` rộng nhất có thể rồi hy vọng `LIMIT` bảo vệ mọi tài nguyên.

## 10. Thiết kế index, constraint và cách truy cập theo thứ tự selectivity

Index giúp tìm **điểm bắt đầu**, còn traversal dùng liên kết graph. Một query hiệu quả thường cần cả hai.

| Kiểu use case | Điểm neo và điều kiện | Công cụ liên quan | Cần kiểm tra |
| --- | --- | --- | --- |
| Xem đơn theo mã | `ShopOrder(tenantId, orderId)` | Uniqueness constraint/index | `NodeIndexSeek`, số dòng đầu vào gần 1 |
| Danh sách đơn của khách | `ShopOrder(tenantId, customerId)` + thứ tự ngày | Composite range index hoặc traversal từ `Customer` | Planner dùng index/order hay mở rộng quan hệ quá nhiều |
| Tìm khách theo mã | `ShopCustomer(tenantId, customerId)` | Composite uniqueness constraint | Có ràng buộc đúng tenant/customer |
| Tìm sản phẩm theo tên | `ShopProduct.title` | Text/full-text index tùy nghĩa truy vấn | `CONTAINS` khác full-text token search |
| Tìm điểm giao nhận gần khách | Thuộc tính `POINT` + bán kính | Point index | CRS, khoảng cách, số node được lọc |
| Tìm top sản phẩm bán chạy | Tenant/trạng thái/thời gian, aggregate | Range index hoặc read model | Chi phí đọc dòng trước `ORDER BY ... LIMIT` |
| Duyệt mạng đề xuất | Node neo, loại/hướng quan hệ, depth | Index và traversal/GDS khi phù hợp | Fan-out, cycle, uniqueness, tenant boundary |

Các chỉ mục không tự giúp mọi predicate:
- Một index trên `o.createdAt` chưa chắc tối ưu truy vấn lọc đồng thời theo tenant và customer.
- Composite index thường có lợi khi các thuộc tính đầu được ràng buộc rõ; dùng `EXPLAIN` thay vì dự đoán plan chỉ từ thứ tự cột.
- Query trả mỗi đơn cùng tất cả sản phẩm vẫn phải duyệt tất cả relationship liên quan đến đơn, dù node ban đầu được tìm bằng index.
- Uniqueness constraint bảo đảm khóa không trùng, khác với chỉ có range index cho tốc độ.

## 11. Thiết kế API Java Driver: trả DTO gọn, không gom toàn bộ graph

### 11.1. Ví dụ endpoint danh sách đơn

Giả sử tầng ứng dụng đã xác thực người dùng và xác định `tenantId`, `customerId` từ danh tính/authorization; cũng đã tạo một đối tượng `Driver driver` dùng chung.

```java
import java.time.ZonedDateTime;
import java.util.List;
import java.util.Map;

import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

record OrderSummary(
    String orderId,
    ZonedDateTime createdAt,
    String status
) {}

static List<OrderSummary> findOrders(
        Driver driver,
        String tenantId,
        String customerId,
        int requestedLimit) {

    int pageSize = Math.max(1, Math.min(requestedLimit, 50));

    String cypher = """
        MATCH (o:ShopOrder {
          tenantId: $tenantId,
          customerId: $customerId
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
            tx.run(cypher, Map.of(
                "tenantId", tenantId,
                "customerId", customerId,
                "limit", pageSize
            )).list(record -> new OrderSummary(
                record.get("orderId").asString(),
                record.get("createdAt").asZonedDateTime(),
                record.get("status").asString()
            ))
        );
    }
}
```

Với tối đa 50 dòng, `list()` là lựa chọn hợp lý. Kết quả được tiêu thụ **trong transaction**, rồi session được đóng. Cần xác thực/ủy quyền tenant và customer ở tầng API, không nhận hai giá trị này như khóa truy cập đáng tin cậy chỉ vì được truyền dưới dạng parameter.

**Không viết:**

```java
// Anti-pattern cho endpoint có dữ liệu lớn:
var allRecords = session.run("MATCH (n) RETURN n").list();
// Sau đó mới tìm orderId, lọc tenant và dựng JSON trong Java.
```

Đoạn đó đưa phần việc vốn thuộc database sang Java, kéo theo I/O, heap và rủi ro phân quyền không cần thiết.

### 11.2. Kết quả lớn: stream có kiểm soát

Java Driver cung cấp cách tiêu thụ `Result` theo từng record, thay vì bắt buộc gọi `list()`. Ví dụ mô tả khi xuất báo cáo một tenant:

```java
try (Session session = driver.session(
        SessionConfig.forDatabase("neo4j"))) {

    session.executeReadWithoutResult(tx -> {
        var result = tx.run(
            """
            MATCH (o:ShopOrder {tenantId: $tenantId})
            RETURN o.orderId AS orderId
            ORDER BY orderId
            """,
            Map.of("tenantId", "t1")
        );

        while (result.hasNext()) {
            var record = result.next();
            // Ghi từng dòng đến sink có backpressure/buffer giới hạn.
            System.out.println(record.get("orderId").asString());
        }
    });
}
```

Đoạn minh họa này không gom toàn bộ output vào một `List`, nhưng vẫn có **một transaction đọc kéo dài**; với hàng triệu bản ghi, cần cân nhắc chia thành nhiều batch/keyset page, giới hạn timeout và khối lượng ghi ra sink. Callback của managed transaction có thể retry khi lỗi transient, nên **không đưa side effect không idempotent** (ví dụ gửi dòng ra hệ thống ngoài) vào callback rồi giả định nó chỉ chạy một lần.

Khi xuất dữ liệu thật, một job phân lô riêng thường an toàn hơn endpoint người dùng giữ kết nối HTTP trong thời gian dài. “Streaming” ở client không tự biến một truy vấn full scan thành truy vấn rẻ trên server.

### 11.3. Chi phí round-trip

Ứng dụng có thể chậm không chỉ vì DB Hits mà còn vì:

- 20 query lấy 20 nhóm sản phẩm (**N+1**).
- 20 lần xin connection và trao đổi Bolt.
- Query trả quá nhiều thuộc tính, JSON lớn, serialization tốn CPU.
- Mỗi query thực thi transaction riêng khiến phiên làm việc dài hoặc khóa bị giữ.
- Controller đợi tất cả dữ liệu rồi mới trả response.

Chọn **một query trả đúng shape** hoặc **một số query theo batch** có chủ đích; dùng Java Driver sync, async hoặc reactive tùy stack ứng dụng, nhưng vẫn phải viết đúng Cypher.

## 12. Spring Data Neo4j: entity mapping không thay thiết kế read model

Spring Data Neo4j giúp ánh xạ node/relationship thành object và quản lý transaction, nhưng **một màn hình đọc không nhất thiết cần tải đầy đủ cây entity**.

Có ba cách phổ biến:

| Nhu cầu | Hướng thiết kế |
| --- | --- |
| Cập nhật aggregate nhỏ có ranh giới rõ | Entity và `Neo4jRepository`/template |
| Endpoint danh sách, filter và phân trang | `@Query` trả projection/DTO phù hợp hoặc `Neo4jClient` |
| Dashboard thống kê, dữ liệu phẳng | Custom Cypher trả scalar/map/DTO, tránh hydrate entity graph không cần thiết |

Ví dụ dạng custom query trong repository (minh họa):

```java
interface OrderReadRepository
        extends org.springframework.data.repository.Repository<
            ShopOrderEntity, String> {

    @org.springframework.data.neo4j.repository.query.Query("""
        MATCH (o:ShopOrder {
          tenantId: $tenantId,
          customerId: $customerId
        })
        RETURN o.orderId AS orderId,
               o.status AS status
        ORDER BY o.createdAt DESC, o.orderId DESC
        LIMIT $limit
        """)
    java.util.List<OrderSummaryProjection> findSummaries(
        String tenantId,
        String customerId,
        long limit
    );
}
```

Với projection interface `OrderSummaryProjection` chứa `getOrderId()` và `getStatus()`, **cần kiểm tra khả năng ánh xạ scalar/projection ở phiên bản Spring Data Neo4j thực dùng**. Khi cần cấu trúc DTO phức tạp hoặc nhiều nhánh `collect`, dùng `Neo4jClient` với mapping chủ động để tránh giả định rằng mọi map lồng nhau đều được repository tự động bind đúng.

Lưu ý:

- `@Relationship` trong entity có thể gây tải graph vượt nhu cầu nếu repository trả aggregate lớn. Quan sát query do framework sinh ra khi hiệu năng quan trọng.
- Đừng gắn một mối quan hệ “rất nhiều” vào entity rồi luôn gọi `findById` chỉ để lấy 2–3 thuộc tính.
- Tách **write model** (toàn vẹn nghiệp vụ) và **read model** (trả dữ liệu cho use case) khi hai loại nhu cầu khác nhau rõ rệt.
- Trong reactive service, dùng `ReactiveNeo4jClient`/repository reactive phù hợp; không gọi repository blocking trên event loop rồi kỳ vọng luồng không bị chặn.
- Nếu tự dùng `Driver` trực tiếp trong service, transaction đó không tự tham gia transaction Spring Data Neo4j chỉ vì phương thức gọi mang `@Transactional`; cần thiết kế ranh giới giao dịch rõ.

## 13. Bảo mật và giới hạn truy vấn là phần của thiết kế use case

### 13.1. Giới hạn tenant ở bước truy cập đầu tiên

Đừng xây một query đi từ `MATCH (o:ShopOrder)` rồi lọc quyền ở Java. Thay vào đó:

- Đặt `tenantId` trong pattern/`WHERE` của Neo4j.
- Dùng `customerId` được ràng buộc với người dùng hiện tại hoặc xác thực truy cập đơn.
- Kiểm soát relationship giữa các tenant; nếu graph cho phép mối quan hệ xuyên tenant, kiểm tra **mọi node/edge trung gian** trong các path nhạy cảm.
- Dùng quyền Neo4j phù hợp (RBAC, database access, mô hình bảo vệ dữ liệu) như tầng phòng thủ bổ sung.

**Không coi `LIMIT 20` là biện pháp phân quyền.** Nó chỉ hạn chế đầu ra; một query chưa lọc tenant vẫn có thể trả 20 đơn không thuộc quyền xem.

### 13.2. Không để API cho phép truy vấn graph tùy ý

Những tham số nên được kiểm soát ở ứng dụng:

| Tham số | Giới hạn đề xuất theo use case |
| --- | --- |
| `limit` | Ngưỡng nhỏ với trang tương tác, ví dụ `1..50` |
| `maxDepth` | Giới hạn hữu hạn, phù hợp bài toán; không lấy từ input không kiểm tra |
| `sortBy` | Allowlist các cột/property hợp lệ, không nối Cypher từ chuỗi tự do |
| Khoảng thời gian | Max range; tránh truy vấn quét nhiều năm khi UI cần một tháng |
| Filter/labels/types | Chỉ cho phép schema đã định nghĩa, tránh xây pattern tùy ý từ input |
| Timeout | Đặt ở tầng API/driver/transaction phù hợp SLO |
| Page cursor | Kiểm tra chữ ký/kiểu và đảm bảo thuộc user/tenant/query tương ứng |

Một số thành phần cú pháp Cypher như label hoặc property name **không thể thay trực tiếp bằng value parameter trong mọi ngữ cảnh**. Nếu ứng dụng bắt buộc hỗ trợ sort động, hãy dùng **allowlist ở Java**, không nhúng raw input vào chuỗi query.

### 13.3. Quá tải và đồng thời

Một query “đúng logic” vẫn có thể gây quá tải khi 1.000 user gọi đồng thời, mỗi query duyệt hàng triệu quan hệ. Phải có:

- Rate limit/concurrency limit.
- Connection pool phù hợp và timeout.
- Chỉ số p50/p95/p99, DB Hits, Rows, CPU, page cache.
- Giới hạn dữ liệu và số lượng query từ một request.
- Cache/read model cho use case được truy vấn liên tục mà ít thay đổi.

## 14. Dùng `EXPLAIN` và `PROFILE` để xác minh thiết kế

Chỉ xem kết quả đúng **chưa đủ**. Hãy kiểm tra đường truy cập:

```cypher
EXPLAIN
MATCH (o:ShopOrder {
  tenantId: $tenantId,
  customerId: $customerId
})
RETURN o.orderId, o.createdAt
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT $limit;
```

Sau đó đo trên database thử nghiệm hoặc tải được kiểm soát:

```cypher
PROFILE
MATCH (o:ShopOrder {
  tenantId: $tenantId,
  customerId: $customerId
})
RETURN o.orderId, o.createdAt
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT $limit;
```

**Đọc plan theo use case:**

1. **Leaf operator:** `NodeIndexSeek`, `NodeIndexScan` hay `NodeByLabelScan`? Planner có chọn index dự kiến không?
2. **Estimated Rows/Rows:** có bao nhiêu dòng phát sinh trước khi `LIMIT` và sau các bước `Expand`?
3. **DB Hits:** operator nào truy cập storage nhiều nhất? Đừng nhầm DB Hits với số I/O vật lý.
4. **Sort/Top:** `ORDER BY` có phải xử lý nhiều dòng hay tận dụng thứ tự index?
5. **Aggregation:** `collect`/`count` có gom quá nhiều dữ liệu hoặc che giấu fan-out?
6. **Trả kết quả:** payload/JSON có nhỏ và đúng contract API không?
7. **Tham số đại diện:** cả khách có 1 đơn và khách có 500.000 đơn, cả dữ liệu cache nóng/lạnh khi cần.

**Không suy rằng query “chỉ trả 20 dòng” thì đọc 20 node.** `ORDER BY`, aggregation và traversal có thể cần làm việc trên một tập rất lớn trước khi `LIMIT` được áp dụng. Việc thêm index chỉ hữu ích khi đúng predicate và planner thấy có lợi.

### Mẫu bảng đo trước/sau

| Chỉ số | Truy vấn tải rộng | Truy vấn theo use case |
| --- | --- | --- |
| Số node/relationship phải xem xét | Đo bằng `PROFILE` | Đo lại với điều kiện đã thu hẹp |
| `Rows` tại leaf/Expand | Nhiều hay ít? | Có giảm ở điểm đầu vào không? |
| `DB Hits` | Bao nhiêu? | Có giảm khi dùng index và traversal phù hợp không? |
| Kích thước response | MB/GB? | Chỉ field cần cho màn hình? |
| Latency p95 | Đo trong điều kiện cụ thể | Cải thiện thực tế bao nhiêu? |
| Heap Java | Có `list()` toàn bộ? | Giới hạn trang và DTO? |
| Kết quả nghiệp vụ | Có đúng quyền/tenant? | So khớp cùng contract |

Chỉ so sánh các query **cùng mục tiêu và cùng tập kết quả hợp lệ**. Một query quét tất cả đơn và một query chỉ lấy một trang không phải hai cách khác nhau để thực hiện **cùng một công việc**; cái cần đánh giá là liệu query có đáp ứng **đúng use case** hay không.

## 15. Khi nào “xử lý gần như toàn bộ graph” lại là đúng?

Nguyên tắc query theo use case **không đồng nghĩa cấm phân tích toàn graph**. Các tác vụ sau có thể cần quét/phân tích một phần lớn dữ liệu:

| Tác vụ | Công cụ/cách vận hành phù hợp |
| --- | --- |
| PageRank/Louvain/Connected Components trên mạng liên kết | Neo4j Graph Data Science; projection rõ, estimate bộ nhớ, batch/job riêng |
| Di chuyển dữ liệu một lần | `neo4j-admin database import full` hoặc import có kế hoạch |
| Xuất toàn bộ dữ liệu để backup/ETL | Backup/export/stream theo batch với giới hạn tài nguyên và quyền |
| Tính lại read model định kỳ | Job tổng hợp được điều phối, chia lô, có checkpoint/idempotency |
| Kiểm tra toàn vẹn dữ liệu quy mô lớn | Quy trình đối soát offline/ít tải, số liệu kiểm chứng, giám sát tài nguyên |

Điểm chung là: **đây là các use case chủ động cần xử lý phạm vi lớn** và có ngân sách thời gian/bộ nhớ/độ ưu tiên riêng. Không lấy một API tương tác của người dùng để âm thầm tải toàn bộ graph như một job phân tích.

## 16. Các lỗi thiết kế thường gặp

| Anti-pattern | Hậu quả | Cách thay thế |
| --- | --- | --- |
| `MATCH (n) RETURN n` rồi lọc trong Java | Quét dữ liệu, trả payload lớn, rủi ro lộ thông tin | Pattern theo ID/tenant/use case |
| `RETURN *` hoặc trả node/relationship không cần | Serialization và mapping quá mức | Trả scalar/map/DTO với field cần thiết |
| `MATCH p=(a)-[*]-(b)` không ràng buộc | Bùng nổ số đường đi | Neo node, loại/hướng relationship, giới hạn bước |
| `LIMIT` sau khi mở rộng nhiều dòng hàng | Trả sai số đơn, mất dữ liệu dòng | Phân trang **đơn hàng trước**, rồi expand |
| Một truy vấn dòng hàng cho **mỗi đơn** | N+1 round-trip | Batch/truy vấn gom nhóm khi phù hợp |
| Hai `OPTIONAL MATCH` độc lập một-nhiều | Nhân bội Rows và sai `count` | Subquery tổng hợp riêng |
| `SKIP` rất lớn | Tốn chi phí bỏ qua dòng, dễ lệch khi có write | Keyset/cursor pagination |
| Dùng property sao chép nhưng không duy trì | Đọc nhanh nhưng dữ liệu sai | Duy trì trong transaction và kiểm thử consistency |
| Thiếu constraint khóa nghiệp vụ | `MERGE`/ghi đồng thời có nguy cơ trùng | Uniqueness constraint |
| Dựa vào `LIMIT` như bảo vệ tài nguyên | Sort/aggregate/traversal vẫn có thể rất nặng | Thu hẹp từ đầu, đo profile, giới hạn depth/time |
| Tin user-supplied `tenantId` là đủ | Lỗ hổng horizontal access | Authorization từ identity và database policy |
| Trả entity graph lớn từ repository | Tăng heap, mapping và quan hệ không cần | Custom read query/projection |
| Dùng query tổng hợp nặng cho từng request | CPU, I/O và latency lớn | Pre-aggregate/read model có độ trễ chấp nhận |
| Chỉ nhìn số dòng cuối cùng | Bỏ qua Rows/DB Hits trung gian | `EXPLAIN`/`PROFILE` cả cây plan |

## 17. Checklist trước khi đưa một API dùng Neo4j lên production

1. **Contract:** endpoint cần gì, trường nào, có bắt buộc trả mọi relationship không?
2. **Authorization:** xác định tenant/customer/role từ identity đáng tin cậy, không từ input tùy ý.
3. **Graph shape:** xác định node bắt đầu, loại và chiều relationship, chiều sâu tối đa.
4. **Cardinality:** dự tính khách bình thường và khách high-degree; có nhánh một-nhiều nào nhân bội?
5. **Projection:** chỉ trả field cần thiết; không trả graph object nếu DTO đủ dùng.
6. **Pagination:** sắp xếp ổn định, giới hạn trang, chọn keyset nếu dữ liệu nhiều.
7. **Index & constraint:** key duy nhất, index theo truy vấn, không tạo tùy tiện.
8. **Transaction:** ranh giới đọc/ghi rõ, tránh N+1 và side effect không idempotent trong retry.
9. **Driver/SDN:** mỗi operation có session phù hợp, consume trong vòng đời transaction; không gom kết quả vô hạn vào heap.
10. **Hiệu năng:** chạy `EXPLAIN` và `PROFILE` trên mẫu đại diện, xem `Rows`, `DB Hits`, sort, memory và latency.
11. **An toàn vận hành:** timeout, connection pool, concurrency limit, quan sát production.
12. **Tính đúng:** thử tenant khác, ID sai, một đơn không có dòng, nhiều dòng, dữ liệu thêm/xóa trong lúc phân trang.

## 18. Bài tập thực hành

1. Thiết kế query cho màn hình “10 đơn mới nhất của khách `c1` trong tenant `t1`”; chỉ trả `orderId`, `createdAt` và `status`. Giải thích điểm neo và cách sort.
2. Viết endpoint chi tiết `o101` trả một đơn và dòng hàng bằng `OPTIONAL MATCH` + `collect`. Thử thay query bằng cách giới hạn `LIMIT 1` sau `MATCH` dòng hàng và giải thích vì sao có thể mất dòng.
3. Viết danh sách đơn có `LIMIT 20` bằng hai cách: traversal từ khách và truy vấn trực tiếp `ShopOrder(tenantId,customerId)`. Dùng `PROFILE` để đánh giá khi một khách có hàng trăm nghìn đơn.
4. Tạo một khách có 5 đơn và 7 relationship `FAVORITED`. So sánh count khi ghép hai `OPTIONAL MATCH` với count trong hai `CALL (c) { ... }`.
5. Xây keyset cursor theo `createdAt DESC, orderId DESC`; thử hai đơn có cùng thời điểm và giải thích vai trò của tie-breaker.
6. Một API trả top 5 SKU nhưng xử lý 100 triệu dòng hàng. Vì sao `LIMIT 5` không đủ để bảo đảm độ trễ thấp? Đề xuất read model tổng hợp.
7. Từ một graph có nhiều tenant, tìm một pattern 3 bước có thể băng qua tenant khác. Thiết kế kiểm soát tenant ở cả node trung gian.
8. Một Spring Data Neo4j entity có collection 100.000 relationship. Màn hình chỉ cần tên node và trạng thái. Đề xuất custom Cypher/DTO thay vì tải toàn aggregate.
9. Một export cần 10 triệu đơn. So sánh `Result.list()` với streaming theo batch/keyset; nêu cách không lặp side effect khi transaction retry.
10. Đưa ra checklist `EXPLAIN`/`PROFILE` cho một query dùng `ORDER BY ... LIMIT`: cần quan sát index, sort, Rows, DB Hits, heap và payload nào?

## 19. Ghi nhớ

- **Thiết kế từ ca sử dụng → khóa truy cập → pattern quan hệ → result shape → giới hạn → index → đo đạc**, không bắt đầu bằng `MATCH (n) RETURN n`.
- Dùng **khóa nghiệp vụ có constraint** để neo truy vấn, hướng và type relationship rõ ràng để giới hạn vùng graph.
- **Chỉ trả thuộc tính ứng dụng cần**; phân trang đúng đối tượng và tránh `LIMIT` cắt dở kết quả sau fan-out.
- Với nhiều quan hệ một-nhiều, chú ý **N+1**, **Cartesian product** và tổng hợp theo nhánh qua subquery.
- **Keyset pagination** hữu ích cho danh sách sâu, nhưng vẫn cần sắp xếp duy nhất và kiểm soát thay đổi đồng thời.
- **Index, constraint và read model** phải phục vụ ca sử dụng thực tế; property denormalized đòi hỏi duy trì nhất quán.
- **Java Driver/Spring Data Neo4j** không nên materialize cả graph chỉ để tạo một DTO; tránh N+1 và chú ý session/transaction.
- Dùng **`EXPLAIN`/`PROFILE`** để đo số dòng trung gian, truy cập storage, sorting và hiệu năng. `LIMIT` ở cuối không bảo đảm query xử lý ít dữ liệu.
- **Toàn graph** chỉ hợp lý khi chính use case là phân tích, export, import hoặc đối soát trên phạm vi lớn, với tài nguyên và cơ chế vận hành riêng.

### Tài liệu tham khảo chính thức

- [Neo4j Cypher Manual — Query tuning](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/query-tuning/)
- [Neo4j Cypher Manual — Execution plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/)
- [Neo4j Cypher Manual — MATCH](https://neo4j.com/docs/cypher-manual/current/clauses/match/)
- [Neo4j Cypher Manual — WITH](https://neo4j.com/docs/cypher-manual/current/clauses/with/)
- [Neo4j Cypher Manual — ORDER BY](https://neo4j.com/docs/cypher-manual/current/clauses/order-by/)
- [Neo4j Cypher Manual — LIMIT](https://neo4j.com/docs/cypher-manual/current/clauses/limit/)
- [Neo4j Cypher Manual — CALL subqueries](https://neo4j.com/docs/cypher-manual/current/subqueries/call-subquery/)
- [Neo4j Cypher Manual — Create indexes](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/create-indexes/)
- [Neo4j Java Driver Manual — Simple queries](https://neo4j.com/docs/java-manual/current/query-simple/)
- [Neo4j Java Driver Manual — Transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Spring Data Neo4j — Reference](https://docs.spring.io/spring-data/neo4j/reference/)
- [Neo4j GDS — Graph projection](https://neo4j.com/docs/graph-data-science/current/management-ops/graph-creation/graph-project/)
