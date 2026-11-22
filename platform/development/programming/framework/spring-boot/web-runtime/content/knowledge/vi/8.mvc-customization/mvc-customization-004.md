# Bổ sung formatter, converter và argument resolver trong Spring Boot MVC

## 1. Mục tiêu và phạm vi

Spring MVC xử lý rất nhiều công việc trước khi gọi một controller method: chọn route, lấy path variable/query parameter/header, chuyển chuỗi HTTP thành kiểu Java, đọc request body và tạo response body. Các mặc định của Spring Boot đáp ứng trường hợp phổ biến; khi có kiểu dữ liệu miền nghiệp vụ hoặc cách truyền dữ liệu đặc thù, ta có thể bổ sung **Formatter**, **Converter** và **HandlerMethodArgumentResolver**. Một loại converter khác, **HttpMessageConverter**, xử lý nội dung HTTP body và cần được phân biệt rõ.

Sau bài học, bạn có thể:

- Giải thích vai trò của Formatter, Converter<S,T>, HttpMessageConverter<T> và HandlerMethodArgumentResolver.
- Chọn đúng điểm mở rộng thay vì tự parse chuỗi trong mọi controller.
- Đăng ký custom formatter/converter và argument resolver bằng WebMvcConfigurer mà vẫn giữ auto-configuration MVC của Spring Boot.
- Bổ sung message converter cho định dạng body riêng, đồng thời giữ JSON, String và các converter mặc định.
- Viết ví dụ Java 17+ chạy được trên Spring Boot 3.3.x, kiểm thử bằng MockMvc và phân biệt lỗi binding, lỗi media type, lỗi thiếu dữ liệu.
- Nhận biết các rủi ro về locale, giới hạn body, thứ tự converter, bảo mật header và việc vô tình ghi đè mặc định của framework.

**Phạm vi:** Spring MVC trên Servlet web stack, điển hình khi dùng spring-boot-starter-web. Spring WebFlux có pipeline và API mở rộng reactive khác; không tự suy ra rằng WebMvcConfigurer hoặc HandlerMethodArgumentResolver của MVC dùng trực tiếp trong WebFlux.

## 2. Một request đi qua những bước nào?

Với một endpoint ví dụ:

~~~http
GET /api/orders/sku-0123?period=11%2F2026 HTTP/1.1
Host: localhost:8080
X-Tenant-Id: store-a
Accept: application/json
~~~

Dòng xử lý tổng quát:

~~~text
HTTP client
   |
   v
Servlet container (ví dụ Tomcat)
   |
   v
Servlet Filters
   |
   v
DispatcherServlet
   |
   +--> HandlerMapping: tìm controller method
   |
   +--> HandlerAdapter: chuẩn bị tham số
   |       |
   |       +--> Converter: "sku-0123" -> ProductCode
   |       |
   |       +--> Formatter: "11/2026" -> BillingPeriod
   |       |
   |       +--> ArgumentResolver: X-Tenant-Id -> TenantContext
   |       |
   |       +--> HttpMessageConverter khi có @RequestBody
   |
   +--> Controller / Service
   |
   +--> HttpMessageConverter cho @ResponseBody
   |
   v
HTTP response
~~~

**Ba nhiệm vụ khác nhau:**

1. Chuyển đổi một giá trị đơn lẻ từ kiểu nguồn sang kiểu đích: Converter.
2. Phân tích và hiển thị kiểu dữ liệu theo định dạng hoặc locale: Formatter.
3. Quyết định giá trị của cả một tham số controller dựa trên request/context: HandlerMethodArgumentResolver.

Đối với request/response body, dùng HttpMessageConverter; loại này khác Spring Core Converter<String, T>.

## 3. Bảng lựa chọn nhanh

| Nhu cầu | Công cụ phù hợp | Ví dụ |
| --- | --- | --- |
| Chuyển path/query text thành value object | Converter<S,T> | "sku-0123" -> ProductCode("SKU-0123") |
| Phân tích và in định dạng có thể phụ thuộc locale | Formatter<T> | "11/2026" <-> BillingPeriod |
| Tạo tham số controller từ header hoặc request context | HandlerMethodArgumentResolver | @Tenant TenantContext |
| Đọc/ghi toàn bộ HTTP body theo media type | HttpMessageConverter<T> | text/plain <-> PlainNote |
| Kiểm tra tính hợp lệ của object đầu vào | Jakarta Bean Validation / Validator | @Valid, @NotBlank |
| Tùy chỉnh JSON field, tên property hoặc date serialization | Jackson configuration / module | JSON từ Java object |
| Tiền xử lý trước controller | Servlet Filter / HandlerInterceptor | trace ID, cross-cutting logic |
| Đọc file cấu hình vào Bean | @ConfigurationProperties | application.yml -> AppSettings |

Một công cụ có thể cùng xuất hiện trong một request nhưng không thay thế cơ chế của công cụ khác. Ví dụ @RequestBody nhận JSON là nhiệm vụ của message converter, trong khi @RequestParam ProductCode thường sử dụng conversion service. Header nhận diện một tenant có thể dùng @RequestHeader String ở trường hợp đơn giản; custom resolver chỉ có ích khi cần đối tượng và quy tắc dùng chung.

## 4. Converter<S,T>: chuyển một giá trị sang kiểu Java

Converter nằm trong gói org.springframework.core.convert.converter. Hợp đồng đơn giản:

~~~java
public interface Converter<S, T> {
    T convert(S source);
}
~~~

Converter chuyển một object nguồn thành một object đích; phương thức convert không nhận Locale. Một ứng dụng có thể dùng converter để ánh xạ ID, enum, mã nghiệp vụ hoặc format chuỗi chuẩn hóa.

Ví dụ kiểu mã sản phẩm ProductCode luôn được chuẩn hóa thành SKU-xxxx:

~~~java
record ProductCode(String value) {
}

final class ProductCodeConverter
        implements Converter<String, ProductCode> {

    @Override
    public ProductCode convert(String source) {
        String normalized = source.trim().toUpperCase(Locale.ROOT);
        if (!normalized.matches("SKU-[0-9]{4}")) {
            throw new IllegalArgumentException(
                    "Product code must match SKU-0000");
        }
        return new ProductCode(normalized);
    }
}
~~~

