# Tùy chỉnh HttpMessageConverter mà không làm mất bộ chuyển đổi mặc định

Trong ứng dụng **Spring Boot dùng Spring MVC**, `HttpMessageConverter` là cơ chế đọc dữ liệu từ **HTTP request body** thành đối tượng Java và ghi đối tượng Java thành **HTTP response body**. Ví dụ: chuyển JSON vào một DTO có `@RequestBody`, chuyển `String` thành `text/plain`, hoặc trả `byte[]` dưới dạng dữ liệu nhị phân. Những bộ chuyển đổi này nằm trong quá trình xử lý request của `DispatcherServlet`, đặc biệt khi `RequestMappingHandlerAdapter` đọc tham số và ghi giá trị trả về.

Một yêu cầu tùy chỉnh thường gặp là: **thêm một định dạng nội dung mới hoặc điều chỉnh một converter có sẵn nhưng vẫn giữ các converter mặc định** mà Spring Boot đã cấu hình. Cách chọn điểm mở rộng quyết định liệu JSON, String, form data, tài nguyên tĩnh và các media type hiện có có tiếp tục hoạt động hay không.

**Nguyên tắc chính:** Với Spring MVC và Spring Boot 3.x, khi chỉ muốn **bổ sung** hoặc **điều chỉnh** danh sách đang có, ưu tiên `WebMvcConfigurer#extendMessageConverters(List<HttpMessageConverter<?>>)`. Không dùng `configureMessageConverters` để thêm phần tử một cách tùy tiện: khi danh sách được cấu hình ở hook đó không còn rỗng, cơ chế đăng ký các bộ chuyển đổi mặc định của Spring MVC có thể bị bỏ qua.

## 1. HttpMessageConverter nằm ở đâu trong luồng MVC?

Luồng rút gọn khi client gửi JSON tới một REST controller:

~~~text
HTTP client
  |
  | Content-Type: application/json
  | Accept: application/json
  | Request body: {"name":"Lan"}
  v
Servlet container -> FilterChain -> DispatcherServlet
                                       |
                                       v
                                 HandlerMapping
                                       |
                                       v
                                 HandlerAdapter
                                       |
                         chọn converter đọc body
                            canRead(Type, MediaType)
                                       |
                                       v
                          @RequestBody Java object
                                       |
                                       v
                             Controller / Service
                                       |
                                       v
                         chọn converter ghi body
                           canWrite(Type, MediaType)
                                       |
                                       v
                         JSON / text / bytes / ...
                                       |
                                       v
HTTP response qua Servlet container -> Client
~~~

`HttpMessageConverter` không phải cơ chế phân tích mọi dữ liệu HTTP:

- `@RequestParam` thường đọc query parameter hoặc form parameter qua cơ chế binding khác.
- `@PathVariable` lấy giá trị từ URL.
- `@RequestBody` thường dùng converter để đọc **toàn bộ request body** theo kiểu mục tiêu.
- `@ResponseBody`, `@RestController` và nhiều trường hợp của `ResponseEntity` thường dùng converter để ghi body.
- `multipart/form-data` còn liên quan cơ chế multipart resolution; từng `@RequestPart` có thể sử dụng converter cho nội dung của một part.

Nếu converter không hỗ trợ tổ hợp **kiểu Java + media type**, việc request có HTTP body hợp lệ về mặt giao thức không có nghĩa Spring MVC có thể xử lý body đó.

## 2. Các converter mặc định có tác dụng gì?

Spring MVC có các converter cơ bản, và Spring Boot có thể mở rộng hoặc điều chỉnh danh sách dựa trên **dependency/classpath** và cấu hình ứng dụng. Với một dự án `spring-boot-starter-web` thông dụng, các loại thường gặp gồm:

| Converter / nhóm | Vai trò thường gặp | Lưu ý |
|---|---|---|
| `ByteArrayHttpMessageConverter` | Đọc/ghi `byte[]` | Phục vụ body dạng byte |
| `StringHttpMessageConverter` | Đọc/ghi `String` | Rất quan trọng cho endpoint trả plain text |
| `ResourceHttpMessageConverter` và converter tài nguyên liên quan | Đọc/ghi `Resource` | Hữu ích khi trả nội dung tài nguyên |
| `AllEncompassingFormHttpMessageConverter` / form converter | Xử lý form và một số multipart body phù hợp | Phạm vi hỗ trợ phụ thuộc thành phần |
| `MappingJackson2HttpMessageConverter` | Đọc/ghi JSON qua Jackson 2 | Thường được Spring Boot 3.x đưa vào khi có Jackson |
| XML converter tương ứng | Đọc/ghi XML khi dependency thích hợp hiện diện | Không phải dự án nào cũng có |

**Không nên học thuộc một danh sách cố định** cho mọi phiên bản: thứ tự, số lượng và tính năng phụ thuộc phiên bản Spring Boot/Spring Framework, classpath và custom bean. Spring Boot 3.x trong các ví dụ sau dùng Jackson 2; khi nâng major version, cần kiểm tra lại API và cách Boot tích hợp thư viện JSON thực tế.

