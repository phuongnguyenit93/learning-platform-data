# Namespace javax và jakarta khi chuyển thế hệ Spring Boot

Khi nâng ứng dụng từ Spring Boot 2 lên Spring Boot 3, nhiều import bắt đầu bằng `javax.*` phải chuyển sang `jakarta.*`. Đây là thay đổi namespace của các API Java EE được chuyển sang Jakarta EE, không phải quy tắc đổi tên mọi package bắt đầu bằng `javax`.

Spring Boot 3 sử dụng Spring Framework 6 và Jakarta EE 10. Các API như Servlet, Persistence và Bean Validation chuyển sang package `jakarta.*`; dependency tương ứng cũng phải được nâng cấp. Spring Boot 4 tiếp tục dùng namespace `jakarta`, dựa trên Jakarta EE 11 và Spring Framework 7. Vì vậy, khi chuyển từ Boot 3 lên Boot 4, công việc chính là nâng phiên bản API/specification và thư viện tương thích, không phải thực hiện thêm một lần đổi `javax` sang `jakarta`.

Với springdoc-openapi, cần kiểm tra cả hai trục độc lập:

1. Namespace của API nền tảng mà ứng dụng sử dụng, ví dụ `jakarta.servlet` và `jakarta.validation`.
2. Major version của springdoc tương thích với Spring Boot: nhánh 1.x cho Boot 2, 2.x cho Boot 3 và 3.x cho Boot 4.

## 1. Vì sao có hai namespace?

Java EE được chuyển sang Jakarta EE sau khi quyền quản lý nền tảng được chuyển cho Eclipse Foundation. Jakarta EE 9 thực hiện thay đổi package namespace từ `javax.*` sang `jakarta.*` đối với các API thuộc Jakarta EE. Mục tiêu là tạo một namespace mới do Jakarta EE quản lý.

Tên lớp có thể giống nhau nhưng package là một phần của tên kiểu Java. Ví dụ:

`javax.servlet.http.HttpServletRequest`

và

`jakarta.servlet.http.HttpServletRequest`

là hai kiểu khác nhau đối với JVM. Chúng không thể thay thế nhau chỉ vì cùng tên lớp. Một thư viện được biên dịch với kiểu `javax.servlet.Filter` không tự động tương thích với container yêu cầu `jakarta.servlet.Filter`.

Điều này ảnh hưởng tới:

- Import trong mã Java, Kotlin và Groovy.
- Dependency trực tiếp và dependency bắc cầu.
- Annotation và interface mà framework tìm kiếm lúc runtime.
- Chữ ký method trong thư viện đã biên dịch.
- XML descriptor, service provider và cấu hình reflection.
- Generated source, annotation processor và test fixture.

## 2. Ranh giới namespace theo thế hệ Spring

| Thế hệ | Spring Framework | Nền tảng Enterprise API | Namespace chính |
|---|---|---|---|
| Spring Boot 2.x | Spring Framework 5.x (Boot 2.7.x dùng 5.3.x) | Java EE 7/8; mốc mới nhất của dòng này gồm Servlet 4.0, JPA 2.2, Bean Validation 2.0 | `javax.*` cho các API Java EE |
| Spring Boot 3.x | Spring Framework 6.x | Jakarta EE 9/10; Boot 3.0 dùng Servlet 6.0 và JPA 3.1 | `jakarta.*` cho các API Jakarta EE |
| Spring Boot 4.x | Spring Framework 7.x | Jakarta EE 11 baseline; Servlet 6.1, JPA 3.2, Bean Validation 3.1 | Tiếp tục `jakarta.*` |

Các phiên bản đặc tả trong bảng là mốc nền tảng của từng thế hệ. Hãy kiểm tra compatibility matrix và dependency management của patch release đang dùng trước khi nâng ứng dụng.

### 2.1. Chuyển từ Boot 2 lên Boot 3

Đây là bước đổi namespace lớn nhất:

- Spring Boot 3 yêu cầu Java 17 trở lên.
- Spring Framework 6 chuyển sang Jakarta EE namespace.
- Các API Jakarta EE mà ứng dụng dùng phải có dependency tương thích.
- Thư viện bên thứ ba phải cung cấp bản hỗ trợ Jakarta.
- Import, XML descriptor và cấu hình liên quan phải được cập nhật.

