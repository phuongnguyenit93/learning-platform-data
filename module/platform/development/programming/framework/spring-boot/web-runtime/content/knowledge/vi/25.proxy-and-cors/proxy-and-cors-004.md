# Chỉ tin thông tin chuyển tiếp từ proxy được kiểm soát

## 1. Bài toán: thông tin về request có thể bị thay đổi trên đường đi

Ứng dụng Spring Boot thường không nhận trực tiếp kết nối HTTPS từ người dùng. Giữa browser và ứng dụng có thể là CDN, API gateway, ingress controller, load balancer hay reverse proxy NGINX. Proxy nhận request công khai, có thể kết thúc TLS, sau đó gọi HTTP đến ứng dụng nội bộ. Vì vậy Spring Boot nhìn thấy kết nối **từ proxy**, không phải kết nối gốc.

```text
Browser
  198.51.100.25
  https://api.example.test/orders
        │ TLS/HTTPS
        ▼
Edge reverse proxy / ingress
  10.0.0.10
  TLS termination + xác nhận host + chuẩn hóa headers
        │ HTTP nội bộ
        │ X-Forwarded-For: 198.51.100.25
        │ X-Forwarded-Proto: https
        │ X-Forwarded-Host: api.example.test
        │ X-Forwarded-Port: 443
        ▼
Spring Boot (Tomcat hoặc Reactor Netty)
  10.0.1.20:8080
  request.getRemoteAddr() vật lý ban đầu = địa chỉ proxy
  request.getScheme() vật lý ban đầu = http
        │
        ▼
Business handler, redirect, logging, security decisions
```

Để ứng dụng tạo link/redirect phù hợp với URL công khai, proxy có thể gửi **forwarded headers**. Tuy nhiên các header ấy bản chất vẫn là **dữ liệu HTTP**: nếu client có thể tự đưa `X-Forwarded-Host: attacker.invalid` rồi backend tin, request có thể bị đánh lừa.

**Nguyên tắc bắt buộc:** ứng dụng chỉ dùng thông tin chuyển tiếp khi nó được gửi qua **một proxy thuộc ranh giới tin cậy**, proxy đã **loại bỏ/ghi đè dữ liệu do client tự khai báo**, và **kết nối tới backend bị giới hạn cho các proxy được phép**. Chỉ bật một property Spring Boot không tự làm cho mạng trở nên an toàn.

Bài hướng tới Spring Boot 3.3.x và Java 17+, bao gồm Spring MVC/Servlet lẫn WebFlux. Mục đích không phải “luôn lấy được IP thật” bằng mọi giá, mà là **biết dữ liệu nào đáng tin, lấy ở đâu, dùng vào việc gì và cách kiểm thử spoofing**.

## 2. Những header nào có thể mang thông tin chuyển tiếp?

### 2.1. RFC 7239: header chuẩn `Forwarded`

Ví dụ:

```http
Forwarded: for=198.51.100.25;proto=https;host=api.example.test
```

Các directive thường thấy:

- `for=...`: địa chỉ client/peer ở một hop; có thể là IP, IPv6 dạng quoted/bracketed hoặc một identifier bị ẩn danh theo RFC.
- `by=...`: interface/định danh proxy phía gửi.
- `proto=http|https`: scheme của kết nối trước proxy.
- `host=...`: authority/host ban đầu do proxy mô tả.

Nếu qua nhiều proxy, có thể có **nhiều phần tử** phân tách bằng dấu phẩy. Không tự parse header chuẩn bằng `split(",")` hoặc `split(";")` cho mục đích bảo mật: cú pháp quoted-string, IPv6 và escaping có thể phức tạp. Dùng parser/framework được hỗ trợ và chính sách hop rõ ràng.

RFC 7239 quy định thông tin này **không thể mặc nhiên coi là chính xác** vì client hoặc bất kỳ hop nào trên đường truyền có thể tạo/sửa nó. Đó là lý do phải thiết lập ranh giới tin cậy ở mạng/proxy.

### 2.2. Họ header `X-Forwarded-*`

| Header | Ý nghĩa thường dùng | Rủi ro nếu tin từ client |
|---|---|---|
| `X-Forwarded-For` | Danh sách IP client/proxy qua các hop | Bypass IP allowlist/rate limit nếu lấy IP giả |
| `X-Forwarded-Proto` | Scheme công khai (`https`/`http`) | Link/redirect sai; logic HTTPS/cookie phụ thuộc scheme bị sai |
| `X-Forwarded-Host` | Hostname công khai | Host-header poisoning, link reset mật khẩu trỏ tới tên miền kẻ tấn công |
| `X-Forwarded-Port` | Cổng công khai (443, 80, cổng khác) | Redirect/OAuth callback sai port, link độc hại |
| `X-Forwarded-Prefix` | Prefix đã thêm/bỏ trên proxy | Sinh URL/path sai; có thể ảnh hưởng đường dẫn redirect |
| `X-Forwarded-Ssl` | Quy ước cũ để biểu diễn SSL ở một số proxy | Mâu thuẫn với `X-Forwarded-Proto` |
| `X-Real-IP` | IP mà một số proxy tự đặt | Nếu pass-through từ client, chỉ là IP do attacker nói |

Một số implementation chỉ dùng tập con header. Spring Boot/embedded server không hứa xử lý mọi loại và mọi thứ tự giống nhau. **Không để cùng lúc `Forwarded` và `X-Forwarded-*` từ những nguồn không đồng nhất**, vì thư viện A có thể ưu tiên loại này, thư viện B ưu tiên loại kia.

Ví dụ **request độc hại**:

```http
GET /forgot-password HTTP/1.1
Host: api.example.test
Forwarded: for=192.0.2.99;proto=https;host=attacker.invalid
X-Forwarded-For: 192.0.2.99
X-Forwarded-Host: attacker.invalid
X-Forwarded-Proto: https
```

Các địa chỉ `198.51.100.0/24` và `192.0.2.0/24` dùng trong ví dụ là dải tài liệu, không phải địa chỉ Internet của người dùng thật. Nếu ứng dụng tạo link reset từ host được spoof, nó có thể gửi `https://attacker.invalid/...` cho người dùng. Dùng forwarded host trong các flow nhạy cảm **không được thay thế kiểm soát public URL/canonical host**.

## 3. Ranh giới tin cậy: ba lớp phòng vệ phải đồng thời tồn tại

| Lớp | Mục đích | Ví dụ |
|---|---|---|
| **Mạng/transport** | Chỉ proxy được phép kết nối tới backend | `server.address` nội bộ, firewall/security group, Kubernetes NetworkPolicy, mTLS nếu cần |
| **Edge proxy** | Loại bỏ/ghi đè mọi forwarded header không đáng tin ở ranh giới công khai | NGINX `proxy_set_header X-Forwarded-For $remote_addr`, `Forwarded ""`, host allowlist |
| **Framework/container** | Chỉ diễn giải header theo cấu hình và proxy/hop phù hợp | Spring Boot `server.forward-headers-strategy`, Tomcat `RemoteIpValve`, trusted proxies |

Một trong ba lớp thiếu vẫn gây nguy cơ. Ví dụ:
- Backend **publicly reachable** mà bật `FRAMEWORK`: client trực tiếp có thể tự gửi header giả.
- NGINX pass-through `X-Forwarded-For` từ client, backend chỉ lấy phần tử đầu: IP spoofing vẫn có thể xảy ra dù request đi qua NGINX.
- Edge sanitize tốt nhưng một sidecar/instance khác trong mạng nội bộ có thể gửi thẳng tới backend: không thể mặc định mọi nguồn private IP là proxy đáng tin.
- Backend giới hạn mạng nhưng tin `X-Forwarded-Host` do CDN giữ nguyên từ user: absolute URLs vẫn có thể bị đầu độc.

**Nguồn tin cậy là kết nối tới peer đã xác thực/cho phép và quy trình proxy tạo header, không phải tên header.** Dữ liệu `Forwarded` không có chữ ký mặc định. TLS giữa client và edge không chứng minh forwarded headers đi từ client đã được lọc nếu edge vẫn chuyển tiếp chúng nguyên vẹn.

## 4. Khi nào nên bỏ qua hoàn toàn forwarded headers?

Nếu ứng dụng nhận kết nối trực tiếp, hoặc chưa đảm bảo ranh giới proxy, dùng:

```properties
server.forward-headers-strategy=none
```

`NONE` nói với Boot không áp cơ chế chuyển tiếp do Boot cấu hình. Khi đó request metadata thường phản ánh **kết nối trực tiếp tới embedded server**; không tự suy ra scheme/host/IP client từ `X-Forwarded-*`.

Lưu ý: `NONE` **không biến các raw headers thành dữ liệu an toàn hoặc loại chúng khỏi request**. Code tùy biến gọi `request.getHeader("X-Forwarded-For")` vẫn sẽ đọc được chuỗi client gửi. Nếu thực sự muốn header biến mất ở ứng dụng, chặn tại proxy hoặc dùng filter/transformer loại bỏ trong trường hợp phù hợp.

Trong Spring Framework Servlet có `ForwardedHeaderFilter` với `setRemoveOnly(true)` để **ẩn/loại những header kiểu Forwarded mà không diễn giải chúng**. Ở WebFlux có `ForwardedHeaderTransformer.setRemoveOnly(true)`. Đây là lựa chọn nâng cao khi không muốn application layer nhìn thấy header, nhưng **không nên chồng tùy tiện filter remove-only lên pipeline NATIVE đã dùng header**. Tốt nhất vẫn loại tại ranh giới edge.

Đặt tên property ở đây theo Spring Boot 3.3; hãy kiểm tra version thực tế trước khi dùng một option của những bản khác.

## 5. Ba chiến lược `server.forward-headers-strategy` trong Spring Boot

| Giá trị | Thành phần sử dụng | Khi nào phù hợp | Điều kiện bảo mật |
|---|---|---|---|
| `NONE` | Không bật forwarded processing của Boot | Không có proxy tin cậy, app truy cập trực tiếp | Code không tự tin raw headers |
| `NATIVE` | Native support từ embedded server/container (Tomcat `RemoteIpValve`, support tùy server) | Proxy gửi các header quen thuộc, bạn có thể giới hạn trusted proxy theo server | Kiểm tra peer/hop trust, edge sanitize, network ACL |
| `FRAMEWORK` | Spring MVC `ForwardedHeaderFilter` hoặc WebFlux `ForwardedHeaderTransformer` | Cần behavior do Spring Framework xử lý thay native | **Framework không thể tự biết header do proxy đáng tin hay client giả mạo**; edge filtering là bắt buộc |

Spring Boot 3.3 có thể mặc định `NATIVE` trong một số cloud environment được nhận diện; ở môi trường khác mặc định có thể là `NONE`. **Đừng dựa vào giá trị mặc định mơ hồ:** khai báo tường minh từng deployment/profile và test qua proxy thật.

