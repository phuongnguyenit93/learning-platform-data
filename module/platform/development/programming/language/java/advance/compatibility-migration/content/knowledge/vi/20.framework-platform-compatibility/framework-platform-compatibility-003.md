# Spring Boot 2 sang 3: Java baseline và thay đổi hệ sinh thái Jakarta

Chuyển ứng dụng từ **Spring Boot 2.x sang Spring Boot 3.x** là một đợt nâng cấp nền tảng lớn, không chỉ là thay version của plugin hoặc dependency. Spring Boot 3 yêu cầu **Java 17 trở lên**, xây dựng trên **Spring Framework 6**, sử dụng nhiều API thuộc **Jakarta EE** thay cho các API Java EE mang namespace `javax.*`, đồng thời nâng những thành phần quan trọng như Spring Security, Spring Data, Hibernate ORM, embedded Servlet container và hệ quan sát (observability).

Vì các lớp thay đổi này liên quan trực tiếp tới biên dịch, reflection, annotations, serialization, filter chain, persistence và deployment, một ứng dụng có thể gặp lỗi ngay khi compile hoặc chỉ thất bại trong một luồng chạy cụ thể. Ví dụ, source sử dụng `javax.servlet.Filter` không còn khớp với hợp đồng Servlet của Spring Framework 6; entity chứa `javax.persistence.Entity` có thể không được nhận diện theo Jakarta Persistence; một thư viện bảo mật cũ có thể không tương thích với Spring Security 6; hoặc custom auto-configuration không được nạp như trước.

Trong **Java Advance Compatibility Migration**, cách làm hiệu quả là tách các nguyên nhân: **baseline của JDK**, **namespace Jakarta**, **thay đổi phiên bản framework/dependency**, **cấu hình và hành vi mặc định**, cuối cùng là **kiểm thử trên môi trường runtime thật**. Bài học này xây dựng kế hoạch chuyển đổi từng bước, kèm ví dụ Gradle, Maven, Java, cấu hình bảo mật, JPA, Servlet, observability và ma trận kiểm chứng.

## 1. Hiểu phạm vi nâng cấp: Boot 3 không chỉ là Boot 2 chạy trên Java mới

Một ứng dụng Spring Boot 2.x có thể chạy bằng JDK mới trong một số cấu hình phù hợp, nhưng điều đó không đồng nghĩa toàn bộ code đã sẵn sàng cho Spring Boot 3. Đường nâng cấp gồm nhiều trục thay đổi:

| Trục | Nền tảng Boot 2.x điển hình | Khi chuyển sang Boot 3.x |
|---|---|---|
| Java baseline | Tùy nhánh Boot 2; nhiều dự án xuất phát từ Java 8/11 | **Tối thiểu Java 17** |
| Spring Framework | Spring Framework 5.x | Spring Framework 6.x |
| Jakarta / Java EE | Phần lớn tích hợp web, JPA, validation dùng `javax.*` | Chuyển sang các API `jakarta.*` tương ứng |
| Servlet container | Ví dụ Tomcat 9 với `javax.servlet.*` | Các container phù hợp Jakarta Servlet, ví dụ Tomcat 10.1 ở Boot 3.0 |
| Persistence | Hibernate ORM 5.x ở các dòng Boot 2 phổ biến | Hibernate ORM 6.x ở Boot 3 |
| Spring Data | Dòng 2.x ở Boot 2 | Dòng 3.x ở Boot 3 |
| Security | Spring Security 5.x | Spring Security 6.x |
| Observability | Một số hệ dùng Sleuth hoặc custom metrics | Micrometer Observation/Tracing là hướng tích hợp chính |
| Runtime/configuration | Properties, auto-config và defaults của Boot 2 | Có key, cơ chế đăng ký và hành vi đổi |

Đây là bảng mang tính kiến trúc cho lộ trình **2.x → 3.x**, không thay thế compatibility matrix của **patch/minor version cụ thể** mà dự án lựa chọn. Các nhánh Boot 3.x cũng tiếp tục có thay đổi giữa các bản minor.

Điểm cần ghi nhớ: **nâng JDK lên 17 là điều kiện cần để dùng Boot 3, nhưng chưa đủ để bảo đảm migration thành công**.

## 2. Java 17 là mức tối thiểu, không phải lựa chọn tùy ý

Spring Boot 3.0 yêu cầu Java 17 trở lên. Nếu ứng dụng đang chạy Java 8 hoặc Java 11, phải nâng baseline trước hoặc đồng thời với nâng framework.

Các nhóm công việc cần kiểm tra:

1. **Build JVM:** JDK chạy Gradle/Maven và plugins.
2. **Compiler JDK:** JDK biên dịch source, annotation processors và generated sources.
3. **Source/bytecode target:** phiên bản ngôn ngữ, class-file target và Java SE API cho ứng dụng.
4. **Test JVM:** JVM chạy unit/integration tests.
5. **Production runtime:** JDK thật trong VM, image, container hoặc application server.
6. **Các công cụ bổ trợ:** JaCoCo, Mockito/Byte Buddy, APM agents, code generators và static analyzers.

Một pipeline có thể compile bằng Java 17 nhưng deploy artifact vào container còn Java 11, dẫn tới `UnsupportedClassVersionError`. Ngược lại, JDK runtime đã là Java 17 nhưng annotation processor cũ phụ thuộc `com.sun.tools.javac.*` có thể làm build lỗi.

### 2.1. Ví dụ Gradle chọn toolchain

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version 'REPLACE_WITH_VERIFIED_BOOT_3_VERSION'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Chuỗi `REPLACE_WITH_VERIFIED_BOOT_3_VERSION` là **placeholder**, không phải phiên bản để chạy nguyên văn. Hãy chọn bản Boot 3.x và Gradle plugin tương thích qua tài liệu của nhánh mục tiêu; cùng lúc xác minh Gradle wrapper có thể vận hành với JDK đã chọn.

`options.release = 17` chỉ định source language, bytecode target và Java SE API target của compiler khi hỗ trợ. Nó không tự buộc mọi thư viện bên ngoài phải có class-file target 17.

### 2.2. Ví dụ Maven

~~~xml
<properties>
    <java.version>17</java.version>
</properties>
~~~

Trong một Spring Boot Maven project dùng parent/BOM phù hợp, `java.version` thường được dùng để xác định baseline Java. Đối với build tùy biến, cần kiểm tra Maven Compiler Plugin và `maven.compiler.release` thực tế. Đoạn XML trên là fragment, không phải một POM hoàn chỉnh.

### 2.3. Kiểm tra cùng một JDK trên các môi trường

~~~bash
java -version
javac -version
./gradlew --version
mvn -version
~~~

Các lệnh chỉ có ý nghĩa khi chạy ở đúng môi trường và toolchain mà build/deployment thực sự dùng. Không suy rằng `java -version` trên laptop phản ánh JDK trong production container.

## 3. Vì sao nên đi qua Spring Boot 2.7 trước?

Đối với ứng dụng đang ở một bản Boot 2.x cũ, một đường nâng cấp thường dễ kiểm soát hơn là:

~~~text
Spring Boot 2.x cũ
       |
       | Nâng dependencies, làm sạch warnings, bảo đảm tests
       v
Spring Boot 2.7.x phù hợp
       |
       | Chuyển Java 17, chuẩn bị API/config và tests
       v
Spring Boot 3.x mục tiêu
       |
       | Xử lý Jakarta + Security/Data/Observability
       v
Stable deployment
~~~

