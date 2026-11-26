# Đọc `EXPLAIN` và đối chiếu kế hoạch với mẫu truy vấn trong Spring Data Couchbase

Một ứng dụng có thể đã tạo nhiều secondary index cho Couchbase nhưng truy vấn repository vẫn chậm. Nguyên nhân có thể là Query Service chọn index khác dự tính, index chỉ dùng được khóa đầu, vẫn phải đọc quá nhiều document bằng `Fetch`, phải sắp xếp ngoài index hoặc đơn giản là SQL++ phát sinh từ Spring Data không giống câu lệnh đang được thử trong Query Workbench.

**`EXPLAIN`** trả về kế hoạch thực thi do bộ tối ưu SQL++ lập cho một truy vấn. Nó giúp trả lời câu hỏi *“Couchbase định dùng đường truy cập dữ liệu nào, lọc và sắp xếp ở đâu?”*. Tuy nhiên, một kế hoạch trông hợp lý không tự chứng minh truy vấn chạy nhanh; muốn biết chi phí thực tế phải kết hợp **Query Profile và số liệu trên workload đại diện**.

Bài thuộc chương **Chỉ mục** của module **SPRING_DATA_COUCHBASE**. Trọng tâm là đọc và đối chiếu `EXPLAIN` với mẫu truy vấn thực do document mapping, repository, `@Query` hoặc `CouchbaseTemplate` tạo ra. Kiến thức liên hệ với bucket/scope/collection, composite/partial/array/covering index, TTL, CAS, giao dịch, API reactive và scan consistency để tối ưu chính xác mà vẫn giữ tính nhất quán và khả năng vận hành.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Chạy `EXPLAIN` trên SQL++ và đọc cây operator từ đường quét index đến phép lọc, lấy document, sắp xếp, giới hạn và tạo kết quả.
2. Xác định index đang được chọn, **keyspace** thực tế, các `spans` trên khóa index và điều kiện còn phải xử lý sau scan.
3. Phân biệt **index khả dụng**, **index scan chọn lọc**, **covering index** và **index hỗ trợ `ORDER BY`/`LIMIT`**.
4. Dự đoán tác động của điều kiện bằng, khoảng, `IN`, khóa dẫn đầu, `ANY`/`UNNEST` và truy vấn có `JOIN` lên kế hoạch.
5. Đối chiếu câu SQL++ từ Spring Data Couchbase với kế hoạch, đo Query Profile, phát hiện regression và quyết định có cần đổi index hay viết lại truy vấn.

## 2. Bắt đầu từ workload, không bắt đầu từ danh sách index

Giả sử hệ thống bán hàng dùng bucket `commerce`, scope `sales` và collection `orders`. Một document:

```json
{
  "_class": "salesOrder",
  "tenantId": "TENANT-A",
  "customerId": "C-42",
  "status": "PAID",
  "createdAt": "2026-11-20T08:15:00Z",
  "total": 1500000,
  "currency": "VND",
  "deleted": false,
  "items": [
    { "sku": "SKU-42", "quantity": 2 },
    { "sku": "SKU-18", "quantity": 1 }
  ]
}
```

Trong ví dụ, `_class` là discriminator của entity, có thể được lưu dưới alias hoặc tên Java class đầy đủ tùy cấu hình Spring Data; `createdAt` là chuỗi ISO-8601 UTC đã chuẩn hóa. Với mapping `Instant` thực tế, cần kiểm tra JSON mà converter ghi ra trước khi suy luận về chỉ mục theo thời gian.

Hệ thống có bốn endpoint:

| Endpoint | Truy vấn trọng tâm | Điều kiện/SLA cần quan sát |
| --- | --- | --- |
| A. Danh sách đơn theo trạng thái | `tenantId = ? AND status = ? ORDER BY createdAt DESC LIMIT 20` | Đọc thường xuyên, độ trễ danh sách thấp |
| B. Toàn bộ đơn gần đây của tenant | `tenantId = ? ORDER BY createdAt DESC LIMIT 20` | Không cố định `status` |
| C. Tra cứu đơn theo SKU | `tenantId = ? AND ANY item IN items ...` | Lọc trong mảng JSON |
| D. Đọc đơn theo document ID | `findById(id)` | Truy cập KV, không dùng SQL++ index |

Từ cùng một collection, các endpoint có **đường truy cập tối ưu khác nhau**. Không thể kết luận “index ghép có nhiều khóa nhất là tốt nhất” trước khi biết mẫu điều kiện, projection, phân bố dữ liệu và tần suất truy vấn.

Để thực hành, tạo các index **ứng viên** dưới đây trong môi trường riêng được phép quản lý DDL:

```sql
-- Ứng viên cho endpoint A
CREATE INDEX ix_orders_tenant_status_created
ON `commerce`.`sales`.`orders`(
    `tenantId`, `status`, `createdAt` DESC
);

-- Ứng viên cho endpoint B
CREATE INDEX ix_orders_tenant_created
ON `commerce`.`sales`.`orders`(
    `tenantId`, `createdAt` DESC
);

-- Ứng viên cho endpoint C
CREATE INDEX ix_orders_tenant_item_sku
ON `commerce`.`sales`.`orders`(
    `tenantId`,
    DISTINCT ARRAY i.sku FOR i IN items END
);
```

Không mặc định nên giữ cả ba index trên production. Chúng chỉ minh họa các cách đánh index cho ba mẫu đọc; phải đo lợi ích và chi phí duy trì trước khi quyết định.

## 3. Chạy `EXPLAIN` đúng câu SQL++ cần chẩn đoán

### 3.1. Cú pháp cơ bản

Ví dụ cho endpoint A:

```sql
EXPLAIN
SELECT META(o).id AS orderId,
       o.tenantId, o.status, o.createdAt, o.total
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = "TENANT-A"
  AND o.status = "PAID"
ORDER BY o.createdAt DESC
LIMIT 20;
```

`EXPLAIN` giúp xem kế hoạch mà optimizer xây dựng, **không phải báo cáo thời gian thực thi của toàn bộ truy vấn trên dữ liệu thực**. Nó không thể thay thế việc chạy truy vấn có profiling để đo số entry đã quét, số document đã fetch và thời gian từng operator.

Khi đối chiếu giữa các phương án, phải giữ các yếu tố liên quan **nhất quán**:

