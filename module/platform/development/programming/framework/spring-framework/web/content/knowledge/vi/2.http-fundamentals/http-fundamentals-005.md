# Header, Content-Type, Accept và thương lượng nội dung trong HTTP và Spring Web

Một HTTP request hay response gồm **start-line/status-line, tập header và phần body (nếu có)**. Header cung cấp thông tin để hai phía hiểu cách trao đổi dữ liệu: định dạng body, loại response mong muốn, ngôn ngữ, mã hóa truyền tải, xác thực, cache và nhiều điều kiện khác.

Trong Spring MVC hoặc Spring WebFlux, hai header dễ bị nhầm nhất là **Content-Type** và **Accept**:

- **Content-Type** mô tả **body đang được gửi có dạng gì**. Trong request, client khai báo body gửi tới server. Trong response, server khai báo body trả về cho client.
- **Accept** trong HTTP request mô tả **client chấp nhận kiểu dữ liệu nào cho response**. Nó không khai báo kiểu body client đã gửi.
- **Content negotiation (thương lượng nội dung)** là quá trình chọn một **representation** phù hợp cho cùng một tài nguyên dựa trên khả năng của server và sở thích được client nêu bằng header như Accept, Accept-Language và Accept-Encoding.

Ví dụ:

~~~http
POST /api/messages HTTP/1.1
Host: example.test
Content-Type: application/json
Accept: text/plain

{"text":"Xin chào"}
~~~

Client gửi **JSON** và muốn nhận **plain text**. Việc gửi JSON không buộc server phải trả JSON. Nếu endpoint thực sự có khả năng đọc JSON và trả text/plain, trao đổi này là hợp lệ; nếu endpoint không hỗ trợ kết hợp ấy, server có thể trả lỗi tương ứng.

## 1. Cấu trúc thông điệp và vai trò của header

Một HTTP/1.1 request minh họa:

~~~http
GET /api/books/7 HTTP/1.1
Host: example.test
Accept: application/json
Accept-Language: vi
Authorization: Bearer TOKEN_EXAMPLE
~~~

Request GET trên không có body. Server có thể trả một response như:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Content-Language: vi
Cache-Control: private, max-age=60

{"id":7,"title":"HTTP căn bản"}
~~~

Các dòng này là **ví dụ về giao thức**, không phải kết quả tự động bảo đảm từ mọi ứng dụng Spring. Response thực tế có thể có thêm Content-Length, Date, Transfer-Encoding, Vary, headers do proxy thêm và thứ tự khác.

**Phân biệt ba vị trí:**

1. **Start-line/status-line:** phương thức, đường dẫn và phiên bản HTTP (request); hoặc status code (response), theo biểu diễn HTTP/1.x.
2. **Header field:** cặp tên–giá trị có vai trò xác định theo tiêu chuẩn, ví dụ **Content-Type: application/json**.
3. **Body/content:** bytes của representation, có thể là JSON, văn bản, ảnh, multipart... hoặc rỗng.

Trong HTTP/2 và HTTP/3, cách mã hóa trên dây không phải các dòng text HTTP/1.1 y nguyên: có pseudo-headers và framing nhị phân, nhưng **ý nghĩa ngữ nghĩa** của phần lớn field như Content-Type và Accept vẫn được duy trì.

### Quy tắc thực tế về header

- Tên field về ngữ nghĩa **không phân biệt chữ hoa/thường**: Content-Type và content-type chỉ cùng một tên. Khi thao tác qua framework, dùng API header thay vì tự viết parser chuỗi.
- Một số field cho phép **danh sách giá trị** phân tách dấu phẩy, nhưng **không được tự động gộp mọi header** bằng dấu phẩy. Điển hình Set-Cookie có quy tắc riêng.
- Thứ tự đa số header không quan trọng, nhưng thứ tự giữa các giá trị lặp lại của một số field có thể có ý nghĩa; không coi mọi header là danh sách không thứ tự.
- Header mô tả metadata, **không phải bằng chứng bảo mật** về tính đúng đắn của body. Server phải kiểm tra dữ liệu, giới hạn kích thước, xác thực quyền và không tin mù quáng giá trị do client cung cấp.
- Proxy/gateway/load balancer có thể thêm hoặc thay header. Khi debug cần xác định đang quan sát request từ client, sau reverse proxy hay trong ứng dụng.

## 2. Những header thường gặp và cách phân nhóm

| Header | Hướng phổ biến | Ý nghĩa / khi nào dùng |
|---|---|---|
| Content-Type | Request và response có body | Media type của representation hiện tại |
| Accept | Request | Những media type client nhận được trong response |
| Accept-Language | Request | Các ngôn ngữ ưu tiên, ví dụ vi, en |
| Content-Language | Response | Ngôn ngữ của representation trả về |
| Accept-Encoding | Request | Các content coding như gzip, br mà client hiểu |
| Content-Encoding | Response hoặc request có mã hóa | Body đã được áp dụng content coding nào |
| Vary | Response | Các request header làm thay đổi representation, giúp cache chọn đúng phiên bản |
| Authorization | Request | Thông tin xác thực theo scheme, ví dụ Bearer |
| WWW-Authenticate | Response | Challenge cho cơ chế xác thực, thường xuất hiện cùng 401 |
| Cookie / Set-Cookie | Request / response | Truyền cookie về server / thiết lập cookie trên client |
| Cache-Control | Cả hai | Chỉ thị cache, tùy ngữ cảnh request/response |
| ETag / If-None-Match | Response / request | Validator và conditional request hỗ trợ cache |
| Origin | Request | Nguồn (origin) của trình duyệt, quan trọng trong CORS |
| Access-Control-Allow-Origin | Response | Chính sách cho browser chia sẻ response khác origin |
| Location | Response | URI đích cho redirect hoặc resource được tạo |
| Content-Disposition | Chủ yếu response; cũng dùng trong multipart part | Cách hiển thị/tải xuống hoặc mô tả từng multipart part |
| Content-Length | Request/response phù hợp | Kích thước content tính bằng byte khi được xác định, không bằng số ký tự Unicode |

