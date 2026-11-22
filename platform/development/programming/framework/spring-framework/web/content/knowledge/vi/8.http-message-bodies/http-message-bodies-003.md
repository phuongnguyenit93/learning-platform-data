# Cấu hình bộ chuyển đổi HTTP: thay thế mặc định hay mở rộng danh sách trong Spring MVC

## 1. Mục tiêu và bối cảnh

Trong Spring MVC, khi controller nhận một request JSON rồi trả về JSON, việc biến **bytes của HTTP body** thành Java object và ngược lại thường được thực hiện bởi `HttpMessageConverter`. Cấu hình sai danh sách converter có thể khiến endpoint trước đó chạy được bất ngờ trả **415 Unsupported Media Type** hoặc **406 Not Acceptable**. Câu hỏi trọng tâm của bài là: **khi nào nên thay toàn bộ converter mặc định và khi nào chỉ cần mở rộng danh sách đang có?**

Sau bài này, bạn sẽ:
- Hiểu nơi Spring MVC dùng `HttpMessageConverter`, cách chọn converter khi đọc và ghi body, vai trò của `Content-Type`, `Accept` và thứ tự trong danh sách.
- Phân biệt `WebMvcConfigurer#configureMessageConverters` với `extendMessageConverters` ở **Spring Framework 6.x**; hiểu khác biệt giữa Spring MVC thông thường và **Spring Boot 3.x**.
- Triển khai một converter tự tạo, thêm vào danh sách mà vẫn giữ JSON mặc định, và kiểm chứng qua controller, `curl` và `MockMvc`.
- Biết lúc nào nên cấu hình Jackson/`ObjectMapper`, dùng bean converter của Spring Boot hoặc cố ý thay thế toàn bộ; tránh nhầm với converter của form/query parameter.

**Phiên bản cố định để tránh nhầm API:** mã minh họa và chữ ký `configureMessageConverters(List<HttpMessageConverter<?>>)` / `extendMessageConverters(List<HttpMessageConverter<?>>)` ở đây áp dụng cho **Spring Framework 6.x / Spring Boot 3.x, Java 17+**. Từ Spring Framework 7, API cấu hình đã phát triển theo mô hình builder; không sao chép chữ ký ở đây vào dự án 7.x mà không đối chiếu tài liệu phiên bản đang dùng.

## 2. Converter được gọi ở bước nào?

Hình dung hai request:

~~~http
POST /api/greetings/json HTTP/1.1
Host: localhost:8080
Content-Type: application/json
Accept: application/json

{"text":"hello"}
~~~

~~~http
POST /api/greetings/custom HTTP/1.1
Host: localhost:8080
Content-Type: application/vnd.demo.uppercase
Accept: application/vnd.demo.uppercase

hello
~~~

Ở ví dụ đầu, Spring MVC có thể dùng converter Jackson để đọc body JSON thành object `Greeting` và viết object thành JSON. Ở ví dụ thứ hai, ta sẽ tự tạo converter đọc dạng text của media type riêng và ghi ra chữ hoa.

Luồng xử lý thường gặp:

1. `DispatcherServlet` định tuyến request đến handler.
2. Với tham số `@RequestBody` (hoặc part của `@RequestPart` cần chuyển payload), Spring MVC tìm converter có khả năng **đọc** kiểu Java đích cùng `Content-Type`.
3. Handler xử lý đối tượng đã đọc.
4. Với `@ResponseBody`, `@RestController`, `ResponseEntity<T>`, Spring MVC chọn converter có khả năng **ghi** kiểu kết quả với media type được đàm phán theo `Accept`, `produces` và cấu hình.
5. Converter dùng luồng HTTP để đọc/ghi bytes thực tế.

Giao diện `HttpMessageConverter<T>` có các hành vi như `canRead`, `canWrite`, `read`, `write` và các media type được hỗ trợ. Một converter có thể làm được chiều đọc, chiều ghi hoặc cả hai, tùy implementation.

`Content-Type` mô tả **body được gửi đến**; `Accept` mô tả **dạng phản hồi client chấp nhận**. `consumes` và `produces` trên handler ràng buộc route được chọn. Chúng không tự tạo converter và không bảo đảm dữ liệu thực sự parse được.

Một vài converter quen thuộc (khả dụng thực tế phụ thuộc classpath và cấu hình):

