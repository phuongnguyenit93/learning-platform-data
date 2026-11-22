# Đường dẫn document nhúng và dot notation

## 1. Mục tiêu và bối cảnh

MongoDB cho phép một document chứa document khác, array, và array gồm nhiều document. Thiết kế này rất phù hợp với đơn hàng có địa chỉ giao hàng hoặc danh sách dòng hàng: những dữ liệu thường được đọc cùng một đơn có thể lưu ngay trong một document BSON. Nhưng khi tìm kiếm, chúng ta phải diễn đạt **đường dẫn tới trường con** cho chính xác.

Ví dụ, để tìm các đơn giao đến thành phố Hà Nội, thay vì chỉ truy vấn toàn bộ object `shippingAddress`, MongoDB cho phép chỉ định trường con bằng **dot notation**:

```javascript
db.orders.find({ "ship_to.city_name": "Hà Nội" });
```

Đường dẫn này có ý nghĩa khác với việc so khớp toàn bộ document `ship_to`. Và khi trường cần truy vấn nằm trong **array của các document**, các điều kiện trên cùng một đường dẫn còn có thể khớp **những phần tử khác nhau** nếu không dùng `$elemMatch`.

Bài thuộc chương **Query và Criteria** trong module **SPRING_DATA_MONGODB**. Trong quá trình dùng Spring Data MongoDB để kết nối, ánh xạ document và thao tác bằng `MongoTemplate` hoặc repository, hiểu dot notation giúp bạn xây dựng filter, projection, sort, update và index đúng dữ liệu. Kiến thức này cũng liên quan đến aggregation, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng.

Sau bài học, bạn có thể:

1. Phân biệt đường dẫn property Java và đường dẫn field BSON khi dùng `@Field`.
2. Viết query mongosh và `Query`/`Criteria` cho document nhúng.
3. Truy vấn array chứa document, giải thích rõ tình huống cần `$elemMatch`.
4. Phân biệt field không tồn tại, BSON Null và đường dẫn con bị thiếu.
5. Dùng query dẫn xuất của repository cho property lồng nhau, thiết kế index multikey phù hợp.
6. Cập nhật một trường lồng nhau mà không vô tình thay thế cả subdocument, đồng thời kiểm thử query thực tế.

## 2. Mô hình dữ liệu: đơn hàng, địa chỉ và dòng hàng

### 2.1. BSON thực tế

Giả sử collection `orders` lưu dữ liệu dưới dạng:

```javascript
db.orders.insertMany([
  {
    _id: "ord-001",
    tenantId: "tenant-a",
    status: "PAID",
    ship_to: {
      city_name: "Hà Nội",
      district: "Cầu Giấy",
      street: "Xuân Thủy"
    },
    items: [
      { sku_code: "BOOK-A", quantity: 1, unitPriceVnd: NumberLong("90000") },
      { sku_code: "BOOK-B", quantity: 4, unitPriceVnd: NumberLong("60000") }
    ],
    createdAt: ISODate("2026-11-18T08:00:00Z")
  },
  {
    _id: "ord-002",
    tenantId: "tenant-a",
    status: "PAID",
    ship_to: {
      city_name: "Đà Nẵng",
      district: "Hải Châu",
      street: "Bạch Đằng"
    },
    items: [
      { sku_code: "BOOK-A", quantity: 3, unitPriceVnd: NumberLong("90000") }
    ],
    createdAt: ISODate("2026-11-19T09:00:00Z")
  },
  {
    _id: "ord-003",
    tenantId: "tenant-a",
    status: "NEW",
    ship_to: {
      city_name: null,
      district: "Ba Đình"
    },
    items: [],
    createdAt: ISODate("2026-11-20T06:00:00Z")
  },
  {
    _id: "ord-004",
    tenantId: "tenant-b",
    status: "PAID",
    items: [
      { sku_code: "BOOK-C", quantity: 2, unitPriceVnd: NumberLong("50000") }
    ],
    createdAt: ISODate("2026-11-20T07:00:00Z")
  }
]);
```

Đây là dữ liệu minh họa cho collection test. Không chạy `insertMany` trên dữ liệu production khi chưa xác minh ID và ràng buộc hiện có.

```text
orders / document ord-001
├── _id: "ord-001"
├── tenantId: "tenant-a"
├── status: "PAID"
├── ship_to: {...}
│   ├── city_name: "Hà Nội"
│   ├── district: "Cầu Giấy"
│   └── street: "Xuân Thủy"
└── items: [...]
    ├── [0]
    │   ├── sku_code: "BOOK-A"
    │   ├── quantity: 1
    │   └── unitPriceVnd: 90000
    └── [1]
        ├── sku_code: "BOOK-B"
        ├── quantity: 4
        └── unitPriceVnd: 60000
```

### 2.2. Entity Java với tên property khác tên BSON

Để thấy rõ vai trò của mapping, dùng các kiểu Java 17+:

```java
import java.time.Instant;
import java.util.List;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders")
public record OrderDocument(
    @MongoId(FieldType.STRING) String id,
    String tenantId,
    String status,
    @Field("ship_to") ShippingAddress shippingAddress,
    List<OrderLine> items,
    Instant createdAt
) {}

record ShippingAddress(
    @Field("city_name") String city,
    String district,
    String street
) {}

record OrderLine(
    @Field("sku_code") String sku,
    int quantity,
    long unitPriceVnd
) {}
```

Với model trên:

| Property Java | Đường dẫn BSON |
| --- | --- |
| `id` | `_id` |
| `shippingAddress` | `ship_to` |
| `shippingAddress.city` | `ship_to.city_name` |
| `shippingAddress.district` | `ship_to.district` |
| `items` | `items` |
| `items.sku` | `items.sku_code` |
| `items.quantity` | `items.quantity` |

**Quy tắc:** Trong mongosh hoặc khi gọi MongoDB driver trực tiếp, dùng **tên field BSON**. Khi tạo `Query`/`Criteria` với entity class trong Spring Data, thường dùng **đường dẫn property Java** để mapper chuyển thành đường dẫn BSON. Tránh trộn lẫn hai quy ước một cách ngẫu nhiên.

## 3. Dot notation là gì?

### 3.1. Đọc một trường ở cấp sâu hơn

Một đường dẫn như `ship_to.city_name` có hai thành phần:

```text
ship_to.city_name
   │        │
   │        └── field con trong document nhúng
   └─────────── field ở document cha
```

Trong mongosh:

```javascript
db.orders.find({
  tenantId: "tenant-a",
  "ship_to.city_name": "Hà Nội"
});
```

