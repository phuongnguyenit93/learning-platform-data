# Converter tùy chỉnh và phạm vi áp dụng

Khi Spring Boot đọc cấu hình, nhận tham số HTTP hoặc bind dữ liệu vào một object Java, đầu vào thường là chuỗi nhưng chương trình lại muốn những kiểu có ý nghĩa hơn như `Duration`, `DataSize`, `UUID`, `LocalDate` hoặc một value object do ứng dụng định nghĩa. **Spring ConversionService** cung cấp hạ tầng chuyển đổi kiểu. Khi những phép chuyển đổi có sẵn chưa đáp ứng yêu cầu, ta có thể viết một **custom Converter**.

Điểm quan trọng không chỉ là biết tạo một class `Converter<S, T>`, mà còn phải hiểu **converter được đăng ký ở đâu thì có hiệu lực ở đó**:

- Converter đăng ký cho **`@ConfigurationProperties` binding** phục vụ việc chuyển các giá trị cấu hình.
- Converter đăng ký vào **Spring MVC ConversionService** phục vụ data binding của request parameter, path variable và các trường form phù hợp.
- Converter đăng ký trong **một `ConversionService` tự tạo** chỉ có hiệu lực với những lời gọi sử dụng service đó.
- Converter kiểu Spring **không tự động** biến thành Jackson JSON deserializer, JPA `AttributeConverter` hoặc converter của mọi hệ thống khác.

Việc phân biệt các phạm vi này giúp tránh lỗi “converter đã tạo bean nhưng vẫn không hoạt động” và tránh mở rộng một quy tắc chuyển đổi nội bộ thành hành vi toàn ứng dụng ngoài ý muốn.

## 1. ConversionService là gì?

`ConversionService` thuộc Spring Core, là API cho phép chuyển đổi từ kiểu nguồn sang kiểu đích.

Ví dụ với conversion service có hỗ trợ chuyển đổi số:

~~~java
ConversionService conversionService = ...;

Integer port = conversionService.convert("8080", Integer.class);
~~~

Ứng dụng không cần tự viết `Integer.parseInt(...)` trong mỗi chỗ bind. Spring dùng thông tin kiểu và converter đã đăng ký để thực hiện conversion.

Các interface chính:

~~~java
package org.springframework.core.convert;

public interface ConversionService {
    boolean canConvert(Class<?> sourceType, Class<?> targetType);
    <T> T convert(Object source, Class<T> targetType);
}
~~~

Với generic types phức tạp như collection, `ConversionService` còn có API dựa trên `TypeDescriptor` để mô tả kiểu nguồn và đích chi tiết hơn.

### Phân biệt ba khái niệm

| Khái niệm | Chức năng |
|---|---|
| **Conversion** | Chuyển giá trị từ kiểu A sang kiểu B, ví dụ String → RegionCode |
| **Binding** | Ánh xạ dữ liệu từ nguồn (property/request) vào constructor, bean property hoặc object graph |
| **Validation** | Kiểm tra giá trị sau chuyển đổi có thỏa điều kiện nghiệp vụ hay không |

Một binder có thể gọi converter trong quá trình bind. Validation lại là một bước riêng: chuỗi chuyển thành `int` thành công không có nghĩa giá trị đó hợp lệ về nghiệp vụ.

## 2. Những converter Spring Boot đã cung cấp

Spring Framework và Spring Boot hỗ trợ nhiều phép chuyển đổi thông dụng, nên không cần tự viết converter cho mọi trường hợp:

- Chuỗi sang kiểu số, boolean, enum và nhiều kiểu cơ bản.
- Chuỗi sang `UUID` khi định dạng phù hợp.
- Chuỗi sang một số kiểu thời gian/ngày tháng tùy conversion service và cấu hình formatter.
- Giá trị có đơn vị như `5s` hoặc `250ms` sang `Duration` trong configuration binding của Boot.
- Giá trị như `10MB` sang `DataSize` theo conversion service của Boot.
- Một số kiểu collection, array và các phép chuyển đổi có sẵn khác.

Ví dụ:

~~~yaml
app:
  upload:
    timeout: 5s
    max-size: 10MB
~~~

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.util.unit.DataSize;

@ConfigurationProperties(prefix = "app.upload")
public record UploadProperties(
        Duration timeout,
        DataSize maxSize) {
}
~~~

Với một `@ConfigurationProperties` bean được đăng ký đúng cách, Spring Boot có thể bind hai property trên mà không cần custom converter.

**Nguyên tắc:** Trước khi viết converter mới, hãy xác định conversion service đang dùng đã hỗ trợ kiểu đích, đơn vị và format đó chưa. Nếu chỉ cần chuyển `5s` thành `Duration`, custom converter thường là không cần thiết.

## 3. Viết một Converter<S, T> đơn giản

Giả sử cấu hình có mã vùng như `vn`, `US` hoặc ` jp `. Ứng dụng muốn chuyển chúng thành value object `RegionCode` có quy tắc chuẩn hóa và kiểm tra định dạng.

### 3.1. Định nghĩa kiểu dữ liệu đích

~~~java
package com.example.fulfillment.domain;

import java.util.Locale;

public record RegionCode(String value) {

    public RegionCode {
        if (value == null || !value.matches("[A-Z]{2}")) {
            throw new IllegalArgumentException(
                    "Region code must contain exactly two A-Z letters");
        }
    }

