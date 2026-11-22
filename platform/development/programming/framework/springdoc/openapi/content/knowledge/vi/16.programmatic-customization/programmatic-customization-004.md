# `GlobalOpenApiCustomizer` khi cần tác động các tài liệu nhóm

Một ứng dụng Spring Boot có thể xuất nhiều tài liệu OpenAPI: tài liệu mặc định và các tài liệu được tạo từ `GroupedOpenApi`. Khi cần bổ sung cùng một metadata cho tất cả tài liệu, chẳng hạn thông tin liên hệ, server chung, extension hoặc security scheme dùng chung, việc viết một customizer riêng cho từng nhóm sẽ tạo ra cấu hình lặp và dễ lệch nhau.

Springdoc-openapi cung cấp `GlobalOpenApiCustomizer` để tùy biến mô hình OpenAPI trên phạm vi toàn cục, bao gồm tài liệu mặc định và tài liệu nhóm. Đây là lựa chọn phù hợp khi thay đổi cần được áp dụng nhất quán ở mọi document. Nếu chỉ muốn tác động một nhóm, hãy dùng `OpenApiCustomizer` gắn trực tiếp vào builder của `GroupedOpenApi`. Bài này giải thích phạm vi áp dụng, cách triển khai an toàn và cách xác minh từng tài liệu sau khi tùy biến.

## 1. Vì sao cần customizer toàn cục?

Giả sử một dịch vụ có các nhóm tài liệu:

| Tài liệu | Phạm vi |
|---|---|
| Default document | Tài liệu mặc định do springdoc tạo; phạm vi endpoint có thể chồng lấn với các group |
| `public` | API dành cho client bên ngoài |
| `admin` | API quản trị |
| `partner` | API tích hợp đối tác |

Các tài liệu có thể cần một số thông tin chung:

- Thông tin liên hệ nhóm API.
- Đường dẫn điều khoản sử dụng.
- Server base URL dùng chung.
- Extension phục vụ gateway hoặc công cụ nội bộ.
- Security scheme được chia sẻ giữa các nhóm.

Nếu sử dụng một `OpenApiCustomizer` chỉ áp dụng cho tài liệu mặc định, các nhóm có thể không nhận được thay đổi. Khi mục tiêu là tác động tất cả tài liệu, `GlobalOpenApiCustomizer` diễn đạt đúng phạm vi hơn.

## 2. Phân biệt các loại customizer

Springdoc có nhiều extension point với phạm vi khác nhau. Cần chọn đúng loại để tránh trường hợp code chạy nhưng một số tài liệu không được cập nhật.

| Cơ chế | Phạm vi áp dụng | Mục đích |
|---|---|---|
| `OpenApiCustomizer` bean | Tài liệu OpenAPI mặc định | Thay đổi document mặc định |
| `GlobalOpenApiCustomizer` bean | Tài liệu mặc định và các tài liệu nhóm | Áp dụng metadata hoặc thay đổi chung trên mọi document |
| `GroupedOpenApi.Builder.addOpenApiCustomizer(...)` | Nhóm được cấu hình trong builder đó | Tùy biến riêng một group |
| `OperationCustomizer` | Operation trong tài liệu mặc định theo cơ chế đăng ký tương ứng | Điều chỉnh từng operation, ví dụ summary hoặc parameter |
| `GlobalOperationCustomizer` | Operation trong tài liệu mặc định và các nhóm | Điều chỉnh từng operation trên phạm vi toàn cục |

Điểm khác biệt quan trọng là cấp độ tùy biến:

- `GlobalOpenApiCustomizer` nhận toàn bộ `OpenAPI` document, vì vậy có thể thay đổi `info`, `servers`, `tags`, `components`, security và các thuộc tính cấp tài liệu.
- `GlobalOperationCustomizer` nhận từng `Operation`, phù hợp khi cần áp dụng quy tắc lên operation ở nhiều nhóm.
- `GroupedOpenApi.Builder.addOpenApiCustomizer(...)` giới hạn thay đổi ở một nhóm cụ thể.

