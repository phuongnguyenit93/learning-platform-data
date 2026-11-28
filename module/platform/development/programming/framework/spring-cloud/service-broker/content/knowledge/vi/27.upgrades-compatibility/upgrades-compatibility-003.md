# Đánh giá thay đổi API Java, cấu hình và web stack khi nâng phiên bản

Nâng phiên bản Java, Spring Boot, Spring Framework hoặc Spring Cloud có thể đem lại bản vá bảo mật, hiệu năng và tính năng mới, nhưng cũng có thể làm thay đổi API, cấu hình mặc định, cách khởi tạo ứng dụng hoặc hành vi HTTP. Với một service broker triển khai Open Service Broker API (OSB API), thay đổi nhỏ ở web stack cũng có thể ảnh hưởng đến nền tảng: endpoint không còn được expose, authentication filter chạy sai thứ tự, JSON serialization đổi kiểu dữ liệu hoặc status code không còn đúng hợp đồng.

Vì vậy, nâng cấp cần được đánh giá trên nhiều lớp thay vì chỉ kiểm tra mã nguồn có biên dịch hay không. Đối với SPRING_CLOUD_SERVICE_BROKER, cần xác minh tương thích của Java source/binary/runtime, dependency và BOM, API Spring, cấu hình, servlet/reactive stack, Jakarta namespace, security, serialization, database migration và hành vi OSB. Mục tiêu là nâng nền tảng kỹ thuật mà vẫn giữ nguyên hành vi giao thức mà Cloud Foundry hoặc nền tảng khác đang phụ thuộc.

## 1. Phạm vi tương thích cần đánh giá

Một lần nâng phiên bản có thể tác động đến nhiều thành phần độc lập:

| Lớp | Nội dung cần xem xét | Ví dụ rủi ro |
|---|---|---|
| Java language/source | Cú pháp, type inference, annotation, compiler flags | Code không biên dịch với source level mới hoặc cũ |
| Java runtime/JVM | Bytecode target, module system, GC, TLS, reflection | Dependency cũ không chạy trên JDK mới |
| Java APIs | API bị deprecated hoặc removed | Thư viện gọi API đã bị loại bỏ |
| Spring Framework | Bean lifecycle, proxy, validation, HTTP abstractions | Bean không được tạo hoặc advice không chạy |
| Spring Boot | Auto-configuration, property names, defaults | Endpoint/feature bị bật hoặc tắt ngoài dự kiến |
| Spring Cloud | Release train và compatibility với Boot | Dependency không tương thích |
| Web stack | Servlet container hoặc reactive runtime | Routing, timeout, filter hoặc body handling đổi |
| Jakarta namespace | Chuyển package javax sang jakarta ở các API EE | Import và dependency không còn tương thích |
| Security | Filter chain, matcher, password encoder, OAuth/TLS | Broker bị khóa ngoài hoặc endpoint bị mở |
| Serialization | Jackson, validation, date/time, enum handling | JSON OSB thay đổi tên field hoặc format |
| Persistence | Hibernate/JPA, JDBC driver, migration tool | Schema hoặc transaction behavior thay đổi |
| Observability | Actuator, Micrometer, tracing | Health check hoặc metric bị đổi |
| Build/deployment | Maven/Gradle plugin, container image, startup flags | Artifact build được nhưng không chạy ở production |

Không phải mọi lần nâng Spring đều làm thay đổi tất cả các lớp. Tuy nhiên, checklist đánh giá cần bao phủ chúng để phát hiện tác động gián tiếp từ dependency bắc cầu và auto-configuration.

## 2. Phân biệt source, binary và runtime compatibility

Ba khái niệm này thường bị gộp làm một:

- **Source compatibility:** mã nguồn có thể biên dịch sau khi nâng compiler/API hay không.
- **Binary compatibility:** bytecode đã biên dịch có thể liên kết và chạy với thư viện/runtime mới hay không.
- **Runtime compatibility:** ứng dụng thực sự chạy đúng trong môi trường mới, bao gồm reflection, class loading, TLS, serialization và hành vi container.

Một dự án có thể đạt source compatibility nhưng không đạt runtime compatibility. Ví dụ, code compile thành công với JDK mới nhưng một thư viện dùng reflection truy cập nội bộ JDK bị module system chặn. Hoặc ứng dụng compile và start nhưng JSON response của catalog thay đổi kiểu do Jackson upgrade.

Khi nâng Java, cần kiểm tra:

- JDK dùng để build và JRE/JDK dùng để chạy có cùng major version theo policy hay không.
- Compiler release/target có đúng với runtime production không.
- Bytecode của dependency có được runtime hiện tại hỗ trợ không.
- Các thư viện có dùng internal JDK APIs hoặc reflection sâu không.
- TLS provider, cipher suite, truststore và certificate chain có còn tương thích không.
- JVM flags, GC options và container memory detection có thay đổi không.
- Encoding, timezone, locale và date/time parsing có phụ thuộc mặc định JVM không.

Ví dụ Maven đặt Java release:

~~~xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

Ví dụ Gradle:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}
~~~

Các con số trên chỉ minh họa cách khai báo. Chọn Java version dựa trên phiên bản Spring Boot/Spring Cloud mục tiêu, runtime của nền tảng triển khai, chính sách hỗ trợ và dependency thực tế; không tự nâng JDK chỉ vì phiên bản mới hơn đã phát hành.