Spring Boot migration guide khuyến nghị nâng ứng dụng lên bản mới nhất của dòng 2.7.x trước khi chuyển sang Boot 3. Cách này giúp xử lý deprecation và dependency ở thế hệ cũ trước khi thay đổi nền tảng.

### 2.2. Chuyển từ Boot 3 lên Boot 4

Boot 4 không quay lại `javax`. Ứng dụng tiếp tục dùng Jakarta namespace, nhưng cần kiểm tra API level và dependency mới:

- Spring Framework 7.x.
- Jakarta EE 11 baseline.
- Servlet 6.1.
- JPA 3.2.
- Bean Validation 3.1.
- Các thư viện tích hợp phải hỗ trợ Spring Framework 7 và Jakarta EE 11.

Boot 4 còn có thay đổi module/starter và loại bỏ một số API đã deprecated trong Boot 3. Không nên coi việc compile được sau khi đổi version Boot là bằng chứng toàn bộ dependency đã tương thích.

## 3. Những package thường phải chuyển

Bảng dưới đây liệt kê các cặp package thường gặp trong ứng dụng Spring:

| API trước đây | API sau migration | Thường xuất hiện ở |
|---|---|---|
| `javax.servlet.*` | `jakarta.servlet.*` | Servlet, Filter, Listener, request/response |
| `javax.persistence.*` | `jakarta.persistence.*` | JPA entity, repository mapping, persistence annotations |
| `javax.validation.*` | `jakarta.validation.*` | Bean Validation, `@Valid`, constraint annotations |
| `javax.transaction.Transactional`, `javax.transaction.UserTransaction` | `jakarta.transaction.Transactional`, `jakarta.transaction.UserTransaction` | JTA annotations và transaction API |
| `javax.annotation.PostConstruct`, `javax.annotation.PreDestroy`, `javax.annotation.Resource` | `jakarta.annotation.*` | Lifecycle và resource injection |
| `javax.inject.*` | `jakarta.inject.*` | `@Inject`, `@Named`, `@Qualifier` của JSR-330 |
| `javax.websocket.*` | `jakarta.websocket.*` | WebSocket endpoint và session |
| `javax.ws.rs.*` | `jakarta.ws.rs.*` | JAX-RS API và implementation |
| `javax.xml.bind.*` | `jakarta.xml.bind.*` | JAXB marshalling/unmarshalling |
| `javax.mail.*` | `jakarta.mail.*` | Mail API |

Chỉ thay các package thuộc specification tương ứng. Một số thư viện có thể dùng API cùng tên từ một namespace khác; kiểm tra tài liệu của thư viện và dependency trước khi sửa.

Với Dependency Injection, hãy xác định artifact đang dùng. Jakarta Dependency Injection 2.x cung cấp package `jakarta.inject`; thư viện cũ biên dịch với `javax.inject` vẫn có thể cần bản tương thích riêng. Chuyển import và dependency cùng nhau theo phiên bản specification mà ứng dụng chọn.

### 3.1. Những package javax vẫn giữ nguyên

Không phải package `javax` nào cũng thuộc Java EE/Jakarta EE. Nhiều package là một phần của Java SE và không đổi namespace:

| Package vẫn giữ `javax` | Ví dụ |
|---|---|
| `javax.sql` | `DataSource`, `ConnectionPoolDataSource` |
| `javax.transaction.xa` | `XAResource`, `XAException`, `Xid` |
| `javax.crypto` | `Cipher`, `SecretKey`, `Mac` |
| `javax.net` và `javax.net.ssl` | `SocketFactory`, `SSLContext`, `SSLSocket` |
| `javax.xml.parsers` | `DocumentBuilder`, `SAXParser` |
| `javax.xml.stream` | `XMLInputFactory`, `XMLStreamReader` |
| `javax.naming` | `Context`, `InitialContext` |
| `javax.management` | JMX API |
| `javax.annotation.processing` | Annotation processing API của Java |

Ví dụ, `javax.sql.DataSource` vẫn là kiểu đúng khi ứng dụng dùng JDBC. Đổi nó thành `jakarta.sql.DataSource` là sai vì không có Jakarta SQL API tương ứng.

