# Chọn starter và thuộc tính Scalar theo nhánh Springdoc hỗ trợ

Springdoc có nhiều starter khác nhau cho Spring Web MVC, Spring WebFlux, OpenAPI endpoint, Swagger UI và Scalar. Chọn sai starter có thể khiến ứng dụng thiếu giao diện tài liệu, nạp nhầm web stack hoặc kéo theo các dependency không cần thiết.

Scalar là giao diện tham khảo API có khả năng đọc OpenAPI document và cung cấp REST API client ngay trong trình duyệt. Scalar không thay thế bộ sinh OpenAPI của Springdoc: controller, annotation, DTO và cấu hình vẫn được Springdoc dùng để tạo đặc tả JSON/YAML. Scalar chỉ là một cách hiển thị và tương tác với đặc tả đó, tương tự vai trò của Swagger UI.

Để chọn đúng dependency, cần xác định lần lượt:

1. Ứng dụng dùng Spring Web MVC hay Spring WebFlux.
2. Chỉ cần OpenAPI JSON/YAML hay cần giao diện tài liệu.
3. Nếu cần giao diện, muốn Swagger UI, Scalar hay cả hai.
4. Dự án đang dùng Spring Boot 2, 3 hay 4 và nhánh Springdoc tương ứng.

## 1. Phân biệt Springdoc API, Swagger UI và Scalar

Ba thành phần có trách nhiệm khác nhau:

| Thành phần | Trách nhiệm | Endpoint thường gặp |
| --- | --- | --- |
| Springdoc API | Tạo và phục vụ OpenAPI document từ ứng dụng | /v3/api-docs, /v3/api-docs.yaml |
| Swagger UI | Đọc OpenAPI document và hiển thị giao diện tương tác | /swagger-ui.html |
| Scalar | Đọc OpenAPI document và hiển thị API Reference cùng REST client | /scalar |

OpenAPI document là hợp đồng dùng chung. Có thể chỉ xuất document để pipeline hoặc developer portal khác sử dụng mà không cần nhúng UI vào ứng dụng. Cũng có thể dùng một trong hai giao diện hoặc cung cấp cả hai nếu có lý do vận hành rõ ràng.

Không nên thêm starter UI chỉ vì muốn có endpoint JSON. Starter API-only đã đủ để tạo OpenAPI document và giảm phần tài nguyên giao diện không cần thiết.

## 2. Chọn nhánh Springdoc theo Spring Boot

Trước khi chọn artifact, hãy kiểm tra phiên bản Spring Boot trong dự án. Quy tắc tổng quát:

| Spring Boot | Nhánh Springdoc | Ghi chú |
| --- | --- | --- |
| 4.x | Springdoc 3.x | Dùng tài liệu và starter của nhánh 3.x |
| 3.x | Springdoc 2.x | Dùng tài liệu và starter của nhánh 2.x |
| 2.x hoặc 1.x | Springdoc 1.x | Nhánh legacy, artifact dùng tên cũ |

Tại tài liệu nhánh v2, Springdoc 2.10.0 là phiên bản được dùng trong các ví dụ module. Bảng tương thích chi tiết còn phụ thuộc minor version của Spring Boot; ví dụ Boot 3.5.x dùng Springdoc 2.8.x đến 2.10.x, Boot 3.4.x dùng 2.7.x đến 2.8.x, còn Boot 3.3.x dùng 2.6.x.

Springdoc v1.8.0 là bản legacy cuối cùng được tài liệu v1 nêu cho Spring Boot 1.x/2.x và đã kết thúc hỗ trợ open-source. Không lấy artifact v1 rồi ghép với starter v2/v3. Tương tự, không dùng starter Springdoc 3.x của Boot 4 cho ứng dụng Boot 3 chỉ vì 3.x là nhánh mới hơn.

## 3. Chọn theo Web MVC hay WebFlux

Springdoc cung cấp một cặp artifact tương ứng cho từng web stack:

| Nền tảng ứng dụng | API-only | Swagger UI | Scalar |
| --- | --- | --- | --- |
| Spring Web MVC | springdoc-openapi-starter-webmvc-api | springdoc-openapi-starter-webmvc-ui | springdoc-openapi-starter-webmvc-scalar |
| Spring WebFlux | springdoc-openapi-starter-webflux-api | springdoc-openapi-starter-webflux-ui | springdoc-openapi-starter-webflux-scalar |

Các artifact trong bảng áp dụng cho nhánh starter Springdoc v2/v3. Chọn theo web stack thực tế:

- Dự án dùng spring-boot-starter-web thường chọn biến thể webmvc.
- Dự án dùng spring-boot-starter-webflux thường chọn biến thể webflux.
- Không thêm đồng thời starter Web MVC và WebFlux chỉ để có cả hai loại UI.

Web MVC và WebFlux có mô hình request handling khác nhau. Chọn starter tương ứng giúp Springdoc đăng ký đúng tích hợp cho controller, handler mapping và resource của ứng dụng.

## 4. Bảng quyết định starter

| Nhu cầu | Starter nên chọn |
| --- | --- |
| Chỉ xuất OpenAPI JSON/YAML cho CI hoặc portal khác | webmvc-api hoặc webflux-api |
| Có giao diện Swagger UI | webmvc-ui hoặc webflux-ui |
| Chỉ có giao diện Scalar | webmvc-scalar hoặc webflux-scalar |
| Muốn cả Swagger UI và Scalar | Starter Swagger UI/API cùng Scalar standalone integration; xem điều kiện phiên bản ở phần sau |

Ví dụ: một ứng dụng Spring MVC chỉ cần sinh OpenAPI document để pipeline tải về thì không cần starter UI. Nếu đội phát triển muốn mở giao diện ngay trong ứng dụng, chọn starter UI phù hợp với sản phẩm giao diện mà đội muốn dùng.

## 5. Dependency cho Spring Boot 3 và Springdoc 2.x

Với Spring Boot 3 sử dụng Spring Web MVC và chỉ cần Scalar, có thể khai báo:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-scalar</artifactId>
    <version>2.10.0</version>
</dependency>
~~~

Với Spring WebFlux, thay artifact bằng:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webflux-scalar</artifactId>
    <version>2.10.0</version>
</dependency>
~~~

Nếu chỉ cần OpenAPI JSON/YAML trên Web MVC:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-api</artifactId>
    <version>2.10.0</version>
</dependency>
~~~

Nếu cần Swagger UI trên Web MVC:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>2.10.0</version>
</dependency>
~~~

Các ví dụ trên dùng phiên bản Springdoc 2.10.0 để minh họa nhánh Boot 3. Hãy chọn minor version tương thích với minor version Spring Boot trong dự án thay vì nâng riêng Springdoc lên một phiên bản không có trong compatibility matrix.

## 6. Dependency cho Spring Boot 4 và Springdoc 3.x

Với Spring Boot 4, dùng starter của nhánh Springdoc 3.x. Tên artifact giữ cùng quy tắc theo web stack và UI:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-scalar</artifactId>
    <version>3.2.0</version>
</dependency>
~~~

Với WebFlux, dùng springdoc-openapi-starter-webflux-scalar. Nếu chỉ cần API document hoặc Swagger UI, chọn các artifact webmvc-api/webflux-api hoặc webmvc-ui/webflux-ui tương ứng.

Ví dụ dùng 3.2.0 theo tài liệu nhánh hiện hành tại thời điểm biên soạn. Không dùng số phiên bản này cho dự án Spring Boot 3; Boot 3 cần nhánh Springdoc 2.x.

## 7. Quản lý phiên bản dependency bằng BOM

Springdoc cung cấp BOM để đồng bộ phiên bản các module. BOM có từ Springdoc 2.8.7; nên dùng khi dự án khai báo nhiều artifact Springdoc:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springdoc</groupId>
            <artifactId>springdoc-openapi-bom</artifactId>
            <version>2.10.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-scalar</artifactId>
    </dependency>
