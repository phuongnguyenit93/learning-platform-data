# Quan hệ giữa Spring Boot, Spring MVC, WebFlux, Spring Data và Spring Security

Khi xây dựng ứng dụng Java với hệ sinh thái Spring, chúng ta thường gặp năm cái tên: **Spring Boot**, **Spring MVC**, **Spring WebFlux**, **Spring Data** và **Spring Security**. Chúng liên quan chặt chẽ nhưng giải quyết **những nhóm vấn đề khác nhau**. Hiểu đúng mối quan hệ này giúp chọn thư viện phù hợp, đọc được luồng xử lý yêu cầu và tránh nhầm lẫn giữa cơ chế web, truy cập dữ liệu và bảo mật.

Một ứng dụng Spring Boot có thể chỉ dùng Spring MVC, chỉ dùng WebFlux, hoặc thậm chí không cung cấp HTTP API nào. Spring Data và Spring Security là các khả năng bổ sung theo nhu cầu, không phải những tầng bắt buộc của mọi ứng dụng Boot.

## 1. Nhìn toàn cảnh: mỗi thành phần đảm nhiệm việc gì?

| Thành phần | Trách nhiệm chính | Câu hỏi nó giúp trả lời |
|---|---|---|
| **Spring Framework** | Nền tảng IoC/Dependency Injection, quản lý bean, cấu hình, transaction, tích hợp web và nhiều khả năng khác | Các đối tượng ứng dụng được tạo, kết nối và vận hành như thế nào? |
| **Spring Boot** | Khởi tạo và cấu hình ứng dụng Spring nhanh chóng bằng starter, auto-configuration, quản lý phiên bản phụ thuộc và tiện ích vận hành | Làm thế nào để đưa các thành phần Spring vào một ứng dụng chạy được với ít cấu hình thủ công? |
| **Spring MVC** | Xây dựng HTTP API và ứng dụng web trên **Servlet stack** | Nhận request, định tuyến tới controller và tạo response theo mô hình Servlet ra sao? |
| **Spring WebFlux** | Xây dựng HTTP API và luồng xử lý web theo mô hình **reactive**, hỗ trợ I/O không chặn | Xử lý luồng dữ liệu bất đồng bộ với `Mono`/`Flux` như thế nào? |
| **Spring Data** | Cung cấp cách làm việc với hệ lưu trữ dữ liệu qua repository, template và tích hợp công nghệ cụ thể | Truy vấn, lưu và ánh xạ dữ liệu với ít mã lặp như thế nào? |
| **Spring Security** | Xác thực, phân quyền và bảo vệ ứng dụng; có tích hợp tương ứng cho Servlet và reactive | Ai đang truy cập, họ được phép thực hiện thao tác gì và request được bảo vệ ra sao? |

**Điểm mấu chốt:** Spring Boot là lớp hỗ trợ **lắp ráp và vận hành** ứng dụng Spring; MVC/WebFlux xử lý **web**; Spring Data xử lý **dữ liệu**; Spring Security xử lý **bảo mật**. Chúng không phải năm phiên bản thay thế lẫn nhau.

Sơ đồ trách nhiệm đơn giản:

~~~text
                    ỨNG DỤNG SPRING BOOT
             (bootstrap, starter, auto-configuration)
                             │
                     Spring Framework
                   (IoC/DI, bean, cấu hình)
                             │
            ┌────────────────┼──────────────────┐
            │                │                  │
         WEB LAYER        DATA LAYER       SECURITY
            │                │                  │
      Spring MVC       Spring Data JPA      Spring Security
          hoặc             hoặc             (Servlet)
      Spring WebFlux   Spring Data R2DBC        hoặc
                         hoặc loại khác    Spring Security
                                             (Reactive)
~~~

Đây là sơ đồ **vai trò**, không phải sơ đồ kế thừa lớp. Security thường tham gia **trước khi** request tới controller, còn Spring Data thường được service gọi khi cần lưu hoặc lấy dữ liệu.

## 2. Spring Boot đứng ở đâu so với Spring Framework?

Spring Framework là nền tảng cung cấp `ApplicationContext`, bean, Dependency Injection, transaction và các mô-đun web như Spring MVC/WebFlux. Spring Boot được xây trên nền đó để giảm công sức thiết lập ứng dụng:

