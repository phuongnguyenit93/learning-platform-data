# Spring Data R2DBC là gì và giải quyết bài toán nào?

## 1. Bối cảnh: truy cập cơ sở dữ liệu trong ứng dụng Spring

Phần lớn ứng dụng nghiệp vụ lưu dữ liệu trong cơ sở dữ liệu quan hệ như PostgreSQL, MySQL, MariaDB, SQL Server hoặc Oracle. Ứng dụng cần thực hiện các thao tác quen thuộc: tìm một bản ghi, lọc danh sách, thêm mới, cập nhật, xóa và chạy câu lệnh SQL có điều kiện.

Trong hệ sinh thái Spring, có nhiều cách để thực hiện những thao tác đó. JDBC là lựa chọn lâu đời và phổ biến. Spring Data JPA cung cấp mô hình ORM trên JDBC. Spring Data JDBC cung cấp cách ánh xạ dữ liệu quan hệ đơn giản hơn JPA. Còn **Spring Data R2DBC** phục vụ trường hợp ứng dụng muốn truy cập cơ sở dữ liệu quan hệ theo mô hình reactive, với I/O không chặn (non-blocking).

Spring Data R2DBC thuộc hệ sinh thái Spring Data Relational. Nó giữ lại nhiều ý tưởng quen thuộc của Spring Data như ánh xạ entity, repository, truy vấn theo tên phương thức và template, nhưng sử dụng R2DBC để giao tiếp với cơ sở dữ liệu.

## 2. Spring Data R2DBC là gì?

**Spring Data R2DBC là bộ thư viện của Spring Data giúp làm việc với cơ sở dữ liệu quan hệ thông qua R2DBC, theo mô hình reactive và non-blocking.** Thư viện cung cấp các lớp trừu tượng để ứng dụng thao tác với dữ liệu bằng entity, repository hoặc API truy vấn cấp thấp hơn mà không phải tự quản lý toàn bộ vòng đời kết nối và ánh xạ kết quả.

Có thể phân biệt hai thành phần trong tên gọi:

- **R2DBC (Reactive Relational Database Connectivity)** là một đặc tả SPI (Service Provider Interface) cho phép ứng dụng truy cập cơ sở dữ liệu quan hệ theo hướng reactive. Các nhà cung cấp cơ sở dữ liệu triển khai driver tương thích với đặc tả này.
- **Spring Data R2DBC** xây dựng các tiện ích ở tầng Spring trên R2DBC SPI, chẳng hạn ánh xạ hàng dữ liệu thành đối tượng, repository, phương thức truy vấn, template và tích hợp giao dịch.

R2DBC không phải là một lớp bọc biến JDBC thành non-blocking. Ứng dụng cần sử dụng driver R2DBC thực sự của hệ quản trị cơ sở dữ liệu. Nếu gọi JDBC rồi đưa lời gọi đó vào một publisher, thao tác I/O vẫn là blocking; chỉ có cách tổ chức mã bên ngoài được thay đổi.

Trong ứng dụng Spring Boot, Spring Data R2DBC thường được dùng cùng Spring WebFlux hoặc những thành phần khác đã cung cấp API reactive. Khi đó, luồng xử lý từ HTTP request đến truy vấn dữ liệu có thể duy trì mô hình non-blocking xuyên suốt.

## 3. Bài toán cốt lõi: luồng xử lý bị giữ lại trong lúc chờ I/O

### 3.1. Cách truy cập blocking với JDBC

Với JDBC, một lời gọi truy vấn thông thường là lời gọi đồng bộ. Khi ứng dụng gọi **executeQuery()**, luồng đang thực hiện lời gọi thường phải chờ cho đến khi nhận được kết quả hoặc lỗi từ cơ sở dữ liệu.

Ví dụ, một request cần đọc thông tin khách hàng:

~~~text
HTTP request
    |
    v
Servlet worker thread
    |
    v
JDBC query --------------------> Database
    |                              |
    |       thread chờ kết quả     |
    |<-----------------------------|
    v
Xử lý kết quả và trả response
~~~

