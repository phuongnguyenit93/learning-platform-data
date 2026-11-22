# Cho phép trình duyệt đọc Location, ETag và các header cần thiết trong Spring Data REST

Spring Data REST thường trả về những header HTTP có ý nghĩa khi client tạo hoặc cập nhật tài nguyên. Ví dụ, `Location` có thể cho biết URI của tài nguyên vừa tạo; `ETag` có thể mang phiên bản của tài nguyên để client kiểm soát cập nhật đồng thời. Tuy nhiên, khi frontend chạy ở origin khác API, trình duyệt áp dụng CORS và không cho JavaScript đọc tùy ý mọi response header.

Để frontend đọc được các header này, server cần khai báo chúng trong `Access-Control-Expose-Headers`. Với Spring Data REST, có thể cấu hình danh sách đó bằng `CorsRegistry.exposedHeaders(...)` trong `RepositoryRestConfigurer`. Cần phân biệt cấu hình expose response header với cấu hình cho phép origin, method và request header: mỗi phần giải quyết một vấn đề khác nhau.

## 1. CORS ảnh hưởng đến việc đọc response header như thế nào?

Origin được tạo bởi ba thành phần: scheme, host và port. Ví dụ, `https://app.example.com` và `https://api.example.com` là hai origin khác nhau; `http://localhost:3000` và `http://localhost:8080` cũng khác nhau vì port khác nhau.

Same-Origin Policy giới hạn cách một trang web đọc tài nguyên từ origin khác. CORS là cơ chế để server công bố những origin và thao tác cross-origin được phép. Trình duyệt kiểm tra các response header CORS trước khi cho mã JavaScript truy cập kết quả.

Có hai câu hỏi độc lập:

- Request có được phép gửi đến API từ origin hiện tại không? Server trả lời bằng các header như `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods` và `Access-Control-Allow-Headers`.
- Sau khi request được chấp nhận, JavaScript được phép đọc những response header nào? Server công bố danh sách bằng `Access-Control-Expose-Headers`.

Một request có thể thành công ở tầng HTTP nhưng JavaScript vẫn không đọc được một header vì header đó chưa được expose. CORS là cơ chế bảo vệ của trình duyệt; công cụ như curl hoặc Postman không áp dụng cùng quy tắc giới hạn đọc response header.

## 2. Vì sao Location và ETag cần được expose?

Theo quy tắc CORS, trình duyệt mặc định chỉ cho JavaScript đọc một nhóm response header an toàn, thường gồm:

- `Cache-Control`
- `Content-Language`
- `Content-Length`
- `Content-Type`
- `Expires`
- `Last-Modified`
- `Pragma`

Các header như `Location` và `ETag` không nằm trong nhóm mặc định này. Nếu API trả chúng nhưng không expose, đoạn mã `response.headers.get(...)` trong frontend có thể nhận `null`.

### Location

Khi client tạo tài nguyên bằng POST, API thường trả về `Location` để chỉ URI của tài nguyên mới. Client có thể đọc URI này để điều hướng đến trang chi tiết hoặc thực hiện request tiếp theo.

Ví dụ response:

    HTTP/1.1 201 Created
    Location: https://api.example.com/api/orders/42
    Content-Type: application/hal+json

Header `Location` phải thực sự có trong response. CORS expose chỉ cho phép JavaScript đọc giá trị đã được server gửi; nó không tự tạo Location và không thay đổi status code.

### ETag

`ETag` là validator đại diện cho một phiên bản của tài nguyên. Client có thể lưu giá trị này và gửi lại trong request sau để kiểm tra cập nhật đồng thời, thường thông qua `If-Match`.

Ví dụ response:

    HTTP/1.1 200 OK
    ETag: "7"

Khi cập nhật, client có thể gửi:

    PUT /api/orders/42
    If-Match: "7"
    Content-Type: application/json

    {
      "description": "Updated order"
    }