Đoạn code này cần import Converter và Locale; nó sẽ được đặt trong project chạy được ở phần 9. Khi converter được đăng ký vào MVC conversion service, method có thể nhận trực tiếp:

~~~java
@GetMapping("/api/products/{code}")
public String find(@PathVariable ProductCode code) {
    return code.value();
}
~~~

Với GET /api/products/sku-0123, Spring MVC có thể chuyển chuỗi path variable thành ProductCode("SKU-0123") trước khi gọi controller. Nếu dữ liệu không hợp lệ, lỗi chuyển đổi thường được xử lý thành HTTP 400 thay vì gọi controller với object sai.

**Đừng lạm dụng converter:** Nếu chỉ có một endpoint cần kiểm tra chuỗi đơn giản, @Pattern hoặc validator trên DTO có thể đủ. Chỉ tạo Converter khi kiểu domain có ngữ nghĩa rõ, được dùng ở nhiều điểm hoặc khi muốn ranh giới chuyển đổi tập trung.

### 4.1. Converter và GenericConverter

Converter<S,T> mô tả một cặp source-target tĩnh. Khi conversion phụ thuộc generic type, annotation hoặc cần hỗ trợ nhiều cặp kiểu một cách có điều kiện, Spring còn có GenericConverter và ConditionalGenericConverter. Chúng linh hoạt hơn nhưng phức tạp hơn. Với một ID/value object thông thường, Converter<S,T> dễ đọc và dễ kiểm thử nhất.

### 4.2. Có phải mọi chuyển đổi đều chạy cho JSON?

Không. Converter đăng ký trong MVC ConversionService chủ yếu phục vụ binding dữ liệu như query, path, form và model property. JSON request/response thường do Jackson thông qua HttpMessageConverter xử lý. Một Converter<String,ProductCode> không mặc nhiên điều khiển cách Jackson deserialize ProductCode từ JSON. Muốn thay đổi JSON, cần cấu hình Jackson hoặc cơ chế message conversion thích hợp.

## 5. Formatter<T>: parse và print theo ngữ cảnh định dạng

Formatter nằm trong org.springframework.format. Hợp đồng gồm hai chiều:

~~~java
public interface Formatter<T> extends Printer<T>, Parser<T> {
}
~~~

Các phương thức cốt lõi:

- parse(String text, Locale locale): chuyển text thành đối tượng Java.
- print(T object, Locale locale): xuất biểu diễn text.
  
Formatter thích hợp cho ngày tháng, số tiền, tỷ lệ và kiểu nghiệp vụ có quy ước trình bày; Locale cho phép biểu diễn khác nhau theo ngôn ngữ/vùng. Không phải formatter nào cũng phải dùng Locale: nếu hợp đồng API quy định một format cố định, có thể cố tình không phụ thuộc Locale và cần ghi rõ điều đó.

Ví dụ BillingPeriod nhận văn bản MM/yyyy, nhưng lưu bằng YearMonth:

~~~java
record BillingPeriod(YearMonth value) {
}

final class BillingPeriodFormatter
        implements Formatter<BillingPeriod> {

    private static final DateTimeFormatter FORMAT =
            DateTimeFormatter.ofPattern("MM/uuuu")
                    .withResolverStyle(ResolverStyle.STRICT);

    @Override
    public BillingPeriod parse(String text, Locale locale)
            throws ParseException {
        try {
            return new BillingPeriod(YearMonth.parse(text, FORMAT));
        } catch (DateTimeParseException ex) {
            ParseException failure = new ParseException(
                    "Expected billing period MM/yyyy", 0);
            failure.initCause(ex);
            throw failure;
        }
    }

    @Override
    public String print(BillingPeriod object, Locale locale) {
        return FORMAT.format(object.value());
    }
}
~~~

Ví dụ này có chủ đích dùng định dạng cố định MM/yyyy để hợp đồng API nhất quán. Nếu xây dựng form theo ngôn ngữ người dùng, có thể chọn DateTimeFormatter/NumberFormat theo Locale và kiểm thử các locale được hỗ trợ.

Sau khi đăng ký formatter, một method có thể nhận:

~~~java
@GetMapping("/api/reports")
public String report(@RequestParam BillingPeriod period) {
    return period.value().toString();
}
~~~

Request /api/reports?period=11%2F2026 chuyển thành BillingPeriod(YearMonth.of(2026, 11)). Controller trả chuỗi 2026-11.

**Chú ý về print:** Formatter#print được conversion/formatting service sử dụng khi cần chuyển object thành chuỗi, ví dụ form binding hoặc formatting. Trả một record qua @ResponseBody JSON không có nghĩa Jackson sẽ gọi Formatter#print; JSON serialization có cơ chế riêng.

### 5.1. Khi nào ưu tiên công cụ có sẵn?

Trước khi viết Formatter mới, thử các khả năng sẵn có:

- @DateTimeFormat trên parameter hoặc field ngày/giờ.
- @NumberFormat cho số.
- Conversion mặc định với enum, primitive, UUID và các kiểu được framework hỗ trợ.
- @JsonFormat hoặc Jackson config nếu vấn đề thực sự thuộc JSON body.

Ví dụ một endpoint chỉ cần LocalDate:

~~~java
@GetMapping("/api/by-date")
public String byDate(
        @RequestParam
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
        LocalDate date) {
    return date.toString();
}
~~~

Đây là code minh họa trong controller; nó cần import DateTimeFormat và LocalDate. Không nên viết Formatter<LocalDate> toàn cục chỉ để một endpoint dùng ISO date, vì formatter toàn cục có thể thay đổi cách parse ngày của nhiều endpoint khác.

## 6. HandlerMethodArgumentResolver: tạo tham số controller

Spring MVC có sẵn các resolver cho @PathVariable, @RequestParam, @RequestHeader, @RequestBody, HttpServletRequest, Principal và nhiều kiểu khác. Khi muốn thêm một kiểu tham số đặc biệt, có thể triển khai HandlerMethodArgumentResolver.

Hai phương thức chính:

~~~java
boolean supportsParameter(MethodParameter parameter);

Object resolveArgument(
        MethodParameter parameter,
        ModelAndViewContainer mavContainer,
        NativeWebRequest webRequest,
        WebDataBinderFactory binderFactory) throws Exception;
