# Ý nghĩa các nhóm mã trạng thái HTTP và cách lựa chọn phản hồi

Khi client gửi một HTTP request, server trả về **status code** gồm ba chữ số để thông báo kết quả xử lý ở mức giao thức. Chọn đúng status giúp trình duyệt, ứng dụng di động, API client, bộ nhớ đệm (cache), proxy và hệ thống giám sát hiểu được điều gì đã xảy ra, kể cả khi không đọc nội dung JSON.

Ví dụ, cùng một thông điệp “không tìm thấy đơn hàng”, phản hồi `404 Not Found` diễn đạt đúng hơn `200 OK` kèm `{"success":false}`. Status phản ánh kết quả của request; body cung cấp dữ liệu hoặc chi tiết để người gọi hành động. Hai phần phải nhất quán.

## 1. Năm nhóm trạng thái HTTP

| Nhóm | Ý nghĩa | Khi nào thường gặp |
| --- | --- | --- |
| `1xx` — Informational | Thông tin tạm thời; chưa phải kết quả cuối cùng. | `100 Continue`, `101 Switching Protocols`, `103 Early Hints`. |
| `2xx` — Successful | Server đã xử lý hoặc chấp nhận request theo ý nghĩa của mã cụ thể. | Đọc dữ liệu, tạo, cập nhật, xóa, tiếp nhận tác vụ bất đồng bộ. |
| `3xx` — Redirection | Cần dùng vị trí/biểu diễn khác hoặc kết quả điều kiện cache. | Chuyển URL, đổi phương thức sau POST, `304 Not Modified`. |
| `4xx` — Client Error | Request không thể được thực hiện do cú pháp, xác thực, quyền, tài nguyên hoặc điều kiện phía request. | JSON sai, chưa đăng nhập, không có quyền, tài nguyên vắng mặt, xung đột dữ liệu. |
| `5xx` — Server Error | Server/gateway không thể hoàn tất một request hợp lệ do lỗi hoặc tình trạng dịch vụ. | Lỗi nội bộ, quá tải, lỗi upstream, timeout gateway. |

**Hai điểm cần nhớ:** `202 Accepted` mới chỉ có nghĩa là *đã tiếp nhận*, chưa chắc công việc đã hoàn thành. `304 Not Modified` thuộc nhóm 3xx nhưng là phản hồi cho kiểm tra cache, không phải lỗi và không yêu cầu client chuyển sang URL mới.

## 2. Những mã cần hiểu và dùng đúng

### 2.1. Thành công: 2xx

| Mã | Ý nghĩa | Ví dụ lựa chọn |
| --- | --- | --- |
| `200 OK` | Request hoàn tất, thường trả representation trong body. | `GET /api/orders/7` tìm thấy đơn; `GET /api/orders` trả `[]` khi danh sách rỗng. |
| `201 Created` | Request đã tạo được tài nguyên. | `POST /api/orders` tạo đơn số 7; trả `Location: /api/orders/7` và có thể trả body của đơn mới. |
| `202 Accepted` | Đã chấp nhận để xử lý tiếp, có thể thành công hoặc thất bại sau đó. | Nhận yêu cầu xuất báo cáo chạy nền; cung cấp URL kiểm tra trạng thái job nếu có. |
| `204 No Content` | Xử lý thành công, không có response body. | `DELETE /api/orders/7` đã xóa; `PUT/PATCH` thành công nhưng không trả representation. |
| `206 Partial Content` | Trả một phần representation theo range request. | Tải một đoạn file với `Range` và `Content-Range` phù hợp. |

- **GET** thông thường trả `200` với dữ liệu. Danh sách tồn tại nhưng có 0 phần tử vẫn là `200` với `[]`; chỉ dùng `404` nếu *tài nguyên được yêu cầu* không tồn tại.
- **POST tạo tài nguyên** thường dùng `201`; `Location` nên trỏ đến tài nguyên vừa tạo. Nếu endpoint chỉ nhận công việc vào hàng đợi, thường dùng `202`.
- **PUT/PATCH** cập nhật thành công thường dùng `200` nếu trả dữ liệu mới, hoặc `204` nếu không có body. `PUT` có thể dùng `201` khi tạo mới tại URI đích.
- **DELETE** thành công có thể dùng `204` hoặc `200` nếu trả kết quả; xử lý xóa nền có thể dùng `202`. Với tài nguyên đã vắng mặt, `404` hay `204` cho lần gọi lặp đều có thể được thiết kế và công bố nhất quán. *Idempotent* nghĩa là hiệu ứng sau nhiều request giống hiệu ứng sau một request, **không** buộc mọi lần có cùng status.

