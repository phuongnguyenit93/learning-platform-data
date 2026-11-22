# HTTPS ở bên ngoài với HTTP giữa proxy và ứng dụng

Trong nhiều hệ thống Spring Boot, trình duyệt kết nối bằng HTTPS tới reverse proxy hoặc load balancer, còn proxy chuyển request vào ứng dụng bằng HTTP trong mạng riêng. Đây là mô hình TLS termination (kết thúc TLS tại proxy). Nó giúp tập trung quản lý chứng chỉ và giảm cấu hình TLS ở từng service, nhưng ứng dụng cần biết request ban đầu đến bằng HTTPS và có thể đi qua một path prefix công khai.

Điểm này đặc biệt quan trọng với springdoc-openapi và Swagger UI. Nếu ứng dụng chỉ nhìn thấy kết nối nội bộ HTTP, OpenAPI có thể sinh server URL bắt đầu bằng http://, Swagger UI có thể tải tài liệu sai host hoặc redirect về URL nội bộ. Nếu proxy bỏ prefix công khai mà ứng dụng không được thông báo, các link như /v3/api-docs hoặc /swagger-ui/** có thể bị tạo thiếu prefix.

## 1. Mô hình HTTPS bên ngoài, HTTP bên trong

Luồng phổ biến:

~~~mermaid
flowchart LR
    C[Browser / API client] -->|HTTPS :443| P[Reverse proxy / Load balancer]
    P -->|HTTP :8080 trong mạng riêng| A[Spring Boot application]
    A --> S[Spring Security + springdoc]
    S --> D[OpenAPI JSON / Swagger UI]
    D -->|URL công khai HTTPS| C
~~~

Client kết nối tới https://api.example.com, proxy giải mã TLS rồi chuyển request tới http://spring-app:8080. Ở phía ứng dụng, socket và servlet request có thể chỉ cho thấy:

- Scheme là http.
- Port nội bộ là 8080.
- Host là tên service hoặc địa chỉ container.
- Path có thể đã bị proxy bỏ đi một prefix công khai.

Trong khi đó, client cần nhìn thấy URL công khai:

https://api.example.com/gateway

Ứng dụng cần nhận được thông tin gốc qua forwarded headers và xử lý chúng đúng cách.

### 1.1. Ba cách bố trí TLS thường gặp

| Mô hình | TLS được kết thúc ở đâu? | Kết nối phía sau | Khi phù hợp |
|---|---|---|---|
| TLS termination | Reverse proxy | HTTP tới ứng dụng | Proxy và ứng dụng nằm trong mạng riêng được kiểm soát. |
| TLS re-encryption | Proxy giải mã rồi mã hóa lại | HTTPS tới ứng dụng | Cần mã hóa cả đoạn mạng nội bộ hoặc đi qua mạng không hoàn toàn tin cậy. |
| TLS passthrough | Ứng dụng hoặc ingress cuối | Proxy L4 chuyển tiếp TLS nguyên vẹn | Ứng dụng tự xử lý chứng chỉ và cần giữ TLS tới service. |

Bài này tập trung vào TLS termination: HTTPS từ client tới proxy và HTTP từ proxy tới Spring Boot. Nếu dùng re-encryption, forwarded headers vẫn hữu ích để ứng dụng biết URL bên ngoài; đồng thời cần cấu hình chứng chỉ và trust store cho kết nối HTTPS nội bộ.

Với TLS passthrough ở tầng TCP, proxy không giải mã HTTP nên không thể tự thêm X-Forwarded-Proto hoặc X-Forwarded-Prefix. Ứng dụng tự kết thúc TLS và nhìn thấy HTTPS trực tiếp.

## 2. Forwarded headers cho biết URL ban đầu

Proxy có thể gửi header chuẩn RFC 7239 Forwarded hoặc các header phổ biến X-Forwarded-*.

