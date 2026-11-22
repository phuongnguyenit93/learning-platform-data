# Ảnh hưởng của cấu trúc mảng đến multikey index và kế hoạch truy vấn MongoDB

## 1. Vì sao cấu trúc mảng làm thay đổi chiến lược index?

MongoDB cho phép một document lưu mảng các giá trị đơn hoặc mảng document nhúng. Điều đó rất phù hợp với những thông tin thường được đọc cùng nhau, chẳng hạn tags của sản phẩm, các biến thể màu sắc, điểm đánh giá hoặc dòng hàng trong đơn. Nhưng một **mảng không giống một field scalar** khi MongoDB lập index: một document có thể đóng góp nhiều index key, và hai điều kiện trên một mảng có thể được thỏa mãn bởi hai phần tử khác nhau.

Ví dụ:

~~~javascript
{
  _id: "p001",
  category: "tech",
  tags: ["mongodb", "backend"],
  variants: [
    { color: "red", stock: 0 },
    { color: "blue", stock: 6 }
  ]
}
~~~

Truy vấn **có tag mongodb** có thể hưởng lợi từ index trên tags. Nhưng yêu cầu **có một biến thể vừa màu đỏ vừa còn hàng** phải dùng điều kiện ràng buộc cùng phần tử; không thể chỉ so khớp hai đường dẫn con độc lập rồi mặc định chúng thuộc cùng biến thể.

Sau bài học này, bạn sẽ:

- Hiểu **multikey index** hình thành từ Array và tạo nhiều khóa cho một document như thế nào.
- Phân biệt **Array scalar** với **Array embedded documents** khi lập index và truy vấn.
- Sử dụng **$elemMatch** để áp điều kiện cho đúng một phần tử và hỗ trợ kết hợp index bounds.
- Hiểu hạn chế của **compound multikey index**, nhất là hai Array độc lập.
- Đọc **IXSCAN**, **FETCH**, **SORT**, **indexBounds**, **isMultiKey** và các số liệu executionStats.
- Cân nhắc độ dài mảng, chi phí cập nhật index, giới hạn document và cách thiết kế dữ liệu có thể tăng trưởng.

Các ví dụ dùng **mongosh** và database riêng **mongo_multikey_lab**. Bộ dữ liệu cố định để chạy lại được. Những đánh giá hiệu năng thực tế phải dựa trên dữ liệu và lưu lượng đại diện, không lấy kết quả của vài document làm benchmark.

## 2. Multikey index vận hành như thế nào?

### 2.1. Scalar field so với Array field

Với một document:

~~~javascript
{ _id: "p001", category: "tech" }
~~~

Index thông thường trên **category** chứa một khóa cho giá trị tech của document đó. Với Array:

~~~javascript
{ _id: "p001", tags: ["mongodb", "backend", "tutorial"] }
~~~

Index trên **tags** cần cho phép tìm theo từng phần tử của mảng:

~~~javascript
db.products.createIndex({ tags: 1 });
~~~

MongoDB **tự động tạo multikey index** khi indexed field chứa Array; không có bước tạo index loại multikey riêng bắt buộc. Về mặt khái niệm:

~~~text
Giá trị index       Document trỏ tới
"backend"         -> p001
"mongodb"         -> p001
"tutorial"        -> p001
~~~

MongoDB tạo entry cho những giá trị riêng biệt trong mảng. Nếu cùng giá trị lặp trong một Array, nó không cần tạo nhiều entry trùng giá trị cho chính document đó. Một document có thể xuất hiện sau nhiều index key khác nhau, nhưng kết quả của find là **document**, không phải các entry index được nhân lên.

### 2.2. Trường con trong Array document

~~~javascript
{
  _id: "p001",
  variants: [
    { color: "red", stock: 0 },
    { color: "blue", stock: 6 }
  ]
}
~~~

Có thể lập index trên field con theo dotted path:

~~~javascript
db.products.createIndex({ "variants.color": 1 });
~~~

Truy vấn:

~~~javascript
db.products.find({ "variants.color": "red" });
~~~

khớp document có ít nhất một phần tử variants với color bằng red. Nếu field có nhiều phần tử nhúng, index tạo những key ứng với giá trị các phần tử trên đường dẫn đó. Không cần tạo collection riêng chỉ để có khả năng tìm theo field con, nhưng độ lớn mảng và tần suất cập nhật vẫn quyết định thiết kế nào thích hợp.

### 2.3. Hình dạng Array quyết định chi phí

