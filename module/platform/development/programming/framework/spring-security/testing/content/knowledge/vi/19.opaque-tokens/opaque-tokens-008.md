# Timeout, lỗi HTTP và phản hồi introspection không hợp lệ

Trong chương **Opaque token** của module **SPRING_SECURITY_TESTING**, người học cần kiểm chứng điều gì xảy ra khi ứng dụng bảo vệ HTTP dựa vào **token introspection** nhưng dịch vụ xác thực bên ngoài trả lời chậm, trả mã lỗi HTTP hoặc gửi dữ liệu không đúng hợp đồng. Đây là các tình huống thực tế quan trọng: một API không được cho phép truy cập chỉ vì không liên hệ được máy chủ introspection, nhưng cũng cần phân biệt token **được xác nhận không hợp lệ** với hệ thống xác thực **tạm thời không thể kiểm tra token**.

Mục tiêu bài học là xây dựng ca kiểm thử xác thực và phân quyền trên cả **Servlet/MockMvc** và **Reactive/WebTestClient**, sử dụng `spring-security-test`, `SecurityContext` cùng các token giả chỉ tồn tại trong test. Các ví dụ xem xét riêng tác động của timeout, HTTP 4xx/5xx, JSON sai cú pháp và thiếu/sai trường `active`. Đồng thời, bài học chỉ rõ khi nào tiện ích `opaqueToken()`/`mockOpaqueToken()` là phù hợp và khi nào phải để request đi qua bộ introspector thật.

## 1. Introspection nằm ở đâu trong quá trình xác thực?

Opaque access token thường là chuỗi không mang thông tin mà resource server có thể tự giải mã và xác minh như JWT. Khi nhận bearer token, resource server gửi token đến **introspection endpoint** của authorization server. Theo RFC 7662, phản hồi introspection có trường boolean `active`, cho biết token hiện có hiệu lực theo đánh giá của máy chủ phát hành. Khi `active: true`, phản hồi có thể chứa `sub`, `scope`, `client_id`, `exp`, `aud` và các metadata khác để resource server xây dựng principal và authorities.

```mermaid
sequenceDiagram
    participant C as HTTP client
    participant R as Resource server
    participant I as Introspection endpoint
    C->>R: GET /api/orders, Authorization: Bearer opaque-token
    R->>I: POST /introspect, token=opaque-token
    alt active=true, đủ quyền
        I-->>R: 200 JSON {active: true, scope: ...}
        R-->>C: 200 OK
    else active=false
        I-->>R: 200 JSON {active: false}
        R-->>C: 401 Unauthorized (thường gặp)
    else lỗi mạng, timeout hoặc phản hồi sai
        I--xR: Không thể có kết quả introspection đáng tin cậy
        R-->>C: Từ chối tiếp tục; status theo xử lý lỗi cấu hình
    end
```

Lưu ý hai đường HTTP khác nhau:

- **Client → Resource server:** nơi cần khẳng định status 401, 403, 2xx hoặc lỗi dịch vụ trong bộ test API.
- **Resource server → Introspection endpoint:** nơi kiểm tra mã 200/400/401/429/500/503, timeout, body và header. Một `401` tại **introspection endpoint** có thể báo sai thông tin xác thực của *resource server* với authorization server; nó **không tự động có nghĩa** bearer token của client không hợp lệ.

Token introspection hợp lệ thông thường là HTTP 200 với JSON dạng:

```json
{
  "active": true,
  "sub": "fixture-reader",
  "scope": "orders.read",
  "client_id": "resource-api-test"
}
```

Token không hoạt động được diễn đạt theo RFC 7662 bằng một phản hồi thành công HTTP 200 có `active: false`:

```json
{
  "active": false
}
```

Giá trị token, client ID và tên principal trong bài chỉ là fixture; không dùng access token, client secret, cookie hoặc tài khoản thực lấy từ môi trường triển khai.

## 2. Phân loại các lỗi cần kiểm thử

