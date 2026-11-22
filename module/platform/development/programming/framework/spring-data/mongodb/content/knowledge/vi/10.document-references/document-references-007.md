# Lưu document tham chiếu riêng và giới hạn cascade

## 1. Vì sao cần lưu document tham chiếu riêng?

MongoDB có hai cách tổ chức dữ liệu liên quan thường gặp: **nhúng (embedding)** dữ liệu vào một document hoặc **tách thành nhiều document** và giữ liên kết bằng một giá trị tham chiếu. Nhúng phù hợp khi dữ liệu thường được đọc/cập nhật cùng nhau và có vòng đời phụ thuộc document cha. Tham chiếu phù hợp khi đối tượng liên quan có **định danh, vòng đời và quyền truy cập độc lập**, có thể được nhiều document khác cùng sử dụng.

Ví dụ, một đơn hàng cần biết khách hàng đã đặt đơn. Khách hàng có thể tồn tại trước đơn hàng, cập nhật hồ sơ riêng và được nhiều đơn hàng tham chiếu. Nếu mỗi đơn hàng lưu toàn bộ hồ sơ khách hàng như một bản sao, việc đổi thông tin liên hệ có thể phải cập nhật nhiều bản ghi. Vì vậy, mô hình **customers** và **orders** là ứng viên tự nhiên cho việc tham chiếu giữa hai collection.

Trong module **SPRING_DATA_MONGODB**, chủ đề này liên quan trực tiếp đến ánh xạ document, lưu dữ liệu bằng **MongoTemplate** hoặc **repository**, thiết kế truy vấn và aggregation, lập index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng. Điểm quan trọng nhất là: **lưu một tham chiếu không đồng nghĩa Spring Data MongoDB tự lưu, cập nhật hoặc xóa theo dây chuyền các document được tham chiếu**.

Sau bài học, bạn có thể:

1. Quyết định khi nào nên tách document thay vì nhúng.
2. Lưu liên kết bằng ID thủ công, **@DocumentReference** hoặc **@DBRef**.
3. Phân biệt lưu tham chiếu với tự động lưu document đích.
4. Xây quy tắc tạo, đổi và xóa tham chiếu mà không mất dữ liệu ngoài ý muốn.
5. Nhận biết **dangling reference**, **orphan**, rủi ro đọc nhiều lần và yêu cầu transaction.
6. Thiết kế index, truy vấn, kiểm thử và giám sát cho quan hệ giữa các collection.

## 2. Ví dụ xuyên suốt: customers và orders

Collection **customers** lưu hồ sơ khách hàng:

~~~javascript
// customers
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  displayName: "Lan",
  email: "lan@example.test",
  status: "ACTIVE"
}
~~~

Collection **orders** lưu đơn hàng và một tham chiếu tới khách hàng:

~~~javascript
// orders
{
  _id: ObjectId("507f1f77bcf86cd799439012"),
  orderNumber: "ORD-1001",
  customerId: ObjectId("507f1f77bcf86cd799439011"),
  totalMinor: NumberLong("199000"),
  createdAt: ISODate("2025-05-20T09:00:00Z")
}
~~~

Ở đây, **customerId** là một trường BSON ObjectId trong đơn hàng. Document đơn hàng chỉ lưu khóa liên kết, không chứa toàn bộ Customer. MongoDB không tự hiểu rằng trường customerId là khóa ngoại như trong một hệ cơ sở dữ liệu quan hệ. Ứng dụng và các quy trình vận hành phải bảo vệ tính hợp lệ của liên kết này.

~~~mermaid
flowchart LR
    C["customers / Customer"] -->|"_id = C1"| K["ObjectId C1"]
    O["orders / Order"] -->|"customerId = C1"| K
    O -->|"nhiều đơn hàng"| O2["Cùng tham chiếu một khách hàng"]
~~~

**Một ID được lưu ở document A không tự bảo đảm document B còn tồn tại.** Nếu Customer bị xóa, Order vẫn có customerId cũ trừ khi ứng dụng chủ động xử lý.

### 2.1. Phân biệt ID kỹ thuật và dữ liệu nghiệp vụ

- **customerId** là định danh kỹ thuật để truy xuất Customer.
- **displayName** và **email** thuộc về Customer; thay đổi của chúng không nhất thiết yêu cầu ghi lại toàn bộ Order.
- **orderNumber** là mã nghiệp vụ của Order, có thể cần unique index riêng.
- **totalMinor** là số tiền theo quy ước đơn vị nhỏ nhất của hệ thống; loại giá trị này không liên quan tới cách lưu tham chiếu.

Trong nhiều hệ thống, đơn hàng vẫn cần lưu một **snapshot** của vài thông tin tại thời điểm mua, chẳng hạn tên người nhận hoặc địa chỉ giao hàng. Snapshot có mục đích lưu lịch sử và không nhất thiết phải tự động đồng bộ với Customer hiện tại. Vì vậy, một document có thể vừa lưu **customerId** để tham chiếu, vừa lưu **shippingAddressSnapshot** được nhúng.

## 3. Embedding và referencing: chọn theo vòng đời dữ liệu

| Tiêu chí | Nhúng vào document cha | Tách document và tham chiếu |
| --- | --- | --- |
| Vòng đời | Thành phần thường thuộc riêng cha | Đối tượng có vòng đời độc lập |
| Truy vấn thông thường | Thường cần dữ liệu cùng lúc | Có thể đọc riêng đối tượng đích |
| Cập nhật | Một document có thể cập nhật nguyên tử | Có thể phải cập nhật nhiều document |
| Dùng chung | Bản sao trong nhiều cha nếu nhúng lặp | Nhiều cha trỏ cùng một đích |
| Quy mô | Phải chú ý giới hạn kích thước document và mảng tăng lớn | Dễ quản lý tập dữ liệu lớn hơn, nhưng tăng lần đọc |
| Xóa | Dữ liệu nhúng biến mất khi xóa document cha | Document đích tồn tại độc lập nếu không chủ động xóa |
| Tính nhất quán | Các field trong một document được cập nhật nguyên tử | Cần giao thức khi thay đổi nhiều document |

Ví dụ hợp lý:

- Nhúng **items** nhỏ trong Order vì các dòng hàng thuộc đơn hàng và thường đọc cùng nhau.
- Tham chiếu **Customer** từ Order vì khách hàng tồn tại độc lập và có nhiều đơn hàng.
- Có thể tham chiếu **Product** từ Order để liên kết danh mục hiện hành, nhưng vẫn lưu **tên và đơn giá tại thời điểm mua** trong item snapshot để không thay đổi lịch sử.

Đừng hiểu tham chiếu luôn tốt hơn nhúng. Quyết định nên bắt đầu từ **mẫu truy cập và ranh giới nghiệp vụ**, sau đó mới chọn cơ chế ánh xạ.

## 4. Ba cách biểu diễn tham chiếu trong Spring Data MongoDB

Spring Data MongoDB hỗ trợ nhiều cách lưu liên kết giữa document:

| Cách lưu | BSON thường thấy trong Order | Tầng Java | Đặc điểm |
| --- | --- | --- | --- |
| **ID thủ công** | customerId: ObjectId(...) | ObjectId customerId | Đơn giản, minh bạch, ứng dụng tự tải Customer |
| **@DocumentReference** mặc định | customer: ObjectId(...) | Customer customer | Spring Data hỗ trợ resolve đối tượng tham chiếu; thường lưu ID đích |
| **@DBRef** | customer: { $ref: "customers", $id: ObjectId(...) } | Customer customer | Lưu BSON DBRef có metadata collection/ID |

Ví dụ trên minh họa trường hợp phổ biến khi ID của Customer là BSON ObjectId. **@DocumentReference** cũng hỗ trợ định nghĩa lookup và cách lưu tham chiếu tùy chỉnh; khi dùng cấu hình đó, giá trị lưu có thể khác ID đơn giản. Còn **@DBRef** lưu cấu trúc DBRef; không nên nhầm nó với một field ObjectId thông thường.

Điểm chung của cả ba cách: **việc lưu Order không tự tạo một Customer chưa được persist**. Không có cascade-save/cascade-delete mặc định cho các tham chiếu này như người học có thể kỳ vọng khi quen với một số ORM quan hệ.

### 4.1. Không có khóa ngoại tự động

MongoDB không tự thực hiện kiểm tra tồn tại Customer chỉ vì Order có customerId. Schema validation có thể xác nhận **kiểu dữ liệu** của customerId là ObjectId, nhưng không tự chứng minh giá trị đó có bản ghi tương ứng trong collection customers.

Ví dụ một document hợp lệ về kiểu BSON nhưng có tham chiếu không tồn tại:

~~~javascript
{
  orderNumber: "ORD-404",
  customerId: ObjectId("000000000000000000000001")
}
~~~

Ứng dụng cần tự chọn cách xử lý: từ chối tạo Order nếu không có Customer, trả về trạng thái “không tìm thấy Customer”, lưu đơn hàng lịch sử dưới dạng snapshot, hoặc dùng chiến lược khác theo nghiệp vụ.

## 5. Cách 1: lưu ID thủ công và tải document đích

Đây là phương án dễ hiểu, dễ kiểm thử và thường phù hợp khi hệ thống cần kiểm soát rõ số truy vấn.

### 5.1. Entity Customer

~~~java
package com.example.sales;

import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "customers")
public record CustomerDocument(
    @Id ObjectId id,
    String displayName,
    String email
) {}
~~~

### 5.2. Entity Order có customerId

~~~java
package com.example.sales;

import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record OrderDocument(
    @Id ObjectId id,
    String orderNumber,
    ObjectId customerId,
    long totalMinor,
    Instant createdAt
) {}
~~~

Hai entity gốc có collection và ID riêng. **customerId** không được đánh dấu @Id vì nó là khóa liên kết, còn trường **id** mới ánh xạ với _id của Order. Khi lưu, Spring Data MongoDB ghi customerId thành một trường BSON thông thường.

### 5.3. Repository cho hai aggregate

~~~java
package com.example.sales;

import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface CustomerRepository
        extends MongoRepository<CustomerDocument, ObjectId> {
}

public interface OrderRepository
        extends MongoRepository<OrderDocument, ObjectId> {
}
~~~

Ví dụ khởi tạo rồi lưu từng document:

~~~java
CustomerDocument customer = customerRepository.insert(
    new CustomerDocument(null, "Lan", "lan@example.test")
);

OrderDocument order = orderRepository.insert(
    new OrderDocument(
        null,
        "ORD-1001",
        customer.id(),
        199_000L,
        Instant.now()
    )
);

ObjectId customerId = customer.id();
ObjectId orderId = order.id();
~~~

Lưu ý trình tự: Customer đã được lưu thành công và có ID, sau đó Order mới lưu giá trị customerId tương ứng. **Chỉ gọi orderRepository.insert(order) không tự lưu customer**.

Hai thao tác thuộc hai document nên **không tạo thành một giao dịch nguyên tử** trừ khi có transaction MongoDB được thiết kế và cấu hình phù hợp. Nếu thao tác lưu Customer thành công nhưng tạo Order thất bại, Customer vẫn tồn tại; điều đó có thể là hành vi nghiệp vụ hoàn toàn bình thường.

### 5.4. Đọc Order rồi tải Customer

~~~java
import java.util.Optional;
import org.bson.types.ObjectId;

public record OrderDetails(
    String orderNumber,
    String customerName,
    long totalMinor
) {}

public Optional<OrderDetails> loadDetails(ObjectId orderId) {
    Optional<OrderDocument> orderResult = orderRepository.findById(orderId);
    if (orderResult.isEmpty()) {
        return Optional.empty();
    }

    OrderDocument order = orderResult.get();
    CustomerDocument customer = customerRepository.findById(order.customerId())
        .orElseThrow(() -> new IllegalStateException(
            "Order references missing customer: " + order.customerId()
        ));

    return Optional.of(new OrderDetails(
        order.orderNumber(),
        customer.displayName(),
        order.totalMinor()
    ));
}
~~~

Ví dụ trên giả định method nằm trong một service có hai repository được inject sẵn. Nó dùng **hai lần đọc rõ ràng** và kiểm tra tình huống Customer đã không còn. Trong ứng dụng thật, chính sách đối với tham chiếu gãy phải được lựa chọn theo nghiệp vụ: báo lỗi dữ liệu, trả snapshot lịch sử, hoặc xử lý bất đồng bộ.