</dependencies>
~~~

Với nhánh Springdoc 3.x, dùng BOM 3.x cùng nhánh. Không trộn BOM 2.x với starter 3.x hoặc ngược lại.

Scalar standalone integration là dependency riêng của Scalar, không thuộc BOM Springdoc. Nếu dự án dùng nó để kết hợp hai UI, hãy quản lý version Scalar độc lập và kiểm tra dependency tree để tránh nhiều phiên bản Scalar cùng xuất hiện.

## 8. Starter Scalar riêng của Springdoc

Nếu chỉ muốn Scalar UI, chọn starter chuyên dụng:

- springdoc-openapi-starter-webmvc-scalar cho Spring Web MVC.
- springdoc-openapi-starter-webflux-scalar cho Spring WebFlux.

Starter này tích hợp Scalar với Spring Boot và Springdoc. OpenAPI document vẫn do Springdoc phục vụ, thường tại /v3/api-docs; trang Scalar thường có tại /scalar.

Ví dụ luồng truy cập:

~~~text
Browser
   |
   v
GET /scalar
   |
   v
Scalar UI được Spring Boot phục vụ
   |
   v
GET /v3/api-docs
   |
   v
Springdoc trả OpenAPI JSON
   |
   v
Scalar render API Reference
~~~

Không cần thêm Scalar standalone integration khi đã chọn springdoc-openapi-starter-webmvc-scalar hoặc springdoc-openapi-starter-webflux-scalar. Hai hướng tích hợp này có vai trò khác nhau; ghép cả hai mà không có chủ đích có thể tạo auto-configuration hoặc endpoint trùng lặp.

## 9. Cấu hình Scalar bằng application.yml

Các thuộc tính của Scalar dùng prefix scalar, không phải springdoc.scalar. Ví dụ cấu hình cơ bản:

~~~yaml
springdoc:
  api-docs:
    path: /v3/api-docs

scalar:
  enabled: true
  path: /scalar
  url: /v3/api-docs
  theme: deepSpace
  layout: modern
  dark-mode: false
  hide-search: false
  hide-models: false
  hide-test-request-button: false
  document-download-type: both
~~~

Ý nghĩa các thuộc tính:

| Thuộc tính | Mục đích |
| --- | --- |
| scalar.enabled | Bật hoặc tắt Scalar UI |
| scalar.path | Đường dẫn trang API Reference |
| scalar.url | URL của OpenAPI document mà Scalar cần đọc |
| scalar.theme | Chủ đề màu của giao diện |
| scalar.layout | Bố cục modern hoặc classic |
| scalar.dark-mode | Trạng thái dark mode ban đầu |
| scalar.hide-search | Ẩn hoặc hiện ô tìm kiếm |
| scalar.hide-models | Ẩn hoặc hiện phần schema/model |
| scalar.hide-test-request-button | Ẩn hoặc hiện chức năng gửi request thử |
| scalar.document-download-type | Chọn tải JSON, YAML, cả hai hoặc không hiển thị nút tải |

Giá trị cụ thể và tập enum được hỗ trợ phụ thuộc phiên bản Scalar đi cùng starter. Nếu một thuộc tính không được binding, kiểm tra phiên bản dependency và tên property trong tài liệu của đúng bản Scalar đang dùng.

## 10. Đổi đường dẫn OpenAPI và đường dẫn Scalar

Hai endpoint có mục đích riêng:

- springdoc.api-docs.path đổi URL của OpenAPI JSON.
- scalar.path đổi URL trang Scalar UI.

Ví dụ:

~~~yaml
springdoc:
  api-docs:
    path: /openapi

scalar:
  path: /reference
  url: /openapi
~~~

Sau khi đổi cấu hình, URL dự kiến:

| Nội dung | URL |
| --- | --- |
| Scalar UI | /reference |
| OpenAPI JSON | /openapi |
| OpenAPI YAML | /openapi.yaml |

Không dùng springdoc.swagger-ui.path để đổi đường dẫn Scalar. Thuộc tính đó dành cho Swagger UI. Nếu dùng Scalar, điều chỉnh scalar.path.

