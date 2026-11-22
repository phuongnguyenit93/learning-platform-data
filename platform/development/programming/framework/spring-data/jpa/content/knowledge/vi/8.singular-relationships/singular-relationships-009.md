# Xử lý tham chiếu không tồn tại và giới hạn tải lười theo nhà cung cấp trong Spring Data JPA

Trong JPA, một thuộc tính quan hệ có thể trỏ đến entity không tồn tại trong database, hoặc có thể là tham chiếu chưa được tải đầy đủ. Hai tình huống này thường bị nhầm lẫn:

- **Tham chiếu không tồn tại:** khóa ngoại có giá trị nhưng không có hàng tương ứng ở bảng được tham chiếu, hoặc ứng dụng yêu cầu một ID không có trong database.
- **Tham chiếu chưa được tải (lazy):** entity đích có thể tồn tại, nhưng JPA provider chỉ giữ proxy/indirection và tải trạng thái khi ứng dụng truy cập thuộc tính.

Hiểu đúng sự khác biệt giúp chọn giữa `findById` và `getReferenceById`, xử lý lỗi đúng thời điểm, tránh `LazyInitializationException` và kiểm soát số câu SQL. Hành vi tải lười còn phụ thuộc provider và cấu hình triển khai, nên cần kiểm thử với đúng Hibernate hoặc EclipseLink mà ứng dụng thực tế sử dụng.

## 1. Phân biệt ID không tồn tại, khóa ngoại null và khóa ngoại bị mồ côi

Giả sử có entity `Order` tham chiếu đến `Customer`:

~~~java
@Entity
@Table(name = "orders")
public class Order {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id")
    private Customer customer;
}
~~~

Có ba trạng thái khác nhau:

1. `customer_id IS NULL`: đơn hàng không có khách hàng. Nếu quan hệ là tùy chọn, thuộc tính `customer` có thể là `null`.
2. `customer_id = 25` và bảng `customers` có ID 25: tham chiếu hợp lệ. Entity có thể được tải ngay hoặc tải lười.
3. `customer_id = 25` nhưng bảng `customers` không có ID 25: đây là khóa ngoại bị mồ côi (broken/orphan reference).

Nếu database có ràng buộc foreign key được bật và dữ liệu được ghi qua các đường đi tuân thủ ràng buộc, trường hợp thứ ba sẽ bị database ngăn chặn. Dữ liệu mồ côi thường xuất hiện khi bảng cũ không có FK, constraint từng bị tắt, dữ liệu được import trực tiếp, hoặc hệ thống khác ghi dữ liệu mà không bảo đảm toàn vẹn tham chiếu.

Không nên dùng từ “không tồn tại” cho cả ba trạng thái. `null` có thể hợp lệ theo nghiệp vụ; khóa ngoại mồ côi là lỗi toàn vẹn dữ liệu; ID người dùng truyền vào không tồn tại là một tình huống cần xử lý ở tầng ứng dụng.

## 2. findById và getReferenceById khác nhau như thế nào?

Spring Data JPA cung cấp hai cách lấy entity theo ID với mục đích khác nhau.

### 2.1. findById — kiểm tra sự tồn tại và lấy dữ liệu

~~~java
Optional<Customer> optional = customerRepository.findById(customerId);

if (optional.isEmpty()) {
    throw new CustomerNotFoundException(customerId);
}

Customer customer = optional.get();
~~~

`findById` trả về `Optional<T>`. Nếu không có bản ghi, kết quả là `Optional.empty()`. Đây là lựa chọn phù hợp khi ID đến từ request hoặc người dùng và ứng dụng phải phản hồi rõ ràng rằng đối tượng không tồn tại.

Ví dụ service:

~~~java
@Service
public class OrderService {

    private final CustomerRepository customers;
    private final OrderRepository orders;

    public OrderService(
            CustomerRepository customers,
            OrderRepository orders) {
        this.customers = customers;
        this.orders = orders;
    }

    @Transactional
    public Long createOrder(Long customerId) {
        Customer customer = customers.findById(customerId)
                .orElseThrow(() ->
                        new CustomerNotFoundException(customerId));

        Order order = new Order(customer);
        return orders.save(order).getId();
    }
}
~~~

Trong ví dụ, service xác minh khách hàng tồn tại trước khi tạo đơn hàng. Nếu đây là API HTTP, exception nghiệp vụ có thể được ánh xạ thành HTTP 404 bằng exception handler.

