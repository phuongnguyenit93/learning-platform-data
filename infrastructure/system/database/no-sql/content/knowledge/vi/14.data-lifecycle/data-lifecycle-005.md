# Soft delete, trạng thái ngừng sử dụng và truy vấn loại trừ trong NoSQL

Một sản phẩm bị ngừng bán, một tài khoản bị tạm khóa và một bản ghi bị người dùng yêu cầu xóa có thể đều **không còn xuất hiện trong một số màn hình**, nhưng ý nghĩa và vòng đời của chúng khác nhau. Nếu thiết kế NoSQL chỉ có một lệnh xóa hoặc một cờ `active`, hệ thống dễ rơi vào tình trạng dữ liệu biến mất khỏi lịch sử, bị truy cập lại qua API khác, hoặc được khôi phục khi định danh đã bị dùng lại.

**Soft delete** (*xóa mềm*) là kỹ thuật giữ bản ghi vật lý nhưng đánh dấu nó **đã bị xóa về mặt logic**. **Trạng thái ngừng sử dụng** (*inactive, disabled, retired*) cho biết đối tượng còn tồn tại nhưng không được dùng trong một số nghiệp vụ. **Truy vấn loại trừ** là quy tắc để những bản ghi đó không lọt vào tập kết quả không phù hợp.

Bài học này đi từ mô hình trạng thái, truy vấn MongoDB, chỉ mục và ràng buộc duy nhất đến khôi phục, dọn dữ liệu, đồng bộ bản sao và kiểm thử. Trọng tâm là **vòng đời dữ liệu trong NoSQL**, không chỉ cú pháp `$set` hay `deleteOne`.

## 1. Phân biệt ẩn, ngừng sử dụng, xóa mềm và xóa vật lý

| Hành động | Ý nghĩa | Dữ liệu vật lý | Đường truy cập thích hợp |
| --- | --- | --- | --- |
| **Ẩn / unpublish** | Không công khai, nhưng còn trong quy trình soạn thảo | Giữ nguyên | Editor, quản trị |
| **Ngừng sử dụng / deactivate** | Không còn dùng cho thao tác mới, nhưng vẫn là thực thể hợp lệ | Giữ nguyên | Quản trị, lịch sử, có thể kích hoạt lại |
| **Tạm đình chỉ / suspend** | Chặn một nhóm hành vi do chính sách hoặc rủi ro | Giữ nguyên | Quản trị và quy trình xử lý riêng |
| **Lưu trữ / archive** | Chuyển khỏi tập dữ liệu thường xuyên sử dụng | Giữ hoặc chuyển tầng lưu trữ | Truy vấn lịch sử có quyền |
| **Soft delete** | Được coi là đã xóa khỏi không gian dữ liệu thông thường | Giữ có kiểm soát | Khôi phục, kiểm toán, dọn dữ liệu |
| **Hard delete / purge** | Xóa bản ghi khỏi hệ lưu trữ hiện hành | Không còn ở vị trí đó | Chỉ còn dấu vết hoặc bản sao theo chính sách riêng |

Ví dụ ứng dụng quản lý sản phẩm:

- **ACTIVE:** sản phẩm đang bán, được tìm thấy trong danh mục.
- **INACTIVE:** ngừng bán nhưng còn quản trị được, không được tạo đơn hàng mới.
- **SOFT_DELETED:** đã xóa mềm, bị loại khỏi các API hoạt động thông thường.
- **PURGED:** đã xóa vật lý sau thời hạn lưu giữ và các kiểm tra cần thiết.

Một sản phẩm **INACTIVE không phải là một sản phẩm đã xóa**. Nó có thể vẫn giữ mã SKU và được kích hoạt lại, trong khi sản phẩm đã xóa mềm có thể bắt đầu quá trình giải phóng định danh hoặc xóa thông tin nhạy cảm.

### Sơ đồ vòng đời minh họa

~~~mermaid
flowchart LR
    A[ACTIVE] -->|Tạm dừng| B[INACTIVE]
    B -->|Kích hoạt lại| A
    A -->|Xóa mềm| C[SOFT_DELETED]
    B -->|Xóa mềm| C
    C -->|Khôi phục hợp lệ| A
    C -->|Hết hạn giữ, đủ điều kiện| D[PURGED]
~~~

Sơ đồ là một **hợp đồng ví dụ**, không phải quy tắc cho mọi hệ thống. Một số nghiệp vụ yêu cầu khôi phục về trạng thái trước khi xóa; một số không cho khôi phục sau khi tài khoản bị thu hồi vì bảo mật; một số đòi duyệt trước khi purge.

## 2. Hard delete và soft delete trong document database

### Xóa vật lý

~~~javascript
db.products.deleteOne({
  _id: "product-101",
  tenantId: "tenant-a"
});
~~~

Nếu thao tác thành công, document không còn trong collection hiện tại. Các document khác tham chiếu `product-101` không tự động được cập nhật hoặc xóa chỉ vì một field tên `productId`. Khả năng tìm lại dữ liệu phụ thuộc backup, lịch sử sự kiện và quy tắc lưu giữ.

**Hard delete phù hợp** khi dữ liệu đã thực sự được phép xóa, không cần khôi phục từ bản ghi hiện hành và các thực thể liên quan đã được xử lý.

### Xóa mềm

~~~json
{
  "_id": "product-101",
  "tenantId": "tenant-a",
  "name": "Helmet A",
  "businessStatus": "ACTIVE",
  "isDeleted": true,
  "deletedAt": "2026-11-14T08:00:00Z",
  "deletedBy": "admin-07",
  "version": 6
}
~~~

Document vẫn còn nhưng **không được xuất hiện** ở những truy vấn chỉ dành cho bản ghi hiện hành. Lưu ý `deletedAt` được biểu diễn bằng chuỗi trong JSON minh họa; khi lưu MongoDB nên dùng kiểu **BSON Date**.

**Lợi ích:** có thể khôi phục thao tác nhầm, giữ dấu vết thay đổi, trì hoãn xóa vật lý cho đến khi đủ điều kiện và hỗ trợ các báo cáo lịch sử phù hợp.

**Chi phí:** mọi đường truy cập phải nhận biết trạng thái xóa; index và khóa duy nhất phải xử lý bản ghi đã xóa; cache/search/read model phải đồng bộ; dữ liệu vẫn chiếm dung lượng cho đến khi purge.

Soft delete không phải một cách thay thế mọi thao tác hard delete. Nếu có yêu cầu xóa dữ liệu vĩnh viễn, việc đặt `isDeleted:true` **không chứng minh yêu cầu đã hoàn thành**.

## 3. Mô hình trạng thái: một field hay nhiều chiều?

### 3.1. Cờ xóa tối giản

~~~json
{
  "_id": "p1",
  "isDeleted": false
}
~~~

Cách này chỉ thể hiện “đã bị xóa logic hay chưa”. Nó không cho biết p1 có đang được bán hoặc sử dụng hay không.

### 3.2. Một trường trạng thái tổng hợp

~~~json
{
  "_id": "p1",
  "lifecycleState": "INACTIVE"
}
~~~

