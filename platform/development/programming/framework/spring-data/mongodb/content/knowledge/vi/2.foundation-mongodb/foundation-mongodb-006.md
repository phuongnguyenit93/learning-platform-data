# Lệnh `find`, `insert`, `update`, `replace` và `delete` cơ bản

> **Chương:** Nền tảng MongoDB  
> **Phạm vi:** MongoDB CRUD và cách liên hệ với **Spring Data MongoDB** (`MongoTemplate`, repository).  
> **Mục tiêu:** Biết chọn đúng thao tác đọc, thêm, sửa từng trường, thay toàn bộ document và xóa; sử dụng bộ lọc chính xác, đọc kết quả trả về và tránh sửa/xóa nhầm dữ liệu.

## 1. CRUD trong MongoDB làm việc với gì?

MongoDB lưu dữ liệu dưới dạng **document BSON** trong **collection**. Một document gần giống đối tượng JSON, có thể chứa trường lồng nhau và mảng. Mỗi document có trường `_id` duy nhất trong collection; MongoDB tự sinh `ObjectId` nếu lúc chèn không cung cấp `_id`.

| Nhu cầu | Lệnh trong `mongosh` | Ý nghĩa |
| --- | --- | --- |
| Đọc | `find()`, `findOne()` | Trả về các document thỏa bộ lọc |
| Thêm | `insertOne()`, `insertMany()` | Tạo một hoặc nhiều document |
| Sửa trường | `updateOne()`, `updateMany()` | Thay đổi các trường bằng toán tử như `$set`, `$inc` |
| Thay document | `replaceOne()` | Thay nội dung của một document, giữ nguyên `_id` |
| Xóa | `deleteOne()`, `deleteMany()` | Xóa document phù hợp điều kiện |

`find` là thao tác đọc. Bốn nhóm còn lại là thao tác ghi. MongoDB đảm bảo một thao tác ghi trên **một document** là nguyên tử, kể cả khi sửa nhiều trường của document đó; `updateMany()` hay `deleteMany()` không biến cả tập document thành một giao dịch nguyên tử.

### 1.1. Tạo bộ dữ liệu thực hành

Mở `mongosh` và chọn **database dùng để học**, không thực hiện ví dụ xóa trên dữ liệu thật:

~~~javascript
use spring_data_mongodb_lab

// Alias để các ví dụ sau dễ đọc.
const products = db.products_crud_demo_006;

products.insertMany([
  {
    _id: "p001",
    sku: "SP-001",
    name: "Bàn phím cơ",
    category: "accessory",
    priceVnd: 1200000,
    stock: 12,
    active: true,
    tags: ["office", "wired"],
    supplier: { city: "Hà Nội" }
  },
  {
    _id: "p002",
    sku: "SP-002",
    name: "Chuột không dây",
    category: "accessory",
    priceVnd: 450000,
    stock: 0,
    active: true,
    tags: ["office", "wireless"],
    supplier: { city: "Đà Nẵng" }
  },
  {
    _id: "p003",
    sku: "SP-003",
    name: "Đế laptop",
    category: "desk",
    priceVnd: 550000,
    stock: 8,
    active: true,
    tags: ["office"],
    supplier: { city: "Hà Nội" }
  },
  {
    _id: "p004",
    sku: "SP-004",
    name: "Cáp USB-C",
    category: "accessory",
    priceVnd: 150000,
    stock: 25,
    active: false,
    tags: ["cable"],
    supplier: { city: "Hồ Chí Minh" }
  }
]);
~~~

Các ví dụ tiếp theo giả định dữ liệu ban đầu có đúng bốn document này. Chạy `insertMany` lần nữa với cùng `_id` sẽ gặp lỗi trùng khóa; hãy dùng một collection thử nghiệm mới nếu cần thực hành lại từ đầu.

## 2. Đọc document bằng `find`

### 2.1. Cú pháp và bộ lọc

~~~javascript
db.collection.find(filter, projection)
db.collection.findOne(filter, projection)
~~~