### 2.2. getReferenceById — lấy tham chiếu mà chưa cần đọc trạng thái

~~~java
Customer customer =
        customerRepository.getReferenceById(customerId);
~~~

`getReferenceById` trả về tham chiếu JPA đến entity có ID đó. Provider có thể trả về proxy hoặc một đối tượng được enhancement mà chưa truy vấn toàn bộ trạng thái entity. Đây là cách hữu ích khi chỉ cần gán quan hệ đến một entity đã biết là tồn tại.

Ví dụ:

~~~java
@Transactional
public Long createOrderUsingReference(Long customerId) {
    Customer customer =
            customers.getReferenceById(customerId);

    Order order = new Order(customer);
    return orders.save(order).getId();
}
~~~

Nếu provider hỗ trợ proxy, ứng dụng có thể tạo đơn hàng bằng ID khách hàng mà không cần tải tên, email hoặc các thuộc tính khác của khách hàng. Tuy nhiên, `getReferenceById` **không phải phương thức kiểm tra ID tồn tại**.

Theo hợp đồng JPA, lỗi khi tham chiếu không tồn tại có thể được phát hiện khi trạng thái của tham chiếu được truy cập. Một số provider có thể từ chối ID không hợp lệ ngay khi tạo tham chiếu. Spring Data JPA cũng ghi rõ thời điểm phát sinh lỗi phụ thuộc provider.

### 2.3. So sánh nhanh

| Tiêu chí | findById(id) | getReferenceById(id) |
|---|---|---|
| Kết quả | `Optional<T>` | Tham chiếu `T` |
| Mục đích | Tra cứu và xử lý trường hợp không tìm thấy | Tham chiếu đến entity được giả định là tồn tại |
| Có thể đọc trạng thái ngay? | Có, entity được tìm thấy sẽ được trả về | Không nhất thiết; có thể là proxy/chưa khởi tạo |
| ID không tồn tại | Trả `Optional.empty()` | Có thể lỗi ngay hoặc khi tham chiếu được khởi tạo |
| Dùng để xác thực ID request? | Phù hợp | Không phù hợp |
| Dùng để gán FK khi đã biết ID hợp lệ? | Có thể, nhưng tải entity | Có thể tránh tải trạng thái entity |

`getReferenceById` có từ Spring Data JPA 2.7. Các API cũ `getOne` và `getById` đã bị deprecated trong các phiên bản Spring Data JPA mới hơn; khi dùng phiên bản có `getReferenceById`, nên ưu tiên tên này.

### 2.4. Không dùng existsById rồi getReferenceById để kiểm tra

Mẫu sau thường không cần thiết:

~~~java
if (!customers.existsById(customerId)) {
    throw new CustomerNotFoundException(customerId);
}

Customer customer = customers.getReferenceById(customerId);
~~~

Nó có thể tạo hai lần truy cập database và vẫn có khoảng thời gian giữa kiểm tra và sử dụng mà dữ liệu có thể thay đổi (race condition). Nếu cần dữ liệu hoặc cần phản hồi 404, dùng `findById` một lần. Nếu chỉ cần tham chiếu và database có FK được bảo đảm, dùng `getReferenceById` rồi để constraint bảo vệ toàn vẹn khi ghi.

## 3. Xử lý tham chiếu không tồn tại đúng cách

### 3.1. Dùng foreign key để bảo vệ dữ liệu

Thiết kế database nên có ràng buộc FK cho quan hệ bắt buộc:

~~~sql
alter table orders
add constraint fk_orders_customer
foreign key (customer_id)
references customers(id);
~~~

Nếu mỗi đơn hàng bắt buộc có khách hàng, cột có thể được khai báo `NOT NULL`:

~~~sql
customer_id bigint not null
~~~

Ràng buộc `NOT NULL` và FK giải quyết hai vấn đề khác nhau:

- `NOT NULL` cấm giá trị khóa ngoại rỗng.
- FK bảo đảm giá trị khóa ngoại trỏ đến một hàng có thật.

Trong entity, có thể biểu diễn:

~~~java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "customer_id", nullable = false)
private Customer customer;
~~~

`optional = false` thể hiện quan hệ không được phép null ở mô hình JPA; `nullable = false` hỗ trợ mô tả cột khi sinh schema. Ràng buộc database thực tế vẫn cần được tạo và duy trì bằng migration. Annotation không tự sửa schema đã tồn tại nếu dự án không dùng cơ chế sinh schema tương ứng.