Truy vấn này trả `ord-001`, vì `ship_to.city_name` là chuỗi `"Hà Nội"`. Dot notation là **đường dẫn field**, không phải dấu chấm cú pháp của một object Java; cần đặt path có dấu chấm trong dấu nháy khi viết object literal JavaScript.

Có thể đi sâu hơn qua nhiều cấp nếu schema chứa các document lồng nhau:

```javascript
// Ví dụ nếu một schema khác có:
// delivery: { recipient: { contact: { phone: "..." } } }
db.orders.find({
  "delivery.recipient.contact.phone": "0900000000"
});
```

Đường dẫn trong ví dụ thứ hai chỉ áp dụng nếu document thật có cấu trúc tương ứng; nó không có trong dữ liệu mẫu ở mục 2.

### 3.2. So khớp cả subdocument khác so khớp một trường con

Hai truy vấn sau **không tương đương**:

```javascript
// Chỉ quan tâm tới thành phố:
db.orders.find({ "ship_to.city_name": "Hà Nội" });

// So khớp toàn bộ subdocument:
db.orders.find({
  ship_to: {
    city_name: "Hà Nội",
    district: "Cầu Giấy",
    street: "Xuân Thủy"
  }
});
```

Query thứ hai yêu cầu toàn bộ BSON subdocument khớp theo hình dạng và giá trị được chỉ định, bao gồm thứ tự field trong so khớp document nhúng theo equality. Nếu document `ship_to` có thêm field, thiếu field hoặc khác thứ tự lưu, kết quả có thể khác. Khi chỉ cần một hoặc vài thuộc tính, **truy vấn theo dot notation thường rõ và ít bị ràng buộc bởi toàn bộ cấu trúc**.

### 3.3. Kết hợp nhiều trường con bằng AND

```javascript
db.orders.find({
  tenantId: "tenant-a",
  "ship_to.city_name": "Hà Nội",
  "ship_to.district": "Cầu Giấy"
});
```

Đối với **một subdocument thông thường** như `ship_to`, cả hai điều kiện cùng áp dụng lên các trường con của document đó. Nhưng khi đi vào **array of documents**, nhiều điều kiện có thể khớp các phần tử khác nhau; đây là khác biệt quan trọng ở mục 5.

## 4. Query và Criteria cho document nhúng

### 4.1. MongoTemplate với property path Java

```java
import java.util.List;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public class OrderQueryService {
    private final MongoOperations mongo;

    public OrderQueryService(MongoOperations mongo) {
        this.mongo = mongo;
    }

    public List<OrderDocument> findByShippingCity(
        String authenticatedTenantId,
        String city
    ) {
        Query query = Query.query(
            Criteria.where("tenantId").is(authenticatedTenantId)
                .and("shippingAddress.city").is(city)
        );
        query.limit(50);
        return mongo.find(query, OrderDocument.class);
    }
}
```

Với `OrderDocument.class`, Spring Data dùng metadata mapping để chuyển property path `shippingAddress.city` thành field path BSON `ship_to.city_name`. Phương thức giới hạn tối đa 50 kết quả nhằm tránh vô tình tải quá nhiều document; trong API production, nên bổ sung sort ổn định và phân trang theo yêu cầu.

Đường dẫn `shippingAddress.city` không bắt buộc Java phải có một method tên như vậy. Nó là **property path** mà Spring Data ánh xạ dựa trên entity và các kiểu lồng nhau.

### 4.2. Đối chiếu Criteria với MongoDB filter

```java
Query query = Query.query(
    Criteria.where("tenantId").is("tenant-a")
        .and("shippingAddress.city").is("Hà Nội")
);
```

Ý nghĩa BSON dự kiến:

```javascript
{
  tenantId: "tenant-a",
  "ship_to.city_name": "Hà Nội"
}
```

**Lưu ý:** `query.getQueryObject()` có thể hiển thị cấu trúc query trước khi map sang tên field vật lý. Để xác nhận BSON thực sự được gửi, dùng integration test, command monitoring hoặc kiểm tra qua công cụ phù hợp. Không nên chỉ nhìn String do `Query.toString()` tạo ra rồi kết luận annotation `@Field` đã/không được áp dụng.

### 4.3. Nhiều nhánh OR

Ví dụ cần tìm đơn thuộc tenant đang đăng nhập và giao đến Hà Nội **hoặc** Đà Nẵng:

```java
Criteria cityCondition = new Criteria().orOperator(
    Criteria.where("shippingAddress.city").is("Hà Nội"),
    Criteria.where("shippingAddress.city").is("Đà Nẵng")
);

Query query = Query.query(
    new Criteria().andOperator(
        Criteria.where("tenantId").is(authenticatedTenantId),
        cityCondition
    )
);
```

Có thể dùng `in("Hà Nội", "Đà Nẵng")` cho trường hợp đơn giản này:

```java
Query simpler = Query.query(
    Criteria.where("tenantId").is(authenticatedTenantId)
        .and("shippingAddress.city").in("Hà Nội", "Đà Nẵng")
);
```

Ưu tiên biểu thức đơn giản, dễ đọc. Khi có `$or` phức tạp, nhớ giữ điều kiện tenant bên ngoài, tránh nhánh OR vô tình bỏ qua ràng buộc quyền truy cập.

## 5. Dot notation khi đường dẫn đi qua array

### 5.1. Tìm document có ít nhất một phần tử thỏa điều kiện

Trong `ord-001`, `items` là một array of documents. MongoDB cho phép:

```javascript
db.orders.find({
  tenantId: "tenant-a",
  "items.sku_code": "BOOK-A"
});
```

Query này khớp nếu **có ít nhất một phần tử** trong `items` có `sku_code` bằng `"BOOK-A"`. Với dataset ở mục 2, `ord-001` và `ord-002` đều phù hợp.

Trong Spring Data:

```java
Query query = Query.query(
    Criteria.where("tenantId").is("tenant-a")
        .and("items.sku").is("BOOK-A")
);
var matched = mongo.find(query, OrderDocument.class);
```

Do `OrderLine.sku` được gắn `@Field("sku_code")`, property path `items.sku` tương ứng đường dẫn lưu trữ `items.sku_code`.

### 5.2. Hai điều kiện có thể khớp hai phần tử khác nhau

Xét document `ord-001`:

```javascript
items: [
  { sku_code: "BOOK-A", quantity: 1 },
  { sku_code: "BOOK-B", quantity: 4 }
]
```

Truy vấn:

