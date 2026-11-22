# Giới hạn trường trả về bằng thuộc tính fields

## 1. Vấn đề: truy vấn đúng document nhưng trả về quá nhiều dữ liệu

Một hệ thống bán hàng lưu đơn hàng trong collection `orders`. Mỗi document có các thông tin để hiển thị trên danh sách như mã đơn, trạng thái, tổng tiền, đồng thời có nhiều dữ liệu chỉ cần ở màn hình chi tiết như địa chỉ giao hàng, ghi chú nội bộ và các dòng sản phẩm.

Khi khách mở danh sách 20 đơn gần đây, API thực sự chỉ cần:

- Mã đơn (`_id`).
- Trạng thái (`status`).
- Tổng tiền (`totalAmount`).
- Thời gian đặt hàng (`placedAt`).

Nếu dùng repository trả nguyên entity chứa danh sách `items` dài và thông tin vận chuyển, ứng dụng có thể nhận nhiều dữ liệu hơn cần thiết. Chi phí mạng, giải mã BSON, tạo đối tượng Java và nguy cơ đưa nhầm dữ liệu riêng tư vào response đều tăng.

**MongoDB projection** giải quyết nhu cầu này: chỉ định những field được trả về bởi truy vấn, thay vì trả toàn bộ document. Trong Spring Data MongoDB, thuộc tính **`fields` của annotation `@Query`** là cách khai báo projection ngay tại phương thức repository.

Bài thuộc chương **Truy vấn JSON** của module **SPRING_DATA_MONGODB**. Ta sẽ luyện tập cách viết JSON cho `@Query(value=..., fields=...)`, kiểm tra kết quả qua repository hoặc `MongoTemplate`, hiểu những trường hợp include/exclude, field lồng nhau và mảng, rồi phân tích ảnh hưởng tới mapping, index, aggregation, transaction, reactive access, kiểm thử và hiệu năng.

> **Ý tưởng cốt lõi:** `value` (hoặc `query` theo ngữ cảnh API) xác định **document nào khớp**, còn `fields` xác định **trường nào của những document khớp được trả về**. Projection không thay đổi dữ liệu đang lưu trong MongoDB.

## 2. Dữ liệu mẫu và cách đọc trong `mongosh`

Giả sử collection `orders` có document sau. Các lệnh trong bài chỉ nên thử trên database riêng dành cho học tập/kiểm thử.

```javascript
db.orders.insertOne({
  _id: "ord-1001",
  customerId: "cus-01",
  status: "PAID",
  totalAmount: NumberDecimal("1850000.00"),
  placedAt: ISODate("2026-11-20T02:00:00Z"),
  shippingAddress: {
    recipientName: "Nguyễn An",
    city: "Đà Nẵng",
    phone: "0900000000"
  },
  internalNote: "Gọi khách trước khi giao",
  items: [
    {
      productId: "p-10",
      productName: "Bàn phím cơ",
      quantity: 2,
      unitPrice: NumberDecimal("925000.00")
    }
  ]
});
```

Một truy vấn thông thường:

```javascript
db.orders.find({ customerId: "cus-01" });
```

sẽ trả đầy đủ những field trong document, trừ khi có tùy chọn projection khác.

### 2.1. Projection ở MongoDB trước khi áp dụng Spring Data

Đối số thứ hai của `find(filter, projection)` trong `mongosh` cho phép giới hạn trường:

```javascript
db.orders.find(
  { customerId: "cus-01" },
  {
    _id: 1,
    status: 1,
    totalAmount: 1,
    placedAt: 1
  }
);
```

Kết quả minh họa:

```javascript
{
  _id: "ord-1001",
  status: "PAID",
  totalAmount: NumberDecimal("1850000.00"),
  placedAt: ISODate("2026-11-20T02:00:00Z")
}
```

Field `shippingAddress`, `internalNote` và `items` **không nằm trong dữ liệu trả về**. Chúng vẫn còn trong collection; việc chạy projection không xóa hay chỉnh sửa các field ấy.

MongoDB thường biểu diễn projection theo một document BSON/JSON có cặp tên field và chỉ thị: `1` để đưa field vào, `0` để loại field khỏi kết quả. Một số toán tử projection như `$slice` hoặc `$elemMatch` cũng có cú pháp riêng.

## 3. Cú pháp `@Query(fields = "...")` trong Spring Data MongoDB

Trong repository, annotation `@Query` nhận chuỗi truy vấn JSON và chuỗi projection JSON:

```java
@Query(
    value = "{ 'customerId': ?0 }",
    fields = "{ '_id': 1, 'status': 1, 'totalAmount': 1, 'placedAt': 1 }"
)
List<OrderDocument> findOrderHeaders(String customerId);
```

Cách hiểu:

- `value` là phần lọc: chỉ document có `customerId` bằng tham số đầu tiên (`?0`).
- `fields` là phần projection: chỉ trả `_id`, `status`, `totalAmount` và `placedAt`.
- `?0` là placeholder do Spring Data gắn giá trị tham số; không nối trực tiếp JSON từ chuỗi người dùng.
- `List<OrderDocument>` trong ví dụ này sẽ chứa **entity chỉ có một phần field**. Những thuộc tính không được tải có thể thành `null`/giá trị mặc định — đây là lý do thông thường nên ưu tiên một kiểu kết quả chuyên dụng cho danh sách, được trình bày bên dưới.

Annotation `@Query` cho phép định nghĩa điều kiện mà không cần tự viết `MongoTemplate` cho mỗi truy vấn. Nhưng `fields` không phải SQL `SELECT`, không tạo phép join và không làm biến mất field trong document được lưu.

