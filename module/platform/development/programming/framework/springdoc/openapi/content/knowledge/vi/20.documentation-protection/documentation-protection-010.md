# Loại bỏ token, dữ liệu cá nhân và địa chỉ hạ tầng khỏi nội dung công bố

Đặc tả OpenAPI và Swagger UI giúp client hiểu cách gọi API, nhưng chính các tài liệu này cũng có thể làm lộ thông tin nhạy cảm nếu ví dụ, mô tả, server URL hoặc metadata được viết từ dữ liệu thật. Một access token bị sao chép vào ví dụ cURL, email cá nhân trong response mẫu, hostname nội bộ trong `servers` hay địa chỉ quản trị trong `externalDocs` đều có thể trở thành thông tin công khai khi tài liệu được xuất bản.

Với springdoc-openapi, nội dung tài liệu được tổng hợp từ annotation trên controller/DTO, cấu hình OpenAPI, customizer và metadata do ứng dụng cung cấp. Vì vậy, bảo vệ tài liệu cần được thực hiện ở cả nơi tạo dữ liệu và nơi phát hành. Không nên chỉ xóa một chuỗi trong Swagger UI rồi cho rằng file `/v3/api-docs` hoặc bản OpenAPI JSON/YAML đã an toàn.

Bài học này hướng dẫn nhận diện dữ liệu cần bảo vệ, thay dữ liệu thật bằng ví dụ tổng hợp, kiểm soát địa chỉ hạ tầng, bảo vệ endpoint tài liệu và kiểm tra artifact trước khi công bố.

## Mục tiêu

Sau bài học, bạn có thể:

- Nhận diện token, credential, dữ liệu cá nhân và thông tin hạ tầng có thể xuất hiện trong OpenAPI.
- Tìm vị trí rò rỉ trong descriptions, examples, defaults, enum, schema, responses, servers và extensions.
- Viết ví dụ tổng hợp, không chứa dữ liệu thật hoặc bí mật có thể sử dụng.
- Công bố đúng public server URL và loại bỏ hostname/IP/port nội bộ.
- Phân biệt ẩn trường trong tài liệu với bảo vệ dữ liệu ở runtime.
- Tổ chức tài liệu public và internal bằng group hoặc cấu hình riêng.
- Bảo vệ cả Swagger UI lẫn endpoint `/v3/api-docs`.
- Kiểm tra file OpenAPI trước khi đưa vào artifact, CDN, portal hoặc repository công khai.
- Xử lý và khắc phục khi tài liệu đã làm lộ token hoặc dữ liệu nhạy cảm.

## 1. Vì sao tài liệu API cũng là bề mặt rò rỉ dữ liệu?

OpenAPI thường được xem là tài liệu kỹ thuật, nhưng nó có thể chứa nhiều dữ liệu hơn tên endpoint và kiểu JSON. Các thành phần có thể mang nội dung do con người nhập hoặc do ứng dụng sinh:

- `info.description`, `contact`, `license` và `termsOfService`.
- `servers` và server variables.
- Path, query parameter, header, cookie và mô tả request.
- Schema property, `description`, `example`, `default`, `enum` và `format`.
- Request body và response examples.
- Response headers, links và callbacks.
- OAuth2 `authorizationUrl`, `tokenUrl`, OpenID Connect `openIdConnectUrl` và security metadata.
- `externalDocs`, tags, operation descriptions và operation IDs.
- Extensions có tiền tố `x-...` do ứng dụng tự thêm.

Swagger UI chỉ là một giao diện đọc và thử API. Đặc tả JSON/YAML thường vẫn được phục vụ riêng, chẳng hạn `/v3/api-docs`, hoặc được xuất ra artifact để tải xuống. Ẩn một phần tử trên giao diện không xóa dữ liệu khỏi OpenAPI document.

### Tình huống rò rỉ thường gặp

| Tình huống | Thông tin có thể bị lộ | Vị trí thường gặp |
|---|---|---|
| Copy request thật vào ví dụ | Bearer token, cookie, API key | `@ExampleObject`, description, cURL |
| Copy response production | Tên, email, số điện thoại, địa chỉ, ID khách hàng | Schema examples, response examples |
| Dùng cấu hình deployment làm server | Hostname nội bộ, IP private, port, context path | `servers` |
| Ghi chú cách gọi API nội bộ | Tên namespace, cluster, service discovery, admin endpoint | Description, external docs, extensions |
| Dán lỗi từ log vào tài liệu | Stack trace, SQL, đường dẫn file, request ID, dữ liệu người dùng | Response description, example |
| Đưa token vào query string | Token có thể xuất hiện trong URL, history hoặc access log | Parameter và cURL example |
| Đăng Swagger UI công khai | Danh sách endpoint quản trị hoặc operation nội bộ | `/swagger-ui/**`, `/v3/api-docs/**` |
| Lưu file OpenAPI trong artifact public | Toàn bộ metadata chưa được lọc | CI artifact, static hosting, CDN |

Một tài liệu không chứa token vẫn có thể làm tăng rủi ro nếu nó tiết lộ topology, endpoint quản trị hoặc tên hệ thống nội bộ. Hãy xem xét nội dung theo ngữ cảnh phát hành: public API, tài liệu dành cho đối tác hay tài liệu chỉ dành cho nhân viên.

## 2. Phân loại dữ liệu trước khi công bố

Trước khi viết ví dụ hoặc cấu hình customizer, hãy xác định loại dữ liệu nào được phép xuất hiện trong từng nhóm tài liệu.

### Bí mật xác thực và credential

Không đưa các giá trị có thể dùng để xác thực hoặc cấp quyền vào OpenAPI:

- Access token, refresh token, ID token.
- JWT đầy đủ, kể cả token đã hết hạn nếu vẫn có thể tiết lộ claim hoặc cấu trúc.
- API key, client secret, password, private key và certificate private.
- Session ID, cookie xác thực, CSRF token.
- Signed URL hoặc URL có query parameter chứa credential.
- Mã authorization tạm thời, reset token hoặc invitation token.

