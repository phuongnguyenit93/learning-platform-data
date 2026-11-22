# `swagger-config` và các URL tài nguyên phải cùng truy cập được

Swagger UI hoạt động qua nhiều request HTTP riêng biệt. Trình duyệt tải trang giao diện, tải JavaScript/CSS, gọi endpoint `swagger-config`, rồi dùng URL trong cấu hình đó để tải OpenAPI JSON/YAML. Nếu ứng dụng chạy sau reverse proxy, API gateway hoặc dưới một context path, tất cả URL này phải trỏ đến đúng địa chỉ công khai và được proxy chuyển tiếp đúng cách.

Vì vậy, việc mở được `/swagger-ui.html` chưa chứng minh Swagger UI đã hoạt động hoàn chỉnh. Trang có thể tải thành công nhưng không hiển thị API vì `swagger-config` trả 404, URL OpenAPI trong config trỏ về host nội bộ, hoặc tài nguyên JavaScript bị proxy chặn. Cần kiểm tra toàn bộ chuỗi request từ trình duyệt.

## 1. Các URL tham gia vào quá trình tải Swagger UI

Với cấu hình Springdoc mặc định, các request chính thường có dạng:

| Thành phần | URL mặc định | Vai trò |
|---|---|---|
| Trang Swagger UI | `/swagger-ui.html` | Entry point của giao diện; thường chuyển hướng đến trang UI thực tế |
| Tài nguyên UI | `/swagger-ui/**` | JavaScript, CSS, hình ảnh và các tài nguyên của Swagger UI |
| Swagger UI config | `/v3/api-docs/swagger-config` | Trả về cấu hình mà Swagger UI dùng để tìm OpenAPI document |
| OpenAPI mặc định | `/v3/api-docs` | Trả về OpenAPI JSON |
| OpenAPI YAML | `/v3/api-docs.yaml` | Trả về OpenAPI YAML |
| OpenAPI group | `/v3/api-docs/{group}` | Trả về document của một `GroupedOpenApi` |
| OAuth redirect | `/swagger-ui/oauth2-redirect.html` | Callback page khi Swagger UI thực hiện OAuth2 authorization flow |

Các URL này có thể thay đổi khi cấu hình `springdoc.api-docs.path`, `springdoc.swagger-ui.path`, `springdoc.swagger-ui.configUrl`, context path hoặc reverse proxy prefix. Bảng trên là đường dẫn tương đối với context path của ứng dụng, không nhất thiết là đường dẫn công khai cuối cùng.

Ví dụ, nếu ứng dụng được công bố dưới prefix `/docs`, trình duyệt có thể cần truy cập:

```text
https://api.example.com/docs/swagger-ui.html
https://api.example.com/docs/swagger-ui/swagger-ui.css
https://api.example.com/docs/v3/api-docs/swagger-config
https://api.example.com/docs/v3/api-docs
https://api.example.com/docs/swagger-ui/oauth2-redirect.html
```

Không phải mọi phiên bản Swagger UI đều tạo cùng một danh sách asset request hoặc cùng redirect URL. Hãy quan sát Network tab để xác định các URL thực tế mà phiên bản ứng dụng đang tải.

## 2. `swagger-config` khác OpenAPI document

Đây là hai endpoint có nhiệm vụ khác nhau:

- `configUrl` trỏ đến tài liệu cấu hình của Swagger UI, thường là `/v3/api-docs/swagger-config`.
- `url` hoặc `urls` trong cấu hình Swagger UI trỏ đến OpenAPI document mà giao diện sẽ hiển thị.

Ví dụ:

```text
GET /v3/api-docs/swagger-config
```

Endpoint này trả về một JSON cấu hình, có thể chứa các trường như `url`, `urls`, `oauth2RedirectUrl` và các tùy chọn UI. Sau đó Swagger UI mới gọi URL OpenAPI được chỉ định trong cấu hình, ví dụ:

```text
GET /v3/api-docs
```

Không cấu hình `springdoc.swagger-ui.configUrl` trỏ thẳng đến `/v3/api-docs`. Hai endpoint có định dạng và mục đích khác nhau. Nếu UI nhận OpenAPI document tại nơi nó chờ config object, nó có thể báo lỗi parse config hoặc không render được API.

Ví dụ cấu hình tường minh khi API Docs dùng path riêng:

```yaml
springdoc:
  api-docs:
    path: /openapi
  swagger-ui:
    path: /reference
    config-url: /openapi/swagger-config
```

Khi đó, cần kiểm tra cả `/reference`, `/openapi/swagger-config` và `/openapi`. Thay đổi `api-docs.path` làm thay đổi base path của endpoint OpenAPI và swagger-config; thay đổi `swagger-ui.path` chỉ đổi entry point của giao diện.

## 3. Các property quan trọng và phạm vi ảnh hưởng

Springdoc cung cấp các property riêng cho URL giao diện và URL document:

| Property | Mặc định thường gặp | Phạm vi |
|---|---|---|
| `springdoc.swagger-ui.path` | `/swagger-ui.html` | Đường dẫn entry point của giao diện |
| `springdoc.swagger-ui.configUrl` | `/v3/api-docs/swagger-config` | URL lấy cấu hình Swagger UI |
| `springdoc.swagger-ui.url` | Không đặt | URL của một OpenAPI file tùy chỉnh |
| `springdoc.swagger-ui.urls` | Không đặt | Danh sách nhiều OpenAPI document, thường dùng cho group hoặc dịch vụ ngoài |
| `springdoc.swagger-ui.urlsPrimaryName` | Không đặt | Tên document được chọn mặc định khi có danh sách `urls` |
| `springdoc.swagger-ui.oauth2RedirectUrl` | `/swagger-ui/oauth2-redirect.html` | URL callback OAuth2 |
| `springdoc.swagger-ui.use-root-path` | `false` | Cho phép truy cập Swagger UI từ root path của ứng dụng |
| `springdoc.api-docs.path` | `/v3/api-docs` | Base path của endpoint OpenAPI và swagger-config |

Các tên property trong YAML dùng kebab-case, ví dụ `config-url`, `oauth2-redirect-url`, `use-root-path`, `api-docs.path`. Spring Boot relaxed binding sẽ ánh xạ chúng đến property tương ứng.

`springdoc.swagger-ui.url` được dùng khi muốn UI tải một file OpenAPI tùy chỉnh. Nếu khai báo `urls`, danh sách `urls` được ưu tiên và `url` đơn lẻ bị bỏ qua. Mỗi phần tử trong `urls` cần có tên và URL duy nhất để top bar của Swagger UI phân biệt các tài liệu.

Ví dụ cấu hình hai group:

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

Đường dẫn của group phải khớp chính xác với tên group đã đăng ký. Nếu tài liệu được phục vụ qua prefix của proxy, các URL trong danh sách cũng phải được truy cập qua prefix công khai hoặc được tạo đúng nhờ forwarded headers.

## 4. Phân biệt entry path, API Docs path và context path

Ba lớp path này thường bị nhầm lẫn:

1. **Context path hoặc base path** là tiền tố chung mà ứng dụng Spring Boot sử dụng cho request.
2. **Swagger UI path** là đường dẫn mở giao diện.
3. **API Docs path** là đường dẫn lấy OpenAPI JSON/YAML và swagger-config.

Ví dụ với Spring MVC:

```yaml
server:
  servlet:
    context-path: /orders

springdoc:
  swagger-ui:
    path: /reference
  api-docs:
    path: /openapi
```

Đường dẫn nội bộ của ứng dụng lúc này gồm:

```text
/orders/reference
/orders/openapi/swagger-config
/orders/openapi
/orders/openapi.yaml
```