### 3.1. Tên property Java và tên BSON

Trong ví dụ chính, các property và BSON field trùng tên (`customerId`, `status`, `totalAmount`). Với `@Field("customer_id")`, tên Java có thể khác tên đã lưu. Truy vấn repository đi qua metadata mapping của Spring Data; không nên mặc định chuỗi dùng trong raw `mongosh` và annotation đều được xử lý giống nhau trong mọi cấu hình, nhất là khi có converter/naming strategy.

Quy trình an toàn là **kiểm tra field BSON thật**, rồi viết kiểm thử tích hợp cho query/projection, đặc biệt sau khi đổi `@Field` hoặc bộ chuyển đổi dữ liệu.

## 4. Model Java cho ví dụ

Dùng Java 17+ và Spring Data MongoDB. Những đoạn code dưới đây là ví dụ độc lập về mặt ý tưởng; mỗi top-level type nên nằm trong file Java tương ứng.

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders")
public record OrderDocument(
    @MongoId(FieldType.STRING)
    String id,

    String customerId,
    String status,

    @Field(targetType = FieldType.DECIMAL128)
    BigDecimal totalAmount,

    Instant placedAt,
    ShippingAddress shippingAddress,
    String internalNote,
    List<OrderItem> items
) {
    public record ShippingAddress(
        String recipientName,
        String city,
        String phone
    ) {}

    public record OrderItem(
        String productId,
        String productName,
        int quantity,
        @Field(targetType = FieldType.DECIMAL128)
        BigDecimal unitPrice
    ) {}
}
```

`@MongoId(FieldType.STRING)` thể hiện chủ đích lưu `id` trong BSON field `_id` dạng string. Annotation `@Field(targetType=DECIMAL128)` giúp lưu giá trị tiền bằng BSON Decimal128 theo mapping Spring Data.

Nếu một entity được tải thiếu `items`, `shippingAddress` hoặc `internalNote` vì projection, record được ánh xạ không thể đại diện cho một `OrderDocument` đầy đủ như lúc được ghi. Không dùng bản ghi thiếu dữ liệu như bằng chứng rằng những trường ấy vốn không tồn tại.

## 5. Include projection: chỉ chọn trường cần dùng

### 5.1. Repository dùng `@Query(fields=...)`

```java
import java.util.List;

import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.mongodb.repository.Query;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {

    @Query(
        value = "{ 'customerId': ?0 }",
        fields = "{ '_id': 1, 'status': 1, 'totalAmount': 1, 'placedAt': 1 }"
    )
    List<OrderDocument> findOrderHeaders(String customerId);
}
```

Khi gọi:

```java
List<OrderDocument> orders =
    orderRepository.findOrderHeaders("cus-01");

for (OrderDocument order : orders) {
    System.out.println(order.id());
    System.out.println(order.status());
    System.out.println(order.totalAmount());

    // Không kỳ vọng items hoặc shippingAddress được tải.
}
```

Đây là cách đơn giản để thấy thuộc tính `fields` hoạt động. Tuy nhiên, vì kiểu trả về vẫn là entity đầy đủ, một số field của `OrderDocument` sẽ không có giá trị. Phần 9 trình bày interface projection phù hợp hơn cho API chỉ đọc.

### 5.2. Quy tắc mặc định của `_id`

MongoDB **bao gồm `_id` theo mặc định**, kể cả khi bạn chỉ liệt kê những field khác:

```javascript
db.orders.find(
  { customerId: "cus-01" },
  { status: 1, totalAmount: 1 }
);
```

Kết quả vẫn có `_id`. Nếu thật sự không muốn trả ID, thêm `_id: 0`:

```javascript
db.orders.find(
  { customerId: "cus-01" },
  { _id: 0, status: 1, totalAmount: 1 }
);
```

Tương ứng trong repository:

```java
@Query(
    value = "{ 'customerId': ?0 }",
    fields = "{ '_id': 0, 'status': 1, 'totalAmount': 1 }"
)
List<OrderDocument> findAmountsWithoutIds(String customerId);
```

**Cẩn thận:** nếu loại `_id` nhưng kiểu kết quả Java có property `id`, property đó sẽ thiếu dữ liệu. Cách này phù hợp cho dữ liệu chỉ đọc/DTO khi không cần ID, không phù hợp nếu sau đó ứng dụng muốn cập nhật document theo ID.

### 5.3. Có thể kết hợp nhiều field và sort

Một danh sách đơn hàng thường cần phân trang và sắp xếp theo `placedAt`. Projection chỉ quyết định field trả về; sorting và paging là nhiệm vụ riêng:

```java
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.mongodb.repository.Query;

@Query(
    value = "{ 'customerId': ?0 }",
    fields = "{ '_id': 1, 'status': 1, 'totalAmount': 1, 'placedAt': 1 }"
)
Slice<OrderDocument> findHeadersByCustomer(
    String customerId,
    Pageable pageable
);
```

Ví dụ sử dụng:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

PageRequest pageRequest = PageRequest.of(
    0, 20, Sort.by(Sort.Direction.DESC, "placedAt")
);

Slice<OrderDocument> first =
    orderRepository.findHeadersByCustomer("cus-01", pageRequest);
```

`Slice` thường phù hợp khi chỉ cần biết có trang tiếp theo hay không; `Page` có thể cần thêm truy vấn đếm. Nếu dữ liệu thay đổi liên tục, phân trang offset có thể bị lặp/bỏ sót giữa các lần đọc; với lịch sử dài, cân nhắc keyset pagination theo bộ khóa ổn định.

