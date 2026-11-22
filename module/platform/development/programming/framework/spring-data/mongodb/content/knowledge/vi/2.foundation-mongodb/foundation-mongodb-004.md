# Document lồng nhau, array và đường dẫn trường

## 1. Mục tiêu và bối cảnh

Trong MongoDB, một document BSON có thể chứa **document lồng nhau** (embedded document), **mảng** (array), và nhiều cấp kết hợp của hai kiểu dữ liệu này. Đây là nền tảng để mô hình hóa dữ liệu gần với đối tượng nghiệp vụ, ví dụ một đơn hàng chứa địa chỉ giao hàng, nhãn và danh sách sản phẩm.

Trong module **SPRING_DATA_MONGODB (Spring Data MongoDB)**, hiểu cấu trúc này giúp bạn thiết kế document, ánh xạ sang Java, xây dựng truy vấn bằng repository hoặc `MongoTemplate`, cập nhật phần tử mảng, xây dựng aggregation và lựa chọn index hợp lý. Sau bài này, bạn có thể:

- Phân biệt trường scalar, document lồng nhau, mảng scalar và mảng document.
- Đọc và viết **đường dẫn trường** bằng dấu chấm để truy vấn, chiếu và cập nhật.
- Hiểu chính xác điều kiện trên mảng, đặc biệt sự khác nhau giữa các điều kiện độc lập và `$elemMatch`.
- Thao tác với mảng bằng toán tử cập nhật và xử lý mảng bằng aggregation.
- Áp dụng cấu trúc document vào Spring Data MongoDB và nhận biết các giới hạn về index, kích thước và tính nguyên tử.

## 2. Một document làm ví dụ xuyên suốt

Giả sử collection `orders` chứa một đơn hàng:

```javascript
db.orders.insertOne({
  customerId: "KH-101",
  status: "NEW",
  shippingAddress: {
    city: "Đà Nẵng",
    district: "Hải Châu",
    geo: {
      lat: 16.05,
      lng: 108.22
    }
  },
  tags: ["priority", "gift"],
  items: [
    {
      sku: "BOOK-01",
      quantity: 2,
      unitPrice: 120000,
      options: { color: "blue" }
    },
    {
      sku: "PEN-02",
      quantity: 1,
      unitPrice: 30000,
      options: { color: "black" }
    }
  ]
});
```

MongoDB tự sinh `_id` nếu không được cung cấp. Cấu trúc trong ví dụ gồm:

| Thành phần | Kiểu dữ liệu | Ý nghĩa |
| --- | --- | --- |
| `customerId`, `status` | Scalar (chuỗi) | Giá trị đơn |
| `shippingAddress` | Document lồng nhau | Nhóm các trường cùng thuộc một địa chỉ |
| `shippingAddress.geo` | Document lồng nhau cấp sâu hơn | Tọa độ của địa chỉ |
| `tags` | Mảng chuỗi | Nhiều nhãn cho một đơn hàng |
| `items` | Mảng document | Nhiều dòng sản phẩm, mỗi dòng có nhiều thuộc tính |
| `items.options` | Document bên trong phần tử mảng | Tùy chọn sản phẩm |

Có thể hình dung cây dữ liệu như sau:

```text
orders (collection)
└── document đơn hàng
    ├── customerId: "KH-101"
    ├── shippingAddress
    │   ├── city: "Đà Nẵng"
    │   ├── district: "Hải Châu"
    │   └── geo
    │       ├── lat: 16.05
    │       └── lng: 108.22
    ├── tags: ["priority", "gift"]
    └── items: [document, document]
        ├── items[0]: sku, quantity, unitPrice, options
        └── items[1]: sku, quantity, unitPrice, options
```

**Nhúng document** giúp đọc dữ liệu liên quan trong một lần lấy đơn hàng và cập nhật nhiều trường của cùng document một cách nguyên tử. Nhưng mảng tăng trưởng không giới hạn có thể làm document phình to; mô hình nhúng phù hợp nhất khi dữ liệu con có quan hệ sở hữu rõ ràng và kích thước được kiểm soát.