Context path `/orders` được áp dụng chung. `swagger-ui.path` và `api-docs.path` là các phần riêng nằm bên trong context path đó.

Với Spring WebFlux, ứng dụng có thể dùng `spring.webflux.base-path` thay cho `server.servlet.context-path`. Hãy phân biệt cấu hình base path của stack đang chạy với prefix do reverse proxy thêm hoặc loại bỏ.

Đổi `springdoc.swagger-ui.path` không tự đổi `springdoc.api-docs.path`. Đổi `springdoc.api-docs.path` cũng không tự thay đổi đường dẫn public mà proxy đang expose. Mỗi lớp phải được cấu hình và kiểm tra riêng.

## 5. Hai mô hình reverse proxy phổ biến

Khi công bố ứng dụng dưới một prefix, có hai mô hình triển khai thường gặp. Chọn một mô hình và giữ nhất quán giữa proxy và ứng dụng.

### Mô hình A: Proxy giữ nguyên prefix khi chuyển tiếp

Ví dụ client gọi:

```text
https://api.example.com/orders/swagger-ui.html
```

Proxy chuyển tiếp path `/orders/swagger-ui.html` đến backend. Ứng dụng phải được cấu hình để nhận path đó, chẳng hạn qua context path `/orders` hoặc base path tương ứng. Không thêm lại cùng prefix bằng `X-Forwarded-Prefix` nếu ứng dụng đã nhìn thấy và xử lý prefix trong request path.

### Mô hình B: Proxy loại prefix trước khi chuyển tiếp

Client vẫn gọi:

```text
https://api.example.com/orders/swagger-ui.html
```

Nhưng proxy loại `/orders` trước khi gửi đến ứng dụng, nên backend nhận `/swagger-ui.html`. Trong trường hợp này, proxy cần truyền thông tin prefix công khai bằng `X-Forwarded-Prefix: /orders`, cùng host và scheme bên ngoài.

Ứng dụng phải xử lý forwarded headers để Springdoc tạo link công khai đúng. Nếu proxy loại prefix nhưng không gửi `X-Forwarded-Prefix`, ứng dụng có thể tạo URL `/v3/api-docs/swagger-config` mà thiếu `/orders`; trình duyệt sẽ gọi sai đường dẫn.

Không để proxy vừa giữ prefix trong request path, vừa gửi forwarded prefix cùng giá trị nếu cấu hình backend cũng áp dụng cả hai. Kết quả có thể thành URL lặp prefix như `/orders/orders/...`.

## 6. Cấu hình Nginx khi proxy loại prefix

Ví dụ Nginx công bố Spring Boot dưới `/docs/` và loại prefix này trước khi chuyển request vào backend:

```nginx
server {
    listen 443 ssl;
    server_name api.example.com;

    location /docs/ {
        # Dấu / cuối khiến Nginx thay phần /docs/ bằng / khi proxy_pass.
        proxy_pass http://spring-app:8080/;

        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Port $server_port;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Prefix /docs;
    }
}
```

Request công khai `/docs/swagger-ui.html` được chuyển đến backend dưới path `/swagger-ui.html`; request `/docs/v3/api-docs/swagger-config` được chuyển đến `/v3/api-docs/swagger-config`. `X-Forwarded-Prefix` cho backend biết prefix công khai đã bị proxy loại bỏ.

Với Spring Boot 3.x, có thể bật xử lý forwarded headers ở tầng Spring Framework:

```yaml
server:
  forward-headers-strategy: framework
```

Trong Servlet stack, cơ chế này sử dụng `ForwardedHeaderFilter`; trong reactive stack, Spring Framework sử dụng `ForwardedHeaderTransformer`. Cấu hình cụ thể phụ thuộc phiên bản Spring Boot và loại web server.

Nếu proxy chỉ truyền các header như `X-Forwarded-For` và `X-Forwarded-Proto`, chiến lược native của web server có thể đủ. Khi cần xử lý prefix hoặc các forwarded header mà web server không hỗ trợ, kiểm tra lựa chọn `framework` theo tài liệu đúng phiên bản Spring Boot.