### 3.2. Kiểm tra ID từ request

Khi người dùng gửi `customerId`, thường cần xác thực trước khi thực hiện nghiệp vụ:

~~~java
@Transactional
public Long createOrder(CreateOrderRequest request) {
    Customer customer = customerRepository.findById(request.customerId())
            .orElseThrow(() ->
                    new CustomerNotFoundException(request.customerId()));

    Order order = new Order(customer);
    return orderRepository.save(order).getId();
}
~~~

Cách này cho phép trả lỗi nghiệp vụ rõ ràng và không phụ thuộc vào thời điểm provider khởi tạo proxy.

Không nên bắt `EntityNotFoundException` để thay thế mọi bước validation. Exception này thường phản ánh một tham chiếu JPA được yêu cầu nhưng không tìm thấy trạng thái tương ứng; nó không phải cách biểu đạt tốt nhất cho mọi lỗi request.

### 3.3. Gán tham chiếu khi ID đã đáng tin cậy

Nếu một ID đến từ quy trình nội bộ đã xác thực hoặc từ một entity đang được quản lý, có thể dùng `getReferenceById` để gán quan hệ:

~~~java
@Transactional
public void assignCustomer(Long orderId, Long customerId) {
    Order order = orderRepository.findById(orderId)
            .orElseThrow(() -> new OrderNotFoundException(orderId));

    Customer customer = customerRepository.getReferenceById(customerId);
    order.setCustomer(customer);
}
~~~

Nếu chỉ gán quan hệ và không đọc thuộc tính khách hàng, Hibernate có thể dùng ID của proxy khi ghi FK. Nếu ID không tồn tại và database có FK, thao tác INSERT/UPDATE sẽ thất bại khi constraint được kiểm tra, thường tại flush hoặc commit. Provider cũng có thể phát hiện sớm hơn nếu tham chiếu được khởi tạo.

Hãy xác định rõ nơi bắt lỗi database và chuyển thành lỗi nghiệp vụ phù hợp. Không coi việc tạo được proxy là bằng chứng rằng ID hợp lệ.

### 3.4. Xử lý dữ liệu legacy có khóa ngoại mồ côi

Nếu hệ thống cũ không có FK và đang chứa các giá trị tham chiếu đến hàng đã bị xóa, ưu tiên:

1. Thống kê và tìm các khóa ngoại không có hàng đích.
2. Xác định quy tắc nghiệp vụ: bỏ liên kết, khôi phục dữ liệu cha hay ánh xạ sang một trạng thái thay thế.
3. Làm sạch dữ liệu.
4. Thêm FK sau khi dữ liệu đã hợp lệ.
5. Giữ kiểm thử tích hợp để ngăn dữ liệu mồ côi tái xuất hiện.

Có thể tìm dữ liệu mồ côi bằng SQL:

~~~sql
select o.id, o.customer_id
from orders o
left join customers c on c.id = o.customer_id
where o.customer_id is not null
  and c.id is null;
~~~

Truy vấn này chỉ là ví dụ cho quan hệ `orders.customer_id`. Hãy điều chỉnh tên bảng, cột và điều kiện theo schema thực tế.

### 3.5. @NotFound của Hibernate cho dữ liệu không có FK

Hibernate có annotation riêng `@NotFound` để xử lý quan hệ mà database không bảo đảm physical foreign key:

~~~java
import org.hibernate.annotations.NotFound;
import org.hibernate.annotations.NotFoundAction;

@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "legacy_customer_id")
@NotFound(action = NotFoundAction.IGNORE)
private Customer customer;
~~~

Hai lựa chọn:

- `NotFoundAction.EXCEPTION` (mặc định): Hibernate báo lỗi khi phát hiện khóa ngoại trỏ đến hàng không tồn tại; Hibernate hiện đại dùng `FetchNotFoundException` cho trường hợp này.
- `NotFoundAction.IGNORE`: Hibernate coi association không hợp lệ như `null`.

Có một hệ quả quan trọng: các quan hệ `@ManyToOne` và `@OneToOne` có `@NotFound` luôn được Hibernate tải eager, kể cả khi annotation quan hệ đặt `fetch = FetchType.LAZY`. Hibernate cần kiểm tra trạng thái tham chiếu để áp dụng chính sách khi hàng đích không tồn tại.

