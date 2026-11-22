# Khai báo ReactiveCrudRepository và R2dbcRepository

## 1. Repository trong Spring Data R2DBC là gì?

Spring Data R2DBC cung cấp mô hình repository để ứng dụng thao tác với dữ liệu quan hệ bằng API reactive. Thay vì tự viết các câu lệnh SQL cho mọi thao tác đọc, thêm, sửa và xóa, bạn khai báo một interface repository gắn với kiểu entity và kiểu ID. Spring Data tạo implementation tại runtime dựa trên metadata ánh xạ, query method và cấu hình R2DBC.

Hai interface cơ bản thường gặp là:

- ReactiveCrudRepository: cung cấp các thao tác CRUD trả về kiểu reactive như Mono và Flux.
- R2dbcRepository: kết hợp các thao tác CRUD reactive với khả năng sắp xếp được cung cấp bởi ReactiveSortingRepository.

Cả hai đều là repository reactive. Chúng không phải các interface CRUD đồng bộ của Spring Data Commons và không trả về List, Optional hoặc đối tượng kết quả đồng bộ cho các thao tác thông thường.

Ví dụ, một repository cho Customer có thể được khai báo như sau:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {
}
~~~

Interface này mô tả hợp đồng truy cập dữ liệu. Bạn không cần tự viết class triển khai các phương thức CRUD cơ bản. Spring Data tạo proxy repository khi ứng dụng khởi động và kết nối proxy đó với cơ chế mapping và R2DBC.

## 2. Hai tham số generic của repository

Cả ReactiveCrudRepository và R2dbcRepository đều nhận hai tham số generic:

~~~java
ReactiveCrudRepository<T, ID>
~~~

Trong đó:

- T là kiểu entity mà repository quản lý.
- ID là kiểu dữ liệu của thuộc tính định danh trong entity.

Ví dụ:

~~~java
public interface ProductRepository
        extends ReactiveCrudRepository<Product, Long> {
}
~~~

Repository trên quản lý entity Product có ID kiểu Long.

Nếu entity dùng UUID:

~~~java
public interface AccountRepository
        extends ReactiveCrudRepository<Account, UUID> {
}
~~~

Kiểu ID trong repository phải tương thích với kiểu thuộc tính được đánh dấu @Id. Nếu entity dùng Long nhưng repository khai báo UUID, các thao tác tìm kiếm hoặc xóa theo ID sẽ không có kiểu dữ liệu phù hợp và có thể gây lỗi khi biên dịch hoặc lúc chạy tùy cách sử dụng.

