# Mở rộng giao diện bằng tài nguyên hoặc cấu hình phù hợp phiên bản

Swagger UI do springdoc-openapi cung cấp có thể được điều chỉnh ở nhiều mức. Các thuộc tính cấu hình phù hợp cho việc đổi đường dẫn, chọn tài liệu OpenAPI, bố trí giao diện và bật/tắt chức năng. Khi cần thay đổi giao diện sâu hơn như thêm CSS, JavaScript, favicon hoặc sửa trang HTML khởi tạo, cần mở rộng các tài nguyên tĩnh mà Swagger UI đang sử dụng. Cách triển khai phụ thuộc phiên bản springdoc, Spring Boot và loại ứng dụng Web MVC hay WebFlux.

## 1. Chọn đúng mức mở rộng

Trước khi sửa tài nguyên, hãy xác định chính xác mục tiêu:

| Nhu cầu | Cách phù hợp |
|---|---|
| Đổi URL mở Swagger UI | `springdoc.swagger-ui.path` |
| Tắt giao diện nhưng vẫn giữ JSON/YAML OpenAPI | `springdoc.swagger-ui.enabled=false` |
| Chọn một file OpenAPI có sẵn | `springdoc.swagger-ui.url` |
| Cho phép chọn nhiều tài liệu hoặc group | `springdoc.swagger-ui.urls` và `urls-primary-name` |
| Đổi layout sang component đã được Swagger UI cung cấp | `springdoc.swagger-ui.layout` |
| Điều chỉnh sorter, filter, expansion và các tùy chọn hiển thị | Các thuộc tính Swagger UI dưới prefix `springdoc.swagger-ui` |
| Thêm stylesheet, script, favicon hoặc đổi HTML | Tùy chỉnh static resource bằng `SwaggerIndexPageTransformer` |
| Thay đổi cấu trúc giao diện bằng plugin riêng | Tích hợp plugin/layout của Swagger UI qua trang khởi tạo đã tùy biến |

Không cần ghi đè toàn bộ `index.html` chỉ để đổi màu hoặc thêm logo. Mỗi lần thay thế trang khởi tạo, ứng dụng phải tiếp tục cung cấp đúng URL `swagger-config`, OpenAPI document và các asset mà springdoc chèn vào trang. Nếu bỏ sót bước biến đổi mặc định, Swagger UI có thể tải được HTML nhưng không tải được định nghĩa API.

## 2. Kiểm tra tương thích Spring Boot và springdoc trước khi mở rộng

Các lớp dùng để tùy chỉnh tài nguyên Swagger UI là một phần của tích hợp springdoc. Tên artifact, package và chữ ký transformer thay đổi giữa các major version. Trước khi viết code, xác định Spring Boot version, Web MVC/WebFlux và dependency springdoc hiện tại.

| Dòng Spring Boot | Dòng springdoc tương ứng | Dependency UI phổ biến |
|---|---|---|
| Spring Boot 2.x và các ứng dụng legacy 1.x | springdoc 1.x; bản open-source cuối là 1.8.0 | `springdoc-openapi-ui` |
| Spring Boot 3.x | springdoc 2.x | `springdoc-openapi-starter-webmvc-ui` hoặc `springdoc-openapi-starter-webflux-ui` |
| Spring Boot 4.0.x | springdoc 3.0.x | `springdoc-openapi-starter-webmvc-ui` hoặc `springdoc-openapi-starter-webflux-ui` |
| Spring Boot 4.1.x | springdoc 3.1.x đến 3.2.x | `springdoc-openapi-starter-webmvc-ui` hoặc `springdoc-openapi-starter-webflux-ui` |

Ví dụ dependency Maven cho Spring Boot 3 với Web MVC:

```xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>${springdoc.version}</version>
</dependency>
```

Với WebFlux, dùng `springdoc-openapi-starter-webflux-ui`. Nếu chỉ cần tài liệu JSON/YAML mà không cần giao diện, dùng starter `webmvc-api` hoặc `webflux-api` tương ứng.