| Converter | Công dụng |
| --- | --- |
| `MappingJackson2HttpMessageConverter` | JSON sang/từ Java object qua Jackson (Framework 6.x) |
| `StringHttpMessageConverter` | Body chuỗi văn bản |
| `ByteArrayHttpMessageConverter` | Đọc/ghi mảng `byte[]` |
| `ResourceHttpMessageConverter` | Làm việc với `Resource` |
| `FormHttpMessageConverter` hoặc `AllEncompassingFormHttpMessageConverter` | Xử lý form data và một số trường hợp ghi multipart |
| Converter XML | JSON/XML theo thư viện liên quan có trong classpath |

Đây là cơ chế của **Spring MVC Servlet stack**, không phải `HttpMessageReader`/`HttpMessageWriter` trong Spring WebFlux.

## 3. Hai hook của `WebMvcConfigurer`: điểm khác biệt cốt lõi

Trong Spring Framework 6.x:

~~~java
public interface WebMvcConfigurer {
    default void configureMessageConverters(
            List<HttpMessageConverter<?>> converters) {}

    default void extendMessageConverters(
            List<HttpMessageConverter<?>> converters) {}
}
~~~

Đoạn trên là **mô phỏng chữ ký của hai method**, không phải toàn bộ định nghĩa thật của interface.

### 3.1. `configureMessageConverters`: khai báo danh sách từ đầu

Trong cấu hình **Spring MVC thông thường**, danh sách truyền vào ban đầu rỗng. Nếu các cấu hình `configureMessageConverters` điền converter vào danh sách, quá trình **tự động đăng ký danh sách mặc định của framework sẽ không diễn ra theo cơ chế thông thường**. Bạn phải bảo đảm mọi định dạng mà hệ thống cần đều có converter phù hợp.

Ví dụ dưới đây chỉ minh họa **phương án thay thế** cho Spring MVC thuần. **Đừng thêm class này vào dự án thực hành ở phần 5**:

~~~java
package com.example.demo.replace;

import java.util.List;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.converter.HttpMessageConverter;
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class ReplaceConvertersConfig implements WebMvcConfigurer {

    @Override
    public void configureMessageConverters(
            List<HttpMessageConverter<?>> converters) {
        converters.add(new MappingJackson2HttpMessageConverter());
    }
}
~~~

Nếu danh sách hiệu lực thực tế chỉ có converter JSON, các chức năng vốn dựa vào `StringHttpMessageConverter` hoặc `ByteArrayHttpMessageConverter` có thể ngừng hoạt động. Phải chủ động đăng ký đủ converter khác khi chọn cách thay thế; đừng chỉ sửa một lỗi JSON rồi vô tình bỏ mất hỗ trợ text, bytes, form, XML hoặc các kiểu body khác.

**Ngoại lệ quan trọng của Spring Boot:** Spring Boot 3.x tự cấu hình converter và bổ sung các bean `HttpMessageConverter` theo cơ chế `HttpMessageConverters`. Vì thế không suy diễn máy móc rằng thêm một converter trong `configureMessageConverters` sẽ làm mất *tất cả* converter trong ứng dụng Boot. Kết quả hiệu lực phụ thuộc Boot auto-configuration và các `WebMvcConfigurer` khác. Khi cần một converter bổ sung mà vẫn giữ hành vi Boot, cách dễ dự đoán hơn là `extendMessageConverters` hoặc cơ chế đăng ký converter của Boot.

### 3.2. `extendMessageConverters`: bổ sung hoặc điều chỉnh ở cuối

Hook này nhận danh sách đã được cấu hình (gồm converter mặc định, hoặc danh sách do các config khác thiết lập) để bạn **thêm, xóa, sắp thứ tự hay tinh chỉnh**:

~~~java
@Configuration
public class ExtendConvertersConfig implements WebMvcConfigurer {

    @Override
    public void extendMessageConverters(
            List<HttpMessageConverter<?>> converters) {
        converters.add(0, new UppercaseGreetingConverter());
    }
}
~~~

Đây là minh họa ở dạng class: cần các import `Configuration`, `WebMvcConfigurer`, `HttpMessageConverter` và class `UppercaseGreetingConverter` ở cùng project. Ứng dụng hoàn chỉnh ở phần 5 sẽ có đầy đủ file.

- `add(0, ...)` đưa converter mới lên **đầu danh sách**, để nó có cơ hội được xét trước nếu nhiều converter cùng hỗ trợ kiểu và media type.
- `add(...)` ở cuối thường là lựa chọn ít gây ảnh hưởng hơn khi định dạng được thêm rất riêng biệt.
- Nếu converter mới hỗ trợ quá rộng (`*/*`, `Object.class`), cho nó đứng đầu có thể khiến JSON/text sẵn có bị “cướp” bởi converter mới.
- `extend` **không bảo đảm giữ mặc định** nếu chính bạn gọi `converters.clear()`, `removeIf(...)` hoặc sửa converter hiện có theo cách làm mất khả năng đọc/ghi. Tên method không tự bảo vệ khỏi thay đổi phá vỡ tương thích.