| Hình dạng field | Ví dụ | Ý nghĩa đối với index |
| --- | --- | --- |
| Scalar | category: "tech" | Một giá trị khóa theo field |
| Array scalar | tags: ["mongodb", "backend"] | Nhiều khóa từ giá trị phần tử |
| Array nhúng | variants: [{color: "red"}, {color: "blue"}] | Index đường dẫn variants.color trở thành multikey |
| Array rỗng | tags: [] | Không có phần tử nào thỏa phép so khớp tag |
| Array có giá trị lặp | tags: ["sale", "sale"] | Không tự tạo hai document kết quả cho tag sale |
| Array tăng liên tục | events: [các sự kiện không giới hạn] | Số key và kích thước document có thể tăng mạnh |

MongoDB có giới hạn **16 MiB cho một BSON document**. Trước cả khi chạm giới hạn này, mảng quá lớn có thể tăng chi phí ghi, kích thước index, băng thông và độ cạnh tranh khi nhiều thao tác cùng cập nhật một document.

## 3. Dữ liệu mẫu và index có thể chạy lại

Ta dùng sáu sản phẩm trong một tenant. Mỗi sản phẩm có **tags** (Array String), **scores** (Array Number) và **variants** (Array document chứa color, stock). Bộ dữ liệu cố ý có một sản phẩm màu đỏ hết hàng nhưng màu xanh còn hàng để quan sát tác dụng của $elemMatch.

Chạy toàn bộ khối sau bằng mongosh:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_multikey_lab");
  const products = lab.getCollection("lab_products");
  const tag = "multikey-practice-v1";
  const tenant = "lab-shop";

  // Chỉ dọn document thuộc dataset của bài.
  products.deleteMany({ dataset: tag });

  products.insertMany([
    {
      _id: "p001", dataset: tag, tenantId: tenant,
      category: "tech", name: "Bộ học Backend",
      price: NumberDecimal("100.00"),
      tags: ["mongodb", "backend"],
      scores: [65, 95],
      variants: [
        { color: "red", stock: NumberInt(0) },
        { color: "blue", stock: NumberInt(6) }
      ]
    },
    {
      _id: "p002", dataset: tag, tenantId: tenant,
      category: "tech", name: "Bộ học Database",
      price: NumberDecimal("130.00"),
      tags: ["database", "backend"],
      scores: [85, 91],
      variants: [{ color: "red", stock: NumberInt(7) }]
    },
    {
      _id: "p003", dataset: tag, tenantId: tenant,
      category: "books", name: "Sách MongoDB",
      price: NumberDecimal("40.00"),
      tags: ["mongodb", "tutorial"],
      scores: [80],
      variants: [{ color: "green", stock: NumberInt(5) }]
    },
    {
      _id: "p004", dataset: tag, tenantId: tenant,
      category: "tech", name: "Bộ thực hành MongoDB",
      price: NumberDecimal("85.00"),
      tags: ["mongodb", "backend", "sale"],
      scores: [70, 88],
      variants: [
        { color: "black", stock: NumberInt(12) },
        { color: "red", stock: NumberInt(2) }
      ]
    },
    {
      _id: "p005", dataset: tag, tenantId: tenant,
      category: "books", name: "Sách nhập môn",
      price: NumberDecimal("65.00"),
      tags: [], scores: [], variants: []
    },
    {
      _id: "p006", dataset: tag, tenantId: tenant,
      category: "tech", name: "Bộ học Frontend",
      price: NumberDecimal("120.00"),
      tags: ["frontend", "sale"],
      scores: [99],
      variants: [{ color: "red", stock: NumberInt(0) }]
    }
  ]);

  // Một Array cùng hai điều kiện equality scalar.
  products.createIndex(
    { tenantId: 1, category: 1, tags: 1 },
    { name: "ix_tenant_category_tags" }
  );

  // Hai field con nằm trong CÙNG Array path variants.
  products.createIndex(
    { tenantId: 1, "variants.color": 1, "variants.stock": 1 },
    { name: "ix_tenant_variant_color_stock" }
  );

  // Index scalar phục vụ lọc category và sort price.
  products.createIndex(
    { tenantId: 1, category: 1, price: 1 },
    { name: "ix_tenant_category_price" }
  );

  // Một index Array riêng cho bài toán interval.
  products.createIndex(
    { scores: 1 },
    { name: "ix_scores" }
  );

  print("Tổng sản phẩm: " +
    products.countDocuments({ dataset: tag }));
})();
~~~

**Kết quả mong đợi: 6 document.** ID và ngày không phụ thuộc thời gian chạy; nếu đã thay đổi tags/stock, chạy lại khối này sẽ phục hồi dữ liệu. Các lệnh deleteMany và insertMany không thuộc một transaction, nên chỉ sử dụng trong môi trường học tập riêng.

