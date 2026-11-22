# Content-Type, Accept và thương lượng định dạng dữ liệu

## 1. Mục tiêu và bối cảnh

Khi trao đổi qua HTTP, client và server phải thống nhất **dữ liệu đang gửi là định dạng gì** và **client có thể nhận định dạng nào**. Hai header quan trọng là `Content-Type` và `Accept`. Trong Spring Boot, việc chọn handler, đọc request body và tạo response body còn liên quan đến `consumes`, `produces` và bộ chuyển đổi thông điệp (message converter/codec).

Sau bài này, bạn cần có thể:

- Phân biệt vai trò của `Content-Type` và `Accept` trong request/response.
- Đọc media type, tham số `charset`, wildcard và trọng số `q`.
- Giải thích quá trình content negotiation và các lỗi HTTP 400, 406, 415.
- Áp dụng `consumes`, `produces`, `@RequestBody` và `@RestController` trong Spring Boot.
- Kiểm tra API bằng `curl` và xử lý lỗi sai định dạng có hệ thống.

## 2. Biểu diễn tài nguyên và media type

Một URI định danh tài nguyên, chẳng hạn `/api/books/7`. Biểu diễn (representation) là nội dung gửi qua HTTP để mô tả tài nguyên đó: JSON, XML, văn bản thuần, HTML, ảnh... Cùng một tài nguyên về nguyên tắc có thể có nhiều biểu diễn; server chỉ trả về những biểu diễn nó thực sự hỗ trợ.

**Media type** có dạng `type/subtype`, có thể kèm tham số:

| Media type | Thường dùng cho |
| --- | --- |
| `application/json` | JSON của API |
| `text/plain; charset=UTF-8` | Văn bản thuần và bảng mã |
| `text/html` | Tài liệu HTML |
| `application/xml` | XML, nếu server có hỗ trợ |
| `application/x-www-form-urlencoded` | Body của form kiểu cặp khóa–giá trị |
| `multipart/form-data; boundary=...` | Body nhiều phần, thường là upload file |
| `application/octet-stream` | Dữ liệu nhị phân tổng quát |
| `application/problem+json` | Biểu diễn lỗi theo Problem Details (khi ứng dụng hỗ trợ) |

`Content-Type: application/json` cho biết body là JSON; nó không tự chứng minh body đúng cú pháp JSON. Với `multipart/form-data`, `boundary` xác định ranh giới giữa các phần: khi gửi bằng trình duyệt hoặc `curl -F`, hãy để công cụ tạo header và boundary phù hợp thay vì đặt thủ công một giá trị không khớp body.

Media type không đồng nghĩa với phần mở rộng tệp. Một đường dẫn `/books/7.json` không mặc nhiên khiến Spring trả JSON. Định dạng kết quả là một phần của giao thức và cấu hình xử lý request.

## 3. Content-Type và Accept: khác nhau ở đâu?

| Header | Xuất hiện ở đâu? | Ý nghĩa | Ví dụ |
| --- | --- | --- | --- |
| `Content-Type` | Request có body | Mô tả định dạng **body client gửi lên** | `Content-Type: application/json` |
| `Accept` | Request | Nêu định dạng **response client chấp nhận** | `Accept: application/json` |
| `Content-Type` | Response có body | Cho biết định dạng **body server thực sự trả về** | `Content-Type: application/json` |

Vì vậy, một request có thể đồng thời chứa `Content-Type: application/json` và `Accept: text/plain`: client gửi JSON nhưng muốn nhận văn bản thuần. Hai yêu cầu này độc lập; server phải hỗ trợ từng phía thì giao dịch mới thành công.

Ví dụ một vòng trao đổi HTTP đã giản lược:

~~~http
POST /api/books HTTP/1.1
Host: localhost:8080
Content-Type: application/json
Accept: application/json

{"title":"HTTP cơ bản"}
~~~

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{"id":1,"title":"HTTP cơ bản"}
~~~

Request gửi JSON, chấp nhận JSON; response thực sự là JSON. Mã trạng thái và nội dung minh họa một thao tác tạo tài nguyên thành công.

**Các điểm dễ nhầm:**

