# OPTIONS, Allow và mô tả phương thức được hỗ trợ

## 1. Bài toán: client biết có thể làm gì với một resource bằng cách nào?

Trong REST API, URI định danh **resource**, còn phương thức HTTP diễn tả **hành động theo ngữ nghĩa giao thức**. Một client có thể đọc tài liệu qua **GET**, cập nhật một phần qua **PATCH**, nhưng không được tạo hoặc xóa tài liệu tại cùng URI. Nếu client muốn biết resource hỗ trợ những phương thức nào trước khi gửi yêu cầu, HTTP cung cấp phương thức **OPTIONS** và trường header phản hồi **Allow**.

Ví dụ resource **/api/documents/42** có thể cho phép **GET**, **HEAD**, **PATCH** và **OPTIONS**, trong khi **POST** chỉ hợp lệ với collection **/api/documents**. Nếu client gửi **DELETE /api/documents/42** mà resource không cho phép DELETE, server có thể trả **405 Method Not Allowed** kèm **Allow**.

Trong module **INTEGRATION_API_REST**, bài này liên kết cách thiết kế resource/URI với phương thức và mã trạng thái HTTP, hợp đồng dữ liệu rõ ràng, OpenAPI, xác thực/phân quyền, cache, kiểm thử và cách triển khai bằng Java/Spring hoặc công nghệ tương đương.

Sau bài học, bạn cần có thể:

1. Giải thích **OPTIONS**, phạm vi request target và ngữ nghĩa safe/idempotent.
2. Phân biệt **Allow**, **405 Method Not Allowed** và **501 Not Implemented**.
3. Phân biệt yêu cầu thăm dò phương thức bình thường với **CORS preflight OPTIONS** của trình duyệt.
4. Tạo và kiểm tra phản hồi OPTIONS/Allow đúng cho một API nhiều resource.
5. Triển khai cấu hình phù hợp trong Spring MVC/Spring Security và kiểm thử bằng curl/OpenAPI.

## 2. Ngữ nghĩa của OPTIONS theo HTTP

**OPTIONS** yêu cầu server mô tả các lựa chọn liên lạc hoặc năng lực liên quan tới một **target resource**, hoặc tới server nói chung khi request target là dấu sao. Nó dùng để hỏi khả năng được hỗ trợ; bản thân việc hỏi **không có nghĩa client đã thực hiện một thay đổi nghiệp vụ**.

### Hai dạng request target cần phân biệt

**Hỏi một resource cụ thể:**

~~~http
OPTIONS /api/documents/42 HTTP/1.1
Host: api.example.test
Accept: */*

~~~

Trong trường hợp này, câu hỏi là: “Server có những lựa chọn giao tiếp nào đối với **/api/documents/42**?”

**Hỏi về server nói chung:**

~~~http
OPTIONS * HTTP/1.1
Host: api.example.test

~~~

Request target **\*** không chỉ đến một resource tài liệu; nó hỏi năng lực áp dụng cho server ở phạm vi chung. Đây là cú pháp HTTP đặc biệt, **không phải** URI **/\*** hay **/api/***. Không nên sử dụng phản hồi OPTIONS * như danh sách phương thức chính xác cho mọi resource.

### Safe và idempotent

Theo ngữ nghĩa HTTP, **OPTIONS là phương thức safe**: mục đích client yêu cầu là lấy thông tin, không phải đổi trạng thái nghiệp vụ. Safe method cũng được xem là **idempotent** ở cấp ngữ nghĩa giao thức: lặp lại cùng yêu cầu OPTIONS không được khiến tài nguyên nghiệp vụ thay đổi dồn tích.

Server có thể ghi access log, metric hoặc audit cho mỗi lần gọi; các tác động phụ nội bộ ấy không biến OPTIONS thành một lệnh tạo/xóa tài liệu. Một implementation dùng OPTIONS để kích hoạt job, gửi email hoặc ghi đơn hàng là **sai mục đích phương thức**.

| Thuộc tính | OPTIONS |
|---|---|
| Mục đích | Khám phá năng lực giao tiếp của resource/server |
| Safe | Có |
| Idempotent | Có theo ngữ nghĩa phương thức |
| Thường dùng request body | Không cần; body trong OPTIONS có ngữ nghĩa không được HTTP chuẩn hóa chung |
| Phản hồi thường gặp | **200 OK** hoặc **204 No Content**, tùy có nội dung mô tả hay không |
| Có bắt buộc trả Allow? | Không bắt buộc cho mọi phản hồi OPTIONS thành công |
| Cache HTTP thông thường | Phản hồi OPTIONS **không cacheable** theo HTTP semantics |

Không giả định mọi server hoặc reverse proxy đều hỗ trợ OPTIONS trên mọi đường dẫn. OPTIONS là phương thức được định nghĩa trong HTTP, nhưng **hành vi phục vụ** còn phụ thuộc cấu hình endpoint, proxy, CORS và lớp bảo mật.

## 3. Header Allow diễn đạt điều gì?

**Allow** là trường header phản hồi liệt kê các phương thức HTTP hiện được quảng bá là được phép đối với **target resource**.

~~~http
HTTP/1.1 204 No Content
Allow: GET, HEAD, PATCH, OPTIONS

~~~

Ý nghĩa: với target resource tương ứng, server công bố bốn phương thức **GET**, **HEAD**, **PATCH** và **OPTIONS**. Danh sách phương thức phân tách bằng dấu phẩy; thứ tự không mang ý nghĩa ưu tiên. Client không được suy luận rằng hỗ trợ PATCH đồng nghĩa chấp nhận mọi **định dạng dữ liệu PATCH**.

### Các quy tắc quan trọng

| Quy tắc | Giải thích |
|---|---|
| **Allow phụ thuộc resource** | **/api/documents** có thể cho POST, còn **/api/documents/42** chỉ có GET/PATCH |
| **Allow là thông tin tại thời điểm phản hồi** | Tập phương thức có thể thay đổi theo trạng thái hoặc cấu hình server |
| **Allow có thể xuất hiện trong OPTIONS thành công** | Hữu ích cho khám phá khả năng, nhưng chuẩn không bắt buộc mọi OPTIONS phải có |
| **Allow bắt buộc trong 405** | Origin server **MUST** tạo Allow khi phản hồi **405 Method Not Allowed** |
| **Allow không thay thế authorization** | Một phương thức được liệt kê vẫn có thể yêu cầu authentication/permission |
| **Danh sách trống có ý nghĩa** | **Allow:** với giá trị trống có thể cho biết hiện không có phương thức nào được phép trên resource |

