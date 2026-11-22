# Cấu hình khớp nhưng tạo bean thất bại do dữ liệu đầu vào hoặc tài nguyên ngoài

## 1. Hiểu đúng sự khác nhau giữa condition match và bean được tạo thành công

Trong Spring Boot, một auto-configuration có thể được chọn đúng theo condition nhưng ứng dụng vẫn không khởi động được. Ví dụ, property `acme.catalog.enabled=true` làm `@ConditionalOnProperty` khớp, Spring đăng ký bean definition cho `CatalogService`, nhưng method `@Bean` đọc một file cấu hình ngoài bị thiếu. Kết quả là context refresh thất bại với `BeanCreationException`.

Đây là hai câu hỏi riêng:

- **Condition có cho phép đăng ký cấu hình/bean definition không?**
- **Spring có thể bind dữ liệu, tạo instance, giải quyết dependency và hoàn tất khởi tạo bean không?**

Một condition trả về match chỉ xác nhận câu hỏi thứ nhất. Nó không chứng minh constructor sẽ chạy thành công, dữ liệu đầu vào hợp lệ, resource có thể mở, database có thể kết nối hoặc dependency bên thứ ba đã sẵn sàng.

Bài học dùng **Spring Boot 3.3.13, Spring Framework 6.1, Java 17+ và Maven**. Ta sẽ đi từ condition tới binding, validation, bean factory method và resource loading; sau đó xây dựng một auto-configuration đọc file catalog bên ngoài và kiểm thử cả đường thành công lẫn các lỗi khởi động.

Sau bài này, bạn có thể:

1. Phân biệt condition evaluation với bean instantiation và initialization.
2. Xác định lỗi xảy ra ở binding, validation, constructor, dependency injection hay resource loading.
3. Dùng `@ConfigurationProperties` và Jakarta Validation để phát hiện cấu hình sai sớm.
4. Đọc resource qua Spring `ResourceLoader` và báo lỗi có ngữ cảnh.
5. Quyết định trường hợp nào nên fail fast, dùng fallback hay trì hoãn thao tác tới runtime.
6. Viết test cho property disabled, dữ liệu hợp lệ, file thiếu, file sai định dạng và user bean override.
7. Đọc condition report mà không nhầm nó với kết quả tạo bean.

## 2. Vòng đời: từ điều kiện tới instance

Một luồng khởi tạo đơn giản có thể hình dung như sau:

~~~text
Đọc Environment và annotation metadata
                |
                v
Đánh giá @Conditional...
          /           \
      no match       match
         |              |
         v              v
  Không đăng ký     Đăng ký bean definition
  bean definition          |
                           v
                Bind @ConfigurationProperties
                           |
                           v
                  Validate dữ liệu đầu vào
                           |
                           v
              Resolve constructor / method dependencies
                           |
                           v
                 Gọi constructor hoặc @Bean method
                           |
                           v
                Khởi tạo bean và chạy callbacks
                           |
                           v
                  Context refresh thành công
~~~

Condition thường được đánh giá trong lúc Spring phân tích cấu hình và đăng ký bean definitions. Việc tạo singleton bean thường diễn ra sau đó trong quá trình refresh context. Vì thế, một condition có thể match trong khi lỗi chỉ xuất hiện ở bước bind property hoặc gọi factory method.

### 2.1. Condition trả lời câu hỏi về khả năng áp dụng

Ví dụ:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
    prefix = "acme.catalog",
    name = "enabled",
    havingValue = "true"
)
public class CatalogAutoConfiguration {
    // Các bean chỉ được xem xét khi feature được bật.
}
~~~

Khi `acme.catalog.enabled=true`, condition cho phép Spring xử lý cấu hình. Nó không kiểm tra `acme.catalog.location` có được khai báo hay không, file ở đường dẫn đó có mở được không, nội dung file có hợp lệ không hoặc service có khởi tạo được không.

`@ConditionalOnProperty` đọc giá trị từ Spring `Environment`. Mặc định, property phải tồn tại và khác `false`; `havingValue` và `matchIfMissing` cho phép thay đổi quy tắc. Nếu cần bật bằng boolean rõ ràng, nên ghi `havingValue="true"`.

### 2.2. Bean definition được đăng ký không có nghĩa bean instance đã tồn tại

Một `@Bean` method có thể được đăng ký thành bean definition trước khi method thực sự được gọi:

~~~java
@Bean
CatalogService catalogService(CatalogProperties properties) {
    return new CatalogService(properties.getLocation());
}
~~~

Spring có thể biết tên bean, kiểu trả về và dependency cần inject từ metadata của method. Khi tạo bean, framework mới gọi method. Nếu method ném exception, quá trình tạo bean thất bại và exception thường được bọc trong `BeanCreationException`.

Tương tự, constructor injection có thể thất bại khi một dependency không tạo được. Bean A có condition match không bảo đảm bean B mà A phụ thuộc cũng khởi tạo thành công.

### 2.3. Bean creation còn gồm nhiều bước sau factory method

Một bean có thể thất bại ở các bước khác nhau:

- Constructor ném exception.
- Tham số constructor hoặc `@Bean` method không có dependency phù hợp.
- `@ConfigurationProperties` bind không được.
- Validation phát hiện dữ liệu không hợp lệ.
- `@Bean` method đọc file hoặc parse nội dung bị lỗi.
- `InitializingBean`, `@PostConstruct` hoặc custom init method thất bại.
- Một bean phụ thuộc kết nối tới hệ thống bên ngoài và timeout.
- Bean được tạo lazy, lỗi chỉ xuất hiện khi có code đầu tiên yêu cầu nó.

Khi debug, cần xác định **condition có match không** và **bean dừng ở bước nào**. Hai kết luận này có thể đồng thời đúng: condition match, nhưng bean creation fail.

## 3. Các loại condition kiểm tra điều gì và không kiểm tra điều gì?