1. **Starter dependencies** gom những thư viện thường đi cùng một nhu cầu, chẳng hạn `spring-boot-starter-web` hoặc `spring-boot-starter-data-jpa`.
2. **Auto-configuration** xem các thư viện hiện diện trên classpath, bean do ứng dụng khai báo và các thuộc tính cấu hình để tự đăng ký những bean thích hợp.
3. **Embedded server và khởi động ứng dụng** giúp đóng gói một dịch vụ HTTP chạy độc lập; ví dụ Spring MVC thường chạy trên Servlet container nhúng.
4. **Externalized configuration và vận hành** hỗ trợ cấu hình theo môi trường, logging, health/metrics khi thêm các thành phần tương ứng.

Điểm vào quen thuộc:

~~~java
@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

`@SpringBootApplication` kết hợp những khả năng quan trọng như cấu hình Spring, component scanning và kích hoạt auto-configuration. Tuy nhiên, **Boot không tự biến mọi thư viện Spring thành một phần của ứng dụng**: thành phần nào được dùng còn phụ thuộc dependency và cấu hình thực tế.

Ví dụ, nếu thêm `spring-boot-starter-web`, Boot thường cấu hình môi trường Spring MVC cùng Servlet container. Nếu thay bằng `spring-boot-starter-webflux`, Boot có thể cấu hình ứng dụng web reactive. Thêm `spring-boot-starter-security` sẽ kích hoạt cấu hình bảo mật mặc định khi chưa có cấu hình phù hợp do ứng dụng tự khai báo.

## 3. Spring MVC và WebFlux: hai cách xây dựng tầng web

Spring MVC và Spring WebFlux đều có thể khai báo controller bằng `@RestController`, `@GetMapping`, `@RequestBody`, xử lý JSON và trả HTTP response. Sự giống nhau về annotation **không có nghĩa hai mô hình thực thi giống nhau**.

### 3.1. Spring MVC: Servlet và luồng xử lý thông dụng

Spring MVC dựa trên **Servlet API**. `DispatcherServlet` nhận request rồi chuyển đến controller tương ứng. Mô hình phổ biến là mỗi request được xử lý bằng một luồng Servlet, và luồng có thể chờ trong lúc gọi JDBC, JPA hoặc dịch vụ ngoài.

~~~text
HTTP request
  → Servlet container
  → Servlet filters / Spring Security
  → DispatcherServlet
  → Controller → Service → Repository
  → HTTP response
~~~

Ví dụ controller MVC với repository dùng Spring Data JPA:

~~~java
@RestController
@RequestMapping("/api/products")
class ProductMvcController {
    private final ProductJpaRepository repository;

    ProductMvcController(ProductJpaRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/{id}")
    Product findOne(@PathVariable Long id) {
        return repository.findById(id)
                .orElseThrow(() ->
                        new ResponseStatusException(HttpStatus.NOT_FOUND));
    }
}

interface ProductJpaRepository extends JpaRepository<Product, Long> {
}
~~~

Ở đây `Product` là entity JPA đã được ánh xạ tới bảng dữ liệu. `findById` trả về `Optional<Product>`; truy vấn JDBC/JPA thông thường có tính **blocking**. Mô hình này phù hợp với nhiều ứng dụng CRUD, nghiệp vụ giao dịch và các dự án đang sử dụng JDBC/JPA.

Spring MVC cũng hỗ trợ các kỹ thuật bất đồng bộ, nhưng nền tảng request processing của nó vẫn là **Servlet stack**; vì vậy không nên đồng nhất MVC với “mọi thứ luôn đồng bộ”.

### 3.2. Spring WebFlux: lập trình reactive

Spring WebFlux được thiết kế cho mô hình **Reactive Streams**. Thay vì nhất thiết trả đối tượng đã tính xong, handler có thể trả một publisher mô tả kết quả sẽ đến trong tương lai:

- `Mono<T>`: phát ra tối đa **một** giá trị, hoặc hoàn thành rỗng, hoặc phát lỗi.
- `Flux<T>`: phát ra **0 đến nhiều** giá trị, có thể kết thúc hoặc là luồng dài hạn.
- **Backpressure**: bên nhận có thể điều tiết lượng dữ liệu yêu cầu từ bên phát theo giao thức Reactive Streams.

Luồng xử lý web reactive thường có dạng:

~~~text
HTTP request
  → Reactive HTTP runtime
  → Reactive WebFilters / Spring Security
  → DispatcherHandler
  → Controller/Handler → Service → Reactive Repository
  → Mono/Flux → HTTP response
~~~

Ví dụ tương ứng khi dùng Spring Data R2DBC:

~~~java
@RestController
@RequestMapping("/api/products")
class ProductReactiveController {
    private final ProductReactiveRepository repository;

