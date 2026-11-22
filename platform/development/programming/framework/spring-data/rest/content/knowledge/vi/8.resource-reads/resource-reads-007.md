# Đọc Location, Content-Type và các header trong phản hồi

## Mục tiêu

Sau bài này, bạn có thể đọc status code và response header; tìm URI tài nguyên mới qua **Location**; hiểu **Content-Type** và content negotiation; phân biệt Location với Content-Location và HAL self link; nhận biết ETag, cache và CORS; kiểm tra header bằng curl và Java HTTP Client.

## 1. Cấu trúc một HTTP response

Một HTTP response gồm status line, headers và body. Status line cho biết kết quả, headers mô tả metadata của response, còn body chứa representation mà server trả về.

Ví dụ minh họa khi tạo một member bằng Spring Data REST:

~~~http
HTTP/1.1 201 Created
Location: http://localhost:8080/api/members/42
Content-Type: application/hal+json

{
  "name": "Lan",
  "emailAddress": "lan@example.com",
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/members/42"
    }
  }
}
~~~

Đây là response minh họa. Status, URI, body và header thực tế phụ thuộc endpoint, cấu hình, phiên bản framework và dữ liệu.

Khi đọc response, hãy bắt đầu từ status code, sau đó kiểm tra header liên quan đến thao tác và cuối cùng đọc body. Không nên chỉ nhìn JSON rồi bỏ qua metadata HTTP.

## 2. Location: URI của tài nguyên được tạo

**Location** đặc biệt hữu ích khi client tạo tài nguyên bằng POST. Request có thể trông như sau:

~~~http
POST /api/members HTTP/1.1
Host: localhost:8080
Accept: application/hal+json
Content-Type: application/json

{
  "name": "Lan",
  "emailAddress": "lan@example.com"
}
~~~

Khi tạo thành công, server thường trả **201 Created** và chỉ ra URI của tài nguyên mới trong **Location**:

~~~http
HTTP/1.1 201 Created
Location: http://localhost:8080/api/members/42
Content-Type: application/hal+json
~~~

Client dùng URI trong Location để truy cập tài nguyên vừa tạo:

~~~http
GET /api/members/42 HTTP/1.1
Host: localhost:8080
Accept: application/hal+json
~~~

Cách này giúp client không phải tự ghép URL hoặc đoán ID từ response body. ID có thể không phải số tuần tự, URL có thể có cấu trúc riêng và server có thể thay đổi quy tắc định tuyến.

### Location có thể là URI tương đối

Giá trị Location có thể là URI reference. Nhiều server trả URL tuyệt đối, nhưng client cũng cần xử lý trường hợp tương đối bằng cách phân giải nó theo URI của response/request hiện tại.

Ví dụ:

~~~text
Request URI: http://localhost:8080/api/members
Location:    /api/members/42
Resolved:    http://localhost:8080/api/members/42
~~~

Hãy dùng thư viện URI để phân giải URI reference. Tránh nối chuỗi thủ công vì dễ tạo URL sai khi có dấu gạch chéo, query string hoặc proxy prefix.

### Không phải response nào cũng có Location

Location thường xuất hiện trong response tạo tài nguyên thành công hoặc một số response chuyển hướng. GET thông thường không bắt buộc phải trả header này. Nếu endpoint không trả Location, client nên dựa vào hợp đồng API và các liên kết trong body thay vì tự suy đoán.

## 3. Content-Type: kiểu representation trong response

**Content-Type** mô tả định dạng của body mà server đang gửi. Spring Data REST thường trả HAL với media type:

~~~http
Content-Type: application/hal+json
~~~

Media type này cho biết body là JSON theo cấu trúc HAL, có các thành phần như **_links** và có thể có **_embedded**.

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/members/42"
    }
  },
  "name": "Lan",
  "emailAddress": "lan@example.com"
}
~~~

Các response có thể dùng media type khác tùy negotiation và cấu hình. Đừng mặc định mọi JSON đều có cùng cấu trúc: JSON thuần và HAL JSON cùng dùng cú pháp JSON nhưng có hợp đồng representation khác nhau.