**Không nên dùng dấu hiệu header để suy ra mọi hành vi ứng dụng.** Authorization không bảo đảm request được phép truy cập; Accept-Language không bảo đảm server có bản dịch; Accept-Encoding không bảo đảm server đã bật nén; Content-Type không chứng minh body parse được.

### Content-Type không phải Content-Encoding

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Content-Encoding: gzip
Vary: Accept-Encoding
~~~

Nội dung có ý nghĩa logic là **JSON**, nhưng bytes được **nén gzip** trên đường truyền. Client giải mã gzip trước khi parse JSON. Content-Type chỉ loại representation sau khi bỏ các content coding; Content-Encoding chỉ cách giải mã bytes đã áp dụng content coding. MIME type **không thay thế** thuật toán nén.

## 3. Content-Type: khai báo kiểu dữ liệu đang gửi

Media type có dạng **type/subtype**, đôi khi kèm tham số:

~~~http
Content-Type: application/json
Content-Type: text/plain; charset=UTF-8
Content-Type: text/html; charset=utf-8
Content-Type: application/problem+json
Content-Type: application/octet-stream
Content-Type: application/x-www-form-urlencoded
Content-Type: multipart/form-data; boundary=BOUNDARY_123
~~~

**type/subtype** nhận diện cách diễn giải body, ví dụ JSON khác XML dù biểu diễn cùng một đối tượng sách. Với media type có hậu tố **+json**, ví dụ application/problem+json, hậu tố thể hiện cấu trúc JSON nhưng vẫn là **media type cụ thể**; client và server cần thống nhất hỗ trợ media type ấy, không suy rằng mọi endpoint chỉ hỗ trợ application/json sẽ chấp nhận tất cả biến thể +json trong mọi điều kiện.

**charset** cho biết character encoding khi media type có tham số tương ứng, điển hình văn bản. Trong ứng dụng hiện đại, JSON trao đổi giữa các hệ thống thường dùng UTF-8; không nên dựa vào việc gắn charset tùy ý trong Content-Type để xử lý mọi vấn đề encoding.

**multipart boundary** ngăn cách từng part trong body. Các part có thể có Content-Disposition, Content-Type riêng. Khi dùng browser FormData hay công cụ HTTP client tạo multipart tự động, **để client tự gắn Content-Type kèm boundary**; tự đặt thủ công **multipart/form-data** mà không có boundary thường làm server không parse được.

### Content-Type trong request

~~~http
POST /api/books HTTP/1.1
Host: example.test
Content-Type: application/json
Accept: application/json

{"title":"HTTP căn bản"}
~~~

Ở đây server phải **giải mã request body theo JSON** nếu endpoint chấp nhận JSON. Khi client gửi request body là chuỗi văn bản thô nhưng tự nhận Content-Type: application/json, phép parse JSON có thể thất bại (thường 400 cho dữ liệu không hợp lệ). Không được coi Content-Type là công cụ tự chuyển đổi nội dung.

### Content-Type trong response

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain; charset=UTF-8

OK
~~~

Server nói body hiện tại là văn bản. Nếu trả JSON nhưng gắn text/plain, client hoặc browser có thể diễn giải sai; chính sách MIME sniffing của browser cũng có thể ảnh hưởng. Với web content, cấu hình Content-Type chính xác và cân nhắc **X-Content-Type-Options: nosniff** để ngăn browser đoán type trong những trường hợp liên quan.

**Khi GET không gửi body**, thông thường **không cần Content-Type trên request**; nếu muốn nhận JSON, hãy gửi **Accept: application/json**. Header Content-Type không phải “loại API đang gọi” và cũng không đồng nghĩa với kết quả mong muốn.

## 4. Accept: mô tả những response client có thể nhận

Cú pháp điển hình:

~~~http
Accept: application/json
Accept: text/plain
Accept: text/html, application/json
Accept: application/json, text/plain;q=0.5
Accept: application/*;q=0.8, text/plain;q=0.6
Accept: */*
~~~

**Ý nghĩa:**

- **application/json:** chấp nhận JSON.
- **text/plain:** chấp nhận văn bản thuần.
- **application/\***: chấp nhận các subtype trong type application.
- **\*/\***: chấp nhận mọi media type.
- **q:** hệ số mức độ ưu tiên (quality weight), mặc định **1** khi không khai báo, từ **0** đến **1**. **q=0** nghĩa là không chấp nhận loại được biểu đạt ở media range tương ứng.
- **Mức độ cụ thể:** media range khớp cụ thể và các tham số có thể ảnh hưởng cách xác định ứng viên phù hợp; không đơn giản chọn “phần tử đầu tiên của header”.

Ví dụ request:

~~~http
Accept: application/json;q=0.9, text/plain;q=0.5
~~~

Client ưu tiên JSON so với plain text. Nếu server có thể trả cả hai, logic thương lượng có thể chọn JSON theo độ ưu tiên, sau khi xét media type khả dụng và các quy tắc phù hợp. Nếu server **chỉ hỗ trợ text/plain**, trả plain text vẫn hợp lệ vì client cho phép q=0.5.

**Không phải server buộc trả media type đầu tiên trong danh sách.** Accept mô tả giới hạn và sở thích của client; server còn phải có khả năng tạo representation. Các thuật toán chi tiết về xếp hạng có thể khác giữa framework/server, vì vậy không nên tự phát biểu một công thức sắp xếp tuyệt đối áp dụng mọi trường hợp.