| Đầu ra từ introspection endpoint | Cách diễn giải đúng | Hành vi an toàn cần xác minh |
| --- | --- | --- |
| HTTP 200, JSON `active: true`, scope phù hợp | Token đang hoạt động, đã trả metadata phục vụ phân quyền | Endpoint được phép hoạt động nếu mọi điều kiện xác thực/phân quyền khác cũng hợp lệ |
| HTTP 200, JSON `active: false` | Authorization server xác nhận token không hoạt động | Không tạo authenticated principal, thường trả 401 tại API |
| HTTP 200, `active: true` nhưng thiếu scope yêu cầu | Có danh tính nhưng không có quyền cho tài nguyên | Thường trả 403 nếu principal được chấp nhận nhưng thiếu authority |
| Không kết nối được, DNS thất bại, connection refused | Introspection không khả dụng | Không coi token là hợp lệ; trả lỗi phù hợp với chính sách vận hành |
| Connect timeout hoặc read/response timeout | Không có kết quả introspection đáng tin trong giới hạn thời gian | Không thực thi endpoint bảo vệ; không chờ vô hạn |
| Introspection HTTP 400 hoặc 401 | Có thể là yêu cầu introspection sai hoặc resource server xác thực với endpoint thất bại | Không coi là `active: false`; điều tra cấu hình URI/credential và từ chối truy cập |
| Introspection HTTP 429 | Endpoint đang giới hạn tốc độ | Không bỏ qua xác thực; có thể trả lỗi tạm thời và áp dụng retry/backoff có giới hạn ở tầng phù hợp |
| Introspection HTTP 500/502/503/504 | Authorization server hoặc gateway gặp sự cố | Không mặc định cấp quyền; ghi nhận lỗi phụ thuộc và tránh biến sự cố thành thành công |
| HTTP 200, JSON lỗi cú pháp, body rỗng hoặc `Content-Type` bất thường | Không thể đọc phản hồi theo hợp đồng | Không dựng principal từ dữ liệu chưa xác minh |
| HTTP 200, thiếu `active` hoặc `active` sai kiểu | Phản hồi không đúng dạng introspection mong đợi | Không suy đoán `active: true`; kiểm tra parser/validator thực tế và từ chối nếu không xác minh được |

**Fail closed** nghĩa là không cho request đi vào nghiệp vụ được bảo vệ khi xác thực chưa thành công. Fail closed **không đòi hỏi mọi lỗi trả về cùng mã 401**. Lỗi timeout/5xx của introspection là sự cố phụ thuộc, khác về bản chất với thông báo token bị thu hồi. API có thể dùng xử lý exception riêng để biểu diễn lỗi tạm thời, chẳng hạn 503, miễn vẫn từ chối thực thi tài nguyên cần bảo vệ và đáp ứng hợp đồng bảo mật.

### Vì sao phân biệt 401, 403 và lỗi introspection?

- **401 ở API:** request chưa có hoặc không có bearer token được chấp nhận; ví dụ không gửi token hoặc introspection trả `active: false`.
- **403 ở API:** token đã được chấp nhận và xác thực, nhưng principal thiếu authority để truy cập URL hay method được bảo vệ.
- **Lỗi phụ thuộc ở API:** resource server chưa biết token hợp lệ hay không vì introspection timeout, trả 5xx hoặc dữ liệu sai. Mã trả cho client phụ thuộc cách `OpaqueTokenIntrospector`, filter và exception handler của phiên bản/cấu hình Spring Security phối hợp; phải kiểm thử cụ thể, không gán cố định kết quả mặc định.

Không được “sửa” timeout bằng cách bỏ qua introspection hoặc cho mọi bearer token đi qua. Nếu có chiến lược cache kết quả introspection, cache phải có chính sách hết hạn, thu hồi và thất bại rõ ràng; không tự động dùng kết quả `active: true` quá hạn khi authorization server mất kết nối.

## 3. Các mức kiểm thử trong Spring Security