## 3. Đường dẫn trường và dot notation

MongoDB sử dụng dấu chấm (`.`) để truy cập các cấp bên trong document. Đây là **đường dẫn trường** (field path), không phải một tên trường mới.

| Đường dẫn | Trỏ đến |
| --- | --- |
| `shippingAddress.city` | Thành phố trong document địa chỉ |
| `shippingAddress.geo.lat` | Vĩ độ ở cấp lồng nhau thứ hai |
| `items.sku` | Trường `sku` của các document trong mảng `items` |
| `items.options.color` | Màu trong `options` của các phần tử `items` |
| `items.0.sku` | `sku` của phần tử đầu tiên trong `items` |

Khi đặt đường dẫn có dấu chấm vào object truy vấn JavaScript, cần đặt **toàn bộ khóa trong dấu nháy**:

```javascript
// Địa chỉ có thành phố Đà Nẵng
db.orders.find({ "shippingAddress.city": "Đà Nẵng" });

// Đơn hàng có ít nhất một dòng sản phẩm mang SKU này
db.orders.find({ "items.sku": "BOOK-01" });

// SKU ở vị trí đầu tiên của mảng items
db.orders.find({ "items.0.sku": "BOOK-01" });
```

Hai truy vấn cuối khác nhau: `items.sku` có thể khớp **bất kỳ phần tử nào**, còn `items.0.sku` chỉ xét phần tử có chỉ số `0`. Dựa vào vị trí cố định thường kém bền vững vì thứ tự mảng có thể thay đổi.

Đường dẫn cũng dùng được trong phép so sánh và kiểm tra sự tồn tại:

```javascript
// Ít nhất một dòng có số lượng từ 2 trở lên
db.orders.find({ "items.quantity": { $gte: 2 } });

// Có trường tọa độ lat
db.orders.find({ "shippingAddress.geo.lat": { $exists: true } });

// lat có kiểu BSON double
db.orders.find({ "shippingAddress.geo.lat": { $type: "double" } });
```

Lưu ý: `$exists: true` chỉ kiểm tra trường có mặt, **không bảo đảm giá trị khác `null`**. Trong truy vấn thông thường, điều kiện `{ "shippingAddress.geo.lat": null }` có thể khớp cả trường có giá trị `null` lẫn trường không tồn tại. Khi cần tìm đúng kiểu BSON Null, có thể dùng `$type: "null"`.

## 4. Truy vấn mảng: giá trị, phần tử và nhiều điều kiện

### 4.1. Mảng scalar

Với `tags: ["priority", "gift"]`:

```javascript
// Chứa một phần tử bằng "gift"
db.orders.find({ tags: "gift" });

// Chứa cả hai nhãn, không phụ thuộc thứ tự
db.orders.find({ tags: { $all: ["gift", "priority"] } });

// Mảng có đúng 2 phần tử
db.orders.find({ tags: { $size: 2 } });

// So khớp toàn bộ giá trị mảng, bao gồm thứ tự
db.orders.find({ tags: ["priority", "gift"] });
```

Các ý nghĩa cần phân biệt:

- `{ tags: "gift" }` tìm document có **ít nhất một phần tử** bằng `"gift"`.
- `$all` yêu cầu có **tất cả giá trị chỉ định**, dù thứ tự có thể khác.
- `$size` so khớp độ dài mảng, nhưng không thể dùng `$size` trực tiếp với một khoảng số lượng như `$gte`.
- Truy vấn bằng nguyên mảng đòi hỏi mảng khớp chính xác cả giá trị và thứ tự.

### 4.2. Mảng document và bẫy «hai phần tử khác nhau»

Xét truy vấn:

```javascript
db.orders.find({
  "items.sku": "BOOK-01",
  "items.quantity": 1
});
```

**Document ví dụ vẫn khớp truy vấn này**, mặc dù sản phẩm `BOOK-01` có `quantity: 2`. Lý do: điều kiện `items.sku` có thể khớp phần tử thứ nhất, còn `items.quantity` có thể khớp phần tử thứ hai. Hai điều kiện độc lập không tự buộc phải áp dụng lên cùng một phần tử.

