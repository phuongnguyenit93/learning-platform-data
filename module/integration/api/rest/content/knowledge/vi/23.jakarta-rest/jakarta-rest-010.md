# Cấu hình triển khai, dependency và namespace jakarta

## 1. Mục tiêu và vấn đề thực tế

Trong module **INTEGRATION_API_REST**, thiết kế resource, URI, phương thức, status HTTP, hợp đồng dữ liệu và bảo mật mới là một nửa công việc. Để REST API Java chạy được, cần **đúng namespace**, **đúng dependency** và **đúng runtime triển khai**.

Một resource sử dụng **@Path("/products")** và **@GET** có thể compile thành công nhưng trả **404** khi gọi, do:

- Ứng dụng chỉ phụ thuộc **jakarta.ws.rs-api**, không có implementation nhận request.
- WAR chạy trên **servlet-only container** không cung cấp Jakarta REST.
- Source dùng **javax.ws.rs.Path** nhưng REST runtime chỉ nhận **jakarta.ws.rs.Path**.
- Đường public thiếu **context root** hoặc **ApplicationPath**.
- JSON provider, dependency injection hoặc security integration không được cài đặt như dự kiến.

Bài học thuộc chương **Jakarta REST**, minh họa **Jakarta REST 3.1 / Jakarta EE 10**, Java 17 và Maven; các version thư viện bên ngoài là ví dụ tương thích chứ không tự được xem là mới nhất.

Sau bài học, bạn có thể:

1. Phân biệt đặc tả **Jakarta REST API**, runtime implementation, servlet/HTTP container, CDI và JSON provider.
2. Chuyển **javax.ws.rs** sang **jakarta.ws.rs** đúng thế hệ, tránh trộn classpath.
3. Đóng gói và chạy **WAR trên Jakarta EE server**, **Jersey standalone**, hoặc **Spring Boot + Jersey**.
4. Cấu hình base URI, xử lý JSON, authentication/authorization, lỗi và OpenAPI.
5. Kiểm tra bằng HTTP, dependency graph, integration tests và troubleshooting.
6. Hoàn thành bài thực hành triển khai một API theo resource.

## 2. Jakarta REST là đặc tả, không tự là server

Jakarta REST (trước đây gọi JAX-RS) quy định annotation và API:

~~~java
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;

@Path("/health")
public class HealthResource {
    @GET
    @Produces(MediaType.TEXT_PLAIN)
    public String health() {
        return "ok";
    }
}
~~~

Đoạn code này **không tự mở cổng HTTP**. Một implementation như **Jersey** hoặc **RESTEasy** phải đăng ký route, tạo resource và cung cấp request/response processing.

| Thành phần | Chức năng |
| --- | --- |
| **jakarta.ws.rs-api** | Chứa @Path, @GET, Response, Application... để compile |
| **REST implementation** | Route HTTP, tham số, exception mapper, provider |
| **HTTP runtime** | Servlet container, Jakarta EE server, Grizzly... nhận kết nối |
| **JSON provider** | Chuyển JSON ↔ DTO bằng JSON-B/Jackson tích hợp |
| **DI** | CDI, HK2 hoặc Spring injection quản lý service |
| **Security** | Container/JWT/OIDC filter, role, tenant và resource permissions |
| **Build artifact** | WAR hoặc executable JAR với dependency đầy đủ |

~~~mermaid
flowchart LR
    C[Client] --> P[Proxy/Gateway]
    P --> H[HTTP Runtime]
    H --> R[Jakarta REST Implementation]
    R --> A[Resource @Path]
    A --> S[Domain Service]
    S --> DB[(DB)]
    R --> M[JSON + Exception Providers]
~~~

**API jar không đồng nghĩa implementation jar.** Có annotation để compiler hiểu không có nghĩa server đã biết gọi method. Framework cũng không tự quyết định GET có side effect hay không, POST có trả 201/Location đúng không, hoặc người dùng có quyền trên resource hay không.

