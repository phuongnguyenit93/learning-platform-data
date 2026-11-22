# Chỉ mục cho trường lồng nhau hoặc phần tử collection

Trong NoSQL, một bản ghi không chỉ có các trường vô hướng như `id`, `name` hay `price`. Document có thể chứa **đối tượng lồng nhau**, **mảng các giá trị**, **mảng các đối tượng**; wide-column database có thể chứa `list`, `set` hoặc `map`; một công cụ tìm kiếm có thể lập chỉ mục từng phần tử trong một mảng tài liệu. Các cấu trúc này giúp mô hình hóa dữ liệu gần với nghiệp vụ, nhưng việc **đọc nhanh theo một trường con hoặc một phần tử trong collection** phải được thiết kế chủ động.

Ví dụ, một trang thương mại điện tử muốn trả lời:

- Những sản phẩm có `attributes.color = "black"`?
- Những sản phẩm có tag `"bluetooth"`?
- Những sản phẩm có **cùng một biến thể** vừa màu đen vừa còn ít nhất 3 món?
- Những đơn hàng có một dòng hàng mang SKU nhất định?
- Những tài liệu có ít nhất một địa chỉ giao hàng ở một thành phố?
- Những bản ghi có một khóa cụ thể trong `metadata`, trong khi tên khóa có thể thay đổi?

Chỉ mục cho cấu trúc lồng nhau có thể rút ngắn việc tìm kiếm, nhưng nó cũng dễ tạo **kết quả sai về ngữ nghĩa**, số lượng index entries lớn hoặc chi phí ghi cao nếu chưa hiểu cách database “trải” phần tử thành khóa chỉ mục.

Bài học thuộc chương **Chỉ mục và đường truy cập**, dùng MongoDB làm ví dụ chính cho dotted-path, multikey, `$elemMatch`, compound index và wildcard index; sau đó đối chiếu với DynamoDB, Cassandra/ScyllaDB, Elasticsearch/OpenSearch và Redis có module tìm kiếm. Các khả năng cụ thể phụ thuộc sản phẩm, phiên bản, cấu hình và topology; một cú pháp ở hệ này không tự áp dụng cho hệ khác.

## 1. “Trường lồng nhau” và “phần tử collection” là gì?

Cần phân biệt các cấu trúc thường gặp:

| Dạng dữ liệu | Ví dụ | Kiểu câu hỏi |
|---|---|---|
| Scalar field | `priceMinor: 2999` | Giá bằng/nằm trong khoảng |
| Embedded object | `attributes.color: "black"` | Tìm theo một trường con |
| Array scalar | `tags: ["mouse","wireless"]` | Có phần tử `"wireless"`? |
| Array object | `variants: [{sku,color,stock},...]` | Có **một** variant thỏa nhiều điều kiện? |
| Nested arrays | `groups: [{members:[...]}]` | Các phần tử ở nhiều cấp liên hệ ra sao? |
| Map/dictionary | `metadata: {"feature.bluetooth": true}` | Có khóa động/giá trị động? |
| Set/list trong wide-column | `labels set<text>` | Collection có chứa một giá trị? |
| Collection của document (cấp DB) | `products`, `orders` | Tìm bản ghi theo index của collection |

Từ “collection” trong bài chủ yếu nói về **tập phần tử lưu trong một trường** như array/list/set/map. Đây là khái niệm khác với **MongoDB collection**, vốn là tập các document. Một chỉ mục trên `products.tags` được định nghĩa trên collection `products` nhưng giá trị được đánh chỉ mục là các **phần tử trong mảng `tags`**.

### 1.1. Bản ghi mẫu

Dùng một sản phẩm với thông tin lồng nhau:

~~~javascript
{
  _id: "p100",
  tenantId: "t01",
  name: "Wireless Mouse",
  status: "ACTIVE",
  priceMinor: 2999,
  attributes: {
    color: "black",
    dimensions: {
      widthMm: 62,
      heightMm: 38
    },
    warrantyMonths: 24
  },
  tags: ["wireless", "mouse", "bluetooth"],
  variants: [
    { sku: "MOUSE-BLACK", color: "black", stock: 8 },
    { sku: "MOUSE-WHITE", color: "white", stock: 0 }
  ],
  metadata: {
    sellerRegion: "VN",
    energyRating: "A"
  }
}
~~~

Các kiểu truy vấn khác nhau dùng những index khác nhau. Chỉ mục trên `attributes.color` không đương nhiên giúp tìm `variants.color`. Chỉ mục trên `tags` không đương nhiên giúp query `tags.length` hoặc kiểm tra giao phức tạp giữa hai mảng.

## 2. Vì sao chỉ mục trên trường lồng nhau có ích?

Không có index phù hợp, database có thể phải đọc nhiều document rồi kiểm tra điều kiện trong từng bản ghi. Có index, engine có thể tìm các khóa đã được sắp xếp/tra cứu, lấy candidate documents rồi kiểm tra điều kiện còn lại.

Minh họa:

~~~text
Không có index:
  Query color="black"
       |
       v
  Đọc nhiều product documents
       |
       v
  Kiểm tra attributes.color từng document

Có index:
  Query color="black"
       |
       v
  Index key "black" -> document references
       |
       v
  Lấy document/các field cần thiết và xác minh điều kiện
~~~

Index là một **đường truy cập phụ**, không phải bản sao toàn bộ logic truy vấn. Một index có thể giảm documents examined nhưng vẫn cần FETCH để kiểm tra các điều kiện hoặc trả các field không có trong index. Với dữ liệu mảng, một document thường sinh **nhiều index entries**: điều này có lợi cho truy vấn membership nhưng làm tăng index size và chi phí cập nhật.

## 3. Chuẩn bị bộ dữ liệu MongoDB thực hành

Ví dụ dưới đây dành cho một database thử nghiệm riêng, không chạy các lệnh xóa/sửa diện rộng trên production.

~~~javascript
use nosql_nested_index_lab

db.products.insertMany([
  {
    _id: "p100",
    tenantId: "t01",
    name: "Wireless Mouse",
    status: "ACTIVE",
    priceMinor: 2999,
    attributes: {
      color: "black",
      dimensions: { widthMm: 62, heightMm: 38 }
    },
    tags: ["wireless", "mouse", "bluetooth"],
    variants: [
      { sku: "MOUSE-B", color: "black", stock: 8 },
      { sku: "MOUSE-W", color: "white", stock: 0 }
    ],
    metadata: { sellerRegion: "VN", energyRating: "A" }
  },
  {
    _id: "p101",
    tenantId: "t01",
    name: "Desk Lamp",
    status: "ACTIVE",
    priceMinor: 4599,
    attributes: {
      color: "white",
      dimensions: { widthMm: 140, heightMm: 360 }
    },
    tags: ["desk", "lamp"],
    variants: [
      { sku: "LAMP-B", color: "black", stock: 0 },
      { sku: "LAMP-W", color: "white", stock: 5 }
    ],
    metadata: { sellerRegion: "SG", energyRating: "B" }
  },
  {
    _id: "p102",
    tenantId: "t02",
    name: "Travel Keyboard",
    status: "INACTIVE",
    priceMinor: 7999,
    attributes: {
      color: "black",
      dimensions: { widthMm: 280, heightMm: 20 }
    },
    tags: ["wireless", "keyboard"],
    variants: [
      { sku: "KEY-B", color: "black", stock: 3 }
    ],
    metadata: { sellerRegion: "VN" }
  }
]);
~~~