Boot 2.7 là bước đệm hữu ích vì được thiết kế ở giai đoạn ngay trước Boot 3. Tuy nhiên, **không bắt buộc** mọi hệ thống phải phát hành một bản production riêng trên 2.7 trước khi lên 3; đây là chiến lược giảm rủi ro để tách nguyên nhân.

Ở bước đệm:

- Nâng những plugin/test tools đủ mới để chạy Java 17.
- Kiểm tra dependency graph và libraries hỗ trợ Boot 3.
- Thay các API đã deprecated nếu có hướng migration rõ ràng.
- Xác nhận integration tests, database migrations và security behavior.
- Lưu baseline về startup, request mapping, error responses, metrics, latency và resource usage.
- Tránh nâng quá nhiều thư viện không liên quan trong cùng một commit nếu có thể.

**Đừng coi Boot 2.7 chạy xanh là bằng chứng ứng dụng đã dùng Jakarta.** Hầu hết những thay đổi namespace và framework lớn vẫn phải làm khi chuyển sang Boot 3.

## 4. Jakarta EE: đổi namespace là thay đổi hợp đồng API

Các công nghệ Java EE trước đây dùng những package `javax.*`. Hệ sinh thái Jakarta EE 9 chuyển nhiều API sang `jakarta.*`. Spring Framework 6 và Boot 3 tích hợp với hệ Jakarta hiện đại.

Ví dụ:

~~~java
// Trước: ứng dụng Servlet/JPA/Validation dùng Java EE namespace
import javax.servlet.Filter;
import javax.persistence.Entity;
import javax.validation.Valid;
import javax.annotation.PostConstruct;
~~~

Chuyển các API tương ứng:

~~~java
// Sau: API Jakarta tương ứng trong Boot 3
import jakarta.servlet.Filter;
import jakarta.persistence.Entity;
import jakarta.validation.Valid;
import jakarta.annotation.PostConstruct;
~~~

Đây không chỉ là “thay chữ” trong source. **Type identity phụ thuộc đầy đủ vào package name.** `javax.servlet.Filter` và `jakarta.servlet.Filter` là hai types khác nhau dù tên ngắn cùng là `Filter`. Một thư viện compile cho javax Servlet có thể không được nhận bởi Jakarta Servlet container; một framework Jakarta Persistence có thể không nhận entity được đánh dấu bằng annotation `javax.persistence.Entity`.

### 4.1. Bảng ánh xạ nhóm API phổ biến

| Trước (Boot 2 / Java EE API) | Sau (Boot 3 / Jakarta API) | Công việc đi kèm |
|---|---|---|
| `javax.servlet.*` | `jakarta.servlet.*` | Servlet, Filter, Listener, Request/Response wrappers |
| `javax.persistence.*` | `jakarta.persistence.*` | Entity, repositories, converters, JPA customizations |
| `javax.validation.*` | `jakarta.validation.*` | Bean Validation annotations và validators |
| `javax.annotation.*` (ví dụ `PostConstruct`) | `jakarta.annotation.*` | Lifecycle annotations, dependencies |
| `javax.transaction.*` (Jakarta Transactions API) | `jakarta.transaction.*` | Transaction annotations/API nếu đang dùng Jakarta Transactions |
| `javax.mail.*` | `jakarta.mail.*` | Mail API/provider và integrations |
| `javax.activation.*` | `jakarta.activation.*` | Activation API dependencies |
| `javax.ws.rs.*` | `jakarta.ws.rs.*` | JAX-RS libraries nếu ứng dụng dùng |
| `javax.xml.bind.*` | `jakarta.xml.bind.*` | JAXB APIs/implementations nếu chuyển sang dòng Jakarta |

Bảng không có nghĩa tất cả ứng dụng Boot 3 đều dùng mọi API này, cũng không có nghĩa đổi package là đủ mà không nâng implementation.

### 4.2. Không đổi tất cả javax.* thành jakarta.*

Nhiều API Java SE vẫn mang namespace `javax.*` và **không được chuyển**:

- `javax.net.ssl.*` cho TLS.
- `javax.crypto.*` cho cryptography.
- `javax.sql.*` cho DataSource và JDBC APIs.
- `javax.naming.*` cho JNDI.
- `javax.xml.parsers.*`, `javax.xml.transform.*` cho XML APIs thuộc Java SE.
- `javax.management.*` cho JMX.
- `javax.annotation.processing.*` cho annotation processing.

Ngược lại, `javax.persistence.*` và `javax.servlet.*` trong các tích hợp Jakarta là những nhóm cần đổi. Từng import phải được phân loại theo **API owner và thư viện thực tế**, không áp dụng regex thay tên mù quáng trên toàn repository.

### 4.3. Một số type thuộc javax vẫn có ý nghĩa khác

Một ví dụ quan trọng: `javax.transaction.xa.*` thuộc Java SE X/Open XA interfaces và không phải mọi type `javax.transaction.*` đều có cùng chiến lược migration. Phải xem package và module cụ thể thay vì chỉ nhìn prefix.

## 5. Tránh trộn javax và jakarta trong cùng lớp tích hợp

Một lỗi phổ biến khi migration là giữ lại hai hệ API cho cùng một extension point:

~~~text
Spring Framework 6 / Boot 3
         |
         +--> Jakarta Servlet Filter
         |
         +--> Legacy library expects javax.servlet.Filter
                                      ^
                                      |
                                  incompatible
~~~

Nếu một thư viện legacy trả về type `javax.servlet.Filter`, code sử dụng nó không thể coi đó là `jakarta.servlet.Filter` chỉ bằng cast. Hai types có tên package khác và không có quan hệ kế thừa.

Các biểu hiện:

- `incompatible types` ở compile time.
- `ClassNotFoundException: javax.servlet.Filter` hoặc `NoClassDefFoundError` khi chạy.
- Bean không đăng ký hoặc callback không được gọi vì annotation khác namespace.
- Framework không nhận diện entity/validator/listener.
- Servlet container báo không thể load/filter chain.
- Dependency graph có cả `javax.servlet-api` và `jakarta.servlet-api`.

Sự tồn tại của hai JAR trong classpath chưa chắc làm build lỗi ngay, nhưng **không thể dùng một type javax như implementation của contract jakarta tương ứng**.

### 5.1. Không thêm thư viện javax API chỉ để hết lỗi compile

Nếu một thư viện đang cần `javax.servlet-api` trong môi trường Boot 3, bổ sung artifact cũ có thể làm lỗi import biến mất nhưng không giải quyết integration với Jakarta container. Cần nâng/thay **thư viện cung cấp extension**, không chỉ thêm API JAR.

## 6. Servlet container và web application

Boot 3 dùng các Servlet APIs tương thích Jakarta. Ví dụ ở Boot 3.0, embedded Tomcat chuyển sang dòng Tomcat 10.1, nơi Servlet API mang namespace `jakarta.servlet`.

Tác động gồm:

- `Filter` và `FilterChain`.
- `ServletRequest`, `HttpServletRequest`, `HttpServletResponse`.
- `ServletContextListener`, `HttpSessionListener`.
- Custom servlet registrations.
- Servlet API wrappers.
- Third-party servlet filters, SSO adapters, monitoring integrations.
- WAR deployment vào external application server.

### 6.1. Ví dụ custom Filter trước và sau

Trước:

~~~java
import javax.servlet.Filter;
import javax.servlet.FilterChain;
import javax.servlet.ServletRequest;
import javax.servlet.ServletResponse;
import javax.servlet.ServletException;
import java.io.IOException;

public final class LegacyRequestFilter implements Filter {

    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain) throws IOException, ServletException {
        chain.doFilter(request, response);
    }
}
~~~

