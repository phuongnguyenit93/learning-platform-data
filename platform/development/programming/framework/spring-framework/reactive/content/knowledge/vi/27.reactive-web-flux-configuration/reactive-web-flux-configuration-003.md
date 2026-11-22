# Cấu hình codec, Converter, Formatter và Validator trong Spring WebFlux

## 1. Bốn thành phần giải quyết bốn việc khác nhau

Khi một request đi vào Spring WebFlux, dữ liệu có thể phải đi qua nhiều bước trước khi tới controller:

1. **HTTP message codec** đọc byte từ request body, giải mã thành Java object và mã hóa object thành response body.
2. **Converter** chuyển một giá trị từ kiểu này sang kiểu khác, thường là String thành một kiểu domain.
3. **Formatter** parse và in giá trị theo định dạng gắn với locale, ví dụ ngày tháng hoặc số tiền.
4. **Validator** kiểm tra dữ liệu đã bind hoặc deserialize có đáp ứng các quy tắc hay không.

Ví dụ một API tạo sản phẩm nhận JSON, đồng thời có endpoint tìm kiếm:

- JSON body được codec Jackson đọc thành CreateProductRequest.
- Query parameter category=BOOKS được Converter đổi thành CategoryCode.
- Query parameter from=01/03/2026 được Formatter đổi thành LocalDate.
- @NotBlank, @Positive và validator kiểm tra khoảng ngày xác nhận dữ liệu hợp lệ.

Các thành phần có thể phối hợp trong cùng một request, nhưng chúng không thay thế nhau. Converter không phải JSON decoder; Formatter không phải validator; Validator không tự đọc byte từ HTTP body.

## 2. Luồng xử lý request trong WebFlux

Với annotated controller, luồng tổng quát:

~~~text
HTTP request
    |
    +-- Content-Type / body bytes
    |       |
    |       v
    |   HttpMessageReader
    |       |
    |       v
    |   Decoder / Codec
    |       |
    |       v
    |   Java object (@RequestBody, @RequestPart)
    |
    +-- Query / path / header / form values
            |
            v
        WebDataBinder
            |
            +-- ConversionService
            |       +-- Converter
            |       +-- Formatter
            |
            +-- Validator
                    |
                    v
             Controller method
                    |
                    v
          HttpMessageWriter / Encoder
                    |
                    v
             HTTP response bytes
~~~

Đường đọc request body thường dùng HttpMessageReader và Decoder. Đường ghi response dùng HttpMessageWriter và Encoder. Với các giá trị String từ query, path, header hoặc model attribute, Spring dùng hệ thống binding và ConversionService. Sau khi bind hoặc deserialize, validation kiểm tra object.

Đối với functional endpoints, các codec vẫn được dùng khi gọi bodyToMono, bodyToFlux hoặc writeWith. Converter và Validator thường được gọi rõ ràng hơn trong handler hoặc qua WebExchangeDataBinder nếu ứng dụng tự bind dữ liệu.

## 3. HTTP message codecs: đọc và ghi body

### 3.1. Codec là gì?

Codec là thành phần chuyển đổi giữa byte và object theo kiểu non-blocking:

| Thành phần | Trách nhiệm |
| --- | --- |
| Encoder | Mã hóa object thành byte stream |
| Decoder | Giải mã byte stream thành object |
| HttpMessageReader | Đọc HTTP message body và dùng Decoder phù hợp |
| HttpMessageWriter | Ghi HTTP message body và dùng Encoder phù hợp |
| DataBuffer | Abstraction cho vùng byte mà codec đọc/ghi |
| CodecConfigurer | Đăng ký và tùy chỉnh reader/writer mặc định hoặc custom |

Spring Core cung cấp hỗ trợ cho byte[], ByteBuffer, DataBuffer, Resource và String. Spring Web bổ sung codec cho JSON, XML, form data, multipart, server-sent events và các định dạng khác khi thư viện tương ứng có trên classpath.

Trong ứng dụng Spring Boot WebFlux, các codec mặc định được cấu hình tự động dựa trên dependency. Ví dụ có Jackson trên classpath thì JSON reader/writer được đăng ký. Không cần tự tạo toàn bộ reader/writer cho những định dạng phổ biến.

### 3.2. Content-Type và Accept

Hai header quan trọng:

- **Content-Type** mô tả định dạng body mà client gửi. Server chọn HttpMessageReader phù hợp để đọc.
- **Accept** mô tả định dạng response mà client muốn nhận. Server chọn HttpMessageWriter phù hợp để ghi.

Ví dụ:

~~~http
POST /api/products HTTP/1.1
Content-Type: application/json
Accept: application/json

{"name":"Keyboard","price":49.90}
~~~

Controller nhận CreateProductRequest; Jackson decoder đọc JSON. Khi controller trả object, Jackson encoder ghi response JSON.

Nếu request gửi Content-Type không có reader tương ứng, WebFlux có thể trả 415 Unsupported Media Type. Nếu không có writer phù hợp với Accept, có thể trả 406 Not Acceptable. Nếu body có định dạng được hỗ trợ nhưng dữ liệu không hợp lệ về cú pháp, lỗi decode thường trở thành lỗi request 400.

### 3.3. Tùy chỉnh codec mặc định

Dùng WebFluxConfigurer để cấu hình reader/writer phía server:

~~~java
@Configuration
public class WebConfig implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {

        configurer.defaultCodecs()
                .maxInMemorySize(512 * 1024);
    }
}
~~~

Ví dụ đặt giới hạn buffer tổng hợp ở mức 512 KiB. Giới hạn này áp dụng khi codec cần gom nội dung để decode thành một giá trị như String, byte[] hoặc một object JSON. Khi vượt giới hạn, ứng dụng có thể nhận DataBufferLimitException.

Đây không phải giới hạn tổng dung lượng upload của toàn request. Với dữ liệu lớn, ưu tiên xử lý streaming bằng Flux<DataBuffer>, Flux<PartEvent> hoặc Resource phù hợp thay vì gom toàn bộ nội dung vào một object trong memory.

