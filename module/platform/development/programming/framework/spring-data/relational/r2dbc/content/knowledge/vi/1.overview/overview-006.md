# Khi nào nên dùng R2DBC và khi nào nên cân nhắc JDBC

R2DBC và JDBC đều cho phép ứng dụng Java làm việc với cơ sở dữ liệu quan hệ. Khác biệt lớn nhất nằm ở cách chương trình chờ kết quả từ cơ sở dữ liệu:

- **JDBC** sử dụng mô hình đồng bộ và blocking. Luồng gọi thường chờ cho đến khi câu lệnh SQL hoàn tất rồi mới tiếp tục.
- **R2DBC** cung cấp API truy cập cơ sở dữ liệu theo mô hình reactive và non-blocking. Ứng dụng nhận kết quả dưới dạng publisher và có thể tiếp tục xử lý khi thao tác I/O hoàn tất.

Vì vậy, chọn R2DBC hay JDBC là quyết định về kiến trúc thực thi, cách tổ chức luồng xử lý, transaction và hệ sinh thái thư viện. R2DBC không phải lựa chọn mặc định cho mọi ứng dụng, cũng không tự làm cho câu SQL chạy nhanh hơn.

## 1. Hiểu đúng JDBC, R2DBC và Spring Data Relational

### JDBC: API truy cập dữ liệu đồng bộ

JDBC là API tiêu chuẩn lâu đời của Java để kết nối và làm việc với cơ sở dữ liệu quan hệ. Khi gọi một phương thức như `executeQuery()`, luồng thực thi thường bị giữ lại trong lúc driver gửi câu lệnh, chờ database xử lý và nhận kết quả.

Ví dụ với Spring Data JDBC, repository thường trả về một đối tượng, `Optional`, `Iterable` hoặc `List`:

```java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    List<Customer> findByStatus(String status);
}
```

Lời gọi `findByStatus("ACTIVE")` hoàn tất theo cách đồng bộ: khi phương thức trả về, kết quả đã được lấy về và có thể sử dụng ngay.

### R2DBC: API truy cập dữ liệu reactive

R2DBC là viết tắt của *Reactive Relational Database Connectivity*. Đây là một SPI (Service Provider Interface) dành cho driver cơ sở dữ liệu quan hệ có khả năng hỗ trợ I/O non-blocking. Spring Data R2DBC xây dựng các tiện ích ánh xạ dữ liệu và repository trên nền SPI này.

Trong Spring Data R2DBC, repository thường trả về các kiểu Reactor:

- `Mono<T>` biểu diễn một kết quả có thể có hoặc không có.
- `Flux<T>` biểu diễn một chuỗi gồm không, một hoặc nhiều kết quả.