### 5.5. Truy vấn bằng MongoTemplate

~~~java
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public OrderDocument findOrderForCustomer(
        MongoTemplate template, ObjectId customerId) {
    Query query = Query.query(
        Criteria.where("customerId").is(customerId)
    );
    return template.findOne(query, OrderDocument.class);
}
~~~

Đây là truy vấn bằng khóa liên kết. MongoTemplate chọn collection **orders** từ @Document của OrderDocument và không cần giải tham chiếu Customer để lọc. Với các ứng dụng có nhiều query theo customerId, nên tạo index thích hợp trên field này.

## 6. Cách 2: @DocumentReference

**@DocumentReference** cho phép Spring Data MongoDB giữ một tham chiếu trong object Java và tải document đích theo một truy vấn lookup. Với cấu hình mặc định thường gặp, giá trị được lưu trong parent là **ID của document đích**.

Ví dụ định nghĩa một kiểu Order khác dành cho minh họa:

~~~java
import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.DocumentReference;

@Document(collection = "orders_with_document_reference")
public record OrderWithDocumentReference(
    @Id ObjectId id,
    String orderNumber,
    @DocumentReference CustomerDocument customer,
    Instant createdAt
) {}
~~~

Khi Customer đã lưu có ID là ObjectId, BSON của Order có thể như sau:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439012"),
  orderNumber: "ORD-1001",
  customer: ObjectId("507f1f77bcf86cd799439011"),
  createdAt: ISODate("2025-05-20T09:00:00Z")
}
~~~

Đọc OrderWithDocumentReference qua Spring Data có thể giải giá trị tham chiếu thành CustomerDocument. Cần nhớ hai điều:

1. **Document đích phải được persist theo chính sách ứng dụng.** Gắn một đối tượng Customer mới chưa được lưu vào Order không có nghĩa Spring Data sẽ tự insert Customer.
2. Việc resolve có thể sinh thêm truy vấn. Đọc một danh sách lớn Order rồi truy cập Customer của từng Order có thể khiến số thao tác đọc tăng mạnh.

### 6.1. Lazy loading

Có thể yêu cầu trì hoãn việc resolve tham chiếu:

~~~java
@DocumentReference(lazy = true)
private CustomerDocument customer;
~~~

Lazy loading có thể giảm số lần đọc khi ứng dụng không bao giờ cần Customer, nhưng việc truy cập thuộc tính sau đó có thể kích hoạt truy vấn và phát sinh lỗi muộn hơn. Cơ chế proxy còn có các ràng buộc liên quan đến kiểu Java, serialization, module system và môi trường runtime. Cần kiểm thử trước khi áp dụng rộng.

Đừng coi lazy = true là giải pháp tự động cho vấn đề **N+1 queries**. Nếu một API vẫn truy cập Customer của từng Order trong danh sách, tổng số truy vấn có thể vẫn rất lớn; đôi khi cần truy vấn theo lô hoặc aggregation.

### 6.2. Lookup tùy chỉnh

@DocumentReference còn hỗ trợ cấu hình **lookup** để liên kết bằng trường nghiệp vụ hoặc điều kiện khác, khi hệ thống có yêu cầu đặc thù. Tuy nhiên, chọn liên kết bằng giá trị không phải _id đòi hỏi:

- Bảo đảm tính duy nhất của khóa tham chiếu được chọn.
- Bảo đảm chính sách đổi khóa và index tương ứng.
- Kiểm tra chính xác giá trị BSON mà parent lưu.
- Kiểm thử lúc tham chiếu không còn tìm được document đích.

Không nên chuyển sang lookup phức tạp chỉ để che giấu thiết kế ID chưa nhất quán.

## 7. Cách 3: @DBRef

**@DBRef** là cách biểu diễn tham chiếu theo dạng MongoDB DBRef. Ví dụ:

~~~java
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.DBRef;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders_with_dbref")
public record OrderWithDbRef(
    @Id ObjectId id,
    String orderNumber,
    @DBRef CustomerDocument customer
) {}
~~~

BSON có thể biểu diễn tham chiếu như:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439012"),
  orderNumber: "ORD-1001",
  customer: {
    $ref: "customers",
    $id: ObjectId("507f1f77bcf86cd799439011")
  }
}
~~~

Đây là dạng biểu diễn DBRef minh họa trong mongosh; các thành phần thực tế còn phụ thuộc cách encode và database đích. Spring Data sử dụng metadata DBRef để xác định document được tham chiếu khi đọc.

**@DBRef không bật tự động cascade.** Khi Order có @DBRef tới Customer, lưu Order không tự lưu Customer mới; xóa Order không tự xóa Customer. DBRef cũng không có nghĩa MongoDB server đảm bảo khóa ngoại hoặc tự động JOIN ở mọi lệnh truy vấn.

### 7.1. @DocumentReference hay @DBRef?

| Tiêu chí | @DocumentReference | @DBRef |
| --- | --- | --- |
| Dữ liệu lưu mặc định | Thường là ID đích | DBRef gồm collection và ID |
| Giải tham chiếu | Spring Data qua lookup | Spring Data qua DBRef metadata |
| Có cascade save/delete mặc định? | Không | Không |
| Có thể lazy? | Có tùy loại mapping | Có tùy loại mapping |
| Linh hoạt lookup | Có thể tùy chỉnh | Gắn với biểu diễn DBRef |
| Độ phức tạp | Có thể gần với ID thủ công | Có thêm cấu trúc DBRef |

Với mô hình mới, **ID thủ công** hoặc **@DocumentReference** thường dễ kiểm soát hơn khi không có yêu cầu tương thích với hệ thống đã sử dụng DBRef. Nếu dự án đang lưu DBRef, thay đổi annotation **không tự chuyển dữ liệu cũ** sang ObjectId thuần; phải thiết kế migration.

## 8. Cascade là gì và giới hạn quan trọng nhất