**Quy tắc thực tế:** xác định package thuộc Java SE hay thuộc một Jakarta EE specification trước khi thay import. Không chạy global replace `javax` thành `jakarta`.

## 4. Chuyển import trong mã Spring Boot

### 4.1. Servlet API

Trước migration:

~~~java
import java.io.IOException;
import javax.servlet.Filter;
import javax.servlet.FilterChain;
import javax.servlet.ServletException;
import javax.servlet.ServletRequest;
import javax.servlet.ServletResponse;
import javax.servlet.http.HttpServletRequest;

public class RequestAuditFilter implements Filter {
    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain
    ) throws IOException, ServletException {
        HttpServletRequest httpRequest = (HttpServletRequest) request;
        chain.doFilter(httpRequest, response);
    }
}
~~~

Sau migration:

~~~java
import java.io.IOException;
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.http.HttpServletRequest;

public class RequestAuditFilter implements Filter {
    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain
    ) throws IOException, ServletException {
        HttpServletRequest httpRequest = (HttpServletRequest) request;
        chain.doFilter(httpRequest, response);
    }
}
~~~

Logic filter có thể giữ nguyên, nhưng mọi kiểu Servlet trong chữ ký method phải cùng namespace với container. Một filter `javax.servlet.Filter` không đăng ký được như filter `jakarta.servlet.Filter`.

### 4.2. Bean Validation

Trước migration:

~~~java
import javax.validation.Valid;
import javax.validation.constraints.NotBlank;
import javax.validation.constraints.Positive;

public record CreateProductRequest(
        @NotBlank String name,
        @Positive long price
) {}

public ProductResponse create(
        @Valid @RequestBody CreateProductRequest request
) {
    // xử lý request
}
~~~

Sau migration:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;

public record CreateProductRequest(
        @NotBlank String name,
        @Positive long price
) {}

public ProductResponse create(
        @Valid @RequestBody CreateProductRequest request
) {
    // xử lý request
}
~~~

Nếu vẫn dùng constraint annotation thuộc `javax.validation`, provider Jakarta Validation của Boot 3 có thể không nhận diện chúng như constraint của Jakarta API. Kết quả có thể là validation không chạy hoặc lỗi khi tích hợp các kiểu annotation.

### 4.3. JPA

Trước migration:

~~~java
import javax.persistence.Entity;
import javax.persistence.GeneratedValue;
import javax.persistence.GenerationType;
import javax.persistence.Id;
import javax.persistence.Table;

@Entity
@Table(name = "products")
class ProductEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
}
~~~

Sau migration:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "products")
class ProductEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
}
~~~

Tên annotation và logic mapping trong ví dụ không đổi. Tuy nhiên, JPA provider và version specification thay đổi cùng thế hệ Spring; cần kiểm tra query, mapping, dialect và schema generation bằng integration test.

### 4.4. Annotation của Spring không tự đổi namespace

Các annotation thuộc Spring Framework vẫn giữ package `org.springframework.*`, ví dụ:

- `org.springframework.web.bind.annotation.RestController`
- `org.springframework.web.bind.annotation.RequestMapping`
- `org.springframework.beans.factory.annotation.Autowired`
- `org.springframework.transaction.annotation.Transactional`
- `org.springframework.stereotype.Service`

Phân biệt `org.springframework.transaction.annotation.Transactional` với `javax.transaction.Transactional`. Nếu ứng dụng dùng JTA annotation, package tương ứng chuyển thành `jakarta.transaction.Transactional`. Không đổi annotation Spring sang một package `jakarta` chỉ vì tên annotation giống nhau.

## 5. Dependency cũng phải đổi theo namespace

Sửa import mà vẫn giữ API jar cũ sẽ khiến compile hoặc runtime thất bại. Với ứng dụng dùng Spring Boot starters, ưu tiên dependency được Spring Boot quản lý thay vì tự pin version của Jakarta API.

| Dependency cũ | Hướng thay thế |
|---|---|
| `javax.servlet:javax.servlet-api` | `jakarta.servlet:jakarta.servlet-api` |
| `javax.validation:validation-api` | `jakarta.validation:jakarta.validation-api` |
| `javax.persistence:javax.persistence-api` | `jakarta.persistence:jakarta.persistence-api` |
| Java EE API bundle cũ | Các Jakarta API artifact tương ứng do platform/dependency management quản lý |

