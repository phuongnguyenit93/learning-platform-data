# HttpMessageConverter của Spring MVC và codec của Spring WebFlux

Spring Boot cung cấp hai web stack: **Spring MVC (Servlet)** và **Spring WebFlux (reactive)**. Cả hai đều có thể nhận JSON qua `@RequestBody` và trả JSON từ `@RestController`, nhưng dùng **hai lớp hạ tầng khác nhau** để chuyển đổi giữa HTTP body và đối tượng Java:

- **Spring MVC:** dùng danh sách `HttpMessageConverter<?>`. Converter đọc HTTP body theo kiểu Java và media type, hoặc ghi giá trị Java vào HTTP response.
- **Spring WebFlux:** dùng `HttpMessageReader<?>` và `HttpMessageWriter<?>`, thường được xây dựng từ `Decoder<?>`/`Encoder<?>` và những adapter phù hợp. Chúng tích hợp với reactive streams (`Publisher`, `Mono`, `Flux`) và `DataBuffer`.
- **Jackson:** là thư viện JSON phổ biến mà Spring Boot tích hợp ở cả hai mô hình khi dependency phù hợp hiện diện. Jackson xử lý JSON; nó **không** đồng nghĩa toàn bộ cơ chế MVC converters hay WebFlux codecs.

Cùng một kiểu DTO Java và cùng HTTP `Content-Type: application/json` có thể hoạt động giống nhau ở mức API, nhưng cách xử lý stream, buffering, backpressure, threads và điểm cấu hình **không giống nhau**.

## 1. HTTP body được chuyển đổi ở giai đoạn nào?

Giả sử client gửi:

~~~http
POST /people/echo HTTP/1.1
Content-Type: application/json
Accept: application/json

{"name":"Lan","age":24}
~~~

Spring cần thực hiện hai chiều:

1. **Đọc (decode):** nhận các byte JSON, chuyển thành `Person("Lan", 24)` để truyền vào controller.
2. **Ghi (encode):** biến đối tượng Java mà controller trả về thành các byte JSON gửi cho client.

Một DTO dùng chung về mặt ý tưởng:

~~~java
record Person(String name, int age) {}
~~~

Đây là Java record (Java 17+). Khi sử dụng với một mapper JSON tương thích, nó có thể được serialize/deserialize qua các record components.

**Không phải mọi đối số controller đều dùng body converter.** `@PathVariable` và `@RequestParam` đi qua cơ chế mapping/binding; `@RequestBody` và `@ResponseBody`/`@RestController` mới là những vị trí điển hình của body conversion. Với `@RequestPart`, converter/codec có thể tham gia giải mã nội dung của một multipart part.

## 2. Luồng trong Spring MVC: HttpMessageConverter

Với `spring-boot-starter-web`, web server mặc định thông thường là embedded Tomcat. Một HTTP request đi theo đường:

~~~text
HTTP client
  -> Servlet container
  -> Servlet FilterChain
  -> DispatcherServlet
  -> HandlerMapping / HandlerAdapter
  -> @RequestBody argument resolver
       -> HttpMessageConverter.canRead(Java type, Content-Type)
       -> converter.read(...) -> Person
  -> Controller / Service
  -> @ResponseBody return-value handler
       -> HttpMessageConverter.canWrite(Java type, response media type)
       -> converter.write(...) -> HTTP bytes
  -> Servlet container -> HTTP response
~~~

Các class/framework liên quan:

| Thành phần MVC | Vai trò |
|---|---|
| `HttpMessageConverter<T>` | Hợp đồng đọc/ghi body giữa HTTP và kiểu Java |
| `MappingJackson2HttpMessageConverter` | JSON thông qua Jackson 2 trong Spring Boot 3.x khi có dependency phù hợp |
| `StringHttpMessageConverter` | Body dạng `String`, ví dụ text/plain |
| `ByteArrayHttpMessageConverter` | Body kiểu `byte[]` |
| `ResourceHttpMessageConverter` | Body liên quan `Resource` |
| `AllEncompassingFormHttpMessageConverter` | Form và các trường hợp multipart theo hỗ trợ |
| `RequestResponseBodyMethodProcessor` | Đọc `@RequestBody` và xử lý `@ResponseBody` cho annotated MVC |

Danh sách converter thực tế phụ thuộc **Spring Framework/Spring Boot version**, classpath và cấu hình người dùng. Không mặc định tất cả converter JSON, XML, Protobuf, Smile, CBOR... đều có mặt ở mọi ứng dụng.

### 2.1. canRead và canWrite lựa chọn theo hai điều kiện

Một converter được cân nhắc dựa trên ít nhất:

- Kiểu dữ liệu Java mà controller muốn nhận hoặc trả.
- HTTP media type phù hợp: `Content-Type` khi đọc body, hoặc loại nội dung đã thương lượng khi ghi body.
- Với converter và adapter hỗ trợ kiểu generic, Spring còn xét `Type`, generic type/context và phần mở rộng liên quan.

