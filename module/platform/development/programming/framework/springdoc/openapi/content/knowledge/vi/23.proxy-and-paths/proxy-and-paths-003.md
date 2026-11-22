# Server URL được suy ra từ request hoặc khai báo tường minh

OpenAPI dùng đối tượng Server để cho client biết API được gọi tại host nào và base path nào. Khi người dùng mở Swagger UI, lựa chọn server này quyết định URL đích được ghép với path của operation trong lúc Try it out.

springdoc-openapi có thể tạo server URL dựa trên thông tin của HTTP request đang phục vụ tài liệu. Cách này tiện khi chạy local hoặc triển khai sau proxy có cấu hình forwarded headers đúng. Nếu API có một địa chỉ public cố định, hoặc cần công bố nhiều môi trường, có thể khai báo servers tường minh bằng annotation hay OpenAPI bean.

Ứng dụng phía sau reverse proxy thường nhận request nội bộ với host, scheme, port hoặc path khác URL mà client bên ngoài sử dụng. Nếu không xử lý forwarded headers, tài liệu có thể công bố địa chỉ nội bộ như http://10.0.0.12:8080 thay vì https://api.example.com. Bài này hướng dẫn cách chọn nguồn server URL, cấu hình proxy, xử lý prefix, tùy biến và kiểm tra kết quả.

## 1. Server URL nằm ở đâu trong OpenAPI?

Trong OpenAPI, trường servers chứa danh sách Server Object. Mỗi server có URL cơ sở và có thể có description cùng biến URL.

~~~yaml
openapi: 3.1.0
info:
  title: Order API
  version: 1.0.0
servers:
  - url: https://api.example.com/v1
    description: API production
paths:
  /orders:
    get:
      summary: Liệt kê đơn hàng
      responses:
        '200':
          description: Thành công
~~~

Client ghép server URL với path của operation. Trong ví dụ, URL gọi API là:

~~~text
https://api.example.com/v1/orders
~~~

Phần /v1 thuộc base path của server. Phần /orders thuộc path được mô tả trong OpenAPI.

Server URL không phải URL của file tài liệu. Cần phân biệt:

| Thành phần | Vai trò |
|---|---|
| /v3/api-docs | Endpoint cung cấp OpenAPI JSON |
| /swagger-ui.html | Đường dẫn mở giao diện Swagger UI |
| servers[].url | Địa chỉ API mà client gọi |
| springdoc.swagger-ui.url | URL để Swagger UI tải một file OpenAPI |

Đổi springdoc.swagger-ui.url không tự thay đổi servers[].url. Ngược lại, đổi server URL không làm thay đổi vị trí tải tài liệu.

## 2. Server URL suy ra và server URL tường minh

Có hai cách chính để cung cấp server URL:

| Cách | Nguồn dữ liệu | Phù hợp khi |
|---|---|---|
| Suy ra từ request | Scheme, host, port và context/prefix mà ứng dụng nhìn thấy | Nhiều hostname hoặc proxy khác nhau cùng phục vụ ứng dụng |
| Khai báo tường minh | Annotation hoặc OpenAPI bean | Public base URL cố định hoặc cần liệt kê môi trường rõ ràng |

springdoc có thể tự tạo server URL khi tài liệu không khai báo server tường minh. Nếu có server annotation, các khai báo đó được sử dụng thay cho việc tự suy ra từ request.

Cần phân biệt hành vi của springdoc với mặc định của một OpenAPI document thuần: theo đặc tả, nếu trường servers không có hoặc là danh sách rỗng thì server mặc định có URL tương đối /. springdoc có thể tạo server URL dựa trên request khi sinh tài liệu. Vì vậy, hãy kiểm tra trường servers trong JSON đầu ra thay vì suy luận từ riêng mã controller.

Vì vậy, hãy quyết định nguồn nào là nguồn có thẩm quyền. Nếu đã khai báo server cố định nhưng mong URL tự thay đổi theo header của proxy, kết quả có thể không như kỳ vọng. Nếu muốn server URL theo request, đừng vô tình đưa một danh sách servers tĩnh vào cấu hình.

## 3. Server URL được suy ra từ request như thế nào?

Khi tạo tài liệu, springdoc có thể sử dụng thông tin request hiện tại để xây dựng server URL. Những thành phần quan trọng gồm:

- Scheme: http hoặc https.
- Host: tên miền hoặc địa chỉ IP.
- Port: cổng mà client sử dụng.
- Context path hoặc prefix public nếu có.

Ví dụ ứng dụng chạy trực tiếp tại:

~~~text
http://localhost:8080
~~~

Tài liệu được yêu cầu từ địa chỉ này có thể công bố server URL tương ứng. Khi chạy sau proxy, request nội bộ có thể tới:

~~~text
http://10.0.0.12:8080
~~~

Trong khi client bên ngoài sử dụng:

~~~text
https://api.example.com
~~~

Nếu ứng dụng chỉ nhìn request nội bộ mà không được cung cấp thông tin gốc, springdoc có thể suy ra server URL sai đối với client. Đây là lý do cần cấu hình forwarded headers ở cả proxy và Spring Boot.

## 4. Các header mô tả request gốc

Có hai nhóm header thường gặp:

- Forwarded: header chuẩn được định nghĩa trong RFC 7239.
- X-Forwarded-*: nhóm header theo quy ước phổ biến trước khi có Forwarded.

Các header thường được proxy gửi:

| Header | Thông tin |
|---|---|
| Forwarded | Có thể mang proto, host và thông tin proxy theo chuẩn |
| X-Forwarded-Host | Host public mà client đã gọi |
| X-Forwarded-Proto | Scheme public, thường là http hoặc https |
| X-Forwarded-Port | Port public |
| X-Forwarded-Prefix | Prefix public được proxy thêm hoặc dùng để rewrite |
| X-Forwarded-For | Địa chỉ IP client qua chuỗi proxy |

Đối với server URL, các giá trị quan trọng nhất thường là host, proto, port và prefix. X-Forwarded-For chủ yếu mô tả địa chỉ client, không phải hostname của API.

Ví dụ request được proxy chuyển tiếp có thể kèm:

~~~http
Forwarded: proto=https;host=api.example.com
X-Forwarded-Host: api.example.com
X-Forwarded-Proto: https
X-Forwarded-Port: 443
X-Forwarded-Prefix: /gateway
~~~

Ứng dụng cần được cấu hình để xử lý những header này. Chỉ gửi header ở proxy mà Spring Boot không đọc chúng thì URL suy ra vẫn có thể dùng host và scheme nội bộ.

## 5. Bật xử lý forwarded headers trong Spring Boot

Spring Boot cung cấp thuộc tính server.forward-headers-strategy. Với cấu hình dùng Spring Framework để xử lý forwarded headers:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Hoặc application.properties:

~~~properties
server.forward-headers-strategy=framework
~~~

Các lựa chọn thường gặp:

| Giá trị | Ý nghĩa |
|---|---|
| none | Không áp dụng forwarded headers |
| native | Dùng khả năng xử lý của web server/container |
| framework | Dùng cơ chế của Spring Framework |

NATIVE phụ thuộc khả năng của container. FRAMEWORK dùng thành phần của Spring Framework để sửa thông tin request theo forwarded headers.

Với Servlet stack, Spring Framework cung cấp ForwardedHeaderFilter. Với WebFlux, Spring Framework dùng ForwardedHeaderTransformer. Khi chọn server.forward-headers-strategy=framework, Spring Boot quản lý cơ chế phù hợp với web stack; không cần tự đăng ký thêm filter hoặc transformer nếu cấu hình Boot đã thực hiện việc đó.

Tên property và hành vi mặc định có thể thay đổi theo dòng Spring Boot. Hãy đối chiếu tài liệu đúng phiên bản của dự án, đặc biệt khi nâng cấp major version.

## 6. Cấu hình proxy gửi thông tin public

Ví dụ Nginx chuyển tiếp request từ public prefix /gateway tới ứng dụng chạy ở root path:

~~~nginx
location /gateway/ {
    proxy_pass http://order-service:8080/;

    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Port $server_port;
    proxy_set_header X-Forwarded-Prefix /gateway;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
~~~

Trong ví dụ:

- Client gọi https://api.example.com/gateway/orders.
- Proxy chuyển request tới http://order-service:8080/orders.
- Proxy cung cấp host, scheme, port và prefix public.
- Ứng dụng xử lý forwarded headers để biết URL public có prefix /gateway.

Cấu hình proxy thực tế phụ thuộc cách proxy_pass rewrite path, TLS termination và số lớp proxy. Nếu proxy không loại prefix khỏi path, hoặc ứng dụng đã có context path tương ứng, không được cộng prefix lần thứ hai.

Không sao chép cấu hình mẫu mà không kiểm tra URL sau rewrite. Hãy xác định rõ path mà client gọi, path proxy gửi tới ứng dụng và path mà Spring MVC/WebFlux nhận được.

## 7. Xử lý X-Forwarded-Prefix

X-Forwarded-Prefix quan trọng khi gateway thêm một đoạn path ở public URL nhưng bỏ đoạn đó trước khi chuyển request tới backend.

Ví dụ:

~~~text
Public URL:
https://api.example.com/platform/orders

Backend URL:
http://order-service:8080/orders
~~~

Proxy có thể gửi:

~~~http
X-Forwarded-Prefix: /platform
~~~

Ứng dụng xử lý prefix để các URL được tạo ra hướng về public path /platform.

Nếu thiếu header này, server URL trong OpenAPI có thể chỉ là:

~~~text
https://api.example.com
~~~

Swagger UI sau đó gọi /orders thay vì /platform/orders và nhận 404.

Nếu prefix xuất hiện hai lần, URL có thể thành:

~~~text
https://api.example.com/platform/platform/orders
~~~

Lỗi lặp prefix thường do proxy giữ nguyên prefix trong request path nhưng đồng thời gửi X-Forwarded-Prefix, hoặc ứng dụng đã cấu hình context path và lại cộng prefix lần nữa.

Kiểm tra một request thực tế qua gateway để xác định chính xác prefix thuộc server URL hay path của operation.

## 8. Servlet và WebFlux xử lý forwarded headers

Cùng một cấu hình Spring Boot có thể áp dụng cho hai web stack, nhưng thành phần nền khác nhau:

| Web stack | Thành phần Spring Framework |
|---|---|
| Spring MVC / Servlet | ForwardedHeaderFilter |
| Spring WebFlux / Reactive | ForwardedHeaderTransformer |

ForwardedHeaderFilter bọc Servlet request để các thành phần phía sau nhìn thấy scheme, host, port và thông tin đã được chuyển tiếp. ForwardedHeaderTransformer thực hiện vai trò tương ứng trong WebFlux ở giai đoạn xử lý ServerHttpRequest.

Khi dùng Spring Boot, ưu tiên cấu hình server.forward-headers-strategy phù hợp. Nếu tự đăng ký thành phần thủ công, phải hiểu thứ tự xử lý và tránh đăng ký trùng với cơ chế Boot đã tạo.

Đối với WebFlux, nếu khai báo transformer trực tiếp theo cấu hình Spring Framework, bean thường dùng tên forwardedHeaderTransformer để được nhận diện. Không cần thêm bean thủ công nếu Boot đã cấu hình framework strategy.

## 9. Khai báo server URL tường minh bằng @OpenAPIDefinition

Nếu public base URL cố định, có thể khai báo servers trong @OpenAPIDefinition:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.servers.Server;
import org.springframework.context.annotation.Configuration;

@OpenAPIDefinition(
    servers = {
        @Server(
            url = "https://api.example.com/v1",
            description = "Production API"
        ),
        @Server(
            url = "https://sandbox-api.example.com/v1",
            description = "Sandbox API"
        )
    }
)
@Configuration
class OpenApiConfiguration {
}
~~~

OpenAPI sẽ có hai server để người dùng chọn trong Swagger UI. Client generator cũng có thể sử dụng danh sách server theo cách mà công cụ hỗ trợ.

Khi đã khai báo servers tường minh, springdoc dùng các server đó thay vì tự suy ra URL từ request. Điều này phù hợp khi muốn kiểm soát chính xác host public và base path.

Không nên khai báo URL production cố định trong mọi môi trường nếu development hoặc staging dùng hostname khác. Hãy đưa URL vào cấu hình môi trường hoặc dùng server variables khi phù hợp.

## 10. Khai báo servers bằng OpenAPI bean

Có thể tạo OpenAPI bean và thiết lập servers bằng swagger-models:

~~~java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.servers.Server;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

import java.util.List;

@Configuration
class OpenApiServerConfiguration {

    @Bean
    OpenAPI customOpenAPI(Environment environment) {
        String publicBaseUrl =
            environment.getRequiredProperty("api.public-base-url");

        return new OpenAPI()
            .servers(List.of(
                new Server()
                    .url(publicBaseUrl)
                    .description("Public API")
            ));
    }
}
~~~

Cấu hình application.yml:

~~~yaml
api:
  public-base-url: https://api.example.com/v1
~~~

application-dev.yml có thể thay bằng:

~~~yaml
api:
  public-base-url: https://dev-api.example.com/v1
~~~

Ưu điểm của OpenAPI bean là URL có thể lấy từ property, biến môi trường hoặc config server. Nhờ đó cùng một artifact ứng dụng có thể chạy ở nhiều môi trường với server URL tương ứng.

Khi tự khai báo OpenAPI bean, hãy giữ các metadata khác như Info, Components, security schemes và tags nếu ứng dụng cần. Không vô tình tạo một định nghĩa OpenAPI rỗng làm mất cấu hình tùy biến hiện có.

## 11. Dùng ServerBaseUrlCustomizer để chỉnh URL suy ra

Nếu URL được suy ra gần đúng nhưng cần điều chỉnh một phần, springdoc cung cấp ServerBaseUrlCustomizer. Extension point này nhận server base URL đã được tạo và trả về giá trị đã chỉnh sửa.

Ví dụ thay host nội bộ bằng host public trong một cấu hình triển khai cụ thể:

~~~java
import org.springdoc.core.customizers.ServerBaseUrlCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ServerUrlCustomizationConfiguration {

    @Bean
    ServerBaseUrlCustomizer serverBaseUrlCustomizer() {
        return serverBaseUrl -> {
            String internalBase = "http://order-service:8080";
            String publicBase = "https://api.example.com";

            if (serverBaseUrl.startsWith(internalBase)) {
                return publicBase
                    + serverBaseUrl.substring(internalBase.length());
            }

            return serverBaseUrl;
        };
    }
}
~~~

Ví dụ này minh họa việc thay một base URL đã biết và giữ lại phần path còn lại. Trong thực tế, chỉ dùng cách thay thế chuỗi khi mapping rõ ràng và được quản lý theo môi trường.

ServerBaseUrlCustomizer phù hợp để chuẩn hóa URL, chẳng hạn bỏ port nội bộ hoặc điều chỉnh host. Nó không thay thế việc cấu hình proxy gửi forwarded headers. Nếu cần suy ra URL public chính xác từ request, hãy xử lý forwarded headers trước; customizer chỉ nên thực hiện bước điều chỉnh bổ sung.

Package của interface và extension point có thể khác giữa major version springdoc. Hãy kiểm tra API của đúng version trước khi sao chép import.

## 12. Chọn giữa proxy headers, servers tường minh và customizer

| Tình huống | Cách phù hợp |
|---|---|
| Một ứng dụng phục vụ qua nhiều hostname public | Forwarded headers từ proxy đáng tin cậy |
| Public URL cố định theo môi trường | OpenAPI bean lấy URL từ property |
| Cần công bố production và sandbox cùng lúc | Danh sách servers tường minh |
| URL suy ra đúng phần lớn nhưng cần chuẩn hóa host/port | ServerBaseUrlCustomizer |
| Gateway rewrite path | X-Forwarded-Prefix hoặc cấu hình server base path phù hợp |
| Nhiều proxy cùng phục vụ một tài liệu nhưng URL thay đổi theo request | Forwarded headers và cân nhắc cache |
| Chỉ muốn đổi URL mà Swagger UI tải file spec | springdoc.swagger-ui.url, không phải servers |

Không nên dùng customizer để bù cho proxy chưa gửi đúng header. Cũng không nên khai báo servers cố định rồi mong server URL thay đổi theo hostname của request.

## 13. Dùng nhiều Server Object cho các môi trường

OpenAPI cho phép liệt kê nhiều server:

~~~yaml
servers:
  - url: https://dev-api.example.com/v1
    description: Development
  - url: https://staging-api.example.com/v1
    description: Staging
  - url: https://api.example.com/v1
    description: Production
~~~

Swagger UI có thể hiển thị danh sách server để người dùng chọn. Điều này hữu ích khi người dùng có quyền truy cập nhiều môi trường và muốn thử cùng một operation trên từng server.

Chỉ đưa server thực sự được phép công bố vào tài liệu. Không để hostname nội bộ, IP private hoặc URL management xuất hiện trong spec public nếu chúng không dành cho client bên ngoài.

Nếu mỗi môi trường có auth, dữ liệu hoặc policy khác nhau, hãy mô tả rõ sự khác biệt và kiểm tra security scheme tương ứng. Việc chọn server không tự đổi credential hoặc quyền truy cập.

## 14. Server Variables cho URL có phần thay đổi

Nếu URL có cấu trúc giống nhau nhưng một phần thay đổi theo môi trường, có thể dùng server variables:

~~~yaml
servers:
  - url: https://{environment}.api.example.com/{basePath}
    description: API server
    variables:
      environment:
        default: api
        enum:
          - api
          - sandbox
      basePath:
        default: v1
~~~

Server variables giúp tránh lặp nhiều URL có cùng cấu trúc. Mỗi biến cần có default; nếu giới hạn lựa chọn, có thể khai báo enum.

Ví dụ trên tạo URL production https://api.api.example.com/v1 và sandbox https://sandbox.api.example.com/v1. Nếu hostname thực tế là api.example.com và sandbox-api.example.com, hai hostname có cấu trúc khác nhau; liệt kê hai Server Object thường rõ ràng hơn.

Server URL phải là URI hợp lệ và không chứa query hoặc fragment. Không dùng server variables để che giấu mapping phức tạp mà client không thể hiểu.

## 15. Server URL ở root, path và operation

OpenAPI cho phép servers ở nhiều cấp:

- Root OpenAPI Object: áp dụng mặc định cho toàn tài liệu.
- Path Item Object: áp dụng cho tất cả operation của path đó.
- Operation Object: áp dụng riêng cho một operation.

Server ở cấp thấp hơn có thể ghi đè server cấp cao hơn cho phạm vi tương ứng.

~~~yaml
servers:
  - url: https://api.example.com/v1

paths:
  /orders:
    get:
      responses:
        '200':
          description: Thành công

  /reports:
    servers:
      - url: https://reports.example.com
    get:
      responses:
        '200':
          description: Báo cáo
~~~

Operation /orders dùng server root https://api.example.com/v1. Path /reports dùng server riêng https://reports.example.com.

Khi điều tra Swagger UI gọi sai host, hãy kiểm tra servers không chỉ ở root. Có thể operation hoặc path đã ghi đè server toàn cục.

## 16. Ghép server URL với path và tránh lặp context path

Giả sử API public có base URL:

~~~text
https://api.example.com/platform/v1
~~~

Path trong OpenAPI nên là:

~~~yaml
paths:
  /orders:
    get:
      responses:
        '200':
          description: Thành công
~~~

URL cuối là:

~~~text
https://api.example.com/platform/v1/orders
~~~

Không nên vừa đặt /platform/v1 trong server URL vừa khai báo path /platform/v1/orders, vì URL có thể bị lặp prefix.

Nếu ứng dụng có context path hoặc WebFlux base path, xác định xem phần đó đã nằm trong server URL được suy ra hay chưa. Tương tự, nếu proxy gửi X-Forwarded-Prefix, đừng thêm lại prefix trong @Server hoặc OpenAPI bean mà không kiểm tra kết quả.

Một cách debug dễ dàng là ghi ra ba giá trị: public URL người dùng gọi, internal URL proxy chuyển tới backend và server URL trong OpenAPI JSON.

## 17. Context path và springdoc endpoint path là hai cấu hình khác nhau

Spring Boot có thể chạy ứng dụng dưới context path. Ví dụ Servlet stack:

~~~yaml
server:
  servlet:
    context-path: /shop
~~~

Khi đó URL public trực tiếp có thể là https://api.example.com/shop. Swagger UI và OpenAPI endpoint cũng nằm dưới context path, trừ khi cấu hình khác.

Đường dẫn API docs có thể được tùy chỉnh riêng:

~~~yaml
springdoc:
  api-docs:
    path: /internal/openapi
  swagger-ui:
    path: /internal/docs
~~~

api-docs.path điều chỉnh endpoint tài liệu. swagger-ui.path điều chỉnh đường dẫn giao diện. Chúng không phải server URL của operation.

Khi thay context path hoặc path của springdoc, hãy cập nhật proxy routing và security matcher tương ứng. Không giả định thay đổi đường dẫn tài liệu sẽ tự thêm prefix vào server URL của API.

## 18. Xử lý server URL khi có nhiều proxy

Một request có thể đi qua CDN, load balancer, ingress và reverse proxy trước khi tới Spring Boot:

~~~text
Browser
  -> CDN
  -> API Gateway
  -> Kubernetes Ingress
  -> Spring Boot service
~~~

Mỗi lớp có thể thay đổi host, scheme, port hoặc path. Cần quy định proxy nào là nguồn đáng tin cậy cuối cùng để ghi forwarded headers.

Khuyến nghị:

- Proxy ở ranh giới tin cậy xóa forwarded headers do client gửi vào.
- Proxy tạo hoặc ghi đè Forwarded/X-Forwarded-* theo thông tin mà nó xác minh.
- Proxy phía sau chỉ tiếp tục chuỗi thông tin đã được kiểm soát.
- Backend chỉ nhận traffic từ proxy hoặc network được tin cậy.
- Không để ứng dụng public trực tiếp nhưng lại tin mọi forwarded header.

Nếu mỗi lớp tự nối thêm giá trị header, ứng dụng có thể chọn nhầm host hoặc scheme. Hãy xác định rõ quy tắc của hạ tầng và kiểm tra request thực tế.

## 19. Rủi ro bảo mật khi tin forwarded headers

Forwarded headers có thể bị giả mạo nếu client gửi trực tiếp tới ứng dụng và ứng dụng tin giá trị đó. Kẻ tấn công có thể làm tài liệu sinh ra host không mong muốn hoặc ảnh hưởng URL tuyệt đối được tạo từ request.

Để bảo vệ:

- Chỉ chấp nhận forwarded headers từ proxy tin cậy.
- Proxy tại ranh giới tin cậy phải xóa hoặc ghi đè cả Forwarded và X-Forwarded-* từ request bên ngoài.
- Không chỉ xóa một nhóm header mà để nhóm còn lại đi qua.
- Giới hạn network để client không thể bỏ qua proxy và gọi trực tiếp backend.
- Không dùng Host header do client tùy ý gửi làm public base URL nếu chưa xác minh.
- Kiểm tra redirect, link tuyệt đối và OpenAPI server URL sau triển khai.

ForwardedHeaderFilter và ForwardedHeaderTransformer có thể áp dụng thông tin header hoặc chỉ xóa header trong chế độ remove-only. Việc xử lý header không thay thế cấu hình trust boundary ở proxy.

## 20. Cache OpenAPI và server URL thay đổi theo request

springdoc mặc định tính toán OpenAPI description và cache kết quả. Điều này thường phù hợp khi server URL ổn định.

Tuy nhiên, nếu cùng một ứng dụng được phục vụ qua nhiều hostname hoặc proxy khác nhau, server URL suy ra từ request đầu tiên có thể bị giữ lại trong cache. Request tiếp theo qua hostname khác có thể nhận lại document chứa URL trước đó.

Nếu cần tính lại OpenAPI description theo từng request, có thể tắt cache:

~~~yaml
springdoc:
  cache:
    disabled: true
~~~

Hoặc:

~~~properties
springdoc.cache.disabled=true
~~~

Chỉ bật khi thực sự cần URL động theo request. Tắt cache có thể khiến việc tạo OpenAPI document diễn ra thường xuyên hơn và tăng chi phí xử lý.

Nếu servers đã được khai báo tường minh và không thay đổi theo request, thường không cần tắt cache chỉ để giải quyết server URL.

## 21. ServerBaseUrlCustomizer không thay thế cache policy

ServerBaseUrlCustomizer giúp điều chỉnh giá trị base URL mà springdoc tạo. Nhưng nếu tài liệu đã được cache, thay đổi request hoặc cấu hình không nhất thiết làm document được tạo lại ở mỗi lần gọi.

Khi URL phụ thuộc request:

1. Proxy gửi forwarded headers đúng.
2. Spring Boot xử lý forwarded headers.
3. springdoc suy ra base URL từ request đã được điều chỉnh.
4. Nếu cần, ServerBaseUrlCustomizer chuẩn hóa URL.
5. Cache được cấu hình phù hợp nếu URL phải thay đổi theo từng request.

Không thêm customizer trước khi xác minh request đã có host/scheme/prefix đúng. Nếu đầu vào đã sai, customizer có thể chỉ che một phần lỗi và làm cấu hình khó bảo trì.

## 22. Phân biệt server URL với springdoc.swagger-ui.url

Hai thuộc tính thường bị nhầm:

~~~yaml
springdoc:
  swagger-ui:
    url: /v3/api-docs
~~~

springdoc.swagger-ui.url chỉ định URL mà Swagger UI tải tài liệu OpenAPI. Nó không quyết định server URL dùng để gửi request API.

Trong khi đó, OpenAPI servers:

~~~yaml
servers:
  - url: https://api.example.com/v1
~~~

xác định base URL cho operation khi client thực hiện request.

Ví dụ Swagger UI có thể tải spec từ https://docs.example.com/specs/orders.json nhưng server API trong spec là https://api.example.com/v1. Đây là cấu hình hợp lệ. Tài liệu có thể được host ở một domain riêng và mô tả API ở domain khác.

## 23. Kiểm tra server URL trong OpenAPI JSON

Sau khi ứng dụng chạy, tải document qua public URL:

~~~bash
curl -fsS https://api.example.com/gateway/v3/api-docs -o openapi.json
~~~

Xem danh sách server:

~~~bash
jq '.servers' openapi.json
~~~

Xem URL đầu tiên:

~~~bash
jq -r '.servers[0].url' openapi.json
~~~

Kiểm tra operation có server riêng hay không:

~~~bash
jq '.paths["/orders"].get.servers' openapi.json
~~~

Kiểm tra path item có server riêng:

~~~bash
jq '.paths["/reports"].servers' openapi.json
~~~

Đối chiếu các thành phần:

- Scheme có phải https khi client truy cập qua TLS không?
- Host có phải public hostname không?
- Port có đúng hoặc đã được bỏ khi dùng cổng mặc định không?
- Context path và X-Forwarded-Prefix có đủ không?
- Prefix có bị lặp không?
- Có hostname nội bộ hoặc IP private bị lộ không?
- Path-level hoặc operation-level server có ghi đè root không?

Không chỉ kiểm tra document ở localhost. Hãy tải spec qua hostname public sau reverse proxy vì đó là URL mà client thật sẽ sử dụng.

## 24. Kiểm tra bằng request qua proxy

Gọi trực tiếp public URL:

~~~bash
curl -i https://api.example.com/gateway/v3/api-docs
~~~

Lưu spec và kiểm tra server:

~~~bash
curl -fsS https://api.example.com/gateway/v3/api-docs -o openapi.json
jq '.servers' openapi.json
~~~

Nếu ứng dụng được phục vụ qua nhiều host, kiểm tra từng hostname:

~~~bash
curl -fsS https://api.example.com/gateway/v3/api-docs -o public.json
curl -fsS https://internal.example.com/gateway/v3/api-docs -o internal.json
~~~

Nếu server URL cần thay đổi theo request, so sánh trường servers của hai tài liệu. Nếu kết quả giống nhau ngoài dự kiến, kiểm tra cache và nguồn forwarded headers.

Không dùng curl gửi X-Forwarded-* trực tiếp từ Internet để thay thế kiểm tra proxy. Test bằng cách gọi qua proxy thực tế mới chứng minh proxy đã ghi header đúng và backend chỉ tin nguồn phù hợp.

## 25. Kiểm thử forwarded headers bằng WebTestClient

Có thể tạo integration test gửi các forwarded header giả lập tới ứng dụng test đã bật xử lý forwarded headers:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class ForwardedServerUrlTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void usesPublicForwardedServerAddress() {
        webTestClient.get()
            .uri("/v3/api-docs")
            .header("X-Forwarded-Host", "api.example.com")
            .header("X-Forwarded-Proto", "https")
            .header("X-Forwarded-Port", "443")
            .header("X-Forwarded-Prefix", "/gateway")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.servers[0].url")
            .isEqualTo("https://api.example.com/gateway");
    }
}
~~~