Ví dụ các trạng thái có thể là `ACTIVE`, `INACTIVE`, `SOFT_DELETED`. Ưu điểm là trạng thái loại trừ nhau; nhược điểm là phải ghi lại **trạng thái trước khi xóa** nếu muốn khôi phục chính xác, và một trường dễ bị quá tải khi còn có các chiều độc lập như visibility, moderation hay fulfillment.

### 3.3. Tách trạng thái nghiệp vụ và trạng thái xóa

Trong bài này, chọn hai field:

~~~json
{
  "_id": "p1",
  "tenantId": "tenant-a",
  "businessStatus": "INACTIVE",
  "isDeleted": false,
  "version": 3
}
~~~

- `businessStatus`: `ACTIVE` hoặc `INACTIVE` đối với tình huống minh họa.
- `isDeleted`: `true` hoặc `false`, chỉ nói bản ghi có bị xóa mềm không.
- `version`: số phiên bản dùng để bảo vệ cập nhật đồng thời.
- Khi xóa, thêm `deletedAt`, `deletedBy`, `deleteReason` và tùy chính sách `purgeAfter`.

Hai chiều này cho phép trả lời câu hỏi:

| businessStatus | isDeleted | Ý nghĩa |
| --- | --- | --- |
| ACTIVE | false | Đang được sử dụng |
| INACTIVE | false | Còn hợp lệ nhưng ngừng sử dụng |
| ACTIVE | true | Đã xóa mềm; trạng thái trước khi xóa là ACTIVE |
| INACTIVE | true | Đã xóa mềm; trạng thái trước khi xóa là INACTIVE |

Cách dùng hai field có thể tạo tổ hợp không nhất quán nếu các service ghi tùy tiện. Cần **hợp đồng schema**, validator và một số thao tác chuyển trạng thái chuẩn hóa.

### 3.4. Quy tắc bất biến

Ví dụ bộ quy tắc:

1. `isDeleted` luôn là boolean, không được bỏ trống ở document mới.
2. `isDeleted:true` phải có `deletedAt` hợp lệ.
3. `isDeleted:false` không được giữ `purgeAfter` còn hiệu lực.
4. `businessStatus` chỉ thuộc tập giá trị được định nghĩa.
5. Các thao tác sửa thông thường phải chặn bản ghi `isDeleted:true`.
6. Mỗi thay đổi trạng thái tăng `version` để tránh ghi từ bản sao cũ.
7. Nếu có tenant, mọi truy vấn và thao tác phải giữ đúng phạm vi tenant.

Quy tắc tương tự có thể triển khai với trạng thái enum thay vì boolean, miễn ngữ nghĩa được áp dụng nhất quán.

## 4. Trạng thái ngừng sử dụng là một nghiệp vụ độc lập

Một số ví dụ:

| Loại dữ liệu | Ngừng sử dụng có thể nghĩa là | Còn cần lưu để làm gì? |
| --- | --- | --- |
| Sản phẩm | Không bán mới | Đơn hàng lịch sử, báo cáo, kích hoạt lại |
| Tài khoản | Không được đăng nhập | Kiểm toán, xử lý yêu cầu, chống cấp trùng định danh |
| Cấu hình | Phiên bản không còn dùng | Đối chiếu thay đổi, khôi phục triển khai |
| Thiết bị | Tạm ngắt hoạt động | Lịch sử đo đạc, thông tin bảo trì |
| Tài liệu | Không xuất bản công khai | Biên tập, duyệt lại nội dung |

Điều kiện `lastActiveAt` quá cũ **không tự động đồng nghĩa** `businessStatus:"INACTIVE"`. Nếu muốn tự chuyển sang trạng thái không hoạt động, phải có một **chính sách chuyển trạng thái** và audit event.

Khi sản phẩm chỉ tạm ngừng bán, việc giữ `isDeleted:false` còn giúp **khóa SKU vẫn được bảo vệ**, tránh cấp lại mã định danh đang sử dụng.

## 5. Truy vấn loại trừ phải phù hợp từng đường đọc

Giả sử có ba document:

~~~json
{ "_id": "p1", "businessStatus": "ACTIVE", "isDeleted": false }
~~~

~~~json
{ "_id": "p2", "businessStatus": "INACTIVE", "isDeleted": false }
~~~

~~~json
{ "_id": "p3", "businessStatus": "ACTIVE", "isDeleted": true }
~~~

Trang danh mục **đang bán** cần hai điều kiện:

~~~javascript
db.products.find({
  isDeleted: false,
  businessStatus: "ACTIVE"
});
~~~

Chỉ p1 hợp lệ. Nếu lọc `isDeleted:false` mà không kiểm tra status, p2 có thể xuất hiện dù đang tạm dừng. Nếu chỉ lọc status, p3 có thể lọt vào danh mục dù đã xóa mềm.

### 5.1. $ne:true không tương đương isDeleted:false

Xét dữ liệu cũ:

~~~json
{ "_id": "a", "isDeleted": false }
~~~

~~~json
{ "_id": "b", "isDeleted": true }
~~~

~~~json
{ "_id": "c" }
~~~

Trong MongoDB:

~~~javascript
// Chỉ field có boolean false.
db.products.find({ isDeleted: false });

// Bao gồm cả document thiếu field isDeleted.
db.products.find({ isDeleted: { $ne: true } });
~~~

- Điều kiện `false` khớp **a**.
- Điều kiện `$ne:true` khớp **a và c**.

Nếu `c` là bản ghi từ schema cũ, việc nó có được coi là “chưa xóa” hay không **phải được quyết định qua chính sách migration**, không nên do một toán tử phủ định vô tình quyết định. Tương tự, `{deletedAt:null}` trong MongoDB thường khớp cả field null **và field vắng mặt**, còn `{deletedAt:{$exists:false}}` chỉ khớp field thiếu.

Bài này dùng quy ước **strict `isDeleted:false`**. Dữ liệu cũ phải được backfill và kiểm soát writer để mọi bản ghi mới có field boolean hợp lệ.

### 5.2. Mỗi mục đích có một predicate

| Đường đọc | Predicate điển hình |
| --- | --- |
| Danh mục đang bán | `tenantId + isDeleted:false + businessStatus:"ACTIVE"` |
| Quản trị danh sách chưa xóa | `tenantId + isDeleted:false` |
| Sản phẩm đang tạm dừng | `tenantId + isDeleted:false + businessStatus:"INACTIVE"` |
| Thùng rác/khôi phục | `tenantId + isDeleted:true` cùng quyền phù hợp |
| Lấy một sản phẩm công khai theo ID | `_id + tenantId + isDeleted:false + businessStatus:"ACTIVE"` |
| Đơn hàng lịch sử | Theo dữ liệu giao dịch đã chốt, không tự loại đơn vì product gốc đã xóa |

Không nên tạo một tham số `includeDeleted=true` công khai cho mọi client. Các đường xem/xử lý bản ghi đã xóa nên **tách theo vai trò và quyền truy cập**.

### 5.3. Tenant và soft delete là hai ranh giới khác nhau

~~~javascript
db.products.findOne({
  _id: "p1",
  tenantId: "tenant-a",
  isDeleted: false
});
~~~

