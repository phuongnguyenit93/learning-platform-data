# Chỉ mục đơn, chỉ mục tổng hợp và thứ tự trường

## 1. Vì sao một truy vấn đúng vẫn có thể rất chậm?

Trong chương **Chỉ mục** của **Spring Data MongoDB**, hai truy vấn cùng trả đúng 20 sản phẩm có thể có chi phí hoàn toàn khác nhau:

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a",
  status: "ACTIVE"
})
.sort({ createdAt: -1, _id: 1 })
.limit(20);
~~~

Nếu collection chỉ có vài chục document, MongoDB có thể tìm kiếm nhanh dù chưa có index chuyên dụng. Nhưng khi tăng tới hàng triệu document, server có thể phải kiểm tra rất nhiều tài liệu và thực hiện sort tốn tài nguyên. **Index** là cấu trúc dữ liệu giúp MongoDB tìm các khóa phù hợp và, khi cấu trúc index tương thích, **trả kết quả theo thứ tự yêu cầu mà không cần một bước sort blocking lớn**.

Vấn đề không dừng ở câu hỏi “có index hay chưa”. Một index có đủ field nhưng **sắp xếp thứ tự field sai** vẫn có thể khiến planner phải đọc nhiều key, lọc nhiều document hoặc sort lại.

Ví dụ các index sau không tương đương:

~~~javascript
// Index đơn
db.catalog_products.createIndex({ tenantId: 1 });

// Compound: tenant trước, status sau
db.catalog_products.createIndex({ tenantId: 1, status: 1 });

// Compound: status trước, tenant sau
db.catalog_products.createIndex({ status: 1, tenantId: 1 });

// Compound có cả điều kiện lọc và thứ tự hiển thị
db.catalog_products.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: 1
});
~~~

Các index compound này có thể có giá trị khác nhau tùy query thực tế. Trong hệ thống đa tenant, truy vấn thường luôn có `tenantId`, còn `status` đôi khi là tùy chọn; khi đó vị trí field đầu tiên trở nên rất quan trọng.

**Mục tiêu bài học:** phân biệt single-field và compound index, hiểu leftmost prefix, hướng sort, nguyên tắc *Equality–Sort–Range* (ESR), biểu diễn index trong Spring Data MongoDB, kiểm tra `explain("executionStats")`, đánh đổi chi phí ghi và viết integration test.

> Ví dụ dùng Java 17+, Spring Boot 3.x, Spring Data MongoDB 4.x và MongoDB tương thích. Query planner, cách hiển thị `explain` và các tối ưu có thể thay đổi theo phiên bản/server topology. Quy tắc ESR và prefix là công cụ thiết kế **khởi đầu**, không phải một bảo đảm rằng MongoDB luôn chọn đúng index ta dự đoán.

## 2. Index là gì và index không làm gì?

Index dạng B-tree thông thường của MongoDB lưu các khóa theo thứ tự được xác định. Một index trên `tenantId` hỗ trợ tìm các document có tenant cụ thể mà không nhất thiết phải quét toàn collection:

~~~javascript
db.catalog_products.createIndex(
  { tenantId: 1 },
  { name: "idx_product_tenant" }
);
~~~

Ký hiệu `1` là hướng **tăng dần** của field trong index; `-1` là hướng **giảm dần**. Với index **chỉ một field**, MongoDB thường có thể duyệt index theo cả chiều xuôi và ngược để đáp ứng sort đơn giản. Với **nhiều field**, mẫu dấu của các field liên quan đến sort là một phần quan trọng của thiết kế.

Index có thể giúp:

- Giới hạn vùng khóa cần tìm cho điều kiện equality/range khi index phù hợp.
- Duyệt khóa theo thứ tự yêu cầu cho một số dạng `sort`.
- Giảm số document phải đọc nếu điều kiện và projection được hỗ trợ bởi index.
- Bảo vệ uniqueness khi định nghĩa **unique index**.

Index **không tự động**:

- Biến mọi truy vấn thành nhanh; MongoDB có thể chọn collection scan với tập nhỏ hoặc khi filter không chọn lọc.
- Bảo đảm tất cả truy vấn dùng index đó, kể cả khi có `hint`.
- Tạo snapshot nhất quán giữa các trang pagination.
- Giải quyết filter sai tenant hoặc ngữ nghĩa query sai.
- Loại chi phí ghi; insert/update/delete phải duy trì các index liên quan.
- Đảm bảo thao tác trên nhiều document là transaction.

Một collection mới có index `_id` mặc định; không cần tạo lại index `{ _id: 1 }` chỉ vì entity có property Java `id`.

## 3. Dữ liệu mẫu và yêu cầu truy vấn

Giả sử collection `catalog_products` lưu:

~~~json
{
  "_id": "p-101",
  "tenantId": "tenant-a",
  "sku": "BOTTLE-500",
  "display_name": "Bình nước 500 ml",
  "status": "ACTIVE",
  "stock_qty": 12,
  "tags": ["outdoor", "premium"],
  "createdAt": { "$date": "2026-11-20T08:00:00Z" }
}
~~~

Các API đọc phổ biến:

| Yêu cầu | Filter | Sort | Dữ liệu trả |
|---|---|---|---|
Lấy một sản phẩm theo ID | `_id = ?` | Không bắt buộc | Tối đa một |
Lấy sản phẩm của tenant | `tenantId = ?` | `createdAt DESC` | Một trang |
Lấy sản phẩm ACTIVE của tenant | `tenantId = ? AND status = ACTIVE` | `createdAt DESC, _id ASC` | Một trang |
Tìm SKU trong tenant | `tenantId = ? AND sku = ?` | Không | Tối đa một nếu có unique index |
Tìm tồn kho từ 5 trở lên | `tenantId = ? AND status = ACTIVE AND stock_qty >= 5` | `stock_qty ASC` hoặc `createdAt DESC` | Một trang |
Tìm có tag outdoor | `tenantId = ? AND tags = outdoor` | `createdAt DESC` | Một trang |

Nếu ứng dụng có 100 tenant, mỗi tenant có số lượng và trạng thái sản phẩm rất khác nhau, **độ chọn lọc** của `tenantId` và `status` cũng khác nhau. Không quyết định thứ tự index chỉ từ tên field; phải xem tập truy vấn, dữ liệu và sort thực tế.

### Entity Spring Data

**CatalogProduct.java**

~~~java
package com.example.catalog;

import java.time.Instant;
import java.util.List;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "catalog_products")
public record CatalogProduct(
        @MongoId(FieldType.STRING) String id,
        String tenantId,
        String sku,
        @Field("display_name") String name,
        String status,
        @Field("stock_qty") long stock,
        List<String> tags,
        Instant createdAt) {
}
~~~

`@MongoId(FieldType.STRING)` yêu cầu BSON `_id` là String. `@Field` khiến `name` được lưu thành `display_name` và `stock` thành `stock_qty`. Query typed trong `MongoTemplate` có thể dùng tên property Java; MongoDB shell và raw BSON cần dùng **tên field vật lý**.

Không tự suy luận `@Document` sẽ tạo mọi index cần thiết. Index phải được khai báo và triển khai có chủ đích, sau đó được xác minh trên database.

## 4. Chỉ mục đơn (single-field index)

### 4.1. Một field equality

~~~javascript
db.catalog_products.createIndex(
  { status: 1 },
  { name: "idx_product_status" }
);

db.catalog_products.find({ status: "ACTIVE" });
~~~

