# Profile riêng để xuất tài liệu mà vẫn khởi động đủ mapping cần thiết

springdoc-openapi tạo OpenAPI document bằng cách quan sát ứng dụng Spring Boot đang chạy: controller, functional route, cấu hình Spring MVC/WebFlux, DTO, validation và annotation. Vì vậy, khi xuất tài liệu trong CI, ứng dụng phải khởi động với các bean đăng ký endpoint mà client sẽ gọi ở môi trường triển khai.

Một profile chuyên để xuất tài liệu rất hữu ích: nó có thể tắt Swagger UI, dùng adapter giả lập cho dịch vụ ngoài và tránh kết nối tới hệ thống production. Nhưng nếu profile này vô tình loại controller, RouterFunction hoặc cấu hình đăng ký handler khỏi ApplicationContext, ứng dụng vẫn có thể khởi động thành công trong khi OpenAPI document thiếu operation hoặc chỉ còn paths rỗng.

Bài này hướng dẫn thiết kế profile xuất tài liệu, giữ mapping cần thiết, cấu hình springdoc và dùng Maven/Gradle plugin để lưu JSON hoặc YAML thành artifact của build.

## 1. Vì sao cần profile riêng để xuất OpenAPI?

Trong một dự án thật, cấu hình chạy production thường có những thành phần không cần thiết cho bước xuất tài liệu:

- Kết nối tới database hoặc message broker production.
- Gọi dịch vụ thanh toán, email, kho hàng hoặc hệ thống bên thứ ba.
- Bật Swagger UI cho người dùng cuối.
- Cấu hình log, tracing hoặc cache theo môi trường triển khai.
- Dùng credential và endpoint chỉ tồn tại trong môi trường thật.

Profile xuất tài liệu cho phép ứng dụng khởi động trong một cấu hình kiểm soát được. Ví dụ:

| Thành phần | Profile production | Profile openapi |
| --- | --- | --- |
| Controller REST | Có | Có |
| RouterFunction/WebFlux route | Có | Có |
| RequestMappingHandlerMapping | Có | Có |
| Springdoc API docs endpoint | Có nếu được bật | Bật để plugin tải tài liệu |
| Swagger UI | Theo chính sách triển khai | Có thể tắt |
| Adapter database | Kết nối database production | Adapter test hoặc dữ liệu rỗng |
| Adapter dịch vụ ngoài | Client thật | Stub/no-op hoặc mock an toàn |
| Secret production | Có qua secret store | Không cần |

Điểm cốt lõi là profile export thay đổi cấu hình và adapter cần thiết cho việc khởi động; nó vẫn phải đăng ký đúng tập endpoint của hợp đồng API.

## 2. Springdoc đọc các mapping đã được đăng ký

Springdoc không tự tạo controller từ tên class hoặc từ mã nguồn đang nằm trên đĩa. Nó đọc các handler đã được Spring đăng ký trong ApplicationContext.

Với Spring MVC, các mapping annotation như @RequestMapping, @GetMapping và @PostMapping được đăng ký qua RequestMappingHandlerMapping. Với WebFlux, ứng dụng cũng có các mapping annotation và có thể đăng ký functional route thông qua RouterFunction bean.

Nếu controller bị loại bởi @Profile, @ConditionalOnProperty, component scan filter hoặc cấu hình import, mapping của controller đó không xuất hiện trong handler registry. springdoc không thể đưa operation đó vào document.

Luồng sinh tài liệu có thể hình dung như sau:

~~~mermaid
flowchart TD
    A[Khởi động Spring Boot với profile openapi] --> B[Đọc cấu hình và profile group]
    B --> C[Đăng ký controller và RouterFunction beans]
    C --> D[Tạo HandlerMapping và route registry]
    D --> E[springdoc đọc mappings, DTO và annotations]
    E --> F[Tạo OpenAPI model]
    F --> G[GET /v3/api-docs hoặc /v3/api-docs.yaml]
    G --> H[Maven/Gradle plugin lưu artifact]
~~~

Ứng dụng khởi động thành công chỉ chứng minh ApplicationContext có thể tạo được. Điều đó chưa chứng minh tất cả operation mong đợi đã được đăng ký.

