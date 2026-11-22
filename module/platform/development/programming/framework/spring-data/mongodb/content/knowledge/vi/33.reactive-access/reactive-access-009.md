# Giới hạn DBRef, document reference và các tính năng chỉ có ở API đồng bộ

## 1. Bài toán: chuyển một hệ thống MongoDB từ blocking sang reactive

Một hệ thống đặt hàng đang dùng Spring Data MongoDB qua **MongoRepository** và **MongoTemplate**. Trong entity Order, một số lập trình viên khai báo quan hệ tới Customer/Product bằng **@DBRef** hoặc **@DocumentReference**, rồi truy cập property như một đối tượng Java đã được tải từ collection khác.

Khi ứng dụng chuyển sang **ReactiveMongoRepository** và **ReactiveMongoTemplate**, một thay đổi trông có vẻ đơn giản:

~~~java
// Ban đầu: blocking repository.
interface OrderRepository
        extends MongoRepository<OrderDocument, ObjectId> {}

// Sau khi chuyển: reactive repository.
interface ReactiveOrderRepository
        extends ReactiveMongoRepository<OrderDocument, ObjectId> {}
~~~

Tuy nhiên, **thay đổi kiểu trả về thành Mono/Flux không làm toàn bộ cơ chế quan hệ của mapping layer trở thành non-blocking**. Đặc biệt, cách Spring Data MongoDB tự đọc **DBRef/document references** có những giới hạn trong reactive infrastructure. Nếu vẫn phụ thuộc vào lazy reference resolution như blocking stack, ứng dụng có thể gặp lỗi mapping, field không được giải tham chiếu hoặc một thiết kế vô tình đưa I/O blocking vào luồng Reactor.

Trong bài, chúng ta sẽ xây cách đọc Order cùng Customer/Product một cách tường minh:

- Lưu **customerId** và **productIds** trong BSON thay vì dựa vào proxy quan hệ.
- Dùng **flatMap**, **Mono.zip**, **findById/findAllById** và query có điều kiện tenant để đọc reference theo reactive.
- Chọn **$lookup aggregation** cho một số tình huống cần join ở MongoDB Server.
- Phân biệt tính năng **không hỗ trợ**, **có API khác** và **được hỗ trợ có điều kiện** giữa hai stack.
- Không dùng **block()**, tự **subscribe()** hoặc dùng blocking repository bên trong luồng reactive.

Bài **Giới hạn DBRef, document reference và các tính năng chỉ có ở API đồng bộ** thuộc chương **Truy cập reactive** trong module **SPRING_DATA_MONGODB**. Phạm vi module gồm kết nối/ánh xạ document, thao tác MongoDB qua repository hoặc MongoTemplate, thiết kế truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng.

### 1.1. Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt **@DBRef**, **@DocumentReference**, **reference ID thuần** và embedded document.
2. Giải thích vì sao việc **đọc và giải tham chiếu tự động** không nên được trông đợi ở reactive mapping.
3. Thiết kế entity và DTO phù hợp với cách load reference bất đồng bộ.
4. Viết query reactive an toàn với tenant, giữ đúng thứ tự reference và xử lý reference bị thiếu.
5. Tránh N+1, uncontrolled concurrency và tích lũy bộ nhớ không giới hạn.
6. Chọn **$lookup** hoặc denormalization khi phù hợp.
7. Nhận biết những giới hạn ở **repository, template, session, AOT và kiểu trả về** theo phiên bản Spring Data.
8. Viết integration test với MongoDB thật và **StepVerifier**.

## 2. Hai stack Spring Data MongoDB khác nhau ở đâu?

Một ứng dụng có thể dùng đồng thời hai nhóm API, nhưng chúng không hoán đổi trực tiếp cho nhau.

| Khía cạnh | Imperative/blocking | Reactive/non-blocking |
| --- | --- | --- |
| Dependency Boot thường dùng | spring-boot-starter-data-mongodb | spring-boot-starter-data-mongodb-reactive |
| Template | MongoTemplate | ReactiveMongoTemplate |
| Repository | MongoRepository | ReactiveMongoRepository |
| Phương thức tìm theo ID | Optional/đối tượng tùy API | Mono<Entity> |
| Truy vấn nhiều kết quả | List/Stream/Iterable | Flux<Entity> |
| Driver I/O | Blocking MongoDB Java Driver | MongoDB Reactive Streams Driver |
| Thực thi query | Lệnh đồng bộ khi method được gọi/tiêu thụ | Publisher thường **lazy**, chạy theo subscription |
| Tham gia transaction | MongoTransactionManager | ReactiveMongoTransactionManager |
| Transaction context | Thread-bound | Reactor Context |
| Mapping reference tự động | DBRef/DocumentReference có cơ chế giải tham chiếu | Không coi giải tham chiếu tự động là tính năng hỗ trợ |

**Reactive không phải một chế độ được bật bằng cách đổi chữ Mongo thành Reactive.** Nếu một thành phần vẫn gọi blocking MongoRepository, JDBC hoặc HTTP client đồng bộ từ một event loop, request có thể bị chặn dù bên ngoài trả Mono.

### 2.1. Vẫn dùng cùng MongoDB Server

Hai stack đều gửi MongoDB commands đến server và dùng chung:

- Collection, BSON documents và indexes.
- MongoDB CRUD/aggregation capabilities mà API/driver tương ứng phơi bày.
- Semantics của query/filter, write concern và server-side transactions.
- Nguyên tắc bảo mật, multi-tenant và consistency.

Thứ khác nhau chủ yếu là **thời điểm/lifecycle I/O, publisher, conversion và cách API tích hợp**. Không khẳng định MongoDB Server “không có join” chỉ vì một tiện ích mapping không có ở reactive Java layer.

### 2.2. Một bảng quyết định nhanh

| Bài toán | Cách tiếp cận |
| --- | --- |
| Đọc entity độc lập theo ID | ReactiveMongoRepository.findById |
| Đọc một entity rồi đọc reference theo khóa | flatMap + repository/template |
| Đọc nhiều ID reference | Query.in hoặc findAllById rồi tái lập thứ tự |
| Trả toàn bộ dữ liệu liên quan trong một pipeline | MongoDB $lookup qua ReactiveMongoTemplate |
| Cần quan hệ luôn có mặt, nhỏ và thay đổi cùng nhau | Xem xét embedded document |
| Có code cũ cần @DBRef proxy lazy | Giữ ở blocking boundary có kiểm soát hoặc refactor sang IDs |
| Cần MongoDB transaction reactive | ReactiveMongoTransactionManager / TransactionalOperator |
| Cần một tiện ích chỉ có ở API đồng bộ | Thiết kế adapter riêng, tránh block event loop và kiểm tra tài liệu version |

## 3. @DBRef là gì?

MongoDB hỗ trợ một quy ước lưu tham chiếu gọi là **DBRef**, có dạng document đặc biệt chứa các field như **$ref** và **$id**, có thể kèm **$db**.

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439012"),
  tenantId: "shop-a",
  customer: {
    $ref: "customers",
    $id: ObjectId("507f1f77bcf86cd799439011")
  }
}
~~~

Ở Java blocking stack:

~~~java
import org.springframework.data.mongodb.core.mapping.DBRef;

@Document(collection = "orders")
class BlockingOrder {

    @Id ObjectId id;
    String tenantId;

    @DBRef
    CustomerDocument customer;
}
~~~

Spring Data mapping layer có cơ chế đọc DBRef rồi truy vấn document đích. Với tùy chọn **@DBRef(lazy=true)**, blocking stack có thể tạo lazy proxy và chỉ tải giá trị khi caller truy cập property.

### 3.1. DBRef không phải foreign key

DBRef không tự tạo ràng buộc khóa ngoại như một quan hệ SQL. MongoDB không tự:

- Bảo đảm document Customer được tham chiếu vẫn tồn tại.
- Xóa theo cascade khi Order bị xóa.
- Lưu Customer tự động mỗi lần gọi save(Order).
- Kiểm soát quyền truy cập document đích theo tenant.

**Tham chiếu là một cách mô tả liên kết; tính toàn vẹn vòng đời vẫn thuộc nghiệp vụ.**

### 3.2. Lazy DBRef trong blocking stack

~~~java
@DBRef(lazy = true)
private CustomerDocument customer;
~~~

Lời gọi tưởng như truy cập property thường:

~~~java
String name = order.getCustomer().getName();
~~~

có thể kích hoạt truy vấn MongoDB **đồng bộ** để lấy Customer. Điều này dễ dẫn tới I/O ẩn, khó phát hiện N+1 và rối phạm vi sống của ClientSession.

Với Java mới và JDK strong encapsulation, một số proxy lazy còn chịu giới hạn class/proxy/reflection. Không nên thiết kế WebFlux dựa trên việc JVM tự cho phép mọi lazy DBRef proxy.

## 4. @DocumentReference khác DBRef ra sao?

Spring Data MongoDB còn có **@DocumentReference**, cho phép lưu một pointer/reference linh hoạt hơn so với format DBRef.

Blocking entity minh họa:

~~~java
import org.springframework.data.mongodb.core.mapping.DocumentReference;

@Document(collection = "orders")
class BlockingOrder {

    @Id ObjectId id;
    String tenantId;

    @DocumentReference
    CustomerDocument customer;
}
~~~

Với mặc định dựa trên ID, BSON có thể lưu:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439012"),
  tenantId: "shop-a",
  customer: ObjectId("507f1f77bcf86cd799439011")
}
~~~

Đây là **một giá trị khóa**, không phải một DBRef có $ref/$id. Tuy vậy, annotation vẫn yêu cầu Spring Data **đọc document đích và ánh xạ thành CustomerDocument** khi nạp Order.

### 4.1. Tính linh hoạt của document reference

Tùy phiên bản Spring Data, @DocumentReference có các lựa chọn:

- Tên collection/database đích.
- Biểu thức **lookup** riêng.
- **sort** cho collection reference.
- **lazy**.
- Document pointer/converter do ứng dụng cấu hình.

Những lựa chọn này phục vụ **cơ chế giải tham chiếu của mapping layer**. Không mặc định chúng được thực thi tự động bởi reactive infrastructure.

### 4.2. Pointer thuần và @DocumentReference không tương đương

Nếu Java entity khai báo:

~~~java
ObjectId customerId;
~~~

thì property được đọc như một ObjectId bình thường. Ứng dụng **chủ động** quyết định có đi truy vấn customers hay không.

Ngược lại:

~~~java
@DocumentReference
CustomerDocument customer;
~~~

thể hiện yêu cầu mapping layer biến một pointer thành entity đích, nên nó không còn là phép đọc field thuần.

**Đổi DBRef sang @DocumentReference không tự khắc phục giới hạn đọc reference trong reactive.**

## 5. Giới hạn cốt lõi: reactive không giải tham chiếu tự động

Tài liệu Spring Data MongoDB về DBRef/document references nêu rõ **không hỗ trợ đọc document references bằng reactive infrastructure**. Tài liệu về Querydsl/reactive cũng lưu ý **DBRef joins không được hỗ trợ trong Reactive MongoDB**.

Điều này dẫn đến quy tắc thiết kế:

> **Khi đọc entity bằng ReactiveMongoTemplate/ReactiveMongoRepository, không dựa vào việc @DBRef hoặc @DocumentReference được tự động resolve thành entity đích.**