## 6. Exclude projection: loại những trường không cần

Thay vì khai báo danh sách field muốn nhận, có thể **loại khỏi kết quả** một hoặc một số field:

```javascript
db.orders.find(
  { customerId: "cus-01" },
  { internalNote: 0, items: 0 }
);
```

Kết quả vẫn có `_id`, `customerId`, `status`, `totalAmount`, `placedAt` và `shippingAddress`. Chỉ `internalNote` và `items` bị loại.

Trong repository:

```java
@Query(
    value = "{ 'customerId': ?0 }",
    fields = "{ 'internalNote': 0, 'items': 0 }"
)
List<OrderDocument> findWithoutLargeDetails(String customerId);
```

### 6.1. Quy tắc không trộn include và exclude

Ngoại lệ thông dụng là `_id`, **không thể trộn tùy ý** inclusion (`1`) và exclusion (`0`) trong cùng một projection thông thường:

```javascript
// Không hợp lệ: status được include nhưng items bị exclude.
db.orders.find(
  {},
  { status: 1, items: 0 }
);
```

Hai lựa chọn hợp lệ:

```javascript
// Chỉ trả những field được chọn, bỏ _id:
db.orders.find({}, { status: 1, totalAmount: 1, _id: 0 });

// Trả mọi field trừ items và internalNote:
db.orders.find({}, { items: 0, internalNote: 0 });
```

MongoDB có những ngoại lệ/toán tử projection đặc thù như `$meta` hoặc `$slice` với quy tắc riêng; trước khi dùng chúng, kiểm tra đúng cú pháp và phiên bản server đang triển khai. Với danh sách API, cách dễ đọc nhất thường là include rõ từng field được phép trả.

### 6.2. Vì sao include an toàn hơn cho API ổn định?

Giả sử năm sau document được thêm field `fraudAssessment` hoặc `paymentProviderSecret`. Một projection **exclude hai field cũ** có thể vô tình trả field mới, trong khi projection **include bốn field cần thiết** sẽ không tự mở rộng theo schema.

Điều đó không biến projection thành cơ chế bảo mật độc lập. API vẫn phải xác thực người dùng, kiểm tra quyền theo document và field, đồng thời dùng DTO được kiểm soát. Nhưng với endpoint trả danh sách cố định, cách include thường dễ review và ít rủi ro lộ thông tin ngoài ý muốn hơn.

## 7. Projection với object lồng nhau

Ta có địa chỉ:

```javascript
shippingAddress: {
  recipientName: "Nguyễn An",
  city: "Đà Nẵng",
  phone: "0900000000"
}
```

Nếu chỉ muốn thành phố, dùng dot notation:

```javascript
db.orders.find(
  { customerId: "cus-01" },
  {
    _id: 1,
    "shippingAddress.city": 1
  }
);
```

Kết quả minh họa:

```javascript
{
  _id: "ord-1001",
  shippingAddress: {
    city: "Đà Nẵng"
  }
}
```

Tương tự với `@Query(fields=...)`:

```java
@Query(
    value = "{ 'customerId': ?0 }",
    fields = "{ '_id': 1, 'shippingAddress.city': 1 }"
)
List<OrderDocument> findOrderCities(String customerId);
```

Trường `shippingAddress` được tải một phần, vì vậy `recipientName` và `phone` không có trong subdocument trả về. **Không đưa một object lồng nhau được tải một phần vào thao tác `save` để cập nhật cả entity**; có thể gây mất các trường chưa được tải.

### 7.1. Một trường lồng nhau là field BSON, không phải đường truy cập Java tùy ý

Nếu model dùng `@Field("shipping_address")`, tên field trong BSON có thể khác. Với `MongoTemplate` hoặc repository dùng mapping metadata, tên property có thể được ánh xạ theo schema; khi viết truy vấn `mongosh` phải dùng đường BSON thật.

Các query có nested object, field rename hoặc converter tùy chỉnh nên có **kiểm thử BSON và test truy vấn** để đảm bảo annotation `fields` chọn đúng đường dẫn sau mapping.

## 8. Projection trên mảng: một giới hạn dễ bỏ sót

Giả sử một đơn có nhiều dòng sản phẩm. Nếu viết:

```javascript
db.orders.find(
  { _id: "ord-1001" },
  { "items.productName": 1, status: 1 }
);
```

MongoDB vẫn có thể trả về mảng `items` với các phần tử chỉ chứa `productName`. Câu lệnh **giới hạn trường của mỗi phần tử**, không có nghĩa chỉ trả một phần tử hay chỉ giữ những phần tử khớp một điều kiện.

Với document:

```javascript
{
  items: [
    { productId: "p-10", productName: "Bàn phím cơ", quantity: 2 },
    { productId: "p-11", productName: "Chuột", quantity: 1 }
  ]
}
```

projection theo `items.productName` vẫn có thể trả cả hai tên. Muốn giới hạn số phần tử hoặc chọn phần tử theo điều kiện, cần toán tử chuyên biệt.

### 8.1. Dùng `$slice` để chỉ trả vài phần tử

Trong `mongosh`:

```javascript
db.orders.find(
  { _id: "ord-1001" },
  {
    status: 1,
    items: { $slice: 2 }
  }
);
```

