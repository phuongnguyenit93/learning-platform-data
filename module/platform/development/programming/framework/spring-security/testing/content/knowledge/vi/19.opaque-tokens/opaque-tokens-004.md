# Giới hạn của helper không gọi introspection endpoint

Trong kiểm thử **Opaque token** của Spring Security, có hai kiểu kết quả nhìn bên ngoài rất giống nhau: request mang danh tính đã xác thực và được API trả `200 OK`, hoặc request thực sự gửi Bearer token rồi được **resource server** kiểm tra thông qua cơ chế **token introspection**. Hai tình huống này có ý nghĩa khác nhau.

`spring-security-test` cung cấp `SecurityMockMvcRequestPostProcessors.opaqueToken()` để giả lập `BearerTokenAuthentication`. Helper giúp kiểm thử phân quyền theo scope, thuộc tính principal và hành vi controller nhanh, ổn định. Tuy nhiên, nó **không gửi token tới introspection endpoint** và **không gọi `OpaqueTokenIntrospector.introspect()`**. Vì vậy, một test thành công khi dùng `with(opaqueToken())` không chứng minh rằng access token còn hiệu lực, chưa bị thu hồi, được authorization server nhận diện hoặc có các scope thật.

Bài này thuộc module `SPRING_SECURITY_TESTING`, nơi người học kiểm chứng xác thực, phân quyền và cơ chế bảo vệ HTTP bằng `spring-security-test` trên Servlet/Reactive. Trọng tâm ở đây là **MockMvc cho ứng dụng Servlet**; cuối bài có đối chiếu với WebTestClient/Reactive để tránh nhầm lẫn cùng loại helper.

Sau khi học, bạn có thể:

- Giải thích rõ helper `opaqueToken()` mô phỏng điều gì và bỏ qua những bước nào.
- Chọn giữa kiểm thử authorization bằng principal giả và kiểm thử luồng Bearer token qua `OpaqueTokenIntrospector`.
- Dùng `MockMvc` gửi `Authorization: Bearer ...`, giả lập kết quả introspection và xác minh `introspect(rawToken)` được gọi.
- Phân biệt 401 do token bị từ chối, 403 do thiếu scope và 200 khi token được chấp nhận.
- Biết khi nào phải có HTTP stub cho introspection endpoint thay vì chỉ mock Java interface.

## 1. Opaque token là gì và tại sao cần introspection?

Khác với JWT thường chứa claims có thể đọc và kiểm tra bằng decoder, **opaque access token** được resource server xem như một chuỗi không tự giải thích được quyền và trạng thái của nó. Resource server cần một nguồn thông tin đáng tin cậy để biết token có hiệu lực và có những quyền gì. Với Spring Security OAuth2 Resource Server, nguồn đó thường là **OAuth 2.0 Token Introspection Endpoint** theo RFC 7662.

Ví dụ, client gọi API:

```http
GET /api/me HTTP/1.1
Authorization: Bearer opq-7b9c-client-token
```

Resource server lấy chuỗi `opq-7b9c-client-token` và yêu cầu introspection. Trong một triển khai điển hình, server gửi HTTP POST đến authorization server, thường với client credentials dùng riêng cho introspection:

```http
POST /oauth2/introspect HTTP/1.1
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <resource-server-client-credentials>

token=opq-7b9c-client-token
```

Một phản hồi token còn hiệu lực có thể là:

```json
{
  "active": true,
  "sub": "alice",
  "scope": "profile orders.read",
  "client_id": "mobile-app",
  "exp": 1799999999
}
```

Một token không còn hợp lệ có thể được biểu diễn bằng:

```json
{
  "active": false
}
```

Hai chi tiết dễ nhầm:

1. Introspection endpoint có thể trả **HTTP 200** kèm `"active": false`. Điều này **không có nghĩa API được phép trả 200**; resource server phải từ chối Bearer token đó.
2. Header `Authorization: Bearer ...` là thông tin client gửi tới resource server. Header `Authorization: Basic ...` trong ví dụ introspection là cách **resource server xác thực với authorization server**. Đây là hai kết nối và hai mục đích riêng.

