# 413, 414, 416 cho giới hạn kích thước và phạm vi dữ liệu

## 1. Bài toán: ba kiểu giới hạn khác nhau của REST API

Giả sử một hệ thống quản lý tài liệu cung cấp ba tính năng:

1. **Tải tệp lên:** người dùng gửi một tệp 50 MiB, trong khi API chỉ chấp nhận tối đa 20 MiB cho mỗi tệp.
2. **Tra cứu tài liệu:** ứng dụng ghép hàng nghìn mã tài liệu vào một URL GET khiến request target vượt giới hạn của gateway.
3. **Tải tiếp tệp bị gián đoạn:** trình tải xuống yêu cầu phần byte bắt đầu từ vị trí 10.000, nhưng tệp hiện tại chỉ có 8.000 byte.

Ba lỗi có vẻ cùng liên quan đến “kích thước”, nhưng nằm ở **ba phần khác nhau của thông điệp HTTP**. Phản hồi đúng lần lượt là những ứng viên điển hình cho **413 Content Too Large**, **414 URI Too Long** và **416 Range Not Satisfiable**.

Trong module **INTEGRATION_API_REST**, đây là những mã cần nắm khi thiết kế URI, phương thức HTTP, hợp đồng dữ liệu, phân trang, tải tệp, cache/validator, xử lý lỗi và kiểm thử bằng Java/Spring hoặc công nghệ tương đương. Chọn sai mã có thể khiến HTTP client thử lại vô ích, hiển thị sai hướng dẫn, hoặc làm hỏng quá trình tải dữ liệu.

### Kết quả học tập

Sau bài này, bạn có thể:

- Phân biệt chính xác 413, 414 và 416 theo **thành phần request gây lỗi** và ngữ nghĩa HTTP.
- Biết khi nào nên dùng **413** cho request content vượt giới hạn, cùng chính sách giới hạn upload nhiều lớp.
- Thiết kế URI, query parameters, phân trang và cơ chế tìm kiếm để tránh **414**.
- Xử lý **Range**, **Content-Range**, **206 Partial Content**, **200 OK** và **416** đúng khi tải từng phần.
- Giải thích vai trò của **ETag/If-Range** khi tệp thay đổi giữa các lần tải.
- Triển khai phản hồi lỗi, cấu hình kích thước và kiểm thử HTTP trên Java/Spring.
- Thiết kế thông báo lỗi, hành vi client và giám sát để bảo vệ hệ thống trước request quá lớn hoặc range bất thường.

## 2. Bản đồ nhanh: mã nào dành cho vấn đề nào?

| Mã | Tên theo HTTP Semantics | Điều đang vượt giới hạn hoặc không thỏa | Ví dụ |
|---|---|---|---|
| **413** | **Content Too Large** (tên cũ thường gặp: Payload Too Large) | **Nội dung request** lớn hơn mức server sẵn sàng hoặc có thể xử lý | POST upload body 50 MiB vượt mức 20 MiB |
| **414** | **URI Too Long** | **Target URI** dài hơn mức server sẵn sàng diễn giải | GET với hàng nghìn ID nối trong query string |
| **416** | **Range Not Satisfiable** | **Tập byte range yêu cầu** không thỏa được trên biểu diễn đã chọn, hoặc bị từ chối vì quá nhiều range nhỏ/chồng lấn | GET Range: bytes=10000- khi tệp chỉ dài 8000 byte |

Sơ đồ quyết định ở mức logic:

~~~mermaid
flowchart TD
    R[Nhận HTTP request] --> U{Target URI quá dài?}
    U -->|Có| E414[414 URI Too Long]
    U -->|Không| B{Request content quá lớn?}
    B -->|Có| E413[413 Content Too Large]
    B -->|Không| G{GET có Range cần xử lý?}
    G -->|Không| N[Xử lý request bình thường]
    G -->|Có| V{Range phù hợp và có thể phục vụ?}
    V -->|Có| P206[206 Partial Content]
    V -->|Không có byte khả dụng hoặc Range bị từ chối| E416[416 Range Not Satisfiable]
    V -->|Bỏ qua Range theo HTTP| P200[200 OK với toàn bộ biểu diễn]
~~~

Sơ đồ là **cách phân biệt nguyên nhân**, không bắt buộc server đánh giá mọi điều kiện theo thứ tự này. Proxy có thể chặn 414 hoặc 413 trước khi request đến ứng dụng; server có thể bỏ qua Range và trả 200 trong các trường hợp HTTP cho phép. Một request không hợp lệ còn có thể cần mã khác như 400, 401, 403, 404, 415, 422 hoặc 431 tùy nguyên nhân thực.

## 3. Mã 413 Content Too Large

### 3.1. Ngữ nghĩa và tình huống sử dụng

Theo **RFC 9110**, 413 cho biết server từ chối xử lý request vì **request content** lớn hơn giới hạn server sẵn sàng hoặc có thể xử lý. Tên **Content Too Large** thay thế cách gọi **Payload Too Large** trong các tài liệu/thư viện cũ; cùng là mã số **413**.

Các tình huống thực tế:

- POST multipart upload vượt giới hạn mỗi file hoặc tổng multipart request.
- PUT gửi toàn bộ biểu diễn tài nguyên quá lớn.
- PATCH chứa tài liệu cập nhật khổng lồ, ví dụ hàng trăm nghìn thao tác.
- POST gửi JSON, XML, CSV hoặc request body nén mà server không thể xử lý an toàn theo chính sách.
- Gateway/WAF loại bỏ request vượt giới hạn nội dung trước khi chuyển đến service.

Ví dụ:

~~~http
POST /documents HTTP/1.1
Host: api.example.test
Content-Type: application/octet-stream
Content-Length: 52428800
Authorization: Bearer <access-token>

... 50 MiB dữ liệu ...
~~~

Khi giới hạn cho endpoint là 20 MiB:

~~~http
HTTP/1.1 413 Content Too Large
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/request-too-large",
  "title": "Content Too Large",
  "status": 413,
  "detail": "Tệp vượt giới hạn 20 MiB cho mỗi lần tải lên.",
  "limitBytes": 20971520
}
~~~

Đây là một ví dụ dùng **Problem Details** (RFC 9457). Thuộc tính mở rộng **limitBytes** là quy ước của API ví dụ, không phải trường bắt buộc của HTTP. Chỉ công bố giới hạn mà client có thể sử dụng hợp lệ; không đưa đường dẫn máy chủ, stack trace hoặc cấu hình nội bộ nhạy cảm vào thông báo.

### 3.2. Vì sao không chỉ kiểm tra Content-Length?

**Content-Length**, nếu có, giúp server/gateway phát hiện sớm request lớn hơn giới hạn. Tuy nhiên, không phải mọi request đều có độ dài biết trước; dữ liệu có thể được truyền bằng streaming hoặc theo framing khác tùy phiên bản HTTP.

Do đó server cần:

1. Từ chối sớm nếu metadata đủ tin cậy cho thấy request vượt giới hạn.
2. **Đếm byte thực nhận** khi body được stream, chặn khi vượt mức cho phép.
3. Kiểm soát cả **kích thước sau giải nén/giải mã**, số phần tử, độ sâu JSON và mức tiêu thụ CPU/bộ nhớ khi xử lý nội dung.
4. Xóa phần dữ liệu tạm và giải phóng tài nguyên nếu từ chối giữa chừng.

Ví dụ, một file nén nhỏ có thể giải nén thành lượng dữ liệu lớn. Giới hạn 20 MiB trên đường truyền không ngăn được tình huống giải nén vượt bộ nhớ. API phải phân biệt **giới hạn byte request** với **quota dữ liệu sau xử lý** và **giới hạn tài nguyên tính toán**.

### 3.3. 413 có thể đi kèm Retry-After

Nếu tình trạng vượt ngưỡng có tính **tạm thời**, server **có thể** gửi **Retry-After** để nói khi nào client có thể thử lại. Chẳng hạn chính sách tạm giảm khả năng nhận tệp trong một khoảng thời gian:

~~~http
HTTP/1.1 413 Content Too Large
Retry-After: 120
Content-Type: application/problem+json

{"title":"Content Too Large","status":413,"detail":"Tạm thời không nhận nội dung ở kích thước này."}
~~~

**Không thêm Retry-After cho giới hạn cố định chỉ để client gửi lại nguyên request.** Nếu file 50 MiB nhưng API chỉ hỗ trợ tối đa 20 MiB, đợi hai phút không làm tệp nhỏ đi. Client nên thông báo giới hạn, nén/chia nhỏ theo hợp đồng hoặc chọn quy trình upload thích hợp.

Server có thể **đóng kết nối** hoặc từ chối trước khi đọc xong toàn bộ body nhằm tránh tiêu tốn tài nguyên; do đó client có thể không nhận được JSON lỗi trong mọi trường hợp. Cần kiểm thử hành vi tại gateway, reverse proxy, server và thư viện HTTP.

### 3.4. Phân biệt 413 với các mã dễ nhầm

| Tình huống | Mã thường phù hợp | Lý do |
|---|---|---|
| Body hoặc file vượt giới hạn nhận | **413** | Kích thước request content |
| Body có cú pháp JSON sai | **400** | Cấu trúc request sai |
| Media type không được hỗ trợ | **415** | Content-Type không phù hợp |
| Dữ liệu hợp lệ về cú pháp nhưng vi phạm quy tắc nghiệp vụ | **422** hoặc mã được hợp đồng quy định | Sai ngữ nghĩa dữ liệu, không phải vượt giới hạn content |
| Tenant đã hết **quota lưu trữ** theo gói | **403, 409, 422** hoặc mã theo hợp đồng/quy tắc hệ thống | Đây là quota nghiệp vụ; không tự đồng nhất với request body quá lớn |
| Gửi quá nhiều request trong một khoảng thời gian | **429** | Rate limit, không phải độ lớn body |
| Server không còn dung lượng lưu trữ để hoàn tất yêu cầu | **507 Insufficient Storage** trong ngữ cảnh phù hợp | Không giống việc server chủ động đặt giới hạn body |
| Header Cookie hoặc Authorization quá lớn | **431 Request Header Fields Too Large** khi được hỗ trợ | Vấn đề nằm ở header, không phải body |

Độ lớn file và **quota người dùng** có thể cùng làm request bị từ chối, nhưng nên trả mã và error code đúng với điều kiện bị vi phạm để client biết cần giảm kích thước hay nâng quyền/gói.

## 4. Thiết kế giới hạn upload ở nhiều lớp

### 4.1. Chặn sớm, bảo vệ sâu và tránh giới hạn mâu thuẫn

Một request thường đi qua nhiều thành phần:

~~~mermaid
flowchart LR
    C[Client] --> G[CDN / WAF / API Gateway]
    G --> P[Reverse Proxy]
    P --> A[Java / Spring API]
    A --> T[Temporary Storage / Parser]
    T --> S[Object Storage]
~~~

| Lớp | Việc cần kiểm soát | Rủi ro nếu bỏ qua |
|---|---|---|
| CDN/WAF/Gateway | Body limit, thời gian upload, request rate | Request quá lớn tiêu thụ băng thông và connection |
| Reverse proxy | Buffering/streaming, body limit, timeout | Gateway chấp nhận nhưng proxy từ chối; upload lỗi không nhất quán |
| Spring/Servlet | Multipart file size, total request size, validation | File quá lớn được tải vào bộ nhớ hoặc đĩa tạm |
| Parser | Kích thước sau giải nén, độ sâu JSON, số phần | Request nhỏ gây quá tải CPU/memory |
| Application domain | Giới hạn từng loại tài liệu, quyền, số bản ghi, quota | Lưu được dữ liệu trái hợp đồng |
| Storage | Kích thước object, virus scan nếu áp dụng, lifetime file tạm | Tệp không hợp lệ hoặc file tạm bị bỏ quên |

Nếu gateway chặn 10 MiB mà tài liệu OpenAPI nói endpoint cho phép 20 MiB, client sẽ không bao giờ đạt được hợp đồng đã công bố. Hãy kiểm thử **đường đi thực tế** từ Internet, qua các proxy, đến API; cấu hình logic và tổng giới hạn nên có mối quan hệ rõ ràng.

### 4.2. Cấu hình Spring Boot cho multipart

Ví dụ Spring Boot sử dụng Servlet stack:

~~~yaml
spring:
  servlet:
    multipart:
      max-file-size: 20MB
      max-request-size: 24MB
~~~

- **max-file-size:** giới hạn một file riêng lẻ.
- **max-request-size:** giới hạn toàn multipart request, gồm nhiều file và các phần form.

Đơn vị cấu hình **MB** tuân theo cách Spring Boot diễn giải DataSize; khi trao đổi với client, nên công bố giá trị byte hoặc đơn vị rõ ràng, ví dụ 20 MiB = 20 × 1.048.576 = 20.971.520 byte. Hai thuộc tính trên **không phải giới hạn chung cho mọi JSON body** và không thay thế cấu hình gateway hay parser. Với WebFlux hoặc một server khác, cơ chế cấu hình có thể khác.

### 4.3. Trả 413 có cấu trúc từ Spring MVC

Trong Spring Framework 6, có thể dùng **ProblemDetail**:

~~~java
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.multipart.MaxUploadSizeExceededException;

@RestControllerAdvice
class UploadErrorHandler {

    @ExceptionHandler(MaxUploadSizeExceededException.class)
    ResponseEntity<ProblemDetail> handle(MaxUploadSizeExceededException ex) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatusCode.valueOf(413),
            "Tệp hoặc tổng request vượt giới hạn upload cho phép."
        );
        problem.setTitle("Content Too Large");
        return ResponseEntity.status(413).body(problem);
    }
}
~~~

Đây là ví dụ cho lỗi **multipart** được đưa vào tầng MVC. Một request bị **WAF/proxy/container từ chối trước khi vào Spring Controller** sẽ không đi qua handler này; cần cấu hình phản hồi 413 và quan sát tại lớp đó. Với upload dạng raw stream hoặc JSON, phải áp dụng giới hạn riêng phù hợp.

### 4.4. Khi file lớn là một nghiệp vụ hợp lệ

Nếu khách hàng cần upload video hoặc bản sao dữ liệu lớn, tăng body limit của mọi REST endpoint không nhất thiết là lựa chọn tốt. Một thiết kế khác:

1. POST tạo **upload session** có xác thực, quota, loại nội dung, kích thước dự kiến và thời gian hết hạn.
2. API cấp quyền upload trực tiếp vào object storage theo phạm vi hẹp, hoặc hỗ trợ từng chunk đã giới hạn.
3. Client gửi từng phần theo cơ chế được hệ thống/storage hỗ trợ, có checksum và khả năng tiếp tục khi mất kết nối.
4. API xác minh các phần, số byte thực tế, quyền, trạng thái quét và quota trước khi hoàn tất tài nguyên.
5. Tác vụ lỗi/hết hạn được dọn dẹp; một upload session không được hoàn tất hoặc tính phí nhiều lần do retry.

**Upload nhiều phần** giải quyết vấn đề truyền file lớn, nhưng không loại bỏ yêu cầu chống lạm dụng, tính toàn vẹn, quota và quyền. Cũng không được mặc định cách ghép nhiều request PATCH/PUT thành một upload session là tính năng có sẵn trong HTTP; mỗi API phải định nghĩa hợp đồng riêng.

## 5. Mã 414 URI Too Long

### 5.1. URI quá dài là gì?

**414 URI Too Long** cho biết server không muốn diễn giải **target URI** vì nó dài hơn mức server sẵn sàng xử lý. Tình huống hay gặp:

- Client đưa danh sách rất nhiều ID vào query string của GET.
- Hệ thống encode một tài liệu JSON lớn vào URL thay vì dùng request content khi phù hợp.
- Redirect hoặc rewrite sai khiến URL liên tục nối thêm tham số.
- Client sinh URL bất thường, có thể do lỗi hoặc hành vi cố ý gây quá tải.

