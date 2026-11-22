# Ảnh hưởng của bean tên conversionService và cách tránh thay đổi ngoài ý muốn

Trong Spring Boot, việc chuyển một chuỗi từ `application.properties`, YAML, biến môi trường hay đối số dòng lệnh thành `Duration`, `DataSize`, `URI`, enum hoặc kiểu do ứng dụng tự định nghĩa thường diễn ra trong quá trình **binding** của `@ConfigurationProperties`. Spring Boot đã cung cấp những converter mặc định cho rất nhiều kiểu dữ liệu phổ biến.

Khi muốn thêm chuyển đổi riêng, bạn có thể gặp một chi tiết rất quan trọng: **bean có tên chính xác là `conversionService` có ý nghĩa đặc biệt trong cơ chế chuyển đổi thuộc tính cấu hình của Spring Boot**. Một bean như vậy có thể được yêu cầu **rất sớm trong vòng đời khởi động** và có thể làm thay đổi cách những thuộc tính được ép kiểu. Vì thế, việc thêm một bean `ConversionService` rồi vô tình đặt tên `conversionService` không phải quyết định vô hại.

Bài học này phân biệt cơ chế chuyển đổi của Spring Framework và Spring Boot Binder, giải thích tác động của tên bean, tình huống khởi tạo sớm, hậu quả khi làm mất converter có sẵn, cách dùng `@ConfigurationPropertiesBinding` thay cho việc thay đổi converter chung, cách đổi tên service nếu chỉ phục vụ nghiệp vụ và cách kiểm chứng cấu hình không bị ảnh hưởng ngoài dự kiến.

Ví dụ Java sử dụng mô hình Spring Boot 3.x, Java 17+.

## 1. Khái niệm trước khi viết mã

| Thành phần | Vai trò |
| --- | --- |
| `Environment` | Cung cấp key/value hiệu lực từ nhiều `PropertySource` |
| `@ConfigurationProperties` | Định nghĩa nhóm thuộc tính cần bind vào class/record Java |
| Spring Boot `Binder` | Ánh xạ tên key và chuyển value sang kiểu đích |
| `ConversionService` | Giao diện chuyển đổi kiểu của Spring Framework |
| `ApplicationConversionService` | Cài đặt của Spring Boot bao gồm hỗ trợ chuyển đổi/format thường dùng trong ứng dụng |
| Bean tên `conversionService` | Một bean có tên được Spring Boot nhận diện khi cần ConversionService cho configuration properties |
| `@ConfigurationPropertiesBinding` | Qualifier dành cho converter/formatter áp dụng trong ngữ cảnh binding configuration properties |
| Converter nghiệp vụ có tên riêng | Chỉ được dùng tại những chỗ ứng dụng chủ động inject hoặc gọi |

Một câu chốt:

> **Nếu chỉ cần chuyển đổi một kiểu cho `@ConfigurationProperties`, hãy ưu tiên converter được đánh dấu `@ConfigurationPropertiesBinding`. Nếu một `ConversionService` chỉ phục vụ nghiệp vụ, đừng vô tình đặt tên bean là `conversionService`.**

Tên bean là một phần quan trọng của cơ chế này. Không thể chỉ nhìn vào kiểu Java của bean rồi kết luận Spring Boot chắc chắn dùng hoặc không dùng nó cho quá trình bind.

## 2. Luồng binding và vị trí ConversionService

~~~text
application.yml / application.properties
          |
          +-- environment variables
          +-- JVM system properties (-D...)
          +-- command-line arguments (--...)
          +-- profile-specific Config Data
          |
          v
      Environment
          |
          v
      Boot Binder
          |
          +--> tìm property theo prefix và relaxed binding
          |
          +--> chuyển String / value nguồn thành kiểu Java
                  |
                  +-- converter mặc định (String -> Duration, DataSize, ...)
                  |
                  +-- converter chuyên dụng @ConfigurationPropertiesBinding
                  |
                  +-- ConversionService tùy biến được dùng cho binding,
                      nếu ứng dụng cung cấp theo quy tắc Spring Boot
          |
          v
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(Duration timeout, URI endpoint) {}
          |
          v
Bean nghiệp vụ nhận typed configuration
~~~

Ví dụ file:

~~~yaml
app:
  client:
    connect-timeout: 750ms
    endpoint: https://api.example.test
    max-retries: 3
~~~

Model:

~~~java
import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
    Duration connectTimeout,
    URI endpoint,
    int maxRetries
) {}
~~~

Nếu bean được đăng ký đúng cách qua `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`, Binder có thể chuyển `750ms` thành `Duration`, chuỗi URL thành `URI` và `3` thành `int`.

**Thông thường không cần tự tạo bean `conversionService` để làm những phép chuyển đổi này.** Spring Boot có hỗ trợ chuyển kiểu ứng dụng và thuộc tính cấu hình sẵn có.

## 3. Điều gì đặc biệt ở tên bean conversionService?

Spring Framework nhận diện bean theo tên và kiểu trong những tình huống khác nhau. Với Spring Boot configuration properties, tài liệu chính thức nêu khả năng cung cấp **một `ConversionService` bean mang tên `conversionService`** để tùy biến property conversion.

Ví dụ cấu hình sau cố tình tạo bean theo tên quan trọng đó:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.ConversionService;
import org.springframework.core.convert.support.DefaultConversionService;

@Configuration(proxyBeanMethods = false)
public class ConversionConfiguration {

    @Bean
    ConversionService conversionService() {
        return new DefaultConversionService();
    }
}
~~~

Với `@Bean` không chỉ định tên, tên bean mặc định thường lấy từ tên method: ở đây là **`conversionService`**. Tên này không phải một nhãn tùy ý đối với hạ tầng chuyển đổi cấu hình.

Bean `DefaultConversionService` ở ví dụ được tạo để minh họa một rủi ro; nó **không phải mẫu khuyến nghị khi chỉ muốn thêm một phép chuyển đổi nhỏ**. Nó không mặc nhiên mang toàn bộ tập converter/formatter chuyên biệt mà một `ApplicationConversionService` của Spring Boot cung cấp.

### Không phải mọi bean ConversionService đều được dùng theo cùng cách

Hai khai báo sau không giống nhau về naming:

~~~java
@Bean
ConversionService conversionService() {
    return new DefaultConversionService();
}
~~~

~~~java
@Bean
ConversionService reportConversionService() {
    return new DefaultConversionService();
}
~~~

Bean thứ nhất có tên mặc định `conversionService`; bean thứ hai có tên `reportConversionService`. Nếu component chỉ cần service chuyển đổi riêng cho báo cáo và inject bean thứ hai một cách rõ ràng, việc đổi tên giúp tránh trùng tên đặc biệt dành cho infrastructure.

**Đổi tên không có nghĩa bean được cách ly tuyệt đối khỏi mọi cơ chế của Spring.** Nếu bạn đánh dấu `@Primary`, inject theo type vào nơi khác, hoặc một thành phần khác chủ động lấy bean đó, nó vẫn có thể ảnh hưởng nơi đó. Điều cần tránh trước tiên là **vô tình tham gia cơ chế chọn ConversionService của Binder qua tên đặc biệt**.