Không dùng customizer cấp document để xử lý logic cần biết chi tiết từng method nếu một operation customizer phù hợp hơn. Ngược lại, không cần lặp một customizer nhóm nếu thay đổi thực sự giống nhau trên mọi tài liệu.

## 3. Khai báo `GlobalOpenApiCustomizer` bean

Với springdoc-openapi 2.x, interface `GlobalOpenApiCustomizer` nằm trong package `org.springdoc.core.customizers`. Có thể đăng ký một bean trong class cấu hình Spring:

```java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import org.springdoc.core.customizers.GlobalOpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class GlobalOpenApiConfiguration {

    @Bean
    GlobalOpenApiCustomizer commonDocumentMetadata() {
        return openApi -> {
            if (openApi.getInfo() == null) {
                openApi.setInfo(new Info()
                        .title("Application API")
                        .version("1.0.0"));
            }

            if (openApi.getInfo().getContact() == null) {
                openApi.getInfo().setContact(new Contact()
                        .name("API Support")
                        .email("api-support@example.com"));
            }

            if (openApi.getInfo().getDescription() == null) {
                openApi.getInfo().setDescription(
                        "API được công bố bởi nền tảng dịch vụ.");
            }
        };
    }
}
```

Spring quản lý bean và springdoc gọi customizer khi xây dựng tài liệu. Vì đây là customizer toàn cục, cùng logic có thể tác động tài liệu mặc định và từng group.

Trong ví dụ, customizer chỉ bổ sung thông tin khi trường tương ứng chưa có. Cách này giúp giữ metadata riêng đã khai báo cho một tài liệu, chẳng hạn title hoặc description riêng của nhóm. Nếu chủ đích là ép mọi document dùng một giá trị giống nhau, có thể ghi đè tường minh, nhưng cần hiểu rằng metadata riêng của group cũng sẽ bị thay thế.

Import và API có thể khác giữa các major version. Với dự án springdoc 1.x, hãy đối chiếu package và phiên bản dependency đang sử dụng; không sao chép import 2.x một cách máy móc.

## 4. `GlobalOpenApiCustomizer` tác động đến những tài liệu nào?

Giả sử ứng dụng có một tài liệu mặc định và hai nhóm:

```java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ApiGroupsConfiguration {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
                .group("public")
                .pathsToMatch("/api/public/**")
                .build();
    }

    @Bean
    GroupedOpenApi adminApi() {
        return GroupedOpenApi.builder()
                .group("admin")
                .pathsToMatch("/api/admin/**")
                .build();
    }
}
```

Một `GlobalOpenApiCustomizer` bean có thể được áp dụng cho:

- `/v3/api-docs` — tài liệu mặc định.
- `/v3/api-docs/public` — tài liệu nhóm `public`.
- `/v3/api-docs/admin` — tài liệu nhóm `admin`.

Nếu cần YAML, kiểm tra endpoint YAML tương ứng của từng tài liệu theo cấu hình springdoc. Đường dẫn có thể thay đổi khi ứng dụng cấu hình `springdoc.api-docs.path`, context path hoặc reverse proxy prefix.

Không cần đăng ký một bản customizer riêng cho mỗi group để áp dụng cùng metadata. Nếu một group cần ngoại lệ, hãy kết hợp customizer riêng cho group hoặc điều chỉnh điều kiện trong thiết kế cấu hình một cách rõ ràng.

## 5. Thêm metadata chung mà vẫn giữ thông tin riêng của group

Một lỗi thường gặp là customizer toàn cục ghi đè mọi `Info` bằng một object mới. Cách đó có thể làm mất title, version hoặc description được khai báo riêng cho nhóm.

Ví dụ không nên dùng nếu mỗi group có title riêng:

```java
return openApi -> openApi.setInfo(new Info()
        .title("Application API")
        .version("1.0.0"));
```

Đoạn code trên thay toàn bộ `Info` hiện có. Nếu nhóm `admin` đã có title `Admin API`, title đó sẽ bị ghi đè.