Ví dụ:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<Customer> findByStatus(String status);
}
```

Lời gọi `findByStatus("ACTIVE")` trả về một `Flux<Customer>`. Publisher mô tả quá trình lấy dữ liệu; kết quả được phát ra khi publisher được subscribe và thao tác bất đồng bộ hoàn tất. Vì thế, cần kết hợp các publisher trong pipeline thay vì giả định rằng dữ liệu đã có ngay sau khi gọi repository.

### Non-blocking không có nghĩa là không cần chờ

Ứng dụng vẫn phải chờ database xử lý truy vấn. Điểm khác biệt là trong lúc chờ I/O, mô hình non-blocking có thể giải phóng luồng để xử lý công việc khác, thay vì giữ một luồng bị chặn cho mỗi thao tác đang chờ.

Reactive Streams còn có cơ chế backpressure để bên tiêu thụ điều tiết lượng dữ liệu được phát ra. Khả năng streaming, cách driver lấy từng phần kết quả và mức độ hỗ trợ backpressure cụ thể vẫn phụ thuộc vào driver và database.

## 2. Khi nào nên chọn R2DBC?

R2DBC phù hợp nhất khi ứng dụng có lý do rõ ràng để xây dựng luồng xử lý reactive từ đầu đến cuối.

### 2.1. Ứng dụng đã sử dụng WebFlux và reactive stack

Nếu controller, service và các lời gọi I/O khác đều trả về `Mono` hoặc `Flux`, Spring Data R2DBC giúp thao tác database tham gia cùng pipeline đó.

Ví dụ, một request có thể gọi database, gọi một dịch vụ HTTP khác rồi kết hợp kết quả mà không cần chặn luồng tại từng bước:

```java
public Mono<CustomerView> getCustomerView(Long id) {
    Mono<Customer> customer = customerRepository.findById(id);
    Mono<Preference> preference = preferenceClient.getPreference(id);

    return Mono.zip(customer, preference)
            .map(tuple -> new CustomerView(tuple.getT1(), tuple.getT2()));
}
```

Đây là ví dụ minh họa cách kết hợp publisher. Trong ứng dụng thực tế, cần xử lý trường hợp một nguồn không có dữ liệu, lỗi hoặc timeout theo yêu cầu nghiệp vụ.

Nếu ứng dụng dùng Spring MVC theo kiểu imperative và mọi service đều blocking, chuyển riêng repository sang R2DBC thường không đem lại lợi ích tương xứng với chi phí thay đổi. Hãy đánh giá toàn bộ luồng request trước khi chọn reactive.

### 2.2. Có nhiều thao tác I/O đồng thời và thời gian chờ đáng kể

R2DBC đáng cân nhắc cho dịch vụ có nhiều request đồng thời, mỗi request thường phải chờ database hoặc các dịch vụ I/O khác. Với tải phù hợp, non-blocking I/O có thể giảm số luồng cần giữ trong lúc chờ và cải thiện khả năng sử dụng tài nguyên.

Ví dụ thường gặp:

- API gateway hoặc dịch vụ tổng hợp dữ liệu gọi nhiều nguồn.
- Dịch vụ có nhiều kết nối đồng thời và phần lớn thời gian request nằm ở I/O.
- Luồng xử lý dữ liệu cần phối hợp nhiều thao tác bất đồng bộ.
- API có nhu cầu phát dữ liệu theo luồng thay vì đợi tập kết quả hoàn chỉnh.

Điều này không đồng nghĩa R2DBC luôn có throughput cao hơn JDBC. Nếu database đã là nút thắt, truy vấn chậm, thiếu index hoặc connection pool bị quá tải, đổi API truy cập dữ liệu không giải quyết được nguyên nhân đó.

### 2.3. Muốn duy trì backpressure trong pipeline

Khi dữ liệu được xử lý qua nhiều bước reactive, backpressure giúp kiểm soát tốc độ phát và tiêu thụ dữ liệu giữa các thành phần. Điều này hữu ích với pipeline có nhiều bước xử lý bất đồng bộ hoặc có khả năng phát ra nhiều bản ghi.

Tuy nhiên, không nên mặc định rằng mọi truy vấn R2DBC đều truyền dữ liệu từng dòng từ database đến ứng dụng. Hành vi fetch và buffering còn phụ thuộc driver, cấu hình và loại truy vấn. Hãy kiểm tra tài liệu của driver đang sử dụng và đo mức sử dụng bộ nhớ với dữ liệu thực tế.

### 2.4. Database và driver có hỗ trợ phù hợp

Trước khi chọn R2DBC, xác nhận database mục tiêu có driver R2DBC phù hợp với phiên bản đang dùng. Kiểm tra các khả năng ứng dụng thực sự cần, chẳng hạn:

- Kiểu dữ liệu và phép ánh xạ dữ liệu đặc thù.
- Câu SQL, function, stored procedure hoặc tính năng riêng của database.
- Transaction, isolation level và locking.
- Connection pooling, timeout, retry và quan sát lỗi.
- Mức độ ổn định, bảo trì và tương thích của driver.

Hệ sinh thái R2DBC đã có nhiều driver hữu ích, nhưng độ trưởng thành và phạm vi tính năng không nhất thiết đồng đều với driver JDBC tương ứng.

## 3. Khi nào nên cân nhắc JDBC?

JDBC thường là lựa chọn hợp lý khi mô hình blocking phù hợp với ứng dụng và hệ sinh thái JDBC đáp ứng tốt yêu cầu.

### 3.1. Ứng dụng dùng Spring MVC và kiến trúc imperative

Với ứng dụng Spring MVC truyền thống, service gọi repository tuần tự và xử lý kết quả trực tiếp, JDBC thường đơn giản, dễ đọc và dễ bảo trì.

```java
public Customer getCustomer(Long id) {
    return customerRepository.findById(id)
            .orElseThrow(() -> new CustomerNotFoundException(id));
}
```

Không cần đưa `Mono` hoặc `Flux` vào mọi tầng nếu phần còn lại của ứng dụng không sử dụng reactive. Một mô hình đồng bộ rõ ràng có thể là lựa chọn tốt hơn cho nhóm phát triển và cách vận hành hiện tại.

### 3.2. Không có vấn đề về số luồng hoặc khả năng chịu tải

Nếu tải hiện tại nằm trong khả năng của thread pool, connection pool và database, chuyển sang R2DBC có thể làm tăng độ phức tạp mà không tạo ra lợi ích đo được.

Hãy giữ JDBC nếu số liệu cho thấy ứng dụng đáp ứng tốt yêu cầu về latency, throughput và tài nguyên. Chỉ nên thay đổi khi có vấn đề cụ thể mà kiến trúc reactive có thể giải quyết.

### 3.3. Cần hệ sinh thái JDBC hoặc tính năng ORM quen thuộc

JDBC có hệ sinh thái lâu đời và được hỗ trợ rộng rãi bởi nhiều thư viện, công cụ, driver và giải pháp quản trị database. Cân nhắc JDBC khi dự án phụ thuộc vào:

- Thư viện chỉ cung cấp API JDBC hoặc chỉ hỗ trợ blocking.
- Công cụ, driver hoặc tính năng đặc thù chưa có hỗ trợ R2DBC tương đương.
- Spring Data JPA/Hibernate với các tính năng ORM như dirty checking, lazy loading hoặc mapping quan hệ phức tạp.
- Mã nguồn JDBC hiện có đã ổn định và chi phí chuyển đổi lớn hơn lợi ích dự kiến.

Lưu ý: Spring Data JDBC và Spring Data R2DBC đều thuộc họ Spring Data Relational, nhưng không phải JPA/Hibernate. Spring Data R2DBC không tự cung cấp đầy đủ các tính năng ORM như dirty checking hoặc lazy loading. Nếu ứng dụng cần các tính năng đó, hãy đánh giá JPA/Hibernate và JDBC như một lựa chọn riêng.

### 3.4. Transaction và tích hợp hiện tại dựa trên JDBC

Nhiều ứng dụng đã tổ chức transaction theo mô hình imperative với `PlatformTransactionManager`, `JdbcTemplate`, Spring Data JDBC hoặc JPA. Nếu các ranh giới transaction, thư viện và quy trình vận hành đều dựa trên JDBC, tiếp tục dùng JDBC thường giúp giữ kiến trúc nhất quán.

R2DBC sử dụng reactive transaction manager và ngữ cảnh reactive. Việc chuyển đổi đòi hỏi kiểm tra lại cách transaction bắt đầu, truyền qua pipeline và kết thúc; không chỉ thay kiểu trả về của repository.

## 4. So sánh nhanh

| Tiêu chí | R2DBC | JDBC |
| --- | --- | --- |
| Mô hình I/O | Reactive, non-blocking khi driver hỗ trợ | Đồng bộ, blocking trong lúc chờ I/O |
| Kiểu kết quả phổ biến trong Spring Data | `Mono<T>`, `Flux<T>` | `T`, `Optional<T>`, `Iterable<T>`, `List<T>` |
| Cách kết hợp nhiều bước | Kết hợp publisher bằng toán tử reactive | Gọi tuần tự bằng lời gọi phương thức thông thường |
| Framework thường gặp | Spring WebFlux và reactive services | Spring MVC và ứng dụng imperative |
| Transaction | Reactive transaction manager, ngữ cảnh reactive | Platform transaction manager, thường gắn với thread |
| Driver | Cần driver R2DBC riêng | Hệ sinh thái JDBC rộng và lâu đời |
| ORM | Spring Data R2DBC ánh xạ aggregate; không phải JPA | Có thể dùng Spring Data JDBC, JPA/Hibernate hoặc JDBC API |
| Độ phức tạp | Cao hơn nếu nhóm chưa quen reactive | Thường dễ tiếp cận trong ứng dụng đồng bộ |
| Hiệu năng | Có thể tăng hiệu quả sử dụng luồng khi tải I/O đồng thời phù hợp | Đơn giản, hiệu quả tốt với nhiều ứng dụng thông thường |

Không có hàng nào trong bảng này bảo đảm một công nghệ luôn nhanh hơn. Kết quả thực tế phụ thuộc vào truy vấn, database, driver, pool, tải và cách triển khai.

## 5. Ví dụ cấu hình và repository

### 5.1. Cấu hình Spring Data R2DBC

Với Spring Boot, dependency thường gồm starter R2DBC và driver tương ứng. Ví dụ dùng PostgreSQL với Gradle:

```groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")
    runtimeOnly("org.postgresql:r2dbc-postgresql")
}
```

Cấu hình kết nối có thể đặt trong `application.properties`:

```properties
spring.r2dbc.url=r2dbc:postgresql://localhost:5432/shop
spring.r2dbc.username=app
spring.r2dbc.password=secret
```

Phiên bản driver nên được quản lý tương thích với phiên bản Spring Boot/Spring Data của dự án. Không dùng URL `jdbc:...` cho kết nối R2DBC; URL có scheme riêng theo driver, ví dụ `r2dbc:postgresql:...`.

### 5.2. Khai báo entity và reactive repository

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public class Customer {

    @Id
    private Long id;

    private String name;
    private String status;

    // Constructor, getter và setter được lược bớt.
}
```