| Mục tiêu | Công cụ | Phạm vi được chứng minh |
| --- | --- | --- |
| Kiểm tra quyền của principal đã xác thực | `MockMvc` với `opaqueToken()` hoặc `WebTestClient` với `mockOpaqueToken()` | Luật `hasAuthority`, `@PreAuthorize`, ánh xạ authority/claim ở tầng HTTP và ứng dụng |
| Kiểm tra `OpaqueTokenIntrospector` với từng phản hồi | HTTP stub/mock server hoặc `MockRestServiceServer` gắn vào client introspection | Xử lý `active`, payload, mã HTTP, dữ liệu sai và lỗi transport của introspector |
| Kiểm tra cả filter chain và parser/introspector | `MockMvc`/`WebTestClient` gửi header `Authorization: Bearer ...` tới app có introspector thật trỏ vào stub | HTTP authentication/authorization và mã trả về khi dependency lỗi |
| Kiểm tra timeout thực tế | Stub có trì hoãn có kiểm soát + HTTP client cấu hình connect/read/response timeout hữu hạn | Timeout được áp dụng và request từ chối trong giới hạn chờ dự kiến |
| Kiểm tra tích hợp với authorization server | Sandbox cô lập của nhà cung cấp, tài khoản/secret test | Hợp đồng tích hợp, mTLS/client authentication nếu có; không phụ thuộc môi trường production |

`SecurityMockMvcRequestPostProcessors.opaqueToken()` và `SecurityMockServerConfigurers.mockOpaqueToken()` tạo trạng thái opaque token **đã được xác thực**. Chúng không gửi một POST introspection, do đó không thể tự kiểm tra timeout, HTTP 500 hay JSON malformed từ introspection endpoint. `@WithMockUser` cũng chỉ hữu ích cho logic sau xác thực và không kích hoạt introspection. Với các ca mà mục tiêu là kiểm thử lỗi thật của introspection, phải gửi Bearer header và giữ đường đi tới introspector trong cấu hình test.

## 4. Servlet: cấu hình resource server và kiểm thử phân quyền độc lập

Cấu hình minh họa cho một API chỉ cho phép authority `SCOPE_orders.read`:

```java
@Configuration
class OrderSecurityConfig {

    @Bean
    SecurityFilterChain orderSecurityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth -> oauth
                .opaqueToken(Customizer.withDefaults()))
            .build();
    }
}
```

Đây là cấu hình Servlet dùng Spring Security 6 theo phong cách lambda DSL. Cần cung cấp một `OpaqueTokenIntrospector` (qua cấu hình Boot phù hợp hoặc bean riêng). Với `spring-security-test`, test nhanh kiểm tra chính sách mà không phụ thuộc introspection endpoint:

```java
@Test
void aReaderWithScopeCanAccessOrders() throws Exception {
    mockMvc.perform(get("/api/orders")
            .with(opaqueToken().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read"))))
        .andExpect(status().isOk());
}

@Test
void aReaderWithoutScopeIsForbidden() throws Exception {
    mockMvc.perform(get("/api/orders")
            .with(opaqueToken().authorities(
                new SimpleGrantedAuthority("SCOPE_profile.read"))))
        .andExpect(status().isForbidden());
}
```

Các đoạn trên là method của một test đã có `MockMvc`, controller ở `GET /api/orders`, security filter chain và các static import tương ứng. `opaqueToken()` đến từ `SecurityMockMvcRequestPostProcessors`. Test có thể kiểm tra 200/403 nhưng **không thể chứng minh request chờ introspection bị timeout**.

Để kiểm tra điều đó, tạo một bài integration test riêng, gửi bearer token như client thật:

```java
mockMvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION,
            "Bearer fixture-token-inactive"))
    .andExpect(status().isUnauthorized());
```