Khi cần các điều kiện nằm trong **cùng một phần tử**, dùng `$elemMatch`:

```javascript
// Không khớp document ví dụ: BOOK-01 có quantity = 2
db.orders.find({
  items: {
    $elemMatch: {
      sku: "BOOK-01",
      quantity: 1
    }
  }
});

// Khớp document ví dụ: cùng dòng BOOK-01 có quantity >= 2
db.orders.find({
  items: {
    $elemMatch: {
      sku: "BOOK-01",
      quantity: { $gte: 2 }
    }
  }
});
```

| Cách viết | Ý nghĩa |
| --- | --- |
| `"items.sku": "BOOK-01"` | Có ít nhất một phần tử có SKU đó |
| `"items.sku": "BOOK-01", "items.quantity": 1` | Có thể khớp trên hai phần tử khác nhau |
| `items: { $elemMatch: { sku: "BOOK-01", quantity: 1 } }` | Một phần tử phải thỏa **cả hai** điều kiện |

`$elemMatch` đặc biệt quan trọng với dữ liệu dạng danh sách dòng hàng, lịch sử trạng thái, lịch học, danh sách thành viên hoặc bất kỳ trường hợp nào cần giữ mối liên hệ giữa nhiều thuộc tính của cùng phần tử.

### 4.3. Projection: chỉ lấy những trường cần thiết

Projection giới hạn những trường được trả về:

```javascript
db.orders.find(
  { "shippingAddress.city": "Đà Nẵng" },
  {
    _id: 0,
    customerId: 1,
    "shippingAddress.city": 1,
    "items.sku": 1
  }
);
```

Kết quả giữ lại phần đường dẫn được yêu cầu, thay vì trả toàn bộ dữ liệu đơn hàng. **Chiếu `"items.sku": 1` không có nghĩa là chỉ trả về phần tử mảng khớp điều kiện lọc**; thông thường nó chiếu trường `sku` của các phần tử trong mảng. Nếu cần chọn từng phần tử thỏa điều kiện, hãy cân nhắc `$elemMatch` trong projection hoặc `$filter` trong aggregation.

## 5. Cập nhật document lồng nhau và phần tử mảng

### 5.1. Cập nhật trường con mà không thay cả document cha

```javascript
db.orders.updateOne(
  { customerId: "KH-101" },
  { $set: { "shippingAddress.city": "Huế" } }
);
```

Cách dùng đường dẫn giữ lại `district` và `geo`. Ngược lại, cập nhật `$set: { shippingAddress: { city: "Huế" } }` sẽ **thay toàn bộ giá trị của `shippingAddress`**, khiến các trường con không có trong object mới biến mất. Ví dụ cập nhật ở các mục là các thao tác độc lập, không cần thực hiện tuần tự.

### 5.2. Thêm và xóa phần tử mảng

```javascript
// Thêm một nhãn; nếu chuỗi đã tồn tại thì không thêm trùng
db.orders.updateOne(
  { customerId: "KH-101" },
  { $addToSet: { tags: "fragile" } }
);

// Thêm một dòng hàng mới vào cuối mảng
db.orders.updateOne(
  { customerId: "KH-101" },
  {
    $push: {
      items: {
        sku: "NOTE-03",
        quantity: 1,
        unitPrice: 45000,
        options: { color: "white" }
      }
    }
  }
);

// Xóa mọi dòng hàng có sku = PEN-02
db.orders.updateOne(
  { customerId: "KH-101" },
  { $pull: { items: { sku: "PEN-02" } } }
);
```

`$push` luôn thêm phần tử, còn `$addToSet` tránh thêm một **giá trị phần tử** đã tồn tại theo quy tắc so sánh của MongoDB; nó không tự bảo đảm tính duy nhất cho một trường con như `items.sku` trong các object khác nhau.

### 5.3. Toán tử vị trí: `$`, `$[]` và `$[identifier]`

