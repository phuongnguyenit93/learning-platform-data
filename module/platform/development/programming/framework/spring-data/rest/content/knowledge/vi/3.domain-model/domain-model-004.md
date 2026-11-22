# Phân biệt ID lưu trữ, URI tài nguyên và khóa nghiệp vụ

Trong một ứng dụng Spring Data REST, một bản ghi có thể được nhận diện theo nhiều cách. Ví dụ, một đơn hàng có khóa chính trong database là `42`, có mã đơn hàng mà bộ phận kinh doanh sử dụng là `SO-2026-0042`, và được truy cập qua URI `https://api.example.com/api/orders/42`.

Ba giá trị này có thể liên quan với nhau, nhưng chúng phục vụ ba mục đích khác nhau:

- **ID lưu trữ (storage ID)** xác định entity trong persistence store, thường là khóa chính của database.
- **URI tài nguyên (resource URI)** xác định tài nguyên trong hợp đồng HTTP mà client sử dụng.
- **Khóa nghiệp vụ (business key)** xác định một đối tượng theo quy tắc của domain, có ý nghĩa với người dùng hoặc hệ thống nghiệp vụ.

Phân biệt rõ ba khái niệm giúp thiết kế entity, quan hệ database, API và quá trình migration ổn định hơn. Đặc biệt, không nên mặc định ID trong database luôn phải xuất hiện nguyên dạng trong URL hoặc mã nghiệp vụ phải được dùng làm khóa chính.

## 1. Một ví dụ xuyên suốt

Giả sử hệ thống quản lý đơn hàng có một entity:

| Khái niệm | Ví dụ | Ý nghĩa |
|---|---|---|
| ID lưu trữ | `42` | Khóa chính trong bảng `orders` |
| Khóa nghiệp vụ | `SO-2026-0042` | Mã đơn hàng hiển thị trên hóa đơn và trao đổi với khách hàng |
| URI tài nguyên | `https://api.example.com/api/orders/42` | Địa chỉ HTTP để client đọc hoặc thao tác với order |

Trong cấu hình Spring Data REST mặc định, item URI thường được tạo bằng collection path cộng với database identifier. Vì vậy, nếu repository export dưới đường dẫn `/orders` và entity có ID là 42, URI mặc định có dạng `/orders/42`.

Tuy nhiên, API có thể được cấu hình để dùng một định danh khác trong URI, ví dụ mã đơn hàng `SO-2026-0042`. Khi đó, ID lưu trữ vẫn là 42 và khóa nghiệp vụ vẫn là SO-2026-0042; chỉ cách định danh resource trên HTTP thay đổi.

## 2. ID lưu trữ — Storage ID

ID lưu trữ là định danh mà persistence layer sử dụng để nhận diện một entity. Với JPA, trường được đánh dấu `@Id` là định danh entity. Database thường dùng giá trị này làm primary key và dùng nó để tạo foreign key từ các bảng liên quan.

### 2.1. Đặc điểm

- Có tính duy nhất trong phạm vi entity/table hoặc phạm vi được persistence store quy định.
- Thường không mang ý nghĩa nghiệp vụ.
- Có thể được sinh tự động bằng identity, sequence hoặc cơ chế UUID.
- Được dùng trong quan hệ giữa các bản ghi và thao tác persistence.
- Nên ổn định trong suốt vòng đời entity.
- Thường có kiểu đơn giản như `Long`, `UUID` hoặc một kiểu khóa phức hợp.

Ví dụ JPA:

~~~java
@Entity
@Table(name = "orders")
public class Order {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String status;

    protected Order() {
    }

    public Long getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }
}
~~~

Trong ví dụ, `id` là khóa chính của entity. Khi lưu entity mới, database/provider sinh ID. Ứng dụng không cần yêu cầu người dùng nhập ID này.

### 2.2. Các kiểu ID thường gặp

| Kiểu | Ví dụ | Điểm cần cân nhắc |
|---|---|---|
| Identity số | `42` | Dễ dùng, gọn, có thể lộ thứ tự hoặc quy mô dữ liệu |
| Sequence số | `10042` | Có thể cấp trước theo sequence; vẫn là ID kỹ thuật |
| UUID | `8d3d...-...` | Có thể tạo phân tán, ít phụ thuộc bộ cấp số trung tâm; dài hơn |
| Composite ID | `tenantId + localId` | Biểu diễn và tham chiếu phức tạp hơn |
| ID của data store | MongoDB ObjectId, key của store khác | Phụ thuộc cơ chế của persistence store |