Assertion 401 có ý nghĩa khi introspector test thực sự nhận `fixture-token-inactive` và trả kết quả `active: false` theo RFC 7662. Đừng dùng `opaqueToken()` trên chính request này: làm vậy sẽ bỏ qua điều đang cần kiểm chứng.

## 5. Tạo HTTP stub cho introspection để tái hiện từng phản hồi

Một HTTP stub như MockWebServer hoặc WireMock giúp kiểm soát chính xác **status, content type, body và độ trễ**. Dưới đây là các phản hồi có thể đưa vào hàng đợi của một mock server trong test, độc lập với tài khoản và token thật:

```java
// HTTP 200: token đang hoạt động và có scope đọc đơn hàng.
new MockResponse()
    .setResponseCode(200)
    .addHeader("Content-Type", "application/json")
    .setBody("""
        {"active":true,"sub":"fixture-reader","scope":"orders.read"}
        """);

// HTTP 200: token đã bị thu hồi hoặc không hợp lệ.
new MockResponse()
    .setResponseCode(200)
    .addHeader("Content-Type", "application/json")
    .setBody("{\"active\":false}");

// HTTP 503: dịch vụ introspection tạm thời không khả dụng.
new MockResponse()
    .setResponseCode(503)
    .addHeader("Content-Type", "application/json")
    .setBody("{\"error\":\"temporarily_unavailable\"}");

// HTTP 200: JSON sai hợp đồng (active không phải boolean).
new MockResponse()
    .setResponseCode(200)
    .addHeader("Content-Type", "application/json")
    .setBody("{\"active\":\"true\"}");
```

Ví dụ dùng `okhttp3.mockwebserver.MockResponse` (thư viện phụ thuộc test). Đây là **các fixture độc lập**; khi chạy, hãy `server.enqueue(response)` đúng một phản hồi trước request cần kiểm tra. Không đưa bốn response vào một test rồi giả định request nào cũng nhận response đầu tiên. Tránh chạy test song song nếu các test dùng chung hàng đợi server mà không cô lập.

### Gắn ứng dụng với URL và credential giả

Ví dụ cấu hình thuộc **profile test**, khi dùng Spring Boot với các khóa cấu hình resource server opaque token:

```properties
spring.security.oauth2.resourceserver.opaquetoken.introspection-uri=http://127.0.0.1:9999/introspect
spring.security.oauth2.resourceserver.opaquetoken.client-id=fixture-resource-client
spring.security.oauth2.resourceserver.opaquetoken.client-secret=fixture-secret-only
```

Port `9999` chỉ mang tính minh họa; trong test thực tế lấy port động từ mock server bằng `@DynamicPropertySource` hoặc cấu hình tương đương để tránh xung đột cổng. `client-secret` ở đây là chuỗi giả do test tạo ra, không cấp quyền tới một authorization server đang triển khai. Nếu ứng dụng tự khai báo bean `OpaqueTokenIntrospector`, xác minh bean đó thực sự lấy URI và credential từ cấu hình test; khai báo property mà bean vẫn dùng production URL thì test không được coi là cô lập.

### Kiểm tra HTTP introspection request được gửi đúng

Ngoài status của API, bắt request trên mock server và xác minh các đặc điểm của **HTTP request tới introspection endpoint**:

1. Method là `POST` đến URI giả lập đã cấu hình.
2. Body là `application/x-www-form-urlencoded` và có tham số `token` nhận đúng chuỗi fixture.
3. Resource server tự xác thực với endpoint bằng cơ chế cấu hình trong test (thường là HTTP Basic; một số hệ thống dùng phương thức client authentication khác).
4. Không ghi giá trị token, secret hoặc header `Authorization` ra log/snapshot test; khi cần chẩn đoán, chỉ ghi sự có mặt và tên header hoặc giá trị đã che.
5. Khi introspection từ chối hoặc không trả về kết quả tin cậy, controller bảo vệ **không được thực thi**.