`@NotFound` là tính năng riêng của Hibernate, không phải annotation Jakarta Persistence chuẩn. Không dùng nó như cách thay thế FK trong schema mới. Với `IGNORE`, dữ liệu gốc vẫn chứa khóa ngoại mồ côi; mapping chỉ thay đổi cách ứng dụng nhìn thấy quan hệ.

## 4. Lazy loading hoạt động như thế nào?

Lazy loading trì hoãn việc đọc dữ liệu liên quan cho đến khi ứng dụng cần truy cập. Ví dụ:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "customer_id")
private Customer customer;

@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderLine> lines = new ArrayList<>();
~~~

Khi tải một `Order`, provider có thể chỉ đọc dữ liệu đơn hàng. `customer` và `lines` được đại diện bằng proxy hoặc đối tượng indirection; khi code truy cập quan hệ, provider mới phát truy vấn bổ sung.

### 4.1. Quy tắc của Jakarta Persistence

Với Jakarta Persistence 3.1, các mặc định quan trọng là:

| Mapping | Fetch mặc định |
|---|---|
| `@ManyToOne` | `FetchType.EAGER` |
| `@OneToOne` | `FetchType.EAGER` |
| `@OneToMany` | `FetchType.LAZY` |
| `@ManyToMany` | `FetchType.LAZY` |
| `@ElementCollection` | `FetchType.LAZY` |
| `@Basic` | `FetchType.EAGER` |

`FetchType.EAGER` là yêu cầu đối với provider: dữ liệu phải được tải eager. `FetchType.LAZY` chỉ là gợi ý; provider được phép tải dữ liệu sớm hơn yêu cầu của ứng dụng. Vì vậy, `fetch = FetchType.LAZY` không phải cam kết rằng không có SQL nào chạy trước khi getter được gọi.

Đối với quan hệ ToOne, nên khai báo `LAZY` rõ ràng nếu nghiệp vụ không luôn cần entity liên quan:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;

@OneToOne(fetch = FetchType.LAZY)
private Invoice invoice;
~~~

Sau đó chủ động yêu cầu fetch các quan hệ cần dùng trong từng query. Cách này giảm việc tải dữ liệu không cần thiết do mặc định `EAGER` của ToOne.

### 4.2. LAZY không đồng nghĩa với JOIN

`LAZY` mô tả thời điểm dữ liệu được tải, không quy định provider phải dùng loại SQL nào. Provider có thể:

- Tải entity gốc rồi tải quan hệ bằng SELECT riêng khi proxy được khởi tạo.
- Gom nhiều tham chiếu thành một truy vấn batch.
- Dùng bytecode enhancement hoặc indirection để theo dõi thuộc tính chưa tải.
- Tải eager sớm nếu mapping, query hoặc provider yêu cầu.

Tương tự, `EAGER` không bảo đảm rằng provider sẽ tạo một câu SQL JOIN duy nhất. Một truy vấn trả về nhiều entity có quan hệ eager nhưng không fetch join phù hợp vẫn có thể tạo thêm các SELECT riêng.

Vì vậy, cần quan sát SQL thực tế và thiết kế fetch plan theo use case thay vì suy luận số câu SQL chỉ từ annotation.

## 5. Giới hạn tải lười theo JPA provider

JPA quy định hợp đồng chung, còn cơ chế thực hiện lazy loading phụ thuộc provider. Hai provider phổ biến có cơ chế khác nhau là Hibernate và EclipseLink.

### 5.1. Hibernate

Hibernate thường sử dụng:

- **Proxy cho quan hệ ToOne:** một đối tượng đại diện giữ ID của entity đích; khi truy cập trạng thái chưa tải, proxy được khởi tạo bằng SQL.
- **Persistent collection wrapper cho ToMany:** collection được Hibernate quản lý và có thể tải phần tử khi ứng dụng duyệt hoặc truy cập.
- **Bytecode enhancement:** hỗ trợ lazy attribute loading và một số trường hợp quan hệ cần theo dõi trạng thái thuộc tính chi tiết hơn.

Các giới hạn thực tế:

1. **Entity phải proxy được nếu dùng subclass proxy truyền thống.** Lớp final hoặc phương thức final có thể hạn chế khả năng tạo proxy; bytecode enhancement có cơ chế khác nhưng cần cấu hình build/runtime phù hợp.
2. **Quan hệ One-to-One ở phía inverse có thể khó lazy.** Provider cần xác định có bản ghi phía bên kia hay không để phân biệt null với một proxy; trong một số mapping có thể phải truy vấn sớm. Enhancement và cấu hình mapping ảnh hưởng cách giải quyết.
3. **Truy cập proxy sau khi Session đóng sẽ lỗi.** Hibernate thường ném `LazyInitializationException` khi cần tải dữ liệu mà không còn persistence context.
4. **`@NotFound` làm ToOne eager.** Đây là ngoại lệ quan trọng nếu hệ thống cần xử lý khóa ngoại mồ côi.
5. **N+1 query vẫn có thể xảy ra.** Một truy vấn lấy nhiều đơn hàng, sau đó mỗi lần đọc `order.getCustomer().getName()` có thể tạo thêm một SELECT cho từng khách hàng.

Hibernate có thể giảm N+1 bằng batch fetching. Ví dụ:

~~~java
import org.hibernate.annotations.BatchSize;

@Entity
@BatchSize(size = 32)
public class Customer {
    // entity fields
}
~~~

Hoặc cấu hình chung:

~~~properties
spring.jpa.properties.hibernate.default_batch_fetch_size=32
~~~

Khi nhiều proxy hoặc collection cần được khởi tạo, Hibernate có thể gom các ID thành một truy vấn theo lô. Đây là tính năng riêng của Hibernate; kích thước batch cần được đo bằng workload thực tế, không nên đặt tùy tiện quá lớn.

### 5.2. EclipseLink

EclipseLink dùng cơ chế *indirection* để trì hoãn tải quan hệ. Với collection ToMany, provider có thể dùng transparent indirection để ứng dụng làm việc với collection như bình thường trong khi dữ liệu được tải khi cần.

Đối với quan hệ ToOne (`@OneToOne` và `@ManyToOne`), khả năng lazy loading phụ thuộc weaving:

- **Dynamic weaving:** EclipseLink biến đổi bytecode khi class được nạp. Trong Java SE, thường cần agent hoặc môi trường tích hợp cho phép weaving.
- **Static weaving:** bytecode được xử lý trước khi chạy, hữu ích khi không thể dùng agent lúc khởi động JVM.
- Nếu weaving không được bật hoặc không khả dụng, lazy ToOne có thể không được thực hiện như mong đợi và quan hệ có thể được tải sớm.

EclipseLink có thuộc tính `eclipselink.weaving.lazy` để bật/tắt lazy ToOne weaving; thuộc tính này chỉ có tác dụng khi weaving được cấu hình phù hợp (`true` hoặc `static`).

Ví dụ cấu hình persistence unit:

~~~xml
<property name="eclipselink.weaving" value="true"/>
<property name="eclipselink.weaving.lazy" value="true"/>
~~~

Trong môi trường Java SE, hãy kiểm tra cách chạy thực tế và cấu hình agent/static weaving. Không sao chép cấu hình này sang Hibernate vì đây là thuộc tính riêng của EclipseLink.

### 5.3. So sánh thực tế

| Nội dung | JPA portable | Hibernate | EclipseLink |
|---|---|---|---|
| LAZY có phải cam kết tuyệt đối? | Không, chỉ là hint | Có thể dùng proxy/enhancement nhưng vẫn chịu mapping và fetch plan | Có thể dùng indirection/weaving; phụ thuộc cấu hình |
| Lazy ToOne | Provider có thể tải eager | Thường dùng proxy hoặc enhancement | Java SE cần weaving cho ToOne lazy |
| Lazy ToMany | Mặc định LAZY | Persistent collection wrapper | Transparent indirection |
| Truy cập sau khi persistence context đóng | Không bảo đảm tải được; lỗi tùy provider | Thường là LazyInitializationException | Provider có thể ném lỗi indirection/detached |
| Xử lý FK mồ côi bằng annotation riêng | Không có annotation chuẩn tương đương | `@NotFound`; ToOne bị eager | Cần chiến lược riêng, không dùng Hibernate annotation |
| Batch fetching | Không chuẩn hóa một annotation chung | Có `@BatchSize` và cấu hình batch | Có cơ chế batch/indirection riêng |

