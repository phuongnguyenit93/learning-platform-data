# Đọc request body một lần và giới hạn khi muốn đọc lại trong filter

## 1. Vì sao request body cần được xử lý đặc biệt?

Trong Spring WebFlux, request body được biểu diễn dưới dạng một luồng dữ liệu reactive, thường là **Flux<DataBuffer>** ở tầng HTTP. Các codec có thể chuyển luồng byte này thành đối tượng Java, ví dụ:

~~~java
Mono<CreateOrderRequest> body =
        exchange.getRequest().getBody()
                .as(BodyExtractors.toMono(CreateOrderRequest.class));
~~~

Đoạn trên chỉ minh họa ý tưởng ở tầng exchange; trong controller, cách quen thuộc hơn là dùng **@RequestBody Mono<CreateOrderRequest>**.

Điểm quan trọng: request body đến từ một kết nối HTTP đang được đọc theo luồng. Sau khi một consumer đọc hết dữ liệu, consumer tiếp theo không thể mặc định yêu cầu server đọc lại từ socket như đọc một mảng byte trong bộ nhớ. **Hãy coi body của một request là nguồn dữ liệu one-shot** trừ khi ứng dụng chủ động tạo cơ chế cache/replay.

Ví dụ filter đọc body để kiểm tra chữ ký hoặc xác thực JSON:

~~~java
return DataBufferUtils.join(exchange.getRequest().getBody())
        .flatMap(buffer -> {
            inspect(buffer);
            return chain.filter(exchange);
        });
~~~

Filter đã tiêu thụ body gốc. Nếu controller phía sau tiếp tục dùng @RequestBody, nó có thể nhận body rỗng hoặc không còn dữ liệu để giải mã. Việc chỉ gọi lại getBody() hoặc subscribe lần thứ hai không làm nội dung mạng tự quay lại từ đầu.

Có ba cách xử lý thường gặp:

1. **Không đọc body trong filter:** ưu tiên kiểm tra header, method, path hoặc metadata nếu đủ cho yêu cầu.
2. **Đọc và xử lý một lần:** filter tiêu thụ body, sau đó truyền kết quả đã phân tích qua ServerWebExchange attributes hoặc một context riêng; downstream không đọc body lần nữa.
3. **Cache có giới hạn rồi replay:** filter đọc body gốc một lần, sao chép thành byte[], thay request bằng ServerHttpRequestDecorator và phát một DataBuffer mới cho mỗi lần downstream subscribe.

Bài này tập trung vào cách thứ ba, khi filter bắt buộc kiểm tra nội dung nhưng controller hoặc handler vẫn cần đọc body.

## 2. Các thành phần cần hiểu

### 2.1. ServerWebExchange và WebFilter

**ServerWebExchange** đại diện cho một lần trao đổi HTTP, cung cấp request, response và request attributes. Nó có thể được mutate để dùng một ServerHttpRequest khác:

~~~java
ServerWebExchange mutated =
        exchange.mutate()
                .request(decoratedRequest)
                .build();
~~~

Đây là cách thay request cho phần filter chain tiếp theo. Exchange mới vẫn đại diện cùng một request/response lifecycle; nó chỉ sử dụng request decorator đã cung cấp.

**WebFilter** là contract xử lý request theo chuỗi:

~~~java
Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain);
~~~

Filter có thể kiểm tra request, thay exchange rồi gọi chain.filter(mutatedExchange), hoặc kết thúc sớm bằng response lỗi. Nó phải trả về Mono<Void> để framework điều phối toàn bộ quá trình reactive.

### 2.2. ServerHttpRequest và ServerHttpRequestDecorator

**ServerHttpRequest** cung cấp method, URI, headers và body. Body thường là Flux<DataBuffer>.

**ServerHttpRequestDecorator** ủy quyền phần lớn hành vi cho request gốc nhưng cho phép override phương thức cần thay đổi, thường là getBody():

~~~java
ServerHttpRequest decorated = new ServerHttpRequestDecorator(original) {
    @Override
    public Flux<DataBuffer> getBody() {
        // Phát body đã cache.
    }
};
~~~