Ví dụ:

~~~http
GET /orders?ids=1001,1002,1003,...(hàng chục nghìn ID)... HTTP/1.1
Host: api.example.test
~~~

Phản hồi:

~~~http
HTTP/1.1 414 URI Too Long
Content-Type: application/problem+json

{
  "title": "URI Too Long",
  "status": 414,
  "detail": "Bộ lọc truy vấn đã vượt độ dài URI cho phép. Hãy thu hẹp điều kiện lọc."
}
~~~

**HTTP không áp đặt một giới hạn URI duy nhất cho mọi server.** Giới hạn thực tế phụ thuộc browser, client library, proxy, gateway, web server, phiên bản HTTP và cách đếm byte/ký tự. Do đó không nên viết “URI luôn tối đa 2.048 ký tự” như một quy tắc HTTP. Hãy đo giới hạn thấp nhất trên tuyến thật và thiết kế URL có kích thước hợp lý.

### 5.2. Cách thiết kế REST API tránh 414

| Vấn đề | Phương án thiết kế |
|---|---|
| GET danh sách hàng nghìn ID | Chia batch có giới hạn hoặc cung cấp thao tác batch thích hợp |
| GET một tập rất lớn | Dùng **pagination/cursor** với trang vừa đủ thay vì mã hóa mọi ID trên URL |
| Bộ lọc rất phức tạp | Rút gọn filter; nếu thực sự cần body lớn, thiết kế **POST /searches** hoặc **POST /reports** với hợp đồng rõ |
| URL chứa trạng thái UI dài | Chỉ đưa bộ lọc/tùy chọn cần thiết hoặc dùng saved search ID |
| Redirect loop làm URL tăng dần | Sửa logic redirect/rewrite; không chỉ tăng giới hạn server |
| GET dựa trên dữ liệu nhạy cảm trong query | Đánh giá việc URI bị lưu trong logs/history; thiết kế cơ chế an toàn hơn |

Ví dụ tạo một báo cáo tìm kiếm phức tạp:

~~~http
POST /report-jobs HTTP/1.1
Content-Type: application/json

{
  "filters": {
    "regions": ["north", "central", "south"],
    "orderStatus": ["paid", "shipped"],
    "dateFrom": "2026-01-01",
    "dateTo": "2026-06-30"
  }
}
~~~

Server có thể tạo resource đại diện tác vụ báo cáo và trả **201 Created** cùng Location, hoặc chấp nhận xử lý bất đồng bộ và trả **202 Accepted** theo hợp đồng. Đây là **thay đổi mô hình API có chủ đích**, không phải chuyển mọi GET thành POST chỉ để vượt lỗi 414. GET vẫn phù hợp cho truy vấn an toàn, có URL ngắn, hỗ trợ cache và chia sẻ đường dẫn.

### 5.3. 414 khác 413 và 431

Đưa bộ lọc lớn từ URI sang **request body** có thể tránh 414 nhưng lại gặp **413** nếu body vượt giới hạn. Đồng thời:

- **414:** vấn đề là target URI, thường gồm path và query.
- **431:** vấn đề là kích thước một hoặc nhiều **request header fields**, ví dụ Cookie hoặc Authorization quá dài.
- **413:** vấn đề là **request content**, không phải header hay URI.

Với HTTP/2 hoặc HTTP/3, biểu diễn wire-level của request target khác HTTP/1.1; máy chủ hoặc gateway vẫn áp dụng giới hạn URI theo chính sách. Mã lỗi thực tế của từng tầng có thể khác nhau khi request vượt ngưỡng nội bộ, nên cần kiểm chứng end-to-end.

## 6. Mã 416 Range Not Satisfiable

### 6.1. Range là gì và vì sao có 416?

Khi tải một file hoặc một biểu diễn tài nguyên lớn, client có thể yêu cầu **một phần byte** bằng header **Range**:

~~~http
GET /files/file-123 HTTP/1.1
Host: api.example.test
Range: bytes=0-99
~~~

Nếu resource dài 1.000 byte, server hỗ trợ range và chấp nhận yêu cầu, phản hồi điển hình:

~~~http
HTTP/1.1 206 Partial Content
Content-Type: application/octet-stream
Accept-Ranges: bytes
Content-Range: bytes 0-99/1000
Content-Length: 100

... 100 byte đầu của tệp ...
~~~

Các số có nghĩa:

- **bytes**: đơn vị phạm vi là byte.
- **0-99**: chỉ số byte bắt đầu và kết thúc, **đánh số từ 0 và gồm cả hai đầu**.
- **/1000**: tổng chiều dài của biểu diễn đang được phục vụ là 1.000 byte.
- **Content-Length: 100**: số byte thực truyền trong response 206 này.

Nếu client yêu cầu:

~~~http
GET /files/file-123 HTTP/1.1
Range: bytes=1000-
~~~

Với tổng chiều dài 1.000 byte, chỉ số cuối cùng hợp lệ là **999**; từ 1000 trở đi không có byte để trả. Server có thể phản hồi:

~~~http
HTTP/1.1 416 Range Not Satisfiable
Content-Range: bytes */1000
Content-Type: application/problem+json

{
  "title": "Range Not Satisfiable",
  "status": 416,
  "detail": "Phạm vi yêu cầu nằm ngoài độ dài biểu diễn hiện tại."
}
~~~

Đối với **416**, **Content-Range: bytes */1000** cho biết **chiều dài biểu diễn được chọn**, không phải chiều dài JSON Problem Details trong response. Khi biết chiều dài, server **nên** gửi Content-Range dạng này để client nhận biết trạng thái file hiện tại.

### 6.2. Cách xác định byte range thỏa được

Giả sử biểu diễn hiện tại có **1.000 byte**, các vị trí hợp lệ là 0 đến 999:

| Range request | Độ dài/ý nghĩa | Phản hồi thường gặp khi server hỗ trợ Range |
|---|---|---|
| **bytes=0-99** | 100 byte đầu | 206, Content-Range: bytes 0-99/1000 |
| **bytes=900-** | Byte 900 đến cuối | 206, bytes 900-999/1000 |
| **bytes=-100** | 100 byte cuối | 206, bytes 900-999/1000 |
| **bytes=0-2000** | Bắt đầu ở 0 và đi quá cuối | **206**, trả byte 0-999; không tự động là 416 |
| **bytes=-2000** | Yêu cầu tối đa 2.000 byte cuối | **206**, trả toàn bộ 1.000 byte |
| **bytes=999-** | Chỉ còn một byte cuối | 206, bytes 999-999/1000 |
| **bytes=1000-** | Không có byte bắt đầu 1000 | **416** nếu server từ chối range không thỏa |
| **bytes=1200-1400** | Toàn bộ nằm ngoài biểu diễn | **416** nếu không có range khác thỏa |

Một hiểu nhầm phổ biến: **end lớn hơn kích thước tài nguyên không nhất thiết gây 416**. Nếu **start còn hợp lệ**, server có thể thu hẹp end về byte cuối. Với tài nguyên **0 byte**, không có byte để trả theo byte range có ý nghĩa, nên yêu cầu như **bytes=0-0** không thỏa.

### 6.3. Các điểm đặc biệt của Range

- **Range** được định nghĩa để thay đổi ngữ nghĩa của **GET**; server phải bỏ qua Range đối với phương thức không phải GET.
- Khi không hỗ trợ hoặc quyết định bỏ qua Range, server có thể trả **200 OK với toàn bộ biểu diễn** thay vì 206/416.
- Nếu request hỏi nhiều range hợp lệ, server có thể trả **206** dạng **multipart/byteranges**, từng phần có Content-Range riêng. Client phải xử lý ranh giới và thứ tự từng phần đúng.
- Server có thể từ chối tập range quá nhiều đoạn nhỏ hoặc chồng lấn bất thường như một biện pháp chống lạm dụng; **416** là một phản hồi có thể phù hợp trong trường hợp này.
- Nếu Range có đơn vị không hiểu được hoặc cú pháp không được hỗ trợ, server có thể bỏ qua Range; **không mặc định trả 416 cho mọi Range sai cú pháp**.

