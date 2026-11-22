# HTTP 405 Method Not Allowed, header Allow và phương thức không được hỗ trợ

## 1. Bối cảnh: phương thức HTTP là một phần của hợp đồng REST API

Trong REST API, **URI** xác định tài nguyên, còn **phương thức HTTP (HTTP method)** diễn tả thao tác mà client muốn thực hiện trên tài nguyên đó. Cùng một URI có thể hỗ trợ một số phương thức nhưng không hỗ trợ những phương thức khác.

Ví dụ hệ thống đơn hàng cung cấp:

| Yêu cầu | Ý nghĩa dự kiến | API có hỗ trợ? |
| --- | --- | --- |
| `GET /api/orders` | Lấy danh sách đơn hàng | Có |
| `POST /api/orders` | Tạo đơn hàng | Có |
| `GET /api/orders/ord-001` | Xem một đơn hàng | Có |
| `DELETE /api/orders/ord-001` | Xóa đơn hàng | Không, nếu hợp đồng chỉ cho phép hủy bằng thao tác nghiệp vụ |
| `PUT /api/orders` | Thay thế toàn bộ collection | Không |

Nếu client gửi `PUT /api/orders` trong khi tài nguyên collection `/api/orders` có tồn tại nhưng **không cho phép PUT**, server nên phản hồi **405 Method Not Allowed** và thông báo những phương thức hiện được hỗ trợ bằng header **`Allow`**.

Bài này thuộc chương **Mã trạng thái** của module **INTEGRATION_API_REST**. Kiến thức về 405 nối trực tiếp với thiết kế resource/URI, ngữ nghĩa GET–POST–PUT–PATCH–DELETE, hợp đồng OpenAPI, xử lý lỗi, xác thực/phân quyền, cache, idempotency và kiểm thử API trên Java/Spring hoặc nền tảng tương đương.

### Kết quả học tập

Sau bài học, bạn có thể:

1. Giải thích ý nghĩa của mã **405** và vai trò bắt buộc của header **`Allow`**.
2. Phân biệt **405** với **404, 401, 403, 415, 501** và các lỗi CORS thường bị nhầm.
3. Thiết kế danh sách phương thức được phép theo **từng resource**, tránh mở nhầm những thao tác phá hủy hoặc trái ngữ nghĩa.
4. Triển khai và tùy biến phản hồi 405 trong **Spring MVC** mà vẫn giữ đúng header `Allow`.
5. Dùng `curl` và MockMvc để kiểm tra status, header, body, xác thực và các tình huống khác nhau giữa các route.

## 2. 405 có nghĩa là gì?

**405 Method Not Allowed** có nghĩa: máy chủ đã nhận biết phương thức HTTP được gửi đến, nhưng **resource đích không hỗ trợ phương thức ấy**.

Phân tích câu trả lời sau:

```http
PUT /api/orders HTTP/1.1
Host: api.example.test
Content-Type: application/json

{"id":"ord-001","status":"CONFIRMED"}
```

```http
HTTP/1.1 405 Method Not Allowed
Allow: GET, HEAD, POST, OPTIONS
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Method Not Allowed",
  "status": 405,
  "detail": "PUT is not supported on /api/orders",
  "instance": "/api/orders"
}
```

Phản hồi trên minh họa một endpoint có GET, POST, HEAD và OPTIONS. **Danh sách thực tế phải lấy từ những phương thức resource hiện hỗ trợ**, không được sao chép cố định từ ví dụ này.

Có ba thông tin cần đọc độc lập:

- **Status `405`**: phương thức của request không được phép với resource đích.
- **Header `Allow`**: những phương thức HTTP **đang được resource đó hỗ trợ**.
- **Body lỗi**: mô tả hữu ích cho người dùng API. Body có thể theo định dạng Problem Details (`application/problem+json`), nhưng **không thay thế header `Allow`**.

**Theo HTTP:** Origin server **MUST** tạo header `Allow` trong phản hồi **405**, chứa danh sách các phương thức hiện hỗ trợ ở resource đích. Các token phương thức trong danh sách được phân tách bằng dấu phẩy; thứ tự liệt kê không thể hiện thứ tự ưu tiên.