Sau:

~~~java
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.ServletException;
import java.io.IOException;

public final class RequestFilter implements Filter {

    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain) throws IOException, ServletException {
        chain.doFilter(request, response);
    }
}
~~~

Ví dụ thể hiện sự thay đổi contract. Nếu Filter được đăng ký qua Spring bean hoặc `FilterRegistrationBean`, kiểm tra cả generic types và imports của mọi lớp liên quan.

### 6.2. WAR không thể triển khai tùy tiện lên container javax cũ

Một WAR sử dụng Spring Framework 6/Jakarta Servlet không nên được deploy vào một Servlet container chỉ hỗ trợ `javax.servlet`, chẳng hạn dòng Tomcat 9. Nếu triển khai external container, kiểm tra **Jakarta Servlet API level và container support matrix** phù hợp với Boot minor/patch đã chọn.

### 6.3. WebFlux không đồng nghĩa Servlet

Ứng dụng dùng Spring WebFlux trên Netty không nhất thiết có cùng luồng Filter/Servlet như Spring MVC; nhưng nó vẫn chạy trên Spring Framework 6 và có thể chịu các thay đổi Jakarta ở Validation hoặc integrations. Không ép mọi ứng dụng Boot 3 phải có `jakarta.servlet-api` nếu kiến trúc không dùng Servlet stack.

## 7. Spring MVC: kiểm tra request mapping và behavior thay đổi

Ngay cả khi controller source compile sau đổi imports, hành vi web có thể khác giữa Spring Framework 5 và 6.

Một điểm đáng chú ý là **trailing slash matching**: các cấu hình/request mappings có thể không tự xem `/orders` và `/orders/` là tương đương như giả định trước đây.

Ví dụ:

~~~java
@RestController
@RequestMapping("/orders")
public final class OrderController {

    @GetMapping
    public List<String> all() {
        return List.of("A", "B");
    }
}
~~~

Cần kiểm tra cả:

~~~text
GET /orders
GET /orders/
~~~

Đừng mặc định hai đường dẫn đều trả cùng status/body khi chuyển framework. Nếu API contract cần hỗ trợ cả hai, cấu hình mapping hoặc redirect một cách chủ động và kiểm thử bằng client thực tế.

Những hành vi cũng nên kiểm tra:

- Path matching và path variables.
- Request parameter parsing.
- Content negotiation và media types.
- Message converters và serialization.
- Exception handling qua `@ControllerAdvice`.
- Error response shape và status codes.
- Multipart uploads.
- Validation và default error messages.
- CORS và Spring Security filter behavior.

### 7.1. Spring MVC test giúp bảo vệ hợp đồng

Ví dụ:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void listsOrders() throws Exception {
        mvc.perform(get("/orders"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0]").value("A"));
    }
}
~~~

Đoạn code giả định có các static imports tương ứng của JUnit, MockMvc request builders và matchers. Điểm quan trọng là kiểm tra **HTTP contract** chứ không chỉ compile controller.

## 8. Jakarta Persistence và Hibernate ORM 6

Spring Boot 3 nâng hệ persistence theo Jakarta Persistence; các dòng Boot 3 phổ biến dùng Hibernate ORM 6. Đây là một trong những khu vực thường phát sinh thay đổi sâu hơn đổi package.

Trước:

~~~java
import javax.persistence.Entity;
import javax.persistence.Id;
import javax.persistence.Table;

@Entity
@Table(name = "orders")
public class OrderEntity {

    @Id
    private Long id;
}
~~~

Sau:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "orders")
public class OrderEntity {

    @Id
    private Long id;

    protected OrderEntity() {
    }

    public OrderEntity(Long id) {
        this.id = id;
    }

    public Long getId() {
        return id;
    }
}
~~~

Ví dụ chỉ là một entity nhỏ; chiến lược tạo ID, constraints và mapping associations phụ thuộc schema thực tế.

### 8.1. Các thành phần phải khảo sát

- `@Entity`, `@Table`, `@Id`, `@GeneratedValue`.
- `@OneToMany`, `@ManyToOne`, `@JoinColumn` và fetching behavior.
- `AttributeConverter`, custom types và custom user types.
- Custom `Dialect`, Hibernate interceptors/listeners.
- JPQL/HQL và native queries.
- Criteria API.
- Pagination, sorting và query parameter binding.
- Identifier generation và database sequence naming.
- Schema validation và DDL generation.
- Second-level cache và transaction boundaries.

Không nên giả định đổi `javax.persistence.Entity` thành `jakarta.persistence.Entity` sẽ giữ toàn bộ query semantics của Hibernate 5. Hibernate ORM 6 có thay đổi nội bộ về query model, type system, SQL generation và nhiều extension APIs.

### 8.2. Query và custom Hibernate APIs

Một repository sử dụng `JpaRepository` có thể vẫn compile, nhưng HQL/JPQL phức tạp hoặc custom dialect có thể cần sửa. Nên chạy integration tests với **đúng database engine/version và dữ liệu đại diện**, không chỉ embedded H2 nếu production dùng hệ khác.

### 8.3. Nguy cơ thay đổi schema

Một nâng cấp ORM có thể khác default sequence, identifier handling hoặc SQL type mapping. Không bật auto DDL update trên production rồi kỳ vọng migration an toàn.

Hướng triển khai:

1. Dùng Flyway/Liquibase hoặc quy trình schema migration có kiểm soát.
2. Chụp schema và dữ liệu quan trọng trước nâng cấp.
3. So sánh DDL mong muốn với schema thực tế.
4. Chạy `validate` ở môi trường phù hợp khi có thể.
5. Kiểm tra insert/update/delete, optimistic locking, transactions và query plans.
6. Thiết kế rollback dữ liệu nếu ORM hoặc migration thay schema.

## 9. Spring Data 3 và repository integration

Spring Data 3 đi cùng hệ Spring Framework 6/Jakarta và các thay đổi API của dòng Spring Data.

Một interface thông thường:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository
        extends JpaRepository<OrderEntity, Long> {
}
~~~

Có thể không cần đổi tên interface `JpaRepository`, nhưng lớp entity/imports và Hibernate integration phải phù hợp. Nếu dự án có custom repositories, converters, event listeners, auditing, projections hoặc query generation đặc biệt, cần kiểm tra riêng.

Những vấn đề tiềm ẩn:

- Derived queries gọi property đã đổi tên.
- `@Query` dùng cú pháp HQL/JPQL không còn phù hợp.
- Return type và pagination semantics ảnh hưởng clients.
- Auditing annotations/bean configurations thay đổi.
- Custom Hibernate session code không compile.
- Multi-datasource configuration cần đồng bộ properties và transaction managers.
- Migrations hoặc DDL assumptions không còn đúng.

Đừng xem application startup thành công là bằng chứng mọi repository query hoạt động; một số queries chỉ được parse hoặc thực thi khi được gọi.

## 10. Bean Validation: jakarta.validation thay javax.validation

Các annotations của Bean Validation thuộc Jakarta namespace trong Boot 3.

Trước:

~~~java
import javax.validation.Valid;
import javax.validation.constraints.NotBlank;
import javax.validation.constraints.Size;
~~~

Sau:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
~~~

Ví dụ DTO:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateOrderRequest(
        @NotBlank String customerId,
        @Size(min = 1, max = 40) String note) {
}
~~~

Controller:

~~~java
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public final class OrderWriteController {

    @PostMapping("/orders")
    public String create(@Valid @RequestBody CreateOrderRequest request) {
        return request.customerId();
    }
}
~~~

