# WebExchangeDataBinder và dữ liệu từ ServerWebExchange trong Spring WebFlux

## 1. Mục tiêu và bối cảnh

Một request gửi tới Spring WebFlux có thể mang dữ liệu ở nhiều vị trí: query string trên URL, body dạng form URL-encoded, body multipart, URI template variables, headers và JSON. Khi một controller nhận **model attribute**, Spring cần tập hợp các giá trị phù hợp, chuyển kiểu rồi gán vào Java object. Thành phần làm nhiệm vụ binding trên reactive stack là `WebExchangeDataBinder` (và biến thể mở rộng của nó), làm việc với request context `ServerWebExchange`.

Ví dụ request:

~~~http
POST /registrations?age=21 HTTP/1.1
Host: localhost:8080
Content-Type: application/x-www-form-urlencoded

name=Lan&tags%5B0%5D=java
~~~

Một Java form có thể nhận:

~~~java
public class RegistrationForm {
    private String name;
    private Integer age;
    private List<String> tags = new ArrayList<>();
    // Các getter/setter tương ứng.
}
~~~

Kết quả sau property binding mong muốn: `name == "Lan"`, `age == 21` và `tags.get(0).equals("java")`. Query parameter `age` và form field `name`, `tags[0]` cùng tham gia, còn `ConversionService`/property editors giúp đổi chuỗi `"21"` thành `Integer`.

**Điểm cốt lõi của bài:**

- `ServerWebExchange` đại diện cho **một tương tác HTTP**: request, response, attributes, session, form data và multipart data theo reactive API.
- `WebExchangeDataBinder` kế thừa `WebDataBinder`/`DataBinder` và biết cách lấy các giá trị có thể bind từ `ServerWebExchange`.
- `bind(exchange)` trả về **`Mono<Void>`**: hoàn tất sau khi dữ liệu cần thiết được đọc và binding xảy ra. Không nên gọi rồi bỏ qua publisher.
- `BindingResult` chứa binding/conversion errors; **validation** với `@Valid`/`@Validated` là bước riêng.
- `@ModelAttribute` trong **Spring WebFlux** sử dụng data binding, khác hoàn toàn với `@RequestBody` JSON được giải mã qua `HttpMessageReader`.
- Request field names do client kiểm soát. Dùng DTO dành riêng cho input, `allowedFields`, giới hạn kích thước, kiểm tra quyền và không bind trực tiếp vào domain entity nhạy cảm.

Nội dung dựa trên Spring Framework 6.2/Java 17. Ví dụ chạy được dùng Spring Boot 3.5.7 và **`spring-boot-starter-webflux`**, không dùng `spring-boot-starter-web` của Servlet MVC.

## 2. Các đối tượng tham gia

### 2.1. `ServerWebExchange` là gì?

Interface `org.springframework.web.server.ServerWebExchange` bao bọc request–response interaction của WebFlux. Các API tiêu biểu:

| API | Dữ liệu | Tính chất |
| --- | --- | --- |
| `getRequest()` | `ServerHttpRequest` | Request URI, method, headers, `getQueryParams()` |
| `getResponse()` | `ServerHttpResponse` | HTTP status, response headers và body |
| `getAttributes()` | `Map<String,Object>` | Dữ liệu thuộc phạm vi exchange, không phải input fields mặc định |
| `getFormData()` | `Mono<MultiValueMap<String,String>>` | Body dạng `application/x-www-form-urlencoded` |
| `getMultipartData()` | `Mono<MultiValueMap<String,Part>>` | Body `multipart/form-data` và những multipart media types được cấu hình |
| `getSession()` | `Mono<WebSession>` | Truy cập session theo reactive contract |
| `getPrincipal()` | `Mono<Principal>` | Principal của request nếu có |
| `getLocaleContext()` | `LocaleContext` | Context địa phương hóa của request |

`exchange.getRequest().getQueryParams()` trả `MultiValueMap<String,String>` **đồng bộ** vì query đã nằm trong URI. Ngược lại, `getFormData()` và `getMultipartData()` trả `Mono` vì nội dung body được đọc và parse qua reactive message readers.

Ví dụ đọc form một cách reactive:

~~~java
public Mono<String> readName(ServerWebExchange exchange) {
    return exchange.getFormData()
            .map(form -> form.getFirst("name"))
            .defaultIfEmpty("");
}
~~~

Đây là **một phương thức minh họa**, chưa phải cả class có import. Lưu ý `defaultIfEmpty` chỉ xử lý trường hợp publisher không phát giá trị; nếu `getFirst("name")` là `null`, Reactor `map` không cho phép trả `null`. Trong code ứng dụng cần xử lý tên field vắng mặt an toàn, chẳng hạn:

~~~java
public Mono<String> readNameSafely(ServerWebExchange exchange) {
    return exchange.getFormData()
            .map(form -> form.getFirst("name") == null
                    ? ""
                    : form.getFirst("name"));
}
~~~

Đoạn thứ hai thể hiện chính xác null-handling. `getFormData()` của `ServerWebExchange` theo hợp đồng trả một map (có thể rỗng) khi đã giải quyết form data. Form data được đọc và parse đầy đủ rồi **cache map**, nên gọi lại `getFormData()` trên cùng exchange không tự đọc lại body raw; tuy nhiên nó vẫn đòi hỏi ngân sách bộ nhớ thích hợp.

Với multipart, metadata về parts được cache ở `getMultipartData()`, nhưng **nội dung của mỗi `Part` không được cache để có thể đọc lặp tùy ý**. Đọc upload cần xử lý stream/lifecycle đúng cách.

### 2.2. `WebExchangeDataBinder` là gì?

Class:

~~~java
org.springframework.web.bind.support.WebExchangeDataBinder
~~~

Kế thừa theo thứ tự:

~~~text
DataBinder
   └── WebDataBinder
           └── WebExchangeDataBinder
                   └── ExtendedWebExchangeDataBinder
                       (biến thể dùng trong WebFlux controller)
~~~