Header HTTP không phân biệt chữ hoa/chữ thường ở **tên header** (`Allow`, `allow`); nhưng **tên phương thức HTTP là token phân biệt chữ hoa/chữ thường**. Hợp đồng API thông thường dùng các token chuẩn `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `HEAD`, `OPTIONS`.

### 2.1. Điều kiện để trả 405

Ví dụ: route `/api/orders` tồn tại; controller xử lý GET và POST; request gửi PUT. Server nhận biết PUT nhưng endpoint đó không có thao tác PUT. Đây là trường hợp điển hình cho 405.

Ngược lại:

- Nếu **URI/tài nguyên không tồn tại** hoặc không có route phù hợp, thường dùng **404**.
- Nếu **server không nhận biết hoặc không có khả năng hỗ trợ phương thức đó cho bất kỳ resource nào**, dùng **501 Not Implemented**.
- Nếu **phương thức được hỗ trợ nhưng client không đủ quyền thực hiện**, xem xét **401** hoặc **403** tùy trạng thái xác thực.

Thứ tự xử lý authentication, gateway, router và nội dung request có thể khiến kết quả quan sát khác nhau. Không thể suy ra “chắc chắn phải 405” chỉ từ phương thức khi chưa biết request đã đến được resource đích hay chưa.

### 2.2. Không phải lỗi “server không hỗ trợ REST”

405 không có nghĩa server bị hỏng hay API không tương thích với REST. Nó là **phản hồi đúng hợp đồng** khi resource chủ động giới hạn thao tác.

Chẳng hạn:

- Danh sách đơn hàng cho `GET` và `POST`, không cho `DELETE` toàn bộ.
- Một hóa đơn đã phát hành chỉ hỗ trợ `GET`; không hỗ trợ sửa hoặc xóa tùy tiện.
- Resource `/users/{id}` có thể hỗ trợ `GET` và `PATCH`, nhưng không hỗ trợ `PUT` nếu API chỉ cho cập nhật một số trường có kiểm soát.

Không nên triển khai “chấp nhận mọi phương thức rồi trả 200” chỉ để tránh lỗi 405. Làm vậy che giấu sai hợp đồng và có thể biến API thành nơi thực hiện thao tác ngoài dự kiến.

## 3. Header Allow: ý nghĩa, định dạng và ranh giới

### 3.1. Cú pháp và ví dụ

Các phản hồi hợp lệ có thể như sau:

```http
HTTP/1.1 405 Method Not Allowed
Allow: GET, HEAD
```

```http
HTTP/1.1 405 Method Not Allowed
Allow: GET, HEAD, POST, OPTIONS
```

`Allow` là một **danh sách phương thức cho resource đích**. Khi dùng 405, server phải cung cấp header này; một phản hồi chỉ có JSON `{"allowedMethods":["GET","POST"]}` nhưng **không có `Allow`** là thiếu thông tin được chuẩn HTTP yêu cầu.

Theo HTTP, trường hợp đặc biệt `Allow:` với giá trị rỗng có thể biểu thị resource hiện không cho phép phương thức nào (chẳng hạn tạm vô hiệu hóa bởi cấu hình). Điều này khác với **quên gửi header**. Trong REST API thông thường, nên mô hình hóa rõ trạng thái khóa/tạm dừng và cân nhắc mã lỗi thích hợp cho tình huống nghiệp vụ thay vì tùy tiện trả 405 rỗng.

### 3.2. Danh sách phương thức có thể thay đổi

Ví dụ một resource cho phép đọc và cập nhật ở trạng thái `DRAFT`, nhưng sau khi được phát hành không còn cho sửa:

| Resource hoặc trạng thái | Thao tác theo hợp đồng | Gợi ý xử lý |
| --- | --- | --- |
| `/documents/42` ở `DRAFT` | `GET`, `PATCH` | Cho phép sửa nếu có quyền |
| `/documents/42` ở `PUBLISHED` | Có thể chỉ `GET` | Nếu method thật sự không còn được hỗ trợ trên resource này, `405` với `Allow` hiện hành có thể phù hợp |
| `/documents/42` nhưng người gọi không được sửa | `PATCH` tồn tại nhưng thiếu quyền | `403` hoặc `401`, tùy xác thực; không dùng 405 để diễn tả thiếu quyền |
| `/documents/42` có `PATCH` nhưng phiên bản tài liệu xung đột | `PATCH` hợp lệ, precondition không đạt | Xem xét `412 Precondition Failed` nếu dùng `If-Match`, hoặc `409 Conflict` theo ngữ cảnh |

**Phân biệt:** “Server không có thao tác PATCH cho resource” và “thao tác PATCH tồn tại nhưng trạng thái hiện tại không cho phép nghiệp vụ” không phải luôn cùng một tình huống. Nếu hợp đồng vẫn hỗ trợ PATCH nhưng thao tác bị từ chối vì quy tắc trạng thái, **409** có thể rõ nghĩa hơn **405**. Chính sách cần nhất quán, có tài liệu và được kiểm thử.

### 3.3. `Allow` không phải danh sách quyền của từng người dùng

`Allow` mô tả **phương thức được resource hỗ trợ**. Nó không tự chứng minh rằng người gọi đã được cấp phép thực thi tất cả những phương thức ấy.

Ví dụ:

- Một resource có thể hỗ trợ `DELETE`, nhưng chỉ quản trị viên được dùng. Người dùng đã đăng nhập nhưng không có quyền gửi `DELETE` có thể nhận **403**.
- Người gọi chưa xác thực có thể nhận **401** kèm `WWW-Authenticate` khi cần xác thực.
- Vì lý do bảo mật, API có thể chủ động trả 404 để không tiết lộ sự tồn tại của một resource thuộc người khác, theo chính sách đã thiết kế.

Không xây authorization bằng cách dựa vào client đọc `Allow`. **Server phải xác thực và phân quyền cho từng request**, dù UI có ẩn nút xóa hay không.

### 3.4. `Allow` có thể xuất hiện ngoài 405

Header `Allow` có thể được gửi ở những phản hồi khác, chẳng hạn phản hồi của một số request `OPTIONS`, để mô tả phương thức được hỗ trợ. Tuy nhiên, **yêu cầu phải có `Allow` là đặc biệt quan trọng với 405**.

Khi xây controller hoặc middleware lỗi tùy biến, tránh trả `405` rồi xóa hoặc bỏ qua header này.

## 4. Phân biệt 405 với các mã thường nhầm

| Mã | Ý nghĩa trong tình huống liên quan | Ví dụ với `/api/orders` |
| --- | --- | --- |
| **400 Bad Request** | Cú pháp request không hợp lệ hoặc dữ liệu request không thể diễn giải theo quy tắc | JSON sai cú pháp trên một POST được hỗ trợ |
| **401 Unauthorized** | Request thiếu xác thực hợp lệ; tên mã dễ gây nhầm nhưng dùng cho authentication | POST yêu cầu bearer token nhưng client không cung cấp token |
| **403 Forbidden** | Server hiểu request nhưng từ chối, thường do thiếu quyền | User đã đăng nhập nhưng không được xóa đơn hàng |
| **404 Not Found** | Không tìm thấy resource đích hoặc server không muốn tiết lộ sự tồn tại | GET một orderId không tồn tại |
| **405 Method Not Allowed** | Phương thức được nhận biết nhưng resource đích không hỗ trợ | PUT lên collection chỉ có GET/POST |
| **406 Not Acceptable** | Không cung cấp được biểu diễn nội dung phù hợp `Accept` theo cơ chế thương lượng | Client chỉ chấp nhận định dạng mà endpoint không thể trả |
| **409 Conflict** | Request hợp lệ nhưng xung đột với trạng thái hiện tại của resource | Hủy đơn đã giao xong trái quy tắc nghiệp vụ |
| **412 Precondition Failed** | Điều kiện request (`If-Match` hoặc tương đương) không được thỏa mãn | Sửa đơn bằng ETag cũ |
| **415 Unsupported Media Type** | Định dạng nội dung gửi lên không được endpoint hỗ trợ | POST chỉ nhận JSON nhưng gửi XML |
| **501 Not Implemented** | Server không hỗ trợ chức năng cần thiết để xử lý request; có thể là phương thức server không nhận biết/không hỗ trợ cho bất kỳ resource nào | Gửi phương thức mở rộng mà server không triển khai |

### 4.1. 405 hay 404?

Nếu client gửi `PUT /api/orders`, route `/api/orders` có GET và POST, **405** thường là đáp án đúng. Nếu client gửi `PUT /api/unknown-path` và **không tồn tại resource/route tương ứng**, phản hồi **404** thường phù hợp hơn.

Tuy nhiên, với `PUT /api/orders/does-not-exist`, việc server ưu tiên xử lý kiểm tra **method** hay xác định **resource thực** tùy định tuyến và hợp đồng. Không nên dạy quy tắc máy móc rằng “bất kỳ `PUT` sai nào cũng phải 405” hoặc “mọi ID không tồn tại luôn phải 404 trước”.

### 4.2. 405 hay 501?

**405**: server hiểu `PATCH`, nhưng `/api/orders` không cho PATCH.

**501**: server không có khả năng hỗ trợ phương thức mà nó nhận được đối với bất kỳ resource nào, chẳng hạn một extension method hoàn toàn chưa được triển khai.

Server hoặc gateway có thể chặn một phương thức sớm hơn ở tầng giao thức, policy hoặc security và trả mã khác. Vì vậy, khi kiểm thử cần kiểm tra mã trả về tại **đường đi thực tế** của request, bao gồm reverse proxy/API gateway.

### 4.3. 405 hay 403 khi xóa?

Giả sử `/api/orders/{id}` **không có thao tác DELETE** theo thiết kế, vì đơn hàng chỉ có thể được **hủy qua endpoint nghiệp vụ**. Khi gọi DELETE, 405 là lựa chọn tự nhiên.

Ngược lại, nếu `/api/orders/{id}` có DELETE cho quản trị viên, nhưng người dùng thường không được phép gọi, **403** phù hợp hơn sau khi xác thực. Việc trả 405 để thay cho mọi lỗi authorization làm client hiểu sai rằng method không tồn tại.

## 5. Thiết kế phương thức theo resource

Khi thiết kế REST API, hãy xác định **resource trước, method sau**:

| Resource | GET | POST | PUT | PATCH | DELETE |
| --- | --- | --- | --- | --- | --- |
| `/api/orders` | Danh sách | Tạo mới | Thường không dùng để thay toàn bộ danh sách | Thường không hỗ trợ | Thường không hỗ trợ |
| `/api/orders/{id}` | Xem chi tiết | Thường không hỗ trợ tạo lại cùng URI | Có thể hỗ trợ thay thế đầy đủ nếu nghiệp vụ cho phép | Có thể hỗ trợ cập nhật một phần | Có thể hỗ trợ nếu hợp đồng cho xóa |
| `/api/orders/{id}/cancellation` | Có thể lấy trạng thái yêu cầu hủy | Có thể tạo yêu cầu hủy | Phụ thuộc mô hình resource | Phụ thuộc mô hình resource | Thường không hỗ trợ |

Mỗi ô trong bảng là **lựa chọn thiết kế**, không phải khuôn bắt buộc cho mọi API. Cần xác định ranh giới thao tác dựa trên hành vi nghiệp vụ và ngữ nghĩa HTTP.

### 5.1. Nhắc lại ngữ nghĩa phương thức

- **GET:** lấy biểu diễn resource, an toàn (safe) theo ngữ nghĩa HTTP; không chủ ý gây thay đổi trạng thái nghiệp vụ.
- **HEAD:** tương tự GET ở ý nghĩa lấy metadata, nhưng phản hồi **không có body**. Nhiều framework tự hỗ trợ HEAD cho endpoint GET.
- **POST:** yêu cầu resource đích xử lý biểu diễn gửi lên theo quy tắc riêng; thường dùng tạo tài nguyên hoặc lệnh nghiệp vụ.
- **PUT:** tạo/thay thế trạng thái của resource tại URI đích theo ngữ nghĩa PUT; **idempotent** theo đặc tính giao thức.
- **PATCH:** yêu cầu áp dụng tập thay đổi; **không mặc định idempotent**, phụ thuộc định dạng patch và cách xử lý.
- **DELETE:** yêu cầu xóa liên kết của resource với URI đích; **idempotent** về tác động dự kiến theo ngữ nghĩa HTTP.
- **OPTIONS:** hỏi các tùy chọn giao tiếp với resource; có thể liên quan tới CORS preflight nhưng không đồng nhất.

Idempotent không có nghĩa **mọi lần request đều trả cùng mã trạng thái**: một DELETE đầu tiên có thể trả 204 và lần tiếp theo trả 404, miễn là tác động dự kiến khi lặp không làm thay đổi trạng thái vượt quá điều đã thực hiện.

### 5.2. Không sửa lỗi 405 bằng cách đổi method tùy tiện

Khi gặp 405, trước hết kiểm tra tài liệu API, phương thức và URI. Không tự động đổi `POST` thành `GET` hay đổi `PUT` thành `POST` nếu thao tác có side effect; cách đổi đó có thể làm thay đổi ý nghĩa, caching và idempotency.

Nếu client muốn **gửi lại POST tạo đơn** sau timeout, cần thiết kế idempotency rõ ràng (ví dụ `Idempotency-Key` được server thực thi). Việc chuyển sang PUT chỉ để “không bị trùng” không tự tạo idempotency nếu URI và xử lý phía server không đáp ứng ngữ nghĩa PUT.

## 6. OPTIONS, HEAD và CORS: ba nguồn nhầm lẫn

### 6.1. OPTIONS không phải lúc nào cũng là CORS preflight

Một yêu cầu OPTIONS thông thường:

```http
OPTIONS /api/orders HTTP/1.1
Host: api.example.test
```

Server có thể phản hồi:

```http
HTTP/1.1 204 No Content
Allow: GET, HEAD, POST, OPTIONS
```

Phản hồi cụ thể phụ thuộc server và API. `OPTIONS` là một phương thức HTTP độc lập; có thể được dùng để tìm hiểu khả năng của resource dù không có trình duyệt hoặc CORS.

### 6.2. CORS preflight sử dụng header khác

Khi trình duyệt định gửi một yêu cầu cross-origin cần preflight, nó có thể gửi:

```http
OPTIONS /api/orders HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type, authorization
```

Nếu CORS policy chấp nhận yêu cầu từ origin đó, phản hồi có thể gồm:

```http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET, POST
Access-Control-Allow-Headers: content-type, authorization
Vary: Origin
```

**`Access-Control-Allow-Methods` khác với `Allow`:**

| Header | Mục đích | Nơi thường gặp |
| --- | --- | --- |
| `Allow` | Phương thức được resource đích hỗ trợ theo HTTP | Bắt buộc trong 405; có thể có trong OPTIONS |
| `Access-Control-Allow-Methods` | Phương thức mà CORS policy cho phép trong ngữ cảnh cross-origin | Phản hồi preflight cho trình duyệt |

CORS policy còn phụ thuộc `Origin`, credentials và header yêu cầu. Không thể dựa vào một `Access-Control-Allow-Methods` để kết luận **mọi caller** đều được dùng các phương thức đó; cũng không thể thay header bắt buộc `Allow` của 405 bằng header CORS.

Nếu CORS preflight bị từ chối, trình duyệt có thể hiện lỗi CORS trước khi gửi request chính. **Không được tự suy ra preflight thất bại là lỗi 405 của phương thức chính**. Dùng DevTools và kiểm tra riêng preflight/actual request, đồng thời kiểm tra tại API gateway hoặc reverse proxy.

### 6.3. HEAD cần được kiểm thử riêng

Ví dụ endpoint có GET và framework hỗ trợ HEAD tự động. Phản hồi HEAD phải **không có response body**, trong khi header mô tả biểu diễn có thể tương ứng với GET theo ngữ nghĩa HEAD. Một bộ kiểm thử chỉ kiểm tra GET mà quên HEAD có thể bỏ sót khả năng truy vấn metadata hoặc việc middleware trả body ngoài dự kiến.

Đừng giả định mọi hệ thống hoặc gateway đều tự triển khai HEAD/OPTIONS giống nhau. Danh sách `Allow` phải phản ánh những gì server thực sự chấp nhận ở đường đi của request.

## 7. Triển khai 405 với Java và Spring MVC

Ví dụ sau dùng **Java 17+ và Spring Boot 3 / Spring MVC 6**. Các dòng code chỉ minh họa contract method; trong dự án thật cần tích hợp xác thực, validate payload, lưu trữ, logging và quy tắc nghiệp vụ.

### 7.1. Controller chỉ khai báo phương thức được hỗ trợ

```java
package example.api;

