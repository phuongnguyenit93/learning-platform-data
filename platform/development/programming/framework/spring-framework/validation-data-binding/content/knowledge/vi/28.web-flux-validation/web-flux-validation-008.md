# Cấu hình converter, formatter và validator bằng WebFluxConfigurer

## 1. Mục tiêu và bối cảnh

Spring WebFlux là web stack reactive của Spring Framework. Khi một HTTP request tới annotated controller, framework phải **đọc dữ liệu**, **chuyển dữ liệu sang kiểu Java** và **kiểm tra ràng buộc** trước khi gọi phần nghiệp vụ. Ba công việc này không thuộc cùng một API:

- **Converter** chuyển giá trị từ kiểu nguồn sang kiểu đích, chẳng hạn `String -> OrderCode` hoặc `String -> CustomerId`.
- **Formatter** parse một chuỗi thành object và print object thành chuỗi, thường cần quan tâm `Locale` hoặc quy ước hiển thị như ngày tháng, số tiền, phần trăm.
- **Validator** kiểm tra một object/giá trị đã được bind và ghi nhận lỗi, ví dụ `@NotNull`, `@Min` hoặc quy tắc nghiệp vụ riêng.

Trong Spring WebFlux, giao diện `org.springframework.web.reactive.config.WebFluxConfigurer` cung cấp các hook để cấu hình ba nhóm này:

```java
@Configuration
public class WebConfig implements WebFluxConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        // Đăng ký Converter và Formatter dùng trong argument binding.
    }

    @Override
    public Validator getValidator() {
        // Chọn Validator toàn cục cho WebFlux.
        return null; // Chỉ là khung API, không phải cấu hình hoàn chỉnh.
    }
}
```

Đoạn trên là **khung minh họa**, không phải chương trình chạy độc lập. Cần import `org.springframework.context.annotation.Configuration`, `org.springframework.format.FormatterRegistry`, `org.springframework.validation.Validator` và `org.springframework.web.reactive.config.WebFluxConfigurer`. Một dự án chạy đầy đủ với Java 17/Spring Boot có ở mục 7.

Điều cốt lõi: **`WebFluxConfigurer#addFormatters` cấu hình conversion/formatting cho dữ liệu tham số hoặc binding; `getValidator` chọn bộ kiểm tra toàn cục. Chúng không phải nơi duy nhất điều khiển JSON request/response body.** Đọc/ghi body qua HTTP message codecs là một cơ chế riêng.

## 2. Chuỗi xử lý của WebFlux

Đối với annotated controller nhận form hoặc request parameter, luồng có thể hình dung như sau:

```text
HTTP request
   |
   v
WebFlux HandlerMapping + HandlerAdapter
   |
   v
Argument resolution / WebExchangeDataBinder
   |-- lấy query/form/path/header
   |-- ConversionService: Converter/Formatter
   |-- binding errors: typeMismatch, ...
   |
   v
Validator được kích hoạt bởi @Valid / @Validated
   |-- Bean Validation constraints
   |-- Spring Validator nếu được cấu hình
   |
   +-- lỗi -> BindingResult (nếu nằm ngay sau @ModelAttribute)
   |          hoặc WebExchangeBindException ở đường thích hợp
   v
Controller method -> kết quả trả về -> HTTP response
```

Đối với `@RequestBody` JSON, quá trình **đọc body** đi qua `HttpMessageReader` (Jackson JSON decoder nếu có cấu hình thích hợp), sau đó mới validation đối tượng đã decode. Việc `String -> OrderCode` đã đăng ký bằng `addFormatters` **không tự động** khiến Jackson deserialize một trường JSON chứa String thành `OrderCode` theo converter đó.

Sơ đồ là cách học luồng thông thường; WebFlux có thể nhận `Mono<T>`/`Flux<T>`, với việc resolve và validate diễn ra trong reactive pipeline tương ứng. Không suy luận rằng mọi handler đều bị chặn và xử lý chính xác như một servlet thread.

## 3. Cấu hình WebFluxConfigurer đúng cách

### 3.1. Cấu hình tối thiểu

Với Spring Boot và dependency `spring-boot-starter-webflux`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration
public class WebConfig implements WebFluxConfigurer {
    // Chỉ override các hook cần thay đổi.
}
```

Spring Boot tiếp tục cung cấp phần lớn auto-configuration. **Không cần thêm `@EnableWebFlux`** trong trường hợp thông thường.

Nếu chủ động dùng Spring Framework WebFlux thuần, `@EnableWebFlux` có thể bật cấu hình mặc định. Nhưng trong ứng dụng Spring Boot, thêm `@EnableWebFlux` là một lựa chọn mang tính **takeover**: bạn có thể mất một số tùy chỉnh WebFlux tự động của Boot. Tài liệu Spring khuyến nghị triển khai `WebFluxConfigurer` mà không thêm `@EnableWebFlux` nếu muốn giữ auto-configuration.

**Nhầm lẫn tên interface:** `WebMvcConfigurer` dành cho Spring MVC Servlet stack; `WebFluxConfigurer` dành cho Spring WebFlux. Chúng không phải hai cách viết tùy ý cho cùng một hạ tầng.

### 3.2. Những hook liên quan

| Hook | Công dụng |
| --- | --- |
| `addFormatters(FormatterRegistry)` | Thêm converter, formatter, formatter registrar cho annotated-controller argument binding |
| `getValidator()` | Cung cấp Spring `Validator` toàn cục |
| `configureHttpMessageCodecs(ServerCodecConfigurer)` | Tùy chỉnh HTTP readers/writers cho body và một số thiết lập codec |
| `configureContentTypeResolver(...)` | Tùy chỉnh cách xác định media type cho request |
| `addCorsMappings(...)` | Cấu hình CORS mapping |
| `addResourceHandlers(...)` | Cấu hình tài nguyên tĩnh |

Bài này tập trung vào ba hook đầu và sự khác nhau giữa chúng. Không nên override mọi method chỉ vì interface có sẵn nhiều callback.

## 4. Converter: chuyển giá trị từ một kiểu sang kiểu khác

Spring Conversion SPI cung cấp:

```java
public interface Converter<S, T> {
    T convert(S source);
}
```

Đây là **chữ ký minh họa** của `org.springframework.core.convert.converter.Converter`, không phải mã cần tự tạo interface.

Ví dụ ứng dụng có kiểu giá trị định danh:

```java
public record OrderCode(String value) {}
```

Một converter có thể chuẩn hóa text đầu vào thành mã đơn hàng:

```java
public class StringToOrderCode implements Converter<String, OrderCode> {