Không nên kết luận provider nào “lazy tốt hơn” chỉ từ bảng tính năng. Kết quả phụ thuộc mapping, phiên bản provider, bytecode enhancement/weaving, transaction boundary, database và cách query. Hãy kiểm thử trên chính provider được đóng gói trong ứng dụng.

## 6. Lazy loading và vòng đời persistence context

Một proxy chỉ có thể tải dữ liệu khi provider còn persistence context/session phù hợp. Nếu entity đã detached hoặc EntityManager đã đóng, việc truy cập thuộc tính lazy chưa được khởi tạo có thể thất bại.

Ví dụ dễ gây lỗi:

~~~java
public Order getOrder(Long id) {
    return orderRepository.findById(id).orElseThrow();
}

// EntityManager/transaction đã đóng khi caller chạy:
String customerName = getOrder(10L).getCustomer().getName();
~~~

Trong ví dụ này, service trả entity ra ngoài transaction. Nếu `customer` chưa được tải, caller có thể không còn khả năng khởi tạo proxy.

### 6.1. Tải dữ liệu cần thiết trong transaction

Một cách an toàn là tạo DTO trong service khi transaction còn mở:

~~~java
public record OrderSummary(
        Long id,
        String customerName) {
}

@Service
public class OrderQueryService {

    private final OrderRepository orders;

    public OrderQueryService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional(readOnly = true)
    public OrderSummary getSummary(Long id) {
        Order order = orders.findById(id)
                .orElseThrow(() -> new OrderNotFoundException(id));

        String customerName = order.getCustomer().getName();

        return new OrderSummary(order.getId(), customerName);
    }
}
~~~

Service đọc thuộc tính cần thiết khi persistence context còn mở và trả về dữ liệu đã được chuyển thành DTO. Controller/serializer không phải khởi tạo proxy.

### 6.2. Open Session in View không thay thế fetch plan

Trong ứng dụng web, Open Session in View (OSIV) có thể giữ persistence context mở trong thời gian render response. Điều này đôi khi che giấu việc service trả entity chưa tải đủ dữ liệu.

Nếu serializer truy cập quan hệ lazy, SQL có thể phát sinh trong lúc tạo JSON. Hệ quả là truy vấn database bị ẩn trong tầng trình bày, dễ phát sinh N+1 và khó dự đoán độ trễ.

Có thể chủ động tắt OSIV:

~~~properties
spring.jpa.open-in-view=false
~~~

Khi tắt, service phải tải các thuộc tính cần thiết trong transaction và chuyển thành DTO. Đây là cách giúp ranh giới truy cập dữ liệu rõ ràng hơn. Nếu dự án vẫn bật OSIV, hãy tránh dựa vào nó để tải quan hệ một cách ngẫu nhiên trong serializer.

## 7. Chọn fetch plan theo từng use case

Không cần chuyển mọi quan hệ thành EAGER để tránh lỗi lazy. Hãy giữ mapping hợp lý và chọn dữ liệu cần tải ở query.

### 7.1. EntityGraph

Spring Data JPA hỗ trợ `@EntityGraph` để chỉ định quan hệ cần tải cho một phương thức repository:

~~~java
public interface OrderRepository
        extends JpaRepository<Order, Long> {

    @EntityGraph(attributePaths = "customer")
    Optional<Order> findWithCustomerById(Long id);
}
~~~

Khi gọi phương thức này, query yêu cầu tải cả `customer` cùng đơn hàng. EntityGraph có thể được khai báo trên method hoặc dùng named entity graph ở entity.

EntityGraph giúp fetch plan nằm gần query/use case. Nó không đảm bảo provider phải dùng một kiểu SQL duy nhất; provider có thể chọn cách tải phù hợp với mapping và khả năng của nó.

### 7.2. JOIN FETCH

Với JPQL, có thể yêu cầu fetch join rõ ràng:

~~~java
public interface OrderRepository
        extends JpaRepository<Order, Long> {

    @Query("""
           select o
           from Order o
           left join fetch o.customer
           where o.id = :id
           """)
    Optional<Order> findWithCustomer(@Param("id") Long id);
}
~~~

`LEFT JOIN FETCH` giữ lại đơn hàng ngay cả khi quan hệ khách hàng là tùy chọn và không có giá trị. Nếu quan hệ bắt buộc, có thể dùng `JOIN FETCH`.

Fetch join phù hợp khi query cụ thể cần một quan hệ. Không thêm nhiều collection fetch join một cách máy móc, vì join nhiều collection có thể nhân số hàng kết quả và gây tải dữ liệu quá lớn.