## 4. Ảnh hưởng thứ nhất: thay đổi conversion dùng khi bind configuration properties

Giả sử ứng dụng có nhiều nhóm cấu hình:

~~~properties
app.client.connect-timeout=2s
app.upload.max-file-size=10MB
app.payment.currency=USD
app.worker.retry-delay=250ms
~~~

Các model có kiểu:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(Duration connectTimeout) {}

@ConfigurationProperties(prefix = "app.upload")
public record UploadProperties(DataSize maxFileSize) {}

@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(Duration retryDelay) {}
~~~

Các loại `Duration` và `DataSize` được Spring Boot hỗ trợ chuyển đổi theo cách quen thuộc trong `@ConfigurationProperties`. Nếu ứng dụng tùy biến quá rộng dịch vụ chuyển đổi và vô tình thay thế hoặc làm mất những converter cần thiết, một thuộc tính vốn bind tốt có thể bắt đầu gây lỗi.

Ví dụ thông báo có thể có dạng:

~~~text
Failed to bind properties under 'app.client.connect-timeout'
to java.time.Duration
~~~

Hoặc:

~~~text
Failed to convert from type [java.lang.String]
to type [org.springframework.util.unit.DataSize]
~~~

**Không phải lỗi bind nào như trên cũng do tên `conversionService`.** Nó cũng có thể phát sinh do value sai cú pháp, dữ liệu trùng nguồn, constructor binding hoặc converter có exception. Nhưng khi lỗi xuất hiện ngay sau một thay đổi về bean `ConversionService`, hãy kiểm tra tên bean và tập converter đã đăng ký.

### Chuyển đổi kiểu không phải thay đổi precedence

Nếu property xuất hiện ở YAML và command line:

~~~properties
# application.properties
app.client.connect-timeout=3s
~~~

~~~bash
java -jar app.jar --app.client.connect-timeout=500ms
~~~

thì cơ chế nguồn cấu hình của Spring Boot quyết định value hiệu lực theo precedence. `ConversionService` chỉ giúp **chuyển value đã được chọn sang kiểu đích**. Nó không tự quyết định một source được ưu tiên hơn source khác.

Đừng cố sửa vấn đề ghi đè property bằng cách đổi ConversionService, và cũng đừng cho rằng một converter mới sẽ thay đổi profile nào được kích hoạt.

## 5. Ảnh hưởng thứ hai: bean được yêu cầu rất sớm

Một cảnh báo trong tài liệu Spring Boot là **những bean dùng cho property conversion có thể được yêu cầu rất sớm trong vòng đời ứng dụng**. Đó là thời điểm ApplicationContext đang thiết lập cơ sở hạ tầng cần thiết để tạo các bean tiếp theo.

Vì vậy, hãy tưởng tượng một `conversionService` phụ thuộc quá nhiều thứ:

~~~java
@Configuration(proxyBeanMethods = false)
public class RiskyConfiguration {

    @Bean
    ConversionService conversionService(
        RemoteCatalogClient remoteCatalogClient,
        TenantRepository tenantRepository,
        ClientProperties clientProperties
    ) {
        // Ví dụ có rủi ro phụ thuộc vào bean khác và
        // @ConfigurationProperties ngay trong quá trình chuẩn bị binding.
        var service = new DefaultConversionService();
        return service;
    }
}
~~~

Đây là **đoạn minh họa thiết kế cần tránh**, không phải ví dụ triển khai. Để tạo ConversionService, Spring phải tạo các dependency tương ứng. Nhưng `ClientProperties` cũng có thể đang cần Binder và ConversionService để được khởi tạo. Kết quả có thể là vòng phụ thuộc, bean bị tạo sớm ngoài mong muốn, hoặc một thành phần chưa được xử lý đầy đủ bởi những `BeanPostProcessor` dự kiến.

Ngay cả khi không có vòng phụ thuộc trực tiếp, gọi database, HTTP service, cache, hoặc đọc cấu hình nghiệp vụ phức tạp trong factory method tạo `conversionService` là rủi ro không cần thiết.

### Dấu hiệu vấn đề do early initialization

- Startup thất bại với lỗi thiếu bean hoặc vòng phụ thuộc, dù dependency đó vẫn được dùng bình thường ở những chỗ khác.
- Log xuất hiện cảnh báo một bean **không đủ điều kiện được tất cả `BeanPostProcessor` xử lý**.
- Chức năng phụ thuộc proxy, annotation hoặc auto-configuration có hành vi khác sau khi thêm custom converter.
- Lỗi xuất hiện rất sớm, trước khi service nghiệp vụ của bạn được khởi tạo.
- Chỉ những lần startup có cấu hình conversion tùy biến mới gặp lỗi.

Các dấu hiệu này chưa đủ để kết luận tuyệt đối; hãy đọc stack trace và dependency chain thực tế.

## 6. Ảnh hưởng thứ ba: phạm vi chuyển đổi có thể rộng hơn dự tính

Một ứng dụng có thể cần converter riêng để hiển thị báo cáo, nhưng lại vô tình tạo một bean có tên toàn cục. Ví dụ một module chỉ muốn chuyển `String -> ReportStatus`:

~~~java
public enum ReportStatus {
    NEW, RUNNING, DONE
}
~~~

Bạn có thể định nghĩa một `ConversionService` riêng để chuyển dữ liệu báo cáo trong code. Tuy nhiên, nếu bean đó mang tên `conversionService` thì nó có thể được infrastructure nhận diện để phục vụ cả conversion của configuration properties.

Phạm vi thay đổi ngoài dự kiến có thể biểu hiện ở:

- Các bean `@ConfigurationProperties` khác bắt đầu nhận cách chuyển đổi mới hoặc lỗi do thiếu converter cũ.
- Component sử dụng bean `conversionService` theo tên cũng nhận hành vi mới.
- Một số cơ chế Spring khác có thể tương tác với bean `ConversionService` được đưa vào context, tùy subsystem và cấu hình cụ thể.

Cần diễn đạt chính xác: **không phải cứ có bean `conversionService` thì mọi chuyển đổi của MVC, JSON, database và tất cả thư viện lập tức dùng nó**. Những hệ thống đó có thể có converter registry và cơ chế cấu hình riêng. Rủi ro cụ thể cần xét là **bean nào sử dụng ConversionService đó**; với Spring Boot property binding, tên `conversionService` là tín hiệu quan trọng.

### So sánh một converter và một registry toàn cục