| Condition | Kiểm tra | Không chứng minh |
| --- | --- | --- |
| `@ConditionalOnProperty` | Property có mặt và có giá trị thỏa điều kiện | Các property khác hợp lệ; file được chỉ ra tồn tại; bean tạo được |
| `@ConditionalOnClass` | Class có trên classpath | Phiên bản binary tương thích; class khởi tạo không lỗi; dependency đầy đủ |
| `@ConditionalOnBean` | Bean phù hợp đã có trong BeanFactory theo tiêu chí | Bean instance đó khởi tạo thành công hoặc dịch vụ bên trong sẵn sàng |
| `@ConditionalOnMissingBean` | Chưa có bean phù hợp để auto-configuration cung cấp default | Default bean tạo được |
| `@ConditionalOnSingleCandidate` | Có một candidate có thể được chọn để inject | Candidate đó khởi tạo được |
| `@ConditionalOnResource` | Resource được chỉ định có mặt theo cơ chế resource condition | Nội dung hợp lệ, quyền đọc đúng, resource mở được và vẫn tồn tại khi sử dụng |

### 3.1. @ConditionalOnResource không phải bộ kiểm tra nội dung

Ví dụ:

~~~java
@AutoConfiguration
@ConditionalOnResource(
    resources = "classpath:catalog/default.properties"
)
public class CatalogDefaultsAutoConfiguration {
}
~~~

Condition này hữu ích khi một thư viện chỉ áp dụng cấu hình nếu một resource đóng gói sẵn có mặt. Nó không xác thực file có đủ key, đúng encoding hoặc parse được hay không.

Với file ngoài có đường dẫn do người dùng cấu hình, kiểm tra sự hiện diện ở một thời điểm cũng không thay thế được thao tác mở và đọc thực tế. File có thể bị xóa, quyền truy cập có thể thay đổi hoặc nội dung có thể hỏng sau khi condition đã đánh giá. Đây là tình huống kiểu “kiểm tra xong rồi mới dùng” (time-of-check/time-of-use).

Nếu resource là bắt buộc khi feature bật, hãy để bean/service mở resource và phát ra lỗi có ngữ cảnh khi không thể sử dụng. Nếu resource thật sự tùy chọn, định nghĩa fallback rõ ràng và kiểm thử cả hai nhánh.

### 3.2. @ConditionalOnExpression không nên dùng để gọi bean kiểm tra tài nguyên

Tránh viết expression tham chiếu bean để kiểm tra file hoặc remote service:

~~~java
@ConditionalOnExpression("@catalogHealthChecker.available()")
~~~

Việc tham chiếu bean trong expression có thể làm bean được khởi tạo rất sớm trong lúc refresh context. Khi đó bean có thể chưa trải qua đầy đủ post-processing, bao gồm configuration properties binding. Ngoài ra, condition sẽ phụ thuộc I/O hoặc trạng thái dịch vụ ngoài và khó kiểm thử.

Condition nên quyết định cấu hình có áp dụng hay không dựa trên metadata/property/classpath. Việc mở file, parse dữ liệu và kết nối dịch vụ thuộc về bean/service ở giai đoạn phù hợp.

## 4. Phân loại dữ liệu đầu vào và lỗi thường gặp

Trước khi đọc stack trace, hãy xác định dữ liệu đến từ đâu và được kiểm tra ở thời điểm nào.

| Nhóm dữ liệu | Ví dụ | Lỗi thường gặp | Cách xử lý |
| --- | --- | --- | --- |
| Property scalar | `acme.catalog.enabled`, `max-items` | Thiếu key, sai kiểu, giá trị ngoài phạm vi | Type-safe binding và validation |
| Property có cấu trúc | Danh sách endpoint, credentials, nested options | Thiếu field lồng, phần tử không hợp lệ | `@Valid`, constraint trên nested object |
| Đường dẫn resource | `file:./config/catalog.properties` | File không tồn tại, không có quyền đọc, sai working directory | `ResourceLoader`, thông báo location cụ thể |
| Nội dung resource | Properties, YAML, JSON, XML | Thiếu key, sai encoding, dữ liệu hỏng | Parse có kiểm soát và validate schema/domain |
| Dependency bên ngoài | Database, HTTP API, message broker | DNS, TLS, authentication, timeout, service unavailable | Timeout, retry có giới hạn, readiness/health và fallback phù hợp |
| Dependency Java | Class hoặc thư viện tùy chọn | Thiếu class, version không tương thích, `LinkageError` | Dependency management và class condition |

### 4.1. Binding lỗi khác với condition no-match

Ví dụ `acme.catalog.max-items=many` không làm `@ConditionalOnProperty(acme.catalog.enabled=true)` trở thành false. Condition vẫn có thể match. Sau đó binder cố chuyển chuỗi `many` thành kiểu số và thất bại.

Đây là lỗi chuyển đổi dữ liệu (binding/conversion), không phải lỗi condition. Sửa condition để kiểm tra `max-items` bằng SpEL thường không phải giải pháp tốt; hãy bind vào kiểu `int` hoặc `Integer`, rồi validate giá trị.

### 4.2. Validation khác với parse resource

Giá trị `acme.catalog.location=` có thể bind thành chuỗi rỗng. Nếu field có `@NotBlank`, validation sẽ từ chối cấu hình trước khi `@Bean` method được gọi.

Ngược lại, một location hợp lệ về mặt chuỗi như `file:./config/catalog.properties` vẫn có thể trỏ tới file không tồn tại. Validation của property chỉ xác nhận chuỗi không trống; nó không đảm bảo filesystem có resource tương ứng.

### 4.3. File mở được vẫn có thể chứa dữ liệu sai

Một file có thể tồn tại và đọc được nhưng:

- Thiếu key bắt buộc.
- Giá trị số không parse được.
- Giá trị nằm ngoài miền nghiệp vụ.
- Encoding không đúng như giả định.
- Dữ liệu bị cắt hoặc ghi dở.
- Nội dung không tương thích với version schema của thư viện.

Vì vậy, sau khi mở resource cần kiểm tra cấu trúc và giá trị domain. Không nên coi `Resource.exists()` hoặc `Resource.isReadable()` là bằng chứng rằng nội dung hợp lệ.

## 5. Bind và validate cấu hình bằng @ConfigurationProperties