Đây là điểm mở rộng thích hợp để downstream nhận dữ liệu đã cache thay vì body gốc đã bị filter tiêu thụ.

### 2.3. DataBuffer và DataBufferFactory

**DataBuffer** là abstraction byte buffer của Spring. Tùy server, nó có thể được hỗ trợ bởi heap buffer hoặc pooled/direct buffer của Netty.

**DataBufferFactory** tạo hoặc wrap DataBuffer. Factory có thể truy cập từ ServerHttpResponse:

~~~java
DataBuffer buffer =
        exchange.getResponse().bufferFactory().wrap(bytes);
~~~

Phương thức wrap(byte[]) tạo DataBuffer dựa trên byte array đã có. Trong decorator, hãy tạo một DataBuffer mới mỗi lần getBody() được subscribe để mỗi consumer có vị trí đọc riêng.

### 2.4. DataBufferUtils.join và release

**DataBufferUtils.join(Publisher<DataBuffer>)** gom nhiều buffer thành một buffer tổng hợp. Overload có giới hạn:

~~~java
Mono<DataBuffer> joined =
        DataBufferUtils.join(request.getBody(), 64 * 1024);
~~~

Tham số thứ hai là giới hạn số byte được phép gom. Khi vượt giới hạn, Spring phát **DataBufferLimitException**.

Khi join thành công, consumer nhận buffer tổng hợp và phải giải phóng nó sau khi đọc. Nếu nguồn lỗi hoặc bị cancel trong lúc gom, DataBufferUtils quản lý việc release các buffer đã tích lũy theo contract của API. Không giữ pooled DataBuffer lâu hơn thời gian cần thiết.

## 3. Quy trình cache và replay

Một filter cache body có giới hạn thực hiện theo trình tự:

~~~text
HTTP request body
       |
       v
Original Flux<DataBuffer>
       |
       v
DataBufferUtils.join(maxBytes)
       |
       +-- vượt giới hạn --> DataBufferLimitException --> HTTP 413
       |
       v
Đọc joined DataBuffer vào byte[]
       |
       +--> release joined DataBuffer
       |
       v
Kiểm tra nội dung trong filter
       |
       v
ServerHttpRequestDecorator
       |
       +--> getBody() subscription #1 -> DataBuffer mới
       +--> getBody() subscription #2 -> DataBuffer mới
       +--> getBody() subscription #n -> DataBuffer mới
       |
       v
Controller / downstream codec đọc body như bình thường
~~~

Các nguyên tắc:

- Chỉ subscribe body gốc một lần để tạo cache.
- Sao chép nội dung sang byte[] trước khi release buffer tổng hợp.
- Không trả lại cùng một DataBuffer đã bị đọc hoặc đã release.
- Mỗi lần downstream gọi getBody() phải nhận DataBuffer mới, có read position mới.
- Áp dụng giới hạn byte ngay khi join; không dựa duy nhất vào Content-Length.
- Nếu filter không cần downstream đọc lại, không cần tạo decorator.

## 4. Vì sao không nên cache lại chính DataBuffer?

Một cách dễ mắc lỗi là giữ buffer tổng hợp rồi phát lại cùng object:

~~~java
DataBuffer cached = ...;

@Override
public Flux<DataBuffer> getBody() {
    return Flux.just(cached);
}
~~~

Cách này không an toàn nếu có nhiều subscription:

- Consumer đầu tiên đã di chuyển read position của buffer.
- Consumer tiếp theo có thể thấy không còn byte để đọc.
- Nếu buffer là pooled, release ở consumer đầu tiên có thể làm buffer không còn hợp lệ.
- Nếu tăng reference count mà không giảm đúng lúc, ứng dụng có thể rò pooled memory.
- Hai consumer đồng thời có thể cạnh tranh trên cùng trạng thái buffer.

Giải pháp dễ kiểm soát hơn cho body nhỏ là **copy sang byte[] rồi wrap một DataBuffer mới cho từng subscription**. Byte array phải được coi là bất biến trong suốt vòng đời replay. Không để code downstream sửa nội dung mảng.