    @Override
    public OrderCode convert(String raw) {
        String code = raw.trim().toUpperCase(Locale.ROOT);
        if (!code.matches("ORD-[0-9]{3}")) {
            throw new IllegalArgumentException("Invalid order code");
        }
        return new OrderCode(code);
    }
}
```

Đây là đoạn **minh họa từng phần**; cần import `Converter`, `Locale` và record `OrderCode`. Bản chạy đầy đủ nằm ở mục 7.

Đăng ký với WebFlux:

```java
@Override
public void addFormatters(FormatterRegistry registry) {
    registry.addConverter(new StringToOrderCode());
}
```

Khi request có `code=ord-123` và đối số/thuộc tính Java cần `OrderCode`, conversion service có thể gọi converter để tạo `new OrderCode("ORD-123")`.

**Nguyên tắc viết Converter:**

- Chỉ thực hiện chuyển kiểu; không truy vấn database hoặc thực hiện I/O blocking.
- Nếu định dạng không hợp lệ, ném exception rõ ràng; binder/argument resolver sẽ chuyển thành lỗi tương ứng tùy nơi conversion diễn ra.
- Tránh thay đổi global state khi thực hiện chuyển đổi.
- Không dùng `Converter<String,T>` để tự làm nhiệm vụ giải mã JSON body của Jackson.
- Với giá trị `null`, conversion service có quy tắc xử lý nguồn rỗng; validator kiểm tra `@NotNull` nếu cần cấm giá trị thiếu.
- Khi định dạng có nhiều trường hợp locale, ưu tiên `Formatter` hoặc parser dùng `Locale` thay vì hardcode một phương thức chuyển đổi thiếu ngữ cảnh.

### 4.1. GenericConverter và ConverterFactory khi nào dùng?

Nếu quy tắc cần hỗ trợ một họ kiểu đích, Spring còn có `ConverterFactory<S,R>`; nếu cần xem source/target descriptor hoặc cấu trúc phức tạp, có `GenericConverter`. Với một cặp kiểu đơn giản và cố định, `Converter<S,T>` dễ đọc, dễ test và ít khó khăn hơn.

## 5. Formatter: parse, print và Locale

Spring Formatting SPI định nghĩa:

```java
public interface Formatter<T> extends Printer<T>, Parser<T> {

    // Parser<T>: T parse(String text, Locale locale)
    // Printer<T>: String print(T object, Locale locale)
}
```

Đây là **hình dạng API để giải thích**, không phải code cần viết mới. Khác converter một chiều, formatter bao gồm cả:

- `parse(text, locale)`: từ chuỗi người dùng nhập sang object Java.
- `print(object, locale)`: từ object sang chuỗi trình bày.

Ví dụ loại giá trị `DeliveryDate` nhận input `2026/11/20`:

```java
public record DeliveryDate(LocalDate value) {}
```

Formatter minh họa:

```java
public class DeliveryDateFormatter implements Formatter<DeliveryDate> {

    private static final DateTimeFormatter FORMAT =
        DateTimeFormatter.ofPattern("uuuu/MM/dd", Locale.ROOT)
            .withResolverStyle(ResolverStyle.STRICT);

    @Override
    public DeliveryDate parse(String text, Locale locale) {
        return new DeliveryDate(LocalDate.parse(text, FORMAT));
    }

    @Override
    public String print(DeliveryDate object, Locale locale) {
        return FORMAT.format(object.value());
    }
}
```

Khi `addFormatters(registry)` gọi `registry.addFormatter(new DeliveryDateFormatter())`, WebFlux có thể chuyển `"2026/11/20"` thành object `DeliveryDate(LocalDate.of(2026,11,20))` và in lại theo quy ước của formatter.

Formatter trên dùng định dạng cố định nên không sử dụng tham số `locale` để quyết định dấu phân cách. Đây là chủ đích của ví dụ API. Với tiền tệ, số theo vùng hoặc ngày theo ngôn ngữ, hãy dùng `locale` thực sự và kiểm thử cả chiều `parse` và `print`.

### 5.1. Formatters sẵn có

Spring WebFlux đã cài nhiều formatter mặc định cho số, ngày giờ và hỗ trợ annotation:

- `@DateTimeFormat`
- `@NumberFormat`
- `@DurationFormat` (trong những phiên bản hỗ trợ)

Ví dụ nếu cần HTML `<input type="date">` với format ISO cố định thay vì parse ngày theo locale:

```java
@Override
public void addFormatters(FormatterRegistry registry) {
    DateTimeFormatterRegistrar registrar = new DateTimeFormatterRegistrar();
    registrar.setUseIsoFormat(true);
    registrar.registerFormatters(registry);
}
```

Đây là đoạn cấu hình tích hợp, cần import `org.springframework.format.datetime.standard.DateTimeFormatterRegistrar`. Khi bổ sung vào cấu hình thực tế, hãy kết hợp với những converter/formatter khác trong **cùng method `addFormatters`** thay vì khai báo nhiều method Java có cùng chữ ký.

### 5.2. Conversion và formatting không phải JSON codecs

Ví dụ `@RequestParam("shipOn") DeliveryDate shipOn` dùng conversion/formatting của WebFlux. Nhưng `@RequestBody Mono<BookingRequest>` dùng HTTP message reader để deserialize JSON. Muốn tùy biến `DeliveryDate` bên trong JSON, thường cần cấu hình Jackson serializer/deserializer, annotation hoặc module phù hợp; **không nên coi `FormatterRegistry` như cấu hình thay thế ObjectMapper**.

## 6. Validator: kiểm tra dữ liệu đã bind

### 6.1. Mặc định khi có Jakarta Bean Validation

Khi provider Jakarta Bean Validation (thường Hibernate Validator) nằm trong classpath, Spring WebFlux có thể đăng ký `LocalValidatorFactoryBean` làm global validator cho `@Valid` và `@Validated` trên controller method arguments. Vì vậy nhiều ứng dụng chỉ cần:

```java
public class BookingForm {

