# Biểu diễn và phân giải @DBRef

> **Chương:** Tham chiếu tài liệu  
> **Module:** `SPRING_DATA_MONGODB`

Trong MongoDB, một document có thể **nhúng** dữ liệu liên quan hoặc giữ **tham chiếu** đến document khác. Khi một ứng dụng Java dùng Spring Data MongoDB muốn ánh xạ thuộc tính dạng đối tượng nhưng lưu dưới dạng tham chiếu, annotation `@DBRef` là một lựa chọn. Thay vì lưu toàn bộ document được tham chiếu, Spring Data lưu một giá trị theo định dạng **DBRef** gồm tên collection và khóa định danh. Khi đọc, Spring Data có thể dùng thông tin đó để tìm và ánh xạ document đích trở lại đối tượng Java.

Điểm cần phân biệt ngay từ đầu: **DBRef là quy ước biểu diễn tham chiếu trong BSON, không phải khóa ngoại của MongoDB và không tự tạo phép nối do máy chủ thực hiện**. Spring Data MongoDB mới là thành phần giải tham chiếu khi sử dụng `MongoTemplate` hoặc repository. Hiểu cơ chế này giúp tránh các lỗi về số lượt truy vấn, dữ liệu tham chiếu đã bị xóa và giả định sai về tự động lưu lan truyền.

Bài học thuộc module `SPRING_DATA_MONGODB`, nơi người học kết nối MongoDB, ánh xạ document, sử dụng `MongoTemplate` hoặc repository và tiếp tục với truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng. Nội dung ở đây tập trung trực tiếp vào **biểu diễn và phân giải `@DBRef`**, làm nền cho việc lựa chọn cách thiết kế quan hệ giữa các document.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Đọc được cấu trúc BSON của DBRef với `$ref`, `$id` và `$db`; phân biệt với ID thuần và document nhúng.
2. Khai báo `@DBRef` trong entity Java, lưu đúng thứ tự dữ liệu liên quan và đọc lại bằng Spring Data MongoDB.
3. Giải thích đường đi của truy vấn khi phân giải tham chiếu, chế độ mặc định và `lazy = true`.
4. Nhận diện giới hạn về cascade, toàn vẹn tham chiếu, transaction, N+1 query, vòng tham chiếu và JSON serialization.
5. So sánh `@DBRef` với nhúng document, lưu ID thủ công và `@DocumentReference` để chọn giải pháp phù hợp.

## 2. Từ quan hệ nghiệp vụ đến tham chiếu MongoDB

Giả sử hệ thống bán hàng có hai loại dữ liệu:

- **Customer:** hồ sơ khách hàng có thể được sử dụng cho nhiều đơn hàng.
- **Order:** đơn hàng có trạng thái, thời điểm tạo, số tiền và thông tin khách hàng liên quan.

Hai document có vòng đời khác nhau. Một khách hàng có thể có hàng nghìn đơn; nhúng toàn bộ lịch sử đơn vào customer dễ tạo array lớn và gây tranh chấp cập nhật. Mặt khác, nhúng toàn bộ hồ sơ customer vào mỗi order dẫn đến dữ liệu bị nhân bản và khó cập nhật nhất quán. Đối với một số luồng sử dụng, lưu tham chiếu từ order đến customer là lựa chọn hợp lý.

```text
Database: shop

customers                          orders
┌───────────────────────┐          ┌────────────────────────────┐
│ _id: ObjectId(C1)     │          │ _id: ObjectId(O1)          │
│ name: "An"            │ <------- │ customer: DBRef(C1)        │
│ email: "an@..."       │          │ orderCode: "ORD-001"       │
└───────────────────────┘          │ totalMinor: 450000         │
                                   └────────────────────────────┘

Một customer có thể được nhiều order tham chiếu.
```

MongoDB không buộc kiểu dữ liệu của document trong collection phải phụ thuộc lẫn nhau như khóa ngoại SQL. Nếu customer bị xóa, một DBRef trong order có thể vẫn tồn tại và trở thành **dangling reference** (tham chiếu không còn đích).

## 3. Định dạng BSON DBRef: $ref, $id và $db

DBRef có cấu trúc logic:

```javascript
{
  "$ref": "customers",
  "$id": ObjectId("66a000000000000000000101"),
  "$db": "shop"
}
```

Trong đó:

| Thành phần | Bắt buộc? | Ý nghĩa | Ví dụ |
| --- | --- | --- | --- |
| `$ref` | Có | Tên **collection đích** | `"customers"` |
| `$id` | Có | Giá trị **`_id` của document đích**, giữ kiểu BSON của khóa | `ObjectId("...")`, string, số... |
| `$db` | Không | Tên **database đích** nếu cần chỉ rõ | `"shop"` |

Các trường điều khiển của DBRef thường được biểu diễn theo thứ tự `$ref`, `$id`, rồi `$db` nếu có. MongoDB driver và một số công cụ có thể hiển thị dạng trợ giúp như `DBRef("customers", ObjectId("..."))`; đó vẫn là cùng ý tưởng tham chiếu, không phải document customer được nhúng.

Ví dụ hai collection ở cùng database:

```javascript
use shop

db.customers.insertOne({
  _id: ObjectId("66a000000000000000000101"),
  name: "Nguyen An",
  email: "an@example.com"
})

db.orders.insertOne({
  _id: ObjectId("66a000000000000000000201"),
  orderCode: "ORD-001",
  totalMinor: NumberLong(450000),
  customer: {
    "$ref": "customers",
    "$id": ObjectId("66a000000000000000000101")
  }
})
```