Thay vào đó, chỉ cập nhật trường chung:

```java
return openApi -> {
    if (openApi.getInfo() == null) {
        openApi.setInfo(new Info()
                .title("Application API")
                .version("1.0.0"));
    }

    openApi.getInfo().setTermsOfService("https://example.com/terms");

    if (openApi.getInfo().getContact() == null) {
        openApi.getInfo().setContact(new Contact()
                .name("Platform API Team")
                .email("api-team@example.com"));
    }
};
```

Ví dụ này giữ title/version/description hiện tại, đồng thời bổ sung điều khoản và contact nếu chưa có. Nếu mọi group cần contact giống nhau tuyệt đối, có thể ghi đè contact; nếu có contact riêng, hãy giữ giá trị đã tồn tại.

## 6. Thêm server chung cho tất cả tài liệu

Một số ứng dụng muốn mọi document có cùng server base URL. Có thể dùng `GlobalOpenApiCustomizer` và lấy URL từ cấu hình thay vì hard-code môi trường:

```java
import java.util.ArrayList;

import io.swagger.v3.oas.models.servers.Server;
import org.springdoc.core.customizers.GlobalOpenApiCustomizer;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;

@Bean
GlobalOpenApiCustomizer commonServer(
        @Value("${app.openapi.server-url:/}") String serverUrl) {
    return openApi -> {
        if (openApi.getServers() == null) {
            openApi.setServers(new ArrayList<>());
        }

        boolean exists = openApi.getServers().stream()
                .anyMatch(server -> serverUrl.equals(server.getUrl()));

        if (!exists) {
            openApi.addServersItem(new Server()
                    .url(serverUrl)
                    .description("API server"));
        }
    };
}
```

Property ví dụ:

```yaml
app:
  openapi:
    server-url: https://api.example.com
```

Đoạn code kiểm tra URL đã tồn tại trước khi thêm, tránh tạo server trùng khi customizer được gọi lại trong quá trình tạo tài liệu. Nếu mỗi group triển khai ở host hoặc base path khác nhau, không nên thêm một server chung cho tất cả. Hãy cấu hình server theo group hoặc theo môi trường phù hợp.

Với môi trường local, staging và production, có thể cung cấp property qua profile hoặc biến môi trường. Không đưa URL nội bộ nhạy cảm vào tài liệu public.

## 7. Thêm extension dùng chung

OpenAPI cho phép vendor extension có tên bắt đầu bằng `x-`. Extension thường được dùng để truyền metadata cho API gateway, developer portal hoặc công cụ nội bộ.

Ví dụ thêm audience và mã sở hữu tài liệu:

```java
import org.springdoc.core.customizers.GlobalOpenApiCustomizer;
import org.springframework.context.annotation.Bean;

@Bean
GlobalOpenApiCustomizer commonExtensions() {
    return openApi -> {
        openApi.addExtension("x-api-owner", "platform-team");
        openApi.addExtension("x-api-audience", "service-consumers");
    };
}
```

Output ở cấp document có thể có dạng:

```yaml
x-api-owner: platform-team
x-api-audience: service-consumers
```

Nếu extension đã được thiết lập bởi một cấu hình khác, `addExtension` có thể thay thế giá trị cùng key. Hãy xác định rõ customizer là nguồn có quyền ghi đè hay chỉ bổ sung khi chưa tồn tại. Extension không có ý nghĩa chuẩn với mọi client; chỉ dùng khi các công cụ tiêu thụ hiểu quy ước đó.

## 8. Khai báo security scheme dùng chung

Một security scheme có thể được khai báo trong `components.securitySchemes` để nhiều operation hoặc group tham chiếu. Ví dụ thêm HTTP Bearer JWT vào tất cả tài liệu:

```java
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.security.SecurityScheme;
import org.springdoc.core.customizers.GlobalOpenApiCustomizer;
import org.springframework.context.annotation.Bean;

@Bean
GlobalOpenApiCustomizer commonBearerScheme() {
    return openApi -> {
        if (openApi.getComponents() == null) {
            openApi.setComponents(new Components());
        }

        if (openApi.getComponents().getSecuritySchemes() == null
                || !openApi.getComponents().getSecuritySchemes()
                        .containsKey("bearerAuth")) {
            openApi.getComponents().addSecuritySchemes(
                    "bearerAuth",
                    new SecurityScheme()
                            .type(SecurityScheme.Type.HTTP)
                            .scheme("bearer")
                            .bearerFormat("JWT")
            );
        }
    };
}
```

Schema bảo mật xuất hiện trong `components`, nhưng chỉ khai báo scheme chưa có nghĩa là mọi operation đều bắt buộc xác thực. Để đánh dấu security requirement ở cấp document, có thể thêm `SecurityRequirement`; khi đó requirement mặc định áp dụng cho các operation trong tài liệu, trừ khi operation có cấu hình khác.

Không thêm security requirement toàn cục nếu một số endpoint trong group là public. Có thể khai báo scheme chung bằng customizer, rồi gắn `@SecurityRequirement(name = "bearerAuth")` vào các operation cần bảo vệ. Xác thực runtime vẫn phải được cấu hình bằng Spring Security; OpenAPI chỉ mô tả cách client gửi thông tin xác thực.

## 9. Khi nào nên dùng customizer riêng cho một nhóm?

Không phải thay đổi nào cũng nên áp dụng toàn cục. Ví dụ:

- Nhóm `public` có title, contact và terms dành cho khách hàng.
- Nhóm `admin` có description và server nội bộ riêng.
- Nhóm `partner` có extension chứa mã đối tác hoặc policy riêng.

Trong các trường hợp này, dùng `GroupedOpenApi.Builder.addOpenApiCustomizer(...)`:

```java
import io.swagger.v3.oas.models.info.Info;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;

@Bean
GroupedOpenApi partnerApi() {
    return GroupedOpenApi.builder()
            .group("partner")
            .pathsToMatch("/api/partner/**")
            .addOpenApiCustomizer(openApi -> {
                if (openApi.getInfo() == null) {
                    openApi.setInfo(new Info()
                            .title("Partner API")
                            .version("1.0.0"));
                } else {
                    openApi.getInfo().setTitle("Partner API");
                }
                openApi.addExtension("x-api-audience", "partners");
            })
            .build();
}
```

Customizer gắn vào builder này chỉ dành cho nhóm `partner`. Nếu cũng có một `GlobalOpenApiCustomizer` sửa cùng trường `info.title` hoặc extension, kết quả cuối cùng phụ thuộc thứ tự các customizer được áp dụng. Tránh để nhiều customizer ghi đè cùng thuộc tính nếu không có chủ đích; nên gom quy tắc hoặc kiểm tra output thực tế theo phiên bản đang dùng.

## 10. Điều kiện để customizer an toàn và dễ bảo trì

Customizer có thể được gọi trong quá trình tạo hoặc làm mới tài liệu. Vì vậy, logic nên đơn giản, có thể chạy lặp và không tạo tác dụng phụ ngoài dự kiến.

### Thiết kế idempotent

Một customizer idempotent có thể chạy nhiều lần mà không làm kết quả ngày càng khác đi. Ví dụ, trước khi thêm server hoặc tag, hãy kiểm tra phần tử đã tồn tại. Tránh append lặp cùng một tag, server, security requirement hoặc extension.

### Không phụ thuộc request cụ thể

OpenAPI document thường là tài liệu dùng chung, không phải một response riêng cho từng người dùng. Không đọc thông tin principal hiện tại, request header hoặc tenant của request đang chạy để thay đổi tài liệu toàn cục. Nếu mỗi tenant có tài liệu khác nhau, cần thiết kế cơ chế phát hành tài liệu riêng có kiểm soát thay vì phụ thuộc ngẫu nhiên vào request.

### Tránh gọi hệ thống ngoài trong customizer