Lọc `tenantId` tránh đọc chéo tenant; lọc `isDeleted` tránh đọc dữ liệu đã xóa. **Không điều kiện nào thay thế được xác thực/phân quyền**. Tenant ID phải được xác định từ bối cảnh truy cập đáng tin cậy, không chỉ lấy từ query parameter do người gọi tùy ý đưa vào.

## 6. Index phục vụ truy vấn loại trừ

Truy vấn thường dùng:

~~~javascript
db.products.find({
  tenantId: "tenant-a",
  isDeleted: false,
  businessStatus: "ACTIVE"
})
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);
~~~

Một **ứng viên compound index**:

~~~javascript
db.products.createIndex({
  tenantId: 1,
  isDeleted: 1,
  businessStatus: 1,
  createdAt: -1,
  _id: -1
});
~~~

Các field lọc bằng nhau đặt trước hai field sort. Tuy nhiên, index thực sự được dùng hay không còn tùy thống kê, bộ tối ưu, độ chọn lọc và cấu hình database.

### 6.1. Partial index

MongoDB hỗ trợ **partial index** chỉ chứa những document khớp một predicate:

~~~javascript
db.products.createIndex(
  {
    tenantId: 1,
    businessStatus: 1,
    createdAt: -1,
    _id: -1
  },
  {
    partialFilterExpression: {
      isDeleted: false
    }
  }
);
~~~

Khi document chuyển từ `false` sang `true`, các index entry tương ứng thay đổi. Nhưng một **index không tự thêm điều kiện lọc cho truy vấn**. Query ứng dụng vẫn cần `isDeleted:false`. Nếu query không bảo đảm chỉ tìm document chưa xóa, bộ tối ưu không thể tùy tiện dùng partial index để trả kết quả đầy đủ.

Đường quản trị xem deleted có thể cần index riêng nếu có nhiều bản ghi đã xóa. Đừng chỉ tối ưu đường danh mục rồi để job khôi phục/quản trị quét hàng triệu document.

### 6.2. Unique index và tái sử dụng mã sau xóa

Giả sử `normalizedSku` phải duy nhất **trong mỗi tenant giữa những sản phẩm chưa xóa**, kể cả sản phẩm INACTIVE:

~~~javascript
db.products.createIndex(
  { tenantId: 1, normalizedSku: 1 },
  {
    unique: true,
    partialFilterExpression: { isDeleted: false }
  }
);
~~~

| Bản ghi | Quy tắc |
| --- | --- |
| tenant-a / sku-bike / false | Được dùng nếu chưa có bản ghi false trùng |
| tenant-a / sku-bike / false lần nữa | Bị từ chối |
| tenant-a / sku-bike / true | Có thể tồn tại cùng mã |
| tenant-b / sku-bike / false | Có thể tồn tại vì tenant khác |

**Hệ quả quan trọng:** sau khi xóa mềm một sản phẩm, mã của nó có thể được dùng cho sản phẩm mới. Khi khôi phục sản phẩm cũ, unique index có thể **từ chối** vì mã đã bị chiếm.

Nếu nghiệp vụ đòi **mã không bao giờ được tái sử dụng**, không nên dùng partial unique theo chính sách trên. Có thể dùng unique index toàn cục theo tenant, một registry định danh, tombstone giữ mã hoặc quy tắc alias, tùy yêu cầu.

## 7. Thực hành MongoDB: dữ liệu có active, inactive và deleted

Dùng `mongosh` cùng database thực hành riêng `nosql_soft_delete_lab`. Dữ liệu là giả định, không đại diện cho cửa hàng thực tế.

> Đoạn seed **xóa collection `products` trong database thực hành** để bắt đầu từ trạng thái biết trước. Không chạy trên collection chứa dữ liệu cần giữ.

~~~javascript
const lab = db.getSiblingDB("nosql_soft_delete_lab");

lab.products.drop();

lab.products.insertMany([
  {
    _id: "p1",
    tenantId: "tenant-a",
    normalizedSku: "sku-bike",
    name: "Xe dap A",
    businessStatus: "ACTIVE",
    isDeleted: false,
    createdAt: new Date("2026-11-01T08:00:00Z"),
    version: 1
  },
  {
    _id: "p2",
    tenantId: "tenant-a",
    normalizedSku: "sku-helmet",
    name: "Mu bao hiem B",
    businessStatus: "INACTIVE",
    isDeleted: false,
    createdAt: new Date("2026-11-02T08:00:00Z"),
    version: 1
  },
  {
    _id: "p3",
    tenantId: "tenant-a",
    normalizedSku: "sku-scooter",
    name: "Xe may C (da xoa)",
    businessStatus: "ACTIVE",
    isDeleted: true,
    deletedAt: new Date("2026-11-10T08:00:00Z"),
    deletedBy: "admin-1",
    createdAt: new Date("2026-10-15T08:00:00Z"),
    version: 2
  },
  {
    _id: "p4",
    tenantId: "tenant-b",
    normalizedSku: "sku-bike",
    name: "Xe dap D",
    businessStatus: "ACTIVE",
    isDeleted: false,
    createdAt: new Date("2026-11-03T08:00:00Z"),
    version: 1
  },
  {
    _id: "p5",
    tenantId: "tenant-a",
    normalizedSku: "sku-scooter",
    name: "Xe may E (tai su dung SKU)",
    businessStatus: "ACTIVE",
    isDeleted: false,
    createdAt: new Date("2026-11-11T08:00:00Z"),
    version: 1
  }
]);

lab.products.createIndex({
  tenantId: 1,
  isDeleted: 1,
  businessStatus: 1,
  createdAt: -1,
  _id: -1
});

lab.products.createIndex(
  { tenantId: 1, normalizedSku: 1 },
  {
    unique: true,
    partialFilterExpression: { isDeleted: false }
  }
);
~~~

Bộ dữ liệu có **5 document vật lý** nhưng không phải cả 5 đều hợp lệ cho danh mục công khai.

### 7.1. Truy vấn danh mục

~~~javascript
lab.products.find(
  {
    tenantId: "tenant-a",
    isDeleted: false,
    businessStatus: "ACTIVE"
  },
  {
    _id: 1,
    name: 1,
    normalizedSku: 1,
    createdAt: 1
  }
)
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .toArray();
~~~

Trước khi cập nhật dữ liệu ở các phần sau, kết quả mong đợi gồm **p5 rồi p1**. p2 bị loại vì INACTIVE; p3 vì đã xóa mềm; p4 vì thuộc tenant-b.

### 7.2. Truy vấn quản trị và thùng rác

~~~javascript
// Tất cả sản phẩm chưa bị xóa của tenant-a.
lab.products.find({
  tenantId: "tenant-a",
  isDeleted: false
}).toArray();

// Sản phẩm đang ngừng sử dụng.
lab.products.find({
  tenantId: "tenant-a",
  isDeleted: false,
  businessStatus: "INACTIVE"
}).toArray();

// Thùng rác: chỉ dùng trong đường quản trị có phân quyền.
lab.products.find({
  tenantId: "tenant-a",
  isDeleted: true
}).toArray();
~~~

