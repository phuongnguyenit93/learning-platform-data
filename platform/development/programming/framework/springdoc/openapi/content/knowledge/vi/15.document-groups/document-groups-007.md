# Đường dẫn đặc tả theo nhóm và lựa chọn nhóm trên Swagger UI

Một ứng dụng Spring Boot có thể cung cấp nhiều nhóm API với đối tượng sử dụng và phạm vi khác nhau. Ví dụ, ứng dụng quản lý đơn hàng có API công khai cho khách hàng, API quản trị cho nhân viên và API nội bộ cho các dịch vụ khác. Nếu đưa tất cả operation vào một tài liệu OpenAPI, người đọc khó tìm endpoint cần thiết và có thể nhìn thấy những phần không liên quan đến vai trò của họ.

Springdoc-openapi hỗ trợ tạo nhiều tài liệu đặc tả bằng `GroupedOpenApi`. Mỗi nhóm có tên riêng, tập endpoint được chọn và một đường dẫn tài liệu riêng. Swagger UI có thể hiển thị danh sách tài liệu để người dùng chọn nhóm cần xem. Bài này trình bày cách định nghĩa nhóm, truy cập JSON/YAML theo nhóm, cấu hình bộ chọn trên Swagger UI và kiểm soát việc công bố tài liệu.

## 1. Nhóm tài liệu OpenAPI là gì?

Một nhóm tài liệu (API group) là một tập operation được chọn từ các controller Spring. Springdoc tạo một OpenAPI document riêng cho mỗi nhóm. Việc nhóm có thể dựa trên:

- Path của endpoint, ví dụ `/api/public/**` hoặc `/api/admin/**`.
- Package chứa controller, ví dụ `com.example.api.publicapi`.
- Các điều kiện lọc hoặc tùy biến tài liệu bổ sung.

Ví dụ ứng dụng có ba khu vực:

| Nhóm | Path ví dụ | Người dùng tài liệu |
|---|---|---|
| `public` | `/api/public/**` | Client bên ngoài |
| `admin` | `/api/admin/**` | Giao diện quản trị và nhân viên |
| `internal` | `/internal/**` | Dịch vụ nội bộ hoặc nhóm vận hành |

Mỗi nhóm có thể có `info`, `servers`, `paths`, `components`, security và mô tả riêng. Những operation không khớp bộ lọc của một nhóm sẽ không xuất hiện trong tài liệu nhóm đó.

Nhóm tài liệu chỉ phân chia nội dung OpenAPI. Việc đưa endpoint vào nhóm `internal` không tự bảo vệ endpoint khỏi người dùng bên ngoài. Xác thực và phân quyền API vẫn phải được cấu hình bằng Spring Security hoặc cơ chế bảo vệ tương ứng.

## 2. Tạo nhóm bằng `GroupedOpenApi`

Cách phổ biến là khai báo một bean `GroupedOpenApi` cho mỗi nhóm. Ví dụ:

```java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiGroupConfiguration {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
                .group("public")
                .pathsToMatch("/api/public/**")
                .build();
    }

    @Bean
    GroupedOpenApi adminApi() {
        return GroupedOpenApi.builder()
                .group("admin")
                .pathsToMatch("/api/admin/**")
                .build();
    }

    @Bean
    GroupedOpenApi internalApi() {
        return GroupedOpenApi.builder()
                .group("internal")
                .pathsToMatch("/internal/**")
                .build();
    }
}
```

Trong ví dụ, `group(...)` đặt tên nhóm. `pathsToMatch(...)` chọn các endpoint có path khớp mẫu. Mỗi bean tạo một tài liệu độc lập. Khi thêm một nhóm mới, cần dùng tên duy nhất và một bộ lọc có mục đích rõ ràng.

Với springdoc 2.x, package của `GroupedOpenApi` là `org.springdoc.core.models.GroupedOpenApi`. Các dự án dùng springdoc 1.x có thể có package API khác; hãy dùng import tương ứng với phiên bản đang cài đặt thay vì sao chép import giữa các major version.

## 3. Lọc nhóm theo path và package

`GroupedOpenApi.Builder` hỗ trợ các điều kiện lọc thường dùng:

| Phương thức | Công dụng |
|---|---|
| `pathsToMatch(...)` | Chỉ lấy endpoint có path khớp mẫu |
| `pathsToExclude(...)` | Loại endpoint có path khớp mẫu khỏi nhóm |
| `packagesToScan(...)` | Chỉ lấy controller trong package được chỉ định |
| `packagesToExclude(...)` | Loại controller thuộc package được chỉ định |
| `addOpenApiCustomizer(...)` | Tùy chỉnh OpenAPI document của nhóm |

### Lọc theo path

Khi URL thể hiện rõ ranh giới nghiệp vụ, lọc theo path thường dễ đọc:

```java
@Bean
GroupedOpenApi customerApi() {
    return GroupedOpenApi.builder()
            .group("customer")
            .pathsToMatch("/api/customers/**")
            .pathsToExclude("/api/customers/internal/**")
            .build();
}
```

Ví dụ này chọn các endpoint khách hàng nhưng loại một nhánh nội bộ. Cần kiểm tra path thực tế sau khi ghép class-level mapping, method-level mapping và context path; bộ lọc phải khớp đường dẫn mà Spring MVC công bố.

### Lọc theo package

Nếu tổ chức mã nguồn đã tách controller theo package, có thể chọn package:

```java
@Bean
GroupedOpenApi billingApi() {
    return GroupedOpenApi.builder()
            .group("billing")
            .packagesToScan("com.example.application.billing.controller")
            .build();
}
```

Package filter hữu ích khi path giữa các module có thể giống nhau hoặc khi nhóm được quản lý theo cấu trúc mã nguồn. Tuy nhiên, di chuyển controller sang package khác có thể làm endpoint biến mất khỏi nhóm mà không đổi URL. Hãy xem việc thay đổi package là một thay đổi có thể ảnh hưởng tài liệu.

### Kết hợp include và exclude

Có thể dùng include để chọn phạm vi lớn và exclude để loại một số endpoint. Tránh tạo các mẫu chồng lấn khó hiểu. Nếu một endpoint khớp nhiều nhóm, endpoint đó có thể xuất hiện trong nhiều tài liệu; đây là điều hợp lệ nếu chủ đích là chia sẻ operation.

## 4. Cấu hình nhóm bằng application YAML

Ngoài khai báo bean, có thể cấu hình nhóm qua `springdoc.group-configs` trong `application.yml`:

```yaml
springdoc:
  group-configs:
    - group: public
      paths-to-match:
        - /api/public/**
    - group: admin
      paths-to-match:
        - /api/admin/**
    - group: internal
      paths-to-match:
        - /internal/**
```

Cấu hình này giúp quản lý bộ lọc nhóm ở một nơi và phù hợp khi các điều kiện nhóm đơn giản. Nếu cần customizer, method filter hoặc logic Java phức tạp, khai báo `GroupedOpenApi` bean linh hoạt hơn.

Nên chọn một cách cấu hình chính cho từng nhóm. Tránh khai báo cùng một nhóm đồng thời bằng bean và property nếu không có chủ đích rõ ràng, vì cấu hình trùng có thể gây nhầm lẫn hoặc xung đột tên nhóm.

## 5. Đường dẫn JSON của từng nhóm

Mặc định, springdoc cung cấp tài liệu JSON tổng quát tại:

```text
/v3/api-docs
```

Với nhóm có tên `public`, tài liệu nhóm được truy cập tại:

```text
/v3/api-docs/public
```

Với nhóm `admin`:

```text
/v3/api-docs/admin
```

Đường dẫn có dạng `/v3/api-docs/{groupName}`. `{groupName}` phải khớp với giá trị đã truyền vào `group(...)` hoặc thuộc tính `group` trong `group-configs`.

Ví dụ kiểm tra bằng curl:

```bash
curl -fS http://localhost:8080/v3/api-docs/public
curl -fS http://localhost:8080/v3/api-docs/admin
```

Tài liệu nhóm là một OpenAPI document hoàn chỉnh trong phạm vi các operation được chọn. Có thể dùng URL này cho validator, code generator, mock server hoặc quy trình lưu artifact riêng của từng nhóm.

## 6. Đường dẫn YAML của từng nhóm

Springdoc cũng hỗ trợ lấy tài liệu YAML. Với group `public`, endpoint YAML thường có dạng:

```text
/v3/api-docs/public.yaml
```

Với group `admin`:

```text
/v3/api-docs/admin.yaml
```

Ví dụ tải cả hai định dạng:

```bash
curl -fS http://localhost:8080/v3/api-docs/public -o public-openapi.json
curl -fS http://localhost:8080/v3/api-docs/public.yaml -o public-openapi.yaml
```

JSON và YAML của cùng một nhóm biểu diễn cùng một mô hình OpenAPI. Chọn định dạng theo công cụ tiêu thụ và quy ước lưu trữ. Nếu pipeline cần so sánh hai định dạng, hãy parse chúng về cấu trúc dữ liệu rồi so sánh ngữ nghĩa thay vì so sánh văn bản trực tiếp.

Nếu đã đổi `springdoc.api-docs.path`, đường dẫn cơ sở của tài liệu cũng thay đổi. Ví dụ:

```yaml
springdoc:
  api-docs:
    path: /api-docs
```

Khi đó, endpoint nhóm sẽ dùng prefix `/api-docs` thay vì `/v3/api-docs`; kiểm tra URL thực tế theo cấu hình đang chạy.

## 7. Đưa các nhóm vào bộ chọn Swagger UI

Khi có nhiều tài liệu, Swagger UI có thể hiển thị danh sách để người dùng chọn nhóm. Có thể khai báo danh sách URL trong `application.yml`:

```yaml
springdoc:
  swagger-ui:
    urls:
      - name: Public API
        url: /v3/api-docs/public
      - name: Admin API
        url: /v3/api-docs/admin
      - name: Internal API
        url: /v3/api-docs/internal
    urls-primary-name: Public API
```

Mỗi phần tử có:

- `name`: nhãn hiển thị trong danh sách chọn của Swagger UI.
- `url`: đường dẫn đến OpenAPI document tương ứng.

`urls-primary-name` chọn tài liệu được mở mặc định theo đúng tên `name` trong danh sách. Giá trị này phân biệt chữ hoa/chữ thường theo tên đã khai báo; cần giữ chúng trùng nhau.

Nếu nhóm đã được springdoc đăng ký, URL có thể trỏ trực tiếp đến endpoint group tương ứng. Khi tự cấu hình `urls`, phải bảo đảm mọi URL đều hợp lệ và có thể truy cập từ trình duyệt mở Swagger UI.

## 8. Phân biệt `url` và `urls` của Swagger UI

Swagger UI có thể nạp một tài liệu đơn hoặc một danh sách tài liệu:

| Thuộc tính | Mục đích | Trường hợp sử dụng |
|---|---|---|
| `springdoc.swagger-ui.url` | URL của một OpenAPI document | Một tài liệu duy nhất hoặc một nguồn chính |
| `springdoc.swagger-ui.urls` | Danh sách tên và URL tài liệu | Có nhiều nhóm và cần bộ chọn |
| `springdoc.swagger-ui.urls-primary-name` | Tên tài liệu được chọn ban đầu trong danh sách | Muốn mở sẵn nhóm mặc định |

Ví dụ cấu hình một tài liệu:

```yaml
springdoc:
  swagger-ui:
    url: /v3/api-docs/public
```

Ví dụ cấu hình nhiều tài liệu:

```yaml
springdoc:
  swagger-ui:
    urls:
      - name: Public API
        url: /v3/api-docs/public
      - name: Admin API
        url: /v3/api-docs/admin
    urls-primary-name: Public API
```

Khi dùng danh sách `urls`, không cần đặt thêm `url` trỏ đến cùng một tài liệu trừ khi có mục đích cấu hình cụ thể. Tránh để `url` và `urls` cạnh tranh nhau khiến người vận hành khó biết giao diện đang nạp nguồn nào.

Có thể tắt URL mặc định mẫu của Swagger UI bằng:

```yaml
springdoc:
  swagger-ui:
    disable-swagger-default-url: true
```

Điều này giúp tránh việc giao diện hiển thị một tài liệu mẫu mặc định khi cấu hình nguồn tài liệu của ứng dụng chưa đúng.

## 9. Đường dẫn Swagger UI và đường dẫn đặc tả là hai thứ khác nhau

Đường dẫn giao diện Swagger UI thường là `/swagger-ui.html` (được chuyển hướng đến trang UI) hoặc `/swagger-ui/index.html`. Đường dẫn tài liệu OpenAPI mặc định là `/v3/api-docs`; đường dẫn tài liệu theo nhóm là `/v3/api-docs/{group}`.

