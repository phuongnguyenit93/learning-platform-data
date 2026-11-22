# bearerFormat như thông tin mô tả định dạng token

Trong OpenAPI, một API có thể yêu cầu client gửi bearer token qua HTTP header **Authorization**. Security Scheme mô tả cơ chế này bằng **type: http** và **scheme: bearer**. Thuộc tính **bearerFormat** bổ sung một gợi ý về định dạng token, chẳng hạn **JWT**.

Điều cần hiểu chính xác là bearerFormat chỉ là metadata mô tả trong tài liệu. Nó không xác định thuật toán ký, không giải mã token, không kiểm tra chữ ký, không xác minh claim và không cấu hình Spring Security. Việc xác thực token vẫn do cơ chế bảo mật runtime của ứng dụng thực hiện.

Trong springdoc-openapi, có thể khai báo bearer scheme bằng annotation **@SecurityScheme** hoặc cấu hình OpenAPI model. Sau đó, dùng **@SecurityRequirement** để gắn scheme vào toàn bộ tài liệu hoặc operation cụ thể. Bài này tập trung vào ý nghĩa của bearerFormat, cách mô tả đúng và cách kiểm tra tài liệu lẫn hành vi xác thực.

## 1. Bearer token được gửi như thế nào?

Với HTTP bearer authentication, client gửi token trong header:

~~~http
GET /api/profile
Authorization: Bearer eyJhbGciOi...
~~~

Trong đó:

- **Authorization** là tên HTTP header.
- **Bearer** là scheme trong giá trị header.
- Phần sau Bearer là token mà server nhận để xác thực.

OpenAPI mô tả cơ chế này bằng Security Scheme Object:

~~~yaml
type: http
scheme: bearer
bearerFormat: JWT
~~~

**scheme: bearer** xác định loại xác thực HTTP được dùng. **bearerFormat: JWT** chỉ cung cấp thông tin bổ sung rằng token dự kiến có định dạng JWT. Client vẫn gửi token theo quy ước bearer trong Authorization header.

Không nhầm bearer token với một loại token duy nhất. Bearer là cách trình bày thông tin xác thực trong HTTP; token mang theo có thể là JWT, token opaque hoặc một định dạng khác được hệ thống chấp nhận.

## 2. bearerFormat là gì?

**bearerFormat** là chuỗi tùy chọn trong HTTP Bearer Security Scheme của OpenAPI. Nó giúp người đọc hoặc công cụ hiểu định dạng token mà API dự kiến sử dụng.

Một số giá trị mô tả có thể gặp:

| Giá trị | Ý nghĩa mô tả |
|---|---|
| JWT | Token được thiết kế theo JSON Web Token |
| Opaque | Token không công khai cấu trúc nội bộ cho client |
| JWT (JWS) | Gợi ý token JWT được biểu diễn dưới dạng ký JWS |

Đây là giá trị văn bản tự do, không phải enum bắt buộc của OpenAPI. Các tên trên là quy ước mô tả; công cụ đọc tài liệu không được phép suy ra thuật toán, issuer hoặc quy tắc xác thực chỉ từ chuỗi này.

Ví dụ:

~~~yaml
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
      description: Access token dạng JWT gửi qua Authorization header.
~~~

Trong tài liệu, bearerFormat có thể được Swagger UI hoặc công cụ khác trình bày như một gợi ý. Giao diện cụ thể hiển thị nó ra sao phụ thuộc phiên bản công cụ. Việc đổi bearerFormat không làm thay đổi token được phát hành hoặc cách server xử lý request.

### bearerFormat không bắt buộc

Nếu hệ thống không muốn cam kết một định dạng cụ thể, có thể bỏ thuộc tính này:

~~~yaml
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      description: Access token gửi qua Authorization header.
~~~

Để trống bearerFormat thường tốt hơn việc ghi một giá trị đoán. Chỉ mô tả JWT khi token thực tế của hệ thống là JWT; nếu token opaque, hãy nói rõ trong description hoặc dùng nhãn mô tả phù hợp.

## 3. bearerFormat không phải cơ chế xác thực

Những trách nhiệm sau không thuộc bearerFormat:

- Phân tích cấu trúc compact của JWT dạng JWS; JWT dạng JWE có cấu trúc khác.
- Kiểm tra chữ ký hoặc thuật toán ký.
- Xác minh issuer, audience, expiration hoặc not-before.
- Kiểm tra token bị thu hồi hay chưa.
- Gọi endpoint introspection cho opaque token.
- Ánh xạ claim hoặc scope thành quyền truy cập.
- Từ chối request thiếu token hoặc token không hợp lệ.

Ví dụ, hai tài liệu sau chỉ khác nhãn mô tả:

~~~yaml
bearerAuth:
  type: http
  scheme: bearer
  bearerFormat: JWT
~~~

~~~yaml
bearerAuth:
  type: http
  scheme: bearer
  bearerFormat: Opaque
~~~

Không có dòng nào trong hai cấu hình trên tự khiến Spring Security chuyển sang JWT decoder hoặc opaque token introspection. Ứng dụng phải được cấu hình riêng để xác minh loại token thực tế.

Nếu API khai báo bearerFormat là JWT nhưng server chấp nhận token opaque, tài liệu đang mô tả sai kỳ vọng của client. Ngược lại, nếu đổi thành Opaque mà server vẫn xác minh JWT, hành vi runtime không thay đổi nhưng tài liệu gây hiểu nhầm.

## 4. Khai báo HTTP bearer scheme bằng @SecurityScheme

Trong springdoc-openapi 2.x, có thể dùng annotation từ swagger-annotations để khai báo scheme:

~~~java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import org.springframework.context.annotation.Configuration;

@Configuration
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT",
    description = "Access token dạng JWT trong Authorization header."
)
public class OpenApiSecurityConfiguration {
}
~~~

Các thuộc tính chính:

| Thuộc tính | Vai trò |
|---|---|
| **name** | Tên định danh scheme trong components/securitySchemes |
| **type** | Loại scheme; với HTTP bearer là SecuritySchemeType.HTTP |
| **scheme** | Tên HTTP authentication scheme; bearer cần viết là bearer |
| **bearerFormat** | Gợi ý định dạng token, ví dụ JWT |
| **description** | Mô tả cách client lấy và gửi token |

Tên **bearerAuth** là tên do ứng dụng lựa chọn. Tên này phải khớp với Security Requirement tham chiếu tới scheme.

### Scheme name không phải token format

Trong ví dụ:

- bearerAuth là tên tham chiếu của security scheme.
- bearer là HTTP authentication scheme.
- JWT là bearerFormat.

Ba giá trị này có vai trò khác nhau. Không đặt name thành JWT rồi tưởng rằng token format đã được cấu hình; cũng không đổi scheme thành JWT vì JWT không phải HTTP authentication scheme.

## 5. Đăng ký scheme không tự áp dụng bảo mật cho operation

Khai báo @SecurityScheme tạo định nghĩa trong components. Để operation yêu cầu scheme đó, cần thêm **Security Requirement**.

Gắn cho một operation:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;

@RestController
@RequestMapping("/api/profile")
public class ProfileController {

    @Operation(
        summary = "Lấy hồ sơ hiện tại",
        security = @SecurityRequirement(name = "bearerAuth")
    )
    @GetMapping
    public ProfileResponse currentProfile() {
        // ...
        return null;
    }
}
~~~

Hoặc dùng annotation @SecurityRequirement trực tiếp ở cấp class hoặc method:

~~~java
@SecurityRequirement(name = "bearerAuth")
@RestController
@RequestMapping("/api/orders")
public class OrderController {
    // Các operation của controller được mô tả với yêu cầu bearerAuth
}
~~~

Định nghĩa scheme và áp dụng requirement là hai bước khác nhau:

1. **Security Scheme** mô tả cơ chế xác thực.
2. **Security Requirement** cho biết operation hoặc toàn tài liệu yêu cầu cơ chế nào.

Nếu chỉ có components.securitySchemes mà không có security requirement, Swagger UI có thể biết scheme tồn tại nhưng tài liệu không chỉ ra operation nào yêu cầu nó.

## 6. Áp dụng bearer authentication toàn tài liệu

Nếu phần lớn hoặc tất cả endpoint đều yêu cầu bearer token, có thể khai báo requirement ở cấp tài liệu bằng @OpenAPIDefinition:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    security = {
        @SecurityRequirement(name = "bearerAuth")
    }
)
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
public class OpenApiSecurityConfiguration {
}
~~~