| Truy vấn | ID mong đợi |
| --- | --- |
| Chưa xóa | p1, p2, p5 |
| Chưa xóa và INACTIVE | p2 |
| Đã xóa mềm | p3 |

### 7.3. Count và danh sách phải cùng điều kiện

~~~javascript
lab.products.countDocuments({
  tenantId: "tenant-a",
  isDeleted: false,
  businessStatus: "ACTIVE"
});
~~~

Nếu UI hiển thị 2 sản phẩm nhưng nhãn “Tổng” báo 3 do hàm count chỉ lọc `isDeleted:false`, đó là **lỗi hợp đồng truy vấn**. Danh sách, count, export và pagination cần thống nhất predicate tương ứng.

## 8. Ngừng sử dụng và kích hoạt lại

Tạm ngừng sản phẩm p1:

~~~javascript
const deactivateResult = lab.products.updateOne(
  {
    _id: "p1",
    tenantId: "tenant-a",
    isDeleted: false,
    businessStatus: "ACTIVE",
    version: 1
  },
  {
    $set: {
      businessStatus: "INACTIVE",
      inactivatedAt: new Date()
    },
    $inc: { version: 1 }
  }
);

printjson(deactivateResult);
~~~

Bản ghi vẫn **`isDeleted:false`**. Unique partial index vẫn giữ `sku-bike`, ngăn sản phẩm khác trong cùng tenant chiếm mã trong lúc sản phẩm tạm dừng.

Kích hoạt lại sau khi xác minh điều kiện nghiệp vụ:

~~~javascript
lab.products.updateOne(
  {
    _id: "p1",
    tenantId: "tenant-a",
    isDeleted: false,
    businessStatus: "INACTIVE",
    version: 2
  },
  {
    $set: { businessStatus: "ACTIVE" },
    $unset: { inactivatedAt: "" },
    $inc: { version: 1 }
  }
);
~~~

Nếu chạy theo thứ tự ví dụ, p1 quay về ACTIVE ở **version 3**. `matchedCount = 0` cho biết điều kiện không khớp; có thể do version đã thay đổi, ID sai, tenant sai hoặc bản ghi đã bị xóa. Ứng dụng phải xử lý tình huống này, không âm thầm báo thành công.

## 9. Xóa mềm có điều kiện và metadata

Một thao tác soft delete nên giới hạn theo tenant, trạng thái hiện hành và version:

~~~javascript
const now = new Date();
const retentionDays = 30;
const purgeAfter = new Date(
  now.getTime() + retentionDays * 24 * 60 * 60 * 1000
);

const deleteResult = lab.products.updateOne(
  {
    _id: "p1",
    tenantId: "tenant-a",
    isDeleted: false,
    version: 3
  },
  {
    $set: {
      isDeleted: true,
      deletedAt: now,
      deletedBy: "admin-07",
      deleteReason: "Duplicate listing",
      purgeAfter
    },
    $inc: { version: 1 }
  }
);

printjson(deleteResult);
~~~

Nếu p1 có version 3 và chưa xóa, thao tác sẽ chuyển nó thành deleted, version 4. Từ đó p1 bị loại khỏi query `isDeleted:false`.

Metadata có vai trò riêng:

| Field | Tác dụng |
| --- | --- |
| `deletedAt` | Thời điểm xóa logic theo quy ước |
| `deletedBy` | Chủ thể thực hiện |
| `deleteReason` | Lý do phục vụ quản trị |
| `purgeAfter` | Thời điểm dự kiến có thể xóa vật lý |
| `version` | Chống cập nhật từ bản sao cũ |
| `deleteOperationId` (nếu cần) | Phân biệt các thao tác xóa và hỗ trợ idempotency |

`purgeAfter` không cam kết rằng dữ liệu được xóa vật lý chính xác vào thời điểm đó. Và metadata trong document **không tự thay thế** audit log có khả năng chống sửa đổi nếu nghiệp vụ đòi kiểm toán nghiêm ngặt.

### 9.1. Ghi sau khi bản ghi đã bị xóa

Một worker giá bán chạy chậm không nên sửa bản ghi đã xóa:

~~~javascript
lab.products.updateOne(
  {
    _id: "p1",
    tenantId: "tenant-a",
    isDeleted: false
  },
  {
    $set: { price: 150000 }
  }
);
~~~

Sau khi p1 đã deleted, thao tác này không khớp. Không nên bật `upsert:true` tùy tiện trên đường cập nhật này: một writer cũ có thể vô tình **tạo lại bản ghi** theo ID sau khi đã xóa.

### 9.2. Idempotency khi request bị gửi lại

Lệnh xóa mềm có `isDeleted:false` giúp tránh cập nhật lần thứ hai, nhưng response của retry có thể là `matchedCount = 0`. Để đáp ứng hợp đồng API “xóa một lần nhưng retry an toàn”, hệ thống có thể lưu `deleteOperationId`, tra trạng thái hiện tại và xác nhận request lặp theo cùng mã thao tác, không tự suy rằng mọi trường hợp 0 đều thành công.

## 10. Khôi phục: phải kiểm tra version, định danh và thời hạn

Một lệnh `$set:{isDeleted:false}` đơn độc không đủ vì có thể:

- Khôi phục bản ghi của tenant khác.
- Khôi phục sau thời hạn được phép.
- Ghi đè thay đổi mới hơn.
- Bỏ sót việc xóa `purgeAfter` khiến TTL xóa vật lý sau restore.
- Gặp trùng SKU hoặc khóa nghiệp vụ khác.
- Khôi phục khi các quan hệ và dữ liệu phụ thuộc đã bị dọn.

Một thao tác có điều kiện:

~~~javascript
const restoreResult = lab.products.updateOne(
  {
    _id: "p1",
    tenantId: "tenant-a",
    isDeleted: true,
    version: 4
  },
  {
    $set: { isDeleted: false },
    $unset: {
      deletedAt: "",
      deletedBy: "",
      deleteReason: "",
      purgeAfter: ""
    },
    $inc: { version: 1 }
  }
);

printjson(restoreResult);
~~~

Lệnh minh họa giả định chính sách cho phép restore và p1 vừa bị xóa ở phần 9. Trong triển khai thực, kiểm tra thời hạn và quyền nên là **điều kiện đáng tin cậy tại thời điểm thực thi**, không chỉ là bước giao diện.

### 10.1. Unique partial index có thể chặn khôi phục

Trong bộ seed:

~~~text
p3: tenant-a / sku-scooter / isDeleted=true
p5: tenant-a / sku-scooter / isDeleted=false
~~~

Khi cố restore p3, nó trở lại tập `isDeleted:false`, nên sẽ bị **unique partial index** từ chối do p5 đang sử dụng SKU đó. Đây là cơ chế bảo vệ tính duy nhất, không phải lỗi nên bỏ qua.

Chính sách hợp lệ có thể:

1. Từ chối restore và yêu cầu xử lý.
2. Đổi SKU của bản ghi cũ trước khi phục hồi.
3. Hợp nhất thực thể nếu nghiệp vụ cho phép.
4. Thiết kế từ đầu không tái sử dụng SKU đã xóa nếu khả năng restore mã cũ quan trọng.