Có thể tùy chỉnh đường dẫn UI:

```yaml
springdoc:
  swagger-ui:
    path: /docs
```

Việc đổi `swagger-ui.path` chỉ đổi URL giao diện. Nó không tự đổi URL tài liệu OpenAPI. Tương tự, đổi `springdoc.api-docs.path` chỉ đổi endpoint đặc tả; cần cập nhật URL trong danh sách Swagger UI nếu các đường dẫn được cấu hình tường minh.

Nếu ứng dụng chạy dưới context path, chẳng hạn `/service`, hoặc được reverse proxy thêm prefix, URL mà trình duyệt nhìn thấy có thể là `/service/v3/api-docs/public`. Hãy cấu hình URL tương đối phù hợp với đường dẫn public và thiết lập forwarded headers/proxy đúng cách để Swagger UI tải được tài liệu.

## 10. Cấu hình `GroupedOpenApi` cùng customizer riêng cho nhóm

Một nhóm có thể cần thông tin hoặc nội dung riêng, chẳng hạn title, description, server hoặc security metadata. Có thể gắn `OpenApiCustomizer` vào builder của nhóm:

```java
@Bean
GroupedOpenApi partnerApi() {
    return GroupedOpenApi.builder()
            .group("partner")
            .pathsToMatch("/api/partner/**")
            .addOpenApiCustomizer(openApi -> {
                openApi.getInfo()
                        .title("Partner API")
                        .description("API dành cho đối tác tích hợp");
            })
            .build();
}
```

Customizer cho phép cập nhật mô hình OpenAPI của nhóm. Cần bảo đảm các object như `info` đã tồn tại trước khi gọi setter; trong ứng dụng thực tế có thể khởi tạo `Info` nếu chưa có. Không sửa nội dung tài liệu theo điều kiện quá rộng khiến nhóm này vô tình ảnh hưởng nhóm khác.

Nếu có cấu hình `OpenAPI` dùng chung, thông tin chung có thể được áp dụng cho nhiều tài liệu; customizer theo nhóm dùng để điều chỉnh phần khác biệt. Sau khi tùy biến, kiểm tra từng endpoint group JSON/YAML để xác nhận chỉ nhóm dự kiến bị tác động.

## 11. Cách kiểm tra nhóm nào chứa endpoint nào

Khi cấu hình nhiều bộ lọc, cần kiểm tra kết quả tài liệu thay vì chỉ đọc cấu hình. Một endpoint có thể:

- Xuất hiện đúng một nhóm nếu path/package chỉ khớp một bộ lọc.
- Xuất hiện trong nhiều nhóm nếu được chủ động chia sẻ.
- Không xuất hiện trong nhóm nào nếu không khớp bộ lọc.
- Bị loại khỏi nhóm do `pathsToExclude` hoặc `packagesToExclude`.

Quy trình kiểm tra:

1. Gọi endpoint JSON của từng nhóm.
2. Tìm `paths` trong document và liệt kê operation được công bố.
3. Đối chiếu path với mục tiêu nhóm.
4. Kiểm tra operation bị loại có thực sự vắng mặt.
5. Kiểm tra các schema trong `components` được tham chiếu hợp lệ.
6. Mở Swagger UI và chọn lần lượt từng nhóm.
7. Xác nhận giao diện hiển thị đúng title, endpoint và schema của nhóm đã chọn.

Ví dụ dùng `jq` để xem danh sách path của một tài liệu:

```bash
curl -s http://localhost:8080/v3/api-docs/public | jq -r '.paths | keys[]'
```

Lệnh này chỉ kiểm tra danh sách path; để xác minh đầy đủ cần xem method, parameter, schema, security và response của từng operation.

## 12. Bảo vệ tài liệu nhóm bằng Spring Security

Nhóm `internal` hoặc `admin` có thể chứa thông tin không dành cho mọi người. Việc ẩn nhóm khỏi Swagger UI không đủ để bảo vệ endpoint tài liệu. Người dùng vẫn có thể gọi trực tiếp URL `/v3/api-docs/internal` nếu server cho phép.

