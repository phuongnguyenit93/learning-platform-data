# Nạp nguồn kiểm thử bằng @TestPropertySource và hiểu giới hạn Config Data

## 1. Mục tiêu bài học

Trong Spring Boot, cùng một ứng dụng có thể được chạy trong nhiều môi trường nhờ externalized configuration. Khi viết integration test, chúng ta thường muốn ghi đè một số giá trị như `app.client.timeout`, `app.feature.enabled`, URL của server giả, hoặc thông tin kết nối cơ sở dữ liệu dành riêng cho kiểm thử.

Spring TestContext Framework cung cấp `@TestPropertySource` để thêm các **nguồn property dành cho bài test** vào `Environment` của application context. Đây là cơ chế tiện lợi khi test cần vài giá trị inline hoặc một file `.properties` nhỏ.

Ví dụ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

@SpringBootTest
@TestPropertySource(properties = {
    "app.client.timeout=150ms",
    "app.client.enabled=false"
})
class ClientConfigurationTest {

    @Test
    void contextLoads() {
    }
}
~~~

Nhưng `@TestPropertySource` **không phải** công cụ nạp toàn bộ Spring Boot Config Data. Boot Config Data xử lý `application.yml`, `application-{profile}.yml`, multi-document activation, location groups và `spring.config.import` theo quy trình khởi động riêng. Test-specific property source có thể ghi đè giá trị của Config Data sau khi được thêm vào context, nhưng điều đó không làm nó sở hữu mọi chức năng của Config Data.

Bài này hướng đến sáu kết quả:

1. Biết dùng `properties` và `locations` trong `@TestPropertySource`.
2. Hiểu đường dẫn file, kế thừa annotation và thứ tự ưu tiên.
3. Phân biệt nạp file `.properties` với nạp YAML bằng Boot Config Data.
4. Chọn `@ActiveProfiles`, `@SpringBootTest(properties)` và `@DynamicPropertySource` đúng tình huống.
5. Hiểu rủi ro của các property được Boot đọc rất sớm.
6. Xây bài test ổn định, không phụ thuộc môi trường developer hoặc làm lộ secret.

## 2. PropertySource, Environment và Binder

Trong Spring Framework, `Environment` duy trì tập `PropertySource`. Mỗi source có thể góp giá trị cho một key. Khi nhiều source cùng khai báo `app.client.timeout`, source có độ ưu tiên cao hơn thường quyết định giá trị hiệu lực.

~~~text
application.yml / application-test.yml
               |
        Boot Config Data
               |
               v
           Environment
               ^
               |
     @TestPropertySource
      |           |
 inline values  .properties file
               |
               v
      @ConfigurationProperties
               |
               v
           Bean under test
~~~

`@TestPropertySource` cung cấp nguồn giá trị vào `Environment` của test context. Sau đó `@Value` hoặc `@ConfigurationProperties` có thể tiêu thụ chúng.

Ví dụ, mặc định:

~~~properties
app.client.timeout=3s
~~~

Test khai báo:

~~~java
@TestPropertySource(properties = "app.client.timeout=200ms")
~~~

Nếu source test được áp vào context như dự kiến, một bean `@ConfigurationProperties` sẽ nhận timeout `200ms` thay vì `3s`.

**Hai câu hỏi cần phân biệt:** nguồn đã có giá trị trong `Environment` chưa, và bean đã bind/chuyển đổi kiểu đúng chưa? Một key có mặt không có nghĩa mọi bean đã được đăng ký hoặc mọi quy tắc validation đã thành công.

## 3. Ví dụ hoàn chỉnh với @ConfigurationProperties

Lớp:

~~~java
package com.example.demo.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        Duration timeout,
        boolean enabled,
        String endpoint
) {}
~~~

Ứng dụng:

~~~java
package com.example.demo;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {}
~~~

Tài nguyên mặc định:

~~~yaml
# src/main/resources/application.yml
app:
  client:
    timeout: 3s
    enabled: true
    endpoint: "https://default.example.test"
~~~

Test:

~~~java
package com.example.demo;

import com.example.demo.config.ClientProperties;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@TestPropertySource(properties = {
    "app.client.timeout=250ms",
    "app.client.enabled=false",
    "app.client.endpoint=https://mock.example.test"
})
class ClientPropertiesTest {

    @Autowired ClientProperties properties;

    @Test
    void bindsTestValues() {
        assertThat(properties.timeout())
            .isEqualTo(Duration.ofMillis(250));
        assertThat(properties.enabled()).isFalse();
        assertThat(properties.endpoint())
            .isEqualTo("https://mock.example.test");
    }
}
~~~

Spring Boot sẽ chuyển `250ms` thành `Duration` và `false` thành `boolean` khi binding. Annotation không sửa nội dung `application.yml`; nó chỉ đóng góp giá trị vào context của bài test.

### 3.1. Vì sao test nên dùng endpoint giả?

Nếu test dùng một URL production, có thể vô tình gọi hệ thống thật. Tốt hơn là sử dụng stub/mock server hoặc endpoint không định tuyến được trong test không gửi request. Khi cần server thật của test, tạo server trong test lifecycle và truyền URL động bằng cơ chế phù hợp.

### 3.2. Khi nào không cần Spring context?

Một unit test thuần Java với object đã được khởi tạo trực tiếp không được TestContext tự đưa property vào. Ví dụ:

~~~java
ClientProperties props =
        new ClientProperties(Duration.ofSeconds(1), true, "local");
~~~

Không có Binder, không có Spring `Environment` và `@TestPropertySource` không liên quan. Chỉ dùng Spring test annotations khi cần xác nhận behavior của Spring context hoặc binding.

## 4. Cú pháp inline properties