| Bạn muốn sửa | Nên tác động đến |
| --- | --- |
| Chuyển một type trong `@ConfigurationProperties` | Converter được qualify bằng `@ConfigurationPropertiesBinding` |
| Chuyển dữ liệu theo luật riêng trong một service | Converter hoặc ConversionService có tên riêng, inject rõ ràng |
| Chuyển field input của Spring MVC | Cơ chế `Formatter`/`Converter` của MVC (ví dụ `WebMvcConfigurer#addFormatters`) |
| Chuyển JSON | Cấu hình serialization/deserialization của Jackson |
| Thay đổi chính sách chuyển kiểu cho nhiều configuration properties | Xem xét ConversionService dành cho binding, có chủ đích và có kiểm thử |
| Đổi nguồn value thắng trong YAML/profile | Xem Config Data/PropertySource precedence, không sửa converter |

## 7. Cách an toàn phổ biến: @ConfigurationPropertiesBinding

Nếu chỉ cần một phép chuyển đổi riêng cho configuration properties, bạn có thể đăng ký **một converter cụ thể** với qualifier `@ConfigurationPropertiesBinding` thay vì thay thế toàn bộ registry.

Giả sử cấu hình có một mã vùng như `ap-southeast-1` và ứng dụng muốn dùng type riêng:

~~~properties
app.routing.default-region=ap-southeast-1
~~~

Một value object:

~~~java
package com.example.orders.config;

public record RegionCode(String value) {
    public RegionCode {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "RegionCode must not be blank");
        }
    }
}
~~~

Một converter tách biệt:

~~~java
package com.example.orders.config;

import org.springframework.core.convert.converter.Converter;

public final class StringToRegionCodeConverter
        implements Converter<String, RegionCode> {

    @Override
    public RegionCode convert(String source) {
        return new RegionCode(source.trim());
    }
}
~~~

Đăng ký converter cho configuration properties:

~~~java
package com.example.orders.config;

import org.springframework.boot.context.properties.ConfigurationPropertiesBinding;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;

@Configuration(proxyBeanMethods = false)
public class RegionBindingConfiguration {

    @Bean
    @ConfigurationPropertiesBinding
    public static Converter<String, RegionCode>
            regionCodeConfigurationConverter() {
        return new StringToRegionCodeConverter();
    }
}
~~~

Trong ví dụ này, `RegionBindingConfiguration` cần thực sự được Spring xử lý, ví dụ nằm trong phạm vi component scan của ứng dụng hoặc được import theo một cấu hình khác.

Record có thể bind:

~~~java
package com.example.orders.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.routing")
public record RoutingProperties(
    RegionCode defaultRegion
) {}
~~~

Khi `RoutingProperties` được scan/enable đúng cách, Binder có thể dùng converter chuyên dụng để tạo `RegionCode` từ chuỗi `ap-southeast-1`.

### Vì sao cách này có phạm vi rõ hơn?

`@ConfigurationPropertiesBinding` đánh dấu converter **phục vụ việc bind các thuộc tính cấu hình**. Bạn không cần đưa vào context một registry chuyển đổi `conversionService` mới cho toàn bộ ứng dụng. Các converter mặc định vẫn có thể được sử dụng cho những kiểu khác theo cơ chế của Spring Boot.

Nếu converter chỉ liên quan đến `RegionCode`, việc đặt logic trong `Converter<String, RegionCode>` cũng làm phạm vi của thay đổi dễ nhìn thấy hơn so với tùy chỉnh một registry tổng quát.

### Qualifier không có nghĩa converter chỉ chạy cho một key

Một converter `Converter<String, RegionCode>` có thể được dùng ở **mọi vị trí configuration properties cần chuyển `String` thành `RegionCode`**, không chỉ `app.routing.default-region`. Nếu muốn có ý nghĩa khác nhau cho cùng kiểu Java nhưng theo từng property path, hãy thiết kế type riêng hoặc tổ chức contract rõ ràng; đừng mặc định rằng converter biết key gốc là gì.

## 8. Vì sao @Bean @ConfigurationPropertiesBinding nên là static?

Tài liệu Spring Boot khuyến nghị **phương thức `@Bean` được annotate `@ConfigurationPropertiesBinding` nên là `static`**, nhằm tránh cảnh báo liên quan đến bean được khởi tạo quá sớm, chưa được mọi `BeanPostProcessor` xử lý.

Ví dụ khuyến nghị:

~~~java
@Configuration(proxyBeanMethods = false)
public class BindingConverters {

    @Bean
    @ConfigurationPropertiesBinding
    public static Converter<String, RegionCode>
            regionCodeConverter() {
        return new StringToRegionCodeConverter();
    }
}
~~~

`static` ở đây áp dụng cho **factory method của bean converter**. Nó không có nghĩa record `RegionCode`, class `StringToRegionCodeConverter` hoặc mọi method của ứng dụng đều phải là `static`.

### Ví dụ dễ gặp cảnh báo

~~~java
@Configuration(proxyBeanMethods = false)
public class BindingConverters {

    private final TenantService tenantService;

    public BindingConverters(TenantService tenantService) {
        this.tenantService = tenantService;
    }

    @Bean
    @ConfigurationPropertiesBinding
    public Converter<String, RegionCode> regionCodeConverter() {
        return value -> tenantService.resolveRegion(value);
    }
}
~~~

Đây là ví dụ **có rủi ro**. Factory method là instance method nên cần khởi tạo `BindingConverters`, đồng thời kéo theo `TenantService`. Binding converter lại được yêu cầu sớm; đường tạo bean có thể phức tạp hoặc phát sinh cảnh báo.

Cách làm an toàn hơn là **giữ converter thuần, không có dependency ứng dụng**, và đăng ký qua static factory method:

~~~java
@Bean
@ConfigurationPropertiesBinding
public static Converter<String, RegionCode> regionCodeConverter() {
    return source -> new RegionCode(source.trim());
}
~~~

Khi công việc chuyển đổi thật sự cần gọi API hoặc repository, hãy cân nhắc lại ranh giới trách nhiệm: configuration binding nên parse/validate dữ liệu; truy vấn nghiệp vụ hoặc làm giàu dữ liệu nên thực hiện trong một service được khởi tạo sau khi cấu hình đã sẵn sàng.

## 9. Ví dụ YAML và Java hoàn chỉnh không thay conversionService

Giả sử muốn bind một danh sách endpoint cấu hình, trong đó mỗi endpoint có một `RegionCode` tự định nghĩa và một `Duration` mặc định của Boot:

~~~yaml
app:
  routing:
    endpoints:
      - name: primary
        region: ap-southeast-1
        url: https://primary.example.test
        timeout: 500ms
      - name: backup
        region: eu-west-1
        url: https://backup.example.test
        timeout: 2s
~~~

Model:

~~~java
package com.example.orders.config;

import java.net.URI;
import java.time.Duration;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.routing")
public record RoutingProperties(
    List<Endpoint> endpoints
) {
    public record Endpoint(
        String name,
        RegionCode region,
        URI url,
        Duration timeout
    ) {}
}
~~~

Converter chuyên dụng `StringToRegionCodeConverter` và `RegionBindingConfiguration` giữ nguyên như ví dụ ở phần trước.

Main class:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Consumer:

~~~java
package com.example.orders.service;

import com.example.orders.config.RoutingProperties;
import org.springframework.stereotype.Service;

