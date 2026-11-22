# Không có endpoint /v3/api-docs do sai starter hoặc cấu hình tắt

Trong ứng dụng Spring Boot có springdoc-openapi, request đến /v3/api-docs có thể trả 404, 401, 403 hoặc bị chuyển hướng sang trang đăng nhập. Những kết quả này có nguyên nhân khác nhau. 404 thường gợi ý endpoint tài liệu chưa được đăng ký, URL đang gọi không đúng hoặc proxy không chuyển tiếp request. 401 và 403 thường liên quan đến Spring Security. Nếu Swagger UI không mở nhưng /v3/api-docs vẫn trả JSON, vấn đề nằm ở phần giao diện hoặc static resource chứ không phải endpoint OpenAPI.

Quy trình chẩn đoán nên bắt đầu từ web stack và dependency starter, sau đó kiểm tra property bật/tắt, path tùy chỉnh, context path và security. Không kết luận springdoc không hoạt động chỉ vì không thấy nút Swagger UI: starter API-only vẫn có thể cung cấp OpenAPI JSON/YAML mà không có giao diện.

## 1. Phân biệt lỗi endpoint với lỗi Swagger UI

Springdoc cung cấp hai phần có thể được sử dụng độc lập:

- OpenAPI endpoint tạo document JSON/YAML, mặc định là /v3/api-docs và /v3/api-docs.yaml.
- Swagger UI cung cấp giao diện trình duyệt để xem và thử các operation. Giao diện thường được mở qua /swagger-ui.html.

| Kết quả quan sát | Ý nghĩa cần kiểm tra |
| --- | --- |
| /v3/api-docs trả 200 và JSON hợp lệ | Endpoint hoạt động. Nếu UI lỗi, kiểm tra starter UI, static resource, swagger-config và security. |
| /v3/api-docs trả 404 | Kiểm tra starter, auto-configuration, property bật/tắt, path tùy chỉnh, context path và proxy. |
| /v3/api-docs trả 401 | Endpoint có thể đã được đăng ký nhưng request chưa được xác thực. |
| /v3/api-docs trả 403 | Request đã đến security layer nhưng principal không có quyền hoặc bị policy chặn. |
| Request bị 302 hoặc 303 tới trang đăng nhập | Security đang dùng form login hoặc cơ chế redirect; kiểm tra Location và cấu hình xác thực. |
| /v3/api-docs trả 200 nhưng paths rỗng | Endpoint đã tồn tại; kiểm tra controller scanning, group filter, mapping và @Hidden. |
| /swagger-ui.html lỗi nhưng /v3/api-docs hoạt động | Kiểm tra đang dùng starter *-api hay *-ui, UI có bị tắt không và các request tài nguyên giao diện. |

Một document có paths: {} là tình huống khác với không có endpoint. Trong trường hợp đầu, springdoc đã tạo document nhưng không tìm thấy operation phù hợp với cấu hình quét hoặc bộ lọc. Trong trường hợp thứ hai, route tài liệu có thể chưa được đăng ký hoặc không thể truy cập ở URL đang gọi.

## 2. Chọn starter theo web stack

Với Spring Boot 3 và springdoc 2.x, chọn starter đúng với ứng dụng:

| Kiến trúc ứng dụng | Có Swagger UI | Chỉ cần OpenAPI JSON/YAML |
| --- | --- | --- |
| Spring MVC / Servlet | springdoc-openapi-starter-webmvc-ui | springdoc-openapi-starter-webmvc-api |
| Spring WebFlux / Reactive | springdoc-openapi-starter-webflux-ui | springdoc-openapi-starter-webflux-api |

Spring Boot 4 dùng dòng springdoc 3.x và các starter tương ứng. Ứng dụng Spring Boot 2 thuộc dòng springdoc 1.x legacy, dùng artifact theo tài liệu v1 thay vì sao chép tên starter v2/v3. Luôn kiểm tra compatibility matrix của đúng dòng Spring Boot trước khi chọn version.