    @NotNull
    private OrderCode code;

    @NotNull
    private DeliveryDate deliveryDate;

    @NotNull
    @Min(1)
    private Integer amount;

    // Constructors, getters và setters...
}
```

Nếu `@Valid @ModelAttribute("booking") BookingForm form` được bind, việc validation có thể phát hiện các giá trị thiếu hoặc số lượng nhỏ hơn 1.

### 6.2. getValidator() trả về Validator nào?

Method của `WebFluxConfigurer` là:

```java
@Override
public org.springframework.validation.Validator getValidator() {
    // Trả về Spring Validator muốn sử dụng toàn cục.
    return configuredValidator;
}
```

**Trả về validator tự viết không có tích hợp Jakarta Bean Validation có thể thay thế validator mặc định.** Khi đó annotation `@NotNull`, `@Email`, `@Min` trong DTO sẽ không tự được đánh giá qua cùng đường global validation nếu validator mới không thực thi Bean Validation.

Cách minh họa rõ ràng để **giữ Jakarta constraints** nhưng chủ động chỉ định global validator trong một `@Configuration` class:

```java
@Bean
public LocalValidatorFactoryBean applicationJakartaValidator() {
    return new LocalValidatorFactoryBean();
}

@Override
public Validator getValidator() {
    return applicationJakartaValidator();
}
```

Đây là **đoạn cấu hình tích hợp**: `LocalValidatorFactoryBean` là Spring `Validator`/`SmartValidator` đồng thời tích hợp Jakarta Bean Validation. Với `@Configuration` mặc định (proxy bean methods), lời gọi `applicationJakartaValidator()` do Spring điều phối để dùng bean được quản lý; không sao chép máy móc vào cấu hình `@Configuration(proxyBeanMethods=false)` rồi giả định lần gọi method trực tiếp luôn trả cùng singleton.

**Đa số Spring Boot app không cần tự override `getValidator()`**; chỉ nên làm khi cần kiểm soát rõ global validator/factory, message interpolation hay cấu hình validation. Ví dụ đầy đủ ở mục 7 chủ động sử dụng hook để quan sát cách kết nối.

### 6.3. Spring Validator và SmartValidator

Spring `org.springframework.validation.Validator` có hai method:

```java
boolean supports(Class<?> clazz);
void validate(Object target, Errors errors);
```

Một custom validator kiểm tra object và ghi lỗi bằng `errors.rejectValue("field","code")` hoặc `errors.reject("code")`. `SmartValidator` thêm khả năng nhận hints (ví dụ validation groups) qua `validate(target,errors,hints...)`. `LocalValidatorFactoryBean` hỗ trợ việc chuyển hints của `@Validated(SomeGroup.class)` cho provider.

Không giả định một custom Spring `Validator` chỉ cài hai method cơ bản sẽ hiểu validation groups; nếu cần phân nhánh theo groups, hãy thiết kế/hỗ trợ `SmartValidator` hoặc dùng trực tiếp API Bean Validation thích hợp.

### 6.4. Local validator với @InitBinder

Khi một rule chỉ dành cho một controller/form, giữ global validator và **bổ sung** rule cục bộ:

```java
@InitBinder("booking")
void initBookingBinder(WebDataBinder binder) {
    binder.addValidators(bookingPolicyValidator);
}
```

Đây là đoạn **minh họa thuộc controller**, không phải standalone; cần `WebDataBinder`, một biến/bean `bookingPolicyValidator` và `@InitBinder`. 
- `addValidators(...)` giữ lại những validator đã đăng ký.
- `setValidator(...)` thay danh sách validator của binder; vô tình có thể làm mất global Bean Validation.
- `supports(BookingForm.class)` của validator phải đúng kiểu target được bind.
- `@InitBinder` không tự bật validation; nó cấu hình binder. Tham số được đánh dấu `@Valid` hoặc `@Validated` sẽ kích hoạt validation theo đường tương ứng.

Trong WebFlux, form object **không bọc reactive type** có thể đi kèm `BindingResult` ngay sau trong chữ ký controller. Nếu khai báo `@ModelAttribute Mono<BookingForm>` thì không thể dùng cùng cách đặt `BindingResult` synchronous ngay sau để xử lý lỗi; hãy xử lý lỗi trong reactive pipeline.

### 6.5. Lỗi và exception của WebFlux không giống MVC

Với `@Valid @ModelAttribute`, nếu không đặt `BindingResult` kề bên, Spring WebFlux thường phát `WebExchangeBindException` khi binding/validation thất bại; trong Spring MVC Servlet stack, loại exception tương ứng thường là `MethodArgumentNotValidException`. Với direct constraint trên tham số handler, WebFlux 6.1+ còn có method-validation path và có thể dùng `HandlerMethodValidationException`. Không viết `@ControllerAdvice` WebFlux chỉ bắt mỗi exception của Spring MVC.

Một form có `BindingResult` kề sau được controller xử lý sẽ **không tự động trả HTTP 400**: controller phải chọn status, response body hoặc view. Ngoài ra, lỗi HTTP body decode, lỗi missing required query parameter, codec memory limit có đường exception khác chứ không phải tất cả thành `FieldError`.

## 7. Ví dụ Java 17 / Spring Boot 3.5.6 chạy được: Converter + Formatter + Validator

Bài thực hành dùng WebFlux annotated controller, không dùng Spring MVC. Một request gửi ba thuộc tính:

- `code=ord-123`: Converter `String -> OrderCode` tạo `ORD-123`.
- `deliveryDate=2026/11/20`: Formatter parse thành `DeliveryDate` chứa `LocalDate`.
- `amount=2`: Bean Validation kiểm tra `@NotNull @Min(1)`.
- `code=ORD-000`: một local Spring Validator kiểm tra quy tắc mã đặt trước.

### 7.1. Cấu trúc

```text
webflux-conversion-validation/
├── pom.xml
└── src/main/java/demo/reactive/
    ├── ReactiveApp.java
    ├── OrderCode.java
    ├── DeliveryDate.java
    ├── BookingForm.java
    ├── WebFluxConfig.java
    ├── BookingPolicyValidator.java
    └── BookingController.java