Đừng coi một entity đã compile, save được hoặc có field pointer trong BSON là bằng chứng rằng **reactive read tự tải được reference**.

### 5.1. Điều gì thường gây hiểu nhầm?

**Trường hợp A — Lưu thành công nhưng đọc không được entity liên kết.**

Ứng dụng ghi một Order có pointer tới Customer, nhưng khi query reactive, field customer không được giải theo kỳ vọng. Đó không phải bằng chứng document đích mất; hãy đọc BSON gốc và kiểm tra mapping capability.

**Trường hợp B — Dùng lazy=true với hy vọng không blocking.**

Lazy property trong blocking stack có thể gọi I/O đồng bộ khi getter chạy. Reactive không trở thành non-blocking chỉ vì property chưa được truy cập ngay.

**Trường hợp C — Gắn một annotation khác mà không thay đổi thiết kế.**

@DocumentReference có cấu trúc lưu trữ khác @DBRef, nhưng vấn đề vẫn nằm ở việc mapping cần fetch thêm document trong quá trình conversion.

**Trường hợp D — Dùng Mono.just với object có lazy proxy.**

~~~java
// Mono.just không biến I/O blocking bên trong getter thành reactive.
return Mono.just(blockingOrder.getCustomer().getName());
~~~

Biểu thức truyền cho Mono.just được tính trước, và getter có thể block ngay khi method được gọi.

### 5.2. Giới hạn của Spring Data không phải giới hạn của MongoDB $lookup

MongoDB Server vẫn hỗ trợ **$lookup** cho nhiều trường hợp join giữa các collection. ReactiveMongoTemplate có thể gửi aggregation pipeline có $lookup để nhận kết quả dưới dạng Flux.

Không nên viết “MongoDB reactive không hỗ trợ join” một cách tuyệt đối. Chính xác hơn:

- **Không trông đợi converter tự resolve @DBRef/@DocumentReference qua reactive.**
- **Có thể truy vấn tường minh qua reactive repositories/templates.**
- **Có thể thực hiện $lookup ở server nếu dữ liệu và query phù hợp.**

### 5.3. Kiểm tra compatibility theo phiên bản

Tính năng Spring Data thay đổi theo thế hệ thư viện. Với một release cụ thể, kiểm tra tài liệu của **chính phiên bản đang build**. Bài này hướng dẫn mô hình an toàn không phụ thuộc automatic reference resolution.

## 6. Bốn cách mô hình hóa quan hệ trong MongoDB reactive

| Mô hình | BSON ví dụ | Ưu điểm | Điều cần chú ý |
| --- | --- | --- | --- |
| Embedded | order.customerSnapshot | Một lần đọc, dữ liệu sát order | Dữ liệu lặp, snapshot phải có ý nghĩa nghiệp vụ |
| Reference ID thuần | order.customerId | Mapping giản đơn, explicit fetch | Service phải tự đọc Customer |
| List reference IDs | order.productIds | Linh hoạt, có thể batch fetch | Thứ tự và missing IDs phải được xử lý |
| Server-side $lookup | Pipeline join orders/products | Gom truy vấn, projection tập trung | Chi phí join, index, memory, giới hạn server |

**Không có lựa chọn tối ưu cho mọi quan hệ.** Nên hỏi:

1. Customer/Product có thay đổi độc lập không?
2. Order cần giữ snapshot lịch sử hay luôn xem dữ liệu mới nhất?
3. Số lượng reference trong một Order có thể lớn tới đâu?
4. API nào thực sự cần join dữ liệu?
5. Cần những ràng buộc tenant, trạng thái và thời điểm nào?

### 6.1. Khi nào embedded phù hợp?

Với địa chỉ giao hàng hoặc giá sản phẩm tại thời điểm mua, snapshot thường phù hợp:

~~~javascript
{
  orderNo: "ORD-001",
  shippingAddress: {
    recipient: "A",
    city: "Ha Noi"
  },
  items: [
    { sku: "BOOK-101", quantity: 2, priceMinor: NumberLong("120000") }
  ]
}
~~~

Địa chỉ/giá tại thời điểm đặt hàng **không nên bị tự thay đổi** khi customer cập nhật địa chỉ hoặc catalog thay giá. Lúc đó embedded snapshot là lựa chọn nghiệp vụ, không chỉ mẹo tránh DBRef.

### 6.2. Khi nào ID reference phù hợp?

Nếu cần đường dẫn từ Order sang Customer hiện tại, lưu customerId và thực hiện query khi cần:

~~~javascript
{
  orderNo: "ORD-001",
  tenantId: "shop-a",
  customerId: ObjectId("507f1f77bcf86cd799439011")
}
~~~

Khóa được lưu như một giá trị BSON thông thường và không yêu cầu converter tự fetch entity liên quan.

## 7. Domain mẫu không sử dụng @DBRef/@DocumentReference

Tạo ba collection **customers**, **products**, **orders**.

~~~javascript
// customers
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  tenantId: "shop-a",
  displayName: "Khach hang A",
  active: true
}
~~~

~~~javascript
// products
{
  _id: ObjectId("507f1f77bcf86cd799439021"),
  tenantId: "shop-a",
  sku: "BOOK-101",
  name: "Spring Data MongoDB",
  active: true
}
~~~

~~~javascript
// orders
{
  _id: ObjectId("507f1f77bcf86cd799439031"),
  tenantId: "shop-a",
  customerId: ObjectId("507f1f77bcf86cd799439011"),
  productIds: [ObjectId("507f1f77bcf86cd799439021")],
  status: "PAID"
}
~~~

Đây là **BSON pointer theo khóa** do ứng dụng quy định, không phải DBRef format. Mỗi Order vẫn có tenantId để giới hạn quyền truy vấn.

### 7.1. Java entity dùng ObjectId

~~~java
package com.example.reactiveorders;

import java.util.List;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "customers")
public record CustomerDocument(
    @Id ObjectId id,
    String tenantId,
    String displayName,
    boolean active
) {}

@Document(collection = "products")
public record ProductDocument(
    @Id ObjectId id,
    String tenantId,
    String sku,
    String name,
    boolean active
) {}

@Document(collection = "orders")
public record OrderDocument(
    @Id ObjectId id,
    String tenantId,
    ObjectId customerId,
    List<ObjectId> productIds,
    String status
) {}
~~~

Mỗi **public record** cần đặt trong một file riêng theo quy tắc Java. Bài ghép chung để dễ theo dõi mô hình.

### 7.2. Không thay ObjectId thành String tùy tiện

MongoDB ObjectId và String có thể trông giống nhau khi hiển thị nhưng **khác BSON type**. Nếu Customer._id là ObjectId, một query trên field String thông thường bằng chuỗi 24 hex có thể không match theo cách bạn kỳ vọng.

Việc Spring Data tự convert **@Id String** sang ObjectId trong một số tình huống cũng không có nghĩa mọi String reference property đều được convert tương tự. Chọn cùng kiểu BSON cho ID và foreign-key field, hoặc định nghĩa converter rõ ràng và kiểm thử.

### 7.3. Có cần lưu DBRef để dùng $lookup?

**Không.** $lookup có thể join theo các field thông thường như customerId ↔ _id hoặc productIds ↔ _id. Khóa thuần thường đơn giản hơn DBRef cho reactive use cases.

## 8. Reactive repositories: khai báo theo khóa

~~~java
package com.example.reactiveorders;

import java.util.Collection;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ReactiveOrderRepository
        extends ReactiveMongoRepository<OrderDocument, ObjectId> {

    Mono<OrderDocument> findByIdAndTenantId(
        ObjectId id, String tenantId
    );
}

public interface ReactiveCustomerRepository
        extends ReactiveMongoRepository<CustomerDocument, ObjectId> {

    Mono<CustomerDocument> findByIdAndTenantId(
        ObjectId id, String tenantId
    );
}

public interface ReactiveProductRepository
        extends ReactiveMongoRepository<ProductDocument, ObjectId> {

    Flux<ProductDocument> findByTenantIdAndIdIn(
        String tenantId, Collection<ObjectId> ids
    );
}
~~~

Tương tự các entity, ba public interface cần nằm trong ba source file riêng trong dự án.

Các method derived-query có **tenantId** là lớp bảo vệ dữ liệu quan trọng: chỉ gọi findById cho entity liên quan có thể trả document thuộc tenant khác nếu người dùng biết ObjectId đó.

### 8.1. Không trông đợi phương thức getCustomer() tự fetch

~~~java
OrderDocument order = ...;
ObjectId customerId = order.customerId();
~~~

Ở đây **customerId() chỉ trả ObjectId**, không gọi database. Nếu API cần Customer, service phải gọi customerRepository hoặc ReactiveMongoTemplate một cách tường minh.

### 8.2. Tính lazy của publisher

~~~java
Mono<OrderDocument> order =
    orderRepository.findByIdAndTenantId(id, tenantId);
~~~

Đây là Publisher mô tả thao tác tìm. Thực thi thường bắt đầu khi có subscription. Không gọi repository rồi bỏ Mono vì tưởng đã fetch xong dữ liệu; cũng không gọi subscribe() trong service chỉ để ép chạy.

## 9. Load Order + Customer bằng flatMap

DTO kết quả:

~~~java
package com.example.reactiveorders;

public record CustomerSummary(
    ObjectId id,
    String displayName
) {}

public record OrderWithCustomer(
    ObjectId id,
    String status,
    CustomerSummary customer
) {}
~~~

Service:

~~~java
package com.example.reactiveorders;

import org.bson.types.ObjectId;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class OrderReadService {

    private final ReactiveOrderRepository orders;
    private final ReactiveCustomerRepository customers;

    public OrderReadService(
            ReactiveOrderRepository orders,
            ReactiveCustomerRepository customers) {
        this.orders = orders;
        this.customers = customers;
    }

    public Mono<OrderWithCustomer> read(
            ObjectId orderId,
            String authenticatedTenantId) {

        return orders.findByIdAndTenantId(
                orderId, authenticatedTenantId)
            .flatMap(order ->
                customers.findByIdAndTenantId(
                        order.customerId(), authenticatedTenantId)
                    .map(customer ->
                        new OrderWithCustomer(
                            order.id(),
                            order.status(),
                            new CustomerSummary(
                                customer.id(), customer.displayName()
                            )
                        )
                    )
            );
    }
}
~~~

**Cách hoạt động:**

1. Tìm Order đã giới hạn tenant.
2. Khi Order được phát, lấy **customerId** từ chính Order đó.
3. Truy vấn Customer trong cùng tenant bằng một Mono khác.
4. Ánh xạ hai kết quả thành DTO.
5. Nếu Order hoặc Customer không tồn tại, pipeline ở dạng này có thể hoàn thành rỗng; service cần quy định contract cụ thể.

### 9.1. Xử lý reference bị thiếu

Đừng để **Mono.empty()** ngầm trở thành “Order không tồn tại” nếu thực ra Customer bị xóa hoặc bị ẩn theo quyền. Có thể dùng lỗi nghiệp vụ rõ:

~~~java
return orders.findByIdAndTenantId(orderId, tenantId)
    .switchIfEmpty(Mono.error(new OrderNotFoundException()))
    .flatMap(order ->
        customers.findByIdAndTenantId(
                order.customerId(), tenantId)
            .switchIfEmpty(
                Mono.error(new MissingReferenceException(
                    "Customer unavailable")))
            .map(customer -> toDto(order, customer))
    );