## 3. Lập ma trận phiên bản trước khi sửa code

Trước khi thay đổi dependency, lập bảng current/target cho các thành phần có quan hệ tương thích:

| Thành phần | Phiên bản hiện tại | Phiên bản mục tiêu | Cần xác minh |
|---|---|---|---|
| JDK build/runtime | Đang dùng | Được chọn | Java support range của framework và platform |
| Spring Boot | Đang dùng | Được chọn | Spring Framework, embedded server, Jackson, Micrometer |
| Spring Framework | Do Boot quản lý | Theo Boot mục tiêu | API deprecated/removed và lifecycle |
| Spring Cloud release train | Đang dùng | Tương ứng Boot mục tiêu | Compatibility verifier/release matrix |
| Spring Cloud Open Service Broker | Đang dùng | Được chọn | API response model và endpoint behavior |
| Servlet container hoặc Reactor Netty | Đang dùng | Do BOM/Boot quản lý | Java, Servlet/Jakarta và TLS compatibility |
| Jackson | Đang dùng | Theo dependency management | JSON contract và module support |
| Spring Security | Đang dùng | Theo Boot/BOM | Filter chain và authorization rules |
| Database driver/ORM | Đang dùng | Được chọn | JDBC behavior, dialect và migration |
| Build plugin | Đang dùng | Được chọn | JDK compatibility và reproducible build |

Không nâng tất cả dependency lên latest version một cách độc lập. Spring Boot BOM và Spring Cloud release train được thiết kế để quản lý các phiên bản đã được kiểm tra cùng nhau. Override một dependency nền tảng có thể tạo ra tổ hợp không được hỗ trợ dù từng artifact riêng lẻ đều tồn tại.

## 4. Tương thích giữa Spring Boot và Spring Cloud

Spring Cloud có release train tương ứng với các dòng Spring Boot. Khi nâng Boot, phải chọn release train Spring Cloud tương thích theo ma trận chính thức của Spring Cloud. Không suy ra compatibility chỉ từ số version hoặc từ việc Maven/Gradle tải được dependency.

Quy trình:

1. Xác định Spring Boot version hiện tại và mục tiêu.
2. Tra compatibility matrix chính thức để chọn Spring Cloud release train.
3. Xác định phiên bản Spring Cloud Open Service Broker thuộc release train hoặc được hỗ trợ cùng tổ hợp đó.
4. Kiểm tra Java baseline của toàn bộ stack.
5. Chạy dependency insight/tree để phát hiện nhiều version của cùng thư viện.
6. Kiểm tra compatibility verifier nếu release train cung cấp.
7. Chạy application context và HTTP contract tests trên tổ hợp mục tiêu.

Ví dụ khai báo dependency management với Maven:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>BOOT_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>CLOUD_TRAIN_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

BOOT_VERSION và CLOUD_TRAIN_VERSION là placeholder, phải được thay bằng cặp phiên bản tương thích đã xác minh. Không copy một cặp version từ dự án khác mà không kiểm tra Java baseline, dependency và release support.

## 5. Kiểm tra API Java bị deprecated hoặc removed

Nâng Java hoặc Spring có thể làm xuất hiện cảnh báo deprecation, sau đó API bị loại bỏ trong major release tiếp theo. Cần phân biệt:

- API deprecated nhưng vẫn tồn tại: có thể chạy nhưng cần kế hoạch thay thế.
- API removed: code hoặc dependency có thể không compile/link.
- API thay đổi semantics: vẫn compile nhưng kết quả khác.
- Internal API: không có cam kết tương thích và có thể biến mất.

Các nguồn cần kiểm tra:

- Compiler warnings với deprecation và unchecked operations.
- Release notes của Java và Spring Framework.
- Migration guide của Spring Boot.
- API documentation và Javadoc của dependency đang dùng.
- Static analysis và dependency vulnerability/compatibility reports.

Ví dụ compile nghiêm ngặt hơn:

~~~text
javac -Xlint:deprecation -Xlint:unchecked
~~~

Với Maven/Gradle, cấu hình compiler plugin tương ứng để phát cảnh báo trong CI. Không cần biến mọi warning thành lỗi ngay trong một bước nâng lớn nếu codebase đang có nhiều warning; có thể đặt baseline và xử lý theo từng nhóm, nhưng warning mới phải được review.

## 6. Chuyển namespace javax sang jakarta

Một thay đổi lớn khi nâng từ các thế hệ Spring cũ sang Spring Framework 6/Spring Boot 3 là chuyển nhiều API Jakarta EE từ package javax sang jakarta. Ví dụ:

| Namespace cũ | Namespace mới |
|---|---|
| javax.servlet | jakarta.servlet |
| javax.validation | jakarta.validation |
| javax.persistence | jakarta.persistence |
| javax.annotation trong các API liên quan | jakarta.annotation |
| javax.transaction | jakarta.transaction |

Không phải mọi package bắt đầu bằng javax đều chuyển sang jakarta. Một số API Java SE vẫn dùng javax, chẳng hạn javax.crypto hoặc javax.net.ssl. Không thực hiện replace toàn cục mọi chuỗi javax.

Kiểm tra các điểm:

- Import trong controller, filter, servlet, validation, persistence và transaction.
- Dependency của Servlet API, Bean Validation, JPA provider và embedded server.
- Custom annotation, validator, converter và exception handler.
- Thư viện bên thứ ba vẫn compile với javax nhưng ứng dụng mục tiêu dùng jakarta.
- Test fixture và reflection string chứa tên class đầy đủ.

