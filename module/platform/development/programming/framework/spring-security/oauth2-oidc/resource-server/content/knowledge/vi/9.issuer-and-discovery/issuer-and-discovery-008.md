# URL bên trong, URL công bố và issuer khi triển khai sau proxy

Khi **Authorization Server** và **Spring Security OAuth 2.0/OIDC Resource Server** được triển khai sau Nginx, API Gateway, Ingress hoặc Load Balancer, rất dễ xuất hiện hai địa chỉ cho cùng một hệ thống:

- **URL nội bộ:** địa chỉ service mà hạ tầng dùng để chuyển tiếp, ví dụ `http://auth-service:8080`.
- **URL công bố (public/external URL):** địa chỉ mà client, trình duyệt và những thành phần tích hợp nhìn thấy, ví dụ `https://login.example.com`.

Vấn đề quan trọng là **`issuer` không đơn thuần là nơi một request tình cờ được chuyển tới**. Trong OAuth 2.0 và OpenID Connect, issuer là **định danh logic ổn định của bên phát hành token**. Claim `iss` trong JWT, trường `issuer` của metadata và cấu hình `issuer-uri` tại Resource Server phải thống nhất với định danh đã công bố.

> **Nguyên tắc thiết kế:** giữ một issuer canonical ổn định, thường là URL HTTPS công bố của Authorization Server, dù giao tiếp giữa proxy và service nội bộ sử dụng hostname, port hoặc đường dẫn khác.

Đây là nguyên nhân của nhiều lỗi `401 invalid_token`, discovery `404`, metadata chứa URL `http` hoặc client bị redirect về tên container sau khi triển khai lên production.

## 1. Ba loại URL cần phân biệt

Giả sử hệ thống có một Identity Provider (IdP) phục vụ shop:

| Loại địa chỉ | Ví dụ | Dùng để làm gì? |
|---|---|---|
| **Issuer canonical** | `https://login.example.com/realms/shop` | Định danh AS trong metadata, claim `iss` và cấu hình Resource Server |
| **URL public của endpoint** | `https://login.example.com/realms/shop/.well-known/openid-configuration` | Client/Resource Server gọi để khám phá cấu hình AS |
| **URL upstream nội bộ** | `http://auth-service:8080/realms/shop` | Reverse proxy chuyển tiếp request tới ứng dụng AS trong mạng riêng |
| **JWK Set URI** | `https://login.example.com/realms/shop/protocol/openid-connect/certs` | Phân phối public keys để xác minh chữ ký JWT |
| **Resource Server API URL** | `https://api.example.com/api/orders` | Địa chỉ API nhận bearer token từ client |

Các địa chỉ trong bảng chỉ minh họa. Đường dẫn JWKS thực tế phụ thuộc Authorization Server; nó **không có một đường dẫn URL cố định áp dụng cho mọi IdP**.

Điểm cần tránh: thay vì khai báo:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: http://auth-service:8080/realms/shop
~~~

chỉ vì Resource Server nằm cùng Docker/Kubernetes network, nên dùng issuer **thực sự xuất hiện trong JWT và metadata**:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
~~~

Hai URI này đại diện cho **hai tên khác nhau**, dù proxy có thể dẫn tới cùng process. Spring Security không tự xem chúng là tương đương về issuer.

## 2. Sơ đồ triển khai có reverse proxy

~~~text
       Browser / Mobile / Backend Client
                      |
                      | HTTPS
                      | https://login.example.com/realms/shop
                      v
                Reverse Proxy / Ingress
                      |
                      | internal upstream route
                      | http://auth-service:8080/realms/shop
                      v
             Authorization Server (AS)
                      |
              ký access token JWT
                      |
                      v
 JWT claims:
   iss = https://login.example.com/realms/shop
   aud = orders-api
   exp = ...
                      |
                      v
      Client -- Authorization: Bearer <JWT> --> Resource Server
                                                     |
                                            issuer-uri =
                                            https://login.example.com/realms/shop
                                                     |
                                             JWT signature + claim
                                                validation
~~~

Có thể có thêm reverse proxy trước Resource Server, ví dụ `https://api.example.com` chuyển tiếp đến `http://orders-service:8080`. Điều đó **không làm thay đổi issuer của JWT**. Một token được phát hành bởi `login.example.com` vẫn có claim `iss` là issuer của AS, kể cả Resource Server nhận request qua một tên miền khác.

### Ai quyết định giá trị `iss`?

**Authorization Server quyết định giá trị issuer trong token**. Resource Server chỉ cấu hình giá trị mà nó tin và kiểm tra claim:

~~~json
{
  "iss": "https://login.example.com/realms/shop",
  "sub": "alice",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 2000000000
}
~~~

Nếu AS phát hành token có:

~~~json
{
  "iss": "http://auth-service:8080/realms/shop"
}
~~~

nhưng Resource Server tin `https://login.example.com/realms/shop`, xác minh issuer sẽ thất bại dù cả hai URL cùng chuyển tới một dịch vụ. Cách khắc phục đúng thường là **cấu hình AS phát hành canonical issuer**, kiểm tra proxy/forwarded headers và đồng bộ Resource Server. Không nên tùy tiện tắt `iss` validator.

## 3. Issuer là định danh, không phải mẹo tìm đường mạng

OAuth 2.0 Authorization Server Metadata và OpenID Connect Discovery sử dụng URI issuer như một **identifier**. Cần phân biệt hai câu hỏi:

1. **Token có đúng nguồn phát hành tin cậy không?** → kiểm tra `iss` với issuer canonical.
2. **Resource Server kết nối mạng tới endpoint metadata/JWKS bằng cách nào?** → routing, DNS, proxy, TLS hoặc một JWKS URI được cấu hình tin cậy.

Hai câu hỏi có thể có đáp án khác nhau. Ví dụ:

~~~text
Expected issuer (identity):
  https://login.example.com/realms/shop

Trusted public JWKS endpoint:
  https://login.example.com/realms/shop/protocol/openid-connect/certs

Optional trusted internal JWKS endpoint:
  https://auth-jwks.svc.cluster.local/realms/shop/protocol/openid-connect/certs
~~~

Nếu dùng JWKS nội bộ, cần bảo đảm URL đó **thực sự phục vụ public keys của cùng issuer**, bảo vệ kênh kết nối và không cho client tùy ý chọn URL. Giá trị `iss` trong token vẫn là **URL public canonical**.

### So khớp URI phải chính xác

Các giá trị sau **không mặc nhiên tương đương** trong issuer validation:

| Issuer 1 | Issuer 2 | Khác biệt |
|---|---|---|
| `https://login.example.com` | `http://login.example.com` | Scheme |
| `https://login.example.com` | `https://login.example.com:8443` | Port |
| `https://login.example.com/realms/shop` | `https://login.example.com/realms/shop/` | Dấu slash cuối |
| `https://login.example.com/realms/shop` | `https://login.example.com/shop` | Path |
| `https://login.example.com` | `https://login-internal` | Host |

Đừng tự sửa string bằng cách thêm/bớt slash hoặc đổi HTTP thành HTTPS trong JWT. Chữ ký token bảo vệ cả payload; sửa claim `iss` sẽ khiến signature không còn hợp lệ. Giá trị đúng phải được phát hành từ AS và được cấu hình nhất quán trong các client/Resource Server.

## 4. Discovery dựa vào `issuer-uri` hoạt động ra sao?

Với Spring Boot Resource Server dùng JWT:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          audiences:
            - orders-api
~~~

Spring Security dùng issuer URI để xác định endpoint **Provider Configuration (OIDC)** hoặc **Authorization Server Metadata (OAuth 2.0)** theo các quy tắc discovery được hỗ trợ, sau đó tìm `jwks_uri` để tải public keys.

Sơ đồ:

~~~text
Resource Server
  |
  | issuer-uri = https://login.example.com/realms/shop
  v
Discovery endpoint được hỗ trợ
  |
  | metadata: issuer, jwks_uri, ...
  v
JWKS endpoint
  |
  | public keys theo kid/kty/alg...
  v
JwtDecoder
  |
  +-- verify signature
  +-- validate iss / exp / nbf / aud theo cấu hình
  +-- chuyển scope -> authorities
~~~

### 4.1. Metadata OIDC

Với issuer có path `/realms/shop`, một provider có thể công bố:

~~~text
GET https://login.example.com/realms/shop/.well-known/openid-configuration
~~~

Phản hồi rút gọn:

~~~json
{
  "issuer": "https://login.example.com/realms/shop",
  "authorization_endpoint": "https://login.example.com/realms/shop/protocol/openid-connect/auth",
  "token_endpoint": "https://login.example.com/realms/shop/protocol/openid-connect/token",
  "jwks_uri": "https://login.example.com/realms/shop/protocol/openid-connect/certs"
}
~~~

Tất cả URL trên là minh họa một kiểu triển khai IdP. Các endpoint của Spring Authorization Server, Keycloak, Auth0, Okta hoặc IdP khác có thể sử dụng đường dẫn khác nhau.

**Metadata phải công bố issuer canonical.** Nếu khách hàng truy cập metadata qua `https://login.example.com` nhưng response lại chứa:

~~~json
{
  "issuer": "http://auth-service:8080/realms/shop"
}
~~~

đây là dấu hiệu AS/proxy chưa thống nhất external URL. Đổi `issuer-uri` tại Resource Server thành URL nội bộ có thể che đi sự cố ở một dịch vụ nhưng làm sai hợp đồng cho browser, client và các API khác.

### 4.2. Metadata OAuth 2.0 theo RFC 8414

Không phải mọi AS là một OIDC Provider. Resource Server JWT có thể dùng metadata OAuth 2.0 khi được hỗ trợ.

Với issuer có path, RFC 8414 định nghĩa cách chèn well-known suffix giữa host và path của issuer. Ví dụ cho issuer `https://login.example.com/realms/shop`, endpoint OAuth metadata có thể là:

~~~text
https://login.example.com/.well-known/oauth-authorization-server/realms/shop
~~~

Trong khi OIDC discovery thường sử dụng endpoint:

~~~text
https://login.example.com/realms/shop/.well-known/openid-configuration
~~~

Spring Security có thể thử một số dạng metadata endpoint được chuẩn hóa. **Không tự đoán rằng mọi well-known URL luôn dùng một cách ghép path**; kiểm tra endpoint do IdP hỗ trợ và tài liệu tương ứng.

### 4.3. Resource Server kiểm tra metadata và JWT ở hai thời điểm

Metadata discovery giúp tìm issuer và nguồn khóa. Sau khi có khóa phù hợp, Resource Server xác minh JWS và kiểm tra claim `iss`/`aud`/thời hạn. Một metadata JSON trả `200 OK` **không tự làm mọi JWT đều hợp lệ**.

Với cấu hình Spring Security hiện đại, discovery có thể được trì hoãn đến request JWT đầu tiên; với decoder được khởi tạo khác, hành vi mạng lúc startup có thể khác. Dù lúc nào metadata được truy cập, **public DNS/TLS/routing phải hoạt động khi Resource Server cần discovery hoặc tải key chưa cache**.

## 5. Những lỗi đặc trưng khi AS đứng sau proxy

### 5.1. AS công bố `http` dù người dùng truy cập HTTPS

Tình huống:

~~~text
Browser   -- HTTPS --> https://login.example.com
Ingress   -- HTTP  --> http://auth-service:8080
AS nhìn request nội bộ:
  scheme = http
  host   = auth-service
~~~

Nếu AS tự suy ra issuer hoặc endpoint URL từ request nội bộ mà không xử lý reverse proxy, metadata có thể chứa `http://auth-service:8080`. Đó là địa chỉ không phù hợp cho client ngoài mạng, và thường không khớp `iss`/issuer mà Resource Server kỳ vọng.

Cách giải quyết: **cấu hình canonical external issuer rõ ràng** nếu IdP hỗ trợ; đồng thời bảo đảm reverse proxy chuyển tiếp đúng `Host`, scheme, port và prefix (khi cần), còn AS chỉ tin forwarded headers từ proxy đã được xác thực/trust.

### 5.2. Redirect quay về hostname nội bộ

Client mở:

~~~text
https://login.example.com/oauth2/authorize
~~~

nhưng AS trả:

~~~http
HTTP/1.1 302 Found
Location: http://auth-service:8080/login
~~~

Browser ngoài cluster không thể gọi `auth-service:8080`. Đây là lỗi external URL reconstruction / issuer/forwarded headers hoặc cấu hình endpoint mapping của AS. Cần giải quyết ở AS/proxy, không giải quyết bằng cách sửa `redirect_uri` của client thành hostname container.

### 5.3. Metadata đúng nhưng `jwks_uri` là URL nội bộ

Ví dụ:

~~~json
{
  "issuer": "https://login.example.com",
  "jwks_uri": "http://auth-service:8080/oauth2/jwks"
}
~~~

Resource Server chạy cùng cluster **có thể** truy cập được URL nội bộ, nhưng client ngoài cluster hoặc các hệ thống tích hợp khác không truy cập được. Metadata công bố chung thường nên chứa endpoint public mà những bên tiêu thụ metadata có thể tiếp cận và xác thực được.

