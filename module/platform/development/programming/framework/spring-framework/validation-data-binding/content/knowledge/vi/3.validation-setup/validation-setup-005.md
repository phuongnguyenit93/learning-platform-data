# Khai báo ConversionService và tập converter dùng chung trong Spring Framework

Trong Spring Framework, **`ConversionService` là điểm truy cập thống nhất để chuyển giá trị từ một kiểu Java sang kiểu khác**. Thay vì mỗi controller, service hoặc binder tự viết `Integer.parseInt(...)`, chuyển enum hay phân tích một mã nghiệp vụ riêng, ứng dụng có thể khai báo các `Converter` rồi đăng ký chúng vào một `ConversionService`. Nơi nào thực sự sử dụng service đó sẽ có cùng quy tắc chuyển đổi.

Bài này tập trung vào **cách khai báo và tổ chức một tập converter dùng chung**, chọn đúng nơi đăng ký trong Spring container, Spring MVC và Spring Boot, cũng như kiểm chứng quy tắc hoạt động. Ví dụ xuyên suốt: mã đơn hàng đi vào dưới dạng chuỗi `" ord-2026-007 "`, được chuẩn hóa thành kiểu `OrderCode` có giá trị `"ORD-2026-007"`.

## 1. ConversionService giải quyết vấn đề gì?

Trong luồng nhận dữ liệu, các giá trị thường xuất phát từ chuỗi: query parameter `?code=...`, path variable, form field hoặc thuộc tính cấu hình. Code nghiệp vụ lại muốn làm việc với các kiểu có ý nghĩa: `LocalDate`, `UUID`, enum hay `OrderCode`. Spring cần một cơ chế chuyển đổi để liên kết hai thế giới này.

Luồng khái quát cho Spring MVC:

~~~text
HTTP query/path/form (String)
          |
          v
  Spring MVC argument binding
          |
          v
  MVC ConversionService
          |
          v
 Converter<String, OrderCode>
          |
          v
   OrderCode (kiểu nghiệp vụ)
          |
          v
      Controller
~~~

Ở trường hợp truy cập trực tiếp bằng Java, service có thể gọi `conversionService.convert(rawValue, OrderCode.class)`. Điều này giúp quy tắc chuyển đổi có **một nơi định nghĩa** và có thể tái sử dụng tại nhiều điểm nhận dữ liệu.

Tuy nhiên, cần phân biệt:

- **Conversion** chuyển kiểu hoặc diễn giải giá trị, chẳng hạn `String -> OrderCode`.
- **Validation** kiểm tra đối tượng có thỏa quy tắc hay không, chẳng hạn `@NotNull` hoặc một ràng buộc nghiệp vụ.
- **Formatting** chuyển đổi văn bản có xét `Locale` để hiển thị hoặc phân tích giá trị (ngày, tiền tệ, số).
- **JSON deserialization** của `@RequestBody` thường do Jackson/`HttpMessageConverter` thực hiện. Đăng ký một `Converter<String, OrderCode>` trong MVC không đồng nghĩa Jackson sẽ tự dùng nó để đọc JSON body.

Một converter có thể từ chối chuỗi sai định dạng bằng exception, nhưng **không phải** mọi quy tắc validation, phân quyền hoặc trạng thái database đều nên nhét vào converter.

## 2. Các API cần phân biệt

