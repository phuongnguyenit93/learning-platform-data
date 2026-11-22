# Method, header, cookie và thông tin xác thực với Spring WebClient

## 1. Mục tiêu: xây dựng request HTTP có đủ thông tin

`WebClient` là HTTP client reactive của Spring WebFlux. Nó cung cấp API fluent để chọn HTTP method, tạo URI, thêm headers, cookies, body và cách đọc response. Các thao tác được compose thành `Mono` hoặc `Flux`, vì vậy ứng dụng có thể gọi dịch vụ từ xa mà không cần chặn thread để chờ kết quả.

Một request outbound thường cần bốn nhóm thông tin:

1. **HTTP method và URI** xác định thao tác và resource đích.
2. **Headers** mô tả request, định dạng body, kiểu response mong muốn và metadata như trace ID.
3. **Cookies** gửi trạng thái phiên hoặc thông tin mà server yêu cầu qua cookie.
4. **Authentication** cung cấp credential theo cơ chế Basic, Bearer token, API key, cookie session hoặc OAuth2.

Bài học tập trung vào cách thiết lập từng nhóm bằng `WebClient`, phân biệt cấu hình mặc định với cấu hình theo request, dùng `ExchangeFilterFunction` cho hành vi dùng chung, quản lý credential an toàn và kiểm thử request thực tế.

Sau bài này, bạn có thể:

- Chọn method bằng các shortcut hoặc `method(HttpMethod)`.
- Tạo URI có path variable và query parameter.
- Thêm, thay thế và đặt header mặc định.
- Gửi cookie theo request và hiểu giới hạn của việc lưu cookie giữa nhiều lần gọi.
- Gửi Basic credentials, Bearer token và API key.
- Tích hợp OAuth2 Client reactive để lấy access token cho outbound request.
- Kiểm tra method, headers, cookies và authentication bằng một HTTP test server giả lập.

## 2. Cấu trúc một request WebClient

Một request thường được xây dựng theo chuỗi:

```java
Mono<Item> result = webClient.get()
        .uri("/items/{id}", "42")
        .accept(MediaType.APPLICATION_JSON)
        .header("X-Request-Id", "req-123")
        .retrieve()
        .bodyToMono(Item.class);
```

Các bước có ý nghĩa riêng:

- `get()` chọn HTTP method GET.
- `uri(...)` tạo URI đích và thay path variable.
- `accept(...)` đặt header `Accept`, cho biết client muốn nhận representation nào.
- `header(...)` thêm metadata tùy chỉnh.
- `retrieve()` bắt đầu luồng xử lý response theo API đơn giản.
- `bodyToMono(Item.class)` decode response body thành `Item`.

Request chưa được gửi chỉ vì gọi `get()`, `uri()` hoặc `header()`. Các lời gọi đó xây dựng request specification. HTTP exchange bắt đầu khi publisher được subscribe, thường do WebFlux hoặc một reactive pipeline ở tầng gọi quản lý.

Không gọi `.block()` trong controller/service reactive production. Có thể dùng `block(Duration)` trong chương trình nhỏ hoặc test đồng bộ, nhưng luồng ứng dụng WebFlux nên return và compose `Mono`/`Flux`.

### Tạo WebClient

```java
WebClient client = WebClient.builder()
        .baseUrl("https://inventory.example.com")
        .build();
```

Hoặc dùng factory:

```java
WebClient client = WebClient.create(
        "https://inventory.example.com");
```

`WebClient` sau khi build là immutable và có thể dùng lại giữa nhiều request. Nếu cần một biến thể với filter/header khác, có thể dùng `mutate()` để tạo builder mới rồi build client mới:

```java
WebClient partnerClient = client.mutate()
        .defaultHeader("X-Client-Name", "partner-adapter")
        .build();
```

Không tạo một `WebClient` mới cho mọi request nếu không có lý do. Tái sử dụng client giúp tận dụng connection pooling và cấu hình connector.

## 3. Chọn HTTP method và tạo URI

### 3.1. Các method shortcut

`WebClient` có shortcut cho các method thường dùng:

| API | HTTP method | Mục đích thường gặp |
|---|---|---|
| `get()` | GET | Đọc resource |
| `post()` | POST | Tạo resource hoặc thực hiện thao tác |
| `put()` | PUT | Thay thế representation của resource |
| `patch()` | PATCH | Cập nhật một phần resource |
| `delete()` | DELETE | Xóa resource |
| `head()` | HEAD | Lấy headers mà không cần response body |
| `options()` | OPTIONS | Hỏi khả năng/phương thức được hỗ trợ |

Ví dụ:

```java
Mono<Item> item = client.get()
        .uri("/items/{id}", "42")
        .retrieve()
        .bodyToMono(Item.class);

Mono<Item> created = client.post()
        .uri("/items")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(new CreateItem("Keyboard"))
        .retrieve()
        .bodyToMono(Item.class);

Mono<Void> deleted = client.delete()
        .uri("/items/{id}", "42")
        .retrieve()
        .bodyToMono(Void.class);
```

### 3.2. Chọn method động bằng `method(HttpMethod)`

Khi method được quyết định tại runtime hoặc được truyền từ một abstraction khác, dùng `method(...)`:

```java
HttpMethod method = HttpMethod.PATCH;

Mono<String> response = client.method(method)
        .uri("/items/{id}", "42")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(Map.of("displayName", "Mechanical keyboard"))
        .retrieve()
        .bodyToMono(String.class);
```

