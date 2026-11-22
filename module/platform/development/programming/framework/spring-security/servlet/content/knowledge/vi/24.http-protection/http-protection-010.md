# Yêu cầu HTTPS, cấu hình chuyển hướng và nguy cơ vòng lặp sau proxy

## 1. Vấn đề cần giải quyết

Khi một API **Spring Security Servlet** chỉ chấp nhận truy cập bảo mật, truy cập từ `http://` thường phải được nâng cấp sang `https://`. Điều này nghe đơn giản trên một máy chủ có TLS trực tiếp, nhưng dễ sinh lỗi khi ứng dụng Spring Boot chạy sau **reverse proxy, ingress hoặc load balancer**.

Một mô hình triển khai phổ biến:

```text
Browser --HTTPS:443--> Reverse proxy / Load balancer
                               |
                               | HTTP:8080 (mạng nội bộ)
                               v
                         Spring Boot Servlet
                         Spring Security
```

Trình duyệt đã dùng HTTPS với proxy, nhưng kết nối **proxy → Spring Boot** vẫn là HTTP. Nếu Spring Security nhìn vào request nội bộ và kết luận rằng client dùng HTTP, nó sẽ trả redirect sang HTTPS. Trình duyệt trở lại cùng URL HTTPS, proxy lại chuyển vào backend bằng HTTP, và quá trình có thể lặp vô hạn.

Muốn cấu hình đúng, phải phân biệt ba việc:

1. **Bắt buộc HTTPS đối với client:** quyết định request nào phải được chuyển hướng hoặc từ chối khi client dùng HTTP.
2. **Nhận biết giao thức gốc sau proxy:** làm cho ứng dụng biết client thực sự kết nối với proxy bằng HTTPS, thông qua metadata đã được proxy đáng tin chuẩn hóa.
3. **Bảo vệ từng đoạn kết nối:** HTTPS client → proxy không đồng nghĩa proxy → backend tự được mã hóa; đoạn nội bộ cần được bảo vệ theo mô hình mạng và rủi ro của hệ thống.

**Điểm mấu chốt:** `requiresSecure()` xử lý chính sách kênh của Spring Security; `server.ssl.*` và TLS listener xử lý giao thức thực tế; `Forwarded`/`X-Forwarded-*` diễn giải giao thức gốc sau proxy. Chúng liên quan nhưng không thể thay thế nhau.

## 2. HTTPS có nghĩa gì trong hệ thống nhiều lớp?

HTTPS là HTTP được bảo vệ bởi TLS. Trình duyệt xác minh chứng chỉ của máy chủ TLS, thiết lập khóa mã hóa rồi truyền dữ liệu qua kết nối an toàn. Khi có reverse proxy kết thúc TLS (*TLS termination*), proxy giải mã request trước khi chuyển tiếp về backend.

Có hai dạng triển khai chính.

### A. TLS trực tiếp tại ứng dụng

```text
Client --HTTPS--> Spring Boot (TLS listener)
```

Ứng dụng mở cổng HTTPS và tự dùng chứng chỉ/keystore. Servlet request thường có:

```text
request.isSecure() = true
request.getScheme() = "https"
```

Một request HTTP vào cổng riêng có thể được redirect, từ chối hoặc không được mở cổng tùy kiến trúc.

### B. TLS kết thúc ở proxy

```text
Client --HTTPS--> Proxy --HTTP--> Spring Boot
```

Nếu **không xử lý forwarded headers**, Servlet request phía backend thường phản ánh kết nối thật mà backend thấy:

```text
request.isSecure() = false
request.getScheme() = "http"
request.getServerPort() = 8080
```

Dù browser đang hiện biểu tượng khóa HTTPS, Spring Security có thể nghĩ request không an toàn. Để diễn giải chính xác giao thức gốc, proxy phải chuyển metadata đáng tin và Spring Boot phải được cấu hình đọc metadata ấy.

`X-Forwarded-Proto: https` thường mô tả scheme bên ngoài. Header chuẩn RFC 7239 có dạng `Forwarded: proto=https;host=api.example.com`. Các thành phần như host và port cũng cần đúng khi dựng redirect tuyệt đối.

