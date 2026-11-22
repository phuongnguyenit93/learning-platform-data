# Binding @ModelAttribute trong ngăn xếp phản ứng (Spring WebFlux)

## Mục tiêu bài học

Spring WebFlux là ngăn xếp web phản ứng của Spring Framework, thường chạy trên Reactor Netty. Khi nhận một HTML form, ứng dụng vẫn cần chuyển tên trường và giá trị từ HTTP thành Java object, chuyển đổi kiểu, kiểm tra Bean Validation và báo lỗi. Spring cung cấp `@ModelAttribute` cùng `WebDataBinder` để thực hiện việc đó. **Điểm khác với Spring MVC không phải là bỏ data binding, mà là WebFlux có thể giải quyết model/argument qua luồng reactive và nhận `Mono<Form>` trực tiếp.**

Sau bài học, bạn có thể:

- Hiểu `@ModelAttribute` lấy dữ liệu từ đâu trong WebFlux, khác gì `@RequestParam` và `@RequestBody`.
- Mô tả constructor/property binding, type conversion, tên thuộc tính lồng và validation.
- Dùng hai kiểu handler: **object thường + `BindingResult`** và **`Mono<DTO>` + `onErrorResume(...)`**.
- Đọc `WebExchangeBindException`, phân biệt lỗi binding/validation với `HandlerMethodValidationException`.
- Viết một ví dụ Spring Boot 3 / Java 17+ chạy trên WebFlux, gồm hai endpoint có cùng luật dữ liệu nhưng hai cách xử lý lỗi.
- Kiểm thử qua `WebTestClient` và tránh các lỗi blocking, mass assignment, mất rejected value, hoặc nhầm form với JSON.

## 1. @ModelAttribute làm gì trong WebFlux?

Ví dụ HTTP client gửi:

~~~http
POST /forms/plain
Content-Type: application/x-www-form-urlencoded

name=Lan&age=22&address.city=Ha+Noi
~~~

Đối tượng đích có những property:

~~~java
class SignupForm {
    String name;
    Integer age;
    Address address;
}

class Address {
    String city;
}
~~~

`@ModelAttribute("signup")` bảo Spring WebFlux tạo/lấy object tương ứng rồi bind các dữ liệu có tên phù hợp:

| Request field | Java property | Công việc |
| --- | --- | --- |
| `name=Lan` | `SignupForm.name` | Gán chuỗi |
| `age=22` | `SignupForm.age` | Chuyển `"22"` thành `Integer 22` |
| `address.city=Ha Noi` | `SignupForm.address.city` | Đi theo nested property và gán chuỗi |
| `age=abc` | `Integer age` | Không đổi được kiểu; ghi lỗi `typeMismatch` |
| `name=` | `String name` có `@NotBlank` | Bind được chuỗi rỗng, nhưng sai constraint |

Trong WebFlux, `@ModelAttribute` trên handler argument hỗ trợ dữ liệu form, query parameters, URI path variables và các request headers phù hợp. Khi cùng tên có nhiều nguồn, **form/query parameters ưu tiên hơn path variables và headers**; phần header name có cách chuẩn hóa riêng. Đừng coi đây là cơ chế cho phép client ghi tùy ý mọi property: cần thiết kế DTO và allowlist.

Luồng logic:

~~~text
HTTP request
   |--- query parameters
   |--- application/x-www-form-urlencoded body
   |--- path variables / request headers
   v
WebFlux annotated controller argument resolution
   v
@ModelAttribute("signup")
   |--- lấy model attribute có sẵn / session nếu cấu hình
   |--- hoặc tạo object theo constructor phù hợp
   v
WebDataBinder
   |--- constructor binding / property binding
   |--- ConversionService, Formatter, PropertyEditor
   |--- ghi FieldError nếu conversion/binding thất bại
   v
@Valid / @Validated (nếu khai báo)
   |--- validate constraints của bean
   |--- cascade theo những cạnh @Valid
   v
BindingResult hoặc WebExchangeBindException
   v
handler phản hồi / view / reactive pipeline
~~~

WebFlux dùng kiểu reactive để phối hợp I/O mà không yêu cầu ứng dụng tự gọi `subscribe()` hoặc `block()`. Tuy nhiên, **đừng suy luận Bean Validation hoặc Java property binding tự trở thành tác vụ bất đồng bộ**: các phép chuyển kiểu, kiểm tra metadata và nhiều validator vẫn thực thi đồng bộ khi phần dữ liệu đã sẵn sàng. Không đưa JDBC/blocking network call vào validator hoặc handler trên event-loop.

## 2. WebFlux khác Spring MVC ở những điểm liên quan