Để gọn kết quả, khai báo hàm phụ trong phiên mongosh:

~~~javascript
function showProductIds(label, filter) {
  const c = db.getSiblingDB("mongo_multikey_lab")
    .getCollection("lab_products");

  const ids = c.find(
      {
        $and: [
          { dataset: "multikey-practice-v1", tenantId: "lab-shop" },
          filter
        ]
      },
      { _id: 1 }
    )
    .sort({ _id: 1 })
    .toArray()
    .map(doc => doc._id);

  print(label + ": " + JSON.stringify(ids));
  return ids;
}
~~~

Hàm giúp các ví dụ luôn lọc theo dataset và tenant. Nếu mở phiên mongosh mới, cần chạy lại định nghĩa hàm trước khi gọi.

## 4. Truy vấn Array scalar và ý nghĩa của index

### 4.1. Tìm một phần tử

~~~javascript
showProductIds("Có mongodb", { tags: "mongodb" });
// ["p001", "p003", "p004"]
~~~

MongoDB so khớp khi mảng chứa phần tử bằng mongodb. Index trên tags có thể giúp truy cập các khóa mongodb và tìm document ứng viên mà không quét toàn bộ collection. Tính hiệu quả còn phụ thuộc bao nhiêu document có cùng tag đó.

### 4.2. Tìm đủ nhiều phần tử bằng $all

~~~javascript
showProductIds(
  "Có cả mongodb và backend",
  { tags: { $all: ["mongodb", "backend"] } }
);
// ["p001", "p004"]
~~~

**$all** yêu cầu Array có đủ các phần tử, không cần đúng thứ tự. Tuy nhiên, không thể khẳng định mọi điều kiện $all luôn được giao hoàn toàn ở mức index: cần quan sát **indexBounds** và FETCH từ explain để biết MongoDB đã đánh giá phần nào trong index, phần nào sau khi đọc document.

### 4.3. Equality cả mảng khác với equality một phần tử

~~~javascript
showProductIds(
  "Đúng toàn Array",
  { tags: ["mongodb", "backend"] }
);
// ["p001"]

showProductIds(
  "Chứa backend",
  { tags: "backend" }
);
// ["p001", "p002", "p004"]
~~~

Truy vấn với toàn Array kiểm tra **mảng theo thứ tự và giá trị**; khác với kiểm tra một phần tử bất kỳ. Multikey index có thể giúp tìm ứng viên theo phần tử đầu của mảng, nhưng không thể tự chứng minh mọi trường hợp equality toàn Array chỉ bằng giá trị của từng index entry. MongoDB có thể cần **FETCH** document để so sánh cấu trúc mảng nguyên vẹn.

### 4.4. $size không tự được giải quyết bởi index tags

~~~javascript
showProductIds("Tags rỗng", { tags: { $size: 0 } });
// ["p005"]
~~~

**$size** so sánh số phần tử của Array. Một multikey index lưu giá trị phần tử, không trực tiếp cung cấp số phần tử theo cách giúp giải quyết riêng điều kiện $size. Nếu nghiệp vụ thường xuyên lọc theo độ dài mảng, cân nhắc trường scalar **tagsCount** được duy trì nhất quán với tags và index thích hợp. Việc thêm trường tổng hợp cũng tạo chi phí ghi, vì vậy phải xuất phát từ access pattern.

## 5. $elemMatch trên Array document: cùng phần tử hay nhiều phần tử?

### 5.1. Điều kiện dotted path độc lập

Yêu cầu nghiệp vụ: **sản phẩm có một biến thể màu đỏ và số lượng tồn lớn hơn 0**. Truy vấn:

~~~javascript
showProductIds(
  "Hai điều kiện trên variants",
  {
    "variants.color": "red",
    "variants.stock": { $gt: 0 }
  }
);
// ["p001", "p002", "p004"]
~~~

Tại sao có **p001**? Document này có phần tử màu đỏ nhưng stock 0, đồng thời một phần tử màu xanh có stock 6. Hai điều kiện được thỏa nhờ **hai phần tử khác nhau**. Query không có $elemMatch chỉ khẳng định cả hai thuộc tính xuất hiện trong document, chứ chưa buộc chúng thuộc một biến thể.

~~~text
p001.variants
  +--------------------+    +--------------------+
  | color: red         |    | color: blue        |
  | stock: 0           |    | stock: 6           |
  +--------------------+    +--------------------+
        |                          |
        +-- khớp color             +-- khớp stock > 0

Tổng thể document khớp hai điều kiện độc lập.
Không có biến thể nào thỏa cả hai điều kiện.
~~~

### 5.2. $elemMatch yêu cầu đồng thời trên một phần tử