ID số tăng dần không phải lúc nào cũng là lựa chọn sai. Nó thường thuận tiện cho khóa chính và index. UUID cũng không tự động làm hệ thống an toàn hơn; authorization vẫn phải kiểm tra quyền truy cập cho từng resource.

### 2.3. ID lưu trữ không phải khóa bảo mật

Không nên cho rằng một ID khó đoán đồng nghĩa người dùng không thể truy cập trái phép. Nếu API cho phép `GET /orders/42`, server vẫn phải xác minh người gọi có quyền xem order 42 hay không.

ID tuần tự có thể khiến người dùng dễ thử các giá trị lân cận. UUID có thể làm việc đoán URI khó hơn, nhưng không thay thế authentication và authorization. URI không phải secret token.

## 3. Khóa nghiệp vụ — Business key

Khóa nghiệp vụ là giá trị được domain dùng để nhận diện một đối tượng theo quy tắc thực tế. Nó thường có ý nghĩa với con người hoặc hệ thống tích hợp.

Ví dụ:

- Mã đơn hàng: `SO-2026-0042`.
- Mã sản phẩm: `SKU-AX19-BLK`.
- ISBN của sách.
- Mã nhân viên do doanh nghiệp cấp.
- Mã khách hàng trong hệ thống CRM.
- Mã giao dịch từ đối tác thanh toán.

Khóa nghiệp vụ có thể là natural key nếu được lấy từ dữ liệu có ý nghĩa tự nhiên trong domain. Tuy nhiên, một giá trị có vẻ tự nhiên vẫn có thể thay đổi, trùng lặp theo phạm vi hoặc chứa thông tin nhạy cảm.

### 3.1. Đặc điểm

- Có ý nghĩa trong domain và thường được dùng trong giao tiếp nghiệp vụ.
- Có quy tắc tạo, định dạng, phạm vi duy nhất và vòng đời riêng.
- Có thể là chuỗi, số, tổ hợp nhiều trường hoặc mã từ hệ thống bên ngoài.
- Có thể cần unique constraint ở database.
- Có thể bất biến hoặc có thể thay đổi theo chính sách nghiệp vụ.
- Không nhất thiết là primary key của database.

Một mã đơn hàng có thể duy nhất trong toàn hệ thống, hoặc chỉ duy nhất trong từng tenant/năm/chi nhánh. Phạm vi duy nhất phải được định nghĩa rõ. Nếu mã chỉ duy nhất trong tenant, cần ràng buộc trên cặp `tenant_id, order_number`, không phải chỉ trên `order_number`.

### 3.2. Đặt unique constraint cho business key

Ví dụ entity có ID kỹ thuật và mã đơn hàng riêng:

~~~java
import jakarta.persistence.*;

@Entity
@Table(
    name = "orders",
    uniqueConstraints = {
        @UniqueConstraint(
            name = "uk_orders_order_number",
            columnNames = "order_number"
        )
    }
)
public class Order {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(
        name = "order_number",
        nullable = false,
        updatable = false,
        length = 40
    )
    private String orderNumber;

    @Column(nullable = false)
    private String status;

    protected Order() {
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }
}
~~~

Ở đây:

- `@Id` xác định ID lưu trữ.
- `@GeneratedValue` để persistence provider/database sinh ID.
- `orderNumber` là khóa nghiệp vụ.
- `uniqueConstraints` yêu cầu database bảo đảm mã đơn hàng không trùng.
- `updatable = false` thể hiện mã đơn hàng không được cập nhật qua cơ chế cập nhật entity thông thường. Chỉ dùng nếu chính sách domain xác định mã là bất biến.

Có thể dùng `@Column(unique = true)` cho unique constraint đơn giản. `@Table(uniqueConstraints = ...)` hữu ích khi cần đặt tên constraint hoặc tạo unique constraint trên nhiều cột.