    ProductReactiveController(ProductReactiveRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/{id}")
    Mono<Product> findOne(@PathVariable Long id) {
        return repository.findById(id)
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(HttpStatus.NOT_FOUND)));
    }
}

interface ProductReactiveRepository
        extends ReactiveCrudRepository<Product, Long> {
}
~~~

Trong ví dụ này, `Product` phải được ánh xạ phù hợp với Spring Data R2DBC; không thể giả định entity JPA và mapping R2DBC luôn tương đương. Repository trả `Mono<Product>` và sử dụng **R2DBC driver** phù hợp để truy cập cơ sở dữ liệu theo hướng reactive.

WebFlux có thể dùng Reactor Netty hoặc chạy trên một số Servlet container hỗ trợ non-blocking I/O. Đặc trưng quyết định là **cách xử lý reactive**, chứ không đơn giản là tên máy chủ HTTP.

### 3.3. Nên chọn MVC hay WebFlux?

| Tiêu chí | Spring MVC | Spring WebFlux |
|---|---|---|
| Mô hình web | Servlet stack | Reactive stack |
| Kết quả controller thường gặp | POJO, `ResponseEntity<T>`, hỗ trợ kiểu async | `Mono<T>`, `Flux<T>`, cùng nhiều kiểu kết quả khác |
| Cơ chế I/O quen thuộc | Blocking với JDBC/JPA | Non-blocking khi **các dependency liên quan** hỗ trợ reactive |
| Truy cập SQL thường kết hợp | Spring Data JPA/JDBC | Spring Data R2DBC |
| Bài toán phổ biến | CRUD, nghiệp vụ giao dịch, hệ thống có thư viện blocking | Nhiều tác vụ I/O đồng thời, stream, pipeline có client/driver reactive |
| Điểm cần chú ý | Số luồng chờ I/O, cấu hình tài nguyên | Không chặn event-loop; kiểm soát backpressure, lifecycle, lỗi và transaction reactive |

**WebFlux không mặc nhiên nhanh hơn MVC.** Lợi ích phụ thuộc tải, dạng I/O, tài nguyên máy, driver, kiến trúc và phép đo thực tế. Nếu controller WebFlux vẫn gọi JPA/JDBC đồng bộ, thao tác đó vẫn chặn luồng đang thực thi; chỉ đổi kiểu trả về sang `Mono` không khiến truy vấn trở thành non-blocking.

Trong một ứng dụng Boot, nếu cả starter MVC và WebFlux cùng xuất hiện, **Boot mặc định ưu tiên cấu hình ứng dụng Servlet/MVC**. Một trường hợp hợp lý để thêm thư viện WebFlux vào ứng dụng MVC là dùng `WebClient` để gọi HTTP ở phía client; điều đó không tự chuyển server sang WebFlux. Kiểu ứng dụng có thể được cấu hình rõ ràng khi thật sự cần.

## 4. Spring Data là tầng truy cập dữ liệu, độc lập với lựa chọn web

Spring Data không phải một database, và cũng không đồng nghĩa với JPA. Đây là họ dự án cung cấp các abstraction và tích hợp lưu trữ như:

- **Spring Data JPA**: repository cho JPA, thường dùng Hibernate làm JPA provider và JDBC làm cơ chế truy cập SQL.
- **Spring Data JDBC**: truy cập relational database với mô hình aggregate đơn giản hơn JPA, dùng JDBC.
- **Spring Data R2DBC**: truy cập relational database qua driver reactive.
- **Spring Data MongoDB**: hỗ trợ cách truy cập đồng bộ hoặc reactive tùy driver và API được chọn.
- Các mô-đun khác tùy loại kho lưu trữ.