- Cùng cụm/môi trường, phiên bản Couchbase và keyspace `commerce.sales.orders`.
- Cùng SQL++, predicate, projection, `ORDER BY`, `LIMIT`, tham số hoặc giá trị đại diện.
- Cùng trạng thái build của index; xác nhận index mới thực sự `online`.
- Kiểm soát thay đổi về thống kê, phân bố dữ liệu và index khác đang tồn tại.

Đổi `SELECT` từ một projection 5 trường sang `SELECT o.*` có thể thêm `Fetch`. Đổi `status = "PAID"` sang `status IN ["PAID", "SHIPPED"]` có thể thay đổi khả năng tận dụng `ORDER BY`. Đổi `FROM` sang collection khác khiến mọi so sánh index theo collection cũ không còn phù hợp.

### 3.2. Tên keyspace trong `FROM` là một phần của chẩn đoán

Ưu tiên đường dẫn ba phần:

```sql
FROM `commerce`.`sales`.`orders` AS o
```

đặc biệt khi chạy `EXPLAIN` thủ công hoặc viết migration. Câu `FROM orders` có thể phụ thuộc query context hiện hành. Index ở `commerce.archive.orders` không dùng để phục vụ `commerce.sales.orders` dù hai collection cùng tên `orders`.

Nếu ứng dụng dùng context riêng, hãy đọc context runtime và đối chiếu với `FROM` thực. Không chẩn đoán “optimizer không chọn index” khi thực tế đang đọc **sai keyspace**.

### 3.3. Tham số và prepared statement

Spring Data Couchbase thường dùng tham số thay vì nối giá trị từ người dùng vào SQL++. Ví dụ `tenantId = $1 AND status = $2` trong một truy vấn `@Query`. Khi debug, cần kiểm tra dạng SQL++ thực cùng giá trị bind đại diện và cách câu lệnh được chuẩn bị/thực thi.

Đặc biệt, một partial index `WHERE status = "OPEN"` có thể không phù hợp cho một prepared query dùng `status = $status` với giá trị có thể thay đổi qua các lần gọi. Một câu `EXPLAIN` viết tay với literal `"OPEN"` không nhất thiết chứng minh prepared query trong ứng dụng sẽ dùng cùng index.

## 4. Đọc cấu trúc cây kế hoạch SQL++

Kết quả `EXPLAIN` thông thường chứa thông tin JSON về các operator. Một số phiên bản có khóa như `#operator`, `~children`, `~child`, `index`, `keyspace`, `spans` hoặc `covers`. Tên và cấu trúc JSON có thể thay đổi theo phiên bản Couchbase, loại toán tử và cách Query Service biểu diễn execution plan.

Một chuỗi xử lý **mang tính minh họa, không phải output nguyên văn**:

```text
Sequence
  -> IndexScan3(index = ix_orders_tenant_status_created)
       spans = tenantId "TENANT-A", status "PAID"
  -> Fetch(orders)           [nếu SELECT/Filter cần trường ngoài index]
  -> Filter(...)             [nếu còn điều kiện phải kiểm tra]
  -> Order(createdAt DESC)   [nếu không tận dụng được thứ tự index]
  -> InitialProject(...)
  -> Limit(20)
```

Một số operator có thể được đẩy vào index scan hoặc không xuất hiện nếu không cần thiết. `Sequence`, `Parallel` hoặc các toán tử bao bọc khác cho biết cách Query Service tổ chức bước xử lý; **không nên đọc cây từ trên xuống như một log thời gian từng bước**. Hãy xác định đường dữ liệu bắt đầu ở nguồn scan và theo luồng tới kết quả.

### 4.1. Bảng đọc nhanh những operator quan trọng

| Toán tử/dấu hiệu | Nó làm gì? | Câu hỏi cần hỏi |
| --- | --- | --- |
| `IndexScan`, `IndexScan3` | Quét secondary index (GSI) | Dùng index nào? Có thu hẹp đúng khóa không? |
| `PrimaryScan` hoặc biến thể primary scan | Quét từ primary index | Có đang quét rộng do thiếu index theo thuộc tính không? |
| `Fetch` | Lấy nội dung document gốc | Do thiếu trường trong index, hay cần đánh giá predicate/projection khác? |
| `Filter` | Lọc hàng theo điều kiện còn lại | Điều kiện nào chưa được đẩy vào index scan? |
| `Order` | Sắp xếp kết quả | Index có hỗ trợ `ORDER BY` hoặc cần sort ngoài? |
| `Offset` / `Limit` | Bỏ qua/giới hạn hàng | Chúng được áp dụng sớm hay sau bước xử lý rộng? |
| `InitialProject` / `FinalProject` | Tạo dữ liệu `SELECT` | Query thực trả ít trường hay cả entity? |
| `Distinct`, `Group` / `Aggregate` | Loại trùng, nhóm, tổng hợp | Index có giảm được số hàng trước các toán tử này không? |
| `Join` / `HashJoin` / `NestedLoopJoin` | Kết hợp các nguồn dữ liệu | Hai phía có index thích hợp, số hàng trung gian có tăng mạnh không? |
| `Unnest` | Mở rộng phần tử mảng thành hàng | Query đang tìm parent document hay cần từng phần tử? |
| `Union` / `Intersect` / `DistinctScan` | Kết hợp/loại trùng các đường scan theo kế hoạch | Có nhiều index tham gia? Đánh giá chi phí so với một index ghép |

Không phải mọi phiên bản đều dùng đúng tên như bảng. Quan trọng là **vai trò thực thi**, kết hợp với tên index, biểu thức và số liệu trên Query Profile.

### 4.2. `IndexScan` chỉ cho biết đang dùng index, chưa nói index tốt

Giả sử optimizer chọn `ix_orders_tenant_status_created`. Cần xem:

1. Scan có dùng được **`tenantId` và `status`** để giới hạn phạm vi không?
2. `createdAt` có được dùng cho khoảng hoặc sắp xếp không?
3. Có rất nhiều entry được đọc rồi bị `Filter` loại bỏ không?
4. Có cần `Fetch` nhiều document vì `SELECT` lấy thêm `total` hoặc metadata khác?
5. Có phải sort ngoài index trước khi lấy 20 hàng không?

Một plan có `IndexScan3` vẫn có thể chậm nếu quét hàng trăm nghìn entry để trả 20 kết quả; ngược lại, một index ngắn quét 20–30 entry và phải `Fetch` vài document có thể hoàn toàn chấp nhận được.

## 5. Đọc `spans`: điều kiện nào thật sự thu hẹp index?