Ba kiểu cập nhật phần tử mảng thường gặp:

| Toán tử | Phạm vi |
| --- | --- |
| `$` | Phần tử đầu tiên khớp điều kiện mảng trong truy vấn |
| `$[]` | Tất cả phần tử của mảng |
| `$[line]` | Tất cả phần tử thỏa điều kiện `arrayFilters` cho định danh `line` |

```javascript
// Tăng số lượng của phần tử đầu tiên có sku = BOOK-01
db.orders.updateOne(
  { customerId: "KH-101", "items.sku": "BOOK-01" },
  { $inc: { "items.$.quantity": 1 } }
);

// Tăng giá mỗi dòng hàng thêm 1.000
db.orders.updateOne(
  { customerId: "KH-101" },
  { $inc: { "items.$[].unitPrice": 1000 } }
);

// Chỉ tăng giá các dòng có quantity >= 2
db.orders.updateOne(
  { customerId: "KH-101" },
  { $inc: { "items.$[line].unitPrice": 1000 } },
  { arrayFilters: [{ "line.quantity": { $gte: 2 } }] }
);
```

`$` là toán tử vị trí của mảng và cần điều kiện mảng thích hợp trong bộ lọc truy vấn. Với `$[line]`, tên `line` trong đường dẫn và trong `arrayFilters` phải trùng nhau. Nếu có nhiều dòng hàng cùng SKU, `$` chỉ tác động lên phần tử khớp đầu tiên; dùng filtered positional operator khi muốn tác động lên tất cả phần tử phù hợp.

MongoDB bảo đảm một thao tác ghi trên **một document** là nguyên tử, kể cả khi nó thay đổi nhiều trường hoặc phần tử mảng trong document đó. Tuy nhiên, một thao tác trên nhiều document không tự trở thành giao dịch nguyên tử cho cả tập; nếu nghiệp vụ cần ràng buộc xuyên document, phải thiết kế cơ chế nhất quán hoặc transaction phù hợp.

## 6. Xử lý array trong aggregation

Truy vấn `find` trả về document khớp điều kiện. Khi cần tính toán, biến đổi hoặc thống kê trên từng phần tử mảng, sử dụng aggregation pipeline.

### 6.1. `$unwind`: tách mỗi phần tử thành một dòng pipeline

```javascript
db.orders.aggregate([
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.sku",
      totalQuantity: { $sum: "$items.quantity" },
      totalAmount: {
        $sum: { $multiply: ["$items.quantity", "$items.unitPrice"] }
      }
    }
  },
  { $sort: { totalQuantity: -1 } }
]);
```

Mỗi dòng hàng trong `items` trở thành một document tạm thời trong pipeline; `$group` sau đó cộng dồn số lượng và thành tiền theo `sku` trên tất cả đơn hàng. Mặc định, `$unwind` bỏ qua document có trường mảng rỗng, `null` hoặc thiếu; có thể dùng tùy chọn `preserveNullAndEmptyArrays: true` khi cần giữ các document đó.

### 6.2. `$filter`: giữ lại phần tử mảng thỏa điều kiện

```javascript
db.orders.aggregate([
  {
    $project: {
      _id: 0,
      customerId: 1,
      highQuantityItems: {
        $filter: {
          input: "$items",
          as: "line",
          cond: { $gte: ["$$line.quantity", 2] }
        }
      }
    }
  }
]);
```

Với đơn hàng mẫu, `highQuantityItems` chỉ chứa dòng `BOOK-01`. Khác với lọc document bằng `"items.quantity": { $gte: 2 }`, `$filter` **tạo mảng kết quả chỉ gồm các phần tử phù hợp**. Trong biểu thức aggregation, `$items` tham chiếu trường của document hiện hành còn `$$line` tham chiếu biến được đặt qua `as`. Toán tử `$map` có thể biến đổi từng phần tử, chẳng hạn tạo danh sách thành tiền `quantity × unitPrice`.

## 7. Ánh xạ và truy vấn bằng Spring Data MongoDB

### 7.1. Mapping embedded document và list sang Java