## 3. Lỗi thường gặp: controller chỉ hoạt động ở profile dev/prod

Giả sử controller được gắn profile:

~~~java
@RestController
@RequestMapping("/api/orders")
@Profile({"dev", "production"})
class OrderController {

    @GetMapping
    List<OrderResponse> listOrders() {
        return List.of();
    }
}
~~~

Khi chạy với profile dev hoặc production, controller được tạo. Nhưng khi chạy:

~~~bash
java -jar app.jar --spring.profiles.active=openapi
~~~

controller không được đăng ký vì profile openapi không khớp với dev hoặc production. Spring Boot vẫn có thể khởi động nếu không có bean khác phụ thuộc controller. Kết quả là endpoint /api/orders biến mất khỏi OpenAPI document.

Không nên gắn profile môi trường lên controller chỉ để thay đổi adapter hoặc cấu hình triển khai. Nếu không có yêu cầu thực sự về việc ẩn toàn bộ API trong môi trường đó, hãy để controller hoạt động trong mọi profile cần cung cấp hợp đồng.

## 4. Tách profile của API mapping khỏi profile hạ tầng

Một cách tổ chức dễ kiểm soát là tách profile theo trách nhiệm:

- api-mappings: bật controller và route của API.
- production-adapters: bật adapter kết nối database/dịch vụ thật.
- export-adapters: bật adapter an toàn dành cho bước xuất tài liệu.
- openapi: profile tổng hợp dùng khi xuất document.

Khai báo profile group trong application.yml không gắn điều kiện profile:

~~~yaml
spring:
  profiles:
    group:
      production:
        - api-mappings
        - production-adapters
      openapi:
        - api-mappings
        - export-adapters
~~~

Khi kích hoạt production, Spring Boot đồng thời kích hoạt api-mappings và production-adapters. Khi kích hoạt openapi, ứng dụng vẫn đăng ký API mapping nhưng dùng export-adapters.

Profile group được hỗ trợ trong các phiên bản Spring Boot hiện đại, từ dòng 2.4 trở lên. Với phiên bản cũ hơn, có thể dùng spring.profiles.include trong application.yml nền để thêm profile cần thiết. Không đặt spring.profiles.active, spring.profiles.include hoặc spring.profiles.group trong file application-openapi.yml hay tài liệu cấu hình chỉ được kích hoạt bởi một profile; các thuộc tính điều khiển profile này phải nằm trong tài liệu không phụ thuộc profile.

Nếu controller không cần profile riêng, hãy bỏ @Profile trên controller. Khi đó group openapi chỉ cần kích hoạt profile adapter phù hợp.

## 5. Đăng ký controller theo profile mapping khi thật sự cần

Nếu dự án chủ động quản lý nhóm mapping bằng profile, controller có thể dùng profile api-mappings:

~~~java
import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/orders")
@Profile("api-mappings")
class OrderController {

    private final OrderQuery orderQuery;

    OrderController(OrderQuery orderQuery) {
        this.orderQuery = orderQuery;
    }

    @GetMapping
    List<OrderResponse> listOrders() {
        return orderQuery.findAll();
    }
}
~~~

Profile group openapi đã bao gồm api-mappings, vì vậy controller vẫn xuất hiện trong ApplicationContext khi plugin khởi động ứng dụng.

Nếu dự án không cần bật/tắt toàn bộ nhóm controller, không thêm @Profile chỉ để phục vụ export. Controller dùng chung sẽ giảm nguy cơ quên kích hoạt profile và giúp hợp đồng được sinh từ cùng tập mapping ở nhiều môi trường.

## 6. Giữ dependency của controller bằng adapter riêng

Một lý do phổ biến khiến nhóm phát triển gắn @Profile lên controller là controller phụ thuộc vào database hoặc dịch vụ ngoài. Khi chạy profile export, các bean hạ tầng production không tồn tại nên constructor injection thất bại.

Hãy tách nghiệp vụ phụ thuộc hạ tầng qua interface/port:

~~~java
import java.util.List;

interface OrderQuery {
    List<OrderResponse> findAll();
}
~~~