`DataBinder` cung cấp binding vào JavaBean/constructor, converter, validator và `BindingResult`. `WebDataBinder` bổ sung xử lý field markers/defaults và cơ chế thích hợp với web forms. `WebExchangeDataBinder` chuyên xử lý việc **lấy giá trị từ reactive `ServerWebExchange`** để gán vào object.

Các chữ ký API quan trọng trên Spring Framework 6.2:

~~~java
// Các chữ ký rút gọn của thư viện Spring, KHÔNG định nghĩa lại.
new WebExchangeDataBinder(target);
new WebExchangeDataBinder(target, "registrationForm");

Mono<Void> bind(ServerWebExchange exchange);
Mono<Void> construct(ServerWebExchange exchange); // Có từ Spring 6.1.
Mono<Map<String, Object>> getValuesToBind(ServerWebExchange exchange);
static Mono<Map<String, Object>>
    extractValuesToBind(ServerWebExchange exchange);
~~~

- Constructor nhận `target` là bean cần bind. `objectName` giúp gắn tên lỗi vào đúng model attribute.
- `bind(exchange)` phục vụ **property binding** trên object đã tồn tại, ví dụ gọi setters của form.
- `construct(exchange)` tạo target qua constructor binding khi binder được cấu hình loại target phù hợp, không phải chỉ đơn giản gọi `new` cho mọi class. Khi xây handler `@ModelAttribute`, Spring thường điều phối khâu tạo object.
- `getValuesToBind(exchange)` lấy map dữ liệu bind, mặc định gọi hàm tĩnh `extractValuesToBind(exchange)`.
- `getBindingResult()` kế thừa từ `DataBinder`, cho biết các lỗi binding. Khi gọi `bind` thủ công, `@Valid` **không tự chạy** chỉ vì target có annotations.

### 2.3. `ExtendedWebExchangeDataBinder` để làm gì?

`WebExchangeDataBinder.extractValuesToBind` chủ yếu tập hợp **query parameters, form fields và multipart fields/parts**. Trong luồng `@ModelAttribute` của controller WebFlux, Spring dùng binder mở rộng `ExtendedWebExchangeDataBinder`, có khả năng thêm **URI template variables** và **request headers** để làm ứng viên bind khi không bị request parameters ưu tiên ghi đè.

Ví dụ:

~~~http
POST /owners/42/profile?name=Lan HTTP/1.1
X-Region: south
Content-Type: application/x-www-form-urlencoded

city=Hanoi
~~~

Một `@ModelAttribute ProfileForm` có thể nhận `name` từ query, `city` từ body và `ownerId` từ path variable nếu route template là `/owners/{ownerId}/profile` và có property tương ứng. Với header, Spring xử lý tên header để phù hợp với property binding (bao gồm bỏ dấu gạch ngang) và chỉ thêm khi không bị request parameters chiếm tên. **Không dựa vào header/path variable để thay thế cơ chế authorization**; client có thể thao túng một phần dữ liệu này.

Quan trọng: **không đồng nhất hàm tĩnh `WebExchangeDataBinder.extractValuesToBind(exchange)` với mọi nguồn bổ sung mà `ExtendedWebExchangeDataBinder` có thể thêm trong handler.** Khi tự tạo base binder bằng `new WebExchangeDataBinder(...)`, bạn đang chọn cơ chế core query/form/multipart; đừng kỳ vọng path variables/headers tự được gán y như MVC annotation resolution.

## 3. Nguồn dữ liệu nào được bind?

### 3.1. Query parameters

~~~http
GET /search?name=Lan&age=21 HTTP/1.1
~~~

`getQueryParams()` lấy key → danh sách giá trị theo URI. Với `@ModelAttribute`, đây là một nguồn cho property binding. Các query names có thể là nested/indexed paths như `tags[0]` hoặc `address.city` nếu DTO hỗ trợ.

Trong **WebFlux**, `@RequestParam` chủ yếu đọc **query parameters**. Đừng mặc định `@RequestParam` của WebFlux sẽ đọc cùng form body giống những thói quen từ Servlet MVC. Với HTML form object, dùng `@ModelAttribute` hoặc API `ServerWebExchange#getFormData()` đúng mục đích.

### 3.2. Form URL-encoded

~~~http
POST /registrations HTTP/1.1
Content-Type: application/x-www-form-urlencoded

name=Lan&age=21&tags%5B0%5D=java
~~~

`getFormData()` trả `Mono<MultiValueMap<String,String>>`. `WebExchangeDataBinder` có thể lấy các form fields và trộn vào map bind. Giá trị bắt đầu là chuỗi; converter chuyển sang property type (`Integer`, `LocalDate`, enum, v.v.) khi binder có cấu hình phù hợp.

**Không cần tự gọi `getFormData()` trong annotated handler trước khi khai báo `@ModelAttribute`**. Spring thực hiện bước đó trong argument resolution.

### 3.3. Multipart

~~~text
multipart/form-data
  field "name" -> text part
  field "avatar" -> file part
~~~

`getMultipartData()` trả `Mono<MultiValueMap<String,Part>>`. `WebExchangeDataBinder` hỗ trợ multipart form data trong binding; nội dung parts được biểu diễn dưới dạng `Part` hoặc các dạng tương thích theo cấu hình binding.

Nếu xử lý **upload file thực sự**, thường rõ ràng hơn khi dùng `@RequestPart FilePart` hoặc truy cập `Part.content()`/`FilePart.transferTo(...)` theo reactive API, thay vì tưởng rằng binder sẽ biến mọi file upload thành `byte[]` sẵn trong memory.

Những request multipart rất lớn có thể tiêu thụ tài nguyên khi parse toàn bộ metadata/part list; cần cấu hình giới hạn codec, server và chính sách lưu trữ phù hợp.

### 3.4. JSON không đi qua property binding của form

~~~http
POST /registrations-json HTTP/1.1
Content-Type: application/json

{"name":"Lan","age":21,"tags":["java"]}
~~~

Trong handler `@RequestBody RegistrationForm`, JSON thường được đọc bởi `HttpMessageReader`/Jackson (với Spring WebFlux), **không phải parse tên field `tags[0]` của HTML form qua `WebExchangeDataBinder.bind(exchange)`**.