Ví dụ Header **Accept-Ranges: bytes** cho biết server quảng bá hỗ trợ byte range. **Accept-Ranges: none** thể hiện không hỗ trợ, nhưng việc header vắng mặt không nhất thiết chứng minh server không hỗ trợ. Quan trọng nhất là client phải xử lý cả **200**, **206** và **416**.

### 6.4. Byte range áp dụng cho biểu diễn đã được chọn

Byte offsets là các byte của **selected representation**. Nếu server dùng content coding như gzip, byte range có thể áp dụng cho biểu diễn sau mã hóa thay vì chuỗi byte file gốc, tùy representation được chọn. Khi xây dựng resume download:

- Dùng validator và content negotiation nhất quán.
- Tránh ghép byte từ hai representation khác nhau do thay đổi Content-Encoding, phiên bản hoặc chuyển đổi nội dung.
- Đo Content-Length, Content-Range và ETag trên đúng representation đang truyền.

Nếu server hỗ trợ range không chính xác hoặc thay đổi encoding giữa các lần tải, file nối lại có thể bị hỏng dù mọi response có mã 2xx.

## 7. Tệp thay đổi khi tải tiếp: ETag và If-Range

Một client tải 400 byte đầu của file phiên bản **v1**, rồi mất kết nối. Trong lúc đó file được thay bằng **v2**. Nếu client tải tiếp bằng **Range: bytes=400-** mà không kiểm tra phiên bản, nó có thể ghép 400 byte đầu của v1 với phần còn lại của v2.

### 7.1. If-Range giúp tải tiếp đúng phiên bản

Client lưu **strong ETag** trong response gốc:

~~~http
HTTP/1.1 200 OK
ETag: "file-v1"
Accept-Ranges: bytes
Content-Length: 1000
~~~

Khi tải tiếp, client gửi:

~~~http
GET /files/file-123 HTTP/1.1
Range: bytes=400-
If-Range: "file-v1"
~~~

- Nếu validator vẫn khớp và Range thỏa, server có thể trả **206 Partial Content** với byte 400 đến cuối.
- Nếu file đã đổi thành v2 và **If-Range không khớp**, server **bỏ qua Range**, trả **200 OK** với toàn bộ representation mới. Client cần bỏ phần tải dở của v1 và bắt đầu lại theo v2.
- Nếu validator khớp nhưng range đã không thỏa, server có thể trả **416** với Content-Range phù hợp để client đối chiếu độ dài.

**If-Range không giống If-Match**: If-Match thường bảo vệ cập nhật có điều kiện, còn If-Range nói “chỉ gửi một phần nếu phiên bản vẫn như tôi có; nếu khác, gửi toàn bộ”. Client không dùng **weak ETag** làm validator của If-Range.

### 7.2. Quy trình resume download an toàn

~~~mermaid
flowchart TD
    S[Tải file và lưu ETag] --> I[Gián đoạn sau N byte]
    I --> REQ[GET với Range bytes=N- và If-Range]
    REQ --> CODE{HTTP status?}
    CODE -->|206| VERIFY[Kiểm tra Content-Range, validator, byte count]
    VERIFY --> APPEND[Ghép phần tiếp theo vào file tạm]
    CODE -->|200| RESTART[Bỏ phần cũ, tải lại representation mới]
    CODE -->|416| CHECK[Đọc Content-Range */length; kiểm tra file hiện tại]
    CHECK --> RESYNC[HEAD/GET lại hoặc xác minh checksum rồi quyết định]
~~~

Không xem **416** là tín hiệu “download hoàn tất” một cách tự động. File cục bộ có thể đã hoàn tất, nhưng cũng có thể chứa dữ liệu phiên bản cũ, sai offset, bị rút ngắn hoặc bị hỏng. Cần kiểm tra ETag, tổng chiều dài, checksum nếu có và trạng thái thực tế trước khi đánh dấu thành công.

## 8. Ranh giới của 416: không dùng để báo lỗi phân trang thông thường

REST API thường có nhiều cách đọc “một phần dữ liệu”. Cần phân biệt:

| Cơ chế | Ví dụ | Kết quả mong đợi |
|---|---|---|
| HTTP Range cho byte của một representation | GET /files/x với Range: bytes=1000- | 206 nếu thỏa; 416 nếu phạm vi bị từ chối vì không thỏa hoặc lạm dụng |
| Phân trang query parameter | GET /orders?page=200&pageSize=20 | Thường 200 với danh sách trống và metadata, hoặc lỗi theo contract; **không tự gán 416** |
| Cursor pagination | GET /orders?cursor=abc | Cursor hết hạn/không hợp lệ được xử lý theo hợp đồng API, thường là lỗi client phù hợp |
| Tìm kiếm có lọc | GET /orders?status=paid | 200 với kết quả tìm được, kể cả danh sách trống |
| Download một đoạn bằng endpoint riêng | GET /files/x/chunks/10 | Mã lỗi phụ thuộc hợp đồng resource; không tự suy 416 nếu không dùng ngữ nghĩa HTTP Range |

**416 gắn với header Range và hệ thống range units của HTTP**, không phải một mã chung cho “page không tồn tại” hoặc “index ngoài mảng” trong mọi API. Nếu API dùng custom range unit thay vì bytes, phải định nghĩa và quảng bá cơ chế đó nhất quán; không tự dùng cú pháp Content-Range: bytes khi đơn vị thực sự là bản ghi hay trang.

## 9. Triển khai download từng phần trong Java/Spring

Ví dụ sau dùng Spring MVC và **StreamingResponseBody** để trình bày những bước cốt lõi của một endpoint download. Nó chủ động chỉ **hỗ trợ một byte range có dạng bytes=start-end hoặc bytes=start-**; khi client gửi dạng range khác như suffix range, nhiều range hoặc đơn vị khác, ví dụ **bỏ qua Range và trả 200**. Một dịch vụ production có thể hỗ trợ thêm suffix/multi-range theo nhu cầu.

### 9.1. Luồng quyết định ở server

1. Xác thực client và phân quyền đọc file.
2. Lấy một **snapshot/version bất biến** của biểu diễn, cùng chiều dài và strong ETag.
3. Nếu không có Range hoặc If-Range không khớp, gửi **200** với toàn bộ representation.
4. Nếu Range được hỗ trợ, tính start và end; giới hạn end ở byte cuối hợp lệ.
5. Nếu start ngoài biểu diễn, gửi **416** và Content-Range dạng bytes */length.
6. Nếu còn byte hợp lệ, gửi **206** với Content-Range và đúng Content-Length.
7. Stream đúng đoạn byte từ **cùng một phiên bản file**; không để một lần ghi thay thế file trong lúc stream tạo response lệch với ETag.

### 9.2. Ví dụ controller minh họa

~~~java
import java.io.IOException;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

@RestController
class FileDownloadController {
    private static final Pattern SINGLE_RANGE =
        Pattern.compile("^bytes=(\\d+)-(\\d*)$");

    private final FileStore fileStore;

    FileDownloadController(FileStore fileStore) {
        this.fileStore = fileStore;
    }