Không được tắt unique index để buộc khôi phục một bản ghi gây xung đột rồi để hệ thống có hai đối tượng cùng định danh.

### 10.2. Khôi phục về ACTIVE hay INACTIVE?

Nếu trước lúc xóa bản ghi là INACTIVE, khôi phục thẳng về ACTIVE có thể làm nó đột ngột được bán lại. Có hai cách:

- **Giữ businessStatus** khi xóa và khôi phục để quay về trạng thái trước đó.
- Lưu `previousBusinessStatus` và áp dụng quy tắc rõ ràng khi restore.

Cách nào cũng cần xem ràng buộc hiện tại: sản phẩm có còn đủ điều kiện mở bán không, tenant còn hoạt động không và những tài liệu tham chiếu có còn tồn tại không.

## 11. Soft delete phải được áp dụng trên nhiều đường truy vấn

Một API danh mục được lọc đúng vẫn có thể rò rỉ bản ghi qua các đường khác:

- `GET /products/{id}` lấy theo `_id` mà quên `isDeleted`.
- Search/autocomplete dùng index chưa cập nhật.
- Featured list hoặc recommendation lấy bản sao cũ.
- Aggregation với `$lookup` ghép bản ghi deleted.
- Cache trả object đã được lưu trước khi xóa.
- Report hoặc export dùng điều kiện khác với API.
- Graph traversal vẫn đi qua nút bị xóa.
- Tổng số và phân trang được tính trước khi filter.

### 11.1. Lọc trước khi tổng hợp

~~~javascript
lab.products.aggregate([
  {
    $match: {
      tenantId: "tenant-a",
      isDeleted: false,
      businessStatus: "ACTIVE"
    }
  },
  {
    $group: {
      _id: "$businessStatus",
      count: { $sum: 1 }
    }
  }
]).toArray();
~~~

Nếu pipeline có `$lookup` từ collection khác, bộ lọc trên collection đầu **không tự áp dụng cho collection được ghép**. Ví dụ bài đăng còn công khai nhưng tác giả đã bị đình chỉ: phải có quy tắc có được hiển thị bài đó hay không và áp dụng nó ở bước tương ứng.

### 11.2. Giữ đúng lịch sử nghiệp vụ

Đơn hàng đã thanh toán có thể chứa snapshot SKU, tên và giá sản phẩm tại thời điểm mua. Nếu sản phẩm gốc hiện bị xóa mềm, **không nên loại đơn hàng lịch sử hợp lệ** khỏi báo cáo doanh thu. Ngược lại, giao diện đặt hàng mới không được lấy sản phẩm deleted chỉ vì nó còn được tham chiếu trong một đơn cũ.

**Đường đọc “hiện tại” và “lịch sử” cần hợp đồng khác nhau.**

### 11.3. Lớp repository mặc định

Có thể tạo các thao tác truy cập dữ liệu tách rõ:

~~~text
findVisibleProduct(tenantId, productId)
  -> isDeleted=false, businessStatus=ACTIVE

findManagedProduct(tenantId, productId)
  -> isDeleted=false, kiểm tra quyền quản trị

findDeletedProductForRestore(tenantId, productId)
  -> isDeleted=true, kiểm tra quyền phục hồi
~~~

Cách tổ chức này giảm nguy cơ quên predicate. Nhưng aggregation, job batch và truy vấn raw có thể bỏ qua repository; cần kiểm thử toàn bộ bề mặt đọc.

## 12. Pagination và index khi dữ liệu deleted tích lũy

Ví dụ sau giúp giữ thứ tự ổn định:

~~~javascript
lab.products.find({
  tenantId: "tenant-a",
  isDeleted: false,
  businessStatus: "ACTIVE"
})
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .toArray();
~~~

Trường `_id` dùng làm khóa phụ khi nhiều sản phẩm có cùng `createdAt`. Nếu phải phân trang sâu, có thể dùng **keyset pagination** theo cặp (`createdAt`, `_id`) thay vì `skip` với offset lớn.

~~~javascript
// Cursor minh họa; ứng dụng phải lấy từ phần tử cuối trang trước.
const lastCreatedAt = new Date("2026-11-02T08:00:00Z");
const lastId = "p2";

lab.products.find({
  tenantId: "tenant-a",
  isDeleted: false,
  businessStatus: "ACTIVE",
  $or: [
    { createdAt: { $lt: lastCreatedAt } },
    {
      createdAt: lastCreatedAt,
      _id: { $lt: lastId }
    }
  ]
})
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .toArray();
~~~

Nếu lấy 20 record trước rồi **lọc isDeleted ở application**, trang có thể chỉ còn 7 kết quả, và cursor dễ sai. Nên lọc tại tầng truy vấn trước khi giới hạn số kết quả.

Khi collection có tỷ lệ deleted lớn, cần xem execution plan, số record/index được xét, chi phí giữ dữ liệu và phương án purge. Một partial index có thể giảm chi phí đọc hiện hành nhưng không thay thế chính sách lưu trữ.

## 13. Retention, TTL và purge

**Xóa logic** và **xóa vật lý** có thể cách nhau nhiều ngày hoặc nhiều tháng. Một chu trình ví dụ:

~~~text
Đối tượng đang dùng
   |
   v
Yêu cầu xóa hợp lệ
   |
   +--> Chuyển isDeleted=true
   +--> Ghi audit event
   +--> Ẩn khỏi query hiện hành
   +--> Đồng bộ search/cache/read model
   |
   v
Giai đoạn lưu giữ / khôi phục
   |
   +--> Có thể restore nếu chính sách cho phép
   +--> Có thể có legal hold hoặc tranh chấp
   |
   v
Đủ điều kiện purge
   |
   +--> Kiểm tra phụ thuộc và các bản sao
   +--> Xóa hoặc ẩn danh theo chính sách
   +--> Ghi kết quả, retry và đối chiếu
   |
   v
PURGED
~~~

### 13.1. TTL không phải soft delete

TTL (*time to live*) là cơ chế hết hạn theo thời gian. Trong MongoDB, có thể tạo TTL index trên field Date dành riêng cho việc dọn dữ liệu:

~~~javascript
lab.products.createIndex(
  { purgeAfter: 1 },
  { expireAfterSeconds: 0 }
);
~~~

Điểm phải hiểu đúng:

- TTL dọn dữ liệu theo **quá trình nền**, không bảo đảm xóa đúng từng giây ở mốc `purgeAfter`.
- Nếu một document ACTIVE vô tình có `purgeAfter` đến hạn, TTL index đơn giản này cũng có thể **xóa vật lý** document đó.
- Khi restore, cần **xóa field `purgeAfter`**.
- TTL không mặc nhiên xử lý dữ liệu tham chiếu, file đính kèm, cache, search index hoặc bản sao lưu.
- Nếu có legal hold hay quy trình phê duyệt trước khi xóa, một worker purge có điều kiện có thể an toàn và dễ kiểm soát hơn TTL tự động.