Ví dụ Maven cho ứng dụng Spring MVC trên Spring Boot 3:

~~~xml
<properties>
    <springdoc.version>2.10.0</springdoc.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
        <version>${springdoc.version}</version>
    </dependency>
</dependencies>
~~~

Ví dụ trên dùng webmvc-ui để có cả OpenAPI endpoint và Swagger UI. Nếu ứng dụng chỉ cần endpoint tài liệu, đổi artifact thành springdoc-openapi-starter-webmvc-api. Không cần thêm starter UI chỉ để tạo JSON.

Với Spring WebFlux, dùng spring-boot-starter-webflux và starter springdoc-openapi-starter-webflux-ui hoặc springdoc-openapi-starter-webflux-api tương ứng. Không chọn starter MVC cho ứng dụng reactive thuần.

### 2.1. Những cách khai báo dependency dễ sai

| Cấu hình sai hoặc đáng nghi | Vì sao có vấn đề | Cách xử lý |
| --- | --- | --- |
| Ứng dụng WebFlux nhưng chỉ thêm starter webmvc | Auto-configuration không khớp web stack đang chạy | Dùng starter webflux phù hợp. |
| Ứng dụng MVC nhưng thêm starter webflux | Có thể không có integration MVC mong muốn | Dùng starter webmvc. |
| Dùng springdoc-openapi-starter-webmvc-ui cho Boot 2 | Starter hiện đại thuộc dòng springdoc 2.x, không dành cho Boot 2 | Dùng module legacy springdoc 1.x tương thích Boot 2 hoặc nâng nền tảng theo kế hoạch. |
| Dùng springdoc 1.x trong Boot 3/4 | Sai dòng nền tảng và namespace | Boot 3 dùng springdoc 2.x; Boot 4 dùng springdoc 3.x. |
| Chỉ thêm Swagger annotations | Annotation mô tả API nhưng không đăng ký endpoint springdoc | Thêm starter springdoc phù hợp. |
| Dùng starter *-api nhưng mong đợi Swagger UI | API-only không cung cấp giao diện UI | Chọn starter *-ui nếu cần giao diện. |
| Thêm cả MVC UI và WebFlux UI | Kéo hai integration stack vào cùng ứng dụng, gây cấu hình dư thừa hoặc xung đột | Chỉ giữ starter tương ứng web stack thực tế. |

Đừng dùng sự hiện diện của class annotation @Operation hoặc @Schema làm bằng chứng rằng endpoint đã được đăng ký. Các annotation này chỉ được springdoc xử lý khi integration tương ứng đã có trong runtime classpath.

## 3. Xác minh web application type thực tế

Spring Boot có thể chạy dưới dạng Servlet MVC hoặc Reactive WebFlux. Kiểm tra dependency nền tảng:

~~~xml
<!-- Ứng dụng Spring MVC -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

~~~xml
<!-- Ứng dụng Spring WebFlux -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

Nếu cả spring-boot-starter-web và spring-boot-starter-webflux cùng có trong classpath, Spring Boot thường chọn MVC khi cả hai stack hiện diện. Điều này có thể khiến người phát triển nghĩ ứng dụng đang chạy WebFlux chỉ vì code có dùng Mono hoặc Flux. Hãy kiểm tra loại application context thực tế và chọn springdoc starter theo stack đã được Boot kích hoạt.

Mono hoặc Flux xuất hiện trong controller không tự chứng minh ứng dụng đang chạy WebFlux. Một ứng dụng MVC có thể dùng các kiểu reactive ở một số tầng mà vẫn chạy Servlet stack.

## 4. Xác minh dependency đã có trong runtime classpath

Một dependency xuất hiện trong file build chưa chắc đã có ở runtime. Kiểm tra dependency tree thay vì chỉ đọc pom.xml hoặc build.gradle.

Với Maven:

~~~bash
./mvnw dependency:tree -Dincludes=org.springdoc
./mvnw dependency:tree -Dincludes=org.springdoc,io.swagger.core.v3,org.springframework
~~~

