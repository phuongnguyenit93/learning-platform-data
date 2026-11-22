# Kiểm tra trong luồng phản ứng và ranh giới với method validation AOP

## Mục tiêu học tập

Trong **Spring WebFlux**, một HTTP request được xử lý qua các thành phần reactive, nhưng dữ liệu sai vẫn cần bị phát hiện và báo lại đúng chỗ. Câu hỏi khó không chỉ là “dùng `@Valid` thế nào?” mà còn là **kiểm tra ở ranh giới nào và tại thời điểm nào**:

- Khi WebFlux giải mã/bind request thành một command object.
- Khi Spring AOP chặn một lời gọi phương thức của service có `@Validated`.
- Khi dữ liệu thực sự xuất hiện qua `Mono`/`Flux`, có thể sau lời gọi phương thức khá lâu.
- Khi một service tạo kết quả không thỏa ràng buộc hậu điều kiện, hoặc trả một `Publisher` chưa phát giá trị.
- Khi một lỗi trở thành exception tức thời, hay `onError` trong pipeline Reactor, và HTTP response có còn đổi status được không.

Bài này giải thích ranh giới và cho ví dụ Java 17+ với Spring Boot 3, WebFlux, Jakarta Bean Validation, AOP method validation và `StepVerifier`. Bạn sẽ phân biệt `WebExchangeBindException`, `HandlerMethodValidationException`, `ConstraintViolationException` và `MethodValidationException`; hiểu vì sao `@Valid` không tự biến cả pipeline thành được validate; biết đặt validation ở nơi kiểm tra được bằng test.

## 1. Ba lớp validation không thay thế cho nhau

Xét API đặt hàng:

~~~text
HTTP POST /orders/quote
    |
    v
WebFlux @RequestBody Mono<OrderLine>
    |
    +-- giải mã JSON + @Valid trên payload
    |      sai: WebExchangeBindException
    |
    v
OrderController
    |
    v
OrderService bean có @Validated, được gọi qua AOP proxy
    |
    +-- @NotBlank sku, @Min quantity trên method arguments
    |      sai: ConstraintViolationException (mặc định)
    |
    v
Mono<String> kết quả từ service
    |
    v
Reactor subscription
    |
    +-- map/flatMap/filter/concatMap, I/O reactive
    +-- validator.validate(item) trên từng item nếu được khai báo
    |      sai: tín hiệu onError (ví dụ ConstraintViolationException)
    |
    v
HTTP response
~~~

**Ba cơ chế khác nhau:**

1. **WebFlux argument validation:** do hạ tầng controller thực hiện lúc đọc `@RequestBody`, `@ModelAttribute` hoặc `@RequestPart` và/hoặc validate chữ ký handler. Nó gắn với HTTP boundary.
2. **Spring method validation qua AOP:** do `MethodValidationPostProcessor` và `MethodValidationInterceptor` áp dụng lên bean, thường chọn bằng `@Validated` ở class. Nó gắn với lời gọi phương thức **qua Spring proxy**, không phụ thuộc phương thức được gọi từ HTTP, message listener hay job.
3. **Validation trong Reactor chain:** do logic trên `onNext`/`flatMap`/`handle`… thực hiện khi dữ liệu thực sự phát ra. Nó có thể dùng Jakarta `Validator` hoặc business rule bất đồng bộ. Mục tiêu của nó là từng phần tử/kết quả trong stream.

Bật một cơ chế **không** có nghĩa hai cơ chế còn lại tự chạy. Chẳng hạn service được đánh dấu `@Validated` không tự chứng minh mọi phần tử do `Flux` trả về được kiểm tra; ngược lại, `validator.validate(item)` trong `flatMap` không kiểm tra những scalar arguments của một service method khác.

## 2. Vì sao thời điểm kiểm tra rất quan trọng?

Reactor có tính **lazy**: phần lớn pipeline chỉ thực thi khi có subscription.

~~~java
Mono<String> publisher = Mono.fromSupplier(
        () -> {
            System.out.println("source executes");
            return "ready";
        });

// Chưa in gì khi chỉ tạo publisher.
publisher.subscribe(System.out::println);
~~~

Đây là snippet Java dùng Reactor, không phải chương trình Java độc lập. Dòng `"source executes"` được in khi có subscription. Trong ứng dụng WebFlux, framework thường là bên subscribe; bạn **không nên tự gọi `subscribe()` trong controller** chỉ để buộc validation chạy.

Giờ xét AOP:

~~~java
@Validated
@Service
public class QuoteService {
    public Mono<String> quote(
            @NotBlank String sku, @Min(1) int quantity) {
        return Mono.just("quoted:" + sku + ":" + quantity);
    }
}
~~~

Nếu caller gọi `quoteService.quote("", 2)` **qua Spring-managed proxy**, ràng buộc `@NotBlank` trên đối số chuỗi đã sẵn sàng có thể bị kiểm tra **ngay trong lời gọi method**, trước khi caller có cơ hội subscribe vào `Mono` trả về. `Mono` lazy không làm cho mọi việc liên quan đến method call trở nên lazy.

Ngược lại, với nguồn:

~~~java
Flux<OrderLine> incoming = someReactiveSource();

Flux<String> output = incoming.concatMap(item ->
        validateThenProcess(item));
~~~

`item` chưa tồn tại tại thời điểm dựng pipeline; kiểm tra từng `item` phải diễn ra khi stream emit giá trị. `validateThenProcess` ở đây là method giả định, chỉ để minh họa vị trí thao tác.

**Hệ quả khi xử lý exception:**

- AOP có thể ném một exception đồng bộ từ method call (nếu vi phạm ràng buộc trên giá trị đối số đã có).
- Một lambda chạy trong `flatMap`/`concatMap` có thể ném exception **lúc subscription**, và Reactor biến nó thành `onError`.
- `onErrorResume(...)` **chỉ** xử lý lỗi đã nằm trong pipeline của publisher đó. Nó không tự bắt mọi exception xảy ra **trước khi publisher được tạo**. Nếu cần hoãn việc gọi một method có thể ném vào subscription, có thể dùng `Mono.defer(...)` một cách có chủ đích.

## 3. WebFlux controller: validation theo request

Spring Framework 6.1+ có cơ chế validation tích hợp vào annotated controllers. Với WebFlux, có hai đường quan trọng.