Không gửi JSON như `{}`, `null` hay thông báo thành công trong body của `204`; nếu cần body, hãy chọn mã cho phép body, thường là `200`.

### 2.2. Chuyển hướng và cache: 3xx

| Mã | Cách hiểu và lưu ý |
| --- | --- |
| `301 Moved Permanently` | URL đã chuyển lâu dài; một số client có thể đổi `POST` thành `GET` khi đi theo chuyển hướng. |
| `302 Found` | Chuyển hướng tạm thời; với `POST`, client truyền thống cũng có thể đổi sang `GET`. |
| `303 See Other` | Sau một action như `POST`, hướng client đi `GET` một tài nguyên khác, ví dụ trang/kết quả vừa tạo. |
| `307 Temporary Redirect` | Chuyển tạm thời và **giữ nguyên phương thức cùng body** khi client đi theo. |
| `308 Permanent Redirect` | Chuyển lâu dài và **giữ nguyên phương thức cùng body** khi client đi theo. |
| `304 Not Modified` | Điều kiện cache của `GET/HEAD` cho thấy có thể tái sử dụng bản đã lưu; không có response body. |

Một API thay đổi URL của endpoint nhận `POST` mà cần giữ nguyên phương thức nên cân nhắc `307` hoặc `308`. Khi muốn trình duyệt chuyển từ kết quả của POST sang một trang GET, `303` thể hiện rõ ý định hơn `302`. Với `304`, phải có cơ chế request có điều kiện như `If-None-Match`/`ETag` hoặc `If-Modified-Since`; không dùng mã này cho “dữ liệu rỗng”.

### 2.3. Request chưa thể đáp ứng: 4xx

| Mã | Chọn khi | Tránh nhầm với |
| --- | --- | --- |
| `400 Bad Request` | Request sai cấu trúc/cú pháp, JSON không parse được, tham số không hợp lệ theo quy ước API. | `422` cho nội dung parse được nhưng vi phạm quy tắc ngữ nghĩa. |
| `401 Unauthorized` | Thiếu hoặc sai thông tin xác thực; client cần xác thực hợp lệ. | `403` khi đã xác thực nhưng bị từ chối quyền. |
| `403 Forbidden` | Server hiểu request nhưng từ chối, thường vì thiếu quyền. | `401` nếu cần đăng nhập/chứng thực lại. |
| `404 Not Found` | Không tìm thấy resource theo URI hoặc cố ý không tiết lộ sự tồn tại. | `200 []` cho một collection hợp lệ nhưng rỗng. |
| `405 Method Not Allowed` | URI có xử lý nhưng không hỗ trợ phương thức đang gọi. | `404`; phản hồi `405` phải có header `Allow` liệt kê phương thức được hỗ trợ. |
| `406 Not Acceptable` | Không có representation đáp ứng điều kiện `Accept` của client. | `415` liên quan `Content-Type` của request. |
| `408 Request Timeout` | Server không nhận đầy đủ request trong thời gian chờ. | `504` là gateway chờ upstream quá lâu. |
| `409 Conflict` | Thao tác xung đột với **trạng thái hiện tại của tài nguyên**. | `422` cho dữ liệu vi phạm quy tắc độc lập với trạng thái; `412` cho điều kiện HTTP thất bại. |
| `410 Gone` | Biết chắc resource trước đây tồn tại nhưng đã bị xóa và tình trạng vắng mặt được coi là lâu dài. | `404` nếu không biết hoặc không muốn nói resource đã từng tồn tại. |
| `412 Precondition Failed` | Điều kiện như `If-Match`/`If-Unmodified-Since` không đúng. | `409` cho xung đột nghiệp vụ không dựa trên header điều kiện HTTP. |
| `413 Content Too Large` | Payload request vượt giới hạn chấp nhận. | `415` khi kiểu media không được hỗ trợ. |
| `415 Unsupported Media Type` | Server không xử lý được kiểu media/body được gửi. | `406` khi client không chấp nhận kiểu phản hồi. |
| `422 Unprocessable Content` | Content type và cú pháp đã hiểu, nhưng nội dung có lỗi ngữ nghĩa nên không thể xử lý. | `400` khi JSON sai cú pháp; `409` khi xung đột trạng thái. |
| `428 Precondition Required` | Server yêu cầu client gửi điều kiện như `If-Match` để tránh ghi đè mất cập nhật. | `412` khi client **đã gửi** điều kiện nhưng điều kiện sai. |
| `429 Too Many Requests` | Client vượt ngưỡng request/rate limit. | `503` khi dịch vụ quá tải hoặc tạm ngừng ở phía server. |