Với Gradle:

~~~bash
./gradlew dependencyInsight --dependency springdoc-openapi --configuration runtimeClasspath
./gradlew dependencies --configuration runtimeClasspath
~~~

Xác nhận:

- Có đúng starter webmvc hoặc webflux.
- Version springdoc thuộc dòng tương thích với Spring Boot đang chạy.
- Starter nằm trong implementation hoặc scope runtime phù hợp, không chỉ ở test scope.
- Không có đồng thời artifact legacy và starter mới ngoài chủ đích.
- Không bị exclude module springdoc cần thiết bởi dependency khác.
- Không override Swagger Core hoặc Spring module sang version không tương thích.

Nếu dependency chỉ nằm trong testImplementation, test có thể thấy springdoc nhưng executable artifact production lại không có. Đưa starter vào dependency runtime của ứng dụng.

## 5. Kiểm tra property có tắt OpenAPI endpoint không

Property điều khiển việc bật/tắt OpenAPI endpoint là springdoc.api-docs.enabled. Giá trị mặc định là true. Nếu cấu hình thành false, springdoc không cung cấp endpoint API docs:

~~~yaml
springdoc:
  api-docs:
    enabled: false
~~~

Để bật lại:

~~~yaml
springdoc:
  api-docs:
    enabled: true
~~~

Kiểm tra mọi nguồn cấu hình có thể ghi đè giá trị này:

- application.yml hoặc application.properties.
- File profile như application-prod.yml, application-staging.yml.
- Environment variable, ví dụ SPRINGDOC_API_DOCS_ENABLED.
- JVM system property, ví dụ -Dspringdoc.api-docs.enabled=false.
- Tham số dòng lệnh, ví dụ --springdoc.api-docs.enabled=false.
- Config server, Kubernetes ConfigMap/Secret hoặc cấu hình triển khai bên ngoài.

Giá trị cuối cùng được quyết định bởi thứ tự ưu tiên property source của Spring Boot. Đừng chỉ tìm trong application.yml rồi kết luận property không bị tắt; profile hoặc environment của production có thể đặt giá trị khác.

Trong môi trường cần tài liệu, cấu hình có thể đặt:

~~~yaml
springdoc:
  api-docs:
    enabled: true
~~~

Nếu chính sách production yêu cầu tắt OpenAPI, giữ false là quyết định có chủ đích. Khi đó, đừng dùng việc mở Swagger UI làm cách xác minh endpoint docs; kiểm tra theo profile mà tài liệu được phép hoạt động.

## 6. Phân biệt api-docs.enabled với swagger-ui.enabled

Hai property điều khiển hai thành phần khác nhau:

| Property | Điều khiển | Hệ quả khi false |
| --- | --- | --- |
| springdoc.api-docs.enabled | OpenAPI JSON/YAML endpoint | /v3/api-docs không được cung cấp. |
| springdoc.swagger-ui.enabled | Swagger UI | Giao diện không được cung cấp, nhưng OpenAPI endpoint có thể vẫn hoạt động. |

Ví dụ chỉ tắt giao diện:

~~~yaml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: false
~~~

Trong cấu hình này, /v3/api-docs vẫn có thể trả JSON. Không bật Swagger UI chỉ để sửa lỗi API docs nếu nguyên nhân thực sự là springdoc.api-docs.enabled=false hoặc sai starter.

Ngược lại, nếu dùng starter API-only, không có giao diện là hành vi dự kiến. Endpoint JSON/YAML vẫn là phần cần kiểm tra.

## 7. Kiểm tra path đã được tùy chỉnh

Endpoint mặc định là /v3/api-docs, nhưng property sau có thể đổi path: springdoc.api-docs.path.

Ví dụ:

~~~yaml
springdoc:
  api-docs:
    path: /openapi
~~~

Sau cấu hình này, hãy gọi /openapi thay vì /v3/api-docs. YAML tương ứng thường ở /openapi.yaml. Nếu ứng dụng có group, document được phục vụ dưới base path mới, ví dụ /openapi/partner-v1.