`method(HttpMethod)` trả về request specification phù hợp để tiếp tục thiết lập URI, headers và body. Chỉ cho phép method nằm trong danh sách mà ứng dụng hỗ trợ; không lấy một chuỗi tùy ý từ người dùng rồi dùng trực tiếp để điều khiển outbound request.

### 3.3. Path variable và query parameter

Có thể dùng URI template:

```java
client.get()
        .uri("/items/{id}", "item-42")
        .retrieve()
        .bodyToMono(Item.class);
```

Với query parameter, dùng `UriBuilder` để mã hóa giá trị đúng cách:

```java
client.get()
        .uri(uriBuilder -> uriBuilder
                .path("/items")
                .queryParam("category", "office supplies")
                .queryParam("page", 2)
                .queryParam("tag", "new")
                .queryParam("tag", "featured")
                .build())
        .retrieve()
        .bodyToFlux(Item.class);
```

Giá trị có khoảng trắng hoặc ký tự đặc biệt cần được URI builder encode. Tránh ghép query string bằng phép nối chuỗi vì dễ tạo URI sai hoặc làm lộ dữ liệu nhạy cảm trong URL.

### 3.4. Method, body và semantics HTTP

GET thường không gửi body. POST, PUT và PATCH thường có body; DELETE thường không cần body, dù một số API có contract riêng. Hãy tuân theo contract của server thay vì dựa vào việc client API có cho phép gọi một method nào đó với body hay không.

Các method có semantics khác nhau:

- GET được kỳ vọng là safe và không thay đổi trạng thái nghiệp vụ.
- PUT thường mang ý nghĩa thay thế resource tại URI.
- PATCH áp dụng thay đổi một phần; media type của patch phải theo contract, ví dụ JSON Merge Patch hoặc JSON Patch.
- POST thường không idempotent mặc định. Nếu retry POST, hãy cân nhắc idempotency key do API hỗ trợ.
- DELETE thường được thiết kế idempotent về hiệu ứng, dù response cho lần xóa tiếp theo có thể khác.

Không tự retry mọi request có lỗi mạng. Request có thể đã tới server và tạo side effect dù client không nhận được response.

## 4. Headers: thêm, thay thế và đặt mặc định

HTTP headers truyền metadata của request. Một số header phổ biến:

| Header | Ý nghĩa |
|---|---|
| `Accept` | Media type client muốn nhận |
| `Content-Type` | Media type của request body |
| `Authorization` | Credential theo authentication scheme |
| `Accept-Language` | Ngôn ngữ response mong muốn |
| `If-None-Match` | Conditional request theo ETag |
| `If-Modified-Since` | Conditional request theo thời điểm sửa đổi |
| `X-Request-Id` | Correlation/request ID theo contract nội bộ |
| `X-Api-Key` | API key nếu dịch vụ quy định header này |

### 4.1. Dùng các shortcut có sẵn

```java
client.get()
        .uri("/catalog")
        .accept(MediaType.APPLICATION_JSON)
        .acceptCharset(StandardCharsets.UTF_8)
        .header("Accept-Language", "vi-VN")
        .retrieve()
        .bodyToMono(String.class);
```

Với request có body:

```java
client.post()
        .uri("/items")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .bodyValue(new CreateItem("Keyboard"))
        .retrieve()
        .bodyToMono(Item.class);
```

`Content-Type` mô tả body đang gửi. `Accept` mô tả representation muốn nhận. Hai header có chiều giao tiếp khác nhau; không dùng một header thay cho header còn lại.

### 4.2. `header(...)` thêm giá trị

```java
client.get()
        .uri("/catalog")
        .header("X-Feature", "search")
        .header("X-Feature", "recommendations")
        .retrieve()
        .bodyToMono(String.class);
```

`header(name, values...)` thêm giá trị dưới tên header. Nếu header đã có giá trị, có thể tạo nhiều giá trị hoặc nhiều field value theo semantics của HTTP và header cụ thể.

Đừng dùng cách thêm lặp cho các header mà API yêu cầu một giá trị duy nhất như `Authorization`. Với những header đó, hãy dùng `headers(...)` và `set(...)` để thay thế giá trị hiện tại.

### 4.3. `headers(...)` để set, add hoặc remove

```java
client.get()
        .uri("/profile")
        .headers(headers -> {
            headers.set("X-Tenant", "tenant-42");
            headers.set("X-Request-Id", "req-2026-001");
            headers.remove("X-Debug-Only");
        })
        .retrieve()
        .bodyToMono(Profile.class);
```

`headers(Consumer<HttpHeaders>)` cho phép thao tác với `HttpHeaders` đã khai báo:

- `set(name, value)` thay các giá trị hiện có bằng một giá trị.
- `add(name, value)` thêm một giá trị.
- `remove(name)` xóa header.

Các helper authentication cũng nằm trên `HttpHeaders`, ví dụ `setBasicAuth(...)` và `setBearerAuth(...)`.

### 4.4. Default headers ở cấp WebClient

Nếu mọi request tới một dịch vụ đều cần cùng metadata, đặt default ở builder:

```java
WebClient inventoryClient = WebClient.builder()
        .baseUrl("https://inventory.example.com")
        .defaultHeader("X-Client-Name", "order-service")
        .defaultHeader(
                HttpHeaders.ACCEPT,
                MediaType.APPLICATION_JSON_VALUE)
        .build();
```

`defaultHeader` chỉ thêm header mặc định nếu request cụ thể chưa khai báo header đó. Vì vậy request có thể ghi đè bằng giá trị riêng:

```java
inventoryClient.get()
        .uri("/items")
        .header("X-Client-Name", "catalog-sync")
        .retrieve()
        .bodyToFlux(Item.class);
```

Tương tự, `defaultHeaders(...)` cho phép quản lý tập default header đã khai báo:

```java
WebClient client = WebClient.builder()
        .defaultHeaders(headers -> {
            headers.set("X-Client-Name", "report-service");
            headers.setAccept(List.of(MediaType.APPLICATION_JSON));
        })
        .build();
```

Không đặt user token hoặc cookie của một người dùng vào default header/cookie của một client dùng chung cho nhiều user hoặc nhiều host. Credential có thể bị gửi nhầm sang request khác nếu client được dùng với URI ngoài dự kiến.

### 4.5. Conditional headers

WebClient có helper cho một số conditional request:

```java
client.get()
        .uri("/documents/42")
        .ifNoneMatch("\"version-7\"")
        .retrieve()
        .bodyToMono(Document.class);
```

Hoặc:

```java
client.get()
        .uri("/documents/42")
        .ifModifiedSince(
                ZonedDateTime.parse("2026-10-01T00:00:00Z"))
        .retrieve()
        .toBodilessEntity();
```

Server có thể trả `304 Not Modified` nếu resource không đổi theo validator. Đây là cơ chế HTTP cache validation; nó không thay thế việc cache response ở ứng dụng.

### 4.6. Những header không nên tự đặt tùy tiện

Thông thường không tự đặt `Host`, `Content-Length`, `Connection` hoặc các hop-by-hop headers. HTTP connector chịu trách nhiệm tính toán và quản lý những header gắn với transport. Chỉ tùy chỉnh khi có yêu cầu cụ thể từ server/proxy và đã hiểu ảnh hưởng đến framing, connection reuse và streaming.

Header name không phân biệt chữ hoa/chữ thường theo HTTP. Tuy nhiên, không giả định mọi header value cũng không phân biệt chữ hoa/chữ thường; hãy theo semantics của header cụ thể.

## 5. Cookies: gửi session hoặc trạng thái theo request

Cookie là cặp tên/giá trị được gửi trong request header `Cookie`. Trong WebClient, dùng `cookie(...)` hoặc `cookies(...)`:

```java
client.get()
        .uri("/account")
        .cookie("SESSION", "session-token-value")
        .retrieve()
        .bodyToMono(Account.class);
```

Nhiều cookie:

```java
client.get()
        .uri("/preferences")
        .cookies(cookies -> {
            cookies.add("locale", "vi-VN");
            cookies.add("theme", "dark");
        })
        .retrieve()
        .bodyToMono(Preferences.class);
```

Dùng `cookie(name, value)` cho một cookie cụ thể; dùng `cookies(Consumer<MultiValueMap<String, String>>)` khi cần thêm, thay thế hoặc xóa nhiều cookie trong cùng request.

### 5.1. Default cookie

```java
WebClient client = WebClient.builder()
        .baseUrl("https://portal.example.com")
        .defaultCookie("client-locale", "vi-VN")
        .build();
```

Default cookie chỉ được thêm nếu request chưa có cookie cùng tên. Request cụ thể có thể cung cấp giá trị riêng:

```java
client.get()
        .uri("/settings")
        .cookie("client-locale", "en-US")
        .retrieve()
        .bodyToMono(Settings.class);
```

Không đặt cookie session của một user thành default cookie trên WebClient singleton dùng chung. Session của user phải được truyền theo request hoặc quản lý bởi một cookie store có phạm vi phù hợp.

### 5.2. `Cookie` và `Set-Cookie` là hai chiều khác nhau

- Request gửi `Cookie: SESSION=...` để cung cấp cookie đã có.
- Response gửi `Set-Cookie: SESSION=...; Path=/; HttpOnly; Secure; SameSite=Lax` để yêu cầu client lưu/cập nhật cookie.

`WebClient.cookie(...)` thiết lập cookie gửi đi. Các thuộc tính `HttpOnly`, `Secure`, `SameSite`, `Domain`, `Path` và `Expires` thuộc chỉ thị `Set-Cookie` do server trả về; không phải thuộc tính được gửi lại trong request `Cookie`.

Nếu cần duy trì phiên qua nhiều request, ứng dụng phải xác định cách lưu và gửi lại cookie nhận từ `Set-Cookie`. Không giả định API fluent của WebClient tự cung cấp một browser cookie jar portable cho mọi `ClientHttpConnector`. Có thể quản lý cookie trong application/session store hoặc cấu hình cookie store riêng của HTTP connector đang dùng.

### 5.3. Cookie không phải nơi lưu tùy tiện mọi dữ liệu

Cookie có thể được gửi ở mỗi request tới domain/path phù hợp. Tránh nhét dữ liệu lớn hoặc dữ liệu nhạy cảm không cần thiết vào cookie. Session cookie thường chứa một session identifier ngẫu nhiên; dữ liệu phiên thực tế được quản lý ở server hoặc session store.