`@InitBinder#setAllowedFields(...)` dùng để kiểm soát **property binding**, không thay thế whitelist JSON deserialization. Với JSON, vẫn cần request DTO riêng, cấu hình Jackson phù hợp, validation và authorization.

### 3.5. Nhiều giá trị cùng tên

`MultiValueMap` hỗ trợ nhiều values cho một key:

~~~text
tag=java&tag=reactor
~~~

Trong quá trình extraction, binder chuyển những giá trị đó thành dạng phù hợp với property/constructor conversion. **Đừng khẳng định mọi key nhiều giá trị luôn trở thành một `String` hoặc một `List<String>`**; kết quả tùy hình dạng values, target property type và converter. Khi cần nhiều phần tử có index rõ ràng cho model attribute, dùng `tags[0]`, `tags[1]` và test cấu trúc thật.

## 4. Reactive contract: `Mono<Void>` phải được thực thi

`WebExchangeDataBinder#bind(ServerWebExchange)` trả `Mono<Void>`. Mono này mô tả công việc đọc các nguồn dữ liệu liên quan và bind vào target. Không thể chỉ viết:

~~~java
WebExchangeDataBinder binder =
        new WebExchangeDataBinder(form, "registrationForm");
binder.bind(exchange); // Sai khi bỏ qua publisher.
return Mono.just(form);
~~~

Đoạn trên là **minh họa lỗi**, không phải code cần triển khai. Chỉ tạo publisher chưa chắc đã thực thi công việc. Phải trả publisher vào reactive chain hoặc subscribe thông qua một subscriber phù hợp. Không gọi `block()` trong event-loop WebFlux.

Ví dụ đúng trong một helper/handler có `form` và `exchange`:

~~~java
WebExchangeDataBinder binder =
        new WebExchangeDataBinder(form, "registrationForm");

binder.setAllowedFields("name", "age", "tags[*]");

return binder.bind(exchange)
        .then(Mono.fromSupplier(() -> {
            if (binder.getBindingResult().hasErrors()) {
                return "binding-error";
            }
            return form.getName();
        }));
~~~

**Đây là đoạn logic cần đặt trong method trả `Mono<String>`**, và import `reactor.core.publisher.Mono`, không phải một Java file standalone. `then(...)` đợi bind hoàn tất trước khi đọc target. `Mono.fromSupplier(...)` trì hoãn việc đọc form cho tới lúc publisher downstream thực sự được subscribe.

Trong handler annotated thông thường, Spring quản lý chuỗi bind/validate cho `@ModelAttribute`; bạn không phải tự tạo `WebExchangeDataBinder` trong mỗi endpoint. Manual binder hữu ích khi viết infrastructure, adapter hoặc unit test cho behavior của binding.

### `bind` không tự bằng `validate`

~~~java
WebExchangeDataBinder binder =
        new WebExchangeDataBinder(form, "registrationForm");
binder.setAllowedFields("name", "age");

// Đợi bind hoàn tất trước khi gọi các bước dùng target.
Mono<Void> work = binder.bind(exchange);
~~~

Bộ binder có thể ghi **conversion/typeMismatch errors**. Nhưng constraint annotations như `@NotBlank`, `@Min` cần một `Validator` được cấu hình, rồi gọi `validate()` ở đúng thời điểm, hoặc dùng `@Valid` trong annotated controller để Spring kích hoạt. Đừng coi `WebExchangeDataBinder` là một Bean Validation provider.

Với `@Valid @ModelAttribute`, Spring thực hiện validation theo lifecycle handler và báo lỗi thông qua `BindingResult` hoặc exception phù hợp.

## 5. Project Spring Boot 3.5.7 chạy được

Ví dụ sau giữ đúng phạm vi:
- WebFlux (không phải MVC Servlet).
- `@ModelAttribute` nhận URL-encoded form, gồm query + body.
- `@InitBinder` chỉ cho phép các fields hợp lệ.
- `WebTestClient` xác minh HTTP-level behavior.
- `MockServerWebExchange` và `WebExchangeDataBinder` xác minh manual binder không cần server.
- Jakarta Validation cho `@NotBlank`/`@Min`; `BindingResult` xử lý field errors.

Dùng **Java 17**, Maven và Spring Boot **3.5.7**. Cấu trúc:

~~~text
pom.xml
src/main/java/com/example/webfluxbind/
  WebFluxBindingApplication.java
  RegistrationForm.java
  RegistrationController.java
src/test/java/com/example/webfluxbind/
  RegistrationControllerTest.java
  WebExchangeDataBinderTest.java
~~~

### 5.1. Maven dependencies

~~~xml
<!-- pom.xml -->
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>webflux-exchange-binding</artifactId>
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
            <artifactId>spring-boot-starter-validation</artifactId>
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
</project>
~~~

`spring-boot-starter-webflux` dùng Reactor Netty và WebFlux controllers theo mặc định nếu không có MVC starter. `spring-boot-starter-validation` bổ sung Jakarta Bean Validation provider, `reactor-test` có `StepVerifier`, và `spring-boot-starter-test` có JUnit 5 / Spring test infrastructure.

Nếu một dự án có **cả `spring-boot-starter-web` và `spring-boot-starter-webflux`**, Spring Boot mặc định có thể chọn loại ứng dụng **Servlet MVC**. Để bài tập này thực sự chạy WebFlux, chỉ thêm webflux starter như trên, không trộn Servlet starter vào.

### 5.2. Main application

~~~java
// src/main/java/com/example/webfluxbind/WebFluxBindingApplication.java
package com.example.webfluxbind;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFluxBindingApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebFluxBindingApplication.class, args);
    }
}
~~~

### 5.3. Form DTO

~~~java
// src/main/java/com/example/webfluxbind/RegistrationForm.java
package com.example.webfluxbind;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.util.ArrayList;
import java.util.List;

public class RegistrationForm {

    @NotBlank(message = "Tên không được để trống")
    private String name;

    @NotNull(message = "Tuổi là bắt buộc")
    @Min(value = 18, message = "Tuổi tối thiểu là 18")
    private Integer age;

