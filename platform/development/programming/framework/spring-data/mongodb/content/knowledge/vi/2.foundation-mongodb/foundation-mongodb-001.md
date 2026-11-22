# Database, collection, document và cách tổ chức dữ liệu

> **Chương:** Nền tảng MongoDB  
> **Module:** `SPRING_DATA_MONGODB`

Trong MongoDB, dữ liệu được lưu thành các **document BSON** nằm trong **collection** của một **database**. Hiểu đúng ba đơn vị này là bước đầu để thiết kế mô hình dữ liệu phù hợp với truy vấn và ánh xạ sang đối tượng Java bằng Spring Data MongoDB.

Module `SPRING_DATA_MONGODB` hướng đến việc kết nối MongoDB, ánh xạ document và thao tác dữ liệu bằng `MongoTemplate` hoặc repository. Những kỹ năng tiếp theo như thiết kế truy vấn, aggregation, index, transaction, truy cập reactive, kiểm thử và chẩn đoán hiệu năng đều phụ thuộc vào cách tổ chức dữ liệu ban đầu.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt database, collection, document và trường dữ liệu (field); giải thích BSON, `_id` và tính linh hoạt về cấu trúc.
2. Tổ chức dữ liệu cho một nghiệp vụ thực tế; quyết định khi nào nhúng document, khi nào lưu tham chiếu.
3. Viết thao tác cơ bản trong `mongosh` để tạo và đọc dữ liệu, hình dung cách MongoDB lưu trữ.
4. Liên hệ collection và field với `@Document`, `@Id`, `@Field`, `MongoRepository` và `MongoTemplate` trong Spring Data MongoDB.
5. Nhận diện sai lầm phổ biến về kích thước document, kiểu dữ liệu, tính nhất quán và khả năng truy vấn.

## 1. Cấu trúc từ database đến field

```text
MongoDB deployment (máy chủ hoặc cụm)
└── Database: shop
    ├── Collection: customers
    │   ├── Document: {_id: ..., name: ..., email: ...}
    │   └── Document: {_id: ..., name: ..., email: ...}
    ├── Collection: products
    │   └── Document: {_id: ..., sku: ..., price_vnd: ...}
    └── Collection: orders
        ├── Document: {_id: ..., customer_id: ..., items: [...]}
        └── Document: {_id: ..., customer_id: ..., items: [...]}
```

| Thành phần | Chức năng | Ví dụ | Liên hệ khi dùng Spring Data MongoDB |
| --- | --- | --- | --- |
| **Database** | Không gian tên logic chứa nhiều collection | `shop` | Database mà `MongoDatabaseFactory` / cấu hình kết nối trỏ tới |
| **Collection** | Tập hợp các document, có thể có index và quy tắc validation riêng | `orders` | `@Document(collection = "orders")` hoặc tên collection truyền cho `MongoTemplate` |
| **Document** | Đơn vị dữ liệu BSON gồm các cặp tên field và giá trị | Một đơn hàng | Một đối tượng domain được ánh xạ sang document |
| **Field** | Thuộc tính trong document; có thể chứa giá trị đơn, object lồng nhau hoặc array | `status`, `items` | Thuộc tính Java, có thể đổi tên lưu trữ bằng `@Field` |

Có thể hình dung gần đúng database như database trong hệ quản trị quan hệ, collection như bảng và document như hàng. **Đây chỉ là phép so sánh để định vị:** một document có thể chứa object và array lồng nhau, và các document cùng collection không bắt buộc có bộ field giống hệt nhau.

MongoDB không dùng một “bảng con” riêng cho mọi cấu trúc lồng nhau. Nhiều thông tin cần đọc cùng lúc có thể nằm ngay trong một document; vì thế cách chọn ranh giới document quan trọng hơn việc chuyển nguyên xi mô hình bảng quan hệ sang collection.

## 2. Database: ranh giới tổ chức ở mức cao