@Service
public class RoutingService {
    private final RoutingProperties properties;

    public RoutingService(RoutingProperties properties) {
        this.properties = properties;
    }

    public void printEndpointRegions() {
        for (var endpoint : properties.endpoints()) {
            System.out.println(
                endpoint.name() + ": " + endpoint.region().value());
        }
    }
}
~~~

Nếu những bean nói trên nằm trong phạm vi scan/registration, Binder sử dụng converter custom cho `RegionCode` và converter mặc định phù hợp cho `Duration`/`URI`. Không có nhu cầu tạo bean tên `conversionService` chỉ vì một field kiểu `RegionCode`.

### Tại sao ví dụ này đáng chú ý?

Ứng dụng đang dùng **cả conversion có sẵn và conversion tự định nghĩa trong cùng một object**:

- `String -> RegionCode`: custom converter cho configuration binding.
- Chuỗi `500ms`/`2s` thành `Duration`: conversion mặc định của Boot.
- Chuỗi URL thành `URI`: conversion thích hợp của framework.

Việc thêm converter nhỏ không yêu cầu thay toàn bộ conversion registry. Đây là cách giữ diện ảnh hưởng hẹp.

## 10. Khi nào mới cân nhắc bean tên conversionService?

Có những tình huống ứng dụng cần **toàn quyền kiểm soát một `ConversionService` phục vụ property conversion**: bổ sung nhiều converter và formatter với một chính sách tập trung, thay đổi conversion behavior được xác định rõ, hoặc có một framework nội bộ phụ trách mô hình chuyển đổi.

Khi đó việc cung cấp bean tên `conversionService` có thể là quyết định hợp lệ. Nhưng cần xác định rõ:

1. **Vì sao** converter/formatter chuyên dụng không đáp ứng được?
2. Bean được dùng bởi **những subsystem nào**?
3. Cần giữ lại các **converter phổ biến của Spring Boot** nào?
4. Bean có **phụ thuộc khởi tạo sớm** vào các service hoặc properties bean khác không?
5. Có kiểm thử để ngăn việc `Duration`, `DataSize`, enum, collections và các typed properties khác bị ảnh hưởng không?
6. Tên bean và cách register có được coi là quyết định API vận hành, thay vì chi tiết implementation tạm thời không?

Một hướng minh họa nếu chủ động tùy biến conversion cho application properties:

~~~java
import org.springframework.boot.convert.ApplicationConversionService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.support.ConfigurableConversionService;

@Configuration(proxyBeanMethods = false)
public class BroadConversionConfiguration {

    @Bean(name = "conversionService")
    public static ConfigurableConversionService conversionService() {
        ApplicationConversionService service =
            new ApplicationConversionService();

        service.addConverter(new StringToRegionCodeConverter());
        return service;
    }
}
~~~

Mẫu này **chỉ phù hợp khi bạn có chủ đích cung cấp registry có tên `conversionService`**. Nó dùng `ApplicationConversionService` làm nền để giữ các converter/formatter ứng dụng thông dụng của Spring Boot, rồi bổ sung converter mong muốn. Nếu toàn bộ nhu cầu chỉ là `RegionCode` trong `@ConfigurationProperties`, vẫn nên chọn `@ConfigurationPropertiesBinding` ở phần trước.

Không phải mọi lớp ứng dụng được phép tùy ý thêm converters vào ConversionService chung. Với một hệ thống lớn, hãy phân công rõ module nào sở hữu bean tên `conversionService` để tránh xung đột định nghĩa hoặc thay đổi hành vi xuyên module.

## 11. Sự khác nhau giữa DefaultConversionService và ApplicationConversionService

Một điểm kỹ thuật quan trọng:

~~~java
new DefaultConversionService()
~~~

và:

~~~java
new ApplicationConversionService()
~~~

không có cùng mục tiêu hoàn toàn.

`DefaultConversionService` là implementation cơ bản của Spring Framework, cung cấp những converter phổ biến của framework. `ApplicationConversionService` của Spring Boot xây dựng trên cơ sở đó và thêm hỗ trợ conversion/format được Spring Boot sử dụng trong ngữ cảnh ứng dụng.

Ví dụ Boot thường hỗ trợ cấu hình:

~~~properties
app.retry.delay=250ms
app.upload.max-size=10MB
~~~

để bind sang:

~~~java
@ConfigurationProperties(prefix = "app.retry")
public record RetryProperties(Duration delay) {}

@ConfigurationProperties(prefix = "app.upload")
public record UploadProperties(DataSize maxSize) {}
~~~

Nếu tạo một ConversionService quá đơn giản rồi giao nó cho cơ sở hạ tầng conversion, bạn có nguy cơ làm mất một số kiểu chuyển đổi mà app đang trông đợi. Không nên thay registry chỉ để thêm một converter không liên quan.

### Điều này có nghĩa DefaultConversionService luôn sai?

Không. Nó vẫn hữu ích trong nhiều thành phần Spring Framework và có thể phù hợp cho một conversion service **riêng** của nghiệp vụ. Vấn đề là **ngữ cảnh sử dụng và tên bean**, không phải `DefaultConversionService` là class bị cấm.

Một registry báo cáo được dùng thủ công vẫn có thể hợp lệ:

~~~java
@Bean("reportConversionService")
ConversionService reportConversionService() {
    return new DefaultConversionService();
}
~~~

Nếu chỉ cần converter nhỏ, có thể còn đơn giản hơn khi inject trực tiếp `Converter<A,B>` vào service thay vì tạo cả registry.

## 12. Đổi tên bean để tránh tham gia binding cấu hình

Giả sử bạn cần service convert cho dữ liệu trong một module báo cáo. Không muốn bean này chi phối `@ConfigurationProperties`. Thay vì:

~~~java
@Bean
ConversionService conversionService() {
    return new DefaultConversionService();
}
~~~

hãy đặt tên có ý nghĩa:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.ConversionService;
import org.springframework.core.convert.support.DefaultConversionService;

@Configuration(proxyBeanMethods = false)
public class ReportConversionConfiguration {

    @Bean("reportConversionService")
    ConversionService reportConversionService() {
        return new DefaultConversionService();
    }
}
~~~

Consumer inject rõ bean:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.convert.ConversionService;
import org.springframework.stereotype.Service;

@Service
public class ReportValueMapper {
    private final ConversionService conversions;

    public ReportValueMapper(
        @Qualifier("reportConversionService")
        ConversionService conversions
    ) {
        this.conversions = conversions;
    }

    public Integer parseInteger(String value) {
        return conversions.convert(value, Integer.class);
    }
}
~~~

Tên `reportConversionService` giúp truyền đạt đây là hạ tầng của module báo cáo, không phải service chuyển đổi mặc định của framework.

**Chỉ đổi tên method cũng có thể đổi tên bean mặc định**, nếu `@Bean` không chỉ định name. Nhưng cách ghi `@Bean("reportConversionService")` làm ý định rõ ràng và ít phụ thuộc việc refactor method name.