| Chủ đề | Spring MVC (Servlet stack) | Spring WebFlux (reactive stack) |
| --- | --- | --- |
| Nền tảng server | Servlet API, thường Tomcat | Reactive server API, thường Reactor Netty |
| `@ModelAttribute SignupForm form` | Hỗ trợ | Hỗ trợ |
| `@ModelAttribute Mono<SignupForm> formMono` | Không phải mẫu chuẩn của MVC | Được hỗ trợ |
| Model có `Mono<Profile>` | Không theo cơ chế native WebFlux | Được hỗ trợ; có thể resolve trước handler/view |
| `BindingResult` sát sau object thường | Có | Có |
| `BindingResult` sát sau `Mono<Form>` | Không phù hợp | **Không hỗ trợ**: phải dùng argument không wrapper |
| `@RequestParam` với form body | Servlet gom query/form thành request parameters | `@RequestParam` chủ yếu **chỉ query parameters** |
| Form fields + query bind vào command object | Có | Có |
| JSON body | `@RequestBody` + message converter | `@RequestBody` + reactive HTTP message reader/codecs |
| Lỗi individual `@ModelAttribute` validation không được xử lý ở handler | Thường `MethodArgumentNotValidException` | Thường **`WebExchangeBindException`** |
| Kiểm tra lỗi cuối đường ống reactive | Servlet exception handling | Có thêm `Mono.onErrorResume(...)` hoặc `@ExceptionHandler` |

**Điểm đặc biệt cần nhớ:** `@RequestParam` trong WebFlux lấy **query parameters**, không phải tên trường form body theo cách Servlet API gộp dữ liệu. Nếu cần bind nhiều trường của form `application/x-www-form-urlencoded`, dùng `@ModelAttribute` (hoặc lấy `ServerWebExchange.getFormData()` cho trường hợp cần kiểm soát thô). Không chuyển một form thành `@RequestBody Mono<Form>` rồi kỳ vọng Jackson đọc form như JSON.

## 3. Hai chữ ký handler hợp lệ

### 3.1. Object thường và BindingResult

~~~java
@PostMapping("/plain")
public Mono<String> handle(
        @Valid @ModelAttribute("signup") SignupForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return Mono.just("signup-form");
    }
    return Mono.just("redirect:/forms/success");
}
~~~

Đây là **snippet mô tả handler render view**, giả định đã có DTO, template và controller phù hợp. `BindingResult` phải đứng **ngay sau** `SignupForm`. Khi có lỗi, controller có thể hiện lại form trong cùng HTTP request. `Mono<String>` là return type của handler, không có nghĩa argument bắt buộc phải là `Mono<Form>`.

`BindingResult` chứa lỗi conversion và validation. Ví dụ nếu `age=abc` nhưng `age` có kiểu `Integer`, Java bean có thể nhận `null`, còn `errors.getFieldError("age").getRejectedValue()` và `errors.getFieldValue("age")` vẫn có thể giữ chuỗi `"abc"` để hiển thị lại.

### 3.2. Reactive wrapper và onErrorResume

~~~java
@PostMapping("/wrapped")
public Mono<String> handleReactive(
        @Valid @ModelAttribute("signup")
        Mono<SignupForm> formMono) {

    return formMono
            .flatMap(form -> Mono.just("redirect:/forms/success"))
            .onErrorResume(
                    WebExchangeBindException.class,
                    ex -> Mono.just("signup-error"));
}
~~~

Đây là snippet giải thích **cách xử lý trong pipeline**, không phải handler độc lập của demo ở mục 5. Khi dùng `Mono<SignupForm>`, **không đặt `BindingResult` ngay sau Mono**: Spring chỉ cho đối số `BindingResult` khi `@ModelAttribute` trước nó là **object không bọc reactive**. Với wrapped form, một lỗi binding/validation có thể được phát ra như tín hiệu `onError`; có thể dùng `onErrorResume(WebExchangeBindException.class, ...)` để chuyển sang response/view phù hợp.

Ví dụ này trả một view lỗi chung; nếu thật sự muốn render lại **giá trị đã nhập**, phải chuyển object và lỗi từ `ex.getBindingResult()`/`ex.getModel()` vào model của view một cách đúng đắn, hoặc chọn cách object thường + `BindingResult` đơn giản hơn. Đừng chỉ trả view name mới rồi giả định dữ liệu từ Mono đã tự được giữ đầy đủ trong model.

### 3.3. Điều không đúng

~~~java
// SAI: BindingResult không ghép cặp với Mono<Form>
@PostMapping("/broken")
Mono<String> broken(
        @Valid @ModelAttribute("signup") Mono<SignupForm> form,
        BindingResult errors) {
    return Mono.just("signup-form");
}
~~~

Đây là **anti-pattern**, không chạy theo contract được mô tả. Không áp dụng máy móc quy tắc “luôn đặt BindingResult sát sau form” mà bỏ qua kiểu wrapper reactive.

## 4. Spring WebFlux nhận form theo cách nào?

### 4.1. Form URL-encoded

Content type thường dùng cho HTML form:

~~~http
Content-Type: application/x-www-form-urlencoded
~~~

Request body là các cặp `name=value` đã URL-encode. Spring đọc dữ liệu đó bằng các API phù hợp rồi bind theo property names trên command object. Ví dụ `address.city` là tên property lồng. Đừng gửi đối tượng JSON trong body này rồi kỳ vọng `@ModelAttribute` tự deserialize bằng Jackson.

### 4.2. Query và path variables

`@ModelAttribute` có thể lấy giá trị từ query/path/header bên cạnh form fields. Với endpoint `POST /owners/42/edit?name=Lan`, có thể bind `name` từ query; chỉ khi model có property tương ứng thì giá trị mới được dùng. Khi field cùng tên xuất hiện nhiều nguồn, form/query có precedence cao hơn path/header. Phải kiểm tra chính sách binding để tránh kẻ tấn công lợi dụng nguồn dữ liệu thay thế.