### Khi không có Accept

Thiếu Accept thường có ý nghĩa rằng client **không chỉ rõ ràng buộc định dạng response**; server có thể chọn loại mặc định. Công cụ dòng lệnh **curl** thường gửi **Accept: */*** theo mặc định (có thể xem bằng curl -v).

Ví dụ browser khi điều hướng trang HTML thường đề xuất text/html cùng vài media type khác; một lời gọi API từ mã nguồn có thể chủ động đặt Accept: application/json. Vì thế **đừng dựa vào header mặc định của trình duyệt để chứng minh một API hỗ trợ định dạng nào**.

### Accept không đổi request body

~~~http
POST /api/books HTTP/1.1
Content-Type: text/plain
Accept: application/json

sach 1
~~~

Client yêu cầu response JSON nhưng gửi **plain text**. Nếu endpoint chỉ đọc JSON, có thể trả **415 Unsupported Media Type**; việc Accept=application/json không làm body text/plain trở thành JSON. Đây là lỗi cấu hình HTTP client rất thường gặp.

## 5. Content negotiation: một tài nguyên, nhiều representation

Một tài nguyên có thể có các cách biểu diễn:

~~~text
GET /api/status
           |
           | request Accept?
           +--> application/json --> {"status":"ok"}
           +--> text/plain       --> status=ok
           +--> text/html        --> <p>status=ok</p>
           +--> không khớp       --> 406 (nếu server không cung cấp fallback)
~~~

Đây là **mô hình khái niệm**. Để hoạt động, server cần thật sự cài đặt các representation; không phải Spring tự động biết biến mọi object thành JSON, XML, HTML và plain text chỉ vì client yêu cầu.

**Các bước giải thích phía server:**

1. Phát hiện resource theo URL, method và các điều kiện routing khác.
2. Xem request body có tồn tại không, Content-Type của request có được endpoint hỗ trợ không và có converter/decoder đọc được không.
3. Đọc Accept (và các chiến lược cấu hình khác) để xác định media type response mà client mong muốn.
4. Giao giữa **những gì client chấp nhận** với **những gì endpoint và message converter/encoder có thể tạo ra**.
5. Chọn handler/representation phù hợp, serialize body và trả Content-Type của response tương ứng.
6. Nếu không thể chọn, có thể trả **406**; nếu không thể tiêu thụ request body do media type không hỗ trợ, có thể trả **415**. Các loại lỗi khác có thể phát sinh trước hoặc sau quá trình thương lượng.

### Content negotiation chủ động và thương lượng thay thế

**Server-driven / proactive negotiation:** client gửi Accept, Accept-Language, Accept-Encoding; server chọn representation. Đây là cách sử dụng phổ biến của Spring REST controller.

**Agent-driven / reactive negotiation theo nghĩa HTTP:** server có thể cung cấp thông tin lựa chọn hoặc phản hồi như 300/406 để client tự chọn. Chữ **reactive** ở đây là thuật ngữ trong HTTP content negotiation, **không liên quan trực tiếp** đến Spring WebFlux/Reactive Streams.

### Content-Type, Accept và kết quả minh họa

| Request gửi | Server hỗ trợ | Kết quả |
|---|---|---|
| Content-Type JSON, Accept JSON | POST đọc JSON và trả JSON | Thành công nếu body hợp lệ |
| Content-Type JSON, Accept text/plain | POST đọc JSON, trả được text/plain | Thành công nếu có nhánh text/plain |
| Content-Type text/plain, Accept JSON | POST chỉ đọc JSON | Thường **415** |
| Content-Type JSON, Accept XML | POST đọc JSON nhưng chỉ trả JSON | Thường **406** |
| Content-Type JSON, Accept JSON | POST đọc JSON, nhưng body JSON hỏng | Thường **400**, không phải 415 |
| GET không body, Accept JSON | GET trả JSON | Thành công; không cần request Content-Type |
| GET không body, Accept XML | GET chỉ có JSON | Thường **406** |
| GET Accept */* | GET có nhiều representation | Server lựa chọn một representation theo cấu hình; đừng đoán loại nào nếu chưa kiểm tra |

Bảng giả định URL, method, quyền truy cập, handler và cấu hình còn lại đều hợp lệ. HTTP có trường hợp fallback, error handling hoặc media type matching khác; **không nên xem mã lỗi ở bảng là lời hứa tuyệt đối cho mọi web server**.

## 6. Spring MVC: consumes, produces và HttpMessageConverter

Trong **Spring MVC**, controller định tuyến request bằng @RequestMapping và các shortcut như @GetMapping, @PostMapping. Hai thuộc tính quan trọng:

- **consumes:** điều kiện ánh xạ dựa trên **Content-Type của request**. Ví dụ consumes = application/json nghĩa là handler chỉ nhận request representation phù hợp application/json.
- **produces:** điều kiện ánh xạ dựa trên **Accept của request** và khả năng sinh response. Ví dụ produces = application/json biểu thị handler dành cho client chấp nhận JSON.
- **headers:** các điều kiện khớp header khác, ví dụ headers = "X-Client-Version=1", nhưng **nên dùng consumes và produces cho Content-Type/Accept** thay vì xử lý bằng điều kiện headers thủ công.
- **@RequestBody:** yêu cầu Spring đọc/deserialize body thành tham số Java, phụ thuộc converter và media type.
- **@ResponseBody** hoặc **@RestController:** yêu cầu Spring viết giá trị Java thành response body.
- **ResponseEntity:** điều khiển status code, headers và body; Content-Type có thể được chỉ rõ trong response khi cần.

**Luồng đơn giản của Spring MVC:**