### 3.1. Validation riêng của một request argument

Ví dụ:

~~~java
@PostMapping("/orders")
Mono<String> create(
        @Valid @RequestBody Mono<OrderLine> body) {
    return body.map(order -> "ok:" + order.sku());
}
~~~

Đây là snippet controller, giả định `OrderLine` có constraint và đã import các annotation. `@Valid` trên `@RequestBody` yêu cầu kiểm tra bean giải mã từ JSON. Với kiểu `Mono<OrderLine>`, lỗi validation có thể được đưa vào reactive stream và dẫn tới **`WebExchangeBindException`**, thông thường phản hồi HTTP 400 nếu không tùy chỉnh handler.

`@Valid` là marker dùng cho Bean Validation và cascade, **không phải một direct constraint** như `@Min`. Nếu chỉ có `@Valid` trên command object và không có constraint ở cấp method, WebFlux thường dùng argument-level validation.

Với `@ModelAttribute` nhận form, một cách khác:

~~~java
@PostMapping("/forms")
Mono<String> accept(
        @Valid @ModelAttribute("form") OrderForm form,
        BindingResult errors) {
    if (errors.hasErrors()) {
        return Mono.just("form-error");
    }
    return Mono.just("form-ok");
}
~~~

Ở đây `BindingResult` đặt **ngay sau object thường** (không phải `Mono<OrderForm>`). Nếu argument là `Mono<OrderForm>`, pattern nhận `BindingResult` liền kề không được hỗ trợ; xử lý lỗi bằng reactive operators/exception handlers như `onErrorResume(WebExchangeBindException.class, ...)`.

### 3.2. Native method validation của controller

Nếu method có direct constraint:

~~~java
@GetMapping("/limits")
Mono<String> limit(@RequestParam @Min(1) int count) {
    return Mono.just("limit:" + count);
}
~~~

`@Min(1)` trên tham số làm WebFlux thực hiện **method validation** cho handler method. Khi vi phạm, trường hợp không có `Errors` tương ứng thường nhận **`HandlerMethodValidationException`**. Điểm này khác với `WebExchangeBindException` của argument-level validation một object.

Khi method validation được yêu cầu, nó có thể bao gồm cả nested constraints của những argument `@Valid` và thay thế kiểm tra riêng của argument resolver, để tránh double validation.

**Quan trọng:** không nên dùng `@Validated` ở **cấp class controller** chỉ để bật validation mặc định cho annotated WebFlux methods. Class-level `@Validated` có thể làm controller tham gia **Spring AOP method validation**, ảnh hưởng đến cơ chế exception; để dùng native controller method validation từ Spring 6.1, tài liệu Spring khuyến nghị bỏ class-level `@Validated` khi thích hợp.

### 3.3. Khi nào gặp từng exception?

| Ngữ cảnh | Dạng lỗi thường gặp | Gợi ý xử lý |
| --- | --- | --- |
| `@Valid @RequestBody Mono<Dto>`, DTO sai | `WebExchangeBindException` | 400 và trường lỗi |
| `@Valid @ModelAttribute Dto, BindingResult` | Handler đọc `BindingResult` | Render lại form |
| Controller có direct constraint `@Min`/`@NotBlank` | `HandlerMethodValidationException` | 400 nếu parameter lỗi |
| Controller return value vi phạm direct constraint | `HandlerMethodValidationException` | Xem là lỗi server/hậu điều kiện |
| Spring service `@Validated` qua proxy, mode mặc định | `ConstraintViolationException` | Tách lỗi service với lỗi HTTP |
| Spring service AOP với `adaptConstraintViolations=true` | `MethodValidationException` | Đọc `MethodValidationResult` |
| `validator.validate(bean)` gọi trực tiếp | Trả `Set<ConstraintViolation<T>>` | Code tự xử lý |
| `Mono/Flux` bị lỗi khi chạy operator | Tín hiệu Reactor `onError` | `onErrorResume`/error handler phù hợp |

Không nên catch mọi `RuntimeException` rồi trả HTTP 400. `HandlerMethodValidationException` với **lỗi return value** là vấn đề phía server; `MethodValidationException` từ một service có thể chỉ lỗi lập trình nội bộ chứ không nhất thiết do người dùng gửi request sai.

## 4. Spring AOP method validation: ranh giới bean và proxy

### 4.1. Điều kiện để AOP thực sự chạy

Spring Framework dùng `MethodValidationPostProcessor` để phát hiện bean `@Validated` và tạo AOP advice. Với Spring Boot 3 có Jakarta Validation provider và cấu hình method validation tiêu chuẩn, hạ tầng này thường được tự động cấu hình.

Mẫu service:

~~~java
@Service
@Validated
public class ReservationService {

    public Mono<String> reserve(
            @NotBlank String code,
            @Min(1) int count) {
        return Mono.just("reserved:" + code + ":" + count);
    }
}
~~~

Lỗi ràng buộc **trên đối số method** được kiểm tra khi gọi qua Spring proxy.

Điều kiện thực tế:

1. Service là bean do Spring quản lý.
2. Một Jakarta Bean Validation provider có mặt.
3. Method được gọi qua **proxy**, không phải qua `new ReservationService()` hoặc self-invocation `this.reserve(...)`.
4. Phương thức có annotation constraint phù hợp ở đúng vị trí; nhóm validation nếu có phải khớp.
5. Phương thức có thể được intercept bởi kiểu proxy đang dùng (visibility, final, interface/proxy class).

**Self-invocation:** nếu `ReservationService.otherMethod()` gọi `this.reserve("", 0)` trong cùng target object, lời gọi đó thường vượt qua Spring proxy; AOP method validation không được kích hoạt cho `reserve`. Đây là một trong những lỗi phổ biến nhất khi thấy test “ngoài bean” báo lỗi nhưng production call bên trong cùng class không báo.

### 4.2. Nguyên tắc validation trước và sau lời gọi

Jakarta `ExecutableValidator` hỗ trợ:

~~~java
var executor = validator.forExecutables();

var inputViolations = executor.validateParameters(
        service, method, arguments);

var outputViolations = executor.validateReturnValue(
        service, method, returnedValue);
~~~

Đây là snippet chỉ có ý nghĩa khi biến `validator`, `service`, `method` và `arguments` đã được tạo. AOP interceptor dùng cơ chế tương tự để kiểm tra preconditions và postconditions.