Index này có thể giúp khi điều kiện trạng thái đủ chọn lọc. Nhưng nếu 95% document đều ACTIVE, một lần đọc phần lớn collection qua index + FETCH có thể không rẻ hơn một collection scan. Query planner quyết định theo thống kê/chi phí và server version.

Nếu gần như mọi query đều theo tenant, một index chỉ có `status` có thể là lựa chọn yếu so với index compound bắt đầu bằng `tenantId`. Đừng tự động tạo một index cho mọi property entity.

### 4.2. Một field range và sort

~~~javascript
db.catalog_products.createIndex(
  { createdAt: -1 },
  { name: "idx_product_created_desc" }
);

db.catalog_products.find({}).sort({ createdAt: -1 }).limit(20);
~~~

Index single-field có thể được duyệt ngược, vì vậy `{ createdAt: -1 }` không nhất thiết phải tạo kèm `{ createdAt: 1 }` để hỗ trợ cả hai hướng sort một-field.

Nhưng query trên vẫn có thể trả sản phẩm của mọi tenant. **Index không thay quyền truy cập**: filter `tenantId` phải có khi dữ liệu yêu cầu cách ly tenant.

### 4.3. Index _id có sẵn

~~~javascript
db.catalog_products.find({ _id: "p-101" });
~~~

Collection thường đã có unique index `_id_`. Dùng `findById`/`findOne` theo ID với điều kiện bảo vệ tenant khi nghiệp vụ cần. Trong ứng dụng đa tenant, việc có unique `_id` không khiến một người dùng được phép đọc ID của tenant khác; vẫn cần authorization.

### 4.4. Một field index không thay thế unique business key

Nếu cùng tenant không được có hai sản phẩm có cùng `sku`, index `{ sku: 1 }` có `unique: true` sẽ **ngăn SKU trùng trên toàn collection**, có thể sai khi hai tenant được phép dùng cùng SKU.

Khi uniqueness có phạm vi tenant, xem `{ tenantId: 1, sku: 1 }` ở mục compound index bên dưới.

## 5. Chỉ mục tổng hợp (compound index) và leftmost prefix

Một compound index lưu nhiều field theo thứ tự cố định. Ví dụ:

~~~javascript
db.catalog_products.createIndex(
  { tenantId: 1, status: 1, createdAt: -1, _id: 1 },
  { name: "idx_product_tenant_status_created_id" }
);
~~~

Ở mức trực giác, khóa index sắp xếp trước hết theo `tenantId`, trong mỗi tenant theo `status`, trong mỗi trạng thái theo `createdAt` giảm dần, và khi `createdAt` trùng nhau theo `_id` tăng dần.

Sơ đồ:

~~~text
tenantId ASC
  └── status ASC
       └── createdAt DESC
            └── _id ASC

Ví dụ phần khóa:
tenant-a / ACTIVE  / 2026-11-20T10:00Z / p-001
tenant-a / ACTIVE  / 2026-11-20T10:00Z / p-002
tenant-a / ACTIVE  / 2026-11-20T09:00Z / p-003
tenant-a / PENDING / 2026-11-20T11:00Z / p-004
tenant-b / ACTIVE  / 2026-11-20T12:00Z / p-005
~~~

### 5.1. Leftmost prefix

Một compound index thường hiệu quả nhất với các điều kiện bắt đầu từ **phần tiền tố ngoài cùng bên trái** (leftmost prefix):

| Filter | Mức độ khớp prefix | Nhận xét |
|---|---|---|
`{ tenantId: "tenant-a" }` | Có field đầu | Có thể dùng phần đầu index |
`{ tenantId: "tenant-a", status: "ACTIVE" }` | Có hai field đầu | Có thể thu hẹp vùng khóa tốt hơn |
`{ tenantId: "tenant-a", status: "ACTIVE", createdAt: { $gte: t } }` | Có các field theo thứ tự | Có thể kết hợp equality và range trên field tiếp theo |
`{ status: "ACTIVE" }` | Thiếu field tenant đầu | Không tận dụng prefix giống các dòng trên |
`{ createdAt: { $gte: t } }` | Thiếu tenant và status | Không phải truy vấn đích tốt của index này |
`{ tenantId: "tenant-a", createdAt: { $gte: t } }` | Thiếu field status ở giữa | Có thể tận dụng tenant, nhưng chưa chắc giới hạn/sort tốt theo createdAt |

**Không nói tuyệt đối rằng query không chứa field đầu “không thể dùng index”.** MongoDB đôi khi vẫn chọn index cho một điều kiện không phải prefix, một cách quét rộng hoặc một chiến lược tối ưu khác; vấn đề là **khả năng thu hẹp phạm vi quét và cung cấp thứ tự** có thể kém hơn nhiều. Dùng `explain` để xác minh.

### 5.2. Vì sao tenantId thường nên nằm trước status?

Trong API đa tenant, gần như mọi truy vấn đều có `tenantId`. Nếu chọn:

~~~javascript
{ status: 1, tenantId: 1, createdAt: -1, _id: 1 }
~~~

thì query chỉ có tenant mà **không có status** không còn khớp tiền tố đầu. Index với `tenantId` đứng đầu thường phù hợp hơn cho cả truy vấn “mọi trạng thái của tenant” và truy vấn “một trạng thái cụ thể của tenant”.

Tuy vậy, nếu workload **luôn** có equality trên cả tenant và status, thứ tự giữa hai equality fields có thể cho các lựa chọn gần tương đương về khía cạnh thu hẹp một query đó. Quyết định cuối cùng còn dựa vào **truy vấn khác dùng chung index, sort, cardinality và index prefix có sẵn**.

### 5.3. Compound index không có nghĩa mọi tổ hợp field đều tối ưu

Một index `{ tenantId: 1, status: 1, createdAt: -1, _id: 1 }` không tự tối ưu việc lọc `stock_qty >= 5`, vì `stock_qty` không phải key của index. MongoDB vẫn phải kiểm tra điều kiện trên document hoặc dùng chiến lược khác.

Thêm tất cả field vào cùng một index có thể tăng kích thước và chi phí ghi, đồng thời **không giải quyết được sự xung đột giữa range và sort**. Thiết kế index theo *query shape* thay vì “index chứa mọi field có trong ứng dụng”.

## 6. Hướng tăng/giảm trong compound index và sort

Với index:

~~~javascript
{ tenantId: 1, status: 1, createdAt: -1, _id: 1 }
~~~

truy vấn thường gặp:

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a",
  status: "ACTIVE"
})
.sort({ createdAt: -1, _id: 1 })
.limit(20);
~~~

Khi `tenantId` và `status` đều có điều kiện **equality**, các khóa index thuộc một cặp tenant/status đã được sắp theo `createdAt DESC, _id ASC`. Vì vậy MongoDB có thể tận dụng thứ tự index để trả trang kết quả mà không phải sort lại toàn bộ tập ứng viên.

### 6.1. Đảo chiều toàn bộ mẫu sort

Với hai field sort `createdAt` và `_id`:

| Sort sau hai equality | Tương thích chiều quét của index? |
|---|---|
`{ createdAt: -1, _id: 1 }` | Có, cùng mẫu dấu |
`{ createdAt: 1, _id: -1 }` | Có thể duyệt **ngược** toàn bộ mẫu |
`{ createdAt: -1, _id: -1 }` | Không phải phép đảo toàn bộ mẫu đã định |
`{ createdAt: 1, _id: 1 }` | Không phải phép đảo toàn bộ mẫu đã định |