Trong thời gian cơ sở dữ liệu xử lý truy vấn hoặc dữ liệu truyền qua mạng, worker thread vẫn bị chiếm dụng. Với tải thấp, điều này thường không gây vấn đề đáng kể. Nhưng khi có nhiều request đồng thời và phần lớn thời gian dành cho việc chờ I/O, số lượng thread cần thiết có thể tăng lên.

Thread không phải tài nguyên vô hạn. Mỗi thread tiêu thụ bộ nhớ và có chi phí lập lịch. Khi thread pool cạn, request mới phải chờ đến lượt. Tăng số thread có thể giúp một phần trong ngắn hạn, nhưng cũng làm tăng chi phí bộ nhớ và chuyển đổi ngữ cảnh. Nếu cơ sở dữ liệu đã quá tải, tăng thread còn có thể khiến áp lực lên database lớn hơn.

Đây là vấn đề về **khả năng sử dụng tài nguyên khi có nhiều thao tác I/O đồng thời**, không nhất thiết là vấn đề về tốc độ thực thi của một câu SQL riêng lẻ.

### 3.2. Cách tiếp cận non-blocking với R2DBC

Với R2DBC, driver cung cấp API reactive. Thay vì giữ luồng gọi lại trong lúc chờ kết quả, thao tác I/O được đăng ký và kết quả được phát ra khi sẵn sàng. Trong thời gian chờ, luồng xử lý có thể phục vụ công việc khác.

~~~text
HTTP request
    |
    v
Reactive event loop
    |
    v
R2DBC query --------------------> Database
    |                              |
    | luồng không phải chờ đồng bộ |
    |                              |
    |<------ tín hiệu kết quả -----|
    v
Tiếp tục pipeline reactive
    |
    v
Trả response
~~~

Điểm khác biệt quan trọng là **luồng không bị giữ chỉ để chờ phản hồi I/O**. Một số ít event-loop thread có thể điều phối nhiều thao tác đang chờ đồng thời. Khi kết quả về, pipeline tiếp tục xử lý theo cơ chế reactive.

Điều đó có thể giúp ứng dụng sử dụng thread và bộ nhớ hiệu quả hơn trong workload có nhiều thao tác I/O đồng thời. Tuy nhiên, non-blocking không làm cho câu SQL tự nhiên chạy nhanh hơn, không tăng năng lực xử lý của database và cũng không bảo đảm mọi ứng dụng sẽ có throughput cao hơn. Hiệu quả phụ thuộc vào driver, connection pool, truy vấn, cấu hình và toàn bộ chuỗi xử lý.

## 4. R2DBC hoạt động như thế nào trong Spring Data?

Một luồng truy cập dữ liệu điển hình có thể hình dung như sau:

~~~text
Service / WebFlux Controller
          |
          v
Spring Data Repository
          |
          v
Mapping và chuyển đổi tham số
          |
          v
R2dbcEntityTemplate / DatabaseClient
          |
          v
R2DBC SPI
          |
          v
R2DBC Driver của database
          |
          v
Relational Database
~~~

Các thành phần chính gồm:

| Thành phần | Vai trò |
|---|---|
| R2DBC driver | Thực hiện giao tiếp reactive với hệ quản trị cơ sở dữ liệu cụ thể |
| ConnectionFactory | Cung cấp kết nối R2DBC; thường được cấu hình tự động từ URL và thông tin kết nối |
| Spring Data mapping | Ánh xạ hàng dữ liệu và cột thành object, cũng như ánh xạ object thành dữ liệu ghi |
| ReactiveCrudRepository | Cung cấp các thao tác CRUD trả về kiểu reactive |
| R2dbcEntityTemplate | Cung cấp API thao tác entity linh hoạt hơn repository |
| DatabaseClient | Cho phép thực thi SQL và đọc kết quả ở mức thấp hơn |
| R2dbcTransactionManager | Quản lý giao dịch reactive trên kết nối R2DBC |

Spring Boot có thể tự cấu hình các thành phần kết nối khi ứng dụng khai báo starter và driver phù hợp. Người phát triển tập trung vào entity, repository và luồng nghiệp vụ thay vì tự tạo kết nối cho từng truy vấn.

## 5. Reactive type: Mono, Flux và luồng dữ liệu