Không thêm đồng thời nhiều major version của springdoc hoặc tự ghim một phiên bản Swagger UI WebJar không tương thích với starter. Starter đã quản lý phiên bản Swagger UI mà springdoc tích hợp. Khi nâng Spring Boot, hãy kiểm tra compatibility matrix và migration guide của đúng major version trước khi sao chép code transformer cũ.

## 3. Cấu hình giao diện bằng application.yml

Các thuộc tính cấu hình Swagger UI của springdoc dùng prefix `springdoc.swagger-ui`. Có thể cấu hình bằng YAML hoặc properties; Spring Boot hỗ trợ relaxed binding nên tên YAML thường dùng kebab-case.

Ví dụ đặt đường dẫn giao diện, chọn layout có sẵn và dùng một file OpenAPI tĩnh:

```yaml
springdoc:
  swagger-ui:
    enabled: true
    path: /docs/swagger-ui.html
    layout: BaseLayout
    url: /openapi/store-api.yaml
    disable-swagger-default-url: true
```

Trong ví dụ:

- Giao diện được truy cập qua `/docs/swagger-ui.html`.
- `BaseLayout` là layout mặc định của Swagger UI.
- `url` trỏ tới file OpenAPI được phục vụ tại `/openapi/store-api.yaml`.
- `disable-swagger-default-url` tắt URL Petstore mặc định của Swagger UI.

Để phục vụ file YAML tĩnh, có thể đặt file tại `src/main/resources/static/openapi/store-api.yaml`. Với static resource mặc định của Spring Boot, file này được truy cập tại `/openapi/store-api.yaml`.

Nếu dùng OpenAPI được sinh từ controller, không cần khai báo `url` riêng trong trường hợp thông thường; springdoc tự cấu hình `/v3/api-docs`.

### Chọn nhiều tài liệu OpenAPI

Khi ứng dụng có nhiều group, dùng `urls` để hiển thị dropdown chọn tài liệu:

```yaml
springdoc:
  swagger-ui:
    urls:
      - name: Public API
        url: /v3/api-docs/public
      - name: Admin API
        url: /v3/api-docs/admin
    urls-primary-name: Public API
    disable-swagger-default-url: true
```

Tên và URL trong danh sách cần duy nhất. `urls` được ưu tiên khi có cấu hình đồng thời với `url`; do đó, đừng kỳ vọng `url` đơn lẻ sẽ được sử dụng khi danh sách `urls` đã có.

### Tách endpoint UI khỏi trang chủ ứng dụng

Nếu ứng dụng đã có `src/main/resources/public/index.html` hoặc trang welcome ở root, endpoint Swagger UI có thể gây xung đột khi dùng đường dẫn mặc định. Đặt đường dẫn riêng:

```yaml
springdoc:
  swagger-ui:
    path: /docs/swagger-ui.html
```

Điều này giữ nguyên trang chủ hiện tại và đưa tài liệu API sang URL riêng. Sau khi đổi path, cập nhật security matcher, reverse proxy route và liên kết tài liệu nội bộ nếu có.

## 4. Cấu hình Swagger UI theo chương trình

Khi cấu hình phụ thuộc profile hoặc logic Java, có thể tùy chỉnh `SwaggerUiConfigProperties` bằng bean. Ví dụ dưới đây bật hiển thị common extensions trong schema:

```java
import org.springdoc.core.properties.SwaggerUiConfigProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

@Configuration
class SwaggerUiPropertiesConfiguration {

    @Bean
    @Primary
    SwaggerUiConfigProperties swaggerUiConfigProperties(
        SwaggerUiConfigProperties properties
    ) {
        properties.setShowCommonExtensions(true);
        return properties;
    }
}
```

Ví dụ dùng package của springdoc 2.x/3.x. Với springdoc 1.x, package của một số lớp cấu hình khác. Không tạo một instance `SwaggerUiConfigProperties` mới bằng constructor rỗng nếu mục tiêu là sửa cấu hình đã được Spring Boot bind; hãy nhận bean cấu hình hiện tại và cập nhật các thuộc tính cần thiết.