Kết quả kỳ vọng phụ thuộc cấu hình context path, proxy rewrite và phiên bản Spring Boot. Nếu prefix không được xử lý trong cấu hình test, hãy kiểm tra property và transformer thay vì sửa assertion cho khớp một URL sai.

Test này xác minh ứng dụng diễn giải forwarded headers. Nó không chứng minh proxy production đã xóa header giả mạo hoặc ghi header đúng. Cần có kiểm tra triển khai qua gateway thật.

## 26. Kiểm thử nhiều request và cache

Nếu cùng một app được gọi qua hai host, có thể tạo test hai request liên tiếp với header khác nhau. Khi yêu cầu URL thay đổi theo từng request, cấu hình cache cần phản ánh điều đó.

| Request | Forwarded host | Kết quả server mong đợi |
|---|---|---|
| Request A | api.example.com | https://api.example.com |
| Request B | partner.example.com | https://partner.example.com |
| Request C | api.example.com | https://api.example.com |

Nếu request B vẫn nhận server URL của request A, kiểm tra springdoc.cache.disabled và cách cache document theo request. Nếu hệ thống chỉ có một public host, không cần tạo biến thể động không cần thiết.

Test cache nên chạy trên application context cấu hình giống production. Không chỉ test một request đầu tiên vì lỗi cache thường chỉ xuất hiện khi có request thứ hai qua host khác.