Spring Data MongoDB ánh xạ document lồng nhau thành object Java và mảng BSON thành collection Java. Ví dụ dưới đây dùng Java 17+ với `record` để rút gọn phần khai báo:

```java
import java.util.List;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record Order(
    @Id String id,
    String customerId,
    String status,
    ShippingAddress shippingAddress,
    List<String> tags,
    List<LineItem> items
) {}

record ShippingAddress(String city, String district, Geo geo) {}
record Geo(double lat, double lng) {}
record LineItem(String sku, int quantity, long unitPrice, ItemOptions options) {}
record ItemOptions(String color) {}
```

Nếu dự án dùng POJO với constructor, getter và setter thì ánh xạ về mặt cấu trúc vẫn tương tự. Ví dụ này dùng `long` cho giá tiền số nguyên theo đơn vị nhỏ nhất của tiền tệ; với giá trị cần phần thập phân, hãy chọn kiểu số và quy ước lưu trữ phù hợp, tránh sử dụng `double` cho tính toán tiền.

Điểm cần nhớ:

- `shippingAddress` là một object con, không phải collection độc lập.
- `List<LineItem>` được lưu dưới dạng mảng document trong chính đơn hàng.
- `@Id` ánh xạ thuộc tính định danh sang `_id`; cách lưu kiểu ID cụ thể chịu ảnh hưởng của cấu hình và cơ chế chuyển đổi của Spring Data.
- Tên field mặc định dựa trên tên thuộc tính; nếu dùng `@Field` để đổi tên lưu trữ, cần giữ truy vấn và mapping nhất quán.

### 7.2. Repository: đi qua thuộc tính lồng nhau

```java
import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.mongodb.repository.Query;

public interface OrderRepository extends MongoRepository<Order, String> {

    // Dấu gạch dưới chỉ rõ ranh giới thuộc tính lồng nhau.
    List<Order> findByShippingAddress_City(String city);

    // Bảo đảm sku và quantity nằm trong cùng một dòng hàng.
    @Query("{ 'items': { $elemMatch: { 'sku': ?0, 'quantity': { $gte: ?1 } } } }")
    List<Order> findByItemSkuAndMinQuantity(String sku, int minimumQuantity);
}
```

Spring Data có thể suy ra nhiều truy vấn bằng tên phương thức. Tuy nhiên, khi cần nhiều điều kiện trên **cùng phần tử mảng**, `@Query` với `$elemMatch` thể hiện ràng buộc rõ ràng hơn việc kết hợp các điều kiện dot notation độc lập. Tham số `?0` và `?1` được Spring Data bind từ lời gọi phương thức.

### 7.3. MongoTemplate: kiểm soát trực tiếp query và update

```java
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public class OrderOperations {
    private final MongoTemplate mongoTemplate;

    public OrderOperations(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public List<Order> findOrdersWithBookQuantityAtLeastTwo() {
        Criteria itemCriteria = Criteria.where("sku").is("BOOK-01")
            .and("quantity").gte(2);
        Query query = new Query(
            Criteria.where("items").elemMatch(itemCriteria)
        );
        return mongoTemplate.find(query, Order.class);
    }

    public void increaseBookQuantity(String customerId) {
        Query query = new Query(
            Criteria.where("customerId").is(customerId)
                .and("items.sku").is("BOOK-01")
        );
        Update update = new Update().inc("items.$.quantity", 1);
        mongoTemplate.updateFirst(query, update, Order.class);
    }
}
```

`Criteria.where("items").elemMatch(...)` tương đương ý nghĩa với truy vấn `$elemMatch` trong MongoDB. `Update.inc("items.$.quantity", 1)` sử dụng toán tử vị trí để tăng số lượng của phần tử phù hợp đầu tiên. Khi ứng dụng có nhiều luồng cùng cập nhật, các phép cập nhật nguyên tử như `$inc` thường an toàn hơn mẫu «đọc object → tăng trong bộ nhớ → lưu đè toàn bộ».