Nếu thay toàn bộ danh sách bằng một converter tự viết chỉ đọc `text/plain`, endpoint JSON trước đó có thể mất khả năng đọc `application/json`, một số endpoint trả resource có thể lỗi và content negotiation sẽ thay đổi. Đây là lý do cần **giữ converter mặc định** khi yêu cầu chỉ là một tính năng bổ sung.

## 3. Bốn cách tùy chỉnh và mức độ ảnh hưởng

| Cách làm | Có giữ danh sách mặc định không? | Khi nên sử dụng |
|---|---|---|
| Thuộc tính `spring.jackson.*` | Thường có, khi Boot/Jackson auto-config tương ứng hoạt động | Thay quy tắc JSON phổ biến như bỏ field null |
| Bean cấu hình `Jackson2ObjectMapperBuilderCustomizer` | Thường có, nếu dùng Jackson 2 của Boot | Điều chỉnh cách xây dựng `ObjectMapper` mà không thay converter |
| `WebMvcConfigurer#extendMessageConverters` | **Có**, tác động lên danh sách converter đã được thiết lập | Thêm custom converter hoặc sửa phần tử có sẵn |
| `WebMvcConfigurer#configureMessageConverters` | **Có nguy cơ thay cơ chế đăng ký mặc định** nếu danh sách được điền từ đây | Chủ động sở hữu danh sách converter từ đầu, biết rõ những gì phải đăng ký |

Một điểm cần phân biệt: trong Spring Boot, bean `HttpMessageConverter` do ứng dụng cung cấp cũng có thể được đưa vào danh sách converter theo cơ chế auto-configuration. Đây là đường tích hợp hợp lệ, nhưng cần kiểm soát type, ordering và việc thay thế converter mặc định của cùng loại. Không nên vừa đăng ký cùng một converter như một bean vừa thêm lại thủ công mà chưa hiểu kết quả.

Trong bài này, cách minh họa chính là **`extendMessageConverters`**: nó dễ nhìn thấy tác dụng bổ sung, không đòi hỏi tự tái tạo danh sách JSON/String/bytes của framework và giúp kiểm thử rằng các converter hiện có vẫn hoạt động.

## 4. Vì sao configureMessageConverters dễ làm mất converter mặc định?

Spring MVC có hai hook với tên rất giống nhau:

~~~java
@Override
public void configureMessageConverters(
        List<HttpMessageConverter<?>> converters) {
    // Chủ động cấu hình danh sách converter.
}

@Override
public void extendMessageConverters(
        List<HttpMessageConverter<?>> converters) {
    // Bổ sung hoặc điều chỉnh danh sách đã được tạo.
}
~~~

Các đoạn trên là chữ ký trong một class implements `WebMvcConfigurer`, không phải tệp Java độc lập.

Khi `configureMessageConverters` làm danh sách **không rỗng**, cơ chế của Spring MVC có thể không đăng ký các converter mặc định theo đường thông thường. Do đó, cách viết sau là **một ví dụ cần tránh** nếu mục tiêu chỉ là bổ sung:

~~~java
@Override
public void configureMessageConverters(
        List<HttpMessageConverter<?>> converters) {
    converters.add(new ScoreHttpMessageConverter());
}
~~~

Nếu làm như vậy mà không đăng ký các converter cần thiết khác, JSON, String, bytes và các media type thông dụng có thể không còn được xử lý theo kỳ vọng. Khi dùng Spring Boot, những customizer hoặc converter bean khác cũng có thể tham gia cấu hình, vì vậy không nên khẳng định mọi dự án sẽ mất chính xác cùng một danh sách; nhưng **đây không phải hook an toàn mặc định cho việc thêm một converter**.

Cách phù hợp hơn:

~~~java
@Override
public void extendMessageConverters(
        List<HttpMessageConverter<?>> converters) {
    converters.add(0, new ScoreHttpMessageConverter());
}
~~~

Lúc này danh sách mặc định đã được Spring MVC/Spring Boot chuẩn bị; chúng ta thêm converter có phạm vi hẹp vào đầu danh sách. Các converter còn lại vẫn tồn tại.

**Không nhầm với `@EnableWebMvc`.** Annotation này thể hiện lựa chọn kiểm soát cấu hình MVC ở mức sâu hơn và khiến phần tự động cấu hình MVC của Spring Boot thông thường nhường chỗ. Nó không có nghĩa Spring MVC không thể có bất kỳ default converter nào, nhưng nhiều tiện ích cấu hình của Boot sẽ không còn được áp dụng tự động như trước. Khi chỉ muốn thêm converter, **không cần `@EnableWebMvc`**.

## 5. Ví dụ đầy đủ: thêm định dạng application/vnd.example.score

Giả sử có một API nhỏ nhận một số nguyên dưới dạng văn bản, tăng lên một đơn vị rồi ghi kết quả về cùng định dạng:

~~~http
POST /scores/plus-one HTTP/1.1
Content-Type: application/vnd.example.score
Accept: application/vnd.example.score