### Đừng dùng @Primary như một phương án cách ly

`@Primary` thường ảnh hưởng resolution bean khi inject theo type. Nó không phải biện pháp “không bao giờ được framework sử dụng”. Khi muốn tách biệt rõ, dùng tên riêng và `@Qualifier`; khi muốn converter chỉ phục vụ binding, dùng `@ConfigurationPropertiesBinding`.

## 13. Trường hợp dùng @Component trên Converter

Có thể viết:

~~~java
@Component
public class StringToRegionCodeConverter
        implements Converter<String, RegionCode> {
    @Override
    public RegionCode convert(String value) {
        return new RegionCode(value.trim());
    }
}
~~~

Việc một converter được component scan tìm thấy **không tự nói rõ nó sẽ được đăng ký vào converter registry nào và lúc nào**. Cơ chế của một subsystem có thể tự khám phá Converter beans; subsystem khác lại yêu cầu qualifier hoặc registration tường minh.

Nếu mục tiêu rất cụ thể là configuration properties binding, cách rõ ràng là dùng `@ConfigurationPropertiesBinding` cùng cơ chế bean registration tương ứng (ví dụ static `@Bean`).

Nếu mục tiêu là MVC, hãy đăng ký trong cấu hình MVC thích hợp. Nếu mục tiêu là nghiệp vụ, inject converter hoặc dùng service riêng. **Đừng chỉ thêm `@Component` rồi giả định mọi vị trí tự đổi theo converter mới.**

## 14. Phân biệt conversion của @ConfigurationProperties và @Value

Hai cơ chế đều có thể đọc từ `Environment`, nhưng không có cùng đầy đủ tính năng.

`@ConfigurationProperties` sử dụng Binder với relaxed binding và type conversion dành cho cấu hình. `@Value` là cơ chế injection của Spring Core, có thể giải quyết placeholder và SpEL, và không bảo đảm dùng cùng một converter custom chỉ vì converter đã được qualify bằng `@ConfigurationPropertiesBinding`.

Ví dụ:

~~~properties
app.routing.default-region=ap-southeast-1
~~~

Với converter chuyên dụng như `StringToRegionCodeConverter`:

~~~java
@ConfigurationProperties(prefix = "app.routing")
public record RoutingProperties(RegionCode defaultRegion) {}
~~~

là use case chính.

Nếu một component lại viết:

~~~java
@Value("\${app.routing.default-region}")
private RegionCode region;
~~~

thì đừng mặc định rằng converter chỉ dành cho configuration properties binding luôn được `@Value` injection sử dụng. Nếu cần tương thích cả hai, hãy thiết kế conversion ở phạm vi và cơ chế thực sự được mỗi đường gọi hỗ trợ, hoặc inject typed `RoutingProperties` thay vì dùng `@Value` rải rác.

**Cách dễ duy trì hơn:** consumer inject bean `RoutingProperties`, rồi đọc `routingProperties.defaultRegion()`. Bạn sẽ tránh việc hai đường injection có conversion behavior khác nhau.

## 15. Không trộn chuyển đổi với nghiệp vụ hoặc I/O

Một converter lý tưởng nên có các đặc tính:

- Không phụ thuộc database hoặc HTTP client.
- Không gọi network hoặc file system trong mỗi lần parse.
- Không yêu cầu một `@ConfigurationProperties` bean khác để có thể khởi tạo.
- Không chứa state thay đổi theo request.
- Cho cùng input hợp lệ một output ổn định.
- Với input không hợp lệ, ném exception rõ ràng để cấu hình bị từ chối sớm.

Ví dụ converter thuần:

~~~java
public final class StringToPortRangeConverter
        implements Converter<String, PortRange> {

    @Override
    public PortRange convert(String source) {
        String[] parts = source.split("-", 2);
        if (parts.length != 2) {
            throw new IllegalArgumentException(
                "Expected start-end, e.g. 8000-8010");
        }
        int start = Integer.parseInt(parts[0].trim());
        int end = Integer.parseInt(parts[1].trim());
        if (start < 1 || end > 65535 || start > end) {
            throw new IllegalArgumentException(
                "Port range must be within 1..65535");
        }
        return new PortRange(start, end);
    }
}
~~~

Đây là converter tự đủ dữ liệu đầu vào. Nếu muốn kết quả `PortRange` kiểm tra quyền tenant, quota hoặc sự tồn tại của cluster, làm bước đó trong tầng service hoặc validation chuyên biệt sau khi typed settings đã sẵn sàng, tránh kéo theo dependency lifecycle phức tạp vào conversion.

## 16. Sử dụng Formatter thay vì Converter khi nào?

`Converter<S,T>` phù hợp khi một chuyển đổi có input type và target type rõ ràng, ví dụ `String -> RegionCode`. `Formatter<T>` phù hợp trong những bài toán cần parse/print dựa trên locale hoặc ngữ nghĩa trình bày.

Nhưng phải phân biệt **đăng ký formatter trong MVC** với **đăng ký converter cho configuration properties**.

Ví dụ một formatter phục vụ dữ liệu form với locale cụ thể thường được thêm trong Spring MVC qua `WebMvcConfigurer#addFormatters`, không nhất thiết phải thay bean tên `conversionService` của toàn ApplicationContext.

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class WebFormattingConfiguration
        implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToRegionCodeConverter());
    }
}
~~~

Đây là ví dụ dành cho **MVC conversion** khi component có mục tiêu tương ứng; không đồng nghĩa với việc converter này được đăng ký cho `@ConfigurationProperties`.

Nếu cùng một phép chuyển đổi cần ở cả hai nơi, có thể đăng ký cùng implementation vào hai registry có chủ đích, nhưng tránh suy luận rằng chỉ cần một bean tên `conversionService` là mọi subsystem sẽ thống nhất tự động.

## 17. Một lỗi giả định: tạo ConversionService vì cần một converter riêng

Giả sử dự án đang chạy ổn với:

~~~yaml
app:
  retry:
    backoff: 300ms
  storage:
    quota: 50MB
~~~

Typed configs:

~~~java
@ConfigurationProperties(prefix = "app.retry")
public record RetryProperties(Duration backoff) {}

@ConfigurationProperties(prefix = "app.storage")
public record StorageProperties(DataSize quota) {}
~~~

Developer muốn hỗ trợ thêm `RegionCode`, nên thêm:

~~~java
@Configuration(proxyBeanMethods = false)
public class CustomConversionConfiguration {

    @Bean("conversionService")
    ConversionService conversionService() {
        DefaultConversionService service =
            new DefaultConversionService();
        service.addConverter(new StringToRegionCodeConverter());
        return service;
    }
}
~~~

**Rủi ro:** bean có tên chính xác `conversionService` có thể được dùng cho configuration conversion, trong khi implementation chọn ở đây không nhất thiết giữ được toàn bộ converter/formatter chuyên biệt của Boot. Việc chỉ thêm một converter nay có diện ảnh hưởng lớn hơn dự tính.

