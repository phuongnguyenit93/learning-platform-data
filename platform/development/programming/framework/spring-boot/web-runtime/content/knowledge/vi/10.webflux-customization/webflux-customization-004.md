# CodecCustomizer và cấu hình codec ở mức ứng dụng trong Spring WebFlux

## Mục tiêu học tập

Trong Spring WebFlux, HTTP request/response body không tự biến thành Java object. Framework chọn **HTTP message reader/writer** dựa trên Content-Type, Accept, Java type, thư viện trong classpath và các cấu hình codec. Spring Boot hỗ trợ cấu hình mặc định cho phần này, cho phép áp dụng thuộc tính ứng dụng hoặc đăng ký bean **CodecCustomizer** để tùy chỉnh.

Sau khi học, bạn có thể:

- Phân biệt codec, Encoder/Decoder, HttpMessageReader/HttpMessageWriter và CodecConfigurer.
- Mô tả cách Spring Boot kết hợp default codecs, application properties và CodecCustomizer.
- Chọn đúng giữa **spring.http.codecs.max-in-memory-size**, **CodecCustomizer**, **WebFluxConfigurer.configureHttpMessageCodecs** và cấu hình riêng của WebClient.
- Hiểu giới hạn buffer in-memory, DataBufferLimitException và những giới hạn không được điều khiển bởi maxInMemorySize.
- Thiết lập cấu hình không vô tình loại bỏ JSON, text, form, multipart hoặc Server-Sent Events.
- Xây dựng ứng dụng WebFlux Java 17+ có codec customization và kiểm thử HTTP với WebTestClient.
- Phân tích lỗi 400, 406, 415, lỗi JSON và rủi ro lộ dữ liệu khi bật logging codec.

## 1. Vì sao WebFlux cần HTTP codecs?

Một HTTP request có **metadata** như method, path, headers và có **body** là chuỗi byte. Khi controller nhận một Java object từ request body, hoặc trả một object để gửi response, WebFlux cần chuyển đổi dữ liệu.

Ví dụ client gửi:

~~~http
POST /api/echo HTTP/1.1
Host: localhost:8080
Content-Type: application/json
Accept: application/json

{"text":"hello"}
~~~

Controller nhận Java record Payload và trả một record. WebFlux phải:

1. Dựa trên **Content-Type: application/json** và Java type để chọn reader/decoder phù hợp.
2. Đọc các DataBuffer từ request body theo Reactive Streams.
3. Decode JSON thành đối tượng Payload.
4. Gọi controller/service (có thể trả Mono hoặc Flux).
5. Dựa trên **Accept: application/json** và response Java type để chọn writer/encoder phù hợp.
6. Encode đối tượng thành byte, ghi HTTP response.

Sơ đồ:

~~~text
HTTP request                           Spring WebFlux                      HTTP response
headers + Flux<DataBuffer>             request handling                   headers + bytes
         |                                    |                                    ^
         v                                    |                                    |
   HttpMessageReader                         |                             HttpMessageWriter
         |                                    |                                    ^
       Decoder                               |                                  Encoder
         |                                    |                                    ^
         v                                    v                                    |
     Java object ----------------> Controller/Handler -----------------> Java object/Publisher
~~~

Codecs **không quyết định controller URL** và cũng không thay thế validation, authentication hay exception handling. Chúng phụ trách cách đọc/ghi body, media type, serialization và việc buffer khi cần.

## 2. Phân biệt các khái niệm

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| Encoder<T> | Chuyển đối tượng hoặc chuỗi thành dữ liệu byte | Encode JSON, String, byte[] |
| Decoder<T> | Chuyển dữ liệu byte thành đối tượng | Decode JSON, String, protobuf nếu có custom codec |
| HttpMessageReader<T> | Adapter đọc request body theo HTTP/media type | Reader cho JSON, form |
| HttpMessageWriter<T> | Adapter ghi response body theo HTTP/media type | Writer cho JSON, text hoặc SSE |
| CodecConfigurer | Registry và điểm cấu hình nhóm codecs | registerDefaults, defaultCodecs, customCodecs |
| ServerCodecConfigurer | CodecConfigurer cho phía server WebFlux | Dùng trong WebFluxConfigurer |
| ClientCodecConfigurer | CodecConfigurer cho HTTP client WebClient | Dùng với WebClient.Builder.codecs |
| CodecCustomizer | Callback của Spring Boot áp dụng vào CodecConfigurer | Điều chỉnh giới hạn bộ nhớ, đăng ký custom codec |
| Jackson / JSON mapper | Engine serialize/deserialize JSON | Chuyển JSON thành Java record và ngược lại |
| DataBuffer | Phần dữ liệu byte trong reactive I/O | Flux<DataBuffer> của request body |

Ở mức đơn giản, bạn có thể nghĩ **Decoder** là cách chuyển dữ liệu vào, **Encoder** là cách chuyển dữ liệu ra. Các HttpMessageReader/Writer bổ sung ngữ cảnh HTTP và chọn codec phù hợp.

