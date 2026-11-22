# Yêu cầu có nhiều token, token rỗng và cú pháp không hợp lệ trong Bearer Token

## 1. Vấn đề cần giải quyết

Một **Spring Security OAuth 2.0 Resource Server** thường nhận access token từ HTTP request để bảo vệ API. Với cơ chế **Bearer**, client thông thường gửi token trong header:

```http
GET /api/orders/123 HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIxMjMifQ.signature
```

Trong hệ thống thực tế, request không phải lúc nào cũng đúng khuôn dạng. Client hoặc proxy có thể gửi **hai token**, gửi `Authorization: Bearer` nhưng không có giá trị token, truyền một chuỗi bị lỗi khi ghép header, hoặc gửi đồng thời token qua header và query/body. Nếu API xử lý không nhất quán, có thể xuất hiện lỗi xác thực khó đoán, bỏ qua token sai hoặc nghiêm trọng hơn là **mỗi tầng hệ thống hiểu một token khác nhau**.

Bài này giải thích cách nhận diện và xử lý ba nhóm tình huống:

1. **Nhiều token trong một request**: nhiều header `Authorization`, nhiều giá trị bearer hoặc phối hợp các vị trí truyền token.
2. **Token rỗng hoặc vắng mặt**: phân biệt không cung cấp token với việc cố cung cấp Bearer nhưng bỏ trống phần giá trị.
3. **Cú pháp không hợp lệ**: sai định dạng của HTTP Authorization header, khác với token có cú pháp hợp lệ nhưng không qua kiểm tra chữ ký/thời hạn/issuer.

Phạm vi là **access token gửi đến Resource Server**. ID token của OIDC dành cho client xử lý đăng nhập; refresh token dùng ở token endpoint của Authorization Server. Không dùng hai loại đó để thay Bearer access token khi gọi API nghiệp vụ.

## 2. Quy tắc của Bearer token trong HTTP

### 2.1. Dạng chuẩn của Authorization header

Theo **RFC 6750, Section 2.1**, cú pháp của Bearer credential được mô tả như sau:

```abnf
credentials = "Bearer" 1*SP b64token
b64token    = 1*( ALPHA / DIGIT /
                  "-" / "." / "_" / "~" / "+" / "/" ) *"="
```

Điều này có một số hệ quả thực hành:

- `Bearer` là tên **authentication scheme**; tên scheme trong HTTP không phân biệt chữ hoa/chữ thường.
- Giữa scheme và token phải có dấu cách `SP`. Cú pháp RFC cho phép một hoặc nhiều dấu cách, nhưng **parser cụ thể của framework có thể khắt khe hơn**.
- Giá trị token không được là chuỗi rỗng.
- Ký tự thuộc tập `b64token` ở trên; dấu `=` chỉ được xuất hiện ở cuối theo dạng padding.
- Không dùng dấu phẩy để liệt kê nhiều Bearer credential, không bọc token trong dấu nháy, không thêm tiền tố `Bearer` thứ hai sau dấu phẩy.
- **Cú pháp đúng không chứng minh token hợp lệ**: `Bearer abc` có thể vượt bước tách token nhưng vẫn bị từ chối khi Resource Server xác thực.

Các ví dụ sau giúp phân biệt việc *đọc được giá trị* với *xác thực được giá trị*:

| Header | Nhận xét |
|---|---|
| `Authorization: Bearer abc.def.ghi` | Cú pháp Bearer phù hợp; JWT thật vẫn phải được kiểm tra |
| `Authorization: bearer abc` | Tên scheme không phân biệt hoa/thường |
| `Authorization: Bearer abc` | Cú pháp có thể hợp lệ dù `abc` không phải JWT hợp lệ |
| `Authorization: Bearer` | Thiếu giá trị token |
| `Authorization: Bearer ` | Giá trị token rỗng |
| `Authorization: Bearer "abc"` | Đặt token trong dấu nháy, sai dạng `b64token` |
| `Authorization: Bearer abc def` | Giá trị chứa dấu cách, không đúng cú pháp |
| `Authorization: Bearer abc,Bearer def` | Cố gộp nhiều credential bằng dấu phẩy |
| `Authorization: Basic YTpi` | Đây là scheme khác; không phải Bearer token |
| Không có `Authorization` | Không cung cấp credential theo header |

