# Thương lượng application/json, application/problem+json và định dạng luồng trong Spring Boot

## 1. Mục tiêu bài học

Spring Boot Web Runtime có thể trả một object JSON, một **ProblemDetail** báo lỗi hoặc một luồng dữ liệu được chuyển dần qua HTTP. Cùng dùng Jackson nhưng ba kiểu phản hồi này **không có cùng Content-Type, cách encode hay cách client parse**. Cần phân biệt rõ **application/json**, **application/problem+json** và các streaming media type như **application/x-ndjson** hoặc **text/event-stream**.

Bài thuộc nhóm **JSON và codec**. Sau khi học, bạn có thể:

1. Giải thích sự khác biệt giữa **Content-Type** và **Accept**, giữa **consumes** và **produces** của Spring.
2. Hiểu vì sao request có thể trả **406 Not Acceptable**, **415 Unsupported Media Type**, **400 Bad Request** hoặc **404 Not Found**.
3. Dùng **ProblemDetail** theo **RFC 9457** và chọn **application/problem+json** cho response lỗi HTTP có cấu trúc.
4. Biết vì sao **Flux<T> + application/json** không nhất thiết streaming, còn **application/x-ndjson** dùng một JSON document mỗi dòng.
5. Sử dụng **text/event-stream** và **ServerSentEvent<T>** để gửi các sự kiện SSE.
6. Xây ví dụ **Spring Boot 3.5, Java 17, WebFlux/Reactor Netty** chạy được với đủ JSON, ProblemDetail, NDJSON và SSE.
7. Kiểm thử body, media type, status, streaming, xử lý lỗi sau response commit và ảnh hưởng proxy/cache.

Phần runnable dùng **Spring Boot 3.5.x + Spring Framework 6.2**, còn các giải thích về **Spring MVC** được so sánh khi cần. Ở Boot 4/Framework 7, hãy kiểm tra tài liệu đúng nhánh trước khi sao chép cấu hình.

## 2. Ba câu hỏi khác nhau trong một HTTP exchange

Ví dụ client gửi:

~~~http
POST /api/items HTTP/1.1
Content-Type: application/json
Accept: application/json, application/problem+json

{"name":"Sách"}
~~~

Ý nghĩa:

- **Request Content-Type** nói **body gửi đi** đang là gì. Ở ví dụ là application/json.
- **Request Accept** nói **những kiểu response** client có thể xử lý; có thể cho phép cả thành công và lỗi.
- **Response Content-Type** nói server **đã trả thực tế** media type gì.

Response thành công:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":1,"name":"Sách"}
~~~

Response lỗi:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Item not found",
  "status": 404,
  "detail": "Item 99 does not exist",
  "instance": "/api/items/99",
  "code": "ITEM_NOT_FOUND"
}
~~~

**Sai lầm thường gặp:** gửi Content-Type: application/json trên request GET không có body để “yêu cầu server trả JSON”. Header thể hiện yêu cầu về **response** là **Accept**.

| Thành phần | Chủ thể | Mục đích |
|---|---|---|
| Request **Content-Type** | Client | Kiểu request body |
| Request **Accept** | Client | Các representation response được chấp nhận |
| Controller **consumes** | Server | Giới hạn kiểu request body được handler nhận |
| Controller **produces** | Server | Giới hạn kiểu response handler có thể tạo |
| Response **Content-Type** | Server | Kiểu body thực tế được trả |
| HTTP status | Server | Trạng thái xử lý, độc lập với cú pháp body |
| **Vary: Accept** | Server/cache | Hữu ích khi cùng URL trả representation khác theo Accept |

### 2.1. Accept có thể có nhiều giá trị

Ví dụ:

~~~http
Accept: application/json;q=0.9, application/problem+json;q=1.0
~~~

Giá trị **q** cho biết mức ưu tiên từ 0 đến 1. Nó không có nghĩa server phải trả ProblemDetail cho request thành công. Khi chọn representation, Spring xét mapping, media type, chất lượng và converter/codec đang có.

