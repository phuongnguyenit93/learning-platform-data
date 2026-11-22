# HTTP client, kết nối, timeout và quản lý tài nguyên

Trong **Spring Security OAuth 2.0 / OIDC Resource Server** sử dụng **opaque access token**, xác thực một request có thể đòi hỏi ứng dụng gửi một HTTP request mới đến **Authorization Server** để **introspect** token. Vì vậy việc tùy chỉnh introspection không chỉ là sửa URL hoặc client secret: Resource Server phải quản lý **HTTP client, kết nối TLS, thời gian chờ, connection pool, giới hạn tài nguyên, vòng đời client và khả năng chịu lỗi** như một phần của đường đi xác thực.

Một request có bearer token hợp lệ vẫn có thể thất bại nếu pool hết connection, DNS gặp lỗi, TLS handshake quá chậm, Authorization Server trả lời trễ hoặc client không giải phóng socket. Ngược lại, nếu tìm cách “chữa” những sự cố đó bằng việc chấp nhận token chưa được introspect, API có thể mất ranh giới bảo mật.

Ví dụ Spring Boot thường thấy:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.com/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

Cấu hình trên xác định **điểm đến và credential introspection**. Nhưng khi triển khai ở môi trường có lưu lượng lớn, ta còn phải chủ động trả lời:

- Kết nối tới Authorization Server tối đa chờ bao lâu?
- Nếu tất cả connection trong pool đang bận, một request phải chờ bao lâu?
- Sau khi đã kết nối, chờ HTTP response trong bao lâu?
- Có nên tái sử dụng TCP/TLS connection? Pool có bao nhiêu connection?
- Khi Authorization Server lỗi hoặc bị rate limit, xử lý thế nào để vừa **fail closed** vừa không làm nghẽn API?
- Ai sở hữu HTTP client và ai chịu trách nhiệm đóng pool/thread khi ứng dụng dừng?
- Cần đo những chỉ số nào để phát hiện pool exhaustion, latency, TLS errors và lệch cấu hình?

> **Bối cảnh:** Orders API chạy Spring Boot 3.x / Spring Security 6.x trên Servlet stack, Authorization Server có introspection endpoint `https://login.example.com/oauth2/introspect`. Các giá trị timeout và kích thước pool trong bài là **ví dụ thiết kế**, không phải mặc định bắt buộc hay lời khuyên dùng nguyên xi cho mọi hệ thống. Cần đối chiếu API cụ thể của phiên bản Spring Security, Spring Boot và HTTP client trước khi tích hợp.

## 1. Tại sao HTTP client là một thành phần bảo mật?

Với opaque token, caller gửi:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.com
Authorization: Bearer ACCESS_TOKEN
```

Orders API phải xác thực bằng một đường riêng:

```http
POST /oauth2/introspect HTTP/1.1
Host: login.example.com
Authorization: Basic BASE64_INTROSPECTION_ID_AND_SECRET
Content-Type: application/x-www-form-urlencoded

token=ACCESS_TOKEN
```

Ở đây có hai credential khác nhau:

1. **Bearer token** của caller, đi từ caller → Orders API.
2. **Credential introspection** của Resource Server, đi từ Orders API → Authorization Server.

HTTP client của introspection mang **cả token cần kiểm tra lẫn credential để chứng minh quyền introspect**. Nếu tự chuyển URL tới host khác, vô hiệu hóa TLS hoặc ghi lại request body/header vào log, ứng dụng có thể làm lộ những credential này.

### 1.1. Luồng xử lý cơ bản

```mermaid
sequenceDiagram
    autonumber
    participant C as API Caller
    participant RS as Spring Resource Server
    participant Pool as Outbound HTTP Client / Pool
    participant AS as Authorization Server
    C->>RS: Authorization: Bearer opaque-token
    RS->>Pool: OpaqueTokenIntrospector.introspect(token)
    Pool->>Pool: Xin connection / DNS / TLS
    Pool->>AS: POST introspection (token + client auth)
    AS-->>Pool: active=true/false + attributes
    Pool-->>RS: HTTP response
    RS->>RS: Xác thực active, ánh xạ authorities
    RS->>RS: Kiểm tra scope/tenant/ownership
    alt Token và quyền hợp lệ
        RS-->>C: 200 / kết quả nghiệp vụ
    else Token inactive hoặc không đủ quyền
        RS-->>C: Từ chối
    end
```

Nếu không dùng cache, một API request có thể tương ứng với một outbound introspection request. Spring có thể xác minh opaque token ở nhiều request liên tiếp ngay cả khi access token giống nhau; vì vậy đặc tính của HTTP client ảnh hưởng trực tiếp tới **latency và availability** của Resource Server.

### 1.2. Những phần nào do Spring Security đảm nhiệm?

| Thành phần | Vai trò |
|---|---|
| `BearerTokenAuthenticationFilter` | Lấy Bearer token từ HTTP request |
| `OpaqueTokenAuthenticationProvider` | Điều phối xác thực bằng opaque token |
| `OpaqueTokenIntrospector` | Hợp đồng hỏi token có hợp lệ và nhận principal/attributes |
| Implementation introspector | Gửi HTTP introspection và chuyển response thành principal |
| `RestOperations`/HTTP client | Điều khiển request, connection, TLS, timeout, authentication, pool |
| `AuthorizationFilter`/method security | Kiểm tra authorities của caller |
| Domain service/policy | Kiểm tra tenant, ownership, trạng thái tài nguyên |

**Không sửa HTTP client để bù thiếu kiểm tra quyền**: `active=true` và kết nối thành công không cho phép mọi thao tác. API vẫn phải kiểm tra scope, audience/resource, client/subject và quyền trên từng đối tượng.

## 2. Hợp đồng HTTP của introspection theo RFC 7662

OAuth 2.0 Token Introspection (RFC 7662) dùng một HTTP endpoint được bảo vệ. Resource Server gửi token trong **form body** của request **POST**, có thể kèm `token_type_hint` nếu muốn:

```http
POST /oauth2/introspect HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded
Accept: application/json
Authorization: Basic BASE64_ID_COLON_SECRET