Ở các phần tiếp theo, `tenantId` đại diện ranh giới nghiệp vụ: ứng dụng phải xác thực tenant và áp giới hạn đúng ở mọi query. Index không phải cơ chế phân quyền; một query thiếu tenant vẫn có thể trả bản ghi không được phép nếu ứng dụng thiếu kiểm tra.

## 4. Index trên field lồng nhau bằng dotted path

MongoDB cho phép tạo index trên field con bằng **dot notation**:

~~~javascript
db.products.createIndex(
  { "attributes.color": 1 },
  { name: "ix_attributes_color" }
);
~~~

Truy vấn tương ứng:

~~~javascript
db.products.find(
  { "attributes.color": "black" },
  { name: 1, "attributes.color": 1 }
);
~~~

Dấu chấm trong `"attributes.color"` có nghĩa đi vào object `attributes` để lấy field `color` theo đường dẫn. Nó khác việc lập chỉ mục cả object `attributes`.

### 4.1. Index cả embedded object khác index field con

MongoDB có thể tạo index theo một embedded document với ngữ nghĩa so sánh object, nhưng:

~~~javascript
db.products.createIndex({ attributes: 1 });
~~~

không nên được xem là thay thế phổ quát cho:

~~~javascript
db.products.createIndex({ "attributes.color": 1 });
~~~

Khi ứng dụng chủ yếu lọc theo màu, index theo **field path** thường khớp đường truy cập hơn. So sánh cả object có thể phụ thuộc cấu trúc và thứ tự field của embedded document; ứng dụng không nên dựa vào equality trên toàn object nếu chỉ có nhu cầu đọc một trường con.

### 4.2. Index trên nhiều cấp lồng nhau

~~~javascript
db.products.createIndex({
  "attributes.dimensions.widthMm": 1
});

db.products.find({
  "attributes.dimensions.widthMm": { $gte: 100 }
});
~~~

Cách suy nghĩ: chọn một **đường truy cập ổn định từ root document đến giá trị cần lọc**. Nếu thường xuyên query theo chiều rộng và tenant, index ghép có thể phù hợp hơn hai index đơn rời rạc.

## 5. Index ghép trên tenant và field lồng nhau

Trong hệ đa tenant, phần lớn query có dạng:

~~~javascript
db.products.find({
  tenantId: "t01",
  status: "ACTIVE",
  "attributes.color": "black"
});
~~~

Một index theo pattern truy cập:

~~~javascript
db.products.createIndex(
  {
    tenantId: 1,
    status: 1,
    "attributes.color": 1
  },
  { name: "ix_tenant_status_color" }
);
~~~

Đọc ý nghĩa của khóa index:

~~~text
tenantId → status → attributes.color → document reference
~~~

Điều kiện equality trên `tenantId` và `status` thu hẹp phạm vi trước khi tìm màu. Tuy nhiên, không có quy tắc rằng cứ đặt nhiều field nhất vào compound index là tốt nhất. Thứ tự field phải dựa trên query thường dùng, equality/range/sort, độ chọn lọc, khả năng dùng prefix, kích thước index và chi phí ghi.

Một index theo `tenantId, status, attributes.color` phù hợp với filter trên cả ba trường, nhưng có thể không hiệu quả cho query chỉ dùng `attributes.color` mà không có tenant. Nếu ứng dụng không cho phép truy vấn xuyên tenant thì đây có thể là đánh đổi hợp lý.

## 6. Index cho phần tử mảng: multikey index

Một document có thể chứa:

~~~json
{
  "_id": "p100",
  "tags": ["wireless", "mouse", "bluetooth"]
}
~~~

Khi tạo index:

~~~javascript
db.products.createIndex(
  { tags: 1 },
  { name: "ix_tags" }
);
~~~

MongoDB tự coi index là **multikey index** khi field được index chứa array. Mỗi phần tử của mảng có thể tham gia vào các index entries dùng để định vị document.

Sơ đồ khái niệm:

~~~text
Document p100:
  tags = [wireless, mouse, bluetooth]

Multikey index:
  bluetooth  -> p100
  mouse      -> p100
  wireless   -> p100

Document p102:
  tags = [wireless, keyboard]

Multikey index:
  keyboard   -> p102
  wireless   -> p102
~~~

Đây là mô hình tư duy, không phải bản mô tả byte-level của B-tree hay mọi quy tắc loại trùng entry. Điểm cốt lõi: **một document có thể tạo nhiều khóa index** khi trường là mảng.

Truy vấn membership:

~~~javascript
db.products.find({
  tags: "wireless"
});
~~~

Query này chọn các document có mảng `tags` chứa giá trị `"wireless"`. Index trên `tags` có thể giúp định vị nhanh hơn việc quét toàn bộ collection, tùy selectivity và query plan.

## 7. Các truy vấn mảng: equality, $in, $all và $elemMatch

Các biểu thức tưởng giống nhau có thể trả tập kết quả khác nhau:

~~~javascript
// Có ít nhất một tag bằng "wireless".
db.products.find({ tags: "wireless" });

// Có ít nhất một tag trong danh sách.
db.products.find({
  tags: { $in: ["wireless", "bluetooth"] }
});

// Có đủ cả hai tag, không cần nằm ở một vị trí cố định.
db.products.find({
  tags: { $all: ["wireless", "bluetooth"] }
});

// Có một phần tử tag thỏa các điều kiện trong cùng elemMatch.
db.products.find({
  tags: {
    $elemMatch: {
      $regex: "^wire",
      $options: "i"
    }
  }
});
~~~

Với array scalar, `$elemMatch` đặc biệt hữu ích khi cần một phần tử đồng thời thỏa nhiều điều kiện; với query regex, hiệu quả sử dụng index còn phụ thuộc mẫu regex, collation và dữ liệu. Không suy từ “đã tạo index” rằng mọi regex sẽ nhanh.

### 7.1. $all không có nghĩa cùng một phần tử

`$all` kiểm tra tập giá trị cần xuất hiện trong array. Nó không có nghĩa một phần tử đồng thời mang nhiều thuộc tính. Với array object, nếu các điều kiện phải cùng thuộc **một object con**, cần `$elemMatch` như phần sau.

### 7.2. Phân biệt thành viên array và toàn bộ array

Ví dụ:

~~~javascript
// Phần tử "wireless" thuộc mảng.
db.products.find({ tags: "wireless" });

// Document có toàn bộ mảng bằng đúng thứ tự/giá trị cho trước.
db.products.find({
  tags: ["wireless", "mouse", "bluetooth"]
});
~~~

Hai truy vấn có ý nghĩa khác nhau. Index multikey trên `tags` tối ưu nhiều dạng membership; equality của cả array có thể vẫn phải FETCH document để kiểm tra cấu trúc/thứ tự, không chỉ dựa vào một entry.

## 8. Mảng object và lỗi “khớp nhầm hai phần tử”

Đây là điểm quan trọng nhất của bài.

Sản phẩm `p101` có hai biến thể:

~~~javascript
variants: [
  { sku: "LAMP-B", color: "black", stock: 0 },
  { sku: "LAMP-W", color: "white", stock: 5 }
]
~~~

Nghiệp vụ: tìm sản phẩm có **một biến thể màu đen còn ít nhất 3 chiếc**.

Nếu dùng hai dotted conditions độc lập:

~~~javascript
db.products.find({
  "variants.color": "black",
  "variants.stock": { $gte: 3 }
});
~~~

