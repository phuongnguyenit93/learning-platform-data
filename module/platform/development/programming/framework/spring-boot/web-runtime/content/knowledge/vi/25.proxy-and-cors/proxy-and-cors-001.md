# Đường dẫn, host và giao thức công khai khi ứng dụng Spring Boot nằm sau reverse proxy

## 1. Bài toán: người dùng nhìn thấy URL nào, backend nhìn thấy URL nào?

Một ứng dụng Spring Boot triển khai sau **reverse proxy**, **load balancer**, **API gateway** hoặc **ingress controller** thường có hai địa chỉ khác nhau:

- **Public URL:** địa chỉ thực sự người dùng hoặc hệ thống bên ngoài nhìn thấy, ví dụ `https://app.example.com/portal/demo/inspect`.
- **Backend URL:** địa chỉ mà reverse proxy dùng để gọi ứng dụng, ví dụ `http://127.0.0.1:8080/demo/inspect` hoặc `http://app-service:8080/demo/inspect`.

Proxy có thể kết thúc HTTPS (TLS termination), thay host/port, và thêm hoặc loại bỏ một path prefix. Backend chỉ nhìn vào kết nối đến chính nó sẽ thấy HTTP, host nội bộ và đường dẫn đã rewrite. Nếu ứng dụng dùng những thông tin ấy để sinh absolute links, redirects, OAuth callback URL hoặc cookie, người dùng có thể gặp:

- Redirect tới `http://app-service:8080/...` thay vì `https://app.example.com/...`.
- Browser báo **mixed content** khi trang HTTPS chứa link/script/API endpoint HTTP.
- Redirect thiếu prefix `/portal` dẫn tới 404.
- Cookie `Secure` hoặc `Path` không đúng, login loop hoặc session không được gửi.
- OAuth/OIDC redirect URI không khớp giá trị đã đăng ký.
- URL được tạo từ host header không tin cậy, dẫn tới **host-header poisoning**, open redirect hoặc link reset password gửi tới domain của attacker.

Bài này nằm trong chủ đề **Proxy và CORS**, tập trung vào cách giữ **scheme, host, port, path prefix** đúng với điểm truy cập công khai. Ví dụ dùng **Spring Boot 3.5.x, Spring MVC/Servlet, Java 17+**, proxy Nginx minh họa; phần cuối có WebFlux, cookie, Spring Security và CORS.

**Mục tiêu quan trọng nhất:** thiết lập một **ranh giới tin cậy** nơi proxy xóa giá trị `Forwarded`/`X-Forwarded-*` do client gửi và đặt các giá trị được xác nhận; Spring chỉ được phép diễn giải thông tin đã qua ranh giới ấy. Đừng tin forwarded headers từ Internet trực tiếp.

## 2. Sơ đồ request và cách URL thay đổi qua proxy

Xét cấu hình:

```text
Trình duyệt / đối tác bên ngoài
GET https://app.example.com/portal/demo/inspect
                 |
                 | HTTPS :443
                 v
Nginx / Ingress / Load Balancer
- Xác nhận Host = app.example.com
- Kết thúc TLS
- Loại prefix /portal khi gửi upstream
- Xóa forwarded headers không tin cậy và đặt lại headers của proxy
                 |
                 | HTTP :8080 (mạng nội bộ)
                 v
Spring Boot MVC
GET http://127.0.0.1:8080/demo/inspect
                 |
                 v
Spring cần biết URL gốc là:
scheme = https
host = app.example.com
port = 443
external path prefix = /portal
```

Hãy phân biệt **hai phép biến đổi khác nhau**:

1. **Rewrite request path tại proxy:** từ `/portal/demo/inspect` thành `/demo/inspect`. Đây là bước để controller `@GetMapping("/demo/inspect")` xử lý được request.
2. **Tái tạo public URL trong backend:** ứng dụng vẫn cần biết rằng URL ngoài có prefix `/portal` và scheme/host công khai, để sinh link/redirect đúng.

Chỉ làm (1) nhưng bỏ (2) khiến app xử lý request thành công nhưng trả link sai. Chỉ làm (2) trong khi proxy không rewrite đúng khiến Spring không khớp controller mapping.

Một mô hình khác là **giữ nguyên prefix** tại proxy rồi cấu hình `server.servlet.context-path=/portal` ở backend. Hai mô hình đều có thể hợp lệ. Nhưng **không nên vừa xóa prefix ở proxy vừa buộc backend yêu cầu context path ấy**, cũng không nên vừa giữ prefix nội bộ vừa tự thêm prefix vào mọi link, vì dễ 404 hoặc bị nhân đôi `/portal/portal`.

## 3. Các thành phần của public URL

Với URL:

```text
https://app.example.com:443/portal/products/42?q=a%26b#details
  |        |         |     |        |            |
scheme    host       port  prefix   path         query/fragment
```

- **Scheme:** `https` hoặc `http`; HTTPS tại edge không đồng nghĩa backend dùng HTTPS.
- **Host:** `app.example.com`, không phải hostname pod/container/VM nội bộ.
- **Port:** `443` cho HTTPS mặc định; có thể bỏ qua khi biểu diễn URL chuẩn. Nếu proxy công khai port không mặc định như `8443`, cần phản ánh đúng.
- **Public prefix:** `/portal`, thường đến từ routing/rewrite của gateway; **không phải tên classpath directory**.
- **Path:** `/products/42` là phần đường dẫn trong ứng dụng.
- **Query:** tham số cần được encode theo vị trí; không nối raw user input vào link.
- **Fragment:** `#details` thường chỉ được browser xử lý phía client, không truyền tới server trong HTTP request.

Một **origin** trong chính sách CORS gồm **scheme + host + port**, không gồm path prefix. Ví dụ `https://app.example.com/portal` và `https://app.example.com/another` có **cùng origin** nếu cùng scheme/host/port, dù routing khác nhau.

## 4. Hai nhóm header proxy phổ biến

### 4.1. Header chuẩn `Forwarded` (RFC 7239)

Một proxy có thể dùng:

```http
Forwarded: for=203.0.113.20;proto=https;host=app.example.com
```

Thông tin thường gồm:

- `for`: danh tính/địa chỉ client theo chuỗi hop, phụ thuộc proxy policy.
- `proto`: scheme ở phía client/edge (ví dụ `https`).
- `host`: public host, có thể chứa port.

Header có thể chứa nhiều phần tử qua các proxy hop. Không tự tách chuỗi bằng dấu phẩy/dấu chấm phẩy đơn giản để làm logic bảo mật: định dạng RFC hỗ trợ quoted values, IPv6, danh tính ẩn, nhiều hop và luật tin cậy proxy.

### 4.2. Nhóm header `X-Forwarded-*`

Nhiều proxy dùng convention lâu đời:

```http
X-Forwarded-Proto: https
X-Forwarded-Host: app.example.com
X-Forwarded-Port: 443
X-Forwarded-Prefix: /portal
X-Forwarded-For: 203.0.113.20
```

Ý nghĩa:

| Header | Phản ánh | Cạm bẫy |
| --- | --- | --- |
| `X-Forwarded-Proto` | Public scheme, ví dụ `https` | Nếu thiếu, app có thể tự sinh `http://...` |
| `X-Forwarded-Host` | Host người dùng truy cập | Nếu cho client tự chọn, có thể làm URL trỏ tới attacker |
| `X-Forwarded-Port` | Public port | Sai port có thể làm callback/redirect không truy cập được |
| `X-Forwarded-Prefix` | Prefix bên ngoài proxy đã xử lý | Mất prefix -> 404, lặp prefix -> URL sai; mức hỗ trợ tùy Spring version/cấu hình |
| `X-Forwarded-For` | Chuỗi địa chỉ client/proxy hops | Không tự tin giá trị đầu tiên là IP đáng tin |
| `X-Forwarded-Ssl` | Một convention khác cho HTTPS termination | Không thay thế một contract proxy chuẩn hóa |

Đây là **metadata có thể giả mạo** nếu backend nhận trực tiếp từ client. Không sử dụng các header để quyết định **phân quyền**, cấp đặc quyền, chống brute-force hoặc allowlist IP trước khi xác minh nguồn header và chuỗi trusted hops.

**Không chủ động bật cả hai kiểu chuẩn và legacy chỉ để “phòng hờ”**. Hãy thống nhất một contract với proxy; strip những header từ Internet không sử dụng, và kiểm thử cách framework ưu tiên nếu vẫn xuất hiện cả hai dạng.

## 5. Bảo mật ranh giới tin cậy: trước khi bật forwarded headers

Cấu hình Spring có thể tái tạo public URL **chỉ khi proxy đảm bảo header đáng tin**. Spring không thể tự biết giá trị `Forwarded` do proxy hợp lệ đặt hay do người ngoài giả mạo.

Ba yêu cầu tối thiểu:

1. **Edge proxy xóa/ghi đè** `Forwarded` và mọi `X-Forwarded-*` từ Internet, rồi đặt giá trị phù hợp từ một nguồn đáng tin (TLS termination, routing rules, verified host). Nếu có nhiều proxy, quy tắc giữ/thay hop phải được định nghĩa rõ ở từng trust boundary.
2. **Backend không được truy cập công khai trực tiếp.** Bind localhost nếu cùng máy, security group, network policy, firewall, private service endpoint hoặc sidecar isolation. Trong production không để Internet truy cập `http://pod-ip:8080` cùng lúc với reverse proxy.
3. **Cho phép đúng public hosts.** Cấu hình ingress/server name allowlist; tránh sử dụng raw `Host` hoặc `X-Forwarded-Host` client gửi để tự quyết định domain của link, reset password URL hoặc redirect.

Ví dụ sai:

```http
GET /demo/next HTTP/1.1
Host: 127.0.0.1:8080
X-Forwarded-Proto: https
X-Forwarded-Host: attacker.invalid
```

Nếu backend tin header này từ kết nối trực tiếp, một URL phản hồi có thể bị biến thành `https://attacker.invalid/...`. Kẻ tấn công không cần biết cấu hình link nội bộ; chỉ cần ứng dụng dùng header để xây URL.

Với các **link bảo mật đặc biệt quan trọng** (khôi phục mật khẩu, invitation link, xác minh email, webhook callback, OAuth redirect URI), nên ưu tiên **canonical public base URL do operator cấu hình** và/hoặc allowlist host đã duyệt, thay vì hoàn toàn dựa vào request metadata. Ví dụ `app.public-base-url=https://app.example.com/portal` được giới thiệu trong bài thực hành.

**Kiểm tra một request hợp lệ không đủ chứng minh proxy an toàn.** Phải kiểm tra request có `Forwarded` hoặc `X-Forwarded-Host` độc hại từ bên ngoài được xóa/ghi đè trước khi tới Spring; đồng thời đảm bảo raw backend port không lộ ra Internet.

## 6. Cấu hình Spring Boot `server.forward-headers-strategy`

Spring Boot có property:

```properties
server.forward-headers-strategy=framework
```

Các mode:

| Giá trị | Ý nghĩa | Cân nhắc |
| --- | --- | --- |
| `none` | Không dựa vào forwarded headers để tái tạo request theo cơ chế này | Thích hợp khi không có trusted proxy hoặc muốn URL canonical cố định |
| `native` | Dùng khả năng native của embedded web server/container (ví dụ Tomcat `RemoteIpValve`) | Hữu ích cho scheme/remote IP; mức hỗ trợ prefix/host khác nhau theo container/version |
| `framework` | Dùng xử lý ở tầng Spring Framework: `ForwardedHeaderFilter` với Servlet MVC hoặc `ForwardedHeaderTransformer` với WebFlux | Phù hợp khi cần xử lý phức tạp hơn, nhưng vẫn phải bảo vệ trust boundary |

**Không bật `framework` và đồng thời đăng ký thêm một `ForwardedHeaderFilter` khác một cách tùy tiện**, vì có thể xử lý header hai lần hoặc có thứ tự filter không như dự kiến. Spring Boot đã cung cấp integration qua property.

Spring Boot 3.5 tài liệu nêu có môi trường cloud có default khác; **hãy đặt mode rõ ràng theo thiết kế triển khai** thay vì dựa vào default giữa local, Docker và cloud. Trong bài thực hành ta dùng `framework` ở môi trường mô phỏng trusted proxy, **không có nghĩa an toàn để mở port app ra Internet**.

### 6.1. Khi nào `native` là lựa chọn hợp lý?

Nếu proxy cung cấp `X-Forwarded-For` và `X-Forwarded-Proto` thông thường, native support của container có thể đủ cho scheme/client metadata. Với Tomcat, `RemoteIpValve` có cấu hình thêm về tên header và dải proxy nội bộ được tin cậy. Ví dụ key cấu hình (cần khớp kiến trúc thật):

```properties
server.forward-headers-strategy=native
server.tomcat.remoteip.protocol-header=x-forwarded-proto
server.tomcat.remoteip.remote-ip-header=x-forwarded-for
```

Đây là **một lựa chọn thay thế** cho `framework`, không phải property phải bật đồng thời. Không đặt `server.tomcat.remoteip.internal-proxies` rỗng trong production chỉ để mọi IP đều được tin. Kiểm tra trusted proxy IP/CIDR và cách Tomcat parse chain; không dùng `X-Forwarded-For` làm định danh an ninh khi client có thể chèn dữ liệu.

