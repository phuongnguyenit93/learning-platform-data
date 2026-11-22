# Chiến lược xử lý forwarded headers của Spring Boot

Một ứng dụng Spring Boot thường chạy phía sau reverse proxy, ingress controller hoặc load balancer. Trình duyệt truy cập ứng dụng bằng HTTPS trên domain công khai, trong khi proxy chuyển request tới Spring Boot bằng HTTP trên mạng nội bộ. Nếu ứng dụng chỉ nhìn kết nối nội bộ, nó có thể nghĩ request dùng HTTP, host là tên container và port là 8080. Kết quả là redirect, link tuyệt đối, callback OAuth2 hoặc URL được tạo từ request có thể sai.

Reverse proxy có thể gửi **forwarded headers** để cho ứng dụng biết thông tin mà client đã dùng ở phía ngoài. Spring Boot cung cấp thuộc tính **server.forward-headers-strategy** để chọn cách xử lý các header đó: **NONE**, **NATIVE** hoặc **FRAMEWORK**.

Chọn đúng chiến lược giúp Spring hiểu scheme, host, port và external prefix của request. Tuy nhiên, forwarded headers chỉ đáng tin khi chúng đến từ proxy được kiểm soát. Nếu ứng dụng nhận trực tiếp header do client tự đặt, kẻ gọi có thể giả mạo host hoặc scheme và ảnh hưởng tới URL, redirect và một số quyết định bảo mật.

## 1. Vì sao cần forwarded headers?

Giả sử luồng triển khai như sau:

~~~text
Browser
  https://api.example.com/gateway/api/orders
          |
          v
Reverse proxy / ingress
  TLS termination
  rewrite /gateway
          |
          v
Spring Boot
  http://orders-service:8080/api/orders
~~~

Spring Boot nhìn thấy kết nối từ proxy tới orders-service:8080. Nếu không nhận được thông tin chuyển tiếp, request có thể được nhận diện như:

| Thuộc tính Spring nhìn thấy | Giá trị nội bộ |
|---|---|
| Scheme | http |
| Host | orders-service |
| Port | 8080 |
| Context/prefix bên ngoài | Không có /gateway |
| Secure request | false |

Nhưng người dùng thực sự truy cập:

~~~text
https://api.example.com/gateway/api/orders
~~~

Khác biệt này có thể làm hỏng:

- Redirect tới trang đăng nhập hoặc callback OAuth2.
- URL tuyệt đối được tạo bằng ServletUriComponentsBuilder.
- Header Location trong response.
- Link trong email hoặc nội dung HATEOAS được tạo từ request hiện tại.
- Cookie có thuộc tính Secure hoặc logic phụ thuộc request.isSecure().
- URL server được sinh động cho tài liệu OpenAPI nếu ứng dụng dựa vào request hiện tại.
- Log và audit cần phân biệt địa chỉ client với địa chỉ proxy.

Forwarded headers truyền lại thông tin của request công khai để framework hoặc web server điều chỉnh request mà ứng dụng nhìn thấy.

## 2. Các loại forwarded headers

Có hai nhóm header thường gặp.

### Header chuẩn Forwarded

RFC 7239 định nghĩa header Forwarded. Ví dụ:

~~~http
Forwarded: for=198.51.100.24;proto=https;host=api.example.com
~~~

Các tham số thường gặp:

| Tham số | Ý nghĩa |
|---|---|
| for | Địa chỉ client hoặc node đứng trước proxy |
| by | Node proxy nhận request |
| proto | Scheme bên ngoài, ví dụ https |
| host | Host mà client dùng, có thể kèm port |

Nếu request đi qua nhiều proxy, header có thể chứa nhiều phần tử được nối bằng dấu phẩy. Không nên tự tách chuỗi bằng một quy tắc đơn giản rồi coi phần tử đầu hoặc cuối luôn là client đáng tin.

### Nhóm X-Forwarded-*

Các header X-Forwarded-* được dùng rộng rãi trong reverse proxy:

| Header | Ý nghĩa |
|---|---|
| X-Forwarded-For | Địa chỉ client và/hoặc chuỗi proxy |
| X-Forwarded-Proto | Scheme bên ngoài như https |
| X-Forwarded-Host | Host bên ngoài |
| X-Forwarded-Port | Port bên ngoài |
| X-Forwarded-Prefix | Prefix công khai đã được proxy thêm hoặc loại khỏi path nội bộ |

Ví dụ:

~~~http
X-Forwarded-For: 198.51.100.24
X-Forwarded-Host: api.example.com
X-Forwarded-Proto: https
X-Forwarded-Port: 443
X-Forwarded-Prefix: /gateway
~~~

X-Forwarded-Prefix đặc biệt hữu ích khi proxy nhận URL có prefix /gateway, sau đó loại prefix này trước khi chuyển request tới ứng dụng. Framework cần biết prefix công khai để tạo lại URL mà client có thể truy cập.

Không nên gửi hai bộ header mâu thuẫn. Hãy thống nhất proxy sẽ tạo Forwarded, nhóm X-Forwarded-*, hay một bộ header chuẩn mà container/framework đang được cấu hình để đọc.

## 3. Ba chiến lược của Spring Boot

Thuộc tính cấu hình:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Spring Boot có ba lựa chọn:

| Giá trị | Cách xử lý | Khi phù hợp |
|---|---|---|
| NONE | Không yêu cầu Spring Boot xử lý forwarded headers | Ứng dụng truy cập trực tiếp hoặc proxy không gửi header đáng tin |
| NATIVE | Dùng khả năng xử lý forwarded header của web server/container | Container có hỗ trợ phù hợp và đã được cấu hình đúng |
| FRAMEWORK | Dùng cơ chế của Spring Framework để điều chỉnh request | Muốn xử lý forwarded headers nhất quán ở tầng framework |

### NONE

~~~yaml
server:
  forward-headers-strategy: none
~~~

Với NONE, ứng dụng không dùng forwarded headers theo chiến lược tự động của Spring Boot. Spring nhìn thấy thông tin của kết nối tới chính nó, thường là kết nối từ reverse proxy.

Đây là lựa chọn phù hợp khi không có proxy đáng tin phía trước hoặc khi hệ thống không muốn ứng dụng diễn giải các header do client gửi. Nếu triển khai sau proxy nhưng vẫn để NONE, URL tạo ra từ request có thể dùng host, port và scheme nội bộ.

### NATIVE

~~~yaml
server:
  forward-headers-strategy: native
~~~

Với NATIVE, Spring Boot yêu cầu web server/container sử dụng khả năng xử lý forwarded header riêng. Ví dụ, Tomcat có thể dùng RemoteIpValve để diễn giải các header chuyển tiếp và cập nhật thông tin request.

Ưu điểm là xử lý ở tầng container. Tuy nhiên, header được hỗ trợ, cách xác định proxy tin cậy và khả năng xử lý prefix phụ thuộc container cùng cấu hình của nó. Không giả định mọi container đều diễn giải mọi header giống nhau.

Nếu chọn NATIVE, hãy kiểm tra tài liệu của container đang chạy, cấu hình danh sách proxy tin cậy và xác minh request mà ứng dụng nhận được. Với Tomcat, có thể cần tinh chỉnh các thuộc tính server.tomcat.remoteip.* tùy topology và header proxy gửi.

### FRAMEWORK

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Với FRAMEWORK, Spring Boot sử dụng hỗ trợ forwarded header của Spring Framework. Trong ứng dụng Servlet, cơ chế này dùng ForwardedHeaderFilter; trong ứng dụng reactive, Spring dùng ForwardedHeaderTransformer.

Cơ chế framework điều chỉnh các thuộc tính request như scheme, host, port, secure state và thông tin prefix theo forwarded headers được hỗ trợ. Các API Spring xây dựng URL từ request đã được điều chỉnh có thể tạo URL công khai thay vì URL nội bộ.