thì `p101` có thể được chọn: phần tử thứ nhất có color black, phần tử thứ hai có stock 5. Không có **một** biến thể nào thỏa cả hai. Kết quả sai nếu trang bán hàng hiểu rằng biến thể đen còn hàng.

Câu query đúng ý định:

~~~javascript
db.products.find({
  variants: {
    $elemMatch: {
      color: "black",
      stock: { $gte: 3 }
    }
  }
});
~~~

`$elemMatch` gắn các điều kiện vào **cùng một phần tử mảng object**.

| Query | p100 | p101 | p102 |
|---|---|---|---|
| Color black ở một phần tử, stock ≥3 ở một phần tử bất kỳ | Có | Có | Có |
| Cùng một variant color black **và** stock ≥3 | Có | Không | Có |

Với ứng dụng đa tenant đang đọc dữ liệu của `t01`, cần thêm `tenantId: "t01"`; khi đó `p102` thuộc `t02` không phải kết quả được phép.

## 9. Tạo multikey index trên thuộc tính trong array object

Để tìm variant theo màu:

~~~javascript
db.products.createIndex(
  { "variants.color": 1 },
  { name: "ix_variant_color" }
);
~~~

Để truy vấn theo cả màu và stock:

~~~javascript
db.products.createIndex(
  {
    "variants.color": 1,
    "variants.stock": 1
  },
  { name: "ix_variant_color_stock" }
);
~~~

Vì các giá trị nằm trong mảng `variants`, index có thể trở thành compound multikey. Dùng `$elemMatch` với điều kiện cùng phần tử không chỉ giúp đúng nghiệp vụ, mà trong các trường hợp thích hợp còn giúp planner **kết hợp index bounds** cho những trường xuất phát từ cùng đường array.

Ví dụ:

~~~javascript
db.products.find({
  variants: {
    $elemMatch: {
      color: "black",
      stock: { $gte: 3 }
    }
  }
}).explain("executionStats");
~~~

Khi xem explain, cần kiểm tra index nào được chọn, tổng keys/docs examined và giai đoạn FETCH. Không chỉ nhìn vào tên index rồi kết luận mọi điều kiện đã được thực thi hoàn toàn trong index.

### 9.1. Compound multikey có ràng buộc quan trọng

MongoDB có hạn chế đối với **nhiều trường array độc lập trong cùng một compound multikey index**. Ví dụ một document chứa cả:

~~~javascript
{
  tags: ["wireless", "mouse"],
  regions: ["VN", "SG"]
}
~~~

Không được mặc định có thể tạo và duy trì index ghép `{tags:1, regions:1}` khi cả hai đều là array trong cùng một document. Các phiên bản MongoDB áp dụng ràng buộc compound multikey liên quan đến số đường array; cần xem quy tắc cụ thể trước khi thiết kế. Ngược lại, nhiều field con xuất phát từ **cùng array of objects** như `variants.color` và `variants.stock` là một trường hợp khác cần đánh giá bằng index/explain thực tế.

Không thể tối ưu mọi bộ lọc “có tag X và region Y” chỉ bằng cách cộng tất cả array fields vào một compound index. Có thể phải chọn một index dẫn đường, đổi mô hình dữ liệu hoặc materialize projection chuyên cho truy vấn phổ biến.

## 10. Bảo toàn quan hệ giữa các field con trong một phần tử

Xét đơn hàng:

~~~javascript
{
  _id: "o500",
  tenantId: "t01",
  items: [
    { sku: "SKU-A", quantity: 1, unitPriceMinor: 2999 },
    { sku: "SKU-B", quantity: 5, unitPriceMinor: 499 }
  ]
}
~~~

Yêu cầu: tìm Order có một dòng hàng SKU-A với quantity ít nhất 3.

Sai về ngữ nghĩa:

~~~javascript
db.orders.find({
  "items.sku": "SKU-A",
  "items.quantity": { $gte: 3 }
});
~~~

Nó có thể khớp `o500` vì SKU-A thuộc phần tử thứ nhất, quantity 5 thuộc phần tử thứ hai.

Đúng:

~~~javascript
db.orders.find({
  tenantId: "t01",
  items: {
    $elemMatch: {
      sku: "SKU-A",
      quantity: { $gte: 3 }
    }
  }
});
~~~

Index gợi ý nếu đây là access pattern thường gặp:

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    "items.sku": 1,
    "items.quantity": 1
  },
  { name: "ix_tenant_item_sku_quantity" }
);
~~~

Lưu ý: kết quả `$elemMatch` đúng không đồng nghĩa mọi điều kiện được giải quyết hoàn toàn trong index. Khi cần trả chi tiết dòng hàng, database có thể còn phải lấy document gốc.

## 11. Array scalar có nhiều điều kiện range

Một document có:

~~~javascript
{
  _id: "sensor-1",
  measurements: [2, 9, 20]
}
~~~

Muốn một **giá trị đo duy nhất** nằm trong khoảng từ 5 đến 10:

~~~javascript
db.sensors.find({
  measurements: {
    $elemMatch: {
      $gte: 5,
      $lte: 10
    }
  }
});
~~~

Nếu chỉ viết:

~~~javascript
db.sensors.find({
  measurements: {
    $gte: 5,
    $lte: 10
  }
});
~~~

trên field array, các điều kiện có thể được đáp ứng bởi các phần tử khác nhau: 20 đáp ứng `>=5`, còn 2 đáp ứng `<=10`, mặc dù ví dụ này cũng có 9. Trong dữ liệu khác như `[2,20]`, query thiếu `$elemMatch` vẫn có nguy cơ khớp khi không có phần tử nào trong [5,10].

Một multikey index trên `measurements` có thể dùng cho range membership; với `$elemMatch`, planner có thêm thông tin để kết hợp bounds tương ứng. Đây là lý do **đúng ngữ nghĩa và index strategy phải được xem cùng nhau**.

## 12. Unique multikey index không bảo đảm phần tử trong một document là duy nhất

Giả sử muốn không có hai sản phẩm chia sẻ cùng mã variant giữa các product documents:

~~~javascript
db.products.createIndex(
  { "variants.sku": 1 },
  { unique: true, name: "uq_variant_sku" }
);
~~~

Với những điều kiện hợp lệ của index, unique multikey có thể ngăn **hai document khác nhau** tạo cùng indexed key. Nhưng không được hiểu nó tự bảo vệ mọi trường hợp hai phần tử trùng SKU **trong cùng một document**. Trong MongoDB, tính duy nhất của multikey index không tự trở thành một unique constraint giữa các phần tử của cùng document.

Ví dụ một product có:

~~~javascript
variants: [
  { sku: "MOUSE-B", color: "black" },
  { sku: "MOUSE-B", color: "black" }
]
~~~

Cần kiểm tra bằng application validation, document schema validation thích hợp hoặc một mô hình chuyển variant thành thực thể có khóa riêng. Nếu tính duy nhất của mỗi variant là bất biến quan trọng, hãy định nghĩa cách bảo vệ nó trong thao tác cập nhật nguyên tử, không chỉ hy vọng vào unique multikey index.

Ngoài ra, một unique index chỉ trên `variants.sku` áp quy tắc toàn collection, chưa chắc phù hợp nếu SKU chỉ duy nhất **trong tenant**. Khi đó cần xét index chứa `tenantId` và tương tác với multikey theo mô hình dữ liệu thực.

## 13. Partial index cho trường lồng nhau

Nếu chỉ tra cứu sản phẩm ACTIVE, có thể giảm index entries bằng một **partial index**:

~~~javascript
db.products.createIndex(
  {
    tenantId: 1,
    "attributes.color": 1
  },
  {
    name: "ix_active_color",
    partialFilterExpression: {
      status: "ACTIVE"
    }
  }
);
~~~

Index chỉ chứa những document phù hợp điều kiện partial filter. Query nên diễn đạt điều kiện đó:

~~~javascript
db.products.find({
  tenantId: "t01",
  status: "ACTIVE",
  "attributes.color": "black"
});
~~~

Với query không có `status:"ACTIVE"`, planner không thể tùy tiện dùng partial index nếu làm thiếu kết quả cần trả. Điều kiện query phải đủ để bảo đảm không bỏ sót document ngoài phạm vi index.

Khi document chuyển ACTIVE → INACTIVE hoặc ngược lại, các index entries cần được thêm/xóa tương ứng. Partial index giúp một số workload đọc/ghi nhưng cũng đòi hỏi người thiết kế hiểu **trạng thái nào được phép có mặt trong kết quả**.

### 13.1. Partial index khác sparse index

**Sparse index** tập trung vào sự hiện diện của field và có quy tắc riêng với missing/null. **Partial index** dùng biểu thức lọc linh hoạt hơn để quyết định document nào được index. Hai loại không hoàn toàn tương đương, đặc biệt khi cần xử lý null, trạng thái ACTIVE, array fields và unique constraints.

Không dùng `sparse` để suy ra “bỏ mọi null” nếu chưa đọc đúng semantics sản phẩm. Nên viết fixture gồm missing, explicit null, empty array và array có giá trị, rồi xác nhận query/index behavior.

## 14. Wildcard index cho schema động

Một số ứng dụng cho phép thuộc tính sản phẩm khác nhau theo danh mục:

~~~javascript
{
  _id: "p300",
  tenantId: "t01",
  attributes: {
    screenSizeInch: 14,
    memoryGb: 16,
    keyboardLayout: "US"
  }
}

{
  _id: "p301",
  tenantId: "t01",
  attributes: {
    material: "cotton",
    size: "M",
    organic: true
  }
}
~~~

Nếu tên field được người dùng hoặc danh mục sản phẩm mở rộng thường xuyên, tạo index riêng cho mọi `attributes.X` có thể không thực tế. MongoDB hỗ trợ dạng **wildcard index**:

~~~javascript
db.products.createIndex(
  { "attributes.$**": 1 },
  { name: "ix_attributes_wildcard" }
);
~~~

Nó có thể giúp truy vấn theo nhiều đường dẫn trong subtree `attributes` mà chưa cần tạo một index B-tree riêng cho từng path.

Ví dụ:

~~~javascript
db.products.find({
  "attributes.memoryGb": { $gte: 16 }
});

db.products.find({
  "attributes.material": "cotton"
});
~~~

**Đánh đổi:** wildcard index có thể lớn, đặc biệt khi document có nhiều field động hoặc mảng. Nó cũng không nhất thiết hỗ trợ tốt mọi kiểu compound filter, sort, coverage hoặc workload nhiều điều kiện như các index được thiết kế rõ cho đường truy cập quan trọng.

Khi một thuộc tính đã trở thành filter phổ biến, đo index/query plan và cân nhắc index chuyên biệt thay vì mặc định wildcard giải quyết mọi thứ.

## 15. Dynamic keys trong map: giữ đúng sự khác biệt giữa key và value

Trong NoSQL, map có thể là:

~~~javascript
metadata: {
  sellerRegion: "VN",
  energyRating: "A",
  stockSource: "warehouse"
}
~~~

Nếu tên key ổn định, index trực tiếp `metadata.sellerRegion` thường rõ nhất. Nếu key động thực sự, wildcard hoặc một mô hình key–value khác có thể phù hợp.

Tuy nhiên, một string key chứa dấu chấm hoặc ký tự đặc biệt có thể khó phân biệt với dot-path trong câu query, tùy hệ và phiên bản. Không nên dựa vào truy cập dotted path khi tên key là do người dùng tự nhập và có thể chứa dấu chấm. Trong MongoDB có các cơ chế truy cập field literal chuyên biệt ở những phiên bản thích hợp; phải xem tài liệu đúng phiên bản hoặc chuẩn hóa tên key trước khi ghi.

Với trường hợp cần tìm mọi record có cặp key/value tùy ý, một projection **thuộc tính thành hàng riêng** có thể là lựa chọn:

~~~text
product_attribute_index
  (tenantId=t01, key=material, value=cotton) -> productId p301
  (tenantId=t01, key=memoryGb, value=16) -> productId p300
~~~

Đó là mô hình **inverted index do ứng dụng quản lý**, đổi lại phải cập nhật/rebuild projection khi attributes của product thay đổi.

## 16. Nested object và embedded collection: nên index trường nào?

Có thể chọn theo câu hỏi nghiệp vụ thay vì “mỗi field một index”.

| Query | Index gợi ý để bắt đầu đo | Lưu ý |
|---|---|---|
| Product theo tenant, color | `tenantId, attributes.color` | Equality và selectivity |
| Product có tag `bluetooth` | `tenantId, tags` | Multikey; tag quá phổ biến có thể ít chọn lọc |
| Product có variant SKU | `tenantId, variants.sku` | Array object, index entries tăng theo variants |
| Product có một variant black stock≥3 | `tenantId, variants.color, variants.stock` | `$elemMatch` để giữ same-element semantics |
| Order chứa SKU-A | `tenantId, items.sku` | Trả order, có thể cần FETCH |
| Product có thuộc tính động bất kỳ | `attributes.$**` | Theo dõi index size và query mix |
| Product ACTIVE có màu X | Partial index `tenantId,color` cho ACTIVE | Chỉ dùng an toàn khi query bao hàm điều kiện partial |
| Sort theo giá sau lọc thuộc tính | Index ghép theo access pattern thực | Sort/index behavior phải đo, nhất là với multikey |

Không có index duy nhất thắng mọi query. Tạo nhiều index gần giống nhau làm tăng storage, bộ nhớ, write amplification và thời gian xây dựng/rebuild. Nên xác định các đường đọc quan trọng, đo rồi mới mở rộng.

## 17. Selectivity và độ lớn mảng

Một index chỉ giúp tốt khi nó giảm lượng dữ liệu cần xử lý hoặc hỗ trợ sort. Nếu gần như mọi product đều có tag `"sale"`, index trên `tags` có thể trả quá nhiều document references, đôi khi planner chọn scan phù hợp hơn.

Ngược lại, tag hiếm như `"braille-keyboard"` có thể chọn rất ít document.

Ví dụ giả định:

| Thuộc tính | Tỷ lệ document có giá trị | Ý nghĩa |
|---|---:|---|
| `tags: "sale"` | 85% | Index membership ít chọn lọc |
| `tags: "bluetooth"` | 15% | Có thể có ích |
| `tags: "rare-feature"` | 0,01% | Rất chọn lọc |
| `attributes.color: "black"` | 35% | Có thể cần kết hợp tenant/status |
| `variants.sku: "MOUSE-B"` | Gần 1 product | Lookup tương đối đặc hiệu |

Đây là số liệu minh họa; phải đo phân bố thực. Với array dài, **fan-out index entries** tăng: document có 3 tags tạo đường index khác document có 5.000 tags. Điều này ảnh hưởng chi phí cập nhật, insert, storage và đôi khi cả giới hạn document/index key của engine.

Một mô hình ước lượng thô:

\[
\text{Index entries} \approx \sum_{d \in \text{documents}} \text{số giá trị được index của }d
\]

Công thức chỉ để hiểu chiều tăng trưởng: index thực có quy tắc loại trùng, sparse/partial, cách mã hóa và overhead riêng. Không thể dùng nó để dự đoán chính xác byte storage.

## 18. Compound multikey, sort và giới hạn coverage

Một query có thể lọc tags rồi sort theo giá:

~~~javascript
db.products.find({
  tenantId: "t01",
  tags: "wireless"
}).sort({
  priceMinor: 1,
  _id: 1
}).limit(20);
~~~

Index tiềm năng:

~~~javascript
db.products.createIndex(
  {
    tenantId: 1,
    tags: 1,
    priceMinor: 1,
    _id: 1
  },
  { name: "ix_tenant_tag_price" }
);
~~~

Nhưng không mặc định index này luôn loại được mọi bước sort hoặc cho phép covered query. Với multikey, khả năng dùng index để sort và cover projection có những hạn chế, đặc biệt khi query/projection truy cập field array và khi cần điều kiện `$elemMatch`.

Những câu hỏi cần kiểm tra qua explain:

1. Planner chọn `IXSCAN` nào?
2. Có bước `FETCH` để kiểm tra document gốc không?
3. Có bước sort riêng tiêu thụ bộ nhớ không?
4. Có nhiều keys examined so với documents returned không?
5. Index bounds có kết hợp các điều kiện cùng phần tử đúng cách không?
6. Index còn có ích khi tag rất phổ biến không?

Mục tiêu là **trả đúng kết quả với chi phí chấp nhận được**, không phải ép mọi query phải là index-only.

## 19. Index intersection không thay thế thiết kế query

Giả sử có hai index đơn:

~~~javascript
db.products.createIndex({ tenantId: 1 });
db.products.createIndex({ tags: 1 });
~~~

Engine có thể có khả năng xem xét nhiều đường truy cập, kể cả kết hợp chỉ mục trong một số tình huống; nhưng không nên giả định nó luôn intersect hai index hiệu quả hơn index ghép:

~~~javascript
db.products.createIndex({ tenantId: 1, tags: 1 });
~~~

Tương tự, có index riêng trên `variants.color` và `variants.stock` không chứng minh query được tối ưu theo **cùng một phần tử**. Vấn đề đúng–sai do `$elemMatch` giải quyết ở semantics; vấn đề chi phí do compound bounds, index plan và phân bố dữ liệu quyết định.

## 20. Cập nhật mảng khiến chi phí index tăng thế nào?

Khi thêm/xóa một phần tử trong mảng đã index, database phải bảo đảm những giá trị có thể tìm được bằng index phản ánh trạng thái mới của document.

Ví dụ:

~~~javascript
db.products.updateOne(
  { _id: "p100", tenantId: "t01" },
  { $addToSet: { tags: "ergonomic" } }
);

db.products.updateOne(
  { _id: "p100", tenantId: "t01" },
  { $pull: { tags: "mouse" } }
);
~~~

Index trên `tags` cần được duy trì khi dữ liệu thay đổi. Nếu index có `tenantId, tags, status`, khi đổi `status` cũng có thể phải cập nhật các index entries liên quan.

Với array of objects:

~~~javascript
db.products.updateOne(
  { _id: "p100", tenantId: "t01" },
  {
    $set: { "variants.$[v].stock": 7 }
  },
  {
    arrayFilters: [
      { "v.sku": "MOUSE-B" }
    ]
  }
);
~~~

Các field được index như `variants.stock` hoặc compound multikey cần phản ánh cập nhật. Một product chứa hàng nghìn variants có thể tạo hot document và khối lượng index maintenance đáng kể. Đừng nhúng mảng không giới hạn như lịch sử mọi lượt click của người dùng vào một document rồi tạo nhiều multikey indexes.

### 20.1. Ranh giới aggregate và mô hình tách collection

Nếu mỗi Product chỉ có 2–10 variants, embed có thể hợp lý để đọc toàn bộ sản phẩm trong một lần. Nếu mỗi Product có hàng trăm nghìn offers/availability records, việc tách sang collection riêng như `product_variants` có thể giúp:

- Index theo `tenantId, sku, stock` phù hợp hơn.
- Update một variant độc lập thay vì tranh cùng document cha.
- Phân trang và giới hạn dữ liệu theo từng phần tử.
- Quản lý vòng đời/index của variants riêng.

Đánh đổi: đọc toàn bộ product + variants có thể cần hai query/aggregation; bất biến xuyên Product–Variant có thể cần transaction hoặc workflow nhất quán. Không nên tách chỉ vì muốn index; cần cân nhắc **đường ghi, ranh giới nguyên tử và truy vấn phổ biến**.

## 21. Chỉ mục với arrays lồng nhiều tầng

Ví dụ:

~~~javascript
{
  _id: "course-1",
  groups: [
    {
      groupId: "g1",
      members: [
        { userId: "u1", role: "mentor" },
        { userId: "u2", role: "learner" }
      ]
    },
    {
      groupId: "g2",
      members: [
        { userId: "u3", role: "mentor" }
      ]
    }
  ]
}
~~~

Câu hỏi “có userId u2 ở một nhóm bất kỳ không?” khác câu hỏi “**group g1** có userId u2 với role learner không?”. Với các array lồng nhau, cần đặt `$elemMatch` ở đúng cấp để ràng buộc các điều kiện thuộc **cùng group** và **cùng member**.

Một truy vấn minh họa:

~~~javascript
db.courses.find({
  groups: {
    $elemMatch: {
      groupId: "g1",
      members: {
        $elemMatch: {
          userId: "u2",
          role: "learner"
        }
      }
    }
  }
});
~~~

Index trên đường như `groups.members.userId` có thể tồn tại trong những điều kiện và phiên bản phù hợp, nhưng càng nhiều tầng array, càng cần kiểm tra giới hạn multikey, index bounds và query plan. Không được giả định mọi cách kết hợp điều kiện across nested arrays đều được một compound index đáp ứng trực tiếp.

Nếu nghiệp vụ thường query thành viên của nhóm độc lập, một model collection riêng `group_memberships` với key `(courseId,groupId,userId)` có thể cho access pattern đơn giản hơn và uniqueness rõ hơn.

## 22. DynamoDB: nested attribute không mặc nhiên trở thành index key

DynamoDB hỗ trợ item chứa Map và List. Nhưng primary key và **GSI/LSI key attributes** có những ràng buộc về kiểu/định nghĩa khác với việc lập chỉ mục tự động trên mọi nested path như MongoDB.

Ví dụ item:

~~~json
{
  "PK": "TENANT#t01",
  "SK": "PRODUCT#p100",
  "attributes": {
    "color": "black",
    "warrantyMonths": 24
  },
  "tags": ["wireless", "mouse"]
}
~~~

Nếu access pattern là “lấy product p100 theo tenant”, key chính phục vụ tốt. Nếu là “tìm mọi product màu đen trong tenant”, việc có `attributes.color` trong Map **không tự tạo index theo màu**.

Một `FilterExpression` có thể lọc item sau khi đọc qua một Query/Scan, nhưng không làm các item không phù hợp biến mất khỏi chi phí đọc trước filter. Không nên nhầm filter trên List/Map với index lookup.

### 22.1. Materialize field cần index ra scalar key

Một phương án:

~~~json
{
  "PK": "TENANT#t01",
  "SK": "PRODUCT#p100",
  "attributes": {
    "color": "black"
  },
  "colorLookup": "TENANT#t01#COLOR#black",
  "productId": "p100"
}
~~~