token=opaque-value&token_type_hint=access_token
```

Authorization Server trả:

```json
{
  "active": true,
  "scope": "orders.read",
  "sub": "customer-42",
  "client_id": "storefront-web",
  "aud": ["orders-api"],
  "iss": "https://login.example.com",
  "exp": 2000000000
}
```

hoặc:

```json
{
  "active": false
}
```

Chỉ những **token active** mới có thể trở thành một `Authentication` hợp lệ. Phản hồi `active=true` vẫn cần thỏa các điều kiện mà Orders API đặt ra.

### 2.1. HTTP 200 không đồng nghĩa token hợp lệ

Một introspection endpoint thường trả **HTTP 200 với `{"active":false}`** cho token không active. HTTP 200 chỉ biểu thị request introspection được xử lý thành công ở tầng giao thức; **`active`** mới biểu thị trạng thái token.

Ngược lại, HTTP 401 từ Authorization Server có thể do **client-id/client-secret introspection sai**. Nó không được diễn giải như một kết quả `active=false` bình thường nếu cần chẩn đoán đúng sự cố.

| Outbound HTTP / body | Ý nghĩa |
|---|---|
| `200 {"active":true,...}` | Introspection thành công; tiếp tục áp claim/resource policy |
| `200 {"active":false}` | Token không được chấp nhận |
| `401` tại endpoint introspection | Client authentication của Resource Server bị từ chối hoặc policy AS không cho introspect |
| `403` tại endpoint introspection | Caller introspection thiếu quyền theo chính sách AS |
| `429` | AS áp rate limit; đây không phải bằng chứng token hợp lệ |
| `5xx` | AS hoặc hạ tầng đang gặp lỗi |
| Timeout, TLS error, malformed response | Không có kết quả introspection đủ tin cậy |

**Không phân loại mọi lỗi outbound thành “token của user sai” rồi khuyên user đăng nhập lại.** Nếu lỗi do client secret hoặc AS timeout, đăng nhập lại không khắc phục căn nguyên.

### 2.2. Không nhầm `client_id` trong response với cấu hình introspection

`client_id=storefront-web` trong JSON là OAuth client **đã nhận access token**. Nó khác với `client-id=orders-api-introspector` trong cấu hình Resource Server dùng để **xác thực khi hỏi trạng thái token**.

Dùng credential introspection riêng của mỗi Resource Server giúp giảm quyền và cải thiện audit. HTTP client phải giữ bí mật đó; không bao giờ gửi client secret cho frontend.

## 3. Bốn nhóm thời gian chờ thường bị gộp nhầm

Một lời gọi HTTP không chỉ có “timeout” duy nhất. Các thư viện HTTP client thường có các ngưỡng thời gian khác nhau.

| Loại | Bắt đầu/áp dụng khi nào? | Nếu vượt ngưỡng |
|---|---|---|
| **Connection acquisition / pool lease timeout** | Chờ lấy connection trống từ pool khi pool đang bận | Không có connection để gửi request |
| **Connect timeout** | Thiết lập kết nối mạng đến endpoint (mức chính xác tùy implementation) | Không kết nối được trong thời hạn |
| **Response/read/socket timeout** | Chờ server gửi byte/response sau khi đã kết nối, hoặc chờ giữa các lần đọc, tùy client | Lỗi đọc/chờ response |
| **Overall request deadline** | Giới hạn tổng thời gian của toàn bộ thao tác introspection, tính cả nhiều pha | Hết ngân sách end-to-end, cần hủy hoặc trả lỗi |

Ngoài ra có **DNS lookup time**, TLS handshake time, proxy negotiation và thời gian chờ ở queue của ứng dụng. **Không phải mọi thư viện gộp tất cả vào connect/read timeout**, nên phải đọc semantics của phiên bản HTTP client.

### 3.1. Connection acquisition timeout

Nếu ứng dụng có pool tối đa 30 connection tới AS và 30 request đã chiếm chúng, request thứ 31 có thể chờ trong hàng đợi của pool.

Nếu không giới hạn thời gian chờ lấy connection, thread request có thể chờ lâu ngay cả khi AS không có lỗi; khi tải tăng, hàng đợi phình ra gây **pool exhaustion và thread starvation**.

Một chính sách ví dụ:

```text
Connection request (pool lease): <= 150 ms
```

Ngưỡng này không đo tốc độ mở TCP connection; nó chỉ giới hạn thời gian chờ **một connection có thể sử dụng**.

### 3.2. Connect timeout

Connect timeout giới hạn thời gian client chờ thiết lập kết nối tới host/port. Nó đặc biệt hữu ích khi:

- IP không thể truy cập.
- Firewall drop packet thay vì từ chối ngay.
- Một endpoint trong nhiều IP bị treo.
- Network egress từ pod/container gặp sự cố.

Cấu hình ví dụ:

```text
Connect timeout: 300 ms
```

Điểm cần nhớ: DNS lookup và TLS handshake **có thể không được giới hạn hoàn toàn bằng connect timeout** trong một số client. Cần xem cơ chế deadline hoặc timeout riêng nếu cần cam kết latency end-to-end.

### 3.3. Response/read timeout

Một kết nối TCP/TLS đã được thiết lập không bảo đảm AS phản hồi nhanh. API cần giới hạn thời gian chờ response:

```text
Response/read timeout: 800 ms
```

Một số API gọi đây là **socket read timeout**: thời gian không có byte dữ liệu trước khi báo lỗi, thay vì tổng thời gian cho toàn request. Nếu server gửi dữ liệu rất chậm từng chút một, read timeout đơn thuần có thể không kiểm soát tổng thời lượng. Do vậy hệ thống có SLA chặt chẽ nên cân nhắc **overall deadline**.

### 3.4. Overall request deadline và tác động tới SLA

Tổng thời gian có thể gồm:

```text
T_total =
  T_queue_in_app
+ T_lease_from_pool
+ T_DNS
+ T_TCP_connect
+ T_TLS_handshake
+ T_send_request
+ T_wait_response
+ T_receive_response
+ T_parse_and_validate
+ T_retry_backoff_and_subsequent_attempts
```

Không nhất thiết mọi thành phần xuất hiện trên mỗi request: connection tái sử dụng thường không phải handshake TLS mới, còn DNS có thể đã cache. Nhưng một “timeout 1 giây” cho read **không đồng nghĩa** request chắc chắn kết thúc dưới 1 giây.

Một ngân sách minh họa:

| Pha | Giới hạn ví dụ |
|---|---:|
| Chờ pool | 150 ms |
| TCP connect | 300 ms |
| Chờ response | 800 ms |
| Tổng mục tiêu cho introspection | 1.200 ms |

Các con số trên **không có phép cộng tuyệt đối**, vì một số pha không đồng thời xuất hiện và DNS/TLS có semantics riêng. Nếu thiết lập deadline tổng 1.200 ms, HTTP client hoặc lớp orchestration phải thực sự thực thi deadline đó; **đừng chỉ ghi số 1.200 trong tài liệu rồi coi là đã được bảo đảm**.

## 4. Chọn timeout theo hệ thống, không sao chép thông số máy khác

Một cách suy nghĩ hợp lý:

1. Xác định **latency budget của Orders API**, ví dụ p95 dưới một mức đã thống nhất.
2. Tách phần thời gian dành cho **introspection** khỏi thời gian xử lý DB/business logic.
3. Đo latency bình thường của AS và network theo từng môi trường.
4. Chọn connect/pool/read timeout để phát hiện lỗi nhanh mà không loại bỏ lượng request hợp lệ đáng kể.
5. Đặt trần số request đồng thời và retry để tránh nghẽn toàn API.
6. Kiểm tra hành vi khi AS chậm, mất kết nối, TLS handshake lỗi, pool đầy.
7. Đo lại khi lưu lượng hoặc topology thay đổi.

Ví dụ một API có mục tiêu đáp ứng 1.500 ms:

```text
Inbound HTTP budget:            1.500 ms
    Introspection budget:         700 ms
    Business/DB budget:           550 ms
    Network/serialize/reserve:    250 ms
```

Đây là **phân bổ ngân sách minh họa**, không phải API nào cũng dùng con số đó. Nếu AS có p99 cao hơn 700 ms trong điều kiện bình thường, phải tối ưu AS/network hoặc điều chỉnh hợp đồng SLA; không thể âm thầm tăng timeout vô hạn.

### 4.1. Short timeout có thể gây sự cố không kém long timeout

Timeout quá ngắn dẫn đến false negatives khi AS chịu tải hợp lệ, làm tăng 401/5xx và retry. Timeout quá dài giữ thread/socket quá lâu, dễ làm quá tải toàn hệ thống.

Lựa chọn timeout phải dựa trên **latency distribution, capacity, concurrency và error budget**, chứ không phải một giá trị “mọi người hay dùng”.

## 5. Cấu hình Spring Boot mặc định với opaque token

Một cấu hình đơn giản:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.com/oauth2/introspect
          client-id: ${ORDERS_INTROSPECTION_CLIENT_ID}
          client-secret: ${ORDERS_INTROSPECTION_CLIENT_SECRET}
```

Security chain ở Servlet stack:

```java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrdersSecurity {

    @Bean
    SecurityFilterChain ordersChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(Customizer.withDefaults())
            )
            .build();
    }
}
```

Ở đây Spring Security sử dụng `OpaqueTokenIntrospector` và opaque token provider; nó **không** dùng `JwtDecoder` cho access token introspection. Bearer token được gửi qua HTTP bởi caller, còn Resource Server cần có outbound client để gọi AS.

### 5.1. Vì sao cần custom OpaqueTokenIntrospector?

Mặc định thư viện có thể chọn HTTP client và các giá trị timeout chung. Khi có yêu cầu cụ thể về:

- Connect/read timeout và pool lease timeout.
- Connection pooling, TLS, proxy, mTLS.
- Observability, tracing và request deadline.
- Bảo vệ credentials, giới hạn redirects.
- Decorator policy, cache hoặc circuit breaker.

thì ứng dụng có thể **tự cung cấp bean `OpaqueTokenIntrospector`** để cài đặt đường truyền phù hợp.

**Điểm đáng chú ý:** khi có custom bean, cấu hình tự động của Spring Boot có thể lùi lại để sử dụng bean đó. Vì vậy bạn phải bảo đảm implementation mới vẫn thực hiện **HTTP client authentication, kiểm tra active và xử lý token không hợp lệ**; đừng vô tình bỏ toàn bộ validation.

## 6. Một cấu hình timeout đơn giản với RestTemplate

