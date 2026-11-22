# Hiển thị request, cURL, response và thời gian phản hồi

Sau khi người dùng chọn **Try it out** và nhấn **Execute**, Swagger UI gửi HTTP request đến server được chọn trong tài liệu OpenAPI. Kết quả hiển thị giúp kiểm tra request đã được tạo như thế nào, server trả về status nào, response có nội dung gì và request mất bao lâu để hoàn tất ở phía trình duyệt.

Các phần này đặc biệt hữu ích khi tích hợp API: có thể đối chiếu request URL và cURL với hợp đồng, xem header và body thực tế, kiểm tra lỗi từ server rồi tái hiện request bằng công cụ dòng lệnh. Thời gian phản hồi trên giao diện là thời gian quan sát từ phía client; nó không tự cho biết riêng thời gian xử lý bên trong server.

## 1. Những phần xuất hiện sau khi Execute

Khi operation được thực thi trong Swagger UI, giao diện thường hiển thị các thông tin sau:

| Phần hiển thị | Nội dung | Câu hỏi cần trả lời |
|---|---|---|
| Request URL | URL đầy đủ được gọi, gồm server, path và query string | Request đi đến host và endpoint nào? |
| cURL | Lệnh tương đương để tái hiện request | Có thể chạy lại request từ terminal không? |
| Server response | HTTP status code và thông tin phản hồi | Server chấp nhận hay từ chối request? |
| Response body | Nội dung trả về theo media type | Dữ liệu thực tế có đúng schema không? |
| Response headers | Header server gửi về | Content-Type, cache, request ID hoặc thông tin khác là gì? |
| Response time | Thời gian request hoàn tất được giao diện đo | Client đã chờ bao lâu? |

Tên và cách sắp xếp từng vùng có thể khác nhẹ giữa các phiên bản Swagger UI. Nội dung cốt lõi vẫn là request đã gửi và response trình duyệt nhận được.

## 2. Request URL cho biết chính xác đích gọi

Request URL được tạo từ server URL trong OpenAPI, path của operation và các tham số mà người dùng nhập. Ví dụ operation:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;

@GetMapping("/orders/{orderId}")
OrderResponse getOrder(
        @PathVariable("orderId") String orderId,
        @RequestParam(name = "includeItems", defaultValue = "false")
        boolean includeItems) {
    // ...
}
~~~

Nếu server được chọn là <code>http://localhost:8080/api</code>, người dùng nhập <code>orderId = ORD-100</code> và bật <code>includeItems</code>, request URL có thể là:

~~~text
http://localhost:8080/api/orders/ORD-100?includeItems=true
~~~

Khi kiểm tra URL, hãy đối chiếu:

- Scheme là <code>http</code> hay <code>https</code>.
- Host và port có đúng môi trường đang thử không.
- Context path hoặc prefix của gateway có bị thiếu hay lặp không.
- Path variable đã được thay bằng giá trị nhập chưa.
- Query parameter có tên và giá trị đúng không.
- Giá trị có ký tự đặc biệt đã được URL encode phù hợp chưa.

Nếu URL sai, kiểm tra danh sách server trong OpenAPI, cấu hình <code>servers</code>, context path, reverse proxy và server URL đang chọn trong Swagger UI. Không nên vội kết luận controller bị lỗi khi request chưa đến đúng ứng dụng.

## 3. cURL là bản tái hiện request

Swagger UI thường cung cấp một lệnh cURL dựa trên operation, server, parameter, request body và thông tin xác thực đã chọn. Ví dụ:

~~~bash
curl -X 'GET' \
  'http://localhost:8080/api/orders/ORD-100?includeItems=true' \
  -H 'accept: application/json' \
  -H 'Authorization: Bearer <access-token>'
~~~

Lệnh này gửi request GET đến endpoint, yêu cầu response JSON và đính kèm Bearer token. Với request có body, cURL có thể có thêm content type và dữ liệu:

~~~bash
curl -X 'POST' \
  'http://localhost:8080/api/orders' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
    "productCode": "SKU-100",
    "quantity": 2
  }'
~~~

Có thể sao chép lệnh từ Swagger UI và chạy trong terminal để tái hiện request mà không cần mở giao diện. Khi dùng token, thay placeholder bằng token thử nghiệm còn hiệu lực và tránh lưu token thật vào script, lịch sử terminal dùng chung hoặc tài liệu.

### 3.1. cURL không nhất thiết là bản ghi byte-for-byte của trình duyệt

Lệnh cURL được dựng từ thông tin OpenAPI và trạng thái tương tác của Swagger UI. Nó hữu ích để tái hiện method, URL, header đã khai báo và request body, nhưng không nhất thiết chứa mọi header do trình duyệt, proxy hoặc cookie tự thêm. Ví dụ, request thực tế có thể mang <code>Origin</code>, <code>User-Agent</code>, cookie hoặc header phục vụ CORS mà đoạn cURL hiển thị không thể hiện đầy đủ.

Vì vậy, nếu cần điều tra chính xác một request lỗi, hãy xem thêm tab Network của trình duyệt hoặc log phía server. Dùng cURL để tái hiện và thu hẹp vấn đề, rồi so sánh với request thực tế khi có khác biệt.

### 3.2. Chạy cURL trên Windows

Trên Windows PowerShell, tên <code>curl</code> có thể được ánh xạ thành alias của <code>Invoke-WebRequest</code> tùy phiên bản và cấu hình. Nếu muốn chạy cú pháp cURL được Swagger UI tạo ra, dùng executable <code>curl.exe</code> khi đã cài đặt. Có thể cần điều chỉnh dấu nháy hoặc xuống dòng theo shell đang sử dụng.

## 4. Đọc HTTP status trong Server response

Status code cho biết kết quả ở mức HTTP. Một số nhóm thường gặp:

| Nhóm | Ý nghĩa | Ví dụ |
|---|---|---|
| 2xx | Request được xử lý thành công | <code>200 OK</code>, <code>201 Created</code>, <code>204 No Content</code> |
| 3xx | Cần chuyển hướng hoặc có trạng thái redirect | <code>301</code>, <code>302</code>, <code>304</code> |
| 4xx | Request có vấn đề hoặc không được phép | <code>400</code>, <code>401</code>, <code>403</code>, <code>404</code>, <code>409</code> |
| 5xx | Server hoặc thành phần trung gian gặp lỗi | <code>500</code>, <code>502</code>, <code>503</code>, <code>504</code> |

Không chỉ nhìn màu hoặc số status. Hãy đối chiếu status thực tế với response được khai báo trong OpenAPI:

- <code>200</code>: đọc response body và kiểm tra dữ liệu.
- <code>201</code>: kiểm tra tài nguyên mới được tạo và định danh trả về.
- <code>204</code>: không có response body; kiểm tra status và header.
- <code>400</code>: đọc chi tiết validation hoặc lỗi cú pháp request.
- <code>401</code>: kiểm tra token hoặc thông tin xác thực.
- <code>403</code>: request đã xác thực nhưng không đủ quyền, tùy chính sách server.
- <code>404</code>: kiểm tra path, ID và sự tồn tại của tài nguyên.
- <code>409</code>: kiểm tra xung đột nghiệp vụ hoặc trạng thái dữ liệu.
- <code>5xx</code>: tra log server, gateway và correlation/request ID nếu có.

Swagger UI hiển thị status mà endpoint hoặc thành phần trung gian trả về. Giao diện không tự xác định nguyên nhân nghiệp vụ của lỗi; cần đọc response body và đối chiếu log.

## 5. Đọc Response body và Content-Type

Response body là dữ liệu server thực sự trả về. Ví dụ thành công:

~~~json
{
  "orderId": "ORD-100",
  "status": "CONFIRMED",
  "total": 259900.00,
  "items": []
}
~~~

Đối chiếu body với schema OpenAPI:

- Field bắt buộc có xuất hiện không?
- Kiểu dữ liệu là number, string, boolean, array hay object đúng như schema không?
- Tên field, enum, format và cấu trúc lồng nhau có khớp không?
- Giá trị null hoặc field bị lược bỏ có đúng quy ước không?

Header <code>Content-Type</code> cho biết định dạng body, ví dụ <code>application/json</code>. Nếu operation trả file, văn bản hoặc định dạng khác, nội dung hiển thị có thể khác cách trình bày JSON.

Với response <code>204 No Content</code>, body rỗng là hành vi đúng. Không xem vùng Response body trống là lỗi nếu status và hợp đồng quy định operation không trả nội dung.

Nếu server trả HTML của trang lỗi proxy trong khi OpenAPI mô tả JSON, có thể request đã bị chặn hoặc lỗi ở gateway trước khi vào controller. Hãy kiểm tra Content-Type, status và log ở các thành phần trung gian.

## 6. Đọc Response headers

Response headers cung cấp metadata cho client. Một số header hữu ích:

| Header | Vai trò |
|---|---|
| <code>Content-Type</code> | Định dạng response body |
| <code>Content-Length</code> | Kích thước body nếu được cung cấp |
| <code>Cache-Control</code> | Quy tắc cache |
| <code>ETag</code> | Định danh phiên bản biểu diễn tài nguyên |
| <code>Location</code> | URL tài nguyên mới hoặc đích chuyển hướng, thường gặp ở response tạo mới |
| <code>Retry-After</code> | Gợi ý thời gian chờ trước khi thử lại |
| <code>X-Request-Id</code> | Mã để tra cứu log nếu hệ thống có phát hành |

Không phải mọi header đều xuất hiện trong mọi response. Một số header do gateway hoặc web server thêm vào; một số khác do ứng dụng chủ động trả về.

Khi Swagger UI chạy khác origin với API, JavaScript trong trình duyệt chỉ đọc được các response header được CORS cho phép. Nếu một header tùy chỉnh như <code>X-Request-Id</code> có trong response nhưng không thấy ở giao diện, kiểm tra cấu hình <code>Access-Control-Expose-Headers</code> ở server. Điều này không có nghĩa header chắc chắn không được gửi qua mạng; hãy kiểm tra tab Network để xác nhận.

## 7. Hiển thị thời gian phản hồi

Swagger UI có tùy chọn <code>displayRequestDuration</code> để hiển thị thời gian request. Với springdoc-openapi, có thể bật trong <code>application.yml</code>:

~~~yaml
springdoc:
  swagger-ui:
    displayRequestDuration: true
~~~

Sau khi khởi động lại hoặc nạp lại cấu hình ứng dụng, thực hiện operation bằng Try it out. Giao diện sẽ hiển thị thời gian request bên cạnh thông tin response theo cách trình bày của phiên bản Swagger UI đang dùng.

Nếu muốn cấu hình bằng properties:

~~~properties
springdoc.swagger-ui.displayRequestDuration=true
~~~

Thời gian này là phép đo ở phía giao diện/client trong quá trình gửi request và nhận response. Nó có thể bao gồm:

- Thời gian trình duyệt chuẩn bị và gửi request.
- Độ trễ mạng giữa trình duyệt, proxy/gateway và server.
- Thời gian xử lý tại các thành phần trung gian.
- Thời gian server xử lý và tạo response.
- Thời gian nhận dữ liệu phản hồi về trình duyệt.

Vì vậy, không nên đồng nhất con số này với thời gian CPU hoặc thời gian xử lý nội bộ của controller. Nếu cần phân tích hiệu năng server, hãy kết hợp metric, tracing và log phía backend.

### 7.1. Phân biệt các loại thời gian

| Số đo | Nơi đo | Thường phản ánh |
|---|---|---|
| Request duration trên Swagger UI | Trình duyệt | Thời gian client quan sát từ lúc gửi đến lúc nhận phản hồi |
| Server request duration | Backend hoặc web server | Thời gian server xử lý request theo điểm đo của hệ thống |
| Database query time | Tầng dữ liệu | Thời gian truy vấn cơ sở dữ liệu |
| Distributed trace span | Mỗi dịch vụ/thành phần | Thời gian và quan hệ giữa các bước trong request |