```

### 7.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.6</version>
    <relativePath/>
  </parent>

  <groupId>demo</groupId>
  <artifactId>webflux-conversion-validation</artifactId>
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
```

**Quan trọng:** không thêm `spring-boot-starter-web` song song khi chủ đích là chạy ứng dụng WebFlux. Trong cấu hình Boot thông thường, nếu cả MVC và WebFlux cùng có mặt, MVC có thể được ưu tiên chọn làm loại web application. Ví dụ này chỉ dùng WebFlux + Validation.

### 7.3. ReactiveApp.java

```java
package demo.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveApp {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveApp.class, args);
    }
}
```

### 7.4. OrderCode.java

```java
package demo.reactive;

public record OrderCode(String value) {
}
```

`OrderCode` là **value object**. Converter tạo ra object này từ form parameter thay vì để controller tự parse mã text.

### 7.5. DeliveryDate.java

```java
package demo.reactive;

import java.time.LocalDate;

public record DeliveryDate(LocalDate value) {
}
```

Record giữ ngày dưới kiểu Java rõ ràng. Formatter chịu trách nhiệm cú pháp văn bản của request.

### 7.6. BookingForm.java

```java
package demo.reactive;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

public class BookingForm {

    @NotNull
    private OrderCode code;

    @NotNull
    private DeliveryDate deliveryDate;

    @NotNull
    @Min(1)
    private Integer amount;

    public BookingForm() {
    }

    public OrderCode getCode() {
        return code;
    }

    public void setCode(OrderCode code) {
        this.code = code;
    }

    public DeliveryDate getDeliveryDate() {
        return deliveryDate;
    }

    public void setDeliveryDate(DeliveryDate deliveryDate) {
        this.deliveryDate = deliveryDate;
    }

    public Integer getAmount() {
        return amount;
    }

    public void setAmount(Integer amount) {
        this.amount = amount;
    }
}
```

`@NotNull` cấm thiếu `code`, `deliveryDate`, `amount`; `@Min(1)` cấm `amount` bằng 0 hoặc âm sau khi đã bind thành `Integer`.

### 7.7. WebFluxConfig.java

```java
package demo.reactive;

import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;
import org.springframework.format.Formatter;
import org.springframework.format.FormatterRegistry;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.validation.Validator;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration
public class WebFluxConfig implements WebFluxConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToOrderCodeConverter());
        registry.addFormatter(new DeliveryDateFormatter());
    }

    @Bean("applicationJakartaValidator")
    public LocalValidatorFactoryBean applicationJakartaValidator() {
        return new LocalValidatorFactoryBean();
    }

    @Override
    public Validator getValidator() {
        // @Configuration mặc định proxyBeanMethods=true:
        // Spring điều phối lời gọi để lấy bean đã được quản lý.
        return applicationJakartaValidator();
    }

    @Override
    public void configureHttpMessageCodecs(ServerCodecConfigurer configurer) {
        // Dành cho body codecs; không thay addFormatters.
        configurer.defaultCodecs().maxInMemorySize(512 * 1024);
    }

    private static final class StringToOrderCodeConverter
            implements Converter<String, OrderCode> {

        @Override
        public OrderCode convert(String source) {
            String normalized =
                    source.trim().toUpperCase(Locale.ROOT);

            if (!normalized.matches("ORD-[0-9]{3}")) {
                throw new IllegalArgumentException("Invalid order code");
            }

            return new OrderCode(normalized);
        }
    }

    private static final class DeliveryDateFormatter
            implements Formatter<DeliveryDate> {

        private static final DateTimeFormatter DATE =
            DateTimeFormatter.ofPattern("uuuu/MM/dd", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);

        @Override
        public DeliveryDate parse(String text, Locale locale) {
            return new DeliveryDate(LocalDate.parse(text, DATE));
        }

        @Override
        public String print(DeliveryDate object, Locale locale) {
            return DATE.format(object.value());
        }
    }
}
```

Đây là cấu hình trung tâm của ví dụ:

- `addFormatters` cài converter và formatter chung cho argument binding.
- `getValidator` chọn một `LocalValidatorFactoryBean` **được quản lý như Spring bean**, để Jakarta constraints tiếp tục hoạt động. Ví dụ chủ động override hook nhằm minh họa API; nhiều Spring Boot app nên dùng validator mặc định nếu không cần tùy biến.
- `configureHttpMessageCodecs` giới hạn bộ đệm in-memory của một số HTTP body codecs ở 512 KiB; nó **không** quyết định format của `deliveryDate` hay cú pháp `code` từ form.
- `@Configuration` dùng chế độ proxy method mặc định; không đổi sang `proxyBeanMethods=false` trong khi vẫn dựa vào lời gọi `applicationJakartaValidator()` từ `getValidator()`.
- Không dùng `@EnableWebFlux` nên giữ cơ hội cho Spring Boot auto-configuration của WebFlux.

Đây không phải cách duy nhất tích hợp Jakarta validator; bạn cũng có thể inject một Jakarta provider có sẵn và adapt nó đúng cách. Điều quan trọng là validator được chọn toàn cục vẫn hỗ trợ các constraint của DTO cần dùng.

### 7.8. BookingPolicyValidator.java

```java
package demo.reactive;

import org.springframework.stereotype.Component;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

@Component
public class BookingPolicyValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return BookingForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        BookingForm form = (BookingForm) target;

        if (form.getCode() != null
                && "ORD-000".equals(form.getCode().value())) {
            errors.rejectValue(
                "code", "reservedCode",
                "Mã đơn hàng này được dành riêng");
        }
    }
}
```

Validator là bean singleton nhưng không giữ dữ liệu thay đổi theo request. Nó kiểm tra sau khi code đã được converter chuyển về dạng chuẩn. Đây là rule cục bộ của form, không ảnh hưởng các controller khác.

### 7.9. BookingController.java

```java
package demo.reactive;

import jakarta.validation.Valid;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.stream.Collectors;

@RestController
public class BookingController {

    private final BookingPolicyValidator bookingPolicy;

    public BookingController(BookingPolicyValidator bookingPolicy) {
        this.bookingPolicy = bookingPolicy;
    }

    @InitBinder("booking")
    void initBookingBinder(WebDataBinder binder) {
        // Thêm rule cục bộ, không thay validator global.
        binder.addValidators(bookingPolicy);
    }

    @PostMapping(
        path = "/bookings",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<String> create(
            @Valid @ModelAttribute("booking") BookingForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            String codes = errors.getFieldErrors().stream()
                .map(error -> error.getField() + ":" + shortCode(error))
                .sorted()
                .collect(Collectors.joining(","));

            return ResponseEntity.badRequest()
                    .body("INVALID|" + codes);
        }

        return ResponseEntity.ok(
                "OK|" + form.getCode().value()
                + "|" + form.getDeliveryDate().value()
                + "|" + form.getAmount());
    }

    private static String shortCode(FieldError error) {
        String[] codes = error.getCodes();
        return codes == null || codes.length == 0
                ? "unknown"
                : codes[codes.length - 1];
    }
}
```

Chú ý ba chỗ:

1. `@InitBinder("booking")` thêm local validator cho model attribute `booking`; tên phải trùng với `@ModelAttribute("booking")`.
2. `@Valid` kích hoạt validation trên object đã bind; global validator và local validator cùng đóng góp lỗi vào `BindingResult`.
3. `BindingResult` đứng **ngay sau** `BookingForm` và không bọc trong `Mono<BindingResult>`. Controller có thể trả lỗi tại chỗ. Sau bước `hasErrors()` thành công mới dùng các giá trị đã được convert.

Đây là **annotated WebFlux handler trả `ResponseEntity<String>` trực tiếp** — loại return value hợp lệ trong WebFlux. Nó không thực hiện blocking I/O. Với nghiệp vụ bất đồng bộ như đọc database reactive, có thể chuyển thân nghiệp vụ sang `Mono<ResponseEntity<...>>` mà vẫn giữ thiết kế validation rõ ràng.

### 7.10. Lệnh chạy và kết quả

Yêu cầu Java 17+, Maven 3.x, cổng 8080 còn trống. Trong thư mục có `pom.xml`:

```bash
mvn -q spring-boot:run
```

Ứng dụng dùng Reactor Netty theo starter WebFlux mặc định. Trong terminal bash/zsh/WSL khác, gửi các request.

**Case A — Converter, Formatter, Validator đều hợp lệ:**

```bash
curl -s -X POST 'http://localhost:8080/bookings' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'code=ord-123' \
  --data-urlencode 'deliveryDate=2026/11/20' \
  --data-urlencode 'amount=2'
```

HTTP **200 OK**, response body:

```text
OK|ORD-123|2026-11-20|2
```

- Converter đổi `ord-123` thành `OrderCode("ORD-123")`.
- Formatter parse `2026/11/20` thành `LocalDate.of(2026,11,20)`.
- Global validator chấp nhận cả ba field.
- Local validator không phát hiện mã đặt trước.

**Case B — Jakarta Bean Validation phát hiện số lượng sai:**

```bash
curl -s -X POST 'http://localhost:8080/bookings' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'code=ord-123' \
  --data-urlencode 'deliveryDate=2026/11/20' \
  --data-urlencode 'amount=0'
```

HTTP **400 Bad Request**, body:

```text
INVALID|amount:Min
```

Mã `Min` được tạo bởi global Jakarta Bean Validation. Controller chủ động trả status 400, không phải `BindingResult` tự chọn HTTP status.

**Case C — Local Spring Validator phát hiện mã không được phép:**

```bash
curl -s -X POST 'http://localhost:8080/bookings' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'code=ord-000' \
  --data-urlencode 'deliveryDate=2026/11/20' \
  --data-urlencode 'amount=2'
```