Spring MVC/Servlet thường dùng các API blocking như `RestOperations` và `RestTemplate`. Một mẫu dễ hiểu cho ứng dụng tải vừa là sử dụng `SimpleClientHttpRequestFactory`.

```java
package com.example.orders.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.security.oauth2.server.resource.introspection.NimbusOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.web.client.RestTemplate;
import org.springframework.http.client.support.BasicAuthenticationInterceptor;

@Configuration
public class SimpleIntrospectionHttpConfiguration {

    @Bean
    OpaqueTokenIntrospector opaqueTokenIntrospector(
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.introspection-uri}")
            String introspectionUri,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-id}")
            String clientId,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-secret}")
            String clientSecret) {

        SimpleClientHttpRequestFactory requestFactory =
            new SimpleClientHttpRequestFactory();

        // Milliseconds: các ngưỡng ví dụ, cần điều chỉnh theo SLA.
        requestFactory.setConnectTimeout(300);
        requestFactory.setReadTimeout(800);

        RestTemplate restTemplate = new RestTemplate(requestFactory);

        // Đưa Basic auth của introspection client vào outbound request.
        restTemplate.getInterceptors().add(
            new BasicAuthenticationInterceptor(clientId, clientSecret)
        );

        // Constructor nhận RestOperations có trên các bản Spring Security
        // hỗ trợ NimbusOpaqueTokenIntrospector theo hướng tùy chỉnh HTTP.
        return new NimbusOpaqueTokenIntrospector(
            introspectionUri,
            restTemplate
        );
    }
}
```

**Lưu ý về phiên bản:** tên implementation và constructor/builder cho custom HTTP transport có thể khác giữa các nhánh Spring Security (các bản mới có thể cung cấp `SpringOpaqueTokenIntrospector`). Khi áp dụng, đối chiếu Javadoc của **đúng phiên bản thư viện đang dùng** và giữ nguyên ý tưởng: introspector chuẩn + `RestOperations` được cấu hình HTTP client authentication và timeout. Đừng thay bằng một callback tự tuyên bố mọi token active.

### 6.1. Cách cấu hình này giải quyết gì?

- `setConnectTimeout(300)` giới hạn connect theo semantics của factory.
- `setReadTimeout(800)` giới hạn thời gian chờ đọc.
- `BasicAuthenticationInterceptor` xác thực Resource Server với introspection endpoint.
- `NimbusOpaqueTokenIntrospector` xử lý lời gọi introspection và phản hồi theo implementation.
- `SecurityFilterChain` dùng authorities sau khi token được introspect thành công.

### 6.2. Giới hạn của SimpleClientHttpRequestFactory

`SimpleClientHttpRequestFactory` sử dụng cơ chế HTTP client JDK truyền thống; nó **không cung cấp toàn bộ khả năng pool acquisition/concurrency/eviction** như một HTTP client pooling chuyên dụng. Tùy nền tảng JDK, kết nối HTTP có thể được giữ lại ở tầng dưới nhưng ứng dụng không có một **pool được cấu hình minh bạch theo max-per-route, max-total và lease timeout** như ví dụ Apache HttpClient bên dưới.

Với AS có lưu lượng lớn và yêu cầu giám sát pool rõ ràng, nên dùng một HTTP transport hỗ trợ pooling, lifecycle và metrics có chủ đích.

### 6.3. Tránh basic auth và token bị log

Interceptor Basic được xây trong server-side application, không dùng credential client từ incoming request. Không thêm một interceptor HTTP logging in toàn bộ:

```text
Authorization: Basic ...
body: token=...
```

Dù dùng môi trường dev, raw bearer token và introspection secret vẫn là credential. Nếu cần debug, ghi latency, status code, mã lỗi, request ID và endpoint hostname đã cho phép.

## 7. Connection pooling: vì sao quan trọng?

Mỗi outbound HTTPS connection mới có thể cần TCP handshake, TLS handshake, socket/file descriptor và tài nguyên kernel. Nếu mỗi introspection request đều mở kết nối mới không tái sử dụng, API chịu thêm latency và áp lực:

- Socket/file descriptors.
- Ephemeral ports và trạng thái `TIME_WAIT`.
- CPU/TLS handshake ở cả API và AS.
- DNS/proxy/TLS setup.
- Network load và firewall connection tracking.

**Connection pooling** cho phép nhiều request tuần tự hoặc đồng thời **tái sử dụng các connection HTTP/TLS còn hợp lệ** theo giới hạn đã cấu hình.

Một pool không có nghĩa token được cache. Token có thể vẫn được introspect trên mỗi request trong khi socket được tái sử dụng.

### 7.1. Khái niệm total connections và per-route connections

| Thông số | Ý nghĩa |
|---|---|
| **Max total** | Tổng connection tối đa mà một pool giữ trên nhiều route/host |
| **Max per route** | Connection tối đa cho một route như `https://login.example.com:443` |
| **Connection request timeout** | Chờ pool cấp một connection tối đa bao lâu |
| **Connection max lifetime/TTL** | Tuổi connection được tái sử dụng tối đa nếu client hỗ trợ |
| **Idle eviction** | Dọn những connection không sử dụng trong khoảng thời gian |
| **Expired eviction** | Dọn những connection quá tuổi/không còn hợp lệ |
| **Keep-alive** | Khoảng thời gian kết nối có thể được giữ theo chính sách server/client |
| **Connection validate-after-inactivity** | Kiểm tra connection đã idle trước khi tái sử dụng nếu client hỗ trợ |

Pool phải được **giới hạn**; pool quá nhỏ gây queue và timeout, còn pool rất lớn có thể gây quá tải AS và chiếm tài nguyên trên từng instance.

### 7.2. Không nhầm pool size với số thread

Ví dụ Tomcat có thể có 200 request threads nhưng pool introspection chỉ có 20 connection tới AS. Nếu 100 requests đang cần introspection, 20 requests có thể được gửi ngay, số còn lại chờ pool hoặc hết lease timeout.

Tăng Tomcat threads từ 200 lên 500 **không giải quyết** một bottleneck pool 20 connection; nó có thể chỉ khiến nhiều thread bị treo chờ hơn.

Ngược lại, tăng pool lên 500 mà Authorization Server chỉ xử lý tốt 50 concurrent introspection có thể làm AS quá tải. Cần sizing dựa trên **capacity toàn hệ thống**, không chỉ phía client.

## 8. Ước lượng concurrency bằng tốc độ và độ trễ

Có thể dùng trực giác từ **Little's Law** trong trạng thái ổn định:

\[
\text{Concurrency} \approx \text{Requests per second} \times \text{Average service time (seconds)}
\]

Giả sử một instance Orders API có:

```text
500 introspection calls / second
Average time một outbound request = 0.08 seconds
Estimated average in-flight = 500 × 0.08 = 40
```

Ở thời điểm tải tăng:

```text
500 introspection calls / second
Average duration tăng thành 0.30 seconds
Estimated in-flight = 500 × 0.30 = 150
```

Nếu pool chỉ có 40 connection, request xếp hàng khi latency tăng; hàng đợi có thể làm tổng thời gian vượt SLA.

**Đây là ước lượng trung bình, không phải công thức chọn pool size cuối cùng.** Cần xét burstiness, p95/p99, connection reuse, throttling, headroom và số instance.

### 8.1. Sizing phải tính tổng các replicas

Nếu có 12 pods, mỗi pod pool 100 connection cho một route, AS có thể nhìn thấy **tối đa khoảng 1.200 connection** từ hệ thống này khi tất cả pods sử dụng hết pool. Nếu AS chỉ dự kiến vài trăm connections, việc tăng pool cục bộ có thể tạo sự cố toàn cụm.

Một cách thiết kế:

1. Biết AS tối đa xử lý bao nhiêu RPS/concurrent requests.
2. Chia quota hợp lý cho tất cả Resource Servers cùng sử dụng AS.
3. Xác định pool và concurrency limit **theo mỗi pod**.
4. Kiểm tra autoscaling tăng pod có làm tăng tổng connection không.
5. Quan sát active/idle/pending pool connections, timeout và AS saturation.
6. Dùng admission control/bulkhead để dừng quá tải trước khi thread pool bị chiếm hết.

## 9. Pooling HTTP client bằng Apache HttpClient 5

Trong Servlet stack, một lựa chọn là **Apache HttpClient 5** phối hợp với `HttpComponentsClientHttpRequestFactory` của Spring. Ví dụ này thể hiện:

- Giới hạn số connection.
- Timeout khi chờ pool.
- Connect/socket/response timeouts.
- Tái sử dụng và dọn connection idle.
- Đóng client khi Spring container dừng.

Thêm dependency phù hợp với Spring Boot BOM:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    implementation 'org.apache.httpcomponents.client5:httpclient5'
}
```

### 9.1. Định nghĩa CloseableHttpClient do Spring quản lý

```java
package com.example.orders.security;

import org.apache.hc.client5.http.classic.HttpClient;
import org.apache.hc.client5.http.config.ConnectionConfig;
import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManagerBuilder;
import org.apache.hc.core5.util.TimeValue;
import org.apache.hc.core5.util.Timeout;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class IntrospectionHttpClientConfiguration {

    @Bean(destroyMethod = "close")
    CloseableHttpClient introspectionHttpClient() {
        var connectionManager =
            PoolingHttpClientConnectionManagerBuilder.create()
                .setMaxConnTotal(120)
                .setMaxConnPerRoute(80)
                .setDefaultConnectionConfig(
                    ConnectionConfig.custom()
                        .setConnectTimeout(
                            Timeout.ofMilliseconds(350)
                        )
                        .setSocketTimeout(
                            Timeout.ofMilliseconds(900)
                        )
                        .build()
                )
                .build();

        RequestConfig requestConfig = RequestConfig.custom()
            .setConnectionRequestTimeout(
                Timeout.ofMilliseconds(150)
            )
            .setResponseTimeout(
                Timeout.ofMilliseconds(900)
            )
            .build();

        return HttpClients.custom()
            .setConnectionManager(connectionManager)
            .setDefaultRequestConfig(requestConfig)
            .disableRedirectHandling()
            .evictExpiredConnections()
            .evictIdleConnections(TimeValue.ofSeconds(30))
            .build();
    }
}
```

**Giải thích:**

- `setMaxConnTotal(120)` giới hạn connection toàn client.
- `setMaxConnPerRoute(80)` giới hạn trên một route; nếu chỉ có một AS host, đây thường là giới hạn hiệu dụng.
- `ConnectionConfig` cấu hình connect/socket timeout ở lớp connection của HttpClient 5.
- `RequestConfig` cấu hình pool acquisition và response timeout.
- `disableRedirectHandling()` tránh tự gửi dữ liệu introspection tới endpoint khác khi có redirect ngoài mong đợi.
- `evictExpiredConnections()` / `evictIdleConnections(...)` hỗ trợ dọn connection không dùng.
- `@Bean(destroyMethod = "close")` giúp Spring gọi `close()` cho HTTP client có tài nguyên pool/thread khi application context dừng.

**Tương thích phiên bản:** tên/lớp API Apache HttpClient 5 có thể thay đổi chi tiết giữa các bản, và một số setter deprecated ở bản mới. Hãy đối chiếu version do Spring Boot BOM quản lý khi tích hợp. Đặc biệt không nên sao chép cấu hình cũ của Apache HttpClient **4.x** sang **5.x** vì package và semantics khác nhau.

### 9.2. Tạo RestOperations dùng client pooling

```java
package com.example.orders.security;

import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.HttpComponentsClientHttpRequestFactory;
import org.springframework.http.client.support.BasicAuthenticationInterceptor;
import org.springframework.web.client.RestOperations;
import org.springframework.web.client.RestTemplate;

@Configuration
public class IntrospectionRestOperationsConfiguration {

    @Bean
    RestOperations introspectionRestOperations(
            CloseableHttpClient introspectionHttpClient,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-id}")
            String clientId,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-secret}")
            String clientSecret) {

        var requestFactory = new HttpComponentsClientHttpRequestFactory(
            introspectionHttpClient
        );

        RestTemplate template = new RestTemplate(requestFactory);

        template.getInterceptors().add(
            new BasicAuthenticationInterceptor(clientId, clientSecret)
        );

        return template;
    }
}
```

Ở đây `RestTemplate` **tái sử dụng** HTTP client được container quản lý. Không tạo `CloseableHttpClient` mới bên trong mỗi `introspect()` hoặc mỗi HTTP request của user.

### 9.3. Gắn RestOperations vào OpaqueTokenIntrospector

```java
package com.example.orders.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.introspection.NimbusOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.web.client.RestOperations;

@Configuration
public class IntrospectionConfiguration {

    @Bean
    OpaqueTokenIntrospector opaqueTokenIntrospector(
            RestOperations introspectionRestOperations,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.introspection-uri}")
            String introspectionUri) {

        return new NimbusOpaqueTokenIntrospector(
            introspectionUri,
            introspectionRestOperations
        );
    }
}
```

Mẫu trên dành cho phiên bản có constructor tương ứng. Nếu phiên bản Spring Security đang dùng giới thiệu implementation/builder mới (chẳng hạn `SpringOpaqueTokenIntrospector`), sử dụng **API tương đương** theo Javadoc để truyền HTTP client tùy chỉnh; **không** thay `OpaqueTokenIntrospector` bằng hàm “trả active=true” tự tạo.

### 9.4. Vòng đời bean: không đóng pool sau mỗi lần gọi

**Đúng:**

```text
Spring application context
  ├── One CloseableHttpClient (connection pool)
  ├── One RestOperations for introspection
  └── One OpaqueTokenIntrospector
       └── Many HTTP requests reuse the same client
```

**Sai:**

```java
// Minh họa anti-pattern: tạo client mới cho từng token.
public OAuth2AuthenticatedPrincipal introspect(String token) {
    CloseableHttpClient client = HttpClients.createDefault();
    // Có nguy cơ lãng phí connection, TLS handshake và rò tài nguyên
    // nếu không đóng client/response trên từng đường lỗi.
    throw new UnsupportedOperationException("Example of bad design");
}
```

Thực tế với pooling cần **một client dùng chung và được đóng có kiểm soát**, không đóng HTTP pool sau mỗi token. Các HTTP response/body phải được tiêu thụ/đóng bởi transport/introspector đúng cách để connection được trả về pool. Nếu tự cài low-level client, việc không đóng response có thể làm connection **không được trả về pool**, khiến pool cạn theo thời gian.

## 10. Những tài nguyên nào cần quản lý?

| Tài nguyên | Rủi ro nếu không quản lý | Chiến lược |
|---|---|---|
| TCP sockets/file descriptors | Hết file descriptors, lỗi mở connection | Pool giới hạn, close lifecycle, metrics |
| HTTP connection pool | Queue vô hạn, pool exhaustion | Max per route/total, lease timeout, pending limit |
| Request threads (Servlet) | Thread starvation khi chờ AS | Timeouts, bulkhead, giới hạn concurrency |
| TLS sessions/handshakes | CPU và latency tăng | Reuse connection, tối ưu TLS đúng cách |
| DNS cache/connections cũ | Tiếp tục gọi IP/host cũ sau failover | Connection lifetime/eviction/DNS policy |
| Memory cho request/response | Tăng heap khi payload lớn, response malformed | Giới hạn body size, HTTP client policies |
| Scheduled eviction threads | Resource leak khi app shutdown | Quản lý trong bean lifecycle, đóng client |
| Secret trong headers/interceptors | Rò credential qua logs/traces | Redaction, không log raw header/body |
| Metrics tags | Cardinality lớn nếu tag token/client động | Chỉ dùng status, host/route được phép, error class |
| Cache nếu có | Token revoke vẫn được chấp nhận, rò dữ liệu | TTL ngắn theo risk, protected cache keys |

### 10.1. Tài nguyên của pool có vòng đời dài

Connection pool thường tồn tại suốt vòng đời instance. Nó không gắn một-một với từng user request. Do đó:

- Tạo pool lúc application startup hoặc bean initialization, không tạo theo request.
- Đóng khi ứng dụng shutdown và đợi các request in-flight dừng theo chiến lược graceful shutdown.
- Không trộn chung một HTTP client chứa interceptor Basic credential introspection với các HTTP calls tới host không liên quan.
- Dùng HTTP client **riêng cho introspection** nếu muốn tránh chia sẻ credential, pool và timeout với API outbound khác.
- Trong test, đóng client và fake server sau mỗi test context/test suite phù hợp.

### 10.2. HTTP redirect có thể làm lộ token

Nếu introspection endpoint trả:

```http
HTTP/1.1 302 Found
Location: https://unexpected.example.net/collect
```

và HTTP client tự động follow redirect bằng request chứa token/Authorization header, có nguy cơ gửi credential tới host không mong đợi; hành vi follow redirect chi tiết phụ thuộc implementation và status code.

**Cách tiếp cận an toàn:** URI phải là URL được cấu hình/allowlist; xử lý redirect có chủ đích, và với introspection nên **tránh follow redirect tự động** nếu chưa kiểm soát đường đi và credential. Không lấy introspection URL từ HTTP header hoặc JWT chưa xác minh.

### 10.3. Proxy và TLS interception

Nếu outbound HTTPS đi qua enterprise proxy:

- Proxy phải được cấu hình rõ trong HTTP client/egress policy.
- Nếu proxy có TLS interception, cần xác định CA được tổ chức phê duyệt và chính sách kiểm soát nội dung.
- Không import CA lạ chỉ để hết `PKIX path building failed`.
- Không đưa client-secret vào proxy URL hoặc log.
- Cần kiểm tra hostname/SNI và truststore **trong container/JVM thực tế**, không chỉ trên laptop.

## 11. TLS, truststore và mutual TLS

Introspection request mang credential nhạy cảm; HTTPS cần bảo vệ kênh:

```text
Orders API (HTTP client)
   |
   | HTTPS + certificate validation
   v