Trong phát triển ứng dụng, **cascade** thường được dùng để chỉ hành vi mà một thao tác trên đối tượng cha sẽ tự động lan sang những đối tượng liên quan: persist, merge/update hoặc remove. Khi sử dụng ORM quan hệ, lập trình viên có thể quen với cascade trên quan hệ entity. Với Spring Data MongoDB, cần phân biệt:

- **Embedded object**: là một phần của cùng BSON document. Khi ghi document cha, dữ liệu nhúng được ghi trong chính document đó. Xóa cha làm dữ liệu nhúng cũng không còn, vì chúng không phải document độc lập.
- **Referenced document**: nằm trong collection/document độc lập. Ghi hoặc xóa parent chỉ thao tác với parent trừ khi **mã ứng dụng chủ động gọi thêm thao tác** đối với target.

~~~mermaid
flowchart TD
    A["Lưu Order có Customer tham chiếu"] --> B["Lưu document Order"]
    B --> C{"Có lưu Customer tự động?"}
    C -->|"Mặc định: không"| D["Customer tồn tại hoặc chưa tồn tại tùy thao tác riêng"]
    E["Xóa Order"] --> F["Chỉ xóa document Order"]
    F --> G["Customer được giữ lại"]
~~~

Đây là ranh giới quan trọng để tránh hai lỗi đối nghịch:

1. **Tin rằng lưu Order sẽ tự lưu Customer mới**, khiến Order giữ ID tham chiếu tới bản ghi chưa tồn tại.
2. **Tự cài cascade delete thiếu kiểm soát**, khiến xóa một Order lại xóa Customer đang được hàng trăm Order khác sử dụng.

### 8.1. Ví dụ sai về kỳ vọng cascade-save

~~~java
// Dùng với entity OrderWithDocumentReference ở phần trên.
CustomerDocument notPersisted = new CustomerDocument(
    null, "Mai", "mai@example.test"
);

OrderWithDocumentReference order = new OrderWithDocumentReference(
    null, "ORD-2001", notPersisted, Instant.now()
);

// Sai về ý định: không được kỳ vọng lệnh này tự insert Customer.
orderWithRefRepository.insert(order);
~~~

Tùy mapping và trạng thái ID, trường hợp đối tượng tham chiếu chưa được persist có thể gây lỗi hoặc tạo giá trị tham chiếu không hợp lệ. Không nên phụ thuộc vào một hành vi tình cờ của converter. **Quy tắc đúng là lưu hoặc xác minh Customer trước**, sau đó mới tạo Order tham chiếu ID/Customer đã có.

### 8.2. Ví dụ lưu có chủ đích

~~~java
CustomerDocument customer = customerRepository.insert(
    new CustomerDocument(null, "Mai", "mai@example.test")
);

OrderWithDocumentReference order = new OrderWithDocumentReference(
    null, "ORD-2001", customer, Instant.now()
);

OrderWithDocumentReference savedOrder =
    orderWithRefRepository.insert(order);
~~~

Các repository trong ví dụ là dependency do service khai báo và inject. Hai câu lệnh insert là **hai thao tác tường minh**, không phải cascade mặc định. Nếu cần chúng thành một đơn vị nguyên tử, xem phần transaction bên dưới.

## 9. Tại sao cascade-delete rất nguy hiểm với tham chiếu dùng chung?

Giả sử Customer **C1** có ba đơn hàng **O1**, **O2**, **O3**:

~~~mermaid
flowchart LR
    O1["Order O1"] --> C1["Customer C1"]
    O2["Order O2"] --> C1
    O3["Order O3"] --> C1
~~~

Nếu một logic xóa O1 gọi tiếp customerRepository.deleteById(C1), O2 và O3 sẽ giữ các tham chiếu không còn target. Đây thường là lỗi thiết kế nghiêm trọng.

**Quy tắc thực hành:** Khi target có vòng đời độc lập hoặc có thể được chia sẻ, thao tác xóa parent **không được xóa target theo dây chuyền** nếu chưa có một bất biến nghiệp vụ được chứng minh và cơ chế kiểm tra ràng buộc.

| Thao tác | Hành vi mặc định của reference | Chính sách thường hợp lý |
| --- | --- | --- |
| Tạo Order liên kết Customer | Chỉ tạo Order | Xác minh Customer tồn tại trước khi ghi |
| Sửa tên Customer | Chỉ sửa Customer | Order tiếp tục tham chiếu cùng ID |
| Xóa một Order | Chỉ xóa Order | Giữ Customer nếu tồn tại độc lập |
| Xóa Customer còn Order | Không có foreign-key guard mặc định | Từ chối, soft delete hoặc xử lý ràng buộc theo nghiệp vụ |
| Xóa Customer không còn Order | Chỉ xóa Customer | Có thể cho phép sau khi kiểm tra điều kiện |
| Xóa một OrderItem nhúng | Sửa/xóa trong Order | Thay đổi cùng document, không phải xóa collection riêng |

Hãy phân biệt **xóa object khỏi một mảng tham chiếu** với **xóa document đích**. Bỏ productId khỏi danh sách productIds của một Order chỉ gỡ liên kết; nó không phải lệnh xóa Product.

## 10. Dangling reference và orphan: hai tình huống khác nhau

**Dangling reference** là tham chiếu từ một document còn tồn tại tới một target không tồn tại:

~~~javascript
// Order còn trong collection orders.
{ orderNumber: "ORD-404", customerId: ObjectId("000000000000000000000001") }

// Nhưng customers không có document với _id đó.
~~~

**Orphan document** là một document không còn được document khác tham chiếu, trong trường hợp nghiệp vụ kỳ vọng nó phải thuộc về một chủ thể. Ví dụ một attachment tạm không còn gắn với đơn hàng nào. Orphan **không luôn là lỗi**: Customer có thể chưa đặt đơn nào nhưng vẫn là khách hàng hợp lệ.

Mỗi loại dữ liệu cần chính sách riêng:

- Với **Customer**, không có Order tham chiếu có thể vẫn hoàn toàn bình thường.
- Với **attachment chỉ phục vụ một Order**, attachment không còn liên kết có thể cần dọn định kỳ.
- Với **audit record**, ngay cả khi entity nghiệp vụ đã bị xóa, việc giữ lại record cũng có thể là yêu cầu lưu trữ.

Vì vậy không có quy tắc “hễ không được tham chiếu thì xóa” áp dụng cho mọi collection.

