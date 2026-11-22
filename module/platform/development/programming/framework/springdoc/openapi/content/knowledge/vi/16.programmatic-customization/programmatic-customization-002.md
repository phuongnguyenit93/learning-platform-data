# OpenApiCustomizer cho các thay đổi ở cấp tài liệu

springdoc-openapi có thể tạo tài liệu OpenAPI từ controller, DTO và các annotation. Khi metadata cần được tính theo môi trường, chia sẻ giữa nhiều endpoint hoặc bổ sung sau khi tài liệu đã được tạo, annotation trên từng controller có thể không còn thuận tiện. **OpenApiCustomizer** cung cấp một điểm mở rộng để chỉnh sửa mô hình OpenAPI ở cấp toàn tài liệu.

Với customizer, ứng dụng có thể cập nhật tiêu đề và thông tin liên hệ, thêm server URL, khai báo tag dùng chung, bổ sung security scheme, extension hoặc metadata khác. Có thể áp dụng thay đổi cho tài liệu mặc định, cho một document group cụ thể hoặc cho nhiều group. Customizer chỉ thay đổi đặc tả được công bố; nó không tự thay đổi route, quyền truy cập hay hành vi xử lý request của Spring MVC.

## 1. OpenApiCustomizer trong quá trình tạo tài liệu

~~~text
Spring MVC controllers + DTO + annotations
                  |
                  v
          springdoc scans API
                  |
                  v
        OpenAPI model is created
                  |
                  v
       OpenApiCustomizer callbacks
                  |
                  v
       OpenAPI JSON/YAML document
                  |
                  v
              Swagger UI
~~~

Springdoc quét các mapping và metadata, sau đó xây dựng mô hình Java của đặc tả OpenAPI. Customizer nhận mô hình đó và có thể thêm, sửa hoặc loại bỏ thông tin trước khi tài liệu được xuất ra.

Trong mã nguồn, customizer thường là một lambda hoặc một bean triển khai interface `OpenApiCustomizer`. Đối tượng nhận vào là `io.swagger.v3.oas.models.OpenAPI`, tức mô hình tài liệu chứ không phải request HTTP đang chạy.

## 2. OpenApiCustomizer là gì?

Trong Springdoc 2.x, interface thường được import từ:

~~~java
import org.springdoc.core.customizers.OpenApiCustomizer;
~~~

Đây là functional interface nên có thể tạo customizer bằng lambda:

~~~java
OpenApiCustomizer metadataCustomizer = openApi -> {
    // Thay đổi mô hình OpenAPI tại đây.
};
~~~

`openApi` là đối tượng gốc của tài liệu. Từ đó có thể truy cập các thành phần:

| Thành phần | Mục đích |
|---|---|
| `info` | Tên API, mô tả, phiên bản, liên hệ, license |
| `servers` | Địa chỉ server mà client có thể gọi |
| `tags` | Danh sách tag và mô tả tag ở cấp tài liệu |
| `paths` | Các path và operation đã được phát hiện |
| `components` | Schema, response, parameter, security scheme dùng lại |
| `security` | Yêu cầu bảo mật mặc định ở cấp tài liệu |
| `externalDocs` | Liên kết đến tài liệu bổ sung |
| `extensions` | Metadata mở rộng theo quy ước `x-...` |

Customizer nên được dùng cho metadata hoặc quy tắc thực sự thuộc cấp tài liệu. Những mô tả riêng của một operation như summary, request parameter hoặc response cụ thể thường nên đặt bằng annotation tương ứng hoặc `OperationCustomizer`.

## 3. Khai báo OpenApiCustomizer dưới dạng Spring bean

Springdoc có thể nhận một bean `OpenApiCustomizer` để tùy biến tài liệu OpenAPI mặc định:

~~~java
import io.swagger.v3.oas.models.info.Info;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiConfiguration {

    @Bean
    OpenApiCustomizer documentMetadataCustomizer() {
        return openApi -> {
            Info info = openApi.getInfo();
            if (info == null) {
                info = new Info();
                openApi.setInfo(info);
            }

            info.setDescription(
                "Tài liệu API của hệ thống quản lý cửa hàng."
            );
        };
    }
}
~~~