RFC 6750 mô tả các cơ chế truyền bearer access token khác, nhưng **khuyến nghị dùng `Authorization` header**. Đưa token vào query string có nguy cơ xuất hiện trong URL log, lịch sử trình duyệt, referrer và các thành phần giám sát. Spring Security mặc định chỉ tìm bearer token trong header; các đường truyền thay thế phải bật rõ ràng.

### 2.2. Một request nên có một nguồn token rõ ràng

Trong RFC 6750, một request **không được sử dụng nhiều hơn một phương thức** để truyền access token. Ví dụ không đồng thời gửi `Authorization: Bearer ...` và tham số `access_token=...` trong query hoặc form body.

Ngay cả khi hai vị trí chứa cùng giá trị, request vẫn mơ hồ về nguồn credential, nhất là khi API gateway, proxy và backend áp dụng parser khác nhau. Không tự đặt quy tắc “ưu tiên header” hay “lấy token cuối cùng” nếu hợp đồng bảo mật yêu cầu một nguồn duy nhất.

## 3. Yêu cầu chứa nhiều token

### 3.1. Hai header Authorization riêng biệt

Ví dụ request có thể xuất hiện ở phía client:

```http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer token-A
Authorization: Bearer token-B
```

Đây là trường hợp cần từ chối theo chính sách đầu vào thống nhất: client đang cung cấp **hơn một credential trong cùng loại header**. Tuy nhiên, phải hiểu hành vi của các tầng HTTP:

- HTTP client, reverse proxy hoặc servlet container có thể **giữ hai giá trị**, **gộp thành một giá trị** hoặc xử lý trùng header theo cách riêng.
- Trong Servlet API, `request.getHeader("Authorization")` thường trả về **giá trị đầu tiên**. Lấy một giá trị bằng `getHeader` không đảm bảo đã phát hiện các header lặp.
- `request.getHeaders("Authorization")` cho phép xét các giá trị mà container còn giữ lại; bộ lọc ở gateway có thể cần phát hiện và từ chối trùng header **trước khi tới ứng dụng**.
- Không giả định Spring Security mặc định luôn nhận ra mọi dạng duplicate `Authorization` đi qua proxy. Việc kiểm tra phải được đặt tại đúng tầng còn quan sát được request ban đầu.

Nếu hệ thống gồm API gateway và Resource Server, nên áp dụng chính sách nhất quán: **một Authorization header chứa một Bearer credential**. Nếu có nhiều giá trị, từ chối tại điểm vào tin cậy.

### 3.2. Hai token trong cùng một header

```http
Authorization: Bearer token-A, Bearer token-B
```

Đây không phải cú pháp hợp lệ của Bearer credential. Không dùng `split(",")` rồi chọn một token: dấu phẩy không phải ký hiệu hợp lệ để truyền danh sách Bearer token trong header đó. Parser nên từ chối giá trị sai.

Một biến thể khác:

```http
Authorization: Bearer token-A token-B
```

Dấu cách nằm bên trong chuỗi token làm credential sai cú pháp. Không nối hai phần lại, không bỏ qua phần token thứ hai.

### 3.3. Có Bearer header và query parameter

```http
GET /api/orders?access_token=token-B HTTP/1.1
Host: api.example.com
Authorization: Bearer token-A
```

Theo RFC 6750, client đang dùng **hai phương thức truyền access token**. Với Spring Security:

- **Mặc định** `DefaultBearerTokenResolver` không đọc bearer token từ query, nên tham số đó không tự động tạo ra lỗi “nhiều token” tại resolver. Header vẫn là nguồn token mặc định.
- Nếu bật `setAllowUriQueryParameter(true)`, resolver có thể phát hiện đồng thời token trong header và query rồi từ chối bằng lỗi `invalid_request`.
- Một API muốn **cấm hoàn toàn** query `access_token` (kể cả khi resolver không sử dụng nó) cần chính sách kiểm tra đầu vào ở lớp ứng dụng/gateway. Không hiểu “không đọc query” thành “đã chủ động từ chối mọi request có query token”.

Trong phần lớn API, giữ cấu hình mặc định và yêu cầu client truyền token bằng header là lựa chọn dễ quản lý hơn.

### 3.4. Có Bearer header và form body parameter

Khi body parameter được cho phép, một request có thể chứa hai nguồn:

```http
POST /api/orders/search HTTP/1.1
Host: api.example.com
Authorization: Bearer token-A
Content-Type: application/x-www-form-urlencoded

access_token=token-B&state=open
```