Đây là lựa chọn thường dùng khi muốn Spring Framework xử lý forwarded headers độc lập với khả năng riêng của container. Vẫn phải bảo đảm proxy đã ghi đè header đầu vào và ứng dụng chỉ nhận traffic từ proxy đáng tin.

## 4. Chọn chiến lược nào?

Có thể chọn theo các câu hỏi:

1. Ứng dụng có chạy sau reverse proxy hoặc ingress không?
2. Proxy có gửi scheme, host, port và prefix công khai không?
3. Proxy có xóa hoặc ghi đè các forwarded headers do client tự gửi không?
4. Container đang dùng có hỗ trợ native forwarding phù hợp không?
5. Ứng dụng dùng Servlet MVC hay WebFlux?

Gợi ý lựa chọn:

| Môi trường | Hướng lựa chọn |
|---|---|
| Chạy trực tiếp, không có proxy | NONE |
| Sau proxy, muốn Spring Framework xử lý header | FRAMEWORK |
| Sau proxy, container có cơ chế native đã cấu hình và kiểm thử | NATIVE |
| Sau nhiều lớp proxy | Chọn một cơ chế, chuẩn hóa header tại biên tin cậy và kiểm tra chuỗi proxy |

Không bật đồng thời nhiều cơ chế để chắc chắn nhận được header. Nếu container đã sửa request rồi framework tiếp tục diễn giải cùng header, thông tin host, scheme hoặc prefix có thể bị áp dụng hai lần. Chọn một chiến lược làm nguồn xử lý chính.

Nếu thuộc tính không được khai báo, hành vi mặc định thường tương ứng với việc không xử lý forwarded headers; môi trường triển khai hoặc cấu hình container có thể bổ sung hành vi riêng. Hãy kiểm tra cấu hình thực tế thay vì suy ra chỉ từ một file YAML.

## 5. Cấu hình cơ bản trong application.yml

Với ứng dụng Spring MVC sau reverse proxy:

~~~yaml
server:
  port: 8080
  forward-headers-strategy: framework
~~~

Tương đương trong application.properties:

~~~properties
server.port=8080
server.forward-headers-strategy=framework
~~~

Với WebFlux, thuộc tính server.forward-headers-strategy vẫn là điểm cấu hình ở Spring Boot; phần xử lý phía framework sử dụng cơ chế reactive tương ứng thay vì Servlet filter.

Không cần tự đăng ký thêm một ForwardedHeaderFilter nếu Spring Boot đã tự cấu hình nó theo FRAMEWORK. Việc thêm filter trùng lặp có thể làm request bị điều chỉnh nhiều lần hoặc khiến thứ tự filter khó kiểm soát.

## 6. Ví dụ reverse proxy Nginx

Nếu Nginx trực tiếp kết thúc TLS từ client rồi proxy request tới Spring Boot, cấu hình có thể gửi thông tin bên ngoài như sau:

~~~nginx
server {
    listen 443 ssl;
    server_name api.example.com;

    location / {
        proxy_pass http://orders-service:8080;

        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Port $server_port;
        proxy_set_header X-Forwarded-For $remote_addr;
    }
}
~~~

Ví dụ này giả định Nginx nhìn thấy kết nối HTTPS công khai và chính Nginx kết thúc TLS. Khi đó $scheme là https và $server_port là port công khai của listener.

Trong ví dụ ở biên Internet, X-Forwarded-For được đặt bằng địa chỉ peer mà Nginx trực tiếp nhìn thấy. Cách này loại bỏ chuỗi X-Forwarded-For có thể do client tự gửi. Nếu có một load balancer đáng tin phía trước, hãy cấu hình riêng trust chain và chỉ giữ địa chỉ do các proxy đã xác thực thêm vào; không sao chép nguyên header từ một client bất kỳ.

Nếu TLS đã được kết thúc ở một load balancer phía trước Nginx, Nginx có thể chỉ nhìn thấy HTTP nội bộ. Khi ấy $scheme có thể là http; không được dùng nó để ghi đè thông tin HTTPS công khai. Hãy cấu hình lớp proxy tin cậy phía trước ghi đè forwarded headers, chỉ cho Nginx nhận traffic từ lớp đó, rồi chuyển tiếp giá trị đã được xác thực theo topology.