    private List<@NotBlank String> tags = new ArrayList<>();

    // Cố tình có property không cho người dùng thay đổi.
    private boolean admin;

    public RegistrationForm() {
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }

    public List<String> getTags() {
        return tags;
    }

    public void setTags(List<String> tags) {
        this.tags = tags;
    }

    public boolean isAdmin() {
        return admin;
    }

    public void setAdmin(boolean admin) {
        this.admin = admin;
    }
}
~~~

Form này dùng mutable JavaBean với default constructor/getters/setters để minh họa **property binding**. `List<@NotBlank String>` cho phép kiểm tra từng phần tử khi validation chạy; với `List`, Bean Validation provider thường có value extractor mặc định.

`admin` chỉ dùng để chứng minh rủi ro *mass assignment/over-posting* và cách `allowedFields` ngăn client cập nhật. Trong code production, cách tốt hơn là **không có property nhạy cảm trên request DTO**.

### 5.4. Controller dùng `@ModelAttribute` và `@InitBinder`

~~~java
// src/main/java/com/example/webfluxbind/RegistrationController.java
package com.example.webfluxbind;

import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/registrations")
public class RegistrationController {

    @InitBinder("registrationForm")
    void initBinder(WebDataBinder binder) {
        binder.setAllowedFields("name", "age", "tags[*]");
        binder.setAutoGrowCollectionLimit(10);
    }

    @PostMapping(consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public Mono<ResponseEntity<Map<String, Object>>> register(
            @Valid @ModelAttribute("registrationForm") RegistrationForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            List<String> fields = errors.getFieldErrors().stream()
                    .map(FieldError::getField)
                    .distinct()
                    .sorted()
                    .toList();

            Map<String, Object> payload = Map.of("invalidFields", fields);
            return Mono.just(ResponseEntity.badRequest().body(payload));
        }

        Map<String, Object> payload = Map.of(
                "name", form.getName(),
                "age", form.getAge(),
                "tags", form.getTags(),
                "admin", form.isAdmin()
        );
        return Mono.just(ResponseEntity.ok(payload));
    }