Nếu server dùng cookie để xác thực, cần tuân theo chính sách của server. Với browser-facing application, server nên thiết lập `Secure`, `HttpOnly` và `SameSite` phù hợp. `WebClient` là HTTP client backend; việc gửi cookie không tự tạo ra các thuộc tính bảo vệ ở phía server.

## 6. Basic Authentication

HTTP Basic Authentication truyền username và password trong header:

```http
Authorization: Basic base64(username:password)
```

Base64 chỉ là encoding, không phải mã hóa bảo mật. Chỉ dùng Basic Authentication qua HTTPS/TLS.

### 6.1. Thiết lập cho một request

```java
client.get()
        .uri("/private/profile")
        .headers(headers ->
                headers.setBasicAuth("demo-user", "demo-password"))
        .retrieve()
        .bodyToMono(Profile.class);
```

`HttpHeaders.setBasicAuth(username, password)` tạo header Authorization theo Basic scheme.

### 6.2. Dùng filter cho một WebClient riêng

Spring cung cấp `ExchangeFilterFunctions.basicAuthentication(...)`:

```java
WebClient basicClient = WebClient.builder()
        .baseUrl("https://legacy.example.com")
        .filter(ExchangeFilterFunctions.basicAuthentication(
                "demo-user", "demo-password"))
        .build();
```

Mọi request qua client này sẽ được áp dụng Basic authentication filter. Nên giới hạn client ở một dịch vụ/origin đáng tin cậy; không dùng client có Basic credentials mặc định để gọi URL tùy ý.

Không hardcode username/password trong source code. Đọc credential từ secret manager hoặc cơ chế cấu hình an toàn của môi trường triển khai. Tránh log `Authorization` header hoặc cấu hình HTTP wiretap có thể ghi credential.

## 7. Bearer token và API key

### 7.1. Bearer token theo từng request

Bearer token thường được gửi qua header:

```http
Authorization: Bearer access-token
```

Dùng helper của `HttpHeaders`:

```java
client.get()
        .uri("/api/private/orders")
        .headers(headers ->
                headers.setBearerAuth(accessToken))
        .retrieve()
        .bodyToFlux(Order.class);
```

Token là credential có quyền truy cập resource. Bất kỳ bên nào sở hữu token đều có thể sử dụng token trong phạm vi quyền và thời hạn của nó. Không ghi token vào log, URL query string, exception message hoặc metric tag.

Nếu token thay đổi theo user/request, truyền token trong request đó hoặc dùng OAuth2 Client filter. Tránh lưu token động trong default header của client singleton.

### 7.2. API key trong custom header

Một số dịch vụ dùng API key:

```java
client.get()
        .uri("/v1/metrics")
        .header("X-Api-Key", apiKey)
        .retrieve()
        .bodyToMono(Metrics.class);
```

Tên header phải theo contract của nhà cung cấp API. Không mặc định mọi API đều dùng `X-Api-Key`; một số dịch vụ dùng header khác hoặc scheme riêng.

API key cũng là secret. Lưu trong secret manager/environment config, giới hạn quyền, xoay vòng định kỳ và tránh gửi sang host không tin cậy. Không đặt key trong query string vì URL thường xuất hiện trong access log, proxy log, tracing và lịch sử hệ thống.

### 7.3. Basic, Bearer, API key và cookie khác nhau thế nào?

| Cơ chế | Nơi gửi | Thông tin thường chứa | Quản lý vòng đời |
|---|---|---|---|
| Basic | `Authorization` | Username/password được encode | Credential tĩnh hoặc thay đổi theo chính sách |
| Bearer | `Authorization` | Access token | Có thời hạn; cần cấp mới/refresh theo OAuth2 flow |
| API key | Custom header theo contract | Key nhận diện ứng dụng/client | Secret được cấp, giới hạn và xoay vòng |
| Session cookie | `Cookie` | Session identifier | Server quản lý session và cookie expiry |

Không tự chọn scheme chỉ vì nó dễ viết. Hãy dùng cơ chế mà API đích hỗ trợ và tuân theo chính sách credential của hệ thống.

## 8. OAuth2 Client reactive với WebClient

Khi gọi API được bảo vệ bằng OAuth2, ứng dụng thường cần lấy access token từ authorization server, gắn Bearer token vào outbound request và quản lý việc hết hạn. Spring Security OAuth2 Client cung cấp `ReactiveOAuth2AuthorizedClientManager` và `ServerOAuth2AuthorizedClientExchangeFilterFunction` để tích hợp với WebClient.

Thêm dependency Spring Boot:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
```

Cấu hình một client registration, ví dụ dùng `client_credentials` cho giao tiếp service-to-service:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          inventory:
            provider: company-auth
            client-id: ${INVENTORY_CLIENT_ID}
            client-secret: ${INVENTORY_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope: inventory.read
        provider:
          company-auth:
            token-uri: https://auth.example.com/oauth2/token
```

Đây là cấu hình minh họa. Token URI, grant type, scope và credential phải khớp với authorization server thật. Không commit secret vào repository.

Cấu hình WebClient filter:

```java
@Configuration
public class OAuthWebClientConfiguration {

    @Bean
    WebClient inventoryWebClient(
            ReactiveOAuth2AuthorizedClientManager authorizedClientManager) {

        ServerOAuth2AuthorizedClientExchangeFilterFunction oauth =
                new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                        authorizedClientManager);

        return WebClient.builder()
                .baseUrl("https://inventory.example.com")
                .filter(oauth)
                .build();
    }
}
```