Không sử dụng token thật trong `Authorization` header của ví dụ cURL. Không đặt token vào `default`, `example`, `enum`, description hoặc extension. OpenAPI chỉ cần mô tả scheme và yêu cầu bảo mật; người dùng tự cung cấp credential hợp lệ khi thử API.

### Dữ liệu cá nhân

Hãy kiểm tra cả dữ liệu nhận diện trực tiếp lẫn dữ liệu có thể kết hợp để nhận diện một người:

- Họ tên, email, số điện thoại.
- Địa chỉ nhà, ngày sinh, ảnh và giấy tờ định danh.
- Mã khách hàng, mã tài khoản, mã đơn hàng gắn với cá nhân.
- Tọa độ vị trí, thông tin thiết bị hoặc định danh trực tuyến.
- Dữ liệu thanh toán, ngân hàng, bảo hiểm hoặc thông tin tài khoản.
- Nội dung tự do có thể chứa thông tin người dùng.

Một ID dạng số hoặc UUID không nhất thiết là dữ liệu vô danh. Nếu ID có thể truy ngược tới một người trong hệ thống hoặc kết hợp với nguồn khác để nhận diện họ, hãy xem nó là dữ liệu cần bảo vệ.

### Thông tin hạ tầng và vận hành

Không công bố chi tiết hạ tầng chỉ dành cho vận hành nội bộ:

- Hostname nội bộ, DNS suffix, tên namespace hoặc service discovery.
- Địa chỉ IP private, loopback, link-local hoặc địa chỉ management.
- Port nội bộ, đường dẫn admin, actuator hoặc debug endpoint.
- Tên database, queue, bucket, topic, cluster và region nội bộ.
- Đường dẫn filesystem, mount point, tên máy, container ID.
- Tên người dùng vận hành, cấu hình proxy, internal gateway hoặc topology.
- Stack trace, SQL, câu lệnh shell, tên class nội bộ và đường dẫn source.

Một public hostname hoặc địa chỉ liên hệ hỗ trợ có thể được công bố nếu đó là thông tin được duyệt. Phân loại theo mục đích và phạm vi truy cập, không tự động xem mọi URL/IP là bí mật hoặc mọi URL/IP là an toàn.

### Dữ liệu nghiệp vụ nhạy cảm

Một số thông tin không phải credential hay dữ liệu cá nhân nhưng vẫn không nên xuất bản:

- Tên khách hàng, đối tác hoặc dự án chưa công bố.
- Quy tắc giá, hạn mức, ngưỡng chống gian lận và chính sách nội bộ.
- Tên feature flag, mã sản phẩm chưa phát hành.
- Endpoint beta, operation quản trị hoặc luồng xử lý chưa được công bố.
- Thông tin về hệ thống bên thứ ba và hợp đồng tích hợp.

Hãy phân biệt tài liệu dành cho public developer với tài liệu dành cho đối tác đã ký thỏa thuận và tài liệu nội bộ.

## 3. Xác định dữ liệu nhạy cảm nằm ở đâu trong OpenAPI

Không chỉ tìm các trường có tên `password` hoặc `token`. Nội dung nhạy cảm có thể xuất hiện ở bất kỳ chuỗi tự do nào.

### Description và summary

Các trường văn bản thường bị bỏ qua khi review:

~~~java
@Operation(
    summary = "Tra cứu tài khoản",
    description = "Dùng tài khoản thật của khách hàng X tại hệ thống nội bộ để kiểm tra..."
)
~~~

Description được xuất vào OpenAPI. Không chép ghi chú nội bộ, ticket, log hoặc email trao đổi vào summary/description. Hãy viết lại thành hướng dẫn tổng quát, mô tả hành vi API mà client cần biết.

### Schema example, default và enum

Ví dụ không an toàn:

~~~java
@Schema(
    description = "Bearer token của phiên test",
    example = "TOKEN_VALUE_MUST_NOT_BE_PUBLISHED"
)
private String accessToken;
~~~

Đoạn trên có thể xuất token vào schema ngay cả khi endpoint không trả token trong response. Không dùng token giả có hình thức giống token có thể sử dụng; một chuỗi trông như JWT vẫn dễ bị copy vào môi trường thật và gây nhầm lẫn.

`default` cũng là dữ liệu được công bố trong schema. Không đặt mật khẩu mặc định, API key, hostname nội bộ hoặc ID tài khoản thật vào default. `enum` có thể làm lộ tên tenant, khách hàng, trạng thái nội bộ hoặc giá trị cấu hình chưa công bố.

### Request và response examples

`@ExampleObject`, `@Content`, `@ApiResponse` và annotation trên DTO có thể tạo ví dụ hiển thị trong Swagger UI và OpenAPI JSON. Hãy xem các ví dụ như nội dung xuất bản, cần review như một tài liệu chính thức.

Không lấy nguyên request/response từ production hoặc log để làm example. Hãy tạo fixture tổng hợp, kiểm tra mọi trường lồng nhau và thay cả các ID có thể truy ngược.

### Server, URL và external documentation

Kiểm tra tất cả URL, không chỉ `servers`:

- OAuth2 `authorizationUrl` và `tokenUrl`.
- OpenID Connect `openIdConnectUrl`.
- `externalDocs.url`.
- Callback URL và link trong response.
- Server variables và default của chúng.
- URL trong description, example, extension và contact.

Một URL có thể chứa signed query string, API key, tenant ID hoặc path nội bộ. Hãy dùng endpoint public được duyệt hoặc URL placeholder dành riêng cho tài liệu.

### Extensions và metadata tự định nghĩa

Các extension `x-...` thường được thêm bởi customizer hoặc hệ thống build. Chúng có thể chứa tên service, route nội bộ, build metadata, commit URL, tên cluster, request trace hoặc thông tin triển khai. Đưa extensions vào danh sách review như các property OpenAPI tiêu chuẩn.

## 4. Viết ví dụ tổng hợp thay vì sao chép dữ liệu thật

Ví dụ an toàn nên minh họa cấu trúc và kiểu dữ liệu mà không đại diện cho một cá nhân, credential hoặc hệ thống thật.