Khi ứng dụng có server.servlet.context-path, ví dụ /catalog, hãy kiểm tra URL cuối cùng trong trình duyệt. Scalar phải tải đúng OpenAPI document có context path, chẳng hạn /catalog/openapi. URL tương đối hoặc tuyệt đối cần được chọn theo cách ứng dụng được reverse proxy công bố.

## 11. Kết hợp Swagger UI và Scalar từ Springdoc 2.10.0

Nếu muốn cung cấp cả hai giao diện trong ứng dụng Spring MVC, có thể dùng starter Swagger UI của Springdoc và Scalar standalone integration:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>2.10.0</version>
</dependency>

<dependency>
    <groupId>com.scalar.maven</groupId>
    <artifactId>scalar-webmvc</artifactId>
    <version>${scalar.version}</version>
</dependency>
~~~

Với WebFlux, dùng springdoc-openapi-starter-webflux-ui cùng com.scalar.maven:scalar-webflux.

Từ Springdoc 2.10.0, khi ứng dụng dùng một starter Springdoc khác (Swagger UI hoặc API-only) cùng Scalar standalone integration, Scalar standalone được bật mặc định. Có thể đặt scalar.enabled=false để tắt hoặc scalar.url để trỏ đến OpenAPI document; nếu không chỉ định URL, Scalar standalone có thể hiển thị tài liệu demo.

Ví dụ:

~~~yaml
scalar:
  enabled: true
  path: /scalar
  url: /v3/api-docs
~~~

Khi đó:

- Swagger UI thường ở /swagger-ui.html.
- Scalar UI ở /scalar.
- Cả hai đọc cùng OpenAPI document /v3/api-docs.

Đây là trường hợp dùng Scalar standalone integration. Không thêm springdoc-openapi-starter-webmvc-scalar vào cùng cấu hình này nếu mục tiêu chỉ là hai UI; hãy chọn một chiến lược tích hợp rõ ràng.

## 12. Kết hợp API-only với Scalar standalone

Một số ứng dụng muốn giữ backend ở mức chỉ phục vụ API document, còn UI có thể được thêm như một module tích hợp độc lập. Với Springdoc 2.10.0 trở lên, có thể kết hợp:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-api</artifactId>
    <version>2.10.0</version>
</dependency>

<dependency>
    <groupId>com.scalar.maven</groupId>
    <artifactId>scalar-webmvc</artifactId>
    <version>${scalar.version}</version>
</dependency>
~~~

Scalar standalone có thể được bật riêng và trỏ về endpoint OpenAPI của Springdoc. Cách này hữu ích khi không muốn dùng Swagger UI nhưng vẫn cần Scalar. Nếu chỉ cần Scalar, starter Springdoc chuyên dụng webmvc-scalar thường là lựa chọn đơn giản hơn.

## 13. Cấu hình nhiều OpenAPI document trong Scalar

Scalar có thể hiển thị nhiều tài liệu trong cùng giao diện thông qua cấu hình sources nếu phiên bản Scalar được tích hợp hỗ trợ thuộc tính này.

Ví dụ:

~~~yaml
scalar:
  enabled: true
  sources:
    - url: /v3/api-docs/public
      title: Public API
      slug: public
    - url: /v3/api-docs/partner
      title: Partner API
      slug: partner
~~~

Mỗi source là một OpenAPI document độc lập. Tên, slug và URL cần tương ứng với group endpoint thực tế do Springdoc tạo ra. Nếu cần chỉ định source mặc định, kiểm tra đúng tên thuộc tính mà phiên bản Scalar đang dùng hỗ trợ; các bản tích hợp khác nhau có thể dùng default hoặc isDefault.

Không khai báo scalar.url toàn cục nếu muốn mỗi source có URL riêng và frontend ưu tiên nội dung nguồn riêng. Sau khi cấu hình, kiểm tra document selector trong Scalar và quyền truy cập của từng endpoint group.

