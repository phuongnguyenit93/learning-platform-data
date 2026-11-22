# Lộ trình học và các kiến thức cần chuẩn bị

Spring Data Relational R2DBC giúp ứng dụng Java làm việc với cơ sở dữ liệu quan hệ thông qua API reactive, phù hợp với những hệ thống cần xử lý I/O bất đồng bộ và luồng dữ liệu không chặn. Để học hiệu quả, cần hiểu cả mô hình dữ liệu quan hệ, cách Spring Data ánh xạ dữ liệu và cách Reactor vận hành luồng reactive. Chỉ ghi nhớ tên annotation hoặc cách khai báo repository là chưa đủ: phần khó nhất thường nằm ở việc hiểu vòng đời của một luồng reactive, ranh giới giao dịch và cách tổ chức truy vấn.

Lộ trình dưới đây đi từ nền tảng đến khả năng xây dựng một ứng dụng có thể vận hành. Có thể bỏ qua những phần đã thành thạo, nhưng nên giữ thứ tự phụ thuộc giữa SQL, reactive programming, R2DBC và Spring Data R2DBC.

## 1. Hiểu vị trí của R2DBC trong ứng dụng Spring

R2DBC là viết tắt của *Reactive Relational Database Connectivity*. Đây là một đặc tả để ứng dụng Java truy cập cơ sở dữ liệu quan hệ theo mô hình reactive. Các driver R2DBC triển khai đặc tả này cho từng hệ quản trị cơ sở dữ liệu, chẳng hạn PostgreSQL, Microsoft SQL Server, MySQL hoặc H2. Spring Data R2DBC cung cấp lớp tích hợp ở mức cao hơn: ánh xạ đối tượng, repository, truy vấn và hỗ trợ giao dịch reactive.

Có thể hình dung các lớp trong một ứng dụng như sau:

```text
HTTP request / message / scheduled task
                 |
          Application service
                 |
       Spring Data R2DBC
       /               \
 Reactive Repository   DatabaseClient
       \               /
           R2DBC SPI
                |
        Database driver
                |
       Relational database
```

Mỗi lớp giải quyết một vấn đề khác nhau:

- **R2DBC SPI** định nghĩa hợp đồng kết nối, tạo câu lệnh, bind tham số và nhận kết quả bất đồng bộ.
- **R2DBC driver** chuyển các thao tác theo SPI thành giao tiếp cụ thể với một hệ quản trị cơ sở dữ liệu.
- **Spring Data Relational** cung cấp mô hình ánh xạ dữ liệu quan hệ và các quy tắc làm việc với aggregate.
- **Spring Data R2DBC** kết hợp mô hình Spring Data Relational với R2DBC, cung cấp repository reactive và API truy vấn mức thấp hơn.
- **Reactor** cung cấp các kiểu và toán tử reactive mà API của Spring Data R2DBC sử dụng, chủ yếu là `Mono` và `Flux`.

JDBC truyền thống thường thực hiện lời gọi cơ sở dữ liệu theo cách chặn luồng đang gọi cho đến khi có kết quả. R2DBC cung cấp API bất đồng bộ, không chặn ở tầng truy cập dữ liệu. Điều này có thể giúp ứng dụng phục vụ nhiều thao tác I/O đồng thời với tài nguyên luồng hiệu quả hơn, nhưng chỉ khi phần còn lại của đường xử lý cũng được thiết kế phù hợp. Một đoạn mã gọi `.block()` hoặc một thư viện JDBC chặn vẫn có thể làm nghẽn luồng xử lý.

Spring Data R2DBC không phải một bản sao reactive của JPA/Hibernate. Nó không cung cấp đầy đủ cơ chế ORM như persistence context, dirty checking, lazy loading hay quản lý quan hệ đối tượng tự động theo cách JPA thường làm. Người phát triển cần chủ động thiết kế truy vấn SQL, ranh giới aggregate và cách tải dữ liệu liên quan.

## 2. Kiến thức cần chuẩn bị

### 2.1. Java và công cụ phát triển

Trước khi học R2DBC, nên sử dụng Java ở mức có thể đọc, viết và gỡ lỗi một ứng dụng Spring thông thường. Phiên bản JDK cần tương thích với phiên bản Spring Boot được chọn.

Các nội dung Java nên nắm:

- Class, interface, enum, record, generic và annotation.
- Lambda expression, method reference và functional interface.
- Collection, `Optional`, exception và cách xử lý lỗi.
- Constructor injection và cách tổ chức package.
- Maven hoặc Gradle, quản lý dependency và cấu hình môi trường chạy.
- Đọc stack trace, đặt breakpoint và sử dụng log để tìm nguyên nhân lỗi.