### Phân biệt Accept và Content-Type

| Header | Nằm ở đâu? | Vai trò |
|---|---|---|
| **Accept** | Request | Client nói server muốn nhận media type nào |
| **Content-Type** | Request có body | Client nói body gửi lên có định dạng nào |
| **Content-Type** | Response có body | Server nói body trả về có định dạng nào |

Ví dụ client gửi JSON và muốn nhận HAL JSON:

~~~http
Accept: application/hal+json
Content-Type: application/json
~~~

Hai header này mô tả hai chiều khác nhau. Nếu client yêu cầu media type server không hỗ trợ, server có thể trả **406 Not Acceptable**. Nếu client gửi body với Content-Type không được endpoint hỗ trợ, server có thể trả **415 Unsupported Media Type**.

Response không có body, ví dụ **204 No Content**, thường không có Content-Type vì không có representation để mô tả. Client nên kiểm tra status trước khi parse JSON.

## 4. Location, Content-Location và HAL self link

Ba thành phần có thể cùng chứa URI nhưng không có cùng ý nghĩa:

| Thành phần | Ý nghĩa |
|---|---|
| **Location** | URI của tài nguyên được tạo trong response 201 hoặc đích của một số response chuyển hướng |
| **Content-Location** | URI định danh representation trong body của response |
| **_links.self.href** | Liên kết hypermedia tự trỏ tới resource/representation theo hợp đồng HAL |

Ví dụ HAL body:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/members/42"
    }
  },
  "name": "Lan"
}
~~~

**_links.self.href** nằm trong body và giúp client tiếp tục khám phá API. **Location** là metadata ở tầng HTTP; khi POST tạo mới thành công, client thường dùng Location để biết URI của tài nguyên vừa tạo. Nếu body cũng có self link, hai URI thường có thể trỏ tới cùng resource, nhưng không nên giả định chúng luôn giống hệt nhau.

**Content-Location** nói về URI của representation trong message. Không dùng nó thay cho Location khi xử lý kết quả tạo mới.

## 5. Các header khác cần nhận biết

| Header | Ý nghĩa | Cách dùng |
|---|---|---|
| **ETag** | Validator đại diện cho một phiên bản representation | Gửi lại qua If-None-Match hoặc If-Match nếu server hỗ trợ |
| **Last-Modified** | Thời điểm representation được sửa lần cuối | Có thể dùng với If-Modified-Since |
| **Cache-Control** | Chính sách lưu cache | Quyết định response có thể cache và trong bao lâu |
| **Vary** | Header request nào ảnh hưởng representation | Giúp cache phân biệt các biến thể response |
| **Link** | Liên kết HTTP ở tầng header theo Web Linking | Có thể bổ sung quan hệ ngoài body |
| **Allow** | Các HTTP method resource hỗ trợ | Hữu ích khi kiểm tra method hợp lệ |
| **Access-Control-Expose-Headers** | Response header được JavaScript đọc qua CORS | Cần nếu frontend cần đọc Location, ETag hoặc Link |

Không phải endpoint nào cũng trả tất cả các header trên. Hãy xem chúng như metadata tùy theo hợp đồng và cấu hình server.

### ETag và conditional request

Nếu server trả:

~~~http
ETag: "member-42-v3"
~~~

client có thể gửi validator này ở request sau:

~~~http
If-None-Match: "member-42-v3"
~~~

Với GET, nếu representation chưa thay đổi và server hỗ trợ conditional request, server có thể trả **304 Not Modified** để client dùng bản cache. Với thao tác cập nhật, **If-Match** có thể giúp tránh ghi đè một phiên bản đã thay đổi; server có thể trả **412 Precondition Failed** nếu validator không còn khớp.

ETag chỉ có tác dụng như vậy khi server thực sự phát và kiểm tra validator. Không tự tạo ETag ở client và không giả định Spring Data REST luôn trả ETag cho mọi repository.