## 14. Cấu hình Scalar sau reverse proxy

Khi ứng dụng chạy sau reverse proxy, Scalar cần biết URL public để tải đúng OpenAPI document. Từ Springdoc 2.9.1 ở nhánh v2 và 3.1.1 ở nhánh v3, Scalar starter không còn tự đăng ký ForwardedHeaderFilter (Web MVC) hoặc ForwardedHeaderTransformer (WebFlux).

Nếu ứng dụng nằm sau proxy đáng tin cậy và cần xử lý Forwarded hoặc X-Forwarded-* headers, cấu hình Spring Boot:

~~~properties
server.forward-headers-strategy=framework
~~~

Chỉ bật cách xử lý forwarded headers khi hạ tầng đã cấu hình proxy đáng tin cậy để loại bỏ hoặc ghi đè header giả mạo từ client. Không để ứng dụng trực tiếp tin các giá trị Forwarded/X-Forwarded-* do mọi client bên ngoài gửi.

Sau khi cấu hình, kiểm tra:

1. Trang /scalar được mở bằng host và scheme public.
2. Scalar tải đúng URL OpenAPI document.
3. OpenAPI servers trong document trỏ đến địa chỉ API public phù hợp.
4. Request thử từ Scalar đi đến API server đúng host, port và context path.

Nếu trang Scalar tải được nhưng document báo 404, thường cần kiểm tra context path, api-docs.path, scalar.url và cấu hình proxy trước khi thay đổi starter.

## 15. Bảo vệ Scalar và OpenAPI bằng Spring Security

Scalar UI và OpenAPI document có thể tiết lộ endpoint, schema, server URL và ví dụ request. Với API nội bộ, nên bảo vệ cả UI lẫn document thay vì chỉ ẩn link giao diện.

Ví dụ:

~~~java
@Bean
SecurityFilterChain apiDocsSecurity(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/scalar", "/scalar/**").hasAuthority("DOCS_READ")
        .requestMatchers("/v3/api-docs", "/v3/api-docs/**", "/v3/api-docs.yaml")
            .hasAuthority("DOCS_READ")
        .anyRequest().authenticated()
    );
    return http.build();
}
~~~

Nếu dùng đường dẫn OpenAPI tùy chỉnh, cập nhật matcher tương ứng. Nếu có Swagger UI, bổ sung matcher cho /swagger-ui.html và /swagger-ui/**. Hãy kiểm tra cả swagger-config và static resources mà UI cần tải.

Không nên cho phép tất cả endpoint tài liệu truy cập công khai chỉ để Scalar hiển thị được. Nếu UI cần gọi OpenAPI document bằng browser, cả hai endpoint phải có chính sách xác thực phù hợp và trình duyệt phải gửi được credential theo thiết kế.

## 16. Scalar authentication và dữ liệu nhạy cảm

Scalar có thể hiển thị các lựa chọn xác thực dựa trên security scheme đã khai báo trong OpenAPI document. Tên scheme trong cấu hình Scalar phải khớp chính xác với tên scheme trong components.securitySchemes.

Ví dụ OpenAPI có HTTP bearer scheme tên BearerAuth thì Scalar phải tham chiếu đúng BearerAuth, không tự đặt một tên khác.

Không đặt access token, API key hoặc client secret thật vào cấu hình Scalar được gửi xuống trình duyệt. Giá trị được prefill trong giao diện có thể quan sát bởi người dùng có quyền mở trang. Tính năng prefill chỉ nên dùng cho môi trường phát triển/test với credential giả hoặc giới hạn phạm vi.

Scalar không thay thế Spring Security. Việc có nút Authorize hoặc Test Request trên UI không có nghĩa API runtime đã được bảo vệ. SecurityFilterChain, OAuth2 resource server và authorization policy của endpoint vẫn phải được cấu hình riêng.

## 17. Các thuộc tính Scalar nên chọn theo mục tiêu

Không cần bật mọi tùy chọn. Chọn các thuộc tính theo nhu cầu của người đọc tài liệu:

| Mục tiêu | Thuộc tính gợi ý | Lưu ý |
| --- | --- | --- |
| Đổi đường dẫn UI | scalar.path | Không phải springdoc.swagger-ui.path |
| Chỉ định OpenAPI document | scalar.url | Phải trỏ đến endpoint đang được phục vụ |
| Chọn giao diện sáng/tối | scalar.theme, scalar.dark-mode | Giá trị theme phụ thuộc phiên bản Scalar |
| Ẩn schema khỏi sidebar | scalar.hide-models | Chỉ thay đổi cách trình bày |
| Ẩn thanh tìm kiếm | scalar.hide-search | Không thay đổi nội dung OpenAPI |
| Ẩn nút gửi request | scalar.hide-test-request-button | Không thay thế authorization ở server |
| Chọn kiểu tải tài liệu | scalar.document-download-type | json, yaml, both hoặc none tùy phiên bản |
| Sắp xếp operation/tag | scalar.operation-sorter, scalar.tag-sorter | Kiểm tra giá trị enum của phiên bản |

Các property name có thể được Spring Boot relaxed binding chấp nhận ở dạng kebab-case hoặc camelCase. Tuy nhiên, nên dùng nhất quán một kiểu trong application.yml và tra tài liệu Scalar tương ứng với dependency đã khóa.

## 18. Những lỗi chọn starter thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không có /v3/api-docs | Chỉ thêm UI bên ngoài hoặc API endpoint bị tắt | Chọn starter API phù hợp và kiểm tra springdoc.api-docs.enabled |
| Không có /scalar | Dùng API-only hoặc Swagger UI starter nhưng chưa thêm Scalar integration | Chọn starter Scalar hoặc tích hợp scalar-webmvc/webflux theo version |
| Ứng dụng WebFlux nhưng thêm webmvc-scalar | Chọn nhầm web stack | Thay bằng webflux-scalar |
| Scalar hiển thị tài liệu demo | scalar.url chưa trỏ đến OpenAPI document | Cấu hình scalar.url đúng endpoint |
| Scalar báo 404 khi tải document | api-docs.path, context path hoặc proxy URL không khớp | Đối chiếu URL trong Network tab |
| Cả Swagger UI và Scalar không ổn định | Trộn Scalar starter chuyên dụng với standalone integration | Chọn một mô hình tích hợp; nếu cần cả hai dùng starter UI/API cùng Scalar standalone từ v2.10.0 |
| Dependency không tìm thấy | Dùng tên artifact v2/v3 trên nhánh v1 | Dùng đúng nhánh tương thích hoặc nâng cấp |
| Lỗi NoSuchMethodError/ClassNotFound | Các module Springdoc khác phiên bản hoặc dependency Scalar xung đột | Dùng BOM đúng nhánh và kiểm tra dependency tree |
| Host Scalar sai sau proxy | Forwarded headers không được xử lý hoặc không đáng tin cậy | Cấu hình proxy và server.forward-headers-strategy đúng cách |
| Scalar UI mở được nhưng request thử thất bại | API security, CORS hoặc server URL chưa đúng | Kiểm tra browser network, CORS và security policy |
| Thay theme không có hiệu lực | Giá trị theme không thuộc enum của Scalar version | Tra danh sách theme theo đúng version |

## 19. Kiểm tra sau khi thêm starter

Sau khi ứng dụng khởi động, kiểm tra lần lượt:

~~~bash
curl -i http://localhost:8080/v3/api-docs
curl -i http://localhost:8080/v3/api-docs.yaml
curl -I http://localhost:8080/scalar
~~~

Nếu dùng đường dẫn tùy chỉnh, thay các URL bằng giá trị trong cấu hình. Với Scalar UI, kiểm tra thêm request tải OpenAPI document trong tab Network của trình duyệt.

Các điều cần xác minh:

1. OpenAPI JSON trả HTTP 200 và có trường openapi, info, paths.
2. OpenAPI YAML trả đúng content type và nội dung tương ứng.
3. Scalar UI trả HTML và tải được JavaScript/CSS.
4. Scalar lấy đúng URL document, không lấy demo spec.
5. Các operation và schema hiển thị đúng.
6. Test Request gọi đúng API server và xử lý xác thực như mong muốn.
7. Khi bật Spring Security, người không có quyền không đọc được tài liệu nội bộ.

Có thể dùng integration test để xác minh các endpoint:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ApiDocumentationEndpointTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void openApiDocumentIsAvailable() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON
            ))
            .andExpect(jsonPath("$.openapi").exists())
            .andExpect(jsonPath("$.paths").exists());
    }

    @Test
    void scalarPageIsAvailable() throws Exception {
        mockMvc.perform(get("/scalar"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaType.TEXT_HTML));
    }
}
~~~

Test Scalar page có thể cần điều chỉnh theo cách resource handler và redirect được triển khai trong version đang dùng. Nếu trang trả redirect, kiểm tra Location header và follow redirect thay vì kết luận starter bị lỗi.

## 20. Checklist chọn starter và cấu hình Scalar

- [ ] Đã xác định Spring Boot version và nhánh Springdoc tương thích.
- [ ] Không dùng Springdoc 2.x cho Spring Boot 4 hoặc Springdoc 3.x cho Spring Boot 3.
- [ ] Đã xác định ứng dụng dùng Spring Web MVC hay WebFlux.
- [ ] Đã chọn API-only, Swagger UI hoặc Scalar theo nhu cầu.
- [ ] Artifact Scalar khớp web stack: webmvc-scalar hoặc webflux-scalar.
- [ ] Các module Springdoc dùng cùng một version hoặc BOM cùng nhánh.
- [ ] Không thêm đồng thời Scalar starter chuyên dụng và Scalar standalone integration nếu không có thiết kế rõ ràng.
- [ ] Nếu cần cả Swagger UI và Scalar, đã kiểm tra điều kiện tích hợp standalone từ Springdoc 2.10.0 trở lên.
- [ ] Các thuộc tính Scalar dùng prefix scalar, không nhầm với springdoc.swagger-ui.
- [ ] scalar.url trỏ đến đúng OpenAPI JSON document.
- [ ] scalar.path không xung đột với route ứng dụng.
- [ ] Đã kiểm tra context path, reverse proxy và forwarded headers.
- [ ] Security bảo vệ cả trang Scalar và OpenAPI document theo chính sách của hệ thống.
- [ ] Không đưa token hoặc secret thật vào cấu hình prefill hiển thị trên browser.
- [ ] Đã kiểm tra /v3/api-docs, /v3/api-docs.yaml và /scalar.

Chọn starter đúng bắt đầu từ web stack và nhu cầu giao diện, sau đó mới đến thuộc tính Scalar. Với Spring Boot 3 dùng Springdoc 2.x; với Boot 4 dùng Springdoc 3.x; nhánh v1 là legacy và dùng tên artifact cũ. Nếu chỉ cần Scalar, ưu tiên starter Scalar chuyên dụng của Springdoc. Nếu cần đồng thời Swagger UI và Scalar, dùng mô hình Scalar standalone theo hướng dẫn của đúng nhánh và phiên bản. Cuối cùng, xác minh URL OpenAPI, proxy và security để giao diện hiển thị đúng tài liệu mà không vô tình công khai hợp đồng nội bộ.

## Tài liệu tham khảo

- [Springdoc OpenAPI v2 — Modules và Scalar support](https://springdoc.org/v2/modules.html)
- [Springdoc OpenAPI v2 — Properties](https://springdoc.org/v2/properties.html)
- [Springdoc OpenAPI v2 — Migration từ v1](https://springdoc.org/v2/migrating-from-springdoc-v1.html)
- [Springdoc OpenAPI — Modules hiện hành](https://springdoc.org/modules.html)
- [Springdoc OpenAPI v1 — Legacy documentation](https://springdoc.org/v1/)
- [Scalar — Java integration](https://scalar.com/products/api-references/integrations/java)