Thí dụ một JSON converter có thể đọc `Person` với `application/json`, nhưng `StringHttpMessageConverter` thường được dùng để ghi một response `String` dưới dạng text.

**Thứ tự trong danh sách có thể quan trọng** khi nhiều converter cùng báo hỗ trợ một tổ hợp type + media type. Không nên thêm converter tùy biến hỗ trợ `Object.class` và `*/*` ở đầu danh sách khi mục tiêu chỉ là thêm một wire format hẹp: nó có thể chiếm phần việc của JSON/String converter mặc định.

### 2.2. Servlet body thường đọc/ghi đồng bộ

Một `HttpMessageConverter` điển hình nhận `HttpInputMessage` và `HttpOutputMessage` có body liên quan tới Servlet HTTP stream. Trong một request Servlet đồng bộ thông thường, việc đọc/ghi qua converter diễn ra trên worker thread đang xử lý request.

Spring MVC có cả hỗ trợ asynchronous request processing. Vì vậy, không được kết luận “mọi MVC request bắt buộc giữ đúng một thread từ đầu đến cuối”, nhưng **contract HttpMessageConverter chủ yếu là body conversion đồng bộ** chứ không phải Reactive Streams reader/writer.

## 3. Luồng trong WebFlux: reader/writer và encoder/decoder

Với `spring-boot-starter-webflux` và không có starter Servlet khiến Boot suy luận stack khác, embedded HTTP server mặc định thường là **Reactor Netty**.

~~~text
HTTP client
  -> Reactor Netty HTTP events / DataBuffer
  -> WebFilter chain
  -> DispatcherHandler
  -> HandlerMapping / HandlerAdapter
  -> @RequestBody resolution
       -> HttpMessageReader.canRead(element type, media type)
       -> Decoder đọc các DataBuffer / Publisher
       -> Mono<Person> hoặc Person được cung cấp cho handler
  -> Reactive controller / Service
  -> Response body result handler
       -> HttpMessageWriter.canWrite(element type, media type)
       -> Encoder tạo các DataBuffer
       -> ghi HTTP response bằng non-blocking I/O
~~~

Những lớp cần biết:

| Thành phần WebFlux | Vai trò |
|---|---|
| `HttpMessageReader<T>` | Đọc body và phát dữ liệu Java qua reactive API |
| `HttpMessageWriter<T>` | Ghi dữ liệu Java/publisher ra HTTP response |
| `Decoder<T>` | Chuyển các `DataBuffer` thành dữ liệu Java |
| `Encoder<T>` | Chuyển dữ liệu Java thành các `DataBuffer` |
| `DecoderHttpMessageReader<T>` | Adapter từ decoder sang HTTP message reader |
| `EncoderHttpMessageWriter<T>` | Adapter từ encoder sang HTTP message writer |
| `Jackson2JsonDecoder` | Giải mã JSON bằng Jackson 2 trong Spring Framework 6.x |
| `Jackson2JsonEncoder` | Mã hóa JSON bằng Jackson 2 trong Spring Framework 6.x |
| `ServerCodecConfigurer` | Cấu hình default và custom codecs/readers/writers cho server |

`HttpMessageReader`/`Writer` là tầng biết về HTTP headers/media type, còn `Decoder`/`Encoder` tập trung vào chuyển đổi nội dung. Một số writer/reader không đơn thuần chỉ là adapter quanh một encoder/decoder — ví dụ xử lý multipart/resource có đặc thù riêng. Vì vậy, đừng nhầm `HttpMessageReader` là từ đồng nghĩa tuyệt đối với `Decoder`.

### 3.1. Vì sao WebFlux dùng Publisher và DataBuffer?

`DataBuffer` đại diện cho một vùng dữ liệu byte trong pipeline I/O. Thay vì buộc phải tập hợp toàn bộ body trước rồi mới xử lý, nhiều thành phần WebFlux có thể nhận/ghi dữ liệu theo luồng `Flux<DataBuffer>`. Decoder và encoder có thể biến các phần dữ liệu ấy thành đối tượng Java và ngược lại.

Ví dụ:

- JSON request đại diện một `Person`: nhiều decoder sẽ **gom/đọc đủ dữ liệu cần thiết** để tạo object hoàn chỉnh.
- Dòng JSON qua streaming media type như `application/x-ndjson`: encoder/decoder tương ứng có thể xử lý nhiều phần tử trên một stream mà không bắt buộc tích lũy toàn bộ chuỗi thành một JSON array trước.
- Tải file hoặc streaming binary response: có thể sử dụng API `DataBuffer`/Resource đặc thù; không nhất thiết đi qua Jackson.

**Reactive không đồng nghĩa luôn streaming zero-copy hoặc không dùng bộ nhớ.** Khi codec cần aggregate dữ liệu thành object, có buffering và giới hạn bộ nhớ; khi làm việc với pooled DataBuffer, quản lý vòng đời buffer là trách nhiệm quan trọng của framework và custom codec.

