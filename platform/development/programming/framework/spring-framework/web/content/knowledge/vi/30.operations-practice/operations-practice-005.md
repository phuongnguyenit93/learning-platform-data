# Triển khai Spring Web sau reverse proxy: HTTPS, forwarded headers, streaming và WebSocket

## 1. Bức tranh triển khai và các lỗi thường bị nhầm

Trong triển khai thực tế, người dùng thường kết nối tới **reverse proxy** (Nginx, Envoy, gateway, ingress, load balancer), rồi proxy chuyển request tới ứng dụng Spring chạy trên mạng nội bộ. Proxy có thể terminate TLS, đổi protocol, địa chỉ IP, hostname, port, path prefix và đặc tính truyền dữ liệu.

```text
Trình duyệt / API client
https://app.example.test       wss://app.example.test/ws
          │ TLS tới proxy
          ▼
┌──────────────────────────────────────────────┐
│ Reverse proxy / Load balancer                 │
│ - HTTPS certificate, TLS policy               │
│ - route, trust boundary, forwarded headers    │
│ - HTTP buffering/timeout, WebSocket Upgrade   │
└──────────────────────────────────────────────┘
          │ HTTP/1.1 nội bộ (ví dụ)
          │ Host/Forwarded/X-Forwarded-* được kiểm soát
          ▼
Spring Boot / Spring MVC hoặc WebFlux
http://127.0.0.1:8080
          │
          ├─ REST/redirect/absolute link
          ├─ SSE/NDJSON/file streaming
          └─ WebSocket handler / STOMP endpoint
```

Ứng dụng ở sau proxy có thể nhìn request nội bộ là `http://127.0.0.1:8080`, dù client thật đã dùng HTTPS. Nếu không truyền và xử lý metadata gốc đúng cách, ứng dụng có thể trả:
- `Location: http://...` thay vì `https://...`, gây mixed content, vòng lặp redirect hoặc sai OAuth callback.
- Cookie thiếu `Secure` hoặc URL/scheme/host suy luận sai từ request.
- SSE “chờ lâu rồi mới nhận một lượt” do buffering/compression ở proxy.
- WebSocket handshake thất bại (`400`/`404`/`426`/`502`) hoặc kết nối tự đóng do thiếu Upgrade, timeout/idle.
- Log IP client sai, hoặc nguy hiểm hơn: tin header IP/host do attacker giả mạo.

Không có một tùy chọn Spring duy nhất sửa tất cả. Phải phối hợp **TLS & trust boundary → forwarded metadata → buffering/timeouts → WebSocket routing → test end-to-end**.

Phần ví dụ sử dụng **Spring Boot 3.3.x, Spring Framework 6.1.x, Java 17+ và Nginx**, với lưu ý riêng cho Servlet MVC/WebFlux. Các hostname, địa chỉ mạng và đường dẫn chứng chỉ được đưa ra để minh họa mô hình; triển khai thật dùng domain, chứng chỉ, mạng nội bộ và chính sách bảo mật của hệ thống.

## 2. HTTPS termination: hai kết nối khác nhau

**TLS termination tại proxy** nghĩa là TLS từ client được xác thực/kết thúc ở proxy, sau đó proxy có thể mở một HTTP connection không mã hóa **trên mạng nội bộ đã kiểm soát** tới Spring.

```text
Browser -- HTTPS/TLS --> Nginx -- HTTP --> Spring :8080
```

Ưu điểm: tập trung certificate, TLS version/cipher, HSTS và lifecycle chứng chỉ; Spring có thể chỉ nghe port nội bộ. Nhưng từ phía Spring, `request.getScheme()` và `isSecure()` ban đầu có thể phản ánh **hop nội bộ** (HTTP, false), không phải giao thức ở browser. Cần metadata được proxy xác thực như `X-Forwarded-Proto: https` hoặc `Forwarded: proto=https;host=...`.

**TLS end-to-end / re-encryption** dùng HTTPS cả proxy → backend:

```text
Browser -- HTTPS/TLS --> Proxy -- HTTPS/TLS --> Spring
```

Ở đây proxy phải verify certificate/hostname của upstream khi cấu hình như vậy; việc bật HTTPS upstream mà không verify đúng danh tính server không đủ chống giả mạo backend. Cân nhắc mTLS khi mạng/kiến trúc yêu cầu. Forwarded headers vẫn có ích vì hostname/port/public prefix bên ngoài có thể khác hostname nội bộ dù cả hai hop là HTTPS.

**Đừng chỉ bật `server.ssl.*` trong Spring và nghĩ proxy đã xong:** nếu proxy terminate TLS nhưng upstream đã chuyển sang HTTPS, `proxy_pass` phải khớp protocol/port backend. Mismatch thường gây `502 Bad Gateway` hoặc lỗi TLS handshake. Không bật HTTPS ở backend chỉ vì client dùng HTTPS nếu topology đã quyết định TLS termination ở trust boundary.