Đây là thao tác `mongosh` tạo dữ liệu minh họa. Giá trị `customer` trong `orders` **không chứa** `name` hoặc `email`. Chỉ bằng cách đọc `orders` ở tầng MongoDB, ta chưa có toàn bộ thông tin khách hàng.

### 3.1. Minh họa cách giải tham chiếu thủ công

```javascript
const order = db.orders.findOne({ orderCode: "ORD-001" });

// Theo quy ước DBRef, collection trong $ref và id trong $id
// xác định nơi cần đọc document đích.
const customer = db.customers.findOne({
  _id: order.customer.$id
});

printjson(customer);
```

Kết quả đọc customer là một thao tác truy vấn khác. Trong ví dụ, ta đã **biết** collection đích là `customers`; khi viết công cụ xử lý DBRef tổng quát, không nên lấy giá trị `$ref` không tin cậy rồi chạy truy vấn đến collection tùy ý mà không kiểm soát.

**Khác với DBRef**, nếu `orders` chỉ có `customerId: ObjectId("...")` thì ứng dụng cần tự biết ID đó thuộc collection `customers`. DBRef mang theo thông tin collection; ID thuần không mang thông tin đó.

### 3.2. $db có ý nghĩa gì?

Khi `$db` bị lược bỏ, tham chiếu thường được diễn giải trong database hiện tại của hoạt động đọc. Khi có `$db`, DBRef có thể chỉ đến collection ở một database khác trên **cùng phạm vi kết nối MongoDB tương thích**. Nó **không** chứa URI, thông tin xác thực hay địa chỉ một cụm MongoDB độc lập.

Spring Data phải có cấu hình driver, quyền và cách giải DBRef phù hợp mới có thể đọc đích. Một DBRef có `$db` không có nghĩa MongoDB tự thiết lập kết nối đến server khác hoặc tự cấp quyền truy cập database được ghi trong metadata.

### 3.3. DBRef khác với khóa ngoại và $lookup

- DBRef là **dữ liệu tham chiếu**; MongoDB không tự kiểm tra `$id` đã tồn tại khi ghi.
- `MongoTemplate`/repository sử dụng mapping để đọc đích trong quá trình chuyển BSON → Java.
- `$lookup` là một **aggregation stage phía MongoDB server** dùng để ghép dữ liệu; DBRef **không** tự sinh ra `$lookup` cho mọi truy vấn.
- Không có cascade save/delete hoặc ràng buộc khóa ngoại tự động chỉ nhờ `@DBRef`.

Vì thế, thiết kế dữ liệu phải quy định cách xử lý document đích bị xóa, lỗi mạng khi phân giải và giới hạn độ trễ khi có nhiều tham chiếu.

## 4. Ánh xạ @DBRef trong Spring Data MongoDB

Một ví dụ tự chứa sử dụng Java, Spring Data MongoDB và các repository thông thường.

### 4.1. Entity Customer

File `Customer.java`:

```java
package com.example.shop.customer;

import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "customers")
public class Customer {
    @Id
    private ObjectId id;

    private String name;
    private String email;

    protected Customer() {}

    public Customer(String name, String email) {
        this.name = name;
        this.email = email;
    }

    public ObjectId getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }
}
```

`@Document(collection = "customers")` xác định collection và `@Id` ánh xạ `id` tới `_id`. Ví dụ dùng `ObjectId` tường minh để tránh nhầm lẫn giữa ID string và BSON ObjectId khi quan sát cấu trúc `$id`.

### 4.2. Entity Order với @DBRef

File `Order.java`:

```java
package com.example.shop.order;

import com.example.shop.customer.Customer;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.DBRef;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public class Order {
    @Id
    private ObjectId id;

    private String orderCode;
    private long totalMinor;

    @DBRef
    private Customer customer;

    protected Order() {}

    public Order(String orderCode, long totalMinor, Customer customer) {
        this.orderCode = orderCode;
        this.totalMinor = totalMinor;
        this.customer = customer;
    }

    public ObjectId getId() {
        return id;
    }

    public String getOrderCode() {
        return orderCode;
    }

    public long getTotalMinor() {
        return totalMinor;
    }

    public Customer getCustomer() {
        return customer;
    }
}
```

`@DBRef` nằm trên field `customer`, có type Java là `Customer`. Khi lưu `Order`, Spring Data dùng thông tin `@Document` và ID của customer để tạo DBRef trong document order. Khi đọc `Order`, converter có thể lấy document customer đích và ánh xạ lại thành `Customer`.

Trong thiết kế này, `Customer` cần được lưu và có ID phù hợp **trước khi** lưu `Order`; annotation không tự gọi `save(customer)`.

### 4.3. Khai báo repository

File `CustomerRepository.java`:

```java
package com.example.shop.customer;

import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface CustomerRepository
        extends MongoRepository<Customer, ObjectId> {
}
```

File `OrderRepository.java`:

```java
package com.example.shop.order;

import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<Order, ObjectId> {
}
```

Hai repository làm việc với hai collection tương ứng. Việc chúng cùng được đăng ký trong Spring context phụ thuộc cấu hình repository scan/auto-configuration của ứng dụng; `@DBRef` không tự khai báo hoặc đăng ký repository.

### 4.4. Lưu đúng thứ tự và đọc lại

File `OrderApplicationService.java`:

```java
package com.example.shop.order;

import com.example.shop.customer.Customer;
import com.example.shop.customer.CustomerRepository;
import org.bson.types.ObjectId;
import org.springframework.stereotype.Service;

@Service
public class OrderApplicationService {
    private final CustomerRepository customers;
    private final OrderRepository orders;

    public OrderApplicationService(
            CustomerRepository customers,
            OrderRepository orders) {
        this.customers = customers;
        this.orders = orders;
    }

    public Order createExampleOrder() {
        Customer customer = customers.save(
            new Customer("Nguyen An", "an@example.com")
        );

        // customer đã có _id nên DBRef có khóa đích hợp lệ.
        Order order = new Order("ORD-002", 450000L, customer);
        return orders.save(order);
    }

    public String customerName(ObjectId orderId) {
        Order order = orders.findById(orderId)
            .orElseThrow(() -> new IllegalArgumentException(
                "Không tìm thấy đơn hàng: " + orderId));

        Customer customer = order.getCustomer();
        if (customer == null) {
            throw new IllegalStateException(
                "Đơn hàng thiếu tham chiếu khách hàng hợp lệ");
        }
        return customer.getName();
    }
}
```

Với mapping mặc định, document sau khi lưu có dạng tương tự:

```javascript
{
  _id: ObjectId("66a000000000000000000202"),
  orderCode: "ORD-002",
  totalMinor: NumberLong(450000),
  customer: {
    "$ref": "customers",
    "$id": ObjectId("66a000000000000000000102")
  },
  _class: "com.example.shop.order.Order"
}
```

Các giá trị ObjectId trong ví dụ BSON chỉ minh họa cấu trúc, không phải ID thật do lần gọi `save` phía trên nhất thiết tạo ra. Field `_class` là metadata mapping mặc định của Spring Data (có thể thay đổi nếu cấu hình type mapping khác); nó **không phải thành phần của DBRef**.

## 5. Spring Data phân giải DBRef như thế nào?

Khi đọc một `Order` qua repository hoặc `MongoTemplate`, quy trình khái quát là:

```text
OrderRepository.findById(orderId)
        │
        ▼
MongoDB: find trong collection orders
        │
        ▼
BSON { customer: { $ref: "customers", $id: C1 } }
        │
        ▼
MappingMongoConverter nhận biết field @DBRef
        │
        ├── Mặc định eager: lấy Customer(C1) trong lúc ánh xạ Order
        │
        └── lazy=true: tạo proxy, trì hoãn việc lấy Customer
        │
        ▼
Order.getCustomer() → Customer đã giải hoặc proxy
```

Khi **eager** (mặc định), converter cần đọc document đích trong quá trình chuyển đổi dữ liệu sang Java. Mỗi DBRef thường dẫn đến nhu cầu lấy thêm dữ liệu, nhưng số lệnh thực tế có thể khác nhau tùy cách Spring Data gom tải, số loại collection, bộ nhớ đệm và đường truy cập.

Spring Data sử dụng metadata `$ref` và `$id` để định vị đích rồi chuyển BSON sang class tương ứng; máy chủ MongoDB không tự thay DBRef bằng document khi `find` trên orders.

### 5.1. Phân giải một tham chiếu

Ví dụ phần dữ liệu order chứa:

```javascript
customer: {
  "$ref": "customers",
  "$id": ObjectId("66a000000000000000000101")
}
```

Muốn phân giải cần tìm document có `_id` tương ứng trong `customers`:

```javascript
db.customers.findOne({
  _id: ObjectId("66a000000000000000000101")
})
```

MongoDB tạo index duy nhất trên `_id` ở collection thông thường nên việc lấy **một** document theo ID thường hiệu quả. Nhưng nếu ứng dụng phải giải hàng nghìn tham chiếu, chi phí có thể đến từ **số lượt gọi, network round-trip, mapping và kích thước dữ liệu trả về**, không chỉ tốc độ tìm theo từng `_id`.

### 5.2. Đọc document không đồng nghĩa dữ liệu đích luôn còn tồn tại

Một DBRef hợp lệ về hình thức không đảm bảo document đích tồn tại hoặc người dùng có quyền đọc nó. Có thể gặp:

- ID đã bị xóa hoặc dữ liệu đang trong quá trình di chuyển.
- Collection hoặc database được chỉ định khác với kỳ vọng.
- Dữ liệu đích không phù hợp với model Java hiện tại.
- Truy cập thất bại do lỗi kết nối, phân quyền hoặc chế độ lazy dereference.

Không nên mặc định tham chiếu thiếu sẽ luôn trả `null` một cách đồng nhất ở mọi cấu hình/phiên bản và mọi thời điểm truy cập. Hãy xác định chính sách nghiệp vụ khi thiếu đích và có kiểm thử tích hợp cho trường hợp này.

## 6. Eager và lazy: khác nhau về lúc truy vấn

### 6.1. Mặc định: eager

```java
@DBRef
private Customer customer;
```

Spring Data cố gắng phân giải tham chiếu trong quá trình đọc đối tượng chứa nó. Khi giao diện danh sách chỉ hiển thị `orderCode` và `totalMinor`, việc eager load customer có thể tạo thêm I/O không cần thiết.

### 6.2. Trì hoãn bằng lazy = true

```java
@DBRef(lazy = true)
private Customer customer;
```

Với cơ chế lazy reference được hỗ trợ, Spring Data đặt một **proxy** vào property. Dữ liệu khách hàng có thể chưa được truy vấn ngay khi đọc order; việc gọi một phương thức cần nội dung thực của customer có thể kích hoạt truy vấn.

Ví dụ ý tưởng:

```java
Order order = orders.findById(orderId).orElseThrow();

// Có thể chưa đụng tới dữ liệu customer:
String code = order.getOrderCode();

// Có thể kích hoạt phân giải proxy customer:
String name = order.getCustomer().getName();
```

Hai dòng trên chỉ minh họa thời điểm phát sinh truy cập, trong đó `orders` là biến kiểu `OrderRepository` và `orderId` hợp lệ.