Với method trả về `Mono<T>`, ràng buộc đặt **trên chính kiểu giá trị trả về của method** có thể áp dụng lên đối tượng publisher mà method trả ra. Ví dụ:

~~~java
@NotNull
public Mono<Invoice> findInvoice(String id) {
    return Mono.empty();
}
~~~

Ở đây method trả một **đối tượng Mono khác null**, dù publisher đó có thể hoàn tất mà không phát `Invoice` nào. `@NotNull` trên return value **không đồng nghĩa** “Mono phải emit một Invoice”. Nếu yêu cầu nghiệp vụ là “không được empty”, dùng `switchIfEmpty(Mono.error(...))` hoặc quy tắc tương ứng trong stream. Nếu yêu cầu từng emitted `Invoice` thỏa constraints, cần cấu hình đúng cơ chế kiểm tra **phần tử** hoặc chủ động validate chúng.

### 4.3. Hỗ trợ tham số Mono/Flux của interceptor không phải phép màu

Spring 6.1+ mở rộng `MethodValidationInterceptor` để hỗ trợ reactive **method parameters** như `Mono` và `Flux` trong những trường hợp có validation metadata trên chính reactive parameter. Interceptor có thể bọc publisher bằng operator kiểm tra giá trị khi được emit. Điều này có nghĩa không thể kết luận rằng AOP luôn bỏ qua nội dung mọi `Mono`/`Flux`.

Nhưng cần phân biệt rõ:

- **Reactive method parameter được đánh dấu thích hợp** khác với **reactive return value**.
- Metadata/annotation và Spring Framework version quyết định cơ chế nào áp dụng.
- Một service trả `Flux<Invoice>` **không** mặc nhiên bảo đảm mọi `Invoice` đều được kiểm tra, nhất là nếu không có metadata hoặc chủ động validation trong pipeline.
- Validation qua AOP không thay thế mọi kiểm tra domain hoặc điều kiện cần I/O.

Ví dụ mẫu kiến trúc cần test riêng theo version:

~~~java
@Validated
@Service
class IntakeService {
    public Mono<Void> intake(@Valid Flux<Invoice> invoices) {
        return invoices.then();
    }
}
~~~

Đây là **snippet minh họa**, chưa phải chương trình chạy độc lập: `Invoice` phải khai báo constraints và imports thích hợp. Khi sử dụng thật, phải kiểm tra bằng `StepVerifier` và xác nhận AOP proxy đã gắn, bởi validation có thể xảy ra trong operator sau subscription. Đừng dựa vào một test chỉ gọi method mà không subscribe rồi khẳng định mọi item đã được validate.

## 5. Lỗi AOP: ConstraintViolationException hoặc MethodValidationException

Mặc định, `MethodValidationPostProcessor` để `adaptConstraintViolations=false`; một vi phạm method validation sẽ dẫn đến **`jakarta.validation.ConstraintViolationException`** chứa `Set<ConstraintViolation<?>>`:

~~~java
try {
    service.reserve("", 1);
} catch (ConstraintViolationException ex) {
    ex.getConstraintViolations().forEach(v ->
            System.out.println(
                    v.getPropertyPath() + " -> "
                    + v.getMessage()));
}
~~~

Đây là snippet minh họa, không là file chạy độc lập. `Set` không bảo đảm thứ tự; sắp xếp nếu cần output ổn định.

Nếu cấu hình:

~~~java
@Bean
static MethodValidationPostProcessor methodValidation() {
    MethodValidationPostProcessor p =
            new MethodValidationPostProcessor();
    p.setAdaptConstraintViolations(true);
    return p;
}
~~~

Spring 6.1+ có thể dùng **`org.springframework.validation.method.MethodValidationException`** thay thế, với các `ParameterValidationResult` và `MessageSourceResolvable` phù hợp hệ sinh thái Spring.

Đoạn cấu hình này chỉ minh họa trong một `@Configuration`; **không tự thêm bean thứ hai** vào ứng dụng Boot đang có method-validation auto-configuration nếu chưa kiểm tra hạ tầng hiện hữu.

Bảng phân biệt:

| Exception | Nguồn | Cấu trúc dữ liệu |
| --- | --- | --- |
| `ConstraintViolationException` | Jakarta / Spring AOP mặc định | `Set<ConstraintViolation<?>>` và `Path` |
| `MethodValidationException` | Spring AOP bật adaptation | `MethodValidationResult` và các lỗi được nhóm theo parameter |
| `WebExchangeBindException` | WebFlux bind/validate một controller argument | `BindingResult` / `FieldError` |
| `HandlerMethodValidationException` | Native WebFlux controller method validation | `MethodValidationResult` của handler method |

Sự khác nhau không chỉ ở package: các exception này được tạo tại **ranh giới khác nhau**. Tạo một global handler trả 400 cho cả bốn mà không kiểm tra nguồn và loại vi phạm có thể che bug hậu điều kiện hoặc lỗi gọi service nội bộ.

## 6. Validation thủ công trong Reactor stream

Khi xử lý một `Flux<OrderLine>` lấy từ database, broker, WebClient hay biến đổi nhiều bước, dữ liệu chỉ có khi subscriber yêu cầu. Nếu mỗi phần tử cần đảm bảo constraints, có thể gọi Jakarta `Validator.validate(item)` trong một operator.

Ví dụ:

~~~java
Flux<OrderLine> checked = source.concatMap(item -> {
    Set<ConstraintViolation<OrderLine>> problems =
            validator.validate(item);

    if (!problems.isEmpty()) {
        return Mono.error(
                new ConstraintViolationException(problems));
    }

    return Mono.just(item);
});
~~~

Đây là snippet kiến trúc; `source` và `validator` giả định có sẵn.