### Quy tắc tạo dữ liệu mẫu

1. Dùng tên miền dành cho ví dụ như `example.com` hoặc `.invalid`; không dùng domain của khách hàng hay môi trường production.
2. Dùng ID tổng hợp, ví dụ `sample-001` hoặc UUID được tạo riêng cho tài liệu.
3. Dùng dữ liệu không gắn với một cá nhân có thật.
4. Không dùng số điện thoại, email hoặc địa chỉ được lấy từ ticket, database hay log.
5. Không dùng JWT, API key hoặc password thật; tốt nhất không đưa credential vào example.
6. Giữ dữ liệu nhất quán giữa request và response nhưng không sao chép record production.
7. Kiểm tra dữ liệu lồng nhau, file đính kèm, URL, metadata và header.

Ví dụ response tổng hợp:

~~~json
{
  "id": "sample-product-001",
  "name": "Bàn phím mẫu",
  "status": "ACTIVE",
  "contactEmail": "developer@example.com"
}
~~~

`example.com` là domain dành cho ví dụ. `sample-product-001` là mã minh họa, không tham chiếu bản ghi production.

### Ví dụ request không chứa token

Không nên viết:

~~~bash
curl -H "Authorization: Bearer REDACTED_VALUE" \
  https://api.example.com/api/products
~~~

Có thể viết hướng dẫn dùng biến môi trường:

~~~bash
curl \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  https://api.example.com/api/products
~~~

Đây là placeholder cho token do người dùng tự cung cấp trong môi trường của họ. Không gán giá trị token thật vào ví dụ, file `.env` mẫu hoặc script được phát hành.

### Không dùng placeholder có thể bị hiểu nhầm là credential

Một chuỗi có prefix giống credential của nhà cung cấp, dù đã cắt ngắn, vẫn có thể bị scanner nhận diện là secret. Trong tài liệu, hãy dùng placeholder rõ nghĩa như `${ACCESS_TOKEN}` hoặc dòng mô tả “Cung cấp access token hợp lệ tại thời điểm gọi”.

Nếu cần minh họa cấu trúc JWT, dùng payload tổng hợp không ký hoặc đánh dấu rõ token chỉ là chuỗi giả, không thể xác thực. Không tạo một token ký bằng secret thật để minh họa.

### Dữ liệu tổng hợp và dữ liệu đã ẩn danh

Thay một phần ký tự trong email, số điện thoại hoặc tên không đảm bảo dữ liệu đã ẩn danh. Ví dụ `n***@company.com` vẫn có thể nhận diện một người khi domain và ngữ cảnh đủ hẹp. Với tài liệu public, ưu tiên tạo dữ liệu tổng hợp từ đầu thay vì làm mờ dữ liệu production.

Nếu phải dùng dữ liệu đã biến đổi, đánh giá khả năng tái nhận diện và kiểm tra các trường kết hợp. Xóa tên nhưng giữ email, ID khách hàng, địa chỉ và timestamp chính xác có thể vẫn để lộ danh tính.

## 5. Mô tả trường nhạy cảm trong schema

Không phải trường nhạy cảm nào cũng cần xuất hiện trong tài liệu. Trước tiên hãy xác định client có cần biết trường đó tồn tại hay không và có cần gửi/nhận trường đó không.

### Không công bố trường nội bộ không cần thiết

Nếu DTO chứa field chỉ dùng nội bộ, cân nhắc tách DTO public khỏi entity hoặc internal model. Đây là cách rõ ràng nhất để kiểm soát hợp đồng:

~~~java
public record PublicUserResponse(
    String id,
    String displayName
) {}
~~~

Không đưa password hash, internal notes, moderation flags, database key hoặc thông tin vận hành vào response DTO chỉ để sau đó tìm cách ẩn khỏi OpenAPI.

### @Schema(hidden = true) không phải kiểm soát truy cập

Có thể ẩn một property khỏi schema:

~~~java
@Schema(hidden = true)
private String internalRiskScore;
~~~

Điều này ảnh hưởng đến tài liệu OpenAPI. Nó không tự ngăn Jackson serialize field ra JSON, không bảo vệ endpoint và không thay thế kiểm tra quyền. Nếu field không được phép xuất hiện trong response, hãy loại bỏ nó khỏi response DTO hoặc cấu hình serialization phù hợp rồi viết test JSON runtime.

Tương tự, `@Parameter(hidden = true)` hoặc `@Hidden` chỉ tác động đến mô tả tài liệu trong phạm vi annotation; không biến một endpoint hoặc parameter thành an toàn. Nếu client thực sự phải gửi một header hoặc parameter, đừng ẩn nó chỉ để tránh lộ giá trị nhạy cảm. Hãy mô tả tên và mục đích của trường, không ghi credential thật vào example/default.

### readOnly và writeOnly

OpenAPI có thể dùng `readOnly` hoặc `writeOnly` để mô tả hướng dữ liệu:

- `readOnly: true`: property được trả về nhưng client không nên gửi khi tạo/cập nhật.
- `writeOnly: true`: property được gửi trong request nhưng không được trả về trong response.

Ví dụ password có thể được mô tả là write-only nếu API thực sự nhận password:

~~~yaml
password:
  type: string
  format: password
  writeOnly: true
  description: Mật khẩu mới do người dùng cung cấp
~~~

Không thêm example hoặc default cho password. `writeOnly` là metadata hợp đồng; ứng dụng vẫn phải bảo đảm password không bị serialize trong response, log hoặc exception.

### Tách request DTO và response DTO

Một DTO dùng chung cho cả request và response dễ khiến field nội bộ hoặc write-only xuất hiện sai chỗ. Với dữ liệu nhạy cảm, tách kiểu thường dễ kiểm soát hơn:

~~~java
public record ChangePasswordRequest(
    @Schema(format = "password", writeOnly = true)
    String newPassword
) {}

public record PublicProfileResponse(
    String id,
    String displayName
) {}
~~~

Không đưa password vào response DTO. Nếu dùng annotation trên record component, kiểm tra OpenAPI JSON và JSON runtime để xác nhận metadata cùng serialization đúng như mong đợi.