Với nhiều property có quan hệ với nhau, nên gom chúng vào một class có kiểu thay vì đọc từng chuỗi bằng `@Value`.

### 5.1. Khai báo properties class

Ví dụ:

~~~java
package com.acme.catalog.autoconfigure;

import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "acme.catalog")
@Validated
public class CatalogProperties {

    @NotBlank
    private String location;

    public String getLocation() {
        return this.location;
    }

    public void setLocation(String location) {
        this.location = location;
    }
}
~~~

`@ConfigurationProperties` cho phép Spring Boot bind property từ file properties/YAML, environment variables, system properties hoặc command-line arguments. `@Validated` kích hoạt validation cho class; `@NotBlank` yêu cầu location có nội dung khác khoảng trắng.

Để dùng Jakarta Validation, thêm một implementation vào classpath. Trong ví dụ Maven ở mục 9, dependency `spring-boot-starter-validation` cung cấp hạ tầng validation.

### 5.2. Đăng ký properties bean trong auto-configuration

Có thể dùng `@EnableConfigurationProperties`:

~~~java
@AutoConfiguration
@EnableConfigurationProperties(CatalogProperties.class)
public class CatalogAutoConfiguration {
}
~~~

Khi cấu hình được xử lý, Spring Boot đăng ký properties bean và thực hiện binding/validation. Nếu location thiếu hoặc trống, context có thể thất bại trong lúc tạo properties bean, trước khi factory method tạo `CatalogService` được gọi.

### 5.3. Validate các trường hợp đơn giản ngay ở biên cấu hình

Các constraint thường dùng:

| Annotation | Quy tắc |
| --- | --- |
| `@NotNull` | Giá trị không được null |
| `@NotBlank` | Chuỗi không null và phải có ký tự không phải khoảng trắng |
| `@NotEmpty` | Chuỗi/collection/map không được rỗng |
| `@Min(1)` | Giá trị số tối thiểu là 1 |
| `@Max(1000)` | Giá trị số tối đa là 1000 |
| `@Positive` | Số phải dương |
| `@Email` | Chuỗi phải có dạng email phù hợp validator |
| `@Pattern` | Chuỗi phải khớp biểu thức chính quy |

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "acme.catalog")
@Validated
public class CatalogProperties {

    @NotBlank
    private String location;

    @Min(1)
    @Max(1000)
    private int maxItems = 100;

    // getters and setters
}
~~~

Với object lồng nhau, dùng `@Valid` trên field cần cascade validation. Nếu không có `@Valid`, constraint trên object con có thể không được đánh giá theo cách mong muốn.

### 5.4. Không nhét kiểm tra I/O vào validator cấu hình

Validation phù hợp để kiểm tra tính hợp lệ của giá trị đã bind: không trống, đúng format, nằm trong khoảng, tương thích với các property khác.

Không nên biến validator thành nơi gọi HTTP, truy cập database hoặc đọc file lớn. Những thao tác này có thể chậm, phụ thuộc môi trường và có side effect. Kiểm tra resource thực tế trong service/factory method sau khi properties đã được bind.

## 6. Đọc resource ngoài bằng Spring Resource abstraction

Spring cung cấp `Resource` và `ResourceLoader` để truy cập nhiều loại resource qua một API thống nhất.

Một số dạng location thường gặp:

| Prefix | Ý nghĩa |
| --- | --- |
| `classpath:` | Resource trên classpath |
| `file:` | Resource trên filesystem |
| URL như `https:` | Resource được truy cập qua URL handler tương ứng |
| Đường dẫn không prefix | Cách xử lý phụ thuộc `ResourceLoader` đang dùng |

Ví dụ:

~~~java
Resource resource = resourceLoader.getResource(
    "file:./config/catalog.properties"
);
~~~

### 6.1. Dùng getInputStream() và đóng stream đúng cách

`Resource` là descriptor của resource. Để thực sự mở nội dung, gọi `getInputStream()`. Stream cần được đóng, nên dùng try-with-resources:

~~~java
try (InputStream input = resource.getInputStream()) {
    // Đọc dữ liệu.
}
~~~

Không chỉ kiểm tra `resource != null`: việc tạo descriptor không đồng nghĩa resource tồn tại hoặc mở được. `exists()` có thể kiểm tra sự hiện diện vật lý; `isReadable()` có thể cho biết khả năng đọc theo descriptor, nhưng lần gọi `getInputStream()` thực tế vẫn có thể thất bại.

### 6.2. Đường dẫn tương đối phụ thuộc working directory

Location `file:./config/catalog.properties` được phân giải tương đối với working directory của process. Khi chạy từ IDE, Maven, service manager, container hoặc systemd, working directory có thể khác nhau.

Với production deployment, ưu tiên một trong các cách:

- Cung cấp absolute path qua environment variable hoặc deployment configuration.
- Mount file vào một đường dẫn cố định trong container.
- Dùng `spring.config.import`/config tree nếu file thực chất là nguồn application configuration.
- Dùng một secret/configuration provider được hỗ trợ và có policy rõ ràng.

Không log nội dung secret hoặc credential khi báo lỗi. Chỉ ghi location, tên property và nguyên nhân kỹ thuật đủ để người vận hành sửa.

### 6.3. Khi nào nên dùng spring.config.import?

Nếu file ngoài là **application configuration** mà Spring Boot cần đưa vào `Environment`, hãy cân nhắc Config Data API:

~~~properties
spring.config.import=file:./config/extra.properties
~~~

Khi đó các property trong file được thêm vào Environment và có thể bind bằng `@ConfigurationProperties`.

Nếu file là **dữ liệu nghiệp vụ riêng** của một bean, chẳng hạn catalog, template hoặc mapping file, `ResourceLoader` thường phù hợp hơn. Không nên tự parse file `application.properties` bằng `Properties.load()` để thay thế cơ chế config data của Spring Boot.

## 7. Thiết kế auto-configuration có lỗi rõ ràng và có thể hành động

Ví dụ sau tạo default `CatalogService` khi feature bật và người dùng chưa cung cấp implementation riêng. Properties chỉ được đăng ký trong nested configuration mặc định; nếu user bean đã có, thư viện không cần bind location hoặc đọc file mặc định.