Chỉ nên dùng bean programmatic khi có lý do rõ ràng như profile, cấu hình tenant hoặc giá trị được tính từ môi trường. Với giá trị cố định, `application.yml` dễ đọc và dễ kiểm tra hơn.

## 5. Các tài nguyên tĩnh mà Swagger UI sử dụng

Swagger UI được đóng gói dưới dạng WebJar. Trong ứng dụng, các tài nguyên thường nằm dưới đường dẫn classpath tương tự:

```text
META-INF/resources/webjars/swagger-ui/{swagger.version}/
```

Các file quan trọng gồm:

| Tài nguyên | Vai trò |
|---|---|
| `index.html` | Trang khởi tạo Swagger UI và vị trí gắn CSS/JavaScript |
| `swagger-ui.css` | Kiểu dáng mặc định của giao diện |
| `swagger-ui-bundle.js` | Phần triển khai giao diện và logic Swagger UI |
| `swagger-ui-standalone-preset.js` | Các thành phần preset, gồm top bar/layout mặc định |
| `favicon-32x32.png` | Biểu tượng tab trình duyệt |
| Các file `.map` | Source map phục vụ debug JavaScript/CSS |

Không nên chỉnh sửa trực tiếp nội dung WebJar trong thư viện đã tải về hoặc thay toàn bộ bundle JavaScript chỉ để thay đổi CSS. Những file này thuộc phiên bản Swagger UI được springdoc đóng gói; nâng dependency có thể thay cấu trúc HTML, selector CSS, API plugin hoặc đường dẫn tài nguyên.

Springdoc cung cấp extension point `SwaggerIndexPageTransformer` để biến đổi tài nguyên trước khi gửi cho trình duyệt. Có thể dùng extension point này để thêm link stylesheet, script hoặc thay đổi một phần tài nguyên gốc mà vẫn giữ các xử lý mặc định của springdoc.

## 6. Thêm CSS riêng bằng static resource

Đặt stylesheet riêng trong static resources của ứng dụng:

```text
src/
└── main/
    └── resources/
        └── static/
            └── docs-assets/
                └── swagger-ui/
                    └── custom.css
```

Ví dụ nội dung `custom.css`:

```css
/* Điều chỉnh giao diện theo bộ nhận diện của ứng dụng. */
.swagger-ui .topbar {
    background: #17324d;
}

.swagger-ui .info .title {
    font-weight: 700;
}

.swagger-ui .opblock-tag {
    border-bottom-width: 2px;
}
```

Với cấu hình static resource mặc định, file được phục vụ tại `/docs-assets/swagger-ui/custom.css`. Dùng một prefix riêng như `docs-assets` để tránh trùng với resource handler `/swagger-ui/**` mà springdoc đăng ký cho WebJar. Nếu ứng dụng thay đổi `spring.web.resources.static-locations`, đường dẫn truy cập có thể khác.

Chỉ cần stylesheet này được phục vụ thành công là chưa đủ; trang Swagger UI còn phải nạp nó. Có thể thêm một thẻ `<link>` vào `index.html` thông qua transformer ở phần tiếp theo.

## 7. Dùng SwaggerIndexPageTransformer trong Spring Web MVC

Ví dụ dưới đây dành cho Spring Boot 3/4 với springdoc 2.x/3.x và Web MVC. Các import thuộc dòng springdoc 2.x/3.x; hãy đối chiếu API của đúng dependency nếu dùng phiên bản khác.

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import jakarta.servlet.http.HttpServletRequest;

import org.springdoc.core.properties.SwaggerUiConfigParameters;
import org.springdoc.core.properties.SwaggerUiConfigProperties;
import org.springdoc.core.properties.SwaggerUiOAuthProperties;
import org.springdoc.webmvc.ui.SwaggerIndexPageTransformer;
import org.springdoc.webmvc.ui.SwaggerIndexTransformer;
import org.springdoc.webmvc.ui.SwaggerWelcomeCommon;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.Resource;
import org.springframework.web.servlet.resource.ResourceTransformerChain;
import org.springframework.web.servlet.resource.TransformedResource;

@Configuration
class SwaggerUiResourceConfiguration {