41
~~~

Response mong đợi là HTTP 200, với body:

~~~text
42
~~~

Đây **không phải JSON**: body chỉ là các chữ số thể hiện một số nguyên. Ta tạo converter dành riêng cho kiểu Java `Score` và media type `application/vnd.example.score`. Converter này không xử lý `String`, `Map` hoặc JSON. Nhờ vậy, khi thêm nó vào danh sách, các converter đã có vẫn phụ trách định dạng cũ.

### 5.1. Dependency

Ví dụ sử dụng **Spring Boot 3.x, Java 17+**, dự án Gradle có Spring Boot plugin và dependency management phù hợp. Trong `build.gradle` (Groovy DSL):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Starter web cung cấp Spring MVC và các thư viện JSON cơ bản theo cách quản lý của Spring Boot trong ví dụ này. Không cần thêm một starter cho converter đặc biệt vì converter được tự viết bằng API Spring.

### 5.2. Mã Java có thể chạy trong dự án Spring Boot

Tạo file **`src/main/java/demo/converter/ConverterDemoApplication.java`**:

~~~java
package demo.converter;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpInputMessage;
import org.springframework.http.HttpOutputMessage;
import org.springframework.http.MediaType;
import org.springframework.http.converter.AbstractHttpMessageConverter;
import org.springframework.http.converter.HttpMessageConverter;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.http.converter.HttpMessageNotWritableException;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@SpringBootApplication
public class ConverterDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConverterDemoApplication.class, args);
    }
}

record Score(int value) {
}

final class ScoreHttpMessageConverter
        extends AbstractHttpMessageConverter<Score> {

    ScoreHttpMessageConverter() {
        super(MediaType.parseMediaType(
                "application/vnd.example.score"
        ));
    }

    @Override
    protected boolean supports(Class<?> clazz) {
        return Score.class == clazz;
    }

    @Override
    protected Score readInternal(
            Class<? extends Score> clazz,
            HttpInputMessage input
    ) throws IOException, HttpMessageNotReadableException {
        String body = new String(
                input.getBody().readAllBytes(),
                StandardCharsets.UTF_8
        ).trim();

        try {
            return new Score(Integer.parseInt(body));
        } catch (NumberFormatException ex) {
            throw new HttpMessageNotReadableException(
                    "Score must be an integer",
                    ex,
                    input
            );
        }
    }

    @Override
    protected void writeInternal(
            Score score,
            HttpOutputMessage output
    ) throws IOException, HttpMessageNotWritableException {
        byte[] bytes = Integer.toString(score.value())
                .getBytes(StandardCharsets.UTF_8);
        output.getBody().write(bytes);
    }
}

@Configuration(proxyBeanMethods = false)
class ConverterMvcConfiguration implements WebMvcConfigurer {

    @Override
    public void extendMessageConverters(
            List<HttpMessageConverter<?>> converters
    ) {
        // Bổ sung vào danh sách đã có, không xóa converter mặc định.
        converters.add(0, new ScoreHttpMessageConverter());
    }
}

@RestController
class ConverterDemoController {

    @PostMapping(
            path = "/scores/plus-one",
            consumes = "application/vnd.example.score",
            produces = "application/vnd.example.score"
    )
    public Score plusOne(@RequestBody Score input) {
        return new Score(input.value() + 1);
    }

    @GetMapping(path = "/plain", produces = MediaType.TEXT_PLAIN_VALUE)
    public String plain() {
        return "text-ok";
    }

    @PostMapping(
            path = "/json/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Map<String, String> echoJson(
            @RequestBody Map<String, String> payload
    ) {
        return payload;
    }
}
~~~

**Vì sao ví dụ hoạt động?**

1. `@SpringBootApplication` khởi động Spring MVC và quét các class trong package `demo.converter`.
2. `ScoreHttpMessageConverter` chỉ khai báo hỗ trợ Java class `Score` và media type `application/vnd.example.score`.
3. `readInternal` đọc bytes trong request body thành số nguyên, trả về `Score`. Nếu body không biểu diễn được một số nguyên `int`, nó ném `HttpMessageNotReadableException` để MVC xử lý lỗi đọc body.
4. `writeInternal` chuyển số nguyên thành bytes UTF-8 rồi ghi vào HTTP output body.
5. `ConverterMvcConfiguration` dùng **`extendMessageConverters`**; converter mới được thêm vào vị trí đầu danh sách mà không xóa các converter khác.
6. Endpoint `/plain` tiếp tục dùng xử lý String, còn endpoint `/json/echo` tiếp tục dùng JSON converter đã có.

`Score` là record không có logic nghiệp vụ ngoài việc giữ một giá trị nguyên. `ScoreHttpMessageConverter` chỉ là một ví dụ về định dạng tùy biến: trong thực tế nên dùng định dạng chuẩn như JSON khi không có yêu cầu tương tác với giao thức riêng.

### 5.3. Chạy và thử qua HTTP

Từ dự án Spring Boot đã thiết lập Gradle wrapper và main class ở trên:

~~~bash
./gradlew bootRun
~~~

Trên Windows có thể dùng `gradlew.bat bootRun`. Nếu cổng 8080 đang bị chiếm hoặc bị cấu hình lại, cần sửa cổng truy cập tương ứng.

Trong một terminal khác, gọi định dạng mới:

~~~bash
curl -i http://localhost:8080/scores/plus-one \
  -H 'Content-Type: application/vnd.example.score' \
  -H 'Accept: application/vnd.example.score' \
  --data-binary '41'
~~~

Với cú pháp shell kiểu Bash, dấu `\\` nối dòng. Trong Windows PowerShell, dùng lệnh `curl.exe` trên một dòng hoặc điều chỉnh cú pháp xuống dòng cho shell đang sử dụng. Khi chạy thành công, **HTTP status là 200**, response body là:

~~~text
42
~~~

Kiểm tra String converter vẫn hoạt động:

~~~bash
curl -i -H 'Accept: text/plain' http://localhost:8080/plain
~~~

Body mong đợi:

~~~text
text-ok
~~~

Kiểm tra Jackson JSON converter không bị mất:

~~~bash
curl -i http://localhost:8080/json/echo \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data '{"message":"xin chao"}'
~~~

Với ứng dụng không có security/filter khác can thiệp, kết quả trả body JSON biểu diễn cùng dữ liệu, ví dụ:

~~~json
{"message":"xin chao"}
~~~

Ba phép thử này có mục đích khác nhau: **converter mới hoạt động**, **plain text còn hoạt động**, và **JSON mặc định còn hoạt động**. Chỉ test endpoint tùy biến là chưa đủ để chứng minh không làm hỏng cấu hình cũ.

Đoạn mã ví dụ không cố định HTTP headers như `Date` hoặc `Transfer-Encoding`; chúng có thể thay đổi theo Servlet container. Status/body là điều cần xác nhận ở đây.

## 6. Trình tự chọn converter: canRead và canWrite

Spring MVC không chọn converter chỉ dựa trên tên class. Các điều kiện quan trọng gồm:

- **Kiểu Java** cần đọc/ghi, chẳng hạn `Score`, `String`, `Map`, `byte[]` hoặc DTO.
- **Content-Type của request** khi đọc `@RequestBody`.
- **Accept của client** và các ràng buộc `produces` khi ghi response body.
- **Danh sách converter và thứ tự** được đăng ký.
- Khả năng `canRead` / `canWrite` của từng converter theo kiểu và media type, cùng những biến thể API có thêm thông tin generic type.

Trong ví dụ:

- Request body `41` với `Content-Type: application/vnd.example.score`, đích `Score`: custom converter được chọn để **đọc**.
- Controller trả về `Score(42)` và client chấp nhận media type mới: custom converter được chọn để **ghi**.
- Controller trả `Map<String,String>` với JSON: custom converter nói không hỗ trợ `Map`; converter JSON tiếp tục được chọn.
- Controller trả `String` với text/plain: custom converter nói không hỗ trợ `String`; `StringHttpMessageConverter` làm phần việc đó.

**Thứ tự quan trọng khi có chồng lấn**. Nếu tạo một converter tuyên bố `canRead(Object.class, application/json)` hoặc `canWrite(Object.class, */*)`, nó có thể chiếm vị trí xử lý của converter JSON/String có sẵn. Với converter dành cho một định dạng chuyên dụng, nên **giới hạn rõ kiểu Java và media type** thay vì khai báo hỗ trợ quá rộng.

Trong ví dụ, đặt custom converter ở đầu danh sách phù hợp vì nó có phạm vi rất hẹp. Nếu converter mới chồng lấn với Jackson, cần cân nhắc vị trí, điều kiện lựa chọn và kiểm thử từng loại body.

## 7. Content-Type, Accept và các mã lỗi liên quan

**Content-Type** cho biết media type của body mà client **gửi lên**. Nó ảnh hưởng converter dùng để đọc `@RequestBody`. **Accept** cho biết các media type client có thể **nhận về**. Nó cùng `produces` ảnh hưởng cơ chế ghi response body.

| Tình huống | Kết quả thường gặp | Cách điều tra |
|---|---|---|
| Client gửi media type không khớp `consumes` | HTTP 415 Unsupported Media Type | Xác nhận Content-Type và mapping |
| Converter không đọc được body theo kiểu cần thiết | Thường lỗi 400 hoặc 415 tùy nguyên nhân | Kiểm tra canRead, media type, dữ liệu, exception |
| Body không parse được như số nguyên trong ví dụ | HTTP 400 Bad Request | Xác nhận body, format và lỗi đọc |
| Client chỉ nhận media type không khớp `produces` | HTTP 406 Not Acceptable | Xác nhận Accept và mapping |
| Converter không ghi được kiểu trả về | Lỗi xử lý response, có thể 500/406 tùy nhánh | Kiểm tra canWrite và converter selection |
| Không có mapping HTTP method phù hợp | Có thể 404 hoặc 405 | Kiểm tra request mapping; chưa chắc do converter |

