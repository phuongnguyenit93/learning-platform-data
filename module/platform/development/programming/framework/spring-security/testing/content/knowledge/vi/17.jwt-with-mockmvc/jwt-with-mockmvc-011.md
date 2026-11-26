# Kiểm tra token bị từ chối khi decoder trả lỗi

Một API sử dụng JWT thường chấp nhận request có header `Authorization: Bearer <token>`. Nhưng việc **nhìn thấy header** chưa có nghĩa token đã được chấp nhận. Với Spring Security OAuth2 Resource Server, JWT phải được chuyển đến `JwtDecoder` để phân tích, xác minh chữ ký theo cấu hình và kiểm tra những ràng buộc đã thiết lập (chẳng hạn thời hạn hoặc issuer). Khi token không hợp lệ, request phải dừng ở lớp bảo mật trước khi controller thực thi.

Trong chương **JWT với MockMvc** của module `SPRING_SECURITY_TESTING`, bài này tập trung vào câu hỏi: **Làm sao chứng minh API trả lỗi xác thực khi `JwtDecoder` từ chối token?** Ta sẽ viết kiểm thử Servlet bằng `MockMvc`, thay `JwtDecoder` bằng mock có kiểm soát, chủ động cho nó ném ngoại lệ phù hợp, rồi kiểm tra HTTP status, header challenge và lời gọi decoder.

Điểm quan trọng nhất: `with(jwt())` từ `spring-security-test` rất hữu ích để kiểm tra phân quyền, nhưng nó cung cấp sẵn `JwtAuthenticationToken` cho request. Cách đó **không gọi `JwtDecoder.decode()`**, vì vậy không dùng riêng nó để kết luận “token bị từ chối khi decoder lỗi”.

## 1. Mục tiêu và điều kiện của bài thực hành

Sau bài này, bạn có thể:

- Gửi Bearer token qua header thực của request `MockMvc` để kích hoạt `BearerTokenAuthenticationFilter`.
- Cấu hình `JwtDecoder` mock trả `Jwt` hợp lệ hoặc ném `BadJwtException`.
- Kiểm tra token bị từ chối bằng **401 Unauthorized**, challenge `WWW-Authenticate` chứa `invalid_token` và xác nhận decoder đã được gọi với đúng token.
- Phân biệt **401** vì token không hợp lệ, **403** vì người dùng đã xác thực nhưng không đủ quyền và lỗi hệ thống khi decoder không thể hoạt động.
- Nhận diện trường hợp test đi tắt bằng `jwt()`, quên đăng ký filter chain hoặc chỉ assert status mà không kiểm tra luồng thực thi.

Ví dụ sử dụng Java 17+, ứng dụng Spring Boot Servlet, Spring Security 6.x và Spring Security Test. Annotation `@MockitoBean` có từ Spring Framework 6.2 (thường gặp từ Spring Boot 3.4); nếu dự án đang dùng phiên bản cũ hơn, thay nó bằng phương pháp đăng ký mock bean phù hợp với phiên bản đó, chẳng hạn `@MockBean` trong những phiên bản Spring Boot còn hỗ trợ. Đường import của một số test annotation có thể khác trong thế hệ Spring Boot mới; cần sử dụng package tương ứng với dependency thực tế của dự án.

## 2. JWT đi qua những thành phần nào?

Khi request tới API có Bearer token, luồng cơ bản là:

~~~mermaid
sequenceDiagram
    participant C as Client / MockMvc
    participant F as BearerTokenAuthenticationFilter
    participant P as JwtAuthenticationProvider
    participant D as JwtDecoder
    participant A as Controller
    C->>F: GET /api/me + Authorization: Bearer ...
    F->>P: Yêu cầu xác thực Bearer token
    P->>D: decode(rawToken)
    alt JWT hợp lệ
        D-->>P: Jwt đã được xác thực, parse, validate
        P-->>F: JwtAuthenticationToken
        F->>A: Cho phép đi tiếp
        A-->>C: 200 OK
    else Token không hợp lệ
        D-->>P: BadJwtException
        P-->>F: InvalidBearerTokenException
        F-->>C: 401 + WWW-Authenticate: Bearer ... invalid_token
    end
~~~

Các trách nhiệm không nên bị đánh đồng:

| Thành phần | Trách nhiệm | Điều cần chứng minh trong test |
| --- | --- | --- |
| `BearerTokenResolver` | Tìm Bearer token trong request | Header có đúng cú pháp để đi tiếp không? |
| `BearerTokenAuthenticationFilter` | Tạo yêu cầu xác thực, điều phối lỗi | Request lỗi có bị chặn trước controller không? |
| `JwtAuthenticationProvider` | Yêu cầu decoder giải mã và chuyển JWT thành authentication | Lỗi JWT được chuyển thành lỗi xác thực tương ứng không? |
| `JwtDecoder` | Kiểm tra/giải mã JWT theo cấu hình | `decode(token)` có được gọi và trả JWT hoặc ném lỗi như mong đợi? |
| `BearerTokenAuthenticationEntryPoint` | Tạo phản hồi cho yêu cầu chưa xác thực | HTTP status và `WWW-Authenticate` có đúng không? |
| `AuthorizationFilter` | Kiểm tra quyền sau xác thực | Token hợp lệ nhưng thiếu quyền có nhận 403 không? |

Trong luồng Resource Server mặc định của Spring Security, khi `JwtDecoder` ném `BadJwtException`, `JwtAuthenticationProvider` xử lý nó như **Bearer token không hợp lệ**, từ đó response thường là **401** kèm `WWW-Authenticate: Bearer error="invalid_token"`. Chi tiết về thông điệp lỗi có thể thay đổi theo phiên bản và cấu hình `AuthenticationEntryPoint`; nên assert phần hợp đồng ổn định trước.

**Vì sao không chỉ kiểm tra `JwtDecoder` bằng unit test?** Một unit test trực tiếp gọi `decoder.decode()` có thể chứng minh decoder phát hiện token hỏng. Nhưng nó không chứng minh filter chain ngăn request, xử lý exception hoặc trả HTTP 401. Để kiểm tra hành vi của endpoint khi decoder lỗi, phải gửi request qua chuỗi bảo mật.

## 3. Chuẩn bị API Servlet bảo vệ bằng JWT

Các dependency tối thiểu cho ví dụ thường gồm:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Sử dụng BOM hoặc dependency management của Spring Boot để các phiên bản tương thích nhau. Các ví dụ dưới đây giả định ứng dụng có lớp `@SpringBootApplication` và các class cấu hình/controller nằm trong package được component scan.

### 3.1. SecurityFilterChain