    @GetMapping("/files/{id}/content")
    ResponseEntity<StreamingResponseBody> download(
            @PathVariable String id,
            @RequestHeader(name = "Range", required = false) String rangeHeader,
            @RequestHeader(name = "If-Range", required = false) String ifRange
    ) throws IOException {
        // Hàm này phải xác thực và phân quyền theo principal/tenant hiện tại.
        // Snapshot chứa size, strong ETag và versionId bất biến.
        FileSnapshot file = fileStore.openAuthorizedSnapshot(id);
        long total = file.size();
        String etag = file.strongEtag(); // Ví dụ: "\"file-v7\""

        if (rangeHeader == null
                || (ifRange != null && !ifRange.equals(etag))) {
            return full(file, total, etag);
        }

        Matcher matcher = SINGLE_RANGE.matcher(rangeHeader.trim());

        // Range không hỗ trợ: server bỏ qua và gửi toàn bộ representation.
        if (!matcher.matches()) {
            return full(file, total, etag);
        }

        long start;
        long requestedEnd;
        try {
            start = Long.parseLong(matcher.group(1));
            requestedEnd = matcher.group(2).isEmpty()
                ? Long.MAX_VALUE
                : Long.parseLong(matcher.group(2));
        } catch (NumberFormatException invalidOrOverflowedRange) {
            return full(file, total, etag);
        }

        if (start >= total || requestedEnd < start) {
            return ResponseEntity.status(416)
                .header(HttpHeaders.CONTENT_RANGE, "bytes */" + total)
                .header(HttpHeaders.ACCEPT_RANGES, "bytes")
                .eTag(etag)
                .build();
        }

        long end = Math.min(requestedEnd, total - 1);
        long count = end - start + 1;

        StreamingResponseBody partial = output ->
            fileStore.copyRange(file, start, count, output);

        return ResponseEntity.status(206)
            .contentType(MediaType.APPLICATION_OCTET_STREAM)
            .header(HttpHeaders.ACCEPT_RANGES, "bytes")
            .header(
                HttpHeaders.CONTENT_RANGE,
                "bytes " + start + "-" + end + "/" + total
            )
            .contentLength(count)
            .eTag(etag)
            .body(partial);
    }

    private ResponseEntity<StreamingResponseBody> full(
            FileSnapshot file, long total, String etag) {
        StreamingResponseBody body = output ->
            fileStore.copyAll(file, output);

        return ResponseEntity.ok()
            .contentType(MediaType.APPLICATION_OCTET_STREAM)
            .header(HttpHeaders.ACCEPT_RANGES, "bytes")
            .contentLength(total)
            .eTag(etag)
            .body(body);
    }
}

// FileStore và FileSnapshot là abstraction giả định của ứng dụng.
// FileSnapshot phải tham chiếu một version nội dung bất biến.
// FileStore.copyRange(snapshot, start, count, output) ghi đúng count byte.
~~~

**Giới hạn cố ý của ví dụ:**

- Chỉ nhận single byte range bắt đầu bằng vị trí số. **bytes=-100** là một range hợp lệ theo HTTP, nhưng ví dụ chọn trả **200** thay vì cố xử lý nó như byte-range không thỏa.
- Client có thể gửi If-Range bằng HTTP-date; ví dụ chỉ chấp nhận khi giá trị bằng strong ETag đã phát hành. Các dạng khác không khớp và được xử lý như tải lại toàn bộ.
- Ví dụ dùng cách xử lý đơn giản với range không hỗ trợ; production cần giới hạn độ dài/số phần tử Range và kiểm thử đầy đủ để tránh lạm dụng tài nguyên.
- Ví dụ chưa thể hiện các cơ chế range multipart, Content-Disposition, caching, authentication, conditional GET như If-None-Match, và error mapping nếu tệp biến mất. Những hành vi đó phải bổ sung theo hợp đồng.
- **FileStore** cần mở đúng version được gắn ETag và có hỗ trợ stream/bounded read; không nạp toàn bộ file lớn vào bộ nhớ và cắt mảng nếu workload lớn.
- Mọi thao tác xác thực, kiểm tra quyền, authorization theo tenant, hạn mức tải và audit phải được thực hiện trước khi trả stream.

Điều quan trọng nhất không nằm ở cú pháp Java mà ở **tính nhất quán giữa header và byte thực truyền**. Trả Content-Range: bytes 0-99/1000 nhưng thực tế gửi 101 byte là lỗi giao thức và có thể làm hỏng file phía client.

### 9.3. Không nên phát sinh 416 từ business exception chung

Ví dụ, controller tải tệp không nên dùng cùng một handler cho “không có file”, “không có quyền” và “range không thỏa” rồi trả 416 cho tất cả:

- Không có file theo URI có thể cần **404**, tùy chính sách che giấu tài nguyên.
- Người dùng không được xem file có thể cần **403** hoặc 404 để tránh lộ tồn tại tài nguyên theo chính sách.
- File tồn tại, client được phép đọc nhưng byte range không thỏa mới là tình huống **416** tương ứng.

Tương tự, một controller nhận upload không nên chuyển mọi lỗi dung lượng lưu trữ thành 413; phải xét lỗi đang nằm ở giới hạn body, quota hay sự cố storage.

## 10. Thiết kế hợp đồng API và Problem Details

### 10.1. Hợp đồng cần nói rõ điều gì?

Đối với endpoint upload:

- Loại request body và media type được hỗ trợ.
- Giới hạn **mỗi file**, **tổng request**, kích thước sau giải nén và quota nghiệp vụ nếu có.
- 413 sẽ được trả ở gateway hay application; có giới hạn khác theo gói/tenant không.
- Có hỗ trợ chunked/multipart/resumable upload hay không, và cách client phục hồi khi mất kết nối.

Đối với endpoint tìm kiếm:

- URI và query parameter, độ dài/batch size tối đa được hợp đồng chấp nhận.
- Chiến lược phân trang/cursor và endpoint cho filter phức tạp.
- Cách trả **414**, kèm thông báo hành động để client thu nhỏ request.

Đối với endpoint download:

- Có hỗ trợ **Range: bytes** hay không, dạng nào được hỗ trợ, có multi-range không.
- Khi nào trả **200**, **206**, **416**; các header **Accept-Ranges, Content-Range, ETag, If-Range**.
- Định nghĩa resource version hoặc checksum để resume an toàn.

### 10.2. Mẫu mô tả OpenAPI rút gọn

Ví dụ OpenAPI 3.x:

~~~yaml
paths:
  /documents:
    post:
      summary: Tải lên một tài liệu
      description: >
        Giới hạn mỗi file 20 MiB; tổng request 24 MiB.
        File lớn hơn phải dùng quy trình upload session.
      requestBody:
        required: true
        content:
          multipart/form-data:
            schema:
              type: object
              properties:
                file:
                  type: string
                  format: binary
              required: [file]
      responses:
        "201":
          description: Đã tạo tài liệu
        "413":
          description: Request content vượt giới hạn cho phép
          content:
            application/problem+json:
              schema:
                type: object
                properties:
                  title: {type: string}
                  status: {type: integer}
                  detail: {type: string}

  /documents/{id}/content:
    get:
      summary: Tải file, có thể tải từng byte range
      parameters:
        - name: id
          in: path
          required: true
          schema: {type: string}
        - name: Range
          in: header
          required: false
          description: "Ví dụ: bytes=0-1023"
          schema: {type: string}
        - name: If-Range
          in: header
          required: false
          description: Strong ETag của representation đã tải một phần
          schema: {type: string}
      responses:
        "200":
          description: Toàn bộ representation
        "206":
          description: Một phần byte hợp lệ
          headers:
            Content-Range:
              schema: {type: string}
              description: "Ví dụ: bytes 0-1023/10000"
        "416":
          description: Byte range không thỏa hoặc bị từ chối
          headers:
            Content-Range:
              schema: {type: string}
              description: "Ví dụ: bytes */10000"
~~~

Đoạn mẫu tập trung vào phạm vi nội dung bài học; trong tài liệu production cần khai báo thêm **security schemes, schemas, media types đầy đủ, response bodies, error codes, example và chính sách cache**. OpenAPI có thể mô tả giới hạn, nhưng **không tự cấu hình** gateway hay Spring để thực thi.

### 10.3. Lỗi nào có thể trả Problem Details?

413 và 414 thường có thể trả **application/problem+json** rõ ràng khi request đã đi tới lớp tạo response. Đối với 416, body Problem Details cũng có thể hữu ích, nhưng client download thường cần **Content-Range** để đối chiếu dữ liệu đang có. Vì vậy không nên chỉ nhìn JSON body rồi bỏ qua header.

Một lỗi API nên có **mã ứng dụng ổn định** bên cạnh HTTP status nếu cần định danh lý do cụ thể, ví dụ **UPLOAD_FILE_TOO_LARGE**, **URI_FILTER_TOO_LONG**, **DOWNLOAD_RANGE_UNSATISFIABLE**. Tên mã này là hợp đồng ứng dụng, không phải status HTTP mới. Tránh ghi thông tin nhạy cảm trong detail và cấu hình lỗi.