### Tin cậy forwarded headers

Chỉ chấp nhận forwarded headers từ reverse proxy đáng tin cậy. Proxy biên nên xóa hoặc ghi đè các header `Forwarded` và `X-Forwarded-*` do client tự gửi, sau đó tạo lại giá trị dựa trên request thực tế. Nếu backend nhận trực tiếp forwarded header giả mạo, ứng dụng có thể sinh link chứa host, scheme hoặc prefix không đáng tin cậy.

## 7. Ví dụ cấu hình Springdoc khi ứng dụng nằm dưới `/docs`

Khi proxy loại `/docs` và gửi `X-Forwarded-Prefix`, ứng dụng có thể giữ các path nội bộ mặc định:

```yaml
server:
  forward-headers-strategy: framework

springdoc:
  api-docs:
    path: /v3/api-docs
  swagger-ui:
    path: /swagger-ui.html
    config-url: /v3/api-docs/swagger-config
```

Không cần hardcode prefix `/docs` vào mọi property nếu forwarded headers được xử lý đúng. Hãy kiểm tra response của swagger-config để xác nhận các URL được tạo ra có prefix public.

Nếu không thể cấu hình forwarded headers ở backend, cần cấu hình các URL public phù hợp và đảm bảo proxy chuyển tiếp đúng các route đó. Tuy nhiên, cách này dễ phát sinh khác biệt giữa môi trường và dễ bỏ sót URL group hoặc OAuth callback. Xử lý forwarded headers đúng thường dễ duy trì hơn.

## 8. `ServerBaseUrlCustomizer` không thay thế cấu hình URL của Swagger UI

Springdoc cung cấp `ServerBaseUrlCustomizer` để điều chỉnh server base URL được đưa vào OpenAPI document. Điều này hữu ích khi `servers` sinh ra có host, port hoặc scheme không đúng với địa chỉ API công khai.

Ví dụ khái niệm:

```java
import org.springdoc.core.customizers.ServerBaseUrlCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiServerConfiguration {

    @Bean
    ServerBaseUrlCustomizer publicServerBaseUrlCustomizer() {
        return serverBaseUrl -> serverBaseUrl
            .replace("http://spring-app:8080", "https://api.example.com");
    }
}
```

Đây chỉ là ví dụ minh họa; không nên dùng phép thay chuỗi cố định nếu ứng dụng có nhiều host hoặc môi trường. Hãy ưu tiên forwarded headers được proxy tin cậy truyền vào.

`ServerBaseUrlCustomizer` tác động đến `servers` trong OpenAPI document, tức URL mà Try it out dùng để gọi API nghiệp vụ. Nó không sửa đường dẫn để Swagger UI tải HTML, asset, `swagger-config` hoặc OpenAPI document. Nếu Swagger UI không tải được config, customizer này không giải quyết nguyên nhân.

## 9. Cấu hình nhiều OpenAPI document hoặc file tĩnh

### Nhiều group nội bộ

Nếu ứng dụng có nhiều `GroupedOpenApi`, Swagger UI có thể hiển thị danh sách document:

```yaml
springdoc:
  swagger-ui:
    urls:
      - name: Public
        url: /v3/api-docs/public
      - name: Admin
        url: /v3/api-docs/admin
    urls-primary-name: Public
```

Proxy phải cho phép truy cập tất cả URL được liệt kê. Chỉ mở `/v3/api-docs` mà chặn `/v3/api-docs/admin` thì group Admin vẫn không tải được.

### OpenAPI file tĩnh

Nếu muốn Swagger UI tải một file đặt trong `src/main/resources/static`, ví dụ `openapi.yaml`, có thể cấu hình:

```yaml
springdoc:
  swagger-ui:
    url: /openapi.yaml
    disable-swagger-default-url: true
```