## 4. So sánh nhanh hai pipeline

| Thuộc tính | Spring MVC | Spring WebFlux |
|---|---|---|
| Server phổ biến | Servlet: Tomcat/Jetty/Undertow | Reactive: Reactor Netty |
| Front Controller | `DispatcherServlet` | `DispatcherHandler` |
| HTTP body abstraction | `HttpInputMessage` / `HttpOutputMessage` | `ReactiveHttpInputMessage` / `ReactiveHttpOutputMessage` |
| Chuyển đổi body | `HttpMessageConverter` | `HttpMessageReader` / `HttpMessageWriter` |
| Chuyển đổi byte ↔ object | Thường do converter đọc/ghi trực tiếp | `Decoder` / `Encoder` và codec adapters |
| Request body Java API | `@RequestBody Person` | `@RequestBody Person` hoặc `@RequestBody Mono<Person>` |
| Response body API | DTO, `ResponseEntity`, `@ResponseBody` | DTO, `Mono<DTO>`, `Flux<DTO>` và reactive response types |
| I/O chính | Servlet request/response, thường đồng bộ | Reactive non-blocking I/O |
| Điểm mở rộng phổ biến | `WebMvcConfigurer` | `WebFluxConfigurer` / `ServerCodecConfigurer` |
| Giữ cấu hình Boot mặc định | `extendMessageConverters` | `configureHttpMessageCodecs` với default/custom codec API phù hợp |
| Vấn đề dễ gặp | Mất default converters khi thay danh sách | Decoder/encoder custom chồng lấn, buffer vượt giới hạn, blocking trên event loop |

## 5. Ví dụ chạy được với Spring MVC

Ví dụ độc lập thứ nhất dùng **Spring Boot 3.x**, **Java 17+**, Gradle plugin/Boot dependency management đã được thiết lập. Dependency `build.gradle`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Tệp **src/main/java/demo/mvc/MvcJsonApplication.java**:

~~~java
package demo.mvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class MvcJsonApplication {

    public static void main(String[] args) {
        SpringApplication.run(MvcJsonApplication.class, args);
    }
}

record Person(String name, int age) {
}

@RestController
class MvcPeopleController {

    @PostMapping(
            path = "/people/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    Person echo(@RequestBody Person input) {
        return input;
    }

    @GetMapping(
            path = "/people/example",
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    Person example() {
        return new Person("Lan", 24);
    }
}
~~~

Tại endpoint POST, Spring MVC chọn JSON `HttpMessageConverter` để đọc body thành `Person`. Controller trả lại record; Spring MVC tiếp tục dùng converter phù hợp để ghi JSON response.

Chạy bằng Gradle wrapper của dự án:

~~~bash
./gradlew bootRun
~~~

Windows có thể dùng `gradlew.bat bootRun`. Test (cú pháp Bash):

~~~bash
curl -i http://localhost:8080/people/echo \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data '{"name":"Lan","age":24}'
~~~

Trong dự án minh họa không có Security/filter khác thay đổi hành vi, response HTTP có status **200 OK**, body JSON mang đúng giá trị `name=Lan` và `age=24`, ví dụ:

~~~json
{"name":"Lan","age":24}
~~~

Thứ tự trường JSON không phải quy tắc bảo đảm trong mọi cấu hình Jackson. Không nên viết test đòi thứ tự keys cố định nếu hợp đồng API chỉ yêu cầu giá trị.

## 6. Ví dụ chạy được với Spring WebFlux

Ví dụ độc lập thứ hai dùng **một dự án khác** với cùng Java 17+ và Spring Boot 3.x, nhưng chỉ dependency WebFlux:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

Tệp **src/main/java/demo/webflux/WebFluxJsonApplication.java**:

~~~java
package demo.webflux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class WebFluxJsonApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebFluxJsonApplication.class, args);
    }
}

record Person(String name, int age) {
}

@RestController
class WebFluxPeopleController {

    @PostMapping(
            path = "/people/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    Mono<Person> echo(@RequestBody Mono<Person> input) {
        return input;
    }