## 27. Kiểm tra Swagger UI Try it out

Swagger UI sử dụng server URL trong OpenAPI khi gửi request. Sau khi tải tài liệu qua public hostname:

1. Mở Swagger UI bằng URL công khai.
2. Kiểm tra server selector có đúng URL mong muốn không.
3. Chọn một operation GET an toàn.
4. Bấm Try it out và Execute.
5. Mở Network tab của trình duyệt.
6. Xác minh request được gửi tới đúng scheme, host, port và prefix.
7. Kiểm tra response status và lỗi CORS hoặc 404 do path.

Nếu server URL sai, Swagger UI có thể gọi tới địa chỉ nội bộ mà trình duyệt không truy cập được. Nếu URL đúng nhưng request vẫn thất bại, kiểm tra CORS, authentication, API path và proxy routing riêng.

Swagger UI có thể tải tài liệu thành công nhưng Try it out vẫn gọi sai server. Vì vậy, test endpoint /v3/api-docs cần kết hợp với browser test hoặc kiểm tra URL request thực tế.

## 28. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| OpenAPI công bố http nhưng public site dùng https | Thiếu hoặc không xử lý X-Forwarded-Proto |
| Server URL chứa hostname nội bộ | Không xử lý X-Forwarded-Host hoặc khai báo sai server |
| Server URL có port nội bộ | Proxy header hoặc container không phản ánh port public |
| Thiếu prefix /gateway | Proxy chưa gửi X-Forwarded-Prefix hoặc Spring không xử lý |
| Prefix xuất hiện hai lần | Prefix đã có trong request path/context path nhưng lại được cộng thêm |
| Swagger UI gọi localhost | Document được tạo từ request nội bộ hoặc explicit server sai |
| Host thay đổi nhưng servers không đổi | OpenAPI document đang được cache |
| Customizer thay URL sai môi trường | Mapping host hard-code hoặc cấu hình profile không đúng |
| Root server đúng nhưng một operation sai | Path Item hoặc Operation có servers ghi đè |
| Đổi swagger-ui.url nhưng API vẫn gọi sai host | Nhầm URL tải spec với servers[].url |
| Local đúng nhưng production sai | Chưa kiểm tra forwarded headers qua proxy thật |
| Chỉ một proxy hoạt động đúng | Các lớp proxy không thống nhất cách ghi đè forwarded headers |

