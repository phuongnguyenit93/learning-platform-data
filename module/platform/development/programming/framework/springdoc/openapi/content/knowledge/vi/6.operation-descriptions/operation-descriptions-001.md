# `@OpenAPIDefinition` và thông tin tài liệu ở phạm vi ứng dụng

Một tài liệu OpenAPI cần mô tả API ở cấp tổng thể trước khi đi vào từng endpoint. Người đọc cần biết API tên gì, phiên bản tài liệu nào đang được công bố, ai phụ trách, điều khoản sử dụng ở đâu và client nên gửi request đến server nào. Springdoc cho phép khai báo các thông tin chung này bằng `@OpenAPIDefinition` trong ứng dụng Spring Boot.

`@OpenAPIDefinition` là annotation cấp tài liệu. Nó bổ sung metadata dùng chung cho toàn bộ đặc tả OpenAPI, trong khi `@Operation`, `@Parameter`, `@ApiResponse` và `@Schema` mô tả từng operation hoặc cấu trúc dữ liệu. Khi ứng dụng có giá trị cấu hình thay đổi theo môi trường, có thể tạo bean `OpenAPI` để xây dựng metadata bằng Java và đọc giá trị từ cấu hình Spring.

## 1. `@OpenAPIDefinition` dùng để làm gì?

`@OpenAPIDefinition` là annotation thuộc OpenAPI 3 annotations, nằm trong package `io.swagger.v3.oas.annotations`. Springdoc đọc annotation này để đưa các thông tin cấp ứng dụng vào tài liệu được sinh ra.

Các thuộc tính thường dùng gồm:

| Thuộc tính | Ý nghĩa | Annotation hoặc kiểu dữ liệu |
| --- | --- | --- |
| `info` | Tên, mô tả, phiên bản, liên hệ và giấy phép của API | `@Info` |
| `servers` | Các địa chỉ server mà client có thể gửi request đến | `@Server` |
| `tags` | Metadata tên và mô tả cho các nhóm operation | `@Tag` |
| `externalDocs` | Liên kết đến tài liệu tham khảo bên ngoài | `@ExternalDocumentation` |
| `security` | Yêu cầu bảo mật mặc định cho tài liệu hoặc operation | `@SecurityRequirement` |

Ví dụ, một tài liệu API có thể công bố tên `Books API`, phiên bản tài liệu `1.0.0`, server production và liên kết đến hướng dẫn tích hợp. Những thông tin này giúp người tiêu thụ hiểu bối cảnh của toàn bộ API mà không phải lặp lại trong từng controller.

## 2. Khai báo thông tin chung bằng `@OpenAPIDefinition`

Tạo một lớp cấu hình trong package được Spring Boot quét, ví dụ `com.example.books.config.OpenApiDocumentationConfig`:

```java
package com.example.books.config;

import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Contact;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.info.License;
import io.swagger.v3.oas.annotations.servers.Server;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    info = @Info(
        title = "Books API",
        version = "1.0.0",
        description = "API tra cứu và quản lý thông tin sách",
        termsOfService = "https://example.com/terms",
        contact = @Contact(
            name = "Books API Team",
            url = "https://example.com/support",
            email = "api-support@example.com"
        ),
        license = @License(
            name = "Apache 2.0",
            url = "https://www.apache.org/licenses/LICENSE-2.0.html"
        )
    ),
    servers = {
        @Server(
            url = "https://api.example.com",
            description = "Production server"
        ),
        @Server(
            url = "http://localhost:8080",
            description = "Local development server"
        )
    }
)
public class OpenApiDocumentationConfig {}
```

`@Configuration` giúp Spring phát hiện lớp cấu hình. `@OpenAPIDefinition` khai báo metadata cho toàn bộ tài liệu. `@Info` mô tả API; `@Contact` cung cấp kênh liên hệ; `@License` công bố giấy phép; `@Server` liệt kê các server có thể được Swagger UI dùng làm đích gửi request.

Các URL và email trong ví dụ là địa chỉ minh họa. Khi áp dụng vào dự án, hãy thay bằng thông tin thật đã được nhóm xác nhận. Không công bố server nội bộ hoặc thông tin liên hệ không dành cho người tiêu thụ API.

## 3. Hiểu các trường trong `@Info`

`@Info` là phần metadata quan trọng nhất của tài liệu. Các trường thường được dùng như sau:

| Trường | Mục đích | Cách chọn giá trị |
| --- | --- | --- |
| `title` | Tên hiển thị của API | Tên sản phẩm hoặc dịch vụ dễ nhận biết |
| `version` | Phiên bản hợp đồng/tài liệu được công bố | Giá trị theo quy ước versioning của nhóm |
| `description` | Giải thích phạm vi và khả năng chính của API | Mô tả ngắn gọn đối tượng sử dụng và chức năng |
| `termsOfService` | URL điều khoản sử dụng | Trang điều khoản được công bố chính thức |
| `contact` | Thông tin nhóm hoặc đơn vị hỗ trợ | Tên nhóm, URL hỗ trợ hoặc email đang hoạt động |
| `license` | Thông tin giấy phép của API/tài liệu | Tên giấy phép và URL đến văn bản giấy phép |

Giá trị `info.version` không tự tạo version cho URL endpoint. Ví dụ, đặt `version = "2.0.0"` không làm cho `/api/v1/books` tự đổi thành `/api/v2/books`. Phiên bản tài liệu và chiến lược versioning endpoint là hai quyết định riêng; nhóm phải duy trì chúng nhất quán.

Không nên ghi mô tả quá chung như “API dùng để quản lý dữ liệu”. Một mô tả hữu ích nên cho biết API phục vụ nghiệp vụ nào, ai có thể tích hợp và phạm vi chính của các thao tác. Thông tin liên hệ và license cũng cần phản ánh chính sách thực tế của tổ chức.

## 4. Khai báo server bằng `@Server`

Trường `servers` xác định một hoặc nhiều URL gốc của API. Swagger UI sử dụng danh sách này để xây dựng URL gửi request khi người dùng chọn **Try it out**.

Ví dụ:

```java
servers = {
    @Server(url = "https://api.example.com", description = "Production"),
    @Server(url = "https://staging-api.example.com", description = "Staging")
}
```

Nếu endpoint là `/api/books`, server production ở trên tạo URL request hoàn chỉnh `https://api.example.com/api/books`. Vì vậy, URL server thường là địa chỉ gốc; không lặp lại path của từng operation trong thuộc tính `url`.

Một số lưu ý khi khai báo server:

- Chỉ công bố server mà người đọc tài liệu được phép sử dụng.
- Kiểm tra scheme `https`/`http`, hostname, port và base path.
- Nếu ứng dụng chạy sau reverse proxy hoặc gateway, URL công bố cần phản ánh địa chỉ client thực sự truy cập.
- Server được liệt kê trong OpenAPI không tự cấu hình DNS, TLS, proxy hoặc routing của ứng dụng.
- Nhiều server trong tài liệu tạo lựa chọn cho người dùng Swagger UI; chúng không tự động làm ứng dụng chạy trên tất cả các môi trường đó.

OpenAPI còn hỗ trợ server URL tương đối hoặc URL có biến. Tuy nhiên, với ứng dụng mới, nên bắt đầu bằng URL rõ ràng và xác minh URL cuối cùng mà Swagger UI tạo ra trước khi dùng các mẫu phức tạp.

## 5. Bổ sung tài liệu tham khảo bằng `@ExternalDocumentation`

Khi API có tài liệu nghiệp vụ, hướng dẫn xác thực hoặc quy ước tích hợp ở một trang khác, có thể đưa liên kết đó vào metadata:

```java
import io.swagger.v3.oas.annotations.ExternalDocumentation;
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    externalDocs = @ExternalDocumentation(
        description = "Hướng dẫn tích hợp Books API",
        url = "https://docs.example.com/books-api"
    )
)
public class OpenApiExternalDocsConfig {}
```

`externalDocs` cung cấp liên kết tham khảo ở cấp tài liệu. Đây là đường dẫn để người dùng tiếp tục tìm hiểu; Springdoc không tạo nội dung của trang đó và cũng không kiểm tra quyền truy cập của người đọc. Hãy dùng URL ổn định và đảm bảo trang đích được duy trì.

Nếu tài liệu có liên kết tham khảo riêng cho một schema hoặc operation, OpenAPI cũng có các vị trí hỗ trợ external documentation ở phạm vi tương ứng. Chọn đúng phạm vi để người đọc tìm được thông tin liên quan.

## 6. Công bố yêu cầu bảo mật ở cấp tài liệu

Một API có thể yêu cầu Bearer JWT cho hầu hết operation. Có thể khai báo security scheme và yêu cầu bảo mật mặc định trong tài liệu:

```java
package com.example.books.config;

import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import org.springframework.context.annotation.Configuration;

@Configuration
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
@OpenAPIDefinition(
    security = @SecurityRequirement(name = "bearerAuth")
)
public class OpenApiSecurityDocumentationConfig {}
```

