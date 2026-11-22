# HTTPS, reverse proxy, chuyển hướng và địa chỉ công khai

## 1. Vấn đề cốt lõi: URL người dùng thấy khác URL backend nhìn thấy

Trong ứng dụng Spring MVC, một request đi thẳng vào Tomcat nhúng có thể mang thông tin `http://localhost:8080`. Nhưng khi chạy thật, người dùng truy cập `https://app.example.test`, TLS được xử lý tại reverse proxy, và proxy chuyển tiếp request tới backend qua HTTP nội bộ.

```text
Trình duyệt
   |
   | GET https://app.example.test/api/orders/42
   | HTTPS (TLS tới cổng công khai 443)
   v
Reverse proxy / load balancer
   |
   | GET http://127.0.0.1:8080/api/orders/42
   | HTTP nội bộ; thêm thông tin host/scheme gốc qua forwarded headers
   v
Spring MVC / DispatcherServlet / Controller
   |
   | phản hồi JSON, Location, Set-Cookie...
   v
Proxy -> HTTPS -> Trình duyệt
```

Nếu Spring không biết scheme, host, port hoặc tiền tố đường dẫn công khai, ứng dụng có thể:

- Sinh link trong email, JSON, trang HTML hoặc tài liệu API thành `http://127.0.0.1:8080/...` hay `http://app.example.test/...` thay vì `https://app.example.test/...`.
- Chuyển hướng `Location` tới host/port nội bộ, sai HTTP/HTTPS hoặc thiếu tiền tố `/portal`.
- Vòng lặp redirect giữa proxy ép HTTPS và ứng dụng hiểu request là HTTP.
- Thiết lập sai một số tính chất phụ thuộc HTTPS (chẳng hạn đánh giá request có an toàn hay không), hoặc xử lý sai callback URL.

Bài này tập trung vào mối quan hệ giữa **HTTP/TLS, reverse proxy, forwarded headers, redirect và external/public URL** trong Spring Web MVC. Mô hình WebFlux có các cơ chế riêng, như `ForwardedHeaderTransformer`.

## 2. Từng khái niệm và ranh giới trách nhiệm

### HTTPS và TLS termination

HTTPS là HTTP truyền qua TLS. TLS bảo vệ tính bí mật, toàn vẹn và xác thực danh tính máy chủ trên đoạn kết nối được thiết lập TLS. Khi **TLS termination tại reverse proxy**, trình duyệt kiểm tra chứng chỉ của proxy; backend có thể nhận HTTP nội bộ.

Điều đó không tự động bảo đảm đoạn từ proxy tới backend được mã hóa. Chọn HTTP nội bộ chỉ trong mạng tin cậy có kiểm soát, hoặc dùng HTTPS/mTLS giữa các tầng nếu mô hình bảo mật yêu cầu. Một chứng chỉ HTTPS hợp lệ ở phía client không cho biết backend đã dùng TLS.

### Reverse proxy và load balancer

Reverse proxy đứng trước ứng dụng, nhận request ở địa chỉ công khai rồi chuyển tới một hoặc nhiều backend. Nó có thể terminate TLS, cân bằng tải, thêm header, cache, rewrite đường dẫn hoặc chọn upstream. Load balancer có thể hoạt động ở tầng TCP (L4) hoặc HTTP (L7); chỉ những hop hiểu HTTP mới thêm/sửa HTTP headers.

### Địa chỉ công khai (public origin/base URL)

Một **origin** là bộ `scheme + host + port`; ví dụ `https://app.example.test` có port mặc định 443. **Base URL** có thể thêm tiền tố ứng dụng như `https://app.example.test/portal`. Cần phân biệt:

| Thành phần | Ví dụ | Tác dụng |
| --- | --- | --- |
| Scheme | `https` | Protocol mà client sử dụng. |
| Host | `app.example.test` | Host công khai, khác `localhost` hoặc tên máy nội bộ. |
| Port | `443` | Cổng phía client; thường được lược khỏi URL HTTPS nếu mặc định. |
| Path prefix | `/portal` | Đường dẫn ngoài proxy có thể thêm hoặc bỏ khi forward. |
| Request URI | `/portal/api/orders/42` | Đường dẫn request mà người dùng gọi từ bên ngoài. |

Một địa chỉ công khai đúng không thể suy ra chỉ từ cổng `8080` mà Spring dùng để lắng nghe nội bộ.

## 3. Những header giúp backend biết request gốc