`$slice: 2` lấy tối đa hai phần tử đầu của mảng `items`. Nếu mảng chỉ có một phần tử, chỉ một phần tử được trả về. Đây **không phải** phân trang ổn định dành cho mảng dài; nó chỉ là giới hạn phần tử trong phép projection.

Trong annotation, `fields` cũng là chuỗi JSON để khai báo các projection operator được hỗ trợ:

```java
@Query(
    value = "{ '_id': ?0 }",
    fields = "{ 'status': 1, 'items': { '$slice': 2 } }"
)
OrderDocument findWithFirstTwoItems(String id);
```

Mẫu trên thể hiện cách viết toán tử trong field projection. Đối với các API MongoDB/phiên bản Spring Data khác nhau, nên xác minh truy vấn phát sinh và kết quả BSON bằng kiểm thử tích hợp.

### 8.2. `$elemMatch` chỉ lấy phần tử khớp đầu tiên

Nếu muốn chi tiết phần tử đầu tiên có `productId = "p-10"`:

```javascript
db.orders.find(
  { _id: "ord-1001" },
  {
    status: 1,
    items: { $elemMatch: { productId: "p-10" } }
  }
);
```

Toán tử projection `$elemMatch` chọn **phần tử đầu tiên** của mảng khớp điều kiện, nếu có. Nó không tương đương với bộ lọc document `{ "items.productId": "p-10" }`: bộ lọc quyết định *đơn nào* khớp, còn projection quyết định *dòng hàng nào* được trả về trong đơn đã khớp.

Nếu cần biến đổi/phân trang/phân nhóm mảng phức tạp, xem xét `$filter`, `$slice` trong aggregation `$project` hoặc một mô hình document khác. Không nên nhồi logic quá phức tạp vào `@Query(fields=...)` chỉ để tránh viết một pipeline rõ ràng.

## 9. Không dùng entity tải một phần để ghi đè dữ liệu

Đây là rủi ro quan trọng nhất khi kết hợp projection với CRUD.

Giả sử:

```java
@Query(
    value = "{ '_id': ?0 }",
    fields = "{ '_id': 1, 'status': 1 }"
)
OrderDocument findStatusOnly(String orderId);
```

Kết quả có thể có `id` và `status`, nhưng `customerId`, `totalAmount`, `placedAt`, `items`, `shippingAddress` và `internalNote` không được tải.

Nếu sau đó:

```java
OrderDocument partial = orderRepository.findStatusOnly("ord-1001");

// KHÔNG thực hiện thao tác lưu lại entity partial để cập nhật status:
orderRepository.save(partial);
```

thì việc save/replace có thể làm mất các field đã không được đọc, hoặc gây lỗi vì bất biến/mapping của entity không được đáp ứng. **Không coi entity partial là aggregate hoàn chỉnh.**

### 9.1. Khi cần cập nhật một field: dùng update có điều kiện

Ví dụ chuyển đơn từ `PAID` sang `SHIPPED` bằng `MongoTemplate`:

```java
import com.mongodb.client.result.UpdateResult;

import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public boolean markShipped(MongoTemplate template, String id) {
    Query query = Query.query(
        Criteria.where("_id").is(id)
            .and("status").is("PAID")
    );

    Update update = new Update()
        .set("status", "SHIPPED");

    UpdateResult result = template.updateFirst(
        query,
        update,
        OrderDocument.class
    );
    return result.getModifiedCount() == 1;
}
```

Chỉ field `status` thay đổi. Phần còn lại của document không bị thay thế bởi một entity tải thiếu dữ liệu. Bộ lọc trạng thái giúp tránh một số cập nhật sai khi có request cạnh tranh.

### 9.2. Interface projection là lựa chọn tốt cho API chỉ đọc

Định nghĩa một view chỉ gồm bốn field:

```java
import java.math.BigDecimal;
import java.time.Instant;

public interface OrderListView {
    String getId();
    String getStatus();
    BigDecimal getTotalAmount();
    Instant getPlacedAt();
}
```

Khai báo method repository:

```java
@Query(
    value = "{ 'customerId': ?0 }",
    fields = "{ '_id': 1, 'status': 1, 'totalAmount': 1, 'placedAt': 1 }"
)
List<OrderListView> findListViewsByCustomerId(String customerId);
```

Kết quả là **interface-based projection** dành cho đọc dữ liệu. Nó thể hiện rõ hợp đồng trả về; service không cần sử dụng một `OrderDocument` được lấp đầy một phần như thể đó là entity hoàn chỉnh.

Cần lưu ý: projection interface trong Spring Data có quy tắc ánh xạ riêng. Một projection **closed** với các accessor đơn giản như trên thường thuận lợi để tối ưu danh sách field; projection **open** chứa biểu thức SpEL hoặc tính toán dựa trên target có thể khiến framework phải đọc nhiều dữ liệu hơn. Đừng dựa vào lời hứa tối ưu khi chưa xem query thực tế.

### 9.3. DTO và mapping API

Có thể chuyển `OrderListView` sang một response DTO chuyên biệt để tránh trả trực tiếp kiểu dữ liệu persistence trong API:

```java
import java.math.BigDecimal;
import java.time.Instant;

public record OrderSummaryResponse(
    String id,
    String status,
    BigDecimal totalAmount,
    Instant placedAt
) {
    public static OrderSummaryResponse from(OrderListView view) {
        return new OrderSummaryResponse(
            view.getId(),
            view.getStatus(),
            view.getTotalAmount(),
            view.getPlacedAt()
        );
    }
}
```