Nếu phiên bản tài nguyên đã thay đổi, server có thể từ chối cập nhật theo cơ chế optimistic locking, thường bằng status `412 Precondition Failed` hoặc phản hồi xung đột theo cách ứng dụng cấu hình. ETag phải được server tạo và kiểm tra đúng cách; chỉ expose header không tự bật optimistic locking.

Trong Spring Data REST, cơ chế ETag có thể phụ thuộc mapping và cấu hình persistence, chẳng hạn thuộc tính phiên bản `@Version`. Hãy kiểm tra response thật của endpoint để xác nhận ETag được phát hành.

## 3. Cấu hình CORS cho Spring Data REST

Spring Data REST cung cấp `RepositoryRestConfigurer` để tùy chỉnh cấu hình REST repository. Có thể khai báo origin được phép, method, request header và response header trong cùng một `CorsRegistry`.

Ví dụ Spring Boot 3:

    import org.springframework.context.annotation.Configuration;
    import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
    import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
    import org.springframework.web.servlet.config.annotation.CorsRegistry;

    @Configuration
    public class RepositoryCorsConfiguration
            implements RepositoryRestConfigurer {

        @Override
        public void configureRepositoryRestConfiguration(
                RepositoryRestConfiguration config,
                CorsRegistry cors) {

            cors.addMapping("/**")
                .allowedOrigins("https://app.example.com")
                .allowedMethods(
                    "GET", "POST", "PUT", "PATCH", "DELETE"
                )
                .allowedHeaders(
                    "Authorization",
                    "Content-Type",
                    "If-Match",
                    "If-None-Match"
                )
                .exposedHeaders(
                    "Location",
                    "ETag"
                )
                .allowCredentials(true)
                .maxAge(3600);
        }
    }

Ý nghĩa của từng phần:

- `addMapping("/**")`: áp dụng cấu hình cho các endpoint khớp path. Nếu API có base path riêng, có thể thu hẹp mapping theo path thực tế.
- `allowedOrigins(...)`: cho phép frontend ở origin đã chỉ định gọi API. Giá trị origin chỉ gồm scheme, host và port, không thêm path.
- `allowedMethods(...)`: khai báo các HTTP method mà cross-origin request được phép sử dụng.
- `allowedHeaders(...)`: khai báo request header mà browser được phép gửi, ví dụ `Authorization`, `Content-Type` và `If-Match`.
- `exposedHeaders(...)`: khai báo response header mà JavaScript được phép đọc, trong ví dụ là `Location` và `ETag`.
- `allowCredentials(true)`: cho phép browser gửi thông tin xác thực dạng credentials như cookie trong request cross-origin.
- `maxAge(3600)`: cho phép browser cache kết quả preflight trong tối đa 3.600 giây, tùy giới hạn của trình duyệt.

Nếu chỉ cần frontend đọc Location và ETag, hai header đó là nội dung cốt lõi của `exposedHeaders`. Những header khác chỉ nên thêm khi client thực sự cần đọc chúng, chẳng hạn `X-Request-Id` để đối chiếu log.

Không đăng ký nhiều cấu hình CORS chồng lấn cho cùng endpoint nếu chúng tạo ra các giá trị `Access-Control-Allow-Origin` hoặc expose header mâu thuẫn. Hãy đặt chính sách ở cấu hình phù hợp với đường đi request của ứng dụng.

## 4. Phân biệt allowedHeaders và exposedHeaders

Đây là điểm dễ nhầm khi cấu hình CORS:

| Cấu hình | Áp dụng cho | Ví dụ | Mục đích |
|---|---|---|---|
| `allowedHeaders` | Request gửi từ browser đến server | `Authorization`, `If-Match` | Cho phép client gửi header |
| `exposedHeaders` | Response từ server về browser | `Location`, `ETag` | Cho phép JavaScript đọc header |

Ví dụ, frontend muốn dùng ETag trong quy trình cập nhật:

1. GET tài nguyên và đọc response header `ETag`. Server cần expose `ETag`.
2. Lưu ETag ở frontend.
3. Gửi PUT hoặc PATCH với request header `If-Match`. Server cần cho phép request header `If-Match` qua `allowedHeaders`.
4. Server so sánh phiên bản và xử lý cập nhật.
5. Nếu response mới có ETag, frontend lại cần được expose header đó để đọc phiên bản tiếp theo.

Chỉ thêm `ETag` vào `exposedHeaders` sẽ không cho phép browser gửi `If-Match`. Ngược lại, chỉ thêm `If-Match` vào `allowedHeaders` cũng không làm cho JavaScript đọc được response header `ETag`.

## 5. Sử dụng header trong frontend

Ví dụ dùng Fetch API để tạo một đơn hàng và đọc URI của tài nguyên mới:

    const response = await fetch(
      "https://api.example.com/api/orders",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          description: "New order"
        })
      }
    );

    if (!response.ok) {
      throw new Error("Create order failed: " + response.status);
    }

    const location = response.headers.get("Location");
    const etag = response.headers.get("ETag");

    console.log("Created resource:", location);
    console.log("Resource version:", etag);

Nếu server trả hai header và CORS expose đúng, frontend có thể đọc chúng. Nếu giá trị là `null`, cần kiểm tra response thực tế và chính sách CORS trước khi kết luận server không tạo header.

Ví dụ gửi ETag trong request cập nhật:

    const response = await fetch(
      "https://api.example.com/api/orders/42",
      {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          "If-Match": savedEtag
        },
        body: JSON.stringify({
          description: "Updated order"
        })
      }
    );

    if (response.status === 412) {
      throw new Error("The order has changed; reload before editing.");
    }

    if (!response.ok) {
      throw new Error("Update failed: " + response.status);
    }

    const nextEtag = response.headers.get("ETag");

Request có header `If-Match` thường làm browser gửi preflight vì đây không phải request header CORS-safelisted. Server phải cho phép header đó trong `allowedHeaders`. Phần expose response header vẫn được cấu hình riêng.

## 6. Credentials, wildcard và origin cụ thể

Khi frontend gửi cookie cross-origin, Fetch API cần dùng:

    fetch(url, {
      credentials: "include"
    });

Server phải cho phép credentials và trả về origin cụ thể, ví dụ:

    Access-Control-Allow-Origin: https://app.example.com
    Access-Control-Allow-Credentials: true
    Access-Control-Expose-Headers: Location, ETag

Không thể kết hợp `Access-Control-Allow-Credentials: true` với wildcard origin `*` theo cách cho phép browser chấp nhận credentialed response. Spring cũng kiểm tra ràng buộc này khi dùng `allowedOrigins("*")` cùng `allowCredentials(true)`.

Với credentialed request, không dùng `Access-Control-Expose-Headers: *` để thay cho danh sách header cụ thể. Khi request có credentials, dấu `*` không hoạt động như wildcard expose; browser hiểu nó như tên một header có ký tự dấu sao. Hãy liệt kê tường minh:

    .exposedHeaders("Location", "ETag")

Nếu chỉ dùng Bearer token trong request header `Authorization`, vẫn cần cho phép `Authorization` trong `allowedHeaders`. Việc có cần `allowCredentials(true)` hay không phụ thuộc cách ứng dụng truyền credentials; không bật tùy chọn này chỉ vì request có một header Authorization.

Chỉ cho phép những origin đáng tin cậy. Không phản chiếu tùy tiện giá trị Origin do client gửi và không mở toàn bộ origin khi API dùng cookie hoặc thông tin xác thực nhạy cảm.

## 7. Spring Security và preflight request

Nếu ứng dụng có Spring Security, CORS phải được xử lý trước khi security yêu cầu xác thực cho request thực tế. Browser có thể gửi preflight `OPTIONS` để hỏi server liệu origin, method và request header có được phép hay không. Preflight thường không mang cookie phiên như request chính.