~~~javascript
showProductIds(
  "Một biến thể red còn hàng",
  {
    variants: {
      $elemMatch: {
        color: "red",
        stock: { $gt: 0 }
      }
    }
  }
);
// ["p002", "p004"]
~~~

**$elemMatch** chỉ khớp khi tồn tại **một phần tử variants** cùng thỏa color red và stock > 0. Do đó p001 không được trả về; p006 cũng không khớp vì biến thể red hết hàng.

Đây là một vấn đề **đúng/sai nghiệp vụ**, không chỉ là tối ưu hiệu năng. Nếu ứng dụng bán sản phẩm dựa trên truy vấn độc lập, nó có thể cho thấy biến thể màu đỏ còn hàng dù thực tế chỉ màu khác còn hàng.

## 6. Index bounds trên Array và vai trò của $elemMatch

**Index bounds** mô tả phạm vi giá trị key mà MongoDB quét trong một index. Khi trường là scalar, hai điều kiện range có thể giao thành một khoảng hẹp. Khi trường là Array, điều kiện range có thể được thỏa bởi các phần tử khác nhau, do đó không thể luôn giao bounds mà vẫn giữ nguyên tập kết quả.

### 6.1. Khoảng điểm số không dùng $elemMatch

Product p001 có **scores = [65, 95]**.

~~~javascript
showProductIds(
  "scores >= 80 và <= 90",
  { scores: { $gte: 80, $lte: 90 } }
);
// ["p001", "p002", "p003", "p004"]
~~~

p001 khớp vì 95 thỏa $gte: 80, còn 65 thỏa $lte: 90. Không có một phần tử nào nằm trong [80, 90]. Nếu index scan chỉ lấy các key trong [80, 90], p001 sẽ bị loại sai. Khi không có $elemMatch, MongoDB phải bảo toàn semantics này; planner có thể dùng một bound rồi đánh giá điều kiện còn lại trên document.

### 6.2. Khoảng điểm số với $elemMatch

~~~javascript
showProductIds(
  "Có một score trong [80, 90]",
  {
    scores: {
      $elemMatch: { $gte: 80, $lte: 90 }
    }
  }
);
// ["p002", "p003", "p004"]
~~~

Đây mới là truy vấn yêu cầu **một score duy nhất nằm trong khoảng**. $elemMatch có thể cho phép MongoDB **giao các ranh giới** trên multikey index thành khoảng hiệu quả hơn vì không còn nguy cơ bỏ sót document khớp nhờ các phần tử khác nhau.

### 6.3. Quan sát indexBounds trực tiếp

~~~javascript
(() => {
  const c = db.getSiblingDB("mongo_multikey_lab")
    .getCollection("lab_products");

  const withoutElemMatch = c.find({
    dataset: "multikey-practice-v1",
    scores: { $gte: 80, $lte: 90 }
  }).hint("ix_scores").explain("executionStats");

  const withElemMatch = c.find({
    dataset: "multikey-practice-v1",
    scores: { $elemMatch: { $gte: 80, $lte: 90 } }
  }).hint("ix_scores").explain("executionStats");

  print("Không có $elemMatch:");
  printjson(withoutElemMatch);
  print("Có $elemMatch:");
  printjson(withElemMatch);
})();
~~~

Tìm **indexBounds** bên trong IXSCAN của hai kế hoạch. Đọc thêm **totalKeysExamined**, **totalDocsExamined**, **nReturned** và xem có FETCH hay không. Dùng **hint** ở lab để quan sát cùng index; trong ứng dụng thật, không nên ép hint mặc định khi chưa đo kế hoạch tối ưu trên dữ liệu đại diện.

### 6.4. Kết hợp bounds cho các field con chung Array path

Index:

~~~javascript
{
  tenantId: 1,
  "variants.color": 1,
  "variants.stock": 1
}
~~~

Hai field color và stock cùng nằm trong Array path **variants**. Để MongoDB có cơ sở **compound bounds** của hai field này, truy vấn cần thể hiện điều kiện trên cùng phần tử:

~~~javascript
db.getSiblingDB("mongo_multikey_lab")
  .getCollection("lab_products")
  .find({
    tenantId: "lab-shop",
    variants: {
      $elemMatch: {
        color: "red",
        stock: { $gt: 0 }
      }
    }
  })
  .hint("ix_tenant_variant_color_stock")
  .explain("executionStats");
~~~

Đây là trường hợp **hai field con có cùng tiền tố Array path**. Nếu chỉ dùng hai dotted predicates độc lập, có thể không thể compound hai bounds chặt như truy vấn với $elemMatch. Đường dẫn đặt $elemMatch phải đúng **variants**, tức phần chung trước color và stock.