Nếu muốn repository trả trực tiếp DTO, Spring Data có các cơ chế class-based projection, nhưng kết quả phụ thuộc constructor, metadata và query method. Cần kiểm tra mapping theo phiên bản đang dùng và luôn xác minh BSON/query. Interface projection rồi map sang DTO là cách rõ ràng để minh họa `fields` mà không phụ thuộc các chi tiết phức tạp.

## 10. So sánh `@Query(fields=...)` với `MongoTemplate`

### 10.1. Repository: projection tĩnh, dễ tái sử dụng

Một phương thức:

```java
@Query(
    value = "{ 'status': ?0 }",
    fields = "{ '_id': 1, 'status': 1, 'totalAmount': 1 }"
)
List<OrderListView> findViewsByStatus(String status);
```

phù hợp khi một endpoint hoặc use case dùng tập field ổn định. Tên phương thức diễn đạt ý nghĩa truy vấn, còn `fields` công khai hợp đồng dữ liệu được tải.

### 10.2. MongoTemplate: projection động theo use case

Khi cần xây query nhiều điều kiện, có thể dùng `Query.fields()`:

```java
import java.util.List;

import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public List<OrderDocument> findPaidHeads(
    MongoTemplate template,
    String customerId
) {
    Query query = Query.query(
        Criteria.where("customerId").is(customerId)
            .and("status").is("PAID")
    );

    query.fields()
         .include("_id")
         .include("status")
         .include("totalAmount")
         .include("placedAt");

    return template.find(query, OrderDocument.class);
}
```

Về ý nghĩa, nó tương đương việc đặt `fields = "{ '_id': 1, 'status': 1, 'totalAmount': 1, 'placedAt': 1 }"` trong repository. Kết quả `OrderDocument` ở đây vẫn là partial entity; chỉ sử dụng cho đọc.

Muốn loại field:

```java
query.fields()
     .exclude("internalNote")
     .exclude("items");
```

Không được ghép các lệnh `include("status")` và `exclude("items")` trên cùng query theo cách trộn include/exclude không hợp lệ. Ngoại lệ `_id` có thể được include/exclude theo nhu cầu.

### 10.3. Khi nào chọn phương án nào?

| Tiêu chí | `@Query(fields=...)` | `MongoTemplate Query.fields()` |
| --- | --- | --- |
| Projection cố định | Gọn trong interface repository | Phải viết query trong service/helper |
| Điều kiện và tập field xây dựng động | Không phải lựa chọn linh hoạt nhất | Dễ thêm include/exclude có điều kiện |
| Truy vấn JSON cần review | Hiện ngay trong annotation | Hiện trong code tạo `Query` |
| Ghép nhiều stage như `$group`, `$lookup` | Không phù hợp cho mọi pipeline | Dùng `Aggregation` và `aggregate` |
| Kiểm thử | Gọi method repository rồi xác minh kết quả | Gọi service/template rồi kiểm tra dữ liệu |
| Tác động tới entity partial | Có, nếu return entity | Có, nếu return entity |

Hai lựa chọn đều dùng mô hình Spring Data MongoDB, và cả hai cần đo lường. Không nên chuyển sang `MongoTemplate` chỉ vì nghĩ rằng annotation `@Query` không thể đặt projection; thuộc tính `fields` giải quyết nhu cầu phổ biến này rất trực tiếp.

## 11. `fields` không giống `$project` của aggregation

Trong MongoDB, `find(..., projection)` là công cụ chọn field ở kết quả truy vấn thông thường. Trong aggregation pipeline, stage `$project` có thể tạo field, đổi tên, tính toán biểu thức và bỏ field.

Ví dụ: chỉ hiển thị mã đơn, số tiền và nhãn trạng thái:

```javascript
db.orders.aggregate([
  { $match: { customerId: "cus-01" } },
  {
    $project: {
      _id: 1,
      totalAmount: 1,
      statusLabel: {
        $cond: [
          { $eq: ["$status", "PAID"] },
          "Đã thanh toán",
          "Chưa thanh toán"
        ]
      }
    }
  }
]);
```

`statusLabel` không phải field gốc ở document; nó được tính trong pipeline. Đây là chức năng vượt quá một inclusion projection đơn giản.

Trong Spring Data MongoDB, có thể dùng `Aggregation` với `MongoTemplate.aggregate(...)` để mô tả pipeline tương đương. Không dùng `@Query(fields=...)` như công cụ thay thế toàn bộ aggregation nếu use case cần `$lookup`, `$group` hay tính toán phức tạp.

Một mặt khác cần phân biệt: `fields` của `@Query` **không thay đổi filter**. Chẳng hạn truy vấn lọc theo `customerId` nhưng không include `customerId` vẫn tìm đúng đơn của khách; field lọc không bắt buộc phải xuất hiện trong response.

## 12. Projection và index: có thực sự nhanh hơn không?

### 12.1. Projection giúp giảm dữ liệu truyền, không luôn giảm số document đã đọc

Khi projection chỉ trả vài trường nhỏ, thông thường MongoDB gửi ít dữ liệu hơn qua mạng và client giải mã ít field hơn. Nhưng phía server **vẫn có thể cần đọc document gốc** để lấy những field được chọn.

Vì vậy, không nên kết luận “projection làm truy vấn nhanh hơn nhiều lần” nếu chưa đo. Với collection có document nhỏ và mạng nhanh, chênh lệch có thể ít; với document lớn chứa mảng dài, lợi ích truyền dữ liệu có thể đáng kể.

### 12.2. Covered query