- `filter` là document mô tả điều kiện; `{}` nghĩa là không lọc.
- `projection` chọn những trường cần trả về.
- `find()` trả về **cursor**, cho phép duyệt nhiều document; `findOne()` trả về một document hoặc `null` nếu không tìm thấy.
- Khi nhiều document cùng thỏa điều kiện, không giả định thứ tự kết quả nếu chưa gọi `sort()`.

~~~javascript
// Tất cả sản phẩm.
products.find({});

// Một sản phẩm có _id xác định.
products.findOne({ _id: "p001" });

// Các điều kiện cùng cấp được kết hợp bằng AND.
products.find({
  category: "accessory",
  active: true,
  priceVnd: { $lte: 500000 }
});
// Với dữ liệu gốc: p002.

// Điều kiện OR.
products.find({
  $or: [{ stock: 0 }, { active: false }]
});
// Với dữ liệu gốc: p002 và p004.
~~~

Một số toán tử lọc phổ biến:

| Toán tử | Ví dụ | Diễn giải |
| --- | --- | --- |
| `$eq`, `$ne` | `{ active: { $ne: false } }` | Bằng / khác; `$ne` có thể khớp cả document thiếu trường |
| `$gt`, `$gte` | `{ stock: { $gt: 0 } }` | Lớn hơn / lớn hơn hoặc bằng |
| `$lt`, `$lte` | `{ priceVnd: { $lte: 500000 } }` | Nhỏ hơn / nhỏ hơn hoặc bằng |
| `$in` | `{ category: { $in: ["desk", "accessory"] } }` | Thuộc một tập giá trị |
| `$or`, `$and` | `{ $or: [{ stock: 0 }, { active: false }] }` | Kết hợp điều kiện |
| `$exists` | `{ updatedAt: { $exists: true } }` | Trường có tồn tại hay không |

Trường lồng nhau dùng **dot notation**; với mảng giá trị đơn giản, so khớp bằng một phần tử là đủ:

~~~javascript
// Document có supplier.city = "Hà Nội": p001, p003.
products.find({ "supplier.city": "Hà Nội" });

// Document có mảng tags chứa "office": p001, p002, p003.
products.find({ tags: "office" });

// Tìm SKU trong danh sách cho trước.
products.find({ sku: { $in: ["SP-001", "SP-003"] } });
~~~

**Chú ý kiểu dữ liệu:** `"1200000"` (chuỗi) khác `1200000` (số). `"p001"` cũng khác một `ObjectId` có biểu diễn dạng chuỗi. Bộ lọc sai kiểu thường trả về rỗng dù nhìn giá trị có vẻ giống nhau.

### 2.2. Projection, sắp xếp và phân trang

~~~javascript
// Chỉ lấy tên, SKU và giá; bỏ _id.
products.find(
  { active: true },
  { _id: 0, sku: 1, name: 1, priceVnd: 1 }
);

// Hàng còn tồn: giá tăng dần, _id làm tiêu chí phụ.
products.find({ stock: { $gt: 0 } })
  .sort({ priceVnd: 1, _id: 1 })
  .skip(0)
  .limit(2);

// Đếm số sản phẩm hoạt động.
products.countDocuments({ active: true });
~~~

`1` trong projection nghĩa là **lấy trường**, `0` là **bỏ trường**. Thông thường không trộn chọn và bỏ trong cùng projection, ngoại lệ phổ biến là `_id: 0`. Với `sort()`, `1` là tăng dần, `-1` là giảm dần. `skip()` bỏ qua số document đầu tiên và `limit()` giới hạn số lượng; phân trang sâu bằng `skip` có thể tốn tài nguyên, khi cần hiệu năng hãy cân nhắc phân trang theo khóa có index.

Một truy vấn trả về ít kết quả chưa chắc chạy nhanh: MongoDB vẫn có thể quét nhiều document. Với bộ lọc được sử dụng thường xuyên, cân nhắc index và xem kế hoạch truy vấn bằng `find(filter).explain("executionStats")`; đây là phần tối ưu truy vấn tiếp theo.

## 3. Thêm document bằng `insert`

### 3.1. `insertOne()` và `insertMany()`