Repository sử dụng `ReactiveCrudRepository`:

```java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<Customer> findByStatus(String status);

    Mono<Customer> findFirstByName(String name);
}
```

Service giữ nguyên kiểu reactive khi gọi repository:

```java
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Flux<Customer> findActiveCustomers() {
        return repository.findByStatus("ACTIVE");
    }

    public Mono<Customer> create(Customer customer) {
        return repository.save(customer);
    }
}
```

Controller WebFlux có thể trả trực tiếp publisher:

```java
@RestController
@RequestMapping("/customers")
public class CustomerController {

    private final CustomerService service;

    public CustomerController(CustomerService service) {
        this.service = service;
    }

    @GetMapping
    public Flux<Customer> findActive() {
        return service.findActiveCustomers();
    }

    @PostMapping
    public Mono<Customer> create(@RequestBody Customer customer) {
        return service.create(customer);
    }
}
```

Trong pipeline này, controller không cần gọi `.block()` để lấy dữ liệu. Framework subscribe và ghi kết quả HTTP theo cơ chế reactive.

### 5.3. Cùng nghiệp vụ với Spring Data JDBC

Nếu ứng dụng chọn Spring Data JDBC, dependency và cấu hình kết nối sẽ dùng starter JDBC và datasource JDBC. Repository có thể trông như sau:

```java
import org.springframework.data.repository.CrudRepository;
import java.util.List;

public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    List<Customer> findByStatus(String status);
}
```

Lời gọi repository trả về dữ liệu đồng bộ. Service có thể xử lý trực tiếp:

```java
public List<Customer> findActiveCustomers() {
    return repository.findByStatus("ACTIVE");
}
```

Hai ví dụ có cùng mục tiêu nghiệp vụ, nhưng repository, kiểu trả về, cấu hình connection và transaction manager thuộc hai stack khác nhau. Khi chọn một stack, nên giữ nhất quán qua các tầng của ứng dụng.

## 6. Những khác biệt cần chú ý khi dùng R2DBC

### 6.1. Không gọi `block()` trong reactive request path

`block()` biến lời gọi reactive thành lời gọi đồng bộ bằng cách chờ kết quả. Nếu gọi trên event-loop thread của WebFlux, nó có thể chặn luồng chịu trách nhiệm xử lý nhiều request và làm mất lợi ích của non-blocking I/O.

Thay vì:

```java
Customer customer = customerRepository.findById(id).block();
```

hãy giữ kết quả ở dạng publisher và kết hợp bằng `map`, `flatMap`, `zip` hoặc toán tử phù hợp:

```java
public Mono<CustomerView> getView(Long id) {
    return customerRepository.findById(id)
            .flatMap(customer -> preferenceClient.getPreference(id)
                    .map(preference -> new CustomerView(customer, preference)));
}
```