Các dòng “không phải phép đảo” không có nghĩa MongoDB không thể phục vụ sort bằng **bất kỳ index nào**; nó có thể dùng index khác hoặc bước sort riêng. Trường hợp có equality, một số khóa sort cố định hoặc sort prefix có thể tạo ra ngoại lệ cần phân tích từng query. Bảng minh họa cách nhìn căn bản về **mẫu dấu của một compound index**.

### 6.2. Thiếu equality trên status

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a"
})
.sort({ createdAt: -1, _id: 1 });
~~~

Vì index sắp theo `status` **trước** `createdAt`, các sản phẩm ACTIVE và PENDING của một tenant nằm ở các vùng khóa khác nhau. Một lần duyệt index theo thứ tự đó **không tương đương** sắp tất cả sản phẩm trong tenant theo createdAt.

Nếu màn hình “tất cả trạng thái” là một query chủ đạo, có thể cần thêm index:

~~~javascript
db.catalog_products.createIndex(
  { tenantId: 1, createdAt: -1, _id: 1 },
  { name: "idx_product_tenant_created_id" }
);
~~~

Đây là trade-off: index bổ sung hỗ trợ query khác, nhưng tăng chi phí duy trì index. Đừng tạo cả hai chỉ vì ví dụ có hai dạng query; dùng thống kê truy cập và `explain` quyết định.

## 7. ESR: Equality – Sort – Range

Quy tắc **ESR** là heuristic thiết kế thứ tự field compound index:

1. **E (Equality):** các field thường so sánh bằng (`=`, nhiều trường hợp `$in` nhỏ).
2. **S (Sort):** các field quyết định thứ tự hiển thị.
3. **R (Range):** các field dùng bất đẳng thức (`$gt`, `$gte`, `$lt`, `$lte`...), regex/range tùy hình thức.

Ví dụ:

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a",
  status: "ACTIVE",
  stock_qty: { $gte: 5 }
})
.sort({ createdAt: -1, _id: 1 })
.limit(20);
~~~

Một ứng viên theo ESR:

~~~javascript
db.catalog_products.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1,
    _id: 1,
    stock_qty: 1
  },
  { name: "idx_product_esr_created_stock" }
);
~~~

Hai equality đầu giúp chọn tenant và status; các field sort tiếp theo giúp duyệt theo thứ tự; field `stock_qty` ở cuối có thể được kiểm tra trong quá trình quét khóa nhưng **không nhất thiết giúp giới hạn mạnh phạm vi scan** trước khi lấy đủ 20 document có stock phù hợp.

### 7.1. Khi range rất chọn lọc: cân nhắc ERS

Nếu chỉ 0,01% sản phẩm có `stock_qty >= 50000`, ưu tiên range trước sort có thể giảm rất nhiều key cần quét:

~~~javascript
db.catalog_products.createIndex(
  {
    tenantId: 1,
    status: 1,
    stock_qty: 1,
    createdAt: -1,
    _id: 1
  },
  { name: "idx_product_ers_stock_created" }
);
~~~

Đổi lại, vì range `stock_qty` xuất hiện trước `createdAt`, index có thể **không cung cấp sort toàn cục theo createdAt** cho các giá trị stock khác nhau. Query planner có thể cần sort sau khi lọc.

Vì thế:

- **ESR** thường có lợi khi tránh blocking sort là quan trọng và cần nhanh chóng lấy vài dòng đầu tiên.
- **ERS** có thể có lợi khi range cực kỳ chọn lọc, giảm số document ứng viên tới mức sort phần còn lại rẻ.
- Không có thứ tự nào là “đúng trong mọi workload”; phải đo latency, keys/docs examined, sort memory và tỷ lệ dữ liệu khớp.

### 7.2. Equality không đồng nghĩa mọi $in đều giống một giá trị

`$in` với một danh sách nhỏ có thể được planner xử lý gần với nhiều equality ranges, đôi khi hỗ trợ sort theo cách đặc biệt. Với danh sách lớn, hành vi có thể gần range hơn và cách tối ưu thay đổi theo phiên bản MongoDB.

Do đó đừng viết quy tắc kiểu “`$in` **luôn** là equality” hoặc “**luôn** là range” rồi áp dụng máy móc vào compound index. Một ứng dụng cho phép lọc hàng nghìn SKU cần được đo riêng.

### 7.3. Không ép hint khi chưa có lý do

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a", status: "ACTIVE"
})
.hint("idx_product_tenant_status_created_id");
~~~

`hint` yêu cầu sử dụng một index cụ thể, hữu ích khi làm thí nghiệm hoặc xử lý một trường hợp đã chẩn đoán rõ. Nhưng trong production, hint cứng có thể làm truy vấn kém hơn khi dữ liệu đổi, index bị sửa hoặc query shape thay đổi. Mặc định hãy để planner chọn và dùng `explain` để xác minh trước khi thêm hint.

## 8. Index hỗ trợ sort, range và pagination

### 8.1. Offset pagination

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a", status: "ACTIVE"
})
.sort({ createdAt: -1, _id: 1 })
.skip(10000)
.limit(20);
~~~

Index phù hợp giúp không cần sort lại tập lớn, nhưng `skip(10000)` vẫn có thể phải **duyệt và bỏ qua** nhiều khóa. Index không làm cho mọi độ sâu offset có chi phí hằng số.

### 8.2. Keyset pagination theo sort nhiều field

Giả sử trang trước kết thúc bằng:

~~~text
lastCreatedAt = 2026-11-20T08:00:00Z
lastId = "p-101"
sort = { createdAt: -1, _id: 1 }
~~~

Để lấy các document nằm **sau cursor** theo đúng thứ tự này:

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a",
  status: "ACTIVE",
  $or: [
    { createdAt: { $lt: ISODate("2026-11-20T08:00:00Z") } },
    {
      createdAt: ISODate("2026-11-20T08:00:00Z"),
      _id: { $gt: "p-101" }
    }
  ]
})
.sort({ createdAt: -1, _id: 1 })
.limit(20);
~~~

Giải thích hai nhánh:

1. Sản phẩm **cũ hơn** theo `createdAt` sẽ nằm sau trên sort giảm dần.
2. Nếu timestamp bằng nhau, ID **lớn hơn** theo `_id ASC` sẽ nằm sau cursor.

Index `{ tenantId: 1, status: 1, createdAt: -1, _id: 1 }` là ứng viên thích hợp để đánh giá cho cách phân trang này. Tuy nhiên hiệu quả của filter `$or`, giới hạn và thứ tự đọc phải được kiểm tra bằng `explain`.

**Chú ý:** keyset pagination ổn định hơn offset khi dữ liệu mới được thêm vào đầu danh sách, nhưng nó **không tự tạo snapshot giao dịch**. Nếu document thay đổi `createdAt` hoặc bị xóa, kết quả qua nhiều trang vẫn chịu tác động của cập nhật đồng thời. Cursor cần mang đủ khóa sort và thông tin phạm vi tenant; phải validate, không tin giá trị cursor do client tự sửa.

## 9. Unique compound index và khóa nghiệp vụ

Giả sử quy tắc của hệ thống:

> Mỗi tenant không được có hai sản phẩm cùng SKU đã chuẩn hóa, nhưng hai tenant khác nhau có thể dùng cùng SKU.

Chỉ mục phù hợp:

~~~javascript
db.catalog_products.createIndex(
  { tenantId: 1, sku: 1 },
  { unique: true, name: "uq_product_tenant_sku" }
);
~~~