Không cần biết sâu về lập trình đa luồng ngay từ đầu, nhưng nên hiểu thread, blocking I/O, concurrency và vì sao một thao tác I/O chậm có thể chiếm tài nguyên xử lý.

### 2.2. Cơ sở dữ liệu quan hệ và SQL

Đây là nền tảng bắt buộc. R2DBC thay đổi cách ứng dụng gửi và nhận kết quả từ cơ sở dữ liệu; nó không thay thế kiến thức về mô hình quan hệ hay SQL.

Nên thành thạo các chủ đề sau:

| Chủ đề | Kiến thức cần nắm | Vì sao cần thiết |
|---|---|---|
| Mô hình quan hệ | Bảng, hàng, cột, kiểu dữ liệu, khóa chính và khóa ngoại | Hiểu dữ liệu được lưu và liên kết như thế nào |
| Thiết kế schema | Chuẩn hóa ở mức cơ bản, ràng buộc `NOT NULL`, `UNIQUE`, `CHECK` | Bảo vệ tính hợp lệ của dữ liệu ngay tại database |
| CRUD | `INSERT`, `SELECT`, `UPDATE`, `DELETE` | Hiểu thao tác mà repository thực hiện |
| Truy vấn | `WHERE`, `ORDER BY`, `GROUP BY`, `HAVING`, hàm tổng hợp | Xây dựng truy vấn theo yêu cầu nghiệp vụ |
| Kết hợp bảng | `JOIN`, quan hệ một-một, một-nhiều và nhiều-nhiều | Đọc và ghi dữ liệu qua nhiều bảng |
| Giao dịch | `COMMIT`, `ROLLBACK`, mức cô lập và khóa | Bảo đảm nhiều thao tác dữ liệu có tính nhất quán |
| Hiệu năng | Index, execution plan, phân trang và giới hạn kết quả | Tránh truy vấn chậm hoặc tải quá nhiều dữ liệu |

Hãy thực hành trực tiếp trên hệ quản trị cơ sở dữ liệu dự định dùng trong dự án. Cần biết cách tạo schema, chèn dữ liệu mẫu, chạy truy vấn và đọc lỗi SQL. Nếu chưa tự viết được một truy vấn `JOIN` đơn giản hoặc chưa hiểu khóa ngoại, nên củng cố SQL trước khi đi sâu vào Spring Data R2DBC.

### 2.3. Spring Framework và Spring Boot

Spring Data R2DBC nằm trong hệ sinh thái Spring. Người học nên hiểu các cơ chế nền tảng trước khi tìm hiểu cấu hình chuyên biệt cho database:

- IoC container, dependency injection và bean lifecycle ở mức cơ bản.
- Annotation cấu hình như `@Configuration`, `@Bean`, `@Component` và cách component scanning hoạt động.
- Cấu hình ứng dụng qua `application.yml` hoặc `application.properties`.
- Spring Boot auto-configuration và cách dependency trên classpath ảnh hưởng đến cấu hình.
- Constructor injection, phân lớp controller, service và repository.
- Quản lý profile, biến môi trường và thông tin kết nối.

Nếu chưa từng xây dựng ứng dụng Spring Boot, hãy làm một ứng dụng nhỏ có controller, service và một cấu hình bên ngoài trước. Việc này giúp phân biệt lỗi cấu hình Spring với lỗi kết nối R2DBC khi bắt đầu học database.

### 2.4. Reactive programming và Project Reactor

Đây là phần cần đầu tư thời gian nhiều nhất nếu trước đó chỉ làm việc với JDBC hoặc lập trình đồng bộ.

Spring Data R2DBC trả về các kiểu reactive của Reactor:

- `Mono<T>` biểu diễn một kết quả có thể phát ra không có giá trị hoặc tối đa một giá trị.
- `Flux<T>` biểu diễn một luồng có thể phát ra từ không đến nhiều giá trị.

Các publisher thường là lazy: việc mô tả pipeline chưa đồng nghĩa với việc thao tác đã chạy. Pipeline được thực thi khi có subscriber. Vì vậy, cần hiểu subscription, signal, completion, error và cách các toán tử kết hợp với nhau.

Các khái niệm Reactor nên học theo thứ tự:

1. Tạo và đọc `Mono` / `Flux`.
2. Biến đổi dữ liệu bằng `map` và `flatMap`.
3. Kết hợp nhiều publisher bằng `zip`, `concat` hoặc `merge` khi phù hợp.
4. Xử lý lỗi bằng `onErrorMap`, `onErrorResume` và các toán tử liên quan.
5. Hiểu `switchIfEmpty`, `defaultIfEmpty` và trường hợp publisher hoàn tất mà không phát giá trị.
6. Hiểu subscription, cancellation và backpressure ở mức đủ để dự đoán luồng dữ liệu.
7. Phân biệt thao tác đồng bộ, thao tác bất đồng bộ và thao tác blocking.

Ví dụ, hai thao tác truy vấn có thể được kết hợp thành một pipeline:

```java
Mono<Customer> customerMono = customerRepository.findById(customerId);

Mono<CustomerProfile> profileMono = customerMono.flatMap(customer ->
    addressRepository.findPrimaryByCustomerId(customer.id())
        .map(address -> new CustomerProfile(customer, address))
);
```

`flatMap` được dùng vì hàm bên trong trả về một publisher khác. Nếu dùng `map`, kết quả sẽ trở thành publisher lồng nhau, chẳng hạn `Mono<Mono<CustomerProfile>>`, thay vì một `Mono<CustomerProfile>`.

Hai thói quen cần hình thành sớm:

- Trong service, ưu tiên trả về `Mono` hoặc `Flux` để tầng gọi quyết định cách kết hợp và xử lý kết quả.
- Không gọi `subscribe()` tùy tiện trong controller hoặc service để tự khởi chạy tác vụ rồi bỏ luồng kết quả. Việc đó làm mất khả năng phối hợp lỗi, hoàn tất và vòng đời request của pipeline.

Tránh dùng `.block()` trong luồng xử lý reactive của ứng dụng, đặc biệt trên event-loop của Spring WebFlux. `.block()` có thể hữu ích ở một số ranh giới imperative hoặc trong đoạn kiểm thử phù hợp, nhưng không nên trở thành cách nối các bước trong service.

### 2.5. WebFlux và xử lý HTTP reactive

Spring WebFlux thường được dùng cùng Spring Data R2DBC để xây dựng đường xử lý không chặn từ HTTP đến database. Nên biết cách controller trả về `Mono` hoặc `Flux`, cách ánh xạ lỗi HTTP và cách truyền dữ liệu theo luồng.

WebFlux không phải điều kiện bắt buộc để sử dụng Spring Data R2DBC. Một ứng dụng có thể dùng R2DBC trong thành phần khác hoặc kết hợp với Spring MVC. Tuy vậy, nếu mục tiêu là một ứng dụng reactive end-to-end, cần hiểu WebFlux và tránh đưa các thao tác blocking vào cùng đường xử lý.

### 2.6. Kiến thức vận hành và kiểm thử

Khi đã làm được CRUD, cần bổ sung các kiến thức để ứng dụng hoạt động ổn định:

- Connection pool, giới hạn kết nối, timeout và cách đóng tài nguyên.
- Transaction reactive và cách truyền transaction context.
- Log, metrics và khả năng quan sát lỗi truy vấn.
- Kiểm thử publisher bằng `StepVerifier` thuộc `reactor-test`.
- Kiểm thử tích hợp với đúng loại database và driver dự kiến triển khai.
- Quản lý schema và migration theo quy trình triển khai của dự án.

## 3. Lộ trình học theo từng giai đoạn

### Giai đoạn 1: Ôn SQL và mô hình dữ liệu

**Mục tiêu:** Tự thiết kế được một schema nhỏ và viết truy vấn phục vụ yêu cầu nghiệp vụ.

Thực hành với một bài toán quen thuộc, ví dụ quản lý khách hàng và đơn hàng. Tạo bảng `customers`, `orders` và `order_items`; khai báo khóa chính, khóa ngoại và các ràng buộc cần thiết. Viết truy vấn lấy đơn hàng của một khách hàng, tổng tiền theo đơn và danh sách đơn hàng theo trạng thái.

Kết thúc giai đoạn này khi có thể giải thích quan hệ giữa các bảng, viết được `JOIN`, biết khi nào cần index và hiểu transaction bảo vệ một nhóm thao tác ghi như thế nào.

### Giai đoạn 2: Học Reactor trước khi dùng database reactive

**Mục tiêu:** Đọc và kết hợp publisher mà không cần dựa vào `block()`.