## 7. Compound multikey index: khả năng và giới hạn

### 7.1. Một Array kết hợp nhiều scalar

Index **{ tenantId: 1, category: 1, tags: 1 }** là một compound multikey index hợp lệ với dữ liệu của bài: tenantId/category là scalar, tags là Array. Nó hỗ trợ mẫu lọc:

~~~javascript
db.getSiblingDB("mongo_multikey_lab")
  .getCollection("lab_products")
  .find({
    tenantId: "lab-shop",
    category: "tech",
    tags: "mongodb"
  });
// p001 và p004.
~~~

Trong compound index, **thứ tự field** quyết định khả năng tận dụng tiền tố index. Mẫu truy vấn theo tenant và category có thể được hưởng lợi từ hai field đầu, rồi dùng tags để thu hẹp thêm. Không cần tự tạo index cho mọi tổ hợp nếu các query thực tế chỉ tập trung ở một vài access pattern.

### 7.2. Hai Array độc lập trong cùng compound index bị giới hạn

Ví dụ:

~~~javascript
{
  _id: "example",
  tags: ["mongodb", "backend"],
  regions: ["north", "south"]
}
~~~

Không thể tùy tiện tạo compound multikey index trên **tags** và **regions** nếu cùng document chứa cả hai field là Array:

~~~javascript
// Ví dụ minh họa cấu hình không hợp lệ khi có hai Array song song:
// db.products.createIndex({ tags: 1, regions: 1 });
~~~

MongoDB giới hạn **parallel arrays** trong compound multikey index. Nếu document hiện tại đã có cả hai Array, tạo index có thể bị từ chối. Nếu index tồn tại trước, một insert/update khiến document chứa hai mảng được index có thể thất bại.

**Không nhầm với variants.color + variants.stock**: hai field đó nằm trong cùng một Array of embedded documents và có thể được compound khi thỏa điều kiện cùng path và $elemMatch. Điều quan trọng là **cấu trúc đường dẫn Array**, không chỉ nhìn thấy hai field con có nhiều giá trị.

### 7.3. Unique multikey không thay cho unique trong từng mảng

Với unique multikey index, uniqueness được thực thi trên key giữa **các document khác nhau**. Những phần tử lặp trong một mảng của cùng document không tự khiến unique index báo lỗi vì lặp cùng index key trong document đó.

Ví dụ:

~~~javascript
{ _id: "p001", tags: ["sale", "sale"] }
~~~

Không thể dựa vào unique multikey index để bảo đảm một document không chứa tag trùng. Nếu nghiệp vụ muốn tags như một tập hợp, cần kiểm soát input và có thể dùng **$addToSet** khi thêm phần tử; xử lý dữ liệu cũ có trùng lặp vẫn là trách nhiệm riêng.

Unique multikey index trên tags còn có thể cấm **hai product khác nhau dùng chung một tag**, thường không phải yêu cầu của catalog. Không đặt unique: true chỉ với hy vọng loại trùng phần tử bên trong mỗi Array.

### 7.4. Những giới hạn thêm cần nhớ

- **Hashed index** không hỗ trợ multikey; đừng lập hashed index trực tiếp trên Array.
- **Shard key index** không được là multikey, dù một compound index có shard key ở phần tiền tố có thể có multikey field ở phần hậu tố không thuộc shard key.
- Multikey index có giới hạn riêng về **sort**, **covered query** và **index bounds**.
- Một query dùng **$expr** không thể kỳ vọng multikey index hỗ trợ theo cùng cách một predicate thông thường trên Array có thể sử dụng index.

## 8. Đọc explain để hiểu kế hoạch truy vấn

### 8.1. Những thông tin quan trọng

~~~javascript
db.getSiblingDB("mongo_multikey_lab")
  .getCollection("lab_products")
  .find({
    tenantId: "lab-shop",
    category: "tech",
    tags: "mongodb"
  })
  .hint("ix_tenant_category_tags")
  .explain("executionStats");
~~~

Tên và vị trí các stage có thể thay đổi giữa phiên bản/server query engine, nhưng các khái niệm thường cần đọc gồm:

| Thông tin | Ý nghĩa |
| --- | --- |
| **winningPlan** | Kế hoạch bộ tối ưu lựa chọn |
| **IXSCAN** | Đang đọc khóa từ index |
| **indexName** | Index được dùng trong stage |
| **isMultiKey** | Cho biết index trong stage là multikey |
| **multiKeyPaths** | Các đường dẫn làm index trở thành multikey, khi được trình bày |
| **indexBounds** | Phạm vi khóa được quét theo từng field của index |
| **FETCH** | Đọc document thật từ collection, ví dụ để kiểm tra điều kiện còn lại |
| **SORT** | Sắp xếp blocking khi chưa tận dụng đầy đủ thứ tự index |
| **COLLSCAN** | Quét collection |
| **totalKeysExamined** | Số khóa index đã được xem xét |
| **totalDocsExamined** | Số document đã được kiểm tra |
| **nReturned** | Số document trả về |

