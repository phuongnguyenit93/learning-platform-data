# Nhiều scheme cùng bắt buộc so với nhiều phương án thay thế

Một API có thể hỗ trợ nhiều cơ chế xác thực: bearer token, API key, HTTP Basic hoặc OAuth2. Khi mô tả bảo mật bằng OpenAPI, cần xác định client phải cung cấp đồng thời nhiều cơ chế hay chỉ cần chọn một trong các phương án được hỗ trợ.

OpenAPI biểu diễn hai trường hợp này bằng cấu trúc Security Requirement:

- Nhiều security scheme bên trong cùng một Security Requirement Object có nghĩa là tất cả scheme đều phải được đáp ứng (AND).
- Nhiều Security Requirement Object trong mảng security có nghĩa là chỉ cần đáp ứng một object bất kỳ (OR).

Đây là khác biệt cốt lõi khi mô tả bảo mật bằng springdoc-openapi. Nếu đảo nhầm hai cấu trúc, Swagger UI có thể hướng dẫn client gửi sai thông tin xác thực và tài liệu sẽ không phản ánh đúng chính sách API.

## 1. Phân biệt Security Scheme và Security Requirement

Hai thành phần này trả lời hai câu hỏi khác nhau:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| Security Scheme | Định nghĩa một cơ chế xác thực có thể dùng | Bearer JWT, API key trong header, OAuth2 |
| Security Requirement | Chỉ ra operation cần cơ chế nào | Bearer JWT và Partner API key cùng lúc |

Security Scheme thường được khai báo trong components.securitySchemes. Security Requirement được đặt ở cấp document hoặc operation thông qua trường security.

Ví dụ định nghĩa hai scheme:

~~~yaml
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
    partnerApiKey:
      type: apiKey
      in: header
      name: X-Partner-Key
~~~

Định nghĩa này chỉ tạo hai cơ chế có thể tham chiếu. Nó chưa nói endpoint cần cả hai hay chỉ một trong hai. Điều đó được quyết định bởi cấu trúc security.

## 2. Nhiều scheme trong cùng object là AND

Nếu một operation cần đồng thời bearer token và API key, đặt cả hai tên scheme trong cùng một Security Requirement Object:

~~~yaml
security:
  - bearerAuth: []
    partnerApiKey: []
~~~

Client phải gửi cả hai:

~~~http
POST /api/partner/orders
Authorization: Bearer eyJhbGciOi...
X-Partner-Key: partner-key-value
Content-Type: application/json
~~~

Nếu thiếu bearer token hoặc thiếu API key, request không đáp ứng requirement được công bố. Cách biểu diễn này phù hợp khi hệ thống cần danh tính người dùng/dịch vụ qua bearer token và đồng thời cần khóa định danh đối tác qua API key.

Một Security Requirement Object có thể chứa nhiều scheme. Tất cả scheme trong object đó phải được thỏa mãn để object được xem là hợp lệ.

## 3. Nhiều object trong mảng là OR

Nếu API chấp nhận bearer token hoặc API key như hai phương án độc lập, khai báo hai object riêng:

~~~yaml
security:
  - bearerAuth: []
  - partnerApiKey: []
~~~

Client có thể chọn một trong hai cách:

~~~http
GET /api/orders
Authorization: Bearer eyJhbGciOi...
~~~

Hoặc:

~~~http
GET /api/orders
X-Partner-Key: partner-key-value
~~~

Hai object nằm ở hai phần tử riêng của mảng security, do đó chúng biểu diễn các phương án thay thế. Client không cần cung cấp cả hai chỉ vì cả hai scheme cùng xuất hiện trong tài liệu.

## 4. So sánh trực tiếp AND và OR

| YAML | Logic | Điều kiện để request được chấp nhận theo hợp đồng |
| --- | --- | --- |
| Một object chứa bearerAuth và partnerApiKey | AND | Phải có cả bearer token và partner key |
| Hai object riêng, một chứa bearerAuth và một chứa partnerApiKey | OR | Có bearer token hoặc partner key |
| Một object chứa oauth2 với scope orders:read | Một scheme với scope | Token OAuth phải có scope orders:read |
| Một object rỗng {} | Anonymous | Cho phép request không xác thực |

Hãy chú ý dấu thụt dòng YAML. Chỉ cần đặt partnerApiKey thành một phần tử mới của mảng, logic đã chuyển từ AND sang OR.

## 5. Khai báo security scheme bằng annotation

Springdoc đọc các annotation của swagger-core để tạo security scheme. Có thể đặt nhiều SecurityScheme trên một class cấu hình:

~~~java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeIn;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.annotations.security.SecuritySchemes;
import org.springframework.context.annotation.Configuration;

@Configuration
@SecuritySchemes({
    @SecurityScheme(
        name = "bearerAuth",
        type = SecuritySchemeType.HTTP,
        scheme = "bearer",
        bearerFormat = "JWT",
        description = "Access token dạng JWT."
    ),
    @SecurityScheme(
        name = "partnerApiKey",
        type = SecuritySchemeType.APIKEY,
        in = SecuritySchemeIn.HEADER,
        paramName = "X-Partner-Key",
        description = "API key cấp cho đối tác."
    )
})
class ApiSecuritySchemes {
}
~~~

Các giá trị name là tên tham chiếu trong Security Requirement. Tên phải khớp chính xác với key trong components.securitySchemes. paramName là tên header/query parameter chứa API key; nó không phải tên scheme.

Không khai báo một API key như HTTP bearer chỉ vì cả hai đều được gửi trong header. Scheme cần phản ánh đúng cách server đọc credential.

## 6. Mô tả OR bằng @SecurityRequirement lặp lại

Annotation SecurityRequirement có thể lặp lại trên method hoặc class. Nhiều annotation riêng biệt biểu diễn nhiều requirement thay thế nhau, tức OR:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    @Operation(
        summary = "Lấy danh sách đơn hàng",
        security = {
            @SecurityRequirement(name = "bearerAuth"),
            @SecurityRequirement(name = "partnerApiKey")
        }
    )
    @GetMapping("/api/orders")
    List<OrderResponse> listOrders() {
        return orderService.findAll();
    }
}
~~~

Tài liệu sinh ra tương ứng:

~~~yaml
paths:
  /api/orders:
    get:
      security:
        - bearerAuth: []
        - partnerApiKey: []
~~~

Đây là hai phương án thay thế. Không dùng hai annotation lặp lại với kỳ vọng chúng có nghĩa là cả hai credential cùng bắt buộc.

## 7. Mô tả AND bằng annotation combine ở swagger-core phiên bản mới

Các phiên bản swagger-annotations mới có thuộc tính combine trên SecurityRequirement. Thuộc tính này cho phép gom nhiều scheme vào cùng một requirement object:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.security.SecurityRequirementEntry;

@Operation(
    summary = "Tạo đơn hàng dành cho đối tác",
    security = {
        @SecurityRequirement(
            combine = {
                @SecurityRequirementEntry(name = "bearerAuth"),
                @SecurityRequirementEntry(name = "partnerApiKey")
            }
        )
    }
)
~~~

Kết quả mong đợi:

~~~yaml
security:
  - bearerAuth: []
    partnerApiKey: []
~~~

combine có trong Javadoc của swagger-annotations 2.2.53. Không phải mọi phiên bản swagger-annotations đi kèm springdoc đều có thuộc tính này. Nếu IDE không nhận ra combine hoặc SecurityRequirementEntry, hãy kiểm tra phiên bản dependency thực tế; không nâng riêng swagger-annotations một cách tùy tiện nếu việc đó làm lệch phiên bản swagger-core mà springdoc đang dùng.

Với phiên bản cũ không có combine, dùng OpenAPI model trong customizer để tạo một requirement object chứa nhiều scheme.

## 8. Biểu diễn AND bằng OpenApiCustomizer

Có thể tạo requirement object trực tiếp bằng io.swagger.v3.oas.models.security.SecurityRequirement. Gọi addList nhiều lần trên cùng object để thêm các scheme vào cùng một requirement:

~~~java
import io.swagger.v3.oas.models.security.SecurityRequirement;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.List;

@Configuration
class PartnerSecurityConfig {

    @Bean
    OpenApiCustomizer partnerAndSecurity() {
        return openApi -> {
            SecurityRequirement requirement = new SecurityRequirement()
                .addList("bearerAuth")
                .addList("partnerApiKey");

            openApi.setSecurity(List.of(requirement));
        };
    }
}
~~~

Đoạn code đặt requirement ở cấp document mà customizer xử lý. Nếu customizer được gắn cho một GroupedOpenApi, requirement sẽ áp dụng cho tài liệu của group đó. Nếu dùng customizer mặc định độc lập, cần kiểm tra đúng document mà phiên bản springdoc áp dụng.

Để chỉ áp dụng cho một operation, sửa security của operation tương ứng:

~~~java
@Bean
OpenApiCustomizer partnerOrdersSecurity() {
    return openApi -> {
        if (openApi.getPaths() == null) {
            return;
        }

        var pathItem = openApi.getPaths().get("/api/partner/orders");
        if (pathItem == null || pathItem.getPost() == null) {
            return;
        }

        SecurityRequirement requirement = new SecurityRequirement()
            .addList("bearerAuth")
            .addList("partnerApiKey");

        pathItem.getPost().setSecurity(List.of(requirement));
    };
}
~~~

Khi dùng customizer, hãy bảo đảm cả hai scheme đã được khai báo trong components.securitySchemes. Security Requirement chỉ tham chiếu scheme; nó không tự định nghĩa scheme còn thiếu.

## 9. Biểu diễn OR bằng OpenApiCustomizer

Để tạo hai phương án thay thế bằng Java, tạo hai object riêng biệt trong danh sách:

~~~java
@Bean
OpenApiCustomizer partnerOrSecurity() {
    return openApi -> openApi.setSecurity(List.of(
        new SecurityRequirement().addList("bearerAuth"),
        new SecurityRequirement().addList("partnerApiKey")
    ));
}
~~~

Kết quả:

~~~yaml
security:
  - bearerAuth: []
  - partnerApiKey: []
~~~

Đừng gộp hai addList vào cùng object nếu mục tiêu là OR. Cũng đừng tạo hai object riêng nếu API bắt buộc cả hai credential.

## 10. Kết hợp OAuth2 scope với nhiều scheme

OAuth2/OpenID Connect có thể yêu cầu một hoặc nhiều scope. Scope là quyền cụ thể bên trong một scheme, khác với việc kết hợp nhiều scheme.

Ví dụ định nghĩa OAuth2:

~~~yaml
components:
  securitySchemes:
    oauth2:
      type: oauth2
      flows:
        clientCredentials:
          tokenUrl: https://auth.example.com/oauth/token
          scopes:
            orders:read: Đọc đơn hàng
            orders:write: Tạo hoặc cập nhật đơn hàng
~~~

Một requirement yêu cầu scope:

~~~yaml
security:
  - oauth2:
      - orders:read
      - orders:write
~~~

Đây vẫn là một scheme oauth2. Danh sách scope mô tả các quyền OAuth được yêu cầu, không phải hai phương thức xác thực thay thế.

Nếu API yêu cầu OAuth2 token và API key cùng lúc:

~~~yaml
security:
  - oauth2:
      - orders:write
    partnerApiKey: []
~~~

Cả OAuth2 với scope orders:write và partner API key đều phải được đáp ứng. Nếu muốn OAuth2 hoặc API key là hai phương án thay thế, đặt chúng trong hai object riêng.

Với annotation, SecurityRequirement(name = "oauth2", scopes = {"orders:read"}) mô tả scope của OAuth2 scheme. Với yêu cầu kết hợp nhiều scheme, dùng combine ở phiên bản hỗ trợ hoặc OpenAPI model customizer.

## 11. Bảo mật toàn cục và ghi đè ở operation

Có thể đặt security ở cấp document để làm mặc định cho mọi operation:

~~~yaml
security:
  - bearerAuth: []
~~~

Operation kế thừa yêu cầu này nếu không khai báo security riêng. Một operation có thể ghi đè chính sách mặc định.

Ví dụ endpoint health công khai:

~~~yaml
paths:
  /actuator/health:
    get:
      security: []
      responses:
        '200':
          description: Trạng thái ứng dụng
~~~

security: [] tại operation loại bỏ yêu cầu bảo mật được kế thừa từ cấp document. Nó có nghĩa operation không yêu cầu scheme nào theo hợp đồng OpenAPI.

Một trường hợp khác là endpoint cho phép anonymous hoặc bearer token:

~~~yaml
paths:
  /api/catalog:
    get:
      security:
        - {}
        - bearerAuth: []
~~~

Object rỗng {} là một requirement cho truy cập ẩn danh. Khi nằm cùng object bearerAuth trong mảng, client có thể gọi ẩn danh hoặc gửi bearer token.

Phân biệt:

| Khai báo ở operation | Ý nghĩa |
| --- | --- |
| Không có field security | Kế thừa security ở cấp document |
| security: [] | Gỡ yêu cầu bảo mật kế thừa; operation không yêu cầu xác thực theo OpenAPI |
| security: [{}] | Cho phép truy cập anonymous |
| security: [{}, {bearerAuth: []}] | Cho phép anonymous hoặc bearer token |
| security: [{bearerAuth: []}] | Bắt buộc bearer token |