## 11. Chiến lược của client khi nhận 413, 414 hoặc 416

Ba mã này không nên được xử lý bằng cùng một vòng retry:

| Mã nhận được | Hành vi client phù hợp | Điều không nên làm |
|---|---|---|
| **413** | Hiển thị giới hạn; giảm kích thước, chọn file khác, nén/chunk nếu API hỗ trợ; chỉ đợi khi server chỉ ra đây là giới hạn tạm thời | Retry vô hạn nguyên request quá lớn |
| **414** | Thu gọn filter/ID list, phân trang/batch, sửa redirect loop, dùng endpoint search/job khi contract cho phép | Chỉ tăng timeout hoặc retry cùng URL |
| **416** | Kiểm tra Content-Range, ETag, offset; tải lại metadata, resume đúng phiên bản hoặc tải lại từ đầu | Coi 416 đương nhiên là file đã tải xong |

### 11.1. Ví dụ client resume download

~~~text
downloadedBytes = kích thước file tạm đang lưu
savedEtag = strong ETag của representation ban đầu

GET /files/file-123
Range: bytes=<downloadedBytes>-
If-Range: <savedEtag>

switch response.status:
  206:
    xác minh Content-Range.start == downloadedBytes
    xác minh version/ETag và tổng kích thước phù hợp
    append đúng byte; cập nhật offset
  200:
    thay file tạm bằng nội dung representation mới
    lưu ETag mới, kiểm tra checksum nếu có
  416:
    lấy chiều dài hiện tại từ Content-Range nếu có
    so sánh offset, strong ETag, checksum
    GET/HEAD lại hoặc restart có kiểm soát
  khác:
    áp dụng chính sách xử lý lỗi theo HTTP status
~~~

Đây là giả mã. Trong ứng dụng thật, client còn phải xử lý mất kết nối giữa chừng, partial write vào disk, response Content-Encoding, ETag thiếu, nội dung trả về khác với nội dung kỳ vọng và khả năng dữ liệu bị thay đổi trong lúc tải.

### 11.2. Retry/backoff không sửa được request sai

Exponential backoff và jitter hữu ích cho lỗi **tạm thời** hoặc **rate limiting**, nhưng thường không giải quyết được:

- 413 do giới hạn body cố định.
- 414 do URI dài hơn giới hạn cố định.
- 416 do offset không khớp kích thước file hiện tại.

Client cần **thay đổi request hoặc trạng thái local** theo ý nghĩa mã lỗi. Không retry đồng thời hàng trăm file không thể tải lên; điều này vừa không thành công vừa làm tăng áp lực gateway.

## 12. Bảo mật, hiệu năng và quan sát vận hành

### 12.1. Request lớn là rủi ro tài nguyên

Các giới hạn kích thước không chỉ là yêu cầu UX; chúng bảo vệ CPU, memory, disk, băng thông, connection slots và chi phí:

- Upload quá lớn có thể chiếm connection, file tạm, memory buffer và storage.
- JSON/XML quá sâu hoặc nhiều phần tử có thể làm parser tiêu thụ tài nguyên bất thường.
- URI rất dài có thể gây áp lực lên parser, logging, router và hệ thống lưu dấu vết.
- Range nhiều đoạn nhỏ/chồng lấn có thể làm server đọc đĩa nhiều lần hoặc tạo response multipart tốn kém.

Biện pháp thích hợp gồm **byte limit, streaming, timeout, quota, rate limit, request complexity limit, queue admission control, WAF rules phù hợp, giới hạn concurrency và cô lập tài nguyên**. Các kiểm soát không loại trừ nhau.

### 12.2. Bảo mật dữ liệu khi báo lỗi

Để tránh rò thông tin:

- Không ghi raw Authorization, Cookie, signed URL, token hoặc toàn bộ query nhạy cảm vào log chỉ vì request có lỗi 414.
- Không trả đường dẫn filesystem, tên bucket nội bộ, stack trace hoặc chi tiết reverse proxy không cần thiết trong Problem Details.
- Xác thực và phân quyền download trước khi cung cấp nội dung hoặc thông tin nhạy cảm về file.
- Áp dụng giới hạn theo tenant/account/client để tránh một bên tiêu thụ tài nguyên của bên khác.
- Kiểm tra nội dung upload bằng quy trình an toàn phù hợp với nghiệp vụ, kể cả khi kích thước nằm dưới giới hạn.

### 12.3. Metric và log nên thu thập

| Tín hiệu | Phân tích |
|---|---|
| Số 413 theo route, gateway, tenant/gói | Giới hạn cấu hình quá thấp hay client upload sai? |
| Số 414 theo route và client version | Query quá dài do app, UI hoặc redirect loop? |
| Số 416 theo resource type, client version | Resume offset sai, cache validator lỗi hay tệp thay đổi thường xuyên? |
| Request body bytes, file bytes, decode size | Có sự chênh lệch giữa wire size và processed size? |
| Target URI length (không lưu query nhạy cảm) | URL gần ngưỡng trước khi lỗi? |
| Số byte range và response bytes | Range requests có tạo thêm I/O hoặc bị lạm dụng? |
| Upload duration, failure stage, temporary file bytes | Lỗi xảy ra ở gateway, parser hay storage? |
| Resume success rate, checksum mismatch | Client ghép file đúng phiên bản hay không? |

Một dashboard chỉ hiển thị tổng HTTP 4xx chưa đủ. Cần phân biệt **lỗi do hợp đồng client** và **lỗi do giới hạn gateway/ứng dụng không nhất quán**. Chỉ số cần đi kèm route, tầng phát lỗi, release của client và trace/correlation ID khi phù hợp; tránh nhãn metric có cardinality quá lớn.

## 13. Ma trận kiểm thử tích hợp cho ba mã trạng thái

Một REST API có thể trả status đúng trong unit test nhưng lỗi khi chạy qua gateway hoặc CDN. Vì vậy cần kiểm tra **cả tầng ứng dụng lẫn luồng thực tế từ client**.

| Test case | Đầu vào | Kết quả cần xác nhận |
|---|---|---|
| Upload dưới giới hạn | Tệp nhỏ hơn max-file-size | Thành công theo contract, lưu đúng byte và metadata |
| Upload đúng ngưỡng | Tệp bằng kích thước tối đa đã công bố | Xử lý đúng biên byte; không từ chối vì nhầm đơn vị |
| Upload vượt ngưỡng một file | Tệp lớn hơn max-file-size | 413 ở tầng phù hợp, không lưu dữ liệu dở dang |
| Tổng multipart vượt ngưỡng | Nhiều tệp hợp lệ riêng nhưng tổng body quá lớn | 413 theo max-request-size |
| Upload stream không có chiều dài biết trước | Body tăng dần vượt giới hạn | Chặn trong lúc nhận, giải phóng tài nguyên |
| Dữ liệu nén bất thường | Body nhỏ nhưng giải nén lớn | Parser/storage được bảo vệ bằng giới hạn phù hợp |
| URI gần ngưỡng | GET query có độ dài tiệm cận giới hạn | Hợp đồng được đáp ứng, không lỗi do config lệch |
| URI vượt ngưỡng | Query rất dài | 414 tại lớp được cấu hình; không bị hiểu thành 413 |
| Header riêng quá lớn | Cookie/Authorization quá dài | Kiểm tra hành vi 431/giới hạn của stack; không nhầm 414 |
| Range hợp lệ | bytes=0-99 với file 1.000 byte | 206, 100 byte, Content-Range đúng |
| Range end vượt cuối | bytes=0-2000 với file 1.000 byte | 206 trả 0-999, không tự động 416 |
| Range start bằng chiều dài | bytes=1000- với file 1.000 byte | 416, Content-Range bytes */1000 nếu có chiều dài |
| Range suffix hợp lệ | bytes=-100 | 206 khi hỗ trợ suffix hoặc 200 nếu server chủ động bỏ qua Range |
| File rỗng | bytes=0-0 với file 0 byte | 416 nếu xử lý Range và không có byte thỏa |
| Range không hỗ trợ | Đơn vị Range khác hoặc nhiều range khi API chỉ hỗ trợ đơn range | Hành vi ignore/response được tài liệu hóa; client xử lý 200 |
| Tệp thay đổi | If-Range chứa ETag cũ | 200 với bản mới thay vì ghép sai file |
| Resume thành công | If-Range khớp, start hợp lệ | 206, byte nối tiếp đúng, checksum cuối đúng |
| Range lạm dụng | Nhiều đoạn nhỏ/chồng lấn bất thường | Giới hạn tài nguyên, không gây quá tải hoặc lộ dữ liệu |
| 413 do proxy | Body bị từ chối trước Spring MVC | Quan sát được 413 và lý do tại proxy; tài liệu không mâu thuẫn |