Spring Data R2DBC thường sử dụng Reactor, thư viện reactive phổ biến trong hệ sinh thái Spring.

- **Mono<T>** biểu diễn một kết quả bất đồng bộ có thể không có giá trị hoặc có một giá trị, chẳng hạn tìm một khách hàng theo ID hoặc lưu một bản ghi.
- **Flux<T>** biểu diễn một chuỗi bất đồng bộ có thể phát ra không, một hoặc nhiều phần tử, chẳng hạn danh sách khách hàng hoặc kết quả truy vấn nhiều dòng.

Hai kiểu này là các implementation của Reactive Streams **Publisher**. Chúng mô tả một pipeline xử lý; việc thực thi thường bắt đầu khi có subscriber đăng ký. Vì vậy, chỉ tạo một Mono hoặc Flux chưa có nghĩa là truy vấn đã được chạy.

Ví dụ:

~~~java
Mono<Customer> customer = customerRepository.findById(42L);
Flux<Customer> customers = customerRepository.findByStatus("ACTIVE");
~~~

Mono và Flux cũng cho phép ghép các bước bất đồng bộ:

~~~java
return customerRepository.findById(customerId)
        .flatMap(customer -> orderRepository.findLatestByCustomerId(customer.getId()));
~~~

Ở ví dụ trên, truy vấn đơn hàng chỉ được thực hiện sau khi truy vấn khách hàng phát ra kết quả. **flatMap** giúp nối hai thao tác reactive mà không cần chặn luồng để lấy giá trị từ thao tác thứ nhất.

Reactive Streams còn có khái niệm **backpressure**: subscriber có thể biểu đạt nhu cầu nhận dữ liệu, giúp điều tiết tốc độ phát và tiêu thụ phần tử giữa các thành phần trong pipeline. Điều này hữu ích khi xử lý tập kết quả lớn hoặc khi các bước downstream có tốc độ xử lý khác nhau. Mức độ streaming thực tế còn phụ thuộc vào khả năng của driver và database; không nên mặc định mọi truy vấn đều được tải từng dòng theo cùng một cách.

## 6. Ví dụ Spring Data R2DBC với PostgreSQL

Ví dụ dưới đây minh họa cách khai báo dependency, cấu hình kết nối, ánh xạ entity và tạo repository. Cấu hình thực tế cần dùng phiên bản Spring Boot, Spring Data và driver tương thích với nhau.

### 6.1. Khai báo dependency

Với Gradle Groovy DSL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-r2dbc'
    runtimeOnly 'org.postgresql:r2dbc-postgresql'
}
~~~

Starter cung cấp tích hợp Spring Data R2DBC. Driver PostgreSQL cung cấp khả năng giao tiếp R2DBC với PostgreSQL. Nếu sử dụng MySQL hoặc hệ quản trị khác, cần chọn driver R2DBC tương ứng và kiểm tra mức độ hỗ trợ của driver đó.

### 6.2. Cấu hình kết nối

Ví dụ trong application.properties:

~~~properties
spring.r2dbc.url=r2dbc:postgresql://localhost:5432/app
spring.r2dbc.username=${DB_USER}
spring.r2dbc.password=${DB_PASSWORD}
~~~

URL R2DBC có scheme riêng, ở đây là **r2dbc:postgresql**. Tên người dùng và mật khẩu nên được truyền qua biến môi trường hoặc hệ thống quản lý secret thay vì ghi trực tiếp thông tin nhạy cảm vào source code.

Spring Boot có thể dùng các thuộc tính này để tạo ConnectionFactory và cấu hình những bean liên quan. Nếu cần connection pool, ứng dụng phải sử dụng cấu hình hoặc thư viện pool R2DBC tương thích; pool có giới hạn kết nối và cần được điều chỉnh theo năng lực của database.

### 6.3. Khai báo entity

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public record Customer(
        @Id Long id,
        String name,
        String email,
        String status
) {}
~~~

**@Table** xác định bảng tương ứng trong database. **@Id** đánh dấu trường khóa chính. Spring Data sử dụng metadata ánh xạ để chuyển đổi giữa hàng dữ liệu và đối tượng Customer.

