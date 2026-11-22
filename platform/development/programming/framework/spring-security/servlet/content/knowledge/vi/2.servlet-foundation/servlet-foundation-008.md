# HTTPS, proxy và ranh giới tin cậy của các header chuyển tiếp trong Spring Security Servlet

## 1. Mục tiêu và bối cảnh

Trong ứng dụng Spring Boot chạy **Servlet stack** (Spring MVC và Servlet container như Tomcat), request từ trình duyệt thường không đến ứng dụng trực tiếp. Trên môi trường production, nó có thể đi qua CDN, load balancer, API gateway, ingress controller hoặc reverse proxy. Những thành phần này có thể chấm dứt kết nối TLS và mở một kết nối mới tới backend.

Bài học tập trung vào ba câu hỏi liên quan chặt chẽ:

1. **HTTPS được bảo vệ trên đoạn kết nối nào?** Khi proxy nhận HTTPS nhưng chuyển HTTP tới backend, ứng dụng có biết request gốc của client là HTTPS không?
2. **Spring Security quyết định điều hướng và bảo vệ dựa trên thông tin nào?** Vì sao sai `scheme`, `host` hoặc `port` có thể gây redirect loop, URL sai hoặc mất header HSTS?
3. **Ai được phép khai báo các header chuyển tiếp?** Vì sao không được tin ngay `Forwarded`, `X-Forwarded-Proto`, `X-Forwarded-Host` hay `X-Forwarded-For` do một HTTP client gửi tới?

Sau bài này, bạn cần phân biệt được kết nối TLS thực tế với thông tin giao thức được *chuyển tiếp*; hiểu cách cấu hình Spring Boot/Spring Security trên Servlet khi có reverse proxy tin cậy; và kiểm tra được những lỗi triển khai phổ biến mà không biến một header do client tự khai thành bằng chứng đáng tin.

## 2. HTTPS và reverse proxy: hai kết nối, hai góc nhìn

Một kiến trúc phổ biến:

```text
Trình duyệt
   |  HTTPS/TLS; URL công khai: https://app.example.test
   v
[Reverse proxy / Load balancer]
   |  HTTP nội bộ, ví dụ http://127.0.0.1:8080
   |  + metadata do proxy kiểm soát:
   |    X-Forwarded-Proto: https
   |    X-Forwarded-Host: app.example.test
   |    X-Forwarded-Port: 443
   v
[Servlet container] -> [Spring Security filters]
                              |
                         DispatcherServlet
                              |
                         Controller/Service
```

**TLS termination (chấm dứt TLS)** nghĩa là proxy thực hiện bắt tay TLS và giải mã dữ liệu của kết nối client tại proxy. Kết nối tiếp theo từ proxy đến backend là **kết nối riêng**, có thể dùng HTTP hoặc HTTPS. Vì vậy:

- **Client → proxy qua HTTPS** không tự động có nghĩa **proxy → backend cũng được mã hóa**. Nếu backend nằm trên mạng không đáng tin, cần TLS cho chặng đó; trong một số kiến trúc còn cần xác thực hai chiều (mTLS).
- Nếu backend nhận HTTP nội bộ trực tiếp, Servlet container có thể thấy `request.getScheme() == "http"`, `request.isSecure() == false` và cổng nội bộ `8080`. Nó chưa biết client ngoài Internet đã dùng HTTPS.
- Proxy có thể cung cấp metadata về request bên ngoài; backend chỉ nên dùng metadata ấy khi nó đi qua **chuỗi proxy đã được xác minh và kiểm soát**.
- Việc proxy nói "request gốc là HTTPS" không thay thế việc thực thi TLS thực tế ở biên. Chỉ đặt `X-Forwarded-Proto: https` trên kết nối HTTP công khai không làm kết nối đó trở nên an toàn.

Trong môi trường không có proxy, Servlet container tự quan sát TLS và không cần header chuyển tiếp. Không nên bật xử lý forwarded headers chỉ vì ứng dụng sử dụng Spring Security.