## 3. Spring Security quyết định chuyển hướng ra sao?

Trong Spring Security dùng Servlet, có thể yêu cầu request đi qua kênh HTTPS bằng DSL `requiresChannel(...)`. Cơ chế channel security kiểm tra request mà nó nhận được; khi yêu cầu secure nhưng request không được nhận diện là secure, Spring Security có thể trả **redirect** đến URL HTTPS.

```java
http.requiresChannel(channel ->
        channel.anyRequest().requiresSecure());
```

Điều này có ba hệ quả:

- Redirect là **response gửi về client**, không phải một lần backend tự kết nối HTTPS.
- `requiresSecure()` **không tự cài chứng chỉ, mở cổng HTTPS hay biến HTTP giữa proxy và backend thành TLS**.
- Nếu backend nhìn sai scheme do proxy không chuyển hoặc không được tin cậy, mọi lần truy cập hợp lệ qua HTTPS vẫn có thể bị redirect lại.

Spring Security cũng cần xác định URL chuyển hướng: scheme, hostname và port. Với một số cấu hình, mapping port HTTP → HTTPS có thể dùng các giá trị mặc định (chẳng hạn 8080 → 8443). Đây là điều cần kiểm tra khi ứng dụng đứng sau proxy dùng public port 443.

**Không coi redirect là hàng rào bảo mật duy nhất.** Request HTTP đầu tiên có thể đã làm lộ URL, cookie không có `Secure` hoặc dữ liệu nhạy cảm trước khi server kịp trả redirect. Ở biên Internet, ưu tiên phục vụ HTTPS đúng cách, redirect request HTTP sớm và bảo vệ cookie.

## 4. Ví dụ ứng dụng Spring Boot 3.3.x và Java 17+

Ví dụ dưới đây là ứng dụng Spring MVC + Spring Security Servlet tối giản để quan sát **yêu cầu HTTPS và quá trình redirect**. Endpoint công khai dùng riêng cho kiểm thử, tránh việc lỗi xác thực làm nhiễu kết quả. Khi triển khai API thật phải thêm quy tắc xác thực/phân quyền đúng nghiệp vụ.

### 4.1. Các dependency

Ví dụ Gradle Groovy trong `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

### 4.2. Lớp khởi động

Tạo `src/main/java/demo/https/HttpsDemoApplication.java`:

```java
package demo.https;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpsDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpsDemoApplication.class, args);
    }
}
```

### 4.3. SecurityFilterChain: bắt buộc HTTPS

Tạo `src/main/java/demo/https/HttpSecurityConfig.java`:

```java
package demo.https;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class HttpSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .requiresChannel(channel ->
                        channel.anyRequest().requiresSecure())
                .authorizeHttpRequests(auth ->
                        auth.anyRequest().permitAll())
                .build();
    }
}
```

`anyRequest().requiresSecure()` thể hiện chính sách cho mọi đường dẫn. `permitAll()` ở đây **chỉ giúp ví dụ tập trung vào HTTPS**, không phải chính sách production. Một ứng dụng thật thường cấu hình các endpoint cần xác thực và quyền truy cập riêng. Channel security không thay thế authorization.

Tạo `src/main/java/demo/https/PingController.java`:

```java
package demo.https;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {
    @GetMapping("/public/ping")
    public Map<String, String> ping() {
        return Map.of("message", "pong");
    }
}
```

Với request **được hệ thống nhận diện là secure**, controller trả JSON tương đương:

```json
{"message":"pong"}
```

Thứ tự thuộc tính JSON không có ý nghĩa. Với request bị nhận diện là HTTP, chính sách channel chạy trước MVC nên controller không được gọi.

### 4.4. Chạy và quan sát redirect trong môi trường local

Dùng Gradle wrapper của dự án:

```bash
./gradlew bootRun
curl -i --max-redirs 0 http://localhost:8080/public/ping
```

Trên Windows PowerShell, có thể chạy `.\gradlew.bat bootRun` rồi gọi `curl.exe` (tránh alias `curl` của PowerShell cũ).

Khi ứng dụng chỉ mở HTTP 8080, kết quả thường có HTTP **3xx** với header `Location` trỏ đến một URL HTTPS, chẳng hạn:

```http
HTTP/1.1 302
Location: https://localhost:8443/public/ping
```

**Đây là ví dụ minh họa, không cam kết chính xác status hoặc port trong mọi môi trường.** URL phụ thuộc port mapping, server/proxy và cách cấu hình redirect. Nếu không có HTTPS listener tại đích, việc dùng `curl -L` để theo redirect sẽ thất bại khi kết nối, dù quy tắc redirect đang hoạt động đúng. Không nhầm lỗi “không có server trên 8443” với vòng lặp HTTPS sau proxy.

## 5. TLS termination tại reverse proxy: cấu hình phía ứng dụng

Trong production, giả sử public URL là `https://api.example.com`, proxy phục vụ TLS trên 443 và đưa traffic đến Spring Boot qua HTTP 8080.