~~~

OrderNotFoundException, MissingReferenceException và toDto là các thành phần nghiệp vụ minh họa cần định nghĩa riêng. Quyết định có coi missing reference là lỗi, null hoặc fallback phải dựa trên API contract.

### 9.2. Khi chỉ cần thông tin Customer

Nếu caller chỉ yêu cầu **displayName**, không cần tải nhiều field như addresses, permissions hoặc preferences. Cân nhắc projection DTO hoặc Query.fields().include(...) phù hợp để giảm payload và tránh lộ dữ liệu không cần thiết.

### 9.3. flatMap không tạo transaction

Hai lệnh đọc trong chuỗi flatMap **không tự nằm trong một transaction/snapshot**. Customer có thể thay đổi hoặc bị xóa giữa hai lần đọc. Khi cần consistency mạnh, thiết kế transaction/read concern/snapshot theo yêu cầu, thay vì coi Reactor chain là một operation MongoDB nguyên tử.

## 10. Mono.zip: khi có các truy vấn độc lập

Nếu đã biết các ID cần đọc, có thể kết hợp những Publisher độc lập:

~~~java
Mono<CustomerDocument> customer =
    customerRepository.findByIdAndTenantId(customerId, tenantId);

Mono<ProductDocument> product =
    productRepository.findById(productId);

Mono.zip(customer, product)
    .map(tuple -> new OverviewDto(
        tuple.getT1().displayName(),
        tuple.getT2().name()
    ));
~~~

OverviewDto là DTO minh họa; repository/product ID cần được giới hạn theo tenant trước khi áp dụng vào API nhiều tenant. **Mono.zip** hữu ích khi hai Publisher không phụ thuộc nhau, nhưng không nên dùng để bỏ qua authorization hoặc tự biến hai lần đọc thành snapshot nhất quán.

### 10.1. Mono.zip với nguồn rỗng

Nếu một Mono hoàn thành rỗng, **Mono.zip có thể hoàn thành rỗng** mà không tạo DTO. Muốn trả thông tin về reference thiếu, xử lý switchIfEmpty trên từng nguồn trước khi zip.

### 10.2. Không ghép kết quả bằng block()

~~~java
// Không nên trong WebFlux/reactive service.
CustomerDocument customer = customerRepository
    .findById(customerId)
    .block();
~~~

block() biến việc chờ I/O thành synchronous wait; trên event loop có thể làm tắc nghẽn request hoặc bị Reactor từ chối.

### 10.3. Đừng lạm dụng subscribe()

~~~java
// Không làm như vậy để gán Customer bất đồng bộ vào field mutable.
customerRepository.findById(customerId)
    .subscribe(customer -> order.setCustomer(customer));
return Mono.just(order);
~~~

Mono.just(order) có thể được phát **trước khi** callback subscribe chạy. Hơn nữa, ta đã tạo subscription phụ khó quản lý cancellation/error. Hãy **return chain flatMap/map** để caller kiểm soát subscription duy nhất.

## 11. Một Order chứa nhiều productIds: batch lookup thay vì N+1

Order có:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439031"),
  tenantId: "shop-a",
  productIds: [
    ObjectId("507f1f77bcf86cd799439021"),
    ObjectId("507f1f77bcf86cd799439022"),
    ObjectId("507f1f77bcf86cd799439023")
  ]
}
~~~

Cách ngây thơ là query từng ID:

~~~java
Flux<ProductDocument> products = Flux
    .fromIterable(order.productIds())
    .concatMap(productId ->
        productRepository.findById(productId)
    );
~~~

Nếu một Order có **N productIds**, code này có thể tạo **N truy vấn MongoDB**. Ngoài ra, dùng findById không có tenant filter có nguy cơ đọc sản phẩm khác tenant.

### 11.1. Query gom các ID trong một lần

Repository:

~~~java
Flux<ProductDocument> findByTenantIdAndIdIn(
    String tenantId,
    Collection<ObjectId> ids
);
~~~

Service:

~~~java
return orderRepository.findByIdAndTenantId(orderId, tenantId)
    .flatMap(order ->
        productRepository
            .findByTenantIdAndIdIn(
                tenantId, order.productIds())
            .collectList()
            .map(products -> toOrderDetails(order, products))
    );
~~~

Trong code này, toOrderDetails là hàm chuyển DTO nghiệp vụ tự định nghĩa. Query tương đương:

~~~javascript
db.products.find({
  tenantId: "shop-a",
  _id: { $in: [productIdA, productIdB, productIdC] }
});
~~~

**Ưu điểm:** Một lần truy vấn tới collection products có thể lấy nhiều ID. MongoDB có unique index trên _id và query còn ràng buộc tenant.

### 11.2. collectList có giới hạn rõ

**collectList()** giữ toàn bộ product results của một Order trong RAM. Nó hợp lý khi sản phẩm tham chiếu trên mỗi Order được kiểm soát, chẳng hạn không quá 50 hoặc 100 ID theo quy tắc nghiệp vụ.

Không dùng collectList trên một Flux có thể chứa hàng triệu product hoặc một change stream vô hạn. Để đọc tập rất lớn, cần phân lô hoặc thực hiện aggregation có kế hoạch bộ nhớ.

### 11.3. ID bị trùng, ID bị mất và thứ tự

Truy vấn **$in** không bảo đảm trả sản phẩm theo đúng thứ tự productIds. Ngoài ra:

- Hai ID giống nhau trong productIds có thể mang ngữ nghĩa lặp lại.
- Một Product đã bị xóa có thể không được trả.
- Một Product thuộc tenant khác không được trả do điều kiện tenant.
- Một Product đã inactive có thể cần bị loại hoặc vẫn giữ để báo cáo lịch sử.

Không trả về List products theo thứ tự MongoDB ngẫu nhiên rồi cho rằng nó khớp index của item trong Order.

## 12. Tái lập thứ tự reference bằng một DTO rõ ràng

Một response thường cần giữ thứ tự dòng sản phẩm như Order. Để tránh lệ thuộc thứ tự của $in, tạo map theo ID rồi duyệt lại danh sách ID gốc.

~~~java
package com.example.reactiveorders;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.bson.types.ObjectId;

public record ProductSummary(
    ObjectId id,
    String sku,
    String name
) {}

public record OrderDetails(
    ObjectId id,
    String status,
    List<ProductSummary> products
) {}

public final class OrderDetailsMapper {

    private OrderDetailsMapper() {}

    public static OrderDetails map(
            OrderDocument order,
            List<ProductDocument> loaded) {

        Map<ObjectId, ProductDocument> byId = new HashMap<>();
        for (ProductDocument product : loaded) {
            byId.put(product.id(), product);
        }

        List<ProductSummary> ordered = new ArrayList<>();
        for (ObjectId id : order.productIds()) {
            ProductDocument product = byId.get(id);

            if (product == null) {
                throw new IllegalStateException(
                    "A referenced product is missing or inaccessible");
            }

            ordered.add(new ProductSummary(
                product.id(),
                product.sku(),
                product.name()
            ));
        }

        return new OrderDetails(
            order.id(),
            order.status(),
            List.copyOf(ordered)
        );
    }
}
~~~

Mỗi public record/class phải ở file Java riêng khi dùng thật. Logic bên trên:

1. Truy vấn sản phẩm theo **tenantId + tập ID**.
2. Tạo map ID → document.
3. Duyệt productIds gốc để phục hồi thứ tự.
4. Kiểm tra document tham chiếu bị thiếu hoặc không thuộc tenant.
5. Trả DTO được định nghĩa rõ.

### 12.1. Duplicate references

Nếu productIds chứa cùng một ID hai lần, vòng lặp vẫn thêm hai ProductSummary. Nếu nghiệp vụ Order cho phép nhiều dòng cùng SKU với quantity khác nhau, tốt hơn nên lưu **order items** có **productId, quantity, priceAtOrder** thay vì chỉ một List IDs.

### 12.2. Missing-reference policy

Có thể chọn một trong các hợp đồng:

- **Strict:** một reference thiếu → báo dữ liệu không toàn vẹn.
- **Tolerant:** thay item thiếu bằng một marker “unavailable”, giữ ID gốc.
- **Snapshot:** dùng thông tin sản phẩm đã lưu trong Order thay vì cần Product hiện tại.

Không tự coi một reference thiếu là bằng chứng Product không tồn tại nếu nguyên nhân thực là **tenant filter** chặn truy cập. Public error cần tránh tiết lộ dữ liệu khác tenant.

### 12.3. Tại sao dùng DTO?

DTO tách **đối tượng dữ liệu được lưu** khỏi **mô hình response**. Không nên gán ProductDocument đã fetch vào một transient field OrderDocument rồi gọi repository.save(order) nếu mapping có thể gây ghi lại dữ liệu không cần thiết.

## 13. ReactiveMongoTemplate: query rõ đường dẫn BSON

Khi không muốn tạo một derived repository method cho mọi bộ filter:

~~~java
import java.util.Collection;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import reactor.core.publisher.Flux;

public Flux<ProductDocument> loadProducts(
        ReactiveMongoTemplate template,
        String tenantId,
        Collection<ObjectId> productIds) {

    if (tenantId == null || tenantId.isBlank()) {
        return Flux.error(
            new IllegalArgumentException("Tenant required"));
    }

    if (productIds == null || productIds.isEmpty()) {
        return Flux.empty();
    }

    Query query = Query.query(
        Criteria.where("tenantId").is(tenantId)
            .and("_id").in(productIds)
    );

    query.fields()
        .include("_id")
        .include("tenantId")
        .include("sku")
        .include("name")
        .include("active");

    return template.find(query, ProductDocument.class);
}
~~~

Đây là **một reactive find** với các điều kiện explicit. Không có @DBRef/@DocumentReference và không cần một proxy lazy.

### 13.1. Mapping Java/BSON

Nếu ProductDocument dùng **@Field("tenant_id")**, Spring Data template mapping thông thường có thể chuyển property tenantId sang field BSON tương ứng. Khi viết raw BSON Document, phải dùng tên BSON thật, không mặc định raw field name được chuyển giống Criteria trên entity.

### 13.2. Projection và save partial entity

Truy vấn dùng Query.fields() chỉ tải một phần field; kết quả mapping vào ProductDocument có thể để các field khác ở giá trị mặc định/null. **Không save lại một entity chỉ tải một phần** để tránh ghi sai dữ liệu.

Nếu mục tiêu là read DTO, ưu tiên projection DTO/mapping phù hợp thay vì vật hóa entity và coi đó là đầy đủ.

### 13.3. Index

MongoDB có index mặc định trên **_id**, nên filter theo tập ObjectId thường có đường truy vấn tốt nếu tập ID không quá lớn. Một index compound trên tenantId và _id không phải lúc nào cũng có lợi; dùng **explain** với workload thật.

Nếu join theo business key khác _id, ví dụ sku, cần index hỗ trợ đúng pattern và uniqueness trong phạm vi tenant.

## 14. N+1 khi đọc nhiều Order từ một Flux

Đọc 1 Order và sau đó đọc 1 Customer là hai truy vấn; có thể hợp lý. Nhưng khi API đọc 1.000 Order rồi với mỗi Order lại gọi customerRepository, ta có thể tạo N+1:

~~~java
Flux<OrderWithCustomer> data =
    orderRepository.findAll()
        .flatMap(order ->
            customerRepository.findById(order.customerId())
                .map(customer -> toDto(order, customer))
        );
~~~

Ngoài N+1, còn có ba lỗi:

- **findAll() thiếu tenant**, có thể đọc toàn bộ orders.
- **findById() thiếu tenant** cho Customer.
- **flatMap() không giới hạn concurrency rõ**, có thể tạo nhiều lệnh I/O cùng lúc nếu upstream phát nhanh.

### 14.1. Bản sửa tối thiểu: filter và giới hạn concurrency

~~~java
Flux<OrderWithCustomer> data =
    orderRepository.findByTenantId(tenantId)
        .flatMap(
            order -> customerRepository
                .findByIdAndTenantId(order.customerId(), tenantId)
                .map(customer -> toDto(order, customer)),
            8
        );
~~~

Ví dụ giả định có method **findByTenantId(String)** và hàm toDto đã được định nghĩa. Giá trị concurrency=8 là giới hạn minh họa, cần đo theo pool connections, tải thực tế và database capacity.

**Đây chưa phải giải pháp bỏ N+1**, chỉ giới hạn số truy vấn chạy cùng lúc và ngăn truy vấn xuyên tenant.

### 14.2. flatMap và concatMap

| Operator | Đặc điểm |
| --- | --- |
| flatMap | Có thể subscribe nhiều inner Publishers, kết quả có thể không giữ thứ tự đầu vào |
| concatMap | Thực thi các inner Publishers tuần tự, giữ thứ tự, throughput có thể thấp hơn |
| flatMapSequential | Có thể chạy nhiều inner Publishers đồng thời và phát theo thứ tự đầu vào, nhưng cần buffer để phục hồi thứ tự |

Không nên chọn operator chỉ theo “cái nào nhanh hơn”. Xác định yêu cầu thứ tự, concurrency và memory, rồi benchmark.

### 14.3. Batching ở mức trang

Một cách tốt hơn cho API phân trang:

1. Tải một **trang Order hữu hạn** theo tenant.
2. Thu các customerIds cần cho trang.
3. Query customers bằng **$in** và cùng tenant.
4. Tạo map Customer theo ID.
5. Ghép DTO theo thứ tự Order đã sort.

Nếu trang chỉ có 20–50 Order, việc materialize **một trang nhỏ** thường chấp nhận được và giảm số lần round trip. Không gom tất cả order lịch sử thành một List vô hạn chỉ để tối ưu N+1.

### 14.4. Cache customer theo ID?

Cache có thể giảm truy vấn lặp, nhưng phải có key **tenantId + customerId**, TTL/invalidation và chính sách quyền. Không dùng cache toàn cục chỉ theo customerId khi cùng ID/business key có thể liên quan nhiều tenant hoặc chính sách truy cập khác nhau.

## 15. Khi nào $lookup tốt hơn nhiều query client-side?

**$lookup** là aggregation stage của MongoDB Server để nối dữ liệu từ collection liên quan. Nó không cần Java converter tự resolve DBRef.

Yêu cầu: đọc Order theo ID + tenant, kèm Customer thuộc cùng tenant.

~~~javascript
db.orders.aggregate([
  {
    $match: {
      _id: ObjectId("507f1f77bcf86cd799439031"),
      tenantId: "shop-a"
    }
  },
  {
    $lookup: {
      from: "customers",
      let: {
        cid: "$customerId",
        owner: "$tenantId"
      },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$_id", "$$cid"] },
                { $eq: ["$tenantId", "$$owner"] }
              ]
            }
          }
        },
        {
          $project: {
            displayName: 1
          }
        }
      ],
      as: "customerRows"
    }
  },
  {
    $unwind: {
      path: "$customerRows",
      preserveNullAndEmptyArrays: false
    }
  },
  {
    $project: {
      _id: 1,
      status: 1,
      customerName: "$customerRows.displayName"
    }
  }
]);
~~~

### 15.1. Vì sao lookup có điều kiện tenant?

Nếu chỉ dùng customerId, một Order có pointer sai tới Customer khác tenant có thể khiến API tiết lộ dữ liệu. Pipeline trên ràng buộc:

\[
\text{customers.\_id}=\text{orders.customerId}
\quad \land \quad
\text{customers.tenantId}=\text{orders.tenantId}.
\]

**$lookup không tự thực thi authorization.** Phải áp tenant filter ở root collection và target side.

### 15.2. preserveNullAndEmptyArrays=false

Khi không tìm thấy Customer, $unwind với tùy chọn trên làm Order không xuất hiện trong kết quả. Đây là **inner join semantics**. Nếu API cần trả Order dù Customer thiếu, dùng cách preserve phù hợp và xử lý null trong DTO.

### 15.3. $lookup khác lazy loading

Đây là **một aggregation command** với các stage ở MongoDB Server. Java reactive client nhận kết quả qua Publisher, không cần property lazy proxy giải reference.

Chi phí server-side join vẫn có thể lớn. Đo **executionStats**, số root documents, chỉ mục target, memory và độ trễ trước khi đổi từ hai query sang $lookup.

## 16. $lookup với ReactiveMongoTemplate

Một cách viết dễ kiểm soát là dùng **AggregationOperation** tạo BSON stage, rồi truyền vào ReactiveMongoTemplate.aggregate.

~~~java
import java.util.List;
import org.bson.Document;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationOperation;
import reactor.core.publisher.Mono;

public Mono<Document> readOrderCustomer(
        ReactiveMongoTemplate template,
        ObjectId orderId,
        String tenantId) {

    AggregationOperation match = ctx ->
        new Document("$match",
            new Document("_id", orderId)
                .append("tenantId", tenantId));

    Document customerMatch = new Document("$expr",
        new Document("$and", List.of(
            new Document("$eq", List.of("$_id", "$$cid")),
            new Document("$eq", List.of("$tenantId", "$$owner"))
        )));

    AggregationOperation lookup = ctx ->
        new Document("$lookup",
            new Document("from", "customers")
                .append("let",
                    new Document("cid", "$customerId")
                        .append("owner", "$tenantId"))
                .append("pipeline", List.of(
                    new Document("$match", customerMatch),
                    new Document("$project",
                        new Document("displayName", 1))
                ))
                .append("as", "customerRows"));

    AggregationOperation unwind = ctx ->
        new Document("$unwind",
            new Document("path", "$customerRows")
                .append("preserveNullAndEmptyArrays", false));

    AggregationOperation project = ctx ->
        new Document("$project",
            new Document("_id", 1)
                .append("status", 1)
                .append("customerName",
                    "$customerRows.displayName"));

    Aggregation pipeline = Aggregation.newAggregation(
        match, lookup, unwind, project);

    return template.aggregate(
        pipeline, "orders", Document.class
    ).next();
}
~~~

**Chú ý:** raw Document dùng đúng **tên BSON thực**, không nhất thiết được ánh xạ từ Java @Field như các builder dùng metadata entity. Ví dụ này giả định collection dùng tenantId, customerId và displayName theo tên BSON đã minh họa.

### 16.1. Không tin mọi lookup đều được index tối ưu

Một lookup có **$expr** và **let** có các quy tắc sử dụng index theo phiên bản MongoDB, toán tử so sánh và hình dạng dữ liệu. Đừng khẳng định mọi lookup qua $expr sẽ có hiệu năng giống truy vấn find theo _id; phải chạy explain với data thực.

### 16.2. Thứ tự productIds sau lookup

Nếu lookup một mảng productIds, kết quả join **không mặc nhiên giữ thứ tự ID gốc**. Muốn giữ thứ tự, cần xử lý bằng array operators trong pipeline hoặc khôi phục tại service bằng map ID → Product giống phần 12.

### 16.3. Một lookup không thay transaction

Một aggregation $lookup giúp đọc dữ liệu kết hợp; nó không tự tạo một transaction nhiều document cho các thao tác ghi khác. Cần quy định read concern/snapshot nếu API phải đọc nhất quán tại một thời điểm.

## 17. Chọn giữa hai query và $lookup

| Tiêu chí | Service flatMap / batch lookup | Server-side $lookup |
| --- | --- | --- |
| Khả năng điều khiển logic Java | Cao, dễ thêm rule và fallback | Logic join/filter nằm trong pipeline |
| Số round trips | Có thể 2 hoặc hơn; có thể batch | Thường một aggregation command, có thể nhiều batch |
| Mapping | Explicit Java DTO | Aggregation projection/DTO |
| Tenant policy | Filter từng query | Filter root và lookup pipeline |
| N+1 | Có nếu viết từng ID; batch có thể giảm | Tránh nhiều query từ client, nhưng server vẫn có chi phí join |
| Sort/reference order | Tự khôi phục | Cần thiết kế $sort/$map/array operators |
| Query plan | Dễ đo riêng từng query | Cần quan sát pipeline explain |
| Phù hợp | Một số ít references, business rules tường minh | Read-model/report cần dữ liệu liên kết nhiều |

Không phải “$lookup luôn nhanh hơn hai query”. Nếu Customer được cache, lookup phức tạp có thể đắt hơn. Nếu API chỉ cần Customer name và Order, một pipeline gọn có thể phù hợp hơn nhiều round trips.

## 18. Chủ động tránh I/O blocking trong converter và callback

Một phản ứng phổ biến trước DBRef không hỗ trợ là tạo **@ReadingConverter** hoặc entity callback rồi tự gọi blocking repository để nạp reference:

~~~java
// Phản ví dụ: không làm MongoDB I/O blocking trong converter.
public OrderDocument convert(Document raw) {
    OrderDocument order = ...;
    CustomerDocument customer =
        blockingCustomerRepository.findById(...).orElseThrow();
    return order;
}
~~~

Converter được gọi trong quá trình mapping dữ liệu; nếu nó block, reactive driver vẫn phải đợi converter kết thúc trước khi phát element. Hệ quả:

- Bỏ qua lợi ích I/O non-blocking.
- Có thể block event-loop/driver execution thread.
- Tạo N+1 ẩn mà service không kiểm soát.
- Khó biểu diễn error/cancellation/transaction context.

### 18.1. Converter nên làm gì?

Converter phù hợp cho **biến đổi dữ liệu thuần** như:

- Đổi BSON string code sang enum.
- Đổi một embedded value object.
- Chuẩn hóa một cấu trúc dữ liệu đã có trong document.

**Không nên** dùng converter như repository/service có I/O.

### 18.2. Entity lifecycle callbacks không thay reactive composition

Không tự gọi subscribe() bên trong callback để nạp reference rồi gán vào entity mutable. Subscription phụ có lifecycle và error không gắn với publisher chính, nên consumer có thể nhận entity chưa hoàn chỉnh.

Nếu cần read model kết hợp, xây nó trong service bằng flatMap/zip hoặc aggregation.

## 19. Nhiều tầng quan hệ: tránh chuỗi N+1 lồng nhau

Ví dụ:

~~~text
Order
  -> Customer
      -> DefaultAddress
  -> Products[]
      -> Categories[]
~~~

Nếu mỗi getter quan hệ tự query, một Order có thể kéo theo hàng chục/hàng trăm truy vấn. Reactive không tự làm số round trips này biến mất.