Ví dụ dùng Java record để mã ngắn gọn. Có thể dùng class thông thường với constructor, getter và setter nếu phù hợp với mô hình ứng dụng. Tên trường và kiểu dữ liệu cần tương thích với schema hoặc được cấu hình mapping rõ ràng khi tên cột, kiểu dữ liệu khác quy ước.

### 6.4. Tạo repository reactive

~~~java
import org.springframework.data.r2dbc.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<Customer> findByStatus(String status);

    @Query("""
        SELECT id, name, email, status
        FROM customers
        WHERE status = :status
        ORDER BY id
        """)
    Flux<Customer> findCustomersByStatus(@Param("status") String status);
}
~~~

Kế thừa **ReactiveCrudRepository<Customer, Long>** giúp repository có sẵn những thao tác như:

- **save(entity)** để lưu một entity.
- **findById(id)** để tìm theo khóa chính.
- **findAll()** để lấy các entity.
- **existsById(id)** để kiểm tra sự tồn tại.
- **deleteById(id)** để xóa theo khóa chính.

Các phương thức trả về Mono hoặc Flux, do đó có thể được ghép vào pipeline reactive. Spring Data cũng hỗ trợ derived query như **findByStatus**, trong đó tên phương thức được dùng để suy ra điều kiện truy vấn. Khi cần kiểm soát SQL cụ thể, có thể dùng **@Query**.

### 6.5. Dùng repository trong service

~~~java
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class CustomerService {

    private final CustomerRepository customerRepository;

    public CustomerService(CustomerRepository customerRepository) {
        this.customerRepository = customerRepository;
    }

    public Mono<Customer> findById(Long id) {
        return customerRepository.findById(id);
    }

    public Flux<Customer> findActiveCustomers() {
        return customerRepository.findByStatus("ACTIVE");
    }

    public Mono<Customer> create(Customer customer) {
        return customerRepository.save(customer);
    }
}
~~~

Service trả lại Mono hoặc Flux để tầng gọi tiếp tục kết hợp với các thao tác khác. Nếu controller dùng Spring WebFlux, controller có thể trả trực tiếp những kiểu reactive này cho framework:

~~~java
@GetMapping("/{id}")
public Mono<Customer> getCustomer(@PathVariable Long id) {
    return customerService.findById(id);
}
~~~

Luồng xử lý được duy trì theo kiểu reactive từ controller đến repository. WebFlux có thể đăng ký và ghi response khi publisher phát ra dữ liệu.

## 7. Những API truy cập dữ liệu Spring Data R2DBC cung cấp

Không phải mọi thao tác đều cần được đặt trong repository. Spring Data R2DBC có một số mức trừu tượng để chọn theo nhu cầu.

### 7.1. Reactive repository

Repository phù hợp với các thao tác CRUD và truy vấn gắn với một aggregate hoặc entity. Ưu điểm là ít mã lặp, dễ kiểm thử và dễ đọc. Có thể dùng derived query hoặc **@Query** cho những câu SQL cụ thể.

### 7.2. R2dbcEntityTemplate

**R2dbcEntityTemplate** cung cấp API hướng entity cho những thao tác linh hoạt hơn repository. Nó hữu ích khi cần xây dựng truy vấn động, chọn điều kiện theo tham số hoặc thực hiện thao tác entity mà không muốn tự xử lý toàn bộ mapping.

### 7.3. DatabaseClient

**DatabaseClient** cho phép làm việc gần với SQL hơn. Người phát triển có thể thực thi câu SQL, bind tham số và ánh xạ kết quả. API này phù hợp khi câu truy vấn có cấu trúc phức tạp hoặc cần tận dụng tính năng riêng của hệ quản trị cơ sở dữ liệu.

Có thể chọn mức trừu tượng theo từng thao tác trong cùng một ứng dụng. Ví dụ, dùng repository cho CRUD thông thường và DatabaseClient cho một truy vấn báo cáo phức tạp. Dù chọn API nào, các thao tác I/O vẫn cần được giữ trong pipeline reactive nếu muốn duy trì tính non-blocking.

## 8. Spring Data R2DBC giải quyết tốt những trường hợp nào?

### 8.1. Ứng dụng có nhiều request đồng thời và thường xuyên chờ database