Đặt scalar field phục vụ GSI nếu schema và yêu cầu phù hợp. GSI cần được thiết kế theo key access pattern cụ thể, có chi phí write/storage và độ mới khác bảng chính; không coi filter tùy ý trên Map là GSI traversal.

### 22.2. Membership nhiều giá trị: inverted-index items

Để tìm mọi product có tag `"wireless"`, có thể tạo các item lookup riêng:

~~~text
PK=TAG#t01#wireless   SK=PRODUCT#p100
PK=TAG#t01#mouse      SK=PRODUCT#p100
PK=TAG#t01#wireless   SK=PRODUCT#p102
~~~

Query theo partition key tag trả danh sách product IDs, sau đó đọc product detail. Cần xử lý thêm/xóa tag, eventual consistency, idempotency và phục hồi projection. Bài toán này gần với một **inverted index do ứng dụng quản lý**, không phải tự động index nested List.

## 23. Cassandra/ScyllaDB: collection types và đường truy cập

Cassandra hỗ trợ các kiểu collection như `list`, `set`, `map` trong những phạm vi và điều kiện cụ thể. Ví dụ khái niệm:

~~~sql
CREATE TABLE products_by_id (
  tenant_id text,
  product_id text,
  name text,
  tags set<text>,
  attributes map<text, text>,
  PRIMARY KEY ((tenant_id), product_id)
);
~~~

Đường đọc hiệu quả tự nhiên là biết `tenant_id` và `product_id`:

~~~sql
SELECT name, tags, attributes
FROM products_by_id
WHERE tenant_id = 't01'
  AND product_id = 'p100';
~~~

Nếu muốn “tìm mọi product có tag wireless”, phải kiểm tra **cơ chế index collection** được engine, phiên bản và cấu hình hỗ trợ (ví dụ secondary index hoặc Storage-Attached Indexing trong những hệ phù hợp). Các biểu thức như `CONTAINS` và `CONTAINS KEY` có semantics theo CQL nhưng không đồng nghĩa mọi bảng đều có đường đọc tối ưu không cần index.

Một mẫu CQL minh họa ý nghĩa điều kiện collection:

~~~sql
-- Truy vấn chỉ thích hợp khi schema/index và phiên bản hỗ trợ.
SELECT product_id, name
FROM products_by_id
WHERE tags CONTAINS 'wireless';
~~~

Không nên triển khai câu này trên bảng sản lượng lớn trước khi xác nhận index, partitioning và query plan. Với truy vấn tag là lõi nghiệp vụ, một bảng query-first có thể rõ ràng hơn:

~~~sql
CREATE TABLE products_by_tag (
  tenant_id text,
  tag text,
  product_id text,
  name text,
  PRIMARY KEY ((tenant_id, tag), product_id)
);
~~~

Khi có tag `wireless`, query đi thẳng vào partition `(tenantId,tag)`. Đánh đổi là **ghi nhiều bản** khi product có nhiều tags và giữ bảng phụ đồng bộ, kể cả xóa tag hoặc đổi product status.

### 23.1. Không biến một collection thành tập vô hạn

Trong Cassandra, một collection lớn và liên tục thay đổi có thể gây chi phí đọc/ghi, tombstone và phân vùng quá lớn. Dù hệ hỗ trợ index membership, không có nghĩa nên lưu hàng triệu phần tử trong một cell/row. Tách bảng theo item hoặc chọn partition key phù hợp có thể là mô hình bền vững hơn.

## 24. Elasticsearch/OpenSearch: object array khác nested array

Một công cụ tìm kiếm lập chỉ mục JSON có thể **flatten object arrays** theo cách làm mất mối quan hệ “cùng phần tử” nếu mapping là dạng `object` thông thường.

Ví dụ tài liệu:

~~~json
{
  "productId": "p101",
  "variants": [
    {"color": "black", "stock": 0},
    {"color": "white", "stock": 5}
  ]
}
~~~

Một truy vấn độc lập `variants.color=black` và `variants.stock>=3` có nguy cơ khớp tài liệu này nếu engine không giữ ranh giới mỗi object con.

Với Elasticsearch/OpenSearch, kiểu mapping **nested** có thể bảo toàn ranh giới các object phần tử và cho phép nested query:

~~~json
{
  "mappings": {
    "properties": {
      "variants": {
        "type": "nested",
        "properties": {
          "color": { "type": "keyword" },
          "stock": { "type": "integer" }
        }
      }
    }
  }
}
~~~

Một nested query:

~~~json
{
  "query": {
    "nested": {
      "path": "variants",
      "query": {
        "bool": {
          "filter": [
            { "term": { "variants.color": "black" } },
            { "range": { "variants.stock": { "gte": 3 } } }
          ]
        }
      }
    }
  }
}
~~~

Nó yêu cầu hai điều kiện khớp trong một nested element. **Cần tạo mapping đúng từ đầu hoặc xây index mới/reindex** nếu dữ liệu đã được lập chỉ mục dưới mapping không phù hợp. Không thể giả định việc đổi type từ object sang nested trong index đang có sẽ diễn ra tại chỗ, không gián đoạn.

### 24.1. Chi phí của nested index

Trong Elasticsearch/OpenSearch, nested objects được xử lý theo cơ chế lập chỉ mục riêng, tạo overhead lưu trữ/truy vấn. Khi update document cha, có thể phải cập nhật/reindex phần liên quan theo cơ chế engine. Hệ còn có giới hạn nested fields/objects theo cấu hình để chống tài liệu quá phức tạp. Cần kiểm tra theo phiên bản và workload.

Chỉ dùng `nested` khi truy vấn cần bảo toàn tương quan giữa những trường **cùng một phần tử**. Nếu mỗi product có hàng nghìn biến thể thay đổi liên tục, index riêng theo variant có thể phù hợp hơn, đổi lại có thêm bước tổng hợp product và đồng bộ.

## 25. Redis JSON/RediSearch: index phụ không có sẵn ở mọi triển khai

Redis dùng key–value; RedisJSON và RediSearch (hoặc các khả năng tương đương trong phiên bản/phân phối được dùng) có thể hỗ trợ lưu JSON và lập chỉ mục path theo cấu hình riêng.

Ví dụ mô hình dữ liệu:

~~~json
{
  "tenantId": "t01",
  "name": "Wireless Mouse",
  "attributes": { "color": "black" },
  "tags": ["wireless", "mouse"]
}
~~~

Muốn search theo `attributes.color` hoặc `tags` có thể cần khai báo schema index theo JSONPath/loại TAG/TEXT/NUMERIC phù hợp. Không phải mọi Redis server chỉ có lệnh `GET/SET` đều tự cung cấp tìm kiếm theo nested JSON.

Các điểm phải kiểm tra:

- RedisJSON/RediSearch có được cài và bật không?
- Phiên bản nào hỗ trợ kiểu field và cú pháp JSONPath cần thiết?
- Search index có hỗ trợ dữ liệu mảng object với same-element semantics theo cách yêu cầu không?
- Có chi phí đồng bộ index, RAM và giới hạn tài nguyên nào?
- Khi cập nhật JSON qua path, index có được làm mới kịp theo hợp đồng không?
- Nếu chỉ cần lookup theo key, liệu tạo search index có thực sự cần thiết không?

Tránh biến dữ liệu JSON trong Redis thành giả định rằng Redis là document search engine giống hệt MongoDB hoặc Elasticsearch.