~~~javascript
// Tạo một document.
products.insertOne({
  _id: "p005",
  sku: "SP-005",
  name: "Giá treo tai nghe",
  category: "desk",
  priceVnd: 290000,
  stock: 4,
  active: true,
  tags: ["office"],
  supplier: { city: "Hà Nội" }
});

// Tạo nhiều document trong một lời gọi.
products.insertMany([
  {
    _id: "p006",
    sku: "SP-006",
    name: "Lót bàn",
    category: "desk",
    priceVnd: 200000,
    stock: 15,
    active: true
  },
  {
    _id: "p007",
    sku: "SP-007",
    name: "Kẹp dây",
    category: "accessory",
    priceVnd: 50000,
    stock: 30,
    active: true
  }
]);
~~~

Kết quả thành công có `acknowledged` và `insertedId` (một document) hoặc `insertedIds` (nhiều document). Nếu không truyền `_id`, MongoDB tạo giá trị mặc định.

MongoDB mặc định tạo **unique index** cho `_id`. Chèn lại `_id: "p005"` sẽ phát sinh `E11000 duplicate key`. Trường `sku` trong ví dụ chỉ là trường thông thường; để thực sự bắt buộc duy nhất, cần tạo unique index riêng, chẳng hạn:

~~~javascript
products.createIndex({ sku: 1 }, { unique: true });
~~~

Với `insertMany()`, mặc định `ordered: true` khiến lệnh dừng xử lý các phần tử tiếp theo khi gặp lỗi ghi. Tùy chọn `{ ordered: false }` cho phép tiếp tục thử những document còn lại, nhưng **không** khiến toàn bộ lô ghi trở thành nguyên tử. Với dữ liệu sản xuất, cần xác định chính sách xử lý thành công một phần.

## 4. Sửa từng trường bằng `update`

### 4.1. Vì sao dùng toán tử cập nhật?

`updateOne(filter, update, options)` thay đổi tối đa **một** document khớp điều kiện; `updateMany(filter, update, options)` thay đổi **mọi** document khớp. Khi dùng dạng update document, đối số `update` chứa các toán tử như `$set` hoặc `$inc`.

~~~javascript
// Xuất 2 chiếc p001 nếu số tồn kho vẫn đủ.
const updateResult = products.updateOne(
  { _id: "p001", stock: { $gte: 2 } },
  {
    $inc: { stock: -2 },
    $set: { updatedAt: new Date() }
  }
);

printjson(updateResult);
// Nếu chạy một lần từ dữ liệu gốc: stock của p001 từ 12 thành 10.

// Đánh dấu khuyến mãi cho tất cả phụ kiện đang hoạt động.
products.updateMany(
  { category: "accessory", active: true },
  { $set: { promotion: true } }
);
// Nếu chạy sau ví dụ trên: p001 và p002 được thêm promotion: true.
~~~

Đặt điều kiện `stock: { $gte: 2 }` trong cùng `updateOne()` với `$inc` giúp kiểm tra và trừ hàng trên **một document** trong một thao tác nguyên tử. Cách đọc tồn kho về ứng dụng, tự trừ rồi ghi lại có thể gây mất cập nhật khi nhiều yêu cầu đến cùng lúc.

| Toán tử cập nhật | Tác dụng | Ví dụ đối số |
| --- | --- | --- |
| `$set` | Đặt giá trị trường (tạo trường nếu chưa có) | `{ $set: { active: false } }` |
| `$unset` | Bỏ hẳn một trường | `{ $unset: { promotion: "" } }` |
| `$inc` | Cộng số âm/dương vào trường số | `{ $inc: { stock: 3 } }` |
| `$push` | Nối thêm phần tử vào mảng, có thể trùng | `{ $push: { tags: "new" } }` |
| `$addToSet` | Thêm phần tử vào mảng nếu chưa có phần tử bằng nó | `{ $addToSet: { tags: "new" } }` |
| `$pull` | Loại phần tử mảng khớp điều kiện | `{ $pull: { tags: "wired" } }` |
| `$setOnInsert` | Đặt trường chỉ khi `upsert` tạo document mới | `{ $setOnInsert: { createdAt: new Date() } }` |