- `validator.validate(item)` trả `Set`, **không tự ném `ConstraintViolationException`**. Code chủ động biến errors thành exception.
- Khi đã subscribe, nếu `item` sai, `Mono.error(...)` biến lỗi thành tín hiệu `onError` của pipeline.
- `concatMap` xử lý kết quả từng item theo thứ tự đầu vào trong ví dụ; có thể dùng `flatMap` cho concurrency nếu đó là lựa chọn nghiệp vụ phù hợp.
- `onError` chấm dứt stream ở luồng xử lý thông thường. Để thu thập nhiều lỗi và trả report sau cùng, cần mô hình dữ liệu kết quả hợp lệ/lỗi riêng, không mặc định `onErrorContinue` là chiến lược validation.
- Validator có thể dùng đồng thời từ nhiều subscriber nếu implementation tuân thủ contract; custom `ConstraintValidator` phải thread-safe về state.
- Đừng thực hiện JDBC hoặc HTTP blocking bên trong `isValid()` khi chạy trên WebFlux event loop. Bean Validation phù hợp nhất với các quy tắc in-memory/ngắn; ràng buộc cần I/O phải thiết kế ở reactive service.

### 6.1. Có thể dùng handle thay cho concatMap

~~~java
Flux<OrderLine> checked = source.handle((item, sink) -> {
    var errors = validator.validate(item);
    if (errors.isEmpty()) {
        sink.next(item);
    } else {
        sink.error(new ConstraintViolationException(errors));
    }
});
~~~

Snippet này chỉ minh họa cú pháp. `handle` phù hợp khi kết quả là “emit item hợp lệ hoặc error”, còn `concatMap`/`flatMap` tiện khi bước kế tiếp trả `Mono` từ service hoặc repository.

### 6.2. Khác nhau giữa error signal và data error

Có ít nhất hai chiến lược:

**Fail-fast:** gặp item sai thì stream `onError`. Phù hợp khi đầu vào phải là một lô nguyên vẹn, hoặc yêu cầu abort để tránh tiếp tục tác dụng phụ sau lỗi.

**Per-item results:** biến từng item thành `ValidationOutcome` chứa valid/errors, rồi xử lý các item hợp lệ hay báo cáo lỗi từng dòng. Phù hợp import hàng loạt hoặc xử lý message độc lập. Không dùng `onError` để mô hình hóa “mỗi record có thể sai” nếu nghiệp vụ yêu cầu tiếp tục với record còn lại.

Ví dụ phác họa:

~~~java
record Outcome(
        OrderLine input,
        boolean valid,
        java.util.List<String> messages) {}

Flux<Outcome> reports = source.map(item -> {
    var errors = validator.validate(item);
    var messages = errors.stream()
            .map(ConstraintViolation::getMessage)
            .sorted()
            .toList();
    return new Outcome(item, messages.isEmpty(), messages);
});
~~~

Đây là snippet với `source`, `validator` và imports giả định có sẵn, không phải ứng dụng độc lập. `map` biến mỗi item thành một báo cáo thay vì ném lỗi. Trong production, quyết định hành vi retry/acknowledgment/transaction phải nằm ở nghiệp vụ, không chỉ ở annotation.

## 7. Ví dụ Java 17+ chạy được: WebFlux, AOP và Reactor validation

Ví dụ sau kết hợp **ba ranh giới tách biệt**:

1. WebFlux `@Valid @RequestBody Mono<OrderLine>` kiểm tra payload HTTP và báo lỗi 400 nếu DTO sai.
2. Service `@Validated` kiểm tra scalar arguments `sku` và `quantity` qua Spring AOP khi method được gọi.
3. Một service method khác dùng `validator.validate(...)` **trong `Flux.concatMap(...)`** để bảo đảm từng item trong stream.

Với ví dụ này, không cần dựa vào các giả định phức tạp về việc AOP có kiểm tra payload của một reactive return type hay không: item-level validation được viết tường minh để dễ đọc và kiểm thử.

### 7.1. Cấu trúc dự án

~~~text
webflux-validation-boundaries/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/boundaries/
    │       ├── Application.java
    │       ├── OrderLine.java
    │       ├── OrderService.java
    │       └── OrderController.java
    └── test/
        └── java/com/example/boundaries/
            └── ValidationBoundaryTest.java
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
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>webflux-validation-boundaries</artifactId>
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

**Vì sao không có `spring-boot-starter-web`?** Nếu cùng đưa starter MVC và WebFlux vào classpath, Spring Boot thông thường ưu tiên Servlet web application type. Demo chỉ dùng WebFlux để minh bạch ranh giới kiểm tra của reactive controller.

Spring Boot 3.5.7 là một phiên bản cố định của ví dụ, dùng Java 17+ và namespace `jakarta.validation`. Trong production, dùng dependency management/patch version phù hợp chính sách cập nhật của dự án.

### 7.3. Application.java

~~~java
package com.example.boundaries;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

### 7.4. OrderLine.java — constraints trên command object

~~~java
package com.example.boundaries;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record OrderLine(
        @NotBlank String sku,
        @Min(1) int quantity) {
}
~~~

Record Java 17 mang hai ràng buộc:

- `sku` không được rỗng hoặc chỉ chứa whitespace.
- `quantity` phải ít nhất 1.

Các annotation trên record components được Jakarta provider xử lý qua metadata tương ứng. DTO bất biến giảm nguy cơ object bị thay đổi sau validation, nhưng không thay các quy tắc authorization hoặc domain validation.

### 7.5. OrderService.java — AOP boundary và stream boundary

~~~java
package com.example.boundaries;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.ConstraintViolationException;
import jakarta.validation.Validator;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.util.Set;

@Service
@Validated
public class OrderService {

    private final Validator validator;

    public OrderService(Validator validator) {
        this.validator = validator;
    }

    // Boundary A: scalar arguments validated by Spring AOP.
    public Mono<String> quote(
            @NotBlank String sku,
            @Min(1) int quantity) {

        return Mono.just("quote:" + sku + ":" + quantity);
    }

    // Boundary B: explicitly validate each onNext item.
    public Flux<String> ingest(Flux<OrderLine> source) {
        return source.concatMap(line -> {
            Set<ConstraintViolation<OrderLine>> problems =
                    validator.validate(line);

            if (!problems.isEmpty()) {
                return Mono.<String>error(
                        new ConstraintViolationException(problems));
            }

            return Mono.just("stored:" + line.sku()
                    + ":" + line.quantity());
        });
    }
}
~~~

Ở `quote(...)`, đối số scalar có sẵn khi code gọi method qua Spring proxy. `@NotBlank`/`@Min` được Spring AOP method validation áp dụng; khi sai và dùng cấu hình mặc định, `ConstraintViolationException` được ném từ lời gọi đó.

