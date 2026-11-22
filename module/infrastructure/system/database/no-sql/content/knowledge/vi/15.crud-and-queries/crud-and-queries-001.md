# Thao tác tạo, đọc, thay thế, cập nhật từng phần và xóa

CRUD là nhóm thao tác cơ bản nhất của một ứng dụng sử dụng cơ sở dữ liệu: **Create** (tạo), **Read** (đọc), **Update** (cập nhật) và **Delete** (xóa). Trong NoSQL, chữ U phải được hiểu tường minh hơn: **thay thế toàn bộ bản ghi (replace)** và **chỉ cập nhật một phần (partial update)** có ngữ nghĩa rất khác nhau. Chọn sai thao tác có thể xóa mất trường, ghi đè thay đổi của người khác, trừ tồn kho hai lần khi retry hoặc làm sai dữ liệu giữa nhiều dịch vụ.

Bài này xây dựng một catalog sản phẩm với MongoDB để giải thích năm nhóm thao tác, sau đó đối chiếu Redis, DynamoDB và Cassandra. Ví dụ được trình bày bằng mongosh, HTTP, Redis CLI, CQL và pseudocode khi cần. Những khả năng transaction, TTL, query và consistency phụ thuộc hệ quản trị, phiên bản và topology thực tế; không thể suy rằng tên thao tác giống nhau thì bảo đảm cũng giống nhau.

## 1. Năm thao tác cần phân biệt

| Thao tác | Mục tiêu | Lệnh MongoDB minh họa | Rủi ro |
|---|---|---|---|
| Tạo | Thực thể mới chưa tồn tại | `insertOne` | Trùng khóa, retry tạo hai lần |
| Đọc | Trả dữ liệu phù hợp khóa/bộ lọc | `findOne`, `find` | Đọc sai tenant, scan rộng, stale read |
| Thay thế | Đặt lại toàn bộ nội dung bản ghi | `replaceOne` | Mất field, lost update |
| Cập nhật từng phần | Chỉ đổi những field/toán tử được chỉ định | `updateOne`, `updateMany` | Race, sai đường dẫn, upsert ngoài ý muốn |
| Xóa | Bỏ bản ghi hoặc ngừng hiệu lực | `deleteOne`, `deleteMany`, soft delete | Xóa nhầm, thiếu dữ liệu lịch sử |

Một tài liệu hiện có:

~~~json
{
  "_id": "p100",
  "name": "Wireless Mouse",
  "priceMinor": 2999,
  "currency": "USD",
  "tags": ["wireless", "mouse"]
}
~~~

Nếu thay **toàn bộ** bằng một document chỉ chứa `name` và `priceMinor`, những trường không có trong replacement sẽ bị bỏ. Nếu chỉ `$set` hai field này, `currency` và `tags` được giữ nguyên. Đó là khác biệt trung tâm của bài.

## 2. Thiết kế dữ liệu mẫu và access pattern

Hệ thống quản lý sản phẩm của nhiều tenant; mỗi sản phẩm có SKU, giá và tồn kho.

~~~javascript
{
  _id: "p100",
  tenantId: "t01",
  sku: "MOUSE-01",
  name: "Wireless Mouse",
  description: "Ergonomic mouse",
  priceMinor: NumberLong("2999"),
  currency: "USD",
  availableStock: 12,
  tags: ["wireless", "mouse"],
  attributes: {
    color: "black",
    warrantyMonths: 12
  },
  status: "ACTIVE",
  version: 1,
  createdAt: ISODate("2026-11-14T08:00:00Z"),
  updatedAt: ISODate("2026-11-14T08:00:00Z")
}
~~~

Trong ví dụ, `priceMinor=2999` nghĩa là 29.99 USD; không phải mọi đồng tiền đều có hai chữ số thập phân. `version` phục vụ optimistic concurrency. `createdAt` và `updatedAt` phục vụ audit, sort và phân trang, nhưng không tự thay thế nhật ký thay đổi.

Các đường truy cập cần thiết:

- Tạo product bằng ID và SKU duy nhất trong tenant.
- Đọc product theo ID, chỉ trả field được phép.
- Liệt kê product ACTIVE theo tenant và thời gian cập nhật.
- Thay toàn bộ mô tả product từ một snapshot có thẩm quyền.
- Chỉ sửa tên, giá, tags hoặc một field lồng nhau.
- Giảm tồn kho có điều kiện để không tạo số âm.
- Ngừng bán, lưu lịch sử và cuối cùng có thể xóa theo retention.

**Ranh giới dữ liệu:** Một sản phẩm có thể là một document và cập nhật một document là đơn vị nguyên tử trong MongoDB, nhưng nghiệp vụ giữ hàng còn phải ghi Reservation/Order ở nơi khác. Không đồng nhất sự nguyên tử một document với cả workflow nhiều document.

## 3. Chuẩn bị môi trường MongoDB thực hành

Chỉ chạy những lệnh thao tác/xóa dữ liệu sau trong database thực hành. Trong mongosh:

~~~javascript
use nosql_crud_lab

db.products.createIndex(
  { tenantId: 1, sku: 1 },
  { unique: true, name: "uq_tenant_sku" }
);

db.products.createIndex(
  { tenantId: 1, status: 1, updatedAt: -1, _id: 1 },
  { name: "ix_tenant_status_recent" }
);
~~~

`_id` đã có ràng buộc duy nhất ở collection. Index `tenantId + sku` bảo vệ một bất biến khác: không có hai product có cùng SKU trong một tenant. Nếu đã có record vi phạm, việc tạo unique index có thể thất bại và cần xử lý dữ liệu trước.

Index thứ hai phục vụ query theo tenant/status, sau đó sort theo thời gian và ID. Thiết kế index nên dựa trên access pattern, không tạo càng nhiều càng tốt vì mỗi index làm tăng storage và chi phí ghi.

## 4. Create: tạo mới bằng insertOne

~~~javascript
db.products.insertOne({
  _id: "p100",
  tenantId: "t01",
  sku: "MOUSE-01",
  name: "Wireless Mouse",
  description: "Ergonomic mouse",
  priceMinor: NumberLong("2999"),
  currency: "USD",
  availableStock: 12,
  tags: ["wireless", "mouse"],
  attributes: { color: "black", warrantyMonths: 12 },
  status: "ACTIVE",
  version: 1,
  createdAt: ISODate("2026-11-14T08:00:00Z"),
  updatedAt: ISODate("2026-11-14T08:00:00Z")
});
~~~