Kiểm tra duy nhất ở Java trước khi lưu chỉ giúp thông báo sớm. Hai request đồng thời vẫn có thể cùng vượt qua bước kiểm tra. Database unique constraint mới là lớp bảo vệ cuối cùng để không lưu hai giá trị trùng nhau.

### 3.3. Business key có thể thay đổi

Không phải khóa nghiệp vụ nào cũng bất biến. Email, số điện thoại, tên người dùng hoặc mã khách hàng có thể được đổi theo quy trình nghiệp vụ. Nếu dùng một trường có thể thay đổi làm định danh lâu dài cho entity, mọi URI hoặc hệ thống tham chiếu đến trường đó có thể bị ảnh hưởng.

Trước khi chọn business key làm ID công khai, hãy trả lời:

1. Giá trị có duy nhất trong toàn bộ phạm vi cần thiết không?
2. Giá trị có thể đổi trong vòng đời entity không?
3. Có thể tái sử dụng giá trị sau khi xóa entity không?
4. Giá trị có chứa thông tin cá nhân hoặc dữ liệu nội bộ không?
5. Hệ thống bên ngoài có phụ thuộc vào giá trị này không?
6. Có cần ghép thêm tenant, issuer hoặc namespace để tránh trùng không?

Nếu câu trả lời cho tính duy nhất hoặc tính ổn định không rõ ràng, hãy giữ business key như một thuộc tính riêng có unique constraint theo phạm vi phù hợp.

## 4. URI tài nguyên — Resource URI

URI (Uniform Resource Identifier) là định danh của một tài nguyên trong một không gian tên. URL là một dạng URI dùng để xác định vị trí và cách truy cập tài nguyên. Trong REST API, client thường nhận một HTTP URL làm URI của resource.

Ví dụ:

~~~text
https://api.example.com/api/orders/42
~~~ 

Có thể chia thành:

| Thành phần | Giá trị | Vai trò |
|---|---|---|
| Scheme | `https` | Giao thức |
| Authority | `api.example.com` | Host và có thể có port |
| Base path | `/api` | Tiền tố API |
| Collection path | `/orders` | Nhóm resource |
| Item identifier | `42` | Định danh item trong URI |

URI thuộc hợp đồng HTTP của API. Nó cho phép client nhận diện và truy cập resource mà server công bố. URI không bắt buộc phải là khóa chính database, cũng không nhất thiết phải trùng business key.

### 4.1. URI mặc định của Spring Data REST

Giả sử repository:

~~~java
@RepositoryRestResource(path = "orders")
public interface OrderRepository extends JpaRepository<Order, Long> {
}
~~~

Với ID lưu trữ là 42, Spring Data REST mặc định tạo item URI tương tự:

~~~text
/orders/42
~~~

Nếu cấu hình base path:

~~~properties
spring.data.rest.base-path=/api
~~~

URI sẽ có dạng:

~~~text
/api/orders/42
~~~

Mặc định, Spring Data REST ghép collection path với database identifier. Client có thể nhận URI qua link `self` trong HAL response hoặc header `Location` khi tạo resource.

Điều này là quy ước mặc định, không phải quy tắc bắt buộc rằng ID database và URI resource phải giống nhau trong mọi ứng dụng.

### 4.2. URI là một phần của hợp đồng API

Client có thể lưu hoặc theo dõi URI để truy cập resource ở những lần gọi tiếp theo. Vì vậy, thay đổi collection path, base path, item identifier hoặc host có thể ảnh hưởng đến client.

Một số nguyên tắc:

- Dùng link `self` server trả về thay vì tự ghép URI từ ID.
- Tránh để client suy luận cấu trúc database từ path.
- Chỉ đổi URI strategy khi đã đánh giá ảnh hưởng đến client và tích hợp bên ngoài.
- Giữ URI ổn định trong phạm vi hợp đồng API đã cam kết.
- Không đặt dữ liệu nhạy cảm vào URI vì URI thường xuất hiện trong log, browser history, proxy và monitoring.

Một resource URI có thể đại diện cho dữ liệu tổng hợp từ nhiều bảng, hoặc một representation khác của cùng entity. Do đó, URI mô tả tài nguyên ở tầng API chứ không phải địa chỉ trực tiếp của một hàng database.

## 5. Ba khái niệm liên hệ với nhau như thế nào?

Một mô hình phổ biến là:

~~~mermaid
flowchart LR
    A[Business key<br/>SO-2026-0042] --> B[Domain entity<br/>Order]
    C[Storage ID<br/>42] --> B
    B --> D[Resource URI<br/>/api/orders/42]
    D --> E[HTTP client]
    E --> F[Spring Data REST]
    F --> B
~~~

Database sử dụng ID lưu trữ để quản lý entity và quan hệ. Domain sử dụng business key để áp dụng quy tắc nghiệp vụ. API sử dụng URI để công bố resource cho client.

Một request:

~~~http
GET /api/orders/42
Accept: application/hal+json
~~~

có thể được xử lý theo logic:

1. Spring Data REST nhận item identifier `42` từ URI.
2. Framework chuyển identifier thành kiểu ID của repository.
3. Repository tìm entity có storage ID là 42.
4. Entity trả về có business key là `SO-2026-0042`.
5. Framework dựng representation và trả link `self` của resource.

Trong cấu hình mặc định, URI item chứa storage ID. Nếu ứng dụng cấu hình custom entity lookup, bước 2 và 3 có thể dùng một định danh khác.

## 6. Dùng business key trong URI của Spring Data REST

Có hai nhu cầu khác nhau thường bị nhầm lẫn:

- **Đổi cách biểu diễn backend ID:** ví dụ ID kỹ thuật là UUID hoặc composite ID nhưng muốn chuyển nó thành một chuỗi URI phù hợp.
- **Dùng một thuộc tính khác của entity làm resource identifier:** ví dụ muốn URI chứa username hoặc order number thay cho database ID.

Spring Data REST có các cơ chế riêng cho hai nhu cầu này.

### 6.1. Custom Entity Lookup

Nếu muốn item URI dùng business key, Spring Data REST hỗ trợ cấu hình entity lookup. Ví dụ repository:

~~~java
@RepositoryRestResource(path = "orders")
public interface OrderRepository extends JpaRepository<Order, Long> {

    Optional<Order> findByOrderNumber(String orderNumber);
}
~~~

Đăng ký mapping từ entity sang business key và từ business key về entity:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;

@Configuration
public class SpringDataRestConfiguration
        implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config) {

        config.withEntityLookup()
            .forRepository(OrderRepository.class)
            .withIdMapping(Order::getOrderNumber)
            .withLookup(OrderRepository::findByOrderNumber);
    }
}
~~~

Với cấu hình trên:

- `Order::getOrderNumber` cung cấp định danh sẽ xuất hiện trong item URI.
- `findByOrderNumber` tìm entity tương ứng khi server nhận request.
- Storage ID của entity vẫn là `Long id`.
- Business key phải duy nhất trong phạm vi repository lookup.

Nếu order có storage ID 42 và business key `SO-2026-0042`, item URI có thể trở thành:

~~~text
/orders/SO-2026-0042
~~~

Client có thể GET resource bằng business key:

~~~http
GET /orders/SO-2026-0042
Accept: application/hal+json
~~~

Đây là thay đổi quan trọng của hợp đồng API. Trước khi bật, cần kiểm tra business key có ổn định, duy nhất, không nhạy cảm và có thể dùng an toàn trong URI hay không. Đồng thời, kiểm thử các link được tạo, thao tác cập nhật/xóa và association trỏ đến item resource.

Nếu business key có phạm vi theo tenant, cần thiết kế lookup để không trả nhầm entity giữa các tenant. Không dùng một trường chỉ duy nhất cục bộ làm identifier toàn cục nếu URI không chứa namespace cần thiết.

### 6.2. BackendIdConverter

`BackendIdConverter` là SPI cho phép tùy chỉnh cách ID backend được biểu diễn trong URI. Nó có hai chiều:

- `toRequestId(...)`: chuyển backend ID thành chuỗi dùng trong URI được sinh ra.
- `fromRequestId(...)`: chuyển chuỗi trong request thành backend ID để repository tìm entity.

Cơ chế này hữu ích khi cần chuyển đổi cách biểu diễn ID, ví dụ ID phức hợp hoặc một chuỗi opaque. Nó không tự tạo ra quy tắc business key cho domain. Nếu muốn ánh xạ từ thuộc tính như order number sang entity, hãy dùng entity lookup phù hợp.