## 3. Namespace javax → jakarta: nguồn lỗi migration lớn

| Thế hệ | REST package | Ý nghĩa |
| --- | --- | --- |
| Java EE/JAX-RS cũ | **javax.ws.rs.\*** | Mã và runtime thế hệ trước |
| Jakarta EE 8 | Phần lớn API vẫn là **javax.\*** | Nền tảng đổi tên nhưng chưa chuyển package |
| Jakarta EE 9 / Jakarta REST 3.0 | **jakarta.ws.rs.\*** | Bước đổi namespace |
| Jakarta EE 10 / Jakarta REST 3.1 | **jakarta.ws.rs.\*** | Ngữ cảnh ví dụ bài này |

Thay đổi các import liên quan:

~~~java
// Cũ: Java EE / JAX-RS
import javax.ws.rs.GET;
import javax.ws.rs.Path;
import javax.ws.rs.core.Response;

// Mới: Jakarta REST 3.x
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.core.Response;
~~~

Các API doanh nghiệp khác cũng chuyển theo thế hệ:

~~~java
import jakarta.servlet.Filter;
import jakarta.persistence.Entity;
import jakarta.validation.Valid;
import jakarta.inject.Inject;
import jakarta.annotation.security.RolesAllowed;
~~~

**Không thay mọi javax.\* bằng jakarta.\*.** **javax.crypto** và **javax.net.ssl** vẫn thuộc JDK và tiếp tục tồn tại. Phải tra đặc tả của từng API trước khi sửa package.

### 3.1. Vì sao thêm cả hai API jar không giải quyết được?

**javax.ws.rs.Path** và **jakarta.ws.rs.Path** là **hai annotation type khác nhau**. Runtime Jakarta REST 3.x không mặc nhiên đăng ký resource mang annotation javax đời cũ. Trộn các thư viện có thể tạo **NoClassDefFoundError, NoSuchMethodError, LinkageError** hoặc route 404 do annotation không được quét.

Không chọn cách thêm song song **javax.ws.rs-api** và **jakarta.ws.rs-api** rồi hy vọng Java tự tạo bridge. Hãy kiểm dependency tree, chuyển source và chọn một bộ implementation tương thích; nếu bắt buộc chạy code cũ, cần môi trường legacy hoặc migration/adapter đã kiểm thử.

## 4. Chọn deployment model trước dependency

| Cách chạy | Artifact | Nơi cung cấp REST runtime |
| --- | --- | --- |
| **Jakarta EE 10 server** | WAR | Server cung cấp REST implementation, CDI, các nền tảng liên quan |
| **Servlet-only container** | WAR | Ứng dụng phải đóng gói Jersey/RESTEasy tương thích |
| **Java SE + Jersey/Grizzly** | Java app/JAR | Ứng dụng đóng gói Jersey, HTTP container và JSON provider |
| **Spring Boot + Spring MVC** | JAR/WAR | Spring MVC; **không tự là Jakarta REST** |
| **Spring Boot + Jersey** | JAR/WAR | spring-boot-starter-jersey và Jersey runtime |

Với **Jakarta EE application server**, REST API library thường để Maven **provided** vì server đã cung cấp. Với **standalone/servlet-only**, cần runtime implementation trong ứng dụng. Với Spring Boot, dùng **@RestController/@GetMapping** nếu chọn Spring MVC, hoặc **@Path/@GET** nếu tích hợp Jersey thật.

**Không bắt đầu bằng việc copy pom.xml từ một runtime khác.** Khác biệt về dependency scope, JSON provider, servlet version và CDI có thể khiến code compile nhưng fail khi deploy.

## 5. Maven WAR trên Jakarta EE 10 server

Ví dụ project Java 17, package **WAR**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>catalog-api</artifactId>
  <version>1.0.0</version>
  <packaging>war</packaging>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>jakarta.platform</groupId>
      <artifactId>jakarta.jakartaee-web-api</artifactId>
      <version>10.0.0</version>
      <scope>provided</scope>
    </dependency>
  </dependencies>