Đặc biệt, không dùng mù quáng $http_x_forwarded_proto hoặc $http_x_forwarded_host từ mọi client. Chỉ giữ các giá trị này khi upstream đáng tin đã loại bỏ header giả mạo và tự thiết lập chúng.

## 7. Proxy loại bỏ prefix và X-Forwarded-Prefix

Một số hệ thống public API dưới prefix /gateway, nhưng route Spring Boot bắt đầu từ /api. Proxy có thể loại bỏ prefix trước khi chuyển request:

~~~text
Public URL:  https://api.example.com/gateway/api/orders
Backend URL: http://orders-service:8080/api/orders
~~~

Nếu proxy không truyền prefix công khai, Spring có thể tạo redirect hoặc link thành:

~~~text
http://orders-service:8080/api/orders
~~~

Khi proxy được cấu hình để loại prefix, nó có thể gửi:

~~~http
X-Forwarded-Prefix: /gateway
X-Forwarded-Proto: https
X-Forwarded-Host: api.example.com
X-Forwarded-Port: 443
~~~

Spring Framework có thể dùng prefix này khi xây dựng URL từ request. Cần bảo đảm prefix chỉ được áp dụng một lần:

- Nếu proxy giữ nguyên /gateway trong path chuyển tiếp, đừng cấu hình thêm prefix theo cách làm URL bị lặp.
- Nếu proxy loại /gateway, hãy gửi prefix công khai để ứng dụng dựng lại URL bên ngoài.
- Nếu ứng dụng đã có server.servlet.context-path, phân biệt context path nội bộ với prefix do proxy thêm.

Kết quả đúng phải là URL mà client có thể gọi, không phải đường dẫn nội bộ mà proxy dùng để kết nối backend.

## 8. Forwarded headers ảnh hưởng gì tới URL trong Spring?

Khi request được điều chỉnh đúng, các API đọc thông tin request có thể phản ánh địa chỉ bên ngoài:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@GetMapping("/diagnostics/request")
Map<String, Object> requestInfo(HttpServletRequest request) {
    return Map.of(
        "scheme", request.getScheme(),
        "secure", request.isSecure(),
        "serverName", request.getServerName(),
        "serverPort", request.getServerPort(),
        "contextPath", request.getContextPath(),
        "requestURI", request.getRequestURI()
    );
}
~~~

Endpoint này chỉ nên dùng trong môi trường phát triển hoặc kiểm thử, không công khai thông tin hạ tầng không cần thiết trong production.

Các API xây URL như ServletUriComponentsBuilder.fromCurrentRequest() có thể dùng thông tin đã được forwarded-header mechanism điều chỉnh. Điều này hữu ích khi:

- Tạo Location header sau khi POST tạo tài nguyên.
- Tạo link tuyệt đối trong response.
- Sinh redirect về frontend.
- Tạo callback URI cho OAuth2 Client dùng base URL của request.
- Xây dựng link điều hướng trong nội dung HATEOAS.

Forwarded headers không tự sửa các URL được hard-code trong application.yml, database hoặc biến môi trường. Nếu một server URL được cấu hình tĩnh, cần cập nhật cấu hình đó theo domain public.

## 9. Tác động tới OAuth2/OIDC redirect URI

Spring Security OAuth2 Client thường dùng redirect URI template có {baseUrl}:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          my-client:
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
~~~

Nếu ứng dụng chạy sau proxy HTTPS nhưng Spring chỉ thấy HTTP nội bộ, {baseUrl} có thể được tạo thành http://... . Identity Provider đã đăng ký URI https://... sẽ từ chối với lỗi redirect URI mismatch.

Khi forwarded headers được xử lý đúng, base URL có thể phản ánh scheme và host công khai. Sau khi cấu hình, vẫn cần kiểm tra authorization request thực tế trong browser Network tab:

- redirect_uri có đúng scheme HTTPS không?
- Host và port có đúng domain công khai không?
- Context path hoặc prefix có được giữ không?
- Callback path có đúng registrationId không?

Không sửa lỗi redirect URI mismatch bằng cách nới lỏng danh sách redirect URI thành wildcard. Hãy sửa thông tin proxy và đăng ký URI chính xác.

## 10. Tác động tới springdoc-openapi và Swagger UI

Nếu ứng dụng hoặc customizer tạo URL tài liệu dựa trên request hiện tại, forwarded headers giúp Spring nhận đúng scheme, host và prefix công khai. Điều này có thể ảnh hưởng tới:

- URL tuyệt đối trong response hoặc link tài liệu.
- servers được xây dựng động từ request.
- Swagger UI tải API docs qua reverse proxy prefix.
- URL OAuth2 redirect dành cho Swagger UI nếu được cấu hình dựa trên địa chỉ public.

Tuy nhiên, không phải mọi cấu hình springdoc đều tự suy ra server URL từ forwarded headers. Nếu OpenAPI có servers khai báo tĩnh, giá trị tĩnh vẫn là nguồn quyết định. Hãy kiểm tra JSON cuối tại /v3/api-docs và request mà Swagger UI thực sự gửi.

Ví dụ khi public API nằm dưới prefix /gateway:

~~~yaml
springdoc:
  api-docs:
    path: /v3/api-docs
  swagger-ui:
    path: /swagger-ui.html
~~~

Các property trên xác định endpoint tài liệu bên trong ứng dụng. Proxy vẫn cần ánh xạ public path tới đúng backend path và gửi prefix/scheme/host phù hợp nếu đã rewrite URL. Không tự thêm /gateway vào cả proxy rewrite, context path và OpenAPI server URL nếu chúng đã được ghép ở một tầng khác.

## 11. Ranh giới tin cậy: chỉ nhận forwarded headers từ proxy đáng tin

Forwarded headers có thể bị giả mạo nếu client gửi trực tiếp tới ứng dụng:

~~~http
X-Forwarded-Host: attacker.example
X-Forwarded-Proto: https
~~~

Nếu ứng dụng tin các giá trị đó, nó có thể tạo redirect hoặc link tuyệt đối tới host do kẻ gọi chỉ định. Điều này có thể dẫn tới host-header poisoning, redirect sai domain, callback URI không mong muốn hoặc ghi log sai thông tin.

Các nguyên tắc bắt buộc:

1. Đặt ứng dụng phía sau proxy đáng tin và hạn chế truy cập trực tiếp từ Internet tới port backend.
2. Proxy biên phải xóa hoặc ghi đè forwarded headers mà client gửi vào.
3. Chỉ tin forwarded headers do proxy trong topology kiểm soát tạo ra.
4. Nếu có nhiều proxy, xác định rõ proxy nào được tin và cách xử lý chuỗi địa chỉ.
5. Không dùng X-Forwarded-For làm danh tính đã xác thực; đây chỉ là thông tin mạng có thể bị giả mạo nếu trust chain sai.
6. Kiểm tra Host header hợp lệ ở ingress/proxy và ứng dụng.

Nếu không kiểm soát được nguồn header, chọn NONE hoặc cấu hình cơ chế chỉ loại bỏ header thay vì diễn giải chúng. Spring Framework có chế độ xử lý forwarded header theo hướng remove-only trong một số cấu hình filter; mục đích là loại bỏ header không đáng tin trước khi ứng dụng sử dụng request, không phải tin các giá trị do client cung cấp.

## 12. Cấu hình nhiều lớp proxy

Trong triển khai nhiều lớp, ví dụ CDN → load balancer → ingress → Spring Boot, mỗi lớp có thể bổ sung hoặc nối forwarded headers. Cần xác định rõ:

- Lớp nào kết thúc TLS?
- Lớp nào nhìn thấy IP client thật?
- Lớp nào được phép ghi Forwarded hoặc X-Forwarded-*?
- Header có được ghi đè hay nối thêm?
- Spring/container sẽ tin proxy nào trong chuỗi?