Cần bảo đảm project có **validation implementation** phù hợp, thường thông qua Spring Boot validation starter khi sử dụng Bean Validation. Việc có import `jakarta.validation.*` compile được không chứng minh validator runtime đã hoạt động.

### 10.1. Chú ý custom validators

Custom `ConstraintValidator` và custom annotations phải dùng cùng Jakarta Validation contract:

~~~java
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
~~~

Một custom validator vẫn implement `javax.validation.ConstraintValidator` có thể không tương thích với implementation được Boot 3 dùng.

### 10.2. Kiểm tra validation errors

Khi nâng framework, cần bảo vệ hợp đồng về HTTP 400 response, field errors, message keys, locale và các định dạng mà frontend/client kỳ vọng. Đổi namespace không được phép làm mất validation trong một nhánh request mà không được phát hiện.

## 11. Lifecycle annotations và các API Jakarta khác

Ví dụ:

~~~java
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
~~~

Nếu ứng dụng có `javax.annotation.PostConstruct` từ legacy dependency, không nên giữ import cũ chỉ vì build có thể compile. Spring Framework 6 sử dụng hợp đồng tương ứng của Jakarta cho các integration liên quan.

Cần xem thêm các thư viện:

- Jakarta Mail và các APIs gửi thư.
- Jakarta Activation nếu xử lý MIME attachments.
- JAXB/Jakarta XML Binding nếu serialization XML.
- Jakarta Transactions khi dùng các loại `jakarta.transaction.*`.
- Jakarta WebSocket nếu dùng WebSocket APIs.
- JAX-RS nếu dự án dùng Jersey/RESTEasy hoặc nền tảng khác.

**Không phải mọi service Boot 3 đều cần đổi tất cả thư viện Java EE thành Jakarta trong một lượt.** Chỉ những APIs thực sự dùng và thuộc phần integration cần thiết mới được thay, nhưng toàn bộ các bên cùng tham gia một integration phải chọn hệ API tương thích.

## 12. Spring Security 6: cấu hình filter chain

Một thay đổi lớn trong quá trình Boot 2 → 3 là hệ Spring Security 6. Một số cách cấu hình cũ đã deprecated rồi bị loại bỏ ở các version mới, đặc biệt lối mở rộng `WebSecurityConfigurerAdapter`.

### 12.1. Ví dụ cách cấu hình cũ

~~~java
@Configuration
@EnableWebSecurity
public class LegacySecurityConfiguration
        extends WebSecurityConfigurerAdapter {

    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http.authorizeRequests()
                .antMatchers("/public/**").permitAll()
                .anyRequest().authenticated()
                .and()
                .httpBasic();
    }
}
~~~

Đây là hình thức legacy để nhận diện code cần migration, không phải mẫu dùng với Spring Security 6.

### 12.2. Cấu hình theo SecurityFilterChain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated()
        );

        http.httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Ở đây `SecurityFilterChain` là bean được Spring Security dùng để xây filter chain. Đây là ví dụ ngắn minh họa cấu trúc API, chưa bao gồm authentication provider, password encoding, CORS, session policy hay CSRF configuration của hệ thống cụ thể.

### 12.3. authorizeRequests, antMatchers và requestMatchers

Cần kiểm tra những API cũ như `authorizeRequests()`, `antMatchers()` và `mvcMatchers()` trong code security configuration; đối chiếu cách dùng `authorizeHttpRequests()` và `requestMatchers()` của Security 6 theo loại matcher phù hợp.

Không thay máy móc mọi matcher khi pattern semantics khác. Nên có tests cho các URL được phép, bị từ chối, HTTP methods và cả các endpoint có trailing slash.

### 12.4. CSRF và session management

Không tự thêm `csrf.disable()` chỉ để integration tests pass sau migration. Với ứng dụng sử dụng cookie/session, CSRF protection có thể là kiểm soát cần thiết. Nếu một stateless API dùng bearer token có thiết kế riêng, quyết định CSRF phải dựa trên threat model và cấu hình authentication thực tế.

### 12.5. Method security

Một số dự án chuyển từ `@EnableGlobalMethodSecurity` sang `@EnableMethodSecurity` và rà các annotations `@PreAuthorize`, `@PostAuthorize`. Cần kiểm tra các method security rules, SpEL expressions và behavior của service layer sau nâng cấp.

## 13. OAuth2, JWT và bảo mật ứng dụng

Nếu ứng dụng là OAuth2 client, resource server hoặc authorization server, cần kiểm kê:

- Spring Security OAuth2 modules và version.
- Resource server JWT decoder và JWK retrieval.
- Issuer/audience validation.
- Authorities/roles mapping.
- Session, login redirects và logout.
- CORS và CSRF.
- Authorization ở HTTP request và method levels.
- Third-party authentication adapters hoặc SSO libraries.

Một adapter gắn với `javax.servlet.*` không thể được coi là tương thích với Jakarta Servlet chỉ vì nó đã từng chạy trên Boot 2. Tìm bản library hỗ trợ Boot 3/Spring Security 6, hoặc thay integration theo tài liệu của nhà cung cấp.

### 13.1. Không hạ bảo mật để đạt “migration pass”

Một số lỗi startup có thể biến mất khi xóa filter, cho phép mọi URL hoặc bỏ validation token. Đó không phải migration thành công. Cần có test chứng minh:

- Endpoint công khai vẫn công khai.
- Endpoint riêng vẫn cần authentication.
- Scope/role/claim rules giữ đúng semantics.
- Token sai issuer/signature/audience bị từ chối.
- Session/login/logout hoạt động nếu ứng dụng sử dụng.
- Unauthorized và forbidden responses đúng hợp đồng API.

## 14. Dependency graph và BOM: không trộn các phiên bản không tương thích

Spring Boot thường cung cấp dependency management thông qua **Spring Boot BOM** hoặc parent/build plugin. Khi đổi từ Boot 2 sang 3, hàng loạt versions được cập nhật đồng bộ.

Những lỗi dễ gặp:

- Giữ Spring Framework 5 JAR ở một module nhưng core dùng Spring Framework 6.
- Giữ Hibernate 5 extension khi Boot 3 quản lý Hibernate 6.
- Cài `javax.servlet-api` chỉ để biên dịch library cũ.
- Đưa bản Spring Security 5 cũ vào application đã dùng Security 6.
- Một BOM nội bộ vẫn override các phiên bản theo Boot 2.
- Dependency `spring-boot-starter-*` ở nhiều major versions khác nhau.
- Shaded JAR chứa API implementation cũ.
- Java agent/bytecode library chưa hỗ trợ Java 17.

### 14.1. Gradle: kiểm tra dependency selection

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency spring-web \
  --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency hibernate-core \
  --configuration runtimeClasspath
~~~

Các lệnh tham khảo, phải điều chỉnh tên subproject/configuration cho dự án. Không tự override version của Spring Framework/Hibernate khi chưa xác minh compatibility matrix của Boot minor đích.

### 14.2. Maven: xem effective dependency versions

~~~bash
mvn help:effective-pom
mvn dependency:tree
~~~

Nếu dự án dùng Spring Boot parent, cần xem parent version chính xác. Nếu import Spring Boot BOM qua `dependencyManagement`, cần xem các BOM khác có thể xung đột và version cuối đã được chọn.

### 14.3. Tách direct và transitive dependencies

Một starter có thể kéo vào implementation version mới nhưng một thư viện legacy kéo thêm implementation cũ. Điều tra graph thực tế và artifact cuối; không coi “chỉ có starter Boot 3 trong POM” là đủ.