Ở `ingest(...)`, `source` là publisher. Ta cố ý **không đặt `@Valid` trên `Flux` parameter**, vì muốn cho thấy cơ chế **tự kiểm tra mỗi item lúc emit**. `validator.validate(line)` nằm trong `concatMap`; nếu line sai, method trả `Mono.error(...)` và Reactor phát tín hiệu `onError` **lúc subscribe**.

Lưu ý `@Validated` ở class chỉ là pointcut cho Spring AOP method validation; việc gọi `ingest(...)` qua proxy không khiến `validator.validate(line)` xảy ra trước subscription. `concatMap` vẫn lazy như Reactor semantics.

Ví dụ này chỉ tạo chuỗi `"stored:..."`; không có database hoặc side effect thực sự. Khi dùng R2DBC để lưu, gọi repository reactive **sau** bước kiểm tra và xem lại tính nguyên tử của batch, thứ tự commit, retry và cancellation.

### 7.6. OrderController.java — hai kiểu validation native của WebFlux

~~~java
package com.example.boundaries;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    // WebFlux validates the JSON command object.
    @PostMapping(
            path = "/quote",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> quote(
            @Valid @RequestBody Mono<OrderLine> body) {

        return body.flatMap(line ->
                service.quote(line.sku(), line.quantity()));
    }

    // WebFlux native controller method validation.
    @GetMapping(
            path = "/limits",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> limits(
            @RequestParam @Min(1) int count) {

        return Mono.just("limit:" + count);
    }
}
~~~

**Điểm cần phân tích:**

- `quote(...)` có `@Valid @RequestBody Mono<OrderLine>` nên WebFlux kiểm tra đối tượng sau khi decode JSON. Input vi phạm `@NotBlank`/`@Min` đi theo đường `WebExchangeBindException` và mặc định phản hồi 400. Nếu hợp lệ, `flatMap` gọi **proxied service**, ở đó AOP method validation áp dụng cho scalar arguments.
- `limits(...)` có direct `@Min(1)` trên query parameter. Đây là native **controller method validation**, khi lỗi thường là `HandlerMethodValidationException`.
- Không gắn class-level `@Validated` trên controller; vì vậy không chuyển nhầm controller validation sang Spring AOP path.
- Controller không tự `subscribe()` hay `block()`. Return `Mono<String>` cho WebFlux phối hợp request lifecycle.
- Vì demo không định nghĩa global exception handler, mặc định lỗi hợp lệ kiểu input dẫn đến HTTP 400; body lỗi mặc định có thể thay đổi theo content negotiation, Spring configuration và problem-details handling. Bài kiểm thử khẳng định status, không phụ thuộc JSON lỗi mặc định.

### 7.7. ValidationBoundaryTest.java — tests cho từng ranh giới

~~~java
package com.example.boundaries;

import jakarta.validation.ConstraintViolationException;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
@AutoConfigureWebTestClient
class ValidationBoundaryTest {

    @Autowired
    private OrderService service;

    @Autowired
    private WebTestClient client;

    @Test
    void aopRejectsScalarArgumentsAtMethodInvocation() {
        assertThrows(
                ConstraintViolationException.class,
                () -> service.quote("", 2));
    }

    @Test
    void validServiceMethodReturnsMono() {
        StepVerifier.create(service.quote("SKU", 2))
                .expectNext("quote:SKU:2")
                .verifyComplete();
    }

    @Test
    void perItemValidationEmitsErrorOnSubscription() {
        Flux<OrderLine> input = Flux.just(
                new OrderLine("A", 1),
                new OrderLine("", 1));

        Flux<String> result = service.ingest(input);

        StepVerifier.create(result)
                .expectNext("stored:A:1")
                .expectError(ConstraintViolationException.class)
                .verify();
    }

    @Test
    void validJsonBodyPassesWebFluxAndService() {
        client.post()
                .uri("/orders/quote")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new OrderLine("SKU", 2))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("quote:SKU:2");
    }

    @Test
    void invalidJsonBodyFailsWebFluxValidation() {
        client.post()
                .uri("/orders/quote")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new OrderLine("", 2))
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void directControllerConstraintIsMethodValidation() {
        client.get()
                .uri("/orders/limits?count=0")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void validControllerConstraint() {
        client.get()
                .uri("/orders/limits?count=3")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("limit:3");
    }
}
~~~

Chạy với Maven/JDK 17+:

~~~bash
mvn test
~~~

**Bảy điều cần chứng minh:**

1. `aopRejectsScalarArgumentsAtMethodInvocation` bắt exception ngay ở lời gọi proxy, **không gọi StepVerifier** vì chưa nhận được publisher.
2. `validServiceMethodReturnsMono` kiểm tra kết quả reactive hợp lệ.
3. `perItemValidationEmitsErrorOnSubscription` có một item được phát trước khi item sai gây `onError`; `StepVerifier` xác minh thứ tự.
4. `validJsonBodyPassesWebFluxAndService` đi qua cả controller boundary và service.
5. `invalidJsonBodyFailsWebFluxValidation` phản hồi 400 trước khi xử lý thành công của service.
6. `directControllerConstraintIsMethodValidation` phản hồi 400 do `@Min` trên query parameter.
7. `validControllerConstraint` cho thấy một giá trị query hợp lệ.

Các test không giả định toàn bộ log hoặc JSON lỗi mặc định là cố định. Nếu muốn xác minh exception type của từng HTTP boundary, thêm `@ControllerAdvice` hoặc kiểm tra handler-level metadata phù hợp; **chỉ HTTP status 400 không chứng minh hai đường exception có cùng type**.

### 7.8. Thử chạy HTTP thủ công

Khởi động:

~~~bash
mvn spring-boot:run
~~~

Gửi quote hợp lệ:

~~~bash
curl -i -X POST http://localhost:8080/orders/quote \
  -H "Content-Type: application/json" \
  -d '{"sku":"SKU","quantity":2}'
~~~

Body thành công do controller/service demo định nghĩa:

~~~text
quote:SKU:2
~~~

Gửi input sai:

~~~bash
curl -i -X POST http://localhost:8080/orders/quote \
  -H "Content-Type: application/json" \
  -d '{"sku":"","quantity":2}'
~~~

HTTP status mong đợi: **400 Bad Request**. Nội dung body lỗi phụ thuộc cấu hình Spring Boot/WebFlux, nên không cung cấp một mẫu body “chính xác” có thể sai giữa các môi trường.

Thử native method validation:

~~~bash
curl -i "http://localhost:8080/orders/limits?count=0"
~~~

Mong đợi HTTP **400** do `@Min(1)` không đạt.

### 7.9. Thử nghiệm đối chiếu AOP

Nếu sửa test thành:

~~~java
OrderService target = new OrderService(validator);
target.quote("", 2);
~~~

thì đoạn này **không** đi qua Spring proxy và không được method-validation interceptor kiểm tra; method body có thể trả `Mono` bình thường. Đây là snippet để so sánh, cần biến `validator` đã tồn tại. Không dùng cách tạo bằng `new` trong code ứng dụng thật nếu muốn method validation AOP.

Ngược lại, trong `OrderController`, service được Spring inject là bean proxy nên `service.quote(...)` đi qua interceptor. Điều này giải thích vì sao lỗi “annotation không có tác dụng” đôi khi là lỗi kiến trúc lời gọi chứ không phải lỗi Bean Validation metadata.

## 8. Reactive publisher không phải emitted value

Có ba thực thể khác nhau:

~~~text
Method argument:       String sku = ""
Method return value:   Mono<Invoice> publisher
Published item:        Invoice emitted onNext later
~~~

- Với `@NotBlank String sku`, validator có thể kiểm tra ngay đối số đã có.
- Với `@NotNull` đặt trên method trả `Mono<Invoice>`, ràng buộc không-nhận-null của return value không tự xác nhận sẽ có một `Invoice` được phát.
- Với `Invoice` được phát từ publisher, muốn kiểm tra constraints của đối tượng này cần metadata/cơ chế hỗ trợ phần tử hoặc viết kiểm tra tại operator trong stream.
- Với `Mono.empty()`, không có `onNext` để validate; nếu nghiệp vụ yêu cầu phát ít nhất một item, phải xử lý empty bằng `switchIfEmpty(...)`.

Ví dụ:

~~~java
Mono<Invoice> result = repository.findById(id)
        .switchIfEmpty(
                Mono.error(new InvoiceMissingException(id)))
        .flatMap(invoice -> {
            var violations = validator.validate(invoice);
            if (!violations.isEmpty()) {
                return Mono.error(
                        new ConstraintViolationException(violations));
            }
            return Mono.just(invoice);
        });
~~~

Đây là snippet kiến trúc không độc lập, giả định có `repository`, `validator`, `Invoice` và `InvoiceMissingException`. Nó thể hiện riêng **không cho empty** và **kiểm tra nội dung emitted item**.

### 8.1. Return-value validation của controller và service khác nhau

Spring WebFlux native controller method validation (Spring 6.1+) có thể kiểm tra method **return value** khi có ràng buộc được hỗ trợ trên chữ ký. Spring AOP service có ranh giới trả về từ lời gọi proxied method. Cả hai không thay thế kiểm tra mỗi item phát ra bởi một publisher dài hoặc phát liên tục.

Nếu một `Flux` đang stream HTTP response và item thứ ba mới sai, server có thể đã gửi bytes của item thứ nhất và thứ hai. Khi response đã **committed**, không thể quay lại biến status 200 đã gửi thành 400/500 để báo lỗi đẹp theo cách thông thường. Đây là lý do một API đòi **toàn bộ response hợp lệ mới gửi** đôi khi phải validate/buffer tất cả trước khi ghi (đánh đổi memory/latency), hoặc chọn giao thức truyền sự kiện có quy ước báo lỗi riêng.

## 9. Khi nào validate trong pipeline, khi nào tại AOP?

| Quy tắc | Vị trí nên cân nhắc | Lý do |
| --- | --- | --- |
| Mã sản phẩm bắt buộc khi gọi service | `@NotBlank` trên scalar argument của `@Validated` service | Precondition sẵn có ngay ở method call |
| DTO JSON của HTTP request | `@Valid @RequestBody` trong WebFlux controller | Ranh giới input HTTP, thông báo lỗi 400 |
| Giá trị query page/count ≥ 1 | Direct `@Min` ở controller hoặc service boundary | Kiểm tra constraint trong chữ ký; native method validation/AOP tùy tầng |
| Từng item nhận từ `Flux`/message broker | Reactor `map/concatMap/handle` + `validator.validate(item)` hoặc cơ chế element validation được hỗ trợ và test | Thời điểm item được emit |
| Kết quả có thể `Mono.empty()` nhưng bắt buộc có | `switchIfEmpty(Mono.error(...))` | Không có item để kiểm tra bằng Bean Validation |
| Kiểm tra user có quyền sửa order trong database | Reactive service + repository/security | Có I/O và context, không nhét vào constraint validator blocking |
| Phụ thuộc vào kết quả hai API async | `zip`/`flatMap` rồi validate invariant | Chỉ biết dữ liệu sau khi I/O hoàn thành |
| Batch import cần ghi nhận nhiều dòng sai | Map mỗi item thành `ValidationOutcome` | Không muốn `onError` dừng toàn bộ batch |
| Lỗi ở object trả ra cho client | Validate item/response trước khi encode nếu cần | Tránh rò rỉ dữ liệu/hậu điều kiện sai |

**Nguyên tắc chọn vị trí:** validate càng gần ranh giới nhận dữ liệu càng tốt cho các constraint thuần dữ liệu; validate nghiệp vụ ở tầng sở hữu thông tin và quyền; validate từng emitted item đúng thời điểm item tồn tại. Tránh duplicate validation nặng hoặc cấu hình gây xử lý lỗi lặp.

## 10. Error handling trong reactive chain

### 10.1. onErrorResume bắt những lỗi nào?

~~~java
return service.ingest(source)
        .onErrorResume(
                ConstraintViolationException.class,
                ex -> Flux.empty());
~~~

Snippet này chuyển stream lỗi thành hoàn tất bình thường; dùng **chỉ nếu nghiệp vụ cho phép bỏ qua phần còn lại**, vì có thể che dữ liệu sai. Nó bắt lỗi khi `ingest` đã trả publisher và publisher đó phát `onError`, ví dụ lỗi do `validator.validate(...)` trong `concatMap`.

**Nhưng** nếu method `service.quote("", 2)` ném `ConstraintViolationException` trực tiếp **trong lúc gọi**, code sau sẽ không có publisher để gọi `onErrorResume`:

~~~java
Mono<String> p = service.quote("", 2); // Có thể ném ngay tại đây.
return p.onErrorResume(
        ConstraintViolationException.class,
        ex -> Mono.just("fallback"));
~~~

Muốn thay đổi thời điểm gọi vào subscription một cách rõ ràng:

~~~java
return Mono.defer(() -> service.quote("", 2))
        .onErrorResume(
                ConstraintViolationException.class,
                ex -> Mono.just("fallback"));
~~~

Đây là **snippet minh họa có chủ đích**: `Mono.defer` thực thi supplier khi subscribe, nên exception xảy ra trong supplier có thể trở thành `onError` của Mono. Tuy nhiên, đừng dùng `defer` chỉ để che một validation error thành thành công giả; policy cần phân biệt input sai, domain error và server bug.

### 10.2. Dùng doOnError cho quan sát, không xử lý thay

~~~java
return service.ingest(source)
        .doOnError(ex -> logger.warn(
                "ingest failed: {}", ex.getClass().getSimpleName()));
~~~

Đây là snippet giả định có `logger`. `doOnError` là **side effect** quan sát; nó không nuốt error. `onErrorMap` đổi kiểu lỗi, `onErrorResume` đổi sang publisher thay thế, `onErrorReturn` cung cấp một giá trị fallback; chọn phù hợp với semantics, không chỉ để test xanh.

### 10.3. Đừng log dữ liệu nhạy cảm

`ConstraintViolation.getInvalidValue()`, `FieldError.getRejectedValue()`, target object hoặc exception message đôi khi chứa input người dùng, token hay thông tin định danh. HTTP response nên có mã lỗi, field và thông điệp cần thiết, không serialise nguyên `Throwable`/`ConstraintViolation`. Với hệ thống đa ngôn ngữ, dùng `MessageSource`/`MessageSourceResolvable` để nội suy thông điệp thay vì phụ thuộc toàn chuỗi exception.

## 11. Validation groups và metadata ở các tầng

Jakarta Validation có nhóm mặc định `Default` và custom group:

~~~java
interface FinalizeOrder {
}

record OrderLine(
        @NotBlank String sku,
        @Min(1) int quantity,
        @NotBlank(groups = FinalizeOrder.class) String approvalCode) {
}
~~~

Đây là fixture minh họa khác với record hai field trong demo chạy được. Nếu gọi `validator.validate(orderLine)` không truyền groups, chỉ các constraint thuộc `Default` được kiểm tra. Muốn cả constraints mặc định và nhóm cuối:

~~~java
var errors = validator.validate(
        orderLine, Default.class, FinalizeOrder.class);
~~~

Cần import `jakarta.validation.groups.Default` và có instance `orderLine`. Tương tự, Spring `@Validated(FinalizeOrder.class)` chọn group custom nhưng không tự bổ sung Default. Nếu service method cần cả hai, cấu hình rõ `@Validated({Default.class, FinalizeOrder.class})` ở điểm thích hợp và test đúng nhóm.

Với object graph lồng nhau, `@Valid` trên cạnh tham chiếu cho phép cascade constraints của object con. Nếu không đặt `@Valid`, không tự động duyệt toàn bộ graph chỉ vì outer method có `@Validated`. `@ConvertGroup` có thể chuyển group trên một cạnh cascade cụ thể; không xem nó là cơ chế kích hoạt mọi constraint.

**Đừng nhầm `@Validated` trên service class với `@Validated` trên một request argument.** Cùng tên annotation nhưng vị trí quyết định vai trò: class-level gắn với AOP method validation, còn parameter-level trên `@RequestBody`/`@ModelAttribute` chọn nhóm bean validation của WebFlux argument.

## 12. Những lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Service `@Validated` nhưng input sai không bị chặn | Gọi `new Service()`, self-invocation, proxy không hoạt động | Gọi bean qua Spring proxy; kiểm tra post-processor |
| Viết `@Valid` ở controller nhưng vẫn không bắt lỗi scalar query | `@Valid` không phải constraint trực tiếp | Dùng constraint phù hợp như `@Min` |
| Nhầm `WebExchangeBindException` với `ConstraintViolationException` | Hai tầng khác nhau | Xác định lỗi từ HTTP argument resolver hay AOP service |
| Catch `ConstraintViolationException` không chạy | AOP adaptation bật hoặc lỗi ở controller native method validation | Kiểm tra exception thực và cấu hình `adaptConstraintViolations` |
| `Flux` chứa item sai nhưng không có exception ở lúc tạo publisher | Stream lazy, chưa subscribe | Test bằng `StepVerifier`/WebTestClient |
| `@NotNull` trên `Mono<T>` vẫn cho `Mono.empty()` | Publisher khác null, không có item | Dùng `switchIfEmpty` |
| `validator.validate(item)` không ném exception | API trả Set | Xử lý Set và phát `Mono.error`/`sink.error` |
| `onErrorResume` không bắt exception | Exception xảy ra trước khi publisher tồn tại | Xem call site, cân nhắc `Mono.defer` hợp lệ |
| Controller có class-level `@Validated` tạo exception khác | AOP intercept controller thay vì native WebFlux handler validation | Kiểm tra annotation vị trí/class-level |
| `@Valid` trên DTO không kiểm tra field lồng | Thiếu cascade `@Valid` trên object property | Đặt marker đúng cạnh |
| Test dùng `MockMvc` dù chạy WebFlux | Trộn web stack/adapter | Dùng `WebTestClient` |
| HTTP status vẫn 200 sau khi stream lỗi | Response đã committed | Validate/buffer trước gửi nếu contract yêu cầu |
| Pipeline chậm/nghẽn | Validator gọi JDBC/HTTP blocking trên event loop | Đưa I/O sang reactive service/driver |
| Dùng `onErrorContinue` để bỏ item sai | Semantics khó đoán với operator và side effects | Mô hình hóa per-item outcomes tường minh |
| Mọi lỗi service biến thành 400 | Nhầm precondition, postcondition, lỗi nội bộ | Thiết kế mapping theo boundary và ownership |
| Các nhóm validation không chạy như tưởng tượng | `@Validated(Group)` không bao gồm Default | Chọn groups rõ ràng |
| Một phần data đã ghi trước item lỗi | Stream processing không tự transactional toàn batch | Thiết kế transaction/compensation/ack lại |

### Checklist debug nhanh

1. Xác nhận Spring Boot dùng reactive app type; kiểm tra dependency để tránh Servlet/MVC được chọn do có cả hai web starters.
2. Xác nhận input thực tế là JSON, URL-encoded form hay query; dùng `@RequestBody`, `@ModelAttribute`, `@RequestParam` đúng nguồn.
3. Kiểm tra Bean Validation provider có mặt và annotation dùng `jakarta.validation.*`.
4. Với controller, xem `@Valid`/direct constraint, `BindingResult` và exception type thực tế.
5. Với service, xem bean có `@Validated` ở nơi phù hợp, caller có đi qua proxy hay không, method/parameter có constraint và group khớp không.
6. Với reactive pipeline, kiểm tra subscription đã xảy ra chưa; dùng `StepVerifier` để xác định signal và thứ tự emit.
7. Phân biệt lỗi **ngay khi method invocation** với lỗi **onError sau subscribe**; đặt error mapping tại ranh giới phù hợp.
8. Kiểm tra stream response có thể đã committed khi item lỗi không.
9. Giữ validator ngắn, không có blocking I/O; kiểm tra quyền và domain validation ở service có thông tin nghiệp vụ.
10. Kiểm thử ít nhất một case hợp lệ, một case invalid HTTP DTO, một case AOP scalar và một case invalid emitted item.

## 13. Bài tập vận dụng

**Bài 1 — Ranh giới:** Giải thích vì sao `@Valid @RequestBody Mono<OrderLine>` và `@Validated` trên `OrderService` không phải cùng một cơ chế. Nếu DTO sai ngay từ HTTP request, lớp nào báo trước khi service làm việc?

**Bài 2 — AOP proxy:** Trong test, thay bean inject bằng `new OrderService(validator)` và gọi `quote("", 2)`. Vì sao annotation trên method không tự ném exception nữa?

**Bài 3 — Lazy execution:** Với `Flux.just(valid, invalid)` truyền vào `ingest(...)`, vì sao chỉ dựng `Flux<String>` chưa chứng minh validation đã chạy? Viết `StepVerifier` xác minh một item hợp lệ rồi lỗi.

**Bài 4 — Empty và null:** Method `@NotNull Mono<Invoice> find(...)` trả `Mono.empty()`. Vì sao điều này không nhất thiết vi phạm `@NotNull` của return object? Thêm logic để phát lỗi khi empty.

**Bài 5 — Exception taxonomy:** Nhận bốn lỗi `WebExchangeBindException`, `HandlerMethodValidationException`, `ConstraintViolationException`, `MethodValidationException`. Gán từng lỗi vào controller argument, native controller method, AOP raw và AOP adapted.

**Bài 6 — Tín hiệu Reactor:** `onErrorResume(ConstraintViolationException.class, ...)` không bắt một lời gọi `service.quote("", 1)` đã ném trước khi bạn gắn operator. Hãy giải thích cơ chế và nêu khi nào `Mono.defer` là phù hợp.

**Bài 7 — Per-item outcomes:** Thay `ingest` fail-fast bằng một stream trả `Outcome(valid, messages)` để tiếp tục kiểm tra những dòng còn lại. Đảm bảo không nhầm “dòng bị từ chối” với “lỗi máy chủ”.

**Bài 8 — Response streaming:** Server phát hai events thành công rồi item thứ ba lỗi. Điều gì xảy ra nếu headers đã gửi? Thiết kế lại API nếu client bắt buộc nhận mã status 422 cho toàn batch.

**Bài 9 — Groups:** Thêm group `FinalSubmit` và constraint chỉ thuộc group đó. Trong pipeline thủ công, gọi `validator.validate(item, Default.class, FinalSubmit.class)`; giải thích sự khác nhau với `validator.validate(item)`.

**Bài 10 — Performance/security:** Một custom validator gọi JDBC đồng bộ trên event loop. Hãy di chuyển nó sang reactive service phù hợp và giải thích vì sao đây là thay đổi về kiến trúc, không chỉ đổi tên annotation.

## Kết luận: mô hình tư duy đúng

Ghi nhớ ba câu hỏi trước khi chọn annotation/operator:

~~~text
1. Dữ liệu tồn tại ở đâu?
   Request object / scalar method argument / onNext item

2. Khi nào dữ liệu tồn tại?
   Trước invocation / trong controller resolution / khi subscribe

3. Ai sở hữu chính sách lỗi?
   WebFlux HTTP boundary / Spring AOP service boundary /
   Reactor domain pipeline
~~~

`@Valid` trên controller giúp kiểm tra input bean; `@Validated` trên Spring service có thể kích hoạt AOP method validation qua proxy; `validator.validate(item)` trong `concatMap` cho phép kiểm tra dữ liệu khi nó xuất hiện trong stream. Reactor không làm cho mọi validation tự động lazy, cũng không làm cho mọi `Mono`/`Flux` tự động có các emitted items hợp lệ. Phân biệt rõ loại exception, thời điểm phát lỗi và HTTP response đã committed hay chưa sẽ giúp xây dựng WebFlux API chính xác và dễ kiểm thử.

## Tài liệu tham khảo

- [Spring Framework 6.2 — Validation in WebFlux annotated controllers](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-validation.html)
- [Spring Framework 6.2 — Java Bean Validation and Spring-driven method validation](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html)
- [Spring Framework 6.2 — MethodValidationInterceptor API](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/validation/beanvalidation/MethodValidationInterceptor.html)
- [Spring Framework 6.2 — MethodValidationPostProcessor API](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/validation/beanvalidation/MethodValidationPostProcessor.html)
- [Spring Framework 6.2 — WebFlux @RequestBody validation](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/requestbody.html)
- [Spring Framework 6.2 — WebFlux error responses](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/ann-rest-exceptions.html)
- [Spring Framework 6.2 — WebFlux return types and streaming responses](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/return-types.html)
- [Spring Framework 6.2 — Validation in functional WebFlux endpoints](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html)
- [Jakarta Validation 3.0 — Bean Validation and executable validation](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)
- [Project Reactor — Testing a scenario with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html)