Không thể mặc định phần tử đầu hoặc cuối của X-Forwarded-For luôn là địa chỉ client đáng tin. Nếu dùng Tomcat native support, cấu hình trusted/internal proxies theo tài liệu container. Nếu dùng Spring Framework, đảm bảo proxy biên đã chuẩn hóa header và backend không thể bị gọi trực tiếp từ nguồn không tin.

Tránh để từng lớp tự thêm một X-Forwarded-Prefix hoặc thay đổi X-Forwarded-Proto mà không có quy ước. Một header nhất quán qua toàn bộ tuyến giúp tránh URL sai và khó điều tra.

## 13. Kiểm tra forwarded headers qua proxy

Ưu tiên kiểm tra bằng request đi qua đúng reverse proxy/ingress đang dùng, không chỉ gọi thẳng port backend.

Có thể dùng endpoint chẩn đoán tạm thời ở môi trường phát triển:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ForwardedHeaderProbeController {

    @GetMapping("/_diagnostics/request-url")
    Map<String, Object> inspect(HttpServletRequest request) {
        return Map.of(
            "scheme", request.getScheme(),
            "secure", request.isSecure(),
            "host", request.getServerName(),
            "port", request.getServerPort(),
            "contextPath", request.getContextPath(),
            "requestURI", request.getRequestURI()
        );
    }
}
~~~

Gọi public URL:

~~~bash
curl -i https://api.example.com/gateway/_diagnostics/request-url
~~~

Kết quả cần phản ánh địa chỉ công khai theo thiết kế. Nếu proxy loại prefix /gateway, kiểm tra context path/request URI sau khi Spring áp dụng forwarded prefix.

Sau khi kiểm tra, xóa hoặc bảo vệ endpoint chẩn đoán. Không để endpoint này tiết lộ host nội bộ, port, cấu trúc proxy hoặc dữ liệu request nhạy cảm trong production.

### Kiểm tra request header ở biên proxy

Ở môi trường test, có thể quan sát request backend nhận được hoặc bật log phù hợp tại proxy. Xác nhận:

- Proxy đặt đúng X-Forwarded-Proto.
- Host công khai được truyền đúng.
- Port công khai được giữ nếu cần.
- Prefix được truyền khi proxy rewrite path.
- Client-supplied forwarded headers đã bị loại hoặc ghi đè.

Không bật log toàn bộ Authorization, Cookie hoặc token chỉ để debug forwarded headers.

## 14. Kiểm thử bằng MockMvc

Với ứng dụng Servlet dùng chiến lược FRAMEWORK, integration test có thể gửi forwarded header và xác minh request URL được điều chỉnh. Ví dụ endpoint kiểm thử trả về scheme/host:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ForwardedHeaderTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void usesPublicSchemeAndHostFromForwardedHeader() throws Exception {
        mockMvc.perform(get("/_test/request-url")
                .header(
                    "Forwarded",
                    "proto=https;host=api.example.test"
                ))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.scheme").value("https"))
            .andExpect(jsonPath("$.host").value("api.example.test"));
    }
}
~~~

Test chỉ phản ánh cấu hình filter thực sự được bật trong test ApplicationContext. Nếu test không chạy với server.forward-headers-strategy=framework, việc thêm header đơn thuần không chứng minh filter đang hoạt động.

Nên bổ sung test cho:

- X-Forwarded-Proto và X-Forwarded-Host nếu proxy thực tế dùng nhóm header này.
- X-Forwarded-Prefix nếu có path rewrite.
- Request không có forwarded headers.
- Header giả mạo từ nguồn không đáng tin ở lớp proxy/edge test.
- Redirect URI hoặc Location header được tạo từ request.

Với WebFlux, dùng WebTestClient và kiểm tra request URI sau khi ForwardedHeaderTransformer được áp dụng. Cách test cụ thể phụ thuộc cấu hình reactive server của ứng dụng.