Trong handler cần **một tham số query riêng** thì `@RequestParam("page") int page` phù hợp. Nhưng riêng `@RequestParam("name")` của WebFlux **không** đọc form body theo cùng quy ước với Spring MVC. Đây là nguồn nhầm lẫn quan trọng khi chuyển ứng dụng từ Servlet sang reactive stack.

### 4.3. Multipart

WebFlux xử lý multipart với hạ tầng riêng (ví dụ `FilePart`/`Part`). Data binding có thể lấy dữ liệu form và parts vào command object trong trường hợp thích hợp, nhưng với file lớn cần dùng streaming-aware API và chính sách upload/giới hạn file; đừng giữ cả file vào Java bean chỉ để thỏa mô hình `@ModelAttribute` khi có cách xử lý phù hợp hơn.

### 4.4. JSON là một đường khác

Với:

~~~http
POST /api/orders
Content-Type: application/json

{"name":"Lan","age":22}
~~~

Controller thông thường chọn `@RequestBody OrderDto` hoặc `@RequestBody Mono<OrderDto>`. Spring WebFlux đọc nội dung qua codecs/message readers. Vì vậy:

- `@ModelAttribute`: hướng đến data binding form/query/path/header sang command object.
- `@RequestBody`: hướng đến giải mã HTTP body theo media type, như JSON.
- `@RequestParam`: query parameter riêng lẻ trong WebFlux.

Chọn annotation theo **nguồn và định dạng dữ liệu**, không chỉ theo việc return type của handler có phải `Mono` hay không.

## 5. Ví dụ Java 17+ / Spring Boot 3.5.7: hai đường binding

Ví dụ này dùng **WebFlux với REST-style text responses** để thấy chính xác status, giá trị và lỗi của hai kiểu handler mà không phụ thuộc template engine. Sau đó mục 7 sẽ giải thích cách dùng chung dữ liệu để render HTML form. Ví dụ không sử dụng Spring MVC, không dùng database và không chặn luồng bằng `block()`.

### 5.1. Cấu trúc dự án

~~~text
webflux-modelattribute-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/webflux/
    │       ├── FormsApplication.java
    │       ├── SignupForm.java
    │       └── FormController.java
    └── test/
        └── java/com/example/webflux/
            └── FormControllerTest.java
~~~

### 5.2. pom.xml

~~~xml
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
    <artifactId>webflux-modelattribute-demo</artifactId>
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

`spring-boot-starter-webflux` chọn WebFlux với Reactor Netty theo thiết lập Boot thường dùng. `spring-boot-starter-validation` cung cấp Jakarta Bean Validation provider; `spring-boot-starter-test` hỗ trợ JUnit và WebTestClient.

**Đừng thêm `spring-boot-starter-web` chỉ vì quen Spring MVC.** Khi cả hai starter MVC và WebFlux có mặt trong một ứng dụng Spring Boot, Boot mặc định chọn kiểu ứng dụng Servlet/MVC nếu không được ép cấu hình khác; điều đó có thể khiến bạn tưởng đang chạy WebFlux trong khi thực tế không phải. Demo cố ý chỉ thêm WebFlux starter.

### 5.3. FormsApplication.java

~~~java
package com.example.webflux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FormsApplication {

    public static void main(String[] args) {
        SpringApplication.run(FormsApplication.class, args);
    }
}
~~~

### 5.4. SignupForm.java — form DTO

~~~java
package com.example.webflux;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class SignupForm {

    @NotBlank
    private String name;

    @NotNull
    @Min(18)
    private Integer age;

    @Valid
    private Address address = new Address();

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

    public Address getAddress() {
        return address;
    }

    public void setAddress(Address address) {
        this.address = address;
    }

    public static class Address {
        @NotBlank
        private String city;

        public String getCity() {
            return city;
        }

        public void setCity(String city) {
            this.city = city;
        }
    }
}
~~~

Ba rules:

1. `name` phải có nội dung (`@NotBlank`).
2. `age` phải hiện diện và từ 18 trở lên (`@NotNull` + `@Min(18)`).
3. `address.city` phải có nội dung **vì** `address` được đánh dấu `@Valid`, rồi validator đi vào object con.

`address` được khởi tạo để property binding xử lý `address.city`. `@Valid` một mình bỏ qua object null; nếu nghiệp vụ bắt buộc có object `address`, đặt thêm `@NotNull` trên field đó. Với form HTML, DTO dùng mutable JavaBean properties giúp ví dụ dễ theo dõi; ở code production có thể cân nhắc constructor binding/immutable DTO nếu phù hợp.

### 5.5. FormController.java — thường và wrapped

~~~java
package com.example.webflux;

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
import org.springframework.web.bind.support.WebExchangeBindException;
import reactor.core.publisher.Mono;

import java.util.stream.Collectors;

@RestController
@RequestMapping("/forms")
public class FormController {

    @InitBinder("signup")
    void configureBinder(WebDataBinder binder) {
        binder.setAllowedFields(
                "name", "age", "address.city");
    }

    private static String fields(BindingResult errors) {
        return errors.getFieldErrors().stream()
                .map(FieldError::getField)
                .distinct()
                .sorted()
                .collect(Collectors.joining(","));
    }

    private static String summary(SignupForm form) {
        return form.getName()
                + "/" + form.getAge()
                + "/" + form.getAddress().getCity();
    }