</project>
~~~

**provided**: compile thấy API nhưng WAR không nhất thiết chứa API jar; server tương thích phải cung cấp runtime. Đây không phải bảo đảm server đang dùng đúng Jakarta EE version.

Nếu chỉ cần API Jakarta REST ở compile time thay vì toàn bộ web profile:

~~~xml
<dependency>
  <groupId>jakarta.ws.rs</groupId>
  <artifactId>jakarta.ws.rs-api</artifactId>
  <version>3.1.0</version>
  <scope>provided</scope>
</dependency>
~~~

**Hai đoạn là các lựa chọn minh họa**, không bắt buộc khai báo cả hai. Nếu resource còn dùng CDI/JPA/Validation phải có các API tương ứng hoặc dùng umbrella dependency phù hợp.

**Trình tự triển khai:**

1. Chọn server thực sự tương thích **Jakarta EE 10 / Jakarta REST 3.1** và JDK hỗ trợ.
2. Build WAR và kiểm các jar trong artifact không trộn javax REST với jakarta REST.
3. Deploy WAR, xác định context root, cấu hình datasource/secret/security.
4. Kiểm REST resource được đăng ký, JSON provider hoạt động, route health truy cập đúng.
5. Chạy smoke test qua **đúng proxy/gateway** như môi trường production.

Với annotation-based setup thường không cần **web.xml**, nhưng context path, DI, datasource và bảo mật vẫn có thể đòi cấu hình đặc thù server.

## 6. ApplicationPath, resource path và URL cuối cùng

~~~java
import jakarta.ws.rs.ApplicationPath;
import jakarta.ws.rs.core.Application;

@ApplicationPath("/api")
public class RestApplication extends Application {
}
~~~

Resource:

~~~java
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;

@Path("/health")
public class HealthResource {
    @GET
    @Produces(MediaType.TEXT_PLAIN)
    public String get() {
        return "ok";
    }
}
~~~

Nếu WAR **catalog-api.war** có context root **/catalog-api**, HTTP path thường là:

~~~http
GET /catalog-api/api/health HTTP/1.1
Host: localhost:8080
Accept: text/plain
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain

ok
~~~

**Đường đi = context root của deployment + @ApplicationPath + @Path class/method.** Proxy có thể rewrite prefix, nên URL client nhìn thấy khác với URL tới servlet container. Nếu gặp 404, xác minh đủ ba tầng trước khi đổi @Path.

### 6.1. HTTP resource thực tế

~~~java
@Path("/products")
@Produces(MediaType.APPLICATION_JSON)
public class ProductResource {

    @GET
    @Path("/{id}")
    public ProductDto get(@PathParam("id") UUID id) {
        return products.requireReadable(id);
    }

    @POST
    @Consumes(MediaType.APPLICATION_JSON)
    public Response create(
            ProductCreateRequest input, @Context UriInfo uri) {
        ProductDto created = products.createAuthorized(input);
        URI location = uri.getAbsolutePathBuilder()
            .path(created.id().toString()).build();
        return Response.created(location).entity(created).build();
    }
}
~~~

**Code là skeleton**: cần imports, DTO, service được inject đúng và quyền kiểm tra trong service. REST framework không tự xác minh caller có quyền với **id** trong URI.

- GET có thể trả **200** và JSON đúng representation.
- POST tạo resource dùng **201 Created** với **Location**.
- Nếu dùng **UriInfo** để tạo absolute Location, cần cấu hình forwarded headers ở proxy đáng tin, tránh phát URL nội bộ hay tin Host do client giả.

## 7. JSON serialization và provider

**@Produces(application/json)** tuyên bố media type, không tự cung cấp serializer. Jakarta REST dùng **MessageBodyReader/Writer** để ánh xạ request/response entity; server có thể tích hợp **JSON-B** hoặc **Jackson provider** tùy môi trường.

~~~java
public record ProductDto(
    UUID id, String sku, String name, long priceMinor) {}