Vì thế, chỉ áp dụng TTL nếu có thể bảo đảm **field hết hạn chỉ tồn tại trên dữ liệu được phép xóa** và đã thiết kế chính sách restore/hold phù hợp. Không nên coi đây là cấu hình mặc định cho mọi soft delete.

### 13.2. Purge worker kiểm tra lại điều kiện

Giả mã:

~~~text
for each document where:
    isDeleted == true
    and purgeAfter <= now
    and legalHold == false

    lock or validate purge ownership
    re-check lifecycle version and eligibility
    handle dependent copies under defined policy
    hard-delete with a condition that still requires isDeleted=true
    persist result / checkpoint
    retry transient failures idempotently
~~~

**Tại sao phải kiểm tra lại?** Một admin có thể restore document sau khi worker đưa nó vào danh sách chờ. Nếu worker chỉ `deleteOne({_id})`, nó có thể xóa vĩnh viễn bản ghi vừa khôi phục.

### 13.3. Backup, retention và lời hứa “xóa”

Xóa document khỏi collection hiện tại **không đồng nghĩa** dữ liệu đã biến mất lập tức khỏi:

- Snapshot/backup.
- Event log, CDC/outbox.
- Search index.
- Cache và read model.
- File lưu ngoài database.
- Hệ phân tích, export hoặc báo cáo.

Một chính sách lưu giữ dữ liệu phải xác định từng loại bản sao, thời hạn và hành vi khi khôi phục hệ từ backup. Nếu doanh nghiệp có yêu cầu xóa dữ liệu cá nhân, phải đối chiếu chính sách và nghĩa vụ áp dụng; **soft delete không phải bằng chứng hoàn tất xóa vĩnh viễn**.

## 14. Tombstone và nguy cơ “dữ liệu sống lại”

Trong hệ phân tán, một sự kiện cũ có thể tới **sau** sự kiện xóa:

~~~text
T=10: p1 version 5 = ACTIVE
T=11: p1 version 6 = SOFT_DELETED
T=12: Worker nhận trễ event version 5 và upsert ACTIVE
~~~

Nếu consumer ghi đè vô điều kiện, p1 có thể **tái xuất hiện** dù đã bị xóa. Một **tombstone** là thông tin tối thiểu ghi nhận đối tượng đã bị xóa tại một version/generation, để các thành phần khác không áp dụng sự kiện cũ.

Ví dụ event:

~~~json
{
  "eventId": "evt-p1-delete-v6",
  "tenantId": "tenant-a",
  "entityType": "PRODUCT",
  "entityId": "p1",
  "sourceVersion": 6,
  "type": "PRODUCT_SOFT_DELETED",
  "occurredAt": "2026-11-14T08:00:00Z"
}
~~~

Quy tắc ví dụ:

~~~text
if event.sourceVersion <= lastAppliedVersion(entity):
    ignore stale/duplicate event
else:
    apply event according to its type
    persist lastAppliedVersion
~~~

Version cần tăng đơn điệu **trong phạm vi thực thể**; nếu ID được dùng lại cho một thực thể khác, nên có thêm generation/incarnation hoặc không tái sử dụng ID. Timestamp từ nhiều hệ không nhất thiết là thứ tự tuyệt đối đáng tin cậy.

“Tombstone” trong tầng ứng dụng không hoàn toàn đồng nghĩa tombstone nội bộ của Cassandra hoặc các storage engine LSM. Cùng tên nhưng ngữ nghĩa, vòng đời và quy trình dọn có thể khác nhau.

## 15. Cache, tìm kiếm và dữ liệu dẫn xuất

Một sản phẩm có thể đồng thời xuất hiện tại:

~~~text
Canonical NoSQL products
  |
  +-- Cache theo productId
  +-- Search index / autocomplete
  +-- Featured-products view
  +-- Recommendation feed
  +-- Export và analytics pipeline
~~~

Sau soft delete:

- Cache có thể vẫn trả object cũ.
- Search index còn chứa product.
- Featured view còn trỏ tới ID đã xóa.
- Worker báo cáo đọc snapshot cũ.

Một thiết kế đồng bộ có thể dùng **outbox hoặc CDC**, với event xóa logic gửi tới các consumer để invalidate/suppress:

~~~mermaid
flowchart TD
    A[Soft delete canonical] --> B[Outbox hoặc CDC]
    B --> C[Event publisher]
    C --> D[Cache invalidation]
    C --> E[Search suppression]
    C --> F[Read model update]
    D --> G[Theo dõi lag và retry]
    E --> G
    F --> G
~~~

Nếu yêu cầu **không được hiển thị dữ liệu đã thu hồi ngay**, chỉ chờ worker bất đồng bộ có thể chưa đủ. Đường đọc cần một cơ chế **chặn hiển thị từ trạng thái đáng tin cậy** hoặc bảo đảm tương đương.

Consumer cũng phải xử lý **restore** và **purge**, không chỉ create/delete. Dùng event idempotent và version để tránh event cũ ghi đè trạng thái mới.

## 16. Soft delete và dữ liệu tham chiếu

NoSQL thường không tự tạo foreign key chỉ vì hai document chứa cùng ID. Khi một thực thể bị xóa mềm, cần định nghĩa rõ chuyện gì xảy ra với tài liệu liên quan.

### 16.1. Đơn hàng tham chiếu sản phẩm đã xóa

Một đơn hàng lịch sử nên giữ snapshot giá, tên hoặc SKU tại thời điểm mua, tùy nghiệp vụ. Nếu product gốc bị xóa mềm thì:

- Danh mục bán hiện tại không trả product.
- Đơn hàng đã thanh toán vẫn có thể hiện dòng sản phẩm lịch sử hợp lệ.
- Báo cáo doanh thu không được tự xóa giao dịch chỉ vì nguồn product đã đổi trạng thái.

### 16.2. Tài khoản và bài đăng

Xóa mềm một tài khoản có thể yêu cầu:

- Ẩn mọi bài viết của tài khoản khỏi feed công khai.
- Giữ một phần nội dung đã xuất bản theo chính sách.
- Ẩn hoặc xóa tên/avatar và dữ liệu nhạy cảm.
- Dọn dữ liệu liên kết theo lô.

Nếu có hàng triệu bài đăng, không thể giả định toàn bộ thay đổi là **một update nguyên tử**. Có thể dùng trạng thái cha để chặn truy cập tức thì, rồi dọn các bản sao con bất đồng bộ; song phải kiểm tra hiệu năng và tính nhất quán.

### 16.3. Soft cascade và khôi phục có chọn lọc

Giả sử thư mục cha F có các file A, B, C. File B đã bị người dùng xóa trước đó. Sau này F bị xóa mềm theo cascade. Khi restore F, **không nên tự khôi phục B** nếu nó vốn đã bị xóa độc lập.

Một thiết kế có thể ghi `deleteOperationId` hoặc `deletionGeneration` để phân biệt những file bị xóa theo cùng thao tác. Restore chỉ phục hồi những đối tượng đủ điều kiện của operation đó.

Đây là lý do “xóa mềm cha rồi đặt cờ cho mọi con” thường cần một **hợp đồng khôi phục** tường minh.