    @GetMapping(
            path = "/people/example",
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    Mono<Person> example() {
        return Mono.just(new Person("Lan", 24));
    }
}
~~~

Trong WebFlux, `@RequestBody Mono<Person>` được giải mã qua `HttpMessageReader`/decoder, cung cấp publisher kết quả để handler xử lý. Controller trả `Mono<Person>`; response writer/encoder ghi JSON sau khi publisher phát dữ liệu.

Thử:

~~~bash
./gradlew bootRun
~~~

~~~bash
curl -i http://localhost:8080/people/echo \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data '{"name":"Lan","age":24}'
~~~

Với cấu hình minh họa, body kết quả mang cùng dữ liệu:

~~~json
{"name":"Lan","age":24}
~~~

**Điểm khác MVC không nằm ở hình dạng JSON**, mà ở việc WebFlux làm việc với publisher, reactive reader/writer và server I/O. Controller **không cần và không nên** tự gọi `subscribe()` hoặc `block()` để trả body. Web runtime quản lý subscription và hoàn thiện HTTP response.

**Không sao chép hai class `Person`, hai `@SpringBootApplication` và hai starter vào cùng một package/module** rồi cho rằng cả hai stack sẽ chạy đồng thời. Hai ví dụ là hai dự án độc lập. Khi `spring-boot-starter-web` và `spring-boot-starter-webflux` cùng hiện diện, Spring Boot thường ưu tiên suy luận **Servlet MVC** theo mặc định.

## 7. Content-Type, Accept và lựa chọn bộ chuyển đổi

Hai HTTP header có vai trò khác nhau:

- **Content-Type:** thông báo kiểu dữ liệu **client gửi lên**. Khi đọc `@RequestBody`, framework tìm converter/reader hỗ trợ tổ hợp kiểu Java và request media type.
- **Accept:** thông báo những kiểu nội dung **client sẵn sàng nhận**. Khi ghi response, framework thương lượng media type dựa trên mapping `produces`, Accept và khả năng của converter/writer.

Ví dụ:

~~~http
POST /people/echo
Content-Type: application/json
Accept: application/json
~~~

Khi thay request Content-Type thành `text/plain` trong khi controller chỉ có `consumes=application/json`, thường nhận **HTTP 415 Unsupported Media Type**. Nếu client chỉ gửi `Accept: text/plain` trong khi endpoint khai báo `produces=application/json`, thường nhận **HTTP 406 Not Acceptable**. Chúng là vấn đề lựa chọn media type/mapping, **không chứng minh Jackson bị mất**.

| Trạng thái | Nguyên nhân thường gặp |
|---|---|
| 400 Bad Request | JSON hỏng, body không decode được, binding/validation lỗi |
| 404 Not Found | Không tìm thấy URL/handler phù hợp |
| 405 Method Not Allowed | URL có route nhưng method không phù hợp |
| 406 Not Acceptable | Response media type không thỏa Accept/produces |
| 415 Unsupported Media Type | Request Content-Type không thỏa consumes/reader |
| 413 Content Too Large | Giới hạn kích thước HTTP body từ server/proxy |
| 500 hoặc error handler khác | Lỗi encode, xử lý hoặc exception không được xử lý |

Với body lỗi, **MVC** thường phát exception như `HttpMessageNotReadableException`; **WebFlux** thường có `ServerWebInputException` hoặc exception codec liên quan. Response cuối cùng phụ thuộc error handling và Spring Boot configuration, nên không nên áp một class exception duy nhất cho mọi bản lỗi.

## 8. Tùy chỉnh trong MVC mà không làm mất converters mặc định

Với Spring MVC, khi muốn **thêm hoặc điều chỉnh** danh sách đã có, cách an toàn thường là `WebMvcConfigurer#extendMessageConverters`:

~~~java
package demo.mvc;

import java.util.List;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.converter.HttpMessageConverter;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
class MvcConverterConfiguration implements WebMvcConfigurer {

    @Override
    public void extendMessageConverters(
            List<HttpMessageConverter<?>> converters
    ) {
        // Tại đây danh sách converter mặc định đã được chuẩn bị.
        // Nếu cần thêm định dạng riêng: converters.add(customConverter);
        // Không gọi converters.clear() chỉ để bổ sung một converter.
    }
}
~~~

Class này có thể được thêm vào dự án MVC ví dụ, nhưng **không tự đăng ký converter mới** vì đoạn trên nhằm minh họa hook không phá mặc định. Muốn thêm wire format mới, viết converter có `canRead`/`canWrite` thật sự hẹp theo Java type và media type, rồi `converters.add(...)` có chủ đích. Tránh đăng ký converter trùng bằng cả `@Bean` và `extendMessageConverters`.

### Cảnh báo về configureMessageConverters

~~~java
@Override
public void configureMessageConverters(
        List<HttpMessageConverter<?>> converters) {
    converters.add(customConverter);
}
~~~

Đây là **fragment minh họa rủi ro**, thiếu khai báo `customConverter` nên không biên dịch độc lập. Trong Spring MVC, điền danh sách ở `configureMessageConverters` có thể khiến cơ chế đăng ký converter mặc định bị bỏ qua; JSON/String/bytes có thể bị ảnh hưởng. Không dùng hook này nếu mục tiêu chỉ là thêm một phần tử.

`@EnableWebMvc` cũng là thay đổi lớn: nó cho phép quản lý cấu hình MVC chủ động hơn và khiến cấu hình MVC auto-configuration của Boot thông thường nhường chỗ. Không thêm chỉ để sửa một converter.

Nếu mục tiêu đơn thuần là JSON naming/serialization, ưu tiên `spring.jackson.*` hoặc customizer ObjectMapper phù hợp thay vì tự thay toàn bộ converter Jackson.

## 9. Tùy chỉnh trong WebFlux: ServerCodecConfigurer

WebFlux không dùng `WebMvcConfigurer#extendMessageConverters` để điều chỉnh WebFlux codecs. Điểm mở rộng tương ứng là `WebFluxConfigurer#configureHttpMessageCodecs(ServerCodecConfigurer)`.

Ví dụ chỉ tùy chỉnh giới hạn bộ nhớ buffer, giữ các default readers/writers còn lại:

~~~java
package demo.webflux;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration(proxyBeanMethods = false)
class WebFluxCodecConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer
    ) {
        configurer.defaultCodecs().maxInMemorySize(256 * 1024);
    }
}
~~~