| tenantId | sku | Có được phép tồn tại đồng thời? |
|---|---|---|
| tenant-a | BOTTLE-500 | Có |
| tenant-a | BOTTLE-500 (document thứ hai) | Không |
| tenant-b | BOTTLE-500 | Có |

**Unique index** là cơ chế database bảo vệ tính duy nhất khi nhiều request ghi đồng thời. Mẫu `existsByTenantIdAndSku(...)` rồi `save(...)` không tương đương: hai request có thể cùng thấy SKU chưa tồn tại trước khi một request tạo document.

### 9.1. Phạm vi uniqueness phụ thuộc vào dữ liệu null/missing

Unique index compound so sánh **tổ hợp giá trị index key**. Field thiếu hoặc null có những quy tắc index cụ thể; nếu cho phép các document chưa có `sku`, cần xem thiết kế liệu có đụng khóa trùng ngoài dự kiến không.

Các lựa chọn:

- Bắt buộc `tenantId` và `sku` trong schema validation/application validation.
- Chuẩn hóa SKU về một format thống nhất trước khi ghi.
- Khi uniqueness chỉ áp dụng cho tập document có điều kiện, cân nhắc **partial unique index** với `partialFilterExpression` phù hợp.
- Nếu cần so sánh SKU không phân biệt hoa/thường, định nghĩa **collation** nhất quán cho index và quy tắc truy vấn.

Không chỉ thêm `unique: true` trên field `sku` ở entity nếu yêu cầu thật là unique theo (`tenantId`, `sku`).

### 9.2. Tạo index trên collection đã có dữ liệu

MongoDB có thể từ chối tạo unique index khi dữ liệu hiện tại đã trùng key. Quy trình production cần:

1. Thống kê duplicate và dữ liệu sai chuẩn.
2. Đưa ra chính sách hợp nhất/giải quyết duplicate.
3. Kiểm tra tài nguyên cho quá trình index build.
4. Triển khai index bằng migration/operation có kiểm soát.
5. Xác minh index tồn tại và ứng dụng xử lý duplicate-key exception đúng contract.

Đừng sửa dữ liệu trùng bằng cách tự xóa document chỉ để index build qua; cần quyết định nghiệp vụ rõ ràng.

## 10. Compound index với array: multikey và giới hạn

`tags` trong `CatalogProduct` là `List<String>`, được lưu dưới dạng BSON array. Index:

~~~javascript
db.catalog_products.createIndex(
  { tenantId: 1, tags: 1 },
  { name: "idx_product_tenant_tags" }
);
~~~

có thể trở thành **multikey index** vì `tags` là mảng. Các phần tử mảng đóng góp vào việc lập index, giúp truy vấn như:

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a",
  tags: "outdoor"
});
~~~

Tuy nhiên multikey index có các ràng buộc quan trọng:

- Không tùy ý tạo compound index trên **hai field chứa các mảng độc lập** trong cùng một document. MongoDB có quy tắc không cho phép một compound multikey index có nhiều array paths độc lập gây kiểu *parallel arrays*.
- Index trên mảng lớn có thể tạo nhiều index entries, ảnh hưởng kích thước, memory và chi phí cập nhật.
- `$elemMatch` đôi khi cần để buộc nhiều điều kiện nằm trên cùng phần tử mảng document và có thể ảnh hưởng cách planner kết hợp index bounds.
- Multikey index có hạn chế riêng với covered queries, sorting và một số field path; không suy ra mọi query trên array đều “covered”.

Nếu dùng `{ tenantId: 1, tags: 1, createdAt: -1 }`, cần đo query với filter tag và sort thực tế; chỉ thấy `IXSCAN` không đủ để kết luận không có blocking sort.

**Index không thay ngữ nghĩa array.** Ví dụ hai điều kiện `variants.color = RED` và `variants.quantity >= 10` trên hai dot paths có thể khớp ở **hai phần tử khác nhau**; nếu phải đúng trên cùng biến thể, cần `$elemMatch` bất kể có index hay không.

## 11. Khai báo index bằng annotation trong Spring Data MongoDB

Spring Data MongoDB hỗ trợ metadata index trên entity thông qua các annotation như `@Indexed`, `@CompoundIndex`, `@CompoundIndexes`.

### 11.1. @Indexed cho field đơn

Ví dụ nếu màn hình thường xuyên tìm sản phẩm theo `sku` trong **collection chỉ có một tenant**, hoặc nhu cầu business chỉ cần index trên SKU:

~~~java
import org.springframework.data.mongodb.core.index.Indexed;

@Indexed(name = "idx_product_sku")
private String sku;
~~~

Đoạn này minh họa field trong một **class entity**, không phải phần của record `CatalogProduct` đã định nghĩa ở mục 3. Trong ứng dụng đa tenant dùng unique (`tenantId`, `sku`), không tự động thêm single-field SKU index nếu query workload không cần.

### 11.2. @CompoundIndex trên entity

Có thể đặt annotation trên entity:

~~~java
import org.springframework.data.mongodb.core.index.CompoundIndex;

@CompoundIndex(
        name = "idx_product_tenant_status_created_id",
        def = "{ 'tenantId': 1, 'status': 1, 'createdAt': -1, '_id': 1 }")
@Document(collection = "catalog_products")
public class IndexedProduct {
    // Định nghĩa fields tương ứng, ví dụ tenantId, status, createdAt, id.
}
~~~

Đây là **minh họa metadata annotation**, không phải một entity hoàn chỉnh để copy chạy độc lập. Trong dự án thật, dùng tên entity thực và khai báo đầy đủ các field theo schema. `@CompoundIndex` được đặt ở mức class, không trên từng field.

Nếu cần nhiều compound indexes:

~~~java
@CompoundIndexes({
    @CompoundIndex(
            name = "idx_product_tenant_status_created_id",
            def = "{ 'tenantId': 1, 'status': 1, 'createdAt': -1, '_id': 1 }"),
    @CompoundIndex(
            name = "uq_product_tenant_sku",
            def = "{ 'tenantId': 1, 'sku': 1 }",
            unique = true)
})
~~~

Đây là fragment annotation đặt trên **cùng entity class** và cần import `CompoundIndexes` cùng `CompoundIndex`. Trong các phiên bản hỗ trợ annotation lặp lại, cách viết khác cũng có thể hoạt động. Quy tắc naming và mapping property trong `def` phải được kiểm tra theo entity/phiên bản, nhất là với `@Field` và nested paths.

### 11.3. Annotation không đồng nghĩa tự tạo index ngay

Từ Spring Data MongoDB 3.x, **tự động tạo index theo annotation không bật mặc định**. Trong Spring Boot, cấu hình tương ứng có thể là:

~~~yaml
spring:
  data:
    mongodb:
      auto-index-creation: true
~~~

Đây là **cấu hình minh họa** khi dự án quyết định cho phép automatic index creation. Không bật đồng loạt trong production mà không xem xét quy trình migration, khối lượng dữ liệu, duplicate keys, quyền tạo index và thời gian deploy. Một annotation hiện diện trong source code **không xác nhận index đã tồn tại trên server**.

Trong production, thường cần quy trình quản lý index tường minh, có kiểm tra thay đổi và có thể rollback theo kế hoạch; không coi việc khởi tạo repository là công cụ migration hoàn chỉnh.

## 12. Tạo và kiểm tra index bằng MongoTemplate

Spring Data có `IndexOperations` để làm việc với index của entity/collection. Ví dụ một service quản lý index có kiểm soát:

**CatalogIndexProvisioner.java**

~~~java
package com.example.catalog;

import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.Index;
import org.springframework.data.mongodb.core.index.IndexInfo;
import org.springframework.stereotype.Component;

@Component
public class CatalogIndexProvisioner {
    private final MongoTemplate mongo;

    public CatalogIndexProvisioner(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public void ensureReadIndex() {
        Index index = new Index()
                .on("tenantId", Sort.Direction.ASC)
                .on("status", Sort.Direction.ASC)
                .on("createdAt", Sort.Direction.DESC)
                .on("_id", Sort.Direction.ASC)
                .named("idx_product_tenant_status_created_id");

        mongo.indexOps(CatalogProduct.class).ensureIndex(index);
    }

    public List<IndexInfo> listIndexes() {
        return mongo.indexOps(CatalogProduct.class).getIndexInfo();
    }
}
~~~

`indexOps(CatalogProduct.class)` lấy metadata collection tương ứng. `ensureIndex(...)` yêu cầu tạo index nếu chưa tồn tại theo định nghĩa phù hợp; nếu đã có index cùng tên nhưng **khác keys/options**, MongoDB có thể báo xung đột thay vì âm thầm sửa index.

**Không chạy ensureIndex một cách không kiểm soát ở mọi HTTP request.** Nên dùng migration/deployment step hoặc quy trình khởi tạo được quản trị; index build trên collection lớn có chi phí thật và cần quyền thích hợp.

### 12.1. Kiểm tra index thực tế trên MongoDB

Trong mongosh:

~~~javascript
db.catalog_products.getIndexes();
~~~

Kết quả minh họa:

~~~json
[
  { "v": 2, "key": { "_id": 1 }, "name": "_id_" },
  {
    "v": 2,
    "key": {
      "tenantId": 1,
      "status": 1,
      "createdAt": -1,
      "_id": 1
    },
    "name": "idx_product_tenant_status_created_id"
  }
]
~~~

Các field như `v` và metadata server có thể khác theo phiên bản; đừng so sánh nguyên văn toàn bộ output JSON. Hãy xác nhận **key order, direction, name và options** như unique/partial/collation.

### 12.2. IndexOptions là một phần của định nghĩa

Hai index có cùng key pattern nhưng khác `unique`, `partialFilterExpression` hoặc `collation` không nhất thiết thay thế được nhau. Nếu thay đổi options, quy trình migration có thể cần tạo index khác, chuyển hướng đọc và sau đó dọn index cũ khi an toàn.

Không tự `dropIndex` trên production chỉ để test một phỏng đoán. Một index có thể đang phục vụ nhiều API khác; phải kiểm kê workload và có phương án rollback.

## 13. Viết Query và Sort typed trong MongoTemplate

Đoạn service sau sử dụng index đã thiết kế ở mục 5. `Query` dùng tên property Java, không dùng BSON raw path cho `name` và `stock`.

**CatalogSearchService.java**

~~~java
package com.example.catalog;

import java.time.Instant;
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class CatalogSearchService {
    private final MongoTemplate mongo;

    public CatalogSearchService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public List<CatalogProduct> newestActive(
            String authenticatedTenantId, int limit) {
        if (authenticatedTenantId == null
                || authenticatedTenantId.isBlank()
                || limit < 1 || limit > 100) {
            throw new IllegalArgumentException("Bộ lọc hoặc limit không hợp lệ");
        }

        Query query = Query.query(
                Criteria.where("tenantId").is(authenticatedTenantId)
                        .and("status").is("ACTIVE"));

        query.with(Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("id")));
        query.limit(limit);

        return mongo.find(query, CatalogProduct.class);
    }

    public List<CatalogProduct> newestWithStock(
            String authenticatedTenantId, long minimumStock, int limit) {
        if (minimumStock < 0) {
            throw new IllegalArgumentException("minimumStock không hợp lệ");
        }
        if (authenticatedTenantId == null
                || authenticatedTenantId.isBlank()
                || limit < 1 || limit > 100) {
            throw new IllegalArgumentException("Bộ lọc hoặc limit không hợp lệ");
        }

        Query query = Query.query(
                Criteria.where("tenantId").is(authenticatedTenantId)
                        .and("status").is("ACTIVE")
                        .and("stock").gte(minimumStock));
        query.with(Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("id")));
        query.limit(limit);
        return mongo.find(query, CatalogProduct.class);
    }
}
~~~

Với `CatalogProduct.class`, `Criteria.where("stock")` được mapping sang BSON `stock_qty`; `Sort.Order.asc("id")` được ánh xạ thành `_id: 1`. Tuy nhiên, trường có `@Field`, nested property hoặc alias phức tạp phải được xác minh bằng command capture/integration test, không chỉ xem Java method names.

### 13.1. BSON dự kiến

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a",
  status: "ACTIVE",
  stock_qty: { $gte: 5 }
})
.sort({ createdAt: -1, _id: 1 })
.limit(20);
~~~

Index `{ tenantId: 1, status: 1, createdAt: -1, _id: 1 }` có thể cung cấp thứ tự, nhưng phải lọc thêm `stock_qty` trên tài liệu ứng viên. Nếu rất nhiều sản phẩm có stock dưới 5, nó có thể phải duyệt nhiều key mới lấy đủ 20 sản phẩm phù hợp. Đây là lúc cần so sánh các index ESR/ERS của mục 7.

## 14. explain("executionStats"): kiểm tra thực tế thay vì đoán

Một index **có tồn tại** chưa chắc được query planner **sử dụng**, và một index **được sử dụng** chưa chắc làm truy vấn nhanh. Hãy kiểm tra:

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a",
  status: "ACTIVE"
})
.sort({ createdAt: -1, _id: 1 })
.limit(20)
.explain("executionStats");
~~~

### 14.1. Những trường cần đọc

| Thông tin | Ý nghĩa | Cách diễn giải |
|---|---|---|
`queryPlanner.winningPlan` | Kế hoạch được chọn | Tìm index scan/collection scan/sort stage theo format của phiên bản |
`IXSCAN` hoặc dạng plan index scan tương đương | Truy cập qua index | Có thể tốt, nhưng cần nhìn số key/document đã duyệt |
`COLLSCAN` | Quét collection | Đôi khi hợp lý với collection nhỏ hoặc filter rộng |
`SORT` / blocking sort | Có bước sort riêng | Có thể tốn memory khi nhiều ứng viên |
`executionStats.totalKeysExamined` | Số khóa index được duyệt | So với số kết quả và độ chọn lọc |
`executionStats.totalDocsExamined` | Số document được kiểm tra | Cao hơn nhiều so với returned docs có thể báo index chưa đủ chọn lọc |
`executionStats.nReturned` | Số document trả về | Dùng làm mẫu số khi so sánh |
`executionStats.executionTimeMillis` | Thời gian trên lần giải thích | Không phải latency p95/p99 production |

MongoDB có thể hiển thị kế hoạch khác giữa classic engine và Slot-Based Execution (SBE); đừng viết test yêu cầu một đường JSON `winningPlan.inputStage...` duy nhất cho mọi phiên bản. Quan sát ý nghĩa và số liệu chung.

### 14.2. So sánh ba truy vấn quan trọng

**A — Hai equality và sort phù hợp:**

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a", status: "ACTIVE"
})
.sort({ createdAt: -1, _id: 1 })
.limit(20).explain("executionStats");
~~~

**B — Bỏ equality trên status nhưng giữ sort:**

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a"
})
.sort({ createdAt: -1, _id: 1 })
.limit(20).explain("executionStats");
~~~