Nếu cần `X-Forwarded-Prefix`, đừng giả định native mode sẽ xử lý giống Spring filter. **Test thực tế context path và Location header**, hoặc dùng scheme kiến trúc không cần strip prefix.

### 6.2. `framework` và `X-Forwarded-Prefix`

Khi proxy đã bỏ `/portal` trước khi gửi upstream, Spring cần cơ chế hiểu **public prefix**.

Spring Framework có hỗ trợ `X-Forwarded-Prefix` trong forwarded-header infrastructure. **Hành vi bật/tắt tiền tố có thể khác nhau giữa các bản Spring Framework**, bao gồm tùy chọn dùng prefix riêng trên những bản mới. Vì thế không nên kết luận chỉ từ property `server.forward-headers-strategy=framework` rằng mọi bản framework sẽ tự đặt `request.getContextPath()` bằng `/portal`. Hãy kiểm tra bản framework cụ thể, cấu hình filter/transformer và output của `request.getContextPath()` hay link do Spring tạo.

Với bản framework cho phép chỉnh `ForwardedHeaderFilter.setUseForwardedPrefix(true)`, lựa chọn này chỉ được áp dụng khi gateway thật sự truyền một prefix **đáng tin**. Không tự thêm filter thứ hai khi Boot đã đăng ký filter; nếu cần cấu hình sâu, hãy chủ động thiết kế cách đăng ký để có **một** cơ chế xử lý duy nhất.

**Cách dự phòng đơn giản và ổn định:** cho các link quan trọng dùng `app.public-base-url` cố định, cộng thêm đường dẫn nội bộ đúng vị trí. Ví dụ bên dưới vẫn giữ cấu hình forwarded headers để minh họa scheme/host, nhưng redirect được sinh từ canonical base nhằm bảo toàn `/portal` ngay cả khi một bản framework chưa tự xử lý prefix.

### 6.3. Tomcat TLS termination và redirect context root

Theo tài liệu Spring Boot, với Tomcat phía sau proxy kết thúc TLS, có thể cần:

```properties
server.tomcat.redirect-context-root=false
```

Mục đích là tránh redirect context-root do Tomcat thực hiện **trước khi `X-Forwarded-Proto` được áp dụng** trong một số cấu hình. Đây không phải tùy chọn tạo HTTPS từ HTTP, cũng không thay thế header proxy. Hãy xác nhận theo phiên bản Tomcat/Boot và deployment của bạn trước khi áp dụng.

## 7. Ví dụ cấu hình reverse proxy Nginx

Giả sử client truy cập `https://app.example.com/portal/demo/inspect` và backend lắng nghe `http://127.0.0.1:8080/demo/inspect`.

Ví dụ **minh họa cách rewrite và đặt một bộ header canonical**; file TLS certificate phải thực sự tồn tại và config hoàn chỉnh còn cần các chính sách timeout, logging, allowlist host, HTTP→HTTPS redirect, trust chain và hardening của hạ tầng:

```nginx
server {
    listen 443 ssl;
    server_name app.example.com;

    ssl_certificate     /etc/nginx/tls/app.example.com.crt;
    ssl_certificate_key /etc/nginx/tls/app.example.com.key;

    # Khi URL không có dấu / cuối, chuyển về prefix chuẩn.
    location = /portal {
        return 308 /portal/;
    }

    location /portal/ {
        # Dấu / cuối proxy_pass giúp loại /portal/ trước khi gửi upstream.
        proxy_pass http://127.0.0.1:8080/;

        # Cố định host công khai, không lấy thẳng từ request tùy ý.
        proxy_set_header Host app.example.com;

        # Chỉ dùng X-Forwarded-* cho contract ví dụ.
        proxy_set_header Forwarded "";

        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Host app.example.com;
        proxy_set_header X-Forwarded-Port 443;
        proxy_set_header X-Forwarded-Prefix /portal;

        # Giả sử Nginx là edge nhận client trực tiếp.
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Real-IP $remote_addr;

        # Không giữ các legacy indicators không nằm trong contract.
        proxy_set_header X-Forwarded-Ssl "";
    }
}
```

**Giải thích:**

- `location /portal/` + `proxy_pass http://127.0.0.1:8080/;`: URI được proxy chuyển đổi từ `/portal/demo/inspect` sang `/demo/inspect` theo quy tắc Nginx đối với prefix location.
- `Host` và `X-Forwarded-Host` cùng là `app.example.com` từ cấu hình server đã phê duyệt, không dựa vào raw `Host` client.
- `X-Forwarded-Proto=https` và `X-Forwarded-Port=443` truyền public scheme/port sau khi Nginx xử lý TLS.
- `X-Forwarded-Prefix=/portal` thông báo external prefix, **không tự rewrite URL trong Spring nếu version/filter chưa hỗ trợ**.
- Dòng `X-Forwarded-For $remote_addr` chỉ hợp lý khi Nginx thực sự là **trusted edge nhận client trực tiếp**. Nếu phía trước còn CDN/load balancer, cần cấu hình real-client-IP trust chain cụ thể; không tự chọn phần tử đầu/cuối của chuỗi tùy ý.
- `proxy_set_header Forwarded "";` đảm bảo không truyền header RFC do khách gửi trong cấu hình minh họa. Trong hệ thống thật, phải **strip/override đầy đủ tất cả biến thể forwarded metadata** tại edge, kể cả những header do gateway/hạ tầng riêng sử dụng.
- URL `/portal` được redirect thành `/portal/`. HTTP 308 bảo toàn HTTP method/body theo chuẩn; ứng dụng phải cân nhắc điều này nếu route cho phép phương thức có tác dụng phụ. Ví dụ chỉ dùng prefix entry.
- Nếu triển khai Nginx ở container riêng, `127.0.0.1` sẽ trỏ về **chính container Nginx**, không phải container Spring; thay bằng DNS service được cấp phép như `app-service:8080` trong mạng riêng.

**Giới hạn của ví dụ:** Nginx không cung cấp sẵn chứng chỉ giả trong snippet; các đường dẫn TLS là ví dụ về nơi chứa file trong một deployment thật. Cũng phải bảo vệ backend bằng firewall/network policy, không chỉ dựa vào `proxy_set_header`. Nếu có nhiều ingress cùng truy cập ứng dụng, mỗi ingress phải thực thi cùng trust policy.

### 7.1. Một thay đổi trong location có thể làm toàn bộ path hỏng

So sánh các trường hợp:

```nginx
# Mẫu A: URI prefix /portal/ bị thay bằng / khi proxy_pass có dấu / cuối.
location /portal/ {
    proxy_pass http://127.0.0.1:8080/;
}

# Mẫu B: URI gốc thường được giữ khi proxy_pass không có URI phía sau host.
location /portal/ {
    proxy_pass http://127.0.0.1:8080;
}
```