Ví dụ, Swagger UI báo 850 ms trong khi metric controller báo 120 ms. Phần chênh lệch có thể nằm ở mạng, gateway, xác thực, serialization hoặc các bước trước/sau controller. Cần dùng tracing để xác định chính xác thay vì suy luận từ một con số.

### 7.2. So sánh thời gian một cách có ý nghĩa

Khi so sánh hai lần gọi, giữ điều kiện gần giống nhau:

- Cùng endpoint, method và server.
- Cùng payload và kích thước dữ liệu.
- Cùng trạng thái xác thực và quyền.
- Cùng môi trường và điều kiện mạng.
- Ghi nhận nhiều lần thay vì kết luận từ một request.

Request đầu tiên có thể chịu ảnh hưởng của khởi tạo ứng dụng, cache lạnh hoặc kết nối chưa được tái sử dụng. Không lấy một lần đo duy nhất để kết luận hiệu năng đã cải thiện hay suy giảm.

## 8. Ví dụ cấu hình và cách đọc một lần gọi hoàn chỉnh

Giả sử API trả chi tiết đơn hàng:

~~~java
import java.math.BigDecimal;
import java.util.List;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping("/{orderId}")
    ResponseEntity<OrderResponse> getOrder(
            @PathVariable("orderId") String orderId,
            @RequestParam(name = "includeItems", defaultValue = "false")
            boolean includeItems) {

        OrderResponse response = new OrderResponse(
            orderId,
            "CONFIRMED",
            new BigDecimal("259900.00"),
            includeItems ? List.of("SKU-100") : List.of()
        );
        return ResponseEntity.ok(response);
    }
}

record OrderResponse(
    String orderId,
    String status,
    BigDecimal total,
    List<String> items
) {}
~~~

Sau khi mở <code>GET /api/orders/{orderId}</code>:

1. Nhấn Try it out.
2. Nhập <code>orderId = ORD-100</code>.
3. Đặt <code>includeItems = false</code>.
4. Nhấn Execute.

Một kết quả minh họa có thể gồm:

~~~text
Request URL
http://localhost:8080/api/orders/ORD-100?includeItems=false

Server response
Code: 200

Response body
{
  "orderId": "ORD-100",
  "status": "CONFIRMED",
  "total": 259900.00,
  "items": []
}

Response headers
content-type: application/json
~~~

Swagger UI cũng cung cấp cURL tương ứng và thời gian phản hồi nếu đã bật <code>displayRequestDuration</code>. Đây là kết quả minh họa; URL, body, header và thời gian thực tế phụ thuộc ứng dụng đang chạy.

## 9. Tái hiện lỗi bằng cURL

Giả sử Swagger UI nhận <code>404</code> cho một mã đơn hàng. Hãy sao chép cURL, chạy lại trong terminal và giữ nguyên method, URL, query, header cùng body. Sau đó:

1. So sánh status và response body giữa Swagger UI và terminal.
2. Nếu cả hai cùng lỗi, kiểm tra endpoint, dữ liệu và log server.
3. Nếu chỉ Swagger UI lỗi, kiểm tra CORS, cookie, token, server URL và browser Network.
4. Nếu cURL trả response khác, đối chiếu header và thông tin xác thực đã gửi.
5. Nếu response có request ID, dùng mã đó để tìm log liên quan.

Khi chia sẻ kết quả lỗi, nên ghi method, URL đã ẩn thông tin nhạy cảm, status, response body đã loại bỏ dữ liệu cá nhân và request ID. Không gửi access token, cookie phiên hoặc dữ liệu khách hàng trong ảnh chụp hay log công khai.

## 10. Một số trường hợp cần chú ý