Nếu một Resource Server có lý do vận hành để tải JWKS qua địa chỉ nội bộ, hãy **cấu hình riêng `jwk-set-uri` cho Resource Server đó**, giữ `issuer-uri` canonical. Không nên phát hành metadata chứa internal-only host chỉ để giải quyết routing cho một consumer.

### 5.4. Sai context path hoặc rewrite path

Ví dụ bên ngoài là:

~~~text
https://login.example.com/idp/realms/shop
~~~

nhưng service nội bộ là:

~~~text
http://auth-service:8080/realms/shop
~~~

Proxy phải chuyển `/idp/realms/shop` thành `/realms/shop` theo quy tắc đã thiết kế. AS cũng cần biết path public `/idp` khi tạo metadata, redirect và issuer, nếu cấu hình sản phẩm yêu cầu. **`X-Forwarded-Prefix` có thể giúp một số framework tái dựng external path, nhưng không tự giải quyết mọi cơ chế rewrite/path của IdP**.

Sai một slash, strip path hai lần hoặc thêm prefix hai lần có thể gây `404` discovery, `404` JWKS hoặc redirect loop.

## 6. Cấu hình issuer ngay tại Authorization Server

Về mặt trách nhiệm, **AS phải phát hành token với issuer canonical**. Resource Server không có nghĩa vụ “biến” một issuer nội bộ thành public issuer.

### 6.1. Spring Authorization Server

Với ứng dụng AS xây dựng bằng Spring Authorization Server, có thể cấu hình issuer tường minh:

~~~java
package com.example.auth.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;

@Configuration
public class AuthorizationServerIssuerConfig {

    @Bean
    AuthorizationServerSettings authorizationServerSettings() {
        return AuthorizationServerSettings.builder()
            .issuer("https://login.example.com")
            .build();
    }
}
~~~

Đây là ví dụ **cho một Authorization Server có issuer gốc không có path prefix**. Nếu public issuer thật sự có path, sử dụng đúng giá trị public issuer đã quy định và cấu hình các endpoint/routing tương ứng.

Theo tài liệu Spring Authorization Server, nếu không khai báo issuer trong `AuthorizationServerSettings`, framework có thể xác định issuer từ request hiện tại. Sau proxy, request nội bộ có thể không phản ánh đúng host/scheme công bố nếu forwarded headers chưa được xử lý an toàn. **Khai báo issuer cố định giúp ổn định danh tính của AS qua các request và môi trường hạ tầng.**

Lưu ý: thay issuer của một AS **đang phát hành token cho production** là thay đổi hợp đồng, không phải chỉ đổi base URL của giao diện. Các client/Resource Server đang tin issuer cũ có thể từ chối JWT mới hoặc metadata mới. Cần kế hoạch chuyển đổi tương ứng.

### 6.2. Với IdP khác

Keycloak, Okta, Auth0 và các Authorization Server khác có cách thiết lập public hostname/front-end URL, proxy mode hoặc issuer riêng. Hãy cấu hình đúng theo **phiên bản và tài liệu nhà cung cấp**, ví dụ:

- External hostname/scheme/port mà client nhìn thấy.
- Path prefix mà IdP cần công bố.
- Reverse-proxy headers được phép tin.
- Metadata issuer và endpoint URL được sinh ra.
- JWKS endpoint và signing key rotation.

Không sửa `iss` bằng tay sau khi ký JWT, không thay token bằng Base64URL encode lại và không tắt kiểm tra issuer ở Resource Server để che lỗi external URL.

## 7. Forwarded headers giúp AS thấy thông tin public request

Khi TLS kết thúc ở proxy, ứng dụng phía sau thường nhìn thấy HTTP request nội bộ. Proxy có thể truyền thông tin về request gốc bằng:

| Header | Nội dung gợi ý | Ví dụ |
|---|---|---|
| `X-Forwarded-Proto` | Scheme bên ngoài | `https` |
| `X-Forwarded-Host` | Host bên ngoài | `login.example.com` |
| `X-Forwarded-Port` | Port bên ngoài | `443` |
| `X-Forwarded-Prefix` | Prefix bên ngoài, nếu có | `/idp` |
| `X-Forwarded-For` | Địa chỉ client/hops theo proxy policy | `203.0.113.10` |
| `Forwarded` (RFC 7239) | Thông tin proxy chuẩn hóa | `proto=https;host=login.example.com` |

Những header này giúp framework xây dựng absolute URL và redirect, nhưng **chúng không phải sự thật bảo mật nếu request được gửi trực tiếp từ Internet hoặc nếu proxy giữ nguyên header do client tự tạo**.

### 7.1. Spring Boot xử lý forwarded headers

Với ứng dụng Spring Boot phục vụ HTTP sau reverse proxy, có thể khai báo:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Spring Boot có các chiến lược điển hình:

- **`none`:** không dùng forwarded headers để tái dựng request URL.
- **`native`:** để embedded web server sử dụng hỗ trợ forwarded headers của chính server, tùy Tomcat/Jetty/Undertow/Netty.
- **`framework`:** sử dụng cơ chế Spring Framework, như `ForwardedHeaderFilter` trong Servlet stack hoặc `ForwardedHeaderTransformer` trong WebFlux.

Đây là **cấu hình ứng dụng HTTP đang đứng sau proxy**; nếu Spring Boot chạy ở phía Authorization Server, nó có thể giúp AS tạo URL đúng. Nếu Resource Server API cũng đứng sau proxy, forwarded headers có thể giúp API xử lý redirect/link và các logic HTTP tương ứng, nhưng **nó không tự sửa `issuer-uri` JWT**.

Trong một số cấu hình Tomcat có HTTPS termination ở proxy, có thể cần thêm:

~~~yaml
server:
  forward-headers-strategy: framework
  tomcat:
    redirect-context-root: false
~~~

Thuộc tính Tomcat này liên quan xử lý redirect context root trước khi scheme forwarded có hiệu lực. Chỉ áp dụng khi phù hợp phiên bản Boot/Tomcat và hành vi của ứng dụng.

### 7.2. Ví dụ Nginx minh họa

Giả sử Nginx là **trusted edge proxy**, nhận HTTPS tại `login.example.com` và chuyển tiếp tới AS trên mạng riêng:

~~~nginx
server {
    listen 443 ssl;
    server_name login.example.com;

    # Cần khai báo ssl_certificate / ssl_certificate_key thật
    # và cấu hình TLS phù hợp ở production.

    location / {
        proxy_pass http://auth-service:8080;

        proxy_set_header Host login.example.com;
        proxy_set_header X-Forwarded-Host login.example.com;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Port 443;

        # Proxy tại biên phải ghi đè/loại bỏ forwarded headers
        # mà client có thể tự gửi.
        proxy_set_header Forwarded "";
        proxy_set_header X-Forwarded-For $remote_addr;
    }
}
~~~