| API | Vai trò | Thường dùng khi nào |
| --- | --- | --- |
| `Converter<S,T>` | Quy tắc chuyển đổi có cặp kiểu nguồn/đích cố định | `String -> OrderCode`, `String -> CustomerId` |
| `ConverterFactory<S,R>` | Tạo converter cho một họ kiểu đích có quan hệ kế thừa | Nhiều kiểu con của một kiểu chung |
| `GenericConverter` | Xử lý nhiều cặp kiểu, có thông tin `TypeDescriptor` | Chuyển đổi cần biết kiểu phần tử/annotation |
| `ConditionalGenericConverter` | Chỉ áp dụng trong điều kiện metadata nhất định | Conversion phụ thuộc đặc điểm kiểu đích |
| `ConversionService` | **Dùng** quy tắc: `canConvert(...)` và `convert(...)` | Controller infrastructure, service, binder |
| `ConverterRegistry` | **Đăng ký** quy tắc bằng `addConverter(...)` | Lúc cấu hình ứng dụng |
| `ConfigurableConversionService` | Kết hợp khả năng chuyển đổi và đăng ký | Khi cần cấu hình và dùng cùng instance |
| `Formatter<T>` / `FormatterRegistry` | Parse/print theo ngôn ngữ, khu vực; đăng ký formatter và converter | Form, ngày, số, tiền tệ |
| `FormatterRegistrar` | Gom các phép đăng ký formatter và converter theo nhóm | Cấu hình một bộ quy tắc nhất quán |

Về thiết kế, **`ConversionService` là giao diện sử dụng**, còn **`ConverterRegistry` là giao diện cấu hình**. Đừng tìm `addConverter(...)` trên biến chỉ có kiểu `ConversionService` vì phương thức đó thuộc registry.

Những implementation đáng biết:

- `GenericConversionService`: nền tảng chuyển đổi tổng quát, cho phép đăng ký converter; một instance mới không tự chứa toàn bộ converter chuẩn.
- `DefaultConversionService`: kế thừa `GenericConversionService` và **đã đăng ký các converter mặc định** cho nhiều kiểu số, enum, collection, chuỗi và kiểu phổ biến.
- `FormattingConversionService`: bổ sung khả năng đăng ký/áp dụng formatter cho trường dữ liệu; phù hợp form và hiển thị phụ thuộc locale.
- `DefaultFormattingConversionService`: cấu hình formatter mặc định cùng khả năng conversion.
- `ApplicationConversionService` của Spring Boot: mở rộng tập chuyển đổi hữu ích cho cấu hình ứng dụng; không được tự coi là chính instance MVC đang dùng.

Một `ConversionService` thông thường được tạo trong giai đoạn khởi tạo ứng dụng và chia sẻ giữa các luồng. **Converter phải không giữ trạng thái thay đổi theo từng request**; nếu cần format tùy locale, dùng `Formatter` thay vì cất locale của request trong field toàn cục.

## 3. “Dùng chung” có hai cấp độ

### 3.1. Dùng chung định nghĩa converter

Tập quy tắc nghiệp vụ như `String -> OrderCode` nên chỉ được **định nghĩa một lần** trong lớp converter. Một lớp đăng ký tập trung có thể thêm các converter đó vào **bất kỳ registry phù hợp**.

~~~text
           DomainConverters.register(registry)
                         |
             +-----------+-----------+
             |                       |
             v                       v
    domainConversionService   Spring MVC FormatterRegistry
    (dùng trong Java code)      (query/path/form binding)
             |                       |
             +-----------+-----------+
                         |
             cùng quy tắc OrderCode
~~~

Hai registry ở sơ đồ có thể là **hai instance khác nhau**. “Dùng chung converter” nghĩa là dùng chung định nghĩa và tập quy tắc, **không** có nghĩa framework tự động chia sẻ một registry cho mọi subsystem.

### 3.2. Dùng chung đúng instance khi cần

Có thể tạo một `ConversionService` bean, inject vào các service cùng `ApplicationContext` và dùng qua `convert(...)`. Spring core container còn hỗ trợ bean có **tên chính xác `conversionService`** để áp dụng khi chuyển đổi thuộc tính bean. Tuy nhiên, việc đặt tên bean này **không tự đảm bảo** Spring MVC, Spring Boot `@ConfigurationProperties` và Jackson JSON đều sử dụng một instance đó.

Trong Spring Boot, nên dùng tên riêng như `domainConversionService` khi chỉ cần conversion cho code nghiệp vụ. Chỉ cấu hình bean tên `conversionService` khi thực sự muốn tác động đến conversion của container/cấu hình và đã xem xét vòng đời khởi tạo sớm, những converter mặc định cần giữ lại.