public record ProductCreateRequest(
    String sku, String name, long priceMinor) {}
~~~

Cần kiểm:

- DTO **record**, enum, date-time, nested object có được provider thực tế serialize/deserialize chính xác?
- Có provider xử lý **application/json** cho request và response hay chưa?
- Có trộn JSON-B và Jackson khiến tên field, null hoặc enum khác hợp đồng?
- Client gửi **Content-Type** không hỗ trợ → có thể **415**; không thỏa **Accept** → có thể **406**.
- API không nên bind thẳng JPA entity: DTO input chỉ nhận field cho phép, service kiểm authorization và giá trị tiền do server quản lý.

Một **Jackson library** trong Maven không đảm bảo tự động đăng ký Jakarta REST MessageBodyWriter. Phải có provider integration phù hợp và cấu hình/kiểm thử đúng runtime.

## 8. Jersey standalone và HTTP container Grizzly

Khi chạy Java SE thay cho Jakarta EE server, có thể dùng Jersey 3.1.x + Grizzly. Ví dụ ba dependency chạy ở cùng version (không tuyên bố là mới nhất):

~~~xml
<dependencies>
  <dependency>
    <groupId>org.glassfish.jersey.containers</groupId>
    <artifactId>jersey-container-grizzly2-http</artifactId>
    <version>3.1.5</version>
  </dependency>
  <dependency>
    <groupId>org.glassfish.jersey.inject</groupId>
    <artifactId>jersey-hk2</artifactId>
    <version>3.1.5</version>
  </dependency>
  <dependency>
    <groupId>org.glassfish.jersey.media</groupId>
    <artifactId>jersey-media-json-jackson</artifactId>
    <version>3.1.5</version>
  </dependency>
</dependencies>
~~~

Dự án thực nên dùng **Jersey BOM** và version hỗ trợ đã được kiểm tra lỗ hổng/tính tương thích; tránh mỗi module Jersey một version.

Bootstrap:

~~~java
import java.net.URI;
import org.glassfish.grizzly.http.server.HttpServer;
import org.glassfish.jersey.grizzly2.httpserver.GrizzlyHttpServerFactory;
import org.glassfish.jersey.jackson.JacksonFeature;
import org.glassfish.jersey.server.ResourceConfig;

public class Main {
    public static void main(String[] args) {
        ResourceConfig config = new ResourceConfig()
            .register(HealthResource.class)
            .register(JacksonFeature.class);

        HttpServer server =
            GrizzlyHttpServerFactory.createHttpServer(
                URI.create("http://localhost:8080/api/"), config);

        Runtime.getRuntime().addShutdownHook(
            new Thread(server::shutdownNow));
    }
}
~~~

Ở **Grizzly standalone**, base URI từ **createHttpServer**, không có context root của WAR. URL ví dụ là **http://localhost:8080/api/health**.

**HK2 không tự đồng nghĩa Jakarta CDI**. Nếu resource dùng **@Inject** CDI từ Jakarta EE server, khi chuyển sang Jersey standalone phải cấu hình bridge/injection phù hợp hoặc đăng ký dependency bằng cơ chế được Jersey hỗ trợ. JAR phát hành cần chứa toàn bộ runtime dependency, không chỉ class ứng dụng.

## 9. Spring Boot 3 và Jersey: hai mô hình routing khác nhau

Spring Boot 3 sử dụng nhiều API **jakarta.servlet**, **jakarta.validation** và **jakarta.persistence**, nhưng controller thông thường của **Spring MVC** dùng annotation riêng:

~~~java
@RestController
@RequestMapping("/api/products")
public class SpringProductController {
    @GetMapping("/{id}")
    public ResponseEntity<ProductDto> get(@PathVariable UUID id) {
        return ResponseEntity.ok(service.requireReadable(id));
    }
}
~~~

**@RestController/@GetMapping không tương đương @Path/@GET.** Một project chỉ thêm **spring-boot-starter-web** không tự động đăng ký resource Jakarta REST.

