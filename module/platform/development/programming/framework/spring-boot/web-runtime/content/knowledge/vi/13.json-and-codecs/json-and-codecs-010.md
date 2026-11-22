# Kiểm soát bộ đệm và lỗi DataBufferLimitException trong Spring WebFlux

Trong **Spring WebFlux**, HTTP body thường đi qua các thành phần reactive như `Flux<DataBuffer>`, `HttpMessageReader`, `Decoder`, `HttpMessageWriter` và `Encoder`. Cơ chế này có thể xử lý dữ liệu theo luồng, nhưng **không bảo đảm mọi body đều được giải mã mà không cần gom dữ liệu vào bộ nhớ**.

Khi một codec cần tích lũy nhiều bytes để tạo ra một giá trị Java hoàn chỉnh, Spring có thể áp dụng giới hạn **maxInMemorySize**. Nếu lượng dữ liệu cần giữ trong bộ nhớ vượt ngưỡng, ta có thể gặp **`org.springframework.core.io.buffer.DataBufferLimitException`**.

Vấn đề cần hiểu không chỉ là cách tăng con số cấu hình. Người phát triển phải phân biệt:

1. **Codec aggregation limit**: lượng dữ liệu được phép gom vào bộ nhớ bởi một reader/decoder phù hợp.
2. **HTTP request body size limit**: tổng bytes client được phép gửi trong một request.
3. **Streaming/backpressure**: cách tiêu thụ từng phần dữ liệu và kiểm soát nhu cầu downstream.
4. **Resource ownership**: ai chịu trách nhiệm giải phóng `DataBuffer`, đặc biệt khi dùng pooled buffers của Netty.
5. **Server và WebClient**: lỗi có thể phát sinh cả khi server đọc request **và** khi HTTP client reactive đọc response.

**Thông điệp chính:** `maxInMemorySize` là **giới hạn bộ nhớ khi một số codec phải gom dữ liệu**; nó **không phải giới hạn toàn cục** cho tổng kích thước HTTP request, không thay thế bảo vệ ở reverse proxy, và cũng không biến một endpoint đọc toàn bộ body thành streaming chỉ vì nó trả `Mono`.

## 1. DataBuffer là gì?

`DataBuffer` là abstraction của Spring cho một vùng bytes. Trong WebFlux, HTTP server/client có thể phát hoặc nhận một dòng các `DataBuffer` thay vì bắt buộc lấy toàn bộ nội dung trước.

~~~text
HTTP request body 40 KiB
         |
         v
Netty nhận các phần bytes từ network
         |
         v
Flux<DataBuffer>
  |-- chunk A
  |-- chunk B
  |-- chunk C
  |-- ...
         |
         +--> đọc/ghi theo luồng nếu API hỗ trợ
         |
         +--> decoder gom bytes để tạo một Object
                    |
                    v
              Kiểm tra giới hạn
              maxInMemorySize
                    |
             +------+------+
             |             |
           <= limit     > limit
             |             |
          Decode       DataBufferLimitException
~~~

Kích thước mỗi chunk không phải một hợp đồng API cố định: một HTTP request có thể được nhận thành nhiều buffer khác nhau tùy transport, backpressure và thời điểm dữ liệu tới.

**Các triển khai buffer có thể khác nhau.** Reactor Netty có thể dùng pooled buffers dựa trên Netty; trong trường hợp ấy, việc giữ hoặc giải phóng reference sai có thể làm memory tăng hoặc dẫn tới lỗi truy cập buffer đã được release. Khi chỉ dùng `@RequestBody DTO` với codec mặc định, framework thường quản lý vòng đời buffer cho bạn. Khi tự thao tác `Flux<DataBuffer>`, cần hiểu ownership/lifecycle rõ hơn.

## 2. Vì sao WebFlux vẫn có lúc cần bộ đệm?

WebFlux hỗ trợ non-blocking I/O, nhưng một HTTP body có thể đại diện cho **một JSON object hoàn chỉnh**, một chuỗi text hoặc một cấu trúc cần parse đủ trước khi dựng đối tượng Java.

Ví dụ:

~~~http
POST /api/profile HTTP/1.1
Content-Type: application/json

{"name":"Lan","description":"... hàng nghìn ký tự ..."}
~~~

Controller có thể viết:

~~~java
@PostMapping("/api/profile")
Mono<Profile> create(@RequestBody Mono<Profile> body) {
    return body;
}
~~~

Đây là fragment, cần `Profile` và annotation imports. Dù controller nhận `Mono<Profile>`, **JSON decoder vẫn phải nhận đủ nội dung cần thiết để tạo Profile**. Nếu bộ phận codec phải aggregate vượt ngưỡng, request có thể thất bại trước khi controller có đối tượng Profile.

Tương tự, trong HTTP client:

~~~java
Mono<String> entireResponse = webClient.get()
        .uri("/large-text")
        .retrieve()
        .bodyToMono(String.class);
~~~

Đây là fragment với `webClient` được cấu hình sẵn. `bodyToMono(String.class)` biểu thị mong muốn nhận **toàn bộ nội dung dưới dạng một chuỗi**. Khi response lớn, codec phù hợp có thể phải giữ nhiều dữ liệu trong bộ nhớ và vượt `maxInMemorySize`.

**Reactive không đồng nghĩa zero-memory:** kết quả cần biểu diễn như một object/string hoàn chỉnh thường phát sinh chi phí bộ nhớ phù hợp với kích thước của nó. Muốn giảm aggregation phải thay đổi cách thiết kế dữ liệu và cách xử lý, không chỉ đổi kiểu return từ `String` sang `Mono<String>`.

## 3. DataBufferLimitException là lỗi gì?

Tên exception đầy đủ là:

~~~java
org.springframework.core.io.buffer.DataBufferLimitException
~~~