Tạo các ví dụ độc lập với database: chuyển đổi một giá trị thành `Mono`, xử lý danh sách bằng `Flux`, gọi hai nguồn dữ liệu giả lập và kết hợp kết quả, xử lý trường hợp rỗng và lỗi. Dùng `StepVerifier` để quan sát các signal mà publisher phát ra.

Kết thúc giai đoạn này khi có thể giải thích vì sao `map` khác `flatMap`, khi nào một pipeline được thực thi, và lỗi được truyền qua pipeline ra sao.

### Giai đoạn 3: Tìm hiểu R2DBC SPI và driver

**Mục tiêu:** Hiểu Spring Data đang sử dụng cơ chế nào để giao tiếp với database.

Tìm hiểu khái niệm `ConnectionFactory`, `Connection`, `Statement`, `Result` và việc bind tham số. Không cần bắt đầu bằng cách tự triển khai driver. Chỉ cần hiểu driver là thành phần kết nối đặc tả R2DBC với giao thức của database, và mỗi database có thể có mức hỗ trợ tính năng khác nhau.

Chọn một database cụ thể, thêm driver R2DBC tương ứng và xác nhận ứng dụng có thể kết nối. Nên dùng database gần với môi trường triển khai thực tế để sớm phát hiện khác biệt về kiểu dữ liệu, cú pháp SQL và hành vi driver.

### Giai đoạn 4: Làm CRUD với Spring Data R2DBC

**Mục tiêu:** Ánh xạ một bảng thành entity và thao tác qua reactive repository.

Học các thành phần chính:

- `@Table`, `@Id` và `@Column` để ánh xạ entity với bảng và cột.
- `ReactiveCrudRepository` để có các thao tác CRUD cơ bản.
- Derived query methods để tạo truy vấn từ tên phương thức.
- `@Query` để khai báo SQL khi cần kiểm soát truy vấn.
- `DatabaseClient` khi cần thao tác SQL ở mức thấp hơn repository.

