# Chẩn đoán lỗi HTTP 405: phương thức không khớp và cách kiểm tra `Allow`

Trong REST API, URI xác định tài nguyên còn phương thức HTTP diễn tả thao tác mà client muốn thực hiện. Một đường dẫn có thể tồn tại nhưng chỉ chấp nhận một số phương thức: chẳng hạn `GET /api/orders/42` dùng để đọc đơn hàng, `PATCH /api/orders/42` dùng để cập nhật một phần, còn `PUT /api/orders/42` chưa được thiết kế. Khi client gửi `PUT` đến đường dẫn này, server có thể trả **`405 Method Not Allowed`**.

Bài học thuộc chương **Chẩn đoán sự cố** của mô-đun **INTEGRATION_API_REST**. Mục tiêu là tìm nguyên nhân thực sự của 405 bằng cách đối chiếu **resource, URI, phương thức HTTP, hợp đồng API và header `Allow`**, sau đó sửa ở đúng lớp: client, ứng dụng Java/Spring, bộ định tuyến, gateway hoặc cấu hình bảo mật.

## 1. Khi nào 405 là phản hồi đúng?

Theo ngữ nghĩa HTTP, **405** có nghĩa là server nhận biết phương thức được gửi, nhưng **tài nguyên đích không hỗ trợ phương thức ấy**. Server tạo phản hồi 405 **phải gửi header `Allow`** với danh sách các phương thức hiện được hỗ trợ cho tài nguyên đích (RFC 9110, phần 15.5.6 và 10.2.1).

Ví dụ, giả sử API quy định:

| Tài nguyên | Phương thức được thiết kế | Ý nghĩa |
| --- | --- | --- |
| `/api/orders` | `GET`, `POST` | Liệt kê và tạo đơn hàng |
| `/api/orders/{id}` | `GET`, `HEAD`, `PATCH` | Đọc thông tin, đọc header và cập nhật một phần |

Client gửi yêu cầu ngoài hợp đồng:

```http
PUT /api/orders/42 HTTP/1.1
Host: api.example.com
Content-Type: application/json

{"status":"PAID"}
```

Một phản hồi minh họa hợp lệ là:

```http
HTTP/1.1 405 Method Not Allowed
Allow: GET, HEAD, PATCH
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Method Not Allowed",
  "status": 405,
  "detail": "Phương thức PUT không được hỗ trợ cho tài nguyên này."
}
```

Các phương thức trong `Allow` ở đây chỉ là **ví dụ theo hợp đồng giả định**. Giá trị thực tế phụ thuộc vào tài nguyên và cấu hình định tuyến của server. Thứ tự phương thức không có ý nghĩa; server cũng có thể trả `Allow` rỗng nếu tài nguyên tạm thời không chấp nhận phương thức nào. JSON mô tả lỗi là tùy chọn; **`Allow` mới là header bắt buộc khi trả 405**.

Điểm cần phân biệt: `Allow` mô tả khả năng của **tài nguyên đích**, không thay thế kiểm tra xác thực/phân quyền. Một người dùng có thể nhìn thấy `PATCH` trong `Allow` nhưng vẫn nhận `403 Forbidden` khi thực hiện `PATCH` do không có quyền.

## 2. Phân biệt 405 với các lỗi thường bị nhầm