Trong Spring Boot, thường nên dùng starter phù hợp, ví dụ `spring-boot-starter-validation` hoặc `spring-boot-starter-data-jpa`, thay vì tự thêm API và implementation rời rạc. Servlet API thường được cung cấp qua web starter và container; chỉ khai báo trực tiếp khi có yêu cầu build cụ thể như compile-only/provided.

### 5.1. Không trộn hai API của cùng specification

Một dependency cũ có thể kéo theo `javax.servlet-api` trong khi ứng dụng chạy trên container Jakarta. Dù source code của ứng dụng đã chuyển sang `jakarta.servlet`, thư viện cũ vẫn có thể tham chiếu kiểu `javax.servlet`.

Kiểm tra dependency tree:

~~~bash
# Maven
mvn dependency:tree

# Tìm các artifact Java EE cũ trong cây dependency
mvn dependency:tree -Dincludes=javax.servlet:*,javax.validation:*,javax.persistence:*

# Gradle
./gradlew dependencies --configuration runtimeClasspath
~~~

Khi phát hiện dependency cũ:

1. Nâng thư viện lên bản hỗ trợ Jakarta.
2. Nếu dependency cũ không còn được dùng, loại bỏ nó khỏi build.
3. Nếu dependency bắc cầu kéo API cũ, kiểm tra release mới hoặc exclusion có kiểm soát.
4. Không loại API cũ một cách mù quáng nếu thư viện vẫn cần nó; khi đó cần thay thư viện hoặc tạo ranh giới tương thích riêng.

Không giữ đồng thời hai API của cùng specification chỉ để làm compile pass. Hai namespace là hai tập kiểu độc lập và có thể gây lỗi khi framework trao đổi object qua interface.

## 6. Thư viện bên thứ ba phải hỗ trợ Jakarta

Ứng dụng có thể đã đổi import nhưng vẫn thất bại vì một thư viện cũ được biên dịch dựa trên `javax.*`. Các nhóm thư viện cần rà soát:

- Servlet filter, listener, security adapter và embedded container extension.
- JPA provider, Hibernate extension, custom type và auditing library.
- Validation provider và custom constraint.
- SOAP/JAX-WS, JAXB, JAX-RS, mail và WebSocket implementation.
- Report engine, document processor và thư viện tích hợp server.
- Test utilities, mock server, test container và annotation processor.

Một thư viện tương thích Boot 2 không tự động tương thích Boot 3. Kiểm tra release notes hoặc compatibility matrix của thư viện. Nếu nhà cung cấp có nhánh Jakarta, nâng lên nhánh đó; nếu không có, cân nhắc thay thế hoặc giữ thành phần legacy trong một service riêng có ranh giới giao tiếp rõ ràng.

### 6.1. Vì sao không thể chỉ ép cast?

Giả sử một thư viện cũ nhận:

~~~java
public void register(javax.servlet.Filter filter) {
    // ...
}
~~~

Ứng dụng Boot 3 cung cấp:

~~~java
jakarta.servlet.Filter filter = new RequestAuditFilter();
~~~

Hai kiểu này không có quan hệ kế thừa. Không thể cast `jakarta.servlet.Filter` thành `javax.servlet.Filter`. Cần phiên bản thư viện được biên dịch với Jakarta API hoặc thay thế adapter.

## 7. springdoc-openapi và Swagger annotations khi migration

Namespace Jakarta của ứng dụng và version springdoc là hai quyết định khác nhau.

| Spring Boot | Spring Framework | Nhánh springdoc phù hợp | Ghi chú |
|---|---|---|---|
| 2.x | 5.3.x | 1.x; 1.8.0 là bản open-source cuối cho Boot 2/1 | Dùng module legacy. |
| 3.x | 6.x | 2.x | Dùng starter module của springdoc v2. |
| 4.x | 7.x | 3.x | Dùng nhánh springdoc tương thích Boot 4. |

Ví dụ dependency cho Spring MVC:

~~~xml
<!-- Spring Boot 2 / springdoc v1 -->
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-ui</artifactId>
    <version>1.8.0</version>
</dependency>
~~~

~~~xml
<!-- Spring Boot 3 / springdoc v2 -->
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>${springdoc.version}</version>
</dependency>
~~~