Khi đó, trình duyệt phải truy cập được file `/openapi.yaml` qua cùng origin hoặc một origin có CORS phù hợp. Nếu dùng `urls`, cấu hình `url` đơn lẻ sẽ bị bỏ qua.

### Tài liệu từ dịch vụ khác

Swagger UI có thể tải OpenAPI document từ dịch vụ khác bằng `urls`. Trình duyệt là bên thực hiện request đó, vì vậy dịch vụ nguồn phải cho phép CORS từ origin của Swagger UI. URL có thể truy cập từ máy chủ Spring Boot chưa chắc truy cập được từ trình duyệt người dùng.

## 10. OAuth2 redirect cũng phải đi qua proxy

Khi Swagger UI dùng OAuth2 Authorization Code Flow, browser sẽ quay lại callback URL được cấu hình bởi `springdoc.swagger-ui.oauth2RedirectUrl`. URL mặc định thường là `/swagger-ui/oauth2-redirect.html` tương đối với context path của ứng dụng.

Nếu UI mở tại `https://api.example.com/docs/swagger-ui.html`, callback cũng phải được công bố dưới prefix `/docs` và proxy phải chuyển tiếp đến tài nguyên callback tương ứng. Nếu authorization server đã đăng ký redirect URI không có prefix trong khi trình duyệt quay lại URL có prefix, quá trình đăng nhập sẽ bị từ chối vì redirect URI không khớp.

Hãy đồng bộ ba nơi:

1. `springdoc.swagger-ui.oauth2RedirectUrl` trong Springdoc.
2. URL callback mà Swagger UI thực sự gửi trong authorization request.
3. Redirect URI được đăng ký trên authorization server.

Nếu dùng custom redirect URL, bảo đảm nó có thể truy cập công khai và nằm trong danh sách redirect URI hợp lệ của client OAuth2. Không dùng URL nội bộ như `http://spring-app:8080/...` trong cấu hình OAuth client chạy ở trình duyệt.

## 11. Security và CORS trên chuỗi URL

Swagger UI cần tải tài nguyên giao diện, swagger-config và OpenAPI document. Nếu Spring Security bảo vệ một trong các endpoint này, trình duyệt có thể nhận 401, 403 hoặc redirect đến trang đăng nhập thay vì JSON mong đợi.

Một số dấu hiệu thường gặp:

- Trang UI tải được nhưng danh sách operation trống vì `/v3/api-docs/swagger-config` bị 401.
- `swagger-config` trả 200 nhưng URL OpenAPI trả 302 đến trang login, khiến UI báo lỗi parse JSON.
- JSON document truy cập được bằng cURL nhưng bị trình duyệt chặn do CORS khi UI và document khác origin.
- UI resource trả 403 do rule bảo mật chỉ cho phép `/swagger-ui.html` nhưng không cho phép `/swagger-ui/**`.

Nếu UI và OpenAPI cùng origin, CORS thường không cần thiết cho request đó. Nếu chúng khác origin, server cung cấp OpenAPI phải cho phép origin của Swagger UI, method và header cần thiết. CORS không thay thế authentication; các endpoint tài liệu vẫn cần policy truy cập riêng.

Khi bảo vệ tài liệu, hãy kiểm tra cả:

- Entry point `/swagger-ui.html` hoặc custom path.
- Static resources `/swagger-ui/**`.
- Swagger config endpoint `/v3/api-docs/swagger-config` hoặc custom path.
- OpenAPI JSON/YAML và các group `/v3/api-docs/**`.
- OAuth2 redirect resource nếu dùng OAuth.

Các matcher phải theo path thực tế sau context path và cấu hình proxy. Nếu chỉ cho phép entry point mà quên asset hoặc config endpoint, giao diện sẽ tải không đầy đủ.

## 12. Kiểm tra response của swagger-config

Sau khi triển khai, gọi URL public của swagger-config:

```bash
curl -i https://api.example.com/docs/v3/api-docs/swagger-config
```