Có hai họ thông tin thường gặp:

- `Forwarded` theo RFC 7239, ví dụ `Forwarded: for=192.0.2.10;proto=https;host=app.example.test`. Một chuỗi proxy có thể tạo nhiều phần tử trong header.
- Các header thực tế phổ biến: `X-Forwarded-Proto: https`, `X-Forwarded-Host: app.example.test`, `X-Forwarded-Port: 443`, `X-Forwarded-For: 192.0.2.10` và `X-Forwarded-Prefix: /portal`.

| Header | Mang ý nghĩa gì? | Nhầm lẫn thường gặp |
| --- | --- | --- |
| `Host` | Host của request mà **hop hiện tại** nhận | Không nhất thiết là host ngoài cùng nếu proxy thay đổi Host. |
| `Forwarded` | Thông tin client/host/protocol do các proxy cung cấp theo chuẩn | Không phải dữ liệu xác thực tự thân; có thể bị client giả mạo nếu proxy không lọc. |
| `X-Forwarded-Proto` | Scheme của request phía ngoài, thường là `https` | Không phải bằng chứng backend ↔ proxy có TLS. |
| `X-Forwarded-Host` | Host công khai ban đầu | Không an toàn nếu cho người dùng tự đặt tùy ý. |
| `X-Forwarded-Port` | Port công khai | Không phải `server.port` nội bộ. |
| `X-Forwarded-For` | Thông tin địa chỉ client qua các hop | Là chuỗi do các proxy cung cấp, phải phân tích theo trust chain; không mặc định tin phần tử đầu. |
| `X-Forwarded-Prefix` | Tiền tố public path bị proxy thay đổi | Phải phối hợp đúng với rewrite path và servlet context path. |

**Cảnh báo bảo mật bắt buộc:** client có thể gửi header `Forwarded` hoặc `X-Forwarded-*` giả. **Reverse proxy ở ranh giới tin cậy phải loại bỏ header forwarded từ request bên ngoài rồi gán những giá trị chính xác của chính nó**, kể cả khi hệ thống chỉ định dùng một trong hai họ header. Ngoài ra, cần ngăn người dùng truy cập trực tiếp backend tin tưởng forwarded headers. Nếu không, attacker có thể làm ứng dụng sinh password-reset URL tới tên miền của họ, redirect sai host hoặc ghi sai IP. Spring không tự phân biệt header được proxy đáng tin cậy thêm hay client giả mạo.

## 4. Spring Boot xử lý forwarded headers như thế nào?

Spring Boot hỗ trợ cấu hình `server.forward-headers-strategy`:

| Giá trị | Cách xử lý | Chọn khi nào |
| --- | --- | --- |
| `none` | Không diễn giải forwarded headers để thay thông tin request public | Chạy trực tiếp hoặc không có trust boundary bảo đảm. |
| `native` | Dùng hỗ trợ của container, chẳng hạn cấu hình RemoteIpValve của Tomcat | Container xử lý đủ các loại header mà ứng dụng cần. |
| `framework` | Dùng cơ chế Spring Framework, với Spring MVC là `ForwardedHeaderFilter` | Cần ứng dụng nhận đúng scheme/host/port hoặc behavior redirect qua forwarded headers, nhất là khi container native chưa đáp ứng. |

Spring Boot có thể chọn mặc định khác nhau trên một số môi trường cloud; **không nên suy đoán từ môi trường**. Hãy chỉ rõ lựa chọn trong cấu hình triển khai và kiểm tra request thực tế. Với Tomcat đằng sau proxy terminate TLS, tài liệu Spring Boot khuyên xem `server.tomcat.redirect-context-root=false` để forwarded scheme được tính đến trước khi container tự redirect context root.

Ví dụ Spring Boot 3.5, trong `src/main/resources/application.yml`:

```yaml
server:
  port: 8080
  forward-headers-strategy: framework
  tomcat:
    redirect-context-root: false
```

Khi có header forwarded hợp lệ từ proxy tin cậy, `ForwardedHeaderFilter` bọc request để các handler và thành phần downstream nhìn thấy scheme, host, port, và tùy cấu hình/version là prefix công khai. Filter cũng xử lý tác động của forwarded headers lên một số redirect. Nếu có các filter tự đăng ký, thứ tự áp dụng rất quan trọng: thành phần cần thông tin URL public phải chạy sau khi request đã được xử lý forwarded headers.