Phần **Allow** mô tả **khả năng phương thức của resource**, không phải giấy phép vô điều kiện cho người gọi. Ví dụ server có thể hỗ trợ DELETE nhưng người dùng chỉ có quyền GET; yêu cầu DELETE vẫn phải trải qua xác thực và phân quyền. Chính sách bảo mật có thể chủ động hạn chế thông tin được tiết lộ, nhưng không được dùng một header quảng bá như cơ chế kiểm soát truy cập.

### HEAD và OPTIONS trong danh sách

**HEAD** có ngữ nghĩa như GET nhưng phản hồi **không có message content**. Framework thường hỗ trợ HEAD cho route GET; tuy nhiên cần kiểm thử hành vi thực tế của server, proxy và middleware trước khi ghi HEAD vào Allow. Không tự suy ra rằng OPTIONS luôn xuất hiện chỉ vì server triển khai HTTP.

### Hỗ trợ PATCH: mô tả thêm định dạng

Một resource chấp nhận PATCH có thể trả thêm **Accept-Patch** để nêu các media type cho patch document, ví dụ:

~~~http
HTTP/1.1 204 No Content
Allow: GET, HEAD, PATCH, OPTIONS
Accept-Patch: application/merge-patch+json

~~~

**Accept-Patch** không thay thế Allow. Nó trả lời câu hỏi “PATCH nhận kiểu tài liệu gì?”, còn Allow trả lời “phương thức HTTP nào được hỗ trợ?”. Trường này hữu ích khi xây API cập nhật một phần, và cách xử lý merge patch phải được mô tả trong hợp đồng API.

## 4. OPTIONS và mã trạng thái phản hồi

### OPTIONS thành công có hoặc không có nội dung

**204 No Content** phù hợp khi server chỉ cần trả metadata trong header:

~~~http
OPTIONS /api/documents/42 HTTP/1.1
Host: api.example.test

HTTP/1.1 204 No Content
Allow: GET, HEAD, PATCH, OPTIONS
Accept-Patch: application/merge-patch+json

~~~

Đây là cặp request/response được đặt chung để dễ đọc. **204 không được có response body**, và server không được gửi **Content-Length** trong phản hồi 204.

**200 OK** có thể dùng khi server cung cấp nội dung mô tả thêm, với định dạng được API xác định:

~~~http
HTTP/1.1 200 OK
Allow: GET, HEAD, PATCH, OPTIONS
Content-Type: application/json

{
  "resource": "/api/documents/42",
  "methods": ["GET", "HEAD", "PATCH", "OPTIONS"],
  "documentation": "/api-docs"
}
~~~

JSON trên là **quy ước minh họa của API**, không phải định dạng bắt buộc được chuẩn HTTP quy định cho OPTIONS. Nếu dùng body tùy biến, cần công bố schema để client có thể đọc đúng.

### Khi phương thức đã biết nhưng resource không chấp nhận: 405

~~~http
DELETE /api/documents/42 HTTP/1.1
Host: api.example.test

HTTP/1.1 405 Method Not Allowed
Allow: GET, HEAD, PATCH, OPTIONS
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/method-not-allowed",
  "title": "Method Not Allowed",
  "status": 405,
  "detail": "Resource này không hỗ trợ DELETE."
}
~~~

**405** nghĩa là server **nhận ra phương thức** nhưng target resource không hỗ trợ nó. Origin server phải kèm **Allow** để thông báo tập phương thức hiện hành. Body theo **Problem Details** ở trên chỉ là ví dụ; thiết kế lỗi có thể tùy hợp đồng, nhưng status và header phải nhất quán.