Ví dụ hai kiểu repository có cùng mục đích nghiệp vụ nhưng hợp đồng thực thi khác nhau:

~~~java
// JPA: truy vấn kiểu blocking.
interface OrderJpaRepository extends JpaRepository<OrderEntity, Long> {
    Optional<OrderEntity> findByCode(String code);
}

// R2DBC: truy vấn kiểu reactive.
interface OrderR2dbcRepository
        extends ReactiveCrudRepository<OrderRow, Long> {
    Mono<OrderRow> findByCode(String code);
}
~~~

`OrderEntity` và `OrderRow` đại diện hai mô hình ánh xạ riêng của từng công nghệ. Spring Data tạo implementation repository dựa vào module được kích hoạt và metadata. Ứng dụng vẫn nên đặt nghiệp vụ trong **service**, không để repository chịu trách nhiệm xác thực, phân quyền hoặc định tuyến HTTP.

Mối quan hệ quan trọng:

- **MVC + Spring Data JPA** là tổ hợp rất thường gặp: controller gọi service, service dùng repository, truy vấn SQL chạy qua JPA/JDBC.
- **WebFlux + Spring Data R2DBC** là tổ hợp reactive xuyên suốt: publisher có thể đi từ HTTP handler tới database driver.
- **MVC + một API dữ liệu reactive** vẫn có thể xảy ra, nhưng phải hiểu chính xác chỗ nào bridge giữa hai mô hình.
- **WebFlux + JPA** cũng có thể được nối vào hệ thống, nhưng JPA vẫn là blocking. Nếu buộc phải gọi nó, cần cách ly công việc chặn khỏi các event-loop; đây là một giải pháp tích hợp có chi phí và giới hạn, không thay thế cho reactive driver.

Transaction cũng khác về ngữ cảnh: với JPA, transaction thường gắn với luồng thực thi; với reactive, transaction được quản lý theo **reactive execution context** và phải bao bọc đúng publisher/chuỗi thao tác. Không thể lấy cách quản lý transaction của JDBC/JPA áp nguyên xi cho R2DBC.

## 5. Spring Security bảo vệ cả MVC lẫn WebFlux

Spring Security là một phần độc lập của hệ sinh thái Spring, tích hợp vào **chuỗi xử lý HTTP** và có thể bảo vệ cả phương thức nghiệp vụ. Hai khái niệm nền tảng:

- **Authentication — xác thực:** xác định chủ thể đang truy cập, chẳng hạn thông qua session, HTTP Basic hoặc Bearer token.
- **Authorization — phân quyền:** xác định chủ thể đã xác thực được phép truy cập endpoint hoặc thao tác nào.

Ở Servlet/MVC, Spring Security sử dụng **Servlet filter chain**, thường được cấu hình bằng `SecurityFilterChain` và `HttpSecurity`. Với WebFlux, nó sử dụng **WebFilter chain** reactive, cấu hình bằng `SecurityWebFilterChain` và `ServerHttpSecurity`.

### 5.1. Ví dụ cấu hình cho Spring MVC

~~~java
@Configuration
class MvcSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .anyRequest().authenticated());
        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
~~~

### 5.2. Ví dụ cấu hình cho Spring WebFlux