Nếu thao tác thành công, MongoDB trả thông tin như `insertedId`. Nếu chạy lại cùng `_id`, lệnh bị lỗi trùng khóa; nếu tạo ID khác nhưng dùng cùng SKU/tenant, unique index cũng có thể chặn.

### 4.1. Tạo record và idempotency

Nếu client gửi `POST /products` rồi mất kết nối sau khi server đã commit, client không biết record có được tạo hay chưa. Retry với ID mới có thể tạo product thứ hai.

Một API nên dùng định danh ổn định và quy tắc:

- Cùng idempotency key + cùng payload → trả tài nguyên đã tạo hoặc kết quả tương đương.
- Cùng key + payload khác → báo xung đột.
- Lỗi duplicate ID → tra lại bản ghi, kiểm tra đúng tenant, đúng ý định; không tự coi mọi duplicate là thành công.
- ID nghiệp vụ và tenant phải được xác thực/chuẩn hóa ở phía server.

Ví dụ request:

~~~http
POST /v1/products
Idempotency-Key: catalog-t01-mouse01-v1
Content-Type: application/json

{
  "sku": "MOUSE-01",
  "name": "Wireless Mouse",
  "priceMinor": 2999,
  "currency": "USD"
}
~~~

Server không nên cho client tự ý điền `tenantId`, `version` hoặc bất kỳ field nội bộ nào không thuộc quyền sửa.

### 4.2. insertMany không mặc nhiên all-or-nothing

~~~javascript
db.products.insertMany([
  {
    _id: "p101", tenantId: "t01", sku: "KB-01",
    name: "Keyboard", priceMinor: NumberLong("8999"),
    currency: "USD", availableStock: 5, status: "ACTIVE",
    version: 1, createdAt: new Date(), updatedAt: new Date()
  },
  {
    _id: "p102", tenantId: "t01", sku: "PAD-01",
    name: "Mouse Pad", priceMinor: NumberLong("999"),
    currency: "USD", availableStock: 20, status: "ACTIVE",
    version: 1, createdAt: new Date(), updatedAt: new Date()
  }
]);
~~~

Nếu một phần tử bị lỗi, một số phần tử khác có thể đã được ghi tùy chế độ ordered/unordered và trạng thái thực thi. Không coi `insertMany` nhiều document tương đương transaction toàn bộ; nếu bắt buộc tất cả thành công cùng nhau, phải xem transaction hoặc một workflow có thể đối soát.

## 5. Upsert: tạo nếu chưa có, cập nhật nếu đã có

Một thao tác **upsert** kết hợp create và update:

~~~javascript
db.productSettings.updateOne(
  { _id: "t01:catalog" },
  {
    $set: { locale: "vi", updatedAt: new Date() },
    $setOnInsert: {
      createdAt: new Date(),
      schemaVersion: 1
    }
  },
  { upsert: true }
);
~~~

`$setOnInsert` chỉ dùng khi upsert sinh record mới. Nếu record đã tồn tại, `$set` thay field tương ứng. Trong cạnh tranh nhiều writer, cần unique index/primary key và xử lý duplicate/retry.

**Không dùng upsert thay create-only** nếu nghiệp vụ yêu cầu từ chối tạo trùng. Upsert có thể sửa tài nguyên cũ khi caller tưởng đang tạo tài nguyên mới. Với API PUT-as-upsert phải ghi rõ hợp đồng: tạo khi thiếu hay trả `404`, có yêu cầu `If-Match`/`If-None-Match` hay không.

## 6. Read theo ID và phạm vi tenant

Đọc một record:

~~~javascript
db.products.findOne({
  _id: "p100",
  tenantId: "t01"
});
~~~

Đọc ít field cần thiết:

~~~javascript
db.products.findOne(
  { _id: "p100", tenantId: "t01" },
  {
    _id: 1,
    sku: 1,
    name: 1,
    priceMinor: 1,
    currency: 1,
    status: 1
  }
);
~~~

Projection giúp giảm dữ liệu truyền và tránh trả các trường nội bộ không cần thiết. Tuy nhiên, một filter `tenantId` trong query không tự tạo cơ chế ủy quyền; tenant phải lấy từ ngữ cảnh được xác thực và tất cả truy vấn/đường ghi phải tuân thủ quy tắc truy cập. Việc trả `404` hay `403` cần được thiết kế để không tiết lộ tài nguyên của tenant khác.

Đọc trên replica hoặc projection có thể chậm hơn dữ liệu vừa ghi; API cần nêu rõ read-after-write và consistency contract.

## 7. Read danh sách: filter, sort, limit

~~~javascript
db.products.find(
  {
    tenantId: "t01",
    status: "ACTIVE"
  },
  {
    name: 1,
    sku: 1,
    priceMinor: 1,
    updatedAt: 1
  }
).sort({
  updatedAt: -1,
  _id: 1
}).limit(20);
~~~

Một query tốt có:

1. **Filter** đủ cụ thể và đúng quyền truy cập.
2. **Index** hỗ trợ đường lọc/sắp xếp.
3. **Projection** chỉ trả field cần thiết.
4. **Limit/pagination** giới hạn payload và tài nguyên.
5. **Thứ tự ổn định** khi nhiều bản ghi có cùng khóa sort.

Với dữ liệu lớn, câu lệnh lọc một field không có index có thể dẫn tới quét nhiều document. Dùng `explain("executionStats")` trong môi trường thử để quan sát keys/docs examined, plan và sort. Việc query nhanh trên 100 record không chứng minh chạy nhanh trên hàng chục triệu record.

### 7.1. Offset và seek pagination

Offset:

~~~javascript
db.products.find({
  tenantId: "t01",
  status: "ACTIVE"
}).sort({
  updatedAt: -1, _id: 1
}).skip(10000).limit(20);
~~~

Với trang sâu, `skip` có thể tăng công việc. Dữ liệu thay đổi giữa các request còn khiến một số record bị lặp hoặc bỏ sót.

Seek/cursor pagination dùng khóa cuối của trang trước, theo thứ tự `updatedAt DESC, _id ASC`:

~~~javascript
const lastUpdatedAt = ISODate("2026-11-14T07:30:00Z");
const lastId = "p100";

db.products.find({
  tenantId: "t01",
  status: "ACTIVE",
  $or: [
    { updatedAt: { $lt: lastUpdatedAt } },
    {
      updatedAt: lastUpdatedAt,
      _id: { $gt: lastId }
    }
  ]
}).sort({
  updatedAt: -1, _id: 1
}).limit(20);
~~~

Cursor cần gắn với tenant, query filter và sort. Nếu `updatedAt` của document thay đổi giữa hai trang, seek pagination không mặc nhiên có snapshot bất biến; cần quy tắc rõ về dữ liệu động.

## 8. Query trên nested object và array

Ví dụ document:

~~~javascript
{
  _id: "p200",
  tenantId: "t01",
  variants: [
    { sku: "P200-BLACK-M", color: "black", size: "M", stock: 4 },
    { sku: "P200-WHITE-L", color: "white", size: "L", stock: 0 }
  ]
}
~~~

Nếu cần **cùng một variant** vừa màu black vừa stock ít nhất 2, dùng:

~~~javascript
db.products.find({
  tenantId: "t01",
  variants: {
    $elemMatch: {
      color: "black",
      stock: { $gte: 2 }
    }
  }
});
~~~

Hai điều kiện độc lập `"variants.color": "black"` và `"variants.stock": {$gte:2}` có thể khớp ở **hai phần tử khác nhau**. Không chọn query chỉ vì cú pháp ngắn mà bỏ mất ngữ nghĩa của yêu cầu.

## 9. Replace: cung cấp toàn bộ bản ghi mới

`replaceOne` dùng một replacement document thay cho document khớp filter:

~~~javascript
db.products.replaceOne(
  {
    _id: "p100",
    tenantId: "t01"
  },
  {
    _id: "p100",
    tenantId: "t01",
    sku: "MOUSE-01",
    name: "Wireless Mouse V2",
    priceMinor: NumberLong("2799"),
    currency: "USD",
    availableStock: 12,
    status: "ACTIVE",
    version: 2
  }
);
~~~

Với ví dụ trước đó, các field không nằm trong replacement như `description`, `tags` và `attributes` bị loại khỏi document được thay. `_id` là định danh không thể đổi bằng replace.

**Replace phù hợp khi** caller sở hữu toàn bộ trạng thái cần ghi, ví dụ đồng bộ snapshot hoàn chỉnh từ nguồn chuẩn, hoặc muốn loại các trường không còn hợp lệ. **Không phù hợp khi** một form chỉ cho sửa tên/giá, hoặc một ứng dụng phiên bản cũ không biết những field mới mà ứng dụng khác vừa thêm.

## 10. Replace có điều kiện tránh lost update

Giả sử hai admin cùng đọc product tại `version=4`. Admin A sửa tên, Admin B sửa giá trên snapshot cũ. Nếu cả hai replace không điều kiện, người ghi sau có thể xóa thay đổi của người ghi trước.

Dùng optimistic concurrency:

~~~javascript
const expectedVersion = 4;

const replacement = {
  _id: "p100",
  tenantId: "t01",
  sku: "MOUSE-01",
  name: "Wireless Mouse Pro",
  description: "Updated description",
  priceMinor: NumberLong("2799"),
  currency: "USD",
  availableStock: 12,
  tags: ["wireless", "mouse"],
  attributes: { color: "black", warrantyMonths: 12 },
  status: "ACTIVE",
  version: expectedVersion + 1,
  createdAt: ISODate("2026-11-14T08:00:00Z"),
  updatedAt: new Date()
};

const result = db.products.replaceOne(
  {
    _id: "p100",
    tenantId: "t01",
    version: expectedVersion
  },
  replacement
);

if (result.matchedCount === 0) {
  print("NOT_FOUND_OR_VERSION_CONFLICT");
}
~~~

Một writer đã tăng version khiến writer khác dùng version cũ không khớp. Ứng dụng cần đọc lại/hiển thị conflict hoặc merge theo luật nghiệp vụ, không tự thay snapshot cũ bằng cách tăng expectedVersion để ép ghi đè.

Mọi writer quan trọng phải tuân thủ version; chỉ một worker cũ ghi không điều kiện có thể phá cơ chế này.

## 11. Partial update: thay một vài field bằng $set

Khi chỉ đổi tên/giá, dùng `updateOne` thay vì replace:

~~~javascript
db.products.updateOne(
  {
    _id: "p100",
    tenantId: "t01"
  },
  {
    $set: {
      name: "Wireless Mouse Pro",
      priceMinor: NumberLong("3299"),
      updatedAt: new Date()
    }
  }
);
~~~

Các field `tags`, `description`, `attributes`, `availableStock` vẫn được giữ. Tuy nhiên, partial update cũng phải kiểm soát caller được sửa field nào và có version check hay không.

### 11.1. Field lồng nhau và dot notation

~~~javascript
db.products.updateOne(
  { _id: "p100", tenantId: "t01" },
  {
    $set: {
      "attributes.color": "silver",
      "attributes.warrantyMonths": 24
    }
  }
);
~~~

Hai dot-path chỉ sửa các trường tương ứng. Nếu thay bằng:

~~~javascript
db.products.updateOne(
  { _id: "p100", tenantId: "t01" },
  {
    $set: {
      attributes: { color: "silver" }
    }
  }
);
~~~

toàn bộ object `attributes` bị thay bằng object mới, và `warrantyMonths` có thể biến mất. **Partial update ở cấp document không có nghĩa nested object được deep-merge tự động**.

### 11.2. $unset khác gán null

~~~javascript
// Bỏ field khỏi document.
db.products.updateOne(
  { _id: "p100", tenantId: "t01" },
  { $unset: { description: "" } }
);

// Giữ field với giá trị BSON null.
db.products.updateOne(
  { _id: "p100", tenantId: "t01" },
  { $set: { description: null } }
);
~~~

Missing và explicit null có thể khác nhau trong validation, mặc định nghiệp vụ, chỉ mục và query. Trong MongoDB, predicate `{field:null}` có thể khớp cả missing; muốn tách cần dùng `$exists` hoặc `$type` phù hợp.