`@SecurityScheme` định nghĩa cách client gửi thông tin xác thực. `@SecurityRequirement` ở cấp `@OpenAPIDefinition` áp dụng yêu cầu đó làm mặc định trong tài liệu. Với endpoint công khai không cần token, có thể mô tả ngoại lệ ở cấp operation theo cấu trúc OpenAPI phù hợp.

Phần khai báo trên chỉ mô tả hợp đồng bảo mật. Nó không cấu hình Spring Security, không xác thực JWT, không cấp token và không bảo vệ endpoint. Ứng dụng vẫn phải triển khai cơ chế xác thực/phân quyền thật; các quy tắc được mô tả trong OpenAPI cần khớp với cơ chế đó.

## 7. Khi nào nên dùng `@OpenAPIDefinition`, khi nào dùng bean `OpenAPI`?

Springdoc cũng hỗ trợ tạo một bean `OpenAPI`. Hai cách tiếp cận phục vụ nhu cầu khác nhau:

| Tiêu chí | `@OpenAPIDefinition` | Bean `OpenAPI` |
| --- | --- | --- |
| Cách khai báo | Annotation và các annotation lồng nhau | Java object model |
| Giá trị cấu hình | Phù hợp với metadata tĩnh được biết khi biên dịch | Có thể đọc từ property, profile hoặc bean Spring |
| Cấu trúc | Ngắn gọn với metadata đơn giản | Linh hoạt khi cần điều kiện hoặc logic xây dựng |
| Thích hợp khi | Tên, mô tả, liên hệ và server ít thay đổi | Server URL, title hoặc version phụ thuộc môi trường |

Ví dụ tạo bean với giá trị đọc từ `application.properties`:

```java
package com.example.books.config;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.servers.Server;
import java.util.List;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiBeanConfig {

    @Bean
    public OpenAPI booksOpenAPI(
            @Value("${api.docs.title:Books API}") String title,
            @Value("${api.docs.version:1.0.0}") String version,
            @Value("${api.docs.server-url:http://localhost:8080}") String serverUrl) {

        return new OpenAPI()
            .info(new Info()
                .title(title)
                .description("API tra cứu và quản lý sách")
                .version(version))
            .servers(List.of(
                new Server()
                    .url(serverUrl)
                    .description("Server của môi trường hiện tại")
            ));
    }
}
```

Trong `application.properties`:

```properties
api.docs.title=Books API
api.docs.version=1.0.0
api.docs.server-url=https://api.example.com
```

Có thể dùng Spring profile hoặc biến môi trường để cung cấp `api.docs.server-url` khác nhau cho local, staging và production. Ví dụ trên sử dụng cú pháp mặc định trong `@Value`, nhờ đó ứng dụng vẫn có giá trị fallback nếu property chưa được khai báo.

Hãy chọn một nguồn quản lý metadata chung và tránh khai báo cùng một trường `info` hoặc `servers` ở nhiều nơi với giá trị mâu thuẫn. Nếu dự án đang dùng cả annotation và bean `OpenAPI`, hãy kiểm tra tài liệu sinh ra để xác định kết quả kết hợp thực tế của phiên bản Springdoc đang dùng; không giả định các giá trị trùng lặp sẽ được ghi đè theo thứ tự mong muốn.

## 8. Ví dụ metadata tương ứng trong OpenAPI YAML

Khi truy cập `/v3/api-docs.yaml` (nếu ứng dụng đã bật endpoint YAML), các metadata đã khai báo sẽ được biểu diễn ở cấp tài liệu. Ví dụ rút gọn:

```yaml
openapi: 3.0.3
info:
  title: Books API
  version: 1.0.0
  description: API tra cứu và quản lý thông tin sách
  termsOfService: https://example.com/terms
  contact:
    name: Books API Team
    url: https://example.com/support
    email: api-support@example.com
  license:
    name: Apache 2.0
    url: https://www.apache.org/licenses/LICENSE-2.0.html
servers:
  - url: https://api.example.com
    description: Production server
externalDocs:
  description: Hướng dẫn tích hợp Books API
  url: https://docs.example.com/books-api
```

Đây là cấu trúc minh họa để nhận biết vị trí metadata, không phải bản sao đầy đủ được bảo đảm giống hệt đầu ra của mọi phiên bản Springdoc. Phiên bản OpenAPI, thứ tự field và các thành phần khác có thể thay đổi theo cấu hình và phiên bản thư viện.

## 9. Kiểm tra metadata đã được Springdoc sinh ra

