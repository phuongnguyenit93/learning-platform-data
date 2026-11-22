# Tùy biến áp dụng riêng cho một nhóm

Một ứng dụng Spring Boot có thể công bố nhiều tài liệu OpenAPI bằng `GroupedOpenApi`: chẳng hạn tài liệu cho client công khai, tài liệu quản trị và tài liệu nội bộ. Các nhóm có thể dùng chung controller hoặc chứa những tập endpoint khác nhau. Trong nhiều trường hợp, mỗi nhóm còn cần metadata riêng như tiêu đề, phiên bản, server URL, tag, security requirement hoặc mô tả operation.

Springdoc cho phép gắn customizer trực tiếp vào cấu hình của một `GroupedOpenApi`. Cách này giới hạn thay đổi trong tài liệu của nhóm được chọn. Cần phân biệt nó với `OpenApiCustomizer` bean áp dụng cho tài liệu mặc định và `GlobalOpenApiCustomizer` bean áp dụng trên phạm vi toàn bộ tài liệu. Chọn đúng phạm vi customizer giúp tránh trường hợp thay đổi dành cho nhóm admin vô tình xuất hiện trong tài liệu public.

## 1. Mỗi group là một OpenAPI document riêng

Khi khai báo nhiều `GroupedOpenApi`, Springdoc tạo các tài liệu độc lập. Mỗi tài liệu có thể có `info`, `servers`, `tags`, `security`, `paths` và `components` riêng.

Ví dụ ứng dụng có ba nhóm:

| Group | Phạm vi endpoint | Mục đích tài liệu |
|---|---|---|
| `public` | `/api/public/**` | Hợp đồng dành cho ứng dụng khách |
| `admin` | `/api/admin/**` | Hợp đồng cho giao diện quản trị |
| `internal` | `/internal/**` | Hợp đồng cho tích hợp nội bộ |

Các endpoint tài liệu thường có dạng:

```text
/v3/api-docs/public
/v3/api-docs/admin
/v3/api-docs/internal
```

Swagger UI có thể tải từng URL và cho người dùng chọn tài liệu. Mỗi URL trả về một OpenAPI document riêng, nên group `admin` có thể đặt title, version và security requirement khác với group `public`.

Group chỉ tổ chức tài liệu và lọc operation được đưa vào document. Nó không tự tạo route mới, không thay đổi request mapping của controller và không thực thi quyền truy cập. Muốn bảo vệ API quản trị, ứng dụng vẫn cần cấu hình Spring Security hoặc cơ chế authorization runtime.

## 2. Tạo group bằng `GroupedOpenApi`

Trong Springdoc v2, `GroupedOpenApi` nằm trong package `org.springdoc.core.models`. Một group có thể lọc endpoint theo path, package, media type hoặc điều kiện method.

Ví dụ khai báo hai group:

```java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ApiGroupConfiguration {

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

`group(...)` đặt tên cho tài liệu. `pathsToMatch(...)` xác định các path được đưa vào group. Có thể dùng `packagesToScan(...)` khi muốn giới hạn theo package controller, hoặc kết hợp điều kiện lọc phù hợp với cách tổ chức ứng dụng.

Một endpoint có thể xuất hiện trong nhiều group nếu điều kiện lọc của các nhóm giao nhau. Đây là hành vi hợp lệ khi muốn cùng một operation được trình bày theo những tài liệu khác nhau. Nếu không muốn trùng, hãy thiết kế phạm vi path/package rõ ràng.

## 3. Gắn `OpenApiCustomizer` trực tiếp vào group

Để thay đổi metadata của riêng một nhóm, dùng `.addOpenApiCustomizer(...)` trong builder của group đó.

```java
import io.swagger.v3.oas.models.info.Info;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ApiGroupConfiguration {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public")
            .pathsToMatch("/api/public/**")
            .addOpenApiCustomizer(openApi -> {
                Info info = openApi.getInfo();
                if (info == null) {
                    info = new Info();
                    openApi.setInfo(info);
                }
                info.setTitle("Public API");
                info.setVersion("1.0.0");
                info.setDescription("Hợp đồng API dành cho các ứng dụng khách.");
            })
            .build();
    }
}
```

Customizer nhận mô hình `OpenAPI` đã được Springdoc tạo cho group. Có thể sửa `Info`, thêm `Server`, `Tag`, `SecurityScheme`, extension hoặc điều chỉnh các phần khác của document.

Trong ví dụ, customizer chỉ thay đổi `info` của group `public`. Các group khác không nhận title hoặc version này trừ khi chúng được gắn cùng customizer hoặc có một customizer toàn cục thay đổi các trường đó.

Nếu `Info` đã được tạo từ `@OpenAPIDefinition` hoặc bean `OpenAPI`, ví dụ trên giữ lại các thuộc tính khác và chỉ cập nhật title, version, description. Nếu thay toàn bộ bằng `openApi.setInfo(new Info()...)`, những metadata trước đó như contact, license hoặc terms of service có thể bị mất.

## 4. Phân biệt customizer theo phạm vi

Springdoc có nhiều extension point. Chọn loại phù hợp với phạm vi thay đổi:

| Cơ chế | Phạm vi áp dụng | Khi nào dùng |
|---|---|---|
| `.addOpenApiCustomizer(...)` trên `GroupedOpenApi.Builder` | Chỉ document của group đang cấu hình | Metadata, server, security hoặc components riêng cho một group |
| `.addOperationCustomizer(...)` trên `GroupedOpenApi.Builder` | Operation thuộc group đang cấu hình | Điều chỉnh summary, description, tag hoặc parameter theo handler trong một group |
| Bean `OpenApiCustomizer` | Tài liệu OpenAPI mặc định, không phải cách để áp dụng cho mọi group | Tùy biến document không chia nhóm |
| Bean `GlobalOpenApiCustomizer` | Tài liệu mặc định và các group | Quy tắc thật sự dùng chung cho tất cả document |
| Bean `OperationCustomizer` | Operation của tài liệu mặc định | Logic operation dùng chung cho tài liệu mặc định |
| Bean `GlobalOperationCustomizer` | Operation trong tài liệu mặc định và các group | Quy tắc operation thực sự dùng chung trên mọi document |

Nếu chỉ muốn đổi title cho group `admin`, hãy đặt customizer trong builder `adminApi()`. Không nên tạo một bean `OpenApiCustomizer` chung rồi kiểm tra tên group bằng giả định rằng bean đó chỉ được gọi cho một group.

Nếu muốn thêm một extension hoặc quy tắc chung vào mọi document, dùng `GlobalOpenApiCustomizer`; nếu muốn áp dụng logic ở cấp operation trên mọi document, dùng `GlobalOperationCustomizer`. Nếu có cả customizer toàn cục và customizer riêng của group, hãy kiểm tra kết quả cuối cùng vì customizer chạy sau có thể ghi đè trường đã được customizer trước đặt.

API và package customizer có thể thay đổi giữa các dòng Springdoc. Các ví dụ trong bài dùng Springdoc v2; hãy đối chiếu Javadoc của đúng phiên bản dependency trong dự án khi nâng cấp.

## 5. Tùy biến server URL riêng cho từng group

Các nhóm có thể được công bố qua server URL khác nhau. Ví dụ, tài liệu public dùng API gateway công khai còn tài liệu admin dùng hostname nội bộ.

```java
import java.util.List;
import io.swagger.v3.oas.models.servers.Server;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;

@Bean
GroupedOpenApi adminApi() {
    return GroupedOpenApi.builder()
        .group("admin")
        .pathsToMatch("/api/admin/**")
        .addOpenApiCustomizer(openApi -> openApi.setServers(List.of(
            new Server()
                .url("https://admin-api.example.com")
                .description("API quản trị")
        )))
        .build();
}
```

`setServers(...)` thay danh sách server của document bằng danh sách được cung cấp. Nếu muốn giữ server đã có và bổ sung thêm một server, dùng `addServersItem(...)` thay vì thay cả danh sách.

Server URL trong tài liệu phải là URL mà client thực sự có thể truy cập trong môi trường tương ứng. Không dùng hostname nội bộ hoặc URL test trong tài liệu public nếu client bên ngoài không thể truy cập. Khi ứng dụng chạy sau reverse proxy hoặc có context path, kiểm tra URL công khai và path trong document có ghép đúng hay không.

## 6. Tùy biến security riêng cho group

Một trường hợp thường gặp là group public không yêu cầu đăng nhập ở cấp document, trong khi group admin yêu cầu Bearer token. Có thể khai báo security scheme và security requirement trong customizer của group admin.

```java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.security.SecurityRequirement;
import io.swagger.v3.oas.models.security.SecurityScheme;