### 7.3. DTO projection

Nếu màn hình chỉ cần một vài trường, projection có thể hiệu quả hơn việc tải cả entity graph:

~~~java
public record OrderRow(
        Long orderId,
        String customerName) {
}

@Query("""
       select new com.example.store.OrderRow(
           o.id,
           c.name
       )
       from Order o
       join o.customer c
       where o.status = :status
       """)
List<OrderRow> findRowsByStatus(
        @Param("status") OrderStatus status);
~~~

Đây là ví dụ DTO projection bằng constructor expression của JPQL. Tên package và constructor phải đúng với DTO thực tế. Kết quả chỉ chứa các cột cần thiết, không phụ thuộc vào việc serializer khởi tạo quan hệ lazy.

### 7.4. Cẩn thận khi phân trang collection fetch join

Fetch join một quan hệ ToOne thường dễ dự đoán hơn fetch join một collection ToMany. Khi kết hợp collection fetch join với `Pageable`, một đơn hàng có nhiều dòng có thể xuất hiện thành nhiều hàng SQL. Điều này làm việc phân trang ở cấp entity gốc trở nên phức tạp.

Các phương án thường dùng:

- Phân trang ID của entity gốc trước, sau đó truy vấn fetch dữ liệu quan hệ cho tập ID đó.
- Dùng DTO projection để chỉ lấy dữ liệu cần thiết.
- Tách query count và query nội dung.
- Kiểm tra log SQL và cảnh báo của Hibernate về việc phân trang collection fetch.

Không nên giả định `Pageable` cộng với một collection fetch join luôn tạo ra phân trang SQL chính xác và hiệu quả.

## 8. N+1 query và cách chẩn đoán

Giả sử một truy vấn tải 50 đơn hàng:

~~~java
List<Order> orders = orderRepository.findAll();

for (Order order : orders) {
    System.out.println(order.getCustomer().getName());
}
~~~

Nếu mỗi `customer` là một proxy riêng chưa được khởi tạo, Hibernate có thể chạy:

- 1 SELECT lấy danh sách đơn hàng.
- Tối đa 50 SELECT để tải khách hàng.

Đó là vấn đề N+1. Số câu SQL thực tế có thể thấp hơn nếu persistence context hoặc cache đã có entity, hoặc provider dùng batch fetching; không nên dựa vào giả định đó khi thiết kế.

Cách xử lý:

1. Dùng EntityGraph hoặc fetch join nếu use case luôn cần khách hàng.
2. Dùng DTO projection nếu chỉ cần ID đơn hàng và tên khách hàng.
3. Với Hibernate, cân nhắc `@BatchSize` hoặc `hibernate.default_batch_fetch_size` khi truy cập nhiều proxy/collection.
4. Dùng `PersistenceUnitUtil.isLoaded(entity, "customer")` để kiểm tra thuộc tính đã được tải hay chưa theo API JPA.
5. Bật SQL logging trong môi trường kiểm thử và đo số query, thời gian thực thi, dữ liệu trả về.

Không nên đổi mọi quan hệ sang EAGER để chữa N+1. EAGER có thể làm các query khác tải thêm dữ liệu hoặc tạo N+1 qua các SELECT phụ.

## 9. Kiểm thử tham chiếu không tồn tại

### 9.1. findById trả về rỗng

Đây là hành vi có thể kiểm thử trực tiếp và ổn định:

~~~java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository customers;

    @Test
    void returnsEmptyWhenCustomerDoesNotExist() {
        assertThat(customers.findById(999999L)).isEmpty();
    }
}
~~~

Database test phải được khởi tạo với trạng thái không có ID được kiểm tra. Nếu test dùng dữ liệu fixture, hãy chọn một ID chắc chắn không tồn tại trong fixture.

### 9.2. Kiểm tra getReference với ID không tồn tại

`EntityManager.getReference` và Spring Data `getReferenceById` có thể trì hoãn việc kiểm tra cho đến khi tham chiếu được khởi tạo. Provider cũng được phép phát hiện lỗi sớm.

Ví dụ minh họa:

~~~java
@Test
void missingReferenceFailsWhenProviderChecksIt() {
    assertThatThrownBy(() -> {
        Customer reference =
                entityManager.getReference(Customer.class, 999999L);

        reference.getName();
    }).isInstanceOf(EntityNotFoundException.class);
}
~~~