Do một document có thể có nhiều index key, **totalKeysExamined** cao hơn **nReturned** là điều có thể xảy ra tự nhiên trên multikey index. Muốn kết luận index tốt/xấu phải xét độ chọn lọc, số document FETCH, latency và tổng tài nguyên.

### 8.2. So sánh hai index cho cùng predicate

~~~javascript
const c = db.getSiblingDB("mongo_multikey_lab")
  .getCollection("lab_products");

const filter = {
  tenantId: "lab-shop",
  category: "tech",
  tags: "mongodb"
};

printjson(
  c.find(filter)
    .hint("ix_tenant_category_tags")
    .explain("executionStats")
);

printjson(
  c.find(filter)
    .hint("ix_tenant_category_price")
    .explain("executionStats")
);
~~~

Index thứ nhất chứa tags nên có cơ hội lọc theo tag bằng key. Index thứ hai hỗ trợ tenant/category/price nhưng **không chứa tags**, vì vậy có thể cần FETCH document để kiểm tra tag. Trong lab chỉ có sáu document, chênh lệch sẽ không đại diện cho một hệ thống nhiều triệu sản phẩm.

### 8.3. Multikey có thể cover query, nhưng có điều kiện

**Covered query** là truy vấn mà index có thể đáp ứng cả filter/projection mà không cần đọc document gốc. Multikey index vẫn có khả năng cover một số truy vấn nếu:

- Projection **không trả về Array field**.
- Query **không dùng $elemMatch**.
- Các trường cần cho filter/projection và các điều kiện covered query thông thường đều được đáp ứng, ví dụ loại _id khi index không chứa _id.

Ví dụ có khả năng được cover:

~~~javascript
c.find(
  {
    tenantId: "lab-shop",
    category: "tech",
    tags: "mongodb"
  },
  { _id: 0, category: 1 }
)
  .hint("ix_tenant_category_tags")
  .explain("executionStats");
~~~

Trái lại, nếu projection trả về **tags**, index multikey không thể cover hoàn toàn theo cùng điều kiện:

~~~javascript
c.find(
  {
    tenantId: "lab-shop",
    category: "tech",
    tags: "mongodb"
  },
  { _id: 0, tags: 1 }
)
  .hint("ix_tenant_category_tags")
  .explain("executionStats");
~~~

Chỉ có **IXSCAN** trong kế hoạch không có nghĩa truy vấn đã được cover; cần xem còn FETCH hay không.

### 8.4. Sort và field Array

Multikey index có các quy tắc đặc biệt khi sort. Trong một số trường hợp MongoDB phải dùng **SORT** dạng blocking, kể cả khi field được sort đã có index, do ranh giới của multikey field và các tiền tố đường dẫn không đáp ứng điều kiện sử dụng thứ tự index.

~~~javascript
c.find(
  { tenantId: "lab-shop", scores: { $gte: 80 } },
  { _id: 1, scores: 1 }
)
  .sort({ scores: 1 })
  .hint("ix_scores")
  .explain("executionStats");
~~~

Khi sort tăng dần trên Array, MongoDB dùng quy tắc chọn giá trị sort của mảng (thường là giá trị nhỏ nhất khi sort tăng dần). Điều kiện lọc không nhất thiết quyết định phần tử nào là khóa sort. Nếu nghiệp vụ cần **giá thấp nhất**, **điểm cao nhất** hoặc **ngày cập nhật mới nhất** của các phần tử, có thể cần một scalar field tổng hợp có ngữ nghĩa cụ thể.

## 9. Chi phí index, ghi đồng thời và thiết kế dữ liệu

### 9.1. Fan-out của mảng làm tăng chi phí

Một product có 2 tags khác với một product có 200 tags khác nhau. Với multikey index, càng nhiều giá trị riêng biệt trong mảng thì một document có thể đóng góp càng nhiều index key. Điều đó có thể làm tăng:

- Dung lượng index lưu trên đĩa và bộ nhớ cache cần cho index.
- Số key MongoDB cần duyệt trong truy vấn không đủ chọn lọc.
- Lượng cập nhật index khi thêm, xóa hoặc sửa phần tử.
- Thời gian ghi và khối lượng dữ liệu phải đồng bộ/backup trong hệ thống thực.