## 6. Dùng customizer để áp dụng chính sách công bố

OpenApiCustomizer cho phép kiểm soát tài liệu sau khi springdoc đã tạo mô hình OpenAPI. Nó hữu ích để áp dụng một số chính sách nhất quán, chẳng hạn đặt public server URL từ cấu hình đã duyệt, chuẩn hóa contact thành địa chỉ hỗ trợ công khai, xóa extension nội bộ đã được nhận diện rõ, hoặc từ chối tài liệu có server host ngoài allowlist.

Customizer không nên trở thành nơi duy nhất xử lý mọi dữ liệu nhạy cảm. Dữ liệu an toàn cần được tạo ngay từ annotation, DTO và fixture; customizer là lớp kiểm soát bổ sung và có thể có logic riêng cho từng group.

### Chuẩn hóa contact công khai

Nếu metadata nguồn có contact nội bộ, một customizer riêng cho tài liệu public có thể đặt contact đã được duyệt:

~~~java
import io.swagger.v3.oas.models.info.Contact;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.context.annotation.Bean;

@Bean
OpenApiCustomizer publicContactCustomizer() {
    return openApi -> {
        if (openApi.getInfo() != null) {
            openApi.getInfo().setContact(
                new Contact()
                    .name("API Support")
                    .url("https://developers.example.com/support")
                    .email("support@example.com")
            );
        }
    };
}
~~~

Đây là thay thế contact có chủ đích cho tài liệu public. Dùng địa chỉ hỗ trợ được tổ chức phê duyệt; không thay bằng email cá nhân hoặc alias nội bộ.

### Không dùng regex để thay thế mọi chuỗi trong OpenAPI

Không nên serialize toàn bộ OpenAPI thành text rồi chạy một loạt regex để thay hostname, token hoặc email. Cách này có thể thay nhầm nội dung hợp lệ trong example hoặc mô tả, bỏ sót dữ liệu nằm trong cấu trúc JSON/YAML khác, làm hỏng URL hoặc tham chiếu schema, và tạo cảm giác an toàn giả vì một số mẫu bí mật không khớp regex.

Ưu tiên sửa annotation, DTO, cấu hình server và example tại nguồn. Với customizer, thao tác trên đúng property/model node có chủ sở hữu rõ ràng. Nếu cần bộ lọc tổng quát, dùng parser OpenAPI để duyệt cấu trúc và viết test cho từng loại node; không sửa chuỗi serialized bằng replace toàn cục.

### Từ chối tài liệu khi gặp host ngoài allowlist

Đối với public spec, có thể kiểm tra server URL trước khi phát hành:

~~~java
private static final Set<String> ALLOWED_HOSTS =
    Set.of("api.example.com", "sandbox.example.com");

private void validatePublicServers(OpenAPI openApi) {
    if (openApi.getServers() == null) {
        throw new IllegalStateException("Public server is missing");
    }

    for (Server server : openApi.getServers()) {
        URI uri = URI.create(server.getUrl());
        if (uri.getHost() != null && !ALLOWED_HOSTS.contains(uri.getHost())) {
            throw new IllegalStateException(
                "OpenAPI contains a server outside the public allowlist"
            );
        }
    }
}
~~~

Đây là helper minh họa; cần import java.net.URI, java.util.Set, OpenAPI và Server. URL tương đối như / không có host, nên cần cho phép theo policy riêng. Không đưa nguyên URL bị từ chối vào exception/log nếu nó có thể chứa credential hoặc query secret.

Một kiểm tra allowlist như trên chỉ xác minh server URL. Nó không tìm PII trong examples, token trong descriptions hoặc địa chỉ nội bộ trong extensions; cần các bước kiểm tra khác cho những trường đó.

## 7. Không làm lộ dữ liệu qua response và logging

OpenAPI là một phần của vòng đời API, nhưng dữ liệu nhạy cảm còn có thể rò rỉ từ response thực tế, lỗi và log. Nếu schema đã được làm sạch nhưng endpoint trả password hash hoặc stack trace, tài liệu không thể bảo vệ dữ liệu đó.

### Response lỗi phải an toàn

Không đưa chi tiết nội bộ vào response lỗi:

~~~json
{
  "message": "Connection failed to database-host.internal.invalid:5432",
  "sql": "select * from customer_account where id = ...",
  "stackTrace": "..."
}
~~~

Thay bằng lỗi tổng quát và mã tham chiếu không nhạy cảm:

~~~json
{
  "code": "INTERNAL_ERROR",
  "message": "Đã xảy ra lỗi. Vui lòng thử lại sau.",
  "traceId": "sample-trace-001"
}
~~~

Trace ID trong ví dụ phải là giá trị tổng hợp. Trong runtime, trace ID có thể giúp support tìm log, nhưng log cần được bảo vệ và không nên cho phép người dùng dùng ID đó để đọc thông tin nội bộ.

OpenAPI response examples và descriptions cần mô tả lỗi đã được chuẩn hóa. Không chép stack trace, SQL, hostname, đường dẫn filesystem hoặc nội dung request thật vào response example.

### Không log credential và dữ liệu nhạy cảm

Kiểm tra logging ở controller, filter, interceptor, gateway và HTTP client:

- Không log Authorization, Cookie, Set-Cookie hoặc client secret.
- Không log toàn bộ request/response body nếu có password, thông tin thanh toán hoặc dữ liệu cá nhân.
- Không ghi query string chứa signed URL hoặc token.
- Không ghi JWT đầy đủ; nếu cần correlation, dùng request ID riêng.
- Không ghi stack trace hoặc cấu hình nội bộ vào response gửi client.
- Hạn chế quyền đọc log, đặt retention và masking theo chính sách.

Masking ở log chỉ giảm dữ liệu hiển thị; không thay thế việc tránh ghi credential ngay từ đầu. Cần kiểm tra cả log do thư viện HTTP, proxy, ingress và tracing agent tạo ra.

### Tài liệu và response phải thống nhất

