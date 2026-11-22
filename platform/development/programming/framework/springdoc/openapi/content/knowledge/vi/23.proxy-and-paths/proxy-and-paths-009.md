# ServerBaseUrlCustomizer khi cần điều chỉnh URL sinh ra

Khi chạy Spring Boot trực tiếp, springdoc-openapi có thể suy ra server URL từ request gọi tài liệu. Nhưng khi ứng dụng nằm sau reverse proxy, ingress hoặc API gateway, request mà ứng dụng nhận được có thể mang scheme, host, port và path khác với URL mà client bên ngoài sử dụng. Khi đó Swagger UI có thể hiển thị server URL nội bộ hoặc gửi request Try it out sai địa chỉ.

Nên để proxy chuyển tiếp thông tin URL gốc qua các forwarded headers và cấu hình Spring Boot xử lý chúng trước. `ServerBaseUrlCustomizer` là điểm mở rộng của springdoc để tinh chỉnh chuỗi base URL đã được tính toán, ví dụ loại một port không nên xuất hiện trên tài liệu. Nó không thay thế việc cấu hình reverse proxy, context path hay bảo vệ forwarded headers.

Bài học này tập trung vào lúc nào nên dùng `ServerBaseUrlCustomizer`, cách viết customizer an toàn, cách xử lý forwarded headers, cache tài liệu và kiểm tra server URL cuối cùng trong OpenAPI JSON.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích cách springdoc suy ra server URL từ request.
- Nhận diện sai lệch scheme, host, port và path khi chạy sau proxy.
- Phân biệt forwarded-header handling với `ServerBaseUrlCustomizer`.
- Cấu hình `server.forward-headers-strategy` cho servlet hoặc reactive stack.
- Viết bean `ServerBaseUrlCustomizer` để chỉnh URL đã sinh có điều kiện.
- Biết khi nào nên khai báo `servers` tĩnh bằng OpenAPI annotation hoặc bean.
- Xử lý context path và `X-Forwarded-Prefix` mà không nhân đôi path.
- Hiểu tác động của cache khi tài liệu được truy cập qua nhiều hostname.
- Bảo vệ ứng dụng khỏi forwarded headers do client không tin cậy tự gửi.
- Kiểm tra URL trong Swagger UI và `/v3/api-docs`.

## 1. Server URL được dùng ở đâu?

Trong OpenAPI, `servers` xác định địa chỉ gốc để client gọi các path được mô tả. Ví dụ một operation có path `/api/products`, còn server URL là `https://api.example.com/catalog`, thì URL gọi hoàn chỉnh là:

~~~text
https://api.example.com/catalog/api/products
~~~

Swagger UI dùng server URL để tạo request khi người dùng nhấn Try it out. Các SDK generator và công cụ tích hợp cũng có thể dùng danh sách server này để cấu hình base URL.

Nếu `servers` chứa địa chỉ nội bộ như `http://product-service:8080`, client bên ngoài có thể không truy cập được. Nếu scheme bị sinh thành `http` trong khi gateway public dùng `https`, browser có thể chặn request mixed content hoặc client gửi request sai giao thức. Nếu thiếu path prefix của gateway, request có thể đi vào route không tồn tại.

### Ví dụ kiến trúc

~~~text
Client
  |
  | https://api.example.com/catalog
  v
Reverse proxy / API Gateway
  |
  | http://product-service:8080
  v
Spring Boot + springdoc-openapi
~~~

Client chỉ nhìn thấy `https://api.example.com/catalog`. Ứng dụng Spring Boot nhận kết nối nội bộ từ proxy tại `product-service:8080`. Nếu không có forwarded-header handling, request URL mà springdoc nhìn thấy có thể phản ánh địa chỉ nội bộ.

Mục tiêu là tài liệu công bố server URL mà client thực sự dùng được:

~~~yaml
servers:
  - url: https://api.example.com/catalog
