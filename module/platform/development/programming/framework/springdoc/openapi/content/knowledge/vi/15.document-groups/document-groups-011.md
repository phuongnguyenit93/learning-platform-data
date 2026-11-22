# Giữ siêu dữ liệu dùng chung mà không làm sai hợp đồng từng nhóm

Khi một ứng dụng Spring Boot xuất nhiều tài liệu OpenAPI bằng GroupedOpenApi, các tài liệu thường có một phần thông tin chung như đơn vị sở hữu API, thông tin liên hệ, giấy phép, điều khoản sử dụng và cơ chế xác thực. Tuy vậy, mỗi nhóm có thể phục vụ một đối tượng khác nhau, có tên tài liệu, phiên bản, máy chủ hoặc chính sách bảo mật riêng.

Mục tiêu là giữ các metadata thật sự dùng chung nhất quán giữa các nhóm, đồng thời để mỗi hợp đồng công bố đúng phạm vi của nó. springdoc-openapi cung cấp OpenAPI bean, OpenApiCustomizer, GlobalOpenApiCustomizer và customizer gắn trực tiếp vào GroupedOpenApi để tổ chức việc này.

## 1. Siêu dữ liệu nào nên dùng chung?

OpenAPI document có nhiều phần metadata. Không phải trường nào cũng nên giống nhau ở mọi group.

| Thành phần | Ý nghĩa | Cách dùng giữa các group |
| --- | --- | --- |
| Info.title | Tên hiển thị của tài liệu | Thường riêng cho từng group |
| Info.version | Phiên bản của hợp đồng API được mô tả | Có thể chung hoặc riêng theo vòng đời API |
| Info.description | Mô tả phạm vi và đối tượng sử dụng | Thường riêng theo group |
| Info.termsOfService | URL điều khoản sử dụng | Có thể dùng chung |
| Info.contact | Đơn vị hoặc kênh liên hệ | Thường dùng chung, có thể khác theo sản phẩm |
| Info.license | Thông tin giấy phép | Dùng chung nếu chính sách áp dụng giống nhau |
| Servers | URL gốc để client gửi request | Có thể chung hoặc riêng theo môi trường/audience |
| Tags | Nhóm operation và mô tả nhóm | Một số tag dùng chung, một số chỉ thuộc một group |
| Components | Schema, parameter, response và security scheme tái sử dụng | Chỉ đưa vào tài liệu có operation cần dùng hoặc theo chính sách chung |
| Security requirements | Yêu cầu xác thực ở cấp document hoặc operation | Phải khớp chính sách của từng operation/group |
| External docs | Liên kết tới hướng dẫn bổ sung | Có thể chung ở cấp API, hoặc riêng theo group |

Ví dụ, contact và license có thể là metadata chung của tổ chức. Trong khi đó, Public API và Partner API nên có title và description riêng để người tích hợp nhận biết đúng hợp đồng. Một API dành cho đối tác có thể dùng server URL riêng; không nên đưa host nội bộ vào tài liệu public.

## 2. Phân biệt tên group với metadata Info

Tên group là định danh cấu hình của springdoc và thường xuất hiện trong URL lấy tài liệu. Info.title là tên hiển thị trong OpenAPI document và Swagger UI.

Ví dụ:

~~~java
@Bean
GroupedOpenApi partnerApi() {
    return GroupedOpenApi.builder()
        .group("partner-api")
        .pathsToMatch("/api/partner/**")
        .build();
}
~~~

Ở đây partner-api là group id. Nó không tự đặt Info.title, Info.version hay Info.description. Nếu không tùy biến Info, tài liệu có thể dùng metadata mặc định hoặc metadata chung của ứng dụng.

Có thể hiểu các trường theo cách sau:

| Giá trị | Vai trò |
| --- | --- |
| group = partner-api | Chọn tài liệu và định danh URL của group |
| Info.title = Partner API | Tên hiển thị cho người tích hợp |
| Info.version = v1 | Phiên bản của hợp đồng được mô tả |
| openapi = 3.1.0 | Phiên bản đặc tả OpenAPI, không phải phiên bản API |