Tìm property springdoc.api-docs.path trong tất cả profile và nguồn cấu hình. Nếu có giá trị tùy chỉnh, việc gọi /v3/api-docs có thể trả 404 dù springdoc đã hoạt động bình thường.

Không nhầm path tải document với path Swagger UI:

- springdoc.api-docs.path đổi URL JSON/YAML.
- springdoc.swagger-ui.path đổi URL entry point của giao diện.

Đổi UI path không đổi docs path. Đổi docs path cũng không tự đổi mapping API nghiệp vụ của controller.

## 8. Kiểm tra context path và reverse proxy

Ứng dụng Servlet có thể được đặt dưới context path:

~~~yaml
server:
  servlet:
    context-path: /store
~~~

Khi đó URL truy cập bên ngoài có thể là /store/v3/api-docs.

Với ứng dụng WebFlux, base path thường cấu hình bằng:

~~~yaml
spring:
  webflux:
    base-path: /store
~~~

Nếu ứng dụng chạy sau reverse proxy hoặc API gateway, proxy có thể thêm, bỏ hoặc rewrite prefix. Hãy xác định chiến lược thực tế:

1. Proxy giữ nguyên prefix khi forward request.
2. Proxy strip prefix rồi forward path đã rút gọn.
3. Proxy rewrite cả request và response redirect.

Kiểm tra URL từ client qua public ingress, không chỉ gọi localhost backend. Nếu proxy publish dưới /store, request công khai có thể là /store/v3/api-docs trong khi backend nhận /v3/api-docs.

Nếu springdoc cần sinh URL tuyệt đối dựa trên scheme/host/prefix public, cấu hình forwarded headers ở proxy và Spring. Chỉ tin forwarded headers do proxy đáng tin cậy thiết lập; không cho request Internet tùy ý quyết định host hoặc prefix được phản ánh trong document.

## 9. Phân biệt 404 với 401, 403 và redirect do Spring Security

Spring Security có thể chặn endpoint tài liệu dù route springdoc đã được đăng ký:

| Status | Nguyên nhân thường gặp | Cách xác minh |
| --- | --- | --- |
| 401 Unauthorized | Chưa đăng nhập hoặc token thiếu/không hợp lệ | Gửi credential hợp lệ và xem authentication entry point. |
| 403 Forbidden | Đã xác thực nhưng thiếu authority/scope hoặc bị policy chặn | Kiểm tra authorization rule và authority của principal. |
| 302 Found hoặc 303 See Other | Form login redirect sang trang đăng nhập | Xem header Location và cấu hình login. |
| 404 Not Found | Route không tồn tại ở path đã gọi, bị proxy rewrite sai hoặc bị cấu hình loại bỏ | Kiểm tra mapping, property, context path và gateway. |
| 200 OK nhưng body là HTML | Có thể đã nhận trang login/fallback thay vì OpenAPI JSON | Kiểm tra Content-Type và body thực tế. |

Ví dụ rule cho môi trường mà tài liệu được phép đọc:

~~~java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers(
        "/v3/api-docs",
        "/v3/api-docs/**",
        "/v3/api-docs.yaml"
    ).hasAuthority("docs.read")
    .anyRequest().authenticated()
);
~~~

Đây chỉ là phần rule minh họa để ghép vào SecurityFilterChain hiện có. Nếu endpoint tài liệu cần public trong môi trường dev, có thể cấu hình quyền truy cập phù hợp với policy của môi trường. Nếu tài liệu nội bộ, giữ xác thực và cấp authority cho API registry hoặc developer. Không mở toàn bộ ứng dụng chỉ để làm /v3/api-docs trả 200.