Không kiểm tra bằng chuỗi Basic chứa `client-secret` thật; chỉ dùng credential fixture và so sánh cẩn trọng trong môi trường test. Với introspection API dùng xác thực khác HTTP Basic, phải dựng đúng contract của nhà cung cấp thay vì giả định mọi hệ thống giống nhau.

## 6. Timeout: phân biệt chờ kết nối và chờ đọc phản hồi

Có ít nhất hai kiểu timeout cần kiểm thử khi resource server gọi introspection:

- **Connect timeout:** client không thiết lập được kết nối TCP trong thời hạn. Trường hợp này khác với `connection refused`, khi phía nhận từ chối kết nối ngay.
- **Read/response timeout:** kết nối đã có nhưng server không gửi phản hồi (hoặc không hoàn tất phản hồi) trong thời hạn cấu hình.

Các HTTP client khác nhau có thể có thêm timeout tổng request, DNS timeout hoặc thời gian chờ từ connection pool. Không chỉ kiểm tra một thuộc tính timeout rồi mặc định đã khống chế mọi nguồn chờ.

Với một introspector Servlet sử dụng `RestTemplate`, có thể dựng `RestOperations` riêng cho test, dùng credential fixture và thời hạn chờ hữu hạn:

```java
RestTemplate restTemplate = new RestTemplateBuilder()
    .basicAuthentication("fixture-resource-client", "fixture-secret-only")
    .connectTimeout(Duration.ofMillis(200))
    .readTimeout(Duration.ofMillis(300))
    .build();

OpaqueTokenIntrospector introspector =
    new NimbusOpaqueTokenIntrospector(
        "http://127.0.0.1:9999/introspect", restTemplate);
```

Ví dụ sử dụng API của Spring Boot 3 và Spring Security 6 có constructor nhận `RestOperations`; tên builder/implementation có thể thay đổi giữa các phiên bản. Khi dùng phiên bản mới hoặc introspector tự viết, hãy chuyển chính sách timeout tương ứng sang HTTP client thực mà bean đang dùng. Đừng đặt timeout trên một `RestTemplate` không được gắn vào introspector rồi cho rằng có hiệu lực.

Để tái hiện **read timeout**, mock server có thể trì hoãn body lâu hơn thời hạn đọc đã cấu hình:

```java
MockResponse delayed = new MockResponse()
    .setResponseCode(200)
    .addHeader("Content-Type", "application/json")
    .setBody("{\"active\":true,\"scope\":\"orders.read\"}")
    .setBodyDelay(2, TimeUnit.SECONDS);

server.enqueue(delayed);
```

Với `readTimeout = 300 ms`, test này cố gắng gây timeout trước khi client nhận đủ body. Để kiểm thử tình huống server không gửi bất kỳ byte phản hồi nào, dùng độ trễ header/response thích hợp của mock server. Thời gian OS, DNS, thread scheduler và HTTP client có thể làm phép đo thực tế dao động; khẳng định “không có quyền truy cập” và exception/status đúng **chính sách cấu hình**, đồng thời chỉ kiểm tra thời gian hoàn tất trong ngưỡng đủ rộng để test không chập chờn. Không dùng `Thread.sleep()` làm cơ sở xác thực trạng thái token.

### Test phải kiểm tra gì khi timeout?

Với bearer token hợp lệ về hình thức nhưng introspection bị timeout:

1. Request không trả 2xx cho tài nguyên bảo vệ.
2. Controller/service thực thi tài nguyên không bị gọi; không có ghi dữ liệu hoặc side effect do request chưa xác thực.
3. Timeout được ghi nhận như lỗi phụ thuộc, không chuyển thành danh tính `authenticated` có quyền mặc định.
4. Nếu ứng dụng định nghĩa mapping lỗi timeout sang HTTP 503, test khẳng định **503** một cách tường minh. Nếu dùng mapping mặc định, xác nhận status/exception thực tế thay vì gán nhầm mọi timeout thành 401.
5. Không có vòng retry vô hạn. Nếu có retry, chỉ retry theo chính sách đã thiết kế với giới hạn và kiểm thử riêng; sự cố introspection không được nhân số lượng kết nối vô hạn.