Một database gom các collection phục vụ một phạm vi dữ liệu. Chẳng hạn `shop` chứa `customers`, `products` và `orders`; một hệ thống khác có thể có database `analytics` cho dữ liệu phân tích.

- **Tên và phạm vi:** mỗi collection thuộc một database cụ thể. Hai database có thể cùng có collection tên `orders` nhưng đó là hai collection khác nhau.
- **Kết nối và quyền:** ứng dụng cần chọn đúng database và được cấp quyền phù hợp. Tách database có thể hỗ trợ quản trị và phân quyền, nhưng **không tự bảo đảm cách ly tài nguyên vật lý**, bởi nhiều database có thể nằm trên cùng triển khai MongoDB.
- **Tạo dữ liệu:** lệnh `use shop` trong `mongosh` chỉ chọn database hiện hành. Database thường được tạo thực tế khi có dữ liệu hoặc collection được tạo, nếu tài khoản có quyền.

Ví dụ trong `mongosh`:

```javascript
use shop
db.getName()               // "shop"
db.createCollection("orders")
show collections
```

Trong ứng dụng Java, database được xác định từ cấu hình kết nối hoặc `MongoDatabaseFactory`; annotation `@Document` chỉ định **collection**, không chọn database độc lập cho từng entity. Muốn làm việc với nhiều database thì phải cấu hình cơ chế tương ứng một cách tường minh.

**Quy tắc thực hành:** chọn ranh giới database theo yêu cầu triển khai, quyền truy cập và vận hành; thiết kế collection/document theo cách nghiệp vụ đọc và cập nhật dữ liệu.

## 3. Collection: nơi nhóm document theo mục đích truy vấn

Collection chứa các document cùng một vai trò nghiệp vụ, ví dụ `orders` chứa đơn hàng. MongoDB cho phép các document trong một collection có cấu trúc khác nhau, nhưng điều đó **không có nghĩa nên trộn mọi loại dữ liệu vào một collection**.

Một collection có thể có:

- **Index** để hỗ trợ lọc và sắp xếp; mỗi collection bình thường có index duy nhất trên `_id`.
- **Schema validation** để kiểm tra kiểu hoặc cấu trúc document được ghi; mặc định MongoDB không đòi hỏi mọi document có schema giống nhau.
- **Tùy chọn tạo collection** cho những nhu cầu đặc thù. Bài này tập trung vào collection thông thường.

Ví dụ hai document đơn hàng có thể khác nhau về field tùy chọn:

```javascript
db.orders.insertMany([
  {
    customer_id: "CUS-001",
    status: "CREATED",
    channel: "WEB",
    total_vnd: 350000
  },
  {
    customer_id: "CUS-002",
    status: "PAID",
    total_vnd: 820000,
    coupon_code: "WELCOME"
  }
])
```

Việc thiếu `coupon_code` ở đơn đầu tiên là hợp lệ khi chưa đặt quy tắc bắt buộc. Tuy nhiên, nếu ứng dụng mong đợi `total_vnd` luôn là số và `status` thuộc một tập trạng thái đã định nghĩa, cần duy trì hợp đồng dữ liệu ở lớp ứng dụng và cân nhắc validator ở database.

Ví dụ kiểm soát một phần cấu trúc khi **tạo collection mới**:

```javascript
db.createCollection("orders", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["customer_id", "status", "total_vnd"],
      properties: {
        customer_id: { bsonType: "string" },
        status: { enum: ["CREATED", "PAID", "CANCELLED"] },
        total_vnd: { bsonType: ["int", "long"], minimum: 0 }
      }
    }
  }
})
```

Đoạn trên dùng cho **collection chưa tồn tại**. Nếu đã chạy `db.createCollection("orders")` ở ví dụ trước, hãy thử validator trong database thực hành mới hoặc dùng `collMod` để cập nhật collection hiện có. Validator cần được điều chỉnh theo nghiệp vụ thực tế, ví dụ trạng thái trả hàng, số tiền hoàn lại và cách lưu giá trị tiền.