~~~

supportsParameter quyết định resolver có chịu trách nhiệm cho parameter nào; resolveArgument thực sự lấy dữ liệu và tạo đối tượng để controller sử dụng.

Ví dụ controller muốn nhận:

~~~java
@GetMapping("/api/orders")
public String listOrders(@Tenant TenantContext tenant) {
    return tenant.id();
}
~~~

Ở đây @Tenant là annotation của ứng dụng. Resolver sẽ đọc X-Tenant-Id từ header và tạo TenantContext. Controller không phải tự lặp lại logic đọc header.

Một resolver tốt nên:

- Chỉ nhận đúng annotation/kiểu parameter mình sở hữu; không bắt quá rộng các tham số String hoặc Object.
- Xử lý rõ khi dữ liệu thiếu, lỗi định dạng hoặc không được phép.
- Không giữ trạng thái mutable theo request trong field singleton.
- Không đọc cả request body tùy tiện khi @RequestBody đã xử lý bằng message converter.
- Có test cho tình huống có/không có header và header không hợp lệ.

**Cảnh báo bảo mật:** X-Tenant-Id trong ví dụ chỉ để học cách truyền dữ liệu. Header do client gửi không chứng minh tenant identity hoặc quyền truy cập. Ở ứng dụng đa tenant thật, resolver phải dựa trên security principal/claims đã xác thực và cơ chế phân quyền được kiểm chứng, không tin header không xác thực để quyết định quyền truy cập dữ liệu.

### 6.1. Vì sao không dùng Converter cho mọi parameter?

Converter xử lý *một giá trị* S -> T mà framework đã đọc được. Resolver có thể quyết định nguồn của parameter: header, cookie, request attribute, session, principal hoặc ngữ cảnh đa trường. Nó cũng có thể tạo một object phức tạp từ nhiều thành phần.

Nếu muốn @RequestHeader("X-Tenant-Id") TenantContext, có thể dùng Converter<String,TenantContext>. Nếu muốn cú pháp riêng @Tenant và lấy dữ liệu qua security context/metadata khác, HandlerMethodArgumentResolver phù hợp hơn.

## 7. HttpMessageConverter<T>: đọc và ghi HTTP body

Có hai loại converter dễ bị nhầm:

- Spring Core Converter<S,T>: chuyển giá trị Java theo conversion service.
- Spring Web HttpMessageConverter<T>: đọc/ghi *toàn bộ HTTP message body* theo content type, accept header và kiểu Java.

Khi controller dùng @RequestBody, Spring MVC chọn HttpMessageConverter có thể đọc Java type cần thiết với request Content-Type. Khi controller trả @ResponseBody hoặc @RestController, framework tìm converter có thể ghi return value theo media type phù hợp với Accept và cấu hình produces.

Ví dụ các converter mặc định thường gặp:

- StringHttpMessageConverter cho String/plain text.
- MappingJackson2HttpMessageConverter (trong Spring Framework 6.x với Jackson được cấu hình) cho JSON.
- ByteArrayHttpMessageConverter cho byte[].
- ResourceHttpMessageConverter cho Resource/streaming thích hợp.

**Content-Type** cho biết body request được gửi dưới định dạng gì; **Accept** nêu định dạng response mà client muốn nhận. Nếu request body không được hỗ trợ, có thể nhận HTTP 415; nếu không tìm được định dạng response chấp nhận được, có thể nhận HTTP 406. Việc binding/parse body thất bại thường dẫn tới HTTP 400, tùy ngoại lệ và exception handler của ứng dụng.

Thêm message converter cho format custom khi đã có hợp đồng nội dung riêng. Nếu chỉ cần đổi tên JSON field hoặc cách serialize một object, nên dùng Jackson annotation/serializer/configuration trước khi tự viết converter HTTP.

## 8. Tích hợp vào Spring Boot bằng WebMvcConfigurer

Spring Boot MVC auto-configuration cung cấp các converter, formatter và argument resolver mặc định. Cách mở rộng thông dụng là tạo một @Configuration class implements WebMvcConfigurer:

~~~java
@Configuration(proxyBeanMethods = false)
class MvcCustomizationConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new ProductCodeConverter());
        registry.addFormatter(new BillingPeriodFormatter());
    }

    @Override
    public void addArgumentResolvers(
            List<HandlerMethodArgumentResolver> resolvers) {
        resolvers.add(new TenantArgumentResolver());
    }

    @Override
    public void extendMessageConverters(
            List<HttpMessageConverter<?>> converters) {
        converters.add(0, new PlainNoteMessageConverter());
    }
}
~~~

Đây là code minh họa; phần 9 chứa project hoàn chỉnh và import tương ứng.

Ý nghĩa:

- addFormatters: bổ sung Converter và Formatter vào MVC FormattingConversionService.
- addArgumentResolvers: thêm handler method argument resolver cho các kiểu/annotation đặc thù; những built-in resolver khác vẫn tồn tại.
- extendMessageConverters: mở rộng danh sách converter body sau khi danh sách mặc định được chuẩn bị; thứ tự danh sách có thể ảnh hưởng chọn converter.

**Không thêm @EnableWebMvc** vào một ứng dụng Spring Boot chỉ vì muốn đăng ký converter hoặc resolver. @EnableWebMvc chuyển sang chế độ tự kiểm soát MVC nhiều hơn và làm Boot MVC auto-configuration không còn áp dụng theo cách thông thường. Điều này dễ gây mất cấu hình static resources, formatter, converter hoặc các mặc định khác mà dự án đang sử dụng.

### 8.1. configureMessageConverters và extendMessageConverters

Trong cấu hình Spring MVC thuần, việc thêm converter qua configureMessageConverters có thể thay đổi cơ chế đăng ký mặc định. Spring Boot có các điều chỉnh riêng và cũng tự thu thập HttpMessageConverter beans. Với mục tiêu *bổ sung* converter mà giữ những converter sẵn có, extendMessageConverters là cách dễ hiểu.

Không tự clear() danh sách mặc định hay thay thế toàn bộ converter chỉ để thêm text/plain. Khi thêm converter có supports() quá rộng hoặc media type quá rộng, nó có thể lấy mất trách nhiệm của Jackson/String converters, gây thay đổi response hiện hữu.