## 15. Ví dụ Gradle Boot 3 và dependencies Jakarta

Một ví dụ build script đơn giản:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version 'REPLACE_WITH_VERIFIED_BOOT_3_VERSION'
    id 'io.spring.dependency-management' version 'REPLACE_WITH_COMPATIBLE_PLUGIN_VERSION'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Đoạn cấu hình là **ví dụ minh họa**, không phải file chạy được ngay do các version placeholder phải thay. Hãy xem version plugin management phù hợp với Gradle wrapper và Boot release được chọn. Tùy project, có thể dùng cơ chế BOM/platform khác thay cho plugin `io.spring.dependency-management`; không nhất thiết phải sao chép chính xác một cách quản lý dependency cho mọi dự án.

Lưu ý: Spring Security starter có thể khiến ứng dụng cần khai báo cấu hình authentication/authorization rõ hơn. Thêm starter không tự bảo đảm policy của Boot 2 được giữ nguyên.

## 16. Ví dụ Maven Boot 3 theo parent

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>REPLACE_WITH_VERIFIED_BOOT_3_VERSION</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>orders-service</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Version placeholder cần được thay bằng bản Boot 3.x có thật và được chọn theo support policy của sản phẩm. Đây là ví dụ Maven cơ bản không bao gồm mọi dependency riêng của ứng dụng.

## 17. Auto-configuration: thay đổi cách đăng ký

Các Spring Boot extension libraries có thể cung cấp auto-configuration. Trong nhiều thư viện viết cho Boot 2, auto-configuration classes được liệt kê trong `META-INF/spring.factories` với key `org.springframework.boot.autoconfigure.EnableAutoConfiguration`.

Trong Boot 3, cơ chế đăng ký auto-configuration dùng resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Ví dụ nội dung file:

~~~text
com.example.orders.autoconfig.OrderClientAutoConfiguration
com.example.orders.autoconfig.OrderMetricsAutoConfiguration
~~~

Đây là tên lớp giả định để minh họa resource format.

### 17.1. Vì sao library chạy Boot 2 lại không auto-config trên Boot 3?

Nếu một starter tự viết **chỉ** đăng ký auto-config theo cơ chế cũ và chưa được chuyển đổi đúng, các bean dự kiến có thể không xuất hiện. Hệ quả là `NoSuchBeanDefinitionException`, configuration không kích hoạt hoặc tính năng chạy không đúng.

Khi migration thư viện nội bộ:

1. Xác định toàn bộ auto-configuration classes.
2. Dùng cách đăng ký được Boot 3 hỗ trợ.
3. Kiểm tra điều kiện `@ConditionalOnClass`, `@ConditionalOnProperty`.
4. Xem imports còn dùng `javax.*` hay type bị thay không.
5. Chạy ApplicationContext tests cho starter trên Boot 3.

### 17.2. Không xóa mọi spring.factories không phân biệt

`spring.factories` từng được dùng cho nhiều extension mechanisms, không phải chỉ auto-configuration. Việc chuyển **đăng ký auto-configuration** không đồng nghĩa mọi entry khác trong file đó đều phải bị xóa. Cần xem mỗi key phục vụ framework extension nào và được Spring Boot release mục tiêu hỗ trợ ra sao.

## 18. Cấu hình application.properties và application.yml

Boot 3 có các thay đổi ở một số configuration property keys và defaults. Khi nâng, cần so sánh với configuration metadata của **Boot version đích**.

Ví dụ các khu vực cần rà:

- Server HTTP, session và compression.
- DataSource, pool, JPA/Hibernate.
- Redis và Spring Data integrations.
- Actuator endpoint exposure.
- Logging, tracing, metrics và management endpoints.
- Security OAuth2 client/resource server settings.
- Config import, environment variables, profiles.
- Third-party starter namespaces.
- Kubernetes/readiness/liveness properties.

Đừng tự suy mọi property cũ đều còn được bind sau khi plugin version thay đổi. Một property bị đổi tên có thể bị bỏ qua hoặc có thông báo cảnh báo tùy hệ thống.

### 18.1. Spring Boot Properties Migrator

Trong quá trình nâng, Spring Boot cung cấp artifact `spring-boot-properties-migrator` để hỗ trợ nhận diện/migration một số configuration properties đã thay đổi. Có thể thêm **tạm thời** vào dependency khi điều tra ứng dụng, theo hướng dẫn cho Boot release đích, rồi gỡ bỏ khi cấu hình đã được cập nhật.

Không coi properties migrator là giải pháp dài hạn hoặc thay thế việc đọc migration guide. Nó không thể tự sửa mọi custom property, thay đổi namespace Java hoặc behavior của integration bên ngoài.

### 18.2. Cấu hình đã cũ có thể không còn tác dụng

Nếu một key không còn được nhận diện, application có thể khởi động nhưng dùng default mới, tạo lỗi khó phát hiện hơn compile error. Nên test các hiệu ứng thật: connection pool size, timeout, metrics exposure, session cookie, server port và các chính sách security.

## 19. Logging, Actuator và observability

Trong Boot 3, observability dựa nhiều vào **Micrometer Observation** và tích hợp tracing/metrics hiện đại. Những hệ thống trước đó dùng Spring Cloud Sleuth cần đánh giá kế hoạch chuyển sang Micrometer Tracing hoặc giải pháp tương thích.

### 19.1. Đổi thư viện chưa đủ để giữ tracing

Khi thay stack observability, cần kiểm tra:

- Trace ID và span ID có được tạo/lan truyền không.
- HTTP/messaging/database instrumentation.
- Propagation format giữa các services.
- MDC logging và log correlation.
- Sampling policy.
- OTLP/Zipkin/exporter configuration nếu sử dụng.
- Metrics tags/names và khả năng dashboard tương thích.
- Actuator endpoints và quyền truy cập.

Một dịch vụ có thể build và trả HTTP 200 nhưng làm đứt distributed trace hoặc thay metric names, khiến hệ thống giám sát bị mù ở production.

### 19.2. Không phơi bày Actuator endpoints ngoài ý muốn

Nâng Boot có thể thay defaults và property keys liên quan management. Cần kiểm tra endpoint nào enabled, exposed qua web/JMX, và áp authentication/authorization phù hợp. Không mở `/actuator/**` cho tất cả người dùng chỉ để hệ thống monitoring hoạt động sau migration.

### 19.3. Dashboard cần chuyển đổi có kiểm chứng

Nếu metric names hoặc tags thay đổi, hãy cập nhật dashboards và alerts có chủ đích. Đừng coi việc có endpoint `/actuator/health` là đủ chứng minh monitoring, tracing và SLO vẫn hoạt động.

## 20. Testing stack: JUnit, Mockito và bytecode tooling

Boot 3 đi với các phiên bản mới của testing libraries. Những dependency cũ có thể không hỗ trợ Java 17, Spring Framework 6 hoặc bytecode patterns mới.

Cần xem:

- Spring TestContext framework.
- `@SpringBootTest` và test slices (`@WebMvcTest`, `@DataJpaTest`).
- JUnit Platform/Jupiter và test runner.
- Mockito, Byte Buddy và agent-based mocking.
- Testcontainers/database driver versions.
- JaCoCo, SpotBugs và các static analyzers.
- JSON/XML test assertions.
- MockMvc request mappings và security tests.
- ApplicationContext load và custom bean configurations.

### 20.1. Test classes phải dùng Jakarta imports

Một test tạo fake servlet request/filter theo `javax.servlet.*` sẽ không còn phản ánh Jakarta Servlet contract. Cần nâng test helpers, mocks và fake implementations cùng framework.