### 3.4. Cấu hình Jackson ObjectMapper

Nếu muốn dùng ObjectMapper đã được Spring Boot cấu hình, có thể thay decoder/encoder mặc định bằng instance dùng mapper đó:

~~~java
@Configuration
public class JsonCodecConfiguration implements WebFluxConfigurer {

    private final ObjectMapper objectMapper;

    public JsonCodecConfiguration(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {

        configurer.defaultCodecs().maxInMemorySize(512 * 1024);

        configurer.defaultCodecs().jackson2JsonDecoder(
                new Jackson2JsonDecoder(objectMapper));

        configurer.defaultCodecs().jackson2JsonEncoder(
                new Jackson2JsonEncoder(objectMapper));
    }
}
~~~

ObjectMapper do Spring Boot cung cấp có thể đã nhận cấu hình spring.jackson.*, module Java Time và các module Jackson có trên classpath. Dùng chung mapper giúp JSON body tuân theo một chính sách serialize/deserialize thống nhất.

Khi thay decoder hoặc encoder mặc định, hãy bảo đảm codec mới hỗ trợ đủ MediaType mà API cần. Đừng thay codec mặc định bằng một decoder chỉ đọc một media type rồi vô tình làm mất khả năng đọc application/json.

### 3.5. Đăng ký custom codec

Nếu API dùng một định dạng riêng hoặc cần hành vi decode đặc biệt, có thể đăng ký custom Encoder/Decoder hoặc HttpMessageReader/Writer:

~~~java
MimeType customType = MimeType.valueOf("application/x-example-json");

configurer.customCodecs().registerWithDefaultConfig(
        new Jackson2JsonDecoder(objectMapper, customType));

configurer.customCodecs().registerWithDefaultConfig(
        new Jackson2JsonEncoder(objectMapper, customType));
~~~

registerWithDefaultConfig đăng ký codec đồng thời áp dụng một số cấu hình mặc định như maxInMemorySize và logging request details nếu đã được đặt. Dùng register() khi cần tự quản lý cấu hình của codec.

Nếu custom codec cần giới hạn buffer giống codec mặc định, hãy dùng registerWithDefaultConfig hoặc tự cấu hình giới hạn tương ứng. Không giả định custom codec tự động nhận mọi thiết lập của defaultCodecs nếu chỉ đăng ký bằng register().

### 3.6. Không tắt codec mặc định một cách tùy tiện

CodecConfigurer có registerDefaults(false). Khi đặt false, Spring không đăng ký các reader/writer mặc định; ứng dụng phải tự cung cấp đầy đủ codec cần thiết.

Chỉ dùng cách này khi muốn kiểm soát hoàn toàn định dạng HTTP. Nếu chỉ cần bổ sung một định dạng riêng, đăng ký qua customCodecs() và giữ các codec mặc định.

### 3.7. Codec của WebClient là cấu hình riêng

Cấu hình ServerCodecConfigurer trong WebFluxConfigurer tác động tới HTTP server. Nó không tự động thay đổi codec của WebClient.

Client có cấu hình riêng:

~~~java
WebClient client = WebClient.builder()
        .codecs(configurer -> {
            configurer.defaultCodecs()
                    .maxInMemorySize(512 * 1024);
        })
        .build();
~~~

Có thể đăng ký decoder/encoder riêng cho WebClient qua ClientCodecConfigurer. Hãy cấu hình cả hai phía nếu ứng dụng vừa nhận HTTP request vừa gọi API bên ngoài.

### 3.8. Cấu hình Spring Boot 3.5

Spring Boot 3.5 hỗ trợ cấu hình codec dùng chung cho các instance WebFlux server và WebClient tự động cấu hình qua:

~~~yaml
spring:
  http:
    codecs:
      max-in-memory-size: 512KB
      log-request-details: false
~~~

max-in-memory-size giới hạn số byte được buffer khi luồng input cần aggregate. log-request-details bật log form data ở DEBUG và headers ở TRACE khi được đặt true. Các dữ liệu này có thể chứa token, thông tin cá nhân hoặc dữ liệu nhạy cảm; giữ false trong production trừ khi có lý do và biện pháp bảo vệ rõ ràng.

Có thể cấu hình bằng property hoặc qua CodecConfigurer. Nếu cần chính sách riêng cho một server/client hoặc custom codec, cấu hình bằng Java giúp kiểm soát chi tiết hơn.

## 4. Converter: chuyển kiểu dữ liệu

### 4.1. Converter giải quyết vấn đề gì?

HTTP thường truyền giá trị dưới dạng text. Controller có thể cần nhận một kiểu domain thay vì tự parse String ở mọi method.

Converter<S,T> định nghĩa phép chuyển từ kiểu nguồn S sang kiểu đích T:

~~~java
public interface Converter<S, T> {
    T convert(S source);
}
~~~

Ví dụ chuyển chuỗi "books" thành CategoryCode:

~~~java
public record CategoryCode(String value) {
}

public class StringToCategoryCodeConverter
        implements Converter<String, CategoryCode> {

    @Override
    public CategoryCode convert(String source) {
        String normalized = source.trim()
                .toLowerCase(Locale.ROOT);

        if (!normalized.matches("[a-z][a-z0-9-]{0,19}")) {
            throw new IllegalArgumentException("Invalid category code");
        }

        return new CategoryCode(normalized);
    }
}
~~~

Converter phù hợp với logic chuyển kiểu tổng quát, không cần định dạng hiển thị theo locale. Ví dụ khác: String thành UUID, String thành enum domain, Long thành AccountId hoặc String thành một kiểu mã nghiệp vụ.

### 4.2. Đăng ký Converter toàn cục

WebFluxConfigurer.addFormatters nhận FormatterRegistry. Registry này cũng là nơi đăng ký Converter:

~~~java
@Configuration
public class WebConfig implements WebFluxConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToCategoryCodeConverter());
    }
}
~~~

