# @ActiveProfiles và application-test.yml

Trong kiểm thử Spring Boot, cùng một đoạn mã có thể phải chạy với cấu hình khác nhau: môi trường production gửi email thật, môi trường test chỉ ghi nhận yêu cầu gửi; production kết nối database và dịch vụ bên ngoài, còn test dùng database hoặc adapter cô lập. Nếu các thông số này bị trộn lẫn, test dễ chậm, không ổn định hoặc nguy hiểm vì vô tình tác động tới hệ thống thật.

**`@ActiveProfiles`** và **`application-test.yml`** giải quyết hai phần liên quan nhưng không giống nhau:

- `@ActiveProfiles("test")` thông báo cho **Spring TestContext Framework** rằng profile `test` phải hoạt động khi dựng `ApplicationContext` của bài kiểm thử.
- `application-test.yml` là **tệp cấu hình theo profile** mà cơ chế **Config Data của Spring Boot** tìm và nạp khi profile `test` hoạt động trong một ứng dụng được khởi tạo bằng Spring Boot.
- Annotation chọn **profile**; tệp YAML khai báo **giá trị cấu hình**. Spring `@Profile` quyết định **bean definition nào được kích hoạt**; Spring Boot kết hợp các property source để xác định **giá trị cuối cùng**.
- Chỉ có tên file `application-test.yml` không làm profile `test` tự bật. Và `@ActiveProfiles` không tự làm tệp YAML được xử lý trong mọi cách nạp context: bạn cần quy trình cấu hình Boot tương ứng, như `@SpringBootTest`.

Mục tiêu của bài là hiểu cơ chế, viết được ví dụ Java 17+/Spring Boot/JUnit 5, thiết kế môi trường test an toàn và chẩn đoán lỗi cấu hình mà không suy đoán từ tên file.

## 1. Bức tranh tổng thể: profile, bean và property

Hãy hình dung một ứng dụng có service chào người dùng. Trong production, service dùng tiền tố `Hello` và có thể gửi thông báo ra cổng ngoài. Trong test, tiền tố là `Xin chào` và thao tác gửi bị tắt hoặc được thay bằng một cổng ghi nhận trong bộ nhớ.

Dòng xử lý:

```text
JUnit Jupiter test
   |
   | @SpringBootTest + @ActiveProfiles("test")
   v
Spring TestContext / SpringExtension
   |
   | bootstrap ApplicationContext bằng Spring Boot
   v
SpringApplication + Config Data
   |                               |
   | application.yml               | application-test.yml
   | (giá trị chung)                | (ghi đè khi test active)
   v                               v
              Spring Environment
                       |
              +--------+---------+
              |                  |
       @Profile("!test")   @Profile("test") hoặc bean test @Import
       bean production      bean giả lập có kiểm soát
              |                  |
              +--------+---------+
                       |
             Bean được inject vào service
                       |
                 Assertion của test
```

Cần phân biệt ba đối tượng:

| Khái niệm | Chức năng | Ví dụ |
|---|---|---|
| **Active profile** | Tên môi trường đang được Spring đánh dấu hoạt động | `test`, `integration`, `local` |
| **Property source** | Nơi cung cấp các key–value đưa vào Spring `Environment` | `application.yml`, `application-test.yml`, env var, test property |
| **Conditional bean definition** | Quyết định bean nào được tạo theo profile | `@Profile("!test")` hoặc `@Profile("test")` |

Bật profile **không đồng nghĩa** mọi dependency đã tự đổi thành fake. Chỉ các bean và cấu hình thật sự có điều kiện hoặc đọc property tương ứng mới thay đổi hành vi.

## 2. `@ActiveProfiles` làm chính xác điều gì?

`@ActiveProfiles` nằm trong package:

```java
import org.springframework.test.context.ActiveProfiles;
```

Cách dùng phổ biến với integration test:

```java
@SpringBootTest
@ActiveProfiles("test")
class MyIntegrationTest {
    // Các @Test dùng ApplicationContext với profile "test".
}
```

Ví dụ trên chỉ minh họa annotation; chưa phải test hoàn chỉnh.

Đối với TestContext, annotation này:

1. Xác định profile hoặc các profile active khi context của test được nạp.
2. Khiến Spring xem xét điều kiện `@Profile` trên `@Component`, `@Configuration` hoặc method `@Bean`.
3. Tham gia cấu hình context dùng để xác định khả năng tái sử dụng từ cache.
4. Hỗ trợ kế thừa profile từ superclass hoặc enclosing class theo quy tắc của Spring TestContext.
5. Có thể chỉ định nhiều profile và `ActiveProfilesResolver` tùy chỉnh khi có nhu cầu đặc biệt.

Ví dụ nhiều profile:

```java
@ActiveProfiles({"test", "integration"})
class DatabaseIntegrationTest {
    // Minh họa: cả hai profile đều được kích hoạt.
}
```

**Các điểm dễ nhầm:**

- `@ActiveProfiles` là annotation của **Spring TestContext**, không phải cách cấu hình chung cho một ứng dụng production đang chạy bằng `java -jar`.
- Nếu một test dùng JUnit thuần, không có SpringExtension/Boot TestContext, việc viết annotation này **không tự nạp context**.
- Nếu bạn đã khai báo `@ActiveProfiles` trên test, **TestContext lấy profile theo annotation/resolver**, không đơn giản để biến môi trường hoặc system property `spring.profiles.active` lặng lẽ ghi đè annotation. Đây là hành vi được tài liệu Spring TestContext nêu rõ.
- Tên profile `test` chỉ là quy ước phổ biến, không phải một profile đặc biệt có mọi tính năng giả lập tự động.
- Với Spring Boot 3.x/JUnit Jupiter, `@SpringBootTest` đã tích hợp `SpringExtension`; không cần thêm `@ExtendWith(SpringExtension.class)` chỉ để kích hoạt `@ActiveProfiles`.

Để kiểm tra profile đã active, có thể inject `Environment` và đọc `getActiveProfiles()` hoặc dùng `acceptsProfiles(Profiles.of("test"))`. **Đọc profile là bước chẩn đoán**, còn test nên assert cả giá trị cấu hình hoặc hành vi cần bảo vệ.

## 3. `application-test.yml` là file gì và được nạp lúc nào?

Spring Boot thường tìm các file Config Data như `application.properties` hoặc `application.yml`. Khi có profile `test`, nó còn cân nhắc các file dạng **`application-{profile}.yml`**, trong trường hợp này là `application-test.yml`, tại những location cấu hình hợp lệ.

Ví dụ cấu trúc:

```text
src/
├── main/
│   ├── java/
│   │   └── ... mã ứng dụng ...
│   └── resources/
│       └── application.yml
└── test/
    ├── java/
    │   └── ... JUnit test ...
    └── resources/
        └── application-test.yml
```

Trong một dự án Gradle/Maven thông thường, `src/test/resources` nằm trên **test runtime classpath**. Tệp ở đó phục vụ test và không được đóng gói cùng artifact production mặc định. Đặt cấu hình riêng test ở đây là cách phân tách hợp lý.

**Cơ chế nạp điển hình với `@SpringBootTest + @ActiveProfiles("test")`:**