Đối với **Tomcat** sử dụng `NATIVE`, Spring Boot cung cấp các property liên quan:
- `server.tomcat.remoteip.internal-proxies`: regular expression của địa chỉ proxy được coi là internal/trusted tại kết nối.
- `server.tomcat.remoteip.trusted-proxies`: proxy trung gian tin cậy xuất hiện trong chuỗi, tùy contract `RemoteIpValve`.
- `server.tomcat.remoteip.remote-ip-header`: tên header chứa chuỗi IP (thường `x-forwarded-for`).
- `server.tomcat.remoteip.protocol-header`: header chứa protocol gốc (thường `x-forwarded-proto`).
- `server.tomcat.remoteip.host-header` và `port-header`: header host/port dùng để xây metadata.

**Không đặt `server.tomcat.remoteip.internal-proxies` thành rỗng để “trust all” trong production.** Các dải private `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` có thể chứa cả workload không đáng tin trong VPC/Kubernetes. Thu hẹp theo IP/CIDR của hop proxy thực sự và chặn mọi kết nối khác ở mạng.

Tomcat xử lý chuỗi proxy theo thuật toán/trust settings của `RemoteIpValve`. Không tự dùng logic `X-Forwarded-For.split(",")[0]` để đưa quyết định IP allowlist; giá trị trái nhất có thể do client tạo. Với nhiều proxy, thứ tự và cách chọn IP client phụ thuộc chính sách tin cậy, bắt đầu từ peer mạng gần ứng dụng.

## 6. Ví dụ chạy được: Spring Boot MVC quan sát metadata sau proxy

Ví dụ độc lập sử dụng **Java 17+, Spring Boot 3.3.13, Gradle**, chạy Tomcat MVC. Endpoint `/inspect` hiển thị thông tin **đã được embedded server xử lý** và URL tạo từ request. Chỉ dùng endpoint này để học và kiểm thử; trong production không public endpoint debug có thể tiết lộ topology.

### 6.1. Cấu trúc project

```text
proxy-trust-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/proxytrust/ProxyTrustApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/proxytrust/ForwardedHeadersIgnoredTest.java
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/resources/application.properties`:**

```properties
server.port=8080
# Demo chỉ cho NGINX cùng máy gọi Tomcat.
# Môi trường container cần cấu hình bind và firewall/NetworkPolicy khác.
server.address=127.0.0.1

# Chỉ diễn giải forwarded headers qua Tomcat RemoteIpValve.
server.forward-headers-strategy=native

# Ví dụ một hop proxy chạy trên localhost.
# Trong .properties, hai dấu backslash -> một backslash regex sau parse.
server.tomcat.remoteip.internal-proxies=127\\.0\\.0\\.1
server.tomcat.remoteip.remote-ip-header=x-forwarded-for
server.tomcat.remoteip.protocol-header=x-forwarded-proto
server.tomcat.remoteip.host-header=x-forwarded-host
server.tomcat.remoteip.port-header=x-forwarded-port

# Khi TLS terminate tại proxy, tránh redirect context-root quá sớm.
server.tomcat.redirect-context-root=false
```

**Nhận xét quan trọng:** `internal-proxies` được chọn cho **một hop loopback của demo**, không phải regex phù hợp toàn thế giới. Khi deploy thực tế phải thay bằng peer proxy/network phù hợp, không trust mặc định toàn bộ private network. Việc ràng buộc `server.address=127.0.0.1` chỉ phù hợp NGINX và backend trên cùng host/net namespace; trong Kubernetes/Docker khác network, phải dùng bind nội bộ, firewall và policies tương ứng.

**`src/main/java/com/example/proxytrust/ProxyTrustApplication.java`:**

```java
package com.example.proxytrust;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@SpringBootApplication
public class ProxyTrustApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProxyTrustApplication.class, args);
    }
}

@RestController
class ProxyDiagnosticController {

    @GetMapping("/inspect")
    RequestView inspect(HttpServletRequest request) {
        String exampleLink = ServletUriComponentsBuilder
                .fromCurrentContextPath()
                .path("/done")
                .toUriString();

        return new RequestView(
                request.getScheme(),
                request.isSecure(),
                request.getServerName(),
                request.getServerPort(),
                request.getRemoteAddr(),
                exampleLink);
    }

    @GetMapping("/done")
    ResponseEntity<String> done() {
        return ResponseEntity.status(HttpStatus.OK).body("done");
    }
}

record RequestView(
        String scheme,
        boolean secure,
        String host,
        int port,
        String remoteAddress,
        String exampleLink) {}
```

Chỉ có một top-level `public class` trong file Java; `ProxyDiagnosticController` và `RequestView` package-private là hợp lệ. `ServletUriComponentsBuilder` được dùng ở endpoint **chẩn đoán** để thấy sự khác biệt giữa URL nội bộ và URL công khai. Đừng dùng một URL dựa trên request host không được whitelist cho OAuth callback, reset password hoặc những action nhạy cảm.

**Chạy app:**

```bash
gradle bootRun
```

Nếu có Gradle Wrapper, có thể dùng `./gradlew bootRun` (Linux/macOS) hoặc `.\gradlew.bat bootRun` (Windows PowerShell). Yêu cầu JDK 17+ và Gradle tương thích Boot 3.3.x.

Nếu gửi request trực tiếp từ local vào backend:

```bash
curl -s http://127.0.0.1:8080/inspect
```

Khi không có forwarded headers, response JSON phản ánh kết nối HTTP local. Các trường chính thường có dạng:

```json
{
  "scheme": "http",
  "secure": false,
  "host": "127.0.0.1",
  "port": 8080,
  "remoteAddress": "127.0.0.1",
  "exampleLink": "http://127.0.0.1:8080/done"
}
```

Đây là output **minh họa**, phụ thuộc hostname mà curl gửi, địa chỉ loopback IPv4/IPv6 và server implementation. Đừng assert mọi chuỗi không liên quan tới nghiệp vụ như địa chỉ loopback nếu môi trường khác.