`spans` hoặc phần mô tả phạm vi scan cho biết Query Service dự định đọc những dải giá trị nào trong index. Với secondary index ghép, đây là chỗ quan trọng để phân biệt **điều kiện viết trong `WHERE`** với **điều kiện có thể giới hạn dải index scan**.

### 5.1. Hai khóa bằng trước một khóa thời gian

Index:

```sql
CREATE INDEX ix_orders_tenant_status_created
ON `commerce`.`sales`.`orders`(
    `tenantId`, `status`, `createdAt` DESC
);
```

Truy vấn:

```sql
EXPLAIN
SELECT META(o).id AS orderId, o.createdAt
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = "TENANT-A"
  AND o.status = "PAID"
  AND o.createdAt >= "2026-11-01T00:00:00Z"
ORDER BY o.createdAt DESC
LIMIT 20;
```

Một kế hoạch tốt có thể thể hiện các điều kiện trên `tenantId`, `status` và phạm vi `createdAt` tại index scan. Logic tương ứng:

```text
Index key order: (tenantId, status, createdAt DESC)

tenantId = "TENANT-A"  -> nhóm tenant
status   = "PAID"      -> nhóm status của tenant
createdAt >= mốc      -> dải thời gian bên trong nhóm
```

Hai điều kiện bằng cố định tiền tố của index, còn khóa thời gian phục vụ range và thứ tự kết quả. **Thứ tự viết `AND` trong `WHERE` không cần trùng thứ tự index**: optimizer phân tích biểu thức để lập spans.

### 5.2. Thiếu khóa nằm giữa làm dải scan rộng hơn

So sánh:

```sql
EXPLAIN
SELECT META(o).id AS orderId, o.createdAt
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = "TENANT-A"
  AND o.createdAt >= "2026-11-01T00:00:00Z"
ORDER BY o.createdAt DESC
LIMIT 20;
```

Truy vấn này **không lọc `status`**. Với index `(tenantId, status, createdAt DESC)`, các entry của tenant được nhóm theo status trước khi theo thời gian. Vì vậy index chưa chắc thu hẹp được khoảng thời gian hay cung cấp đúng `createdAt DESC` cho **toàn tenant** như index `(tenantId, createdAt DESC)`.

Nếu `EXPLAIN` vẫn chọn index đầu tiên, hãy xem số entry quét và có `Order` hay không. Không nhầm **“index xuất hiện trong plan”** với **“index phù hợp nhất cho endpoint B”**.

### 5.3. `IN` không tương đương một giá trị bằng duy nhất khi sắp xếp

```sql
EXPLAIN
SELECT META(o).id AS orderId, o.status, o.createdAt
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = "TENANT-A"
  AND o.status IN ["PAID", "SHIPPED"]
ORDER BY o.createdAt DESC
LIMIT 20;
```

Index `(tenantId, status, createdAt DESC)` có thể giúp tìm hai nhóm status. Nhưng kết quả `createdAt DESC` **bên trong từng nhóm status** chưa phải thứ tự giảm dần trên **toàn bộ hai nhóm**. Một kế hoạch có thể cần sort bổ sung hoặc chiến lược hợp nhất phù hợp. Đọc `Order` và số hàng trung gian trước `Limit`.

### 5.4. Range không nên đặt trước mọi equality nếu workload chủ yếu lọc equality

Index ứng viên:

```sql
CREATE INDEX ix_orders_tenant_created_status
ON `commerce`.`sales`.`orders`(
    `tenantId`, `createdAt` DESC, `status`
);
```

Nó có thể phù hợp với endpoint chỉ lọc tenant + thời gian. Tuy nhiên, khi truy vấn có `tenantId = ? AND status = ? AND createdAt >= ?`, `status` đứng **sau** khóa range `createdAt`, nên thường không tạo cùng dải quét hẹp như `(tenantId, status, createdAt DESC)`.

Hãy đối chiếu `spans` và số entry thực tế, không kết luận chỉ từ số trường trùng nhau giữa index và `WHERE`.

## 6. Đọc `Fetch`, `Filter` và khả năng bao phủ dữ liệu

### 6.1. Vì sao có `Fetch` dù index đã lọc tốt?

Với index `(tenantId, status, createdAt DESC)`, truy vấn:

```sql
SELECT META(o).id AS orderId, o.createdAt, o.total, o.currency
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = "TENANT-A" AND o.status = "PAID"
ORDER BY o.createdAt DESC
LIMIT 20;
```

cần thêm `total` và `currency`. Hai trường đó chưa nằm trong index ví dụ, nên Query Service có thể phải lấy JSON gốc bằng `Fetch` để trả đủ projection.

Một index ứng viên cho endpoint danh sách đọc nhiều:

```sql
CREATE INDEX ix_orders_list_cover
ON `commerce`.`sales`.`orders`(
    `tenantId`,
    `status`,
    `createdAt` DESC,
    `total`,
    `currency`
);
```

Khi `SELECT`, `WHERE`, `ORDER BY` và các biểu thức khác có thể được giải quyết bằng dữ liệu trong index, kế hoạch có thể có `covers` và **không phải `Fetch`**. Đây là *covering index đối với truy vấn cụ thể*; không phải thuộc tính “cover mọi truy vấn” của index đó.

### 6.2. `Filter` không đồng nghĩa nhất định phải `Fetch`

Một toán tử `Filter` xử lý predicate chưa áp dụng được ngay tại scan. Nếu các giá trị cần lọc nằm trong index, `Filter` vẫn có thể làm việc trên giá trị đã được bao phủ mà không cần đọc document gốc.

Ngược lại, nếu query chứa một điều kiện trên field chưa có trong index, kế hoạch có thể phải `Fetch` trước khi lọc. Do đó, hãy xem đồng thời:

- `IndexScan` và `spans`: điều kiện nào đã thu hẹp index?
- `Filter`: còn điều kiện nào phải xét?
- `Fetch`: có lấy JSON gốc không?
- `covers` / `filter_covers`: index hoặc predicate của partial index đã cung cấp những biểu thức nào?

**Không coi việc còn `Filter` là thất bại tuyệt đối.** Đánh giá mức độ ảnh hưởng qua số hàng vào/ra từng toán tử và thời gian thực tế.

### 6.3. `SELECT *` và repository trả entity đầy đủ