### 7.1. Service model

File `src/main/java/com/acme/catalog/autoconfigure/CatalogService.java`:

~~~java
package com.acme.catalog.autoconfigure;

public record CatalogService(String name, int maxItems) {
}
~~~

### 7.2. Auto-configuration

File `src/main/java/com/acme/catalog/autoconfigure/CatalogAutoConfiguration.java`:

~~~java
package com.acme.catalog.autoconfigure;

import java.io.IOException;
import java.io.InputStreamReader;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;

@AutoConfiguration
@ConditionalOnProperty(
    prefix = "acme.catalog",
    name = "enabled",
    havingValue = "true"
)
public class CatalogAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnMissingBean(CatalogService.class)
    @EnableConfigurationProperties(CatalogProperties.class)
    static class DefaultCatalogConfiguration {

        @Bean
        CatalogService catalogService(
                CatalogProperties properties,
                ResourceLoader resourceLoader) {

            String location = properties.getLocation();
            Resource resource = resourceLoader.getResource(location);
            Properties values = new Properties();

            try (Reader reader = new InputStreamReader(
                    resource.getInputStream(),
                    StandardCharsets.UTF_8)) {
                values.load(reader);
            }
            catch (IOException ex) {
                throw new IllegalStateException(
                    "Cannot read catalog resource '" + location + "'",
                    ex
                );
            }
            catch (IllegalArgumentException ex) {
                throw new IllegalStateException(
                    "Catalog resource '" + location
                        + "' contains malformed properties data",
                    ex
                );
            }

            String name = values.getProperty("catalog.name");
            if (name == null || name.isBlank()) {
                throw new IllegalStateException(
                    "Required key 'catalog.name' is missing or blank in '"
                        + location + "'"
                );
            }

            String rawMaxItems =
                values.getProperty("catalog.max-items", "100");

            int maxItems;
            try {
                maxItems = Integer.parseInt(rawMaxItems.trim());
            }
            catch (NumberFormatException ex) {
                throw new IllegalStateException(
                    "Property 'catalog.max-items' in '" + location
                        + "' must be an integer, but was '"
                        + rawMaxItems + "'",
                    ex
                );
            }

            if (maxItems < 1) {
                throw new IllegalStateException(
                    "Property 'catalog.max-items' in '" + location
                        + "' must be greater than zero"
                );
            }

            return new CatalogService(name.trim(), maxItems);
        }
    }
}
~~~

Có một số quyết định quan trọng trong thiết kế:

- Condition ngoài kiểm tra feature có được bật hay không.
- `@ConditionalOnMissingBean` cho phép ứng dụng thay thế default service.
- `@EnableConfigurationProperties` chỉ nằm trong nested default configuration. Nếu ứng dụng đã cung cấp `CatalogService`, properties mặc định không cần được bind và file ngoài không cần được đọc.
- `ResourceLoader` xử lý location theo abstraction của Spring.
- `getInputStream()` thực sự mở file; IOException được bọc bằng exception có location cụ thể.
- Nội dung được parse và kiểm tra key/giá trị trước khi trả service.
- Mọi lỗi đều nêu tên property hoặc resource cần sửa.

Không nên bắt `Exception` chung rồi bỏ qua lỗi hoặc trả một object rỗng. Điều đó khiến ứng dụng tiếp tục chạy với trạng thái không đúng và làm nguyên nhân thật khó tìm.

### 7.3. Vì sao không kiểm tra file trong condition?

Có thể nghĩ tới một custom condition đọc file trước khi đăng ký bean. Thiết kế đó không phù hợp cho ví dụ này:

- Condition chạy trong giai đoạn xử lý cấu hình.
- Đọc file có I/O và có thể phụ thuộc permission hoặc filesystem.
- Sau khi condition trả match, file vẫn có thể thay đổi trước khi bean mở nó.
- Nếu condition đọc và parse file, bean/service vẫn cần dữ liệu đã parse hoặc phải đọc lần nữa.
- Lỗi ở condition thường khó diễn đạt bằng thông báo domain-specific như lỗi trong factory method.

Hãy để condition kiểm tra điều kiện cấu hình đơn giản. Hãy để bean/service thực hiện thao tác tạo đối tượng và xác thực tài nguyên cần thiết cho đối tượng đó.

## 8. Phân biệt tài nguyên bắt buộc, tùy chọn và tài nguyên từ xa

Không phải resource nào cũng nên khiến ứng dụng fail startup. Chính sách phụ thuộc vai trò của resource.

| Loại dependency | Chính sách thường phù hợp | Ví dụ |
| --- | --- | --- |
| Bắt buộc để phục vụ mọi request | Fail fast khi không thể đọc/validate | Catalog lõi, schema bắt buộc, truststore bắt buộc |
| Tùy chọn, có default an toàn | Dùng fallback và ghi log rõ ràng | Template mặc định, file override tùy chọn |
| Chỉ dùng cho một tính năng | Có thể tắt riêng feature hoặc khởi tạo lazy có chủ đích | Export module không được dùng ở mọi deployment |
| Dịch vụ từ xa có thể gián đoạn | Client bean có thể tạo trước; kết nối có timeout/retry và health/readiness | HTTP API, message broker |
| Dịch vụ bắt buộc trước khi nhận traffic | Fail fast hoặc giữ instance chưa ready cho tới khi dependency sẵn sàng | Hệ thống xác thực bắt buộc |

### 8.1. Fail fast khi thiếu dữ liệu bắt buộc

Nếu không có catalog thì mọi request của ứng dụng đều sai, nên dừng startup với thông báo:

~~~text
APPLICATION FAILED TO START

Description:
Cannot read catalog resource 'file:./config/catalog.properties'

Action:
Verify that the file exists, is readable by the application process,
and contains the required catalog properties.
~~~

Đây là thông báo minh họa do ứng dụng hoặc FailureAnalyzer tùy chỉnh có thể tạo. Nội dung thật phụ thuộc exception và logging.

### 8.2. Fallback khi resource thật sự tùy chọn

Nếu file override chỉ dùng để tùy chỉnh giao diện, có thể dùng default khi không có file:

~~~java
if (!resource.exists()) {
    return CatalogService.withDefaults();
}
~~~

Nhưng fallback phải là hành vi được tài liệu hóa. Không dùng fallback âm thầm cho một resource bắt buộc vì ứng dụng có thể chạy nhưng phục vụ dữ liệu sai.

### 8.3. Không kết nối mạng tùy tiện trong constructor

Một `@Bean` method có thể tạo client object mà chưa mở connection. Đây thường là thiết kế tốt hơn so với gọi remote API trong constructor. Khi request thực tế tới, client dùng timeout, retry có giới hạn và circuit breaker phù hợp.

Nếu startup bắt buộc phải xác minh dependency từ xa, hãy làm rõ lý do và giới hạn thời gian. Đừng để DNS/network outage khiến ứng dụng treo vô thời hạn. Với Kubernetes hoặc hệ thống orchestration, readiness/health checks có thể thể hiện trạng thái dependency theo chính sách của ứng dụng.

## 9. Ví dụ hoàn chỉnh Java 17+ và Maven

Ví dụ dưới đây có một auto-configuration, một ứng dụng demo và bộ test dùng `ApplicationContextRunner`. Package ứng dụng `demo.app` tách khỏi package thư viện `com.acme.catalog.autoconfigure`; auto-configuration được nạp qua imports file.

### 9.1. Cấu trúc project

~~~text
catalog-demo/
├── pom.xml
├── config/
│   └── catalog.properties
└── src/
    ├── main/
    │   ├── java/
    │   │   ├── com/acme/catalog/autoconfigure/
    │   │   │   ├── CatalogProperties.java
    │   │   │   ├── CatalogService.java
    │   │   │   └── CatalogAutoConfiguration.java
    │   │   └── demo/app/
    │   │       └── CatalogApplication.java
    │   └── resources/
    │       ├── application.properties
    │       └── META-INF/spring/
    │           └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/demo/app/
            └── CatalogAutoConfigurationTests.java
~~~

### 9.2. File pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>catalog-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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

`spring-boot-starter-validation` cung cấp Jakarta Validation implementation để `@Validated` và `@NotBlank` hoạt động. `spring-boot-starter-test` cung cấp JUnit, AssertJ và Spring Boot test utilities.

### 9.3. File CatalogProperties.java

~~~java
package com.acme.catalog.autoconfigure;

import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "acme.catalog")
@Validated
public class CatalogProperties {

    @NotBlank
    private String location;

    public String getLocation() {
        return this.location;
    }

    public void setLocation(String location) {
        this.location = location;
    }
}
~~~

### 9.4. File CatalogService.java

~~~java
package com.acme.catalog.autoconfigure;

public record CatalogService(String name, int maxItems) {
}
~~~

### 9.5. File CatalogAutoConfiguration.java

Dùng nguyên implementation ở mục 7.2. Trong project demo, file nằm tại `src/main/java/com/acme/catalog/autoconfigure/CatalogAutoConfiguration.java`.

### 9.6. Đăng ký auto-configuration

File `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`:

~~~text
com.acme.catalog.autoconfigure.CatalogAutoConfiguration
~~~

Imports file giúp Spring Boot phát hiện auto-configuration trong JAR. Package auto-configuration không cần nằm dưới package component scan của ứng dụng.

### 9.7. Cấu hình ứng dụng

File `src/main/resources/application.properties`:

~~~properties
acme.catalog.enabled=true
acme.catalog.location=file:./config/catalog.properties
~~~

File ngoài `config/catalog.properties` ở project root:

~~~properties
catalog.name=Demo Catalog
catalog.max-items=25
~~~

`file:./config/catalog.properties` tương đối với working directory. Khi chạy lệnh Maven dưới đây, hãy chạy từ thư mục `catalog-demo` để đường dẫn trỏ tới đúng file.

### 9.8. Main application

File `src/main/java/demo/app/CatalogApplication.java`:

~~~java
package demo.app;

import com.acme.catalog.autoconfigure.CatalogService;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }

    @Bean
    CommandLineRunner printCatalog(CatalogService catalog) {
        return args -> System.out.printf(
            "catalog=%s, maxItems=%d%n",
            catalog.name(),
            catalog.maxItems()
        );
    }
}
~~~

### 9.9. Chạy ứng dụng

Yêu cầu: JDK 17+ và Maven. Từ thư mục project:

~~~bash
mvn clean spring-boot:run
~~~

Dòng output do `CommandLineRunner` in ra:

~~~text
catalog=Demo Catalog, maxItems=25
~~~

Spring Boot sẽ có thêm startup logs. Dòng trên là output nghiệp vụ của ví dụ khi file tồn tại và có nội dung hợp lệ.

## 10. Kiểm thử cả thành công lẫn thất bại bằng ApplicationContextRunner

`ApplicationContextRunner` tạo context nhỏ, cho phép thay property và user configuration theo từng test. Nó phù hợp để kiểm tra một auto-configuration có xử lý đúng tổ hợp input hay không.

### 10.1. File test

File `src/test/java/demo/app/CatalogAutoConfigurationTests.java`:

~~~java
package demo.app;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import com.acme.catalog.autoconfigure.CatalogAutoConfiguration;
import com.acme.catalog.autoconfigure.CatalogService;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class CatalogAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(CatalogAutoConfiguration.class)
            );

    private ApplicationContextRunner enabledWith(Path file) {
        return this.contextRunner.withPropertyValues(
            "acme.catalog.enabled=true",
            "acme.catalog.location=" + file.toUri()
        );
    }

    @Test
    void doesNotCreateCatalogWhenFeatureIsDisabled() {
        this.contextRunner
            .withPropertyValues("acme.catalog.enabled=false")
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).doesNotHaveBean(CatalogService.class);
            });
    }

    @Test
    void createsCatalogFromValidExternalFile(@TempDir Path tempDir)
            throws IOException {

        Path file = tempDir.resolve("catalog.properties");
        Files.writeString(
            file,
            "catalog.name=Test Catalog\ncatalog.max-items=12\n",
            StandardCharsets.UTF_8
        );

        this.enabledWith(file).run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(CatalogService.class);

            CatalogService catalog =
                context.getBean(CatalogService.class);

            assertThat(catalog.name()).isEqualTo("Test Catalog");
            assertThat(catalog.maxItems()).isEqualTo(12);
        });
    }

    @Test
    void failsWithLocationWhenExternalFileIsMissing(@TempDir Path tempDir) {
        Path missing = tempDir.resolve("missing.properties");

        this.enabledWith(missing).run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure())
                .hasStackTraceContaining("Cannot read catalog resource");
        });
    }

    @Test
    void failsWhenLocationIsBlank() {
        this.contextRunner
            .withPropertyValues(
                "acme.catalog.enabled=true",
                "acme.catalog.location="
            )
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                    .hasStackTraceContaining("must not be blank");
            });
    }

    @Test
    void failsWhenCatalogNumberIsMalformed(@TempDir Path tempDir)
            throws IOException {

        Path file = tempDir.resolve("catalog.properties");
        Files.writeString(
            file,
            "catalog.name=Test Catalog\ncatalog.max-items=many\n",
            StandardCharsets.UTF_8
        );

        this.enabledWith(file).run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure())
                .hasStackTraceContaining("must be an integer");
        });
    }

    @Test
    void userServiceOverridesDefaultWithoutReadingDefaultFile() {
        this.contextRunner
            .withPropertyValues("acme.catalog.enabled=true")
            .withUserConfiguration(UserCatalogConfiguration.class)
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(CatalogService.class);

                CatalogService catalog =
                    context.getBean(CatalogService.class);

                assertThat(catalog.name()).isEqualTo("Custom Catalog");
                assertThat(catalog.maxItems()).isEqualTo(7);
            });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserCatalogConfiguration {

        @Bean
        CatalogService customCatalogService() {
            return new CatalogService("Custom Catalog", 7);
        }
    }
}
~~~

### 10.2. Ma trận kết quả

| Test | Input | Kết quả mong đợi |
| --- | --- | --- |
| Feature disabled | `enabled=false` | Context thành công, không có `CatalogService` |
| File hợp lệ | `enabled=true`, location trỏ file hợp lệ | Context thành công, service chứa đúng dữ liệu |
| File thiếu | `enabled=true`, location trỏ file không tồn tại | Context thất bại, lỗi có location |
| Location trống | `enabled=true`, location rỗng | Binding/validation thất bại trước khi đọc file |
| Nội dung sai | `catalog.max-items=many` | Bean creation thất bại với lỗi parse có tên key |
| User bean override | Có `CatalogService` do ứng dụng cung cấp | Default configuration back off, không cần location mặc định |

Test cuối đặc biệt hữu ích: nested configuration chứa `@ConditionalOnMissingBean` bao quanh cả `@EnableConfigurationProperties`. Khi ứng dụng đã cung cấp `CatalogService`, default properties không cần bind và file mặc định không bị đọc.

### 10.3. Chạy test

Tại thư mục project:

~~~bash
mvn clean test
~~~

Có sáu test độc lập. Kết quả mong đợi là sáu test pass và Maven báo `BUILD SUCCESS`. Đây là kỳ vọng từ assertion trong ví dụ; hãy chạy lệnh trong môi trường dự án để xác nhận dependency/plugin và runtime cụ thể.

### 10.4. Vì sao test nên kiểm tra context thay vì chỉ gọi helper?

Nếu chỉ test hàm đọc file, bạn chưa kiểm tra:

- `@ConditionalOnProperty` có match đúng không.
- `@EnableConfigurationProperties` có bind và validate đúng không.
- `@ConditionalOnMissingBean` có back off đúng không.
- Spring có wrap exception trong `BeanCreationException` hay không.
- Context refresh có thành công hoặc thất bại đúng tình huống không.

`ApplicationContextRunner` kiểm tra toàn bộ luồng auto-configuration ở phạm vi nhỏ và nhanh hơn việc khởi động toàn ứng dụng trong mọi test.

## 11. Chẩn đoán lỗi khi condition đã match

Khi log cho thấy auto-configuration được áp dụng nhưng ứng dụng vẫn fail, hãy điều tra theo thứ tự.

### 11.1. Đọc exception đầu tiên của bean thất bại

Tìm bean name trong `BeanCreationException`, ví dụ:

~~~text
Error creating bean with name 'catalogService'
~~~

Sau đó lần theo các `Caused by` để tìm nguyên nhân sâu nhất. Một chuỗi có thể trông như:

~~~text
BeanCreationException
  -> IllegalStateException:
       Cannot read catalog resource 'file:./config/catalog.properties'
       -> FileNotFoundException
~~~

Thông báo ngoài cùng cho biết bean nào không tạo được; nguyên nhân sâu nhất thường cho biết thao tác nào thất bại.

### 11.2. Phân loại theo điểm dừng

| Dấu hiệu | Điểm cần kiểm tra |
| --- | --- |
| `ConfigurationPropertiesBindException` / `BindException` | Property name, kiểu dữ liệu, conversion và nguồn cấu hình |
| Validation exception | Constraint, property bị thiếu/rỗng, nested `@Valid` |
| `UnsatisfiedDependencyException` | Bean dependency nào không thể inject |
| `NoSuchBeanDefinitionException` | Bean definition bị thiếu hoặc condition không đăng ký |
| `NoUniqueBeanDefinitionException` | Có nhiều bean candidate cho injection một giá trị |
| `BeanCreationException` | Constructor, `@Bean` method, init callback hoặc dependency |
| `FileNotFoundException` | Location, working directory, mount và tên file |
| `AccessDeniedException` / `IOException` | Permission, filesystem, encoding, stream hoặc I/O |
| `NumberFormatException` / parse exception | Nội dung resource và định dạng value |
| `ConnectException`, timeout, SSL/auth exception | DNS, endpoint, TLS, credentials và timeout |

Không nên sửa condition chỉ vì thấy `BeanCreationException`. Nếu condition đã match đúng, hãy sửa dữ liệu, resource hoặc bean factory logic đang thất bại.

### 11.3. Bật condition evaluation report