### 19.1. Thiết kế read model cho endpoint

Một endpoint trả chi tiết Order không nhất thiết cần tất cả Category, Supplier, Customer preferences hoặc stock từ mọi kho. Xác định **đúng fields cần cho response** trước khi lập kế hoạch fetch.

Ví dụ:

~~~java
public record OrderDetailView(
    ObjectId orderId,
    String customerName,
    List<ProductSummary> items
) {}
~~~

Thay vì trả nguyên một entity graph như JPA và hy vọng serialization không kích hoạt lazy queries, build DTO chủ động.

### 19.2. Giới hạn số references

Một Order chứa 100.000 productIds là tín hiệu thiết kế cần xem xét:

- Kích thước document BSON.
- Memory cần thiết khi collectList.
- Kích thước truy vấn $in.
- Chi phí join và response.
- Có cần tách order_items thành collection với pagination?

Không dùng List IDs vô hạn rồi tải toàn bộ trong một API WebFlux request.

### 19.3. Không serialize raw entity graph trực tiếp

Trả entity chứa hàng loạt references hoặc mutable fields cho JSON serializer có thể:

- Kích hoạt lazy loading ở blocking stack.
- Trả quá nhiều dữ liệu.
- Vô tình lộ thông tin từ references không được kiểm tra quyền.
- Gây vòng tham chiếu khi object graph có cycle.

DTO explicit là một hàng rào dữ liệu hữu ích trong cả sync và reactive.

## 20. Tính nhất quán và giao dịch khi đọc references

Giả sử Order được đọc trước rồi Product bị xóa ngay trước khi Product query chạy:

~~~text
T0: read Order.productIds = [P1, P2]
T1: service khác xóa P2
T2: query products({_id:{$in:[P1,P2]}}) chỉ trả P1
~~~

Đây không phải lỗi Reactor. **Hai query tách rời không mặc nhiên nằm trong cùng snapshot**.

### 20.1. Khi cần snapshot thực sự

Nếu nghiệp vụ cần consistency mạnh giữa nhiều document:

- Xác định MongoDB topology hỗ trợ transaction.
- Dùng **ReactiveMongoTransactionManager** cho transaction reactive.
- Compose các thao tác trong một reactive chain và kiểm tra read concern/transaction options.
- Giữ transaction ngắn; không giữ nó mở qua HTTP response streaming dài.

Ví dụ cấu hình:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.ReactiveMongoDatabaseFactory;
import org.springframework.data.mongodb.ReactiveMongoTransactionManager;

@Configuration
public class ReactiveTransactionsConfig {

    @Bean("reactiveMongoTransactionManager")
    ReactiveMongoTransactionManager mongoTx(
            ReactiveMongoDatabaseFactory factory) {
        return new ReactiveMongoTransactionManager(factory);
    }
}
~~~

Lúc dùng:

~~~java
@Transactional(
    transactionManager = "reactiveMongoTransactionManager",
    readOnly = true
)
public Mono<OrderDetails> readConsistentOrder(...) {
    // Return một Publisher gồm tất cả query liên quan.
    return ...;
}
~~~

Code này minh họa **transaction boundary**, không phải một implementation đầy đủ. Read-only metadata trong Spring Data MongoDB vẫn có thể dẫn đến một transaction; cần xem read concern và resource cost trên phiên bản sử dụng.

### 20.2. Đừng nhầm session API với @Transactional

Tài liệu Spring Data MongoDB phân biệt:

- **Manual ClientSession** của reactive template (withSession).
- **Transaction management** qua ReactiveMongoTransactionManager gắn Reactor Context.

Tài liệu ghi chú rằng **explicit reactive ClientSession integration được giới hạn ở Template API, không phải một API session thủ công trực tiếp của reactive repositories**. Điều này **không đồng nghĩa** ReactiveMongoRepository hoàn toàn không thể tham gia transaction được quản lý bởi reactive transaction manager.

Không lấy một ví dụ withSession(template) rồi cho rằng repository bên ngoài callback tự nhận session thủ công đó.

### 20.3. Khi snapshot của Order đủ?

Đối với lịch sử giao dịch, lưu customerName, productName hoặc priceAtOrder làm snapshot trong Order có thể phù hợp hơn truy vấn Customer/Product live. Quyết định dựa trên tính đúng đắn nghiệp vụ, không chỉ yêu cầu dùng reactive.

## 21. Những giới hạn và khác biệt API cần nhận diện đúng

Không nên lập một danh sách tùy tiện “mọi thứ reactive thiếu”. Nhiều tính năng đã có API reactive với tên hoặc return type khác. Bảng sau phân loại những điểm liên quan trực tiếp đến bài học.

| Tính năng / mô hình | Blocking API | Reactive API / giới hạn |
| --- | --- | --- |
| @DBRef tự đọc document đích | Mapping DBRef và lazy proxy theo điều kiện | **Không có DBRef join resolution tương đương** |
| @DocumentReference tự đọc document đích | Mapping reference dựa trên pointer/lookup | **Không hỗ trợ đọc document reference bằng reactive infrastructure** trong tài liệu hiện hành |
| Pointer ID thuần | Đọc ID rồi fetch thủ công | **Hỗ trợ**; dùng Mono/Flux và query tường minh |
| $lookup aggregation | MongoTemplate.aggregate | **Hỗ trợ** qua ReactiveMongoTemplate.aggregate |
| Java Stream từ cursor blocking | Stream<T>, cần close | Thường dùng **Flux<T>** với subscription/cancellation |
| Page<T> tự động từ reactive repository query | Repository đồng bộ có thể trả Page | **Không hỗ trợ Mono<Page<T>>** như kiểu trả về repository reactive |
| Pageable cho truy vấn find | Hỗ trợ | **Vẫn hỗ trợ như tham số** giới hạn sort/skip/limit, kết quả thường là Flux |
| GeoPage / GeoResults | Có kiểu kết quả aggregate geo riêng trong sync use case | Không coi các kiểu tập kết quả tính sẵn như GeoPage là reactive stream; kiểm tra API của phiên bản |
| Explicit ClientSession withSession | MongoTemplate API | ReactiveMongoTemplate API; **không có cùng kiểu manual session integration trên reactive repositories** |
| Managed transactions | MongoTransactionManager | **ReactiveMongoTransactionManager** có hỗ trợ |
| Querydsl predicates | QuerydslPredicateExecutor | **ReactiveQuerydslPredicateExecutor có hỗ trợ ở các phiên bản hiện hành** |
| GridFS | GridFsTemplate | **ReactiveGridFsTemplate** có hỗ trợ |
| Bulk updates | BulkOperations | **ReactiveBulkOperations** có hỗ trợ ở các phiên bản phù hợp |
| Change streams / tailable cursors | API đồng bộ hoặc các tích hợp phù hợp | Reactive APIs có hỗ trợ; không phải sync-only |
| Repository AOT optimizations | Một số query methods được AOT hỗ trợ | Tài liệu Spring Data về repository AOT nêu **reactive repository interfaces chưa được AOT repository optimizations hỗ trợ** ở thế hệ tài liệu tương ứng |

### 21.1. Vì sao phải ghi phiên bản?

Một tài liệu Spring Data MongoDB cũ có thể nói reactive Querydsl chưa hỗ trợ, trong khi tài liệu hiện hành có **ReactiveQuerydslPredicateExecutor**. Tương tự, API bulk, sessions, AOT và đặc biệt các overload có thể thay đổi.

Khi viết quyết định kiến trúc:

1. Ghi Spring Boot version.
2. Ghi Spring Data MongoDB version thực tế.
3. Ghi MongoDB Reactive Streams Driver và MongoDB Server versions.
4. Đọc API reference đúng phiên bản.
5. Viết integration test chứng minh tính năng mà service đang dựa vào.

**Không dùng một bài viết nhiều năm tuổi để kết luận tuyệt đối về release hiện tại.**

### 21.2. Phân biệt “không hỗ trợ” và “không nên làm”

- **Không hỗ trợ**: chức năng automatic document-reference reading trong reactive mapping không có contract tương ứng ở tài liệu đã nêu.
- **Có API khác**: ReactiveMongoTemplate.aggregate thay MongoTemplate.aggregate; Flux thay Stream.
- **Không nên làm**: gọi blocking repository trong event loop, dù vẫn có thể compile.
- **Chỉ có điều kiện**: tính năng AOT, session integration, transaction propagation hoặc index APIs phụ thuộc version/infrastructure.

Đây là những loại ràng buộc khác nhau, không gom tất cả thành “ReactiveMongoDB không làm được”.

## 22. Page, Slice, Flux và kiểu trả về kết quả

Blocking repository có thể cung cấp:

~~~java
Page<OrderDocument> findByTenantId(
    String tenantId, Pageable pageable);
~~~

Reactive repository không hỗ trợ trực tiếp **Mono<Page<OrderDocument>>** để tự trả đồng thời content + total như kiểu Page ở imperative repository.

Thay vào đó:

~~~java
Flux<OrderDocument> findByTenantId(
    String tenantId, Pageable pageable);
~~~

Tham số Pageable vẫn giúp gửi sort/skip/limit phù hợp xuống MongoDB, nhưng publisher trả về là Flux các document trong phạm vi đó.

### 22.1. Nếu API thật sự cần total?

Thiết kế hai truy vấn rõ ràng:

~~~java
Mono<List<OrderDocument>> content = orderRepository
    .findByTenantId(tenantId, pageable)
    .collectList();

Mono<Long> total =
    orderRepository.countByTenantId(tenantId);

return Mono.zip(content, total)
    .map(tuple -> new PageResponse<>(
        tuple.getT1(),
        tuple.getT2(),
        pageable.getPageNumber(),
        pageable.getPageSize()
    ));
~~~

PageResponse là DTO do ứng dụng định nghĩa, còn **countByTenantId** là method derived repository cần khai báo. Cách này tốn thêm một query count; hai query không tự cùng snapshot.

### 22.2. Khi không cần total chính xác

Trả một **Slice-like response** hoặc cursor/keyset continuation token có thể tiết kiệm hơn việc count toàn collection. Một cách phổ biến là lấy tối đa **pageSize+1** kết quả để biết còn trang sau hay không, nhưng cần viết query/limit rõ ràng.

Đừng giả định gọi collectList trên mọi Flux có nghĩa tự nhiên đã tạo một Page đúng.

### 22.3. GeoPage và GeoResults

Một số kiểu kết quả blocking như **GeoPage** hoặc **GeoResults** tính sẵn tổng hợp/average, không có cùng hợp đồng reactive streaming. Reactive geo query thường làm việc với từng **GeoResult<T>** trong Flux hoặc DTO khác, tùy API/version.

Không suy ra rằng **reactive không hỗ trợ geospatial query**. Hạn chế nằm ở một số kiểu **aggregate result container** và cách kết quả deferred được biểu diễn.

## 23. Querydsl, GridFS, Bulk: đừng gọi nhầm là sync-only

Các tính năng sau có ví dụ reactive trong Spring Data hiện hành:

### 23.1. Reactive Querydsl

~~~java
import org.springframework.data.querydsl.ReactiveQuerydslPredicateExecutor;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;

interface ReactiveProductSearchRepository
        extends ReactiveMongoRepository<ProductDocument, ObjectId>,
                ReactiveQuerydslPredicateExecutor<ProductDocument> {
}
~~~