**Lưu ý về đường dẫn trong ứng dụng:** Khi viết query/update, hãy bám theo tên thuộc tính đã được ánh xạ của model và kiểm tra cấu trúc thực tế trong collection, nhất là khi dự án sử dụng `@Field` hoặc custom converters. Với truy vấn phức tạp, xem câu lệnh MongoDB được tạo ra và kiểm thử trên dữ liệu có nhiều phần tử mảng.

## 8. Index, thiết kế schema và hiệu năng

### 8.1. Index trên đường dẫn lồng nhau

MongoDB hỗ trợ tạo index trên nested path:

```javascript
db.orders.createIndex({ "shippingAddress.city": 1 });
db.orders.createIndex({ "items.sku": 1 });

db.orders.find({ "items.sku": "BOOK-01" })
  .explain("executionStats");
```

Index trên `shippingAddress.city` phục vụ lọc theo thành phố. Index trên `items.sku` là **multikey index** khi `items` là mảng: MongoDB lập index cho các giá trị tương ứng với phần tử mảng. Điều này hữu ích với truy vấn tìm theo SKU, nhưng mảng quá lớn cũng khiến số entry index và chi phí ghi tăng.

Với compound multikey index, MongoDB có giới hạn đối với việc lập index cho **các trường mảng song song** trong cùng document. Khi truy vấn đồng thời nhiều thuộc tính của cùng một phần tử mảng, `$elemMatch` không chỉ giúp đúng ngữ nghĩa mà còn có thể giúp bộ tối ưu tận dụng điều kiện index phù hợp. Hãy đánh giá bằng `explain("executionStats")` trên dữ liệu và truy vấn thực tế, thay vì suy luận chỉ từ sự tồn tại của index.

### 8.2. Khi nào nên nhúng, khi nào nên tham chiếu?

| Tiêu chí | Nhúng document/array | Tham chiếu sang collection khác |
| --- | --- | --- |
| Cách đọc | Hay đọc dữ liệu cha cùng dữ liệu con | Dữ liệu con được truy cập độc lập |
| Vòng đời | Con gắn chặt với cha | Con có vòng đời hoặc quyền sở hữu riêng |
| Kích thước | Có giới hạn và dễ dự đoán | Số phần tử có thể tăng rất lớn |
| Cập nhật | Muốn cập nhật nguyên tử trong một document | Cần cập nhật từng đối tượng độc lập |
| Đánh đổi | Document lớn, mảng dài và index nhiều entry | Phải thực hiện thêm truy vấn hoặc `$lookup` khi cần kết hợp |

Ví dụ, địa chỉ giao hàng ghi nhận tại thời điểm đặt hàng thường nên được nhúng vào đơn hàng vì đó là **ảnh chụp dữ liệu lịch sử**. Danh sách dòng hàng thường cũng hợp lý để nhúng nếu mỗi đơn chỉ có số dòng hữu hạn. Trái lại, lịch sử sự kiện liên tục phát sinh hàng triệu bản ghi thường phù hợp hơn với collection riêng hoặc chiến lược phân đoạn.

MongoDB có giới hạn **16 MiB cho một document BSON**. Việc nhúng các mảng tăng trưởng không kiểm soát vừa có nguy cơ chạm giới hạn này, vừa tăng chi phí truyền dữ liệu và duy trì index. Không nên dựa vào việc dùng `$slice` khi đọc để giải quyết tận gốc một document tăng trưởng vô hạn.