Một entity minh họa:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public class Customer {

    @Id
    private Long id;

    private String fullName;
    private String email;

    public Customer() {
    }

    public Customer(Long id, String fullName, String email) {
        this.id = id;
        this.fullName = fullName;
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public String getEmail() {
        return email;
    }
}
~~~

Spring Data sử dụng @Id để xác định thuộc tính định danh. Tên bảng và cột được suy ra theo mapping convention hoặc được chỉ định bằng @Table và @Column. Repository dựa trên metadata đó để tạo các thao tác CRUD.

## 3. ReactiveCrudRepository

### 3.1. Mục đích

ReactiveCrudRepository là lựa chọn cơ bản khi cần các thao tác CRUD reactive. Interface này kế thừa Repository và cung cấp những phương thức phổ biến để lưu, đọc và xóa entity.

Ví dụ:

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {
}
~~~

Không cần triển khai các phương thức save, findById, findAll hoặc deleteById. Spring Data tạo implementation phù hợp với R2DBC repository infrastructure.

### 3.2. Các phương thức CRUD thường dùng

Các phương thức thường gặp gồm:

| Phương thức | Kiểu trả về reactive thường dùng | Ý nghĩa |
|---|---|---|
| save(entity) | Mono<S> | Lưu một entity mới hoặc cập nhật entity theo cơ chế persistence |
| saveAll(Iterable) | Flux<S> | Lưu một tập entity có sẵn |
| saveAll(Publisher) | Flux<S> | Nhận các entity từ publisher và lưu |
| findById(id) | Mono<T> | Tìm một entity theo ID |
| findById(Publisher<ID>) | Mono<T> | Tìm theo ID được phát từ publisher |
| existsById(id) | Mono<Boolean> | Kiểm tra entity có tồn tại theo ID |
| findAll() | Flux<T> | Đọc các entity |
| findAllById(Iterable<ID>) | Flux<T> | Đọc các entity theo nhiều ID |
| count() | Mono<Long> | Đếm số entity |
| deleteById(id) | Mono<Void> | Xóa theo ID |
| delete(entity) | Mono<Void> | Xóa entity |
| deleteAll() | Mono<Void> | Xóa tất cả entity thuộc repository |

Chữ ký chính xác có thể thay đổi theo phiên bản Spring Data. Khi cần xác nhận kiểu trả về của một overload, hãy đối chiếu API documentation của phiên bản đang dùng. Ý tưởng chung là kết quả được biểu diễn bằng publisher reactive, không phải giá trị đồng bộ.

### 3.3. save() không đơn giản luôn có nghĩa INSERT

Phương thức save(entity) lưu một entity. Spring Data xác định entity mới hay đã tồn tại dựa trên cơ chế nhận diện trạng thái mới (newness detection), thường dựa vào ID hoặc cơ chế Persistable nếu entity tùy chỉnh cách xác định.

Vì vậy, không nên chỉ dựa vào tên save để kết luận câu SQL luôn là INSERT. Tùy trạng thái entity, mapping và dialect, Spring Data có thể thực hiện thao tác insert hoặc update phù hợp.

Ví dụ:

~~~java
Mono<Customer> saved = customerRepository.save(customer);
~~~

Publisher saved mô tả thao tác lưu. Nó được thực thi khi có subscription. Khi thành công, Mono phát ra entity đã lưu theo kết quả mà repository trả về.

Nếu cần bảo đảm một bản ghi mới, hãy thiết kế ID và trạng thái newness rõ ràng. Nếu cần cập nhật một bản ghi hiện hữu, hãy xác định cách ID được quản lý và xử lý trường hợp bản ghi không tồn tại. Không nên giả định save luôn thực hiện upsert theo cùng một semantics trên mọi database.

### 3.4. Đọc một entity và đọc nhiều entity

findById trả về Mono vì một ID chỉ có thể tìm thấy tối đa một entity:

~~~java
Mono<Customer> customer = customerRepository.findById(42L);
~~~

Nếu không có bản ghi, Mono hoàn tất mà không phát ra giá trị. Có thể xử lý trường hợp này bằng switchIfEmpty:

~~~java
return customerRepository.findById(customerId)
    .switchIfEmpty(Mono.error(
        new CustomerNotFoundException(customerId)
    ));
~~~

findAll trả về Flux vì số lượng kết quả có thể bằng không, một hoặc nhiều:

~~~java
Flux<Customer> customers = customerRepository.findAll();
~~~

Flux phát từng entity theo luồng. Không cần tải toàn bộ kết quả vào List trước khi bắt đầu xử lý. Nếu muốn gom kết quả thành List, có thể dùng collectList(), nhưng cần cân nhắc kích thước dữ liệu vì thao tác đó giữ toàn bộ kết quả trong bộ nhớ.

### 3.5. Xóa dữ liệu và kiểu Mono<Void>

Các thao tác xóa thường trả về Mono<Void>:

~~~java
Mono<Void> deletion = customerRepository.deleteById(42L);
~~~

Mono<Void> biểu thị một thao tác hoàn tất hoặc phát sinh lỗi, không phát ra entity kết quả. Muốn thực hiện bước tiếp theo sau khi xóa, dùng then():

~~~java
return customerRepository.deleteById(customerId)
    .then(auditRepository.recordCustomerDeletion(customerId));
~~~

Nếu cần biết có bản ghi bị xóa hay không, hãy thiết kế thao tác kiểm tra hoặc câu lệnh phù hợp. Không nên giả định Mono<Void> cung cấp số hàng bị ảnh hưởng.

## 4. R2dbcRepository

### 4.1. Mục đích và quan hệ kế thừa

R2dbcRepository là interface repository chuyên biệt cho Spring Data R2DBC. Nó kế thừa các thao tác CRUD reactive và khả năng sắp xếp reactive được cung cấp bởi ReactiveSortingRepository.

Có thể khai báo:

~~~java
import org.springframework.data.r2dbc.repository.R2dbcRepository;

public interface CustomerRepository
        extends R2dbcRepository<Customer, Long> {
}
~~~

Trong cách dùng thông thường, repository này vẫn cung cấp các thao tác CRUD như ReactiveCrudRepository, đồng thời có hợp đồng tìm kiếm/sắp xếp với Sort.

Điểm cần nhớ là R2dbcRepository không biến thao tác reactive thành blocking. Các phương thức vẫn trả về Mono hoặc Flux.

### 4.2. Khả năng sắp xếp

ReactiveSortingRepository cung cấp phương thức findAll(Sort sort) để đọc dữ liệu theo thứ tự được yêu cầu:

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.r2dbc.repository.R2dbcRepository;

public interface CustomerRepository
        extends R2dbcRepository<Customer, Long> {
}
~~~

Cách sử dụng:

~~~java
Sort sort = Sort.by(Sort.Direction.ASC, "fullName");

Flux<Customer> customers =
    customerRepository.findAll(sort);
~~~

Thuộc tính được truyền vào Sort là tên property trong entity, không nhất thiết là tên cột SQL. Mapping metadata sẽ chuyển property sang cột tương ứng theo quy ước hoặc annotation.

Ví dụ, property fullName có thể ánh xạ tới cột full_name. Khi dùng Sort.by("fullName"), Spring Data làm việc với property metadata để tạo thứ tự theo cột tương ứng.

Nếu sort theo nhiều thuộc tính:

~~~java
Sort sort = Sort.by(
    Sort.Order.asc("lastName"),
    Sort.Order.asc("firstName")
);

Flux<Customer> customers = customerRepository.findAll(sort);
~~~

Chỉ nên cho phép sắp xếp theo những thuộc tính hợp lệ của entity. Nếu tên sort đến từ request bên ngoài, hãy ánh xạ danh sách giá trị được cho phép sang property tương ứng thay vì chuyển nguyên chuỗi không kiểm soát.

### 4.3. Chọn interface nào?

| Nhu cầu | Interface thường phù hợp |
|---|---|
| Chỉ cần CRUD reactive | ReactiveCrudRepository |
| Cần CRUD reactive và findAll(Sort) | R2dbcRepository |
| Muốn khai báo rõ repository dùng R2DBC | R2dbcRepository |
| Muốn giữ hợp đồng tối thiểu cho service | ReactiveCrudRepository |

R2dbcRepository là lựa chọn tiện khi cần sorting repository contract. Nếu không cần sorting, ReactiveCrudRepository giúp interface thể hiện đúng phạm vi chức năng mà service sử dụng.

Không cần kế thừa cả hai interface trong cùng repository chỉ để có CRUD và sorting, vì R2dbcRepository đã bao gồm các hợp đồng đó theo quan hệ kế thừa của Spring Data R2DBC.

Chi tiết interface và quan hệ kế thừa có thể thay đổi giữa các phiên bản Spring Data. Hãy kiểm tra Javadoc của đúng phiên bản dependency trong dự án trước khi dựa vào một method hoặc interface mở rộng cụ thể.

## 5. Khai báo query method theo tên phương thức

Một lợi ích quan trọng của Spring Data repository là khả năng suy ra truy vấn từ tên phương thức. Bạn khai báo method theo quy ước, Spring Data phân tích tên để xây dựng query.

Ví dụ:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<Customer> findByLastName(String lastName);

    Mono<Customer> findByEmail(String email);

    Flux<Customer> findByActiveTrue();

    Mono<Boolean> existsByEmail(String email);

    Mono<Long> countByActiveTrue();

    Mono<Void> deleteByEmail(String email);
}
~~~