## 5. Giới hạn bộ nhớ: Content-Length không đủ

### 5.1. Kiểm tra Content-Length chỉ là tối ưu sớm

Có thể từ chối sớm nếu client khai báo body lớn hơn giới hạn:

~~~java
long contentLength = request.getHeaders().getContentLength();

if (contentLength > MAX_BODY_BYTES) {
    return payloadTooLarge(exchange);
}
~~~

Nhưng Content-Length có thể không có, đặc biệt khi request dùng streaming hoặc chunked transfer. Giá trị -1 có nghĩa là không biết trước tổng số byte.

Vì vậy, kiểm tra header không thay thế giới hạn thực tế của DataBufferUtils.join:

~~~java
DataBufferUtils.join(request.getBody(), MAX_BODY_BYTES)
~~~

Giới hạn ở bước join mới bảo vệ trường hợp body đến từng chunk mà không có Content-Length đáng tin cậy.

### 5.2. Chọn giới hạn theo loại request

Ví dụ minh họa:

| Loại body | Chiến lược thường phù hợp |
| --- | --- |
| JSON nhỏ cho lệnh tạo/cập nhật | Có thể cache với giới hạn vài chục hoặc vài trăm KiB |
| JSON lớn | Cân nhắc xử lý một lần hoặc tăng giới hạn có kiểm soát |
| Upload file | Streaming, không gom toàn bộ file vào byte[] |
| Multipart | Dùng multipart API hoặc PartEvent theo luồng |
| SSE hoặc streaming request | Xử lý từng phần tử; không cache toàn bộ stream |
| Body không giới hạn hoặc không biết kích thước | Không bật replay toàn bộ; đặt giới hạn và chính sách rõ ràng |

Nếu mỗi request cache tối đa 64 KiB và có 1.000 request đồng thời, riêng phần byte[] đã có thể chiếm khoảng 64 MiB, chưa tính buffer đang gom, object và overhead khác. Trong thời gian copy, joined DataBuffer và byte[] có thể cùng tồn tại. Chọn giới hạn dựa trên concurrency thực tế.

### 5.3. Codec limit và manual cache limit là hai việc khác nhau

Cấu hình maxInMemorySize của codec kiểm soát một số thao tác decode/aggregate của message reader/writer. Nếu filter tự gọi DataBufferUtils.join, filter phải tự truyền maxByteCount.

Không giả định giới hạn codec tự động bảo vệ mọi đoạn code thủ công đang gom DataBuffer.

## 6. Xử lý DataBuffer đúng vòng đời

### 6.1. Release buffer sau khi copy

Mẫu cơ bản:

~~~java
byte[] copy(DataBuffer buffer) {
    try {
        byte[] bytes = new byte[buffer.readableByteCount()];
        buffer.read(bytes);
        return bytes;
    } finally {
        DataBufferUtils.release(buffer);
    }
}
~~~

Sau khi copy xong, byte[] độc lập với pooled buffer gốc. Khối finally bảo đảm buffer tổng hợp được release ngay cả khi thao tác copy gặp lỗi.

### 6.2. Join lỗi hoặc bị cancel

DataBufferUtils.join có trách nhiệm giải phóng các buffer đã tích lũy khi nguồn phát lỗi hoặc bị hủy theo contract của API. Không tự release từng buffer nguồn trước khi join hoàn tất, vì join đang sở hữu chúng trong quá trình tổng hợp.

Sau khi join thành công, buffer kết quả thuộc trách nhiệm của consumer; hãy release sau khi đọc.

### 6.3. Discard và các operator trung gian

Nếu code tự giữ hoặc loại bỏ DataBuffer qua các operator có discard support, cần xem xét doOnDiscard(DataBuffer.class, DataBufferUtils::release) đúng vị trí. Không thêm doOnDiscard một cách máy móc vào mọi pipeline; phải biết operator nào có thể loại bỏ phần tử và ai đang sở hữu buffer.

### 6.4. Không double-release