@Configuration
class AdminOpenApiConfiguration {

@Bean
GroupedOpenApi adminApi() {
    return GroupedOpenApi.builder()
        .group("admin")
        .pathsToMatch("/api/admin/**")
        .addOpenApiCustomizer(openApi -> {
            Components components = openApi.getComponents();
            if (components == null) {
                components = new Components();
                openApi.setComponents(components);
            }

            components.addSecuritySchemes(
                "bearerAuth",
                new SecurityScheme()
                    .type(SecurityScheme.Type.HTTP)
                    .scheme("bearer")
                    .bearerFormat("JWT")
            );

            openApi.addSecurityItem(
                new SecurityRequirement().addList("bearerAuth")
            );
        })
        .build();
}
}
```

Document admin sẽ có `components.securitySchemes.bearerAuth` và security requirement ở cấp tài liệu. Các operation kế thừa yêu cầu Bearer, trừ operation có security riêng ghi đè.

Nếu một operation trong group admin thực sự công khai, có thể khai báo security rỗng cho operation đó bằng annotation hoặc operation customizer thích hợp. OpenAPI dùng `security: []` để bỏ yêu cầu bảo mật kế thừa ở cấp document.

Lưu ý: security trong OpenAPI chỉ mô tả hợp đồng cho Swagger UI và công cụ client. Nó không cấu hình Spring Security. Hãy bảo vệ cả API admin và endpoint tài liệu `/v3/api-docs/admin` theo chính sách runtime. Việc Swagger UI hiển thị Authorize không đồng nghĩa server đã xác thực token.

## 7. Tùy biến operation trong một group

Nếu chỉ một số operation trong group cần metadata bổ sung, dùng `.addOperationCustomizer(...)`. Customizer nhận `Operation` cùng `HandlerMethod`, vì vậy có thể dựa vào annotation hoặc metadata của method để quyết định thay đổi.

Ví dụ tạo annotation đánh dấu operation cần mô tả nội bộ:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface AdminOperation {
    String description();
}
```

Controller sử dụng annotation:

```java
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping("/reports")
@AdminOperation(description = "Truy xuất báo cáo dành cho quản trị viên.")
List<ReportResponse> reports() {
    return reportService.findReports();
}
```

Gắn customizer vào group admin:

```java
import org.springdoc.core.customizers.OperationCustomizer;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;

@Bean
GroupedOpenApi adminApi() {
    return GroupedOpenApi.builder()
        .group("admin")
        .pathsToMatch("/api/admin/**")
        .addOperationCustomizer((operation, handlerMethod) -> {
            AdminOperation marker = handlerMethod.getMethod()
                .getAnnotation(AdminOperation.class);

            if (marker != null) {
                operation.setDescription(marker.description());
                operation.addTagsItem("Administration");
            }
            return operation;
        })
        .build();
}
```

Trong ví dụ, thay đổi chỉ được gắn vào các operation của group admin. Nếu một method không có `@AdminOperation`, operation giữ metadata mà Springdoc suy luận hoặc lấy từ Swagger annotations.

Không nên dùng customizer để thay đổi URL, HTTP method hoặc hành vi runtime. `OperationCustomizer` chỉ sửa mô hình OpenAPI; mapping của Spring vẫn quyết định request thật.

## 8. Kết hợp group filter và customizer

Một group thường có cả điều kiện lọc và customizer. Ví dụ group admin chỉ lấy endpoint trong package quản trị và path `/api/admin/**`, rồi bổ sung metadata riêng.