**C — Có range stock cùng sort:**

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a",
  status: "ACTIVE",
  stock_qty: { $gte: 1000 }
})
.sort({ createdAt: -1, _id: 1 })
.limit(20).explain("executionStats");
~~~

So sánh keys/docs examined và sự hiện diện của sort stage. Kế hoạch của C có thể khác nhiều giữa dữ liệu trong đó stock cao cực hiếm và dữ liệu trong đó stock cao phổ biến.

### 14.3. Explain không phải benchmark duy nhất

- Một explain trên 5 document test không đủ để kết luận index production.
- Cache, warm-up, concurrency, lưu lượng ghi và phân phối tenant có thể ảnh hưởng kết quả.
- Số key examined thấp chưa đủ: fetch document lớn hoặc sort memory lớn vẫn có thể tốn thời gian.
- Index creation và độ trễ ghi phải được đo bên cạnh độ trễ đọc.
- Khi so sánh, giữ nguyên query shape, dữ liệu đại diện và read preference/collation.

## 15. Covered query và projection

Một truy vấn **được index cover** khi MongoDB có thể trả các field yêu cầu từ index mà không cần đọc document gốc, trong các điều kiện thích hợp. Với:

~~~javascript
db.catalog_products.createIndex(
  { tenantId: 1, status: 1, createdAt: -1, _id: 1 },
  { name: "idx_product_tenant_status_created_id" }
);
~~~

query:

~~~javascript
db.catalog_products.find(
  { tenantId: "tenant-a", status: "ACTIVE" },
  { _id: 1, createdAt: 1 }
)
.sort({ createdAt: -1, _id: 1 });
~~~

có thể là ứng viên **covered query** vì các field filter, sort và projection đều nằm trong key pattern của index. Trong một kế hoạch phù hợp, `totalDocsExamined` có thể bằng **0** và plan thể hiện projection từ index.

Ngược lại:

~~~javascript
db.catalog_products.find(
  { tenantId: "tenant-a", status: "ACTIVE" },
  { _id: 1, display_name: 1 }
);
~~~

yêu cầu `display_name` vốn **không có trong index**, nên MongoDB thường phải fetch document để trả tên. Không nên thêm mọi field hiển thị vào compound index chỉ để đạt covered query nếu index sẽ quá rộng và làm chi phí ghi vượt lợi ích.

Với array/multikey, field thiếu, collation và projection đặc biệt, cần kiểm tra giới hạn covered query của phiên bản MongoDB. `totalDocsExamined = 0` trong explain là tín hiệu hữu ích, nhưng phải đối chiếu với kết quả và plan cụ thể.

## 16. Collation, null và kiểu dữ liệu: index đúng key chưa chắc đúng semantics

### 16.1. Collation của index và query

Nếu sản phẩm được tìm theo SKU hoặc tên không phân biệt hoa/thường, cần chính sách nhất quán. Một index được tạo với collation cụ thể có thể không phục vụ tốt phép so sánh chuỗi dùng **collation khác**.

Ví dụ:

~~~javascript
db.catalog_products.createIndex(
  { tenantId: 1, sku: 1 },
  {
    name: "idx_tenant_sku_ci",
    collation: { locale: "en", strength: 2 }
  }
);
~~~

Muốn dùng cùng semantics:

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a",
  sku: "bottle-500"
}).collation({ locale: "en", strength: 2 });
~~~

`strength: 2` thường phục vụ so khớp không phân biệt hoa/thường trong collation đã chọn; các quy tắc dấu/Unicode và locale khác phải được xem xét theo dữ liệu. Đừng tự suy ra một collation cho `name` có thể áp dụng đúng cho mã SKU hoặc mọi ngôn ngữ.

### 16.2. Field null/missing

MongoDB index các giá trị theo quy tắc BSON; điều kiện `{ field: null }` có semantics liên quan cả null và field thiếu ở truy vấn equality. Với unique index, null/missing cũng ảnh hưởng khóa uniqueness.

Nếu nghiệp vụ yêu cầu phân biệt “không có SKU”, “SKU null” và “SKU rỗng”, dùng schema validation và query rõ ràng, đừng dựa vào index tự định nghĩa semantics nghiệp vụ.

### 16.3. Trộn kiểu BSON

`stock_qty` nên lưu nhất quán kiểu số. Nếu lịch sử có document lưu String `"12"` hoặc null, index vẫn có thể tồn tại nhưng so sánh range và mapping sang Java `long` không còn như dự kiến. Cần migration và test với raw BSON; index không tự ép kiểu dữ liệu cũ về chuẩn.

## 17. Chi phí index: đọc nhanh hơn nhưng ghi nặng hơn

Mỗi index bổ sung cần tài nguyên:

| Chi phí | Vì sao xảy ra? | Cách kiểm soát |
|---|---|---|
Dung lượng đĩa | Có thêm cấu trúc khóa | Giữ số index có chủ đích; xem `$indexStats` |
Bộ nhớ/cache | Index cạnh tranh cache với dữ liệu | Theo dõi working set |
Insert | Ghi document và cập nhật các index liên quan | Benchmark tốc độ import |
Update | Field được index thay đổi → cập nhật index | Tránh index rộng không cần thiết |
Delete | Phải loại các entry liên quan | Đo workload ghi |
Index build | Có thể tốn CPU/I/O/thời gian | Lên lịch và giám sát deployment |
Tính chọn lọc thấp | Index scan quá rộng | Đo `keysExamined`/`docsExamined` |
Compound index dài | Nhiều khóa và options phức tạp | Thiết kế đúng query shape |

Không có một tỷ lệ cố định kiểu “mỗi index làm insert chậm X%”. Chi phí phụ thuộc kích thước document, số lượng field, cardinality, phần cứng và workload.

### 17.1. Kiểm kê index chưa dùng

MongoDB có `$indexStats` để quan sát thống kê sử dụng index trong phạm vi mà server cung cấp:

~~~javascript
db.catalog_products.aggregate([
  { $indexStats: {} }
]);
~~~

Nhưng số liệu có cửa sổ/tuổi đời phụ thuộc server và có thể reset do restart, rebuild hoặc các sự kiện quản trị. **Không drop một index chỉ vì số lần dùng hiển thị thấp trong một thời điểm.** Cần đối chiếu với lịch chạy batch cuối tuần, báo cáo tháng, công việc bảo trì và các consumer khác.

### 17.2. Index thừa theo prefix

Nếu đã có:

~~~javascript
{ tenantId: 1, status: 1, createdAt: -1, _id: 1 }
~~~

thì index `{ tenantId: 1, status: 1 }` có thể trở nên **dư thừa** đối với một số truy vấn equality prefix. Nhưng quyết định xóa nó còn phụ thuộc kích thước index, query khác, uniqueness, sparse/partial/collation và hành vi planner.

Không loại bỏ index có **unique constraint** chỉ vì một index không unique dài hơn có cùng prefix: unique constraint là một bất biến nghiệp vụ độc lập.

## 18. Kiểm thử tích hợp trên MongoDB thật

Mock `MongoTemplate` chỉ xác nhận code gọi method, không chứng minh index thực sự đã được tạo, key order đúng hoặc planner sử dụng index. Cần integration test với MongoDB thật, ví dụ Testcontainers. Trong Spring Boot 3.x, `@DataMongoTest` cấu hình MongoDB test slice nhưng **không tự cung cấp server**.

### 18.1. Seed dữ liệu và xác minh kết quả sort