Nó báo rằng một thao tác xử lý/giải mã buffer **đã vượt giới hạn số bytes có thể giữ trong bộ nhớ** được áp dụng cho thao tác ấy. Một thông báo thường gặp có dạng:

~~~text
Exceeded limit on max bytes to buffer : 262144
~~~

Dòng trên chỉ là **ví dụ thông báo**, không phải text cố định giữa các Spring version và không phải mọi môi trường đều dùng ngưỡng 262144 bytes. **262144 bytes tương đương 256 KiB**.

Lỗi có thể xuất hiện khi:

- WebFlux server đọc request JSON bằng decoder và cần gom body thành một object.
- WebClient đọc response lớn qua `bodyToMono(String.class)`, DTO hoặc byte array.
- Đọc một số part/form/multipart hoặc một số kiểu content cần aggregation qua codec.
- Code tự gọi `DataBufferUtils.join(..., maxByteCount)` với giới hạn maxByteCount.
- Một custom reader/decoder đang tích lũy dữ liệu vào buffer và kiểm tra giới hạn.

Lỗi **không nhất thiết có nghĩa tổng Content-Length của request là quá lớn**. Một số codec giới hạn lượng dữ liệu của **từng giá trị** hoặc từng phần phải được aggregate; cách tính chính xác phụ thuộc codec, định dạng và phiên bản framework.

Một body có thể lớn hơn ngưỡng mà vẫn truyền theo luồng thành công nếu không có bước phải gom vượt ngưỡng đó. Ngược lại, một body nhỏ hơn tổng giới hạn HTTP của proxy vẫn có thể vượt aggregation limit của codec.

### 3.1. Không nhầm với OutOfMemoryError

`DataBufferLimitException` là cơ chế **từ chối việc buffer quá ngưỡng** trước khi bộ nhớ tăng không kiểm soát đối với thao tác cụ thể. Nó không có nghĩa JVM đã hết heap.

`OutOfMemoryError` là tình trạng tài nguyên bộ nhớ không đủ ở mức runtime và thường nghiêm trọng hơn. Việc tăng `maxInMemorySize` bừa bãi để “xóa” DataBufferLimitException có thể khiến heap/direct memory chịu tải lớn hơn và dẫn tới áp lực GC hoặc OOM thật.

## 4. maxInMemorySize: mặc định và phạm vi áp dụng

Trong nhiều cấu hình Spring WebFlux/Spring Framework 6.x, một ngưỡng mặc định thường thấy cho các codec cần aggregate là **256 KiB** (262144 bytes). **Không nên coi con số này là bất biến**: default, codec cụ thể và cách Spring Boot áp dụng có thể thay đổi theo phiên bản hoặc custom configuration.

`maxInMemorySize` thường liên quan:

- Một số decoder text/JSON và các default codecs của `ServerCodecConfigurer`.
- Default codecs của `ClientCodecConfigurer` dùng trong `WebClient`.
- Các đường xử lý multipart hoặc format đặc thù, với giới hạn và quy tắc riêng.
- Một số phương thức tập hợp buffer khi người viết tự đưa vào maxByteCount.

Nó **không** phải:

- Giới hạn kích thước tổng thể của mọi request HTTP gửi đến server.
- Giới hạn upload file bắt buộc trong mọi cơ chế multipart.
- Số bytes tối đa mà một `Flux<DataBuffer>` được phép phát trong cả vòng đời.
- Giới hạn heap cho JVM hoặc direct memory của Netty.
- Giới hạn số phần tử `Flux` hoặc số request concurrent.

Khi thay ngưỡng, hãy kiểm tra **codec nào thực sự đang đọc body**. Nếu code dùng DataBuffer trực tiếp hoặc một codec custom không tham gia default configurer, property chung có thể không bảo vệ đường đi ấy.

## 5. Cách cấu hình server bằng application.yml

Với **Spring Boot 3.x**, cách thông dụng để điều chỉnh giới hạn buffer cho các WebFlux codecs được Boot quản lý là thuộc tính:

~~~yaml
spring:
  codec:
    max-in-memory-size: 512KB
~~~

Ở đây `512KB` là ví dụ mức cấu hình chứ không phải khuyến nghị chung. Spring Boot xử lý giá trị dưới dạng `DataSize`; dùng đơn vị tường minh (`KB`, `MB`) để giảm nhầm lẫn với số bytes thô.

Ví dụ muốn đặt ngưỡng thấp để kiểm tra lỗi trong môi trường phát triển:

~~~yaml
spring:
  codec:
    max-in-memory-size: 8KB

server:
  port: 8080
~~~

Nếu codec đang xử lý một JSON object vượt ngưỡng nhỏ này, có thể quan sát DataBufferLimitException trong log hoặc error chain. Sau khi thử nghiệm, phải chọn mức production dựa trên loại payload được phép, số request đồng thời và memory budget.

**Đừng tự hiểu `8KB` là cấu hình chặn mọi HTTP request lớn hơn 8 KB.** Chẳng hạn endpoint nhận raw chunks trực tiếp có thể đi qua pipeline không aggregate theo cùng ngưỡng, còn một multipart upload có cấu hình và hành vi khác.

### 5.1. Tách cấu hình theo profile

Một hệ thống có thể có payload production lớn hơn môi trường dev:

~~~yaml
# application-prod.yml
spring:
  codec:
    max-in-memory-size: 1MB
~~~

Mục đích của profile là quản lý nhu cầu khác nhau theo môi trường, không dùng ngưỡng cao để né mọi vấn đề hiệu năng. Cần đối chiếu giới hạn proxy, container, downstream và API contract để tránh client nhận 413 ở proxy dù ứng dụng cho phép nhiều hơn.

### 5.2. Không chồng chéo property và customizer