Phân biệt ba tình huống dễ nhầm:

1. Body `{"quantity":-2}` là JSON hợp lệ nhưng sai quy tắc số lượng phải dương: có thể trả `422` (hoặc `400` nếu API thống nhất dùng 400 cho lỗi validation). Cần chọn một quy ước và dùng nhất quán.
2. Hai request cùng tạo resource với mã nghiệp vụ đã tồn tại: `409 Conflict` có thể diễn đạt xung đột unique key/trạng thái hiện tại. Nếu muốn dùng `422` cho trường hợp này, cần giải thích rõ hợp đồng API; đừng tùy tiện thay đổi giữa các endpoint.
3. Client sửa resource với `If-Match: "v3"`, nhưng ETag hiện tại là `"v4"`: `412 Precondition Failed`. Nếu endpoint bắt buộc điều kiện mà client không gửi, cân nhắc `428 Precondition Required`.

**401 và 403:** `401` nghĩa là request chưa có xác thực hợp lệ, dù tên tiếng Anh là “Unauthorized”; phản hồi `401` dùng cơ chế challenge phù hợp qua `WWW-Authenticate`. `403` nghĩa là từ chối thực hiện dù đã hiểu request, thường vì thiếu quyền. Đối với tài nguyên nhạy cảm, server có thể trả `404` để không tiết lộ sự tồn tại, tùy chính sách bảo mật.

### 2.4. Server/gateway thất bại: 5xx

| Mã | Chọn khi | Ví dụ |
| --- | --- | --- |
| `500 Internal Server Error` | Có lỗi nội bộ bất ngờ khiến server không hoàn thành request. | NullPointerException không được xử lý, lỗi trạng thái nội bộ ngoài dự kiến. |
| `501 Not Implemented` | Server không hỗ trợ chức năng cần thiết để đáp ứng request, ví dụ không nhận biết một HTTP method. | Khác `405`: method được server hiểu nhưng bị cấm với URI cụ thể. |
| `502 Bad Gateway` | Gateway/proxy nhận phản hồi không hợp lệ từ upstream. | Reverse proxy gặp upstream trả dữ liệu lỗi. |
| `503 Service Unavailable` | Dịch vụ tạm thời không sẵn sàng vì quá tải/bảo trì. | Có thể bổ sung `Retry-After` để hướng dẫn thử lại. |
| `504 Gateway Timeout` | Gateway/proxy không nhận kịp phản hồi từ upstream. | API gateway hết thời gian chờ backend. |

Đừng trả `500` cho một điều kiện nghiệp vụ đã dự kiến như “hết hàng”, “không đủ quyền”, “đơn đã hủy”. Chúng thường cần `4xx` thích hợp. Với lỗi `5xx`, ghi log/correlation ID phục vụ điều tra nhưng không lộ stack trace, bí mật cấu hình hoặc nội dung nhạy cảm trong body công khai. Lỗi mất kết nối mạng mà client không nhận được HTTP response thì **không có status code HTTP** để đọc, dù client có thể tự báo lỗi mạng.

## 3. Quy trình chọn status cho một endpoint

Hãy đi theo kết quả thật của request thay vì tự động trả `200`:

1. **Request có được hiểu và hợp lệ ở tầng HTTP/API không?** JSON lỗi cú pháp → `400`; `Content-Type` không hỗ trợ → `415`; thương lượng `Accept` thất bại → `406`.
2. **Đã xác thực và có quyền chưa?** Thiếu/sai credential → `401`; bị từ chối theo quyền/chính sách → `403` (có thể che giấu bằng `404` theo chính sách).
3. **Resource và điều kiện thực thi thế nào?** Không tồn tại → `404`; method không hỗ trợ tại URI → `405`; xung đột trạng thái → `409`; `If-Match` sai → `412`; validation nội dung đã parse được thất bại → `422` hoặc `400` theo hợp đồng API.
4. **Server/gateway có gặp sự cố không?** Lỗi bất ngờ → `500`; tạm thời không sẵn sàng → `503`; lỗi gateway/upstream → `502` hoặc `504`.
5. **Nếu thành công, kết quả là gì?** Có representation → thường `200`; vừa tạo resource → `201`; mới tiếp nhận xử lý nền → `202`; thành công không trả body → `204`; trả đoạn byte → `206`.
6. **Nếu đang xử lý cache/chuyển hướng**, chọn mã 3xx có ngữ nghĩa đúng (`304`, `303`, `307`, `308`...), và đặt header tương ứng.

### Bảng quyết định theo tình huống API

| Request/tình huống | Status gợi ý | Lý do |
| --- | --- | --- |
| `GET /products/8` tìm thấy | `200` | Trả representation của product. |
| `GET /products?category=x` không có phần tử | `200` + `[]` | Collection vẫn hợp lệ, kết quả lọc rỗng. |
| `GET /products/999` không tồn tại | `404` | Resource đơn không tìm thấy. |
| `POST /products` tạo product mới ngay | `201` + `Location` | Có resource mới có URI riêng. |
| `POST /exports` đưa job vào queue | `202` | Công việc chưa hoàn tất, nên trả link theo dõi. |
| `PUT /products/8` cập nhật và trả object | `200` | Có response body. |
| `PATCH /products/8` cập nhật, không trả object | `204` | Không có response body. |
| `DELETE /products/8` thành công, không trả object | `204` | Xóa xong, không cần body. |
| Request JSON hỏng cú pháp | `400` | Không parse được request. |
| Request JSON hợp lệ nhưng số lượng âm | `422` hoặc `400` theo chuẩn API | Sai ngữ nghĩa/validation. |
| Chưa đăng nhập vào endpoint yêu cầu đăng nhập | `401` | Thiếu authentication hợp lệ. |
| Đã đăng nhập nhưng thiếu quyền quản trị | `403` | Từ chối authorization. |
| Đặt hàng trùng mã duy nhất đang có | `409` | Xung đột trạng thái hiện tại. |
| Cập nhật với ETag cũ trong `If-Match` | `412` | HTTP precondition không đạt. |
| Gửi `Content-Type: text/plain` tới endpoint chỉ nhận JSON | `415` | Không hỗ trợ kiểu media request. |
| Bị giới hạn tần suất gọi API | `429` | Cần giảm tốc hoặc chờ theo chính sách. |
| Dịch vụ tạm ngừng để bảo trì | `503` | Lỗi tạm thời ở phía server. |

Không có bảng nào thay thế được hợp đồng của endpoint: cùng một nghiệp vụ có thể trả các mã khác nhau tùy thao tác thực sự đã hoàn thành hay chỉ được tiếp nhận. Hãy mô tả các status có thể xảy ra trong API documentation và kiểm thử chúng.

## 4. Status, header và body phải đồng bộ

Một HTTP response có status cùng các header; body là tùy chọn theo ngữ nghĩa status. Những kết hợp quan trọng:

| Status | Header/body cần lưu ý |
| --- | --- |
| `201` | `Location` thường cho biết URI của resource mới; body có thể trả object mới. |
| `202` | Body/link nên cho biết cách tra trạng thái tác vụ; không hứa tác vụ chắc chắn thành công. |
| `204` | **Không có body**. |
| `206` | Header range, nhất là `Content-Range`, phải phù hợp phần nội dung thực tế. |
| `301/302/303/307/308` | `Location` cho biết nơi chuyển hướng; lựa chọn mã quyết định hành vi method. |
| `304` | **Không có body**; dùng cùng điều kiện cache và metadata đại diện phù hợp. |
| `401` | `WWW-Authenticate` diễn đạt challenge xác thực theo giao thức. |
| `405` | Header `Allow` liệt kê các method hỗ trợ tại resource. |
| `429/503` | Có thể gửi `Retry-After` để thông báo thời điểm hoặc số giây nên chờ. |

Đối với lỗi API, có thể dùng **Problem Details for HTTP APIs** với media type `application/problem+json`. Ví dụ một lỗi validation (minh họa, không phải chuỗi thông báo mặc định của Spring):

```http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Dữ liệu đơn hàng không hợp lệ",
  "status": 422,
  "detail": "sku phải có giá trị"
}
```

`status` trong JSON chỉ là thông tin bổ sung, phải khớp status thực tế của response. Client nên kiểm tra HTTP status trước rồi mới đọc body. Với production API, có thể thêm mã lỗi ứng dụng, `instance` và correlation ID nhất quán, đồng thời tránh lộ dữ liệu nhạy cảm.

## 5. Ví dụ Spring Boot 3.x (Java 17+): chọn status bằng `ResponseEntity`

Ví dụ dưới đây dùng **Spring MVC** và dependency `spring-boot-starter-web`. Dữ liệu giữ trong RAM để tập trung vào ý nghĩa HTTP; chạy lại ứng dụng sẽ mất các đơn đã tạo. Hai file cùng package `demo.web`, trong một Spring Boot project đã cấu hình Gradle/Maven bình thường.

File `src/main/java/demo/web/WebRuntimeApplication.java`:

```java
package demo.web;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebRuntimeApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebRuntimeApplication.class, args);
    }
}
```

File `src/main/java/demo/web/OrderController.java`:

```java
package demo.web;

import java.net.URI;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@RestController
@RequestMapping("/api/orders")
public class OrderController {
    private final Map<Long, Order> orders = new ConcurrentHashMap<>();
    private final AtomicLong nextId = new AtomicLong(1);

    public record NewOrder(String sku) {}
    public record Order(long id, String sku) {}

    @GetMapping("/{id}")
    public ResponseEntity<Order> get(@PathVariable long id) {
        Order order = orders.get(id);
        return order == null
                ? ResponseEntity.notFound().build()
                : ResponseEntity.ok(order);
    }

    @PostMapping
    public ResponseEntity<?> create(@RequestBody NewOrder request) {
        if (request == null || request.sku() == null || request.sku().isBlank()) {
            ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                    HttpStatus.UNPROCESSABLE_ENTITY, "sku phải có giá trị");
            problem.setTitle("Dữ liệu đơn hàng không hợp lệ");
            return ResponseEntity.unprocessableEntity().body(problem);
        }

        long id = nextId.getAndIncrement();
        Order order = new Order(id, request.sku());
        orders.put(id, order);
        URI location = ServletUriComponentsBuilder.fromCurrentRequest()
                .path("/{id}").buildAndExpand(id).toUri();
        return ResponseEntity.created(location).body(order);
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable long id) {
        return orders.remove(id) == null
                ? ResponseEntity.notFound().build()
                : ResponseEntity.noContent().build();
    }
}
```

Khởi chạy từ thư mục dự án Spring Boot: `./gradlew bootRun` trên Linux/macOS hoặc `gradlew.bat bootRun` trên Windows (với Gradle wrapper của dự án). Thử bằng terminal có `curl`; các lệnh dưới đây dùng cú pháp Bash:

```bash
# Lần tạo đầu tiên sau khi khởi động ứng dụng
curl -i -X POST http://localhost:8080/api/orders \
  -H 'Content-Type: application/json' \
  -d '{"sku":"BOOK-1"}'

# Tìm đơn vừa tạo
curl -i http://localhost:8080/api/orders/1

# Dữ liệu có cú pháp đúng nhưng sai ngữ nghĩa
curl -i -X POST http://localhost:8080/api/orders \
  -H 'Content-Type: application/json' \
  -d '{"sku":"  "}'

# Xóa đơn; sau đó GET cùng URI sẽ không còn dữ liệu
curl -i -X DELETE http://localhost:8080/api/orders/1
curl -i http://localhost:8080/api/orders/1
```