Hai đoạn trên là **ví dụ so sánh**, không phải cấu hình chạy đồng thời. Đối với Mẫu A, backend map `/demo/inspect`. Đối với Mẫu B, backend có thể nhận `/portal/demo/inspect`, nên nếu controller chỉ map `/demo/inspect` sẽ trả 404 trừ khi có context/mapping tương ứng.

**Đừng sửa lỗi mất prefix bằng cách nối thêm `/portal` khắp controller.** Hãy xác định trước contract: prefix được giữ ở backend hay được proxy strip, sau đó cấu hình URL builder/headers nhất quán.

## 8. Ví dụ Spring Boot Java 17+ có thể chạy: URL động và URL canonical

Ví dụ dùng Spring MVC. Nó cung cấp:

- `GET /demo/inspect`: cho thấy request metadata **sau khi forwarded header processing** và URL mà Spring cố gắng tái tạo. Chỉ trả thông tin cơ bản của demo, không xuất session token hay IP nhạy cảm.
- `GET /demo/next`: trả HTTP **302 Location** đến public URL cố định `https://app.example.com/portal/demo/inspect`; điều này tránh lỗi link reset/callback bị phụ thuộc raw host request.
- `GET /demo/link`: trả URL liên kết canonical theo property server, phù hợp đưa vào JSON hoặc email mẫu.

**Nội dung demo không có authentication và không phải thiết kế cho các endpoint nhạy cảm công khai.** Mục đích là hiểu public URL khi chạy sau proxy.

### 8.1. Tạo dự án

Tạo dự án Spring Boot **3.5.x** với **Java 17+**, dependency **Spring Web** (`spring-boot-starter-web`) và **Spring Boot Starter Test** (`spring-boot-starter-test`, test scope). Dùng Maven Wrapper do Spring Initializr tạo.

```text
src/
├─ main/
│  ├─ java/com/example/demo/
│  │  ├─ ProxyUrlsApplication.java
│  │  └─ PublicUrlController.java
│  └─ resources/
│     └─ application.properties
└─ test/java/com/example/demo/
   └─ PublicUrlIntegrationTest.java
```

### 8.2. File cấu hình

**`src/main/resources/application.properties`**

```properties
server.port=8080

# Có trusted proxy thì cho Spring framework tái tạo public request metadata.
server.forward-headers-strategy=framework

# Canonical URL được operator cấu hình, không lấy từ header tùy ý.
app.public-base-url=https://app.example.com/portal

# Hỗ trợ trường hợp Tomcat thực hiện context root redirect sau TLS termination.
server.tomcat.redirect-context-root=false
```

Trong local demo, gọi thẳng `http://localhost:8080` kèm header mô phỏng proxy để quan sát. Trong production, **không được để cổng này công khai** khi `server.forward-headers-strategy=framework` được bật; phải có ranh giới proxy đáng tin trước đó.

### 8.3. Main class

**`src/main/java/com/example/demo/ProxyUrlsApplication.java`**

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProxyUrlsApplication {
    public static void main(String[] args) {
        SpringApplication.run(ProxyUrlsApplication.class, args);
    }
}
```

### 8.4. Controller

**`src/main/java/com/example/demo/PublicUrlController.java`**

```java
package com.example.demo;

import java.net.URI;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;
import org.springframework.web.util.UriComponentsBuilder;

@RestController
@RequestMapping("/demo")
public class PublicUrlController {

    private final URI canonicalPublicBase;

    public PublicUrlController(
            @Value("${app.public-base-url}") String configuredBase) {
        URI base = URI.create(configuredBase).normalize();

        // Policy đơn giản cho bài thực hành: một origin + prefix cố định.
        if (!"https".equalsIgnoreCase(base.getScheme())
                || !"app.example.com".equalsIgnoreCase(base.getHost())
                || !"/portal".equals(base.getPath())
                || base.getRawQuery() != null
                || base.getRawFragment() != null) {
            throw new IllegalArgumentException(
                "Invalid configured public base URL"
            );
        }
        this.canonicalPublicBase = base;
    }

    @GetMapping("/inspect")
    public RequestInfo inspect(HttpServletRequest request) {
        // Spring dựng base từ request mà framework đã xử lý.
        String derivedBase =
            ServletUriComponentsBuilder.fromCurrentContextPath()
                .build()
                .toUriString();

        return new RequestInfo(
            request.getScheme(),
            request.getServerName(),
            request.getServerPort(),
            request.getContextPath(),
            derivedBase,
            canonicalPublicBase.toString()
        );
    }

    @GetMapping("/link")
    public Map<String, String> link() {
        return Map.of("url", canonicalInspectUrl().toString());
    }

    @GetMapping("/next")
    public ResponseEntity<Void> next() {
        return ResponseEntity.status(HttpStatus.FOUND)
            .location(canonicalInspectUrl())
            .build();
    }

    private URI canonicalInspectUrl() {
        return UriComponentsBuilder.fromUri(canonicalPublicBase)
            .path("/demo/inspect")
            .build()
            .toUri();
    }

    public record RequestInfo(
        String scheme,
        String host,
        int port,
        String contextPath,
        String derivedBase,
        String configuredPublicBase
    ) {}
}
```

**Vì sao ví dụ tách hai dạng URL?**

1. `derivedBase` dùng `ServletUriComponentsBuilder.fromCurrentContextPath()` và **request đã được framework xử lý**. Nếu trusted headers cho biết `https` và `app.example.com`, giá trị động sẽ phản ánh những thông tin ấy. Nếu phiên bản/framework xử lý `X-Forwarded-Prefix` như mong đợi, path public `/portal` cũng xuất hiện.
2. `canonicalPublicBase` là một URI do operator cấu hình. Dù request đi qua đường nội bộ hoặc reverse proxy không truyền prefix, `canonicalInspectUrl()` vẫn tạo **`https://app.example.com/portal/demo/inspect`**.
3. `URI.create(...).normalize()` **không phải** một hàm chống URL poisoning tổng quát; đoạn constructor chỉ chấp nhận đúng scheme/host/prefix đã đặt cho demo. Với nhiều public domains, phải thiết kế explicit allowlist/tenant mapping, không bỏ kiểm tra để nhận mọi `Host`.
4. `ResponseEntity.status(FOUND).location(uri)` đặt header `Location` cho redirect 302. `@RestController` không tự ghép path và không trả tên view như `@Controller`.
5. Tên URI có `https` dù kết nối tới Tomcat là `http`, vì đó là public URL operator muốn client thấy.
6. Để tạo URL chứa ID/query từ input, sử dụng `UriComponentsBuilder` và encode **đúng thành phần**, thay vì ghép trực tiếp user strings vào URL. Ví dụ ở phần 10.