Ví dụ sửa riêng trường lồng nhau và mảng:

~~~javascript
// Giữ các trường khác của supplier, chỉ đổi city.
products.updateOne(
  { _id: "p002" },
  {
    $set: { "supplier.city": "Hải Phòng" },
    $addToSet: { tags: "featured" }
  }
);

// Bỏ một trường không còn cần thiết.
products.updateOne(
  { _id: "p002" },
  { $unset: { promotion: "" } }
);
~~~

`$set: { supplier: { city: "Hải Phòng" } }` sẽ thay **toàn bộ** subdocument `supplier`; dùng `"supplier.city"` khi chỉ muốn đổi một thuộc tính con.

### 4.2. Đọc kết quả và sử dụng `upsert`

Một kết quả cập nhật thường có:

- `matchedCount`: số document khớp bộ lọc.
- `modifiedCount`: số document thực sự bị thay đổi; có thể bằng `0` dù `matchedCount = 1` nếu giá trị mới trùng giá trị cũ.
- `upsertedCount` và `upsertedId`: số lượng/`_id` được chèn khi bật `upsert`.
- `acknowledged`: server đã xác nhận thao tác theo write concern áp dụng.

~~~javascript
// Không tìm thấy SP-009 thì tạo mới; tìm thấy thì sửa các trường trong $set.
products.updateOne(
  { sku: "SP-009" },
  {
    $set: {
      name: "Lót chuột",
      category: "accessory",
      priceVnd: 90000,
      stock: 20,
      active: true
    },
    $setOnInsert: { createdAt: new Date() }
  },
  { upsert: true }
);
~~~

Mặc định `upsert: false`: nếu không khớp document nào thì không có gì thay đổi. Khi `upsert: true`, thao tác có thể thêm document mới; cần thiết kế filter theo khóa định danh đáng tin cậy (thường là khóa có unique index) để tránh tạo bản ghi trùng trong các yêu cầu đồng thời. Trong ví dụ, `SP-009` được sinh `_id` tự động vì không chỉ định `_id`.

## 5. Thay cả document bằng `replace`

`replaceOne(filter, replacement, options)` thay nội dung của tối đa một document bằng **replacement document**. Khác `updateOne`, replacement **không dùng** `$set`, `$inc` và các toán tử cập nhật. Trường cũ không được đưa vào replacement sẽ **biến mất**; trường `_id` của document hiện có phải giữ nguyên.

~~~javascript
products.replaceOne(
  { _id: "p003" },
  {
    _id: "p003",            // Giữ nguyên _id.
    sku: "SP-003",
    name: "Đế laptop nhôm",
    category: "desk",
    priceVnd: 590000,
    stock: 8,
    active: true,
    tags: ["office", "aluminum"],
    supplier: { city: "Hà Nội" }
  }
);

products.findOne({ _id: "p003" });
~~~

Thao tác trên thay document `p003` bằng phiên bản mới. Nếu replacement bỏ `tags`, `supplier` hoặc một trường khác đang có, các trường đó không còn sau khi thay. Có thể **bỏ `_id` khỏi replacement** để MongoDB giữ `_id` hiện tại; tuyệt đối không cố đổi `_id` sang giá trị khác.

`replaceOne()` cũng hỗ trợ `{ upsert: true }`. Chỉ dùng khi xác định rõ dữ liệu đầy đủ của document mới và quy tắc định danh. Khi chỉ sửa một vài trường, ưu tiên `updateOne()` với `$set`, `$inc` để tránh mất dữ liệu ngoài ý muốn.

## 6. Xóa document bằng `delete`

`deleteOne(filter)` xóa tối đa một document thỏa điều kiện, `deleteMany(filter)` xóa tất cả document thỏa điều kiện. Kết quả chứa `deletedCount`.

~~~javascript
// Xóa đúng một document theo khóa duy nhất.
products.deleteOne({ _id: "p007" });

// Chỉ xóa sản phẩm đã đánh dấu ngừng hoạt động.
products.deleteMany({ active: false });
// Nếu chưa thay active ở bước khác, p004 bị xóa.
~~~