Nếu mỗi request dành phần lớn thời gian chờ database hoặc dịch vụ I/O khác, mô hình blocking có thể giữ nhiều thread trong trạng thái chờ. R2DBC giúp giải phóng luồng điều phối trong thời gian chờ truy vấn, từ đó có thể phục vụ nhiều thao tác đang diễn ra đồng thời với số lượng thread nhỏ hơn.

Điều này đặc biệt đáng cân nhắc với API có lượng truy cập lớn, nhiều request ngắn và tỷ lệ thời gian chờ I/O cao. Lợi ích phải được đo bằng tải thực tế vì database, connection pool và các thành phần khác vẫn có giới hạn riêng.

### 8.2. Ứng dụng đã sử dụng Spring WebFlux

WebFlux được thiết kế để xử lý request theo mô hình reactive. Nếu tầng web non-blocking nhưng tầng truy cập dữ liệu lại gọi JDBC blocking trực tiếp trên event loop, luồng xử lý có thể bị chặn và làm mất lợi ích của mô hình reactive.

Spring Data R2DBC cho phép tầng truy cập relational database trả về Mono và Flux, giúp nối tiếp pipeline của WebFlux. Các thành phần khác trong request path cũng cần tương thích non-blocking; một lời gọi blocking ở bất kỳ bước nào vẫn có thể làm nghẽn event loop.

### 8.3. Xử lý luồng kết quả bất đồng bộ

Một số nghiệp vụ cần xử lý tập dữ liệu lớn hoặc kết hợp nhiều thao tác I/O theo chuỗi. Flux cho phép biểu diễn tập kết quả như một luồng phần tử, kết hợp với các toán tử reactive để lọc, biến đổi hoặc gọi tiếp dịch vụ khác. Backpressure hỗ trợ điều tiết nhu cầu tiêu thụ trong pipeline.

Cần thiết kế truy vấn, phân trang và giới hạn dữ liệu phù hợp. Dùng Flux không tự động khiến một truy vấn lớn trở nên rẻ hoặc không giới hạn bộ nhớ; cách driver lấy dữ liệu và cách downstream xử lý vẫn rất quan trọng.

### 8.4. Kết hợp nhiều nguồn I/O trong một pipeline

Một request có thể cần đọc database, gọi HTTP service và ghi kết quả. Khi các thành phần đều cung cấp API reactive, có thể phối hợp chúng bằng các toán tử Reactor mà không phải chặn luồng ở mỗi bước. Spring Data R2DBC đóng vai trò là tầng truy cập relational database trong pipeline đó.

## 9. Spring Data R2DBC không giải quyết những vấn đề nào?

R2DBC thay đổi cách ứng dụng chờ và phối hợp I/O. Nó không thay thế trách nhiệm thiết kế database hoặc tối ưu câu SQL.

- **Không tự làm truy vấn nhanh hơn.** Index thiếu, kế hoạch thực thi kém, join tốn kém, khóa tranh chấp hoặc truy vấn trả quá nhiều dòng vẫn là vấn đề ở database.
- **Không tăng vô hạn số kết nối.** Connection pool, giới hạn kết nối của database và năng lực xử lý của máy chủ vẫn là các giới hạn cần quản lý.
- **Không làm công việc CPU-bound nhanh hơn.** Tính toán nặng, nén dữ liệu hoặc xử lý thuật toán vẫn tiêu thụ CPU; non-blocking I/O không loại bỏ chi phí đó.
- **Không tự biến thư viện blocking thành reactive.** Gọi JDBC, Thread.sleep hoặc một HTTP client blocking trên event loop vẫn chặn luồng. Những tích hợp blocking cần được thay bằng API non-blocking hoặc được cô lập trên scheduler phù hợp.
- **Không cung cấp đầy đủ mô hình ORM của JPA/Hibernate.** Spring Data R2DBC có mapping cho dữ liệu quan hệ, nhưng không có persistence context, dirty checking hay lazy-loading proxy theo cách JPA thường cung cấp.
- **Không bảo đảm tính năng giống nhau giữa mọi database.** Mức độ hỗ trợ kiểu dữ liệu, câu SQL, metadata và tính năng riêng phụ thuộc vào driver R2DBC cụ thể.