Ứng dụng cần hiểu **client đã truy cập bằng HTTPS**. Spring Boot Servlet hỗ trợ xử lý forwarded headers bằng cấu hình:

```yaml
# src/main/resources/application-prod.yml
server:
  forward-headers-strategy: framework
```

Với chiến lược `framework`, Spring Boot sử dụng cơ chế của Spring Framework như `ForwardedHeaderFilter` cho Servlet, giúp điều chỉnh thông tin scheme, host và port từ các forwarded headers khi xử lý request. Một lựa chọn khác là `native`, tận dụng hỗ trợ của Servlet container (ví dụ Tomcat `RemoteIpValve`); chi tiết trust proxy và tập header áp dụng tùy container. `none` là không dùng việc chuyển đổi này.

Khi cấu hình đúng và proxy gửi `X-Forwarded-Proto: https`, request phía Spring Security có thể được **nhận diện** như một request secure dù socket giữa proxy và backend là HTTP.

```text
Browser:  HTTPS https://api.example.com/public/ping
Proxy:    TLS được xử lý ở biên
Proxy -> Spring Boot:
          GET /public/ping HTTP/1.1
          Host: api.example.com
          X-Forwarded-Proto: https
          X-Forwarded-Host: api.example.com
          X-Forwarded-Port: 443
Spring Boot (đã áp dụng trusted forwarded metadata):
          isSecure() = true
          scheme = https
          serverPort = 443
Spring Security:
          HTTPS yêu cầu đã thỏa mãn -> không redirect
Controller:
          trả {"message":"pong"}
```

Lưu ý rằng các giá trị được **diễn giải từ metadata forwarded**, không chứng minh backend đang thực sự giao tiếp TLS trực tiếp với proxy. Việc mã hóa đoạn nội bộ cần giải quyết bằng TLS backend, mTLS, VPN/overlay hoặc mạng riêng đáng tin tùy yêu cầu.

### Proxy phải chuẩn hóa forwarded headers

Ví dụ **đoạn cấu hình `location` của Nginx trong HTTPS virtual host**, không phải cấu hình Nginx hoàn chỉnh:

```nginx
location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host api.example.com;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-Host api.example.com;
    proxy_set_header X-Forwarded-Port 443;
}
```

Ví dụ dùng một public hostname cố định. Thực tế, proxy có thể cần chuyển cả thông tin prefix/path, original client IP và host của từng tenant; phải cấu hình từ **giá trị đã được proxy xác minh**. Nếu TLS kết thúc ở một load balancer nằm **trước** Nginx, Nginx cũng phải hiểu giao thức bên ngoài và chỉ tin metadata do tầng upstream đáng tin cung cấp; không được mặc định đặt `https` cho cả request HTTP chưa được nâng cấp.

Ở HTTP virtual host tại biên, redirect có thể thực hiện như sau (đoạn Nginx minh họa, cần kết hợp cấu hình TLS và `server_name` thực tế):

```nginx
server {
    listen 80;
    server_name api.example.com;
    return 308 https://api.example.com$request_uri;
}
```