```javascript
db.orders.find({
  _id: "ord-001",
  "items.sku_code": "BOOK-A",
  "items.quantity": { $gte: 3 }
});
```

**Vẫn khớp `ord-001`**, vì điều kiện SKU được thỏa bởi phần tử đầu, còn điều kiện số lượng được thỏa bởi phần tử thứ hai. Khi dùng nhiều predicate qua array, MongoDB **không mặc định yêu cầu các predicate cùng đúng trên một phần tử**.

Đây là lỗi logic nghiêm trọng nếu nghiệp vụ muốn «đơn có ít nhất một dòng BOOK-A với số lượng từ 3 trở lên». Dùng `$elemMatch` để liên kết các điều kiện vào cùng một phần tử.

### 5.3. $elemMatch: các điều kiện trên cùng một phần tử

```javascript
db.orders.find({
  tenantId: "tenant-a",
  items: {
    $elemMatch: {
      sku_code: "BOOK-A",
      quantity: { $gte: 3 }
    }
  }
});
```

Kết quả từ dữ liệu mẫu chỉ gồm `ord-002`: phần tử `BOOK-A` của đơn đó có `quantity = 3`. `ord-001` không khớp vì dòng `BOOK-A` chỉ có số lượng 1.

Hình dung:

```text
ord-001:
  items[0] -> sku=BOOK-A  ✓, quantity>=3 ✗
  items[1] -> sku=BOOK-B  ✗, quantity>=3 ✓
  Không có cùng một phần tử thỏa cả hai.

ord-002:
  items[0] -> sku=BOOK-A  ✓, quantity>=3 ✓
  Có một phần tử thỏa cả hai.
```

**Quy tắc nhớ:** Khi các điều kiện phải áp dụng cho cùng một object trong array, dùng `$elemMatch` ở **trường array bao ngoài**.

### 5.4. $elemMatch trong Criteria

```java
Criteria sameLine = Criteria.where("sku").is("BOOK-A")
    .and("quantity").gte(3);

Query query = Query.query(
    Criteria.where("tenantId").is(authenticatedTenantId)
        .and("items").elemMatch(sameLine)
);

List<OrderDocument> orders = mongo.find(
    query, OrderDocument.class
);
```

Ý định của query là:

```javascript
{
  tenantId: "tenant-a",
  items: {
    $elemMatch: {
      sku_code: "BOOK-A",
      quantity: { $gte: 3 }
    }
  }
}
```

Việc ánh xạ property path bên trong `$elemMatch` phụ thuộc metadata của phần tử array và implementation QueryMapper của phiên bản đang dùng. Hãy kiểm tra BSON được gửi bằng integration test, đặc biệt khi nested entity có `@Field` hoặc custom conversion. Với API driver hoặc mongosh, luôn dùng tên vật lý `sku_code`.

### 5.5. Đọc phần tử theo vị trí

Khi cần kiểm tra **phần tử đầu tiên**, MongoDB có thể dùng vị trí array:

```javascript
db.orders.find({
  "items.0.sku_code": "BOOK-A"
});
```

Đường dẫn `items.0.sku_code` có ý nghĩa rất khác `items.sku_code`: nó chỉ kiểm tra phần tử có chỉ số 0. Chỉ sử dụng nếu thứ tự array là một phần của hợp đồng dữ liệu. Đối với mảng dòng hàng, thứ tự có thể đổi khi người dùng sửa giỏ hoặc khi import dữ liệu; việc dùng index vị trí cố định thường không phù hợp cho tìm kiếm nghiệp vụ.

## 6. Phân biệt document nhúng, array và document tham chiếu

Dot notation chỉ đi vào **cấu trúc BSON thật đang nằm trong document được truy vấn**.

### 6.1. Embedded document

```javascript
{
  _id: "ord-001",
  ship_to: { city_name: "Hà Nội" }
}
```

Truy vấn `"ship_to.city_name"` có ý nghĩa vì `ship_to` thực sự là document nhúng.

### 6.2. Tham chiếu chỉ lưu ID

Nếu thay địa chỉ thành một tham chiếu:

```javascript
// orders:
{ _id: "ord-001", shippingAddressId: "addr-001" }

// addresses:
{ _id: "addr-001", city_name: "Hà Nội" }
```

Truy vấn `"shippingAddressId.city_name"` **không tìm được tên thành phố trong collection addresses**. Field `shippingAddressId` chỉ chứa String ID, không phải document nhúng.

Tương tự, `@DocumentReference` mặc định có thể ánh xạ property Java thành object khi đọc, nhưng thường lưu giá trị tham chiếu ID trong BSON. MongoDB `find` không tự join các collection. Muốn lọc theo địa chỉ trong collection khác, cân nhắc `$lookup`, truy vấn hai bước hoặc denormalization hợp lý.

### 6.3. Chọn embed hay reference từ access pattern

| Nhu cầu | Mô hình thường phù hợp |
| --- | --- |
| Địa chỉ giao hàng phải được giữ như snapshot tại thời điểm đặt | Embedded `ship_to` |
| Nhiều đơn cần trỏ đến thông tin khách hàng hiện hành | Reference ID, có thể lưu thêm snapshot cần thiết |
| Tìm đơn theo thành phố thường xuyên | Có field thành phố trong orders và index phù hợp |
| Thông tin liên kết thay đổi liên tục, kích thước lớn | Reference hoặc projection/collection chuyên biệt |

Không nên biến mọi mối quan hệ thành document nhúng chỉ để có thể dùng dot notation. Kích thước document, tần suất thay đổi và cardinality là yếu tố quyết định.

## 7. Null, missing và đường dẫn lồng nhau

Ở dữ liệu mẫu:

- `ord-001` có `ship_to.city_name = "Hà Nội"`.
- `ord-003` có `ship_to.city_name = null`.
- `ord-004` **không có field `ship_to`**.

### 7.1. Tìm trường con bằng Null

```javascript
db.orders.find({ "ship_to.city_name": null });
```

Trong MongoDB, equality với `null` theo cú pháp này thường khớp **cả field có BSON Null và field không tồn tại**. Vì vậy, `ord-003` và `ord-004` đều phù hợp. Không nên dùng filter này nếu nghiệp vụ muốn phân biệt «đã ghi null» và «chưa từng có địa chỉ».

### 7.2. Tìm field con tồn tại hoặc không tồn tại

```javascript
// Có đường dẫn ship_to.city_name, kể cả khi giá trị là null.
db.orders.find({
  "ship_to.city_name": { $exists: true }
});

// Đường dẫn ship_to.city_name không tồn tại.
db.orders.find({
  "ship_to.city_name": { $exists: false }
});
```