Không nên gọi database, remote API hoặc dịch vụ cấu hình chậm mỗi khi customizer chạy. Điều đó làm tài liệu khó dự đoán, tăng độ trễ và có thể khiến endpoint docs lỗi khi dịch vụ phụ thuộc không sẵn sàng. Nạp cấu hình cần thiết qua Spring configuration và giữ customizer thuần túy nhất có thể.

### Bảo vệ dữ liệu trong tài liệu

Không đưa token, mật khẩu, khóa bí mật, host nội bộ hoặc dữ liệu cá nhân vào description, example, extension hoặc server URL của tài liệu public. Nếu document có phạm vi nội bộ, vẫn phải bảo vệ endpoint docs bằng Spring Security.

## 11. Phân biệt customizer toàn cục với `@OpenAPIDefinition`

`@OpenAPIDefinition` khai báo metadata OpenAPI bằng annotation ở mức cấu hình, chẳng hạn title, version, description, servers, tags hoặc security. `GlobalOpenApiCustomizer` dùng Java code để điều chỉnh mô hình document sau khi springdoc xây dựng.

| Cách làm | Phù hợp khi |
|---|---|
| `@OpenAPIDefinition` | Metadata tĩnh, đơn giản và có thể khai báo bằng annotation |
| `OpenAPI` bean | Muốn khởi tạo cấu trúc OpenAPI bằng Java theo cấu hình chung |
| `OpenApiCustomizer` | Muốn sửa document mặc định bằng logic Java |
| `GlobalOpenApiCustomizer` | Muốn cùng logic sửa document mặc định và mọi group |
| Customizer trên `GroupedOpenApi` | Muốn sửa riêng một group |

Không cần đưa mọi metadata vào customizer. Nếu giá trị tĩnh có thể biểu đạt rõ bằng annotation hoặc bean, hãy dùng cơ chế khai báo đơn giản. Dành customizer cho phần cần điều kiện, kiểm tra tồn tại, hợp nhất hoặc biến đổi theo logic.

## 12. Kiểm tra customizer có tác động đến mọi group

Sau khi đăng ký bean, hãy kiểm tra tài liệu mặc định và từng nhóm. Ví dụ:

```text
GET /v3/api-docs
GET /v3/api-docs/public
GET /v3/api-docs/admin
GET /v3/api-docs/partner
```

Nếu đã cấu hình YAML, kiểm tra endpoint YAML tương ứng. Với mỗi document, xác nhận:

1. Metadata chung như contact, terms hoặc extension xuất hiện.
2. Metadata riêng của group như title hoặc server vẫn được giữ nếu customizer được thiết kế theo kiểu bổ sung.
3. Server, tag và security scheme không bị lặp.
4. Security requirement chỉ áp dụng đúng phạm vi mong muốn.
5. `$ref` trong `components` vẫn hợp lệ sau khi tùy biến.
6. Không có operation hoặc schema bị xóa ngoài dự kiến.
7. Swagger UI tải đúng document của từng group.

Có thể tải tài liệu bằng curl:

```bash
curl -fS http://localhost:8080/v3/api-docs -o default-openapi.json
curl -fS http://localhost:8080/v3/api-docs/public -o public-openapi.json
curl -fS http://localhost:8080/v3/api-docs/admin -o admin-openapi.json
```

Sau đó dùng JSON parser hoặc OpenAPI validator để kiểm tra từng file. Không chỉ kiểm tra tài liệu mặc định; mục tiêu của `GlobalOpenApiCustomizer` là bảo đảm thay đổi cũng xuất hiện trong các group.