Nếu cấu hình cho phép đọc `access_token` từ form body, trường hợp đồng thời có bearer header phải được xem là **nhiều token** và bị từ chối. Theo RFC 6750, phương thức form body chỉ dùng trong các điều kiện được mô tả tại Section 2.2 (chẳng hạn body có kiểu `application/x-www-form-urlencoded`); không coi một field JSON tên `access_token` là cơ chế truyền bearer token chuẩn.

Spring Security mặc định **không bật** cách truyền token qua form body. Chỉ bật nếu yêu cầu tương thích bắt buộc và hiểu rõ tác động của việc đọc tham số request.

### 3.5. Tham số access_token lặp lại

```http
GET /api/orders?access_token=token-A&access_token=token-B HTTP/1.1
Host: api.example.com
```

Khi hệ thống cho phép query parameter, việc lặp cùng tên tham số khiến parser khó biết giá trị nào được chọn. Không xử lý bằng cách lấy token đầu tiên/cuối cùng tùy ý. Tương tự với các tham số form body lặp tên. Với HTTP parameter parsing, các giá trị lặp có thể được lấy qua `getParameterValues("access_token")`; nếu chấp nhận kênh này, cần chính sách từ chối trường hợp mơ hồ.

**Tình huống quan trọng:** bật một kênh truyền token khác có thể làm thay đổi cách ứng dụng hiểu request vốn đã chạy trước đó. Hãy coi thay đổi này như thay đổi giao thức đầu vào, cần sự nhất quán giữa các thành phần.

## 4. Token rỗng, thiếu token và không có Bearer credential

Một lỗi thường gặp là coi mọi trường hợp không trích xuất được token giống nhau. Thực tế có ít nhất ba loại:

| Tình huống | Request | Ý nghĩa |
|---|---|---|
| Không gửi Authorization | Không có header | Client chưa cung cấp Bearer credential |
| Header không phải Bearer | `Authorization: Basic ...` | Có credential scheme khác; Bearer resolver thông thường không trích xuất token |
| Cố gửi Bearer nhưng thiếu giá trị | `Authorization: Bearer` hoặc `Bearer ` | Request có ý định dùng Bearer nhưng credential **không hợp lệ** |
| Token được tạo từ giá trị rỗng | `Authorization: Bearer ${token}` khi biến trống | Lỗi xây dựng request ở client |
| Giá trị literal `null`/`undefined` | `Authorization: Bearer null` | Chuỗi **không rỗng**, cú pháp Bearer có thể hợp lệ nhưng giá trị không phải access token có thể xác thực |

Phân biệt này có ích khi trả response và truy tìm nguyên nhân.

### 4.1. Không gửi token

```http
GET /api/orders HTTP/1.1
Host: api.example.com
```

Resolver thông thường trả về `null` khi không thấy Bearer credential. Request đi tiếp trong filter chain. Nếu endpoint yêu cầu xác thực, Spring Security sau đó thường trả **401** và challenge Bearer. Nếu endpoint cho phép anonymous, request có thể được xử lý bình thường. **Resolver trả về null không tự đồng nghĩa request bị từ chối ngay lập tức.**

### 4.2. Gửi Bearer nhưng không có giá trị

```http
Authorization: Bearer
```

hoặc:

```http
Authorization: Bearer 
```

Đây là credential Bearer sai cú pháp. Với `DefaultBearerTokenResolver` của Spring Security, giá trị bắt đầu bằng `Bearer` nhưng không khớp mẫu hợp lệ thường tạo `OAuth2AuthenticationException` với lỗi `invalid_token`, sau đó tầng xử lý lỗi của Resource Server thường trả **401 Unauthorized**.

Đừng âm thầm chuyển trường hợp này thành anonymous hoặc đoán token khác từ query/cookie. Nếu client cố gắng gửi Bearer rỗng, cần sửa logic tạo request ở client.

### 4.3. Giá trị token có whitespace

```http
Authorization: Bearer    
```

Dấu cách không tạo thành giá trị token. Các biến thể chứa newline, tab không đúng vị trí, khoảng trắng đuôi, hoặc dấu cách xen giữa chuỗi token phải được xử lý theo parser HTTP/bearer đã cấu hình; không dùng `trim()` rồi tự sửa một credential tùy tiện. Một tầng có thể chuẩn hóa whitespace trong khi tầng khác không chuẩn hóa, vì vậy sự thống nhất là quan trọng.

## 5. Cú pháp header sai khác token không hợp lệ