Khi gọi API, chọn client registration:

```java
import static org.springframework.security.oauth2.client.web.reactive.function.client
        .ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

Mono<Item> item = inventoryWebClient.get()
        .uri("/items/{id}", "42")
        .attributes(clientRegistrationId("inventory"))
        .retrieve()
        .bodyToMono(Item.class);
```

Filter dùng authorized client manager để lấy authorized client và đặt access token vào `Authorization: Bearer ...`. Cơ chế cấp mới/refresh phụ thuộc grant type và provider đã cấu hình. Với `client_credentials`, manager có thể lấy access token mới theo vòng đời token và provider.

### OAuth2 Client khác với chuyển tiếp token hiện tại

Có hai tình huống khác nhau:

- **OAuth2 Client**: ứng dụng chủ động được cấp quyền và lấy access token để gọi API khác. Dùng `ReactiveOAuth2AuthorizedClientManager` cùng `ServerOAuth2AuthorizedClientExchangeFilterFunction`.
- **Bearer token propagation**: request hiện tại đã được xác thực bằng Bearer token và ứng dụng muốn chuyển tiếp token đó tới dịch vụ downstream. Spring Security cung cấp `ServerBearerExchangeFilterFunction` cho mục đích này.

Bearer propagation không tự làm mới token đã hết hạn. Nếu cần authorization flow, token acquisition và refresh, hãy dùng OAuth2 Client.

## 9. `ExchangeFilterFunction`: áp dụng hành vi dùng chung

`ExchangeFilterFunction` cho phép chặn và sửa outbound request trước khi nó được gửi, hoặc quan sát response sau khi nhận. Filter phù hợp với metadata dùng chung như correlation ID, client name, metrics và authentication policy.

Ví dụ thêm header cho mọi request của một client:

```java
ExchangeFilterFunction clientNameFilter =
        (request, next) -> {
            ClientRequest filtered = ClientRequest.from(request)
                    .headers(headers ->
                            headers.set("X-Client-Name", "billing-service"))
                    .build();

            return next.exchange(filtered);
        };

WebClient client = WebClient.builder()
        .baseUrl("https://billing.example.com")
        .filter(clientNameFilter)
        .build();
```

`ClientRequest.from(request)` tạo builder dựa trên request hiện tại. Filter thay đổi header rồi gọi `next.exchange(filtered)` để tiếp tục chuỗi filter và gửi request.

### Filter tạo correlation ID

```java
ExchangeFilterFunction correlationFilter =
        (request, next) -> {
            String correlationId = UUID.randomUUID().toString();

            ClientRequest filtered = ClientRequest.from(request)
                    .headers(headers ->
                            headers.set("X-Correlation-Id", correlationId))
                    .build();

            return next.exchange(filtered);
        };
```

Trong ứng dụng có tracing, nên tích hợp Micrometer Observation/Tracing hoặc context propagation hiện có thay vì tạo correlation ID riêng không liên kết với trace. Ví dụ trên chỉ minh họa cách mutate request.

### Filter cần giữ reactive composition

`ExchangeFilterFunction.filter` trả về `Mono<ClientResponse>`. Hãy return publisher từ `next.exchange(...)` và compose operator cần thiết. Không tự gọi `.subscribe()` hoặc `.block()` trong filter.

Nếu filter đọc response body để quyết định retry hoặc refresh token, phải consume hoặc release body đúng cách trước khi gửi request tiếp theo. Nếu không, connection/buffer có thể bị giữ lại. Spring documentation có ví dụ xử lý 401 và gọi `response.releaseBody()` trước khi retry.

### Thứ tự filter

Có thể đăng ký nhiều filter trên builder:

```java
WebClient client = WebClient.builder()
        .filter(correlationFilter)
        .filter(clientNameFilter)
        .filter(authenticationFilter)
        .build();
```

Filter tạo thành một chain. Hãy đặt filter theo thứ tự phù hợp với dữ liệu mà filter sau cần đọc. Tránh filter logging toàn bộ headers vì có thể ghi lại `Authorization`, cookie session hoặc API key.

`WebClient` đã build là immutable. Dùng `mutate()` để tạo client mới nếu cần thay đổi filter list hoặc cấu hình.

## 10. Header, cookie và authentication theo từng request hay mặc định?

| Phạm vi | API | Khi nên dùng |
|---|---|---|
| Một request | `header`, `headers`, `cookie`, `cookies` | Tenant, user token, trace ID hoặc session cụ thể |
| Mọi request của client | `defaultHeader`, `defaultCookie` | Client name, locale mặc định hoặc header cố định |
| Logic xuyên suốt request | `ExchangeFilterFunction` | Correlation, metrics, authentication integration |
| Credential được quản lý | OAuth2 filter | Access token cần lấy/refresh theo registration |

Ví dụ một request có token và tenant riêng:

```java
Mono<Order> order = client.get()
        .uri("/orders/{id}", "order-42")
        .headers(headers -> {
            headers.setBearerAuth(accessToken);
            headers.set("X-Tenant-Id", tenantId);
        })
        .cookie("SESSION", sessionCookie)
        .retrieve()
        .bodyToMono(Order.class);
```