Nếu phải tích hợp một thư viện blocking, cần cô lập phần blocking trên scheduler phù hợp và giới hạn mức đồng thời. Đây là giải pháp tương thích có chủ đích, không biến thư viện blocking thành non-blocking.

### 6.2. Transaction reactive có cách truyền ngữ cảnh riêng

Với JDBC, transaction thường gắn với thread thực thi. Với R2DBC, transaction reactive được quản lý qua reactive context để có thể đi theo chuỗi publisher dù các bước không nhất thiết chạy trên cùng một thread.

Khi dùng `@Transactional` cho luồng R2DBC, cần bảo đảm phương thức trả về publisher và ứng dụng có reactive transaction manager phù hợp. Có thể dùng `TransactionalOperator` khi muốn biểu diễn ranh giới transaction trực tiếp trong pipeline.

Không nên gọi `.block()` giữa transaction reactive hoặc tách một bước ra khỏi pipeline rồi giả định transaction vẫn được giữ. Cũng không nên mặc định một transaction manager có thể bao phủ đồng thời thao tác JDBC và R2DBC; hai stack thường có connection factory, connection pool và transaction manager riêng.

### 6.3. Spring Data R2DBC không phải JPA reactive

R2DBC cung cấp truy cập SQL reactive cho cơ sở dữ liệu quan hệ. Spring Data R2DBC tập trung vào ánh xạ dữ liệu và aggregate theo cách tiếp cận Spring Data Relational.

Không nên kỳ vọng có đầy đủ các tính năng thường thấy ở JPA/Hibernate như:

- Persistence context theo dõi thay đổi đối tượng và dirty checking.
- Lazy loading tự động cho quan hệ entity.
- Cơ chế cascade và entity graph giống JPA.
- Thay đổi một field rồi tự động flush toàn bộ object graph.

Thiết kế aggregate, câu truy vấn và thao tác lưu dữ liệu cần được thể hiện rõ trong ứng dụng. Nếu dự án phụ thuộc sâu vào mô hình ORM của JPA, hãy đánh giá lại lợi ích của việc chuyển sang R2DBC.

### 6.4. Quản lý connection pool và mức đồng thời

Non-blocking cho phép ứng dụng xử lý nhiều thao tác đang chờ I/O, nhưng database vẫn có giới hạn về connection, CPU, bộ nhớ và năng lực xử lý truy vấn. Tăng concurrency vô hạn có thể làm pool cạn, tăng hàng đợi hoặc khiến database quá tải.

Khi vận hành, cần theo dõi ít nhất:

- Số connection đang dùng, connection nhàn rỗi và thời gian chờ lấy connection.
- Latency truy vấn, timeout, lỗi kết nối và số lần retry.
- Throughput, số request đồng thời và độ dài hàng đợi.
- CPU, bộ nhớ và tải của database.

Đặt giới hạn đồng thời phù hợp với năng lực database và connection pool. Với các toán tử như `flatMap`, cân nhắc giới hạn concurrency nếu pipeline có thể phát sinh nhiều truy vấn cùng lúc.

## 7. Có nên kết hợp JDBC và R2DBC trong cùng ứng dụng?

Có thể tồn tại cả hai stack trong một ứng dụng, ví dụ một module cũ vẫn dùng JDBC trong khi một luồng mới dùng WebFlux và R2DBC. Tuy nhiên, cần thiết kế ranh giới rõ ràng:

1. Mỗi stack có cấu hình kết nối và pool phù hợp với driver của nó.
2. Xác định rõ transaction manager được dùng cho từng thao tác.
3. Không giả định transaction của JDBC tự động bao phủ thao tác R2DBC hoặc ngược lại.
4. Không gọi JDBC blocking trực tiếp trên event-loop thread.
5. Theo dõi tổng số connection của cả hai pool để tránh vượt giới hạn database.

Nếu một nghiệp vụ cần cập nhật nhiều tài nguyên thuộc hai stack, hãy thiết kế tính nhất quán dữ liệu và xử lý lỗi như một bài toán riêng. Một annotation `@Transactional` đơn lẻ không tự tạo ra transaction phân tán giữa hai connection độc lập.

Với hệ thống mới, chỉ nên dùng song song khi có nhu cầu cụ thể. Nếu không, chọn một mô hình truy cập dữ liệu chủ đạo sẽ giúp code, transaction và vận hành dễ hiểu hơn.

## 8. Cách đưa ra quyết định cho dự án

Trước khi chọn công nghệ, hãy trả lời lần lượt các câu hỏi sau:

1. Ứng dụng đang dùng Spring MVC hay Spring WebFlux? Các tầng service và client hiện tại là blocking hay reactive?
2. Vấn đề cần giải quyết là gì: thiếu khả năng chịu tải I/O, số luồng quá lớn, hay chỉ là mong muốn dùng công nghệ mới?
3. Database đang dùng có driver R2DBC phù hợp và hỗ trợ đầy đủ các tính năng dự án cần không?
4. Ứng dụng có phụ thuộc vào JPA/Hibernate, thư viện JDBC hoặc stored procedure đặc thù không?
5. Nhóm phát triển có kinh nghiệm với `Mono`, `Flux`, backpressure, reactive error handling và reactive transaction không?
6. Đã có benchmark hoặc số liệu production chứng minh JDBC là điểm nghẽn chưa?

Có thể áp dụng quy tắc định hướng sau:

| Tình huống | Hướng lựa chọn ban đầu |
| --- | --- |
| Ứng dụng WebFlux, các tầng I/O đều reactive, driver hỗ trợ tốt | Ưu tiên đánh giá R2DBC |
| Ứng dụng Spring MVC, service và repository đồng bộ | Ưu tiên JDBC |
| Dự án cần tính năng JPA/Hibernate | Ưu tiên stack JDBC cùng JPA/Hibernate |
| Tải I/O đồng thời cao và JDBC đã được đo là giới hạn về tài nguyên luồng | Thử nghiệm R2DBC bằng benchmark thực tế |
| Driver R2DBC thiếu tính năng database quan trọng | Dùng JDBC hoặc giữ giải pháp hiện tại |
| Ứng dụng đang ổn định, chưa có vấn đề hiệu năng được đo lường | Tiếp tục dùng stack hiện tại |

Nếu quyết định chuyển đổi, nên thử trên một luồng nghiệp vụ có thể đo lường. So sánh cùng dữ liệu, cùng truy vấn và cùng mức tải; đo latency p50/p95/p99, throughput, CPU, bộ nhớ, số connection, timeout và tỷ lệ lỗi. Kiểm tra cả hành vi transaction và các tình huống lỗi, không chỉ đo một truy vấn CRUD đơn giản.

## 9. Kết luận

Chọn **R2DBC** khi ứng dụng thực sự cần mô hình reactive, có nhiều I/O đồng thời, các tầng xử lý có thể giữ non-blocking từ đầu đến cuối và driver đáp ứng yêu cầu database. Chọn **JDBC** khi kiến trúc imperative đang phù hợp, hệ sinh thái JDBC đáp ứng tốt hoặc dự án cần các thư viện và tính năng dựa trên JDBC/JPA.

Quyết định tốt nhất dựa trên kiến trúc hiện tại, yêu cầu nghiệp vụ, khả năng của driver và số liệu tải thực tế. Đừng chuyển sang R2DBC chỉ vì kỳ vọng rằng non-blocking sẽ tự động làm mọi truy vấn nhanh hơn.
