# Giới hạn dữ liệu được gom trong bộ nhớ khi đọc nội dung – Spring WebFlux

## 1. Mục tiêu học tập

Spring WebFlux nhận HTTP body thành một luồng dữ liệu thay vì buộc tải toàn bộ vào RAM ngay lập tức. Tuy nhiên, khi codec chuyển một luồng byte thành **một String, byte[], DTO JSON, form data hoặc một object khác**, nó có thể cần **gom (aggregate/buffer)** nhiều DataBuffer. Nếu không giới hạn, chỉ một payload lớn hoặc nhiều request đồng thời cũng có thể gây áp lực heap, direct memory, garbage collection và độ trễ.

Spring Framework cung cấp **maxInMemorySize** cho các codec cần buffer. Spring Boot 3.5 cung cấp property **spring.http.codecs.max-in-memory-size** để cấu hình giới hạn này cho WebFlux server và các WebClient do Boot tự cấu hình.

Sau bài này, bạn có thể:

1. Phân biệt byte stream, DataBuffer, Decoder, HttpMessageReader, aggregation và streaming.
2. Hiểu phạm vi thực sự của giới hạn **maxInMemorySize** và lỗi **DataBufferLimitException**.
3. Cấu hình Spring Boot 3.5 bằng YAML, Java **WebFluxConfigurer** và cấu hình **WebClient** riêng.
4. Phân biệt giới hạn bộ đệm codec, giới hạn tổng HTTP request, multipart disk usage và giới hạn tải đồng thời.
5. Chạy demo Java 17 / Spring Boot 3.5 để kiểm tra JSON lớn, JSON nhỏ và NDJSON streaming.
6. Chọn chiến lược xử lý file, streaming và DataBuffer không gây tích lũy RAM ngoài ý muốn.

Bài thuộc nhóm **Tùy chỉnh WebFlux**; không áp dụng nguyên xi các property Servlet như **spring.servlet.multipart.max-file-size** cho WebFlux/Reactor Netty.

## 2. Vì sao reactive không có nghĩa là không dùng bộ nhớ?

Sơ đồ tổng quan:

~~~mermaid
flowchart TD
    A[HTTP network chunks] --> B[Flux DataBuffer]
    B --> C{Ứng dụng / codec cần dạng nào?}
    C -->|Một object / String / byte array| D[Aggregation]
    D --> E[maxInMemorySize]
    E --> F[Giải mã DTO hoặc DataBufferLimitException]
    C -->|Các phần tử độc lập| G[Streaming decoder]
    G --> H[Decode từng item có thể có buffer riêng]
    H --> I[Flux xử lý từng phần]
~~~

**DataBuffer** là abstraction cho vùng byte, có thể được cấp phát từ pooled/direct memory tùy server. **Mono** biểu diễn tối đa một kết quả, **Flux** biểu diễn nhiều kết quả. Nhưng điều này **không** bảo đảm Mono luôn buffer hoặc Flux luôn stream không giới hạn: cần xét codec và kiểu dữ liệu thực tế.

Ví dụ:

- **@RequestBody Mono<MyDto>**: thường cần giải mã một JSON object hoàn chỉnh và có thể buffer.
- **@RequestBody Mono<String>**: thường phải gom body text thành một String.
- **WebClient.bodyToMono(byte[].class)**: thường phải gom response thành một mảng byte.
- **Flux<Event>** với NDJSON: có thể đọc từng JSON object, nhưng codec vẫn có thể cần buffer để hoàn tất **một record**.
- **Flux<DataBuffer>**: cho phép thao tác theo chunk, nhưng nếu code gọi **collectList()**, **DataBufferUtils.join()** hoặc tự ghép byte[] thì vẫn có aggregation.

**Backpressure** giúp điều tiết tốc độ tiêu thụ dữ liệu giữa các publisher/subscriber phù hợp; nó không thay thế giới hạn tổng payload hay giới hạn đối tượng đang tích lũy.

## 3. maxInMemorySize giới hạn điều gì?