Class cấu hình này có thể đặt cùng package với ví dụ WebFlux. Nó thiết lập giới hạn buffering tối đa **256 KiB** cho những default codecs hỗ trợ giới hạn đó, **không thay thế toàn bộ danh sách mặc định**.

Tùy phiên bản, một cấu hình property của Spring Boot 3.x cho cùng nhu cầu là:

~~~yaml
spring:
  codec:
    max-in-memory-size: 256KB
~~~

Khi property đáp ứng yêu cầu, ưu tiên property vì dễ phân biệt theo môi trường. Không đặt property và code tùy chỉnh cùng giá trị với hai mục tiêu mâu thuẫn mà không kiểm tra thứ tự áp dụng.

Nếu thực sự cần codec riêng, `ServerCodecConfigurer` có `customCodecs()` để đăng ký thêm codecs/readers/writers phù hợp. Thông thường **không nên gọi `registerDefaults(false)`** chỉ để bổ sung một codec: tắt defaults khiến JSON/text/resource codecs có thể không còn theo kỳ vọng. Khi chỉnh JSON decoder/encoder trực tiếp, cần bảo đảm cả hai hướng đọc và ghi, và kiểm tra ObjectMapper đang được dùng.

### 9.1. MVC và WebFlux không dùng cùng extension point

| Mục tiêu | Spring MVC | Spring WebFlux |
|---|---|---|
| Thêm body format tùy biến | `HttpMessageConverter` và `extendMessageConverters` | `HttpMessageReader/Writer` hoặc `Encoder/Decoder` qua `ServerCodecConfigurer.customCodecs()` |
| Giữ cấu hình mặc định | Không xóa danh sách converters; dùng hook extend | Giữ `defaultCodecs()`; đăng ký custom codecs có chọn lọc |
| Tùy chỉnh JSON đơn giản | Boot Jackson config/ObjectMapper | Boot Jackson config/ObjectMapper với default Jackson codecs |
| Giới hạn buffer body | Servlet/container và cơ chế liên quan | `maxInMemorySize` ở default codecs hoặc Boot property phù hợp |
| Xử lý body bất đồng bộ | Servlet async có cơ chế riêng | Publisher, DataBuffer và reactive codecs |

Không đăng ký một `HttpMessageConverter` của MVC rồi kỳ vọng WebFlux trên Reactor Netty tự sử dụng nó. Cũng không dùng `WebFluxConfigurer` để cấu hình các Servlet converters của ứng dụng thực sự đang chạy MVC.

## 10. Jackson: điểm chung nhưng không đồng nhất hai stack

Khi ứng dụng dùng Jackson 2 với Spring Boot 3.x, các lớp JSON thường gặp:

- MVC: `MappingJackson2HttpMessageConverter`.
- WebFlux: `Jackson2JsonDecoder` và `Jackson2JsonEncoder`.

Cả hai có thể sử dụng các quy tắc Jackson về annotation, serialization/deserialization, modules, naming strategy và date/time. Tuy nhiên, codec WebFlux còn chịu trách nhiệm làm việc với `Publisher`/`DataBuffer` và một số streaming media types; MVC converter không tự có những semantics ấy.

### 10.1. Cấu hình JSON bằng application.yml

Ví dụ muốn không xuất các property có giá trị null:

~~~yaml
spring:
  jackson:
    default-property-inclusion: non_null
~~~

Đây là thuộc tính Boot 3.x trong cấu hình tích hợp Jackson tương ứng. Khi JSON được tạo bằng ObjectMapper do Spring Boot quản lý, thay đổi có thể tác động tới cả MVC và WebFlux ở dự án tương ứng mà không phải thay toàn bộ converter/codec.

Cần phân biệt rõ:
- Null property bị bỏ khi **serialize**, không có nghĩa client gửi JSON thiếu field sẽ được validate tự động.
- Các Java record components, bean validation, Kotlin nullability và giá trị primitive có các quy tắc khác nhau.
- Một `ObjectMapper` tự khởi tạo bằng `new ObjectMapper()` có thể không nhận module/setting đã đăng ký trong Boot.

Nếu yêu cầu chỉ áp dụng cho một DTO, có thể dùng annotation Jackson trên DTO thay vì đổi quy tắc JSON toàn ứng dụng.