Adapter production:

~~~java
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Repository;

@Repository
@Profile("production-adapters")
class JpaOrderQueryAdapter implements OrderQuery {

    private final OrderRepository repository;

    JpaOrderQueryAdapter(OrderRepository repository) {
        this.repository = repository;
    }

    @Override
    public List<OrderResponse> findAll() {
        return repository.findAll().stream()
            .map(OrderResponse::from)
            .toList();
    }
}
~~~

Adapter dùng khi xuất tài liệu:

~~~java
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

import java.util.List;

@Component
@Profile("export-adapters")
class ExportOrderQueryAdapter implements OrderQuery {

    @Override
    public List<OrderResponse> findAll() {
        return List.of();
    }
}
~~~

Controller vẫn được tạo và mapping vẫn được đăng ký. Trong lúc springdoc đọc metadata, nó không cần gọi nghiệp vụ để lấy danh sách đơn hàng. Adapter export tồn tại để ApplicationContext có đủ dependency nếu controller hoặc cấu hình cần chúng trong quá trình khởi động.

Nếu endpoint được gọi trong smoke test, adapter trả dữ liệu rỗng hoặc fixture tổng hợp. Không kết nối production database và không trả dữ liệu người dùng thật vào artifact OpenAPI.

## 7. Không để hai adapter cùng được đăng ký

Với cấu hình profile group ở trên, production-adapters và export-adapters là hai profile tách biệt. Điều này tránh trường hợp có hai bean cùng implement OrderQuery và gây lỗi NoUniqueBeanDefinitionException.

Nếu ứng dụng có nhiều profile cùng lúc, hãy kiểm tra điều kiện trên từng adapter. Có thể dùng @Primary khi có chủ đích chọn một implementation mặc định, nhưng không nên dùng @Primary để che giấu việc hai profile không được thiết kế rõ ràng.

Các lỗi cần kiểm tra:

| Lỗi | Nguyên nhân |
| --- | --- |
| NoSuchBeanDefinitionException | Profile export đã loại adapter cần cho constructor |
| NoUniqueBeanDefinitionException | Adapter production và export cùng hoạt động |
| Controller không xuất hiện | Profile của controller không được kích hoạt |
| Mapping tồn tại nhưng gọi endpoint lỗi | Adapter export không hỗ trợ request smoke test hoặc bean phụ thuộc chưa đủ |
| ApplicationContext khởi động lâu | Profile export vẫn gọi database, broker hoặc remote service thật |

## 8. Cấu hình springdoc riêng cho profile export

Tạo application-openapi.yml:

~~~yaml
spring:
  main:
    banner-mode: off

server:
  port: 9090

springdoc:
  api-docs:
    enabled: true
    path: /v3/api-docs
  swagger-ui:
    enabled: false
~~~

Trong profile này:

- API docs endpoint vẫn bật để build plugin tải JSON.
- Swagger UI tắt vì CI chỉ cần OpenAPI document.
- Port riêng giảm nguy cơ xung đột với ứng dụng local đang chạy.
- Có thể thêm cấu hình adapter export, timeout hoặc endpoint mock.

Hai thuộc tính springdoc có ý nghĩa riêng:

| Thuộc tính | Tác dụng |
| --- | --- |
| springdoc.api-docs.enabled | Bật/tắt endpoint OpenAPI JSON/YAML |
| springdoc.swagger-ui.enabled | Bật/tắt giao diện Swagger UI |

Nếu đặt springdoc.api-docs.enabled=false trong profile export, plugin sẽ nhận 404 khi gọi /v3/api-docs. Tắt Swagger UI không làm mất API docs endpoint.

Nếu chỉ cần API docs, có thể dùng starter API tương ứng với web stack như springdoc-openapi-starter-webmvc-api hoặc springdoc-openapi-starter-webflux-api. Nếu dự án đã dùng starter UI, chỉ cần tắt Swagger UI trong profile export.

## 9. Kích hoạt profile từ lệnh chạy

Không cần ghi profile openapi làm profile mặc định của ứng dụng. Hãy kích hoạt riêng ở bước export:

~~~bash
java -jar target/application.jar --spring.profiles.active=openapi
~~~

Hoặc dùng biến môi trường:

~~~bash
SPRING_PROFILES_ACTIVE=openapi java -jar target/application.jar
~~~

Trong CI, profile này chỉ áp dụng cho tiến trình được plugin khởi động. Khi ứng dụng production chạy bình thường, nó vẫn dùng profile do môi trường triển khai quy định.

Không đặt spring.profiles.active=openapi bên trong application-openapi.yml. Spring Boot chỉ cho phép thuộc tính active/default/include/group ở tài liệu cấu hình không phụ thuộc profile; file application-openapi.yml là file đã được kích hoạt bởi profile nên không phải nơi để tự kích hoạt chính profile đó.

## 10. Kiểm tra mapping trước khi xuất file

Trước khi cấu hình plugin, nên xác nhận profile openapi tạo ra đúng mapping. Với Spring MVC, có thể dùng MockMvc:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("openapi")
class OpenApiExportProfileTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void exportsExpectedOrderOperation() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.paths['/api/orders'].get").exists());
    }
}
~~~

Ví dụ này giả định API có operation GET /api/orders và OpenAPI endpoint dùng path mặc định. Nếu dự án đổi springdoc.api-docs.path, cập nhật URL trong test. Nếu dự án dùng Spring WebFlux, dùng WebTestClient để gọi endpoint tài liệu và kiểm tra path tương tự.

Test này xác nhận tài liệu được sinh và operation mong đợi xuất hiện. Nên bổ sung assertion cho các operation quan trọng, security scheme và response schema mà client phụ thuộc.

## 11. Kiểm tra functional routes và bộ lọc springdoc

Với WebFlux functional endpoint, bean RouterFunction cũng phải được đăng ký trong profile export. Nếu RouterFunction được tạo trong một @Configuration có @Profile("production"), profile openapi không có route đó.

Ngoài profile, các thuộc tính lọc của springdoc cũng có thể làm document thiếu operation:

~~~yaml
springdoc:
  packages-to-scan:
    - com.example.api
  paths-to-match:
    - /api/**
  paths-to-exclude:
    - /internal/**
~~~

Hãy kiểm tra package và path filter trong application.yml, application-openapi.yml và các group config. Nếu filter chỉ khớp một phần route, document có thể hợp lệ về JSON nhưng không chứa toàn bộ API cần export.

Phân biệt hai nguyên nhân:

1. Mapping không tồn tại trong Spring: kiểm tra profile, component scan, điều kiện bean và RouterFunction.
2. Mapping tồn tại nhưng không được đưa vào OpenAPI: kiểm tra packages-to-scan, paths-to-match, paths-to-exclude, @Hidden và group config.

## 12. Xuất JSON và YAML bằng HTTP endpoint

Khi ứng dụng đã chạy với profile openapi, springdoc mặc định cung cấp:

~~~text
JSON: http://localhost:9090/v3/api-docs
YAML: http://localhost:9090/v3/api-docs.yaml
~~~

Có thể tải thủ công:

~~~bash
curl --fail --silent --show-error http://localhost:9090/v3/api-docs --output openapi.json

curl --fail --silent --show-error http://localhost:9090/v3/api-docs.yaml --output openapi.yaml
~~~

Nếu đã đổi springdoc.api-docs.path, dùng URL mới tương ứng. Chỉ lưu file sau khi response thành công; curl với --fail giúp lệnh trả mã lỗi khi server trả HTTP 4xx/5xx.

## 13. Xuất tự động bằng springdoc Gradle plugin

Gradle plugin khởi động Spring Boot application, gọi endpoint OpenAPI và lưu kết quả vào file. Plugin cần Spring Boot plugin cùng springdoc runtime dependency; nó chỉ gọi HTTP endpoint nên không phụ thuộc trực tiếp vào phiên bản springdoc library. Hãy chọn phiên bản plugin tương thích với Gradle và build hiện tại.

Ví dụ Kotlin DSL cho Spring Boot 3:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.16"
    id("org.springdoc.openapi-gradle-plugin") version "2.0.0"
}

openApi {
    apiDocsUrl.set("http://localhost:9090/v3/api-docs")
    outputDir.set(layout.buildDirectory.dir("openapi"))
    outputFileName.set("openapi.json")
    waitTimeInSeconds.set(60)

    customBootRun {
        args.set(
            listOf(
                "--spring.profiles.active=openapi",
                "--server.port=9090"
            )
        )
    }
}
~~~

Chạy:

~~~bash
./gradlew generateOpenApiDocs
~~~

Kết quả mặc định theo cấu hình ví dụ:

~~~text
build/openapi/openapi.json
~~~

customBootRun cho phép khởi động ứng dụng với profile khác với bootRun thông thường. Các thiết lập không được ghi đè tiếp tục lấy từ bootRun, vì vậy cần kiểm tra các JVM argument, environment variable và main class mà build đang sử dụng.

Để xuất YAML, đổi URL kết thúc bằng .yaml và đổi tên file:

~~~kotlin
openApi {
    apiDocsUrl.set("http://localhost:9090/v3/api-docs.yaml")
    outputDir.set(layout.buildDirectory.dir("openapi"))
    outputFileName.set("openapi.yaml")
    customBootRun {
        args.set(
            listOf(
                "--spring.profiles.active=openapi",
                "--server.port=9090"
            )
        )
    }
}
~~~

Plugin cũng hỗ trợ requestHeaders để gửi header khi endpoint tài liệu yêu cầu xác thực, và groupedApiMappings để tải nhiều group thành nhiều file. Không ghi access token hoặc secret trực tiếp vào build.gradle.kts; lấy credential từ secret store của CI.

## 14. Xuất tự động bằng springdoc Maven plugin

Maven plugin hoạt động cùng spring-boot-maven-plugin. Spring Boot plugin khởi động ứng dụng trước integration test và dừng sau khi hoàn tất; springdoc plugin gọi API docs endpoint rồi ghi file.

Ví dụ cấu hình trong pom.xml:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-maven-plugin</artifactId>
      <configuration>
        <jvmArguments>-Dspring.application.admin.enabled=true</jvmArguments>
        <arguments>
          <argument>--spring.profiles.active=openapi</argument>
          <argument>--server.port=9090</argument>
        </arguments>
      </configuration>
      <executions>
        <execution>
          <id>pre-integration-test</id>
          <goals>
            <goal>start</goal>
          </goals>
        </execution>
        <execution>
          <id>post-integration-test</id>
          <goals>
            <goal>stop</goal>
          </goals>
        </execution>
      </executions>
    </plugin>

    <plugin>
      <groupId>org.springdoc</groupId>
      <artifactId>springdoc-openapi-maven-plugin</artifactId>
      <version>1.6</version>
      <executions>
        <execution>
          <id>generate-openapi</id>
          <goals>
            <goal>generate</goal>
          </goals>
        </execution>
      </executions>
      <configuration>
        <apiDocsUrl>http://localhost:9090/v3/api-docs</apiDocsUrl>
        <outputFileName>openapi.json</outputFileName>
        <outputDir>${project.build.directory}/openapi</outputDir>
        <failOnError>true</failOnError>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

Chạy:

~~~bash
./mvnw verify
~~~

File được ghi vào target/openapi/openapi.json. Thuộc tính failOnError nên bật trong CI; nếu không, một số lỗi tải hoặc ghi tài liệu chỉ được ghi log và build có thể tiếp tục dù artifact không được tạo.

Để xuất YAML, đổi apiDocsUrl thành /v3/api-docs.yaml và outputFileName thành openapi.yaml:

~~~xml
<apiDocsUrl>http://localhost:9090/v3/api-docs.yaml</apiDocsUrl>
<outputFileName>openapi.yaml</outputFileName>
~~~

Maven plugin cũng hỗ trợ headers để gọi endpoint cần xác thực và attachArtifact để đính kèm file vào artifact Maven. Credential phải được lấy từ biến môi trường hoặc secret store, không commit vào POM.

Nếu build thất bại giữa các phase, kiểm tra tiến trình Spring Boot đã được dừng chưa. Tài liệu plugin lưu ý rằng khi build thất bại, goal stop có thể không được thực thi; ứng dụng cũ còn chạy có thể trả tài liệu cũ cho lần build tiếp theo.

## 15. Profile export không được vô tình dùng cấu hình production

Profile openapi nên tạo ra môi trường có thể khởi động và phản ánh đúng hợp đồng, nhưng không nên kéo theo secret hoặc side effect của production.

Một số lựa chọn an toàn:

- Adapter repository trả collection rỗng hoặc fixture tổng hợp.
- Mock server cho remote API nếu ApplicationContext cần endpoint đó khi khởi động.
- Dùng database in-memory nếu startup bắt buộc cần schema hoặc metadata từ database.
- Tắt scheduler, consumer và background job không cần thiết khi export.
- Không gửi email, thanh toán hoặc ghi dữ liệu thật trong bước khởi động.
- Cấu hình timeout và port cố định để plugin có thể chờ endpoint sẵn sàng.

Không tắt toàn bộ Spring Security chỉ để plugin gọi được /v3/api-docs. Nếu docs endpoint được bảo vệ, cấu hình quyền phù hợp cho profile export hoặc truyền header từ secret store của CI. Không để profile export vô tình trở thành cấu hình public trong production.

## 16. Xác thực endpoint tài liệu trong CI

Sau khi plugin tạo file, pipeline nên kiểm tra artifact:

~~~bash
test -s build/openapi/openapi.json
jq -e '.openapi and .paths and (.paths | length > 0)' build/openapi/openapi.json
~~~

Với Maven:

~~~bash
test -s target/openapi/openapi.json
jq -e '.openapi and .paths and (.paths | length > 0)' target/openapi/openapi.json
~~~

Các assertion này chỉ là bước kiểm tra tối thiểu: file không rỗng, JSON parse được, có trường phiên bản OpenAPI và có ít nhất một path. Hãy kiểm tra thêm operation quan trọng để phát hiện profile đã làm mất mapping.

Ví dụ:

~~~bash
jq -e '.paths["/api/orders"].get' build/openapi/openapi.json
jq -e '.components.schemas.OrderResponse' build/openapi/openapi.json
~~~

Nếu API có nhiều group, kiểm tra từng file được sinh từ groupedApiMappings hoặc từng URL group của Maven plugin.

## 17. Phân biệt lỗi khởi động với lỗi thiếu mapping

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Ứng dụng không khởi động | Thiếu bean dependency trong profile openapi | Tạo adapter export hoặc kích hoạt profile bean cần thiết |
| Ứng dụng chạy nhưng paths rỗng | Controller/RouterFunction không được đăng ký | Kiểm tra @Profile, @ConditionalOnProperty và component scan |
| Chỉ thiếu một số controller | Controller thuộc profile khác hoặc nằm ngoài package scan | Kiểm tra profile group và packages-to-scan |
| Functional endpoint không xuất hiện | RouterFunction bean không được tạo | Kiểm tra profile của @Configuration và bean method |
| Endpoint có trong runtime nhưng không có trong docs | paths-to-match, paths-to-exclude hoặc @Hidden | Kiểm tra bộ lọc springdoc và group config |
| Plugin nhận 404 | API docs endpoint bị tắt hoặc sai path/port | Kiểm tra springdoc.api-docs.enabled, api-docs.path và URL plugin |
| Plugin nhận 401/403 | Security chặn API docs endpoint | Cấp quyền cho CI hoặc truyền header hợp lệ |
| File cũ vẫn xuất hiện | Plugin không ghi đè do task up-to-date hoặc app cũ vẫn chạy | Kiểm tra input task, clean output và dừng tiến trình cũ |
| Plugin timeout | Ứng dụng khởi động chậm hoặc chờ external service | Tăng wait/timeout có kiểm soát và dùng adapter export |
| Document khác production | Profile export thay đổi package/path filter hoặc adapter metadata | So sánh profile group, springdoc filters và OpenAPI customizer |

Đừng chỉ kiểm tra HTTP 200 của /v3/api-docs. Một document hợp lệ nhưng thiếu operation vẫn có thể khiến CI xanh nếu pipeline không có assertion về paths bắt buộc.

## 18. Kiểm tra mapping trong Spring MVC và WebFlux

Với Spring MVC, kiểm tra các mapping đã đăng ký qua RequestMappingHandlerMapping hoặc kiểm tra OpenAPI JSON được sinh ra. Với WebFlux functional endpoint, cần xác nhận RouterFunction bean được khởi tạo trong profile export.

Một cách kiểm tra trực tiếp trên document là so sánh danh sách path bắt buộc:

~~~json
{
  "requiredPaths": [
    "/api/orders",
    "/api/customers",
    "/api/payments"
  ]
}
~~~

Đây là danh sách kỳ vọng của pipeline, không phải phần của OpenAPI document. CI có thể dùng script hoặc contract test để xác nhận mỗi path tồn tại trong OpenAPI file.

Nếu controller có nhiều HTTP method, kiểm tra method cụ thể. Một path chỉ xuất hiện với GET không có nghĩa POST/PUT/DELETE cũng đã được đăng ký.

## 19. Giữ hợp đồng nhất quán giữa profile export và runtime

Profile export có thể dùng adapter khác, nhưng các thành phần ảnh hưởng tới hợp đồng cần nhất quán:

- Controller và RouterFunction.
- DTO và Jackson serialization configuration.
- Validation constraints.
- Security scheme, scope và response metadata.
- Controller advice và error response.
- springdoc packages/paths/group configuration.
- OpenAPI customizer và operation customizer.

Nếu profile export bỏ một ControllerAdvice hoặc Jackson module, schema/response có thể khác runtime. Nếu profile export dùng một OpenAPI customizer khác, file export có thể không phản ánh tài liệu mà production phục vụ.

Hãy tách customizer mô tả contract khỏi bean chỉ phục vụ UI. Khi cần cấu hình khác theo profile, chỉ thay những giá trị môi trường như public server URL, không đổi cấu trúc schema hoặc operation ngoài chủ đích.

## 20. Quy trình CI khuyến nghị

1. Chọn phiên bản Spring Boot, springdoc và build plugin tương thích.
2. Định nghĩa profile group openapi trong cấu hình nền nếu cần kích hoạt thêm mapping profile.
3. Giữ controller và RouterFunction được đăng ký trong profile export.
4. Dùng adapter an toàn cho database, broker và dịch vụ ngoài.
5. Bật springdoc.api-docs.enabled và có thể tắt springdoc.swagger-ui.enabled.
6. Khởi động ứng dụng với --spring.profiles.active=openapi.
7. Chờ ứng dụng sẵn sàng rồi gọi JSON hoặc YAML endpoint.
8. Lưu file vào target/build directory như artifact của build.
9. Kiểm tra file không rỗng, parse được và chứa paths/operations quan trọng.
10. Chạy contract diff và review thay đổi trước khi publish hoặc sinh client.
11. Dừng tiến trình ứng dụng sau khi export, kể cả khi pipeline có lỗi.

Profile export tốt giúp tạo tài liệu lặp lại được trong CI, đồng thời giữ đúng mapping và schema của API. Khi controller/route được giữ trong ApplicationContext và chỉ adapter hạ tầng được thay thế, OpenAPI document phản ánh hợp đồng thực tế mà không cần kết nối production hoặc bật Swagger UI trong bước build.

## Tài liệu tham khảo

- [Spring Boot 4.2 – Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html)
- [Spring Boot 3.5 – Profiles](https://docs.spring.io/spring-boot/3.5/reference/features/profiles.html)
- [springdoc-openapi v2 – Maven and Gradle plugins](https://springdoc.org/v2/)
- [springdoc-openapi – Configuration Properties](https://springdoc.org/properties.html)
- [springdoc-openapi Maven plugin – README and CI options](https://github.com/springdoc/springdoc-openapi-maven-plugin)
- [springdoc-openapi Gradle plugin – README and customBootRun](https://github.com/springdoc/springdoc-openapi-gradle-plugin)
- [Spring Framework – @Profile](https://docs.spring.io/spring-framework/reference/core/beans/environment.html#beans-definition-profiles)