Khi document cha `ship_to` không tồn tại, đường dẫn con `ship_to.city_name` cũng được coi là missing. Nhưng nếu `ship_to.city_name` tồn tại và chứa null, `$exists: true` vẫn khớp.

### 7.3. Tìm BSON Null tường minh

```javascript
db.orders.find({
  "ship_to.city_name": { $type: "null" }
});
```

Với cấu trúc một subdocument như `ship_to`, điều kiện trên tìm những document có field con kiểu BSON Null, không đồng nhất với missing. Trường hợp field cha hoặc đường dẫn đi qua array phức tạp cần test với BSON thực tế để tránh suy luận quá mức.

### 7.4. Criteria.exists(...) và kiểm tra chính xác

```java
Query missingCity = Query.query(
    Criteria.where("tenantId").is(authenticatedTenantId)
        .and("shippingAddress.city").exists(false)
);
```

Tương tự mongosh, `exists(false)` kiểm tra field con không tồn tại; không có nghĩa «chuỗi rỗng», «Null» hoặc «địa chỉ không hợp lệ». Nếu nghiệp vụ cần phân biệt những trạng thái đó, thiết kế validation và migration dữ liệu thích hợp.

## 8. Query dẫn xuất trong MongoRepository cho property lồng nhau

### 8.1. Derived query theo đường dẫn property

Spring Data có thể phân tích đường dẫn property trong tên method:

```java
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.repository.Repository;

public interface OrderSearchRepository
    extends Repository<OrderDocument, String> {

    Slice<OrderDocument> findByTenantIdAndShippingAddress_City(
        String tenantId,
        String city,
        Pageable pageable
    );
}
```

Dấu gạch dưới `_` trong `ShippingAddress_City` giúp chỉ rõ điểm tách property path: `shippingAddress.city`. Đây là đường dẫn **Java model**, không phải tên field BSON `ship_to.city_name`. Spring Data mapping có thể áp dụng `@Field` để truy vấn đúng dữ liệu lưu trữ.

Gọi repository:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

var page = repository.findByTenantIdAndShippingAddress_City(
    authenticatedTenantId,
    "Hà Nội",
    PageRequest.of(
        0,
        20,
        Sort.by(Sort.Order.desc("createdAt"), Sort.Order.desc("id"))
    )
);
```

Ở đây `repository` là bean `OrderSearchRepository` do Spring inject. Dùng `Slice` để có `hasNext()` mà không bắt buộc tính tổng số trang; offset sâu vẫn có thể tốn chi phí.

### 8.2. Đừng đặt tên method mơ hồ

Giả sử entity sau này có cả property `shippingAddressCity` và object `shippingAddress.city`, một method như `findByShippingAddressCity` có thể gây nhầm trong quá trình parse property path. Dùng dấu phân tách `_` khi cần thể hiện rõ nested path, đồng thời đặt tên model tránh xung đột khó đọc.

Không có nghĩa query dẫn xuất luôn ưu việt hơn `@Query`. Với điều kiện nested array phức tạp, `$elemMatch` và nhiều tổ hợp AND/OR, `MongoTemplate` hoặc JSON query minh bạch thường dễ review hơn.

### 8.3. @Query với đường dẫn BSON

Khi muốn biểu diễn filter dưới dạng JSON trong repository:

```java
import java.util.List;
import org.springframework.data.mongodb.repository.Query;

public interface OrderJsonQueryRepository
    extends Repository<OrderDocument, String> {

    @Query("{ 'tenantId': ?0, 'ship_to.city_name': ?1 }")
    List<OrderDocument> findByStoredCity(
        String tenantId,
        String city
    );
}
```

Ở đây query viết theo **đường dẫn BSON thực tế**. `?0` và `?1` được Spring Data bind theo tham số; không tự ghép String JSON từ đầu vào người dùng. Lưu ý method trả `List` không có giới hạn; ứng dụng production nên dùng `Pageable`/`Slice` hoặc một giới hạn rõ ràng tùy nhu cầu.

Trong một số API, Spring Data còn thực hiện mapping tên field cho query JSON. Để tránh nhầm khi vừa sử dụng alias `@Field` vừa viết JSON thủ công, luôn kiểm tra query thật và thống nhất cách diễn đạt trong repository.

## 9. Projection và sort trên nested path

### 9.1. Projection chỉ lấy các trường cần thiết

MongoDB cho phép chỉ lấy một trường con:

```javascript
db.orders.find(
  { tenantId: "tenant-a" },
  {
    "ship_to.city_name": 1,
    status: 1
  }
);
```

Kết quả BSON thường vẫn giữ cấu trúc lồng nhau, ví dụ:

```javascript
{
  _id: "ord-001",
  status: "PAID",
  ship_to: { city_name: "Hà Nội" }
}
```

Muốn loại `_id` khỏi projection MongoDB, chỉ định `_id: 0`. Projection này không tự làm document `ship_to` có đủ mọi field ban đầu; nếu map vào entity với các field bắt buộc, cần xem hành vi constructor/defaults. Với API danh sách, DTO/projection thiết kế riêng thường phù hợp hơn đọc một entity thiếu dữ liệu rồi vô tình gọi `save`.

### 9.2. Projection qua Query.fields()

```java
Query query = Query.query(
    Criteria.where("tenantId").is(authenticatedTenantId)
);
query.fields()
    .include("shippingAddress.city")
    .include("status");
query.limit(20);
```

Khi query chạy trên `OrderDocument.class`, property path có thể được mapper đổi thành `ship_to.city_name`. Cần xác nhận BSON thực tế, đặc biệt nếu kết quả map sang DTO thay vì domain entity.

### 9.3. Sort theo trường con

```javascript
db.orders.find({ tenantId: "tenant-a" })
  .sort({ "ship_to.city_name": 1, _id: 1 });
```

Trong Spring Data:

```java
import org.springframework.data.domain.Sort;