1. Boot tạo `ApplicationContext` thông qua `SpringApplication`.
2. Cơ chế Config Data đọc cấu hình chung `application.yml`.
3. Vì profile `test` active, Boot nạp thêm `application-test.yml` từ vị trí tìm thấy.
4. Với những property cùng tên tại cùng mức location phù hợp, giá trị trong cấu hình theo profile có thể **ghi đè** giá trị chung.
5. Bean có `@ConfigurationProperties`, `@Value` hoặc truy cập `Environment` sẽ nhận giá trị hiệu lực từ tổng hợp property sources.
6. Những bean gắn `@Profile` được tạo hoặc loại theo tập profile đang active.

Chẳng hạn:

**`src/main/resources/application.yml`**

```yaml
app:
  welcome:
    prefix: "Hello"
    sending-enabled: true
    max-length: 80
```

**`src/test/resources/application-test.yml`**

```yaml
app:
  welcome:
    prefix: "Xin chào"
    sending-enabled: false
```

Trong test profile, kết quả mong đợi:

| Key | File chung | File test | Giá trị hiệu lực trong ví dụ |
|---|---|---|---|
| `app.welcome.prefix` | `Hello` | `Xin chào` | `Xin chào` |
| `app.welcome.sending-enabled` | `true` | `false` | `false` |
| `app.welcome.max-length` | `80` | Không khai báo | `80` |

Tức là **file theo profile chỉ cần khai báo những property khác biệt**; property chung vẫn có thể được dùng. Không cần sao chép toàn bộ `application.yml` vào `application-test.yml`, vì việc nhân bản làm tăng chi phí duy trì và dễ khiến cấu hình test lỗi thời.

**Quan trọng:** ví dụ trên giả định không có nguồn ưu tiên cao hơn cùng định nghĩa các key ấy. Environment variables, system properties, test property inline, cấu hình động hoặc nguồn ngoài có thể thay đổi giá trị cuối cùng. Vì vậy khi debug phải xem **effective property**, không chỉ đọc một tệp.

## 4. Test profile không nên dùng cấu hình production

Một môi trường test an toàn cần có ranh giới thực tế, không chỉ nhãn `test`. Ví dụ:

- Endpoint email, payment, message broker, object storage phải là fake, mock server, container cô lập hoặc tài khoản sandbox được cấp phép.
- Database test phải dùng schema/database riêng và dữ liệu test tự quản lý; không được nhầm với dữ liệu thật.
- Credential thật không được ghi vào source-controlled YAML. Dùng cơ chế secret của CI/hệ thống chạy test cho credential test nếu bắt buộc.
- Mọi side effect ngoài database như gửi message, webhook, file hoặc request HTTP thật cần được kiểm soát riêng; transaction rollback không tự thu hồi chúng.
- Cần thiết lập giới hạn timeout, dữ liệu cố định và cleanup phù hợp với cấp test.

**Đặt `sending-enabled: false` chỉ có tác dụng nếu code thực sự đọc và tôn trọng property đó.** Nếu có một bean khác vẫn gửi HTTP trực tiếp, profile test không tự chặn hành vi ấy. Trong các ví dụ sắp tới, chúng ta vừa thay adapter ngoài bằng bean giả, vừa kiểm tra flag từ YAML.

## 5. Ví dụ hoàn chỉnh: Spring Boot 3.x, Java 17+, JUnit Jupiter 5

Ta xây một ứng dụng tối giản có khả năng:

- Trả lời `Hello, Mai!` ở cấu hình chung.
- Khi test profile active, trả lời `Xin chào, Mai!` và **không gửi thông báo** do cấu hình `sending-enabled: false`.
- Chỉ có adapter xuất thông báo của production khi profile `test` không active.
- Trong test, một adapter ghi nhận message được đưa vào context qua `@TestConfiguration`.
- Một test thứ hai chứng minh có thể ghi đè riêng property cho một trường hợp, nhưng vẫn dùng profile `test`.

Các test tập trung vào **hành vi quan sát được và cấu hình Boot thực sự inject**, không chỉ so sánh tên file.

### 5.1. Cấu trúc thư mục

```text
src/
  main/
    java/com/example/profiles/
      ProfileDemoApplication.java
      WelcomeSettings.java
      DeliveryPort.java
      ConsoleDeliveryPort.java
      WelcomeService.java
    resources/
      application.yml
  test/
    java/com/example/profiles/
      RecordingPortConfig.java
      WelcomeProfileTest.java
      WelcomeOverrideTest.java
    resources/
      application-test.yml
```

Những class test ở cùng package `com.example.profiles` nên có thể dùng các kiểu package-private của fixture.

### 5.2. Khởi tạo Spring Boot và quét `@ConfigurationProperties`

**`src/main/java/com/example/profiles/ProfileDemoApplication.java`**

```java
package com.example.profiles;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ProfileDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProfileDemoApplication.class, args);
    }
}
```

`@SpringBootApplication` kích hoạt cấu hình/auto-configuration thông thường. `@ConfigurationPropertiesScan` tìm các kiểu `@ConfigurationProperties` trong package thích hợp (bao gồm `WelcomeSettings`).

### 5.3. Cấu hình strongly typed bằng Java record

**`src/main/java/com/example/profiles/WelcomeSettings.java`**

```java
package com.example.profiles;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.welcome")
public record WelcomeSettings(
        String prefix,
        boolean sendingEnabled,
        int maxLength) {
}
```

Trong Spring Boot 3.x, record có constructor chính được dùng cho constructor binding mà không cần đặt `@ConstructorBinding` cho trường hợp một constructor như ở đây. Boot thực hiện **relaxed binding**, vì thế YAML key `sending-enabled` map sang record component `sendingEnabled`, và `max-length` map sang `maxLength`.

`@ConfigurationProperties` mô tả binding **giá trị cấu hình**, không kích hoạt profile. Annotation `@ActiveProfiles` trên test quyết định profile và từ đó ảnh hưởng các value mà binder nhìn thấy.

Nếu property bắt buộc thiếu hoặc cấu hình sai kiểu, context có thể không tạo được bean đúng cách. Với cấu hình nghiệp vụ nghiêm ngặt, cân nhắc validation (`@Validated` và các constraint kèm dependency validation phù hợp); tránh im lặng chấp nhận `null` hoặc mặc định primitive khi lỗi cấu hình đáng lẽ phải bị phát hiện.

### 5.4. Tách tác dụng phụ qua cổng ra

**`src/main/java/com/example/profiles/DeliveryPort.java`**

```java
package com.example.profiles;

public interface DeliveryPort {
    void send(String destination, String message);
}
```

**`src/main/java/com/example/profiles/ConsoleDeliveryPort.java`**

```java
package com.example.profiles;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("!test")
public class ConsoleDeliveryPort implements DeliveryPort {

    @Override
    public void send(String destination, String message) {
        System.out.println("To " + destination + ": " + message);
    }
}
```

Đây là **adapter console mang tính học tập**, không phải email/payment adapter production thật. `@Profile("!test")` biểu thị bean được xét khi **không có profile `test` đang active**. Do đó, nó bị loại khỏi context khi chạy test profile. Trong một hệ thống thật, điều kiện profile nên phản ánh chính sách môi trường đã được thiết kế, không phải cách duy nhất để chặn side effect.