## 12. Những toán tử cập nhật từng phần thông dụng

| Toán tử | Tác dụng | Ví dụ |
|---|---|---|
| `$set` | Gán giá trị field | Đổi tên, trạng thái |
| `$unset` | Bỏ field | Xóa optional attribute |
| `$inc` | Cộng/trừ số | Counter, stock có điều kiện |
| `$min` / `$max` | Chỉ thay khi nhỏ/lớn hơn | Giữ mốc thống kê |
| `$mul` | Nhân số | Biến đổi số theo quy tắc kiểm soát |
| `$addToSet` | Thêm phần tử nếu chưa có giá trị tương đương | Tags không trùng |
| `$push` | Thêm phần tử, có thể trùng | Danh sách có thứ tự |
| `$pull` | Bỏ các phần tử khớp | Xóa tag |
| `$currentDate` | Đặt date/timestamp theo cơ chế DB | updatedAt |
| `$setOnInsert` | Chỉ ghi khi upsert tạo record | createdAt mặc định |

### 12.1. $inc và race khi tăng counter

Nếu hai request cùng đọc `viewCount=10` rồi cùng ghi 11, tổng mất một lượt. Dùng:

~~~javascript
db.products.updateOne(
  { _id: "p100", tenantId: "t01" },
  {
    $inc: { viewCount: 1 },
    $currentDate: { updatedAt: true }
  }
);
~~~

Một phép `$inc` trên document dùng giá trị hiện tại cho update. Nhưng nếu client timeout sau khi đã commit rồi retry, counter có thể tăng **hai** lần. Cần phân biệt **atomic increment** với **exactly-once event processing**; với thống kê cần khử trùng theo event ID hoặc chấp nhận sai lệch theo hợp đồng.

### 12.2. Mảng: $addToSet, $push và $pull

~~~javascript
db.products.updateOne(
  { _id: "p100", tenantId: "t01" },
  { $addToSet: { tags: "bluetooth" } }
);

db.products.updateOne(
  { _id: "p100", tenantId: "t01" },
  { $push: { tags: "bluetooth" } }
);

db.products.updateOne(
  { _id: "p100", tenantId: "t01" },
  { $pull: { tags: "mouse" } }
);
~~~

`$addToSet` chỉ kiểm tra phần tử tương đương trong mảng, không thay thế mọi ràng buộc uniqueness nghiệp vụ. `$push` cho phép giá trị lặp. Với mảng tăng không giới hạn, document có thể ngày càng lớn và gây chi phí update/index; nên tách lịch sử click/log sang collection riêng nếu phù hợp.

## 13. Partial update của một phần tử trong array

Với variants của `p200`:

~~~javascript
db.products.updateOne(
  { _id: "p200", tenantId: "t01" },
  {
    $set: {
      "variants.$[v].stock": 6
    }
  },
  {
    arrayFilters: [
      { "v.sku": "P200-BLACK-M" }
    ]
  }
);
~~~

`arrayFilters` cho phép chọn phần tử mảng theo điều kiện. Nếu nhiều phần tử có cùng SKU, một filter có thể khớp nhiều phần tử; cần thiết kế uniqueness trong aggregate.

Nếu đây là thao tác cấp phát stock trong lúc concurrent request, dùng `$set stock=6` cố định là sai hướng. Cần điều kiện `stock >= q` và phép giảm nguyên tử ở đúng phần tử, cùng cơ chế idempotency của ý định đặt hàng. Không đồng nhất cú pháp update array với một giao dịch tồn kho an toàn.

## 14. Cập nhật có điều kiện bảo vệ bất biến

Giả sử người dùng muốn giữ 3 sản phẩm, và `availableStock` không được âm:

~~~javascript
const qty = 3;

const result = db.products.updateOne(
  {
    _id: "p100",
    tenantId: "t01",
    status: "ACTIVE",
    availableStock: { $gte: qty }
  },
  {
    $inc: {
      availableStock: -qty,
      version: 1
    },
    $currentDate: { updatedAt: true }
  }
);

if (result.matchedCount !== 1) {
  print("NOT_AVAILABLE_OR_NOT_FOUND");
}
~~~

Cả điều kiện `availableStock >= qty` và phép giảm nằm trong một thao tác trên document, nên nhiều request không thể cùng vượt qua dựa trên snapshot cũ để trừ quá số hiện có.

**Nhưng ví dụ này chưa đủ để tạo Reservation.** Nếu giảm Product thành công rồi process chết trước khi ghi Reservation, stock bị giữ mà không có thông tin để hoàn. Muốn workflow đúng cần transaction đa document hoặc state machine/saga và reconciliation theo thiết kế.

### 14.1. Version CAS khi sửa giá

~~~javascript
const expectedVersion = 7;

const result = db.products.updateOne(
  {
    _id: "p100",
    tenantId: "t01",
    version: expectedVersion
  },
  {
    $set: { priceMinor: NumberLong("3499") },
    $inc: { version: 1 },
    $currentDate: { updatedAt: true }
  }
);

if (result.matchedCount === 0) {
  print("CONFLICT_OR_NOT_FOUND");
}
~~~

CAS theo `version` ngăn writer stale ghi đè giá mới hơn. Nếu không khớp, đọc lại rồi quyết định merge hoặc trả conflict; không đổi expectedVersion mù quáng để ép ghi.

## 15. updateOne và updateMany khác nhau ở phạm vi

`updateOne` sửa tối đa một document khớp:

~~~javascript
db.products.updateOne(
  { _id: "p100", tenantId: "t01" },
  { $set: { status: "INACTIVE" } }
);
~~~

`updateMany` sửa nhiều document khớp:

~~~javascript
db.products.updateMany(
  {
    tenantId: "t01",
    category: "Discontinued"
  },
  {
    $set: { status: "INACTIVE" },
    $currentDate: { updatedAt: true }
  }
);
~~~

Không mặc định một `updateMany` trên hàng nghìn document là transaction all-or-nothing; nếu bị ngắt, một phần có thể đã cập nhật. Cần batch, checkpoint và retry idempotent cho migration lớn, đồng thời đo mức tải ghi.

**Không sử dụng filter rỗng một cách vô ý.** `updateMany({}, ...)` có thể cập nhật toàn collection; một biến filter sai do lỗi ứng dụng có thể gây hậu quả lớn.