### 10.2. Jackson2ObjectMapperBuilderCustomizer

Ví dụ Spring Boot 3.x, Jackson 2:

~~~java
import com.fasterxml.jackson.annotation.JsonInclude;

import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class JsonConfiguration {

    @Bean
    Jackson2ObjectMapperBuilderCustomizer omitNullFields() {
        return builder -> builder.serializationInclusion(
                JsonInclude.Include.NON_NULL
        );
    }
}
~~~

Đây là class cấu hình có thể được package scan trong một ứng dụng đã có Jackson và Spring Boot auto-configuration phù hợp. Mục đích là cấu hình **cách xây dựng ObjectMapper**, không phải xóa converter/codec rồi tái tạo chúng bằng mapper rỗng.

Không giả định mọi ObjectMapper trên classpath đều đi qua Boot builder; thư viện bên thứ ba có thể khởi tạo mapper riêng. Khi nâng major version Spring Boot/Spring Framework hoặc thay JSON library, phải kiểm tra lại tên API và cách auto-config thực tế.

## 11. Streaming JSON: WebFlux có thêm lựa chọn

Trong API trả nhiều phần tử, có khác biệt giữa:

- Một JSON array hoàn chỉnh:
  
~~~json
[{"id":1},{"id":2},{"id":3}]
~~~

- Một dòng JSON cho mỗi phần tử, theo kiểu NDJSON:

~~~text
{"id":1}
{"id":2}
{"id":3}
~~~

Trong WebFlux, có thể trả `Flux<Event>` và đặt media type dạng streaming như `application/x-ndjson` khi encoder hỗ trợ:

~~~java
@GetMapping(
        path = "/events",
        produces = MediaType.APPLICATION_NDJSON_VALUE
)
Flux<Event> streamEvents() {
    return eventService.events();
}
~~~

Đây là **fragment WebFlux**, cần định nghĩa `Event`, `eventService` và imports. Endpoint có thể encode từng phần tử thành các dòng JSON khi producer phát signal, thay vì nhất thiết gom toàn bộ thành một JSON array trong bộ nhớ.

Tuy nhiên, streaming vẫn bị chi phối bởi HTTP/proxy buffering, flush behavior, rate downstream, serialization cost và cơ chế backpressure. Không hứa mỗi `onNext` luôn tương ứng một TCP packet tới client.

Trong MVC, ứng dụng cũng có thể stream response bằng những API Servlet như `StreamingResponseBody` hoặc `ResponseBodyEmitter` phù hợp. Vì vậy, khác biệt không phải “MVC tuyệt đối không streaming” mà là **WebFlux dùng reactive publisher/codec integration làm mô hình chính**.

## 12. Buffer limits, DataBufferLimitException và request lớn

Một điểm quan trọng trong WebFlux là **bộ nhớ để gom body**. Nếu JSON object cần được aggregate để deserialize và kích thước vượt ngưỡng của codec, ứng dụng có thể gặp `DataBufferLimitException` hoặc lỗi liên quan. Tùy error handling, HTTP response có thể khác nhau; không mặc định luôn 413 hay 500.

Cách xử lý tốt:

1. Xác định body nào thực sự cần aggregate và body nào nên stream.
2. Đặt giới hạn buffer phù hợp với yêu cầu nghiệp vụ và container memory.
3. Đặt giới hạn kích thước request ở proxy/ingress/server nếu cần.
4. Với upload lớn, cân nhắc streaming/multipart và cơ chế lưu trữ có giới hạn.
5. Theo dõi latency, heap/direct memory, GC và lỗi codec.
6. Không tăng `maxInMemorySize` vô hạn chỉ để chữa lỗi mà chưa phân tích nguyên nhân.

**DataBuffer cần quản lý vòng đời:** khi viết custom decoder/reader thao tác trực tiếp với pooled buffers, phải tuân theo API giữ/giải phóng buffer phù hợp. Không giữ `DataBuffer` qua thời gian dài hoặc bỏ qua release khi đã chiếm quyền sở hữu. Dùng những codec của framework khi có thể để giảm rủi ro memory leak.

Với MVC, vấn đề kích thước body cũng tồn tại, nhưng điểm cấu hình có thể nằm tại Servlet container, multipart settings, HTTP client/proxy hoặc custom converter; không thể dùng một property WebFlux như `spring.codec.max-in-memory-size` để thay cho mọi giới hạn Servlet.

## 13. Blocking I/O: tại sao codec WebFlux không tự làm mọi thứ non-blocking?

WebFlux dùng non-blocking I/O khi runtime/client và pipeline hỗ trợ. Nhưng nếu một JSON encoder gọi hàm tính toán quá nặng hoặc một custom decoder thực hiện JDBC đồng bộ, đoạn code đó **vẫn chặn thread** mà nó chạy trên.

Không nên đặt trong một WebFlux controller:

~~~java
@PostMapping("/bad")
Person bad(@RequestBody Person input) {
    blockingLegacyRepository.save(input);
    return input;
}
~~~

Đây là **fragment chống-pattern** nếu chạy trực tiếp trên event loop, không độc lập biên dịch vì thiếu repository/định nghĩa class. Một HTTP codec có reactive API không tự biến JDBC thành non-blocking.

Nếu phải giữ API blocking, có thể cô lập bằng deferred source:

~~~java
Mono<Person> result = Mono.fromCallable(() ->
        blockingLegacyRepository.saveAndReturn(input)
).subscribeOn(Schedulers.boundedElastic());
~~~

Đây là fragment cần `blockingLegacyRepository`, `input` và imports; `boundedElastic` có giới hạn threads/queue, không phải I/O non-blocking thật sự. Khi đa số nghiệp vụ dùng JDBC/JPA blocking, **Spring MVC có thể đơn giản và phù hợp hơn**. Không chọn WebFlux chỉ vì muốn code có `Mono`.

Với reactive end-to-end, cân nhắc `WebClient` cho HTTP và driver/reactive data access thích hợp như R2DBC khi hệ thống hỗ trợ. Tiếp tục giới hạn connection pool, concurrency, timeout và retry; reactive I/O không làm hệ thống phụ thuộc có throughput vô hạn.

## 14. Kiểm thử để phát hiện lỗi converter/codec

Một bài test có giá trị cần kiểm tra **cả hai chiều**: request JSON đi vào controller đúng kiểu và response JSON có đúng media type/body. Không chỉ kiểm tra endpoint khởi động được.

### 14.1. MVC với MockMvc

Trong **dự án MVC ví dụ**, thêm:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Tạo file **src/test/java/demo/mvc/MvcJsonApplicationTest.java**:

~~~java
package demo.mvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class MvcJsonApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void jsonIsReadAndWritten() throws Exception {
        String payload = """
                {"name":"Lan","age":24}
                """;

        mvc.perform(post("/people/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content(payload))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.name").value("Lan"))
           .andExpect(jsonPath("$.age").value(24));
    }
}
~~~

Với Java 17, text block `"""` trên là chuỗi JSON hợp lệ kèm newline cuối; Jackson chấp nhận whitespace cuối trong JSON request. Dùng text block tránh lỗi escape dấu nháy. `MockMvc` chạy mô hình MVC mà không mở TCP server; để test connector/network, cần bài integration test khác.

### 14.2. WebFlux với WebTestClient

Trong **dự án WebFlux riêng**, thêm test starter:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Tạo file **src/test/java/demo/webflux/WebFluxJsonApplicationTest.java**:

~~~java
package demo.webflux;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class WebFluxJsonApplicationTest {

    @Autowired
    WebTestClient client;

    @Test
    void jsonIsReadAndWritten() {
        client.post()
              .uri("/people/echo")
              .bodyValue(Map.of("name", "Lan", "age", 24))
              .exchange()
              .expectStatus().isOk()
              .expectHeader().contentTypeCompatibleWith(
                      org.springframework.http.MediaType.APPLICATION_JSON)
              .expectBody()
              .jsonPath("$.name").isEqualTo("Lan")
              .jsonPath("$.age").isEqualTo(24);
    }
}
~~~

Ở chế độ RANDOM_PORT với reactive web application, Spring Boot Test có thể cung cấp một `WebTestClient` được cấu hình để gọi HTTP server thực theo cơ chế test của phiên bản đang dùng. Nếu dự án có thêm cấu hình custom test clients thì cần điều chỉnh injection phù hợp. Sử dụng Map trong `bodyValue` để Spring WebFlux chọn JSON writer mà không phải viết một chuỗi JSON escape thủ công.

Lệnh test cho cả hai dự án:

~~~bash
./gradlew test
~~~

Nếu test JSON của MVC fail sau khi đăng ký custom `HttpMessageConverter`, kiểm tra `configureMessageConverters` có vô tình thay default không. Nếu WebFlux fail sau khi cấu hình custom codec, kiểm tra `ServerCodecConfigurer`, `registerDefaults`, Jackson dependencies và media type.

**Kiểm thử âm tính nên có:** `Content-Type: text/plain` tới endpoint chỉ consume JSON (thường 415), `Accept: text/plain` khi endpoint chỉ produce JSON (thường 406), JSON sai cấu trúc hoặc không khớp DTO (thường 400), và body quá lớn theo cấu hình giới hạn.

## 15. Lỗi phổ biến và cách chẩn đoán

**Lỗi 1 — Nghĩ HttpMessageConverter dùng cho cả WebFlux Reactor Netty.** Đây là cơ chế của MVC Servlet stack. Với WebFlux, cấu hình `HttpMessageReader`/`HttpMessageWriter` và encoders/decoders.