| Mã / hiện tượng | Cách hiểu khi chẩn đoán | Hướng kiểm tra |
| --- | --- | --- |
| **405 Method Not Allowed** | Đường dẫn có tài nguyên phù hợp, nhưng phương thức hiện tại không được hỗ trợ. | Đọc `Allow`, so sánh hợp đồng và route thực tế. |
| **404 Not Found** | Không tìm thấy tài nguyên/route phù hợp hoặc server chủ động che sự tồn tại của nó. | Kiểm tra URL, prefix, biến đường dẫn, slash, proxy rewrite và chính sách bảo mật. |
| **501 Not Implemented** | Server không nhận biết hoặc không hỗ trợ khả năng xử lý phương thức yêu cầu. | Kiểm tra phương thức lạ, server/gateway có hỗ trợ phương thức đó không. |
| **400 Bad Request** | Yêu cầu không hợp lệ, chẳng hạn JSON sai cú pháp. | Kiểm tra payload và cách phân tích request. |
| **415 Unsupported Media Type** | Route có thể hỗ trợ phương thức, nhưng không nhận `Content-Type` đã gửi. | Kiểm tra `consumes`, `Content-Type` và codec. |
| **406 Not Acceptable** | Server không thể tạo biểu diễn thỏa `Accept`. | Kiểm tra `produces`, `Accept` và định dạng trả về. |
| **401 / 403** | Yêu cầu thiếu thông tin xác thực hoặc không được phép thực hiện. | Kiểm tra token, quyền và security filter. |
| **Lỗi CORS trên trình duyệt** | Trình duyệt chặn truy cập phản hồi, có thể do preflight hoặc header CORS. | Xem Network tab, request `OPTIONS` và các header `Access-Control-*`. |

Chẳng hạn, nếu controller khai báo `@PostMapping(path = "/orders", consumes = "application/json")`, một `POST` với `Content-Type: text/plain` thường dẫn đến **415**, không phải 405. Đổi `POST` thành `PUT` chỉ vì gặp lỗi 415 sẽ làm sai hợp đồng.

**Không suy ra mã lỗi chỉ từ URI.** Kết quả còn phụ thuộc vào phương thức, mapping của framework, các filter và lớp đứng trước ứng dụng.

## 3. Quy trình tái hiện và tìm nguyên nhân

### Bước 1 — Ghi lại request thực tế

Thu thập phương thức, URL đầy đủ (scheme, host, path, query), `Content-Type`, `Accept`, kết quả redirect và `X-Request-ID`/trace ID nếu có. Mã nguồn client nói “gọi PATCH” chưa đủ: SDK, proxy hoặc cấu hình redirect có thể khiến request đến server mang phương thức khác.

```bash
curl -i -X PUT "https://api.example.com/api/orders/42" \
  -H "Content-Type: application/json" \
  -d '{"status":"PAID"}'
```

`-i` hiển thị cả status và response headers; `-v` giúp quan sát request/redirect/TLS chi tiết hơn khi cần. Ví dụ sử dụng địa chỉ giả định `api.example.com`; thay bằng môi trường kiểm thử của bạn.

### Bước 2 — Đọc `Allow`, không chỉ đọc body

Với phản hồi 405, kiểm tra `Allow` trước:

```http
HTTP/1.1 405 Method Not Allowed
Allow: GET, HEAD, PATCH
```

- Nếu client dùng `PUT` nhưng `Allow` chỉ liệt kê `GET, HEAD, PATCH`, kiểm tra xem **đúng ý định là cập nhật một phần bằng PATCH** hay API cần được bổ sung PUT.
- Nếu `Allow` thiếu hoàn toàn trong phản hồi 405, đây là dấu hiệu phản hồi chưa tuân thủ HTTP hoặc đã bị gateway/handler tùy chỉnh làm rơi header. Cần xác định thành phần nào tạo 405.
- Nếu `Allow` không khớp OpenAPI/controller, xem xét sự khác biệt giữa phiên bản đã triển khai, route prefix, gateway và handler xử lý lỗi.

Không đoán rằng mọi tài nguyên đều phải có `POST`, `PUT` hoặc `DELETE`. Chỉ mở phương thức khi nghiệp vụ và hợp đồng API có quy định rõ.

### Bước 3 — So sánh URI và bảng route

Đối chiếu theo **cặp `(HTTP method, path)`**. Một mapping `POST /api/orders` không đồng nghĩa server cho phép `POST /api/orders/42`. Tương tự, `/api/orders/42/` có thể khác `/api/orders/42` tùy cấu hình.

Đọc hợp đồng OpenAPI và annotation của controller; kiểm tra prefix như `/v1`, `/api`, context path, trailing slash và route rewrite. Kiểm tra xem bản ứng dụng triển khai có đúng phiên bản hợp đồng mà client đang sử dụng hay không.