Đoạn mã chỉ bổ sung description. Nếu `Info` đã được tạo từ `@OpenAPIDefinition` hoặc bean `OpenAPI`, các thuộc tính khác như title và version vẫn được giữ lại.

Bean `OpenApiCustomizer` thông thường áp dụng cho tài liệu mặc định. Nếu cần áp dụng cùng quy tắc cho các document group, hãy xem `GlobalOpenApiCustomizer`; nếu chỉ muốn sửa một group, gắn customizer vào `GroupedOpenApi`.

## 4. Cập nhật Info mà không làm mất metadata đã có

`Info` chứa metadata nhận diện API. Có thể bổ sung description, terms of service, contact và license:

~~~java
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.info.License;
import org.springdoc.core.customizers.OpenApiCustomizer;

@Bean
OpenApiCustomizer apiInfoCustomizer() {
    return openApi -> {
        Info info = openApi.getInfo();
        if (info == null) {
            info = new Info();
            openApi.setInfo(info);
        }

        info.setDescription(
            "API hỗ trợ tra cứu sản phẩm, đơn hàng và khách hàng."
        );
        info.setTermsOfService("https://example.com/terms");

        Contact contact = info.getContact();
        if (contact == null) {
            contact = new Contact();
            info.setContact(contact);
        }
        contact.setName("API Support");
        contact.setEmail("api-support@example.com");
        contact.setUrl("https://example.com/support");

        License license = info.getLicense();
        if (license == null) {
            license = new License();
            info.setLicense(license);
        }
        license.setName("Internal API Terms");
        license.setUrl("https://example.com/api-license");
    };
}
~~~

Ví dụ kiểm tra object con trước khi tạo mới để giữ metadata đã khai báo từ nguồn khác. Nếu muốn ghi đè một trường, hãy ghi đè đúng trường đó thay vì thay toàn bộ `Info` bằng object mới. Điều này tránh vô tình xóa title, version hoặc contact đã được cấu hình.

Không đưa thông tin liên hệ cá nhân hoặc URL nội bộ vào tài liệu public nếu chúng không được phép công bố.

## 5. Thêm server URL theo môi trường

`servers` xác định địa chỉ gốc mà client dùng để gọi API. Một ứng dụng có thể chạy ở localhost, staging và production với các base URL khác nhau.

Không nên ghi cứng địa chỉ production trong customizer dùng chung cho mọi môi trường. Hãy lấy URL từ cấu hình:

~~~yaml
app:
  openapi:
    server-url: https://api.example.com
~~~

Customizer đọc cấu hình bằng Spring `Environment` và thêm server nếu chưa có:

~~~java
import io.swagger.v3.oas.models.servers.Server;
import java.util.ArrayList;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@Bean
OpenApiCustomizer serverCustomizer(Environment environment) {
    String serverUrl = environment.getRequiredProperty(
        "app.openapi.server-url"
    );

    return openApi -> {
        if (openApi.getServers() == null) {
            openApi.setServers(new ArrayList<>());
        }

        boolean exists = openApi.getServers().stream()
            .anyMatch(server -> serverUrl.equals(server.getUrl()));

        if (!exists) {
            openApi.addServersItem(
                new Server()
                    .url(serverUrl)
                    .description("Server của môi trường hiện tại.")
            );
        }
    };
}
~~~

Cấu hình có thể được ghi đè theo profile:

~~~yaml
# application-local.yml
app:
  openapi:
    server-url: http://localhost:8080
~~~

~~~yaml
# application-prod.yml
app:
  openapi:
    server-url: https://api.example.com
~~~

Nếu ứng dụng chạy sau reverse proxy hoặc API gateway, server URL công khai có thể khác địa chỉ mà ứng dụng nhìn thấy bên trong container. Hãy công bố URL mà client thực sự sử dụng. Cấu hình server trong OpenAPI không tự cấu hình proxy, CORS hoặc định tuyến gateway.

