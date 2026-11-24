# Trusted proxies và đường dẫn công khai sau nhiều lớp proxy

## 1. Vì sao Gateway cần hiểu URL công khai?

Trong kiến trúc microservices, **Spring Cloud Gateway** là điểm vào chịu trách nhiệm route predicate, filter chain, biến đổi path/header, service discovery, xác thực, giới hạn lưu lượng, circuit breaker, retry, TLS và quan sát request. Khi triển khai thực tế, Gateway thường không trực tiếp tiếp nhận TCP/TLS connection từ Internet: phía trước còn CDN, WAF, load balancer, ingress hoặc reverse proxy.

Ví dụ một người dùng gọi:

~~~http
GET https://api.example.test/platform/api/orders/42?lang=vi
~~~

Nhưng từng hop có thể nhìn thấy đường dẫn và scheme khác nhau:

~~~text
Browser
  https://api.example.test/platform/api/orders/42
       |
       v
CDN / WAF
  public host = api.example.test; TLS từ client
       |
       v
Ingress / Nginx
  strip /platform
       |
       v
Spring Cloud Gateway WebFlux
  http://edge-gateway:8080/api/orders/42
  Path=/api/orders/**; StripPrefix=1
       |
       v
order-service
  http://order-service:8081/orders/42
~~~

Nếu Gateway và backend chỉ nhìn vào địa chỉ nội bộ, hệ thống có thể tạo ra `Location: http://order-service:8081/orders/42` thay vì URL public, redirect từ HTTPS sang HTTP, sinh callback OAuth2/OIDC sai, hoặc đặt cookie Path không khớp public prefix. Nếu tin các header `Forwarded`/`X-Forwarded-*` do một client tự khai báo, lỗi còn có thể trở thành **bypass IP allowlist/rate limiting, host-header poisoning hoặc open redirect**.

Bài **“Trusted proxies và đường dẫn công khai sau nhiều lớp proxy”**, thuộc chương **Triển khai** của module **SPRING_CLOUD_GATEWAY**, giải thích cách quản lý những vấn đề này như một **hợp đồng giữa các hop** thay vì một danh sách cấu hình rời rạc.

**Mục tiêu học tập:**

1. Lập bản đồ các proxy hops và phân biệt URL client nhìn thấy với URL Gateway/backend nhận.
2. Hiểu `Host`, `Forwarded`, `X-Forwarded-For`, `X-Forwarded-Proto`, `X-Forwarded-Host`, `X-Forwarded-Port` và `X-Forwarded-Prefix`.
3. Đặt ranh giới tin cậy tại đúng proxy, loại bỏ headers do client giả mạo.
4. Cấu hình Gateway WebFlux `trusted-proxies` đúng namespace theo version, phân biệt với Spring Boot `server.forward-headers-strategy`.
5. Giải quyết strip prefix, public redirects, Location, cookies, OAuth callback, forwarded client IP.
6. Kiểm thử full chain và tránh regression khi nâng cấp bản vá bảo mật.

> **Phạm vi:** ví dụ chính dùng **Spring Cloud Gateway Server WebFlux**. Gateway Server Web MVC chạy Servlet/WebMvc.fn, có filter/properties cùng ý tưởng nhưng khác namespace và API Java. Khi chuyển runtime, đừng chỉ đổi tên starter rồi copy nguyên cấu hình reactive.

## 2. Các địa chỉ khác nhau của cùng một request

| Điểm nhìn | Scheme / Host | Path | Vai trò |
| --- | --- | --- | --- |
| Client | `https://api.example.test` | `/platform/api/orders/42` | **URL công khai**, cần dùng trong links |
| CDN/WAF | Public origin được validate | `/platform/api/orders/42` | Ranh giới internet |
| Ingress nhận | Tùy routing/TLS topology | `/platform/api/orders/42` | Bỏ `/platform` |
| Gateway nhận | `http://edge-gateway:8080` | `/api/orders/42` | Route predicate |
| Backend nhận | `http://order-service:8081` | `/orders/42` | Business handler |
| Client nhận redirect | `https://api.example.test` | `/platform/api/orders/42` | Không lộ internal host/path |

**Phải tách ba thứ:** địa chỉ public, request path thực tế mỗi hop và response URL phải gửi về client. Một header `X-Forwarded-Prefix` không có nghĩa Gateway tự sửa mọi response links đúng như bảng trên.

### 2.1. TLS theo từng chặng

~~~text
Client --TLS A--> CDN --TLS B hoặc HTTP--> Ingress
       --HTTP/TLS C--> Gateway --HTTP/TLS D--> Backend
~~~

`X-Forwarded-Proto: https` thường mô tả scheme bên ngoài, **không chứng minh** Gateway → backend đang mã hóa. Nếu cần TLS/mTLS ở nội bộ, phải cấu hình SSL trust, certificate verification, SNI và service identity riêng. Inbound HTTPS không tự bảo đảm outbound HTTPS.

### 2.2. URL theo người dùng và URL theo transport

Client có thể nhìn `https://api.example.test`, trong khi Reactor Netty của Gateway nhận socket từ ingress và thấy `http://10.42.0.10:8080`. Cả hai đều có thể đúng cho mục đích riêng. Sai lầm bắt đầu khi ứng dụng dùng transport scheme/host để tạo public URL, hoặc ngược lại dùng host công khai chưa xác thực để xác định backend target.

## 3. Hai họ header nói về proxy chain

### 3.1. RFC 7239 Forwarded

Ví dụ:

~~~http
Forwarded: for=203.0.113.44;proto=https;host=api.example.test
~~~

| Tham số | Ý nghĩa thường gặp |
| --- | --- |
| `for` | Danh tính địa chỉ client hoặc proxy trước hop hiện tại |
| `proto` | Scheme bên ngoài được proxy ghi nhận |
| `host` | Host của request được forward |
| `by` | Địa chỉ/giao diện proxy xử lý hop, nếu bật |

Qua nhiều hops, `Forwarded` có thể chứa nhiều phần tử, phân tách bằng dấu phẩy:

~~~http
Forwarded: for=203.0.113.44;proto=https;host=api.example.test, for=198.51.100.10;proto=https;host=api.example.test
~~~

RFC cho phép quoted strings, IPv6 trong ngoặc vuông, giá trị `unknown` và dạng obfuscated identifiers. Không tự viết parser bằng `split(",")` rồi xem như đủ cho mọi định dạng.

### 3.2. X-Forwarded-* phổ biến hơn ở nhiều hạ tầng

~~~http
Host: edge-gateway.internal
X-Forwarded-For: 203.0.113.44, 198.51.100.10
X-Forwarded-Proto: https
X-Forwarded-Host: api.example.test
X-Forwarded-Port: 443
X-Forwarded-Prefix: /platform
~~~

| Header | Giải quyết | Rủi ro nếu tin sai |
| --- | --- | --- |
| `X-Forwarded-For` | Đường đi IP client/proxies | Fake IP để vượt quota/allowlist |
| `X-Forwarded-Proto` | Scheme public | HTTP redirect, cookie Secure sai |
| `X-Forwarded-Host` | Public host | Host poisoning, open redirect |
| `X-Forwarded-Port` | Port public | Link có `:8080`, scheme/port lệch |
| `X-Forwarded-Prefix` | Prefix bị strip ở hop trước | 404, double prefix hoặc path injection |
| `Forwarded` | Metadata chuẩn gộp | Parse/priority mâu thuẫn với X-Forwarded |

Headers là **thông tin do một bên gửi HTTP cung cấp**, không phải credential. Client từ Internet cũng có thể tự đặt các giá trị trên.

### 3.3. Host hiện tại và X-Forwarded-Host không đồng nhất

- `Host` có thể là authority của hop HTTP hiện tại hoặc host giữ lại theo proxy configuration.
- `X-Forwarded-Host` có ý định biểu diễn original/public authority.
- HTTP client của Gateway có thể đặt Host theo target URI tới backend, trừ khi dùng filter preserve/set host.
- Nếu có `Host=evil.example` do client tự chọn, một Host predicate match cũng **không phải xác thực người dùng**.

## 4. Ranh giới tin cậy: vệ sinh trước khi tin

### 4.1. Quy tắc cốt lõi

**Proxy đầu tiên thuộc miền tin cậy** phải được thiết kế để:

1. Nhận request từ Internet hoặc một nguồn có mức tin cậy thấp hơn.
2. **Xóa hoặc ghi đè cả `Forwarded` và họ `X-Forwarded-*` do client có thể gửi**.
3. Tạo lại scheme/host/port/prefix từ TLS listener, validated hostname, route mapping và remote peer thực tế.
4. Chỉ chuyển metadata đã chuẩn hóa tới các hops được phép kết nối.
5. Giới hạn header sizes, hop counts và xử lý chuỗi malformed.
6. Áp dụng host allowlist, network ACL và TLS policy riêng.

Bỏ mỗi `Forwarded` nhưng để `X-Forwarded-Host: evil.example`, hoặc chỉ làm ngược lại, vẫn còn bề mặt tấn công tương tự. Spring Framework và Spring Security đều nhấn mạnh làm sạch **cả hai họ** ở trusted boundary.

### 4.2. Minh họa một client giả mạo

~~~http
GET /login HTTP/1.1
Host: api.example.test
Forwarded: for=10.0.0.1;proto=http;host=evil.example
X-Forwarded-Host: evil.example
X-Forwarded-Proto: http
X-Forwarded-Prefix: /admin
~~~

Nếu app xây callback/redirect từ giá trị chưa được xác minh, nó có thể trả:

~~~http
HTTP/1.1 302 Found
Location: http://evil.example/admin/oauth2/callback
~~~

Đây là **phản ví dụ nguy hiểm**. Kết quả hợp lệ phải sử dụng public origin/prefix thuộc allowlist hoặc từ chối request. Không nên test bằng cách chỉ xem HTTP 200; cần assert `Location`, backend headers, client IP được suy ra và security decision.

### 4.3. Ba lớp bảo vệ bổ sung nhau

| Lớp | Mục đích | Không thay được |
| --- | --- | --- |
| Network ACL / Kubernetes NetworkPolicy / SecurityGroup | Chỉ cho ingress được kết nối đến Gateway | Không sửa headers |
| Ingress/CDN header sanitization | Loại header giả, tạo metadata đáng tin | Không thay auth backend |
| Gateway/Spring trusted forwarded processing | Dùng/forward đúng dữ liệu đã được tin | Không chặn direct NodePort bypass |

**Không có property nào trong Gateway tự biến mọi port 8080 thành private network.** Một NodePort hoặc public LoadBalancer bên cạnh ingress có thể là đường bypass mà attacker gửi trực tiếp `X-Forwarded-Host` tới Gateway.

### 4.4. Định nghĩa tin cậy dựa trên nguồn

Một chuỗi đáng tin có thể là:

~~~text
Client -> CDN/WAF -> Ingress (sanitize) -> Gateway (private) -> Service
~~~

Nhưng nếu CDN là một hop đã trusted còn ingress chấp nhận traffic bypass CDN, việc dùng header client IP từ CDN mà **không xác minh peer là CDN** tạo lỗ hổng. Tin cậy phải có cả network/source identity và contract về headers.

## 5. Spring Cloud Gateway WebFlux trusted-proxies

### 5.1. Nhánh 4.3/5.x theo namespace mới

Tài liệu Gateway Server WebFlux 5.x liệt kê property:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          trusted-proxies: '^10[.]42[.]0[.](?:10|11)$'
~~~

Đây là **Java regular expression** mô phỏng hai proxy identities `10.42.0.10` và `10.42.0.11`, không phải CIDR. Giá trị này **không tự whitelist socket remote IP** và không thay mạng private/ACL. Nếu forwarded metadata thực tế có port, IPv6, quotes hoặc hình thức khác, phải kiểm cách regex được matcher của version Gateway áp dụng và chỉnh phù hợp.

Tài liệu `HttpHeadersFilters` mô tả `trusted-proxies` là cấu hình cần thiết để kích hoạt xử lý `Forwarded` và `X-Forwarded-*` ở HTTP outbound header filters. Những tùy chọn tương ứng gồm:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          x-forwarded:
            for-enabled: true
            host-enabled: true
            proto-enabled: true
            port-enabled: true
            prefix-enabled: true
            for-append: true
            host-append: true
            proto-append: true
            port-append: true
            prefix-append: true
~~~

Đoạn trên là **bảng knobs minh họa**, không phải một baseline production nên copy nguyên. Trong một số phiên bản, các cờ trên mặc định true, nhưng patch/security advisory có thể thay đổi hành vi và điều kiện kích hoạt filters. **Append không an toàn nếu chuỗi cũ có phần tử client tự ghi và chưa được sanitize.**

Một số cờ tổng thể được liệt kê trong configprops:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          forwarded:
            enabled: true
          x-forwarded:
            enabled: true
~~~

Đây là các cờ tính năng, **không phải lệnh tin mọi request header**. Chỉ sử dụng với proxy chain đáng tin và kiểm chứng bản vá.

### 5.2. Nhánh 4.1/4.2 hoặc 4.3 namespace cũ

Ở nhiều release trước:

~~~yaml
spring:
  cloud:
    gateway:
      trusted-proxies: '^10[.]42[.]0[.](?:10|11)$'
      x-forwarded:
        for-enabled: true
        host-enabled: true
        proto-enabled: true
        prefix-enabled: true
~~~

| Dòng cấu hình | Property trusted proxies |
| --- | --- |
| Gateway Server WebFlux 4.1/4.2 | `spring.cloud.gateway.trusted-proxies` |
| Gateway 4.3 giai đoạn migration | Namespace được artifact/version đang chạy hỗ trợ |
| Gateway Server WebFlux 5.x | `spring.cloud.gateway.server.webflux.trusted-proxies` |
| Gateway Server Web MVC 5.x | `spring.cloud.gateway.server.webmvc.trusted-proxies` |

Không đặt hai property/route namespaces song song để “chắc ăn”. Điều đó có thể tạo cấu hình khác với điều người vận hành tưởng đã bật.

### 5.3. Regex không phải CIDR

~~~yaml
# PHẢN VÍ DỤ: không viết chuỗi CIDR rồi giả định Java regex hiểu subnet.
trusted-proxies: '10.42.0.0/24'

# PHẢN VÍ DỤ: quá rộng, dễ làm mất ý nghĩa trust boundary.
trusted-proxies: '.*'
~~~

Hãy dùng một regex giới hạn chính xác các proxy identities được biểu diễn trong forwarded headers, kiểm soát direct network access bằng ACL riêng và viết integration tests với format thực của header.

## 6. Cảnh báo bảo mật đã được Spring công bố

### 6.1. CVE-2025-41235, công bố 27/05/2025

Spring công bố lỗi **Gateway Server forwards headers from untrusted proxies**. Các khoảng phiên bản được nêu bao gồm:

- 4.2.0–4.2.2; bản sửa OSS 4.2.3.
- 4.1.0–4.1.7; bản sửa OSS 4.1.8.
- Một số nhánh 4.0.x và 3.1.x theo advisory.

Bản sửa điều chỉnh hành vi mặc định của forwarded-header functionality; để bật cần cấu hình trusted proxies phù hợp. Không coi cài một regex là tương đương cập nhật bản vá.

Nguồn: [Spring Security Advisory CVE-2025-41235](https://spring.io/security/cve-2025-41235/).

### 6.2. CVE-2026-47825, công bố 11/06/2026

Spring công bố lỗi **chuyển tiếp `X-Forwarded-For`/`Forwarded` từ untrusted proxies trong một số cấu hình**, ảnh hưởng Server WebFlux **và** WebMVC.

| Khoảng phiên bản bị ảnh hưởng theo advisory | Bản sửa được Spring liệt kê |
| --- | --- |
| 5.0.0–5.0.1 | 5.0.2 (OSS) |
| 4.3.0–4.3.4 | 4.3.5 (OSS) |
| 4.2.0–4.2.8 | 4.2.9 (Enterprise Support) |
| 4.1.0–4.1.12 | 4.1.13 (Enterprise Support) |
| Các nhánh cũ hơn | Xem advisory và kế hoạch nâng cấp |

Theo advisory, bản sửa đã **tắt `NettyServerCustomizer` của Gateway Server WebFlux theo mặc định**. Nếu một ứng dụng cần bật lại customizer theo release 5.0.x hoặc 4.3.x đã migrate namespace, property là:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          httpserver:
            customizer-enabled: true
~~~

**Không bật tùy chọn trên như bước mặc định.** Đây chỉ là cách khôi phục chức năng khi đã hiểu tác động, có threat model và kiểm thử. Ở namespace cũ, advisory nêu `spring.cloud.gateway.httpserver.customizer-enabled`; kiểm bản cài đặt trước khi dùng.

Nguồn: [Spring Security Advisory CVE-2026-47825](https://spring.io/security/cve-2026-47825/).

**Bài học vận hành:** cập nhật bản sửa được hỗ trợ, kiểm tra lại forwarding behavior và regression tests sau nâng cấp. Patch/security advisory là một phần quan trọng của deployment, không phải chi tiết có thể bỏ qua.

## 7. Spring Boot forward-headers-strategy ở tầng inbound

Gateway HttpHeadersFilters xử lý headers **trước HTTP call xuống backend**. Spring Boot/Spring Framework còn có một cơ chế **đọc forwarded metadata khi request đi vào chính Gateway**.

### 7.1. Các lựa chọn trong Boot 3.x

| Giá trị `server.forward-headers-strategy` | Mục đích |
| --- | --- |
| `NONE` | Không áp dụng forwarded metadata qua auto-configuration của Boot |
| `NATIVE` | Nhờ HTTP server thực thi cơ chế native phù hợp |
| `FRAMEWORK` | Dùng Spring Framework, với WebFlux là `ForwardedHeaderTransformer` |

Ví dụ chỉ trong môi trường **trusted ingress đã vệ sinh headers**:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

`ForwardedHeaderTransformer` có thể điều chỉnh thông tin scheme, host, port và prefix mà Spring WebFlux thấy, đồng thời xử lý/loại các header đã dùng. Ở Servlet MVC, cơ chế tương ứng là `ForwardedHeaderFilter` hoặc cấu hình native của Tomcat/Jetty.

**Nếu Gateway public port có thể bị client Internet gọi trực tiếp và gửi forwarded headers tùy ý, không bật FRAMEWORK rồi xem nó an toàn.** Phải có network boundary.

### 7.2. Inbound transformer khác outbound filter

~~~text
Ingress HTTP request
  -> Boot/Framework forwarded handling:
       diễn giải effective scheme/host/port/prefix
  -> Gateway route predicate/filter chain:
       chọn route, strip/rewrite path
  -> Gateway HttpHeadersFilters:
       tạo/điều chỉnh forwarded headers outbound
  -> HTTP client đến backend
~~~

Khi Spring Framework đã áp dụng rồi loại bỏ incoming headers, Gateway có thể tạo outbound headers từ request đã biến đổi. Nếu ingress và Gateway mỗi nơi tự prepend prefix hoặc append một chuỗi khác nhau, kết quả dễ bị double-prefix, sai proto hoặc header không nhất quán.

Thiết kế:

1. Xác định proxy nào sinh và làm sạch headers.
2. Quyết định Boot có cần thay đổi effective request URI không.
3. Quyết định Gateway có cần gửi forwarded metadata xuống backend không.
4. Test `request.getURI()`, route matching và backend recorded headers theo đúng patch.
5. Không đăng ký custom transformer rồi vẫn kỳ vọng default auto-configuration hành xử như cũ.

### 7.3. removeOnly khi hoàn toàn không muốn dùng headers

Spring WebFlux có chế độ `ForwardedHeaderTransformer.setRemoveOnly(true)`, tức là **loại headers chứ không áp dụng chúng**:

~~~java
package example.gateway.deployment;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.server.adapter.ForwardedHeaderTransformer;

@Configuration
class DiscardForwardedHeaders {

    @Bean
    ForwardedHeaderTransformer forwardedHeaderTransformer() {
        ForwardedHeaderTransformer transformer =
                new ForwardedHeaderTransformer();
        transformer.setRemoveOnly(true);
        return transformer;
    }
}
~~~

Đây là **phương án thay thế**, không phải cấu hình cần thêm cùng `FRAMEWORK` để “tăng bảo mật”. Nếu ứng dụng cần phục hồi public origin dựa trên trusted headers, removeOnly sẽ cố ý **không sử dụng** thông tin đó. Hãy chọn một chính sách duy nhất, không chồng nhiều cơ chế rồi hy vọng các kết quả tự nhất quán.

### 7.4. Spring Boot 4.x có thêm điểm cần đối chiếu

Tài liệu Spring Boot 4.x bổ sung nhóm property `server.request.header.forwarded.*` và một số tùy chọn liên quan prefix. Không mặc định mọi property/hành vi của Boot 3.x giữ nguyên khi đổi phiên bản. Cần đối chiếu các docs về **Running Behind a Front-end Proxy Server** và kiểm tra effective configuration/startup.

## 8. Ví dụ Nginx ở biên TLS, không có CDN phía trước

### 8.1. Hợp đồng

Trong ví dụ này, **Nginx chính là proxy công khai đầu tiên**:

- Public: `https://api.example.test/platform/api/orders/42`.
- Nginx strip `/platform` và gửi `http://edge-gateway:8080/api/orders/42`.
- Gateway strip `/api` và gọi `http://order-service:8081/orders/42`.
- Nginx là nguồn sinh các forwarded headers được ứng dụng tin.

### 8.2. Nginx config minh họa

~~~nginx
# RÚT GỌN CHO LAB; chưa gồm hardening TLS, rate limit,
# security headers, host validation, logging/monitoring và timeouts.
server {
    listen 443 ssl;
    server_name api.example.test;

    ssl_certificate     /etc/nginx/certs/server.crt;
    ssl_certificate_key /etc/nginx/certs/server.key;

    location /platform/ {
        # Dấu / sau proxy_pass làm Nginx thay /platform/ bằng /.
        proxy_pass http://edge-gateway:8080/;
        proxy_http_version 1.1;

        # Không cho client tự định nghĩa Forwarded.
        proxy_set_header Forwarded "";

        # Ghi đè metadata từ sự thật đã biết ở public edge.
        proxy_set_header Host api.example.test;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Host api.example.test;
        proxy_set_header X-Forwarded-Port 443;
        proxy_set_header X-Forwarded-Prefix /platform;
    }
}
~~~

**Các giới hạn quan trọng:**

- Không dùng snippet này như **Nginx production config hoàn chỉnh**. Cần TLS policy, default host rejection, trusted network, header allowlist/sanitize toàn diện, timeouts và limits.
- Nginx có thể pass những headers chưa được liệt kê. Phải kiểm các header tùy biến cùng họ forwarded nếu backend tiêu thụ chúng.
- `$remote_addr` là peer mà Nginx nhìn thấy. Nếu có CDN phía trước thì đó có thể chỉ là **địa chỉ CDN**; không tùy tiện coi là client IP gốc.
- `X-Forwarded-Prefix` đáng tin ở đây vì Nginx **tự đặt** giá trị cố định dựa trên mapping, không dùng giá trị client gửi.
- Cú pháp `proxy_pass http://edge-gateway:8080/;` có trailing slash trong `location /platform/` sẽ làm thay prefix location theo quy tắc Nginx. Nếu sửa slash, hãy chạy lại path tests.

## 9. Gateway route theo cùng public mapping

### 9.1. Gateway Server WebFlux 5.x

~~~yaml
server:
  port: 8080
  forward-headers-strategy: framework

spring:
  application:
    name: edge-gateway
  cloud:
    gateway:
      server:
        webflux:
          trusted-proxies: '^10[.]42[.]0[.](?:10|11)$'
          routes:
            - id: orders-api
              uri: http://order-service:8081
              predicates:
                - Path=/api/orders/**
              filters:
                - StripPrefix=1
~~~

Mô hình kỳ vọng:

~~~text
Client:  GET /platform/api/orders/42  [HTTPS public]
Nginx:   GET /api/orders/42           [HTTP nội bộ]
Gateway: route orders-api
Backend: GET /orders/42               [HTTP nội bộ]
~~~

Regex IP ở đây chỉ là **placeholder** cho proxy identities thật; nó không tự cấu hình Nginx IP/routing. Vì Boot xử lý forwarded headers có thể điều chỉnh request URI/prefix trước route predicates, hãy kiểm **route path nhận thực tế** trên version đang chạy. Không coi đoạn YAML + Nginx trên là test PASS trước khi chạy thử.

### 9.2. Gateway WebFlux 4.x dùng namespace cũ

~~~yaml
server:
  port: 8080
  forward-headers-strategy: framework

spring:
  cloud:
    gateway:
      trusted-proxies: '^10[.]42[.]0[.](?:10|11)$'
      routes:
        - id: orders-api
          uri: http://order-service:8081
          predicates:
            - Path=/api/orders/**
          filters:
            - StripPrefix=1
~~~

Hai cấu hình là **biến thể thay thế**. Ở 4.3 có migration namespace tùy version; hãy kiểm runtime/property binding trước khi chọn.

### 9.3. URI backend không chứng minh có service discovery hoặc TLS

`uri: http://order-service:8081` mô tả một HTTP target cụ thể. Nếu dùng `lb://ORDER-SERVICE`, LoadBalancer cần service instances thực và có scheme/security policy tương ứng. Forwarded headers **không** thay mTLS hoặc authorization downstream.

## 10. X-Forwarded-Prefix và ba phép biến đổi khác nhau

### 10.1. Ingress rewrite, Gateway rewrite và URL reconstruction

| Công cụ | Tác động |
| --- | --- |
| Nginx `proxy_pass` / ingress rewrite | Thay path mà Gateway **thực sự nhận** |
| Gateway `StripPrefix` / `RewritePath` | Thay path mà backend **thực sự nhận** |
| `X-Forwarded-Prefix` | Metadata về prefix public đã bị proxy ở trước loại bỏ |
| Response `Location` rewrite / public base URL | Quyết định link/redirect mà client nhìn thấy |

`X-Forwarded-Prefix` **không phải lệnh tự động prepend prefix vào mọi outbound request hoặc redirect**.

### 10.2. Double strip

~~~text
Public:         /platform/api/orders/42
Ingress lỡ bỏ:  /platform/api  -> /orders/42
Gateway còn:    Path=/api/orders/**  -> không match
~~~

Hoặc nếu Gateway dùng route rộng và vẫn `StripPrefix=1`, path `/orders/42` bị đổi thành `/42`, backend 404.

Giải pháp: trong topology mẫu, ingress **chỉ bỏ `/platform`**, Gateway **chỉ bỏ `/api`**.

### 10.3. Double prefix

~~~text
Backend đã sinh: /platform/api/orders/42
Gateway lỡ thêm: /platform/platform/api/orders/42
~~~

Không append `X-Forwarded-Prefix` vào mọi link một cách mù quáng. Cần xét redirect relative/absolute, path đã encode, prefix rỗng, slash kép, nhiều routes và các hops khác đã rewrite.

### 10.4. Cần có bảng path ở ranh giới mỗi hop

| Client | Nginx → Gateway | Gateway → backend |
| --- | --- | --- |
| `/platform/api/orders/42` | `/api/orders/42` | `/orders/42` |
| `/platform/api/orders/42?x=1` | `/api/orders/42?x=1` | `/orders/42?x=1` |
| `/platform/api/orders/42/items` | `/api/orders/42/items` | `/orders/42/items` |
| `/platform/api/orders-old/42` | `/api/orders-old/42` | Không match orders route |
| `/platform/platform/api/orders/42` | Không đúng contract | Không auto-fix bằng double-strip |

Các giá trị là **kỳ vọng cần kiểm thử**, không phải kết quả đo đã có.

## 11. Khi có CDN phía trước ingress

~~~mermaid
flowchart LR
    C["Client<br/>203.0.113.44"] --> CDN["CDN/WAF<br/>198.51.100.10"]
    CDN --> ING["Ingress<br/>192.0.2.20"]
    ING --> G["Spring Cloud Gateway"]
    G --> O["order-service"]
~~~

Các địa chỉ trên thuộc **dải IP ví dụ dùng trong tài liệu**, không phải IP thực.

### 11.1. Vì sao $remote_addr có thể không phải client IP?

Nếu CDN kết nối tới Nginx, `$remote_addr` mà Nginx nhận có thể là `198.51.100.10`, không phải `203.0.113.44`. Dùng cấu hình tại mục 8 khi có CDN sẽ **mất client IP gốc**, dù nó còn tránh tin XFF giả từ client.

Nếu cần original client IP:

1. Chỉ cho những IP ranges đã xác minh của CDN kết nối vào ingress.
2. Xác định đúng header provider ghi client IP.
3. Chỉ chấp nhận header đó khi **transport peer** thuộc tập CDN được phép.
4. Cấu hình Nginx real-IP/trusted proxy module theo version và cập nhật IP ranges.
5. Sau khi resolve, tạo `X-Forwarded-For` sạch theo một owner.
6. Test cả đường đi qua CDN và bypass CDN.

**Không cấu hình `set_real_ip_from 0.0.0.0/0` hoặc tin XFF của mọi peer.**

### 11.2. Append không chữa dữ liệu bị giả

Phản ví dụ:

~~~http
# Attacker gửi:
X-Forwarded-For: 10.0.0.1

# Một proxy chỉ append:
X-Forwarded-For: 10.0.0.1, 203.0.113.44
~~~

Ứng dụng đọc phần tử đầu tiên có thể tưởng client là `10.0.0.1`. **Append chỉ an toàn sau khi các phần tử trước đó đã được xác minh hoặc loại bỏ**.

### 11.3. Forwarded và X-Forwarded-* có thể mâu thuẫn

~~~http
Forwarded: for=203.0.113.44;proto=https;host=api.example.test
X-Forwarded-For: 10.0.0.1
X-Forwarded-Proto: http
X-Forwarded-Host: evil.example
~~~

Không có quy tắc “RFC header luôn thắng” cho mọi implementation. Một service có thể ưu tiên `Forwarded`, service khác ưu tiên `X-Forwarded-*`. Vì vậy hãy chuẩn hóa **cả hai họ tại edge**; khi không dùng một họ, có thể loại bỏ nó theo hợp đồng.

## 12. Public redirects và Location response

### 12.1. Sai scheme/host/port/path đều là lỗi

Backend trả:

~~~http
HTTP/1.1 302 Found
Location: http://order-service:8081/orders/42
~~~

Nhưng client cần thấy:

~~~http
HTTP/1.1 302 Found
Location: https://api.example.test/platform/api/orders/42
~~~

Chỉ đổi host thôi chưa giải quyết missing `/platform/api`. Chỉ thêm prefix chưa sửa `http` thành `https`. Phải phục hồi đầy đủ **scheme + host + port + public path**.

### 12.2. RewriteLocationResponseHeader

Gateway Server WebFlux cung cấp `RewriteLocationResponseHeader` để điều chỉnh `Location`, thường sửa host và xử lý API version.

Ví dụ cú pháp trên Gateway 5.x:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-api
              uri: http://order-service:8081
              predicates:
                - Path=/api/orders/**
              filters:
                - StripPrefix=1
                - RewriteLocationResponseHeader=AS_IN_REQUEST, Location, api.example.test, https?
~~~

`AS_IN_REQUEST` là mode liên quan việc strip phần API version; tham số host dùng thay host trong Location theo semantics của filter. **Đừng xem filter này là lời giải tự động cho mọi scheme/prefix**: nó không hứa dựng `/platform/api` đúng trong mọi response, hoặc ép HTTP thành HTTPS theo mọi topology. Test output thật; nếu cần, cấu hình public URL tại backend hoặc response rewrite bổ sung đã kiểm chứng.

### 12.3. Relative Location vẫn có thể sai prefix

~~~http
Location: /orders/42
~~~

Browser sẽ resolve thành `https://api.example.test/orders/42`, **không tự thêm `/platform/api`**. Nếu contract yêu cầu relative Location, nó nên có public path:

~~~http
Location: /platform/api/orders/42
~~~

### 12.4. Redirect loop và HTTP method

- Một Gateway nội bộ nhận HTTP nhưng client đã ở HTTPS có thể redirect loop nếu app không tin `proto=https` từ trusted proxy.
- `301/302` có lịch sử client đổi POST sang GET theo semantics/UA.
- `307/308` quy định giữ method.
- Test nên **không auto-follow redirect** khi cần kiểm status và `Location` gốc.
- Không dùng arbitrary forwarded host để xây link logout/reset-password/OAuth callback.

## 13. PreserveHostHeader và SetRequestHostHeader có vai trò gì?

### 13.1. Host của backend khác host public

Một HTTP request đi qua Gateway có thể chứa nhiều lớp authority:

~~~text
Client Host:                 api.example.test
Ingress -> Gateway Host:     api.example.test hoặc edge-gateway.internal
Gateway target URI host:     order-service:8081
Backend outbound Host:       theo target hoặc Gateway filter có hiệu lực
~~~

`PreserveHostHeader` là filter Gateway WebFlux yêu cầu sử dụng Host request đã được lưu theo behavior của Gateway. `SetRequestHostHeader` đặt một giá trị Host chủ động cho outbound HTTP call.

~~~yaml
# Chỉ là các lựa chọn cần review, không bật cả hai tùy tiện.
filters:
  - PreserveHostHeader
~~~

hoặc:

~~~yaml
filters:
  - SetRequestHostHeader=orders.internal.example.test
~~~

**Không đồng nhất HTTP Host với TLS SNI hay certificate identity**: HTTP client kết nối đến target URI, còn truststore/SNI/hostname validation có quy tắc riêng. Cần test khi backend có virtual hosts hoặc TLS/mTLS.

### 13.2. PreserveHostHeader có thể làm tăng rủi ro

Nếu ingress không giới hạn Host, việc bảo toàn `Host: evil.example` xuống backend có thể:

- Khiến backend chọn sai virtual host.
- Khiến backend tạo absolute Location trỏ domain giả.
- Phá cookie Domain.
- Làm OAuth2 callback sai.
- Gây cache poisoning nếu cache key phụ thuộc Host.

Vì thế, chỉ preserve public Host **khi nó đã qua host allowlist và network trust boundary**. Với backend chỉ cần target host nội bộ, không cần preserve.

### 13.3. Host route predicate là điều kiện routing, không phải danh tính

Ví dụ:

~~~yaml
predicates:
  - Host=api.example.test
  - Path=/api/orders/**
~~~

Một client có thể điều chỉnh HTTP Host khi trực tiếp kết nối Gateway. Predicate Host không thay xác thực OAuth2/JWT, ownership checks hay mTLS service identity.

## 14. Cookie, session và redirect URI OAuth2/OIDC

### 14.1. Cookie Path phải tương thích public path

Backend trả:

~~~http
Set-Cookie: SID=demo; Path=/orders; HttpOnly; SameSite=Lax
~~~

Browser đang truy cập `https://api.example.test/platform/api/orders/42`. Với Path `/orders`, browser có thể **không gửi cookie** cho đường dẫn public yêu cầu. Một response rewrite phù hợp hoặc backend aware public base path phải tạo Path theo contract.

| Cookie attribute | Kiểm thử |
| --- | --- |
| `Domain` | Có trỏ đúng public domain? Có lộ sang sibling domain? |
| `Path` | Có thuộc đường dẫn public mà browser gửi lại? |
| `Secure` | Có bật cho cookie nhạy cảm trên HTTPS? |
| `HttpOnly` | JavaScript có bị cấm đọc session cookie? |
| `SameSite` | Có phù hợp cross-site SSO/frontend flow? |
| Max-Age/Expires | Có đúng lifecycle session/token? |

`X-Forwarded-Proto=https` không tự đảm bảo cookie an toàn nếu server tin untrusted header, hoặc inbound HTTPS chưa được enforce.

### 14.2. OAuth2/OIDC redirect_uri

Một redirect URI được đăng ký tại IdP có thể là:

~~~text
https://api.example.test/platform/login/oauth2/code/company
~~~

Nếu backend/Gateway xây callback từ internal request URI, nó có thể thành `http://edge-gateway:8080/login/oauth2/code/company` và IdP từ chối. Ngược lại, dùng `X-Forwarded-Host` do attacker giả có thể tạo callback tới domain ngoài allowlist.

Thiết kế:

1. Chỉ sử dụng public base URL từ cấu hình tin cậy hoặc đã được trusted proxy chuẩn hóa.
2. Đăng ký exact redirect URI với IdP theo môi trường.
3. Dùng HTTPS và xác minh host/scheme.
4. Kiểm login flow đầy đủ, `state`, session cookie, CSRF và callback Path.
5. Đối với multi-tenant domains, ánh xạ domain từ allowlist theo tenant đã xác thực, không dùng arbitrary Host header.
6. Đừng log authorization code/access token trong query/Location khi điều tra.

### 14.3. CORS và frontend

CORS `Origin` là dữ liệu cho trình duyệt kiểm soát cross-origin JavaScript, không phải authentication. Swagger/OpenAPI `servers` cũng cần public URL bao gồm prefix. Nếu một OpenAPI document chứa `http://order-service:8081`, frontend có thể tự gọi nhầm host nội bộ hoặc báo lỗi mixed content.

Trước khi công bố docs/API client SDK, test cả:

- Public OpenAPI server URL.
- Redirect từ `/docs`.
- CORS preflight `OPTIONS` và credentials policy.
- Cookies ở browser.
- WebSocket public `wss://` nếu có nâng cấp kết nối.
- Không tiết lộ IP/host nội bộ trong body và headers.

## 15. X-Forwarded-For và client IP: hai resolver khác nhau

### 15.1. RemoteAddr mặc định nhìn TCP peer

Ở Gateway WebFlux, `RemoteAddr` route predicate dùng remote address theo request. Khi Gateway ngồi sau ingress, giá trị này thường là **IP ingress** thay vì IP browser.

Spring Cloud Gateway còn cung cấp `XForwardedRemoteAddressResolver` để chọn IP từ `X-Forwarded-For`.

### 15.2. trustAll không an toàn

~~~java
import org.springframework.cloud.gateway.support.ipresolver.XForwardedRemoteAddressResolver;

// PHẢN VÍ DỤ: có thể chọn phần tử đầu do attacker tự gửi.
XForwardedRemoteAddressResolver unsafe =
        XForwardedRemoteAddressResolver.trustAll();

// Ví dụ có chọn số hop trusted, cần xác minh topology thực tế.
XForwardedRemoteAddressResolver controlled =
        XForwardedRemoteAddressResolver.maxTrustedIndex(2);
~~~

`trustAll()` chọn phần tử đầu; nó dễ bị giả mạo nếu XFF chưa được sanitize. `maxTrustedIndex(n)` chọn phần tử từ **bên phải sang** theo index và giả định về chuỗi proxy đã trusted.

Ví dụ header:

~~~http
X-Forwarded-For: 203.0.113.44, 198.51.100.10, 192.0.2.20
~~~

| maxTrustedIndex | Kết quả theo ví dụ |
| --- | --- |
| `1` | `192.0.2.20` |
| `2` | `198.51.100.10` |
| `3` | `203.0.113.44` |

**Không mặc định chọn 3 vì sơ đồ có ba proxy boxes.** Header có thể được xây khác nhau, có thể thiếu phần tử, hoặc client đã chèn phần tử giả. Nên test đúng chuỗi do hạ tầng thật tạo, đếm những trusted hops thực, và không tin phần tử trái nhất ngoài policy.

### 15.3. maxTrustedIndex khác trusted-proxies

| Cơ chế | Mục đích | Kiểu đầu vào |
| --- | --- | --- |
| `trusted-proxies` | Điều kiện xử lý/forward trusted metadata trong Gateway HttpHeadersFilters | Java regular expression |
| `XForwardedRemoteAddressResolver.maxTrustedIndex(n)` | Chọn địa chỉ từ chuỗi XFF | Số hop/index |
| `RemoteAddr` | So remote address với danh sách | CIDR ranges |
| NetworkPolicy/firewall | Chặn kết nối vào Gateway | IP/network/service identity |

**Không dùng resolver để thay edge sanitization**; cũng không dùng trusted-proxies regex để quyết định mọi kết nối TCP được phép.

### 15.4. IP không phải authentication

Ngay khi lấy đúng client IP:

- Nhiều người dùng có thể chia sẻ IP qua NAT.
- Mobile IP có thể thay đổi trong phiên.
- Proxy chain thay đổi làm log/rate-limit key drift.
- IP không chứng minh tenant/ownership trên resource.

Với authenticated APIs, rate-limit key nên dựa vào principal hoặc tenant được xác minh; client IP có thể là signal bổ sung cho abuse prevention.

## 16. Ảnh hưởng đến rate limiting, auditing và tracing

### 16.1. Rate limiting theo IP giả có thể bị bypass

Nếu KeyResolver đọc thẳng header trái nhất:

~~~http
X-Forwarded-For: 203.0.113.1
~~~

attacker có thể thay thành `203.0.113.2` ở request tiếp theo để tránh quota nếu edge không sanitize. Ngược lại, nếu key luôn là ingress IP, tất cả users chung một bucket và dễ bị 429 tập thể.

Phương án đúng:

1. Dùng authenticated principal/tenant khi có.
2. Với unauthenticated traffic, dùng client IP đã được xác minh qua chain.
3. Không tin `X-Client-IP` hoặc `X-Forwarded-For` do client trực tiếp gửi.
4. Test Redis buckets và rate-limit behavior dưới nhiều principals/IP.
5. Khi CDN/ingress đổi, chạy lại tests để phát hiện thay đổi selected client IP.

### 16.2. Phân biệt transportRemoteIp và derivedClientIp

Một log schema **minh họa**, đã giảm dữ liệu nhạy cảm:

~~~text
routeId=orders-api
transportPeer=ingress
derivedClientIpCategory=external
publicHost=api.example.test
publicProto=https
publicPrefix=/platform
status=200
~~~

Không dump raw cookie, authorization, query chứa tokens hoặc toàn bộ XFF chain vào application logs nếu không thật sự cần. IP addresses có thể là dữ liệu cá nhân theo chính sách/luật áp dụng; quản lý retention, access control và redaction.

### 16.3. Trace context độc lập với forwarding headers

W3C `traceparent` giúp nối traces Gateway → microservice, nhưng nó không xác nhận client IP, Host, public Proto hoặc quyền truy cập. Một attacker cũng có thể tự tạo một traceparent hợp lệ.

Do đó:

- Tracing không thay security.
- Forwarded headers không thay trace propagation.
- Rate limiting không được dựa vào baggage/client trace ID.
- Thay đổi proxy chain cần test cả tracing header injection lẫn public URL reconstruction.

## 17. Bảo mật network, TLS và các lớp ứng dụng

### 17.1. Không để ingress là con đường duy nhất “trên sơ đồ”

Trong Kubernetes, cần kiểm:

- Gateway Service có type phù hợp, không có public LoadBalancer/NodePort ngoài dự kiến.
- NetworkPolicy cho phép ingress controller đến Gateway, ngăn sources khác.
- Cloud firewall/SecurityGroup điều khiển cổng công khai.
- Direct pod IP access và service mesh bypass paths.
- DNS/service discovery và mTLS identities, nếu sử dụng.
- Management/Actuator endpoints không public qua routes không kiểm soát.

Ngay cả nếu NetworkPolicy có mặt, phải xác nhận CNI thực sự enforce policy và có quy tắc default-deny phù hợp.

### 17.2. Public HTTPS và outbound HTTPS độc lập

Một request có `X-Forwarded-Proto: https` có thể đi qua chặng Gateway → backend bằng `http://`. Nếu policy yêu cầu outbound TLS:

- Đặt route target `https://` hoặc service instance secure tương ứng.
- Cấu hình trust store/certificate bundle.
- Kiểm hostname validation/SNI.
- Có client certificate/mTLS nếu service identity yêu cầu.
- Không dùng insecure trust manager trong production.

HSTS nên được trả ở public HTTPS boundary theo chính sách domain, không cần backend phỏng đoán scheme dựa trên header bất kỳ.

### 17.3. WebSocket, HTTP/2 và gRPC

Với WebSocket, public `wss://` có thể được chuyển sang `ws://` hoặc TLS backend riêng. Upgrade headers có HTTP semantics đặc biệt; proxy chain phải hỗ trợ Upgrade/Connection theo cấu hình websocket routing đúng version.

HTTP/2 và gRPC dùng pseudo-headers/authority khác HTTP/1.1; forwarded headers không được hiểu như một cách chung để thay SNI và gRPC authority. Thử routing/headers với giao thức thật, không dùng chỉ một curl HTTP/1.1 làm bằng chứng cho WebSocket/gRPC.

## 18. Kiểm thử full proxy chain: ba ranh giới quan sát

Một integration test tốt thu được:

1. **Client response:** status, `Location`, `Set-Cookie`, HTML/JSON absolute links.
2. **Gateway view:** route ID, effective scheme/host/prefix, path sau ingress.
3. **Mock backend recorded request:** method/path/query, Host, `Forwarded` và `X-Forwarded-*`.

~~~mermaid
flowchart LR
    T["Test Client"] --> P["Nginx/Envoy test ingress"]
    P --> G["Gateway WebFlux"]
    G --> B["MockWebServer / WireMock"]
    B --> A["RecordedRequest assertions"]
    G --> T
    T --> R["Response assertions"]
~~~

Unit tests chỉ mock một `ServerWebExchange` **không chứng minh** public ingress strip path đúng, không kiểm TLS termination hay chặn direct NodePort.

### 18.1. Ma trận path test

| Test | Client public path | Gateway cần nhận | Backend cần nhận |
| --- | --- | --- | --- |
| P1 | `/platform/api/orders/42` | `/api/orders/42` | `/orders/42` |
| P2 | `/platform/api/orders/42?x=1` | `/api/orders/42?x=1` | `/orders/42?x=1` |
| P3 | `/platform/api/orders/42/items` | `/api/orders/42/items` | `/orders/42/items` |
| P4 | `/platform/api/orders/` | `/api/orders/` | `/orders/` nếu match |
| P5 | `/platform/api/orders-old/42` | `/api/orders-old/42` | Không match orders route |
| P6 | `/platform/api/orders/a%2Fb` | Theo URI encoding policy | Không bypass path/authorization |
| P7 | `/platform/platform/api/orders/42` | Không đúng public contract | Không “tự sửa” double prefix |
| P8 | Direct `/api/orders/42` vào Gateway | Bị network policy từ chối ngoài ingress | Không được bypass |

Các kết quả trong bảng là **test expectations**, không phải log đã chạy. Với encoded slash, dot segments và Unicode, proxy/Framework có thể normalize ở thời điểm khác nhau; kiểm trên topology thật.

### 18.2. Test spoofing bằng curl

Chạy ở **môi trường kiểm thử được phép**, qua public entrypoint:

~~~bash
curl -i \
  -H 'Forwarded: for=10.0.0.1;proto=http;host=evil.example' \
  -H 'X-Forwarded-For: 10.0.0.1' \
  -H 'X-Forwarded-Proto: http' \
  -H 'X-Forwarded-Host: evil.example' \
  -H 'X-Forwarded-Prefix: /admin' \
  'https://api.example.test/platform/api/orders/42'
~~~

Assertions cần có:

- Public Location/absolute links **không** lấy `evil.example`.
- Gateway/backend **không** coi `10.0.0.1` client tự gửi là trusted client IP.
- Backend nhận forwarded metadata theo ingress/Gateway policy đã chuẩn hóa.
- Không nhảy sang route `/admin` hoặc bypass auth.
- Không ghi nguyên forwarded headers chứa dữ liệu nhạy cảm vào log.

### 18.3. Test redirect có upstream nội bộ

Cho mock backend trả:

~~~http
HTTP/1.1 302 Found
Location: http://order-service:8081/orders/42
~~~

Nếu contract yêu cầu rewriting, test client không tự follow redirect và assert:

~~~text
status = 302
Location = https://api.example.test/platform/api/orders/42
~~~

Test này chỉ PASS khi **response rewrite hoặc canonical public URL mechanism thật sự hoạt động**. Bật `trusted-proxies` đơn thuần không tự khiến Location có đúng cả scheme, host và public prefix.

### 18.4. Kiểm tra session và OAuth

- Cookie Path chứa public prefix đúng, Domain allowlisted, Secure/HttpOnly/SameSite hợp lệ.
- Callback URL exact match IdP registration.
- Redirect status và Location không chứa internal host/port.
- Untrusted host/proto/prefix injection không thay được callback.
- Direct request vào internal API route không bypass authorization.

### 18.5. Test khi qua CDN thật và khi bypass

Một mock ingress local không thể chứng minh hoàn toàn provider-specific CDN headers. Cần staging test đi qua CDN thật, so IP mà ingress nhìn thấy, rồi thử bypass CDN từ một nguồn không tin cậy để xác minh bị chặn.

Nếu có nhiều Gateway replicas, chạy test qua từng replica/canary để phát hiện config drift.

## 19. Một bộ kiểm thử tự động cần những assertion nào?

### 19.1. Request đến upstream

Dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)` + `WebTestClient.bindToServer()` với Gateway thật, cùng MockWebServer/WireMock ở HTTP upstream. Khi cần test Nginx, thêm một reverse proxy thật trong test setup.

Kỳ vọng:

~~~text
Given public route /platform/api/orders/**
When client GET /platform/api/orders/42?lang=vi
Then backend recorded request:
  method = GET
  path = /orders/42
  query = lang=vi
  Host = theo policy đã cấu hình
  Forwarded/X-Forwarded = chỉ metadata từ trusted hops
~~~

Đừng assert mọi header phải giống nguyên byte-for-byte giữa client và backend: Gateway có header filters, hop-by-hop headers và HTTP client transport-specific rules.

### 19.2. Response trả client

~~~text
Given backend returns:
  302 Location: http://order-service:8081/orders/42

Then client must see:
  302 Location: https://api.example.test/platform/api/orders/42
  no internal hostname in response
~~~

Nếu hệ thống chọn backend tự tạo canonical URL thay vì Gateway rewrite, assert vẫn giống nhau ở phía client. Cách triển khai là lựa chọn kiến trúc, nhưng **hợp đồng public URL không đổi**.

### 19.3. Các lớp test bổ sung

| Tầng | Kiểm tra | Giới hạn |
| --- | --- | --- |
| Unit logic | Validation/normalization public host/prefix | Không thấy network bypass |
| Gateway HTTP integration | Route, path, headers, Location | Có thể chưa có TLS/CDN |
| Ingress integration | Prefix stripping và header sanitization | Không hoàn toàn mô phỏng provider CDN |
| Staging full chain | CDN/Ingress/Gateway/Service/TLS | Chậm, cần kiểm soát data và secrets |
| Security tests | Spoof Host/Forwarded, direct bypass, IP limits | Phải chạy trên topology đúng |
| Upgrade regression | Behavior patch trước/sau | Không thay security review |

**Không đánh dấu PASS chỉ dựa trên một HTTP 200**; mock backend phải xác nhận request đúng và test client phải xác nhận response public đúng.

## 20. Hướng dẫn kiểm tra theo tầng bằng curl

### 20.1. Public HTTPS

~~~bash
curl -i \
  'https://api.example.test/platform/api/orders/42'
~~~

Để nhìn redirect 3xx gốc, **không thêm `-L`**. Với chứng chỉ self-signed trong lab, nên truyền test CA qua `--cacert`, không dùng `-k` trên production để lờ certificate errors.

### 20.2. Kiểm tra redirect

~~~bash
curl -i \
  'https://api.example.test/platform/api/orders/42/redirect'
~~~

Kiểm:

~~~text
Location scheme = https
Location host   = api.example.test
Location path   = /platform/api/orders/...
Location        = không có internal DNS/port
Location        = không nhân đôi /platform
~~~

### 20.3. Direct Gateway chỉ trong sandbox nội bộ

~~~bash
# Chỉ thực hiện ở mạng test có quyền truy cập.
curl -i \
  -H 'Forwarded: for=203.0.113.99;proto=https;host=evil.example' \
  -H 'X-Forwarded-Host: evil.example' \
  'http://edge-gateway:8080/api/orders/42'
~~~

Trong production, kết nối trực tiếp từ network không tin cậy nên bị **ACL/NetworkPolicy chặn**. Đừng dùng việc header có vẻ bị Spring bỏ qua làm biện pháp bảo vệ duy nhất.

### 20.4. Quan sát log có điều kiện

Log example đã làm sạch:

~~~text
routeId=orders-api
publicHost=api.example.test
publicProto=https
publicPrefix=/platform
gatewayPath=/api/orders/42
backendPath=/orders/42
transportPeer=ingress
forwardedPolicy=trusted
status=200
~~~

Đây là **schema đề xuất**, không phải output mặc định. Tránh ghi raw tokens/cookies/PII hoặc toàn bộ forwarded chain.

## 21. Triệu chứng, nguyên nhân và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Redirect từ HTTPS sang HTTP | Internal scheme được dùng làm public scheme | Trusted proxy proto, Boot strategy, canonical URL |
| Location chứa `:8080` | Lấy port Gateway nội bộ | Public port/rewrite |
| Location chứa `order-service` | Chưa rewrite host internal | Public Location contract |
| Redirect loop HTTP–HTTPS | Proto bị mất/ghi sai giữa hops | Kiểm từng hop, trusted metadata |
| Client 404 sau 302 | Thiếu prefix `/platform` hoặc `/api` | Assert Location public path |
| URL có `/platform/platform` | Prefix được apply hai lần | Chọn một owner |
| Backend nhận `/42` | Double strip từ ingress + Gateway | Bảng path mỗi hop |
| Gateway 404, backend không có request | Prefix/route mismatch, wrong namespace | Kiểm ingress path và route predicates |
| Host outbound sai | PreserveHost/SetRequestHostHeader thiếu/sai | Backend Host test + TLS SNI |
| Cookie không được gửi | Cookie Path/Domain/Secure sai | Browser test/Set-Cookie |
| OAuth2 redirect_uri bị từ chối | Public callback sai scheme/host/prefix | Canonical URL và IdP registration |
| Mọi người dùng chung rate-limit bucket | Lấy ingress IP thay client | Trusted resolver hoặc principal |
| Rate limit bypass bằng XFF | Tin phần tử client tự gửi | Edge sanitization, không dùng trustAll |
| RemoteAddr CIDR sai | Transport peer khác client IP | XForwarded resolver + network review |
| trusted-proxies không match | Đặt CIDR thay Java regex hoặc sai format header | Effective regex + recorded headers |
| Forwarded vs XFF mâu thuẫn | Không normalize đủ hai họ | Vệ sinh tại edge |
| Swagger servers chỉ internal host | Chưa có public base URL | OpenAPI public servers config |
| Client IP mất sau CDN | Ingress `$remote_addr` là CDN IP | Xác minh CDN ranges và Real-IP policy |
| Sau upgrade headers thay đổi | Security patch đổi default/customizer | Xem advisories và regression tests |
| Gateway WebMVC dùng WebFlux property | Sai namespace/runtime | Chọn `server.webmvc.*` đúng release |
| Test Gateway pass, direct NodePort vẫn mở | Chỉ test header, chưa test network | Firewall/NetworkPolicy test |
| Chỉ một replica bị redirect sai | Drift cấu hình hoặc patch | Canary, config diff/rollout |
| Backend HTTPS lỗi dù XFP=https | Outbound TLS chưa cấu hình | Truststore, certificate và SNI |
| Audit log tràn IP/PII | Dump raw forwarding headers | Redact, retention policy |

## 22. Runbook rollout trusted proxies

### 22.1. Trước khi đổi cấu hình

1. Vẽ topology CDN/WAF/LB/Ingress/Gateway/Backend **đang chạy**, không dựa vào sơ đồ giả định.
2. Ghi rõ public hosts, HTTPS ports, path prefixes và OAuth callbacks.
3. Lập danh sách network identities/IP ranges cho từng proxy hop.
4. Chỉ định **hop nào sanitize, hop nào append và hop nào consume** mỗi header.
5. Kiểm Spring Boot, Spring Cloud Gateway, Spring Framework và ingress versions.
6. Đối chiếu CVE-2025-41235/CVE-2026-47825 và nâng bản sửa được hỗ trợ.
7. Chọn một Gateway namespace và một Boot forwarded strategy theo thiết kế.
8. Đặt test matrix cho spoofing, Location, Set-Cookie, method/path/query và direct bypass.
9. Theo dõi redirect 3xx, 404, 401/403, 429, p95/p99 và lỗi TLS.
10. Chuẩn bị rollback **vẫn giữ network isolation và header sanitization**.

### 22.2. Canary rollout

- Bảo đảm network chặn public direct access tới Gateway.
- Bật sanitize/host validation ở edge.
- Đổi cấu hình Gateway trên một replica/canary có thể quan sát.
- Kiểm inbound scheme/host/path/prefix thực tế.
- Kiểm mock backend nhận correct path và only trusted forwarded metadata.
- Test client spoofing và IP-based quota.
- Test redirects/cookies/OAuth flow trên public HTTPS URL.
- Kiểm lỗi 404/redirect loop sau thay đổi.
- So sánh với baseline và mở rộng rollout nếu pass.
- Giữ cùng cấu hình trên toàn bộ Gateway replicas.

### 22.3. Sau rollout

- Audit hiệu lực patch và `NettyServerCustomizer` khi version có thay đổi.
- Kiểm thay đổi CDN address ranges, ingress controllers và security groups.
- Giám sát forwarding header size/drop/malformed events.
- Xem logs/traces đã redact, không dump raw token/cookie.
- Khi lỗi, rollback về **một cấu hình đã kiểm chứng an toàn**; không dùng `trusted-proxies: '.*'` hoặc `trustAll()` để chữa nhanh.
- Ghi rõ owner, ngày thay đổi, kết quả test và trường hợp cần rollback.

## 23. Bài thực hành tổng hợp

**Bối cảnh:** hệ thống có public URL `https://api.example.test/platform/api/orders/42`, ingress Nginx, Gateway WebFlux và mock order-service. Một CDN có thể được bổ sung ở giai đoạn hai.

### Yêu cầu

1. Vẽ scheme/host/port/path từng hop.
2. Dùng Nginx terminate TLS, rewrite `/platform` theo hợp đồng.
3. Xóa/ghi đè `Forwarded` và các `X-Forwarded-*` từ Internet.
4. Cấm direct public access đến Gateway ngoài ingress.
5. Chọn một release Gateway và trusted-proxies namespace tương ứng.
6. Viết Java regex giới hạn phù hợp với proxy metadata, không dùng `.*`.
7. Chọn Boot forwarded strategy, xác minh tác động lên request URI.
8. Tạo route `Path=/api/orders/**`, `StripPrefix=1`, target mock backend.
9. Gửi GET public, xác minh backend nhận `/orders/42`.
10. Thử query, trailing slash, encoded slash và route không khớp.
11. Gửi X-Forwarded-Host/Proto/For/Prefix giả, xác nhận không ảnh hưởng public URL hoặc quyền.
12. Mock backend trả `302 Location: http://order-service:8081/orders/42`; triển khai rewrite/canonical URL theo contract.
13. Kiểm Location public đúng scheme/host/prefix; test relative Location.
14. Kiểm Cookie Secure/Path/Domain/SameSite qua browser flow.
15. Kiểm OAuth2/OIDC redirect_uri exact và login callback.
16. Thử `maxTrustedIndex(1/2/3)` trên mock XFF chain, giải thích kết quả và threat model.
17. Kiểm rate limiter dùng principal/trusted IP thay client XFF tự đặt.
18. Thêm CDN giả/real ở staging và kiểm thay đổi remote peer, host và XFF.
19. Test một replica thiếu config để phát hiện config drift.
20. Thực hiện patch upgrade theo advisory, chạy lại contract/security tests và viết runbook.

### Ma trận nghiệm thu

| Mã | Phép thử | Kỳ vọng |
| --- | --- | --- |
| A1 | HTTPS public request | Đúng route/backend |
| A2 | Ingress strip prefix | Gateway nhận `/api/orders/42` |
| A3 | Gateway StripPrefix | Backend nhận `/orders/42` |
| A4 | Query `lang=vi` | Query không mất qua các hops |
| A5 | XFF giả từ client | Không trở thành trusted client IP |
| A6 | Forwarded/XFH giả | Không tạo Location `evil.example` |
| A7 | XFP giả | Không đổi public prefix thành `/admin` |
| A8 | Backend 302 nội bộ | Client Location dùng HTTPS public origin/path |
| A9 | Relative redirect | Không thiếu hoặc nhân đôi prefix |
| A10 | Cookie session | Attributes đúng theo browser contract |
| A11 | OAuth callback | redirect_uri exact và nguồn tin cậy |
| A12 | No-route | Không vô tình gọi backend khác |
| A13 | Rate limiter | Không bypass bằng IP giả |
| A14 | Direct Gateway bypass | Network deny |
| A15 | Multi-replica | Version và headers policy đồng nhất |
| A16 | Patch upgrade | Regression/security tests còn PASS |

**Đây là mục tiêu kiểm thử**, không khẳng định các lệnh đã chạy trong project thật.

## 24. Checklist production

- [ ] Public origin và path prefix đã được ghi rõ thành hợp đồng.
- [ ] Topology CDN/WAF/LB/ingress/Gateway/backend có owner và network identity rõ.
- [ ] Trusted edge sanitize **cả** `Forwarded` và `X-Forwarded-*` từ client.
- [ ] Có host allowlist, giới hạn header sizes và xử lý malformed values.
- [ ] Gateway chỉ nhận traffic từ trusted ingress; không public NodePort/bypass.
- [ ] Đã cài bản vá Gateway được vendor hỗ trợ cho forwarded-header advisories.
- [ ] `trusted-proxies` dùng Java regex giới hạn và test match actual proxy metadata.
- [ ] Không dùng `trusted-proxies: '.*'` hoặc viết CIDR thay regex.
- [ ] Gateway/WebFlux vs Server WebMVC properties đúng release train.
- [ ] Boot forwarded strategy và Gateway outbound filters không double-process.
- [ ] Append/overwrite rules được định nghĩa cho mọi proxy hop.
- [ ] Nginx/CDN client IP được xác minh trước khi dùng XFF.
- [ ] Không dùng `XForwardedRemoteAddressResolver.trustAll()` cho security.
- [ ] Ingress/Gateway strip đúng số path segments.
- [ ] `X-Forwarded-Prefix` không gây thiếu/nhân đôi public path.
- [ ] Public redirects/absolute links không lộ HTTP/internal DNS/port.
- [ ] Relative Location đã test trên public prefix.
- [ ] Cookies có Domain/Path/Secure/HttpOnly/SameSite đúng.
- [ ] OAuth2/OIDC callback exact và không lấy untrusted host.
- [ ] HSTS/CORS/OpenAPI/WebSocket public scheme phù hợp.
- [ ] Outbound TLS/mTLS/certificates được đánh giá độc lập với XFP.
- [ ] Rate-limit/IP audit key dùng trusted client IP hoặc principal.
- [ ] Đã test spoofing, network bypass, 3xx loop, 404 và multi-hop chain.
- [ ] Gateway replicas có patch/config nhất quán và rollback an toàn.
- [ ] Logs/traces đã che raw token/cookie/client PII.

## 25. Tổng kết và tài liệu tham khảo

Trong Spring Cloud Gateway sau nhiều proxy, URL public và URL nội bộ khác nhau là điều **bình thường**: client gọi `https://api.example.test/platform/api/orders/42`, ingress chuyển thành `/api/orders/42`, Gateway chuyển đến backend `/orders/42`. Điều quan trọng là mọi hop hiểu đúng trách nhiệm của mình.

**Ba nguyên tắc cần nhớ:**

1. **Tin theo nguồn, không theo tên header.** Trusted edge phải sanitize `Forwarded` và `X-Forwarded-*`, chặn đường bypass và Gateway phải có bản vá bảo mật cùng trusted-proxy policy đúng version.
2. **Request path và response public URL là hai bài toán khác nhau.** Ingress rewrite, Gateway StripPrefix, X-Forwarded-Prefix và Location/cookie/OAuth callback không tự động thay thế cho nhau.
3. **Test full chain.** Assert request thực đến backend, response cuối ở client và những ca cố ý giả Host/Proto/For/Prefix. Một HTTP 200 không chứng minh forwarded headers an toàn.

Khi CDN, ingress, Boot forwarded handling, Gateway header filters và backend có hợp đồng rõ, nền tảng microservices mới kết hợp được routing, auth, rate limit, retry, TLS và tracing mà không biến forwarding metadata thành đường vòng bảo mật.

### Tài liệu tham khảo chính thức

- [Spring Cloud Gateway Server WebFlux — HttpHeadersFilters](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/httpheadersfilters.html).
- [Spring Cloud Gateway — Configuration Properties 5.x](https://docs.spring.io/spring-cloud-gateway/reference/5.0/configprops.html).
- [Spring Cloud Gateway Server WebFlux — RemoteAddr và XForwardedRemoteAddressResolver](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/request-predicates-factories.html).
- [Spring Cloud Gateway Server WebFlux — RewriteLocationResponseHeader](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/gatewayfilter-factories/rewritelocationresponseheader-factory.html).
- [Spring Cloud Gateway Server WebMVC — HttpHeadersFilters](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/httpheadersfilters.html).
- [Spring Boot 3.5 — Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html).
- [Spring Boot 4.0 — Embedded Web Servers và Forwarded Headers](https://docs.spring.io/spring-boot/4.0/how-to/webserver.html).
- [Spring Framework WebFlux — ForwardedHeaderTransformer](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html).
- [Spring Security — HTTP Forwarded Headers Security](https://docs.spring.io/spring-security/reference/7.0/features/exploits/http.html).
- [IETF RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239.html).
- [Spring Security Advisory CVE-2025-41235](https://spring.io/security/cve-2025-41235/).
- [Spring Security Advisory CVE-2026-47825](https://spring.io/security/cve-2026-47825/).