Sau khi khởi chạy ứng dụng, mở các endpoint tài liệu thường dùng:

| URL mặc định | Nội dung |
| --- | --- |
| `/v3/api-docs` | Đặc tả OpenAPI dạng JSON |
| `/v3/api-docs.yaml` | Đặc tả OpenAPI dạng YAML |
| `/swagger-ui/index.html` | Giao diện Swagger UI |

Trong JSON hoặc YAML, kiểm tra các trường sau:

1. `info.title`, `info.version` và `info.description` có đúng giá trị mong muốn.
2. `info.contact` và `info.license` có thông tin chính xác, URL có thể truy cập.
3. `servers` có hostname, scheme và base path phù hợp với môi trường.
4. `externalDocs` trỏ đến trang tài liệu đúng.
5. `components.securitySchemes` chứa security scheme được khai báo; `security` thể hiện đúng yêu cầu mặc định.
6. Các operation và schema vẫn được tạo như trước khi bổ sung metadata cấp tài liệu.

Trong Swagger UI, kiểm tra tên API, mô tả, danh sách server và nút **Authorize** nếu tài liệu có security scheme. Nếu Swagger UI gửi request đến sai hostname, hãy kiểm tra `servers` trong đặc tả trước khi sửa cấu hình proxy hoặc controller.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Không thấy title hoặc description | Lớp chứa `@OpenAPIDefinition` chưa được component scan phát hiện hoặc có cấu hình khác tạo metadata | Kiểm tra package scan và JSON `/v3/api-docs` |
| Thông tin liên hệ hoặc license bị thiếu | Chưa khai báo trong `@Info` hoặc đang xem nhầm tài liệu/group | Kiểm tra `info.contact`, `info.license` và group đang mở |
| Swagger UI gửi request đến server sai | `@Server` chứa URL cũ hoặc base path không đúng | Kiểm tra mảng `servers` trong JSON/YAML |
| Server local xuất hiện trong tài liệu production | Metadata tĩnh liệt kê nhiều môi trường hoặc cấu hình không tách theo profile | Dùng bean `OpenAPI` với property theo môi trường hoặc công bố đúng server cần thiết |
| Nút Authorize không xuất hiện | Chưa khai báo security scheme hoặc UI đang tải tài liệu khác | Kiểm tra `components.securitySchemes` và URL tài liệu UI tải |
| Tài liệu thể hiện yêu cầu Bearer nhưng endpoint vẫn truy cập không token | Chỉ khai báo metadata OpenAPI mà chưa cấu hình Spring Security | Kiểm tra filter chain và test request thực tế |
| Metadata khác với cấu hình mong đợi | Annotation và bean OpenAPI cùng khai báo các giá trị trùng lặp | Chọn nguồn cấu hình chính và kiểm tra kết quả sinh ra |

Nếu dùng nhiều group, mỗi group có thể có tài liệu riêng. Hãy kiểm tra đúng URL `/v3/api-docs/{group}` thay vì chỉ xem tài liệu mặc định. Nếu ứng dụng đổi `springdoc.api-docs.path` hoặc có context path, endpoint kiểm tra cũng cần được điều chỉnh tương ứng.

## 11. Checklist cho metadata cấp ứng dụng

- [ ] Đã khai báo `@OpenAPIDefinition` trong package được Spring Boot quét hoặc tạo bean `OpenAPI` phù hợp.
- [ ] `info.title`, `info.version` và `info.description` mô tả đúng API.
- [ ] Contact và license dùng thông tin được phép công bố.
- [ ] Server URL phản ánh đúng địa chỉ client truy cập trong môi trường tương ứng.
- [ ] Liên kết `externalDocs` ổn định và trỏ đến tài liệu phù hợp.
- [ ] Security scheme và security requirement trong OpenAPI khớp với cơ chế bảo mật thực tế.
- [ ] Không nhầm `info.version` với version của URL endpoint.
- [ ] Không khai báo metadata trùng lặp hoặc mâu thuẫn giữa annotation và bean.
- [ ] Đã kiểm tra JSON/YAML và Swagger UI sau khi thay đổi cấu hình.

`@OpenAPIDefinition` giúp tập trung thông tin chung của hợp đồng API tại phạm vi ứng dụng. Khi metadata cần thay đổi theo môi trường, bean `OpenAPI` kết hợp cấu hình Spring mang lại sự linh hoạt. Dù chọn cách nào, hãy xác minh đặc tả được sinh ra và bảo đảm server, liên hệ, phiên bản cùng yêu cầu bảo mật phản ánh đúng cách API đang được vận hành.