Ví dụ minh họa cấu hình bảo vệ endpoint tài liệu nội bộ:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers(
                            "/v3/api-docs/internal",
                            "/v3/api-docs/internal.yaml"
                    ).hasRole("ADMIN")
                    .requestMatchers(
                            "/v3/api-docs/public",
                            "/v3/api-docs/public.yaml"
                    ).permitAll()
                    .anyRequest().authenticated()
            )
            .build();
}
```

Đây là ví dụ rút gọn; cần tích hợp với các filter chain và quy tắc bảo mật hiện có của ứng dụng. Nếu đã đổi `springdoc.api-docs.path`, context path hoặc reverse proxy prefix, cập nhật request matcher theo URL server nhận được. Kiểm tra cả JSON lẫn YAML và các endpoint cấu hình Swagger UI có liên quan.

Các điểm cần nhớ:

- Grouping là cách tổ chức tài liệu, không phải cơ chế authorization.
- Swagger UI có thể bị bảo vệ riêng với endpoint JSON/YAML.
- Nếu tài liệu nội bộ không được phép truy cập công khai, cần bảo vệ cả đường dẫn đặc tả trực tiếp.
- API runtime vẫn phải có quy tắc phân quyền riêng; bảo vệ tài liệu không tự bảo vệ endpoint nghiệp vụ.
- Không đưa credential, token thật hoặc thông tin bí mật vào example/description của tài liệu.

## 13. Đường dẫn nhóm khi thay đổi cấu hình

Đường dẫn tài liệu có thể bị ảnh hưởng bởi một số cấu hình:

| Cấu hình | Ảnh hưởng |
|---|---|
| `GroupedOpenApi.group(...)` hoặc `group-configs[].group` | Tên group trong URL tài liệu và định danh nhóm |
| `springdoc.api-docs.path` | Prefix endpoint JSON/YAML |
| `server.servlet.context-path` | Prefix URL của ứng dụng trong Spring Boot |
| Reverse proxy path prefix | Prefix public mà trình duyệt/client nhìn thấy |
| `springdoc.swagger-ui.path` | URL giao diện Swagger UI, không phải URL đặc tả |
| `springdoc.swagger-ui.urls` | Danh sách URL tài liệu mà UI cung cấp để chọn |

Khi đổi tên group từ `admin` thành `backoffice`, URL tài liệu cũng đổi theo. Phải cập nhật `springdoc.swagger-ui.urls`, request matcher trong Spring Security, pipeline tải artifact và các client/tool đang gọi URL cũ.

Không nên đổi tên group chỉ để đổi nhãn hiển thị trong Swagger UI. Nếu muốn nhãn khác, có thể giữ URL group ổn định và đặt `name` hiển thị riêng trong `urls`.

## 14. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `/v3/api-docs/{group}` trả 404 | Group chưa được đăng ký hoặc tên URL không khớp | Kiểm tra bean/property và group name |
| Tài liệu nhóm không có endpoint mong đợi | `pathsToMatch` hoặc `packagesToScan` không khớp | Kiểm tra path mapping cuối cùng và package controller |
| Endpoint xuất hiện ở nhiều nhóm | Các bộ lọc nhóm chồng lấn | Xác định việc chia sẻ là chủ đích hay cần loại trừ |
| Swagger UI không có lựa chọn nhóm | Danh sách `urls` chưa cấu hình đúng hoặc config UI chưa được nạp | Kiểm tra `springdoc.swagger-ui.urls` và swagger-config |
| Chọn nhóm nhưng tài liệu không tải | URL trong `urls` sai, thiếu context path hoặc bị security chặn | Gọi URL trực tiếp và kiểm tra network response |
| UI luôn mở sai nhóm | `urls-primary-name` không khớp `name` trong danh sách | Đồng bộ chính xác tên nhóm mặc định |
| Đổi `swagger-ui.path` nhưng docs URL không đổi | Hai cấu hình có mục đích riêng | Điều chỉnh `springdoc.api-docs.path` nếu muốn đổi endpoint docs |
| YAML group không tải được | Sai hậu tố hoặc prefix sau khi tùy chỉnh api-docs path | Kiểm tra URL YAML của đúng group và phiên bản springdoc |
| Nhóm nội bộ vẫn truy cập công khai | Chỉ ẩn nhóm trên UI, chưa bảo vệ docs endpoint | Thêm Spring Security matcher cho JSON/YAML |
| Tài liệu nhóm thiếu schema dùng chung | Schema không còn được tham chiếu trong nhóm hoặc customizer loại bỏ thành phần | Kiểm tra `$ref` và `components.schemas` của chính document đó |
| Swagger UI hiển thị Petstore hoặc tài liệu mẫu | UI đang dùng URL mặc định mẫu | Cấu hình `url`/`urls` và cân nhắc `disable-swagger-default-url` |

## 15. Quy trình cấu hình và xác minh hoàn chỉnh

Một quy trình thực tế để tạo nhóm và hiển thị chúng trên Swagger UI:

1. Xác định ranh giới nhóm theo audience, module hoặc chính sách công bố.
2. Chọn bộ lọc theo path hoặc package; đặt tên group ổn định, dễ đọc.
3. Đăng ký `GroupedOpenApi` bean hoặc khai báo `springdoc.group-configs`.
4. Khởi động ứng dụng và gọi endpoint JSON của từng nhóm.
5. Gọi endpoint YAML tương ứng và xác nhận cùng nội dung.
6. Cấu hình `springdoc.swagger-ui.urls` với nhãn và URL cho từng tài liệu.
7. Đặt `urls-primary-name` nếu cần chọn nhóm mặc định.
8. Mở Swagger UI, kiểm tra danh sách chọn và lần lượt xem từng nhóm.
9. Bảo vệ endpoint đặc tả và giao diện theo chính sách truy cập.
10. Cập nhật URL trong pipeline, validator, code generator và tài liệu tích hợp khi tên group hoặc prefix thay đổi.

Ví dụ cấu hình tổng hợp:

```yaml
springdoc:
  api-docs:
    path: /v3/api-docs
  group-configs:
    - group: public
      paths-to-match:
        - /api/public/**
    - group: admin
      paths-to-match:
        - /api/admin/**
  swagger-ui:
    path: /swagger-ui.html
    urls:
      - name: Public API
        url: /v3/api-docs/public
      - name: Admin API
        url: /v3/api-docs/admin
    urls-primary-name: Public API
    disable-swagger-default-url: true
```

Sau khi áp dụng, xác minh tối thiểu các URL:

```text
GET /v3/api-docs/public
GET /v3/api-docs/public.yaml
GET /v3/api-docs/admin
GET /v3/api-docs/admin.yaml
GET /swagger-ui.html
```

Các URL có thể khác nếu ứng dụng đặt context path, đổi `springdoc.api-docs.path` hoặc được reverse proxy thêm prefix. Hãy dùng địa chỉ thực tế mà client truy cập.

## 16. Nguyên tắc thiết kế nhóm tài liệu

- Đặt nhóm theo người tiêu dùng hoặc phạm vi công bố có ý nghĩa, không chỉ theo tên package tùy tiện.
- Dùng group name ngắn, ổn định, không chứa khoảng trắng và dễ đưa vào URL.
- Dùng `pathsToMatch` khi ranh giới API thể hiện rõ trong URL; dùng `packagesToScan` khi cấu trúc controller phản ánh ranh giới module.
- Dùng exclude có chủ đích và kiểm tra các bộ lọc chồng lấn.
- Giữ nhãn Swagger UI (`urls[].name`) tách biệt với tên group trong URL nếu cần tên hiển thị thân thiện.
- Cấu hình `urls-primary-name` để người dùng mở đúng tài liệu mặc định.
- Phân biệt đường dẫn UI với đường dẫn JSON/YAML.
- Kiểm tra group JSON và YAML độc lập vì mỗi group là một document riêng.
- Bảo vệ docs endpoint bằng Spring Security; không coi grouping là phân quyền.
- Cập nhật pipeline và client khi đổi tên group hoặc prefix endpoint.

## Kết luận

`GroupedOpenApi` cho phép springdoc-openapi tạo tài liệu riêng cho từng nhóm controller hoặc path. Mỗi nhóm có endpoint JSON và YAML theo tên group; Swagger UI có thể hiển thị danh sách tài liệu qua `springdoc.swagger-ui.urls` và chọn nhóm mặc định bằng `urls-primary-name`. Khi cấu hình, cần giữ bộ lọc nhóm rõ ràng, phân biệt URL giao diện với URL đặc tả, cập nhật context path/reverse proxy và bảo vệ tài liệu nội bộ bằng Spring Security. Kiểm tra từng tài liệu nhóm cùng Swagger UI giúp bảo đảm người dùng nhìn thấy đúng tập API được công bố.