Không release buffer đã được consumer khác release. Không release buffer tổng hợp trước khi copy xong. Không giữ buffer pooled trong singleton field để dùng cho request sau.

Khi không chắc quyền sở hữu, hãy đọc contract của API tạo hoặc chuyển giao DataBuffer. Quyền sở hữu và thời điểm release phải rõ ràng.

## 7. Ví dụ filter hoàn chỉnh: cache JSON tối đa 64 KiB

Ví dụ dưới đây chỉ áp dụng cho POST /api/echo với Content-Type application/json. Filter đọc body, xác nhận JSON root là object, sau đó phát lại nội dung để controller vẫn có thể dùng @RequestBody.

Đây là ví dụ cho Spring Boot 3.5.5 và Java 17+. Trong dự án mới, dùng bản Spring Boot đang được tổ chức phê duyệt và còn được duy trì.

### 7.1. Cấu trúc dự án

~~~text
request-body-cache/
├── pom.xml
└── src/
    ├── main/java/example/bodycache/
    │   ├── DemoApplication.java
    │   ├── RequestBodyCacheFilter.java
    │   └── EchoController.java
    └── test/java/example/bodycache/
        └── EchoControllerTest.java
~~~

### 7.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.5</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>request-body-cache</artifactId>
    <version>1.0.0</version>

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

### 7.3. DemoApplication.java

~~~java
package example.bodycache;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 7.4. RequestBodyCacheFilter.java

~~~java
package example.bodycache;

import java.io.IOException;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferLimitException;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.http.server.reactive.ServerHttpRequestDecorator;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class RequestBodyCacheFilter implements WebFilter {

    static final int MAX_BODY_BYTES = 64 * 1024;
    static final String BODY_LENGTH_ATTRIBUTE =
            RequestBodyCacheFilter.class.getName() + ".bodyLength";

    private final ObjectMapper objectMapper;

    public RequestBodyCacheFilter(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        ServerHttpRequest request = exchange.getRequest();
        MediaType contentType = request.getHeaders().getContentType();

        boolean targetRequest =
                HttpMethod.POST.equals(request.getMethod())
                && "/api/echo".equals(request.getURI().getPath())
                && contentType != null
                && MediaType.APPLICATION_JSON.isCompatibleWith(contentType);

        if (!targetRequest) {
            return chain.filter(exchange);
        }

        long contentLength = request.getHeaders().getContentLength();
        if (contentLength > MAX_BODY_BYTES) {
            return payloadTooLarge(exchange);
        }

        Mono<byte[]> cachedBody = DataBufferUtils
                .join(request.getBody(), MAX_BODY_BYTES)
                .map(this::copyAndRelease)
                .defaultIfEmpty(new byte[0])
                .onErrorMap(
                        DataBufferLimitException.class,
                        RequestBodyTooLargeException::new
                );

        return cachedBody
                .flatMap(bytes -> {
                    try {
                        JsonNode json = objectMapper.readTree(bytes);
                        if (json == null || !json.isObject()) {
                            return badRequest(exchange);
                        }
                    } catch (IOException error) {
                        return badRequest(exchange);
                    }

                    ServerHttpRequest decorated =
                            new ServerHttpRequestDecorator(request) {
                        @Override
                        public Flux<DataBuffer> getBody() {
                            return Flux.defer(() -> Flux.just(
                                    exchange.getResponse()
                                            .bufferFactory()
                                            .wrap(bytes)
                            ));
                        }
                    };

                    ServerWebExchange mutated = exchange.mutate()
                            .request(decorated)
                            .build();

                    mutated.getAttributes().put(
                            BODY_LENGTH_ATTRIBUTE,
                            bytes.length
                    );

                    // The filter can inspect the cached bytes here.
                    // The downstream controller still receives a replay.
                    return chain.filter(mutated);
                })
                .onErrorResume(
                        RequestBodyTooLargeException.class,
                        error -> payloadTooLarge(exchange)
                );
    }

    private byte[] copyAndRelease(DataBuffer buffer) {
        try {
            byte[] bytes = new byte[buffer.readableByteCount()];
            buffer.read(bytes);
            return bytes;
        } finally {
            DataBufferUtils.release(buffer);
        }
    }

    private Mono<Void> badRequest(ServerWebExchange exchange) {
        exchange.getResponse().setStatusCode(HttpStatus.BAD_REQUEST);
        return exchange.getResponse().setComplete();
    }

    private Mono<Void> payloadTooLarge(ServerWebExchange exchange) {
        exchange.getResponse().setStatusCode(HttpStatus.PAYLOAD_TOO_LARGE);
        return exchange.getResponse().setComplete();
    }

    private static final class RequestBodyTooLargeException
            extends RuntimeException {
        RequestBodyTooLargeException(Throwable cause) {
            super(cause);
        }
    }
}
~~~