### 5.5. Service chạy code nghiệp vụ thật

**`src/main/java/com/example/profiles/WelcomeService.java`**

```java
package com.example.profiles;

import org.springframework.stereotype.Service;

@Service
public class WelcomeService {
    private final WelcomeSettings settings;
    private final DeliveryPort deliveryPort;

    public WelcomeService(
            WelcomeSettings settings,
            DeliveryPort deliveryPort) {
        this.settings = settings;
        this.deliveryPort = deliveryPort;
    }

    public String welcome(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }

        String normalized = name.strip();
        if (normalized.length() > settings.maxLength()) {
            throw new IllegalArgumentException("name too long");
        }

        String message = settings.prefix() + ", " + normalized + "!";
        if (settings.sendingEnabled()) {
            deliveryPort.send(normalized, message);
        }
        return message;
    }
}
```

Service nhận cả cấu hình lẫn port qua constructor injection; **không tự đọc `application-test.yml` bằng API file**. Nó chỉ làm việc với các bean mà Spring tạo. Do đó, cùng một class `WelcomeService` chạy trong production và test, nhưng quyết định gửi tin và tiền tố thay đổi do environment.

Kiểm tra tên `null` và `blank` được đặt trước `strip()`. `maxLength` dùng giá trị 80 từ file chung ở ví dụ, cho thấy cấu hình test không nhất thiết lặp lại mọi property.

### 5.6. File YAML cho các môi trường

**`src/main/resources/application.yml`**

```yaml
app:
  welcome:
    prefix: "Hello"
    sending-enabled: true
    max-length: 80
```

**`src/test/resources/application-test.yml`**

```yaml
app:
  welcome:
    prefix: "Xin chào"
    sending-enabled: false
```

Đặt đúng tên và đúng thư mục. File test nằm trong **test resources**, được đưa vào classpath khi chạy JUnit. Không cần khai báo `spring.profiles.active: test` bên trong `application-test.yml` — đây là file được chọn **sau khi** profile đã active và Spring Boot không cho khai báo `spring.profiles.active` trong tài liệu profile-specific.

YAML dùng thụt lề để thể hiện map; hãy dùng khoảng trắng thay vì tab. Với những value là chuỗi có khoảng trắng hoặc giá trị dễ bị YAML parse thành kiểu khác, dùng dấu ngoặc kép để biểu đạt rõ ý.

### 5.7. Tạo fake port trong test scope, không gắn vào source production

**`src/test/java/com/example/profiles/RecordingPortConfig.java`**

```java
package com.example.profiles;

import java.util.ArrayList;
import java.util.List;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

@TestConfiguration(proxyBeanMethods = false)
public class RecordingPortConfig {

    @Bean
    RecordingDeliveryPort recordingDeliveryPort() {
        return new RecordingDeliveryPort();
    }
}

final class RecordingDeliveryPort implements DeliveryPort {
    private final List<String> messages = new ArrayList<>();

    @Override
    public void send(String destination, String message) {
        messages.add(destination + "|" + message);
    }

    List<String> messages() {
        return List.copyOf(messages);
    }
}
```

`@TestConfiguration` cho biết đây là cấu hình dùng riêng trong test; `@Import(RecordingPortConfig.class)` ở test class sẽ nhập bean này một cách tường minh. `ConsoleDeliveryPort` bị loại bởi `@Profile("!test")`, nên tại test profile, chỉ fake port phù hợp được đưa vào `WelcomeService`.

Fake ghi vào danh sách trong bộ nhớ. Đây là **fixture đồng bộ** để minh họa; nếu có concurrency, test nhiều thread hoặc dùng chung instance qua nhiều phương thức có side effect, cần thiết kế isolation phù hợp hơn. Tốt nhất mỗi test/fixture được giữ độc lập; không dùng danh sách mutable được chia sẻ giữa nhiều test đang chạy song song.

### 5.8. Test profile: giá trị YAML, bean selection và hành vi thật

**`src/test/java/com/example/profiles/WelcomeProfileTest.java`**

```java
package com.example.profiles;

import java.util.Arrays;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = ProfileDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("test")
@Import(RecordingPortConfig.class)
class WelcomeProfileTest {

    @Autowired
    WelcomeService service;

    @Autowired
    WelcomeSettings settings;

    @Autowired
    RecordingDeliveryPort recorder;

    @Autowired
    Environment environment;

    @Test
    void loadsTestProfileAndConfigData() {
        assertTrue(Arrays.asList(environment.getActiveProfiles())
                        .contains("test"));

        assertAll("configuration under test profile",
                () -> assertEquals("Xin chào", settings.prefix()),
                () -> assertFalse(settings.sendingEnabled()),
                () -> assertEquals(80, settings.maxLength()));
    }

    @Test
    void appliesTestSettingsToRealService() {
        assertEquals("Xin chào, Mai!",
                service.welcome("  Mai  "));

        assertEquals(List.of(), recorder.messages(),
                "Không gửi message khi sending-enabled=false");
    }

    @Test
    void validatesInputWhileUsingTestProfile() {
        assertThrows(IllegalArgumentException.class,
                () -> service.welcome("   "));
    }
}
```

Trong `loadsTestProfileAndConfigData`, test xác nhận **profile active**, **property override của YAML test** và **property chung kế thừa từ application.yml**. Trong `appliesTestSettingsToRealService`, service chạy thật, còn adapter ghi nhận message không bị gọi vì flag tắt.

Đối với `@SpringBootTest`, `webEnvironment=NONE` tránh tạo web environment khi không cần HTTP. Test vẫn dùng TestContext Framework và một Spring Boot `ApplicationContext`. Không phải gọi `SpringApplication.run` thủ công trong test.

**Lưu ý độ độc lập của test:** file này có nhiều method dùng cùng context và singleton fake, nhưng chỉ method `appliesTestSettingsToRealService` liên quan đến kiểm tra danh sách messages và với flag tắt nó không thay đổi danh sách. Trong các test có send thật, nên reset fixture hoặc tạo context/bean state phù hợp để tránh phụ thuộc thứ tự giữa test. Method order của JUnit không nên được xem là trình tự nghiệp vụ.

### 5.9. Một test riêng ghi đè property mà vẫn giữ profile test

Đôi khi muốn kiểm tra nhánh `sending-enabled=true` mà **không sửa `application-test.yml` cho toàn bộ suite**. Có thể dùng `@TestPropertySource(properties=...)`.

**`src/test/java/com/example/profiles/WelcomeOverrideTest.java`**

```java
package com.example.profiles;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = ProfileDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("test")
@Import(RecordingPortConfig.class)
@TestPropertySource(properties = "app.welcome.sending-enabled=true")
class WelcomeOverrideTest {

    @Autowired
    WelcomeService service;

    @Autowired
    WelcomeSettings settings;

    @Autowired
    RecordingDeliveryPort recorder;

    @Test
    void inlineTestPropertyOverridesProfileYamlForThisContext() {
        assertTrue(settings.sendingEnabled());

        assertEquals("Xin chào, Mai!", service.welcome("  Mai  "));
        assertEquals(
                List.of("Mai|Xin chào, Mai!"),
                recorder.messages());
    }
}
```