### 8.2. Có thể dùng Bean riêng không?

Spring Boot hỗ trợ đóng góp Converter, GenericConverter, Formatter và HttpMessageConverter bằng Bean thích hợp. Dù dùng Bean hoặc WebMvcConfigurer, phải hiểu phạm vi đăng ký: MVC conversion service phục vụ web binding, còn ApplicationConversionService của Boot cho cấu hình application.properties có đường đăng ký riêng. Việc thêm converter vào một conversion service không tự động bảo đảm tất cả service khác cùng dùng converter đó.

## 9. Ví dụ chạy được: Converter, Formatter, Resolver và MessageConverter

Ví dụ này dùng **Spring Boot 3.3.x, Java 17+**, Spring MVC và embedded Tomcat mặc định. Nó minh họa bốn điểm mở rộng bằng một project nhỏ, không phụ thuộc database.

Các endpoint:

- GET /api/orders/{code}?period=MM/yyyy với header X-Tenant-Id: nhận ProductCode, BillingPeriod và TenantContext.
- POST /api/echo với body text/plain: đọc body thành PlainNote rồi ghi PlainNote ra text/plain.

### 9.1. Cấu trúc thư mục

~~~text
mvc-extensions-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        example/
          mvc/
            MvcExtensionsApplication.java
    test/
      java/
        example/
          mvc/
            MvcExtensionsApplicationTests.java
~~~

Trong ví dụ học tập này, nhiều class package-private nằm chung một file Java để dễ quan sát toàn bộ pipeline. Ở dự án thực, mỗi class có trách nhiệm riêng nên được tách file để dễ bảo trì.

### 9.2. Tệp settings.gradle

~~~groovy
rootProject.name = 'mvc-extensions-demo'
~~~

### 9.3. Tệp build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Cần Gradle Wrapper có phiên bản tương thích với Spring Boot 3.3.x và JDK 17 trở lên. Phiên bản plugin trong ví dụ cố định để tái hiện; trong module thực tế hãy theo bộ phiên bản do build của dự án quản lý.

### 9.4. Tệp MvcExtensionsApplication.java

~~~java
package example.mvc;

import java.io.IOException;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.text.ParseException;
import java.time.YearMonth;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.List;
import java.util.Locale;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.MethodParameter;
import org.springframework.core.convert.converter.Converter;
import org.springframework.format.Formatter;
import org.springframework.format.FormatterRegistry;
import org.springframework.http.HttpInputMessage;
import org.springframework.http.HttpOutputMessage;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.converter.AbstractHttpMessageConverter;
import org.springframework.http.converter.HttpMessageConverter;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.support.WebDataBinderFactory;
import org.springframework.web.context.request.NativeWebRequest;
import org.springframework.web.method.support.HandlerMethodArgumentResolver;
import org.springframework.web.method.support.ModelAndViewContainer;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@SpringBootApplication
public class MvcExtensionsApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcExtensionsApplication.class, args);
    }
}

record ProductCode(String value) {
}

record BillingPeriod(YearMonth value) {
}

record TenantContext(String id) {
}

record PlainNote(String text) {
}

@Target(ElementType.PARAMETER)
@Retention(RetentionPolicy.RUNTIME)
@interface Tenant {
}

final class ProductCodeConverter
        implements Converter<String, ProductCode> {

    @Override
    public ProductCode convert(String source) {
        String normalized = source.trim().toUpperCase(Locale.ROOT);
        if (!normalized.matches("SKU-[0-9]{4}")) {
            throw new IllegalArgumentException(
                    "Product code must match SKU-0000");
        }
        return new ProductCode(normalized);
    }
}

final class BillingPeriodFormatter implements Formatter<BillingPeriod> {

    private static final DateTimeFormatter FORMAT =
            DateTimeFormatter.ofPattern("MM/uuuu")
                    .withResolverStyle(ResolverStyle.STRICT);

    @Override
    public BillingPeriod parse(String text, Locale locale)
            throws ParseException {
        try {
            return new BillingPeriod(YearMonth.parse(text, FORMAT));
        } catch (DateTimeParseException ex) {
            ParseException failure = new ParseException(
                    "Expected billing period MM/yyyy", 0);
            failure.initCause(ex);
            throw failure;
        }
    }

    @Override
    public String print(BillingPeriod object, Locale locale) {
        return FORMAT.format(object.value());
    }
}

final class TenantArgumentResolver
        implements HandlerMethodArgumentResolver {

    @Override
    public boolean supportsParameter(MethodParameter parameter) {
        return parameter.hasParameterAnnotation(Tenant.class)
                && parameter.getParameterType() == TenantContext.class;
    }

    @Override
    public Object resolveArgument(
            MethodParameter parameter,
            ModelAndViewContainer mavContainer,
            NativeWebRequest request,
            WebDataBinderFactory binderFactory) {

        String value = request.getHeader("X-Tenant-Id");
        if (value == null
                || !value.matches("[a-z][a-z0-9-]{0,31}")) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "X-Tenant-Id is missing or invalid");
        }
        return new TenantContext(value);
    }
}

final class PlainNoteMessageConverter
        extends AbstractHttpMessageConverter<PlainNote> {

    private static final int MAX_BYTES = 4096;

    PlainNoteMessageConverter() {
        super(new MediaType("text", "plain", StandardCharsets.UTF_8));
    }

    @Override
    protected boolean supports(Class<?> clazz) {
        return PlainNote.class.isAssignableFrom(clazz);
    }

    @Override
    protected PlainNote readInternal(
            Class<? extends PlainNote> clazz,
            HttpInputMessage input) throws IOException {

        byte[] bytes = input.getBody().readNBytes(MAX_BYTES + 1);
        if (bytes.length > MAX_BYTES) {
            throw new HttpMessageNotReadableException(
                    "Plain text body exceeds 4096 bytes", input);
        }

        MediaType contentType = input.getHeaders().getContentType();
        Charset charset = contentType != null
                && contentType.getCharset() != null
                ? contentType.getCharset()
                : StandardCharsets.UTF_8;

        return new PlainNote(new String(bytes, charset));
    }

    @Override
    protected void writeInternal(
            PlainNote note, HttpOutputMessage output) throws IOException {
        output.getBody().write(
                note.text().getBytes(StandardCharsets.UTF_8));
    }
}