**Trước khi xóa hàng loạt**, chạy đúng bộ lọc đó bằng `find()` hoặc `countDocuments()`:

~~~javascript
const filter = { active: false, category: "accessory" };
products.find(filter, { _id: 1, sku: 1, name: 1 });
products.countDocuments(filter);

// Chỉ thực hiện sau khi xác nhận tập kết quả là đúng.
products.deleteMany(filter);
~~~

`deleteMany({})` sẽ xóa **mọi** document trong collection; `deleteOne({})` chọn một document không xác định nếu không có điều kiện đủ cụ thể. Xóa document không tự tạo cơ chế khôi phục hay soft delete. Nếu nghiệp vụ cần lịch sử, cân nhắc đánh dấu `active: false` hoặc `deletedAt` rồi thiết kế truy vấn chỉ lấy bản ghi còn hiệu lực.

## 7. Phân biệt `update` và `replace` qua cùng một tình huống

Giả sử document hiện có:

~~~javascript
{
  _id: "p010",
  name: "Chuột",
  priceVnd: 300000,
  stock: 5,
  tags: ["wireless"]
}
~~~

Nếu gọi:

~~~javascript
products.updateOne(
  { _id: "p010" },
  { $set: { priceVnd: 280000 } }
);
~~~

thì chỉ `priceVnd` thay đổi; `name`, `stock`, `tags` vẫn tồn tại. Ngược lại:

~~~javascript
products.replaceOne(
  { _id: "p010" },
  { _id: "p010", name: "Chuột", priceVnd: 280000 }
);
~~~

thì `stock` và `tags` bị loại khỏi document. Hai lệnh này là **ví dụ so sánh giả định**: cần chèn `p010` trước nếu muốn chạy thực tế.

| Tiêu chí | `updateOne()` với toán tử | `replaceOne()` |
| --- | --- | --- |
| Dữ liệu truyền vào | Các thay đổi bằng `$set`, `$inc`… | Toàn bộ document thay thế |
| Trường không nhắc tới | Được giữ lại | Bị bỏ khỏi document |
| `_id` | Không thể sửa | Phải giữ nguyên của document cũ |
| Trường hợp phù hợp | Thay giá, trừ tồn, thêm tag | Đồng bộ lại toàn bộ bản ghi từ nguồn có đủ dữ liệu |

## 8. Liên hệ trực tiếp với Spring Data MongoDB

Spring Data MongoDB ánh xạ document ↔ đối tượng Java qua `@Document`, `@Id` và các quy tắc mapping. `MongoTemplate` cung cấp thao tác tương ứng gần với MongoDB gốc, còn `MongoRepository` tiện cho CRUD theo entity và truy vấn suy ra từ tên phương thức.

### 8.1. Mô hình ánh xạ

Ví dụ Java 17+ dưới đây dùng `record` để tập trung vào thao tác dữ liệu. Trong ứng dụng thực tế có thể dùng class POJO tương đương:

~~~java
import java.util.List;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "products_crud_demo_006")
public record Product(
    @Id String id,
    String sku,
    String name,
    String category,
    long priceVnd,
    int stock,
    boolean active,
    List<String> tags,
    Supplier supplier
) {
    public record Supplier(String city) {}
}
~~~

`id` là thuộc tính Java được ánh xạ vào `_id` trong MongoDB. Một document có `_id` kiểu chuỗi `"p001"` khác với `ObjectId`, vì vậy cần thống nhất cách lưu/đọc định danh. Ví dụ shell ở trên cố ý dùng chuỗi ngắn để dễ thực hành.

### 8.2. Các lệnh tương ứng trong `MongoTemplate`

Các đoạn Java sau có thể đặt trong một service đã inject `MongoTemplate template`. Chúng minh họa cách gọi API, không yêu cầu chạy nối tiếp các ví dụ `mongosh` trước đó.

~~~java
import com.mongodb.client.result.DeleteResult;
import com.mongodb.client.result.UpdateResult;
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.ReplaceOptions;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