**Giới hạn cần nhớ:**

- Lazy proxy không biến DBRef thành một phép nối do MongoDB xử lý. Nó chỉ trì hoãn thời điểm lấy dữ liệu.
- Việc debug, gọi `toString()`, logging, JSON serialization hoặc debugger xem sâu property có thể làm proxy bị kích hoạt ngoài ý muốn.
- Khả năng tạo proxy phụ thuộc vào kiểu của thuộc tính, constructor/finality và cơ chế proxy khả dụng trong phiên bản Spring Data/Java đang chạy. Interface có thể dễ làm proxy hơn một số kiểu không mở rộng được.
- Khi truy cập proxy, tài nguyên truy cập MongoDB và cấu hình ứng dụng phải còn sử dụng được. Không nên đồng nhất hành vi lazy của Spring Data MongoDB với lazy loading của Hibernate.
- Lazy loading cần được **đo và kiểm thử**; không nên tin rằng mọi đường chuyển đổi hoặc serialization đều trì hoãn I/O như nhau.

### 6.3. Chọn eager hay lazy?

| Tiêu chí | Eager `@DBRef` | Lazy `@DBRef(lazy=true)` |
| --- | --- | --- |
| Thời điểm thường lấy đích | Khi đọc đối tượng chứa tham chiếu | Khi proxy cần dữ liệu thực |
| Hữu ích khi | Hầu như luôn cần customer cùng order | Nhiều luồng chỉ dùng thông tin order |
| Rủi ro | Nhiều truy vấn thừa, tăng thời gian đọc | Truy vấn phát sinh muộn, khó phát hiện từ caller |
| API/serialization | Có thể đã có dữ liệu đầy đủ | Serializer có thể kích hoạt proxy và đọc database |
| Bảo đảm tránh N+1 | Không | **Không**, chỉ thay thời điểm phát sinh |

Muốn giảm chắc chắn chi phí đọc, có thể dùng **projection**, DTO hoặc query được thiết kế rõ dữ liệu cần trả. Lazy là một lựa chọn thực thi, không thay thế thiết kế truy vấn.

## 7. @DBRef trên collection/array

Một đơn hàng có thể giữ tham chiếu đến nhiều chứng từ:

```java
import java.util.List;
import org.springframework.data.mongodb.core.mapping.DBRef;

@DBRef(lazy = true)
private List<Attachment> attachments;
```

Giả sử `Attachment` là entity `@Document(collection = "attachments")` với ID đã được lưu. BSON trong document order có thể gồm:

```javascript
attachments: [
  { "$ref": "attachments", "$id": ObjectId("66a000000000000000000301") },
  { "$ref": "attachments", "$id": ObjectId("66a000000000000000000302") }
]
```

Spring Data có thể tối ưu việc tải **tập tham chiếu cùng collection** bằng cách gom các ID cho một lượt truy vấn phù hợp. Ngược lại, một collection tham chiếu trộn nhiều collection đích khó gom tải chung; chi phí có thể cao hơn. Đó là lý do nên tránh các list DBRef pha trộn nhiều loại document/collection khi không có nhu cầu rõ ràng.

**Không nhúng array không giới hạn bằng DBRef rồi cho rằng hoàn toàn không có chi phí:** tuy mỗi phần tử chỉ lưu tham chiếu, độ dài array vẫn làm document gốc lớn lên và việc resolve nhiều phần tử vẫn tốn I/O. Với quan hệ một-nhiều không giới hạn, cân nhắc để collection con giữ `orderId` và truy vấn phân trang.

## 8. @DBRef không tự lưu lan truyền

Một sai lầm dễ gặp là tạo customer chưa có ID rồi chỉ lưu order:

```java
Customer unsaved = new Customer(
    "Nguyen An", "an@example.com");
Order order = new Order("ORD-003", 450000L, unsaved);

// Không có cascade save do @DBRef.
orders.save(order);
```

Đây là **ví dụ phản diện, không nên áp dụng**: tham chiếu đến đối tượng chưa được lưu có thể dẫn đến lỗi mapping/ghi hoặc trạng thái không hợp lệ. Spring Data không tự insert customer và cấp ID chỉ vì order có field `@DBRef`.

Luồng đúng cần lưu đích trước:

```java
Customer savedCustomer = customers.save(
    new Customer("Nguyen An", "an@example.com"));

Order savedOrder = orders.save(
    new Order("ORD-003", 450000L, savedCustomer));
```

Tương tự, chỉnh một customer đang được order tham chiếu **không** có nghĩa `orders.save(order)` tự cập nhật customer:

```java
// Khi muốn cập nhật dữ liệu khách hàng, gọi:
customers.save(customer);
```

Ở đoạn trên, `customer` giả định là entity có ID hợp lệ và đã được chỉnh qua setter/service thích hợp. Mọi trường hợp save/delete/cập nhật đồng bộ nhiều document cần được thiết kế riêng.

### 8.1. Tính nguyên tử và transaction

MongoDB bảo đảm một thao tác ghi trên **một document** là nguyên tử. Nhưng:

1. Ghi customer.
2. Ghi order chứa DBRef tới customer.

Là hai thao tác trên hai document khác nhau. Nếu bước 1 thành công nhưng bước 2 thất bại, có thể còn customer không gắn với order. Nếu nghiệp vụ cần hai thay đổi thành công hoặc thất bại cùng nhau, phải cân nhắc **transaction nhiều document trên triển khai MongoDB hỗ trợ**, cấu hình session và transaction manager phù hợp trong Spring Data MongoDB.