### 9.1. Spring Boot muốn dùng Jakarta REST thực sự

Có thể tích hợp **Jersey**:

~~~xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-jersey</artifactId>
</dependency>
~~~

Dự án phải dùng BOM/dependency management của Spring Boot đang chạy; nếu dùng JSON-Jackson provider, xác nhận module tích hợp tương ứng có trên classpath. Cấu hình Jersey resource:

~~~java
@Configuration
public class JerseyConfiguration extends ResourceConfig {
    public JerseyConfiguration() {
        register(HealthResource.class);
    }
}
~~~

Chọn application path:

~~~yaml
spring:
  jersey:
    application-path: /api
server:
  servlet:
    context-path: /catalog
~~~

Đường dự kiến trong servlet deployment là **/catalog/api/health**, nhưng cần kiểm tra servlet/filter registration và proxy thực tế. Không cấu hình **@ApplicationPath** ở một nơi, application-path ở nơi khác rồi giả định luôn được ghép theo ý mình.

**Spring bean injection khác CDI/HK2 injection.** Resource của Jersey cần được quản lý/đăng ký đúng theo integration version; kiểm tra constructor/service injection bằng test. Nếu ứng dụng đã dùng Spring MVC ổn định, không cần chuyển sang Jakarta REST chỉ vì đã đổi namespace javax.servlet → jakarta.servlet.

## 10. Dependency injection và lifecycle

Trong Jakarta EE runtime hỗ trợ CDI:

~~~java
import jakarta.enterprise.context.RequestScoped;
import jakarta.inject.Inject;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;

@Path("/inventory")
@RequestScoped
public class InventoryResource {
    @Inject
    InventoryService service;

    @GET
    public String summary() {
        return service.summary();
    }
}
~~~

Ở Jersey standalone với **HK2**, không mặc nhiên có full Jakarta CDI; ở Spring Boot + Jersey, cần bridge/container integration phù hợp. Một annotation **@Inject** không tự chứng minh service được tạo và transactional proxy được áp dụng.

Kiểm tra:

- **@RequestScoped** giúp giữ dữ liệu theo request trong môi trường hỗ trợ, nhưng service singleton phải thread-safe.
- Không đặt **user, access token, request-specific data** vào mutable field của singleton resource.
- Không tự **new Service()** rồi mong CDI transaction/security interceptors hoạt động.
- Datasource, transaction manager, secret config và connection pool phải được cung cấp ở runtime.
- Lỗi injection, route đăng ký, JSON provider nên được phát hiện ở startup/smoke test, không đợi traffic thật.

## 11. Authentication, authorization và tenant scope

Jakarta REST có **SecurityContext** nhưng không tự xác thực JWT. Container/filter/security integration phải xác minh token và cấp principal.

~~~java
import jakarta.ws.rs.GET;
import jakarta.ws.rs.NotAuthorizedException;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.PathParam;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.Context;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.SecurityContext;

@Path("/orders")
@Produces(MediaType.APPLICATION_JSON)
public class OrdersResource {
    @Context
    SecurityContext security;

    @GET
    @Path("/{id}")
    public OrderView read(@PathParam("id") UUID id) {
        if (security.getUserPrincipal() == null) {
            throw new NotAuthorizedException("Bearer");
        }
        return orders.requireReadable(
            security.getUserPrincipal(), id);
    }
}
~~~

**orders** là dependency cần inject và **requireReadable** phải xác minh quyền trên ID, tenant, role/scope và trạng thái resource. Nếu SecurityContext chưa được security integration điền principal, code không thể tự xác minh bearer token.