HTTP 308 duy trì method và request body theo ngữ nghĩa redirect, khác với những trường hợp 301/302 có thể bị client đổi sang GET. Dù vậy, không thiết kế API nhạy cảm dựa vào việc gửi POST có credential qua HTTP trước rồi mới nâng cấp: client phải dùng HTTPS ngay từ đầu.

## 6. Vòng lặp redirect xảy ra thế nào?

Giả sử browser đã gửi `GET https://api.example.com/public/ping`. Proxy giải mã TLS và forward tới backend qua HTTP nhưng **không gửi `X-Forwarded-Proto`** hoặc Spring Boot không dùng forwarded headers.

```text
(1) Browser -> https://api.example.com/public/ping
               |
(2) Proxy TLS: HTTPS -> nội bộ HTTP:8080
               |
(3) Spring Boot: isSecure() = false
               |
(4) Spring Security: requiresSecure()
                     -> trả 302 Location: https://api.example.com/public/ping
               |
(5) Browser theo Location HTTPS (vẫn chính URL đã gọi)
               |
(6) Quay lại (2), lặp 302 -> 302 -> 302 ...
```

Biểu hiện có thể là browser báo `ERR_TOO_MANY_REDIRECTS` hoặc `curl` dừng vì vượt số lần redirect. Khi host/port cũng sai, `Location` có thể trỏ đến `https://localhost:8443`, `https://api.example.com:8443` hoặc hostname nội bộ: đó là một nhóm lỗi cấu hình cùng nguồn gốc, nhưng không nhất thiết là vòng lặp.

**Nguyên nhân thường gặp:**

1. Proxy không chuyển `Forwarded` / `X-Forwarded-Proto`.
2. Proxy chuyển đúng nhưng Boot đang cấu hình `server.forward-headers-strategy=none` hoặc cấu hình profile chưa kích hoạt.
3. Có nhiều tầng proxy; proxy cuối **ghi đè `X-Forwarded-Proto: http`** dựa vào hop nội bộ thay vì giữ thông tin scheme của client từ upstream đáng tin.
4. Ứng dụng có `ForwardedHeaderFilter` chỉ ở chế độ bỏ headers (`removeOnly`) hoặc có một filter/proxy khác sửa metadata theo cách không tương thích.
5. Port mapping hoặc các header host/port không phù hợp với địa chỉ công khai, dẫn đến redirect sai đích.
6. Hai lớp tạo redirect với điều kiện mâu thuẫn (gateway sửa host/path, Spring redirect sang scheme/port khác, rewrite quay trở lại).
7. Proxy tự đổi từ HTTP sang HTTPS ở cạnh ngoài nhưng Spring ở backend vẫn xem mọi request là HTTP: edge redirect riêng **không tự sửa** nhận thức scheme của Spring.

Không khắc phục vòng lặp bằng cách tắt HTTPS requirement trên toàn hệ thống khi nguyên nhân là metadata bị hiểu sai. Cần xác nhận chính xác **client scheme**, **forwarded scheme**, **Servlet `isSecure()`** và **Location** ở từng hop.

## 7. Kiểm tra thực tế, theo thứ tự

### 7.1. Kiểm tra từ client

Từ một máy có quyền truy cập public URL:

```bash
curl -i --max-redirs 0 http://api.example.com/public/ping
curl -i --max-redirs 0 https://api.example.com/public/ping
curl -v -L --max-redirs 5 https://api.example.com/public/ping
```

Kỳ vọng với hệ thống cấu hình chuẩn: HTTP đi đến HTTPS qua tối đa một bước redirect ở biên (nếu cổng HTTP được mở); HTTPS tới endpoint hợp lệ thì trả response ứng dụng thay vì lại redirect sang chính HTTPS URL.

Trong chuỗi log của `curl -v`, hãy ghi các giá trị `HTTP status`, `Location`, host và port ở **mỗi** lần chuyển hướng. Đừng chỉ nhìn response cuối cùng.

Nếu production chỉ cho phép HTTPS và cổng 80 đóng hoàn toàn, request HTTP có thể thất bại ngay ở tầng mạng; đó cũng có thể là chính sách hợp lệ, không nhất thiết có redirect.