`SELECT o.*` thường cần nhiều field của document, gồm object/mảng lớn mà index không lưu. Tương tự, một repository trả `SalesOrder` đầy đủ thường cần dữ liệu để ánh xạ các thuộc tính entity, có thể dẫn tới `Fetch`.

So sánh hai yêu cầu:

| Hợp đồng API | Truy vấn thường cần | Khả năng covering |
| --- | --- | --- |
| Màn hình list chỉ có ID, trạng thái, ngày, tổng tiền | Projection nhỏ | Có thể tạo index đủ trường |
| Trang chi tiết trả địa chỉ, `items`, metadata và toàn entity | Document hoàn chỉnh | Thường nên chấp nhận KV lookup theo ID hoặc `Fetch` khi query theo thuộc tính |

Đừng đưa toàn bộ mảng `items` vào index chỉ để bỏ `Fetch` cho trang chi tiết: index lớn có thể tốn nhiều tài nguyên hơn lợi ích đọc. Phương án **index để tìm document ID, sau đó đọc KV chi tiết khi người dùng mở một đơn** đôi khi hợp lý hơn.

### 6.4. Bộ lọc loại entity ảnh hưởng covering

Spring Data có thể thêm bộ lọc kiểu `_class` vào SQL++ để không ánh xạ nhầm document. Một SQL++ viết tay không có `_class` có thể được bao phủ, trong khi SQL++ thực của repository phải `Fetch` hoặc dùng index khác do bổ sung bộ lọc.

Nếu collection chứa nhiều loại entity và query luôn lọc `_class = "salesOrder"`, có thể thử partial index:

```sql
CREATE INDEX ix_orders_sales_list_cover
ON `commerce`.`sales`.`orders`(
    `tenantId`, `status`, `createdAt` DESC, `total`, `currency`
)
WHERE `_class` = "salesOrder";
```

Query phải hàm ý được predicate của partial index; giá trị `"salesOrder"` cần trùng **giá trị discriminator thực được lưu và điều kiện của repository**. Nếu runtime dùng tên class Java đầy đủ, index minh họa có thể không phù hợp. Dùng `EXPLAIN` tìm `filter_covers` và xác nhận không `Fetch` khi xét đúng SQL++.

## 7. Đọc `Order`, `Limit` và kế hoạch phân trang

### 7.1. Index sắp xếp tốt có thể tránh operator `Order`

Truy vấn endpoint A:

```sql
SELECT META(o).id AS id, o.createdAt
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = "TENANT-A"
  AND o.status = "PAID"
ORDER BY o.createdAt DESC
LIMIT 20;
```

Với index `(tenantId, status, createdAt DESC)`, hai khóa đầu được cố định bằng điều kiện bằng. `createdAt DESC` là thứ tự ở dải còn lại. Nếu optimizer dùng được thứ tự này, có thể không cần sort bổ sung.

Tuy vậy, việc có khóa `createdAt DESC` trong index **không bảo đảm** tất cả các truy vấn sắp xếp theo `createdAt DESC` đều bỏ `Order`. Truy vấn thiếu `status` hoặc lọc `status IN [...]` là các ví dụ cần kiểm tra riêng.

### 7.2. `LIMIT 20` không tự động khiến query rẻ

Nếu optimizer phải đọc 500.000 entry, lọc và sort rồi mới chọn 20 hàng, `LIMIT 20` ở cuối query không xoá đi công việc trước nó. Ngược lại, index vừa lọc vừa sắp xếp đúng có thể tạo điều kiện để giới hạn được áp dụng hiệu quả từ sớm.

Đọc trong plan:

1. Có operator `Order` ngoài index không?
2. `Limit` hoặc pushdown vào `IndexScan` diễn ra ở đâu?
3. Operator nào tạo ra lượng hàng trung gian lớn?
4. Query có `OFFSET` lớn khiến phải duyệt qua nhiều hàng trước khi trả trang hiện tại không?

Một index bao phủ mà vẫn phải sort hàng triệu entry có thể chậm hơn index khác lọc rất hẹp. Khi phân trang khối lượng lớn, cân nhắc **keyset pagination** theo thứ tự có khóa phụ ổn định nếu nghiệp vụ cho phép.

### 7.3. Thứ tự ổn định khi `createdAt` trùng

Nếu hai đơn có cùng `createdAt`, chỉ `ORDER BY createdAt DESC` không bảo đảm thứ tự tương đối ổn định. Với phân trang cursor, có thể cần thêm `META(o).id` làm khóa phụ:

```sql
SELECT META(o).id AS orderId, o.createdAt
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = "TENANT-A"
ORDER BY o.createdAt DESC, META(o).id DESC
LIMIT 20;
```

Khi đổi `ORDER BY`, cần kiểm tra `EXPLAIN` lại vì khả năng dùng thứ tự sẵn có từ index cũng có thể thay đổi. Đừng giả định `ORDER BY` có thêm khóa phụ luôn được index cũ hỗ trợ hoàn toàn.

## 8. Index theo mảng, `UNNEST` và những kế hoạch dễ đọc nhầm

### 8.1. `ANY` cần biểu thức array index tương thích

Yêu cầu: tìm các đơn thuộc tenant có SKU `SKU-42` trong mảng `items`:

```sql
EXPLAIN
SELECT META(o).id AS orderId
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = "TENANT-A"
  AND ANY item IN o.items
      SATISFIES item.sku = "SKU-42"
      END;
```

Index ứng viên:

```sql
CREATE INDEX ix_orders_tenant_sku
ON `commerce`.`sales`.`orders`(
    `tenantId`,
    DISTINCT ARRAY item.sku FOR item IN items END
);
```

Khi đọc plan, hỏi:

- Optimizer có chọn array index hay chỉ index trên `tenantId` rồi `Fetch` để kiểm tra mảng?
- Biểu thức `ANY` có tương thích với `DISTINCT ARRAY item.sku FOR item IN items END` không?
- Có một predicate `_class` hoặc `deleted` trong SQL++ từ Spring Data làm partial index không phù hợp không?
- Số document/entry scan và số hàng trả về thế nào?

Index thường chỉ giúp truy vấn **tìm đơn nào có item phù hợp**. Nếu `SELECT o.items`, Query Service vẫn có thể phải `Fetch` mảng đầy đủ.

### 8.2. `UNNEST` thay đổi cardinality

```sql
EXPLAIN
SELECT META(o).id AS orderId, i.sku, i.quantity
FROM `commerce`.`sales`.`orders` AS o
UNNEST o.items AS i
WHERE o.tenantId = "TENANT-A"
  AND i.sku = "SKU-42";
```