## 3. Các header chuyển tiếp chứa gì?

Proxy cần mô tả lại request mà client nhìn thấy. Có hai họ header thường gặp:

| Header | Ý nghĩa thường gặp | Điều cần cảnh giác |
| --- | --- | --- |
| `Forwarded` (chuẩn RFC 7239) | Có các tham số như `for`, `proto`, `host`, tùy trường hợp `by`; có thể biểu diễn nhiều hop | Một client cũng tự gửi được header này; nhiều phần tử cần được phân tích theo chuỗi proxy tin cậy |
| `X-Forwarded-Proto` | Giao thức ở phía client, thường `https` hoặc `http` | Giá trị `https` không tự chứng minh có TLS |
| `X-Forwarded-Host` | Host công khai mà client truy cập | Host giả có thể làm sai redirect và URL tuyệt đối |
| `X-Forwarded-Port` | Cổng công khai, thường `443` | Dễ sai khi edge dùng cổng khác hoặc metadata giữa các proxy mâu thuẫn |
| `X-Forwarded-For` | Danh sách địa chỉ IP đi qua các hop | Phần đầu danh sách có thể do client tự đặt; không được lấy phần tử đầu tiên một cách mù quáng |
| `X-Forwarded-Prefix` | Tiền tố path được gateway công khai rồi bỏ đi trước khi proxy | Sai prefix có thể làm sai link, redirect hoặc URL callback |

Ví dụ *chỉ để hiểu định dạng*, không phải bằng chứng tin cậy:

```http
Forwarded: for=192.0.2.60;proto=https;host=app.example.test
X-Forwarded-Proto: https
X-Forwarded-Host: app.example.test
X-Forwarded-Port: 443
X-Forwarded-For: 192.0.2.60
```

`192.0.2.60` thuộc dải IP dành cho tài liệu. Trên thực tế, proxy có thể thêm hoặc ghi đè các header này; nhiều proxy nối tiếp có thể làm xuất hiện danh sách nhiều địa chỉ. Không nên tự viết quy tắc kiểu "lấy IP trái nhất trong X-Forwarded-For" rồi dùng làm danh tính, quyền quản trị hoặc điều kiện bảo mật. Địa chỉ IP gốc là thông tin mạng có độ tin cậy phụ thuộc vào **proxy nào đã quan sát và ghi nhận nó**.

**Phân biệt hai nhóm thông tin:** `X-Forwarded-Proto`/`Host`/`Port` mô tả URL, giao thức mà client *được cho là* đã sử dụng; `X-Forwarded-For` mô tả chuỗi nguồn mạng. Chúng không xác thực người dùng, không thay thế `Authentication`/`SecurityContext` và không phải quyền truy cập tài nguyên.

## 4. Ranh giới tin cậy nằm tại đâu?

Giả sử backend tin `X-Forwarded-Proto: https` và `X-Forwarded-Host: app.example.test`. Nếu client có thể gửi trực tiếp tới backend hoặc gửi header đó qua một proxy chuyển nguyên giá trị từ client, một người bất kỳ có thể **tự tuyên bố** request của họ đã dùng HTTPS và mang host mong muốn.

Mô hình tin cậy đúng:

```text
VÙNG KHÔNG TIN CẬY                    VÙNG ĐƯỢC KIỂM SOÁT
Client HTTP request
  | (có thể giả mọi X-Forwarded-*)
  v
[Ingress/Proxy công khai]
  1. Kiểm tra HTTP/TLS thực tế tại cổng vào
  2. Chặn hoặc loại bỏ metadata do client tự gửi
  3. Sinh metadata chuẩn từ thông tin proxy quan sát
  4. Chỉ chuyển sang backend được phép truy cập
  |
  v
[Backend Servlet] -> xử lý forwarded headers đã được chuẩn hóa
                   -> Spring Security dùng request metadata phù hợp
```

Một *trusted proxy* không chỉ là một địa chỉ IP trong sơ đồ. Để backend thực sự tin được thông tin đó, phải đồng thời có các điều kiện sau:

1. **Không tồn tại đường đi tắt:** Backend chỉ nhận traffic từ các proxy tin cậy (loopback, network policy, firewall hoặc private network có kiểm soát); không mở cổng 8080 trực tiếp ra Internet.
2. **Proxy không chuyển nguyên khai báo của client:** Ở biên tin cậy, proxy phải loại bỏ/ghi đè `Forwarded` và các `X-Forwarded-*` có liên quan, rồi tạo metadata từ kết nối mà nó biết. Nếu có CDN/load balancer phía trước, mỗi hop cần có hợp đồng và quy tắc xác minh riêng.
3. **Host công khai được giới hạn:** Gateway chỉ phục vụ các domain/host hợp lệ; không tùy ý dùng `Host` hoặc `X-Forwarded-Host` làm nơi tạo callback, link khôi phục mật khẩu hay chuyển hướng.
4. **Không có các header cạnh tranh mâu thuẫn:** Nếu cả `Forwarded` chuẩn và họ `X-Forwarded-*` cùng xuất hiện, cần quy tắc rõ bên nào là nguồn chuẩn; tốt nhất proxy chỉ truyền bộ metadata được chuẩn hóa, nhất quán.
5. **Kênh proxy → backend phù hợp mức rủi ro:** Mạng nội bộ HTTP chỉ chấp nhận khi ranh giới mạng thật sự được kiểm soát; với chặng xuyên máy/cluster không đáng tin, nên mã hóa và xác thực kênh.
6. **Log đủ hai góc nhìn:** Có thể đối chiếu URL/scheme/host mà ứng dụng hiểu với thông tin ingress quan sát, nhưng không ghi nguyên token, mật khẩu hoặc cookie nhạy cảm vào log.

Nếu thiếu một điều kiện, bật tính năng "trust forwarded headers" ở framework có thể khiến request metadata bị giả mạo. **Lựa chọn này là một quyết định về kiến trúc tin cậy**, không phải mẹo sửa lỗi redirect.

## 5. Servlet và Spring Security dùng thông tin đó như thế nào?

Trên Servlet, những API thường ảnh hưởng đến cách ứng dụng xử lý URL và bảo mật gồm:

```java
request.getScheme();       // "http" hoặc "https" theo request hiện hành
request.isSecure();        // Có được xem là kết nối an toàn?
request.getServerName();   // Tên host mà ứng dụng nhìn thấy
request.getServerPort();   // Cổng mà ứng dụng nhìn thấy
request.getRequestURL();   // URL dạng tuyệt đối do Servlet request cung cấp
```

Khi chưa xử lý header chuyển tiếp, các giá trị có thể phản ánh **kết nối nội bộ**. Khi có bộ xử lý forwarded headers và proxy đáng tin, request có thể được bọc/chuẩn hóa để các API phản ánh **URL công khai**.

Với Spring Security, điều này tác động trực tiếp đến:

- **HTTPS enforcement:** Cấu hình `requiresChannel(...requiresSecure())` xét request đang được xem là secure hay không. Nếu backend chỉ thấy HTTP nội bộ dù client đã dùng HTTPS, ứng dụng có thể redirect lặp lại.
- **Redirect sau login, logout hoặc lỗi xác thực:** Khi framework tạo URL tuyệt đối hoặc URL dựa trên host/scheme, metadata sai có thể đưa người dùng tới cổng 8080, hostname nội bộ hoặc host không mong muốn.
- **OAuth2/OIDC callback trong ứng dụng dùng tính năng đó:** `redirect_uri` sai scheme/host/port có thể không khớp giá trị đã đăng ký với identity provider. Đây là ví dụ về hệ quả của URL công khai sai; bài này không đi sâu vào giao thức OAuth2/OIDC.
- **HTTP Strict Transport Security (HSTS):** Header HSTS mặc định của Spring Security chỉ được thêm trên request được nhìn nhận là HTTPS. Nếu app nghĩ request là HTTP sau TLS termination, nó có thể không gửi HSTS như mong đợi; proxy cũng có thể quản lý HSTS tại biên.
- **Cookie của phiên đăng nhập:** Thuộc tính `Secure` của session cookie phải phù hợp với HTTPS công khai. Một số chính sách cookie phụ thuộc request/Servlet container, vì vậy nên xác định cấu hình production rõ ràng rồi kiểm tra `Set-Cookie` thực tế.
- **Chẩn đoán và audit:** Scheme/host/IP được ghi nhận có thể sai hoặc bị giả nếu trust boundary yếu. Không dùng header forwarded làm principal đã xác thực.