## 7. Lỗi HTTP 4xx/5xx của introspection endpoint

Đừng chỉ thử HTTP 500. Nên chia ít nhất ba nhóm lỗi để chẩn đoán:

**400/401:** Có thể do URL introspection sai, body gửi sai định dạng hoặc client authentication của resource server không hợp lệ. Khi đó token của người dùng **chưa được introspect thành công**. Không nên kết luận nó đã bị thu hồi chỉ dựa vào status 401 trả về ở kênh server-to-server.

**429:** Endpoint giới hạn tốc độ. Nếu retry ngay, nhiều request đồng thời có thể gây tải lớn hơn. Có thể sử dụng thông tin `Retry-After` nếu hệ thống có chính sách xử lý phù hợp, kết hợp backoff và giới hạn tài nguyên. Trong khoảng lỗi, không cho request chưa xác thực đi qua.

**500/502/503/504:** Lỗi server/gateway của identity infrastructure. Kiểm tra khả năng trả lỗi ổn định, ghi log đã che dữ liệu, giới hạn thời gian và không cho controller chạy. Từ góc nhìn người dùng, một mã lỗi tạm thời có thể phản ánh nguyên nhân tốt hơn “token không hợp lệ”, nhưng việc mapping cụ thể phải được định nghĩa và kiểm thử trong ứng dụng.

Ví dụ ma trận kiểm thử ở tầng HTTP stub và application:

| Stub introspection | Khẳng định bắt buộc | Có thể khẳng định thêm nếu ứng dụng quy định |
| --- | --- | --- |
| 400 | Không cấp principal, không thực thi controller | Mã lỗi API và thông tin chẩn đoán nội bộ dành cho sai request introspection |
| 401 | Không đánh đồng với `active: false`, không cấp quyền | Cảnh báo sai client authentication hoặc cấu hình introspection |
| 429 | Không thực thi nghiệp vụ, không retry vô hạn | Backoff và mã 503 / retry contract |
| 500 hoặc 503 | Fail closed | Status 5xx của resource server nếu có exception handler |
| 200, `active: false` | Không có authentication hợp lệ | 401 của resource server |

Hãy chọn một token fixture cố định và đổi **một** yếu tố phản hồi mỗi test. Nếu cùng lúc thay token, URL, client credential và body, khi test lỗi sẽ khó xác định nguyên nhân.

## 8. Phản hồi JSON không hợp lệ: lỗi cú pháp và lỗi ngữ nghĩa

Phản hồi có HTTP 200 vẫn có thể sai hợp đồng. Những fixture quan trọng gồm:

```text
Body rỗng

{"active":          // JSON thiếu dấu kết thúc

{"active":"true"}   // active sai kiểu: string thay cho boolean

{"scope":"orders.read"} // thiếu active

[]                  // không phải JSON object cho introspection

{"active":null}     // active không có giá trị boolean hữu dụng
```

Không xây principal dựa vào việc “HTTP 200 là thành công” hoặc “trường `scope` có mặt”. Cần kiểm tra `active` đúng hợp đồng và xử lý parse error/validation error với chính parser của introspector đang dùng. Nếu API nhận `active: true` nhưng các trường khác sai kiểu, test phải chứng minh ứng dụng không cấp authority ngoài dữ liệu đã được xác minh.

Một số phản hồi có thể hợp lệ theo RFC nhưng không đủ cho **chính sách riêng của ứng dụng**. Ví dụ, introspection trả `active: true` nhưng không có `scope`; nếu endpoint yêu cầu `SCOPE_orders.read`, token có thể được xác thực mà không đủ quyền, dẫn đến 403. Điều này khác với JSON sai cú pháp hoặc thiếu `active`, vốn không đủ dữ liệu để xác minh trạng thái token. Cần giữ riêng các test cho **validation**, **authentication** và **authorization**.