    public static RegionCode parse(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException(
                    "Region code must not be blank");
        }

        return new RegionCode(raw.trim().toUpperCase(Locale.ROOT));
    }
}
~~~

Record này chỉ là **value object minh họa**: nó kiểm tra hai chữ cái ASCII viết hoa, không kiểm tra mã có thực sự nằm trong danh mục quốc gia/vùng được ứng dụng hỗ trợ hay không. Để kiểm tra tập mã hợp lệ, cần thêm quy tắc nghiệp vụ riêng.

### 3.2. Tạo Converter

~~~java
package com.example.fulfillment.config;

import com.example.fulfillment.domain.RegionCode;
import org.springframework.core.convert.converter.Converter;

public final class StringToRegionCodeConverter
        implements Converter<String, RegionCode> {

    @Override
    public RegionCode convert(String source) {
        return RegionCode.parse(source);
    }
}
~~~

Hai generic parameters có ý nghĩa:

- `String`: kiểu dữ liệu đầu vào.
- `RegionCode`: kiểu dữ liệu đích.
- `convert(String source)`: phép biến đổi cụ thể.

Ví dụ:

~~~java
Converter<String, RegionCode> converter =
        new StringToRegionCodeConverter();

RegionCode region = converter.convert(" vn ");
System.out.println(region.value()); // VN
~~~

Một converter như vậy nên **stateless**, không gọi database, không có side effect và không giữ dữ liệu riêng của request. Những converter được đăng ký trong Spring thường là đối tượng dùng chung, nên không được giả định mỗi lần chuyển đổi có một instance mới.

## 4. Đăng ký một converter vào ConversionService thủ công

Để hiểu cơ chế trước khi tích hợp với Spring Boot, có thể tự tạo conversion service rồi đăng ký converter:

~~~java
import org.springframework.core.convert.support.DefaultConversionService;

DefaultConversionService conversionService =
        new DefaultConversionService();

conversionService.addConverter(new StringToRegionCodeConverter());

RegionCode region =
        conversionService.convert("vn", RegionCode.class);

System.out.println(region.value()); // VN
~~~

Ở đây, converter có hiệu lực cho **`conversionService` instance** vừa tạo. Nó không tự ảnh hưởng Spring MVC, `@ConfigurationProperties` hay một application context khác.

### 4.1. Đăng ký theo kiểu tường minh

Spring sử dụng metadata generic của converter để biết source và target type. Khi cần kiểm soát rõ ràng, có thể đăng ký:

~~~java
conversionService.addConverter(
        String.class,
        RegionCode.class,
        new StringToRegionCodeConverter()
);
~~~

Cách này hữu ích với những implementation không cung cấp được thông tin generic theo cách Spring có thể suy luận.

### 4.2. Tự gọi converter và ConversionService khác nhau

Gọi trực tiếp:

~~~java
new StringToRegionCodeConverter().convert("vn");
~~~

là một lời gọi Java thông thường. Gọi qua `ConversionService` cho phép container chọn converter dựa trên kiểu nguồn/đích và kết hợp với những conversion khác khi API hỗ trợ.

Converter chỉ thực sự tham gia vào data binding nếu binder ở điểm đó **sử dụng một conversion service có đăng ký nó**.

## 5. Phạm vi 1: @ConfigurationProperties binding

Spring Boot có cơ chế đặc thù để bind externalized configuration vào class dùng `@ConfigurationProperties`. Một converter muốn phục vụ riêng quá trình này nên được đăng ký bằng `@ConfigurationPropertiesBinding`.

### 5.1. Định nghĩa configuration properties

~~~yaml
app:
  fulfillment:
    origin: vn
    timeout: 2s
    max-payload: 5MB
~~~

~~~java
package com.example.fulfillment.config;

import java.time.Duration;
import com.example.fulfillment.domain.RegionCode;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.util.unit.DataSize;

@ConfigurationProperties(prefix = "app.fulfillment")
public record FulfillmentProperties(
        RegionCode origin,
        Duration timeout,
        DataSize maxPayload) {
}
~~~

Các property có `Duration` và `DataSize` dùng converter có sẵn của Boot. Riêng `origin` là kiểu `RegionCode` của ứng dụng, nên ta muốn Binder dùng `StringToRegionCodeConverter`.

### 5.2. Đăng ký converter cho configuration binding

~~~java
package com.example.fulfillment.config;

import com.example.fulfillment.domain.RegionCode;
import org.springframework.boot.context.properties.ConfigurationPropertiesBinding;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;

@Configuration(proxyBeanMethods = false)
public class FulfillmentConversionConfiguration {

    @Bean
    @ConfigurationPropertiesBinding
    static Converter<String, RegionCode> regionCodeConverter() {
        return new StringToRegionCodeConverter();
    }
}
~~~

`@ConfigurationPropertiesBinding` là qualifier được Spring Boot dùng để phát hiện converter dành cho configuration properties binding. Nó giúp thể hiện rõ phạm vi áp dụng, thay vì kỳ vọng mọi conversion service trong ứng dụng đều tự dùng converter.

Phương thức `@Bean` được khai báo `static` có chủ đích. Converter dành cho configuration properties có thể được yêu cầu **rất sớm** trong quá trình bootstrap; phương thức static giúp tránh phải tạo instance của class `@Configuration` quá sớm chỉ để gọi factory method.

### 5.3. Đăng ký properties class