Sau khi đăng ký, Spring có thể chuyển String sang CategoryCode khi bind các giá trị như path variable, request parameter hoặc field của model attribute.

Ví dụ:

~~~java
@GetMapping("/categories/{category}/products")
Mono<List<Product>> products(
        @PathVariable CategoryCode category) {
    return service.findByCategory(category);
}
~~~

Nếu request gọi /categories/BOOKS/products, converter chuẩn hóa giá trị thành CategoryCode("books"). Controller nhận kiểu domain đã được chuyển đổi.

### 4.3. Converter có thể thất bại

Nếu giá trị đầu vào không hợp lệ, converter có thể ném IllegalArgumentException. Spring chuyển lỗi conversion thành lỗi binding/request phù hợp với ngữ cảnh.

Không dùng converter để thay thế validation cho toàn bộ object. Converter chỉ trả lời câu hỏi "String này biểu diễn kiểu đích nào?". Validator trả lời "object sau khi chuyển đổi có đáp ứng quy tắc nghiệp vụ hay không?".

Ví dụ "books" có thể chuyển thành CategoryCode hợp lệ, nhưng một SearchCriteria chứa from sau to vẫn không hợp lệ. Đây là hai bước khác nhau.

## 5. Formatter: parse và in theo Locale

### 5.1. Formatter khác Converter thế nào?

Formatter được thiết kế cho dữ liệu hiển thị/nhập trong môi trường web và có nhận Locale:

~~~java
public interface Formatter<T> {
    T parse(String text, Locale locale) throws ParseException;
    String print(T object, Locale locale);
}
~~~

| Thành phần | Converter | Formatter |
| --- | --- | --- |
| Mục đích | Chuyển đổi kiểu tổng quát | Parse/print giá trị theo định dạng |
| Locale | Không có tham số Locale | Nhận Locale |
| Hướng chuyển đổi | Source sang Target | String sang object và object sang String |
| Ví dụ | String thành CategoryCode | "12/03/2026" thành LocalDate |

Nếu chỉ cần chuyển kiểu, dùng Converter. Nếu cần biểu diễn ngày, số hoặc tiền tệ theo ngôn ngữ/khu vực, Formatter phù hợp hơn.

### 5.2. Formatter cho LocalDate

Ví dụ formatter dùng định dạng ngày dd/MM/yyyy:

~~~java
public class LocalDateFormatter implements Formatter<LocalDate> {

    private DateTimeFormatter formatter(Locale locale) {
        return DateTimeFormatter.ofPattern("dd/MM/uuuu", locale);
    }

    @Override
    public LocalDate parse(String text, Locale locale)
            throws ParseException {
        try {
            return LocalDate.parse(text, formatter(locale));
        } catch (DateTimeParseException error) {
            ParseException exception =
                    new ParseException("Expected dd/MM/yyyy", 0);
            exception.initCause(error);
            throw exception;
        }
    }

    @Override
    public String print(LocalDate value, Locale locale) {
        return formatter(locale).format(value);
    }
}
~~~

Formatter nhận Locale của request để có thể chọn cách parse/print phù hợp. Trong ví dụ này pattern ngày được giữ cố định để API có contract rõ ràng. Nếu muốn dùng định dạng ngày bản địa hóa hoàn toàn, có thể tạo DateTimeFormatter bằng DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT).withLocale(locale).

Không dùng SimpleDateFormat dùng chung trong singleton formatter vì SimpleDateFormat không thread-safe. DateTimeFormatter là immutable và thread-safe, phù hợp cho ứng dụng reactive có nhiều request đồng thời.

### 5.3. Đăng ký Formatter

~~~java
@Override
public void addFormatters(FormatterRegistry registry) {
    registry.addConverter(new StringToCategoryCodeConverter());
    registry.addFormatter(new LocalDateFormatter());
}
~~~

Controller có thể nhận LocalDate trực tiếp:

~~~java
@GetMapping("/search")
Mono<SearchResult> search(
        @RequestParam LocalDate from,
        @RequestParam LocalDate to) {
    return service.search(from, to);
}
~~~

Request:

~~~http
GET /search?from=01%2F03%2F2026&to=31%2F03%2F2026
~~~

Spring bind chuỗi query parameter thành LocalDate bằng formatter đã đăng ký.

### 5.4. Formatter có thể dùng cho model attribute và form

Khi dùng @ModelAttribute, WebDataBinder bind nhiều field vào một object. Converter và Formatter áp dụng cho từng property theo kiểu đích.

~~~java
@GetMapping("/search-form")
Mono<SearchResult> searchForm(
        @Valid @ModelAttribute("criteria") SearchCriteria criteria) {
    return service.search(criteria);
}
~~~

Nếu SearchCriteria có field CategoryCode và LocalDate, Spring dùng converter và formatter để bind các chuỗi tương ứng.

Spring WebFlux đã cài sẵn formatters cho nhiều kiểu số và ngày. Các annotation @NumberFormat, @DurationFormat và @DateTimeFormat có thể tùy chỉnh định dạng cho field/parameter mà không cần viết formatter mới.

### 5.5. DateTimeFormat và HTML date input

Browser dùng định dạng cố định theo HTML cho input type="date" và input type="time". Với form web, có thể cấu hình DateTimeFormatterRegistrar:

~~~java
@Override
public void addFormatters(FormatterRegistry registry) {
    DateTimeFormatterRegistrar registrar =
            new DateTimeFormatterRegistrar();
    registrar.setUseIsoFormat(true);
    registrar.registerFormatters(registry);
}
~~~

ISO format phù hợp với các trường HTML date/time. Hãy phân biệt định dạng hiển thị trong form tự thiết kế với định dạng chuẩn mà browser gửi cho input type="date".

## 6. DataBinder và @InitBinder

### 6.1. DataBinder làm gì?

WebDataBinder điều phối việc bind request values vào object, chuyển kiểu và chạy validation. Nó thường được tạo cho từng lần bind, không nên giữ binder trong field dùng chung.