**Cảnh báo về test trực tiếp:** do demo cấu hình **tin peer loopback**, bất kỳ tiến trình local có thể gọi thẳng cổng 8080 và **tự spoof forwarded headers**. Việc này không chứng minh backend an toàn trước attacker có quyền local. Nó chỉ mô phỏng môi trường NGINX chạy trên cùng host. Trong production phải giới hạn **ai được kết nối tới backend** và xác định threat model cho mọi tiến trình cùng network namespace.

## 7. Ví dụ NGINX: ghi đè header, không tiếp tục chuyển nguyên giá trị từ client

Trong mô hình một hop:
- HTTP client bên ngoài kết nối tới **edge NGINX**.
- NGINX xác định host được phép và tạo **bộ header chuẩn hóa**.
- Spring Boot chỉ nhận kết nối từ NGINX.
- Ứng dụng dùng `server.forward-headers-strategy=native` đã cấu hình ở mục 6.

Ví dụ cấu hình NGINX **local lab** sau đặt bên trong cấu hình `http { ... }` của NGINX, không phải file `nginx.conf` standalone:

```nginx
# Host không khớp sẽ không vào app.
server {
    listen 127.0.0.1:8088 default_server;
    server_name _;
    return 421;
}

server {
    listen 127.0.0.1:8088;
    server_name localhost;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;

        # Host cố định cho virtual host hợp lệ.
        proxy_set_header Host localhost;

        # Chỉ dùng họ X-Forwarded do NGINX tái tạo.
        # Không pass header RFC Forwarded do client đưa tới.
        proxy_set_header Forwarded "";

        # Một hop edge: thay thế, KHÔNG nối với header client gửi.
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host localhost;
        proxy_set_header X-Forwarded-Port $server_port;

        # Loại thông tin không nằm trong policy của demo.
        proxy_set_header X-Forwarded-Prefix "";
        proxy_set_header X-Forwarded-Ssl "";
        proxy_set_header X-Forwarded-Server "";
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

**Điểm cần hiểu:**
- `proxy_set_header X-Forwarded-For $remote_addr` **thay** giá trị với địa chỉ socket mà NGINX thực sự thấy. Khác `$proxy_add_x_forwarded_for`, giá trị của client **không bị nối vào chuỗi**. Đây là chọn lựa đơn giản phù hợp khi NGINX là **edge đầu tiên**, không có một proxy hợp lệ nào ở phía trước.
- `proxy_set_header Forwarded ""` và các header rỗng được NGINX **không chuyển tới upstream**. Điều này ngăn xung đột giữa `Forwarded` RFC và `X-Forwarded-*` do NGINX chuẩn hóa.
- `X-Forwarded-Proto=$scheme` lấy scheme mà NGINX thực sự nhận, không lấy từ client-provided `X-Forwarded-Proto`. Ở lab HTTP 8088, giá trị phải là `http`; ở TLS-terminating NGINX sẽ là `https`.
- `Host localhost` và `X-Forwarded-Host localhost` dùng giá trị cố định, không dùng thẳng `$http_host` client gửi. Khi phục vụ nhiều hostname, phải có **allowlist/virtual host routing** rõ ràng và đặt host đã kiểm tra.
- `X-Forwarded-Port=$server_port` lấy cổng mà NGINX listen, ở lab là 8088. Nếu deployment có port-mapping hoặc CDN bên ngoài, đây có thể không phải external port; cần lấy thông tin từ **hạ tầng đáng tin**, không từ header client tự gửi.
- Một cấu hình `default_server` từ chối host lạ; ở TLS còn phải xem SNI/certificate đúng và hợp đồng HTTP authority, không chỉ `server_name`.

Đây là lab **HTTP nội bộ** để cô lập vấn đề forwarded headers, **không phải cấu hình public production**. Triển khai thực tế cần TLS termination, cổng public, bảo vệ ingress, timeouts, size limits, security headers và quyền mạng thích hợp.

### 7.1. Kiểm tra rằng NGINX không giữ header giả

Khi NGINX đã load config và Spring Boot còn chạy:

```bash
curl -s \
  -H 'Forwarded: for=192.0.2.99;proto=https;host=attacker.invalid' \
  -H 'X-Forwarded-For: 192.0.2.99' \
  -H 'X-Forwarded-Host: attacker.invalid' \
  -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Port: 443' \
  -H 'Host: localhost' \
  http://127.0.0.1:8088/inspect
```

Kỳ vọng từ metadata mà server đã xử lý:

```json
{
  "scheme": "http",
  "secure": false,
  "host": "localhost",
  "port": 8088,
  "remoteAddress": "127.0.0.1",
  "exampleLink": "http://localhost:8088/done"
}
```

Đây là **kết quả minh họa trong lab IPv4 loopback**; có thể khác khi NGINX/Java bind IPv6 hoặc khi nginx config khác. Điều bắt buộc cần assert là **không có `attacker.invalid`**, scheme không chuyển sang `https` theo request giả và port không bị ép 443. Header `Forwarded` của client đã bị bỏ; `X-Forwarded-*` của client đã bị ghi đè.

Thử host không nằm trong allowlist:

```bash
curl -i -H 'Host: attacker.invalid' \
  http://127.0.0.1:8088/inspect