query.with(Sort.by(
    Sort.Order.asc("shippingAddress.city"),
    Sort.Order.asc("id")
));
```

Sort theo `shippingAddress.city` đi qua metadata khi có domain type. Nếu dữ liệu chứa `null`, missing hoặc loại BSON không nhất quán, thứ tự có thể khác yêu cầu nghiệp vụ. Nếu muốn thứ tự tên thành phố theo quy tắc tiếng Việt, xem xét `Collation` phù hợp **và index có cùng collation**.

## 10. Index cho đường dẫn document nhúng

### 10.1. Compound index theo tenant và thành phố

Nếu thường tìm đơn của một tenant theo thành phố:

```javascript
db.orders.createIndex(
  { tenantId: 1, "ship_to.city_name": 1 },
  { name: "ix_orders_tenant_ship_city" }
);
```

Index này phù hợp một nhóm query equality theo `tenantId` và `ship_to.city_name`. MongoDB có thể dùng index để hạn chế số document cần duyệt; không bảo đảm index này luôn được chọn nếu tập dữ liệu nhỏ hoặc có index khác hiệu quả hơn.

### 10.2. Chọn index theo filter và sort

Nếu nghiệp vụ cần tìm các đơn giao Hà Nội mới nhất:

```javascript
db.orders.find({
  tenantId: "tenant-a",
  "ship_to.city_name": "Hà Nội"
})
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);
```

Một ứng viên compound index:

```javascript
db.orders.createIndex(
  {
    tenantId: 1,
    "ship_to.city_name": 1,
    createdAt: -1,
    _id: -1
  },
  { name: "ix_orders_tenant_city_recent" }
);
```

Hai field đầu lọc equality, các field sau hỗ trợ thứ tự sắp xếp. Cần kiểm tra query thực tế bằng `explain("executionStats")` và đo trên dữ liệu đại diện. Không tạo nhiều index gần giống nhau mà không xét chi phí ghi và lưu trữ.

### 10.3. Index không áp đặt schema hay quyền

Index trên `ship_to.city_name` không bảo đảm document luôn chứa `ship_to` hoặc `city_name`, không kiểm tra thành phố có hợp lệ và không tự ràng buộc tenant. Những yêu cầu này cần validation ở tầng ứng dụng và/hoặc MongoDB schema validation, cùng kiểm thử phân quyền.

## 11. Multikey index cho array of documents

### 11.1. Index trên items.sku_code

Khi index một field lấy giá trị qua array, MongoDB có thể tạo **multikey index**:

```javascript
db.orders.createIndex(
  { tenantId: 1, "items.sku_code": 1 },
  { name: "ix_orders_tenant_item_sku" }
);
```

Với `ord-001`, array có hai dòng nên index có thể có các entry tương ứng cho hai giá trị SKU. Điều này giúp truy vấn:

```javascript
db.orders.find({
  tenantId: "tenant-a",
  "items.sku_code": "BOOK-A"
});
```

Tuy nhiên, index multikey có chi phí lưu trữ và cập nhật khi array thay đổi; mảng lớn hoặc nhiều giá trị trùng có thể ảnh hưởng hiệu năng.

### 11.2. $elemMatch và compound multikey index

Nếu thường tìm dòng hàng theo cả SKU và số lượng:

```javascript
db.orders.find({
  tenantId: "tenant-a",
  items: {
    $elemMatch: {
      sku_code: "BOOK-A",
      quantity: { $gte: 3 }
    }
  }
});
```

Một index cần đánh giá:

```javascript
db.orders.createIndex(
  {
    tenantId: 1,
    "items.sku_code": 1,
    "items.quantity": 1
  },
  { name: "ix_orders_tenant_item_sku_qty" }
);
```

Với các điều kiện trên **cùng một phần tử array** qua `$elemMatch`, query planner có thể tận dụng các bound của compound multikey index phù hợp tốt hơn so với các điều kiện độc lập có thể khớp nhiều phần tử.

**Giới hạn cần nhớ:** Không phải compound index nào có nhiều field array cũng hợp lệ. MongoDB có những ràng buộc đối với compound multikey index và việc index các array độc lập. Index ví dụ ở trên đi qua các field của **cùng array `items`**; nếu thiết kế thêm một field array độc lập khác, phải xem lại tính hợp lệ và lợi ích của index.

### 11.3. Dùng explain để phân biệt sai query và index kém

```javascript
db.orders.find({
  tenantId: "tenant-a",
  items: {
    $elemMatch: {
      sku_code: "BOOK-A",
      quantity: { $gte: 3 }
    }
  }
}).explain("executionStats");
```

Quan sát `winningPlan`, `IXSCAN` hoặc `COLLSCAN`, `totalKeysExamined`, `totalDocsExamined` và `nReturned`. Nếu query không trả `ord-001`, đó là **kết quả đúng về logic `$elemMatch`**, không phải lỗi index. Đừng bỏ `$elemMatch` chỉ để thấy nhiều kết quả hơn.

## 12. Cập nhật trường lồng nhau bằng dot notation

Dot notation không chỉ phục vụ đọc. MongoDB cho phép cập nhật một trường con trong subdocument bằng `$set`.

### 12.1. Sửa thành phố, giữ lại quận và đường

```javascript
db.orders.updateOne(
  { _id: "ord-001", tenantId: "tenant-a" },
  { $set: { "ship_to.city_name": "Hải Phòng" } }
);
```

Sau lệnh này, những trường `ship_to.district` và `ship_to.street` vẫn được giữ nguyên.

Ngược lại:

```javascript
db.orders.updateOne(
  { _id: "ord-001", tenantId: "tenant-a" },
  { $set: { ship_to: { city_name: "Hải Phòng" } } }
);
```

Lệnh thứ hai **thay toàn bộ giá trị `ship_to`** bằng subdocument mới, khiến `district` và `street` bị mất nếu trước đó tồn tại. Hai phép update này không tương đương.

### 12.2. Update qua MongoTemplate

```java
import org.springframework.data.mongodb.core.query.Update;

Query query = Query.query(
    Criteria.where("id").is("ord-001")
        .and("tenantId").is(authenticatedTenantId)
);

Update update = new Update()
    .set("shippingAddress.city", "Hải Phòng");

var result = mongo.updateFirst(
    query, update, OrderDocument.class
);
```

Trong context `OrderDocument.class`, Spring Data có thể ánh xạ đường dẫn property `shippingAddress.city` sang BSON `ship_to.city_name`. Với dữ liệu sản xuất, luôn xác minh rằng phần Update được mapper xử lý đúng theo alias `@Field`.

Lệnh MongoDB trên một document là nguyên tử. Tuy vậy, nếu cần bảo đảm quyền chỉnh sửa địa chỉ theo trạng thái đơn hoặc version hiện tại, hãy đặt điều kiện nghiệp vụ phù hợp ngay trong filter, không chỉ kiểm tra từ một lần đọc trước đó.

### 12.3. Cập nhật một phần tử array có điều kiện

Khi muốn sửa dòng `BOOK-A` mà không sửa dòng `BOOK-B`, có thể dùng filtered positional operator `$[line]` và `arrayFilters`:

```javascript
db.orders.updateOne(
  {
    _id: "ord-001",
    tenantId: "tenant-a"
  },
  { $set: { "items.$[line].quantity": 3 } },
  {
    arrayFilters: [
      { "line.sku_code": "BOOK-A" }
    ]
  }
);
```

Mỗi phần tử `items` thỏa điều kiện của `line` có thể được cập nhật. Đây là hành vi khác với toán tử positional `$` chỉ gắn với phần tử được chọn bởi điều kiện query trong những thao tác phù hợp.

Với Spring Data MongoDB có hỗ trợ `Update.filterArray(...)`:

```java
Update update = new Update()
    .set("items.$[line].quantity", 3)
    .filterArray(
        Criteria.where("line.sku_code").is("BOOK-A")
    );