Một thư viện cũ có thể kéo theo javax API và không tương thích với stack Jakarta. Hãy nâng thư viện đó hoặc thay thế; thêm cả javax và jakarta API vào classpath không tự làm chúng tương thích vì đây là hai kiểu khác nhau.

## 7. Đánh giá thay đổi Spring API và extension point

Spring Framework có thể thay đổi API, generic type, constructor, annotation attribute, callback hoặc extension point giữa các major/minor release. Những khu vực broker nên kiểm tra kỹ:

- Controller/handler mapping và request body conversion.
- Bean validation và method validation.
- Exception handler, error response và Problem Details nếu được bật.
- Transaction management và proxy boundaries.
- Reactive return types, Reactor context và cancellation.
- Application events, SmartLifecycle và graceful shutdown.
- ConfigurationProperties binding và validation.
- Security filter chain và method security.
- HTTP client abstraction và timeout/retry defaults.
- Jackson modules, Kotlin/Java time support và enum serialization.

Nếu dùng Spring Cloud Open Service Broker, kiểm tra migration guide/API của thư viện cho các interface như ServiceInstanceService, ServiceInstanceBindingService, CatalogService và response builders. Không dựa vào tên method của một phiên bản khác. Một interface có thể thay đổi generic type hoặc request/response model mà không làm ý nghĩa OSB endpoint thay đổi.

## 8. Cấu hình Spring Boot có thể đổi tên hoặc đổi mặc định

Một ứng dụng có thể khởi động thành công sau nâng cấp nhưng dùng cấu hình mặc định khác. Đây là nguồn lỗi khó phát hiện vì không nhất thiết có compile error.

Các nhóm property cần rà soát:

- Server port, context path, compression, forwarded headers và graceful shutdown.
- Jackson naming strategy, date/time format, unknown property handling.
- Datasource URL, pool sizing, timeout và transaction behavior.
- Security user, filter chain, CSRF, CORS và endpoint authorization.
- Actuator exposure, health groups, readiness/liveness.
- Logging format, tracing và metric export.
- SSL/TLS, truststore, keystore và certificate reload.
- Spring Cloud config/import, discovery và circuit breaker.
- Flyway/Liquibase enablement và migration locations.

Tạo một bảng cấu hình có owner và giá trị kỳ vọng:

| Property/nhóm | Giá trị mong đợi | Nguồn giá trị | Test xác minh |
|---|---|---|---|
| Broker server port | Theo deployment contract | Environment/secret config | Startup + HTTP smoke test |
| Context path | Đúng OSB base path | Application config | Route contract test |
| Graceful shutdown | Enabled theo policy | application config | SIGTERM integration test |
| Actuator readiness | Exposed cho orchestrator | deployment config | Probe test |
| Datasource pool | Theo concurrency/load | environment | Load/connection test |
| Security matcher | Chỉ OSB và health routes cần thiết | Security config | Positive/negative auth test |
| Jackson naming | JSON field theo OSB | ObjectMapper config | JSON schema contract test |

Không dựa vào cấu hình mặc định mà không ghi nhận. Khai báo tường minh những property ảnh hưởng đến endpoint, security, database và lifecycle.

## 9. ConfigurationProperties và validation

Khi nâng Spring Boot, cách bind property và validation có thể thay đổi do dependency hoặc annotation namespace. Broker nên dùng typed configuration thay vì đọc chuỗi rời rạc khắp code.

Ví dụ:

~~~java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "broker.provider")
public record ProviderProperties(
        @NotBlank String endpoint,
        @Min(1) int connectTimeoutMillis,
        @Min(1) int readTimeoutMillis) {
}
~~~

Ví dụ dùng Jakarta validation namespace trong stack tương ứng. Nếu dự án còn dùng javax validation, phải đồng bộ dependency và annotation theo thế hệ Spring mục tiêu. Kiểm tra rằng validation thực sự chạy khi bind configuration, và ứng dụng fail fast với thông báo không tiết lộ secret khi property bắt buộc bị thiếu.

Nên có test cho:

- Property hợp lệ được bind đúng.
- Property thiếu hoặc sai kiểu làm startup fail rõ ràng.
- Profile/environment override theo đúng thứ tự.
- Secret reference được resolve từ nguồn bảo mật.
- Property cũ được migrate hoặc bị từ chối, không âm thầm bị bỏ qua.

## 10. Chọn servlet hay reactive web stack

Spring Boot có thể chạy ứng dụng theo servlet stack (ví dụ Spring MVC với embedded Tomcat/Jetty/Undertow) hoặc reactive stack (Spring WebFlux với Reactor Netty). Hai stack có programming model và giới hạn khác nhau.

| Tiêu chí | Servlet/MVC | Reactive/WebFlux |
|---|---|---|
| Request handling | Thread-per-request hoặc mô hình server tương ứng | Non-blocking event loop khi dùng reactive server |
| Return type | Object, ResponseEntity, Callable, v.v. | Mono/Flux và reactive types |
| Blocking JDBC | Thường phù hợp với thread model | Cần cô lập trên bounded elastic hoặc dùng reactive driver |
| Filter | Servlet Filter, HandlerInterceptor | WebFilter, WebExceptionHandler |
| Security | Servlet SecurityFilterChain | Reactive SecurityWebFilterChain |
| Testing | MockMvc | WebTestClient |
| Rủi ro phổ biến | Thread pool exhaustion | Blocking event loop, cancellation/context loss |

