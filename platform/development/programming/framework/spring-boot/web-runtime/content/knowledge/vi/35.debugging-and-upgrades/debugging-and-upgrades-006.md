# 400, 413 hoặc 431 do dữ liệu đầu vào và giới hạn kích thước

## 1. Mục tiêu và triệu chứng cần chẩn đoán

Trong nhóm **Gỡ lỗi và nâng cấp** của **Spring Boot - web-runtime**, nhiều lỗi request được người dùng mô tả giống nhau: “gửi dữ liệu không thành công”. Trên thực tế, một request có thể bị chặn ở proxy, HTTP parser của Tomcat, Spring MVC message converter, Jakarta Bean Validation hoặc trong business code. Ba mã thường gây nhầm lẫn là:

- **400 Bad Request:** cú pháp hoặc nội dung request có vấn đề khiến server không thể hoặc không muốn xử lý, ví dụ JSON không hợp lệ, sai kiểu dữ liệu, ràng buộc đầu vào sai hoặc HTTP request malformed.
- **413 Content Too Large:** **nội dung/body** request vượt mức server có khả năng hoặc được phép xử lý. Tên cũ thường thấy là **413 Payload Too Large**; mã số vẫn là 413.
- **431 Request Header Fields Too Large:** một hay nhiều **request headers** hoặc tổng header section quá lớn; ví dụ Cookie hoặc Authorization dài bất thường.

Điểm mấu chốt: **HTTP status mô tả kết quả nhìn từ client, không tự cho biết component nào từ chối.** Tomcat có thể trả **400** cho header vượt kích thước ở parser, dù 431 là status chuyên biệt; một ingress có thể trả 413 trước khi request tới ứng dụng. Nếu chỉ tìm @ExceptionHandler trong Spring MVC, bạn có thể không thấy gì.

Bài cung cấp:
1. Cách phân biệt 400/413/431 với 414, 415, 422 và lỗi từ gateway.
2. Sơ đồ request đi qua proxy, connector, filters, converter, validation và Controller.
3. Cấu hình thực tế của **Spring Boot 3.3.13 + embedded Tomcat 10.1** và các bẫy khi nâng phiên bản.
4. Một dự án **Java 17 + Spring Boot MVC** chạy được, có đường trả 400/413/431 bằng logic có thể kiểm chứng.
5. Test HTTP thật để phân biệt lỗi do application policy với lỗi do Tomcat header parser hoặc upload parser.
6. Runbook chẩn đoán trong môi trường có NGINX/Ingress/Gateway, cùng checklist bảo mật và kiểm thử giới hạn.

Không dùng các con số demo làm ngưỡng production: phải đo request size thật, quyền riêng tư, năng lực bộ nhớ, proxy và thời gian phục vụ.

## 2. Bản đồ các tầng có thể từ chối request

~~~text
Client (curl, browser, mobile app)
        |
        v
DNS / TLS / WAF / CDN / API Gateway
        |-- header/cookie too large: 400 hoặc 431
        |-- request body too large: 413
        |-- URI quá dài: 414
        |-- rate limit: 429
        |
        v
Ingress / reverse proxy (nếu có)
        |-- header buffers / request-line limits
        |-- body limit / buffering / timeout
        |
        v
Tomcat HTTP Connector (Spring Boot embedded)
        |-- HTTP request line + headers parser
        |-- server.max-http-request-header-size
        |-- maxPostSize cho form parameter parsing
        |-- maxSwallowSize cho upload bị abort
        |
        v
Servlet filters / Spring Security
        |-- authentication / CSRF / custom request limits
        |
        v
DispatcherServlet / Spring MVC
        |-- HandlerMapping: path, method, consumes, produces
        |-- HttpMessageConverter (Jackson JSON)
        |-- MultipartResolver / Servlet Part parser
        |-- @Valid / method validation
        |
        v
Controller / service / domain rules
        |
        v
HTTP 2xx, 4xx, 5xx hoặc connection bị đóng
~~~

**Thứ tự cụ thể phụ thuộc deployment.** Một CDN, WAF hoặc API Gateway có thể ngừng request trước Tomcat. Nếu request chưa vào Spring MVC, **@ControllerAdvice không thể tự đổi status hoặc body** của response đã được proxy/container tạo.

Vì vậy cần phân biệt:
- **Ứng dụng nhận request rồi trả lỗi**: có trace/log của DispatcherServlet hoặc Controller.
- **Connector/parser từ chối trước mapping**: chỉ có Tomcat connector log/error response; Spring MVC handler có thể không được gọi.
- **Ingress/WAF từ chối trước backend**: ứng dụng hoàn toàn không thấy request, dù client nhận HTTP status.
- **Network abort**: client không nhận được HTTP response hoàn chỉnh; có thể thấy connection reset, EOF, timeout hoặc HTTP/2 stream reset.

## 3. Bảng phân biệt 400, 413 và 431 theo ngữ nghĩa HTTP

| Mã | Đối tượng bị giới hạn/sai | Ví dụ | Hướng sửa ban đầu |
| --- | --- | --- | --- |
| **400 Bad Request** | Request malformed hoặc field không hợp lệ | JSON sai cú pháp; quantity=0 khi @Min(1); header có ký tự không hợp lệ | Sửa cú pháp/dữ liệu; tìm tầng báo lỗi |
| **413 Content Too Large** | Request **body/content** lớn hơn policy/capacity | File upload 70 KiB khi max-file-size 64 KiB; body raw quá hạn mức | Giảm body, chunk/upload protocol hoặc thay limits theo policy |
| **431 Request Header Fields Too Large** | Một header hoặc tập headers quá lớn | Cookie tích lũy, JWT trong Authorization rất dài | Giảm header, cookie scope/claims, kiểm proxy limits |
| **414 URI Too Long** | Request-target/path/query quá dài | Đẩy JSON lớn vào GET query string | Giảm URI; chuyển dữ liệu vào body nếu đúng semantics |
| **415 Unsupported Media Type** | Content-Type không được hỗ trợ | Gửi text/plain tới endpoint chỉ nhận JSON | Đặt Content-Type đúng |
| **422 Unprocessable Content** | Body đúng cú pháp/type nhưng không xử lý được theo domain semantics | Quy tắc API tự định nghĩa | Kiểm business rule; không mặc định Bean Validation trả 422 |
| **429 Too Many Requests** | Caller vượt rate limit/quota | API key quá số lần gọi | Backoff/quota, không tăng body/header limit |
| **502/504** | Gateway gặp vấn đề khi trao đổi với upstream | Upstream close hoặc timeout | Xem ingress, proxy và backend tương ứng |

**RFC 9110:** 413 có tên chuẩn hiện hành **Content Too Large**. Nhiều framework, constants và blog cũ vẫn dùng chữ **Payload Too Large**; không phải một mã mới. **RFC 6585** định nghĩa 431. Không suy luận từ status là một yêu cầu cùng loại sẽ luôn sinh cùng error JSON trên mọi server.

### 3.1. Hai request cùng lỗi header có thể ra 400 hoặc 431

Theo HTTP semantics, 431 là mã hữu ích khi header field(s) quá lớn, nhưng **Tomcat HTTP parser có thể trả 400** khi request header buffer đầy. Ở một gateway khác, request tương tự có thể trả 431. Đây là sự khác biệt implementation/layer, không phải bằng chứng body JSON sai.

Nếu ứng dụng tự kiểm một header nhỏ hơn giới hạn Tomcat và chủ động trả 431, status sẽ dự đoán được; còn nếu **vượt giới hạn của Tomcat trước MVC**, controller không có cơ hội trả 431 tùy chỉnh.

### 3.2. Content-Length không phải độ dài header

Ví dụ:

~~~http
POST /api/upload HTTP/1.1
Host: localhost:8080
Content-Type: multipart/form-data; boundary=...
Content-Length: 73000
Cookie: session=...
~~~

- **Content-Length** là một header field, nhưng **giá trị 73000** không làm request header dài 73.000 bytes. Nó mô tả kích thước HTTP body được quảng cáo.
- Nếu body lớn hơn upload limit, có thể bị 413.
- Nếu **Cookie** chứa vài chục kilobytes ký tự, request header section có thể vượt limit và bị 400/431 **trước khi body được đọc**.
- Nếu framing của HTTP message sai, ví dụ Content-Length/Transfer-Encoding bất hợp lệ, HTTP parser có thể trả 400 vì message malformed, không phải 413.

### 3.3. Không phải mọi 400 đều do kích thước

Một JSON body 30 bytes vẫn có thể bị 400 vì thiếu dấu ngoặc, sai kiểu hoặc @Valid không đạt. Một URL 10.000 bytes có thể bị 414 hoặc 400 tại connector; nó không làm body lớn. Khi phân loại sự cố, hãy bắt đầu từ **method, path, headers, body length, Content-Type** và **nơi từ chối**.

## 4. Các nguyên nhân HTTP 400 trong Spring MVC

### 4.1. JSON không hợp lệ về cú pháp

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json