HTTP **400 Bad Request**, body:

```text
INVALID|code:reservedCode
```

Mã `reservedCode` xuất phát từ `BookingPolicyValidator`; rule global `@NotNull` không thay thế logic local.

**Case D — Formatter không đọc được ngày:**

```bash
curl -s -X POST 'http://localhost:8080/bookings' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'code=ord-123' \
  --data-urlencode 'deliveryDate=2026/13/20' \
  --data-urlencode 'amount=2'
```

Bước parse không thể biến tháng 13 thành `LocalDate`. Với cơ chế property binding thông thường, `BindingResult` có lỗi `typeMismatch` của `deliveryDate` và controller trả HTTP 400. Dạng body dự kiến trong ví dụ:

```text
INVALID|deliveryDate:typeMismatch
```

Đây là **lỗi conversion/formatting**, không phải lỗi `@Min` hay một constraint ngày đã chạy. Nếu ứng dụng tùy biến message codes hoặc binding behavior, chi tiết chuỗi lỗi có thể khác; phần quyết định là phải trả lỗi có cấu trúc, không cố xử lý `deliveryDate` như thể nó đã được chuyển hợp lệ.

**Case E — Thiếu thuộc tính ngày:**

```bash
curl -s -X POST 'http://localhost:8080/bookings' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'code=ord-123' \
  --data-urlencode 'amount=2'
```

Do `deliveryDate` còn `null` sau binding, global validator phát hiện `@NotNull`; HTTP 400, body:

```text
INVALID|deliveryDate:NotNull
```

Các output trên là **HTTP response body**, không phải toàn bộ log Maven, Netty hoặc Spring Boot. `curl -s` cũng không tự thêm dòng mới. Chương trình cố tình in mã lỗi tổng quát và sắp xếp để tránh phụ thuộc thứ tự tạo `FieldError`.

### 7.11. Nếu bỏ getValidator() hoặc thay bằng validator không tích hợp Jakarta?

Nếu xóa override `getValidator()` nhưng vẫn giữ dependency provider và cấu hình Boot bình thường, framework thường cung cấp global Bean Validation validator mặc định, nên các constraint vẫn có thể được đánh giá. **Không phải bỏ override là tắt validation.**

Nếu thay `getValidator()` bằng một Spring `Validator` chỉ kiểm tra `BookingForm.code` và không dùng provider, `@NotNull`/`@Min` có thể bị bỏ qua tại đường global binder validation. Trong trường hợp ấy phải chủ động xây dựng chiến lược kết hợp nếu muốn giữ cả hai; không dựa vào việc dependency Hibernate Validator vẫn nằm trong classpath để kết luận.

## 8. configureHttpMessageCodecs khác addFormatters như thế nào?

Dù tên “converter” có thể gây nhầm, WebFlux HTTP **codecs** xử lý byte buffers/nội dung HTTP, còn Spring **ConversionService** xử lý typed values trong argument binding.

| Tình huống | API/cơ chế chính |
| --- | --- |
| `?count=12` thành `int` | ConversionService / converter mặc định |
| `?code=ord-123` thành `OrderCode` | Custom `Converter<String, OrderCode>` trong `addFormatters` |
| `?deliveryDate=2026/11/20` thành `DeliveryDate` | Custom `Formatter<DeliveryDate>` trong `addFormatters` |
| `@Valid @ModelAttribute BookingForm` | WebExchangeDataBinder + WebFlux global/local Validator |
| `@RequestBody Mono<BookingJson>` đọc JSON | `HttpMessageReader` + Jackson decoder/codec |
| `Mono<BookingResponse>` trả JSON | `HttpMessageWriter` + Jackson encoder/codec |
| Giới hạn byte in-memory khi decode body | `configureHttpMessageCodecs` / `ServerCodecConfigurer` |
| Cấu hình JSON date serialization | Jackson serializer/deserializer/module, không phải `FormatterRegistry` đơn thuần |

Ví dụ cấu hình body memory limit:

```java
@Override
public void configureHttpMessageCodecs(ServerCodecConfigurer codecs) {
    codecs.defaultCodecs().maxInMemorySize(512 * 1024);
}
```

Không nên tưởng rằng giới hạn 512 KiB là giới hạn độ dài của một `@RequestParam` hay giới hạn mọi lượng dữ liệu stream; nó điều chỉnh kích thước đệm của một số thao tác decode/aggregate qua codecs. Với dữ liệu upload lớn, cần thiết kế streaming, phân tích cấu hình codec cụ thể, xác thực input và giới hạn ở tầng web server/gateway.

Trong ứng dụng Spring Boot, nếu yêu cầu chỉ là tăng/giảm buffer codec, có thể cân nhắc cấu hình property hoặc customizer được Boot hỗ trợ thay vì phải override toàn bộ WebFluxConfigurer. Dù chọn cách nào, không thay registry formatter chỉ để giải quyết lỗi decoder JSON.

## 9. Vùng áp dụng: Controller annotation, reactive type và functional routes

`WebFluxConfigurer#addFormatters` phục vụ type conversion/formatting của các annotated controller method arguments và data binding tương ứng. Nó không khiến mọi chỗ trong toàn hệ thống có thể tự động gọi cùng converter:

- `WebClient` đọc JSON response bằng codec riêng, không mặc định dùng custom argument converter của server cho từng field JSON.
- Functional routes (`RouterFunction` + `HandlerFunction`) có thể dùng codec chung cho request/response body, nhưng nếu handler tự lấy String từ query rồi parse thủ công, bạn cần chủ động sử dụng `ConversionService` hoặc parser thích hợp.
- Reactive repository/service không tự được validate bằng `getValidator()` của WebFlux. Có thể cần explicit Bean Validation, method validation khác hoặc validation trong reactive pipeline tùy kiến trúc.
- `@ModelAttribute Mono<T>` hỗ trợ reactive binding, nhưng `BindingResult` synchronous **không** thể đặt như một cặp liền kề với wrapper reactive. Hãy xử lý binding/validation errors trong `Mono`.