Một Resource Server xử lý request qua hai bước khái niệm:

```text
HTTP request
    |
    v
[Bước 1] Trích xuất Bearer credential
    |  - Có header không?
    |  - Scheme/cấu trúc có nhận diện được không?
    |  - Có nhiều nguồn hoặc nhiều giá trị không?
    |
    +-- Sai ở bước 1 --> Lỗi định dạng/truyền token
    |
    v
[Bước 2] Xác thực access token đã trích xuất
       - JWT: signature, issuer, thời hạn, audience, các validator
       - Opaque: introspection và trạng thái/hợp đồng token
       - Sau đó: scope/authority và quyền nghiệp vụ
    |
    +-- Sai token --> Lỗi xác thực/quyền
    |
    v
Endpoint được phép xử lý
```

**Ví dụ 1: sai cấu trúc HTTP**

```http
Authorization: Bearer abc def
```

Bước trích xuất thất bại vì chuỗi chứa dấu cách nội bộ.

**Ví dụ 2: cấu trúc đúng nhưng access token giả**

```http
Authorization: Bearer abc.def.ghi
```

Giá trị này phù hợp tập ký tự và có dấu chấm, nhưng việc có ba phần **không chứng minh đây là JWT hợp lệ**. JWT decoder có thể từ chối vì Base64URL/JSON/chữ ký/thuật toán hoặc các claim sai.

**Ví dụ 3: token có chữ ký hợp lệ nhưng không dành cho API**

Một JWT access token của `catalog-api` có `aud=catalog-api` không được dùng để gọi `orders-api` nếu API yêu cầu audience riêng. Cần kiểm tra audience, issuer và phạm vi quyền **sau khi** tách token. Tương tự, ID token OIDC có `aud=web-client` không phải access token cho API, kể cả nó là JWT có chữ ký đúng.

**Ví dụ 4: access token còn hiệu lực nhưng thiếu scope**

Token hợp lệ để xác thực vẫn có thể không cho phép `POST /api/orders`; khi đó hệ thống áp dụng chính sách authorization và thường trả **403 Forbidden**, không phải lỗi cú pháp token.

## 6. HTTP status và WWW-Authenticate

RFC 6750 Section 3 quy định cách Resource Server thông báo lỗi qua **`WWW-Authenticate`** với Bearer scheme. Các mã lỗi quan trọng:

| Lỗi | Ngữ cảnh điển hình | HTTP status thường dùng |
|---|---|---|
| Không có credential khi API yêu cầu | Client chưa gửi Bearer token | **401 Unauthorized**, thường có Bearer challenge, có thể không có `error` |
| `invalid_request` | Request sai cấu trúc, dùng hơn một cơ chế truyền token, tham số lặp hoặc không được hỗ trợ | **400 Bad Request** theo RFC 6750 |
| `invalid_token` | Access token đã hết hạn, bị thu hồi, không đúng hoặc không thể xác thực | **401 Unauthorized** |
| `insufficient_scope` | Access token hợp lệ nhưng không đủ quyền được yêu cầu | **403 Forbidden** |