Trách nhiệm cơ bản tại proxy:
1. Redirect HTTP port 80 sang HTTPS port 443 nếu hệ thống yêu cầu.
2. Dùng chứng chỉ hợp lệ cho public hostname; cấu hình TLS hiện đại và tự động gia hạn.
3. Chặn truy cập trực tiếp port ứng dụng từ Internet; backend chỉ nhận traffic từ proxy/ingress đáng tin.
4. Hạn chế request size, kết nối và các policy an ninh thích hợp; giữ thời hạn proxy hợp với workload.
5. Gửi đầy đủ thông tin public scheme/host/port theo chính sách rõ ràng, tuyệt đối không chuyển tiếp giá trị giả mạo từ bên ngoài.

HSTS (`Strict-Transport-Security`) chỉ nên bật sau khi xác minh HTTPS hoạt động ổn định trên domain/subdomain cần áp dụng, đặc biệt nếu dùng `includeSubDomains`. Các cookie chứa session thường cần `Secure`, `HttpOnly`, `SameSite` theo chính sách auth/cross-site; forwarded scheme là một phần thông tin để ứng dụng thiết lập chúng, nhưng không thay việc cấu hình cookie.

## 3. Forwarded headers: phục hồi URL thật và xác định ranh giới tin cậy

Hai họ header phổ biến:

**RFC 7239 `Forwarded`:**

```http
Forwarded: for=203.0.113.10;proto=https;host=app.example.test
```

**`X-Forwarded-*` (de facto):**

```http
X-Forwarded-For: 203.0.113.10
X-Forwarded-Proto: https
X-Forwarded-Host: app.example.test
X-Forwarded-Port: 443
```

Một số proxy còn dùng `X-Forwarded-Prefix: /portal` nếu public path có prefix khác ứng dụng. Các ví dụ địa chỉ `203.0.113.0/24` và domain `example.test` thuộc không gian dành cho tài liệu, không phải endpoint có thể truy cập thực tế.

Ý nghĩa từng trường:
- `For` / `X-Forwarded-For`: IP ở đầu chuỗi qua các proxy (có thể nhiều hop).
- `Proto` / `X-Forwarded-Proto`: giao thức nhìn từ bên ngoài, ví dụ `https`.
- `Host` / `X-Forwarded-Host`: public hostname, đôi khi kèm port.
- `X-Forwarded-Port`: port public nếu proxy dùng.
- `X-Forwarded-Prefix`: base path phía public khi proxy strip/prefix rewrite.

Sau khi được framework tin cậy và xử lý, các thao tác dựa trên request như tạo absolute links, redirects, `getScheme()`, `getServerName()`, `isSecure()` có thể phản ánh URL phía client. Cần phân biệt:
- Header `Host` của HTTP request upstream do proxy đặt.
- Forwarded headers do proxy quản lý.
- Giá trị `request.getRemoteAddr()` ở socket có thể vẫn là địa chỉ proxy, không phải IP gốc; việc nhận dạng IP qua chuỗi proxy phụ thuộc container/adapter và trust model.

### Quy tắc bảo mật quan trọng nhất

**Không tin `Forwarded`/`X-Forwarded-*` do client Internet tự đặt.** Nếu một attacker tự gửi:

```http
X-Forwarded-Host: attacker.example
X-Forwarded-Proto: http
```

mà ứng dụng trực tiếp tin, absolute redirect/password reset URL có thể trỏ sai host hoặc cookie/URL security bị ảnh hưởng. Ở **proxy biên tin cậy**, cần:
1. Xóa/ghi đè cả `Forwarded` **và** toàn bộ `X-Forwarded-*` nhận từ bên ngoài, kể cả các trường không dùng.
2. Ghi lại giá trị mới do proxy kiểm soát từ kết nối đáng tin (hostname được validate, client IP thực tế, TLS state).
3. Không cho bên ngoài bypass proxy để gửi thẳng vào backend.
4. Với nhiều lớp proxy, định nghĩa chính xác trusted hops/networks; không suy IP thật bằng cách lấy phần tử đầu tiên của `X-Forwarded-For` do bất kỳ nguồn nào gửi.

**`X-Forwarded-For` từ Nginx:** `$proxy_add_x_forwarded_for` *nối thêm* địa chỉ client vào header `X-Forwarded-For` có sẵn. Nếu Nginx là **edge proxy trực tiếp Internet** và chưa dọn header đầu vào, phép nối này có thể giữ giá trị giả mạo. Ở ví dụ Nginx phía dưới, dùng `X-Forwarded-For $remote_addr` để **ghi đè** chuỗi từ browser. Nếu Nginx ở sau CDN/LB đáng tin, cấu hình trust chain bằng `real_ip_header`/`set_real_ip_from` hoặc cơ chế của hạ tầng trước khi xây lại IP, không suy đoán rằng `$remote_addr` luôn là IP browser.

## 4. Spring Boot: NATIVE, FRAMEWORK và NONE

Spring Boot 3.3 hỗ trợ:

```yaml
server:
  forward-headers-strategy: framework
```

Các giá trị:

| Chiến lược | Cơ chế | Lưu ý |
| --- | --- | --- |
| `none` | Không xử lý forwarded metadata theo Boot strategy | Dùng khi không có reverse proxy tin cậy hoặc không muốn tin metadata |
| `native` | Dùng chức năng của web server/container nền (Tomcat, Jetty, Reactor Netty tùy stack) | Behavior/hỗ trợ các header phụ thuộc container |
| `framework` | Dùng cơ chế xử lý của Spring Framework | Servlet MVC dùng `ForwardedHeaderFilter`, reactive WebFlux dùng `ForwardedHeaderTransformer` |