Ta bảo vệ endpoint `/api/me`, cho phép đọc `/api/orders` chỉ khi có authority `SCOPE_orders.read`, và bật resource server JWT:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class JwtApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/orders")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers("/api/**").authenticated()
                .anyRequest().permitAll()
            )
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

`oauth2ResourceServer(...jwt(...))` yêu cầu ứng dụng có một `JwtDecoder` để xác thực Bearer token. Trong môi trường thực, decoder có thể được cấu hình với issuer/JWK Set URI và khóa xác minh. **Trong test này, ta thay bean đó bằng mock**, nhờ vậy có thể ép riêng tình huống chữ ký sai hoặc token hết hạn mà không phải tự tạo một JWT thật đã ký.

`SessionCreationPolicy.STATELESS` thể hiện mô hình token trên mỗi request; nó không có nghĩa bỏ qua xác thực. Mỗi request cần gửi Bearer token. Bài này chỉ dùng GET, vì vậy CSRF không quyết định kết quả; với POST/PUT/DELETE phải xét thêm chính sách CSRF thực tế thay vì suy diễn từ các test GET.

### 3.2. Controller để nhận ra request được phép đi tiếp

~~~java
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class JwtApiController {

    @GetMapping("/api/me")
    Map<String, String> me(@AuthenticationPrincipal Jwt jwt) {
        return Map.of("subject", jwt.getSubject());
    }

    @GetMapping("/api/orders")
    String orders() {
        return "orders-visible";
    }
}
~~~

Khi JWT hợp lệ, `@AuthenticationPrincipal Jwt` lấy principal đã được resource server xác thực. Khi JWT bị từ chối, Spring Security phải trả phản hồi từ filter chain **trước khi** `me()` hoặc `orders()` được gọi.

## 4. Kỹ thuật chính: mock JwtDecoder rồi gửi header Bearer thật

Bài test mẫu dưới đây dùng:

- `@SpringBootTest` để tải context và `SecurityFilterChain`.
- `@AutoConfigureMockMvc` để request đi qua MVC và filters.
- `@MockitoBean JwtDecoder` để điều khiển kết quả của `decode()`.
- Header `Authorization: Bearer ...` qua `MockMvcRequestBuilders.get()`.
- `verify(jwtDecoder).decode(...)` để xác nhận request thực sự chạm đến decoder.

### 4.1. Token có chữ ký sai phải trả 401

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.response
    .SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class JwtDecoderFailureTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    JwtDecoder jwtDecoder;

    @Test
    void invalidSignatureIsRejectedWithBearerChallenge() throws Exception {
        String rawToken = "token-with-invalid-signature";

        when(jwtDecoder.decode(rawToken))
            .thenThrow(new BadJwtException("Invalid JWT signature"));

        mockMvc.perform(get("/api/me")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + rawToken))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                containsString("error=\"invalid_token\"")
            ))
            .andExpect(unauthenticated());

        verify(jwtDecoder).decode(rawToken);
    }
}
~~~

Ở đây `rawToken` chỉ là chuỗi đầu vào đủ đúng cú pháp Bearer token để đến decoder; nó **không cần là JWT có ba phần** vì decoder đã được mock. Nếu client gửi token có cú pháp HTTP không hợp lệ ngay từ đầu, `BearerTokenResolver` có thể chặn trước khi gọi decoder — đó là một ca khác.

Những assertion này kiểm tra ba lớp trách nhiệm:

1. `verify(jwtDecoder).decode(rawToken)` chứng minh filter chain chuyển đúng token đến decoder.
2. `401 Unauthorized` và `WWW-Authenticate` chứa `invalid_token` chứng minh hệ thống từ chối token ở tầng HTTP authentication.
3. `unauthenticated()` chứng minh request không được nhận một danh tính xác thực hợp lệ sau lỗi.

Nếu chỉ mock decoder mà không gửi header trong `mockMvc.perform(...)`, phần stub có thể không được gọi. Nếu chỉ thêm `@WithMockUser` hoặc `with(jwt())`, request có thể được xem là đã đăng nhập từ trước, khiến bài test không còn đo được tình huống cần kiểm tra.

### 4.2. Token hết hạn và JWT không đạt validation

Hết hạn `exp`, issuer `iss` sai, audience `aud` không hợp lệ hoặc không đạt validator tùy chỉnh là những lý do phổ biến để từ chối JWT. Trong một ứng dụng dùng `NimbusJwtDecoder` cùng các validators thích hợp, lỗi xác thực JWT thường được biểu diễn qua `BadJwtException` hoặc subtype của nó (ví dụ `JwtValidationException`).

Nếu mục đích là kiểm tra HTTP response **khi decoder báo token hết hạn**, có thể mô phỏng như sau trong cùng test class:

~~~java
@Test
void expiredTokenReportedByDecoderIsRejected() throws Exception {
    String rawToken = "expired-token";

    when(jwtDecoder.decode(rawToken))
        .thenThrow(new BadJwtException("JWT expired"));

    mockMvc.perform(get("/api/me")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + rawToken))
        .andExpect(status().isUnauthorized())
        .andExpect(header().string(
            HttpHeaders.WWW_AUTHENTICATE,
            containsString("invalid_token")
        ))
        .andExpect(unauthenticated());

    verify(jwtDecoder).decode(rawToken);
}
~~~

**Giới hạn của cách mock:** Test này không chứng minh Java đã đối chiếu `exp` với đồng hồ hay đã xác minh chữ ký RSA/ECDSA thật. Nó chứng minh **hệ thống HTTP xử lý đúng một kết quả từ chối của decoder**. Kiểm tra bản thân thuật toán/validator thuộc một test riêng với decoder thật và JWT đầu vào có thể kiểm soát.

Không nên làm một “test hết hạn” bằng cách trả từ `Mockito` một đối tượng `Jwt` có `expiresAt` trong quá khứ rồi mong filter tự động phát hiện. Khi mock `JwtDecoder.decode()` trả về `Jwt`, phần validate của decoder thật đã bị bỏ qua; `JwtAuthenticationProvider` thường tin kết quả decoder trả về là hợp lệ.

## 5. Cần có test đối chứng: token được decoder chấp nhận

Nếu tất cả test đều trả 401, có thể ứng dụng đang từ chối mọi request vì thiếu filter, thiếu converter hoặc cấu hình sai. Một ca token hợp lệ giúp xác nhận đường thành công và kiểm tra mock đang tác động đúng thành phần.

Thêm các import sau vào `JwtDecoderFailureTest`:

~~~java
import java.time.Instant;
import org.springframework.security.oauth2.jwt.Jwt;

import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
~~~

Rồi thêm phương thức:

~~~java
@Test
void acceptedTokenPassesDecoderAndReachesController() throws Exception {
    String rawToken = "accepted-token";
    Instant now = Instant.now();

    Jwt jwt = Jwt.withTokenValue(rawToken)
        .header("alg", "RS256")
        .subject("alice")
        .issuedAt(now)
        .expiresAt(now.plusSeconds(600))
        .claim("scope", "profile orders.read")
        .build();

    when(jwtDecoder.decode(rawToken)).thenReturn(jwt);

    mockMvc.perform(get("/api/me")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + rawToken))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.subject").value("alice"));

    verify(jwtDecoder).decode(rawToken);
}
~~~

Ở test này, `JwtDecoder` trả về một `Jwt` đã được dựng sẵn. `JwtAuthenticationProvider` có thể chuyển nó thành `JwtAuthenticationToken`, rồi controller nhận subject `alice`. Kết quả 200 cho thấy cấu hình pipeline chấp nhận Bearer JWT do decoder cung cấp.

Giá trị `.header("alg", "RS256")` minh họa claim/header của JWT; nó **không khiến mock thực hiện kiểm tra RS256**. Dòng `when(jwtDecoder.decode(rawToken)).thenReturn(jwt)` mới là thứ xác định kết quả xác thực trong test này.

### 5.1. Token hợp lệ vẫn có thể bị 403 khi thiếu quyền

Ta có route `/api/orders` yêu cầu authority `SCOPE_orders.read`. Converter mặc định của resource server thường trích `scope` hoặc `scp` và tạo authority tiền tố `SCOPE_`.

~~~java
@Test
void validTokenWithoutRequiredScopeGetsForbidden() throws Exception {
    String rawToken = "token-without-orders-scope";
    Instant now = Instant.now();

    Jwt jwt = Jwt.withTokenValue(rawToken)
        .header("alg", "RS256")
        .subject("alice")
        .issuedAt(now)
        .expiresAt(now.plusSeconds(600))
        .claim("scope", "profile")
        .build();

    when(jwtDecoder.decode(rawToken)).thenReturn(jwt);

    mockMvc.perform(get("/api/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + rawToken))
        .andExpect(status().isForbidden());

    verify(jwtDecoder).decode(rawToken);
}
~~~

So sánh hai trường hợp:

| Tình huống | Authentication | HTTP status điển hình |
| --- | --- | --- |
| Decoder ném `BadJwtException` | Không hình thành authentication hợp lệ | **401** |
| Decoder trả JWT hợp lệ, không có `SCOPE_orders.read` | Đã xác thực, nhưng không đủ authority | **403** |
| Decoder trả JWT hợp lệ, có `SCOPE_orders.read` | Đã xác thực và đủ quyền | **200** |

Nếu ứng dụng dùng custom `JwtAuthenticationConverter` hoặc policy khác, kỳ vọng 403/200 cần điều chỉnh theo authority thực tế. Phần 401 do token không hợp lệ vẫn thuộc lớp authentication trước authorization.

## 6. Vì sao BadJwtException và JwtException không hoàn toàn giống nhau?

Tên “decoder trả lỗi” rất rộng. Không nên kỳ vọng mọi loại exception đều trả 401 trong mọi cấu hình.

Các ngoại lệ thường có ý nghĩa khác nhau:

| Nguồn lỗi | Ví dụ | Thành phần chịu trách nhiệm | Kỳ vọng thường gặp |
| --- | --- | --- | --- |
| Không có Bearer token | Thiếu `Authorization` | Entry point / filter chain | **401**, challenge `Bearer`; có thể không có `invalid_token` |
| Header Bearer sai cú pháp | Header lặp, token chứa ký tự không hợp lệ | `BearerTokenResolver` | Lỗi request ở filter trước decoder; status/error tùy loại lỗi |
| `BadJwtException` | JWT không hợp lệ, chữ ký sai, validation thất bại | `JwtDecoder` → `JwtAuthenticationProvider` | **401**, `invalid_token` |
| `JwtValidationException` | Hết hạn/issuer/audience vi phạm validator được cấu hình | JWT validator/decoder | Thường là **401**, `invalid_token` |
| `JwtException` khác, phản ánh lỗi hạ tầng | Không tải được JWKS, cấu hình/khóa hỏng, decoder gặp lỗi hệ thống | Decoder hoặc hạ tầng liên quan | Có thể trở thành `AuthenticationServiceException` và được đẩy ra như lỗi hệ thống; **không mặc định assert 401** |
| Token hợp lệ, thiếu scope | JWT decode thành công, authorization từ chối | `AuthorizationFilter` / access denied handler | **403** |

Ở Spring Security Resource Server, `JwtAuthenticationProvider` xử lý `BadJwtException` bằng cách báo Bearer token không hợp lệ (`InvalidBearerTokenException`). Với các `JwtException` khác, nó có thể bọc lỗi thành `AuthenticationServiceException` để phân biệt lỗi hệ thống với thông tin đăng nhập sai. Các failure handler có thể tiếp tục ném lỗi dịch vụ thay vì biến nó thành `401 invalid_token`.

Do đó, test mục tiêu “**JWT bị từ chối vì decoder kết luận token không hợp lệ**” nên chủ động mock `BadJwtException`. Nếu muốn kiểm tra sự cố JWKS/decoder không hoạt động, hãy làm một test khác với hợp đồng lỗi 5xx, cơ chế fallback, giám sát và handler phù hợp với hệ thống.

Ví dụ sau chỉ minh họa một lỗi loại khác, **không đưa ra assertion HTTP 401**:

~~~java
when(jwtDecoder.decode("token-service-failure"))
    .thenThrow(new org.springframework.security.oauth2.jwt.JwtException(
        "Unable to retrieve verification keys"
    ));
~~~

Cách thiết kế test cần trả lời câu hỏi: “Client đang gửi token sai” hay “Hệ thống không thể xác minh token vì lỗi nội bộ”? Hai tình huống nên được ghi nhận khác nhau dù đều không được phép đi tiếp tới tài nguyên bảo vệ.

### 6.1. Kiểm tra đúng challenge header

Với Bearer token không hợp lệ, một phản hồi minh họa là:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token", error_description="..."
~~~

Thay vì so sánh nguyên chuỗi `WWW-Authenticate` chứa mô tả exception, nên dùng:

~~~java
.andExpect(status().isUnauthorized())
.andExpect(header().string(
    HttpHeaders.WWW_AUTHENTICATE,
    containsString("error=\"invalid_token\"")
))
~~~

Mô tả lỗi và thứ tự thuộc tính có thể thay đổi giữa các phiên bản hoặc custom entry point. Ngoài ra, ứng dụng production không nên vô tình trả chi tiết nhạy cảm như đường dẫn key store hoặc thông tin nội bộ của decoder vào error description.

Nếu request **không có header** thì phản hồi 401 có thể chỉ chứa `WWW-Authenticate: Bearer`. Không nên áp assertion `invalid_token` của token sai cho ca chưa gửi token.

## 7. Phân biệt kiểm tra decoder với helper jwt() của spring-security-test

`SecurityMockMvcRequestPostProcessors.jwt()` thiết lập sẵn JWT authentication phục vụ kiểm tra authorization. Ví dụ:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.mockito.Mockito.verifyNoInteractions;

@Test
void mockedJwtAuthenticationDoesNotUseDecoder() throws Exception {
    mockMvc.perform(get("/api/me")
            .with(jwt().jwt(token -> token.subject("alice"))))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.subject").value("alice"));

    verifyNoInteractions(jwtDecoder);
}
~~~

Test này vẫn có giá trị. Nó có thể nhanh chóng xác nhận endpoint sử dụng principal `Jwt` và những quy tắc authorization với claim/scope giả lập. Tuy nhiên, `verifyNoInteractions(jwtDecoder)` cho thấy decoder không xử lý token đầu vào trong request trên.

Để chứng minh decoder lỗi dẫn tới từ chối HTTP, so sánh:

~~~java
// KIỂM TRA PHÂN QUYỀN: có sẵn JwtAuthenticationToken.
mockMvc.perform(get("/api/me").with(jwt()));

// KIỂM TRA XÁC THỰC QUA HEADER: gửi token để filter gọi JwtDecoder.
mockMvc.perform(get("/api/me")
    .header(HttpHeaders.AUTHORIZATION, "Bearer token-with-invalid-signature"));
~~~

Tương tự, `@WithMockUser` và `with(user("alice"))` thiết lập principal giả lập; chúng không kiểm tra JWT được giải mã, chữ ký hay Bearer filter. Không trộn các post-processor xác thực giả lập với test `decode()` lỗi, bởi request có thể đã có authentication trước khi filter xem header.

Khi cần bao phủ cả hai loại hành vi, nên giữ hai nhóm test rõ ràng:

- **Authorization unit/integration tests:** dùng `jwt()` để tạo các scope và principal mong muốn, kiểm tra 200/403 nhanh.
- **HTTP Bearer authentication tests:** gửi header, điều khiển hoặc dùng decoder thật, kiểm tra 200/401/403 và lời gọi `decode()`.

## 8. Ca âm tính bổ sung để chứng minh đúng vị trí thất bại

### 8.1. Không gửi Bearer token: decoder không được gọi

Trong cùng class, có thể viết:

~~~java
@Test
void missingTokenIsRejectedBeforeDecoder() throws Exception {
    mockMvc.perform(get("/api/me"))
        .andExpect(status().isUnauthorized());

    verifyNoInteractions(jwtDecoder);
}
~~~

Cần import `verifyNoInteractions` của Mockito. Request không có header thì resolver không có token để chuyển xuống decoder. 401 ở đây chứng minh tài nguyên được bảo vệ, nhưng **không phải** bằng chứng decoder từ chối token.

### 8.2. Token bị parser/header resolver từ chối trước decoder

Nếu header sai cú pháp, `BearerTokenResolver` có thể tạo lỗi trước khi `JwtDecoder` nhận đầu vào:

~~~java
@Test
void malformedBearerHeaderIsRejectedBeforeDecoder() throws Exception {
    mockMvc.perform(get("/api/me")
            .header(HttpHeaders.AUTHORIZATION, "Bearer token with spaces"))
        .andExpect(status().is4xxClientError());

    verifyNoInteractions(jwtDecoder);
}
~~~

Đây là một ví dụ với `DefaultBearerTokenResolver` mặc định: token có dấu cách bên trong không phù hợp cú pháp Bearer credential; bộ lọc có thể từ chối bằng phản hồi lỗi client, với mã lỗi OAuth2 và HTTP status tùy tình huống hoặc cấu hình resolver/entry point. Giá trị cốt lõi là **decoder không được gọi** khi request bị chặn ở bước đọc header.

Không nên lấy chuỗi “JWT trông giống bị lỗi” rồi suy luận filter chắc chắn đã gọi decoder. Phải xác nhận bằng `verify(jwtDecoder).decode(rawToken)` hoặc một công cụ tương đương.

### 8.3. MockMvc có thực sự chạy Spring Security filters?

Một cách dựng `MockMvc` bằng `standaloneSetup(controller)` có thể bỏ qua filter chain. Với setup thủ công dựa trên `WebApplicationContext`, cần tích hợp Spring Security:

~~~java
import static org.springframework.security.test.web.servlet.setup
    .SecurityMockMvcConfigurers.springSecurity;

MockMvc securedMvc = MockMvcBuilders
    .webAppContextSetup(webApplicationContext)
    .apply(springSecurity())
    .build();
~~~

`@SpringBootTest` kết hợp `@AutoConfigureMockMvc` thông thường giúp tích hợp filters tự động. Tránh `@AutoConfigureMockMvc(addFilters = false)` trong bài test cần xác minh Bearer authentication. Một dấu hiệu đáng ngờ là request không có token vẫn trả 200 hoặc decoder mock không nhận bất kỳ lời gọi nào.

### 8.4. Nhiều SecurityFilterChain có thể làm thay đổi kết quả

Ứng dụng có thể cấu hình nhiều chain: `/api/**` dùng Bearer JWT, còn `/web/**` dùng form login. Nếu request rơi vào chain không chứa `oauth2ResourceServer().jwt()` thì `JwtDecoder` sẽ không được gọi, và client có thể nhận redirect 302 thay vì challenge 401.

Trong test, hãy chọn đúng endpoint đã được resource server bảo vệ, giữ `MockMvc` dùng cấu hình gần với runtime, và kiểm tra cả token hợp lệ lẫn không hợp lệ. Đừng sửa kỳ vọng 401 thành 302 chỉ để test xanh khi cấu hình chain không như dự kiến.

## 9. Kiểm tra JWT thật khác với mock lỗi decoder

Mock decoder giúp kiểm tra ánh xạ *ngoại lệ → hành vi HTTP* một cách ổn định. Nó thích hợp khi ta muốn biết lớp Servlet Security có chặn request với `BadJwtException` hay không, độc lập với khóa, issuer và mạng.

Để kiểm chứng việc **tự giải mã và xác thực JWT**, cần thêm test với decoder thật, chẳng hạn `NimbusJwtDecoder` được tạo từ khóa công khai kiểm thử, token ký bằng khóa riêng tương ứng và validator issuer/audience/expiry giống cấu hình ứng dụng. Khi đó có thể chuẩn bị:

1. JWT được ký đúng và còn hạn: decoder chấp nhận.
2. JWT bị sửa payload nhưng vẫn giữ chữ ký cũ: decoder từ chối.
3. JWT hết hạn: decoder từ chối nếu expiry validator được bật.
4. JWT có `iss`/`aud` sai: decoder từ chối **nếu** ứng dụng có validator cho từng claim.
5. JWKS/issuer không thể truy cập: kiểm tra lỗi vận hành riêng, tránh coi đó là token sai mật khẩu hay sai chữ ký.

Nếu hệ thống sử dụng decoder dựa trên JWKS từ IdP, cần tách kiểm tra xử lý token sai khỏi tình huống mất mạng hoặc rotation khóa. Đối với unit/integration test thông thường, hạn chế phụ thuộc IdP bên ngoài; dùng key fixture hoặc endpoint JWKS giả lập khi thật sự cần kiểm tra tích hợp.

Trong cả hai loại test, một nguyên tắc không đổi: **JWT phải đi qua authentication entry point và filter chain mà hệ thống thực sự dùng**. Kết quả `200 OK` từ `jwt()` post-processor không thay thế bằng chứng chữ ký JWT đã được xác thực.

## 10. Bảng ca kiểm thử đề xuất

| Ca | Request / Stub | Decoder được gọi? | Kỳ vọng |
| --- | --- | --- | --- |
| JWT sai chữ ký | Bearer token; `decode()` ném `BadJwtException` | Có | **401**, `invalid_token`, chưa xác thực |
| JWT hết hạn | Bearer token; decoder mock báo `BadJwtException` | Có | **401**, `invalid_token` |
| JWT hợp lệ | Bearer token; decoder mock trả `Jwt` | Có | **200**, subject xuất hiện trong response |
| JWT hợp lệ nhưng thiếu scope | Bearer token; decoder trả JWT thiếu authority | Có | **403** |
| Không có token | Không gửi header | Không | **401** với Bearer challenge |
| Header Bearer sai cú pháp | Header chứa token có dấu cách không hợp lệ | Không | **4xx** do resolver/entry point xử lý; kiểm tra mã cụ thể theo cấu hình |
| Sử dụng `with(jwt())` | Principal giả lập, không có Bearer header | Không | 200/403 tùy quyền, không kiểm tra decoder |
| Lỗi dịch vụ decoder | Decoder ném `JwtException` không phải `BadJwtException` | Có | Kiểm tra chính sách lỗi hệ thống, không mặc nhiên 401 |
| Lỗi validation thật | JWT ký sai, hết hạn, issuer/audience không hợp lệ | Có, decoder thật | Tùy validator đã cấu hình; token không hợp lệ bị từ chối |

**Tiêu chí hoàn thành bài thực hành:** Có ít nhất một request Bearer khiến mock `JwtDecoder.decode()` ném `BadJwtException`; kết quả là **401 Unauthorized**, `WWW-Authenticate` chứa `invalid_token`, `unauthenticated()` và `verify(decoder).decode(...)` thành công. Một request khác được decoder trả JWT hợp lệ phải đến controller; thiếu token phải bị chặn trước decoder. Khi phân biệt được các nhánh đó, bộ test chứng minh ứng dụng **xử lý lỗi decoder trên luồng xác thực HTTP thật của MockMvc**, thay vì chỉ mô phỏng người dùng đã đăng nhập.