~~~java
package com.example.fulfillment;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class FulfillmentApplication {

    public static void main(String[] args) {
        SpringApplication.run(FulfillmentApplication.class, args);
    }
}
~~~

Để cấu hình converter hoạt động, `FulfillmentConversionConfiguration` cũng phải được Spring xử lý. Ví dụ trên giả định class cấu hình nằm trong package con được component scan của ứng dụng bao phủ, hoặc đã được nhập bằng `@Import`.

Khi khởi động:

~~~text
application.yml
  app.fulfillment.origin=vn
            |
            v
@ConfigurationProperties Binder
            |
            v
StringToRegionCodeConverter
            |
            v
RegionCode("VN")
            |
            v
FulfillmentProperties.origin()
~~~

Các service khác có thể inject `FulfillmentProperties` như một bean Spring bình thường.

### 5.4. Đăng ký tường minh khi không muốn scan

Nếu properties class không nằm trong phạm vi `@ConfigurationPropertiesScan`, có thể dùng:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(FulfillmentProperties.class)
@Import(FulfillmentConversionConfiguration.class)
public class FulfillmentModuleConfiguration {
}
~~~

Đây cũng là một cách đóng gói module dùng chung: ứng dụng import một configuration class thay vì mở rộng component scan ra toàn bộ package thư viện.

### 5.5. @ConfigurationPropertiesBinding không có nghĩa “mọi nơi”

Giả sử `regionCodeConverter` được đánh dấu `@ConfigurationPropertiesBinding` và hoạt động khi bind `app.fulfillment.origin`. Không nên tự kết luận rằng:

- `@PathVariable RegionCode` trong controller cũng hoạt động.
- JSON request có trường `"origin": "vn"` sẽ được Jackson chuyển thành `RegionCode`.
- Entity JPA có field `RegionCode` sẽ tự được lưu thành chuỗi.
- Lời gọi `@Value("${app.fulfillment.origin}")` bắt buộc đi qua chính converter đó.

Các vị trí này có **cơ chế binding hoặc conversion riêng**. Muốn áp dụng cùng quy tắc ở nơi khác, hãy đăng ký converter vào conversion service được nơi đó dùng hoặc triển khai extension point tương ứng.

## 6. Vì sao converter cho configuration properties cần ít dependency?

Spring Boot thường cần bind cấu hình trong quá trình tạo context. Một số converter cấu hình được yêu cầu khi các bean khác chưa khởi tạo đầy đủ.

Ví dụ không nên:

~~~java
@Component
@ConfigurationPropertiesBinding
public class DatabaseRegionConverter
        implements Converter<String, RegionCode> {

    private final RegionRepository repository;

    public DatabaseRegionConverter(RegionRepository repository) {
        this.repository = repository;
    }

    @Override
    public RegionCode convert(String source) {
        return repository.findByText(source);
    }
}
~~~

Lý do:

1. Binder cần converter để tạo các configuration properties bean.
2. Converter yêu cầu `RegionRepository`.
3. Repository có thể phụ thuộc datasource, transaction infrastructure hoặc chính một properties bean đang được bind.
4. Spring có thể phải tạo nhiều bean quá sớm hoặc gặp circular dependency.

Thậm chí nếu cấu hình tình cờ chạy được, kết quả binding giờ phụ thuộc database hoặc dịch vụ ngoài, làm startup phức tạp và khó kiểm thử.

**Thiết kế phù hợp hơn:** converter chỉ thực hiện parsing/normalization của một giá trị. Nếu cần kiểm tra mã vùng có tồn tại trong database, hãy thực hiện validation nghiệp vụ ở một service sau khi context có đủ dependency.

### 6.1. Vì sao @Bean static được khuyến nghị?

Cấu hình:

~~~java
@Configuration(proxyBeanMethods = false)
class ConversionConfiguration {

    @Bean
    @ConfigurationPropertiesBinding
    static Converter<String, RegionCode> regionCodeConverter() {
        return new StringToRegionCodeConverter();
    }
}
~~~

không đòi hỏi Spring phải khởi tạo một instance `ConversionConfiguration` chỉ để gọi method factory. Điều này giảm khả năng kéo theo việc khởi tạo sớm không cần thiết của configuration class.

`static` không làm converter chạy “mỗi lần một object”. Bean được đăng ký vẫn tuân theo scope của bean definition; theo mặc định nó là singleton.

## 7. Phạm vi 2: chuyển đổi dữ liệu trong Spring MVC

HTTP request cung cấp các giá trị như query parameter và path variable dưới dạng chuỗi. Spring MVC có một conversion service dùng cho data binding từ request.

Ví dụ mong muốn:

~~~text
GET /shipping/options?region=vn
~~~

Controller:

~~~java
import com.example.fulfillment.domain.RegionCode;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ShippingController {

    @GetMapping("/shipping/options")
    public String options(@RequestParam RegionCode region) {
        return "Options for " + region.value();
    }
}
~~~

Muốn `@RequestParam RegionCode` được bind từ `"vn"`, hãy đăng ký converter với **Spring MVC formatter registry**.

~~~java
import com.example.fulfillment.config.StringToRegionCodeConverter;
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class ShippingWebConfiguration implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToRegionCodeConverter());
    }
}
~~~