## 4. Document BSON: dữ liệu và ranh giới cập nhật

**Document** là một tập các cặp field–value. MongoDB lưu bằng BSON (Binary JSON), hỗ trợ các loại như string, boolean, số nguyên 32/64 bit, double, `Decimal128`, date, `ObjectId`, object lồng nhau và array.

Ví dụ một đơn hàng đầy đủ hơn:

```javascript
use shop

db.orders.insertOne({
  _id: ObjectId("66a000000000000000000001"),
  customer_id: "CUS-001",
  status: "PAID",
  created_at: ISODate("2026-01-15T08:30:00Z"),
  items: [
    { sku: "KB-01", quantity: 1, unit_price_vnd: NumberLong(350000) },
    { sku: "MS-02", quantity: 2, unit_price_vnd: NumberLong(120000) }
  ],
  shipping_address: {
    recipient: "Nguyen A",
    city: "Ha Noi"
  },
  total_vnd: NumberLong(590000)
})
```

Ở ví dụ này:

- `_id` nhận diện duy nhất đơn hàng **trong collection `orders`**. Nếu không cung cấp `_id` khi insert, driver thường tạo giá trị `ObjectId`. MongoDB cũng cho phép kiểu `_id` khác; không nên mặc định tất cả ID đều là `ObjectId`.
- `created_at` là giá trị BSON Date (thông qua `ISODate` trong `mongosh`), khác với chuỗi văn bản ghi ngày. BSON Date lưu thời điểm theo UTC; giao diện có thể hiển thị theo múi giờ người dùng.
- `items` là array gồm các object lồng nhau. Dòng hàng nằm cùng document đơn hàng để có thể đọc một đơn mà không ghép thêm các bản ghi dòng hàng.
- `shipping_address` là object lồng nhau mô tả địa chỉ giao hàng tại thời điểm mua.
- `total_vnd` và `unit_price_vnd` dùng số nguyên 64 bit để biểu diễn số tiền VND, tránh sai số làm tròn của số chấm động trong ví dụ. Với tiền có phần thập phân, có thể chọn đơn vị nhỏ nhất hoặc `Decimal128` theo quy ước nhất quán.

**Hai giới hạn thiết kế cần nhớ:** document BSON thông thường có kích thước tối đa **16 MiB**, và một thao tác ghi trên **một document** có tính nguyên tử. Không nên suy ra rằng nhiều document trong các collection khác nhau luôn cập nhật nguyên tử như một đơn vị; trường hợp đó cần xem xét transaction hoặc thiết kế lại ranh giới dữ liệu.

> **Lưu ý về cú pháp:** `ObjectId(...)`, `ISODate(...)` và `NumberLong(...)` là cách biểu diễn kiểu dữ liệu trong `mongosh`; chúng không phải cú pháp JSON thuần. Dữ liệu lưu trên máy chủ là BSON.

### Truy cập field và array

```javascript
// Tìm đơn của một khách hàng, mới nhất trước.
db.orders
  .find(
    { customer_id: "CUS-001" },
    { _id: 1, status: 1, created_at: 1, total_vnd: 1 }
  )
  .sort({ created_at: -1 })
  .limit(20)

// Truy vấn field trong object của một phần tử array.
db.orders.find({ "items.sku": "KB-01" })

// Truy vấn field của object lồng nhau.
db.orders.find({ "shipping_address.city": "Ha Noi" })
```

**Dot notation** (ví dụ `items.sku`) cho phép truy vấn theo đường dẫn field trong document. Với nhiều điều kiện phải cùng đúng trên **một phần tử array**, dùng `$elemMatch`; các điều kiện dot notation độc lập có thể khớp ở những phần tử array khác nhau.

```javascript
db.orders.find({
  items: {
    $elemMatch: { sku: "KB-01", quantity: { $gte: 1 } }
  }
})
```

## 5. Thiết kế dữ liệu theo cách ứng dụng sử dụng

Giả sử hệ thống bán hàng có ba nhóm dữ liệu chính:

- `customers`: hồ sơ khách hàng, có thể thay đổi tên hoặc thông tin liên hệ.
- `products`: thông tin sản phẩm, giá hiện hành và tồn kho.
- `orders`: giao dịch đã đặt, gồm trạng thái, dòng hàng, giá đã chốt và địa chỉ giao tại thời điểm mua.

Hai cách tổ chức quan hệ thường gặp là **embedding** (nhúng dữ liệu) và **referencing** (lưu ID tham chiếu).

### 5.1. Nhúng (embedding)

Nhúng khi dữ liệu con thuộc về một thực thể chính, thường được đọc cùng nhau và kích thước có thể kiểm soát được. Ví dụ `items` và `shipping_address` được nhúng trong `orders`.

Ưu điểm:

- Đọc một đơn hàng cùng các dòng hàng trong một document.
- Có thể cập nhật các field trong một đơn hàng bằng một thao tác ghi nguyên tử.
- Lưu lại thông tin “chụp tại thời điểm đặt hàng”, như đơn giá và địa chỉ giao, kể cả khi hồ sơ sản phẩm hoặc khách hàng thay đổi.

Đánh đổi:

- Thông tin được lặp lại giữa các đơn; muốn sửa thông tin lịch sử trên diện rộng phải cập nhật nhiều document.
- Array có thể tăng không giới hạn nếu chọn nhúng sai, gây document lớn và thao tác ghi nặng.

**Ví dụ tốt:** vài dòng hàng của mỗi đơn. **Ví dụ rủi ro:** nhúng toàn bộ hàng triệu đơn hàng vào một document khách hàng.

### 5.2. Tham chiếu (referencing)

Lưu ID khi thực thể được sử dụng độc lập, chia sẻ bởi nhiều document, thường xuyên thay đổi hoặc có tập quan hệ phát triển lớn.

Trong `orders`, field `customer_id` trỏ đến khách hàng, và `items.sku` nhận diện sản phẩm. Ứng dụng có thể cần truy vấn thêm `customers` hoặc `products` khi cần dữ liệu hiện tại.

Ưu điểm là tránh nhân bản những dữ liệu lớn hoặc luôn thay đổi. Đánh đổi là thao tác đọc có thể phải gọi nhiều truy vấn hoặc dùng `$lookup` trong aggregation; tính nhất quán giữa nhiều document cần được xử lý tường minh.

Spring Data MongoDB hỗ trợ các cơ chế tham chiếu như `@DBRef` hoặc `@DocumentReference`, nhưng không nên mặc định rằng chúng tự tạo cascade write hay làm quan hệ giống khóa ngoại SQL. Với các liên kết đơn giản, **lưu ID tường minh** thường dễ kiểm soát luồng đọc, ghi và hiệu năng hơn.

### 5.3. Quy tắc quyết định

| Câu hỏi về dữ liệu con | Thiên về nhúng | Thiên về tham chiếu |
| --- | --- | --- |
| Có luôn đọc cùng dữ liệu cha? | Có | Ít khi |
| Kích thước/tổng số phần tử có giới hạn hợp lý? | Có | Tăng liên tục, khó giới hạn |
| Có cần cập nhật cùng cha trong một thao tác nguyên tử? | Có | Không thường xuyên |
| Có được nhiều thực thể khác cùng sử dụng? | Ít | Nhiều |
| Có cần dữ liệu lịch sử tại thời điểm giao dịch? | Có, lưu snapshot | Khi cần truy cập trạng thái hiện tại |

Không có quy tắc “nhúng luôn nhanh hơn” hoặc “tham chiếu luôn chuẩn hơn”. Ranh giới tốt phụ thuộc **mẫu truy vấn, vòng đời dữ liệu, số lượng phần tử, tần suất cập nhật và yêu cầu nhất quán**.

## 6. Một thiết kế đơn hàng có thể mở rộng

Đối với hệ thống ví dụ, ta dùng:

```text
shop
├── customers
│   └── {_id, name, email, ...}
├── products
│   └── {_id, sku, name, current_price_vnd, stock, ...}
└── orders
    └── {
          _id,
          customer_id,               // tham chiếu khách hàng
          status,
          created_at,
          items: [
            {sku, quantity, unit_price_vnd}, // snapshot dòng hàng
            ...
          ],
          shipping_address: {...},   // snapshot địa chỉ giao
          total_vnd
        }
```

Ở đây, đơn hàng lưu `sku` để biết mua sản phẩm nào nhưng đồng thời lưu `unit_price_vnd` vì giá giao dịch không được tự động đổi khi giá niêm yết trong `products` thay đổi. Nếu tên sản phẩm phải xuất hiện chính xác như lúc mua trên hóa đơn, có thể lưu thêm `product_name` trong từng dòng hàng.

Ví dụ các tình huống truy cập:

| Nhu cầu | Collection chính | Hướng thiết kế |
| --- | --- | --- |
| Xem chi tiết một đơn | `orders` | Nhúng `items`, `shipping_address` để đọc cùng đơn |
| Liệt kê 20 đơn gần nhất của khách | `orders` | Lọc `customer_id`, sắp xếp `created_at` giảm dần |
| Sửa email khách hàng | `customers` | Cập nhật hồ sơ độc lập; không cần sửa lịch sử đơn |
| Thay đổi giá bán hiện tại | `products` | Chỉ sửa sản phẩm; giữ nguyên giá đã chốt trong đơn cũ |
| Báo cáo doanh thu theo tháng | `orders` | Aggregation theo ngày/trạng thái với chỉ mục phù hợp |

**Nguyên tắc:** chọn mô hình document theo dữ liệu cần đọc và cập nhật **cùng nhau**, chứ không chỉ theo sơ đồ lớp Java hoặc số bảng trong một cơ sở dữ liệu quan hệ sẵn có.

## 7. Ánh xạ sang Spring Data MongoDB

Spring Data MongoDB dùng mapping để biến document BSON thành đối tượng Java. Với thiết kế đơn hàng trên, có thể dùng Java record cho ví dụ ngắn gọn:

```java
import java.time.Instant;
import java.util.List;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document(collection = "orders")
public record Order(
    @Id String id,
    @Field("customer_id") String customerId,
    String status,
    @Field("created_at") Instant createdAt,
    List<OrderLine> items,
    @Field("shipping_address") ShippingAddress shippingAddress,
    @Field("total_vnd") long totalVnd
) {}

record OrderLine(
    String sku,
    int quantity,
    @Field("unit_price_vnd") long unitPriceVnd
) {}

record ShippingAddress(String recipient, String city) {}
```

Những điểm cần hiểu:

- `@Document(collection = "orders")` ánh xạ entity `Order` sang collection `orders`. Không có annotation này, Spring Data có quy tắc mặc định để xác định tên collection, nhưng dùng tên tường minh giúp tránh lệch khi refactor.
- `@Id` đánh dấu thuộc tính ánh xạ tới field MongoDB `_id`. Với `String`, Spring Data có cơ chế chuyển đổi ID sang `ObjectId` khi có thể; khi thiết kế API, cần quy định và kiểm thử kiểu ID nhất quán.
- `@Field("customer_id")` ánh xạ thuộc tính Java `customerId` sang field lưu trữ `customer_id`. Các annotation tương tự giải quyết khác biệt đặt tên giữa Java và BSON.
- `List<OrderLine>` được ánh xạ thành array của các document lồng nhau; `ShippingAddress` thành object lồng nhau.
- Với `Instant`, dữ liệu tương ứng được chuyển đổi sang kiểu thời gian MongoDB thông qua mapping/conversion. Cần thống nhất cách xử lý múi giờ và độ chính xác thời gian trong toàn ứng dụng.