login.example.com (introspection endpoint)
```

Cần xác minh:

1. Endpoint dùng `https` trong môi trường thật.
2. Certificate SAN khớp hostname mà HTTP client kết nối.
3. Certificate chain hợp lệ theo JVM truststore hoặc TLS configuration.
4. Certificate chưa hết hạn, đồng hồ container chính xác.
5. Không dùng TrustManager chấp nhận mọi chứng chỉ.
6. Secret chỉ được gửi tới đúng endpoint đáng tin.

### 11.1. Truststore của JVM không phải khóa ký JWT

Với introspection, HTTPS certificate phục vụ **xác thực endpoint và bảo vệ kết nối**. Nó không phải RSA/ECDSA public key dùng xác minh JWT từ JWKS.

Opaque Resource Server có thể không tải JWKS, nhưng vẫn cần truststore/CA chuẩn cho kết nối introspection.

### 11.2. Private CA và staging

Staging có thể dùng private CA. Một nguyên tắc:

```text
JVM truststore riêng cho staging
  └── Chỉ thêm CA được tổ chức phê duyệt

Introspection URL:
  https://login.staging.example.com/oauth2/introspect
Certificate SAN:
  login.staging.example.com
```

Không dùng `--insecure` hoặc `trustAll` trong production. Không copy nguyên credential production sang staging, vì ranh giới môi trường khác nhau.

### 11.3. mTLS hoặc private_key_jwt

Không phải AS nào cũng chấp nhận HTTP Basic client ID/secret; một số endpoint có thể yêu cầu:

- **mTLS client certificate**.
- `private_key_jwt` client authentication.
- Cơ chế authentication riêng có hợp đồng rõ.

Khi dùng mTLS, HTTP client phải tải certificate/private key của **Resource Server client** trong keystore, cấu hình TLS context và rotation tương ứng. Chứng chỉ client mTLS **không phải bearer token**. Không tự nghĩ rằng việc đã kết nối HTTPS có nghĩa hai chiều đã xác thực mTLS.

Nếu AS dùng `private_key_jwt`, request introspection cần thêm client assertion theo phương thức đăng ký. Một BasicAuthenticationInterceptor thông thường **không đủ**; phải sử dụng HTTP/client authentication module phù hợp.

## 12. Retry: không biến sự cố AS thành bão request

Khi AS lỗi tạm thời, retry nghe có vẻ hợp lý, nhưng một Resource Server có lưu lượng lớn có thể khiến sự cố trầm trọng hơn.

Ví dụ:

```text
1.000 API requests/s
× 1 introspection mỗi request
× 3 attempts khi AS lỗi
= có thể lên tới 3.000 HTTP attempts/s
```

Nếu nhiều replicas đồng thời retry, **retry storm** có thể làm AS mất khả năng hồi phục.

### 12.1. Nguyên tắc retry cho introspection

- Chỉ retry các lỗi **được phân loại là tạm thời**, nếu hợp đồng cho phép.
- Không retry `active=false`: đó là kết quả hợp lệ của introspection.
- Không retry vô hạn HTTP `401` vì client secret sai.
- Với `429`, xem rate limit/`Retry-After` nếu áp dụng, nhưng không giữ request thread chờ quá deadline.
- Với timeout hoặc `5xx`, cân nhắc số lần thử ít, backoff và jitter.
- Mọi lần thử phải nằm trong **overall request budget**.
- Không thay URI sang AS ngoài allowlist để “tìm endpoint nào còn sống”.
- Không log token/secret mỗi lần retry.

### 12.2. Mẫu quyết định retry

| Kết quả | Nên retry? | Ghi chú |
|---|---|---|
| `200 active=true` | Không | Tiếp tục xác minh claims/policy |
| `200 active=false` | **Không** | Token bị từ chối |
| `400` request malformed | Thông thường không | Sửa cấu hình/request format |
| `401/403` của introspection client | Thông thường không | Điều tra client authentication/permission |
| `429` | Có điều kiện | Theo quota và deadline; tránh thundering herd |
| `502/503/504` | Có điều kiện | Chỉ khi còn budget và AS có cơ hội hồi phục |
| Connect/read timeout | Có điều kiện | Số retry giới hạn, quan sát latency/AS load |
| TLS certificate invalid | **Không** | Sửa truststore/certificate; không bypass TLS |

### 12.3. Dùng circuit breaker nhưng phải fail closed

Circuit breaker có thể tạm ngừng outbound calls khi AS lỗi liên tục để bảo vệ servlet threads và giảm tải.

```text
Circuit CLOSED → cho phép gọi introspection
Circuit OPEN   → không gọi AS, báo lỗi dependency
Circuit HALF_OPEN → thăm dò bằng lượng request giới hạn
```

**Tuyệt đối không** viết “breaker OPEN thì coi `active=true`” hay “AS mất kết nối thì cho mọi token qua tạm”. Nếu không thể lấy bằng chứng xác thực đáng tin, không được cho phép hành động bảo vệ.

### 12.4. Phân biệt retry với backpressure

- **Retry** phát sinh thêm request cho cùng một token.
- **Backpressure/admission control** hạn chế số request mới được phép chiếm tài nguyên introspection.
- **Bulkhead** giới hạn concurrency cho dependency AS, bảo vệ phần còn lại của ứng dụng.

Khi dependency bão hòa, thêm retry có thể gây hại; cần giới hạn tải và kiểm soát hàng đợi.

## 13. Cache introspection: hiệu năng đổi lấy độ trễ thu hồi

Cache có thể giảm số HTTP calls tới AS. Nhưng introspection giúp biết token bị thu hồi; cache quá lâu làm mất lợi ích cập nhật trạng thái.

Giả sử AS vừa revoke token tại 12:00 nhưng Orders API đã cache `active=true` tới 12:05. Trong 5 phút đó, cache có thể vẫn coi token active trừ khi có cơ chế invalidation.

### 13.1. Một số biến cần xác định

- TTL tối đa mà sản phẩm chấp nhận trạng thái revoke bị chậm.
- `exp` của access token còn bao lâu?
- AS có trả `exp` tin cậy không?
- Quyền/tenant/role có thể thay đổi trong thời gian cache không?
- Cache key có bảo vệ bí mật raw token không?
- Mỗi pod tự cache hay dùng cache phân tán? Có cần invalidate toàn cụm?
- Token không active có nên cache âm không, trong bao lâu?
- Chính sách xử lý lỗi cache/AS là gì?

Một bất đẳng thức có ích:

```text
effectiveCacheTTL <= min(
  configuredMaxTTL,
  remainingLifetimeUntilExp,
  acceptableRevocationDelay
)
```

Đây là **nguyên tắc thiết kế**, không phải thuật toán đầy đủ. Nếu response không có `exp` mà hợp đồng yêu cầu, nên fail closed hoặc dùng cơ chế đã phê duyệt, không giả định access token luôn còn hạn.

### 13.2. Cache key không được làm lộ bearer credential

Opaque token là bearer credential; người lấy được giá trị token có thể sử dụng lại khi token còn active. Tránh:

- Ghi raw token làm metric label.
- Đưa raw token vào cache admin UI hoặc logs.
- Truyền token tới hệ thống cache không được phê duyệt.
- Ghi token vào file/dump/debug endpoint.
- Cache principal/permissions nhạy cảm không có kiểm soát truy cập.

Có thể dùng khóa được dẫn xuất qua hash/HMAC có thiết kế phù hợp để giảm việc lộ token nguyên văn trong key, nhưng cần phân tích collision, key management và vận hành. Không coi hashing token trong cache như giải pháp đủ để bảo vệ toàn bộ hệ thống nếu giá trị raw token vẫn nằm trong cache value/log.

### 13.3. Cache không thay HTTP connection pooling

**Connection pooling:** tái sử dụng kết nối TLS/HTTP, **vẫn gọi AS để introspect** mỗi request khi không cache.

**Introspection caching:** tái sử dụng kết quả `active`/principal/authorities, **có thể không gọi AS** trong TTL.

Hai tối ưu này độc lập và có rủi ro khác nhau. Pooling giảm chi phí kết nối mà không làm kết quả introspection bị stale; caching giảm lưu lượng nhưng ảnh hưởng khả năng phản ánh revocation.

## 14. Chống DoS khi mọi token đều kéo theo HTTP request

Một API cho phép bất kỳ caller nào gửi bearer token. Nếu mỗi token bất kỳ đều dẫn tới AS, kẻ tấn công có thể gửi rất nhiều token vô nghĩa để tiêu tốn:

- Servlet threads.
- Pool connections.
- CPU TLS handshake.
- Network bandwidth.
- Năng lực xử lý introspection của AS.
- Log/metric capacity.

Do đó cần thiết kế **giới hạn ở trước hoặc cùng tầng xác thực** mà không bỏ các điều kiện bảo mật.

### 14.1. Một số biện pháp

1. Giới hạn inbound request rate theo nguồn/tầng mạng phù hợp.
2. Đặt giới hạn độ dài `Authorization` header và token theo chính sách API.
3. Từ chối Bearer token sai cú pháp trước khi gửi introspection.
4. Giới hạn concurrent introspection calls cho từng instance.
5. Sizing pool và lease timeout theo AS capacity.
6. Cân nhắc cache kết quả inactive trong thời gian ngắn nếu có hợp đồng và không gây rủi ro tài nguyên.
7. Giám sát tỷ lệ invalid tokens, requests by source và pool pending.
8. Không cho client lựa chọn introspection URI, tránh SSRF và token exfiltration.
9. Không tiết lộ khác biệt quá chi tiết về token không tồn tại trong response để tránh enumeration.

**Không nên tự chấp nhận token với cú pháp “trông giống token thật”**. Các giới hạn trước introspection chỉ ngăn abuse; xác thực vẫn cần dựa trên AS và policy.

### 14.2. Không để một người dùng xấu chiếm toàn pool

Nếu một nhóm requests sai token có thể sử dụng toàn bộ pool, request của người dùng hợp lệ cũng bị ảnh hưởng. Có thể cần:

- Rate limiting tại edge/gateway.
- Per-caller quotas khi có căn cứ.
- Bulkhead và bounded queue riêng cho introspection.
- Connection pool đủ dùng nhưng không vượt sức AS.
- Giám sát `pool.pending`, `connection_request_timeout`, `introspection.error_rate`.

Một pool lớn không thể thay một cơ chế rate-limit tốt.

## 15. Trả lỗi đúng: inactive token khác dependency outage

Một số tình huống và hành vi mong đợi:

| Điều kiện | Authentication result | Phản hồi inbound thường gặp |
|---|---|---|
| Không có bearer token ở endpoint cần xác thực | Chưa xác thực | `401 Unauthorized` |
| Introspection trả `active=false` | Token bị từ chối | `401 invalid_token` |
| Token active nhưng thiếu `orders.write` | Đã xác thực, thiếu quyền | `403 Forbidden` |
| Token active, đủ scope nhưng không sở hữu order | Business authorization từ chối | `403` hoặc `404` theo chính sách |
| AS từ chối client secret | Không thể xác thực token do lỗi RS → AS | Fail closed, phân loại lỗi cấu hình |
| Pool lease timeout | Không nhận được kết quả introspection | Fail closed, phân loại quá tải client |
| AS read timeout hoặc TLS failure | Không có kết quả đáng tin | Fail closed, báo dependency failure theo error mapping |
| Response JSON malformed | Không xác minh được token | Từ chối, điều tra AS/proxy/client |
| Circuit breaker OPEN | Chưa introspect | Không chấp nhận token mặc định |

Spring Security và HTTP error handlers có thể map các exception cụ thể ra 401, 5xx hoặc status khác tùy implementation và customization. **Không khẳng định framework luôn tự trả 503 khi AS outage.** Nếu cần phân biệt lỗi hạ tầng (503) với token inactive (401), phải cấu hình exception translation và test thực tế.

### 15.1. “Fail closed” không đồng nghĩa che mọi lỗi thành 401

Fail closed nghĩa là **không cho phép truy cập khi không đủ bằng chứng xác thực/ủy quyền**. Về vận hành, client secret sai hay AS outage là lỗi dịch vụ, có thể phù hợp để trả `503 Service Unavailable` cho caller thay vì 401 khiến họ tưởng token cá nhân sai.

Tuy nhiên việc phân biệt 401/503 phải dựa trên exception/hệ thống đang dùng và không tiết lộ bí mật hoặc chi tiết nội bộ. Không map mọi `RestClientException` thành `401 invalid_token` mà không cân nhắc phân biệt nguyên nhân.

### 15.2. Deadline và hủy request

Khi vượt deadline, HTTP client cần hủy hoặc đóng đúng request đang chờ, giải phóng connection/response/threads theo cơ chế implementation. Chỉ timeout một `Future.get(...)` ở lớp bên ngoài **không bảo đảm** HTTP request bên dưới tự dừng.

Vì vậy thiết lập timeout **ngay trên HTTP client** và nếu dùng deadline ở orchestration, cần cơ chế cancellation/cleanup tương thích.

## 16. Observability: đo trạng thái client, không ghi token

Các metrics có ích:

| Metric/Signal | Mục đích |
|---|---|
| `introspection.requests.total` | Tổng lượt gọi endpoint introspection |
| `introspection.duration` histogram/p95/p99 | Đo latency |
| `introspection.result.active/inactive` | Phân biệt token active và inactive ở mức thống kê |
| `introspection.http.status` | Phân loại lỗi HTTP từ AS |
| `introspection.error.type` | DNS, TLS, connect timeout, read timeout, parse, client auth |
| `http.pool.leased` | Số connection đang được dùng |
| `http.pool.available` | Số connection rỗi |
| `http.pool.pending` | Request đang chờ pool |
| `http.pool.timeout.total` | Đo pool lease exhaustion |
| `introspection.circuit.state` | CLOSED/OPEN/HALF_OPEN |
| `introspection.cache.hit_ratio` | Chỉ khi có cache và biết TTL/risk |
| `jvm.threads.busy` / servlet active threads | Phát hiện thread starvation |
| `AS rate_limit/429` | Cảnh báo capacity hoặc retry storm |

Tên metric trong bảng chỉ là **gợi ý đặt tên**, không phải tất cả tự có sẵn từ Spring Security. Có thể tích hợp Micrometer/Actuator, metrics của Apache HttpClient hoặc instrument wrapper introspector phù hợp.

### 16.1. Tag nào an toàn?

Có thể dùng tag low-cardinality như:

- `outcome=active|inactive|error`.
- `error_type=timeout|tls|client_auth|invalid_response`.
- `environment=staging|prod`.
- `as_host=login.example.com` khi host đã nằm trong allowlist.
- `method=POST`, `client_type=introspection`.

**Không dùng raw bearer token, `sub`, `client-secret`, request ID từng request hay token hash có số lượng rất lớn làm metric tag.** Chúng vừa gây rò thông tin vừa làm cardinality phình to.

### 16.2. Log nên ghi gì?

Ví dụ:

```text
WARN introspection_failed
  requestId=...
  dependency=authorization-server
  phase=pool_acquisition
  error=timeout
  elapsedMs=151