Spring MVC sử dụng converter khi cần bind tham số `region` vào kiểu `RegionCode`. Nếu đầu vào không hợp lệ, quá trình bind có thể tạo lỗi chuyển kiểu; với request parameter thông thường, ứng dụng thường phản hồi 400 Bad Request theo cơ chế xử lý lỗi mặc định hoặc `@ControllerAdvice`.

Đăng ký trên `WebMvcConfigurer` này **không tự đăng ký converter cho mọi `@ConfigurationProperties`**. Nếu muốn cùng phép chuyển đổi ở cả hai nơi, có thể tái sử dụng class `StringToRegionCodeConverter` nhưng đăng ký tường minh ở từng conversion service thích hợp.

### 7.1. Ví dụ @PathVariable

~~~java
@GetMapping("/shipping/regions/{region}")
public String detail(@PathVariable RegionCode region) {
    return "Region " + region.value();
}
~~~

Với MVC converter đã đăng ký, `/shipping/regions/us` có thể được chuyển thành `RegionCode("US")`.

### 7.2. Không phải cách đọc JSON @RequestBody

Ví dụ JSON request:

~~~json
{
  "region": "vn",
  "quantity": 5
}
~~~

~~~java
@PostMapping("/shipping/orders")
public void create(@RequestBody CreateOrderRequest request) {
}
~~~

Với `@RequestBody` JSON trong Spring MVC, dữ liệu thường được Jackson deserialize qua `HttpMessageConverter`, không phải đi qua Spring MVC `Converter<String, RegionCode>` theo cùng cách `@RequestParam` hoạt động.

Muốn Jackson chuyển một chuỗi JSON thành value object, có thể thiết kế `@JsonCreator`/`@JsonValue` khi phù hợp hoặc dùng custom Jackson deserializer/module. Đây là extension point khác với Spring `ConversionService`.

## 8. Phạm vi 3: @InitBinder và dữ liệu form cục bộ

Spring MVC cho phép tùy biến data binding theo controller thông qua `@InitBinder`, chẳng hạn đăng ký một `PropertyEditor` cho một kiểu cụ thể.

~~~java
import java.beans.PropertyEditorSupport;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.RestController;

@RestController
class RegionFormController {

    @InitBinder
    void configureBinder(WebDataBinder binder) {
        binder.registerCustomEditor(
                RegionCode.class,
                new PropertyEditorSupport() {
                    @Override
                    public void setAsText(String text) {
                        setValue(RegionCode.parse(text));
                    }
                }
        );
    }
}
~~~

Đây là ví dụ dùng **PropertyEditor** của JavaBeans để thể hiện cơ chế binder cục bộ, không phải `Converter`. Với nhu cầu chung cho nhiều controller, đăng ký `Converter` vào MVC `FormatterRegistry` thường rõ ràng hơn.

Khi dùng custom editor, phải lưu ý lifecycle và thread safety. `PropertyEditor` thường có mutable state (qua `setValue`), vì vậy không nên tái sử dụng tùy tiện một instance mutable cho mọi thread.

## 9. Converter, ConverterFactory, GenericConverter và Formatter

Không phải mọi conversion problem đều nên dùng một `Converter<S,T>` đơn lẻ.

| Extension point | Khi nào nên dùng | Ví dụ |
|---|---|---|
| `Converter<S,T>` | Một phép đổi kiểu nguồn–đích cụ thể | String → RegionCode |
| `ConverterFactory<S,R>` | Một họ kiểu đích có chung cách chuyển đổi | String → nhiều subtype liên quan |
| `GenericConverter` | Cần nhiều cặp kiểu hoặc metadata kiểu nguồn/đích | Conversion phụ thuộc `TypeDescriptor` |
| `ConditionalGenericConverter` | Chỉ áp dụng nếu metadata/thành phần target thỏa điều kiện | Kiểm tra khả năng conversion theo field/annotation |
| `Formatter<T>` | Chuyển text ↔ object theo locale | Ngày, tiền tệ, định dạng hiển thị |
| `PropertyEditor` | Cơ chế JavaBeans cũ, có thể đăng ký cho WebDataBinder | Chuyển string cục bộ theo binder |

### 9.1. Converter<S,T>

Interface:

~~~java
public interface Converter<S, T> {
    T convert(S source);
}
~~~

Nên chọn đầu tiên cho phép chuyển đổi đơn giản, rõ ràng, ví dụ `StringToRegionCodeConverter`.

### 9.2. ConverterFactory<S,R>

`ConverterFactory` cung cấp những converter ứng với một họ target type có chung supertype. Spring có những factory converter phục vụ các chuyển đổi kiểu enum.

Hãy dùng nó khi phải chọn thuật toán theo target subtype. Nếu chỉ có một kiểu đích `RegionCode`, một `Converter<String, RegionCode>` dễ đọc và đủ mạnh.

### 9.3. GenericConverter

`GenericConverter` làm việc với `ConvertiblePair` và `TypeDescriptor`, giúp xét kiểu generic, annotation hoặc nhiều cặp source/target type. Nó phù hợp cho thư viện binding hạ tầng, nhưng phức tạp hơn converter thường. Không nên chọn chỉ để xử lý một chuỗi có prefix đơn giản.

### 9.4. Formatter<T>

`Formatter<T>` có hai hướng:

~~~java
public interface Formatter<T>
        extends Printer<T>, Parser<T> {
}
~~~

- `parse(String text, Locale locale)`: text → object.
- `print(T object, Locale locale)`: object → text.