~~~

## 2. Cách springdoc tạo server URL

Khi không khai báo server URL rõ ràng, springdoc có thể tự tạo base URL từ request đến endpoint tài liệu. Với Web MVC, endpoint JSON mặc định là `/v3/api-docs`; YAML mặc định là `/v3/api-docs.yaml`. Phần base URL được suy ra từ request URL sau khi loại phần path dành cho endpoint tài liệu và các phần path nội bộ mà springdoc biết.

Ví dụ request đến:

~~~text
http://localhost:8080/store/v3/api-docs
~~~

có thể tạo base URL:

~~~text
http://localhost:8080/store
~~~

Nếu request đi qua proxy nhưng ứng dụng không nhận biết URL gốc, base URL có thể chứa:

- `http` thay vì `https`.
- Host nội bộ hoặc địa chỉ IP của container.
- Port nội bộ như `8080`.
- Thiếu prefix public như `/catalog`.
- Context path bị thiếu hoặc bị lặp.

### Khi đã khai báo servers tường minh

Nếu OpenAPI có server được khai báo bằng `@OpenAPIDefinition(servers = ...)`, `@Server` hoặc OpenAPI bean, springdoc dùng server đã khai báo thay cho server URL tự sinh. Khi muốn một địa chỉ cố định cho mọi request, hãy khai báo server tĩnh ngay trong OpenAPI definition.

Ví dụ:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.servers.Server;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    servers = {
        @Server(
            url = "https://api.example.com/catalog",
            description = "Public API"
        )
    }
)
class PublicApiDefinition {
}
~~~

Địa chỉ trong ví dụ là URL minh họa. Khi phát hành, thay bằng public URL đã được chủ sở hữu API phê duyệt. Với cấu hình server cố định, không cần `ServerBaseUrlCustomizer` chỉ để tạo lại cùng URL đó.

## 3. Forwarded headers giải quyết phần nào?

Reverse proxy có thể truyền URL gốc trong header chuẩn `Forwarded` theo RFC 7239 hoặc các header phổ biến dạng `X-Forwarded-*`.

| Header | Thông tin |
|---|---|
| `Forwarded` | Có thể mang `proto`, `host` và thông tin node theo RFC 7239 |
| `X-Forwarded-Host` | Host mà client bên ngoài đã gọi |
| `X-Forwarded-Proto` | Scheme bên ngoài, thường là `https` |
| `X-Forwarded-Port` | Port bên ngoài, ví dụ `443` |
| `X-Forwarded-Prefix` | Path prefix public mà proxy đã loại khỏi request trước khi chuyển tiếp |
| `X-Forwarded-For` | Địa chỉ IP của client hoặc chuỗi proxy; không phải host của API |

Spring Boot cần được cấu hình để đọc các header này. Khi chúng được xử lý đúng, request mà Spring nhìn thấy sẽ phản ánh URL bên ngoài tốt hơn; springdoc sau đó có thể tạo server URL phù hợp mà không cần tự phân tích header.

### Chọn chiến lược forwarded headers

Với Spring Boot 3, cấu hình thường dùng là:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Các giá trị chính:

| Giá trị | Hành vi |
|---|---|
| `NONE` | Bỏ qua forwarded headers |
| `NATIVE` | Dùng khả năng xử lý forwarded headers của web server/container |
| `FRAMEWORK` | Dùng cơ chế của Spring Framework |

`NATIVE` có thể đủ nếu container xử lý đúng những header mà proxy gửi. Khi cần hỗ trợ `X-Forwarded-Prefix` hoặc hành vi không được container hỗ trợ, `FRAMEWORK` dùng `ForwardedHeaderFilter` cho servlet stack và `ForwardedHeaderTransformer` cho WebFlux stack.

Thông thường chỉ cần cấu hình `server.forward-headers-strategy`; Spring Boot sẽ đăng ký cơ chế tương ứng. Tránh tự đăng ký thêm một `ForwardedHeaderFilter` trùng lặp khi auto-configuration đã xử lý forwarded headers.

