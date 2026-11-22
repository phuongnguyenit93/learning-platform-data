# Khác biệt giữa cấu hình Springdoc với cấu hình của công cụ giao diện

Springdoc-openapi và Swagger UI thường được cài cùng nhau trong một Spring Boot application, nhưng chúng làm hai việc khác nhau. Springdoc đọc controller, DTO, annotation và cấu hình Spring để tạo OpenAPI document. Swagger UI nhận document đó rồi hiển thị thành trang tài liệu có thể tìm kiếm, mở rộng operation và gửi thử request.

Vì hai công cụ có nhiều property được khai báo dưới cùng prefix springdoc, rất dễ nhầm một thay đổi giao diện với thay đổi hợp đồng API. Ví dụ:

- springdoc.paths-to-match quyết định endpoint nào được đưa vào OpenAPI document.
- springdoc.swagger-ui.doc-expansion chỉ quyết định operation được mở rộng thế nào trên trang.
- springdoc.api-docs.path đổi URL của OpenAPI document.
- springdoc.swagger-ui.path đổi URL của trang HTML Swagger UI.

Phân biệt hai lớp cấu hình giúp chẩn đoán đúng khi JSON/YAML không thay đổi dù giao diện đã đổi, hoặc giao diện vẫn hiển thị nhưng tài liệu OpenAPI thiếu operation.

## 1. Hai công cụ, hai trách nhiệm

| Thành phần | Trách nhiệm | Ví dụ cấu hình |
|---|---|---|
| Springdoc core | Quét controller, chọn endpoint, tạo paths, operations, schemas, responses và security definitions | springdoc.paths-to-match, springdoc.packages-to-scan, springdoc.api-docs.path |
| OpenAPI model customization | Bổ sung hoặc chỉnh nội dung hợp đồng OpenAPI | OpenAPI bean, OpenApiCustomizer, OperationCustomizer |
| Swagger UI | Hiển thị document, điều hướng tags/operations, trình bày schema và hỗ trợ Try it out | springdoc.swagger-ui.doc-expansion, operations-sorter, filter |
| Swagger UI network/auth configuration | Chọn document, config endpoint, OAuth UI và request options của trình duyệt | springdoc.swagger-ui.url, urls, config-url, oauth.* |

Springdoc tạo ra tài liệu OpenAPI. Swagger UI là một client-side application đọc tài liệu đó. Cấu hình Swagger UI không tự sửa controller, schema hoặc response mà Springdoc đã sinh.

## 2. Luồng hoạt động từ ứng dụng đến giao diện

~~~mermaid
flowchart TD
    A[Spring Controller / DTO / Annotation] --> B[Springdoc]
    C[Spring Boot application properties] --> B
    D[OpenAPI bean / Customizer] --> B
    B --> E[OpenAPI JSON or YAML]
    B --> F[Swagger UI config JSON]
    G[Swagger UI properties] --> F
    E --> H[Swagger UI in browser]
    F --> H
    H --> I[Render operations / schemas]
    H --> J[Try it out HTTP request]
    J --> K[Spring Boot API endpoint]
~~~

Các endpoint mặc định thường gặp:

| Endpoint | Nội dung |
|---|---|
| /v3/api-docs | OpenAPI document dạng JSON. |
| /v3/api-docs.yaml | OpenAPI document dạng YAML. |
| /v3/api-docs/swagger-config | JSON cấu hình mà Swagger UI tải để biết document URL và các UI options. |
| /swagger-ui.html | Trang HTML mở Swagger UI. |
| /swagger-ui/** | Static resources của giao diện như JavaScript và CSS. |

Swagger UI thường tải cấu hình trước, sau đó dùng URL trong cấu hình để tải OpenAPI JSON/YAML. Vì vậy, hai endpoint sau có ý nghĩa khác nhau:

- springdoc.swagger-ui.url: URL của OpenAPI document.
- springdoc.swagger-ui.config-url: URL của file cấu hình Swagger UI.

Không trỏ config-url tới file OpenAPI YAML. Swagger UI cần một config document ở URL đó; URL của API definition được khai báo bằng url hoặc urls.

## 3. Cấu hình phần sinh OpenAPI

Nhóm property core quyết định Springdoc đọc gì và xuất hợp đồng ở đâu.

~~~yaml
springdoc:
  api-docs:
    enabled: true
    path: /internal/openapi
    version: OPENAPI_3_1
  packages-to-scan:
    - com.example.catalog.api
    - com.example.billing.api
  paths-to-match:
    - /api/**
  paths-to-exclude:
    - /api/internal/**
  writer-with-default-pretty-printer: true
~~~

Ý nghĩa:

- api-docs.enabled: bật hoặc tắt endpoint cung cấp OpenAPI document.
- api-docs.path: đổi path JSON document.
- api-docs.version: chọn OpenAPI 3.0 hoặc 3.1 theo khả năng của nhánh springdoc.
- packages-to-scan: giới hạn package chứa controller được xem xét.
- paths-to-match: chỉ đưa các path khớp điều kiện vào document.
- paths-to-exclude: loại path khỏi document.
- writer-with-default-pretty-printer: định dạng JSON dễ đọc hơn.

Các property này tác động tới OpenAPI document. Ví dụ, loại /api/internal/** khỏi tài liệu không xóa controller tương ứng và không chặn HTTP request tới controller đó. Muốn bảo vệ endpoint runtime, phải dùng Spring Security, gateway hoặc network policy.

### 3.1. Tùy chỉnh nội dung document bằng Java

Nếu cần metadata chung, security scheme hoặc server URL, có thể tạo OpenAPI bean:

~~~java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiConfiguration {

    @Bean
    OpenAPI customOpenAPI() {
        return new OpenAPI()
                .info(new Info()
                        .title("Catalog API")
                        .version("1.4.0")
                        .description("API quản lý danh mục sản phẩm."));
    }
}
~~~

Để chỉnh từng document hoặc group, có thể dùng OpenApiCustomizer và OperationCustomizer. Đây là customization của hợp đồng, không phải customization của layout Swagger UI.

~~~java
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiExtensionConfiguration {

    @Bean
    OpenApiCustomizer addOwnerExtension() {
        return openApi -> openApi.addExtension("x-owner", "catalog-team");
    }
}
~~~

Sau khi thêm customizer, kiểm tra /v3/api-docs để xác nhận extension thực sự có trong document.

## 4. Cấu hình đường dẫn Swagger UI

Nhóm property springdoc.swagger-ui chủ yếu điều khiển trang giao diện và cách giao diện tải document.

~~~yaml
springdoc:
  swagger-ui:
    enabled: true
    path: /docs
    config-url: /internal/openapi/swagger-config
    url: /internal/openapi
    doc-expansion: none
    operations-sorter: alpha
    tags-sorter: alpha
    display-request-duration: true
    display-operation-id: true
~~~

Trong ví dụ:

- Trang UI nằm ở /docs.
- UI tải cấu hình tại /internal/openapi/swagger-config.
- UI lấy OpenAPI document tại /internal/openapi.
- Tags và operations được sắp xếp alphabetically.
- Các operation mặc định không mở rộng.
- UI hiển thị thời gian thực hiện request và operationId.

Khi thay đổi api-docs.path hoặc dùng config URL riêng, hãy kiểm tra endpoint cấu hình thực tế được ứng dụng phục vụ. Nếu cấu hình mặc định không trỏ tới path mới, cập nhật config-url tương ứng.

### 4.1. url, urls và config-url

| Property | Trỏ tới | Dùng khi |
|---|---|---|
| springdoc.swagger-ui.url | Một OpenAPI JSON/YAML document | Một API definition tùy chỉnh. |
| springdoc.swagger-ui.urls | Danh sách nhiều OpenAPI document | Swagger UI cần dropdown chọn nhiều service/group. |
| springdoc.swagger-ui.config-url | Swagger UI configuration document | Dùng cấu hình giao diện được lưu ở endpoint hoặc nguồn riêng. |

Ví dụ liệt kê hai group:

~~~yaml
springdoc:
  swagger-ui:
    urls:
      - name: Catalog
        url: /v3/api-docs/catalog
      - name: Billing
        url: /v3/api-docs/billing
    urls-primary-name: Catalog
~~~

Khi urls được cấu hình, url đơn lẻ bị bỏ qua. Tên và URL trong danh sách phải duy nhất vì Swagger UI dùng chúng làm identifier.

## 5. Những property chỉ ảnh hưởng tới cách hiển thị

Các property dưới đây thay đổi trải nghiệm người xem, không thay đổi paths hoặc schemas trong OpenAPI:

~~~yaml
springdoc:
  swagger-ui:
    doc-expansion: none
    operations-sorter: alpha
    tags-sorter: alpha
    filter: true
    max-displayed-tags: 30
    default-models-expand-depth: 1
    default-model-expand-depth: 1
    display-operation-id: true
    display-request-duration: true
    show-extensions: true
    show-common-extensions: true
~~~

Một số lựa chọn:

| Property | Tác động |
|---|---|
| doc-expansion | list, full hoặc none quyết định mức mở rộng ban đầu. |
| operations-sorter | Sắp xếp operation theo alphabet hoặc HTTP method. |
| tags-sorter | Sắp xếp tag. |
| filter | Hiển thị ô lọc operation/tag. |
| max-displayed-tags | Giới hạn số tag được hiển thị. |
| default-models-expand-depth | Độ sâu mở rộng danh sách model. |
| display-operation-id | Hiển thị operationId trong giao diện. |
| display-request-duration | Hiển thị thời gian của request Try it out. |
| show-extensions | Hiển thị các vendor extension x- trong giao diện. |
| show-common-extensions | Hiển thị các constraint như minLength, maxLength, minimum và maximum. |

Nếu người dùng muốn Swagger UI gọn hơn, thay doc-expansion hoặc filter. Nếu họ muốn bỏ một endpoint khỏi hợp đồng, thay paths-to-exclude, GroupedOpenApi hoặc annotation phù hợp. Không dùng property UI để giải quyết vấn đề ở OpenAPI document.

## 6. Try it out không phải authorization

Swagger UI có thể gửi request trực tiếp từ trình duyệt. Hai nhóm property thường được dùng:

~~~yaml
springdoc:
  swagger-ui:
    try-it-out-enabled: true
    supported-submit-methods:
      - get
      - post
      - put
    persist-authorization: false
~~~

- try-it-out-enabled điều khiển trạng thái mở rộng mặc định của khu vực Try it out.
- supported-submit-methods chỉ định HTTP methods mà UI cho phép gửi thử.
- Danh sách supported-submit-methods rỗng sẽ tắt Try it out cho mọi operation nhưng không xóa operation khỏi giao diện.
- persist-authorization quyết định Swagger UI có giữ authorization data qua lần refresh/đóng mở trình duyệt hay không.

Các property này chỉ điều khiển browser UI. Chúng không thay đổi server endpoint, không chặn người dùng gọi API bằng curl/Postman và không thay thế Spring Security. Nếu muốn cấm POST ở production, phải enforce tại server hoặc gateway.

## 7. Cấu hình OAuth của Swagger UI và security contract

Có hai lớp liên quan tới authentication nhưng mục tiêu khác nhau:

1. **OpenAPI security definition** mô tả scheme và operation nào yêu cầu scheme đó.
2. **Swagger UI OAuth configuration** giúp browser thực hiện flow đăng nhập để thử API.

Ví dụ định nghĩa Bearer scheme trong OpenAPI:

~~~java
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.security.SecurityScheme;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ApiSecurityDocumentation {

    @Bean
    OpenAPI securedApi() {
        return new OpenAPI()
                .info(new Info()
                        .title("Secured Catalog API")
                        .version("1.4.0"))
                .components(new Components()
                        .addSecuritySchemes(
                                "bearerAuth",
                                new SecurityScheme()
                                        .type(SecurityScheme.Type.HTTP)
                                        .scheme("bearer")
                                        .bearerFormat("JWT")
                        ));
    }
}
~~~

Một operation có thể tham chiếu scheme bằng SecurityRequirement hoặc security requirement trong OpenAPI model. Khi đó JSON/YAML có components.securitySchemes và security tương ứng. Nếu ứng dụng đã có OpenAPI bean để khai báo title/version/server, hãy thêm security scheme vào cùng bean đó thay vì tạo hai bean OpenAPI cạnh tranh.

Swagger UI có thể được cấu hình để hỗ trợ OAuth:

~~~yaml
springdoc:
  swagger-ui:
    oauth:
      client-id: catalog-docs
      use-pkce-with-authorization-code-grant: true
    oauth2-redirect-url: https://api.example.com/docs/oauth2-redirect.html
~~~

Chỉ khai báo client ID và các thông tin flow phù hợp với identity provider. Không đặt springdoc.swagger-ui.oauth.client-secret trong production vì giá trị này được gửi tới trình duyệt và có thể bị người dùng xem. Với public client, sử dụng Authorization Code + PKCE khi identity provider hỗ trợ.

OAuth UI configuration không tạo security scheme trong OpenAPI nếu chưa định nghĩa scheme. Ngược lại, một security scheme trong OpenAPI không tự cấu hình identity provider hoặc cấp token cho browser.

## 8. Cấu hình Swagger UI bằng Java

Khi cấu hình qua application.yml chưa đủ, springdoc cho phép cung cấp bean SwaggerUiConfigProperties. FAQ của dự án minh họa cách dùng bean @Primary để thay đổi thuộc tính UI:

~~~java
import org.springdoc.core.properties.SwaggerUiConfigProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

@Configuration
class SwaggerUiConfiguration {

    @Bean
    @Primary
    SwaggerUiConfigProperties swaggerUiConfig(
            SwaggerUiConfigProperties config) {
        config.setShowCommonExtensions(true);
        return config;
    }
}
~~~

Đây là cấu hình cho Swagger UI. Nếu cần chỉnh OpenAPI model, dùng OpenAPI bean, OpenApiCustomizer hoặc OperationCustomizer tương ứng.

Tránh cấu hình cùng một giá trị ở nhiều nơi mà không có quy tắc ưu tiên rõ ràng. Nếu application.yml đặt doc-expansion: full nhưng Java bean lại ghi none, hãy kiểm tra giá trị thực tế trong config document được UI tải.

## 9. config-url và thứ tự ưu tiên cấu hình của Swagger UI

Swagger UI có thể nhận config từ:

- Object được truyền vào khi khởi tạo Swagger UI.
- Document được tải qua configUrl.
- Query parameters trong URL.

Theo tài liệu Swagger UI, config document tải từ configUrl có mức ưu tiên cao hơn config object khởi tạo; query parameters có mức ưu tiên cao nhất. Tuy nhiên, springdoc mặc định không bật việc ghi đè cấu hình qua query parameters. Property springdoc.swagger-ui.query-config-enabled đã bị vô hiệu hóa theo mặc định từ v1.6.0 vì lý do bảo mật.

Nếu tự triển khai config document bên ngoài:

1. Đảm bảo URL config trả JSON có cấu trúc Swagger UI mong đợi.
2. Đảm bảo URL OpenAPI document nằm trong url hoặc urls của config.
3. Đảm bảo browser truy cập được cả config và OpenAPI document.
4. Cấu hình CORS nếu các URL khác origin.
5. Kiểm tra DevTools Network để biết UI đang tải config nào và giá trị nào được áp dụng.

Không dùng query string để thay đổi các thiết lập nhạy cảm của Swagger UI trong production. Giữ query config disabled trừ khi có lý do rõ ràng và đã đánh giá security advisory.

## 10. Tắt UI và tắt OpenAPI document là hai việc khác nhau

| Property | Tác động |
|---|---|
| springdoc.api-docs.enabled=false | Tắt endpoint OpenAPI document được springdoc tạo. |
| springdoc.swagger-ui.enabled=false | Tắt trang Swagger UI. |

Một deployment có thể tắt Swagger UI nhưng vẫn cung cấp OpenAPI JSON/YAML cho CI hoặc API catalog. Ngược lại, UI có thể được bật để hiển thị một OpenAPI file bên ngoài trong cấu hình đặc biệt, nhưng cần bảo đảm nguồn document và cấu hình UI được thiết lập đầy đủ.

Không coi việc ẩn Swagger UI là biện pháp bảo vệ API. Endpoint /v3/api-docs và các API nghiệp vụ vẫn cần được bảo vệ bằng authorization phù hợp. Nếu tài liệu chỉ dành cho nội bộ, kiểm soát truy cập tại Spring Security hoặc reverse proxy.

## 11. Kiểm tra đúng lớp cấu hình

Sau khi thay đổi cấu hình, kiểm tra cả server output và browser UI.

### 11.1. Kiểm tra OpenAPI document

Ví dụ:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o build/openapi.json
~~~

Xác minh:

- openapi và info có giá trị mong muốn.
- paths chỉ chứa endpoint được chọn.
- components.schemas, security schemes và responses đúng.
- API docs endpoint nằm ở path đã cấu hình.

Nếu đổi springdoc.paths-to-match, springdoc.paths-to-exclude, api-docs.version hoặc customizer, kết quả cần thể hiện trong JSON/YAML.

### 11.2. Kiểm tra Swagger UI config document

Với cấu hình mặc định:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs/swagger-config
~~~

Kiểm tra:

- url hoặc urls trỏ tới OpenAPI document đúng.
- urlsPrimaryName khớp một entry nếu dùng danh sách nhiều document.
- oauth2RedirectUrl đúng public URL nếu dùng OAuth.
- UI properties như docExpansion, filter, supportedSubmitMethods được đưa vào config khi phù hợp.

Nếu swagger-config đúng nhưng trang UI không đổi, kiểm tra browser cache, static resource version và DevTools Network.

### 11.3. Kiểm thử hai endpoint bằng MockMvc

Một integration test có thể xác nhận OpenAPI document và Swagger UI config đều được phục vụ:

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
class DocumentationConfigurationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void servesOpenApiDocument() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.openapi").exists())
                .andExpect(jsonPath("$.paths").exists());
    }

    @Test
    void servesSwaggerUiConfiguration() throws Exception {
        mockMvc.perform(get("/v3/api-docs/swagger-config"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.url").value("/v3/api-docs"));
    }
}
~~~

Ví dụ giả định endpoint tài liệu được phép truy cập trong test. Nếu Spring Security bảo vệ các endpoint này, thêm authentication phù hợp vào request test; không thay đổi policy production để làm test pass.

Nếu ứng dụng đổi api-docs.path hoặc dùng urls cho nhiều document, điều chỉnh endpoint và assertion theo cấu hình đã chọn. Test JSON không thay thế browser test: vẫn cần kiểm tra JavaScript/CSS, redirect, CORS và hành vi Try it out.

### 11.4. Kiểm tra trang UI

Mở /swagger-ui.html hoặc custom path đã cấu hình và kiểm tra:

- UI tải JavaScript/CSS thành công.
- UI lấy đúng swagger-config.
- UI tải đúng OpenAPI JSON/YAML.
- Layout, sorting, filter và expansion đúng mong muốn.
- Try it out chỉ bật cho các method được cấu hình.
- Authorization flow dùng đúng redirect URL và identity provider.

Một UI render thành công không chứng minh OpenAPI schema đúng. Ngược lại, OpenAPI JSON hợp lệ không đảm bảo Swagger UI có thể tải file hoặc render đúng khi config URL, CORS hoặc static resources sai.

## 12. Những lỗi thường gặp

Property list thay đổi theo nhánh springdoc và phiên bản Swagger UI được đóng gói. Dự án Spring Boot 3 dùng tài liệu springdoc v2; Spring Boot 4 dùng tài liệu nhánh hiện hành. Khi một property không được nhận diện, hãy đối chiếu đúng nhánh tài liệu và kiểm tra version Swagger UI đi kèm thay vì giả định mọi phiên bản có cùng tập option.

- **Dùng springdoc.paths-to-match để sắp xếp operation**: property này lọc endpoint trong document; dùng operations-sorter cho UI.
- **Dùng doc-expansion để bỏ operation khỏi OpenAPI**: property này chỉ thay cách mở rộng giao diện.
- **Nhầm api-docs.path với swagger-ui.path**: một path là OpenAPI document, path còn lại là trang HTML.
- **Nhầm config-url với url**: config URL trả UI configuration; url trỏ tới OpenAPI document.
- **Tùy chỉnh OpenAPI bằng SwaggerUiConfigProperties**: dùng OpenAPI bean/customizer cho schema, paths và security definitions.
- **Tùy chỉnh UI bằng OpenAPI bean**: dùng springdoc.swagger-ui.* hoặc Swagger UI configuration.
- **Tắt api-docs.enabled nhưng vẫn mong UI đọc document nội bộ**: UI cần một nguồn spec hợp lệ.
- **Tắt swagger-ui.enabled rồi nghĩ API docs cũng bị tắt**: hai property điều khiển hai endpoint khác nhau.
- **Dùng supported-submit-methods như authorization**: người dùng vẫn có thể gọi API ngoài Swagger UI.
- **Đưa OAuth client secret vào browser**: secret có thể bị lộ; dùng public client và PKCE khi phù hợp.
- **Bật query config override mà không xem xét bảo mật**: giữ queryConfigEnabled disabled theo mặc định.
- **Đổi config-url nhưng quên CORS**: browser có thể chặn tải config từ origin khác.
- **Chỉ kiểm tra trang HTML**: phải kiểm tra cả JSON/YAML và swagger-config.
- **Cho rằng UI filter là API filter**: filter trong giao diện chỉ ẩn bớt nội dung đang hiển thị.

## 13. Quy trình lựa chọn cấu hình

1. **Xác định mục tiêu**: thay đổi nội dung hợp đồng hay trải nghiệm xem tài liệu.
2. **Chọn lớp Springdoc core** nếu cần lọc controller/path, đổi OpenAPI version hoặc chỉnh schema.
3. **Chọn OpenAPI bean/customizer** nếu cần thêm metadata, server, security scheme hoặc operation details.
4. **Chọn Swagger UI properties** nếu cần đổi layout, sorting, expansion, filtering hoặc Try it out.
5. **Chọn url/urls** nếu muốn UI tải một hay nhiều OpenAPI document.
6. **Chọn config-url** nếu muốn UI tải configuration document từ endpoint riêng.
7. **Cấu hình OAuth UI** nhưng giữ secret ở phía server và dùng PKCE cho public client khi phù hợp.
8. **Bảo vệ API docs và UI** bằng security policy; không dựa vào việc ẩn trang.
9. **Kiểm tra OpenAPI JSON/YAML và swagger-config** sau khi thay đổi.
10. **Kiểm tra browser runtime** để xác nhận UI tải đúng document, assets và request behavior.

## 14. Checklist review

- [ ] Đã phân biệt Springdoc core properties với Swagger UI properties.
- [ ] api-docs.path và swagger-ui.path được dùng đúng mục đích.
- [ ] paths-to-match/packages-to-scan chỉ lọc nội dung OpenAPI.
- [ ] OpenAPI bean/customizer dùng để thay đổi contract.
- [ ] url hoặc urls trỏ tới OpenAPI document.
- [ ] config-url trỏ tới JSON cấu hình giao diện.
- [ ] UI sorting, filtering và expansion không bị nhầm là thay đổi contract.
- [ ] Try it out settings không bị coi là server-side authorization.
- [ ] OAuth client secret không được gửi tới browser production.
- [ ] Query config override vẫn disabled trừ khi có lý do và security review.
- [ ] CORS được cấu hình nếu UI tải spec/config từ origin khác.
- [ ] api-docs.enabled và swagger-ui.enabled được quản lý riêng.
- [ ] CI kiểm tra OpenAPI JSON/YAML và swagger-config.
- [ ] Browser test xác nhận UI tải đúng document và assets.

## 15. Tài liệu tham khảo

- [springdoc-openapi – Core and UI configuration properties](https://springdoc.org/properties.html)
- [springdoc-openapi – Swagger UI properties reference](https://springdoc.org/ui-properties.html)
- [springdoc-openapi v2 – FAQ for Spring Boot 3](https://springdoc.org/v2/faq.html)
- [springdoc-openapi – Getting Started](https://springdoc.org/getting-started.html)
- [Swagger UI – Configuration reference](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/)
- [Swagger UI – OAuth 2.0 configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/oauth2/)
- [OpenAPI Specification](https://spec.openapis.org/oas/)

Springdoc quyết định hợp đồng nào được sinh và nội dung hợp đồng đó; Swagger UI quyết định người dùng nhìn thấy và tương tác với tài liệu ra sao. Hãy dùng core properties và OpenAPI customizers cho document, dùng springdoc.swagger-ui.* cho giao diện, phân biệt url với config-url, rồi kiểm tra riêng OpenAPI JSON/YAML, swagger-config và browser runtime. Cách phân lớp này giúp tránh sửa nhầm nơi và giữ ranh giới rõ giữa tài liệu API, công cụ hiển thị và bảo mật endpoint thật.