~~~text
Client
  -> Servlet container
  -> DispatcherServlet
  -> HandlerMapping lọc path/method/consumes/produces
  -> HandlerAdapter + HttpMessageConverter đọc @RequestBody
  -> Controller gọi business service
  -> ReturnValueHandler + HttpMessageConverter ghi response
  -> Content-Type + HTTP response
~~~

Các converter quen thuộc: **StringHttpMessageConverter** xử lý String/text, **MappingJackson2HttpMessageConverter** xử lý JSON khi Jackson/config tương ứng được khai báo (tên class/converter cụ thể có thể thay đổi theo thế hệ Spring). XML cần dependency và converter phù hợp; không nên chỉ thêm produces="application/xml" rồi kỳ vọng object tự động có XML hợp lệ.

Spring MVC mặc định ưu tiên **Accept header** để suy ra representation được yêu cầu trong các bản Spring hiện đại. Có thể cấu hình thêm chiến lược query parameter nếu cần; **phụ thuộc đuôi .json/.xml của path làm nguồn quyết định media type không còn là mặc định và thường không được khuyến khích** vì mơ hồ routing và rủi ro bảo mật.

## 7. Thực hành Spring Boot + Spring MVC: ví dụ chạy được

Tạo ứng dụng Spring Boot từ **https://start.spring.io/**, chọn **Java**, **Maven**, **Spring Web**, JDK tương thích với phiên bản Boot đã chọn (Java 17+ là mức nền phù hợp cho Boot 3.x/4.x). Chọn package name **example.media** hoặc thay toàn bộ package tương ứng trong hai file sau. Starter MVC được Spring Initializr chọn theo thế hệ Boot (ví dụ Boot 3.x dùng spring-boot-starter-web, còn Boot 4.x dùng spring-boot-starter-webmvc).

**File src/main/java/example/media/MediaDemoApplication.java:**

~~~java
package example.media;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MediaDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(MediaDemoApplication.class, args);
    }
}
~~~

**File src/main/java/example/media/MediaController.java:**