Không nên tự viết converter mã hóa ID chỉ để che giấu dữ liệu rồi coi đó là biện pháp bảo mật. Dù URI dùng số, UUID hay chuỗi đã mã hóa, server vẫn phải kiểm tra quyền truy cập.

## 7. Tìm entity bằng business key mà không đổi item URI

Không phải lúc nào cũng cần đưa business key vào item URI. Có thể giữ URI theo storage ID và công bố query method để tra cứu theo business key.

Ví dụ:

~~~java
@RepositoryRestResource(path = "orders")
public interface OrderRepository extends JpaRepository<Order, Long> {

    @RestResource(path = "by-order-number", rel = "by-order-number")
    Optional<Order> findByOrderNumber(
        @Param("orderNumber") String orderNumber
    );
}
~~~

Client tìm order theo business key:

~~~http
GET /orders/search/by-order-number?orderNumber=SO-2026-0042
Accept: application/hal+json
~~~

Response sẽ cung cấp representation của order và link `self` đến URI item theo cấu hình hiện tại, ví dụ `/orders/42`.

Cách này giữ rõ hai vai trò:

- Business key là tiêu chí tìm kiếm nghiệp vụ.
- Item URI vẫn được định danh bằng storage ID.

Nên dùng query method khi business key có thể thay đổi hoặc không muốn biến nó thành định danh lâu dài của resource. Nếu cần URI công khai dễ đọc theo business key, custom entity lookup là lựa chọn có chủ đích hơn.

## 8. Surrogate key và natural key

Hai chiến lược thường gặp khi thiết kế khóa database:

### 8.1. Surrogate key

Surrogate key là ID kỹ thuật không mang ý nghĩa nghiệp vụ, ví dụ `Long id` hoặc UUID.

Ưu điểm:

- Ít thay đổi khi quy tắc nghiệp vụ thay đổi.
- Dễ dùng làm foreign key.
- Không phụ thuộc độ dài hoặc định dạng business key.
- Có thể tạo trước hoặc phân phối theo cơ chế phù hợp.

Nhược điểm:

- Người dùng không thể hiểu ý nghĩa chỉ từ ID.
- Cần trường business key riêng nếu nghiệp vụ cần mã nhận diện.
- Nếu ID tuần tự được công khai, client có thể suy đoán các giá trị khác; vẫn cần authorization.

### 8.2. Natural key

Natural key là khóa lấy từ thuộc tính có ý nghĩa trong domain, ví dụ ISBN hoặc mã sản phẩm được chuẩn hóa.

Ưu điểm:

- Có thể dùng trực tiếp trong nghiệp vụ và trao đổi dữ liệu.
- Giảm một trường mã riêng nếu giá trị thực sự ổn định và duy nhất.
- Hữu ích khi tích hợp hệ thống cần cùng một mã nhận diện.

Nhược điểm:

- Có thể thay đổi do chính sách hoặc nguồn cấp mã.
- Có thể dài, phức tạp hoặc chứa thông tin nhạy cảm.
- Có thể chỉ duy nhất trong một phạm vi.
- Nếu dùng làm khóa chính, thay đổi có thể ảnh hưởng nhiều foreign key và hệ thống liên quan.

Với phần lớn ứng dụng nghiệp vụ, một thiết kế thực tế là dùng surrogate key làm primary key, đồng thời giữ business key ở một cột riêng với unique constraint phù hợp. Chỉ dùng natural key làm primary key khi domain thực sự bảo đảm tính ổn định, tính duy nhất và phạm vi sử dụng lâu dài.

## 9. Khóa nghiệp vụ phức hợp và phạm vi duy nhất

Một business key có thể được tạo từ nhiều trường. Ví dụ mã đơn hàng chỉ duy nhất trong từng tenant:

~~~java
@Entity
@Table(
    name = "orders",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_orders_tenant_number",
        columnNames = {"tenant_id", "order_number"}
    )
)
public class Order {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(name = "order_number", nullable = false)
    private String orderNumber;
}
~~~

Ở đây, `orderNumber` không duy nhất toàn cục. Khóa nghiệp vụ thực tế là cặp:

~~~text
(tenantId, orderNumber)
~~~