| Biện pháp | Lý do |
| --- | --- |
| TLS, JWT/OIDC validation | Kiểm signature, issuer, audience, expiry, key rotation |
| 401 + WWW-Authenticate | Credential không hợp lệ, challenge phù hợp |
| 403/404 | Caller không đủ quyền hoặc resource không được công bố |
| Tenant-bound queries | Chống BOLA/IDOR khi thay ID trên URI |
| DTO request riêng | Không nhận tenantId, role, price hay flags từ client tùy ý |
| Rate limit / quota | Chặn request abuse ở gateway và service |
| CORS đúng origin | Bảo vệ web integration, **không thay auth** |
| Audit/log | Không ghi token, password, raw PII |

**@RolesAllowed** thuộc **jakarta.annotation.security**; mức thực thi phụ thuộc container/interceptor/security setup, phải được kiểm thử. Trên Spring Boot + Jersey phải xác minh filter chain đúng path /api; route legacy không được bypass Spring Security. Không giả định prefix **/admin** tự cấp quyền.

## 12. ExceptionMapper, HTTP errors và Problem Details

Trong Jakarta REST, **@Provider ExceptionMapper** biến domain exception thành HTTP response:

~~~java
import jakarta.ws.rs.core.Response;
import jakarta.ws.rs.ext.ExceptionMapper;
import jakarta.ws.rs.ext.Provider;
import java.util.Map;

@Provider
public class OrderNotVisibleMapper
        implements ExceptionMapper<OrderNotVisibleException> {

    @Override
    public Response toResponse(OrderNotVisibleException ex) {
        var problem = Map.of(
            "type", "about:blank",
            "title", "Not Found",
            "status", 404,
            "code", "ORDER_NOT_FOUND");
        return Response.status(Response.Status.NOT_FOUND)
            .type("application/problem+json")
            .entity(problem)
            .build();
    }
}
~~~

**OrderNotVisibleException** cần định nghĩa riêng; provider JSON phải serialize được Map, mapper phải được register/scan đúng. Đây là minh họa một response theo **RFC 9457 Problem Details** có extension code; production cần policy title/detail/traceId an toàn và thống nhất.

| Tình huống | HTTP status |
| --- | --- |
| GET thành công | **200** + JSON |
| POST tạo resource | **201 Created** + Location |
| Xóa thành công không có body | **204** |
| JSON sai | **400** |
| Thiếu/sai token | **401** + challenge |
| Không có quyền | **403**, hoặc 404 theo privacy policy |
| Không thấy resource | **404** |
| Xung đột nghiệp vụ | **409** |
| Content-Type không hỗ trợ | **415** |
| Giới hạn tốc độ | **429** |
| Lỗi hạ tầng | **5xx** |

**Security filters hoặc gateway có thể trả lỗi trước khi Jakarta REST resource/mapper chạy.** Muốn lỗi thống nhất phải cấu hình đồng thời gateway, authentication layer và application. Không trả SQL detail hoặc stack trace trong Problem Details; cũng không dùng HTTP 200 chứa success=false để che thất bại.

## 13. OpenAPI 3.1 và đường triển khai

Đặt context path + Jakarta REST base path trong **servers**, và chỉ viết path của resource trong **paths** để không nhân đôi tiền tố:

~~~yaml
openapi: 3.1.0
info:
  title: Catalog Jakarta REST API
  version: 1.0.0
servers:
  - url: https://api.example.test/catalog-api/api
paths:
  /health:
    get:
      operationId: health
      responses:
        '200':
          description: Alive
          content:
            text/plain:
              schema:
                type: string
                example: ok
  /products/{id}:
    get:
      operationId: getProduct
      security:
        - bearerAuth: []
      parameters:
        - in: path
          name: id
          required: true
          schema:
            type: string
            format: uuid
      responses:
        '200':
          description: Product được phép xem
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Product'
        '401': { description: Chưa xác thực }
        '403': { description: Không đủ quyền }
        '404': { description: Không tìm thấy }
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
  schemas:
    Product:
      type: object
      required: [id, sku, name, priceMinor]
      properties:
        id: { type: string, format: uuid }
        sku: { type: string }
        name: { type: string }
        priceMinor: { type: integer, format: int64, minimum: 0 }
~~~