**Không đăng ký filter thủ công lần thứ hai** nếu Boot đã tự cấu hình theo `server.forward-headers-strategy: framework`. Tránh cùng lúc bật các cách xử lý forwarding chồng lên nhau mà chưa hiểu và kiểm tra thứ tự.

### Nếu không dùng Spring Boot

Ứng dụng Spring MVC cấu hình Servlet filter thủ công có thể dùng `org.springframework.web.filter.ForwardedHeaderFilter`. Khi tự đăng ký filter, đặt nó đủ sớm và xét các dispatcher type `REQUEST`, `ASYNC`, `ERROR`; các downstream filter/servlet phải thấy request đã được bọc. Filter còn có chế độ `removeOnly` để loại header forwarded mà **không** dùng chúng. Các constructor và option riêng như cách chọn `Forwarded` so với `X-Forwarded-*` hoặc việc xử lý prefix có thể thay đổi theo dòng Spring Framework: đọc Javadoc của đúng version trước khi tự cấu hình.

## 5. Ví dụ Spring MVC chạy được: sinh link và chuyển hướng đúng public URL

Ví dụ dưới đây dùng Java 17+, Spring Boot **3.5.16**, Maven và Tomcat nhúng. Endpoint `/api/public-link` trả về URL tuyệt đối tới `/api/items/42`; endpoint `/go` thực hiện HTTP redirect đến endpoint item. Nếu forwarded headers hợp lệ được xử lý, URL tuyệt đối sẽ phản ánh host/scheme công khai.

**Cấu trúc:**

```text
proxy-demo/
├── pom.xml
└── src/main/
    ├── java/demo/
    │   ├── ProxyDemoApplication.java
    │   ├── LinkController.java
    │   └── NavigationController.java
    └── resources/application.yml
```

**`pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>proxy-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/resources/application.yml`:**

```yaml
server:
  port: 8080
  forward-headers-strategy: framework
  tomcat:
    redirect-context-root: false
```

**`src/main/java/demo/ProxyDemoApplication.java`:**

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProxyDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ProxyDemoApplication.class, args);
    }
}
```

**`src/main/java/demo/LinkController.java`:**

```java
package demo;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@RestController
public class LinkController {
    @GetMapping("/api/public-link")
    public Map<String, String> link() {
        String url = ServletUriComponentsBuilder.fromCurrentContextPath()
                .path("/api/items/{id}")
                .buildAndExpand(42)
                .toUriString();
        return Map.of("url", url);
    }