// READ: find(filter).sort(...).limit(...)
Query inStockQuery = Query.query(
    Criteria.where("active").is(true).and("stock").gt(0)
).with(Sort.by(Sort.Order.asc("priceVnd"), Sort.Order.asc("id")))
 .limit(10);
List<Product> inStock = template.find(inStockQuery, Product.class);

// INSERT: tương đương insertOne().
Product newProduct = new Product(
    "p008", "SP-008", "Bộ hub USB-C", "accessory",
    390000L, 5, true, List.of("office"),
    new Product.Supplier("Hà Nội")
);
Product inserted = template.insert(newProduct);

// UPDATE ONE: thay đổi đúng trường stock, có điều kiện để tránh âm kho.
UpdateResult updated = template.updateFirst(
    Query.query(Criteria.where("id").is("p008").and("stock").gte(1)),
    new Update().inc("stock", -1),
    Product.class
);

// UPDATE MANY: cùng một thay đổi trên tất cả document phù hợp.
UpdateResult updatedMany = template.updateMulti(
    Query.query(Criteria.where("category").is("accessory")
                         .and("active").is(false)),
    new Update().set("active", true),
    Product.class
);

// REPLACE ONE: truyền đối tượng chứa toàn bộ thông tin muốn giữ lại.
Product replacement = new Product(
    "p008", "SP-008", "Bộ hub USB-C 6 cổng", "accessory",
    490000L, 4, true, List.of("office", "usb-c"),
    new Product.Supplier("Hà Nội")
);
UpdateResult replaced = template.replace(
    Query.query(Criteria.where("id").is("p008")),
    replacement,
    ReplaceOptions.none()
);

// DELETE: remove(Query, Class) xóa các document khớp filter.
DeleteResult deleted = template.remove(
    Query.query(Criteria.where("id").is("p008")),
    Product.class
);
~~~

Trong Spring Data, `Criteria.where("id")` được ánh xạ theo thuộc tính `@Id` sang `_id` khi truy vấn với entity `Product`. `updateFirst` tương ứng `updateOne`; `updateMulti` tương ứng `updateMany`; `replace` tương ứng `replaceOne`. Với `template.remove(Query, Product.class)`, mọi document khớp `Query` đều có thể bị xóa, vì vậy ví dụ dùng điều kiện `id` duy nhất.

**Điểm cần nhớ với replacement:** đối tượng thay thế phải có bộ trường đầy đủ và `id` hợp lệ. Theo API Spring Data, `replace` không được dùng để đổi `_id` của document hiện có. Khi dùng `replace` + `upsert` mà entity sử dụng kiểu id riêng, cần kiểm soát `_id` trong query hoặc replacement để tránh phát sinh kiểu `ObjectId` ngoài mong muốn.

### 8.3. Dùng `MongoRepository` khi thao tác theo entity

~~~java
import java.util.List;
import java.util.Optional;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface ProductRepository extends MongoRepository<Product, String> {
    Optional<Product> findBySku(String sku);
    List<Product> findByActiveTrueAndStockGreaterThan(int minStock);
}
~~~

~~~java
// Ví dụ một service đã inject ProductRepository repository.
Optional<Product> one = repository.findById("p001");
List<Product> available = repository.findByActiveTrueAndStockGreaterThan(0);

// save() chèn nếu mới; với _id đã tồn tại, nó ghi lại trạng thái entity.
Product saved = repository.save(newProduct);
repository.deleteById("p008");
~~~

`save()` không phải bản sao của `$set`: khi lưu entity đang tồn tại, việc ghi lại document có thể làm mất các trường không được ánh xạ vào entity. Với yêu cầu tăng/giảm một trường, cần điều kiện cập nhật nguyên tử hoặc sửa đúng trường, hãy dùng `MongoTemplate.updateFirst` / `updateMulti` hay truy vấn cập nhật phù hợp.

Trong luồng **reactive**, `ReactiveMongoTemplate` và `ReactiveMongoRepository` cung cấp các thao tác tương tự nhưng trả về `Mono` / `Flux`. Các Publisher cần được subscribe bởi chuỗi reactive mới thực thi; không áp dụng trực tiếp giả định “gọi phương thức xong là đã ghi” như API đồng bộ.