Không chuyển MVC sang WebFlux chỉ vì nâng Spring. Chuyển web stack là một thay đổi kiến trúc riêng, cần đánh giá blocking database driver, provider SDK, security filter, metrics, test tooling và backpressure.

Nếu broker hiện dùng WebFlux nhưng provider SDK/JDBC là blocking, cần giới hạn và cô lập blocking work. Không gọi JDBC hoặc provider SDK blocking trực tiếp trên event loop. Nếu broker dùng MVC, việc nâng embedded servlet container vẫn cần kiểm tra filter, connector, TLS và request size/timeouts.

## 11. Thay đổi embedded server và HTTP behavior

Nâng Spring Boot có thể kéo theo phiên bản Tomcat, Jetty, Undertow hoặc Reactor Netty mới. Dù controller không đổi, HTTP behavior có thể thay đổi:

- Header parsing và giới hạn header size.
- Max request body size và multipart handling.
- URI normalization và encoded path handling.
- Connection timeout, keep-alive và idle timeout.
- HTTP/2, TLS protocol và cipher support.
- Compression và forwarded header processing.
- Graceful shutdown và connection draining.
- Error handling khi client ngắt kết nối.

Với OSB broker, cần kiểm tra endpoint path và query parameter không bị rewrite, ví dụ service instance ID có ký tự được encode; request body lớn có bị reject; proxy headers có được tin cậy đúng phạm vi; và timeout của load balancer/provider client có phù hợp.

Không bật trust-all forwarded headers ở môi trường public. Chỉ tin proxy header từ proxy/load balancer được cấu hình rõ ràng để tránh spoof scheme, host hoặc client address.

## 12. Giữ ổn định OSB HTTP contract khi nâng web stack

OSB API là contract bên ngoài. Dù Spring controller, router hoặc response model đổi, broker vẫn phải giữ:

- Method và path đúng endpoint OSB.
- Query parameters như service_id, plan_id, accepts_incomplete và operation.
- Header API version và authentication behavior.
- JSON property names và types.
- Status code theo trạng thái nghiệp vụ.
- Body schema cho catalog, provision, update, bind, last_operation và error.
- Semantics idempotency, async operation và retry.

Ví dụ, provision mới hoàn tất đồng bộ có thể trả 201; operation được chấp nhận async trả 202 với operation ID; last_operation trả 200 cùng state; update đồng bộ trả response đúng schema. Không để nâng Spring làm một DELETE response rỗng chuyển từ 200 theo OSB contract thành 204 chỉ vì framework mới thay cách biểu diễn empty body.

Contract test cần chạy qua HTTP stack thật của Spring application context. Test gọi trực tiếp service method sẽ không phát hiện lỗi route, filter, converter, serialization hoặc status mapping.

## 13. Jackson và JSON serialization

Jackson version hoặc ObjectMapper configuration có thể ảnh hưởng trực tiếp đến JSON OSB:

- snake_case và camelCase.
- Null field inclusion.
- Enum serialization.
- Date/time format.
- Unknown property handling.
- Polymorphic type metadata.
- Constructor/record binding.
- Custom serializer/deserializer.
- Number coercion và boolean coercion.

Ví dụ Java record:

~~~java
public record LastOperationResponse(
        String state,
        String description) {
}
~~~

Nếu ObjectMapper dùng naming strategy khác, JSON có thể phát ra lastOperation thay vì state/description hoặc các field OSB mong đợi. Dùng annotation hoặc cấu hình serializer rõ ràng cho model giao thức khi cần.

Test JSON theo cấu trúc:

~~~java
client.get()
        .uri("/v2/service_instances/instance-42/last_operation?operation=op-42")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.state").isEqualTo("in progress");
~~~

Không chỉ snapshot toàn bộ JSON rồi coi mọi thay đổi là lỗi. Kiểm tra required fields, types, enum values và những extension mà broker chủ đích công bố.

## 14. Spring Security và thứ tự filter

Nâng Spring Security có thể thay đổi DSL, matcher behavior, default security và cách cấu hình nhiều filter chain. Với broker, cần bảo đảm:

- Endpoint OSB yêu cầu authentication theo cấu hình broker.
- Catalog không vô tình bị mở public nếu policy yêu cầu bảo vệ.
- Actuator health/readiness chỉ expose những endpoint cần thiết.
- Internal drain/management endpoint không bị truy cập từ mạng không tin cậy.
- CSRF policy phù hợp với API machine-to-machine và không tắt rộng hơn cần thiết.
- CORS không mở wildcard cho endpoint có credentials nếu không có lý do.
- Error response không lộ thông tin xác thực.
- Role/tenant authorization vẫn được áp dụng sau khi URL matcher thay đổi.

Ví dụ cấu trúc SecurityFilterChain:

~~~java
@Bean
SecurityFilterChain brokerSecurity(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(authorize -> authorize
                    .requestMatchers("/actuator/health/**").permitAll()
                    .requestMatchers("/v2/**").authenticated()
                    .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
}
~~~

Đây là ví dụ minh họa, không phải cấu hình production hoàn chỉnh. Phải bổ sung password encoder, secret sourcing, TLS termination, CSRF policy phù hợp, actuator exposure và các chain riêng nếu ứng dụng có nhiều loại endpoint. Contract/security tests cần xác minh cả request được phép và request bị từ chối.

## 15. Validation và error response

Nâng Spring có thể thay đổi cách Bean Validation phát hiện lỗi, exception được ném hoặc exception handler chuyển thành HTTP response. Nếu framework bắt đầu trả Problem Details mặc định, broker vẫn cần bảo đảm error JSON phù hợp với OSB contract.

Kiểm tra:

- Field validation trả status phù hợp và error code ổn định.
- Missing/malformed JSON không tạo side effect.
- Constraint violation không trả stack trace.
- Provider exception được ánh xạ sang error response an toàn.
- Không trả 200 cùng body lỗi nghiệp vụ.
- Error handler không nuốt status code hoặc operation metadata.
- Validation của query/path/header và body nhất quán.

Nên có test riêng cho lỗi 400, 401, 404, 409, 412, 422 và 5xx theo endpoint/cấu hình broker. Không giả định một exception Java luôn được ánh xạ thành cùng status qua mọi phiên bản Spring.

## 16. Transaction, persistence và ORM compatibility

Spring Boot upgrade có thể kéo theo Hibernate/JPA, transaction manager hoặc JDBC driver mới. Các thay đổi này ảnh hưởng đến operation store và idempotency:

- Flush timing hoặc transaction boundary thay đổi.
- Lazy loading và proxy behavior khác.
- SQL dialect hoặc generated SQL đổi.
- Optimistic locking/version column xử lý khác.
- Connection pool default và timeout đổi.
- Database driver thay đổi type mapping hoặc TLS.
- Migration tool thay đổi validation/checksum behavior.

Với broker, đặc biệt kiểm tra transaction ghi operation và outbox. Broker không được trả 202 trước khi transaction chứa operation record và outbox intent đã commit. Nếu upgrade làm thay đổi reactive transaction propagation hoặc proxy boundary, có thể xuất hiện response thành công nhưng operation record chưa bền vững.

Kiểm tra cả trường hợp rollback, duplicate request, concurrent update và worker restart. Không dựa vào H2 test nếu production dùng PostgreSQL/MySQL có semantics khác; dùng Testcontainers hoặc database tương thích trong integration test.

## 17. Spring Cloud Open Service Broker API compatibility

Spring Cloud Open Service Broker cung cấp abstraction để triển khai catalog, provision, update, deprovision, binding và last_operation. Khi nâng thư viện, hãy xác minh:

- Service implementation interface và method signatures.
- Request/response model constructors, builders và accessors.
- Async response flags và operation field.
- Capability declaration trong catalog.
- Context, bind_resource và parameters mapping.
- Error mapping và exception types.
- Retrieval API cho service instance/binding nếu khai báo capability.
- Authentication và version handling do framework cung cấp.
- WebFlux/MVC integration và test utilities.

Không sửa business semantics chỉ để thích nghi với API Java mới. Nếu builder hoặc interface đổi, tạo adapter ở ranh giới framework và giữ domain use case ổn định.

Ví dụ kiến trúc:

~~~text
OSB HTTP endpoint
      |
Spring Cloud Open Service Broker adapter
      |
Application use case
      |
Domain model / operation state machine
      |
Provider adapter + persistence
~~~

Tách framework response model khỏi domain model giúp nâng Spring Cloud Open Service Broker dễ hơn. Adapter chịu trách nhiệm map request/response; domain layer vẫn quản lý idempotency, provider state và lifecycle.

## 18. Cấu hình timeout và retry sau nâng cấp

Một version mới có thể thay default timeout hoặc retry behavior của HTTP client. Nếu timeout ngắn hơn, provider operation có thể bị coi là thất bại sớm; nếu timeout dài hơn, thread hoặc connection bị giữ quá lâu.

Rà soát:

- Connect timeout và response/read timeout.
- Connection pool max connections, pending acquire timeout và idle eviction.
- Retryable status/exception và số lần retry.
- Backoff, jitter và Retry-After.
- Circuit breaker thresholds và half-open behavior.
- Cancellation khi client disconnect hoặc shutdown.
- Timeout của load balancer so với broker/provider client.

Không retry POST/PUT có side effect một cách tự động nếu không có idempotency key hoặc read-before-retry. Một retry ở HTTP client có thể tạo provider resource trùng nếu request đầu đã đến provider nhưng response bị mất.

## 19. Actuator, health checks và metrics

Nâng Boot/Micrometer có thể đổi endpoint exposure, metric name, tag hoặc histogram configuration. Với broker, kiểm tra:

- Readiness phản ánh khả năng nhận request mới.
- Liveness không phụ thuộc mọi provider tạm thời phải healthy.
- Health contributor database/queue có timeout và không block event loop.
- Metric name/tag không bị đổi ngoài dashboard/alert.
- Histogram buckets và percentiles vẫn phù hợp SLO.
- Prometheus endpoint chỉ được expose qua mạng và quyền phù hợp.
- Tracing không ghi secret hoặc payload nhạy cảm.

Nếu metric name đổi, dashboard có thể hiện khoảng trống hoặc alert không còn kích hoạt dù ứng dụng vẫn chạy. So sánh metric inventory trước/sau nâng cấp và cập nhật dashboard/rule cùng release.

## 20. Logging, tracing và context propagation

Nâng Spring, Reactor hoặc Micrometer Tracing có thể ảnh hưởng MDC, trace context và propagation qua thread/event loop. Điều này quan trọng khi broker xử lý operation async:

- Correlation ID từ HTTP request cần gắn với operation record.
- Worker chạy sau request cần khôi phục trace/correlation metadata từ persistence/message.
- Reactor Context không tự tồn tại sau khi operation được enqueue.
- Không giả định MDC thread-local tự truyền qua mọi scheduler.
- Trace sampling không được làm mất audit event bắt buộc.
- Log phải che Authorization, password, token và binding credentials.

Contract test không thay thế observability test. Có thể thêm integration test xác minh correlation ID xuất hiện ở log/trace của provider call và worker, nhưng không chứa secret.

## 21. Quy trình nâng cấp theo từng bước

Một quy trình an toàn nên chia thành các chặng nhỏ:

1. **Inventory:** liệt kê Java, Boot, Cloud train, Open Service Broker, web server, security, JSON, persistence và plugin build.
2. **Compatibility review:** tra release notes, migration guide, Java baseline và dependency matrix.
3. **Baseline tests:** chạy unit, integration, contract, security và performance tests trên phiên bản hiện tại.
4. **Build/toolchain upgrade:** nâng JDK/build plugin trước nếu cần, giữ framework dependencies ổn định để tách lỗi.
5. **Framework upgrade:** nâng Boot và Cloud train theo cặp được hỗ trợ; xử lý API/deprecation/Jakarta.
6. **Configuration migration:** đổi property và default một cách tường minh.
7. **Web/security migration:** kiểm tra servlet/reactive stack, filter, serialization và error mapping.
8. **Persistence migration:** đánh giá schema, driver, ORM, transaction và outbox.
9. **Contract verification:** chạy OSB HTTP contract tests và platform integration.
10. **Staging/canary:** deploy trên môi trường tương đương production, thử catalog/provision/bind/update/unbind/deprovision.
11. **Production rollout:** rolling deploy với backward compatibility và đủ capacity.
12. **Post-deploy verification:** kiểm tra readiness, operation backlog, error rate, latency, provider jobs và consumer connectivity.

Không thay JDK, Boot, Cloud train, web stack và database driver cùng lúc nếu không có lý do bắt buộc. Tách thay đổi giúp xác định nguồn gốc lỗi và rollback chính xác.

## 22. Dùng dependency tree để tìm xung đột

Dependency tree cho biết artifact nào kéo phiên bản thư viện nào. Kiểm tra trước và sau nâng cấp để tìm:

- Nhiều version của cùng artifact.
- Dependency bị override ngoài BOM.
- Thư viện cũ kéo javax API vào stack Jakarta.
- Logging implementation trùng lặp.
- Jackson modules không cùng version.
- Servlet API vừa javax vừa jakarta.
- Reactor/Netty version lệch với Spring Cloud BOM.
- Vulnerability hoặc dependency đã hết hỗ trợ.

Maven:

~~~text
mvn dependency:tree
mvn help:effective-pom
~~~

Gradle:

~~~text
./gradlew dependencies
./gradlew dependencyInsight --dependency jackson-databind
~~~

Đây là lệnh kiểm tra để đội dự án chạy trong workspace/build pipeline. Khi xử lý xung đột, ưu tiên BOM tương thích và nâng/thay thư viện kéo version cũ thay vì thêm override ngẫu nhiên.

## 23. Kiểm thử trước và sau nâng cấp

Giữ cùng một bộ test trên phiên bản cũ và mới để so sánh behavior. Các nhóm test tối thiểu:

| Nhóm | Điều cần chứng minh |
|---|---|
| Compile/API | Source build thành công, không còn API removed hoặc signature mismatch |
| Application context | Bean, auto-configuration và configuration binding đúng |
| Catalog contract | Service/plan IDs, capability và JSON schema không đổi ngoài chủ đích |
| Provision | Status/body, sync/async, idempotency và provider mapping đúng |
| Update | Plan/parameters transition, previous_values và error mapping đúng |
| Bind/unbind | Credentials, binding lifecycle và revoke behavior đúng |
| Deprovision | Delete semantics và retry không tạo orphan |
| Last operation | Operation ID, state values và polling response đúng |
| Security | Authentication, authorization, tenant isolation và TLS đúng |
| Serialization | Snake_case, null, enum, date/time và numeric types đúng |
| Persistence | Transaction, outbox, optimistic lock và migration đúng |
| Shutdown | Readiness, graceful drain và worker recovery đúng |
| Observability | Health, metrics, logs và traces vẫn hoạt động |
| Performance | Latency, throughput, memory và connection pool không suy giảm ngoài ngưỡng |

Một bài test “application starts” không đủ. Cần chạy các thao tác OSB qua HTTP thật và xác minh cả provider side effects bằng mock/stub hoặc sandbox.

## 24. Contract snapshot và regression testing

Có thể lưu catalog/request/response fixtures theo OSB API version và so sánh trước/sau nâng cấp. Snapshot nên tập trung vào các field contract quan trọng:

- JSON property names và types.
- HTTP status và headers.
- Error codes.
- Operation state vocabulary.
- Catalog capabilities.
- Binding credentials shape (dùng secret giả lập).

Không snapshot provider-generated IDs hoặc timestamp động như giá trị cố định. Chuẩn hóa các field này trong test fixture. Không để snapshot chứa credentials production.

Ví dụ assertion:

~~~java
client.get()
        .uri("/v2/catalog")
        .header("X-Broker-API-Version", "2.17")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody()
        .jsonPath("$.services[0].id").isEqualTo("postgres-service")
        .jsonPath("$.services[0].plans[0].id").isEqualTo("standard");
~~~

Test cần chạy trên cùng security filters và serialization configuration như production. Nếu dùng test slice làm thiếu auto-configuration, bổ sung application-context contract test.

## 25. Rolling deployment và tương thích ngược

Trong rolling deployment, replica cũ và mới cùng hoạt động. Do đó:

- Database schema phải được cả hai phiên bản đọc/ghi trong thời gian chuyển tiếp.
- Event/message payload phải backward-compatible hoặc được version hóa.
- Cache key và serialized object không được đổi không tương thích đột ngột.
- Operation state do phiên bản cũ tạo phải được worker mới đọc được.
- Worker cũ không được ghi đè state mới theo enum/format cũ.
- API response gửi cho nền tảng phải ổn định giữa các replica.
- Health/readiness behavior phải nhất quán để load balancer không route sai.

Với schema change, dùng expand-migrate-contract: thêm field/bảng trước, deploy code tương thích, backfill, chuyển read/write, rồi xóa cấu trúc cũ ở release sau. Không ghép migration phá hủy với lần nâng framework nếu vẫn cần rollback về artifact cũ.

## 26. Rollback khi nâng cấp framework thất bại

Rollback ứng dụng có thể đơn giản hơn rollback schema hoặc data format. Trước khi deploy, xác định:

- Artifact cũ có thể chạy với schema đã expand không.
- Migration nào không thể đảo ngược.
- Config mới có tương thích với code cũ không.
- Message mới có thể được worker cũ đọc không.
- Cache/session có chứa object serialize theo class mới không.
- Có thể chạy song song old/new version trong thời gian rollout không.

Nếu migration schema đã chạy, không mặc định chạy migration down. Có thể giữ schema mở rộng và rollback code trước. Với thay đổi data format không tương thích, cần forward-fix hoặc restore theo runbook và RPO/RTO đã phê duyệt.

## 27. Ví dụ cấu hình web stack cần so sánh

Một cấu hình application có thể làm rõ các hành vi quan trọng thay vì dựa vào default:

~~~yaml
server:
  port: 8080
  shutdown: graceful
  forward-headers-strategy: framework

spring:
  application:
    name: service-broker
  jackson:
    default-property-inclusion: non_null
  lifecycle:
    timeout-per-shutdown-phase: 45s

management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
~~~

Đây là ví dụ để chỉ ra các property có thể cần quản lý; giá trị cụ thể phải theo kiến trúc và phiên bản Boot mục tiêu. Không expose Actuator rộng trên public interface nếu không có security policy tương ứng. Nếu broker nằm sau reverse proxy, chỉ dùng forwarded-header strategy phù hợp với topology tin cậy.

## 28. Kiểm thử hiệu năng và tài nguyên sau nâng cấp

Một upgrade có thể không làm sai contract nhưng làm tăng latency hoặc memory. Kiểm tra:

- P50/P95/P99 latency của catalog, provision, bind và last_operation.
- Throughput và request concurrency.
- JVM heap, metaspace, direct memory và GC pause.
- Servlet thread pool hoặc Reactor event-loop utilization.
- HikariCP active/idle/pending connections.
- HTTP client connection pool và pending acquire.
- Queue lag và operation oldest age.
- CPU throttling, container memory limit và restart count.

So sánh cùng workload, dataset và môi trường. Nếu latency tăng, phân tích metric/profiling trước khi tăng resource limit một cách mù quáng. Kiểm tra cả cold start và steady state vì class loading, JIT và connection initialization có thể làm kết quả khác nhau.

## 29. Kiểm soát thay đổi cấu hình và secret

Nâng cấp có thể làm property binding hoặc secret integration thay đổi. Không ghi credentials vào file cấu hình mặc định hoặc commit. Dùng secret manager/environment injection được nền tảng hỗ trợ.

Khi đổi tên property:

1. Xác định property cũ và mới.
2. Cập nhật deployment manifest/ConfigMap/secret reference.
3. Nếu cần rolling deployment, hỗ trợ cả hai property trong giai đoạn chuyển tiếp.
4. Cảnh báo khi property cũ còn được dùng.
5. Xóa alias cũ sau khi mọi environment đã migrate.
6. Kiểm tra không có secret bị copy vào log khi configuration binding fail.

Không giữ cả hai property với giá trị xung đột mà không định nghĩa precedence. Fail fast nếu cấu hình mâu thuẫn thay vì âm thầm chọn một giá trị.

## 30. Những lỗi nâng cấp thường gặp

**Nâng Boot nhưng giữ Cloud release train không tương thích:** dependency resolve được nhưng application context fail hoặc runtime behavior không ổn định. Chọn cặp theo compatibility matrix.

**Override Jackson/Netty riêng lẻ:** tạo version skew ngoài BOM. Kiểm tra dependency tree và dùng dependency management thống nhất.

**Replace toàn bộ javax thành jakarta:** làm hỏng Java SE packages vẫn thuộc javax. Chỉ migrate các API Jakarta EE liên quan.

**Chuyển MVC sang WebFlux cùng lúc nâng Boot:** thay đổi thread model, filter và blocking behavior. Tách thành một migration riêng.

**Dựa vào default property:** security, serialization hoặc timeout thay đổi mà không có config diff. Ghi rõ property quan trọng và test.

**Chỉ chạy unit test:** không phát hiện lỗi routing, status mapping, header hoặc JSON. Chạy HTTP contract test.

**Nâng Spring Security nhưng không test negative cases:** endpoint có thể bị mở hoặc khóa ngoài ý muốn. Test auth/authorization cho từng route.

**Nâng ORM mà không kiểm tra transaction:** operation và outbox có thể không còn atomic như trước. Chạy database integration tests.

**Rollback code nhưng không xem schema/message compatibility:** phiên bản cũ không đọc được dữ liệu mới. Dùng expand-migrate-contract và rollback plan.

**Bỏ qua metrics sau nâng cấp:** dashboard/alert mất dữ liệu do metric rename. So sánh metric inventory và cập nhật rules.

## 31. Runbook đánh giá một lần nâng phiên bản

| Giai đoạn | Việc thực hiện | Bằng chứng cần lưu |
|---|---|---|
| Inventory | Chụp dependency/build/runtime/config hiện tại | Dependency tree, effective POM, config manifest |
| Compatibility | Kiểm tra Java, Boot, Cloud, OSB library và container matrix | Compatibility decision record |
| Baseline | Chạy test và đo latency/resource trước nâng | CI report, dashboard snapshot |
| Upgrade | Nâng toolchain/framework theo từng lớp | Commit và migration notes |
| Config diff | So sánh property/default/security/web behavior | Config diff đã review |
| Contract | Chạy catalog/lifecycle/error/header tests | Contract test report |
| Integration | Chạy database/provider/queue/security tests | Integration report |
| Staging | Thử deploy, rolling update và rollback | Deployment rehearsal |
| Production | Canary/rolling release và theo dõi SLO | Change record, metrics |
| Close | Xác nhận compatibility và cập nhật support matrix | Upgrade sign-off |

Nếu bất kỳ bước nào thất bại, ghi rõ lớp tương thích bị ảnh hưởng và quyết định: sửa code, thay dependency, giữ phiên bản cũ, thay cấu hình hay hoãn nâng cấp. Không tiếp tục chỉ vì build xanh nếu contract hoặc security test đỏ.

## 32. Checklist trước khi phát hành

- [ ] JDK build/runtime nằm trong support range của Spring Boot và Spring Cloud mục tiêu.
- [ ] Spring Boot và Spring Cloud release train thuộc tổ hợp tương thích.
- [ ] Spring Cloud Open Service Broker API được xác minh với phiên bản mục tiêu.
- [ ] Dependency tree không có version skew ngoài chủ đích.
- [ ] API Java deprecated/removed và internal API đã được rà soát.
- [ ] Jakarta namespace migration đã được xử lý đúng, không replace toàn cục javax.
- [ ] Servlet/reactive web stack không bị đổi ngoài kế hoạch.
- [ ] Server route, timeout, forwarded header và graceful shutdown đã được kiểm thử.
- [ ] Security filter chain, authentication, authorization và actuator exposure đã được kiểm thử.
- [ ] Jackson JSON contract và OSB response status/body vẫn đúng.
- [ ] ConfigurationProperties, property names và default đã được rà soát.
- [ ] Database driver, ORM, transaction, outbox và migration đã được kiểm tra.
- [ ] Health, metric, log và tracing vẫn hoạt động.
- [ ] Rolling deployment và rollback tương thích schema/message.
- [ ] Performance/load test đạt ngưỡng đã đặt.
- [ ] Có deployment runbook và bằng chứng staging/canary.

## 33. Trình tự triển khai cho service broker

Đối với SPRING_CLOUD_SERVICE_BROKER, có thể áp dụng trình tự:

1. Ghi nhận Java, Spring Boot, Spring Cloud, Open Service Broker library, web server và dependency hiện tại.
2. Chọn JDK và bộ phiên bản Spring theo compatibility matrix chính thức.
3. Nâng build toolchain và xử lý compile/deprecation warnings.
4. Nâng Boot/Cloud theo tổ hợp tương thích, xử lý Jakarta namespace và API thay đổi.
5. Rà soát configuration properties, security defaults, Actuator và web server settings.
6. Kiểm tra MVC/WebFlux model, blocking provider/database calls và timeout.
7. Xác minh JSON serialization và OSB HTTP contract.
8. Kiểm tra transaction, operation store, outbox, database driver và migration.
9. Chạy contract, security, integration, concurrency, performance và shutdown tests.
10. Thử rolling deployment, recovery và rollback trên staging.
11. Canary production, theo dõi SLO và operation backlog trước khi hoàn tất rollout.
12. Cập nhật dependency support matrix và runbook cho lần nâng cấp tiếp theo.

Một lần nâng cấp thành công không chỉ là ứng dụng biên dịch và khởi động được. Service broker phải giữ ổn định các endpoint OSB, JSON, status, authentication và lifecycle operation trong khi runtime, framework, cấu hình và web stack thay đổi. Đánh giá có hệ thống từng lớp tương thích, kiểm thử qua HTTP thật và triển khai theo từng chặng giúp phát hiện sớm breaking change, giảm rủi ro production và giữ nền tảng broker có thể tiếp tục quản lý service instance an toàn.