    @GetMapping("/api/items/{id}")
    public Map<String, Object> item(@PathVariable long id) {
        return Map.of("id", id, "status", "ok");
    }
}
```

**`src/main/java/demo/NavigationController.java`:**

```java
package demo;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class NavigationController {
    @GetMapping("/go")
    public String go() {
        return "redirect:/api/items/42";
    }
}
```

`@Controller` trả tên view `redirect:/...` nên Spring MVC tạo HTTP redirect. **Nếu đổi lớp này thành `@RestController`, chuỗi `redirect:/api/items/42` sẽ được gửi dưới dạng body**, không tự chuyển hướng; phải trả `ResponseEntity` có header `Location` khi muốn redirect từ REST controller.

**Chạy:**

```bash
mvn spring-boot:run
```

Ở terminal khác, khi chưa có forwarded headers:

```bash
curl -s http://localhost:8080/api/public-link
```

JSON body dự kiến (một trường, không có sự khác biệt thứ tự khóa):

```json
{"url":"http://localhost:8080/api/items/42"}
```

Thử mô phỏng proxy **trên môi trường phát triển cô lập**:

```bash
curl -s -H "X-Forwarded-Proto: https" -H "X-Forwarded-Host: app.example.test" -H "X-Forwarded-Port: 443" http://localhost:8080/api/public-link
```

JSON body dự kiến:

```json
{"url":"https://app.example.test/api/items/42"}
```

Quan sát redirect (đừng thêm `-L` vì `-L` sẽ theo tiếp Location):

```bash
curl -i -H "X-Forwarded-Proto: https" -H "X-Forwarded-Host: app.example.test" -H "X-Forwarded-Port: 443" http://localhost:8080/go
```

Kỳ vọng nhận status 3xx (mặc định redirect view thường là **302**) và `Location` dẫn về đường dẫn `/api/items/42` trên origin công khai. Đối chiếu **giá trị Location thực tế**: tùy cấu hình redirect và phiên bản Framework, trình duyệt có thể nhận URL tuyệt đối hoặc đường dẫn tương đối; điều bất biến cần kiểm là browser điều hướng được tới **đúng public origin/path**, không phải backend nội bộ.

**Lưu ý kiểm thử:** gửi trực tiếp `X-Forwarded-*` từ `curl` ở trên chỉ nhằm chứng minh cơ chế biến đổi request trong máy phát triển. Production chỉ chấp nhận những header này từ proxy tin cậy đã làm sạch chúng.

## 6. Cấu hình reverse proxy: TLS, Host và forwarded headers

Ví dụ sau là **khối `location` Nginx minh họa**, đặt bên trong một `server` đã được cấu hình HTTPS hợp lệ, chứng chỉ và `server_name app.example.test`. Nginx là reverse proxy ở **ranh giới công khai cuối cùng** nhận request từ Internet, và ứng dụng chỉ nhận kết nối nội bộ từ Nginx.

```nginx
location / {
    proxy_pass http://127.0.0.1:8080;

    proxy_set_header Host app.example.test;
    proxy_set_header X-Forwarded-Host app.example.test;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-Port 443;
    proxy_set_header X-Forwarded-For $remote_addr;

    proxy_set_header Forwarded "";
    proxy_set_header X-Forwarded-Prefix "";
    proxy_set_header X-Forwarded-Ssl "";
}
```

Giải thích các quyết định trong ví dụ:

- `proxy_pass` chỉ tới backend nội bộ. Trong ví dụ này Nginx và app chạy cùng máy; tại môi trường container, địa chỉ upstream thường khác.
- `Host` và `X-Forwarded-Host` gán **một host công khai đã xác định**, tránh phản chiếu Host không hợp lệ từ phía client. Nếu có nhiều tên miền hợp lệ, cần routing/allowlist host tương ứng chứ không ghi cứng một host cho mọi site.
- `X-Forwarded-Proto` và `X-Forwarded-Port` phản ánh listener HTTPS công khai. Giá trị cố định này chỉ đúng khi khối Nginx thực sự phục vụ HTTPS ở 443. Với kiến trúc nhiều tầng, giá trị được tính ở đúng trust boundary.
- `X-Forwarded-For` gán địa chỉ peer mà edge proxy quan sát; ở đây không nối tiếp dữ liệu `X-Forwarded-For` do client tự gửi. Nếu phía trước còn một proxy đáng tin cậy, phải thiết kế chuỗi địa chỉ thật với cấu hình trusted proxies tương ứng.
- Các header còn lại được xóa khỏi request upstream để client không lén đưa thông tin giả vào; Nginx không chuyển tiếp header có giá trị rỗng từ chỉ thị `proxy_set_header`.
- Firewall/network policy phải chặn kết nối công khai thẳng vào cổng backend 8080 nếu backend sẽ tin forwarded headers.

**Kiểm soát trust là trách nhiệm của hạ tầng.** Không có một cấu hình `server.forward-headers-strategy` nào tự xác minh `X-Forwarded-Host` tới từ proxy đã xác thực. Với nhiều load balancer, CDN hoặc ingress, xác định nơi các header được xóa, tạo lại và chấp nhận ở từng hop; không lấy header client tự khai làm nguồn chân lý.

### Khi phía ngoài có tiền tố `/portal`

Có hai trường hợp khác nhau:

**Trường hợp 1: proxy giữ nguyên path**: Browser gọi `/portal/api/items/42` và backend cũng nhận path đó. Có thể cấu hình ứng dụng có context path `/portal` hoặc cấu trúc mapping phù hợp; không thêm `X-Forwarded-Prefix` vô cớ. Lưu ý `server.servlet.context-path=/portal` là cấu hình cấp Servlet container, khác với chỉ viết thêm một đoạn `@RequestMapping`.

**Trường hợp 2: proxy bỏ tiền tố path**: Browser gọi `/portal/api/items/42`, backend nhận `/api/items/42`. Proxy tin cậy có thể gửi `X-Forwarded-Prefix: /portal` để framework dựng link public kèm tiền tố, khi phiên bản/cách cấu hình forwarding hỗ trợ. Cần test cả link và `Location` thực tế; không suy từ header rằng mọi loại redirect, static asset và context path tự động hoạt động hoàn hảo.

Ví dụ khi Nginx đã có HTTPS server như mục trên, có thể thay khối `location /` bằng mẫu routing có prefix:

```nginx
location /portal/ {
    proxy_pass http://127.0.0.1:8080/;

    proxy_set_header Host app.example.test;
    proxy_set_header X-Forwarded-Host app.example.test;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-Port 443;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Prefix /portal;

    proxy_set_header Forwarded "";
    proxy_set_header X-Forwarded-Ssl "";
}
```

Dấu `/` ở cuối `proxy_pass` có ý nghĩa đối với quy tắc thay thế location prefix của Nginx: trong cấu hình ví dụ, `/portal/api/items/42` tới backend thành `/api/items/42`. Nếu mục tiêu muốn giữ prefix, cấu hình proxy khác đi và phải đồng bộ context path. Khi sử dụng `X-Forwarded-Prefix`, xác minh hỗ trợ thực tế của đúng phiên bản Spring; không đặt đồng thời context path `/portal` và áp thêm prefix `/portal` một cách tùy tiện vì có thể sinh `/portal/portal/...`.

## 7. HTTP redirect: status code, Location và bảo toàn method

Redirect là phản hồi HTTP 3xx chứa `Location`; browser/client có thể gửi request mới tới đích. Trong Spring MVC, `redirect:` tạo redirect view; với REST API có thể trả `ResponseEntity.status(...).location(uri).build()`.

| Status | Ý nghĩa chính | Cách client xử lý method/body |
| --- | --- | --- |
| **301 Moved Permanently** | URL đã chuyển lâu dài | Client có lịch sử thay POST thành GET; không nên mặc định dựa vào bảo toàn method. |
| **302 Found** | Chuyển tạm thời | Với browser và nhiều client, POST có thể bị đổi thành GET. |
| **303 See Other** | Đi tới tài nguyên khác để xem kết quả | Thường dùng sau POST, request tiếp theo là GET (trừ HEAD). |
| **307 Temporary Redirect** | Redirect tạm, **bảo toàn method và body** | Hữu ích khi phải giữ nguyên method. |
| **308 Permanent Redirect** | Redirect vĩnh viễn, **bảo toàn method và body** | Dùng cẩn trọng vì có thể được cache. |

**Ví dụ Post/Redirect/Get (PRG)**: Sau POST tạo bản ghi thành công, trả **303 See Other** tới trang `GET /orders/42`, tránh browser tải lại biểu mẫu gây gửi POST lần nữa. Với redirect 307/308, client tiếp tục gửi cùng method/body tới đích, có thể gây thay đổi dữ liệu tại nơi khác nếu cấu hình sai.

```java
// Đoạn minh họa đặt bên trong một @RestController.
@PostMapping("/api/orders")
public ResponseEntity<Void> create() {
    URI location = URI.create("/api/orders/42");
    return ResponseEntity.status(HttpStatus.SEE_OTHER)
            .location(location)
            .build();
}
```

Đoạn này **không phải file Java độc lập**; cần `import java.net.URI;`, `ResponseEntity` và `HttpStatus` của Spring, cùng `@PostMapping`. Đây là ví dụ trả `Location` tương đối; browser sẽ giải quyết nó theo origin của request hiện tại. Trong ứng dụng thực, ID phải đến từ bản ghi vừa tạo, và thiết kế REST API có thể chọn **201 Created + Location** thay vì redirect tùy hợp đồng của endpoint.

**Không chọn redirect chỉ dựa vào mặc định Spring.** Xác định rõ đây là đổi URL tạm/vĩnh viễn, sau POST hay GET, có cần giữ method/body hay không, và client có thể cache redirect không.

## 8. HTTP → HTTPS: nên chuyển hướng tại đâu?

Mẫu phổ biến là proxy có listener HTTP trên 80 trả redirect sang HTTPS trên 443, rồi dùng HTTPS cho request ứng dụng:

```text
GET http://app.example.test/api/items/42
  -> proxy: 301/308 Location: https://app.example.test/api/items/42
  -> browser: GET https://app.example.test/api/items/42
  -> proxy: chuyển tới Spring backend