| Khía cạnh | `configureMessageConverters` | `extendMessageConverters` |
| --- | --- | --- |
| Khi được gọi trong chu trình MVC 6.x | Giai đoạn cấu hình danh sách converter | Sau cấu hình / bổ sung mặc định |
| Mục đích phổ biến | Chủ động kiểm soát bộ converter sẽ dùng | Giữ và tùy chỉnh danh sách đã có |
| Với Spring MVC thuần | Thêm converter thường vô hiệu hóa bước đăng ký default | Mặc định được lập trước khi mở rộng nếu cần |
| Rủi ro | Bỏ sót khả năng đọc/ghi cũ | Thứ tự xung đột hoặc sửa/xóa sai converter |
| Gợi ý trong Spring Boot 3.x | Cần xét tương tác Boot auto-config | Thường tiện hơn khi chỉ cần bổ sung |
| Nên kiểm chứng | Danh sách converter hiệu lực và nhiều media type | Danh sách/thứ tự, JSON cũ và media type mới |

### 3.3. Khi nào cố ý thay thế toàn bộ?

Chỉ cân nhắc chủ động thay bộ mặc định khi bạn kiểm soát rõ mọi định dạng mà ứng dụng được phép trao đổi (ví dụ giao thức API chuyên biệt hoặc môi trường hạn chế). Khi đó cần kiểm thử đầy đủ các đường `@RequestBody`, `@ResponseBody`, `ResponseEntity`, exception response, file/resource, multipart/form, text và JSON đang được dùng.

Với nhu cầu thường gặp như thêm một media type, sửa JSON naming strategy, thay một serializer hoặc thêm hỗ trợ loại payload mới, bạn **không cần phá danh sách mặc định**.

## 4. Spring MVC thuần khác Spring Boot như thế nào?

### Cấu hình MVC thuần

Với cấu hình Spring MVC bật bằng `@EnableWebMvc`, Spring Framework đăng ký các thành phần hạ tầng MVC và cung cấp tập converter mặc định dựa trên thư viện có sẵn. `configureMessageConverters` cho bạn chỉ định danh sách riêng, còn `extendMessageConverters` cho phép can thiệp sau bước cấu hình. Nếu dùng cả hai và `configure` đã điền converter, `extend` thấy danh sách do config tạo ra; không được giả định default đã được giữ.

### Spring Boot 3.x

`spring-boot-starter-web` thường đã có Jackson và auto-configuration phục vụ JSON. Spring Boot thu thập các bean `HttpMessageConverter`, bổ sung/ghi đè một số converter mặc định, và cung cấp `HttpMessageConverters` để quản lý tổ hợp. Những đường cấu hình thường dùng:

1. Giữ auto-configuration, tạo bean converter riêng khi cần một converter thêm.
2. Dùng `WebMvcConfigurer#extendMessageConverters` khi cần kiểm soát vị trí hoặc tinh chỉnh danh sách có sẵn.
3. Với JSON, ưu tiên `spring.jackson.*`, bean `Jackson2ObjectMapperBuilderCustomizer`, hoặc Jackson module / annotation riêng cho DTO nếu chỉ muốn thay một phần serialization.
4. Khi cần toàn quyền MVC, có thể chọn `@EnableWebMvc` hoặc kế thừa cấu hình MVC chuyên sâu. **Lựa chọn đó làm Spring Boot bỏ qua phần đáng kể Web MVC auto-configuration**, nên chỉ dùng khi đã chủ động quản lý hệ quả.

Không nên thêm `@EnableWebMvc` vào class `WebMvcConfigurer` của ứng dụng Spring Boot thông thường chỉ để đăng ký một converter.

**Lưu ý phiên bản:** các class `HttpMessageConverters` và cơ chế builder/configuration được chỉnh sửa theo thế hệ Spring Boot/Framework. Khi chuyển từ Boot 3 lên Boot 4/Framework 7, hãy kiểm tra Javadoc phiên bản tương ứng thay vì giữ nguyên import API 6.x.

## 5. Thực hành: thêm media type riêng mà JSON vẫn hoạt động