API thật cần bổ sung requestBody và responses cho POST, errors và các header quan trọng. **OpenAPI không tự đăng ký Jersey resource hoặc cấu hình JSON provider.** Nếu staging có proxy khác, cập nhật servers theo môi trường; không lặp **/catalog-api/api** trong path.

## 14. Smoke test và JerseyTest

Với WAR được deploy như mục 6:

~~~bash
curl -i \
  -H "Accept: text/plain" \
  http://localhost:8080/catalog-api/api/health

curl -i \
  -H "Accept: application/json" \
  http://localhost:8080/catalog-api/api/health
~~~

Request đầu mong **200 text/plain** + body ok. Request hai có thể nhận **406 Not Acceptable** nếu endpoint chỉ công bố text/plain. Nếu 404, xem context root/ApplicationPath/registry; nếu 405, method không match; nếu 415, xem **Content-Type** và MessageBodyReader. Đừng suy diễn chỉ từ mã mà bỏ qua deployment logs.

Ví dụ **JerseyTest** cho resource không cần CDI:

~~~java
import jakarta.ws.rs.core.Application;
import org.glassfish.jersey.server.ResourceConfig;
import org.glassfish.jersey.test.JerseyTest;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class HealthResourceTest extends JerseyTest {
    @Override
    protected Application configure() {
        return new ResourceConfig(HealthResource.class);
    }

    @Test
    void healthReturnsOk() {
        var response = target("health")
            .request("text/plain").get();
        assertEquals(200, response.getStatus());
        assertEquals("ok", response.readEntity(String.class));
        response.close();
    }
}
~~~

Test project cần **Jersey test framework + test container provider** tương thích (và JUnit integration phù hợp). JerseyTest pass **không chứng minh** WAR chạy trên application server: cần smoke test sau deploy thực tế.

### 14.1. Ma trận test

| ID | Kịch bản | Mục tiêu |
| --- | --- | --- |
| T01 | Compile source jakarta.ws.rs | Imports/runtime tương thích |
| T02 | Trộn javax annotation với Jakarta runtime | CI/contract test phát hiện |
| T03 | Chỉ có API jar, thiếu runtime | Bootstrap không thể qua smoke test |
| T04 | WAR deploy vào Jakarta EE 10 server | Route được đăng ký |
| T05 | GET đúng context root/ApplicationPath | 200 và text/plain |
| T06 | Sai prefix | 404 được chẩn đoán đúng |
| T07 | Client Accept không match | 406 theo contract |
| T08 | POST Content-Type sai | 415 nếu request media không hỗ trợ |
| T09 | JSON provider và DTO | Enum/null/date-time đúng contract |
| T10 | 201 Created + Location | URL public đúng, không lộ host nội bộ |
| T11 | Mapper domain exception | 404 problem+json, không lộ PII |
| T12 | Thiếu/expired bearer token | 401/challenge |
| T13 | Truy cập khác tenant | 403/404, không lộ resource |
| T14 | POST thêm tenantId/role | Không mass assignment |
| T15 | Jersey trên Spring Boot | Không routing conflict/DI fail |
| T16 | Restart/readiness | Không injection/provider error |

Để phân tích dependency, dùng **Maven dependency:tree**, kiểm **WAR/JAR thực tế**, server logs và smoke tests. Maven build thành công chỉ xác nhận compile/package, **không xác nhận runtime đã chọn đúng implementation/provider**.

## 15. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân khả dĩ / hướng kiểm |
| --- | --- |
| **404 mọi resource** | REST implementation không bootstrap, sai base path, javax annotations |
| **404 một resource** | Không quét/register class, @Path sai |
| **405** | URI match nhưng method không có handler |
| **415** | @Consumes và Content-Type sai, JSON reader chưa hoạt động |
| **406** | Accept không được @Produces hỗ trợ |
| **500 khi serialize JSON** | MessageBodyWriter/DTO/serializer exception |
| **NoClassDefFoundError/LinkageError** | javax/jakarta hoặc module version không đồng bộ |
| **@Inject không hoạt động** | CDI/HK2/Spring resource lifecycle khác dự kiến |
| **401 dù token hợp lệ** | JWT validator/filter mapping/issuer/audience sai |
| **CORS lỗi** | Preflight/origin/headers chưa đúng; không tắt auth để sửa |
| **Location trỏ host nội bộ** | Forwarded headers/trusted proxy cấu hình sai |
| **Local chạy, WAR fail** | Scope/runtime/context root/provider khác |