Một @InitBinder method có thể đăng ký:

- PropertyEditor cũ.
- Converter hoặc Formatter tùy phạm vi binder.
- Validator cục bộ.
- Các cấu hình binding như allowed fields hoặc direct field access khi phù hợp.

### 6.2. Đăng ký validator cục bộ

~~~java
@Controller
public class SearchController {

    @InitBinder("criteria")
    void initCriteriaBinder(WebDataBinder binder) {
        binder.addValidators(new SearchCriteriaValidator());
    }
}
~~~

Tên criteria khớp với tên model attribute. Validator chỉ áp dụng cho binder của object đó. Nếu dùng @ControllerAdvice với @InitBinder, có thể áp dụng cho nhiều controller hoặc nhóm controller theo cấu hình phù hợp.

### 6.3. Converter/Formatter toàn cục và binder cục bộ

Dùng WebFluxConfigurer.addFormatters khi kiểu chuyển đổi được sử dụng ở nhiều controller. Dùng @InitBinder khi quy tắc chỉ phù hợp với một form hoặc controller cụ thể.

Không đăng ký cùng một formatter theo nhiều cách nếu không có lý do, vì thứ tự và phạm vi đăng ký có thể làm kết quả binding khó dự đoán.

## 7. Validator: kiểm tra dữ liệu sau binding

### 7.1. Spring Validator

Spring cung cấp Validator interface:

~~~java
public interface Validator {
    boolean supports(Class<?> clazz);
    void validate(Object target, Errors errors);
}
~~~

supports cho biết validator có xử lý kiểu object đó hay không. validate kiểm tra object và ghi lỗi vào Errors/BindingResult.

Ví dụ kiểm tra khoảng ngày:

~~~java
public class SearchCriteriaValidator implements Validator {

    @Override
    public boolean supports(Class<?> clazz) {
        return SearchCriteria.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        SearchCriteria criteria = (SearchCriteria) target;

        if (criteria.getFrom() != null
                && criteria.getTo() != null
                && criteria.getTo().isBefore(criteria.getFrom())) {
            errors.rejectValue(
                    "to",
                    "date.range.invalid",
                    "to must not be before from"
            );
        }
    }
}
~~~

Validator kiểm tra quan hệ giữa hai field. Đây là ví dụ phù hợp cho custom validator vì một annotation đơn trên từng field không diễn đạt trực tiếp quy tắc from phải nhỏ hơn hoặc bằng to.

### 7.2. Bean Validation với Jakarta

Spring WebFlux hỗ trợ Jakarta Bean Validation. Thêm dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Khi provider như Hibernate Validator có trên classpath, Spring đăng ký LocalValidatorFactoryBean làm global Validator mặc định.

Các annotation thường dùng:

| Annotation | Ý nghĩa |
| --- | --- |
| @NotNull | Giá trị không được null |
| @NotBlank | Chuỗi không null, không rỗng và phải có ký tự không phải whitespace |
| @NotEmpty | Chuỗi/collection/map/array không được rỗng |
| @Size | Giới hạn độ dài hoặc số phần tử |
| @Min / @Max | Giới hạn số nguyên theo ngưỡng |
| @Positive / @PositiveOrZero | Số phải dương hoặc không âm |
| @DecimalMin / @DecimalMax | Giới hạn giá trị decimal |
| @Email | Kiểm tra định dạng email cơ bản |
| @Pattern | Kiểm tra theo regular expression |
| @Valid | Kích hoạt cascade validation cho object lồng nhau |

Ví dụ:

~~~java
public record CreateProductRequest(
        @NotBlank
        @Size(max = 80)
        String name,

        @NotNull
        @DecimalMin("0.01")
        BigDecimal price
) {
}
~~~

Controller:

~~~java
@PostMapping("/products")
Mono<ProductResponse> create(
        @Valid @RequestBody CreateProductRequest request) {
    return service.create(request);
}
~~~

Nếu name rỗng hoặc price nhỏ hơn 0.01, WebFlux từ chối request trước khi gọi logic controller.

### 7.3. @Valid và @Validated

@Valid yêu cầu validation object và cascade xuống các field/object lồng nhau. @Validated là annotation của Spring, hỗ trợ chọn validation groups và một số cách kích hoạt validation khác.

@Valid không phải constraint annotation. Bản thân @Valid không kích hoạt method validation; nó chỉ yêu cầu validate object được đánh dấu và các object lồng nhau.

Ví dụ nested validation:

~~~java
public record AddressRequest(
        @NotBlank String city,
        @NotBlank String street
) {
}

public record CustomerRequest(
        @NotBlank String name,
        @Valid @NotNull AddressRequest address
) {
}
~~~

Nếu thiếu @Valid trên address, constraint của city/street có thể không được cascade kiểm tra.

### 7.4. Validation cho @RequestBody, @RequestPart và @ModelAttribute

WebFlux hỗ trợ validation cho command object được đánh dấu @Valid hoặc @Validated ở các tham số như:

- @RequestBody CreateProductRequest.
- @RequestPart UploadMetadata.
- @ModelAttribute SearchCriteria.

Với tham số là Map hoặc Collection, điều kiện validation có khác biệt; thường nên bọc dữ liệu vào một DTO để khai báo constraint và nested validation rõ ràng.

Nếu cần giữ lỗi để controller tự quyết định, có thể đặt Errors hoặc BindingResult ngay sau tham số được validate. Nếu không, WebFlux phát exception phù hợp.

## 8. Hai loại exception validation trong WebFlux

Từ Spring Framework 6.1, WebFlux có built-in method validation cho annotated controller. Ứng dụng cần phân biệt hai exception chính:

| Exception | Khi nào thường xuất hiện |
| --- | --- |
| WebExchangeBindException | Validation riêng một command object như @ModelAttribute, @RequestBody hoặc @RequestPart |
| HandlerMethodValidationException | Method validation khi constraint như @Min, @NotBlank được đặt trực tiếp trên tham số hoặc return value |

Ví dụ method parameter constraint:

~~~java
@GetMapping("/page")
Mono<PageResult> page(@RequestParam("page") @Min(1) int page) {
    return Mono.just(new PageResult(page));
}
~~~

Nếu page nhỏ hơn 1, built-in method validation có thể phát HandlerMethodValidationException.

Để dùng built-in method validation của Spring Framework 6.1+, không đặt @Validated ở cấp class của controller. @Validated cấp class kích hoạt cơ chế method validation qua AOP proxy; điều đó thay đổi cơ chế và exception được sử dụng.

Ứng dụng nên xử lý cả WebExchangeBindException và HandlerMethodValidationException vì exception phụ thuộc chữ ký controller.

### 8.1. Xử lý lỗi validation tập trung

~~~java
@RestControllerAdvice
public class ValidationAdvice {

    @ExceptionHandler(WebExchangeBindException.class)
    ResponseEntity<ValidationError> handleBinding(
            WebExchangeBindException exception) {

        String detail = exception.getFieldErrors().stream()
                .map(error -> error.getField() + ": "
                        + error.getDefaultMessage())
                .collect(Collectors.joining("; "));

        return ResponseEntity.badRequest().body(
                new ValidationError("VALIDATION_ERROR", detail));
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    ResponseEntity<ValidationError> handleMethodValidation(
            HandlerMethodValidationException exception) {

        return ResponseEntity.badRequest().body(
                new ValidationError(
                        "METHOD_VALIDATION_ERROR",
                        "One or more method parameters are invalid"));
    }
}
~~~

Trong production, nên trả mã lỗi và thông tin field đủ để client sửa request. Không trả stack trace hoặc thông tin nội bộ của validator. Nếu cần message đa ngôn ngữ, sử dụng MessageSource và message bundle thay vì hardcode toàn bộ message.

## 9. Validator toàn cục và validator cục bộ

### 9.1. Validator mặc định

Khi Bean Validation có mặt, LocalValidatorFactoryBean được đăng ký toàn cục. Bạn có thể dùng nó cho @Valid/@Validated trên controller arguments và inject vào service nếu cần validate object ở tầng nghiệp vụ.

### 9.2. Tùy chỉnh global Validator

WebFluxConfigurer có getValidator():

~~~java
@Override
public Validator getValidator() {
    return customGlobalValidator;
}
~~~

Nếu override global validator, cần hiểu rõ việc thay thế validator mặc định. Nếu vẫn cần Bean Validation, hãy kết hợp/delegate tới LocalValidatorFactoryBean thay vì vô tình loại bỏ các constraint Jakarta.

### 9.3. Validator cục bộ qua @InitBinder

~~~java
@InitBinder("criteria")
void initBinder(WebDataBinder binder) {
    binder.addValidators(new SearchCriteriaValidator());
}
~~~

Cách này thêm quy tắc cho một object mà không cần thay validator toàn cục. Đây là lựa chọn dễ kiểm soát khi custom rule chỉ áp dụng cho một form.

### 9.4. Custom constraint annotation

Nếu một quy tắc có thể tái sử dụng trên nhiều DTO, có thể tạo annotation @Constraint và ConstraintValidator. Ví dụ @ValidProductCode có thể kiểm tra format mã sản phẩm. SpringConstraintValidatorFactory cho phép validator nhận dependency từ Spring khi được tạo bởi LocalValidatorFactoryBean.

Dùng Spring Validator khi quy tắc gắn với object và cần Errors; dùng Jakarta constraint khi muốn khai báo annotation tái sử dụng trên field, property, parameter hoặc class.

## 10. Ví dụ Java 17+ chạy được: codec, Converter, Formatter và Validator

Ví dụ sử dụng Spring Boot 3.5.16, Java 17+ và WebFlux. Ứng dụng cung cấp:

- POST /api/products nhận JSON và kiểm tra @NotBlank, @Size, @DecimalMin.
- GET /api/search bind category qua Converter, from/to qua Formatter và kiểm tra khoảng ngày bằng Spring Validator.
- GET /api/page kiểm tra trực tiếp method parameter bằng @Min.
- POST /api/codec-echo minh họa body JSON được đọc/ghi bởi Jackson codec đã cấu hình.

### 10.1. Cấu trúc dự án

~~~text
webflux-binding-demo/
├── pom.xml
└── src/
    ├── main/java/example/binding/
    │   ├── DemoApplication.java
    │   ├── WebConfig.java
    │   ├── ProductController.java
    │   ├── CategoryCode.java
    │   ├── StringToCategoryCodeConverter.java
    │   ├── LocalDateFormatter.java
    │   ├── SearchCriteria.java
    │   ├── SearchCriteriaValidator.java
    │   ├── CreateProductRequest.java
    │   ├── ProductMessage.java
    │   ├── SearchResult.java
    │   ├── ProductResponse.java
    │   ├── PageResult.java
    │   ├── ValidationError.java
    │   └── ValidationAdvice.java
    └── test/java/example/binding/
        └── ProductControllerTest.java
~~~

### 10.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>webflux-binding-demo</artifactId>
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

### 10.3. DemoApplication.java

~~~java
package example.binding;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 10.4. CategoryCode.java

~~~java
package example.binding;

public record CategoryCode(String value) {
}
~~~

### 10.5. StringToCategoryCodeConverter.java

~~~java
package example.binding;

import java.util.Locale;

import org.springframework.core.convert.converter.Converter;

public class StringToCategoryCodeConverter
        implements Converter<String, CategoryCode> {

    @Override
    public CategoryCode convert(String source) {
        String normalized = source.trim()
                .toLowerCase(Locale.ROOT);

        if (!normalized.matches("[a-z][a-z0-9-]{0,19}")) {
            throw new IllegalArgumentException(
                    "Category must contain 1-20 lowercase letters, digits or hyphens");
        }

        return new CategoryCode(normalized);
    }
}
~~~

### 10.6. LocalDateFormatter.java

~~~java
package example.binding;

import java.text.ParseException;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.Locale;

import org.springframework.format.Formatter;

public class LocalDateFormatter implements Formatter<LocalDate> {