    @Bean
    SwaggerIndexTransformer swaggerIndexTransformer(
        SwaggerUiConfigProperties swaggerUiConfig,
        SwaggerUiOAuthProperties swaggerUiOAuthProperties,
        SwaggerUiConfigParameters swaggerUiConfigParameters,
        SwaggerWelcomeCommon swaggerWelcomeCommon
    ) {
        return new SwaggerIndexPageTransformer(
            swaggerUiConfig,
            swaggerUiOAuthProperties,
            swaggerUiConfigParameters,
            swaggerWelcomeCommon
        ) {
            @Override
            public Resource transform(
                HttpServletRequest request,
                Resource resource,
                ResourceTransformerChain transformerChain
            ) throws IOException {
                // Giữ nguyên các bước mà springdoc cần để tạo trang Swagger UI.
                Resource transformed = super.transform(request, resource, transformerChain);

                if (!"index.html".equals(resource.getFilename())) {
                    return transformed;
                }

                String html;
                try (InputStream input = transformed.getInputStream()) {
                    html = new String(input.readAllBytes(), StandardCharsets.UTF_8);
                }

                String cssUrl = request.getContextPath() + "/docs-assets/swagger-ui/custom.css";
                String cssLink = "<link rel=\"stylesheet\" href=\""
                    + cssUrl + "\">";

                if (!html.contains(cssUrl)) {
                    html = html.replace("</head>", cssLink + "</head>");
                }

                return new TransformedResource(
                    transformed,
                    html.getBytes(StandardCharsets.UTF_8)
                );
            }
        };
    }
}
```

Điểm quan trọng trong ví dụ:

1. Bean thay thế transformer mặc định thông qua extension point của springdoc.
2. Gọi `super.transform(...)` trước khi chỉnh HTML để giữ các URL và cấu hình Swagger UI do springdoc chèn vào trang.
3. Chỉ sửa `index.html`; các tài nguyên khác tiếp tục dùng xử lý mặc định.
4. Đường dẫn CSS được thêm `request.getContextPath()` để hoạt động khi ứng dụng có servlet context path.
5. Dùng UTF-8 tường minh khi đọc và ghi HTML.
6. Kiểm tra thẻ link trước khi chèn để tránh thêm lặp nếu transformer được gọi nhiều lần.

Nếu ứng dụng đặt Swagger UI sau reverse proxy có prefix, cần cấu hình forwarded headers đáng tin cậy và kiểm tra URL thực tế mà trình duyệt nhận được. `getContextPath()` chỉ phản ánh servlet context path; nó không tự suy ra mọi prefix do proxy thêm vào.

## 8. Tùy chỉnh CSS trực tiếp bằng cách biến đổi stylesheet

Nếu không muốn thêm file CSS riêng, có thể biến đổi `swagger-ui.css` và nối phần CSS của ứng dụng vào cuối nội dung. Cách này vẫn dùng transformer nhưng áp dụng cho tài nguyên CSS:

```java
if ("swagger-ui.css".equals(resource.getFilename())) {
    String css;
    try (InputStream input = resource.getInputStream()) {
        css = new String(input.readAllBytes(), StandardCharsets.UTF_8);
    }

    String customCss = "\n"
        + "/* Application overrides */\n"
        + ".swagger-ui .topbar { background: #17324d; }\n"
        + ".swagger-ui .info .title { font-weight: 700; }\n";

    return new TransformedResource(
        resource,
        (css + customCss).getBytes(StandardCharsets.UTF_8)
    );
}
```

Đoạn code là phần xử lý thay thế cho nhánh `index.html` trong transformer trước đó; không khai báo thêm một bean transformer thứ hai nếu ứng dụng chỉ cần một transformer. Có thể xử lý cả `index.html` và `swagger-ui.css` trong cùng một phương thức `transform` bằng các nhánh điều kiện riêng.

Nối CSS vào cuối stylesheet gốc giúp ghi đè selector mặc định, nhưng vẫn phụ thuộc cấu trúc class CSS của Swagger UI. Sau khi nâng phiên bản WebJar, cần kiểm tra selector còn tồn tại và thứ tự stylesheet vẫn đúng. Không dùng thay thế chuỗi chung như `css.replace("old", "new")` trên toàn bundle vì có thể vô tình thay đổi nội dung không liên quan.

## 9. Thêm JavaScript, favicon hoặc đổi tiêu đề trang

Nếu cần JavaScript riêng, đặt file trong static resources, ví dụ:

```text
src/main/resources/static/docs-assets/swagger-ui/custom.js
```

Sau đó thêm thẻ script vào HTML đã được springdoc biến đổi, tương tự cách chèn stylesheet:

```java
String jsUrl = request.getContextPath() + "/docs-assets/swagger-ui/custom.js";
String scriptTag = "<script defer src=\"" + jsUrl + "\"></script>";
html = html.replace("</body>", scriptTag + "</body>");
```

Đoạn mã trên là phần bổ sung vào nhánh xử lý `index.html` trong transformer. Đảm bảo chỉ chèn một lần và đặt script sau khi các phần tử Swagger UI cần thao tác đã được tạo, hoặc dùng sự kiện/plugin chính thức thay vì truy cập DOM quá sớm.

Favicon có thể được thêm bằng cách cập nhật thẻ `link rel="icon"` trong `index.html` để trỏ tới file trong static resources. Có thể đổi tiêu đề bằng cách sửa phần tử `<title>` trong HTML, nhưng nên kiểm tra lại markup sau mỗi lần nâng Swagger UI vì mẫu HTML có thể thay đổi.

Không nhúng token, client secret, mật khẩu hoặc dữ liệu môi trường vào JavaScript được phục vụ công khai. Mọi script chạy trong trang Swagger UI có thể đọc DOM và thực hiện request theo quyền của phiên người dùng. Chỉ nạp script tin cậy, ưu tiên tài nguyên same-origin và tuân thủ Content Security Policy của ứng dụng.

## 10. Tùy chỉnh trang khởi tạo mà không làm mất cấu hình springdoc

`index.html` không chỉ là một trang HTML tĩnh. Springdoc dùng transformer để bổ sung cấu hình như URL tài liệu, config URL, OAuth settings và các tham số Swagger UI. Nếu thay thế trang này bằng một bản sao tự viết mà không tái tạo các bước cấu hình, giao diện có thể không biết tải OpenAPI document nào.

Khi cần thay đổi trang:

- Ưu tiên mở rộng `SwaggerIndexPageTransformer` và gọi `super.transform(...)`.
- Chỉ thay các đoạn HTML cần thiết, chẳng hạn title, link CSS, script hoặc favicon.
- Không xóa phần khởi tạo `SwaggerUIBundle` hoặc cấu hình được springdoc tạo.
- Nếu cần layout/plugin riêng, bảo đảm plugin được đăng ký trong cấu hình khởi tạo và component layout có tên khớp với `springdoc.swagger-ui.layout`.
- Kiểm tra URL `configUrl` và URL OpenAPI sau khi triển khai dưới context path hoặc reverse proxy.

Thuộc tính `layout` chỉ chọn tên component đã có trong plugin system; đặt `layout: CustomLayout` không tự tạo component đó. Muốn có layout riêng, phải cung cấp plugin JavaScript tương ứng và bảo đảm plugin được nạp trước khi Swagger UI khởi tạo.

## 11. Khác biệt giữa Web MVC và WebFlux

Transformer trong ví dụ ở trên là servlet-based. Không dùng nguyên class hoặc chữ ký method đó cho WebFlux.

| Nội dung | Web MVC | WebFlux |
|---|---|---|
| Transformer | `org.springdoc.webmvc.ui.SwaggerIndexPageTransformer` | `org.springdoc.webflux.ui.SwaggerIndexPageTransformer` |
| Request context | `HttpServletRequest` | `ServerWebExchange` |
| Chữ ký transform | Trả về `Resource` | Trả về `Mono<Resource>` |
| Resource transformer chain | `org.springframework.web.servlet.resource.ResourceTransformerChain` | `org.springframework.web.reactive.resource.ResourceTransformerChain` |
| Starter UI | `springdoc-openapi-starter-webmvc-ui` | `springdoc-openapi-starter-webflux-ui` |

Với WebFlux, cần viết transformer theo reactive API, đọc nội dung resource trong flow phù hợp và trả về `Mono<Resource>`. Không chặn event loop bằng thao tác I/O blocking hoặc gọi `block()` trong transformer. Hãy dùng ví dụ/demo đúng phiên bản WebFlux của springdoc khi triển khai.

## 12. Lưu ý riêng theo major version

### springdoc 1.x

Springdoc 1.x dùng các artifact cũ, ví dụ `springdoc-openapi-ui`, và một số lớp cấu hình nằm trong package `org.springdoc.core` thay vì `org.springdoc.core.properties`. Phiên bản 1.8.0 là bản open-source cuối hỗ trợ dòng Spring Boot 2.x/1.x. Không sao chép import của v2/v3 sang dự án 1.x mà không đối chiếu Javadoc và mã nguồn đúng phiên bản.

### springdoc 2.x

Springdoc 2.x dành cho Spring Boot 3. Các artifact UI dùng tên starter, chẳng hạn `springdoc-openapi-starter-webmvc-ui`. Một số package đã đổi so với v1, ví dụ `SwaggerUiConfigProperties`, `SwaggerUiOAuthProperties` và `SwaggerUiConfigParameters` thuộc `org.springdoc.core.properties`; `GroupedOpenApi` thuộc `org.springdoc.core.models`.

Ví dụ transformer Web MVC trong bài sử dụng cấu trúc API của dòng 2.x. Dù các class có tên tương tự, hãy kiểm tra đúng minor version nếu constructor hoặc dependency thay đổi.

### springdoc 3.x

Springdoc 3.x dành cho Spring Boot 4. Starter UI tiếp tục dùng tên `springdoc-openapi-starter-webmvc-ui` hoặc `springdoc-openapi-starter-webflux-ui`. Tài liệu hiện hành có ví dụ `SwaggerIndexPageTransformer` với bốn dependency cấu hình như trong ví dụ Web MVC ở trên. Dù vậy, các extension point nội bộ có thể thay đổi giữa minor version; khi nâng cấp, compile và kiểm tra lại transformer thay vì chỉ giữ nguyên import cũ.

Một số bản mới cũng thay đổi cách xử lý cache và biến đổi trang theo từng request. Nếu transformer chèn giá trị riêng cho từng request, chẳng hạn CSP nonce, cần xác minh response không bị cache nội dung đã biến đổi của request trước. Không dùng một transformer singleton để lưu nonce hoặc dữ liệu người dùng trong field dùng chung giữa các request.

## 13. Những thuộc tính cấu hình không nên tự suy đoán

Swagger UI có nhiều option trong tài liệu upstream, nhưng không phải option nào cũng có một property tương ứng trong `springdoc.swagger-ui`. Hãy kiểm tra bảng properties của đúng phiên bản springdoc trước khi thêm key vào YAML.

Một số điểm dễ nhầm:

- `springdoc.swagger-ui.layout` chọn layout component có sẵn; nó không tự nạp file HTML tùy ý.
- `springdoc.swagger-ui.url` trỏ tới một OpenAPI document; nó không phải URL CSS.
- `springdoc.swagger-ui.urls` tạo danh sách tài liệu để chọn; nó không phải danh sách asset.
- `springdoc.swagger-ui.path` đổi route của trang UI; nó không đổi đường dẫn `/v3/api-docs`.
- `springdoc.swagger-ui.enabled=false` tắt UI; `springdoc.api-docs.enabled=false` mới tắt endpoint tài liệu JSON/YAML.
- Không giả định `springdoc.swagger-ui.custom-css-url`, `custom-js-url` hoặc `custom-favicon` là property được springdoc hỗ trợ nếu bảng cấu hình của phiên bản đang dùng không liệt kê chúng. Với CSS/JS tùy chỉnh, sử dụng static resources và transformer.
- `query-config-enabled` cho phép ghi đè một số cấu hình qua query string. Đây là tùy chọn legacy có cảnh báo bảo mật; giữ tắt trừ khi đã đánh giá rõ nhu cầu và rủi ro.

Nếu một property không được nhận diện, ứng dụng có thể vẫn khởi động mà không áp dụng thay đổi. Hãy kiểm tra `/v3/api-docs/swagger-config`, log startup và tài liệu cấu hình thay vì chỉ dựa vào việc YAML hợp lệ.

## 14. Bảo vệ Swagger UI và tài nguyên mở rộng

Khi thêm CSS hoặc JavaScript riêng, các file đó trở thành static endpoint của ứng dụng. Nếu Swagger UI được bảo vệ bằng Spring Security, cần quyết định rõ ai được truy cập:

- Trang UI, tài liệu JSON/YAML và tài nguyên CSS/JS cần cùng chính sách truy cập phù hợp.
- Không mở public `/v3/api-docs/**` chỉ vì stylesheet không tải được; kiểm tra matcher của đúng tài nguyên trước.
- Nếu tài liệu chỉ dành cho developer nội bộ, yêu cầu authentication/role cho UI và OpenAPI endpoint.
- Không đưa client secret vào `application.yml` hoặc JavaScript phía trình duyệt; OAuth client secret có thể bị người dùng đọc từ source hoặc network.
- Nếu dùng CSP, bảo đảm `style-src`, `script-src` và `font-src` cho phép các tài nguyên thực sự được nạp. Ưu tiên file cùng origin và tránh inline script nếu chính sách yêu cầu nonce/hash.

Ví dụ matcher minh họa khi chỉ nhóm developer được xem tài liệu:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(
        "/docs/swagger-ui.html",
        "/swagger-ui/**",
        "/docs-assets/swagger-ui/**",
        "/v3/api-docs/**"
    ).hasRole("DEVELOPER")
    .anyRequest().authenticated()
);
```

Điều chỉnh danh sách URL theo `springdoc.swagger-ui.path`, `springdoc.api-docs.path`, context path và các group thực tế. Nếu route được đổi tên, security matcher cũ có thể khiến UI trả 401/403 dù API backend vẫn hoạt động.

## 15. Kiểm tra sau khi mở rộng giao diện

Sau khi thêm cấu hình hoặc transformer, kiểm tra cả giao diện lẫn các endpoint dữ liệu:

1. Trang Swagger UI trả về HTML hoặc redirect hợp lệ theo cấu hình.
2. `swagger-config` tải được và chứa đúng URL OpenAPI.
3. `/v3/api-docs` hoặc endpoint group trả về OpenAPI JSON hợp lệ.
4. File CSS/JS/favicon riêng trả về HTTP 200, đúng Content-Type và không bị Spring Security chặn.
5. HTML cuối cùng có link CSS/script đúng một lần.
6. Browser DevTools không báo lỗi 404, CSP, MIME type hoặc JavaScript exception.
7. Các chức năng như Authorize, Try it out, chọn group, request/response và schema vẫn hoạt động.
8. Trang vẫn hoạt động khi có context path, reverse proxy và profile môi trường thực tế.
9. Tải lại trang sau khi xóa cache để kiểm tra stylesheet mới; khi phát hành asset mới, dùng tên file fingerprint hoặc chính sách cache phù hợp.

Ví dụ kiểm tra static resource và OpenAPI bằng MockMvc:

```java
@SpringBootTest
@AutoConfigureMockMvc
class SwaggerUiResourceTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void servesCustomStylesheet() throws Exception {
        mockMvc.perform(get("/docs-assets/swagger-ui/custom.css"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith("text/css"));
    }

    @Test
    void keepsOpenApiDocumentAvailable() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON
            ));
    }
}
```

Nếu security bảo vệ các endpoint tài liệu, test cần cung cấp principal/authority phù hợp hoặc kiểm tra riêng response 401/403 theo chính sách. Đường dẫn trong ví dụ là mặc định; thay bằng path đã cấu hình trong ứng dụng.

## 16. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| CSS file trả 404 | Đặt file sai classpath hoặc URL không khớp static resource mapping | Kiểm tra `src/main/resources/static` và URL trong thẻ link |
| CSS tải 200 nhưng không áp dụng | Selector không còn tồn tại, CSS bị nạp trước stylesheet gốc hoặc độ ưu tiên thấp | Kiểm tra thứ tự `<link>`, selector và specificity |
| Swagger UI hiện trang nhưng không có API | Transformer thay `index.html` và làm mất cấu hình mặc định | Gọi `super.transform(...)` rồi mới sửa nội dung |
| Swagger UI báo lỗi tải config | `configUrl` sai, context path/proxy prefix không khớp hoặc security chặn | Kiểm tra `/v3/api-docs/swagger-config`, forwarded headers và security matcher |
| Đổi path UI làm trang chủ mất | Swagger UI chiếm route welcome page ở root | Dùng `springdoc.swagger-ui.path` riêng |
| CSS/JS bị chặn bởi CSP | `style-src` hoặc `script-src` không cho phép nguồn tài nguyên | Phục vụ asset same-origin và cập nhật CSP có kiểm soát |
| JavaScript chạy hai lần | Transformer chèn thẻ script lặp hoặc bean bị cấu hình chồng | Kiểm tra idempotency và chỉ đăng ký một transformer |
| Không compile được transformer sau khi nâng major | Package hoặc chữ ký API thay đổi | Đối chiếu migration guide/Javadoc đúng version và Web MVC/WebFlux |
| CSS cũ vẫn hiển thị sau deploy | Browser hoặc proxy cache stylesheet | Dùng fingerprint filename, cache-control phù hợp và hard reload |
| Swagger UI không mở dưới reverse proxy | HTML dùng URL tuyệt đối thiếu context/proxy prefix | Cấu hình forwarded headers và kiểm tra URL sinh ra trong HTML/config |
| UI bị 403 nhưng file CSS hoạt động | Security matcher của UI, swagger-config hoặc OpenAPI không đồng bộ | Bảo vệ đúng tập endpoint và kiểm tra request bị từ chối |

## 17. Quy trình lựa chọn cách mở rộng

Khi cần tùy chỉnh Swagger UI trong một dự án Spring Boot, thực hiện theo thứ tự:

1. Xác định Boot version, springdoc major/minor và Web MVC hay WebFlux.
2. Chọn đúng starter UI và xác nhận phiên bản trong compatibility matrix.
3. Dùng `springdoc.swagger-ui.*` cho path, layout, URL tài liệu và các option có trong bảng cấu hình.
4. Đặt CSS/JS/favicon riêng trong static resources của ứng dụng.
5. Nếu cần nạp asset vào trang, mở rộng `SwaggerIndexPageTransformer` đúng stack và version; giữ xử lý mặc định bằng `super.transform(...)`.
6. Chỉ biến đổi resource cần thiết; tránh thay toàn bộ WebJar bundle.
7. Kiểm tra context path, reverse proxy, CSP và security matcher.
8. Kiểm tra HTML, asset, swagger-config, OpenAPI JSON/YAML và browser console.
9. Sau mỗi lần nâng springdoc/Swagger UI, kiểm tra lại transformer và selector CSS.

Các thuộc tính cấu hình phù hợp cho những thay đổi giao diện có sẵn; transformer và static resources phục vụ các yêu cầu sâu hơn. Chọn đúng extension point theo phiên bản giúp giao diện tùy chỉnh vẫn giữ khả năng tải OpenAPI, xác thực và tương tác API mà springdoc đã tích hợp.

## 18. Tài liệu tham khảo

- [Springdoc OpenAPI v2 Documentation](https://springdoc.org/v2/): Swagger UI configuration, custom static resources và migration từ v1.
- [Springdoc OpenAPI v2 – Configuration Properties](https://springdoc.org/v2/properties.html): bảng thuộc tính cấu hình của springdoc 2.x.
- [Springdoc OpenAPI – Current Documentation](https://springdoc.org/): tài liệu hiện hành và compatibility matrix cho các dòng Spring Boot mới.
- [Swagger UI – Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/): các option chính thức, plugin system và cách cấu hình giao diện.
- [Spring Framework – Static Resources](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html): cách phục vụ static resource trong Spring MVC.