    // Khác với method trên: KHÔNG có BindingResult sau object.
    @PostMapping(path = "/strict",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public Mono<String> strict(
            @Valid @ModelAttribute("registrationForm") RegistrationForm form) {
        return Mono.just("accepted:" + form.getName());
    }
}
~~~

`@InitBinder("registrationForm")` chỉ áp dụng cho binder gắn với đúng object name, không phải mọi argument. `setAllowedFields` là whitelist của **property binding**. Ở đây client được gán `name`, `age` và từng `tags[i]`, nhưng **không được gán `admin`**.

`setAutoGrowCollectionLimit(10)` giới hạn độ lớn auto-grow của list/array khi setter property binding dùng indexed paths. Đây **không phải giới hạn kích thước request HTTP** hay giới hạn form fields tổng thể.

Trong `register`:
- `BindingResult` được đặt **ngay sau** tham số `@ModelAttribute`, nên handler có thể trả danh sách field errors an toàn.
- Khi có lỗi, trả 400 cùng tên fields, không trả rejected values nhạy cảm.
- Khi hợp lệ, trả JSON summary; `Mono.just` đủ cho ví dụ không có bất đồng bộ nghiệp vụ, còn binding ở tầng argument resolution đã được framework hoàn tất trước khi method được gọi.

Trong `strict`, không có `BindingResult`. Nếu validation của `RegistrationForm` thất bại, WebFlux thường ném `WebExchangeBindException` và mặc định trả HTTP 400, trước khi chạy phần thân controller.

Không cần tạo `new WebExchangeDataBinder(...)` trong `RegistrationController`: WebFlux argument resolver đã quản lý binder/validation.

### 5.5. HTTP-level tests bằng `WebTestClient`

~~~java
// src/test/java/com/example/webfluxbind/RegistrationControllerTest.java
package com.example.webfluxbind;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

@AutoConfigureWebTestClient
@SpringBootTest
class RegistrationControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void bindsQueryAndFormAndSuppressesAdmin() {
        client.post()
                .uri("/registrations?age=21")
                .body(BodyInserters.fromFormData("name", "Lan")
                        .with("tags[0]", "java")
                        .with("admin", "true"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.name").isEqualTo("Lan")
                .jsonPath("$.age").isEqualTo(21)
                .jsonPath("$.tags[0]").isEqualTo("java")
                .jsonPath("$.admin").isEqualTo(false);
    }

    @Test
    void reportsBeanValidationFieldErrors() {
        client.post()
                .uri("/registrations")
                .body(BodyInserters.fromFormData("name", " ")
                        .with("age", "16"))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.invalidFields").isArray()
                .jsonPath("$.invalidFields[0]").isEqualTo("age")
                .jsonPath("$.invalidFields[1]").isEqualTo("name");
    }

    @Test
    void reportsConversionErrorForAge() {
        client.post()
                .uri("/registrations")
                .body(BodyInserters.fromFormData("name", "Lan")
                        .with("age", "not-a-number"))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.invalidFields[0]").isEqualTo("age");
    }

    @Test
    void strictFormWithoutBindingResultReturnsBadRequest() {
        client.post()
                .uri("/registrations/strict")
                .body(BodyInserters.fromFormData("name", " ")
                        .with("age", "16"))
                .exchange()
                .expectStatus().isBadRequest();
    }
}
~~~

`BodyInserters.fromFormData(...)` tạo request body dạng `application/x-www-form-urlencoded`, nên test trực tiếp con đường form reading của WebFlux thay vì dùng JSON. Spring Boot test tự cấu hình `WebTestClient` gắn với WebFlux application context.

Điều được xác minh:
1. Query `age` và body `name/tags` cùng vào `RegistrationForm`.
2. Client gửi `admin=true` nhưng response là `false` do `allowedFields`.
3. Bean Validation với `@NotBlank`/`@Min` cho field errors `age` và `name`.
4. Chuỗi không chuyển được thành `Integer` tạo binding error cho `age`.
5. Endpoint không nhận `BindingResult` trả HTTP 400 cho form không hợp lệ.

Ở test 2, tên fields được controller sắp xếp, nên index 0 là `age`, index 1 là `name`. Không ép thứ tự các lỗi bên trong `BindingResult` (không phải hợp đồng quan trọng); chỉ thứ tự **do controller chủ động sort** là ổn định.

### 5.6. Đọc trực tiếp `ServerWebExchange` và gọi `WebExchangeDataBinder`

Bài này cần phân biệt “WebFlux tự bind qua `@ModelAttribute`” với “ta chủ động dùng `WebExchangeDataBinder`”. Test sau không khởi động HTTP server mà tạo mock exchange và kiểm tra state target khi `Mono<Void>` hoàn tất.

~~~java
// src/test/java/com/example/webfluxbind/WebExchangeDataBinderTest.java
package com.example.webfluxbind;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.web.bind.support.WebExchangeDataBinder;
import reactor.test.StepVerifier;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class WebExchangeDataBinderTest {

    private MockServerWebExchange newExchange() {
        return MockServerWebExchange.from(
                MockServerHttpRequest.post("/registrations?age=21")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .body("name=Lan&tags%5B0%5D=java&admin=true"));
    }

    @Test
    void bindReturnsMonoAndUpdatesObjectWhenSubscribed() {
        RegistrationForm form = new RegistrationForm();
        WebExchangeDataBinder binder =
                new WebExchangeDataBinder(form, "registrationForm");

        binder.setAllowedFields("name", "age", "tags[*]");

        StepVerifier.create(binder.bind(newExchange()))
                .verifyComplete();

        assertEquals("Lan", form.getName());
        assertEquals(21, form.getAge());
        assertEquals("java", form.getTags().get(0));
        assertFalse(form.isAdmin());
        assertArrayEquals(
                new String[]{"admin"},
                binder.getBindingResult().getSuppressedFields()
        );
    }

    @Test
    void extractionCanBeObservedBeforeBinding() {
        StepVerifier.create(
                WebExchangeDataBinder.extractValuesToBind(newExchange()))
                .assertNext(values -> {
                    assertEquals("Lan", values.get("name"));
                    assertEquals("21", values.get("age"));
                    assertTrue(values.containsKey("tags[0]"));
                    assertTrue(values.containsKey("admin"));
                })
                .verifyComplete();
    }

    @Test
    void bindDoesNotImplicitlyRunBeanValidation() {
        RegistrationForm form = new RegistrationForm();
        WebExchangeDataBinder binder =
                new WebExchangeDataBinder(form, "registrationForm");
        binder.setAllowedFields("name", "age");

        MockServerWebExchange exchange = MockServerWebExchange.from(
                MockServerHttpRequest.post("/registrations?age=16")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .body("name=%20"));

        StepVerifier.create(binder.bind(exchange))
                .verifyComplete();

        // " " và 16 đều chuyển kiểu được: không có binding error.
        assertEquals(" ", form.getName());
        assertEquals(16, form.getAge());
        assertFalse(binder.getBindingResult().hasErrors());

        // @NotBlank và @Min chỉ chạy khi có validator/validation step.
    }
}
~~~

Ở test 2, `extractValuesToBind(...)` là API để quan sát map **trước khi whitelist và gán property**. Key `admin` có mặt trong map nguồn **không có nghĩa** nó phải được cho bind; `setAllowedFields` kiểm soát bước bind tiếp theo.

**Một lưu ý về test extraction:** Javadoc xác nhận returned map chứa values phục vụ binding; cách Spring biểu diễn scalar so với list/array có thể tùy số lần xuất hiện key. Ở fixture này mỗi key chỉ xuất hiện một lần nên `name`/`age` được mong đợi là string đơn. Khi nâng framework/provider hay thay đổi fixture nhiều values, nên test ở **property-level behavior** thay vì phụ thuộc mọi detail của map nội bộ.

Chạy toàn bộ các test:

~~~bash
mvn test
~~~

**Kết quả kỳ vọng:** 7 JUnit tests PASS (4 `RegistrationControllerTest` + 3 `WebExchangeDataBinderTest`). Đây là khẳng định về kết quả dự kiến theo API và code đã trình bày, **không phải log chạy thực tế**. Maven/Surefire có thể trình bày thứ tự test và stdout khác nhau.

Chạy server để thử bằng curl:

~~~bash
mvn spring-boot:run
~~~

Sau khi server khởi động:

~~~bash
curl -i -X POST "http://localhost:8080/registrations?age=21" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "name=Lan" \
  --data-urlencode "tags[0]=java" \
  --data-urlencode "admin=true"
~~~

JSON response kỳ vọng (không cam kết thứ tự keys):

~~~json
{
  "name": "Lan",
  "age": 21,
  "tags": ["java"],
  "admin": false
}
~~~

Ví dụ không lưu thông tin vào database; `admin=false` là kết quả whitelist, không phải bằng chứng tự thân về một hệ thống authorization hoàn chỉnh.

## 6. Validation và lỗi binding trong WebFlux

### 6.1. Conversion/binding errors

Khi request gửi:

~~~text
age=not-a-number
~~~

và DTO có `Integer age`, converter không tạo được giá trị. `BindingResult` ghi `FieldError` cho `age`; mã lỗi thường là `typeMismatch`. Lỗi này xảy ra trong **binding**, không phải do `@Min(18)`.

Khi gửi:

~~~text
age=16
~~~

conversion thành công, nhưng `@Min(18)` phát hiện value nhỏ hơn điều kiện sau khi Jakarta Bean Validation được kích hoạt.

Với annotated handler, dùng:

~~~java
@PostMapping("/example")
public Mono<String> save(
        @Valid @ModelAttribute("registrationForm") RegistrationForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return Mono.just("invalid");
    }
    return Mono.just("ok");
}
~~~

Đây là **method minh họa riêng**, không có trong `RegistrationController` của project runnable. `BindingResult` **phải ngay sau `@ModelAttribute`**; nếu không, Spring có thể không gắn lỗi vào đúng argument.

### 6.2. `WebExchangeBindException`

Với form `@Valid @ModelAttribute` không có `BindingResult` liền sau, khi validation sai, WebFlux thường phát sinh:

~~~java
org.springframework.web.bind.support.WebExchangeBindException
~~~

Exception này chứa `getBindingResult()` với `FieldError`/`ObjectError` và thông thường được ánh xạ HTTP **400 Bad Request**.

Đừng nhầm `WebExchangeBindException` của WebFlux với `MethodArgumentNotValidException` thường thấy trong MVC Servlet. Trong Spring WebFlux 6.1+, **nếu controller có direct method constraints** như `@RequestParam @Min(1)` trên các argument khác hoặc return constraint, method validation có thể chiếm ưu tiên và tạo `HandlerMethodValidationException`. Code xử lý lỗi cần cân nhắc cả hai loại tương ứng với chữ ký handler.

### 6.3. Model attribute có reactive wrapper

WebFlux cho phép:

~~~java
// Method minh họa thuộc @RestController.
@PostMapping("/reactive")
public Mono<String> submitReactive(
        @Valid @ModelAttribute("registrationForm")
        Mono<RegistrationForm> formMono) {

    return formMono
            .map(form -> "ok:" + form.getName())
            .onErrorResume(
                    WebExchangeBindException.class,
                    error -> Mono.just("invalid"));
}
~~~

Cách này cho phép xử lý lỗi trong reactive chain. **Không khai báo `BindingResult` ngay sau `Mono<RegistrationForm>`**: theo tài liệu WebFlux, cách dùng `BindingResult` trực tiếp yêu cầu argument `@ModelAttribute` **không bọc trong reactive type**. Nếu dùng reactive wrapper, hãy xử lý validation errors thông qua `onErrorResume`/`onErrorMap` hoặc cơ chế error handling phù hợp.

Khi xây response HTTP, đừng chỉ trả chuỗi `"invalid"` với status 200 như đoạn minh họa ở trên nếu API yêu cầu lỗi 400. Trong code thật, trả `ResponseEntity.badRequest()` hoặc xử lý exception toàn cục; đoạn này chỉ trình bày nhánh xử lý reactive error.

### 6.4. Method-level constraints từ Spring Framework 6.1

Có thể viết:

~~~java
@GetMapping("/lookups")
public Mono<String> lookup(@RequestParam @NotBlank String key) {
    return Mono.just(key);
}
~~~

Trong WebFlux 6.1+, direct constraint `@NotBlank` trên method parameter kích hoạt built-in **method validation**; sai giá trị có thể tạo `HandlerMethodValidationException`. Đây là cơ chế khác với object-only `@Valid @ModelAttribute`.

Lưu ý: class-level `@Validated` trên controller có thể chuyển method validation sang con đường AOP proxy. Khi muốn sử dụng built-in method validation trong WebFlux 6.1+, đừng đặt class-level `@Validated` chỉ để kích hoạt cơ chế đã được framework cung cấp.

## 7. Constructor binding và `construct(exchange)`

Kể từ Spring Framework 6.1, `DataBinder`/`WebExchangeDataBinder` hỗ trợ **constructor binding**, hữu ích cho object bất biến. Khác với property binding dùng setter, constructor binding tìm một primary/single constructor có tham số khớp với request values, gọi constructor sau khi chuyển kiểu.

~~~java
public record RegistrationCommand(
        String name,
        Integer age,
        List<String> tags
) {
}
~~~

Đây là **DTO thay thế** để minh họa, không thuộc mã nguồn mutable chạy ở mục 5.

Trong `@ModelAttribute RegistrationCommand command`, framework có thể construct record với query/form data; có thể dùng `@BindParam` để ánh xạ tên request khác tên constructor parameter. Constructor binding hỗ trợ list/map/array thông qua chuỗi được convert hoặc tên indexed/keyed như `tags[0]` và `accounts[2].name`.

API dành cho người xây infrastructure:

~~~java
Mono<Void> construct(ServerWebExchange exchange);
~~~

**Không thể thay `new WebExchangeDataBinder(null).bind(exchange)` để tạo record** rồi kỳ vọng Spring tự biết cần class nào: binder phải biết target type/constructor cần tạo, và sau construct phải kiểm tra `getBindingResult()`. Trong annotated controllers, nên để framework làm việc này trừ khi bạn thực sự xây custom argument resolver.

Các phương thức `setAutoGrowNestedPaths` và `setAutoGrowCollectionLimit` dành cho **property binding** khi gán JavaBean properties; không mặc định chi phối mọi cách constructor binding. Vì thế thay DTO mutable bằng record là một quyết định cần test input names, conversion, constructor errors và validation riêng.

### Bảo vệ constructor/property binding

Spring khuyến nghị model tailored cho web input hoặc constructor binding khi phù hợp. Nếu vẫn phải property bind một object có nhiều fields, hãy dùng `setAllowedFields(...)` theo whitelist. `setDeclarativeBinding(true)` có thể được dùng để ưu tiên constructor binding và chỉ cho property binding với các fields được cho phép; nhưng vẫn phải bảo đảm constructor chỉ nhận những gì caller được quyền cung cấp.

## 8. Câu chuyện nguồn dữ liệu: query, form, URI variables và headers

Một model attribute handler có thể kết hợp:
- Query parameters.
- URL-encoded form fields hoặc multipart fields/parts.
- URI template variables.
- Request headers sau xử lý tên.

**Thứ tự ưu tiên quan trọng:** tài liệu Spring WebFlux mô tả form data và query parameters được ưu tiên so với URI variables/headers. Đừng dựa vào “request header authoritative hơn form” cho thuộc tính cùng tên. Nếu bạn cần một giá trị từ route có ý nghĩa quyền truy cập như `userId`, dùng `@PathVariable` riêng rồi kiểm tra quyền ở service, **không ẩn nó trong một form DTO có setter**.

Ví dụ:

~~~java
@PostMapping("/customers/{customerId}")
public Mono<String> update(
        @PathVariable long customerId,
        @Valid @ModelAttribute CustomerForm form) {
    // customerId dùng riêng cho authorization/lookup;
    // CustomerForm chỉ chứa các trường client được phép sửa.
    return Mono.just("received");
}
~~~

Phương thức trên minh họa kiến trúc, không phải thành phần của project ở mục 5. `CustomerForm` giả định là DTO có các property web-input thích hợp.

Không đưa vào binder tất cả exchange attributes/sessions/principal một cách tùy tiện. Các thuộc tính đó có chức năng riêng; dữ liệu security context nên được xác thực và cấp từ Spring Security, không lấy từ form headers tự khai là “admin”.

### Giới hạn khi đọc body

`ServerWebExchange.getFormData()` parse **toàn bộ** URL-encoded body để tạo `MultiValueMap` và cache kết quả. `getMultipartData()` cũng thu thập map metadata parts. Điều đó **không có nghĩa** WebFlux có thể xử lý form kích thước vô hạn mà không tốn bộ nhớ, chỉ có nghĩa I/O API là reactive.

Để chặn request quá lớn hoặc quá nhiều parts:
- Cấu hình codec `maxInMemorySize` và multipart handling phù hợp với deployment.
- Giới hạn request body ở reverse proxy/server gateway.
- Xác minh tổng số fields, số phần tử list/map và độ sâu nested paths.
- Từ chối hoặc giới hạn file upload theo type/size/quota trước khi đưa vào xử lý nghiệp vụ.
- Với file streaming, tiêu thụ/lưu `Part` theo reactive contract; không lặp lại `Part.content()` khi phần trước đã tiêu thụ.

## 9. Bảo mật: `setAllowedFields` và mass assignment

Khi property binding nhận tên key do người dùng cung cấp, các tên như:

~~~text
admin=true
account.ownerId=another-user
roles[0]=ADMIN
settings.billingEnabled=true
~~~

có thể thành tác động lên object graph nếu target có setters và binder cho phép. Đây là vấn đề *mass assignment* và *over-posting*, không phải lỗi validation về định dạng.

### 9.1. Whitelist là một phòng tuyến

~~~java
@InitBinder("registrationForm")
void initBinder(WebDataBinder binder) {
    binder.setAllowedFields("name", "age", "tags[*]");
}
~~~

Field `admin` không có trong whitelist nên bị **suppress** khi property binder lấy values từ request. Có thể xem:

~~~java
String[] ignored = binder.getBindingResult().getSuppressedFields();
~~~

Nếu bạn đang ở trong annotated controller và chỉ có `BindingResult errors`, có thể dùng `errors.getSuppressedFields()` vì interface `BindingResult` cung cấp API này. Đừng nhầm suppressed fields với `FieldError`: một field bị chặn vì whitelist **không nhất thiết là validation error**.

### 9.2. DTO tách khỏi domain entity

Tốt hơn là không có setters cho `admin`, `role`, `ownerId`, `approved`, `paid` trên public input DTO. Trong thực tế:
1. Parse/bind vào DTO nhỏ chỉ gồm fields dự kiến.
2. Validate format, kích thước, constraints và semantics.
3. Xác thực principal và authorization.
4. Service kiểm tra domain invariants rồi mapping vào entity.
5. Không lấy role/owner chỉ từ request body/query/header.

Không gán trực tiếp `@ModelAttribute` lên JPA entity/aggregate nhạy cảm với nhiều nested properties.

### 9.3. Indexed paths và auto-grow

`tags[0]` là một property path bình thường, nhưng request ác ý có thể gửi `tags[999999]` để ép binder tạo nhiều phần tử hoặc gặp exception. Dùng `setAutoGrowCollectionLimit(10)` trong ví dụ để giới hạn list auto-growth theo quy mô form.

**Giới hạn auto-grow không thay thế giới hạn request size**; không cho rằng mọi index vượt giới hạn sẽ tự chuyển thành một `FieldError` hoặc HTTP 400 nhất quán. Đảm bảo boundary checks, parameter count limit và error handling phù hợp trong thực tế.

### 9.4. Validation không phải authorization

`@Min(18)` kiểm tra tuổi tối thiểu; nó không xác minh người dùng có quyền đăng ký cho `accountId` khác. `@NotBlank` kiểm tra name; nó không chặn người dùng giả mạo email. Dù DTO hoàn toàn hợp lệ, mọi ràng buộc quyền truy cập và state transition vẫn do hệ thống tin cậy kiểm tra.

## 10. Những lỗi thường gặp và cách sửa

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `bind(exchange)` được gọi nhưng target không đổi | Không subscribe/không compose `Mono<Void>` | Trả publisher vào reactive chain hoặc `StepVerifier` trong test |
| Ứng dụng chặn event loop khi bind | Gọi `block()` trong handler | Dùng `then`, `flatMap`, `map` và non-blocking callbacks |
| `@ModelAttribute` không nhận JSON body | JSON không đi qua form property binder | Dùng `@RequestBody`/Jackson |
| `@RequestParam` không đọc form field | WebFlux `@RequestParam` đọc query params | Dùng `@ModelAttribute` hoặc `getFormData()` |
| `age=oops` không bind thành `Integer` | Type conversion failure | Đọc `BindingResult`, error code `typeMismatch` |
| `name=" "` bind thành công dù có `@NotBlank` | Chưa chạy Bean Validation | Dùng `@Valid`/`@Validated` trong controller hoặc cấu hình rồi gọi binder.validate() |
| Không thấy `BindingResult` tại handler | Đặt sai vị trí hoặc bọc form trong `Mono<T>` | Đặt ngay sau non-reactive `@ModelAttribute`, hoặc xử lý reactive errors |
| `WebExchangeBindException` xuất hiện | Model attribute sai và không có `BindingResult` ngay sau | Thêm error handling hoặc `BindingResult` |
| Dùng `HandlerMethodValidationException` thay vì `WebExchangeBindException` | Có direct method constraint làm method validation áp dụng | Kiểm tra handler signature và chính sách exception |
| Property `admin` đổi theo request | Over-posting, không có DTO/allowed fields | Dùng DTO riêng và whitelist |
| Key từ route/header bị form ghi đè | Source precedence của annotated binding | Tách `@PathVariable`/`@RequestHeader` khỏi form để xử lý tin cậy |
| Multipart `Part` chỉ đọc được một lần | Contents stream không cache | Xử lý `Part.content()`/transferTo một lần |
| `tags[999999]` gây lỗi hay allocation | Auto-grow/index vượt giới hạn | Cấu hình limit, reject request sớm, kiểm tra số phần tử |
| Spring Boot app thực tế chạy MVC | Có cả MVC và WebFlux starters | Chỉ dùng `spring-boot-starter-webflux` cho demo, kiểm tra web application type |
| Dùng `HttpServletRequest` trong WebFlux | Nhầm Servlet stack với reactive stack | Dùng `ServerWebExchange`/`ServerHttpRequest` |
| Test mock exchange không giống HTTP thật | Codecs/headers/body format không khớp | Dùng `WebTestClient` cho integration, unit binder test có Content-Type phù hợp |

### Tình huống: đổi cùng một key ở query và form

Ví dụ request có `name=Query` trong URL và `name=Form` trong body. Đừng đặt logic nghiệp vụ quan trọng trên giả định một nguồn luôn thắng nguồn kia ở mọi lớp framework và mọi phiên bản. Bạn có thể:
- Không cho client gửi cùng field ở hai nguồn.
- Đọc nguồn cụ thể trực tiếp bằng `exchange.getRequest().getQueryParams()` hoặc `exchange.getFormData()` nếu business contract yêu cầu.
- Đặt test tích hợp cho trường hợp trùng key, giải thích precedence rõ trong API contract.
- Không dùng các nguồn có thể bị client thay đổi làm chứng cứ xác thực/authorization.

### Tình huống: lỗi hiện ở field nào?

`BindingResult#getFieldErrors()` chứa `FieldError#getField()` là tên field, có thể là `age` hoặc indexed path như `tags[0]`. Nếu ứng dụng trả API response, đưa danh sách tên field và mã lỗi có kiểm soát; không đưa `getRejectedValue()` nguyên dạng nếu dữ liệu có thể nhạy cảm.

## 11. Khi nào tự tạo `WebExchangeDataBinder`?

**Phần lớn annotated WebFlux controllers không cần tự tạo binder**. Dùng `@ModelAttribute`, `@InitBinder`, `@Valid` và `BindingResult` là đủ; framework xử lý lifecycle, body reading và model setup.

Tự dùng binder khi:
- Viết component/test muốn bind dữ liệu từ `ServerWebExchange` vào target do bạn chủ động tạo.
- Cần hạ tầng binding tùy chỉnh ngoài đường annotated controller.
- Cần quan sát chính xác giai đoạn extraction/binding/conversion.
- Đang xây custom argument resolver, với yêu cầu hiểu rõ constructor/target type, validation và lifecycle.

Checklist thủ công:

~~~text
1. Xác định target bean/type và objectName.
2. Chọn allowed fields, conversion, auto-grow, validators.
3. Có ServerWebExchange từ context hợp lệ.
4. Gọi binder.bind(exchange) hoặc construct(exchange) phù hợp.
5. Compose Mono vào reactive chain, không bỏ subscription.
6. Sau completion, đọc BindingResult và target.
7. Nếu cần Bean Validation, kích hoạt rõ ràng, không dựa vào bind ngầm.
8. Không trả raw request values hay thông tin nhạy cảm.
~~~

## 12. Tổng kết và bài tập tự luyện

**Ghi nhớ:**

- `WebExchangeDataBinder` biến query/form/multipart input từ `ServerWebExchange` thành property/constructor values cho Java object.
- `ServerWebExchange` là context reactive của HTTP interaction; `getFormData()`/`getMultipartData()` trả `Mono` và cần được tiêu thụ đúng lifecycle.
- `WebExchangeDataBinder.bind(exchange)` trả `Mono<Void>`, không đồng nghĩa với “đã bind ngay khi viết ra lệnh gọi”.
- `@ModelAttribute` là cách dùng thông dụng; `@RequestBody` JSON đi qua `HttpMessageReader`, không qua cùng property binder.
- Spring WebFlux có `WebExchangeBindException` cho object-only validation và `HandlerMethodValidationException` khi method constraints yêu cầu method validation.
- `BindingResult` phải đặt ngay sau **non-reactive `@ModelAttribute`** nếu muốn xử lý lỗi trong handler.
- Bảo mật binding cần dedicated input DTO, whitelist và giới hạn tài nguyên, không chỉ constraints trên field.

**Bài tập:**
1. Thêm field `country` với một converter từ code `VN`/`SG` sang enum; test valid/invalid conversion.
2. Thêm `tags[1]` và `tags[2]` trong request, xác nhận order và lỗi `@NotBlank` ở phần tử rỗng.
3. Thay `RegistrationForm` bằng record immutable và so sánh constructor binding với property binding.
4. Thử gửi `admin=true`, `tags[9999]`, body rất lớn; giải thích rõ cơ chế nào chặn từng trường hợp.
5. Thử handler `Mono<RegistrationForm>` và xử lý `WebExchangeBindException` trong reactive chain; so sánh với `BindingResult` liền sau non-reactive form.
6. Gửi multipart và xử lý một `FilePart` bằng reactive transfer, đồng thời giữ form DTO không có field được phép chứa bytes của file.

## 13. Tài liệu tham khảo

- Spring Framework 6.2 — WebFlux `@ModelAttribute` (nguồn dữ liệu, constructor/property binding, reactive wrapper, errors): https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/modelattrib-method-args.html
- Spring Framework 6.2 — WebFlux `@InitBinder` và data binding security: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-initbinder.html
- Spring Framework 6.2 — WebFlux validation: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-validation.html
- Spring Framework 6.2 — Reactive Core, form và multipart data: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html
- Spring Framework 6.2 — `ServerWebExchange` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/server/ServerWebExchange.html
- Spring Framework 6.2 — `WebExchangeDataBinder` Javadoc (6.2.6): https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/web/bind/support/WebExchangeDataBinder.html
- Spring Framework 6.2 — `WebExchangeBindException`: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/bind/support/WebExchangeBindException.html
- Spring Boot 3.5 — Testing với `WebTestClient`: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