## 17. Race condition: xóa, sửa, restore và purge đồng thời

### 17.1. Sửa đồng thời với xóa mềm

~~~text
Editor đọc p1 version 5, chuẩn bị sửa giá.
Admin xóa mềm p1: version 5 → 6.
Editor gửi lệnh update theo version 5.
~~~

Nếu writer dùng `{_id, tenantId, isDeleted:false, version:5}`, thao tác đến trễ không khớp, tránh sửa dữ liệu đã xóa. Nếu chỉ dùng `_id`, nó vẫn có thể ghi và gây khó cho audit/restore.

### 17.2. Restore đồng thời với purge

~~~text
Worker chọn p1 vì purgeAfter đã tới hạn.
Admin restore p1 và xóa purgeAfter, version tăng.
Worker xóa theo _id mà không kiểm tra lại.
~~~

Đây là race nguy hiểm. Bước xóa vật lý cần guard theo **trạng thái hiện hành, thời hạn và version/ownership**, hoặc cơ chế điều phối phù hợp khi có nhiều hệ liên quan.

### 17.3. Hai request xóa cùng lúc

Request đầu chuyển `isDeleted:false` → `true`. Request hai không khớp điều kiện. API có thể trả “đã đạt trạng thái đích” nếu xác định đó là retry hợp lệ, hoặc trả conflict. Nhưng không được làm mất nguyên nhân xóa ban đầu, tạo audit event trùng hoặc tự đẩy `purgeAfter` mới về sau mỗi lần retry.

### 17.4. Restore với khóa đã tái sử dụng

Nếu partial unique index đã cho phép cấp lại một SKU, restore document cũ có thể bị từ chối. Đó là trường hợp phải xử lý bằng quyết định nghiệp vụ, không nên tạm xóa ràng buộc unique.

## 18. API và quyền truy cập

Một API công khai có thể trả **404 Not Found** cho document đã soft deleted, bởi từ góc nhìn client không có quyền, đối tượng không khả dụng. Một số API dùng **410 Gone** nếu muốn công bố tài nguyên từng tồn tại rồi bị thu hồi, nhưng khả năng tiết lộ sự tồn tại của tài nguyên cũng là quyết định bảo mật.

Các hành động nên tách rõ:

~~~text
POST   /admin/products/{id}/deactivate
POST   /admin/products/{id}/activate
DELETE /admin/products/{id}
POST   /admin/products/{id}/restore
POST   /admin/products/{id}/purge
~~~

Đây là phác thảo API, không phải chuẩn bắt buộc. Mỗi hành động phải có **quyền**, **điều kiện chuyển trạng thái**, **version**, **idempotency** và **audit** thích hợp.

Không nên cho mọi endpoint công khai nhận `includeDeleted=true`. API quản trị để xem dữ liệu đã xóa cần kiểm tra vai trò và phạm vi tenant riêng.

Với bulk delete, cần ghi nhận số ID thành công, ID không tồn tại, không có quyền, đã xóa từ trước và lỗi một phần. Trả “đã xóa mọi thứ” khi chỉ cập nhật một phần batch là không đúng.

## 19. Kiểm chứng bằng dữ liệu đại diện

Một bộ test chỉ có record ACTIVE không thể phát hiện lỗi soft delete. Nên có các trường hợp:

| Dữ liệu | Danh mục công khai | Quản trị chưa xóa | Thùng rác |
| --- | --- | --- | --- |
| ACTIVE + false | Có | Có | Không |
| INACTIVE + false | Không | Có | Không |
| ACTIVE + true | Không | Không | Có |
| INACTIVE + true | Không | Không | Có |
| isDeleted thiếu/sai kiểu | Không theo hợp đồng strict | Cần migration | Không tự suy đoán |
| Tenant khác | Không | Không | Không nếu không có quyền |

Đồng thời thử:

- ID không tồn tại.
- Khóa nghiệp vụ bị dùng lại sau soft delete.
- Restore sau hết thời hạn.
- Document đã khôi phục nhưng cache/search chưa cập nhật.
- Writer cũ gửi sự kiện sau soft delete.
- Worker purge và admin restore đồng thời.
- Tỷ lệ record deleted rất cao so với dữ liệu hoạt động.
- Danh sách và tổng số dùng cùng predicate.

### 19.1. Kiểm tra execution plan

~~~javascript
printjson(
  lab.products.find({
    tenantId: "tenant-a",
    isDeleted: false,
    businessStatus: "ACTIVE"
  })
    .sort({ createdAt: -1, _id: -1 })
    .limit(20)
    .explain("executionStats")
);
~~~

Các chỉ số `winningPlan`, `nReturned`, `totalKeysExamined`, `totalDocsExamined` và `executionTimeMillis` giúp hiểu đường truy cập (tùy phiên bản MongoDB). Mẫu vài document ở bài thực hành chỉ có giá trị học cú pháp; đánh giá hiệu năng thực phải dùng **phân bố dữ liệu và tải đại diện**.

### 19.2. Quan sát chi phí vòng đời

Cần đo:

- Tỷ lệ document đã xóa mềm.
- Dung lượng dữ liệu, index và bản sao.
- p95/p99 latency của danh mục, quản trị, thùng rác.
- Độ trễ search/cache ngừng trả bản ghi đã xóa.
- Số restore thành công/thất bại do duplicate key.
- Số record đến hạn purge nhưng chưa được dọn.
- Tỷ lệ lỗi/timeout và retry của purge worker.
- Số event cũ bị loại nhờ version/tombstone.

Soft delete mang lại lợi ích khi giúp thực hiện **chính sách vòng đời**, không phải khi chỉ làm cho thao tác xóa có vẻ nhanh trên giao diện.

## 20. Những lỗi thiết kế hay gặp

### 20.1. Chỉ lọc ở màn danh sách

Danh mục dùng `isDeleted:false` nhưng API lấy theo ID không lọc, người biết ID vẫn lấy được sản phẩm đã xóa. Phải áp dụng điều kiện ở mọi đường đọc phù hợp.

### 20.2. Nhầm INACTIVE với DELETED

Tạm ngừng bán khiến sản phẩm bị xóa logic, gây khó quản trị và xung đột khi muốn tái sử dụng định danh. Nên giữ hai khái niệm khác nhau.

### 20.3. Dùng phủ định với dữ liệu thiếu field

`$ne:true` bao gồm bản ghi thiếu cờ; nếu schema cũ chưa được xử lý thì có thể làm lộ dữ liệu không phù hợp. Chọn quy ước và migration rõ ràng.

### 20.4. Quên unique index khi restore

Sau xóa, SKU được cấp cho bản ghi khác. Restore thất bại hoặc gây xung đột. Quy tắc tái sử dụng khóa phải được quyết định trước.

### 20.5. Tạo TTL trên tài liệu đang hoạt động

`purgeAfter` vô tình xuất hiện ở document ACTIVE và TTL có thể xóa vật lý. Cần kiểm soát quá trình tạo field, validator, quy trình hold và cân nhắc worker có guard.

### 20.6. Không xóa dữ liệu phụ trợ