**Ý nghĩa:**

- Profile **vẫn là `test`**, nên `application-test.yml` vẫn tham gia tạo context và production adapter `@Profile("!test")` không được chọn.
- Property inline từ `@TestPropertySource` có ưu tiên cao hơn config data file trong trường hợp này, nên flag hiệu lực trở thành `true`.
- Lời gọi thật tới `WelcomeService` gửi đúng một message tới fake `RecordingDeliveryPort`, **không** tới adapter production.
- Hai test class có cấu hình property source khác nhau nên thường dùng **hai cache key/context khác nhau**. Không dùng một test method đổi global property giữa chừng rồi chờ `@ConfigurationProperties` bean tự rebind; cấu hình bean thường được bind lúc context được dựng.

## 6. Vì sao ví dụ trên có thể kiểm tra tính đúng của profile?

Một test chỉ viết:

```java
@ActiveProfiles("test")
@Test
void profileWorks() {
    assertTrue(true);
}
```

không chứng minh cấu hình đang được nạp. Dòng `assertTrue(true)` luôn xanh, kể cả khi không có context.

Test có giá trị nên bảo vệ ít nhất một hợp đồng quan trọng, ví dụ:

- `Environment` chứa profile được mong đợi;
- `WelcomeSettings.prefix()` có giá trị `Xin chào` thay vì `Hello`;
- `WelcomeSettings.sendingEnabled()` đúng là `false`;
- `WelcomeService.welcome(...)` trả đúng chuỗi;
- bean production bị loại và fake port được inject;
- khi bật cờ ở context test riêng, message được ghi vào fake.

Trong dự án thật, không cần assert từng key cấu hình nếu chúng chỉ là chi tiết nội bộ và đã được chứng minh qua hành vi. Ngược lại, những key giữ an toàn như URL sandbox, disabling external delivery hoặc database endpoint test **đáng có assertion rõ ràng** để giảm nguy cơ vô tình gọi tài nguyên thật.

## 7. `@Profile` và `@ActiveProfiles` khác nhau thế nào?

**`@ActiveProfiles`** gắn với **test class** để chọn active profiles. **`@Profile`** gắn với **bean/configuration** để quyết định điều kiện đăng ký bean.

Ví dụ:

```java
@Component
@Profile("!test")
class RealGateway implements Gateway {
    // ...
}

@Component
@Profile("test")
class InMemoryGateway implements Gateway {
    // ...
}
```

Đây là minh họa cú pháp, không phải file độc lập: các type `Gateway`, import và method implementation chưa được khai báo.

Khi có `test` active, chỉ bean được điều kiện `@Profile("test")` chấp nhận, còn `@Profile("!test")` bị loại. Điều kiện `@Profile("!test")` không đồng nghĩa chỉ production: nó cũng hoạt động dưới `local`, `dev` hoặc không có profile active, miễn profile `test` không active.

**Thực hành tốt:** trong nhiều dự án, đặt adapter test trong `src/test/java` bằng `@TestConfiguration` và `@Import` như ví dụ hoàn chỉnh, thay vì đóng gói một fake vào production artifact. Phân tách này giúp tránh test-only behavior xuất hiện ở môi trường triển khai.

### 7.1. Một số cú pháp profile

```java
@Profile("test")               // Chỉ khi test active
@Profile("!prod")              // Khi prod không active
@Profile({"local", "test"})     // Một trong hai profile active
@Profile("integration & !prod") // Ví dụ biểu thức AND/NOT
```

Đây là đoạn minh họa các annotation đơn lẻ, không phải Java class đầy đủ. Trong `@Profile({"local","test"})`, danh sách giá trị theo ngữ nghĩa OR. Biểu thức kết hợp AND/NOT/OR có hỗ trợ qua profile expressions; hãy dùng cú pháp rõ ràng và kiểm tra tài liệu Spring phiên bản đang dùng nếu tổ hợp phức tạp.

### 7.2. Bean có thể xung đột khi nhiều profile active

Nếu có hai bean cùng implement `DeliveryPort` và đều active, injection chỉ theo type có thể dẫn đến lỗi `NoUniqueBeanDefinitionException`. Giải pháp là thiết kế điều kiện profile loại trừ nhau, chọn `@Primary`/`@Qualifier` có chủ đích hoặc dùng cấu hình test thay bean theo cơ chế đúng version. **Không xử lý bằng cách thêm bean giả khắp mọi test context** vì điều đó khiến kết quả khó đoán.

## 8. Thứ tự ưu tiên property: file nào thắng?

Spring Boot ghép nhiều `PropertySource` theo thứ tự ưu tiên. Cấu hình test có thể được quyết định bởi:

- file chung `application.yml`;
- file profile-specific `application-test.yml`;
- file ngoài jar, file từ location tùy chỉnh và `spring.config.import`;
- environment variables, JVM system properties và các nguồn runtime khác;
- thuộc tính `properties` trên `@SpringBootTest` hoặc một test slice;
- `@TestPropertySource`, `@DynamicPropertySource` trong test.

Không nên thuộc lòng một thứ tự rút gọn rồi suy ra đúng với mọi ứng dụng. Location group, file ngoài jar, profile kết hợp, property test inline hoặc config importer có thể làm thứ tự phức tạp. Với hai file trong ví dụ ở cùng classpath, giá trị trong `application-test.yml` thắng giá trị cùng key ở `application.yml`, **nếu không có nguồn ưu tiên cao hơn**.

Bảng minh họa:

| Cấu hình | `prefix` | `sending-enabled` | Giải thích |
|---|---|---|---|
| Chỉ `application.yml` | `Hello` | `true` | Giá trị chung |
| `@ActiveProfiles("test")` + Boot config data | `Xin chào` | `false` | File `application-test.yml` ghi đè |
| Như trên + `@TestPropertySource(properties="app.welcome.sending-enabled=true")` | `Xin chào` | `true` | Property test inline ghi đè flag |
| Như trên nhưng một nguồn khác ưu tiên cao hơn khai báo `app.welcome.prefix` | Phụ thuộc nguồn | Theo nguồn ưu tiên | Không thể kết luận chỉ từ hai file |

**`@TestPropertySource(locations="classpath:application-test.yml")` không phải cách chuẩn để nạp YAML.** Spring TestContext `@TestPropertySource` mặc định xử lý định dạng `.properties` hoặc định dạng được hỗ trợ qua factory tùy chỉnh; với YAML profile-specific của Boot, hãy để Boot Config Data nạp tệp qua profile active. Nếu cần file không theo convention, dùng `spring.config.import` hoặc property source/factory tương thích theo đúng mục tiêu.

## 9. `@ActiveProfiles` với `spring.profiles.active`

Trong **chạy ứng dụng bình thường**, có thể bật profile bằng:

```bash
java -jar app.jar --spring.profiles.active=local
```

Hoặc thông qua environment variable `SPRING_PROFILES_ACTIVE=local`, JVM system property hay cấu hình phù hợp. Đây là cách điều khiển profile lúc ứng dụng chạy.