### 10.1. Kiểm tra tham chiếu thủ công

Với mô hình customerId, có thể đối chiếu số bản ghi Order và Customer bằng aggregation:

~~~javascript
db.orders.aggregate([
  {
    $lookup: {
      from: "customers",
      localField: "customerId",
      foreignField: "_id",
      as: "matchedCustomers"
    }
  },
  { $match: { matchedCustomers: { $size: 0 } } },
  { $project: { orderNumber: 1, customerId: 1 } }
]);
~~~

Pipeline trên tìm Order không match được Customer. Nó hữu ích cho kiểm tra dữ liệu, nhưng với collection rất lớn có thể gây tốn tài nguyên. Nên cân nhắc chạy theo batch, trong thời gian phù hợp và bảo đảm index trên trường join. Collection customers mặc định có index _id; với các truy vấn Order theo customerId, vẫn nên cân nhắc index riêng bên orders.

### 10.2. Truy vấn MongoDB không tự bảo đảm reference

Các thao tác như find, updateOne hoặc insertOne có thể hoạt động dù customerId trỏ tới giá trị không tồn tại. Chỉ khi mã ứng dụng, job kiểm tra hoặc logic resolve reference yêu cầu Customer thì lỗi mới lộ ra. Không nên dùng khả năng đọc được Order làm bằng chứng Customer vẫn tồn tại.

## 11. Xóa và đổi liên kết có kiểm soát

### 11.1. Xóa Order, giữ Customer

~~~java
public void deleteOrder(ObjectId orderId) {
    orderRepository.deleteById(orderId);
}
~~~

Lệnh này chỉ thao tác collection **orders**. Nó không yêu cầu xóa document Customer và không cần cascading vì Customer có vòng đời riêng.

### 11.2. Đổi Customer của Order

Ví dụ với MongoTemplate và mô hình lưu customerId:

~~~java
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import com.mongodb.client.result.UpdateResult;

public boolean reassignCustomer(
        MongoTemplate template, ObjectId orderId, ObjectId newCustomerId) {

    if (!template.exists(
            Query.query(Criteria.where("_id").is(newCustomerId)),
            CustomerDocument.class)) {
        throw new IllegalArgumentException("Customer does not exist");
    }

    Query query = Query.query(Criteria.where("_id").is(orderId));
    Update update = new Update().set("customerId", newCustomerId);

    UpdateResult result = template.updateFirst(
        query, update, OrderDocument.class
    );
    return result.getMatchedCount() == 1;
}
~~~

Hàm trên minh họa **kiểm tra trước khi đổi liên kết**, nhưng kiểm tra tồn tại và update là hai thao tác riêng. Một tiến trình khác có thể xóa Customer sau khi kiểm tra và trước khi cập nhật Order. Nếu nghiệp vụ yêu cầu bất biến chặt, cần transaction/giao thức khóa hợp lý hoặc quy tắc cấm xóa Customer đang được tham chiếu, không chỉ kiểm tra tồn tại một lần.

### 11.3. Xóa Customer được nhiều Order sử dụng

Một chính sách là từ chối xóa Customer còn Order:

~~~java
boolean hasOrders = mongoTemplate.exists(
    Query.query(Criteria.where("customerId").is(customerId)),
    OrderDocument.class
);

if (hasOrders) {
    throw new IllegalStateException(
        "Cannot delete customer referenced by orders"
    );
}

customerRepository.deleteById(customerId);
~~~

Kiểm tra này có **race condition** tương tự: một writer có thể tạo Order mới sau khi hasOrders được tính nhưng trước khi Customer bị xóa. Trong hệ thống cần giữ ràng buộc mạnh, mọi writer và delete flow phải tuân theo cùng một giao thức; chỉ bao bọc đoạn code trong một transaction cũng cần xét cách ngăn concurrent insert gây mồ côi trong mô hình cách ly của MongoDB.

Một phương án nghiệp vụ phổ biến là **soft delete** hoặc đặt status = INACTIVE, rồi chặn tạo Order mới cho Customer không còn hoạt động. Điều này bảo toàn lịch sử đơn hàng và giúp xử lý vòng đời độc lập.

## 12. Transaction có giúp cascade an toàn hơn không?

MongoDB hỗ trợ transaction nhiều document trên những cấu hình server phù hợp. Spring Data MongoDB có thể tích hợp transaction manager để nhóm các thao tác lưu/xóa vào một transaction:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration
public class MongoTxConfig {
    @Bean
    MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory factory) {
        return new MongoTransactionManager(factory);
    }
}
~~~

Ví dụ một service tạo Customer và Order trong cùng transaction khi nghiệp vụ yêu cầu cả hai cùng thành công hoặc cùng thất bại:

~~~java
import java.time.Instant;
import org.springframework.transaction.annotation.Transactional;

@Transactional
public OrderDocument createCustomerAndFirstOrder(
        String customerName, String orderNumber) {

    CustomerDocument customer = customerRepository.insert(
        new CustomerDocument(null, customerName, null)
    );

    return orderRepository.insert(
        new OrderDocument(
            null,
            orderNumber,
            customer.id(),
            0L,
            Instant.now()
        )
    );
}
~~~

Ví dụ giả định method nằm trong Spring-managed service, transaction manager được cấu hình và MongoDB deployment hỗ trợ transaction. Cần xét cách gọi qua proxy của Spring để @Transactional có hiệu lực. Trong môi trường không hỗ trợ transaction hoặc khi không cấu hình đúng, annotation đơn thuần không biến hai thao tác thành nguyên tử.

Transaction giúp nhóm **các ghi được chọn rõ ràng** thành một đơn vị commit/rollback. Nó **không tự bật cascade của @DBRef/@DocumentReference**, không tạo foreign key và không miễn trừ việc thiết kế cách xử lý cạnh tranh giữa các luồng tạo/xóa tham chiếu.

### 12.1. Không tự động dùng transaction cho mọi reference

Transaction nhiều document có chi phí và điều kiện vận hành. Với trường hợp Customer đã tồn tại, Order được tạo mới và việc tạo Order thất bại không cần rollback Customer, thường không có lý do để nhóm hai thao tác vào transaction.