Đây là ví dụ để giải thích **truyền public host/scheme qua một proxy duy nhất**. Nó chưa phải cấu hình Nginx hoàn chỉnh để chạy production: còn cần chứng chỉ TLS, cài đặt timeout, giới hạn request, logging, upstream health, chính sách IP thật khi có thêm load balancer phía trước và cấu hình network.

Trong chain nhiều proxy, việc xác định `X-Forwarded-For` hoặc header chuẩn `Forwarded` cần trust boundary rõ ràng. Không sao chép nguyên một chuỗi `X-Forwarded-For` không đáng tin rồi dùng địa chỉ đầu tiên làm căn cứ bảo mật.

### 7.3. Rủi ro Host header và forwarded-header injection

Nếu attacker được phép tự gửi:

~~~http
Host: attacker.example
X-Forwarded-Host: attacker.example
X-Forwarded-Proto: http
~~~

và AS tin những header này, nó có thể tạo redirect, metadata hoặc absolute URL sai. Trong thiết kế thiếu kiểm soát, sự cố có thể liên quan open redirect, host-header injection, issuer confusion hoặc rò rỉ token qua URL.

Các biện pháp nền tảng:

1. Proxy tại **ranh giới tin cậy** phải xóa/ghi đè header `Forwarded` và `X-Forwarded-*` từ nguồn không đáng tin.
2. Chỉ cho phép traffic tới AS/RS backend qua proxy hoặc những kết nối nội bộ được phép; không để client đi vòng qua proxy rồi tự đưa header giả.
3. Kiểm soát danh sách host được phép và TLS hostname.
4. Ưu tiên **cấu hình issuer canonical cố định** khi sản phẩm cho phép.
5. Giới hạn quyền sửa cấu hình issuer/JWKS, vì đó là nguồn quyết định tin cậy.

Chỉ bật `server.forward-headers-strategy: framework` mà không bảo vệ forwarded headers ở edge là chưa đủ.

## 8. Path prefix: external path và internal path có thể khác nhau

Một sơ đồ triển khai thường có prefix:

~~~text
Public:
  https://login.example.com/idp/oauth2/jwks

Internal:
  http://auth-service:8080/oauth2/jwks
~~~

Nếu proxy strip `/idp` trước khi chuyển request, AS có thể không biết public prefix. Một số framework hỗ trợ `X-Forwarded-Prefix: /idp`, nhưng cách sử dụng thực tế phụ thuộc stack và chính sản phẩm Authorization Server.

Các quyết định cần thống nhất:

- **Issuer canonical** có path `/idp` hay không?
- OIDC/OAuth metadata đang công bố những absolute URLs nào?
- Ingress có giữ nguyên path, rewrite hay strip prefix?
- AS có được cấu hình context path hoặc frontend URL tương ứng không?
- Endpoint callback và logout của client đang trỏ tới URL public nào?
- Có đoạn nào thêm prefix hai lần hoặc bỏ prefix hai lần không?

### 8.1. Ví dụ path không thay đổi

Nếu cả public và internal đều phục vụ `/realms/shop`, mapping đơn giản:

~~~text
https://login.example.com/realms/shop/*
    -> http://auth-service:8080/realms/shop/*
~~~

Trong trường hợp này, AS có thể giữ nguyên route path và chỉ cần biết scheme/host/port public.

### 8.2. Ví dụ path bị rewrite

~~~text
https://login.example.com/idp/realms/shop/*
    -> http://auth-service:8080/realms/shop/*
~~~

Lúc này, chỉ cấu hình `X-Forwarded-Proto=https` và `X-Forwarded-Host=login.example.com` chưa chắc đủ. Cần quyết định cách AS hiểu `/idp` và cách proxy rewrite path. Một cấu hình sai có thể làm metadata tuy trả 200 nhưng công bố JWKS URI không tồn tại hoặc `iss` thiếu `/idp`.

**Không sửa `issuer-uri` của Resource Server cho “khớp internal path”** nếu token đang phát hành với public issuer có prefix. Cần sửa nơi phát hành metadata/token hoặc cách routing.

## 9. Khi Resource Server không gọi được hostname public

Trong Docker/Kubernetes, Resource Server có thể truy cập `auth-service:8080` nhưng không phân giải hoặc kết nối được `login.example.com`. Đây là **sự cố network routing/DNS**, không đồng nghĩa issuer nên thay bằng hostname nội bộ.

Có ba hướng tổ chức thường gặp.

### 9.1. Cho Resource Server truy cập public issuer qua routing phù hợp

Cấu hình chỉ dùng issuer:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          audiences:
            - orders-api
~~~

Hạ tầng phải cho phép Resource Server kết nối tới endpoints metadata và JWKS qua hostname công bố. Việc kết nối có thể đi qua public ingress, private ingress hoặc split-horizon DNS, miễn là **TLS được xác minh đúng** và URL nội dung metadata thống nhất.

Ưu điểm: một nguồn endpoint public chuẩn để tất cả consumer nhìn thấy.

Lưu ý: trong một số cluster, request từ pod tới external hostname của chính ingress có thể gặp vấn đề hairpin NAT hoặc routing. Giải quyết bằng kiến trúc ingress/DNS phù hợp, không đổi giá trị `iss`.

### 9.2. Split-horizon DNS giữ nguyên URL nhưng định tuyến nội bộ

Có thể thiết lập:

~~~text
Trong Internet:
  login.example.com -> public ingress address

Trong cluster:
  login.example.com -> internal ingress address
~~~

Ứng dụng vẫn gọi `https://login.example.com`. Vì **hostname trong URL không đổi**, TLS certificate và endpoint metadata phải phù hợp với `login.example.com`; địa chỉ IP đích có thể khác nhau theo nơi phân giải.

Đây thường là cách giữ một canonical issuer cho nhiều mạng khác nhau mà vẫn tối ưu đường đi nội bộ. Phải đảm bảo internal ingress thực thi cùng hợp đồng issuer/JWKS, có truststore/chứng chỉ hợp lệ, và không bỏ TLS hostname verification.

### 9.3. `issuer-uri` public + `jwk-set-uri` internal

Spring Security hỗ trợ khai báo **issuer public để validate `iss`** và **JWK Set URI trực tiếp để lấy public keys**:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          jwk-set-uri: https://auth-jwks.svc.cluster.local/realms/shop/protocol/openid-connect/certs
          audiences:
            - orders-api
~~~

Trong ví dụ:

- `issuer-uri` vẫn phải khớp claim `iss` của JWT.
- `jwk-set-uri` là địa chỉ nội bộ **đã được phê duyệt**, phục vụ public keys tương ứng với cùng AS/issuer.
- Resource Server không cần metadata discovery để tìm JWKS URI.
- Token vẫn phải vượt qua signature verification, issuer/time validation và audience validation.

