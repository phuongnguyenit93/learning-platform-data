# Phạm vi của customizer mặc định và customizer gắn với nhóm

Springdoc có thể tạo một tài liệu OpenAPI mặc định và nhiều tài liệu riêng thông qua `GroupedOpenApi`. Khi cần thêm metadata, server, security scheme, extension hoặc chỉnh sửa operation, customizer là một điểm mở rộng quan trọng. Tuy nhiên, phạm vi chạy của customizer phụ thuộc vào cách đăng ký: một bean `OpenApiCustomizer` thông thường phục vụ tài liệu mặc định; `GlobalOpenApiCustomizer` được áp dụng cho tài liệu mặc định và các group; còn customizer gắn trực tiếp vào `GroupedOpenApi.Builder` chỉ phục vụ group tương ứng.

Phân biệt đúng ba phạm vi này giúp tránh hai lỗi phổ biến: thay đổi dành cho một nhóm vô tình xuất hiện trong tài liệu khác, hoặc customizer tưởng đã áp dụng cho group nhưng thực tế chỉ chạy trên `/v3/api-docs`.

## 1. Tài liệu mặc định và tài liệu theo nhóm

Khi ứng dụng dùng Springdoc mà không khai báo group, endpoint tài liệu mặc định thường là:

```text
/v3/api-docs
```

Khi khai báo `GroupedOpenApi`, mỗi group có một tài liệu riêng. Ví dụ:

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

Các URL tài liệu tương ứng thường là:

| Tài liệu | URL mặc định |
|---|---|
| OpenAPI mặc định | `/v3/api-docs` |
| Group public | `/v3/api-docs/public` |
| Group admin | `/v3/api-docs/admin` |

Nếu đổi `springdoc.api-docs.path`, URL gốc sẽ thay đổi tương ứng. Group chỉ tạo document với phạm vi operation được lọc; nó không tạo route nghiệp vụ và không tự thực thi phân quyền.

Điểm quan trọng: tài liệu mặc định và các tài liệu group là những document riêng. Một customizer chạy trên document mặc định không mặc nhiên chạy trên tất cả document group.

## 2. Ba cách đăng ký customizer và phạm vi của chúng

Springdoc cung cấp ba cách chính để tùy biến OpenAPI document:

| Cách đăng ký | Phạm vi | Khi nên dùng |
|---|---|---|
| Bean `OpenApiCustomizer` | Document mặc định tại `/v3/api-docs` | Metadata hoặc thay đổi chỉ dành cho tài liệu mặc định |
| Bean `GlobalOpenApiCustomizer` | Document mặc định và mọi document được tạo từ `GroupedOpenApi` | Quy tắc thật sự dùng chung cho tất cả tài liệu |
| `.addOpenApiCustomizer(...)` trên `GroupedOpenApi.Builder` | Chỉ document của group đang cấu hình | Title, server, security hoặc metadata riêng của một group |

Ba cách này đều dùng logic tùy biến một `OpenAPI` model, nhưng phạm vi áp dụng khác nhau. Không nên chọn chỉ dựa trên tên interface; hãy chọn theo document nào cần nhận thay đổi.

### Bean `OpenApiCustomizer`: chỉ document mặc định

Ví dụ:

```java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class DefaultOpenApiConfiguration {

    @Bean
    OpenApiCustomizer defaultDocumentCustomizer() {
        return openApi -> {
            Info info = openApi.getInfo();
            if (info == null) {
                info = new Info();
                openApi.setInfo(info);
            }

            info.setDescription("Tài liệu OpenAPI mặc định của ứng dụng.");
            openApi.addExtension("x-document-scope", "default");
        };
    }
}
```

Bean này được Springdoc áp dụng cho tài liệu mặc định. Nếu ứng dụng có group `public` và `admin`, không nên kỳ vọng description hoặc extension trên tự xuất hiện trong `/v3/api-docs/public` và `/v3/api-docs/admin`.

Đây là lựa chọn phù hợp khi document mặc định đại diện cho toàn bộ API hoặc một hợp đồng tổng hợp, còn các group cần metadata riêng.

### Bean `GlobalOpenApiCustomizer`: document mặc định và mọi group

Nếu một quy tắc phải áp dụng cho tất cả document, dùng `GlobalOpenApiCustomizer`:

```java
import org.springdoc.core.customizers.GlobalOpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class GlobalOpenApiConfiguration {

    @Bean
    GlobalOpenApiCustomizer organizationCustomizer() {
        return openApi -> openApi.addExtension(
            "x-organization",
            "Example Platform"
        );
    }
}
```

Extension `x-organization` sẽ được thêm vào tài liệu mặc định và tài liệu của các group. Có thể dùng customizer toàn cục để bổ sung thông tin chủ sở hữu, chuẩn tuân thủ, mã hệ thống hoặc metadata dùng chung.

Không dùng customizer toàn cục cho dữ liệu chỉ thuộc một group. Ví dụ, nếu chỉ admin có server nội bộ hoặc security requirement riêng, đặt logic đó ở builder của group admin.

### Customizer gắn trực tiếp vào một group

Khi chỉ group admin cần thay title và server, gắn customizer trong builder của group:

```java
import java.util.List;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.servers.Server;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class AdminApiConfiguration {

    @Bean
    GroupedOpenApi adminApi() {
        return GroupedOpenApi.builder()
            .group("admin")
            .pathsToMatch("/api/admin/**")
            .addOpenApiCustomizer(openApi -> {
                Info info = openApi.getInfo();
                if (info == null) {
                    info = new Info();
                    openApi.setInfo(info);
                }
                info.setTitle("Administration API");
                info.setVersion("1.0.0");
                info.setDescription("Hợp đồng API dành cho giao diện quản trị.");

                openApi.setServers(List.of(
                    new Server()
                        .url("https://admin-api.example.com")
                        .description("Máy chủ API quản trị")
                ));
            })
            .build();
    }
}
```

Customizer này được gắn với group `admin`. Group `public` và document mặc định không nhận title hoặc server riêng này, trừ khi một customizer khác cũng thay đổi chúng.

Nếu muốn giữ server đã có rồi bổ sung server mới, dùng `addServersItem(...)` thay vì `setServers(...)`, vì `setServers(...)` thay toàn bộ danh sách.

## 3. Khi nhiều loại customizer cùng tồn tại

Một ứng dụng có thể đăng ký đồng thời cả ba cách:

```java
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springdoc.core.customizers.GlobalOpenApiCustomizer;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiCustomizationConfiguration {

    @Bean
    OpenApiCustomizer defaultDocumentCustomizer() {
        return openApi -> openApi.addExtension(
            "x-default-document",
            true
        );
    }

    @Bean
    GlobalOpenApiCustomizer globalDocumentCustomizer() {
        return openApi -> openApi.addExtension(
            "x-platform-owner",
            "API Platform Team"
        );
    }

    @Bean
    GroupedOpenApi adminApi() {
        return GroupedOpenApi.builder()
            .group("admin")
            .pathsToMatch("/api/admin/**")
            .addOpenApiCustomizer(openApi -> openApi.addExtension(
                "x-audience",
                "administrators"
            ))
            .build();
    }

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public")
            .pathsToMatch("/api/public/**")
            .build();
    }
}
```

Kết quả về phạm vi:

| Document | `x-default-document` | `x-platform-owner` | `x-audience` |
|---|---|---|---|
| `/v3/api-docs` | Có | Có | Không |
| `/v3/api-docs/admin` | Không | Có | Có |
| `/v3/api-docs/public` | Không | Có | Không |

Bảng trên thể hiện phạm vi đăng ký của từng customizer. Nó không phải thứ tự thực thi. Nếu nhiều customizer cùng sửa một field, kết quả cuối có thể phụ thuộc thứ tự mà Springdoc và Spring áp dụng chúng. Để dễ bảo trì, hãy để mỗi field có một nguồn sở hữu chính hoặc dùng những field/extension riêng biệt cho từng phạm vi.

## 4. Phân biệt OpenAPI customizer và operation customizer

Ngoài customizer cấp document, Springdoc còn hỗ trợ customizer cấp operation. Chúng khác nhau ở đối tượng được sửa:

| Interface hoặc builder method | Đối tượng nhận được | Phạm vi |
|---|---|---|
| `OpenApiCustomizer` bean | `OpenAPI` | Document mặc định |
| `GlobalOpenApiCustomizer` bean | `OpenAPI` | Document mặc định và group |
| `OperationCustomizer` bean | `Operation` và `HandlerMethod` | Operation trong document mặc định |
| `GlobalOperationCustomizer` bean | `Operation` và `HandlerMethod` | Operation trong document mặc định và group |
| `.addOpenApiCustomizer(...)` | `OpenAPI` | Document của group được cấu hình |
| `.addOperationCustomizer(...)` | `Operation` và `HandlerMethod` | Operation thuộc group được cấu hình |

Ví dụ `OperationCustomizer` bean chỉ dành cho tài liệu mặc định:

```java
import org.springdoc.core.customizers.OperationCustomizer;
import org.springframework.context.annotation.Bean;

@Bean
OperationCustomizer defaultOperationCustomizer() {
    return (operation, handlerMethod) -> {
        operation.addExtension("x-reviewed", true);
        return operation;
    };
}
```

Nếu muốn áp dụng quy tắc operation cho cả tài liệu mặc định và mọi group, dùng `GlobalOperationCustomizer`. Nếu chỉ muốn sửa operation trong một group, dùng `.addOperationCustomizer(...)` trên builder của group đó.

Ví dụ group admin chỉ gắn tag cho method được đánh dấu:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface AdminOnly {
}

@Configuration
class AdminOperationConfiguration {