```

Kỳ vọng NGINX chọn `default_server` trả HTTP **421** mà không proxy vào Spring Boot. Ở lab, `421` là lựa chọn từ cấu hình NGINX, không phải status Spring Boot tự sinh.

### 7.2. Tại sao `$proxy_add_x_forwarded_for` có thể gây rủi ro?

Directive rất phổ biến:

```nginx
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
```

Biến này xây danh sách bằng cách **giữ giá trị `X-Forwarded-For` đã có rồi thêm `$remote_addr`**. Nó phù hợp ở những vị trí/hợp đồng cụ thể của chuỗi nhiều proxy, nhưng **không đủ** để loại dữ liệu client tự khai báo ở edge đầu tiên. Nếu client gửi `X-Forwarded-For: 192.0.2.99`, upstream có thể thấy `192.0.2.99, 198.51.100.25`. Một ứng dụng chọn token trái nhất sẽ nhận IP giả.

Cách an toàn ở edge đơn giản là **ghi đè hoàn toàn**. Trong hệ nhiều proxy, dùng thuật toán duyệt hop đáng tin **từ peer gần ứng dụng ra ngoài**, và chỉ chấp nhận các hop có xác thực/allowlist. Không dùng “lấy token đầu tiên” như quy tắc toàn cục.

## 8. Khi TLS kết thúc ở proxy: giữ scheme chính xác và tránh redirect sai

Production thường có:

```text
Browser --HTTPS:443--> NGINX --HTTP:8080--> Spring Boot
                         │
                   X-Forwarded-Proto: https
                   X-Forwarded-Host: api.example.test
                   X-Forwarded-Port: 443
```

Nếu Boot chỉ nhìn kết nối HTTP 8080, nó có thể:
- Tạo `http://...` trong `Location` redirect dù người dùng truy cập HTTPS.
- Sinh absolute URL sai scheme/port (liên quan OAuth callback, email links, redirect).
- Đánh giá `request.isSecure()` là false ở những logic dựa vào Servlet API.
- Lộ hostname/port nội bộ trong link.
- Tạo redirect loop khi proxy lại ép HTTP→HTTPS và backend cũng redirect.

Trong NGINX **đang thực sự terminate TLS**, có thể sinh headers từ metadata đáng tin:

```nginx
# Mảnh cấu hình cho một server TLS được kiểm soát:
proxy_set_header X-Forwarded-Proto $scheme;      # https
proxy_set_header X-Forwarded-Host api.example.test;
proxy_set_header X-Forwarded-Port 443;
proxy_set_header Host api.example.test;
proxy_set_header X-Forwarded-For $remote_addr;
proxy_set_header Forwarded "";
```

Đoạn này chỉ là **mảnh cấu hình**, cần `listen 443 ssl`, certificate/key hợp lệ, `proxy_pass`, virtual host validation và network ACL. Không dán nguyên vào NGINX như một file chạy độc lập.

Với **Spring Boot 3.3 + Tomcat**, `server.tomcat.redirect-context-root=false` là lưu ý được tài liệu Boot nêu khi SSL terminate tại proxy, để header protocol được xử lý trước redirect context root. Dùng cùng với **proxy sanitization và trusted peer constraints**; property này không thay thế bất kỳ lớp bảo mật nào.

Không được nhận `X-Forwarded-Proto: https` như bằng chứng kết nối HTTPS từ một client trực tiếp không qua proxy, vì attacker tự viết được. Tương tự, không được suy từ `X-Forwarded-Host` chưa xác thực rằng redirect URI nằm trong allowlist.

## 9. Nhiều hop proxy: nguyên tắc chọn IP và chính sách tin cậy

Ví dụ:

```text
Client 198.51.100.25
      │
      ▼
CDN proxy 203.0.113.10
      │
      ▼
Ingress proxy 10.0.0.10
      │
      ▼
App 10.0.1.20
```

Từ phía app, socket peer vật lý thường là `10.0.0.10`, còn `X-Forwarded-For` có thể mang một danh sách. Nếu CDN/ingress **đều thuộc chính sách tin cậy** và đã sanitization ở edge, có thể bảo toàn chuỗi hop hợp lệ. Nếu CDN không nằm trong chính sách hoặc client có thể kết nối bỏ qua CDN, danh sách phải được hiểu lại.

**Thuật toán tư duy an toàn:**
1. Xác định **socket peer gần nhất**: có phải proxy mà app cho phép không?
2. Nếu không tin peer, **không sử dụng forwarded headers** cho security decisions.
3. Nếu tin peer, xem giá trị mà peer chắc chắn đã sanitize/ghi đè; với chain nhiều hop cần policy rõ về các IP intermediates.
4. Khi phân tích `X-Forwarded-For`, xét các hop từ phía gần app ra ngoài, **dừng ở hop không đáng tin đầu tiên** theo contract của thư viện/ingress. Không coi IP đầu tiên ở trái là đã xác thực.
5. Kiểm tra `Host`/`Proto`/`Port` tại nguồn có thẩm quyền, không chỉ IP. Một chuỗi IP đáng tin không tự khiến forwarded host được phép là bất kỳ domain nào.

Tomcat `RemoteIpValve` hỗ trợ `internalProxies`/`trustedProxies` để giải quyết mạng nhiều hop; từng version có cú pháp và behavior riêng. Với NGINX ở sau CDN, nếu dùng `real_ip_header`/`set_real_ip_from`, phải đặt **dải IP CDN chính xác và được cập nhật**, tránh `set_real_ip_from 0.0.0.0/0`. Khi đó `$remote_addr` có thể đã được real-ip module thay theo proxy chain, nên cần kiểm thử riêng thay vì giả định nó luôn là socket peer ban đầu.

Không dùng các nguồn không đáng tin như raw `X-Forwarded-For`, `X-Real-IP` hoặc `Forwarded` làm **bằng chứng quyền quản trị**. Nếu IP allowlisting thật sự là requirement, thực hiện ở edge/firewall trước khi tới ứng dụng hoặc dùng module nhận diện trusted proxies đúng chuẩn, kèm thử spoof và audit.

## 10. FRAMEWORK trên MVC và WebFlux: xử lý URL không đồng nghĩa xác thực proxy

