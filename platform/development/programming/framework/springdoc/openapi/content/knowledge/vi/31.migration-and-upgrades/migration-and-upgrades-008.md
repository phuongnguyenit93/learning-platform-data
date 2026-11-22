# Đối chiếu thuộc tính cấu hình và giá trị mặc định sau nâng cấp

Sau khi nâng Spring Boot hoặc springdoc-openapi, ứng dụng có thể vẫn khởi động và Swagger UI vẫn mở được nhưng OpenAPI document đã thay đổi. Nguyên nhân không chỉ đến từ property trong application.yml. Giá trị mặc định của thư viện, phiên bản Swagger UI được đóng gói, cấu hình theo profile, biến môi trường và thay đổi cách Springdoc suy luận schema đều có thể làm đầu ra khác trước.

Vì vậy, khi nâng cấp cần đối chiếu ba lớp:

1. **Property được khai báo** trong application.yml, application.properties, profile, biến môi trường hoặc command line.
2. **Giá trị hiệu lực** sau khi Spring Boot bind configuration và áp dụng default của phiên bản thư viện mới.
3. **Hành vi đầu ra** trong OpenAPI JSON/YAML, swagger-config và giao diện Swagger UI.

Không nên kết luận cấu hình đã tương thích chỉ vì các key trong application.yml vẫn còn nguyên. Một property không được khai báo có thể nhận default khác sau nâng cấp; một default không đổi vẫn có thể tạo output khác khi Springdoc, swagger-core hoặc Swagger UI thay đổi cách xử lý.

## 1. Phân biệt các phiên bản trước khi so sánh cấu hình

Có nhiều loại version cùng xuất hiện trong một ứng dụng:

| Loại version | Ví dụ | Ý nghĩa |
|---|---|---|
| Spring Boot | 3.5.x hoặc 4.1.x | Nền tảng runtime và hệ sinh thái Spring. |
| springdoc-openapi | 2.10.x hoặc 3.2.x | Thư viện đọc Spring application và sinh tài liệu. |
| OpenAPI Specification | 3.0.x hoặc 3.1.x | Phiên bản ngôn ngữ được ghi trong trường openapi. |
| API release version | info.version: 2.4.0 | Phiên bản API do sản phẩm quản lý. |
| Spring Framework API versioning | Header hoặc query parameter như X-API-Version | Cơ chế chọn phiên bản operation khi ứng dụng triển khai API versioning. |

Các version này độc lập. Đổi springdoc 2.x lên 3.x không tự đổi info.version của API. Đổi OpenAPI 3.0 sang 3.1 không đồng nghĩa đổi URL version của REST API. Property springdoc.api-docs.version điều khiển phiên bản đặc tả, không điều khiển phiên bản nghiệp vụ của API.

## 2. Chọn springdoc theo major version của Spring Boot

Chọn đúng nhánh tương thích trước khi xem xét property:

| Spring Boot | Nhánh springdoc | Ghi chú |
|---|---|---|
| 4.x | 3.x | Dành cho Spring Boot 4 và Spring Framework 7. |
| 3.5.x | 2.8.x–2.10.x | Dùng nhánh springdoc 2.x. |
| 3.4.x | 2.7.x–2.8.x | Dùng nhánh springdoc 2.x. |
| 3.3.x | 2.6.x | Dùng nhánh springdoc 2.x. |
| 3.2.x | 2.3.x–2.5.x | Dùng nhánh springdoc 2.x. |
| 3.1.x | 2.2.x | Dùng nhánh springdoc 2.x. |
| 3.0.x | 2.0.x–2.1.x | Dùng nhánh springdoc 2.x. |
| 2.x và 1.x | 1.8.0 là bản open-source cuối cho các nhánh legacy | Kiểm tra chính sách hỗ trợ mở rộng nếu vẫn phải duy trì. |

Compatibility matrix thay đổi theo release. Khi nâng cấp, kiểm tra matrix chính thức tại thời điểm chọn version; không chọn springdoc mới nhất chỉ vì version đó mới hơn.

## 3. Những thay đổi quan trọng từ springdoc v1 sang v2