Khi đó tài liệu có thể chứa:

~~~yaml
security:
  - bearerAuth: []
~~~

Danh sách rỗng sau bearerAuth là đúng với HTTP bearer scheme. OAuth2 requirement có thể liệt kê scopes; HTTP bearer không khai báo scope theo cấu trúc này.

Nếu chỉ một số endpoint cần token, không nên áp dụng requirement toàn cục rồi để người đọc đoán endpoint công khai nào được miễn. Có thể gắn requirement riêng trên từng operation hoặc ghi đè security ở operation công khai.

## 7. Cách ghi đè security cho operation công khai

OpenAPI cho phép operation ghi đè security requirement cấp tài liệu. Nếu API mặc định yêu cầu bearer token nhưng endpoint health công khai, có thể mô tả operation không yêu cầu security:

~~~yaml
security:
  - bearerAuth: []
paths:
  /health:
    get:
      security: []
      responses:
        "200":
          description: Service is healthy
~~~

Trong OpenAPI, **security: []** ở operation có nghĩa operation không yêu cầu security scheme nào, ghi đè yêu cầu ở cấp cao hơn.

Đừng nhầm trường hợp này với:

~~~yaml
security:
  - bearerAuth: []
  - {}
~~~

Danh sách có một security requirement rỗng {} thể hiện rằng xác thực là tùy chọn: request có thể dùng bearerAuth hoặc không dùng security scheme nào. Đây là ngữ nghĩa khác với security: [] tại operation.

Tài liệu phải phản ánh chính sách thực tế. Nếu health endpoint thực sự yêu cầu token, không đặt security rỗng chỉ để Swagger UI cho phép gọi không xác thực.

## 8. Ví dụ OpenAPI hoàn chỉnh

Định nghĩa scheme và requirement có thể được biểu diễn như sau:

~~~yaml
openapi: 3.0.3
info:
  title: Profile API
  version: v1

components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
      description: Access token dạng JWT gửi qua Authorization header.

security:
  - bearerAuth: []

paths:
  /api/profile:
    get:
      summary: Lấy hồ sơ hiện tại
      responses:
        "200":
          description: Hồ sơ người dùng
        "401":
          description: Thiếu hoặc token không hợp lệ
        "403":
          description: Đã xác thực nhưng không đủ quyền
~~~

Trong tài liệu:

- components.securitySchemes định nghĩa bearerAuth.
- type http và scheme bearer mô tả HTTP bearer authentication.
- bearerFormat JWT cung cấp gợi ý về định dạng token.
- security cấp root áp dụng requirement cho các operation trong tài liệu, trừ operation có ghi đè.
- 401 và 403 mô tả các kết quả bảo mật có thể xảy ra; chúng không được tự động tạo ra chỉ vì có security requirement.

## 9. Phân biệt HTTP bearer với OAuth2 và API key

Không phải mọi token trong Authorization header đều nên mô tả bằng bearerFormat. Hãy chọn loại security scheme phù hợp với cơ chế client thực sự sử dụng:

| Cơ chế | OpenAPI type | Thuộc tính chính | bearerFormat |
|---|---|---|---|
| HTTP Bearer | http | scheme: bearer | Có thể dùng để gợi ý định dạng token |
| HTTP Basic | http | scheme: basic | Không dùng để mô tả mật khẩu |
| API key trong header | apiKey | name: Authorization hoặc header riêng; in: header | Không áp dụng ngữ nghĩa HTTP bearer |
| OAuth 2.0 | oauth2 | flows, authorizationUrl, tokenUrl, scopes | Không dùng bearerFormat thay cho flow |
| OpenID Connect | openIdConnect | openIdConnectUrl | Không dùng bearerFormat thay cho discovery URL |

### HTTP bearer

Phù hợp khi client đã có access token và gửi trực tiếp:

~~~yaml
type: http
scheme: bearer
bearerFormat: JWT
~~~

### OAuth2

Nếu API mô tả quy trình cấp token như Authorization Code, Client Credentials hoặc Refresh Token, hãy dùng security scheme **oauth2** và khai báo flows. Không thay flows bằng bearerFormat:

~~~yaml
type: oauth2
flows:
  authorizationCode:
    authorizationUrl: https://identity.example.test/oauth2/authorize
    tokenUrl: https://identity.example.test/oauth2/token
    scopes:
      profile.read: Đọc hồ sơ
~~~

OAuth2 access token thường được gửi như bearer token ở tầng HTTP, nhưng OpenAPI OAuth2 scheme mô tả cả cơ chế cấp quyền và scopes. Nếu chỉ cần mô tả endpoint nhận một bearer token đã có, HTTP bearer scheme có thể phù hợp hơn.

### API key

Nếu hệ thống dùng một chuỗi key riêng trong header, mô tả bằng apiKey:

~~~yaml
type: apiKey
in: header
name: X-API-Key
~~~

Không khai báo apiKey rồi thêm bearerFormat để ngụ ý đó là JWT bearer. Hai cơ chế có cấu trúc và cách gửi khác nhau.

## 10. JWT và opaque token: mô tả đúng định dạng đang dùng

### JWT

JWT là một định dạng token chứa claims được biểu diễn theo cấu trúc JSON. JWT có thể được ký dưới dạng JWS hoặc mã hóa dưới dạng JWE. Nhiều access token JWT được ký và gửi dưới dạng bearer token:

~~~yaml
type: http
scheme: bearer
bearerFormat: JWT
description: Access token JWT do Authorization Server phát hành.
~~~

Không suy ra thuật toán ký từ bearerFormat. Ví dụ, ghi JWT không nói token dùng RS256, ES256 hay HS256; cũng không cho biết issuer, audience, thời hạn hoặc key rotation.

### Opaque token

Opaque token thường là chuỗi định danh không để client tự đọc claims. Resource Server có thể xác minh bằng introspection hoặc cơ chế tra cứu tương ứng:

~~~yaml
type: http
scheme: bearer
bearerFormat: Opaque
description: Access token opaque; server xác minh với Authorization Server.
~~~

Nếu token không có định dạng công khai ổn định, có thể bỏ bearerFormat và giải thích cách sử dụng trong description.

### Không đưa token thật vào tài liệu

Không dùng access token còn hiệu lực làm example, default hoặc description. Token có thể cấp quyền truy cập dữ liệu và thao tác thật. Nếu cần ví dụ header, dùng giá trị giả lập không thể xác thực và không dùng token của môi trường phát triển hay production.

## 11. Cấu hình bearerFormat bằng OpenAPI bean

Nếu ứng dụng quản lý tài liệu bằng OpenAPI bean thay vì annotation, có thể tạo SecurityScheme model:

~~~java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.security.SecurityScheme;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiModelConfiguration {

    @Bean
    OpenAPI libraryOpenApi() {
        SecurityScheme bearerScheme = new SecurityScheme()
            .type(SecurityScheme.Type.HTTP)
            .scheme("bearer")
            .bearerFormat("JWT")
            .description("Access token dạng JWT.");

        return new OpenAPI()
            .components(new Components()
                .addSecuritySchemes("bearerAuth", bearerScheme));
    }
}
~~~

Đoạn bean trên khai báo scheme trong components. Nếu muốn áp dụng security requirement toàn cục, cần bổ sung requirement:

~~~java
return new OpenAPI()
    .components(new Components()
        .addSecuritySchemes("bearerAuth", bearerScheme))
    .addSecurityItem(
        new io.swagger.v3.oas.models.security.SecurityRequirement()
            .addList("bearerAuth")
    );
~~~

Không khai báo đồng thời nhiều scheme trùng tên ở annotation, bean và customizer nếu không có chủ đích. Nhiều nguồn cấu hình có thể gây ghi đè hoặc kết quả khó đoán; chọn một nơi quản lý chính và kiểm tra JSON cuối.

## 12. bearerFormat và Swagger UI Authorize

Khi tài liệu có security scheme HTTP bearer và operation có security requirement tương ứng, Swagger UI có thể hiển thị nút **Authorize**. Người dùng nhập token theo hướng dẫn của giao diện; khi thực thi operation, Swagger UI gửi Authorization header theo scheme được khai báo.

Ví dụ request dự kiến:

~~~http
Authorization: Bearer <access-token>
~~~

bearerFormat có thể giúp người đọc nhận biết token dự kiến là JWT, nhưng không tự:

- Lấy token từ Identity Provider.
- Thực hiện OAuth2 login flow nếu chỉ khai báo HTTP bearer.
- Kiểm tra token trước khi gửi request.
- Làm token hết hạn hoặc refresh token.
- Cấp quyền cho endpoint.

Nếu nhập token vào Authorize, hãy kiểm tra request preview hoặc Network tab để xác nhận header chỉ có một tiền tố Bearer. Cách nhập cụ thể có thể khác theo phiên bản Swagger UI và loại security scheme. Tránh nhập cả tiền tố nếu giao diện tự thêm nó, gây ra giá trị sai dạng Bearer Bearer ....

Nếu cần Swagger UI tự thực hiện OAuth2 flow, hãy cấu hình scheme type oauth2 với flow tương ứng, không chỉ đặt bearerFormat thành JWT.

## 13. Cấu hình Spring Security vẫn phải thực hiện riêng

OpenAPI mô tả cho client biết endpoint cần bearer token. Ứng dụng phải cấu hình Spring Security để xác minh token khi request đến.

Với JWT Resource Server, các phần thường cần có:

- Dependency Resource Server và JWT support phù hợp với phiên bản Spring Boot.
- Cấu hình issuer hoặc JWK Set URI để xác minh chữ ký và nguồn phát hành.
- Cấu hình audience hoặc các validator bổ sung nếu API yêu cầu.
- Chính sách authorization để ánh xạ scope/authority vào endpoint.
- Cách xử lý token hết hạn, sai chữ ký hoặc không hợp lệ.

Với opaque token, Resource Server thường cần cấu hình introspection endpoint và thông tin xác thực để hỏi Authorization Server. Hai cơ chế runtime này khác nhau dù cả hai có thể được gửi trong header Authorization: Bearer.

Kết quả:

| Request | Kết quả thường gặp |
|---|---|
| Không gửi token tới endpoint yêu cầu xác thực | 401 Unauthorized |
| Token sai chữ ký, hết hạn hoặc không hợp lệ | 401 Unauthorized |
| Token hợp lệ nhưng thiếu authority | 403 Forbidden |
| Token hợp lệ và đủ quyền | Request được xử lý theo logic endpoint |

Mã trạng thái chính xác có thể được điều chỉnh bởi exception handler hoặc cấu hình security của ứng dụng. OpenAPI nên phản ánh response thực tế.

## 14. Kiểm tra bearerFormat trong tài liệu sinh ra

Sau khi chạy ứng dụng, mở **/v3/api-docs** hoặc endpoint JSON của group tương ứng. Tìm components/securitySchemes:

~~~bash
curl -s http://localhost:8080/v3/api-docs \
  | jq '.components.securitySchemes.bearerAuth'
~~~

Kết quả mong đợi có dạng:

~~~json
{
  "type": "http",
  "scheme": "bearer",
  "bearerFormat": "JWT",
  "description": "Access token dạng JWT trong Authorization header."
}
~~~

Kiểm tra security requirement cấp tài liệu:

~~~bash
curl -s http://localhost:8080/v3/api-docs | jq '.security'
~~~

Kiểm tra requirement trên một operation:

~~~bash
curl -s http://localhost:8080/v3/api-docs \
  | jq '.paths["/api/profile"].get.security'
~~~

Đối chiếu:

1. Tên scheme trong components có đúng không?
2. type có phải http và scheme có phải bearer không?
3. bearerFormat có phản ánh token thực tế không?
4. Operation có security requirement tham chiếu đúng tên không?
5. Endpoint công khai có được ghi đè security đúng cách không?
6. Response 401/403 có mô tả đúng hành vi server không?

Nếu bearerFormat không xuất hiện, kiểm tra annotation hoặc bean có được springdoc đọc không và phiên bản swagger-annotations có hỗ trợ thuộc tính tương ứng. Không thay đổi sang một thuộc tính tự chế trong OpenAPI; bearerFormat là tên field chuẩn của Security Scheme Object cho HTTP bearer.

## 15. Kiểm tra runtime độc lập với tài liệu

Một tài liệu có bearerAuth không chứng minh server đang xác minh token. Hãy gửi request tới endpoint được bảo vệ trong môi trường kiểm thử:

~~~bash
# Không có token
curl -i http://localhost:8080/api/profile