Nếu giá trị có ý nghĩa hiển thị khác nhau theo locale, ví dụ ngày tháng hoặc số tiền, `Formatter` thường phù hợp hơn `Converter` không có tham số locale.

Ví dụ một ứng dụng phục vụ nhiều locale không nên cố diễn giải `01/02/2026` như cùng một ngày ở mọi quốc gia khi format ngày có thể khác nhau. Với form/query param, có thể dùng `@DateTimeFormat` và các formatter có sẵn trước khi tự viết.

## 10. Không mở rộng conversionService bean toàn cục khi chỉ cần một phạm vi hẹp

Spring và Spring Boot có thể sử dụng những conversion service khác nhau cho những công việc khác nhau. Đặc biệt, một bean có tên `conversionService` trong application context có thể được Spring dùng cho conversion của bean factory và các giá trị thuộc tính liên quan.

Ví dụ:

~~~java
@Bean(name = "conversionService")
ConversionService applicationConversionService() {
    // Cần cân nhắc kỹ nếu thay thế conversion service dùng chung.
}
~~~

Việc thay đổi conversion service dùng chung có thể ảnh hưởng các converter mặc định hoặc quá trình tạo bean, và bean này có thể phải được tạo rất sớm. Nếu tự thay thế mà không giữ những converter cần thiết, một số phép chuyển đổi trước đây hoạt động có thể bị lỗi.

Đối với Spring Boot configuration properties, **ưu tiên `@ConfigurationPropertiesBinding`** cho converter của một kiểu dữ liệu cụ thể. Đối với request parameter của Spring MVC, **ưu tiên `WebMvcConfigurer.addFormatters`**. Tránh thay global conversion service chỉ để một property kiểu `RegionCode` bind thành công.

Cũng không nên kết luận một bean converter chỉ cần có `@Component` là tự động được sử dụng trong tất cả conversion service. Cơ chế thu thập converter phụ thuộc vào framework component và cấu hình hiện tại.

## 11. Ranh giới với Resource và ResourceLoader

Trong bài học về tài nguyên và dữ liệu, dễ gặp những giá trị cấu hình dạng đường dẫn:

~~~properties
app.templates.invoice=classpath:/templates/invoice.txt
app.archive.location=file:/var/app/archive/
~~~

Spring có abstraction `Resource` và `ResourceLoader` để truy cập resource từ classpath, file hoặc những protocol được hỗ trợ:

~~~java
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;

public class InvoiceTemplateService {

    private final Resource invoiceTemplate;

    public InvoiceTemplateService(ResourceLoader resourceLoader) {
        this.invoiceTemplate = resourceLoader.getResource(
                "classpath:/templates/invoice.txt"
        );
    }
}
~~~

Đây là cơ chế **resolve resource location** từ một chuỗi. Nó không có nghĩa mọi custom converter cần mở file hoặc đọc nội dung resource. Nếu chỉ muốn chuyển một chuỗi cấu hình thành `Resource`, hãy cân nhắc khả năng chuyển đổi/resource editor mặc định của Spring trước khi thêm converter.

Phân biệt:

| Nhiệm vụ | Hạ tầng thích hợp |
|---|---|
| String → value object, ví dụ RegionCode | `Converter` |
| String location → Resource handle | `ResourceLoader` / resource conversion phù hợp |
| Đọc bytes/text từ Resource | `Resource.getInputStream()` và I/O API |
| JSON → Java object | Jackson/HttMessageConverter tương ứng |
| Entity field → database column | JPA converter/JDBC mapping |
| Cấu hình YAML/property → typed object | Spring Boot Binder + ConversionService |

**Lưu ý bảo mật:** Nếu đầu vào là do người dùng cung cấp, đừng đưa trực tiếp một chuỗi path/URL chưa kiểm soát vào `ResourceLoader` rồi mở stream. Cần giới hạn protocol, thư mục cho phép và quyền truy cập để tránh đọc file ngoài phạm vi hoặc SSRF. Converter nên không làm I/O ngoài ý muốn khi chỉ cần parse dữ liệu.

## 12. Spring Converter khác Jackson và JPA converter

Ba hệ thống hay bị nhầm vì đều dùng từ “converter”:

### 12.1. Spring Converter

~~~java
import org.springframework.core.convert.converter.Converter;

class StringToRegionCodeConverter
        implements Converter<String, RegionCode> {
    @Override
    public RegionCode convert(String source) {
        return RegionCode.parse(source);
    }
}
~~~

Được sử dụng bởi `ConversionService` có đăng ký nó.

### 12.2. Jackson deserializer

Jackson xử lý JSON request/response với cấu hình `ObjectMapper` và các serializer/deserializer. Nếu một API muốn JSON string `"vn"` thành `RegionCode`, có thể dùng annotation của Jackson ở value object hoặc custom deserializer cho kiểu đó.

Một converter của Spring không tự trở thành Jackson deserializer chỉ vì nó là bean.

### 12.3. JPA AttributeConverter

~~~java
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter(autoApply = true)
public class RegionCodeJpaConverter
        implements AttributeConverter<RegionCode, String> {

    @Override
    public String convertToDatabaseColumn(RegionCode region) {
        return region == null ? null : region.value();
    }

    @Override
    public RegionCode convertToEntityAttribute(String value) {
        return value == null ? null : RegionCode.parse(value);
    }
}
~~~

JPA `@Converter` và `AttributeConverter` là cơ chế mapping giữa entity attribute và column type của persistence provider; khác với Spring `org.springframework.core.convert.converter.Converter`.