Query query = Query.query(
    Criteria.where("id").is("ord-001")
        .and("tenantId").is(authenticatedTenantId)
);

mongo.updateFirst(query, update, OrderDocument.class);
```

**Quan trọng:** Điều kiện của `arrayFilters` có thể được truyền xuống driver mà **không qua cùng cơ chế ánh xạ tên field** như Criteria gắn với entity. Vì vậy, trong filter dùng tên BSON thực tế `line.sku_code`, không giả định `line.sku` sẽ tự đổi theo `@Field`. Hãy kiểm tra phiên bản API và BSON update trong integration test.

### 12.4. Thận trọng với update path không hợp lệ

Nếu `ship_to` không tồn tại hoặc không phải document đúng schema, một lệnh cập nhật `ship_to.city_name` có thể tạo object lồng nhau hoặc thất bại tùy trạng thái dữ liệu. Không nên xem dot notation là cách tự sửa mọi dữ liệu sai cấu trúc. Phải có validation và migration khi dữ liệu cũ chứa field cha khác kiểu.

## 13. Aggregation và $lookup dùng đường dẫn BSON

Dot notation cũng xuất hiện trong aggregation:

```javascript
db.orders.aggregate([
  { $match: {
      tenantId: "tenant-a",
      "ship_to.city_name": "Hà Nội"
  }},
  { $unwind: "$items" },
  { $group: {
      _id: "$items.sku_code",
      orderedQuantity: { $sum: "$items.quantity" }
  }},
  { $sort: { orderedQuantity: -1 } }
]);
```

Pipeline trên:

1. Lọc đơn thuộc tenant và thành phố.
2. Dùng `$unwind` tách các phần tử của array `items`.
3. Nhóm theo SKU của **mỗi phần tử đã unwind**.
4. Cộng tổng số lượng để tạo báo cáo.

Điều này minh họa rằng `"$items.sku_code"` trong **aggregation expression** có ngữ nghĩa truy xuất giá trị khác với tên field filter trong `find`. Dấu `$` dùng cho biểu thức tham chiếu đến đường dẫn; trong filter JSON `{ "items.sku_code": "BOOK-A" }` không cần dấu `$`.

Nếu dữ liệu thực lưu reference ID thay vì embedded object, `$lookup` có thể được dùng để kết hợp collection thích hợp; dot notation tự nó không thực hiện join.

## 14. Query đúng và an toàn trong hệ thống nhiều tenant

### 14.1. Không nhận field path tùy ý từ client

Một UI cho phép lọc đơn theo thành phố, trạng thái và SKU. Không nên nhận nguyên một chuỗi như `fieldPath = "items.0.unitPriceVnd"` rồi truyền thẳng vào:

```java
// Không an toàn khi fieldPath do client tự chọn mà chưa kiểm soát.
Criteria.where(fieldPath).is(value);
```

Điều này có thể làm lộ cấu trúc nội bộ, tạo query khó kiểm soát hoặc gây tải lớn. Thay vào đó, ánh xạ tập tùy chọn hợp lệ thành property path đã duyệt:

```java
String field = switch (filterName) {
    case "city" -> "shippingAddress.city";
    case "sku" -> "items.sku";
    case "status" -> "status";
    default -> throw new IllegalArgumentException("Unsupported filter");
};

Query query = Query.query(
    Criteria.where("tenantId").is(authenticatedTenantId)
        .and(field).is(value)
);
```

Đoạn code minh họa cách whitelist field; `filterName`/`value` phải được validate và chuyển đúng kiểu trước khi dùng trong ứng dụng thật. Với nhiều điều kiện thuộc cùng một array element, không ghép chung bằng `and("items.quantity")` mà quên `$elemMatch`.

### 14.2. Kết hợp điều kiện tenant với nested path

Một query chỉ theo `"ship_to.city_name"` có thể tìm cả đơn thuộc tenant khác. Với hệ thống nhiều tenant, dùng:

```javascript
db.orders.find({
  tenantId: "tenant-a",
  "ship_to.city_name": "Hà Nội"
});
```

Tham số tenant phải xuất phát từ security context hoặc logic authorization đáng tin cậy. Việc query có field `tenantId` **không tự xác thực** giá trị được truyền vào.

### 14.3. Không trộn logic AND/OR làm mất điều kiện bắt buộc

Ví dụ sau nguy hiểm khi developer muốn «tenant-a và (Hà Nội hoặc Đà Nẵng)»:

```javascript
// Sai nếu yêu cầu mọi kết quả đều phải thuộc tenant-a:
db.orders.find({
  $or: [
    { tenantId: "tenant-a", "ship_to.city_name": "Hà Nội" },
    { "ship_to.city_name": "Đà Nẵng" }
  ]
});
```

Nhánh thứ hai không ràng buộc tenant. Viết đúng:

```javascript
db.orders.find({
  tenantId: "tenant-a",
  "ship_to.city_name": { $in: ["Hà Nội", "Đà Nẵng"] }
});
```

Với logic nhiều nhánh hơn, đặt tenant ở cấp cao nhất và kiểm tra filter BSON thực tế. Không có index hoặc annotation nào có thể bù cho điều kiện quyền bị viết sai.

## 15. Kiểm thử mapping và điều kiện array

### 15.1. Ma trận kiểm thử tối thiểu

| Test | Kết quả mong đợi |
| --- | --- |
| Tìm `shippingAddress.city = "Hà Nội"` trong tenant-a | Khớp `ord-001` |
| Tìm cùng thành phố nhưng tenant khác | Không trả `ord-001` |
| Tìm `items.sku = "BOOK-A"` | Khớp `ord-001` và `ord-002` trong tenant-a |
| Hai điều kiện độc lập `items.sku=BOOK-A` và `items.quantity>=3` | Có thể khớp `ord-001` vì hai phần tử khác nhau |
| Dùng `$elemMatch` cho BOOK-A và quantity>=3 | Chỉ `ord-002` |
| Tìm `ship_to.city_name: null` | Khớp Null và missing theo semantics của MongoDB |
| `$exists: false` trên thành phố | Khớp document thiếu đường dẫn con |
| `$type: "null"` trên thành phố | Chỉ nhóm có BSON Null tại field con |
| Update `shippingAddress.city` | Quận/đường cũ vẫn giữ |
| Thay toàn bộ `shippingAddress` | Các field không có trong object mới có thể mất |
| Update arrayFilter theo BOOK-A | Không sửa dòng BOOK-B |
| Index trên nested path | Query đúng và plan được quan sát |

### 15.2. Test MongoTemplate với database

Khung minh họa JUnit 5, giả định test context đã inject `MongoOperations` và có cơ sở dữ liệu MongoDB test riêng:

```java
import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