Response phải là JSON cấu hình Swagger UI. Không nên nhận HTML của trang login, trang lỗi reverse proxy hoặc trang welcome page.

Nếu có `jq`, kiểm tra các URL mà cấu hình công bố:

```bash
curl -fsS https://api.example.com/docs/v3/api-docs/swagger-config \
  | jq '{url, urls, oauth2RedirectUrl}'
```

Đối chiếu:

- `url` có trỏ đến OpenAPI document công khai không?
- Mỗi `urls[].url` có thể truy cập từ trình duyệt không?
- `oauth2RedirectUrl` có chứa đúng context path/proxy prefix không?
- Có URL nào trỏ đến `localhost`, hostname container, IP private hoặc port nội bộ không?
- Có URL nào bị lặp prefix như `/docs/docs/...` không?

Sau đó gọi từng OpenAPI document:

```bash
curl -i https://api.example.com/docs/v3/api-docs
curl -i https://api.example.com/docs/v3/api-docs.yaml
curl -i https://api.example.com/docs/v3/api-docs/admin
```

Nếu API Docs path đã được tùy chỉnh, thay URL kiểm tra tương ứng. Mục tiêu là xác minh toàn bộ document được liệt kê trong swagger-config, không chỉ document mặc định.

## 13. Kiểm tra tài nguyên UI trong trình duyệt

Mở Developer Tools → Network, tải lại Swagger UI và kiểm tra theo thứ tự:

1. Request đến entry point trả redirect hợp lệ hoặc trang HTML 200.
2. JavaScript/CSS dưới `/swagger-ui/**` trả 200 và đúng content type.
3. Request đến `swagger-config` trả JSON 200.
4. Request đến OpenAPI JSON/YAML trả document hợp lệ.
5. Nếu dùng OAuth2, callback resource có thể truy cập qua URL public.

Lọc Network tab theo `swagger`, `api-docs`, `openapi` hoặc `oauth2-redirect`. Một request 200 vẫn có thể sai nếu body là HTML login page thay vì JavaScript, CSS hoặc JSON. Luôn kiểm tra cả status, content type và nội dung response.

Khi cần xác định URL sai xuất phát từ đâu, xem response của swagger-config trước. Nếu config đã chứa URL nội bộ hoặc thiếu prefix, kiểm tra forwarded headers và server request metadata. Nếu config đúng nhưng request bị 404, kiểm tra route của proxy. Nếu request trả 401/403, kiểm tra security matcher. Nếu browser báo CORS, kiểm tra origin và CORS response headers.

## 14. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `/swagger-ui.html` mở được nhưng trang báo không tải được definition | `configUrl` hoặc OpenAPI URL sai/không truy cập được | Kiểm tra `/v3/api-docs/swagger-config`, sau đó gọi URL document trong config |
| `swagger-config` trả 404 | Proxy chưa chuyển tiếp API Docs path hoặc `api-docs.path` đã đổi | Cập nhật route proxy và `springdoc.swagger-ui.configUrl` |
| `swagger-config` trả OpenAPI JSON | Đặt `configUrl` trỏ đến `/v3/api-docs` | Đổi về endpoint swagger-config tương ứng |
| Config chứa hostname nội bộ | Ứng dụng không nhận forwarded host/proto hoặc document bị cache từ request nội bộ | Cấu hình forwarded headers, kiểm tra proxy và cache |
| URL thiếu prefix public | Proxy loại prefix nhưng không gửi `X-Forwarded-Prefix` hoặc backend không xử lý | Gửi header và bật forwarded header strategy phù hợp |
| URL lặp prefix | Proxy giữ prefix đồng thời forwarded prefix cũng được áp dụng | Chọn một mô hình preserve hoặc strip prefix |
| JavaScript/CSS trả 404 | Proxy chỉ route entry path, không route `/swagger-ui/**` | Mở route tài nguyên UI qua proxy |
| OpenAPI JSON trả HTML | Security redirect, custom error page hoặc proxy rewrite sai | Kiểm tra status, content type, login redirect và route |
| Group trong top bar không tải | `urls[].url` sai hoặc proxy chặn group endpoint | Kiểm tra từng URL group từ browser |
| Try it out gọi sai host | `servers` trong OpenAPI sinh từ request nội bộ | Sửa forwarded headers hoặc `ServerBaseUrlCustomizer` |
| OAuth2 login quay về 404 | Redirect URL không có prefix hoặc proxy không phục vụ callback | Đồng bộ `oauth2RedirectUrl`, proxy route và redirect URI đăng ký |
| cURL hoạt động nhưng browser không tải được spec ngoài | CORS chặn request cross-origin | Cấu hình CORS trên server cung cấp document |
| UI hoạt động khi truy cập trực tiếp nhưng lỗi qua gateway | Gateway rewrite path, forwarded headers hoặc security policy khác | Kiểm tra URL công khai và Network tab qua gateway |