### Phân biệt 405, 501, 401, 403 và 404

| Tình huống | Mã thường phù hợp | Ý nghĩa |
|---|---|---|
| DELETE là phương thức server hiểu, nhưng không hỗ trợ trên URI này | **405** | Method Not Allowed; có Allow |
| Server không nhận ra/không có khả năng hỗ trợ phương thức đó đối với bất kỳ resource nào | **501** | Not Implemented; khác với 405 |
| Endpoint yêu cầu xác thực mà chưa có credentials hợp lệ | **401** | Unauthorized theo HTTP; thường kèm thử thách xác thực phù hợp |
| Đã nhận diện người gọi nhưng không được phép thực hiện | **403** | Forbidden; không cần quảng bá phương thức để cấp quyền |
| Resource không tồn tại, hoặc server chọn không tiết lộ sự tồn tại | **404** | Not Found |
| CORS preflight bị từ chối theo chính sách | Có thể là **403** hoặc phản hồi không có quyền CORS thích hợp | Trình duyệt không thực hiện cross-origin request mong muốn |

Kết quả thực tế phụ thuộc **thứ tự filter, routing, xác thực và proxy**: ví dụ middleware có thể trả 401/403 trước khi router xác định 405. Khi thiết kế API, cần có chính sách nhất quán; không nên coi mọi DELETE trả 403 hoặc 404 đều là lỗi phương thức.

## 5. Quan hệ giữa OPTIONS, resource và REST contract

Một API có collection và item resource nên có tập phương thức được thiết kế riêng:

| Resource | Ý nghĩa | Các method ví dụ | Method bị từ chối ví dụ |
|---|---|---|---|
| **/api/documents** | Danh sách và tạo tài liệu | GET, HEAD, POST, OPTIONS | DELETE cả collection nếu API không cho phép |
| **/api/documents/{id}** | Một tài liệu cụ thể | GET, HEAD, PATCH, OPTIONS | POST vào item URI nếu không được thiết kế |
| **/api/documents/{id}/versions** | Các phiên bản của tài liệu | GET, HEAD, POST, OPTIONS | PUT khi không hỗ trợ thay thế toàn bộ collection |
| **/api/jobs/{id}** | Trạng thái một tác vụ | GET, HEAD, DELETE, OPTIONS (nếu cho hủy) | PATCH nếu không có hành vi cập nhật từng phần |

Danh sách trên là **bản thiết kế giả định**, không phải yêu cầu bắt buộc của REST. Một API có thể chọn PUT để thay thế toàn bộ một resource, hoặc không cho DELETE vì quy tắc lưu trữ. Phương thức được hỗ trợ phải thống nhất ở **router, authorization, tài liệu OpenAPI và kiểm thử**.

### Khám phá không đồng nghĩa thực thi

Client có thể gửi OPTIONS để thăm dò và sau đó gọi PATCH. Tuy nhiên giữa hai yêu cầu:

- Quyền người dùng có thể thay đổi.
- Resource có thể bị khóa, xóa hoặc chuyển trạng thái.
- Feature flag hoặc phiên bản API có thể thay đổi.
- API gateway có thể có chính sách riêng theo tenant hoặc origin.

Vì vậy client **vẫn phải xử lý lỗi của thao tác thật**. OPTIONS không cung cấp “đặt chỗ quyền” cho request tiếp theo và không thay thế optimistic concurrency, **ETag/If-Match**, idempotency hay kiểm tra trạng thái nghiệp vụ.

## 6. CORS preflight: cũng là OPTIONS nhưng hỏi điều khác

Trong ứng dụng web, bạn sẽ thường thấy trình duyệt tự gửi **OPTIONS** trước một số cross-origin request. Đây là **CORS preflight**, nhằm hỏi server xem origin, phương thức và các header của request sắp gửi có được chính sách CORS cho phép hay không.

Ví dụ frontend chạy tại **https://shop.example.test**, API tại **https://api.example.test**. JavaScript sắp gửi một request **PATCH** với **Authorization** và **Content-Type: application/merge-patch+json**. Trình duyệt có thể gửi:

~~~http
OPTIONS /api/documents/42 HTTP/1.1
Host: api.example.test
Origin: https://shop.example.test
Access-Control-Request-Method: PATCH
Access-Control-Request-Headers: authorization,content-type

~~~

Phản hồi preflight hợp lệ theo chính sách ứng dụng có thể là:

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://shop.example.test
Access-Control-Allow-Methods: GET, HEAD, PATCH, OPTIONS
Access-Control-Allow-Headers: Authorization, Content-Type
Access-Control-Max-Age: 600
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers

~~~

Đây là ví dụ cho **một origin được cho phép**. Phản hồi preflight không bắt buộc phải có **Allow**, dù API có thể bổ sung Allow nếu muốn cung cấp cả metadata về resource.

### Phân biệt ba header dễ bị nhầm