Các thư viện có trên classpath ảnh hưởng khả năng codec. Ví dụ thiếu thư viện hỗ trợ JSON phù hợp có thể làm request application/json không được xử lý như mong muốn. Spring Boot thường quản lý bộ phụ thuộc cần thiết khi dùng starter WebFlux.

**Không nhầm với MVC:** Spring MVC dùng HttpMessageConverter theo Servlet stack; Spring WebFlux chủ yếu dùng HttpMessageReader/Writer và reactive codecs. Vì vậy một Customizer của MVC không tự động là CodecCustomizer của WebFlux.

## 3. Spring Boot chọn và tùy chỉnh codecs như thế nào?

Với ứng dụng Spring WebFlux auto-configured, Spring Boot tạo cấu hình codecs dựa trên mặc định của Spring Framework và những thành phần trên classpath. Sau đó có thể áp dụng các tùy chỉnh qua:

- **Application properties** như spring.http.codecs.max-in-memory-size và spring.http.codecs.log-request-details trong các phiên bản hỗ trợ.
- **CodecCustomizer beans** do Spring Boot hoặc ứng dụng cung cấp.
- **Jackson configuration** và các module/bean liên quan đến serialization/deserialization nếu JSON mapper tương ứng được dùng.
- **WebFluxConfigurer.configureHttpMessageCodecs** để tùy chỉnh đăng ký reader/writer ở phía HTTP server.
- **WebClient-specific codec configuration** dành cho các client được tạo hoặc tùy chỉnh riêng.

Mô hình:

~~~text
Spring Boot WebFlux auto-configuration
            |
            +-- Spring Framework default codecs
            |       JSON, String, byte[], form, SSE ... tùy classpath
            |
            +-- spring.http.codecs.* properties
            |
            +-- CodecCustomizer beans
            |       default codecs / custom codecs
            |
            +-- WebFlux server codec configuration
            |       HttpMessageReader / HttpMessageWriter
            |
            +-- WebClient auto-configuration (khi áp dụng)
                    ClientCodecConfigurer / ExchangeStrategies
~~~

Spring Boot có thể cung cấp customizer của chính nó cho JSON mapper, giới hạn buffer hoặc logging. Nếu thêm một customizer khác, bạn phải xét khả năng các callback cùng sửa một property; giá trị có hiệu lực cuối cùng phụ thuộc cách framework áp dụng và thứ tự. Đừng tạo nhiều cấu hình mâu thuẫn rồi kỳ vọng một thuộc tính luôn “thắng”.

**Giữ lại Boot auto-configuration:** Nếu chỉ muốn mở rộng WebFlux, khai báo WebFluxConfigurer trong @Configuration **không thêm @EnableWebFlux**. @EnableWebFlux là chế độ dành cho việc chủ động kiểm soát cấu hình WebFlux theo Spring Framework, và có thể làm những tiện ích auto-configuration dành cho WebFlux của Boot không còn được áp dụng như trước.

## 4. CodecCustomizer là gì?

**CodecCustomizer** là callback của Spring Boot nhận một CodecConfigurer và cho phép code của ứng dụng thay đổi cách codec được cấu hình. Đây không phải một codec riêng và không trực tiếp đọc hoặc ghi body; nó **tùy chỉnh registry/configuration** khi Spring Boot xây dựng HTTP codec configuration.

### Khác biệt package theo phiên bản

Package của CodecCustomizer thay đổi theo thế hệ Spring Boot. Không sao chép import từ blog bất kỳ khi nâng major version.

| Spring Boot | Import điển hình | Ghi chú |
|---|---|---|
| Spring Boot 3.5.x | org.springframework.boot.web.codec.CodecCustomizer | Dùng trong ví dụ runnable bên dưới |
| Spring Boot 4.x | org.springframework.boot.http.codec.CodecCustomizer | API đã được tổ chức lại theo module/package |

Mỗi project chỉ dùng import tương thích với version của mình. Ví dụ bài này tập trung Java 17+ và Spring Boot **3.5.x**, để giữ code compile được nhất quán. Nếu dự án dùng 4.x, kiểm tra Javadoc/BOM tương ứng và đổi import như bảng.

Hình thức khai báo một bean:

~~~java
@Configuration(proxyBeanMethods = false)
class CodecConfig {

    @Bean
    CodecCustomizer codecCustomizer() {
        return configurer ->
            configurer.defaultCodecs().maxInMemorySize(1024 * 1024);
    }
}
~~~

Đây là đoạn code rút gọn, cần imports @Configuration, @Bean và CodecCustomizer theo đúng phiên bản. Giá trị 1024 * 1024 là **1 MiB = 1.048.576 byte**, không phải một triệu byte thập phân.

### Khi nào dùng CodecCustomizer?