    @PostMapping(
            path = "/plain",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<ResponseEntity<String>> plain(
            @Valid @ModelAttribute("signup") SignupForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return Mono.just(ResponseEntity.badRequest()
                    .body("invalid:" + fields(errors)));
        }

        return Mono.just(ResponseEntity.ok(
                "accepted:" + summary(form)));
    }

    @PostMapping(
            path = "/wrapped",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<ResponseEntity<String>> wrapped(
            @Valid @ModelAttribute("signup")
            Mono<SignupForm> formMono) {

        return formMono
                .map(form -> ResponseEntity.ok(
                        "accepted:" + summary(form)))
                .onErrorResume(
                        WebExchangeBindException.class,
                        ex -> Mono.just(
                                ResponseEntity.badRequest().body(
                                        "invalid:" + fields(ex))));
    }
}
~~~

**Phân tích:**

- `plain(...)` dùng object thường và `BindingResult` ngay sau để handler chủ động kiểm tra `hasErrors()`. Kết quả là `Mono<ResponseEntity<String>>` vì response thuộc reactive handler contract.
- `wrapped(...)` lấy `Mono<SignupForm>`, **không thêm `BindingResult`**. Nếu binding/validation thất bại, lỗi được chuyển qua `onErrorResume(WebExchangeBindException.class, ...)`.
- `WebExchangeBindException` cung cấp các API của `BindingResult`, nên helper `fields(BindingResult)` được dùng chung cho cả hai mode. `FieldError.getField()` trả tên field như `age` hoặc `address.city`.
- `distinct().sorted()` giúp response ổn định khi một field có nhiều lỗi (`@NotNull`, `typeMismatch`...) hoặc provider trả lỗi theo thứ tự khác nhau.
- `summary(form)` chỉ gọi khi form đã qua validation; demo chỉ xuất các giá trị không nhạy cảm. Không đưa raw `getInvalidValue()` hoặc `rejectedValue` vào HTTP response production.
- `@InitBinder("signup")` cho phép bind đúng ba property và chặn ghi tùy ý các field khác. Việc này bổ trợ cho DTO design, không thay validation.
- Không có `Thread.sleep(...)`, `block()` hay I/O chặn trong handler. Với xử lý lưu thật, dùng API reactive phù hợp (ví dụ R2DBC) thay vì chặn event loop bằng JDBC.

Ở code này `@RestController` được chọn **chỉ để xuất text dễ kiểm thử**. `@ModelAttribute` hoạt động trong cả `@Controller` render HTML và `@RestController`; kiểu response không làm thay đổi quy tắc binding.

### 5.6. Lệnh chạy và kết quả dự kiến

Tại thư mục `pom.xml`, dùng JDK 17+ / Maven:

~~~bash
mvn spring-boot:run
~~~

Trong terminal khác, gửi form URL-encoded:

~~~bash
curl -i -X POST "http://localhost:8080/forms/plain" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "name=Lan" \
  --data-urlencode "age=22" \
  --data-urlencode "address.city=Ha Noi"
~~~

Phản hồi mong đợi: HTTP **200**, response body chính xác:

~~~text
accepted:Lan/22/Ha Noi
~~~

Thử type mismatch:

~~~bash
curl -i -X POST "http://localhost:8080/forms/plain" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "name=Lan" \
  --data-urlencode "age=abc" \
  --data-urlencode "address.city=Ha Noi"
~~~

Phản hồi mong đợi: HTTP **400**, body:

~~~text
invalid:age
~~~

Đổi URL thành `/forms/wrapped` với cùng dữ liệu hợp lệ/sai: bạn nhận kết quả 200/400 và body tương ứng. Điểm khác nằm ở **vị trí xử lý lỗi của code**, không phải ràng buộc dữ liệu hay HTTP contract.

Nếu gửi `address.city=` với các trường còn lại hợp lệ, response body sẽ là:

~~~text
invalid:address.city
~~~

Ví dụ này có thể phát sinh log khi ứng dụng khởi động; không đặt kỳ vọng vào stdout của Boot vì log/port/timestamp khác nhau. Các **HTTP response bodies** ở trên do chính controller demo định nghĩa.

## 6. Kiểm thử WebFlux bằng WebTestClient

WebFlux nên dùng `WebTestClient` để kiểm tra cả status, headers và body, thay vì sử dụng `MockMvc` (công cụ thường dành cho Spring MVC/Servlet).

Tạo file `src/test/java/com/example/webflux/FormControllerTest.java`:

~~~java
package com.example.webflux;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

@SpringBootTest
@AutoConfigureWebTestClient
class FormControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void plainValid() {
        client.post().uri("/forms/plain")
                .contentType(
                        MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("name", "Lan")
                        .with("age", "22")
                        .with("address.city", "Ha Noi"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("accepted:Lan/22/Ha Noi");
    }

    @Test
    void plainTypeMismatch() {
        client.post().uri("/forms/plain")
                .contentType(
                        MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("name", "Lan")
                        .with("age", "abc")
                        .with("address.city", "Ha Noi"))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody(String.class)
                .isEqualTo("invalid:age");
    }

    @Test
    void plainNestedValidation() {
        client.post().uri("/forms/plain")
                .contentType(
                        MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("name", "Lan")
                        .with("age", "22")
                        .with("address.city", ""))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody(String.class)
                .isEqualTo("invalid:address.city");
    }

    @Test
    void wrappedValid() {
        client.post().uri("/forms/wrapped")
                .contentType(
                        MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("name", "Lan")
                        .with("age", "22")
                        .with("address.city", "Ha Noi"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("accepted:Lan/22/Ha Noi");
    }

    @Test
    void wrappedValidationFailure() {
        client.post().uri("/forms/wrapped")
                .contentType(
                        MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("name", "")
                        .with("age", "22")
                        .with("address.city", "Ha Noi"))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody(String.class)
                .isEqualTo("invalid:name");
    }

    @Test
    void wrappedTypeMismatch() {
        client.post().uri("/forms/wrapped")
                .contentType(
                        MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("name", "Lan")
                        .with("age", "abc")
                        .with("address.city", "Ha Noi"))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody(String.class)
                .isEqualTo("invalid:age");
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Sáu test chứng minh các trường hợp:

1. Object thường bind chính xác form và trả HTTP 200.
2. Lỗi `age=abc` được ghi là lỗi binding, handler trả 400.
3. Lỗi bean con `address.city` được tìm thấy qua `@Valid`.
4. Mono-wrapped argument nhận form hợp lệ.
5. `@NotBlank` của `name` gây tín hiệu lỗi và được `onErrorResume` xử lý.
6. Mono-wrapped argument vẫn giữ khả năng nhận lỗi conversion.

`BodyInserters.fromFormData(...)` gửi đúng dữ liệu form URL-encoded. Nhờ vậy test không vô tình gửi JSON rồi gán nhãn form. `@AutoConfigureWebTestClient` giúp WebTestClient kết nối với WebFlux application context trong bài test; không cần khởi động trình duyệt.

## 7. Render HTML form bằng @Controller thay vì text response

Nếu ứng dụng dùng Thymeleaf hoặc template engine tương thích WebFlux, bạn có thể giữ mô hình object thường + `BindingResult`:

~~~java
@Controller
@RequestMapping("/signup")
class SignupPageController {

    @GetMapping
    String form(Model model) {
        model.addAttribute("signup", new SignupForm());
        return "signup";
    }

    @PostMapping
    Mono<String> submit(
            @Valid @ModelAttribute("signup") SignupForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return Mono.just("signup");
        }

        // Sau validation, có thể gọi service reactive.
        return Mono.just("redirect:/signup/success");
    }
}
~~~

Đây là **snippet minh họa**, không nằm trong file chạy được ở mục 5. Để thực thi, cần thêm `spring-boot-starter-thymeleaf`, imports, template `signup.html`, route thành công và chú ý response/security của ứng dụng. Khi form sai, trả lại cùng view (cùng request) sẽ giữ model object và `BindingResult` cho template.

Với Thymeleaf:

~~~html
<form th:action="@{/signup}"
      th:object="${signup}"
      method="post">

    <input type="text" th:field="*{name}">
    <span th:errors="*{name}"></span>

    <input type="text" inputmode="numeric"
           th:field="*{age}">
    <span th:errors="*{age}"></span>

    <input type="text" th:field="*{address.city}">
    <span th:errors="*{address.city}"></span>

    <button type="submit">Đăng ký</button>
</form>
~~~

Đây là **template snippet**, chưa có `html/head/body`. `th:object`, `th:field`, `th:errors` tận dụng binding status; nếu `age=abc` không thể chuyển thành `Integer`, `BindingResult.getFieldValue("age")` có thể trả chuỗi người dùng đã gõ, cho phép template hiển thị lại thay vì dựa vào `form.getAge()` (có thể `null`).

Không thay model attribute bằng object rỗng khi lỗi. Không tự động `redirect:/signup` sau khi form sai nếu chưa chuyển cả object và `BindingResult` qua trạng thái thích hợp: redirect mở request mới, có thể làm mất input và error messages. Mẫu phổ biến: **return view khi lỗi, redirect sau thành công**.

### Khi model chứa Mono<T>

Một khả năng riêng của WebFlux là controller cung cấp model attribute dưới dạng reactive publisher:

~~~java
@ModelAttribute
void loadProfile(@RequestParam String id, Model model) {
    model.addAttribute(
            "profile",
            profileService.findById(id)); // Mono<Profile>
}

@PostMapping("/profile/save")
Mono<String> save(
        @ModelAttribute("profile") Profile profile,
        BindingResult errors) {
    // ...
    return Mono.just("profile");
}
~~~

Đây là **snippet kiến trúc**, giả định có `profileService`, `Profile`, và id query parameter; không là code chạy độc lập. WebFlux có thể resolve publisher trong model trước khi đưa object cho handler **không wrapper**, và resolve giá trị publisher trước khi render view. Không dùng `subscribe()` thủ công để “đẩy” dữ liệu vào model.

Nếu bản thân method argument là `Mono<Profile>`, bạn phải xử lý các lỗi trong pipeline thay cho `BindingResult` đứng sát sau. Phân biệt rõ **model attribute được cung cấp bất đồng bộ** với **argument được khai báo reactive**.

## 8. Validation và exception trong WebFlux

### 8.1. @Valid và @Validated trên @ModelAttribute

~~~java
@Valid @ModelAttribute("signup") SignupForm form
~~~

Spring chạy Bean Validation theo nhóm mặc định trên object sau binding. Những constraint như `@NotBlank`, `@Min`, và cascade qua `@Valid` trên nested fields sẽ xuất hiện trong `BindingResult` hoặc lỗi được ném ra nếu không có handler cho chúng.

Nếu cần groups:

~~~java
@Validated({Default.class, FinalStep.class})
@ModelAttribute("signup") SignupForm form
~~~

`Default` thuộc `jakarta.validation.groups.Default`, `FinalStep` là marker interface nghiệp vụ do bạn tự định nghĩa. Group riêng chỉ chạy khi được chọn; `@Valid` không có thuộc tính để chọn groups tại điểm sử dụng. Việc đặt `@Validated` ở cấp class controller cho AOP method validation khác với `@Validated` đặt trực tiếp lên form argument.

### 8.2. WebExchangeBindException

Khi object `@ModelAttribute` được bind/validate và không có `BindingResult` sát sau, Spring WebFlux mặc định có thể ném **`org.springframework.web.bind.support.WebExchangeBindException`**. Exception này cung cấp dữ liệu `BindingResult` như `getFieldErrors()`, `getFieldValue()`, `getAllErrors()`, `getModel()` và response status thích hợp (thường **400 Bad Request** cho lỗi input).

Các API quan trọng:

~~~java
for (FieldError field : ex.getFieldErrors()) {
    String name = field.getField();
    Object rejected = field.getRejectedValue();
    boolean bindingProblem = field.isBindingFailure();
    String code = field.getCode();

    // name, code và loại lỗi phục vụ debug/mapping;
    // đừng log giá trị nhạy cảm.
}
~~~

Snippet này giả định `ex` là `WebExchangeBindException` hoặc một `BindingResult` phù hợp; không chạy độc lập.

Trong controller nhận `Mono<Form>`, bạn có thể xử lý exception đó ngay trong pipeline:

~~~java
return formMono
        .flatMap(service::save) // giả định save trả Mono<Result>
        .onErrorResume(WebExchangeBindException.class, ex -> {
            // Chuyển sang response lỗi phù hợp.
            return fallback(ex);
        });
~~~

Đây chỉ là pattern minh họa, `service`/`fallback` chưa có trong demo. Khi dùng `onErrorResume`, chọn exception type cụ thể để không “nuốt” mọi lỗi hệ thống thành lỗi form 400.

### 8.3. HandlerMethodValidationException

Từ Spring Framework 6.1, nếu controller method có **constraint trực tiếp** như `@Min(1)` trên một tham số hoặc constraint trên return value, native method validation có thể chạy cho cả chữ ký:

~~~java
@PostMapping("/check")
Mono<String> check(
        @Valid @ModelAttribute("signup") SignupForm form,
        @RequestParam @Min(1) int page) {
    return Mono.just("ok");
}
~~~

Snippet giả định imports phù hợp. Khi method validation báo lỗi và chúng không thể được xử lý hoàn toàn bằng những `Errors`/`BindingResult` sát sau các tham số tương ứng, WebFlux có thể ném `HandlerMethodValidationException`. **`@Valid` tự nó không phải một direct constraint**, nên không mặc nhiên gây method validation. `@NotNull` trên chính method parameter lại có thể làm thay đổi đường đi.

| Trường hợp | Hành vi thường gặp |
| --- | --- |
| `@Valid @ModelAttribute Form form, BindingResult errors` | Handler nhận lỗi, chủ động render/đáp ứng |
| `@Valid @ModelAttribute Form form` không có BindingResult | `WebExchangeBindException` nếu bean không hợp lệ |
| `@Valid @ModelAttribute Mono<Form> formMono` | Có thể xử lý `WebExchangeBindException` trong reactive pipeline |
| Method có direct constraint cần validation toàn method | `HandlerMethodValidationException` khi lỗi không được handle tại argument |
| Lỗi server/validator configuration | Không nên biến thành input error chỉ vì có chữ “validation” |

Trong một số chữ ký, method validation có thể phối hợp với `Errors`; handler chỉ được gọi nếu **mọi** vi phạm đều gắn với những tham số có đối số `Errors`/`BindingResult` tương ứng. Nếu một tham số khác sai và không có chỗ nhận lỗi, framework ném exception thay vì cho handler chạy như bình thường.

### 8.4. Response và error schema

Với REST API thật, có thể dùng `@RestControllerAdvice` hoặc `@ExceptionHandler` để chuẩn hóa lỗi WebFlux thành JSON/ProblemDetail có fields, codes, messages và status. Đừng serialise nguyên `WebExchangeBindException` hoặc target bean cho client: chúng có thể chứa dữ liệu nhạy cảm. `MessageSource` có thể dùng các mã trong `FieldError.getCodes()` để bản địa hóa.

Với form HTML, lỗi validation thường có cách UX tốt hơn là render lại view cùng model/binding state. Chỉ sau khi form hợp lệ mới chuyển sang một redirect hoặc reactive service call phù hợp.

## 9. Data binding, constructor binding và bảo mật

### 9.1. Constructor và property binding

Trong các phiên bản Spring hiện đại, `@ModelAttribute` có thể sử dụng constructor binding (ví dụ immutable record, constructor với tên tham số) và/hoặc property binding với setters. WebFlux vẫn dùng hạ tầng `WebDataBinder` và conversion. Nếu dùng constructor binding trong Java, tên tham số cần được giữ trong bytecode (ví dụ compiler `-parameters`) hoặc có cơ chế mapping `@BindParam` phù hợp.

Ví dụ ý tưởng immutable DTO:

~~~java
public record SignupInput(
        String name,
        Integer age) {
}
~~~

Đây là snippet minh họa constructor binding; nếu cần validation, đặt constraint thích hợp trên record components và chọn nhóm theo nghiệp vụ. Không nhất thiết một form phải là JavaBean mutable, nhưng ví dụ mục 5 dùng JavaBean để mô tả rõ nested property binding.

### 9.2. Giới hạn property có thể ghi

**Không bind HTTP request trực tiếp vào entity có field như `role`, `isAdmin`, `accountBalance`, `approved`.** Kẻ tấn công có thể cố gửi tên field bất ngờ. Dùng DTO riêng và kiểm soát property binding, ví dụ:

~~~java
@InitBinder("signup")
void configure(WebDataBinder binder) {
    binder.setAllowedFields(
            "name", "age", "address.city");
}
~~~

Đây là đoạn đã có trong chương trình đầy đủ. Với constructor binding, chỉ constructor parameters tương ứng được nhận; vẫn cần kiểm tra ownership, authentication, authorization và domain rules trong service.

### 9.3. Reactive không đồng nghĩa tự động an toàn về blocking

Data binding thường có bước lập bean, reflection, format/conversion và Bean Validation đồng bộ trong thời gian xử lý argument. Điều đó không mặc nhiên gây lỗi kiến trúc; các thao tác in-memory ngắn là bình thường. Nhưng custom converter/validator gọi JDBC, remote HTTP blocking hoặc `Thread.sleep` có thể chặn event-loop, làm giảm throughput của toàn WebFlux server. Giữ kiểm tra dữ liệu tại bước binding nhanh, không side-effect; kiểm tra cần I/O nên thiết kế ở tầng reactive service và thực hiện theo lifecycle phù hợp, thay vì ném một lời gọi chặn vào `ConstraintValidator.isValid()`.

Không gọi `Mono.block()` trong controller WebFlux để “đợi binding xong”. WebFlux argument resolver, Reactor và framework sẽ phối hợp subscribe/demand theo contract.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách giải quyết |
| --- | --- | --- |
| Form fields không vào object | Chuyển từ MVC sang WebFlux nhưng dùng `@RequestParam` cho body form | Dùng `@ModelAttribute` cho command object |
| Gửi JSON vào form handler nhưng không bind | `@ModelAttribute` không phải JSON message reader | Dùng `@RequestBody` cho JSON |
| `BindingResult` sau `Mono<Form>` không hoạt động | Chữ ký không được WebFlux hỗ trợ | Dùng plain Form + BindingResult hoặc Mono + onErrorResume |
| Bean có `@NotBlank` nhưng không bị chặn | Thiếu `@Valid`/`@Validated` hoặc provider Jakarta Validation | Bổ sung annotation và starter validation |
| Field con sai nhưng không có lỗi | Thiếu `@Valid` trên quan hệ `address` | Khai báo cascade ở đúng cạnh |
| `age=abc` thành null trên model | Conversion sang `Integer` thất bại | Đọc rejected value từ BindingResult, không dựa vào getter |
| Form bị xóa sau lỗi | Controller redirect hoặc thay model attribute | Render cùng view và giữ binding state |
| Unexpected `HandlerMethodValidationException` | Có constraint trực tiếp trên method parameter hoặc return value | Xem method signature và phân biệt với individual bean validation |
| Test dùng MockMvc trong WebFlux | Bộ test không phù hợp web stack | Dùng `WebTestClient` |
| Kết quả lỗi khác thứ tự | Danh sách/collection lỗi không có thứ tự UI ổn định | Sắp field/message theo rule rõ ràng |
| Handler không thực thi khi lỗi | Không có BindingResult hoặc lỗi phát ra trong Mono | Bắt đúng đường lỗi với BindingResult/onErrorResume |
| Có cả MVC và WebFlux dependencies | Boot chọn Servlet app type thay vì reactive | Kiểm tra dependency tree và application type |
| App nghẽn dưới tải | Gọi blocking APIs ở event-loop | Dùng reactive driver hoặc chuyển tác vụ blocking sang scheduler thích hợp có kiểm soát |
| Field nhạy cảm bị cập nhật ngoài ý muốn | Mass assignment qua property binding | Dùng DTO, allowedFields và kiểm soát quyền |
| Dùng `subscribe()` trong controller | Tách lifecycle khỏi framework | Trả Mono/Flux cho WebFlux quản lý |

### Debug thực tế

1. Kiểm tra request method/URL, `Content-Type` và payload thực tế bằng browser DevTools hoặc WebTestClient.
2. Xác nhận app chạy WebFlux, không vô tình chạy Servlet/MVC do dependency `spring-boot-starter-web`.
3. Xác nhận handler có `@ModelAttribute` tường minh, model attribute name và field names tương ứng.
4. Kiểm tra DTO có constructor/properties bind được, nested objects đã khởi tạo (nếu dùng setters) và các allowed fields.
5. Phân biệt lỗi conversion (`typeMismatch`, `isBindingFailure()==true`) với constraint validation (`@NotBlank`, `@Min`).
6. Nếu dùng plain object, kiểm tra `BindingResult` sát ngay sau object; nếu dùng Mono-wrapped, kiểm tra `onErrorResume` trong chain thật.
7. Nếu gặp lỗi method-level, tìm các direct `@Constraint` trên handler parameters/return.
8. Nếu render HTML, xem model và `BindingResult.MODEL_KEY_PREFIX + attributeName`, kiểm tra `th:object`/`th:field`.
9. Kiểm tra logs có blocking calls, không log giá trị cá nhân khi debug binding.
10. Viết WebTestClient test cho input hợp lệ, type mismatch, nested validation và cả wrapped/plain modes.

## 11. Bài tập tự kiểm tra

**Bài tập 1 — Nguồn dữ liệu:** Trong WebFlux, vì sao `@RequestParam("name")` không phải lựa chọn đủ để bind một HTML form POST? Vì nó chỉ truy cập query parameter; muốn gom các trường form, dùng `@ModelAttribute` với command object.

**Bài tập 2 — Hai kiểu đối số:** Nêu sự khác nhau giữa `@Valid @ModelAttribute SignupForm form, BindingResult errors` và `@Valid @ModelAttribute Mono<SignupForm> formMono`. Tại sao không gắn `BindingResult` sát sau Mono? WebFlux chỉ hỗ trợ đối số BindingResult trực tiếp với model attribute **không wrapper**.

**Bài tập 3 — Conversion:** Khi gửi `age=abc`, đâu là lỗi binding và đâu là lỗi validation? Tại sao Java `Integer age` không giữ được chuỗi `"abc"`? Cách lấy rejected update từ `FieldError` như thế nào?

**Bài tập 4 — Nested:** Bỏ `@Valid` trên `SignupForm.address` rồi gửi `address.city=`. Dự đoán điều gì xảy ra và giải thích cơ chế cascade.

**Bài tập 5 — Reactive error handling:** Bỏ `onErrorResume(WebExchangeBindException.class, ...)` khỏi `wrapped(...)`. Khi input sai, lỗi có thể được truyền cho WebFlux exception handlers; mặc định là phản hồi 400, nhưng body lỗi sẽ không còn do controller tự định nghĩa.

**Bài tập 6 — View:** Tạo `@Controller` render `signup.html` qua Thymeleaf; dùng `BindingResult` giữ giá trị khi sai và redirect khi thành công. Vì sao trả view trong cùng request dễ hơn redirect ngay khi lỗi?

**Bài tập 7 — Nhóm validation:** Thêm marker group `FinalStep` và `@NotBlank(groups=FinalStep.class)` cho một field. Dùng `@Validated({Default.class, FinalStep.class})` trong endpoint gửi cuối; thử `@Validated(FinalStep.class)` để thấy constraint Default có thể bị bỏ qua.

**Bài tập 8 — Security:** Thử gửi thêm `role=ADMIN` vào POST form. Vì sao DTO riêng và `setAllowedFields(...)` an toàn hơn việc bind thẳng entity?

**Bài tập 9 — Blocking:** Nếu custom validator gọi JDBC đồng bộ trong WebFlux, nguy cơ gì xảy ra? Hãy chuyển việc kiểm tra cần I/O sang một reactive service phù hợp, đồng thời giữ các constraint in-memory tại boundary.

## Kết luận

`@ModelAttribute` trên WebFlux **vẫn là data binding sang object** từ form/query/path/header. Sự khác biệt nổi bật so với MVC là hỗ trợ **reactive model values và model attribute arguments**, ví dụ `Mono<SignupForm>`. Chọn một trong hai mô hình lỗi rõ ràng:

~~~text
@Valid @ModelAttribute SignupForm form
    + BindingResult ngay sau
    → kiểm tra errors.hasErrors() trong handler

@Valid @ModelAttribute Mono<SignupForm> formMono
    → kiểm tra qua Mono.onErrorResume(WebExchangeBindException.class, ...)
    → không gắn BindingResult sau Mono
~~~

`WebExchangeBindException` là loại exception riêng của WebFlux cho lỗi binding/validation argument; `HandlerMethodValidationException` có thể xuất hiện khi native method validation áp dụng cho cả chữ ký. Hãy dùng `WebTestClient`, DTO có allowlist, các constraint đúng kiểu và tránh blocking event-loop để có luồng nhận form vừa đúng vừa dễ kiểm thử.

## Tài liệu tham khảo

- [Spring Framework 6.2 — WebFlux @ModelAttribute method argument](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework 6.2 — WebFlux model và reactive model attributes](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-modelattrib-methods.html)
- [Spring Framework — WebFlux validation và exceptions](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-validation.html)
- [Spring Framework — WebFlux @RequestParam chỉ áp dụng query](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestparam.html)
- [Spring Framework 6.2 — WebFlux @RequestBody và HTTP message readers](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/requestbody.html)
- [Spring Framework API — WebExchangeBindException](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/bind/support/WebExchangeBindException.html)
- [Spring Framework — WebFlux data binding](https://docs.spring.io/spring-framework/reference/web/webflux/data-binding.html)
- [Spring Framework — WebTestClient testing](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