```

Nếu muốn dùng **308** cho redirect toàn site, phải chắc chắn mọi client chấp nhận method preservation khi request không phải GET. Với browser tương tác thông thường, 301/302 thường gặp; với HTTP API, đánh giá cẩn thận cách redirect ảnh hưởng POST/PUT/PATCH.

**Tránh hai tầng cùng ép HTTPS mà không thống nhất trust headers**. Ví dụ proxy đã nhận HTTPS nhưng gửi HTTP nội bộ, Spring nhìn thấy `request.isSecure() == false` vì forwarded headers bị thiếu; Spring lại redirect tới HTTPS; browser quay lại proxy và lặp mãi. Một giải pháp là xử lý HTTPS ở edge và cấu hình forwarding đúng để Spring thấy public scheme là `https`. Có thể bỏ redirect lặp ở tầng application nếu proxy đã chịu trách nhiệm.

### HSTS là gì?

**HTTP Strict Transport Security** gửi header `Strict-Transport-Security` trong phản hồi **HTTPS** để thông báo trình duyệt hỗ trợ rằng trong một khoảng thời gian nó chỉ nên dùng HTTPS cho host đó. Ví dụ:

```http
Strict-Transport-Security: max-age=31536000
```

HSTS **không thay thế** việc triển khai HTTPS và redirect HTTP khi cần, và browser bỏ qua HSTS được gửi qua HTTP. `includeSubDomains` và `preload` có tác động diện rộng, khó đảo ngược nhanh; chỉ bật khi mọi subdomain liên quan thực sự đáp ứng HTTPS và có kế hoạch vận hành. Spring Security có hỗ trợ HSTS khi ứng dụng dùng Spring Security; một số proxy cũng có thể phát header này. Hãy xác định **một nơi chịu trách nhiệm** và kiểm tra đầu ra thực tế, tránh cấu hình mâu thuẫn.

### Cookie và OAuth callback

- Cookie chứa session ID/auth token thường cần thuộc tính `Secure` để browser chỉ gửi qua HTTPS; `HttpOnly` giảm khả năng JavaScript truy cập cookie, `SameSite` liên quan việc gửi cookie trong ngữ cảnh cross-site. Chúng có vai trò khác nhau.
- Các callback URL (OAuth/OIDC), password reset URL, link email, Swagger UI redirect hoặc webhook response cần đúng **host/scheme/path công khai**, thường phải trùng allowlist của nhà cung cấp. Nên cấu hình external base URL cố định cho nghiệp vụ cần ổn định tuyệt đối, thay vì lấy trực tiếp Host/Forwarded header từ request không tin cậy.
- HSTS, cookie `Secure` và tính bảo mật TLS không thể xác nhận chỉ bằng việc `curl -k` nhận status 200. Cần test từ một client nhìn thấy chứng chỉ, proxy và redirect như người dùng thật.

## 9. Chọn giữa URL tương đối và tuyệt đối

**URL tương đối** như `/api/items/42` không cần biết host hoặc scheme và thường là lựa chọn đơn giản nhất cho liên kết điều hướng **trong cùng public origin**. Tuy nhiên nếu ứng dụng được xuất bản dưới prefix `/portal`, đường dẫn bắt đầu bằng `/` sẽ tham chiếu gốc host và có thể thiếu `/portal`. Khi đó cần ghép path dựa trên public context đúng hoặc dùng URL tương đối theo vị trí hiện tại đã kiểm thử.

**URL tuyệt đối** như `https://app.example.test/portal/api/items/42` cần thiết khi giá trị sẽ rời khỏi ngữ cảnh request hiện tại (email, callback, QR, redirect cross-origin hợp lệ, tài liệu cho client ngoài hệ thống).