Khi cấu hình security chain, bật hỗ trợ CORS phù hợp và bảo đảm chính sách CORS của security không mâu thuẫn với cấu hình Spring Data REST. Ví dụ cấu hình security có thể dùng:

    http.cors(Customizer.withDefaults());

Cách cung cấp `CorsConfigurationSource` hoặc tích hợp với MVC phụ thuộc kiến trúc security của ứng dụng. Tránh đăng ký hai chính sách độc lập có giá trị khác nhau cho cùng đường dẫn.

Nếu preflight nhận 401 hoặc 403, kiểm tra thứ tự xử lý CORS và security. Nếu preflight thành công nhưng JavaScript không đọc được ETag, kiểm tra `Access-Control-Expose-Headers`; hai lỗi này nằm ở hai giai đoạn khác nhau.

## 8. Kiểm tra CORS và response header

Có thể dùng DevTools của trình duyệt:

1. Mở tab Network và thực hiện request từ frontend.
2. Chọn request thực tế, kiểm tra status code và response headers.
3. Xác nhận server có trả `Location` hoặc `ETag` hay không.
4. Xác nhận response có `Access-Control-Allow-Origin` phù hợp.
5. Xác nhận response có `Access-Control-Expose-Headers` chứa tên header cần đọc.
6. Nếu xuất hiện request OPTIONS, kiểm tra preflight có cho phép method và request header mà browser yêu cầu không.

Có thể kiểm tra preflight bằng curl:

    curl -i -X OPTIONS \
      "https://api.example.com/api/orders" \
      -H "Origin: https://app.example.com" \
      -H "Access-Control-Request-Method: POST" \
      -H "Access-Control-Request-Headers: content-type,authorization"

Đối chiếu response với origin, method và request header mong đợi. Curl chỉ giúp xem HTTP response; nó không mô phỏng việc browser chặn JavaScript đọc header theo CORS.

Các dấu hiệu thường gặp:

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Network có Location nhưng JavaScript nhận null | Location chưa được expose | Thêm Location vào exposedHeaders |
| Network không có Location | Endpoint không phát hành Location hoặc request không tạo tài nguyên | Kiểm tra status và response của endpoint |
| Network có ETag nhưng JavaScript nhận null | ETag chưa được expose | Thêm ETag vào exposedHeaders |
| Preflight bị từ chối | Origin, method hoặc request header chưa được cho phép; security chặn OPTIONS | Kiểm tra allowedOrigins, allowedMethods, allowedHeaders và security |
| Đọc được ETag nhưng gửi If-Match bị chặn | Request header chưa được cho phép | Thêm If-Match vào allowedHeaders |
| Curl đọc được mọi header nhưng browser không đọc được | Curl không áp dụng chính sách CORS của browser | Kiểm tra response CORS và thử từ đúng frontend origin |

## 9. Checklist khi triển khai

Trước khi đưa cấu hình vào môi trường thật, xác nhận:

- Frontend origin được khai báo chính xác, gồm scheme và port nếu có.
- Chỉ các HTTP method mà client cần mới được cho phép.
- Request header như `Authorization`, `Content-Type` và `If-Match` đã được cho phép khi sử dụng.
- Response header `Location`, `ETag` và các header thực sự cần đọc đã được expose.
- Nếu dùng cookie cross-origin, frontend gửi credentials và server cho phép credentials với origin cụ thể.
- Spring Security xử lý preflight phù hợp và không ghi đè chính sách CORS.
- Endpoint thực sự phát hành Location hoặc ETag; expose không tạo ra header còn thiếu.
- Kiểm thử cả trường hợp preflight, request thành công và response JavaScript đọc được header.

CORS expose là bước nối giữa response HTTP của Spring Data REST và khả năng quan sát response của frontend. Khi cấu hình đúng cả quyền gửi request lẫn quyền đọc response, frontend có thể sử dụng Location để điều hướng đến tài nguyên mới và ETag để hỗ trợ kiểm soát cập nhật đồng thời.