Không nên tính đơn giản số phần tử nhân một hằng số rồi coi đó là kích thước index thực tế; cấu trúc key, trùng lặp, nén và index compound còn ảnh hưởng dung lượng.

### 9.2. Update Array còn phải duy trì index

~~~javascript
db.getSiblingDB("mongo_multikey_lab")
  .getCollection("lab_products")
  .updateOne(
    { _id: "p001", dataset: "multikey-practice-v1" },
    { $addToSet: { tags: "performance" } }
  );
~~~

Lệnh trên thêm tag chưa tồn tại. Nếu tags được index, các key liên quan phải được duy trì tương ứng. $addToSet tránh thêm phần tử trùng mới theo semantics của thao tác, nhưng không tự dọn sạch phần tử trùng đã tồn tại trong mảng cũ.

~~~javascript
db.getSiblingDB("mongo_multikey_lab")
  .getCollection("lab_products")
  .updateOne(
    {
      _id: "p002",
      dataset: "multikey-practice-v1",
      "variants.color": "red"
    },
    { $inc: { "variants.$.stock": 1 } }
  );
~~~

Stock thuộc index trên variants, nên thay đổi này không chỉ sửa document mà còn có thể thay đổi các index key. Update một document là atomic trong phạm vi document; nếu ứng dụng cần bảo vệ tồn kho không âm hoặc tránh ghi trùng đơn, vẫn cần điều kiện nghiệp vụ và kiểm soát concurrency phù hợp.

### 9.3. Khi nào không nên nhúng một mảng rất lớn?

| Loại dữ liệu | Khi nhúng thường hợp lý | Khi nên cân nhắc tách collection |
| --- | --- | --- |
| Product tags | Ít phần tử, giới hạn rõ, đọc cùng product | Tập tags tăng rất lớn, thay đổi thường xuyên |
| Product variants | Số biến thể hữu hạn, đọc cùng product | Nhiều biến thể, cập nhật tồn kho độc lập với tần suất cao |
| Order line items | Số dòng hàng bị giới hạn theo nghiệp vụ | Đơn có thể có hàng nghìn/dài vô hạn dòng |
| Bình luận, events, logs | Số ít, vòng đời gắn với cha | Tăng liên tục, cần phân trang/tìm kiếm riêng |
| Danh sách liên kết ID | Ít giá trị và ít thay đổi | Có thể lên tới hàng triệu quan hệ |

Ngoài giới hạn 16 MiB, phải xem cả **đường đọc**, **đường ghi**, **tần suất cập nhật**, **vòng đời**, **số lượng phần tử** và **bộ index cần duy trì**. Một mảng dễ truy vấn bằng multikey index không mặc nhiên là lựa chọn tốt cho một quan hệ tăng vô hạn.

### 9.4. Index nên xuất phát từ access pattern

Giả sử ứng dụng có ba chức năng:

1. Tìm sản phẩm theo tenant/category/tag.
2. Tìm biến thể theo color và stock trong cùng một phần tử.
3. Sắp xếp sản phẩm theo tenant/category/price.

Ba index được tạo trong lab thể hiện ba nhu cầu đó. Không nhất thiết gộp tất cả vào một index; việc gộp **tags Array** và **variants Array** trong một compound index còn có thể gặp hạn chế parallel arrays. Nếu index không được query nào dùng, nó vẫn tốn chi phí bảo trì mỗi lần ghi.

## 10. Dọn dữ liệu và đọc lại cấu hình index

Để đưa dữ liệu về ban đầu sau khi update tags hoặc stock, chạy lại script seed ở mục 3. Các document có ID cố định, và các index có tên/định nghĩa ổn định. Có thể kiểm tra:

~~~javascript
const c = db.getSiblingDB("mongo_multikey_lab")
  .getCollection("lab_products");

print(c.countDocuments({ dataset: "multikey-practice-v1" }));
// 6 nếu vừa chạy seed.

printjson(c.getIndexes());
~~~

**getIndexes()** hiển thị định nghĩa index, nhưng để tìm thông tin **isMultiKey** và **multiKeyPaths** được sử dụng trong một query plan, cần xem explain của truy vấn tương ứng.

Khi kết thúc bài, chỉ xóa document có nhãn dữ liệu lab:

~~~javascript
db.getSiblingDB("mongo_multikey_lab")
  .getCollection("lab_products")
  .deleteMany({ dataset: "multikey-practice-v1" });
~~~

Không cần drop collection hoặc drop database để dọn dữ liệu; các index vẫn tồn tại nếu cần thực hành tiếp.