@Configuration(proxyBeanMethods = false)
class MvcCustomizationConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new ProductCodeConverter());
        registry.addFormatter(new BillingPeriodFormatter());
    }

    @Override
    public void addArgumentResolvers(
            List<HandlerMethodArgumentResolver> resolvers) {
        resolvers.add(new TenantArgumentResolver());
    }

    @Override
    public void extendMessageConverters(
            List<HttpMessageConverter<?>> converters) {
        converters.add(0, new PlainNoteMessageConverter());
    }
}

@RestController
class ExampleController {

    @GetMapping("/api/orders/{code}")
    public Map<String, String> order(
            @PathVariable("code") ProductCode code,
            @RequestParam("period") BillingPeriod period,
            @Tenant TenantContext tenant) {

        return Map.of(
                "productCode", code.value(),
                "period", period.value().toString(),
                "tenant", tenant.id());
    }

    @PostMapping(
            path = "/api/echo",
            consumes = MediaType.TEXT_PLAIN_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    public PlainNote echo(@RequestBody PlainNote input) {
        return input;
    }
}
~~~

Phần main là public class duy nhất và trùng tên file MvcExtensionsApplication.java. Các class/record/annotation còn lại có phạm vi package nên có thể đặt cùng file Java trong ví dụ này.

**Bốn điểm nối trong runtime:**

1. Khi parse {code}, ProductCodeConverter.convert chuẩn hóa chuỗi thành ProductCode.
2. Khi parse period, BillingPeriodFormatter.parse tạo BillingPeriod.
3. Với parameter có @Tenant, TenantArgumentResolver lấy X-Tenant-Id và tạo TenantContext.
4. Với /api/echo, PlainNoteMessageConverter.readInternal đọc body text/plain thành PlainNote; writeInternal biến PlainNote thành response text/plain.

Ở /api/orders, controller trả Map nên JSON vẫn do converter mặc định đảm nhiệm. Vì extendMessageConverters chỉ thêm converter hỗ trợ PlainNote, các API JSON hiện có vẫn có thể sử dụng Jackson.

### 9.5. Chạy ứng dụng

Trên Linux/macOS:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Từ terminal khác, gọi endpoint:

~~~bash
curl -i "http://localhost:8080/api/orders/sku-0123?period=11%2F2026" -H "X-Tenant-Id: store-a"
~~~

Nếu server khởi động thành công trên port mặc định và không có cấu hình khác ghi đè, status mong đợi là HTTP 200, response body JSON chứa ba giá trị:

~~~json
{"productCode":"SKU-0123","period":"2026-11","tenant":"store-a"}
~~~

Thứ tự các key JSON không được bảo đảm. Điều quan trọng là productCode được chuẩn hóa thành SKU-0123, period thành 2026-11 và tenant lấy từ header.

Gửi text/plain:

~~~bash
curl -i -X POST "http://localhost:8080/api/echo" -H "Content-Type: text/plain; charset=UTF-8" -H "Accept: text/plain" --data-binary "Xin chao"
~~~

Status mong đợi: HTTP 200. Response body:

~~~text
Xin chao
~~~

Ở endpoint này, dữ liệu gửi lên được giới hạn 4096 byte trong custom converter. Đây chỉ là giới hạn đơn giản phục vụ minh họa; production cần chính sách giới hạn request body ở các tầng phù hợp và bộ xử lý charset/validation đầy đủ.

### 9.6. Thử các lỗi hợp lệ

- Bỏ X-Tenant-Id: resolver trả HTTP 400 vì thiếu header bắt buộc.
- Dùng X-Tenant-Id có ký tự nằm ngoài pattern cho phép: HTTP 400.
- Gọi /api/orders/abc?period=11%2F2026 với header hợp lệ: ProductCodeConverter không tạo được ProductCode, Spring MVC thường trả HTTP 400.
- Gọi period=13%2F2026: formatter từ chối tháng 13, thường trả HTTP 400.
- POST /api/echo với Content-Type: application/json trong khi mapping yêu cầu text/plain: HTTP 415.
- Gửi Accept: application/json cho /api/echo vốn khai báo produces=text/plain: HTTP 406 nếu không có định dạng phản hồi giao được.
- Gửi text/plain hơn 4096 byte: custom message converter từ chối đọc body, Spring MVC mặc định xử lý thành HTTP 400.

Mã status chính xác có thể được thay đổi bởi global exception handler hoặc security filter chain trong dự án thực. Khi gặp lỗi, xem status, content type, exception và log có liên quan; không chỉ đoán dựa trên controller.

## 10. Kiểm thử bằng MockMvc

Phần này kiểm thử bốn kiểu tùy chỉnh mà không cần mở một port TCP thực. MockMvc đi qua lớp Spring MVC request mapping, argument resolution và message conversion theo cấu hình test context.

Tệp src/test/java/example/mvc/MvcExtensionsApplicationTests.java:

~~~java
package example.mvc;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MvcExtensionsApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void converterFormatterAndResolverWorkTogether() throws Exception {
        mvc.perform(get("/api/orders/sku-0123")
                        .param("period", "11/2026")
                        .header("X-Tenant-Id", "store-a"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.productCode").value("SKU-0123"))
                .andExpect(jsonPath("$.period").value("2026-11"))
                .andExpect(jsonPath("$.tenant").value("store-a"));
    }

    @Test
    void plainNoteMessageConverterReadsAndWrites() throws Exception {
        mvc.perform(post("/api/echo")
                        .contentType(MediaType.TEXT_PLAIN)
                        .accept(MediaType.TEXT_PLAIN)
                        .content("Xin chao"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.TEXT_PLAIN))
                .andExpect(content().string("Xin chao"));
    }

    @Test
    void invalidProductCodeReturnsBadRequest() throws Exception {
        mvc.perform(get("/api/orders/invalid")
                        .param("period", "11/2026")
                        .header("X-Tenant-Id", "store-a"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void invalidPeriodReturnsBadRequest() throws Exception {
        mvc.perform(get("/api/orders/sku-0123")
                        .param("period", "13/2026")
                        .header("X-Tenant-Id", "store-a"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void missingTenantHeaderReturnsBadRequest() throws Exception {
        mvc.perform(get("/api/orders/sku-0123")
                        .param("period", "11/2026"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void wrongContentTypeReturnsUnsupportedMediaType()
            throws Exception {
        mvc.perform(post("/api/echo")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"text\":\"abc\"}"))
                .andExpect(status().isUnsupportedMediaType());
    }
}
~~~

Chạy test:

~~~bash
./gradlew test
~~~

Các test xác minh status, JSON field, text body và lỗi, thay vì chỉ kiểm tra rằng context khởi tạo. Với thay đổi converter/resolver thật, hãy bổ sung test cho những endpoint cũ để chắc chắn cấu hình mới không phá vỡ binding, JSON hoặc API contract đã có.

### 10.1. @WebMvcTest và @SpringBootTest khác gì?

- @WebMvcTest phù hợp khi chỉ muốn một phần MVC, nhanh hơn khi chỉ cần controller/web configuration. Tuy nhiên custom config/converter/resolver và dependency cần được đưa vào slice test đầy đủ; nếu không test có thể thất bại vì thiếu Bean hoặc báo sai hành vi.
- @SpringBootTest + @AutoConfigureMockMvc (như ví dụ) tạo application context rộng hơn nhưng không cần mở port thực, phù hợp xác minh sự kết hợp của các tùy chỉnh.
- @SpringBootTest(webEnvironment = RANDOM_PORT) dùng embedded server thật để kiểm tra cả HTTP connector, filter chain và tích hợp network; thích hợp cho integration test sau cùng.

Không nên chỉ dùng unit test gọi trực tiếp ExampleController.order(...) để kết luận formatter hoặc argument resolver hoạt động, bởi trực tiếp gọi method đã bỏ qua MVC binding pipeline.

## 11. Đọc kỹ cách Spring MVC chọn một extension

### 11.1. Khi nào Converter/Formatter được gọi?

Các resolver built-in, chẳng hạn xử lý @PathVariable hoặc @RequestParam, trước tiên tìm giá trị thô trong request rồi cần chuyển kiểu đích. WebDataBinder và ConversionService/FormattingConversionService có thể thực hiện bước này. Converter hoặc Formatter được chọn khi có cặp source-target phù hợp đã được đăng ký.

Điều đó có nghĩa một @RequestParam ProductCode vẫn do built-in request-parameter resolver nhận, nhưng giá trị String bên trong được chuyển nhờ ProductCodeConverter. Không cần viết HandlerMethodArgumentResolver chỉ để parse path variable thành một value object đơn giản.

Nếu có nhiều converter/formatter trùng cặp kiểu, thứ tự và cách đăng ký có thể dẫn tới hành vi khó dự đoán. Tránh đăng ký nhiều chiến lược xung đột cho cùng một type toàn cục; dùng annotation hoặc binder cục bộ khi định dạng cần thay đổi theo endpoint.

### 11.2. Khi nào HandlerMethodArgumentResolver được gọi?

RequestMappingHandlerAdapter có danh sách các resolver. Framework tìm resolver đầu tiên mà supportsParameter(...) trả true cho controller parameter rồi gọi resolveArgument(...).

Danh sách custom bổ sung qua WebMvcConfigurer.addArgumentResolvers được dùng cùng các built-in resolver. Các built-in cho annotation chuẩn như @RequestParam/@PathVariable vẫn được ưu tiên theo cách framework sắp xếp; custom resolver phù hợp nhất khi dùng annotation riêng và kiểu riêng của ứng dụng. Đừng cố ghi đè cách xử lý @RequestBody hoặc @RequestParam bằng custom resolver chung chung.

Nếu buộc phải thay đổi built-in argument resolution, cần hiểu sâu RequestMappingHandlerAdapter và cấu hình tương ứng. Đây là thay đổi có tác động rộng, phải kiểm thử toàn bộ API liên quan.

### 11.3. Khi nào HttpMessageConverter được gọi?

RequestResponseBodyMethodProcessor và các component MVC liên quan dùng HttpMessageConverters để đọc @RequestBody và ghi @ResponseBody. Chúng cân nhắc Java type, Content-Type, Accept, consumes/produces và thứ tự converter đã đăng ký.

Một converter tự nhận hỗ trợ Object.class và tất cả media type có thể chiếm quyền lựa chọn trước Jackson, dẫn đến output sai. PlainNoteMessageConverter ở ví dụ chỉ hỗ trợ PlainNote và text/plain; vì thế phạm vi tác động có thể kiểm soát.

## 12. Formatter, locale và tính nhất quán dữ liệu

Sự khác biệt giữa parse và print quan trọng khi làm form nhập liệu:

- Parse: "11/2026" -> BillingPeriod(YearMonth.of(2026,11)).
- Print: BillingPeriod(...) -> "11/2026".

Hai chiều cần tương thích để dữ liệu sau khi hiển thị và gửi lại không đổi ý nghĩa. Nếu formatter phụ thuộc locale, phải kiểm tra cả hai chiều dưới những locale mà ứng dụng hỗ trợ.

Ví dụ số thập phân "1,234" có thể mang ý nghĩa khác nhau giữa các locale. Không dùng NumberFormat mặc định của máy server cho một API public nếu hợp đồng API yêu cầu format cố định. Nếu API yêu cầu ISO date hoặc decimal dùng dấu chấm, ghi rõ hợp đồng và kiểm tra input thay vì phó mặc cho locale ngẫu nhiên.

Một custom Formatter<LocalDate> toàn cục có thể thay đổi hàng loạt endpoint và form. Khi chỉ một field có format đặc biệt, cân nhắc @DateTimeFormat hoặc @InitBinder của controller thay vì override toàn cục.

## 13. Validation và exception handling

Converter/Formatter có trách nhiệm tạo một giá trị đúng kiểu và định dạng. Validation có thể bổ sung các ràng buộc nghiệp vụ sau khi dữ liệu được bind.

Những cơ chế khác nhau:

- Không parse được path/query sang kiểu đích: lỗi conversion/binding, thường trả 400.
- DTO @Valid không đạt ràng buộc: Spring MVC thường chuyển lỗi validation thành 400.
- Message converter không đọc được body: HttpMessageNotReadableException, thường trả 400.
- Media type không hỗ trợ: 415 hoặc 406 tùy chiều request/response.
- Argument resolver thiếu ngữ cảnh bắt buộc: tự quyết định thông báo lỗi, ví dụ ResponseStatusException(400) trong sample.
- Sai quyền truy cập: 401/403 phải được xử lý bằng cơ chế security thích hợp, không dùng lỗi parse 400 để thay thế.

Ứng dụng production có thể dùng @RestControllerAdvice để chuyển các lỗi thành một cấu trúc ổn định như ProblemDetail. Tránh trả raw exception message chứa thông tin hệ thống, SQL hoặc dữ liệu nhạy cảm ra client. Đồng thời log đủ request ID và nguyên nhân để điều tra.

Không bọc mọi lỗi converter vào RuntimeException rồi trả HTTP 500; lỗi input không hợp lệ cần được phân loại đúng. Ngược lại, không giấu lỗi lập trình nghiêm trọng dưới status 400 chỉ để có vẻ “an toàn”.

## 14. Phạm vi áp dụng: toàn cục, theo controller và theo field

Có nhiều cấp độ cấu hình:

| Phạm vi | Cơ chế ví dụ | Khi nào chọn |
| --- | --- | --- |
| Toàn bộ ứng dụng MVC | WebMvcConfigurer.addFormatters | Value object được dùng nhất quán ở nhiều controller |
| Một field/parameter cụ thể | @DateTimeFormat, @NumberFormat | Quy ước đã có trong Spring đủ dùng |
| Một controller/binder | @InitBinder | Parser/editor riêng theo nhóm form/controller |
| Theo loại HTTP body | HttpMessageConverter | Media type hoặc representation riêng |
| Theo kiểu/annotation parameter | HandlerMethodArgumentResolver | Ngữ cảnh request đặc thù được inject vào controller |
| Toàn bộ JSON schema | Jackson configuration | Thay đổi JSON serialization/deserialization có chủ đích |

Không đăng ký toàn cục chỉ vì muốn giải quyết một trường hợp nhỏ. Ranh giới càng rộng thì nguy cơ ảnh hưởng endpoint không liên quan càng lớn.

Với REST API, ưu tiên định dạng input được đặc tả rõ, JSON DTO dễ hiểu và annotation có sẵn. Custom extension nên giải quyết nhu cầu thực sự lặp lại và phải có test ràng buộc behavior.

## 15. Tác động của @EnableWebMvc và cấu hình mặc định

Spring Boot thường tự cấu hình MVC khi spring-boot-starter-web phù hợp có trên classpath. Những mặc định có thể bao gồm HttpMessageConverters, conversion service, static resource mappings, view resolver và cấu hình path matching.

Nếu chỉ muốn bổ sung formatter/converter/resolver, dùng @Configuration implements WebMvcConfigurer và **không thêm @EnableWebMvc**. Trong Boot, dùng @EnableWebMvc làm thay đổi cơ chế auto-configuration; ứng dụng có thể mất những mặc định đang dựa vào.

Các dấu hiệu khi tùy chỉnh quá mức:

- Một số endpoint trước đây trả JSON nay bị 406.
- @RequestBody từng đọc JSON nhưng giờ trả 415.
- Static resources bị 404 sau khi cấu hình MVC.
- Một controller nhận request nhưng binding parameter mặc định ngừng hoạt động.
- Một formatter toàn cục làm ngày tháng hoặc số đổi format trên nhiều API.

Hãy kiểm tra diff cấu hình, các WebMvcConfigurer mới thêm, danh sách converters và hoạt động của endpoint cũ. Sửa đúng điểm mở rộng; tránh vô hiệu hóa toàn bộ MVC defaults để giải quyết một nhu cầu hẹp.

## 16. Kiểm soát thứ tự và độ rộng của converter

Một vài nguyên tắc vận hành:

1. supports(Class<?>) chỉ nên trả true cho type thực sự thuộc định dạng custom.
2. Media types cần cụ thể; tránh tự tuyên bố hỗ trợ tất cả request/response nếu không cần.
3. Thứ tự đăng ký quan trọng khi nhiều converter cùng hỗ trợ một Java type và media type.
4. Khi thêm mới, dùng extendMessageConverters để giữ defaults; kiểm tra bằng test JSON và text.
5. Khi override mặc định thật sự, nêu rõ mục tiêu, tác động đến endpoint và khả năng rollback.
6. Không đọc unbounded request body bằng readAllBytes() trong converter public mà không có giới hạn phù hợp.
7. Parse dữ liệu với charset rõ ràng và xử lý input malformed theo contract.
8. Nếu cần streaming file lớn, nghiên cứu Resource/StreamingResponseBody hoặc giải pháp streaming phù hợp, thay vì buffer toàn bộ body vào RAM.

Trong ví dụ, PlainNoteMessageConverter được chèn đầu danh sách nhưng supports() chỉ nhận PlainNote và media type là text/plain. Lựa chọn này giữ ảnh hưởng nhỏ; với một converter có thể xử lý nhiều kiểu, cách đặt ở đầu danh sách cần được đánh giá lại.

## 17. Liên hệ với bảo mật và đa tenant

Header, cookie hoặc principal đều có thể trở thành nguồn dữ liệu cho HandlerMethodArgumentResolver, nhưng trách nhiệm xác thực/phân quyền phải rõ ràng.

Ở hệ thống thật:

- Authentication filter hoặc security chain cần xác thực user/token trước khi ứng dụng tin identity.
- TenantContext nên được tạo từ principal/claims đã xác thực và đối chiếu quyền truy cập dữ liệu.
- Không cho một header tùy ý quyết định tenant của database nếu client chưa được xác thực.
- Tránh giữ tenant theo static mutable field vì request xử lý đồng thời.
- Khi dùng ThreadLocal hoặc context propagation, phải hiểu lifecycle, cleanup, async dispatch và executor; không giữ dữ liệu request sang thread khác một cách thiếu kiểm soát.
- Nếu resolver gọi database/remote service, phải hiểu tác động về latency, timeout và failure mode trong mọi request.

Custom resolver có thể giảm lặp code nhưng cũng trở thành hạ tầng tập trung; lỗi ở đó có thể ảnh hưởng mọi endpoint dùng annotation tương ứng. Cần unit/integration test với nhiều tình huống phân quyền.

## 18. Lỗi thường gặp và hướng khắc phục

| Triệu chứng | Khả năng nguyên nhân | Cách xử lý |
| --- | --- | --- |
| @PathVariable ProductCode trả 400 | Converter không đăng ký hoặc format sai | Kiểm tra addFormatters, source type, regex và URL |
| @RequestParam BillingPeriod trả 400 | Formatter parse thất bại hoặc input sai MM/yyyy | Kiểm tra định dạng, encoding và exception |
| Annotation @Tenant không có tác dụng | supportsParameter không match annotation/type hoặc resolver chưa đăng ký | Kiểm tra @Retention(RUNTIME), addArgumentResolvers, signature |
| Resolver xử lý nhầm parameter | supportsParameter quá rộng | Chỉ match annotation/kiểu rõ ràng |
| @RequestBody text/plain trả 415 | Thiếu custom message converter hoặc consumes/media type sai | Kiểm tra Content-Type, supports, converter list |
| Trả PlainNote bị 406 | Không có converter ghi type theo Accept/produces | Kiểm tra converter write và media type |
| JSON cũ lỗi sau khi thêm custom converter | Converter hỗ trợ Object hoặc media type quá rộng | Thu hẹp supports/media type, kiểm tra thứ tự |
| Static resource/format mặc định bị mất | Bật @EnableWebMvc hoặc override cấu hình quá mức | Giữ WebMvcConfigurer mở rộng thay vì thay toàn bộ Boot MVC |
| Unit test pass nhưng HTTP lỗi | Test gọi thẳng controller nên bỏ qua MVC pipeline | Dùng MockMvc/integration test |
| Format ngày khác theo môi trường | Locale hoặc formatter global không được kiểm soát | Cố định hợp đồng API, dùng @DateTimeFormat hoặc test locale |
| POST body lớn làm tăng memory | Converter đọc hết body không giới hạn | Giới hạn body và kiểm soát streaming |
| Tenant bị giả mạo | Dùng header không xác thực làm danh tính | Dùng principal/claims đã xác minh và authorization |
| Đổi JSON không có tác dụng | Thay Converter<String,T> trong khi Jackson đang xử lý | Dùng Jackson config/serializer/deserializer |
| Có Spring WebFlux nhưng MVC config không chạy | Ứng dụng là reactive web stack | Dùng API/configuration dành cho WebFlux |

## 19. Bài thực hành mở rộng

Sau khi chạy project mẫu, hãy thực hiện các bài thực hành sau:

**Bài 1 — Converter:** Đổi quy tắc ProductCode sang SKU-xxxxxx, thêm test mã hợp lệ, mã chứa chữ, mã thiếu số và mã có khoảng trắng. Giải thích việc normalize nên ở converter hay domain constructor.

**Bài 2 — Formatter:** Chuyển BillingPeriod sang format yyyy-MM; thay formatter, test parse và print cho hai chiều. Nếu sản phẩm có đa ngôn ngữ, bổ sung Locale phù hợp và chứng minh round-trip không đổi ý nghĩa.

**Bài 3 — Resolver:** Thêm @CurrentRequestId RequestId lấy từ request attribute do filter tin cậy thiết lập, với fallback an toàn. Thử request thiếu attribute, thử nhiều request liên tiếp để chứng minh không dùng mutable shared state.

**Bài 4 — Body converter:** Thêm PlainNote text/plain hợp lệ và body vượt giới hạn; test response status, charset và body. Đảm bảo GET JSON vẫn pass khi custom converter đã đăng ký.

**Bài 5 — Lỗi:** Bổ sung @RestControllerAdvice để tạo response lỗi nhất quán; giữ status 400/406/415 chính xác và không lộ stack trace.

**Bài 6 — Ranh giới:** Thử viết converter JSON thay vì text/plain rồi so sánh với Jackson serializer. Chọn phương án ít tác động hơn và giải thích vì sao.

Bằng chứng hoàn thành nên gồm source code, output curl hoặc MockMvc, log lỗi khi input sai, và danh sách endpoint cũ vẫn chạy như trước.

## 20. Câu hỏi tự kiểm tra

1. Converter<S,T> khác HttpMessageConverter<T> ở điểm nào?
2. Vì sao Formatter<T> có parse và print trong khi Converter<S,T> chỉ có convert?
3. Khi nào @DateTimeFormat tốt hơn một Formatter<LocalDate> toàn cục?
4. Vì sao @PathVariable ProductCode thường chỉ cần Converter mà không cần custom argument resolver?
5. supportsParameter(...) của HandlerMethodArgumentResolver nên match phạm vi nào?
6. Vì sao không dùng header client tự gửi làm bằng chứng tenant đã được xác thực?
7. MVC xử lý @RequestBody và @ResponseBody bằng cơ chế nào?
8. Content-Type và Accept ảnh hưởng việc chọn message converter ra sao?
9. Vì sao nên dùng extendMessageConverters khi chỉ thêm một converter?
10. Thêm @EnableWebMvc vào Boot có thể gây những tác động gì?
11. Một Formatter đăng ký cho MVC có mặc nhiên làm Jackson đổi JSON format không?
12. MockMvc test chứng minh điều gì, và nó có mở TCP port thật không?
13. Khi bị lỗi 400, 406 hoặc 415, kiểm tra những lớp xử lý nào trước?
14. Nếu một custom converter làm hỏng JSON API cũ, cần kiểm tra supports, media type và thứ tự ra sao?
15. Cần kiểm thử gì trước khi đưa một argument resolver dùng chung vào production?

## Tài liệu chính thức

- [Spring Boot 3.3 – Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html)
- [Spring Boot – Spring MVC Customization](https://docs.spring.io/spring-boot/how-to/spring-mvc.html)
- [Spring Framework – Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring Framework – Field Formatting](https://docs.spring.io/spring-framework/reference/core/validation/format.html)
- [Spring Framework – MVC Configuration](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config.html)
- [Spring Framework – HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html)
- [WebMvcConfigurer API (Spring Framework 6.1)](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/servlet/config/annotation/WebMvcConfigurer.html)

Các ví dụ tập trung vào MVC trên Spring Boot 3.3.x. Khi nâng phiên bản framework, hãy xem lại API và hành vi mặc định tương ứng trước khi sao chép cấu hình sang ứng dụng production.