Các **status kỳ vọng**, với ứng dụng mới khởi động và request đầu tiên tạo đơn: `201` cùng `Location` cho POST hợp lệ; `200` kèm JSON đơn cho GET; `422` kèm Problem Details cho POST có `sku` toàn khoảng trắng; `204` không có body cho DELETE thành công; `404` cho GET sau khi xóa. Header phụ, văn bản reason phrase và cách trình bày lỗi do server/framework quyết định nên không cần giống hệt từng byte. JSON bị hỏng cú pháp sẽ bị tầng Spring MVC từ chối trước khi vào logic validation và thường nhận `400`.

Trong WebFlux, vẫn áp dụng **cùng ý nghĩa status HTTP**; code có thể dùng `ResponseEntity` trong annotated controller hoặc `ServerResponse` với functional endpoint. Việc chọn status không phụ thuộc bạn đang dùng Servlet hay reactive runtime.

## 6. Lỗi lựa chọn status thường gặp

- **Luôn trả `200`**, kể cả khi body ghi `"error"`: client, proxy và monitoring có thể hiểu sai kết quả. Nên dùng mã phản ánh outcome thực.
- **Trả `201` trước khi resource được tạo**: nếu mới enqueue xử lý, dùng `202`; không khẳng định đã tạo xong.
- **Dùng `204` rồi gửi JSON**: trái ngữ nghĩa no-content; cần chọn `200` nếu muốn body.
- **Dùng `401` cho mọi trường hợp thiếu quyền**: phân biệt authentication (401) và authorization/forbidden (403).
- **Dùng `404` cho list rỗng**: filter thành công và không có phần tử thường là `200 []`.
- **Dùng `409` cho mọi lỗi input**: phân biệt xung đột trạng thái (409), precondition HTTP thất bại (412) và dữ liệu sai ngữ nghĩa (422/400).
- **Dùng `500` cho lỗi người dùng có thể sửa**: map validation, authentication, permission và business conflict về 4xx tương ứng.
- **Dùng `302` khi cần giữ nguyên method của POST/PUT qua redirect**: chọn `307`/`308` nếu yêu cầu giữ method và body.
- **Đồng nhất tính idempotent với status bất biến**: PUT/DELETE có thể thay đổi status giữa các lần gọi nhưng vẫn idempotent về hiệu ứng.
- **Quên header bắt buộc hoặc hữu ích**: đặc biệt `Allow` cho 405, challenge `WWW-Authenticate` cho 401, `Location` cho 201/redirect, thông tin retry khi cần.

## 7. Checklist tự kiểm tra cho một API endpoint

1. Request thực sự đã thành công, được tiếp nhận hay bị từ chối? Status nói đúng **thời điểm và kết quả** này chưa?
2. Resource mới, resource vắng mặt, collection rỗng, conflict nghiệp vụ và validation đã được phân biệt rõ chưa?
3. Đã tách authentication khỏi authorization và lỗi client khỏi lỗi server chưa?
4. Các trường hợp có/không có response body có phù hợp với `200/201/202/204/304` chưa?
5. Đã gửi header cần thiết (`Location`, `Allow`, `WWW-Authenticate`, `ETag`/`Retry-After` khi thích hợp) chưa?
6. API documentation và automated tests có xác nhận cả happy path lẫn 4xx/5xx dự kiến, body lỗi và header liên quan chưa?

**Quy tắc thực hành:** Chọn HTTP status dựa trên **ngữ nghĩa của kết quả request**, sau đó thiết kế body và header để giải thích kết quả đó một cách nhất quán. Nhóm 2xx ghi nhận thành công/chấp nhận, 3xx phục vụ điều hướng/cache, 4xx diễn đạt request không thể đáp ứng theo điều kiện client, và 5xx biểu thị dịch vụ/gateway không thể hoàn thành.