Nếu cần giữ nhiều server để người dùng Swagger UI lựa chọn, hãy thêm nhiều phần tử có chủ đích. Tránh thêm lặp server mỗi lần customizer được áp dụng; ví dụ trên kiểm tra URL trước khi thêm.

## 6. Bổ sung tag ở cấp tài liệu

Tag ở cấp tài liệu mô tả tên và ý nghĩa nhóm operation. Có thể thêm tag dùng chung bằng customizer:

~~~java
import io.swagger.v3.oas.models.tags.Tag;
import java.util.ArrayList;
import org.springdoc.core.customizers.OpenApiCustomizer;

@Bean
OpenApiCustomizer commonTagsCustomizer() {
    return openApi -> {
        if (openApi.getTags() == null) {
            openApi.setTags(new ArrayList<>());
        }

        boolean catalogExists = openApi.getTags().stream()
            .anyMatch(tag -> "Catalog".equals(tag.getName()));

        if (!catalogExists) {
            openApi.addTagsItem(
                new Tag()
                    .name("Catalog")
                    .description("Tra cứu và quản lý sản phẩm.")
            );
        }
    };
}
~~~

Danh sách tag trong tài liệu định nghĩa metadata của tag. Việc operation thực sự thuộc tag nào vẫn được thể hiện ở thuộc tính `tags` của từng operation, thường khai báo bằng `@Tag` hoặc `@Operation(tags = ...)`.

Customizer trên chỉ thêm định nghĩa tag nếu chưa có tên tương ứng. Nó không tự gắn tag `Catalog` vào tất cả operation. Nếu muốn gắn tag dựa trên đường dẫn hoặc quy tắc nghiệp vụ, có thể duyệt `paths` và operation, nhưng cân nhắc dùng `OperationCustomizer` khi logic chỉ liên quan đến operation.

## 7. Thêm Components và schema dùng chung

`components` chứa các định nghĩa có thể tham chiếu từ nhiều operation. Một customizer có thể bổ sung schema dùng chung khi schema đó không được suy ra từ DTO:

~~~java
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.media.ObjectSchema;
import io.swagger.v3.oas.models.media.StringSchema;
import org.springdoc.core.customizers.OpenApiCustomizer;

@Bean
OpenApiCustomizer sharedSchemaCustomizer() {
    return openApi -> {
        if (openApi.getComponents() == null) {
            openApi.setComponents(new Components());
        }

        if (openApi.getComponents().getSchemas() == null
                || !openApi.getComponents().getSchemas()
                    .containsKey("CorrelationInfo")) {
            ObjectSchema schema = new ObjectSchema()
                .addProperty("requestId", new StringSchema()
                    .description("Mã định danh request."))
                .addProperty("traceId", new StringSchema()
                    .description("Mã trace dùng để tra cứu log."));

            openApi.getComponents().addSchemas("CorrelationInfo", schema);
        }
    };
}
~~~

Ví dụ thêm schema `CorrelationInfo` vào `components.schemas`. Một schema chỉ có ích cho client khi được tham chiếu từ request, response hoặc thành phần khác. Việc thêm schema vào components không tự thêm field vào DTO runtime.

Nếu schema tương ứng với một kiểu Java thực tế, ưu tiên khai báo DTO và để springdoc sinh schema. Dùng customizer cho schema được chia sẻ từ hệ thống ngoài, metadata không thể suy ra từ kiểu Java hoặc quy tắc tài liệu đặc biệt.

## 8. Bổ sung Security Scheme ở cấp tài liệu

Có thể dùng customizer để khai báo cơ chế xác thực mà API hỗ trợ. Ví dụ API dùng HTTP Bearer với JWT:

~~~java
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.security.SecurityScheme;
import org.springdoc.core.customizers.OpenApiCustomizer;