Không thêm {} vào security nếu endpoint thực sự bắt buộc xác thực. Một requirement anonymous có thể khiến tài liệu nói rằng request không credential vẫn được phép.

## 12. Dùng @OpenAPIDefinition cho bảo mật mặc định

Có thể khai báo security requirement toàn cục bằng @OpenAPIDefinition:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    security = {
        @SecurityRequirement(name = "bearerAuth")
    }
)
class OpenApiDefinition {
}
~~~

Đoạn này đặt bearerAuth làm requirement mặc định ở cấp document. Operation cần bảo mật khác hoặc public có thể định nghĩa security riêng bằng @Operation hoặc customizer.

Khi khai báo nhiều SecurityRequirement ở cấp OpenAPI definition, chúng là các requirement thay thế nhau (OR). Nếu cần nhiều scheme cùng bắt buộc ở cấp toàn cục, dùng combine nếu phiên bản swagger-annotations hỗ trợ hoặc customizer tạo một SecurityRequirement model có nhiều key.

## 13. Ví dụ tổng hợp cho API đối tác

Giả sử API đối tác hỗ trợ hai cách gọi:

- Dịch vụ nội bộ của đối tác dùng bearer token.
- Một hệ thống cũ dùng API key.

Nếu server chấp nhận một trong hai phương án, tài liệu nên thể hiện OR:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeIn;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.annotations.security.SecuritySchemes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SecuritySchemes({
    @SecurityScheme(
        name = "bearerAuth",
        type = SecuritySchemeType.HTTP,
        scheme = "bearer",
        bearerFormat = "JWT"
    ),
    @SecurityScheme(
        name = "partnerApiKey",
        type = SecuritySchemeType.APIKEY,
        in = SecuritySchemeIn.HEADER,
        paramName = "X-Partner-Key"
    )
})
class PartnerSecuritySchemes {
}

@RestController
class PartnerOrderController {

    private final OrderService orderService;

    PartnerOrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @Operation(
        summary = "Tra cứu đơn hàng đối tác",
        security = {
            @SecurityRequirement(name = "bearerAuth"),
            @SecurityRequirement(name = "partnerApiKey")
        }
    )
    @GetMapping("/api/partner/orders")
    List<OrderResponse> listPartnerOrders() {
        return orderService.findPartnerOrders();
    }
}
~~~

Nếu yêu cầu bảo mật thay đổi thành bearer token và API key cùng bắt buộc, thay security thành một requirement kết hợp hoặc cấu hình customizer như phần trước. Không cần thay định nghĩa hai scheme; chỉ thay cách operation tham chiếu chúng.

## 14. Kiểm tra security trong tài liệu sinh ra

Sau khi cấu hình, gọi OpenAPI JSON:

~~~bash
curl -sS http://localhost:8080/v3/api-docs
~~~

Kiểm tra scheme:

~~~yaml
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
    partnerApiKey:
      type: apiKey
      in: header
      name: X-Partner-Key
~~~

Kiểm tra logic AND:

~~~yaml
security:
  - bearerAuth: []
    partnerApiKey: []
~~~

Kiểm tra logic OR:

~~~yaml
security:
  - bearerAuth: []
  - partnerApiKey: []
~~~

Checklist:

1. Mỗi tên trong security có scheme tương ứng trong components.securitySchemes không?
2. Nhiều scheme bắt buộc có nằm trong cùng một object không?
3. Các phương án thay thế có nằm thành các object riêng không?
4. OAuth2 scopes có đúng tên và đúng operation không?
5. Operation có ghi đè security toàn cục đúng chủ đích không?
6. Endpoint public có security: [] hoặc requirement {} đúng với ý định không?
7. Swagger UI có hiển thị lựa chọn xác thực phù hợp với cấu trúc tài liệu không?

Có thể kiểm tra bằng test JSON:

~~~java
mockMvc.perform(get("/v3/api-docs"))
    .andExpect(status().isOk())
    .andExpect(jsonPath(
        "$.paths['/api/partner/orders'].post.security[0].bearerAuth"
    ).exists())
    .andExpect(jsonPath(
        "$.paths['/api/partner/orders'].post.security[0].partnerApiKey"
    ).exists());
~~~

Để kiểm tra OR, xác nhận hai phần tử khác nhau trong mảng security, mỗi phần tử chứa một scheme. Không chỉ kiểm tra rằng cả hai tên đều xuất hiện ở đâu đó trong JSON.

## 15. Tài liệu OpenAPI không thay thế xác thực runtime

Security Scheme và Security Requirement chỉ mô tả hợp đồng cho client, Swagger UI và công cụ sinh mã. Chúng không tự cấu hình Spring Security, không tạo token và không kiểm tra header khi request tới server.