## 9. Lỗi thường gặp và cách tự kiểm tra

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra/xử lý |
| --- | --- | --- |
| `find()` trả rỗng dù thấy dữ liệu | Sai database, collection, tên trường, kiểu `_id`, kiểu dữ liệu hoặc chữ hoa/thường | `db.getName()`, `products.findOne({})`, so sánh đúng kiểu |
| `E11000 duplicate key` khi insert | `_id` hoặc trường có unique index bị trùng | Kiểm tra giá trị và `products.getIndexes()`; dùng khóa mới hoặc xử lý nghiệp vụ tạo mới |
| `matchedCount: 1`, `modifiedCount: 0` | Giá trị đã bằng giá trị mong muốn | Đọc document sau cập nhật, không mặc định coi là lỗi |
| `matchedCount: 0` | Không có document khớp, hoặc điều kiện đồng thời (như `stock >= 2`) không còn đúng | Dùng `findOne(filter)` với đúng filter của update |
| Mất trường sau khi sửa | Dùng `replaceOne` hoặc `save` với đối tượng thiếu thuộc tính | Chuyển sang `$set` / `$inc` nếu chỉ sửa vài trường |
| Sửa/xóa quá nhiều document | Filter rộng hoặc `{}` | Dùng `find(filter)`, `countDocuments(filter)` trước thao tác ghi |
| Truy vấn chậm | Quét collection, sort không có index phù hợp, `skip` sâu | Kiểm tra `explain("executionStats")` và index dựa trên truy vấn thực tế |

Khi thay đổi nhiều document liên quan, đừng giả định các lệnh CRUD đơn lẻ sẽ bảo đảm tính nhất quán xuyên document. Chỉ dùng transaction khi yêu cầu nghiệp vụ thực sự cần và triển khai MongoDB hỗ trợ; các transaction, index nâng cao, aggregation và phân tích hiệu năng chuyên sâu là những chủ đề tiếp theo của module Spring Data MongoDB.

## 10. Bài thực hành ngắn

Hãy thử ba truy vấn **ngay sau khi nạp bốn document ban đầu** ở mục 1, trước khi thực hiện các lệnh ghi về sau:

1. Lấy `sku`, `name` và `stock` của các sản phẩm đang hoạt động và còn hàng, không trả về `_id`.
2. Tìm phụ kiện hoạt động có giá không quá 500.000 VND.
3. Liệt kê các sản phẩm mà `supplier.city` là `"Hà Nội"`, sắp xếp giá giảm dần.

**Đáp án tham khảo:**

~~~javascript
// 1. Dự kiến: p001 và p003.
products.find(
  { active: true, stock: { $gt: 0 } },
  { _id: 0, sku: 1, name: 1, stock: 1 }
);

// 2. Dự kiến: p002.
products.find({
  category: "accessory",
  active: true,
  priceVnd: { $lte: 500000 }
});

// 3. Dự kiến: p001 rồi p003.
products.find({ "supplier.city": "Hà Nội" })
  .sort({ priceVnd: -1, _id: 1 });
~~~

Tiếp theo, tự viết một `updateOne()` giảm tồn kho của `p003` đi 1 **chỉ nếu `stock > 0`**, đọc `matchedCount` và kiểm chứng số tồn bằng `findOne()`. Thử viết `replaceOne()` cho `p003` với một trường bị bỏ đi trong replacement và quan sát sự khác biệt so với `updateOne()` trên collection thử nghiệm.

## Tài liệu tham khảo

- [MongoDB Manual — CRUD Operations](https://www.mongodb.com/docs/manual/crud/): nhóm lệnh đọc, ghi và tính nguyên tử của thao tác.
- [MongoDB Manual — Update Methods](https://www.mongodb.com/docs/manual/reference/update-methods/): phân biệt `updateOne`, `updateMany` và `replaceOne`.
- [Spring Data MongoDB — Saving, Updating, and Removing Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html): `MongoTemplate`, update, replace, delete và các API liên quan.