### 7.2. Kiểm tra tại proxy

Xác nhận:

- Nơi **thực sự kết thúc TLS** và cổng công khai 443.
- Header scheme được tính từ request **trước TLS termination**, không tính từ hop HTTP phía sau.
- Giá trị `Forwarded`/`X-Forwarded-Proto`, `X-Forwarded-Host`, `X-Forwarded-Port` mà proxy cuối gửi đến backend.
- Proxy có redirect riêng không, redirect đó có thay đổi host, path hoặc port không.
- Có rewrite scheme/path giữa ingress, API gateway và reverse proxy hay không.
- Backend được truy cập trực tiếp từ Internet không; nếu có, forwarded headers có thể bị giả mạo.

Một ví dụ log chẩn đoán **nội bộ, tạm thời** sau khi forwarded processing đã chạy:

```text
request.getScheme() = https
request.isSecure() = true
request.getServerName() = api.example.com
request.getServerPort() = 443
```

Không xuất những thông tin hạ tầng chi tiết này ra public endpoint chỉ để debug. Nếu ứng dụng vẫn ghi `http/false/8080` cho traffic công khai HTTPS, điều tra metadata và thứ tự filter trước khi sửa Security rules.

### 7.3. Khoanh vùng chính sách security

Tìm các nguồn gây chuyển hướng:

- `.requiresChannel(...requiresSecure())` hoặc chính sách HTTPS tương đương trong `SecurityFilterChain`.
- Redirect HTTP → HTTPS tại load balancer hoặc ingress.
- Các Spring MVC redirect hay controller tự trả `Location`.
- Cấu hình context path, virtual host, port mapping và `X-Forwarded-Prefix`.
- Redirect của authentication (login page/OAuth2 callback): đây có thể là chuyển hướng đăng nhập khác với redirect nâng cấp HTTPS.

HTTP `301`, `302`, `307`, `308` đều là redirect, nhưng cần đọc `Location` và ngữ cảnh để biết ai tạo ra. Với login/OAuth2, hostname và scheme trong callback sai có thể gây vòng lặp riêng, ngay cả khi request đã secure.

## 8. Ranh giới tin cậy: forwarded headers có thể bị giả

`X-Forwarded-Proto` là HTTP header, tự nó **không có chữ ký xác thực**. Một client có thể gửi:

```http
GET /public/ping HTTP/1.1
Host: api.example.com
X-Forwarded-Proto: https
```

Nếu backend HTTP mở trực tiếp ra Internet và ứng dụng tin header này, Spring Security có thể coi request đang secure dù client không hề dùng TLS. Vì vậy cấu hình `server.forward-headers-strategy=framework` **chỉ đúng khi triển khai đi kèm ranh giới proxy tin cậy**.

Các biện pháp cần làm cùng nhau:

1. Chỉ cho proxy, ingress hoặc load balancer đáng tin kết nối tới backend; hạn chế port nội bộ bằng firewall/security group/network policy.
2. Tại proxy biên, **xóa hoặc ghi đè** `Forwarded` và `X-Forwarded-*` do Internet client tự đưa vào; sinh header mới từ connection và routing đã xác minh.
3. Với nhiều hop, định nghĩa rõ proxy nào được tin và cách xác định scheme/host ban đầu; không nối/ghi đè giá trị một cách tùy tiện.
4. Nếu dùng hỗ trợ **native** của container, cấu hình danh sách proxy/IP đáng tin phù hợp, và kiểm thử `isSecure()` sau xử lý.
5. Khi không cần headers chuyển tiếp, tắt việc tin chúng; khi cần, không bật chỉ vì “nó làm hết vòng lặp”.
6. Kiểm tra `Host`, forwarded host và port trước khi dùng chúng tạo absolute redirect, tránh tạo `Location` trỏ sang domain do attacker kiểm soát.