**Phân biệt việc bật HTTPS với nhận diện HTTPS:** `requiresSecure()` có thể yêu cầu kênh an toàn, nhưng không tự cấu hình certificate, listener TLS, firewall hay cách proxy xử lý header. Quyết định TLS ở ingress và cách ứng dụng diễn giải forwarded headers phải khớp nhau.

### Các lỗi quan sát được

| Hiện tượng | Nguyên nhân có thể | Kiểm tra trọng tâm |
| --- | --- | --- |
| Trình duyệt lặp 302/301 giữa các URL | Edge HTTPS nhưng backend luôn thấy `http`; tầng app lại ép HTTPS | `getScheme()`, `isSecure()`, `X-Forwarded-Proto`, thứ tự xử lý filter, chỗ phát redirect |
| Redirect về `http://localhost:8080` hoặc host nội bộ | App tạo URL từ địa chỉ upstream nội bộ | Host, proto, port, URL công khai của proxy |
| Callback login bị từ chối | `redirect_uri` khác scheme/host/port/prefix đã đăng ký | URL callback được tạo thật, path rewrite và trusted forwarded headers |
| Cookie session thiếu `Secure` | Cookie policy hoặc request secure detection sai | `Set-Cookie` trên HTTPS response và cấu hình session cookie |
| HSTS không xuất hiện | Spring Security chỉ nhìn thấy HTTP; header bị cấu hình khác ghi đè | Response HTTPS ở edge, chính sách HSTS của ứng dụng/proxy |
| IP trong audit/rate limit không đúng | Dùng `remoteAddr` của proxy hoặc tin danh sách IP do client khai | Chuỗi trusted hops và cấu hình xác định client IP tại ingress |
| Link/redirect trỏ sang host lạ | Host hoặc forwarded host chưa được hạn chế | Host allowlist và việc xóa/ghi đè header ở proxy |

## 6. Cấu hình Spring Boot Servlet khi có trusted reverse proxy

Spring Boot cung cấp thuộc tính `server.forward-headers-strategy`:

| Giá trị | Ý nghĩa | Khi nào cân nhắc |
| --- | --- | --- |
| `none` | Không chủ động xử lý forwarded headers qua chiến lược này | Ứng dụng không đứng sau proxy, hoặc không có nguồn forwarded đáng tin |
| `native` | Giao cho hỗ trợ gốc của Servlet container, chẳng hạn cơ chế của Tomcat | Hạ tầng có hợp đồng rõ về remote IP và trusted proxies, muốn dùng cơ chế container |
| `framework` | Dùng cơ chế framework (trên Servlet thường là `ForwardedHeaderFilter`) để nhận diện metadata forwarded | Spring MVC đứng sau proxy được kiểm soát, cần request URL phản ánh frontend |

Trên một ứng dụng Spring Boot 3.x/Java 17+, cấu hình production mẫu:

```yaml
# src/main/resources/application-prod.yml
server:
  forward-headers-strategy: framework
  servlet:
    session:
      cookie:
        secure: true
```

`server.servlet.session.cookie.secure: true` có ý nghĩa với ứng dụng sử dụng HTTP session; nó bảo đảm cookie session được gắn cờ `Secure` trong deployment này. `HttpOnly`, `SameSite`, domain/path và timeout cần chính sách phù hợp với ứng dụng thực tế. Không coi `SameSite` là sự thay thế đầy đủ cho CSRF protection.