```java
import io.swagger.v3.oas.models.info.Info;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;

@Bean
GroupedOpenApi adminApi() {
    return GroupedOpenApi.builder()
        .group("admin")
        .packagesToScan("com.example.admin.web")
        .pathsToMatch("/api/admin/**")
        .pathsToExclude("/api/admin/internal/**")
        .addOpenApiCustomizer(openApi -> {
            Info info = openApi.getInfo();
            if (info != null) {
                info.setTitle("Administration API");
                info.setVersion("1.0.0");
            }
        })
        .build();
}
```

Trong cấu hình này:

- `packagesToScan` giới hạn package chứa controller được xem xét.
- `pathsToMatch` giới hạn path cần đưa vào document.
- `pathsToExclude` loại path nội bộ khỏi document.
- `addOpenApiCustomizer` thay đổi metadata của document sau khi Springdoc xây dựng nó.

Điều kiện lọc và customizer có trách nhiệm khác nhau. Filter chọn operation nào xuất hiện; customizer thay đổi cách document hoặc operation được mô tả. Nếu customizer tự thêm path mới vào mô hình, nó có thể làm document vượt ra ngoài phạm vi filter ban đầu; chỉ làm điều đó khi có chủ đích và kiểm thử rõ ràng.

## 9. Cấu hình Swagger UI để chọn đúng group

Sau khi tạo group, thêm URL tài liệu vào danh sách Swagger UI:

```yaml
springdoc:
  swagger-ui:
    urls:
      - name: Public API
        url: /v3/api-docs/public
      - name: Administration API
        url: /v3/api-docs/admin
      - name: Internal API
        url: /v3/api-docs/internal
    urls-primary-name: Public API
```

Swagger UI hiển thị danh sách tài liệu để người dùng chọn. `urls-primary-name` chọn group được mở mặc định trong danh sách. Nếu chỉ có một document, không cần cấu hình danh sách `urls`.

Tên trong `name` là nhãn hiển thị ở giao diện, còn `url` là endpoint tài liệu. Tên hiển thị không bắt buộc trùng với group ID, nhưng URL phải khớp chính xác tên group được khai báo bằng `.group(...)`.

Nếu Swagger UI và API Docs nằm sau gateway hoặc context path, hãy dùng URL tương đối/đường dẫn công khai phù hợp. Khi giao diện báo không tải được document, mở trực tiếp URL `/v3/api-docs/{group}` để tách lỗi tạo tài liệu khỏi lỗi cấu hình UI.

## 10. Tách customizer dùng chung và customizer riêng

Trong ứng dụng nhiều group, có thể có metadata chung như contact, license hoặc extension của tổ chức, đồng thời có metadata riêng cho từng nhóm. Hãy tách hai phạm vi.

Ví dụ customizer toàn cục:

```java
import io.swagger.v3.oas.models.info.Info;
import org.springdoc.core.customizers.GlobalOpenApiCustomizer;
import io.swagger.v3.oas.models.info.Contact;
import org.springframework.context.annotation.Bean;

@Bean
GlobalOpenApiCustomizer organizationMetadata() {
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
```

Customizer này áp dụng metadata contact cho tài liệu mặc định và các group. Sau đó, group-specific customizer có thể đặt title, version hoặc description riêng.

Ví dụ, group `admin` chỉ thay title và version trong customizer gắn trực tiếp vào builder. Contact do customizer toàn cục đặt vẫn được giữ vì code chỉ cập nhật hai field đó.

Khi nhiều customizer sửa cùng một trường, giá trị cuối phụ thuộc thứ tự thực thi. Không nên để customizer toàn cục và group-specific cùng ghi đè một field mà không có quy ước rõ. Nếu cần thứ tự, dùng cơ chế ordering được Spring hỗ trợ trong phiên bản đang chạy và kiểm tra document đầu ra.

## 11. Tái sử dụng cấu hình mà vẫn giữ phạm vi rõ ràng

Nếu nhiều group cần cùng một đoạn tùy biến, có thể tách thành hàm Java thuần và gọi từ builder của từng group. Cách này tái sử dụng logic mà vẫn làm rõ group nào đã đăng ký nó.