### Cache-Control và Vary

**Cache-Control** có thể quy định response là public, private, no-cache hoặc no-store và thời gian cache. Với dữ liệu cá nhân, client cần tôn trọng chính sách cache của server và không tự lưu response nhạy cảm vào cache dùng chung.

**Vary: Accept** cho biết representation có thể thay đổi theo Accept request header. Cache phải phân biệt response HAL và các biến thể media type khác nếu server cung cấp chúng.

### Link header và HAL _links

HTTP **Link** header và trường **_links** trong HAL đều mô tả quan hệ liên kết, nhưng nằm ở hai vị trí và theo hai cơ chế representation khác nhau. Spring Data REST thường dùng HAL body để client khám phá repository resource. Nếu response có Link header, hãy đọc relation và URI theo cú pháp header đó; không nhầm nó với JSON object trong body.

## 6. Kiểm tra response bằng curl

Dùng **-i** để in cả response header và body:

~~~bash
curl -i \
  -H "Accept: application/hal+json" \
  http://localhost:8080/api/members
~~~

Khi tạo member, thêm Content-Type cho request body:

~~~bash
curl -i -X POST \
  -H "Accept: application/hal+json" \
  -H "Content-Type: application/json" \
  -d '{"name":"Lan","emailAddress":"lan@example.com"}' \
  http://localhost:8080/api/members
~~~

Tập trung kiểm tra:

1. Status code có phải **201 Created** khi tạo mới thành công hay không.
2. Có header **Location** không và URI đó có trỏ tới item resource hay không.
3. **Content-Type** có phù hợp với representation client yêu cầu không.
4. Body có HAL link phù hợp để tiếp tục truy cập hay không.
5. Header cache/validator có xuất hiện và cần được client xử lý không.

Có thể lưu riêng header và body:

~~~bash
curl -sS \
  -D response-headers.txt \
  -o response-body.json \
  -H "Accept: application/hal+json" \
  http://localhost:8080/api/members
~~~

Tùy chọn **-D** ghi response headers ra file; **-o** ghi body. Cách này hữu ích khi so sánh metadata giữa nhiều request.

## 7. Đọc header bằng Java HTTP Client

Java 21 có HTTP Client trong JDK. Sau khi gửi request, client có thể lấy status code, header và body từ cùng một response.

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.Optional;

public class MemberApiClient {

    private final HttpClient httpClient = HttpClient.newHttpClient();

    public void createMember() throws Exception {
        URI collectionUri =
            URI.create("http://localhost:8080/api/members");

        String json = """
            {
              "name": "Lan",
              "emailAddress": "lan@example.com"
            }
            """;

        HttpRequest request = HttpRequest.newBuilder(collectionUri)
            .header("Accept", "application/hal+json")
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(json))
            .build();

        HttpResponse<String> response = httpClient.send(
            request,
            HttpResponse.BodyHandlers.ofString()
        );

        int status = response.statusCode();

        Optional<String> locationHeader =
            response.headers().firstValue("Location");

        Optional<String> contentType =
            response.headers().firstValue("Content-Type");

        URI createdUri = locationHeader
            .map(collectionUri::resolve)
            .orElse(null);

        System.out.println("Status: " + status);
        System.out.println("Location: " + createdUri);
        System.out.println("Content-Type: " + contentType.orElse("(absent)"));
        System.out.println("Body: " + response.body());
    }
}
~~~

Trong ví dụ, **firstValue** trả về Optional vì header có thể không tồn tại. **URI.resolve** xử lý cả URI tuyệt đối và tương đối dựa trên collection URI. Ứng dụng thực tế nên kiểm tra status code trước khi coi response là thao tác tạo thành công, rồi mới sử dụng Location.

Tên header HTTP không phân biệt chữ hoa/thường. Khi đọc header, dùng API của HTTP client thay vì tự parse raw response bằng cách tìm chuỗi trong văn bản.