    @Bean
    GroupedOpenApi adminApi() {
        return GroupedOpenApi.builder()
            .group("admin")
            .pathsToMatch("/api/admin/**")
            .addOperationCustomizer((operation, handlerMethod) -> {
                if (handlerMethod.getMethod().isAnnotationPresent(AdminOnly.class)) {
                    operation.addTagsItem("Administration");
                }
                return operation;
            })
            .build();
    }
}
```

`OperationCustomizer` chỉ sửa mô hình mô tả operation. Nó không thêm mapping, không thay HTTP method và không cấp quyền cho method đó.

## 5. Tùy biến metadata chung nhưng vẫn giữ thông tin riêng

Một lỗi dễ gặp là thay toàn bộ `Info` object trong customizer chung:

```java
openApi.setInfo(new Info().title("Company API"));
```

Nếu document đã có `version`, `description`, `contact` hoặc `license`, thao tác trên có thể làm mất các trường đó. Khi chỉ muốn bổ sung một thuộc tính, hãy sửa object hiện có:

```java
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import org.springdoc.core.customizers.GlobalOpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class CommonMetadataConfiguration {

    @Bean
    GlobalOpenApiCustomizer contactCustomizer() {
        return openApi -> {
            Info info = openApi.getInfo();
            if (info == null) {
                info = new Info();
                openApi.setInfo(info);
            }
            info.setContact(new Contact()
                .name("API Platform Team")
                .email("api-platform@example.com"));
        };
    }
}
```

Có thể đặt contact trong `GlobalOpenApiCustomizer` để mọi document có cùng thông tin liên hệ. Sau đó, customizer riêng của group chỉ thay title, description hoặc server của group mà không xóa contact chung.

## 6. Kết hợp customizer mặc định với `GroupedOpenApi`

Ví dụ đầy đủ dưới đây cho thấy một document mặc định, một group public và một group admin cùng tồn tại:

```java
import io.swagger.v3.oas.models.info.Info;
import org.springdoc.core.customizers.GlobalOpenApiCustomizer;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiConfiguration {

    @Bean
    OpenApiCustomizer defaultCustomizer() {
        return openApi -> {
            Info info = openApi.getInfo();
            if (info != null) {
                info.setDescription("Tài liệu tổng hợp của ứng dụng.");
            }
        };
    }

    @Bean
    GlobalOpenApiCustomizer globalCustomizer() {
        return openApi -> openApi.addExtension("x-platform", "springdoc");
    }

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public")
            .pathsToMatch("/api/public/**")
            .addOpenApiCustomizer(openApi -> {
                if (openApi.getInfo() != null) {
                    openApi.getInfo().setTitle("Public API");
                }
            })
            .build();
    }

    @Bean
    GroupedOpenApi adminApi() {
        return GroupedOpenApi.builder()
            .group("admin")
            .pathsToMatch("/api/admin/**")
            .addOpenApiCustomizer(openApi -> {
                if (openApi.getInfo() != null) {
                    openApi.getInfo().setTitle("Administration API");
                }
            })
            .build();
    }
}
```

Theo phạm vi đăng ký:

- `/v3/api-docs` nhận `defaultCustomizer` và `globalCustomizer`.
- `/v3/api-docs/public` nhận `globalCustomizer` và customizer gắn với group public.
- `/v3/api-docs/admin` nhận `globalCustomizer` và customizer gắn với group admin.

Do đó, description “Tài liệu tổng hợp của ứng dụng” chỉ thuộc document mặc định; title của từng group được đặt tại builder tương ứng; extension `x-platform` xuất hiện trong mọi document.

## 7. Phạm vi customizer không phải phạm vi bảo mật

Tách tài liệu bằng group hoặc chỉ định customizer riêng không tự bảo vệ endpoint. Ví dụ, customizer có thể thêm `security` vào tài liệu admin, nhưng server vẫn cần Spring Security để xác thực và phân quyền request thực tế.

Tương tự, document `/v3/api-docs/admin` có thể chứa đường dẫn quản trị dù API runtime đã được bảo vệ. Nếu chính sách yêu cầu tài liệu admin chỉ dành cho người dùng nội bộ, cần bảo vệ endpoint API Docs tương ứng và giao diện Swagger UI theo cấu hình bảo mật. Không dựa vào customizer hoặc tên group như một ranh giới truy cập.

## 8. Kiểm chứng customizer đã chạy trên đúng document

Sau khi khởi động ứng dụng, gọi trực tiếp từng endpoint tài liệu. Ví dụ:

```bash
curl -s http://localhost:8080/v3/api-docs | jq '.info, .["x-document-scope"], .["x-platform-owner"]'
curl -s http://localhost:8080/v3/api-docs/admin | jq '.info, .["x-platform-owner"], .["x-audience"]'
curl -s http://localhost:8080/v3/api-docs/public | jq '.info, .["x-platform-owner"], .["x-audience"]'
```

Khi chẩn đoán, kiểm tra riêng:

1. URL đang gọi là document mặc định hay document group.
2. Customizer được đăng ký dưới dạng bean `OpenApiCustomizer`, bean `GlobalOpenApiCustomizer` hay builder method.
3. Group có đúng `group` name và filter không.
4. Giá trị cần kiểm tra nằm ở cấp document (`info`, `servers`, `components`) hay cấp operation (`paths`).
5. Có customizer nào khác sửa cùng field sau đó không.

Không chỉ quan sát Swagger UI. UI có thể đang tải URL group khác hoặc giữ cache trình duyệt. Gọi trực tiếp endpoint JSON/YAML sẽ giúp xác định customizer đã thay đổi document nào.

### Kiểm thử phạm vi bằng MockMvc

Có thể kiểm tra sự hiện diện/vắng mặt của metadata ở từng document:

```java
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
class OpenApiCustomizerScopeTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void defaultCustomizerOnlyChangesDefaultDocument() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.info.description")
                .value("Tài liệu tổng hợp của ứng dụng."));

        mockMvc.perform(get("/v3/api-docs/admin"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.info.description").doesNotExist());
    }

    @Test
    void globalAndGroupCustomizersApplyToAdminDocument() throws Exception {
        mockMvc.perform(get("/v3/api-docs/admin"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.info.title").value("Administration API"))
            .andExpect(jsonPath("$['x-platform']").value("springdoc"));
    }
}
```

Các assertion phải khớp metadata mà ứng dụng thực sự cấu hình. Nếu API Docs được bảo vệ bằng Spring Security, test cần cung cấp authentication phù hợp thay vì mở endpoint trong môi trường production.

## 9. Những nhầm lẫn thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `OpenApiCustomizer` bean không thay đổi group document | Bean này được áp dụng cho document mặc định | Dùng `GlobalOpenApiCustomizer` hoặc `.addOpenApiCustomizer(...)` trên group |
| Metadata group admin xuất hiện trong document public | Đăng ký thay đổi bằng customizer toàn cục | Chuyển logic sang builder của group admin |
| Customizer group không tác động `/v3/api-docs` | Builder customizer chỉ gắn với group | Đăng ký riêng `OpenApiCustomizer` nếu document mặc định cũng cần thay đổi |
| Operation customizer không chạy trên group | Dùng `OperationCustomizer` bean thay vì `GlobalOperationCustomizer` hoặc builder method | Chọn đúng phạm vi operation |
| Title hoặc contact bị mất | Thay toàn bộ `Info` object | Sửa field cần thiết trên object hiện có |
| Kết quả khác khi có nhiều customizer | Nhiều customizer cùng sửa một field hoặc thứ tự thực thi khác | Tách trách nhiệm và kiểm tra document cuối |
| Security trong document nhưng API vẫn mở | Nhầm metadata OpenAPI với authorization runtime | Cấu hình Spring Security độc lập |
| Swagger UI cho thấy kết quả cũ | UI tải sai URL group hoặc cache | Gọi trực tiếp endpoint tài liệu và kiểm tra URL UI |

## 10. Nguyên tắc chọn phạm vi

- Dùng bean `OpenApiCustomizer` khi chỉ document mặc định cần thay đổi.
- Dùng bean `GlobalOpenApiCustomizer` khi mọi document đều cần cùng một quy tắc.
- Dùng `.addOpenApiCustomizer(...)` khi thay đổi chỉ thuộc một group.
- Dùng bean `OperationCustomizer` cho operation trong document mặc định.
- Dùng `GlobalOperationCustomizer` cho quy tắc operation trên document mặc định và các group.
- Dùng `.addOperationCustomizer(...)` cho operation thuộc một group cụ thể.
- Không để customizer toàn cục sửa các trường cần giá trị riêng theo group.
- Không thay toàn bộ object metadata khi chỉ cần đổi một field.
- Kiểm tra trực tiếp JSON/YAML của document mặc định và từng group sau khi thay đổi.

## 11. Checklist trước khi phát hành cấu hình customizer

- [ ] Đã xác định document cần thay đổi: mặc định, một group hay tất cả group.
- [ ] Đã chọn đúng `OpenApiCustomizer`, `GlobalOpenApiCustomizer` hoặc builder customizer.
- [ ] Nếu sửa operation, đã chọn đúng `OperationCustomizer`, `GlobalOperationCustomizer` hoặc `.addOperationCustomizer(...)`.
- [ ] Customizer riêng của group được gắn vào đúng `GroupedOpenApi`.
- [ ] Customizer toàn cục chỉ chứa quy tắc dùng chung.
- [ ] Các customizer không ghi đè metadata của nhau ngoài ý muốn.
- [ ] `Info`, `Servers`, `Components` được cập nhật mà không làm mất field không liên quan.
- [ ] Đã kiểm tra `/v3/api-docs` và từng `/v3/api-docs/{group}`.
- [ ] Đã xác nhận group filters đưa đúng operation vào document.
- [ ] Đã kiểm tra bảo mật endpoint tài liệu và API runtime độc lập.

Phạm vi customizer được quyết định bởi cách đăng ký. Bean `OpenApiCustomizer` tác động lên tài liệu mặc định; bean `GlobalOpenApiCustomizer` tác động lên tài liệu mặc định và các group; `.addOpenApiCustomizer(...)` chỉ tác động group được cấu hình. Với operation cũng có các lựa chọn tương ứng. Khi xác định rõ document mục tiêu trước khi viết customizer và kiểm tra từng URL tài liệu sau đó, thay đổi sẽ xuất hiện đúng nơi cần thiết và không lan sang các hợp đồng API khác.

## Tài liệu tham khảo

- [Springdoc OpenAPI – Official documentation](https://springdoc.org/)
- [Springdoc OpenAPI v2 – FAQ](https://springdoc.org/v2/#faq)
- [Springdoc OpenAPI – FAQ](https://springdoc.org/faq.html)
- [Springdoc OpenAPI – GitHub repository](https://github.com/springdoc/springdoc-openapi)
- [Springdoc – `SpringDocConfiguration` customizer registration](https://github.com/springdoc/springdoc-openapi/blob/main/springdoc-openapi-starter-common/src/main/java/org/springdoc/core/configuration/SpringDocConfiguration.java)
- [Springdoc – `GlobalOpenApiCustomizer` API](https://javadoc.io/doc/org.springdoc/springdoc-openapi-starter-common/latest/org/springdoc/core/customizers/GlobalOpenApiCustomizer.html)
- [Springdoc – `OpenApiCustomizer` API](https://javadoc.io/doc/org.springdoc/springdoc-openapi-starter-common/latest/org/springdoc/core/customizers/OpenApiCustomizer.html)