Trong ứng dụng thật, `OpaqueTokenIntrospector` có thể dùng HTTP để lấy thông tin active, subject, scope và các thuộc tính khác. Nó chuyển kết quả hợp lệ thành `OAuth2AuthenticatedPrincipal` để Spring Security tạo authentication và thực hiện authorization.

### Luồng khi request chứa Bearer token thật

```mermaid
sequenceDiagram
    participant C as Client / MockMvc
    participant F as BearerTokenAuthenticationFilter
    participant P as OpaqueTokenAuthenticationProvider
    participant I as OpaqueTokenIntrospector
    participant S as Authorization Server
    participant A as API controller
    C->>F: Authorization: Bearer opq-...
    F->>P: Xác thực chuỗi token
    P->>I: introspect(token)
    I->>S: HTTP POST introspection (triển khai thật)
    alt Token active
        S-->>I: active=true, sub, scope...
        I-->>P: OAuth2AuthenticatedPrincipal
        P-->>F: BearerTokenAuthentication
        F->>A: Request đã xác thực
        A-->>C: 200, hoặc 403 nếu thiếu quyền
    else Token inactive/không hợp lệ
        S-->>I: active=false
        I-->>P: Từ chối token
        P-->>F: Lỗi xác thực
        F-->>C: 401 Unauthorized
    end
```

Sơ đồ mô tả **triển khai introspector thật có giao tiếp mạng**. Khi `OpaqueTokenIntrospector` là Mockito mock, mũi tên từ introspector tới authorization server **không xảy ra**. Khi dùng helper `opaqueToken()`, phần đường đi qua `BearerTokenAuthenticationFilter` tới introspector cũng được bỏ qua.

## 2. Helper opaqueToken() thực sự làm gì?

Trong MockMvc, cú pháp quen thuộc là:

```java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.opaqueToken;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;

mockMvc.perform(get("/api/me")
    .with(opaqueToken()));
```

`opaqueToken()` là **request post-processor của thư viện test**. Nó chuẩn bị authentication giả lập có principal kiểu `OAuth2AuthenticatedPrincipal`, token và authorities để request được xử lý như đã xác thực. Nó không kiểm tra mật khẩu, không gửi HTTP introspection request, không truy vấn trạng thái `active`, không tra cứu revocation và không xác nhận chữ ký nào.

Giá trị mặc định của helper phù hợp cho bài test nhanh, nhưng trong trường hợp cần subject/scope xác định rõ, hãy tự thiết lập thuộc tính hoặc authorities:

```java
mockMvc.perform(get("/api/me")
    .with(opaqueToken()
        .attributes(attrs -> attrs.put("sub", "alice"))));

mockMvc.perform(get("/api/orders")
    .with(opaqueToken()
        .authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        )));
```

Các ví dụ trên đặt dữ liệu **trực tiếp trong test**. Scope được khai báo không phải kết quả một authorization server đã cấp và kiểm tra. Mọi assertion 200/403 sử dụng các request này là bằng chứng về **authorization với danh tính giả lập**, không phải về khả năng introspect token.

Bảng sau giúp chọn đúng công cụ:

| Công cụ | Tạo authentication như thế nào? | Có gọi `introspect(token)`? | Điều có thể chứng minh |
| --- | --- | --- | --- |
| `with(opaqueToken())` | Gắn sẵn `BearerTokenAuthentication` kiểm thử | **Không** | Quyền truy cập và cách API đọc principal/authority |
| `with(opaqueToken().authorities(...))` | Gắn danh sách quyền do test chọn | **Không** | Cho phép/từ chối theo scope |
| `@WithMockUser` | Gắn user giả lập, thường dạng `UsernamePasswordAuthenticationToken` | **Không** | Rule áp dụng cho user/role giả lập |
| `GET ...` + `Authorization: Bearer token` + `OpaqueTokenIntrospector` mock | Filter chain gọi Java interface được mock | **Có, ở mức interface** | Kết quả 200/401/403 khi introspector trả principal hoặc ném lỗi |
| `GET ...` + Bearer header + introspector HTTP thật + local stub server | Filter chain gọi introspector thật; introspector gửi HTTP đến stub | **Có, bao gồm HTTP** | URL, phương thức, credentials, body, parse `active`/scope và response của API |