Ví dụ challenge, các thông tin hiển thị tùy cấu hình:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token", error_description="Bearer token is malformed"
```

```http
HTTP/1.1 400 Bad Request
WWW-Authenticate: Bearer error="invalid_request", error_description="Found multiple bearer tokens in the request"
```

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

**Cần phân biệt quy tắc RFC với mapping thực tế của framework.** Theo RFC, request malformed thường thuộc `invalid_request` với 400. Nhưng `DefaultBearerTokenResolver` của Spring Security xử lý Bearer header không khớp mẫu bằng `invalid_token`, dẫn tới 401 trong cấu hình thông thường. Từng ngoại lệ và response cuối cùng còn phụ thuộc security filter chain, entry point và cấu hình riêng. Vì vậy không nên viết client theo giả định rằng mọi dấu cách thừa đều chắc chắn trả 400.

`error_description` là thông tin giúp client sửa lỗi, không phải nơi chứa token gốc. **Không đưa nguyên access token, header Authorization hoặc dữ liệu nhạy cảm vào response lỗi**.

## 7. Spring Security xử lý Bearer token ở đâu?

Với Spring Security Servlet Resource Server, luồng điển hình là:

1. **`BearerTokenAuthenticationFilter`** gọi `BearerTokenResolver` để tìm token.
2. **`DefaultBearerTokenResolver`** mặc định đọc `Authorization` header và kiểm tra cấu trúc Bearer.
3. Nếu không có Bearer token, filter tiếp tục filter chain; quyết định cho anonymous hay bắt buộc xác thực do cấu hình endpoint.
4. Nếu resolver ném `OAuth2AuthenticationException`, filter chuyển tới cơ chế trả lỗi xác thực (ví dụ `BearerTokenAuthenticationEntryPoint`).
5. Nếu đã trích xuất token, `AuthenticationManager` dùng JWT decoder hoặc opaque introspection để xác thực.
6. Khi token hợp lệ, Spring Security tạo `Authentication` và áp dụng chính sách authorization của endpoint.

Đối với JWT và opaque token, **bước trích xuất token từ HTTP về cơ bản giống nhau**. Sự khác biệt nằm ở bước xác thực nội dung token (giải mã/xác minh JWT so với introspection).

### 7.1. Cấu hình mặc định: chỉ chấp nhận Bearer header

Ví dụ ứng dụng Spring Boot bảo vệ endpoint bằng JWT:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.com/realms/demo
```

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfig {

    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/public/**").permitAll()
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}
```

Trong cấu hình này, `DefaultBearerTokenResolver` mặc định:

- Tìm token trong `Authorization` header.
- Không cho phép lấy `access_token` từ URI query parameter.
- Không cho phép lấy `access_token` từ form-encoded body parameter.
- Dùng mẫu Bearer header cụ thể, có thể từ chối một số cách viết dù ngữ pháp RFC linh hoạt hơn; ví dụ RFC cho phép nhiều dấu `SP` còn parser mặc định thông thường đòi đúng một dấu cách sau `Bearer`.
- Báo lỗi với giá trị Bearer malformed thay vì coi nó là credential hợp lệ.

Các thiết lập trên **chỉ mô tả quá trình chọn bearer token**. API còn cần cấu hình validator audience, issuer, thời hạn và các quyền truy cập đúng hợp đồng của hệ thống.

### 7.2. Khi bật query hoặc form body

Spring Security cung cấp các setter trên `DefaultBearerTokenResolver`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.resource.web.BearerTokenResolver;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;

@Bean
BearerTokenResolver bearerTokenResolver() {
    DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();

    // Giữ giá trị mặc định an toàn: chỉ đọc Bearer trong header.
    resolver.setAllowUriQueryParameter(false);
    resolver.setAllowFormEncodedBodyParameter(false);

    return resolver;
}
```

Nếu cần bật một cơ chế khác vì giao thức cũ, các API `setAllowUriQueryParameter(true)` hoặc `setAllowFormEncodedBodyParameter(true)` thay đổi hành vi trích xuất token. Khi đó phải xác định rõ cách xử lý request có **nhiều vị trí token**, tham số trùng tên và tác động tới logging. Không bật cả hai chỉ để “cho client gửi tùy ý”.

Để dùng bean `BearerTokenResolver` riêng trong security chain:

```java
@Bean
SecurityFilterChain api(HttpSecurity http,
        BearerTokenResolver bearerTokenResolver) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                    .bearerTokenResolver(bearerTokenResolver)
                    .jwt(Customizer.withDefaults()))
            .build();
}
```

Các đoạn mã ở mục này là **những lựa chọn cấu hình minh họa**; khi áp dụng, hợp nhất thành cấu hình nhất quán trong dự án và dùng một `SecurityFilterChain` thích hợp với đường dẫn API của bạn.

## 8. Chủ động từ chối hai Authorization header

Spring Security `DefaultBearerTokenResolver` tập trung vào token mà servlet request trả về khi đọc header. Trong môi trường có nguy cơ duplicate `Authorization`, có thể thêm một lớp kiểm tra trước khi ủy quyền phân tích giá trị cho resolver mặc định.

Ví dụ decorator cho ứng dụng chỉ hỗ trợ **một Authorization header**:

```java
import java.util.Enumeration;

import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.server.resource.BearerTokenErrors;
import org.springframework.security.oauth2.server.resource.web.BearerTokenResolver;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;

@Bean
BearerTokenResolver strictBearerTokenResolver() {
    DefaultBearerTokenResolver delegate = new DefaultBearerTokenResolver();

    return request -> {
        Enumeration<String> headers =
                request.getHeaders(HttpHeaders.AUTHORIZATION);
        int count = 0;
        while (headers != null && headers.hasMoreElements()) {
            headers.nextElement();
            count++;

            if (count > 1) {
                throw new OAuth2AuthenticationException(
                        BearerTokenErrors.invalidRequest(
                                "More than one Authorization header"));
            }
        }

        return delegate.resolve(request);
    };
}
```

Kết nối resolver vào DSL `oauth2ResourceServer(...)` theo ví dụ ở mục 7.2. Lúc này:

- Khi servlet container **còn giữ** hai giá trị `Authorization` tách biệt, resolver từ chối với `invalid_request`.
- Khi request có một header `Authorization: Bearer token-A, Bearer token-B`, delegate mặc định sẽ phát hiện Bearer credential sai mẫu.
- Khi request có đúng một Bearer header, delegate tiếp tục thực hiện kiểm tra cú pháp thông thường.
- Ví dụ áp dụng chính sách từ chối **mọi duplicate Authorization header**; nếu API còn hỗ trợ scheme khác hoặc đa security chain, phải đặt kiểm tra đúng phạm vi endpoint.

**Giới hạn cần hiểu:** nếu reverse proxy đã loại bỏ header thứ hai trước khi request tới ứng dụng, servlet filter không thể biết request ban đầu có duplicate. Vì thế chính sách ở **gateway/edge** và **ứng dụng** cần thống nhất. Không coi đoạn code trên là giải pháp thay thế hoàn toàn việc cấu hình gateway.

## 9. Ma trận các request và hành vi mong đợi

Bảng dưới đây đặt trong ngữ cảnh **API bảo vệ bằng Spring Security Resource Server với resolver mặc định** (query/body token chưa bật). Với cột status, các giá trị mô tả hành vi thường gặp khi endpoint bắt buộc xác thực; security chain tùy chỉnh có thể thay đổi kết quả.

| Input | Ở bước trích xuất Bearer | Kết quả thường gặp |
|---|---|---|
| Không có `Authorization` | Không tìm thấy token | Đi tiếp; endpoint bảo vệ thường trả 401/challenge |
| `Authorization: Basic ...` | Không phải Bearer scheme | Không trích xuất Bearer; endpoint bảo vệ thường trả 401/challenge |
| `Authorization: Bearer` | Header Bearer malformed | `invalid_token`, thường 401 |
| `Authorization: Bearer ` | Giá trị rỗng, malformed | `invalid_token`, thường 401 |
| `Authorization: Bearer abc def` | Có dấu cách bên trong token | `invalid_token`, thường 401 |
| `Authorization: Bearer "abc"` | Token có dấu nháy | `invalid_token`, thường 401 |
| `Authorization: Bearer abc, Bearer def` | Nhiều token trong một header, sai mẫu | `invalid_token`, thường 401 |
| `Authorization: Bearer abc` | Lấy được chuỗi `abc` | Qua bước trích xuất; JWT/opaque validator có thể trả 401 |
| Header Bearer + query `access_token` | Resolver mặc định **bỏ qua query** | Chỉ thử xác thực token trong header |
| Chỉ có query `access_token` | Resolver mặc định **không đọc query** | Endpoint bảo vệ thường trả 401/challenge |
| Header Bearer + form `access_token` | Resolver mặc định **không đọc form** | Chỉ thử xác thực token trong header |
| Hai header Authorization tách biệt | Phụ thuộc servlet/proxy và resolver | Nên chặn ở gateway hoặc resolver bổ sung |
| Token hợp lệ nhưng không đủ scope | Trích xuất và xác thực được token | Kiểm tra quyền thường trả 403 |

Nếu **đã bật** query/form parameter trong resolver, bảng thay đổi: request mang token ở cả header và phương thức được bật có thể bị phân loại `invalid_request` (thường 400). Khi truyền token qua một phương thức thay thế, các giới hạn của RFC 6750 và servlet request vẫn được áp dụng.

## 10. Minh họa tình huống từ client đến Resource Server

### 10.1. Client vô tình ghép hai token

Giả sử frontend đặt giá trị header hai lần vì một interceptor thêm token, còn lớp HTTP khác tiếp tục ghép token:

```text
Interceptor A: Authorization = "Bearer token-A"
Interceptor B: Authorization = "Bearer " + previousValue
Result:        Authorization = "Bearer Bearer token-A"
```

Request cuối cùng có hai phần `Bearer` trong một chuỗi, parser sẽ không thể trích xuất bearer credential hợp lệ. **Cách sửa** là bảo đảm chỉ có một nơi chịu trách nhiệm gắn `Authorization`, và không ghép thêm `Bearer ` trước header đã định dạng.

### 10.2. Client tạo token rỗng do race condition

```javascript
// Ví dụ lỗi: accessToken có thể là chuỗi rỗng ở thời điểm gửi request.
const headers = { Authorization: `Bearer ${accessToken ?? ""}` };
```

Nếu `accessToken` chưa có, request trở thành `Authorization: Bearer `, thường bị từ chối như Bearer credential malformed.

Sửa cách xây dựng request: chỉ gửi header nếu thực sự có một access token hợp lệ về mặt dữ liệu đầu vào:

```javascript
const headers = {};

if (typeof accessToken === "string" && accessToken.length > 0) {
  headers.Authorization = `Bearer ${accessToken}`;
}
```

Điều này chỉ tránh gửi giá trị rỗng; không thay bước xác thực của Resource Server. Nếu endpoint yêu cầu xác thực mà client chưa có token, ứng dụng vẫn cần thực hiện luồng đăng nhập/cấp quyền phù hợp trước khi gọi.

### 10.3. Gateway và backend nhận khác nhau

```text
Client
  |-- Authorization: Bearer token-A
  |-- Authorization: Bearer token-B
  v
Gateway  [có thể giữ, gộp hoặc chọn giá trị theo sản phẩm/cấu hình]
  |
  v
Resource Server [đọc những header còn lại sau gateway]
```

Nếu gateway xác thực `token-A` nhưng backend lại sử dụng `token-B`, danh tính/quyền mà hai tầng áp dụng có thể khác nhau. Đây là một lý do để **từ chối credential mơ hồ càng sớm càng tốt** và cấu hình các tầng theo cùng một quy tắc.

### 10.4. Bearer token syntactically valid nhưng là ID token

```http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer ID_TOKEN_CREATED_FOR_WEB_CLIENT
```

Nếu giá trị chỉ gồm các ký tự cho phép, parser có thể lấy được token; điều đó không có nghĩa API phải chấp nhận. API cần validation về issuer, audience, các yêu cầu access token của Authorization Server và quyền truy cập. Không xử lý lỗi loại token bằng cách nới lỏng parser hoặc bỏ qua audience.

## 11. Kiểm tra thủ công một API

Khi quan sát một endpoint đã cấu hình Resource Server, có thể tạo các request minh họa bằng cURL. Mỗi lệnh sau là một **kịch bản request**; HTTP status thực tế còn phụ thuộc server và security chain, không phải kết quả đã thực thi:

**Không có token:**

```bash
curl -i https://api.example.com/api/orders
```

**Bearer rỗng:**

```bash
curl -i -H 'Authorization: Bearer ' \
  https://api.example.com/api/orders
```

**Hai Bearer credential ghép trong một header:**

```bash
curl -i -H 'Authorization: Bearer token-A, Bearer token-B' \
  https://api.example.com/api/orders
```

**Cố gửi Authorization hai lần:**

```bash
curl -i \
  -H 'Authorization: Bearer token-A' \
  -H 'Authorization: Bearer token-B' \
  https://api.example.com/api/orders
```

Chú ý: HTTP client, reverse proxy và servlet container có thể chuẩn hóa duplicate header, nên việc kiểm chứng chính sách ở gateway cần quan sát đúng request tại tầng đó. Không in access token thật vào command history hoặc log khi thực hiện kiểm tra trong môi trường có dữ liệu thật.

**Header kèm query token:**

```bash
curl -i \
  -H 'Authorization: Bearer token-A' \
  'https://api.example.com/api/orders?access_token=token-B'
```

Với resolver mặc định, query token không phải nguồn xác thực; nếu môi trường cần **từ chối** sự hiện diện của query `access_token` thì phải triển khai quy tắc đó riêng.

## 12. Thiết kế xử lý lỗi và quan sát vận hành

### 12.1. Lỗi cần rõ nghĩa nhưng không rò rỉ credential

Thông tin chẩn đoán phù hợp:

- Lỗi trích xuất: header thiếu, Bearer rỗng, Bearer sai dạng, có nhiều nguồn.
- Lỗi xác thực: token không được issuer chấp nhận, quá hạn hoặc không dành cho API.
- Lỗi phân quyền: token đã xác thực nhưng thiếu quyền truy cập tài nguyên.

Thông tin **không nên đưa vào log/response**: toàn bộ bearer token, refresh token, header Authorization nguyên vẹn, giá trị `access_token` từ query hoặc body, dữ liệu định danh nhạy cảm không cần thiết.

Nếu cần đo đếm, có thể dùng các nhãn sự kiện như `missing_credentials`, `malformed_bearer`, `multiple_authorization_headers`, `multiple_token_sources`, `jwt_validation_failed`. Nên phân biệt lỗi ở resolver với lỗi ở decoder/introspector vì cách sửa ở client/gateway hoàn toàn khác nhau.

### 12.2. Đừng tự chữa request sai

Không khuyến khích các mẫu xử lý sau:

```java
// Sai hướng: tự chọn phần cuối của một header mơ hồ.
String token = authorization.substring(
        authorization.lastIndexOf("Bearer ") + "Bearer ".length());

// Sai hướng: lỗi Bearer rỗng thì tự thử tìm trong query hoặc cookie.
// Sai hướng: thử từng token cho đến khi có một token xác thực được.
```

Những cách “chữa” này mở rộng bề mặt chấp nhận đầu vào, che giấu lỗi client và có thể tạo khác biệt giữa gateway với backend. Hãy quy định một định dạng request rõ ràng và trả lỗi thích hợp khi client vi phạm.

### 12.3. Chọn trách nhiệm theo từng tầng

| Tầng | Trách nhiệm phù hợp |
|---|---|
| **Client** | Chỉ gắn một header `Authorization: Bearer <access_token>` khi đã có token; không tự nối lặp |
| **API Gateway / Reverse Proxy** | Chuẩn hóa chính sách duplicate header, ngăn credential mơ hồ trước khi proxy tiếp |
| **BearerTokenResolver** | Xác định nguồn token và cú pháp Bearer; từ chối input không thể giải thích nhất quán |
| **JWT Decoder / Opaque Introspector** | Xác minh token được phát hành và còn hiệu lực theo hợp đồng issuer |
| **Authorization layer** | Kiểm tra scope/authority, tenant, quyền sở hữu tài nguyên và hành động cụ thể |
| **Error handling / Logging** | Trả status/challenge phù hợp, log lý do tối thiểu và không log token |

## 13. Quy tắc ghi nhớ

Đối với Spring Security OAuth 2.0 Resource Server:

1. **Một request, một Bearer access token, một nguồn rõ ràng.** Header `Authorization` là vị trí mặc định nên dùng.
2. **Không có token** khác **cố gửi Bearer rỗng**: trường hợp đầu có thể đi tiếp dưới dạng anonymous, trường hợp sau là credential sai.
3. **Sai cú pháp** khác **token đã trích xuất nhưng xác thực thất bại**: resolver và JWT decoder/introspector chịu trách nhiệm ở hai bước khác nhau.
4. **Nhiều Authorization header** cần xem xét cả gateway/proxy và servlet container; không dựa vào một lần gọi `getHeader` để kết luận không có header trùng.
5. **RFC 6750 và hành vi Spring Security không hoàn toàn đồng nhất ở mã lỗi của mọi tình huống malformed**: theo dõi `WWW-Authenticate`, `invalid_request`, `invalid_token` và response thực tế theo cấu hình ứng dụng.
6. **Đừng tìm cách sửa token sai trong backend** bằng chọn token đầu/cuối, cắt chuỗi tùy ý, hoặc thử lần lượt nhiều token.

Một Resource Server an toàn cần **chọn đúng một bearer credential**, **xác thực đúng access token dành cho API**, rồi **áp dụng phân quyền đối với tài nguyên đang yêu cầu**. Ba bước đó độc lập và đều cần thực hiện đúng.

## 14. Tài liệu tham khảo

- **RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage**, đặc biệt Sections 2.1–2.3 (truyền token), Section 3 (Bearer challenge và lỗi), Section 5 (cân nhắc bảo mật): https://www.rfc-editor.org/rfc/rfc6750
- **RFC 9110 — HTTP Semantics**, phần HTTP authentication, `Authorization` và `WWW-Authenticate`: https://www.rfc-editor.org/rfc/rfc9110
- **Spring Security Reference — OAuth 2.0 Resource Server**: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html
- **Spring Security API — `DefaultBearerTokenResolver`**: https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/web/DefaultBearerTokenResolver.html
- **Spring Security API — `BearerTokenAuthenticationFilter`**: https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/web/authentication/BearerTokenAuthenticationFilter.html