Nếu API chỉ dùng `/orders/{orderNumber}`, server không thể xác định duy nhất entity khi có hai tenant cùng dùng mã đó. Có thể chọn một trong các hướng:

- Đưa tenant hoặc namespace vào URI.
- Dùng một public identifier duy nhất toàn cục.
- Giữ item URI theo storage ID và dùng query method có kiểm tra tenant.
- Dùng custom entity lookup có phạm vi tenant rõ ràng dựa trên context bảo mật.

Không nên ghép chuỗi tùy tiện nếu không có quy tắc escaping và parsing rõ ràng. Nếu ID phức hợp cần xuất hiện trong URI, cân nhắc converter chuyên biệt và kiểm thử round-trip.

## 10. Những rủi ro khi dùng business key làm URI

### 10.1. Business key thay đổi

Nếu mã đơn hàng được đổi, URI cũ có thể không còn tìm thấy entity. Client lưu URI cũ sẽ gặp lỗi hoặc cần redirect/alias. Nếu URI đã được chia sẻ cho đối tác, migration phức tạp hơn nhiều so với cập nhật một cột database.

Chỉ dùng business key trong URI khi chính sách xác định nó ổn định. Nếu vẫn có thể đổi, hãy cân nhắc URI theo surrogate/public ID và dùng business key làm search parameter.

### 10.2. Business key chứa dữ liệu cá nhân

Email, số điện thoại, số giấy tờ hoặc tên người dùng có thể là business identifier nhưng không nhất thiết phù hợp để xuất hiện trong URL. URI thường được ghi vào access log, reverse proxy, monitoring và lịch sử trình duyệt.

Dùng một mã công khai được thiết kế riêng nếu cần định danh resource mà không tiết lộ thông tin cá nhân.

### 10.3. Trùng lặp và tái sử dụng mã

Một unique check trong service không đủ để xử lý request đồng thời. Cần unique constraint ở database và xử lý lỗi vi phạm constraint phù hợp.

Cũng phải quyết định business key có được tái sử dụng sau khi entity bị xóa hay không. Ví dụ mã nhân viên có thể cần được giữ lại để audit và không cấp cho người khác.

### 10.4. Lẫn lộn với authorization

Không được cho rằng người biết business key hoặc URI có quyền thao tác trên entity. Mọi request vẫn cần kiểm tra quyền theo user, tenant, trạng thái nghiệp vụ và resource đích.

### 10.5. Tác động đến tích hợp và migration

Khi đổi storage ID, foreign key và dữ liệu tham chiếu nội bộ có thể bị ảnh hưởng. Khi đổi URI, client và tích hợp bên ngoài có thể bị ảnh hưởng. Khi đổi business key, quy tắc domain, hóa đơn, báo cáo và hệ thống đối tác có thể bị ảnh hưởng.

Hãy quản lý ba loại thay đổi như ba loại hợp đồng khác nhau.

## 11. Cách chọn thiết kế cho một ứng dụng Spring Data REST

Có thể dùng các câu hỏi sau để quyết định:

| Nhu cầu | Thiết kế thường phù hợp |
|---|---|
| Cần khóa chính gọn, ổn định cho database | Surrogate storage ID |
| Cần mã dễ đọc cho người dùng và hóa đơn | Business key riêng, có unique constraint |
| API không cần lộ database ID | Public identifier hoặc custom entity lookup |
| Business key có thể thay đổi | Giữ item URI theo ID ổn định, dùng search endpoint |
| Business key chỉ duy nhất trong tenant | Unique constraint và lookup có tenant scope |
| ID backend là composite hoặc cần encoding | Xem xét `BackendIdConverter` |
| Client cần khám phá URI thực tế | Trả HAL links và yêu cầu client theo link `self` |

Một lựa chọn cân bằng thường là:

1. Dùng `Long id` hoặc UUID làm storage ID.
2. Dùng `orderNumber` làm business key, có unique constraint.
3. Để Spring Data REST công bố item URI theo storage ID nếu không có yêu cầu khác.
4. Công bố query method để tìm theo order number.
5. Chỉ chuyển item URI sang business key khi business key thực sự ổn định và là một phần chủ đích của API contract.

## 12. Kiểm thử và xác minh

Cần kiểm tra riêng từng lớp định danh:

- **Storage ID:** lưu entity và xác nhận primary key được sinh; quan hệ foreign key tham chiếu đúng entity.
- **Business key:** thử mã hợp lệ, mã trùng, mã sai định dạng, mã thay đổi và phạm vi tenant.
- **Resource URI:** GET qua link `self`, xác nhận URI được tạo đúng; kiểm tra POST trả `Location`; kiểm tra client vẫn hoạt động khi dùng base path.
- **Custom entity lookup:** GET bằng business key, kiểm tra entity được tìm đúng và business key trùng không thể tạo kết quả mơ hồ.
- **Security:** thử truy cập URI hợp lệ nhưng thuộc tenant khác; server phải từ chối theo chính sách.
- **Migration:** kiểm tra URI cũ và business key cũ khi thay đổi định danh.

Ví dụ integration test cho query method theo business key:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderBusinessKeyTests {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void findsOrderByBusinessKey() throws Exception {
        mockMvc.perform(get(
                "/orders/search/by-order-number"
            )
            .param("orderNumber", "SO-2026-0042")
            .accept("application/hal+json"))
            .andExpect(status().isOk());
    }
}
~~~

Test này giả định dữ liệu mẫu đã được chuẩn bị và repository đã export query method tương ứng. Trong test đầy đủ, hãy kiểm tra ID, business key, link `self` và quyền truy cập của người gọi.

## 13. Lỗi thường gặp

- **Dùng business key làm primary key theo thói quen:** nếu giá trị có thể thay đổi, các quan hệ và migration sẽ khó khăn.
- **Cho rằng URI luôn chứa database ID:** đó là mặc định thường gặp của Spring Data REST, nhưng có thể cấu hình entity lookup hoặc ID converter.
- **Cho rằng business key tự động duy nhất:** cần xác định phạm vi và bảo đảm bằng database constraint.
- **Dùng URI làm nơi chứa dữ liệu bí mật:** URL có thể được ghi log và lưu trong nhiều hệ thống trung gian.
- **Dùng UUID để thay authorization:** ID khó đoán không ngăn được truy cập trái phép khi server không kiểm tra quyền.
- **Đổi business key mà không tính đến client:** nếu business key nằm trong URI, các link cũ có thể hỏng.
- **Dùng query method như custom item URI:** tìm kiếm theo business key và định danh item URI là hai cách công bố API khác nhau.
- **Không phân biệt BackendIdConverter và EntityLookup:** một cơ chế chuyển đổi cách biểu diễn backend ID; cơ chế kia ánh xạ một giá trị định danh resource sang entity.

## 14. Checklist thiết kế

- [ ] Entity có storage ID ổn định và được đánh dấu `@Id`.
- [ ] Business key được định nghĩa rõ về định dạng, phạm vi duy nhất và khả năng thay đổi.
- [ ] Database có unique constraint tương ứng với quy tắc business key.
- [ ] Resource URI được xem là hợp đồng API, không phụ thuộc client vào schema database.
- [ ] Client sử dụng link `self` từ HAL response.
- [ ] Nếu dùng custom entity lookup, mapping hai chiều hoạt động và không mơ hồ.
- [ ] Nếu dùng BackendIdConverter, chuyển đổi URI ID và backend ID có tính round-trip.
- [ ] Authorization được kiểm tra độc lập với việc ID có dễ đoán hay không.
- [ ] Có test cho duplicate key, tenant scope, URI cũ và thay đổi business key.

## 15. Tài liệu tham khảo

- [Spring Data REST Reference — Customizing item resource URIs](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html): mô tả cách mặc định tạo item URI và cấu hình custom entity lookup.
- [Spring Data REST API — BackendIdConverter](https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/webmvc/spi/BackendIdConverter.html): SPI chuyển đổi backend ID sang chuỗi URI và ngược lại.
- [Spring Data REST Reference — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): mô tả collection và item resource, HTTP methods và HAL links.

Storage ID, business key và resource URI có thể cùng trỏ đến một entity nhưng đại diện cho ba lớp trách nhiệm khác nhau. Thiết kế tốt giữ cho ID lưu trữ ổn định, business key tuân thủ quy tắc domain, và URI trở thành một định danh HTTP rõ ràng, ổn định cho client.