Trong **Spring TestContext test**, `@ActiveProfiles("test")` là cách khai báo test profile rõ ràng tại class. Theo tài liệu Spring TestContext, khi annotation này có mặt, `spring.profiles.active` từ system property hoặc environment variable **không tự được lấy làm quyền ghi đè profile đã khai báo trong `@ActiveProfiles`**. Nếu có yêu cầu cho runtime external setting quyết định profile test, dùng `ActiveProfilesResolver` có chủ đích và thiết kế sự cô lập phù hợp; không dựa vào hành vi ngầm.

Ví dụ chỉ mang tính cú pháp:

```java
@SpringBootTest
@ActiveProfiles("integration")
class IntegrationEnvironmentTest {
    // Context test dùng profile integration theo TestContext.
}
```

Tuy nhiên, property `spring.profiles.active` vẫn có các quy tắc của Boot Config Data trong những tình huống không bị `@ActiveProfiles` điều khiển. Đừng gộp hai cơ chế thành một khái niệm.

**Không đưa dòng sau vào `application-test.yml`:**

```yaml
spring:
  profiles:
    active: test
```

Spring Boot không cho cấu hình `spring.profiles.active` trong chính tài liệu **profile-specific** hoặc tài liệu đã được kích hoạt bởi `spring.config.activate.on-profile`. Ngoài ra nó tạo quan hệ vòng: profile phải active trước để file này được chọn. Hãy để `@ActiveProfiles("test")` trên test class, hoặc đặt cơ chế chọn profile tại nguồn **không profile-specific** khi chạy ứng dụng.

## 10. Kết hợp nhiều profile và các file YAML tương ứng

Có thể chạy một test với nhiều profile:

```java
@ActiveProfiles({"test", "integration"})
@SpringBootTest
class IntegrationTest {
}
```

Nếu Boot tìm thấy `application.yml`, `application-test.yml` và `application-integration.yml`, các file profile-specific có thể cùng tham gia. Khi nhiều file khai báo **cùng key**, Boot dùng cơ chế ưu tiên có quy tắc *last-wins* theo thứ tự/profile/location group phù hợp. Không nên dựa vào sự sắp xếp không được kiểm chứng trong một hệ thống config phức tạp.

Ví dụ minh họa:

**`application-test.yml`**

```yaml
app:
  endpoint:
    mode: "fake"
    timeout-ms: 200
```

**`application-integration.yml`**

```yaml
app:
  endpoint:
    timeout-ms: 1000
```

Trong tình huống profile được áp dụng và cùng location group theo thứ tự cho phép file integration ghi đè, `mode` vẫn có thể là `fake`, còn `timeout-ms` sẽ thành 1000. Nếu kết quả cụ thể quan trọng, **assert property hiệu lực trong test**, vì thứ tự có thể thay đổi theo cấu trúc config.

**Phạm vi gợi ý:**

- `test` cho test chung, fake port và giá trị an toàn.
- `integration` để thêm cấu hình cho database/container/infrastructure.
- `local` cho môi trường phát triển, không nên tự động trộn với test CI nếu điều đó có thể gọi dịch vụ thật.

Tránh nhiều profile khác nhau chỉ để giải quyết một boolean trong một test đơn lẻ. Với một ngoại lệ nhỏ, `@TestPropertySource` hoặc `@SpringBootTest(properties=...)` thường dễ đọc hơn.

## 11. Profile mặc định và `@Profile("default")`

Nếu không có active profile rõ ràng, Spring có một tập **default profiles**, thường chứa tên `default`. Điều này khác với việc nói `default` luôn active cùng `test`.

Ví dụ:

- Một bean `@Profile("default")` chỉ được chọn khi điều kiện default profiles có hiệu lực.
- Khi `test` đã active, profile `default` theo mặc định **không còn là profile kích hoạt bean** như trong tình huống không active profile.
- Một bean không có `@Profile` thường được Spring tạo ở cả test và production, trừ khi điều kiện/cấu hình khác loại nó.

Vì vậy, đừng gắn `@Profile("default")` lên bean chính rồi bất ngờ vì trong test profile không thấy bean. Nếu muốn bean hoạt động trừ khi `test` active, biểu thức `@Profile("!test")` mô tả rõ hơn; nếu muốn Bean dùng riêng khi không có profile nào, `default` có ý nghĩa riêng.

Cũng cần hiểu khái niệm **default values từ application.yml** khác **default profile**. File `application.yml` là nguồn cấu hình chung, không phải file chỉ dùng cho `@Profile("default")`.

## 12. Một lựa chọn khác: tài liệu YAML nhiều đoạn (multi-document)

Không bắt buộc tạo file `application-test.yml` riêng. Spring Boot hỗ trợ nhiều tài liệu trong một file YAML bằng dòng phân cách `---` và điều kiện `spring.config.activate.on-profile`.

Ví dụ **thay thế cấu trúc file**, không đặt đồng thời trong project với file ví dụ nếu bạn không muốn hai nguồn ghi đè nhau:

**`src/main/resources/application.yml`**

```yaml
app:
  welcome:
    prefix: "Hello"
    sending-enabled: true
    max-length: 80

---
spring:
  config:
    activate:
      on-profile: "test"
app:
  welcome:
    prefix: "Xin chào"
    sending-enabled: false
```

Trong file trên, document đầu là cấu hình chung; document sau chỉ có hiệu lực khi profile `test` active.

So sánh:

| Cách | Ưu điểm | Hạn chế |
|---|---|---|
| `src/test/resources/application-test.yml` | Không đóng gói test-specific config vào artifact production; rõ phạm vi test | Cần đảm bảo test runtime classpath và profile được chọn đúng |
| `src/main/resources/application-test.yml` | Có thể dùng cho một môi trường chạy theo profile `test` của ứng dụng | File có thể được đóng gói vào artifact; dễ nhầm với cấu hình CI |
| Multi-document `application.yml` | Gom các nhánh ngắn và dùng chung cấu trúc | File lớn và chứa cả cấu hình theo môi trường; khó rà soát hơn nếu nhiều profile |

Không có một lựa chọn thắng tuyệt đối. Với **kiểm thử tự động** cần cấu hình và fake adapter riêng, `src/test/resources/application-test.yml` thường tách bạch hơn.

**Không đặt `spring.profiles.active` bên trong document có `spring.config.activate.on-profile`.** Boot giới hạn các property điều khiển profile trong tài liệu không profile-specific.

## 13. `@ActiveProfiles` và kế thừa trong các lớp test

Khi tạo base test class dùng chung, Spring TestContext hỗ trợ kế thừa active profile từ superclass theo mặc định. Ví dụ:

```java
@ActiveProfiles("test")
abstract class BaseContextTest {
}

@ActiveProfiles("integration")
class OrderIntegrationTest extends BaseContextTest {
    // Theo mặc định, profile từ base class được kế thừa,
    // kết hợp với profile lớp con theo quy tắc framework.
}
```

Đây là **mã minh họa**, không phải test hoàn chỉnh. Khi dùng `inheritProfiles = false` trên annotation của subclass, bạn có thể tắt việc kế thừa profile từ superclass. Các test trong class lồng nhau cũng có quy tắc kế thừa từ enclosing class theo cấu hình.