Với `framework`, Spring Boot có thể tự đăng ký `ForwardedHeaderFilter` trên Servlet. Không tự đăng ký thêm một filter trùng chức năng nếu Boot đã xử lý; không bật cả một tầng rewrite tại container và một tầng rewrite khác nếu không hiểu thứ tự của chúng. Với `native`, cách chọn và kiểm tra địa chỉ proxy tin cậy phụ thuộc container và cấu hình vận hành; không mặc định nó tương đương `framework` trong mọi chi tiết.

**Cảnh báo quan trọng:** Cấu hình `framework` hoặc `native` chỉ là cách *diễn giải* header. Nó không thể xác minh độc lập rằng các header đã được viết bởi trusted proxy. Điều kiện chặn truy cập trực tiếp backend và chuẩn hóa header tại ingress vẫn là bắt buộc.

### Ví dụ ranh giới proxy: một ingress Nginx duy nhất

Đoạn sau là **fragment** cho một `location /` bên trong virtual host HTTPS hợp lệ của Nginx, không phải toàn bộ cấu hình TLS. Giả sử Nginx là ingress công khai duy nhất; chỉ Nginx truy cập được backend trên `127.0.0.1:8080`, và domain public cố định là `app.example.test`.

```nginx
location / {
    proxy_set_header Host app.example.test;

    # Bỏ metadata do client tự khai, chỉ tạo bộ X-Forwarded-* đã kiểm soát.
    proxy_set_header Forwarded "";
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-Host app.example.test;
    proxy_set_header X-Forwarded-Port 443;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Prefix "";

    proxy_pass http://127.0.0.1:8080;
}
```

Ở cấu hình này `$remote_addr` là địa chỉ peer mà **Nginx trực tiếp** quan sát, không tự suy ra được người dùng cuối khi còn có CDN/load balancer khác phía trước. Nếu hạ tầng có nhiều hop, phải cấu hình lại chính sách trusted upstream và client IP tại biên; không sao chép đoạn cấu hình một hop rồi khẳng định đã lấy đúng IP người dùng.

Virtual host HTTPS phải có certificate và chính sách TLS thực tế; virtual host HTTP công khai phải chuyển người dùng sang HTTPS ở ingress theo thiết kế. Dùng host cố định trong ví dụ để tránh lấy giá trị `Host` chưa được validate làm host đáng tin. `.test` là tên miền ví dụ, muốn kiểm thử thật cần hostname, DNS và certificate tương ứng trong môi trường của mình.

## 7. Một ví dụ Spring Boot 3.x / Java 17+ để quan sát và ép HTTPS

Dưới đây là ứng dụng Servlet nhỏ giúp kiểm tra backend đang **hiểu** scheme/host/port như thế nào. Dự án cần hai dependency Spring Boot cơ bản:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

Trong dự án Spring Boot 3.x đã cấu hình plugin/dependency management, tạo tệp `src/main/java/example/proxy/ProxyTlsDemoApplication.java`:

```java
package example.proxy;

import jakarta.servlet.http.HttpServletRequest;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ProxyTlsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProxyTlsDemoApplication.class, args);
    }

    @GetMapping("/transport")
    public Map<String, Object> transport(HttpServletRequest request) {
        return Map.of(
            "scheme", request.getScheme(),
            "secure", request.isSecure(),
            "host", request.getServerName(),
            "port", request.getServerPort()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/transport").permitAll()
                .anyRequest().denyAll()
            )
            .requiresChannel(channel -> channel
                .anyRequest().requiresSecure()
            )
            .build();
    }
}
```

Vì `/transport` chỉ cho phép HTTP GET và dùng `permitAll()`, endpoint này giúp quan sát metadata mà không cần đăng nhập. `requiresSecure()` vẫn yêu cầu request được nhận diện là HTTPS **trước khi** request vào controller. `anyRequest().denyAll()` chỉ là chính sách đơn giản để demo không mở thêm endpoint; ứng dụng thực tế cần tự thiết kế route và quyền.