## 15. Checklist triển khai Swagger UI sau reverse proxy

- [ ] Đã xác định URL công khai của Swagger UI entry point.
- [ ] Proxy chuyển tiếp đầy đủ `/swagger-ui/**` và các tài nguyên cần thiết.
- [ ] `springdoc.swagger-ui.configUrl` trỏ đến swagger-config endpoint, không phải OpenAPI document.
- [ ] Proxy chuyển tiếp swagger-config endpoint và trả JSON đúng định dạng.
- [ ] Mọi URL `url` hoặc `urls[].url` trong swagger-config truy cập được từ trình duyệt.
- [ ] OpenAPI JSON, YAML và tất cả group document đều có route phù hợp.
- [ ] Context path, API Docs path và UI path được phân biệt rõ.
- [ ] Đã chọn mô hình proxy giữ prefix hoặc loại prefix, không áp dụng lặp.
- [ ] Nếu proxy loại prefix, đã gửi `X-Forwarded-Prefix` và ứng dụng xử lý forwarded headers.
- [ ] Proxy ghi đè forwarded headers từ client và chỉ backend tin cậy mới được gửi chúng.
- [ ] Scheme, host và port công khai khớp với request HTTPS bên ngoài.
- [ ] `servers` trong OpenAPI trỏ đến API public đúng để Try it out hoạt động.
- [ ] OAuth2 redirect URL khớp URL công khai và redirect URI trên authorization server.
- [ ] Spring Security cho phép hoặc xác thực đầy đủ entry, asset, config, document và callback theo chính sách.
- [ ] CORS được cấu hình nếu UI và OpenAPI document khác origin.
- [ ] Đã kiểm tra status, content type và body của từng request bằng cURL và browser Network tab.

Swagger UI là chuỗi tài nguyên HTTP: trang giao diện tải asset, gọi `swagger-config`, rồi tải OpenAPI document từ URL được cấu hình. Reverse proxy và Spring Boot phải phối hợp để tạo đúng scheme, host, port, context path và prefix công khai. Hãy phân biệt `configUrl` với `url`/`urls`, chuyển tiếp đầy đủ static resources và các endpoint API Docs, xử lý forwarded headers theo mô hình proxy đang dùng, rồi xác minh từng request từ trình duyệt. Khi tất cả URL đều truy cập được và trả đúng loại nội dung, Swagger UI mới có thể hiển thị tài liệu và thực hiện Try it out ổn định.

## Tài liệu tham khảo

- [Springdoc OpenAPI – FAQ: Deploy behind a reverse proxy](https://springdoc.org/faq.html)
- [Springdoc OpenAPI – Configuration Properties](https://springdoc.org/properties.html)
- [Spring Boot 3.5 – Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html#howto.webserver.use-behind-a-proxy-server)
- [Spring Framework – Forwarded Headers](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html#filters-forwarded-headers)
- [Swagger UI – Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/)