## 9. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Query yêu cầu SKU và số lượng trả về dòng hàng «sai» | Điều kiện dot notation khớp các phần tử khác nhau | Dùng `$elemMatch` khi cần cùng phần tử |
| Cập nhật thành phố làm mất quận và tọa độ | `$set` thay toàn bộ object `shippingAddress` | Dùng `$set` lên `shippingAddress.city` |
| Thêm nhãn tạo dữ liệu trùng | Dùng `$push` thay vì `$addToSet` | Chọn toán tử theo ý nghĩa nghiệp vụ |
| Cập nhật chỉ thay một trong nhiều dòng phù hợp | Dùng positional `$` | Dùng `$[identifier]` kết hợp `arrayFilters` |
| Query khớp đơn hàng nhưng kết quả vẫn có cả mảng `items` | Lọc document khác với lọc phần tử mảng | Dùng `$filter` hoặc projection phù hợp |
| Truy vấn lồng nhau chậm trên dữ liệu lớn | Chưa có index thích hợp hoặc index multikey quá lớn | Đo bằng `explain`; đánh giá query pattern và kích thước mảng |
| Dữ liệu lỗi vì giả định trường luôn tồn tại | Schema linh hoạt; `null` và missing có thể khác nhau | Kiểm tra `$exists`, `$type` và áp dụng validation/mapping phù hợp |

Một lỗi tinh vi khác là lạm dụng vị trí `items.0`. Cách này chỉ ổn khi vị trí có ý nghĩa nghiệp vụ ổn định; với danh sách sản phẩm, nên định danh dòng hàng bằng trường rõ ràng (ví dụ `lineId`) khi cần chỉnh sửa chính xác một dòng.

## 10. Thực hành có lời giải

Hãy sử dụng collection `orders` có cấu trúc như ở mục 2. Các truy vấn bên dưới độc lập với nhau; hãy chạy trên dữ liệu mẫu mới nếu đã thử các lệnh cập nhật.

**Bài 1.** Tìm đơn hàng giao đến Đà Nẵng, có nhãn `priority` và chứa một dòng `BOOK-01` với số lượng từ 2 trở lên.

```javascript
db.orders.find({
  "shippingAddress.city": "Đà Nẵng",
  tags: "priority",
  items: {
    $elemMatch: {
      sku: "BOOK-01",
      quantity: { $gte: 2 }
    }
  }
});
```

**Bài 2.** Tăng số lượng của **tất cả** dòng có SKU `BOOK-01` trong đơn hàng `KH-101`, kể cả khi dữ liệu vô tình có nhiều dòng cùng SKU.

```javascript
db.orders.updateOne(
  { customerId: "KH-101" },
  { $inc: { "items.$[line].quantity": 1 } },
  { arrayFilters: [{ "line.sku": "BOOK-01" }] }
);
```

**Bài 3.** Chỉ trả về `customerId` và các dòng hàng có `unitPrice` từ 100000 trở lên.

```javascript
db.orders.aggregate([
  {
    $project: {
      _id: 0,
      customerId: 1,
      expensiveItems: {
        $filter: {
          input: "$items",
          as: "line",
          cond: { $gte: ["$$line.unitPrice", 100000] }
        }
      }
    }
  }
]);
```

Các bài tập minh họa ba cấp xử lý riêng biệt: **lọc document** với `find` và `$elemMatch`, **cập nhật các phần tử được chọn** với `arrayFilters`, và **lọc mảng trong kết quả** với `$filter`.

## 11. Ghi nhớ

1. Document lồng nhau mô tả quan hệ cấu thành; mảng mô tả nhiều giá trị hoặc nhiều object trong cùng document.
2. Đường dẫn dấu chấm truy cập nested field và field của phần tử mảng. Trong query đối với mảng, đường dẫn thường có nghĩa «ít nhất một phần tử khớp».
3. Nhiều điều kiện dot notation trên cùng mảng có thể khớp **những phần tử khác nhau**. Dùng `$elemMatch` nếu cần cùng phần tử.
4. Dùng đường dẫn khi cập nhật trường con, `$` cho phần tử đầu tiên, `$[]` cho tất cả và `$[identifier]` cùng `arrayFilters` cho một tập phần tử được chọn.
5. Dùng `$unwind` để tổng hợp theo từng phần tử và `$filter` để tạo mảng đầu ra đã lọc.
6. Trong Spring Data MongoDB, object và `List<T>` ánh xạ tự nhiên sang nested document và array; kiểm tra ngữ nghĩa truy vấn thay vì chỉ dựa vào tên method.
7. Index theo đường dẫn, đo hiệu năng thật và giữ kích thước mảng trong giới hạn phù hợp với nghiệp vụ.