Nếu chạy local **chỉ bằng HTTP**, request `GET /transport` có thể trả về chuyển hướng HTTPS, rồi không hoàn thành ở local nếu chưa có TLS listener/proxy. Đây là hành vi phù hợp với `requiresSecure()`, không phải lỗi Java. Trong môi trường dùng ingress HTTPS tin cậy, đặt `server.forward-headers-strategy: framework`, chạy ứng dụng phía sau proxy và gọi:

```bash
curl -i https://app.example.test/transport
```

Khi ingress được thiết lập đúng, response dự kiến là HTTP **200** với các cặp giá trị tương đương (thứ tự key JSON không được đảm bảo):

```json
{
  "scheme": "https",
  "secure": true,
  "host": "app.example.test",
  "port": 443
}
```

Đây là **kết quả kỳ vọng về mặt hành vi**, không phải stdout đã chạy thực tế trên một server trong bài. Nếu thấy `http`, `false`, `localhost` hoặc `8080` từ request public HTTPS, cần kiểm tra chuỗi proxy/config và filter trước khi chỉnh logic controller. Nếu endpoint trả redirect, xem `Location` và nguồn sinh redirect (edge hay Spring Security).

### Vì sao không thể chỉ kiểm tra `isSecure()`?

Sau khi bật nhận diện forwarded headers, `request.isSecure()` có thể phản ánh **khai báo đã được proxy chuyển tiếp** chứ không phải trạng thái TLS giữa backend và proxy. Giá trị `true` ở controller chỉ có ý nghĩa bảo mật nếu policy ingress và network boundary đã được kiểm chứng. Cũng vì vậy, đừng triển khai cơ chế kiểm tra TLS công khai bằng cách tự đọc chuỗi `X-Forwarded-Proto` trong controller rồi coi nó là đáng tin.

## 8. `ForwardedHeaderFilter`, Servlet filter chain và Spring Security

Trên Servlet stack, thứ tự tổng quát được quan tâm là:

```text
Proxy gửi request + forwarded metadata chuẩn hóa
             |
Servlet container
             |
Bộ xử lý forwarded headers (framework hoặc container)
             |
DelegatingFilterProxy -> FilterChainProxy
                          -> SecurityFilterChain
                             (HTTPS redirect, authn, authz, headers, ...)
             |
DispatcherServlet -> Controller
```

Đây là **sơ đồ chức năng**, không phải thứ tự chính xác của từng filter cho mọi ứng dụng/phiên bản. Khi chọn `framework`, thành phần nhận diện forwarded headers cần hoạt động đủ sớm để các filter liên quan đến redirect hoặc secure request nhìn thấy thông tin đã chuẩn hóa.

`ForwardedHeaderFilter` của Spring Framework dùng `Forwarded` và các header `X-Forwarded-*` tương ứng để bọc request/response và điều chỉnh cách tính URL/redirect. Nó có chế độ chỉ **gỡ header** (`removeOnly`) khi không muốn sử dụng thông tin forwarded; việc dùng chế độ đó cũng cần cấu hình nhất quán với Spring Boot. Không phải cứ có header là Spring Security tự bật chiến lược xử lý.

**Hai lớp bảo mật khác nhau:**

- **Ingress/proxy:** xác minh giao thức thật, quản lý certificate, kiểm soát host, chuẩn hóa metadata và giới hạn đường vào backend.
- **Spring Security Servlet:** dựa trên request đã được chuẩn hóa để thực hiện chính sách channel, xác thực, phân quyền, CSRF protection và response headers.

CORS không quyết định request có HTTPS hay không; CSRF không chứng minh forwarded headers đáng tin. `X-Forwarded-User` hoặc header do gateway tự đặt cũng **không** mặc nhiên là người dùng đã được xác thực: nếu dùng identity headers phải có thiết kế xác thực gateway và kênh tin cậy riêng.