Bốn nguồn sinh URL cần phân biệt:

1. **URL dựa trên request hiện tại**: `ServletUriComponentsBuilder` hoặc các công cụ của Spring MVC nhận dữ liệu request sau khi forwarding đã được xử lý; hữu ích cho link đại diện request, phụ thuộc trust boundary.
2. **External base URL cấu hình tĩnh**: hostname/cổng/prefix chính thức đã kiểm duyệt, tốt cho email và callback; tránh Host header injection và không bị lệ thuộc request nội bộ.
3. **Route tương đối trong browser**: browser tự dùng origin hiện tại, phù hợp link nội bộ; phải lưu ý prefix.
4. **URI/Location do client cung cấp**: không bao giờ redirect tùy ý đến giá trị query `?next=https://...` nếu chưa validate. Đây là lỗi *open redirect*.

Đừng sử dụng `request.getRequestURL()` trước khi kiểm tra proxy config để xây những link nhạy cảm: nếu forwarded headers chưa xử lý, nó có thể là địa chỉ backend; nếu headers chưa được làm sạch, nó có thể mang host do attacker chọn.

## 10. Lỗi mở chuyển hướng và cách xây allowlist

Ví dụ endpoint nhận `/login?next=https://evil.example` rồi trả `Location` bằng nguyên chuỗi next là **open redirect**. Kẻ tấn công có thể gửi link trông như thuộc website thật nhưng chuyển sang tên miền lừa đảo sau khi người dùng click.