Ví dụ gửi sai content type:

~~~bash
curl -i http://localhost:8080/scores/plus-one \
  -H 'Content-Type: text/plain' \
  -H 'Accept: application/vnd.example.score' \
  --data-binary '41'
~~~

Endpoint được khai báo `consumes=application/vnd.example.score`, nên trong cấu hình minh họa có thể phản hồi **HTTP 415** trước khi converter tự viết được dùng để đọc body.

Ví dụ client chỉ chấp nhận JSON:

~~~bash
curl -i http://localhost:8080/scores/plus-one \
  -H 'Content-Type: application/vnd.example.score' \
  -H 'Accept: application/json' \
  --data-binary '41'
~~~

Vì endpoint chỉ khai báo `produces=application/vnd.example.score`, kết quả thường là **HTTP 406**. Đây là vấn đề **content negotiation**, không phải chứng cứ JSON converter đã bị xóa.

Nếu body là `hello` thay vì số nguyên và headers hợp lệ, custom converter sẽ ném `HttpMessageNotReadableException`, dẫn đến HTTP 400 theo exception handling mặc định của Spring MVC trong ví dụ.

**Đừng nhầm:** endpoint lỗi 415/406 dù JSON converter vẫn tồn tại nếu `consumes`, `produces` hoặc header client không tương thích.

## 8. Điều chỉnh Jackson JSON mà vẫn giữ cấu hình mặc định

Rất nhiều yêu cầu “tùy chỉnh converter” thực ra chỉ cần sửa **quy tắc Jackson**: không serialise field null, định dạng ngày giờ, quy tắc naming hoặc module. Đừng thay toàn bộ `MappingJackson2HttpMessageConverter` chỉ để thực hiện một quy tắc JSON phổ biến.

### 8.1. Ưu tiên thuộc tính Spring Boot

Ví dụ `application.yml` trong ứng dụng Spring Boot/Jackson 2 có cấu hình tương ứng:

~~~yaml
spring:
  jackson:
    default-property-inclusion: non_null
    serialization:
      indent_output: false
~~~

Cấu hình làm mục đích rõ ràng và để Spring Boot tiếp tục xây dựng ObjectMapper/converter mặc định. Các property thực tế có thể khác khi thay major version hoặc thư viện JSON; cần kiểm tra theo phiên bản đang dùng.

Khi chỉ cần ẩn null ở một DTO, có thể cân nhắc annotation Jackson trên lớp/field thay vì thay toàn bộ policy JSON của ứng dụng.

### 8.2. Dùng Jackson2ObjectMapperBuilderCustomizer khi cần code

Trong **Spring Boot 3.x với Jackson 2**, một bean customizer có thể trông như sau:

~~~java
import com.fasterxml.jackson.annotation.JsonInclude;

import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class JacksonSerializationConfiguration {

    @Bean
    Jackson2ObjectMapperBuilderCustomizer includeNonNullFields() {
        return builder -> builder.serializationInclusion(
                JsonInclude.Include.NON_NULL
        );
    }
}
~~~

Đây là class cấu hình cần được package scan của Spring Boot nhìn thấy. `Jackson2ObjectMapperBuilderCustomizer` điều chỉnh cách builder cấu hình ObjectMapper; thông thường converter JSON do Boot tạo vẫn tồn tại. Cách này ảnh hưởng những ObjectMapper được xây dựng thông qua builder liên quan, không chỉ một controller; phải đánh giá phạm vi sử dụng trước khi áp dụng toàn cục.

Đừng vừa dùng `spring.jackson.default-property-inclusion` vừa viết customizer tương đương nhưng giá trị khác nhau mà không kiểm tra quy tắc ưu tiên. Khi cần áp dụng khác biệt chỉ cho một endpoint, có thể dùng DTO-specific annotation hoặc cấu hình đặc thù thay vì policy toàn ứng dụng.

### 8.3. Tránh tự tạo ObjectMapper rỗng để thay converter

Một ví dụ dễ gây tác dụng phụ là:

~~~java
// Minh họa rủi ro: KHÔNG thay thế bừa bãi converter mặc định.
converters.removeIf(c ->
        c instanceof MappingJackson2HttpMessageConverter);
converters.add(new MappingJackson2HttpMessageConverter(
        new ObjectMapper()));
~~~

Đây là fragment, không phải Java source độc lập. Tạo `new ObjectMapper()` có thể làm mất module, custom serializer/deserializer, naming policy, Java time support và những tùy chỉnh mà ứng dụng đã đăng ký qua Boot. Việc xóa rồi thêm converter cũng có thể thay đổi ordering hoặc supported media types.

Nếu thực sự cần thay converter, phải tái hiện có chủ đích các cấu hình cần thiết, kiểm tra tác động đến cả request lẫn response và bao phủ bằng integration test. **Không tái tạo converter chỉ để bật một tùy chọn Jackson đơn giản.**

## 9. Sửa converter đang có trong extendMessageConverters