Nếu OpenAPI mô tả traceId nhưng response thực tế trả requestId, client sẽ khó đối chiếu. Nếu schema đánh dấu password là write-only nhưng serializer vẫn trả password, đó là lỗi runtime. Hãy kiểm thử cả hai phía:

- OpenAPI JSON không chứa dữ liệu nhạy cảm.
- Response JSON thực tế không chứa field hoặc giá trị bị cấm.
- Error response không có stack trace hoặc infrastructure detail.
- Log không ghi credential hoặc body nhạy cảm theo cấu hình đang dùng.

## 8. Kiểm tra OpenAPI trước khi tạo artifact

Một file OpenAPI tĩnh có thể được lưu trong build artifact, package, repository, portal developer hoặc CDN. Sau khi phát hành, việc thu hồi bản cũ có thể khó hơn thay đổi endpoint động. Hãy đưa kiểm tra nội dung vào pipeline tạo artifact.

### Quy trình phát hành an toàn

1. Xác định audience: public, partner hay internal.
2. Chọn đúng source và group OpenAPI cho audience đó.
3. Sinh JSON/YAML từ đúng phiên bản ứng dụng.
4. Parse file bằng OpenAPI parser để bảo đảm cấu trúc hợp lệ.
5. Kiểm tra server, OAuth URL, externalDocs và callback theo allowlist.
6. Quét token, API key, private key và các mẫu credential.
7. Quét PII trong examples, descriptions, default, enum và extensions.
8. Kiểm tra endpoint/path nội bộ và metadata vận hành.
9. Review thủ công các đoạn văn bản tự do, response examples và extension.
10. Lưu artifact vào nơi có quyền truy cập đúng audience.
11. Gắn version/build metadata không nhạy cảm và giữ lịch sử phát hành.
12. Chỉ publish sau khi các kiểm tra bắt buộc đạt.

### Phân loại artifact

| Artifact | Nơi lưu phù hợp | Kiểm soát |
|---|---|---|
| Public OpenAPI | Portal public hoặc static hosting được duyệt | Chỉ chứa operation và server public |
| Partner OpenAPI | Portal có xác thực theo partner | Phân quyền theo đối tác và version |
| Internal OpenAPI | Artifact repository hoặc portal nội bộ | SSO/RBAC, network policy, retention |
| Raw generated OpenAPI | Build workspace hoặc artifact nội bộ tạm thời | Không tự động publish ra ngoài |

Không dùng cùng một file OpenAPI cho public và internal nếu nó chứa operation, schema hoặc server khác phạm vi. Hãy tạo artifact riêng và xác minh nội dung trước khi upload.

### Quản lý cache và bản sao

Khi phát hiện nội dung nhạy cảm trong tài liệu đã phát hành, xóa file gốc chưa chắc đã xóa hết bản sao:

- CDN cache và reverse proxy cache.
- Browser cache và download của người dùng.
- Build artifact, package registry và release attachment.
- Git history, branch, fork và mirror.
- Portal developer hoặc hệ thống index tài liệu.
- Backup và archive theo retention.

Xác định các nơi đã phân phối file và quy trình thu hồi của từng nơi. Không công bố lại artifact cũ chỉ vì source hiện tại đã được sửa.

## 9. Tự động hóa kiểm tra secret và PII

Kiểm tra tự động giúp phát hiện lỗi sớm, nhưng không thể thay thế review nội dung. Nên kết hợp secret scanning, PII scanning, schema validation và các assertion theo policy.

### Secret scanning

Secret scanner có thể tìm:

- JWT hoặc chuỗi có entropy cao.
- API key theo pattern của nhà cung cấp.
- Private key PEM.
- Authorization header hoặc cookie có giá trị.
- URL chứa credential trong query string.

Không nên chỉ dựa vào một pattern chung như eyJ; chuỗi đó có thể xuất hiện trong ví dụ không phải token, và token có thể dùng định dạng khác. Dùng scanner phù hợp với hệ thống credential đang dùng và xử lý false positive có kiểm soát.

Nếu scanner phát hiện secret, không in nguyên giá trị match ra CI log. Báo tên file, vị trí hoặc loại rule cùng một đoạn đã che; chỉ người có quyền phù hợp mới được truy cập artifact cần điều tra.

### PII scanning

PII scanner có thể phát hiện email, số điện thoại, địa chỉ hoặc định danh theo pattern. Nhưng tên người, ID nghiệp vụ và nội dung tự do thường khó nhận diện tự động. Hãy bổ sung:

- Allowlist domain ví dụ đã được phê duyệt.
- Danh sách field nhạy cảm trong schema.
- Review examples và descriptions.
- Kiểm tra các trường có thể kết hợp để tái nhận diện.
- Kiểm tra ID có thể truy ngược về hệ thống production.

Không coi kết quả scanner “không phát hiện” là bằng chứng tuyệt đối rằng tài liệu vô danh.

### Assertion cho public server

Một test đơn giản có thể xác nhận server public:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class PublicOpenApiTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publishesOnlyApprovedServer() throws Exception {
        mockMvc.perform(get("/v3/api-docs/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.servers[0].url")
                .value("https://api.example.com"));
    }
}
~~~

Giá trị cần khớp cấu hình test. Bổ sung assertion cho mọi server, không chỉ phần tử đầu tiên nếu tài liệu có nhiều server.

### Kiểm tra không có chuỗi nội bộ đã biết

Có thể kiểm tra body tài liệu không chứa hostname hoặc marker nội bộ:

~~~java
mockMvc.perform(get("/v3/api-docs/public"))
    .andExpect(status().isOk())
    .andExpect(content().string(not(containsString(".svc.cluster.local"))))
    .andExpect(content().string(not(containsString("db-prod-"))));
~~~

Ví dụ dùng Hamcrest not và containsString; cần import static các matcher và content(). Đây chỉ là kiểm tra bổ sung cho những marker đã biết. Nó không thay thế parser, allowlist hoặc secret scanner.

### Kiểm tra tài liệu và runtime cùng lúc

Viết test riêng để bảo đảm:

- OpenAPI không chứa internalRiskScore nếu field đó không được công bố.
- Response runtime không chứa internalRiskScore nếu field đó không được phép trả.
- Schema password có writeOnly: true và không có example/default.
- Public server không chứa internal hostname.
- Public group không chứa path admin/internal.
- Swagger UI và /v3/api-docs yêu cầu đúng quyền nếu tài liệu không public.

## 10. Xử lý khi tài liệu đã làm lộ dữ liệu

Nếu phát hiện token, PII hoặc địa chỉ nội bộ trong tài liệu đã công bố, hãy xử lý theo mức độ dữ liệu và phạm vi phân phối.

### Khi bị lộ credential

1. Xác định loại credential, nơi xuất hiện, thời điểm và các artifact liên quan.
2. Thu hồi hoặc rotate token, API key, password, certificate hay secret tương ứng theo quy trình hệ thống.
3. Kiểm tra log truy cập, download, CDN và portal để xác định khả năng bị sử dụng.
4. Gỡ hoặc thay artifact bị ảnh hưởng, purge cache và cập nhật portal.
5. Kiểm tra repository history, release attachment và bản sao đã phân phối.
6. Sửa nguồn annotation/configuration/example để lỗi không tái diễn.
7. Thêm test hoặc scanner rule ngăn phát hành lại nội dung tương tự.

Xóa chuỗi khỏi file không làm credential cũ mất hiệu lực. Nếu credential có thể sử dụng, hãy thu hồi/rotate theo quy trình; không chỉ dựa vào việc tài liệu đã được sửa.

### Khi bị lộ dữ liệu cá nhân

1. Xác định loại dữ liệu, cá nhân/nhóm bị ảnh hưởng và phạm vi công bố.
2. Hạn chế truy cập hoặc gỡ tài liệu theo quy trình ứng phó sự cố.
3. Thu hồi bản sao, cache và artifact có thể kiểm soát.
4. Thông báo cho đầu mối bảo vệ dữ liệu hoặc đội incident response theo chính sách tổ chức và quy định áp dụng.
5. Đánh giá khả năng tái nhận diện từ các trường còn lại.
6. Thay ví dụ bằng dữ liệu tổng hợp và thêm bước review.

Không sao chép dữ liệu cá nhân bị lộ vào ticket hoặc log điều tra mới nếu không cần thiết. Khi báo cáo, dùng mã tham chiếu và mô tả loại dữ liệu thay vì nhân rộng giá trị nhạy cảm.

### Khi bị lộ hạ tầng nội bộ

1. Gỡ hostname, IP, port, route và topology khỏi tài liệu public.
2. Kiểm tra endpoint có thể truy cập từ Internet hoặc mạng không tin cậy hay không.
3. Rà soát firewall, gateway, DNS và network policy nếu thông tin bị lộ làm tăng khả năng dò tìm.
4. Kiểm tra log truy cập và cảnh báo bảo mật.
5. Sửa server URL, externalDocs, examples, extensions và các source metadata.
6. Thêm allowlist host và test chống tái xuất bản.

Không phải mọi hostname nội bộ bị lộ đều đòi hỏi thay đổi hạ tầng. Đánh giá khả năng truy cập và rủi ro thực tế, sau đó áp dụng biện pháp phù hợp.

## 11. Checklist trước khi công bố

### Nội dung và schema

- [ ] Không có access token, refresh token, ID token, API key, client secret hoặc password thật.
- [ ] Không có private key, cookie, session ID, CSRF token hoặc signed URL.
- [ ] Examples dùng dữ liệu tổng hợp và domain dành cho ví dụ.
- [ ] Không có email, số điện thoại, địa chỉ, tên hoặc ID gắn với cá nhân thật.
- [ ] Không có thông tin có thể tái nhận diện khi kết hợp nhiều trường.
- [ ] Không có password hash, internal note, risk score hoặc field nội bộ không cần thiết.
- [ ] Descriptions và response examples không chứa log, stack trace, SQL hoặc đường dẫn máy.
- [ ] Default và enum không làm lộ credential, tenant hoặc cấu hình nội bộ.
- [ ] Extensions x-... đã được review.

### URL và hạ tầng

- [ ] Server URL chỉ chứa hostname public được duyệt hoặc URL tương đối theo policy.
- [ ] Không có private IP, loopback, internal DNS suffix, namespace hoặc port quản trị.
- [ ] OAuth2 và OpenID Connect URL phù hợp với audience.
- [ ] External docs, callback, webhook và response links đã được review.
- [ ] Contact chỉ dùng địa chỉ hỗ trợ công khai đã được duyệt.

### Truy cập và phát hành

- [ ] Public group chỉ chứa operation được duyệt.
- [ ] Internal/admin documentation được bảo vệ riêng.
- [ ] Swagger UI và /v3/api-docs đều được bảo vệ hoặc tắt khi không cần.
- [ ] @Hidden không bị xem nhầm là kiểm soát truy cập runtime.
- [ ] Artifact được parse, scan secret/PII và review trước khi publish.
- [ ] Artifact public và internal được lưu ở nơi có quyền truy cập phù hợp.
- [ ] Cache và bản sao cũ có quy trình thu hồi.
- [ ] Có test xác minh server, schema, path và endpoint protection.

## 12. Bài thực hành tổng hợp

Chuẩn bị một ứng dụng Spring Boot có API public và API nội bộ. Tạo tài liệu OpenAPI rồi thực hiện các bước:

1. Tạo DTO response có field công khai và một field nội bộ; tách public DTO hoặc loại field nội bộ khỏi response.
2. Tạo request DTO có password write-only và không đặt example/default cho password.
3. Tạo response example bằng dữ liệu tổng hợp, dùng domain example.com và ID mẫu.
4. Kiểm tra không có token, cookie, API key hoặc signed URL trong examples và descriptions.
5. Cấu hình public server URL qua application property.
6. Tạo GroupedOpenApi chỉ chứa public paths.
7. Loại operation nội bộ khỏi tài liệu public và vẫn bảo vệ endpoint bằng Spring Security.
8. Bảo vệ /swagger-ui/** và /v3/api-docs/** bằng authority riêng hoặc tắt tài liệu ở profile production.
9. Kiểm tra OAuth2/OIDC URL, contact, externalDocs, server variables và extensions.
10. Sinh OpenAPI JSON, parse và quét secret/PII trước khi tạo artifact.
11. Viết MockMvc test xác minh public server, path public và endpoint docs protection.
12. Viết test response runtime để bảo đảm field nội bộ và credential không xuất hiện.
13. Mô phỏng phát hiện token trong artifact; lập quy trình thu hồi, purge cache và thay artifact.
14. Ghi lại nguồn dữ liệu, người duyệt và audience cho mỗi artifact được phát hành.

### Tiêu chí hoàn thành

- [ ] Tài liệu không chứa credential hoặc token có thể sử dụng.
- [ ] Examples không chứa PII production và không thể truy ngược cá nhân.
- [ ] Public OpenAPI không tiết lộ hostname, IP, port hoặc topology nội bộ.
- [ ] Server URL và OAuth/OIDC URL phù hợp với audience.
- [ ] DTO public không công bố field nội bộ không cần thiết.
- [ ] Schema hidden không bị dùng thay cho kiểm soát serialization hoặc authorization.
- [ ] Public/internal group được phân tách đúng.
- [ ] Swagger UI và OpenAPI endpoints được bảo vệ hoặc tắt theo policy.
- [ ] Secret/PII scan và OpenAPI validation chạy trước khi publish.
- [ ] Test kiểm tra nội dung OpenAPI và response runtime.
- [ ] Có quy trình thu hồi credential và artifact khi xảy ra rò rỉ.

## 13. Công bố server URL mà không tiết lộ topology nội bộ

Springdoc có thể suy ra server từ request hiện tại hoặc dùng server được khai báo trong cấu hình OpenAPI. Trong môi trường có reverse proxy, ingress hoặc API gateway, request nội bộ tới ứng dụng có thể mang hostname và port khác với địa chỉ client bên ngoài sử dụng.

Ví dụ tài liệu vô tình công bố:

~~~yaml
servers:
  - url: http://product-api.namespace.svc.internal.invalid:8080
~~~

URL này tiết lộ tên service, namespace và port trong cluster. Client bên ngoài cũng không thể truy cập trực tiếp địa chỉ đó.

Hãy công bố địa chỉ public gateway đã được phê duyệt:

~~~yaml
servers:
  - url: https://api.example.com
    description: Public API
~~~

Nếu API được phục vụ dưới cùng origin với ứng dụng client, có thể dùng server URL tương đối phù hợp với cấu hình triển khai:

~~~yaml
servers:
  - url: /
    description: Current host
~~~

Không dùng URL production thật trong bài học, fixture hoặc test nếu không cần. `example.com` là tên miền minh họa; khi phát hành, thay bằng hostname public chính thức được chủ sở hữu API duyệt.

### Cấu hình public URL theo môi trường

Đưa public base URL vào cấu hình deployment thay vì suy ra từ hostname nội bộ:

~~~yaml
app:
  public-api-url: https://api.example.com
~~~

Customizer có thể đặt danh sách server cho tài liệu public:

~~~java
import io.swagger.v3.oas.models.servers.Server;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.List;

@Configuration
class PublicOpenApiServerConfiguration {

    @Bean
    OpenApiCustomizer publicServerCustomizer(
            @Value("${app.public-api-url:/}") String publicApiUrl) {

        return openApi -> openApi.setServers(List.of(
            new Server()
                .url(publicApiUrl)
                .description("Public API")
        ));
    }
}
~~~

Đoạn mã thay toàn bộ `servers` bằng URL public đã cấu hình. Chỉ gắn customizer này vào tài liệu public; tài liệu internal có thể cần server khác và phải được bảo vệ riêng. Nếu ứng dụng cần nhiều public server, xây dựng danh sách từ cấu hình đã kiểm duyệt thay vì lấy tất cả địa chỉ từ request hoặc service discovery.

Nếu public spec được tạo bằng GroupedOpenApi, có thể gắn customizer vào builder của group đó bằng addOpenApiCustomizer. Không áp dụng customizer public lên tài liệu internal hoặc partner nếu các audience này có base URL khác.

Hãy xác thực cấu hình khi khởi động hoặc trong pipeline: chỉ chấp nhận scheme/host/path được duyệt. Nếu URL bị thiếu, sai scheme hoặc trỏ vào hostname nội bộ, không nên âm thầm xuất nó vào tài liệu public.

### Kiểm tra server variables

Server variable có thể chứa hostname hoặc path mặc định:

~~~yaml
servers:
  - url: https://{environment}.example.com/{basePath}
    variables:
      environment:
        default: api
        enum:
          - api
          - sandbox
      basePath:
        default: v1
~~~

Chỉ công bố các giá trị enum và default mà client được phép sử dụng. Không đưa tên cluster, namespace, internal DNS suffix hoặc port quản trị vào biến server.

### Kiểm tra mọi URL khác

Ngoài `servers`, hãy review:

- OAuth2 `authorizationUrl` và `tokenUrl`: dùng endpoint public của authorization server.
- OpenID Connect `openIdConnectUrl`: không để lộ địa chỉ discovery nội bộ nếu client public không thể truy cập.
- `externalDocs`: chỉ liên kết đến portal hoặc tài liệu được phép công bố.
- Callback và webhook URL: dùng hostname public hoặc placeholder trong ví dụ.
- Response links: không chứa signed URL hoặc query parameter có credential.
- Contact: dùng email hỗ trợ công khai, không dùng email cá nhân hoặc alias vận hành nội bộ.

Không dùng query parameter để truyền bearer token hoặc API key. URL thường được ghi trong browser history, proxy log, analytics và access log. Dùng `Authorization` header hoặc cơ chế xác thực được thiết kế cho API.

## 14. Phân tách tài liệu public và internal

Không phải endpoint nào trong ứng dụng cũng dành cho mọi người đọc. Một API có thể có:

- Public operation dành cho developer bên ngoài.
- Partner operation chỉ dành cho đối tác đã được cấp quyền.
- Internal operation phục vụ service-to-service.
- Admin, support, actuator hoặc diagnostic endpoint.

Một tài liệu duy nhất chứa tất cả path có thể làm lộ hoạt động nội bộ. Hãy tạo nhóm tài liệu theo audience và chỉ đưa operation được duyệt vào từng nhóm.

### Dùng GroupedOpenApi cho public API

Ví dụ public group chỉ chứa các path có tiền tố public:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiGroupsConfiguration {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public")
            .pathsToMatch("/api/public/**")
            .build();
    }
}
~~~

Tài liệu group được phục vụ tại endpoint dạng `/v3/api-docs/public`. Chỉ công bố group public cho audience bên ngoài. Nếu có group internal hoặc admin, hãy bảo vệ endpoint tài liệu của chúng bằng xác thực và authorization phù hợp.

Group lọc path theo cấu hình tài liệu; nó không tự bảo vệ endpoint runtime. Nếu một internal endpoint vẫn được truy cập không cần quyền, việc loại nó khỏi public OpenAPI không sửa được lỗi authorization.

### @Hidden chỉ ẩn khỏi tài liệu

Có thể loại một controller hoặc operation khỏi OpenAPI bằng `@Hidden`:

~~~java
@Hidden
@RestController
@RequestMapping("/internal/maintenance")
class InternalMaintenanceController {
    // ...
}
~~~

Hoặc ẩn một operation cụ thể nếu không muốn đưa nó vào tài liệu:

~~~java
@Hidden
@PostMapping("/internal/reindex")
public void reindex() {
    // ...
}
~~~

`@Hidden` ảnh hưởng đến việc tạo tài liệu. Nó không chặn HTTP request, không thay thế Spring Security, gateway policy hoặc network control. Endpoint vẫn phải được bảo vệ độc lập ở runtime.

### Không dựa vào việc đổi URL Swagger UI

Đổi `/swagger-ui.html` thành một path khó đoán hoặc đổi `/v3/api-docs` không phải biện pháp authorization. Path có thể bị phát hiện qua JavaScript, network request, log hoặc cấu hình client. Bảo vệ bằng xác thực, authorization, network policy hoặc tắt hoàn toàn nếu không cần.

## 15. Bảo vệ Swagger UI và OpenAPI endpoints

Swagger UI và OpenAPI JSON là hai tài nguyên riêng. Nếu chỉ bảo vệ trang UI, người dùng vẫn có thể gọi trực tiếp endpoint tài liệu. Nếu chỉ bảo vệ `/v3/api-docs`, một trang Swagger UI public vẫn có thể để lộ HTML, asset, tên group hoặc metadata khác.

### Bảo vệ cả hai đường dẫn

Ví dụ Spring Security có thể yêu cầu authority riêng để đọc tài liệu:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class DocumentationSecurityConfiguration {

    @Bean
    SecurityFilterChain documentationSecurity(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(authorize -> authorize
            .requestMatchers(
                "/swagger-ui.html",
                "/swagger-ui/**",
                "/v3/api-docs/**"
            ).hasAuthority("SCOPE_api-docs:read")
            .anyRequest().authenticated()
        );

        return http.build();
    }
}
~~~

Đây là ví dụ rule authorization; cần tích hợp vào `SecurityFilterChain` thực tế của ứng dụng và kiểm tra thứ tự các filter chain, matcher, CSRF, CORS và cơ chế đăng nhập. Nếu API có chain riêng, hãy bảo đảm matcher tài liệu được xử lý bởi chain dự kiến. Không tạo một chain quá rộng khiến rule bảo vệ API hiện hữu bị thay đổi ngoài ý muốn.

Không nhất thiết dùng cùng cơ chế OAuth2 của API cho trang tài liệu. Swagger UI có thể cần SSO, gateway authentication, VPN hoặc mạng nội bộ để tải tài liệu, trong khi operation API dùng OAuth2 scopes riêng. Chọn cách xác thực phù hợp với audience của tài liệu.

### Tắt tài liệu khi không cần phát hành

Nếu production không cần phục vụ tài liệu động, có thể tắt API docs và Swagger UI bằng cấu hình Springdoc:

~~~yaml
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: false
~~~

Đặt cấu hình theo profile/environment và xác minh endpoint thực sự không còn được phục vụ trong production. Nếu cần phát hành OpenAPI artifact tĩnh, có thể tạo artifact trong pipeline kiểm soát và lưu ở nơi có quyền truy cập phù hợp, trong khi tắt endpoint động trên ứng dụng.

Đổi `springdoc.api-docs.path` chỉ thay đường dẫn endpoint; nó không thay thế việc tắt hoặc bảo vệ endpoint.

### Swagger UI Try it out và lưu authorization

Swagger UI có thể gửi request thật từ trình duyệt. Hãy cân nhắc:

- Chỉ bật Try it out cho audience được phép gọi API từ giao diện đó.
- Không đưa token vào ví dụ hoặc query string.
- Không bật lưu authorization lâu dài trên trình duyệt dùng chung nếu không có lý do và policy rõ ràng.
- Dùng HTTPS và cấu hình CORS theo origin được phép.
- Tránh đưa dữ liệu thật vào response mẫu hoặc request prefill.
- Kiểm tra token được giữ trong memory/local storage theo cấu hình và phiên bản Swagger UI đang dùng.

Tùy chọn `persistAuthorization` có thể khiến trạng thái authorization được giữ lại giữa các lần tải trang. Không bật tùy chọn này một cách mặc định trên máy dùng chung hoặc kiosk; hãy đánh giá hành vi của phiên bản Swagger UI được nhúng và chính sách browser của tổ chức.

## Tiếp tục học

Sau bài này, hãy kết hợp bảo vệ tài liệu với authentication, authorization, grouped documentation, customizer và CI contract testing. Mỗi lần thay đổi schema, examples, server hoặc security metadata, hãy review nội dung được công bố theo đúng audience và xác minh cả OpenAPI artifact lẫn hành vi runtime.