Không dùng group id thay cho API version. Đổi group id có thể làm thay đổi URL tài liệu; đổi Info.version chỉ cập nhật metadata của hợp đồng.

## 3. Các cấp tùy biến trong springdoc-openapi

Có ba cách chính để đưa metadata vào tài liệu:

| Cơ chế | Phạm vi áp dụng | Khi nào dùng |
| --- | --- | --- |
| OpenAPI bean | Metadata và components dùng chung cho các tài liệu, kể cả group | Khai báo thông tin tổ chức, security scheme hoặc component chung |
| GlobalOpenApiCustomizer bean | Tùy biến được áp dụng cho tài liệu mặc định và các group | Bổ sung hoặc chuẩn hóa metadata trên mọi tài liệu |
| OpenApiCustomizer gắn vào GroupedOpenApi | Chỉ tài liệu của group được gắn customizer | Đặt title, description, server hoặc tag riêng cho một group |

Một điểm dễ nhầm: bean OpenApiCustomizer độc lập thường chỉ được áp dụng cho tài liệu OpenAPI mặc định. Nếu muốn customizer bean được chạy cho cả các group, dùng GlobalOpenApiCustomizer. Nếu chỉ muốn thay đổi một group, gắn OpenApiCustomizer bằng addOpenApiCustomizer trên builder của chính group đó.

Tài liệu FAQ của springdoc mô tả rõ sự khác nhau giữa customizer mặc định và global customizer. Hãy kiểm tra đúng tài liệu của major version đang dùng vì package và một số API có thể thay đổi giữa các dòng springdoc.

## 4. Khai báo metadata chung bằng OpenAPI bean

OpenAPI bean phù hợp để khai báo những thành phần mà mọi tài liệu cần có. Ví dụ, tổ chức dùng chung contact, license, terms of service và HTTP bearer scheme:

~~~java
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.info.License;
import io.swagger.v3.oas.models.security.SecurityScheme;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class SharedOpenApiConfig {

    @Bean
    OpenAPI sharedOpenAPI() {
        return new OpenAPI()
            .info(new Info()
                .title("Shop API")
                .version("v1")
                .termsOfService("https://developer.example.com/terms")
                .contact(new Contact()
                    .name("API Platform Team")
                    .email("api-support@example.com")
                    .url("https://developer.example.com/support"))
                .license(new License()
                    .name("Internal API License")
                    .url("https://developer.example.com/license")))
            .components(new Components()
                .addSecuritySchemes("bearerAuth",
                    new SecurityScheme()
                        .type(SecurityScheme.Type.HTTP)
                        .scheme("bearer")
                        .bearerFormat("JWT")));
    }
}
~~~

Bean trên cung cấp metadata và component dùng chung. Không cần gắn cùng một security requirement vào mọi operation chỉ vì đã khai báo bearerAuth. Security scheme chỉ định nghĩa cách xác thực; security requirement mới yêu cầu client sử dụng scheme đó.

Nếu dự án đã có OpenAPI bean khác, hãy hợp nhất cấu hình thay vì tạo nhiều bean OpenAPI cạnh tranh. Một nguồn cấu hình rõ ràng giúp tránh metadata hoặc components bị ghi đè ngoài dự kiến.

## 5. Giữ metadata chung bằng GlobalOpenApiCustomizer

GlobalOpenApiCustomizer phù hợp khi cần bổ sung cùng một quy ước cho mọi tài liệu, kể cả các group. Ví dụ, bảo đảm mọi document đều có contact và license nếu metadata ban đầu chưa khai báo:

~~~java
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.info.License;
import org.springdoc.core.customizers.GlobalOpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class SharedOpenApiCustomizerConfig {

    @Bean
    GlobalOpenApiCustomizer sharedInfoCustomizer() {
        return openApi -> {
            Info info = openApi.getInfo();
            if (info == null) {
                info = new Info()
                    .title("API")
                    .version("v1");
                openApi.setInfo(info);
            }

            if (info.getContact() == null) {
                info.setContact(new Contact()
                    .name("API Platform Team")
                    .email("api-support@example.com")
                    .url("https://developer.example.com/support"));
            }

            if (info.getLicense() == null) {
                info.setLicense(new License()
                    .name("Internal API License")
                    .url("https://developer.example.com/license"));
            }
        };
    }
}
~~~

Ví dụ chỉ điền contact và license khi chưa có giá trị. Cách làm này giữ lại metadata đã được khai báo ở cấp group hoặc OpenAPI bean. Nếu muốn áp dụng một giá trị bắt buộc cho toàn tổ chức, có thể chủ động ghi đè, nhưng cần hiểu rõ rằng mọi group sẽ nhận cùng giá trị đó.

Tránh thay toàn bộ Info object trong global customizer nếu mỗi group đã có title, version hoặc description riêng. Việc gọi openApi.setInfo(new Info().title(...)) có thể xóa các field đã được thiết lập trước đó.

## 6. Đặt metadata riêng bằng OpenApiCustomizer của từng group

Mỗi group có thể thay đổi title, version và description mà vẫn giữ contact, license và các metadata chung.

~~~java
import io.swagger.v3.oas.models.info.Info;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class GroupMetadataConfig {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public-api")
            .pathsToMatch("/api/public/**")
            .addOpenApiCustomizer(openApi -> {
                Info info = openApi.getInfo();
                if (info == null) {
                    info = new Info();
                    openApi.setInfo(info);
                }
                info.setTitle("Public API");
                info.setVersion("v1");
                info.setDescription(
                    "Hợp đồng dành cho ứng dụng web, mobile và khách hàng tích hợp công khai.");
            })
            .build();
    }

    @Bean
    GroupedOpenApi partnerApi() {
        return GroupedOpenApi.builder()
            .group("partner-api")
            .pathsToMatch("/api/partner/**")
            .addOpenApiCustomizer(openApi -> {
                Info info = openApi.getInfo();
                if (info == null) {
                    info = new Info();
                    openApi.setInfo(info);
                }
                info.setTitle("Partner API");
                info.setVersion("v2");
                info.setDescription(
                    "Hợp đồng dành cho đối tác vận chuyển và bán hàng.");
            })
            .build();
    }
}
~~~

Trong ví dụ, mỗi customizer chỉ ghi các trường thuộc phạm vi riêng của group. Contact và license được giữ lại từ cấu hình chung. Nếu muốn group có contact hoặc license riêng, hãy đặt chúng có chủ đích trong customizer tương ứng.

Không nên dựa vào thứ tự chạy giữa nhiều customizer để giải quyết xung đột metadata. Tốt nhất, mỗi field có một nơi chịu trách nhiệm rõ ràng: global customizer bổ sung field chung; group customizer đặt field riêng. Nếu hai nơi cùng ghi một field, hãy hợp nhất logic hoặc kiểm thử thứ tự thực tế theo phiên bản thư viện.

## 7. Dùng OpenAPI bean, annotation hay customizer?

Có thể chọn cơ chế theo tính chất metadata:

| Nhu cầu | Cơ chế phù hợp |
| --- | --- |
| Metadata chung, cố định và khai báo tĩnh | @OpenAPIDefinition |
| Metadata chung cần đọc từ Spring configuration | OpenAPI bean |
| Bổ sung quy tắc cho mọi group | GlobalOpenApiCustomizer |
| Metadata hoặc cấu trúc chỉ thuộc một group | GroupedOpenApi.builder().addOpenApiCustomizer(...) |
| Mô tả operation/schema cụ thể | @Operation, @ApiResponse, @Schema và annotation tương ứng |