Một số codec của WebFlux cần giữ một phần hoặc toàn bộ input trong memory để tạo đầu ra. **maxInMemorySize** đặt giới hạn byte được buffer cho thao tác decode tương ứng.

Các trường hợp cụ thể:

| Kiểu đọc | Cách buffer | Ý nghĩa ngưỡng |
|---|---|---|
| **Mono<String>** | Gom text thành một giá trị | Có thể bị từ chối khi vượt giới hạn |
| **Mono<byte[]>** | Gom byte thành một mảng | Ngưỡng áp dụng với việc tích lũy này |
| **Mono<MyDto>** từ JSON | Decoder phải xử lý JSON object | Object lớn có thể vượt ngưỡng |
| Form **application/x-www-form-urlencoded** | Thường cần parse và tập hợp form | Codec có thể ràng buộc lượng dữ liệu |
| **Flux<Event>** từ NDJSON | Tách từng record rồi decode | Thường áp dụng cho **mỗi record** |
| Flux dòng văn bản | Giữ đến ranh giới một dòng | Dòng quá dài vẫn có thể vượt ngưỡng |
| **Flux<DataBuffer>** thô | Không nhất thiết gom thành object | Không xem limit là tổng byte stream |
| Multipart | Parser có threshold RAM/disk riêng | Không coi limit bộ nhớ là file-size limit |

### 3.1. Giá trị mặc định thường gặp

Nếu không đặt giới hạn chung, từng codec sử dụng cấu hình mặc định. Theo tài liệu Spring Framework và Spring Boot 3.5, **đa số codec mặc định giới hạn khoảng 256 KiB**, tương đương **262.144 byte**.

Đây là **byte**, không phải 262.144 ký tự. Chuỗi UTF-8 có ký tự tiếng Việt hoặc emoji có thể cần nhiều byte hơn số ký tự thấy được.

Lỗi thường gặp khi codec buffer quá mức:

~~~text
org.springframework.core.io.buffer.DataBufferLimitException:
Exceeded limit on max bytes to buffer
~~~

Thông điệp thực tế có thể kèm giá trị ngưỡng, tùy phiên bản. Exception này báo việc **codec aggregation vượt ngưỡng**, không nhất thiết JVM đã gặp OutOfMemoryError.

### 3.2. Điều giới hạn này không làm được

**maxInMemorySize không phải là:**

- Giới hạn tổng byte của mọi HTTP request: một NDJSON stream có nhiều record nhỏ vẫn có thể lớn hơn ngưỡng mà được xử lý tuần tự.
- Giới hạn tổng bộ nhớ heap/direct memory của tiến trình; nhiều request vẫn có thể đồng thời buffer.
- Giới hạn số request đồng thời, số record trong Flux, tốc độ truyền hay thời gian của request.
- Giới hạn mặc định cho mọi file upload; multipart có cơ chế spool xuống disk.
- Lớp bảo vệ duy nhất chống DoS; vẫn cần giới hạn kết nối, tốc độ, timeout, disk quota, body size và xác thực.
- Giới hạn của các toán tử tích lũy do người viết code tạo ngoài codec, chẳng hạn **collectList()** không giới hạn.

Nguyên tắc quan trọng: **giới hạn codec theo nhu cầu dữ liệu hợp lệ, đồng thời đặt giới hạn tổng request ở tầng thích hợp**.

## 4. Cấu hình đúng cho Spring Boot 3.5

Trong file **src/main/resources/application.yml**, đặt:

~~~yaml
spring:
  http:
    codecs:
      max-in-memory-size: 512KB
~~~

Boot chuyển giá trị kích thước dữ liệu thành số byte thích hợp cho các codec được tự cấu hình. **512KB** trong cú pháp DataSize của Spring Boot tương ứng **512 × 1024 byte**.

Nếu endpoint chỉ cần payload nhỏ, ví dụ giới hạn 128 KiB:

~~~yaml
spring:
  http:
    codecs:
      max-in-memory-size: 128KB