| Header | Dùng ở đâu | Trả lời câu hỏi |
|---|---|---|
| **Allow** | Phản hồi, đặc biệt là **405**, và có thể là OPTIONS thành công | Resource có thể nhận các **HTTP methods** nào? |
| **Access-Control-Request-Method** | Request **OPTIONS preflight** do trình duyệt tạo | Trình duyệt dự định gọi method nào sau preflight? |
| **Access-Control-Allow-Methods** | Phản hồi **CORS preflight** | Chính sách CORS cho origin/request đó cho phép các method nào? |

**Allow và Access-Control-Allow-Methods không đồng nghĩa.** Một route có thể hỗ trợ DELETE ở mức HTTP nhưng chính sách CORS chỉ cho web frontend dùng GET/PATCH; ứng dụng server-to-server vẫn có thể gọi DELETE nếu có quyền. Ngược lại, nếu CORS quảng bá DELETE nhưng route không triển khai DELETE, preflight có thể thành công và request DELETE thực tế vẫn nhận 405.

### Những trường CORS khác cần hiểu

- **Origin:** origin của trang web gửi request, gồm scheme, host và port.
- **Access-Control-Request-Headers:** tên các header không thuộc nhóm được phép tự động mà trình duyệt muốn gửi trong request thật.
- **Access-Control-Allow-Origin:** origin được đọc phản hồi, không phải danh sách người dùng đã xác thực.
- **Access-Control-Allow-Headers:** tên header được chấp nhận theo CORS.
- **Access-Control-Allow-Credentials:** cho phép trình duyệt gửi/phơi bày phản hồi với credentials theo quy tắc CORS; phải cấu hình đúng và hiểu tác động bảo mật.
- **Access-Control-Max-Age:** thời gian trình duyệt có thể lưu kết quả preflight vào **CORS-preflight cache**, có giới hạn do browser áp dụng.
- **Vary:** quan trọng khi phản hồi thay đổi theo Origin hoặc yêu cầu preflight, tránh cache/proxy tái sử dụng sai chính sách.

**Lưu ý về cache:** HTTP định nghĩa phản hồi OPTIONS không cacheable bởi HTTP cache thông thường. Việc trình duyệt dùng **Access-Control-Max-Age** để cache quyết định preflight là **cơ chế CORS riêng**, không phủ định quy tắc HTTP này.

### Preflight không xảy ra với mọi cross-origin request

Một cross-origin **GET** chỉ dùng các header đơn giản phù hợp có thể không cần preflight. Dù vậy, phản hồi GET thực tế vẫn phải đáp ứng quy tắc CORS để JavaScript đọc được nó. Các yêu cầu có phương thức hoặc header ngoài nhóm cho phép tự động, như PATCH hay Authorization trong ví dụ, thường kích hoạt preflight.

Browser chủ động thực thi CORS; công cụ như **curl/Postman** không tự chặn truy cập dữ liệu vì thiếu CORS header. Bởi vậy, chạy curl thành công **không chứng minh** frontend trình duyệt sẽ vượt qua CORS.

### Bảo mật: CORS không phải authorization

CORS là chính sách trình duyệt kiểm soát việc JavaScript từ một origin truy cập phản hồi cross-origin. Nó **không thay thế** authentication, authorization, CSRF protection, validation hay rate limiting. Request thực tế vẫn phải xác thực token/session và kiểm tra quyền resource.

Với request dùng credentials, **không** trả **Access-Control-Allow-Origin: \*** đồng thời với **Access-Control-Allow-Credentials: true**; browser sẽ từ chối kiểu kết hợp này. Khi dùng allowlist origin động, phải xác thực origin theo allowlist chặt chẽ và trả đúng origin được phép, tránh phản chiếu tùy ý.

Về thông lệ, CORS preflight do trình duyệt gửi **không mang credentials thông thường**; lớp bảo mật cần cho phép việc kiểm tra preflight hợp lệ trước khi yêu cầu xác thực request thật. Ngoại lệ triển khai trình duyệt/chứng chỉ phía client có thể tồn tại, nhưng không nên thiết kế luồng preflight phụ thuộc token Authorization của người dùng.

## 7. Một chuỗi request thực tế: OPTIONS trước, PATCH sau

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant G as API Gateway / CORS layer
    participant A as REST API
    B->>G: OPTIONS /api/documents/42 (Origin, ACR-Method: PATCH)
    G-->>B: 204 + Access-Control-Allow-*
    Note over B: Kiểm tra origin, method và headers
    B->>G: PATCH /api/documents/42 + Authorization
    G->>A: PATCH đã qua routing, authentication và authorization
    A->>A: Kiểm tra schema, quyền và phiên bản dữ liệu
    A-->>G: 200/204 hoặc lỗi nghiệp vụ/HTTP phù hợp
    G-->>B: Response và CORS headers thích hợp
~~~

Preflight chỉ quyết định browser có được **gửi request thực tế theo chính sách CORS** hay không. Request PATCH sau đó vẫn có thể trả **401**, **403**, **404**, **409**, **412**, **415** hoặc **422** tùy tình huống. Phản hồi CORS thành công không có nghĩa cập nhật dữ liệu chắc chắn thành công.