Khi phát sự kiện ra hệ thống ngoài hoặc đồng bộ qua nhiều dịch vụ, transaction MongoDB không tự đảm bảo email/event đã được gửi cùng commit. Cần cân nhắc **outbox**, **saga** hoặc quy trình bù trừ khi có yêu cầu nhất quán xuyên hệ thống.

## 13. Chẩn đoán hiệu năng: N+1, query và index

Giả sử một API tải 100 Order và mỗi Order có Customer tham chiếu. Nếu code thực hiện 100 lần tìm Customer riêng lẻ sau khi đọc danh sách Order, số thao tác đọc tăng đáng kể. Đây là một dạng **N+1 queries**.

| Cách đọc | Số thao tác đọc điển hình | Điểm cần chú ý |
| --- | --- | --- |
| Tải Orders rồi findById từng Customer | 1 + N (trước khi tối ưu cache/lặp ID) | Đơn giản nhưng nhiều round-trip |
| Tải Orders, gom customerId rồi query customers bằng $in | Thường 2 truy vấn chính | Cần ghép lại kết quả, xử lý ID thiếu |
| Aggregation $lookup | Một pipeline trên server | Cần index, chú ý memory/size/pipeline |
| @DocumentReference hoặc @DBRef tự resolve | Phụ thuộc mapping và cách truy cập | Không giả định chỉ có một truy vấn |

### 13.1. Gom ID để đọc theo lô

Với tham chiếu ObjectId thủ công, chiến lược phổ biến:

1. Đọc danh sách Orders theo filter và page size.
2. Thu thập **customerId** khác nhau.
3. Truy vấn Customer theo tập ID bằng **$in**.
4. Xây map **customerId → Customer**.
5. Kết hợp kết quả và xử lý các tham chiếu không tìm được.

Ví dụ query MongoTemplate lấy Customer theo nhiều ID:

~~~java
import java.util.Collection;
import java.util.List;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public List<CustomerDocument> loadCustomers(
        MongoTemplate template, Collection<ObjectId> ids) {
    if (ids.isEmpty()) {
        return List.of();
    }
    return template.find(
        Query.query(Criteria.where("_id").in(ids)),
        CustomerDocument.class
    );
}
~~~

Đây là cách giảm số round-trip; vẫn cần giới hạn kích thước trang và tập ID để không tạo query quá lớn. Khi nhiều Orders cùng Customer, chỉ cần truy xuất Customer một lần trong batch.

### 13.2. Aggregation $lookup

Ví dụ ghép Order và Customer trên server:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      createdAt: { $gte: ISODate("2025-01-01T00:00:00Z") }
    }
  },
  {
    $lookup: {
      from: "customers",
      localField: "customerId",
      foreignField: "_id",
      as: "customer"
    }
  },
  {
    $unwind: {
      path: "$customer",
      preserveNullAndEmptyArrays: true
    }
  },
  {
    $project: {
      orderNumber: 1,
      customerId: 1,
      customerName: "$customer.displayName",
      totalMinor: 1
    }
  }
]);
~~~

**$lookup** là phép ghép dữ liệu theo pipeline, không phải cascade và không thay đổi cách tham chiếu được lưu. Khi dùng $lookup, kiểm tra kích thước dữ liệu kết quả, cách filter trước khi join và khả năng dùng index của collection đích.

### 13.3. Index cho khóa liên kết

MongoDB tạo index _id cho collection thông thường. Ngoài ra, khi truy vấn Orders theo Customer, có thể tạo:

~~~javascript
db.orders.createIndex({ customerId: 1, createdAt: -1 });

db.orders.find({
  customerId: ObjectId("507f1f77bcf86cd799439011")
}).sort({ createdAt: -1 }).explain("executionStats");
~~~

Index compound phù hợp khi API thường lọc customerId và sắp xếp theo createdAt, nhưng hiệu quả thực tế phụ thuộc dữ liệu và các mẫu query. Dùng **explain("executionStats")** để đo keys/documents examined, kế hoạch và độ trễ. Đừng chỉ dựa vào sự tồn tại của annotation để tin rằng index đã được tạo trên server.

## 14. Tham chiếu tới danh sách document

Một Order có thể liên kết tới nhiều Product. Cách lưu ID thủ công:

~~~javascript
{
  orderNumber: "ORD-3001",
  productIds: [
    ObjectId("507f1f77bcf86cd799439021"),
    ObjectId("507f1f77bcf86cd799439022")
  ]
}
~~~

Ở phía Java:

~~~java
import java.util.List;
import org.bson.types.ObjectId;

public record OrderProductLinks(
    String orderNumber,
    List<ObjectId> productIds
) {}
~~~

Đây là một mô hình liên kết đơn giản, nhưng cần quyết định:

- Có cho phép một Product xuất hiện nhiều lần trong productIds không?
- Thứ tự phần tử có ý nghĩa nghiệp vụ không?
- Có cần snapshot thông tin Product tại thời điểm đặt hàng không?
- Danh sách có thể tăng không giới hạn và khiến document lớn quá mức không?
- Xóa Product có được phép khi vẫn xuất hiện trong Order lịch sử không?

Với quan hệ nhiều-nhiều lớn hoặc có thông tin liên kết riêng (chẳng hạn vai trò, thời gian hiệu lực), có thể cân nhắc **collection liên kết** thay vì mảng ID ngày càng lớn. Việc chọn phụ thuộc vào mẫu truy cập và ràng buộc nghiệp vụ, không có một công thức cố định.

### 14.1. Gỡ tham chiếu không xóa Product

Ví dụ:

~~~javascript
db.orders.updateOne(
  { orderNumber: "ORD-3001" },
  {
    $pull: {
      productIds: ObjectId("507f1f77bcf86cd799439021")
    }
  }
);
~~~

Lệnh $pull chỉ sửa mảng trong Order. Document Product với _id tương ứng vẫn tồn tại trong collection products.

## 15. Giới hạn cascade trong reactive access

Với **ReactiveMongoRepository** hoặc **ReactiveMongoTemplate**, nguyên tắc tham chiếu không đổi: parent và target là các document riêng. Mã reactive phải tổ chức tường minh trình tự ghi:

~~~java
import java.time.Instant;
import org.bson.types.ObjectId;
import reactor.core.publisher.Mono;

public Mono<OrderDocument> createOrderForCustomer(
        ObjectId customerId, String number) {

    return reactiveCustomerRepository.findById(customerId)
        .switchIfEmpty(Mono.error(
            new IllegalArgumentException("Customer does not exist")
        ))
        .flatMap(customer -> reactiveOrderRepository.insert(
            new OrderDocument(
                null, number, customer.id(), 0L, Instant.now()
            )
        ));
}
~~~

Ví dụ giả định hai reactive repository là dependency được inject vào service. **flatMap** bảo đảm lệnh ghi Order chỉ được thực hiện sau khi đã đọc Customer thành công, nhưng hai thao tác vẫn **không tự động có transaction**. Giữa kiểm tra và ghi vẫn có thể xảy ra thay đổi đồng thời, tương tự imperative access.

Nếu cần reactive transaction, phải cấu hình **ReactiveMongoTransactionManager** và quản lý ngữ cảnh transaction qua cơ chế reactive phù hợp. Không gọi block() trong chuỗi xử lý reactive chỉ để ép các thao tác tham chiếu chạy đồng bộ.

Khi resolve reference lazy trong ứng dụng reactive, cần đặc biệt kiểm tra hành vi I/O và proxy. Một mapping tiện dụng không tự bảo đảm tải tham chiếu theo cách non-blocking ở mọi ngữ cảnh; với luồng có yêu cầu hiệu năng và khả năng dự đoán cao, có thể chủ động sử dụng reactive repository và truy vấn theo batch.

## 16. Kiểm thử quan hệ tham chiếu và cascade

Không nên chỉ kiểm tra một lần lưu Order thành công. Bộ kiểm thử cần chứng minh rằng liên kết được lưu đúng kiểu, đọc được và **không lan thao tác ngoài ý muốn**.

| Trường hợp | Điều cần xác minh |
| --- | --- |
| Tạo Customer rồi Order | Order lưu đúng customerId; tải được Customer từ ID. |
| Tạo Order với customerId không tồn tại | Service từ chối hoặc xử lý theo hợp đồng; không âm thầm coi liên kết hợp lệ. |
| Lưu Order dùng @DocumentReference | Trường tham chiếu có hình dạng BSON dự kiến; Customer không bị insert ngoài ý muốn. |
| Lưu Order dùng @DBRef | BSON chứa DBRef đúng; thao tác lưu Order không cascade-save Customer. |
| Xóa một Order | Customer được giữ lại. |
| Cố xóa Customer còn Orders | Chính sách chặn/soft delete hoặc xử lý có kiểm soát được áp dụng. |
| Gỡ productId khỏi mảng | Product vẫn tồn tại; chỉ liên kết thay đổi. |
| Customer bị thiếu do dữ liệu cũ | Đường đọc/aggregation xử lý dangling reference rõ ràng. |
| Đọc nhiều Orders | Số truy vấn và độ trễ nằm trong giới hạn chấp nhận. |
| Transaction rollback | Các ghi trong cùng transaction được rollback đúng; không công bố thành công trước commit. |

### 16.1. Ví dụ kiểm thử không cascade-delete

Ví dụ dùng JUnit 5 và repository, với cấu hình database test riêng:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import java.time.Instant;

@SpringBootTest
class OrderReferenceTest {
    @Autowired CustomerRepository customerRepository;
    @Autowired OrderRepository orderRepository;

    @Test
    void deletingOrderDoesNotDeleteCustomer() {
        CustomerDocument customer = customerRepository.insert(
            new CustomerDocument(null, "Test Customer", null)
        );

        try {
            OrderDocument order = orderRepository.insert(
                new OrderDocument(
                    null,
                    "TEST-" + java.util.UUID.randomUUID(),
                    customer.id(),
                    123L,
                    Instant.now()
                )
            );

            orderRepository.deleteById(order.id());

            assertThat(orderRepository.findById(order.id()))
                .isEmpty();
            assertThat(customerRepository.findById(customer.id()))
                .isPresent();
        } finally {
            customerRepository.deleteById(customer.id());
        }
    }
}
~~~

Kiểm thử này xác nhận hành vi **xóa Order không xóa Customer** với mô hình ID thủ công. Nó chưa kiểm tra tình huống lỗi khi xóa giữa chừng, mọi dạng reference hay transaction. Nên bổ sung fixture raw BSON để xác minh chính xác cấu trúc @DocumentReference và @DBRef trong dự án.

## 17. Cảnh báo khi chuyển từ embedded sang reference

Giả sử phiên bản cũ nhúng Customer vào Order:

~~~javascript
{
  orderNumber: "ORD-OLD",
  customer: {
    displayName: "Lan",
    email: "lan@example.test"
  }
}
~~~

Phiên bản mới tách Customer sang collection customers và chỉ giữ customerId:

~~~javascript
{
  orderNumber: "ORD-NEW",
  customerId: ObjectId("507f1f77bcf86cd799439011")
}
~~~

**Chỉ thay field Java từ Customer thành ObjectId không tự chuyển BSON cũ.** Migration cần:

1. Xác định mỗi Customer nhúng có phải thực thể dùng chung hay snapshot lịch sử.
2. Chọn khóa nhận diện Customer duy nhất trước khi tạo document đích; tránh tạo trùng Customer cho cùng một người.
3. Ghi Customer đích và lưu ID trả về.
4. Cập nhật Order sang schema mới bằng thao tác có điều kiện hoặc transaction tùy bất biến.
5. Triển khai reader tương thích trong lúc hai cấu trúc cùng tồn tại.
6. Kiểm tra dữ liệu, đối soát tham chiếu và chỉ xóa field cũ sau cửa sổ rollback.

Đặc biệt, **snapshot lịch sử** có thể không nên xóa dù đã có Customer tham chiếu. Ví dụ địa chỉ giao hàng tại thời điểm mua phải còn nguyên sau khi khách hàng đổi địa chỉ hiện tại.