MongoDB đã đánh dấu xóa nhưng cache và search vẫn trả sản phẩm. Cần event, invalidation, suppress khi đọc và theo dõi lag.

### 20.7. Coi soft delete là đã dọn dữ liệu

Dữ liệu vẫn tồn tại và tăng theo thời gian, có thể nằm trong backup/export. Cần retention và purge với chính sách hợp lệ.

### 20.8. Purge không kiểm tra lại trạng thái

Worker xóa theo `_id` sau khi admin đã restore. Cần condition/version ở điểm thực hiện xóa vật lý.

### 20.9. Cascade và restore không phân biệt nguyên nhân

Khôi phục cha làm sống lại con đã xóa độc lập từ trước. Cần operation ID/generation hoặc logic lựa chọn cụ thể.

### 20.10. Upsert từ event cũ

Một consumer nhận event tạo/cập nhật trễ và ghi lại thực thể đã xóa. Cần tombstone, version và bảo vệ định danh.

### 20.11. Lọc sau khi giới hạn kết quả

Lấy 20 product rồi loại deleted ở Java khiến trang chỉ có vài item, count và cursor sai. Nên lọc tại database trước sort/limit.

### 20.12. Không phân biệt delete logic với quyền xóa vĩnh viễn

Xóa logic không xóa dữ liệu trong backup, index và hệ phụ trợ. Cần ghi nhận từng giai đoạn xử lý và không khẳng định đã xóa hoàn toàn khi chưa hoàn tất.

## 21. Bài tập thực hành

### Bài 1: chọn trạng thái

Sản phẩm ngừng bán một tháng, dự kiến mở lại; đơn hàng lịch sử vẫn phải tra cứu được. Nên đặt `businessStatus:"INACTIVE"` hay `isDeleted:true`?

**Gợi ý:** Chọn INACTIVE, giữ `isDeleted:false`, vì không có ý định xóa logic.

### Bài 2: truy vấn với $ne

Cho ba document `a` false, `b` true và `c` thiếu cờ. Truy vấn `{isDeleted:{$ne:true}}` trả những ID nào?

**Gợi ý:** a và c. Nếu chỉ muốn false thực sự, dùng `{isDeleted:false}` theo hợp đồng strict.

### Bài 3: lọc ACTIVE chưa xóa

Dùng bộ seed phần 7 viết truy vấn lấy sản phẩm ACTIVE chưa xóa của tenant-a, sắp mới nhất trước.

~~~javascript
lab.products.find({
  tenantId: "tenant-a",
  isDeleted: false,
  businessStatus: "ACTIVE"
})
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);
~~~

Khi chưa chạy các cập nhật sau seed, kết quả mong đợi là p5 rồi p1.

### Bài 4: sản phẩm INACTIVE và khóa duy nhất

p2 ở tenant-a có `sku-helmet`, `isDeleted:false` nhưng INACTIVE. Có thể tạo sản phẩm chưa xóa khác trong cùng tenant với SKU đó không?

**Gợi ý:** Không, vì unique partial index vẫn tính p2 trong tập `isDeleted:false`.

### Bài 5: khôi phục xung đột

Vì sao restore p3 có thể bị lỗi khi p5 có cùng `normalizedSku`?

**Gợi ý:** Khi p3 chuyển sang false, nó tham gia unique partial index và trùng với p5. Cần quy tắc đổi mã hoặc xử lý xung đột.

### Bài 6: TTL

Nếu một document ACTIVE vô tình có `purgeAfter` đã quá hạn, TTL index ở phần 13 có tự kiểm tra `isDeleted:false` trước khi xóa không?

**Gợi ý:** Không theo index đơn giản đó; document có thể bị xóa vật lý. Đây là lý do cần kiểm soát việc đặt field hoặc dùng purge worker có điều kiện.

### Bài 7: API lấy theo ID

Sản phẩm đã bị xóa mềm không nằm trong danh mục nhưng vẫn đọc được qua `GET /products/p3`. Cần xem lại điều gì?

**Gợi ý:** Predicate và quyền trên đường get-by-ID, không chỉ ở danh sách.

### Bài 8: đọc đơn hàng lịch sử

Sản phẩm đã xóa mềm nhưng đơn đã thanh toán năm trước có dòng sản phẩm đó. Có nên bỏ đơn khỏi báo cáo doanh thu?

**Gợi ý:** Không nếu giao dịch vẫn hợp lệ; báo cáo dựa trên đơn hàng/snapshot và quy tắc hạch toán, không dựa riêng vào trạng thái hiện tại của product.

### Bài 9: race restore–purge

Worker đã chọn document để purge; admin restore trước khi worker xóa vật lý. Nếu worker chỉ `deleteOne({_id})`, rủi ro gì xảy ra?

**Gợi ý:** Nó có thể xóa document vừa được khôi phục. Cần điều kiện kiểm tra trạng thái, hạn xóa và version ở thời điểm delete.

### Bài 10: kiểm chứng toàn hệ

Thiết kế test để bảo đảm một soft-deleted product không lọt vào danh mục, tìm kiếm, cache, recommendation hay export công khai. Những chỉ số nào cần đo?

**Gợi ý:** Tính đúng tập kết quả, độ trễ invalidate/suppress, tỉ lệ stale read, lỗi đồng bộ và sự kiện đến sai thứ tự.

## 22. Quy trình áp dụng cho một model NoSQL mới

1. **Phân loại trạng thái:** inactive, hidden, suspended, archived, deleted và purged có nghĩa cụ thể gì?
2. **Đặt hợp đồng schema:** kiểu field, metadata, version, quy tắc missing/null và các chuyển trạng thái hợp lệ.
3. **Thiết kế từng query:** danh mục, get-by-ID, admin, search, aggregate, report và lịch sử loại trừ thế nào?
4. **Thiết kế index và unique key:** phạm vi tenant, đối tượng active/inactive, khả năng tái sử dụng ID sau xóa.
5. **Bảo vệ đường ghi:** soft delete, restore, version, idempotency, không upsert bất ngờ.
6. **Xử lý dữ liệu liên quan:** document con, tham chiếu, read model, cache, search index.
7. **Định nghĩa retention và purge:** điều kiện xóa vật lý, legal hold, backup và trách nhiệm đồng bộ.
8. **Kiểm chứng sự cố:** race giữa restore–purge, event trễ, ghi đồng thời và bản sao bị lỗi.
9. **Đo trên dữ liệu đại diện:** tỷ lệ deleted/inactive, đường index, chi phí duy trì và độ trễ sync.
10. **Công bố trạng thái rõ ràng:** đã ẩn, đã xóa logic, đang chờ dọn và đã purge là những mốc khác nhau.

**Kết luận:** Soft delete chỉ thực sự đúng khi toàn bộ hệ thống thống nhất **đối tượng nào đã bị xóa, ai còn được phép thấy nó, có thể khôi phục trong điều kiện nào và khi nào mới xóa vật lý**. Trạng thái ngừng sử dụng cần được phân biệt khỏi xóa logic; còn truy vấn loại trừ phải trở thành một phần của hợp đồng dữ liệu, không phải một bộ lọc tùy hứng ở màn hình.