Nếu preflight không đạt, trình duyệt có thể báo lỗi CORS và **không gửi PATCH thực tế**. Server sẽ không có log của PATCH, chỉ thấy OPTIONS. Đây là nguyên nhân thường khiến nhà phát triển hiểu sai rằng controller PATCH “không được gọi”.

## 8. Triển khai bằng Java và Spring MVC

### 8.1. Khai báo route đúng với ngữ nghĩa HTTP

Spring MVC dùng annotation mapping để gắn phương thức với resource. Ví dụ dưới đây minh họa route GET cho một item; dữ liệu trả về là giả định:

~~~java
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/items")
public class ItemController {
    @GetMapping("/{id}")
    public Map<String, Object> getItem(@PathVariable String id) {
        return Map.of("id", id, "name", "Ví dụ");
    }
}
~~~

Với cấu hình Spring MVC thông dụng, framework có thể **tự xử lý HEAD/OPTIONS** cho các route đã khai báo và tạo **Allow** dựa trên mapping. Request dùng phương thức khác trên cùng route thường được xử lý thành **405**. Hành vi phản hồi cụ thể phải được kiểm tra với **phiên bản Spring, Spring Security, filter và reverse proxy** đang dùng; không nên khẳng định mọi OPTIONS sẽ là 204 hay mọi response sẽ có cùng Allow.

Khi cần chủ động tùy biến OPTIONS (chẳng hạn cung cấp metadata đặc thù hoặc Accept-Patch), có thể cấu hình handler riêng. Nếu làm vậy, **đừng hard-code Allow không còn khớp với mapping thực tế**.

### 8.2. Ví dụ OPTIONS handler tùy biến

Trong một controller có route GET và PATCH thực sự được triển khai ở tầng service, có thể thêm một handler như sau:

~~~java
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;

// Đặt trong controller tương ứng; chỉ quảng bá những method đã triển khai.
@RequestMapping(path = "/{id}", method = RequestMethod.OPTIONS)
public ResponseEntity<Void> optionsItem() {
    return ResponseEntity.noContent()
            .allow(HttpMethod.GET, HttpMethod.HEAD,
                   HttpMethod.PATCH, HttpMethod.OPTIONS)
            .build();
}
~~~

Đây là **đoạn minh họa**, không phải một controller độc lập có thể chạy ngay; nó giả định các route GET/PATCH cùng resource tồn tại. Nếu ứng dụng chỉ có GET thì phải sửa Allow theo thực tế. Với Spring MVC, xử lý CORS preflight của framework/filter có thể **chặn hoặc trả phản hồi trước khi controller OPTIONS tùy biến được gọi**, nên cấu hình CORS cần được kiểm thử riêng.

### 8.3. Cấu hình CORS có allowlist rõ ràng