### 8.5. Chạy local

```bash
java -version
./mvnw spring-boot:run
```

Trên Windows, dùng `mvnw.cmd spring-boot:run` và `curl.exe` nếu PowerShell có alias `curl`.

**Không gửi forwarded headers** (request thẳng tới local server):

```bash
curl -i http://localhost:8080/demo/inspect
```

Kết quả JSON dạng:

```json
{
  "scheme": "http",
  "host": "localhost",
  "port": 8080,
  "contextPath": "",
  "derivedBase": "http://localhost:8080",
  "configuredPublicBase": "https://app.example.com/portal"
}
```

Đây là **kết quả kỳ vọng với HTTP localhost không qua proxy và không có header forwarded**, không phải bản ghi chạy thật. Thứ tự fields/formatting JSON tùy Jackson; không kiểm thử string JSON có whitespace cố định.

**Giả lập trusted proxy trong local** (chỉ phù hợp test/dev trên cổng không công khai):

```bash
curl -i http://localhost:8080/demo/inspect \
  -H "X-Forwarded-Proto: https" \
  -H "X-Forwarded-Host: app.example.com" \
  -H "X-Forwarded-Port: 443" \
  -H "X-Forwarded-Prefix: /portal"
```

Kỳ vọng sau filter:

- `"scheme":"https"` và `"host":"app.example.com"`.
- `"port"` thể hiện HTTPS mặc định (thường là 443).
- `contextPath` / `derivedBase`: có thể phản ánh `/portal` **nếu Spring version/config bật xử lý forwarded prefix**; xác minh cụ thể với bản framework đang chạy.
- `"configuredPublicBase":"https://app.example.com/portal"` luôn cố định theo property.

**Kiểm tra redirect:**

```bash
curl -i http://localhost:8080/demo/next
```

Kỳ vọng HTTP `302 Found` và:

```http
Location: https://app.example.com/portal/demo/inspect
```

Redirect này **không phụ thuộc forwarded headers** vì được tạo từ canonical base. Đừng dùng `curl -L` khi chỉ muốn xem header: nó có thể cố truy cập domain trong Location (ví dụ public domain chưa cấu hình DNS trong môi trường demo).

**Kiểm tra link JSON:**

```bash
curl -i http://localhost:8080/demo/link
```

Kỳ vọng:

```json
{"url":"https://app.example.com/portal/demo/inspect"}
```

Đây là URL có thể công bố nếu hạ tầng thật đã route hostname/prefix đó; local demo không tạo bản ghi DNS hoặc chứng chỉ TLS cho `app.example.com`.

## 9. Kiểm thử tích hợp: HTTP connector thật và headers mô phỏng

Chỉ test controller bằng `MockMvc` có thể không quan sát đầy đủ behavior của embedded server và filter chain như khi request qua HTTP. Ví dụ này dùng `@SpringBootTest(webEnvironment=RANDOM_PORT)` để mở Tomcat cục bộ và **JDK HttpClient** gửi header mô phỏng một trusted proxy.

**`src/test/java/com/example/demo/PublicUrlIntegrationTest.java`**

```java
package com.example.demo;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class PublicUrlIntegrationTest {

    @LocalServerPort
    int port;

    private final HttpClient client = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();

    private final ObjectMapper json = new ObjectMapper();

    private URI local(String path) {
        return URI.create("http://localhost:" + port + path);
    }

    @Test
    void directRequestSeesLocalScheme() throws Exception {
        HttpRequest req = HttpRequest.newBuilder(local("/demo/inspect"))
            .GET()
            .build();

        HttpResponse<String> res = client.send(
            req, HttpResponse.BodyHandlers.ofString()
        );

        assertEquals(200, res.statusCode());
        JsonNode body = json.readTree(res.body());
        assertEquals("http", body.get("scheme").asText());
        assertEquals("localhost", body.get("host").asText());
        assertEquals(
            "https://app.example.com/portal",
            body.get("configuredPublicBase").asText()
        );
    }

    @Test
    void trustedProxySimulationRestoresSchemeAndHost() throws Exception {
        HttpRequest req = HttpRequest.newBuilder(local("/demo/inspect"))
            .header("X-Forwarded-Proto", "https")
            .header("X-Forwarded-Host", "app.example.com")
            .header("X-Forwarded-Port", "443")
            .header("X-Forwarded-Prefix", "/portal")
            .GET()
            .build();

        HttpResponse<String> res = client.send(
            req, HttpResponse.BodyHandlers.ofString()
        );

        assertEquals(200, res.statusCode());
        JsonNode body = json.readTree(res.body());
        assertEquals("https", body.get("scheme").asText());
        assertEquals("app.example.com", body.get("host").asText());
        assertTrue(
            body.get("derivedBase").asText()
                .startsWith("https://app.example.com")
        );
    }

    @Test
    void redirectUsesCanonicalPublicUrl() throws Exception {
        HttpRequest req = HttpRequest.newBuilder(local("/demo/next"))
            .GET()
            .build();

        HttpResponse<Void> res = client.send(
            req, HttpResponse.BodyHandlers.discarding()
        );

        assertEquals(302, res.statusCode());
        assertEquals(
            "https://app.example.com/portal/demo/inspect",
            res.headers().firstValue("Location").orElseThrow()
        );
    }

    @Test
    void linkContainsPublicPrefixExactlyOnce() throws Exception {
        HttpRequest req = HttpRequest.newBuilder(local("/demo/link"))
            .GET()
            .build();

        HttpResponse<String> res = client.send(
            req, HttpResponse.BodyHandlers.ofString()
        );

        assertEquals(200, res.statusCode());
        JsonNode body = json.readTree(res.body());
        assertEquals(
            "https://app.example.com/portal/demo/inspect",
            body.get("url").asText()
        );
    }
}
```

Chạy:

```bash
./mvnw test
```

**Kết quả thiết kế:** với project Spring Boot 3.5.x tương thích, embedded Tomcat và property `server.forward-headers-strategy=framework` có hiệu lực, **bốn test được kỳ vọng pass**. Chúng minh họa framework tái tạo scheme/host và canonical redirect. **Không phải báo cáo đã chạy test trong repository thực tế.**

Những điều test **chưa chứng minh**:

- Nginx thật có strip mọi forwarded headers từ Internet hay không.
- Backend port có bị truy cập trực tiếp từ mạng bên ngoài hay không.
- Spring/framework version có xử lý `X-Forwarded-Prefix` đúng kỳ vọng hay không: test chỉ kiểm tra scheme/host; canonical link kiểm tra prefix không bị lặp, **không đồng nghĩa dynamic derivedBase có prefix**.
- OAuth login flow, cookie path, SecurityFilterChain hay CORS policy hoạt động đúng trên production host.