Springdoc v2 được xây dựng cho Spring Boot 3, sử dụng Spring Framework 6 và hệ sinh thái Jakarta. Ngoài việc đổi dependency, migration còn có thể cần đổi package import và annotation.

### 3.1. Dependency artifact được đổi tên

| springdoc v1 | springdoc v2 và v3 |
|---|---|
| springdoc-openapi-ui | springdoc-openapi-starter-webmvc-ui |
| springdoc-openapi-webflux-ui | springdoc-openapi-starter-webflux-ui |
| springdoc-openapi-webmvc-core | springdoc-openapi-starter-webmvc-api |
| springdoc-openapi-webflux-core | springdoc-openapi-starter-webflux-api |
| springdoc-openapi-common | springdoc-openapi-starter-common |

Các module bổ sung như Data REST, Security, HATEOAS, Kotlin và Javadoc được tích hợp qua starter-common trong v2. Rà soát dependency cũ để tránh giữ các artifact đã được thay thế.

Ví dụ Spring MVC chỉ cần OpenAPI document và Swagger UI:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>2.10.0</version>
</dependency>
~~~

Với Spring WebFlux, chọn starter-webflux-ui. Nếu chỉ cần JSON/YAML và không cần giao diện, chọn starter-webmvc-api hoặc starter-webflux-api tương ứng.

### 3.2. Một số package và class được chuyển

| v1 | v2 |
|---|---|
| org.springdoc.core.SpringDocUtils | org.springdoc.core.utils.SpringDocUtils |
| org.springdoc.api.annotations.ParameterObject | org.springdoc.core.annotations.ParameterObject |
| org.springdoc.core.GroupedOpenApi | org.springdoc.core.models.GroupedOpenApi |
| org.springdoc.core.customizers.OpenApiCustomiser | org.springdoc.core.customizers.OpenApiCustomizer |
| org.springdoc.core.Constants | org.springdoc.core.utils.Constants |
| org.springdoc.core.SwaggerUiConfigParameters | org.springdoc.core.properties.SwaggerUiConfigParameters |

Tên OpenApiCustomiser được chuẩn hóa sang OpenApiCustomizer. Sửa import và code customizer theo API của version mới thay vì chỉ đổi dependency rồi giữ import cũ.

### 3.3. Chuyển từ javax sang jakarta

Spring Boot 3 chuyển nhiều API Java EE từ namespace javax sang jakarta. Nếu controller hoặc DTO dùng Bean Validation, Servlet API hoặc annotation liên quan, kiểm tra dependency và import:

- javax.validation.Valid → jakarta.validation.Valid
- javax.validation.constraints.NotNull → jakarta.validation.constraints.NotNull
- javax.servlet.* → jakarta.servlet.*

Nếu annotation validation vẫn thuộc namespace cũ, Spring Boot 3 có thể không áp dụng validation như mong đợi; schema Springdoc suy luận từ các annotation đó cũng có thể thiếu constraint.

## 4. Một default quan trọng thay đổi từ v1 sang v2

Property springdoc.api-docs.version có default khác giữa v1 và v2:

| Nhánh | Default | Ý nghĩa |
|---|---|---|
| springdoc v1 | openapi_3_0 | Tài liệu sinh theo OpenAPI 3.0. |
| springdoc v2 | openapi_3_1 | Tài liệu sinh theo OpenAPI 3.1. |
| springdoc v3 | openapi_3_1 | Tiếp tục dùng OpenAPI 3.1 theo property reference hiện hành. |

Đây là thay đổi có thể ảnh hưởng trực tiếp tới client generator, API gateway và validator. OpenAPI 3.1 dùng Schema Object gần với JSON Schema Draft 2020-12; nullable, type union, exclusiveMinimum và các keyword schema có thể được biểu diễn khác 3.0.

Nếu đang nâng từ v1 và cần giữ hợp đồng 3.0 cho hệ thống downstream, khai báo rõ:

~~~yaml
springdoc:
  api-docs:
    version: OPENAPI_3_0
~~~