Khi `NATIVE` chưa đáp ứng (chẳng hạn proxy dùng `X-Forwarded-Prefix` hoặc native server hỗ trợ hạn chế), Boot có:

```properties
server.forward-headers-strategy=framework
```

- **Spring MVC/Servlet:** `ForwardedHeaderFilter` tạo request/response wrapper để các API như `getScheme()`, `getServerName()`, `getServerPort()`, `isSecure()`, `sendRedirect(...)` phản ánh forwarded metadata.
- **Spring WebFlux:** `ForwardedHeaderTransformer` điều chỉnh reactive `ServerHttpRequest` theo forwarded metadata trước pipeline xử lý.

**Chốt bảo mật:** filter/transformer **không tự xác định** một header tới từ proxy được kiểm soát hay do client trực tiếp gửi. Spring Framework khuyến nghị proxy ở **điểm ranh giới tin cậy** loại bỏ header `Forwarded` và `X-Forwarded-*` do phía ngoài truyền vào.

`removeOnly=true` chỉ **remove** header (không sử dụng). Có thể hữu ích nếu ứng dụng không tin chúng. Nhưng nếu chỉ cần bỏ qua forwarded headers và không có proxy thì ưu tiên `NONE`, và nếu có edge proxy thì sanitize ngay tại edge. Tránh cấu hình đồng thời `NATIVE` + custom `ForwardedHeaderFilter` không được kiểm soát khiến request bị rewrite hai lần hoặc security checks nhìn không đồng nhất.

`FRAMEWORK` có thể làm URL hiển thị đúng trong ứng dụng, nhưng không xác thực client IP/hop chain thay cho ingress. **An toàn hay không phụ thuộc topology và proxy**, không phụ thuộc cái tên `FRAMEWORK`.

## 11. Tạo URL và redirect: cách tránh Host-header poisoning

Các thư viện xây absolute URL từ request metadata có thể dùng `Host`, `scheme`, `port` sau forwarded processing. Nếu những giá trị đó do attacker kiểm soát, hệ thống có thể:
- Gửi link đặt lại mật khẩu đến domain giả.
- Tạo OAuth `redirect_uri` ngoài whitelist, dẫn tới lỗi/flow không mong muốn.
- Tạo `Location` response redirect sang host giả.
- Sinh canonical URL và cache keys sai, gây cache poisoning.
- Tham chiếu API/hình ảnh từ hostname lạ trong HTML/email.

Một số hướng giảm rủi ro:

1. **Allowlist host tại edge** (HTTP Host và HTTP/2 `:authority`, đồng thời kiểm soát TLS SNI khi phù hợp).
2. **Overwrite `X-Forwarded-Host`** bằng hostname đã được xác thực, không giữ nguyên `$http_host` nếu không có validation.
3. Với URL nhạy cảm, **cấu hình public base URL tường minh**, ví dụ:

```properties
app.public-base-url=https://api.example.test
```

Thay vì ghép `request.getServerName()` hoặc `request.getHeader("X-Forwarded-Host")` vào link xác thực, lấy từ cấu hình do vận hành kiểm soát; không gắn token nhạy cảm vào URL nếu có phương án an toàn hơn, và không log đầy đủ URL chứa token.

4. Khi chỉ điều hướng trong cùng origin, ưu tiên **redirect đường dẫn tương đối** theo contract client/framework nếu không cần absolute URL. Điều này giảm phụ thuộc hostname, nhưng vẫn cần kiểm tra các behavior redirect/filter theo version.
5. Với các callback/OAuth, đăng ký và so khớp **redirect URI cố định/allowlist**. Không coi một forwarded host “trông giống domain nội bộ” là đủ.
6. Nếu có `X-Forwarded-Prefix` cho path rewrite, proxy phải tạo prefix từ route hợp lệ và strip giá trị client cung cấp. Không cho client tự chuyển app sang một base path tùy ý.

**Không có một middleware “host filtering” phù hợp mọi hệ thống.** Proxy/gateway nên là nơi chính thức kiểm soát public host; ứng dụng vẫn cần validate các public URLs sử dụng cho nghiệp vụ nhạy cảm.

## 12. Proxy và CORS: hai mô hình tin cậy khác nhau

Tên chủ đề cha có **Proxy và CORS**, nhưng cần phân biệt:

- **Forwarded headers:** mô tả thông tin kết nối qua proxy; phải có **trusted proxy boundary**.
- **CORS `Origin`:** browser báo origin khởi tạo fetch/XHR và enforce policy ở browser. Bản thân header `Origin` có thể được client không phải browser tự tạo; nó **không phải cơ chế authentication**.
- **CSRF:** attacker lợi dụng trình duyệt có cookie credentials gửi request; không được coi CORS allowlist là thay thế toàn bộ bảo vệ CSRF.
- **Authorization:** dựa vào identity/roles/scopes đáng tin, không dựa vào một `X-Forwarded-For` do client khai báo.

Một lỗi nguy hiểm là tự động cấp `Access-Control-Allow-Origin`/`Access-Control-Allow-Credentials` theo `X-Forwarded-Host` hoặc một `Origin` bất kỳ. Allowed origins nên được cấu hình theo public origins thật, không tùy tiện “reflect” host được gửi tới. Đặt proxy trust đúng là cần thiết nhưng **không tự sửa được CORS policy sai**.

Ví dụ các public origins của dịch vụ phải được allowlist rõ ràng như `https://app.example.test`, khác với backend Host `api.example.test`. Nếu dùng cookie cross-site, còn phải cân nhắc `SameSite`, `Secure`, CSRF, credentials và TLS.

## 13. Test chống giả mạo header