**CatalogIndexIntegrationTest.java**

~~~java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.Index;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
@Import(CatalogSearchService.class)
class CatalogIndexIntegrationTest {
    @Autowired MongoTemplate mongo;
    @Autowired CatalogSearchService search;

    private CatalogProduct product(
            String id, String tenant, String status,
            long stock, String time) {
        return new CatalogProduct(
                id, tenant, "SKU-" + id, "Product " + id,
                status, stock, List.of("outdoor"),
                Instant.parse(time));
    }

    @BeforeEach
    void prepare() {
        // Chỉ chạy trên database test cô lập.
        mongo.dropCollection(CatalogProduct.class);
        mongo.indexOps(CatalogProduct.class).ensureIndex(
                new Index()
                        .on("tenantId", Sort.Direction.ASC)
                        .on("status", Sort.Direction.ASC)
                        .on("createdAt", Sort.Direction.DESC)
                        .on("_id", Sort.Direction.ASC)
                        .named("idx_product_tenant_status_created_id"));

        mongo.insert(List.of(
                product("a-1", "tenant-a", "ACTIVE", 12,
                        "2026-11-20T10:00:00Z"),
                product("a-2", "tenant-a", "ACTIVE", 3,
                        "2026-11-20T10:00:00Z"),
                product("a-3", "tenant-a", "ACTIVE", 9,
                        "2026-11-20T09:00:00Z"),
                product("a-4", "tenant-a", "PENDING", 50,
                        "2026-11-20T11:00:00Z"),
                product("b-1", "tenant-b", "ACTIVE", 100,
                        "2026-11-20T12:00:00Z")
        ), CatalogProduct.class);
    }

    @Test
    void newestActiveHasStableOrderAndTenantIsolation() {
        List<CatalogProduct> rows = search.newestActive("tenant-a", 20);
        assertThat(rows).extracting(CatalogProduct::id)
                .containsExactly("a-1", "a-2", "a-3");
    }

    @Test
    void stockFilterUsesJavaPropertyButStoredFieldIsBsonAlias() {
        List<CatalogProduct> rows =
                search.newestWithStock("tenant-a", 5, 20);
        assertThat(rows).extracting(CatalogProduct::id)
                .containsExactly("a-1", "a-3");

        Document raw = mongo.getCollection("catalog_products")
                .find(new Document("_id", "a-1")).first();
        assertThat(raw).isNotNull();
        assertThat(raw.get("stock_qty")).isInstanceOf(Number.class);
        assertThat(raw.containsKey("stock")).isFalse();
        assertThat(raw.containsKey("display_name")).isTrue();
    }

    @Test
    void compoundIndexKeyOrderIsExactlyAsDesigned() {
        Document actual = null;
        for (Document index :
                mongo.getCollection("catalog_products").listIndexes()) {
            if ("idx_product_tenant_status_created_id"
                    .equals(index.getString("name"))) {
                actual = index;
                break;
            }
        }
        assertThat(actual).isNotNull();

        Document key = actual.get("key", Document.class);
        assertThat(key).isNotNull();
        assertThat(key.keySet()).containsExactly(
                "tenantId", "status", "createdAt", "_id");
        assertThat(((Number) key.get("tenantId")).intValue()).isEqualTo(1);
        assertThat(((Number) key.get("status")).intValue()).isEqualTo(1);
        assertThat(((Number) key.get("createdAt")).intValue()).isEqualTo(-1);
        assertThat(((Number) key.get("_id")).intValue()).isEqualTo(1);
    }
}
~~~

**Vì sao test không assert bắt buộc `IXSCAN`?** Với chỉ năm document, query planner có thể chọn `COLLSCAN` mà vẫn rất hợp lý. Test cần kiểm chứng **index definition đúng** và **kết quả truy vấn đúng**; test hiệu năng phải dùng dữ liệu đại diện và tiêu chí riêng.

Test cũng không chứng minh rằng index này tối ưu mọi truy vấn thêm range `stock`. Đó là bài toán benchmark ở mục 14.

### 18.2. Các test lỗi cần bổ sung

| Ca kiểm thử | Kỳ vọng |
|---|---|
Chỉ query `tenantId` | Đối chiếu explain và lựa chọn index |
Query tenant + status + sort | Kiểm tra key order và khả năng bỏ sort blocking |
Query tenant nhưng bỏ status, vẫn sort createdAt | Phát hiện không được hỗ trợ tốt bởi prefix sort |
Sort đảo toàn bộ pattern | Kiểm tra chiều duyệt index có thể phục vụ |
Sort mixed không tương thích | Quan sát planner dùng index khác/SORT |
Thêm range stock cực chọn lọc | So sánh ESR với ERS |
Unique (`tenantId`, `sku`) và insert duplicate | MongoDB từ chối document trùng |
Hai tenant cùng SKU | Được phép nếu khóa unique scoped đúng |
`tags` là array | Kiểm tra multikey index và filter |
Tên Java `stock` khác BSON `stock_qty` | Query typed vẫn lọc đúng |
Index cùng tên nhưng khác key/options | Migration báo xung đột, không âm thầm sửa |
Nhiều test chạy song song | Không đụng chung database/collection |

### 18.3. Capture command và explain

Nếu cần xem BSON query thực tế từ `MongoTemplate`, dùng MongoDB Java Driver `CommandListener` với `CommandStartedEvent` trong test. Xác nhận filter `tenantId`, `status`, `stock_qty` và sort `createdAt`/`_id`.

Ở MongoDB shell, chạy cùng filter/sort với `explain("executionStats")`. Trong Java driver cũng có API `FindIterable.explain(...)` trên các phiên bản hỗ trợ; có thể dùng trong **test chẩn đoán**, nhưng không đưa explain vào đường request thông thường.

Không bật command logging production ở chế độ chứa dữ liệu khách hàng hoặc tenant ID nếu chưa có chính sách che/lưu trữ phù hợp.

## 19. Quy trình lựa chọn index thực tế

Một quy trình thiết kế có thể lặp lại:

~~~mermaid
flowchart TD
    A["Thu thập query shape và tần suất"] --> B["Ghi equality, sort, range, projection"]
    B --> C["Kiểm tra index đã tồn tại"]
    C --> D["Chọn ứng viên prefix/ESR hoặc ERS"]
    D --> E["Tạo index trong môi trường test"]
    E --> F["Explain trên dữ liệu đại diện"]
    F --> G{"Đúng kết quả và chi phí đạt mục tiêu?"}
    G -->|"Không"| H["Sửa filter, schema hoặc index"]
    H --> D
    G -->|"Có"| I["Đo read + write workload"]
    I --> J["Triển khai bằng migration có kiểm soát"]
    J --> K["Giám sát latency, index size, regressions"]
~~~

Thực hiện theo thứ tự:

1. **Ghi query shape**, bao gồm filter bắt buộc tenant/quyền, sort đầy đủ, limit và projection.
2. **Xác định dữ liệu**: phân phối tenant, tỷ lệ ACTIVE, số document theo vùng giá trị stock, chiều dài array.
3. **Kiểm kê index** đã tồn tại: `getIndexes()`/`IndexOperations.getIndexInfo()`.
4. **Đề xuất ít index ứng viên**, tránh trùng prefix không có lợi.
5. **Giữ semantics truy vấn đúng**, rồi mới đo hiệu năng. Không sửa logic filter chỉ để index “đẹp”.
6. **Chạy explain** cho query đại diện, bao gồm các tenant có kích thước cực khác nhau.
7. **Đo read/write trade-off**, không chỉ latency của một query.
8. **Triển khai có quản lý**: kiểm tra unique conflicts, naming và collation.
9. **Giám sát sau triển khai** và có phương án xử lý regressions.