### 20.2. Test xác thực Bean Validation

Không chỉ kiểm tra DTO compile. Nên gửi request sai constraint và xác nhận HTTP response, field errors, locale/message và database state không thay đổi ngoài ý muốn.

### 20.3. Test dữ liệu thật

H2 hoặc một embedded database có thể xử lý SQL và type mapping khác Postgres/MySQL/Oracle mà production dùng. Hibernate 6 migration cần integration tests trên database engine phù hợp, nhất là custom HQL, identifiers và schema assumptions.

## 21. Spring Native/AOT và executable packaging

Spring Boot 3 hỗ trợ các cơ chế AOT và native-image workflows hiện đại. Tuy nhiên, **không phải ứng dụng Boot 3 nào cũng phải chuyển sang GraalVM native image**. Một JVM deployment thông thường vẫn hợp lệ.

Nếu dự án dùng AOT/native image, cần điều tra thêm:

- Reflection metadata và runtime hints.
- Resource/proxy/serialization hints.
- Dynamic class loading.
- Native-compatible libraries.
- Build time vs runtime initialization.
- Testing và observability của binary.
- Image architecture và toolchain.

Đừng gộp việc đổi Boot 2 sang 3 với chuyển từ JVM JAR sang native image nếu không có mục tiêu sản phẩm cụ thể. Làm hai thay đổi cùng lúc sẽ khiến khó phân lập nguyên nhân.

## 22. Những dependency bên thứ ba thường cần thay phiên bản

Các thư viện thuộc hệ Spring Boot thường cần có bản hỗ trợ Spring Framework 6 và Jakarta EE:

- API documentation / OpenAPI integration.
- Servlet filters, authentication adapters và SSO clients.
- ORM extensions, database mapping và auditing libraries.
- Bean Validation custom providers.
- Messaging connectors.
- Spring Cloud components.
- Scheduler, batch, caching và distributed lock libraries.
- Spring integration starters của bên thứ ba.
- APM/tracing agents.
- Code generation, annotation processing và testing tools.

Một thư viện chỉ công bố hỗ trợ “Java 17” **chưa chắc hỗ trợ Boot 3**. Nó có thể chạy được trên JVM 17 nhưng vẫn compile bằng Spring 5/`javax.servlet.*`. Cần xác minh **cả Java version và Spring/Jakarta compatibility** của artifact cụ thể.

### 22.1. Spring Cloud compatibility

Nếu ứng dụng dùng Spring Cloud, đừng giữ nguyên một release train từng dành cho Boot 2 và kỳ vọng tương thích với Boot 3. Cần chọn tổ hợp Spring Cloud/Spring Boot được công bố hỗ trợ cho minor branch mục tiêu, sau đó kiểm tra Gateway, Config, Discovery, Circuit Breaker, LoadBalancer và các starter cụ thể.

### 22.2. Springdoc/OpenAPI và Swagger integrations

Một Swagger/OpenAPI integration cũ có thể trực tiếp phụ thuộc Spring MVC types hoặc `javax.servlet.*`, gây lỗi startup. Nên chọn bản tương thích Spring Boot 3 và xác minh endpoint tài liệu, schema, security metadata và API grouping, không chỉ compile dependency mới.

### 22.3. Spring Batch, Scheduler và storage

Các framework cùng hệ sinh thái có thể thay cấu trúc metadata, API và schema database. Nếu hệ thống dùng Spring Batch hoặc job schedulers, cần đánh giá migration riêng cho repository metadata, lịch chạy, retry và trạng thái job đang dở. Không mặc định việc đổi BOM giữ nguyên state model của mọi subsystem.

## 23. Phân loại lỗi compile và runtime sau nâng Boot

| Lỗi/triệu chứng | Nguyên nhân có thể | Hành động ưu tiên |
|---|---|---|
| `package javax.servlet does not exist` | Code/library chưa đổi Servlet namespace | Chuyển Jakarta imports, nâng thư viện tương thích |
| `incompatible types: javax.servlet.Filter ... jakarta.servlet.Filter` | Đang trộn hai type systems | Thay thư viện/contract, không cast |
| `ClassNotFoundException: javax.persistence.Entity` | Dependency hoặc reflection config cũ | Chuyển Jakarta Persistence và implementation phù hợp |
| Entity không được nhận diện | Annotation vẫn `javax.persistence.Entity` hoặc scan config lỗi | Kiểm tra imports, entity scan và ORM integration |
| `NoSuchMethodError` với Spring/Hibernate classes | Version conflict hoặc ABI mismatch | Xem BOM và runtime dependency graph |
| `NoSuchBeanDefinitionException` sau nâng starter | Auto-config không được nạp hoặc điều kiện đổi | Kiểm tra AutoConfiguration.imports và conditions |
| Security config không compile | API Security 5 bị loại/đổi | Chuyển `SecurityFilterChain` và request matchers |
| 404 với URL có trailing slash | Request matching behavior thay | Test route contract, khai báo mapping/redirect rõ |
| Validation không kích hoạt | Dùng annotations cũ hoặc thiếu implementation | Jakarta Validation và starter/config |
| SQL/HQL query fail | Hibernate ORM 6 semantics/API thay | Integration tests trên DB thật, sửa query |
| Metrics/traces mất | Observability stack hoặc exporter đổi | Micrometer/Tracing config và pipeline |
| `UnsupportedClassVersionError` | JVM runtime cũ hơn class files | Đồng bộ Java 17+ runtime |
| Java agent không instrument được | Agent/ASM/Byte Buddy version cũ | Nâng bytecode tooling |
| Tests pass nhưng behavior sai | Defaults và properties thay | Contract/integration tests và config audit |

Không quy mọi lỗi sau nâng Boot cho “Jakarta” nếu stack trace cho thấy dependency conflict, HQL behavior hoặc config property bị bỏ qua. Nên đọc exception gốc, version graph và điểm tích hợp thực tế.

## 24. Quy trình kiểm kê source theo namespace

Có thể rà soát mã nguồn và cấu hình:

~~~bash
rg -n "javax\.servlet|javax\.persistence|javax\.validation|javax\.annotation|javax\.transaction|javax\.mail" \
  src
~~~

Dùng công cụ phù hợp với hệ điều hành; `rg` là ripgrep. Kết quả là **danh sách cần phân loại**, không phải danh sách luôn phải thay toàn bộ.

Các nhóm cần điều tra riêng:

1. Import trực tiếp trong source viết tay.
2. Generated source/templates.
3. Annotation processors tạo code có `javax.*`.
4. Third-party libraries hoặc shaded JARs.
5. Reflection names trong `Class.forName` hoặc config.
6. Test fixtures và mock implementations.
7. Documentation có ví dụ cũ nhưng không được compile.
8. Config của application server hoặc deployment packaging.

### 24.1. Không dùng text replacement toàn repository như biện pháp duy nhất

Một lệnh thay mọi `javax.` thành `jakarta.` có thể phá các API Java SE còn hợp lệ và khiến code compile không đúng. Thực hiện migration bằng IDE refactoring/OpenRewrite recipe phù hợp hoặc thay theo danh sách API được kiểm tra; sau đó review imports và dependency graph.

## 25. OpenRewrite và tự động hóa migration

Các công cụ source transformation như OpenRewrite có thể giúp xử lý nhiều bước đổi import/API/config theo recipe. Chúng phù hợp nhất khi repository lớn và các biến đổi đã được nhà cung cấp công cụ mô tả rõ.

Tuy vậy, code rewrite không giải quyết trọn vẹn:

- SQL/schema compatibility.
- Security policy semantics.
- Runtime plugins chưa hỗ trợ Jakarta.
- Client API/HTTP contract.
- Observability và metrics dashboards.
- Custom reflection/bytecode transformations.
- Deployment và container compatibility.
- Data format và rollback.

Một quy trình an toàn là chạy recipe trên branch riêng, review diff, compile, kiểm tra dependency graph rồi thử các integration tests. Không xem “recipe completed” là bằng chứng đã migrate framework thành công.

## 26. Chiến lược migration có kiểm soát

Một lộ trình thực tế:

### Pha A — Chụp baseline Boot 2

Ghi chính xác Boot 2 version, JDK, framework dependencies, build plugins, runtime image, integration contracts, database schema, security policy và observability baseline. Đảm bảo tests hiện tại chạy thực sự và có logs/artifacts.

### Pha B — Đưa ứng dụng tới Boot 2.7 phù hợp

Nâng các dependencies và dọn deprecated APIs có thể thực hiện trên Boot 2. Đừng trì hoãn toàn bộ nâng cấp tooling cho tới lúc thay parent/plugin bằng Boot 3.

### Pha C — Chuyển Java baseline lên 17

Đồng bộ build/test/runtime toolchains và image. Xử lý annotation processors, Java agents, bytecode analyzers. Chạy tests trên Java 17 trước khi thay phần lớn framework khi chiến lược dự án cho phép.

### Pha D — Chuyển Jakarta và third-party libraries

Đổi imports chính xác, nâng Servlet/ORM/validation/mail/integration libraries tương thích Jakarta, loại dependency javax không cần. Cập nhật generated code và thư viện nội bộ dùng chung.

### Pha E — Nâng Spring Boot 3 và framework stack

Chọn Boot 3 target patch/minor phù hợp support policy; cập nhật parent/plugin/BOM, Security 6 config, Hibernate 6 integrations, auto-config registration và properties.

### Pha F — Xác minh hành vi

Chạy unit/integration/contract tests, đặc biệt HTTP mappings, validation, security, JPA queries/DDL, messaging và observability. Đánh giá hiệu năng/runtime.

### Pha G — Triển khai theo giai đoạn

Dùng staging/canary/rolling rollout khi phù hợp; quan sát lỗi 4xx/5xx, authentication failures, database exceptions, metrics, tracing và resource usage. Có kế hoạch rollback cả artifact và dữ liệu.

### Pha H — Dọn phụ thuộc tạm

Gỡ properties migrator, compatibility adapters, import/API cũ và runtime flags không cần; cập nhật runbook, BOM, SBOM và ownership.

Không nhất thiết mọi hệ thống phải thực hiện các pha trên theo một trật tự release cố định, nhưng mỗi pha cần có **tiêu chí hoàn thành và bằng chứng** để phân biệt nguyên nhân khi xảy ra lỗi.

## 27. Migration theo module trong monorepo

Một monorepo có thể chứa:

~~~text
platform/
├── common-model/
├── persistence/
├── web-api/
├── security/
├── external-client/
├── admin-service/
└── integration-tests/
~~~

Không nên để `common-model` hoặc `persistence` công bố public interface dùng `javax.persistence.*` nếu service Boot 3 phải tiêu thụ các types Jakarta tương ứng. Điều này có thể buộc phải điều chỉnh dependency boundaries.

### 27.1. Một thư viện dùng chung cho Boot 2 và Boot 3?

Nếu API công khai của một thư viện chứa `javax.servlet.Filter` hoặc `javax.persistence.Entity`, việc dùng cùng artifact không đổi cho cả hai hệ thường không khả thi đối với những extension points đó. Có thể cần:

- Tách core không phụ thuộc Servlet/JPA khỏi adapters.
- Phát hành adapters riêng cho javax và jakarta.
- Định nghĩa DTO/interface thuần Java cho phần business.
- Di chuyển các service theo từng nhóm tương thích.
- Có compatibility window và lộ trình xóa variant cũ.

Đừng cố làm library chung bằng cách nhét cả javax và jakarta APIs vào cùng một public method signature mà không có thiết kế rõ; điều đó tăng coupling và nguy cơ classpath conflicts.

### 27.2. REST contract có thể giữ nguyên dù Java API đổi

Một server chuyển `javax.servlet` sang `jakarta.servlet` vẫn có thể giữ HTTP JSON contract đối với external clients nếu URL, JSON schema, headers, status codes và authentication semantics không đổi. Đây là lý do nên bảo vệ **client-facing contracts** bằng tests thay vì chỉ cố giữ source import tương thích.

## 28. Thiết kế regression tests theo vùng rủi ro

| Vùng | Tình huống cần kiểm chứng | Vì sao quan trọng |
|---|---|---|
| Startup | ApplicationContext load, auto-config, custom beans | Phát hiện starter/condition incompatibility |
| Java baseline | JDK 17+ build/test/runtime | Tránh class-file mismatch |
| Routing | Các URI, slash, path variables, methods | Phát hiện Spring MVC behavior changes |
| JSON | Serialization/deserialization, enums, dates | Giữ API contract |
| Validation | Request sai constraint và error response | Phát hiện Jakarta Validation thiếu |
| Security | Public/private endpoints, auth, CSRF, CORS | Không làm yếu policy |
| JPA | CRUD, queries, relations, converters | Hibernate 6 differences |
| Database | Schema, sequence, migrations, locking | Tránh data loss/regressions |
| Messaging | Producer/consumer, serialization, retry | Integration compatibility |
| Observability | Metrics, trace propagation, health | Không mất giám sát |
| Deployment | WAR/JAR/container, ports, readiness | Runtime tương thích Jakarta |
| Performance | Startup, p95/p99, heap, pool | Regression sau nâng |
| Rollback | Old/new data/API compatibility | Có đường lui khi production lỗi |

Một test suite chỉ kiểm tra HTTP 200 cho `/actuator/health` không đủ chứng minh các chức năng doanh nghiệp, database queries và security controls tương thích.

### 28.1. Security negative tests

Ngoài test một yêu cầu được phép, cần test những yêu cầu **phải bị từ chối**. Ví dụ resource server phải reject token sai issuer hoặc thiếu quyền. Nếu chỉ test happy path sau migration, lỗi cấu hình cho phép quá rộng có thể bị bỏ qua.

### 28.2. JPA tests với migration schema

Chạy tests trên database tương tự production khi có thể, với Flyway/Liquibase scripts và dữ liệu đại diện. Kiểm tra không có DDL thay ngoài kế hoạch, sequence mismatch hoặc truy vấn tạo dữ liệu sai.

### 28.3. So sánh observability

Giữ baseline metric/trace trước migration. Sau đó xác minh tên metrics, labels, trace correlation, log fields và alerts, không chỉ việc actuator endpoint tồn tại.

## 29. Những sai lầm phổ biến

### 29.1. “Chỉ cần thay Spring Boot version”

Sai vì Boot 3 đồng thời thay Java baseline, Spring Framework, Jakarta APIs và nhiều frameworks/dependencies. Cần kế hoạch theo vùng rủi ro.

### 29.2. “Thay tất cả javax thành jakarta”

Có thể phá `javax.net.ssl`, `javax.sql`, `javax.crypto` và các Java SE APIs khác. Phân loại theo package/API owner.

### 29.3. “Thêm javax.servlet-api để giữ library cũ”

Đó không phải cầu nối hợp lệ giữa Java EE Servlet và Jakarta Servlet. Cần bản thư viện tương thích Jakarta hoặc adapter có chủ đích theo contract.

