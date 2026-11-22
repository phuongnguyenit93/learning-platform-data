# Phân biệt Flux với phản hồi thực sự được gửi từng phần trong Spring WebFlux

## 1. Flux là publisher, streaming HTTP là hành vi truyền dữ liệu

Trong Reactor, \`Flux<T>\` là một publisher có thể phát **0 đến nhiều phần tử** theo thời gian, sau đó hoàn tất hoặc phát lỗi. Nó mô tả cách ứng dụng tạo và tiêu thụ dữ liệu theo Reactive Streams.

Một HTTP response streaming là hành vi ở tầng giao tiếp: server gửi response body thành nhiều phần khi dữ liệu sẵn sàng, để client có thể nhận và xử lý từng phần **trước khi toàn bộ response kết thúc**.

Hai khái niệm liên quan nhưng không đồng nghĩa:

- \`Flux\` cho biết handler có thể tạo nhiều giá trị bất đồng bộ.
- HTTP message writer/codec quyết định cách biến các giá trị thành bytes của response.
- Media type giúp writer chọn định dạng và chiến lược ghi phù hợp.
- Server transport, reverse proxy, gateway và HTTP client có thể tiếp tục buffer hoặc gom bytes.
- Chỉ khi dữ liệu thực sự đến client theo từng phần thì client mới quan sát được streaming end-to-end.

Vì vậy, method trả \`Flux<T>\` **chưa đủ để kết luận** browser hoặc client nhận từng phần ngay khi publisher phát \`onNext\`. Một \`Flux\` có thể bị gom thành collection, serialize thành một JSON document rồi mới gửi.

Điểm cốt lõi của bài là phân biệt ba thời điểm:

1. Publisher phát một phần tử.
2. Spring encode và ghi bytes vào response.
3. Client thật sự nhận được bytes và có thể xử lý phần dữ liệu đó.

Nếu ba thời điểm này bị tách xa nhau do buffering, ứng dụng vẫn có reactive pipeline nhưng người dùng không quan sát được phản hồi streaming.

## 2. Đường đi từ Flux đến HTTP response

Trong annotated controller, \`@ResponseBody\` (được bao hàm bởi \`@RestController\`) yêu cầu Spring serialize giá trị trả về thông qua \`HttpMessageWriter\`. WebFlux dùng codec tương ứng với kiểu Java và media type để ghi response.

Mô hình:

~~~text
Controller trả Flux<T>
        |
        v
Reactive Streams subscription
        |
        v
HttpMessageWriter / Encoder
        |
        +-- Chọn định dạng theo Content-Type
        +-- Có thể buffer hoặc encode từng phần tử
        +-- Có thể flush sau mỗi phần tử
        |
        v
ServerHttpResponse / server transport
        |
        v
Proxy / gateway / load balancer (nếu có)
        |
        v
HTTP client / browser
        |
        v
Ứng dụng client đọc bytes và xử lý record
~~~

Mỗi tầng có thể ảnh hưởng thời điểm dữ liệu xuất hiện. Spring có thể ghi và flush từng record, nhưng proxy vẫn có thể giữ dữ liệu một lúc trước khi chuyển tiếp. Client cũng có thể buffer trước khi hiển thị hoặc parse.

Do đó, cần xem cả **publisher, codec, media type, transport và client**, thay vì chỉ xem chữ ký method.

## 3. Khác biệt quan trọng của application/json

Với Jackson codec mặc định của Spring Framework 6.2, khi ghi một multi-value publisher như \`Flux<T>\` với media type \`application/json\`, \`Jackson2Encoder\` mặc định gọi \`collectToList()\` rồi serialize collection đó thành một JSON array.

Ví dụ:

~~~java
@GetMapping(value = "/numbers", produces = MediaType.APPLICATION_JSON_VALUE)
public Flux<NumberEvent> numbers() {
    return Flux.interval(Duration.ofSeconds(1))
        .take(5)
        .map(NumberEvent::new);
}
~~~

Publisher phát một giá trị mỗi giây, nhưng response JSON thông thường có dạng:

~~~json
[
  {"value":0},
  {"value":1},
  {"value":2},
  {"value":3},
  {"value":4}
]
~~~

Với codec mặc định, các giá trị được gom thành danh sách trước khi serialize thành JSON array. Client thường nhận body sau khi publisher hoàn tất và JSON document đã được tạo.

Điều này có một hệ quả quan trọng: nếu trả một \`Flux\` **không bao giờ hoàn tất** với \`application/json\`, encoder chờ collection hoàn chỉnh và không thể kết thúc JSON array. Đây không phải định dạng thích hợp cho một stream vô hạn.

JSON array là một document có cấu trúc. Dấu \`[\` mở đầu, các phần tử được phân tách bằng dấu phẩy, và dấu \`]\` chỉ xuất hiện khi danh sách kết thúc. Client dùng parser JSON thông thường thường cần nhận đủ document trước khi có thể xử lý toàn bộ array.

Có thể chọn parser streaming ở phía client để xử lý JSON array từng token, nhưng điều đó không thay đổi hành vi mặc định của Jackson encoder nói trên trong Spring WebFlux.

**Kết luận:** \`Flux<T>\` kết hợp với \`application/json\` có thể tạo response JSON array hữu hạn, nhưng không mặc nhiên là streaming từng phần tử.

## 4. application/x-ndjson: mỗi JSON object là một record

NDJSON (Newline Delimited JSON, còn gọi là JSON Lines) biểu diễn mỗi record bằng một JSON document độc lập trên một dòng:

~~~text
{"value":0}
{"value":1}
{"value":2}
{"value":3}
{"value":4}
~~~

Media type phổ biến là:

~~~http
Content-Type: application/x-ndjson
~~~

Với streaming media type như \`application/x-ndjson\`, Jackson encoder mặc định của WebFlux encode, ghi và **flush từng giá trị riêng lẻ** theo định dạng line-delimited JSON. Client có thể đọc từng dòng khi dữ liệu đến mà không cần đợi toàn bộ publisher hoàn tất.

Ví dụ:

~~~java
@GetMapping(
    value = "/numbers",
    produces = MediaType.APPLICATION_NDJSON_VALUE
)
public Flux<NumberEvent> numbers() {
    return Flux.interval(Duration.ofSeconds(1))
        .take(5)
        .map(NumberEvent::new);
}
~~~

Mỗi lần publisher phát \`NumberEvent\`, encoder chuyển nó thành một JSON object, ghi record và flush. Đây là lựa chọn phù hợp cho:

- Xuất dữ liệu lớn theo từng record.
- Event feed đơn giản cho service-to-service.
- Import/export theo dòng.
- Client cần parse từng JSON object độc lập.
- Pipeline không cần một JSON array hoàn chỉnh.

NDJSON không phải JSON array. Client cần đọc theo dòng và parse từng dòng thành một object. Không được parse toàn bộ body bằng một JSON parser mong đợi một document duy nhất.

Một record NDJSON phải được đóng khung rõ ràng bằng newline. Nếu dữ liệu JSON chứa chuỗi có ký tự newline, encoder JSON sẽ escape ký tự đó bên trong string; newline kết thúc record vẫn phân biệt được.

## 5. text/event-stream: Server-Sent Events

**Server-Sent Events (SSE)** là định dạng streaming một chiều từ server tới client. Browser có API \`EventSource\` để mở kết nối và nhận các event theo thời gian.

Media type:

~~~http
Content-Type: text/event-stream
~~~

Một event SSE có thể chứa các trường:

- \`data:\` nội dung event.
- \`id:\` mã định danh event, hữu ích cho reconnect.
- \`event:\` tên loại event.
- \`retry:\` thời gian client chờ trước khi reconnect.
- Dòng bắt đầu bằng \`:\` là comment, thường dùng làm heartbeat.

Mỗi event kết thúc bằng một dòng trống. Ví dụ hình dạng response:

~~~text
id:0
event:number
data:{"value":0}

id:1
event:number
data:{"value":1}

id:2
event:number
data:{"value":2}

~~~

Spring WebFlux hỗ trợ \`Flux<ServerSentEvent<T>>\`. Với SSE, encoder được gọi cho từng event và output được flush để dữ liệu được chuyển đi mà không phải chờ stream hoàn tất.

Ví dụ:

~~~java
@GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<NumberEvent>> events() {
    return Flux.interval(Duration.ofSeconds(1))
        .take(5)
        .map(index -> {
            NumberEvent data = new NumberEvent(index);
            return ServerSentEvent.<NumberEvent>builder(data)
                .id(Long.toString(index))
                .event("number")
                .build();
        });
}
~~~

Nếu chỉ cần gửi data mà không cần event id/name/retry/comment, có thể trả \`Flux<T>\` với \`produces = text/event-stream\`; wrapper \`ServerSentEvent<T>\` là tùy chọn.

### NDJSON hay SSE?

| Tiêu chí | NDJSON | SSE |
| --- | --- | --- |
| Media type | \`application/x-ndjson\` | \`text/event-stream\` |
| Record framing | Một JSON document trên mỗi dòng | Các trường event, kết thúc bằng dòng trống |
| Dữ liệu | JSON record độc lập | Event có thể có data, id, event, retry, comment |
| Client điển hình | Service, CLI, parser stream | Browser \`EventSource\`, client hỗ trợ SSE |
| Reconnect/event ID | Ứng dụng tự thiết kế | Có hỗ trợ id và \`Last-Event-ID\` theo giao thức SSE |
| Chiều giao tiếp | Server response stream | Server-to-client một chiều |
| Use case | Export/feed dữ liệu | Notification, live dashboard, trạng thái job |

SSE không thay thế WebSocket nếu ứng dụng cần trao đổi hai chiều liên tục. Với giao tiếp hai chiều, cân nhắc WebSocket hoặc giao thức phù hợp khác.

## 6. So sánh ba endpoint cùng trả Flux

Cùng một nguồn \`Flux<NumberEvent>\` có thể tạo ba kiểu HTTP response khác nhau tùy media type:

| Return type | Media type | Hành vi mặc định của encoder | Client quan sát |
| --- | --- | --- | --- |
| \`Flux<NumberEvent>\` | \`application/json\` | Gom thành List rồi serialize JSON array | Thường nhận array khi publisher hoàn tất |
| \`Flux<NumberEvent>\` | \`application/x-ndjson\` | Encode, ghi và flush từng JSON record | Có thể đọc từng dòng khi đến |
| \`Flux<ServerSentEvent<NumberEvent>>\` | \`text/event-stream\` | Encode và flush từng SSE event | Nhận event theo thời gian |

Đây là hành vi của codec mặc định được mô tả trong tài liệu Spring Framework 6.2. Nếu ứng dụng đăng ký custom encoder/writer hoặc thay đổi codec configuration, hành vi có thể khác; cần kiểm tra cấu hình thực tế.

Cũng cần phân biệt \`Flux<T>\` với \`Mono<List<T>>\`:

- \`Flux<T>\` phát từng phần tử theo Reactive Streams.
- \`Mono<List<T>>\` phát một collection sau khi đã gom dữ liệu.
- Khi dùng JSON array, encoder mặc định có thể gom multi-value Flux thành collection trước khi serialize, nên kết quả trên wire gần với một array hoàn chỉnh.

## 7. Flush, HTTP chunking và ranh giới record

Một số thuật ngữ dễ bị dùng lẫn:

**Ghi (write):** server chuyển bytes vào response output pipeline.

**Flush:** yêu cầu tầng output đẩy dữ liệu đang chờ xuống tầng tiếp theo. Với NDJSON/SSE, encoder mặc định flush sau mỗi record/event.

**HTTP framing:** cách HTTP xác định response body dài bao nhiêu và khi nào kết thúc.

**Record framing:** cách ứng dụng phân biệt record này với record tiếp theo, ví dụ newline của NDJSON hoặc dòng trống của SSE.

Trong HTTP/1.1, response có kích thước chưa biết trước có thể dùng \`Transfer-Encoding: chunked\` để đóng khung message body. Chunked transfer coding là cơ chế truyền và xác định độ dài các chunk bytes; nó **không định nghĩa ranh giới JSON record** và không bảo đảm mỗi \`onNext\` tương ứng đúng một HTTP chunk.

Trong HTTP/2, body được truyền bằng DATA frames; không dùng \`Transfer-Encoding: chunked\` như HTTP/1.1. DATA frame cũng là framing ở tầng HTTP transport, không phải ranh giới record của ứng dụng.

Vì vậy:

- Thấy header \`Transfer-Encoding: chunked\` không chứng minh mỗi Flux item được client nhận riêng.
- Không thấy header đó cũng không chứng minh response không streaming, nhất là khi dùng HTTP/2.
- TCP packet, HTTP chunk hoặc HTTP/2 DATA frame không phải ranh giới record mà client nên dựa vào.
- Client phải parse theo định dạng ứng dụng: newline cho NDJSON, event delimiter cho SSE.

## 8. Vì sao dữ liệu vẫn có thể bị buffer?

Ngay cả khi Spring encoder flush từng phần tử, các tầng khác có thể làm chậm việc hiển thị:

1. **Publisher hoặc operator:** \`collectList()\`, \`buffer()\`, \`window()\` kết hợp gom dữ liệu, hoặc một operator đợi completion trước khi phát.
2. **Codec:** media type hoặc custom writer chọn chiến lược aggregate.
3. **Server transport:** dữ liệu có thể được gom theo cách triển khai I/O và thời điểm ghi.
4. **Compression:** middleware nén có thể giữ dữ liệu để tạo block nén hiệu quả.
5. **Reverse proxy/gateway:** proxy buffering có thể gom response trước khi chuyển tiếp.
6. **Load balancer/service mesh:** tầng trung gian có thể áp dụng buffering hoặc timeout.
7. **Client library:** client có thể đọc body thành byte array/string trước khi parse.
8. **Browser UI:** JavaScript có thể chờ đủ dữ liệu hoặc chờ render batch.

Do đó, cần thử trên đường truyền thực tế của ứng dụng, bao gồm proxy và client production. Một unit test cho publisher chỉ chứng minh publisher phát phần tử theo thời gian; nó không chứng minh browser nhận từng phần ngay lập tức.

Nếu dùng reverse proxy, kiểm tra cấu hình buffering của proxy. Ví dụ với Nginx, response buffering có thể cần tắt cho endpoint streaming theo cấu hình triển khai. Không tắt buffering toàn hệ thống một cách máy móc; chỉ điều chỉnh route cần streaming và kiểm thử tải.

## 9. Backpressure: điều tiết demand, không phải bảo đảm flush

Reactive Streams backpressure cho phép subscriber điều khiển số lượng phần tử muốn nhận bằng \`request(n)\`. Reactor truyền demand ngược lên upstream qua các operator.

Ví dụ:

~~~java
Flux<Long> ticks = Flux.interval(Duration.ofMillis(100))
    .onBackpressureBuffer(100);
~~~

Đoạn này chỉ minh họa operator; nó tạo buffer tối đa 100 phần tử theo chính sách mặc định của overload này trước khi overflow được xử lý. Không nên thêm buffer lớn để che một consumer chậm.

Backpressure giúp pipeline reactive điều tiết việc phát/tiêu thụ dữ liệu, nhưng **không đồng nghĩa** mỗi \`onNext\` lập tức thành một lần gửi mạng hoặc client render ngay. Transport, proxy và client vẫn có buffer riêng.

Các nguyên tắc:

- Tránh \`collectList()\` hoặc \`collectMap()\` với stream không giới hạn.
- Không dùng \`onBackpressureBuffer()\` không giới hạn cho nguồn có thể phát nhanh hơn consumer.
- Giới hạn concurrency khi mỗi event gọi service/database.
- Chọn chính sách overflow phù hợp: buffer có giới hạn, drop, latest hoặc báo lỗi, tùy nghiệp vụ.
- Đo queue size, latency, dropped events và tốc độ consumer.
- Kiểm tra cancellation khi client đóng kết nối.

Một endpoint streaming cần thiết kế cả tốc độ nguồn lẫn khả năng tiêu thụ của client; chỉ trả \`Flux\` không tự giải quyết quá tải.

## 10. Cancellation và phát hiện client đã ngắt kết nối

Khi client đóng kết nối, server có thể phát hiện việc response không còn được tiêu thụ và hủy subscription upstream. Tuy nhiên, việc phát hiện có thể bị trì hoãn nếu server chưa thử ghi thêm dữ liệu hoặc kết nối trung gian vẫn còn mở.

Với stream dài hoặc gần như vô hạn, Spring khuyến nghị gửi dữ liệu định kỳ để phát hiện client disconnect sớm hơn. Với SSE có thể gửi comment-only event hoặc empty event làm heartbeat; NDJSON có thể có một record heartbeat theo schema ứng dụng nếu client hiểu record đó.

Ví dụ theo dõi vòng đời:

~~~java
Flux<NumberEvent> stream = source()
    .doFinally(signal -> {
        if (signal == SignalType.CANCEL) {
            metrics.incrementClientDisconnects();
        }
    });
~~~

Đây là đoạn minh họa cần \`source()\` và \`metrics\` của ứng dụng. \`doFinally\` quan sát \`ON_COMPLETE\`, \`ON_ERROR\` hoặc \`CANCEL\`; nó không thay thế cleanup resource có scope. Nếu nguồn giữ listener, socket hoặc handle, cần gắn cleanup đúng lifecycle.

Đừng giả định client disconnect luôn xuất hiện ngay khi tab đóng. Heartbeat định kỳ giúp server có cơ hội ghi dữ liệu và nhận biết connection đã hỏng.

## 11. Error xảy ra sau khi response đã bắt đầu

Trong streaming response, status và headers thường được commit trước hoặc khi những bytes đầu tiên được gửi. Nếu publisher phát một số event rồi mới phát \`onError\`, server không thể quay lại thay status 200 bằng 500 và ghi một JSON error document mới.

Ví dụ:

~~~java
Flux<NumberEvent> stream = Flux.concat(
    Flux.just(new NumberEvent(0), new NumberEvent(1)),
    Flux.error(new IllegalStateException("source failed"))
);
~~~

Khi hai record đầu đã được gửi, lỗi xảy ra sau đó chỉ có thể làm stream kết thúc bất thường hoặc được biểu diễn theo protocol ứng dụng. Không thể thay thế phần body đã gửi bằng response lỗi hoàn chỉnh.

Các lựa chọn thiết kế:

- Kiểm tra các lỗi có thể biết trước **trước khi commit response**.
- Dùng error event trong SSE nếu client protocol hiểu event đó.
- Với NDJSON, chỉ gửi một record lỗi cuối nếu schema API quy định rõ loại record đó; không trộn tùy tiện record lỗi vào stream dữ liệu.
- Ghi log/metric phía server, gắn request ID và phân biệt lỗi upstream với client cancellation.
- Nếu client cần biết toàn bộ batch thành công hay thất bại như một đơn vị, cân nhắc buffer/batch hữu hạn và trả một JSON document sau khi xử lý xong.

Streaming tối ưu độ trễ và khả năng xử lý từng phần, nhưng thay đổi cách API thể hiện lỗi. Client phải hiểu rằng stream có thể kết thúc trước khi nhận đủ record dự kiến.

## 12. Ví dụ hoàn chỉnh Java 17+ với Spring Boot WebFlux

Ví dụ tạo ba endpoint dùng cùng một nguồn phát năm phần tử, mỗi giây một phần tử:

- \`GET /api/numbers/json\`: trả JSON array; mặc định Jackson gom các phần tử rồi serialize khi Flux hoàn tất.
- \`GET /api/numbers/ndjson\`: trả từng JSON record và flush theo dòng.
- \`GET /api/numbers/events\`: trả SSE event, mỗi event có ID và tên event.

Cấu trúc dự án:

~~~text
flux-http-streaming/
├── pom.xml
└── src/
    ├── main/java/com/example/streaming/
    │   ├── StreamingApplication.java
    │   └── StreamController.java
    └── test/java/com/example/streaming/
        └── StreamControllerTest.java
~~~

File \`pom.xml\` (Spring Boot 3.5.0, Java 17+):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>flux-http-streaming</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
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

File \`src/main/java/com/example/streaming/StreamingApplication.java\`:

~~~java
package com.example.streaming;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StreamingApplication {

    public static void main(String[] args) {
        SpringApplication.run(StreamingApplication.class, args);
    }
}
~~~

File \`src/main/java/com/example/streaming/StreamController.java\`:

~~~java
package com.example.streaming;

import java.time.Duration;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/api")
public class StreamController {

    public record NumberEvent(long value) {}

    private Flux<NumberEvent> numbers() {
        return Flux.interval(Duration.ofSeconds(1))
            .take(5)
            .map(NumberEvent::new);
    }

    // Một Flux, nhưng application/json mặc định được gom thành array.
    @GetMapping(
        path = "/numbers/json",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Flux<NumberEvent> jsonArray() {
        return numbers();
    }

    // Mỗi NumberEvent được encode và flush thành một dòng NDJSON.
    @GetMapping(
        path = "/numbers/ndjson",
        produces = MediaType.APPLICATION_NDJSON_VALUE
    )
    public Flux<NumberEvent> ndjson() {
        return numbers();
    }

    // Mỗi NumberEvent được gửi thành một SSE event.
    @GetMapping(
        path = "/numbers/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    public Flux<ServerSentEvent<NumberEvent>> events() {
        return numbers().map(value ->
            ServerSentEvent.<NumberEvent>builder(value)
                .id(Long.toString(value.value()))
                .event("number")
                .build()
        );
    }
}
~~~

Chạy từ thư mục \`flux-http-streaming\` với JDK 17+ và Maven:

~~~bash
mvn spring-boot:run
~~~

### Thử JSON array

~~~bash
curl -i -H "Accept: application/json" \
  http://localhost:8080/api/numbers/json
~~~

Body JSON dự kiến:

~~~json
[
  {"value":0},
  {"value":1},
  {"value":2},
  {"value":3},
  {"value":4}
]
~~~

Nguồn phát trong năm giây, nhưng với Jackson encoder mặc định, JSON array được serialize sau khi publisher hoàn tất. Đây là ví dụ cho thấy chữ ký \`Flux\` không tự bảo đảm streaming từng record.

### Thử NDJSON

~~~bash
curl -N -i -H "Accept: application/x-ndjson" \
  http://localhost:8080/api/numbers/ndjson
~~~

Body dự kiến xuất hiện theo từng dòng, cách nhau khoảng một giây:

~~~text
{"value":0}
{"value":1}
{"value":2}
{"value":3}
{"value":4}
~~~

Tùy chọn \`-N\` của cURL tắt output buffering phía cURL để dễ quan sát dữ liệu đến từng phần.

### Thử SSE

~~~bash
curl -N -i -H "Accept: text/event-stream" \
  http://localhost:8080/api/numbers/events
~~~

Body có cấu trúc tương tự:

~~~text
id:0
event:number
data:{"value":0}

id:1
event:number
data:{"value":1}

id:2
event:number
data:{"value":2}

~~~

SSE event kết thúc bằng một dòng trống. Browser có thể dùng \`EventSource\` để nhận event và xử lý callback theo event type.

Trên Windows PowerShell, nếu \`curl\` bị ánh xạ thành alias của PowerShell, dùng \`curl.exe\`. Nếu chạy qua proxy, hãy kiểm tra proxy có buffering hay không trước khi kết luận encoder không flush.

## 13. Kiểm thử streaming bằng WebTestClient và StepVerifier

WebTestClient có thể trả về \`FluxExchangeResult\` cho response stream. Sau đó dùng \`StepVerifier\` để kiểm tra các phần tử đến theo thời gian.

File \`src/test/java/com/example/streaming/StreamControllerTest.java\`:

~~~java
package com.example.streaming;

import java.time.Duration;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class StreamControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void ndjsonValuesArriveAsSeparateSignals() {
        FluxExchangeResult<StreamController.NumberEvent> result =
            client.get()
                .uri("/api/numbers/ndjson")
                .accept(MediaType.APPLICATION_NDJSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_NDJSON)
                .returnResult(StreamController.NumberEvent.class);

        StepVerifier.create(result.getResponseBody())
            .expectNext(new StreamController.NumberEvent(0))
            .expectNoEvent(Duration.ofMillis(200))
            .expectNext(new StreamController.NumberEvent(1))
            .expectNext(new StreamController.NumberEvent(2))
            .expectNext(new StreamController.NumberEvent(3))
            .expectNext(new StreamController.NumberEvent(4))
            .verify(Duration.ofSeconds(8));
    }

    @Test
    void jsonEndpointReturnsACompleteArray() {
        client.get()
            .uri("/api/numbers/json")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectBodyList(StreamController.NumberEvent.class)
            .hasSize(5);
    }
}
~~~

Chạy test:

~~~bash
mvn test
~~~

Test NDJSON xác nhận các record được giải mã thành các tín hiệu riêng và có khoảng nghỉ giữa hai record đầu. Test JSON xác nhận endpoint trả collection gồm năm phần tử. Khi test trên máy tải cao, có thể nới khoảng thời gian và timeout để tránh phụ thuộc scheduler/CI quá chặt.

Test WebTestClient giúp xác minh status, headers và response body stream trong integration test. Để chứng minh hành vi qua production proxy/browser, vẫn cần thử end-to-end qua đúng đường truyền triển khai.

## 14. Đọc stream ở phía client

### WebClient nhận NDJSON

Một service reactive có thể tiêu thụ từng record bằng \`bodyToFlux\`:

~~~java
Flux<NumberEvent> events = webClient.get()
    .uri("/api/numbers/ndjson")
    .accept(MediaType.APPLICATION_NDJSON)
    .retrieve()
    .bodyToFlux(NumberEvent.class);
~~~

Client có thể compose:

~~~java
return events
    .doOnNext(this::processEvent)
    .then();
~~~

Không gọi \`collectList()\` nếu mục tiêu là xử lý từng record với bộ nhớ giới hạn. Nếu cần tổng hợp, hãy dùng batch có giới hạn hoặc aggregation phù hợp.

### Browser nhận SSE

Ví dụ JavaScript phía browser:

~~~javascript
const source = new EventSource("/api/numbers/events");

source.addEventListener("number", event => {
  const value = JSON.parse(event.data);
  console.log("received", value.value);
});

source.onerror = () => {
  console.log("SSE connection interrupted; browser may reconnect");
};
~~~

\`EventSource\` tự xử lý một số khía cạnh reconnect của SSE. Nếu server đặt \`id\`, browser có thể gửi \`Last-Event-ID\` khi reconnect; server cần thiết kế logic resume nếu muốn tiếp tục từ event trước đó.

NDJSON thường được đọc bằng Fetch Streams hoặc HTTP client có hỗ trợ incremental body reading; gọi API đọc toàn bộ body thành \`text()\` hoặc \`json()\` sẽ đợi đến khi response kết thúc và làm mất trải nghiệm xử lý từng record.

## 15. Chọn media type theo hợp đồng client

| Nhu cầu | Định dạng nên cân nhắc | Lý do |
| --- | --- | --- |
| Trả danh sách hữu hạn, client cần một document JSON | \`application/json\` | JSON array dễ dùng với parser và API thông thường |
| Gửi nhiều record độc lập khi có dữ liệu | \`application/x-ndjson\` | Mỗi dòng là một JSON object, parse từng record |
| Dashboard/browser nhận thông báo một chiều | \`text/event-stream\` | SSE có event type, id và reconnect |
| Trao đổi hai chiều liên tục | WebSocket hoặc giao thức phù hợp | SSE chỉ server-to-client |
| File lớn cần tải xuống | Response body streaming theo byte/Resource | Chọn API truyền byte và quản lý range/content disposition |
| Client cần biết batch thành công như một đơn vị | JSON response hữu hạn hoặc batch có giới hạn | Có thể validate/serialize trước khi commit |

Đừng chọn media type chỉ vì controller trả \`Flux\`. Hãy bắt đầu từ cách client cần parse, xử lý lỗi, reconnect và xác nhận hoàn tất.

## 16. Heartbeat và timeout cho stream dài

Một stream có thể không phát dữ liệu nghiệp vụ trong nhiều phút. Khi đó proxy, load balancer hoặc client có thể coi kết nối không hoạt động và đóng nó. Server cũng khó nhận biết client đã disconnect nếu không có dữ liệu để ghi.

Spring khuyến nghị gửi dữ liệu định kỳ cho streaming response để phát hiện client ngắt kết nối sớm hơn. Với SSE, comment-only event có thể làm heartbeat mà không tạo event nghiệp vụ:

~~~text
: keep-alive

~~~

Có thể chọn chu kỳ heartbeat ngắn hơn idle timeout của các tầng mạng. Không gửi heartbeat quá dày vì sẽ tăng lưu lượng và công việc parse.

Với NDJSON, nếu gửi heartbeat, hãy quy định rõ schema record, ví dụ \`{"type":"heartbeat"}\`; client phải nhận biết và bỏ qua record này. Không gửi một dòng tùy tiện khiến client parse thành domain object thất bại.

Ngoài heartbeat, cần cấu hình:

- Timeout ở server, reverse proxy, load balancer và client.
- Giới hạn số kết nối stream đồng thời.
- Chính sách reconnect và backoff.
- Event ID/offset nếu cần resume.
- Cleanup khi cancel và khi server shutdown.

## 17. DataBuffer và streaming raw bytes

Trong phần lớn endpoint, hãy để codec chuyển DTO thành bytes. Không cần thao tác trực tiếp với \`DataBuffer\` khi chỉ trả \`Flux<DTO>\`.

Chỉ dùng \`Flux<DataBuffer>\` khi ứng dụng thật sự cần kiểm soát raw byte stream, ví dụ proxy file hoặc chuyển tiếp nội dung binary. Khi đó cần chú ý:

- Một số server như Reactor Netty sử dụng pooled, reference-counted buffer.
- Buffer phải được release đúng lúc nếu ứng dụng tự tiêu thụ hoặc giữ buffer.
- Khi discard buffer trong pipeline, phải có xử lý discard thích hợp.
- Không giữ DataBuffer lâu hơn lifecycle cần thiết.
- Không chuyển buffer sang thread khác mà bỏ qua ownership/reference count.

Ví dụ cấu trúc khi tự xử lý buffer:

~~~java
Flux<DataBuffer> body = source()
    .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
~~~

Đây chỉ là đoạn minh họa; \`source()\` và import cần được cung cấp. Với codec chuẩn và DTO, framework quản lý buffer cho ứng dụng. Không thêm release thủ công vào pipeline DTO một cách tùy tiện.

## 18. Những lỗi thường gặp

1. **Thấy return type là Flux và kết luận HTTP streaming:** sai; cần kiểm tra writer, media type và hành vi flush.
2. **Trả Flux vô hạn với application/json:** Jackson encoder mặc định gom thành List và chờ completion, nên JSON array không thể hoàn tất.
3. **Dùng JSON array cho feed vô hạn:** client không có document hoàn chỉnh để parse theo cách thông thường. Dùng NDJSON hoặc SSE.
4. **Nhầm chunked transfer coding với record framing:** chunked là cơ chế đóng khung HTTP/1.1 body, không phải ranh giới mỗi Flux element.
5. **Cho rằng mỗi onNext tương ứng một TCP packet/HTTP chunk:** transport có thể gộp hoặc chia bytes. Client parse theo media type.
6. **Không khai báo streaming media type:** encoder có thể chọn chế độ aggregate phù hợp với media type mặc định.
7. **Dùng NDJSON nhưng client parse cả body thành một JSON document:** mỗi dòng là một document riêng; parse theo line.
8. **Dùng SSE nhưng client gọi response.json():** SSE là text/event-stream, cần EventSource hoặc SSE parser.
9. **Cho rằng flush bảo đảm browser render ngay:** proxy, compression, network và client vẫn có thể buffer.
10. **Không tắt proxy buffering cho endpoint cần realtime:** dữ liệu có thể bị giữ ở proxy. Kiểm tra cấu hình từng route.
11. **Dùng collectList/buffer cho stream lớn:** làm tăng memory và trì hoãn record đầu tiên. Xử lý từng phần tử hoặc batch có giới hạn.
12. **Không xử lý client cancellation:** upstream có thể tiếp tục công việc nếu nguồn không hỗ trợ cancel hoặc cleanup.
13. **Không gửi heartbeat cho stream idle lâu:** server có thể phát hiện disconnect muộn hoặc connection bị tầng trung gian đóng.
14. **Cho rằng có thể đổi HTTP status sau khi stream bắt đầu:** response đã commit; lỗi muộn phải được xử lý theo protocol stream.
15. **Không phân biệt error với cancel:** client disconnect thường tạo cancellation, không nhất thiết là application error.
16. **Tự subscribe trong controller:** tách công việc khỏi response lifecycle và làm cancellation/backpressure khó kiểm soát. Trả publisher cho WebFlux.
17. **Không giới hạn concurrency/queue:** nguồn nhanh hơn consumer có thể tạo backlog và tăng memory.
18. **Thao tác DataBuffer mà không release:** có thể gây memory leak với pooled buffer.
19. **Chỉ test publisher mà không test HTTP:** publisher phát từng phần tử không chứng minh codec và proxy truyền từng phần.
20. **Dùng WebTestClient rồi kết luận production proxy không buffer:** test integration chỉ kiểm tra đường đi trong môi trường test; cần end-to-end test ở môi trường triển khai.

## 19. Checklist xác minh streaming thật sự

Khi cần xác nhận endpoint gửi từng phần, kiểm tra theo thứ tự:

- Publisher có phát các phần tử cách nhau theo thời gian hay đã gom trước?
- Controller khai báo media type phù hợp chưa?
- Codec mặc định hoặc custom writer có encode/flush từng phần tử không?
- Response có bắt đầu ghi trước khi publisher hoàn tất không?
- Client có đọc incremental body hay chờ \`bodyToMono\`, \`json()\`, \`text()\` hoàn tất?
- cURL có dùng \`-N\` để tắt output buffering khi quan sát không?
- Proxy/gateway có response buffering không?
- Compression có trì hoãn flush không?
- HTTP version đang dùng là 1.1 hay 2? Đừng dựa vào \`Transfer-Encoding\` để kết luận.
- Khi client cancel, upstream có dừng và resource có được dọn không?
- Stream có heartbeat, timeout và reconnect policy không?
- Nếu error xảy ra sau record đầu, client hiểu cách stream kết thúc thế nào?
- Có test WebTestClient/StepVerifier và một test qua đường truyền gần production không?

Một endpoint chỉ được xem là streaming end-to-end khi dữ liệu thực sự tới client theo từng phần và client có thể xử lý trước khi publisher hoàn tất.

## 20. Câu hỏi tự kiểm tra

**1.** \`Flux<T>\` mô tả điều gì? Một publisher có thể phát 0 đến nhiều phần tử, sau đó complete hoặc error.

**2.** Trả \`Flux<T>\` có bảo đảm response HTTP được gửi từng phần không? Không. Còn phụ thuộc codec, media type, flush, transport, proxy và client.

**3.** Với Jackson encoder mặc định, \`Flux<T>\` + \`application/json\` có hành vi gì? Gom các phần tử thành List rồi serialize thành JSON array.

**4.** Media type nào phù hợp cho từng JSON record? \`application/x-ndjson\`.

**5.** SSE dùng media type nào? \`text/event-stream\`.

**6.** SSE event được phân cách như thế nào? Các field được ghi thành dòng; một dòng trống kết thúc event.

**7.** \`ServerSentEvent<T>\` bổ sung gì? Các trường như data, id, event, retry và comment.

**8.** Vì sao Flux vô hạn với application/json không phù hợp? Encoder mặc định chờ publisher hoàn tất để tạo JSON array.

**9.** Flush có bảo đảm browser nhận ngay không? Không; proxy, network và client có thể buffer.

**10.** HTTP/1.1 chunked có phải ranh giới record NDJSON không? Không. Newline mới là ranh giới record NDJSON.

**11.** HTTP/2 có dùng Transfer-Encoding: chunked không? Không; HTTP/2 dùng DATA frames để mang message content.

**12.** Dùng gì để kiểm thử stream bằng WebTestClient? \`FluxExchangeResult\` kết hợp \`StepVerifier\`.

**13.** Vì sao cần heartbeat? Để có dữ liệu gửi định kỳ và phát hiện client disconnect sớm hơn trong stream idle lâu.

**14.** Có thể đổi status thành 500 sau khi đã gửi event đầu tiên không? Không; response đã commit.

**15.** Backpressure có đồng nghĩa mỗi record được flush ngay không? Không. Backpressure điều tiết demand, còn flush là hành vi ghi response.

**Ghi nhớ:** \`Flux\` chỉ mô tả chuỗi reactive nhiều phần tử. Với codec Jackson mặc định, \`application/json\` gom \`Flux\` thành một JSON array; \`application/x-ndjson\` ghi và flush từng record; \`text/event-stream\` gửi và flush từng SSE event. Streaming thật sự còn phụ thuộc response writer, server, proxy và client. Hãy chọn media type theo hợp đồng dữ liệu, kiểm tra incremental delivery end-to-end, quản lý backpressure/cancellation, heartbeat và lỗi sau khi response đã commit.

**Tài liệu chính thức:**
- [Spring Framework 6.2 — Reactive Core, Jackson Encoder and Streaming](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html)
- [Spring Framework 6.2 — @ResponseBody and HTTP Message Writers](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/responsebody.html)
- [Spring Framework 6.2 — ServerSentEvent Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/codec/ServerSentEvent.html)
- [Spring Framework 6.2 — WebTestClient Streaming Responses](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html)
- [Reactor 3.8 — Backpressure](https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html)
- [RFC 9112 — HTTP/1.1 Transfer Coding](https://www.rfc-editor.org/rfc/rfc9112.html)
- [RFC 9113 — HTTP/2 DATA Frames](https://www.rfc-editor.org/rfc/rfc9113.html).