**Lỗi 2 — Có Mono trong controller nên tưởng server đang reactive.** Khi cùng có `spring-boot-starter-web` và `spring-boot-starter-webflux`, Boot thường suy luận MVC. Kiểm tra dependency và loại ApplicationContext thực.

**Lỗi 3 — Dùng configureMessageConverters để thêm một converter đơn giản.** Danh sách mặc định có thể bị bỏ qua. Ưu tiên `extendMessageConverters` hoặc cơ chế bean Boot phù hợp, kiểm thử JSON/String/bytes.

**Lỗi 4 — Tắt default codecs để đăng ký custom.** Dùng `registerDefaults(false)` có thể khiến JSON, text, resource không hoạt động theo kỳ vọng. Chỉ tắt khi chủ động cấu hình toàn bộ danh sách.

**Lỗi 5 — Converter/codec có media type quá rộng.** Một custom `*/*` hoặc `Object` decoder ở vị trí ưu tiên cao dễ chiếm những payload không dành cho nó. Giới hạn kiểu dữ liệu/media type theo wire format.

**Lỗi 6 — Thay Jackson ObjectMapper bằng new ObjectMapper() không kiểm soát.** Có thể mất modules, Java time, naming/serialization settings do Boot cung cấp. Dùng cấu hình Jackson/Boot-managed mapper khi phù hợp.

**Lỗi 7 — Nhầm Content-Type và Accept.** Content-Type quyết định cách đọc request body; Accept/produces quyết định response format. 415 và 406 có nguyên nhân khác nhau.

**Lỗi 8 — Tăng WebFlux maxInMemorySize vô hạn.** Có thể tăng heap/direct memory và che vấn đề upload/JSON lớn. Chọn streaming hoặc giới hạn kích thước có chủ đích.

**Lỗi 9 — Viết custom reactive decoder mà gọi JDBC hoặc block().** Codec reactive không tự giải phóng event loop khi code bên trong blocking. Giữ codec chuyên trách chuyển đổi bytes ↔ object; gọi DB ở service với client phù hợp.

**Lỗi 10 — Viết custom DataBuffer codec thiếu release.** Khi quản lý pooled buffers sai có thể gây leak. Dùng abstraction framework hoặc tuân thủ ownership/lifecycle của buffer.

**Lỗi 11 — Test chỉ kiểm tra JSON output.** Có thể mất khả năng đọc body request. Test POST echo để xác nhận cả hai chiều, và regression cho text/format cũ.

**Lỗi 12 — Giả định Jackson JSON encoder luôn stream từng object như NDJSON.** Streaming phụ thuộc media type, codec, publisher và proxy flush/buffering. Phải thử bằng client hỗ trợ streaming.

## 16. Checklist lựa chọn và triển khai

1. Xác định web stack thực: MVC Servlet hay WebFlux Reactive, tránh suy luận từ tên controller hoặc việc import Mono.
2. Với MVC, tìm hiểu `HttpMessageConverter`, `canRead`/`canWrite`, media type và thứ tự converter.
3. Với WebFlux, nắm `HttpMessageReader/Writer`, `Encoder/Decoder`, `DataBuffer`, reactive publisher và codec selection.
4. Dùng JSON serializer như Jackson theo cấu hình Boot; không tự tạo mapper mới khi chỉ cần một quy tắc JSON.
5. Nếu chỉ thêm định dạng ở MVC, ưu tiên `extendMessageConverters` thay vì thay toàn bộ default list.
6. Nếu thêm WebFlux codec, dùng `ServerCodecConfigurer.customCodecs()` và giữ defaults, trừ khi cố ý quản lý toàn bộ.
7. Cấu hình giới hạn buffer và payload size phù hợp, chú ý DataBufferLimitException khi aggregate body lớn.
8. Không đưa JDBC, HTTP blocking, CPU work quá nặng vào Netty event loop chỉ vì code nằm trong reactive pipeline.
9. Kiểm tra content negotiation: Content-Type, Accept, consumes, produces; đừng chẩn đoán 415/406 như một lỗi duy nhất.
10. Test JSON POST echo ở cả MVC và WebFlux; bổ sung test 400/415/406 và body quá lớn.
11. Với streaming NDJSON/Flux, đo memory, flush, latency, backpressure và proxy buffering bằng HTTP client thật.
12. Khi nâng major version, đối chiếu lại API Jackson/Spring Boot và những default codecs được tự cấu hình.

**Ghi nhớ:** `HttpMessageConverter` là ranh giới chuyển đổi body ở **Spring MVC Servlet**, còn **Spring WebFlux** dùng `HttpMessageReader`/`HttpMessageWriter` cùng `Encoder`/`Decoder` trong một pipeline reactive. Cùng một JSON body có thể tạo cùng DTO và response, nhưng **cơ chế I/O, buffering, streaming và điểm tùy chỉnh khác nhau**. Giữ defaults, cấu hình JSON ở nơi phù hợp, và regression test cả chiều đọc lẫn ghi để tránh làm hỏng hợp đồng HTTP hiện có.