## 13. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Metadata chỉ xuất hiện ở `/v3/api-docs` | Dùng `OpenApiCustomizer` bean thay vì `GlobalOpenApiCustomizer` | Đổi sang customizer toàn cục nếu cần tác động các group |
| Một group không nhận thay đổi | Dùng customizer gắn vào group khác hoặc group chưa được đăng ký | Kiểm tra bean và phạm vi đăng ký |
| Title của group bị đổi ngoài ý muốn | Global customizer thay toàn bộ `Info` hoặc ghi đè title | Chỉ sửa trường chung hoặc dùng customizer riêng group |
| Server bị lặp | Customizer thêm server mỗi lần chạy mà không kiểm tra | Kiểm tra URL đã tồn tại trước khi thêm |
| Tag hoặc security requirement bị nhân đôi | Logic append không idempotent | Kiểm tra phần tử hiện có và chỉ thêm khi thiếu |
| Endpoint public bị đánh dấu cần Bearer | Thêm security requirement toàn cục cho cả document | Chỉ khai báo scheme chung và gắn requirement vào operation cần bảo vệ |
| Tài liệu có server URL sai môi trường | Hard-code URL trong customizer | Đưa URL vào property/profile phù hợp |
| Customizer làm docs chậm hoặc lỗi | Gọi database/remote service hoặc logic có tác dụng phụ | Dùng cấu hình đã nạp sẵn và giữ customizer đơn giản |
| Thay đổi không thấy trên Swagger UI | UI cache hoặc đang chọn tài liệu group khác | Tải lại tài liệu đúng URL và kiểm tra JSON/YAML trực tiếp |
| `GlobalOpenApiCustomizer` không được nhận diện | Sai import hoặc không tương thích phiên bản springdoc | Kiểm tra dependency và package của phiên bản đang dùng |

## 14. Quy trình triển khai

1. Xác định thay đổi cần áp dụng cho mọi document hay chỉ một group.
2. Nếu cần tác động mọi document, tạo bean `GlobalOpenApiCustomizer`.
3. Nếu chỉ cần tài liệu mặc định, dùng `OpenApiCustomizer` phù hợp.
4. Nếu chỉ cần một group, gắn `OpenApiCustomizer` vào `GroupedOpenApi.Builder`.
5. Giữ customizer idempotent, tránh ghi đè metadata riêng và không phụ thuộc request.
6. Khởi động ứng dụng và tải document mặc định cùng từng group.
7. So sánh metadata chung, thông tin riêng và các thành phần security.
8. Chạy validator OpenAPI và mở Swagger UI để kiểm tra.
9. Kiểm tra lại khi thay đổi phiên bản springdoc hoặc cấu hình group.

## 15. Nguyên tắc thiết kế

- Dùng `GlobalOpenApiCustomizer` khi cùng một thay đổi phải xuất hiện trên tài liệu mặc định và tất cả tài liệu nhóm.
- Dùng `OpenApiCustomizer` bean cho document mặc định và customizer gắn vào builder cho group cụ thể.
- Dùng `GlobalOperationCustomizer` nếu cần thay đổi từng operation trên phạm vi tất cả document.
- Giữ metadata riêng của group khi chỉ bổ sung thông tin chung.
- Kiểm tra trước khi thêm server, tag, extension hoặc security scheme để tránh trùng.
- Chỉ thêm security requirement toàn cục khi mọi operation trong document thực sự cần xác thực.
- Đưa server URL và giá trị môi trường vào configuration thay vì hard-code.
- Không phụ thuộc request hiện tại hoặc gọi dịch vụ ngoài trong customizer.
- Kiểm tra JSON/YAML của từng group, không chỉ tài liệu mặc định.
- Bảo vệ endpoint tài liệu bằng security độc lập với việc customizer thay đổi schema.

## Kết luận

`GlobalOpenApiCustomizer` là extension point cấp document dành cho các thay đổi cần áp dụng trên tài liệu OpenAPI mặc định và các tài liệu nhóm do springdoc tạo. Nó phù hợp để bổ sung metadata, server, extension hoặc security scheme chung. `OpenApiCustomizer` bean có phạm vi hẹp hơn; customizer gắn vào `GroupedOpenApi.Builder` dành cho một nhóm cụ thể. Hãy chọn đúng phạm vi, tránh ghi đè metadata riêng, thiết kế logic idempotent và kiểm tra từng endpoint JSON/YAML để bảo đảm mọi nhóm nhận đúng thay đổi dự kiến.