## 16. Hiểu kết quả thao tác: matched, modified, upserted

MongoDB báo các chỉ số như:

- `matchedCount`: số document khớp filter.
- `modifiedCount`: số document thực sự có thay đổi.
- `upsertedId`: ID record được tạo nếu upsert sinh bản ghi.

Một document đã `status="ACTIVE"` có thể khớp lệnh `$set status="ACTIVE"` nhưng không thay đổi nội dung, nên `matchedCount=1` và `modifiedCount=0` có thể là kết quả bình thường.

Khi `matchedCount=0` với điều kiện `version=7`, có thể record không tồn tại, sai tenant hoặc đã được nâng version. API cần trả status phù hợp mà không tiết lộ tài nguyên ngoài quyền.

Nếu cần đọc document **ngay sau update một cách có phối hợp**, xem `findOneAndUpdate` với tùy chọn trả trước/sau theo driver. Update rồi GET riêng có thể bị request khác xen vào, nên kết quả GET không nhất thiết là trạng thái do chính update của mình tạo.

## 17. Delete: xóa một document hoặc nhiều document

Xóa một document theo key và tenant:

~~~javascript
db.products.deleteOne({
  _id: "p102",
  tenantId: "t01"
});
~~~

`deletedCount` cho biết số document bị xóa. Gọi lại lần hai có thể trả `deletedCount=0`; hợp đồng API phải xác định đây là idempotent success hay “not found”.

Xóa theo filter lớn:

~~~javascript
// Chỉ minh họa trong môi trường học với dữ liệu có thể phục hồi.
db.products.deleteMany({
  tenantId: "t01",
  status: "ARCHIVED"
});
~~~

Không chạy `deleteMany({})` trong môi trường thật nếu không chủ đích xóa toàn bộ collection. Xóa theo batch cần xác nhận phạm vi, backup, quyền, retention, số record trước/sau, monitor replication và kế hoạch xử lý khi một phần đã xóa.

### 17.1. Delete có điều kiện theo version

~~~javascript
db.products.deleteOne({
  _id: "p100",
  tenantId: "t01",
  version: 8
});
~~~

Nếu product đã thay đổi lên version 9, delete không khớp; ứng dụng có thể trả conflict thay vì xóa dữ liệu vừa được người khác chỉnh sửa. Điều kiện này chỉ hữu ích nếu các đường ghi quan trọng đều duy trì version đúng.

## 18. Soft delete, hard delete và tham chiếu lịch sử

**Hard delete** yêu cầu loại bỏ bản ghi theo cơ chế database. **Soft delete** giữ record nhưng đặt trạng thái ngừng sử dụng:

~~~javascript
db.products.updateOne(
  {
    _id: "p100",
    tenantId: "t01",
    deletedAt: { $exists: false }
  },
  {
    $set: {
      status: "DELETED",
      deletedAt: new Date()
    },
    $inc: { version: 1 }
  }
);
~~~

Query công khai cần loại record DELETED:

~~~javascript
db.products.find({
  tenantId: "t01",
  status: "ACTIVE",
  deletedAt: { $exists: false }
});
~~~

Lợi ích của soft delete: audit, khả năng khôi phục, giữ tham chiếu với Order cũ. Hạn chế: code phải lọc nhất quán, record vẫn tốn lưu trữ/index, và unique index có thể không cho tạo SKU mới trùng SKU của product đã xóa.

Nếu nghiệp vụ muốn tái sử dụng SKU sau soft delete, có thể cần partial unique index hoặc chính sách khác; phải giải quyết khi một bản ghi cũ được restore. Không tự đổi uniqueness khi chưa định nghĩa business invariant.

**Không nên xóa cứng product đang được Order lịch sử tham chiếu** nếu Order không có snapshot và nghĩa vụ lưu trữ bắt buộc. Quyết định delete cần xét Order, audit, cache, search, backups và retention.

## 19. TTL không đồng nghĩa logic xóa ngay tức thì

Một số hệ NoSQL có TTL để tự hết hạn dữ liệu session, cache hoặc log.

MongoDB ví dụ:

~~~javascript
db.sessions.createIndex(
  { expiresAt: 1 },
  { expireAfterSeconds: 0 }
);
~~~

TTL monitor không bảo đảm record bị xóa đúng microsecond khi tới `expiresAt`. Do đó API xác thực session vẫn phải kiểm tra thời hạn tại thời điểm sử dụng, không dựa hoàn toàn vào việc document đã biến mất.

Tương tự, Reservation hết hạn cần chuyển trạng thái và trả quota theo workflow; **TTL xóa Reservation không tự tăng availableStock của Product**. Xóa bằng TTL trong Cassandra/Redis/DynamoDB có semantics và độ trễ khác nhau, phải xem tài liệu từng sản phẩm.

## 20. CRUD và transaction nhiều document

Một nghiệp vụ “đặt 2 sản phẩm” có thể cần:

~~~text
1. Giảm availableStock của Product
2. Tạo Reservation
3. Đổi Order sang HELD
4. Ghi OutboxEvent
~~~

Update một document nguyên tử không chứng minh cả bốn bước cùng thành công. Nếu crash giữa 1 và 2, stock có thể bị giữ nhưng không có Reservation.

Các hướng thiết kế:

- **Transaction nhiều document:** khi database/topology hỗ trợ, kiểm tra isolation và chi phí.
- **Aggregate root hợp lý:** gom những gì cần nguyên tử trong một ranh giới đủ nhỏ.
- **Saga/state machine:** các bước có trạng thái, compensation và reconciliation.
- **Outbox/CDC:** đồng bộ projection sau commit, replay được và khử trùng sự kiện.
- **CAS/conditional updates:** từ chối các write cạnh tranh dựa trên trạng thái cũ.

Một thao tác trừ có điều kiện ngăn stock âm nhưng **không tự bảo đảm idempotency**. Nếu request trừ 2 đã commit và response mất, retry có thể tiếp tục trừ 2 nếu còn hàng. Muốn “một ý định chỉ thực hiện một lần” cần idempotency key và bản ghi kết quả đủ bền, thường trong cùng giao thức transaction.

## 21. Đọc sau ghi, replica và projection