### Xác định header nào thực sự cần

Nếu chỉ sai scheme hoặc host, kiểm tra `Forwarded` hoặc cặp `X-Forwarded-Proto`/`X-Forwarded-Host`. Nếu chỉ sai port, kiểm tra `X-Forwarded-Port`. Nếu URL có đúng host nhưng thiếu path của gateway, kiểm tra `X-Forwarded-Prefix`.

Không dùng `X-Forwarded-For` để sửa server URL. Header này dành cho địa chỉ client, không xác định hostname mà Swagger UI cần gọi.

## 4. Cấu hình proxy để truyền URL gốc

Ứng dụng chỉ có thể xử lý đúng thông tin mà proxy gửi. Proxy cần đặt forwarded headers theo request public và loại bỏ các giá trị giả do client gửi từ trước.

Ví dụ cấu hình Nginx khi public prefix `/catalog` bị loại trước khi chuyển đến ứng dụng:

~~~nginx
location /catalog/ {
    proxy_pass http://product-service:8080/;

    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Port $server_port;
    proxy_set_header X-Forwarded-Prefix /catalog;
}
~~~

Với cấu hình `proxy_pass` có dấu `/` ở cuối trong ví dụ, phần prefix của location được loại khỏi path chuyển tiếp. `X-Forwarded-Prefix: /catalog` cho Spring biết prefix public cần xuất hiện lại trong URL.

Tên service và cấu hình proxy ở đây chỉ để minh họa. Hãy điều chỉnh theo gateway thực tế, đặc biệt khi có nhiều proxy nối tiếp hoặc gateway không loại path prefix.

### Proxy phải ghi đè header từ client

Không để client Internet tự quyết định `Forwarded`, `X-Forwarded-Host`, `X-Forwarded-Proto`, `X-Forwarded-Port` hoặc `X-Forwarded-Prefix` mà ứng dụng tin cậy. Proxy biên cần xóa hoặc ghi đè các giá trị không đáng tin cậy rồi tạo header mới từ request mà nó xác minh được.

Nếu ứng dụng có thể được truy cập trực tiếp bỏ qua proxy, người gọi có thể tự gửi forwarded headers để làm server URL sinh ra trỏ tới host hoặc scheme khác. Chỉ bật forwarded-header handling khi đường truy cập và proxy tin cậy đã được kiểm soát.

## 5. Context path và forwarded prefix

`server.servlet.context-path` là context path của chính ứng dụng Spring Boot. `X-Forwarded-Prefix` mô tả prefix public bị proxy loại bỏ trước khi request đến ứng dụng. Hai giá trị này đại diện cho hai lớp path khác nhau.

Ví dụ:

- Public URL: `https://api.example.com/gateway/catalog`.
- Gateway loại `/gateway` trước khi chuyển tiếp.
- Ứng dụng có context path `/catalog`.
- Request nội bộ đến ứng dụng giữ context path `/catalog`.

Khi đó server URL public cần chứa cả `/gateway/catalog`, nếu proxy thực sự route theo cấu trúc này. Hãy kiểm tra URL thực tế mà client gọi và path request sau khi qua từng lớp.

### Tránh lặp prefix

Nếu proxy không loại prefix `/catalog` nhưng vẫn gửi `X-Forwarded-Prefix: /catalog`, Spring có thể ghép prefix vào một path vốn đã có prefix và tạo kết quả lặp như `/catalog/catalog`.

Ngược lại, nếu proxy đã loại prefix nhưng không gửi `X-Forwarded-Prefix`, tài liệu có thể thiếu đoạn `/catalog`.

Không sửa bằng cách thêm chuỗi path một cách vô điều kiện trong customizer trước khi xác định proxy đang giữ hay loại prefix. Hãy xác định path tại từng chặng và chỉ có một nơi chịu trách nhiệm thêm lại prefix đã bị loại.