Trong một số dự án cần sửa phần tử sẵn có. `extendMessageConverters` nhận danh sách mà Spring MVC đã xây dựng, nên có thể tìm theo type, điều chỉnh có kiểm soát rồi giữ nguyên những phần tử khác.

Ví dụ chỉ **quan sát** danh sách trong môi trường debug, không làm thay đổi thứ tự:

~~~java
@Override
public void extendMessageConverters(
        List<HttpMessageConverter<?>> converters
) {
    for (HttpMessageConverter<?> converter : converters) {
        System.out.println(
                converter.getClass().getSimpleName()
        );
    }
}
~~~

Đây là fragment trong class implements `WebMvcConfigurer`. Không nên ghi toàn bộ danh sách ra log ở mức cao trong production một cách lặp lại, nhưng logging thời điểm khởi tạo có thể giúp hiểu converter nào thực sự tồn tại.

Nếu muốn mở rộng media type của converter đã có, hãy **sao chép** danh sách `getSupportedMediaTypes()` trước, kiểm tra giá trị cần thêm và gọi `setSupportedMediaTypes(...)` nếu API của converter cho phép. Không sử dụng `list.clear()` hoặc `converters.clear()` khi mục tiêu chỉ là thêm một định dạng. Nhớ rằng một converter Jackson hỗ trợ media type rộng như `application/*+json`; thêm thủ công subtype JSON tương thích có thể hoàn toàn không cần thiết.

Cần tránh thay đổi state của một ObjectMapper đang được nhiều thành phần sử dụng sau khi ứng dụng đã nhận traffic. Tùy chỉnh ở giai đoạn cấu hình khởi động; không cập nhật cấu hình converter/ObjectMapper từ mỗi request để tránh race condition và thay đổi hành vi không dự đoán được.

## 10. Kiểm thử tự động rằng converter mới không phá mặc định

Chỉ nhìn Spring Boot khởi động thành công không đủ: lỗi có thể chỉ xuất hiện khi endpoint JSON hoặc plain text được gọi. Một chiến lược kiểm thử nên bảo vệ **ít nhất ba hành vi**:

1. API định dạng tùy chỉnh đọc và ghi đúng body.
2. API JSON đọc và ghi như trước.
3. API plain text vẫn trả được String.

Trong dự án có `spring-boot-starter-test`, có thể dùng `MockMvc` để thực thi MVC request trong test. Đây là một test lớp Spring Boot với converter configuration thực tế:

~~~java
package demo.converter;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ConverterMvcIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void customScoreConverterWorks() throws Exception {
        mvc.perform(post("/scores/plus-one")
                .contentType("application/vnd.example.score")
                .accept("application/vnd.example.score")
                .content("41"))
           .andExpect(status().isOk())
           .andExpect(content().string("42"));
    }

    @Test
    void defaultPlainTextStillWorks() throws Exception {
        mvc.perform(get("/plain")
                .accept(MediaType.TEXT_PLAIN))
           .andExpect(status().isOk())
           .andExpect(content().string("text-ok"));
    }

    @Test
    void defaultJsonStillWorks() throws Exception {
        mvc.perform(post("/json/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("{\"message\":\"xin chao\"}"))
           .andExpect(status().isOk())
           .andExpect(content().json(
                   "{\"message\":\"xin chao\"}"
           ));
    }
}
~~~

Tạo file **`src/test/java/demo/converter/ConverterMvcIntegrationTest.java`**, thêm dependency:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Lệnh thực thi với Gradle:

~~~bash
./gradlew test
~~~

Các test thành công nếu project dùng cấu hình ví dụ, test runtime có đủ JUnit/Spring Test và không có security, profile hoặc cấu hình khác thay đổi mapping/response. `MockMvc` chạy trong MVC test infrastructure chứ không mở socket server thực. Để kiểm tra behavior HTTP server thực tế (content type/proxy/container), bổ sung một `@SpringBootTest(webEnvironment = RANDOM_PORT)` và client HTTP.

**Bài học của test:** tránh test riêng converter mới rồi kết luận “đã giữ default”. Phải có regression test cho ít nhất một số converter mặc định quan trọng của hệ thống thực, đặc biệt JSON nếu API đang dùng rộng rãi.

## 11. Kiểm tra converter được đăng ký và thứ tự thực tế

Khi một custom converter không được chọn, lần lượt kiểm tra:

- Class cấu hình có được Spring quét không? `@Configuration` có thuộc package của application entrypoint không?
- Ứng dụng chạy Spring MVC Servlet hay WebFlux? Hai stack có pipeline codec/converter khác nhau.
- Có bean `WebMvcConfigurer` khác thay đổi converter list hoặc ordering không?
- Có `@EnableWebMvc` hoặc subclass `WebMvcConfigurationSupport` khiến MVC auto-config của Boot bị thay đổi không?
- Converter có thực sự trả true cho type + media type của request/response không?
- `@RequestMapping` có khai báo `consumes` hoặc `produces` làm request bị loại trước lúc converter được chọn không?
- Client có gửi `Content-Type` và `Accept` phù hợp không?
- Có Jackson/JSON library thực sự trên runtime classpath không?
- Có một custom converter đăng ký quá rộng và chiếm việc của converter mặc định không?
- Có tạo trùng converter qua hai con đường `@Bean` và `extendMessageConverters` không?