Để QA đầy đủ, thử thêm request qua URL HTTPS tại edge và kiểm tra `Location`, `Set-Cookie`, page links và phân quyền theo hợp đồng ứng dụng.

## 10. Sinh URL đúng cho link, redirect, query và callback

### 10.1. Absolute URL từ trusted request

Trong Spring MVC, khi đã bảo đảm trusted proxy headers và filter đúng, các API như `ServletUriComponentsBuilder.fromCurrentContextPath()` có thể tái tạo scheme/host/context path. Ví dụ snippet trong controller:

```java
String base = ServletUriComponentsBuilder
    .fromCurrentContextPath()
    .build()
    .toUriString();
```

**Không dùng kết quả này cho tác vụ security-sensitive chỉ vì nó trông giống HTTPS.** Nếu edge chưa lọc input, attacker có thể điều khiển host. Với link gửi qua email, canonical base cố định thường đơn giản hơn.

### 10.2. Relative URL và prefix

Link tương đối như `/demo/inspect` là đường dẫn **từ root của domain**, không phải từ `/portal`. Vì vậy:

- Nếu app public ở `/portal`, href `/demo/inspect` có thể dẫn tới `https://app.example.com/demo/inspect` (**mất prefix**).
- Href `demo/inspect` là relative path theo URL trang hiện tại; có thể sai nếu trang thay đổi độ sâu path.
- Với template Thymeleaf/JSP, dùng context-aware URL helpers (`@{/...}` ở Thymeleaf khi cấu hình context đúng), và kiểm thử sau proxy.
- Với SPA, cấu hình router base, asset public path, fetch base URL và HTML `<base>` có cân nhắc. Thiết lập sai một trong các lớp này vẫn khiến asset 404 dù backend trả API bình thường.
- Khi app public ở subpath mà backend context root rỗng, nếu framework không biết proxy prefix, link context-aware mặc định vẫn có thể thiếu prefix. Cần contract proxy/framework đúng hoặc cấu hình public base trên frontend.

### 10.3. Query/path parameters phải được encode riêng

Snippet minh họa trong service/controller, không phải class độc lập:

```java
URI uri = UriComponentsBuilder
    .fromUri(URI.create("https://app.example.com/portal"))
    .path("/search")
    .queryParam("q", "{q}")
    .encode()
    .buildAndExpand("a&b có dấu")
    .toUri();
```

Kết quả URI chứa query parameter `q` đã percent-encode, không tách `a&b` thành hai param. Ký tự `&` trong dữ liệu phải được bảo vệ. Không ghép:

```java
// ANTI-PATTERN: dữ liệu có thể phá vỡ cấu trúc URL.
String link = "https://app.example.com/portal/search?q=" + userQuery;
```

Khi URL target do user gửi, thêm **kiểm tra đích**: only internal-relative URL hoặc allowlist scheme/host/port, tránh open redirect. `URI.normalize()` chỉ chuẩn hóa URI theo quy tắc của nó, không tự chặn URL độc hại.

### 10.4. OAuth/OIDC redirect và SSO

Nếu Spring Security OAuth2 login dùng endpoint callback như:

```text
https://app.example.com/portal/login/oauth2/code/my-client
```

thì identity provider phải đăng ký **đúng URL công khai**, không phải `http://app-service:8080/login/oauth2/code/my-client`. Cần đối chiếu:

- `https`, host, port ngoài, prefix `/portal`.
- URL thực do Spring Security tạo sau forwarded processing.
- Authorization request redirect URI và giá trị đã đăng ký ở IdP.
- Cookie session, SameSite/Secure và OAuth state giữa các bước redirect.
- Proxy rewrite path ở callback route để backend nhận đúng `/login/oauth2/code/my-client`.

Nếu callback sai, không sửa bằng cách cho phép wildcard redirect URI rộng hoặc tắt CSRF/state. Xác định khâu thiếu protocol/host/prefix rồi sửa trust/proxy configuration.

## 11. Cookie và session phía sau TLS-terminating proxy

Backend có thể nhận HTTP, trong khi trình duyệt đang nói chuyện HTTPS với proxy. Cookie và các xử lý bảo mật dựa trên **ngữ cảnh công khai** phải phản ánh đúng HTTPS.

Các tùy chọn Spring Boot Servlet phổ biến:

```properties
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
```

Với HTTPS production:

```properties
server.servlet.session.cookie.secure=true
```

`Secure` yêu cầu cookie được gửi qua HTTPS từ phía browser; app nội bộ vẫn có thể giao tiếp HTTP với reverse proxy. `HttpOnly` hạn chế JavaScript đọc cookie. `SameSite` giúp hạn chế một số luồng cookie cross-site, nhưng **không thay thế CSRF protection**.

Cần phân biệt **cookie Path**:

- Nếu backend context path là `/` nhưng public prefix là `/portal`, session cookie có thể có `Path=/`; browser vẫn gửi nó tới `/portal/...`, nhưng cookie được gửi rộng hơn cần thiết.
- Nếu cookie có `Path=/portal`, browser gửi nó cho `/portal/...`, nhưng sẽ không gửi cho đường dẫn công khai ở `/other`.
- Nếu proxy rewrite path, đừng giả định cookie path luôn tự khớp; kiểm tra header `Set-Cookie` và giá trị cookie gửi lại trên browser.
- Nếu sử dụng Nginx `proxy_cookie_path`, chỉ rewrite khi thật sự cần và tránh nhân đôi prefix. Quy tắc thay cookie path chỉ xử lý cookie, không sửa link/controller mapping.

Với OAuth, login và biểu mẫu dùng cookie, cần xem chính sách **Secure/HttpOnly/SameSite**, origin, CSRF token và redirect URLs cùng lúc. Redirect sang `http` hoặc host khác có thể khiến cookie không gửi, tạo login loop dù session trên server vẫn còn.

**Không xuất cookie session, CSRF token, Authorization header hoặc access token trong endpoint debug hay log công khai.**

## 12. CORS có liên quan nhưng không đồng nghĩa với forwarded URL

CORS là cơ chế **browser** áp dụng khi JavaScript từ origin A muốn đọc response từ origin B. Một origin gồm scheme, host và port, **không gồm path prefix**:

```text
https://app.example.com/portal
https://app.example.com/another
  -> cùng origin

https://app.example.com
https://api.example.com
  -> khác host, khác origin

http://app.example.com
https://app.example.com
  -> khác scheme, khác origin
```

Nếu website public tại `https://app.example.com` gọi API tại `https://api.example.com`, cần CORS policy phù hợp với **public browser origin**, không phải `http://app-service:8080` của mạng nội bộ.

Ví dụ CORS allowlist cho Spring MVC (snippet cấu hình, **không cần đặt vào project demo nếu mọi request cùng origin**):