import java.net.URI;
import java.util.List;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping
    public List<OrderView> listOrders() {
        return List.of(new OrderView("ord-001"));
    }

    @PostMapping
    public ResponseEntity<OrderView> createOrder(
            @RequestBody CreateOrderRequest request) {
        // Minh họa: ứng dụng thật cần validate, lưu DB và xử lý idempotency.
        OrderView order = new OrderView("ord-002");
        return ResponseEntity
                .created(URI.create("/api/orders/" + order.id()))
                .body(order);
    }

    public record CreateOrderRequest(String productId) {}
    public record OrderView(String id) {}
}
```

Kết quả:

- `GET /api/orders` được map tới `listOrders`.
- `POST /api/orders` được map tới `createOrder` (thành công minh họa trả 201 Created).
- `PUT /api/orders` **không có handler** cho phương thức này; Spring MVC thường trả **405** và header `Allow` tương ứng.

Trong Spring MVC, GET mapping thông thường có thể đáp ứng HEAD; OPTIONS có thể được framework xử lý tự động. Vì vậy response `Allow` có thể chứa thêm `HEAD`, `OPTIONS` dù controller chỉ khai báo `@GetMapping` và `@PostMapping`. Hãy **kiểm tra kết quả phiên bản/framework thực tế** thay vì hardcode danh sách mong muốn.

### 7.2. Khi nào cần tùy biến response?

Trong nhiều ứng dụng, phản hồi mặc định của Spring MVC đã xử lý 405. Nếu hệ thống cần thống nhất định dạng lỗi theo **Problem Details** thì có thể cài `@RestControllerAdvice`. Cần đặc biệt lưu ý giữ **`Allow`**.

```java
package example.api;