Transaction không được `@DBRef` tự kích hoạt. Trong nhiều tình huống, việc bảo đảm thao tác **idempotent**, dùng khóa nghiệp vụ rõ ràng và có quy trình sửa dữ liệu chưa hoàn tất sẽ phù hợp hơn transaction kéo dài.

### 8.2. Xóa document được tham chiếu

Nếu xóa customer còn có order trỏ tới nó, DBRef không ngăn thao tác xóa. Các hướng xử lý gồm:

- **Chặn xóa** nếu còn các bản ghi liên quan.
- **Soft delete** customer để vẫn giữ lịch sử và chính sách truy cập.
- **Lưu snapshot** tên/địa chỉ khách tại thời điểm giao dịch ngay trong order, vì hóa đơn không nên thay đổi nếu hồ sơ khách hàng sau này bị sửa.
- **Dọn tham chiếu hoặc đối soát định kỳ** khi chính sách nghiệp vụ cho phép.

Không có hướng nào được MongoDB tự thực hiện chỉ bởi `@DBRef`.

## 9. Hiệu năng: N+1, vòng tham chiếu và dữ liệu trả về

Giả sử một trang đọc 100 order, mỗi order chứa `@DBRef Customer`. Với eager loading, ứng dụng có thể phải đọc thêm customer cho các order; với lazy loading, chi phí xuất hiện khi caller truy cập `getCustomer()`.

Nếu triển khai phát sinh một truy vấn tìm 100 order và nhiều truy vấn riêng cho customer, ta gặp dạng vấn đề **N+1**. Tuy nhiên **không nên khẳng định chính xác 101 truy vấn**: Spring Data có thể gom tải một số trường hợp, cùng customer có thể xuất hiện nhiều lần và số lượt truy vấn phụ thuộc phiên bản, cách sử dụng và cấu trúc tham chiếu.

### 9.1. Các chiến lược cải thiện

1. **Chỉ đọc dữ liệu cần:** dùng projection để loại field `@DBRef` khỏi kết quả khi trang danh sách không cần customer.
2. **Giới hạn số order mỗi trang:** dùng phân trang và điều kiện lọc hợp lý.
3. **Cân nhắc snapshot dữ liệu quan trọng:** ví dụ `customerNameAtPurchase` trong order giúp xem lịch sử nhanh và đúng thời điểm giao dịch.
4. **Lưu ID tường minh rồi batch lookup:** lấy các `customerId` duy nhất, truy vấn `customers` bằng `_id: { $in: [...] }` rồi kết hợp ở tầng service.
5. **Cân nhắc aggregation `$lookup`:** khi thực sự cần join phía server và mô hình dữ liệu/đường dẫn khóa hỗ trợ, có thể dùng pipeline rõ ràng. Với dữ liệu DBRef chứa key bắt đầu bằng `$`, việc viết pipeline truy cập field cần cân nhắc cú pháp/phiên bản MongoDB; không có join tự động chỉ nhờ annotation.
6. **Đo lệnh driver thực tế:** dùng command monitoring, profiling và thống kê độ trễ, tránh tối ưu dựa trên số lượng tham chiếu suy đoán.

Projection cần kiểm thử với đúng loại query. Một số kỹ thuật projection ở Spring Data vẫn có thể tạo entity đầy đủ và xử lý reference theo cách khác với mong đợi; nếu yêu cầu chỉ trả vài field, dùng DTO projection hoặc truy vấn raw phù hợp rồi đo thực tế.

### 9.2. Tránh vòng tham chiếu không có chủ đích

Nếu cả `Order` trỏ tới `Customer` và `Customer` lại chứa `List<Order>` qua DBRef, truy cập graph hai chiều có thể tạo chuỗi giải tham chiếu phức tạp, thậm chí gây vòng lặp khi `toString()` hoặc JSON serializer đi qua object graph.

```text
Order --@DBRef--> Customer
  ^                   |
  |                   |
  +------@DBRef-------+
```

Nên giữ hướng tham chiếu tối thiểu theo luồng truy vấn thật. Với trang lịch sử đơn hàng của customer, thường đơn giản hơn khi truy vấn `orders` theo `customerId` thay vì luôn nhúng một list DBRef ngày càng dài vào document customer.

### 9.3. Index ở đâu?

Document đích thường được lấy bằng `_id` nên có thể tận dụng index `_id` mặc định. Nhưng khi cần **liệt kê các order của một customer**, index ở collection `customers` **không giúp lọc nhanh order**. Cần một đường truy vấn và index phù hợp tại `orders`.

Vì cấu trúc DBRef chứa các field đặc biệt `$ref`/`$id`, biểu thức truy vấn và index trên những field con này có thể nhạy với phiên bản MongoDB, cú pháp field bắt đầu bằng `$` và tầng mapping. Nếu truy vấn theo khóa customer là nhu cầu chính, lựa chọn **lưu trực tiếp `customerId`** trên order thường dễ xây index, query và aggregation hơn:

```javascript
// Mô hình ID tường minh thay cho @DBRef:
db.orders.createIndex({ customerId: 1, createdAt: -1 })

db.orders
  .find({ customerId: ObjectId("66a000000000000000000101") })
  .sort({ createdAt: -1 })
  .limit(20)
```

Đây là **mô hình thay thế**; lệnh index/truy vấn chỉ có ý nghĩa nếu document order thật sự chứa `customerId`. Với entity `@DBRef` ở phần 4, document lưu field `customer` dưới dạng DBRef, nên không thể chép nguyên truy vấn này vào rồi mong có kết quả.

## 10. So sánh @DBRef, ID thuần, @DocumentReference và embedding