## 11. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Màu red hết hàng nhưng query vẫn trả sản phẩm | Hai điều kiện dotted path khớp hai phần tử khác nhau | Dùng $elemMatch trên variants |
| [65,95] khớp khoảng 80–90 | Range predicates có thể khớp phần tử khác nhau | Dùng $elemMatch để yêu cầu một phần tử nằm trong khoảng |
| Tạo index tags + regions thất bại | Hai Array độc lập bị index cùng trong compound index | Đổi index hoặc mô hình dữ liệu |
| IXSCAN vẫn có totalKeysExamined lớn | Một document có nhiều index key, index bounds chưa chọn lọc | Đọc isMultiKey, multiKeyPaths, indexBounds và kết quả FETCH |
| Query với $elemMatch vẫn phải FETCH | Multikey covered query có hạn chế với $elemMatch | Cân nhắc query/projection và chi phí đọc document |
| Index chứa tags nhưng projection tags không được cover | Array field được trả về | Chỉ kết luận covered khi explain không còn FETCH |
| Sort theo Array có SORT blocking | Quy tắc multikey bounds và sort không thỏa | Kiểm tra explain hoặc dùng scalar sort key |
| Unique multikey vẫn chấp nhận tag lặp trong một document | Uniqueness không có mục tiêu loại trùng phần tử nội bộ | Validate mảng và kiểm soát $addToSet |
| Truy vấn $size không nhanh chỉ nhờ index tags | Index lưu giá trị phần tử, không phải trực tiếp độ dài | Đánh giá có cần trường count riêng |
| Update Array làm tăng write latency | MongoDB phải duy trì thêm key index | Kiểm soát kích thước Array, số index và tần suất cập nhật |
| Lab 6 document dùng COLLSCAN | Dữ liệu quá nhỏ nên COLLSCAN có thể rẻ hơn IXSCAN | Đo trên tập dữ liệu và tải đại diện |

## 12. Bài tập tự thực hành

**Bài 1 — Vẽ multikey index.** Với p001.tags và p004.tags, hãy mô phỏng key của index trên tags và giải thích vì sao find({tags:"mongodb"}) trả document một lần, dù index có nhiều entry.

**Bài 2 — Sửa truy vấn màu đỏ còn hàng.** Viết hai truy vấn tìm color red và stock > 0, một truy vấn dotted path độc lập và một truy vấn $elemMatch. Ghi lại kết quả khác nhau và nêu rõ nguyên nhân p001.

**Bài 3 — Range bounds.** Dự đoán kết quả hai truy vấn scores >= 80 và <= 90, có/không có $elemMatch. Dùng hint("ix_scores") và explain("executionStats") để quan sát indexBounds.

**Bài 4 — Compound index.** Với tenantId, category, tags, variants và price, chọn index phù hợp cho tìm theo tag, tìm biến thể cùng phần tử và sort price. Giải thích tại sao compound index chứa hai Array độc lập không phù hợp.

**Bài 5 — Covered query.** So sánh projection chỉ lấy category với projection có tags khi dùng ix_tenant_category_tags. Xem FETCH và giải thích vì sao trả về Array làm mất khả năng cover.

**Bài 6 — Mảng tăng trưởng.** Nếu product chứa 10.000 tags khác nhau và thay đổi liên tục, hãy liệt kê chi phí multikey index và đề xuất ranh giới document/collection hợp lý hơn nếu các tag thực chất là quan hệ độc lập.

**Bài 7 — Đọc explain.** Với một truy vấn trên tags và một truy vấn trên variants, ghi lại indexName, indexBounds, isMultiKey, totalKeysExamined, totalDocsExamined, nReturned. Giải thích các số liệu dựa trên cấu trúc Array, tránh kết luận chỉ từ số đo trên sáu document.

## 13. Tài liệu MongoDB

- MongoDB Manual — [Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/).
- MongoDB Manual — [Multikey Index Bounds](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/multikey-index-bounds/).
- MongoDB Manual — [Create an Index on an Array Field](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/create-multikey-index-basic/).
- MongoDB Manual — [Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/).
- MongoDB Manual — [Query an Array of Embedded Documents](https://www.mongodb.com/docs/manual/tutorial/query-array-of-documents/).
- MongoDB Manual — [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/).

Khi làm việc với mảng, **multikey index giúp tìm theo phần tử** nhưng cũng làm tăng số key của một document. **$elemMatch** xác định điều kiện đúng trên cùng phần tử, ảnh hưởng trực tiếp đến **index bounds** và tập kết quả. **Compound multikey index** phải tuân theo cấu trúc Array path và giới hạn về mảng song song. Để quyết định index có phù hợp không, hãy đọc **explain** và cân nhắc đồng thời chi phí đọc, ghi, sắp xếp và sự tăng trưởng của mảng.