import java.util.Set;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.HttpRequestMethodNotSupportedException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(HttpRequestMethodNotSupportedException.class)
    public ResponseEntity<ProblemDetail> handleMethodNotAllowed(
            HttpRequestMethodNotSupportedException ex) {

        Set<HttpMethod> supported = ex.getSupportedHttpMethods();

        HttpHeaders headers = new HttpHeaders();
        headers.setAllow(supported != null ? supported : Set.of());

        ProblemDetail problem = ProblemDetail.forStatus(
                HttpStatus.METHOD_NOT_ALLOWED);
        problem.setTitle("Method Not Allowed");
        problem.setDetail(
                "HTTP method " + ex.getMethod()
                + " is not supported for this resource");

        return ResponseEntity
                .status(HttpStatus.METHOD_NOT_ALLOWED)
                .headers(headers)
                .body(problem);
    }
}
```

Giải thích:

1. Spring ném `HttpRequestMethodNotSupportedException` khi route tương ứng không nhận method.
2. `getSupportedHttpMethods()` đưa ra tập method hỗ trợ mà framework đã xác định.
3. `headers.setAllow(...)` sinh header `Allow`; **không thay bằng một giá trị đoán từ client**.
4. `ProblemDetail` chuẩn hóa cấu trúc body, còn status vẫn là 405.
5. Handler xử lý lỗi do **Spring MVC** chuyển đến; nếu request bị chặn tại Spring Security, reverse proxy hoặc API gateway trước đó, handler này có thể không được gọi. Các tầng đó cần policy/response riêng.

Đoạn minh họa đặt tiêu đề/chi tiết ở tiếng Anh để khớp các token HTTP phổ biến; sản phẩm có thể nội địa hóa thông điệp. Với hệ thống thật, không đưa thông tin route nội bộ hoặc stack trace vào response công khai.

**Lưu ý tương thích:** API và hành vi tự động của framework có thể khác theo Spring phiên bản/cấu hình. Nếu ứng dụng đã dùng cơ chế xử lý chuẩn như `ResponseEntityExceptionHandler`, có thể tùy biến đúng điểm mở rộng thay vì đăng ký hai handler cạnh tranh.

### 7.3. Lỗi thường gặp trong Spring Security hoặc gateway

Một request `PUT /api/orders` chưa có token có thể nhận **401** từ security filter trước khi Spring MVC kiểm tra method. Điều này không chứng minh endpoint có PUT. Để kiểm thử 405, dùng request có thông tin xác thực hợp lệ, cấu hình CSRF phù hợp và tuyến request đi đến đúng controller.

Nếu gateway chỉ chuyển tiếp GET/POST hoặc chặn PUT theo policy, client có thể nhận mã từ **gateway** (ví dụ 403/405/404 tùy cấu hình), khác với mã do backend tạo. Quan sát response headers, access logs và các request ID tương quan để xác định tầng nào phản hồi.

Tránh quy tắc global kiểu “mọi method không phải GET/POST đều 405” ở gateway nếu backend có resource khác hỗ trợ PATCH/DELETE. Method policy phải tương ứng với hợp đồng các route và được đồng bộ khi thay đổi phiên bản API.

## 8. Tự kiểm chứng bằng curl

Giả sử ứng dụng đang chạy ở `http://localhost:8080` và endpoint `/api/orders` không yêu cầu xác thực trong môi trường học.