    private DateTimeFormatter formatter(Locale locale) {
        return DateTimeFormatter.ofPattern("dd/MM/uuuu", locale);
    }

    @Override
    public LocalDate parse(String text, Locale locale)
            throws ParseException {
        try {
            return LocalDate.parse(text, formatter(locale));
        } catch (DateTimeParseException error) {
            ParseException exception =
                    new ParseException("Expected dd/MM/yyyy", 0);
            exception.initCause(error);
            throw exception;
        }
    }

    @Override
    public String print(LocalDate value, Locale locale) {
        return formatter(locale).format(value);
    }
}
~~~

### 10.7. SearchCriteria.java

~~~java
package example.binding;

import java.time.LocalDate;

import jakarta.validation.constraints.NotNull;

public class SearchCriteria {

    @NotNull
    private CategoryCode category;

    @NotNull
    private LocalDate from;

    @NotNull
    private LocalDate to;

    public CategoryCode getCategory() {
        return category;
    }

    public void setCategory(CategoryCode category) {
        this.category = category;
    }

    public LocalDate getFrom() {
        return from;
    }

    public void setFrom(LocalDate from) {
        this.from = from;
    }

    public LocalDate getTo() {
        return to;
    }

    public void setTo(LocalDate to) {
        this.to = to;
    }
}
~~~

### 10.8. SearchCriteriaValidator.java

~~~java
package example.binding;

import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public class SearchCriteriaValidator implements Validator {

    @Override
    public boolean supports(Class<?> clazz) {
        return SearchCriteria.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        SearchCriteria criteria = (SearchCriteria) target;

        if (criteria.getFrom() != null
                && criteria.getTo() != null
                && criteria.getTo().isBefore(criteria.getFrom())) {
            errors.rejectValue(
                    "to",
                    "date.range.invalid",
                    "to must not be before from"
            );
        }
    }
}
~~~

### 10.9. CreateProductRequest.java

~~~java
package example.binding;

import java.math.BigDecimal;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record CreateProductRequest(
        @NotBlank
        @Size(max = 80)
        String name,

        @NotNull
        @DecimalMin("0.01")
        BigDecimal price
) {
}
~~~

### 10.10. ProductMessage.java

~~~java
package example.binding;

public record ProductMessage(String id, String name) {
}
~~~

### 10.11. Response records

~~~java
package example.binding;

import java.time.LocalDate;

public record SearchResult(
        String category,
        LocalDate from,
        LocalDate to
) {
}
~~~

~~~java
package example.binding;

import java.math.BigDecimal;

public record ProductResponse(String name, BigDecimal price) {
}
~~~

~~~java
package example.binding;

public record PageResult(int page) {
}
~~~

~~~java
package example.binding;

public record ValidationError(String code, String detail) {
}
~~~

Các record trên có thể đặt trong từng file tương ứng như đã liệt kê trong cấu trúc dự án.

### 10.12. WebConfig.java

~~~java
package example.binding;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.http.codec.json.Jackson2JsonDecoder;
import org.springframework.http.codec.json.Jackson2JsonEncoder;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration(proxyBeanMethods = false)
public class WebConfig implements WebFluxConfigurer {

    private final ObjectMapper objectMapper;

    public WebConfig(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {

        configurer.defaultCodecs().maxInMemorySize(512 * 1024);

        configurer.defaultCodecs().jackson2JsonDecoder(
                new Jackson2JsonDecoder(objectMapper));

        configurer.defaultCodecs().jackson2JsonEncoder(
                new Jackson2JsonEncoder(objectMapper));
    }

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToCategoryCodeConverter());
        registry.addFormatter(new LocalDateFormatter());
    }
}
~~~

Không thêm @EnableWebFlux trong ví dụ Spring Boot này. Chỉ triển khai WebFluxConfigurer để bổ sung cấu hình mà vẫn giữ WebFlux auto-configuration của Boot.

### 10.13. ProductController.java

~~~java
package example.binding;

import java.util.UUID;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;