Nếu toàn bộ consumer đã hỗ trợ 3.1, khai báo rõ OPENAPI_3_1 để thể hiện chủ đích. Không phụ thuộc default cho một quyết định ảnh hưởng tới contract.

Việc pin OPENAPI_3_0 chỉ giữ dialect của đặc tả. Nó không đảm bảo schema output giống hệt v1 vì cách xử lý annotation, Jackson, swagger-core và model converters vẫn có thể thay đổi; vẫn phải semantic diff document sau nâng cấp.

## 5. Các default phổ biến cần đối chiếu

Bảng dưới đây tổng hợp các default thường dùng trong property reference v1 và nhánh hiện hành. Những default không đổi vẫn nên được kiểm tra vì profile hoặc biến môi trường có thể ghi đè.

### 5.1. Core properties

| Property | Default thường gặp | Lưu ý khi nâng cấp |
|---|---|---|
| springdoc.api-docs.path | /v3/api-docs | Giữ nguyên giữa các nhánh phổ biến. |
| springdoc.api-docs.enabled | true | Tắt property này sẽ tắt endpoint tài liệu. |
| springdoc.packages-to-scan | * | Thay đổi package scan có thể làm mất operation. |
| springdoc.paths-to-match | /* | Path filter quyết định operation nào được đưa vào document. |
| springdoc.writer-with-default-pretty-printer | false | Chỉ ảnh hưởng format JSON, không đổi semantics. |
| springdoc.writer-with-order-by-keys | false | Bật sẽ giúp output có thứ tự key ổn định hơn. |
| springdoc.override-with-generic-response | true | Có thể thêm response chung từ @ControllerAdvice. |
| springdoc.api-docs.version | v1: openapi_3_0; v2/v3: openapi_3_1 | Default thay đổi ở v2; cần pin nếu downstream cần 3.0. |
| springdoc.cache.disabled | false | Mặc định bật cache OpenAPI document. |
| springdoc.cache.max-entries | 100 ở các nhánh có bounded cache | Được bổ sung từ v2.9.1; kiểm tra nếu dùng nhiều locale hoặc nhiều tài liệu. |

### 5.2. Swagger UI properties

| Property | springdoc v1 | springdoc v2 | springdoc v3 | Tác động |
|---|---|---|---|---|
| springdoc.swagger-ui.path | /swagger-ui.html | /swagger-ui.html | /swagger-ui.html | URL trang HTML. |
| springdoc.swagger-ui.enabled | true | true | true | Bật/tắt UI, độc lập với API docs. |
| springdoc.swagger-ui.configUrl | /v3/api-docs/swagger-config | /v3/api-docs/swagger-config | /v3/api-docs/swagger-config | URL JSON cấu hình UI. |
| springdoc.swagger-ui.tryItOutEnabled | true | false | false | Default thay đổi ở v2; UI không tự mở Try it out sau khi tải trang. |
| springdoc.swagger-ui.filter | false | false | false | Không hiển thị bộ lọc mặc định. |
| springdoc.swagger-ui.displayOperationId | false | false | false | Không hiển thị operationId mặc định. |
| springdoc.swagger-ui.displayRequestDuration | false | false | false | Không hiển thị thời gian request mặc định. |
| springdoc.swagger-ui.docExpansion | Swagger UI: list | Swagger UI: list | Swagger UI: list | Default nội bộ của Swagger UI; có thể pin bằng doc-expansion. |
| springdoc.swagger-ui.operationsSorter | Server order | Server order | Server order | Không sắp xếp lại operation nếu không cấu hình. |
| springdoc.swagger-ui.tagsSorter | Document order | Document order | Document order | Giữ thứ tự tag theo OpenAPI document. |
| springdoc.swagger-ui.supportedSubmitMethods | All methods | All methods | All methods | Các method có thể dùng với Try it out; mảng rỗng sẽ tắt toàn bộ. |
| springdoc.swagger-ui.defaultModelsExpandDepth | 1 | 1 | 1 | Độ sâu mở rộng danh sách model. |
| springdoc.swagger-ui.defaultModelExpandDepth | 1 | 1 | 1 | Độ sâu mở rộng model. |
| springdoc.swagger-ui.persistAuthorization | false | false | false | Không giữ authorization data mặc định. |
| springdoc.swagger-ui.queryConfigEnabled | false | false | false | Query string không được phép ghi đè UI config theo mặc định; disabled since v1.6.0. |

Swagger UI có một số default nội bộ, ví dụ doc expansion và cách sắp xếp operation/tag. Những giá trị này còn phụ thuộc phiên bản Swagger UI được đóng gói trong starter. Nếu giao diện phải giữ ổn định giữa các lần nâng, đặt rõ các property quan trọng như doc-expansion, operations-sorter và tags-sorter thay vì dựa vào default của thư viện UI.

Nếu muốn giữ hành vi Try it out của springdoc v1 sau khi nâng lên v2/v3, khai báo tường minh:

~~~yaml
springdoc:
  swagger-ui:
    try-it-out-enabled: true
~~~

Default supportedSubmitMethods vẫn cho phép các HTTP methods được Swagger UI hỗ trợ; thay đổi tryItOutEnabled chỉ ảnh hưởng trạng thái bật mặc định của khu vực thử request.

## 6. Các property mới xuất hiện ở những nhánh mới hơn

Không phải property mới nào cũng thay đổi default cũ. Một số chỉ bổ sung khả năng opt-in:

| Property | Default trong tài liệu hiện hành | Tác động |
|---|---|---|
| springdoc.cache.max-entries | 100 | Giới hạn số OpenAPI document được giữ trong cache; có từ v2.9.1. |
| springdoc.model-converters.polymorphic-converter.one-of-as-ref | false | Khi bật, schema polymorphic có thể được biểu diễn bằng component reference. |
| springdoc.model-converters.polymorphic-converter.one-of-ref-suffix | Variant | Hậu tố cho tên component được tạo từ polymorphic schema. |
| springdoc.model-converters.java-nullable-property-customizer.enabled | false | Cho phép JSpecify, Spring hoặc JSR-305 @Nullable làm property Java nullable trong schema. |
| springdoc.model-converters.kotlin-nullable-property-customizer.enabled | true | Giữ hỗ trợ nullable cho Kotlin property. |

Những property này xuất hiện trong các nhánh mới hơn như v2.9.1/v2.10.0 và tài liệu v3 hiện hành. Kiểm tra release notes của patch version cụ thể trước khi thêm chúng vào cấu hình dùng chung.

## 7. Thay đổi đầu ra có thể xảy ra dù property không đổi

Một số thay đổi ở v3.2.0 ảnh hưởng schema và OpenAPI output, không phải chỉ là đổi tên property:

- **Spring Framework API versioning**: default API version chỉ xuất hiện trong version header/query parameter của operation thực sự phục vụ version đó hoặc handler không khai báo version. Operation chỉ phục vụ version khác không còn liệt kê version mặc định đó là allowed/default.
- **PagedModel và PageMetadata**: các property được đánh dấu required vì chúng luôn được serialize.
- **MonetaryAmount**: amount và currency được đánh dấu required vì chúng luôn có trong output.
- **Java @Nullable**: customizer mới có thể đánh dấu property nullable mà không thay đổi shared component schema; cần kiểm tra property opt-in tương ứng.

Các thay đổi này có thể làm client SDK sinh ra model với field non-nullable hoặc thay đổi parameter version được công bố. Nếu ứng dụng dùng Spring Data Page, MonetaryAmount, Kotlin nullable hoặc Spring API versioning, cần kiểm tra schema sau nâng cấp.

### 7.1. Phân biệt default OpenAPI version và default API version

Hai khái niệm có tên gần giống nhau nhưng khác nghĩa:

- springdoc.api-docs.version chọn OpenAPI 3.0 hay 3.1.
- Default API version trong Spring Framework API versioning chọn version request nếu handler không chỉ định version riêng.

Thay đổi default API version ở v3.2.0 không có nghĩa springdoc đổi OpenAPI Specification version. Khi đọc release notes, xác định property hoặc behavior đang nói về loại version nào.

## 8. Xác định giá trị thực tế đang được áp dụng

Đọc application.yml chỉ cho biết một nguồn cấu hình. Giá trị hiệu lực có thể bị ghi đè bởi:

- application-{profile}.yml.
- Environment variables.
- Java system properties.
- Command-line arguments.
- Config import hoặc config server.
- Giá trị mặc định trong class được bind bằng @ConfigurationProperties.

Ví dụ cùng một ứng dụng có thể đang chạy với các biến môi trường sau dù application.yml không khai báo hai property này:

~~~bash
SPRINGDOC_API_DOCS_VERSION=OPENAPI_3_0
SPRINGDOC_SWAGGER_UI_TRYITOUTENABLED=true
~~~

Với biến môi trường, Spring Boot chuyển dấu chấm thành dấu gạch dưới, loại bỏ dấu gạch ngang và viết hoa tên property. Command-line argument như --springdoc.api-docs.version=OPENAPI_3_0 cũng có thể ghi đè giá trị trong file cấu hình. Khi so sánh trước/sau nâng cấp, lưu lại profile và các nguồn override để hai lần chạy dùng cùng điều kiện.

### 8.1. Dùng Actuator configprops và env

Trong môi trường kiểm thử hoặc quản trị đã bảo vệ, có thể expose endpoint cần thiết:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
          - env
          - configprops
~~~

Hai endpoint có mục tiêu khác nhau:

| Endpoint | Dùng để |
|---|---|
| /actuator/configprops | Xem các bean @ConfigurationProperties và giá trị đã bind. |
| /actuator/env/springdoc.api-docs.version | Xem property source và origin của một property cụ thể. |

Ví dụ:

~~~bash
curl -fsS http://localhost:8080/actuator/configprops
curl -fsS http://localhost:8080/actuator/env/springdoc.api-docs.version
~~~

Các endpoint Actuator có thể chứa thông tin nhạy cảm. Chỉ expose trong môi trường cần chẩn đoán, bảo vệ bằng Spring Security/network policy và dùng cơ chế sanitization phù hợp. Không mở env/configprops công khai trên production.

### 8.2. Kiểm tra metadata của dependency

Spring Boot configuration metadata trong META-INF/spring-configuration-metadata.json có thể liệt kê property name, type, description và defaultValue nếu thư viện phát hành metadata đó.

Khi nâng springdoc:

1. So sánh metadata từ artifact cũ và mới.
2. Tìm property đã đổi tên, bị deprecated hoặc không còn tồn tại.
3. Kiểm tra defaultValue trong metadata.
4. Đối chiếu với tài liệu đúng nhánh version.
5. Xác minh giá trị hiệu lực bằng configprops/env và output thực tế.

Metadata không thay thế runtime test. Một property có thể được bind thành công nhưng hành vi tạo document vẫn thay đổi do code xử lý hoặc dependency phía dưới.

## 9. Quy trình đối chiếu trước và sau nâng cấp

Thực hiện trong cùng profile, cùng dữ liệu mẫu và cùng cấu hình deployment để kết quả có thể so sánh.

1. **Ghi baseline dependency**: lưu Spring Boot, Spring Framework, springdoc, swagger-core và Swagger UI versions.
2. **Ghi baseline configuration**: lưu application.yml, profile, environment variables và command-line properties có liên quan.
3. **Lưu OpenAPI artifact cũ**: tải JSON/YAML từ release trước.
4. **Lưu Swagger UI config cũ**: tải swagger-config để ghi nhận url, urls, OAuth và UI options.
5. **Nâng đúng compatibility line**: chọn springdoc 2.x cho Boot 3 hoặc 3.x cho Boot 4.
6. **Cập nhật dependency/import**: đổi starter artifact, package và javax/jakarta nếu migration yêu cầu.
7. **So sánh property defaults**: chú ý api-docs.version, cache, model converters và UI defaults.
8. **Kiểm tra giá trị hiệu lực**: dùng Actuator hoặc kiểm tra configuration beans trong test.
9. **Tải OpenAPI artifact mới**: dùng cùng profile và dữ liệu với baseline.
10. **Semantic diff**: so sánh paths, operation, parameters, request/response schema, required, nullable, security và servers.
11. **Kiểm tra Swagger UI**: so sánh swagger-config, URL tải document, layout và Try it out.
12. **Chạy contract/integration tests**: xác minh runtime vẫn khớp hợp đồng đã duyệt.

## 10. Pin các default quan trọng trong application.yml

Nếu API consumer chưa sẵn sàng nhận OpenAPI 3.1, có thể giữ 3.0 rõ ràng:

~~~yaml
springdoc:
  api-docs:
    enabled: true
    path: /v3/api-docs
    version: OPENAPI_3_0
  swagger-ui:
    enabled: true
    path: /swagger-ui.html
    try-it-out-enabled: false
    persist-authorization: false
~~~

Nếu đã chuyển toàn bộ downstream sang OpenAPI 3.1, đổi version thành OPENAPI_3_1. Không cần pin mọi property mặc định. Chỉ nên ghi rõ những giá trị ảnh hưởng contract, security hoặc trải nghiệm mà hệ thống cần giữ ổn định qua các lần nâng.

## 11. Kiểm tra đầu ra sau nâng cấp

### 11.1. Kiểm tra OpenAPI dialect và paths

MockMvc test có thể xác nhận OpenAPI document đang phát đúng version:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.startsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SpringdocUpgradeContractTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publishesExpectedOpenApiVersion() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.openapi", startsWith("3.1.")));
    }

    @Test
    void keepsExpectedOperationAfterUpgrade() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.paths['/api/products/{id}'].get").exists());
    }
}
~~~

Nếu đã pin OPENAPI_3_0, đổi matcher thành startsWith("3.0."). Không hard-code patch version nếu patch phụ thuộc swagger-core hoặc springdoc.

### 11.2. Kiểm tra Swagger UI config

Tải endpoint cấu hình:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs/swagger-config \
  -o build/swagger-config.json
~~~

So sánh các trường url, urls, urlsPrimaryName, oauth2RedirectUrl và các UI option quan trọng với baseline. Nếu có đổi configUrl hoặc context path, dùng endpoint tương ứng.

### 11.3. So sánh OpenAPI artifact

Lưu artifact sau nâng cấp:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs \
  -o build/openapi-current.json

curl -fsS http://localhost:8080/v3/api-docs.yaml \
  -o build/openapi-current.yaml
~~~

So sánh cấu trúc thay vì chỉ diff text. Tập trung vào:

- Trường openapi và info.version.
- Paths và HTTP methods.
- OperationId.
- Required request fields và response fields.
- Nullable, enum, format và default values.
- oneOf/allOf/discriminator và $ref.
- Security schemes và operation security.
- Server URL và response codes.

## 12. Những lỗi thường gặp

- **Nâng springdoc v1 lên v2 nhưng không kiểm tra OpenAPI version**: default thay từ 3.0 sang 3.1.
- **Chỉ đổi version dependency**: starter artifact, package import và Jakarta namespace có thể cần cập nhật.
- **Dùng springdoc 3.x với Spring Boot 3**: nhánh 3.x dành cho Spring Boot 4.
- **Dùng springdoc 2.x với Spring Boot 4**: chọn nhánh tương thích Boot 4.
- **Nhầm info.version với api-docs.version**: một trường là API release, một property chọn OpenAPI dialect.
- **Cho rằng property trong YAML là giá trị hiệu lực**: profile, env, system property và command line có thể ghi đè.
- **Cho rằng default UI không đổi**: Swagger UI dependency có thể được nâng cùng starter, làm thay đổi hành vi browser.
- **Bỏ qua cache max entries**: từ v2.9.1 có bounded cache với default 100.
- **Bỏ qua requiredness của Page/MonetaryAmount**: schema mới có thể làm SDK sinh field non-nullable.
- **Bỏ qua API versioning behavior ở v3.2.0**: allowed/default version của operation có thể thay đổi.
- **Chỉ kiểm tra ứng dụng khởi động**: cần kiểm tra OpenAPI JSON/YAML và swagger-config.
- **Mở actuator env/configprops công khai**: các endpoint này có thể tiết lộ cấu hình nhạy cảm.
- **Dựa hoàn toàn vào spring-boot-properties-migrator**: công cụ này hỗ trợ property của Spring Boot, không thay thế việc đối chiếu property riêng của springdoc.
- **Chỉ diff YAML text**: thay đổi thứ tự key có thể gây nhiễu; dùng semantic diff cho contract.

## 13. Quy trình review migration

1. **Xác định runtime line**: Spring Boot, Spring Framework, Java và WebMVC/WebFlux.
2. **Chọn springdoc line tương thích**: v1 legacy, v2 cho Boot 3 hoặc v3 cho Boot 4.
3. **Đối chiếu starter và package**: thay artifact/module/import theo migration guide.
4. **Đối chiếu property names**: tìm property đã deprecated, đổi tên hoặc không còn hỗ trợ.
5. **So sánh default**: đặc biệt OpenAPI dialect, cache và model converter.
6. **Kiểm tra effective values**: dùng configprops/env hoặc configuration bean.
7. **So sánh OpenAPI output**: kiểm tra schema, paths, security và servers.
8. **So sánh Swagger UI config**: URL, layout, Try it out, OAuth và persistence.
9. **Chạy contract tests**: xác minh request/response runtime.
10. **Ghi lại thay đổi có chủ đích**: pin property nếu cần giữ behavior qua các lần nâng tiếp theo.

## 14. Checklist review

- [ ] Spring Boot và springdoc thuộc đúng compatibility line.
- [ ] Starter artifact đã được đổi theo migration guide.
- [ ] Package import và javax/jakarta annotations đã được rà soát.
- [ ] Đã kiểm tra default springdoc.api-docs.version.
- [ ] Đã phân biệt OpenAPI version với info.version và API versioning.
- [ ] Đã so sánh các core property defaults.
- [ ] Đã so sánh Swagger UI defaults và version được đóng gói.
- [ ] Đã kiểm tra cache max entries nếu dùng v2.9.1 trở lên.
- [ ] Đã kiểm tra schema requiredness, nullability và polymorphic model.
- [ ] Đã kiểm tra giá trị hiệu lực bằng configprops/env hoặc test.
- [ ] OpenAPI JSON/YAML mới được semantic diff với baseline.
- [ ] Swagger UI config và browser runtime đã được kiểm tra.
- [ ] Contract tests chạy qua request/response thực tế.
- [ ] Actuator diagnostics được bảo vệ.
- [ ] Các default quan trọng đã được pin nếu consumer phụ thuộc vào chúng.

## 15. Tài liệu tham khảo

- [springdoc-openapi v1 – Properties for Spring Boot 2](https://springdoc.org/v1/index.html)
- [springdoc-openapi v2 – Migration from v1](https://springdoc.org/v2/migrating-from-springdoc-v1.html)
- [springdoc-openapi v2 – Properties](https://springdoc.org/v2/properties.html)
- [springdoc-openapi current – Properties](https://springdoc.org/properties.html)
- [springdoc-openapi current – Compatibility matrix](https://springdoc.org/index.html#what-is-the-compatibility-matrix-of-springdoc-openapi-with-spring-boot)
- [springdoc-openapi – Releases](https://github.com/springdoc/springdoc-openapi/releases)
- [Spring Boot – Actuator endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot – Externalized configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)

Nâng cấp Springdoc cần kiểm tra cả dependency, property default, giá trị hiệu lực và tài liệu được sinh. Thay đổi dễ gây ảnh hưởng nhất từ v1 sang v2 là default OpenAPI 3.0 chuyển sang 3.1; các nhánh mới còn bổ sung cache bounds và thay đổi schema cho một số model. Hãy lưu baseline trước nâng cấp, kiểm tra cấu hình runtime và semantic diff OpenAPI JSON/YAML, rồi mới phát hành để bảo đảm client tiếp tục hiểu đúng hợp đồng.