Spring Data MongoDB cung cấp nhiều cách biểu diễn một quan hệ. Không có lựa chọn nào luôn tối ưu cho mọi trường hợp.

| Phương án | BSON lưu trong order | Ai lấy customer? | Đánh đổi |
| --- | --- | --- | --- |
| **Nhúng document** | `customer: {name, email, ...}` | Đã nằm trong order | Đọc nhanh cùng order; dữ liệu lặp và có thể cũ |
| **ID thuần** | `customerId: ObjectId(...)` | Service tự truy vấn hoặc aggregation | Dễ index và batch; phải viết logic lấy đích |
| **`@DBRef`** | `customer: {$ref, $id, [$db]}` | Spring Data giải DBRef | Có metadata collection; phát sinh lookup, không cascade |
| **`@DocumentReference`** | Mặc định thường lưu khóa id của đích | Spring Data giải theo cấu hình lookup | Linh hoạt cách lưu/tra cứu; cần hiểu version và cấu hình |

### 10.1. Khi nào nên nhúng?

Nhúng nếu thông tin con luôn được đọc cùng document cha, có vòng đời phụ thuộc cha và không tăng không giới hạn. Ví dụ **địa chỉ giao hàng được chốt khi đặt đơn** thường phù hợp nhúng trong order. Lưu DBRef đến hồ sơ địa chỉ hiện tại có thể làm lịch sử giao hàng bị diễn giải sai khi người dùng sửa địa chỉ.

### 10.2. Khi nào nên lưu ID thuần?

Nếu ứng dụng truy vấn nhiều theo `customerId`, cần pagination, bulk update, hoặc tương tác qua nhiều dịch vụ/ngôn ngữ, ID thuần giúp schema đơn giản:

```java
@Document(collection = "orders")
public class OrderWithCustomerId {
    @Id
    private ObjectId id;
    private ObjectId customerId;
    private String orderCode;
}
```

Với mô hình này, service có thể tự tải customer:

```java
Customer customer = customers.findById(order.getCustomerId())
    .orElseThrow(() -> new IllegalStateException(
        "Customer đã bị xóa hoặc không tồn tại"));
```

Mã thứ hai là đoạn minh họa trong service với `customers` là `CustomerRepository` và `order` là một đối tượng có `getCustomerId()`. Trường hợp cùng khách hàng xuất hiện ở nhiều đơn, có thể batch theo tập ID duy nhất thay vì thực hiện một lookup cho mỗi đơn.

### 10.3. @DocumentReference khác @DBRef ở biểu diễn

Với Spring Data MongoDB có hỗ trợ `@DocumentReference`, có thể ánh xạ:

```java
import org.springframework.data.mongodb.core.mapping.DocumentReference;

@DocumentReference
private Customer customer;
```

Nếu dùng cơ chế lookup theo `_id` mặc định, BSON field tham chiếu thường là **giá trị ID trực tiếp**, ví dụ:

```javascript
{ customer: ObjectId("66a000000000000000000101") }
```

Điểm khác biệt quan trọng: `@DocumentReference` có thể tùy chỉnh cách lookup/kiểu giá trị lưu, không nhất thiết dùng cấu trúc `$ref`/`$id` truyền thống. Nó cũng **không tự tạo khóa ngoại hay cascade write**. Khả năng sử dụng và cú pháp cấu hình chi tiết cần đối chiếu với phiên bản Spring Data MongoDB của dự án.

### 10.4. Chọn phương án qua câu hỏi nghiệp vụ

| Câu hỏi | Hướng cân nhắc |
| --- | --- |
| Có cần snapshot dữ liệu ở thời điểm giao dịch? | Nhúng các field lịch sử cần giữ nguyên |
| Đích có được chia sẻ bởi nhiều document và cập nhật độc lập? | ID hoặc tham chiếu |
| Có cần đọc hàng loạt bản ghi và lọc theo ID đích? | ID thuần và index rõ ràng |
| Có thực sự muốn Spring Data quản lý việc giải tham chiếu? | `@DBRef` hoặc `@DocumentReference` với kiểm thử |
| Có nhiều ngôn ngữ/dịch vụ dùng chung BSON? | Cân nhắc tránh metadata/behavior chỉ có trong một mapper |
| Có yêu cầu độ trễ nghiêm ngặt? | Đo số lượt query và kích thước dữ liệu, cân nhắc snapshot/denormalization |

## 11. Truy vấn với MongoTemplate hoặc repository

Trong Spring Data MongoDB, repository và `MongoTemplate` có thể cùng đọc entity chứa `@DBRef`:

```java
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

// Ví dụ phương thức đặt trong một service:
public List<Order> recentOrders(MongoTemplate mongoTemplate) {
    Query query = Query.query(
            Criteria.where("totalMinor").gte(100000L))
        .with(Sort.by(Sort.Direction.DESC, "orderCode"))
        .limit(20);

    return mongoTemplate.find(query, Order.class);
}
```

Trong ví dụ này, query chính được chạy trên collection `orders`; `customer` vẫn được Spring Data xử lý theo quy tắc `@DBRef` của entity khi ánh xạ kết quả. Nếu trang chỉ cần mã đơn và tiền, hãy cân nhắc projection hoặc entity/DTO đọc chuyên dụng để không tạo nhu cầu giải tham chiếu không cần thiết.

Truy vấn phân tích như tổng doanh thu, thống kê theo trạng thái hoặc index thường làm việc trực tiếp với field MongoDB. Sự có mặt của `@DBRef` **không khiến mọi aggregation hiểu object graph Java**; phải khai báo pipeline và nguồn dữ liệu tường minh.