Trong Spring Framework, `ForwardedHeaderFilter` có thể tiêu thụ cả header chuẩn `Forwarded` lẫn một số `X-Forwarded-*`; chính filter không tự phân biệt header do proxy tin cậy thêm vào hay do client tự gửi. **Proxy phải chịu trách nhiệm sanitization**. Nếu hạ tầng yêu cầu cứng hóa trust theo IP, tham khảo cơ chế native/container hoặc gateway được kiểm soát thích hợp.

## 9. Redirect tại edge, tại ứng dụng, hay cả hai?

| Vị trí | Có lợi gì | Điều phải lưu ý |
| --- | --- | --- |
| **Edge/proxy** | Redirect HTTP sớm, hiểu public host/port, tránh gửi request HTTP không cần thiết vào app | Phải cấu hình TLS/cert và routing đúng; không tạo loop qua proxy khác |
| **Spring Security `requiresSecure()`** | Áp chính sách cho request khi vào app; có tác dụng phòng vệ khi đi vào đường HTTP chưa bị chặn | Cần nhận diện chính xác scheme sau proxy và cấu hình đúng Location |
| **Cả hai** | Edge nâng cấp sớm, app kiểm tra channel bổ sung | Phải thống nhất forwarded headers và kiểm thử cả hai đường đi |

Trong nhiều hệ thống production, phương án dễ vận hành là **proxy chịu trách nhiệm cổng 80/443 và redirect công khai**, Spring Security yêu cầu HTTPS như chính sách bổ sung trên request đã được diễn giải đúng. Nếu app chỉ phục vụ lưu lượng qua proxy, firewall không cho request chưa qua proxy vào cổng HTTP backend.

Nếu mạng proxy → backend không được coi là tin cậy, bật TLS ở hop đó (re-encryption hoặc mTLS) thay vì xem forwarded headers là giải pháp mã hóa. Forwarded headers chỉ là thông tin *về* kết nối client ban đầu.

## 10. HSTS hỗ trợ gì và không hỗ trợ gì?

HSTS (`Strict-Transport-Security`) là response header khiến trình duyệt ghi nhớ phải ưu tiên HTTPS cho host trong thời gian nhất định sau khi trình duyệt **nhận được header qua một kết nối HTTPS hợp lệ**. Ví dụ:

```http
Strict-Transport-Security: max-age=31536000; includeSubDomains
```

Trong Spring Security Servlet, cơ chế security response headers thường hỗ trợ gửi HSTS cho request được xem là secure. Nhưng:

- HSTS **không thay thế** TLS certificate, HTTPS listener hoặc sửa forwarded headers.
- HSTS trên response HTTP không có tác dụng thiết lập chính sách HSTS đáng tin.
- Nếu Spring Boot sau proxy không nhận biết request là secure, cần kiểm tra HSTS đang được phát ở **edge HTTPS** hay ứng dụng.
- `includeSubDomains` chỉ phù hợp nếu các subdomain liên quan đều sẵn sàng HTTPS; không bật `preload` cho cả miền khi chưa đánh giá toàn bộ domain và điều kiện của danh sách preload.
- HSTS giúp các lần truy cập sau của trình duyệt dùng HTTPS, nhưng không loại bỏ hoàn toàn rủi ro của lần truy cập đầu khi chưa có chính sách được ghi nhớ.

HSTS không phải một cơ chế server-side xử lý request HTTP từ mọi loại client. API consumers ngoài browser vẫn cần yêu cầu HTTPS bằng endpoint, SDK, proxy và quy tắc bảo mật riêng.

## 11. Redirect không thay thế security nghiệp vụ

Sau khi channel HTTPS đã đúng, HTTP status còn có thể đến từ các cơ chế khác:

- `401 Unauthorized` khi chưa có authentication hợp lệ;
- `403 Forbidden` khi thiếu quyền hoặc CSRF token không hợp lệ;
- `404` khi sai route;
- `3xx` liên quan login/session/OAuth2;
- lỗi trình duyệt về chứng chỉ TLS, HSTS hoặc mixed content.