Một số cloud platform được Boot nhận biết có thể mặc định `native`; môi trường khác thường là `none`. **Khai báo tường minh** để deployment dễ review. `framework` thường hữu ích khi muốn xử lý public prefix và URL/redirect thống nhất theo Spring; `native` phù hợp nếu hạ tầng đã dùng container-specific remote-IP/trust logic. Tránh để **cả container và filter của framework đều tự diễn giải cùng một tập header** khi chưa kiểm chứng.

**Servlet MVC:** `ForwardedHeaderFilter` đọc/áp dụng metadata cho request và một số thao tác response như `sendRedirect`. Có `setRemoveOnly(true)` khi chỉ muốn loại header giả mạo mà **không sử dụng** metadata.

**WebFlux:** `ForwardedHeaderTransformer` xử lý metadata trước lúc Spring tạo exchange cho handler; có `setRemoveOnly(true)` tương tự. Spring Boot có thể auto-configure theo `server.forward-headers-strategy=framework`; nếu tự đăng ký bean/filter tương ứng, tránh duplicate handling. Những lớp này **không xác thực proxy**: bảo đảm trust boundary ở lớp ingress/network vẫn là điều kiện bắt buộc.

### Kiểm tra path prefix và URL tuyệt đối

Giả sử public path là `https://app.example.test/portal/api/orders` nhưng Nginx strip `/portal` trước khi chuyển thành `/api/orders`. Nếu chỉ set `X-Forwarded-Proto` mà quên public prefix, các link sinh ra từ request có thể thiếu `/portal`. Hãy chọn **một** mô hình nhất quán:
- Proxy giữ nguyên `/portal` để backend biết application context path, hoặc
- Proxy strip prefix và cung cấp `X-Forwarded-Prefix: /portal` theo cấu hình trusted; backend framework hỗ trợ đúng version và application context.

Kiểm tra từng cấu hình bằng endpoint tự sinh URL và test redirect/`Location` thật. Không hard-code public URL trong mọi controller chỉ để chữa một forwarded-header policy sai. Với application phục vụ ở root path như ví dụ dưới, **không cần** `X-Forwarded-Prefix`.

### Tomcat redirect context root

Với Spring MVC trên Tomcat, khi terminate SSL tại proxy và có context path, tài liệu Spring Boot lưu ý `server.tomcat.redirect-context-root=false` để `X-Forwarded-Proto` được xét trước khi container tự chuyển hướng thêm dấu `/`. Chỉ áp dụng khi thực sự dùng Tomcat/context-root redirect, không bắt buộc cho mọi ứng dụng.

## 5. Nginx: HTTPS, sanitize header, streaming và WebSocket Upgrade

Ví dụ Nginx cấu hình cho **một edge reverse proxy** nhận TLS công khai, upstream Spring nghe HTTP ở `127.0.0.1:8080` trên cùng host. Đây là cấu hình tham khảo, cần thay domain `app.example.test` và certificate paths bằng hạ tầng thật. Giá trị `proxy_read_timeout` là **khoảng không nhận byte liên tiếp** từ upstream, không phải deadline tổng response.

```nginx
# Đặt bên trong http { ... }.
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

server {
    listen 80;
    server_name app.example.test;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name app.example.test;

    ssl_certificate     /etc/nginx/certs/fullchain.pem;
    ssl_certificate_key /etc/nginx/certs/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;

        # Chỉ tin thông tin do edge proxy tạo.
        proxy_set_header Host $host;
        proxy_set_header Forwarded "";
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Port $server_port;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Ssl "";
        proxy_set_header X-Forwarded-Prefix "";

        # WebSocket: hop-by-hop headers cần chuyển rõ ràng.
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;

        proxy_connect_timeout 5s;
        proxy_send_timeout 75s;
        proxy_read_timeout 75s;

        # Mặc định có thể buffer response thông thường.
        # Endpoint SSE trong ví dụ trả X-Accel-Buffering: no.
    }
}
```

**Đừng copy nguyên khối mà chưa xem trust/network/TLS:** certificate thực phải tồn tại/khớp host, firewall không cho client bypass backend, Nginx chỉ nhận các host được phép, và cần chính sách thêm nếu deploy sau CDN/ingress khác. Nếu `proxy_set_header Host $host` không đủ cho application dùng public port tùy biến, xác định chính sách port/host phù hợp. Cấu hình Nginx thay đổi theo phiên bản; HTTP/2 phía client không nhất thiết đồng nghĩa WebSocket upstream sẽ dùng HTTP/2. Snippet sử dụng đường **HTTP/1.1 Upgrade** cho backend.

### WebSocket cần Upgrade/Connection

`Upgrade` và `Connection` là hop-by-hop headers: proxy HTTP thường không chuyển chúng lên backend nếu không đặt lại. Để tạo tunnel WebSocket qua reverse proxy, client gửi handshake HTTP/1.1 với `Upgrade: websocket`; upstream trả `101 Switching Protocols`; proxy duy trì kết nối hai chiều lâu dài.