Dùng khi muốn cấu hình mã hóa/giải mã ở mức Boot, ví dụ:

- Điều chỉnh giới hạn tập hợp buffer cho default codecs.
- Đăng ký một decoder/encoder hoặc message reader/writer chuyên biệt.
- Thay thế hành vi codec mặc định khi thực sự có yêu cầu kiến trúc.
- Thiết lập callback có thể được Boot áp dụng vào codec configuration mà nó tự xây dựng.

Phạm vi thực tế phụ thuộc Boot integration: một WebClient tạo thủ công bằng WebClient.builder() không mặc nhiên nhận tất cả bean/configuration đã được Boot áp dụng cho WebFlux server hoặc cho WebClient.Builder do Boot cung cấp. Khi debug phải xác định rõ client/server được tạo bằng cơ chế nào.

## 5. Cấu hình bằng application.properties: cách đơn giản nhất

Nếu yêu cầu chỉ là đổi giới hạn đọc/aggregate trong bộ nhớ, ưu tiên **property** thay vì viết custom Java bean không cần thiết.

Trong Spring Boot 3.5 và các phiên bản 4.x được đề cập ở tài liệu chính thức:

~~~properties
spring.http.codecs.max-in-memory-size=1MB
~~~

Thuộc tính này kiểm soát mức byte mà các codec phù hợp có thể giữ trong bộ nhớ khi cần tổng hợp dữ liệu. Tài liệu Boot cho biết property áp dụng với **WebFlux server và WebClient được auto-configure**, không bảo đảm mọi HTTP client do bạn tự tạo cũng nhận giá trị này.

Ví dụ ở YAML:

~~~yaml
spring:
  http:
    codecs:
      max-in-memory-size: 1MB
~~~

### Phiên bản cũ hơn có thể dùng tên khác

Trong một số phiên bản Spring Boot 3.0–3.2, tài liệu dùng tên **spring.codec.max-in-memory-size**. Ở các phiên bản 3.5 trở lên, dùng **spring.http.codecs.max-in-memory-size** theo tài liệu của bản đang chạy. Khi nâng cấp, đừng giả định cấu hình cũ vẫn được bind: đọc version-specific application properties và bật cấu hình kiểm tra binding nếu cần.

Nếu hệ thống có nhiều service chạy Spring Boot phiên bản khác nhau, chuẩn hóa lại thuộc tính theo BOM của từng service; không nên copy một file cấu hình chung thiếu kiểm tra tương thích.

### Max in-memory là giới hạn gì?

Nó giới hạn số byte mà codec cần **buffer khi aggregate** một phần dữ liệu. Với JSON body thông thường được decode thành một object, quá trình đọc có thể phải giữ dữ liệu của object đó trong bộ nhớ. Với stream nhiều object, một số codec áp dụng giới hạn trên mỗi object được buffer, không nhất thiết trên tổng số byte của toàn bộ luồng.

Mặc định nhiều codec có ngưỡng khoảng **256 KiB**, nhưng giá trị chính xác có thể khác theo codec và phiên bản. Không chọn cấu hình dựa trên giả định mọi codec dùng cùng con số.

Khi vượt ngưỡng, thường thấy:

~~~text
org.springframework.core.io.buffer.DataBufferLimitException:
Exceeded limit on max bytes to buffer
~~~

**Quan trọng:** spring.http.codecs.max-in-memory-size **không phải** giới hạn dung lượng upload tổng quát của HTTP server, không phải firewall chống payload lớn, và không thay thế các ngưỡng ở gateway, reverse proxy, multipart, file storage, database hay business validation.

Nếu client gửi file 1 GB bằng multipart, không thể bảo vệ hệ thống chỉ bằng cách đặt property trên thành 1MB. Thiết kế upload cần giới hạn riêng, streaming, disk quota, thời gian xử lý, xác thực và xử lý cancellation.

## 6. Cấu hình CodecCustomizer trong Spring Boot 3.5

Ví dụ sau cố ý **giữ default codecs** rồi chỉ điều chỉnh giới hạn buffer. Đây là cách an toàn hơn việc gọi registerDefaults(false) khi bạn chưa muốn tự chịu trách nhiệm toàn bộ danh sách readers/writers.

**File:** src/main/java/com/example/codec/CodecConfig.java

~~~java
package com.example.codec;

import org.springframework.boot.web.codec.CodecCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CodecConfig {

    @Bean
    public CodecCustomizer appCodecCustomizer() {
        return configurer ->
            configurer.defaultCodecs().maxInMemorySize(1024 * 1024);
    }
}
~~~

Trong ví dụ, bean được phát hiện qua component scan của Spring Boot. Khi Boot áp dụng bean này cho CodecConfigurer do nó quản lý, default codecs sẽ nhận giới hạn bộ nhớ 1 MiB.