Nếu đồng thời có `spring.codec.max-in-memory-size`, custom `WebFluxConfigurer` và custom `ServerCodecConfigurer` cùng sửa thông số ấy, kết quả cuối có thể phụ thuộc thứ tự áp dụng. Nên chọn một nơi làm nguồn cấu hình chính và có bài test xác nhận effective behavior.

## 6. Cấu hình bằng Java: ServerCodecConfigurer

Khi cần tùy chỉnh programmatically, Spring WebFlux có hook `WebFluxConfigurer#configureHttpMessageCodecs(ServerCodecConfigurer)`:

~~~java
package demo.buffer;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration(proxyBeanMethods = false)
class BufferCodecConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs().maxInMemorySize(512 * 1024);
    }
}
~~~

Đây là một class Java hoàn chỉnh trong project đã có Spring WebFlux và được component scan nhìn thấy. Giá trị `512 * 1024` là **524288 bytes** (512 KiB).

- `defaultCodecs()` cấu hình nhóm codec mặc định mà Spring đưa vào.
- `maxInMemorySize(...)` chỉnh giới hạn cho các codec mặc định có hỗ trợ quy tắc này.
- Không phải mọi custom codec đều tự động áp dụng con số này.
- Việc đăng ký codecs khác có thể làm thay đổi con đường decode.

**Đây là cách thay thế cho thuộc tính `spring.codec.max-in-memory-size` ở ví dụ phía trên**, không phải bắt buộc dùng đồng thời. Đừng thêm `@EnableWebFlux` chỉ để sửa ngưỡng: annotation đó có thể thay đổi phạm vi WebFlux auto-configuration mà Spring Boot thường quản lý.

Không cần xóa danh sách codec hoặc tắt defaults bằng `registerDefaults(false)` để thay đổi giới hạn bộ đệm.

## 7. Ví dụ Java 17+ chạy được: echo JSON, body lớn và NDJSON

Ví dụ dùng **Spring Boot 3.x**, **Java 17+**, web stack **WebFlux**, và mặc định Reactor Netty. Tạo project Gradle với Spring Boot plugin/dependency management rồi dùng:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

**Không thêm `spring-boot-starter-web` trong ví dụ này**, vì khi cả MVC và WebFlux cùng xuất hiện, Spring Boot thường ưu tiên suy luận Servlet web application mặc định.

Tệp **src/main/java/demo/buffer/BufferDemoApplication.java**:

~~~java
package demo.buffer;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class BufferDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(BufferDemoApplication.class, args);
    }
}

record EchoPayload(String content) {
}

@RestController
class BufferDemoController {

    @PostMapping(
            path = "/api/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    Mono<EchoPayload> echo(
            @RequestBody Mono<EchoPayload> body) {
        return body;
    }

    @GetMapping(
            path = "/api/large-text",
            produces = MediaType.TEXT_PLAIN_VALUE
    )
    Mono<String> largeText() {
        return Mono.fromSupplier(() -> "A".repeat(32 * 1024));
    }

    @GetMapping(
            path = "/api/events",
            produces = MediaType.APPLICATION_NDJSON_VALUE
    )
    Flux<Map<String, Integer>> streamEvents() {
        return Flux.range(1, 1000)
                .map(index -> Map.of("index", index));
    }
}
~~~

Cấu hình **src/main/resources/application.yml** cho mục đích học tập:

~~~yaml
spring:
  codec:
    max-in-memory-size: 8KB

server:
  port: 8080
~~~

**Không đặt đồng thời class `BufferCodecConfiguration` của mục 6 vào project demo này**, vì nó có thể ghi đè giá trị 8 KB mà ta muốn thử. Hai cấu hình đó chỉ là hai lựa chọn học tập.

### 7.1. Đọc ví dụ

- `POST /api/echo`: đọc một JSON object thành `EchoPayload`. Tại bước decode, body có thể cần aggregation, nên giới hạn 8 KB hữu ích để tái hiện lỗi.
- `GET /api/large-text`: tạo chuỗi 32 KiB và trả về với media type `text/plain`. Server ghi response; việc client cố **đọc toàn bộ** response thành String là trường hợp phù hợp để khảo sát giới hạn buffer của client.
- `GET /api/events`: phát một `Flux` gồm 1000 phần tử riêng lẻ dưới dạng NDJSON. Một dòng JSON được encode khi publisher phát từng element; khác với việc dựng một JSON array dài trong một chuỗi hoàn chỉnh.

**Điểm tinh tế:** `Mono<EchoPayload>` không làm việc giải mã JSON tự động stream từng field; nó biểu diễn một object kết quả. Trong khi đó, `Flux<Map<...>>` cùng media type NDJSON cho phép phát nhiều bản ghi mà không nhất thiết aggregate cả stream thành một object.

### 7.2. Khởi động và gửi body nhỏ

Dùng Gradle wrapper của project:

~~~bash
./gradlew bootRun
~~~

Trên Windows, dùng `gradlew.bat bootRun`. Trong terminal khác:

~~~bash
curl -i http://localhost:8080/api/echo \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data '{"content":"hello"}'
~~~

Với đúng dự án minh họa, không có filter/security khác thay đổi behavior, request nhỏ trả status **200 OK** và JSON body tương đương:

~~~json
{"content":"hello"}
~~~

Thứ tự field/headers và formatting JSON có thể khác tùy codec; đối với payload một field ở ví dụ, giá trị `hello` cần được giữ nguyên.

### 7.3. Tái hiện một JSON object vượt 8 KB

Tạo tệp **make_payload.py** để phát sinh một JSON object dài:

~~~python
import json
from pathlib import Path

payload = {"content": "x" * 16384}
Path("large.json").write_text(
    json.dumps(payload), encoding="utf-8"
)
print("large.json created")
~~~

Chạy:

~~~bash
python3 make_payload.py
~~~

Sau đó:

~~~bash
curl -i http://localhost:8080/api/echo \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data-binary @large.json
~~~

Nếu decoder áp dụng ngưỡng 8 KB cho giá trị JSON cần aggregate, request này sẽ kích hoạt giới hạn trước khi tạo được `EchoPayload`. Hãy quan sát **server log và exception cause chain** để xác định `DataBufferLimitException`.

**Không cam kết mã HTTP mặc định luôn là 413**: tùy vị trí exception, Spring Boot version, WebFlux exception handling và các lớp bao lỗi, client có thể nhận response khác. Muốn trả 413 một cách nhất quán cần có chính sách size limit và error mapping được kiểm chứng bằng integration test.

### 7.4. Quan sát NDJSON

Ví dụ:

~~~bash
curl -N -H 'Accept: application/x-ndjson' \
  http://localhost:8080/api/events
~~~

Response là một dòng JSON cho mỗi `index`; hai dòng đầu có cấu trúc:

~~~text
{"index":1}
{"index":2}
~~~

Stream phát tới index 1000 nếu client tiếp tục đọc và không có lỗi/cancel. Flag `-N` tắt output buffering của curl để dễ quan sát, nhưng **không bảo đảm mỗi phần tử tương ứng một TCP packet**. Reverse proxy hoặc transport có thể buffer/ghép dữ liệu theo cách khác.

## 8. Giới hạn trên WebClient khác với giới hạn server

Lỗi `DataBufferLimitException` có thể xảy ra dù server hoạt động bình thường. Ví dụ WebClient gọi một API trả response dài rồi thực thi:

~~~java
Mono<String> text = webClient.get()
        .uri("/api/large-text")
        .retrieve()
        .bodyToMono(String.class);
~~~

Đây là fragment cần bean `webClient` và base URL thích hợp. `bodyToMono(String.class)` yêu cầu body được decode thành một String duy nhất. Nếu client codec áp dụng ngưỡng nhỏ hơn body, reactive pipeline có thể kết thúc bằng `DataBufferLimitException` (có thể được bọc trong exception khác ở một số đường xử lý).

**Cần xác định phía phát sinh lỗi:**

| Vị trí | Điều đang diễn ra | Nơi kiểm tra trước |
|---|---|---|
| WebFlux server nhận JSON | Decoder đọc `@RequestBody` | Server codec config, API payload, log |
| WebClient đọc String/DTO lớn | Client decoder đang aggregate response | WebClient codec config, kích thước response |
| Multipart upload | Reader xử lý form/parts | Multipart config, file size/part constraints, temp disk |
| Custom reactive processing | `DataBufferUtils.join` hoặc custom accumulator | Logic aggregate, maxByteCount, buffer ownership |
| Proxy/ingress | Proxy từ chối request lớn | Request-size limit ở proxy, response 413 |

Nếu **WebClient** gặp giới hạn, chỉ tăng server `ServerCodecConfigurer` chưa chắc sửa được lỗi client. Ngược lại, sửa client limit không giúp server decode một inbound JSON object quá lớn.

### 8.1. Cấu hình riêng cho một WebClient

Trong Spring Framework 6.x/Spring Boot 3.x, có thể cấu hình codecs cho một WebClient cụ thể:

~~~java
package demo.buffer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
class PartnerClientConfiguration {

    @Bean
    WebClient partnerWebClient(WebClient.Builder builder) {
        return builder
                .baseUrl("https://partner.example.test")
                .codecs(configurer -> configurer.defaultCodecs()
                        .maxInMemorySize(2 * 1024 * 1024))
                .build();
    }
}
~~~

Ở ví dụ này, `2 * 1024 * 1024` là **2 MiB**. Base URL chỉ là hostname minh họa, không phải dịch vụ đang thực sự tồn tại để gọi. Bean không phát request khi khởi tạo.

Nếu dùng `WebClient.Builder` do Spring Boot quản lý, builder có thể đã được customizer/auto-configuration điều chỉnh. Cách ở trên chỉ ra rõ giới hạn cho client này, nhưng nên kiểm tra có customizer khác ghi đè hay không. Tránh tăng limit cho **mọi WebClient** nếu chỉ một partner API trả payload đặc biệt lớn.

### 8.2. Client tổng hợp hay stream body?

| Cách đọc response | Đặc điểm |
|---|---|
| `bodyToMono(String.class)` | Cần toàn bộ response dưới dạng một String |
| `bodyToMono(MyDto.class)` | Cần đủ dữ liệu để decode object tương ứng |
| `bodyToMono(byte[].class)` | Cần tạo byte array chứa nội dung |
| `bodyToFlux(MyDto.class)` với NDJSON | Có thể giải mã từng phần tử theo codec/media type |
| `bodyToFlux(DataBuffer.class)` | Cho phép xử lý từng buffer; phải quản lý ownership cẩn thận |

Nếu mục đích là tải file lớn về đĩa, tránh dùng `bodyToMono(byte[].class)` chỉ để có thể gọi `Files.write(...)`, vì như vậy đã giữ toàn bộ bytes trong RAM trước khi ghi.

Một fragment cho trường hợp download streaming với WebClient:

~~~java
Mono<Void> download = webClient.get()
        .uri("/archive.bin")
        .retrieve()
        .bodyToFlux(DataBuffer.class)
        .as(buffers -> DataBufferUtils.write(buffers, targetPath));
~~~

Đoạn trên cần `webClient`, `targetPath`, import `DataBuffer` và `DataBufferUtils`. Đây là fragment, chưa tự chạy vì targetPath và client chưa được khai báo. API `DataBufferUtils.write(Publisher<DataBuffer>, Path, ...)` trong Spring Framework 6.x có khả năng ghi từng buffer ra file và quản lý release theo hợp đồng API tương ứng; cần kiểm tra đường dẫn an toàn, quyền ghi, disk quota, lỗi/cancel và phiên bản library. Không sử dụng đường dẫn lấy trực tiếp từ URL hay filename của người dùng.