Với Q-type được tạo bằng annotation processor tương thích:

~~~java
QProductDocument product = QProductDocument.productDocument;

Flux<ProductDocument> rows =
    repository.findAll(
        product.sku.startsWith("BOOK")
    );
~~~

QProductDocument là generated type minh họa; tên chính xác phụ thuộc package/class/annotation processor. **Reactive Querydsl chỉ giải quyết predicate có kiểu**, không cung cấp join bằng DBRef trong reactive mapping.

### 23.2. Reactive GridFS

Spring Data có **ReactiveGridFsTemplate** cho nhiều thao tác lưu/đọc file từ MongoDB GridFS. Nó sử dụng Publisher, khác với GridFsTemplate đồng bộ.

Điều này không đồng nghĩa mọi helper synchronous trên GridFsTemplate có cùng overload reactive. Kiểm tra API trước khi dùng.

### 23.3. Reactive bulk operations

~~~java
import org.springframework.data.mongodb.core.BulkOperations;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

Mono<?> result = reactiveTemplate
    .bulkOps(
        BulkOperations.BulkMode.ORDERED,
        ProductDocument.class
    )
    .updateOne(
        Query.query(Criteria.where("sku").is("BOOK-101")),
        new Update().set("active", false)
    )
    .execute();
~~~

**ReactiveBulkOperations** có trong các phiên bản phù hợp; một số bulk operations không gọi từng callback/version như save trên entity. Không gộp semantics bulk với repository.save hoặc single-document optimistic locking.

### 23.4. Change streams và tailable cursors

Reactive MongoDB có thể cung cấp Flux cho các luồng thay đổi hoặc tailable query khi server/topology hỗ trợ. Đó là những publisher có thể kéo dài vô hạn, không phải dấu hiệu chúng phải được chuyển thành List.

**Không dùng collectList() trên một publisher vô hạn** để mong nhận được kết quả sau cùng.

## 24. Mixing sync và reactive: ranh giới kỹ thuật

Một ứng dụng có thể đồng thời chứa hai starter và hai MongoDB clients. Nhưng **MongoTemplate** và **ReactiveMongoTemplate** không tự chia sẻ cùng session/transaction context chỉ vì kết nối đến cùng URI.

~~~java
// Phản ví dụ: blocking MongoRepository trong reactive handler.
public Mono<OrderDetails> load(ObjectId id) {
    OrderDocument order = blockingOrderRepository
        .findById(id).orElseThrow();

    return Mono.just(convert(order));
}
~~~

Lời gọi blocking repository xảy ra **trước khi Mono được trả về**, có thể chạy ngay trên HTTP event loop và tạo latency không kiểm soát.

### 24.1. Nếu bắt buộc dùng một API đồng bộ legacy

Trong giai đoạn chuyển đổi, có thể cô lập blocking I/O ở scheduler phù hợp:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public Mono<LegacyResult> callLegacy(ObjectId id) {
    return Mono.fromCallable(() ->
            legacyBlockingService.load(id)
        )
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

**boundedElastic không biến MongoDB call thành non-blocking**. Nó chỉ chuyển blocking work khỏi event loop sang một pool có giới hạn, vẫn tiêu tốn thread và connection. Đây là **biện pháp chuyển tiếp**, không phải cách giải tham chiếu @DBRef reactive.

### 24.2. Không giữ transaction context qua hai driver

Nếu có một method reactive @Transactional và bên trong gọi MongoTemplate đồng bộ qua boundedElastic, thao tác đồng bộ **không tự tham gia** ReactiveMongoTransactionManager. Cần thiết kế ranh giới nhất quán riêng hoặc chuyển các thao tác cần cùng commit sang một stack phù hợp.

### 24.3. ThreadLocal không phải Reactor Context

Trong imperative transaction, session có thể được gắn vào thread. Trong reactive transaction, context đi theo Publisher/Subscriber. Không đọc một ThreadLocal do filter HTTP đồng bộ tạo rồi giả định nó sẽ luôn hiện diện ở mọi stage sau publishOn/subscribeOn.

### 24.4. Không làm việc nặng trong map

~~~java
return products.findAll()
    .map(product ->
        blockingPricingService.calculate(product));
~~~

Nếu calculate thực hiện blocking I/O, nó có thể cản event loop. Có thể thay bằng pricing API reactive được compose với flatMap, hoặc cô lập đúng executor nếu chưa thể migrate.

## 25. Migration từ @DBRef sang ID trong reactive architecture

Một collection legacy có thể đang lưu DBRef:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439031"),
  customer: {
    $ref: "customers",
    $id: ObjectId("507f1f77bcf86cd799439011")
  }
}
~~~

Mục tiêu mới:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439031"),
  customerId: ObjectId("507f1f77bcf86cd799439011")
}
~~~

**Không đổi annotation trong Java rồi mặc định BSON cũ tự chuyển format.** Đó là hai kiểu dữ liệu lưu trữ khác nhau, cần kế hoạch migration.

### 25.1. Quy trình migration đề xuất

1. **Kiểm kê schema thực:** đọc mẫu BSON legacy và danh sách nơi dùng @DBRef/@DocumentReference.
2. **Thống nhất ID types:** ObjectId, String, UUID, custom key; tránh conversion mập mờ.
3. **Thêm field mới** như customerId/productIds trong entity/schema.
4. **Backfill theo lô** từ DBRef.$id hoặc pointer cũ sang ID field tương ứng.
5. **Kiểm tra dữ liệu thiếu/mồ côi**: reference trỏ tới document không tồn tại, sai tenant hoặc collection khác.
6. **Dual read có kiểm soát** trong giai đoạn chuyển đổi nếu cần tương thích.
7. **Đổi write path** sang ID thuần (hoặc dual write ngắn hạn khi có chiến lược nhất quán).
8. **Đổi read path** sang reactive explicit fetch/$lookup.
9. **So sánh kết quả** giữa endpoint blocking cũ và reactive mới trên dữ liệu thử.
10. **Cắt sang schema mới**, bỏ phụ thuộc DBRef sau khi có kế hoạch rollback và kiểm tra đủ.

### 25.2. Backfill một DBRef thành ObjectId

Nếu field DBRef thực sự lưu theo cấu trúc cố định, ý tưởng migration bằng mongosh:

~~~javascript
db.orders.updateMany(
  {
    customerId: { $exists: false },
    customer: { $type: "object" }
  },
  [
    {
      $set: {
        customerId: {
          $getField: {
            field: { $literal: "$id" },
            input: "$customer"
          }
        }
      }
    }
  ]
);
~~~

**Đây là ý tưởng trên dữ liệu mẫu, không phải script production để chạy ngay.** Biểu thức $getField trong ví dụ yêu cầu MongoDB Server hỗ trợ (MongoDB 5.0 trở lên), dùng $literal vì tên field DBRef **$id** bắt đầu bằng dấu $. Điều kiện customer là object chưa chứng minh object đó đúng định dạng DBRef: phải kiểm tra dữ liệu trước, lọc rõ các bản ghi có $id BSON hợp lệ, chạy trên bản sao dữ liệu và giải quyết trường hợp thiếu/sai kiểu trước khi rollout. Dynamic document references có thể lưu pointer theo format hoàn toàn khác.

### 25.3. Nếu @DocumentReference lưu ObjectId ngay trong field?

Khi BSON cũ là:

~~~javascript
{ customer: ObjectId("507f1f77bcf86cd799439011") }
~~~

thì có thể chỉ cần chuyển tên field/customer pointer khi schema yêu cầu. Tuy nhiên, các custom lookup/document pointers có thể là **Document phức tạp**, không được coi tất cả đều là ObjectId mặc định.

### 25.4. Migrate không được làm mất tenant

Khi backfill, không kết luận một ID đang tồn tại là đủ an toàn. Phải xác minh Customer được tham chiếu **đúng tenant** hoặc đáp ứng policy chia sẻ cross-tenant. Nếu dữ liệu legacy cho phép cross-tenant references, cần phân loại trước khi cấp API reactive mới.

## 26. Kiểm thử tích hợp: explicit references hoạt động với ReactiveMongoRepository

Một integration test nên chứng minh:

- Order được lưu với customerId, không cần @DBRef.
- Service đọc Order rồi đọc Customer bằng reactive repository.
- Mọi truy vấn theo tenant phù hợp.
- Publisher hoàn tất và trả DTO mong muốn.

### 26.1. Ví dụ @DataMongoTest và StepVerifier

~~~java
package com.example.reactiveorders;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.UUID;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@DataMongoTest
class ReactiveReferenceIntegrationTest {

    @Autowired ReactiveMongoTemplate template;
    @Autowired ReactiveOrderRepository orders;
    @Autowired ReactiveCustomerRepository customers;

    @Test
    void loadsCustomerExplicitlyByIdAndTenant() {
        String tenant = "TEST-" + UUID.randomUUID();
        ObjectId customerId = new ObjectId();
        ObjectId orderId = new ObjectId();

        CustomerDocument customer = new CustomerDocument(
            customerId, tenant, "Customer A", true
        );

        OrderDocument order = new OrderDocument(
            orderId,
            tenant,
            customerId,
            List.of(),
            "PAID"
        );

        Mono<OrderWithCustomer> scenario = template
            .insert(customer)
            .then(template.insert(order))
            .then(orders.findByIdAndTenantId(orderId, tenant))
            .flatMap(savedOrder ->
                customers.findByIdAndTenantId(
                        savedOrder.customerId(), tenant)
                    .map(savedCustomer ->
                        new OrderWithCustomer(
                            savedOrder.id(),
                            savedOrder.status(),
                            new CustomerSummary(
                                savedCustomer.id(),
                                savedCustomer.displayName()
                            )
                        )
                    )
            );

        StepVerifier.create(scenario)
            .assertNext(view -> {
                assertThat(view.id()).isEqualTo(orderId);
                assertThat(view.status()).isEqualTo("PAID");
                assertThat(view.customer().id())
                    .isEqualTo(customerId);
                assertThat(view.customer().displayName())
                    .isEqualTo("Customer A");
            })
            .verifyComplete();
    }
}
~~~

Ví dụ giả định **Spring Boot test slice có reactive Mongo infrastructure**, dependency reactor-test/JUnit/AssertJ và một MongoDB test instance riêng. Với Spring Boot version cụ thể, kiểm tra package của @DataMongoTest và cấu hình scanning phù hợp.

### 26.2. Tại sao không cần @DBRef?

Customer được tìm qua:

~~~java
customers.findByIdAndTenantId(
    savedOrder.customerId(), tenant
);
~~~

Đây là một MongoDB query được mô tả bằng Publisher; mapping layer không phải tự resolve reference. Test xác nhận DTO đúng nhờ explicit fetch.

### 26.3. Dọn dữ liệu test

Test nên dùng database test riêng hoặc tạo tenant/ID ngẫu nhiên, dọn fixture bằng **ReactiveMongoTemplate.remove** sau mỗi case. Nếu dùng StepVerifier cho setup và cleanup, nhớ rằng không subscribe thì lệnh remove cũng chưa chạy.

**Không chạy ví dụ test này trên production database.** Để tránh ảnh hưởng test song song, có thể dùng một database riêng cho mỗi suite hoặc một Testcontainers MongoDB instance.