**Đừng đồng thời đặt property spring.http.codecs.max-in-memory-size với một giá trị khác cho đúng mục đích đó** nếu bạn không thực sự cần kiểm soát thứ tự và precedence. Để bài học dễ kiểm chứng, khi chạy ví dụ này hãy để property max-in-memory-size **không được khai báo**.

Nếu dự án dùng Spring Boot 4.x, giữ logic tương ứng nhưng thay import bằng:

~~~java
import org.springframework.boot.http.codec.CodecCustomizer;
~~~

Thay đổi import theo major version không đồng nghĩa tất cả API bên dưới sẽ ổn định vô thời hạn. Kiểm tra Spring Boot migration guide khi nâng cấp.

## 7. Ví dụ ứng dụng Spring WebFlux đầy đủ

Ví dụ Java 17+, Spring Boot 3.5.x, starter spring-boot-starter-webflux. Tạo project Maven từ Spring Initializr chọn Spring Reactive Web. Không đồng thời thêm starter MVC nếu mục tiêu là chạy reactive web server.

Ba file Java cần có cùng package com.example.codec.

### 7.1. CodecApplication.java

~~~java
package com.example.codec;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CodecApplication {

    public static void main(String[] args) {
        SpringApplication.run(CodecApplication.class, args);
    }
}
~~~

### 7.2. Payload.java

~~~java
package com.example.codec;

public record Payload(String text) {
}
~~~

Record này dùng để minh họa JSON mapping của Jackson. JSON body hợp lệ sẽ có thuộc tính text kiểu String.

### 7.3. EchoController.java

~~~java
package com.example.codec;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class EchoController {

    @PostMapping(
        path = "/api/echo",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<Payload> echo(@RequestBody Mono<Payload> input) {
        return input.map(value ->
            new Payload(value.text() == null ? "" : value.text().trim())
        );
    }
}
~~~

### 7.4. CodecConfig.java

Dùng file CodecConfig.java đầy đủ ở phần 6 để giới hạn codec buffer tại 1 MiB.

### 7.5. Chạy và gọi endpoint

Từ project có Maven Wrapper:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Ví dụ request:

~~~bash
curl -i -X POST http://localhost:8080/api/echo \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"text":" Hello WebFlux "}'
~~~

Với route đã khai báo, kết quả mong đợi là HTTP 200 cùng JSON tương đương:

~~~json
{"text":"Hello WebFlux"}
~~~

Thứ tự header và header mặc định tùy runtime; điều kiểm tra trọng tâm là Content-Type phù hợp và body được trim.

Trong pipeline này:

1. JSON reader/decoder đọc body vào Payload.
2. Controller nhận Mono<Payload>.
3. map tạo Payload mới sau khi có giá trị.
4. JSON writer/encoder tạo response.
5. Nếu body không tương thích media type hoặc không decode được, WebFlux chuyển lỗi theo cơ chế HTTP handling phù hợp.

Bạn **không cần** tự subscribe() hoặc block() trong controller. Framework quản lý subscription và response lifecycle.

## 8. Khi nào dùng WebFluxConfigurer.configureHttpMessageCodecs?

Ngoài CodecCustomizer, Spring Framework cung cấp **WebFluxConfigurer** để tùy chỉnh hạ tầng WebFlux ở phía server:

~~~java
package com.example.codec;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration(proxyBeanMethods = false)
public class ServerOnlyCodecConfig implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs().maxInMemorySize(512 * 1024);
    }
}
~~~

Đây là **phương án thay thế** cho CodecConfig ở phần 6, không phải class nên thêm đồng thời với một customizer khác đặt max-in-memory-size=1MiB. Nó minh họa tùy chỉnh server codec bằng API của Spring Framework.

Sự khác biệt chính:

| Khả năng | CodecCustomizer | WebFluxConfigurer.configureHttpMessageCodecs | WebClient.Builder.codecs |
|---|---|---|---|
| Thuộc lớp API | Spring Boot | Spring Framework WebFlux | Spring Framework HTTP client |
| Đối tượng cấu hình | CodecConfigurer | ServerCodecConfigurer | ClientCodecConfigurer |
| Phạm vi chính | Codec configurations do Boot sử dụng | WebFlux HTTP server | Một WebClient/builder cụ thể |
| Cần @EnableWebFlux? | Không | Không; tránh thêm nếu muốn giữ Boot defaults | Không |
| Sử dụng phù hợp | Tùy chỉnh ở mức Boot/application | Riêng hệ thống server-side WebFlux | Riêng client outbound hoặc client xây thủ công |

Nếu bạn chỉ muốn thay đổi ngưỡng buffer toàn ứng dụng được Boot auto-configure, property thường ngắn gọn hơn. Nếu bạn cần cấu hình riêng của HTTP server, WebFluxConfigurer có thể rõ mục đích hơn. Nếu ứng dụng dùng nhiều WebClient với các yêu cầu khác nhau, đặt codec config trên từng builder.

### Vì sao không dùng @EnableWebFlux tùy tiện?