## 29. Quy trình cấu hình theo môi trường

Khi triển khai, thực hiện theo trình tự:

1. Xác định public URL và base path mà client sử dụng.
2. Xác định request path và host mà backend nhận sau proxy rewrite.
3. Cấu hình proxy ghi đè Forwarded hoặc X-Forwarded-* bằng giá trị đã xác minh.
4. Bật server.forward-headers-strategy phù hợp với container và web stack.
5. Nếu server URL cố định, khai báo servers qua annotation hoặc OpenAPI bean.
6. Nếu server URL thay đổi theo request, để springdoc suy ra từ request đã xử lý forwarded headers.
7. Chỉ dùng ServerBaseUrlCustomizer cho điều chỉnh bổ sung có kiểm soát.
8. Cấu hình cache nếu cùng ứng dụng được truy cập qua nhiều public host.
9. Tải /v3/api-docs qua public URL và kiểm tra servers.
10. Thử Try it out từ Swagger UI và xác minh request URL.
11. Kiểm tra hostname, prefix và forwarded header spoofing trong deployment.

Không trộn nhiều cách ghi đè URL mà không xác định thứ tự ưu tiên. Khi tài liệu có server annotation hoặc OpenAPI bean khai báo tường minh, hãy kiểm tra xem cấu hình đó có chủ ý thay thế server suy ra hay không.