Các tiền tố thường gặp:

| Tiền tố | Ý nghĩa |
|---|---|
| findBy / readBy / getBy | Tìm bản ghi theo điều kiện |
| existsBy | Kiểm tra bản ghi phù hợp có tồn tại |
| countBy | Đếm bản ghi phù hợp |
| deleteBy / removeBy | Xóa bản ghi phù hợp |

Phần sau By mô tả điều kiện. Ví dụ findByLastName tìm theo property lastName. Spring Data sử dụng mapping metadata để liên hệ property đó với cột trong database.

### 5.1. Kết hợp nhiều điều kiện

Có thể dùng And và Or:

~~~java
Flux<Customer> findByFirstNameAndLastName(
    String firstName,
    String lastName
);

Flux<Customer> findByActiveTrueOrEmailIsNull();
~~~

Tên method cần phản ánh đúng property và toán tử mà Spring Data hỗ trợ. Với truy vấn phức tạp, tên method quá dài sẽ khó đọc và khó bảo trì. Khi đó, cân nhắc @Query hoặc repository fragment.

### 5.2. Điều kiện so sánh và tìm kiếm

Ví dụ:

~~~java
Flux<Product> findByPriceGreaterThan(BigDecimal minPrice);

Flux<Product> findByPriceBetween(
    BigDecimal min,
    BigDecimal max
);