`@TestPropertySource` có thuộc tính `properties` để khai báo một hoặc nhiều chuỗi key/value:

~~~java
@TestPropertySource(properties = {
    "demo.name=integration",
    "demo.port=18080",
    "demo.mode:test"
})
~~~

Spring Test hỗ trợ cú pháp Java properties như `key=value`, `key:value` hoặc các dạng phân tách hợp lệ. Nên thống nhất **`key=value`** để dễ đọc và tránh thay đổi literal không cần thiết.

### 4.1. Các giá trị có định dạng đặc biệt

Ví dụ:

~~~java
@TestPropertySource(properties = {
    "client.connect-timeout=500ms",
    "client.endpoint=https://api.example.test/v1?mode=fast",
    "client.enabled=true"
})
~~~

Dấu `=` trong URL query là dữ liệu thuộc value, không phải một property mới. Tuy nhiên, dữ liệu phức tạp, multiline, PEM hoặc credential không nên được nhồi vào annotation. Hãy chọn một fixture thích hợp hoặc nguồn runtime bảo mật.

### 4.2. Không đưa credential thật vào source code test

Một chuỗi hardcode trong annotation vẫn được commit vào Git và đi vào test artifacts. Dùng fake token hoặc sandbox account với quyền hạn tối thiểu; không đặt token production trong `@TestPropertySource`.

### 4.3. Test context cache và literal strings

Spring TestContext dùng thông tin test properties để xác định khóa cache của context. Hai class dùng cùng ý nghĩa nhưng biểu diễn literal khác nhau có thể hạn chế khả năng tái sử dụng context:

~~~java
@TestPropertySource(properties = "demo.port=8081")
~~~

và:

~~~java
@TestPropertySource(properties = "demo.port = 8081")
~~~

Nên dùng format thống nhất trong test suite để giảm số lần khởi động context không cần thiết.

## 5. Đọc file qua locations

Cấu trúc:

~~~text
src/test/resources/
└── config/
    └── client-test.properties
~~~

Nội dung:

~~~properties
app.client.timeout=400ms
app.client.enabled=false
app.client.endpoint=https://stub.example.test
~~~

Bài test:

~~~java
@SpringBootTest
@TestPropertySource(
    locations = "classpath:/config/client-test.properties"
)
class ClientFileTest {
}
~~~

`locations` hoặc alias `value` nhận một hoặc nhiều Spring resource locations. Theo mặc định, Spring Test hỗ trợ file theo định dạng Java `.properties` truyền thống hoặc XML properties tương ứng.

### 5.1. Đường dẫn tương đối

Giả sử test class thuộc package `com.example.demo`. Khi viết:

~~~java
@TestPropertySource("client-test.properties")
~~~

thì đường dẫn trần được hiểu tương đối theo **package của test class**, tương đương một resource classpath như:

~~~text
classpath:com/example/demo/client-test.properties
~~~

Nó không tự lấy đường dẫn tương đối theo thư mục nơi bạn chạy Maven/Gradle.

### 5.2. Đường dẫn từ gốc classpath

~~~java
@TestPropertySource("/config/client-test.properties")
~~~

hoặc:

~~~java
@TestPropertySource("classpath:/config/client-test.properties")
~~~

làm rõ vị trí resource tính từ classpath root.

### 5.3. Nhiều file

~~~java
@TestPropertySource(locations = {
    "classpath:/config/common-test.properties",
    "classpath:/config/payment-test.properties"
})
~~~

Có thể sử dụng để chia fixture. Nếu cùng key được đặt ở nhiều file, cần kiểm soát thứ tự/precedence thay vì xem đó là cơ chế merge phức tạp. Tránh phân tán một cấu hình quan trọng ra quá nhiều file.

### 5.4. Resource không tồn tại

Nếu location bắt buộc không tồn tại hoặc không đọc được, test context có thể thất bại ngay khi khởi tạo. Kiểm tra đúng tên file, package, spelling, đường dẫn và việc resource có được copy vào test classpath không.

## 6. Không chỉ định locations và properties

Annotation rỗng:

~~~java
@TestPropertySource
class MyIntegrationTest {
}
~~~

không có nghĩa chỉ “bật test properties” mà không đọc gì. Spring TestContext có convention tìm file mặc định cùng tên class.

Nếu class là `com.example.demo.MyIntegrationTest`, vị trí dự kiến:

~~~text
classpath:com/example/demo/MyIntegrationTest.properties
~~~

Nếu file không được tìm thấy, quá trình tạo context có thể ném `IllegalStateException`.

Do đó, nếu không chủ động dùng default-file convention, hãy khai báo `properties` hoặc `locations` rõ ràng; không để `@TestPropertySource` rỗng chỉ để trang trí test.

## 7. Kết hợp file và inline

Có thể khai báo:

~~~java
@SpringBootTest
@TestPropertySource(
    locations = "classpath:/config/client-test.properties",
    properties = {
        "app.client.timeout=100ms",
        "app.client.enabled=true"
    }
)
class FastClientTest {
}
~~~

Giả sử file:

~~~properties
app.client.timeout=400ms
app.client.enabled=false
app.client.endpoint=https://stub.example.test
~~~

Theo Spring TestContext, **inline test properties có ưu tiên cao hơn test properties nạp qua locations**. Giá trị dự kiến:

| Key | File | Inline | Giá trị hiệu lực |
| --- | --- | --- | --- |
| `app.client.timeout` | `400ms` | `100ms` | `100ms` |
| `app.client.enabled` | `false` | `true` | `true` |
| `app.client.endpoint` | Stub URL | Không đặt | Stub URL |