Trong hệ phân tán, dữ liệu có thể được nhân bản hoặc lập chỉ mục bất đồng bộ. Một ghi thành công trên nguồn chuẩn chưa chắc ngay lập tức được nhìn thấy ở mọi replica, cache hoặc search index.

Cần đặt hợp đồng cho từng use case:

- Sửa tên Product rồi mở trang chi tiết: người dùng có phải thấy ngay không?
- Search index cập nhật chậm 2 giây: sản phẩm INACTIVE có còn hiện không?
- Sau DELETE, cache stale có thể còn trả dữ liệu trong bao lâu?
- Nếu client timeout sau write, có thể xác định commit bằng ID/version không?
- Nếu replica của một vùng bị lỗi, nguồn nào được dùng khi yêu cầu tính đúng đắn mạnh?

Đừng dùng dữ liệu từ search/cache chưa chắc kịp đồng bộ làm nguồn ra quyết định trừ stock hoặc thanh toán. API cần chỉ rõ mức freshness, read/write concern hoặc consistency level theo sản phẩm.

## 22. CRUD qua HTTP: POST, GET, PUT, PATCH và DELETE

Tên HTTP method không tương đương một-một với tên lệnh database.

| HTTP method | Ý nghĩa phổ biến | Cách triển khai có thể có |
|---|---|---|
| `POST /products` | Tạo tài nguyên mới | `insertOne` + uniqueness/idempotency |
| `GET /products/{id}` | Đọc tài nguyên | `findOne` + projection |
| `PUT /products/{id}` | Thay representation | `replaceOne`/upsert có điều kiện |
| `PATCH /products/{id}` | Thay một phần representation | `updateOne` với allowlist |
| `DELETE /products/{id}` | Yêu cầu xóa | `deleteOne` hoặc soft delete |

### 22.1. PUT thay toàn bộ representation

~~~http
PUT /v1/products/p100
If-Match: "7"
Content-Type: application/json

{
  "sku": "MOUSE-01",
  "name": "Wireless Mouse Pro",
  "priceMinor": 3299,
  "currency": "USD",
  "status": "ACTIVE"
}
~~~

Nếu API định nghĩa PUT là replace, trường thiếu có thể bị loại/reset. Những trường server-managed như `tenantId`, `version`, `createdAt` cần được giữ/quản lý theo hợp đồng riêng; không tự cho client thay toàn bộ nội dung DB. `If-Match` theo ETag/version giúp chặn snapshot stale và có thể trả `412 Precondition Failed` khi không khớp.

### 22.2. PATCH chỉ sửa một phần

~~~http
PATCH /v1/products/p100
If-Match: "7"
Content-Type: application/merge-patch+json

{
  "name": "Wireless Mouse Pro"
}
~~~

JSON Merge Patch và JSON Patch có ngữ nghĩa khác nhau. Ví dụ trong Merge Patch, một member gán `null` có thể là chỉ thị xóa member; trong JSON Patch, hành động xóa thường là operation `remove`. Server cần công bố rõ media type/format, không để mọi client đoán `null` nghĩa là gì.

### 22.3. Idempotency của HTTP không thay thế logic server

Về ngữ nghĩa HTTP, PUT và DELETE được thiết kế idempotent theo trạng thái mong muốn. Nhưng một implementation tăng viewCount, gửi email hoặc tạo payment attempt mỗi lần PUT/DELETE được gọi vẫn có thể tạo side effect trùng. PATCH dạng increment cũng không idempotent trừ khi được bọc bằng một ý định có ID ổn định. Phải kiểm tra hành vi thực tế của hệ thống.

## 23. Redis: thao tác theo key, string và hash

Redis không có `replaceOne` document giống MongoDB; ý nghĩa cập nhật phụ thuộc kiểu dữ liệu.

Tạo một string key **chỉ khi chưa có**:

~~~redis
SET product:t01:p100 "{\"name\":\"Wireless Mouse\",\"status\":\"ACTIVE\"}" NX
~~~

Đọc:

~~~redis
GET product:t01:p100
~~~

Thay cả string value nếu key đang tồn tại:

~~~redis
SET product:t01:p100 "{\"name\":\"Wireless Mouse Pro\",\"status\":\"ACTIVE\"}" XX
~~~

Lệnh SET thay toàn bộ string, không merge JSON. Ngoài ra SET có ảnh hưởng TTL theo option; muốn giữ expiry cần kiểm tra `KEEPTTL` hoặc cơ chế tương ứng.

Redis hash hỗ trợ sửa field:

~~~redis
HSET product-hash:t01:p100 name "Wireless Mouse" status "ACTIVE"
HSET product-hash:t01:p100 name "Wireless Mouse Pro"
HGETALL product-hash:t01:p100
HDEL product-hash:t01:p100 status
DEL product-hash:t01:p100
~~~

Một lệnh Redis có tính nguyên tử trong phạm vi server thực thi, nhưng nhiều lệnh đọc–kiểm tra–ghi vẫn có thể tranh chấp. Với Redis Cluster, thao tác liên quan nhiều key có giới hạn hash slot; khi cần durability/failover, cần đánh giá replication và persistence chứ không chỉ cú pháp.

## 24. DynamoDB: PutItem khác UpdateItem

Một bảng DynamoDB dùng item với partition key và có thể sort key. Các API có vai trò khác nhau:

| API | Ý nghĩa và giới hạn |
|---|---|
| `PutItem` | Ghi toàn item; có thể thay item cũ cùng key nếu thiếu condition |
| `GetItem` | Đọc theo primary key, consistency tùy loại đọc |
| `Query` | Lọc theo key/index phù hợp |
| `UpdateItem` | Sửa thuộc tính, có điều kiện với SET/REMOVE/ADD... |
| `DeleteItem` | Xóa theo key, có thể dùng condition |
| `Scan` | Duyệt rộng, cần kiểm soát chi phí |

Create-only bằng condition (pseudocode, không phải SDK request đầy đủ):

~~~text
PutItem(
  TableName = "Products",
  Item = {
    PK: "TENANT#t01",
    SK: "PRODUCT#p100",
    name: "Wireless Mouse"
  },
  ConditionExpression = "attribute_not_exists(PK)"
)
~~~

Update một thuộc tính với version (pseudocode):