Khi đổi springdoc.api-docs.path, cập nhật security matcher tương ứng. Đặc biệt, URL YAML như /v3/api-docs.yaml là sibling của base path; pattern /v3/api-docs/** có thể không bao phủ nó. Kiểm tra cả JSON, YAML, group và swagger-config.

## 10. Kiểm tra bằng curl theo từng lớp

Gọi trực tiếp endpoint mặc định:

~~~bash
curl -i http://localhost:8080/v3/api-docs
~~~

Kiểm tra YAML:

~~~bash
curl -i http://localhost:8080/v3/api-docs.yaml
~~~

Nếu đã đổi path:

~~~bash
curl -i http://localhost:8080/openapi
~~~

Nếu ứng dụng có context path:

~~~bash
curl -i http://localhost:8080/store/v3/api-docs
~~~

Nếu endpoint cần xác thực:

~~~bash
curl -i \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  http://localhost:8080/v3/api-docs
~~~

Thay ACCESS_TOKEN bằng token test hợp lệ trong môi trường của bạn. Không ghi token thật vào script, log chia sẻ hoặc tài liệu. Đọc cả status, Content-Type, Location và response body; status 200 nhưng content type text/html không phải document OpenAPI JSON.

## 11. Kiểm tra cấu hình runtime và log khởi động

Khi dependency và property trông có vẻ đúng nhưng endpoint vẫn không xuất hiện:

1. Khởi động lại ứng dụng sau khi thay dependency hoặc config. Thay đổi build file không tự cập nhật runtime process đang chạy.
2. Kiểm tra log startup để xác nhận application context đã khởi động thành công và không có lỗi tạo bean/auto-configuration.
3. Bật log chi tiết có giới hạn cho package springdoc trong môi trường phát triển:

~~~yaml
logging:
  level:
    org.springdoc: DEBUG
~~~

4. Chạy ứng dụng với --debug để xem condition evaluation report của Spring Boot khi cần xác định auto-configuration không được kích hoạt.
5. Nếu Actuator mappings đã được expose và bảo vệ an toàn trong môi trường nội bộ, kiểm tra /actuator/mappings để tìm handler của API docs. Không expose mappings công khai chỉ để chẩn đoán.

Không phải mọi bản springdoc đều ghi một dòng log duy nhất báo endpoint đã đăng ký. Dùng log cùng với dependency tree, property runtime và request thực tế để khoanh vùng.

## 12. Kiểm tra dependency bị loại hoặc xung đột

Nếu starter có trong build file nhưng endpoint không xuất hiện, dependency có thể bị exclude hoặc bị thay thế bởi version không tương thích.

Maven:

~~~bash
./mvnw dependency:tree -Dincludes=org.springdoc,io.swagger.core.v3
./mvnw help:effective-pom
~~~

Gradle:

~~~bash
./gradlew dependencyInsight --dependency springdoc-openapi --configuration runtimeClasspath
./gradlew dependencyInsight --dependency swagger-core --configuration runtimeClasspath
~~~

Tìm các tình huống:

- Có cả springdoc 1.x và 2.x/3.x.
- Dùng starter MVC và WebFlux cùng lúc dù ứng dụng chỉ chạy một stack.
- Dependency springdoc bị khai báo ở test scope thay vì runtime.
- Có exclude loại module auto-configuration hoặc core.
- Một dependency khác ép Swagger Core/Jackson/Spring Framework sang version không tương thích.
- Dùng artifact cũ springdoc-openapi-ui trong ứng dụng đã chuyển sang starter hiện đại.

Không thêm thủ công mọi module Swagger để bù dependency thiếu. Trước tiên xác định starter đang kéo những artifact nào, version được resolve và dependency path nào gây xung đột.

## 13. Phân biệt endpoint không tồn tại với document rỗng

Nếu /v3/api-docs trả 200 nhưng paths rỗng, springdoc đã cung cấp endpoint. Khi đó, kiểm tra:

- Controller có được Spring đăng ký làm bean hay không.
- Mapping có thực sự là request mapping được Spring MVC/WebFlux nhận diện không.
- springdoc.packages-to-scan hoặc springdoc.paths-to-match có lọc mất controller không.
- Group đang gọi có packagesToScan, pathsToMatch hoặc pathsToExclude phù hợp không.
- Operation/controller có gắn @Hidden không.
- Endpoint có nằm trong management context hoặc group khác không.

Ví dụ filter package quá hẹp:

~~~yaml
springdoc:
  packages-to-scan: com.example.publicapi
~~~

Nếu controller thực tế nằm trong com.example.api.orders, nó có thể không được đưa vào document. Mở rộng hoặc sửa package filter theo cấu trúc thật của ứng dụng. Việc filter controller không nên được dùng để sửa endpoint docs bị 404; nó chỉ điều khiển operation nào xuất hiện trong document.

## 14. Ví dụ cấu hình tối thiểu để khôi phục OpenAPI endpoint

Với ứng dụng Spring MVC trên Spring Boot 3 và springdoc 2.x, cấu hình tối thiểu có thể là:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-api</artifactId>
    <version>2.10.0</version>
</dependency>
~~~

~~~yaml
springdoc:
  api-docs:
    enabled: true
    path: /v3/api-docs
  swagger-ui:
    enabled: false
~~~

Starter API-only là đủ cho OpenAPI JSON/YAML. swagger-ui.enabled=false ở ví dụ này chỉ tắt giao diện, không tắt endpoint tài liệu. Version 2.10.0 là ví dụ cho dòng Boot 3.5.x; chọn version theo compatibility matrix của ứng dụng thực tế.

Nếu cần Swagger UI, đổi dependency sang springdoc-openapi-starter-webmvc-ui và đặt springdoc.swagger-ui.enabled: true hoặc bỏ property để dùng mặc định. Với WebFlux, thay starter tương ứng sang WebFlux.

## 15. Kiểm thử endpoint sau khi sửa

Một integration test đơn giản có thể xác nhận endpoint đã trả JSON và chứa trường OpenAPI:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OpenApiEndpointAvailabilityTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void servesOpenApiDocument() throws Exception {
        String body = mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();

        JsonNode document = objectMapper.readTree(body);
        assertThat(document.path("openapi").asText()).startsWith("3.");
        assertThat(document.path("info").isObject()).isTrue();
        assertThat(document.path("paths").isObject()).isTrue();
    }
}
~~~

Ví dụ giả định docs endpoint không bị security chặn trong test. Nếu ứng dụng bảo vệ document, thêm authentication và authority phù hợp. Nếu đã đổi springdoc.api-docs.path, thay URL trong test theo cấu hình. Với ứng dụng WebFlux, dùng WebTestClient thay vì MockMvc.

Test này xác nhận document tồn tại và có cấu trúc cơ bản. Để xác nhận API thực tế được công bố, thêm assertion cho một path và operationId cụ thể. Để xác nhận Swagger UI, kiểm tra UI endpoint và các tài nguyên/config mà trình duyệt tải riêng.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| /v3/api-docs trả 404 ngay sau khi thêm dependency | Starter sai web stack hoặc không có trong runtime | Chọn đúng webmvc/webflux starter và kiểm tra runtime dependency tree. |
| /v3/api-docs trả 404 chỉ ở production | Profile, environment hoặc ConfigMap tắt docs; context path/proxy khác local | Kiểm tra property runtime và URL public qua ingress. |
| /v3/api-docs bị tắt dù YAML local đặt true | Property source có độ ưu tiên cao hơn ghi đè thành false | Kiểm tra command line, JVM, env, profile và config server. |
| /v3/api-docs trả 401/403 | Spring Security chặn request | Kiểm tra authentication, authority và matcher docs. |
| /v3/api-docs redirect sang login | Security dùng form login | Kiểm tra Location và xác thực theo policy. |
| /v3/api-docs hoạt động nhưng UI không có | Dùng starter *-api hoặc UI bị disable | Dùng starter *-ui và kiểm tra swagger-ui.enabled. |
| UI mở nhưng báo không tải được definition | swagger-config trỏ URL cũ, CORS, security hoặc proxy rewrite | Kiểm tra Network tab và request đến JSON/YAML. |
| Gọi /v3/api-docs 404 nhưng /openapi hoạt động | springdoc.api-docs.path đã đổi | Dùng endpoint tùy chỉnh và cập nhật consumer. |
| Chỉ group endpoint hoạt động | Đang dùng group URL, hoặc document mặc định không được cấu hình như dự kiến | Kiểm tra group id và base path docs. |
| Endpoint trả 200 nhưng paths rỗng | Package/path filter hoặc controller scanning không khớp | Kiểm tra package, path filter, mapping và @Hidden. |
| Local chạy nhưng proxy trả 404 | Prefix bị strip/giữ sai hoặc proxy không route docs path | Kiểm tra rewrite, forwarded prefix và public URL. |
| API docs hoạt động trong test nhưng không ở production | Dependency chỉ nằm test scope hoặc profile khác nhau | Kiểm tra runtime artifact và effective configuration. |

## 17. Checklist chẩn đoán

Thực hiện lần lượt:

1. Gọi trực tiếp /v3/api-docs và ghi nhận status, Content-Type, Location và body.
2. Xác định ứng dụng chạy MVC hay WebFlux.
3. Xác nhận starter springdoc khớp web stack và có trong runtime classpath.
4. Xác nhận version springdoc tương thích với Spring Boot.
5. Kiểm tra springdoc.api-docs.enabled ở cấu hình runtime, không chỉ file local.
6. Kiểm tra springdoc.api-docs.path có bị tùy chỉnh không.
7. Kiểm tra Servlet context path hoặc WebFlux base path.
8. Kiểm tra proxy/gateway có rewrite prefix và route endpoint docs không.
9. Phân biệt 404 với 401, 403 và redirect do Spring Security.
10. Nếu JSON trả 200 nhưng paths rỗng, kiểm tra package/path filters và @Hidden.
11. Nếu chỉ UI lỗi, kiểm tra starter *-ui, swagger-ui.enabled, swagger-config và static resources.
12. Kiểm tra dependency tree và log startup khi nguyên nhân chưa rõ.
13. Chạy integration test cho JSON và YAML sau khi sửa.

## 18. Nguyên tắc áp dụng

- Chọn starter theo web stack thực tế: MVC hoặc WebFlux.
- Phân biệt starter API-only với starter có Swagger UI.
- Dùng đúng dòng springdoc cho thế hệ Spring Boot đang chạy.
- Kiểm tra springdoc.api-docs.enabled và các property source ghi đè.
- Kiểm tra springdoc.api-docs.path trước khi kết luận URL mặc định bị mất.
- Tách lỗi endpoint khỏi lỗi Swagger UI và lỗi security.
- Đọc status, content type, redirect và response body thay vì chỉ nhìn trang trình duyệt.
- Kiểm tra context path, reverse proxy và runtime dependency tree.
- Chỉ kiểm tra package/path filters khi endpoint trả document nhưng thiếu operation.
- Thêm integration test để endpoint JSON/YAML tiếp tục hoạt động sau nâng cấp.

Khi /v3/api-docs không xuất hiện, hãy xác định request đang đến URL nào, ứng dụng chạy web stack nào và springdoc starter nào có trong runtime. Sau đó kiểm tra property bật/tắt, path tùy chỉnh, context path, proxy và Spring Security. Nếu endpoint đã trả document nhưng không có operation, chuyển sang kiểm tra controller scanning và filter. Cách tách các lớp này giúp sửa đúng nguyên nhân mà không phải mở rộng quyền truy cập hoặc thêm dependency không cần thiết.

## Tài liệu tham khảo

- [Springdoc OpenAPI – Getting Started](https://springdoc.org/)
- [Springdoc OpenAPI – FAQ](https://springdoc.org/faq.html)
- [Springdoc OpenAPI – Core Properties](https://springdoc.org/core-properties.html)
- [Springdoc OpenAPI v2 – Getting Started](https://springdoc.org/v2/getting-started.html)
- [Spring Boot – Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html)
- [Spring Security – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