## 4. Ví dụ hoàn chỉnh: một tập converter, hai nơi sử dụng

Ví dụ dùng **Java 17+, Spring Boot 3.3.x / Spring Framework 6.x** và Gradle. Các phiên bản plugin được cố định bên dưới để ví dụ có cấu hình cụ thể; dự án thực tế nên dùng bộ phiên bản do project quản lý.

Tạo `settings.gradle`:

~~~groovy
rootProject.name = 'conversion-shared-demo'
~~~

Tạo `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    sourceCompatibility = JavaVersion.VERSION_17
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

### 4.1. Khởi động ứng dụng

Tạo `src/main/java/com/example/conversion/ConversionDemoApplication.java`:

~~~java
package com.example.conversion;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ConversionDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConversionDemoApplication.class, args);
    }
}
~~~

### 4.2. Kiểu đích có bất biến riêng

Tạo `src/main/java/com/example/conversion/OrderCode.java`:

~~~java
package com.example.conversion;

import java.util.regex.Pattern;

public record OrderCode(String value) {
    private static final Pattern FORMAT =
            Pattern.compile("ORD-[0-9]{4}-[0-9]{3}");

    public OrderCode {
        if (value == null || !FORMAT.matcher(value).matches()) {
            throw new IllegalArgumentException(
                    "Order code must match ORD-yyyy-nnn");
        }
    }
}
~~~

`OrderCode` là value object. Constructor kiểm tra định dạng để bất kỳ nơi nào tạo object này cũng phải bảo vệ bất biến. Chuyển chữ hoa và bỏ khoảng trắng thuộc trách nhiệm converter; quy tắc về đơn hàng **có thực sự tồn tại hay không** phải được xử lý tại service/repository, không nằm ở đây.

### 4.3. Viết các converter thuần, không giữ trạng thái

Tạo `src/main/java/com/example/conversion/StringToOrderCodeConverter.java`:

~~~java
package com.example.conversion;

import java.util.Locale;
import org.springframework.core.convert.converter.Converter;

public final class StringToOrderCodeConverter
        implements Converter<String, OrderCode> {

    @Override
    public OrderCode convert(String source) {
        String normalized = source.strip().toUpperCase(Locale.ROOT);
        return new OrderCode(normalized);
    }
}
~~~

Tạo `src/main/java/com/example/conversion/OrderCodeToStringConverter.java`:

~~~java
package com.example.conversion;

import org.springframework.core.convert.converter.Converter;

public final class OrderCodeToStringConverter
        implements Converter<OrderCode, String> {

    @Override
    public String convert(OrderCode source) {
        return source.value();
    }
}
~~~

Hai chiều chuyển đổi được khai báo riêng. Dùng `Locale.ROOT` giúp việc chuẩn hóa mã kỹ thuật không phụ thuộc locale mặc định của máy chạy. Constructor `OrderCode` ném `IllegalArgumentException` khi chuỗi sai định dạng; khi gọi qua `ConversionService`, Spring thường bọc lỗi conversion này trong `ConversionFailedException`.

Một `Converter<S,T>` thường nhận nguồn không null; với `null`, `ConversionService` có quy tắc xử lý null riêng. Vì vậy không được dùng converter để bảo đảm trường bắt buộc; quy tắc bắt buộc thuộc bước binding/validation tương ứng.

### 4.4. Đăng ký tập converter dùng chung

Tạo `src/main/java/com/example/conversion/DomainConverters.java`:

~~~java
package com.example.conversion;

import org.springframework.core.convert.converter.ConverterRegistry;

public final class DomainConverters {
    private DomainConverters() {}

    public static void register(ConverterRegistry registry) {
        registry.addConverter(new StringToOrderCodeConverter());
        registry.addConverter(new OrderCodeToStringConverter());
    }
}
~~~

Tập converter giờ được quản lý ở **một điểm đăng ký**. Nếu thêm `StringToCustomerIdConverter`, chỉ cần thêm vào method `register(...)` và kiểm thử các bối cảnh có gọi method này. Đây cũng là nơi phát hiện xung đột khi nhiều converter có cùng cặp kiểu.

Tạo `src/main/java/com/example/conversion/ConversionConfiguration.java`:

~~~java
package com.example.conversion;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.ConversionService;
import org.springframework.core.convert.support.DefaultConversionService;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class ConversionConfiguration implements WebMvcConfigurer {

    @Bean("domainConversionService")
    public ConversionService domainConversionService() {
        DefaultConversionService service = new DefaultConversionService();
        DomainConverters.register(service);
        return service;
    }

    @Override
    public void addFormatters(FormatterRegistry registry) {
        DomainConverters.register(registry);
    }
}
~~~

Chú ý hai chỗ đăng ký:

1. `domainConversionService()` tạo một `DefaultConversionService` có sẵn những converter cơ bản, rồi bổ sung tập nghiệp vụ. Các bean muốn chuyển đổi trực tiếp sẽ inject bean này bằng `@Qualifier("domainConversionService")`.
2. `addFormatters(...)` bổ sung **cùng bộ quy tắc** vào conversion/formatting registry do Spring MVC quản lý. Vì `FormatterRegistry extends ConverterRegistry`, method `register(...)` dùng được trực tiếp. Spring MVC vẫn giữ những formatter/converter mặc định do hạ tầng cấu hình.

Spring Boot MVC còn có khả năng tự đăng ký những bean thuộc `Converter`/`GenericConverter`/`Formatter`. Ví dụ này chủ động dùng `DomainConverters.register(...)` và **không gắn `@Component` lên từng converter**, nhằm có đường đăng ký rõ ràng và tránh trùng lặp. Trong ứng dụng thật, hãy chọn một chiến lược nhất quán.

### 4.5. Dùng trực tiếp `ConversionService` trong một service

Tạo `src/main/java/com/example/conversion/OrderCodeParser.java`:

~~~java
package com.example.conversion;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.convert.ConversionService;
import org.springframework.stereotype.Service;

@Service
public class OrderCodeParser {
    private final ConversionService conversionService;

    public OrderCodeParser(
            @Qualifier("domainConversionService")
            ConversionService conversionService) {
        this.conversionService = conversionService;
    }

    public OrderCode parse(String raw) {
        return conversionService.convert(raw, OrderCode.class);
    }
}
~~~

Bean trên luôn dùng đúng instance đã đăng ký tập quy tắc. Nếu dự án có nhiều bean `ConversionService`, `@Qualifier` giúp lựa chọn chính xác. Với `@Qualifier("domainConversionService")`, chương trình không phải phụ thuộc vào quy tắc đoán bean nào là `@Primary`.

Có thể kiểm tra trước bằng `conversionService.canConvert(String.class, OrderCode.class)`. Kết quả `true` chỉ chứng minh tồn tại đường chuyển kiểu; **không chứng minh mọi chuỗi đầu vào đều hợp lệ**. Việc chuyển giá trị cụ thể vẫn có thể ném lỗi.

### 4.6. Áp dụng tự động khi bind request trong Spring MVC

Tạo `src/main/java/com/example/conversion/OrderController.java`:

~~~java
package com.example.conversion;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public class OrderController {

    public record CheckResponse(String status, String code) {}

    @GetMapping("/check")
    public CheckResponse check(@RequestParam("code") OrderCode code) {
        return new CheckResponse("accepted", code.value());
    }
}
~~~

Tham số `code` là `OrderCode`, dù dữ liệu query trên HTTP là chuỗi. MVC sử dụng converter được đăng ký qua `addFormatters(...)` **trước khi gọi** thân controller.

Nếu dự án có Gradle Wrapper, chạy từ thư mục gốc:

~~~bash
./gradlew bootRun
~~~

Trên Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Gửi request hợp lệ:

~~~bash
curl --get --data-urlencode "code= ord-2026-007 " http://localhost:8080/orders/check
~~~

Kỳ vọng HTTP `200 OK`; JSON có `status = "accepted"` và `code = "ORD-2026-007"`. Không phụ thuộc vào thứ tự các thuộc tính JSON.

Request sai:

~~~bash
curl --get --data-urlencode "code=wrong-code" http://localhost:8080/orders/check
~~~

Kỳ vọng HTTP `400 Bad Request` trong cấu hình MVC mặc định, vì không thể chuyển chuỗi sai thành `OrderCode`. Controller không được gọi. Body lỗi cụ thể phụ thuộc exception handler và cấu hình Spring Boot; ví dụ không tự định nghĩa một JSON lỗi cố định.

Để chuyển đổi chiều ngược lại bằng service Java, `conversionService.convert(new OrderCode("ORD-2026-007"), String.class)` trả về chuỗi `"ORD-2026-007"` theo `OrderCodeToStringConverter`.

## 5. Chọn đúng điểm đăng ký cho từng subsystem

Một ứng dụng Spring Boot có thể có **nhiều conversion service**. Bảng sau phân biệt nơi tác động và cách cấu hình thường dùng:

| Nhu cầu | Vị trí/cách đăng ký | Điều cần nhớ |
| --- | --- | --- |
| Chuyển kiểu từ code Java bất kỳ | Bean `ConversionService` có tên riêng, ví dụ `domainConversionService` | Inject đúng bean; không tự tạo service mới trong từng lần gọi |
| Binding query/path/form ở Spring MVC | `WebMvcConfigurer.addFormatters(FormatterRegistry)` | Không cần thay thế toàn bộ MVC configuration |
| Chuyển đổi thuộc tính bean qua Spring core container | Bean với tên đặc biệt `conversionService` | Có thể ảnh hưởng rộng; giữ converter mặc định và đánh giá thứ tự khởi tạo |
| Bind `@ConfigurationProperties` trong Spring Boot | `@ConfigurationPropertiesBinding` trên converter bean hoặc conversion service dành cho property binder | Converter phục vụ cấu hình có thể được khởi tạo rất sớm |
| Parse/print phụ thuộc `Locale` | `Formatter<T>` trong `FormatterRegistry` | `Converter` đơn thuần không nhận tham số `Locale` |
| JSON `@RequestBody` | Jackson deserializer / `@JsonCreator` / cấu hình `ObjectMapper` phù hợp | `ConversionService` của MVC không tự thay thế Jackson |
| Dữ liệu sai quy tắc nghiệp vụ | Validation/service/domain | Việc chuyển kiểu thành công không đảm bảo dữ liệu hợp lệ về nghiệp vụ |

### 5.1. Nếu thật sự cần bean `conversionService` cho Spring core

Trong ứng dụng Spring không cần tách tên riêng, có thể khai báo:

~~~java
@Bean("conversionService")
public ConversionService conversionService() {
    DefaultConversionService service = new DefaultConversionService();
    DomainConverters.register(service);
    return service;
}
~~~

Đây là **phương án thay thế** cho bean `domainConversionService` ở ví dụ trên, không phải một bean thứ hai nên thêm nguyên xi cạnh nó. Tên `conversionService` có ý nghĩa với core container. Trong Spring Boot cần kiểm tra tác động đến property binding; một bean dùng cho conversion cấu hình có thể được yêu cầu từ giai đoạn rất sớm. Tránh cho factory phụ thuộc database, HTTP client hoặc các bean cần được khởi tạo muộn.

Cũng không nên dùng `new GenericConversionService()` rồi chỉ thêm converter nghiệp vụ nếu ứng dụng vẫn trông đợi các chuyển đổi mặc định: instance này ban đầu không có bộ default converters như `DefaultConversionService`.

### 5.2. Nếu cần `@ConfigurationPropertiesBinding` trong Spring Boot

Một converter dùng để bind thuộc tính cấu hình cần được đăng ký vào cơ chế binder phù hợp, ví dụ method factory bên trong một `@Configuration` class:

~~~java
@Bean
@ConfigurationPropertiesBinding
public static Converter<String, OrderCode> orderCodePropertyConverter() {
    return new StringToOrderCodeConverter();
}
~~~

Đoạn trên cần import `org.springframework.boot.context.properties.ConfigurationPropertiesBinding` và `org.springframework.context.annotation.Bean`; nó minh họa **đăng ký riêng cho property binding**, không phải một file Java độc lập. Khai báo `static @Bean` giúp giảm nguy cơ tạo `@Configuration` instance quá sớm. Nếu dùng cả cách này và tự động đăng ký converter bean trong MVC, cần kiểm tra xem cùng quy tắc có bị đăng ký lặp hay không.

Ví dụ trong `application.yaml`:

~~~yaml
orders:
  default-code: ord-2026-007
~~~

Một class `@ConfigurationProperties(prefix = "orders")` chứa thuộc tính kiểu `OrderCode defaultCode` có thể dùng converter đã đăng ký qua cơ chế property binder. Đây là tình huống khác với MVC `@RequestParam`.

### 5.3. Formatter và Converter không thay nhau trong mọi bài toán

`Converter<String, OrderCode>` phù hợp với mã định danh có một cách chuẩn hóa không phụ thuộc ngôn ngữ. Nhưng nếu người dùng nhập ngày kiểu `31/12/2026` hoặc số có dấu phân cách theo khu vực, việc parse/print cần `Locale`. Khi đó, có thể dùng `Formatter<T>` với hai method `parse(String, Locale)` và `print(T, Locale)` hoặc dùng các formatter mặc định cùng annotation như `@DateTimeFormat` và `@NumberFormat`.

Khi cần gom nhiều formatter vào một nhóm tái sử dụng, `FormatterRegistrar.registerFormatters(FormatterRegistry)` là cấu trúc phù hợp; `FormatterRegistry` cũng cho phép đăng ký converter. Không nên viết converter `String -> String` trên phạm vi toàn ứng dụng chỉ để cắt khoảng trắng của mọi input, vì nó có thể làm thay đổi dữ liệu mà các API khác đang cần giữ nguyên.

## 6. Cơ chế chọn converter và các giới hạn quan trọng

Khi gọi `convert(source, TargetType.class)`, Spring tra cứu converter phù hợp với kiểu nguồn/đích; với các trường hợp phức tạp, Spring sử dụng `TypeDescriptor` để giữ thêm thông tin kiểu collection/element và annotation. Những converter mặc định có thể chuyển collection nếu đã có converter cho các phần tử.

Ví dụ, chỉ dùng `convert(value, List.class)` không truyền được đầy đủ thông tin phần tử đích `OrderCode`. Khi cần chuyển một collection có kiểu phần tử xác định, dùng dạng `convert(Object source, TypeDescriptor sourceType, TypeDescriptor targetType)`, chẳng hạn:

~~~java
List<String> source = List.of("ord-2026-007");
TypeDescriptor inputType = TypeDescriptor.collection(
        List.class, TypeDescriptor.valueOf(String.class));
TypeDescriptor outputType = TypeDescriptor.collection(
        List.class, TypeDescriptor.valueOf(OrderCode.class));

@SuppressWarnings("unchecked")
List<OrderCode> result = (List<OrderCode>)
        conversionService.convert(source, inputType, outputType);
~~~

Đoạn trên giả định đã có `conversionService` và đã import `java.util.List`, `org.springframework.core.convert.TypeDescriptor`; nó minh họa sử dụng `TypeDescriptor`, không phải chương trình độc lập. Khi dùng `DefaultConversionService` với converter phần tử `String -> OrderCode`, collection conversion có thể tái sử dụng converter phần tử đó.

**Một số nguyên tắc chọn converter:**

1. Converter phải có cặp kiểu đủ cụ thể; hạn chế converter quá rộng như `Object -> String` tự viết vì dễ xung đột converter mặc định.
2. Đăng ký trùng cặp kiểu có thể dẫn đến converter mới thay converter cũ hoặc thay đổi kết quả phân giải; đừng dựa vào thứ tự không được quản lý rõ.
3. `canConvert(...)` là kiểm tra khả năng theo kiểu, không phải xác nhận giá trị đầu vào hợp lệ.
4. Converter phải nhanh và xác định, không thực hiện query DB, gọi network hay thay đổi dữ liệu trạng thái nghiệp vụ trong quá trình binding.
5. Ghi nhận rõ policy chuẩn hóa: có cắt khoảng trắng không, có đổi chữ hoa/chữ thường không, dữ liệu Unicode được chấp nhận thế nào. Việc chuẩn hóa mã kỹ thuật có thể đúng, nhưng chuẩn hóa mật khẩu hoặc free-text theo cùng quy tắc có thể là sai.
6. Converter/formatter thường được dùng đồng thời; tránh mutable state, `SimpleDateFormat` dùng chung thiếu đồng bộ hoặc locale lưu vào field.
7. Cấu hình một lần lúc khởi tạo; không thêm/xóa converter khi request đang chạy. Dùng `@Qualifier` nếu trong context có nhiều `ConversionService` và cần lựa chọn rõ.

## 7. Kiểm thử: converter thuần và luồng MVC

Kiểm thử tốt cần chứng minh cả **đúng quy tắc chuyển đổi** và **đã đăng ký vào đúng conversion service**. Ví dụ với dependency `spring-boot-starter-test` ở trên, tạo `src/test/java/com/example/conversion/ConversionIntegrationTest.java`:

~~~java
package com.example.conversion;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.convert.ConversionService;
import org.springframework.core.convert.ConversionFailedException;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class ConversionIntegrationTest {

    @Autowired
    private MockMvc mvc;

    @Autowired
    @Qualifier("domainConversionService")
    private ConversionService conversionService;

    @Test
    void domainRegistryUsesOurConverter() {
        assertTrue(conversionService.canConvert(
                String.class, OrderCode.class));
        assertEquals(
                new OrderCode("ORD-2026-007"),
                conversionService.convert(" ord-2026-007 ", OrderCode.class));
        assertEquals(
                "ORD-2026-007",
                conversionService.convert(
                        new OrderCode("ORD-2026-007"), String.class));

        assertThrows(ConversionFailedException.class,
                () -> conversionService.convert(
                        "wrong-code", OrderCode.class));
    }

    @Test
    void mvcUsesTheSameRuleForRequestParameters() throws Exception {
        mvc.perform(get("/orders/check")
                .param("code", " ord-2026-007 "))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value("ORD-2026-007"));
    }

    @Test
    void mvcRejectsUnconvertibleValue() throws Exception {
        mvc.perform(get("/orders/check")
                .param("code", "wrong-code"))
                .andExpect(status().isBadRequest());
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Ba test chứng minh registry nghiệp vụ hỗ trợ hai chiều, đầu vào không hợp lệ được từ chối và Spring MVC thực sự dùng converter đã cấu hình. Ở môi trường thực, bổ sung ca `null`/query thiếu, khoảng trắng, chữ thường, giá trị giới hạn, địa chỉ locale khác nhau (nếu có formatter) và lỗi khi nhiều converter trùng cặp kiểu.

Các test trên **không kiểm tra JSON `@RequestBody` hay `@ConfigurationProperties`**, vì đây là hai đường chuyển đổi khác cần kiểm thử riêng khi được sử dụng.

## 8. Sai lầm thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra/khắc phục |
| --- | --- | --- |
| `ConversionService.convert(...)` báo không có converter | Chưa đăng ký hoặc inject sai instance | Kiểm tra bean/`@Qualifier` và `canConvert(...)` |
| Service Java chuyển được, nhưng `@RequestParam OrderCode` thất bại | Chỉ thêm vào service nghiệp vụ, chưa cấu hình MVC | Bổ sung qua `WebMvcConfigurer.addFormatters(...)` |
| MVC hoạt động, nhưng `@ConfigurationProperties` không bind | Boot binder dùng cơ chế conversion riêng | Đăng ký đúng `@ConfigurationPropertiesBinding` hoặc cấu hình binder |
| `@RequestBody` JSON không dùng converter MVC | Jackson deserialization là luồng khác | Cấu hình Jackson nếu thật sự cần chuyển kiểu JSON |
| Những kiểu số/ngày phổ biến bỗng không chuyển được | Thay dịch vụ mặc định bằng registry trống hoặc override rộng | Dùng `DefaultConversionService`/formatter service thích hợp, giữ mặc định |
| Bản ghi giá trị sai gây lỗi trong controller | Converter ném exception khi binding | Thiết kế phản hồi HTTP 400 nhất quán, không đưa stack trace ra API |
| Chuỗi trống được chuyển thành null rồi lọt qua nghiệp vụ | Nhầm conversion với validation bắt buộc | Kiểm tra required/`@NotNull`/validation tại ranh giới |
| Behavior khác nhau giữa unit test và HTTP | Unit test tạo service thủ công nhưng MVC chưa có converter | Thêm integration test với application context/MockMvc |
| Kết quả phụ thuộc locale hoặc luồng xử lý | Converter có mutable state hoặc dùng default locale bừa bãi | Dùng `Locale.ROOT` cho mã kỹ thuật hoặc `Formatter` cho locale-sensitive |
| Cấu hình Boot phát sinh cảnh báo khởi tạo sớm | Bean `conversionService`/converter property binding phụ thuộc bean khởi tạo muộn | Giảm dependency; dùng `static @Bean` cho `@ConfigurationPropertiesBinding` khi phù hợp |

## 9. Checklist áp dụng trong dự án

- Xác định **kiểu nguồn, kiểu đích và quy tắc chuẩn hóa**; ưu tiên một converter nhỏ cho một cặp kiểu.
- Gom đăng ký của converter nghiệp vụ vào một nơi như `DomainConverters.register(...)`, có test phát hiện trùng/xung đột.
- Dùng `DefaultConversionService` khi cần một service riêng có chuyển đổi mặc định; tránh làm rỗng registry vô tình.
- Đăng ký đúng scope: Java service, MVC, property binder hay JSON. Cùng quy tắc có thể phải được thêm vào nhiều registry.
- Cấu hình converter stateless và thread-safe; không trộn tra cứu DB, quyền truy cập hoặc transaction vào conversion.
- Giữ validation và error contract riêng; conversion thành công mới là bước đầu của tính hợp lệ.
- Test cả converter trực tiếp và đường binding thực tế; kiểm tra nhập sai, null, locale, loại request và kết quả HTTP.

**Kết luận:** `ConversionService` cung cấp API chuyển kiểu nhất quán; `ConverterRegistry` và `FormatterRegistry` là nơi thêm quy tắc; tập converter dùng chung bảo đảm các đường xử lý **cùng áp dụng một cách diễn giải dữ liệu**. Điều quan trọng trong Spring không chỉ là viết converter đúng mà còn phải **đăng ký nó vào đúng service mà luồng xử lý đang sử dụng**.

### Tài liệu tham khảo

- Spring Framework — Type Conversion: https://docs.spring.io/spring-framework/reference/core/validation/convert.html
- Spring Framework — Field Formatting: https://docs.spring.io/spring-framework/reference/core/validation/format.html
- Spring Framework — MVC Type Conversion: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html
- Spring Boot — MVC Conversion Service: https://docs.spring.io/spring-boot/reference/web/servlet.html
- Spring Boot — Externalized Configuration, Properties Conversion: https://docs.spring.io/spring-boot/reference/features/external-config.html