Rủi ro: một test tưởng chỉ có profile `integration` nhưng do superclass vẫn có `test`, bean production bị loại bởi `@Profile("!test")` hoặc file test khác cũng được nạp. Điều này có thể làm test chạy khác mong đợi.

**Cách phòng:** giữ hierarchy test đơn giản; đọc active profile thực tế trong context khi có lỗi; không giấu profile quan trọng trong quá nhiều base class hoặc meta-annotation. Nếu cần một profile cụ thể, khai báo rõ và hiểu quy tắc kế thừa.

## 14. Cache `ApplicationContext` và ảnh hưởng của profile lên runtime

Spring TestContext Framework cache context theo tổ hợp cấu hình, bao gồm active profiles và nhiều thông số khác. Hai test có cùng Spring Boot config nhưng dùng profile khác nhau thường tạo **hai context cache entries** khác nhau, bởi bộ bean và property hiệu lực có thể khác.

Trong Spring Framework 6.x, context cache thông thường là **static trong JVM chạy test**. Nó có giới hạn số entry mặc định và cơ chế eviction theo LRU. Nếu CI tạo rất nhiều biến thể profile/property/mock bean, việc nạp lại context có thể làm cả suite chậm.

Ví dụ:

```text
Test A: @SpringBootTest + @ActiveProfiles("test")
Test B: cùng config/profile/test imports
    -> Có thể chia sẻ context trong cùng JVM nếu cache key tương đương.

Test C: @SpringBootTest + @ActiveProfiles("integration")
    -> Profile khác, thường không cùng context với A/B.

Test D: @SpringBootTest + @ActiveProfiles("test")
        + @TestPropertySource(properties="app.welcome.sending-enabled=true")
    -> Property source khác, thường cache key khác A/B.
```

**Lưu ý:** hai class đều ghi `@ActiveProfiles("test")` không đủ đảm bảo cache hit. Các yếu tố khác như cấu hình class, profile kế thừa, dynamic property, context customizer, `@MockBean`/`@MockitoBean` theo version, web resource base path và `@DirtiesContext` cũng có thể làm kết quả khác.

**Giảm chi phí bảo trì và thời gian test:**

1. Chọn một cấu hình profile test chung cho đa số bài kiểm thử.
2. Chỉ dùng profile/inline property khác khi test thực sự cần khác behavior.
3. Giữ fake port độc lập với test class nếu nhiều suite cần chia sẻ cấu hình hợp lệ.
4. Tránh `@DirtiesContext` trên mọi test chỉ để “reset”; ưu tiên reset fixture/DB khi phù hợp.
5. Giữ unit test logic thuần không dùng Spring context.
6. Kiểm tra thống kê cache qua logging Spring TestContext khi suite chậm.

Context cache **không tự reset các singleton mutable giữa các method** nếu reuse cùng context. Nếu dùng fake port giữ danh sách message, chính test hoặc fixture phải bảo đảm trạng thái không bị rò rỉ.

## 15. `@SpringJUnitConfig` khác gì với `@SpringBootTest` khi đọc YAML?

Một hiểu nhầm phổ biến: “Có `@ActiveProfiles("test")` nên Spring chắc chắn tự đọc `application-test.yml` trong mọi test”. Thực tế **`@ActiveProfiles` chỉ quyết định active profiles của TestContext**. Việc xử lý các file `application*.yml` theo convention là nhiệm vụ của **Spring Boot Config Data** trong một context được bootstrapped theo cơ chế Boot.

Với test cấu hình Spring thuần:

```java
@SpringJUnitConfig(TestOnlyConfiguration.class)
@ActiveProfiles("test")
class PlainSpringTest {
}
```

test có thể được tạo từ `@ContextConfiguration`/`@SpringJUnitConfig` mà **không khởi tạo `SpringApplication`**. Annotation `@ActiveProfiles` vẫn ảnh hưởng `@Profile` của bean, nhưng không nên mặc định rằng Boot sẽ tìm và nạp `application-test.yml`. Nếu cần YAML config trong tình huống này, phải cấu hình loader/property source phù hợp hoặc chuyển sang Boot test bootstrap khi điều đó tương xứng.

Với:

```java
@SpringBootTest
@ActiveProfiles("test")
class BootProfileTest {
}
```

Spring Boot dùng `SpringApplication` và các quy tắc Config Data; tệp `application-test.yml` tại location hợp lệ được cân nhắc tự động.

Tương tự, test slice của Spring Boot thường cũng được bootstrap với cấu hình Boot thích hợp nhưng **chỉ nạp phần ứng dụng liên quan**. Không dùng `@SpringBootTest` cho một phép tính Java thuần chỉ vì muốn đọc một property; có thể test trực tiếp logic nếu việc nạp cấu hình không phải contract.

## 16. Kết nối profile với database, message broker và external services

### 16.1. Database

`application-test.yml` có thể định nghĩa datasource test, chẳng hạn:

```yaml
spring:
  datasource:
    url: "jdbc:h2:mem:testdb;DB_CLOSE_DELAY=-1"
    username: "sa"
    password: ""
```

Đây là **đoạn cấu hình minh họa**, không thuộc project runnable ở mục 5 (project đó không khai báo JDBC/JPA hoặc H2). Muốn sử dụng cần bổ sung dependency JDBC/JPA và H2 phù hợp, cùng lựa chọn test database theo contract.

H2 thuận tiện nhưng có khác biệt SQL, transaction, collation và constraint so với PostgreSQL/MySQL. Nếu test cần chứng minh query/migration tương thích production, Testcontainers hoặc database phù hợp có thể đáng dùng hơn.

Không để test trỏ nhầm database production. Nên có biện pháp tách biệt schema, credential và quyền ghi ở cấp hạ tầng; **đừng chỉ trông vào profile**.

### 16.2. Message broker, email, HTTP

Có nhiều hướng lựa chọn:

| Nhu cầu | Cách test phù hợp |
|---|---|
| Unit test logic gửi message | Mock/fake một interface outbound port |
| Test HTTP client serialization/retry | Mock web server có kiểm soát hoặc contract test |
| Test messaging adapter | Embedded/test broker hoặc Testcontainers khi cần hành vi thật |
| Test end-to-end được phép | Sandbox riêng, giới hạn dữ liệu/credential, cleanup rõ |
| Test lựa chọn cấu hình | Assert property hiệu lực và bean/adapter được inject |

Không nên dùng `application-test.yml` để thay một endpoint production bằng localhost mà không đảm bảo service test thực sự đang chạy. Lỗi connection refused sẽ làm test flaky hoặc thất bại vô ích.

### 16.3. Không đặt bí mật thật vào YAML

YAML là nguồn cấu hình, không phải vault. Không commit API key/password production vào `src/main/resources` hoặc `src/test/resources`. Test có thể dùng fake credential chỉ đủ để chạy fake/local server; tích hợp với sandbox thật nên lấy secret từ CI secret manager và chỉ mở quyền cần thiết.

## 17. Troubleshooting: khi profile hoặc YAML không có hiệu lực