Một repository đơn giản:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository extends MongoRepository<Order, String> {
    Page<Order> findByCustomerIdOrderByCreatedAtDesc(
        String customerId, Pageable pageable);
}
```

Spring Data suy ra truy vấn từ **tên thuộc tính Java** (`customerId`, `createdAt`), sau đó ánh xạ sang field thực tế (`customer_id`, `created_at`). Truy vấn tương đương có thể được xây dựng bằng `MongoTemplate`:

```java
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class OrderQueryService {
    private final MongoTemplate mongoTemplate;

    public OrderQueryService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public List<Order> latestOrders(String customerId) {
        Query query = Query.query(Criteria.where("customerId").is(customerId))
            .with(Sort.by(Sort.Direction.DESC, "createdAt"))
            .limit(20);
        return mongoTemplate.find(query, Order.class);
    }
}
```

`MongoTemplate` sử dụng metadata mapping của `Order` để xác định collection và tên field tương ứng. Ở ví dụ này, Spring tự inject `MongoTemplate` qua constructor của service.

### Repository và MongoTemplate chọn thế nào?

`MongoRepository` thích hợp khi thao tác dựa trên entity với các phương thức CRUD và derived query phổ biến. `MongoTemplate` hữu ích khi cần điều khiển chi tiết filter, update, bulk operation, aggregation hoặc cách thực thi truy vấn. Cả hai cùng làm việc trên các collection/document MongoDB; chúng không đòi hỏi hai kiểu lưu trữ dữ liệu khác nhau.

## 8. Tổ chức dữ liệu để truy vấn hiệu quả

Một thiết kế document hợp lý vẫn cần index theo cách truy cập. Ví dụ ứng dụng thường liệt kê đơn của khách, chỉ lấy trạng thái đã thanh toán và sắp xếp mới nhất:

```javascript
db.orders
  .find({ customer_id: "CUS-001", status: "PAID" })
  .sort({ created_at: -1 })
  .limit(20)

db.orders.createIndex({
  customer_id: 1,
  status: 1,
  created_at: -1
})
```

Index ghép này là **ứng viên** cho mẫu truy vấn trên: các field lọc bằng điều kiện bằng nhau đứng trước, tiếp theo là field sắp xếp. Không nên tạo index chỉ vì một field tồn tại; index tiêu tốn dung lượng và làm tăng chi phí ghi.

Kiểm tra kế hoạch thực thi trong môi trường có dữ liệu đại diện:

```javascript
db.orders
  .find({ customer_id: "CUS-001", status: "PAID" })
  .sort({ created_at: -1 })
  .explain("executionStats")