Không dùng default header cho credential có thể thay đổi theo user. Nếu một WebClient gọi nhiều host, không gắn credential nhạy cảm vào mọi request của client đó.

## 11. Xử lý response lỗi khi authentication thất bại

`retrieve()` mặc định chuyển response có status 4xx/5xx thành lỗi `WebClientResponseException`. Có thể xử lý riêng status 401/403:

```java
Mono<Profile> profile = client.get()
        .uri("/profile")
        .headers(headers ->
                headers.setBearerAuth(accessToken))
        .retrieve()
        .onStatus(
                status -> status.value() == 401,
                response -> response.createException())
        .onStatus(
                status -> status.value() == 403,
                response -> response.createException())
        .bodyToMono(Profile.class);
```

Ví dụ trên giữ exception từ response. Nếu cần fallback hoặc refresh token, hãy triển khai trong OAuth2 authorized client manager/filter hoặc một cơ chế có hiểu biết về credential. Không lặp request vô hạn khi nhận 401.

Ý nghĩa thường gặp:

- **401 Unauthorized**: credential thiếu, sai, hết hạn hoặc không được chấp nhận; API có thể yêu cầu xác thực lại.
- **403 Forbidden**: server hiểu danh tính/credential nhưng từ chối quyền thực hiện thao tác.

Một số API dùng status khác theo contract. Hãy đọc tài liệu của dịch vụ đích thay vì coi hai status trên là quy tắc duy nhất.

## 12. Dự án Java 17+ chạy được: kiểm thử method, header, cookie và auth

Dự án nhỏ dưới đây dùng Spring Boot 3.3.5, Java 17, WebFlux và OkHttp MockWebServer. MockWebServer chạy HTTP server cục bộ trong test, ghi lại request đã nhận và trả response giả lập. Test không cần gọi một API internet thật.

### 12.1. Cấu trúc

```text
webclient-request-metadata/
├── pom.xml
└── src/
    └── test/java/edu/demo/client/
        └── WebClientRequestTests.java
```