{"item":"book","quantity":2
~~~

Jackson không thể parse JSON chưa đóng dấu ngoặc. Spring MVC thường ném **HttpMessageNotReadableException** và trả 400 qua exception resolution. Controller có thể **chưa được gọi**.

Một trường hợp khác: body đúng cú pháp JSON nhưng không thể deserialize theo type DTO.

~~~json
{"item":"book","quantity":"many"}
~~~

Nếu quantity là Integer, Jackson không thể chuyển "many" thành số. Đây không phải lỗi của @Min; nó xảy ra trước Jakarta Bean Validation.

### 4.2. JSON đúng cú pháp nhưng vi phạm ràng buộc

~~~java
record OrderRequest(
    @NotBlank String item,
    @NotNull @Min(1) @Max(100) Integer quantity
) {}
~~~

Với **@Valid @RequestBody OrderRequest**, payload:

~~~json
{"item":" ","quantity":0}
~~~

có thể bị **MethodArgumentNotValidException**, trả 400 theo Spring MVC defaults. Phải có **spring-boot-starter-validation** để constraints hoạt động như mong đợi trong Boot 3.3.

**@NotBlank** áp cho String; **@NotNull** cấm null; **@Min(1)** không áp cho String như thay thế độ dài; **@Size(max=...)** mới giới hạn String/Collection length. Những annotation này kiểm dữ liệu **sau khi JSON đã được deserialize**, không bảo đảm chống một HTTP body vài trăm megabytes trước lúc parser cấp phát bộ nhớ.

### 4.3. Query/path parameter không hợp lệ

Ví dụ **GET /api/orders?limit=abc** khi controller nhận int limit: conversion failure có thể trả 400. Thiếu @RequestParam bắt buộc cũng có thể trả 400. Trong Spring Framework 6.1, constraints đặt trực tiếp trên MVC handler method như **@Min @RequestParam** có thể tạo **HandlerMethodValidationException** nếu sử dụng built-in method validation.

**Không tự kết luận 400 nào cũng từ @Valid**, và đừng dùng @ExceptionHandler(MethodArgumentNotValidException) làm cách duy nhất kiểm soát mọi input error.

### 4.4. Malformed HTTP headers ở connector

Header chứa ký tự không được phép, request line sai, framing mâu thuẫn hoặc header quá lớn có thể bị Tomcat HTTP parser từ chối **trước Controller**. Một số trường hợp header quá lớn ra 400; đây là lý do phải đọc connector logs, không chỉ search validation errors.

### 4.5. 400 không phải luôn "lỗi người dùng" theo nghĩa business

Một reverse proxy cấu hình sai có thể thêm headers bất hợp lệ hoặc duplicate/conflicting framing làm backend trả 400. Cần kiểm raw request ở các hops mà không tiết lộ token, nhất là khi lỗi chỉ xuất hiện sau deploy hoặc nâng cấp proxy/server.

## 5. HTTP 413: giới hạn nội dung body và upload

**413** nghĩa là server từ chối xử lý nội dung request vì kích thước lớn hơn mức cho phép hoặc khả năng xử lý. Với trường hợp tạm thời, RFC 9110 khuyến nghị cân nhắc **Retry-After** để báo thời điểm có thể thử lại; nhưng nếu payload vượt policy cố định, retry **nguyên payload** thường vô ích.

Những nguồn 413 thường gặp:
- Reverse proxy giới hạn kích thước body.
- API Gateway/WAF có request-size policy.
- Spring multipart parser thấy **một file** vượt max-file-size.
- Tổng multipart request vượt max-request-size, dù từng file còn dưới ngưỡng.
- Application tự giới hạn một raw stream / decoded content.
- Một service xử lý dữ liệu sinh 413 theo contract business.

**Không phải cứ thấy 413 là tăng cấu hình Spring.** Nếu nginx/ingress trả 413 trước khi request tới Tomcat, tăng Spring multipart max-file-size không thay đổi được kết quả.

### 5.1. Spring Boot 3.3 multipart defaults

Theo Spring Boot 3.3:
- **spring.servlet.multipart.enabled=true**.
- **spring.servlet.multipart.max-file-size=1MB**.
- **spring.servlet.multipart.max-request-size=10MB**.
- **spring.servlet.multipart.file-size-threshold=0B**.
- **spring.servlet.multipart.location** là đường dẫn tạm khi cần lưu multipart intermediate.

Ví dụ:

~~~yaml
spring:
  servlet:
    multipart:
      enabled: true
      max-file-size: 64KB
      max-request-size: 128KB
      file-size-threshold: 0B
~~~

Đây là lab; hai giá trị 64KB/128KB cố ý nhỏ để thử lỗi. Nếu tệp **70KiB** vượt max-file-size 64KB, Servlet multipart parser có thể ném lỗi kích thước; Spring Framework có **MaxUploadSizeExceededException** để biểu diễn trường hợp vượt giới hạn. Trong Spring Framework 6.1, exception này implement **ErrorResponse**, có status **413**. Tuy nhiên, kết quả client **vẫn phụ thuộc** xử lý multipart, request body chưa được đọc hết, Tomcat swallow behavior, proxy và network.

### 5.2. Tổng multipart request khác kích thước file

Một multipart request có:
- Bytes của từng file.
- Fields dạng text.
- Boundaries và **per-part headers**.
- Nhiều parts/files.

Vì vậy file 60KiB có thể dưới max-file-size=64KB nhưng toàn request gần hoặc vượt max-request-size=128KB khi có nhiều parts. Kiểm từng file **và** toàn request; đừng chỉ đo kích thước một object MultipartFile đã được nhận.

### 5.3. Tại sao header Content-Length không đủ để bảo vệ body?

Một client có thể dùng **Transfer-Encoding: chunked** trong HTTP/1.1, khi đó Content-Length không có. Ngay cả khi Content-Length có, chỉ tin header mà không kiểm bytes thực nhận là không đủ để thiết kế generic body limit. Proxy có thể decompress/buffer/transform, kích thước trước và sau decode khác nhau.

**Quy tắc:** dùng một lớp kiểm **actual bytes** trong quá trình đọc hoặc cấu hình ingress/server hỗ trợ body limits thật. Không tự tạo filter chỉ đọc Content-Length rồi tuyên bố đã bảo vệ mọi request, đặc biệt với streaming/chunked.

### 5.4. JSON lớn không tự bị giới hạn bởi multipart property

**spring.servlet.multipart.max-request-size** dành cho **multipart**, không phải một upper bound chung cho **application/json**. Một JSON body lớn có thể được Jackson parse và cấp phát bộ nhớ trước khi @Size/@Valid nhận được DTO. Cần body limit ở ingress/API Gateway hoặc ứng dụng có streaming parser/bounded reader phù hợp.

Không có một property Spring Boot 3.3 tên chung "server.max-http-request-body-size" có thể áp đặt cùng semantics cho mọi embedded Servlet server và mọi content type. Dùng đúng setting của server/codec/protocol và kiểm thử từng đường.

## 6. Tomcat maxPostSize, maxSwallowSize và ba giới hạn khác nhau

**Embedded Tomcat 10.1** có các cấu hình cần phân biệt:

| Spring Boot 3.3 property | Default Boot 3.3 | Điều nó kiểm soát |
| --- | --- | --- |
| **server.max-http-request-header-size** | **8KB** | Request line + tổng header names/values đối với Tomcat |
| **server.tomcat.max-http-form-post-size** | **2MB** | Kích thước content dùng để **chuyển request body thành parameters** của form |
| **server.tomcat.max-swallow-size** | **2MB** | Bytes request body tối đa Tomcat sẽ swallow khi upload đã bị abort |
| **spring.servlet.multipart.max-file-size** | **1MB** | Một uploaded file trong multipart |
| **spring.servlet.multipart.max-request-size** | **10MB** | Tổng multipart request |
| **spring.servlet.multipart.file-size-threshold** | **0B** | Ngưỡng multipart contents có thể ghi disk |
| **server.tomcat.max-parameter-count** | Xem đúng build Tomcat/Boot | Số parameters được container parse từ query/form |
| **server.tomcat.max-part-count** | Xem đúng build Tomcat/Boot | Số multipart parts cho phép |
| **server.tomcat.max-part-header-size** | Xem đúng build Tomcat/Boot | Số bytes header riêng của từng multipart part |

**Đừng dùng tài liệu của phiên bản Boot/Tomcat khác để kết luận defaults của production.** Một số defaults như max-part-count/max-parameter-count đã thay đổi qua các releases. Đối chiếu application properties của **3.3.13** và effective runtime cấu hình đang chạy.

### 6.1. max-http-form-post-size KHÔNG phải generic POST-body limit

Tên này dễ bị hiểu là “mọi HTTP POST chỉ được 2MB”. Tài liệu Tomcat nói **maxPostSize** áp dụng khi container chuyển request body thành **request parameters**, chủ yếu với **application/x-www-form-urlencoded** và phần field parameters trong **multipart/form-data**. Nó **không phải** generic size limit cho toàn bộ body JSON và không nhất thiết giới hạn binary upload part giống spring.servlet.multipart.max-file-size.

Nếu gửi **application/json** 3MB, không thể dựa vào max-http-form-post-size=2MB để cam kết 413. Phải cấu hình body limit của proxy/app hoặc đọc streaming có kiểm soát.

### 6.2. max-swallow-size không phải max-upload-size

Khi Tomcat đã biết upload sẽ bị từ chối nhưng client vẫn gửi body, nó có thể **đọc và bỏ đi (swallow)** một lượng bytes để giữ giao thức/kết nối có thể trả response hợp lý. **server.tomcat.max-swallow-size=2MB** giới hạn lượng dữ liệu bị nuốt sau khi request bị abort.

Nếu client tiếp tục gửi phần body rất lớn, Tomcat có thể **đóng connection/reset** và client không quan sát được JSON 413, dù backend đã phát hiện giới hạn. Đặt **max-swallow-size=-1** để đọc không giới hạn có thể tránh một số triệu chứng giao thức nhưng đổi lại tăng rủi ro tiêu tốn bandwidth/CPU; **không dùng như quick fix không kiểm soát**.

**Tách biệt rõ:**
- Multipart max-file-size: có cho phép file này không?
- Multipart max-request-size: có cho phép tổng multipart request không?
- maxSwallowSize: khi body đã bị từ chối, còn đọc/bỏ tối đa bao nhiêu bytes?

### 6.3. Kiểm giới hạn part count/header riêng

Một request có hàng trăm parts rỗng có thể gây tốn RAM/CPU dù tổng bytes ít. Tomcat còn giới hạn số multipart parts, per-part header size và số request parameters. Các giới hạn này khác **HTTP request headers** ở đầu request; đừng nhầm multipart per-part headers với **server.max-http-request-header-size**.

Trong một số trường hợp Tomcat có thể bỏ qua parameters vượt ngưỡng hoặc phản hồi lỗi tùy implementation/filter và config; không hứa mặc định luôn trả 413. Cần test theo runtime thực.

## 7. HTTP 431 và Cookie/Authorization quá lớn

**431 Request Header Fields Too Large** là lỗi header section, không phải lỗi JSON hoặc uploaded file. Những lý do phổ biến:
- Browser tự gửi nhiều Cookie vì app chia nhỏ session data hoặc đặt domain/path quá rộng.
- Token JWT chứa quá nhiều claims/roles, hoặc Authorization có credential dài.
- Proxy thêm nhiều X-Forwarded-* / tracing headers qua chuỗi hops.
- Client gửi rất nhiều header keys (header count).
- Frontend/backend gắn session data vào cookies và không xóa các cookies cũ.
- Gateway và Tomcat có request-header-size policy khác nhau.

### 7.1. Tomcat tính header size như thế nào?

Spring Boot **server.max-http-request-header-size** trên Tomcat áp dụng cho **request line cộng header names, values và bytes phụ trợ như dấu cách/line terminators** theo HTTP parser của Tomcat, không chỉ một header value.

Ví dụ một request có:
- URI/path/query dài.
- Cookie 5KB.
- Authorization 2KB.
- Tracing headers 1KB.
- Host/User-Agent/Accept headers.

Tổng có thể vượt **8KB** dù mỗi header riêng trông không quá lớn. Với HTTP/2, compression và header list semantics khác HTTP/1.1; thiết bị gateway có thể có giới hạn trên **decompressed header list** hoặc count. Đừng dùng kích thước gói trên dây để suy ra chính xác buffer policy của tất cả hops.

### 7.2. 431 không được bảo đảm ở Tomcat

Tài liệu Tomcat về **maxHttpRequestHeaderSize** mô tả giới hạn bytes của request line+headers. Khi vượt giới hạn, Tomcat có thể từ chối ở parser và phát **400 Bad Request**/đóng kết nối theo runtime; controller **không được chạy**, nên một @ExceptionHandler trong MVC không thể tùy chỉnh thành ProblemDetail 431.

Nếu API contract muốn 431 cho một **header nghiệp vụ** như X-Client-Tag, hãy kiểm header đó trong controller/filter **khi request đã được Tomcat chấp nhận**. Lab có cả hai tình huống để làm rõ.

### 7.3. Đừng tăng header limit không giới hạn

Tomcat có thể cấp phát request-header buffer cho nhiều requests đồng thời. Theo tài liệu Tomcat, tăng maxHttpRequestHeaderSize lên **1MB** khi có **100 concurrent requests** có thể dùng khoảng **100MB heap** cho request-header buffers. Tăng từ 8KB lên 1MB để giải quyết một Cookie bị phình to có thể mở thêm bề mặt memory DoS.

**Ưu tiên sửa nguồn tăng size:** loại cookies không cần thiết, thu nhỏ JWT claims, giảm forwarding headers không thiết yếu, dùng server-side session storage hoặc điều chỉnh cookie domain/path. Chỉ tăng limit sau khi đo distribution thực và đặt upper bound hợp lý ở mọi hops.

### 7.4. 431 vs 414

- **431:** header section quá lớn, thường do Cookie/Authorization.
- **414:** request-target/URI quá dài, ví dụ đưa hàng chục KB JSON vào GET query.
- Một connector có thể dùng **400** cho request line quá dài hoặc header buffer overflow.

Không lấy nguyên trạng lỗi “URI quá dài” rồi chỉ tăng header limit. Xem raw **path/query/header sizes** và config cụ thể.

## 8. Khi nâng cấp Spring Boot 2 lên Boot 3

Một bẫy migration liên quan HTTP header size:

- Spring Boot 2 sử dụng property **server.max-http-header-size** (tùy version).
- Spring Boot 3 đưa property thay thế **server.max-http-request-header-size**, nhất quán cho **request headers**.
- Property cũ được deprecate và behavior trước đó khác nhau giữa các embedded servers; không copy cấu hình cũ rồi tin nó vẫn kiểm response headers tương tự.

Spring Boot 3 còn dùng **Jakarta Servlet** namespace (jakarta.servlet.* thay vì javax.servlet.*) và Spring Framework 6. Với custom filters hay multipart handling, code nhập package cũ có thể không biên dịch.

Để debug sau upgrade:
1. Xác định dependency tree: Spring Boot/Tomcat/Servlet phiên bản nào thực sự chạy?
2. So sánh effective configuration và đổi tên properties đúng.
3. Kiểm tối đa header ở **Ingress/API Gateway** trước khi thay server.
4. Test cùng payload/headers ở trước và sau nâng cấp.
5. Xem log Tomcat parser cùng client HTTP status, không chỉ Controller logs.
6. Kiểm maxPostSize/multipart defaults và HTTP/2 connection settings nếu đổi server.
7. Chạy regression tests cho 400/413/431/414, kể cả content-type và error body.

## 9. Lab Spring Boot 3.3.13: định danh rõ 400, 413 và 431

Dự án dưới đây tạo các trường hợp khác nhau nhưng **không đánh đồng lỗi do app với lỗi do Tomcat**.

**Endpoints:**
- **POST /api/items** — JSON DTO có @Valid; body invalid hoặc malformed trả **400**.
- **POST /api/raw** — đọc **tối đa 2.049 bytes** raw request để giới hạn **2.048 bytes**; vượt ngưỡng trả **413** bằng application policy, kể cả khi không có Content-Length.
- **GET /api/header-check** — header X-Client-Tag dài hơn **256 bytes UTF-8** được app chủ động trả **431**.
- **POST /api/upload** — Servlet multipart, giới hạn **64KB/file** và **128KB/request**; lỗi max upload được advice chuyển thành ProblemDetail 413 nếu exception đến MVC handler.
- **GET /api/ping** — endpoint nhỏ để thử khi Tomcat header parser từ chối request trước Controller.

**Đừng nhầm lab:** 431 chủ động từ /api/header-check kiểm **riêng header nghiệp vụ**, còn **server.max-http-request-header-size=8KB** được Tomcat áp cho toàn bộ request header section. Một request X-Client-Tag dài 300 bytes đi vào Controller và nhận 431; một header 12KB có thể bị Tomcat chặn trước Controller với 400.

### 9.1. Cây thư mục

~~~text
request-limits-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/limits/RequestLimitsApplication.java
    │   └── resources/application.yml
    └── test/
        └── java/com/example/limits/RequestLimitsHttpTest.java
~~~

### 9.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>request-limits-lab</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**spring-boot-starter-validation** là dependency cần có cho @NotBlank, @NotNull, @Min/@Max. Trong Boot 3 dùng **jakarta.validation** và **jakarta.servlet**, không dùng javax cho những APIs này.

### 9.3. application.yml

**src/main/resources/application.yml:**

~~~yaml
server:
  port: 8080
  max-http-request-header-size: 8KB
  tomcat:
    max-http-form-post-size: 2MB
    max-swallow-size: 2MB
  error:
    include-message: never
    include-binding-errors: never
    include-stacktrace: never
    include-exception: false

spring:
  mvc:
    problemdetails:
      enabled: true
  servlet:
    multipart:
      enabled: true
      max-file-size: 64KB
      max-request-size: 128KB
      file-size-threshold: 0B
~~~

**Bảng ý nghĩa trong lab:**

| Thuộc tính | Mục tiêu | Nó KHÔNG làm |
| --- | --- | --- |
| server.max-http-request-header-size: 8KB | Tomcat giới hạn request line+headers | Không giới hạn JSON body |
| max-http-form-post-size: 2MB | Giới hạn form parameter parsing | Không là generic max JSON POST |
| max-swallow-size: 2MB | Giới hạn body bị nuốt sau upload abort | Không là max allowed file size |
| max-file-size: 64KB | Giới hạn một multipart uploaded file | Không giới hạn raw octet-stream |
| max-request-size: 128KB | Giới hạn tổng multipart request | Không giới hạn X-Client-Tag |
| spring.mvc.problemdetails.enabled=true | MVC có hỗ trợ ProblemDetail cho framework errors | Không biến mọi Tomcat/proxy error thành problem+json |
| server.error.include-stacktrace=never | Không phát stack trace mặc định cho client | Không thay logging/trace back-end |

**Không có setting “server.max-http-request-body-size”** trong cấu hình này để tự áp dụng cho mọi JSON/raw body. Endpoint /api/raw bên dưới dùng bounded read cụ thể.

### 9.4. Java source đầy đủ

**src/main/java/com/example/limits/RequestLimitsApplication.java:**

~~~java
package com.example.limits;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.multipart.MaxUploadSizeExceededException;
import org.springframework.web.multipart.MultipartFile;

@SpringBootApplication
public class RequestLimitsApplication {
    public static void main(String[] args) {
        SpringApplication.run(RequestLimitsApplication.class, args);
    }
}

record ItemRequest(
        @NotBlank String name,
        @NotNull @Min(1) @Max(100) Integer quantity
) {}

record ItemReply(String name, int quantity) {}

final class Problems {
    private Problems() {}

    static ProblemDetail of(int status, String code, String detail) {
        ProblemDetail body = ProblemDetail.forStatusAndDetail(
                HttpStatus.valueOf(status), detail
        );
        body.setProperty("code", code);
        return body;
    }
}

@RestController
class LimitsController {

    private static final int RAW_LIMIT_BYTES = 2048;
    private static final int HEADER_LIMIT_BYTES = 256;

    @PostMapping(
        path = "/api/items",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    ResponseEntity<ItemReply> add(
            @Valid @RequestBody ItemRequest request
    ) {
        ItemReply result = new ItemReply(
                request.name(), request.quantity()
        );
        return ResponseEntity.status(HttpStatus.CREATED).body(result);
    }

    @PostMapping(
        path = "/api/raw",
        consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE
    )
    ResponseEntity<?> readRaw(HttpServletRequest request)
            throws IOException {
        // Đọc nhiều nhất 2049 bytes, không dùng readAllBytes()
        // rồi mới kiểm: cách đó có thể cấp phát quá nhiều.
        byte[] prefix = request.getInputStream()
                .readNBytes(RAW_LIMIT_BYTES + 1);

        if (prefix.length > RAW_LIMIT_BYTES) {
            return ResponseEntity.status(413)
                    .contentType(MediaType.parseMediaType(
                            "application/problem+json"
                    ))
                    .body(Problems.of(
                            413,
                            "RAW_TOO_LARGE",
                            "Raw request body exceeds 2048 bytes."
                    ));
        }

        return ResponseEntity.ok(Map.of(
                "status", "accepted",
                "bytes", prefix.length
        ));
    }

    @GetMapping("/api/header-check")
    ResponseEntity<?> checkHeader(
            @RequestHeader(
                value = "X-Client-Tag",
                required = false
            ) String tag
    ) {
        int bytes = tag == null ? 0
                : tag.getBytes(StandardCharsets.UTF_8).length;

        if (bytes > HEADER_LIMIT_BYTES) {
            return ResponseEntity.status(431)
                    .contentType(MediaType.parseMediaType(
                            "application/problem+json"
                    ))
                    .body(Problems.of(
                            431,
                            "HEADER_TOO_LARGE",
                            "X-Client-Tag exceeds 256 UTF-8 bytes."
                    ));
        }

        return ResponseEntity.ok(Map.of(
                "status", "accepted",
                "headerBytes", bytes
        ));
    }

    @PostMapping(
        path = "/api/upload",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
    )
    Map<String, Object> upload(
            @RequestParam("file") MultipartFile file
    ) {
        // Multipart parsing xảy ra trước khi method chạy.
        // Không dùng filename từ client làm server filesystem path.
        return Map.of(
                "status", "accepted",
                "bytes", file.getSize()
        );
    }

    @GetMapping("/api/ping")
    Map<String, String> ping() {
        return Map.of("status", "ok");
    }
}

@RestControllerAdvice
@Order(Ordered.HIGHEST_PRECEDENCE)
class InputErrorAdvice {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ProblemDetail invalidFields(MethodArgumentNotValidException ex) {
        ProblemDetail body = Problems.of(
                400,
                "INVALID_FIELDS",
                "One or more request fields are invalid."
        );
        // Không trả rejected values: có thể chứa PII/secrets.
        body.setProperty(
                "fields",
                ex.getBindingResult().getFieldErrors().stream()
                    .map(error -> error.getField())
                    .distinct()
                    .sorted()
                    .toList()
        );
        return body;
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    ProblemDetail invalidJson(HttpMessageNotReadableException ex) {
        return Problems.of(
                400,
                "INVALID_JSON",
                "JSON body is missing, malformed or has invalid types."
        );
    }

    @ExceptionHandler(MaxUploadSizeExceededException.class)
    ProblemDetail tooLarge(MaxUploadSizeExceededException ex) {
        return Problems.of(
                413,
                "UPLOAD_TOO_LARGE",
                "Uploaded multipart content exceeds configured limits."
        );
    }
}
~~~

### 9.5. Tại sao các endpoints có behavior khác nhau?

**POST /api/items:**
- Jackson đọc JSON, chuyển name/quantity sang Java record.
- **@Valid** kiểm @NotBlank, @NotNull, @Min/@Max.
- Nếu JSON malformed, Spring ném HttpMessageNotReadableException → advice tạo **400 INVALID_JSON**.
- Nếu JSON valid nhưng quantity=0, Spring ném MethodArgumentNotValidException → advice tạo **400 INVALID_FIELDS**.
- Nếu hợp lệ, trả **201** với ItemReply.

**POST /api/raw:**
- Dùng ServletInputStream.readNBytes(2049), **không đọc toàn bộ** body vào memory.
- Nhận 2048 bytes hoặc ít hơn → **200**, trường bytes là tổng đọc được.
- Nhận byte thứ 2049 → **413 RAW_TOO_LARGE** ngay, không cần Content-Length.
- Đọc vượt ngưỡng có thể để lại bytes chưa tiêu thụ; Tomcat có thể swallow hoặc close connection, nhất là với body rất lớn. Lab dùng payload 2049 bytes để dễ quan sát response.
- Nếu malicious client gửi chunked request cực chậm mà không kết thúc, readNBytes có thể tiếp tục đợi; cần timeout, max request duration/rate, ingress limits và cancellation policy ở production.

**GET /api/header-check:**
- So kích thước **UTF-8 encoded value của riêng X-Client-Tag**, không phải toàn bộ HTTP wire headers.
- Header 300 ASCII bytes **nhỏ hơn ngưỡng Tomcat 8KB**, nên vào Controller rồi nhận **431 HEADER_TOO_LARGE**.
- Header 12KB có thể bị Tomcat parser chặn trước Controller, không có custom body/code.
- Nếu có duplicated headers và framework gom giá trị, behavior có thể khác; đây chỉ là **ứng dụng tự đặt limit cho một field**, không thay HTTP parser protection.

**POST /api/upload:**
- Multipart parsing theo Servlet xảy ra trước method controller; max-file-size/max-request-size giới hạn trung gian.
- MaxUploadSizeExceededException có status 413 trong Spring Framework 6.1; advice tạo body ổn định khi exception được MVC xử lý.
- Với body rất lớn và client vẫn upload, Tomcat có thể đóng kết nối vì max-swallow-size; không bảo đảm mọi client luôn đọc được JSON 413.
- API trả byte size nhưng không persist file; không dùng unsanitized original filename.

**@RestControllerAdvice:**
- Dùng ProblemDetail với extension **code** để client có machine-readable error.
- **Không catch Exception.class** và trả 400 cho mọi lỗi, vì sẽ che server bugs.
- Không phản chiếu Jackson parse message hay rejectedValue; các giá trị này có thể chứa dữ liệu người dùng hoặc internal class names.
- Các lỗi do HTTP parser/Ingress tạo trước MVC **không đi qua** advice này.

## 10. Test HTTP thật trên embedded Tomcat

Vì header limits và multipart limits có thể được thực thi trước Controller, dùng **@SpringBootTest(webEnvironment=RANDOM_PORT)** để kiểm ít nhất một đường HTTP thực tế. **MockMvc không chạy real Servlet container request-line/header parser**, và mock multipart test có thể không kích hoạt same size handling như Tomcat.

**src/test/java/com/example/limits/RequestLimitsHttpTest.java:**

~~~java
package com.example.limits;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.nio.charset.StandardCharsets;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class RequestLimitsHttpTest {

    @Autowired
    TestRestTemplate http;

    private static HttpHeaders jsonHeaders() {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        return headers;
    }

    @Test
    void validJsonCreatesItem() {
        HttpEntity<String> request = new HttpEntity<>(
            "{\"name\":\"book\",\"quantity\":2}",
            jsonHeaders()
        );
        ResponseEntity<Map> response = http.postForEntity(
            "/api/items", request, Map.class
        );
        assertEquals(HttpStatus.CREATED, response.getStatusCode());
        assertNotNull(response.getBody());
        assertEquals("book", response.getBody().get("name"));
        assertEquals(2,
            ((Number) response.getBody().get("quantity")).intValue());
    }

    @Test
    void invalidFieldsReturn400() {
        HttpEntity<String> request = new HttpEntity<>(
            "{\"name\":\" \",\"quantity\":0}",
            jsonHeaders()
        );
        ResponseEntity<Map> response = http.postForEntity(
            "/api/items", request, Map.class
        );
        assertEquals(400, response.getStatusCode().value());
        assertNotNull(response.getBody());
        assertEquals("INVALID_FIELDS",
                response.getBody().get("code"));
    }

    @Test
    void malformedJsonReturns400() {
        HttpEntity<String> request = new HttpEntity<>(
            "{broken",
            jsonHeaders()
        );
        ResponseEntity<Map> response = http.postForEntity(
            "/api/items", request, Map.class
        );
        assertEquals(400, response.getStatusCode().value());
        assertNotNull(response.getBody());
        assertEquals("INVALID_JSON",
                response.getBody().get("code"));
    }

    @Test
    void rawPayloadBoundaryIsDeterministic() {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_OCTET_STREAM);

        ResponseEntity<Map> allowed = http.postForEntity(
            "/api/raw",
            new HttpEntity<>(new byte[2048], headers),
            Map.class
        );
        assertEquals(HttpStatus.OK, allowed.getStatusCode());
        assertEquals(2048,
            ((Number) allowed.getBody().get("bytes")).intValue());

        ResponseEntity<Map> rejected = http.postForEntity(
            "/api/raw",
            new HttpEntity<>(new byte[2049], headers),
            Map.class
        );
        assertEquals(413, rejected.getStatusCode().value());
        assertNotNull(rejected.getBody());
        assertEquals("RAW_TOO_LARGE",
                rejected.getBody().get("code"));
    }

    @Test
    void applicationHeaderPolicyReturns431() {
        HttpHeaders headers = new HttpHeaders();
        headers.set("X-Client-Tag", "x".repeat(300));

        ResponseEntity<Map> response = http.exchange(
            "/api/header-check",
            HttpMethod.GET,
            new HttpEntity<>(headers),
            Map.class
        );
        assertEquals(431, response.getStatusCode().value());
        assertNotNull(response.getBody());
        assertEquals("HEADER_TOO_LARGE",
                response.getBody().get("code"));
    }

    @Test
    void smallMultipartIsAcceptedByRealServletParser() {
        byte[] data = "abc\n".getBytes(StandardCharsets.UTF_8);
        ByteArrayResource resource = new ByteArrayResource(data) {
            @Override
            public String getFilename() {
                return "sample.txt";
            }
        };

        MultiValueMap<String, Object> parts =
                new LinkedMultiValueMap<>();
        parts.add("file", resource);

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.MULTIPART_FORM_DATA);

        ResponseEntity<Map> response = http.postForEntity(
            "/api/upload",
            new HttpEntity<>(parts, headers),
            Map.class
        );
        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertNotNull(response.getBody());
        assertEquals(4,
            ((Number) response.getBody().get("bytes")).intValue());
    }
}
~~~

### 10.1. Những gì test đảm bảo

- **201** với JSON hợp lệ.
- **400 INVALID_FIELDS** khi ràng buộc DTO fail.
- **400 INVALID_JSON** khi Jackson không parse được.
- **200 tại 2048 bytes** và **413 tại 2049 bytes** theo limit do /api/raw tự đặt.
- **431 khi X-Client-Tag có 300 ASCII bytes**; request còn dưới Tomcat 8KB, nên app tự trả 431.
- **200 multipart** khi file rất nhỏ.

**Không có test khẳng định Tomcat sẽ trả chính xác 431 cho 12KB headers.** Tomcat parser có thể từ chối trước MVC bằng 400 hoặc close, khác kết quả do /api/header-check tự quyết định.

### 10.2. Vì sao không assert raw JSON string?

Jackson có thể serialize Map/ProblemDetail theo thứ tự fields khác, body có instance/time hoặc các fields bổ sung; việc assert nguyên chuỗi thường giòn. Tests nên kiểm **status**, **Content-Type khi là contract**, **machine-readable code** và boundary behavior. Nếu muốn kiểm application/problem+json, có thể thêm assertion Content-Type compatible với MediaType.parseMediaType("application/problem+json").

### 10.3. Độ tin cậy của multipart overflow test

Với một multipart file 70KiB, max-file-size=64KB, server có thể phát 413 nếu MVC multipart exception được xử lý và response tới được client. Nhưng môi trường với proxy/Tomcat swallow/connection resets có thể tạo cách quan sát khác. Nên có **integration test được chạy trong đúng deployment** và phân biệt kết quả HTTP từ lỗi transport; không đặt test unit MockMultipartFile làm bằng chứng container đã áp size limit.

## 11. Build và chạy lab Java 17

Cần JDK 17+, Maven và cổng 8080 chưa được sử dụng:

~~~bash
mvn test
mvn package
java -jar target/request-limits-lab-1.0.0.jar
~~~

Các JUnit tests trong phần 10 dùng **RANDOM_PORT**, nên không chiếm cố định 8080. Sau khi JAR chạy trên 8080, dùng terminal khác gửi request.

### 11.1. Happy path: nhận 201

~~~bash
curl -i -X POST http://localhost:8080/api/items \
  -H "Content-Type: application/json" \
  -d '{"name":"book","quantity":2}'
~~~

Kỳ vọng **HTTP 201**, body JSON chứa **name=book**, **quantity=2**.

### 11.2. 400 do @Valid

~~~bash
curl -i -X POST http://localhost:8080/api/items \
  -H "Content-Type: application/json" \
  -H "Accept: application/problem+json" \
  -d '{"name":" ","quantity":0}'
~~~

Kỳ vọng **HTTP 400**, Content-Type **application/problem+json**, code **INVALID_FIELDS**, fields bao gồm **name** và **quantity**. Không nhất thiết có một thứ tự JSON keys cố định.

### 11.3. 400 do JSON malformed

~~~bash
curl -i -X POST http://localhost:8080/api/items \
  -H "Content-Type: application/json" \
  -d '{broken'
~~~

Kỳ vọng **HTTP 400** và code **INVALID_JSON**, không chứa raw Jackson stack trace.

### 11.4. 413 do ứng dụng đọc actual body bytes

Dùng Python 3 tạo payload qua stdin, không tạo file lớn:

~~~bash
python3 -c 'import sys;sys.stdout.buffer.write(b"x"*2048)' | \
  curl -i -X POST http://localhost:8080/api/raw \
    -H "Content-Type: application/octet-stream" \
    --data-binary @-
~~~

Kỳ vọng **HTTP 200** với trường **bytes=2048**.

~~~bash
python3 -c 'import sys;sys.stdout.buffer.write(b"x"*2049)' | \
  curl -i -X POST http://localhost:8080/api/raw \
    -H "Content-Type: application/octet-stream" \
    --data-binary @-
~~~

Kỳ vọng **HTTP 413** và code **RAW_TOO_LARGE**. Đây là application policy, **không phải** spring.servlet.multipart.max-file-size và không liên quan Tomcat maxPostSize.

### 11.5. 431 do header nghiệp vụ quá dài

~~~bash
curl -i http://localhost:8080/api/header-check \
  -H "X-Client-Tag: $(python3 -c 'print("x"*300)')"
~~~

Kỳ vọng **HTTP 431** và **HEADER_TOO_LARGE**. Vì 300 bytes nhỏ hơn global request-header limit 8KB, controller nhận request và quyết định status.

### 11.6. Header quá lớn bị Tomcat từ chối trước Controller

~~~bash
curl -v --http1.1 \
  -H "X-Client-Tag: $(python3 -c 'print("x"*12000)')" \
  http://localhost:8080/api/ping
~~~

**Không cố định expected status 431.** 12.000 ký tự làm header section vượt cấu hình 8KB của Tomcat; tùy connector/proxy/transport, client có thể nhận **400**, đôi khi một response khác hoặc connection close. Không mong body có code HEADER_TOO_LARGE, vì Controller có thể chưa chạy.

Chỉ chạy test này trên **localhost**; không sử dụng header quá dài vào service ngoài quyền kiểm thử. Trên PowerShell Windows, lệnh command substitution kiểu Bash không chạy như trên; dùng Python/curl.exe hoặc một test client được cấu hình phù hợp.

### 11.7. Multipart file dưới/trên ngưỡng

~~~bash
printf 'abc\n' > small.txt
curl -i -F "file=@small.txt" http://localhost:8080/api/upload
~~~

Kỳ vọng **HTTP 200** và **bytes=4**.

~~~bash
python3 -c 'from pathlib import Path; Path("large.bin").write_bytes(b"x"*(70*1024))'
curl -v -F "file=@large.bin" http://localhost:8080/api/upload
~~~

**Dự kiến chính sách từ chối 413** khi multipart parser nhận file lớn hơn 64KB và response được gửi thành công. Nhưng cần ghi **status và transport outcome thực**, vì container có thể dừng đọc body/close connection trong một số tình huống. Không gọi 400/500/connection reset là “chắc chắn cấu hình max-file-size không có tác dụng”; phải xem exception chain/connector logs.

Sau test, xóa các tệp giả small.txt và large.bin khi không cần, không đặt tệp khách hàng thật vào demo.

## 12. So sánh lỗi multipart và lỗi JSON raw tại hai endpoint

| Request | Hạn mức đang kiểm | Ai kiểm | Kết quả dự kiến |
| --- | --- | --- | --- |
| POST /api/items JSON hợp lệ nhỏ | @Valid DTO fields | MVC Bean Validation | 201 |
| POST /api/items JSON cú pháp sai | JSON deserializer | Jackson/MVC | 400 INVALID_JSON |
| POST /api/items JSON @Min sai | DTO constraints | MVC validation | 400 INVALID_FIELDS |
| POST /api/raw 2048 bytes | Application 2048-byte stream limit | Controller | 200 |
| POST /api/raw 2049 bytes | Application 2048-byte stream limit | Controller | 413 RAW_TOO_LARGE |
| POST /api/upload 4 bytes | Multipart size 64KB/file, 128KB/request | Servlet parser | 200 |
| POST /api/upload 70KiB | Multipart file max 64KB | Servlet parser/MVC handler | 413 hoặc transport failure tùy layer |
| GET /api/header-check với X-Client-Tag 300B | Header nghiệp vụ 256B | Controller | 431 HEADER_TOO_LARGE |
| GET /api/ping với header 12KB | Tomcat request header 8KB | HTTP parser | 400 thường gặp; không bảo đảm 431 |

Hai request đều có 413 nhưng **không cùng cơ chế**: raw endpoint đếm bytes khi đọc; multipart được Servlet container xử lý theo MultipartConfig. Một lỗi vượt 8KB headers **không có nghĩa** đã chạm vào Controller, dù một lỗi 431 với tag 300B thì có.

## 13. Tại sao 413 có thể “biến thành” connection reset?

HTTP client có thể gửi request body theo nhiều cách:
1. Gửi hết body cùng headers.
2. Gửi headers rồi chờ **100 Continue**.
3. Gửi body theo chunked transfer encoding.
4. Gửi qua HTTP/2 stream với flow control riêng.

Khi server nhận ra request quá lớn, nó có thể trả 413 sớm. Nếu client vẫn tiếp tục đẩy hàng megabytes body, server có thể abort stream/connection. Tomcat **maxSwallowSize** giới hạn số bytes body được đọc-bỏ để giữ kết nối/response. Khi vượt giới hạn, client có thể thấy:

~~~text
curl: (56) Recv failure: Connection reset by peer
curl: (52) Empty reply from server
HTTP/1.1 413 Content Too Large
HTTP/1.1 400 Bad Request
~~~

Các dòng trên là **những ví dụ kết quả có thể xảy ra ở các trường hợp khác nhau**, không phải stdout bắt buộc của một lần curl. Proxy và HTTP protocol version có thể làm behavior khác.

### 13.1. Không điều trị connection reset bằng cách mở maxSwallowSize vô hạn

Giữ **max-swallow-size=-1** có thể khiến Tomcat cố đọc/bỏ không giới hạn upload đã bị từ chối, tăng network/CPU pressure và nguy cơ DoS. Nếu muốn client luôn nhận error JSON, cần xem ingress buffering, HTTP 100-continue, body size limits ở edge và cách client gửi; giải pháp tùy deployment, không có một property giải quyết tất cả.

### 13.2. Không tin Content-Length từ client

Một body filter chỉ so:

~~~java
// FRAGMENT CHƯA ĐỦ để giới hạn mọi loại HTTP body:
if (request.getContentLengthLong() > 2048) {
    response.setStatus(413);
    return;
}
~~~

Đây là **fragment không đầy đủ**: với request chunked, Content-Length có thể là -1; còn proxy/decoder có thể thay đổi representation. Nếu dùng filter, phải xử lý **actual bytes** và blocking/async semantics, bảo vệ trước khi Jackson/buffering cấp phát lớn. Lab đọc tối đa 2049 bytes ở một raw endpoint cụ thể.

### 13.3. Gzip và decompression bomb

Một file nén nhỏ có thể giải nén thành dữ liệu rất lớn. **Body limit trên bytes của request đã nhận** không nhất thiết giới hạn kích thước sau khi decode/decompress trong ứng dụng. Với ZIP/image/PDF/archive uploads, cần kiểm:
- Format/MIME thực, không chỉ extension.
- Uncompressed size / entry count / recursion depth / compression ratio.
- CPU time, memory và scratch disk.
- File scanning và isolation cho nội dung không đáng tin.

Không nâng multipart max size mà bỏ qua downstream parsing cost.

## 14. Reverse proxy, Ingress và Gateway: giới hạn có thể khác nhau

Một deployment thường có nhiều ngưỡng:

~~~text
Browser
  |
  +-- CDN/WAF: body/header/query policy
  |
  +-- Ingress/NGINX/Envoy: max body, header buffers
  |
  +-- Kubernetes Service
  |
  +-- Tomcat: combined request line+headers limit
  |
  +-- Spring MVC multipart: max file/request
  |
  +-- Application: DTO + per-API limits
~~~

Chỉ **mức thấp nhất mà request thực sự đi qua** mới quyết định request bị chặn ở đâu. Nếu ingress body limit 1MB, Spring multipart max=10MB, file 2MB sẽ bị ingress từ chối trước Spring. Nếu ingress 20MB, Spring multipart max-file-size=1MB, request 2MB có thể vào Tomcat rồi bị multipart parser từ chối.

### 14.1. NGINX config minh họa

~~~nginx
server {
    listen 80;
    server_name local.example.test;

    # Chỉ là ví dụ: tính theo policy API,
    # không mặc định 2m là đủ cho mọi upload.
    client_max_body_size 2m;

    location / {
        proxy_pass http://127.0.0.1:8080;
    }
}
~~~

**client_max_body_size** là một NGINX request body limit (có thể trả 413 khi vượt). Tuy nhiên config này là **fragment minh họa**, không phải một deployment Kubernetes Ingress đầy đủ. Với NGINX Ingress Controller, values/annotations có thể dùng tên khác, và nhiều controller/load balancer không dùng NGINX.

Tương tự, NGINX có các header/request-line buffer settings; không copy nguyên một property của Tomcat sang NGINX. Xác minh **Ingress Controller + version** thực, thay vì suy luận mọi 431 là do Spring.

### 14.2. Đừng tùy tiện nới cả ba ngưỡng lên 100MB

Nếu file upload cần hỗ trợ 20MB:
1. Chọn max-file-size/max-request-size theo business requirement và overhead.
2. Kiểm ingress body limit ít nhất tương ứng, có headroom hợp lý.
3. Kiểm disk/temp directory và **ephemeral-storage** quotas.
4. Kiểm scan/transform memory, timeout và concurrency.
5. Kiểm upload streaming/resumable design khi file thực sự lớn.
6. Giữ header limit nhỏ và an toàn; file lớn **không đòi header lớn**.
7. Test cùng đường network thật, không chỉ gọi localhost trực tiếp.

Một lớp giới hạn thay đổi có thể làm lỗi chuyển từ 413 ở edge sang 413/500 ở app; cần quan sát sau deploy.

## 15. Cookie phình to và Authorization dài: cách điều tra 431

Các câu hỏi chẩn đoán:
- Browser có gửi nhiều Cookie với domain/path trùng lặp không?
- JWT có chứa danh sách roles/permissions quá dài không?
- SSO/OIDC có gắn ID token/refresh token vào Cookie thay vì giữ phía server không?
- Trace headers được thêm qua nhiều proxies và tăng không kiểm soát không?
- Browser request có thất bại chỉ khi đã đăng nhập lâu ngày không?
- Incognito hoặc browser profile sạch có hết lỗi không?
- Lỗi xảy ra trên một API hay mọi request tới cùng host?
- Header error xuất hiện ở CDN, ingress hay Tomcat?

### 15.1. Không log nguyên Cookie hoặc Authorization để debug

Headers có thể chứa **session IDs, bearer tokens và dữ liệu cá nhân**. Không log raw Cookie/Authorization vào access logs, exception traces hoặc ticket công khai. Đo **header name + byte count**, tổng request-header size và correlation ID được kiểm soát; có thể redact values.

Ví dụ output chẩn đoán an toàn:

~~~text
request.path=/api/profile
request.header.cookie.bytes=7630
request.header.authorization.bytes=0
request.header.total.estimated.bytes=8050
http.status=400
rejection.layer=tomcat-parser
~~~

Đây là dữ liệu **minh họa**; không phải một tập Tomcat metrics mặc định. Nếu parser từ chối request trước Spring filters, app không thể đo chính xác mọi header tại Controller.

### 15.2. Cookie không tự được làm ngắn khi hết hạn session

Browser có thể giữ nhiều cookies theo Domain, Path, Max-Age, SameSite; logout một endpoint có thể chỉ xóa một cookie theo name/path cụ thể. Cookie cũ ở path khác vẫn được gửi. Khi gặp 431 liên quan session, kiểm Set-Cookie và Cookie scope, expiration, duplicated cookie names và migration giữa các subdomains.

### 15.3. JWT không cần chứa toàn bộ hồ sơ người dùng

Giữ access token gồm claims cần thiết (subject, issuer, audience, expiry và quyền thực sự cần). Danh sách roles/tenants lớn có thể làm Authorization header phình lên; token cũng có thể bị lộ ở logs. Cân nhắc server-side permission lookup/versioning thay vì nhét hàng nghìn quyền vào một JWT.

### 15.4. Vì sao tăng header buffer có chi phí?

Tomcat docs cảnh báo request-header buffers tiêu tốn RAM theo concurrency. Khi đặt global max 1MB để đáp ứng một JWT bất thường, một attacker có thể gửi nhiều requests với headers lớn gây memory pressure. Tối ưu token/cookies thường tốt hơn nâng toàn cục thiếu giới hạn.

## 16. Problem Details và mã lỗi machine-readable

**RFC 9457** định nghĩa Problem Details for HTTP APIs, với media type **application/problem+json**. Một response 413 do app kiểm soát có thể có dạng:

~~~json
{
  "type": "about:blank",
  "title": "Content Too Large",
  "status": 413,
  "detail": "Raw request body exceeds 2048 bytes.",
  "instance": "/api/raw",
  "code": "RAW_TOO_LARGE"
}
~~~

**code** là extension do lab tự đặt; **type/title/status/detail/instance** là các members của Problem Details. Các trường type, instance và title thực tế có thể do Spring serialization/exception handler suy ra; đừng assert exact body byte-for-byte nếu không phải API contract.

Với 431 do app trả:

~~~json
{
  "type": "about:blank",
  "status": 431,
  "detail": "X-Client-Tag exceeds 256 UTF-8 bytes.",
  "code": "HEADER_TOO_LARGE"
}
~~~

Đây là **ví dụ field subset**, không cam kết thứ tự keys hoặc tất cả members trong response.

**Bật spring.mvc.problemdetails.enabled=true** trong Boot 3.3 giúp MVC xử lý nhiều framework errors dưới dạng ProblemDetail, nhưng **không buộc Tomcat connector/Ingress trả cùng schema**. Đừng dùng ProblemDetail như lớp trang trí thay vì xử lý đúng server/proxy limits.

### 16.1. Không đưa bí mật vào error body

Đối với input invalid:
- Trả **code** và message an toàn.
- Tránh echo raw body, original filename, Cookie, Authorization, password, token, SQL query hoặc stack trace.
- Với validation errors, trả field names/constraint codes nếu contract cho phép, không tự động trả rejectedValue.
- Dùng trace/correlation ID không phải credential.
- Không log raw payload lớn vào memory/log files chỉ để debug 413.

Một attacker có thể cố tình gửi payload rất lớn hoặc malformed để làm logging system bão hòa; sampling và redaction là một phần của bảo vệ.

## 17. 400/413/431 cần tests ở những tầng nào?

| Loại test | Công cụ | Bảo đảm tốt | Không bảo đảm |
| --- | --- | --- | --- |
| DTO/unit validation | JUnit + Validator | Constraints @Min/@NotBlank | HTTP parser/header buffers |
| MVC MockMvc | @WebMvcTest/@SpringBootTest MockMvc | Jackson, @Valid, @ExceptionHandler | Real Tomcat maxHttpRequestHeaderSize, OS/network |
| Embedded server HTTP | @SpringBootTest(RANDOM_PORT), TestRestTemplate | Multipart parsing, actual HTTP status/body | Ingress/CDN/WAF behavior |
| Local curl | curl --http1.1 -v | Request/response qua Tomcat thật | External LB path |
| Staging E2E | Real DNS/Ingress/Gateway | Limits ở mọi hop | Production-specific load/traffic toàn bộ |
| Client compatibility | Browser/mobile SDK | Cookie/token, error UX, retry | Server internal exception details |

**Không dùng MockMvc oversized header test làm bằng chứng Tomcat đã giới hạn 8KB.** MockMvc không chạy container-level parser. Tương tự, MockMultipartFile có thể bypass một phần Servlet multipart size enforcement; kiểm bằng real-port integration khi giới hạn container là mục tiêu.

### 17.1. Bài test boundary nên có

- 400: name="" / name=" " / quantity=0 / quantity=1 / quantity=101.
- 400: JSON thiếu dấu ngoặc, quantity="abc", body thiếu hẳn.
- 413 raw: **2048 bytes accept**, **2049 bytes reject**.
- 413 multipart: file dưới 64KB và trên 64KB; tổng multipart request vượt 128KB.
- 431 app header: 256 ASCII bytes accept, 257 reject.
- HTTP parser: combined headers dưới/qua 8KB; kiểm status thực, không khóa 431.
- Cookie nhiều keys, JWT dài, Unicode header policy.
- 414: URI rất dài; quan sát status ở edge/Tomcat, không ép phải 414.
- 415: text/plain gửi đến /api/items consumes JSON.
- 5xx: lỗi bất ngờ không bị advice biến thành 400.

**Tại ranh giới, thống nhất byte units** (KB vs KiB, UTF-8 bytes vs Java String length). Multipart request có overhead boundaries và headers, nên tổng size != sum(file sizes). Đo thực thay vì hứa output cố định chỉ bằng tính số ký tự.

### 17.2. Unit test chỉ cho thấy exception mapping, không chắc client nhận body

Bạn có thể unit-test @ExceptionHandler(MaxUploadSizeExceededException) trả ProblemDetail 413, nhưng một request multipart thật có thể bị Tomcat close trước khi client đọc response. Cần **network integration** để xác minh trải nghiệm client, nhất là khi max-swallow-size đang ảnh hưởng.

## 18. Runbook khi lỗi chỉ xuất hiện trong production

### 18.1. Bước 1: ghi nhận request profile an toàn

Thu thập không chứa secrets:
- HTTP method, route pattern/path đã sanitize.
- Content-Type, Accept, Transfer-Encoding, có/không có Content-Length.
- Tổng size request body thực (nếu đo được tại proxy).
- Estimated header bytes, Cookie bytes, Authorization bytes **chỉ số lượng**, không giá trị.
- Status code, response headers, server/proxy correlation ID.
- HTTP version (1.1, 2, 3).
- Endpoint/instance và thời điểm xảy ra.

Nếu client báo "Network Error", không tự gán nó là 413; cần nhìn trace/gateway logs.

### 18.2. Bước 2: xác định tầng đầu tiên từ chối

~~~text
Có request ID trong gateway log?
    |
    +-- Không: điều tra CDN/WAF/client/DNS/TLS
    |
    +-- Có: gateway trả 413/431/400 mà backend không log?
               |
               +-- Có: kiểm ingress/header/body limits
               |
               +-- Không: backend có nhận request?
                              |
                              +-- Parser Tomcat reject: xem connector logs
                              |
                              +-- MVC mapping/converter: xem safe exception type
                              |
                              +-- App Controller: xem code/validation/domain policy
~~~

Tìm **bằng chứng request đi tới đâu**; không chỉ dựa vào status cuối cùng. Một gateway có thể đổi upstream status hoặc tạo trang HTML lỗi của riêng nó.

### 18.3. Bước 3: giảm payload và lặp lại có kiểm soát

- Nếu body lớn: giảm dần bytes để tìm threshold, nhưng chỉ test trên staging/localhost.
- Nếu Cookie lớn: thử browser profile mới/scope cookie được làm sạch.
- Nếu header nghiệp vụ lớn: thay bằng ASCII strings có chiều dài đo được.
- Nếu URI dài: rút query, xem có cần chuyển payload thành body.
- Nếu proxy path khác localhost: so kết quả direct Tomcat và đi qua ingress.

Dùng binary search threshold để tìm khoảng chặn, nhưng **không bắn vô hạn requests** vào production hoặc endpoint không có quyền load test.

### 18.4. Bước 4: kiểm cấu hình thực, không chỉ YAML trong repo

Có thể có:
- Environment variables hoặc command-line overrides.
- ConfigMap/Helm chart values.
- Different profiles.
- CDN/WAF/gateway policies.
- Tomcat Connector customizer.
- Ingress annotations.
- Spring Security filters.
- Spring MVC multipart resolver custom beans.
- Embedded server version khác do dependency override.

Một property đúng trong application.yml chưa chắc đang được active trong instance nhận request. Cần xem effective configuration bằng phương thức nội bộ được bảo vệ, không bật /actuator/env công khai để debug.

### 18.5. Bước 5: sửa ở tầng đúng và test hồi quy

| Quan sát | Thay đổi nên cân nhắc |
| --- | --- |
| 400 INVALID_JSON | Sửa client JSON, Content-Type và DTO; không tăng header limit |
| 400 INVALID_FIELDS | Sửa validation/caller data contract |
| 400 "Request header is too large" ở Tomcat | Giảm Cookie/JWT/header count; chỉ tăng header buffer khi có số liệu |
| 431 ở gateway | Giảm headers hoặc chỉnh gateway policy theo nhu cầu |
| 413 từ ingress trước app | Điều chỉnh ingress limit và capacity/timeout/streaming |
| 413 multipart ở Spring | Chỉnh max-file-size/max-request-size theo nghiệp vụ và tmp disk |
| 413 raw do app | Thiết kế per-endpoint limit hoặc chunked protocol |
| Connection reset khi oversize upload | Kiểm maxSwallowSize/Expect/proxy buffering, không mặc định app bug |
| 414 | Thu gọn URI, chuyển request data sang body phù hợp |
| 500 vì hết disk multipart | Cấp scratch/quota, cleanup, error mapping; không chỉ tăng upload limit |

## 19. Những lỗi suy luận thường gặp

| Kết luận sai | Vì sao không đúng |
| --- | --- |
| “413 tức JSON @Valid sai” | Validation thường trả 400; 413 là body size policy |
| “431 nghĩa body file lớn” | 431 là request headers, không phải body |
| “Tomcat chắc chắn trả 431 cho header lớn” | Tomcat parser có thể dùng 400 |
| “Tăng spring.servlet.multipart.max-file-size sửa mọi 413” | Proxy, raw body, max-request-size cũng có limits |
| “server.tomcat.max-http-form-post-size=2MB chặn mọi JSON >2MB” | maxPostSize chủ yếu giới hạn form parameter parsing |
| “server.tomcat.max-swallow-size=2MB nghĩa file max 2MB” | Đây là giới hạn body được bỏ sau aborted upload |
| “Content-Length đủ để bảo vệ body” | Chunked/streaming không cần Content-Length |
| “@ControllerAdvice bắt mọi lỗi request” | Proxy/Tomcat parser/filter có thể reject trước MVC |
| “Bật Problem Details thì mọi 4xx cùng JSON” | Connector/ingress/security có handlers riêng |
| “Chỉ cần kiểm HttpStatus 413 trong MockMvc” | MockMvc không tái hiện đầy đủ multipart parser/network swallow |
| “8KB là 8KB cho từng header trên Tomcat” | Tomcat tính combined request line + headers |
| “Tăng max header lên 1MB vô hại” | Header buffers × concurrency gây memory pressure |
| “413 client cứ retry lại” | Payload vượt ngưỡng cố định thường vẫn bị reject |
| “Thay đổi Boot 2 header property sang Boot 3 giữ behavior giống cũ” | Property request-only thay thế và server differences |
| “413 không có trong app logs nghĩa lỗi không tồn tại” | Ingress/Proxy có thể trả lỗi trước backend |
| “Nếu network reset thì app chưa reject” | Tomcat có thể reject rồi close vì unread request body |
| “App accept small upload nghĩa large upload cũng ổn” | Size/spool/part count/total request limits khác |
| “Tăng JSON @Size bảo vệ trước memory allocation” | Jackson có thể parse/allocate trước Bean Validation |

## 20. Bài tập tự kiểm tra

**1.** JSON body chỉ 50 bytes nhưng thiếu dấu ngoặc, status phù hợp?  
**Đáp án:** Thường 400, vì cú pháp JSON sai; không phải 413.

**2.** Một MultipartFile 70KiB khi max-file-size=64KB?  
**Đáp án:** Phải bị từ chối theo multipart policy; thường 413 nếu exception/response xử lý thành công, nhưng có thể có transport error khi upload bị abort.

**3.** JWT chứa quá nhiều claims làm Authorization header 15KB với Tomcat 8KB, có chắc 431 không?  
**Đáp án:** Không. Tomcat HTTP parser có thể trả 400 hoặc đóng kết nối; 431 là mã chuyên biệt nhưng không được bảo đảm.

**4.** Cookie 7KB + Authorization 2KB có thể vượt header limit 8KB dù mỗi field nhỏ hơn 8KB không?  
**Đáp án:** Có; Tomcat tính tổng request line và headers.

**5.** server.tomcat.max-http-form-post-size=2MB có bảo vệ JSON body 100MB?  
**Đáp án:** Không. Nó không phải generic JSON body limit.

**6.** server.tomcat.max-swallow-size điều khiển size nào?  
**Đáp án:** Số body bytes Tomcat swallow sau khi upload bị abort, không phải allowed upload size.

**7.** @Valid với quantity=0 trong DTO @Min(1) thường trả 422?  
**Đáp án:** Spring MVC mặc định thường trả 400; 422 chỉ khi API định nghĩa riêng.

**8.** Tại sao Content-Length không đủ làm body limit?  
**Đáp án:** Client có thể gửi chunked transfer, không có Content-Length; phải kiểm actual bytes.

**9.** 431 và 414 khác nhau thế nào?  
**Đáp án:** 431 cho header field(s) quá lớn, 414 cho URI/request-target quá dài.

**10.** HTTP 413 do ingress nhưng app không thấy log, nên sửa ở đâu?  
**Đáp án:** Kiểm ingress body limit, request buffering và chính sách proxy trước khi chỉnh Spring.

**11.** Multipart max-file-size=10MB nhưng max-request-size=12MB, có được upload hai file 8MB cùng request không?  
**Đáp án:** Không theo tổng request policy, vì 16MB dữ liệu files cộng overhead vượt 12MB.

**12.** Vì sao MockMvc không chứng minh Tomcat header buffer limit?  
**Đáp án:** MockMvc không chạy HTTP connector parser thực.

**13.** Tại sao không nên trả rejectedValue hoặc raw Jackson message trong ProblemDetail?  
**Đáp án:** Có thể lộ PII, token, secret, internal paths và details.

**14.** Nếu lab /api/raw nhận 2048 bytes thì sao? 2049 bytes?  
**Đáp án:** 2048 trả 200 với bytes=2048; 2049 trả 413 RAW_TOO_LARGE.

**15.** Nếu X-Client-Tag 300 ASCII bytes ở lab, vì sao 431 là ổn định?  
**Đáp án:** Nó còn dưới Tomcat 8KB nên Controller nhận được, tự kiểm ngưỡng 256 bytes và trả 431.

**16.** Có nên nâng header limit lên 1MB để tránh lỗi từ JWT dài không?  
**Đáp án:** Thường nên giảm Cookie/JWT/headers trước, vì buffer tăng theo concurrency và có memory DoS risk.

**17.** Tại sao retry đúng payload sau khi nhận 413 có thể vô ích?  
**Đáp án:** Nếu vượt policy cố định, cùng payload sẽ bị reject lại; cần đổi payload hoặc quy trình upload.

**18.** Một app nhận JSON 5MB qua localhost nhưng đi qua ingress trả 413 là vì sao?  
**Đáp án:** Ingress có limit thấp hơn hoặc body buffering policy khác, chặn trước Spring.

**19.** Boot 3 dùng property nào cho request-header size, thay vì property cũ?  
**Đáp án:** server.max-http-request-header-size.

**20.** Khi header quá lớn bị Tomcat từ chối trước Spring MVC, @RestControllerAdvice có bắt được không?  
**Đáp án:** Không, vì Controller/DispatcherServlet không nhận request đã bị parser từ chối.

## 21. Checklist gỡ lỗi và nâng cấp

- [ ] Phân biệt 400/413/431 theo **dữ liệu sai, body quá lớn, headers quá lớn**.
- [ ] Không nhầm 414 URI Too Long, 415 Unsupported Media Type, 422, 429, 502/504.
- [ ] Xác định chính xác **tầng đầu tiên** từ chối request.
- [ ] Kiểm HTTP method, path, Content-Type, Accept, Content-Length/Transfer-Encoding và HTTP version.
- [ ] Đo body/header sizes bằng số bytes, không lộ Cookie/JWT.
- [ ] Với 400, phân biệt Jackson parse, @Valid, conversion và Tomcat parser.
- [ ] Với 413, kiểm ingress body cap, multipart per-file và total request limits.
- [ ] Với 431/400 header, kiểm Cookie/Authorization/request line và buffer theo Tomcat.
- [ ] Không dùng server.tomcat.max-http-form-post-size làm JSON body limit.
- [ ] Không dùng max-swallow-size làm max upload limit.
- [ ] Kiểm multipart temp directory, disk quota và concurrency.
- [ ] Không tăng header/body limits thiếu capacity planning, rate limits và timeout.
- [ ] Hiểu Content-Length không bao quát chunked và decoded content.
- [ ] Khi nâng Boot 2→3, kiểm server.max-http-request-header-size thay cho property cũ.
- [ ] Dùng MockMvc cho MVC validation, real HTTP server cho Tomcat/multipart limits.
- [ ] Có staging tests đi qua ingress/gateway thật.
- [ ] Error response an toàn: status, application/problem+json khi app kiểm soát, machine code.
- [ ] Không log raw payload/credentials hoặc exception internals.
- [ ] Có regression tests ở ranh giới size và retry/backoff khi phù hợp.
- [ ] Xác nhận sự cố đã được xử lý từ **client-visible outcome**, không chỉ app logs.

## 22. Kết luận

**400, 413 và 431 không phải ba cách gọi của cùng một lỗi.** 400 thường gắn với request malformed hoặc invalid input; 413 gắn với **request content/body vượt limit**; 431 gắn với **header fields quá lớn**. Nhưng một request bị Tomcat parser hoặc ingress từ chối trước Spring MVC có thể nhận **400 thay vì 431**, hoặc connection reset thay vì body 413 mong đợi.

Khi gỡ lỗi hoặc nâng cấp, hãy đi theo đường **client → gateway/ingress → Tomcat → filters → Spring MVC → Controller**, xác định nơi kiểm kích thước và đọc **đúng property của Spring Boot/Tomcat phiên bản đang chạy**. Trong Boot 3.3, **server.max-http-request-header-size**, **server.tomcat.max-http-form-post-size**, **server.tomcat.max-swallow-size** và **spring.servlet.multipart.max-* ** phục vụ những nhiệm vụ khác nhau. Giải pháp bền vững là đặt limits theo nghiệp vụ, phân biệt bytes thực, bảo vệ memory/storage và kiểm thử đúng tầng trước khi rollout.

## Tài liệu tham khảo chính thức

- Spring Boot 3.3.13 — Common Application Properties, header size, Tomcat form/swallow, servlet multipart limits: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Boot 3.3 — Spring MVC servlet multipart and web handling: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Apache Tomcat 10.1 — HTTP Connector maxHttpRequestHeaderSize, maxPostSize, maxSwallowSize, multipart limits: https://tomcat.apache.org/tomcat-10.1-doc/config/http.html
- Apache Tomcat 10.1 — Security Considerations, request parameter and part limits: https://tomcat.apache.org/tomcat-10.1-doc/security-howto.html
- Spring Framework 6.1 — MaxUploadSizeExceededException implements ErrorResponse: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/web/multipart/MaxUploadSizeExceededException.html
- Spring Framework — Spring MVC validation and MethodArgumentNotValidException: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework — ProblemDetail and Error Responses: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html
- Spring Boot 3.0 Migration Guide — server.max-http-header-size to server.max-http-request-header-size: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide
- RFC 9110 — HTTP Semantics, 400/413/414/415/422 and field size limits: https://www.rfc-editor.org/rfc/rfc9110
- RFC 6585 — 431 Request Header Fields Too Large: https://www.rfc-editor.org/rfc/rfc6585#section-5
- RFC 9457 — Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457