~~~text
UpdateItem(
  Key = { PK:"TENANT#t01", SK:"PRODUCT#p100" },
  ConditionExpression = "version = :expected",
  UpdateExpression = "SET #name = :name, version = version + :one",
  ExpressionAttributeNames = { "#name": "name" },
  ExpressionAttributeValues = { ... }
)
~~~

`PutItem` không có condition có thể ghi đè item hiện hữu và bỏ những thuộc tính cũ không có trong item mới. `UpdateItem` không có condition tồn tại có thể tạo item chỉ gồm key và các field update theo semantics API. Nếu cần transaction nhiều item, xem `TransactWriteItems` và giới hạn cụ thể. TTL của DynamoDB là cơ chế dọn dữ liệu bất đồng bộ, không đồng nghĩa hết hạn nghiệp vụ chính xác.

## 25. Cassandra: INSERT và UPDATE theo kiểu upsert

Cassandra tổ chức hàng theo partition key và clustering columns:

~~~sql
CREATE TABLE products_by_tenant (
    tenant_id text,
    product_id text,
    name text,
    price_minor bigint,
    status text,
    version int,
    PRIMARY KEY ((tenant_id), product_id)
);
~~~

Đọc đúng đường khóa:

~~~sql
SELECT product_id, name, price_minor, status
FROM products_by_tenant
WHERE tenant_id = 't01'
  AND product_id = 'p100';
~~~

Ghi:

~~~sql
INSERT INTO products_by_tenant
(tenant_id, product_id, name, price_minor, status, version)
VALUES ('t01', 'p100', 'Wireless Mouse', 2999, 'ACTIVE', 1);
~~~

Trong Cassandra, `INSERT` thường có semantics upsert theo primary key; không mặc định lỗi duplicate giống `insertOne` ở MongoDB. Muốn create-only, có thể dùng conditional form:

~~~sql
INSERT INTO products_by_tenant
(tenant_id, product_id, name, price_minor, status, version)
VALUES ('t01', 'p101', 'Keyboard', 8999, 'ACTIVE', 1)
IF NOT EXISTS;
~~~

Partial update cột:

~~~sql
UPDATE products_by_tenant
SET name = 'Wireless Mouse Pro'
WHERE tenant_id = 't01'
  AND product_id = 'p100';
~~~

Các điểm khác MongoDB:

- Không có document replace tương đương `replaceOne` trên toàn document.
- `UPDATE` cũng có thể tạo một số dữ liệu theo key nếu hàng chưa tồn tại.
- `DELETE` tạo tombstone trong mô hình lưu trữ LSM; cần hiểu compaction/repair.
- Truy vấn theo khóa/phân vùng đã thiết kế, không tùy tiện JOIN/lọc mọi field.
- Conditional write/LWT có phạm vi và chi phí riêng, không suy ra transaction toàn cụm đa partition.
- TTL và tombstone ảnh hưởng chi phí vận hành và query.

## 26. Khi nào chọn replace, partial update, upsert và delete?

| Tình huống | Hướng chọn | Lý do |
|---|---|---|
| Nhận snapshot hoàn chỉnh từ nguồn chuẩn | Replace có điều kiện | Chủ động xác định toàn bộ trạng thái |
| Form chỉ sửa tên | Partial `$set` | Không làm mất field khác |
| Thêm tag không trùng | `$addToSet` hoặc phép tương đương | Đúng semantics set |
| Tăng lượt xem | Atomic increment | Tránh lost update read–set |
| Trừ stock còn đủ | Conditional decrement | Bảo vệ không âm |
| Tạo duy nhất theo SKU | Insert + unique constraint | Không ghi đè khi trùng |
| Đồng bộ projection theo sự kiện có version | Upsert/conditional write | Có thể replay và chống out-of-order |
| Xóa dữ liệu hết hạn theo retention | TTL/hard delete khi phù hợp | Kiểm soát lifecycle |
| Ngừng bán nhưng giữ Order lịch sử | Soft delete/status | Giữ audit và tham chiếu |
| Thay toàn bộ product từ UI phiên bản cũ | Thường không nên | Dễ xóa field mới chưa biết |

Quy tắc cốt lõi: **Replace khi người ghi thật sự biết và sở hữu toàn bộ trạng thái; partial update khi chỉ muốn thay một phần.** Với concurrent write, cả hai đều cần điều kiện/version/idempotency nếu nghiệp vụ đòi hỏi.

## 27. Thực hành vòng đời một product

Trên database `nosql_crud_lab`:

1. **Create:** thêm `p300` có tenant, SKU, giá, status và version; thử insert lại cùng ID và SKU khác ID để quan sát uniqueness.
2. **Read:** đọc theo ID/tenant, dùng projection, lọc ACTIVE và sort, xem query plan khi có index.
3. **Replace:** sao lưu bản gốc trong môi trường thực hành; replace `p300` cố tình thiếu `tags` rồi đọc lại để hiểu field bị loại.
4. **Partial:** đổi `attributes.color` qua dot path; thêm tag qua `$addToSet`; tăng `viewCount` qua `$inc`; bỏ optional `description` qua `$unset`.
5. **Delete:** soft-delete một product, kiểm tra không còn trong query ACTIVE; xóa cứng đúng key, rồi gọi delete lại và xem `deletedCount`.

Ví dụ các partial updates:

~~~javascript
db.products.updateOne(
  { _id: "p300", tenantId: "t01" },
  { $set: { "attributes.color": "blue" } }
);

db.products.updateOne(
  { _id: "p300", tenantId: "t01" },
  { $addToSet: { tags: "featured" } }
);

db.products.updateOne(
  { _id: "p300", tenantId: "t01" },
  { $inc: { viewCount: 1 } }
);

db.products.updateOne(
  { _id: "p300", tenantId: "t01" },
  { $unset: { description: "" } }
);
~~~

Giải thích sự khác nhau giữa `$set` một nested path và `$set` toàn object `attributes`.

## 28. Thực nghiệm đồng thời và retry

### 28.1. Hai admin cùng sửa

1. Tạo product `p400` với `version=1`.
2. Hai client đều đọc bản version 1.
3. Client A sửa tên qua CAS và tăng version.
4. Client B cố replace snapshot cũ với điều kiện `version=1`.
5. Xác nhận chỉ một thao tác thắng và dữ liệu của A không bị ghi đè.
6. Viết lại cách client B phản hồi conflict bằng đọc lại/merge.