## 10. So sánh R2DBC, JDBC, Spring Data JDBC và JPA

Các công nghệ này đều có thể được dùng để truy cập cơ sở dữ liệu quan hệ, nhưng giải quyết những nhu cầu khác nhau.

| Tiêu chí | Spring Data R2DBC | JDBC / Spring Data JDBC | JPA / Hibernate |
|---|---|---|---|
| Mô hình I/O | Reactive, non-blocking khi dùng driver R2DBC tương thích | Blocking, đồng bộ theo lời gọi JDBC | Thông thường blocking qua JDBC |
| Kiểu trả về thường gặp | Mono, Flux | Object, Optional, List hoặc kiểu đồng bộ | Entity, Optional, List |
| Tích hợp tự nhiên | Spring WebFlux và pipeline reactive | Spring MVC và ứng dụng imperative | Ứng dụng imperative cần ORM |
| Mapping | Mapping relational của Spring Data | Mapping relational của Spring Data | ORM với persistence context |
| Lazy loading / dirty checking của JPA | Không cung cấp theo mô hình JPA | Không có persistence context của JPA | Có các cơ chế ORM tương ứng |
| Hệ sinh thái driver | Cần R2DBC driver cho database được chọn | JDBC driver rất phổ biến | Dựa trên JDBC driver |
| Độ phức tạp khi phát triển | Cần hiểu reactive và cách ghép publisher | Thường quen thuộc với lập trình đồng bộ | Cần hiểu trạng thái entity, quan hệ và vòng đời persistence context |

**Spring Data JDBC** và **Spring Data R2DBC** có chung định hướng mapping relational đơn giản hơn ORM đầy đủ, nhưng khác nhau ở cơ chế I/O. Spring Data R2DBC dùng R2DBC và reactive type; Spring Data JDBC dùng JDBC và API đồng bộ.

**JPA/Hibernate** phù hợp khi ứng dụng cần nhiều tính năng ORM như persistence context, dirty checking, quan hệ entity và lazy loading. Nếu yêu cầu chính là truy cập dữ liệu quan hệ theo mô hình non-blocking, JPA không phải lựa chọn tương đương trực tiếp với R2DBC.

Không nên chọn R2DBC chỉ vì muốn dùng công nghệ mới. Nếu ứng dụng hiện tại chạy Spring MVC, phần lớn thư viện là blocking và lưu lượng không tạo ra vấn đề về thread, JDBC hoặc JPA có thể đơn giản và phù hợp hơn.

## 11. Những điểm cần lưu ý khi triển khai

### 11.1. Giữ pipeline reactive xuyên suốt

Tránh gọi **block()** trong service hoặc controller đang chạy trên event loop. block() buộc luồng hiện tại chờ kết quả, làm mất lợi ích non-blocking và có thể gây nghẽn. Cũng tránh gọi **subscribe()** tùy tiện bên trong tầng nghiệp vụ vì việc tự đăng ký subscription có thể khiến luồng lỗi, hủy và vòng đời xử lý khó được quản lý.

Thông thường, hãy trả Mono hoặc Flux từ service để tầng gọi kết hợp pipeline. Chỉ có một điểm đăng ký subscription do framework hoặc thành phần điều phối chịu trách nhiệm.

### 11.2. Chú ý giới hạn connection pool

Non-blocking giúp một thread điều phối nhiều thao tác I/O, nhưng mỗi truy vấn vẫn cần tài nguyên kết nối trong lúc làm việc với database. Pool quá nhỏ có thể khiến nhiều truy vấn chờ lấy connection; pool quá lớn có thể đẩy database đến giới hạn. Cần theo dõi thời gian chờ connection, số kết nối đang dùng, thời gian truy vấn và mức tải của database để điều chỉnh.

### 11.3. Quản lý transaction theo reactive context

Spring Data R2DBC hỗ trợ giao dịch reactive thông qua **R2dbcTransactionManager** và cơ chế **@Transactional** của Spring. Với phương thức trả về Mono hoặc Flux, các thao tác trong transaction cần được ghép thành cùng một pipeline để transaction context được truyền đúng.