~~~

Hãy đánh giá payload thực tế, số client đồng thời và giới hạn của downstream trước khi nâng hoặc hạ.

### 4.1. Chú ý thay đổi tên property theo phiên bản

| Phiên bản | Property |
|---|---|
| **Spring Boot 3.4.x và tài liệu cũ** | **spring.codec.max-in-memory-size** |
| **Spring Boot 3.5.x** | **spring.http.codecs.max-in-memory-size** |
| **Spring Boot 4.x** | Kiểm tra đúng tài liệu nhánh đang chạy; nhóm thuộc tính mới là **spring.http.codecs** |

Spring Boot 3.5 đã chuyển tên cũ sang trạng thái deprecated. **Đừng sao chép YAML từ blog cũ** mà không kiểm tra phiên bản: nếu property không được áp dụng, bạn có thể vẫn gặp lỗi ở mức giới hạn mặc định.

Đường dẫn tài liệu chính thức: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/

### 4.2. Cấu hình bằng WebFluxConfigurer

Khi cần cấu hình trực tiếp ở Spring Framework, ví dụ:

~~~java
package com.example.bufferlimit;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration
public class CodecConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(ServerCodecConfigurer configurer) {
        configurer.defaultCodecs().maxInMemorySize(512 * 1024);
    }
}
~~~

Phương thức **configureHttpMessageCodecs** được dùng để tùy chỉnh codec của server WebFlux. Ví dụ này đặt giới hạn 512 KiB cho các default codecs.

**Chọn một chính sách rõ ràng**: khi đã có property và class cấu hình cùng tác động đến một codec, kiểm tra hiệu lực cuối cùng theo phiên bản, tránh khai báo hai giá trị mâu thuẫn.

### 4.3. Server và WebClient là hai hướng khác nhau

Property của Spring Boot 3.5 áp dụng cho **WebFlux server được auto-configure** và **WebClient instance được Boot tự cấu hình**. Tuy nhiên một đối tượng được tạo bằng **WebClient.builder()** thủ công hoặc custom ExchangeStrategies **không tự bảo đảm kế thừa** mọi thiết lập từ Boot.

Ví dụ thiết lập riêng cho một client:

~~~java
import org.springframework.web.reactive.function.client.WebClient;

WebClient client = WebClient.builder()
        .baseUrl("https://example.org")
        .codecs(codecs -> codecs.defaultCodecs()
                .maxInMemorySize(2 * 1024 * 1024))
        .build();
~~~

Đoạn trên là **minh họa trong một class ứng dụng** có dependency WebFlux, không phải chương trình độc lập.

Phân biệt:

- **Inbound request body**: server WebFlux đọc dữ liệu từ client.
- **Outbound HTTP call response**: WebClient đọc dữ liệu của dịch vụ khác.
- Nếu dùng cả hai, phải kiểm tra **hai codec context**, kể cả khi cùng nhận property qua Boot auto-configuration.

## 5. DataBufferLimitException và HTTP response

Giới hạn bộ đệm chủ yếu nhằm **bảo vệ tài nguyên**. Khi vượt ngưỡng, codec có thể ném **DataBufferLimitException**.

### 5.1. Vì sao không mặc định mọi lỗi là HTTP 413?

**HTTP 413 Content Too Large** là status có ý nghĩa khi yêu cầu vượt giới hạn chấp nhận. Tuy nhiên, Spring WebFlux không bảo đảm một DataBufferLimitException luôn được tự động chuyển thành 413 trong **mọi phiên bản, mọi reader và mọi đường đi exception**. Khi không có mapping phù hợp, default error response có thể khác.

Nếu muốn có error contract ổn định ở ứng dụng, hãy xử lý lỗi tại ranh giới phù hợp. Một ví dụ đơn giản cho trường hợp exception đến được controller advice:

~~~java
package com.example.bufferlimit;