```

Không ghi:

```text
token=<raw opaque access token>
Authorization=Basic <base64 client secret>
introspection_response=<all claims and PII>
```

Nếu cần tracing phân tán, tạo span cho outbound introspection với status/latency và attributes an toàn. Không đưa token hoặc credential vào span attributes, baggage hay headers mà exporter có thể lưu.

## 17. Triển khai Kubernetes và nhiều instance

Giả sử Orders API có 8 pods, mỗi pod 250 request threads và pool introspection tối đa 80 connections tới AS:

```text
8 pods × 80 connections/pod = 640 possible connections
```

Đó là **trần lý thuyết theo cấu hình pool** với một route khi tải đủ lớn, không có nghĩa luôn có 640 connection mở. Nhưng AS phải được thiết kế chịu tổng tải từ mọi pod và các Resource Servers khác.

### 17.1. Readiness và graceful shutdown

Khi khởi động:

- App cần được cấu hình đủ URI, TLS trust, secret và network policy.
- Đừng tự đưa app vào ready nếu hệ thống xác thực token không thể thực hiện ở mức chính sách sẵn sàng yêu cầu.
- Nhưng **không ping introspection bằng token production thật** trong health check. Nếu cần synthetic check, dùng credential/test path được phê duyệt.
- Tránh để tất cả pods đồng loạt kết nối/khởi động lại làm AS chịu spike.

Khi shutdown:

1. Ngừng nhận request mới.
2. Cho requests đang chạy hoàn tất trong grace period nếu có thể.
3. Đóng `CloseableHttpClient` và pool theo bean lifecycle.
4. Không để background eviction threads hoặc sockets bị bỏ lại.

### 17.2. DNS rotation, stale connections và failover

Nếu AS đổi IP sau failover hoặc DNS rotation, các connection đang mở có thể vẫn nối tới node cũ. Dọn idle/expired connections và đặt connection lifetime hợp lý giúp các connection mới có cơ hội sử dụng DNS mới.

Không nên cấu hình connection sống vô hạn mà không có cơ chế phát hiện stale/closed connections. Đồng thời **DNS TTL** của JVM/HTTP client và hệ thống mạng có thể khác nhau: một HTTP pool timeout không tự làm DNS refresh.

### 17.3. Tách môi trường

| Môi trường | Endpoint ví dụ | Cấu hình HTTP client |
|---|---|---|
| Development | `https://login.dev.example.com/oauth2/introspect` | Timeout kiểm thử, dev CA được cấp riêng |
| Staging | `https://login.staging.example.com/oauth2/introspect` | Pool/limits đủ để thử tải, staged certificate/secret |
| Production | `https://login.example.com/oauth2/introspect` | Pool theo capacity AS, monitoring, alerting, secret rotation |