Đừng ép mọi rule nghiệp vụ vào `Converter` hoặc `Formatter`. Chúng nên chuyển kiểu nhất quán và đủ nhanh; kiểm tra uniqueness trong database là việc của service/database, đặc biệt vì validation của controller không tự bảo đảm dữ liệu không thay đổi do concurrent requests.

## 10. Tùy biến Validator và nhiều bộ kiểm tra

Nếu ứng dụng có nhiều quy tắc:

- **Global:** dùng `LocalValidatorFactoryBean` cho các annotation Jakarta.
- **Local:** dùng `@InitBinder("booking")` rồi `binder.addValidators(bookingPolicyValidator)` cho một form.
- **Validator mở rộng:** viết Spring `Validator` và khai báo `supports(Class<?>)` chính xác. Với nhiều field, gọi `errors.rejectValue(...)` cho field hoặc `errors.reject(...)` cho lỗi object.

Phân biệt API của binder:

| API | Tác động |
| --- | --- |
| `binder.addValidators(v1, v2)` | Giữ validator đang có và bổ sung v1, v2 |
| `binder.setValidator(v)` | Thay danh sách bằng validator được đưa vào |
| `binder.replaceValidators(v1,v2)` | Thay toàn bộ danh sách với nhiều validator |
| `binder.getValidators()` | Quan sát danh sách validator đã đăng ký |

Không viết một `@InitBinder` không giới hạn phạm vi mà thêm validator chỉ hỗ trợ `BookingForm` vào binder của mọi class; `supports(clazz)` có thể không phù hợp và làm cấu hình lỗi. 
Khi đặt `@InitBinder` trong `@ControllerAdvice`, có thể chia sẻ rule giữa nhiều controller nhưng phải kiểm soát selector và model attribute name. Tránh đăng ký trùng ở advice và controller tạo lỗi bị cộng nhiều lần.

### SmartValidator, hints và group

`@Validated(Group.class)` có thể chuyển group/hints đến `SmartValidator`. `LocalValidatorFactoryBean` hiểu Jakarta groups. Nếu một rule tự viết chỉ triển khai `Validator` thông thường, nó không tự phân biệt validation groups; muốn phụ thuộc nhóm, thiết kế riêng hành vi đó.

**Giữ tính ổn định khi chạy đồng thời:** Spring singleton validators/converters có thể được dùng cho nhiều request; tránh trường mutable per-request trong class. `DateTimeFormatter` trong ví dụ là immutable/thread-safe, phù hợp dùng static final trong formatter.

## 11. Những lỗi hay gặp khi cấu hình

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra và sửa |
| --- | --- | --- |
| Override `addFormatters` nhưng không thấy thay đổi JSON | Nhầm conversion service với Jackson codec | Dùng Jackson serializer/deserializer cho body JSON |
| Dùng `WebMvcConfigurer` trong WebFlux project | Nhầm servlet MVC với reactive WebFlux | Dùng `WebFluxConfigurer` đúng package |
| Thêm `@EnableWebFlux` làm Boot mất vài customizations | Kích hoạt takeover cấu hình framework | Bỏ annotation nếu muốn giữ Boot auto-configuration |
| `@Min` trên form không chạy | Provider thiếu hoặc global validator bị thay bởi custom validator | Kiểm tra starter-validation, `getValidator()`, group |
| `@InitBinder` không chạy với form mong muốn | Tên model attribute không trùng hoặc phạm vi controller sai | Khớp `@InitBinder("booking")` với `@ModelAttribute("booking")` |
| Local validator làm mất global constraint | Dùng `setValidator(...)` thay vì `addValidators(...)` | Giữ global rồi thêm validator local |
| `Converter` thất bại nhưng có lỗi `typeMismatch` | Chuỗi không khớp cú pháp target | Trả lỗi 4xx theo binder/argument resolver, không xử lý như giá trị hợp lệ |
| `Formatter` parse ngày không hợp lệ | Format/request Locale mismatch hoặc ngày không tồn tại | Test format và `Locale`, phân biệt ISO HTML |
| `BindingResult` không dùng được sau `Mono<Form>` | Model attribute reactive wrapper | Xử lý lỗi bên trong reactive pipeline |
| Chỉ bắt `MethodArgumentNotValidException` trong WebFlux | Áp dụng nhầm đường MVC exception | Xử lý `WebExchangeBindException` và lỗi WebFlux tương ứng |
| Lỗi `DataBufferLimitException` | Tùy chọn memory của body codec không phù hợp payload | Xem `configureHttpMessageCodecs`/Boot property và streaming |
| Controller khác không nhận converter mong muốn | Cấu hình WebFlux không được quét hoặc dùng MVC thay vì WebFlux | Kiểm tra application type, package scan, starter và config class |
| Cùng một rule bị chạy hai lần | Trùng validator được đăng ký ở global, local hoặc ControllerAdvice | Tách rõ phạm vi và danh sách validator |

## 12. Hướng kiểm thử thực tế

Nên kiểm tra ở ít nhất hai tầng:

1. **Unit test** `StringToOrderCodeConverter#convert` và `DeliveryDateFormatter#parse/print` với các giá trị hợp lệ/sai.
2. **WebFlux integration test** bằng `WebTestClient` để xác nhận registry thực sự được áp dụng vào `@ModelAttribute`, validator chạy và HTTP status đúng.

Các trường hợp cần phủ:

- `ord-123` thành `ORD-123`, đúng record `OrderCode`.
- Ngày `2026/11/20` parse thành `2026-11-20`.
- Ngày `2026/13/20` gây lỗi conversion chứ không được chấp nhận.
- `amount=0` bị `@Min(1)` từ global validator từ chối.
- Thiếu `amount`/`deliveryDate` bị `@NotNull` từ chối.
- `ORD-000` bị local validator trả mã `reservedCode`.
- Một request sai ở nhiều field có `BindingResult` chứa các lỗi tương ứng.
- JSON `@RequestBody` không mặc nhiên chạy custom `Formatter<DeliveryDate>` khi chưa cấu hình Jackson.
- Form reactive `Mono<BookingForm>` có đường xử lý lỗi khác cặp synchronous `BindingResult`.
- Khi có direct method constraint, kiểm tra đường `HandlerMethodValidationException` (WebFlux 6.1+).
- Không có lỗi mà controller trả thành công và không thực thi business side effect khi input sai.

Nếu chọn `WebTestClient`, có thể dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)` và `@AutoConfigureWebTestClient` cùng `spring-boot-starter-test`, nhưng đây là **mở rộng kiểm thử** ngoài source chạy mẫu ở mục 7. Với callback thuần như converter/formatter, unit test Java đơn giản giúp cô lập lỗi trước khi thử HTTP.

## 13. Các nguyên tắc triển khai an toàn

- **Không block event loop:** Tránh gọi repository JDBC blocking, network blocking, đọc file lớn hoặc sleep trong `Converter`, `Formatter`, `Validator`. Nếu cần async validation, thiết kế explicit reactive workflow thay vì cố giấu I/O bên trong synchronous SPI.
- **Không cho request bind trực tiếp mọi thuộc tính của entity:** Dùng DTO riêng; khi cần property binding, giới hạn allowed fields để giảm mass assignment risk.
- **Không coi validation tại HTTP boundary là phân quyền:** Luôn kiểm tra authentication/authorization và quyền thao tác trong service.
- **Không dùng formatter làm nguồn quy tắc nghiệp vụ:** Formatter lo chuyển format, validator lo quy tắc giá trị; uniqueness hoặc tồn tại trong database phải được bảo vệ bằng giao dịch/ràng buộc thích hợp.
- **Không trả dữ liệu nhạy cảm vào lỗi:** `FieldError#getRejectedValue()`, raw object arguments và stack trace có thể chứa thông tin cần bảo vệ; chuẩn hóa error code và thông báo an toàn.
- **Không dựa vào thứ tự `getFieldErrors()`:** Chuỗi ví dụ dùng `sorted()`; API thực tế nên định nghĩa response model lỗi ổn định, hỗ trợ localization bằng `MessageSource`.
- **Không cấu hình hai global validators cạnh tranh mà không kiểm tra:** Nếu nhiều `WebFluxConfigurer` cùng trả về custom global validator, kết quả cấu hình có thể mơ hồ hoặc lỗi. Chọn một chiến lược xác định và viết test.
- **Không bỏ mặc chuyển đổi phụ thuộc locale:** Locale và format của web form có thể khác máy developer; test cả ngày hợp lệ, ngày không tồn tại và hiển thị lại ở giao diện.

## 14. Tổng kết

`WebFluxConfigurer` là điểm mở rộng cấu hình cho Spring WebFlux:

- Dùng **`addFormatters(FormatterRegistry)`** để đăng ký `Converter`, `Formatter` và formatter registrar phục vụ annotated-controller argument binding.
- Dùng **`getValidator()`** để chỉ định Spring `Validator` toàn cục. Nếu muốn giữ các annotation Jakarta như `@NotNull` và `@Min`, hãy dùng validator có tích hợp Bean Validation, phổ biến là `LocalValidatorFactoryBean`.
- Dùng **`@InitBinder(...).addValidators(...)`** để thêm các Spring Validator cục bộ mà không làm mất global validator.
- Dùng **`configureHttpMessageCodecs(ServerCodecConfigurer)`** khi cần tùy chỉnh cách đọc/ghi **HTTP body**; đừng nhầm cơ chế này với chuyển kiểu tham số.
- Trong Spring Boot, triển khai `@Configuration implements WebFluxConfigurer` thường là đủ; tránh `@EnableWebFlux` nếu không chủ ý nắm toàn quyền cấu hình.

Luôn kiểm thử qua WebFlux request thật để xác nhận converter, formatter và validator được gọi đúng nơi. Với WebFlux reactive, đồng thời bảo đảm mọi bộ chuyển đổi/kiểm tra đồng bộ đều nhẹ, thread-safe và không làm block event loop.

## Tài liệu tham khảo

- Spring Framework 6.2 Reference — WebFlux Config, Conversion/Formatting/Validation/Codecs: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html
- Spring Framework 6.2 Javadoc — `WebFluxConfigurer`: https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/web/reactive/config/WebFluxConfigurer.html
- Spring Framework 6.2 Reference — WebFlux `@ModelAttribute`, `BindingResult`: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/modelattrib-method-args.html
- Spring Framework 6.2 Reference — WebFlux controller arguments: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/arguments.html
- Spring Framework 6.2 Reference — WebFlux validation: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-validation.html
- Spring Framework 6.2 Reference — Spring type conversion: https://docs.spring.io/spring-framework/reference/6.2/core/validation/convert.html
- Spring Framework 6.2 Reference — Spring field formatting: https://docs.spring.io/spring-framework/reference/6.2/core/validation/format.html
- Spring Framework 6.2 Javadoc — `LocalValidatorFactoryBean`: https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html
- Spring Boot reference — Reactive web applications: https://docs.spring.io/spring-boot/reference/web/reactive.html