| Header | Ví dụ | Ý nghĩa |
|---|---|---|
| Forwarded | proto=https;host=api.example.com;for=203.0.113.10 | Header chuẩn mô tả thông tin request qua proxy. |
| X-Forwarded-For | 203.0.113.10 | Địa chỉ client ban đầu hoặc chuỗi proxy đã đi qua. |
| X-Forwarded-Host | api.example.com | Host mà client dùng ở phía ngoài. |
| X-Forwarded-Port | 443 | Port công khai. |
| X-Forwarded-Proto | https | Scheme ban đầu của client. |
| X-Forwarded-Prefix | /gateway | Prefix công khai đã bị proxy loại khỏi path trước khi chuyển tiếp. Đây là header phổ biến nhưng không thuộc RFC 7239. |

Ví dụ request được proxy chuyển tiếp:

~~~http
GET /v3/api-docs HTTP/1.1
Host: spring-app:8080
X-Forwarded-Host: api.example.com
X-Forwarded-Proto: https
X-Forwarded-Port: 443
X-Forwarded-For: 203.0.113.10
X-Forwarded-Prefix: /gateway
~~~

Ứng dụng có thể dùng các header này để xây dựng redirect, link và server URL đúng với request bên ngoài. Nếu không xử lý chúng, ứng dụng có thể tạo link dùng scheme, host, port hoặc path nội bộ.

### 2.1. X-Forwarded-Prefix không tự rewrite request path

Giả sử client gọi URL https://api.example.com/gateway/v3/api-docs.

Proxy có thể bỏ /gateway trước khi gửi request tới ứng dụng. Khi đó ứng dụng nhận /v3/api-docs, còn X-Forwarded-Prefix: /gateway cho biết prefix bên ngoài cần được dùng khi tạo URL.

Hai việc khác nhau:

- proxy_pass hoặc rule rewrite của proxy quyết định path nào được gửi tới ứng dụng.
- X-Forwarded-Prefix thông báo prefix công khai để framework tạo URL bên ngoài.

Chỉ gửi header mà không cấu hình rewrite có thể khiến ứng dụng nhận path không khớp controller. Ngược lại, rewrite đúng nhưng không truyền prefix có thể khiến Swagger UI sinh URL thiếu /gateway.

## 3. Cấu hình Spring Boot xử lý forwarded headers

Spring Boot có hai hướng xử lý chính:

- **Native/web server**: container như Tomcat hoặc Jetty xử lý forwarded headers bằng cơ chế riêng.
- **Framework**: Spring Framework xử lý qua ForwardedHeaderFilter ở Servlet stack hoặc ForwardedHeaderTransformer ở reactive stack.

Chọn cách phù hợp với proxy, container và phiên bản Spring Boot. Không bật nhiều cơ chế xử lý cùng lúc nếu chúng cùng sửa scheme/host/path, vì có thể tạo kết quả sai hoặc áp dụng prefix hai lần.

### 3.1. Spring Boot 3.x

Với Spring Boot 3.x, property thường dùng là server.forward-headers-strategy.

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Các giá trị thường gặp:

| Giá trị | Hành vi |
|---|---|
| NONE | Không xử lý forwarded headers. |
| NATIVE | Dùng hỗ trợ của web server/container. |
| FRAMEWORK | Dùng Spring Framework forwarded-header support. |

Khi cần xử lý X-Forwarded-Prefix để tạo URL có prefix công khai, FRAMEWORK thường là lựa chọn dễ kiểm soát hơn nếu container native không hỗ trợ đầy đủ prefix. Springdoc FAQ cũng hướng dẫn dùng server.forward-headers-strategy=framework khi cần xử lý prefix.

Không đăng ký thêm một ForwardedHeaderFilter thủ công nếu Spring Boot đã tự cấu hình filter từ property này. Nếu tự quản lý filter, cần bảo đảm filter chạy trước các thành phần tạo URL và được map cho dispatcher type phù hợp.

### 3.2. Spring Boot 4.x

Spring Boot 4 chuyển cấu hình forwarded headers sang nhóm property server.request.header.forwarded.*. Ví dụ dùng Spring Framework để xử lý forwarded headers và bật prefix:

~~~yaml
server:
  request:
    header:
      forwarded:
        strategy: framework
        use-prefix: true
~~~

use-prefix mặc định là false; nếu proxy gửi X-Forwarded-Prefix, cần bật rõ để ứng dụng sử dụng prefix. Khi web server/container hỗ trợ đầy đủ header đang dùng, có thể chọn web-server; nếu cần prefix nhưng native support không xử lý được, dùng framework.