Chạy ứng dụng với `--debug`:

~~~bash
java -jar target/catalog-demo-1.0.0.jar --debug
~~~

Condition report cho biết các auto-configuration/condition nào match hoặc no-match. Nếu `CatalogAutoConfiguration` match, report giúp xác nhận property gate đã mở.

Nhưng condition report không kiểm tra nội dung file và không chứng minh `CatalogService` đã tạo thành công. Sau khi xác nhận condition match, tiếp tục đọc stack trace của bean bị lỗi.

Nếu ứng dụng đã khởi động và có Actuator phù hợp, endpoint conditions có thể cung cấp báo cáo. Khi context không thể khởi động, hãy dựa vào startup logs, failure analysis và exception chain.

### 11.4. Dùng FailureAnalyzer và thông báo có hành động cụ thể

Spring Boot gọi các `FailureAnalyzer` đã đăng ký khi startup thất bại. Analyzer có thể biến exception kỹ thuật thành thông báo gồm Description và Action.

Với thư viện riêng, có thể cung cấp analyzer cho một loại exception domain-specific nếu thông báo mặc định chưa đủ rõ. Hãy bảo đảm message nêu:

- Bean/feature nào thất bại.
- Resource hoặc property nào liên quan.
- Lỗi gốc đã xảy ra.
- Người vận hành nên kiểm tra điều gì tiếp theo.

Không đưa secret, password, token hoặc nội dung nhạy cảm vào error message.

## 12. Lazy initialization, retry và health check: chọn đúng thời điểm kiểm tra

### 12.1. Lazy initialization không sửa cấu hình sai

Khi bật:

~~~properties
spring.main.lazy-initialization=true
~~~

Bean được tạo khi có yêu cầu thay vì ngay trong startup. Điều này có thể làm ứng dụng khởi động nhanh hơn, nhưng lỗi cấu hình/resource chỉ xuất hiện khi bean được dùng lần đầu.

Lazy initialization có ích khi bean thực sự tùy chọn hoặc ít được sử dụng. Nó không phải cách xử lý lỗi cho resource bắt buộc. Nếu một feature cần file để phục vụ mọi request, trì hoãn việc phát hiện file thiếu có thể khiến lỗi xuất hiện ở production sau khi traffic đã vào.

Có thể dùng `@Lazy(false)` cho bean cần tạo ngay cả khi ứng dụng bật lazy initialization toàn cục.

### 12.2. Retry chỉ phù hợp với lỗi có khả năng hồi phục

Retry có thể phù hợp với network timeout hoặc dịch vụ tạm thời chưa sẵn sàng. Nó không sửa được:

- File path sai vĩnh viễn.
- Property bị thiếu.
- Giá trị không parse được.
- Schema file không tương thích.
- Permission bị cấu hình sai.

Đừng retry vô hạn khi khởi tạo bean. Nếu cần retry, đặt timeout, số lần thử, backoff và log rõ trạng thái cuối cùng.

### 12.3. Readiness và health khác với startup condition

Một bean client có thể được tạo thành công dù remote service đang tạm thời không sẵn sàng. Khi đó health/readiness có thể phản ánh khả năng phục vụ traffic.

Ngược lại, nếu bean factory method kết nối remote ngay khi tạo bean và ném exception, context có thể không khởi động tới giai đoạn health endpoint. Hãy chọn rõ một trong hai chính sách:

- **Dependency bắt buộc trước khi nhận traffic:** kiểm tra readiness và giữ instance chưa ready hoặc fail startup theo yêu cầu.
- **Dependency có thể gián đoạn:** tạo client an toàn, dùng timeout/retry/circuit breaker và xử lý lỗi ở runtime.

## 13. Lỗi phổ biến và cách khắc phục

| Lỗi / hiểu nhầm | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Condition match nghĩa là bean chắc chắn được tạo | Condition chỉ quyết định đăng ký | Kiểm binding, factory method, dependency và init |
| `@ConditionalOnProperty` kiểm tra file mà property trỏ tới | Nó chỉ đọc giá trị Environment | Mở resource trong bean/service |
| `@ConditionalOnResource` xác thực nội dung file | Nó chỉ kiểm tra sự hiện diện của resource | Parse và validate nội dung sau khi mở |
| Dùng `exists()` rồi giả định `getInputStream()` luôn thành công | Resource có thể thay đổi hoặc lỗi khi mở | Bắt IOException tại thao tác đọc thật |
| Dùng `@Value` cho nhiều property có quan hệ | Khó gom type và validate liên trường | Dùng `@ConfigurationProperties` |
| Chỉ kiểm tra chuỗi location không rỗng | Đường dẫn có thể hợp lệ về cú pháp nhưng không tồn tại | Test mở resource và báo location |
| Bắt exception rồi trả object rỗng | Ứng dụng chạy với dữ liệu sai | Fail fast hoặc fallback có chủ đích |
| Đọc file trong condition | I/O nằm ở giai đoạn đăng ký cấu hình, khó chẩn đoán | Đọc trong factory method/service |
| Kết nối remote trong constructor | Startup phụ thuộc network không cần thiết | Tạo client trước, kết nối theo policy runtime |
| Bật lazy initialization để che lỗi | Lỗi chỉ xuất hiện khi bean được dùng | Giữ eager init cho dependency bắt buộc |
| Chỉ xem condition report | Report không xác nhận bean đã khởi tạo | Đọc exception chain và test context |
| Dùng relative path nhưng không ghi working directory | IDE/Maven/container có working directory khác | Dùng absolute path hoặc mount path ổn định |
| Log toàn bộ cấu hình khi lỗi | Có thể làm lộ credentials/secrets | Chỉ log key/location và thông tin không nhạy cảm |

## 14. Checklist review một auto-configuration có resource bên ngoài

Trước khi phát hành thư viện, hãy kiểm tra:

- [ ] Condition chỉ kiểm tra feature flag, classpath, bean hoặc metadata phù hợp.
- [ ] Không thực hiện I/O, network, database hay gọi `getBean()` trong condition.
- [ ] Property được bind vào `@ConfigurationProperties` có kiểu rõ ràng.
- [ ] Constraint phù hợp được bật bằng `@Validated` và validation implementation có trong dependency.
- [ ] Nested properties có `@Valid` khi cần cascade validation.
- [ ] Resource location có quy tắc rõ ràng về `classpath:`, `file:` hoặc URL.
- [ ] Relative path có ghi rõ working directory; production dùng path ổn định.
- [ ] Stream được đóng bằng try-with-resources.
- [ ] Charset được xác định rõ thay vì phụ thuộc platform default.
- [ ] Nội dung file được parse và validate sau khi mở.
- [ ] Exception nêu bean, property/resource và hành động sửa.
- [ ] Mandatory dependency fail fast; optional dependency có fallback được tài liệu hóa.
- [ ] Remote connection có timeout/retry/health policy phù hợp.
- [ ] User-defined bean override được test và không bị buộc dùng resource mặc định nếu không cần.
- [ ] Test có disabled, valid, missing, malformed và invalid input cases.
- [ ] Condition report và exception chain được dùng đúng mục đích.
- [ ] Lazy initialization không làm trì hoãn lỗi của dependency bắt buộc.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** `@ConditionalOnProperty` match có chứng minh `@Bean` method chạy thành công không?  
**Đáp án:** Không. Nó chỉ cho phép cấu hình/bean definition được đăng ký; binding, dependency injection và factory method vẫn có thể thất bại.

**Câu 2.** Property `acme.catalog.enabled=true` và `acme.catalog.location=file:./missing.properties` có thể làm condition match nhưng bean fail không?  
**Đáp án:** Có. Property gate match, nhưng khi factory method mở resource, thao tác có thể ném IOException và làm bean creation thất bại.

**Câu 3.** `@ConditionalOnResource` có đảm bảo file có key bắt buộc không?  
**Đáp án:** Không. Nó kiểm tra sự hiện diện của resource; nội dung phải được đọc, parse và validate riêng.

**Câu 4.** Khi nào dùng `@ConfigurationProperties` thay cho nhiều `@Value`?  
**Đáp án:** Khi có nhóm property có cấu trúc, cần type-safe binding, relaxed binding và validation tập trung.

**Câu 5.** Vì sao thêm `@Validated` nhưng constraint không chạy?  
**Đáp án:** Có thể thiếu Jakarta Validation implementation trên classpath hoặc properties bean chưa được đăng ký theo cơ chế phù hợp.

**Câu 6.** File tồn tại nhưng `getInputStream()` thất bại. Nên kiểm tra gì?  
**Đáp án:** Permission, filesystem/mount, working directory, URL handler, resource descriptor và lỗi I/O tại thời điểm mở.

**Câu 7.** Có nên gọi HTTP endpoint trong `Condition.matches()` để quyết định bean không?  
**Đáp án:** Không. Condition chạy trong giai đoạn xử lý cấu hình; remote call tạo side effect, tăng độ bất định và làm startup khó kiểm soát.

**Câu 8.** Khi `--debug` cho biết auto-configuration match nhưng context vẫn fail, bước tiếp theo là gì?  
**Đáp án:** Tìm bean name trong `BeanCreationException`, lần theo `Caused by`, phân loại binding/validation/dependency/resource và sửa nguyên nhân gốc.

**Câu 9.** Khi nào lazy initialization phù hợp?  
**Đáp án:** Với bean tùy chọn hoặc ít được dùng mà việc trì hoãn lỗi là chấp nhận được. Không nên dùng để che resource bắt buộc bị thiếu.

**Câu 10.** User cung cấp `CatalogService` riêng. Có nên bắt họ cung cấp file default catalog nếu default bean không được dùng?  
**Đáp án:** Không cần. Có thể đặt `@ConditionalOnMissingBean` trên nested default configuration cùng `@EnableConfigurationProperties` để chỉ bind location và đọc file khi default service thực sự cần.

## 16. Ghi nhớ và tài liệu tham khảo

- Condition match chỉ cho phép Spring đăng ký cấu hình/bean definition; bean vẫn có thể thất bại ở binding, validation, dependency injection, factory method hoặc initialization.
- `@ConditionalOnProperty` kiểm tra Environment; `@ConditionalOnResource` kiểm tra resource presence. Không annotation nào xác nhận nội dung file hợp lệ.
- `@ConfigurationProperties` kết hợp `@Validated` và Jakarta constraints giúp phát hiện dữ liệu sai trước khi bean phụ thuộc được tạo.
- Dùng `ResourceLoader`/`Resource` để đọc classpath, file hoặc URL; đóng stream và xử lý IOException có ngữ cảnh.
- Kiểm tra tài nguyên trong bean/service, không đọc file hoặc gọi network trong condition.
- Mandatory dependency nên fail fast với thông báo cụ thể; optional dependency cần fallback rõ ràng; remote dependency cần timeout, retry và readiness policy.
- `--debug` hiển thị condition evaluation report; exception chain và `FailureAnalyzer` giúp chẩn đoán lỗi tạo bean.
- `ApplicationContextRunner` cho phép test cả match/no-match và các lỗi phát sinh sau khi condition match.

Tài liệu chính thức Spring Boot 3.3.13 và Spring Framework 6.1:

1. [Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html) — condition annotations, resource conditions, bean registration và `ApplicationContextRunner`.
2. [Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html) — property sources, `@ConfigurationProperties`, validation và external config files.
3. [SpringApplication — Startup Failure and Lazy Initialization](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html) — `FailureAnalyzer`, `--debug` và giới hạn của lazy initialization.
4. [ConditionalOnProperty Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html) — quy tắc match property và `havingValue`/`matchIfMissing`.
5. [ConditionalOnResource Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnResource.html) — resource condition.
6. [ConfigurationProperties Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html) — binding external properties.
7. [Resource Javadoc — Spring Framework 6.1](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/io/Resource.html) — `exists()`, `isReadable()`, `getInputStream()` và resource descriptions.
8. [ResourceLoader Javadoc — Spring Framework 6.1](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/io/ResourceLoader.html) — tạo resource theo location.
9. [ApplicationContextRunner Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html) — kiểm thử auto-configuration trong context cô lập.