Đây là cấu hình rất hữu ích khi external issuer không thể được gọi trực tiếp từ network nội bộ nhưng có một trusted JWKS endpoint riêng.

**Các điều kiện cần bảo đảm:**

- `auth-jwks.svc.cluster.local` thật sự là nguồn khóa của AS tương ứng; không trỏ nhầm service hoặc tenant.
- Kênh tới JWKS được bảo vệ (TLS nội bộ hoặc một kênh tin cậy có chính sách rõ ràng); tránh tin nội dung JWKS bị thay đổi trên đường truyền.
- Nếu dùng hostname TLS nội bộ, certificate phải khớp hostname và truststore của JVM.
- Endpoint công bố public metadata cho client vẫn nên chứa URL public thích hợp.
- Key rotation phải làm mới đúng khóa ở nguồn JWKS nội bộ và mọi Resource Server.

**Không cấu hình chỉ `jwk-set-uri` rồi bỏ `issuer-uri`** nếu API vẫn có hợp đồng issuer rõ ràng. Chỉ biết một bộ public keys không tự thay thế việc kiểm tra token thuộc issuer nào.

## 10. Spring Security Resource Server: cấu hình hoàn chỉnh

### 10.1. Dependencies

Ví dụ Gradle cho Spring Boot + Spring MVC:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Starter Resource Server đưa các thành phần JWT/JOSE cần thiết. Nếu khai báo thư viện thủ công, cần có cả `spring-security-oauth2-resource-server` và `spring-security-oauth2-jose`.

### 10.2. application.yml

Giả sử public issuer là `https://login.example.com/realms/shop` và `orders-api` chỉ nhận access token có audience `orders-api`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          jwk-set-uri: https://auth-jwks.svc.cluster.local/realms/shop/protocol/openid-connect/certs
          audiences:
            - orders-api
~~~

Nếu Resource Server kết nối được public discovery/JWKS, có thể bỏ `jwk-set-uri` để Spring Security tự khám phá. Nếu sử dụng phiên bản Spring Boot chưa hỗ trợ property `audiences`, thêm `OAuth2TokenValidator<Jwt>` kiểm tra audience trong decoder.

### 10.3. SecurityFilterChain

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Token có scope `orders.read` thường được chuyển thành authority `SCOPE_orders.read`, sau khi JwtDecoder xác minh token. Cấu hình không bao gồm chính sách session/cookie/CSRF cụ thể; ứng dụng cần xử lý những yếu tố đó theo client và kiến trúc thực tế.

Quan trọng hơn, **không dùng `server.forward-headers-strategy` ở Resource Server như một cách thay thế `issuer-uri`**. Cái thứ nhất liên quan thông tin HTTP request đi qua proxy; cái thứ hai là **giá trị issuer được tin trong token**.

### 10.4. Nếu tự tạo JwtDecoder

Khi ứng dụng tự khai báo `@Bean JwtDecoder` hoặc override decoder trong security DSL, Spring Boot có thể **back off** khỏi auto-configuration. Đặc biệt:

- `issuer-uri` trong YAML không mặc nhiên tự thêm issuer validator cho decoder tùy biến.
- `jwk-set-uri` chỉ cung cấp nguồn key.
- `audiences` có thể không được áp dụng vào custom decoder nếu ứng dụng không tự cấu hình.
- Việc lấy metadata/JWKS lúc startup hoặc runtime tùy builder/factory đang dùng.

Ví dụ custom decoder dùng JWKS nội bộ nhưng vẫn kiểm tra public issuer:

~~~java
package com.example.orders.security;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class ExplicitJwtDecoderConfig {

    private static final String ISSUER =
        "https://login.example.com/realms/shop";

    private static final String JWKS =
        "https://auth-jwks.svc.cluster.local/realms/shop/protocol/openid-connect/certs";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(JWKS).build();

        OAuth2TokenValidator<Jwt> audience =
            new JwtClaimValidator<List<String>>(
                "aud",
                values -> values != null && values.contains("orders-api"));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(ISSUER),
                audience));

        return decoder;
    }
}
~~~

Các URL trong code chỉ minh họa. Khi triển khai, chuyển sang cấu hình môi trường đáng tin và có cơ chế kiểm soát thay đổi. Với ứng dụng thông thường, dùng Spring Boot properties đơn giản hơn.

## 11. Metadata cần đúng những trường nào?

Đối với bài toán issuer/proxy, ít nhất phải xác định:

| Trường metadata | Ý nghĩa | Sai sót điển hình |
|---|---|---|
| `issuer` | Định danh canonical của AS | Lộ `http://auth-service:8080` |
| `jwks_uri` | Endpoint public keys | Chỉ có internal host, sai scheme hoặc path |
| `authorization_endpoint` | Browser/client tới endpoint xin ủy quyền | Redirect ra host container hoặc HTTP |
| `token_endpoint` | Client dùng để đổi code/nhận token | Client ngoài mạng không truy cập được |
| `userinfo_endpoint` (OIDC, khi có) | Endpoint user info | Host/path khác public contract |
| `end_session_endpoint` / logout endpoint (nếu có) | Logout OIDC theo provider | Redirect sai host/prefix |
| `introspection_endpoint` (khi có) | Kiểm tra opaque token | API không kết nối được hoặc dùng sai URL |

Resource Server dùng JWT thường cần `issuer` và `jwks_uri` để xác minh token. OIDC clients có thể cần thêm authorization/token/userinfo/logout endpoint. Việc chỉ sửa JWKS để một API hoạt động chưa đủ nếu login flow của browser vẫn trỏ tới host nội bộ.

**OIDC discovery metadata không phải chỉ là danh sách route.** Nó là hợp đồng mà nhiều client dùng để biết issuer và endpoint đáng tin. Những URL được công bố cần nhất quán với public hostname/path do tổ chức quản lý.

## 12. Kiểm tra cấu hình mà không làm lộ access token

Trước tiên kiểm tra các endpoint public và nội bộ (từ đúng môi trường mạng). Có thể dùng metadata **không chứa credential**:

~~~bash
curl -fsS \
  https://login.example.com/realms/shop/.well-known/openid-configuration
~~~

Nếu máy có `jq`:

~~~bash
curl -fsS \
  https://login.example.com/realms/shop/.well-known/openid-configuration \
  | jq '{issuer, jwks_uri, authorization_endpoint, token_endpoint}'
~~~

Kết quả cần có:

~~~json
{
  "issuer": "https://login.example.com/realms/shop",
  "jwks_uri": "https://login.example.com/realms/shop/protocol/openid-connect/certs",
  "authorization_endpoint": "https://login.example.com/realms/shop/protocol/openid-connect/auth",
  "token_endpoint": "https://login.example.com/realms/shop/protocol/openid-connect/token"
}
~~~

Đường dẫn ví dụ đúng với một kiểu IdP; thay bằng metadata endpoint thực được nhà cung cấp hỗ trợ.

Kiểm tra public JWKS:

~~~bash
curl -fsS \
  https://login.example.com/realms/shop/protocol/openid-connect/certs \
  | jq '{keyCount: (.keys | length), kids: [.keys[].kid]}'
~~~

Kiểm tra trusted internal JWKS **từ chính container/pod Resource Server** nếu đang cấu hình internal URI:

~~~bash
curl -fsS \
  https://auth-jwks.svc.cluster.local/realms/shop/protocol/openid-connect/certs \
  | jq '{keyCount: (.keys | length), kids: [.keys[].kid]}'
~~~

Việc `curl` thành công chỉ chứng minh HTTP/TLS/routing và một số metadata trả về. Nó **chưa chứng minh JWT xác minh được**; vẫn cần một access token thử nghiệm thật được AS ký bằng đúng khóa và các claim được mong đợi.

### 12.1. Kiểm tra các góc nhìn mạng

Nên kiểm tra từ ít nhất những phía có liên quan:

- Browser hoặc máy ngoài hệ thống: public issuer, redirect và JWKS public có truy cập được không?
- Pod/container Resource Server: `issuer-uri` có DNS/TLS/routing phù hợp không, hoặc `jwk-set-uri` nội bộ có truy cập được không?
- Pod/container AS: AS đã nhận đúng forwarded headers và công bố public issuer chưa?
- Ingress/API Gateway: có rewrite path, host hoặc scheme bất ngờ không?

Một URL truy cập được từ máy developer **không có nghĩa** cũng truy cập được từ Kubernetes pod. Ngược lại, `auth-service:8080` truy cập được trong cluster không có nghĩa nó là issuer đúng.

### 12.2. Nếu cần quan sát claim `iss` của JWT

Một JWT dạng JWS có payload có thể Base64URL decode để chẩn đoán. Nhưng việc đọc claim chưa xác minh chỉ là **bằng chứng token tự khai báo**, không thay thế `JwtDecoder` của Resource Server. Không dán token production vào website decoder công khai hoặc log nguyên `Authorization` header.

Tốt nhất dùng **token kiểm thử ngắn hạn** và so sánh claim `iss` với giá trị `issuer` từ metadata và `issuer-uri` của RS, sau đó xem kết quả xác minh thật từ Spring Security.

## 13. Bảng phân biệt lỗi proxy, discovery và JWT

| Triệu chứng | Nguyên nhân thường gặp | Nơi xử lý |
|---|---|---|
| Discovery URL trả 404 | Proxy rewrite path sai hoặc AS không hỗ trợ well-known endpoint đó | Ingress routing, metadata path của IdP |
| Metadata `issuer` là `http://auth-service:8080` | AS tự suy ra URL nội bộ do thiếu external issuer/forwarded headers | Cấu hình AS và trusted proxy |
| Metadata `issuer` public nhưng JWT `iss` internal | AS phát hành issuer khác hợp đồng, nhiều instance config không đồng nhất | Cấu hình token issuer trên AS |
| JWT `iss` đúng public, RS cấu hình `issuer-uri` internal | RS nhầm transport URL thành identity | Sửa RS issuer URI theo canonical value |
| JWT đúng chữ ký nhưng `aud` sai | Token được cấp cho API khác | Audience policy, xin đúng access token |
| Metadata public có `jwks_uri` internal | AS công bố endpoint khó truy cập từ ngoài | Public endpoint metadata/AS config; internal JWKS override tại RS nếu cần |
| `jwks_uri` trả 404 sau đổi prefix | Thừa/thiếu path khi reverse proxy rewrite | Proxy path + AS endpoint mapping |
| Redirect `Location` về HTTP | TLS termination và forwarded proto/AS URL chưa đúng | Proxy, Boot forwarded handling hoặc AS external URL |
| Redirect `Location` về tên container | Host forwarded/public hostname sai | Trusted proxy, AS canonical hostname |
| JWKS TLS certificate lỗi trong pod | DNS/hostname/truststore không khớp | Certificate chain, internal DNS, truststore |
| `kid` mới nhưng JWT không verify được | JWKS cache/rotation chưa đồng bộ | AS key publication và decoder refresh |
| `401 invalid_token` khi chuyển proxy | `iss` khác, key/JWKS không khớp, token hết hạn | JWT authentication logs và AS metadata |
| `403` sau khi JWT hợp lệ | Thiếu scope/authority hoặc quyền dữ liệu | Spring Security authorization rules |
| Chỉ lỗi trong Kubernetes, local chạy | DNS, network policy, ingress/hairpin routing, proxy headers | Hạ tầng cluster và cấu hình môi trường |

**Không mặc định mọi lỗi `401` đều do issuer**. Một JWT có chữ ký sai, hết hạn, audience sai hoặc được phát hành bởi key khác cũng có thể bị từ chối. Cần phân loại lỗi dựa vào xác minh thực, không chỉ nhìn metadata.

## 14. Phân biệt sửa issuer và sửa đường truy cập JWKS

Hai thay đổi sau có ảnh hưởng khác nhau.

### 14.1. Đổi `jwk-set-uri` nhưng giữ issuer

Ví dụ:

~~~text
Trước:
  issuer-uri  = https://login.example.com/realms/shop
  jwk-set-uri = https://login.example.com/.../certs

Sau:
  issuer-uri  = https://login.example.com/realms/shop
  jwk-set-uri = https://auth-jwks.svc.cluster.local/.../certs
~~~

Nếu hai JWKS endpoints đều phục vụ **cùng trusted signing keys** và việc kết nối an toàn, đây có thể chỉ là thay đổi **đường vận chuyển public keys**, không phải đổi issuer. JWT cũ vẫn có thể được chấp nhận nếu signature/claims hợp lệ và key phù hợp.

### 14.2. Đổi issuer canonical

Ví dụ:

~~~text
Trước:
  iss = https://old-login.example.com/realms/shop

Sau:
  iss = https://login.example.com/realms/shop
~~~

Đây là thay đổi **danh tính của AS** theo hợp đồng OAuth/OIDC. JWT cũ và mới không có cùng `iss`. Nếu mọi Resource Server đột ngột chỉ chấp nhận issuer mới, token cũ đang còn hạn có thể bị từ chối.