Không copy nguyên secret hoặc truststore production sang development. Mọi environment cần đúng client authentication, TLS hostname/CA và resource/audience policy.

## 18. Servlet blocking và WebFlux reactive không phải cùng mô hình

Trong **Servlet stack**, introspection thông thường có tính **blocking**: request thread chờ outbound HTTP response. Nếu AS chậm, nhiều Servlet threads bị chiếm. Connection pool và timeouts đặc biệt quan trọng.

Trong **WebFlux reactive stack**, Spring Security có loại **`ReactiveOpaqueTokenIntrospector`** và các implementation dùng HTTP client reactive phù hợp. Mô hình concurrency, connection pooling, timeout/cancellation và backpressure khác với Servlet/RestTemplate.

| Đặc tính | Servlet Resource Server | Reactive Resource Server |
|---|---|---|
| Security HTTP chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Introspector contract | `OpaqueTokenIntrospector` | `ReactiveOpaqueTokenIntrospector` |
| HTTP client điển hình | Blocking `RestOperations`/Apache classic | Nonblocking WebClient/reactive HTTP client |
| Nguy cơ chính khi AS chậm | Servlet thread starvation và pool queue | Event-loop blockage nếu dùng API blocking, in-flight/backpressure |
| Timeout/cancellation | Theo client blocking, thread và connection | Theo reactive operator/HTTP client và propagation |
| Kết quả authentication | `Authentication` trong Servlet context | `Authentication` trong reactive security context |

**Không gọi `RestTemplate.blocking` trực tiếp trên event-loop của WebFlux** và kỳ vọng hệ thống vẫn nonblocking. Nếu đang triển khai Reactive Resource Server, phải thiết kế HTTP transport và timeout bằng API reactive tương ứng, không bê nguyên code Servlet vào.

## 19. Kiểm thử timeout và quản lý connection

Một bài test chỉ dùng `opaqueToken()` trong MockMvc thường **không gọi endpoint introspection thật**, nên không kiểm tra HTTP client hoặc timeout. Cần các lớp test riêng.

### 19.1. Policy tests

Dùng `opaqueToken()` hoặc principal giả để kiểm tra:

- Scope mapping.
- Audience/resource policy nếu đã được thực thi ở layer phù hợp.
- Tenant/ownership.
- Response khi thiếu authority.
- Không cấp quyền khi principal chưa xác thực.

Đây là test authorization, không phải HTTP transport.

### 19.2. Integration tests với fake introspection server

Dùng HTTP test server được kiểm soát để tạo các kịch bản:

| Kịch bản | Fake AS behavior | Kỳ vọng |
|---|---|---|
| Active token | Trả `200 {"active":true,...}` | Authentication hợp lệ; service tiếp tục kiểm tra quyền |
| Inactive token | Trả `200 {"active":false}` | Token bị từ chối |
| Client secret sai | Trả `401` | Fail closed; phân loại client authentication error |
| Read timeout | Kết nối được nhưng delay body | HTTP client dừng theo timeout |
| Connect timeout | Đường mạng không kết nối được | Không giữ request vô hạn |
| Pool exhaustion | Nhiều requests chiếm pool | Lease timeout, không queue vô hạn |
| AS rate limit | Trả `429` | Không retry storm; fail closed |
| AS trả 503 | Lỗi dependency | Không accept token; health/metrics rõ |
| Malformed JSON | Body không đúng cấu trúc | Không biến thành principal hợp lệ |
| HTTPS invalid certificate | TLS handshake fail | Không bật trust-all |
| Redirect sang host lạ | `302 Location` khác host | Không rò token/secret |
| Connection đóng giữa response | Network error | Release resources, báo lỗi và tuân retry policy |
| Secret rotation | Một số pods vẫn dùng secret cũ | Phát hiện lỗi per instance, không cho qua |

Để test **pool** thực sự, cần đưa nhiều requests đồng thời qua HTTP client tích hợp, chứ không chỉ gọi `introspector.introspect(...)` tuần tự với fake AS phản hồi ngay.

### 19.3. Test giới hạn tài nguyên

Một kịch bản đơn giản:

```text
pool max per route = 2
request A: AS giữ connection trong 1 giây
request B: AS giữ connection trong 1 giây
request C: bắt đầu khi A/B còn bận
connectionRequestTimeout = 100 ms
Expected: C hết thời gian chờ pool, không treo mãi
```

Cần test với **đúng implementation HTTP client/pool** trong code. `SimpleClientHttpRequestFactory` không cung cấp pool lease semantics như Apache client.

Khi test connect timeout, cần cẩn thận: một IP không thể route có thể được OS trả lỗi ngay thay vì đợi timeout; dùng network fault injection hoặc test environment kiểm soát để xác nhận hành vi. Đừng dựa vào việc gọi một host công cộng “có vẻ chậm” làm test tất định.

### 19.4. Kiểm tra graceful shutdown và leak

Sau khi chạy tải thử:

- Pool leased connections trở về gần 0 khi requests kết thúc.
- Không có tăng số sockets/file descriptors không giới hạn.
- Không còn eviction threads của HTTP client cũ khi application context đã đóng.
- Connection/request timeout được phân loại đúng.
- Không có raw token/client secret trong logs hoặc traces.
- Khi rolling restart, các pod cũ đóng pool và requests in-flight được xử lý theo grace period.

**Đây là test về tài nguyên và vận hành**, khác với bài kiểm tra JWT/opaque token logic.

## 20. Các anti-pattern thường gặp

### 20.1. Tạo RestTemplate/HttpClient mới theo mỗi request

Sai:

```text
for each bearer token:
   new HTTP client
   new pool
   introspection
   abandon client/pool
```

Hậu quả: mất kết nối tái sử dụng, TLS handshake tăng, sockets/file descriptors và threads khó dọn. Thay bằng **client/pool được Spring quản lý theo lifecycle**, tái sử dụng ở các requests.