Đừng dựa vào tên bean hoặc số lượng converter đoán nó được ưu tiên; Spring MVC dùng khả năng đọc/ghi và thứ tự của danh sách thực tế. Nếu phải log danh sách, thực hiện có kiểm soát tại lúc startup, không log body chứa token/mật khẩu/thông tin nhạy cảm.

## 12. Những lỗi phổ biến và cách khắc phục

### 12.1. Dùng configureMessageConverters để thêm một phần tử

**Biểu hiện:** sau khi thêm converter XML/custom, các endpoint JSON hoặc String trả lỗi.

**Nguyên nhân:** danh sách được điền trong `configureMessageConverters` có thể làm Spring MVC không tự đăng ký các converter mặc định theo đường thông thường.

**Khắc phục:** chuyển phần bổ sung sang `extendMessageConverters` hoặc đăng ký bean converter theo cơ chế Boot với type/ordering được kiểm soát. Test lại JSON/text.

### 12.2. Thêm @EnableWebMvc chỉ để tùy chỉnh body

**Biểu hiện:** một số cấu hình MVC do Spring Boot cung cấp không còn hoạt động như trước, dù controller vẫn chạy.

**Nguyên nhân:** `@EnableWebMvc` thay đổi quyền sở hữu cấu hình MVC, khiến Spring Boot MVC auto-configuration thông thường không còn áp dụng như khi chỉ triển khai `WebMvcConfigurer`.

**Khắc phục:** bỏ annotation nếu không cần kiểm soát toàn bộ MVC, dùng `WebMvcConfigurer` đơn thuần. Kiểm tra lại message converters, static resources, path matching, CORS và các MVC feature khác theo nhu cầu.

### 12.3. Tạo converter mới hỗ trợ Object.class và */*

**Biểu hiện:** body JSON bị converter tự viết xử lý nhầm hoặc content negotiation trả định dạng sai.

**Nguyên nhân:** `supports` hoặc supported media types quá rộng, cộng với việc converter có thứ tự ưu tiên cao.