Không sao chép nguyên cấu hình Boot 3 sang Boot 4 mà không kiểm tra property theo major version. server.forward-headers-strategy đã được thay thế trong tài liệu cấu hình Boot 4.

### 3.3. Tomcat khi proxy kết thúc SSL

Nếu dùng Tomcat và gặp redirect tại context root trước khi X-Forwarded-Proto được áp dụng, Spring Boot có property riêng:

- Spring Boot 3.x: server.tomcat.redirect-context-root: false.
- Spring Boot 4.x: server.tomcat.servlet.redirect-context-root: false.

Chỉ cần cấu hình này khi tình huống redirect/context-root của Tomcat yêu cầu. Không thêm property vào mọi ứng dụng một cách máy móc; kiểm tra redirect thực tế và tài liệu của phiên bản đang chạy.

## 4. Cấu hình Nginx kết thúc TLS và chuyển HTTP vào ứng dụng

Ví dụ dưới đây giả định Nginx là điểm kết thúc TLS ở biên, public host là api.example.com, public prefix là /gateway, còn Spring Boot lắng nghe HTTP ở spring-app:8080.

~~~nginx
server {
    listen 443 ssl;
    server_name api.example.com;

    ssl_certificate     /etc/nginx/tls/api.example.com.crt;
    ssl_certificate_key /etc/nginx/tls/api.example.com.key;

    location /gateway/ {
        # URI "/" ở cuối proxy_pass thay prefix /gateway/ bằng "/".
        proxy_pass http://spring-app:8080/;

        proxy_set_header Host              $host;
        proxy_set_header X-Forwarded-Host  $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Port  $server_port;

        # Ví dụ Nginx là proxy đầu tiên nhận request từ Internet.
        proxy_set_header X-Forwarded-For  $remote_addr;

        # Thông báo prefix đã được strip trước khi chuyển tiếp.
        proxy_set_header X-Forwarded-Prefix /gateway;
    }
}
~~~

Trong cấu hình này:

- Client gọi /gateway/v3/api-docs.
- Nginx bỏ /gateway/ và chuyển /v3/api-docs tới ứng dụng.
- $scheme ở server TLS là https.
- $server_port là 443.
- X-Forwarded-Prefix thông báo prefix bên ngoài là /gateway.

Nginx quy định rằng nếu proxy_pass có URI, phần URI khớp với location sẽ được thay bằng URI trong proxy_pass. Vì vậy dấu / ở cuối proxy_pass http://spring-app:8080/; có ý nghĩa trong ví dụ strip prefix này.

### 4.1. Nếu muốn giữ nguyên prefix khi chuyển tiếp

Nếu ứng dụng tự phục vụ path /gateway/..., dùng cấu hình không có URI ở cuối proxy_pass:

~~~nginx
location /gateway/ {
    proxy_pass http://spring-app:8080;
}
~~~

Khi đó Nginx chuyển nguyên path /gateway/... tới ứng dụng. Ứng dụng cần có context path hoặc mapping tương ứng. Đừng đồng thời strip prefix ở proxy và cấu hình ứng dụng nhận prefix như path nội bộ; chọn một quy tắc nhất quán.

### 4.2. Proxy nằm sau một load balancer khác

Nếu Nginx nhận request từ một load balancer đã kết thúc TLS, $scheme tại Nginx có thể là http dù client bên ngoài dùng HTTPS. Trong trường hợp đó, không ghi đè X-Forwarded-Proto thành $scheme một cách máy móc.

Thay vào đó:

1. Chỉ tin header do load balancer thuộc trust boundary gửi tới.
2. Cấu hình load balancer xóa header forwarded do client tự gửi và ghi lại giá trị đúng.
3. Cấu hình Nginx nhận header từ đúng upstream tin cậy.
4. Chuyển tiếp giá trị đã được xác minh tới Spring Boot.

Chuỗi proxy phải có quy tắc rõ ràng về proxy nào được phép thêm hoặc sửa từng header. Không để client Internet tự quyết định scheme, host hoặc client IP mà ứng dụng tin cậy.

## 5. Ranh giới tin cậy của forwarded headers