### Bước 4 — Xác định lớp trả 405

Trong luồng `client → CDN/WAF → API gateway/reverse proxy → Spring Security/filter → Spring MVC controller`, bất kỳ lớp nào hỗ trợ chặn phương thức đều có thể là nguồn phản hồi.

Các dấu hiệu có ích gồm response headers của proxy (nếu có), trace ID, access log tại gateway, access log ứng dụng, thời điểm controller được gọi và bản ghi exception trong Spring MVC. Khi có quyền truy cập nội bộ, thử cùng một request qua gateway và trực tiếp tới service ở môi trường kiểm thử; khác biệt phản hồi giúp khoanh vùng. Tránh công khai endpoint nội bộ chỉ để thử lỗi.

### Bước 5 — Sửa hợp đồng hoặc cách gọi

Nếu client dùng sai phương thức, sửa HTTP client/SDK theo OpenAPI và kiểm tra request phát ra trên thực tế. Nếu API thực sự cần phương thức mới, bổ sung mapping cùng hành vi nghiệp vụ, xác thực/phân quyền, kiểm thử, mô tả OpenAPI và cấu hình gateway tương ứng. Nếu gateway chặn một phương thức hợp lệ, chỉnh chính sách đúng route, với mức quyền phù hợp. **Không bật mọi phương thức trên toàn bộ API** để làm biến mất 405.

405 do phương thức không phù hợp là lỗi **không được giải quyết bằng retry cùng request**. Việc retry liên tục chỉ tăng tải; cần thay đổi request hoặc cấu hình.

## 4. Tái hiện bằng Spring Boot / Spring MVC

Giả sử một API Java 17+ với Spring Boot 3 / Spring Framework 6 khai báo:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping("/{id}")
    OrderView getOrder(@PathVariable long id) {
        return new OrderView(id, "NEW");
    }

    @PatchMapping("/{id}")
    OrderView patchOrder(@PathVariable long id,
                         @RequestBody ChangeStatus body) {
        return new OrderView(id, body.status());
    }

    record OrderView(long id, String status) {}
    record ChangeStatus(String status) {}
}
```

Đoạn mã cố ý dùng dữ liệu giả để tập trung vào method routing; trong ứng dụng thật còn cần service, validation, persistence và authorization. Ở đây:

- `GET /api/orders/42` khớp `getOrder`.
- `PATCH /api/orders/42` khớp `patchOrder`.
- `PUT /api/orders/42` không có mapping tương ứng nên Spring MVC thường trả **405** qua cơ chế xử lý exception mặc định.
- Spring MVC có cơ chế hỗ trợ `HEAD` cho route `GET`; hãy kiểm tra hành vi thực tế của phiên bản framework và các filter khi đánh giá `Allow`.

Thử ba lệnh sau trong môi trường chạy ứng dụng:

```bash
curl -i "http://localhost:8080/api/orders/42"

curl -i -X PATCH "http://localhost:8080/api/orders/42" \
  -H "Content-Type: application/json" \
  -d '{"status":"PAID"}'

curl -i -X PUT "http://localhost:8080/api/orders/42" \
  -H "Content-Type: application/json" \
  -d '{"status":"PAID"}'