~~~java
@Transactional
public Mono<Void> performBusinessOperation() {
    return repository.updateFirstRecord()
            .then(repository.updateSecondRecord())
            .then();
}
~~~

Các thao tác được nối bằng then và publisher được trả về cho framework quản lý. Không nên tự subscribe() bên trong phương thức transactional, vì như vậy thao tác có thể chạy ngoài vòng đời transaction mà Spring đang quản lý. Cũng cần bảo đảm ứng dụng có transaction manager R2DBC phù hợp với ConnectionFactory.

### 11.4. Phân biệt reactive và blocking khi tích hợp thư viện

Nếu một thành phần chưa có API reactive, cần xác định rõ nó có blocking hay không. Không gọi trực tiếp thao tác blocking trên event-loop thread. Có thể thay bằng thư viện non-blocking tương ứng; nếu bắt buộc dùng thư viện blocking, cần cô lập thao tác trên scheduler dành cho công việc blocking và kiểm soát số lượng tác vụ.

### 11.5. Kiểm tra driver và tính năng database

Trước khi chọn R2DBC, cần kiểm tra driver của database mục tiêu có hỗ trợ phiên bản server, kiểu dữ liệu, câu SQL và tính năng mà ứng dụng cần hay không. Hành vi và mức độ hoàn thiện của driver có thể khác nhau giữa các nhà cung cấp. Các bài kiểm thử tích hợp với database thực tế hoặc Testcontainers giúp phát hiện khác biệt mà kiểm thử giả lập không thể hiện được.

### 11.6. Tách việc migration schema khỏi truy cập runtime

R2DBC tập trung vào truy cập dữ liệu trong ứng dụng. Quy trình tạo và thay đổi schema vẫn cần được quản lý bằng migration. Nhiều dự án dùng Flyway hoặc Liquibase trong một bước triển khai riêng; các công cụ này thường kết nối database qua JDBC. Điều đó không ngăn ứng dụng runtime dùng R2DBC, nhưng cần cấu hình và quản lý hai đường kết nối phù hợp nếu cả hai cùng xuất hiện trong dự án.

## 12. Khi nào nên chọn Spring Data R2DBC?

Có thể cân nhắc Spring Data R2DBC khi:

- Ứng dụng được xây dựng theo mô hình reactive, đặc biệt là Spring WebFlux.
- Workload có nhiều thao tác I/O đồng thời và thời gian chờ database chiếm tỷ trọng đáng kể.
- Database mục tiêu có R2DBC driver đáp ứng các tính năng cần dùng.
- Đội ngũ hiểu cách sử dụng Mono, Flux, Reactor Context, backpressure và transaction reactive.
- Các thành phần quan trọng khác trong request path cũng có API non-blocking.

JDBC, Spring Data JDBC hoặc JPA thường là lựa chọn hợp lý hơn khi ứng dụng dùng mô hình imperative, thư viện phụ thuộc chủ yếu là blocking, cần hệ sinh thái JDBC rộng hoặc cần tính năng ORM của JPA. Việc chuyển một ứng dụng đang ổn định sang R2DBC chỉ có ý nghĩa khi lợi ích về khả năng xử lý đồng thời đủ lớn để bù cho chi phí thay đổi và độ phức tạp reactive.

## 13. Kết luận

Spring Data R2DBC cung cấp cách làm việc với cơ sở dữ liệu quan hệ theo mô hình reactive trong hệ sinh thái Spring. Nó giải quyết bài toán giữ thread trong lúc chờ I/O bằng cách sử dụng R2DBC driver non-blocking và các kiểu reactive như Mono và Flux. Nhờ đó, ứng dụng có thể phối hợp nhiều thao tác I/O đồng thời và tích hợp tự nhiên với Spring WebFlux.

Giá trị của R2DBC nằm ở cách sử dụng tài nguyên khi chờ I/O và khả năng kết hợp pipeline reactive. Nó không thay thế việc tối ưu SQL, thiết kế schema, quản lý connection pool hay kiểm soát tải database. Quyết định sử dụng nên dựa trên kiến trúc tổng thể, workload, driver hỗ trợ và năng lực vận hành reactive của đội ngũ.