import java.util.Map;
import org.springframework.core.io.buffer.DataBufferLimitException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class BufferLimitAdvice {

    @ExceptionHandler(DataBufferLimitException.class)
    public ResponseEntity<Map<String, String>> tooLarge(
            DataBufferLimitException ex) {
        return ResponseEntity.status(HttpStatus.PAYLOAD_TOO_LARGE)
                .body(Map.of(
                        "code", "DECODE_BUFFER_LIMIT",
                        "message", "Request content exceeds the decode limit"));
    }
}
~~~

Nếu lỗi đi qua advice này, kết quả là **HTTP 413** và JSON gồm **code=DECODE_BUFFER_LIMIT**. Nhưng nếu lỗi phát sinh trước Spring, sau khi response đã commit, hoặc được bọc bởi loại exception khác, advice có thể không xử lý được. Cần kiểm thử HTTP thực tế.

**Không** dùng cách chữa lỗi bằng việc bắt exception rồi đọc lại toàn bộ HTTP body vào một mảng byte lớn: body là stream có thể đã bị tiêu thụ một phần và làm như vậy phá hỏng mục tiêu giới hạn RAM.

### 5.2. Chẩn đoán theo ranh giới

1. Lỗi nằm ở **server** khi nhận request hay **WebClient** khi đọc response?
2. Endpoint đọc một object đầy đủ hay stream từng record?
3. Có custom decoder khác hoặc operator **collectList()** không?
4. Property đã được bind đúng tên và đúng profile chưa?
5. Proxy có trả lỗi 413 từ trước khi request đến ứng dụng không?
6. Có thể đổi API sang streaming hoặc upload tách phần thay vì tăng limit không?

## 6. Ví dụ Spring Boot 3.5/Java 17 chạy được

Tạo một ứng dụng WebFlux với hai endpoint:

- **POST /api/echo**: nhận một JSON object và trả số UTF-16 code units của trường text.
- **POST /api/events**: nhận NDJSON gồm nhiều record và đếm số record theo luồng.

### 6.1. Cấu trúc dự án

~~~text
buffer-limit-demo/
├── pom.xml
├── BodyGenerator.java
└── src/main/
    ├── java/com/example/bufferlimit/
    │   ├── BufferLimitApplication.java
    │   ├── PayloadController.java
    │   └── BufferLimitAdvice.java
    └── resources/
        └── application.yml
~~~

### 6.2. pom.xml

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
    <artifactId>buffer-limit-demo</artifactId>
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

**Không thêm spring-boot-starter-web** vào demo này: khi MVC và WebFlux cùng tồn tại, Boot thường ưu tiên MVC và kết quả kiểm thử sẽ không còn đúng cùng stack.

### 6.3. BufferLimitApplication.java

~~~java
package com.example.bufferlimit;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BufferLimitApplication {
    public static void main(String[] args) {
        SpringApplication.run(BufferLimitApplication.class, args);
    }
}
~~~

### 6.4. PayloadController.java

~~~java
package com.example.bufferlimit;