### Cách sửa được ưu tiên

~~~java
@Configuration(proxyBeanMethods = false)
public class CustomConversionConfiguration {

    @Bean
    @ConfigurationPropertiesBinding
    public static Converter<String, RegionCode> regionCodeConverter() {
        return new StringToRegionCodeConverter();
    }
}
~~~

Sau thay đổi này, bạn không chủ động cung cấp registry có tên đặc biệt. Converter được khai báo theo đúng nhu cầu configuration binding, giảm nguy cơ ảnh hưởng đến typed properties không liên quan.

Nếu toàn ứng dụng thật sự cần conversion service custom, hãy giữ những converter quan trọng từ Boot làm nền và kiểm chứng các kiểu cấu hình đang có trước khi thay rộng.

## 18. Một lỗi giả định: ConversionService phụ thuộc vào bean đang được bind

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
class ConversionConfiguration {

    @Bean("conversionService")
    ConversionService conversionService(RoutingProperties routing) {
        // routing là configuration properties bean,
        // có thể cần Binder để được tạo.
        return new DefaultConversionService();
    }
}
~~~

Phụ thuộc này có dạng:

~~~text
Khởi tạo hạ tầng conversion
      -> cần RoutingProperties
             -> cần Binder
                    -> có thể cần hạ tầng conversion
~~~

Một startup path như vậy có nguy cơ tạo vòng phụ thuộc hoặc thứ tự tạo bean không mong muốn. Tài liệu Spring Boot khuyến nghị **giới hạn dependencies của ConversionService** vì nó được yêu cầu sớm.

**Cách giải quyết thường gặp:** converter thuần, static factory method, không phụ thuộc typed properties khác. Nếu logic cần `RoutingProperties`, hãy thực hiện sau bước bind, trong bean nghiệp vụ.

Một service cần config và conversion nghiệp vụ có thể nhận cả hai qua constructor injection bình thường:

~~~java
@Service
public class RoutePlanner {

    private final RoutingProperties settings;
    private final RouteCatalog catalog;

    public RoutePlanner(
        RoutingProperties settings,
        RouteCatalog catalog
    ) {
        this.settings = settings;
        this.catalog = catalog;
    }
}
~~~

`RouteCatalog` là type nghiệp vụ minh họa, cần có bean phù hợp. Chỗ này là **sau** khi typed settings đã được tạo, không phải factory tạo ConversionService infrastructure.

## 19. Đổi tên ConversionService nếu chỉ dùng trong service

Nếu một module đang có:

~~~java
@Bean
ConversionService conversionService() {
    return new DefaultConversionService();
}
~~~

và không hề có chủ đích tác động tới configuration keys coercion, hãy chuyển sang:

~~~java
@Bean("analyticsConversionService")
ConversionService analyticsConversionService() {
    return new DefaultConversionService();
}
~~~

Ở nơi cần, inject tường minh:

~~~java
public AnalyticsImporter(
    @Qualifier("analyticsConversionService")
    ConversionService conversions
) {
    this.conversions = conversions;
}
~~~

Lợi ích:

- Giảm nguy cơ BeanFactory chọn nhầm bean chỉ vì tên mặc định `conversionService`.
- Tách biệt cách conversion phục vụ analytics với typed configuration.
- Dễ tìm consumer của conversion service qua qualifier.
- Dễ test module theo đúng contract thay vì kiểm hàng loạt loại cấu hình khác.
- Tránh đóng một quyết định infrastructure vào method name không được review.

### Đừng đổi tên trong khi một consumer khác đang phụ thuộc tên cũ

Nếu mã khác inject bean `conversionService` qua `@Qualifier("conversionService")` hoặc lookup theo tên, đổi tên sẽ ảnh hưởng consumer đó. Việc đổi tên cần được thực hiện có chủ đích cùng với cập nhật injection tương ứng. Không coi đó là một thay đổi vô hại đối với application public contract.

## 20. Cách kiểm tra bean có tên conversionService không

Trong ứng dụng thử nghiệm, có thể liệt kê tên bean `ConversionService` từ `ApplicationContext`:

~~~java
import java.util.Arrays;

import org.springframework.boot.CommandLineRunner;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.ConversionService;

@Configuration(proxyBeanMethods = false)
public class ConversionProbeConfiguration {

    @Bean
    CommandLineRunner showConversionBeans(
        ApplicationContext context
    ) {
        return args -> {
            String[] names =
                context.getBeanNamesForType(ConversionService.class);
            System.out.println(
                "ConversionService beans: " + Arrays.toString(names));
            System.out.println(
                "Has bean named conversionService: "
                    + context.containsBean("conversionService"));
        };
    }
}
~~~

Đây là một probe để hiểu các bean definition trong context; chạy trong môi trường phát triển hoặc test. Nếu cần điều tra thứ tự khởi tạo, có thể dùng logging phù hợp và đọc stack trace. Không bật log chi tiết hay in toàn bộ `Environment` trên production chỉ vì muốn biết một bean có tồn tại.

**Lưu ý:** `containsBean("conversionService")` kiểm tra sự tồn tại tên/alias theo cơ chế BeanFactory; nó không chứng minh chỉ một service thực sự được dùng ở mọi subsystem. Để biết nguồn conversion nào đang được một Binder path sử dụng, cần kiểm chứng hành vi binding cụ thể.

## 21. Test converter chuyên dụng với ApplicationContextRunner

Một test nhỏ có thể giúp xác minh converter được đăng ký đúng cho configuration properties. Ví dụ sử dụng Spring Boot test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import com.example.orders.config.RegionCode;
import com.example.orders.config.RegionBindingConfiguration;
import com.example.orders.config.RoutingProperties;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.context.properties.ConfigurationPropertiesBinding;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class RegionBindingTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(
                TestConfiguration.class,
                RegionBindingConfiguration.class
            )
            .withPropertyValues(
                "app.routing.default-region=ap-southeast-1"
            );

    @Test
    void usesDedicatedConverter() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(RoutingProperties.class);
            RegionCode region = context
                .getBean(RoutingProperties.class)
                .defaultRegion();
            assertThat(region.value()).isEqualTo("ap-southeast-1");
        });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(RoutingProperties.class)
    static class TestConfiguration {}
}
~~~

Test giả định `RegionBindingConfiguration` đăng ký converter static `@Bean @ConfigurationPropertiesBinding` như phần trước và dependency `spring-boot-starter-test` được khai báo.

Nếu custom converter là lambda trả về một type hiếm gặp, nên xác minh Binder thực sự dùng converter thay vì một phép chuyển đổi mặc định tình cờ cho cùng type. Cách kiểm tra đó thuộc test chức năng trong dự án, không liên quan đến việc có hay không một bean name đặc biệt.

## 22. Test regression cho các kiểu mặc định

Khi dự án cần custom conversion, điều quan trọng là không làm hỏng các kiểu vẫn được Boot hỗ trợ trước đó.

Một class test configuration properties:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.util.unit.DataSize;