**Quy trình điều tra:** tái hiện HTTP request với request ID → gateway → servlet/Grizzly → resource registry → JSON/DI/security → service/DB. Không cố sửa 404 bằng cách vô hiệu hóa security hoặc thay mọi lỗi thành 200.

## 16. Bài thực hành: triển khai Catalog API

**Bối cảnh:** sản phẩm có **id, sku, name, priceMinor**, còn **tenantId** chỉ lưu nội bộ. Người dùng được đọc catalog; admin mới được thêm product.

### Nhiệm vụ (100 điểm)

1. **Namespace/dependency – 25:** chọn Jakarta EE WAR hoặc Jersey standalone, ghi Maven API/runtime dependencies và lý do dùng provided hay packaged.
2. **HTTP/routing – 25:** @ApplicationPath, GET /products/{id}, POST /products, xử lý 200/201/Location/400/401/403/404 và URL qua proxy.
3. **Security/JSON – 25:** JSON provider, DTO allowlist, quyền admin, kiểm tenant, không tin role từ request.
4. **Tests – 25:** ít nhất tám test gồm path prefix, Content-Type/Accept, JSON mapping, authn, cross-tenant, mass assignment, Location và thiếu REST runtime.

**Hướng giải:** với WAR dùng **jakarta.jakartaee-web-api 10.0.0 provided** và server tương thích; với standalone dùng Jersey/Grizzly/JSON provider cùng version, bootstrap ResourceConfig. URI thực xét đúng context root/base path. POST chỉ nhận sku/name và những field người gọi được phép; tenant lấy từ principal, service kiểm quyền. Verify response 201/Location từ public host và mọi field cấm trong DB không thay đổi sau input xấu.

## 17. Checklist và tài liệu tham khảo

- [ ] Đã xác định mô hình deploy: Jakarta EE WAR, Jersey standalone, Spring MVC hoặc Spring Boot + Jersey.
- [ ] Namespace **jakarta.ws.rs** đồng bộ với implementation, không trộn javax REST.
- [ ] Không đổi nhầm các package JDK như javax.crypto.
- [ ] API dependency và runtime/provider JSON không bị đánh đồng.
- [ ] Scope **provided** chỉ dùng khi server thật sự cung cấp dependency tương ứng.
- [ ] Context root, ApplicationPath và reverse proxy path đã được kiểm thử.
- [ ] DI lifecycle, security context và tenant authorization hoạt động đúng.
- [ ] HTTP method, Content-Type, Accept, status và Location khớp hợp đồng.
- [ ] Không log token/PII hay trả stack trace trong errors.
- [ ] Có OpenAPI, dependency graph check và smoke test sau deploy.

**Ghi nhớ:** namespace đúng giúp source liên kết với API; dependency đúng giúp runtime có đủ khả năng; cấu hình triển khai đúng mới đưa resource ra URL thật. Một Jakarta REST API chỉ đáng tin khi đã kiểm cả **HTTP, JSON binding, DI, security và endpoint thực tế**.

### Nguồn tham khảo

- **Jakarta RESTful Web Services 3.1 Specification** và Jakarta EE 10 Platform/Web Profile.
- **Eclipse Jersey User Guide:** ResourceConfig, Grizzly, HK2, JSON providers, JerseyTest.
- **Spring Boot Reference:** Jersey integration, servlet mapping và security filter.
- **RFC 9110 – HTTP Semantics; RFC 9457 – Problem Details; OpenAPI Specification 3.1**.