Đây là kỳ vọng thường gặp với provider JPA, nhưng thời điểm và loại exception cụ thể cần được kiểm chứng với provider/version của dự án. Nếu dùng Spring repository proxy, exception phát sinh ngay trong lời gọi repository có thể còn đi qua cơ chế dịch exception của Spring. Hãy viết test theo exception contract mà ứng dụng chọn để công khai, thay vì dựa vào một thời điểm khởi tạo proxy duy nhất.

### 9.3. Kiểm thử lazy loading và detached entity

Có thể kiểm tra thuộc tính đã tải bằng API JPA:

~~~java
PersistenceUnitUtil util =
        entityManagerFactory.getPersistenceUnitUtil();

Order order = entityManager.find(Order.class, orderId);

boolean loaded =
        util.isLoaded(order, "customer");
~~~

Kết quả phụ thuộc fetch plan của query và provider. Nếu muốn xác nhận query không tải customer ngay, hãy kiểm tra cả trạng thái loaded lẫn SQL log; một provider được phép tải eager dù mapping yêu cầu LAZY.

Với test sau khi đóng persistence context, cần xác định association chưa được khởi tạo trước khi detach/close. Sau đó truy cập association để quan sát exception của provider. Hibernate thường phát `LazyInitializationException`; không nên giả định mọi provider đều dùng cùng exception class.

## 10. Checklist xử lý trong ứng dụng

- [ ] Phân biệt FK null, FK mồ côi và ID request không tồn tại.
- [ ] Dùng `findById` khi cần xác nhận bản ghi và trả lỗi nghiệp vụ rõ ràng.
- [ ] Dùng `getReferenceById` khi chỉ cần tham chiếu đến ID đã đáng tin cậy.
- [ ] Có physical foreign key cho quan hệ cần bảo đảm toàn vẹn dữ liệu.
- [ ] Không dùng `existsById` rồi `getReferenceById` như một lần kiểm tra kép.
- [ ] Hiểu `FetchType.LAZY` là hint và `FetchType.EAGER` là requirement theo JPA.
- [ ] Kiểm tra provider/version và cấu hình proxy, enhancement hoặc weaving.
- [ ] Không truy cập association chưa tải sau khi persistence context đã đóng.
- [ ] Chọn EntityGraph, fetch join hoặc DTO projection theo use case.
- [ ] Đo SQL để phát hiện N+1 và truy vấn eager ngoài ý muốn.
- [ ] Chỉ dùng `@NotFound` khi thật sự phải hỗ trợ dữ liệu legacy không có FK và chấp nhận hệ quả eager của Hibernate.
- [ ] Có test cho ID không tồn tại, FK hợp lệ, association lazy và truy vấn theo fetch plan.

## 11. Tài liệu tham khảo

- [Jakarta Persistence 3.1 Specification](https://jakarta.ee/specifications/persistence/3.1/jakarta-persistence-spec-3.1.pdf) — định nghĩa `FetchType`, `EntityManager.getReference`, association và vòng đời persistence context.
- [Spring Data JPA — JpaRepository Javadoc](https://docs.spring.io/spring-data/jpa/docs/current/api/org/springframework/data/jpa/repository/JpaRepository.html) — `findById`, `getReferenceById` và các API repository.
- [Hibernate ORM 6.2 User Guide](https://docs.hibernate.org/orm/6.2/userguide/html_single/) — proxy, lazy fetching, `@NotFound` và batch fetching.
- [EclipseLink 4.0 — Understanding EclipseLink](https://eclipse.dev/eclipselink/documentation/4.0/concepts/concepts.html) — indirection và weaving.
- [EclipseLink 4.0 — JPA Extensions Reference](https://eclipse.dev/eclipselink/documentation/4.0/jpa/extensions/jpa-extensions.html) — thuộc tính `eclipselink.weaving.lazy`.

Điểm cốt lõi là xác định rõ ứng dụng cần kiểm tra sự tồn tại hay chỉ cần một tham chiếu, sau đó chọn fetch plan phù hợp với transaction và provider. Dùng FK để bảo vệ toàn vẹn dữ liệu, tải association trong ranh giới service và kiểm thử bằng đúng provider giúp tránh lỗi tham chiếu muộn, lazy loading sau khi detach và N+1 query.