## 6. ServerBaseUrlCustomizer là gì?

`ServerBaseUrlCustomizer` là interface của springdoc dùng để điều chỉnh chuỗi base URL mà springdoc đã tính toán trước khi đưa vào tài liệu. Interface có phương thức:

~~~java
String customize(String serverBaseUrl);
~~~

Tham số là chuỗi URL đã sinh. Phương thức trả về URL sau khi chỉnh sửa. Có thể dùng nó để loại port không cần công bố, chuẩn hóa một host đã biết hoặc sửa một phần URL có quy tắc rõ ràng.

Package của interface trong springdoc-openapi v2:

~~~java
import org.springdoc.core.customizers.ServerBaseUrlCustomizer;
~~~

Ví dụ dưới đây chỉ loại port `8080` khi scheme và host khớp chính xác với public endpoint đã định. Path được giữ nguyên:

~~~java
import java.net.URI;

import org.springdoc.core.customizers.ServerBaseUrlCustomizer;
import org.springframework.stereotype.Component;
import org.springframework.web.util.UriComponentsBuilder;

@Component
public class PublicServerBaseUrlCustomizer
        implements ServerBaseUrlCustomizer {

    @Override
    public String customize(String serverBaseUrl) {
        try {
            URI uri = URI.create(serverBaseUrl);

            boolean expectedPublicHost =
                "https".equalsIgnoreCase(uri.getScheme())
                && "api.example.com".equalsIgnoreCase(uri.getHost());

            if (expectedPublicHost && uri.getPort() == 8080) {
                return UriComponentsBuilder.fromUri(uri)
                    .port(-1)
                    .build(true)
                    .toUriString();
            }
        } catch (IllegalArgumentException ex) {
            // Giữ nguyên giá trị sinh ra nếu không phân tích được URL.
        }

        return serverBaseUrl;
    }
}
~~~

Ví dụ giả định ứng dụng đã nhận được host public đúng là `api.example.com`, nhưng base URL vẫn chứa port nội bộ `8080`. Customizer loại port đó và giữ scheme, host, context path cùng phần path hiện có. Thay host ví dụ và port bằng giá trị được xác nhận trong kiến trúc thực tế.

`UriComponentsBuilder.fromUri(uri).port(-1)` loại port. Không dùng thao tác này nếu port là một phần của public endpoint, ví dụ public API thực sự chạy trên `8443`.

Ví dụ giữ nguyên chuỗi ban đầu nếu URI không phân tích được để minh họa phép biến đổi có điều kiện. Với policy phát hành nghiêm ngặt, có thể ném exception và chặn tạo tài liệu khi URL không hợp lệ thay vì tiếp tục với giá trị không xác định.

### Đăng ký bằng @Bean

Nếu không muốn dùng `@Component`, có thể đăng ký interface qua một bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiServerConfiguration {

    @Bean
    ServerBaseUrlCustomizer serverBaseUrlCustomizer() {
        return new PublicServerBaseUrlCustomizer();
    }
}
~~~

Khi dùng cách `@Bean` này, bỏ `@Component` khỏi class `PublicServerBaseUrlCustomizer` ở ví dụ trước. Chọn một cách đăng ký để tránh tạo nhiều customizer cùng sửa một URL. Nếu có nhiều customizer, xác định thứ tự và bảo đảm các phép biến đổi không mâu thuẫn.

## 7. Khi nào nên dùng ServerBaseUrlCustomizer?

Nên cân nhắc interface này khi:

- URL đã được tạo gần đúng nhưng cần bỏ một port nội bộ không nên công bố.
- Một hostname public cụ thể cần chuẩn hóa theo quy tắc ổn định.
- Một phần URL sinh ra cần sửa có điều kiện dựa trên chính chuỗi base URL.
- Không thể giải quyết phần sai lệch chỉ bằng forwarded-header handling hoặc cấu hình server của ứng dụng.