### 13.1. Ví dụ kiểm tra MockMvc

Với controller download hỗ trợ Range, một số kiểm tra có thể viết:

~~~java
mockMvc.perform(get("/files/{id}/content", "file-123")
        .header("Range", "bytes=0-99"))
    .andExpect(status().isPartialContent())
    .andExpect(header().string(
        "Content-Range", "bytes 0-99/1000"
    ))
    .andExpect(header().string(
        "Content-Length", "100"
    ));

mockMvc.perform(get("/files/{id}/content", "file-123")
        .header("Range", "bytes=1000-"))
    .andExpect(status().isRequestedRangeNotSatisfiable())
    .andExpect(header().string(
        "Content-Range", "bytes */1000"
    ));

mockMvc.perform(get("/files/{id}/content", "file-123")
        .header("Range", "bytes=0-2000"))
    .andExpect(status().isPartialContent())
    .andExpect(header().string(
        "Content-Range", "bytes 0-999/1000"
    ));
~~~

Ví dụ giả định **file-123** có đúng 1.000 byte và test fixture cung cấp principal đủ quyền. Với StreamingResponseBody, cần **kiểm tra cả phần async dispatch và byte thực nhận** theo cách cấu hình Spring MVC/MockMvc của dự án; chỉ assert header/status chưa chứng minh rằng body stream được ghi đúng.

Ví dụ test 413 multipart:

~~~java
MockMultipartFile largeFile = new MockMultipartFile(
    "file",
    "large.bin",
    "application/octet-stream",
    new byte[21 * 1024 * 1024]
);

mockMvc.perform(multipart("/documents")
        .file(largeFile))
    .andExpect(status().isPayloadTooLarge());
~~~

**Lưu ý:** Một test MockMvc thuần túy có thể không đi qua cùng **multipart resolver/container/gateway size limit** như request HTTP thực. Vì vậy kết quả của đoạn test là minh họa cho hợp đồng endpoint; hãy bổ sung **integration test chạy với embedded server và cấu hình thực tế**, đặc biệt ở biên 20 MiB/24 MiB. Tên helper kiểm tra status có thể khác theo phiên bản Spring; nếu không có helper phù hợp, dùng **status().is(413)**.

Với 414, gửi URI thực sự qua gateway/web server đang dùng để kiểm tra ngưỡng; gọi controller trực tiếp hoặc MockMvc có thể không kích hoạt lớp giới hạn URI thật.

## 14. Case study: API lưu trữ và chia sẻ tài liệu

### 14.1. Bối cảnh

Một nền tảng nội bộ tên **DocFlow** có ba endpoint:

- **POST /documents:** tải file dưới dạng multipart, giới hạn mỗi file 20 MiB, tổng request 24 MiB.
- **GET /documents:** tìm kiếm tài liệu theo trạng thái, người tạo, nhãn và phân trang.
- **GET /documents/{id}/content:** tải file, hỗ trợ single byte range và strong ETag.

Giả sử user có quyền truy cập tất cả tài liệu trong các ví dụ dưới đây. Backend là Spring Boot, đặt sau API gateway. Đối với file lớn, hệ thống có thêm quy trình upload session vào object storage.

### 14.2. Tình huống A: tải file 80 MiB lên endpoint thường

**Request:** user upload file 80 MiB bằng POST /documents.

**Phân tích:** nội dung request vượt max-file-size và max-request-size đã công bố. Gateway hoặc ứng dụng có thể từ chối. Mã phù hợp là **413**; không dùng 414 vì URI không hề quá dài và không dùng 416 vì đây không phải Range download.

**Hành động hợp lý:**

1. Trả thông báo file vượt 20 MiB, ưu tiên thông tin công bố trong hợp đồng.
2. Gợi ý client dùng upload session/từng phần nếu có quyền và API hỗ trợ.
3. Đảm bảo file tạm bị dọn và không tạo document resource ở trạng thái “thành công nửa chừng”.
4. Theo dõi xem lỗi 413 phát sinh ở gateway hay ứng dụng để tránh giới hạn không thống nhất.

### 14.3. Tình huống B: URL GET chứa 12.000 ID

**Request:** ứng dụng web nối 12.000 ID vào query của GET /documents, tạo URL dài.

**Phân tích:** vấn đề chính nằm ở **target URI**. Nếu vượt giới hạn mà gateway sẵn sàng diễn giải, có thể nhận **414**. Việc tăng timeout hay số lần retry không làm URL ngắn hơn.

**Hành động hợp lý:**

1. Xác định vì sao UI muốn truy xuất 12.000 ID một lần: hiển thị danh sách, export hay cập nhật hàng loạt.
2. Với màn hình danh sách, chuyển sang **pagination** và bộ lọc đủ chọn lọc.
3. Với export dữ liệu lớn, cân nhắc tạo **report/export job** bằng POST rồi tải kết quả khi hoàn tất.
4. Nếu thực sự cần đọc theo danh sách ID, quy định batch size hoặc endpoint phù hợp; không mặc định nhồi dữ liệu vào URL.
5. Không log toàn bộ URL chứa token hoặc dữ liệu nhạy cảm chỉ để điều tra 414.

### 14.4. Tình huống C: tải tiếp với offset cũ

Một file ban đầu dài 10.000 byte. Client tải được 8.000 byte và lưu ETag v2. Sau đó người sở hữu thay file bằng bản dài 6.000 byte với ETag v3. Client gửi:

~~~http
GET /documents/d-100/content HTTP/1.1
Range: bytes=8000-
If-Range: "v2"
~~~

**Nhận định quan trọng:** Vì **If-Range không khớp** phiên bản v3, server đúng chuẩn nên **bỏ qua Range và trả 200 với toàn bộ bản mới**. Không nên trả 416 chỉ vì start=8000 vượt file mới: điều kiện If-Range đã yêu cầu tải toàn bộ representation khi phiên bản thay đổi.

Nếu client **không gửi If-Range** và server xử lý Range trên bản dài 6.000 byte, yêu cầu bytes=8000- **không thỏa**; server có thể trả:

~~~http
HTTP/1.1 416 Range Not Satisfiable
Content-Range: bytes */6000
ETag: "v3"
~~~

Lúc đó client nên kiểm tra phiên bản và tải lại từ đầu thay vì ghép 6.000 byte mới với 8.000 byte đã tải ở v2.

### 14.5. Bảng quyết định của DocFlow

| Request | Nguyên nhân thực | Kết quả / hướng khắc phục |
|---|---|---|
| POST 80 MiB, giới hạn 20 MiB | Request content quá lớn | 413; chọn upload session hoặc giảm file |
| GET chứa 12.000 ID, URI vượt ngưỡng | Target URI quá dài | 414; dùng batch, pagination hoặc export job |
| GET Range bytes=8000- cho file 6.000 byte, không có If-Range | Byte range không thỏa | 416, Content-Range bytes */6000 |
| GET Range bytes=8000- và If-Range v2, file đã sang v3 | Validator không khớp | 200 với toàn bộ bản v3 |
| GET Range bytes=0-9999 cho file 6.000 byte | Start hợp lệ, end vượt cuối | 206 với byte 0-5999 nếu server hỗ trợ range |
| GET /documents?page=99999, không có dữ liệu | Trang kết quả trống | Theo contract phân trang, thường 200 với items rỗng; không tự dùng 416 |