Nếu toàn bộ field cần lọc và field cần trả về đều nằm trong index phù hợp, MongoDB có thể trả lời truy vấn từ index mà không phải đọc document gốc: đây là **covered query**. Ví dụ trên database kiểm thử:

```javascript
db.orders.createIndex({
  customerId: 1,
  status: 1,
  totalAmount: 1
});

db.orders.find(
  { customerId: "cus-01", status: "PAID" },
  {
    _id: 0,
    customerId: 1,
    status: 1,
    totalAmount: 1
  }
).explain("executionStats");
```

Bởi `_id` thường được trả tự động nhưng không xuất hiện trong index trên, ở ví dụ covered query ta **chủ động đặt `_id: 0`**. Khi các điều kiện khác phù hợp, một kế hoạch query được cover có thể có `totalDocsExamined = 0`. Đây là **khả năng**, không phải cam kết cho mọi MongoDB version, dữ liệu và query planner.

Nếu cần sort theo `placedAt`, projection thêm `shippingAddress.city` hoặc truy vấn dùng collation không khớp, index trên có thể không đủ. Với index multikey, projection mảng và một số loại biểu thức cũng có những hạn chế riêng. Chọn index theo **filter + sort + projection** và đo bằng `explain("executionStats")`.

### 12.3. Index theo nhu cầu đọc thực tế

Danh sách đơn gần nhất của một khách thường lọc theo `customerId` và sắp xếp theo `placedAt`:

```javascript
db.orders.createIndex({
  customerId: 1,
  placedAt: -1
});

db.orders.find(
  { customerId: "cus-01" },
  { status: 1, totalAmount: 1, placedAt: 1 }
)
.sort({ placedAt: -1 })
.limit(20)
.explain("executionStats");
```

Index này có thể giúp filter/sort, nhưng **không nhất thiết cover** toàn bộ projection vì `status` và `totalAmount` không nằm trong index; hơn nữa `_id` mặc định được trả. Muốn đưa thêm mọi field vào index để “cover” một use case, cần cân đối kích thước index, write amplification, cache và tần suất truy vấn. Không thêm index cho mọi trường một cách máy móc.

### 12.4. Phân biệt đo query với đo toàn bộ API

Độ trễ từ phía client bao gồm mạng, deserialization, mapping Java, logic service và serialize response. Có thể đo:

- `totalDocsExamined` và `totalKeysExamined` trong `explain("executionStats")`.
- Dung lượng document trả về và thời gian mạng.
- Số field và kích thước mảng được tải.
- Thời gian chuyển `Document` thành entity hoặc projection interface.
- Tổng thời gian endpoint, percentiles latency khi tải cao.

Bảng quan sát giúp tránh việc tối ưu projection trong khi điểm nghẽn thực sự là query thiếu index hoặc N+1 query ở bước tải tham chiếu.

## 13. Tác động tới bảo mật và hợp đồng API

Một endpoint liệt kê đơn hàng của khách không nên dùng `@Query(value="{}")` rồi chỉ giới hạn `fields`, vì projection **không lọc khách hàng sở hữu đơn**. Cần có điều kiện lọc theo identity đã được xác thực và kiểm tra quyền truy cập ở lớp nghiệp vụ.

Ví dụ:

```java
@Query(
    value = "{ 'customerId': ?0 }",
    fields = "{ '_id': 1, 'status': 1, 'totalAmount': 1, 'placedAt': 1 }"
)
List<OrderListView> findCustomerHistory(String customerId);
```

`customerId` phải đến từ danh tính đã được xác thực hoặc một luồng có kiểm soát quyền; **không tin thẳng mã khách do người gọi API tự gửi** nếu họ không có quyền truy cập đơn của người khác.

Sử dụng include projection giúp giảm nguy cơ trả nhầm `internalNote` và `shippingAddress.phone`, nhưng không đủ để bảo vệ dữ liệu khỏi người dùng không được phép. Chính sách truy cập, validation, masking/redaction và response DTO phải được thiết kế riêng.

Không cho client tự truyền một chuỗi JSON bất kỳ để đưa thẳng vào `@Query` hay `MongoTemplate`. Dùng tham số được bind đúng kiểu và danh sách field được ứng dụng cho phép. Một API “chọn field động” cần whitelist, giới hạn độ sâu/số lượng và kiểm tra quyền trên từng nhóm field.

## 14. Reactive repository có dùng projection tương tự không?

Có. Với `ReactiveMongoRepository`, `@Query(fields=...)` vẫn diễn tả projection trong truy vấn JSON, nhưng kết quả được đưa qua `Flux`/`Mono`:

```java
import org.springframework.data.mongodb.repository.Query;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;

import reactor.core.publisher.Flux;

public interface ReactiveOrderRepository
        extends ReactiveMongoRepository<OrderDocument, String> {

    @Query(
        value = "{ 'customerId': ?0 }",
        fields = "{ '_id': 1, 'status': 1, 'totalAmount': 1, 'placedAt': 1 }"
    )
    Flux<OrderListView> findListViews(String customerId);
}
```

Reactive không thay đổi quy tắc include/exclude/_id, không tự loại bỏ field nhạy cảm và không bảo đảm query có index. Nếu dùng `ReactiveMongoTemplate`, có thể tạo `Query` với `fields().include(...)` tương tự rồi gọi `find(...)` trả về `Flux`.