Ví dụ, proxy gửi đúng `X-Forwarded-Host` và `X-Forwarded-Proto`, nhưng container vẫn đưa một port không mong muốn vào URL. Customizer có thể loại đúng port đó khi host khớp allowlist.

### Khi không cần dùng customizer

Không cần `ServerBaseUrlCustomizer` nếu:

- Forwarded headers đã được proxy gửi đúng và Spring xử lý đúng.
- Context path và `X-Forwarded-Prefix` đã được cấu hình chính xác.
- Ứng dụng luôn dùng một public base URL cố định; khi đó khai báo `servers` rõ ràng.
- Server URL sai vì proxy route sai hoặc ứng dụng có context path sai.
- Swagger UI trỏ đến sai OpenAPI document URL; đây là cấu hình Swagger UI, không phải server base URL.

Không dùng customizer để che lỗi định tuyến ở gateway. URL xuất hiện trong OpenAPI có thể đúng nhưng gateway vẫn không route request đến ứng dụng.

## 8. Giới hạn của ServerBaseUrlCustomizer

Phương thức `customize` chỉ nhận một chuỗi `serverBaseUrl`. Nó không nhận `HttpServletRequest`, `ServerHttpRequest` hoặc danh sách request headers. Vì vậy:

- Không thể đọc trực tiếp `X-Forwarded-Prefix` từ tham số của interface.
- Không nên tiêm request-scoped object vào singleton customizer.
- Không dùng `ThreadLocal` để truyền request context vào customizer.
- Không giả định customizer có thể quyết định URL dựa trên user, tenant hoặc gateway header tùy request.

Nếu giá trị cần thiết nằm trong forwarded headers, hãy để Spring xử lý forwarded headers trước khi springdoc tính URL. Nếu server URL cố định theo audience hoặc group, khai báo trong OpenAPI definition hoặc dùng customizer cấp OpenAPI cho group tương ứng.

### Đừng thêm prefix mù quáng

Đoạn mã sau dễ gây lỗi nếu request đã chứa prefix:

~~~java
return serverBaseUrl + "/catalog";
~~~

Kết quả có thể lặp `/catalog/catalog`, thiếu dấu `/`, hoặc làm sai URL có context path khác. Nếu cần sửa path, hãy parse URI, kiểm tra path hiện tại và chỉ thêm khi prefix chưa tồn tại. Tuy nhiên, với proxy strip-prefix, ưu tiên `X-Forwarded-Prefix` và forwarded-header strategy.

### Đừng thay host dựa trên mọi request đầu vào

Không lấy `Host` hoặc `X-Forwarded-Host` từ request bất kỳ rồi thay trực tiếp vào OpenAPI URL nếu proxy chưa được tin cậy. Điều đó có thể khiến tài liệu phát ra hostname do người gọi tự chọn. Dùng proxy allowlist và kiểm tra host public được phép.

## 9. ServerBaseUrlCustomizer và OpenAPI servers tĩnh

Hai cách cấu hình giải quyết hai mục tiêu khác nhau:

| Cách | Phạm vi | Khi phù hợp |
|---|---|---|
| `ServerBaseUrlCustomizer` | Điều chỉnh base URL tự sinh từ request | URL sinh ra gần đúng, cần một phép biến đổi nhỏ |
| `@OpenAPIDefinition(servers = ...)` | Khai báo server cố định trong OpenAPI | Public URL không thay đổi theo request |
| OpenAPI bean | Xây dựng server list bằng Java | Cần đọc cấu hình deployment hoặc tạo danh sách server |
| `GroupedOpenApi` + `OpenApiCustomizer` | Điều chỉnh server theo group | Public, partner và internal có base URL khác nhau |
| Forwarded headers | Khôi phục thông tin URL gốc từ proxy | Sai scheme, host, port hoặc prefix do proxy |