class NestedPathIntegrationTest {
    MongoOperations mongo; // Inject từ test context thực tế.

    @Test
    void nestedPathAndElemMatchMustDiffer() {
        Query independent = Query.query(
            Criteria.where("tenantId").is("tenant-a")
                .and("items.sku").is("BOOK-A")
                .and("items.quantity").gte(3)
        );
        List<OrderDocument> broad = mongo.find(
            independent, OrderDocument.class
        );

        Query sameElement = Query.query(
            Criteria.where("tenantId").is("tenant-a")
                .and("items").elemMatch(
                    Criteria.where("sku").is("BOOK-A")
                        .and("quantity").gte(3)
                )
        );
        List<OrderDocument> strict = mongo.find(
            sameElement, OrderDocument.class
        );

        assertTrue(broad.stream()
            .anyMatch(order -> order.id().equals("ord-001")));
        assertFalse(strict.stream()
            .anyMatch(order -> order.id().equals("ord-001")));
        assertTrue(strict.stream()
            .anyMatch(order -> order.id().equals("ord-002")));
    }
}
```

Đây là **khung test**, không phải class chạy độc lập: cần cấu hình test context, dependency, injection, seed fixture, cleanup dữ liệu và lựa chọn MongoDB test phù hợp. Khi kiểm thử đầy đủ, assert cả danh sách ID chính xác, kiểu BSON, quyền tenant và query thực tế được gửi.

### 15.3. Xác minh đường dẫn do @Field đổi tên

Khi test, đừng chỉ so object Java sau khi đọc. Kiểm tra document vật lý:

```javascript
db.orders.findOne(
  { _id: "ord-001" },
  { ship_to: 1, items: 1 }
);
```

Xác nhận `ship_to.city_name`, `items.sku_code` đúng như metadata. Một integration test có thể dùng `MongoTemplate.find(query, org.bson.Document.class, "orders")` để quan sát BSON mà không map sang domain entity, rồi so với kết quả truy vấn bằng `OrderDocument.class`.

### 15.4. Đo performance sau khi xác minh logic

Chạy:

```javascript
db.orders.find({
  tenantId: "tenant-a",
  "ship_to.city_name": "Hà Nội"
})
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats");
```

Xem `winningPlan`, `IXSCAN`/`COLLSCAN`, `totalKeysExamined`, `totalDocsExamined`, `nReturned` và stage sort. Nếu query thiếu document vì sai cách dùng `$elemMatch`, index không thể sửa lỗi logic. Nếu kết quả đúng nhưng chậm, mới đánh giá compound/multikey index theo workload.

## 16. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra hoặc khắc phục |
| --- | --- | --- |
| `Criteria.where("ship_to.city_name")` không ra kết quả như mong đợi | Trộn tên BSON với property path Java, mapping khác dự kiến | Kiểm tra `@Field` và query BSON đã gửi |
| Truy vấn `shippingAddress.city` trong mongosh không thấy gì | MongoDB chỉ biết field vật lý `ship_to.city_name` | Dùng tên BSON trong mongosh |
| Query `ship_to.city_name` khớp nhưng object nhúng equality không khớp | Subdocument thiếu/thừa field hoặc field order khác | Dùng dot notation nếu chỉ cần một số field |
| Điều kiện SKU và quantity khớp đơn sai | Hai predicate đi qua array, thỏa ở các phần tử khác nhau | Dùng `$elemMatch` |
| Query `items.0.sku_code` thiếu đơn | Chỉ kiểm tra phần tử đầu array | Dùng `items.sku_code` hoặc `$elemMatch` theo nghiệp vụ |
| Query thành phố null trả cả đơn không có địa chỉ | `{field: null}` bao gồm missing | Dùng `$type: "null"` hoặc `$exists` |
| Update thành phố làm mất district/street | `$set` toàn subdocument `ship_to` | `$set` đúng đường dẫn con |
| Array filter không khớp khi dùng `sku` | Filter chưa được mapping sang `sku_code` | Dùng field BSON trong `arrayFilters` và test |
| Truy vấn trên `shippingAddressId.city` sai | Field là reference ID, không phải document nhúng | Query collection đích hoặc `$lookup` |
| Index nested path không làm query nhanh | Key order/sort/collation không phù hợp hoặc dữ liệu ít | Kiểm tra plan thực tế |
| Data leak cross-tenant | Một nhánh OR không có tenant filter | Đặt tenant ở điều kiện bắt buộc cấp cao |
| Projection làm entity thiếu dữ liệu | Chỉ select field con rồi ánh xạ vào entity đầy đủ | Dùng DTO/projection và không save entity thiếu field |

## 17. Bài thực hành có lời giải

### Bài 1 — Viết đường dẫn tới thành phố

**Đề bài:** Một document lưu `ship_to: {city_name: "Hà Nội", district: "Cầu Giấy"}`. Viết query mongosh lấy đơn của tenant-a giao đến Hà Nội.

**Lời giải:**

```javascript
db.orders.find({
  tenantId: "tenant-a",
  "ship_to.city_name": "Hà Nội"
});
```

`ship_to.city_name` là đường dẫn BSON. Không viết `shippingAddress.city` trong mongosh vì đó là tên property Java của model minh họa.

### Bài 2 — Dự đoán ánh xạ @Field

**Đề bài:** Entity có `@Field("ship_to") ShippingAddress shippingAddress`; bên trong `ShippingAddress` có `@Field("city_name") String city`. Viết `Criteria` cho thành phố Đà Nẵng.

**Lời giải:**

```java
Query query = Query.query(
    Criteria.where("shippingAddress.city").is("Đà Nẵng")
);
```

Khi thực thi với `OrderDocument.class`, mapper chuyển sang path BSON `ship_to.city_name`. Trong hệ thống multi-tenant, bổ sung điều kiện tenant trước khi sử dụng query này.

### Bài 3 — Tìm dòng hàng cùng thỏa hai điều kiện

**Đề bài:** Tìm đơn tenant-a có một dòng `BOOK-A` với quantity từ 3 trở lên. Vì sao không nên dùng hai điều kiện dot notation độc lập?

**Lời giải:** Hai điều kiện độc lập có thể thỏa ở hai phần tử khác nhau. Dùng:

```javascript
db.orders.find({
  tenantId: "tenant-a",
  items: {
    $elemMatch: {
      sku_code: "BOOK-A",
      quantity: { $gte: 3 }
    }
  }
});
```

Với fixture, chỉ `ord-002` khớp. `ord-001` có BOOK-A nhưng quantity của BOOK-A chỉ bằng 1.

### Bài 4 — Phân biệt Null và missing

**Đề bài:** Viết hai query: (a) chỉ lấy đơn có `ship_to.city_name` là BSON Null, (b) lấy đơn thiếu đường dẫn đó.

**Lời giải:**

```javascript
db.orders.find({
  "ship_to.city_name": { $type: "null" }
});