- **Accept: */*** chấp nhận mọi kiểu server có thể tạo.
- **Accept: application/json** yêu cầu JSON thông thường.
- **Accept: application/problem+json** yêu cầu Problem Details; không có nghĩa endpoint dữ liệu thông thường cũng tự chuyển sang format lỗi.
- **Accept: application/x-ndjson** dành cho JSON records theo dòng.
- **Accept: text/event-stream** dành cho SSE.
- **q=0** biểu thị media range không được chấp nhận; specificity và wildcard còn ảnh hưởng kết quả.

Nếu client gọi endpoint chỉ **produces=application/json** nhưng chỉ gửi **Accept: text/event-stream**, nó không thể yêu cầu Spring tự biến response thành SSE. Endpoint phải có implementation tương ứng.

### 2.2. consumes/produces trên annotation

~~~java
@PostMapping(
        path = "/api/items",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
~~~

- **consumes** dùng điều kiện Content-Type của request.
- **produces** dùng điều kiện Accept và khả năng ghi response.
- Không nên gắn một danh sách media type rộng vào một endpoint mà chưa chắc return type và encoder tạo được đúng từng format.

Trong **Spring MVC**, body được xử lý qua **HttpMessageConverter**. Trong **Spring WebFlux**, tương ứng là **HttpMessageReader/HttpMessageWriter** và encoder/decoder. Cả hai có logic content negotiation, nhưng khác cách quản lý dòng dữ liệu.

## 3. Quy trình chọn handler và codec

~~~mermaid
flowchart TD
    A[HTTP request] --> B[DispatcherHandler hoặc DispatcherServlet]
    B --> C[HandlerMapping kiểm tra path method consumes produces]
    C --> D{Có handler phù hợp?}
    D -->|Có| E[Decode @RequestBody bằng reader/converter]
    E --> F[Controller, service]
    F --> G{Thành công hay lỗi?}
    G -->|Thành công| H[Encoder / writer cho JSON, NDJSON, SSE]
    G -->|Lỗi| I[ExceptionHandler / ProblemDetail]
    D -->|Sai điều kiện| J[404, 405, 406, 415...]
    H --> K[Status + Content-Type + body]
    I --> K
    J --> K
~~~

Một số tình huống tiêu biểu:

| Tình huống | HTTP status điển hình | Nguyên nhân |
|---|---:|---|
| POST nhận JSON nhưng gửi text/plain | **415** | Không đáp ứng consumes hoặc reader |
| GET chỉ trả JSON nhưng client Accept text/plain | **406** | Không có response representation tương thích |
| Body JSON sai cú pháp | **400** | Decoder không đọc được |
| URL không có handler | **404** | Không tìm thấy route/resource |
| URL có GET mapping, client dùng POST | **405** | HTTP method không phù hợp |
| Business object không tồn tại | **404** nếu handler nghiệp vụ quy định | Exception/error mapping |
| Đã bắt đầu stream, sau đó lỗi | Có thể giữ status đã commit | Headers/body đã gửi |

**Lưu ý:** 406/415 là lỗi **thương lượng kiểu dữ liệu**, không phải lỗi “JSON serializer hỏng”. Ngoài Content-Type và Accept, còn cần xem path, method, security, interceptor/filter và proxy.

## 4. application/json: JSON document thông thường

Theo **RFC 8259**, JSON trao đổi trên các hệ thống mở phải dùng UTF-8. Media type chuẩn:

~~~http
Content-Type: application/json
~~~

Ví dụ một object:

~~~json
{"id":1,"name":"Sách"}
~~~

Ví dụ một array:

~~~json
[
  {"id":1,"name":"Sách"},
  {"id":2,"name":"Bút"}
]
~~~

Cả hai là **một JSON document hợp lệ**. JSON còn cho phép scalar ở top-level, nhưng API thường sử dụng object/array để có schema rõ ràng.

### 4.1. Không nhầm Flux với streaming từng object

Trong WebFlux, đoạn minh họa:

~~~java
@GetMapping(path = "/api/items",
            produces = MediaType.APPLICATION_JSON_VALUE)
public Flux<Item> all() {
    return repository.findAll();
}
~~~

không đồng nghĩa client được nhận từng item ngay lập tức. Theo hành vi mặc định của **Jackson2Encoder trong Spring Framework 6.2**, multi-value publisher ở **application/json** thường được **thu thành collection** rồi serialize thành một JSON array.

Đây là đoạn mã minh họa chưa chạy độc lập vì repository và Item chưa được định nghĩa. Khi dữ liệu lớn hoặc vô hạn, việc gom toàn bộ làm tăng bộ nhớ và độ trễ. Với collection hữu hạn, JSON array vẫn là hợp đồng hợp lý. Khi cần streaming thật, chọn media type streaming và cách decode tương ứng.

### 4.2. Charset và JSON

JSON trao đổi qua mạng hiện đại dùng **UTF-8**. Tham số **charset** không được định nghĩa riêng trong đăng ký media type application/json của RFC 8259; thông thường không cần thêm charset=UTF-8. Không gửi UTF-8 BOM.

Phân biệt **JSON escaping** với lỗi ký tự: body có thể biểu diễn chữ é trực tiếp hoặc bằng **\u00e9** và vẫn được parse thành cùng giá trị Unicode String. Không so sánh thô byte rồi coi hai representation khác nhau là sai dữ liệu.

## 5. application/problem+json: RFC 9457 Problem Details

**Problem Details for HTTP APIs** của **RFC 9457** là chuẩn mô tả lỗi HTTP; nó thay thế RFC 7807. Với JSON, media type là:

~~~http
Content-Type: application/problem+json
~~~

Ví dụ:

~~~json
{
  "type": "https://api.example.org/problems/not-found",
  "title": "Item not found",
  "status": 404,
  "detail": "Item 99 does not exist",
  "instance": "/api/items/99",
  "code": "ITEM_NOT_FOUND"
}
~~~

| Thuộc tính | Ý nghĩa |
|---|---|
| **type** | URI định danh loại lỗi. Nếu không đặt, có thể dùng about:blank |
| **title** | Tiêu đề ngắn cho loại lỗi |
| **status** | Mã HTTP tương ứng; không thay status line |
| **detail** | Thông tin cụ thể cho lần lỗi, an toàn để công khai |
| **instance** | URI/định danh của lần xảy ra lỗi |
| **code** | Extension property tự định nghĩa, không thuộc năm trường chuẩn |

Không bắt buộc mọi response phải có đủ năm trường chuẩn. **ProblemDetail** giúp chuẩn hóa hợp đồng để client nhận biết lỗi bằng HTTP status + machine-readable fields, thay vì kiểm tra chuỗi ngẫu nhiên trong body.

### 5.1. Tạo ProblemDetail trong Spring Framework 6.2

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;

ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.NOT_FOUND, "Item 99 does not exist");
problem.setTitle("Item not found");
problem.setProperty("code", "ITEM_NOT_FOUND");
~~~

Đây là đoạn minh họa trong method handler có các dependency Spring, chưa phải chương trình Java độc lập.

Khi một **@ExceptionHandler** hoặc controller trả **ProblemDetail**:

- HTTP status được xác định từ **status** của ProblemDetail.
- Các JSON codec/converter của Spring ưu tiên **application/problem+json** khi serialize ProblemDetail.
- Extension properties trong Map được serialize như JSON properties ngoài cùng khi dùng Jackson mixin của Spring.
- Trong **Spring Framework 6.2**, trường **instance** có thể được tự đặt theo request path khi chưa khai báo.

**Quan trọng:** chỉ đổi Content-Type thành application/problem+json trên một Map lỗi tùy ý không tự biến nó thành ProblemDetail đúng RFC.

### 5.2. Cấu hình cho Spring Boot 3.5

Với Spring WebFlux:

~~~yaml
spring:
  webflux:
    problemdetails:
      enabled: true
~~~

Property **spring.webflux.problemdetails.enabled** bật auto-configuration để nhiều exception built-in của WebFlux được xử lý bằng Problem Details. Với Spring MVC/Servlet, property tương ứng nhưng **khác stack** là:

~~~yaml
spring:
  mvc:
    problemdetails:
      enabled: true
~~~

Nếu tự dùng **@RestControllerAdvice** trả ProblemDetail cho lỗi nghiệp vụ, handler vẫn có thể hoạt động mà không phụ thuộc hoàn toàn vào property auto-configuration. Nên quản lý **@Order** khi có nhiều advice, và kiểm thử không tạo hai handler cạnh tranh.

### 5.3. Accept cho cả thành công và lỗi

Một cách gọi endpoint JSON thông thường:

~~~http
Accept: application/json, application/problem+json
~~~

Client chấp nhận **application/json** cho thành công và **application/problem+json** cho lỗi. Nếu chỉ gửi **Accept: application/problem+json** tới endpoint có **produces=application/json**, Spring có thể trả **406** ngay ở điều kiện mapping. Đừng dùng Accept chỉ cho lỗi rồi kỳ vọng thành công vẫn trả JSON.

Ngược lại, một custom exception handler có thể trả ProblemDetail với media type lỗi ưu tiên khi request đã vào handler, theo logic content negotiation của Spring. Cần kiểm tra HTTP status và Content-Type thực tế thay vì suy từ tên exception.

### 5.4. Bảo mật và ổn định hợp đồng

Không đưa stack trace, câu SQL, đường dẫn file nội bộ, credential, raw body nhạy cảm hoặc access token vào **detail**. Với lỗi 5xx, hãy gửi thông điệp an toàn và request/correlation ID để tra log.

Một API có thể chuẩn hóa **code=ITEM_NOT_FOUND** hoặc **code=INVALID_ITEM**; client dùng status + code để quyết định xử lý, không parse tiếng Việt hoặc tiếng Anh trong **detail**.

## 6. Định dạng luồng: tại sao cần media type khác?

Một HTTP response có thể sống đủ lâu để server gửi nhiều phần dữ liệu thay vì đợi có toàn bộ. Trong WebFlux, **Flux<T>** là abstraction thuận tiện cho nhiều item, nhưng **media type quyết định cách serialize trên wire**.

| Spring return type | Response media type | Wire format mặc định/thông dụng |
|---|---|---|
| **Mono<Item>** | application/json | Một JSON object |
| **Flux<Item>** | application/json | Một JSON array; codec thường buffer collection |
| **Flux<Item>** | application/x-ndjson | Mỗi item là JSON document trên một dòng, flush từng record |
| **Flux<ServerSentEvent<Item>>** | text/event-stream | SSE frames có data/event/id |
| **Flux<String>** | text/plain hoặc stream text | Các text chunks; không mặc định là JSON array |

Không sử dụng cùng một parser cho mọi dòng trên bảng này.

## 7. NDJSON: application/x-ndjson

**NDJSON – Newline Delimited JSON** là một chuỗi các JSON documents, mỗi document ở một dòng riêng.

~~~json
{"id":1,"name":"Sách"}
{"id":2,"name":"Bút"}
{"id":3,"name":"Vở"}
~~~

Các dòng trên **từng dòng** là JSON hợp lệ, nhưng **cả khối không phải một JSON document duy nhất**. Client không được gọi JSON.parse trên toàn bộ response và kỳ vọng nhận một array.

Media type:

~~~http
Content-Type: application/x-ndjson
~~~

Theo tài liệu Spring Framework 6.2, Jackson encoder có thể serialize và flush **mỗi phần tử Flux** theo kiểu line-delimited khi dùng media type streaming như application/x-ndjson.

### 7.1. Khi nào NDJSON phù hợp?

- Xuất danh sách bản ghi có thể rất lớn.
- Gửi log, event record, hoặc kết quả xử lý dần.
- Client xử lý từng JSON object ngay khi nhận.
- Hệ thống cần giữ schema từng record như JSON, nhưng không cần event metadata của SSE.

Điều cần kiểm soát:

- Một record quá lớn vẫn cần bộ nhớ để encode/decode.
- Một chunk TCP không tương đương một dòng; một dòng có thể bị chia nhiều chunk.
- Không dùng **collectList()** vô hạn khi client đọc stream.
- Proxy/nginx/CDN có thể buffer làm mất tính realtime.
- Không có cơ chế reconnect/replay mặc định được định nghĩa bởi NDJSON; cần tự thiết kế.

### 7.2. Không nhầm NDJSON với JSON-seq

**application/json-seq** theo **RFC 7464** phân tách JSON texts bằng byte **RS (0x1E)**, khác với ranh giới dòng của NDJSON.

Một số hệ thống cũ dùng tên **application/stream+json**. Khi xây API với Spring 6.2, nên chọn và tài liệu hóa một media type cụ thể; đừng tráo header mà không thay parser, encoder và tests.

## 8. SSE: text/event-stream

**Server-Sent Events** cho phép server gửi một chuỗi event qua một HTTP response, thường được trình duyệt tiêu thụ bằng **EventSource**.

~~~http
Content-Type: text/event-stream
~~~

Ví dụ **hai SSE frames**:

~~~text
id:1
event:item
data:{"id":1,"name":"Sách"}

id:2
event:item
data:{"id":2,"name":"Bút"}

~~~

- **id:** nhận dạng event, hữu ích cho reconnect nếu backend hỗ trợ replay.
- **event:** tên loại sự kiện, ví dụ item hoặc update.
- **data:** nội dung; có thể là JSON string/object đã được serialize, nhưng **toàn response vẫn là SSE**.
- **retry:** gợi ý khoảng thời gian reconnect cho client EventSource.
- Dòng trống kết thúc một event; **comment-only event** bắt đầu bằng dấu **:** có thể dùng làm heartbeat.

### 8.1. SSE khác NDJSON

| Yếu tố | NDJSON | SSE |
|---|---|---|
| Media type | application/x-ndjson | text/event-stream |
| Ranh giới phần tử | Newline | Blank line giữa các event |
| Định dạng dữ liệu | Mỗi dòng là JSON document | SSE frame, data có thể là JSON |
| Event metadata | Không mặc định | id/event/retry/comment |
| Browser client | Fetch streaming + parser | **EventSource** |
| Reconnect | Client tự cài đặt | EventSource hỗ trợ reconnect cơ bản |
| Hướng truyền điển hình | Server → client, đôi khi request streaming | Server → client |
| Độ trễ thấp | Flush từng record | Flush từng event |

**EventSource** không cung cấp giao tiếp hai chiều như WebSocket. Đối với server-to-client status updates hoặc notifications, SSE có thể đơn giản hơn WebSocket.

### 8.2. Các giới hạn quan trọng

- SSE dùng **UTF-8** và framing dạng text; parser phải phân đoạn theo dòng, không theo raw TCP chunks.
- Sự kiện có thể tới client chậm do proxy buffering hoặc compression.
- Stream sống lâu cần **heartbeat**, timeout, cancellation và quản lý nguồn dữ liệu.
- Khi EventSource reconnect với **Last-Event-ID**, server phải tự hiện thực replay nếu muốn không bỏ sót event.
- Không dùng SSE như một JSON document; **JSON.parse(responseBody)** trên toàn bộ SSE response sẽ thất bại.

## 9. Xử lý lỗi khi một stream đã commit

Trước khi response bắt đầu truyền, server còn có thể trả:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json
~~~

Nhưng một khi NDJSON record hoặc SSE frame đầu tiên đã được flush, **status và headers có thể đã commit**. Nếu upstream error xảy ra sau đó, ứng dụng thường **không thể đổi HTTP 200 thành 500** hoặc thay toàn bộ body bằng một ProblemDetail response.

Các phương án xử lý:

1. **Kiểm tra authorization và điều kiện ban đầu** trước khi phát record đầu tiên; lỗi sớm trả ProblemDetail.
2. Nếu lỗi xảy ra giữa stream, **log/metric và đóng luồng**, hoặc phát **một sự kiện lỗi theo giao thức stream** khi contract có quy định.
3. Với SSE, có thể phát **event:error** cùng data JSON được client hiểu; đây **không phải** thay HTTP status.
4. Với NDJSON, record lỗi cần schema riêng để không bị hiểu như dữ liệu thường; không tự nối ProblemDetail JSON bất kỳ rồi đổi Content-Type giữa chừng.
5. Client cần xử lý stream bị ngắt, retry, duplicate event và checkpoint.

**Không hứa** mọi lỗi Reactor Flux được chuyển thành HTTP 5xx sau khi response đã có byte được gửi.

## 10. Demo Spring Boot 3.5 / Java 17 chạy được

Demo thuần **WebFlux với Reactor Netty** có các route:

- GET **/api/items/1** → 200 application/json.
- GET **/api/items/99** → 404 application/problem+json.
- GET **/api/items** → JSON array.
- POST **/api/items** → nhận/gửi JSON.
- GET **/api/stream/ndjson** → NDJSON gồm ba record.
- GET **/api/stream/sse** → SSE gồm ba event.