```java
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;

private OpenApiCustomizer apiContact(String teamName, String email) {
    return openApi -> {
        Info info = openApi.getInfo();
        if (info == null) {
            info = new Info();
            openApi.setInfo(info);
        }
        info.setContact(new Contact().name(teamName).email(email));
    };
}

@Bean
GroupedOpenApi publicApi() {
    return GroupedOpenApi.builder()
        .group("public")
        .pathsToMatch("/api/public/**")
        .addOpenApiCustomizer(apiContact("Public API Team", "public@example.com"))
        .build();
}

@Bean
GroupedOpenApi adminApi() {
    return GroupedOpenApi.builder()
        .group("admin")
        .pathsToMatch("/api/admin/**")
        .addOpenApiCustomizer(apiContact("Admin API Team", "admin@example.com"))
        .build();
}
```

Trong ví dụ này, mỗi group truyền metadata riêng. Không đăng ký một customizer như bean toàn cục nếu mục tiêu là chỉ áp dụng cho một số group.

## 12. Kiểm tra tài liệu của từng group

Không chỉ mở Swagger UI để kiểm tra bằng mắt. Hãy gọi trực tiếp từng endpoint OpenAPI và xác nhận `info`, `servers`, `security`, `paths` cùng operation metadata.

Ví dụ:

```bash
curl -s http://localhost:8080/v3/api-docs/public | jq '.info, .servers, (.paths | keys)'
curl -s http://localhost:8080/v3/api-docs/admin | jq '.info, .servers, .security, (.paths | keys)'
```

Kiểm tra các điều kiện:

- Document public có title/version và endpoint public như dự kiến.
- Document admin có title/version riêng và chứa đúng path quản trị.
- Security scheme được định nghĩa trước khi security requirement tham chiếu đến nó.
- Server URL tương ứng với môi trường công bố của group.
- Operation được customizer chỉnh sửa đúng; operation khác không bị tác động ngoài ý muốn.
- Không có path nội bộ hoặc operation nhạy cảm lọt vào group public.

Nếu dùng `pathsToMatch` và `packagesToScan` cùng lúc, hãy xác minh kết quả thực tế của điều kiện lọc bằng danh sách `paths`. Không suy luận chỉ từ tên package.

## 13. Kiểm thử group bằng MockMvc