Forwarded headers có thể ảnh hưởng tới URL redirect, server URL OpenAPI, địa chỉ client và logic bảo mật. Nếu ứng dụng nhận trực tiếp một request có X-Forwarded-Proto: https do client tự đặt, nó có thể hiểu nhầm một kết nối HTTP là HTTPS.

Spring Framework cảnh báo forwarded headers phải được thiết lập bởi proxy tin cậy. Proxy ở ranh giới tin cậy cần xóa các header Forwarded và X-Forwarded-* do client gửi vào, sau đó tự ghi giá trị hợp lệ. Không chỉ xóa một kiểu header; có thể có cả header chuẩn và header không chuẩn.

Các nguyên tắc triển khai:

- Không public trực tiếp cổng HTTP nội bộ của Spring Boot nếu ứng dụng dựa vào forwarded headers để xác định URL gốc.
- Chỉ cho phép proxy/load balancer tin cậy kết nối tới cổng backend.
- Ở proxy biên, ghi đè X-Forwarded-Proto, X-Forwarded-Host, X-Forwarded-Port và prefix theo cấu hình thật.
- Chỉ nối chuỗi X-Forwarded-For khi các hop trước đã được xác minh và có cấu hình trust tương ứng.
- Không đặt cấu hình trust proxy thành “tin tất cả” trong production.
- Kiểm tra host allow-list để tránh Host header injection hoặc tạo link trỏ tới domain không được phép.
- Không dùng forwarded headers làm bằng chứng xác thực danh tính người dùng.

### 5.1. Không mở cổng backend ra Internet

Nếu backend vẫn truy cập được trực tiếp từ Internet, client có thể bỏ qua Nginx và gửi forwarded headers giả. Khi đó:

- OpenAPI có thể sinh server URL theo host giả.
- Redirect có thể chuyển sang scheme hoặc host không mong muốn.
- Log có thể ghi nhận sai địa chỉ client.
- Cookie hoặc link tuyệt đối có thể được tạo với thuộc tính sai.

Hãy giới hạn network policy, firewall hoặc security group để chỉ proxy được truy cập backend. Nếu cần health check hoặc quản trị trực tiếp, tạo đường truy cập riêng với quyền và cấu hình rõ ràng.

## 6. Đảm bảo OpenAPI và Swagger UI dùng URL HTTPS công khai

Springdoc có thể tự suy ra server URL từ thông tin request. Khi forwarded headers được xử lý đúng, URL trong OpenAPI nên phản ánh địa chỉ public thay vì địa chỉ container.

Ví dụ mong muốn:

~~~yaml
servers:
  - url: https://api.example.com/gateway
    description: Public API
~~~

Nếu servers bị sinh thành http://spring-app:8080, hãy kiểm tra theo thứ tự:

1. Proxy có gửi X-Forwarded-Proto: https không?
2. Proxy có gửi đúng X-Forwarded-Host và X-Forwarded-Port không?
3. Spring Boot có xử lý forwarded headers không?
4. Prefix có bị strip và được gửi trong X-Forwarded-Prefix không?
5. Ứng dụng có nhận request trực tiếp từ client ngoài proxy không?
6. Có OpenAPIDefinition(servers = ...) hoặc OpenAPI bean đặt server URL cố định ghi đè URL tự sinh không?

### 6.1. Khai báo server URL tĩnh theo môi trường

Nếu một deployment luôn có public base URL cố định, có thể khai báo server rõ ràng:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.servers.Server;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
        servers = {
            @Server(
                    url = "https://api.example.com/gateway",
                    description = "Public HTTPS API"
            )
        }
)
class OpenApiServerConfiguration {
}
~~~

Server annotation tường minh được dùng thay cho URL tự suy ra. Cách này phù hợp khi mỗi môi trường có URL cố định và cấu hình có thể thay theo profile hoặc deployment. Tránh hard-code URL production vào artifact dùng chung cho local, test và staging.

### 6.2. Tùy chỉnh server URL khi cần

Springdoc cung cấp ServerBaseUrlCustomizer để điều chỉnh base URL được dùng trong Swagger UI/OpenAPI. Dùng nó khi cần chuẩn hóa URL theo một quy tắc deployment cụ thể, ví dụ bỏ port nội bộ hoặc sửa base path. Hãy ưu tiên forwarded headers được cấu hình đúng; customizer không nên che giấu việc proxy đang gửi sai scheme/host.