## 15. Dấu hiệu cấu hình sai và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Redirect tạo URL http:// dù client dùng HTTPS | Thiếu X-Forwarded-Proto/Forwarded hoặc strategy chưa bật | Kiểm tra header proxy gửi và request scheme |
| Redirect trỏ tới hostname container | Host bên ngoài không được truyền hoặc không được tin | Kiểm tra Host và X-Forwarded-Host |
| URL có port 8080 thay vì 443 | Port public bị mất hoặc native container không đọc port header | Kiểm tra X-Forwarded-Port và cấu hình container |
| URL thiếu prefix /gateway | Proxy đã strip prefix nhưng không gửi X-Forwarded-Prefix | Kiểm tra rewrite và prefix header |
| URL có prefix lặp hai lần | Prefix được thêm ở nhiều tầng | Kiểm tra proxy rewrite, context path và forwarded prefix |
| Redirect loop giữa HTTP và HTTPS | Proxy gửi proto sai hoặc app/proxy cùng ép redirect | Kiểm tra nơi kết thúc TLS và X-Forwarded-Proto |
| IP client luôn là địa chỉ proxy | Header client IP không được xử lý hoặc trust chain chưa đúng | Kiểm tra X-Forwarded-For và proxy trust config |
| Client có thể đổi host trong link | Proxy không ghi đè forwarded host hoặc backend bị truy cập trực tiếp | Chặn direct access và chuẩn hóa header ở proxy biên |
| Tomcat và Spring cho kết quả khác nhau | Chọn NATIVE/FRAMEWORK không đúng hoặc xử lý hai lần | Chọn một chiến lược và kiểm tra container |
| Swagger UI gọi sai server URL | OpenAPI servers tĩnh hoặc URL public chưa được cấu hình | Kiểm tra /v3/api-docs và proxy mapping |

## 16. Checklist trước khi triển khai

- [ ] Đã xác định lớp nào kết thúc TLS và lớp nào chuyển tiếp request tới Spring Boot.
- [ ] Đã chọn rõ NONE, NATIVE hoặc FRAMEWORK.
- [ ] Không bật đồng thời cơ chế native và framework cho cùng một chuỗi header.
- [ ] Reverse proxy xóa hoặc ghi đè forwarded headers do client gửi.
- [ ] Backend không thể bị truy cập trực tiếp từ nguồn không tin cậy.
- [ ] Forwarded hoặc X-Forwarded-* phản ánh đúng scheme, host và port công khai.
- [ ] X-Forwarded-Prefix chỉ được dùng khi có path prefix được proxy rewrite.
- [ ] Đã kiểm tra context path nội bộ và prefix bên ngoài không bị ghép lặp.
- [ ] Redirect URI OAuth2/OIDC được tạo đúng domain HTTPS công khai.
- [ ] Link tuyệt đối và Location header phản ánh URL công khai.
- [ ] OpenAPI servers được kiểm tra trong JSON cuối, không chỉ dựa vào suy đoán.
- [ ] Trust chain cho client IP và proxy đã được xác định.
- [ ] Có integration test cho scheme, host, prefix và redirect quan trọng.
- [ ] Endpoint chẩn đoán forwarded header đã được gỡ bỏ hoặc bảo vệ sau khi kiểm thử.

## Kết luận

server.forward-headers-strategy chọn cách Spring Boot diễn giải thông tin từ reverse proxy: **NONE** bỏ qua forwarded headers, **NATIVE** dùng hỗ trợ của web server/container, còn **FRAMEWORK** dùng cơ chế của Spring Framework. Hãy chọn một chiến lược phù hợp với Servlet hoặc WebFlux, chuẩn hóa Forwarded/X-Forwarded-* tại proxy đáng tin và kiểm tra scheme, host, port cùng prefix mà ứng dụng nhìn thấy. Forwarded headers ảnh hưởng tới redirect, OAuth2 callback, link tuyệt đối và URL tài liệu được tạo từ request, nhưng không tự sửa URL cấu hình tĩnh. Quan trọng nhất, không tin header do client tự gửi: proxy phải loại hoặc ghi đè chúng, và backend chỉ nên nhận traffic từ các lớp proxy đã được kiểm soát.