Cần có kế hoạch migration: phiên bản AS/clients, metadata, các Resource Server, token TTL, refresh token, issuer allowlist tạm thời khi được chấp thuận, và thời điểm ngừng issuer cũ. Không thiết kế “so sánh issuer mờ” kiểu bỏ scheme/host/path để qua migration; điều đó có thể làm rộng ranh giới tin cậy không kiểm soát.

## 15. Vì sao issuer và token endpoint không nhất thiết trùng đường dẫn?

Một public issuer có thể là:

~~~text
https://login.example.com
~~~

nhưng endpoint token là:

~~~text
https://login.example.com/oauth2/token
~~~

và JWKS là:

~~~text
https://login.example.com/oauth2/jwks
~~~

Issuer là **định danh của AS**, trong khi token endpoint/JWKS là **các endpoint phục vụ nghiệp vụ**. Không cấu hình:

~~~yaml
issuer-uri: https://login.example.com/oauth2/token
~~~

chỉ vì client gọi token endpoint ở URL đó. Phải lấy issuer từ trường `issuer` của metadata hoặc tài liệu AS rồi so khớp với `iss` thật trong JWT.

Tương tự, path của OpenID Connect Provider Configuration endpoint không phải lúc nào cũng bằng `issuer-uri + "/.well-known/openid-configuration"` khi xét mọi chuẩn/discovery pattern; với OAuth metadata, quy tắc path khác. Dùng discovery chính thức mà stack hỗ trợ.

## 16. Public issuer có bắt buộc mọi người truy cập được không?

Issuer cần là **định danh ổn định, có thể được dùng để khám phá theo hợp đồng của hệ thống**. Với hệ thống phục vụ client công khai, thường chọn HTTPS hostname công bố mà các client/Resource Server có thể xác minh và kết nối tới metadata.

Tuy nhiên cần phân biệt:

- **Định danh issuer:** chuỗi `iss` và `issuer-uri` phải khớp.
- **Khả năng khám phá metadata từ một mạng:** có thể phụ thuộc firewall, DNS và ingress.
- **Khả năng tải JWK Set:** có thể dùng public URL, split-horizon DNS hoặc trusted internal JWKS URI.
- **Quyền truy cập một endpoint:** những endpoint như token/introspection có thể có yêu cầu xác thực riêng, dù metadata/JWKS thường là thông tin public.

Một Resource Server nội bộ có thể dùng `issuer-uri` public và `jwk-set-uri` nội bộ, miễn là **giữ issuer validation và nguồn public keys đáng tin**. Điều này giúp tách identity khỏi transport mà không làm metadata của AS bị “nhiễm” hostname container.

## 17. Kịch bản thực tế: Docker Compose rồi chuyển lên Kubernetes

### 17.1. Ở máy phát triển

Giả sử AS chạy trực tiếp tại:

~~~text
http://localhost:9000
~~~

Ở dev, nếu token do AS phát hành có `iss=http://localhost:9000`, Resource Server chạy trên máy có thể dùng cùng issuer này. Nhưng nếu Resource Server nằm trong container, `localhost` của container là chính container đó, **không phải host hay container AS**.

Cách giải quyết không phải đổi `iss` tùy môi trường mỗi lần một consumer gọi. Nên chọn một hostname phát triển thống nhất (ví dụ DNS nội bộ hoặc mapping được kiểm soát) và bảo đảm mọi thành phần cần gọi URL đều định tuyến được.

### 17.2. Khi lên Kubernetes

AS chạy tại:

~~~text
http://auth-service.security.svc.cluster.local:8080
~~~

Ingress phục vụ:

~~~text
https://login.example.com
~~~

Resource Server nên tin issuer `https://login.example.com` nếu AS công bố giá trị đó. Tùy network policy, RS có thể:

1. Kết nối trực tiếp HTTPS public issuer qua ingress.
2. Dùng split-horizon DNS cho `login.example.com` tới internal ingress.
3. Giữ public issuer và cấu hình `jwk-set-uri` trỏ trusted JWKS nội bộ.

Không truyền `auth-service.security.svc.cluster.local` vào `issuer-uri` chỉ vì nó là địa chỉ service discovery của Kubernetes.

### 17.3. Kubernetes Ingress và TLS termination

Ingress có thể kết thúc TLS, sau đó gửi HTTP về pod. Đó là một kiến trúc có thể dùng nếu traffic nội bộ được bảo vệ theo yêu cầu hệ thống và proxy được tin cậy. Tuy nhiên AS phải sinh metadata/token issuer/redirect từ **external URL đúng**.

Cần kiểm tra nhất quán:

~~~text
Ingress host:     login.example.com
External scheme:  https
External port:    443
External prefix:  (nếu có)
AS public issuer: https://login.example.com[/path]
JWT iss:          https://login.example.com[/path]
RS issuer-uri:    https://login.example.com[/path]
~~~

Thông tin path ở mỗi nơi phải theo đúng hợp đồng, không chỉ giống phần hostname.

## 18. Một kiến trúc Spring Authorization Server + Resource Server

Ví dụ tổ chức có hai Spring Boot services:

~~~text
https://login.example.com
  |
  +--> ingress --> spring-authorization-server:9000
                         |
                         +-- issuer: https://login.example.com
                         +-- metadata: https://login.example.com/.well-known/...
                         +-- JWKS: https://login.example.com/oauth2/jwks

https://api.example.com
  |
  +--> ingress --> orders-api:8080
                         |
                         +-- JWT issuer-uri: https://login.example.com
                         +-- audience: orders-api
                         +-- JWKS from metadata or trusted internal URI
~~~

Bên Authorization Server:

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("https://login.example.com")
        .build();
}
~~~

Bên Resource Server:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com
          audiences:
            - orders-api
~~~

Nếu `orders-api` không kết nối được public metadata/JWKS, có thể thêm:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com
          jwk-set-uri: https://auth-jwks.svc.cluster.local/oauth2/jwks
          audiences:
            - orders-api
~~~

AS Spring Authorization Server phải thực sự công bố endpoint `/oauth2/jwks` và có `JWKSource` tương ứng; không phải mọi AS đều có cùng endpoint. Kết nối tới `auth-jwks.svc.cluster.local` cần được bảo vệ và hoạt động đúng với trusted keys của AS.

**Cả hai cấu hình Resource Server đều chấp nhận cùng `iss` public**. Chỉ khác cách lấy public keys.

## 19. Trường hợp nhiều issuer hoặc nhiều tenant

Một hệ thống có thể có nhiều issuer public:

~~~text
https://login.example.com/realms/tenant-a
https://login.example.com/realms/tenant-b
~~~

Path issuer giúp phân biệt các tenant, ngay cả khi chúng chia sẻ một host hoặc proxy. **Không xóa path khi so khớp `iss`**. Một JWT của tenant A không mặc nhiên hợp lệ cho API tenant B.