### 8.1. Gửi method không được hỗ trợ

```bash
curl -i -X PUT http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"productId":"p-001"}'
```

Kết quả kỳ vọng: **405** và header **`Allow`**; body tùy framework hoặc exception handler. Không cần kiểm tra thứ tự chính xác của các method trong `Allow`, mà cần kiểm tra những method quan trọng có/không có theo contract.

### 8.2. Kiểm tra GET và POST hợp lệ

```bash
curl -i http://localhost:8080/api/orders

curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"productId":"p-001"}'
```

Theo controller minh họa, GET trả **200 OK** và POST trả **201 Created** kèm `Location`. Cần thêm kiểm thử xác thực và validate trong ứng dụng thật.

### 8.3. Kiểm tra OPTIONS và HEAD

```bash
curl -i -X OPTIONS http://localhost:8080/api/orders

curl -I http://localhost:8080/api/orders
```

`curl -I` gửi **HEAD**. Phản hồi HEAD không có body dù có header mô tả biểu diễn. Với OPTIONS, kiểm tra status và header thực tế; nếu có CORS, một OPTIONS kèm `Origin` và `Access-Control-Request-Method` có thể được xử lý khác.

### 8.4. Kiểm tra CORS preflight riêng

```bash
curl -i -X OPTIONS http://localhost:8080/api/orders \
  -H "Origin: https://app.example.test" \
  -H "Access-Control-Request-Method: PUT"
```