```

Nếu ứng dụng có Spring Security, request chưa xác thực có thể bị chặn bằng 401/403 trước khi tới bước chọn handler. Vì vậy, kiểm chứng route ở hai mức: test độc lập cho Spring MVC và test qua đầy đủ security/gateway trong môi trường gần production.

### Test tự động bảo vệ hành vi 405 và `Allow`

Ví dụ với JUnit 5, Spring Test MockMvc và controller ở trên:

```java
import java.util.Arrays;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class OrderControllerMethodTest {
    private final MockMvc mvc = MockMvcBuilders
        .standaloneSetup(new OrderController())
        .build();

    @Test
    void putToExistingRouteReturns405WithAllow() throws Exception {
        mvc.perform(put("/api/orders/42")
                    .contentType("application/json")
                    .content("{\"status\":\"PAID\"}"))
            .andExpect(status().isMethodNotAllowed())
            .andExpect(header().exists(HttpHeaders.ALLOW))
            .andExpect(result -> {
                String headerValue =
                    result.getResponse().getHeader(HttpHeaders.ALLOW);
                var allowed = Arrays.asList(headerValue.split("\\s*,\\s*"));
                assertTrue(allowed.contains("GET"));
                assertTrue(allowed.contains("PATCH"));
            });
    }
}
```

Test cố ý kiểm tra **các phương thức chủ yếu có mặt** thay vì so sánh nguyên chuỗi `Allow`: framework có thể thêm `HEAD` hoặc `OPTIONS`, và thứ tự token không cố định. Kiểm thử bổ sung nên bao gồm đường dẫn không tồn tại (404), yêu cầu có `Content-Type` sai (415), quyền truy cập (401/403) và thử qua gateway.

Nếu tự viết `@ControllerAdvice` hoặc `HandlerExceptionResolver` để biến exception thành JSON/Problem Details, hãy **giữ header `Allow`** từ `HttpRequestMethodNotSupportedException` khi trả 405. Việc chỉ tạo body đẹp nhưng bỏ `Allow` khiến client thiếu thông tin chẩn đoán và làm phản hồi không đúng quy định HTTP.

## 5. 405, `OPTIONS`, `HEAD` và CORS

Hai header dễ bị nhầm là:

| Header | Vai trò | Thường xuất hiện ở đâu |
| --- | --- | --- |
| `Allow` | Những phương thức HTTP hiện được tài nguyên đích hỗ trợ; bắt buộc với 405. | Phản hồi 405, và có thể trong phản hồi `OPTIONS`. |
| `Access-Control-Allow-Methods` | Những phương thức được cho phép trong trao đổi CORS với một origin cụ thể theo chính sách CORS. | Phản hồi CORS preflight `OPTIONS`. |

Khi trình duyệt gửi request cross-origin có phương thức hoặc header cần preflight, nó có thể gửi:

```http
OPTIONS /api/orders/42 HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: PATCH
Access-Control-Request-Headers: content-type,authorization
```

Nếu CORS được cấu hình đúng và request được cho phép, phản hồi có thể chứa:

```http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET, PATCH
Access-Control-Allow-Headers: content-type, authorization
```

Đây là ví dụ về **chính sách CORS**, không phải cam kết mọi route đều xử lý các phương thức vừa liệt kê. Ngược lại, có route `PATCH` hợp lệ cũng **không bảo đảm** trình duyệt gọi được nếu preflight bị chặn do CORS hoặc filter bảo mật.

Khi trình duyệt báo lỗi CORS:

1. Mở **Network** trong DevTools để xem có request `OPTIONS` preflight hay không, phương thức mà trình duyệt dự định gửi và status của từng request.
2. Kiểm tra `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers` và chính sách xác thực.
3. Gọi API bằng `curl` để quan sát HTTP status/header thực, vì `curl` không thực thi chính sách CORS như trình duyệt.
4. Nếu `OPTIONS` bị 405/401/403 trước controller, kiểm tra cấu hình CORS, security filter và gateway; nếu `PATCH` thực tế bị 405, kiểm tra method mapping.

Sử dụng `curl -I` để gửi **HEAD** khi cần kiểm tra header mà không tải body. Việc khai báo `GET` trong Spring MVC thường cho phép HEAD tương ứng; đừng tự tạo một route `HEAD` trả body như GET. Còn `OPTIONS` có thể được framework tự xử lý, nhưng vẫn cần cấu hình phù hợp với gateway và CORS.

## 6. Những tình huống khó thấy trong production

**Sai prefix hoặc phương thức khác giữa các môi trường.** Client gọi `PATCH /api/v2/orders/42` theo OpenAPI mới, nhưng service đang triển khai chỉ hỗ trợ GET hoặc deployment cũ. So sánh route thực trên môi trường xảy ra lỗi với hợp đồng đã phát hành.

**Gateway/WAF chặn PUT, PATCH hoặc DELETE.** Controller đã có `@PatchMapping` nhưng gateway chỉ cho `GET, POST`. 405 có thể xuất hiện mà log controller hoàn toàn không ghi nhận request. So sánh access log và request ID ở từng lớp trước khi chỉnh controller.

**Redirect làm thay đổi cách gửi request.** Một redirect 301/302 có thể khiến một số client chuyển `POST` sang `GET`; redirect 307/308 được thiết kế để giữ nguyên phương thức. Kiểm tra request sau redirect trong log thay vì chỉ xem request ban đầu.

**Header hoặc code lỗi bị handler tùy chỉnh thay đổi.** Một `@ControllerAdvice`, filter hoặc proxy có thể biến lỗi 405 thành mã khác hoặc loại bỏ `Allow`. Kiểm tra cả raw response và cơ chế ánh xạ lỗi, không chỉ thông báo của SDK.

**Nhầm lỗi phân quyền với lỗi phương thức.** Phương thức tồn tại nhưng người gọi không có quyền thường phải xử lý theo chính sách xác thực/phân quyền (401/403, hoặc 404 có chủ đích khi che tài nguyên); không lấy 405 để biểu diễn việc một người dùng cụ thể thiếu quyền.

**Method override và proxy rewrite.** Một số hệ thống cũ dùng `X-HTTP-Method-Override` hoặc middleware chuyển đổi phương thức. Kiểm tra phương thức trên dây và phương thức sau khi middleware xử lý; không tự bật override nếu hợp đồng và chính sách bảo mật không yêu cầu.

**Cache phản hồi lỗi.** Theo HTTP, 405 có thể được cache theo cơ chế heuristic nếu không có chỉ thị ngăn cản. Khi vừa thay đổi danh sách phương thức, kiểm tra chính sách `Cache-Control` và lớp cache trung gian nếu vẫn thấy 405 cũ.

## 7. Checklist điều tra nhanh

- [ ] Đã ghi lại **phương thức thật**, URI đầy đủ và status/header của phản hồi.
- [ ] Đã đọc `Allow` khi nhận 405, không suy đoán từ body.
- [ ] Đã đối chiếu route theo `(method, path)` với OpenAPI và controller đang chạy.
- [ ] Đã phân biệt 405 với 404, 415, 501, 401/403 và lỗi CORS preflight.
- [ ] Đã xác định lỗi phát sinh tại gateway, filter/security hay Spring MVC.
- [ ] Đã sửa ở đúng nơi và cập nhật kiểm thử, tài liệu API khi hợp đồng thay đổi.
- [ ] Đã xác minh lại cả route hợp lệ, route sai phương thức và header `Allow`.

### Bài tập tự kiểm tra

Cho API chỉ hỗ trợ `GET /api/items/{id}` và `DELETE /api/items/{id}`, tài nguyên `/api/items/7` tồn tại, không có rào cản bảo mật:

| Request | Kết quả hợp lý | Giải thích |
| --- | --- | --- |
| `GET /api/items/7` | 200 (giả sử truy xuất thành công) | Đúng đường dẫn và phương thức. |
| `POST /api/items/7` | **405**, kèm `Allow` | Tài nguyên/route có nhưng không nhận POST. |
| `GET /api/itmes/7` | **404** | Path sai chính tả, không có route tương ứng. |
| `DELETE /api/items/7` | 2xx/204 nếu xóa thành công | Phương thức có hỗ trợ; kết quả nghiệp vụ quyết định status cụ thể. |

Trong thực tế, kết quả có thể thay đổi nếu Spring Security, proxy hoặc chính sách ẩn tài nguyên can thiệp. Khi xác minh 405, hãy ưu tiên bằng chứng từ **request thực**, **`Allow`**, **mapping đang triển khai** và **log của lớp trả phản hồi**.

## Tài liệu tham khảo

- [RFC 9110 — HTTP Semantics, mục 15.5.6 (405 Method Not Allowed)](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.5.6).
- [RFC 9110 — HTTP Semantics, mục 10.2.1 (Allow)](https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.1).
- [Spring Framework — Request Mapping](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html).
- [MDN — Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS).