Một index không phải một thuộc tính bất biến của entity; nó là **quyết định vật lý phụ thuộc workload** và cần được rà soát khi lưu lượng/kiểu truy vấn thay đổi.

## 20. Các lỗi phổ biến

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
Cho rằng index nào chứa field là đủ | Không tận dụng prefix hoặc sort | Xem thứ tự các field |
Tạo index `{ status, tenantId }` khi nhiều query chỉ lọc tenant | Prefix không khớp query chủ đạo | Ưu tiên tenant trước khi phù hợp workload |
Nhầm `-1` lúc nào cũng nhanh hơn `1` | Tạo index trùng không cần thiết | Hiểu duyệt xuôi/ngược, nhất là compound |
Sort `createdAt` khi field `status` giữa tenant và createdAt chưa có equality | Có thể cần blocking SORT | Thêm index khớp query thiếu status nếu đáng |
Quy tắc ESR áp dụng bất chấp selectivity | Quét nhiều key để tìm ít document đủ range | So sánh ESR/ERS bằng explain |
Cho rằng mọi `$in` giống một equality scalar | Dự đoán planner/sort sai | Đo theo kích thước `$in`/version |
Chỉ nhìn `IXSCAN` mà tuyên bố nhanh | Nhiều key/doc examined hoặc SORT | Đọc executionStats và latency |
Cho rằng `COLLSCAN` luôn sai | Tối ưu quá mức với collection nhỏ | Đánh giá chi phí thực |
Thêm index trên mọi property | Ghi chậm, tốn disk/cache | Chọn theo query shape |
Cho rằng annotation tự tạo index ở mọi deploy | Index chưa có trên server | Kiểm tra auto-index config/migration |
Đổi tên/option index rồi gọi ensureIndex | Có thể xung đột, không tự migrate | Quản lý thay đổi index |
Quên `@Field` khi viết BSON raw | Index trên field không chứa dữ liệu | Dùng đúng tên lưu trữ, kiểm tra raw BSON |
Unique index toàn collection thay vì tenant+SKU | Không cho phép SKU hợp lệ ở tenant khác | Unique theo business key |
Không xử lý null/missing trong unique | Index build/insert thất bại ngoài dự kiến | Schema validation hoặc partial index |
Compound index có nhiều array độc lập | Vi phạm ràng buộc multikey | Thiết kế lại index/schema |
Trông đợi covered query khi projection có field ngoài index | Phải FETCH document | Kiểm tra field filter/sort/projection |
Deep skip dù có index | Scan bỏ qua nhiều key | Cân nhắc keyset pagination |
Chỉ test index trên 5 document | Planner không đại diện production | Benchmark dữ liệu lớn |
Không xét chi phí ghi khi thêm index | Import/update chậm | Đo write throughput và latency |

## 21. Bài tập thực hành

**Bài 1 — Index đơn.** Tạo `{ tenantId: 1 }` và `{ createdAt: -1 }`. Viết ba query khác nhau, dùng explain quan sát khi nào index có ích. Thử sort createdAt ASC bằng cách duyệt ngược single-field index.

**Bài 2 — Leftmost prefix.** Tạo `{ tenantId: 1, status: 1, createdAt: -1, _id: 1 }`. So sánh truy vấn chỉ tenant, tenant + status và chỉ status. Ghi keys/docs examined trên dữ liệu đủ lớn.

**Bài 3 — Sort direction.** Với hai equality tenant/status, thử sort (`createdAt DESC, _id ASC`), đảo toàn bộ và đổi chỉ một dấu. Quan sát có/không có SORT trong explain.

**Bài 4 — ESR/ERS.** Truy vấn tenant + status + `stock_qty >= 1000` và sort newest. Tạo hai index ứng viên theo ESR và ERS; thay đổi tỷ lệ sản phẩm có stock cao, đo số key scanned và latency.

**Bài 5 — @Field.** Giữ property Java `stock` nhưng lưu BSON `stock_qty`. Xây query typed bằng `MongoTemplate` và kiểm tra raw document. Tạo index theo tên BSON đúng.

**Bài 6 — Unique theo tenant.** Tạo index `{ tenantId: 1, sku: 1 }` unique. Insert hai tenant cùng SKU thành công và hai document cùng tenant+SKU thất bại. Test duplicate-key exception theo framework.

**Bài 7 — Offset và keyset.** Có nhiều document cùng `createdAt`; dùng `_id ASC` phá hòa. So sánh `skip(10000)` với cursor theo hai field và kiểm tra không mất document trong bộ dữ liệu cố định.

**Bài 8 — Multikey.** Tạo index `{ tenantId: 1, tags: 1 }`, lọc tag `outdoor`. Sau đó thử thiết kế index trên hai mảng độc lập và giải thích ràng buộc parallel arrays.

**Bài 9 — Covered query.** Chỉ trả `_id` và `createdAt` cho tenant/status, kiểm tra `totalDocsExamined`. Sau đó thêm `display_name` vào projection và phân tích vì sao có thể phải FETCH.

**Bài 10 — Annotation và lifecycle.** Khai báo `@CompoundIndex`, kiểm tra auto-index creation trong môi trường test. Tắt tính năng đó rồi dùng `indexOps.ensureIndex`, xác minh `getIndexes()` theo key order/options.

**Bài 11 — Collation.** Tạo index tenant+SKU với collation cụ thể. Truy vấn có và không có cùng collation; so sánh kết quả lẫn explain. Xác nhận chính sách so sánh SKU theo nghiệp vụ.

**Bài 12 — Kiểm thử hiệu năng.** Tạo hàng chục nghìn đến hàng trăm nghìn document trong database test riêng. Đo p50/p95 read, tốc độ insert, chi phí update field có index và kích thước index trước/sau. Từ đó chọn ít index cần thiết nhất cho workload.

## 22. Ghi nhớ

**Chỉ mục đơn** phù hợp khi query/sort chủ yếu sử dụng một field; **chỉ mục tổng hợp** lưu nhiều field theo **thứ tự có ý nghĩa**. Đối với compound index, hãy hiểu **leftmost prefix**, khả năng duyệt xuôi/ngược của **mẫu sort nhiều field**, và quy tắc thiết kế **Equality–Sort–Range** như một điểm khởi đầu — không phải lời giải cho mọi truy vấn.

Trong **Spring Data MongoDB**, có thể định nghĩa index bằng `@Indexed`/`@CompoundIndex` hoặc `MongoTemplate.indexOps(...).ensureIndex(...)`. Tuy nhiên, **index phải thực sự tồn tại trên MongoDB**, tên BSON phải đúng với `@Field`, và thay đổi index trong production phải được quản lý như một migration. Index unique bảo vệ business key; index multikey, collation, partial/sparse và null/missing có những ràng buộc riêng.

Khi tối ưu, **luôn bắt đầu từ query shape và tính đúng đắn**, sau đó xác minh bằng `explain("executionStats")`, số key/document được duyệt, sort stage và benchmark trên dữ liệu đại diện. Đo cả **chi phí ghi và dung lượng index**. Index tốt nhất không phải index dài nhất hay nhiều index nhất, mà là tập index ít nhất vẫn đáp ứng đúng workload, bảo mật tenant và mục tiêu hiệu năng.
