# Cùng nguồn, khác nguồn và cơ chế preflight của trình duyệt

Khi một frontend chạy trên một origin gọi API Spring Data REST ở origin khác, trình duyệt áp dụng Same-Origin Policy (SOP) để giới hạn cách JavaScript đọc tài nguyên giữa các origin. CORS (Cross-Origin Resource Sharing) là cơ chế HTTP cho phép server công bố những origin, method và request header được phép truy cập. Với một số request, browser gửi thêm một request kiểm tra trước gọi là **preflight** bằng HTTP OPTIONS.

CORS là chính sách do browser thực thi dựa trên response headers của server. Backend cần cấu hình đúng; frontend không thể tự bật quyền CORS bằng cách thêm một request header tùy ý.

## 1. Origin và Same-Origin Policy

Một origin được xác định bởi ba thành phần:

- **Scheme:** giao thức, ví dụ `http` hoặc `https`.
- **Host:** tên miền hoặc địa chỉ host.
- **Port:** cổng kết nối.

Hai URL cùng origin khi cả ba thành phần này giống nhau. Path không tham gia vào phép so sánh origin.

Ví dụ:

| URL thứ nhất | URL thứ hai | Cùng origin? | Lý do |
|---|---|---|---|
| `https://app.example.test/home` | `https://app.example.test/api` | Có | Cùng scheme, host và port mặc định |
| `https://app.example.test` | `http://app.example.test` | Không | Khác scheme |
| `https://app.example.test` | `https://api.example.test` | Không | Khác host |
| `https://app.example.test` | `https://app.example.test:8443` | Không | Khác port |
| `http://localhost:3000` | `http://localhost:8080` | Không | Khác port |

Same-Origin Policy hạn chế JavaScript đọc response hoặc truy cập một số tài nguyên thuộc origin khác. Nó là nền tảng bảo vệ browser khỏi việc một trang web tùy ý đọc dữ liệu của trang khác mà người dùng đang đăng nhập.

CORS bổ sung một cách có kiểm soát để server cho phép một số origin cụ thể đọc response. CORS không làm hai origin trở thành một origin; browser vẫn nhận biết đây là request cross-origin và áp dụng các quy tắc CORS.

Cũng cần phân biệt **origin** với **site**. Hai subdomain có thể được xem là cùng site trong một số quy tắc cookie nhưng vẫn là hai origin khác nhau. CORS so sánh origin gồm scheme, host và port.

## 2. CORS hoạt động như thế nào?

Khi JavaScript gọi API khác origin bằng Fetch hoặc XMLHttpRequest, browser gửi header `Origin` để cho server biết request xuất phát từ đâu.

Ví dụ frontend ở `https://app.example.test` gọi:

```javascript
fetch("https://api.example.test/people", {
  method: "GET"
});
```

Request có thể mang header:

```http
GET /people HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Accept: application/json
```

Server cho phép origin đó có thể trả:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Vary: Origin
Content-Type: application/hal+json
```

Browser kiểm tra `Access-Control-Allow-Origin`. Nếu giá trị phù hợp với origin của trang, JavaScript được phép đọc response theo CORS policy. Nếu header thiếu hoặc không khớp, browser chặn JavaScript đọc response và hiển thị lỗi CORS trong console.

Server vẫn có thể đã nhận và xử lý request trước khi browser chặn response. Vì vậy, CORS error không đồng nghĩa request chắc chắn chưa đến server hoặc không tạo side effect. Điều này đặc biệt quan trọng với request ghi dữ liệu.

## 3. Simple request và request cần preflight

Không phải mọi request cross-origin đều cần preflight. Browser có thể gửi một số request đơn giản trực tiếp; các request khác phải kiểm tra quyền trước.

Một request thường thuộc nhóm **CORS-safelisted (simple)** khi thỏa các điều kiện chính:

- Method là GET, HEAD hoặc POST.
- Request headers chỉ gồm các header safelisted và giá trị của chúng đáp ứng quy tắc CORS.
- Nếu có `Content-Type`, media type thuộc một trong các loại safelisted: `application/x-www-form-urlencoded`, `multipart/form-data` hoặc `text/plain`.
- Không có các yếu tố khác khiến request không còn thuộc nhóm safelisted.

Ví dụ GET đơn giản:

```javascript
fetch("https://api.example.test/people", {
  method: "GET"
});
```

Ví dụ POST gửi form data:

```javascript
const form = new URLSearchParams();
form.set("name", "An");