@Bean
OpenApiCustomizer bearerSchemeCustomizer() {
    return openApi -> {
        if (openApi.getComponents() == null) {
            openApi.setComponents(new Components());
        }

        openApi.getComponents().addSecuritySchemes(
            "bearerAuth",
            new SecurityScheme()
                .type(SecurityScheme.Type.HTTP)
                .scheme("bearer")
                .bearerFormat("JWT")
                .description("Nhập access token hợp lệ.")
        );
    };
}
~~~

Định nghĩa scheme cho biết client cần gửi thông tin xác thực theo cách nào. Để yêu cầu scheme này ở cấp toàn tài liệu, có thể thêm security requirement:

~~~java
import io.swagger.v3.oas.models.security.SecurityRequirement;

openApi.addSecurityItem(
    new SecurityRequirement().addList("bearerAuth")
);
~~~

Security requirement cấp tài liệu áp dụng mặc định cho các operation trong tài liệu. Chỉ thêm nó nếu mọi operation đều yêu cầu bearer token. Nếu có endpoint public, hãy mô tả security riêng cho từng operation hoặc dùng `@SecurityRequirement` tương ứng để thể hiện ngoại lệ.

Khai báo security trong OpenAPI chỉ giúp Swagger UI và client generator hiểu hợp đồng xác thực. Nó không bật Spring Security, không kiểm tra JWT và không bảo vệ endpoint. Phần thực thi vẫn cần cấu hình Spring Security và kiểm thử độc lập.

## 9. Bổ sung ExternalDocumentation và extension

`externalDocs` cung cấp liên kết đến tài liệu chi tiết hơn:

~~~java
import io.swagger.v3.oas.models.ExternalDocumentation;

openApi.setExternalDocs(
    new ExternalDocumentation()
        .description("Hướng dẫn tích hợp API")
        .url("https://docs.example.com/api")
);
~~~

OpenAPI cũng hỗ trợ extension do nhà cung cấp định nghĩa với tiền tố `x-`. Ví dụ:

~~~java
Map<String, Object> extensions = openApi.getExtensions();
if (extensions == null) {
    extensions = new LinkedHashMap<>();
    openApi.setExtensions(extensions);
}
extensions.putIfAbsent("x-audience", "partner");
~~~

Ví dụ cần import `java.util.LinkedHashMap` và `java.util.Map`. Extension có thể mang metadata cho gateway, portal tài liệu hoặc quy trình nội bộ. Công cụ OpenAPI chung có thể bỏ qua extension mà nó không hiểu; không dùng extension thay thế những field chuẩn như `servers`, `security` hoặc `tags`.

Nếu tài liệu đã có `externalDocs` hoặc extension từ customizer khác, hãy kiểm tra trước khi ghi đè để tránh mất metadata.

## 10. OpenApiCustomizer cho một document group

Khi ứng dụng tạo nhiều tài liệu bằng `GroupedOpenApi`, mỗi group có thể cần metadata riêng. Ví dụ tài liệu đối tác cần tiêu đề, mô tả và server khác tài liệu public:

~~~java
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.servers.Server;
import java.util.List;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class PartnerOpenApiConfiguration {

    @Bean
    GroupedOpenApi partnerApi() {
        return GroupedOpenApi.builder()
            .group("partner")
            .pathsToMatch("/api/partner/**")
            .addOpenApiCustomizer(partnerDocumentCustomizer())
            .build();
    }

    private OpenApiCustomizer partnerDocumentCustomizer() {
        return openApi -> {
            Info info = openApi.getInfo();
            if (info == null) {
                info = new Info();
                openApi.setInfo(info);
            }
            info.setTitle("Partner API");
            info.setVersion("1.0.0");
            info.setDescription(
                "API dành cho hệ thống tích hợp của đối tác."
            );

            openApi.setServers(List.of(
                new Server()
                    .url("https://partner-api.example.com")
                    .description("Partner production API")
            ));
        };
    }
}
~~~

Customizer được gắn trực tiếp bằng `addOpenApiCustomizer`, nên phạm vi thay đổi được giới hạn vào group `partner`. Nếu cần giữ server đã có từ cấu hình khác, hãy thêm có kiểm tra trùng thay vì gọi `setServers` để thay toàn bộ danh sách.