**Request có query parameter.** Kiểm tra query xuất hiện trong Request URL và cURL; lưu ý phân biệt tham số vắng mặt với tham số có giá trị rỗng.

**Request có JSON body.** Kiểm tra cURL chứa Content-Type và body đúng schema. Nếu server trả <code>400</code>, xem chi tiết field lỗi và kiểu JSON.

**Request có file upload.** Kiểm tra media type <code>multipart/form-data</code>, tên field file và các form field khác. Trình duyệt tự tạo multipart boundary; không tự đặt một Content-Type thiếu boundary khi tái hiện bằng cURL.

**Response tải file.** Kiểm tra status, <code>Content-Type</code>, <code>Content-Disposition</code> và hành vi tải xuống. Giao diện có thể không trình bày nội dung nhị phân như JSON.

**Response không có body.** Với <code>204</code>, vùng body trống là bình thường.

**Không thấy response headers tùy chỉnh.** Nếu gọi cross-origin, kiểm tra CORS expose headers và xác minh trong Network.

**Không thấy thời gian phản hồi.** Kiểm tra <code>springdoc.swagger-ui.displayRequestDuration</code>, cấu hình thực tế được nạp và phiên bản Swagger UI đi kèm.

## 11. Lỗi thường gặp

**Request URL trỏ sai server.** Chọn đúng server trong Swagger UI và kiểm tra cấu hình <code>servers</code>, context path cùng reverse proxy.

**cURL chạy khác kết quả trên Swagger UI.** Đối chiếu token, cookie, header, body và URL. cURL được sinh ra không nhất thiết chứa toàn bộ header trình duyệt tự thêm.

**Response body không khớp schema.** Kiểm tra DTO, Jackson serializer/deserializer, content negotiation và exception handler; sau đó cập nhật tài liệu hoặc implementation.

**Có status nhưng không có body.** Kiểm tra status có phải <code>204</code> hay response vốn không có content không. Nếu status là lỗi, xem response headers và log server.

**Không đọc được header tùy chỉnh trên giao diện.** Kiểm tra <code>Access-Control-Expose-Headers</code> khi request cross-origin.

**Thời gian phản hồi cao hơn thời gian server log.** Hai số đo có điểm bắt đầu/kết thúc khác nhau. Dùng metric và distributed tracing để tìm phần thời gian chênh lệch.

**Dùng thời gian của một request để đánh giá hiệu năng.** Chạy nhiều lần trong điều kiện ổn định và dùng công cụ benchmark phù hợp khi cần kiểm thử tải.

## 12. Danh sách rà soát sau mỗi lần Execute

- [ ] Request URL trỏ đúng server, path và query parameter.
- [ ] Method, header và request body đúng với hợp đồng.
- [ ] cURL có thể dùng để tái hiện request sau khi bổ sung thông tin cần thiết.
- [ ] HTTP status khớp với tình huống mong đợi.
- [ ] Response body và Content-Type khớp schema.
- [ ] Response headers quan trọng đã được kiểm tra.
- [ ] Thời gian phản hồi được hiểu là số đo phía client.
- [ ] Khi lỗi, đã đối chiếu cURL, Network, request ID và log server.
- [ ] Thông tin xác thực và dữ liệu nhạy cảm đã được che trước khi chia sẻ.

## Tài liệu tham khảo

- [Swagger UI – Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/): các tùy chọn giao diện, gồm hiển thị thời gian request.
- [springdoc-openapi – Properties](https://springdoc.org/properties.html): cấu hình <code>springdoc.swagger-ui</code>.
- [Swagger UI – Usage](https://swagger.io/docs/open-source-tools/swagger-ui/usage/overview/): đọc operation và sử dụng Try it out.
- [curl – Manual](https://curl.se/docs/manpage.html): cú pháp method, header, body và các tùy chọn request.
- [MDN – HTTP Messages](https://developer.mozilla.org/en-US/docs/Web/HTTP/Messages): cấu trúc request và response HTTP.
- [MDN – CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS): quyền truy cập response header từ trình duyệt khi gọi cross-origin.