Để tránh trùng tên import, nhiều dự án đặt tên class rõ như `RegionCodeJpaConverter` và phân biệt hai nhóm annotation. Với Spring Boot 3 dùng Jakarta Persistence, import là `jakarta.persistence.*`; các dự án Boot 2/JPA cũ thường dùng `javax.persistence.*`.

## 13. Lỗi conversion xảy ra thế nào?

Giả sử converter dùng:

~~~java
RegionCode.parse(source)
~~~

và nhận `"123"`. Constructor `RegionCode` sẽ ném `IllegalArgumentException`. Khi conversion diễn ra trong một pipeline Spring, lỗi có thể được bao bởi exception chuyên biệt của framework, chẳng hạn `ConversionFailedException` hoặc lỗi binding tương ứng.

**Hậu quả phụ thuộc phạm vi**:

| Phạm vi | Hành vi thường gặp khi conversion thất bại |
|---|---|
| `@ConfigurationProperties` | Bean binding không hoàn tất; ứng dụng có thể không khởi động nếu properties bean là bắt buộc |
| MVC `@RequestParam` hoặc `@PathVariable` | Lỗi bind argument; thường được chuyển thành response 400 qua cơ chế MVC |
| ConversionService gọi thủ công | Lời gọi `convert(...)` ném exception cho caller xử lý |
| JPA mapping | Lỗi trong quá trình đọc/ghi entity, theo transaction và persistence provider |
| Jackson deserialization | Lỗi xử lý JSON input; response phụ thuộc `HttpMessageConverter`/exception handler |

Không nên dùng converter để tự trả HTTP status hay xử lý transaction: nhiệm vụ của nó là biến đổi giá trị hoặc thông báo thất bại rõ ràng. Controller advice, binder và framework tầng trên chịu trách nhiệm diễn giải lỗi theo ngữ cảnh.

### 13.1. Tạo thông báo lỗi hữu ích

Một converter nên từ chối dữ liệu không hợp lệ theo quy tắc nhất quán:

~~~java
@Override
public RegionCode convert(String source) {
    try {
        return RegionCode.parse(source);
    } catch (IllegalArgumentException ex) {
        throw new IllegalArgumentException(
                "Invalid region code: expected exactly two letters", ex);
    }
}
~~~

Đối với dữ liệu nhạy cảm như token, password hoặc private key, **không đưa toàn bộ input vào exception message**. Những message có thể được ghi vào log, hiển thị trong startup failure report hoặc HTTP error response.

Không nên tự trả về một object giả khi đầu vào sai vì như vậy che giấu lỗi cấu hình và làm downstream code dùng dữ liệu không đúng.

## 14. Chú ý về thứ tự khởi động và phụ thuộc sớm

Converter cấu hình có thể được tạo trước nhiều bean nghiệp vụ. Các dấu hiệu thiết kế cần tránh:

- Inject `DataSource`, `EntityManager` hoặc repository vào configuration-properties converter.
- Gọi HTTP client để xác thực một giá trị cấu hình.
- Tra cứu bean trong `ApplicationContext` bằng tay ngay trong `convert()`.
- Gọi logic dùng `@Transactional` rồi mặc định proxy đã sẵn sàng.
- Mở file hoặc socket cho mỗi lần conversion.
- Dùng converter để thay đổi global application state.

Một converter **thuần** chỉ dựa trên input và một tập quy tắc cố định dễ sử dụng ở nhiều phạm vi khác nhau:

~~~text
String " vn "
      |
      v
Trim + normalize + validate
      |
      v
RegionCode("VN")
~~~

Nếu cần kiểm tra tính hợp lệ dựa trên state của database, hãy làm trong validation/service layer sau binding.

## 15. Kiểm thử Converter độc lập

Phép chuyển đổi thuần dễ kiểm thử bằng JUnit:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class StringToRegionCodeConverterTest {

    private final StringToRegionCodeConverter converter =
            new StringToRegionCodeConverter();

    @Test
    void normalizesInput() {
        RegionCode actual = converter.convert(" vn ");
        assertEquals("VN", actual.value());
    }

    @Test
    void rejectsInvalidInput() {
        assertThrows(
                IllegalArgumentException.class,
                () -> converter.convert("123")
        );
    }

    @Test
    void rejectsBlankInput() {
        assertThrows(
                IllegalArgumentException.class,
                () -> converter.convert("  ")
        );
    }
}
~~~

Đây là unit test cho logic parse/normalize. Nó không chứng minh Spring Boot Binder hoặc Spring MVC đã đăng ký converter đúng phạm vi. Để xác nhận integration, cần context test tại nơi converter sẽ được sử dụng.

## 16. Kiểm thử @ConfigurationPropertiesBinding bằng ApplicationContextRunner

Ví dụ này sử dụng:

- `FulfillmentProperties` record ở phần 5.
- `FulfillmentConversionConfiguration` khai báo static `@Bean` converter.
- Một class cấu hình test đăng ký properties.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;

class FulfillmentBindingTest {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(FulfillmentProperties.class)
    @Import(FulfillmentConversionConfiguration.class)
    static class TestConfiguration {
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfiguration.class);