**Streaming không miễn phí:** network, disk I/O, CPU encode/decode, file descriptors và concurrent request vẫn là các giới hạn cần quản lý.

## 9. DataBufferUtils.join: chỗ dễ tạo bộ đệm lớn

Một anti-pattern thường gặp:

~~~java
Mono<DataBuffer> wholeBody = DataBufferUtils.join(body);
~~~

`body` là một `Flux<DataBuffer>` giả định. Lệnh này biểu thị mục tiêu **gom tất cả buffers thành một DataBuffer**. Nếu nguồn cực lớn, việc không có giới hạn có thể gây áp lực bộ nhớ; một overload khác cho phép đặt mức tối đa:

~~~java
Mono<DataBuffer> boundedBody =
        DataBufferUtils.join(body, 512 * 1024);
~~~

Giới hạn trên là 512 KiB. Nếu vượt, thao tác có thể phát `DataBufferLimitException`; khi xử lý thành công cũng cần hiểu cách release buffer được trả về sau khi tiêu thụ, theo ownership contract của `DataBufferUtils.join`.

**Không nên sửa lỗi bằng cách chuyển sang `join(body)` không giới hạn**. Đó chỉ là dời vấn đề từ một exception có kiểm soát sang nguy cơ tích lũy dữ liệu không giới hạn.

Nếu nghiệp vụ chỉ cần xử lý từng phần, hãy dùng pipeline streaming. Nếu cần parse một object đơn, hãy xác định kích thước object lớn nhất được phép, đặt limit phù hợp và có chiến lược phản hồi lỗi rõ ràng.

## 10. Đọc và giải phóng pooled DataBuffer

Netty có thể sử dụng `PooledDataBuffer` với cơ chế reference counting. Khi viết custom operator, người phát triển cần hiểu ai sở hữu buffer ở từng nhánh.

**Một số nguyên tắc:**

1. Đừng giữ tham chiếu tới buffer sau khi bên sở hữu đã release nó.
2. Đừng gọi release hai lần nếu API/framework đã quản lý.
3. Nếu tự consume buffer và không chuyển giao quyền sở hữu cho framework/operator khác, cần release theo hợp đồng API.
4. Khi dùng `DataBufferUtils.join`, phải giải phóng buffer kết quả sau khi xử lý.
5. Khi pipeline có lỗi/cancellation/discard, cần bảo đảm những buffer đang sở hữu không bị bỏ quên.
6. Ưu tiên `FilePart.transferTo`, framework codecs và `DataBufferUtils.write` thay vì xây lại toàn bộ logic buffer/file.

Một fragment xử lý buffer rồi release trong `finally`, **chỉ phù hợp khi code của bạn thực sự là bên sở hữu buffer ở giai đoạn đó**:

~~~java
.map(buffer -> {
    try {
        int remaining = buffer.readableByteCount();
        return remaining;
    } finally {
        DataBufferUtils.release(buffer);
    }
})
~~~

Đây là fragment cần một stream `DataBuffer` và imports. Không tự sao chép đoạn release này vào mọi `doOnNext` hay codec framework nếu framework vẫn kỳ vọng đọc buffer sau đó.

### 10.1. Khi nào dùng doOnDiscard?

Một số operator có thể loại bỏ dữ liệu khi cancellation, lỗi hoặc filter. Trong các pipeline có ownership phù hợp, Spring/Reactor hỗ trợ cleanup hook như `doOnDiscard(DataBuffer.class, DataBufferUtils::release)`. Nhưng cleanup cần được áp dụng đúng chỗ và bảo đảm buffer chưa được release ở nhánh khác; không dùng một hook chung như bùa giải mọi leak.

### 10.2. Direct memory và heap

Khi làm việc với Netty pooled/direct buffers, memory usage có thể biểu hiện không giống một object heap thông thường. Giới hạn heap cao chưa đủ nếu direct memory hay pooled buffers bị giữ sai. Cần quan sát heap, direct/native memory, GC và Netty allocator metrics khi có cấu hình instrument tương ứng.

## 11. Multipart upload và giới hạn riêng

Một file upload vài chục MB không nhất thiết phải được giữ toàn bộ trong heap. Trong Spring WebFlux có API `FilePart` và các cấu hình multipart reader cho phép xử lý part/file với giới hạn bộ nhớ và đĩa phù hợp.

Ví dụ fragment controller:

~~~java
@PostMapping(
        path = "/upload",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
Mono<String> upload(@RequestPart("file") FilePart file) {
    Path destination = Path.of("/srv/app-uploads")
            .resolve(java.util.UUID.randomUUID() + ".bin");

    return file.transferTo(destination)
            .thenReturn("stored");
}
~~~

Đây là fragment, cần import `FilePart`, `Path`, Reactor `Mono`, các annotations, và **thư mục đích phải tồn tại và có quyền ghi**. Không nên đưa tên file do client gửi qua `file.filename()` trực tiếp vào path vì nguy cơ path traversal, ghi đè hoặc tên không hợp lệ. Luôn áp dụng quota, xác thực, kiểm tra nội dung và giới hạn file.

**Không nhầm:** `spring.codec.max-in-memory-size` chỉ là một mảnh ghép; multipart có thể có giới hạn riêng cho file part, form field, số lượng part, bộ nhớ/đĩa tạm. Tên và hành vi từng property thay đổi theo Spring Boot/Spring Framework version, nên cần đối chiếu chính phiên bản đang triển khai.

Cần có chính sách giới hạn **tổng upload size**, **mỗi file**, **số part**, **disk usage**, **thời gian upload** và **concurrency**, bằng sự kết hợp của proxy/server và multipart reader. Đừng nghĩ tăng maxInMemorySize sẽ giải quyết mọi loại upload lớn.

## 12. Lựa chọn cấu trúc JSON phù hợp với streaming

Có sự khác nhau giữa **JSON array** và **NDJSON**.

JSON array:

~~~json
[{"id":1},{"id":2},{"id":3}]
~~~

NDJSON:

~~~text
{"id":1}
{"id":2}
{"id":3}
~~~

Khi endpoint trả `Flux<Item>`, việc streaming từng element có thể thuận lợi với `application/x-ndjson` vì mỗi dòng là một giá trị JSON riêng. Tuy nhiên:

- Codec vẫn có thể giới hạn kích thước của **mỗi element** hoặc một giá trị phải aggregate.
- Một phần tử JSON khổng lồ vẫn có thể vượt limit dù cả stream được xử lý theo luồng.
- Client phải hỗ trợ streaming format và backpressure phù hợp.
- Proxy, TLS và HTTP transport có thể buffer/ghép các chunk.
- Không khẳng định từng item luôn xuất hiện ngay lập tức ở client khi server emit.

Một pattern WebFlux:

~~~java
@GetMapping(
        path = "/events",
        produces = MediaType.APPLICATION_NDJSON_VALUE
)
Flux<Event> stream() {
    return eventService.events();
}
~~~

Đây là fragment, cần `Event`, `eventService` và imports. Khi API contract yêu cầu một JSON object duy nhất có cấu trúc lớn, không thể tùy tiện đổi thành NDJSON mà không đồng bộ thay đổi với client.

## 13. DataBufferLimitException và HTTP 413

`DataBufferLimitException` **không phải trực tiếp một HTTP status code**. Nó là exception trong quá trình xử lý buffer. Trên server, HTTP status cuối cùng có thể phụ thuộc nơi exception được ném, lớp exception bao ngoài, error handler của WebFlux và trạng thái response đã commit.

### 13.1. Cần phân biệt ba trường hợp

- **Proxy trả 413:** request có thể chưa đến Spring Boot. Tăng codec limit trong app sẽ không thay đổi proxy limit.
- **WebFlux decoder phát DataBufferLimitException:** request đã đi tới codec nhưng vượt ngưỡng aggregation. Không mặc định client nhận 413 nếu chưa có mapping/test.
- **WebClient decoder phát DataBufferLimitException:** ứng dụng đang đóng vai **HTTP client**; đây là lỗi của pipeline client đọc response, không phải HTTP 413 từ server được gọi.

Để xây dựng hợp đồng API ổn định, có thể xử lý trực tiếp những `DataBufferLimitException` được error resolver chuyển đến:

~~~java
@RestControllerAdvice
class BodySizeAdvice {

    @ExceptionHandler(DataBufferLimitException.class)
    ResponseEntity<Map<String, String>> tooLarge(
            DataBufferLimitException ex) {
        return ResponseEntity
                .status(HttpStatus.PAYLOAD_TOO_LARGE)
                .body(Map.of("error", "payload_too_large"));
    }
}
~~~

Đây là class minh họa cần imports `RestControllerAdvice`, `ExceptionHandler`, `ResponseEntity`, `HttpStatus`, `DataBufferLimitException` và `Map`. **Không bảo đảm mọi codec failure đều được dispatch trực tiếp dưới đúng class exception này:** một số đường decode có thể bọc lỗi trong `ServerWebInputException` hoặc exception khác. Khi đó cần error handling phù hợp và test thực tế để bảo đảm response 413. Không map toàn bộ `ServerWebInputException` thành 413 vì lỗi cú pháp JSON/validation thường không phải payload quá lớn.

Nếu response đã được commit hoặc streaming đã gửi một phần bytes, không phải lúc nào cũng đổi HTTP status sang 413 được. Vì vậy, đặt giới hạn và kiểm tra càng sớm càng tốt đối với endpoint có nguy cơ body lớn.

### 13.2. 413 không thay cho kiểm tra input

Mặc dù một request dưới giới hạn codec, nó vẫn có thể chứa JSON sâu bất thường, trường văn bản khổng lồ trong phạm vi limit hoặc dữ liệu không hợp lệ về nghiệp vụ. Kết hợp:

- Validation cho DTO và giá trị business.
- Content-Type whitelist và API contract cụ thể.
- Global request size restrictions ở hạ tầng.
- Concurrency/rate limits để giảm tài nguyên bị chiếm.
- Timeout và giới hạn số kết nối.
- Kế hoạch xử lý lỗi không tiết lộ stack trace cho client.

## 14. Kiểm thử tự động cho giới hạn buffer

Có hai cấp kiểm thử quan trọng:

1. **Behavior của ứng dụng nhỏ:** JSON hợp lệ dưới ngưỡng phải thành công; payload vượt ngưỡng phải bị từ chối theo error policy đã thiết kế.
2. **Đường truyền HTTP thực:** test với embedded server và HTTP client để thấy cả server codec, proxy thực tế (nếu có) và client codec.

Trong Spring Boot 3.x có thể dùng `spring-boot-starter-test`. Một bài test WebFlux dùng `WebTestClient`, nhưng phải phân biệt test client binding tại ApplicationContext với HTTP client qua server thật.

Một test minh họa dùng **`WebTestClient.bindToApplicationContext(...)`** để không phụ thuộc vào auto-injection client:

~~~java
package demo.buffer;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
class BufferDemoApplicationTest {

    @Autowired
    ApplicationContext context;

    @Test
    void smallJsonBodyStillWorks() {
        WebTestClient client = WebTestClient
                .bindToApplicationContext(context)
                .configureClient()
                .build();

        client.post()
                .uri("/api/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue(new EchoPayload("ok"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.content").isEqualTo("ok");
    }
}
~~~

Tệp test nằm ở **src/test/java/demo/buffer/BufferDemoApplicationTest.java** trong **cùng dự án** với ứng dụng `BufferDemoApplication`. `WebTestClient` đúng package là `org.springframework.test.web.reactive.server.WebTestClient`. Vì test dùng `bindToApplicationContext`, nó không đòi hỏi một HTTP port đang mở; đây là WebFlux handler integration test trong process.

Thêm vào `build.gradle`:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Để test lỗi khi vượt ngưỡng, cần cân nhắc error handling hiện có: nếu không có chính sách chuẩn hóa status, **đừng viết một assertion 413 cứng** khi framework có thể trả status khác. Cách chặt chẽ là thêm error mapping được thiết kế cho đúng exception path, rồi assert status/body bằng HTTP test end-to-end.

### 14.1. Khi cần test WebClient giới hạn riêng

Đừng chỉ gửi payload lớn đến server rồi kết luận client codec bị giới hạn. Một server có thể trả response lớn hoàn toàn hợp lệ, trong khi **chính client** không decode nổi một `String`. Với test client, cấu hình `WebClient.builder().codecs(...maxInMemorySize(...))` rồi đọc response; kiểm tra error cause chain. Tránh gọi `block()` trong event-loop thread — nếu dùng `block()` trong test chạy trên JUnit thread để quan sát lỗi, cần bảo đảm test không chặn pipeline server và đóng resources đúng cách.

## 15. Tại sao không tăng limit lên hàng chục MB ngay?

Giả sử một JSON request có thể đòi buffer 20 MiB và có 100 request cần aggregate đồng thời. Chỉ riêng dữ liệu buffer trung gian đã có thể tiêu thụ đáng kể bộ nhớ; còn có đối tượng Java sau decode, request metadata, network buffers và những cấu trúc khác. Không thể suy ra bộ nhớ chính xác bằng phép nhân đơn giản, nhưng nguy cơ bùng phát memory là có thật.

Trước khi tăng ngưỡng, trả lời:

1. **Payload hợp lệ tối đa là bao nhiêu?** Chỉ vì client vô tình gửi 50 MB không có nghĩa API phải chấp nhận.
2. **Có thể đổi contract sang upload/streaming không?** Một file hoặc dòng sự kiện không nhất thiết phải gom vào một JSON string.
3. **Có bao nhiêu request concurrent?** Max size mỗi request nhân với concurrency tạo ra khả năng peak usage lớn.
4. **Bộ nhớ cấp cho pod/JVM bao nhiêu?** Heap, direct memory, thread stacks và OS đều dùng tài nguyên.
5. **Có proxy limit không?** Proxy từ chối trước thì chỉnh Spring codec không thay đổi được hành vi.
6. **Có custom decoder hoặc `DataBufferUtils.join` riêng không?** Property chung có thể không áp dụng ở chỗ đó.
7. **Có client nào đang aggregate response không?** Nếu lỗi ở WebClient, không nên sửa server.
8. **Đã có benchmark/metrics chưa?** Quan sát p95/p99, GC và buffer allocation thay vì phỏng đoán.

Một mức limit đúng phải dựa trên **hợp đồng payload và memory budget**, không theo thói quen đặt thật cao.

## 16. Phân biệt maxInMemorySize với backpressure

Reactive Streams có **backpressure**: downstream phát demand để điều tiết số phần tử upstream phát trong những trường hợp được hỗ trợ. Nhưng backpressure không thay cho size limit:

- Một phần tử JSON 10 MiB vẫn là một phần tử, dù subscriber yêu cầu đúng một phần tử.
- Một `Mono<String>` chỉ phát một giá trị nhưng giá trị ấy có thể rất lớn.
- `Flux<DataBuffer>` có thể stream tổng hàng GB qua nhiều buffers, nhưng phải kiểm soát tốc độ và tài nguyên lưu trữ.
- Nguồn phát dữ liệu không hỗ trợ backpressure có thể đòi hỏi buffering/dropping/error policy.
- Decoder có thể vẫn phải aggregate đủ để dựng một object.

Vì thế, **backpressure điều tiết dòng dữ liệu**, còn **maxInMemorySize giới hạn lượng dữ liệu được buffer cho một số thao tác**. Cần cả hai khi xử lý streaming dữ liệu lớn.

## 17. Điều tra lỗi theo từng bước

Khi thấy `DataBufferLimitException` trong log:

1. **Xác định phía phát sinh:** WebFlux server đang decode request, WebClient đang decode response, hay custom `DataBufferUtils.join`?
2. **Đọc exception chain:** lỗi có bị bọc trong `ServerWebInputException`, `DecodingException` hoặc exception client khác không?
3. **Xác định media type và type Java:** JSON object, String, byte[], multipart part, NDJSON stream hay custom format?
4. **Đo kích thước thực:** tổng HTTP payload, kích thước từng JSON value/part, decoded object và buffer usage.
5. **Kiểm tra effective limit:** `spring.codec.max-in-memory-size`, `WebFluxConfigurer`, `ServerCodecConfigurer`, `WebClient` riêng, custom codecs.
6. **Kiểm tra hạ tầng:** reverse proxy, CDN, ingress, load balancer, HTTP request size và timeout.
7. **Đánh giá thiết kế:** endpoint có thể chuyển từ `bodyToMono(byte[].class)` sang streaming file không?
8. **Nếu phải tăng limit:** tăng có đo đạc, dùng payload hợp lệ tối đa, test concurrency và quan sát memory.
9. **Bổ sung regression test:** body nhỏ thành công; body vượt ngưỡng bị xử lý có kiểm soát; streaming hoạt động.
10. **Đo lại production:** heap/direct memory, GC, rate 4xx/5xx, payload sizes và timeout.

Trong hệ thống có Micrometer/Actuator, có thể quan sát HTTP server/client metrics; các metric về Netty buffer và allocator cần được bật/hỗ trợ riêng. Không khẳng định mọi môi trường tự xuất sẵn những metric đó.

## 18. Các lỗi thiết kế thường gặp

### Lỗi 1 — Dùng maxInMemorySize như giới hạn request toàn cục

Không đúng. Nó áp dụng cho quá trình aggregation của những codec nhất định. Muốn hạn chế toàn bộ request body, cần cấu hình proxy/server/ingress và cơ chế kiểm soát dữ liệu tương ứng.

### Lỗi 2 — Tăng limit tới 100MB chỉ để làm mất exception

Điều này có thể biến từ chối có kiểm soát thành memory pressure hoặc OOM. Hãy kiểm tra kích thước hợp lệ và concurrency; cân nhắc streaming.

### Lỗi 3 — Sửa server property khi lỗi nằm ở WebClient

`WebClient` có client codecs. Nếu response quá lớn với `bodyToMono(String.class)`, cần xem client codec hoặc đổi cách đọc response. Server decoder limit không giải quyết việc client aggregate quá nhiều.

### Lỗi 4 — Chuyển Mono<String> thành Flux<String> nhưng vẫn gom một chuỗi khổng lồ

Nếu nguồn đã là một String dài, đổi type publisher không có nghĩa đã stream dữ liệu từng phần. Thiết kế cần phát các chunk/records thực sự và chọn media type phù hợp.

### Lỗi 5 — Dùng DataBufferUtils.join không giới hạn

`join` biểu thị aggregation; bỏ maxByteCount chỉ né exception mà không bảo vệ memory. Dùng overload có giới hạn hoặc không join khi chỉ cần streaming.

### Lỗi 6 — Quên giải phóng pooled DataBuffer khi tự xử lý

Có thể gây direct memory leak. Dùng lifecycle operators của Spring và release theo ownership chính xác; tránh double release.

### Lỗi 7 — Coi multipart upload và JSON body là một

Multipart có giới hạn và đường xử lý riêng, có thể dùng disk-backed storage. Dùng `FilePart.transferTo` khi phù hợp và cấu hình limits cho từng part/file, không buộc file lớn thành JSON/base64.

### Lỗi 8 — Khẳng định mọi DataBufferLimitException tự trả 413

Exception có thể được bọc, được xử lý ở server hoặc client, và response có thể đã commit. Hãy kiểm thử HTTP status thực cùng error handler.

### Lỗi 9 — Chỉ kiểm tra response code

Không kiểm tra heap/direct memory, concurrency, logs và GC sẽ bỏ sót hệ quả của tăng limit. Đo cả tài nguyên và latency.

### Lỗi 10 — Để untrusted filename quyết định đường dẫn upload

Có nguy cơ path traversal và ghi đè file. Sinh tên server-side, giới hạn thư mục, xác thực và quota.

### Lỗi 11 — Log nguyên body để debug buffer

Body lớn có thể làm log rất nặng và lộ dữ liệu nhạy cảm. Ghi payload size, media type, route, request ID và thông tin lỗi cần thiết; không log mật khẩu/token.

### Lỗi 12 — Chỉ test body nhỏ

Khi tăng limit hoặc đổi codec, cần có test cho payload vừa ngưỡng, vượt ngưỡng và nhiều request đồng thời. Ngoài ra kiểm tra client đọc response và multipart nếu hệ thống dùng chúng.

## 19. Checklist trước khi đưa cấu hình lên production

- Xác định rõ WebFlux/Reactor Netty hay Spring MVC Servlet stack đang chạy.
- Tìm vị trí phát sinh `DataBufferLimitException`: server decoder, WebClient decoder hay custom buffer aggregation.
- Hiểu ngưỡng `maxInMemorySize` là giới hạn in-memory aggregation, **không** là tổng HTTP upload size cap.
- Chọn giới hạn theo API contract, memory budget và concurrency, không tăng vô hạn.
- Sử dụng `spring.codec.max-in-memory-size` hoặc `ServerCodecConfigurer.defaultCodecs().maxInMemorySize(...)` có chủ đích.
- Với WebClient cụ thể, cân nhắc `WebClient.Builder.codecs(...)` thay vì sửa toàn bộ server codecs.
- Dùng streaming/NDJSON cho nhiều bản ghi khi client và API contract hỗ trợ.
- Với file upload lớn, dùng multipart/`FilePart.transferTo` và quota thay vì gom cả file trong `byte[]`.
- Không gọi `DataBufferUtils.join` thiếu giới hạn khi body không đáng tin; quản lý `DataBuffer` theo ownership/release contract.
- Kiểm tra response 413/error mapping thật, không suy luận trực tiếp từ tên exception.
- Đặt proxy/ingress limits, timeouts, rate/concurrency restrictions và validation phù hợp.
- Test body nhỏ, body vượt limit, WebClient large response, streaming, cancellation, concurrency và memory metrics.
- Bảo vệ logs và client error body khỏi lộ stack trace hoặc dữ liệu riêng tư.

**Kết luận:** `DataBufferLimitException` là tín hiệu một bước **gom dữ liệu vào bộ nhớ đã vượt ngưỡng** trong WebFlux hoặc pipeline liên quan. Cách khắc phục bền vững là xác định **ai đang aggregate dữ liệu và vì sao**, chọn giới hạn phù hợp cho server/client, chuyển sang streaming khi bài toán cho phép, quản lý buffer đúng vòng đời và kiểm thử HTTP/error/memory behavior. Việc chỉ tăng `maxInMemorySize` là một thay đổi cấu hình, không thay thế cho thiết kế payload và giới hạn tài nguyên an toàn.