**HTTPS bảo vệ kết nối; authentication xác định danh tính; authorization quyết định quyền; CSRF bảo vệ một số request có thông tin xác thực gắn tự động.** Không dùng `.permitAll()` của ví dụ cho dữ liệu thật. Không tắt CSRF, CORS hoặc Security filter chain chỉ để “giải quyết” loop mà chưa xác định điều kiện redirect.

Cookie phiên nên dùng `Secure` khi truyền qua HTTPS, kết hợp `HttpOnly` và `SameSite` tùy luồng ứng dụng. Nếu request có token/password hoặc body nhạy cảm, client cần gọi HTTPS ngay từ đầu; việc nhận redirect từ HTTP không cứu được nội dung đã đi qua đường truyền ban đầu.

## 12. Kiểm thử Java có thể chạy được

Với dự án ở phần 4, tạo `src/test/java/demo/https/HttpsChannelTest.java`:

```java
package demo.https;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.startsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class HttpsChannelTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void insecureRequestIsRedirected() throws Exception {
        mvc.perform(get("/public/ping").secure(false))
                .andExpect(status().is3xxRedirection())
                .andExpect(header().string(
                        HttpHeaders.LOCATION, startsWith("https://")));
    }

    @Test
    void secureRequestReachesController() throws Exception {
        mvc.perform(get("/public/ping").secure(true))
                .andExpect(status().isOk())
                .andExpect(content().json("{\"message\":\"pong\"}"));
    }
}
```

Chạy với wrapper:

```bash
./gradlew test
```

Trên Windows dùng `.\gradlew.bat test`.

Test này chứng minh chính sách `requiresSecure()` nhận diện request secure/insecure trong Spring Security và endpoint trả body đúng. `MockMvc` là mô phỏng Servlet request; **nó không chứng minh** môi trường ingress thật đã thêm/sanitize forwarded headers đúng cách, TLS termination và cổng 443 hoạt động, hay redirect ngoài Internet không lặp. Cần kiểm thử bổ sung tại môi trường staging qua public host và reverse proxy thật.

Một bộ test tích hợp triển khai tối thiểu nên kiểm tra:

1. HTTP public (nếu mở) có redirect sang HTTPS public host, đúng path/query và status chủ định.
2. HTTPS public trả response cuối đúng, không còn `Location` sang cùng URL.
3. Application nhìn nhận đúng scheme/host/port sau trusted proxy.
4. Request trực tiếp vào backend từ Internet bị chặn bởi mạng.
5. Header `X-Forwarded-Proto` giả từ client không được làm thay đổi kết quả tại proxy.
6. HSTS, cookie `Secure`, authentication, authorization và callback URL còn đúng.
7. Có ít nhất một trường hợp POST/login và một trường hợp API dùng credential để phát hiện chuyển hướng không mong muốn.

## 13. Một số biến thể triển khai cần lưu ý

**Kubernetes ingress hoặc cloud load balancer:** có thể có nhiều tầng TLS termination và nhiều loại forwarded header. Cần xác định layer cuối cùng có thông tin scheme đáng tin. Khi thay ingress controller hoặc bật thêm CDN, cấu hình `X-Forwarded-Proto` trước đây có thể không còn phù hợp.

**Chạy HTTPS trực tiếp trong Spring Boot:** phải cấu hình chứng chỉ và TLS server thực tế (`server.ssl.*`); `requiresSecure()` chỉ yêu cầu channel và có thể redirect đến port không mở nếu thiếu HTTPS listener.

**Nhiều SecurityFilterChain:** bảo đảm chính sách HTTPS áp dụng cho đúng request matcher/chain. Một `SecurityFilterChain` hẹp cho admin và một chain khác cho API có thể có chính sách channel khác nhau nếu không được cấu hình nhất quán.

**`http://localhost` trong phát triển:** có thể muốn chạy HTTP local để đơn giản. Giữ policy phù hợp profile và môi trường; không dựa vào exception tạm cho local để nới policy trên public host. Với ví dụ có `requiresSecure()` toàn cục, local HTTP sẽ chủ động redirect nên không thể dùng `curl -L` như một endpoint hoạt động trọn vẹn khi chưa có TLS.