Flux<Customer> findByLastNameContaining(String fragment);

Flux<Order> findByStatusIn(Collection<OrderStatus> statuses);
~~~

Các keyword như GreaterThan, Between, Containing và In được Spring Data phân tích theo property type và query derivation rules.

Không phải mọi keyword của Spring Data JPA đều có cùng mức hỗ trợ trong R2DBC. Hãy kiểm tra khả năng query derivation của Spring Data Relational phiên bản đang dùng, đặc biệt với các toán tử đặc thù, function, join và truy vấn database-specific.

### 5.3. Sắp xếp theo tên method

Có thể biểu diễn thứ tự mặc định ngay trong tên method:

~~~java
Flux<Customer> findByActiveTrueOrderByLastNameAscFirstNameAsc();

Flux<Order> findByStatusOrderByCreatedAtDesc(OrderStatus status);
~~~

Nếu thứ tự cần thay đổi theo request, dùng Sort ở method hỗ trợ sorting hoặc dùng R2dbcRepository với findAll(Sort). Với truy vấn derived riêng, hãy kiểm tra chữ ký method và hỗ trợ Sort trong phiên bản Spring Data hiện tại.

## 6. Dùng @Query khi tên method không đủ diễn đạt

Khi truy vấn cần SQL rõ ràng, có thể dùng @Query của Spring Data R2DBC:

~~~java
import org.springframework.data.r2dbc.repository.Query;
import org.springframework.data.repository.reactive.ReactiveCrudRepository;

public interface OrderRepository
        extends ReactiveCrudRepository<Order, Long> {

    @Query("""
        SELECT id, customer_id, status, created_at
        FROM orders
        WHERE customer_id = :customerId
        ORDER BY created_at DESC
        """)
    Flux<Order> findRecentOrdersByCustomer(Long customerId);
}
~~~

@Query cho phép chỉ định câu SQL trực tiếp. Tên tham số được bind theo cơ chế query method của Spring Data R2DBC; hãy bảo đảm tên placeholder và tham số tương ứng khớp nhau theo quy tắc của phiên bản đang dùng.

Khi dùng SQL thủ công:

- Viết tên bảng và cột đúng với schema thật.
- Không giả định naming strategy sẽ tự đổi tên trong chuỗi SQL.
- Dùng parameter binding thay vì nối chuỗi dữ liệu đầu vào vào SQL.
- Chỉ chọn các cột phù hợp với mapping của kiểu kết quả.
- Kiểm tra SQL theo dialect của database.
- Dùng integration test với database thực tế cho các câu query quan trọng.

Nếu query thay đổi dữ liệu, hãy khai báo theo quy tắc modifying query của phiên bản Spring Data R2DBC đang dùng, thường kết hợp @Modifying với @Query. Kiểu trả về cần phù hợp với số hàng bị ảnh hưởng hoặc semantics mà API hỗ trợ.

Ví dụ minh họa:

~~~java
@Modifying
@Query("""
    UPDATE orders
    SET status = :status
    WHERE id = :id
    """)
Mono<Integer> updateStatus(Long id, String status);
~~~

Chữ ký trả về và cách đánh dấu modifying query cần được kiểm tra với phiên bản Spring Data cụ thể. Với thao tác ghi nhiều bước hoặc cần rollback cùng nhau, hãy dùng reactive transaction phù hợp.

## 7. Repository method luôn trả về publisher

ReactiveCrudRepository và R2dbcRepository là API reactive. Phương thức đọc thường trả về Mono hoặc Flux; phương thức ghi/xóa cũng trả về publisher.

Ví dụ service:

~~~java
@Service
public class CustomerService {

    private final CustomerRepository customerRepository;

    public CustomerService(CustomerRepository customerRepository) {
        this.customerRepository = customerRepository;
    }

    public Mono<Customer> getCustomer(Long id) {
        return customerRepository.findById(id);
    }