@ConfigurationProperties(prefix = "app.testing")
public record StandardTypeProperties(
    Duration timeout,
    DataSize limit,
    int maxRetries
) {}
~~~

Một test tích hợp:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.util.unit.DataSize;

@SpringBootTest(properties = {
    "app.testing.timeout=1500ms",
    "app.testing.limit=10MB",
    "app.testing.max-retries=4"
})
class ConversionRegressionTest {

    @Autowired
    StandardTypeProperties values;

    @Test
    void standardTypeConversionStillWorks() {
        assertThat(values.timeout())
            .isEqualTo(Duration.ofMillis(1500));
        assertThat(values.limit())
            .isEqualTo(DataSize.ofMegabytes(10));
        assertThat(values.maxRetries()).isEqualTo(4);
    }
}
~~~

Test giả định `StandardTypeProperties` đã được register bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`. Nó kiểm các hành vi quan trọng bên cạnh converter custom. Nếu một thay đổi bean tên `conversionService` khiến test bắt đầu lỗi, đây là dấu hiệu cần xem lại conversion registry hoặc cơ chế đăng ký.

### Kiểm tra converter custom và converter mặc định cùng nhau

Một test tốt trong dự án có thể khai báo cả:

~~~properties
app.routing.default-region=ap-southeast-1
app.testing.timeout=1500ms
app.testing.limit=10MB
~~~

và xác minh `RegionCode` bind được, `Duration` bind được, `DataSize` bind được. Mục tiêu là phát hiện thay đổi ngoài dự kiến ở nơi tưởng không liên quan khi sửa converter.

## 23. Quy trình xử lý sự cố lúc startup

Nếu thêm converter rồi ứng dụng không khởi động:

**Bước 1 — Xác định lỗi xảy ra trước hay sau binding.** Nếu lỗi là vòng phụ thuộc hoặc bean không được xử lý đầy đủ, kiểm dependency graph của `ConversionService`. Nếu là “Failed to bind”, kiểm conversion, source value và target type.

**Bước 2 — Kiểm chính xác tên bean.** Có một `@Bean` method tên `conversionService()` hoặc `@Bean("conversionService")` không? Có bean từ module khác mang tên đó không?

**Bước 3 — Xác định intent.** Bean này cần thay thế conversion cho configuration properties hay chỉ phục vụ controller, UI, report, import dữ liệu?

**Bước 4 — Nếu chỉ cần custom binding, dùng `@ConfigurationPropertiesBinding`.** Đăng ký converter thuần, ưu tiên static bean method, tránh một ConversionService chung không cần thiết.

**Bước 5 — Nếu cần conversion riêng cho nghiệp vụ, đổi tên.** Dùng tên như `reportConversionService` và inject qua `@Qualifier`; không dựa vào tên đặc biệt.

**Bước 6 — Nếu vẫn phải dùng bean tên `conversionService`, giới hạn dependency.** Tránh inject properties bean hoặc repository và tránh network I/O trong factory tạo conversion service.

**Bước 7 — Kiểm converter tiêu chuẩn.** Test `Duration`, `DataSize`, enum và các typed properties khác mà ứng dụng thực sự dùng.

**Bước 8 — Kiểm quy tắc scope.** Một converter `String -> RegionCode` có thể ảnh hưởng mọi configuration property có target `RegionCode`. Xác định có chỗ nào khác cần ngữ nghĩa khác không.

**Bước 9 — Kiểm warning.** Những cảnh báo kiểu “not eligible for getting processed by all BeanPostProcessors” có thể liên quan factory method của converter hoặc dependency được tạo quá sớm. Trường hợp converter `@ConfigurationPropertiesBinding`, dùng static method như tài liệu khuyến nghị.

**Bước 10 — Kiểm nguồn value.** Không bỏ qua khả năng environment variable, profile hoặc command line đang ghi đè key thành giá trị không parse được.

## 24. Những hiểu nhầm phổ biến

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Bean có kiểu ConversionService thì tên không quan trọng.” | Tên `conversionService` có ý nghĩa đặc biệt trong configuration property conversion. |
| “Cần thêm một converter thì phải khai báo ConversionService bean mới.” | Thường dùng `@ConfigurationPropertiesBinding` cho converter chuyên dụng. |
| “DefaultConversionService có tất cả converter riêng của Spring Boot.” | Không được mặc định đồng nhất nó với `ApplicationConversionService`. |
| “conversionService chỉ được tạo sau khi mọi service nghiệp vụ sẵn sàng.” | Bean dùng cho property conversion có thể được yêu cầu rất sớm. |
| “Converter được phép gọi DB vì nó cũng là Spring bean.” | Binding khởi động nên dùng conversion thuần, ít dependency để tránh vấn đề lifecycle. |
| “Đổi tên bean chẳng ảnh hưởng gì.” | Consumer inject theo tên/qualifier cũ có thể bị ảnh hưởng; cần cập nhật rõ ràng. |
| “@Primary đảm bảo conversionService không can thiệp Binder.” | @Primary và name-based lookup là hai cơ chế khác nhau; không dùng @Primary làm cách ly. |
| “@ConfigurationPropertiesBinding converter chỉ hoạt động cho một property path.” | Converter thường áp dụng cho cặp source/target type phù hợp trong binding, không chỉ một key. |
| “@Component trên Converter khiến mọi subsystem tự dùng nó.” | Mỗi subsystem có registration/discovery riêng, cần kiểm tra cơ chế cụ thể. |
| “@Value và @ConfigurationProperties luôn dùng converter y hệt nhau.” | Hai đường injection có đặc điểm khác, converter riêng cho binding chưa chắc dùng cho @Value. |
| “conversionService thay đổi thứ tự ghi đè config.” | Thứ tự nguồn do Environment/Config Data quyết định; conversion xử lý kiểu value. |
| “Chỉ cần startup chạy là chắc custom converter không phá hệ thống.” | Cần test các kiểu cấu hình quan trọng và những module khác có dùng conversion. |

## 25. Bài tập phân biệt phạm vi thay đổi

### Bài 1 — Tên mặc định của @Bean

~~~java
@Bean
ConversionService conversionService() {
    return new DefaultConversionService();
}
~~~

**Câu hỏi:** Bean này có tên mặc định gì, và vì sao cần quan tâm?

**Đáp án:** `conversionService`, trùng tên được Spring Boot nhận diện cho cấu hình conversion. Nếu không chủ đích tác động tới binder, nên đổi tên hoặc chọn converter chuyên dụng.

### Bài 2 — Service chỉ dùng cho analytics

~~~java
@Bean("analyticsConversionService")
ConversionService analyticsConversionService() {
    return new DefaultConversionService();
}
~~~

**Câu hỏi:** Nó có cùng tên đặc biệt như bài 1 không?

**Đáp án:** không. Bean này có tên `analyticsConversionService`. Consumer muốn dùng nên inject qua `@Qualifier`, tránh xung đột kiểu khi có nhiều ConversionService beans.

### Bài 3 — Chỉ cần String -> RegionCode cho @ConfigurationProperties

**Câu hỏi:** Có cần tạo bean tên `conversionService` không?

**Đáp án:** không nhất thiết. Định nghĩa `Converter<String, RegionCode>`, đăng ký `@Bean @ConfigurationPropertiesBinding`; static factory method được khuyến nghị.

### Bài 4 — Converter cần một repository

~~~java
@Bean("conversionService")
ConversionService conversionService(TenantRepository repository) {
    // ...
}
~~~

**Câu hỏi:** Thiết kế này có rủi ro gì?

**Đáp án:** ConversionService dùng cho property conversion có thể được yêu cầu sớm và kéo theo repository chưa sẵn sàng, có thể gây lỗi dependency/lifecycle. Nên tách thao tác DB khỏi việc chuyển kiểu config.

### Bài 5 — Một model đang bind Duration và DataSize

~~~properties
app.worker.timeout=2s
app.worker.quota=8MB
~~~

**Câu hỏi:** Sau khi thêm custom `conversionService`, cần kiểm gì?

**Đáp án:** các chuyển đổi chuẩn của `Duration` và `DataSize` vẫn hoạt động, cùng các field target khác có ý nghĩa với ứng dụng. Đừng cho rằng custom registry giữ hết conversion của Boot.

### Bài 6 — Dùng converter custom cho @Value

Bạn có `Converter<String, RegionCode>` được annotate `@ConfigurationPropertiesBinding`, nhưng inject:

~~~java
@Value("\${app.routing.default-region}")
private RegionCode region;
~~~

**Câu hỏi:** Có được tự động bảo đảm converter này được @Value dùng không?

**Đáp án:** không nên giả định. Converter qualified dành cho configuration properties binding; nếu ứng dụng dùng @Value thì cần kiểm đường conversion của Spring Core hoặc inject typed configuration bean để nhất quán.

### Bài 7 — Static method giúp giải quyết vấn đề gì?

~~~java
@Bean
@ConfigurationPropertiesBinding
public static Converter<String, RegionCode> regionCodeConverter() {
    return new StringToRegionCodeConverter();
}
~~~

**Đáp án:** factory method static giúp hạn chế việc phải khởi tạo configuration class quá sớm và tránh một số cảnh báo `BeanPostProcessor` theo khuyến nghị Spring Boot. Nó không thay thế việc giữ converter ít dependency.

### Bài 8 — Converter thay precedence?

Trong file `app.retry.delay=3s`, command line có `--app.retry.delay=500ms`.

**Câu hỏi:** Converter có quyết định lấy 3s hay 500ms không?

**Đáp án:** không. Environment/PropertySource precedence quyết định value hiệu lực; converter chuyển value sang kiểu Java. Với thứ tự thông thường, command line `500ms` được ưu tiên hơn file.

### Bài 9 — @Bean có tên đặc biệt nhưng không có ý định

Developer đổi method `reportConversionService()` thành `conversionService()` trong quá trình refactor, không thay nội dung method và cũng không viết `@Bean(name=...)`.

**Câu hỏi:** Có rủi ro gì?

**Đáp án:** tên bean mặc định có thể đổi thành `conversionService`, qua đó thay đổi cách framework nhận diện service conversion. Để ổn định contract, dùng `@Bean("reportConversionService")` hoặc giữ tên rõ ràng.

### Bài 10 — Không muốn ảnh hưởng MVC

Một converter chuyên dùng cho request parameters của Spring MVC.

**Câu hỏi:** Có cần đặt bean tên `conversionService` để MVC sử dụng?

**Đáp án:** không nhất thiết. Có thể đăng ký converter/formatter qua cấu hình MVC thích hợp, ví dụ `WebMvcConfigurer#addFormatters`, thay vì can thiệp conversionService dùng cho property binding.