~~~java
package example.media;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class MediaController {

    // Cùng URI, nhưng representation JSON cho client nhận JSON.
    @GetMapping(path = "/greeting",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Message greetingJson() {
        return new Message("Hello Lan");
    }

    // Cùng URI, representation plain text cho client nhận text/plain.
    @GetMapping(path = "/greeting",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String greetingText() {
        return "Hello Lan";
    }

    // Đọc JSON request body và viết JSON response body.
    @PostMapping(path = "/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Message echo(@RequestBody Message input) {
        return new Message(input.text());
    }

    public record Message(String text) {
    }
}
~~~

**Giải thích mã:**

- Hai handler GET có **cùng path và method** nhưng điều kiện produces khác nhau, cho phép chọn representation theo Accept phù hợp.
- Với GET JSON, Spring và Jackson serialize **Message** thành JSON; với GET plain text, Spring xử lý String như văn bản.
- POST /echo dùng consumes để nhận JSON và produces để trả JSON; @RequestBody chuyển JSON thành record Message.
- Không có database, network client hoặc dependency ngoài Spring Web; ví dụ tập trung đúng vào header/media type.
- Controller ở package **example.media**, cùng package/nhánh con của lớp @SpringBootApplication, giúp component scan tìm thấy.

### Khởi động

Trong thư mục dự án Maven đã giải nén:

~~~bash
# macOS / Linux
./mvnw spring-boot:run
~~~

Trên Windows PowerShell hoặc Command Prompt, chạy lệnh tương đương:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Chạy các lệnh curl sau từ **một terminal thứ hai**. Mỗi ví dụ yêu cầu ứng dụng đang lắng nghe tại http://localhost:8080 và chưa có ứng dụng khác chiếm cổng.

### Trường hợp A — GET yêu cầu JSON

~~~bash
curl -i -H "Accept: application/json" "http://localhost:8080/api/greeting"
~~~

Status và response media type dự kiến:

~~~http
HTTP/1.1 200
Content-Type: application/json
~~~

Body JSON dự kiến:

~~~json
{"text":"Hello Lan"}
~~~

Các header phụ, charset và dòng status chi tiết tùy phiên bản/server; nội dung JSON trên mới là phần cần kiểm tra.

### Trường hợp B — GET yêu cầu plain text

~~~bash
curl -i -H "Accept: text/plain" "http://localhost:8080/api/greeting"
~~~

Response body dự kiến:

~~~text
Hello Lan
~~~

Response Content-Type thuộc **text/plain** (có thể kèm tham số charset). Cùng URI nhưng hai representation khác nhau; đây là ví dụ rõ nhất của **content negotiation theo media type**.

### Trường hợp C — GET yêu cầu XML không được hỗ trợ

~~~bash
curl -i -H "Accept: application/xml" "http://localhost:8080/api/greeting"
~~~

Status dự kiến:

~~~http
HTTP/1.1 406
~~~

Ứng dụng mẫu không có GET handler phù hợp produces=application/xml nên Spring MVC trả **406 Not Acceptable** theo mặc định. Body lỗi và các response header của lỗi có thể do phiên bản Boot/Spring tùy biến; **không khẳng định JSON lỗi hay nội dung lỗi cố định**.

### Trường hợp D — POST gửi JSON, nhận JSON

~~~bash
curl -i -X POST "http://localhost:8080/api/echo" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  --data '{"text":"Hello Spring"}'
~~~

Body JSON dự kiến:

~~~json
{"text":"Hello Spring"}
~~~

Chú ý hai header có hai nhiệm vụ riêng: **Content-Type** giúp chọn/đọc body request; **Accept** giúp chọn/ghi body response.

**Windows PowerShell:** có thể chạy cùng cú pháp với **curl.exe** và đặt lệnh trên một dòng để tránh khác biệt dấu xuống dòng hoặc alias curl trong Windows PowerShell 5.1:

~~~powershell
curl.exe -i -X POST "http://localhost:8080/api/echo" -H "Content-Type: application/json" -H "Accept: application/json" --data '{"text":"Hello Spring"}'
~~~

Nếu môi trường PowerShell cũ thay đổi quoting khi gọi native command, dùng file body JSON hoặc cú pháp escape thích hợp của phiên bản shell; điều quan trọng là **bytes gửi đi phải là JSON hợp lệ**. Cũng có thể dùng Postman/HTTPie.

### Trường hợp E — POST gửi sai Content-Type

~~~bash
curl -i -X POST "http://localhost:8080/api/echo" \
  -H "Content-Type: text/plain" \
  -H "Accept: application/json" \
  --data '{"text":"Hello Spring"}'
~~~

Status dự kiến:

~~~http
HTTP/1.1 415
~~~

Dù body trông như JSON, client khai báo text/plain trong khi mapping chỉ consumes application/json. Spring MVC thường dừng ở điều kiện media type, trả **415 Unsupported Media Type**; không cần dựa vào nội dung chuỗi để chọn handler.

### Trường hợp F — POST gửi JSON đúng, yêu cầu response XML

~~~bash
curl -i -X POST "http://localhost:8080/api/echo" \
  -H "Content-Type: application/json" \
  -H "Accept: application/xml" \
  --data '{"text":"Hello Spring"}'
~~~

Status dự kiến:

~~~http
HTTP/1.1 406
~~~

Client gửi body JSON hợp lệ và mapping có thể đọc, nhưng không có representation XML phù hợp với produces. **406** liên quan response được yêu cầu, **415** liên quan media type của request content.

### Trường hợp G — Header đúng nhưng JSON hỏng

~~~bash
curl -i -X POST "http://localhost:8080/api/echo" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  --data '{"text":'
~~~

Status dự kiến:

~~~http
HTTP/1.1 400
~~~

Định dạng được khai báo **đúng** nhưng payload JSON **sai cú pháp**. HttpMessageConverter không parse được, thường trả **400 Bad Request**. Như vậy không thể suy mọi lỗi body thành 415.

### Trường hợp H — Thiếu Accept hoặc Accept: */*

~~~bash
curl -i "http://localhost:8080/api/greeting"
~~~

Với **hai mapping produces khác nhau**, client không chỉ rõ định dạng mong muốn. Framework có thể chọn theo quy tắc mapping/converter thực tế; **không dự đoán cứng JSON hay text/plain** trong tình huống mở này. Khi client yêu cầu một representation cụ thể, hãy đặt Accept rõ ràng để kiểm thử có tính xác định.

## 8. Cách Spring xử lý @RequestBody, @ResponseBody và converter

Có bốn khái niệm phối hợp nhưng độc lập:

**(1) Handler mapping:** xác định method controller nào đủ điều kiện path, HTTP method, consumes, produces và các ràng buộc khác.

**(2) Request decoding:** @RequestBody nhờ một reader/converter tương thích media type cùng kiểu Java đích. Nếu header đúng nhưng payload sai cấu trúc (JSON hỏng), lỗi phát sinh **trong quá trình đọc**, không nhất thiết là lỗi mapping.

**(3) Return value / response encoding:** @RestController đưa return value vào body. Framework tìm converter hỗ trợ kiểu Java và media type được chọn; ví dụ Jackson với JSON, String converter với text/plain.

**(4) Exception resolution:** lỗi routing, media type, deserialize và nghiệp vụ có thể được ánh xạ sang HTTP status. @RestControllerAdvice/@ExceptionHandler có thể **tùy biến status/body lỗi**, nhưng cần giữ đúng ý nghĩa giao thức.

**Không suy ra JSON chỉ vì trả Java object.** Nếu không có converter tương thích hoặc dependency bị loại, endpoint có thể không tạo được representation như mong đợi. Ngoài ra **ResponseEntity.ok(...).contentType(...)** đặt explicit response Content-Type; cần bảo đảm **body thật sự trùng loại được tuyên bố** và không mâu thuẫn với điều kiện produces.

### consumes và produces khác @RequestHeader

~~~java
@GetMapping(path = "/example",
        headers = "X-Channel=mobile",
        produces = MediaType.APPLICATION_JSON_VALUE)
public Message example() {
    return new Message("Hello");
}
~~~

Đây là **đoạn method minh họa đặt trong MediaController**, không phải file Java độc lập. Method chỉ phù hợp khi client gửi **X-Channel: mobile** và Accept phù hợp JSON. Trong trường hợp không có header tùy chỉnh, lỗi mapping không nhất thiết là 406/415; cần kiểm tra điều kiện nào không khớp. Dùng **@RequestHeader("X-Channel")** để nhận giá trị header làm tham số khi cần, với cơ chế required/defaultValue rõ ràng.

## 9. WebFlux cũng thương lượng nội dung nhưng dùng reactive codecs

Spring WebFlux dùng những annotation tương tự trong **annotated controllers**:

~~~java
@PostMapping(path = "/echo",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
public Mono<Message> echo(@RequestBody Mono<Message> input) {
    return input.map(message -> new Message(message.text()));
}
~~~

**Chỉ là method minh họa**; đoạn này cần đặt trong WebFlux @RestController có import Reactor Mono, MediaType, PostMapping, RequestBody và record Message thích hợp. Trong WebFlux, **HttpMessageReader/HttpMessageWriter (codecs)** đọc/ghi nội dung reactive thay vì chuỗi converter đồng bộ đặc trưng của MVC.

Điểm cần nhớ:

- **Content-Type/Accept, consumes/produces, HTTP 406/415** giữ nguyên ý nghĩa giao thức ở cả MVC và WebFlux.
- WebFlux có thể phản hồi với **Mono/Flux**, streaming và non-blocking I/O; điều đó không thay đổi vai trò hai header.
- **Content-Type: text/event-stream** thường gắn với Server-Sent Events (SSE); client thường dùng **Accept: text/event-stream** khi muốn stream. Streaming còn cần cấu hình flush, serialization, timeout, proxy phù hợp.
- **Flux** nhiều phần tử không đồng nghĩa với một JSON document hợp lệ nếu gửi từng fragment tùy ý. Chọn media type serialization thích hợp: application/json (ví dụ một JSON array khi writer hỗ trợ), application/x-ndjson cho các JSON record phân cách dòng hoặc text/event-stream cho SSE, theo contract API cụ thể.

**Lưu ý:** phép thương lượng không biến blocking API thành reactive. Nếu service gọi JDBC/JPA blocking ngay trên event-loop, dùng WebFlux có thể gây nghẽn bất kể headers đã cấu hình đúng.

## 10. Accept-Language, Accept-Encoding và Vary

Content negotiation không chỉ xoay quanh JSON/XML. Có thể một resource có nhiều phiên bản ngôn ngữ hoặc content coding:

~~~http
GET /guide HTTP/1.1
Accept: text/html
Accept-Language: vi, en;q=0.7
Accept-Encoding: br, gzip;q=0.8
~~~

Server có thể chọn HTML tiếng Việt, nén Brotli nếu hỗ trợ, và trả:

~~~http
HTTP/1.1 200 OK
Content-Type: text/html; charset=UTF-8
Content-Language: vi
Content-Encoding: br
Vary: Accept-Language, Accept-Encoding

[body đã nén, không thể đọc trực tiếp như text]
~~~

Đây là **ví dụ thiết kế**, không phải header Spring Boot mặc định tự thêm tất cả. Việc trả nội dung theo ngôn ngữ và nén HTTP cần cấu hình thích hợp tại ứng dụng hoặc proxy.

### Vary cần cho cache đúng phiên bản

Giả sử **GET /guide** trả tiếng Việt nếu Accept-Language: vi và trả tiếng Anh nếu Accept-Language: en. Nếu shared cache chỉ khóa theo URL, có nguy cơ trả **bản tiếng Việt cho client muốn tiếng Anh**. Header **Vary: Accept-Language** yêu cầu cache tính đến header ấy khi chọn bản lưu. Nếu body còn được thay đổi bởi Accept, có thể cần **Vary: Accept**. Nếu nén thay đổi representation trên dây, có thể cần **Vary: Accept-Encoding**.

**Vary là khai báo cache key**, không có tác dụng tự tạo bản dịch, nén, hay tự định tuyến controller. Chỉ khai báo những header thực sự có ảnh hưởng đến representation; khai báo không chính xác có thể làm giảm hit rate hoặc gây cache trả sai. Khi có dữ liệu riêng theo người dùng, cần thêm chính sách cache phù hợp (Cache-Control: private/no-store, v.v.), không dựa riêng vào Vary.

### Accept-Language là sở thích, không phải lệnh tuyệt đối

Sở thích ngôn ngữ của browser có thể không đại diện cho lựa chọn thực tế. Nếu người dùng đã chọn ngôn ngữ rõ ràng trong UI/profile, thường ưu tiên lựa chọn ấy; nếu dùng Accept-Language, phải có fallback hợp lý. Trong Spring, locale resolution và việc dịch message thông qua MessageSource là cơ chế cần cấu hình hoặc tích hợp; **chỉ gửi Accept-Language không tự biến mọi String thành bản dịch**.

### Accept-Encoding khác Transfer-Encoding

Content-Encoding gzip/ br mô tả **nội dung được mã hóa/nén**. **Transfer-Encoding: chunked** trong HTTP/1.1 nói về cách framing thông điệp trên kết nối; nó không phải media type và không phải thuật toán nén dữ liệu. HTTP/2/3 có framing riêng. Khi debug, phân biệt **content length theo byte**, nén nội dung và cách vận chuyển.

## 11. Form, upload file, JSON và cấu hình client

**JSON API:**

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json
Accept: application/json

{"productId":5,"quantity":2}
~~~

Trong Spring, dùng @RequestBody DTO để đọc JSON; **@RequestParam** phù hợp với query/form parameters, không có nghĩa sẽ deserialize nguyên JSON object.

**HTML form truyền key/value:**

~~~http
POST /login HTTP/1.1
Content-Type: application/x-www-form-urlencoded

username=lan&remember=true
~~~

Đây là URL-encoded form body, **không phải JSON**, dù cả hai đều chứa thông tin có cấu trúc. Spring MVC có binding phù hợp với form parameters.

**Upload file:**

~~~http
POST /upload HTTP/1.1
Content-Type: multipart/form-data; boundary=ExampleBoundary

--ExampleBoundary
Content-Disposition: form-data; name="title"

Mau
--ExampleBoundary
Content-Disposition: form-data; name="file"; filename="note.txt"
Content-Type: text/plain

Example file content
--ExampleBoundary--
~~~

Đây là body multipart dạng **minh họa giao thức**. Trong chương trình thực tế, dùng **MultipartFile/@RequestPart** tương ứng với cấu hình Spring MVC, đặt giới hạn kích thước upload, validate media type/nội dung và tên file. Không tin content type do người dùng cung cấp để kết luận file vô hại.

### Fetch API trên browser

Khi gửi JSON:

~~~javascript
const response = await fetch("/api/echo", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Accept": "application/json"
  },
  body: JSON.stringify({ text: "Hello Spring" })
});

if (!response.ok) {
  throw new Error("HTTP " + response.status);
}

const data = await response.json();
console.log(data.text);
~~~

Đoạn JavaScript trên giả định cùng origin và endpoint JSON mẫu đã triển khai; kết quả console khi request thành công là:

~~~text
Hello Spring
~~~

**Lỗi dễ gặp:** gọi response.json() khi server trả HTML/text hoặc status 204 No Content; việc client đặt Accept: application/json **không bảo đảm server luôn trả JSON**, nhất là ở các response lỗi/proxy. Trước khi parse, có thể kiểm tra status và response Content-Type theo hợp đồng API.

Khi gửi **FormData** chứa file, thường **không tự đặt Content-Type**:

~~~javascript
const form = new FormData();
form.append("title", "Mau");
form.append("file", selectedFile);

await fetch("/upload", {
  method: "POST",
  body: form
});
~~~

Đây là đoạn JavaScript minh họa giả định có biến **selectedFile** là File hợp lệ và server có endpoint upload; browser tự sinh multipart boundary.

### Postman, curl và Spring WebClient

Trong Postman chọn **Body → raw → JSON** thường đồng bộ loại body với Content-Type thích hợp, nhưng vẫn phải kiểm tra tab Headers.

Với curl:

- **-H "Content-Type: application/json"** khai báo request body.
- **-H "Accept: application/json"** yêu cầu response JSON.
- **--data** gửi nội dung; kiểm tra Content-Type thực tế vì lệnh curl có mặc định liên quan application/x-www-form-urlencoded khi dùng --data mà không ghi đè.
- **-i** in response headers cùng body; **-v** quan sát request và response, nhưng tránh đăng công khai Authorization/cookie khi chia sẻ log.
- **--compressed** yêu cầu/giải mã nén theo hỗ trợ của curl khi cần quan sát Accept-Encoding.

Với Spring WebClient, có thể dùng **contentType(MediaType.APPLICATION_JSON)** để khai báo body gửi và **accept(MediaType.APPLICATION_JSON)** để yêu cầu response. Hai phương thức vẫn độc lập như HTTP. Mỗi client có thể tự điền header tùy request/body inserter; hãy kiểm tra request thực tế nếu kết quả không như kỳ vọng.

## 12. Những lỗi thường gặp: 400, 404, 405, 406, 415, 500

| Status | Tình huống tiêu biểu | Kiểm tra đầu tiên |
|---|---|---|
| **400 Bad Request** | JSON body hỏng, thiếu tham số bắt buộc, binding sai | Cú pháp body, trường DTO, required parameters |
| **404 Not Found** | Không có route/resource phù hợp | URL, context path, controller registration |
| **405 Method Not Allowed** | URL đúng kiểu nhưng method không được phép | GET/POST/PUT và @GetMapping/@PostMapping |
| **406 Not Acceptable** | Không tạo được representation phù hợp Accept | Accept, produces, message converter, available response types |
| **415 Unsupported Media Type** | Không nhận/đọc được request content theo media type | Content-Type request, consumes, converter/decoder |
| **500 Internal Server Error** | Lỗi server trong xử lý/serialize hoặc lỗi không được handle | Logs, stack trace, serialization, lỗi code |

Đây là **nguyên nhân thường gặp**, không phải duy nhất. Cấu hình @ControllerAdvice, security layer, proxy, middleware và cơ chế riêng của server có thể trả các status khác; không sửa header một cách máy móc trước khi biết lỗi xảy ra ở tầng nào.

### Ví dụ debug 406

Giả sử:

~~~java
@GetMapping(path = "/report",
        produces = MediaType.APPLICATION_JSON_VALUE)
public Report report() {
    return new Report(1);
}
~~~

Đây là **method minh họa** phụ thuộc một kiểu **Report** hợp lệ và controller bao quanh. Client gọi:

~~~http
GET /report HTTP/1.1
Accept: application/xml
~~~

Nếu server chỉ có representation JSON, không có fallback và mapping theo produces, lỗi **406**. Cách xử lý: sửa **Accept** client nếu khách thật sự muốn JSON; hoặc cung cấp representation XML với message writer/converter và hợp đồng API tương ứng nếu cần XML. **Không đổi Content-Type của GET request** để chữa lỗi này.

### Ví dụ debug 415

~~~java
@PostMapping(path = "/report",
        consumes = MediaType.APPLICATION_JSON_VALUE)
public void submit(@RequestBody Report report) {
    // xử lý báo cáo
}
~~~

Đây cũng là **method minh họa**, không độc lập. Client gửi **Content-Type: text/plain**. Nếu muốn gửi JSON thì thay body thành JSON hợp lệ và khai báo đúng **Content-Type: application/json**. Nếu nghiệp vụ phải chấp nhận text/plain, thiết kế handler/reader khác cho loại ấy. **Không đổi Accept** để chữa 415.

### Checklist khi dùng Spring Boot

1. **Request thực gửi là gì?** Dùng curl -v/Postman console/browser DevTools Network để xem **đường dẫn, method, Content-Type, Accept và body bytes**.
2. **Controller ánh xạ thế nào?** Xem @GetMapping/@PostMapping, consumes/produces, headers, param conditions và tiền tố @RequestMapping ở class.
3. **Dependency/converter có đủ không?** Với JSON kiểm tra Jackson/config tương ứng; với XML kiểm tra converter XML đúng phiên bản.
4. **Body thực sự hợp lệ không?** Content-Type: application/json không làm một chuỗi bất kỳ thành JSON.
5. **Lỗi đến từ đâu?** Controller, Spring framework, security filter, gateway hay reverse proxy? Trace request/correlation ID nếu có, đọc logs đáng tin.
6. **Response lỗi có thể cũng phải thương lượng:** nếu @ExceptionHandler chỉ trả một representation nhất định, client có thể gặp kết quả khác dự kiến. Thiết kế error format nhất quán, ví dụ application/problem+json nếu API chọn chuẩn problem details.
7. **Đã test với Accept cụ thể chưa?** Test cả application/json, text/plain, application/xml và */* đúng theo contract; chỉ dựa một request từ browser là chưa đủ.
8. **Cache có tạo nhầm bản không?** Nếu nhiều representation cùng URI, kiểm tra Vary và Cache-Control ở ứng dụng lẫn CDN/proxy.

## 13. Thiết kế API có thương lượng nội dung tốt

**Khai báo hợp đồng rõ ràng:** endpoint nhận media type nào (request Content-Type) và trả media type nào (response Content-Type/Accept). Trong tài liệu OpenAPI, media type nằm ở requestBody.content và responses.<status>.content; đây là một cách giữ thiết kế và kiểm thử nhất quán.

**Đặt produces/consumes khi có giá trị:** nếu endpoint chỉ nhận JSON, khai báo rõ consumes=application/json cho POST/PUT/PATCH có body; nếu endpoint chỉ trả JSON, khai báo produces=application/json. Điều này giúp phân loại lỗi sớm, tài liệu hóa hợp đồng và lựa chọn handler phù hợp. Không gắn consumes cho GET không body chỉ để “API là JSON”.

**Tách DTO khỏi định dạng đường truyền:** business service làm việc trên domain object; controller/serializer chịu trách nhiệm đọc–ghi representation. Khi thêm định dạng XML/text, tránh nhân đôi logic nghiệp vụ.

**Không ép một URL có mọi định dạng:** nhiều representation cùng URI là khả năng của HTTP, nhưng khi hệ thống không có nhu cầu, API chỉ trả JSON là hoàn toàn hợp lý. Thêm XML/HTML vô cớ làm tăng chi phí kiểm thử, bảo trì và bề mặt rủi ro.

**Tài liệu hóa status code thực tế:** client phải xử lý 406/415/400 và response lỗi. Không hứa response JSON ở mọi lỗi nếu proxy hoặc security layer có thể trả HTML/text.

**Đặt cache đúng:** nếu dùng Accept hoặc Accept-Language để chọn nội dung có thể cache, đánh giá Vary và quy tắc cache ngay từ thiết kế, đặc biệt với CDN.

**Cẩn thận header bảo mật và CORS:** Content-Type và Accept không phải cơ chế phân quyền; CORS do browser thực thi dựa trên Origin và response Access-Control-*; CORS không thay cho authentication/authorization. Dùng Content-Type đúng với nosniff thích hợp cho tài nguyên trình duyệt xử lý.

## 14. Câu hỏi tự kiểm tra

**1. Client POST Content-Type: application/json và Accept: text/plain, nghĩa là gì?** Client gửi JSON, muốn response text/plain; server phải hỗ trợ đọc JSON và tạo plain text nếu muốn thành công.

**2. GET /api/books không có body nhưng muốn JSON, đặt header nào?** **Accept: application/json**. Không cần tự thêm request Content-Type để biểu thị loại response.

**3. Vì sao body JSON hợp lệ vẫn nhận 415?** Vì request có thể khai báo Content-Type khác với consumes, không có reader phù hợp, hoặc kiểu nội dung gửi không được endpoint chấp nhận.

**4. Vì sao Accept: application/xml có thể trả 406?** Client yêu cầu XML nhưng server không tạo được representation XML cho route đó, và không chọn fallback.

**5. q=0.5 trong Accept nói điều gì?** Đó là trọng số độ ưu tiên/chất lượng tương đối cho media range; không phải xác suất 50% server trả loại ấy.

**6. Một endpoint Spring trả record Java có luôn sinh XML khi Accept: application/xml không?** **Không**. Cần handler và converter/encoder tương ứng; chỉ có Java object chưa đủ.

**7. Vary: Accept-Language phục vụ điều gì?** Giúp cache phân biệt response biến đổi theo ngôn ngữ được yêu cầu; không tạo bản dịch.

**8. Cùng URL trả JSON và plain text có vi phạm HTTP không?** **Không**. Đây là nhiều representation của một resource, có thể được chọn bằng content negotiation nếu API triển khai.

**9. Content-Encoding: gzip có nghĩa body là loại gzip thay vì JSON không?** **Không**. Content-Type vẫn có thể là application/json; gzip mô tả cách bytes được nén.

**10. Spring MVC và WebFlux có xử lý Accept/Content-Type khác nghĩa không?** **Không**. Cùng chuẩn HTTP; cơ chế nội bộ đọc/ghi có thể khác (converter vs reactive codecs).

## 15. Tài liệu chuẩn để đối chiếu

- [MDN — HTTP headers](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers): phân loại header và ý nghĩa.
- [MDN — Content-Type](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Type): media type, charset, multipart boundary.
- [MDN — Accept](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Accept): media ranges, wildcard và q weighting.
- [MDN — HTTP content negotiation](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Content_negotiation): representation, language/encoding negotiation, Vary.
- [MDN — 406 Not Acceptable](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/406) và [415 Unsupported Media Type](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/415).
- [Spring Framework — Spring MVC Request Mapping](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html): consumes, produces, header conditions.
- [Spring Framework — Spring MVC Content Types](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/content-negotiation.html): cách Spring MVC xác định requested media types.
- [Spring Framework — WebFlux Request Mapping](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-requestmapping.html): semantics tương ứng của reactive web stack.

**Ghi nhớ:** **Content-Type = body này là gì**; **Accept = response tôi nhận được dạng nào**; **consumes = server nhận loại request body nào**; **produces = server có thể trả response media type nào**; **406 = không đáp ứng được định dạng response mong muốn**; **415 = không hỗ trợ media type của request content**.