Các dòng quan trọng:

```nginx
proxy_http_version 1.1;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection $connection_upgrade;
proxy_read_timeout 75s;
```

Trong `map`: request có `Upgrade` sẽ đặt `Connection: upgrade`, request không có sẽ đặt `Connection: close` theo ví dụ chính thức Nginx (không phải tối ưu cho upstream keep-alive mọi loại request, nhưng rõ ràng và dễ học). Với cấu hình HTTP/1.1 khác, có thể tối ưu keep-alive và routing cho request thường, miễn đảm bảo handshake WebSocket vẫn đúng.

**Giữ kết nối:** Nginx mặc định đóng tunnel nếu upstream không gửi gì trong khoảng `proxy_read_timeout` (mặc định tài liệu Nginx thường 60 giây). Tăng read idle timeout hoặc để backend gửi ping/pong/WebSocket heartbeat thường xuyên đủ để tránh proxy đánh giá idle. `proxy_read_timeout=75s` không có nghĩa mọi WebSocket connection chỉ tồn tại 75 giây; có traffic kịp thời thì kết nối có thể kéo dài.

**STOMP trên WebSocket:** ngoài tunnel, broker/app phải có heartbeat/session cleanup và subscription management phù hợp. Thay route raw `/ws` bằng STOMP handshake endpoint không làm quy tắc proxy đổi căn bản; SockJS fallback còn có HTTP polling/streaming paths, nên cần route tất cả đường dẫn tương ứng nếu dùng SockJS.

### SSE/streaming bị buffer

Nginx proxy buffering (thường mặc định bật) có thể nhận dữ liệu upstream trước rồi phát cho browser theo chính sách buffer, khiến `EventSource`/`curl -N` không thấy từng event ngay. Với endpoint cụ thể, có thể:

- Tắt proxy buffering trong `location /events`: `proxy_buffering off;`, hoặc
- Để ứng dụng trả header `X-Accel-Buffering: no` cho response SSE để Nginx không buffer response này (miễn không bật `proxy_ignore_headers` bỏ qua header). Đây là lựa chọn của ví dụ bên dưới.
- Kiểm tra gzip/Brotli hoặc compression ở các tầng proxy/CDN, vì chúng cũng có thể giữ data trước khi flush.
- Đảm bảo controller **flush** sự kiện ra response thực, có content type `text/event-stream`, và gửi comment heartbeat nếu stream dài.

Đừng tắt buffering toàn bộ API mặc định nếu chỉ vài endpoint streaming cần latency thấp; điều đó có thể làm thay đổi throughput và memory behavior của proxy. Với nhiều proxy/CDN layers, phải tắt buffering tại **mọi layer ảnh hưởng**; thay đổi một Nginx chưa bảo đảm CDN phía trước truyền từng chunk.

## 6. Ví dụ Spring Boot chạy được: scheme, redirect, SSE và WebSocket

Ta xây ứng dụng Spring MVC nhỏ, gửi traffic **trực tiếp localhost HTTP** khi develop, sau đó chạy sau Nginx HTTPS theo mô hình phần 5. Các endpoint:

| Endpoint | Mục đích |
| --- | --- |
| `GET /diag` | Cho thấy scheme, host, secure, URL mà Spring nhận sau forwarded processing |
| `GET /go` | Redirect đến absolute URL `/status` để kiểm tra `Location` |
| `GET /status` | Kết quả đơn giản cho redirect |
| `GET /events` | Phát 3 SSE events, flush qua `SseEmitter` và đặt `X-Accel-Buffering: no` |
| `GET /ws` Upgrade | Raw WebSocket echo để kiểm tra `101 Switching Protocols` và đường hai chiều |

Cấu trúc:

```text
reverse-proxy-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/ProxyDemoApplication.java
    └── resources/application.yml
```

**`settings.gradle`**

```groovy
rootProject.name = 'reverse-proxy-demo'
```

**`build.gradle`** — Java 17+, Gradle 8.x:

```groovy
plugins {
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
    id 'java'
}

group = 'demo'
version = '1.0.0'

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
    implementation 'org.springframework.boot:spring-boot-starter-websocket'
}
```

**`src/main/resources/application.yml`**

```yaml
server:
  port: 8080
  forward-headers-strategy: framework
```

Chỉ bật đọc forwarded headers khi thực sự có **trusted proxy boundary**. Nếu server development mở công khai, bất kỳ client nào gọi trực tiếp `localhost:8080` qua port forwarded/NAT đều có thể tự đặt header; đây là lý do phải ràng buộc backend vào mạng nội bộ hoặc firewall chặn truy cập không qua proxy.

**`src/main/java/demo/ProxyDemoApplication.java`**