```java
@Configuration
class CorsConfig implements WebMvcConfigurer {
    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
            .allowedOrigins("https://app.example.com")
            .allowedMethods("GET", "POST")
            .allowedHeaders("Content-Type", "Authorization");
    }
}
```

Cần import `org.springframework.context.annotation.Configuration`, `org.springframework.web.servlet.config.annotation.WebMvcConfigurer` và `CorsRegistry`. Khi có Spring Security, tích hợp CORS theo filter chain để **preflight OPTIONS** được xử lý trước cơ chế xác thực ngăn request; không tắt authentication chỉ để “sửa CORS”.

**Không** dùng `Access-Control-Allow-Origin: *` kết hợp credentialed cross-origin requests; không phản chiếu arbitrary `Origin` mà không có allowlist. CORS **không** bảo vệ API khỏi curl/server-to-server traffic và không thay thế CSRF/authentication/authorization.

Một request có scheme/host sai trong backend sau proxy có thể làm logic xây link và so sánh origin sai, nhưng **không nên sửa bằng cách mở rộng CORS cho mọi domain**. Sửa forwarded headers và public URL trước, sau đó cấu hình origin allowlist đúng nhu cầu.

## 13. Các lỗi hay gặp và cách điều tra

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra và sửa |
| --- | --- | --- |
| Redirect `Location: http://localhost:8080/...` | Thiếu `X-Forwarded-Proto/Host` hoặc app không xử lý | Kiểm tra edge headers, `server.forward-headers-strategy`, HTTP response từ public URL |
| Browser bị mixed content | URL absolute được tạo bằng scheme HTTP nội bộ | Sửa forwarded proto hoặc dùng HTTPS canonical base |
| Link thiếu `/portal` | Proxy strip path nhưng app không biết prefix | Kiểm tra `X-Forwarded-Prefix`, filter/version, template/router public base |
| Link thành `/portal/portal` | Vừa cấu hình context path vừa thêm prefix bằng tay | Chuẩn hóa mô hình rewrite hoặc preserve, tránh double-prefix |
| Một route 404 chỉ qua proxy | Sai `location`/`proxy_pass` hoặc prefix/trailing slash | So sánh URI vào Nginx và URI upstream thực nhận |
| OAuth `redirect_uri_mismatch` | Callback được tạo bằng internal scheme/host/path | So sánh public redirect và IdP registered URI |
| Login loop / cookie không gửi | Cookie `Secure`/`Path`/SameSite không khớp, redirect host sai | Kiểm tra `Set-Cookie` và Cookie request kế tiếp ở browser |
| Redirect sang domain lạ từ request header | Proxy chuyển tiếp host/forwarded giá trị không tin | Strip/override ở edge, host allowlist, canonical URL cho links quan trọng |
| IP ghi nhận trong log là IP proxy | Chưa xử lý trusted `X-Forwarded-For` | Thiết kế trust chain, access log configuration, không chọn IP client mù quáng |
| Test local pass nhưng prod sai | CDN/ingress có routing/headers khác Nginx local | Test direct-to-backend và qua URL thực tế, xác định từng hop |
| CORS fail dù URL link đúng | Public origin/credentials/preflight config chưa khớp | Review `Origin`, `Access-Control-Allow-Origin`, OPTIONS, Spring Security CORS |
| Proxy dùng HTTPS nhưng `request.isSecure()` sai | Không áp dụng trusted forwarded proto ở backend | Kiểm tra `framework`/`native` và proxy headers, cookie policy |

### Các phép kiểm hữu ích

**Xem response headers từ ngoài:**

```bash
curl -k -I https://app.example.com/portal/demo/inspect
```

`-I` gửi **HEAD**; chỉ dùng nếu endpoint tương thích HEAD. `-k` bỏ xác minh TLS và **chỉ dành cho debug chứng chỉ trong môi trường được phép**, không dùng cho kiểm thử bảo mật cuối cùng; khi kiểm thử thật hãy bỏ `-k` để kiểm tra certificate chain đúng.

**Xem redirect mà không tự đi theo:**

```bash
curl -i https://app.example.com/portal/demo/next
```

Kiểm tra `Location`; phải có scheme, host và path công khai đúng. Nếu dùng `curl -L`, client sẽ đi theo redirect và có thể che mất nơi xảy ra redirect sai.

**Kiểm tra host header bị spoof ở edge (chỉ trong hạ tầng bạn được phép kiểm thử):**

```bash
curl -i https://app.example.com/portal/demo/next \
  -H "X-Forwarded-Host: attacker.invalid"
```

Nếu edge được cấu hình đúng, header từ Internet phải bị xóa/ghi đè, và Location vẫn phải trỏ tới domain cho phép. **Việc demo `/demo/next` luôn canonical không chứng minh edge đã an toàn**; kiểm tra thêm ở endpoint request metadata, access logs được kiểm soát và gateway config.

**Quan sát path có được rewrite không:**

- Request ngoài: `/portal/demo/inspect`.
- Upstream dự kiến: `/demo/inspect`.
- Controller mapping: `@GetMapping("/demo/inspect")` kết hợp với `@RequestMapping("/demo")` theo class.
- Nếu upstream vẫn thấy `/portal/demo/inspect`, kiểm tra dấu `/` trong `proxy_pass` và `location`.
- Không tự áp dụng `server.servlet.context-path=/portal` vào ứng dụng khi proxy đang strip `/portal`.

## 14. Cách kiểm thử ở production-like mà không dùng header giả tùy tiện

Một bộ test QA nên có hai tuyến riêng:

1. **Direct-to-app trong môi trường cô lập:** xác minh Spring nhận `Forwarded`/`X-Forwarded-*` đúng theo contract mà proxy dự kiến gửi. Các test Java ở phần 9 minh họa nhóm này. Không xem đây là bằng chứng trust boundary đã an toàn.
2. **Qua proxy/ingress/CDN thực:** request tới public HTTPS domain; xác nhận scheme, host, port, path, links và redirects đúng. Đồng thời cố tình gửi header spoofed ở **edge** để xác nhận chúng bị loại và không ảnh hưởng backend.

Checklist theo hành vi:

- [ ] `https://app.example.com/portal/demo/inspect` thực sự route tới controller đúng.
- [ ] `request.getScheme()` là `https` sau khi áp dụng trusted forwarded metadata.
- [ ] `request.getServerName()` là public host đã phê duyệt, không phải internal DNS.
- [ ] Port thể hiện external port, không phải 8080 nếu client dùng HTTPS 443.
- [ ] URL động/templating có prefix `/portal` đúng **một lần** khi contract yêu cầu.
- [ ] Redirect `Location` không bao giờ chứa `http://app-service:8080` hoặc domain attacker.
- [ ] Link email, webhook, OAuth callback được xây từ canonical/allowlisted public URL.
- [ ] Cookie `Secure`, `HttpOnly`, `SameSite`, `Path` phù hợp trên public HTTPS.
- [ ] CORS allowed origins chứa đúng scheme/host/port, không sao chép backend URL.
- [ ] Proxy strip/override cả `Forwarded` và `X-Forwarded-*` từ input không tin cậy.
- [ ] Backend chỉ truy cập được từ trusted proxy/sidecar hoặc private network.
- [ ] Không tăng quyền hoặc coi `X-Forwarded-For` là nguồn xác thực trước khi trust chain hợp lệ.
- [ ] Không tạo redirect loop tại `/portal` → `/portal/` hoặc HTTP→HTTPS.
- [ ] Proxy, framework, container, Spring Security đều được cập nhật bản vá.

## 15. Ghi chú với Spring WebFlux

Ví dụ chính dùng **Spring MVC** (`jakarta.servlet.http.HttpServletRequest` và `ForwardedHeaderFilter`). Với **Spring WebFlux**, request không được bao bởi Servlet filter; Spring Framework dùng **`ForwardedHeaderTransformer`** trước khi dispatch để cập nhật các thông tin scheme/host/prefix theo header được phép.

Ví dụ snippet minh họa (không phải ứng dụng WebFlux độc lập):

```java
// Trong WebFlux handler; exchange là ServerWebExchange hợp lệ.
URI requestUri = exchange.getRequest().getURI();
String path = exchange.getRequest().getPath().value();
```

Cần import `java.net.URI` và API WebFlux thích hợp, không sử dụng `HttpServletRequest` hay `ServletUriComponentsBuilder` ở stack Netty. Spring Boot `server.forward-headers-strategy=framework` tích hợp hướng xử lý phù hợp với stack, nhưng **trust boundary ở proxy vẫn là bắt buộc**.

Nếu WebFlux dùng `X-Forwarded-Prefix`, kiểm tra cụ thể behavior `ForwardedHeaderTransformer` theo version và contract gateway. Với response link nghiêm ngặt, canonical base config vẫn hữu ích.

## 16. Tự kiểm tra

**Câu 1.** Browser gọi `https://app.example.com/portal/orders` nhưng backend nhận `http://10.0.0.5:8080/orders`. Đây có nhất thiết là bug không?  
**Đáp:** Không; đây có thể là TLS termination và path prefix rewrite đúng. Bug phát sinh khi app dùng internal scheme/host/path để sinh public URL hoặc proxy không route tương ứng.

**Câu 2.** Chỉ đặt `X-Forwarded-Proto: https` đã đủ để khôi phục mọi public URL chưa?  
**Đáp:** Chưa. Còn public host/port và có thể prefix. Quan trọng hơn là chỉ tin header do proxy hợp lệ đặt.

**Câu 3.** `server.forward-headers-strategy=framework` có an toàn nếu người ngoài gọi thẳng port 8080 không?  
**Đáp:** Không. Khi đó client có thể tự gửi forwarded headers. Backend phải nằm sau trust boundary và edge phải sanitize headers.

**Câu 4.** Vì sao không dùng `X-Forwarded-Host` trực tiếp để tạo link reset password?  
**Đáp:** Vì host có thể bị giả mạo nếu edge xử lý sai. Nên dùng canonical public base/allowlist.

**Câu 5.** Proxy strip `/portal`, nhưng backend đặt `server.servlet.context-path=/portal` thì thường xảy ra gì?  
**Đáp:** Request đến backend thiếu path context cần thiết, dễ bị 404. Phải thống nhất rewrite/preserve.

**Câu 6.** Có phải `X-Forwarded-Prefix` lúc nào cũng tự được hiểu ở `native` mode không?  
**Đáp:** Không. Native support tùy container/version; phải kiểm tra `request.getContextPath()` và generated links hoặc dùng mô hình khác.

**Câu 7.** Hai path `/portal` và `/other` trên cùng `https://app.example.com` có là hai CORS origins không?  
**Đáp:** Không. Origin gồm scheme/host/port, không gồm path.

**Câu 8.** Nếu proxy HTTPS→HTTP, session cookie `Secure` có bị vô hiệu ở browser không?  
**Đáp:** Không, nếu browser truy cập HTTPS public URL và cookie được phát phù hợp. Nhưng phải bảo đảm request metadata/headers và cookie config đúng.

**Câu 9.** Redirect `Location: https://app.example.com/demo` thay vì `/portal/demo` có thể do đâu?  
**Đáp:** Framework không nhận public prefix, template hardcode root path hoặc proxy rewrite path không thống nhất.

**Câu 10.** Test Java gọi thẳng backend với `X-Forwarded-Host: app.example.com` pass đã chứng minh Nginx không nhận header giả mạo từ Internet chưa?  
**Đáp:** Chưa. Phải test **qua edge** và kiểm tra cấu hình proxy/trust chain.

## 17. Tài liệu chính thức

- Spring Boot 3.5 — *Embedded Web Servers / Running Behind a Front-end Proxy Server*: https://docs.spring.io/spring-boot/3.5/how-to/webserver.html
- Spring Framework 6.2 — *Servlet Filters / Forwarded Headers / X-Forwarded-Prefix*: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/filters.html
- Spring Framework — *ServletUriComponentsBuilder API*: https://docs.spring.io/spring-framework/docs/6.2.11/javadoc-api/org/springframework/web/servlet/support/ServletUriComponentsBuilder.html
- Spring Framework — *WebFlux Forwarded Headers*: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Spring Security — *CORS Integration*: https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html
- Spring Security — *OAuth2 Login*: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
- Nginx — *ngx_http_proxy_module / proxy_pass và proxy_set_header*: https://nginx.org/en/docs/http/ngx_http_proxy_module.html
- RFC 7239 — *Forwarded HTTP Extension*: https://www.rfc-editor.org/rfc/rfc7239
- MDN — *Same-origin policy*: https://developer.mozilla.org/en-US/docs/Web/Security/Same-origin_policy
- OWASP — *Unvalidated Redirects and Forwards*: https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html

**Kết luận:** khi Spring Boot chạy phía sau reverse proxy, không coi request nội bộ là địa chỉ công khai. Trước tiên chọn contract về TLS termination, host, port và prefix rewrite; tiếp đến đặt trusted `Forwarded`/`X-Forwarded-*` ở edge và chọn mode xử lý phù hợp trong Spring; cuối cùng xác nhận **redirect, link, cookie, OAuth callback và CORS origin** qua URL HTTPS thực. Với link security-sensitive, dùng canonical public base đã được kiểm soát để tránh phụ thuộc dữ liệu header không đáng tin.