Ví dụ cấu hình dành cho frontend được phép truy cập API từ một origin xác định:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class ApiCorsConfiguration {
    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(
                List.of("https://shop.example.test"));
        cors.setAllowedMethods(
                List.of("GET", "HEAD", "PATCH", "OPTIONS"));
        cors.setAllowedHeaders(
                List.of("Authorization", "Content-Type"));
        cors.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

Trong ứng dụng dùng Spring Security, cần **kích hoạt tích hợp CORS trong security filter chain** (ví dụ qua cấu hình **http.cors(...)** phù hợp phiên bản) để preflight được xử lý trước bước xác thực yêu cầu thật. Không chỉ thêm cấu hình CORS ở controller rồi mặc định preflight sẽ đi qua mọi security filter.

Ví dụ không bật **allowCredentials** vì trường hợp này chưa xác định sử dụng cookie/session. Nếu ứng dụng dùng credentials/cookies, phải thiết kế riêng policy origin, CSRF và SameSite, rồi kiểm thử. Không dùng **allowedOrigins = ["*"]** theo thói quen cho API có dữ liệu nhạy cảm.

### 8.4. Các tình huống lỗi trong Spring

| Quan sát | Nguyên nhân khả dĩ | Kiểm tra |
|---|---|---|
| OPTIONS trả **401/403** | Security filter bắt authentication trước CORS | Thứ tự filter, tích hợp CORS, chính sách preflight |
| OPTIONS trả **404** | Proxy không chuyển tiếp, route/mapping không khớp | URL, context path, gateway và Spring mappings |
| OPTIONS trả **405** | Route/handler hoặc filter không hỗ trợ OPTIONS | Allow, mapping và log framework |
| OPTIONS trả **200/204** nhưng browser vẫn báo CORS | Header **Access-Control-Allow-*** không đúng origin/method/header | Kiểm tra chính xác preflight trong DevTools |
| OPTIONS đúng nhưng PATCH trả 403 | Phân quyền của request thực tế bị từ chối | Role/scope/resource ownership, token |
| Allow khác tài liệu API | Route thay đổi, reverse proxy hoặc handler hard-code | Kiểm thử hợp đồng trên môi trường triển khai thật |

Với Spring, nhiều trường hợp xử lý **HEAD** hoặc **OPTIONS** tự động có thể tạo phản hồi khác kỳ vọng về status hoặc header. Hãy kiểm tra **hành vi thực tế**, tránh viết test chỉ dựa trên một status giả định.

## 9. Kiểm thử bằng curl và HTTP client

Các lệnh dưới đây dùng tên miền **api.example.test** làm chỗ giữ chỗ; thay bằng host của môi trường thử nghiệm.

### 9.1. OPTIONS trực tiếp trên resource

~~~bash
curl -i -X OPTIONS https://api.example.test/api/items/42
~~~

Kiểm tra status (có thể 200 hoặc 204), header Allow nếu API công bố, và **không có side effect nghiệp vụ**. Nếu API bảo vệ route ở gateway, có thể nhận status khác; ghi lại hành vi như một phần hợp đồng.

### 9.2. Mô phỏng CORS preflight

~~~bash
curl -i -X OPTIONS \
  -H 'Origin: https://shop.example.test' \
  -H 'Access-Control-Request-Method: PATCH' \
  -H 'Access-Control-Request-Headers: authorization,content-type' \
  https://api.example.test/api/items/42
~~~

Kiểm tra **Access-Control-Allow-Origin**, **Access-Control-Allow-Methods** và **Access-Control-Allow-Headers** khớp với origin, method, header được yêu cầu. Chạy lại với một origin không được tin cậy để đảm bảo server **không cấp quyền CORS ngoài allowlist**.

### 9.3. Phương thức nhận diện được nhưng route không cho phép

~~~bash
curl -i -X DELETE https://api.example.test/api/items/42
~~~

Nếu server nhận diện DELETE nhưng resource không hỗ trợ, và không có lớp security từ chối trước, kỳ vọng **405** kèm header **Allow** phản ánh route thực tế. Đừng dùng DELETE với URL có thể xóa dữ liệu thật; hãy dùng **môi trường thử nghiệm** và một route đã xác nhận không cho phép DELETE.

### 9.4. HEAD có body hay không?

~~~bash
curl -I https://api.example.test/api/items/42
~~~

Kiểm tra response **không có body**, có metadata thích hợp; header có thể khác GET ở một số trường mà chỉ được tính khi tạo nội dung. Nếu Allow chứa HEAD, test phải chứng minh HEAD thực sự hoạt động.

### 9.5. OPTIONS * trên kết nối HTTP/1.1

~~~bash
curl --http1.1 -i -X OPTIONS --request-target '*' \
  https://api.example.test/
~~~

Một số proxy, load balancer hoặc server không hỗ trợ yêu cầu này hoặc không chuyển tiếp theo cách mong đợi; sử dụng khi thực sự cần kiểm tra năng lực server tổng quát. Không coi phản hồi này là danh sách endpoint/operation của REST API.

### Ma trận kiểm thử tối thiểu

| Kiểm thử | Điều muốn chứng minh |
|---|---|
| OPTIONS vào resource hợp lệ | Status/Allow/metadata đúng, không thay đổi tài nguyên |
| OPTIONS vào URI khác | Allow theo đúng URI, không copy từ collection sang item |
| DELETE/POST sai target | 405 có Allow nếu router đã xác định method không được phép |
| Method không được server nhận diện | 501 khi máy chủ thực sự không hỗ trợ method đó |
| Preflight origin hợp lệ | CORS phản hồi đúng origin, method, request headers |
| Preflight origin bị cấm | Không cấp quyền CORS cho origin ngoài allowlist |
| Preflight cho method không được chấp nhận | Browser không thể tiến hành request theo CORS |
| Preflight hợp lệ nhưng request thật thiếu quyền | Request thật nhận 401/403 theo chính sách |
| HEAD trên GET resource | Không gửi body, metadata phù hợp |
| Có proxy/gateway | Header/status không bị gateway thay đổi trái hợp đồng |

**Cảnh báo kiểm thử:** status 200/204 từ curl chỉ cho biết server đã trả lời OPTIONS; nó không có nghĩa trình duyệt sẽ chấp nhận preflight. Cần kiểm tra header thực tế và thử một request từ browser nếu tính năng phụ thuộc CORS.

## 10. Diễn đạt hợp đồng trong OpenAPI

OpenAPI mô tả các operation theo phương thức và URI. Một resource có thể có GET/PATCH, còn phản hồi OPTIONS có thể do gateway hoặc framework tự cung cấp. Hợp đồng cần nói rõ **những operation nghiệp vụ** được hỗ trợ; nếu chủ động cung cấp OPTIONS metadata, bạn cũng có thể mô tả operation **options**.

Ví dụ rút gọn theo phong cách OpenAPI 3:

~~~yaml
openapi: 3.1.0
info:
  title: Document API
  version: 1.0.0
paths:
  /api/documents/{id}:
    parameters:
      - name: id
        in: path
        required: true
        schema:
          type: string
    get:
      summary: Đọc một tài liệu
      responses:
        '200':
          description: Đọc thành công
        '404':
          description: Không tìm thấy
    patch:
      summary: Cập nhật một phần tài liệu
      requestBody:
        required: true
        content:
          application/merge-patch+json:
            schema:
              type: object
      responses:
        '204':
          description: Cập nhật thành công, không có body
        '412':
          description: Điều kiện If-Match không đạt
    options:
      summary: Khám phá các phương thức hỗ trợ
      responses:
        '204':
          description: Không có nội dung, trả metadata trong header
          headers:
            Allow:
              description: Các HTTP method được quảng bá cho resource
              schema:
                type: string
                example: GET, HEAD, PATCH, OPTIONS
~~~

Ví dụ YAML này mô tả một API **thực sự triển khai OPTIONS và công bố Allow**. Nếu OPTIONS chỉ dùng nội bộ ở tầng CORS/framework và không là một operation được hỗ trợ công khai, không bắt buộc phải thêm options trong từng path. Ngược lại, document GET/PATCH mà router lại chỉ hỗ trợ GET sẽ khiến client hiểu sai; **OpenAPI và hành vi thực tế cần được đối chiếu bằng contract test**.

**OpenAPI không thay thế CORS policy.** Tài liệu operation không tự quyết định trình duyệt có được gửi cross-origin request. CORS còn phụ thuộc origin, request method, header và credentials, phải cấu hình/kiểm thử ở lớp phục vụ request thật.

## 11. Những lỗi phổ biến và cách khắc phục

| Phản mẫu | Tác động | Cách sửa |
|---|---|---|
| Dùng OPTIONS để tạo/xóa tài nguyên | Vi phạm safe semantics, gây side effect bất ngờ | Tách hành động nghiệp vụ sang POST/PUT/PATCH/DELETE phù hợp |
| Bỏ header Allow trong phản hồi 405 | Client mất thông tin phương thức được hỗ trợ, vi phạm quy tắc HTTP | Cho router sinh Allow và viết contract test |
| Dùng Allow thay Access-Control-Allow-Methods | Browser vẫn từ chối preflight | Trả các header CORS chuẩn trên phản hồi preflight |
| Nghĩ preflight thành công là người dùng đã được cấp quyền | Tạo nguy cơ bỏ qua kiểm tra authorization | Xác thực và kiểm tra quyền trên request thực |
| Bật Access-Control-Allow-Origin: * với credentials | Browser không chấp nhận; có thể dẫn tới policy sai | Dùng allowlist origin cụ thể và cấu hình credentials đúng |
| Chặn mọi OPTIONS bằng authentication | Frontend cross-origin không gửi được request chính | Tích hợp CORS trước auth, kiểm tra request thật riêng |
| Hard-code Allow và quên cập nhật khi đổi route | 405 hoặc OPTIONS quảng bá sai hành vi | Sinh từ routing hoặc đồng bộ bằng contract test |
| OPTIONS 204 nhưng có response body/Content-Length | Vi phạm quy tắc phản hồi 204 | Bỏ body và Content-Length |
| Cho rằng OPTIONS HTTP được CDN cache như GET | Hiểu sai hiệu lực và trạng thái cache | Phân biệt HTTP cache với CORS preflight cache |
| Chỉ thử curl, kết luận browser chắc chắn hoạt động | Curl không thực thi CORS như trình duyệt | Thử browser DevTools và kiểm tra preflight |
| Giả định OPTIONS * mô tả mọi URI | Sai phạm vi request target | Hỏi OPTIONS trên resource cụ thể |
| Quảng bá PATCH nhưng không định nghĩa media type hợp lệ | Client gặp 415 hoặc cập nhật sai | Document Content-Type, schema; cân nhắc Accept-Patch |

## 12. Bài tập tình huống: API quản lý báo cáo

Một hệ thống quản lý báo cáo định nghĩa:

- **/api/reports**: GET để liệt kê, POST để tạo yêu cầu tạo báo cáo.
- **/api/reports/{id}**: GET để xem trạng thái, DELETE để hủy nếu job chưa hoàn tất.
- **/api/reports/{id}/download**: GET tải báo cáo đã tạo.
- Tất cả resource cho phép OPTIONS, và framework hỗ trợ HEAD cho GET.
- Frontend hợp lệ chạy tại **https://portal.example.test**. CORS của frontend được cho phép GET/POST/DELETE theo từng route tương ứng và các request headers cần thiết; request thật vẫn yêu cầu quyền.

### Yêu cầu

1. Lập bảng **Allow** mong đợi cho từng URI. Giải thích vì sao **POST /api/reports/{id}** không hợp lệ theo thiết kế.
2. Viết phản hồi **405** cho **PUT /api/reports/123**, có Allow và problem details tùy chọn.
3. Viết request **OPTIONS preflight** khi frontend muốn gửi **DELETE /api/reports/123** với header Authorization.
4. Trả lời: Nếu preflight cho DELETE thành công nhưng tài khoản người dùng không có quyền hủy, request DELETE thật phải làm gì?
5. Nếu một gateway từ chối OPTIONS trước khi Spring Security xử lý CORS, người dùng thấy hiện tượng gì? Nêu bước kiểm tra cụ thể.
6. Giải thích vì sao cache kết quả preflight trong browser khác với cache HTTP của response OPTIONS.

### Gợi ý đáp án

**Bảng Allow theo mô hình đã giả định:**

| Target | Allow mong đợi |
|---|---|
| **/api/reports** | GET, HEAD, POST, OPTIONS |
| **/api/reports/123** | GET, HEAD, DELETE, OPTIONS |
| **/api/reports/123/download** | GET, HEAD, OPTIONS |

**PUT /api/reports/123** phải trả **405** khi router hiểu PUT nhưng item resource không hỗ trợ; Allow tương ứng là **GET, HEAD, DELETE, OPTIONS**. **POST /api/reports/{id}** không phù hợp với contract vì việc tạo báo cáo đã được thiết kế dưới collection **POST /api/reports**.

**Preflight DELETE** có dạng:

~~~http
OPTIONS /api/reports/123 HTTP/1.1
Host: api.example.test
Origin: https://portal.example.test
Access-Control-Request-Method: DELETE
Access-Control-Request-Headers: authorization

~~~

Nếu origin/method/header được chính sách CORS chấp nhận, server có thể trả:

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://portal.example.test
Access-Control-Allow-Methods: GET, HEAD, DELETE, OPTIONS
Access-Control-Allow-Headers: Authorization
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers

~~~

Request DELETE **thực tế** vẫn phải được kiểm tra danh tính và quyền trên báo cáo 123; có thể trả **403** khi người gọi không có quyền. Nếu job đã hoàn tất và không thể hủy vì trạng thái nghiệp vụ, API cần trả mã lỗi phù hợp với contract, chẳng hạn **409 Conflict**, cùng thông điệp rõ ràng; không dùng 405 cho xung đột trạng thái nếu DELETE vẫn là phương thức được endpoint hỗ trợ.

Nếu gateway chặn OPTIONS, trình duyệt có thể báo **lỗi preflight/CORS**, và controller DELETE không nhận request. Hãy xem Network tab, response headers/status của OPTIONS và cấu hình route/filter giữa browser, gateway và API.

**Access-Control-Max-Age** cho browser nhớ quyết định preflight theo cơ chế CORS. Nó không biến phản hồi OPTIONS thành phản hồi GET có thể được HTTP cache lưu và tái sử dụng tùy ý.

## 13. Checklist trước khi đưa API vào production

- [ ] Mỗi URI có danh sách phương thức được thiết kế rõ, phản ánh đúng resource và hành vi nghiệp vụ.
- [ ] OPTIONS không tạo side effect; phân biệt resource-target OPTIONS với **OPTIONS ***.
- [ ] Các route trả **405 có Allow** hợp lệ; phân biệt 405 với 501, 401, 403 và 404.
- [ ] Danh sách **Allow** khớp route thực tế, bao gồm HEAD/OPTIONS nếu thực sự được hỗ trợ.
- [ ] Nếu công bố PATCH, media type, contract và điều kiện cập nhật được mô tả.
- [ ] CORS policy có allowlist origin, methods và headers rõ; không nhầm Allow với Access-Control-Allow-Methods.
- [ ] Preflight không bị security filter/proxy chặn sai; request thật vẫn được authentication/authorization đầy đủ.
- [ ] Cấu hình credentials, CSRF và CORS được xem xét theo cơ chế đăng nhập thực tế.
- [ ] API không gửi body/Content-Length trong 204; 200 có body thì có schema/mime type hợp lệ.
- [ ] OpenAPI, route, gateway và contract test đồng nhất; có kiểm thử OPTIONS, 405, HEAD và preflight.
- [ ] Kiểm thử cả trình duyệt và HTTP client; xác minh CORS cache khác HTTP caching.
- [ ] Có logs/metrics theo request ID để phân biệt lỗi ở gateway, CORS filter, router và authorization.

**Điểm cần nhớ:** **OPTIONS** là cách hỏi khả năng giao tiếp; **Allow** mô tả phương thức hiện được hỗ trợ đối với resource và là header bắt buộc trong phản hồi **405**; còn **Access-Control-Allow-Methods** thuộc chính sách **CORS preflight** của trình duyệt. Ba khái niệm có liên quan nhưng phục vụ các câu hỏi khác nhau. Thiết kế REST API đúng đòi hỏi khớp **ngữ nghĩa HTTP, hợp đồng tài nguyên, bảo mật và hành vi thực tế của framework/gateway**.

### Tài liệu chuẩn để tra cứu

- **RFC 9110 — HTTP Semantics:** phần OPTIONS, Allow, 405 Method Not Allowed và 501 Not Implemented.
- **RFC 5789 — PATCH Method for HTTP:** phương thức PATCH và header Accept-Patch.
- **WHATWG Fetch Standard:** thuật toán CORS-preflight, các header Access-Control-* và CORS-preflight cache.
- **OpenAPI Specification 3.1:** mô tả path, operation, response và response headers.