@OpenAPIDefinition phù hợp với title, version, description, contact và tag ở cấp ứng dụng khi không cần logic điều kiện. OpenAPI bean linh hoạt hơn khi metadata đến từ application.yml hoặc biến môi trường. Customizer phù hợp khi phải dựa vào tên group hoặc cần thao tác trên OpenAPI model.

Ví dụ annotation cho metadata tĩnh dùng chung:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Contact;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.info.License;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    info = @Info(
        title = "Shop API",
        version = "v1",
        description = "API của nền tảng thương mại điện tử",
        termsOfService = "https://developer.example.com/terms",
        contact = @Contact(
            name = "API Platform Team",
            email = "api-support@example.com"
        ),
        license = @License(
            name = "Internal API License",
            url = "https://developer.example.com/license"
        )
    )
)
class StaticOpenApiDefinition {
}
~~~

Annotation này phù hợp khi metadata giống nhau trên mọi tài liệu. Nếu title hoặc version phải khác theo group, hãy đặt các field đó trong customizer riêng của từng group.

Ví dụ đưa metadata chung từ application.yml:

~~~yaml
app:
  api-docs:
    contact-name: API Platform Team
    contact-email: api-support@example.com
    support-url: https://developer.example.com/support
    license-name: Internal API License
    license-url: https://developer.example.com/license
~~~

Có thể inject các giá trị này vào OpenAPI bean bằng @Value hoặc @ConfigurationProperties. Không ghi cứng địa chỉ môi trường nội bộ vào metadata nếu tài liệu được công bố cho client bên ngoài.

## 8. Quản lý servers theo từng hợp đồng

Servers xác định URL gốc mà client dùng để gọi API. Một ứng dụng có thể phục vụ nhiều group qua cùng host, nhưng đôi khi partner API đi qua gateway riêng hoặc API public có base URL khác.

Ví dụ public và partner dùng server khác nhau:

~~~java
import java.util.List;
import io.swagger.v3.oas.models.servers.Server;

// Trong customizer của public-api
openApi.setServers(List.of(
    new Server()
        .url("https://api.example.com")
        .description("Public production")
));

// Trong customizer của partner-api
openApi.setServers(List.of(
    new Server()
        .url("https://partner-api.example.com")
        .description("Partner production")
));
~~~

Servers nên phản ánh URL mà client thực sự có thể truy cập. Nếu ứng dụng chạy sau reverse proxy, hãy kiểm tra forwarded headers và URL công khai. Không để tài liệu public chứa localhost, hostname Kubernetes, IP private hoặc URL staging ngoài chủ đích.

Nếu các group dùng cùng base URL, có thể khai báo server chung. Nếu chỉ khác môi trường development/staging/production, có thể dùng server variables hoặc cấu hình sinh tài liệu theo môi trường, nhưng cần tránh để tài liệu được phát hành nhầm trỏ tới môi trường không dành cho người tích hợp.

## 9. Giữ components và $ref nhất quán giữa các group

Mỗi OpenAPI document có components riêng. Một schema, parameter, response hoặc security scheme chỉ tồn tại trong document mà nó được khai báo. Vì vậy, một $ref trong partner-api không thể mặc định tham chiếu sang components của public-api.

Ví dụ:

~~~yaml
components:
  schemas:
    PartnerOrder:
      type: object
      properties:
        partnerOrderId:
          type: string
~~~

Nếu operation của group partner-api tham chiếu:

~~~yaml
schema:
  $ref: '#/components/schemas/PartnerOrder'
~~~

thì PartnerOrder phải xuất hiện trong chính tài liệu partner-api. Springdoc thường đưa schema vào components khi operation trong group tham chiếu DTO đó. Với component được thêm thủ công qua customizer hoặc OpenAPI bean, hãy bảo đảm nó được đưa vào mọi document có tham chiếu.

Không thêm toàn bộ schema nội bộ vào mọi group nếu người dùng group đó không cần chúng. Components dùng chung nên là những thành phần thực sự thuộc hợp đồng chung; phần còn lại nên giữ trong group tương ứng để tránh công bố cấu trúc không liên quan.