Hướng xử lý an toàn tùy mục đích:

- Với redirect trong site, chỉ chấp nhận một tập đường dẫn nội bộ đã định nghĩa (ví dụ `/dashboard`, `/account`), kiểm tra path, encoding, fragment và các cách biểu diễn `//evil.example` hoặc backslash. Thay vì nhận bất kỳ URL nào, có thể map một mã điều hướng như `next=dashboard` sang một route cố định.
- Với redirect ngoài site thực sự cần thiết, chỉ chấp nhận scheme `https` và các **origin** cụ thể trong allowlist được quản trị. So sánh bằng URI parser/host chuẩn hóa, không chỉ dùng `startsWith("https://example.com")` (có thể bị đánh lừa bằng `example.com.evil.test`).
- Không xây redirect password reset/OAuth từ `X-Forwarded-Host` nếu header có thể bị client giả mạo; dùng base URL cấu hình sẵn hoặc whitelist host từ trust boundary.

Ngay cả khi backend không trực tiếp lộ port, sai cấu hình ở proxy cũng khiến `Location` và link tuyệt đối sai hoặc nguy hiểm.

## 11. Kịch bản lỗi và cách tìm nguyên nhân

| Hiện tượng | Tín hiệu cần quan sát | Nguyên nhân / hướng sửa |
| --- | --- | --- |
| Link trong JSON thành `http://localhost:8080/...` | Response body, `request.getScheme()`, `getServerName()` | Chưa xử lý forwarded headers, hoặc proxy không gửi host/scheme công khai. |
| `Location: http://app.example.test/...` khi site dùng HTTPS | HTTP 3xx `Location` | Mất `X-Forwarded-Proto`/`Forwarded: proto=https` hoặc ứng dụng tạo URL dựa trên HTTP nội bộ. |
| Redirect loop liên tục | Chuỗi `Location` và mã 301/302/307/308 qua `curl -I -L -v` | Tầng proxy và Spring đánh giá khác nhau về HTTPS, context path hoặc trailing slash. |
| Link thiếu `/portal` | Public URL đối chiếu backend request URI | Proxy đã rewrite prefix nhưng framework không nhận prefix; hoặc URL được ghép thủ công. |
| Link lặp `/portal/portal` | Public base URL / context path / forwarded prefix | Prefix được thêm ở nhiều tầng; cần chọn một mapping rõ. |
| Link dẫn tới host lạ | `Host`, `Forwarded`, `X-Forwarded-Host` do client gửi | Trust boundary không làm sạch header; cần cố định/allowlist host và chặn truy cập trực tiếp backend. |
| Request HTTPS bị browser chặn mixed content | Browser console/network | HTML/JS tạo tài nguyên `http://`; sửa nguồn sinh URL, CDN config và forwarding. |
| Cookie không xuất hiện sau redirect/login | `Set-Cookie`, domain/path/`Secure`/`SameSite` | Cookie scope sai, proxy/TLS làm request đánh giá khác public scheme, hoặc cross-site flow bị giới hạn. |
| OAuth báo `redirect_uri_mismatch` | Redirect URI gửi tới provider | Scheme/host/port/prefix không trùng URI đăng ký; cấu hình external base URL chính xác. |
| IP trong log luôn là IP proxy | Request remote address/forward chain | Chưa xử lý `X-Forwarded-For` hoặc nguồn client IP được xác định sai trust chain. |

### Kiểm tra bằng công cụ HTTP

```bash
# Xem status, Location, response headers. Không tự động follow redirect.
curl -i https://app.example.test/go

# Xem cả chuỗi redirect, request method và URL ở từng hop.
curl -v -L --max-redirs 5 https://app.example.test/go

# Tại máy có backend nội bộ, thử so sánh trước/sau chuyển tiếp.
curl -i http://localhost:8080/api/public-link
curl -i -H "X-Forwarded-Proto: https" -H "X-Forwarded-Host: app.example.test" http://localhost:8080/api/public-link
```