Cách này phù hợp nếu nhiều test dùng chung fixture nhưng một test chỉ cần override nhỏ. Khi số lượng thay đổi quá lớn, cân nhắc tạo fixture khác hoặc dùng profile chuyên biệt.

## 8. Thứ tự ưu tiên với các nguồn khác

Spring TestContext mô tả các test property sources có độ ưu tiên cao hơn nhiều nguồn thông thường, bao gồm OS environment, Java system properties và những application property sources thông dụng.

Một vài quy tắc quan trọng:

- `@TestPropertySource(properties = ...)` cao hơn `@TestPropertySource(locations = ...)`.
- `@DynamicPropertySource` được Spring TestContext mô tả là nguồn có precedence cao hơn `@TestPropertySource`.
- Spring Boot cũng có nguồn từ `@SpringBootTest(properties = ...)` và test slice annotations, cùng những quy tắc precedence theo cách Boot chuẩn bị context.

**Khuyến nghị thực tế:** không viết cùng một key tại nhiều annotation chỉ để dựa vào thứ tự ưu tiên. Nếu có tình huống thật sự phải kết hợp, hãy assert giá trị cuối từ `Environment` và tham chiếu tài liệu đúng phiên bản framework đang dùng.

### 8.1. Vì sao precedence ảnh hưởng test?

Ví dụ file mặc định đặt:

~~~properties
app.client.timeout=3s
~~~

nhưng một superclass test có:

~~~java
@TestPropertySource(properties = "app.client.timeout=1s")
~~~

và subclass có:

~~~java
@TestPropertySource(properties = "app.client.timeout=200ms")
~~~

Nếu inheritance được bật, giá trị của subclass có thể ghi đè theo merge rules. Nếu một dynamic source cùng key tồn tại, hành vi hiệu lực còn phụ thuộc nguồn dynamic và thứ tự đã đăng ký. Test cần cố ý sử dụng một nguồn có chủ quyền cho giá trị quan trọng.

## 9. Giới hạn lớn: YAML không được hỗ trợ mặc định

Spring Boot nạp các file:

~~~text
application.yml
application.yaml
application-test.yml
~~~

thông qua Config Data. Nhưng `@TestPropertySource` không tự dùng Boot YAML loader khi bạn khai báo:

~~~java
@TestPropertySource("classpath:/client-test.yml")
~~~

Theo tài liệu Spring Boot, YAML không được nạp trực tiếp bằng `@PropertySource` hoặc `@TestPropertySource` theo cơ chế mặc định. Spring Test mặc định đọc Java Properties/XML properties; YAML là một định dạng khác.

### 9.1. Không suy rằng YAML parse thành công khi không có exception

Nếu một YAML file có cấu trúc lồng nhau:

~~~yaml
app:
  client:
    timeout: 200ms
    enabled: false
~~~

thì một reader Java properties có thể diễn giải từng dòng không giống mong muốn. Một test không crash chưa chứng minh đúng các key `app.client.timeout` và `app.client.enabled` đã được tạo.

Để kiểm chứng, hãy assert cả giá trị từ `Environment` và giá trị đã bind trong bean.

### 9.2. Nạp YAML đúng theo Boot Config Data

Đặt:

~~~text
src/test/resources/application-it.yml
~~~

Nội dung:

~~~yaml
app:
  client:
    timeout: 200ms
    enabled: false
~~~

Test:

~~~java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("it")
class ClientProfileTest {
}
~~~

Khi Spring Boot bootstraps test context và profile `it` active, cơ chế Config Data nạp `application-it.yml` theo quy tắc của Boot. Không cần `@TestPropertySource(locations = "...yml")`.

## 10. PropertySourceFactory tùy chỉnh từ Spring Framework 6.1

Từ Spring Framework 6.1, `@TestPropertySource` có thuộc tính `factory` cho phép chỉ định một `PropertySourceFactory` tùy chỉnh để đọc một định dạng như YAML hoặc JSON.

Ví dụ về một factory cho YAML một document:

~~~java
import java.io.IOException;
import org.springframework.boot.env.YamlPropertySourceLoader;
import org.springframework.core.env.PropertySource;
import org.springframework.core.io.support.EncodedResource;
import org.springframework.core.io.support.PropertySourceFactory;

public class SingleYamlTestFactory implements PropertySourceFactory {

    @Override
    public PropertySource<?> createPropertySource(
            String name,
            EncodedResource resource
    ) throws IOException {
        var list = new YamlPropertySourceLoader().load(
            name != null ? name : "test-yaml",
            resource.getResource()
        );

        if (list.size() != 1) {
            throw new IllegalArgumentException(
                "Expected one YAML document for this test factory"
            );
        }
        return list.get(0);
    }
}
~~~

Trong Spring Framework có `factory`:

~~~java
@TestPropertySource(
    locations = "classpath:/client-test.yml",
    factory = SingleYamlTestFactory.class
)
class ClientTest {
}
~~~

Ví dụ này phục vụ file YAML đơn, không phải một implementation của Config Data loader. Nếu có nhiều YAML documents, factory phải xử lý chúng theo một policy rõ ràng.

**Quan trọng:** custom factory cho phép parse YAML thành `PropertySource` nhưng không tự hỗ trợ `spring.config.import`, `spring.config.activate.on-profile`, location groups, profile-specific resolution và các semantics khác của Spring Boot Config Data. Nếu mục đích là kiểm thử chúng, hãy dùng Boot Config Data trực tiếp.

## 11. Config Data khác TestPropertySource ở đâu?

Spring Boot Config Data xử lý:

- `application.properties`, `application.yml` và các biến thể tên được hỗ trợ.
- `application-{profile}.properties` và `application-{profile}.yml`.
- Multi-document YAML và multi-document properties.
- `spring.config.activate.on-profile` và những điều kiện activation khác.
- `spring.config.import` để nhập thêm Config Data.
- `optional:` cho location được phép thiếu.
- `spring.config.location` và `spring.config.additional-location`.
- Location groups, property-source ordering và một số quy tắc ưu tiên đặc thù.

Ngược lại, `@TestPropertySource` chủ yếu lấy một tập key/value và thêm nó vào Environment của test context. Nó **không phải một entrypoint tổng quát** cho mọi quy tắc Config Data.

### 11.1. Đọc được file chưa phải đã chạy Config Data processing

Một custom factory có thể biến YAML thành map:

~~~text
app.client.timeout -> 200ms
app.client.enabled -> false
~~~

Nhưng nếu file cũng chứa:

~~~yaml
spring:
  config:
    import: "classpath:/config/extra.yml"
~~~

thì factory có thể chỉ đưa chuỗi `spring.config.import` vào map. Điều đó không tự khiến Boot quay lại chạy Config Data resolver để nhập `extra.yml`.

### 11.2. Hậu quả với kiểm thử

Nếu bạn đang test **chức năng của Binder** trên vài property đã được định nghĩa, `@TestPropertySource` là đủ.

Nếu bạn đang test **quy tắc nạp Config Data** gồm profile, import hoặc location precedence, dùng một Config Data file được Boot nạp thật. Hai mục tiêu khác nhau cần setup khác nhau.

## 12. Các property được đọc rất sớm

Một số thuộc tính điều khiển việc Spring Boot đi tìm Config Data:

~~~properties
spring.config.name=custom
spring.config.location=classpath:/cfg/
spring.config.additional-location=file:./external/
~~~

Boot cần biết những giá trị này **trước lúc tìm các file**. Tài liệu Boot hướng dẫn cung cấp chúng từ early environment properties, ví dụ OS environment variable, JVM system property hoặc command-line argument.

Không nên kỳ vọng:

~~~java
@TestPropertySource(properties =
    "spring.config.location=classpath:/cfg/")
~~~

sẽ khiến Boot khởi động lại toàn bộ bước tìm Config Data khi annotation được xử lý theo TestContext.

### 12.1. Vì sao Environment cuối có thể gây hiểu nhầm?

Một assertion:

~~~java
assertThat(environment.getProperty("spring.config.location"))
    .isEqualTo("classpath:/cfg/");
~~~

chỉ cho biết key có mặt trong `Environment` sau khi context đã được chuẩn bị. Nó **không chứng minh** file ở `classpath:/cfg/` đã được nạp ở giai đoạn Config Data bootstrap.

Muốn kiểm thử location, hãy assert một key chỉ tồn tại trong file đích, ví dụ `loaded.from.custom.location=true`.

### 12.2. Những giải pháp phù hợp hơn

- Dùng `@ActiveProfiles` cho `application-it.yml` nếu chỉ cần test profile.
- Đặt `spring.config.import` trong một **Config Data document thực sự** nếu muốn test import.
- Với custom Config Data location, dùng test harness thiết lập early properties đúng pha.
- Không dùng một annotation test source thông thường để thay thế toàn bộ early Boot configuration.

## 13. @ActiveProfiles và application-test.yml

`@ActiveProfiles` là annotation của Spring TestContext để xác định những active profiles cho application context của bài test.

~~~java
@SpringBootTest
@ActiveProfiles("test")
class PaymentIntegrationTest {
}
~~~

Ví dụ:

~~~text
src/main/resources/application.yml
src/test/resources/application-test.yml
~~~

Spring Boot thường nạp `application-test.yml` theo cơ chế Config Data khi profile `test` được kích hoạt, với những quy tắc precedence tương ứng.

`application-test.yml`:

~~~yaml
payment:
  gateway:
    endpoint: "https://sandbox.example.test"
    connect-timeout: 100ms
    enabled: false
~~~

Bài test có thể inject `@ConfigurationProperties` bean để kiểm tra timeout và endpoint, hoặc kiểm tra behavior của service tương ứng.

### 13.1. Kết hợp với inline override

~~~java
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties =
    "payment.gateway.connect-timeout=50ms")
class FastGatewayTest {
}
~~~

Boot nạp cấu hình profile trước theo Config Data; TestContext thêm một override phù hợp. Đây là cách ngắn gọn để giữ phần lớn cấu hình ở YAML nhưng thay một field trong riêng test class.

### 13.2. Khi muốn test chính hành vi profile

Nếu mục tiêu là kiểm chứng profile `test` chọn đúng document, **không** thêm inline override cho chính key mà bạn muốn quan sát. Điều đó có thể che đi lỗi trong file profile.

## 14. Multi-document YAML và activation

Boot Config Data có thể xử lý:

~~~yaml
app:
  cache:
    ttl: 30s

---
spring:
  config:
    activate:
      on-profile: it

app:
  cache:
    ttl: 1s
~~~

Với `@ActiveProfiles("it")`, document sau có thể được kích hoạt và ghi đè giá trị `app.cache.ttl` theo quy tắc Config Data.

Một generic `PropertySourceFactory` không tự hiểu rằng document thứ hai chỉ được dùng khi active profile `it`. Nếu test phải kiểm chứng logic activation, sử dụng Boot Config Data.

### 14.1. Profile-specific file khác document activation

Hai cơ chế:

~~~text
application-it.yml
~~~

và:

~~~yaml
spring:
  config:
    activate:
      on-profile: it
~~~

có thể cùng phục vụ cấu hình theo profile, nhưng chúng được Boot xử lý theo những quy tắc và vị trí riêng. Không cho rằng `@TestPropertySource` tự tham gia các bước đó.

## 15. Kiểm thử spring.config.import đúng cách