Projection cũng **không tự tạo transaction** hay snapshot nhất quán giữa nhiều truy vấn. Nếu hệ thống cần transaction đa document, phải cấu hình manager/session thích hợp (imperative dùng `MongoTransactionManager`, reactive có `ReactiveMongoTransactionManager`) và xác định ranh giới nghiệp vụ. Với một truy vấn đọc danh sách thông thường, thường không cần mở transaction chỉ vì có `fields`.

Tránh gọi `block()` trong luồng xử lý WebFlux chỉ để lấy projection. Và không dùng partial entity đọc từ reactive repository rồi `save` như thể nó có đủ dữ liệu.

## 15. Kiểm thử: bảo đảm MongoDB thật chỉ trả field được chọn

Unit test mock `OrderRepository` không chứng minh `@Query(fields=...)` đã được chuyển thành projection BSON đúng. Muốn xác minh, cần một **integration test trên MongoDB** (có thể dùng Testcontainers) ghi document đầy đủ và đọc bằng repository/template.

### 15.1. Viết kiểm thử repository projection

Ví dụ dùng `@DataMongoTest` và JUnit 5; môi trường cần cấu hình MongoDB test riêng. Với test thực tế, ID phải duy nhất hoặc dữ liệu được dọn giữa các lần chạy:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;

@DataMongoTest
class OrderQueryFieldsTest {

    @Autowired OrderRepository orders;

    @Test
    void returnsOnlyRequestedFieldsInListProjection() {
        OrderDocument full = new OrderDocument(
            "ord-projection-test",
            "cus-test",
            "PAID",
            new BigDecimal("1850000.00"),
            Instant.parse("2026-11-20T02:00:00Z"),
            new OrderDocument.ShippingAddress(
                "Nguyễn An", "Đà Nẵng", "0900000000"
            ),
            "Ghi chú nội bộ",
            List.of(new OrderDocument.OrderItem(
                "p-10", "Bàn phím cơ", 2,
                new BigDecimal("925000.00")
            ))
        );

        orders.insert(full);

        List<OrderListView> views =
            orders.findListViewsByCustomerId("cus-test");

        assertThat(views).hasSize(1);
        assertThat(views.get(0).getId())
            .isEqualTo("ord-projection-test");
        assertThat(views.get(0).getStatus()).isEqualTo("PAID");
        assertThat(views.get(0).getTotalAmount())
            .isEqualByComparingTo("1850000.00");
    }
}
```

Kiểm thử trên xác minh các trường được trả ở lớp Java và cách method chạy cùng dữ liệu thật. Tuy vậy, nó **chưa tự chứng minh** rằng MongoDB không gửi các field khác, vì interface projection đôi khi có thể dựng từ dữ liệu nhiều hơn cần thiết tùy cơ chế mapping.

### 15.2. Xác minh BSON projection thực

Dùng `mongosh` sau khi tạo document kiểm thử:

```javascript
const projected = db.orders.findOne(
  { _id: "ord-projection-test" },
  { _id: 1, status: 1, totalAmount: 1, placedAt: 1 }
);

print(EJSON.stringify(projected, null, 2, { relaxed: false }));