- `Accept` **không mô tả request body**; đặt `Accept: application/json` không biến một body văn bản thuần thành JSON.
- `Content-Type` trong **response** mô tả dữ liệu server đã gửi, không phải một lời đề nghị để client thương lượng tiếp.
- Với `GET` thông thường không có request body, request không cần `Content-Type`. Ngược lại, `Accept` vẫn hữu ích vì GET thường nhận response body.
- Một request không có `Accept` được hiểu là không giới hạn lựa chọn định dạng ở mức header này; `Accept: */*` cũng chấp nhận mọi media type. Điều đó **không bảo đảm** server có thể trả mọi định dạng.
- Tên header HTTP không phân biệt chữ hoa/chữ thường; cách viết `Content-Type` và `Accept` là quy ước dễ đọc.

## 4. Accept: danh sách, wildcard và trọng số q

Client có thể chấp nhận nhiều định dạng và biểu đạt mức ưu tiên tương đối:

~~~http
Accept: application/json, text/plain;q=0.7, */*;q=0.1
~~~

Cách đọc:

- `application/json` không ghi `q` nên có `q=1` (ưu tiên mặc định).
- `text/plain;q=0.7` được chấp nhận với mức ưu tiên thấp hơn JSON.
- `*/*;q=0.1` chấp nhận các media type còn lại ở ưu tiên thấp.
- `q=0` nghĩa là media range đó không được chấp nhận; `q` nằm trong khoảng `0` đến `1`.
- `application/*` khớp các subtype của `application`; `*/*` khớp rộng hơn. Các media range cụ thể có vai trò khi giải quyết mức ưu tiên của những khai báo chồng lấn.

Ví dụ `Accept: application/json;q=0, text/plain;q=1` loại JSON và ưu tiên văn bản thuần. Server phải xét **các biểu diễn có sẵn** cùng quy tắc khớp media range; không thể hứa sẽ trả JSON chỉ vì JSON có trọng số cao nếu endpoint chỉ hỗ trợ XML. `q` là mức ưu tiên ở phía client, không phải cam kết tuyệt đối về thuật toán lựa chọn của mọi server.

Phân biệt `q` với tham số của `Content-Type`:

~~~http
Content-Type: text/plain; charset=UTF-8
Accept: text/plain; q=0.8, application/json; q=1
~~~

`charset=UTF-8` mô tả cách mã hóa ký tự của văn bản đang gửi; `q=0.8` mô tả mức độ chấp nhận một biểu diễn trong `Accept`. Không đặt `q` vào `Content-Type` để yêu cầu server ưu tiên định dạng khác.

## 5. Content negotiation diễn ra thế nào?

**Content negotiation** là quá trình chọn biểu diễn response phù hợp giữa điều client chấp nhận và điều server cung cấp. Với một API Spring Boot thông thường, có thể hiểu quy trình ở mức khái niệm như sau:

1. Spring xác định các mapping ứng viên dựa vào HTTP method và đường dẫn.
2. Nếu request có body, điều kiện `consumes` và khả năng đọc media type quyết định handler/reader có chấp nhận request hay không; body sau đó được giải mã thành đối tượng Java khi cần.
3. Điều kiện `produces`, header `Accept` và các bộ ghi dữ liệu sẵn có giúp xác định biểu diễn response hợp lệ.
4. Spring ghi response body, đặt `Content-Type` thực tế và gửi status phù hợp.

Đây là mô hình để suy luận, không phải thứ tự thực thi cố định của tất cả thành phần bên trong Spring. Việc chọn mapping và kiểm tra điều kiện media type có thể xảy ra cùng nhau trước lúc gọi phương thức controller.

~~~text
Client gửi request
  |-- Content-Type: body gửi lên thuộc kiểu gì?
  |            |-- không hỗ trợ --> thường là 415
  |            '-- hỗ trợ --> đọc/parse body (sai cú pháp có thể là 400)
  |
  '-- Accept: chấp nhận kiểu response nào?
               |-- không có biểu diễn phù hợp --> thường là 406
               '-- phù hợp --> serialize và trả Content-Type thực tế
~~~

Khi server hỗ trợ cả JSON lẫn XML cho cùng một tài nguyên, `Accept` có thể giúp lựa chọn. Khi endpoint **chỉ** trả JSON, `Accept: application/xml` sẽ không tự tạo ra bộ chuyển đổi XML.

Trong Spring MVC, chiến lược content negotiation mặc định xét header `Accept`. Có thể tùy biến chiến lược bằng cấu hình, nhưng không nên giả định phần mở rộng URL như `.json` hoặc `.xml` tự bật thương lượng định dạng.

## 6. Ứng dụng trong Spring Boot và Spring MVC

Các thành phần có vai trò khác nhau:

- `@RestController`: khai báo controller có các phương thức trả dữ liệu cho response body (tương đương `@Controller` cùng cơ chế `@ResponseBody`).
- `@RequestBody`: yêu cầu Spring đọc request body và chuyển thành tham số Java nhờ `HttpMessageConverter` thích hợp.
- `@PostMapping(consumes = "...")`, `@RequestMapping(consumes = "...")`: giới hạn media type của **request** mà mapping nhận.
- `@GetMapping(produces = "...")`, `@RequestMapping(produces = "...")`: giới hạn media type của **response** mà mapping có thể tạo và dùng trong khớp `Accept`.
- `HttpMessageConverter`: đọc/ghi body trong Spring MVC; ví dụ converter dựa trên Jackson chuyển JSON thành đối tượng Java và ngược lại.
- `ResponseEntity<T>`: chủ động đặt status/header/body của response.

`consumes` và `produces` là **điều kiện khai báo**, không tự cài thư viện chuyển đổi dữ liệu. Ví dụ, khai báo `produces = "application/xml"` chưa đủ để trả XML nếu ứng dụng không có converter/serializer XML thích hợp. Với Spring Boot 3.x và dependency `spring-boot-starter-web` thông dụng, Jackson JSON được cấu hình tự động.

Trong Spring WebFlux, các annotation `@RequestBody`/`@GetMapping` và ý nghĩa `consumes`/`produces` vẫn tương tự, nhưng stack reactive sử dụng `HttpMessageReader`/`HttpMessageWriter` và codec thay cho chuỗi xử lý `HttpMessageConverter` kiểu MVC. Đừng trộn chi tiết cấu hình converter của hai stack.

## 7. Ví dụ Java 17+ chạy được: API chỉ hỗ trợ JSON

Tạo dự án **Spring Boot 3.x**, **Java 17 hoặc mới hơn**, chọn dependency **Spring Web** bằng Spring Initializr; giữ nguyên dependency quản lý bởi dự án tạo ra. Đặt hai file sau đúng package `com.example.demo`. Ví dụ chạy bằng Spring MVC, không cần database.

**Tệp `src/main/java/com/example/demo/DemoApplication.java`**

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

**Tệp `src/main/java/com/example/demo/BookController.java`**

~~~java
package com.example.demo;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/books")
public class BookController {

    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<BookResponse> create(@RequestBody BookRequest request) {
        BookResponse response = new BookResponse(1L, request.title());
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @GetMapping(path = "/{id}", produces = MediaType.APPLICATION_JSON_VALUE)
    public BookResponse find(@PathVariable long id) {
        return new BookResponse(id, "Spring HTTP");
    }

    public record BookRequest(String title) {}
    public record BookResponse(long id, String title) {}
}
~~~

Giải thích:

- POST `/api/books` chỉ nhận request có media type tương thích `application/json`, dùng Jackson chuyển JSON thành `BookRequest` và tạo JSON `BookResponse`.
- GET `/api/books/{id}` không nhận body, nên không cần `consumes`; `produces` khẳng định response JSON.
- Hai `record` là kiểu dữ liệu Java. Trong ví dụ, id được cố định ở `1` cho thao tác tạo và dữ liệu GET được tạo trong bộ nhớ: mục đích là kiểm tra HTTP/media type, chưa phải quản lý dữ liệu thực tế.
- `ResponseEntity.status(HttpStatus.CREATED)` tạo status 201 cho POST. `BookResponse` do GET trả trực tiếp thường được framework gửi với status 200.

Chạy ứng dụng tại thư mục gốc dự án:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows PowerShell có thể dùng `.\mvnw.cmd spring-boot:run`. Nếu tạo dự án Gradle, chạy `./gradlew bootRun` (Windows: `.\gradlew.bat bootRun`). Ví dụ này cần classpath/dependency của Spring Boot, nên không biên dịch chỉ bằng một lệnh `javac` độc lập.

### Thử 1 — gửi JSON và nhận JSON: thành công

~~~bash
curl -i -X POST http://localhost:8080/api/books -H "Content-Type: application/json" -H "Accept: application/json" --data '{"title":"HTTP"}'
~~~

Các phần quan trọng của phản hồi:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{"id":1,"title":"HTTP"}
~~~

Header khác như `Date`, `Content-Length` hoặc body lỗi mặc định có thể khác theo môi trường; điều cần xác minh là status 201, `Content-Type` tương thích JSON và dữ liệu JSON có `id`, `title` nêu trên.

### Thử 2 — GET với Accept phù hợp: thành công

~~~bash
curl -i -H "Accept: application/json" http://localhost:8080/api/books/7
~~~

Kỳ vọng status `200 OK`, `Content-Type` tương thích `application/json` và body:

~~~json
{"id":7,"title":"Spring HTTP"}
~~~

### Thử 3 — request body sai media type: 415

~~~bash
curl -i -X POST http://localhost:8080/api/books -H "Content-Type: text/plain" -H "Accept: application/json" --data 'HTTP'
~~~

Kỳ vọng `415 Unsupported Media Type`: POST khai báo `consumes = application/json` nhưng client gửi `text/plain`. Dù `Accept` nói muốn nhận JSON, nó không sửa được định dạng đầu vào.

### Thử 4 — response không có định dạng client chấp nhận: 406

~~~bash
curl -i -H "Accept: application/xml" http://localhost:8080/api/books/7
~~~

Kỳ vọng `406 Not Acceptable`: GET có `produces = application/json`, trong khi client chỉ chấp nhận XML. Việc cài thêm thư viện XML cũng không làm mapping này chuyển sang XML vì `produces` đã giới hạn JSON.

### Thử 5 — Content-Type đúng, JSON sai cú pháp: 400

~~~bash
curl -i -X POST http://localhost:8080/api/books -H "Content-Type: application/json" -H "Accept: application/json" --data '{"title":'
~~~

Kỳ vọng `400 Bad Request` vì cú pháp body JSON không hợp lệ nên Spring/Jackson không đọc được `@RequestBody`. Đây là lỗi khác với 415: media type được chấp nhận, **nội dung** không giải mã được. Hình dạng JSON thông báo lỗi có thể khác theo phiên bản và cấu hình Spring Boot.

Nếu đang dùng Windows PowerShell, nên gọi `curl.exe` để tránh xung đột alias `curl` của các phiên bản PowerShell cũ. Các lệnh trên có thể dùng trong terminal phù hợp với cách đặt dấu nháy.

## 8. Nếu một tài nguyên có nhiều biểu diễn thì sao?

Có thể thiết kế hai handler cùng method/URI nhưng khác điều kiện `produces`. Đoạn sau chỉ là **phần mở rộng cho BookController ở mục 7** (không phải chương trình Java độc lập):

~~~java
@GetMapping(path = "/{id}", produces = MediaType.TEXT_PLAIN_VALUE)
public String findAsText(@PathVariable long id) {
    return "Book " + id;
}
~~~

Khi bổ sung method này vào controller ở trên, client gọi GET `/api/books/7` với `Accept: application/json` để chọn handler JSON, hoặc `Accept: text/plain` để chọn handler văn bản. Response thứ hai có body `Book 7` và media type `text/plain` tương thích với `produces`. Đây là **hai biểu diễn của cùng một đường dẫn**.

Khi có nhiều handler cùng URI mà client gửi `Accept: */*` hoặc không nêu ưu tiên rõ, cần xác định và kiểm thử hành vi chọn handler; đừng mặc định một trong hai luôn thắng. Có thể chọn một định dạng mặc định trong thiết kế API, tách URI hoặc xử lý thương lượng theo một chiến lược nhất quán.

Ngoài `application/json`, có các media type mở rộng như `application/vnd.example.book+json`. Không được mặc định mọi khai báo JSON đều khớp mọi subtype `+json` khi mapping có `produces` cụ thể; cần thiết kế media type và kiểm thử mapping/converter tương ứng.

## 9. Các mã lỗi liên quan và cách phân biệt

| Hiện tượng | Mã thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| POST gửi `text/plain` vào endpoint chỉ `consumes = application/json` | `415 Unsupported Media Type` | Kiểm tra `Content-Type` request và `consumes`/reader |
| GET chỉ trả JSON, client yêu cầu `Accept: application/xml` | `406 Not Acceptable` | Kiểm tra `Accept`, `produces` và khả năng ghi response |
| Body ghi là JSON nhưng JSON sai cú pháp | `400 Bad Request` | Kiểm tra body, mapping dữ liệu và lỗi giải mã `@RequestBody` |
| Đúng media type nhưng HTTP method không được hỗ trợ tại đường dẫn | `405 Method Not Allowed` | Kiểm tra GET/POST/PUT/... và mapping |
| Không có endpoint khớp đường dẫn | `404 Not Found` | Kiểm tra path và định tuyến |

Đây là các kết quả điển hình trong API đã cấu hình như ví dụ; tầng gateway, filter, security, exception handler hoặc chiến lược negotiation tùy biến có thể thay đổi response cụ thể. `415` cũng có thể liên quan đến encoding của request. `406` không có nghĩa tài nguyên không tồn tại: vấn đề là định dạng response được chấp nhận.

Quy trình gỡ lỗi ngắn gọn:

1. Xem **request thực tế** trong Network tab, `curl -v` hoặc HTTP client: method, URI, `Content-Type`, `Accept` và byte/body gửi lên.
2. Nếu **415**, so `Content-Type` với `consumes`, xác nhận có converter đọc định dạng đó. Ví dụ `curl --data` có thể mặc định gửi form data nếu không đặt `Content-Type`; muốn JSON cần header và JSON hợp lệ.
3. Nếu **406**, so `Accept` với `produces` và kiểu dữ liệu/codec có thể ghi. Chỉ thêm `produces = application/xml` khi có hỗ trợ chuyển đổi XML thật.
4. Nếu **400**, xem lỗi giải mã/validation và cấu trúc JSON, không vội đổi `Accept`.
5. Khi cần nhiều biểu diễn cho một URL và có cache trung gian, cân nhắc response header `Vary: Accept` để cache phân biệt các biến thể. `Vary` không phải header tự động giải quyết negotiation; nó mô tả header request đã ảnh hưởng đến việc chọn response.

## 10. Ghi nhớ khi thiết kế API

- Với API chỉ hỗ trợ JSON, hãy xác định rõ hợp đồng: request có body JSON dùng `Content-Type: application/json`, client muốn JSON gửi `Accept: application/json`, server trả response với `Content-Type` tương ứng.
- Dùng `consumes` để ràng buộc định dạng **đầu vào**, `produces` để công bố định dạng **đầu ra**; không đảo chiều.
- Đừng nghĩ chỉ cần ghi `Content-Type` là có thể bỏ qua cấu trúc body, hoặc chỉ cần khai báo `produces` là Spring có ngay converter.
- Tránh lệ thuộc vào phần mở rộng URL, thứ tự vô tình của các handler, hay giá trị `Accept` mặc định của trình duyệt.
- Khi tài nguyên có nhiều biểu diễn, thử nghiệm ít nhất ba trường hợp: media type khớp cụ thể, media type không khớp, và `Accept` rộng/không có.

**Tự kiểm tra:**

1. Request POST có `Content-Type: application/json`, `Accept: text/plain`. Header nào dùng để đọc body, header nào dùng để chọn response?
2. Vì sao `Accept: application/json` không ngăn được lỗi 415 khi body gửi bằng `text/plain`?
3. Vì sao `Content-Type: application/json` vẫn có thể dẫn đến 400?
4. Endpoint chỉ `produces = application/json` sẽ phản ứng ra sao khi client gửi `Accept: application/xml`?
5. Khi phục vụ cùng URI dưới dạng JSON và văn bản, cần quan tâm điều gì với `Accept: */*` và cache?

**Đáp án định hướng:** (1) `Content-Type` cho đầu vào, `Accept` cho đầu ra; (2) `Accept` không thay đổi request body; (3) cú pháp/nội dung JSON có thể sai; (4) thường 406; (5) lựa chọn biến thể cần rõ ràng, kiểm thử trường hợp rộng và cân nhắc `Vary: Accept`.

## 11. Tài liệu tham khảo

- HTTP Semantics (RFC 9110): https://www.rfc-editor.org/rfc/rfc9110
- Spring Framework — Mapping Requests (`consumes`/`produces`): https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html
- Spring Framework — Content Types/Content Negotiation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/content-negotiation.html
- MDN — HTTP Content Negotiation: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Content_negotiation