**Khắc phục:** giới hạn kiểu Java/media type và thử nhiều endpoint có body khác nhau. Không lấy \`*/*\` làm supported media type mặc định trừ khi hiểu hệ quả.

### 12.4. Thay ObjectMapper mà bỏ module đã cấu hình

**Biểu hiện:** dữ liệu ngày giờ serialize khác, annotation hoặc module custom không còn tác dụng.

**Nguyên nhân:** tạo `new ObjectMapper()` và thay converter Jackson mặc định thay vì điều chỉnh builder hoặc properties.

**Khắc phục:** ưu tiên `spring.jackson.*` và `Jackson2ObjectMapperBuilderCustomizer` khi tương thích, hoặc tái sử dụng cấu hình ObjectMapper hiện có có chủ đích.

### 12.5. Không phân biệt 415 và 406

**Biểu hiện:** request thất bại, nhóm phát triển tìm lỗi ở controller dù handler chưa chạy.

**Nguyên nhân:** `Content-Type` không khớp `consumes` hoặc `Accept` không khớp `produces`.

**Khắc phục:** kiểm tra headers và mapping trước khi sửa converter; dùng test negative cases riêng.

### 12.6. Converter không xử lý dữ liệu sai một cách rõ ràng

**Biểu hiện:** parse lỗi dẫn đến 500, hoặc trả thông báo khó hiểu.

**Nguyên nhân:** code convert tự viết ném exception không phù hợp hoặc không giới hạn input.

**Khắc phục:** với request body không đọc được, dùng `HttpMessageNotReadableException` hoặc xử lý lỗi qua Spring MVC thích hợp; áp dụng giới hạn kích thước và validation đầu vào. Không in nguyên request body nhạy cảm ra log.

### 12.7. Không xét charset và encoding

**Biểu hiện:** ký tự tiếng Việt bị lỗi hoặc bytes không khớp với body đã ký số.

**Nguyên nhân:** dùng charset mặc định của hệ điều hành, nhầm `Content-Type` hoặc tự ý biến đổi bytes.

**Khắc phục:** dùng charset rõ ràng khi định dạng cần xử lý text; converter ví dụ dùng `StandardCharsets.UTF_8`. Với định dạng nhị phân hoặc giao thức có charset do client quy định, cần xử lý theo quy ước media type thật thay vì luôn `trim()` như ví dụ số nguyên.

### 12.8. Đọc stream hai lần

**Biểu hiện:** body rỗng trong controller hoặc converter, trong khi filter đã đọc body trước.

**Nguyên nhân:** request input stream thường là stream một lượt; filter đã tiêu thụ nội dung mà không dùng wrapper/caching phù hợp.

**Khắc phục:** không tùy tiện đọc body trong filter; nếu cần log body, giới hạn dung lượng và dùng cơ chế wrapping có trách nhiệm. Converter được thiết kế để tiêu thụ request body trong đúng giai đoạn MVC.

### 12.9. Converter có state mutable theo request

**Biểu hiện:** request đồng thời trả dữ liệu lẫn nhau hoặc lỗi ngẫu nhiên.

**Nguyên nhân:** converter là thành phần được chia sẻ, nhưng giữ nội dung parse/write của từng request trong field instance.

**Khắc phục:** dùng biến cục bộ trong `readInternal` và `writeInternal`; giữ cấu hình converter bất biến trong thời gian chạy, hoặc thiết kế đồng bộ nếu thực sự có shared mutable state.

### 12.10. Chỉ test định dạng mới

**Biểu hiện:** API custom chạy được nhưng các client JSON cũ bị lỗi trên production.

**Nguyên nhân:** không có regression test cho converter mặc định.

**Khắc phục:** test song song custom media type, JSON, plain text, và những định dạng như byte[]/resource/form mà hệ thống thực tế cần.

## 13. Khi nào không nên viết HttpMessageConverter riêng?

Không phải mọi nhu cầu chuyển đổi dữ liệu đều nên tạo converter:

- **Đổi định dạng ngày giờ JSON:** thường dùng Jackson config/serializer.
- **Chỉ đổi một field của DTO:** dùng Jackson annotation, serializer hoặc kiểu dữ liệu phù hợp.
- **Validate giá trị nghiệp vụ:** dùng Bean Validation và service, không gắn chặt vào parser HTTP.
- **Đổi query parameter sang enum/object:** có thể dùng `Converter` hoặc `Formatter` trong Spring MVC conversion service; đó không phải HttpMessageConverter cho body.
- **Chuẩn hóa response envelope:** có thể xem xét `ResponseBodyAdvice`, tùy mức ảnh hưởng tới content type và converter.
- **Chuẩn hóa exception response:** dùng `@RestControllerAdvice` / `@ExceptionHandler` phù hợp.
- **Cần HTTP client codec:** `RestClient`, `RestTemplate` hoặc `WebClient` có cách cấu hình message converters/codecs riêng; không giả định customizer MVC server tự áp dụng cho mọi client.
- **Xử lý reactive server:** Spring WebFlux dùng hệ thống `HttpMessageReader`/`HttpMessageWriter` và codec configuration, không dùng ví dụ `WebMvcConfigurer` của Servlet MVC.

Chỉ viết converter riêng khi bạn **thực sự có wire format đặc thù** cần tích hợp ở ranh giới HTTP body với API MVC. Giới hạn khả năng đọc/ghi càng rõ, nguy cơ thay đổi hành vi converter mặc định càng thấp.

## 14. Checklist triển khai an toàn

1. Xác nhận ứng dụng thực sự dùng **Spring MVC Servlet stack**, có dependency cần thiết trên runtime classpath.
2. Tách rõ nhu cầu thêm **media type mới** với nhu cầu chỉ sửa **quy tắc JSON**; nếu chỉ sửa JSON, ưu tiên properties/builder customizer.
3. Nếu thêm converter, triển khai khả năng đọc/ghi cho kiểu và media type cụ thể; xử lý input sai rõ ràng và không dùng state theo request.
4. Đăng ký bằng `WebMvcConfigurer#extendMessageConverters` hoặc cơ chế bean Boot phù hợp; **không tự xóa danh sách default**.
5. Không dùng `configureMessageConverters` hoặc `@EnableWebMvc` chỉ để thêm một converter đơn giản.
6. Kiểm tra ordering nếu custom converter có phạm vi chồng lấn; loại bỏ đăng ký trùng.
7. Thử request với `Content-Type`, `Accept` và các điều kiện `consumes`/`produces` phù hợp.
8. Thử riêng tình huống body lỗi, media type sai, accept không tương thích và dữ liệu vượt giới hạn.
9. Chạy regression test ít nhất cho **JSON + String + media type mới**, thêm các converter default khác nếu hệ thống phụ thuộc.
10. Quan sát lỗi thực tế trước khi chỉnh code: 400, 415, 406 và lỗi write response không mang cùng ý nghĩa.
11. Không log body nhạy cảm; hạn chế thay đổi ObjectMapper/converter sau khi server đang xử lý traffic.
12. Sau nâng Spring Boot/Spring Framework major version, kiểm tra lại package/API và auto-configuration thay vì áp dụng mù code cũ.

**Kết luận:** `HttpMessageConverter` là lớp chuyển đổi **HTTP body ↔ Java object** trong Spring MVC. Khi yêu cầu chỉ là **bổ sung hoặc điều chỉnh có kiểm soát**, dùng **`extendMessageConverters`** để giữ danh sách mà Spring MVC/Spring Boot đã xây dựng. Nếu chỉ thay quy tắc JSON, ưu tiên cấu hình Jackson thay vì tự thay converter. Một thay đổi chỉ thực sự an toàn khi **converter mới chạy được và các endpoint JSON, text, resource vốn có vẫn hoạt động qua regression test**.