```java
package demo;

import java.io.IOException;
import java.net.URI;
import java.util.LinkedHashMap;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;
import org.springframework.web.socket.handler.TextWebSocketHandler;

@SpringBootApplication
public class ProxyDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ProxyDemoApplication.class, args);
    }

    @Bean("sseTaskExecutor")
    ThreadPoolTaskExecutor sseTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(32);
        executor.setThreadNamePrefix("demo-sse-");
        return executor;
    }
}

@RestController
class DemoController {
    private final TaskExecutor taskExecutor;

    DemoController(@Qualifier("sseTaskExecutor") TaskExecutor taskExecutor) {
        this.taskExecutor = taskExecutor;
    }

    @GetMapping("/diag")
    Map<String, Object> diag(HttpServletRequest request) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("scheme", request.getScheme());
        result.put("secure", request.isSecure());
        result.put("host", request.getServerName());
        result.put("port", request.getServerPort());
        result.put("url", request.getRequestURL().toString());
        return result;
    }

    @GetMapping("/status")
    Map<String, String> status() {
        return Map.of("status", "ok");
    }

    @GetMapping("/go")
    ResponseEntity<Void> redirect() {
        URI target = ServletUriComponentsBuilder
            .fromCurrentContextPath()
            .path("/status")
            .build()
            .toUri();
        return ResponseEntity.status(HttpStatus.FOUND)
            .location(target)
            .build();
    }

    @GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    SseEmitter events(HttpServletResponse response) {
        response.setHeader("X-Accel-Buffering", "no");
        SseEmitter emitter = new SseEmitter(30_000L);

        taskExecutor.execute(() -> {
            try {
                for (int i = 0; i < 3; i++) {
                    emitter.send(SseEmitter.event()
                        .id(Integer.toString(i))
                        .name("tick")
                        .data("event-" + i));
                    Thread.sleep(1_000);
                }
                emitter.complete();
            } catch (IOException disconnected) {
                // Client đã rời đi; container/Spring xử lý I/O error.
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                emitter.complete();
            }
        });
        return emitter;
    }
}

@Configuration
@EnableWebSocket
class WebSocketConfig implements WebSocketConfigurer {

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(new EchoHandler(), "/ws");
        // Mặc định kiểm tra Origin cho same-origin request.
    }

    static final class EchoHandler extends TextWebSocketHandler {
        @Override
        protected void handleTextMessage(WebSocketSession session,
                                         TextMessage message) throws IOException {
            session.sendMessage(new TextMessage("echo: " + message.getPayload()));
        }
    }
}
```

**Giải thích các điểm cần kiểm chứng:**
- `/diag` đọc request đã qua `ForwardedHeaderFilter` (nếu có header đúng và Boot strategy là `framework`), giúp quan sát public scheme/host, nhưng endpoint này chỉ nên bật ở môi trường kiểm tra/được bảo vệ vì có thể lộ topology.
- `/go` tạo absolute `Location` dựa trên request đã được phục hồi, thay vì ghép hard-coded `http://localhost:8080`.
- `/events` trả `SseEmitter` với `Content-Type: text/event-stream`, flush các event qua Spring MVC, đặt `X-Accel-Buffering: no` để Nginx không buffer response cụ thể. Vòng lặp 3 event hữu hạn giúp kiểm tra dễ; production SSE lâu dài cần cleanup/heartbeat, quản lý listener và threading tốt hơn. Pool executor nhỏ ở đây chỉ phục vụ demo; nếu nhiều stream đồng thời, cần thiết kế non-blocking/scheduled fan-out thích hợp, không giữ một thread chờ cho mỗi client vô hạn.
- `/ws` dùng Spring WebSocket raw echo. Ở môi trường production, cần xác thực, authorization, kiểm soát Origin/CSRF theo giao thức và policy gửi đồng thời; mẫu chỉ minh họa transport Upgrade.
- `@EnableWebSocket` cần `spring-boot-starter-websocket`, còn `SseEmitter` của Spring MVC chạy trên servlet async. Đừng trộn nguyên phần servlet code này vào ứng dụng chỉ dùng WebFlux/Netty rồi kỳ vọng compile.

Chạy local:

```bash
gradle bootRun
```

Kiểm tra trực tiếp (trên máy chạy server):

```bash
curl -i http://localhost:8080/status
curl -i http://localhost:8080/go
curl -N -i http://localhost:8080/events
curl -s http://localhost:8080/diag
```

**Kết quả mong đợi ở local, không gắn forwarded header**:
- `/status`: HTTP 200, JSON có `"status":"ok"`.
- `/go`: HTTP 302, `Location: http://localhost:8080/status` (host có thể tương ứng URL thực tế).
- `/events`: status 200 và các event `id:0`, `event:tick`, `data:event-0`, sau đó các event 1, 2 theo khoảng 1 giây và stream kết thúc.
- `/diag`: trường `scheme` là `http`, `secure` false, host `localhost` hoặc host request thực tế.

Các command kiểm tra trên là hành vi dự kiến; transcript raw HTTP phụ thuộc headers mặc định và phiên bản.

Sau khi có Nginx HTTPS hợp lệ tại domain thực, gọi:

```bash
curl -i https://app.example.test/go
curl -N -i https://app.example.test/events
curl -s https://app.example.test/diag
```