```

Quan sát chỉ số như `totalDocsExamined`, `totalKeysExamined` và thời gian thực thi, đồng thời xem kế hoạch có dùng index phù hợp hay không. Một ví dụ chạy trên vài document không đủ để kết luận hiệu năng khi hệ thống có hàng triệu đơn.

Các điểm cần cân nhắc thêm:

- Truy vấn thường xuyên trên `items.sku` có thể cần index trên đường dẫn đó; với array, MongoDB tạo **multikey index** theo quy tắc tương ứng.
- Array quá lớn hoặc tăng mãi có thể khiến document phình ra, dù đã có index. Khi đó hãy tách dữ liệu theo collection phù hợp.
- Tên field, kiểu dữ liệu và cách lưu thời gian phải nhất quán để việc lọc, sort, aggregation và mapping không phát sinh sai lệch khó tìm.
- Dữ liệu nhạy cảm phải tuân theo quy định truy cập và bảo vệ dữ liệu của hệ thống; chọn document/collection không thay thế kiểm soát quyền.

## 9. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Coi collection như bảng SQL và tách mọi object con thành collection riêng | Phải truy vấn/ghép nhiều lần khi xem một thực thể | Nhúng dữ liệu con có vòng đời gắn chặt và kích thước giới hạn |
| Nhúng danh sách có thể tăng vô hạn vào một document | Document tăng lớn, tiệm cận giới hạn 16 MiB, cập nhật khó | Phân trang bằng collection riêng hoặc thiết kế dữ liệu theo giới hạn tăng trưởng |
| Đổi kiểu `total_vnd` giữa số và chuỗi | Lọc, so sánh và tổng hợp sai hoặc khó dự đoán | Chuẩn hóa kiểu số, kiểm tra đầu vào, áp dụng schema validation phù hợp |
| Dùng `double` tùy tiện cho tiền | Rủi ro sai số chấm động | Dùng số nguyên đơn vị nhỏ nhất hoặc `Decimal128` theo quy ước |
| Chỉ lưu mã sản phẩm rồi luôn đọc giá hiện tại khi xem đơn cũ | Lịch sử thanh toán bị diễn giải sai | Lưu snapshot giá và thông tin cần bất biến tại thời điểm mua |
| Cho rằng `@DBRef` tự bảo đảm khóa ngoại/cascade như JPA | Dữ liệu tham chiếu có thể thiếu hoặc không được cập nhật theo ý muốn | Thiết kế kiểm tra tồn tại, cập nhật và tính nhất quán tại lớp nghiệp vụ |
| Tạo index cho mọi field hoặc bỏ qua mẫu truy vấn | Tốn tài nguyên ghi hoặc đọc chậm | Dựa vào truy vấn thực tế và `explain("executionStats")` |
| Tưởng `use shop` đã tạo và ghi database | Không thấy database trong danh sách sau khi chưa ghi dữ liệu | Thực hiện tạo collection/ghi thử và kiểm tra kết quả |

## 10. Quy trình thiết kế khi bắt đầu một tính năng

1. **Liệt kê các màn hình và thao tác:** xem chi tiết, lọc danh sách, cập nhật trạng thái, thống kê.
2. **Xác định document gốc:** nhóm những field cần đọc/ghi cùng nhau; đặt giới hạn hợp lý cho các array.
3. **Chọn nhúng hay tham chiếu:** xét quan hệ sở hữu, mức độ chia sẻ, lịch sử dữ liệu và tốc độ tăng trưởng.
4. **Định nghĩa hợp đồng dữ liệu:** tên field, kiểu BSON, `_id`, field bắt buộc, giá trị tùy chọn và quy tắc chuyển đổi.
5. **Đặt collection và index:** ưu tiên truy vấn trọng yếu, tránh index trùng lặp; cân nhắc validator khi cần.
6. **Ánh xạ Java:** dùng `@Document`, `@Id`, `@Field`, entity lồng nhau và repository/`MongoTemplate` nhất quán.
7. **Thử với dữ liệu đại diện:** xác nhận insert/read/update, cách map kiểu dữ liệu, truy vấn array và hiệu năng bằng `explain`.

### Tình huống tự đối chiếu

Hệ thống cần hiển thị một đơn gồm năm dòng hàng và địa chỉ giao, cho phép người dùng xem lại đơn sau nhiều năm. Người quản trị đồng thời phải sửa thông tin sản phẩm và hồ sơ khách hàng hiện tại.

Thiết kế phù hợp thường là giữ `orders` độc lập, **nhúng năm dòng hàng cùng snapshot địa chỉ/đơn giá**, nhưng **tham chiếu** `customers` và `products` bằng ID hoặc SKU để truy cập dữ liệu hiện hành. Lựa chọn này làm thao tác xem đơn đơn giản và bảo vệ lịch sử giao dịch khỏi những thay đổi về sau.

## Ghi nhớ

**Database** phân chia phạm vi dữ liệu; **collection** nhóm các document cùng mục đích; **document BSON** là đơn vị lưu trữ và cập nhật nguyên tử. MongoDB cho phép document linh hoạt về cấu trúc, nhưng ứng dụng vẫn cần hợp đồng dữ liệu rõ ràng. Trong Spring Data MongoDB, mô hình document quyết định cách ánh xạ Java, lựa chọn repository hay `MongoTemplate`, chiến lược index và giới hạn hiệu năng khi dữ liệu tăng lên.