## 9. Kiểm thử một deployment trước khi đưa vào production

Một bộ kiểm tra có giá trị nên đi từ **biên mạng** vào **ứng dụng**, không chỉ chạy unit test cho controller.

| Trường hợp | Kết quả cần chứng minh | Dấu hiệu sai |
| --- | --- | --- |
| Gọi URL công khai bằng HTTP | Ingress chuyển sang HTTPS theo chính sách; không phục vụ nội dung nhạy cảm qua HTTP | Backend vẫn nhận HTTP public và cho chạy nghiệp vụ nhạy cảm |
| Gọi URL công khai qua HTTPS | TLS certificate hợp lệ; ứng dụng nhìn thấy `scheme=https`, `isSecure=true`, host và port public đúng | Backend nhìn thấy URL nội bộ hoặc bị redirect loop |
| Gọi thẳng cổng backend từ ngoài ingress | Kết nối bị chặn bởi network policy/firewall | Client có thể trực tiếp gửi forwarded headers giả |
| Gửi thử forwarded headers giả tới ingress | Proxy loại bỏ/ghi đè; ứng dụng vẫn nhận metadata chuẩn theo host và TLS được quan sát thật | Host hoặc proto trong URL trả về bị thay bởi giá trị client tự gửi |
| Truy cập host không nằm trong allowlist | Ingress từ chối request hoặc xử lý theo host policy đã định | Redirect tới host tự khai hoặc sinh absolute URL tới domain lạ |
| Đăng nhập bằng cookie/session qua HTTPS | `Set-Cookie` có `Secure` và các thuộc tính cookie đúng policy | Session cookie không có `Secure` hoặc redirect tới HTTP |
| Xem HTTPS response trên route chạy qua Spring Security | HSTS xuất hiện nếu policy yêu cầu và được quản lý ở app hoặc ingress | Không có HSTS do app hiểu nhầm HTTP hoặc cấu hình header mâu thuẫn |
| Dùng ứng dụng sau CDN và nhiều proxy | IP dùng để vận hành được suy ra từ các trusted hops đúng | Tin IP do client đưa trong `X-Forwarded-For`, áp sai giới hạn truy cập |

Có thể thực hiện kiểm tra thủ công ở môi trường thử nghiệm sau khi DNS/TLS đã tồn tại:

```bash
# Quan sát redirect do ingress thực hiện với request HTTP.
curl -I http://app.example.test/transport

# Quan sát URL public, status, HSTS và dữ liệu controller nhìn thấy.
curl -i https://app.example.test/transport

# Thử xem ingress có giữ nguyên metadata giả từ client không.
curl -i -H 'Forwarded: proto=http;host=untrusted.example' \
  -H 'X-Forwarded-Proto: http' \
  -H 'X-Forwarded-Host: untrusted.example' \
  https://app.example.test/transport
```

Với proxy cấu hình đúng, request thứ ba **không được làm thay đổi** host/scheme ứng dụng tin dùng; `untrusted.example` là tên miền ví dụ. Với HTTP public, trạng thái 301/302/307/308 cụ thể phụ thuộc ingress, nên phải xem `Location` và chính sách thực tế thay vì bắt buộc một status duy nhất.

Kiểm thử tự động cần bổ sung ít nhất: request HTTPS hợp lệ; request HTTP bị chuyển hướng; request mang host/proto giả; và đường bypass backend bị chặn ở tầng hạ tầng. Test `MockMvc` có thể chứng minh cách security policy xử lý `secure=true/false`, nhưng **không thay thế** được kiểm thử ingress, firewall, certificate và chuỗi proxy thật.

## 10. Những nhầm lẫn nguy hiểm

### "Có `X-Forwarded-Proto: https` tức là người dùng đã dùng HTTPS"

**Sai.** Bất kỳ client HTTP nào cũng có thể tự tạo header. Chỉ khi trusted ingress quan sát TLS, loại bỏ header nguồn không đáng tin và tái tạo metadata thì backend mới có căn cứ sử dụng thông tin này.