Đây là lựa chọn phù hợp khi mỗi group có metadata riêng. Không nên tạo một bean `OpenApiCustomizer` dùng chung rồi giả định nó sẽ tự áp dụng cho mọi group.

## 11. GlobalOpenApiCustomizer cho nhiều group

Springdoc cung cấp `GlobalOpenApiCustomizer` cho những thay đổi cần áp dụng cho các tài liệu, bao gồm các group. Trong Springdoc 2.x, interface thường nằm trong package:

~~~java
import org.springdoc.core.customizers.GlobalOpenApiCustomizer;
~~~

Ví dụ thêm metadata chung cho các tài liệu:

~~~java
import io.swagger.v3.oas.models.info.Info;
import org.springdoc.core.customizers.GlobalOpenApiCustomizer;
import org.springframework.context.annotation.Bean;

@Bean
GlobalOpenApiCustomizer commonDocumentCustomizer() {
    return openApi -> {
        Info info = openApi.getInfo();
        if (info == null) {
            info = new Info();
            openApi.setInfo(info);
        }

        info.setTermsOfService("https://example.com/terms");
    };
}
~~~

Có thể dùng `GlobalOpenApiCustomizer` cho server metadata, extension, thông tin license hoặc schema dùng chung khi quy tắc thực sự giống nhau giữa các tài liệu. Với group có yêu cầu riêng, dùng `addOpenApiCustomizer` trên builder hoặc một customizer được cấu hình theo group.

Phạm vi áp dụng chính xác có thể phụ thuộc phiên bản springdoc và cách tạo group. Sau khi thêm bean, kiểm tra tài liệu mặc định và từng group để xác nhận customizer xuất hiện đúng nơi. Không tạo đồng thời nhiều customizer ghi đè cùng một field mà không có quy ước thứ tự rõ ràng.

## 12. Phân biệt OpenApiCustomizer và OperationCustomizer

Hai interface có phạm vi khác nhau:

| Customizer | Đối tượng nhận vào | Phạm vi phù hợp |
|---|---|---|
| `OpenApiCustomizer` | Toàn bộ `OpenAPI` document | Metadata, servers, tags, components, security, external docs |
| `GlobalOpenApiCustomizer` | Toàn bộ `OpenAPI` document | Thay đổi chung trên các tài liệu group |
| `OperationCustomizer` | Một `Operation` cùng `HandlerMethod` | Điều chỉnh summary, description, parameter hoặc metadata theo controller method |

Ví dụ `OperationCustomizer` có thể bổ sung một response hoặc tag cho từng operation theo annotation của method. Nếu cần thay đổi `Info`, `Servers` hoặc `Components` cho toàn tài liệu, `OpenApiCustomizer` là abstraction phù hợp hơn.

Không nên dùng một customizer cấp tài liệu để thực hiện logic quá chi tiết cho từng controller nếu annotation hoặc `OperationCustomizer` diễn đạt được quy tắc rõ hơn.

## 13. Kết hợp nhiều thay đổi trong một customizer

Có thể gom các thay đổi liên quan vào một customizer để dễ theo dõi:

~~~java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.servers.Server;
import java.util.ArrayList;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration
public class ApiDocumentCustomizerConfiguration {

    @Bean
    OpenApiCustomizer apiDocumentCustomizer(Environment environment) {
        String serverUrl = environment.getRequiredProperty(
            "app.openapi.server-url"
        );
        return openApi -> customizeDocument(openApi, serverUrl);
    }

    private void customizeDocument(OpenAPI openApi, String serverUrl) {
        Info info = openApi.getInfo();
        if (info == null) {
            info = new Info();
            openApi.setInfo(info);
        }

        info.setDescription("API quản lý cửa hàng.");

        Contact contact = info.getContact();
        if (contact == null) {
            contact = new Contact();
            info.setContact(contact);
        }
        contact.setName("API Support");
        contact.setEmail("api-support@example.com");

        if (openApi.getServers() == null) {
            openApi.setServers(new ArrayList<>());
        }

        boolean hasServer = openApi.getServers().stream()
            .anyMatch(server -> serverUrl.equals(server.getUrl()));

        if (!hasServer) {
            openApi.addServersItem(
                new Server()
                    .url(serverUrl)
                    .description("API server")
            );
        }
    }
}
~~~