Nếu ứng dụng Resource Server thật sự chấp nhận nhiều issuer, cần một **allowlist/registry** issuer được phê duyệt và cơ chế chọn decoder cho từng issuer. Có thể cần đọc `iss` chưa xác minh để chọn decoder, nhưng phải:

1. Chỉ chọn issuer trong danh sách được cấu hình tin cậy.
2. Lấy khóa từ trusted source tương ứng.
3. Xác minh chữ ký và **kiểm tra lại `iss`** sau khi giải mã.
4. Kiểm tra audience/tenant policy và quyền trên tài nguyên.
5. Ngăn endpoint discovery/JWKS bị client tùy ý chỉ định.

Không chấp nhận mọi issuer từ token bằng cách tự discovery URL bất kỳ. Trong môi trường sau proxy, rủi ro đó càng nghiêm trọng vì nhiều host nội bộ/private IP có thể được truy cập từ Resource Server.

## 20. Một số hiểu nhầm cần tránh

**“Issuer là URL nội bộ nơi container chạy.”** Không mặc nhiên đúng. Issuer là định danh do AS phát hành/công bố; với hệ thống qua proxy thường dùng canonical public URL.

**“Dùng cùng máy chủ thì `http://auth-service:8080` và `https://login.example.com` được coi là issuer giống nhau.”** Không. Đây là những chuỗi URI khác nhau và không nên được làm tương đương bằng validator lỏng lẻo.

**“Đổi `issuer-uri` của RS sang internal URL để sửa lỗi DNS là đúng.”** Thường sai nếu JWT `iss` là public URI. Hãy xử lý routing hoặc cấu hình `jwk-set-uri` internal mà vẫn giữ issuer validation.

**“`jwks_uri` là issuer.”** Không. Nó là endpoint public keys; issuer là identifier riêng, và token endpoint cũng là URL riêng.

**“Bật `server.forward-headers-strategy: framework` là đủ an toàn.”** Không. Phải có trusted proxy xóa/ghi đè forwarded headers không đáng tin, và AS phải có issuer/URL policy đúng.

**“Nếu metadata công bố `http`, Resource Server nên tắt issuer validation.”** Không. Sửa external URL/issuer/forwarded configuration tại AS hoặc proxy.

**“Dấu slash cuối trong issuer không quan trọng.”** Không. Giá trị issuer phải nhất quán chính xác giữa metadata, JWT và RS.

**“Chỉ kiểm tra chữ ký là đủ.”** Không. Phải kiểm tra issuer, audience, thời gian và chính sách token.

**“Đổi public hostname chỉ là thay DNS.”** Không nhất thiết. Nếu issuer thay đổi, token mới có `iss` mới; client và Resource Server cần migration.

**“Có thể để external metadata công bố host nội bộ vì RS ở trong cluster.”** Không nên đối với metadata dành cho client công khai. Có thể tách public metadata khỏi transport JWKS riêng của RS.

**“Lỗi `403` luôn là do issuer sau proxy.”** Không. Khi xác thực JWT đã qua, `403` thường liên quan quyền/scope/tài nguyên.

## 21. Câu hỏi tự kiểm tra

**Câu 1.** AS chạy ở `http://auth-service:8080` sau Ingress `https://login.example.com`. Token có `iss=https://login.example.com`. Resource Server nên cấu hình issuer nào?

> `https://login.example.com`. Đó là issuer do AS công bố trong token; địa chỉ `auth-service:8080` chỉ là upstream nội bộ.

**Câu 2.** RS trong cluster không thể truy cập `login.example.com` nhưng truy cập được JWKS nội bộ. Có thể giữ issuer validation không?

> Có. Cấu hình `issuer-uri` public canonical kèm `jwk-set-uri` trỏ trusted internal JWKS, bảo vệ kênh và bảo đảm keys thuộc cùng AS.

**Câu 3.** Metadata có `issuer=http://auth-service:8080` trong khi trình duyệt tới HTTPS public host. Cần sửa ở đâu?

> Tại cấu hình external issuer/hostname của AS và proxy/forwarded headers. Không sửa token sau khi ký và không tắt issuer validation.

**Câu 4.** TLS kết thúc tại Ingress, AS thấy request HTTP. Header nào thường giúp AS biết external scheme?

> `X-Forwarded-Proto: https` hoặc thông tin `Forwarded: proto=https` từ trusted proxy, cùng chính sách external URL/issuer của AS.

**Câu 5.** Attacker có thể gửi `X-Forwarded-Host=attacker.example` trực tiếp vào AS. Vấn đề là gì?

> Nếu AS tin header không đáng tin, có thể sinh absolute URL hoặc redirect sai. Cần giới hạn đường vào backend và xóa/ghi đè forwarded headers tại trusted edge.

**Câu 6.** JWT có chữ ký hợp lệ, `iss` đúng nhưng `aud=billing-api` gửi tới `orders-api`. Có được chấp nhận không?

> Không, nếu RS yêu cầu `aud=orders-api`. Audience validation độc lập với chữ ký và issuer.

**Câu 7.** AS đổi issuer từ `https://old-login.example.com` sang `https://login.example.com`. Token cũ có tự chuyển sang issuer mới không?

> Không. Token cũ vẫn mang claim `iss` cũ đã được ký; migration cần kế hoạch cho clients, RS và thời hạn token.

## 22. Tài liệu tham khảo

- [Spring Security — OAuth 2.0 Resource Server JWT (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): `issuer-uri`, discovery, `jwk-set-uri` và issuer/audience validation.
- [Spring Boot — Embedded Web Servers / Running Behind a Front-end Proxy](https://docs.spring.io/spring-boot/how-to/webserver.html): `server.forward-headers-strategy` và hỗ trợ proxy.
- [Spring Framework — Forwarded Headers / ForwardedHeaderFilter](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html): xử lý `Forwarded`, `X-Forwarded-*` và trust-boundary security.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): `AuthorizationServerSettings` và issuer configuration.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): Provider Configuration, issuer và metadata.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): metadata discovery và cách ghép well-known URL với issuer có path.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): claim `iss`, `aud`, `exp`.
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): kiểm tra issuer/audience, nguồn khóa và tránh token confusion.
- [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239): header `Forwarded` khi request qua proxy.

Trong một hệ thống có reverse proxy, **public issuer là hợp đồng danh tính**, còn **internal URL là chi tiết triển khai mạng**. Giữ `iss` trong JWT, `issuer` trong metadata và `issuer-uri` của Resource Server nhất quán; giải quyết những khác biệt về routing bằng proxy, DNS, forwarded headers hoặc nguồn JWKS nội bộ đáng tin, thay vì nới lỏng việc xác minh token.