import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class PayloadController {

    @PostMapping(
            path = "/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Summary> echo(@RequestBody Mono<Payload> input) {
        return input.map(p ->
                new Summary(p.text() == null ? 0 : p.text().length()));
    }

    @PostMapping(
            path = "/events",
            consumes = "application/x-ndjson",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Map<String, Long>> events(
            @RequestBody Flux<Event> events) {
        return events.count()
                .map(count -> Map.of("processed", count));
    }

    public record Payload(String text) {}
    public record Summary(int chars) {}
    public record Event(String id, String value) {}
}
~~~

Với **/api/echo**, JSON lớn được giải mã thành một **Payload**. Với **/api/events**, decoder có thể tạo từng Event từ NDJSON; **count()** không giữ toàn bộ event trong một List. Tuy nhiên endpoint này chưa giới hạn **tổng số event**, cần bổ sung khi triển khai thật.

### 6.5. BufferLimitAdvice.java

Dùng nguyên class **BufferLimitAdvice** ở mục 5.1. File ở cùng package với class main nên được component scan tìm thấy.

### 6.6. application.yml

~~~yaml
server:
  port: 8080

spring:
  http:
    codecs:
      max-in-memory-size: 128KB
~~~

Giới hạn 128 KiB chọn cho mục đích học và tái hiện lỗi; đây không phải mức khuyến nghị cho mọi ứng dụng.

Chạy:

~~~bash
mvn spring-boot:run
~~~

Gửi request nhỏ:

~~~bash
curl -i \
  -H "Content-Type: application/json" \
  --data-binary '{"text":"xin chào"}' \
  "http://localhost:8080/api/echo"
~~~

Với một payload UTF-8 hợp lệ, mong đợi HTTP 200 với body:

~~~json
{"chars":8}
~~~

Số 8 là số UTF-16 code units của **xin chào** (3 + 1 dấu cách + 4), không phải kích thước byte HTTP.

### 6.7. Sinh một JSON document lớn bằng Java 17

Tạo file **BodyGenerator.java** ở thư mục gốc, độc lập với Spring dependencies:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class BodyGenerator {
    public static void main(String[] args) throws Exception {
        int length = Integer.parseInt(args[0]);
        String json = "{\"text\":\"" + "a".repeat(length) + "\"}";
        Path output = Path.of("body.json");
        Files.writeString(output, json, StandardCharsets.UTF_8);
        System.out.println(Files.size(output));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 BodyGenerator.java
java BodyGenerator 200000
~~~

Stdout chính xác:

~~~text
200011
~~~

File body.json gồm **200.011 byte** (200.000 byte ký tự a và 11 byte dấu ngoặc/nháy/field name), lớn hơn **128 KiB = 131.072 byte**.

Gửi:

~~~bash
curl -i \
  -H "Content-Type: application/json" \
  --data-binary @body.json \
  "http://localhost:8080/api/echo"
~~~

Trong demo, **không mong đợi một kết quả Summary 200 bình thường** khi codec không thể giải mã một object vượt buffer limit. Nếu DataBufferLimitException được chuyển qua **BufferLimitAdvice**, kết quả là HTTP 413 và JSON lỗi có **code=DECODE_BUFFER_LIMIT**. Nếu kết quả khác, phải đọc log và xác nhận exception thực tế, không mặc định mọi vượt ngưỡng đều trả 413.

Kiểm thử payload nhỏ:

~~~bash
java BodyGenerator 1000
~~~

Stdout:

~~~text
1011
~~~

Gửi lại body.json: mong đợi HTTP 200 với:

~~~json
{"chars":1000}
~~~

Dùng chuỗi ASCII ở ví dụ này để cách tính số byte chính xác; với tiếng Việt và emoji, số byte UTF-8 khác số UTF-16 code units.

### 6.8. Test NDJSON streaming

Tạo file **events.ndjson**, lưu UTF-8:

~~~json
{"id":"1","value":"a"}
{"id":"2","value":"b"}
{"id":"3","value":"c"}
~~~

Gọi:

~~~bash
curl -i \
  -H "Content-Type: application/x-ndjson" \
  --data-binary @events.ndjson \
  "http://localhost:8080/api/events"
~~~

Response body mong đợi:

~~~json
{"processed":3}
~~~

**Điểm mấu chốt:** trong streaming NDJSON, nhiều record có thể tạo tổng body lớn, nhưng codec chỉ cần giữ từng record thích hợp. Một record đơn lẻ khổng lồ vẫn có thể vượt maxInMemorySize. **Không** chuyển sang collectList() chỉ để dễ lập trình nếu số record có thể không giới hạn.

Các lệnh curl nhiều dòng dùng shell Bash. Trên Windows PowerShell, dùng **curl.exe** với cú pháp thích hợp; có thể gửi payload từ file UTF-8 để tránh vấn đề escape.

## 7. Giới hạn khi dùng WebClient

WebClient gặp cùng vấn đề trong chiều **đọc HTTP response**:

~~~java
Mono<String> result = client.get()
        .uri("/reports/latest")
        .retrieve()
        .bodyToMono(String.class);
~~~

Nếu response là văn bản lớn, **bodyToMono(String.class)** có thể phải gom byte thành String, gây DataBufferLimitException trên **client side**. Không nên sửa giới hạn server inbound để giải quyết một WebClient được xây thủ công.

Chiến lược phù hợp:

- Nếu API trả một object JSON hợp lệ nhưng lớn, đặt limit riêng cho client sau khi tính memory budget.
- Nếu API có NDJSON/SSE, dùng Flux và xử lý từng phần tử; chú ý mỗi record vẫn có limit riêng.
- Nếu tải file lớn, streaming xuống disk/storage thay vì bodyToMono(byte[].class).
- Đặt timeout, retry có kiểm soát và giới hạn số response concurrent. Một WebClient đọc nhiều response 2 MiB đồng thời vẫn có thể làm tăng memory đáng kể.

## 8. Multipart: giới hạn memory không phải giới hạn dung lượng file

Với **multipart/form-data**, Spring WebFlux còn có nhóm property riêng. Ví dụ trên Spring Boot 3.5:

~~~yaml
spring:
  webflux:
    multipart:
      max-in-memory-size: 256KB
      max-disk-usage-per-part: 20MB
      max-parts: 5
~~~

| Property | Mục đích |
|---|---|
| **spring.webflux.multipart.max-in-memory-size** | Với non-file part là limit bộ nhớ; với file part là ngưỡng có thể chuyển lưu xuống disk |
| **spring.webflux.multipart.max-disk-usage-per-part** | Giới hạn disk usage của mỗi part khi parser viết ra disk |
| **spring.webflux.multipart.max-parts** | Giới hạn số part được gửi trong một request |
| **spring.webflux.multipart.max-headers-size** | Giới hạn dữ liệu header của mỗi part |
| **spring.webflux.multipart.file-storage-directory** | Nơi chứa file multipart tạm trong chế độ phù hợp |

Không đồng nhất **max-in-memory-size: 256KB** với “file upload tối đa 256 KB”. File part lớn có thể chuyển sang disk; cần quota, tổng file size, số part, timeout, storage lifecycle và giới hạn tại proxy/ingress.

Để xử lý file trong reactive controller, **FilePart.transferTo(Path)** phù hợp hơn việc cố giải mã toàn bộ file thành byte[] hoặc String.

Ví dụ **đoạn mã đặt trong controller**, không phải class độc lập:

~~~java
@PostMapping(path = "/upload",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public Mono<String> upload(@RequestPart("file") FilePart file) {
    Path target = Path.of("/srv/uploads")
            .resolve(UUID.randomUUID() + ".bin");
    return file.transferTo(target).thenReturn("uploaded");
}
~~~

Cần các import tương ứng **Path, UUID, MediaType, FilePart, PostMapping, RequestPart, Mono**, thư mục storage tồn tại và quyền ghi hợp lệ. Không dùng tên file do client gửi để ghép thẳng vào đường dẫn. **transferTo** không tự đảm bảo tổng upload được giới hạn hoặc file không độc hại.

### 8.1. Dùng PartEvent khi cần streaming multipart

Spring WebFlux hỗ trợ **PartEvent** để xử lý một số luồng multipart theo streaming. Khi dùng chế độ này, cơ chế lưu tạm file/giới hạn memory theo parser thông thường có thể khác; cần cấu hình và kiểm thử đúng loại HTTP message reader. Hãy đọc Spring Framework docs về multipart và DataBuffer trước khi tự xây pipeline file lớn.

## 9. Quản lý DataBuffer và tránh rò rỉ direct memory

Trên server dùng Netty, DataBuffer có thể dùng pooled/reference-counted memory. Khi làm việc ở mức DTO, codec thường quản lý vòng đời buffer. Khi xử lý trực tiếp **Flux<DataBuffer>**, cần biết bên nào **sở hữu** buffer và trách nhiệm giải phóng.

Các quy tắc:

1. Không giữ một DataBuffer sau khi nó đã bị release.
2. Không release hai lần, cũng không quên release khi code của bạn là bên tiêu thụ.
3. Không gọi **DataBufferUtils.join(...)** cho một nguồn dữ liệu không giới hạn.
4. Không thu cả Flux buffer vào **collectList()** mà không có hạn mức và chiến lược dọn tài nguyên.
5. Khi pipeline cancel/error, bảo đảm buffer bị discard/release đúng theo hợp đồng API.
6. Ưu tiên các API streaming-to-disk và codec/utility của Spring đã xử lý tài nguyên đúng cách.

Một ví dụ minh họa ở mức operator:

~~~java
Flux<Integer> sizes = input.map(buffer -> {
    try {
        return buffer.readableByteCount();
    } finally {
        DataBufferUtils.release(buffer);
    }
});
~~~

**Đây không phải chương trình độc lập**: biến input phải là Flux<DataBuffer> mà code của bạn thực sự sở hữu. Chỉ release khi đoạn code đã hoàn tất xử lý buffer và không chuyển quyền sở hữu cho downstream. Kiểm tra thêm trường hợp cancellation và pooled buffer trong ứng dụng thật.

## 10. Ngân sách bộ nhớ và tải đồng thời

Giả sử đặt codec buffer limit **2 MiB** và có **200 request đồng thời** cần giải mã object gần giới hạn. Dữ liệu aggregation riêng đã có thể tương đương:

~~~text
200 × 2 MiB = 400 MiB
~~~

Con số trên chỉ minh họa, **không phải trần RAM của ứng dụng**. Còn có object Java đã decode, String copies, temporary buffers, Netty direct memory, cache, log, xử lý nghiệp vụ và response.

Khi thay đổi limit, hãy đo:

- Kích thước payload hợp lệ ở p50/p95/p99 và lớn nhất thực tế.
- Số request đồng thời và thời gian tồn tại của mỗi aggregation.
- Heap, off-heap/direct memory, garbage collection, event loop latency.
- Số lỗi DataBufferLimitException và tỉ lệ HTTP 4xx/5xx.
- Khả năng streaming dữ liệu thay vì đưa tất cả vào DTO hoặc collection.
- Giới hạn tải ở gateway, thời gian chờ, số file/part và disk quota.

Một cấu hình tăng limit có thể chạy ổn với một request test nhưng thất bại khi hàng trăm client gửi payload lớn cùng lúc.

## 11. Các lỗi cấu hình và cách khắc phục

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Vẫn thấy ngưỡng 256 KiB dù đã cấu hình | Dùng tên property cũ hoặc profile sai | Boot 3.5: kiểm tra **spring.http.codecs.max-in-memory-size** |
| Server nhận JSON lớn bị lỗi | Mono DTO/String cần buffer vượt limit | Chọn ngưỡng hợp lý hoặc đổi sang streaming |
| WebClient bodyToMono lỗi, server bình thường | Client dùng codec/config riêng | Cấu hình WebClient.Builder đúng nơi |
| NDJSON nhiều record nhỏ vẫn xử lý được | Limit áp dụng theo từng record | Không coi limit là tổng request-size cap |
| Một dòng NDJSON quá dài bị lỗi | Buffer per-record vượt ngưỡng | Giới hạn từng record hoặc đổi dữ liệu |
| Multipart file 1MB vượt threshold 256KB nhưng không lỗi | Threshold có thể chuyển file xuống disk | Đặt giới hạn disk/total upload riêng |
| HTTP status trả 500 thay vì 413 | Exception chưa được map ở đường đi tương ứng | Có policy xử lý lỗi và integration test |
| Nhiều request lớn gây OOM | Concurrency cao và nhiều allocations | Giảm limit, concurrency hoặc đổi streaming |
| API dùng Flux nhưng memory vẫn tăng | collectList/join hoặc cache giữ tất cả | Tránh aggregation vô hạn |
| FilePart được lưu với tên gốc nguy hiểm | Ghép path từ filename người dùng | Tạo ID server-side và sanitize metadata |
| Không hết heap nhưng direct memory tăng | Pooled DataBuffer bị giữ/leak | Kiểm tra ownership/release/cancel |
| Chỉ dựa Content-Length để hạn chế body | Client có thể dùng streaming/chunked | Enforce actual bytes ở proxy/app |

### 11.1. Ma trận kiểm thử nên có

- JSON 1 KiB, JSON gần 128 KiB, JSON 200 KiB khi server limit là 128 KiB.
- Input Unicode/emoji để xác minh **byte size** khác String.length().
- NDJSON nhiều record nhỏ và một record quá lớn.
- Multipart 1 file nhỏ, 1 file vượt memory threshold và trường hợp vượt disk usage cap.
- WebClient response nhỏ/lớn với client tự cấu hình và client do Boot inject.
- Nhiều client đồng thời, request bị cancel, timeout và client disconnect.
- Request không có Content-Length hoặc đi qua gateway, xác định lớp nào trả lỗi.
- Không chỉ kiểm tra response code; theo dõi heap/direct memory và cleanup file.

## 12. Checklist production

- [ ] Biết phiên bản Boot/WebFlux và loại HTTP server đang chạy.
- [ ] Dùng property đúng: **spring.http.codecs.max-in-memory-size** cho Boot 3.5.
- [ ] Hiểu giới hạn của **codec aggregation** không phải giới hạn toàn request.
- [ ] Chọn ngưỡng từ payload hợp lệ và concurrency thực tế, không tăng mù quáng.
- [ ] Dùng streaming cho danh sách lớn, NDJSON, file hoặc nguồn có thể dài vô hạn.
- [ ] Không vô hiệu hóa limit bằng **maxInMemorySize(-1)** nếu không có cơ sở an toàn.
- [ ] Giới hạn tổng request, timeout, rate, concurrent requests và disk quota ở tầng phù hợp.
- [ ] Kiểm tra multipart part limit, file threshold, disk usage và thư mục tạm.
- [ ] Đặt WebClient codec limit riêng nếu client không do Boot auto-configure.
- [ ] Đảm bảo DataBuffer được release đúng quyền sở hữu và trường hợp cancel.
- [ ] Kiểm thử thực tế DataBufferLimitException và status/error contract.
- [ ] Quan sát log, metrics, heap, direct memory và sự cố dưới tải.

## 13. Tài liệu tham khảo chính thức

1. Spring Boot 3.5 – Common Application Properties (**spring.http.codecs.max-in-memory-size** và **spring.webflux.multipart**): https://docs.spring.io/spring-boot/3.5/appendix/application-properties/
2. Spring Framework 6.2 – WebFlux Config, **ServerCodecConfigurer**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html
3. Spring Framework – WebFlux Reactive Core, **Limits**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html
4. Spring Framework – WebClient Configuration/MaxInMemorySize: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html
5. Spring Framework – Data Buffers and Codecs: https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html
6. Spring Boot 3.5 – Reactive Web Applications: https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html
7. Spring Framework – Multipart Content: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/multipart-forms.html

## 14. Tổng kết

Trong WebFlux, dữ liệu HTTP có thể được nhận dưới dạng stream, nhưng codec vẫn phải **gom một số byte nhất định** khi giải mã một giá trị. Giới hạn **maxInMemorySize**, mặc định thường khoảng **256 KiB** ở nhiều codec, giúp phát hiện aggregation quá lớn bằng **DataBufferLimitException**.

Trên **Spring Boot 3.5**, dùng **spring.http.codecs.max-in-memory-size** hoặc cấu hình codec trực tiếp để điều chỉnh giới hạn. **Giới hạn codec không thay thế giới hạn HTTP request, multipart file, concurrency hay RAM toàn tiến trình**. Dùng object/Mono cho payload nhỏ, Flux streaming cho nhiều record, FilePart/PartEvent cho upload và quản lý DataBuffer đúng cách để ứng dụng reactive ổn định dưới tải.