### 10.1. Cấu trúc thư mục

~~~text
media-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/media/
    │   │   ├── MediaApplication.java
    │   │   ├── ItemController.java
    │   │   ├── ItemNotFoundException.java
    │   │   └── ApiProblemHandler.java
    │   └── resources/application.yml
    └── test/java/com/example/media/
        └── MediaNegotiationTest.java
~~~

### 10.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>media-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
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

Không thêm **spring-boot-starter-web** vào project này; khi có cả MVC và WebFlux, Spring Boot thường ưu tiên Servlet/MVC.

### 10.3. MediaApplication.java

~~~java
package com.example.media;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MediaApplication {
    public static void main(String[] args) {
        SpringApplication.run(MediaApplication.class, args);
    }
}
~~~

### 10.4. ItemNotFoundException.java

~~~java
package com.example.media;

public class ItemNotFoundException extends RuntimeException {
    private final long id;

    public ItemNotFoundException(long id) {
        super("Item " + id + " does not exist");
        this.id = id;
    }

    public long getId() {
        return id;
    }
}
~~~

### 10.5. ItemController.java

~~~java
package com.example.media;

import java.time.Duration;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class ItemController {

    @GetMapping(
            path = "/items/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Item> find(@PathVariable long id) {
        if (id == 1L) {
            return Mono.just(new Item(1, "Sách"));
        }
        return Mono.error(new ItemNotFoundException(id));
    }

    @GetMapping(
            path = "/items",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Flux<Item> list() {
        return Flux.just(
                new Item(1, "Sách"),
                new Item(2, "Bút"));
    }

    @PostMapping(
            path = "/items",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Item> create(@RequestBody Mono<NewItem> request) {
        return request.flatMap(input -> {
            if (input.name() == null || input.name().isBlank()) {
                return Mono.error(
                        new IllegalArgumentException("name is required"));
            }
            return Mono.just(new Item(3, input.name().trim()));
        });
    }

    @GetMapping(
            path = "/stream/ndjson",
            produces = "application/x-ndjson")
    public Flux<Item> ndjson() {
        return Flux.just(
                new Item(1, "Sách"),
                new Item(2, "Bút"),
                new Item(3, "Vở"))
                .delayElements(Duration.ofMillis(150));
    }

    @GetMapping(
            path = "/stream/sse",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<Item>> sse() {
        return Flux.just(
                new Item(1, "Sách"),
                new Item(2, "Bút"),
                new Item(3, "Vở"))
                .delayElements(Duration.ofMillis(200))
                .index()
                .map(tuple -> ServerSentEvent.<Item>builder()
                        .id(Long.toString(tuple.getT1() + 1))
                        .event("item")
                        .data(tuple.getT2())
                        .build());
    }

    public record Item(long id, String name) {}
    public record NewItem(String name) {}
}
~~~

**Giải thích code:**

- **find** trả Mono một item hoặc Mono.error để exception handler tạo ProblemDetail.
- **list** dùng Flux, nhưng **produces=application/json** nên Jackson có thể tạo JSON array sau khi thu các phần tử.
- **create** yêu cầu request JSON, kiểm tra name và trả một JSON object; demo chưa lưu database.
- **ndjson** tạo ba JSON records được xuất theo dòng và delay 150ms giữa các phần tử.
- **sse** tạo ba ServerSentEvent, có **id**, tên event **item**, **data** là DTO JSON. Dòng delay minh họa flush từng event.

### 10.6. ApiProblemHandler.java

~~~java
package com.example.media;

import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
@Order(Ordered.HIGHEST_PRECEDENCE)
public class ApiProblemHandler {

    @ExceptionHandler(ItemNotFoundException.class)
    public ProblemDetail notFound(ItemNotFoundException ex) {
        ProblemDetail detail = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND, ex.getMessage());
        detail.setTitle("Item not found");
        detail.setProperty("code", "ITEM_NOT_FOUND");
        return detail;
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ProblemDetail invalid(IllegalArgumentException ex) {
        ProblemDetail detail = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST, ex.getMessage());
        detail.setTitle("Invalid item");
        detail.setProperty("code", "INVALID_ITEM");
        return detail;
    }
}
~~~

**@Order** giúp handler nghiệp vụ cụ thể có mức ưu tiên rõ ràng nếu cùng ứng dụng còn có advice được Boot cấu hình. Không sử dụng **@ExceptionHandler(Exception.class)** bắt mọi exception rồi trả 500 vì nó có thể che lỗi 400/404/405/406/415 của framework.

### 10.7. application.yml

~~~yaml
server:
  port: 8080

spring:
  webflux:
    problemdetails:
      enabled: true
~~~

Ở Boot 3.5, property **spring.webflux.problemdetails.enabled** giúp chuẩn hóa một số phản hồi lỗi built-in của WebFlux. Hai handler custom trên vẫn chịu trách nhiệm cho lỗi nghiệp vụ riêng.

### 10.8. Khởi chạy

Trong thư mục có pom.xml, với JDK 17+ và Maven:

~~~bash
mvn spring-boot:run
~~~

Hoặc:

~~~bash
mvn clean package
java -jar target/media-demo-1.0.0.jar
~~~

## 11. Kiểm thử HTTP bằng curl

### 11.1. JSON thành công

~~~bash
curl -i \
  -H "Accept: application/json, application/problem+json" \
  "http://localhost:8080/api/items/1"
~~~

Mong đợi HTTP **200**, Content-Type tương thích **application/json** và body:

~~~json
{"id":1,"name":"Sách"}
~~~

### 11.2. ProblemDetail

~~~bash
curl -i \
  -H "Accept: application/json, application/problem+json" \
  "http://localhost:8080/api/items/99"
~~~

Mong đợi HTTP **404**, Content-Type tương thích **application/problem+json**. Body có các trường:

~~~json
{
  "type": "about:blank",
  "title": "Item not found",
  "status": 404,
  "detail": "Item 99 does not exist",
  "instance": "/api/items/99",
  "code": "ITEM_NOT_FOUND"
}
~~~

Spring Framework 6.2 có thể tự gán instance. Thứ tự JSON keys không có ý nghĩa.

### 11.3. JSON array

~~~bash
curl -i \
  -H "Accept: application/json" \
  "http://localhost:8080/api/items"
~~~

Mong đợi một JSON array:

~~~json
[
  {"id":1,"name":"Sách"},
  {"id":2,"name":"Bút"}
]
~~~

JSON serializer có thể in trên một dòng nếu không bật pretty-print.

### 11.4. POST JSON thành công

~~~bash
curl -i \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, application/problem+json" \
  --data-binary '{"name":"Hà Nội"}' \
  "http://localhost:8080/api/items"
~~~

Mong đợi HTTP **200** (demo không lưu database và không đặt 201):

~~~json
{"id":3,"name":"Hà Nội"}
~~~

### 11.5. Sai Content-Type → 415

~~~bash
curl -i \
  -H "Content-Type: text/plain" \
  --data-binary "Hello" \
  "http://localhost:8080/api/items"
~~~

Mong đợi HTTP **415 Unsupported Media Type** vì endpoint consumes application/json.

### 11.6. Sai Accept → 406

~~~bash
curl -i \
  -H "Accept: text/plain" \
  "http://localhost:8080/api/items/1"
~~~

Mong đợi HTTP **406 Not Acceptable**, vì endpoint chỉ produces application/json.

### 11.7. Invalid body → 400

~~~bash
curl -i \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, application/problem+json" \
  --data-binary '{"name":"  "}' \
  "http://localhost:8080/api/items"
~~~

Mong đợi HTTP **400** với ProblemDetail **code=INVALID_ITEM**.

### 11.8. NDJSON từng record

~~~bash
curl -i -N \
  -H "Accept: application/x-ndjson" \
  "http://localhost:8080/api/stream/ndjson"
~~~

**-N** tắt buffering của curl. Mong đợi ba JSON lines:

~~~json
{"id":1,"name":"Sách"}
{"id":2,"name":"Bút"}
{"id":3,"name":"Vở"}
~~~

**Không** parse cả khối như một JSON array.

### 11.9. SSE từng event

~~~bash
curl -i -N \
  -H "Accept: text/event-stream" \
  "http://localhost:8080/api/stream/sse"
~~~

Mong đợi dạng:

~~~text
id:1
event:item
data:{"id":1,"name":"Sách"}

id:2
event:item
data:{"id":2,"name":"Bút"}

id:3
event:item
data:{"id":3,"name":"Vở"}

~~~

Đây là các SSE frames; **event.data** mới chứa JSON. Các lệnh multiline dùng Bash; với Windows có thể dùng **curl.exe** một dòng và chú ý escaping.

## 12. Test tích hợp với WebTestClient

Test qua HTTP thật với **Reactor Netty** giúp kiểm tra status và Content-Type; các stream trong demo hữu hạn nên test có thể đọc hết body. Đây không phải cách khuyến nghị để tiêu thụ stream vô hạn trong production.

**src/test/java/com/example/media/MediaNegotiationTest.java**

~~~java
package com.example.media;

import java.nio.charset.StandardCharsets;
import java.time.Duration;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class MediaNegotiationTest {

    @LocalServerPort
    int port;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToServer()
                .baseUrl("http://localhost:" + port)
                .responseTimeout(Duration.ofSeconds(8))
                .build();
    }

    @Test
    void successUsesApplicationJson() {
        client.get().uri("/api/items/1")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.name").isEqualTo("Sách");
    }

    @Test
    void missingItemUsesProblemJson() {
        client.get().uri("/api/items/99")
                .accept(MediaType.APPLICATION_JSON,
                        MediaType.parseMediaType("application/problem+json"))
                .exchange()
                .expectStatus().isNotFound()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.parseMediaType("application/problem+json"))
                .expectBody()
                .jsonPath("$.status").isEqualTo(404)
                .jsonPath("$.code").isEqualTo("ITEM_NOT_FOUND");
    }

    @Test
    void unsupportedAcceptGives406() {
        client.get().uri("/api/items/1")
                .accept(MediaType.TEXT_PLAIN)
                .exchange()
                .expectStatus().isEqualTo(406);
    }

    @Test
    void unsupportedRequestContentTypeGives415() {
        client.post().uri("/api/items")
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("Hello")
                .exchange()
                .expectStatus().isEqualTo(415);
    }

    @Test
    void ndjsonHasThreeRecords() {
        client.get().uri("/api/stream/ndjson")
                .accept(MediaType.parseMediaType("application/x-ndjson"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.parseMediaType("application/x-ndjson"))
                .expectBody()
                .consumeWith(result -> {
                    byte[] bytes = result.getResponseBody();
                    assertThat(bytes).isNotNull();
                    String body = new String(bytes, StandardCharsets.UTF_8);
                    assertThat(body.lines()
                            .filter(line -> !line.isBlank()).count())
                            .isEqualTo(3L);
                });
    }

    @Test
    void sseContainsEventFrames() {
        client.get().uri("/api/stream/sse")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.TEXT_EVENT_STREAM)
                .expectBody()
                .consumeWith(result -> {
                    byte[] bytes = result.getResponseBody();
                    assertThat(bytes).isNotNull();
                    String body = new String(bytes, StandardCharsets.UTF_8);
                    assertThat(body).contains("event:");
                    assertThat(body).contains("data:");
                    assertThat(body).contains("Sách");
                });
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Khi test thành công, Maven kết thúc exit code 0. Test trên xác minh **media type và body sau khi đã nhận đủ dữ liệu**, không chứng minh thời gian flush từng record hoặc behavior khi proxy gây buffering. Để kiểm thử latency/heartbeat, cần subscriber quan sát thời gian từng event và chạy qua hạ tầng production-like.

## 13. Client parse từng format thế nào?

**application/json:** đọc một JSON document; parse thành DTO/array. Kiểm tra HTTP status trước khi parse theo schema thành công.

**application/problem+json:** parse ProblemDetail, dùng status và extension **code** để quyết định hiển thị hoặc retry. Không phụ thuộc hoàn toàn vào chuỗi **detail**.

**application/x-ndjson:** đọc stream byte UTF-8 theo **ranh giới dòng**, parse mỗi dòng hoàn chỉnh. Một chunk mạng có thể chứa nửa dòng, nhiều dòng hoặc một phần UTF-8 character; không đồng nhất chunk với record.

Ví dụ WebClient (đoạn minh họa trong class ứng dụng):

~~~java
Flux<Item> records = webClient.get()
        .uri("/api/stream/ndjson")
        .accept(MediaType.parseMediaType("application/x-ndjson"))
        .retrieve()
        .bodyToFlux(Item.class);
~~~

Phải subscribe hoặc xử lý Publisher qua pipeline. Với stream vô hạn, không dùng **collectList()** không có giới hạn.

**text/event-stream:** sử dụng SSE parser hoặc trình duyệt **EventSource**, rồi parse từng **event.data** nếu nội dung là JSON.

~~~javascript
const source = new EventSource("/api/stream/sse");

source.addEventListener("item", event => {
  const item = JSON.parse(event.data);
  console.log(item.id, item.name);
});

source.onerror = () => {
  console.log("SSE connection interrupted");
};
~~~

JavaScript này chạy phía trình duyệt; nếu dùng bearer token Authorization, EventSource gốc không cho tự đặt tùy ý HTTP headers như fetch. Cần thiết kế xác thực, CORS và cookie/session phù hợp.

## 14. Những lưu ý vận hành production

### 14.1. Streaming và proxy

- Reverse proxy, ingress hoặc CDN có thể **buffer response**, làm NDJSON/SSE đến client muộn dù Spring flush từng phần.
- **Compression** cũng có thể tăng buffering; cần đo với server/proxy thực tế.
- Với stream lâu dài, dùng **heartbeat**, timeout, cancellation và giới hạn kết nối.
- Đừng ép **Content-Length** khi không biết độ dài stream. Với HTTP/1.1, có thể xuất hiện chunked transfer; HTTP/2 có cơ chế framing khác.
- Khi caching nhiều representation cùng URL, xem xét **Vary: Accept** và bảo đảm không cache nhầm response cá nhân.
- Không coi **Content-Type** là cơ chế phân quyền: vẫn phải kiểm tra authentication/authorization.

### 14.2. Buffer limit và backpressure

Trong Spring WebFlux, codec có giới hạn aggregation như **maxInMemorySize**. Với Boot 3.5 có thể cấu hình:

~~~yaml
spring:
  http:
    codecs:
      max-in-memory-size: 256KB
~~~

Giới hạn này không phải giới hạn tổng số byte của NDJSON stream. Stream nhiều record nhỏ có thể dài hơn ngưỡng; một record lớn vẫn có thể vượt giới hạn. Ngoài ra, nếu code gọi **collectList()**, cache hoặc join không giới hạn, việc dùng Flux không ngăn tích lũy bộ nhớ.

### 14.3. Client reconnect

- SSE EventSource có thể reconnect; nếu cần không mất sự kiện, backend phải hiểu **Last-Event-ID** và cung cấp replay/offset phù hợp.
- NDJSON không mặc định có reconnect; cần thiết kế cursor/checkpoint, idempotency và xử lý duplicate records.
- Không tự động retry POST không idempotent chỉ vì kết nối stream bị ngắt.

### 14.4. Lỗi giữa stream

Khi response đã commit, không thể trông chờ một **ProblemDetail JSON response** mới thay thế status/body hiện tại. Hãy định nghĩa event lỗi trong giao thức stream nếu cần, hoặc đóng stream và dùng metric/log để chẩn đoán.

## 15. Bảng lỗi hay gặp

| Hiện tượng | Nguyên nhân | Cách giải quyết |
|---|---|---|
| POST trả 415 | Request Content-Type không khớp consumes | Gửi đúng Content-Type/application/json |
| GET trả 406 | Accept không khớp produces | Chọn media type endpoint hỗ trợ |
| Error JSON được trả 200 | Handler không đặt HTTP status | Dùng ProblemDetail/ResponseEntity đúng status |
| Client cố parse lỗi bằng success DTO | Không phân biệt problem+json | Kiểm tra status/Content-Type |
| Body 404 không có ProblemDetail | Chưa bật auto config hoặc handler khác | Kiểm tra property WebFlux/MVC và advice |
| Flux trả JSON array thay vì stream | produces=application/json | Dùng NDJSON hoặc SSE nếu cần streaming |
| JSON.parse lỗi với NDJSON | Nhiều root JSON documents | Parse từng dòng |
| JSON.parse lỗi với SSE | Đang nhận event frames | Dùng EventSource/SSE parser |
| SSE chậm qua ingress | Proxy buffering/compression | Kiểm tra flush và cấu hình proxy |
| Error trong stream không đổi status 200 | Response đã commit | Thiết kế in-band error hoặc close |
| NDJSON nhiều record gây OOM | Code thu Flux vào List | Streaming, backpressure, giới hạn record |
| application/json-seq đọc sai | RS framing khác newline | Parser đúng RFC 7464 |
| EventSource reconnect liên tục | Timeout/auth/stream kết thúc | Heartbeat, auth, reconnect policy |
| Cache trả nhầm media type | Cache key bỏ qua Accept | Vary: Accept và cache policy |

## 16. Checklist QA

- [ ] Mỗi endpoint có hợp đồng consumes/produces đúng.
- [ ] Success application/json dùng JSON document hợp lệ.
- [ ] Lỗi nghiệp vụ dùng status HTTP phù hợp và application/problem+json.
- [ ] ProblemDetail không lộ stack trace, SQL, token hoặc thông tin riêng tư.
- [ ] Boot WebFlux dùng **spring.webflux.problemdetails.enabled** nếu bật auto-handler.
- [ ] Các test có tình huống 406/415, JSON sai cú pháp và không tìm thấy resource.
- [ ] NDJSON là một JSON document mỗi dòng, không phải JSON array.
- [ ] SSE có event framing và Content-Type text/event-stream.
- [ ] Test bằng curl -N và client parser phù hợp.
- [ ] Cảnh báo proxy buffering, compression, timeout và cancellation.
- [ ] Không tự động gom Flux vô hạn vào memory.
- [ ] Đã thiết kế cách báo lỗi sau response commit.
- [ ] Nếu nhiều representations cùng URL, cache phân biệt theo Accept.
- [ ] Có chiến lược authentication/authorization, reconnect và replay.

## 17. Tài liệu tham khảo chính thức

1. Spring Framework 6.2 – Mapping Requests, consumes/produces: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-requestmapping.html
2. Spring Framework 6.2 – Reactive Core, Jackson encoding và streaming: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html
3. Spring Framework 6.2 – WebFlux Error Responses: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/ann-rest-exceptions.html
4. Spring Framework 6.2 – MVC Error Responses: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html
5. Spring Boot 3.5 – Reactive Web Applications: https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html
6. Spring Boot 3.5 – Common Application Properties: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/
7. RFC 9457 – Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457
8. RFC 8259 – JSON: https://www.rfc-editor.org/rfc/rfc8259
9. RFC 9110 – HTTP Semantics: https://www.rfc-editor.org/rfc/rfc9110
10. RFC 7464 – JSON Text Sequences: https://www.rfc-editor.org/rfc/rfc7464
11. WHATWG HTML – Server-Sent Events: https://html.spec.whatwg.org/multipage/server-sent-events.html

## 18. Kết luận

Trong Spring Boot, **Accept**, **Content-Type**, **consumes** và **produces** quyết định kiểu dữ liệu được chấp nhận và cách chọn handler/codec. **application/json** dành cho một JSON document, **application/problem+json** dành cho ProblemDetail theo RFC 9457, còn **application/x-ndjson** và **text/event-stream** dành cho hai dạng stream với framing và client parser khác nhau.

**Flux<T> không tự bảo đảm response streaming** nếu dùng application/json, vì Jackson mặc định có thể gom các phần tử thành một JSON array. Khi chọn streaming format, phải tính tới flush, proxy, bộ nhớ, backpressure, reconnect và xử lý lỗi sau khi HTTP response đã commit.