# Token giả lập hoặc không hợp lệ
curl -i \
  -H "Authorization: Bearer invalid-token" \
  http://localhost:8080/api/profile

# Token hợp lệ được cấp cho môi trường kiểm thử
curl -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:8080/api/profile
~~~

Không ghi token thật vào shell history, log chia sẻ hoặc tài liệu. Dùng biến môi trường và token test có quyền tối thiểu; không dán giá trị token vào nội dung Knowledge.

Kiểm tra riêng:

- Request không token bị từ chối nếu endpoint yêu cầu xác thực.
- Token sai hoặc hết hạn bị từ chối.
- Token hợp lệ nhưng thiếu quyền nhận response phù hợp.
- Token hợp lệ và đủ quyền gọi được endpoint.
- Swagger UI gửi đúng header khi dùng Authorize.

## 16. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Swagger UI không có nút Authorize | Chỉ khai báo scheme mà chưa có security requirement hoặc scheme không được sinh | Kiểm tra components và security |
| Operation không hiển thị yêu cầu bearer | Requirement thiếu hoặc tham chiếu sai tên scheme | Thêm @SecurityRequirement và dùng đúng name |
| bearerFormat hiện JWT nhưng server nhận opaque token | Metadata mô tả sai loại token | Sửa bearerFormat hoặc description cho khớp runtime |
| Đổi bearerFormat không làm request bị từ chối | bearerFormat chỉ là metadata | Cấu hình Spring Security Resource Server |
| Header thành Bearer Bearer ... | Người dùng nhập cả prefix trong khi UI tự thêm | Xem request preview và nhập token đúng định dạng UI yêu cầu |
| Token hợp lệ vẫn nhận 403 | Token thiếu authority hoặc scope cần thiết | Kiểm tra mapping claim và authorization rule |
| Token hết hạn vẫn được chấp nhận | Validator/runtime chưa kiểm tra expiration hoặc cấu hình sai | Kiểm tra JwtDecoder/opaque introspection và validator |
| Security scheme bị nhân đôi | Khai báo trùng tên ở nhiều nguồn | Chọn một nơi cấu hình và kiểm tra components |
| API key bị mô tả nhầm thành bearer | Chọn sai type/scheme | Dùng type apiKey hoặc HTTP bearer đúng cơ chế thực tế |
| Swagger UI Authorize hoạt động nhưng curl trực tiếp bị 401 | Token không được gửi trong request hoặc server có chính sách khác | Kiểm tra header thực tế và runtime security |
| Tài liệu nói mọi endpoint cần token nhưng health vẫn public | Security requirement toàn cục không được ghi đè đúng | Đặt security: [] cho operation công khai nếu phù hợp |

## 17. Nguyên tắc mô tả bearerFormat chính xác

- Dùng **type: http** và **scheme: bearer** cho HTTP bearer authentication.
- Chỉ đặt **bearerFormat: JWT** khi token thực sự là JWT.
- Dùng description để giải thích cách lấy token và header gửi token.
- Giữ name của Security Scheme ổn định và khớp với Security Requirement.
- Tách khai báo Security Scheme khỏi việc áp dụng Security Requirement.
- Không coi bearerFormat là thuật toán ký, validator, issuer hoặc OAuth2 flow.
- Không dùng bearerFormat để mô tả API key hoặc HTTP Basic.
- Dùng OAuth2 scheme nếu cần mô tả authorization flow và scopes.
- Không đưa token thật vào example, source code hoặc tài liệu.
- Kiểm tra cả OpenAPI JSON lẫn Spring Security runtime.

## Kết luận

**bearerFormat** là metadata tùy chọn trong HTTP Bearer Security Scheme, dùng để gợi ý định dạng token như JWT. Cấu hình xác thực vẫn được xác định bởi **type: http** và **scheme: bearer**; việc áp dụng cho operation cần **Security Requirement** tham chiếu đúng tên scheme. springdoc-openapi có thể sinh metadata này từ @SecurityScheme hoặc OpenAPI bean, nhưng nó không xác minh token và không thay thế Spring Security Resource Server. Hãy mô tả đúng token đang dùng, kiểm tra components/securitySchemes và security trong /v3/api-docs, rồi thử request runtime để xác nhận xác thực thực sự hoạt động.