Giả sử test resources:

~~~text
src/test/resources/
  application-it.yml
  config/remote-it.yml
~~~

`application-it.yml`:

~~~yaml
spring:
  config:
    import: "classpath:/config/remote-it.yml"

app:
  client:
    timeout: 1s
~~~

`config/remote-it.yml`:

~~~yaml
app:
  client:
    timeout: 80ms
    enabled: false
~~~

Bài test:

~~~java
@SpringBootTest
@ActiveProfiles("it")
class ConfigDataImportTest {

    @Autowired ClientProperties properties;

    @Test
    void importIsApplied() {
        assertThat(properties.timeout())
            .isEqualTo(Duration.ofMillis(80));
        assertThat(properties.enabled()).isFalse();
    }
}
~~~

Trong trường hợp đơn giản này, Spring Boot xử lý `spring.config.import` khi nạp Config Data; values của file import được ưu tiên phù hợp với quy tắc Boot so với document nhập nó.

### 15.1. Khác với import nằm trong file @TestPropertySource

Nếu `client-test.properties` được nạp qua `@TestPropertySource` chứa:

~~~properties
spring.config.import=classpath:/config/remote-it.yml
~~~

thì không nên suy ra Boot đã nhập `remote-it.yml` theo Config Data semantics. Chỉ kiểm tra `spring.config.import` có mặt trong `Environment` là chưa đủ; phải kiểm tra key đặc trưng của file import.

### 15.2. optional import

~~~yaml
spring:
  config:
    import: "optional:classpath:/config/remote-it.yml"
~~~

`optional:` cho phép location được phép vắng mặt theo quy tắc Boot. Nếu muốn kiểm thử lỗi khi thiếu file bắt buộc, hãy bỏ `optional:` và thiết kế test assert failure phù hợp.

## 16. @SpringBootTest(properties) là lựa chọn gì?

Spring Boot cung cấp thuộc tính `properties` trên `@SpringBootTest`:

~~~java
@SpringBootTest(properties = {
    "app.client.timeout=75ms",
    "app.client.enabled=true"
})
class ClientBootTest {
}
~~~

Nó tương tự `@TestPropertySource(properties=...)` ở mục tiêu **đưa override cố định vào test context**, nhưng là một thuộc tính riêng do Boot hỗ trợ.

Bảng so sánh:

| Nhu cầu | Cách thường phù hợp |
| --- | --- |
| Vài giá trị cho một Boot integration test | `@SpringBootTest(properties=...)` |
| Nguồn test theo Spring TestContext | `@TestPropertySource(properties=...)` |
| File fixture dạng properties | `@TestPropertySource(locations=...)` |
| YAML và profile-specific Config Data | `@ActiveProfiles` + `application-{profile}.yml` |
| Dynamic port, container URL | `@DynamicPropertySource` |
| Test auto-config và binding gọn | `ApplicationContextRunner` |
| Cấu hình cần bootstrapping sớm | Early environment trong test harness |

Không cần dùng đồng thời cả `@SpringBootTest(properties)` và `@TestPropertySource(properties)` để khai báo lại cùng key nếu không có test case về precedence.

## 17. @DynamicPropertySource cho dữ liệu sinh khi chạy

Một số giá trị chỉ được biết sau khi test resource đã khởi động, chẳng hạn port của Testcontainers PostgreSQL hoặc WireMock server.

`@DynamicPropertySource` đăng ký một supplier cho giá trị:

~~~java
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

@DynamicPropertySource
static void registerDynamicValues(DynamicPropertyRegistry registry) {
    registry.add("app.remote.port", () -> mockServer.getPort());
}
~~~

Đây là lựa chọn tốt hơn việc hardcode port ngẫu nhiên vào `@TestPropertySource`.

### 17.1. Ví dụ Testcontainers

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class RepositoryIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void datasource(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Test
    void repositoryWorks() {
        // Integration test against the container.
    }
}
~~~

Cần các dependency Testcontainers, môi trường container phù hợp và cấu hình service thực tế. Method `@DynamicPropertySource` không tự quản lý toàn bộ lifecycle của container.

### 17.2. Tránh khai báo cùng key ở hai nơi

Ví dụ:

~~~java
@TestPropertySource(properties =
    "spring.datasource.url=jdbc:h2:mem:test")
~~~

cùng lúc đăng ký `spring.datasource.url` bằng dynamic supplier sẽ tạo cạnh tranh nguồn. Nếu test thực sự yêu cầu PostgreSQLContainer, bỏ key H2 tĩnh hoặc tách hai test configurations.

Theo Spring TestContext, dynamic properties có độ ưu tiên cao khi cùng key, nhưng viết rõ một nguồn có thẩm quyền dễ hiểu và ổn định hơn.

## 18. Kế thừa property sources từ test superclass

`@TestPropertySource` hỗ trợ kế thừa `locations` và `properties` từ lớp cha theo mặc định.

~~~java
@TestPropertySource(properties = {
    "app.cache.enabled=false",
    "app.client.timeout=1s"
})
abstract class BaseIntegrationTest {
}
~~~

Subclass:

~~~java
@SpringBootTest
@TestPropertySource(properties = {
    "app.client.timeout=100ms"
})
class FastIntegrationTest extends BaseIntegrationTest {
}
~~~

Spring TestContext có thể merge cấu hình inherited với local declarations theo quy tắc annotation, để subclass thay một số key.

### 18.1. inheritLocations và inheritProperties

~~~java
@TestPropertySource(
    inheritLocations = false,
    inheritProperties = false,
    properties = "app.client.timeout=100ms"
)
~~~