### "Bật `server.forward-headers-strategy: framework` là đủ"

**Chưa đủ.** Framework không tự chặn cổng backend, không thiết lập certificate và không chứng minh host được phép. Kiểm soát đường đi mạng và cơ chế ghi đè header là phần quan trọng nhất của trust boundary.

### "Spring Security `requiresSecure()` khiến toàn bộ đường đi mã hóa"

**Sai.** Nó có thể yêu cầu/redirect HTTPS theo góc nhìn request. Proxy phải xử lý TLS thực sự ở phía công khai; đoạn proxy-backend cần được bảo vệ bằng cách phù hợp hạ tầng.

### "IP đầu tiên trong `X-Forwarded-For` luôn là IP khách"

**Sai.** Chuỗi IP chịu ảnh hưởng cách các proxy nối/ghi đè, và client có thể tạo tiền tố giả. Nếu cần dùng IP cho rate limit hoặc audit, xác định client IP tại một thành phần đã biết trusted hops; không dùng IP làm danh tính thay cho authentication.

### "HSTS, HTTPS và cookie Secure là cùng một thứ"

**Sai.** HTTPS mã hóa kết nối; HSTS yêu cầu browser tiếp tục dùng HTTPS trong phạm vi chính sách; thuộc tính cookie `Secure` giới hạn khi browser gửi cookie. Chúng hỗ trợ nhau nhưng phải được cấu hình và quan sát riêng. HSTS chỉ có ý nghĩa khi browser nhận nó qua HTTPS hợp lệ; nên triển khai chính sách `includeSubDomains`/`preload` thận trọng khi toàn bộ domain liên quan đã sẵn sàng.

### "Dùng `Host` hoặc `X-Forwarded-Host` để sinh link tuyệt đối là luôn an toàn"

**Sai.** Nếu không giới hạn host, kẻ tấn công có thể làm ứng dụng dựng link hoặc redirect sang domain của họ. Những URL nhạy cảm như link khôi phục mật khẩu nên dựa vào cấu hình public origin tin cậy hoặc chính sách xác thực host rõ ràng.

## 11. Bài tập suy luận

1. Client gọi `https://shop.example.test/cart` qua TLS ở load balancer, nhưng backend nhận HTTP cổng 8080. Spring Security có `requiresSecure()` và trang liên tục redirect. Bạn sẽ kiểm tra giá trị Servlet nào, cấu hình nào của Boot và header nào từ LB? Vì sao không nên tắt `requiresSecure()` ngay?
2. Ingress chuyển tiếp nguyên `X-Forwarded-Host` client gửi. Ứng dụng xây redirect sau login dựa trên hostname đó. Hãy mô tả đầu vào bị giả, giá trị bị ảnh hưởng và nơi cần sửa.
3. Backend được mở công khai ở cổng 8080, bật xử lý forwarded headers, rồi một client HTTP tự gửi `X-Forwarded-Proto: https`. `request.isSecure()` có thể báo gì và vì sao kết quả này không chứng minh request đã được mã hóa?
4. Có hai reverse proxy nối tiếp. Tại sao dùng phần tử IP trái nhất của `X-Forwarded-For` để quyết định "địa chỉ mạng nội bộ được miễn xác thực" là nguy hiểm? Thiết kế nào tốt hơn?
5. Một ứng dụng login bằng cookie sau ingress HTTPS nhưng session cookie thiếu `Secure`. Hãy đề xuất cách xác định lỗi thuộc cookie policy hay scheme detection, rồi nêu test bắt buộc sau khi sửa.

**Ghi nhớ:** HTTPS phải được thực thi ở đường vào thật; forwarded headers chỉ là metadata do proxy truyền lại. Spring Security Servlet chỉ có thể đưa ra quyết định channel/redirect/cookie/header đúng khi backend nhìn thấy URL công khai **và** thông tin đó được tạo bởi một ranh giới proxy thực sự đáng tin.