// Kiểm tra field nhạy cảm không xuất hiện trong kết quả projection:
print(Object.prototype.hasOwnProperty.call(projected, "internalNote"));
print(Object.prototype.hasOwnProperty.call(projected, "shippingAddress"));
print(Object.prototype.hasOwnProperty.call(projected, "items"));
```

Ba dòng `hasOwnProperty` cuối dự kiến in `false`. Đây là cách kiểm tra **projection tương đương trên MongoDB**, chưa phải bằng chứng Spring Data đã gửi đúng projection từ annotation. Để xác nhận đường đi thật, có thể bật command monitoring trong môi trường test hoặc kiểm tra lệnh MongoDB được gửi bởi driver/Spring Data (tránh log dữ liệu nhạy cảm). Cần xem field projection của truy vấn đang được thực thi.

### 15.3. Kiểm thử âm tính và hồi quy

| Trường hợp | Điều cần xác minh |
| --- | --- |
| Không khai báo `fields` | Truy vấn trả document đầy đủ theo mapping thông thường |
| Include `status` và `totalAmount` | `items`/`internalNote` không có trong BSON trả về |
| Include và `_id: 0` | Không có `_id`, accessor ID có thể thiếu |
| Exclude `items` | Các trường còn lại vẫn được trả |
| Projection lồng nhau `shippingAddress.city` | Chỉ subfield `city` được giữ trong địa chỉ |
| `items.productName` | Trả các tên trong mảng, không mặc định giới hạn số phần tử |
| `$slice` trên `items` | Số phần tử trả về bị giới hạn theo cú pháp |
| Entity đọc thiếu field rồi `save` | Không được dùng như update an toàn; service phải dùng đường khác |
| Thay `@Field` hoặc converter | Projection và query vẫn dùng đúng BSON field thật |
| Index khác với projection | Đo `explain`, không mặc định covered query |

Nếu hệ thống có dữ liệu lịch sử nhiều phiên bản, cần bổ sung test khi document thiếu field hoặc lưu kiểu khác (ví dụ `totalAmount` là string thay vì BSON decimal). Projection không sửa kiểu dữ liệu cũ.

## 16. Lỗi thường gặp khi dùng `fields`

**Lỗi 1: nhầm `fields` với bộ lọc.** Viết `fields="{ 'status': 1 }"` không có nghĩa chỉ chọn các đơn trạng thái PAID. Điều kiện lọc phải được khai báo trong `value`, ví dụ `"{ 'status': 'PAID' }"`.

**Lỗi 2: không biết `_id` vẫn được trả.** Nếu muốn kết quả không có ID, phải ghi rõ `'_id': 0`. Ngược lại, nếu view cần ID, đừng loại nó.

**Lỗi 3: trộn include với exclude không hợp lệ.** `"{ 'status': 1, 'items': 0 }"` thường không hợp lệ. Hãy chọn chế độ include hoặc exclude, với ngoại lệ `_id`.

**Lỗi 4: lưu lại partial entity.** Repository trả một `OrderDocument` bị thiếu field, rồi ứng dụng gọi `save` có thể làm mất dữ liệu. Tạo read-model/DTO hoặc dùng update riêng trên field cần sửa.

**Lỗi 5: coi nested field projection như phân trang array.** `items.productName` chọn field trong mỗi phần tử; nó không giới hạn số lượng dòng hàng. Dùng `$slice` hoặc thiết kế pipeline phù hợp khi cần.

**Lỗi 6: nghĩ projection luôn tạo covered query.** Index chỉ cover khi chứa đủ thành phần cần thiết; mặc định trả `_id` cũng ảnh hưởng khả năng cover.

**Lỗi 7: dùng exclude để bảo vệ field nhạy cảm mới.** Khi schema thêm field, exclude list cũ có thể vô tình trả field mới. Dùng include/DTO và kiểm tra quyền.

**Lỗi 8: dùng property Java sai tên BSON trong truy vấn raw.** Repository và `MongoTemplate` có metadata mapping, còn `mongosh`/driver raw yêu cầu tên BSON thật. Hãy kiểm thử sau khi dùng `@Field` hoặc converters.

**Lỗi 9: chỉ xem kết quả interface projection rồi kết luận MongoDB đã giảm dữ liệu truyền.** Hãy xác minh command/projection thực và đo độ trễ, dung lượng response.

**Lỗi 10: bỏ qua sort và phân trang.** Trả ít field nhưng đọc hàng trăm nghìn đơn vẫn có thể chậm và tốn bộ nhớ. Phối hợp projection với `limit`/`Pageable`, sort và index phù hợp.

## 17. Quy trình thực hành hoàn chỉnh

1. Tạo document `orders` chứa đủ thông tin, gồm `items`, `shippingAddress` và `internalNote`.
2. Dùng `mongosh find(filter, projection)` để thấy sự khác biệt giữa truy vấn đầy đủ và truy vấn chỉ include bốn field.
3. Định nghĩa `@Query(value=..., fields=...)` trong `OrderRepository`, thử bật/tắt `_id`.
4. Đổi sang interface `OrderListView` để endpoint trả hợp đồng chỉ đọc thay vì partial entity.
5. Thử exclude `items` và so sánh lượng dữ liệu trả về với include projection.
6. Thử projection `shippingAddress.city`, `items.productName`, `$slice` và quan sát cấu trúc JSON.
7. Tạo query tương đương bằng `MongoTemplate.Query.fields()`, đối chiếu kết quả.
8. Tạo index cho bộ lọc/sắp xếp thực tế; dùng `explain("executionStats")` để kiểm tra có `COLLSCAN`/`IXSCAN` và liệu query có được cover.
9. Viết integration test để bảo vệ kết quả DTO/projection và kiểm tra BSON thật sau thay đổi schema.
10. Xem lại bảo mật: điều kiện lọc theo quyền, whitelist field và không xuất dữ liệu nhạy cảm.

## 18. Checklist trước khi đưa `@Query(fields)` vào production

| Câu hỏi | Quy tắc cần xác minh |
| --- | --- |
| Truy vấn đang **lọc** những document nào? | Xem `value` và quyền truy cập, không nhầm với `fields` |
| API cần những field nào? | Ưu tiên include rõ ràng khi hợp đồng trả về cố định |
| Có cần `_id`? | MongoDB include mặc định; bỏ bằng `_id: 0` khi phù hợp |
| Có trộn include/exclude? | Không trộn tùy ý, nhớ ngoại lệ `_id` |
| Có field lồng nhau hoặc mảng? | Dùng dot notation; phân biệt chọn field với chọn phần tử |
| Java object trả về có bị thiếu field? | Không `save` entity partial; ưu tiên view/DTO |
| Tên Java và tên BSON có thống nhất? | Kiểm tra `@Field` và raw BSON, test khi đổi mapping |
| Tập dữ liệu lớn không? | Phân trang, sort, index và giới hạn số document |
| Có giảm dữ liệu truyền thật không? | Quan sát command thực, kích thước kết quả, đo end-to-end |
| Có covered query không? | Kiểm tra index, `_id` và `explain` |
| Có bảo vệ dữ liệu nhạy cảm không? | Authorization, field whitelist và response DTO |
| Có kiểm thử trên MongoDB thực không? | Test repository/template, projection, lồng nhau và hồi quy schema |

**Kết luận:** thuộc tính `fields` trong `@Query` là công cụ trực tiếp của Spring Data MongoDB để yêu cầu MongoDB **chỉ trả những field cần thiết**. Hiểu rõ include/exclude, mặc định `_id`, field lồng nhau và giới hạn mảng giúp truy vấn danh sách gọn hơn, dễ kiểm soát hơn. Kết hợp nó với interface projection/DTO, `MongoTemplate` khi cần truy vấn động, index và `explain` để đo hiệu năng, cùng kiểm thử và kiểm soát quyền truy cập. Quan trọng nhất: **projection chỉ giới hạn dữ liệu đọc, không thay đổi document lưu và không biến một entity tải một phần thành đối tượng an toàn để ghi lại**.