| Triệu chứng | Nguyên nhân đáng kiểm tra | Cách khắc phục |
|---|---|---|
| Test đọc được `Hello` thay vì `Xin chào` | `test` chưa active, file sai tên/vị trí, context không dùng Boot Config Data, nguồn khác đang ghi đè | Kiểm tra `Environment.getActiveProfiles()`, classpath, tên `application-test.yml` và property hiệu lực |
| `@Autowired` bị null | Test không được SpringExtension quản lý hoặc test dùng `new` tự tạo | Dùng `@SpringBootTest`/slice hoặc `@SpringJUnitConfig` phù hợp |
| Bean production vẫn được tạo trong test | Thiếu `@Profile`, profile không active hoặc bean khác không tuân theo profile | Kiểm tra bean definition và điều kiện, assert bean được inject |
| `NoSuchBeanDefinitionException: DeliveryPort` | Production bean `!test` bị loại nhưng fake chưa được `@Import` | Đưa fake bean vào test context hoặc chọn bean override đúng cách |
| `NoUniqueBeanDefinitionException` | Hai bean cùng type đều active | Thiết kế profile loại trừ nhau hoặc dùng qualifier/primary có chủ đích |
| `application-test.yml` bị bỏ qua | Tệp không vào test classpath, tên khác, dùng loader Spring thuần | Kiểm tra build resources, dùng Boot bootstrap hoặc khai báo nguồn config tường minh |
| Spring Boot báo sai loại YAML | Lỗi indentation, tab, kiểu string/boolean/number | Kiểm tra YAML, dùng key kebab-case và giá trị đúng kiểu |
| `spring.profiles.active` không hoạt động trong file test profile | Property được khai báo trong tài liệu profile-specific (không được phép) | Bỏ key khỏi file đó; kích hoạt từ `@ActiveProfiles` trên test |
| Flag test bị property inline ghi đè | Có `@TestPropertySource`, `@SpringBootTest(properties)`, property động hoặc env/CLI | Xem property source ưu tiên và effective value |
| CI khác máy local | Khác env var, JVM props, config location, classpath, secrets | Chuẩn hóa test config và kiểm tra thông tin môi trường đã được phép log |
| Hai test ảnh hưởng lẫn nhau | Context cache chia sẻ singleton mutable hoặc database/test data | Reset fixture, cleanup, tách dữ liệu; không dùng thứ tự test để chữa |
| Test chậm khi đổi nhiều profile | Cache key khác nhau, context được nạp lại | Giảm biến thể config, dùng unit/slice khi đủ, xem thống kê cache |

### 17.1. Cách debug theo tầng

**Tầng 1 — xác nhận profile:** inject `Environment`; kiểm tra `getActiveProfiles()` hoặc `acceptsProfiles(Profiles.of("test"))`.

**Tầng 2 — xác nhận property:** đọc property hiệu lực `environment.getProperty("app.welcome.prefix")` và giá trị trên bean `@ConfigurationProperties`. Không chỉ đọc file YAML trên đĩa rồi kết luận Spring đã nạp nó.

**Tầng 3 — xác nhận bean:** kiểm tra `ApplicationContext` có bean gì thuộc interface cần thiết, `@Profile` có điều kiện đúng không, và bean test đã `@Import` chưa.

**Tầng 4 — kiểm tra ưu tiên nguồn config:** tìm `@TestPropertySource`, test property inline, system props, env vars và config location. Khi có nhiều key giống nhau, nguồn ưu tiên cao hơn thắng.

**Tầng 5 — kiểm tra cache và trạng thái:** nếu lần đầu chạy pass nhưng toàn suite fail, xem bean singleton mutable, context cache, test order, DB và dữ liệu chia sẻ.

### 17.2. Log nên đủ để chẩn đoán, nhưng không lộ secrets

Với bài test cấu hình, có thể quan sát `Environment` và cấu hình bean một cách chọn lọc. Tuyệt đối không dump toàn bộ `PropertySources` hay in password/token lên CI log. Chỉ log những key không nhạy cảm, ví dụ `app.welcome.prefix` hoặc tên active profile.

Nếu lỗi là `Failed to load ApplicationContext`, hãy đọc **root cause** ở các dòng `Caused by` của stack trace; message tổng quát thường không chỉ ra chính xác property hoặc bean bị lỗi.

## 18. Gradle và cách chạy ví dụ

Ví dụ dùng **Java 17+**, Spring Boot **3.x**, JUnit Jupiter **5**. Với dự án đã khai báo Spring Boot plugin/BOM để quản lý dependency version, `build.gradle` cần phần phụ thuộc như sau:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Đây chỉ là đoạn bổ sung của một build đã cấu hình Spring Boot**, không phải file Gradle độc lập vì chưa có `plugins`, `repositories` và version management. Không cần `spring-boot-starter-web` vì ví dụ chỉ có service và port, không có controller HTTP.

Chạy từ thư mục có Gradle wrapper:

```bash
./gradlew test --tests com.example.profiles.WelcomeProfileTest --tests com.example.profiles.WelcomeOverrideTest
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests com.example.profiles.WelcomeProfileTest --tests com.example.profiles.WelcomeOverrideTest
```

Nếu dự án dùng Gradle multi-project, thay task `test` bằng đường dẫn test task của module chứa code. Giữ package/path đúng như file list ở mục 5, chạy trong project có Spring Boot 3.x phù hợp. **Các tệp ví dụ là để học tập, không cần sửa repository hiện tại khi chỉ đọc bài này.**

**Kết quả kỳ vọng của bài test:**

1. `WelcomeProfileTest` nạp profile `test`, bind `prefix="Xin chào"`, `sendingEnabled=false` và `maxLength=80`.
2. `WelcomeProfileTest` gọi `WelcomeService` thật và nhận chuỗi `"Xin chào, Mai!"`, fake port không ghi nhận message.
3. `WelcomeProfileTest` ném `IllegalArgumentException` khi tên chỉ gồm khoảng trắng.
4. `WelcomeOverrideTest` vẫn dùng test profile, nhưng property test inline bật sending; fake port ghi nhận chính xác `"Mai|Xin chào, Mai!"`.
5. Nếu compile, bootstrap và assertions đúng trong môi trường đã chuẩn bị, Gradle thông báo `BUILD SUCCESSFUL`. Đây là **kết quả mong đợi từ mã ví dụ**, không phải tuyên bố đã chạy dự án cụ thể. JUnit test không có stdout nghiệp vụ cố định; adapter console không được dùng khi profile `test` active.

Báo cáo test của Gradle thường được tạo tại `build/reports/tests/test/index.html`; kết quả XML ở `build/test-results/test/`, tính từ build directory của module.

### 18.1. Kiểm tra thông tin trong runtime thay vì chỉ tin tên annotation

Nếu muốn chứng minh property thực sự đến từ nguồn mong đợi, hãy cân nhắc assertions trên bean và `Environment` như ví dụ. Tuy nhiên, **đừng kiểm tra thứ tự riêng của từng `PropertySource` chỉ vì implementation detail** nếu contract chỉ yêu cầu giá trị và bean cuối cùng. Khi test có yêu cầu về nguồn dữ liệu rõ, hãy chọn mức kiểm tra thích hợp, tránh phụ thuộc quá sâu vào internal implementation của Config Data.