## 12. Những vấn đề trong reactive access

`@DBRef` của mô hình đồng bộ thường được minh họa với `MongoTemplate`/`MongoRepository` và cơ chế object proxy. Khi ứng dụng dùng `ReactiveMongoTemplate` hoặc `ReactiveMongoRepository`, không nên giả định có thể mang nguyên cơ chế proxy/lazy dereference của imperative sang luồng reactive mà không thay đổi hành vi.

Hãy kiểm tra khả năng hỗ trợ reference resolution theo **phiên bản Spring Data MongoDB**, rồi chọn cách truy vấn tương ứng. Một thiết kế dễ kiểm soát trong reactive pipeline là lưu ID thuần, lấy dữ liệu đích bằng reactive repository/template và kết hợp kết quả bằng toán tử Reactor phù hợp. Cách đó cho phép định nghĩa rõ lượt I/O, concurrency và xử lý thiếu đích.

**Ví dụ khái niệm:**

```java
import reactor.core.publisher.Mono;

// customers: ReactiveCustomerRepository
public Mono<Customer> loadCustomer(ObjectId customerId) {
    return customers.findById(customerId)
        .switchIfEmpty(Mono.error(
            new IllegalStateException("Customer không tồn tại")));
}
```

Phương thức trên là ví dụ đặt trong service có `customers` là reactive repository đã được inject; tham số `ObjectId` cần import `org.bson.types.ObjectId`. Nó thể hiện **truy cập có chủ đích bằng ID**, không phải một phép giải `@DBRef` ẩn sau getter.

## 13. Kiểm thử hành vi lưu và phân giải

Kiểm thử đơn vị chỉ mock repository không chứng minh DBRef được ghi ở dạng BSON đúng, cũng không đo được số lệnh khi giải tham chiếu. Nên có kiểm thử tích hợp với MongoDB cô lập và phiên bản tương đương môi trường triển khai.

### 13.1. Round-trip: BSON chứa DBRef và đọc lại đúng

Ví dụ kiểm thử JUnit 5/Spring Boot Test:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.bson.BsonDocument;
import org.bson.BsonObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoTemplate;

@SpringBootTest
class OrderDbRefIntegrationTest {
    @Autowired
    CustomerRepository customers;

    @Autowired
    OrderRepository orders;

    @Autowired
    MongoTemplate template;