Hai flag lần lượt kiểm soát kế thừa file locations và inline properties từ lớp cha. Mặc định thường là `true`. Nếu dùng `false`, hãy hiểu đó là một hành động **thay thế** một phần cấu hình test được kế thừa, không phải chỉ đổi giá trị của một key.

### 18.2. Meta-annotations và repeatable annotations

`@TestPropertySource` có thể xuất hiện ở các composed annotations và trong các test configurations phức tạp. Spring TestContext có quy tắc merge và precedence cho nguồn trực tiếp, nguồn meta-present và inherited sources.

Với nhiều cấp kế thừa, hãy giữ setup tường minh; tránh tạo một đồ thị override khiến không ai biết key nào thắng.

## 19. TestContext caching và cấu hình test

Spring TestContext cache `ApplicationContext` để tránh khởi tạo lại những context có cấu hình tương đương. Các thành phần như locations, profiles, test properties và context customizers góp phần xác định cache key.

Hậu quả:

- Một inline property mới có thể dẫn tới context khác.
- Hai class có cấu hình tương thích có thể tái sử dụng context.
- Một bean mutable bị test sửa trực tiếp có thể ảnh hưởng test khác dùng cùng context.
- Một dynamic supplier phụ thuộc resource thay đổi giữa subclasses có thể yêu cầu điều chỉnh lifecycle/cache.

### 19.1. Không sửa Environment global tùy tiện

Một anti-pattern:

~~~java
@BeforeEach
void setUp() {
    System.setProperty("app.client.timeout", "100ms");
}
~~~

mà không restore có thể làm ảnh hưởng test khác trong cùng JVM hoặc test chạy song song.

Ưu tiên khai báo test property trong annotation hoặc runner trước khi context được tạo. Nếu bắt buộc sửa system property, phải restore và kiểm soát concurrency.

### 19.2. @DirtiesContext không phải thuốc chữa chung

`@DirtiesContext` làm context hiện tại không được tái sử dụng theo một phạm vi phù hợp. Nó có thể hữu ích khi state thay đổi khó reset, nhưng khởi động lại context rất tốn chi phí. Đừng dùng nó để che test thiết kế thiếu cô lập.

## 20. Test slices và đăng ký bean

`@SpringBootTest` thường nạp application context rộng, còn các slice như `@WebMvcTest` hoặc `@DataJpaTest` giới hạn phạm vi bean/auto-configuration.

Một bean `@ConfigurationProperties` có thể không tự xuất hiện trong một slice test nếu nó không thuộc phạm vi được nạp.

Ví dụ cấu hình nhỏ:

~~~java
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootConfiguration
@EnableConfigurationProperties(ClientProperties.class)
class ClientBindingTestConfig {
}
~~~

Test:

~~~java
@SpringBootTest(classes = ClientBindingTestConfig.class)
@TestPropertySource(properties = {
    "app.client.timeout=125ms",
    "app.client.enabled=true",
    "app.client.endpoint=https://stub.example.test"
})
class ClientBindingTest {
}
~~~

Nếu test không tìm thấy `ClientProperties`, kiểm tra registration trước khi nghĩ `@TestPropertySource` không hoạt động. Annotation chỉ thêm property source; nó không tự tạo bean target.

## 21. Kiểm thử binding và validation

Giả sử:

~~~java
import java.time.Duration;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.retry")
public record RetryProperties(
    @NotNull Duration delay
) {}
~~~

Test có:

~~~java
@TestPropertySource(properties = "app.retry.delay=500ms")
~~~

Binder có thể chuyển sang `Duration.ofMillis(500)`. Nếu chuỗi sai:

~~~java
@TestPropertySource(properties = "app.retry.delay=tomorrow")
~~~

thì lỗi có thể phát sinh ở **type conversion** khi tạo bean.

Một property rỗng hoặc thiếu thuộc trường bắt buộc có thể vi phạm Bean Validation nếu provider đã được đăng ký. `@TestPropertySource` không tự bật validation; trách nhiệm nằm ở class, registration và validation infrastructure.

### 21.1. Không in rejected value chứa secret

Nếu property là password/API key, các lỗi binding có thể làm xuất hiện thông tin đầu vào trong exception/log do framework hoặc library tạo. Dùng canary giả trong test và kiểm tra output để bảo đảm secrets không lộ.

### 21.2. Test failure riêng bằng ApplicationContextRunner

Spring Boot có `ApplicationContextRunner` hữu ích khi kiểm thử configuration class hoặc auto-configuration trong context gọn:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class RetryFailureTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(RetryTestConfig.class);

    @Test
    void invalidDurationFails() {
        runner.withPropertyValues("app.retry.delay=not-a-duration")
            .run(context ->
                assertThat(context.getStartupFailure()).isNotNull());
    }
}
~~~

`RetryTestConfig` phải đăng ký `RetryProperties`. Ở đây runner cấp giá trị qua `withPropertyValues`, nên không cần `@TestPropertySource`. Chọn công cụ theo phạm vi test, không cần Spring Boot full context cho mọi case.

## 22. Cách kiểm tra property đến từ nguồn nào

Nếu test thất bại vì giá trị không như mong đợi, bắt đầu bằng việc đọc một key xác định:

~~~java
import org.springframework.core.env.Environment;

@Autowired Environment environment;

@Test
void propertyValueIsVisible() {
    assertThat(environment.getProperty("app.client.timeout"))
        .isEqualTo("250ms");
}
~~~

Sau đó kiểm tra bean:

~~~java
@Autowired ClientProperties properties;

@Test
void binderConvertedValue() {
    assertThat(properties.timeout())
        .isEqualTo(Duration.ofMillis(250));
}
~~~

Hai bước giúp phân biệt:

1. **Source/configuration problem:** key không tồn tại hoặc bị source khác override.
2. **Binding problem:** key tồn tại nhưng bean không bind được, prefix sai, conversion lỗi hoặc bean không được đăng ký.

### 22.1. Không dump Environment trong CI logs

`Environment` có thể chứa credentials từ CI, máy phát triển hoặc test container. Tránh in toàn bộ `PropertySource`, `System.getenv()` hoặc raw rejected values. Khi cần chẩn đoán, log tên key/safe source description thay vì giá trị bí mật.

### 22.2. Chẩn đoán sớm các location

Nếu test đặt `spring.config.location` nhưng không thấy file mới được nạp, đừng chỉ kiểm tra property đó. Hãy tạo một marker property duy nhất trong file đích:

~~~properties
test.location.marker=loaded
~~~

và assert `test.location.marker` trong `Environment`. Điều này chứng minh file thực sự có đóng góp dữ liệu, không chỉ tên location được đặt muộn.

## 23. Các tình huống thực tế

### 23.1. Một feature flag

~~~java
@SpringBootTest
@TestPropertySource(properties = "feature.catalog.enabled=false")
class CatalogDisabledTest {
}
~~~

Đây là trường hợp inline tốt: một key tĩnh, không cần profile hoặc file mới.

### 23.2. Một bộ fixture nhiều property

File:

~~~properties
# src/test/resources/config/payment-test.properties
payment.gateway.endpoint=https://sandbox.example.test
payment.gateway.timeout=1s
payment.gateway.enabled=false
~~~

Test:

~~~java
@SpringBootTest
@TestPropertySource(
    locations = "classpath:/config/payment-test.properties"
)
class PaymentIntegrationTest {
}
~~~

Đây là lựa chọn hợp lý khi muốn tái sử dụng nhiều cấu hình đơn giản, không cần YAML activation.

### 23.3. Test profile-specific YAML

File `src/test/resources/application-it.yml`, test:

~~~java
@SpringBootTest
@ActiveProfiles("it")
class ConfigDataProfileTest {
}
~~~

Phù hợp khi kiểm thử profile-specific Config Data.

### 23.4. Test import YAML

File `application-it.yml` có `spring.config.import=classpath:/config/extra-it.yml`. Dùng `@ActiveProfiles("it")` rồi assert marker ở file import. Không dùng một file `@TestPropertySource` làm nơi khai báo import nếu muốn xác nhận đường bootstrap Config Data.

### 23.5. Test port ngẫu nhiên

Server giả hoặc Testcontainers cấp port sau khi khởi động: dùng `@DynamicPropertySource` để đăng ký supplier. Không hardcode port vào `@TestPropertySource`.

### 23.6. Test custom early Config Data location

Khi muốn kiểm thử `spring.config.location` hoặc `spring.config.name`, cần một harness đưa giá trị vào trước Config Data processing, không chỉ thêm test property vào context sau giai đoạn đó.

## 24. Những hiểu nhầm thường gặp

### 24.1. @TestPropertySource tự nạp YAML

Sai theo mặc định. Nó có thể nạp `.properties` và XML properties; YAML cần Config Data hoặc custom factory (Framework 6.1+) với giới hạn rõ ràng.

### 24.2. @TestPropertySource chính là Config Data

Không. Nó thêm property sources vào test context. Không mặc định xử lý `spring.config.import`, profile activation hoặc location resolution của Boot.

### 24.3. Chỉ cần property tồn tại trong Environment là import đã chạy

Không. `Environment` có thể giữ một chuỗi `spring.config.import` mà Boot không sử dụng nó như directive trong đúng pha. Phải assert dữ liệu đến từ location được import.

### 24.4. @ActiveProfiles và @TestPropertySource thay thế được nhau

Không. `@ActiveProfiles` chọn active profiles; `@TestPropertySource` cung cấp key/value test-specific. Chúng bổ sung cho nhau nhưng có mục đích khác.

### 24.5. Dùng cùng key ở mọi nguồn sẽ tăng tính ổn định

Ngược lại. Nhiều nguồn có cùng key khiến test khó hiểu và dễ phụ thuộc precedence. Chọn một nguồn có chủ quyền.

### 24.6. Annotation rỗng không làm gì

Không. Nó có thể kích hoạt tìm file `ClassName.properties` theo convention và gây lỗi nếu không có file.

### 24.7. TestPropertySource tự đăng ký @ConfigurationProperties bean

Không. Bean vẫn cần scanning/enabling hoặc cách đăng ký tương ứng.

### 24.8. @TestPropertySource dùng được cho unit test Java thuần

Không nếu không có Spring TestContext application context. JUnit thuần không tự áp properties vào object.

### 24.9. Có custom YAML factory thì mọi multi-document activation hoạt động

Không. Một factory parse YAML không tự đóng vai trò Boot Config Data resolver/loader.

### 24.10. Có @DirtiesContext thì test luôn được cô lập

Không. External database, hệ thống file, static state và CI environment vẫn có thể chia sẻ; phải thiết kế test isolation đầy đủ.

## 25. Bảng lựa chọn nhanh

| Mục tiêu | Công cụ gợi ý | Vì sao |
| --- | --- | --- |
| Override 1–5 key tĩnh | `@TestPropertySource(properties=...)` | Gọn và rõ |
| Boot integration test với inline overrides | `@SpringBootTest(properties=...)` | Tích hợp trong annotation Boot |
| Nhiều key từ .properties | `@TestPropertySource(locations=...)` | Dễ tái sử dụng |
| YAML profile test | `@ActiveProfiles` + `application-it.yml` | Đúng cơ chế Boot Config Data |
| Multi-document YAML activation | Boot Config Data | Hiểu điều kiện activation |
| `spring.config.import` | File Config Data thật | Đúng giai đoạn import |
| Custom YAML fixture | `@TestPropertySource(factory=...)` nếu hỗ trợ | Chỉ parse thành PropertySource |
| Dynamic database URL | `@DynamicPropertySource` | Supplier runtime |
| Test lỗi binding riêng | `ApplicationContextRunner` | Context nhỏ, nhanh |
| Property cần được Boot đọc cực sớm | Early environment/test harness | Tránh nạp quá muộn |