fetch("https://api.example.test/people-form", {
  method: "POST",
  headers: {
    "Content-Type": "application/x-www-form-urlencoded"
  },
  body: form
});
```

Một số request thường cần preflight:

- Dùng method PUT, PATCH hoặc DELETE.
- Dùng header không thuộc safelist, ví dụ header tùy chỉnh `X-Request-ID`.
- Gửi header `Authorization`.
- Gửi JSON với `Content-Type: application/json`, vì media type này không thuộc nhóm Content-Type safelisted.

Ví dụ request PATCH đến Spring Data REST:

```javascript
fetch("https://api.example.test/people/42", {
  method: "PATCH",
  headers: {
    "Content-Type": "application/merge-patch+json",
    "Accept": "application/hal+json"
  },
  body: JSON.stringify({
    firstName: "An"
  })
});
```

Request này cần preflight do dùng PATCH và các header/media type không safelisted. Browser gửi OPTIONS trước khi gửi PATCH thực tế.

Việc một request là simple không có nghĩa request đó an toàn về nghiệp vụ hoặc không cần authentication. Nó chỉ có nghĩa browser không cần preflight theo các điều kiện CORS.

## 4. Preflight request bằng OPTIONS

Preflight là một request OPTIONS do browser tự gửi trước request cross-origin không thuộc nhóm safelisted. Nó hỏi server liệu origin hiện tại có được phép dùng method và request headers dự kiến hay không.

Ví dụ browser dự định gửi PATCH với Content-Type và Accept:

```http
OPTIONS /people/42 HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: PATCH
Access-Control-Request-Headers: content-type, accept
```

Ý nghĩa:

- `Origin` là origin của frontend.
- `Access-Control-Request-Method` cho biết method của request thực tế sắp gửi.
- `Access-Control-Request-Headers` liệt kê những request headers mà request thực tế muốn dùng.

Nếu policy cho phép, server có thể trả:

```http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET, POST, PUT, PATCH, DELETE, OPTIONS
Access-Control-Allow-Headers: Content-Type, Accept
Access-Control-Max-Age: 3600
Vary: Origin
```

Sau khi kiểm tra response preflight, browser mới tiếp tục gửi request PATCH thật. Nếu preflight thất bại, browser không gửi request thực tế theo luồng đó.

Preflight thường không mang credentials của request thực tế. Tuy vậy, với request có credentials, response preflight và response thực tế vẫn phải đáp ứng các quy tắc CORS cho credentialed request, trong đó có `Access-Control-Allow-Credentials: true` và origin cụ thể.

Browser có thể cache kết quả preflight trong thời gian được server công bố qua `Access-Control-Max-Age`, trong giới hạn mà browser áp dụng. Vì vậy, thay đổi CORS policy có thể không phản ánh ngay lập tức ở một browser đã cache preflight; khi debug, hãy cân nhắc cache và thử lại trong điều kiện phù hợp.

## 5. Các CORS response headers quan trọng

| Header | Vai trò |
|---|---|
| `Access-Control-Allow-Origin` | Origin được phép đọc response; có thể là một origin cụ thể hoặc `*` trong trường hợp không dùng credentials |
| `Access-Control-Allow-Methods` | Các method được phép trong CORS context |
| `Access-Control-Allow-Headers` | Các request headers browser được phép gửi |
| `Access-Control-Allow-Credentials` | Cho phép browser chia sẻ response của credentialed request khi giá trị là `true` |
| `Access-Control-Expose-Headers` | Cho phép JavaScript đọc thêm response headers ngoài nhóm safelisted |
| `Access-Control-Max-Age` | Thời gian browser có thể cache kết quả preflight |
| `Vary: Origin` | Báo cho cache rằng response có thể thay đổi theo Origin request header |

Ví dụ server chỉ cho frontend cụ thể gọi API:

```http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET, POST, PUT, PATCH, DELETE
Access-Control-Allow-Headers: Authorization, Content-Type, Accept, X-Request-ID
Access-Control-Expose-Headers: ETag, Location
Vary: Origin
```

`Access-Control-Allow-Methods` không giống header `Allow` của HTTP. `Allow` mô tả các HTTP method được hỗ trợ bởi target resource; `Access-Control-Allow-Methods` là một phần của CORS policy dành cho browser và origin/request đang xét. Một method có trong Allow chưa chắc đã được CORS cho phép.

Tương tự, `Access-Control-Allow-Headers` nói về request headers browser được phép gửi; `Access-Control-Expose-Headers` nói về response headers JavaScript được phép đọc.

## 6. Credentials: cookie, session và Authorization

Nếu frontend cần gửi cookie hoặc HTTP authentication tự động, Fetch phải bật credentials:

```javascript
fetch("https://api.example.test/people", {
  method: "GET",
  credentials: "include"
});
```

Server cần trả các header phù hợp, ví dụ:

```http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
```

Các quy tắc quan trọng:

- Giá trị của `Access-Control-Allow-Credentials` phải là chữ thường `true`.
- Khi cho phép credentials, `Access-Control-Allow-Origin: *` không hợp lệ cho việc chia sẻ response; server phải trả origin cụ thể.
- Nếu server phản hồi origin động dựa trên request, cần dùng `Vary: Origin` để cache không dùng nhầm response của origin khác.
- Cookie còn chịu các thuộc tính cookie như `SameSite`, `Secure`, domain và path. CORS đúng không tự bảo đảm browser sẽ gửi cookie.
- Header `Authorization` thường khiến request cần preflight và phải được cho phép tường minh trong `Access-Control-Allow-Headers`.

Không phản chiếu bất kỳ giá trị Origin nào mà không kiểm tra. Nếu server lấy Origin từ request rồi trả lại ngay, mọi website có thể được cho phép đọc response, làm mất mục đích của allowlist.

## 7. Cấu hình CORS trong Spring MVC

Có thể cấu hình CORS ở Spring MVC bằng `WebMvcConfigurer`. Ví dụ:

```java
@Configuration
public class CorsConfig implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/**")
            .allowedOrigins("https://app.example.test")
            .allowedMethods(
                "GET", "POST", "PUT", "PATCH",
                "DELETE", "OPTIONS"
            )
            .allowedHeaders(
                "Authorization", "Content-Type",
                "Accept", "X-Request-ID"
            )
            .exposedHeaders("ETag", "Location")
            .allowCredentials(true)
            .maxAge(3600);
    }
}
```

Các giá trị domain, path, method và header là ví dụ. Trong production, chỉ liệt kê origin frontend thực sự cần truy cập. Nếu có nhiều môi trường frontend, quản lý allowlist theo cấu hình môi trường thay vì mở rộng wildcard không cần thiết.

Có thể dùng annotation `@CrossOrigin` ở controller hoặc handler mapping cho cấu hình theo endpoint. Tuy nhiên, Spring Data REST tự tạo nhiều endpoint từ repository; cấu hình global hoặc cấu hình CORS phù hợp cho repository REST thường dễ quản lý nhất. Hãy xác nhận cấu hình áp dụng cho cả collection, item, search và association resources.

Không nên đồng thời tạo nhiều cấu hình CORS mâu thuẫn giữa proxy, Spring MVC và Spring Security. Browser cần nhận một bộ response headers nhất quán trên response cuối cùng.

## 8. Cấu hình CORS khi dùng Spring Security

Nếu ứng dụng dùng Spring Security, CORS phải được xử lý trước khi security filter từ chối request preflight. Preflight thường không gửi cookie/session của request thực tế, nên một rule yêu cầu authenticated cho mọi OPTIONS có thể làm preflight thất bại nếu CORS chưa được xử lý đúng.

Có thể khai báo một `CorsConfigurationSource` và bật CORS trong `SecurityFilterChain`:

```java
@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();

    config.setAllowedOrigins(
        List.of("https://app.example.test")
    );
    config.setAllowedMethods(
        List.of("GET", "POST", "PUT", "PATCH",
                "DELETE", "OPTIONS")
    );
    config.setAllowedHeaders(
        List.of("Authorization", "Content-Type",
                "Accept", "X-Request-ID")
    );
    config.setExposedHeaders(
        List.of("ETag", "Location")
    );
    config.setAllowCredentials(true);
    config.setMaxAge(3600L);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/**", config);
    return source;
}

@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {
    http
        .cors(Customizer.withDefaults())
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        );

    return http.build();
}
```

Cấu hình minh họa dùng Spring Security hiện đại. Import và API cụ thể phụ thuộc phiên bản. Có thể cấu hình CORS qua MVC và để Spring Security sử dụng cấu hình MVC nếu ứng dụng đã thiết lập đúng; hoặc cung cấp `CorsConfigurationSource` như trên. Chọn một nguồn cấu hình rõ ràng và kiểm thử trong toàn bộ filter chain.

Không nên thêm một rule cho phép mọi OPTIONS rồi coi như đã cấu hình CORS. Browser cần các response headers CORS hợp lệ, không chỉ status 200 hoặc 204. Cũng không nên tắt toàn bộ security để giải quyết lỗi preflight.

## 9. CORS không phải authentication, authorization hoặc CSRF protection

CORS chỉ quyết định browser có cho JavaScript của origin khác đọc response hay không. Nó không xác thực người dùng, không kiểm tra quyền nghiệp vụ và không ngăn mọi client gửi request trực tiếp.

Cần phân biệt:

- **Authentication:** xác định caller là ai, ví dụ session hoặc bearer token.
- **Authorization:** quyết định caller có quyền đọc, tạo, sửa, xóa hoặc liên kết resource hay không.
- **CORS:** quyết định browser có cho script từ origin khác truy cập response hay không.
- **CSRF protection:** giảm nguy cơ website khác lợi dụng credentials tự động được browser gửi để thực hiện thao tác ngoài ý muốn.

Một simple cross-origin request có thể được gửi đến server ngay cả khi browser sau đó chặn JavaScript đọc response. Do đó, không dựa vào CORS như hàng rào duy nhất chống CSRF. Với cookie/session authentication, vẫn phải cấu hình CSRF protection phù hợp cho request thay đổi trạng thái. Nếu dùng bearer token trong Authorization header, hãy thiết kế authentication và CSRF policy theo cách token được lưu trữ và gửi đi thực tế.

CORS cũng không áp dụng theo cách tương tự cho mọi HTTP client. cURL, backend service hoặc ứng dụng native không bị browser Same-Origin Policy thực thi. Một request chạy được bằng cURL nhưng thất bại trong browser thường cho thấy vấn đề ở CORS policy hoặc browser credentials, không nhất thiết là endpoint Spring Data REST bị lỗi.

## 10. Những lỗi CORS thường gặp

| Triệu chứng | Nguyên nhân có thể gặp | Cách kiểm tra |
|---|---|---|
| Không có `Access-Control-Allow-Origin` | Origin chưa được allowlist hoặc response lỗi không đi qua CORS handler | Kiểm tra Origin request và cấu hình mapping |
| Preflight trả 401/403 | Security filter từ chối OPTIONS trước khi CORS xử lý | Bật CORS trong SecurityFilterChain và kiểm tra filter order |
| Preflight không cho phép PATCH/DELETE | Method thiếu trong `Access-Control-Allow-Methods` | Thêm đúng method vào allowlist |
| Preflight không cho phép Content-Type/Authorization | Header thiếu trong `Access-Control-Allow-Headers` | Khai báo header request cần dùng |
| Credentialed request bị browser chặn | Dùng wildcard origin hoặc thiếu `Access-Control-Allow-Credentials: true` | Trả origin cụ thể và bật credentials có chủ đích |
| JavaScript không đọc được ETag hoặc Location | Header chưa được expose | Thêm header vào `Access-Control-Expose-Headers` |
| cURL chạy được nhưng browser lỗi | cURL không thực thi CORS như browser | Kiểm tra Network panel và response CORS headers |
| Chỉ một số endpoint bị lỗi | CORS mapping không bao phủ search/association/error path hoặc có proxy ghi đè header | Kiểm tra URL thực tế và response cuối cùng |

Một preflight thành công chưa bảo đảm request thực tế sẽ thành công. Request thật vẫn có thể nhận 401, 403, 404, 409, 415 hoặc lỗi validation theo API contract. Ngược lại, một response nghiệp vụ 400/500 vẫn cần CORS headers phù hợp nếu browser phải đọc được body lỗi.

## 11. Quy trình debug trong browser

Khi gặp lỗi CORS với Spring Data REST, thực hiện theo thứ tự:

1. Mở Developer Tools và chọn tab Network.
2. Tìm request OPTIONS có cùng URL với request API bị lỗi.
3. Kiểm tra request headers: `Origin`, `Access-Control-Request-Method` và `Access-Control-Request-Headers`.
4. Kiểm tra status và response headers của OPTIONS: `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers` và `Access-Control-Allow-Credentials` nếu dùng credentials.
5. Nếu preflight thành công, kiểm tra request thực tế có được gửi hay không.
6. Nếu request thực tế được gửi, đọc status và body của response; đây có thể là lỗi authentication, authorization, validation hoặc persistence độc lập với CORS.
7. Kiểm tra response có đi qua proxy/gateway và CORS headers có bị mất hoặc bị thêm trùng hay không.
8. Khi thay đổi policy, cân nhắc cache preflight và thử lại sau khi cache hết hạn hoặc trong browser session phù hợp.

Có thể mô phỏng preflight bằng cURL để xem server trả header gì:

```bash
curl -i -X OPTIONS \
  -H "Origin: https://app.example.test" \
  -H "Access-Control-Request-Method: PATCH" \
  -H "Access-Control-Request-Headers: content-type,authorization" \
  https://api.example.test/people/42
```

cURL chỉ hiển thị response; nó không thực thi chính sách CORS thay browser. Kết quả này hữu ích để kiểm tra cấu hình server, còn kết luận cuối cùng cần quan sát request từ browser thật.

## 12. Checklist cấu hình CORS cho Spring Data REST

1. Xác định chính xác scheme, host và port của từng frontend origin.
2. Phân biệt origin với site; khác subdomain hoặc port vẫn là cross-origin.
3. Chỉ allowlist các origin thực sự cần truy cập.
4. Khai báo đúng method, request headers và exposed response headers.
5. Nếu dùng cookie/session, cấu hình credentials với origin cụ thể; kiểm tra thêm thuộc tính SameSite và Secure của cookie.
6. Khi dùng Spring Security, xử lý CORS trước khi authorization từ chối preflight.
7. Bao phủ collection, item, search và association endpoints của Spring Data REST.
8. Giữ authentication, authorization và CSRF protection độc lập với CORS.
9. Kiểm thử cả simple request, preflight, credentialed request và response lỗi.
10. Kiểm tra response cuối qua proxy/gateway và xử lý `Vary: Origin` khi origin được chọn động.

SOP mặc định giới hạn việc script đọc dữ liệu giữa các origin. CORS cho phép Spring Data REST công bố một allowlist có kiểm soát để frontend khác origin truy cập API. Browser dùng simple request khi các điều kiện safelist được đáp ứng; nếu không, nó gửi OPTIONS preflight để kiểm tra method và headers dự kiến. Cấu hình đúng ở Spring MVC/Spring Security, đồng thời giữ authentication, authorization và CSRF riêng biệt, giúp tích hợp frontend/API rõ ràng và an toàn hơn.