~~~java
@Configuration
@EnableWebFluxSecurity
class ReactiveSecurityConfig {
    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(auth -> auth
                        .pathMatchers("/api/public/**").permitAll()
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
~~~

Hai đoạn trên minh họa **hai ứng dụng thay thế nhau**, mỗi ứng dụng sử dụng đúng kiểu security chain của web stack tương ứng. Chúng giả định ứng dụng có cơ chế cung cấp thông tin người dùng phù hợp. HTTP Basic chỉ là lựa chọn minh họa; ứng dụng thực tế có thể dùng session, OAuth2/OIDC hoặc JWT theo kiến trúc.

Security cũng có thể kiểm soát truy cập ở tầng service bằng method security, chẳng hạn với `@PreAuthorize` khi bật tính năng tương ứng. Điều này hữu ích vì một nghiệp vụ có thể được gọi từ nhiều entry point, không chỉ một HTTP endpoint.

Lưu ý rằng **CORS, CSRF và phân quyền là các mối quan tâm khác nhau**. Cấu hình chúng dựa trên loại client, cách dùng cookie/session hay token và nguy cơ thực tế; không nên vô hiệu hóa CSRF chỉ để một request thử nghiệm chạy được. Việc có Spring Security cũng không có nghĩa mọi route đã có chính sách nghiệp vụ đúng: nhà phát triển vẫn phải khai báo và kiểm thử quyền truy cập cần thiết.

## 6. Các thành phần phối hợp trong một request thực tế

Xét API `GET /api/orders/42` yêu cầu người dùng đăng nhập và truy vấn database.

### Kiến trúc A: Boot + MVC + Spring Data JPA + Security

~~~text
Client
  │ GET /api/orders/42
  ▼
Embedded Servlet container (do Boot cấu hình)
  ▼
Spring Security servlet filters
  │ xác thực và kiểm tra quyền
  ▼
Spring MVC DispatcherServlet
  ▼
OrderController
  ▼
OrderService (nghiệp vụ, transaction khi phù hợp)
  ▼
Spring Data JPA Repository
  ▼
JPA provider → JDBC driver → SQL database
  │
  └─→ kết quả → controller → JSON/HTTP response
~~~

Trong đường đi này, Spring Boot chịu trách nhiệm **khởi động, kết nối cấu hình và vòng đời thành phần**. Nó không thay controller thực hiện routing, không thay JPA viết cơ chế persistence và cũng không thay Security quyết định quyền truy cập.

### Kiến trúc B: Boot + WebFlux + Spring Data R2DBC + Security

~~~text
Client
  │ GET /api/orders/42
  ▼
Reactive HTTP runtime (do Boot cấu hình)
  ▼
Spring Security reactive WebFilters
  ▼
Spring WebFlux DispatcherHandler
  ▼
OrderHandler / OrderController
  ▼
OrderService trả Mono/Flux
  ▼
Spring Data R2DBC Repository
  ▼
R2DBC driver → SQL database
  │
  └─→ tín hiệu dữ liệu → reactive HTTP response
~~~

Ở kiến trúc B, các bước xử lý nên duy trì tính reactive đến những thao tác I/O quan trọng. **Không chặn event-loop** bằng `Thread.sleep`, JDBC/JPA, gọi mạng đồng bộ hay thao tác file chặn trong các handler reactive. Nếu tích hợp thư viện blocking là bắt buộc, phải có chiến lược offload và giới hạn concurrency rõ ràng.

Hai kiến trúc có thể cung cấp cùng một hợp đồng REST nhưng có **runtime, cách xử lý lỗi, transaction, thread và performance profile** khác nhau.

## 7. Chọn starter trong Spring Boot như thế nào?

Với dự án dùng Gradle và dependency management của Spring Boot, hai ví dụ tối giản:

**Phương án Servlet/MVC và JPA:**

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

**Phương án reactive với WebFlux và R2DBC:**

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-data-r2dbc'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    runtimeOnly 'org.postgresql:r2dbc-postgresql'
}
~~~

Đây là **hai cấu hình tham khảo riêng**; chúng giả định ứng dụng có cấu hình database, schema, mapping và authentication phù hợp. `spring-boot-starter-security` được dùng trong cả hai, nhưng loại security infrastructure được cấu hình phụ thuộc web stack. Khi dùng Boot dependency management, phiên bản của các thư viện được quản lý theo phiên bản Boot đang dùng; tránh tự ghép tùy tiện các phiên bản Spring không tương thích.

Ví dụ thuộc tính kết nối PostgreSQL minh họa khác biệt:

~~~properties
# MVC + JPA: JDBC
spring.datasource.url=jdbc:postgresql://localhost:5432/catalog
spring.datasource.username=app
spring.datasource.password=...

# WebFlux + R2DBC (ở một ứng dụng khác):
# spring.r2dbc.url=r2dbc:postgresql://localhost:5432/catalog
# spring.r2dbc.username=app
# spring.r2dbc.password=...
~~~

Trong tình huống thực tế, dùng cấu hình/secret theo môi trường thay vì ghi mật khẩu thật vào mã nguồn. Không giả định `spring.datasource.*` và `spring.r2dbc.*` tự dùng chung pool, driver hay transaction manager.

## 8. Những nhầm lẫn cần tránh

| Quan niệm dễ nhầm | Cách hiểu chính xác |
|---|---|
| “Spring Boot là framework thay thế Spring MVC.” | Boot dùng và cấu hình Spring Framework; MVC là một web framework có thể chạy trong ứng dụng Boot. |
| “Ứng dụng Boot nào cũng phải có MVC, Data và Security.” | Chỉ thêm khả năng phù hợp với yêu cầu; ứng dụng batch hoặc messaging có thể không cần web layer. |
| “Spring MVC và WebFlux là hai cách viết annotation, còn cơ chế giống nhau.” | Annotation có thể giống, nhưng Servlet và reactive có cách thực thi, quản lý I/O, lỗi và context khác nhau. |
| “Trả về Mono là đã có non-blocking toàn bộ.” | Toàn bộ đường I/O phải phù hợp; JDBC/JPA vẫn blocking dù được bọc trong `Mono`. |
| “Spring Data đồng nghĩa Hibernate hoặc JPA.” | JPA chỉ là một module; Spring Data còn hỗ trợ JDBC, R2DBC, MongoDB và các loại lưu trữ khác. |
| “Spring Security chỉ hoạt động với MVC.” | Security có tích hợp Servlet lẫn reactive; mỗi stack dùng chain và API cấu hình tương ứng. |
| “Có starter Security là phân quyền nghiệp vụ đã hoàn tất.” | Starter cung cấp hạ tầng và mặc định; chính sách endpoint/method phải được thiết kế, cấu hình và kiểm thử. |
| “Dùng WebClient thì server chắc chắn là WebFlux.” | Ứng dụng Spring MVC vẫn có thể dùng WebClient để gọi dịch vụ khác. |

## 9. Áp dụng khi thiết kế và kiểm thử

Khi bắt đầu một module Spring Boot, có thể lần lượt đưa ra các quyết định:

1. **Có cần HTTP server không?** Nếu có, chọn web stack dựa vào yêu cầu thực tế và các thư viện downstream.
2. **Phần lớn I/O có tính blocking hay đã hỗ trợ reactive?** Nếu dùng JPA/JDBC và giao dịch truyền thống, MVC thường là lựa chọn đơn giản. Nếu API xử lý nhiều luồng I/O và các client/driver đều reactive, đánh giá WebFlux.
3. **Dùng hệ lưu trữ nào?** Chọn đúng module Spring Data cho công nghệ lưu trữ và mô hình truy cập; không chọn theo tên controller.
4. **Ai được gọi endpoint và thao tác nào?** Thiết kế authentication/authorization, áp dụng Security theo web stack và cân nhắc kiểm tra quyền tại service.
5. **Kiểm chứng điều gì?** Kiểm thử cả response HTTP, hành vi repository, transaction, xử lý lỗi và trường hợp không đủ quyền.

Các công cụ kiểm thử trong hệ sinh thái thường được dùng tương ứng: `MockMvc` và `@WebMvcTest` cho lớp web MVC; `WebTestClient` và `@WebFluxTest` cho lớp web WebFlux; `@DataJpaTest` cho JPA, `@DataR2dbcTest` cho R2DBC; `@SpringBootTest` khi cần kiểm tra tích hợp nhiều lớp. Sử dụng công cụ hỗ trợ Spring Security Test để xác nhận cả truy cập hợp lệ và truy cập bị từ chối. Mỗi test slice chỉ nạp một phần context, vì vậy không nên suy ra từ một bài kiểm thử controller rằng security, database và toàn bộ ứng dụng đã hoạt động đúng.

Một quy tắc kiến trúc dễ nhớ: **Controller/handler nhận và trả HTTP; service giữ nghiệp vụ; repository làm việc với dữ liệu; security bảo vệ điểm truy cập và thao tác; Spring Boot tạo môi trường để các phần này kết hợp được với nhau.** Chọn MVC hay WebFlux là quyết định về **mô hình xử lý web và I/O**, còn chọn Spring Data và Spring Security là quyết định theo **nhu cầu dữ liệu và bảo mật**.