Kỳ vọng `/diag` cho `scheme=https`, `secure=true` và public host. `Location` của `/go` phải bắt đầu bằng `https://app.example.test/`. Với `curl -N`, ba event được nhận lần lượt, không dồn ở cuối khi proxy buffering đã được điều chỉnh đúng. Địa chỉ `app.example.test` là domain minh họa, phải thay bằng tên DNS thực tế có chứng chỉ.

### Kiểm tra WebSocket

Trên trình duyệt đang mở trang cùng public origin:

```javascript
const socket = new WebSocket("wss://app.example.test/ws");
socket.onopen = () => socket.send("hello");
socket.onmessage = (event) => console.log(event.data);
socket.onerror = (error) => console.error(error);
socket.onclose = (event) => console.log("closed:", event.code);
```

Với domain thực được cấu hình, console sẽ nhận `echo: hello`. DevTools Network → WS sẽ hiện handshake `101 Switching Protocols` và WebSocket frames. Trong thử nghiệm local có thể dùng `ws://localhost:8080/ws` từ một trang cùng origin local; với trang HTTPS, phải dùng `wss://` vì browser chặn mixed active content `ws://`.

**Lưu ý về Origin:** browser WebSocket có thể gửi `Origin`; Spring mặc định có same-origin checking. Khi kiểm thử bằng console từ origin khác, handshake có thể bị từ chối dù Nginx Upgrade hoàn toàn đúng. Không chữa bằng `setAllowedOrigins("*")` trong ứng dụng có xác thực/session; kiểm tra đúng public origin, cookie auth và Origin policy.

## 7. Streaming trong Servlet MVC và WebFlux: flush, heartbeat, backpressure

Cả MVC và WebFlux có thể phát SSE/stream, nhưng mô hình I/O khác:

| Spring MVC Servlet | Spring WebFlux |
| --- | --- |
| `SseEmitter` / `ResponseBodyEmitter` / `StreamingResponseBody` | `Flux<ServerSentEvent<T>>` / `Flux<T>` / `DataBuffer` |
| Servlet async; việc ghi response có thể blocking | Mô hình non-blocking trên server reactive phù hợp |
| Cần `AsyncTaskExecutor` production phù hợp | Tránh blocking event loop; dùng scheduler chỉ khi cần |
| Cleanup `onCompletion`/`onTimeout`/`onError` ở `SseEmitter` | Cleanup qua `doFinally(SignalType.CANCEL)` / resource scope |
| Heartbeat giúp phát hiện client disconnect khi còn kết nối HTTP dài hạn | Tương tự; cancel/transport error phản ánh đóng luồng tùy network |

Ví dụ WebFlux (chỉ **minh họa**, không chèn vào ứng dụng MVC ở phần 6):

```java
@GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<String>> events() {
    return Flux.interval(Duration.ofSeconds(10))
        .map(i -> ServerSentEvent.<String>builder()
            .id(Long.toString(i))
            .event("heartbeat")
            .data("tick-" + i)
            .build())
        .doFinally(signal -> log.info("SSE ended: {}", signal));
}
```

Cần imports `GetMapping`, `MediaType`, `ServerSentEvent`, `Flux`, `Duration` và logger do app khai báo; đoạn không độc lập. **Không gọi `block()` trên reactive event-loop**. Khi browser/người dùng cancel hoặc proxy đóng stream, publisher có thể nhận cancellation. Nhưng hủy subscription không phải lời hứa mọi network/socket close xảy ra ngay đúng thời điểm nếu có proxy layers.

**Heartbeat/flush:** một stream liên tục nhưng lâu không phát byte có thể bị Nginx, LB hoặc CDN đóng do `read idle timeout`. Gửi SSE comment ping định kỳ (ví dụ `: ping` rồi dòng trắng), hoặc event heartbeat có tên tùy contract; nhịp phải ngắn hơn idle timeout **với biên độ dự phòng cho jitter**. Đừng gửi heartbeat quá nhanh cho hàng trăm nghìn client mà chưa đánh giá CPU và bandwidth.

**Compression:** gzip/Brotli có thể làm buffering tăng do encoder đợi đủ dữ liệu. Với `text/event-stream`, cần kiểm tra setting server/proxy/CDN; nếu cần độ trễ thấp, loại trừ SSE khỏi compression ở các tầng gây delay.

**Chunked và HTTP/2:** streaming không có nghĩa phải hiện header `Transfer-Encoding: chunked` ở mọi client. HTTP/2 không dùng chunked transfer coding như HTTP/1.1; kiểm tra **thời điểm nhận các sự kiện và data framing**, không dựa vào một header truyền tải duy nhất.

**Tài nguyên và backpressure:** Spring có thể flush từng event, nhưng network chậm và nhiều client vẫn tạo memory/backpressure/threads. Giới hạn active streams, tốc độ publish, queue per subscriber, payload size và cleanup resource. Không dùng `collectList` với Flux không kết thúc. Với file download lớn, dùng streaming data, đo direct memory/heap và kiểm soát download concurrency.

## 8. WebSocket/STOMP sau proxy: lifecycle và scale

Một WebSocket bắt đầu bằng HTTP handshake rồi chuyển sang kết nối lâu dài. Những yêu cầu ngoài proxy cơ bản:

- **Forwarded public origin:** browser dùng `wss://` tương ứng HTTPS; ứng dụng kiểm tra Origin/auth/cookie và các redirect URL nếu có.
- **Upgrade:** Nginx phải forward `Upgrade`/`Connection` và dùng HTTP/1.1 cho hop đến backend khi áp dụng protocol Upgrade.
- **Idle timeout:** `proxy_read_timeout` và timeout tại ingress/LB phải đủ hoặc có ping/pong; không nhầm read timeout với tổng tuổi thọ session.
- **Scale nhiều instance:** raw WebSocket sessions gắn với node đang giữ TCP connection. Load balancer phải giữ connection sống; khi reconnect có thể sang node khác. Nếu dùng Spring STOMP simple broker in-memory, subscription không tự chia sẻ qua các node; cân nhắc external broker relay.
- **Authentication/session:** HTTPS termination không thay xác thực WebSocket. Browser WebSocket API không cho tùy ý đặt mọi custom header; cần thiết kế cookie hoặc token/subprotocol/handshake theo chính sách an toàn. Tránh đưa bearer token không kiểm soát vào URL/query/log.
- **SockJS fallback:** có thêm đường dẫn/info, XHR streaming/polling; proxy routing, CORS, buffering và sticky session requirement có thể khác native WebSocket.
- **Đóng kết nối:** gửi code close không phải lúc nào được nhận; khi mất mạng cần heartbeat và cleanup idempotent. Với STOMP, `SessionDisconnectEvent` có thể xuất hiện hơn một lần.

`101 Switching Protocols` chỉ chứng minh handshake/tunnel được thiết lập, **không** chứng minh publisher/subscription/auth nghiệp vụ hoạt động. Cần gửi một message thử, nhận phản hồi, quan sát reconnect/timeout và test node draining khi deploy rolling update.

## 9. Checklist xác minh theo từng tầng

| Kiểm tra | Cách thực hiện | Tiêu chí đạt |
| --- | --- | --- |
| TLS/certificate | `curl -I https://domain`, browser certificate inspector | Certificate hợp lệ, đúng hostname, không phải HTTP downgrade |
| Redirect HTTP → HTTPS | `curl -I http://domain/path` | `Location` public HTTPS đúng path/query, không loop |
| Scheme/host mà Spring thấy | Endpoint `/diag` được bảo vệ | `https`/public host/port đúng sau forwarded processing |
| Host spoofing | Kiểm tra proxy sanitize `Forwarded` và mọi `X-Forwarded-*` | Client ngoài không ép ứng dụng tạo URL đến host giả |
| SSE latency | `curl -N -i https://domain/events` và đo timestamps | Event đến dần, không bị dồn cuối |
| SSE timeout | Để idle vượt/ngắn hơn timeout có heartbeat phù hợp | Connection không chết ngoài dự kiến |
| WebSocket Upgrade | Browser DevTools Network → WS | Handshake `101`, có frame hai chiều |
| WebSocket idle/reconnect | Ngắt mạng, đóng tab, thử lại | Server cleanup, client reconnect đúng chính sách |
| Multi-node | Test 2+ replicas khi load balance | Routing/subscription, rolling restart đúng kỳ vọng |
| Resource use | Metrics, tracing, heap, active connections, queue | Không leak stream/socket, có limit và cleanup |

**Chẩn đoán thường gặp:**

1. `502/504` từ Nginx: upstream sai host/port/protocol, backend không sẵn sàng, TLS backend sai hoặc request vượt thời hạn; kiểm tra Nginx error log và health của Spring.
2. OAuth redirect / `Location` quay về HTTP: forwarded proto không được gửi hoặc Spring không áp dụng, hoặc public prefix/host bị xử lý sai.
3. “Too many redirects”: redirect HTTPS ở nhiều tầng không nhất quán, backend nghĩ request luôn HTTP; xét cả CDN/LB/Nginx/Spring và cấu hình trust.
4. Lộ internal host trong response: app sinh absolute URL từ host nội bộ; kiểm tra forwarded host/port/prefix và reverse-proxy behavior.
5. SSE trả đủ dữ liệu nhưng từng batch: proxy buffering, compression, app chưa flush hoặc CDN giữ chunk.
6. SSE bị đóng đúng 60 giây idle: kiểm tra `proxy_read_timeout` và heartbeat interval; timeout là khoảng không nhận byte, không phải max response length.
7. WebSocket `400`/`426`: header Upgrade hoặc Connection không được forward, sai HTTP version/hop, Origin/protocol mismatch.
8. WebSocket `403`: Origin/CORS/auth/security policy bị từ chối; không tắt policy mù quáng.
9. WebSocket `404`: sai path/ingress strip-prefix hoặc backend không đăng ký handshake endpoint.
10. WebSocket `101` rồi đóng nhanh: proxy idle timeout, heartbeat thiếu, app exception, session/resource limits hoặc node restart.
11. Client IP trong log là proxy: chưa cấu hình trusted chain hoặc web-server access log remote-IP behavior; không lấy IP từ header raw thiếu xác thực.
12. Nhiều streams gây CPU/RAM lớn: một blocking writer/thread mỗi client, queue vô hạn, payload lớn, không cleanup, kết nối đóng nhưng listener còn sống.