Ví dụ entity và repository tối giản:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public record Customer(
    @Id Long id,
    String email,
    @Column("display_name") String displayName
) {}
```

```java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<Customer> findByEmailContaining(String keyword);
}
```

Repository trả về publisher; việc gọi phương thức chưa nhất thiết thực hiện truy vấn ngay. Khi kết hợp repository với service, tiếp tục truyền publisher qua các tầng thay vì chặn để lấy đối tượng.

### Giai đoạn 5: Truy vấn, aggregate và transaction

**Mục tiêu:** Xử lý các nghiệp vụ có nhiều bảng hoặc nhiều thao tác ghi một cách nhất quán.

Học cách viết truy vấn tùy chỉnh, bind tham số, ánh xạ kết quả và xử lý quan hệ giữa các bảng. Spring Data Relational tổ chức việc ghi dữ liệu quanh aggregate. Vì vậy, cần xác định aggregate root và ranh giới dữ liệu thuộc về một aggregate thay vì kỳ vọng ORM tự tải mọi quan hệ.

Với các truy vấn kết hợp nhiều bảng, hãy chủ động viết SQL phù hợp hoặc dùng `DatabaseClient`. Với nghiệp vụ cần nhiều thao tác ghi cùng thành công hoặc cùng thất bại, tìm hiểu `R2dbcTransactionManager`, `@Transactional` trên phương thức trả về publisher và `TransactionalOperator` cho trường hợp cần điều khiển bằng code.

Giao dịch reactive gắn với ngữ cảnh reactive. Không nên tách một bước trong transaction ra bằng cách tự `subscribe()` vì bước đó có thể không còn nằm trong cùng transaction context. Hãy kiểm thử cả trường hợp thành công lẫn trường hợp một thao tác giữa chừng phát sinh lỗi để xác nhận rollback đúng như mong đợi.

### Giai đoạn 6: Tích hợp với WebFlux

**Mục tiêu:** Xây dựng luồng xử lý từ HTTP request qua service đến database mà không chặn luồng.

Tạo endpoint tạo khách hàng, tìm theo ID, tìm theo điều kiện và xóa bản ghi. Controller trả về publisher; service kết hợp các thao tác repository; lỗi nghiệp vụ được ánh xạ thành HTTP status phù hợp. Thử cả trường hợp không tìm thấy dữ liệu, dữ liệu không hợp lệ và database tạm thời không truy cập được.

Sau đó bổ sung một endpoint trả về nhiều kết quả và quan sát cách `Flux` được ghi thành response. Chỉ dùng streaming khi định dạng response và yêu cầu nghiệp vụ phù hợp; không phải endpoint danh sách nào cũng cần stream từng phần.

### Giai đoạn 7: Kiểm thử và vận hành

**Mục tiêu:** Có thể phát hiện lỗi ở cả pipeline reactive, truy vấn SQL và kết nối thật.

- Unit test service bằng publisher giả lập hoặc mock phù hợp.
- Dùng `StepVerifier` kiểm tra giá trị, thứ tự signal, lỗi và completion.
- Integration test với database thật hoặc container database tương thích với môi trường chạy.
- Kiểm tra transaction rollback, ràng buộc dữ liệu và truy vấn tùy chỉnh.
- Cấu hình connection pool, timeout và giới hạn tải theo khả năng database.
- Theo dõi thời gian truy vấn, số kết nối đang sử dụng và lỗi kết nối.

Hãy kiểm thử trên cùng loại database và driver sẽ dùng khi triển khai. Một bài kiểm thử chạy tốt trên H2 chưa đủ để bảo đảm câu SQL, kiểu dữ liệu hoặc hành vi transaction tương thích với PostgreSQL hay SQL Server.

## 4. Bài tập thực hành xuyên suốt

Một dự án nhỏ giúp kết nối các chủ đề tốt hơn việc học annotation rời rạc. Có thể triển khai theo các mốc sau:

| Mốc | Chức năng | Kiến thức được luyện tập |
|---|---|---|
| 1 | Tạo bảng khách hàng và CRUD | SQL, entity mapping, `ReactiveCrudRepository` |
| 2 | Tìm kiếm theo email và trạng thái | Derived query, `@Query`, bind tham số |
| 3 | Tạo đơn hàng cùng các dòng chi tiết | Aggregate, quan hệ bảng, transaction |
| 4 | API trả về thông tin khách hàng và đơn hàng | `Mono`, `Flux`, `flatMap`, WebFlux |
| 5 | Xử lý dữ liệu không tồn tại và lỗi database | Empty publisher, error handling, HTTP mapping |
| 6 | Kiểm thử luồng tạo đơn hàng | `StepVerifier`, integration test, rollback |
| 7 | Tối ưu truy vấn và giới hạn kết nối | Index, execution plan, connection pool, timeout |

Không nên bắt đầu bằng một hệ thống có quá nhiều bảng hoặc nhiều dịch vụ. Một schema nhỏ giúp tập trung vào cách R2DBC hoạt động. Khi đã hiểu CRUD và transaction, hãy tăng dần độ phức tạp của truy vấn và nghiệp vụ.

## 5. Cấu hình môi trường học tập tối thiểu

Một môi trường thực hành cơ bản gồm:

1. JDK tương thích với phiên bản Spring Boot đang dùng.
2. Maven hoặc Gradle và IDE có hỗ trợ Java.
3. Một hệ quản trị cơ sở dữ liệu quan hệ, chạy cục bộ hoặc trong container.
4. Spring Boot với dependency Spring Data R2DBC.
5. Driver R2DBC tương ứng với database đã chọn.
6. Công cụ quản lý database để tạo schema và kiểm tra dữ liệu.

Ví dụ cấu hình kết nối PostgreSQL trong `application.yml`:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/learning
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
```

Dependency thường cần có là starter Spring Data R2DBC và driver của database, ví dụ `org.postgresql:r2dbc-postgresql` khi dùng PostgreSQL. Nếu ứng dụng cung cấp API reactive qua HTTP, có thể bổ sung Spring WebFlux. Hãy để Spring Boot dependency management quản lý các phiên bản tương thích thay vì tự chọn phiên bản ngẫu nhiên cho từng thư viện.

R2DBC dùng URL có scheme `r2dbc:`; URL JDBC bắt đầu bằng `jdbc:` dành cho driver JDBC và không thể thay thế trực tiếp. Cấu hình chính xác còn phụ thuộc database, thông tin xác thực, SSL và môi trường triển khai. Không đưa mật khẩu thật vào mã nguồn; dùng biến môi trường hoặc hệ thống quản lý secret.

Việc tạo và nâng cấp schema nên được quản lý bằng quy trình migration rõ ràng. Trong một số dự án, migration được chạy bằng công cụ dựa trên JDBC trong giai đoạn triển khai, trong khi ứng dụng sử dụng R2DBC cho truy cập dữ liệu lúc chạy. Hai vai trò này có thể cùng tồn tại.

## 6. Những nhầm lẫn thường gặp khi mới học