## 26. Chọn mô hình theo truy vấn, không chỉ theo khả năng nhúng dữ liệu

Có ba lựa chọn phổ biến:

| Mô hình | Điểm mạnh | Đánh đổi |
|---|---|---|
| Embed array trong document cha + multikey | Đọc cả aggregate thuận tiện, update một document có thể nguyên tử | Array lớn, index fan-out, hot document |
| Tách phần tử thành document/bảng riêng | Index theo phần tử linh hoạt, phân trang và ghi độc lập | Nhiều lần đọc, thêm đồng bộ/tham chiếu |
| Materialized inverted index/projection | Query theo membership nhanh khi key được thiết kế đúng | Write amplification, consistency/rebuild, xóa/sửa đồng bộ |

Ví dụ catalog có hàng chục variants nhỏ mỗi product, chủ yếu xem chi tiết product và thỉnh thoảng lọc màu: embed + multikey có thể tốt. Nếu mỗi product có hàng trăm nghìn offers thay đổi từng giây, tách offers thành entities riêng có thể giảm hot document và cho index chuyên biệt.

Nếu hệ cần “tìm các product có một variant thỏa cả màu và stock”, hãy kiểm tra cả **ngữ nghĩa same-element** lẫn **đường truy cập**. Không thể chỉ nói “đã index color và stock” là đã giải quyết truy vấn.

## 27. Chỉ mục lồng nhau và dữ liệu thiếu/null/empty

Khi schema linh hoạt, có thể có:

~~~javascript
{ _id: "a" }
{ _id: "b", attributes: null }
{ _id: "c", attributes: {} }
{ _id: "d", attributes: { color: null } }
{ _id: "e", attributes: { color: "black" } }
{ _id: "f", tags: [] }
{ _id: "g", tags: ["black"] }
~~~

Các trạng thái missing, null, empty object và empty array không tương đương nghiệp vụ. Query trên `"attributes.color": null` trong MongoDB có semantics liên quan tới cả null và missing; muốn phân biệt cần `$exists`, `$type` và fixture kiểm thử đúng tình huống.

Index dạng sparse/partial, compound và wildcard có thể lập chỉ mục hoặc bỏ qua các trạng thái theo quy tắc khác nhau. Một migration thêm field mới cũng có thể làm thay đổi tập giá trị index được.

Điều kiện query, schema validation, default ở runtime và index cùng nhau quyết định kết quả. Đừng tạo unique constraint trên một field có nhiều record thiếu/null mà không đánh giá đúng quy tắc và khả năng chuyển dữ liệu.

## 28. Explain và phép đo mới cho biết index có thật sự hữu ích

Trong MongoDB có thể dùng:

~~~javascript
db.products.find({
  tenantId: "t01",
  variants: {
    $elemMatch: {
      color: "black",
      stock: { $gte: 3 }
    }
  }
}).explain("executionStats");
~~~

Các tín hiệu cần đọc:

| Thông số / hiện tượng | Câu hỏi |
|---|---|
| `winningPlan` | Dùng index nào hay collection scan? |
| `IXSCAN` và index bounds | Điều kiện lọc nào thật sự thu hẹp keys? |
| `totalKeysExamined` | Đọc bao nhiêu khóa index? |
| `totalDocsExamined` | Phải lấy bao nhiêu document để xác minh? |
| `nReturned` | Trả bao nhiêu document? |
| `FETCH` | Có phải kiểm tra thêm trên document gốc? |
| `SORT` | Có sort riêng sau scan hay không? |
| Execution time / p95/p99 | Trên workload thực, độ trễ có đạt yêu cầu? |

Không nên chỉ dựa vào một lần chạy với cache nóng. Cần dữ liệu đủ lớn, nhiều tenant, phân bố giá trị lệch, các mảng kích thước khác nhau, cả truy vấn chọn lọc và không chọn lọc. Kiểm tra phần chi phí **ghi** sau khi thêm index, không chỉ thời gian đọc.

### 28.1. Index hint có nên dùng?

Có thể dùng hint trong thí nghiệm để so sánh kế hoạch và hiểu planner, nhưng cố định hint production bừa bãi có thể làm query tệ khi phân bố dữ liệu thay đổi. Tốt hơn là lưu chứng cứ đo, theo dõi query latency/plan và chỉ hint khi có lý do, phạm vi và kế hoạch duy trì rõ ràng.

## 29. Benchmark thực hành: trước và sau index

Một kế hoạch thử nghiệm có thể dùng **dữ liệu giả lập**, không phải benchmark đã chạy:

- 100.000 product documents.
- Mỗi product có từ 1 đến 20 tags.
- Mỗi product có 1–15 variants; 1% product có trên 200 variants để thử skew.
- 10 tenant, trong đó có một tenant chiếm 60% dữ liệu.
- Color: black 35%, white 25%, màu còn lại phân bố không đều.
- Một số tag hiếm chỉ xuất hiện trong 0,1% product; tag phổ biến xuất hiện ở 80%.

Các bước:

1. Chạy queries đại diện **trước khi tạo index mới**, ghi plan và latency.
2. Tạo index trên `tenantId, attributes.color`; thử filter color.
3. Tạo index trên `tenantId, tags`; thử membership tag hiếm/phổ biến.
4. Tạo index trên `tenantId, variants.color, variants.stock`; thử query có/không `$elemMatch`.
5. Thử `updateOne` thêm tag, sửa stock của variant, thêm nhiều variants.
6. Đo lại read latency, docs/keys examined, write latency, index size và hot document contention.
7. So sánh với mô hình tách variants thành collection riêng nếu array quá lớn.
8. Ghi kết luận có phạm vi theo dữ liệu và workload; không lấy một con số p50 đại diện cho mọi truy vấn.

| Workload | Query cần đo | Kỳ vọng kiểm chứng |
|---|---|---|
| Q1 | Color black trong tenant | Dot-path/compound index có giảm scan? |
| Q2 | Tag rare-feature | Multikey membership chọn lọc đến đâu? |
| Q3 | Tag sale phổ biến | Planner có chọn index hợp lý không? |
| Q4 | Same variant black & stock≥3 | `$elemMatch` trả đúng tập kết quả? |
| Q5 | Array scalar có giá trị trong [5,10] | `$elemMatch` tránh khớp hai phần tử? |
| Q6 | Thêm/xóa tag | Index maintenance tốn bao nhiêu? |
| Q7 | Thêm 500 variants vào một product | Index entries, document size và write p99? |
| Q8 | Tìm attributes động | Wildcard so với index chuyên biệt? |

Đây là đề xuất phép thử; kết quả thực tế phụ thuộc server, dataset, version, index build và concurrency.

## 30. Lỗi thiết kế thường gặp