## 10. Security scheme có thể dùng chung, security requirement cần chọn lọc

Một scheme mô tả cơ chế xác thực, ví dụ bearer JWT hoặc OAuth2. Security requirement chỉ ra operation hoặc toàn document yêu cầu scheme đó.

Có thể định nghĩa bearer scheme dùng chung trong OpenAPI bean:

~~~java
new Components().addSecuritySchemes("bearerAuth",
    new SecurityScheme()
        .type(SecurityScheme.Type.HTTP)
        .scheme("bearer")
        .bearerFormat("JWT"))
~~~

Nếu mọi operation trong một group đều yêu cầu bearer token, có thể đặt requirement ở cấp document của group:

~~~java
openApi.addSecurityItem(
    new SecurityRequirement().addList("bearerAuth")
);
~~~

Nhưng không áp dụng security requirement toàn cục nếu group có endpoint public hoặc endpoint dùng cơ chế xác thực khác. Khi đó, đặt requirement ở operation bằng @SecurityRequirement hoặc customizer phù hợp. Scheme có thể dùng chung, còn requirement phải phản ánh chính sách từng endpoint.

Việc khai báo security trong OpenAPI chỉ mô tả cách client xác thực. Spring Security và gateway mới thực thi quyền truy cập. Không dùng tài liệu để thay thế cấu hình bảo mật runtime.

## 11. Tag và externalDocs dùng chung có chọn lọc

Tag giúp gom operation trong mỗi document. Nếu nhiều group có cùng miền, có thể dùng chung tên tag và mô tả, nhưng chỉ những tag có operation liên quan mới nên xuất hiện trong tài liệu.

Ví dụ:

~~~yaml
tags:
  - name: Orders
    description: Các thao tác quản lý đơn hàng
    externalDocs:
      description: Quy trình vòng đời đơn hàng
      url: https://docs.example.com/orders/lifecycle
~~~

Một số group có thể dùng tag Orders nhưng chỉ chứa operation dành cho partner. Description nên nói đúng phạm vi mà người dùng group đó được thấy. Nếu cùng tên tag nhưng ý nghĩa khác nhau theo audience, hãy chọn tên tag cụ thể hơn như Partner Orders hoặc Public Orders.

externalDocs ở cấp document phù hợp với hướng dẫn chung. Tài liệu chi tiết về quy trình partner nên gắn riêng với group hoặc tag partner tương ứng. Tránh đưa liên kết nội bộ hoặc tài liệu cần quyền truy cập của nhân viên vào public API document.

## 12. Tránh làm sai hợp đồng khi tùy biến metadata

Các lỗi thường gặp:

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng OpenApiCustomizer bean cho mọi group | Metadata chỉ xuất hiện trong default document | Dùng GlobalOpenApiCustomizer hoặc gắn customizer vào từng GroupedOpenApi |
| Ghi đè toàn bộ Info object | Mất contact, license, terms hoặc metadata của group | Sửa từng field trên Info hiện có |
| Dùng cùng title/description cho mọi audience | Người đọc không phân biệt được phạm vi hợp đồng | Đặt Info riêng theo group |
| Đặt server URL nội bộ trong tài liệu public | Client bên ngoài không truy cập được hoặc lộ hạ tầng | Dùng URL công khai đúng môi trường |
| Thêm security requirement toàn cục | Endpoint public bị mô tả nhầm là cần token | Chọn requirement theo operation hoặc group |
| Thêm component không có trong mọi document tham chiếu | $ref bị lỗi ở một số group | Kiểm tra components trong từng document |
| Dùng trùng tên tag cho hai ý nghĩa khác nhau | Swagger UI gom operation khó hiểu | Đặt tag name rõ phạm vi |
| Dùng group id làm API version | Người dùng nhầm URL tài liệu với version hợp đồng | Quản lý group id và Info.version riêng |
| Dựa vào thứ tự customizer không được bảo đảm | Metadata bị ghi đè tùy môi trường | Phân chia trách nhiệm field và kiểm thử output |