### 12.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>edu.demo</groupId>
    <artifactId>webclient-request-metadata</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
        <okhttp.version>4.12.0</okhttp.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>com.squareup.okhttp3</groupId>
            <artifactId>mockwebserver</artifactId>
            <version>${okhttp.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 12.3. `WebClientRequestTests.java`

```java
package edu.demo.client;

import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.ExchangeFilterFunctions;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class WebClientRequestTests {

    private MockWebServer server;
    private WebClient client;

    @BeforeEach
    void setUp() throws IOException {
        server = new MockWebServer();
        server.start();

        client = WebClient.builder()
                .baseUrl(server.url("/").toString())
                .build();
    }

    @AfterEach
    void tearDown() throws IOException {
        server.shutdown();
    }

    @Test
    void sendsMethodHeadersBearerTokenAndCookie() throws Exception {
        server.enqueue(new MockResponse()
                .addHeader("Content-Type", "application/json")
                .setBody("""
                        {"id":"42","name":"Keyboard"}
                        """));

        String body = """
                {"name":"Keyboard"}
                """;

        String response = client.method(HttpMethod.PATCH)
                .uri("/items/{id}", "42")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .header("X-Trace-Id", "trace-123")
                .headers(headers ->
                        headers.setBearerAuth("test-access-token"))
                .cookie("SESSION", "session-abc")
                .bodyValue(body)
                .retrieve()
                .bodyToMono(String.class)
                .block(Duration.ofSeconds(3));

        assertNotNull(response);
        assertTrue(response.contains("Keyboard"));

        RecordedRequest request =
                server.takeRequest(2, TimeUnit.SECONDS);

        assertNotNull(request);
        assertEquals("PATCH", request.getMethod());
        assertEquals("/items/42", request.getPath());
        assertEquals("trace-123",
                request.getHeader("X-Trace-Id"));
        assertEquals("Bearer test-access-token",
                request.getHeader(HttpHeaders.AUTHORIZATION));
        assertEquals("application/json",
                request.getHeader(HttpHeaders.CONTENT_TYPE));
        assertEquals("application/json",
                request.getHeader(HttpHeaders.ACCEPT));
        assertTrue(request.getHeader("Cookie")
                .contains("SESSION=session-abc"));
    }

    @Test
    void requestValuesTakePrecedenceOverDefaults() throws Exception {
        server.enqueue(new MockResponse()
                .addHeader("Content-Type", "text/plain")
                .setBody("ok"));

        WebClient withDefaults = WebClient.builder()
                .baseUrl(server.url("/").toString())
                .defaultHeader("X-Client-Name", "default-client")
                .defaultCookie("locale", "vi-VN")
                .build();

        withDefaults.get()
                .uri("/settings")
                .header("X-Client-Name", "request-client")
                .cookie("locale", "en-US")
                .retrieve()
                .bodyToMono(String.class)
                .block(Duration.ofSeconds(3));

        RecordedRequest request =
                server.takeRequest(2, TimeUnit.SECONDS);

        assertNotNull(request);
        assertEquals("request-client",
                request.getHeader("X-Client-Name"));

        String cookie = request.getHeader("Cookie");
        assertNotNull(cookie);
        assertTrue(cookie.contains("locale=en-US"));
        assertTrue(!cookie.contains("locale=vi-VN"));
    }

    @Test
    void basicAuthenticationFilterCreatesAuthorizationHeader()
            throws Exception {

        server.enqueue(new MockResponse()
                .addHeader("Content-Type", "text/plain")
                .setBody("authenticated"));

        WebClient basicClient = WebClient.builder()
                .baseUrl(server.url("/").toString())
                .filter(ExchangeFilterFunctions.basicAuthentication(
                        "demo-user", "demo-password"))
                .build();

        basicClient.get()
                .uri("/private")
                .retrieve()
                .bodyToMono(String.class)
                .block(Duration.ofSeconds(3));

        RecordedRequest request =
                server.takeRequest(2, TimeUnit.SECONDS);

        assertNotNull(request);
        assertEquals(
                "Basic ZGVtby11c2VyOmRlbW8tcGFzc3dvcmQ=",
                request.getHeader(HttpHeaders.AUTHORIZATION));
    }
}
```

Test dùng `block(Duration)` để đồng bộ hóa assertion trong JUnit. Đây là ranh giới test; code reactive trong ứng dụng production nên compose publisher thay vì block.

### 12.4. Chạy test

Từ thư mục chứa `pom.xml`:

```bash
mvn test
```

Khi Maven tải được dependencies và các assertion đúng, Surefire sẽ chạy ba test:

1. Request PATCH gửi đúng URI, Content-Type, Accept, custom header, Bearer token và session cookie.
2. Header/cookie theo request ghi đè giá trị default tương ứng.
3. Basic authentication filter tạo đúng Authorization header.

MockWebServer ghi nhận request thực tế đã đi qua HTTP connector, vì vậy test kiểm tra cả cách WebClient build request và cách connector gửi request.

### 12.5. Ví dụ request tương đương bằng curl

```bash
curl -i -X PATCH "https://inventory.example.com/items/42" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -H "X-Trace-Id: trace-123" \
  -H "Authorization: Bearer ACCESS_TOKEN" \
  -H "Cookie: SESSION=session-abc" \
  -d '{"name":"Keyboard"}'
```

`ACCESS_TOKEN` và session cookie trong ví dụ chỉ là giá trị minh họa. Không đưa credential thật vào shell history, tài liệu công khai hoặc log.

## 13. Những lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Nhầm `Accept` với `Content-Type` | Client mô tả sai định dạng gửi/nhận | `Content-Type` cho body gửi lên; `Accept` cho response mong muốn |
| Dùng `header()` lặp cho `Authorization` | Có thể tạo nhiều giá trị Authorization không hợp lệ | Dùng `headers(h -> h.setBearerAuth(...))` hoặc `setBasicAuth(...)` |
| Nghĩ `defaultHeader` luôn ghi đè header request | Request-specific header không hoạt động như dự định | Default chỉ được thêm nếu request chưa có header đó |
| Đặt user token trong `defaultHeader` của client dùng chung | Credential có thể bị gửi nhầm giữa user/request/host | Đặt token theo request hoặc dùng OAuth2 filter |
| Gửi cookie bằng cách tự nối chuỗi `Cookie` | Dễ sai encoding hoặc trùng giá trị | Dùng `cookie()`/`cookies()` |
| Nhầm `Set-Cookie` với `Cookie` | Không quản lý đúng vòng đời cookie | Đọc `Set-Cookie` response rồi lưu/gửi lại theo cookie-store policy |
| Nghĩ WebClient tự động duy trì session như browser | Request sau có thể thiếu cookie phiên | Quản lý cookie store rõ ràng hoặc truyền cookie theo request |
| Dùng Basic Auth qua HTTP thường | Username/password có thể bị đọc trên đường truyền | Dùng HTTPS/TLS |
| Đặt Bearer token hoặc API key trong URL | Credential có thể xuất hiện trong log/history/tracing | Dùng Authorization/custom header theo contract |
| Hardcode secret trong Java | Secret bị lộ qua source hoặc artifact | Dùng secret manager/environment configuration |
| Log toàn bộ headers | Log có thể chứa Authorization và session cookie | Mask/loại bỏ credential trước khi log |
| Dùng một client có default credential để gọi URI tùy ý | Credential có thể bị gửi sang host khác | Giới hạn base URL và phạm vi client |
| Tự đặt Content-Length/Host không cần thiết | Có thể gây lỗi framing hoặc connector behavior | Để HTTP connector quản lý transport headers |
| Tự subscribe trong filter | Tách request khỏi reactive lifecycle | Return publisher từ `next.exchange(...)` |
| Retry POST không có idempotency | Có thể tạo side effect trùng lặp | Dùng idempotency key và retry policy theo API contract |
| Coi 401 và 403 giống nhau | Xử lý credential/quyền sai hướng | Phân biệt authentication failure và authorization denial |

## 14. Checklist trước khi gọi API bên ngoài

- HTTP method có đúng contract và semantics của endpoint không?
- Path variable/query parameter có được URI builder encode không?
- Request body có `Content-Type` phù hợp không?
- `Accept` có liệt kê representation mà client có thể đọc không?
- Header nào là default và header nào phải thay đổi theo từng request?
- Có dùng `set(...)` cho header một giá trị như Authorization không?
- Cookie session có đúng user/request không?
- Có hiểu cách nhận, lưu và gửi lại `Set-Cookie` không?
- Basic credentials, Bearer token và API key có được lấy từ nơi lưu secret phù hợp không?
- Credential có bị đặt vào URL hoặc log không?
- WebClient có bị dùng để gọi host không tin cậy trong khi mang default credential không?
- OAuth2 Client có registration, provider, scope và grant type đúng không?
- Token acquisition/refresh có do Spring Security authorized client manager quản lý không?
- Có kiểm tra status 401/403 và response body lỗi không?
- Retry có an toàn với method và side effect không?
- Có test request thực tế bằng MockWebServer hoặc test server tương đương không?

## 15. Bài tập tự kiểm tra

**Bài 1.** Khi gửi JSON bằng WebClient, header nào mô tả định dạng body và header nào mô tả response mong muốn?

**Đáp án:** `Content-Type` mô tả body gửi lên; `Accept` mô tả representation response mà client chấp nhận.

**Bài 2.** Muốn chọn method từ một biến `HttpMethod method`, gọi API nào?

**Đáp án:** `client.method(method)` rồi tiếp tục thiết lập URI, headers và body nếu method có body.

**Bài 3.** `header("X-Mode", "a")` rồi `header("X-Mode", "b")` có thể tạo điều gì?

**Đáp án:** Hai giá trị header được thêm vào theo semantics của header. Nếu muốn thay giá trị, dùng `headers(h -> h.set("X-Mode", "b"))`.

**Bài 4.** `defaultHeader("X-Client", "default")` có ghi đè `X-Client` đã đặt trong request không?

**Đáp án:** Không. Default header chỉ được thêm nếu request chưa có header đó.

**Bài 5.** Vì sao không dùng Basic Authentication qua HTTP thường?

**Đáp án:** Basic chỉ Base64-encode chuỗi username/password; Base64 không mã hóa. Cần HTTPS/TLS để bảo vệ credential trên đường truyền.

**Bài 6.** Bearer token nên gửi ở đâu?

**Đáp án:** Trong `Authorization: Bearer ...`, có thể tạo bằng `headers(h -> h.setBearerAuth(token))`.

**Bài 7.** `Set-Cookie` và `Cookie` khác nhau thế nào?

**Đáp án:** Server trả `Set-Cookie` để hướng dẫn client lưu cookie; client gửi `Cookie` ở request sau để cung cấp cookie đã lưu.

**Bài 8.** OAuth2 Client filter khác việc tự đặt Bearer token thế nào?

**Đáp án:** Tự đặt token chỉ gửi credential đã có. OAuth2 Client filter tích hợp authorized client manager để lấy và quản lý token theo registration/grant/provider.

**Bài 9.** `ExchangeFilterFunction` phù hợp với loại công việc nào?

**Đáp án:** Hành vi dùng chung cho outbound requests như correlation metadata, client identity, authentication integration hoặc metrics.

**Bài 10.** Vì sao không nên log mọi request headers?

**Đáp án:** Header có thể chứa Authorization, API key và session cookie. Cần mask hoặc loại bỏ credential trước khi log.

## 16. Ghi nhớ

- `WebClient` có shortcut cho HTTP methods và `method(HttpMethod)` khi method được quyết định lúc chạy.
- `uri(...)` hỗ trợ URI template; `UriBuilder` giúp tạo path và query parameter có encoding.
- `Accept` nói về response mong muốn; `Content-Type` nói về request body.
- `header(...)` thêm giá trị; `headers(...)` cho phép set/add/remove.
- `defaultHeader` và `defaultCookie` chỉ được thêm nếu request chưa khai báo giá trị tương ứng.
- `cookie()`/`cookies()` thiết lập cookie outbound; `Set-Cookie` là chỉ thị server gửi về.
- Basic dùng `setBasicAuth` hoặc `ExchangeFilterFunctions.basicAuthentication`; chỉ dùng qua HTTPS.
- Bearer token dùng `setBearerAuth`; API key dùng custom header theo contract của dịch vụ.
- OAuth2 Client reactive dùng `ReactiveOAuth2AuthorizedClientManager` và `ServerOAuth2AuthorizedClientExchangeFilterFunction`.
- `ExchangeFilterFunction` phù hợp với hành vi dùng chung và phải giữ reactive composition.
- Credential phải được quản lý như secret; không đưa vào URL, log hoặc default client dùng chung ngoài phạm vi tin cậy.
- Kiểm thử request thực tế bằng MockWebServer giúp xác nhận method, URI, headers, cookies và Authorization.

Khi debug một request outbound, kiểm tra lần lượt **method → URI → Content-Type/Accept → custom headers → cookies → Authorization → response status**. Thứ tự này giúp xác định phần request nào không khớp contract của API đích.

## Tài liệu chính thức

- Spring Framework 6.2, **WebClient**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient.html
- Spring Framework 6.2, **WebClient Configuration**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-builder.html
- Spring Framework 6.2, **WebClient Filters**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-filter.html
- Spring Framework 6.2, **WebClient Attributes**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-attributes.html
- Spring Framework 6.2, **`WebClient.Builder` API**: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/reactive/function/client/WebClient.Builder.html
- Spring Framework 6.2, **`WebClient.RequestHeadersSpec` API**: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/reactive/function/client/WebClient.RequestHeadersSpec.html
- Spring Security, **OAuth2 WebFlux Client**: https://docs.spring.io/spring-security/reference/reactive/oauth2/
- Spring Security, **Reactive Bearer Token Propagation**: https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/bearer-tokens.html