Có thể kiểm tra từng document trong integration test. Ví dụ dưới đây giả định ứng dụng đã khai báo group `public` và `admin`:

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
class ApiGroupDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publicDocumentContainsOnlyPublicApiMetadataAndPaths() throws Exception {
        mockMvc.perform(get("/v3/api-docs/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.info.title").value("Public API"))
            .andExpect(jsonPath("$.paths['/api/public/orders']").exists())
            .andExpect(jsonPath("$.paths['/api/admin/users']").doesNotExist());
    }

    @Test
    void adminDocumentContainsAdminSecurity() throws Exception {
        mockMvc.perform(get("/v3/api-docs/admin"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.info.title").value("Administration API"))
            .andExpect(jsonPath("$.components.securitySchemes.bearerAuth").exists())
            .andExpect(jsonPath("$.security[0].bearerAuth").exists());
    }
}
```

Nếu endpoint API Docs được bảo vệ bằng Spring Security, test cần đăng nhập hoặc dùng cấu hình test security phù hợp. Đừng mở endpoint tài liệu trong production chỉ để test dễ hơn. Với test có customizer phụ thuộc bean hoặc profile, hãy khởi chạy đúng cấu hình gần với môi trường triển khai.

## 14. Lỗi thường gặp khi tùy biến theo group

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Title của admin xuất hiện trong public document | Dùng customizer bean ở phạm vi rộng hoặc dùng `GlobalOpenApiCustomizer` cho metadata riêng | Gắn customizer trực tiếp vào builder của group admin |
| Customizer không chạy cho group | Đăng ký `OpenApiCustomizer` bean và kỳ vọng nó tự áp dụng cho mọi group | Dùng `.addOpenApiCustomizer(...)` hoặc `GlobalOpenApiCustomizer` đúng mục đích |
| Group có path không mong muốn | Filter giao nhau hoặc package/path match quá rộng | Thu hẹp `pathsToMatch`, `pathsToExclude` và `packagesToScan` |
| Group admin thiếu security scheme | Chỉ thêm security requirement mà quên components scheme | Khai báo `components.securitySchemes` trong cùng document |
| Swagger UI không hiển thị group | URL trong `swagger-ui.urls` sai hoặc group ID không khớp | Gọi trực tiếp `/v3/api-docs/{group}` và sửa URL |
| Contact hoặc license bị mất | Customizer thay toàn bộ `Info` object | Sửa các field cần thiết trên Info hiện có |
| Customizer toàn cục ghi đè title riêng | Nhiều customizer cùng sửa một trường | Quy định rõ quyền sở hữu field và thứ tự thực thi |
| Tài liệu admin truy cập được công khai | Nhầm group document với security runtime | Bảo vệ endpoint API Docs và API bằng Spring Security |
| Cấu hình hoạt động khác sau nâng cấp | API/package customizer thay đổi giữa phiên bản | Đối chiếu Javadoc và kiểm thử lại từng group |

## 15. Nguyên tắc thiết kế customizer theo group

- Đặt customizer gần nơi khai báo `GroupedOpenApi` để thấy rõ phạm vi áp dụng.
- Dùng `addOpenApiCustomizer` cho thay đổi cấp document và `addOperationCustomizer` cho thay đổi cấp operation.
- Chỉ dùng `GlobalOpenApiCustomizer` cho quy tắc thật sự dùng chung.
- Không dựa vào `OpenApiCustomizer` bean thông thường để tùy biến tất cả group.
- Sửa từng field của `Info` khi muốn giữ contact, license hoặc metadata đã khai báo.
- Khai báo security scheme trước khi thêm security requirement tham chiếu đến nó.
- Không xem group là ranh giới bảo mật hoặc cơ chế versioning của runtime.
- Giữ group filters rõ ràng và kiểm tra các path giao nhau.
- Dùng URL đúng trong `springdoc.swagger-ui.urls`.
- Kiểm thử trực tiếp từng endpoint `/v3/api-docs/{group}` sau mọi thay đổi.

## 16. Checklist trước khi công bố nhiều nhóm tài liệu

- [ ] Mỗi group có tên ổn định và mục đích rõ ràng.
- [ ] `pathsToMatch`, `pathsToExclude` và `packagesToScan` phản ánh đúng phạm vi.
- [ ] Metadata riêng được gắn bằng customizer trực tiếp trên đúng builder.
- [ ] Customizer toàn cục chỉ chứa thông tin thực sự dùng chung.
- [ ] Không có customizer rộng vô tình ghi đè metadata riêng của group.
- [ ] `servers`, `security`, tags và components khớp với audience của group.
- [ ] Swagger UI liệt kê đúng document URL và tên hiển thị.
- [ ] Endpoint API Docs và API runtime được bảo vệ theo chính sách thực tế.
- [ ] Mỗi group được kiểm tra trực tiếp bằng HTTP hoặc integration test.
- [ ] Đã kiểm tra tác động khi nâng cấp Springdoc.

Tùy biến theo group nên được đặt ngay trên `GroupedOpenApi` tương ứng. `.addOpenApiCustomizer(...)` thay đổi document của một nhóm; `.addOperationCustomizer(...)` thay đổi operation trong nhóm đó. Bean `GlobalOpenApiCustomizer` dành cho quy tắc chung trên mọi document, còn `OpenApiCustomizer` bean thông thường phục vụ tài liệu mặc định. Giữ rõ phạm vi này giúp mỗi tài liệu có metadata, server và security đúng với đối tượng sử dụng mà không làm thay đổi hành vi runtime của controller.

## Tài liệu tham khảo

- [Springdoc OpenAPI – Official documentation](https://springdoc.org/)
- [Springdoc OpenAPI – FAQ](https://springdoc.org/faq.html)
- [Springdoc OpenAPI – GitHub repository](https://github.com/springdoc/springdoc-openapi)
- [Swagger Core – OpenAPI model classes](https://github.com/swagger-api/swagger-core)