Nếu chính sách CORS **không cho phép PUT** từ origin này, preflight có thể bị từ chối hoặc thiếu header CORS cần thiết. Đây **không thay thế** kiểm thử PUT thực sự để xác nhận 405. Đối với CORS, cần test origin, credentials, allowed headers và method theo đúng chính sách.

## 9. Kiểm thử tự động 405 trong Spring

Mục tiêu của test không chỉ là status 405. Phải bảo vệ **hợp đồng**: resource thực sự chấp nhận method nào và response có header đúng.

Ví dụ tích hợp với **Spring Boot Test, Spring MVC Test (MockMvc) và JUnit 5**:

```java
package example.api;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderMethodContractTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void putCollectionIsNotAllowedAndHasAllowHeader() throws Exception {
        mockMvc.perform(put("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"productId\":\"p-001\"}"))
            .andExpect(status().isMethodNotAllowed())
            .andExpect(header().string(
                    HttpHeaders.ALLOW, containsString("GET")))
            .andExpect(header().string(
                    HttpHeaders.ALLOW, containsString("POST")));
    }

    @Test
    void supportedMethodsStillWork() throws Exception {
        mockMvc.perform(get("/api/orders"))
            .andExpect(status().isOk());

        mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"productId\":\"p-001\"}"))
            .andExpect(status().isCreated());
    }
}
```

Trong ví dụ, hai assertion về `Allow` chỉ xác nhận `GET` và `POST` có trong header; một bộ contract test đầy đủ nên **parse danh sách token và so sánh tập phương thức được kỳ vọng**, đặc biệt khi sửa route. Nếu hệ thống bật authentication hoặc CSRF, cấu hình mock identity và CSRF token phù hợp; không tắt bảo mật production chỉ để làm test 405 chạy xanh.

### 9.1. Ma trận trường hợp cần kiểm tra

| Trường hợp | Yêu cầu thử nghiệm | Kỳ vọng cần xác minh |
| --- | --- | --- |
| Method không hỗ trợ trên collection | `PUT /api/orders` khi chỉ GET/POST | 405 + `Allow` đúng |
| Method hỗ trợ bình thường | `GET /api/orders` | 200 hoặc mã thành công theo contract |
| Tạo resource | `POST /api/orders` hợp lệ | 201 và `Location` khi tạo mới theo mô hình |
| URI không tồn tại | `GET /api/nonexistent` | Thường 404 |
| Thiếu xác thực | Request tới API bảo vệ không có token | 401 theo security contract, kiểm tra `WWW-Authenticate` khi áp dụng |
| Không đủ quyền | Method tồn tại nhưng role bị chặn | 403 hoặc chính sách che resource có chủ đích |
| Sai media type | POST JSON endpoint bằng XML | 415 nếu method hợp lệ và content type không được hỗ trợ |
| HEAD | HEAD trên endpoint GET | Response không có body |
| OPTIONS thông thường | OPTIONS không có Origin | Kiểm tra hành vi framework/contract |
| CORS preflight | OPTIONS kèm Origin và Access-Control-Request-Method | Kết quả CORS đúng policy, không đánh đồng với Allow |
| Request qua gateway | PUT đi qua reverse proxy/gateway | Cùng chính sách route, không phát sinh mã sai từ lớp trung gian |
| Thay đổi contract | Thêm PATCH cho resource | PATCH hoạt động nếu được thiết kế; Allow và OpenAPI được cập nhật tương ứng |

### 9.2. Kiểm thử negative phải dựa trên trạng thái hợp lệ

Nếu endpoint `PATCH` tồn tại nhưng payload bị sai, request có thể trả **400** hoặc **422** tùy contract; đó **không** phải test tốt cho 405. Để kiểm tra method không được hỗ trợ, dùng URI đang tồn tại và xác thực hợp lệ, tránh các lý do thất bại khác che mất route.

Tương tự, test `DELETE` trên một đơn hàng đã giao xong có thể trả **409 Conflict**, vì method DELETE được hỗ trợ nhưng trạng thái nghiệp vụ không cho phép. Test này khác với trường hợp **không có DELETE mapping**.

## 10. OpenAPI và hợp đồng public API

OpenAPI mô tả những thao tác theo **HTTP method và path**. Nếu `/api/orders` chỉ có GET và POST, tài liệu không được quảng cáo PUT hoặc DELETE trên collection.

Ví dụ OpenAPI 3.1 tối giản:

```yaml
openapi: 3.1.0
info:
  title: Orders API
  version: 1.0.0
paths:
  /api/orders:
    get:
      operationId: listOrders
      responses:
        '200':
          description: List orders
    post:
      operationId: createOrder
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [productId]
              properties:
                productId:
                  type: string
      responses:
        '201':
          description: Order created
          headers:
            Location:
              description: URI of the created order
              schema:
                type: string
  # Không khai báo put hoặc delete cho collection này.
```

**Điểm cần hiểu đúng:** OpenAPI mô tả thao tác tồn tại; nó **không tự buộc** server sinh 405/`Allow` cho các phương thức không khai báo. Hành vi của runtime cần được kiểm tra riêng. Có thể thêm phần mô tả lỗi chung, response headers và contract tests để client biết cách xử lý.

### 10.1. Khi thay đổi phương thức được hỗ trợ

Giả sử nhóm phát triển thêm `PATCH /api/orders/{id}`. Quy trình thay đổi tối thiểu:

1. Xác định payload, điều kiện cập nhật, quyền hạn và idempotency.
2. Khai báo mapping controller, validate và authorization.
3. Cập nhật OpenAPI cho path/method đúng.
4. Cập nhật contract test về method hỗ trợ, 405 và `Allow`.
5. Kiểm tra gateway, WAF, CORS, caching và SDK/client có cho phép PATCH không.
6. Triển khai tương thích với client hiện tại; theo dõi mã 405 sau release để phát hiện sai cấu hình.

Đừng chỉ mở PATCH ở CORS rồi nghĩ backend đã hỗ trợ PATCH. Cũng không chỉ thêm `@PatchMapping` mà quên policy ở gateway hoặc quyền sử dụng.

## 11. Xử lý lỗi có ích và an toàn

### 11.1. Nên gửi thông tin gì?

Phản hồi 405 hữu ích tối thiểu có:

- HTTP status **405**.
- Header **`Allow`** thể hiện các phương thức được hỗ trợ.
- Body lỗi nhất quán theo contract (có thể dùng `application/problem+json`).
- Request/correlation ID trong header hoặc log để truy vết.
- Thông điệp ngắn chỉ rõ method được gửi không phù hợp với resource, không lộ stack trace hoặc thông tin triển khai nội bộ.

Ví dụ:

```http
HTTP/1.1 405 Method Not Allowed
Allow: GET, HEAD, POST, OPTIONS
Content-Type: application/problem+json
X-Request-Id: req-8c2d

{
  "type": "about:blank",
  "title": "Method Not Allowed",
  "status": 405,
  "detail": "PUT is not supported on this resource",
  "instance": "/api/orders"
}
```

Nếu client có thể tự khắc phục, tài liệu nên cho biết **phương thức và resource hợp lệ để đạt mục tiêu nghiệp vụ**, ví dụ dùng POST để tạo order, dùng GET để tra cứu. Không khuyến khích client tự dò hết mọi phương thức bằng request gây side effect trên production.

### 11.2. Cache và khả năng quan sát

Theo ngữ nghĩa HTTP, **405 có thể được cache theo heuristic** nếu các điều kiện của cache và policy cho phép. Khi thay đổi contract route, một phản hồi 405 cũ ở cache trung gian có thể gây khó hiểu. Với API có yêu cầu không lưu cache lỗi, cân nhắc `Cache-Control: no-store` hoặc chiến lược cache phù hợp với loại dữ liệu.

Theo dõi:

- Tỷ lệ 405 theo **path template** và method (tránh gắn nhãn metric bằng ID động).
- 405 theo API version, client version, deployment và lớp trả lỗi (gateway/backend).
- Sự gia tăng 405 sau release: client gửi sai method, route bị đổi, gateway/WAF cấu hình thiếu, preflight bị nhầm.
- Cùng với 401, 403, 404 và 415 để tách nhóm lỗi hợp đồng, quyền và nội dung.

**Không đặt thông tin bí mật hoặc dữ liệu nhạy cảm** trong log request body chỉ để điều tra mã 405. Method, route template, status, correlation ID thường đủ để khoanh vùng.

## 12. Những lỗi triển khai phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Trả `405` nhưng không có `Allow` | Vi phạm yêu cầu header của 405; client khó biết hợp đồng | Để framework sinh hoặc bảo toàn `Allow` trong handler tùy biến |
| Mọi lỗi method đều trả `404` | Client khó phân biệt sai URI với sai method | Mapping rõ resource/method, kiểm thử trường hợp 405 |
| Trả `501` cho mọi method chưa khai báo trong controller | Nhầm thiếu khả năng server với resource không cho method | Dùng 405 khi server biết method nhưng resource không hỗ trợ |
| Dùng `405` để diễn tả thiếu quyền | Che lỗi authorization và gây hiểu sai contract | Dùng 401/403 theo ngữ nghĩa và chính sách bảo mật |
| Cho phép mọi method để tránh lỗi | Tạo thao tác ngoài hợp đồng, có thể không an toàn | Chỉ khai báo phương thức phù hợp nghiệp vụ |
| Hardcode `Allow: GET, POST` ở toàn bộ API | Header sai cho resource có PATCH/DELETE/HEAD | Sinh từ route/resource thực tế; test sau thay đổi |
| Nhầm `Access-Control-Allow-Methods` với `Allow` | CORS đúng nhưng response 405 vẫn thiếu header bắt buộc | Tách method support và cross-origin policy |
| Kiểm thử chỉ ở controller, không qua gateway | Lỗi do proxy hoặc security bị bỏ sót | Test thêm end-to-end ở đường đi thực tế |
| Đổi PUT sang POST tùy ý để “sửa lỗi” | Phá ngữ nghĩa và idempotency của client | Đọc contract resource, sửa thiết kế hoặc request đúng |
| Không quản lý phiên bản OpenAPI | Client sinh mã gọi phương thức không còn tồn tại | Đưa contract tests và kiểm tra compatibility vào CI |