### 28.2. Một trăm yêu cầu tranh 10 sản phẩm

Giả lập 100 request đồng thời, mỗi request giảm `availableStock` 1 từ pool có 10 sản phẩm:

~~~text
for each request i = 1..100 concurrently:
  updateOne(
    filter: {
      productId: "p400",
      availableStock: { $gte: 1 }
    },
    update: {
      $inc: { availableStock: -1 }
    }
  )

assert availableStock >= 0
assert successfulDecrements <= 10
~~~

Đây là test safety của counter, không phải test “mỗi ý định chỉ ghi một lần”. Nếu cùng request retry khi response mất, muốn chống double allocation phải lưu business ID/Reservation trong cơ chế nhất quán phù hợp.

### 28.3. Retry create sau khi mất response

Gửi tạo `p401` với ID cố định, giả lập server commit rồi mất response, gửi lại cùng ID/payload. API phải có cơ chế trả kết quả cũ hoặc xung đột được phân loại đúng, không tạo `p402` mới. Gửi cùng idempotency key nhưng payload khác phải bị từ chối.

### 28.4. Xóa và sửa tranh nhau

Client A đọc product version 3; client B soft-delete và tăng version 4; client A cố cập nhật giá với filter `status=ACTIVE, version=3`. A phải thất bại theo điều kiện, không vô tình làm sống lại product đã xóa.

## 29. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Biện pháp |
|---|---|---|
| Replace khi chỉ sửa một field | Mất trường khác | Partial update |
| Update không condition từ snapshot cũ | Lost update | CAS/version |
| $set toàn nested object | Xóa field con không gửi | Dot-path |
| $push khi muốn unique tags | Giá trị trùng | $addToSet + rule nghiệp vụ |
| Query mảng bằng nhiều điều kiện độc lập | Khớp các phần tử khác nhau | $elemMatch |
| GET rồi SET counter | Mất cập nhật đồng thời | $inc hoặc phép atomic |
| Retry decrement không có business key | Trừ nhiều lần | Idempotency + trạng thái bền |
| Upsert trong create-only | Ghi đè dữ liệu cũ | Insert + uniqueness |
| modifiedCount=0 bị hiểu là not found | Nhầm no-op | Kiểm tra matchedCount |
| deleteMany thiếu điều kiện tenant | Xóa nhầm diện rộng | Allowlist/filter có guard |
| TTL được coi là timer nghiệp vụ | Sai hạn hoặc không hoàn quota | State transition có điều kiện |
| PUT của client cũ thay cả DB document mới | Xóa field schema mới | Writer compatibility |
| Chỉ đo CRUD tuần tự | Bỏ sót race và hot key | Concurrent/failure tests |

## 30. Giám sát CRUD trong vận hành

| Nhóm | Chỉ số |
|---|---|
| Create | Duplicate key, conflict, idempotency reuse, p95 |
| Read | p50/p95/p99, docs examined, index usage, bytes trả |
| Replace | Version conflict, payload size, field loss |
| Partial update | Matched/modified ratio, CAS retries, hot key, timeout |
| Delete | Soft/hard delete count, retention, propagation lag |
| Replication | Read freshness, replica lag, unknown commit |
| Projection | Search/cache lag, stale data, replay backlog |
| Tài nguyên | CPU/RAM/disk I/O, index size, connection pool |

Không log thông tin nhạy cảm nguyên văn khi không cần; dùng correlation ID, mã lỗi, tenant scope và quyền tối thiểu. Đo cả offered load lẫn throughput đạt được; hệ từ chối mọi thao tác để giữ safety không phải một hệ hữu dụng.

## 31. Câu hỏi tự kiểm tra

1. Replace và partial update khác nhau ở việc giữ field không gửi lên thế nào?
2. Vì sao một bản replace không thể đổi `_id` hiện hữu?
3. Upsert khác insert create-only thế nào?
4. Khi `matchedCount=1, modifiedCount=0` có nhất thiết là lỗi không?
5. Query projection có thay thế authorization không?
6. Sort ổn định và cursor pagination giúp gì, có bảo đảm snapshot không?
7. Khi nào phải dùng `$elemMatch` trong mảng object?
8. `$set` nested path khác `$set` toàn object ở hậu quả gì?
9. `$unset` khác gán `null` thế nào?
10. Vì sao `$inc` giảm race nhưng không chống retry tính hai lần?
11. CAS theo `version` giải quyết loại tranh chấp nào?
12. Vì sao updateMany không mặc định là transaction toàn bộ?
13. Soft delete và hard delete khác nhau ở retention/khôi phục ra sao?
14. TTL có thực hiện xóa chính xác tại thời điểm hết hạn không?
15. DynamoDB PutItem và MongoDB insertOne khác nhau thế nào nếu key đã tồn tại?
16. Cassandra INSERT/UPDATE có đặc tính upsert gì?
17. Redis SET string khác HSET field ra sao?
18. HTTP PUT và PATCH cần quy định field thiếu/null như thế nào?
19. Tại sao cập nhật Product atomic chưa đủ cho workflow Order/Reservation?
20. Sau khi commit nhưng mất response, làm sao tránh tạo thêm hoặc trừ thêm?

## 32. Kết luận

CRUD trong NoSQL là **cách diễn đạt ý định thay đổi dữ liệu**, không chỉ là năm lệnh của driver. Create cần uniqueness và idempotency; Read cần access pattern, index, projection và bảo mật; Replace cần snapshot đầy đủ và kiểm soát version; Partial update cần toán tử/đường dẫn đúng cùng điều kiện bảo vệ bất biến; Delete cần chính sách vòng đời dữ liệu và xử lý tham chiếu.

Điều cần giữ lại là **thao tác nguyên tử trên một key/document không tự biến workflow nhiều thực thể thành nguyên tử**. Khi có nhiều người ghi, retry, tồn kho, thanh toán, cache và replica, phải chọn transaction, CAS, idempotency, state machine hoặc quy trình đối soát theo yêu cầu thực tế. Một thiết kế CRUD tốt không chỉ chạy được câu lệnh, mà còn tránh **mất field khi thay thế, mất cập nhật khi cạnh tranh, trùng tác động khi retry và xóa sai phạm vi**.