Với `UNNEST`, một document có nhiều item phù hợp có thể sinh nhiều hàng, khác `ANY` chỉ chọn parent document nếu tồn tại item thỏa. Array index theo `ALL ARRAY` và những kế hoạch `UNNEST` đủ điều kiện có thể hỗ trợ truy cập từng phần tử, nhưng không phải mọi `DISTINCT ARRAY` index đều đáp ứng mọi `UNNEST`.

Đọc plan cần phân biệt số document nguồn với **số hàng sau unnest**, rồi kiểm tra `Filter`, `Fetch` và phép nhóm/loại trùng. Nếu số hàng trung gian bùng nổ, chỉ tạo thêm một index chưa chắc giải quyết được lỗi thiết kế query hoặc nhu cầu trả dữ liệu ở sai cấp.

### 8.3. Hai `ANY` độc lập không có nghĩa cùng phần tử

Hai điều kiện:

```sql
WHERE ANY i IN o.items SATISFIES i.sku = "SKU-42" END
  AND ANY i IN o.items SATISFIES i.quantity >= 2 END
```

có thể được thỏa bởi **hai item khác nhau**. Nếu nghiệp vụ yêu cầu một item có cả SKU và quantity, phải dùng:

```sql
WHERE ANY i IN o.items
      SATISFIES i.sku = "SKU-42" AND i.quantity >= 2
      END
```

`EXPLAIN` giúp tối ưu query, **không thay thế kiểm thử tính đúng của ngữ nghĩa query**. Một kế hoạch rất nhanh nhưng trả sai tập document vẫn là lỗi nghiêm trọng.

## 9. Nhiều index, `JOIN` và khi kế hoạch trở nên phức tạp

### 9.1. Optimizer có thể chọn index khác dự đoán

Giả sử có:

```sql
CREATE INDEX ix_orders_status
ON `commerce`.`sales`.`orders`(`status`);

CREATE INDEX ix_orders_tenant
ON `commerce`.`sales`.`orders`(`tenantId`);

CREATE INDEX ix_orders_tenant_status
ON `commerce`.`sales`.`orders`(`tenantId`, `status`);
```

Với `WHERE tenantId = ? AND status = ?`, optimizer có thể chọn index ghép hoặc một đường truy cập khác dựa trên thống kê, phân bố dữ liệu và chi phí. Một số kế hoạch có thể kết hợp nhiều index bằng các phép hợp/giao; cách biểu diễn tùy phiên bản.

Đừng chỉ đếm số index trong `system:indexes`. Hãy xem index **được chọn**, dải quét và số entry đọc. Nếu nhiều index chồng lắp nhau, chi phí duy trì khi ghi có thể cao mà lợi ích đọc nhỏ.

### 9.2. `JOIN` đòi hỏi quan sát từng nguồn

Ví dụ collection `customers` cũng thuộc `commerce.sales` và đơn hàng tham chiếu bằng `customerId`:

```sql
EXPLAIN
SELECT META(o).id AS orderId, o.status, c.name AS customerName
FROM `commerce`.`sales`.`orders` AS o
JOIN `commerce`.`sales`.`customers` AS c
  ON o.customerId = META(c).id
WHERE o.tenantId = "TENANT-A"
  AND o.status = "PAID"
LIMIT 20;
```

Cần xác định:

- Bên `orders` được lọc bằng index gì, còn bao nhiêu hàng vào phép join?
- Bên `customers` được tra theo document ID (`JOIN ON KEYS`/key lookup trong mẫu phù hợp) hay theo field cần secondary index?
- Có toán tử `HashJoin`/`NestedLoopJoin` hay chiến lược join nào được chọn?
- Độ chọn lọc trước join có đủ cao không, có `Fetch` lớn ở mỗi phía không?

Câu trên minh họa `JOIN` bằng điều kiện khớp ID; một phép **key join** với cú pháp `JOIN ... ON KEYS` có thể là lựa chọn khác khi khóa liên kết đúng là document key. Tuy nhiên, không tự đổi cú pháp join nếu chưa kiểm tra ngữ nghĩa, phạm vi collection và model dữ liệu.

Một `EXPLAIN` có nhiều cây scan cần đọc **từng nguồn dữ liệu**. Index trên `orders` không tự thay thế index hoặc đường KV lookup của `customers`.

## 10. Đưa `EXPLAIN` về đúng SQL++ của Spring Data

### 10.1. Ánh xạ entity và keyspace

Entity minh họa:

```java
import java.time.Instant;
import java.util.List;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.TypeAlias;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@TypeAlias("salesOrder")
@Scope("sales")
@Collection("orders")
public class SalesOrder {
    @Id
    private String id;
    private String tenantId;
    private String customerId;
    private String status;
    private Instant createdAt;
    private long total;
    private String currency;
    private List<OrderItem> items;

    // Constructor, getter, setter được lược bỏ.
}
```

`OrderItem` là kiểu value object của dự án và không cần trình bày đầy đủ tại đây. Bucket `commerce` đến từ cấu hình ứng dụng/operations mapping, không được suy chỉ từ `@Scope` và `@Collection`.

### 10.2. Derived repository query

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

Derived query có thể phát sinh SQL++ để lọc theo thuộc tính, nhưng dạng `SELECT` phục vụ mapping `SalesOrder` có thể chứa nhiều trường hơn truy vấn viết tay chỉ lấy `META(o).id`. Ngoài ra, bộ lọc phân biệt type từ mapping có thể bổ sung điều kiện `_class`.

Khi đối chiếu `EXPLAIN`, cần có đủ:

1. SQL++ thực được repository gửi, không chỉ tên method.
2. Bucket/scope/collection thực tế và query context nếu có.
3. Tên JSON field sau mapping/converter.
4. Predicate kiểu entity, soft delete/tenant và các tham số.
5. Projection toàn entity hay DTO, cùng `ORDER BY`/`LIMIT`.

Nếu chỉ thử `EXPLAIN SELECT META(o).id ...` trong Workbench nhưng production trả `SalesOrder` đầy đủ, kết luận “index cover, không `Fetch`” có thể **không áp dụng cho endpoint production**.

### 10.3. `@Query` minh họa tham số và bộ lọc entity