## 8. Đọc header trong trình duyệt và CORS

Một response có thể chứa Location nhưng JavaScript chạy trên origin khác vẫn không đọc được header đó nếu server không expose nó.

Ví dụ frontend:

~~~javascript
const response = await fetch(
  "http://localhost:8080/api/members",
  {
    method: "POST",
    headers: {
      "Accept": "application/hal+json",
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      name: "Lan",
      emailAddress: "lan@example.com"
    })
  }
);

const location = response.headers.get("Location");
const contentType = response.headers.get("Content-Type");
~~~

Để JavaScript đọc được **Location**, **ETag**, **Link** hoặc **Content-Location**, server cần expose các header đó qua CORS:

~~~http
Access-Control-Expose-Headers: Location, Content-Location, ETag, Link
~~~

Ví dụ cấu hình Spring Data REST qua RepositoryRestConfigurer:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.web.servlet.config.annotation.CorsRegistry;

@Configuration
public class RestCorsConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {
        cors.addMapping("/api/**")
            .allowedOrigins("https://app.example.com")
            .allowedMethods("GET", "POST", "PUT", "PATCH", "DELETE")
            .allowedHeaders("Accept", "Content-Type", "If-Match", "If-None-Match")
            .exposedHeaders("Location", "Content-Location", "ETag", "Link");
    }
}
~~~

Thay origin ví dụ bằng origin frontend thực tế và tích hợp vào cấu hình CORS hiện có. Nếu request dùng credentials, origin phải cụ thể và phù hợp với chính sách credential; không dùng wildcard một cách tùy tiện.

CORS chỉ quyết định trình duyệt có cho JavaScript đọc response hay không. Nó không thay thế authentication hoặc authorization ở server.

## 9. Những lỗi thường gặp

### POST thành công nhưng client không tìm thấy tài nguyên mới

Kiểm tra status code và header Location. Nếu client chỉ parse body, nó có thể bỏ qua URI canonical mà server cung cấp. Với response 201, hãy ưu tiên Location theo hợp đồng HTTP và đối chiếu self link nếu body có HAL.

### Client parse body dù response không có nội dung

Response 204 không có body. Kiểm tra status trước khi gọi JSON parser hoặc deserialize entity.

### Gửi Accept sai

Client gửi Accept không được hỗ trợ có thể nhận 406. Hãy yêu cầu media type mà API thực sự cung cấp và đọc Content-Type response để biết server đã trả gì.

### Nhầm Content-Type của request với response

Request Content-Type mô tả JSON client gửi lên; response Content-Type mô tả HAL/JSON server trả về. Hai giá trị có thể khác nhau.

### Trình duyệt không đọc được Location

Kiểm tra response thực tế trong Network panel. Nếu header tồn tại nhưng JavaScript đọc ra null, kiểm tra Access-Control-Expose-Headers và cấu hình CORS của server.

### Dùng Location như bằng chứng authorization

Location chỉ định URI. Nó không cấp quyền truy cập. Request GET tới URI đó vẫn phải qua xác thực, phân quyền và kiểm tra dữ liệu như các request khác.

## 10. Ghi nhớ

- Đọc status code trước, rồi mới quyết định cách xử lý headers và body.
- **Location** thường cho biết URI của tài nguyên mới sau **201 Created**.
- **Content-Type** mô tả định dạng representation trong response; HAL thường dùng **application/hal+json**.
- **Accept** là yêu cầu representation từ client; **Content-Type** mô tả body đang gửi hoặc nhận.
- **Content-Location** và HAL **_links.self.href** có vai trò riêng, không thay thế tùy tiện cho Location.
- **ETag**, **Last-Modified**, **Cache-Control** và **Vary** hỗ trợ validator và cache khi server cung cấp.
- Trình duyệt cần **Access-Control-Expose-Headers** để JavaScript đọc các response header không được expose mặc định.
- Header không thay thế body, hypermedia, validation hoặc security; hãy đọc chúng cùng nhau để hiểu đầy đủ response.