**WebSocket và callback bên thứ ba:** handshake WebSocket secure dùng `wss://`. OAuth2/OIDC callback cần scheme và public host chính xác; cấu hình proxy sai có thể khiến redirect URI gửi đến identity provider sai và tạo lỗi khác với vòng lặp channel security.

## 14. Bảng nhận diện lỗi và cách xử lý

| Triệu chứng | Chẩn đoán khả dĩ | Hướng sửa |
| --- | --- | --- |
| Trình duyệt báo quá nhiều redirect với HTTPS public | Backend nhìn HTTPS client thành HTTP sau proxy | Kiểm tra `X-Forwarded-Proto`/`Forwarded`, `server.forward-headers-strategy`, trusted proxy chain |
| `Location: https://localhost:8443/...` | Backend dùng internal host/port hoặc port mapping | Kiểm tra forwarded host/port và redirect tại edge |
| HTTP local 8080 tự chuyển sang 8443, rồi lỗi connect | Policy yêu cầu HTTPS nhưng không có TLS listener local | Dùng HTTPS listener hoặc cấu hình profile dev riêng; không coi là lỗi loop proxy |
| HTTPS trả `401`/`403` | Security nghiệp vụ hoặc CSRF | Kiểm tra authentication/authorization/CSRF, không xóa yêu cầu HTTPS |
| HTTPS không có HSTS | Header writer ở tầng app không nhận diện secure hoặc edge chưa phát header | Kiểm tra HSTS tại response HTTPS và scheme nhận diện |
| HTTPS hoạt động khi đi qua proxy nhưng HTTP trực tiếp đến backend cũng bị coi là HTTPS | Forwarded headers giả mạo được tin | Chặn truy cập trực tiếp và sanitize header ở proxy |
| Redirect luân phiên giữa hai hostname hoặc hai path | Rewrite/proxy route/callback không thống nhất | Đối chiếu từng `Location`, host, scheme, port, prefix ở các hop |
| Chỉ một số route không redirect hoặc không được bảo vệ | Nhiều filter chain, matcher hoặc gateway rule | Đối chiếu rule theo URL/method và filter chain thực tế |
| HTTP POST mất body hoặc đổi thành GET sau redirect | Cách client xử lý 301/302 hoặc điều kiện chuyển hướng | Gửi trực tiếp HTTPS, cân nhắc 307/308 ở edge theo contract client |

## 15. Checklist triển khai an toàn

Trước khi xác nhận một API Servlet đã yêu cầu HTTPS đúng:

- Định nghĩa rõ URL public canonical: scheme `https`, hostname, port, context path.
- Xác định **chính xác** nơi TLS kết thúc; bảo vệ đoạn kết nối nội bộ theo chính sách hạ tầng.
- Thiết lập redirect HTTP → HTTPS ở biên nếu cổng HTTP được mở.
- Nếu Spring Security áp `requiresSecure()`, xác minh nó thấy đúng `isSecure()` sau proxy.
- Cấu hình `server.forward-headers-strategy` phù hợp **và** chỉ tin forwarded headers của proxy đã xác minh.
- Đóng cổng backend với Internet; proxy xóa/ghi đè forwarded headers không đáng tin.
- Thử response HTTPS public không tạo redirect lặp; kiểm tra từng giá trị `Location`.
- Thử hostname/port/context path, POST có body, đăng nhập, cookie, CSRF và callback thực.
- Thiết lập HSTS, `Secure` cookie khi phù hợp, theo dõi 3xx tăng đột biến và cảnh báo redirect loop.

## Ghi nhớ

`requiresSecure()` yêu cầu request được Spring Security nhận diện là HTTPS và có thể redirect khi không thỏa điều kiện. Trong mô hình **HTTPS client → proxy → HTTP backend**, muốn tránh vòng lặp phải chuyển đúng metadata scheme/host/port qua **proxy đáng tin** và cấu hình Spring Boot diễn giải metadata ấy. Chỉ bật forwarded headers khi proxy đã kiểm soát nguồn của chúng; đồng thời đặt redirect HTTP ở biên, quản lý TLS thật và kiểm thử public URL qua toàn bộ đường đi.