db.orders.find({
  "ship_to.city_name": { $exists: false }
});
```

Không dùng `{ "ship_to.city_name": null }` nếu yêu cầu phân biệt chính xác, vì cú pháp này thường bao gồm cả missing.

### Bài 5 — Chỉnh thành phố mà giữ nguyên các field khác

**Đề bài:** Với `ord-001`, hãy chuyển thành phố sang Hải Phòng mà vẫn giữ quận và đường.

**Lời giải:**

```javascript
db.orders.updateOne(
  { _id: "ord-001", tenantId: "tenant-a" },
  { $set: { "ship_to.city_name": "Hải Phòng" } }
);
```

Không set toàn bộ `ship_to` bằng object chỉ chứa `city_name`; làm vậy sẽ thay thế subdocument và có thể xóa các field còn lại.

### Bài 6 — Thiết kế index cho hai query

**Đề bài:** (a) Tìm đơn tenant-a giao Hà Nội; (b) tìm đơn tenant-a chứa SKU BOOK-A. Chọn index ban đầu nào?

**Lời giải:**

```javascript
db.orders.createIndex(
  { tenantId: 1, "ship_to.city_name": 1 },
  { name: "ix_orders_tenant_ship_city" }
);

db.orders.createIndex(
  { tenantId: 1, "items.sku_code": 1 },
  { name: "ix_orders_tenant_item_sku" }
);
```

Index thứ hai là multikey nếu `items` là array. Đây là **ứng viên ban đầu**, chưa phải kết luận tối ưu. Kiểm tra `explain("executionStats")` với workload và dữ liệu đại diện.

### Bài 7 — Embedded hay reference?

**Đề bài:** Schema lưu `shippingAddressId: "addr-001"` và địa chỉ thật nằm trong collection `addresses`. Truy vấn `shippingAddressId.city_name` có lấy được đơn theo thành phố không?

**Lời giải:** Không. `shippingAddressId` chỉ chứa ID; dot notation không tự đi theo reference sang collection khác. Cần `$lookup`, truy vấn hai bước hoặc lưu snapshot thành phố trong orders nếu access pattern yêu cầu.

### Bài 8 — Phân quyền khi kết hợp OR

**Đề bài:** Chỉ người dùng tenant-a được thấy các đơn đến Hà Nội hoặc Đà Nẵng. Viết filter tránh nhánh OR bỏ qua tenant.

**Lời giải:**

```javascript
db.orders.find({
  tenantId: "tenant-a",
  "ship_to.city_name": { $in: ["Hà Nội", "Đà Nẵng"] }
});
```

Với các nhánh điều kiện phức tạp, kiểm tra rằng tenant luôn nằm ngoài và áp dụng cho mọi nhánh; tenant của người dùng phải được xác thực ở tầng ứng dụng.

## 18. Checklist và ghi nhớ

| Câu hỏi cần trả lời | Bằng chứng kiểm tra |
| --- | --- |
| Document thực sự nhúng hay chỉ lưu ID? | BSON mẫu từ MongoDB |
| Property Java đã đổi tên bằng `@Field` chưa? | Metadata entity và đường dẫn BSON |
| Filter dùng tên Java hay BSON? | API `Criteria`/`@Query`/mongosh đang sử dụng |
| Đường dẫn có đi qua array không? | Schema và fixture thực tế |
| Các predicate phải cùng một phần tử không? | Có thì dùng `$elemMatch` |
| Có dữ liệu `null`/missing/sai kiểu không? | `$exists`, `$type`, thống kê dữ liệu |
| Query có ràng buộc tenant/owner không? | Security context và integration test |
| Có cần sort, limit hoặc pagination không? | Access pattern và query shape |
| Projection có trả entity thiếu field không? | DTO/projection và test mapping |
| Index nested path có phù hợp không? | `getIndexes()` và `explain` |
| Array index có phải multikey không? | Schema array và index metadata |
| Update chỉ sửa field con hay thay cả document nhúng? | Đọc lại document sau update |
| Array filter có dùng tên field BSON đúng không? | BSON command và integration test |
| Aggregation expression có đúng path không? | Pipeline và kết quả theo fixture |

### Ghi nhớ

1. **Dot notation** mô tả đường dẫn đến trường lồng nhau của document BSON, ví dụ `ship_to.city_name`. Không nhầm tên BSON với property Java `shippingAddress.city`.
2. Trên **document nhúng đơn**, nhiều điều kiện dot notation kiểm tra các trường con cùng document; trên **array of documents**, chúng có thể được thỏa bởi các phần tử khác nhau.
3. Dùng **`$elemMatch`** nếu nhiều điều kiện phải đúng trên **cùng một phần tử** trong array.
4. `null` và field không tồn tại có semantics query khác nhau; chọn `$exists`/`$type` khi cần phân biệt rõ.
5. Query và index phải theo **BSON field thật**, đồng thời bảo đảm tenant filter, sort, giới hạn kết quả và hiệu năng. Multikey index có lợi nhưng có ràng buộc và chi phí riêng.
6. Khi update, `$set: {"ship_to.city_name": ...}` chỉ sửa trường con, còn `$set: {ship_to: {...}}` thay cả subdocument.
7. Đừng chỉ tin vào cách viết Criteria: **kiểm thử mapping, BSON và kết quả thực tế** trước khi tối ưu bằng index.