## 18. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Lưu Order nhưng không thấy Customer mới | Nghĩ @DocumentReference hoặc @DBRef tự cascade-save | Persist Customer riêng rồi lưu Order. |
| Xóa Order làm mất Customer | Service tự viết cascade-delete quá rộng | Xác định ownership; bỏ cascade tới thực thể dùng chung. |
| Order có customerId nhưng không tải được Customer | Tham chiếu gãy, sai kiểu ID hoặc database/collection sai | Kiểm tra BSON _id và customerId, policy dangling reference. |
| Đọc danh sách Orders rất chậm | N+1 lookup, lazy resolve hoặc query không dùng index | Batch fetch, $lookup, đo executionStats. |
| Đổi @DBRef sang @DocumentReference rồi không đọc được bản cũ | BSON biểu diễn reference khác nhau | Migration hoặc converter tương thích. |
| Không thể xóa Customer dù không còn Order | Chính sách cleanup chưa phân biệt orphan và thực thể độc lập | Định nghĩa vòng đời và kiểm tra dữ liệu thực. |
| Kiểm tra tồn tại Customer rồi vẫn tạo tham chiếu gãy | Race giữa kiểm tra và xóa ở tiến trình khác | Dùng giao thức nhất quán, trạng thái/tombstone hoặc transaction phù hợp. |
| Annotation tham chiếu vẫn cho phép ID không hợp lệ | MongoDB không tự kiểm tra foreign key | Validation kiểu kết hợp với kiểm tra tồn tại ở ứng dụng. |
| Reactive pipeline gây I/O bất ngờ | Tự resolve reference/lazy loading hoặc block() | Thiết kế reactive query tường minh và đo trên luồng thật. |

## 19. Bài tập thực hành

### Bài tập 1: xác định điều gì sẽ được lưu

Cho mã:

~~~java
CustomerDocument customer = new CustomerDocument(
    null, "Lan", "lan@example.test"
);
OrderWithDocumentReference order = new OrderWithDocumentReference(
    null, "ORD-5001", customer, Instant.now()
);

orderWithRefRepository.insert(order);
~~~

**Câu hỏi:** Sau lệnh insert Order, có được kết luận Customer cũng đã tồn tại trong customers không?

**Đáp án:** Không. @DocumentReference không cascade-save mặc định. Cần lưu hoặc xác nhận Customer có định danh hợp lệ trước khi tạo Order tham chiếu.

### Bài tập 2: xóa parent và target

Ba Order cùng trỏ tới một Customer. Nếu xóa một Order, có nên xóa Customer không?

**Đáp án:** Không theo mặc định. Customer có vòng đời độc lập và đang được các Order khác sử dụng. Xóa Order chỉ xóa Order; quy tắc xóa Customer cần được xử lý riêng theo nghiệp vụ.

### Bài tập 3: tìm dangling reference

Hãy xây pipeline tìm Order có customerId không tồn tại trong customers.

**Gợi ý:** sử dụng $lookup theo customerId → _id rồi lọc các kết quả có mảng matchedCustomers rỗng; với dữ liệu lớn, cân nhắc hiệu năng và lịch chạy kiểm tra.

### Bài tập 4: tối ưu N+1

API lấy 100 Order nhưng chỉ có 12 customerId khác nhau. Cách đọc nào giúp giảm truy vấn?

**Đáp án:** gom 12 ID duy nhất, query customers bằng $in rồi ánh xạ kết quả về từng Order. Với điều kiện phù hợp, có thể đánh giá thêm aggregation $lookup.

### Bài tập 5: chọn nhúng hay tham chiếu

Một Order chứa 3 dòng hàng, mỗi dòng có tên sản phẩm và giá tại thời điểm mua; Product catalog có thể đổi tên và giá theo thời gian. Bạn sẽ lưu gì?

**Gợi ý:** lưu snapshot tên/giá trong từng item nhúng để bảo toàn lịch sử; nếu cần truy cập catalog hiện hành, lưu thêm productId tham chiếu. Không mặc định cập nhật giá lịch sử theo Product.

### Bài tập 6: transaction có bảo đảm khóa ngoại không?

Một service kiểm tra Customer tồn tại rồi tạo Order trong transaction. Ở một service khác, Customer có thể bị xóa. Có thể kết luận không bao giờ xảy ra tham chiếu gãy không?

**Đáp án:** Chưa đủ. Phải xem toàn bộ giao thức tạo/xóa liên kết và cạnh tranh giữa các writer, không chỉ việc có @Transactional ở một service. Có thể cần giới hạn xóa, trạng thái soft-delete, cập nhật có điều kiện hoặc cơ chế phối hợp nhất quán.

## 20. Nguyên tắc cần ghi nhớ

1. **Reference là liên kết giữa các document độc lập**; bản thân liên kết không tạo khóa ngoại ở MongoDB.
2. **ID thủ công, @DocumentReference và @DBRef** có biểu diễn và cơ chế resolve khác nhau; chọn dựa trên hợp đồng lưu trữ và nhu cầu truy vấn.
3. **Spring Data MongoDB không cascade-save/cascade-delete referenced document mặc định**. Nếu muốn lan truyền thao tác, phải thiết kế và thực hiện có chủ đích.
4. **Xóa parent không nên xóa target dùng chung.** Tách chính sách xóa liên kết khỏi chính sách xóa thực thể.
5. **Dangling reference khác orphan**; xử lý dựa trên quyền sở hữu và vòng đời của từng loại dữ liệu.
6. **Transaction chỉ nhóm các thao tác đã được lập trình**, không tự tạo cascade, foreign key hoặc tính nhất quán liên dịch vụ.
7. **Truy vấn tham chiếu cần đo hiệu năng**. Cân nhắc batch fetch, $lookup, index và tránh N+1.
8. **Thay đổi cách lưu reference là thay đổi schema BSON**. Cần migration, reader tương thích và kiểm thử dữ liệu cũ.
9. **Reactive access vẫn phải bảo vệ cùng bất biến**, dù các thao tác chạy thông qua Mono/Flux.

Hiểu cách lưu document tham chiếu riêng và giới hạn cascade giúp dịch vụ **SPRING_DATA_MONGODB** bảo vệ vòng đời của từng aggregate, tránh xóa dữ liệu ngoài ý muốn và thiết kế các thao tác MongoTemplate, repository, transaction và reactive access có thể kiểm soát, kiểm thử và chẩn đoán được.