    @Test
    void bindsRegionCodeUsingCustomConverter() {
        runner.withPropertyValues(
                "app.fulfillment.origin=vn",
                "app.fulfillment.timeout=2s",
                "app.fulfillment.max-payload=5MB"
        ).run(context -> {
            assertThat(context).hasNotFailed();

            FulfillmentProperties properties =
                    context.getBean(FulfillmentProperties.class);

            assertThat(properties.origin().value()).isEqualTo("VN");
            assertThat(properties.timeout())
                    .isEqualTo(java.time.Duration.ofSeconds(2));
        });
    }

    @Test
    void rejectsInvalidRegionCode() {
        runner.withPropertyValues(
                "app.fulfillment.origin=123",
                "app.fulfillment.timeout=2s",
                "app.fulfillment.max-payload=5MB"
        ).run(context -> assertThat(context).hasFailed());
    }
}
~~~

Test phù hợp với một dự án Spring Boot có dependency `spring-boot-starter-test`. Nó kiểm tra hai điều khác nhau:

1. Logic chuyển đổi trong `RegionCode.parse`.
2. Registration: Binder thật của Spring Boot phát hiện converter `@ConfigurationPropertiesBinding` và sử dụng nó khi bind.

Nếu chỉ test `converter.convert("vn")`, bạn chưa kiểm tra được điều thứ hai.

## 17. Kiểm thử converter trong Spring MVC

Một test cho lớp web nên gọi HTTP binding thực tế, chẳng hạn dùng `MockMvc` với cấu hình web có `WebMvcConfigurer.addFormatters(...)`.

Ví dụ đoạn assertion minh họa:

~~~java
mockMvc.perform(get("/shipping/options")
        .param("region", "vn"))
        .andExpect(status().isOk())
        .andExpect(content().string("Options for VN"));
~~~

Đoạn này giả định:

- `ShippingController` đã được đưa vào test context.
- `ShippingWebConfiguration` được import hoặc được component scan.
- MockMvc đã được cấu hình theo MVC stack tương ứng.
- Controller trả chuỗi đúng như ví dụ phần 7.

Nên có thêm test với input sai:

~~~java
mockMvc.perform(get("/shipping/options")
        .param("region", "123"))
        .andExpect(status().isBadRequest());
~~~

Đó là integration test cho request parameter conversion. Nó độc lập với test `@ConfigurationProperties` và giúp phát hiện trường hợp converter chỉ được đăng ký ở một phạm vi.

## 18. Khi có nhiều converter cùng cặp kiểu

Giả sử ứng dụng đăng ký hai `Converter<String, RegionCode>` với quy tắc khác nhau:

~~~java
class StrictRegionConverter implements Converter<String, RegionCode> { ... }
class LenientRegionConverter implements Converter<String, RegionCode> { ... }
~~~

Cần tránh đăng ký cả hai vào cùng conversion service mà không có chủ đích. Tùy registry và thứ tự đăng ký, một converter có thể thay thế hoặc được chọn thay vì converter còn lại, làm kết quả khó dự đoán.

Hãy chọn một quy tắc canonical cho một cặp source/target type trong từng phạm vi. Nếu cần hai cách diễn giải khác nhau theo endpoint/field, cân nhắc:

- Hai target type khác nhau thể hiện semantics.
- Một `Formatter` hoặc converter có metadata/annotation khi thực sự phù hợp.
- Parsing tại service/controller khi quy tắc quá đặc thù.
- Đặt conversion service riêng cho từng module nếu chúng không nên dùng chung quy tắc.

`@Primary` trên một bean converter không phải giải pháp phổ quát để giải quyết hai converter trùng cặp kiểu trong registry; quá trình lựa chọn converter dựa vào cơ chế đăng ký source/target type, không chỉ quy tắc autowire bean.

## 19. Không trộn converter với business validation

Ví dụ mã vùng:

- Conversion: `" vn "` → `RegionCode("VN")`.
- Structural validation: mã phải gồm đúng hai chữ cái.
- Business validation: vùng này có được phép giao hàng không?
- Authorization: người dùng này có quyền sử dụng vùng đó không?

Những bước này nên được phân tách:

~~~text
Raw request/configuration
          |
          v
   Converter (parse + normalize)
          |
          v
   Value object RegionCode
          |
          v
   Validation / business policy
          |
          v
   Authorization / execution
~~~

Nếu Converter gọi cơ sở dữ liệu để quyết định vùng có được giao hàng hay không, một phép biến đổi kiểu đơn giản bị gắn chặt vào business state. Điều đó khó test, tăng I/O và dễ gây vấn đề startup khi converter được dùng cho configuration binding.

Với dữ liệu nhập từ HTTP, trả lỗi 400 hay lỗi nghiệp vụ cụ thể là trách nhiệm của tầng web/service, không phải lý do để custom converter tự biết `HttpServletResponse`.

## 20. Lưu ý về thread safety và hiệu năng

Một converter Spring được đăng ký như singleton bean có thể được dùng đồng thời. Nên thiết kế:

- Không giữ field mutable thay đổi theo mỗi input.
- Không dùng `SimpleDateFormat` chung không đồng bộ cho nhiều thread; ưu tiên `java.time` formatter bất biến hoặc API phù hợp.
- Không tạo kết nối DB/HTTP cho từng lần `convert()`.
- Không thực hiện truy cập filesystem hoặc đọc tài nguyên ngoài ý muốn.
- Không giữ cache vô hạn cho input không kiểm soát.
- Nếu cần định dạng phụ thuộc locale, chọn `Formatter` với `Locale` do framework cung cấp thay vì biến global mutable.
- Đối với input không tin cậy, giới hạn kích thước/độ phức tạp nếu parsing có thể tiêu thụ tài nguyên lớn.