## 26. Checklist triển khai test

- [ ] Test thật sự dùng Spring TestContext hoặc Boot test context.
- [ ] Chọn `properties` inline khi chỉ có ít key cố định.
- [ ] Chọn `locations` cho file `.properties` đơn giản.
- [ ] Đường dẫn resource được xác định rõ là package-relative hoặc classpath-root.
- [ ] Không dùng annotation rỗng nếu không muốn default-file detection.
- [ ] Biết inline values có thể override file locations.
- [ ] Không giả định YAML được `@TestPropertySource` load mặc định.
- [ ] Khi cần YAML hoặc Config Data semantics, dùng `@ActiveProfiles` và Boot Config Data.
- [ ] Nếu dùng custom `PropertySourceFactory`, test riêng giới hạn của nó.
- [ ] Không đưa early `spring.config.location` vào annotation rồi tin rằng Boot load lại.
- [ ] Không trùng key vô ý giữa `@DynamicPropertySource` và `@TestPropertySource`.
- [ ] Khai báo nguồn động bằng supplier khi cần.
- [ ] Hiểu `inheritLocations` và `inheritProperties` nếu kế thừa test base class.
- [ ] Dùng format inline nhất quán để cải thiện context caching.
- [ ] Tránh sửa system properties/global state không restore.
- [ ] Kiểm tra bean `@ConfigurationProperties` đã được đăng ký.
- [ ] Assert một key từ `Environment` và cả giá trị đã bind.
- [ ] Kiểm tra conversion/validation thay vì chỉ assert context loads.
- [ ] Không đưa secret production vào test resources.
- [ ] Không dump Environment hoặc raw exception chứa credential vào logs.
- [ ] Không dùng `@DirtiesContext` như mặc định cho mọi test.
- [ ] Khi kiểm thử Config Data import, assert marker property của file imported.

## 27. Bài tập suy luận

### Bài tập A: Inline override

`application.yml` có `app.timeout=3s`. Test dùng:

~~~java
@TestPropertySource(properties = "app.timeout=250ms")
~~~

Hỏi giá trị timeout nào được nhìn thấy bởi Binder trong test context thông thường?

**Gợi ý:** test-specific source có thể override giá trị Config Data của ứng dụng.

### Bài tập B: File và inline

`test-client.properties` có:

~~~properties
app.timeout=1s
app.enabled=false
~~~

Annotation:

~~~java
@TestPropertySource(
    locations = "classpath:/test-client.properties",
    properties = "app.timeout=100ms"
)
~~~

Hỏi `app.timeout` và `app.enabled` được lấy từ đâu?

**Gợi ý:** inline ưu tiên hơn file với cùng key; key không bị override vẫn đến từ file.

### Bài tập C: YAML và import

Test viết:

~~~java
@TestPropertySource("classpath:/application-it.yml")
~~~

và kỳ vọng `spring.config.import` trong YAML tự tải một file khác.

**Gợi ý:** sai cơ chế. Dùng Boot Config Data với profile `it`; custom factory parse YAML không tự thay thế Config Data.

### Bài tập D: Dynamic port

Một Testcontainer chạy PostgreSQL trên cổng ngẫu nhiên.

**Gợi ý:** đăng ký URL/username/password qua `@DynamicPropertySource` hoặc cơ chế Testcontainers integration phù hợp; đừng hardcode cổng.

### Bài tập E: Context cache

Hai test dùng cùng key/value nhưng format literal khác nhau. Vì sao có thể giảm cơ hội tái sử dụng context?

**Gợi ý:** test properties được đưa vào context cache key, bao gồm các literal cấu hình.

## 28. Kết luận

`@TestPropertySource` là công cụ hiệu quả để thêm **test-specific property sources** vào Spring `Environment`, đặc biệt khi cần override vài key hoặc dùng file `.properties` cho integration test.

Giới hạn cần nhớ: **nạp property source không đồng nghĩa chạy Spring Boot Config Data**. Những tính năng như profile-specific YAML, multi-document activation, `spring.config.import` và early location resolution cần được kiểm thử qua cơ chế Boot Config Data, không chỉ qua annotation TestContext.

Quy tắc lựa chọn:

1. Ít giá trị cố định → `@TestPropertySource(properties=...)` hoặc `@SpringBootTest(properties=...)`.
2. Nhiều giá trị trong file `.properties` → `@TestPropertySource(locations=...)`.
3. YAML/profile/import/Config Data → `@ActiveProfiles` kết hợp Config Data file được Boot nạp.
4. Giá trị sinh trong test lifecycle → `@DynamicPropertySource`.
5. Test binding/failure trong context nhỏ → `ApplicationContextRunner`.

Cuối cùng, kiểm tra kết quả ở cả `Environment` và bean, không lạm dụng nhiều nguồn cùng key, giữ test isolation, kiểm soát context caching và không bao giờ đưa credential production vào fixture.

### Tài liệu tham khảo

- [Spring Framework Reference — Context Configuration with Test Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/property-sources.html)
- [Spring Framework Reference — Dynamic Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html)
- [Spring Framework API — TestPropertySource](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/TestPropertySource.html)
- [Spring Framework API — ActiveProfiles](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/ActiveProfiles.html)
- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot Reference — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html)