Trong bài này, ta xây dựng media type `application/vnd.demo.uppercase`. Client gửi text `hello`; controller nhận object `Greeting`, trả lại cùng object; converter ghi body `HELLO`. Song song, endpoint JSON mặc định tiếp tục đọc và ghi `{"text":"hello"}`.

Tạo dự án bằng Spring Initializr với **Spring Boot 3.x**, **Java 17+**, **Maven**, dependency **Spring Web**. Thêm **Spring Boot Starter Test** để chạy phần MockMvc. Không tạo thêm class `ReplaceConvertersConfig` ở phần 3.

Cấu trúc file:

~~~text
src/main/java/com/example/demo/DemoApplication.java
src/main/java/com/example/demo/Greeting.java
src/main/java/com/example/demo/UppercaseGreetingConverter.java
src/main/java/com/example/demo/ConverterConfig.java
src/main/java/com/example/demo/GreetingController.java
src/test/java/com/example/demo/GreetingControllerTest.java
~~~

### 5.1. Điểm khởi động

**`src/main/java/com/example/demo/DemoApplication.java`**

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

### 5.2. Kiểu dữ liệu

**`src/main/java/com/example/demo/Greeting.java`**

~~~java
package com.example.demo;

public record Greeting(String text) {
}
~~~

Jackson đi kèm Starter Web trong Boot 3.x hỗ trợ record này với định dạng JSON có property `text`.

### 5.3. Viết converter với media type giới hạn

**`src/main/java/com/example/demo/UppercaseGreetingConverter.java`**

~~~java
package com.example.demo;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

import org.springframework.http.HttpInputMessage;
import org.springframework.http.HttpOutputMessage;
import org.springframework.http.MediaType;
import org.springframework.http.converter.AbstractHttpMessageConverter;

public class UppercaseGreetingConverter
        extends AbstractHttpMessageConverter<Greeting> {

    public static final String MIME = "application/vnd.demo.uppercase";

    public UppercaseGreetingConverter() {
        super(MediaType.parseMediaType(MIME));
    }

    @Override
    protected boolean supports(Class<?> clazz) {
        return Greeting.class.equals(clazz);
    }

    @Override
    protected Greeting readInternal(
            Class<? extends Greeting> clazz,
            HttpInputMessage inputMessage) throws IOException {

        byte[] body = inputMessage.getBody().readAllBytes();
        String text = new String(body, StandardCharsets.UTF_8);
        return new Greeting(text);
    }

    @Override
    protected void writeInternal(
            Greeting greeting,
            HttpOutputMessage outputMessage) throws IOException {

        String upper = greeting.text().toUpperCase(Locale.ROOT);
        outputMessage.getBody()
                .write(upper.getBytes(StandardCharsets.UTF_8));
    }
}
~~~

Các chi tiết cần hiểu:

- `AbstractHttpMessageConverter<Greeting>` hiện thực phần lớn hợp đồng `HttpMessageConverter`, giúp tập trung vào kiểu Java được hỗ trợ, đọc body và ghi body.
- `supports` chỉ chấp nhận class `Greeting`; constructor chỉ đăng ký **một** media type riêng. Converter không tự giành dữ liệu JSON (`application/json`) của Jackson.
- `readInternal` nhận bytes UTF-8 của HTTP request và tạo `Greeting`; `writeInternal` tạo chữ hoa với `Locale.ROOT`, trả bytes UTF-8. Không tự nối thêm newline.
- `readAllBytes()` dùng để giữ ví dụ đơn giản; **trong production** cần giới hạn dung lượng request ở server/proxy trước khi nhận body hoặc dùng streaming nếu thích hợp. Ví dụ này không dành cho payload lớn.
- Dữ liệu đầu vào được coi là text UTF-8 do **hợp đồng media type riêng của ví dụ**. Converter thực tế nên kiểm tra charset và quy tắc encoding, thông báo lỗi khi dữ liệu không hợp lệ.
- Đối với kiểu có nhiều polymorphic subtype, `supports(Greeting.class.equals(clazz))` có thể quá chặt; đây là lựa chọn có chủ đích để tránh converter bắt nhầm kiểu khác.

### 5.4. Mở rộng thay vì thay danh sách mặc định

**`src/main/java/com/example/demo/ConverterConfig.java`**

~~~java
package com.example.demo;

import java.util.List;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.converter.HttpMessageConverter;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class ConverterConfig implements WebMvcConfigurer {

    @Override
    public void extendMessageConverters(
            List<HttpMessageConverter<?>> converters) {
        converters.add(0, new UppercaseGreetingConverter());
    }
}
~~~