Nếu cùng một ứng dụng phục vụ Swagger UI qua nhiều proxy hoặc nhiều hostname, server URL có thể khác theo request. Springdoc mặc định cache tài liệu OpenAPI; trong trường hợp cần tính lại URL theo mỗi request, có thể cấu hình:

~~~yaml
springdoc:
  cache:
    disabled: true
~~~

Chỉ tắt cache khi thực sự cần server URL thay đổi theo request. Với deployment có một public base URL cố định, giữ cache mặc định thường hiệu quả hơn.

## 7. Đường dẫn Swagger UI khi có context path hoặc prefix

Có ba thành phần path cần phân biệt:

| Thành phần | Ví dụ | Ai quản lý |
|---|---|---|
| Public prefix | /gateway | Reverse proxy/load balancer. |
| Application context path | /service | Spring Boot, qua server.servlet.context-path. |
| Endpoint path | /v3/api-docs, /swagger-ui/** | Springdoc. |

URL bên ngoài có thể là:

https://api.example.com/gateway/service/v3/api-docs

Nếu proxy bỏ /gateway trước khi chuyển tiếp, ứng dụng nhận:

/service/v3/api-docs

Khi đó:

- server.servlet.context-path đại diện cho /service.
- X-Forwarded-Prefix đại diện cho /gateway.
- Không đặt server.servlet.context-path=/gateway nếu proxy đã strip prefix và ứng dụng chỉ nhận path còn lại.

### 7.1. Kiểm tra swagger-config

Swagger UI thường tải cấu hình từ /v3/api-docs/swagger-config, rồi lấy URL OpenAPI JSON theo cấu hình đó. Khi dùng prefix, cần xác nhận cả:

- Trang /swagger-ui.html redirect đúng sang URL có HTTPS và prefix.
- CSS/JavaScript của /swagger-ui/** tải được qua prefix.
- swagger-config tải được qua prefix.
- URL OpenAPI JSON trong cấu hình trỏ tới đúng /gateway/v3/api-docs hoặc group tương ứng.
- Nút Try it out gọi API bằng server URL HTTPS công khai.

Nếu tự cấu hình springdoc.swagger-ui.url hoặc configUrl, tránh hard-code hostname nội bộ như http://spring-app:8080. Dùng URL tương đối đúng với public path hoặc cấu hình URL theo môi trường.

## 8. Cấu hình proxy và ứng dụng theo một ví dụ hoàn chỉnh

Giả sử:

- Public URL: https://api.example.com/gateway.
- Nginx kết thúc TLS trên cổng 443.
- Nginx chuyển HTTP tới spring-app:8080.
- Nginx strip prefix /gateway.
- Spring Boot 3.x dùng Spring MVC.

Nginx:

~~~nginx
location /gateway/ {
    proxy_pass http://spring-app:8080/;

    proxy_set_header Host              $host;
    proxy_set_header X-Forwarded-Host  $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Port  $server_port;
    proxy_set_header X-Forwarded-For   $remote_addr;
    proxy_set_header X-Forwarded-Prefix /gateway;
}
~~~

Spring Boot 3.x:

~~~yaml
server:
  forward-headers-strategy: framework

springdoc:
  api-docs:
    path: /v3/api-docs
  swagger-ui:
    path: /swagger-ui.html
~~~

Với Spring Boot 4.x, phần forwarded headers chuyển thành:

~~~yaml
server:
  request:
    header:
      forwarded:
        strategy: framework
        use-prefix: true
~~~

Không cần đổi endpoint springdoc chỉ vì proxy strip prefix. Ứng dụng tiếp tục phục vụ /v3/api-docs nội bộ; framework dùng forwarded prefix để xây dựng URL bên ngoài.

Nếu muốn URL public cố định, có thể khai báo servers theo profile. Nếu muốn springdoc suy ra URL theo request, không khai báo server cố định và kiểm tra forwarded headers cùng cache policy.

## 9. Kiểm thử scheme, host, port và prefix

Đừng chỉ kiểm tra rằng Swagger UI trả HTTP 200. Hãy xác minh URL cuối cùng mà client nhận được.

### 9.1. Kiểm tra bằng curl

Kiểm tra redirect từ trang Swagger UI:

~~~bash
curl -I https://api.example.com/gateway/swagger-ui.html
~~~

Header Location (nếu có) cần dùng https://api.example.com/gateway/..., không phải http://spring-app:8080/....

Kiểm tra OpenAPI server:

~~~bash
curl -s https://api.example.com/gateway/v3/api-docs
~~~

Đọc trường servers trong JSON. Kết quả mong đợi có scheme https, host public và prefix /gateway.

Kiểm tra Swagger UI trong browser Network tab:

- swagger-config trả thành công.
- OpenAPI JSON được tải từ public path.
- Không có request tới hostname container hoặc HTTP URL.
- CSS/JS không bị 404 do thiếu prefix.
- Try it out gọi đúng HTTPS server.

### 9.2. Kiểm thử forwarded headers bằng MockMvc

MockMvc có thể kiểm tra Spring application xử lý header forwarded khi test dùng cùng cấu hình filter. Ví dụ dưới đây minh họa cho Spring Boot 3.x:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "server.forward-headers-strategy=framework",
        "springdoc.cache.disabled=true"
})
@AutoConfigureMockMvc
class ForwardedOpenApiUrlTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void generatesPublicHttpsServerUrl() throws Exception {
        mockMvc.perform(get("/v3/api-docs")
                        .header("X-Forwarded-Proto", "https")
                        .header("X-Forwarded-Host", "api.example.com")
                        .header("X-Forwarded-Port", "443")
                        .header("X-Forwarded-Prefix", "/gateway"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.servers[0].url")
                        .value("https://api.example.com/gateway"));
    }
}
~~~

Test này giả định không có server URL tĩnh ghi đè và phiên bản springdoc đang dùng tự suy ra server URL từ request. Nếu phiên bản hoặc cấu hình ứng dụng tạo URL khác, điều chỉnh assertion theo contract đã chọn.

MockMvc không mô phỏng Nginx rewrite, TLS handshake hoặc firewall. Cần thêm integration test qua proxy thật hoặc môi trường staging để xác minh toàn bộ luồng.

### 9.3. Kiểm tra proxy không tin header giả từ client

Gửi request từ bên ngoài với forwarded header giả, ví dụ X-Forwarded-Proto: http hoặc X-Forwarded-Host: attacker.example, rồi xác nhận proxy biên ghi đè bằng giá trị chuẩn. Kết quả server URL vẫn phải là HTTPS và host hợp lệ.

Đồng thời thử kết nối trực tiếp tới backend từ một mạng không được phép. Kết nối cần bị chặn ở network layer; không dựa vào ứng dụng để sửa mọi header giả từ Internet.

## 10. Các lỗi thường gặp

- **Swagger UI sinh URL HTTP**: ứng dụng chưa xử lý X-Forwarded-Proto hoặc proxy gửi sai giá trị.
- **OpenAPI chứa hostname container**: Host/X-Forwarded-Host chưa được chuyển tiếp hoặc framework chưa dùng forwarded headers.
- **Thiếu public prefix**: proxy strip path nhưng không gửi X-Forwarded-Prefix, hoặc ứng dụng chưa bật xử lý prefix.
- **Prefix xuất hiện hai lần**: proxy giữ nguyên prefix nhưng ứng dụng cũng thêm prefix như context path hoặc forwarded prefix.
- **Redirect quay về HTTP**: Tomcat hoặc ứng dụng chưa nhận scheme HTTPS gốc; kiểm tra forwarded strategy và redirect context root.
- **Swagger UI tải được nhưng JSON 404**: swagger-config trỏ tới URL không có prefix hoặc proxy rewrite sai.
- **Dùng proxy_pass sai dấu /**: Nginx thay hoặc giữ URI khác với mong đợi.
- **Tin forwarded headers từ mọi nguồn**: client có thể giả mạo scheme, host hoặc client IP.
- **Bật NATIVE nhưng prefix vẫn thiếu**: container native có thể không hỗ trợ prefix; thử FRAMEWORK hoặc cấu hình use-prefix theo phiên bản Boot.
- **Tạo thêm ForwardedHeaderFilter thủ công**: có thể xử lý header hai lần khi Boot đã tự cấu hình.
- **Server URL bị cache từ proxy đầu tiên**: nếu cùng ứng dụng phục vụ nhiều URL ngoài khác nhau, cân nhắc springdoc.cache.disabled=true.
- **Hard-code URL production vào mọi môi trường**: local/staging có thể trỏ nhầm sang production.
- **Backend HTTP mở trực tiếp ra Internet**: client có thể bỏ qua proxy và gửi forwarded headers giả.

## 11. Quy trình triển khai

1. **Xác định TLS topology**: termination, re-encryption hay passthrough.
2. **Chốt public URL**: scheme, host, port và prefix mà client nhìn thấy.
3. **Chọn path mapping**: proxy giữ prefix hay strip prefix trước khi chuyển tiếp.
4. **Cấu hình proxy**: ghi đúng forwarded headers, không tin header tùy ý từ client.
5. **Cấu hình Spring Boot theo major version**: Boot 3 dùng server.forward-headers-strategy; Boot 4 dùng server.request.header.forwarded.*.
6. **Kiểm soát trust boundary**: chỉ proxy tin cậy được kết nối backend và tạo forwarded headers.
7. **Kiểm tra springdoc**: xác nhận servers, swagger-config, redirect và tài nguyên UI.
8. **Chọn server URL policy**: tự suy ra qua forwarded headers hoặc khai báo tĩnh theo môi trường.
9. **Kiểm tra cache**: chỉ tắt cache nếu URL cần thay đổi theo từng request/proxy.
10. **Kiểm thử end-to-end**: HTTPS ngoài, HTTP nội bộ, prefix, redirect, Try it out và request header giả.

## 12. Checklist review

- [ ] TLS được kết thúc ở đúng proxy hoặc ứng dụng theo kiến trúc đã chọn.
- [ ] Public URL có scheme HTTPS, host, port và prefix đúng.
- [ ] Proxy ghi đè forwarded headers từ nguồn tin cậy.
- [ ] Backend chỉ nhận kết nối từ proxy hoặc mạng được phép.
- [ ] Spring Boot dùng đúng forwarded strategy cho major version.
- [ ] X-Forwarded-Prefix được hỗ trợ nếu proxy strip prefix.
- [ ] Không cấu hình prefix trùng giữa proxy rewrite, context path và forwarded prefix.
- [ ] Tomcat redirect context root được xử lý nếu có redirect sai scheme.
- [ ] OpenAPI servers không lộ host hoặc port nội bộ.
- [ ] Swagger UI và swagger-config tải JSON qua HTTPS public path.
- [ ] Server URL tĩnh được quản lý theo môi trường nếu có.
- [ ] Cache được giữ mặc định hoặc tắt có chủ đích khi URL động.
- [ ] Integration test kiểm tra URL qua proxy thật.
- [ ] Test xác nhận forwarded headers giả từ client không được tin cậy.

## 13. Tài liệu tham khảo

- [Spring Boot 3.5 – Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html)
- [Spring Boot 4.0 – Forwarded Headers and Prefix Support](https://docs.spring.io/spring-boot/4.0/how-to/webserver.html)
- [Spring Boot – Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html)
- [Spring Framework – ForwardedHeaderFilter and Security Considerations](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html)
- [springdoc-openapi FAQ – Deploy behind a reverse proxy](https://springdoc.org/faq.html)
- [Nginx – ngx_http_proxy_module and proxy_pass URI behavior](https://nginx.org/en/docs/http/ngx_http_proxy_module.html)
- [RFC 7239 – Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239)

Khi HTTPS kết thúc tại proxy, ứng dụng cần dùng forwarded headers đáng tin cậy để hiểu đúng URL bên ngoài. Hãy đồng bộ TLS topology, path rewrite, forwarded strategy theo phiên bản Spring Boot và server URL của springdoc. Kiểm tra cả OpenAPI JSON, Swagger UI, redirect và Try it out qua proxy thật để bảo đảm client luôn dùng HTTPS cùng public path chính xác.