Customizer có thể tách phần xử lý sang phương thức riêng để dễ đọc và kiểm thử. Khi số lượng thay đổi tăng, nên tách thành các customizer nhỏ theo trách nhiệm, ví dụ metadata, servers và security. Tránh để nhiều customizer cùng thay thế toàn bộ một danh sách vì kết quả phụ thuộc thứ tự thực thi.

## 14. Nguyên tắc viết customizer an toàn

Một customizer tốt nên có các đặc điểm:

1. **Có phạm vi rõ ràng:** biết nó áp dụng cho tài liệu mặc định, một group hay tất cả group.
2. **Không phá metadata có sẵn:** chỉ cập nhật field cần thiết, khởi tạo object khi chưa tồn tại.
3. **Có thể chạy lặp an toàn:** tránh thêm tag, server, schema hoặc security requirement trùng lặp.
4. **Không phụ thuộc dữ liệu request:** tài liệu không nên thay đổi theo user đang gọi endpoint tài liệu, trừ khi có yêu cầu đặc biệt được thiết kế rõ.
5. **Không nhầm tài liệu với runtime:** khai báo server hoặc security không tự cấu hình gateway hay Spring Security.
6. **Dùng cấu hình môi trường:** không hardcode host, contact hoặc URL nhạy cảm.
7. **Có kiểm thử đầu ra:** xác minh JSON OpenAPI sau khi customizer chạy.

Nên ưu tiên `putIfAbsent`, kiểm tra phần tử đã tồn tại hoặc chỉ sửa field cần thiết. Nếu customizer gọi `setServers`, `setTags` hoặc `setSecurity` bằng danh sách mới, hãy chắc rằng việc thay toàn bộ danh sách là chủ đích.

## 15. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Ghi đè toàn bộ `Info` | Mất title, version hoặc contact được cấu hình trước | Lấy `getInfo()` rồi chỉ cập nhật field cần thiết |
| Dùng `OpenApiCustomizer` và mong nó áp dụng cho mọi group | Tài liệu nhóm không nhận thay đổi | Dùng `GlobalOpenApiCustomizer` hoặc gắn customizer vào group |
| Thêm server mỗi lần chạy mà không kiểm tra | Danh sách server bị trùng | Kiểm tra URL trước khi thêm |
| Dùng `setServers` khi muốn bổ sung một server | Xóa server được cấu hình từ nguồn khác | Dùng `addServersItem` hoặc hợp nhất danh sách |
| Thêm security requirement toàn cục dù có endpoint public | Swagger UI yêu cầu token cho endpoint công khai | Chỉ áp dụng global khi mọi operation đều được bảo vệ |
| Khai báo security scheme và nghĩ endpoint đã được bảo vệ | API vẫn có thể nhận request không xác thực | Cấu hình và kiểm thử Spring Security riêng |
| Thêm schema vào components nhưng không tham chiếu | Schema không được dùng trong operation | Tham chiếu bằng ref hoặc để DTO sinh schema |
| Dùng customizer cấp tài liệu cho metadata của một method | Quy tắc khó kiểm soát và dễ tác động nhầm operation | Dùng annotation hoặc `OperationCustomizer` |
| Nhiều customizer ghi đè cùng field | Kết quả phụ thuộc thứ tự | Chia trách nhiệm hoặc hợp nhất logic liên quan |
| Đưa URL nội bộ vào tài liệu public | Client nhận địa chỉ không thể truy cập hoặc thông tin nội bộ | Lấy URL công khai theo profile và kiểm tra output |

## 16. Kiểm tra tài liệu sau khi tùy biến

Sau khi ứng dụng khởi động, mở tài liệu mặc định:

~~~bash
curl -s http://localhost:8080/v3/api-docs
~~~

Nếu có group, mở endpoint tài liệu có tên group tương ứng.

Kiểm tra các phần:

- `info`: title, version, description, contact, license và terms of service.
- `servers`: URL công khai đúng với môi trường hiện tại, không có phần tử trùng.
- `tags`: tên và mô tả tag đã được bổ sung mà không xóa metadata khác.
- `components.schemas`: schema dùng chung có đúng kiểu và được tham chiếu khi cần.
- `components.securitySchemes` và `security`: scheme có tên đúng và phạm vi áp dụng phù hợp.
- `externalDocs` và extension `x-...`: URL cùng extension có giá trị đúng.
- `paths`: operation gốc vẫn đầy đủ và không bị thay đổi ngoài dự kiến.

Với Swagger UI, kiểm tra server selector, thông tin API, tag và nút Authorize. Nếu tài liệu có nhiều group, xác nhận từng group nhận đúng customizer. Sau khi thay đổi profile hoặc cấu hình môi trường, kiểm tra lại `servers` để tránh công bố URL staging trong production hoặc ngược lại.

## 17. Kiểm thử customizer

Có thể kiểm thử logic biến đổi mô hình bằng cách tạo một đối tượng `OpenAPI`, gọi customizer rồi xác nhận các field:

~~~java
@Test
void shouldAddDocumentDescription() {
    OpenAPI openApi = new OpenAPI()
        .info(new Info().title("Store API").version("1.0.0"));

    OpenApiCustomizer customizer = openApiModel -> {
        Info info = openApiModel.getInfo();
        info.setDescription("API quản lý cửa hàng.");
    };

    customizer.customise(openApi);

    assertThat(openApi.getInfo().getTitle()).isEqualTo("Store API");
    assertThat(openApi.getInfo().getVersion()).isEqualTo("1.0.0");
    assertThat(openApi.getInfo().getDescription())
        .isEqualTo("API quản lý cửa hàng.");
}
~~~

Ví dụ dùng AssertJ và API `customise` của interface Springdoc. Tên phương thức và khả năng gọi trực tiếp cần được xác nhận theo phiên bản dependency đang dùng; nếu interface phiên bản đó sử dụng chữ ký khác, hãy điều chỉnh test theo API thực tế.

Kiểm thử đơn vị chỉ xác nhận logic customizer. Nên có thêm kiểm thử tích hợp gọi endpoint tài liệu để xác nhận Springdoc thực sự áp dụng bean, serialize đúng JSON và giữ các operation mong đợi.

## 18. Ghi nhớ

- `OpenApiCustomizer` nhận toàn bộ mô hình `OpenAPI` để chỉnh sửa ở cấp tài liệu.
- Dùng bean `OpenApiCustomizer` cho tài liệu mặc định; dùng `GlobalOpenApiCustomizer` cho thay đổi chung trên các group; dùng `addOpenApiCustomizer` cho một group cụ thể.
- Có thể tùy biến `Info`, `Servers`, `Tags`, `Components`, `Security`, `ExternalDocumentation` và extension.
- Nên cập nhật từng field thay vì thay toàn bộ object đã có metadata.
- Customizer cần idempotent để tránh server, tag, schema hoặc security item bị thêm trùng.
- `OperationCustomizer` phù hợp với thay đổi theo từng operation.
- Khai báo security trong OpenAPI không thay thế cấu hình Spring Security.
- Khai báo server URL không cấu hình reverse proxy hoặc gateway.
- Luôn kiểm tra tài liệu mặc định, từng group và Swagger UI sau khi thay đổi.

Khi cần bổ sung metadata hoặc quy tắc dùng chung cho tài liệu OpenAPI, hãy dùng `OpenApiCustomizer` để biến đổi mô hình tài liệu sau khi springdoc tạo ra. Xác định đúng phạm vi áp dụng, bảo toàn metadata hiện có và kiểm tra JSON được sinh ra để bảo đảm Swagger UI cùng client generator nhận đúng hợp đồng.