Đối với configuration properties, một giá trị thường được bind khi bean được tạo; nhưng converter có thể được dùng ở các context khác nhau và nhiều lần. Không dựa vào giả định “converter chỉ chạy một lần”.

## 21. Chẩn đoán converter không có hiệu lực

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `@ConfigurationProperties` không bind được `RegionCode` | Converter chưa đăng ký qua `@ConfigurationPropertiesBinding` hoặc configuration class chưa được nạp | Kiểm tra `@Bean`, `@Import` và tên package |
| Converter chạy trong configuration properties nhưng không chạy ở controller | Chưa đăng ký vào MVC `FormatterRegistry` | Dùng `WebMvcConfigurer.addFormatters` |
| MVC tham số vẫn 400 dù converter unit test pass | Registry của web context không chứa converter hoặc input sai | Dùng MockMvc test để kiểm tra wiring |
| JSON field không dùng converter | Jackson xử lý JSON qua HttpMessageConverter/ObjectMapper | Dùng Jackson extension point phù hợp |
| JPA không lưu/đọc kiểu custom đúng | Spring Converter không áp dụng cho entity attribute | Khai báo JPA `AttributeConverter` |
| Startup báo BeanPostProcessor không xử lý bean sớm | Converter/config class phụ thuộc nhiều bean hoặc non-static factory | Giảm dependency, dùng static `@Bean` khi phù hợp |
| `ConversionService` tự tạo không có Duration/DataSize conversion | Đã dùng service khác với Boot ApplicationConversionService | Sử dụng conversion service thích hợp hoặc đăng ký converter cần thiết |
| Exception thông báo input nhạy cảm | Converter nối raw input vào lỗi | Thay bằng thông báo an toàn, không chứa secret |
| Có hai converter cùng cặp kiểu | Registry có quy tắc trùng và thứ tự đăng ký khó dự đoán | Thiết kế một converter canonical theo phạm vi |
| Property đã thay đổi nhưng giá trị bean không đổi | Configuration properties không tự động refresh runtime | Dùng cơ chế refresh/khởi động lại có thiết kế |

Khi gặp lỗi, kiểm tra theo thứ tự: **nguồn dữ liệu → binder đang sử dụng → conversion service cụ thể → converter đã đăng ký → kiểu nguồn/đích → exception gốc**. Không nên chỉ nhìn thấy class `StringToRegionCodeConverter` trong project rồi khẳng định Spring đã sử dụng nó.

## 22. Chọn phạm vi đăng ký phù hợp

| Bạn muốn chuyển đổi ở đâu? | Cơ chế nên dùng |
|---|---|
| Giá trị `application.yml`/Environment vào `@ConfigurationProperties` | `@ConfigurationPropertiesBinding` trên converter bean |
| Query parameter, path variable hoặc MVC form binding | `WebMvcConfigurer.addFormatters` |
| Chuyển đổi thủ công trong một module/service | `ConversionService` riêng và `addConverter` |
| Text có format phụ thuộc Locale trong MVC | `Formatter<T>` và registry phù hợp |
| JSON request/response | Jackson serializer/deserializer hoặc annotation Jackson |
| Entity ↔ database column | JPA `AttributeConverter` / data access mapping tương ứng |
| Chuỗi đường dẫn ↔ Spring Resource | `ResourceLoader` hoặc built-in resource conversion phù hợp |
| Property name/format phổ biến như Duration, DataSize | Ưu tiên built-in converter của Spring Boot |
| Cần thêm quy tắc kiểm tra nghiệp vụ sau conversion | Service/validator độc lập, không nhồi vào converter |

### Nguyên tắc thiết kế thực hành

1. Xác định **input source** và **target type** trước khi viết converter.
2. Kiểm tra built-in conversion có đáp ứng không.
3. Viết `Converter<S,T>` thuần, stateless, deterministic khi chỉ có một cặp kiểu.
4. Đăng ký **đúng conversion service** thay vì tự cho rằng một converter bean áp dụng khắp ứng dụng.
5. Với `@ConfigurationProperties`, ưu tiên `@ConfigurationPropertiesBinding` và static `@Bean`, không inject business bean nặng vào converter.
6. Với MVC, đăng ký vào `FormatterRegistry`; với JSON/JPA, dùng extension point của chúng.
7. Phân biệt lỗi parse/convert với validation và business authorization.
8. Kiểm thử cả unit conversion lẫn Spring integration tại đúng phạm vi.
9. Không log raw secret hoặc dữ liệu nhạy cảm trong exception.
10. Khi cần nhiều ngữ nghĩa khác nhau, thiết kế những target types hoặc registry riêng có chủ đích.

**Kết luận:** Custom Converter là cơ chế mở rộng quan trọng của Spring, nhưng bản thân `Converter<String, RegionCode>` chỉ mô tả cách biến một giá trị thành giá trị khác. **Phạm vi áp dụng được quyết định bởi conversion service/binder nào đã đăng ký và sử dụng converter đó.** Hiểu rõ ranh giới giữa configuration properties, Spring MVC, JSON, persistence và resource loading giúp phép chuyển đổi nhất quán, dễ kiểm thử và không gây side effect ở những nơi không mong muốn.