Trong Spring Boot, một WebFluxConfigurer thông thường **không cần** @EnableWebFlux. Khi thêm @EnableWebFlux, bạn báo cho Spring Framework trực tiếp cấu hình WebFlux và có thể làm phần WebFlux auto-configuration của Boot rút lui. Điều này có thể thay đổi resource handling, codecs tích hợp và các tiện ích khác. Hãy dùng chế độ full control chỉ khi bạn có lý do kiến trúc và đã kiểm tra các mặc định cần tái cấu hình.

## 9. Khi nào tự đăng ký custom codec?

Custom codec cần thiết khi:

- Ứng dụng có media type riêng không được default codecs hỗ trợ.
- Dữ liệu dùng định dạng binary/protocol chuyên biệt cần Decoder và Encoder tương ứng.
- Có yêu cầu streaming cho message format đặc biệt.
- Cần reader/writer với logic không thể biểu diễn bằng cấu hình serializer phổ thông.

Spring Framework có registry:

~~~java
configurer.customCodecs().register(customDecoder);
~~~

Trong đó customDecoder phải là decoder thật sự triển khai hợp đồng Spring tương ứng. Đây là mẫu minh họa, **không phải một đoạn compile độc lập**; tên biến customDecoder cần định nghĩa bằng một implementation cụ thể.

Trong các phiên bản hỗ trợ, API registerWithDefaultConfig giúp custom codec nhận những default settings thích hợp, chẳng hạn maxInMemorySize và logging details nếu custom codec có hỗ trợ. Việc register một codec không tự bảo đảm nó hiểu tất cả property như default codecs.

### Nguy hiểm của registerDefaults(false)

API:

~~~java
configurer.registerDefaults(false);
~~~

là tùy chọn **tắt đăng ký default codecs**, không phải “ưu tiên custom codec này hơn một chút”. Nếu bật tùy tiện, application có thể mất JSON reader/writer, text reader/writer, form codecs hoặc SSE support tùy tình huống.

Hệ quả có thể là:

- Request Content-Type: application/json không được hỗ trợ, phát sinh 415.
- Server không có writer phù hợp để đáp ứng Accept, phát sinh 406.
- Endpoint previously worked now fails during response serialization.
- Các integration test HTTP bị thay đổi ngoài dự kiến.

Chỉ dùng registerDefaults(false) khi **thật sự muốn thay toàn bộ codec list** và đã đăng ký đủ readers/writers cần thiết cho tất cả media types của ứng dụng. Hầu hết nhu cầu tùy chỉnh giới hạn bộ nhớ **không** cần tắt defaults.

### Thay đổi JSON mapping không nhất thiết cần codec mới

Nếu mục tiêu là định dạng LocalDateTime, quy ước tên thuộc tính hoặc custom serialization, ưu tiên Jackson configuration do Boot hỗ trợ: các cấu hình **spring.jackson.***, Jackson modules và các bean serializer/deserializer. Việc custom hoàn toàn JSON codec có thể làm mất những tích hợp Boot đã thiết lập.

Spring Boot 4.x có thay đổi về thế hệ Jackson, do đó khi nâng major version cần chọn API tương ứng. Không sao chép một đoạn tùy chỉnh Jackson2 codec từ ứng dụng Boot 3.x sang Boot 4.x mà không đối chiếu thư viện và migration guide.

## 10. Cấu hình WebClient: không nhầm server và client

WebFlux server **đọc request** và **ghi response**. WebClient là HTTP client **ghi request** và **đọc response**. Cả hai có codec configs nhưng lifecycle và đối tượng config riêng.

Khi tự tạo client, có thể điều chỉnh codec:

~~~java
import org.springframework.web.reactive.function.client.WebClient;

WebClient client = WebClient.builder()
    .baseUrl("https://service.example")
    .codecs(configurer ->
        configurer.defaultCodecs().maxInMemorySize(2 * 1024 * 1024)
    )
    .build();
~~~

Đây là đoạn code minh họa đặt trong method hoặc @Bean thích hợp; đoạn trên tạo WebClient dùng maxInMemorySize 2 MiB cho default client codecs của nó.

Nếu ứng dụng đã được Spring Boot auto-configure, nên xem xét inject **WebClient.Builder** do Boot cung cấp để tận dụng các customizations phù hợp, rồi bổ sung cấu hình riêng khi cần. Không tự cho rằng mọi WebClient được tạo bằng WebClient.create() hoặc WebClient.builder() sẽ nhận toàn bộ bean CodecCustomizer của Boot.

Một vấn đề thường gặp: server của chính ứng dụng decode request 1 MiB thành công nhưng WebClient gọi downstream và decode response lớn hơn mức mặc định rồi ném DataBufferLimitException. Khi đó phải kiểm tra **codec settings của WebClient nhận dữ liệu**, không chỉ nâng giới hạn ở server.