    public Flux<Customer> searchByLastName(String lastName) {
        return customerRepository.findByLastName(lastName);
    }

    public Mono<Customer> createCustomer(Customer customer) {
        return customerRepository.save(customer);
    }
}
~~~

Service trả publisher cho controller hoặc tầng gọi tiếp theo. Nó không cần gọi subscribe() bên trong mỗi method.

Ví dụ WebFlux controller:

~~~java
@RestController
@RequestMapping("/customers")
public class CustomerController {

    private final CustomerService customerService;

    public CustomerController(CustomerService customerService) {
        this.customerService = customerService;
    }

    @GetMapping("/{id}")
    public Mono<Customer> getById(@PathVariable Long id) {
        return customerService.getCustomer(id);
    }

    @GetMapping
    public Flux<Customer> findAll() {
        return customerService.searchByLastName("Nguyen");
    }
}
~~~

Spring WebFlux đăng ký publisher để ghi response khi request được xử lý. Không cần tự subscribe hoặc block trong controller.

### 7.1. Mono và Flux

| Kiểu | Dùng khi | Ví dụ |
|---|---|---|
| Mono<T> | Không có hoặc có tối đa một kết quả | findById, findByEmail, save |
| Flux<T> | Có thể có nhiều kết quả | findAll, findByStatus, findByLastName |
| Mono<Void> | Chỉ quan tâm thao tác hoàn tất hay lỗi | deleteById |
| Mono<Long> | Kết quả đếm | count |
| Mono<Boolean> | Kết quả tồn tại | existsById |

Nếu một truy vấn được kỳ vọng trả về tối đa một hàng, dùng Mono<T> phù hợp. Nếu database trả về nhiều hơn một hàng trong khi method yêu cầu một kết quả đơn, thao tác có thể phát sinh lỗi cardinality thay vì âm thầm chọn một hàng bất kỳ.

### 7.2. Không dùng kiểu đồng bộ trong reactive repository

Không khai báo repository R2DBC như repository blocking:

~~~java
// Không phù hợp với ReactiveCrudRepository
Customer findByEmail(String email);

List<Customer> findAll();
~~~

Thay vào đó:

~~~java
Mono<Customer> findByEmail(String email);

Flux<Customer> findAll();
~~~

Nếu ứng dụng cần List để xử lý một tập dữ liệu nhỏ ở một ranh giới cụ thể, có thể collectList() từ Flux. Nhưng đó là thao tác gom kết quả trong reactive pipeline, không phải lý do để biến repository thành API blocking.

Không gọi block() trong event-loop thread của WebFlux. Block có thể làm giảm thông lượng và gây lỗi vận hành trong môi trường reactive.

## 8. Repository là interface, Spring tạo implementation

Bạn thường chỉ cần khai báo interface:

~~~java
public interface ProductRepository
        extends ReactiveCrudRepository<Product, Long> {

    Flux<Product> findByCategoryId(Long categoryId);
}
~~~

Spring Data repository infrastructure thực hiện các công việc chính:

1. Phát hiện interface repository trong phạm vi scan.
2. Xác định entity type và ID type từ generic parameters.
3. Đọc mapping metadata của entity.
4. Tạo implementation/proxy cho các phương thức CRUD.
5. Phân tích các query method theo tên hoặc @Query.
6. Kết nối các thao tác với R2DBC infrastructure và conversion configuration.
7. Cung cấp bean repository để các service inject.

Không cần viết class ProductRepositoryImpl chỉ để triển khai các phương thức CRUD tiêu chuẩn. Nếu cần logic truy vấn tùy chỉnh không thể biểu diễn bằng query method hoặc @Query, có thể dùng repository fragment.

## 9. Cấu hình để repository được phát hiện

### 9.1. Spring Boot

Trong ứng dụng Spring Boot, dependency starter phù hợp và cấu hình ConnectionFactory cho phép Spring Boot thiết lập nhiều thành phần R2DBC. Repository interfaces thường được phát hiện tự động trong package scan của ứng dụng.

Một dependency thường dùng trong Gradle:

~~~groovy
dependencies {
    implementation "org.springframework.boot:spring-boot-starter-data-r2dbc"
    runtimeOnly "io.r2dbc:r2dbc-postgresql"
}
~~~

Tên driver phụ thuộc database. Ví dụ trên minh họa PostgreSQL; với MySQL hoặc SQL Server, dùng driver R2DBC tương ứng.