~~~xml
<!-- Spring Boot 4 / springdoc v3 -->
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>${springdoc.version}</version>
</dependency>
~~~

Đặt version theo compatibility matrix hiện hành. Không dùng springdoc 3.x với Boot 3 hoặc springdoc 2.x với Boot 4 chỉ vì artifact name giống nhau.

### 7.1. Swagger annotations không đổi sang jakarta

Các annotation OpenAPI vẫn thuộc package:

`io.swagger.v3.oas.annotations.*`

Ví dụ `@Operation`, `@Parameter`, `@Schema`, `@ApiResponse`, `@SecurityScheme` không chuyển thành `jakarta.swagger.*`. Chúng không phải Jakarta EE APIs.

### 7.2. Package của springdoc có thể đổi riêng

Từ springdoc v1 lên v2 có một số package/class thay đổi:

| springdoc v1 | springdoc v2 |
|---|---|
| `org.springdoc.core.GroupedOpenApi` | `org.springdoc.core.models.GroupedOpenApi` |
| `org.springdoc.core.SpringDocUtils` | `org.springdoc.core.utils.SpringDocUtils` |
| `org.springdoc.api.annotations.ParameterObject` | `org.springdoc.core.annotations.ParameterObject` |
| `org.springdoc.core.customizers.OpenApiCustomiser` | `org.springdoc.core.customizers.OpenApiCustomizer` |

Đây là thay đổi API của springdoc, không phải đổi namespace Java EE. Hãy xử lý song song nhưng phân loại đúng nguyên nhân để tránh thay import nhầm.

## 8. XML descriptor, service loader và generated source

Migration không chỉ nằm trong file `.java`. Tìm kiếm cả:

- `web.xml`, `web-fragment.xml`.
- `persistence.xml`, `orm.xml`.
- `beans.xml` và descriptor của Jakarta EE module.
- `META-INF/services/*`.
- `module-info.java`.
- Generated source trong `target/generated-sources` hoặc `build/generated`.
- Reflection/native-image configuration.
- Kotlin, Groovy và test source.

Ví dụ descriptor Servlet cũ có thể dùng namespace XML Java EE:

~~~xml
<web-app xmlns="http://xmlns.jcp.org/xml/ns/javaee"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           http://xmlns.jcp.org/xml/ns/javaee
           http://xmlns.jcp.org/xml/ns/javaee/web-app_4_0.xsd"
         version="4.0">
</web-app>
~~~

Với Servlet 6.0, descriptor dùng namespace Jakarta EE và schema tương ứng:

~~~xml
<web-app xmlns="https://jakarta.ee/xml/ns/jakartaee"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           https://jakarta.ee/xml/ns/jakartaee
           https://jakarta.ee/xml/ns/jakartaee/web-app_6_0.xsd"
         version="6.0">
</web-app>
~~~

Khi lên Boot 4/Servlet 6.1, cập nhật descriptor theo schema version tương ứng. Nếu ứng dụng không đóng gói descriptor vì dùng cấu hình Spring Java-based, không cần tạo file chỉ để hoàn thành migration.

### 8.1. Service provider file

Một thư viện có thể đăng ký implementation qua `META-INF/services`. Nếu interface thuộc Jakarta API, tên interface trong file service cũng phải là tên Jakarta mới. Kiểm tra file service được đóng gói trong JAR và các file do annotation processor sinh.

## 9. Cách tìm các import cần đổi

Bắt đầu bằng tìm kiếm có phạm vi, không thay toàn bộ chuỗi `javax`:

~~~bash
# Ví dụ tìm các namespace Jakarta EE thường gặp trong source
rg -n "javax\.(servlet|persistence|validation|transaction|annotation|inject|ws\.rs|websocket|xml\.bind|mail)" \
  src pom.xml build.gradle build.gradle.kts

# Tìm import còn sót sau migration
rg -n "^import javax\.(servlet|persistence|validation|transaction)" \
  src
~~~

Sau khi cập nhật, tìm ngược các dependency Java EE cũ:

~~~bash
mvn dependency:tree | rg "javax\.(servlet|persistence|validation)|javax.servlet-api|validation-api"
~~~