### Cho rằng R2DBC tự làm toàn bộ ứng dụng trở thành non-blocking

R2DBC cung cấp API truy cập database không chặn. Nếu service gọi thư viện blocking, đọc file đồng bộ hoặc gọi `.block()` trên event-loop, ứng dụng vẫn có điểm nghẽn blocking. Cần xem xét toàn bộ đường xử lý từ đầu vào đến database.

### Cho rằng `Mono` hoặc `Flux` là dữ liệu đã có sẵn

Publisher mô tả một quá trình phát dữ liệu. Nó có thể chưa chạy cho đến khi được subscribe, có thể hoàn tất mà không phát giá trị, hoặc phát lỗi. Cần hiểu các signal thay vì coi publisher như một `List` hay một đối tượng thông thường.

### Mong đợi quan hệ entity hoạt động như JPA

Spring Data R2DBC không cung cấp lazy loading và persistence context như JPA. Khi cần dữ liệu ở bảng khác, hãy thiết kế truy vấn hoặc bước truy cập rõ ràng. Với mô hình aggregate, hãy xác định dữ liệu nào thuộc về aggregate root và cách lưu chúng.

### Dùng `subscribe()` để né kiểu trả về reactive

Tự subscribe trong service thường làm luồng công việc tách khỏi request hoặc transaction đang xử lý. Hãy trả publisher về cho tầng gọi và kết hợp các bước bằng toán tử Reactor.

### Chỉ kiểm thử bằng database giả lập

Database khác nhau có thể khác cú pháp SQL, kiểu dữ liệu, khả năng của driver và hành vi transaction. Kiểm thử tích hợp với database mục tiêu giúp phát hiện các sai khác mà unit test không thể thấy.

### Bỏ qua giới hạn tài nguyên

Non-blocking không có nghĩa là tài nguyên vô hạn. Connection pool vẫn có giới hạn; truy vấn dài, phát quá nhiều dữ liệu hoặc giữ transaction quá lâu vẫn có thể làm hệ thống chậm. Cần giới hạn kết quả, thiết lập timeout và quan sát tải thực tế.

## 7. Chọn thứ tự học theo kinh nghiệm hiện có

- **Mới học Java hoặc Spring:** Học Java, SQL, Spring Boot và kiến trúc controller–service–repository trước; sau đó học Reactor, rồi mới đến R2DBC.
- **Đã làm Spring MVC với JDBC hoặc JPA:** Ôn lại SQL và transaction, tập trung vào Reactor, sự khác biệt giữa Spring Data R2DBC và JPA, sau đó chuyển một use case CRUD nhỏ sang R2DBC.
- **Đã quen Reactor hoặc WebFlux:** Ôn SQL, mô hình aggregate và R2DBC SPI; sau đó học mapping, repository, truy vấn tùy chỉnh và transaction reactive.
- **Đã dùng R2DBC nhưng gặp lỗi production:** Ưu tiên kiểm tra driver, transaction context, connection pool, timeout, truy vấn SQL và các đoạn blocking trong pipeline.

## 8. Checklist sẵn sàng học Spring Data R2DBC

Trước khi chuyển sang các bài học chuyên sâu, hãy tự kiểm tra xem mình có thể:

- [ ] Viết một truy vấn SQL có `JOIN`, điều kiện lọc và sắp xếp.
- [ ] Giải thích khóa chính, khóa ngoại, index và transaction.
- [ ] Tạo và cấu hình một ứng dụng Spring Boot đơn giản.
- [ ] Giải thích `Mono`, `Flux`, `map` và `flatMap`.
- [ ] Nêu được vì sao `.block()` có thể gây vấn đề trong luồng reactive.
- [ ] Phân biệt R2DBC driver, R2DBC SPI và Spring Data R2DBC.
- [ ] Kết nối được ứng dụng với database bằng R2DBC URL và driver phù hợp.
- [ ] Viết một entity và một reactive repository đơn giản.
- [ ] Kiểm thử publisher bằng `StepVerifier` và kiểm thử truy vấn với database.

Không nhất thiết phải thành thạo mọi mục trước khi bắt đầu. Tuy nhiên, nếu chưa hiểu SQL hoặc chưa đọc được một pipeline `Mono` / `Flux`, nên dành thời gian củng cố hai nền tảng đó. Khi đã nắm được chúng, các annotation và API của Spring Data R2DBC sẽ dễ hiểu hơn, đồng thời có thể đánh giá đúng khi nào mô hình reactive mang lại lợi ích cho ứng dụng.