import org.springframework.http.MediaType;
import org.springframework.validation.Validator;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class ProductController {

    @GetMapping("/categories/{category}")
    public Mono<SearchResult> category(
            @PathVariable CategoryCode category) {
        return Mono.just(new SearchResult(
                category.value(), null, null));
    }

    @GetMapping("/search")
    public Mono<SearchResult> search(
            @Valid @ModelAttribute("criteria") SearchCriteria criteria) {
        return Mono.just(new SearchResult(
                criteria.getCategory().value(),
                criteria.getFrom(),
                criteria.getTo()
        ));
    }

    @PostMapping(
            path = "/products",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<ProductResponse> create(
            @Valid @RequestBody CreateProductRequest request) {
        return Mono.just(new ProductResponse(
                request.name(),
                request.price()
        ));
    }

    @PostMapping(
            path = "/codec-echo",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<ProductMessage> codecEcho(
            @RequestBody ProductMessage message) {
        return Mono.just(message);
    }

    @GetMapping("/page")
    public Mono<PageResult> page(
            @RequestParam("page") @Min(1) int page) {
        return Mono.just(new PageResult(page));
    }

    @InitBinder("criteria")
    void initCriteriaBinder(WebDataBinder binder) {
        binder.addValidators(new SearchCriteriaValidator());
    }
}
~~~

Endpoint categories kiểm tra Converter. Endpoint search kiểm tra Converter, Formatter, Bean Validation và custom Spring Validator. Endpoint products kiểm tra codec JSON và Jakarta constraints. Endpoint page kiểm tra method validation trực tiếp trên tham số.

### 10.14. ValidationAdvice.java

~~~java
package example.binding;

import java.util.stream.Collectors;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.support.WebExchangeBindException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;

@RestControllerAdvice
public class ValidationAdvice {

    @ExceptionHandler(WebExchangeBindException.class)
    ResponseEntity<ValidationError> handleBinding(
            WebExchangeBindException exception) {

        String detail = exception.getFieldErrors().stream()
                .map(error -> error.getField() + ": "
                        + error.getDefaultMessage())
                .collect(Collectors.joining("; "));

        return ResponseEntity.badRequest().body(
                new ValidationError("VALIDATION_ERROR", detail));
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    ResponseEntity<ValidationError> handleMethodValidation(
            HandlerMethodValidationException exception) {

        return ResponseEntity.badRequest().body(
                new ValidationError(
                        "METHOD_VALIDATION_ERROR",
                        "One or more method parameters are invalid"));
    }
}
~~~

### 10.15. application.yml

~~~yaml
spring:
  http:
    codecs:
      max-in-memory-size: 512KB
      log-request-details: false
~~~

Property này là cách cấu hình Spring Boot 3.5 cho các codec được auto-configure. WebConfig trong ví dụ cũng đặt giới hạn trực tiếp bằng Java để thể hiện API ServerCodecConfigurer. Khi dùng thực tế, nên chọn một nguồn cấu hình làm chuẩn để tránh hai giá trị khác nhau.

### 10.16. ProductControllerTest.java

~~~java
package example.binding;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ProductControllerTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void convertsCategoryPathVariable() {
        webTestClient.get()
                .uri("/api/categories/BOOKS")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.category").isEqualTo("books");
    }

    @Test
    void formatsDatesAndRunsCustomSearchValidator() {
        webTestClient.get()
                .uri("/api/search?category=BOOKS&from=01%2F03%2F2026&to=31%2F03%2F2026")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.category").isEqualTo("books")
                .jsonPath("$.from").isEqualTo("2026-03-01")
                .jsonPath("$.to").isEqualTo("2026-03-31");
    }

    @Test
    void rejectsInvalidDateRange() {
        webTestClient.get()
                .uri("/api/search?category=books&from=31%2F03%2F2026&to=01%2F03%2F2026")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("VALIDATION_ERROR")
                .jsonPath("$.detail").value(
                        value -> org.assertj.core.api.Assertions
                                .assertThat(value.toString())
                                .contains("to"));
    }

    @Test
    void rejectsInvalidJsonRequest() {
        webTestClient.post()
                .uri("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new CreateProductRequest(
                        " ",
                        BigDecimal.ZERO
                ))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("VALIDATION_ERROR");
    }

    @Test
    void readsAndWritesJsonWithConfiguredCodec() {
        webTestClient.post()
                .uri("/api/codec-echo")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue(new ProductMessage("p-1", "Keyboard"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.id").isEqualTo("p-1")
                .jsonPath("$.name").isEqualTo("Keyboard");
    }

    @Test
    void rejectsInvalidMethodParameter() {
        webTestClient.get()
                .uri("/api/page?page=0")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("METHOD_VALIDATION_ERROR");
    }
}
~~~

### 10.17. Chạy ứng dụng và test

Tại thư mục chứa pom.xml:

~~~bash
mvn test
~~~

Chạy ứng dụng:

~~~bash
mvn spring-boot:run
~~~

Kiểm tra Converter:

~~~bash
curl -i http://localhost:8080/api/categories/BOOKS
~~~

Response minh họa:

~~~json
{
  "category": "books",
  "from": null,
  "to": null
}
~~~

Kiểm tra Formatter và SearchCriteriaValidator:

~~~bash
curl -i "http://localhost:8080/api/search?category=BOOKS&from=01%2F03%2F2026&to=31%2F03%2F2026"
~~~

Response minh họa:

~~~json
{
  "category": "books",
  "from": "2026-03-01",
  "to": "2026-03-31"
}
~~~

Kiểm tra Bean Validation:

~~~bash
curl -i -X POST http://localhost:8080/api/products \
  -H "Content-Type: application/json" \
  -d '{"name":" ","price":0}'
~~~

Request không hợp lệ trả HTTP 400 với code VALIDATION_ERROR. Nội dung detail phụ thuộc message của Bean Validation provider và cấu hình message source.

Kiểm tra method validation:

~~~bash
curl -i "http://localhost:8080/api/page?page=0"
~~~

Request trả HTTP 400 với code METHOD_VALIDATION_ERROR.

## 11. Streaming, DataBuffer và giới hạn bộ nhớ

Codec không phải lúc nào cũng gom toàn bộ body. Với reactive stream, Decoder có thể nhận Flux<DataBuffer> và phát các object theo backpressure.

Các điểm cần nhớ:

- bodyToMono thường cần hoàn tất một giá trị; một số decoder phải aggregate dữ liệu.
- bodyToFlux phù hợp khi định dạng và codec hỗ trợ streaming.
- application/x-ndjson và text/event-stream có thể phát dữ liệu từng phần tử.
- JSON array thông thường có thể được giải mã thành Flux phần tử; hành vi buffering phụ thuộc codec và media type.
- DataBuffer có thể là pooled/direct memory; code tự thao tác buffer phải tuân thủ retain/release.
- maxInMemorySize giới hạn vùng dữ liệu được aggregate, không thay thế giới hạn tổng request, timeout hoặc quota upload.

Không chuyển một luồng file lớn thành byte[] chỉ để dùng Jackson nếu ứng dụng có thể xử lý theo chunk. Với multipart, dùng FilePart hoặc PartEvent theo nhu cầu và quản lý cleanup đúng lifecycle.

## 12. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nghĩ Converter xử lý JSON body | JSON không được đọc qua Converter | Dùng Decoder/HttpMessageReader |
| Dùng Formatter cho mọi chuyển đổi | Logic chuyển kiểu bị gắn định dạng và Locale không cần thiết | Dùng Converter cho chuyển đổi tổng quát |
| Dùng Converter cho ngày tháng hiển thị theo locale | Không có Locale để parse/print | Dùng Formatter hoặc DateTimeFormat |
| Chỉ đăng ký codec custom bằng register() rồi kỳ vọng nhận mọi default setting | Custom codec có thể không nhận maxInMemorySize/logging config | Dùng registerWithDefaultConfig hoặc tự cấu hình |
| Thay Jackson decoder bằng decoder chỉ hỗ trợ một MIME type | application/json có thể không còn được hỗ trợ | Giữ đủ MIME type cần thiết hoặc đăng ký custom codec riêng |
| Tắt registerDefaults mà quên các codec cơ bản | Request/response phổ biến không đọc/ghi được | Giữ defaults và chỉ bổ sung codec khi có thể |
| Tăng maxInMemorySize quá cao | Request lớn có thể làm tăng heap theo concurrency | Đặt giới hạn theo payload và xử lý streaming |
| Nghĩ maxInMemorySize là tổng request limit | Không bảo vệ toàn bộ request hoặc upload | Dùng gateway/body-size policy và stream counter |
| Gọi Formatter có state mutable dùng chung | Race condition giữa request | Dùng DateTimeFormatter immutable và formatter stateless |
| Dùng SimpleDateFormat singleton | SimpleDateFormat không thread-safe | Dùng DateTimeFormatter |
| Converter trả null cho input lỗi | Lỗi binding khó hiểu hoặc che dữ liệu sai | Ném IllegalArgumentException có thông điệp rõ |
| Dùng Validator để chuyển kiểu | Trộn conversion và validation | Chuyển đổi trước, validate object sau |
| Quên @Valid trên object lồng nhau | Constraint của object con không được cascade | Đánh dấu @Valid tại field/parameter cần cascade |
| Cho rằng @Valid tự kích hoạt method validation | Constraint trực tiếp trên method param không được chạy như mong muốn | Đặt constraint như @Min trực tiếp khi cần method validation |
| Đặt @Validated trên toàn controller trong Spring 6.1+ | Chuyển sang AOP method validation | Bỏ class-level @Validated để dùng built-in validation |
| Chỉ xử lý WebExchangeBindException | Bỏ sót method validation exception | Xử lý cả HandlerMethodValidationException |
| Ghi lỗi validation quá chi tiết cho client | Có thể lộ cấu trúc nội bộ | Trả mã lỗi và field message đã lọc |

## 13. Checklist thiết kế cấu hình

Trước khi triển khai, kiểm tra:

1. API nhận những Content-Type nào và trả những media type nào?
2. Codec mặc định trên classpath đã đủ chưa?
3. Có cần custom Encoder, Decoder, HttpMessageReader hoặc HttpMessageWriter không?
4. Custom codec có nhận đúng giới hạn buffer và logging policy không?
5. maxInMemorySize có phù hợp với payload và concurrency không?
6. Server codecs và WebClient codecs đã được cấu hình riêng đúng nhu cầu chưa?
7. Query/path/header có kiểu domain cần Converter không?
8. Dữ liệu ngày/số có cần Formatter theo Locale không?
9. Format của browser input type=date có phải ISO không?
10. Bean Validation đã có provider và starter dependency chưa?
11. Object lồng nhau đã đánh dấu @Valid chưa?
12. Cross-field/business rules có cần Spring Validator riêng không?
13. Có xử lý WebExchangeBindException và HandlerMethodValidationException không?
14. Controller có tránh class-level @Validated nếu dùng built-in method validation không?
15. Test có bao phủ codec, conversion, formatting, object validation và method validation không?

## 14. Ghi nhớ

- Codec xử lý byte stream và object qua Encoder, Decoder, HttpMessageReader và HttpMessageWriter.
- Content-Type chọn reader cho request; Accept tham gia chọn writer cho response.
- ServerCodecConfigurer cấu hình codec phía server; ClientCodecConfigurer cấu hình codec của WebClient.
- WebFluxConfigurer.configureHttpMessageCodecs tùy chỉnh codec mặc định hoặc thêm custom codec.
- registerWithDefaultConfig giúp custom codec nhận các thiết lập mặc định như maxInMemorySize và logging.
- Spring Boot 3.5 dùng spring.http.codecs.max-in-memory-size cho giới hạn aggregate codec.
- Converter chuyển kiểu tổng quát; Formatter parse/print theo Locale.
- WebFluxConfigurer.addFormatters đăng ký Converter và Formatter toàn cục cho web binding.
- @InitBinder tùy chỉnh WebDataBinder và validator theo controller/model attribute.
- Bean Validation dùng annotation như @NotBlank, @Size, @Positive và @Valid.
- Spring Validator phù hợp với quy tắc liên quan nhiều field hoặc nghiệp vụ đặc thù.
- WebExchangeBindException thường đại diện validation một command object; HandlerMethodValidationException đại diện built-in method validation.
- Với Spring Framework 6.1+, tránh class-level @Validated trên controller nếu muốn dùng built-in method validation.
- Giới hạn bộ nhớ codec không phải giới hạn tổng request; dữ liệu lớn cần streaming và giới hạn ở các tầng phù hợp.

**Tài liệu chính thức:**
- [Spring Framework 6.2 — WebFlux Config: codecs, conversion, formatting and validation](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html)
- [Spring Framework 6.2 — Reactive Core: HTTP message readers and writers](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html)
- [Spring Framework 6.2 — DataBinder and @InitBinder](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-initbinder.html)
- [Spring Framework 6.2 — WebFlux Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-validation.html)
- [Spring Framework 6.2 — Java Bean Validation](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html)
- [Spring Boot 3.5 — Common Application Properties: spring.http.codecs](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html)
- [Spring Framework 6.2 — WebFluxConfigurer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/web/reactive/config/WebFluxConfigurer.html)
- [Spring Framework 6.2 — Jackson2JsonDecoder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.5/javadoc-api/org/springframework/http/codec/json/Jackson2JsonDecoder.html)
- [Spring Framework 6.2 — Jackson2JsonEncoder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.5/javadoc-api/org/springframework/http/codec/json/Jackson2JsonEncoder.html)
- [Spring Framework — Formatter SPI](https://docs.spring.io/spring-framework/reference/6.2/core/validation/format.html)