## 15. Bài thực hành và câu hỏi tự kiểm tra

### Bài 1: Gán status phù hợp

Một API có các tình huống:

1. Body JSON 15 MiB trong khi gateway chỉ chấp nhận 5 MiB.
2. Query URL chứa 50.000 phần tử và vượt độ dài URI cho phép.
3. GET Range: bytes=300-400 cho file hiện tại dài 200 byte.
4. GET Range: bytes=150-300 cho file dài 200 byte.
5. GET Range: bytes=0-0 cho file rỗng.
6. Người dùng đã gửi 2.000 request trong một phút, vượt rate limit nhưng request body chỉ 1 KiB.
7. Header Cookie vượt giới hạn header của gateway.
8. GET /orders?page=100 trong danh sách chỉ có 3 trang.

**Yêu cầu:** Với mỗi tình huống, nêu mã thích hợp hoặc các khả năng chuẩn HTTP cho phép, và giải thích vì sao.

**Gợi ý đáp án:**

| Tình huống | Kết quả hợp lý |
|---|---|
| 1 | **413** vì request content quá lớn |
| 2 | **414** vì target URI quá dài |
| 3 | **416** khi server xử lý Range; Content-Range bytes */200 |
| 4 | **206** với Content-Range bytes 150-199/200 nếu server hỗ trợ range; điểm cuối được cắt về 199 |
| 5 | **416** nếu xử lý byte range, vì file không có byte nào |
| 6 | **429**, lỗi tốc độ chứ không phải kích thước |
| 7 | **431** nếu stack hỗ trợ và dùng mã này; không phải 413/414 chỉ vì header dài |
| 8 | Không tự dùng 416; thường **200** với danh sách trống hoặc hành vi khác được contract phân trang quy định |

### Bài 2: Sửa lỗi tải xuống

Một mobile client thực hiện:

~~~text
GET /files/archive.zip
Range: bytes=1048576-

Response: 416
Content-Range: bytes */524288
~~~

Client hiện đang có file tạm 1.048.576 byte. Hãy trả lời:

1. Số byte của file trên server hiện tại là bao nhiêu?
2. Vì sao range start không thỏa?
3. Có được tự động coi file tạm là bản hoàn tất không?
4. Client phải lưu và gửi thông tin gì để tránh ghép byte của hai phiên bản?

**Gợi ý:** Server báo biểu diễn hiện tại dài 524.288 byte, nên byte 1.048.576 nằm ngoài phạm vi. Không thể coi file local đã hoàn tất; nó có thể thuộc phiên bản cũ. Client nên xác minh strong ETag/If-Range, tổng chiều dài, checksum nếu có và tải lại đúng phiên bản.

### Bài 3: Thiết kế giới hạn upload

Yêu cầu nghiệp vụ của một API:

- File ảnh tối đa 8 MiB.
- File PDF tối đa 20 MiB.
- Một request multipart có thể gửi nhiều file, tổng tối đa 24 MiB.
- Người dùng Enterprise có thể upload tài liệu lớn qua một upload session riêng.

Hãy đề xuất:

1. Giới hạn chung ở gateway và giới hạn riêng theo loại file ở application.
2. Cách trả 413 nhất quán, có mô tả giới hạn theo endpoint/loại file.
3. Cách đảm bảo không lưu file tạm khi upload bị từ chối.
4. Quy trình upload session và cách xác minh byte/kiểm tra dữ liệu khi finalize.
5. Test đúng ngưỡng, vượt ngưỡng 1 byte, request nhiều file, upload streaming và body nén.

**Gợi ý:** Có thể đặt giới hạn tổng request 24 MiB hoặc nhỉnh hơn nếu cần overhead multipart, sau đó kiểm tra giới hạn từng file theo loại tại application. Giá trị gateway phải phản ánh **byte thực** và overhead của request. Upload session phải kiểm tra lại kích thước thực, quyền, quota và tính toàn vẹn ở bước hoàn tất. Không dựa vào Content-Length hoặc phần mở rộng tên file như chứng cứ duy nhất về nội dung.

### Bài 4: Tự kiểm tra khái niệm

Trả lời đúng/sai và giải thích:

1. “HTTP quy định mọi URL tối đa 2.048 ký tự”.
2. “Range: bytes=0-2000 cho file 1.000 byte chắc chắn trả 416”.
3. “Một 416 luôn có nghĩa server không hỗ trợ Range”.
4. “413 có thể được phát ra trước khi request đến controller”.
5. “416 có thể giúp phát hiện offset tải tiếp đã lỗi thời”.
6. “Thêm Retry-After vào 413 luôn giúp client upload thành công sau khi đợi”.

**Đáp án:** 1 Sai (không có một giới hạn chung như vậy); 2 Sai (có thể trả 206 cho byte 0-999); 3 Sai (server có thể hỗ trợ Range nhưng range cụ thể không thỏa); 4 Đúng (gateway/proxy/container có thể chặn sớm); 5 Đúng (cần kiểm tra lại validator và chiều dài); 6 Sai (chỉ có ích trong tình huống giới hạn tạm thời, không giúp file vượt giới hạn cố định).

## 16. Sai lầm thường gặp và quy tắc ghi nhớ

| Sai lầm | Cách sửa |
|---|---|
| Thấy “too large” thì trả 413 cho mọi thứ | Xác định thứ quá lớn: **request content → 413**, **target URI → 414**, **header → có thể 431** |
| Thấy “vượt phạm vi” thì trả 416 cho page/cursor | **416** thuộc cơ chế HTTP **Range**, không phải lỗi phân trang tổng quát |
| End byte vượt cuối file thì luôn 416 | Nếu start hợp lệ, có thể cắt end về byte cuối và trả **206** |
| Client chỉ hỗ trợ 206 khi gửi Range | Server có thể bỏ qua Range và trả **200** |
| 416 nghĩa là tải file đã hoàn tất | Phải đối chiếu ETag, kích thước, checksum và phiên bản |
| Cấu hình multipart của Spring bảo vệ mọi request | JSON/raw body, proxy và parser có giới hạn khác |
| Dùng GET với URL cực dài thay cho mô hình query hợp lý | Thiết kế phân trang/batch hoặc endpoint search/job theo ngữ nghĩa |
| Retry mọi 413/414/416 với exponential backoff | Thay đổi kích thước, URI hoặc offset/validator trước khi retry |
| Trả 413 từ handler Spring là đủ | Proxy/gateway có thể chặn request trước khi tới ứng dụng |
| Tắt mọi giới hạn để khách hàng gửi file lớn | Dùng streaming/upload session và kiểm soát quota, chi phí, an toàn dữ liệu |

**Quy tắc ba câu hỏi:**

1. **Client gửi nội dung quá lớn?** Nghĩ đến **413**.
2. **Client yêu cầu bằng một URI quá dài?** Nghĩ đến **414**.
3. **Client yêu cầu byte range mà representation không đáp ứng?** Nghĩ đến **416**, đồng thời kiểm tra **200/206, Content-Range, ETag và If-Range**.

### Tài liệu chuẩn để đối chiếu

- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): định nghĩa 413, 414, 416, Range Requests, Content-Range và các validator.
- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111): cache behavior và các cân nhắc về representation.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): cấu trúc body lỗi application/problem+json.
- [Spring Boot — Multipart Support](https://docs.spring.io/spring-boot/reference/web/servlet.html#web.servlet.spring-mvc.multipart): các giới hạn multipart trên Servlet stack.

Việc chọn đúng 413, 414 hay 416 giúp API thể hiện **nguyên nhân lỗi có thể hành động được**: giảm hoặc chia nội dung, thiết kế lại URI, hay đồng bộ lại byte range và phiên bản tài nguyên. Kết hợp mã HTTP chuẩn với hợp đồng REST rõ, kiểm soát tài nguyên nhiều lớp và kiểm thử qua tuyến mạng thật sẽ giúp ứng dụng Java/Spring vận hành đáng tin cậy khi làm việc với dữ liệu lớn.