Đoạn trên minh họa lệnh; `app.example.test` là tên miền mẫu, muốn chạy request tới public site cần có DNS/TLS và proxy thực sự của môi trường đó. Khi test bằng `curl -L`, giới hạn redirect để tránh vòng lặp vô tận. Với endpoint nhạy cảm, không đăng log thô các header chứa thông tin cá nhân hoặc token.

Các câu hỏi chẩn đoán quan trọng: “Client gọi URL nào?”, “Proxy chuyển request URI nào?”, “Header nào được proxy tin cậy gán?”, “Spring xử lý những header đó theo cách nào?”, “Response Location/absolute link thực tế là gì?”.

## 12. Checklist triển khai

1. **Xác định public origin và path** chính thức: scheme HTTPS, host, port, prefix. Ghi rõ proxy có giữ hay xóa prefix.
2. **TLS hợp lệ** tại listener công khai; quyết định backend hop dùng HTTP nội bộ hay HTTPS/mTLS theo phân vùng mạng.
3. **Cấu hình trust boundary**: loại `Forwarded`/`X-Forwarded-*` không tin cậy, đặt lại các header cần dùng, kiểm tra quyền truy cập backend và trusted proxy chain.
4. **Chọn forwarding strategy** đúng: `none`, `native` hoặc `framework`; nếu native không xử lý đủ prefix/redirect, cân nhắc framework và test thực tế.
5. **Kiểm thử liên kết và redirect**: URL tuyệt đối, URL tương đối, `Location`, redirect sau POST, prefix, query string và trường hợp HTTP→HTTPS.
6. **Kiểm tra security/cookie**: HSTS trên HTTPS, `Secure`/`HttpOnly`/`SameSite` phù hợp, callback URLs, open redirect, host injection.
7. **Kiểm tra qua proxy thật** từ một client ngoài mạng backend; thử browser, `curl -i` và các flow liên quan; không chỉ test `localhost:8080`.

## 13. Câu hỏi tự đánh giá

**Hỏi:** Client đã dùng HTTPS nhưng `request.isSecure()` trong Spring vẫn là `false`. Có nhất thiết TLS sai không?  
**Đáp:** Không. Proxy có thể terminate TLS và chuyển HTTP nội bộ. Cần kiểm tra TLS ở client→proxy và cách Spring nhận forwarded scheme; bản thân `request.isSecure()` chỉ phản ánh request mà container/filter biểu diễn.

**Hỏi:** `X-Forwarded-Proto: https` có đủ để tin request đến từ HTTPS không?  
**Đáp:** Không. Header do client cũng có thể gửi; chỉ tin sau khi ranh giới proxy đã xóa/gán lại và bảo vệ backend khỏi truy cập ngoài luồng.

**Hỏi:** Vì sao cùng redirect path `/login` chạy đúng ở root nhưng sai khi public URL là `/portal`?  
**Đáp:** Đường dẫn bắt đầu bằng `/` là absolute-path theo gốc host; proxy có thể strip prefix. Cần xây URL theo external path đúng và xác minh hỗ trợ forwarded prefix.

**Hỏi:** Khi nào nên trả 303 thay vì 307?  
**Đáp:** Sau POST và muốn client tải trang kết quả bằng GET, chọn 303; khi redirect mà phải **giữ** request method/body, chọn 307 (tạm thời) hoặc 308 (vĩnh viễn) khi phù hợp.

**Hỏi:** Đã bật `server.forward-headers-strategy=framework`, có thể công khai cổng backend 8080 cho mọi người không?  
**Đáp:** Không nên; nếu backend nhận trực tiếp forwarded headers giả, attacker có thể gây link/redirect tới host sai. Cần firewall/routing và trust boundary.

## 14. Tài liệu đối chiếu

- [Spring Boot 3.5 — Embedded Web Servers / Running Behind a Front-end Proxy](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html).
- [Spring Framework — ForwardedHeaderFilter và bảo mật forwarded headers](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html).
- [Spring Framework — Redirect Attributes](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/redirecting-passing-data.html).
- [RFC 9110 — HTTP Semantics, 3xx redirection](https://www.rfc-editor.org/rfc/rfc9110).
- [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239).
- [MDN — HTTP Strict Transport Security](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Strict-Transport-Security).

**Điểm cần nhớ:** Spring chỉ sinh được đúng public URL khi đã thống nhất giữa **đường đi request ngoài đời thực**, **TLS/redirect của reverse proxy**, **forwarded headers từ nguồn đáng tin**, và **quy tắc tạo URL trong ứng dụng**.