Chỉ dùng `extendMessageConverters`. Ta thêm converter riêng vào danh sách hiệu lực mà không xóa cấu hình converter JSON đã có. Với hỗ trợ media type hẹp và class hẹp, `add(0, ...)` an toàn trong phạm vi mẫu: converter chỉ cạnh tranh khi cả **kiểu Java lẫn media type** phù hợp. Trong hệ thống thực, cần đánh giá thứ tự và media type của các converter khác trước khi chọn index.

### 5.5. Controller kiểm tra cả định dạng riêng và JSON

**`src/main/java/com/example/demo/GreetingController.java`**

~~~java
package com.example.demo;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/greetings")
public class GreetingController {

    @PostMapping(
            path = "/custom",
            consumes = UppercaseGreetingConverter.MIME,
            produces = UppercaseGreetingConverter.MIME)
    public Greeting custom(@RequestBody Greeting greeting) {
        return greeting;
    }

    @PostMapping(
            path = "/json",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Greeting json(@RequestBody Greeting greeting) {
        return greeting;
    }
}
~~~

Handler `/custom` cần converter riêng ở cả chiều request và response; handler `/json` cần converter Jackson của Boot. Nếu thay converter mặc định không cẩn thận, test JSON sẽ phát hiện hồi quy.

## 6. Chạy và đọc kết quả HTTP

Tại thư mục dự án có `pom.xml`, chạy:

~~~bash
./mvnw spring-boot:run
~~~

Với Windows, dùng `mvnw.cmd spring-boot:run`; nếu project không có wrapper, dùng `mvn spring-boot:run` khi đã cài Maven.

Gửi body text theo media type tùy chỉnh:

~~~bash
curl -i -X POST "http://localhost:8080/api/greetings/custom"   -H "Content-Type: application/vnd.demo.uppercase"   -H "Accept: application/vnd.demo.uppercase"   --data-binary "hello"
~~~

**Kết quả kỳ vọng:** status **200 OK**, header response có `Content-Type` tương thích `application/vnd.demo.uppercase` và **body chính xác**:

~~~text
HELLO
~~~

Code `writeInternal` không thêm ký tự xuống dòng vào HTTP body; đoạn Markdown phía trên có xuống dòng để hiển thị, không hàm ý một newline của response.

Kiểm chứng JSON mặc định còn chạy:

~~~bash
curl -i -X POST "http://localhost:8080/api/greetings/json"   -H "Content-Type: application/json"   -H "Accept: application/json"   --data-binary '{"text":"hello"}'
~~~

**Kết quả kỳ vọng:** **200 OK** và JSON body tương đương:

~~~json
{"text":"hello"}
~~~

Thứ tự các property JSON không cần cố định. Nếu chạy trong Windows PowerShell, nên dùng `curl.exe` thay vì alias `curl`; cách escape JSON và nối dòng phải phù hợp shell. Ví dụ trên dành cho Linux/macOS/Git Bash.

### 6.1. Kiểm thử 415 và 406

Request sai `Content-Type` cho endpoint custom:

~~~bash
curl -i -X POST "http://localhost:8080/api/greetings/custom"   -H "Content-Type: application/json"   -H "Accept: application/vnd.demo.uppercase"   --data-binary '{"text":"hello"}'
~~~

Kết quả điển hình: **415 Unsupported Media Type** do handler chỉ nhận `application/vnd.demo.uppercase`. Ngay cả khi ứng dụng có Jackson, `consumes` của handler vẫn là một điều kiện chọn route.

Request chấp nhận định dạng response không khớp:

~~~bash
curl -i -X POST "http://localhost:8080/api/greetings/custom"   -H "Content-Type: application/vnd.demo.uppercase"   -H "Accept: application/json"   --data-binary "hello"
~~~

Kết quả điển hình: **406 Not Acceptable**, vì handler khai báo chỉ `produces = application/vnd.demo.uppercase`, không đáp ứng `Accept: application/json`. Nội dung lỗi có thể thay đổi theo cấu hình Spring Boot, Servlet container và `@ControllerAdvice`, nên chỉ xác nhận mã status và contract HTTP.

**Phân biệt:** 415 thường liên quan media type của **request body**; 406 liên quan media type của **response** mà client yêu cầu; 400 có thể do body có media type được chấp nhận nhưng dữ liệu không parse được thành kiểu Java.

## 7. Kiểm thử tự động bằng MockMvc

Thêm dependency `spring-boot-starter-test` trong dự án. Với Spring Boot 3.x, viết:

**`src/test/java/com/example/demo/GreetingControllerTest.java`**

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(GreetingController.class)
@Import(ConverterConfig.class)
class GreetingControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void newConverterReadsAndWritesCustomMediaType() throws Exception {
        mockMvc.perform(post("/api/greetings/custom")
                        .contentType(UppercaseGreetingConverter.MIME)
                        .accept(UppercaseGreetingConverter.MIME)
                        .content("hello"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        UppercaseGreetingConverter.MIME))
                .andExpect(content().string("HELLO"));
    }