Đặt maxInMemorySize lớn có chi phí bộ nhớ. Với nhiều request đồng thời, mỗi aggregation có thể giữ một lượng dữ liệu đáng kể; cần benchmark với concurrency và giới hạn kích thước payload tại lớp ngoài phù hợp.

## 11. Media type, Content-Type, Accept và status HTTP

**Content-Type** trên request báo định dạng body client gửi, trong khi **Accept** báo định dạng response client muốn nhận. WebFlux lựa chọn reader/writer dựa vào media type, Java type, annotations và codec được đăng ký.

Ví dụ:

~~~http
POST /api/echo HTTP/1.1
Content-Type: application/json
Accept: application/json

{"text":"abc"}
~~~

Handler chỉ khai báo consumes và produces application/json sẽ nhận được request phù hợp. Nếu gửi text/plain thay vì application/json, route có thể bị từ chối vì consumes mismatch, thông thường là 415 Unsupported Media Type.

Nếu Accept chỉ chấp nhận một media type handler/codec không hỗ trợ, có thể trả 406 Not Acceptable. Nếu JSON body bị sai cú pháp và request không deserialize được, thường là lỗi 400 Bad Request trong hành vi mặc định.

Đừng quy mọi HTTP status thành “codec không được register”; ví dụ:

| Triệu chứng | Khả năng nguyên nhân | Cách kiểm tra |
|---|---|---|
| 400 khi gửi JSON | JSON malformed, type mismatch, validation hoặc binding | Kiểm tra body, DTO và message reader error |
| 406 Not Acceptable | Accept/produces không khớp, thiếu writer | Kiểm tra response type, annotation produces, registered writers |
| 415 Unsupported Media Type | Content-Type/consumes không phù hợp, thiếu reader | Kiểm tra request media type và registered readers |
| DataBufferLimitException | Aggregate vượt ngưỡng codec cụ thể | Kiểm tra kích thước một object/buffer và cấu hình phía đang đọc |
| 500 khi ghi response | Encoder/serialization lỗi, lỗi service hoặc exception khác | Xem server logs và stacktrace |
| 413 Content Too Large | Có thể do reverse proxy hoặc giới hạn server/upload khác | Đối chiếu gateway, server và multipart configuration |

Status cuối cùng phụ thuộc framework exception handler, server/gateway và cấu hình ứng dụng. Bảng chỉ đưa ra hướng chẩn đoán, không bảo đảm mã lỗi giống nhau trong mọi deployment.

## 12. Multipart và streaming: tại sao không chỉ tăng maxInMemorySize?

Nếu client upload ảnh hoặc file lớn, việc tăng spring.http.codecs.max-in-memory-size có thể **không** giải quyết đúng vấn đề. Multipart có ngưỡng in-memory/disk riêng, số part, phần header và giới hạn storage.

Một số property liên quan trong Spring Boot 3.5+:

~~~properties
spring.webflux.multipart.max-in-memory-size=256KB
spring.webflux.multipart.max-disk-usage-per-part=10MB
spring.webflux.multipart.max-parts=20
~~~

Ví dụ là chính sách minh họa, không phải khuyến nghị chung; giá trị phù hợp phụ thuộc loại file, business requirements và hạ tầng. Những property này điều khiển multipart handling theo cơ chế Spring WebFlux và version tương ứng; cấu hình HTTP server/proxy vẫn có thể áp thêm giới hạn.

Khác biệt giữa các tình huống:

- **Mono<Payload>** cho một JSON body thường dẫn đến decode một object và có thể aggregate dữ liệu.
- **Flux<Payload>** ở dạng JSON stream/NDJSON có thể xử lý từng phần tử; tuy nhiên codec có thể buffer một object hoặc dùng prefetch.
- **Flux<DataBuffer>** là dạng body byte streaming ở tầng thấp; bản thân việc dùng Flux không làm an toàn nếu downstream vẫn collectList hoặc join toàn bộ stream.
- **Multipart PartEvent streaming** có cơ chế xử lý riêng; cần quản lý release buffer và lỗi khi ghi/đọc.

Nếu payload lớn có thể xử lý theo dòng, hãy thiết kế API streaming thay vì chỉ tăng ngưỡng aggregate lên hàng trăm MB. Cần đo throughput, memory, heap/off-heap và backpressure với tải thực tế.

## 13. Logging codec và dữ liệu nhạy cảm

WebFlux/Boot có tùy chọn logging chi tiết request; trong phiên bản hỗ trợ:

~~~properties
spring.http.codecs.log-request-details=true
~~~

Tính năng này phục vụ việc chẩn đoán trong môi trường có kiểm soát. Nó có thể khiến thông tin form data hoặc header nhạy cảm xuất hiện trong log khi kết hợp logging DEBUG/TRACE tương ứng.

Không bật chi tiết log tràn lan ở production chỉ để tìm nguyên nhân lỗi 415. Trước khi bật, cần cân nhắc:

1. Có thể xuất hiện token, thông tin cá nhân, cookie hoặc dữ liệu bí mật không?
2. Log được lưu ở đâu và ai có quyền đọc?
3. Có retention và masking policy thích hợp không?
4. Có cách debug bằng metadata, content type và payload size thay vì toàn bộ nội dung không?

CodecCustomizer cũng có API cho việc logging request details ở default codecs, nhưng dùng API đó vẫn cần đánh giá an toàn. Mặc định, hãy ưu tiên logging ở mức metadata cần thiết.

## 14. Kiểm thử cấu hình codec bằng WebTestClient

**WebTestClient** cho phép gửi request theo hợp đồng HTTP và kiểm tra kết quả của stack WebFlux. Với project ở phần 7, thêm dependency **spring-boot-starter-test** ở test scope.

Ví dụ Spring Boot 3.5.x:

~~~java
package com.example.codec;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class CodecApplicationTest {

    @Autowired
    private WebTestClient webTestClient;

    @Test
    void jsonBodyIsDecodedAndEncoded() {
        webTestClient.post()
            .uri("/api/echo")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .bodyValue(new Payload("  hello  "))
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON
            )
            .expectBody()
            .jsonPath("$.text").isEqualTo("hello");
    }
}
~~~

Test này xác minh hai chiều: payload Java được test client serialize thành JSON, server decode request và encode response. Với test cần kiểm tra **đúng codec server**, hãy nhận thức test WebTestClient cũng có codec riêng ở phía test client.

Cách kiểm tra giới hạn bộ nhớ có thể thiết kế:

1. Đặt maxInMemorySize nhỏ (ví dụ 64KB) cho test profile.
2. Gửi JSON object có body lớn hơn ngưỡng đó.
3. Kiểm tra request không được xử lý thành công; xem cause chain và log để xác nhận DataBufferLimitException.
4. Gửi object nhỏ hơn ngưỡng và kiểm tra HTTP 200, body đúng.
5. Chạy thử cả WebClient outbound nếu ứng dụng dùng nó.

Không khẳng định mọi request vượt giới hạn đều trả **một HTTP status cố định**: phản hồi còn do exception mapping của runtime. Điều quan trọng là kiểm tra giới hạn bảo vệ hoạt động và lỗi được xử lý nhất quán, không lộ chi tiết hạ tầng.

Với Boot 4.x, package của một số annotation auto-configure test đã thay đổi; cần dùng import/version tương ứng thay vì copy nguyên từ ví dụ Boot 3.5.

## 15. Lỗi thiết kế thường gặp và cách sửa

### Dùng registerDefaults(false) chỉ để thêm một codec

Nếu chỉ muốn custom JSON format hoặc tăng giới hạn buffer, không cần tắt default codecs. Giữ mặc định, cấu hình đúng nhóm codec rồi chạy regression tests cho JSON, text, multipart, SSE.

### Tưởng CodecCustomizer chính là Decoder

CodecCustomizer là callback lên registry. Để hỗ trợ format mới, bạn phải có Encoder/Decoder/reader/writer phù hợp và đăng ký nó. Chỉ có một bean CodecCustomizer không sinh ra khả năng decode protocol bất kỳ.

### Chỉnh server nhưng lỗi nằm ở WebClient

DataBufferLimitException có thể phát sinh khi client gọi service khác. Kiểm tra nơi đọc dữ liệu: server inbound hay client inbound. Với WebClient tự tạo, kiểm tra builder riêng.

### Dùng thuộc tính của phiên bản khác

Trong một số Spring Boot cũ, prefix property là spring.codec.*, còn Boot 3.5/4.x dùng spring.http.codecs.*. Với Boot 4.x, import CodecCustomizer đổi package. Luôn kiểm tra bản thư viện đang chạy.

### Tăng maxInMemorySize vô hạn để tránh lỗi

Tăng ngưỡng có thể giải quyết một object hợp lệ lớn nhưng làm tăng memory footprint. Phải giới hạn ở client/gateway, thiết kế streaming khi phù hợp và cân nhắc nhiều request cùng lúc.

### Lẫn lộn giới hạn codecs với upload file

File multipart có cơ chế disk spill và quotas riêng; proxy cũng có body size limit riêng. Không dùng codec aggregate setting thay cho upload policy.

### Thay toàn bộ Jackson config khi chỉ cần định dạng một field

Tùy chỉnh Jackson serializer/deserializer hoặc property phù hợp trước khi viết JSON decoder mới. Việc thay codec JSON có thể làm mất module, cấu hình date/time và các tích hợp Boot.

### Gọi block() trong controller vì nghĩ codec phải chạy đồng bộ

WebFlux nhận Mono/Flux và tự điều phối đọc/ghi. Codec có thể vận hành trong reactive pipeline; gọi block() trong request handling phá vỡ lợi ích non-blocking và có thể gây vấn đề trên event-loop threads.