### 29.4. “Ứng dụng start được nghĩa ORM đã ổn”

Các queries, converters, sequence generators hoặc database writes chỉ lỗi khi thực thi. Cần tests với dữ liệu và database phù hợp.

### 29.5. “Bỏ Security config để test pass”

Nếu lỗi compile ở `WebSecurityConfigurerAdapter`, phải chuyển sang mô hình cấu hình Security 6 và xác minh policy, không xóa lớp bảo vệ hoặc cho phép mọi URL.

### 29.6. “Nâng một dependency mà bỏ qua BOM”

Thay Spring Framework/Hibernate/Security riêng lẻ có thể tạo runtime linkage errors. Ưu tiên tổ hợp versions tương thích với Boot release đã chọn.

### 29.7. “Properties migrator sẽ sửa tất cả”

Công cụ này hỗ trợ một số configuration keys, không tự sửa API Java, data schemas, security policy hoặc các thay đổi hành vi. Dùng tạm thời và gỡ khi xong.

### 29.8. “Không cần thử trên external container”

Một WAR Jakarta không thể giả định chạy trên container chỉ hỗ trợ `javax.servlet`. Kiểm tra Servlet API level và server version.

### 29.9. “Sleuth/metric hiện tại tự hoạt động như cũ”

Observability là phần cần migration và kiểm chứng riêng. Một service không có distributed trace dù hoạt động nghiệp vụ vẫn gây thiệt hại cho vận hành.

### 29.10. “Rollback chỉ là chạy lại image cũ”

Nếu Hibernate migration hoặc service mới đã thay database schema/dữ liệu, chạy lại image Boot 2 có thể không an toàn. Cần kế hoạch data compatibility và rollback thực tế.

## 30. Bảng kiểm trước khi đưa Boot 3 vào production

- [ ] Đã chọn chính xác Boot 3 minor/patch release và đọc migration/release notes phù hợp.
- [ ] Đã xác định Java baseline ít nhất 17 cho compiler, tests và production JVM.
- [ ] Build tool wrapper, plugin và các Java agents hỗ trợ JDK mục tiêu.
- [ ] Dependency graph không trộn các phiên bản Spring Framework 5/6 sai phạm vi.
- [ ] Những API Servlet, JPA, Validation, lifecycle cần thiết đã chuyển sang Jakarta.
- [ ] Các API Java SE `javax.*` vẫn được giữ đúng, không thay mù quáng.
- [ ] Third-party starters và internal shared libraries có bản hỗ trợ Boot 3/Jakarta.
- [ ] SecurityFilterChain và request/method authorization đã được test.
- [ ] Các endpoint HTTP, mapping/trailing slash và error contracts đã được kiểm chứng.
- [ ] DTO Bean Validation và custom ConstraintValidator sử dụng Jakarta đúng.
- [ ] Entity/repository, Hibernate 6, queries, converters và DDL đã được kiểm tra.
- [ ] Database migrations có backup, validation và rollback strategy.
- [ ] Auto-configuration của starter nội bộ được đăng ký theo cơ chế Boot 3.
- [ ] Configuration property keys/defaults đã được rà và properties migrator đã được gỡ khi hoàn tất.
- [ ] Observability, tracing, Actuator security và alerts đã được kiểm chứng.
- [ ] Coverage, test runners và static analyzers chạy được trên JDK mới.
- [ ] Integration tests trên database/message broker và external services đại diện đã pass.
- [ ] Artifact JAR/WAR/container runtime đúng JDK và Jakarta container compatibility.
- [ ] Đã so sánh performance/resources và thử restart/failure recovery.
- [ ] Rollout, monitoring, data compatibility và rollback runbook đã sẵn sàng.

Checklist là nội dung hướng dẫn của bài học, **không phải xác nhận dự án cụ thể đã thực hiện hay vượt qua các bước**.

## 31. Mẫu báo cáo migration

Một mẫu cấu trúc ghi trạng thái kỹ thuật:

~~~yaml
springBootMigration:
  application: "orders-service"
  from:
    springBoot: "2.7.x"
    java: "11"
    servletApi: "javax.servlet"
  target:
    springBoot: "3.x"
    java: "17"
    servletApi: "jakarta.servlet"
  dependencies:
    springFramework6Reviewed: false
    springSecurity6Reviewed: false
    hibernate6Reviewed: false
    thirdPartyStartersReviewed: false
  source:
    jakartaImportsMigrated: false
    javaSeJavaxImportsPreserved: false
    generatedCodeReviewed: false
  config:
    autoConfigurationReviewed: false
    propertiesReviewed: false
    securityPolicyVerified: false
  tests:
    startupPassed: false
    webContractPassed: false
    validationPassed: false
    persistencePassed: false
    observabilityPassed: false
    productionLikeRuntimePassed: false
  deployment:
    canaryPlanned: false
    rollbackPlanned: false
  owner: "application-team"
  status: "in-progress"
~~~

Các giá trị và tên service chỉ để minh họa. Trong báo cáo thật nên thay `3.x` bằng exact release, kèm build/commit, artifact checksum, kết quả tests, evidence links và người phê duyệt.

## 32. Nguyên tắc cốt lõi

- **Spring Boot 3 yêu cầu Java 17 trở lên** và dùng Spring Framework 6, vì vậy nâng Boot 2 → 3 là nâng baseline platform chứ không chỉ thay parent/plugin version.
- **Jakarta chuyển nhiều enterprise APIs từ javax sang jakarta**, nhất là Servlet, JPA và Validation. Không áp dụng phép đổi tên hàng loạt lên các Java SE APIs như `javax.net.ssl` hoặc `javax.sql`.
- **`javax.servlet.Filter` và `jakarta.servlet.Filter` là hai types khác nhau.** Thêm legacy API JAR không biến thư viện cũ thành Jakarta-compatible.
- **Servlet container, ORM, Security, Spring Data và third-party starters phải tương thích đồng bộ** với bản Boot 3 mục tiêu.
- **Hibernate ORM 6 cần kiểm tra queries, custom types, identifier/schema behavior**, không chỉ sửa imports của entity.
- **Spring Security 6 ưu tiên mô hình SecurityFilterChain**, đồng thời phải xác minh HTTP và method authorization, CSRF, token validation và các negative tests.
- **Auto-configuration và configuration properties có thay đổi**, cần rà starter nội bộ, resource registrations và defaults.
- **Observability cần migration riêng** khi hệ thống dùng Sleuth/tracing hoặc phụ thuộc metrics/alerts cũ.
- **Build và runtime JDK có thể khác nhau**, do đó phải kiểm tra compiler, test runner, Java agent, artifact và production image.
- **Một bản nâng cấp phải có integration/contract/security/data tests**, không kết luận từ compile success hoặc ApplicationContext startup.
- **Tách giai đoạn Boot 2.7, Java 17, Jakarta/framework migration và production rollout** khi phù hợp để giảm số biến thay đổi trong từng lượt.
- **Rollback cần tính đến schema/data và API contracts**, không chỉ khả năng chạy lại container image cũ.

Khi chuyển từ Spring Boot 2 sang 3, mục tiêu bền vững là đưa toàn bộ hệ thống về **một nền tảng Java 17+ và Jakarta nhất quán**, cập nhật những thư viện tương tác với Spring Framework 6, giữ đúng hợp đồng bảo mật/dữ liệu và chứng minh hành vi trên runtime đích. Đó là điều kiện để Java Advance Compatibility Migration không chỉ hoàn thành về mặt biên dịch, mà còn an toàn trong triển khai, vận hành và những lần nâng cấp tiếp theo.