### 20.2. Dùng read timeout rất lớn để giảm lỗi

Nếu AS chậm, tăng timeout từ 1 giây lên 60 giây khiến request threads giữ lâu; pool và Tomcat có thể bị nghẽn. Cần dựa trên SLA, metrics và capacity, không dùng timeout vô hạn để che sự cố.

### 20.3. Chỉ cấu hình connect timeout

Connect nhanh không đồng nghĩa response nhanh. Cần giới hạn **response/read timeout và pool lease timeout** nếu transport có pooling. Nếu có mục tiêu tổng latency, cần kiểm soát deadline end-to-end.

### 20.4. Retry mọi lỗi

Retry `active=false`, HTTP 401 client secret sai hoặc TLS certificate invalid không làm token hợp lệ hơn; nó chỉ tăng tải. Phân loại lỗi và giới hạn số lần thử.

### 20.5. Circuit breaker OPEN thì cho qua

Điều này biến AS outage thành lỗ hổng xác thực. Khi thiếu bằng chứng introspection, **fail closed**; chỉ dùng cache nếu đã được thiết kế/phê duyệt với giới hạn stale rõ ràng.

### 20.6. In toàn bộ outbound request để debug

Bearer token và Basic secret có thể xuất hiện trong logs, APM, proxy hoặc tracing. Log status/latency/error class, không log credential/response claims nhạy cảm.

### 20.7. Một pool dùng chung cho mọi outbound service

Nếu RestTemplate chung có BasicAuthenticationInterceptor, credential introspection có thể được gửi tới host không liên quan. Cũng có nguy cơ một downstream service chậm chiếm connection pool và làm introspection không được cấp connection. Nên **tách transport/credentials/limits theo dependency**.

### 20.8. Pool size gấp nhiều lần capacity AS

Số connection tổng của mọi pods có thể gây quá tải AS. Tính tổng concurrency toàn cụm và phối hợp quota/ratelimit với đội quản trị AS.

### 20.9. Cho caller chọn introspection-uri

Đây là nguy cơ **SSRF và token exfiltration**. URI phải đến từ cấu hình tin cậy, không lấy từ token/header do client tự gửi.

### 20.10. Chỉ xem status HTTP 200 là token active

`200 {"active":false}` có nghĩa token không active. Không tự parse HTTP response bằng logic “2xx thì authenticated” và bỏ trường `active`.

## 21. Một thiết kế production tham khảo

Giả sử Orders API chạy 6 replicas, mỗi replica nhận khoảng 350 requests/s; không cache introspection. Tổng lưu lượng có thể khoảng:

```text
350 requests/s × 6 pods = 2.100 introspection calls/s
```

Cần thống nhất với AS:

- AS có thể xử lý 2.100 RPS introspection với latency mong muốn không?
- Có rate limit theo client ID không?
- Cần phân bổ lưu lượng từ các Resource Servers khác không?
- Nếu AS có p99 latency tăng, tổng in-flight và pool demand tăng bao nhiêu?
- Mức revocation delay chấp nhận được là bao nhiêu nếu cân nhắc cache?
- Có cần nhiều AS replicas/load balancer và failover strategy không?

Trên mỗi pod:

```text
Ingress
  |
  v
BearerTokenAuthenticationFilter
  |
  v
OpaqueTokenAuthenticationProvider
  |
  v
OpaqueTokenIntrospector (singleton bean)
  |
  v
RestOperations / Apache HttpClient 5
  ├─ Basic client auth
  ├─ TLS validation
  ├─ Connection pool (bounded)
  ├─ Pool lease timeout
  ├─ Connect timeout
  ├─ Response/socket timeout
  ├─ Idle/expired connection eviction
  └─ Metrics, bounded retry, fail-closed handling
  |
  v
Authorization Server introspection endpoint
```

Nguyên tắc vận hành:

1. **Giới hạn** tất cả hàng đợi/connections/concurrency.
2. **Tách** Basic credential và pool introspection khỏi HTTP client khác.
3. **Đo** latency, pool saturation và phân loại lỗi.
4. **Bảo vệ** toàn bộ đường gửi token/secret bằng TLS và allowlisted URI.
5. **Đóng** client đúng vòng đời Spring bean.
6. **Không** bỏ xác thực khi AS không sẵn sàng.
7. **Kiểm tra** scope/audience và object-level authorization sau introspection.

### 21.1. Trách nhiệm các nhóm vận hành

| Nhóm | Trách nhiệm |
|---|---|
| Authorization Server team | Endpoint capacity, client auth methods, quota, metadata, secret rotation, trạng thái token |
| API/Resource Server team | Custom introspector, HTTP timeout/pool, Bearer handling, claims/authority, fail closed, service policy |
| Platform/Infrastructure | DNS, TLS cert/CA, egress/firewall, load balancing, autoscaling, node time sync |
| Observability/SRE | Tracing an toàn, dashboards, p95/p99, pool metrics, alerting, incident runbook |
| Security team | Least privilege cho introspection client, secret handling, risk acceptance cho cache/revocation |

Các nhóm cần cùng quyết định một **error budget và capacity contract**, không chỉ thống nhất “introspection-uri hiện truy cập được”.

## 22. Danh sách kiểm tra bàn giao kỹ thuật

| Hạng mục | Câu hỏi cần trả lời |
|---|---|
| URI | Có phải introspection endpoint chính thức, đúng issuer/realm/environment? |
| Client authentication | Dùng Basic secret, mTLS hay private_key_jwt theo đăng ký? |
| Secrets | Có được inject an toàn, rotate, không lộ trong logs? |
| TLS | Hostname, chain, CA/truststore, proxy và SNI đã đúng trong runtime? |
| Connection reuse | HTTP client/pool có tái sử dụng được không? |
| Pool limits | Có max-total, max-per-route và pool-lease timeout? |
| Timeouts | Connect, read/response và overall budget có được hiểu đúng? |
| Queue/concurrency | Có giới hạn thread/connection/in-flight và backpressure? |
| Retries | Có phân loại lỗi, bounded attempts, jitter, deadline? |
| Circuit breaker | Khi open có fail closed, không tự cấp quyền? |
| Cache | Có cân nhắc revocation delay, exp và secret protection? |
| Redirect | Có kiểm soát việc gửi credentials tới host khác? |
| HTTP semantics | Có phân biệt 200 inactive với HTTP 401 client auth lỗi? |
| Authorization | Có scope, audience/resource, tenant/owner business policy? |
| Observability | Có metrics p95/p99/pool pending/error type và log đã redacted? |
| Lifecycle | Pool/client/eviction threads được đóng khi shutdown? |
| Tests | Có network faults, pool exhaustion, timeout, secret rotation và revoked token? |
| Multi-instance | Tổng connection/RPS của mọi pods có phù hợp capacity AS? |

Đây là **bảng gợi ý triển khai**, không phải chứng nhận rằng một hệ thống nào đã đạt những điều kiện trên. Kết quả cần dựa trên môi trường đang chạy và số đo thực tế.

## 23. Tài liệu tham khảo

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): request, `active`, authentication/authorization cho introspection endpoint.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bearer token, `invalid_token` và `insufficient_scope`.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): công bố introspection endpoint và phương thức client authentication hỗ trợ.
- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): `OpaqueTokenIntrospector` và cấu hình introspection cho Servlet.
- [Spring Security — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): xác thực bearer token và chính sách cho Resource Server.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): `RestTemplate`, HTTP request factory và cấu hình REST client.
- [Apache HttpClient 5 Documentation](https://hc.apache.org/httpcomponents-client-5.4.x/index.html): connection manager, request config và lifecycle của HTTP client.
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): quản lý các thuộc tính môi trường và cấu hình không hardcode secrets.

**Kết luận:** Tùy chỉnh HTTP client cho opaque token introspection không chỉ là tăng timeout để request “đỡ lỗi”. Nó là thiết kế một **đường xác thực outbound có giới hạn tài nguyên và fail-closed**: URI/credential được kiểm soát, TLS tin cậy, pool tái sử dụng connection, timeout theo ngân sách, retry có giới hạn, cache có chấp nhận rủi ro, dọn tài nguyên theo vòng đời bean và observability không lộ token. Khi những lớp này được thiết kế đúng, Resource Server có thể giữ được cả **tính an toàn xác thực** và **khả năng vận hành** dưới tải hoặc khi Authorization Server gặp sự cố.