### Thiếu integration test cho Content-Type và Accept

Một request gửi text/plain tới endpoint consumes application/json có thể fail dù controller code đúng. Test cả hợp đồng media type, DTO và response format.

### Giả định mọi custom codec sẽ tôn trọng default settings

Custom codec cần hỗ trợ cấu hình tương ứng. Nếu codec riêng không giới hạn buffer đúng cách, maxInMemorySize của default codecs có thể không bảo vệ nó.

## 16. Checklist khi thay đổi cấu hình codecs ở production

Trước khi deploy, nên xác nhận:

- **Version:** Spring Boot/BOM chính xác; import và property đúng version.
- **Scope:** server inbound, server outbound, WebClient inbound/outbound — bên nào cần thay?
- **Defaults:** có vô tình gọi registerDefaults(false) không?
- **JSON:** serialization/deserialization và các Jackson modules vẫn hoạt động.
- **Media types:** kiểm thử application/json, text/plain, SSE, form/multipart nếu ứng dụng dùng.
- **Memory:** giới hạn phù hợp payload, concurrency và memory budget; không tăng vô hạn.
- **Streaming:** tránh aggregate toàn bộ stream lớn hoặc vô hạn.
- **Security:** không expose secret trong request logging.
- **Errors:** 400, 406, 415 và overflow được chuyển thành phản hồi/metric phù hợp.
- **Regression:** WebTestClient, WebClient integration test và benchmark mô phỏng tải.
- **Observability:** theo dõi DataBufferLimitException, latency, memory và upstream errors.
- **Rollback:** khi lỗi phát sinh, có thể trả về property mặc định hoặc tắt customizer không?

## 17. Câu hỏi tự kiểm tra

1. HttpMessageReader và HttpMessageWriter nằm ở giai đoạn nào của request/response trong WebFlux?
2. CodecCustomizer thuộc Spring Boot hay Spring Framework? Nó có tự tạo Decoder không?
3. Vì sao spring.http.codecs.max-in-memory-size không phải giới hạn tổng kích thước upload?
4. Spring Boot 3.5 và 4.x khác nhau ở import CodecCustomizer như thế nào?
5. Khi nào ưu tiên application property thay vì viết CodecCustomizer bean?
6. Nếu chỉ muốn điều chỉnh server-side codecs, extension point của WebFluxConfigurer là gì?
7. Khi nào cần cấu hình riêng WebClient.Builder.codecs?
8. registerDefaults(false) có thể gây loại lỗi HTTP nào?
9. Vì sao custom JSON converter không nên thay thế tùy tiện toàn bộ Jackson setup?
10. Làm sao xác nhận request JSON thành công mà không dựa vào việc gọi block()?
11. Với DataBufferLimitException ở HTTP client gọi downstream, nên kiểm tra cấu hình phía nào?
12. Có nên bật log-request-details=true ở mọi môi trường sản xuất?

### Đáp án gợi ý

1. Reader decode request body thành đối tượng; writer encode response body từ đối tượng/publisher.
2. Spring Boot; nó tùy chỉnh CodecConfigurer, codec thật phải được cung cấp nếu cần định dạng mới.
3. Giới hạn aggregate của codec, không bao phủ mọi transport body, multipart storage hoặc gateway policy.
4. Boot 3.5: org.springframework.boot.web.codec.CodecCustomizer; Boot 4.x: org.springframework.boot.http.codec.CodecCustomizer.
5. Khi thay đổi chỉ là giới hạn buffer hoặc logging mà Boot đã có property.
6. configureHttpMessageCodecs(ServerCodecConfigurer configurer).
7. Khi WebClient được tạo thủ công hoặc cần settings khác với global auto-configuration.
8. 415 khi thiếu reader phù hợp, 406 khi thiếu writer phù hợp, tùy request và cấu hình.
9. Vì mất khả năng dùng modules/default settings và có thể tạo khác biệt format/validation.
10. Dùng WebTestClient gửi request hợp lệ, assert status, Content-Type và body.
11. Kiểm tra client-side codecs, nhất là WebClient.Builder được dùng tạo client đó.
12. Không; cân nhắc rủi ro header/form data nhạy cảm và chỉ bật giới hạn trong debug có kiểm soát.

## 18. Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html): CodecCustomizer, WebFlux auto-configuration và HTTP codecs.
- [Spring Boot 4.x — Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html): package CodecCustomizer và cơ chế quản lý codec hiện hành.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): spring.http.codecs.max-in-memory-size và multipart.
- [Spring Framework — WebFlux Config](https://docs.spring.io/spring-framework/reference/web/webflux/config.html): WebFluxConfigurer, ServerCodecConfigurer, default codecs và custom codecs.
- [Spring Framework — Reactive Core](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): buffering, DataBufferLimitException và streaming.
- [Spring Framework — WebClient Configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html): cấu hình client codecs.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): kiểm thử request/response của reactive web stack.