Test tốt nhất gồm hai lớp: **unit/integration test của Boot** khi không dùng proxy, và **end-to-end test qua proxy thật** như mục 7.

### 13.1. JUnit + MockMvc: khi NONE thì header giả không biến đổi metadata

Tạo file `src/test/java/com/example/proxytrust/ForwardedHeadersIgnoredTest.java`:

```java
package com.example.proxytrust;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "server.forward-headers-strategy=none"
})
@AutoConfigureMockMvc
class ForwardedHeadersIgnoredTest {

    @Autowired
    MockMvc mvc;

    @Test
    void spoofedHeadersDoNotOverrideSchemeOrHost() throws Exception {
        mvc.perform(get("/inspect")
                        .header("Forwarded",
                                "for=192.0.2.99;proto=https;host=attacker.invalid")
                        .header("X-Forwarded-Host", "attacker.invalid")
                        .header("X-Forwarded-Proto", "https")
                        .header("X-Forwarded-For", "192.0.2.99")
                        .header("X-Forwarded-Port", "443"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.scheme").value("http"))
                .andExpect(jsonPath("$.secure").value(false))
                .andExpect(jsonPath("$.host").value("localhost"));
    }
}
```

Chạy:

```bash
gradle test
```

Khi `server.forward-headers-strategy=none` và không có custom filter xử lý forwarded headers, Spring MVC nhận request metadata mặc định của `MockMvc`: `scheme=http`, `secure=false` và `host=localhost` dù request mang header giả. Test kỳ vọng pass.

**Giới hạn test:** `MockMvc` không chạy qua một proxy thật và không mô phỏng Tomcat `RemoteIpValve` ở socket level. Nó chỉ kiểm tra ứng dụng không tự chấp nhận forwarded headers trong mode `NONE`. **Bài kiểm thử quan trọng nhất cho triển khai `NATIVE` là qua proxy thật**, kèm trường hợp client tự gửi `Forwarded`/`X-Forwarded-*` và trường hợp cố truy cập backend trực tiếp từ nguồn không tin cậy.

### 13.2. Ma trận test cần có trong CI/staging

| Trường hợp | Điều nên xảy ra |
|---|---|
| Client gửi `Forwarded: host=attacker.invalid` vào public edge | Proxy xóa; backend không thấy hostname lạ |
| Client gửi `X-Forwarded-Proto: https` vào edge HTTP | Proxy ghi đè bằng scheme nó biết; app không tự coi request là TLS |
| Client gửi `X-Forwarded-For: 192.0.2.99` | App không dùng IP giả để cho qua allowlist/rate limit |
| Client gửi Host không thuộc public allowlist | Edge từ chối, không route tới app |
| Client cố kết nối thẳng backend từ Internet | Firewall/NetworkPolicy chặn, không chỉ trả kết quả khác |
| Proxy hợp lệ gửi HTTPS host/port đúng | App tạo link/redirect đúng URL public |
| Có hai loại header `Forwarded` và `X-Forwarded-*` mâu thuẫn | Edge chỉ giữ loại được policy chấp nhận; không gây rewrite bất nhất |
| Hai proxy hop, một hop không thuộc trust allowlist | Algorithm dừng tại trust boundary; không nhận IP tự khai báo phía xa |
| Rollout thay đổi ingress, CIDR proxy hoặc hostname | Tests trust boundary được chạy lại, không nới `internal-proxies` vô điều kiện |
| HTTP/2 client gửi `:authority` không hợp lệ | Edge kiểm tra host/authority trước khi chuyển request tới backend |

Không đặt giả thuyết “IP luôn là phần tử đầu trong `X-Forwarded-For`” trong test. Kiểm tra giá trị từ **connection peer và proxy chain đã xác minh**.

## 14. Observability, vận hành và phản ứng khi sai cấu hình

Các log/metrics cần phân biệt:
- **Socket peer IP**: ai kết nối trực tiếp tới backend; từ network accept/access log ở lớp trước khi rewrite khi khả dụng.
- **Derived client IP**: IP sau xử lý forwarded headers và trusted proxy policy, có thể phục vụ analytics/rate limit ở tầng phù hợp.
- **External host/scheme/port**: giá trị do edge xác minh; không ghi bừa raw attacker-controlled headers vào log không escaped.
- **Forwarded-header anomalies**: client gửi header bị proxy từ chối, có cả hai loại mâu thuẫn, host không allowlist, chuỗi IP quá dài.
- **Deployment topology/version**: ingress controller release, proxy IP allowlist, Spring Boot config, Tomcat vs Netty và network policies.

Với hệ thống có CDN hoặc load balancer managed, IP ranges có thể thay đổi theo nhà cung cấp; cập nhật qua quy trình được kiểm soát, không vì một sự cố mà nhanh chóng mở trust cho cả mạng private hoặc toàn bộ Internet.

Khi nghi spoofing:
1. Xác minh có đường truy cập thẳng tới backend không, kiểm tra network ACL và public service exposure.
2. Kiểm tra edge có **xóa cả `Forwarded` lẫn toàn bộ `X-Forwarded-*` không đáng tin** hay đang append nguyên chuỗi client.
3. Kiểm tra Boot đang chạy `NONE/NATIVE/FRAMEWORK` thực tế, embedded server loại nào, trusted proxy pattern nào.
4. So sánh socket peer IP với derived client IP tại điểm kiểm soát an toàn, không tiết lộ thông tin này qua public debug endpoint.
5. Test Host/Proto/For/Port/Prefix spoof qua public ingress, test redirects và auth flows có liên quan.
6. Nếu có reset links/callback URLs bị poison, rà lại logs/email/caches và xử lý theo quy trình bảo mật của đơn vị, không chỉ đổi một property.