Ví dụ, tài liệu có thể mô tả AND giữa bearerAuth và partnerApiKey, nhưng nếu filter chain chỉ kiểm tra JWT và bỏ qua X-Partner-Key thì runtime không thực thi đầy đủ hợp đồng đó. Ngược lại, nếu server yêu cầu cả hai nhưng OpenAPI chỉ mô tả bearerAuth, client sẽ thiếu thông tin cần thiết.

Hãy kiểm thử hai lớp riêng:

| Lớp | Cần kiểm tra |
| --- | --- |
| OpenAPI contract | Cấu trúc security, scheme, scopes và override ở operation |
| Runtime authorization | Thiếu từng credential, credential sai, token hết hạn, API key không hợp lệ và trường hợp hợp lệ |

Với requirement AND, test runtime nên thử ít nhất bốn trường hợp: thiếu cả hai, chỉ có bearer, chỉ có API key và có đủ cả hai. Với OR, thử từng phương án hợp lệ riêng và một request không có phương án nào.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| API yêu cầu cả token và key nhưng Swagger UI chỉ yêu cầu một | Hai scheme được khai báo thành hai Security Requirement Object riêng | Đặt hai scheme trong cùng một object |
| API chấp nhận token hoặc key nhưng Swagger UI yêu cầu cả hai | Hai scheme được gộp trong cùng object | Tạo hai object riêng trong mảng security |
| Security requirement không được nhận diện | Tên scheme trong security không khớp component | Dùng cùng tên chính xác ở hai vị trí |
| Annotation AND không compile | swagger-annotations đang dùng chưa có thuộc tính combine | Dùng OpenApiCustomizer hoặc phiên bản có hỗ trợ tương thích |
| Endpoint public vẫn hiển thị khóa xác thực bắt buộc | Operation chưa ghi đè security toàn cục | Dùng security: [] hoặc requirement anonymous phù hợp |
| Swagger UI hiển thị scheme nhưng server không kiểm tra | Chỉ khai báo OpenAPI, chưa cấu hình filter/authorization | Cấu hình và test Spring Security |
| OAuth2 token bị từ chối dù đã đăng nhập | Thiếu scope được requirement yêu cầu | Cấp đúng scope và mô tả đúng trong OpenAPI |
| API key được gửi sai header | Scheme khai báo sai in hoặc name | Đồng bộ SecurityScheme với cách server đọc credential |

## 17. Quy trình thiết kế security requirement

Khi một operation hỗ trợ nhiều cơ chế xác thực:

1. Định nghĩa từng Security Scheme trong components.securitySchemes.
2. Xác định API cần tất cả scheme cùng lúc hay chỉ một phương án thay thế.
3. Dùng một Security Requirement Object chứa nhiều scheme cho AND.
4. Dùng nhiều Security Requirement Object riêng trong mảng security cho OR.
5. Đặt security ở cấp document nếu đó là mặc định thật sự; ghi đè ở operation khi cần.
6. Dùng {} khi cho phép anonymous và [] khi operation không kế thừa security nào.
7. Nếu dùng annotation, kiểm tra khả năng của phiên bản swagger-annotations; dùng customizer khi cần AND mà annotation hiện tại chưa hỗ trợ.
8. Kiểm tra OpenAPI JSON/YAML và Swagger UI.
9. Kiểm thử Spring Security/runtime độc lập với tài liệu.

Khi hiểu đúng quan hệ AND/OR, tài liệu OpenAPI sẽ mô tả chính xác client phải gửi những credential nào và có những phương án xác thực nào. Đây là cơ sở để Swagger UI, client generator và người tích hợp sử dụng API đúng cách.

## Tài liệu tham khảo

- [OpenAPI Specification – Security Requirement Object](https://spec.openapis.org/oas/v3.1.2.html#security-requirement-object)
- [OpenAPI Specification – Security Scheme Object](https://spec.openapis.org/oas/v3.1.2.html#security-scheme-object)
- [Swagger Core – @SecurityRequirement 2.2.53](https://docs.swagger.io/swagger-core/v2.2.53/apidocs/io/swagger/v3/oas/annotations/security/SecurityRequirement.html)
- [Swagger Core – @SecurityRequirementEntry 2.2.53](https://docs.swagger.io/swagger-core/v2.2.53/apidocs/io/swagger/v3/oas/annotations/security/SecurityRequirementEntry.html)
- [springdoc-openapi – Documentation](https://springdoc.org/)