    @Test
    void jacksonJsonStillReadsAndWrites() throws Exception {
        mockMvc.perform(post("/api/greetings/json")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content("{\"text\":\"hello\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.text").value("hello"));
    }

    @Test
    void rejectsUnsupportedRequestContentType() throws Exception {
        mockMvc.perform(post("/api/greetings/custom")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(UppercaseGreetingConverter.MIME)
                        .content("{\"text\":\"hello\"}"))
                .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void rejectsUnacceptableResponseMediaType() throws Exception {
        mockMvc.perform(post("/api/greetings/custom")
                        .contentType(UppercaseGreetingConverter.MIME)
                        .accept(MediaType.APPLICATION_JSON)
                        .content("hello"))
                .andExpect(status().isNotAcceptable());
    }
}
~~~

Chạy:

~~~bash
./mvnw test
~~~

Bốn test cần thiết vì chỉ kiểm tra endpoint tùy chỉnh thành công **không chứng minh** JSON mặc định còn chạy. Test thứ hai là phép kiểm tra hồi quy cốt lõi khi so sánh “mở rộng” với “thay thế”. `@Import(ConverterConfig.class)` đảm bảo cấu hình converter được đưa vào test slice. `@WebMvcTest` kiểm tra stack MVC bằng `MockMvc` mà không cần mở server thật.

Nếu class test nằm trong dự án đang bật Spring Security với rule xác thực/CSRF, phải cấu hình MockMvc phù hợp chính sách đó; không tắt bảo mật tùy tiện chỉ để test converter. Bài mẫu chỉ có Spring Web và Starter Test.

## 8. Thay JSON behavior mà không cần tự tạo converter mới

Nếu mục tiêu là đổi cách Jackson serialize/deserialize JSON, phương án tùy biến **Jackson** thường đơn giản hơn việc thay toàn bộ `HttpMessageConverter`. Ví dụ Spring Boot 3.x có thể cấu hình:

~~~properties
spring.jackson.serialization.indent_output=true
spring.jackson.default-property-inclusion=non_null
~~~

Lưu ý property này điều chỉnh việc thụt dòng JSON và bỏ property có giá trị null theo Jackson; không thay media type, không can thiệp converter text hay form. Khi nâng cấp, kiểm tra danh sách property được phiên bản Boot hỗ trợ.

Với logic phức tạp hơn, bạn có thể đăng ký `Jackson2ObjectMapperBuilderCustomizer` để cấu hình `ObjectMapper` do Boot xây dựng. Nếu tự tạo `MappingJackson2HttpMessageConverter` với `new ObjectMapper()`, bạn có thể làm mất cấu hình module, Java Time, mix-in, naming strategy và các cấu hình khác mà Boot/Jackson đã chuẩn bị. Khi dùng `@JsonFormat`, `@JsonProperty` hoặc serializer tùy chỉnh trên DTO, sự thay đổi còn có thể giới hạn ở một model, an toàn hơn với toàn ứng dụng.

Đôi khi bạn cần sửa một converter đang có trong `extendMessageConverters`. Ví dụ minh họa:

~~~java
@Override
public void extendMessageConverters(
        List<HttpMessageConverter<?>> converters) {
    for (HttpMessageConverter<?> candidate : converters) {
        if (candidate instanceof MappingJackson2HttpMessageConverter jackson) {
            // Đã tìm được converter Jackson.
            // Chỉ điều chỉnh cấu hình có chủ đích và đã kiểm thử.
        }
    }
}
~~~

Đây là **đoạn minh họa**, không phải class Java độc lập; cần các import và annotation/config tương ứng. Tránh mutate `ObjectMapper` được chia sẻ sau khi đã phục vụ request: nhiều cấu hình Jackson được thiết kế để xác lập lúc startup. Nếu cần thay riêng một converter, chuẩn bị mapper/cấu hình trước khi server chạy; kiểm tra side effect với những nơi cùng dùng mapper đó.

## 9. Thứ tự converter và content negotiation

Spring MVC có thể có nhiều converter cho một Java type và media type. Khi các converter cùng báo `canRead`/`canWrite`, **thứ tự đăng ký** có thể quyết định converter được chọn. Nhất là khi client gửi `Accept: */*`, converter đứng trước có khả năng được ưu tiên. Tuy nhiên chọn response còn phụ thuộc `produces`, các media type hỗ trợ, kiểu trả về và content negotiation; không phải cứ converter đầu tiên trong list là luôn thắng.

Các nguyên tắc nên tuân thủ:

- Giới hạn `supportedMediaTypes` thật hẹp cho converter tùy chỉnh (ví dụ `application/vnd.demo.uppercase`), tránh `MediaType.ALL` nếu không thực sự cần.
- Chỉ hỗ trợ đúng Java type trong `supports`, hoặc thêm điều kiện rõ cho generic type nếu triển khai `GenericHttpMessageConverter`.
- Nếu cần override converter mặc định cho cùng type/media type, sắp thứ tự có ý thức và kiểm thử **đọc lẫn ghi**; với Boot xem xét cơ chế bean/HttpMessageConverters.
- Hạn chế đặt converter generic nhận `Object` đầu danh sách; nó có thể chặn `MappingJackson2HttpMessageConverter`, trả nội dung hoặc media type sai.
- Kiểm tra cả `Content-Type` request, `Accept`, `consumes`, `produces`. Một status 406/415 không đủ để kết luận converter “bị thiếu” trước khi đối chiếu toàn bộ.
- Đừng đặt `produces` sai thực tế: controller tuyên bố JSON nhưng converter lại ghi text không phải JSON sẽ làm sai contract API.

Nếu cần xác minh trong hệ thống đang chạy, có thể xem danh sách converter được đăng ký với `RequestMappingHandlerAdapter#getMessageConverters()` sau khi context được khởi tạo; kết quả phụ thuộc auto-config và các `WebMvcConfigurer` khác. Chỉ đọc cấu hình nguồn của một class chưa đủ để biết toàn bộ danh sách hiệu lực.

## 10. Phân biệt bộ chuyển đổi HTTP body với data binding

Spring MVC có hai nhóm chuyển đổi **khác nhiệm vụ**:

| Bài toán | Cơ chế phù hợp | Ví dụ |
| --- | --- | --- |
| JSON body thành Java object | `HttpMessageConverter` | `@RequestBody Greeting body` |
| Java object thành JSON response | `HttpMessageConverter` | `@RestController` trả `Greeting` |
| JSON part trong multipart | `HttpMessageConverter` theo part | `@RequestPart("metadata") SomeDto dto` |
| Query parameter string thành `LocalDate` | `ConversionService` / `Formatter` | `@RequestParam LocalDate date` |
| Form field string thành property của model | `WebDataBinder` và conversion/formatting | `@ModelAttribute Form form` |
| Chuỗi cần trim trước khi bind form | `@InitBinder`/editor/formatter phù hợp | `WebDataBinder.registerCustomEditor(...)` |

Đừng sửa `configureMessageConverters` để xử lý `@RequestParam("date") LocalDate date`; thông thường cần `Converter<String, LocalDate>`, `Formatter` hoặc `@DateTimeFormat`. Ngược lại, một `Converter<String, String>` của conversion service không tự giải mã JSON body.

Những nhầm lẫn này đặc biệt hay xuất hiện khi controller có cả `@RequestBody` và `@RequestParam`: mỗi loại tham số có cơ chế resolution và conversion tương ứng.

## 11. Những lỗi cấu hình thường gặp

### Lỗi 1: Chỉ thêm một converter trong `configureMessageConverters` của MVC thuần

**Hiện tượng:** endpoint JSON mới hoạt động nhưng response `String`, binary, form hoặc định dạng khác hỏng.

**Nguyên nhân:** danh sách explicit làm bỏ qua bước đăng ký defaults thông thường.

**Cách sửa:** đổi sang `extendMessageConverters` nếu chỉ thêm chức năng; nếu thật sự thay thế, khai báo đầy đủ converter cần thiết và test những endpoint hiện hữu.

### Lỗi 2: Cho converter riêng hỗ trợ `*/*` và `Object.class`

**Hiện tượng:** response `application/json` đôi khi bị ghi thành text tùy chỉnh; serializer cũ không được gọi.

**Nguyên nhân:** converter tùy chỉnh bắt quá nhiều type/media type và có thứ tự ưu tiên cao.

**Cách sửa:** giới hạn `supports`, `supportedMediaTypes`, vị trí; kiểm thử JSON/text cả chiều đọc/ghi.

### Lỗi 3: Dùng `@EnableWebMvc` chỉ để thay một converter trong Spring Boot

**Hiện tượng:** cấu hình web/resource handling và nhiều MVC customizations của Boot thay đổi ngoài dự kiến.

**Nguyên nhân:** `@EnableWebMvc` chuyển ứng dụng sang quản lý MVC chủ động, làm mất đường auto-configuration MVC thông dụng.

**Cách sửa:** dùng bean `WebMvcConfigurer` đơn giản, không `@EnableWebMvc`, hoặc cơ chế converter mà Boot cung cấp.

### Lỗi 4: Gửi JSON với `Content-Type: text/plain`

**Hiện tượng:** DTO `@RequestBody` không parse được hoặc nhận status 415.

**Nguyên nhân:** converter Jackson thường nhắm các JSON media type, trong khi header tuyên bố text.

**Cách sửa:** gửi header đúng dạng `application/json` và dữ liệu JSON hợp lệ; không sửa converter thành nhận `*/*` để che lỗi client.

### Lỗi 5: Chỉ kiểm thử HTTP 200

**Hiện tượng:** API mới hoạt động, API cũ sử dụng converter mặc định khác bị hỏng sau deploy.

**Cách sửa:** có test regression cho ít nhất JSON read/write, media type mới, 415, 406; mở rộng thêm các endpoint text/bytes/form thực sự đang sử dụng.

### Lỗi 6: Nhầm lỗi validation với lỗi converter

**Hiện tượng:** request chuyển thành Java object được nhưng bị 400 do `@Valid`.

**Nguyên nhân:** converter giải mã body thành công; lỗi phát sinh ở validation sau đó.

**Cách sửa:** đọc exception và log tương ứng (ví dụ parse JSON thường phát sinh `HttpMessageNotReadableException`; lỗi validation có thể là `MethodArgumentNotValidException`), xác định tầng trước khi thay cấu hình.

### Lỗi 7: Tưởng cấu hình MVC luôn áp dụng cho RestClient hoặc WebFlux

**Hiện tượng:** một `RestClient` hoặc reactive endpoint không sử dụng converter đã thêm trong MVC.

**Nguyên nhân:** client HTTP và WebFlux có stack riêng; không giả định chúng chia sẻ danh sách converter với Spring MVC server.

**Cách sửa:** cấu hình đúng client hoặc codec reactive tương ứng và kiểm thử riêng.

## 12. Quy tắc quyết định và checklist

| Nhu cầu | Phương án nên bắt đầu |
| --- | --- |
| Chỉ thêm media type/Java type mới vào MVC | `extendMessageConverters` với converter hẹp |
| Dùng Spring Boot 3.x và có bean converter riêng | Đăng ký `HttpMessageConverter` bean theo cơ chế Boot; xem xét `HttpMessageConverters` khi cần |
| Muốn đổi JSON naming/date/null/indent | Jackson annotation, `spring.jackson.*`, customizer/ObjectMapper |
| Muốn thay converter mặc định cụ thể | Cơ chế override converter/bean của Boot hoặc `extend` với thứ tự rõ; kiểm thử |
| Cần kiểm soát toàn bộ protocol hỗ trợ trong MVC thuần | `configureMessageConverters` và đăng ký đủ converter |
| Muốn chuyển query/form field | `ConversionService`, `Formatter`, `@InitBinder`, không phải converter HTTP body |

Trước khi đưa cấu hình vào production, hãy tự kiểm tra: **(1)** framework và Boot đang dùng phiên bản nào; **(2)** danh sách converter thực tế còn hỗ trợ các media type cũ không; **(3)** converter tùy chỉnh có giới hạn type/media type đủ chặt không; **(4)** có test cả request/response và 406/415 không; **(5)** có dùng `@EnableWebMvc` ngoài ý muốn không; **(6)** các response lỗi, resource download, form/multipart và client giao tiếp khác còn hoạt động không.

## Tài liệu chính thức theo phiên bản

- [Spring Framework 6.2 — Message Converters trong MVC Config](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/message-converters.html)
- [Spring Framework 6.2 — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/message-converters.html)
- [Spring Framework 6.2 — `WebMvcConfigurer` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/servlet/config/annotation/WebMvcConfigurer.html)
- [Spring Boot 3.5 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html)
- [Spring Framework 6.2 — MVC enable configuration](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/enable.html)