Cấu hình kết nối có thể đặt trong application.yml:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/shop
    username: app_user
    password: change-me
~~~

Thông tin kết nối trong ví dụ chỉ mang tính minh họa. Trong môi trường thật, không ghi mật khẩu nhạy cảm trực tiếp vào source control; dùng secret/configuration management phù hợp.

### 9.2. @EnableR2dbcRepositories

Khi tự cấu hình hoặc cần chỉ định package repository, có thể dùng @EnableR2dbcRepositories:

~~~java
@Configuration
@EnableR2dbcRepositories(
    basePackages = "com.example.shop.repository"
)
public class R2dbcRepositoryConfiguration {
}
~~~

Annotation này yêu cầu Spring Data quét các repository interface trong package được chỉ định. Trong ứng dụng Boot đã tự động cấu hình repository đúng phạm vi, thường không cần khai báo thêm chỉ để lặp lại cấu hình mặc định.

Nếu repository nằm ngoài package scan, hãy điều chỉnh component/repository scan cho phù hợp. Một interface không được phát hiện sẽ không có bean để inject.

### 9.3. ConnectionFactory và transaction manager

Repository cần một ConnectionFactory phù hợp để truy cập database. Trong ứng dụng reactive có transaction, cấu hình transaction manager R2DBC phù hợp với ConnectionFactory mà repository sử dụng.

Không cấu hình repository dùng một ConnectionFactory và transaction manager dùng ConnectionFactory khác nếu mong muốn các thao tác cùng tham gia một transaction. Cần thống nhất hạ tầng truy cập dữ liệu.

## 10. Tổ chức repository theo nghiệp vụ

Một repository thường gắn với một aggregate root hoặc entity mà ứng dụng cần truy cập. Ví dụ:

~~~java
public interface OrderRepository
        extends ReactiveCrudRepository<Order, Long> {

    Flux<Order> findByCustomerId(Long customerId);

    Flux<Order> findByStatus(OrderStatus status);

    Mono<Long> countByStatus(OrderStatus status);
}
~~~

Service sử dụng repository để thực hiện nghiệp vụ:

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;

    public OrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    public Flux<Order> findCustomerOrders(Long customerId) {
        return orderRepository.findByCustomerId(customerId);
    }

    public Mono<Long> countPendingOrders() {
        return orderRepository.countByStatus(OrderStatus.PENDING);
    }
}
~~~

Không nên nhồi toàn bộ nghiệp vụ vào repository interface. Repository tập trung vào truy cập và truy vấn dữ liệu. Service điều phối nghiệp vụ, transaction và tương tác giữa các repository khi cần.

Cũng không nên tạo repository cho mọi lớp Java một cách máy móc. Một value object hoặc thành phần con thuộc aggregate có thể không cần repository riêng. Hãy dựa trên ranh giới aggregate và cách dữ liệu được truy cập.

## 11. Khi cần repository tùy chỉnh

Query method và @Query đáp ứng nhiều trường hợp. Khi logic truy cập phức tạp, có thể tách một repository fragment.

Ví dụ interface chính:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long>,
                CustomerSearchRepository {
}
~~~

Fragment:

~~~java
public interface CustomerSearchRepository {
    Flux<Customer> searchCustomers(String keyword);
}
~~~

Implementation fragment:

~~~java
public class CustomerSearchRepositoryImpl
        implements CustomerSearchRepository {

    private final DatabaseClient databaseClient;

    public CustomerSearchRepositoryImpl(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    @Override
    public Flux<Customer> searchCustomers(String keyword) {
        return databaseClient.sql("""
                SELECT id, full_name, email
                FROM customers
                WHERE full_name LIKE :pattern
                """)
            .bind("pattern", "%" + keyword + "%")
            .map((row, metadata) -> {
                Customer customer = new Customer();
                // Ánh xạ các cột theo constructor hoặc factory phù hợp.
                return customer;
            })
            .all();
    }
}
~~~

Đoạn mapping trong ví dụ được rút gọn để tập trung vào cấu trúc fragment. Trong implementation thực tế, cần ánh xạ đầy đủ các cột và xử lý null/kiểu dữ liệu theo schema.

Tên implementation fragment theo quy ước của Spring Data và cấu hình repository fragment. Hãy theo đúng convention của phiên bản đang dùng để Spring phát hiện implementation.

## 12. Lưu ý về phân trang trong repository reactive

Reactive repository thường dùng Flux để phát dữ liệu theo luồng. Khái niệm Page<T> đồng bộ có tổng số phần tử và thông tin trang đòi hỏi framework biết tổng số bản ghi, thường cần thêm truy vấn count. Vì thế, không nên mặc định mọi phương thức reactive hỗ trợ Page<T> giống repository blocking.

Khi cần giới hạn dữ liệu, có thể dùng Sort và các cơ chế query phù hợp với phiên bản Spring Data R2DBC, hoặc viết SQL với LIMIT/OFFSET:

~~~sql
SELECT id, full_name, email
FROM customers
ORDER BY id
LIMIT :limit OFFSET :offset;
~~~

Nếu API cần tổng số trang, hãy thực hiện truy vấn count riêng hoặc thiết kế response có metadata phù hợp. Với bảng lớn, cân nhắc keyset pagination/seek pagination thay cho offset sâu để giảm chi phí quét và sắp xếp.

Kiểu tham số Pageable, Page và các khả năng paging phụ thuộc phiên bản và cách khai báo query. Hãy xác nhận với API docs của Spring Data R2DBC đang dùng thay vì suy luận từ Spring Data JPA.

## 13. Transaction khi gọi nhiều repository

Nếu một nghiệp vụ cần cập nhật nhiều bảng, hãy dùng reactive transaction. Các publisher repository phải được nối trong cùng pipeline và chạy dưới transaction context phù hợp.

Ví dụ:

~~~java
@Transactional
public Mono<Void> completeOrder(Long orderId) {
    return orderRepository.findById(orderId)
        .switchIfEmpty(Mono.error(
            new IllegalArgumentException("Không tìm thấy đơn hàng")
        ))
        .flatMap(order -> {
            order.setStatus(OrderStatus.PAID);
            return orderRepository.save(order);
        })
        .flatMap(order ->
            paymentRepository.markPaid(order.getId())
        )
        .then();
}
~~~

Đây là ví dụ cấu trúc. Phương thức phải trả về publisher reactive, transaction manager phải là R2DBC reactive transaction manager và các repository phải dùng cùng ConnectionFactory để tham gia cùng transaction.

Không tự gọi subscribe() bên trong phương thức @Transactional. Việc đó tạo subscription độc lập, có thể chạy ngoài transaction context. Hãy trả publisher và kết hợp bằng flatMap, then, concatMap hoặc toán tử phù hợp.

Nếu có thao tác cần chạy song song, hãy cân nhắc cách connection và driver xử lý nhiều lệnh trên cùng transaction connection. Tuần tự hóa bằng then() hoặc concatMap khi cần bảo đảm thứ tự.

## 14. Các lỗi thường gặp

| Lỗi hoặc nhầm lẫn | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không inject được repository | Interface không được component/repository scan phát hiện | Kiểm tra package và @EnableR2dbcRepositories |
| ID type không khớp | Generic ID khác kiểu thuộc tính @Id | Đồng bộ kiểu ID |
| Query method không được tạo | Tên method dùng property không tồn tại hoặc keyword không hỗ trợ | Kiểm tra entity property và query derivation rules |
| Truy vấn không tìm thấy bảng/cột | Mapping metadata không khớp schema | Kiểm tra @Table, @Column và DDL |
| Dùng List hoặc entity đồng bộ trong repository reactive | Nhầm reactive repository với blocking repository | Dùng Mono/Flux |
| Không thấy truy vấn chạy | Publisher chưa được subscribe | Trả publisher cho framework hoặc subscribe ở đúng biên ứng dụng |
| Truy vấn chạy hai lần | Publisher cold được subscribe nhiều lần | Kiểm tra pipeline và tránh subscribe thủ công |
| Transaction không bao phủ mọi thao tác | Tạo subscription riêng hoặc dùng ConnectionFactory khác | Nối publisher và thống nhất ConnectionFactory |
| Kết quả findById không có giá trị | Không có hàng phù hợp | Dùng switchIfEmpty hoặc xử lý Mono rỗng |
| Tải quá nhiều dữ liệu | Dùng findAll trên bảng lớn rồi collectList | Lọc, giới hạn, sắp xếp hoặc phân trang phù hợp |

## 15. Quy trình khai báo repository mới

Khi thêm repository trong Spring Data R2DBC, có thể làm theo thứ tự:

1. Xác định entity/aggregate root cần truy cập.
2. Đảm bảo entity có mapping metadata đúng, đặc biệt là @Id và tên bảng/cột.
3. Chọn kiểu ID chính xác theo thuộc tính định danh.
4. Chọn ReactiveCrudRepository nếu chỉ cần CRUD reactive.
5. Chọn R2dbcRepository nếu cần thêm sorting repository contract.
6. Khai báo query methods cho các điều kiện đơn giản và thường dùng.
7. Dùng @Query hoặc repository fragment cho truy vấn SQL đặc thù.
8. Bảo đảm các method trả về Mono/Flux hoặc kiểu reactive phù hợp.
9. Kiểm tra repository được scan và tạo bean.
10. Kiểm tra ConnectionFactory, driver và transaction manager.
11. Viết integration test cho CRUD, query method và các trường hợp không có kết quả.
12. Kiểm tra truy vấn thực tế với schema và database mà ứng dụng triển khai.

## 16. Bài tập tự kiểm tra

### Bài 1: Khai báo repository cơ bản

Entity Customer có ID kiểu Long. Hãy khai báo repository chỉ cần CRUD reactive.

Gợi ý:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {
}
~~~

### Bài 2: Chọn R2dbcRepository

Bạn cần CRUD và findAll(Sort). Nên dùng interface nào?

Gợi ý: R2dbcRepository cung cấp CRUD reactive và sorting contract. Có thể dùng findAll(Sort) để sắp xếp theo property của entity.

### Bài 3: Chọn kiểu trả về

Một method tìm khách hàng theo email, với điều kiện email là duy nhất. Nên trả về Mono<Customer> hay Flux<Customer>?

Gợi ý: Mono<Customer> thể hiện tối đa một kết quả. Cần có unique constraint ở database để bảo đảm email thực sự duy nhất.

### Bài 4: Tìm theo điều kiện

Viết query method tìm đơn hàng theo customerId và sắp xếp createdAt giảm dần.

Gợi ý:

~~~java
Flux<Order> findByCustomerIdOrderByCreatedAtDesc(Long customerId);
~~~

### Bài 5: Xử lý không tìm thấy

findById có thể không phát ra entity. Hãy chuyển trường hợp rỗng thành lỗi nghiệp vụ.

Gợi ý:

~~~java
return customerRepository.findById(id)
    .switchIfEmpty(Mono.error(
        new CustomerNotFoundException(id)
    ));
~~~

### Bài 6: Tránh subscription thủ công

Một service gọi repository.save(customer).subscribe() rồi trả Mono<Void>. Vì sao cách này không phù hợp?

Gợi ý: subscribe() khởi động một luồng độc lập, khiến framework khó quản lý vòng đời và transaction của toàn pipeline. Hãy trả publisher từ repository và nối vào pipeline của service.

## 17. Ghi nhớ

- ReactiveCrudRepository cung cấp các thao tác CRUD reactive dựa trên entity và kiểu ID.
- R2dbcRepository là repository chuyên biệt cho R2DBC, kết hợp CRUD reactive với sorting repository contract.
- T và ID trong generic phải khớp entity type và kiểu thuộc tính @Id.
- Các thao tác đọc/trả kết quả dùng Mono hoặc Flux; thao tác xóa thường dùng Mono<Void>.
- Query method có thể được suy ra từ tên method, nhưng keyword và khả năng hỗ trợ cần đối chiếu phiên bản Spring Data R2DBC.
- @Query cho phép viết SQL trực tiếp; SQL thủ công phải khớp schema và dùng parameter binding.
- Spring tạo repository implementation/proxy khi interface được phát hiện và cấu hình repository hợp lệ.
- Repository tập trung vào truy cập dữ liệu; service điều phối nghiệp vụ và transaction.
- Trong reactive pipeline, không tự subscribe() hoặc block() bên trong service.
- Nhiều repository cùng transaction cần dùng transaction manager và ConnectionFactory phù hợp.

Khi khai báo repository, hãy chọn interface nhỏ nhất đáp ứng nhu cầu, khai báo đúng entity và ID type, rồi bổ sung query method hoặc SQL tùy chỉnh khi cần. Giữ toàn bộ luồng truy cập dữ liệu ở dạng reactive để Spring có thể quản lý subscription, connection và transaction nhất quán.