Trong logging, một giá trị người dùng gửi có thể chứa control characters hoặc thông tin giả; ghi structured/escaped, giới hạn độ dài, tránh để attacker giả dòng log hoặc tạo cardinality vô hạn trong metrics.

## 15. Bảng lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng khắc phục |
|---|---|---|
| App sinh link `http://internal:8080` thay vì HTTPS public | Chưa nhận/áp `X-Forwarded-Proto/Host` đáng tin | Cấu hình edge sanitize, Boot strategy và host đúng |
| Bật `FRAMEWORK` rồi bị Host poisoning | Backend public hoặc proxy pass-through header từ client | Chặn direct access, strip/overwrite ở edge, giới hạn hosts |
| `request.getRemoteAddr()` có thể là IP giả | Trusted-proxy pattern quá rộng hoặc chọn XFF token sai | Kiểm tra socket peer, RemoteIpValve/ingress trust hops |
| Redirect loop HTTP↔HTTPS | Backend không biết external scheme, proxy ép HTTPS | Đảm bảo `X-Forwarded-Proto` chính xác từ proxy và cấu hình redirect |
| `server.tomcat.remoteip.internal-proxies` không có hiệu lực | Đang dùng `FRAMEWORK`/Netty thay vì Tomcat NATIVE | Kiểm tra runtime stack, chọn cấu hình phù hợp |
| WebFlux thấy host sai dù proxy gửi header | Chưa bật framework transformer/native support hoặc header bị xóa | Kiểm tra Boot strategy và ingress routing |
| CORS preflight fail | Origin/CORS policy sai, không phải cứ forwarded headers | Cấu hình CORS allowlist và credentials đúng |
| OAuth callback bị đổi hostname | Lấy host từ header không xác minh | Cố định/allowlist redirect URI public, không dùng raw forwarded host |
| Cookie Secure không như mong đợi | App nghĩ request là HTTP sau TLS termination | Kiểm tra trusted proto, HTTPS termination và cookie policy |
| Rate limit theo IP vô tác dụng | Tin XFF trái nhất client tự gửi | Rate limit ở edge hoặc parser trusted hops |
| Request qua CDN mất IP khách | Edge/ingress ghi đè mà chưa nhận diện CDN tin cậy | Cấu hình CDN real-IP theo IP ranges thực, chain contract |
| Host không hợp lệ vẫn vào backend | NGINX default server chưa từ chối, route fallback | Thêm virtual-host allowlist và kiểm tra `Host/:authority` |

## 16. Checklist triển khai an toàn

- [ ] Có sơ đồ trust boundary rõ ràng: browser/CDN/edge/ingress/service/backend.
- [ ] Backend không mở trực tiếp cho nguồn bên ngoài trusted proxies.
- [ ] Edge loại dữ liệu forwarded do client tự khai báo: **`Forwarded` và `X-Forwarded-*`**.
- [ ] Edge **tự tạo** `For`, `Proto`, `Host`, `Port`, `Prefix` theo route/connection đã xác minh.
- [ ] Không dùng `$proxy_add_x_forwarded_for` ở public edge như một cách sanitize mặc định.
- [ ] Chọn tường minh `server.forward-headers-strategy=NONE/NATIVE/FRAMEWORK`.
- [ ] Với Tomcat `NATIVE`, kiểm soát `internal-proxies`/`trusted-proxies`, không tin toàn private network nếu không cần.
- [ ] Không có code dùng thẳng raw `X-Forwarded-For` để cấp quyền hay quyết định bảo mật.
- [ ] Public host/redirect URI nhạy cảm được cấu hình/allowlist, không dựa vào Host tự do.
- [ ] CORS, authentication và CSRF được cấu hình riêng; không dùng CORS như bằng chứng proxy tin cậy.
- [ ] Test spoof Host/For/Proto/Port/Forwarded/Prefix và direct-backend bypass.
- [ ] Theo dõi redirects, HTTPS detection, proxy IP range changes, logs và alert anomalies.

## 17. Tài liệu chính thức

1. Spring Boot 3.3 — **Running Behind a Front-end Proxy Server**, `NATIVE`/`FRAMEWORK`, Tomcat RemoteIpValve và `redirect-context-root`: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
2. Spring Boot 3.3 — **Common Application Properties**, `server.forward-headers-strategy`, `server.tomcat.remoteip.*`: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
3. Spring Framework 6.1 — **ForwardedHeaderFilter** và `removeOnly`: https://docs.spring.io/spring-framework/docs/6.1.2/javadoc-api/org/springframework/web/filter/ForwardedHeaderFilter.html
4. Spring Framework 6.1 — **ForwardedHeaderTransformer** cho WebFlux: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/server/adapter/ForwardedHeaderTransformer.html
5. RFC 7239 — **Forwarded HTTP Extension**, Security Considerations `8.1`: https://www.rfc-editor.org/rfc/rfc7239.html
6. NGINX — `proxy_set_header`, behavior của empty value và host headers: https://nginx.org/en/docs/http/ngx_http_proxy_module.html
7. Apache Tomcat — `RemoteIpValve`, proxy chain và `internalProxies/trustedProxies`: https://tomcat.apache.org/tomcat-10.1-doc/config/valve.html

**Kết luận:** forwarded headers chỉ là **lời khai của request** cho đến khi đi qua một **ranh giới proxy được kiểm soát**. Chính proxy phải loại header độc hại, tự tạo metadata từ kết nối đã xác minh, và backend chỉ được nhận traffic từ proxy đó. Spring Boot xử lý forwarded headers sau ranh giới ấy để tạo URL/redirect đúng; nó không phải cơ chế thay thế network access control, host allowlist, CORS policy hay authorization.