Tùy phiên bản Spring Security và implementation (`NimbusOpaqueTokenIntrospector`, implementation reactive hoặc introspector tùy biến), phản hồi sai kiểu có thể dẫn tới exception khác nhau và cách ánh xạ HTTP cuối cùng khác nhau. Test nên khẳng định bất biến quan trọng là **không cấp quyền** và thêm assertion cụ thể theo contract của ứng dụng. Với parser sai, đừng tự đổi lỗi thành `active: false` nếu điều này khiến sự cố dữ liệu bị che lấp.

## 9. Reactive: WebTestClient và `ReactiveOpaqueTokenIntrospector`

Trên WebFlux, đường đi tương ứng là `SecurityWebFilterChain` → bộ xác thực bearer token → `ReactiveOpaqueTokenIntrospector` → `Authentication` → luật phân quyền. Đối với test authorization với danh tính giả, `spring-security-test` hỗ trợ `mockOpaqueToken()`:

```java
webTestClient.mutateWith(mockOpaqueToken()
        .authorities(new SimpleGrantedAuthority("SCOPE_orders.read")))
    .get().uri("/api/orders")
    .exchange()
    .expectStatus().isOk();

webTestClient.mutateWith(mockOpaqueToken()
        .authorities(new SimpleGrantedAuthority("SCOPE_profile.read")))
    .get().uri("/api/orders")
    .exchange()
    .expectStatus().isForbidden();
```

`mockOpaqueToken()` là tiện ích của `SecurityMockServerConfigurers`, tạo principal xác thực giả trong WebTestClient. Nó **không phát sinh request introspection**. Khi kiểm tra `active: false`, timeout hoặc lỗi 5xx của introspection, gắn một `ReactiveOpaqueTokenIntrospector` thật gọi tới HTTP stub và gửi header Bearer:

```java
webTestClient.get()
    .uri("/api/orders")
    .headers(headers -> headers.setBearerAuth("fixture-token-inactive"))
    .exchange()
    .expectStatus().isUnauthorized();
```

Lệnh trên dự kiến 401 khi HTTP stub trả JSON hợp lệ `{"active":false}`, và resource server được cấu hình xử lý opaque token. Đối với timeout, WebClient/HTTP client phục vụ introspection phải được cấu hình **response timeout** hữu hạn, hoặc một cơ chế timeout có kiểm soát phù hợp pipeline reactive. Không dùng thao tác blocking để giả lập timeout trong một `Mono` trên event loop; hãy mô phỏng lỗi hoặc độ trễ bằng Reactor Test/HTTP stub, rồi khẳng định không có đường đi cho phép truy cập.

Nếu tự tạo `WebTestClient` từ application context, cần bật bộ tích hợp Spring Security tương ứng, ví dụ `.apply(springSecurity())`, để filter chain thực sự tham gia. Test xanh khi security filter bị bỏ qua là dương tính giả.

## 10. Kiểm tra phản hồi API và quan sát lỗi có kiểm soát

Một test bảo mật tốt không chỉ assert status. Với mọi tình huống introspection thất bại, xác nhận **request không chạm nghiệp vụ bảo vệ** (ví dụ qua mock/spy service hoặc bộ đếm trong fixture test). Đồng thời, giữ khả năng chẩn đoán lỗi mà không lộ credential hay token:

| Thông tin có thể ghi nhận | Thông tin phải tránh ghi nguyên văn |
| --- | --- |
| Loại lỗi: `connect_timeout`, `read_timeout`, `introspection_5xx`, `invalid_json` | Raw access token trong header hoặc body POST introspection |
| Mã HTTP downstream và thời gian phản hồi làm tròn | `Authorization: Basic ...`, client secret, refresh token |
| Tên dependency/host test, correlation ID không nhạy cảm | Đầy đủ SecurityContext hoặc phản hồi chứa dữ liệu cá nhân |
| Số lần retry/circuit breaker transition theo policy | Snapshot production token đưa vào báo cáo lỗi hoặc CI artifact |