Ví dụ một group có server cố định:

~~~java
import java.util.List;

import io.swagger.v3.oas.models.servers.Server;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiGroupConfiguration {

@Bean
GroupedOpenApi partnerApi() {
    return GroupedOpenApi.builder()
        .group("partner")
        .pathsToMatch("/api/partner/**")
        .addOpenApiCustomizer(openApi ->
            openApi.setServers(List.of(
                new Server().url("https://partner-api.example.com")
            ))
        )
        .build();
}
}
~~~

Server list trong ví dụ được gắn cho group partner. Không giả định một `ServerBaseUrlCustomizer` có thể phân biệt group, audience hoặc tenant; interface của nó chỉ nhận chuỗi base URL.

## 10. Cache OpenAPI khi URL thay đổi theo request

Theo mặc định, springdoc tính toán OpenAPI description và cache kết quả. Điều này phù hợp khi server URL giống nhau cho mọi request.

Một số hệ thống phục vụ cùng Swagger UI qua cả proxy nội bộ và proxy bên ngoài. Hai request có thể có hostname hoặc scheme khác nhau. Nếu tài liệu được cache sau request đầu tiên, request tiếp theo có thể nhận server URL của request trước.

Khi thực sự cần tính lại tài liệu cho mỗi request, có thể tắt cache:

~~~yaml
springdoc:
  cache:
    disabled: true
~~~

Tắt cache làm tăng chi phí tạo tài liệu. Chỉ bật khi server URL thật sự phụ thuộc request và đã đo tác động. Nếu public base URL luôn cố định, hãy khai báo một server URL cố định thay vì tắt cache.

Cache không sửa được forwarded headers sai. Nếu proxy gửi host hoặc prefix sai, mỗi lần tạo lại tài liệu vẫn cho URL sai.

## 11. Kiểm thử server URL

Hãy kiểm tra URL cuối cùng từ endpoint OpenAPI thay vì chỉ kiểm tra code customizer. Kết quả mong đợi cần bao gồm scheme, host, port và path.

### Kiểm tra với MockMvc và forwarded headers

Ví dụ test khi ứng dụng dùng `server.forward-headers-strategy=framework`:

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
class OpenApiForwardedUrlTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void usesExternalSchemeHostAndPrefix() throws Exception {
        mockMvc.perform(get("/v3/api-docs")
                .header("Forwarded", "proto=https;host=api.example.com")
                .header("X-Forwarded-Prefix", "/catalog"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.servers[0].url")
                .value("https://api.example.com/catalog"));
    }
}
~~~

Đây là ví dụ cho servlet stack; cần nạp cấu hình ứng dụng và các filter như trong môi trường thực. Nếu proxy giữ prefix trong request path thay vì strip-prefix, điều chỉnh header và assertion theo đúng cách route thực tế.

### Unit test cho customizer

Có thể kiểm tra riêng quy tắc bỏ port:

~~~java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class PublicServerBaseUrlCustomizerTest {

    private final PublicServerBaseUrlCustomizer customizer =
        new PublicServerBaseUrlCustomizer();

    @Test
    void removesOnlyTheExpectedInternalPort() {
        String result = customizer.customize(
            "https://api.example.com:8080/catalog"
        );

        assertEquals(
            "https://api.example.com/catalog",
            result
        );
    }

    @Test
    void keepsPortForAnotherHost() {
        String input = "https://internal.example.net:8080/catalog";

        assertEquals(input, customizer.customize(input));
    }
}
~~~

Test thứ nhất xác minh port chỉ bị loại khi host và port khớp quy tắc. Test thứ hai bảo đảm customizer không sửa một host khác.

### Kiểm tra thủ công

Sau khi chạy ứng dụng:

1. Truy cập `/v3/api-docs` từ đường public qua proxy.
2. Kiểm tra `servers[0].url` trong JSON.
3. Mở Swagger UI và xác minh server được hiển thị.
4. Dùng Try it out với một endpoint đọc an toàn để xác nhận request đi qua gateway public.
5. Thử YAML tại `/v3/api-docs.yaml` nếu ứng dụng phát hành cả hai định dạng.
6. Kiểm tra cả truy cập nội bộ và bên ngoài nếu chúng là hai audience được hỗ trợ.

Không chỉ kiểm tra trang Swagger UI tải thành công; UI có thể tải được nhưng server URL bên trong OpenAPI vẫn sai.

## 12. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Swagger UI hiển thị `http` thay vì `https` | Thiếu hoặc không xử lý `X-Forwarded-Proto`/`Forwarded` | Kiểm tra proxy và `server.forward-headers-strategy` |
| Host là tên service hoặc IP nội bộ | Thiếu `X-Forwarded-Host` hoặc `Forwarded host` | Xác minh header proxy gửi đến ứng dụng |
| URL có port `8080` | Proxy không gửi port public hoặc container tạo URL nội bộ | Kiểm tra `X-Forwarded-Port`, sau đó cân nhắc customizer có điều kiện |
| URL thiếu `/catalog` | Proxy strip prefix nhưng không gửi `X-Forwarded-Prefix` | Cấu hình proxy và framework forwarded-header handling |
| URL có `/catalog/catalog` | Prefix đã tồn tại trong path nhưng lại được thêm lần nữa | Xác định proxy có strip prefix hay không |
| URL có context path bị lặp | Context path ứng dụng và proxy prefix bị cấu hình trùng | So sánh path ở public request và upstream request |
| Chỉ request đầu tiên cho URL đúng | OpenAPI cache giữ server URL của request trước | Xem xét `springdoc.cache.disabled` nếu URL phải phụ thuộc request |
| Customizer không thay đổi URL | OpenAPI đã khai báo server tĩnh hoặc customizer không được đăng ký thành bean | Kiểm tra `servers` annotation/bean và Spring context |
| URL bị thay sai ở mọi môi trường | Customizer sửa mọi host/port mà không kiểm tra điều kiện | Giới hạn theo scheme, host và port chính xác |
| Swagger UI tải được nhưng Try it out lỗi | Server URL hoặc gateway route sai; CORS hoặc auth có thể không phù hợp | Kiểm tra `servers`, network request, gateway và CORS |

### Quy trình điều tra theo thứ tự

1. Ghi lại URL public mà browser gọi endpoint `/v3/api-docs`.
2. Ghi lại URL upstream mà proxy gửi đến ứng dụng.
3. Kiểm tra các forwarded headers mà proxy thực sự gửi.
4. Xác nhận Spring Boot đã xử lý các header đó.
5. Đọc `servers` trong OpenAPI JSON.
6. Nếu URL vẫn sai, xác định phần sai thuộc scheme, host, port hay path.
7. Chỉ thêm `ServerBaseUrlCustomizer` nếu phần sai là một biến đổi URL có quy tắc rõ.
8. Kiểm tra lại cache và gọi endpoint qua đúng proxy.

## 13. Bảo mật forwarded headers

Forwarded headers có thể làm thay đổi cách ứng dụng diễn giải URL gốc. Nếu ứng dụng tin header do client không đáng tin cậy gửi, người gọi có thể giả mạo host, scheme hoặc prefix.

Áp dụng các nguyên tắc:

- Chỉ tin forwarded headers từ reverse proxy hoặc load balancer đã được kiểm soát.
- Proxy biên phải xóa hoặc ghi đè giá trị do client tự gửi.
- Không để endpoint nội bộ có thể bị gọi trực tiếp từ mạng không tin cậy nếu ứng dụng đang tin forwarded headers.
- Giới hạn danh sách proxy tin cậy theo cấu hình web server/container khi dùng native strategy.
- Không phản chiếu host tùy ý vào OpenAPI hoặc redirect.
- Chỉ cho phép public host hợp lệ; customizer có thể kiểm tra allowlist nhưng không thay cấu hình proxy trust.
- Không log toàn bộ URL nếu query string có thể chứa credential.