| Nhầm lẫn | Vì sao sai | Giải pháp |
|---|---|---|
| Có index trên object cha thì tự tối ưu mọi field con | Access path có thể khác | Index dotted path theo query |
| Có index `tags` là mọi truy vấn về array đều nhanh | Membership khác equality/sort/array length | Đo query plan đúng biểu thức |
| Hai dotted conditions trên array object luôn cùng phần tử | Có thể khớp hai object khác nhau | Dùng `$elemMatch` |
| Có index `variants.color` và `variants.stock` là đã đúng nghiệp vụ | Index không sửa semantics | Ràng buộc same-element và đo compound bounds |
| Gộp hai independent arrays vào compound multikey không cần kiểm tra | Có giới hạn parallel arrays | Thiết kế index/model khác |
| Unique multikey bảo vệ uniqueness trong cùng array | Chủ yếu ràng buộc across documents | Validate hoặc mô hình key riêng |
| Wildcard index luôn thay mọi index chuyên biệt | Có overhead và hạn chế query | Đo, giữ index cho hot path |
| FilterExpression trong DynamoDB là index lookup | Filter thường áp sau đọc | Key/GSI hoặc inverted-index items |
| Cassandra collection `CONTAINS` tự động rẻ | Cần index/access pattern phù hợp | Query-first table hoặc SAI/index đã xác minh |
| Array object trong search luôn giữ same-element | Object mapping có thể flatten | Nested mapping và nested query |
| Index chỉ ảnh hưởng read | Ghi thêm/sửa/xóa phải cập nhật index | Đo write amplification |
| Mảng lớn không giới hạn vẫn là một aggregate phù hợp | Hot document, index fan-out và memory | Tách entities theo lifecycle |
| Missing/null/empty array luôn như nhau | Query/index/validation khác nhau | Fixture và quy tắc tường minh |
| Index giúp bảo vệ quyền tenant | Index chỉ tối ưu đường truy cập | Authorization và tenant scoping |
| Có index là chắc chắn p99 tốt | Selectivity/skew/plan/caching thay đổi | Benchmark trên workload thật |

## 31. Bài tập thiết kế

### Bài A — Đọc và sửa truy vấn sai

Cho record:

~~~javascript
{
  _id: "p500",
  tenantId: "t01",
  variants: [
    { color: "black", stock: 0, sku: "BLACK" },
    { color: "white", stock: 10, sku: "WHITE" }
  ]
}
~~~

1. Viết query sai có thể trả `p500` khi tìm biến thể black và stock≥5.
2. Sửa query bằng `$elemMatch`.
3. Tạo index phù hợp nếu truy vấn có `tenantId`.
4. Dùng explain kiểm tra index path/keys/docs examined.
5. Giải thích vì sao `LIMIT 10` không tự làm một filter không có index trở nên rẻ.

### Bài B — Từ mảng tags sang bảng tra cứu

Có một triệu product, mỗi product có khoảng 30 tags. Hệ cần tra cứu theo `tenantId + tag` với lưu lượng lớn.

1. Thiết kế multikey index MongoDB trên `tenantId,tags`.
2. Thiết kế inverted-index items theo `(tenantId,tag) → productId`.
3. So sánh độ trễ đọc, số index entries, chi phí ghi và eventual consistency.
4. Khi xóa một tag hoặc product, những index/projection nào phải cập nhật?
5. Nếu tag `sale` xuất hiện ở 90% product, truy vấn sẽ gặp vấn đề gì?

### Bài C — Tính đúng đắn của mảng lồng nhau

Với Course chứa `groups[].members[]`:

1. Viết query tìm member thuộc bất kỳ group nào.
2. Viết query yêu cầu member `u2` thuộc đúng group `g1` và role `learner`.
3. Xác định cấp nào cần `$elemMatch`.
4. Khi số members tăng lên hàng triệu, hãy đề xuất mô hình collection riêng và khóa truy cập.
5. Xác định bất biến uniqueness của một membership.

### Bài D — So sánh sản phẩm NoSQL

Một catalog có trường `attributes` linh hoạt và `tags` là array:

1. Trong MongoDB, chọn dot-path, multikey hoặc wildcard theo query.
2. Trong DynamoDB, giải thích vì sao FilterExpression trên nested Map không là GSI lookup.
3. Trong Cassandra, thiết kế bảng `products_by_tag` theo partition key.
4. Trong Elasticsearch/OpenSearch, chỉ ra khi nào object mapping không đủ và cần nested.
5. Nêu đường đồng bộ khi product đổi tags và cách xử lý event bị gửi lại.

### Bài E — Đánh giá thực nghiệm

Tạo fixture có missing field, null, empty array, tag lặp, variant trùng SKU, hai array độc lập và array object có điều kiện nằm ở hai phần tử. Định nghĩa expected results cho từng query trước khi tạo index. Sau đó đo p50/p95/p99, keys/docs examined, kích thước index và chi phí cập nhật. Kết luận phải phân biệt **kết quả đúng** với **kết quả nhanh**.

## 32. Câu hỏi tự kiểm tra

1. Dotted-path index khác index của cả embedded object như thế nào?
2. Vì sao index trên field array trong MongoDB có thể trở thành multikey?
3. `{tags: "wireless"}` và `{tags: ["wireless","mouse"]}` có cùng ý nghĩa không?
4. `$in` khác `$all` khi kiểm tra phần tử mảng thế nào?
5. Vì sao hai predicate `variants.color` và `variants.stock` độc lập có thể trả kết quả sai?
6. `$elemMatch` ràng buộc điều kiện cùng phần tử ra sao?
7. Compound index trên hai field từ cùng array khác hai independent arrays ở giới hạn nào?
8. Unique multikey có tự chặn hai phần tử trùng trong cùng document không?
9. Partial index giúp gì, và query nào không được dùng nó nếu sẽ làm thiếu kết quả?
10. Sparse index và partial index có hoàn toàn giống nhau không?
11. Wildcard index phù hợp khi nào, và vì sao không luôn thay được index chuyên biệt?
12. Vì sao tag rất phổ biến có thể khiến index membership ít lợi ích?
13. Khi nào index multikey còn cần FETCH?
14. Vì sao cập nhật một tag/variant có thể làm nhiều index entries thay đổi?
15. DynamoDB FilterExpression trên Map/List có ý nghĩa gì về chi phí đọc?
16. CQL `CONTAINS` có luôn đồng nghĩa truy vấn được index hỗ trợ không?
17. Vì sao Elasticsearch object mapping không luôn giữ tương quan giữa các phần tử?
18. Khi dữ liệu array quá lớn, những đường truy cập nào có thể tốt hơn nếu tách collection?
19. Khi product xóa tag, một inverted-index projection phải xử lý gì?
20. Index có thể thay thế kiểm tra tenant/quyền truy cập không?

## 33. Tổng kết: đúng đường truy cập và đúng quan hệ phần tử

Chỉ mục cho nested field và phần tử collection giúp NoSQL tìm dữ liệu phức tạp mà không phải quét toàn bộ bản ghi. **Dot-path** phục vụ trường con; **multikey** hỗ trợ membership trong array; **compound/partial/wildcard indexes** giải quyết những access pattern chuyên biệt. Tuy nhiên, điều quyết định là **ngữ nghĩa**: tìm màu đen và tồn kho còn phải chỉ rõ hai điều kiện có thuộc **cùng một variant** hay không. Trong MongoDB, `$elemMatch` thể hiện ràng buộc đó; trong Elasticsearch/OpenSearch, nested mapping/query giải quyết bài toán tương ứng theo mô hình index riêng.

Khi xây dựng hệ thống thật, hãy bắt đầu bằng câu query nghiệp vụ, xác định field path và quan hệ giữa các phần tử, chọn index phù hợp, rồi dùng explain và benchmark để đo selectivity, index bounds, docs examined, p95/p99 và chi phí ghi. Nếu collection/array lớn hoặc truy cập theo phần tử chiếm ưu thế, cân nhắc tách phần tử thành entities hoặc xây inverted-index projection có cơ chế đồng bộ. **Chỉ mục tốt là chỉ mục giúp truy vấn trả đúng kết quả với chi phí đọc, ghi và vận hành chấp nhận được — không phải chỉ mục được tạo ra nhiều nhất.**