## 26. Bảng quyết định cuối bài

| Nhu cầu thực sự | Phương án ưu tiên |
| --- | --- |
| Chuyển một custom type khi bind `@ConfigurationProperties` | `@ConfigurationPropertiesBinding` + `Converter<String,T>` |
| Tránh bean converter được tạo quá sớm qua configuration class | `static @Bean` factory method cho converter binding |
| Có ConversionService chỉ dùng báo cáo/nghiệp vụ | Tên riêng như `reportConversionService` + `@Qualifier` |
| Cần conversion riêng cho Spring MVC request/input | `WebMvcConfigurer#addFormatters` hoặc cơ chế MVC phù hợp |
| Cần conversion JSON | Jackson serializer/deserializer phù hợp |
| Có yêu cầu kiểm soát conversion diện rộng khi binding | Bean `conversionService` có chủ đích, giữ default converters và test regression |
| Bean conversionService phụ thuộc bean khác | Giảm dependency, loại I/O và vòng phụ thuộc; cân nhắc converter thuần |
| Có typed config Duration/DataSize lỗi sau khi tùy biến | Kiểm custom registry và các converter của Boot |
| Tránh thay đổi precedence ngoài dự tính | Xem Environment/Config Data, không nhầm với type conversion |
| Muốn kiểm tên bean được register | `ApplicationContext.containsBean("conversionService")` và danh sách bean `ConversionService` |
| Muốn chứng minh binding custom type | Test context với `@EnableConfigurationProperties` + converter binding |
| Muốn tránh tác động tới các nhóm properties khác | Chọn converter nhỏ, scope rõ, test các kiểu config hiện hành |

## 27. Nguồn đọc tiếp

- Spring Boot Reference — *Externalized Configuration*, phần **Properties Conversion**: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Framework Reference — *Type Conversion*, tìm hiểu `Converter`, `ConverterFactory`, `GenericConverter` và `ConversionService`.
- Spring Boot API — `ApplicationConversionService` và `ConfigurationPropertiesBinding`.

Trong tài liệu Spring Boot, phần *Properties Conversion* nêu rõ ba nội dung: có thể tùy biến bằng bean `ConversionService` tên `conversionService` hoặc converter qualifier `@ConfigurationPropertiesBinding`; bean dùng cho chuyển đổi có thể được yêu cầu rất sớm; và static `@Bean` method giúp tránh những cảnh báo về `BeanPostProcessor` khi đăng ký converter chuyên dụng.

**Kết luận:** tên `conversionService` không chỉ là cách đặt tên. Với Spring Boot configuration binding, nó có thể quyết định một bean `ConversionService` được infrastructure sử dụng ở giai đoạn rất sớm. Nếu nhu cầu chỉ là một kiểu riêng cho `@ConfigurationProperties`, hãy tạo converter thuần cùng `@ConfigurationPropertiesBinding`, ưu tiên static factory method, và giữ những converter mặc định của Boot. Nếu ConversionService chỉ thuộc một module nghiệp vụ, hãy đặt tên khác và inject tường minh. Việc tách phạm vi như vậy giúp giảm lỗi startup, tránh thay đổi cơ chế chuyển đổi của các typed properties khác, đồng thời làm cấu hình dễ hiểu và dễ bảo trì.