## 13. Ví dụ tổng hợp: metadata chung và metadata riêng

Một cấu hình hoàn chỉnh có thể chia trách nhiệm như sau:

~~~java
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.ExternalDocumentation;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.info.License;
import io.swagger.v3.oas.models.security.SecurityScheme;
import io.swagger.v3.oas.models.servers.Server;
import org.springdoc.core.customizers.GlobalOpenApiCustomizer;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.List;

@Configuration
class ApiDocumentationConfig {

    @Bean
    OpenAPI sharedOpenAPI() {
        return new OpenAPI()
            .info(new Info()
                .title("Shop API")
                .version("v1")
                .termsOfService("https://developer.example.com/terms")
                .contact(new Contact()
                    .name("API Platform Team")
                    .email("api-support@example.com"))
                .license(new License()
                    .name("Internal API License")
                    .url("https://developer.example.com/license")))
            .components(new Components()
                .addSecuritySchemes("bearerAuth",
                    new SecurityScheme()
                        .type(SecurityScheme.Type.HTTP)
                        .scheme("bearer")
                        .bearerFormat("JWT")));
    }

    @Bean
    GlobalOpenApiCustomizer commonMetadata() {
        return openApi -> {
            if (openApi.getExternalDocs() == null) {
                openApi.setExternalDocs(new ExternalDocumentation()
                    .description("Cổng tài liệu dành cho nhà phát triển")
                    .url("https://developer.example.com"));
            }
        };
    }

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public-api")
            .pathsToMatch("/api/public/**")
            .addOpenApiCustomizer(openApi -> {
                Info info = openApi.getInfo();
                if (info == null) {
                    info = new Info();
                    openApi.setInfo(info);
                }
                info.setTitle("Public API");
                info.setVersion("v1");
                info.setDescription("Hợp đồng dành cho ứng dụng và khách hàng công khai.");
                openApi.setServers(List.of(
                    new Server().url("https://api.example.com")
                        .description("Public production")
                ));
            })
            .build();
    }

    @Bean
    GroupedOpenApi partnerApi() {
        return GroupedOpenApi.builder()
            .group("partner-api")
            .pathsToMatch("/api/partner/**")
            .addOpenApiCustomizer(openApi -> {
                Info info = openApi.getInfo();
                if (info == null) {
                    info = new Info();
                    openApi.setInfo(info);
                }
                info.setTitle("Partner API");
                info.setVersion("v2");
                info.setDescription("Hợp đồng dành cho đối tác tích hợp.");
                openApi.setServers(List.of(
                    new Server().url("https://partner-api.example.com")
                        .description("Partner production")
                ));
            })
            .build();
    }
}
~~~

Ví dụ tổng hợp minh họa cách chia phần dùng chung và riêng. Các import được liệt kê trong đoạn mã; hãy kiểm tra phiên bản springdoc để xác nhận package của GroupedOpenApi và GlobalOpenApiCustomizer.

Trong ví dụ, OpenAPI bean cung cấp contact, license, terms và security scheme. GlobalOpenApiCustomizer bổ sung externalDocs cho mọi tài liệu nếu chưa có. Mỗi group đặt title, version, description và server riêng. Security requirement chưa được thêm toàn cục vì chính sách xác thực có thể khác theo operation.

## 14. Kiểm tra metadata trên từng tài liệu

Sau khi khởi động ứng dụng, lấy từng OpenAPI document:

~~~bash
# Tài liệu mặc định
curl -sS http://localhost:8080/v3/api-docs

# Tài liệu public
curl -sS http://localhost:8080/v3/api-docs/public-api

# Tài liệu partner
curl -sS http://localhost:8080/v3/api-docs/partner-api
~~~

Nếu có jq, kiểm tra nhanh phần metadata:

~~~bash
curl -sS http://localhost:8080/v3/api-docs/public-api \
  | jq '{info, servers, tags, security, components}'
~~~

Thực hiện kiểm tra tương tự với partner-api và đối chiếu:

1. Title, version và description có đúng audience không?
2. Contact, license và terms có thống nhất theo chính sách chung không?
3. Servers có đúng host công khai của group không?
4. Security scheme có xuất hiện ở nơi cần dùng không?
5. Security requirement có phản ánh đúng endpoint public và protected không?
6. Tags và externalDocs có mô tả đúng phạm vi group không?
7. Các $ref tới schemas, parameters và responses có tồn tại trong cùng document không?
8. Không có hostname nội bộ, endpoint không công bố hoặc metadata của audience khác bị lộ?

Swagger UI chỉ là giao diện đọc tài liệu. JSON/YAML ở endpoint OpenAPI mới là đầu ra cần kiểm tra khi xác nhận hợp đồng.

## 15. Kiểm thử và quản lý thay đổi metadata

Nên có integration test cho từng group để kiểm tra các metadata quan trọng. Test có thể tải endpoint OpenAPI rồi xác nhận title, version, servers, security scheme và một số path đại diện.

Ví dụ ý tưởng kiểm thử:

~~~java
mockMvc.perform(get("/v3/api-docs/partner-api"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.info.title").value("Partner API"))
    .andExpect(jsonPath("$.info.version").value("v2"))
    .andExpect(jsonPath("$.servers[0].url")
        .value("https://partner-api.example.com"));
~~~

Khi thay đổi metadata chung, hãy kiểm tra tất cả group vì GlobalOpenApiCustomizer và OpenAPI bean có thể ảnh hưởng đồng thời tới nhiều tài liệu. Khi thay đổi customizer riêng, kiểm tra group đích và các group không liên quan để bảo đảm chúng không bị thay đổi ngoài ý muốn.

Có thể lưu các file OpenAPI đã xuất trong CI và chạy contract diff để phát hiện thay đổi không tương thích. Metadata title hoặc description thường không làm thay đổi cấu trúc request/response, nhưng thay server, security, schema hoặc path có thể ảnh hưởng trực tiếp tới client.

## 16. Quy trình tổ chức metadata

Khi một ứng dụng có nhiều tài liệu:

1. Liệt kê metadata chung của tổ chức và metadata riêng của từng group.
2. Chọn OpenAPI bean hoặc @OpenAPIDefinition cho thông tin dùng chung.
3. Dùng GlobalOpenApiCustomizer cho quy tắc cần áp dụng trên mọi tài liệu.
4. Dùng OpenApiCustomizer gắn với GroupedOpenApi để đặt title, version, description hoặc server riêng.
5. Giữ security scheme dùng chung nếu phù hợp, nhưng đặt security requirement theo đúng operation/group.
6. Đảm bảo components và $ref tồn tại trong từng document.
7. Kiểm tra JSON/YAML của mọi group sau khi thay đổi.
8. Thêm integration test và contract diff để bảo vệ metadata và hợp đồng theo thời gian.

Khi metadata chung và riêng có ranh giới rõ ràng, các tài liệu OpenAPI giữ được nhận diện thống nhất của tổ chức mà vẫn phản ánh đúng người dùng, máy chủ, phiên bản và chính sách của từng nhóm.

## Tài liệu tham khảo

- [springdoc-openapi – FAQ: Customize OpenAPI object and grouped definitions](https://springdoc.org/faq.html)
- [springdoc-openapi v2 – FAQ for Spring Boot 3](https://springdoc.org/v2/faq.html)
- [OpenAPI Specification – Info Object](https://spec.openapis.org/oas/latest.html#info-object)
- [OpenAPI Specification – Server Object](https://spec.openapis.org/oas/latest.html#server-object)
- [OpenAPI Specification – Security Requirement Object](https://spec.openapis.org/oas/latest.html#security-requirement-object)