Lệnh tìm kiếm chỉ tạo danh sách cần review. Một kết quả `javax.annotation.processing` hoặc `javax.sql` không phải lỗi migration. Xem package và API cụ thể trước khi sửa.

## 10. Lỗi thường gặp khi namespace không đồng nhất

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `package javax.servlet does not exist` | Dependency Servlet cũ đã bị loại hoặc source chưa chuyển namespace | Đổi import sang `jakarta.servlet` và dùng dependency/container tương thích. |
| `package jakarta.validation does not exist` | Chưa có Jakarta Validation API/starter phù hợp | Thêm validation starter hoặc dependency do Boot quản lý. |
| `NoClassDefFoundError: javax/servlet/...` | Một thư viện cũ vẫn tham chiếu Servlet namespace cũ | Nâng/thay thư viện, kiểm tra dependency tree và runtime classpath. |
| `ClassNotFoundException: javax.persistence...` | JPA extension hoặc persistence library cũ | Nâng sang bản hỗ trợ Jakarta Persistence. |
| `ClassCastException` giữa kiểu `javax` và `jakarta` | Hai API cùng tên nhưng khác type identity | Đồng bộ toàn bộ dependency ở một namespace cho specification đó. |
| Filter không được container nhận | Filter implement `javax.servlet.Filter` trên container Jakarta | Chuyển sang `jakarta.servlet.Filter` hoặc nâng thư viện cung cấp filter. |
| Bean Validation không chạy | Constraint annotation vẫn từ `javax.validation` | Chuyển annotation và provider sang Jakarta Validation. |
| JPA entity không được phát hiện | Entity dùng `javax.persistence.Entity` trong runtime Jakarta | Đổi import, kiểm tra scan package và provider. |
| Springdoc không hiển thị endpoint hoặc schema | Springdoc version không tương thích hoặc dependency cũ gây lỗi khởi động/scan | Chọn đúng nhánh springdoc và kiểm tra generated OpenAPI. |
| `NoSuchMethodError` ở integration library | Thư viện được biên dịch với API/framework khác thế hệ | Đồng bộ phiên bản thư viện và Spring/Jakarta API; kiểm tra classpath. |

Không phải mọi `NoSuchMethodError` đều do namespace. Đây là lỗi linkage tổng quát; cần xác định class và method descriptor được nạp trước khi kết luận.

## 11. Kiểm tra dependency và classpath

### 11.1. Maven

Xem dependency tree và tìm API cũ:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dincludes=javax.servlet:javax.servlet-api
mvn dependency:tree -Dincludes=javax.validation:validation-api
mvn dependency:tree -Dincludes=javax.persistence:javax.persistence-api
~~~

Kiểm tra dependency nào kéo API cũ vào runtime. Nếu thư viện đã có phiên bản Jakarta, nâng nó trước khi thêm exclusion. Dùng Spring Boot parent/BOM để quản lý version đồng bộ.

### 11.2. Gradle

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency javax.servlet --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jakarta.servlet --configuration runtimeClasspath
~~~

`compileClasspath` giúp phát hiện kiểu cũ còn xuất hiện lúc biên dịch; `runtimeClasspath` giúp phát hiện thư viện cũ được đóng gói hoặc nạp khi chạy.

### 11.3. Kiểm tra bytecode khi source không còn import cũ

Thư viện đã biên dịch có thể vẫn tham chiếu `javax.*` dù source của ứng dụng không còn. `jdeps` có thể giúp kiểm tra dependency ở cấp class:

~~~bash
jdeps --ignore-missing-deps -verbose:class target/application.jar
~~~

Đối với executable Spring Boot JAR, cần phân tích các thư viện bên trong `BOOT-INF/lib` nếu công cụ không tự đọc nested JAR. Có thể giải nén artifact trong thư mục build tạm và chạy `jdeps` trên từng JAR cần điều tra.

## 12. Migration tool và cách dùng có kiểm soát

Một số công cụ có thể giảm thao tác lặp:

| Công cụ | Hỗ trợ |
|---|---|
| OpenRewrite | Recipe nâng Spring Boot và chuyển một số package/import, dependency và cấu hình. |
| Spring Boot Migrator | Phân tích một số thay đổi và đề xuất bước migration. |
| IntelliJ IDEA migration/refactoring | Tìm usage, đổi import và hỗ trợ refactor theo scope. |
| `jdeps` | Phân tích dependency giữa class và package trong bytecode. |