    @Test
    void writesAndResolvesCustomerReference() {
        Customer customer = customers.save(
            new Customer("An", "an@example.com"));
        Order saved = orders.save(
            new Order("TEST-ORD-DBREF-001", 450000L, customer));

        BsonDocument stored = template.getCollection("orders")
            .withDocumentClass(BsonDocument.class)
            .find(new BsonDocument(
                "_id", new BsonObjectId(saved.getId())))
            .first();

        assertThat(stored).isNotNull();
        BsonDocument ref = stored.getDocument("customer");
        assertThat(ref.getString("$ref").getValue())
            .isEqualTo("customers");
        assertThat(ref.getObjectId("$id").getValue())
            .isEqualTo(customer.getId());

        Order restored = orders.findById(saved.getId()).orElseThrow();
        assertThat(restored.getCustomer()).isNotNull();
        assertThat(restored.getCustomer().getName()).isEqualTo("An");
    }
}
```

Trong ví dụ, `@Id ObjectId` giữ cùng kiểu ID BSON trên Java và MongoDB. Lời gọi `withDocumentClass(BsonDocument.class)` đọc trực tiếp cấu trúc BSON để kiểm tra `$ref` và `$id`, tránh phụ thuộc driver trả DBRef dưới dạng đối tượng Java chuyên biệt hay `Document`. Nếu thay `ObjectId` bằng string/UUID, phần assertion kiểu BSON `$id` cũng phải đổi cho phù hợp.

Để kiểm tra **không có cascade**, có thể tạo khách hàng và đơn hàng đã lưu, thay đổi customer thông qua lớp service phù hợp, rồi xác nhận save order không tự cập nhật document customer. Đồng thời nên thử document order có tham chiếu đến ID đích bị xóa để xem ứng dụng phản hồi theo chính sách đã đặt.

### 13.2. Kiểm tra eager/lazy và N+1 bằng kết quả đo

Một kiểm thử/đo lường có thể:

1. Seed 50 order, trong đó nhiều order dùng chung một customer.
2. Đọc danh sách order và ghi số lệnh MongoDB được driver phát ra.
3. Lặp lại với `@DBRef(lazy=true)`, lần đầu **không** truy cập getter customer.
4. Sau đó truy cập `getCustomer().getName()` cho mọi order và đo lại.
5. So sánh số lệnh, network round-trip và tổng độ trễ; thử trường hợp list tham chiếu đồng nhất và trường hợp đích phân tán nhiều collection.

Để quan sát, dùng MongoDB driver command monitoring hoặc profiler trong môi trường kiểm thử được kiểm soát; `explain("executionStats")` chỉ mô tả kế hoạch **một query**, không tự tổng hợp toàn bộ các query phát sinh bởi mapper. Khi chạy production, cần tránh bật profiling/log chi tiết không giới hạn.

### 13.3. Những trường hợp cần có trong ma trận test

| Trường hợp | Kỳ vọng kiểm chứng |
| --- | --- |
| Lưu customer trước order | BSON chứa đúng `$ref` và `$id`, không nhúng toàn bộ customer |
| Đọc order qua repository | `customer` ánh xạ được về `Customer` với ID và field phù hợp |
| Lazy getter không được gọi | Không phát sinh lookup đích sớm ngoài dự kiến trong cấu hình hỗ trợ |
| Lazy getter được gọi | Truy vấn đích xảy ra và xử lý lỗi được kiểm soát |
| Customer bị xóa | Ứng dụng xử lý dangling reference theo chính sách nghiệp vụ |
| Cùng customer được nhiều order tham chiếu | Không tạo hàng loạt truy vấn thừa hoặc đo rõ chi phí chấp nhận được |
| Không đủ quyền đọc collection đích | Lỗi được phát hiện, báo cáo đúng ranh giới service |
| Save order sau khi sửa customer trong bộ nhớ | Không có cascade update ngoài ý muốn |
| Tham chiếu qua database khác | Kiểm tra `$db`, quyền và cấu hình đọc thực tế |

## 14. Các lỗi thường gặp

| Vấn đề | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Nghĩ `@DBRef` là join server-side | Không phân biệt BSON reference và aggregation | Hiểu thao tác resolve diễn ra qua Spring Data, đo query thực tế |
| Order lưu tham chiếu tới customer chưa save | `@DBRef` không cascade tạo customer | Lưu đích, kiểm tra ID rồi mới lưu document tham chiếu |
| Customer đổi thông tin nhưng order không “tự cập nhật” | Save order không cascade sang customer | Lưu customer riêng; snapshot nếu cần dữ liệu lịch sử |
| Xóa customer làm giao diện đọc order lỗi | MongoDB không có khóa ngoại tự động | Chặn xóa, soft delete, snapshot hoặc kiểm soát dangling reference |
| Eager DBRef làm trang danh sách chậm | Tải đích dù màn hình không cần | Projection, ID tường minh, batch lookup hoặc mô hình khác |
| Lazy loading vẫn phát sinh nhiều query | Getter/serializer/debugger kích hoạt proxy | Đo query, không serialize trực tiếp object graph, dùng DTO |
| Trường tham chiếu vừa đến vừa đi vòng | Thiết kế quan hệ hai chiều không cần thiết | Giảm chiều tham chiếu; query theo khóa ngoại ở phía con |
| Nhầm `$db` với URI MongoDB | DBRef chỉ chứa tên database, không có kết nối độc lập | Cấu hình client/permission rõ ràng |
| Tạo index trên customer mà mong query order theo customer nhanh | Index đặt ở collection sai | Chọn khóa và index truy vấn ngay trên orders hoặc thiết kế aggregation phù hợp |
| Áp dụng `@DBRef` với reactive rồi giả định có proxy đồng bộ | Hai hạ tầng truy cập khác nhau | Kiểm tra hỗ trợ phiên bản và dùng reactive lookup tường minh khi phù hợp |

## 15. Bài tập thực hành

Ứng dụng thư viện có `Book`, `Author` và `Borrowing`:

- Một tác giả có thể viết nhiều sách.
- Một cuốn sách có thể có nhiều tác giả.
- Khi tạo lượt mượn, hệ thống cần giữ thông tin **tên sách và mã sách tại thời điểm mượn** để phục vụ lịch sử.
- Trang danh sách mượn thường chỉ hiển thị tên sách và ngày mượn; chỉ trang chi tiết mới cần thông tin tác giả.

Hãy thiết kế:

1. Collection nào cần tồn tại và document nào nên giữ dữ liệu snapshot?
2. Có nên dùng `@DBRef` từ `Book` đến `Author`? Nếu có, khi nào dùng lazy?
3. Nếu danh sách hàng trăm cuốn sách phải hiển thị tên tác giả, làm sao tránh số truy vấn tăng theo số sách?
4. Khi xóa tác giả nhưng sách còn tồn tại, ứng dụng cần chính sách gì?
5. Viết cách kiểm thử BSON `$ref`, `$id` và cách đọc lại qua `MongoTemplate` hoặc repository.

**Gợi ý:** giữ `authors` và `books` như thực thể độc lập; lượt mượn có thể lưu snapshot `bookTitleAtBorrow` và `bookCodeAtBorrow` để bảo toàn lịch sử. `@DBRef` cho author chỉ nên dùng khi thực sự muốn Spring Data giải tham chiếu đối tượng; khi danh sách sách dài và phải lọc/sắp xếp theo khóa tác giả, lưu ID và truy vấn/batch lookup có thể thuận tiện hơn. Đo số lệnh phát sinh trước khi quyết định lazy hay eager.

## 16. Ghi nhớ

- **DBRef** biểu diễn bằng `$ref` (collection), `$id` (khóa đích) và `$db` (database tùy chọn).
- **`@DBRef`** giúp Spring Data MongoDB ánh xạ reference BSON và giải đối tượng Java khi đọc; MongoDB server không tự nối document trong `find`.
- **Không có cascade hay khóa ngoại tự động**. Đích phải có ID hợp lệ trước khi lưu reference; ứng dụng chịu trách nhiệm toàn vẹn dữ liệu và thao tác nhiều document.
- **Eager/lazy là quyết định về thời điểm I/O**, không xóa chi phí resolve và không bảo đảm tránh N+1.
- Với truy vấn theo ID đích, dữ liệu lịch sử bất biến, ứng dụng đa ngôn ngữ hoặc tải lớn, hãy cân nhắc **ID thuần, snapshot/embedding hoặc `@DocumentReference`** trước khi chọn `@DBRef`.

Khi dùng Spring Data MongoDB, hãy đánh giá tham chiếu theo nhu cầu truy vấn, mô hình cập nhật, chi phí đọc và ranh giới nhất quán. Kiểm thử round-trip BSON ↔ Java và quan sát số lệnh MongoDB thực tế là hai bước quan trọng trước khi đưa một cấu trúc tham chiếu vào vận hành.