```java
import java.util.List;
import org.springframework.data.couchbase.repository.Query;

public interface SalesOrderRepository
        extends CouchbaseRepository<SalesOrder, String> {

    @Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} " +
           "AND tenantId = $1 AND status = $2 " +
           "ORDER BY createdAt DESC LIMIT 20")
    List<SalesOrder> findRecentByTenantAndStatus(
        String tenantId, String status
    );
}
```

`#{#n1ql.selectEntity}` và `#{#n1ql.filter}` hỗ trợ dựng SQL++ phù hợp việc ánh xạ entity trong Spring Data Couchbase. `$1`, `$2` là tham số theo vị trí, tránh nối trực tiếp dữ liệu từ request.

Trong bài thực hành, hãy lấy SQL++ được ứng dụng log/ghi nhận bằng cách phù hợp với phiên bản đang chạy, rồi chạy `EXPLAIN` trên **bản tương đương về ngữ nghĩa**, không chỉ chép câu SQL++ mẫu mà bỏ qua filter hoặc projection đã phát sinh.

### 10.4. `CouchbaseTemplate` và reactive repository

`CouchbaseTemplate` có thể tạo truy vấn linh hoạt hoặc ánh xạ kết quả tùy API sử dụng. Khi đường thực thi là SQL++, optimizer vẫn làm việc với các index trên collection đích như với repository.

`ReactiveCouchbaseRepository`, `ReactiveCouchbaseTemplate` hay các API reactive SDK có thể đổi cách ứng dụng xử lý I/O, nhưng **không biến scan rộng thành scan hẹp**. Một `Flux` trả kết quả chậm vì `IndexScan`/`Fetch` lớn cần được tối ưu ở SQL++ và index, không chỉ điều chỉnh scheduler hay backpressure.

Nếu phương thức thực hiện KV `findById`, đừng tìm lỗi `EXPLAIN` cho một thao tác không đi qua Query Service. Hãy xác định đường truy cập trước khi chọn công cụ chẩn đoán.

## 11. `EXPLAIN`, Query Profile và scan consistency: ba loại bằng chứng khác nhau

### 11.1. `EXPLAIN` là kế hoạch dự kiến

`EXPLAIN` hữu ích để xác định:

- Index/scan operator được chọn.
- Phạm vi `spans` và bộ lọc còn lại.
- Có khả năng phải `Fetch`, `Order`, aggregate, join hay unnest không.
- Projection, `covers` và `Limit` trong kế hoạch.

Nó **không cung cấp một phép đo độ trễ production đáng tin cậy** chỉ từ việc đọc JSON. Những con số ước lượng của optimizer cũng không phải số lượng entry đã được quét trong một lần chạy cụ thể.

### 11.2. Query Profile và metrics mới phản ánh công việc thực tế

Để kiểm chứng lựa chọn index, chạy truy vấn trên dữ liệu đại diện và dùng cơ chế profiling/giám sát được hỗ trợ ở phiên bản Couchbase:

| Chỉ số | Nó giúp chẩn đoán điều gì? |
| --- | --- |
| Số entry index được scan | Index có đủ chọn lọc không? |
| Số document `Fetch` | Có tốn thời gian đọc JSON gốc không? |
| Số hàng vào/ra `Filter` | Có lọc quá muộn sau scan không? |
| Thời gian `Order`/sort | Index có cung cấp thứ tự phù hợp không? |
| Số hàng sau `UNNEST`/`JOIN` | Có nổ cardinality không? |
| Latency p50/p95/p99 | Endpoint có đáp ứng SLA dưới tải không? |
| CPU/memory và dung lượng Index Service | Index mới có làm cụm quá tải khi đọc/ghi không? |
| Query timeout/error rate | Có regression khi workload đồng thời tăng không? |

Khi benchmark, giữ cùng phân bố tenant lớn/nhỏ, tỷ lệ trạng thái phổ biến/hiếm, điều kiện khoảng, số lượng document và lưu lượng ghi. Cache, phân hoạch dữ liệu và mức tải hệ thống có thể khiến hai lần chạy giống nhau cho kết quả khác.

### 11.3. Scan consistency ảnh hưởng cả độ mới và thời gian chờ

GSI được duy trì bất đồng bộ với KV mutation. Hai thiết lập thường gặp:

| Scan consistency | Ý nghĩa |
| --- | --- |
| `NOT_BOUNDED` | Không bắt buộc đợi index bắt kịp mutation trước truy vấn; có thể ít chờ nhưng kết quả tạm thời cũ |
| `REQUEST_PLUS` | Đợi index bắt kịp các mutation liên quan trước khi scan; dữ liệu mới hơn nhưng có thể tăng độ trễ |

Do đó, khi thấy một endpoint chậm hơn sau khi thay cấu hình consistency, không nên kết luận chỉ mục mới kém hiệu quả từ riêng `EXPLAIN`: plan index có thể tương tự trong khi thời gian **chờ index bắt kịp mutation** tăng.

Ngược lại, một truy vấn `NOT_BOUNDED` chạy nhanh nhưng trả trạng thái cũ không thỏa yêu cầu read-after-write của nghiệp vụ. Cần tách **hiệu năng quét**, **độ mới dữ liệu** và **tính đúng của query**.

### 11.4. TTL, CAS và giao dịch không hiện đầy đủ qua `EXPLAIN`

TTL làm document hết hạn; CAS phát hiện xung đột cập nhật; giao dịch bảo vệ phạm vi thao tác cần nguyên tử theo cơ chế Couchbase. Chúng ảnh hưởng vòng đời và tính đúng của dữ liệu, nhưng `EXPLAIN` chỉ phân tích **kế hoạch truy vấn SQL++**, không chứng minh:

- Một mutation CAS có được chấp nhận hay bị conflict.
- Giao dịch nghiệp vụ đã commit đúng theo yêu cầu.
- Dữ liệu vừa cập nhật đã được index đồng bộ ở mức consistency mong muốn.
- Một document còn hợp lệ theo TTL tại thời điểm nghiệp vụ cụ thể.

Hãy dùng log/metric phù hợp với từng vấn đề, không cố giải thích mọi triệu chứng bằng sự xuất hiện của `IndexScan`.

## 12. Quy trình chẩn đoán từ câu truy vấn đến quyết định tối ưu

Một quy trình áp dụng được cho endpoint Spring Data Couchbase thực tế:

1. **Thu thập triệu chứng:** Query nào chậm, p95 ở tải nào, dữ liệu/tenant nào, có timeout hay kết quả cũ không?
2. **Định danh đường truy cập:** KV theo ID hay SQL++? Nếu SQL++, lấy nguyên câu từ repository/`@Query`/template.
3. **Xác nhận keyspace và mapping:** đúng bucket/scope/collection, field JSON và bộ lọc `_class`?
4. **Lập `EXPLAIN`:** tìm `IndexScan` hoặc primary scan, tên index, `spans`, `Filter`, `Fetch`, `Order` và `Limit`.
5. **Đối chiếu với workload:** điều kiện bằng, range, `IN`, projection, array, join, phân trang có khớp thứ tự khóa của index không?
6. **Kiểm tra index thật:** `system:indexes` có đúng index và trạng thái `online` không? Có index chồng lắp không?
7. **Đo Query Profile:** scan/fetch/hàng trung gian/latency và chi phí update dưới workload có đại diện.
8. **Thử một thay đổi có kiểm soát:** thêm/chỉnh index, đổi projection hoặc sửa SQL++; giữ các yếu tố khác ổn định để so sánh.
9. **Xác nhận tính đúng:** kiểm thử dữ liệu thiếu field, `NULL`, nhiều trạng thái, mảng rỗng, tenant lớn và độ mới dữ liệu.
10. **Triển khai và giám sát:** đưa DDL qua migration, đợi build, bật code phụ thuộc sau khi `EXPLAIN`/metrics đạt yêu cầu; chỉ thu hồi index cũ khi không còn truy vấn sử dụng.

### Truy vấn kiểm tra index trên collection

```sql
SELECT name, state, is_primary, index_key, condition,
       bucket_id, scope_id, keyspace_id
FROM system:indexes
WHERE bucket_id = "commerce"
  AND scope_id = "sales"
  AND keyspace_id = "orders";
```

Có thể thấy cùng tên index xuất hiện trong báo cáo trên những keyspace khác nhau. Vì vậy, luôn giữ bộ ba `bucket_id`, `scope_id` và `keyspace_id` trong kết quả kiểm tra, tránh nhầm index của collection khác.

Nếu index chưa `online`, phải xử lý build/privilege/tài nguyên thay vì kết luận optimizer cố ý bỏ qua. Nếu optimizer chọn index khác, trước hết đo kế hoạch hiện tại; chỉ thử `USE INDEX` để chẩn đoán khi cần so sánh ép một index ứng viên.

Ví dụ hint chẩn đoán:

```sql
EXPLAIN
SELECT META(o).id AS orderId, o.createdAt
FROM `commerce`.`sales`.`orders` AS o
USE INDEX (ix_orders_tenant_status_created USING GSI)
WHERE o.tenantId = "TENANT-A"
  AND o.status = "PAID"
ORDER BY o.createdAt DESC
LIMIT 20;
```

`USE INDEX` giúp kiểm tra một đường truy cập cụ thể nhưng không nên mặc định ép index mãi trong production: dữ liệu và index có thể thay đổi, khiến hint cũ trở nên kém hiệu quả.

## 13. Bảng đối chiếu triệu chứng kế hoạch với hướng xử lý

| Dấu hiệu từ `EXPLAIN`/metrics | Giả thuyết cần kiểm tra | Hướng thử nghiệm |
| --- | --- | --- |
| Primary scan trên query theo thuộc tính | Chưa có secondary index phù hợp hoặc optimizer không thấy | Kiểm tra index trên đúng collection; đề xuất index theo `WHERE` |
| `IndexScan` nhưng scan nhiều entry | Thiếu khóa dẫn đầu, range/sort không khớp | Kiểm tra `spans`; thay thứ tự khóa theo mẫu truy vấn |
| `Filter` loại phần lớn hàng sau scan | Một số predicate chưa được dùng để giới hạn dải index | Xem index key và biểu thức; cân nhắc composite/expression index |
| `Fetch` xuất hiện với projection nhỏ | Index chưa có đủ trường được `SELECT` hoặc cần filter ngoài index | So sánh covering index với chi phí tăng kích thước |
| `Fetch` khi trả entity đầy đủ | Repository ánh xạ nhiều trường/mảng | Cân nhắc DTO/projection hoặc đọc KV ở trang chi tiết |
| `Order` tốn nhiều thời gian | Thứ tự index không tương thích `ORDER BY` | Kiểm tra `IN`, khóa chưa cố định, hướng `ASC/DESC` |
| `LIMIT 20` nhưng vẫn đọc rất nhiều | Sort/filter/offset diễn ra trước khi giới hạn hiệu quả | Thiết kế lại index, projection, keyset pagination |
| Array query không dùng array index | `ANY`/`UNNEST` không tương thích expression index | So sánh `DISTINCT ARRAY`/`ALL ARRAY` theo ngữ nghĩa |
| Join tạo số hàng trung gian rất lớn | Predicate lọc áp dụng muộn, hai phía thiếu đường truy cập | Kiểm tra từng source, key lookup, `Join` và cardinality |
| Chỉ query Spring Data có `Fetch`, Workbench không | Query Spring Data thêm `_class` hoặc trả entity đầy đủ | Lấy SQL++ thực, kiểm tra `SELECT` và `WHERE` |
| Truy vấn literal dùng partial index, prepared query không dùng | Predicate index không suy ra được từ tham số động | Kiểm tra statement thực; cân nhắc index tổng quát |
| Index có trong catalog nhưng không trong plan | Chưa `online`, keyspace sai, cost khác hoặc predicate không khớp | Kiểm tra trạng thái, scope/collection, `EXPLAIN` |
| Query nhanh nhưng trả dữ liệu vừa ghi không đầy đủ | GSI bất đồng bộ, scan consistency | Xác định yêu cầu read-after-write; cân nhắc `REQUEST_PLUS` hoặc KV |
| Nhiều index giúp đọc nhưng update chậm | Chi phí duy trì index khi mutation tăng | Đo write throughput; bỏ index dư sau khi rà soát phụ thuộc |

## 14. Bài thực hành: kiểm chứng bốn giả thuyết trên cùng dataset

Giả sử collection `commerce.sales.orders` có vài trăm nghìn đơn, trong đó các tenant có quy mô khác nhau. Tỷ lệ `PAID`, `SHIPPED` và `OPEN` không đồng đều. Các câu hỏi sau phải được kiểm chứng bằng plan và metrics, không chỉ bằng cảm nhận.

### Thực hành A — Đọc `spans` theo hai điều kiện bằng

Tạo trong môi trường thử:

```sql
CREATE INDEX ix_lab_tenant_status_created
ON `commerce`.`sales`.`orders`(
    `tenantId`, `status`, `createdAt` DESC
);
```

Chạy `EXPLAIN`:

```sql
EXPLAIN
SELECT META(o).id AS id, o.createdAt
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = "TENANT-A"
  AND o.status = "PAID"
ORDER BY o.createdAt DESC
LIMIT 20;
```

Ghi tên index, `spans` theo hai khóa bằng, sự tồn tại của `Order` và `Fetch`. Nếu query chỉ `SELECT` ID/thời gian, hãy kiểm tra có thể cover không. Sau đó bỏ `status` khỏi `WHERE` và chạy lại. Giải thích thay đổi dải scan và nhu cầu sort.

### Thực hành B — So sánh query `IN` với equality

Giữ nguyên index, đổi điều kiện:

```sql
EXPLAIN
SELECT META(o).id AS id, o.status, o.createdAt
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = "TENANT-A"
  AND o.status IN ["PAID", "SHIPPED"]
ORDER BY o.createdAt DESC
LIMIT 20;
```

Dự đoán xem tập giá trị status nhiều nhóm có ảnh hưởng `Order`/`Limit` không, rồi đối chiếu kế hoạch thực. Dùng Query Profile để kiểm tra số hàng phải sắp xếp.

### Thực hành C — Thêm một field ngoài index

```sql
EXPLAIN
SELECT META(o).id AS id, o.createdAt, o.total
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = "TENANT-A" AND o.status = "PAID"
ORDER BY o.createdAt DESC
LIMIT 20;
```

Dự đoán khi thêm `total` vào projection có thể phát sinh `Fetch`. Thử index:

```sql
CREATE INDEX ix_lab_list_cover
ON `commerce`.`sales`.`orders`(
    `tenantId`, `status`, `createdAt` DESC, `total`
);
```

Khi index online, chạy lại `EXPLAIN`; kiểm tra `covers`, `Fetch`, `IndexScan`, so sánh latency và chi phí index khi ghi.

### Thực hành D — `ANY` trên mảng `items`

```sql
EXPLAIN
SELECT META(o).id AS id
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = "TENANT-A"
  AND ANY i IN o.items SATISFIES i.sku = "SKU-42" END;
```

Quan sát nếu chỉ có index tenant, Query Service có thể phải đọc JSON và lọc mảng. Sau đó tạo array index phù hợp, kiểm tra tên index được chọn và số entry scan. Thử `SELECT o.items` để xem còn `Fetch` không.

### Bảng ghi kết quả thực nghiệm

| Truy vấn | Index được chọn | `spans` quan trọng | `Fetch`? | `Order`? | Entry scan / kết quả | Ghi chú |
| --- | --- | --- | --- | --- | --- | --- |
| A1 — tenant + status | Ghi sau chạy | Ghi sau chạy | Ghi sau chạy | Ghi sau chạy | Ghi sau chạy | So sánh A2 |
| A2 — chỉ tenant | Ghi sau chạy | Ghi sau chạy | Ghi sau chạy | Ghi sau chạy | Ghi sau chạy | Thiếu status |
| B — `IN` hai status | Ghi sau chạy | Ghi sau chạy | Ghi sau chạy | Ghi sau chạy | Ghi sau chạy | Sắp xếp đa nhóm |
| C1 — thêm total | Ghi sau chạy | Ghi sau chạy | Ghi sau chạy | Ghi sau chạy | Ghi sau chạy | Projection ngoài index |
| C2 — covering candidate | Ghi sau chạy | Ghi sau chạy | Ghi sau chạy | Ghi sau chạy | Ghi sau chạy | Đo chi phí ghi |
| D — tìm SKU | Ghi sau chạy | Ghi sau chạy | Ghi sau chạy | Ghi sau chạy | Ghi sau chạy | Array index |

Các ô ghi “Ghi sau chạy” là mẫu **sổ thực nghiệm**, không phải số liệu đã được đo. Chỉ điền kết quả từ cụm thực hành sau khi xác nhận trạng thái index và công cụ profiling.

### Câu hỏi tự kiểm tra

1. Vì sao thấy `IndexScan3` chưa đủ để kết luận truy vấn tối ưu?
2. `spans` giúp phân biệt điều kiện trong `WHERE` với điều kiện được dùng để thu hẹp index như thế nào?
3. Với index `(tenantId, status, createdAt DESC)`, tại sao bỏ điều kiện `status` có thể ảnh hưởng cả quét lẫn sort?
4. `Filter` và `Fetch` khác nhau ở chức năng gì? Truy vấn có `Filter` có bắt buộc phải có `Fetch` không?
5. Vì sao `SELECT o.*` có thể thêm `Fetch` so với chỉ `SELECT META(o).id, o.createdAt`?
6. Vì sao `LIMIT 20` không bảo đảm chỉ quét 20 index entry?
7. Cần kiểm tra điều gì khi một array index đã tạo nhưng truy vấn `ANY` không dùng?
8. Vì sao `EXPLAIN` của một câu SQL++ viết tay chưa đủ để khẳng định derived repository query có cùng plan?
9. Khi query chậm sau khi bật `REQUEST_PLUS`, vì sao không nên kết luận ngay do thứ tự khóa index?
10. Phân biệt thông tin có được từ `EXPLAIN` với số liệu chỉ có sau Query Profile.

## 15. Kết luận

`EXPLAIN` là công cụ đọc **quyết định của optimizer**, không phải một phép đo tốc độ hoàn chỉnh. Khi chẩn đoán index trong Spring Data Couchbase, hãy đi từ **SQL++ thực của endpoint** đến **keyspace chính xác**, rồi kiểm tra index được chọn, `spans`, `Filter`, `Fetch`, `Order`, `covers` và `Limit`. Đối chiếu với mẫu equality/range/`IN`, projection, array và join; cuối cùng đo Query Profile để xác nhận chi phí thực tế.

Một chỉ mục được đánh giá tốt khi giúp **đúng truy vấn nghiệp vụ** trả kết quả chính xác với độ trễ và chi phí vận hành phù hợp. Nó không nhất thiết là chỉ mục dài nhất, mới nhất hoặc hoàn toàn không có `Fetch`. Sử dụng `EXPLAIN` cùng dữ liệu đại diện, yêu cầu nhất quán và quy trình triển khai có kiểm soát là cách biến việc tối ưu SQL++/repository thành những quyết định có thể kiểm chứng và duy trì.