### 26.4. Định lượng truy vấn

Với một Order và một Customer, service có thể thực hiện hai lần tìm. Để chứng minh không có N+1 khi tải 100 Order, instrument số command MongoDB bằng command monitoring/metrics và so sánh:

- Từng Order → một Customer query: số query tăng theo N.
- Một trang Order → một batch Customer query: số query phụ ít hơn rõ.
- Một $lookup aggregation: query shape khác, chi phí join chuyển sang server.

Không khẳng định có cải thiện chỉ từ việc đổi List thành Flux.

## 27. Kiểm thử thiếu reference, sai tenant và thứ tự productIds

Một case đọc thành công là chưa đủ. Reference resolution cần kiểm thử các tình huống lỗi dữ liệu và quyền truy cập.

### 27.1. Customer thuộc tenant khác

Seed:

~~~text
Order: tenantId=shop-a, customerId=C1
Customer C1: tenantId=shop-b
~~~

Lệnh:

~~~java
customers.findByIdAndTenantId(C1, "shop-a")
~~~

phải hoàn thành **rỗng**. Service không được lấy Customer thuộc shop-b rồi trả cho người dùng shop-a.

Test dạng StepVerifier:

~~~java
StepVerifier.create(
    customers.findByIdAndTenantId(
        customerIdFromAnotherTenant, "shop-a")
)
.verifyComplete();
~~~

Khi dùng service có switchIfEmpty(Mono.error(...)), hãy assert **business error**, không khẳng định kết quả của service phải rỗng.

### 27.2. Customer bị xóa

Seed Order có customerId nhưng không tạo Customer tương ứng. Xác nhận:

- Repository query trả Mono.empty().
- Service thực hiện **missing-reference policy** đã chọn.
- Không ném NullPointerException không kiểm soát.
- Không tự tạo Customer thay thế ngoài quy tắc nghiệp vụ.

### 27.3. ID sai BSON type

Một Order giữ customerId là String trong legacy data nhưng customers._id là ObjectId. Query có thể không match do type mismatch. Test cần đọc raw BSON để phân biệt lỗi mapping với data không tồn tại.

### 27.4. Thứ tự nhiều sản phẩm

Order.productIds = [P3, P1, P2], nhưng MongoDB query $in có thể trả [P1, P2, P3]. Sau khi ghép DTO phải có:

~~~text
DTO.products = [P3, P1, P2]
~~~

Test nên cố tình seed IDs và thứ tự khác nhau để phát hiện bug, không chỉ dùng một product.

### 27.5. Trùng productId

Order.productIds = [P1, P1] có thể đại diện hai dòng dùng cùng product. Phải xác nhận DTO có giữ hai vị trí nếu hợp đồng yêu cầu, không vô tình loại duplicate khi biến danh sách ID thành Set.

### 27.6. Cancel và error

Với một Flux load nhiều ID, cần test:

- Client cancel sau một số phần tử.
- MongoDB query báo lỗi.
- Missing reference ở giữa một batch.
- Concurrency giới hạn vẫn hoạt động.
- Không có subscribe() phụ làm query tiếp tục không kiểm soát sau cancel.

**StepVerifier kiểm chứng signal của Reactor**, còn khẳng định đã đóng tất cả server cursors cần thêm driver metrics/command monitoring phù hợp nếu đó là SLA.

## 28. Hiệu năng và observability khi load quan hệ reactive

Với read model chứa references, cần quan sát cả **latency từ MongoDB** và **hành vi Reactor**.

### 28.1. Các chỉ số đáng theo dõi

| Chỉ số | Ý nghĩa |
| --- | --- |
| MongoDB commands/request | Phát hiện N+1 |
| Command latency | Query nào gây chậm |
| Number of documents scanned | Có index phù hợp? |
| Query payload/response size | Có đọc thừa field không |
| Pool wait / connections | Concurrency quá cao hay pool thiếu |
| Reactor subscriptions | Có subscribe hai lần/lặp query không |
| Cancellation/timeout | Client bỏ giữa chừng hay query quá lâu |
| Collected list size | Có gom mảng reference lớn vào RAM không |
| Missing-reference count | Dữ liệu mồ côi, sai ID type hoặc phân quyền |
| $lookup executionStats | Join server có được tối ưu không |

### 28.2. Index cho reference

Với reference theo ObjectId, MongoDB đã có unique index trên _id ở collection thông thường. Tuy nhiên, nếu lookup theo business key như:

~~~javascript
{ tenantId: "shop-a", externalCode: "CUST-001" }
~~~

cần index compound phù hợp, đặc biệt nếu externalCode chỉ unique trong tenant.

### 28.3. Không đánh đổi bảo mật lấy hiệu năng

Đừng bỏ tenant filter chỉ vì findById ngắn hơn hoặc index _id đã có. Nếu muốn dùng _id lookup đơn rồi xác minh tenant trong Java, phải chắc không có bước nào đã log/serialize dữ liệu khác tenant và xem đó là một policy được kiểm thử. Truy vấn trực tiếp có điều kiện tenant thường dễ kiểm soát hơn.

### 28.4. Cache và denormalization

Nếu Customer name xuất hiện trong 1.000 Order, có thể giảm số round trips bằng:

- Cache dữ liệu Customer được phân tách theo tenant.
- Batch lookup ID trong mỗi trang.
- Embedded snapshot trong Order.
- $lookup ở server.

Mỗi giải pháp có chính sách freshness, invalidation và consistency riêng. **Không coi denormalization là đồng bộ dữ liệu tự động**; cập nhật Customer không nhất thiết cập nhật mọi snapshot trong Order.

### 28.5. Giới hạn memory và concurrency

~~~java
return orders.findByTenantId(tenantId)
    .flatMap(order -> loadDetails(order), 8);
~~~

Giới hạn concurrency là một cách tránh tạo quá nhiều inner subscriptions cùng lúc. Nhưng nếu **loadDetails** trả kết quả lớn hoặc giữ một List rất lớn, heap vẫn có thể tăng. Kiểm soát cả số element đầu vào, số reference mỗi order và độ lớn response.

## 29. Bảng chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Reactive entity có @DBRef nhưng không tải Customer | DBRef resolution không được hỗ trợ như blocking stack | Lưu customerId, fetch tường minh |
| Đổi sang @DocumentReference vẫn không đọc target | Reactive infrastructure không tự read document references | Dùng ID/explicit query/$lookup |
| Getter làm request chậm đột ngột | Lazy proxy blocking hoặc I/O ẩn | Tránh proxy, DTO explicit |
| Mono hoàn thành rỗng khi Customer thiếu | flatMap từ Mono.empty() | switchIfEmpty theo policy |
| Một API tạo hàng trăm MongoDB commands | N+1 references | Batch $in, pagination, $lookup |
| Sản phẩm lộn thứ tự | $in không giữ thứ tự ID list | Map ID→entity rồi duyệt danh sách gốc |
| Product thuộc tenant khác lọt response | findById thiếu tenant | Filter tenant cả root và target |
| Query không match dù ID nhìn giống nhau | String và BSON ObjectId khác type | Chuẩn hóa kiểu ID, kiểm tra raw BSON |
| Reactor block() gây treo hoặc lỗi | Blocking trên event loop | Compose flatMap/zip, loại blocking calls |
| Query chạy hai lần | subscribe() thủ công và WebFlux subscribe tiếp | Return một publisher duy nhất |
| Mono.zip không ra DTO | Một nguồn hoàn thành rỗng | Xử lý missing reference trước zip |
| Application bị quá tải | flatMap concurrency quá cao | Giới hạn concurrency, đo pool/latency |
| Heap tăng dù dùng Flux | collectList/sort/buffer trên tập lớn | Giới hạn batch/page, tránh tích lũy |
| $lookup trả nhiều dữ liệu hoặc chậm | Join thiếu filter/index/projection | Explain, tenant filter, giảm root scope |
| @Transactional không chứa các query | Sai manager/context/scope | Dùng ReactiveMongoTransactionManager, compose chain |
| Legacy converter vẫn gọi blocking repo | Blocking I/O ẩn trong mapping | Tách sang service explicit |
| Mono<Page> không hoạt động | Reactive repositories không hỗ trợ Page return | Flux + count riêng/DTO tùy nhu cầu |
| Không tìm thấy Reactive Querydsl | Đọc tài liệu cũ hoặc thiếu dependencies/APT | Xác minh release và ReactiveQuerydslPredicateExecutor |
| Reactive bulk API không có trong project | Spring Data version cũ | Kiểm tra API và nâng cấp có kế hoạch |
| Reactive repository AOT không sinh code | Giới hạn repository AOT theo release | Kiểm tra tài liệu AOT, giữ runtime repository implementation |
| DBRef legacy không chuyển thành ID | Chỉ đổi annotation, chưa migration BSON | Backfill/cutover có test |
| Client cancel mà query vẫn chạy | Subscription riêng/callback không liên kết lifecycle | Tránh subscribe phụ, đo cancellation |

### 29.1. Quy trình điều tra nhanh

1. Đọc BSON gốc của field liên quan: DBRef, pointer ObjectId, String hay embedded?
2. Xác định Java property có **@DBRef/@DocumentReference** hay chỉ là ID.
3. Kiểm tra dùng MongoTemplate hay ReactiveMongoTemplate trên read path.
4. Xác nhận sự hỗ trợ reference theo **Spring Data MongoDB version**.
5. Với reactive, kiểm tra query tường minh có được compose trong Mono/Flux không.
6. Kiểm tra tenant filter và missing-reference policy.
7. Đếm số MongoDB commands mỗi request để phát hiện N+1.
8. Kiểm tra ID type, indexes và explain.
9. Kiểm tra block(), subscribe() thủ công, concurrency và operators giữ buffer.
10. Kiểm thử trên MongoDB test instance bằng StepVerifier và BSON thực.

## 30. Bài tập thực hành

### Bài tập 1: DBRef và reactive

Một Order có:

~~~java
@DBRef(lazy = true)
CustomerDocument customer;
~~~

Chuyển repository thành ReactiveMongoRepository thì có thể mặc định customer tự resolve non-blocking không?

**Đáp án:** Không. Reactive mapping không có DBRef join resolution tương đương blocking. Dùng customerId và truy vấn Customer tường minh.

### Bài tập 2: @DocumentReference

Đổi @DBRef thành @DocumentReference có chắc reactive load thành CustomerDocument thành công?

**Đáp án:** Không. Mặc dù format lưu reference linh hoạt hơn, tài liệu Spring Data không hỗ trợ đọc document references bằng reactive infrastructure.

### Bài tập 3: DBRef và pointer ID

Phân biệt:

~~~javascript
{ customer: { $ref: "customers", $id: ObjectId("507f1f77bcf86cd799439011") } }
{ customerId: ObjectId("507f1f77bcf86cd799439011") }
~~~

**Đáp án:** Dòng đầu dùng DBRef structure, dòng sau là ID pointer thuần do ứng dụng quy định. Reactive service có thể dùng customerId để query Customer explicit.

### Bài tập 4: flatMap

Viết reactive flow đọc Order, lấy customerId rồi đọc Customer:

~~~java
return orders.findByIdAndTenantId(orderId, tenantId)
    .flatMap(order ->
        customers.findByIdAndTenantId(
            order.customerId(), tenantId)
    );
~~~