**Nguyên tắc:** Chọn tầng kiểm thử theo điều cần xác nhận. Helper không “sai”; nó chỉ bỏ qua luồng introspection một cách có chủ đích để bài kiểm tra phân quyền tập trung và ít phụ thuộc.

## 3. Ví dụ Servlet API bảo vệ bằng opaque token

Để quan sát sự khác nhau, dùng ứng dụng Spring Boot Servlet có các dependency tương ứng. Với Gradle và Spring Boot dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

### 3.1. Cấu hình security

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OpaqueApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/orders")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers("/api/**").authenticated()
                .anyRequest().permitAll()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(Customizer.withDefaults())
            );

        return http.build();
    }
}
```

`oauth2ResourceServer(...opaqueToken(...))` đăng ký cơ chế xác thực Bearer token bằng opaque introspection. Ứng dụng cần một bean `OpaqueTokenIntrospector` phù hợp. Trong production, bean có thể do Spring Boot cấu hình dựa trên URI/credentials hoặc do ứng dụng khai báo. Trong bài test, bean này có thể được thay bằng mock để điều khiển kết quả mà không gọi authorization server.

Không tắt toàn bộ security filter chain để làm test chạy. Các request GET ở ví dụ này không gây thêm yêu cầu CSRF, vì thế có thể tập trung vào xác thực/ phân quyền.

### 3.2. Controller để phân biệt identity và scope

```java
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OpaqueApiController {

    @GetMapping("/api/me")
    String me(Authentication authentication) {
        return authentication.getName();
    }

    @GetMapping("/api/orders")
    String orders() {
        return "orders-visible";
    }
}
```

Ở endpoint `/api/me`, body phản ánh principal name được Spring Security tạo. Endpoint `/api/orders` đòi `SCOPE_orders.read` nên một principal đã xác thực nhưng thiếu scope vẫn bị từ chối bằng 403.

## 4. Kiểm thử bằng helper: 200 không chứng minh introspection

Dùng Spring Boot test với `MockMvc` và `@MockitoBean` để quan sát xem introspector có được gọi không. `@MockitoBean` có trong Spring Framework 6.2+, thường dùng từ Spring Boot 3.4. Với phiên bản cũ hơn, chọn cơ chế thay bean bằng mock tương thích, chẳng hạn `@MockBean` khi được hỗ trợ.

Ví dụ sau đặt principal cụ thể, khiến body dễ kiểm tra:

```java
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verifyNoInteractions;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.opaqueToken;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OpaqueTokenHelperTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OpaqueTokenIntrospector introspector;

    @Test
    void helperProvidesIdentityWithoutCallingIntrospector()
            throws Exception {
        OAuth2AuthenticatedPrincipal principal =
            new DefaultOAuth2AuthenticatedPrincipal(
                "alice",
                Map.of("sub", "alice"),
                List.of(
                    new SimpleGrantedAuthority("SCOPE_profile")
                )
            );

        mockMvc.perform(get("/api/me")
                .with(opaqueToken().principal(principal)))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));

        verifyNoInteractions(introspector);
    }
}
```

Kết quả có vẻ “đã đăng nhập”: `GET /api/me` trả 200 và Alice là principal. Tuy nhiên, `verifyNoInteractions(introspector)` chứng minh không có quá trình xác minh token qua introspector. Không có lý do để chờ authorization server, cũng không có chỗ nào kiểm tra `active=false`.

Bài test này vẫn hữu ích để kiểm tra endpoint có đọc danh tính đúng hay không. Nhưng nếu acceptance criterion ghi “token bị thu hồi phải bị chặn”, dùng helper như trên là **sai tầng kiểm thử**.

### 4.1. Dùng helper để kiểm tra quyền theo scope

Tiếp tục trong class trên, thêm:

```java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.opaqueToken;

@Test
void helperMaySimulateAllowedScope() throws Exception {
    mockMvc.perform(get("/api/orders")
            .with(opaqueToken().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )))
        .andExpect(status().isOk())
        .andExpect(content().string("orders-visible"));

    verifyNoInteractions(introspector);
}

@Test
void helperMaySimulateInsufficientScope() throws Exception {
    mockMvc.perform(get("/api/orders")
            .with(opaqueToken().authorities(
                new SimpleGrantedAuthority("SCOPE_profile")
            )))
        .andExpect(status().isForbidden());

    verifyNoInteractions(introspector);
}
```

Hai test này chứng minh rule `hasAuthority("SCOPE_orders.read")` chặn hoặc cho phép đúng theo các authorities được test gắn vào authentication. Chúng **không** chứng minh introspection endpoint trả `scope` chính xác, cũng không chứng minh scope đã được trích xuất và ánh xạ từ JSON response thật.

Việc scope có tiền tố `SCOPE_` là quy ước Spring Security thường dùng khi chuyển scope sang authority. Khi tự dựng principal/authorities, test phải dùng chính xác authority mà rule trong ứng dụng yêu cầu. Nếu ứng dụng dùng bộ chuyển đổi quyền tùy biến, hãy điều chỉnh test theo contract đó.

## 5. Kiểm thử đường Bearer thật qua MockMvc và mock introspector

Để kiểm tra ứng dụng có **thực sự yêu cầu introspection** sau khi nhận header Bearer, không dùng `with(opaqueToken())`. Gửi header trực tiếp:

```java
mockMvc.perform(get("/api/me")
    .header(HttpHeaders.AUTHORIZATION, "Bearer opaque-active"));
```

Khi `SecurityFilterChain` có opaque resource server, filter sẽ lấy chuỗi token và đi qua `OpaqueTokenAuthenticationProvider`, gọi `OpaqueTokenIntrospector.introspect(rawToken)`. Ta có thể mock interface introspector để cho kết quả ổn định và kiểm tra đường xử lý.

### 5.1. Tạo class kiểm thử luồng Bearer

Đây là một ví dụ độc lập dựa trên cấu hình/controller ở phần 3. Các import được nêu đầy đủ để người học có thể tách test này thành class riêng.

```java
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.response
    .SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OpaqueTokenIntrospectionFlowTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OpaqueTokenIntrospector introspector;

    @Test
    void activeTokenReachesController() throws Exception {
        String rawToken = "opaque-active";

        OAuth2AuthenticatedPrincipal principal =
            new DefaultOAuth2AuthenticatedPrincipal(
                "alice",
                Map.of("sub", "alice", "active", true),
                List.of(
                    new SimpleGrantedAuthority("SCOPE_orders.read")
                )
            );

        when(introspector.introspect(rawToken)).thenReturn(principal);

        mockMvc.perform(get("/api/me")
                .header(HttpHeaders.AUTHORIZATION,
                        "Bearer " + rawToken))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));

        verify(introspector).introspect(rawToken);
    }

    @Test
    void revokedOrInactiveTokenIsRejected() throws Exception {
        String rawToken = "opaque-revoked";

        when(introspector.introspect(rawToken))
            .thenThrow(new BadOpaqueTokenException(
                "Token is not active"
            ));

        mockMvc.perform(get("/api/me")
                .header(HttpHeaders.AUTHORIZATION,
                        "Bearer " + rawToken))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                containsString("invalid_token")
            ))
            .andExpect(unauthenticated());

        verify(introspector).introspect(rawToken);
    }

    @Test
    void missingTokenIsRejectedBeforeIntrospection() throws Exception {
        mockMvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized())
            .andExpect(unauthenticated());

        verifyNoInteractions(introspector);
    }
}
```

**Kết quả quan trọng:** 

- `activeTokenReachesController` chứng minh filter chuyển đúng token sang introspector và sử dụng principal trả về.
- `revokedOrInactiveTokenIsRejected` chứng minh lỗi `BadOpaqueTokenException` từ introspector khiến API từ chối bằng 401 thay vì cho controller thực thi.
- `missingTokenIsRejectedBeforeIntrospection` chứng minh request không có Bearer token không nên gọi introspector; 401 ở ca này khác nguyên nhân với 401 do token bị từ chối.

`BadOpaqueTokenException` đại diện cho trường hợp introspection kết luận token không hợp lệ. Không nên thay nó bằng một `RuntimeException` bất kỳ rồi mặc định sẽ được ánh xạ thành cùng HTTP 401: lỗi gọi introspection service, cấu hình credentials hoặc mạng có thể là **lỗi hạ tầng** cần cách xử lý khác.

### 5.2. Phân biệt token active nhưng không có quyền

Có token hợp lệ **không** đồng nghĩa đủ quyền vào mọi endpoint. Ví dụ `GET /api/orders` yêu cầu `SCOPE_orders.read` nhưng principal chỉ có `SCOPE_profile`:

```java
@Test
void activeTokenWithoutRequiredScopeGetsForbidden() throws Exception {
    String rawToken = "opaque-without-orders-scope";

    OAuth2AuthenticatedPrincipal principal =
        new DefaultOAuth2AuthenticatedPrincipal(
            "alice",
            Map.of("sub", "alice", "active", true),
            List.of(new SimpleGrantedAuthority("SCOPE_profile"))
        );

    when(introspector.introspect(rawToken)).thenReturn(principal);

    mockMvc.perform(get("/api/orders")
            .header(HttpHeaders.AUTHORIZATION,
                    "Bearer " + rawToken))
        .andExpect(status().isForbidden());

    verify(introspector).introspect(rawToken);
}
```

Hai lỗi cần phân biệt:

| Bối cảnh | Authentication | Kết quả điển hình |
| --- | --- | --- |
| Introspector từ chối token (inactive/revoked) | Không tạo danh tính hợp lệ | **401 Unauthorized** |
| Introspector chấp nhận token nhưng thiếu scope | Đã xác thực, không đủ authority | **403 Forbidden** |
| Introspector chấp nhận token và có scope | Đã xác thực, có quyền | **200 OK** |

Cả 401 và 403 đều có thể là phản hồi đúng tùy nguyên nhân. Nếu test tự gắn `opaqueToken().authorities(...)` thì chỉ kiểm tra được phần phân quyền; nó không quan sát việc introspector chấp nhận hoặc từ chối token.

### 5.3. Vì sao verify(introspector) vẫn chưa đủ để kiểm tra HTTP endpoint?

Trong test trên, `@MockitoBean` thay thế `OpaqueTokenIntrospector` thật. Mockito trả giá trị ngay trong JVM, nên:

```text
MockMvc -> BearerTokenAuthenticationFilter
        -> OpaqueTokenAuthenticationProvider
        -> Mockito mock OpaqueTokenIntrospector
        -> principal / exception
```

Test này kiểm tra **Spring Security có gọi introspector interface và xử lý kết quả đúng**. Nó **chưa gửi HTTP POST** tới authorization server. `verify(introspector).introspect(rawToken)` xác nhận lời gọi ở tầng Java, không phải HTTP request thật.

Vì vậy, không được viết báo cáo “đã kiểm thử kết nối introspection endpoint” chỉ dựa trên `verify()` của Mockito.

## 6. Khi nào cần kiểm thử chính HTTP introspection endpoint?

Nếu yêu cầu bao gồm xác minh URI, xác thực client, request form, JSON `active`, lỗi HTTP hoặc cách truyền scope, cần sử dụng **introspector thật** với một authorization server giả lập chạy cục bộ.

Một thiết kế integration test có thể gồm:

1. Khởi động HTTP stub server cục bộ (ví dụ WireMock hoặc MockWebServer) tại port động.
2. Cấu hình opaque resource server dùng introspection URI trỏ tới stub, kèm test client credentials.
3. Dùng bean `OpaqueTokenIntrospector` thật, không thay bằng `@MockitoBean`.
4. Stub response `active=true` với `sub/scope` và `active=false`; nếu cần, stub cả lỗi 401/500 hoặc timeout của authorization server.
5. Gửi request qua `MockMvc` với `Authorization: Bearer ...`.
6. Kiểm tra **cả** response của API **và** bản ghi HTTP POST mà stub đã nhận.

Với Spring Boot, cấu hình khái niệm của opaque resource server thường có dạng:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: http://localhost:18080/introspect
          client-id: resource-server-test
          client-secret: test-secret-only
```

Đây là **cấu hình minh họa**; trong test thật nên thay port bằng port động mà stub server cung cấp trước khi Spring khởi tạo context. Không đưa client secret production vào repository. Các tên property có thể được thay bằng bean `OpaqueTokenIntrospector` tự cấu hình tùy kiến trúc.

### 6.1. Một hợp đồng HTTP cần quan sát

Ví dụ, stub server nhận request:

```http
POST /introspect HTTP/1.1
Authorization: Basic <test-client-credentials>
Content-Type: application/x-www-form-urlencoded

token=opaque-active
```

Và trả:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"active":true,"sub":"alice","scope":"orders.read"}
```

Khi đó, kỳ vọng đối với request tới `GET /api/orders` là **200 OK** nếu introspector thật ánh xạ `orders.read` thành `SCOPE_orders.read` theo cấu hình.

Ở ca token bị thu hồi, stub trả:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"active":false}
```

Khi API nhận cùng opaque token qua header Bearer, kỳ vọng thường là **401 Unauthorized**. Cùng lúc, stub phải ghi nhận đã nhận POST có tham số `token=opaque-revoked`. Đây là bằng chứng mà helper `opaqueToken()` và một mock `OpaqueTokenIntrospector` không thể cung cấp.

Trong bài test kiểu này, cần kiểm tra tối thiểu: phương thức POST, đường dẫn introspection, form field `token`, thông tin xác thực client ở mức test, cách parse `active` và ánh xạ principal/authority. Không khẳng định có HTTP request nếu test chỉ dùng stub ở interface Java.

### 6.2. Những giới hạn của integration test dùng local stub

Stub cục bộ kiểm tra tích hợp HTTP giữa ứng dụng và một server mô phỏng. Nó vẫn không chứng minh authorization server production đã cấp token, áp dụng đúng quy tắc revocation hay có toàn bộ chính sách scope như mong đợi. Các kiểm thử hệ thống/end-to-end có thể cần một authorization server thật trong môi trường kiểm thử được kiểm soát.

Một số hệ thống có cache introspection, retry, timeout hoặc circuit breaker. Khi những thành phần đó được bật, số HTTP POST có thể khác số request tới API. Kỳ vọng “mỗi API request luôn gọi đúng một lần” phải dựa vào cấu hình và hành vi cache thực tế, không suy ra từ helper hay một test thành công đơn lẻ.

## 7. Những khẳng định test thường mắc sai

### “Tôi dùng opaqueToken(), nên token đã được introspect”

Không chính xác. `opaqueToken()` chỉ tạo authentication. Nó tương tự `with(jwt())` khi giả lập JWT đã được xác thực hoặc `@WithMockUser` khi giả lập người dùng. Không có introspection request.

### “Test trả 200, vậy token chưa bị thu hồi”

Không chính xác khi test dùng helper. Một token bị thu hồi vẫn có thể được gắn sẵn làm principal trong test. Nếu mục tiêu kiểm tra revocation, cần ít nhất làm cho introspector trả trạng thái token không hợp lệ và chứng minh request bị từ chối.

### “Tôi mock introspector rồi verify() nên đã kiểm tra HTTP kết nối tới IdP”

Chưa. Bạn đã kiểm tra lời gọi interface từ Spring Security. Đây là integration test có giá trị đối với filter chain nhưng bỏ qua lớp HTTP client và endpoint thực.

### “401 luôn chứng minh introspector từ chối token”

Không. 401 có thể đến từ việc **không có Bearer header**, header sai, lọt vào filter chain khác hoặc policy của entry point. Cần dùng `verify(introspector).introspect(rawToken)` để phân biệt ca đã đi tới introspector với ca bị chặn từ trước.

### “403 nghĩa là opaque token không hợp lệ”

Thường là không. Trong cấu hình resource server điển hình, 403 nghĩa là đã xác thực nhưng thiếu authority. Cần xác minh token có được introspect thành công không, principal có scope nào và rule yêu cầu gì.

### “Mock principal có scope là kiểm tra được ánh xạ scope từ response”

Không. Khi helper truyền thẳng `SCOPE_orders.read` vào authentication, bước parse `scope` từ JSON introspection response không diễn ra. Kiểm tra mapping này cần introspector thật hoặc test riêng đối với logic chuyển đổi mà ứng dụng định nghĩa.

## 8. Một ma trận test đủ tách bạch các tầng

| Ca thử | Cách dựng request / dữ liệu | Introspector interface được gọi? | HTTP introspection endpoint được gọi? | Ý nghĩa |
| --- | --- | --- | --- | --- |
| Phân quyền cho `orders.read` | `with(opaqueToken().authorities(...))` | Không | Không | Rule cho phép đúng authority |
| Phân quyền khi thiếu scope | `with(opaqueToken())` với authority không phù hợp | Không | Không | Rule trả 403 |
| Token active, mock interface | Bearer header + mock trả principal | Có | Không | Filter/provider dùng principal trả về |
| Token inactive, mock interface | Bearer header + `BadOpaqueTokenException` | Có | Không | Resource server từ chối với 401 |
| Không có Bearer header | Request không authentication | Không | Không | Entry point chặn request |
| Token active, HTTP stub | Bearer header + introspector thật + stub `active=true` | Có | Có, tới stub | Request/parse/authorization cùng hoạt động |
| Token revoked, HTTP stub | Bearer header + introspector thật + stub `active=false` | Có | Có, tới stub | Kiểm tra 401 khi HTTP introspection báo inactive |
| Token active trên IdP thực | Bearer header + tích hợp end-to-end | Có | Có, tới IdP | Kiểm thử hệ thống theo chính sách thực |

Những ca này không thay thế nhau. Bộ test nên dùng helper cho phần lớn biến thể authorization, rồi có một nhóm nhỏ kiểm tra Bearer authentication, cùng một số ca tích hợp HTTP introspection khi hệ thống phụ thuộc vào kết nối đó.

## 9. Lưu ý về Spring Security filter chain và Reactive

### 9.1. Bảo đảm MockMvc đang chạy filters

Với `@SpringBootTest` và `@AutoConfigureMockMvc` thông thường, request đi qua Servlet filters. Nếu tự dựng `MockMvc` từ `WebApplicationContext`, cần áp dụng Spring Security:

```java
import static org.springframework.security.test.web.servlet.setup
    .SecurityMockMvcConfigurers.springSecurity;

MockMvc mockMvc = MockMvcBuilders
    .webAppContextSetup(webApplicationContext)
    .apply(springSecurity())
    .build();
```

Nếu bạn dùng `standaloneSetup(controller)` mà không tích hợp security filters, hoặc `@AutoConfigureMockMvc(addFilters = false)`, test gửi Bearer header có thể gọi thẳng controller mà không introspect token. Một kiểm tra tối thiểu là: request **không có token** tới tài nguyên bảo vệ phải bị chặn.

Với nhiều `SecurityFilterChain`, hãy kiểm tra matcher và thứ tự chain: endpoint được test phải khớp chain bật `oauth2ResourceServer(...opaqueToken(...))`. Nếu đi vào chain form login hoặc JWT, kiểu lỗi và introspector được gọi sẽ khác.

### 9.2. Tương ứng ở WebFlux và WebTestClient

Với Spring Security Reactive, `SecurityMockServerConfigurers.mockOpaqueToken()` của `spring-security-test` phục vụ mục đích tương tự: tạo authentication giả lập trong `WebTestClient` để kiểm tra quyền truy cập. Helper Reactive này cũng **không có nghĩa endpoint introspection đã được gọi**.

Nếu muốn kiểm tra luồng opaque token thật ở Reactive, hãy gửi Bearer header vào WebTestClient có security filter chain phù hợp và dùng `ReactiveOpaqueTokenIntrospector` (mock interface hoặc implementation thật tùy mục tiêu). Không lấy kết luận từ một test Servlet để khẳng định WebFlux sẽ gọi cùng Java interface, vì API Servlet `OpaqueTokenIntrospector` và Reactive `ReactiveOpaqueTokenIntrospector` là hai contract riêng.

### 9.3. Tránh nhầm opaque token với JWT helper

`with(jwt())` tạo JWT authentication giả lập; `with(opaqueToken())` tạo opaque-token authentication giả lập. Cả hai hữu ích trong authorization tests và đều bỏ qua bước xác minh token thực tế. Nếu ứng dụng có cả JWT và opaque resource server trên các chain khác nhau, request phải đi đúng cơ chế để thử `JwtDecoder` hoặc `OpaqueTokenIntrospector` tương ứng.

## 10. Bài thực hành tổng hợp

Giả sử cần bảo đảm `/api/orders` chỉ cho phép token còn hiệu lực và có scope `orders.read`. Hãy dựng ba loại kiểm thử có mục tiêu riêng:

1. **Authorization:** Dùng `with(opaqueToken().authorities(new SimpleGrantedAuthority("SCOPE_orders.read")))` thì 200; bỏ scope thì 403. Sau mỗi phép thử, xác nhận introspector không bị gọi.
2. **Authentication qua filter chain:** Gửi `Authorization: Bearer opaque-active`; stub `introspector.introspect(...)` trả principal chứa `SCOPE_orders.read` và xác nhận 200. Với `opaque-revoked`, stub ném `BadOpaqueTokenException` và xác nhận 401 cùng Bearer challenge có `invalid_token`. Kiểm tra Mockito đã nhận đúng chuỗi token.
3. **Giao tiếp introspection qua HTTP:** Dùng introspector thật với local stub server; trả `active=true` và `active=false`, kiểm tra response 200/401 của API và xác nhận stub có nhận POST với `token`, client credentials và JSON được xử lý đúng.

Thử đối chứng bằng cách bỏ Bearer header. Khi endpoint bảo vệ trả 401 **nhưng introspector không được gọi**, bạn sẽ thấy rõ lý do không nên dùng mỗi assertion HTTP 401 để kết luận “đã kiểm tra introspection thất bại”.

**Tiêu chí hoàn thành:** Người học có thể chạy test `with(opaqueToken())` trả 200 trong khi `verifyNoInteractions(introspector)` vẫn đúng; viết được test Bearer header khiến `introspect(rawToken)` thực sự được gọi; và giải thích tại sao ngay cả test thứ hai cũng chưa chứng minh một **HTTP request tới introspection endpoint** đã xảy ra khi dùng Mockito mock. Ba bằng chứng đó phân định rõ phạm vi của helper, filter/provider và tích hợp HTTP.