## 30. Checklist

- [ ] Đã xác định server URL lấy từ request hay cấu hình tường minh.
- [ ] Nếu dùng request-derived URL, proxy gửi đúng host, proto và port.
- [ ] Nếu có path rewrite, X-Forwarded-Prefix phản ánh public prefix.
- [ ] Spring Boot xử lý forwarded headers theo web stack.
- [ ] Không tin forwarded headers từ client không đáng tin cậy.
- [ ] Proxy ranh giới xóa hoặc ghi đè Forwarded và X-Forwarded-* từ bên ngoài.
- [ ] Không cộng trùng context path và forwarded prefix.
- [ ] Nếu dùng @OpenAPIDefinition, servers có đúng môi trường.
- [ ] Nếu dùng OpenAPI bean, URL lấy từ property phù hợp.
- [ ] ServerBaseUrlCustomizer chỉ thực hiện điều chỉnh có kiểm soát.
- [ ] Đã kiểm tra cache khi URL cần thay đổi theo request.
- [ ] Đã phân biệt springdoc.swagger-ui.url với servers[].url.
- [ ] Đã kiểm tra servers ở root, path và operation.
- [ ] OpenAPI JSON không lộ hostname hoặc port nội bộ.
- [ ] Swagger UI Try it out gọi đúng URL public.
- [ ] Đã kiểm tra qua proxy thật, không chỉ localhost.
- [ ] Đã test nhiều hostname nếu ứng dụng phục vụ nhiều domain.

## 31. Nguồn tra cứu

- [springdoc-openapi FAQ – Reverse proxy và ServerBaseUrlCustomizer](https://springdoc.org/faq.html)
- [Spring Boot – Embedded Web Servers và forwarded headers](https://docs.spring.io/spring-boot/4.0/how-to/webserver.html)
- [Spring Framework – Forwarded Headers trong Servlet stack](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html)
- [Spring Framework – Forwarded Headers trong WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html)
- [OpenAPI Specification – Server Object](https://spec.openapis.org/oas/latest.html#server-object)
- [RFC 7239 – Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239)

Server URL quyết định địa chỉ mà client và Swagger UI dùng để gọi operation. Khi suy ra từ request, hãy bảo đảm proxy chuyển tiếp đúng scheme, host, port và prefix, đồng thời chỉ tin header từ proxy đáng tin cậy. Khi URL cố định hoặc cần nhiều môi trường, khai báo servers tường minh sẽ dễ kiểm soát hơn. Luôn kiểm tra trường servers trong OpenAPI JSON qua public URL và xác minh request Try it out thực sự đi tới đúng địa chỉ.