Điểm quan trọng trong code:

- Filter chỉ chạy với đúng method, path và media type đã chọn.
- Content-Length lớn hơn giới hạn bị từ chối sớm.
- Nếu Content-Length không có hoặc không phản ánh đúng kích thước, join vẫn áp dụng MAX_BODY_BYTES.
- DataBufferLimitException từ bước join được đổi thành exception riêng để chỉ nhánh cache body mới chuyển thành HTTP 413.
- JSON được kiểm tra trước khi gọi filter chain.
- joined DataBuffer được copy và release trong finally.
- Decorator dùng Flux.defer để tạo DataBuffer mới ở mỗi subscription.
- byte[] được giữ trong closure của decorator cho đúng request, không nằm trong field dùng chung của singleton filter.

### 7.5. EchoController.java

~~~java
package example.bodycache;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
public class EchoController {

    @PostMapping(
            path = "/api/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<Map<String, Object>> echo(
            @RequestBody Mono<Map<String, Object>> body,
            ServerWebExchange exchange) {

        return body.map(value -> {
            Map<String, Object> response = new LinkedHashMap<>();
            response.put("received", value);
            response.put(
                    "cachedBytes",
                    exchange.getAttributeOrDefault(
                            RequestBodyCacheFilter.BODY_LENGTH_ATTRIBUTE,
                            -1
                    )
            );
            return response;
        });
    }
}
~~~

Controller vẫn dùng @RequestBody như bình thường. Nó không biết filter đã đọc body trước đó; ServerHttpRequestDecorator phát lại các byte đã cache nên codec của controller có thể decode JSON.

### 7.6. Chạy ứng dụng

Tại thư mục có pom.xml:

~~~bash
mvn spring-boot:run
~~~

Gửi JSON nhỏ:

~~~powershell
curl.exe -i -X POST http://localhost:8080/api/echo -H "Content-Type: application/json" -H "Accept: application/json" --data-binary '{"name":"Ada"}'
~~~

Response body minh họa:

~~~json
{
  "received": {
    "name": "Ada"
  },
  "cachedBytes": 14
}
~~~

Số 14 là số byte của chuỗi JSON UTF-8 không có khoảng trắng: {"name":"Ada"}. Controller nhận được JSON dù filter đã đọc và parse body trước đó.

Nếu gửi body vượt 64 KiB, filter trả HTTP **413 Payload Too Large** trước khi controller được gọi. Nếu body không phải JSON object hợp lệ, filter trả HTTP **400 Bad Request**.

## 8. Kiểm thử bằng WebTestClient

Tệp **EchoControllerTest.java**:

~~~java
package example.bodycache;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class EchoControllerTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void filterCanReadBodyAndControllerCanDecodeItAgain() {
        webTestClient.post()
                .uri("/api/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("name", "Ada"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.received.name").isEqualTo("Ada")
                .jsonPath("$.cachedBytes").isNumber();
    }

    @Test
    void rejectsBodyLargerThanConfiguredLimit() {
        byte[] oversized =
                new byte[RequestBodyCacheFilter.MAX_BODY_BYTES + 1];

        webTestClient.post()
                .uri("/api/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue(oversized)
                .exchange()
                .expectStatus()
                .isEqualTo(HttpStatus.PAYLOAD_TOO_LARGE);
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Test đầu tiên xác nhận hai điều trong cùng một request: filter đọc được body và controller vẫn giải mã được body đã replay. Test thứ hai xác nhận body vượt giới hạn bị từ chối.

Đây là integration test với embedded server, không phải test chỉ gọi filter bằng tay. Nó giúp phát hiện lỗi ở ranh giới giữa WebFilter, request decorator, codec và controller.

## 9. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Filter đọc body gốc rồi gọi chain với exchange cũ | Controller phía sau có thể nhận body rỗng | Cache bytes và thay request bằng decorator |
| Subscribe body hai lần và mong dữ liệu tự phát lại | Nguồn network không tự rewind | Chỉ đọc nguồn gốc một lần; chủ động replay |
| Dùng lại cùng DataBuffer cho nhiều subscription | Read position hoặc reference count đã thay đổi | Tạo DataBuffer mới từ byte[] cho mỗi subscription |
| Giữ pooled DataBuffer trong field singleton | Dùng sau release hoặc rò native memory | Copy byte[] và release buffer đúng lúc |
| Gọi DataBufferUtils.join không có giới hạn | Client có thể gửi body rất lớn | Dùng join(publisher, maxByteCount) |
| Chỉ kiểm tra Content-Length | Bỏ lọt body chunked hoặc không có độ dài | Kiểm tra sớm header và luôn giới hạn lúc join |
| Đặt filter sau filter khác đã đọc body | Filter cache nhận body đã tiêu thụ | Sắp xếp filter trước consumer đầu tiên |
| Đặt switchIfEmpty sau chain.filter(...) | Mono<Void> hoàn tất rỗng, có thể gọi chain lần hai | Xử lý empty body trước khi gọi chain hoặc dùng sentinel |
| Cache mọi request toàn cục | Tăng bộ nhớ và latency không cần thiết | Chỉ cache route, method và media type thật sự cần |
| Cache multipart/file upload toàn bộ | Dễ hết heap và phá streaming | Dùng PartEvent/streaming, consume/relay/release đúng cách |
| Ghi log raw request body | Lộ mật khẩu, token, dữ liệu cá nhân | Log metadata đã lọc; chỉ lưu nội dung khi có chính sách rõ |
| Thay body nhưng giữ Content-Length cũ | Client/server đọc sai độ dài | Cập nhật hoặc loại bỏ Content-Length khi body thay đổi |
| Catch DataBufferLimitException quá rộng | Có thể biến lỗi downstream thành lỗi cache body | Đóng phạm vi xử lý lỗi quanh thao tác join |
| Dùng cache byte[] không giới hạn theo concurrency | Nhiều request đồng thời gây áp lực heap | Giới hạn body, concurrency và thời gian giữ cache |

### 9.1. Bẫy switchIfEmpty với Mono<Void>

Đoạn sau có thể gọi filter chain hai lần:

~~~java
return readBody()
        .flatMap(body -> chain.filter(exchange))
        .switchIfEmpty(chain.filter(exchange));
~~~

Lý do: chain.filter trả Mono<Void>. Mono<Void> không phát giá trị onNext; khi hoàn tất bình thường nó vẫn là empty về mặt dữ liệu. Vì thế switchIfEmpty có thể chạy nhánh fallback sau khi chain đầu tiên đã xử lý xong.

Cách an toàn là xử lý trường hợp body rỗng **trước khi** gọi chain:

~~~java
Mono<byte[]> bytes = readBody()
        .defaultIfEmpty(new byte[0]);

return bytes.flatMap(body -> {
    ServerWebExchange replayed = decorate(exchange, body);
    return chain.filter(replayed);
});
~~~

Hoặc nếu cần phân nhánh empty/non-empty, hãy chuyển kết quả đọc thành một kiểu có giá trị phân biệt trước khi flatMap sang Mono<Void>. Không đặt switchIfEmpty trực tiếp sau chain.filter nếu mục tiêu là fallback cho body rỗng.

## 10. Khi nào nên dùng exchange attributes thay cho replay?

Nếu filter chỉ cần phân tích một lần và handler phía sau không cần đọc body gốc, không cần tạo request decorator.

Ví dụ:

1. Filter đọc body một lần.
2. Decode thành JsonNode hoặc một DTO nhỏ.
3. Kiểm tra policy.
4. Lưu kết quả đã xác thực vào exchange attributes.
5. Handler đọc DTO/metadata từ exchange thay vì parse lại body.

Cách này tránh một lần decode và không cần phát lại byte. Tuy nhiên, nó yêu cầu downstream được thiết kế để nhận dữ liệu đã phân tích; controller có @RequestBody vẫn cần body.

| Tình huống | Lựa chọn |
| --- | --- |
| Filter xác thực chữ ký rồi controller vẫn cần @RequestBody | Cache bytes và replay |
| Filter parse body, handler dùng luôn DTO đã parse | Lưu DTO/metadata trong exchange attributes |
| Handler là functional endpoint và có thể nhận ServerRequest đã xử lý | Thiết kế handler đọc metadata/context đã chuẩn bị |
| Body lớn hoặc stream vô hạn | Không cache toàn bộ; xử lý streaming |
| Chỉ cần kiểm tra header hoặc content type | Không đọc body trong filter |

Không lưu raw body vào singleton field. Exchange attributes có phạm vi request, còn field của filter bean thường được chia sẻ giữa nhiều request đồng thời.

## 11. Multipart và streaming: không gom toàn bộ body

Với upload file hoặc multipart, body có thể rất lớn. Không nên gọi join để gom toàn bộ vào một byte[] chỉ nhằm đọc lại.

Spring WebFlux cung cấp cách xử lý multipart theo từng PartEvent:

~~~java
request.bodyToFlux(PartEvent.class)
        .windowUntil(PartEvent::isLast)
        .concatMap(partEvents ->
                partEvents.switchOnFirst((signal, events) -> {
                    if (!signal.hasValue()) {
                        return events.then();
                    }

                    PartEvent event = signal.get();

                    if (event instanceof FormPartEvent form) {
                        processField(form.name(), form.value());
                        return events.then();
                    }

                    if (event instanceof FilePartEvent file) {
                        return events
                                .map(PartEvent::content)
                                .concatMap(this::writeChunk);
                    }

                    return Mono.error(
                            new IllegalStateException("Unsupported part")
                    );
                })
        );
~~~

Đây là đoạn minh họa về streaming, cần các phương thức processField và writeChunk của ứng dụng. Với từng PartEvent, nội dung DataBuffer phải được **consume, relay hoặc release hoàn toàn**. Không bỏ qua buffer của file nếu không muốn rò tài nguyên.

Nếu filter chỉ cần kiểm tra tên file, content type hoặc metadata multipart, cân nhắc xử lý event theo luồng và truyền metadata cần thiết. Tránh cache file upload toàn bộ chỉ để downstream đọc lại.

## 12. Filter order và phối hợp với Spring Security

Một filter body-cache phải chạy **trước mọi filter khác có thể tiêu thụ request body**. Ví dụ:

~~~java
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
class RequestBodyCacheFilter implements WebFilter {
    // ...
}
~~~

Đây là gợi ý thứ tự, không thay thế việc xem thứ tự filter thực tế của ứng dụng. Nếu Spring Security, gateway filter hoặc filter tùy chỉnh đọc body trước, cache filter đặt sau sẽ không còn nhận được body ban đầu.

Không nên cache toàn bộ request cho mục đích logging nếu không có nhu cầu nghiệp vụ. Filter bảo mật nên tránh log mật khẩu, access token, refresh token, thông tin thanh toán hoặc dữ liệu cá nhân. Nếu cần audit, lưu metadata đã lọc, mã request hoặc kết quả xác thực; không mặc định lưu payload thô.

## 13. Giới hạn và thay đổi body

Trong ví dụ, byte[] được replay nguyên vẹn nên Content-Length ban đầu vẫn đúng. Nếu filter biến đổi nội dung:

- Cập nhật Content-Length theo số byte mới, hoặc bỏ header để runtime tự xử lý theo cơ chế phù hợp.
- Đảm bảo Content-Type phản ánh body sau biến đổi.
- Không giữ Transfer-Encoding hoặc Content-Encoding cũ nếu nội dung đã thay đổi mà semantics không còn đúng.
- Nếu ký số hoặc xác thực chữ ký, xác định rõ byte representation nào được ký: raw bytes, canonical JSON hay nội dung sau giải nén.
- Không decode thành String rồi encode lại nếu chữ ký phụ thuộc byte chính xác, vì encoding, whitespace hoặc thứ tự field có thể khác.

Cache/replay chỉ giải quyết việc downstream nhận lại byte. Nó không tự đảm bảo nội dung đã được canonicalize, validate hay an toàn về nghiệp vụ.

## 14. Kiểm thử và quan sát trong production

### 14.1. Những trường hợp cần test

- Body JSON nhỏ: filter đọc được và controller vẫn decode được.
- Body rỗng: xử lý theo hợp đồng endpoint, không gọi chain hai lần.
- JSON sai cú pháp: trả lỗi phù hợp trước khi controller xử lý.
- Body vượt giới hạn với Content-Length đã biết.
- Body vượt giới hạn nhưng gửi theo chunked/không biết trước độ dài.
- Request method/path/content type không nằm trong phạm vi cache: filter bỏ qua.
- Downstream subscribe body theo cách cần thiết: mỗi subscription nhận buffer mới.
- Cancellation hoặc lỗi trong lúc join: buffer tích lũy được release đúng contract.
- Multipart/upload: không gom toàn bộ file vào memory.
- Nhiều request đồng thời: heap và pooled memory vẫn nằm trong giới hạn.

### 14.2. Metric nên theo dõi

- Số request được cache và số request bị bỏ qua.
- Số body bị từ chối vì vượt giới hạn.
- Kích thước body trung bình và phân vị cao.
- Thời gian filter join/parse.
- Số request đang giữ byte[] cache đồng thời.
- Heap usage, GC pause và Netty pooled buffer leak warning.
- Tỷ lệ lỗi decode, 400, 413 và cancellation.

Không dùng raw body, user ID hoặc token làm metric label có cardinality cao hoặc làm dữ liệu log.

## 15. Ghi nhớ

- Request body HTTP là một luồng; hãy coi nguồn body gốc là one-shot.
- Filter đọc body trước controller sẽ tiêu thụ dữ liệu mà controller có thể cần.
- Muốn downstream đọc lại, cache có giới hạn rồi dùng ServerHttpRequestDecorator.
- Dùng DataBufferUtils.join với maxByteCount; Content-Length chỉ là kiểm tra sớm.
- Copy dữ liệu sang byte[] rồi release DataBuffer tổng hợp trong finally.
- Tạo DataBuffer mới cho mỗi subscription bằng DataBufferFactory.wrap(bytes) trong Flux.defer.
- Không replay cùng một pooled DataBuffer đã bị đọc hoặc release.
- Xử lý DataBufferLimitException có phạm vi để trả 413 rõ ràng.
- Đặt filter trước mọi consumer body khác và chỉ cache route cần thiết.
- Multipart và streaming nên xử lý từng phần; consume, relay hoặc release mọi DataBuffer.
- Nếu downstream có thể dùng kết quả đã parse trong exchange attributes, không cần replay body.
- Test cả body nhỏ, body rỗng, body quá lớn, lỗi parse và cancellation.

**Tài liệu chính thức:**
- [Spring Framework — Data Buffers and Codecs: pooled buffers, release và DataBufferUtils.join](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html)
- [Spring Framework — WebFlux Functional Endpoints: request body streams và PartEvent](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html)
- [Spring Framework — @RequestBody in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestbody.html)
- [Spring Framework Javadoc — DataBufferUtils](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html)
- [Spring Framework Javadoc — ServerHttpRequestDecorator](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/ServerHttpRequestDecorator.html)
- [Spring Framework Javadoc — WebFilter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebFilter.html)
- [Spring Framework Javadoc — ServerWebExchange.Builder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/ServerWebExchange.Builder.html)