`ServerBaseUrlCustomizer` nên là phép biến đổi thuần, có điều kiện rõ ràng và không phụ thuộc trạng thái mutable dùng chung. Tránh lưu URL của request trước trong field của singleton bean.

## 14. Bài thực hành tổng hợp

Triển khai một Spring Boot API phía sau reverse proxy có public URL:

~~~text
https://api.example.com/catalog
~~~

Proxy chuyển request đến ứng dụng ở địa chỉ nội bộ và loại prefix `/catalog` trước khi chuyển tiếp. Thực hiện:

1. Xác định public URL, upstream URL, context path và path prefix bị loại.
2. Cấu hình proxy gửi `X-Forwarded-Host`, `X-Forwarded-Proto`, `X-Forwarded-Port` và `X-Forwarded-Prefix`.
3. Cấu hình `server.forward-headers-strategy=framework`.
4. Gọi `/v3/api-docs` qua proxy và xác minh server URL.
5. Nếu chỉ còn port nội bộ sai, tạo `ServerBaseUrlCustomizer` chỉ loại port cho đúng public host.
6. Tạo test unit cho customizer với URL đúng host, host khác, scheme khác và port khác.
7. Tạo MockMvc integration test kiểm tra `Forwarded` cùng `X-Forwarded-Prefix`.
8. Mở Swagger UI và dùng Try it out để xác minh request đi qua public gateway.
9. Thử gọi tài liệu qua đường nội bộ nếu môi trường hỗ trợ và xác minh hành vi cache.
10. Bật cache lại nếu public server URL cố định; chỉ tắt cache nếu URL phải được tính theo request.
11. Thử gửi forwarded header giả từ client và xác minh proxy biên ghi đè nó.
12. Ghi lại quy tắc host/port/path được phép để người vận hành có thể kiểm tra khi triển khai.

### Tiêu chí hoàn thành

- [ ] Phân biệt được server URL tự sinh và server khai báo tĩnh.
- [ ] Xác định được header cần thiết cho scheme, host, port và prefix.
- [ ] Spring Boot xử lý forwarded headers theo chiến lược phù hợp.
- [ ] `X-Forwarded-Prefix` được cấu hình đúng khi proxy strip path.
- [ ] Không bị lặp context path hoặc gateway prefix.
- [ ] `ServerBaseUrlCustomizer` chỉ thay đổi host/port/path đã được xác định.
- [ ] URL của host khác hoặc môi trường khác không bị thay đổi ngoài ý muốn.
- [ ] Cache được cấu hình theo việc URL có thay đổi giữa các request hay không.
- [ ] `/v3/api-docs` và Swagger UI hiển thị cùng server URL mong muốn.
- [ ] Proxy loại bỏ hoặc ghi đè forwarded headers không đáng tin cậy.
- [ ] Có unit test và integration test cho URL sau proxy.

## Tiếp tục học

Sau bài này, hãy kết hợp forwarded headers với context path, gateway route, grouped documentation và kiểm thử triển khai. Khi URL sinh ra không đúng, hãy xác định chính xác lớp gây sai lệch trước khi thêm customizer; một base URL đúng cần phản ánh cùng lúc scheme, host, port và path mà client thực sự sử dụng.

## Tài liệu tham khảo

- [springdoc-openapi v2 – FAQ: triển khai sau reverse proxy](https://springdoc.org/v2/)
- [Spring Boot 3.5 – Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html)
- [Spring Boot – ForwardHeadersStrategy](https://docs.spring.io/spring-boot/docs/3.2.x/api/org/springframework/boot/autoconfigure/web/ServerProperties.ForwardHeadersStrategy.html)
- [RFC 7239 – Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239)