Công cụ tự động chỉ nên tạo bản thay đổi để review. Không chạy recipe rồi bỏ qua kết quả ở dependency bắc cầu, XML descriptor, generated code và thư viện không có bản Jakarta.

Quy trình an toàn:

1. Commit hoặc tạo nhánh migration để có điểm quay lại.
2. Chạy tool trên phạm vi module đã chọn.
3. Review từng package được đổi.
4. Kiểm tra dependency tree và generated source.
5. Chạy compile, unit test và integration test.
6. So sánh OpenAPI document được sinh trước/sau.

## 13. Quy trình nâng cấp ứng dụng có springdoc

### 13.1. Từ Boot 2 lên Boot 3

1. Nâng ứng dụng lên bản mới nhất của dòng Boot 2.7.x.
2. Ghi lại Java, Spring Boot, Spring Framework, springdoc và dependency liên quan.
3. Kiểm tra thư viện nào còn phụ thuộc `javax.servlet`, `javax.persistence` hoặc `javax.validation`.
4. Nâng các thư viện bên thứ ba lên bản hỗ trợ Jakarta.
5. Chuyển import thuộc Jakarta EE sang `jakarta.*`; giữ nguyên Java SE `javax.*`.
6. Cập nhật dependency coordinate hoặc dùng starter do Spring Boot quản lý.
7. Chuyển springdoc từ v1 sang v2 và cập nhật starter/import riêng của springdoc.
8. Cập nhật XML descriptor, service loader và generated source nếu có.
9. Chạy compile, test và kiểm tra runtime.
10. So sánh OpenAPI JSON/YAML và Swagger UI với baseline.

### 13.2. Từ Boot 3 lên Boot 4

1. Nâng ứng dụng lên bản mới nhất của dòng Boot 3.5.x.
2. Rà soát deprecation đã tồn tại trong Boot 3.
3. Nâng Spring Framework và Jakarta API theo Boot 4/Jakarta EE 11.
4. Kiểm tra Servlet 6.1, JPA 3.2 và Bean Validation 3.1 compatibility.
5. Rà soát module/starter mới và các integration đã bị loại bỏ hoặc thay thế.
6. Chọn springdoc v3 tương thích Boot 4.
7. Không chạy global `javax` → `jakarta`; phần lớn ứng dụng đã dùng Jakarta từ Boot 3.
8. Chạy toàn bộ integration test và kiểm tra OpenAPI output.

## 14. Kiểm tra Springdoc sau migration

Springdoc đọc controller, annotation, cấu hình Spring, validation constraint và model để sinh OpenAPI JSON/YAML. Nếu namespace không đồng nhất, một số annotation hoặc kiểu dữ liệu có thể không được framework nhận diện như mong đợi.

Sau khi nâng cấp, kiểm tra:

- `/v3/api-docs` trả HTTP 200 và JSON hợp lệ.
- `/v3/api-docs.yaml` trả YAML nếu ứng dụng bật endpoint này.
- Controller path và HTTP method vẫn xuất hiện.
- `@Valid` và constraint Jakarta được áp dụng.
- JPA DTO/entity mapping không làm thay đổi response ngoài ý muốn.
- `@Operation`, `@Parameter`, `@Schema`, `@ApiResponse` vẫn được đọc.
- Security scheme và operation requirement không bị mất.
- Swagger UI tải đúng OpenAPI document.

### 14.1. MockMvc regression test

Ví dụ kiểm tra document vẫn chứa operation sau migration:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OpenApiNamespaceMigrationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void openApiStillContainsProductOperation() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.paths['/api/products'].get").exists());
    }
}
~~~

Đây là regression test cho document. Cần có thêm HTTP integration test để xác minh request validation, serialization và response runtime thực sự hoạt động sau khi chuyển namespace.

## 15. Những lỗi migration thường gặp