**Giải thích:** flatMap dùng khi Publisher thứ hai phụ thuộc vào kết quả của Publisher thứ nhất.

### Bài tập 5: Mono.zip

Hai query độc lập theo những ID đã biết. Nên dùng flatMap nối tuần tự hay Mono.zip?

**Đáp án:** Có thể dùng Mono.zip để compose kết quả độc lập. Cần xử lý Mono.empty và quyền tenant cho cả hai nguồn.

### Bài tập 6: lỗi block

~~~java
CustomerDocument customer =
    customers.findById(customerId).block();
~~~

Vì sao không nên dùng trong WebFlux request?

**Đáp án:** Chặn thread chờ I/O, có thể làm nghẽn event loop hoặc vi phạm mô hình Reactor. Trả Mono được compose bằng flatMap.

### Bài tập 7: subscribe ngoài

Service gọi subscribe() để gán customer vào Order rồi return Mono.just(order). Lỗi?

**Đáp án:** Hai lifecycle không đồng bộ; Order có thể được phát trước khi customer load, lỗi/cancel không được liên kết. Dùng map/flatMap trong cùng pipeline.

### Bài tập 8: N+1

Một trang 50 Order, mỗi Order gọi findById(Customer) một lần. Bao nhiêu query phụ có thể xảy ra?

**Đáp án:** Tới 50 query phụ; batch lấy customerIds và query $in có thể giảm round trips nếu phù hợp.

### Bài tập 9: thứ tự ID

Order.productIds=[P3,P1,P2], $in trả [P1,P2,P3]. Có đảm bảo response giữ thứ tự order không?

**Đáp án:** Không. Phải map ID→Product và tái lập theo danh sách gốc hoặc dùng pipeline có thiết kế order tường minh.

### Bài tập 10: missing reference

Order còn customerId nhưng Customer bị xóa. Nên trả response thế nào?

**Đáp án:** Theo API contract: báo thiếu reference, trả marker unavailable, hoặc dùng snapshot. Không để Mono.empty âm thầm biến thành một trạng thái hiểu sai nếu API cần Order.

### Bài tập 11: tenant safety

Order thuộc shop-a nhưng customerId chỉ tới Customer của shop-b. Cách phòng tránh?

**Đáp án:** Filter tenant cả ở Order lẫn Customer; server-side $lookup cũng cần ràng buộc owner trong pipeline.

### Bài tập 12: $lookup

MongoDB reactive không thể join dữ liệu chỉ vì không hỗ trợ DBRef resolution, đúng hay sai?

**Đáp án:** Sai. MongoDB Server có $lookup, ReactiveMongoTemplate gửi aggregation được; giới hạn nằm ở automatic reference mapping.

### Bài tập 13: transaction

flatMap Order query rồi Customer query có tạo snapshot transaction không?

**Đáp án:** Không. Reactor composition không tự mở MongoDB transaction; cần ReactiveMongoTransactionManager/TransactionalOperator và options phù hợp khi thực sự cần.

### Bài tập 14: Page

Reactive repository có thể trả Mono<Page<OrderDocument>> giống MongoRepository không?

**Đáp án:** Không theo contract repository reactive. Dùng Flux với Pageable, và count query/DTO riêng nếu cần total.

### Bài tập 15: Querydsl

Mọi phiên bản ReactiveMongoRepository đều không hỗ trợ Querydsl, đúng không?

**Đáp án:** Không đúng. Spring Data MongoDB hiện hành có ReactiveQuerydslPredicateExecutor. Cần kiểm tra version và annotation processing, nhưng nó không bật DBRef joins.

### Bài tập 16: GridFS và bulk

Có thể khẳng định GridFS và bulk operations là chỉ có ở MongoTemplate đồng bộ không?

**Đáp án:** Không. ReactiveGridFsTemplate và ReactiveBulkOperations có ở các phiên bản phù hợp.

### Bài tập 17: manual ClientSession

ReactiveMongoTemplate.withSession được gọi, sau đó một repository reactive được gọi ngoài callback. Có chắc repository nhận explicit session đã mở không?

**Đáp án:** Không. Tài liệu phân biệt manual session integration ở reactive Template API và managed transaction context. Không suy rằng repository ngoài callback tự nhận explicit ClientSession.

### Bài tập 18: migration

Legacy Order có customer là DBRef, entity mới chỉ có customerId ObjectId. Chỉ deploy entity mới có đủ không?

**Đáp án:** Không. Phải di chuyển BSON, chuẩn hóa ID types, xử lý dangling references, dual read/cutover và kiểm thử.

### Bài tập 19: embedded snapshot

Order cần giữ giá đã thanh toán dù Product.price thay đổi. Nên luôn truy vấn Product giá mới?

**Đáp án:** Không. Lưu **priceAtOrder** trong Order item là lựa chọn đúng về lịch sử giao dịch; reference chỉ dùng khi thật sự cần dữ liệu hiện tại.

### Bài tập 20: AOT

Ứng dụng reactive chạy tốt ở runtime nhưng muốn kích hoạt repository AOT optimizations. Có thể giả định mọi reactive repository đều được hỗ trợ không?

**Đáp án:** Không. Đọc đúng tài liệu AOT của Spring Data version đang dùng; một số thế hệ giới hạn support cho reactive repository interfaces dù runtime reactive repositories vẫn hoạt động.

## 31. Checklist trước khi đưa vào production

- **Schema:** biết chính xác BSON field là DBRef, pointer ID hay embedded chưa?
- **Reactive reference:** không phụ thuộc @DBRef/@DocumentReference auto-read chưa?
- **ID types:** ObjectId/String/UUID của ID và reference có nhất quán chưa?
- **Migration:** legacy references đã được backfill/đối soát chưa?
- **Ownership:** tenant/filter được áp dụng cho cả root và target chưa?
- **Missing:** có chính sách cho reference bị xóa/ẩn/sai tenant chưa?
- **API contract:** cần snapshot lịch sử hay dữ liệu hiện tại?
- **DTO:** không trả entity graph/lazy proxy tùy tiện chưa?
- **Publisher:** không gọi block() hoặc subscribe() trong service chưa?
- **Mapping:** converter/entity callback không thực hiện I/O blocking chưa?
- **N+1:** đã đo số MongoDB commands trên mỗi request chưa?
- **Batch:** truy vấn $in được giới hạn số IDs và khôi phục order chưa?
- **Concurrency:** flatMap có giới hạn phù hợp với database pool chưa?
- **Memory:** collectList/buffer chỉ dùng trên tập hữu hạn đã kiểm soát chưa?
- **$lookup:** root/target tenant filters, projection và indexes đã kiểm tra chưa?
- **Query plan:** explain cho lookup và các find queries đã đo chưa?
- **Page:** không dùng Mono<Page> như một reactive repository contract chưa?
- **Versions:** không dùng tài liệu cũ để phủ nhận ReactiveQuerydsl, GridFS hay bulk chưa?
- **Session:** phân biệt explicit reactive Template session và managed transaction chưa?
- **Consistency:** các read tách rời có cần snapshot/transaction không?
- **AOT:** repository AOT capabilities đúng version đã được kiểm chứng chưa?
- **Cancellation:** không có subscription riêng thoát khỏi lifecycle request chưa?
- **Tests:** đã test missing, cross-tenant, ID type, reference order và N+1 chưa?
- **Observability:** có metrics cho commands, latency, missing links, heap và cancel chưa?
- **Security:** không tiết lộ target document chỉ vì client biết ID chưa?

## 32. Tổng kết

1. **@DBRef** lưu một DBRef BSON và có cơ chế resolution/lazy loading trong blocking mapping stack, không phải ràng buộc foreign key.
2. **@DocumentReference** cho phép pointer linh hoạt hơn, nhưng việc đọc entity đích vẫn phụ thuộc mapping resolver.
3. **Reactive infrastructure không hỗ trợ tự đọc document references** tương tự blocking; DBRef joins cũng không được hỗ trợ theo cách mapping truyền thống.
4. **Lưu ID thuần rồi truy vấn tường minh** là chiến lược phù hợp, dễ kiểm soát và có thể kiểm thử cho reactive.
5. **flatMap** để đọc reference phụ thuộc, **Mono.zip** để kết hợp các query độc lập.
6. **Batch lookup bằng $in** giúp giảm N+1, nhưng phải giữ tenant filter, xử lý missing IDs, duplicate IDs và thứ tự gốc.
7. **ReactiveMongoTemplate.aggregate + $lookup** vẫn có thể join ở MongoDB Server; không đánh đồng giới hạn converter với giới hạn MongoDB.
8. **Converter/callback không nên tự gọi I/O blocking**, cũng không tạo subscription phụ để gán entity reference.
9. **DTO explicit, embedded snapshots và pagination** giúp chọn dữ liệu cần thiết, hạn chế coupling với entity graph.
10. **Reactive Page, manual session integration và repository AOT** có những khác biệt/giới hạn riêng theo API/version.
11. **Không gọi nhầm Querydsl, GridFS, bulk, change streams là sync-only** khi các thế hệ Spring Data hiện hành có API reactive tương ứng.
12. **Managed reactive transaction** dùng ReactiveMongoTransactionManager và Reactor Context, không tự động sinh ra từ một chuỗi flatMap.
13. **Migration DBRef sang ID cần thay đổi BSON và kiểm thử dữ liệu**, không chỉ thay annotation trong Java.
14. **Hiệu năng cần đo bằng round trips, query plan và giới hạn bộ nhớ/concurrency**, không chỉ bởi kiểu trả về Flux.
15. **StepVerifier và MongoDB integration tests** xác minh quyền tenant, missing references, mapping và sự hoàn tất của Publisher.

Hiểu rõ **giới hạn DBRef, document reference và các tính năng chỉ có ở API đồng bộ** giúp ứng dụng **SPRING_DATA_MONGODB** chuyển sang reactive đúng bản chất: mỗi lần truy vấn liên kết được biểu diễn tường minh, có kiểm soát concurrency, bảo mật và consistency, thay vì dựa vào lazy loading ẩn từ mô hình blocking.

### Tài liệu tham khảo

- [Spring Data MongoDB — Using DBRefs and Document References](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/document-references.html) — dạng lưu DBRef, @DocumentReference và giới hạn đọc reactive.
- [Spring Data MongoDB — Spring Data Extensions / Querydsl](https://docs.spring.io/spring-data/mongodb/reference/repositories/core-extensions.html) — ReactiveQuerydslPredicateExecutor và giới hạn DBRef joins.
- [Spring Data MongoDB — MongoDB-specific Query Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html) — reactive repository return types, Pageable và DBRef.
- [Spring Data MongoDB — MongoDB Repositories](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/repositories.html) — MongoRepository vs ReactiveMongoRepository và cấu hình reactive driver.
- [Spring Data MongoDB — Sessions & Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html) — manual ClientSession vs ReactiveMongoTransactionManager.
- [Spring Data MongoDB — GridFS Support](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-gridfs.html) — GridFsTemplate và ReactiveGridFsTemplate.
- [Spring Data MongoDB — Repository AOT](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aot.html) — phạm vi AOT tối ưu repository theo version.
- [Spring Data MongoDB — ReactiveBulkOperations API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/ReactiveBulkOperations.html) — bulk operations reactive.
- [MongoDB Manual — $lookup Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/) — join phía MongoDB Server.