Khi debug, ghép **request ID/trace ID** giữa proxy access log, Spring log và client DevTools; ghi status, latency, upstream status, bytes sent, handshake errors, timeouts và connection closes. Tránh log cookies/Authorization/URL có secret, đặc biệt WebSocket handshake query.

## 10. Nguyên tắc triển khai production

- **Chỉ một nguồn gốc public URL đáng tin:** domain/hostname được validate tại ingress; proxy tạo forwarded metadata; Spring xử lý theo strategy nhất quán.
- **Phân quyền mạng:** backend/private service chỉ nhận connection từ proxy trusted; firewall/security groups/network policy là phần quan trọng nhất để ngăn forged forwarded headers.
- **TLS có lifecycle:** tự động gia hạn cert, kiểm tra chain/hostname, key permissions, policy redirect và HTTPS upstream nếu threat model cần.
- **Timeout phân lớp:** connect, send, read-idle, app async, broker/WebSocket heartbeat và request/business deadline là các đồng hồ khác nhau. Không dùng một con số cho tất cả.
- **Streaming có giới hạn:** buffering/compression chỉ tắt tại endpoint cần thấp latency; duy trì heartbeat và cleanup, đo slow consumer.
- **WebSocket vận hành có trạng thái:** quản lý auth, Origin, subscriptions, idle, node draining, reconnect, graceful deployment và session limits.
- **Giám sát sát với hành vi người dùng:** test trực tiếp qua public hostname và proxy thật; unit test/controller test không chứng minh TLS/headers/streaming network/Upgrade đúng.
- **Đừng bật proxy trust vô điều kiện:** ở staging/dev hay khi backend được gọi trực tiếp, forwarded headers có thể do attacker tự gửi nếu không có trust boundary. Có thể dùng `none` hoặc `removeOnly` trong môi trường không được bảo vệ.

## 11. Câu hỏi tự kiểm tra

1. Browser gọi HTTPS nhưng Spring trả `Location: http://localhost:8080/login`. Kiểm tra đầu tiên? → Proxy có gửi trusted `X-Forwarded-Proto/Host` và Spring có bật đúng `server.forward-headers-strategy` chưa; backend có bị truy cập trực tiếp không.
2. Tại sao `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for` có thể nguy hiểm ở edge Internet? → Nó có thể nối tiếp giá trị client đã giả mạo thay vì thay bằng IP đáng tin.
3. `framework` và `native` khác nhau ở đâu? → Một bên dùng cơ chế Spring `ForwardedHeaderFilter`/`Transformer`, một bên dùng container/network engine; không nên xử lý trùng khi chưa kiểm tra.
4. SSE hiển thị ba event cùng lúc sau ba giây dù server gửi từng giây. Cần tìm ở đâu? → Buffering/compression ở Nginx/CDN hoặc app chưa flush, không chỉ chỉnh `SseEmitter`.
5. `proxy_read_timeout 75s` có cấm WebSocket hoạt động hơn 75s không? → Không. Đây là read idle interval, có traffic/heartbeat thì kết nối dài hạn.
6. WebSocket handshake trả `101` nhưng không nhận STOMP MESSAGE. Đã chắc proxy đúng toàn bộ chưa? → Chưa; cần kiểm tra STOMP CONNECT/SUBSCRIBE, auth, broker routing và event semantics.
7. Với deployment nhiều replica, client reconnect tự khôi phục subscriptions của simple broker? → Không; session và subscription in-memory cần tái lập hoặc kiến trúc broker phù hợp.
8. Vì sao không thể tin thẳng `X-Forwarded-Host` từ browser? → Attacker có thể làm lệch absolute URLs/redirect/cookie logic; proxy trusted phải sanitize.
9. Khi test `curl -N` nhận event nhanh nhưng browser không nhận, cần xem thêm gì? → Browser cache/compression/CDN/EventSource parsing/response media type/CORS, cùng mọi layer mạng.
10. Khi proxy terminate TLS, kết nối proxy → backend là HTTP có phải luôn không an toàn? → Phụ thuộc mạng tin cậy và threat model; nếu cần bảo mật hop nội bộ, dùng HTTPS verify upstream hoặc mTLS.

## 12. Tài liệu chính thức

- Spring Boot 3.3 — Running Behind a Front-end Proxy Server: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html#howto.webserver.use-behind-a-proxy-server
- Spring Framework 6.x — Forwarded Headers (Servlet): https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html#filters-forwarded-headers
- Spring Framework 6.x — Forwarded Headers (WebFlux): https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html#webflux-forwarded-headers
- Spring Framework 6.x — Asynchronous Requests, SSE, disconnects: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Spring Framework 6.x — WebSocket Handshake: https://docs.spring.io/spring-framework/reference/web/websocket/server.html
- Nginx — WebSocket proxying: https://nginx.org/en/docs/http/websocket.html
- Nginx — proxy buffering, `X-Accel-Buffering` và `proxy_read_timeout`: https://nginx.org/en/docs/http/ngx_http_proxy_module.html
- RFC 7239 — Forwarded HTTP Extension: https://www.rfc-editor.org/rfc/rfc7239