## 13. Bài thực hành và câu hỏi tự đánh giá

### 13.1. Tình huống thực tế

Thiết kế API quản lý hóa đơn với các quy tắc:

- `GET /api/invoices/{id}`: xem hóa đơn; chỉ người có quyền được xem.
- `POST /api/invoices`: lập hóa đơn mới.
- Không có thao tác sửa hoặc xóa hóa đơn đã phát hành; nghiệp vụ điều chỉnh được xử lý bằng một resource riêng.
- CORS chỉ cho phép ứng dụng tại `https://billing.example.test` gọi GET/POST với header cần thiết.

Hãy trả lời:

1. Client gửi `DELETE /api/invoices/inv-100` trên một resource được xác định có route GET. Nếu không có DELETE mapping, response nào phù hợp? Header nào phải có?
2. Client chưa xác thực gửi GET trên API bảo vệ. Vì sao 401 có thể xuất hiện trước khi router kiểm tra method?
3. Client gửi `POST /api/invoices` với `Content-Type: application/xml` nhưng API chỉ nhận JSON. Mã nào phù hợp hơn 405?
4. Browser muốn gửi `DELETE` từ origin trên. Preflight gửi method nào và header nào? Nó thất bại theo policy nào?
5. Nếu API có endpoint điều chỉnh hóa đơn `/api/invoices/{id}/adjustments` dùng POST, vì sao không nên mở `PUT /api/invoices/{id}` chỉ để “dễ gọi”?
6. Nếu một client mới nhận 405 sau deploy, cần kiểm tra OpenAPI, gateway, bảo mật và routing theo thứ tự nào?

### 13.2. Gợi ý lời giải

1. **405 Method Not Allowed** khi method đã được nhận biết nhưng resource đích không cho DELETE; phải có `Allow` mô tả những method hiện hỗ trợ, ví dụ `GET, HEAD, OPTIONS` nếu server thực sự hỗ trợ cả ba.
2. Security filter có thể chặn request thiếu xác thực trước controller. **401** phản ánh yêu cầu xác thực, không nói GET có mapping hay không.
3. **415 Unsupported Media Type** nếu POST hợp lệ nhưng loại nội dung gửi lên không được hỗ trợ.
4. Browser gửi **OPTIONS** kèm `Origin` và `Access-Control-Request-Method: DELETE`; CORS policy không cho DELETE nên preflight không được chấp thuận. Đó là quy tắc **cross-origin**, khác với `Allow` của 405.
5. Hóa đơn đã phát hành có lịch sử kế toán cần bảo toàn; resource adjustment nêu rõ nghiệp vụ thay đổi thay vì sửa/ghi đè chứng từ. Method phải phản ánh hợp đồng và bất biến dữ liệu.
6. Kiểm tra request thực tế (URI, method, headers), hợp đồng OpenAPI, response `Allow`, identity/cấu hình security, log ở gateway và backend, sau đó so sánh version vừa triển khai. Xác minh tầng nào tạo response.

### 13.3. Checklist hoàn thành

- [ ] Phân biệt đúng 405 với 404, 401/403, 415 và 501.
- [ ] Mọi phản hồi 405 do hệ thống tạo đều có header `Allow`.
- [ ] `Allow` thể hiện method của resource hiện tại, không hardcode cho toàn bộ ứng dụng.
- [ ] Chính sách CORS được thiết kế và kiểm thử riêng với danh sách method của resource.
- [ ] GET/HEAD/OPTIONS và các method có side effect được xử lý theo ngữ nghĩa HTTP.
- [ ] Endpoint Spring được kiểm thử bằng request hợp lệ về identity, route và content type.
- [ ] Lỗi tùy biến theo Problem Details không làm mất `Allow`.
- [ ] OpenAPI, gateway, server và contract tests mô tả cùng một API.
- [ ] Các thay đổi method được triển khai có phiên bản, giám sát và hướng dẫn client.

## 14. Kết luận

**405 Method Not Allowed** là phản hồi chuẩn khi máy chủ nhận biết phương thức HTTP nhưng **resource đích không hỗ trợ phương thức đó**. Header **`Allow` là yêu cầu bắt buộc trong response 405**, cho client biết các method hiện có. Điều này khác với **501** (server không triển khai chức năng/phương thức), **404** (resource không được tìm thấy), **401/403** (vấn đề xác thực hoặc quyền) và **415** (media type không hỗ trợ).

Trong một REST API có hợp đồng rõ ràng, việc giải quyết 405 bắt đầu từ **resource, URI và ngữ nghĩa method**, sau đó kiểm tra routing, security, CORS, gateway và xử lý lỗi. Khi triển khai trên Spring MVC, có thể dựa vào cơ chế mặc định hoặc tùy biến body theo Problem Details, nhưng luôn phải **bảo toàn header `Allow` và kiểm thử trên đường đi request thực tế**.