- **Thay toàn bộ chuỗi `javax` thành `jakarta`**: làm hỏng package Java SE như `javax.sql` hoặc `javax.crypto`.
- **Chỉ đổi import mà giữ dependency cũ**: compile/runtime vẫn có thể nạp API `javax`.
- **Chỉ nâng Spring Boot mà không nâng thư viện bên thứ ba**: filter, JPA extension hoặc validation library cũ không tương thích.
- **Trộn `javax.servlet.Filter` và `jakarta.servlet.Filter`**: container Jakarta không nhận kiểu Servlet cũ.
- **Giữ annotation `javax.validation`**: Jakarta Validation provider không coi chúng là constraint tương ứng.
- **Quên XML descriptor**: `web.xml`, `persistence.xml` hoặc `orm.xml` có thể còn schema namespace cũ.
- **Quên generated source và service loader**: build sạch có thể sinh lại import hoặc provider name cũ.
- **Nhầm `@Transactional` của Spring với JTA**: hai annotation khác package và có semantics riêng.
- **Nhầm Swagger annotations với Jakarta annotations**: `io.swagger.v3.oas.annotations` không đổi namespace.
- **Dùng springdoc sai major line**: Boot 2 dùng nhánh 1.x, Boot 3 dùng 2.x, Boot 4 dùng 3.x.
- **Chỉ kiểm tra compile**: lỗi linkage có thể chỉ xuất hiện khi Spring khởi tạo filter, entity manager hoặc validation provider.
- **Không semantic diff OpenAPI**: schema required, format, enum hoặc response có thể thay đổi dù ứng dụng vẫn khởi động.
- **Dùng exclusion để che dependency cũ**: thư viện có thể vẫn gọi class bị loại và thất bại ở runtime.

## 16. Checklist review

- [ ] Đã xác định đang nâng Boot 2 → 3 hay Boot 3 → 4.
- [ ] Spring Framework và Jakarta EE baseline thuộc đúng thế hệ.
- [ ] Chỉ package thuộc Jakarta EE được chuyển sang `jakarta.*`.
- [ ] Các package Java SE như `javax.sql`, `javax.crypto`, `javax.net.ssl` vẫn giữ nguyên.
- [ ] Servlet, JPA, Validation và JTA imports đã được rà soát.
- [ ] Spring annotations `org.springframework.*` không bị đổi nhầm.
- [ ] Swagger annotations `io.swagger.v3.*` không bị đổi nhầm.
- [ ] Dependency tree không còn API Java EE cũ không cần thiết.
- [ ] Thư viện bên thứ ba có bản hỗ trợ Jakarta.
- [ ] XML descriptor, service loader và generated source đã được kiểm tra.
- [ ] Springdoc major version tương thích với Spring Boot.
- [ ] Compile, unit test và integration test đều pass.
- [ ] OpenAPI JSON/YAML được kiểm tra và diff với baseline.
- [ ] Swagger UI, validation, security và JPA mapping hoạt động đúng.

## 17. Tài liệu tham khảo

- [Spring Boot 3.0 Migration Guide – Jakarta EE](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide#jakarta-ee)
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide)
- [Spring Framework Versions – Java/Jakarta EE versions](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-Versions#javajakarta-ee-versions)
- [Jakarta EE – Unaffected non-EE javax packages](https://github.com/jakartaee/platform/blob/main/namespace/unaffected-packages.adoc)
- [Jakarta Dependency Injection 2.0](https://jakarta.ee/specifications/dependency-injection/2.0/)
- [Java SE – javax.transaction.xa package](https://docs.oracle.com/en/java/javase/17/docs/api/java.transaction.xa/javax/transaction/xa/package-summary.html)
- [springdoc-openapi v2 – Migration from v1](https://springdoc.org/v2/#migrating-from-springdoc-openapi-v1)
- [springdoc-openapi – Current compatibility matrix](https://springdoc.org/#what-is-the-compatibility-matrix-of-springdoc-openapi-with-spring-boot)
- [OpenRewrite – Spring Boot migration recipes](https://docs.openrewrite.org/recipes/java/spring/boot3)

Namespace migration là thay đổi về kiểu Java và dependency, không chỉ là sửa cú pháp import. Boot 2 lên Boot 3 chuyển các API Java EE sang Jakarta; Boot 3 lên Boot 4 tiếp tục Jakarta và nâng baseline lên EE 11. Hãy rà soát source, dependency tree, thư viện bên thứ ba, XML và generated code; giữ nguyên các package `javax` thuộc Java SE; sau đó kiểm tra springdoc bằng OpenAPI regression test và kiểm thử HTTP runtime.