Khi cần mô phỏng timeout hoặc HTTP 500, không dùng dịch vụ introspection thật của môi trường staging/production. Dùng stub local, fixture không có quyền truy cập thật và URI động để các test chạy lại trên máy khác hoặc CI. Chặn outbound không mong muốn nếu bộ test có nguy cơ nạp sai cấu hình mạng.

## 11. Bài thực hành: xây bộ kiểm thử lỗi introspection

Giả sử `GET /api/orders` yêu cầu `SCOPE_orders.read`. Tạo một endpoint test rất nhỏ, một `SecurityFilterChain` và một `SecurityWebFilterChain` tương đương, cùng một HTTP mock server cung cấp `/introspect` cho mỗi bộ test.

1. Gửi token `fixture-reader` đến introspection stub trả HTTP 200 với `active:true`, `scope:orders.read`. Xác minh API trả 200 và controller được gọi đúng một lần.
2. Đổi `scope` thành `profile.read` nhưng giữ `active:true`. Xác minh 403 và controller không chạy.
3. Trả HTTP 200 với `active:false`. Xác minh 401 và controller không chạy.
4. Giả lập connect timeout và read timeout dài hơn giới hạn đã cấu hình. Xác minh request kết thúc theo chính sách timeout, không trả 2xx, không chạy nghiệp vụ, không retry vô hạn.
5. Lần lượt trả HTTP 400, 401, 429, 500 và 503 từ introspection endpoint. Ghi nhận chính xác status/exception của ứng dụng; xác minh mọi trường hợp đều không cấp quyền và nguyên nhân được phân loại đúng.
6. Thử body rỗng, JSON sai cú pháp, thiếu `active`, `active` sai kiểu và metadata quyền sai kiểu. Không coi HTTP 200 là bảo đảm token hợp lệ.
7. Viết một cặp test `opaqueToken()`/`mockOpaqueToken()` cho role/scope và một cặp test gửi header Bearer thật qua introspector. Giải thích test nào xác minh authorization, test nào xác minh authentication và transport.
8. Chạy test trên CI không cần token, client secret hoặc mạng đến authorization server triển khai. Kiểm tra log và báo cáo test để chắc chắn không lộ dữ liệu nhạy cảm.

### Tiêu chí hoàn thành

- Có bằng chứng HTTP 200 từ introspection với `active:true` và đủ quyền cho phép request, còn `active:false` hoặc thiếu quyền bị chặn đúng 401/403.
- Có test chứng minh timeout, HTTP error và JSON sai đều **fail closed**. Nếu ứng dụng quy định mã lỗi cụ thể cho dependency failure, test kiểm tra đúng mã đó.
- Có fixture tách biệt cho Servlet/MockMvc và Reactive/WebTestClient, và có kiểm tra rằng security filters thực sự được gắn vào mỗi test client.
- Không có tài khoản, access token, client secret hoặc endpoint introspection thật của môi trường triển khai trong source/test artifact.
- Người học phân biệt được hai sự kiện: authorization server xác nhận **token không hoạt động** và resource server **không thể hoàn tất introspection**.

## Ghi nhớ

**Opaque token introspection** tạo ra một phụ thuộc HTTP bên ngoài ngay trên đường xác thực của resource server. `active:false` là kết luận về token, còn timeout, 4xx/5xx hay phản hồi sai là thất bại khi thu thập hoặc kiểm tra kết luận đó. Với `spring-security-test`, dùng `opaqueToken()`/`mockOpaqueToken()` để kiểm thử quyền sau xác thực; dùng bearer header, introspector thật và HTTP stub để kiểm thử lỗi introspection. Trong mọi trường hợp, khi chưa xác thực thành công thì API bảo vệ phải từ chối thực thi nghiệp vụ, đồng thời ứng dụng cần phân loại lỗi và trả HTTP status nhất quán với chính sách đã cấu hình.