## 19. Sai lầm phổ biến và hệ quả

**“Tạo file application-test.yml là đủ.”** Sai: file profile-specific không tự kích hoạt profile. Test phải có cơ chế active profile phù hợp.

**“@ActiveProfiles đọc YAML ngay cả với JUnit test không khởi động Spring.”** Sai: annotation cần TestContext và cách bootstrap phù hợp; quy tắc tự nạp `application-{profile}.yml` là tính năng Boot Config Data.

**“Đặt spring.profiles.active=test trong application-test.yml.”** Sai: Boot không cho khai báo property điều khiển profile trong file đã dành riêng cho một profile. Kích hoạt từ test annotation hoặc nguồn bên ngoài đúng chỗ.

**“Có test profile thì mọi request ngoài đều thành fake.”** Sai: adapter phải được cấu hình và kiểm tra; production component không có điều kiện vẫn có thể được tạo hoặc thực thi.

**“Mọi property trong application-test.yml luôn thắng.”** Sai: còn nhiều property sources với độ ưu tiên khác nhau; một `@TestPropertySource` hoặc nguồn phù hợp có thể ghi đè.

**“Một test có thể sửa System.setProperty rồi bắt Spring bean đã tạo tự đổi ngay.”** Không nên giả định thế. Các bean `@ConfigurationProperties` thường đã bind lúc context được khởi tạo, và việc đổi property toàn JVM còn gây side effect cho test khác. Hãy tạo context với config mong muốn qua annotation/configuration có chủ đích.

**“Dùng @DirtiesContext cho mọi test để luôn có môi trường mới.”** Chi phí nạp lại context rất cao; nó cũng không reset mọi tài nguyên ngoài context. Ưu tiên state isolation, cleanup và cấu hình cache hợp lý.

**“Có @ActiveProfiles('test') thì an toàn tuyệt đối để chạy lên CI.”** Không. An toàn còn phụ thuộc database URL, credential, network, các scheduler, message broker và bean thật sự hoạt động. Dùng hạ tầng/test credentials riêng và có bảo vệ nhiều lớp.

## 20. Bài tập tự đánh giá

### Bài tập 1 — xác định giá trị cuối cùng

Có file `application.yml`:

```yaml
app:
  feature:
    enabled: true
    label: "base"
    retries: 4
```

và `application-test.yml`:

```yaml
app:
  feature:
    enabled: false
    label: "test-only"
```

Nếu `@SpringBootTest` + `@ActiveProfiles("test")` dùng Boot Config Data và không có nguồn override khác, hãy xác định ba giá trị hiệu lực.

**Đáp án:** `enabled=false`, `label="test-only"`, `retries=4`. File profile-specific ghi đè hai key, key còn lại dùng file chung.

### Bài tập 2 — vì sao Spring không thấy bean?

Một interface `PaymentPort` có implementation production gắn `@Profile("!test")`. Test dùng `@ActiveProfiles("test")` nhưng không import implementation test. Lỗi nào dễ xảy ra? Cách sửa đúng?

**Đáp án:** Nếu service cần inject `PaymentPort`, context có thể báo không có bean hợp lệ. Đưa fake/test bean vào context qua `@TestConfiguration` và `@Import`, hoặc dùng cơ chế bean override của phiên bản Spring/Boot phù hợp. Không bỏ điều kiện `!test` chỉ để test khởi động.

### Bài tập 3 — phân biệt Spring TestContext thuần và Boot

Tại sao `@SpringJUnitConfig(TestConfig.class)` + `@ActiveProfiles("test")` có thể chọn bean `@Profile("test")` nhưng không tự tìm `application-test.yml`?

**Đáp án:** Spring TestContext hiểu active profiles và bean definition conditions; còn convention `application-test.yml` là cách Spring Boot Config Data nạp property khi context được bootstrapped bằng Boot.

### Bài tập 4 — ngăn test gọi production

Đưa ra ba lớp bảo vệ bên cạnh `@ActiveProfiles("test")` để test không làm ảnh hưởng production.

**Gợi ý:** adapter fake/mock server, database riêng cùng credential giới hạn, không dùng secrets production, cấu hình URL sandbox có assertion, tắt scheduler hoặc consumer ngoài phạm vi test, test data cleanup.

### Bài tập 5 — giảm runtime context cache

Nếu suite có 40 lớp `@SpringBootTest` khác nhau ở hàng chục flag override nhỏ, tại sao runtime có thể tăng? Giải pháp nào không mất khả năng phát hiện lỗi?

**Đáp án:** Nhiều tổ hợp config/property có thể tạo nhiều context cache entries. Gom các test cùng nhu cầu cấu hình, dùng unit/slice cho logic không đòi full context, tránh đổi profile/inline property không cần thiết, giữ integration test có giá trị cho wiring và side effects.

## 21. Checklist thực hành trước khi chạy test

- [ ] `@ActiveProfiles` được đặt trên test có Spring TestContext/Boot bootstrap phù hợp.
- [ ] File `application-test.yml` nằm đúng location, đúng tên, đúng cú pháp YAML.
- [ ] Tôi không khai báo `spring.profiles.active` bên trong file profile-specific.
- [ ] Tôi hiểu key nào đến từ `application.yml` và key nào được profile test ghi đè.
- [ ] Tôi kiểm chứng **effective value** qua bean/`Environment`, không chỉ nhìn file.
- [ ] Adapter production có điều kiện thích hợp; test fake được inject khi cần.
- [ ] Không có endpoint/credential production trong test context hoặc CI config.
- [ ] Test được cô lập với database, network, message broker và singleton state.
- [ ] Inline property override chỉ dùng khi test cần biến thể; không lạm dụng khiến context cache phân mảnh.
- [ ] Tôi không mặc định `@TestPropertySource` sẽ parse `.yml` giống Boot Config Data.
- [ ] Tôi hiểu active profile trên superclass/nested test có thể được kế thừa.
- [ ] Tôi chọn unit, slice hoặc `@SpringBootTest` theo rủi ro cần kiểm chứng.
- [ ] Tôi không dùng `@DirtiesContext` để thay thế việc cleanup dữ liệu.
- [ ] Khi lỗi, tôi phân biệt sai profile, sai property source, thiếu bean, lỗi bootstrap và lỗi nghiệp vụ.

**Kết luận:** `@ActiveProfiles` chọn tập profile cho Spring TestContext; `application-test.yml` cung cấp cấu hình theo profile mà Spring Boot tải khi profile `test` active trong một context được khởi tạo đúng cơ chế. Kiểm thử đáng tin cần cả **giá trị cấu hình hiệu lực đúng**, **bean/adapter đúng**, và **isolation của tài nguyên ngoài**. Test không chỉ nên xanh mà còn phải chứng minh rằng môi trường được dựng là môi trường mà ta thật sự định kiểm thử.

### Tài liệu tham khảo chính thức

- Spring Framework — `@ActiveProfiles`: https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-activeprofiles.html
- Spring Boot — Externalized Configuration và profile-specific files: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot — Profiles và giới hạn `spring.profiles.active`: https://docs.spring.io/spring-boot/reference/features/profiles.html
- Spring Boot — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html
