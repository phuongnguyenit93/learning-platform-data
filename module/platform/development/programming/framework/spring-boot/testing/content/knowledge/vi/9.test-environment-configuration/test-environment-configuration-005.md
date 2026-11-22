# @TestPropertySource và `properties` trên annotation kiểm thử Spring Boot

Khi một test cần chạy với cấu hình khác ứng dụng thông thường — chẳng hạn phí mặc định thấp hơn, bật feature flag hoặc dùng endpoint giả lập — Spring Boot cho phép **ghi đè từng property trong `Environment` của test**. Hai công cụ dễ gặp là `@TestPropertySource` của Spring Test và thuộc tính `properties` trên `@SpringBootTest` hoặc một số annotation kiểm thử slice. Chúng có thể làm test dùng đúng cấu hình mong muốn mà không sửa `application.yml` gốc, nhưng cần hiểu **nguồn cấu hình, thứ tự ưu tiên, phạm vi context và cách kiểm chứng giá trị thực sự đã bind vào bean**.

Bài học tập trung vào cách dùng, so sánh, thứ tự ghi đè và các lỗi thường gặp; ví dụ hoàn chỉnh dùng **Java 17, Spring Boot 3.3.x, Gradle và JUnit Jupiter**.

## 1. Tại sao cần ghi đè property cho một test?

Giả sử ứng dụng có cấu hình:

```yaml
pricing:
  base-fee: 100
  provider: standard
  feature-enabled: false
```

Ứng dụng dùng `pricing.base-fee` để tính `total = subtotal + baseFee`. Khi test quy tắc tổng tiền, bạn muốn đặt phí bằng `20` để assertion gọn và dễ đọc, hoặc bật `feature-enabled=true` cho tình huống riêng. Sửa trực tiếp cấu hình ứng dụng cho mỗi test không phù hợp vì các test có yêu cầu khác nhau và có thể chạy cùng một build.

Với Spring TestContext, annotation kiểm thử giúp tạo `ApplicationContext` có **test-specific property sources**. Khi bean dùng `@Value`, `Environment` hoặc `@ConfigurationProperties`, nó có thể nhận giá trị đã được override trong context đó.

Ví dụ ngắn:

```java
@SpringBootTest(properties = "pricing.base-fee=20")
class PricingTest {
    // Bean được Spring tạo trong test context sẽ thấy cấu hình phù hợp.
}
```

Đây là trích đoạn; các tệp Java runnable và assertion chi tiết nằm ở phần 5. **Chỉ nhìn thấy annotation chưa chứng minh bean đã dùng đúng giá trị**: test cần assert property có hiệu lực và/hoặc hành vi của service phụ thuộc property.

## 2. Bốn cách đưa cấu hình vào môi trường test

| Cơ chế | Ví dụ | Phù hợp nhất khi | Điểm cần lưu ý |
| --- | --- | --- | --- |
| `@SpringBootTest(properties = ...)` | `@SpringBootTest(properties = "pricing.base-fee=20")` | Một vài giá trị riêng cho integration test dùng Spring Boot context đầy đủ | `properties` được nạp vào test context; không đổi file cấu hình gốc |
| `@TestPropertySource(properties = ...)` | `@TestPropertySource(properties = "pricing.base-fee=35")` | Muốn biểu đạt override của Spring TestContext trực tiếp, có thể kết hợp file và inline | Cần test được chạy với Spring TestContext; inline thắng file trong cùng annotation |
| `@TestPropertySource(locations = ...)` | `@TestPropertySource(locations = "classpath:/pricing-override.properties")` | Nhiều key dùng chung hoặc một fixture cấu hình rõ ràng | Mặc định nạp `.properties` hoặc Java XML properties; không trực tiếp nạp YAML theo đường mặc định |
| `@ActiveProfiles("test")` + `application-test.yml` | Profile test chọn config-data theo quy tắc Spring Boot | Một bộ cấu hình môi trường test có nhiều property hoặc bean theo profile | Profile và property override là hai cơ chế bổ trợ, không đồng nghĩa |

Các annotation kiểm thử theo slice của Spring Boot, chẳng hạn `@WebMvcTest(properties = ...)` hoặc `@DataJpaTest(properties = ...)`, cũng có thuộc tính `properties` ở phiên bản hỗ trợ. **Tác dụng lên test context của slice ấy**, không tự mở rộng slice thành toàn bộ ứng dụng. Ví dụ một MVC slice không chứng minh cấu hình datasource hoặc transaction repository đã hoạt động nếu các bean đó không nằm trong slice.

### `@SpringBootTest(properties)` và `@TestPropertySource` có phải cùng một annotation?

Không. `@SpringBootTest` của Spring Boot tạo application context qua cơ chế khởi chạy Boot, đồng thời cho phép cung cấp các thuộc tính bổ sung qua `properties` (hoặc alias `value`). `@TestPropertySource` thuộc **Spring Test**, bổ sung file hoặc inline property sources cho `Environment` của context được test framework quản lý. Chúng có thể dùng cùng nhau nhưng cần tránh đặt nhiều giá trị khác nhau cho cùng một key trừ khi test chủ đích kiểm tra precedence.

Một unit test Java thuần chỉ dùng `@Test` mà **không kích hoạt Spring TestContext** sẽ không tự nạp property từ `@TestPropertySource`. Nếu chỉ cần unit test cho `new PriceService(new PricingProperties(...))`, hãy truyền cấu hình trực tiếp thay vì dựng context chỉ để sử dụng một số nguyên.

## 3. `@TestPropertySource`: ba hình thức cấu hình quan trọng

### 3.1. Inline `properties`: ngắn và gắn sát test

```java
@SpringBootTest
@TestPropertySource(properties = {
    "pricing.base-fee=35",
    "pricing.provider=inline-test"
})
class InlinePropertySourceTest {
}
```

Mỗi phần tử là một khai báo key/value kiểu Java properties. Có thể dùng `key=value`, `key:value` hoặc khoảng trắng theo cú pháp Spring Test; thực hành tốt là **dùng thống nhất dạng `key=value`** để dễ đọc và tránh thay đổi không cần thiết tới khóa cache test context. Trong Java annotation, hãy dùng chuỗi literal; không thể đặt phép tính Java động như `"pricing.base-fee=" + someRuntimeValue` trong annotation.

### 3.2. `locations`: nạp tệp có thể tái sử dụng

```java
@SpringBootTest
@TestPropertySource(
    locations = "classpath:/pricing-override.properties"
)
class FilePropertySourceTest {
}
```

File nên đặt trong `src/test/resources/pricing-override.properties` nếu chỉ dùng cho test:

```properties
pricing.base-fee=70
pricing.provider=file-test
pricing.feature-enabled=true
```

Cách viết `classpath:/...` làm rõ đường dẫn tính từ classpath root; nó tránh nhầm với đường dẫn tương đối. Với `@TestPropertySource("some.properties")`, một đường dẫn không có dấu slash/protocol được diễn giải tương đối với package của lớp khai báo annotation. File phải thực sự nằm trong test runtime classpath; lỗi sai đường dẫn thường khiến context khởi động thất bại.

**Định dạng file:** `@TestPropertySource` theo mặc định hỗ trợ tệp Java `.properties` và XML properties. Dù Spring Boot tự nạp `application.yml` hoặc `application-test.yml` qua cơ chế config-data, **đừng gắn `@TestPropertySource(locations = "classpath:/custom.yml")` rồi giả định YAML được hiểu tự động**. Spring Framework 6.1 có thể dùng `factory` tùy chỉnh để hỗ trợ format khác; nếu không cần tùy biến, nên dùng file `.properties` hoặc profile YAML theo cách Boot hỗ trợ.

### 3.3. Dùng đồng thời file và inline: inline thắng giá trị trùng key

```java
@SpringBootTest
@TestPropertySource(
    locations = "classpath:/pricing-override.properties",
    properties = "pricing.base-fee=35"
)
class FileAndInlinePricingTest {
}
```

Giả sử file có `pricing.base-fee=70`, `pricing.provider=file-test`, `pricing.feature-enabled=true`, giá trị hiệu lực trong context của test là:

| Key | File test | Inline | Giá trị được dùng |
| --- | --- | --- | --- |
| `pricing.base-fee` | `70` | `35` | **35** |
| `pricing.provider` | `file-test` | Không khai báo | **file-test** |
| `pricing.feature-enabled` | `true` | Không khai báo | **true** |

Đây là một ví dụ precedence có thể kiểm chứng bằng code ở phần 5. Tính năng này phù hợp khi hầu hết property ở file chung, còn một số test thay đổi một hoặc hai key.

### 3.4. Không tham số: có cơ chế dò file mặc định

`@TestPropertySource` trống **không** có nghĩa “lấy mọi file test”. Spring Test tìm file mặc định tương ứng với lớp test: với lớp `com.example.PricingTest`, tên thông thường là `classpath:com/example/PricingTest.properties`. Nếu không thấy file mặc định, Spring có thể ném `IllegalStateException`. Vì vậy trong nội dung giáo trình và dự án lớn, ghi `locations` hoặc `properties` tường minh giúp giảm nhầm lẫn.

## 4. Thứ tự ưu tiên: key nào thực sự thắng?

Spring Boot có nhiều nguồn property: default, application config-data, biến môi trường, Java system properties, command-line args, test annotations và các nguồn động. Nếu một key xuất hiện ở nhiều nguồn, nguồn có độ ưu tiên cao hơn quyết định giá trị được tra cứu trong `Environment`.

Trong Spring Boot **3.3**, tài liệu externalized configuration liệt kê các nguồn test có độ ưu tiên cao hơn config-data/command-line arguments. Với hai annotation đang học, có thể nhớ các quan hệ cần dùng:

1. Giá trị inline của `@TestPropertySource(properties = ...)` **ưu tiên hơn** giá trị cùng key trong `@TestPropertySource(locations = ...)`.
2. `@TestPropertySource` trong Boot 3.3 được xếp **trên** thuộc tính `properties` của `@SpringBootTest`/test slice khi cấu hình cùng key.
3. `@SpringBootTest(properties = ...)` thường được dùng để override giá trị trong `application.yml`, `application.properties` và `application-{profile}.yml` của context test.
4. Một nguồn property động do `@DynamicPropertySource` tạo có precedence cao theo Spring TestContext. Nếu kết hợp nhiều cơ chế test cùng ghi **một key**, tốt nhất đừng đoán từ thứ tự annotation trong source file: kiểm tra đúng **Environment và bean được bind** trong phiên bản framework thực tế.

Tài liệu Spring Framework mô tả `@DynamicPropertySource` và `@TestPropertySource` trong hai phần riêng, còn tài liệu Boot 3.3 có bảng độ ưu tiên tổng thể; khi tác động của nhiều nguồn động và inline chồng nhau trở thành một phần hợp đồng test, cần đo trực tiếp giá trị hiệu lực tại runtime. Ví dụ phần 5 **không tạo xung đột giữa dynamic và `@TestPropertySource`** để mỗi assert có ý nghĩa rõ ràng.

### Đọc giá trị hiệu lực thay vì đoán

```java
@Autowired
Environment environment;

@Test
void selectedPropertyIsVisible() {
    assertEquals(
            "35", environment.getProperty("pricing.base-fee"));
}
```

Đây là trích đoạn đặt trong lớp Spring test có import tương ứng. Ngoài `Environment`, nên assert **bean `@ConfigurationProperties` hoặc kết quả service** vì một property có thể tra được dưới dạng string nhưng chưa bind đúng kiểu, tên field hoặc chưa được business code dùng đến.

### Property bị override chỉ ở đâu?

Các annotation này **không sửa file YAML** và không ghi ngược lên operating system environment. Chúng đóng góp property sources cho `ApplicationContext` test. Nếu hai test class dùng config khác, Spring TestContext có thể tạo hai context được cache riêng. Không nên kỳ vọng một thay đổi của test A trở thành global default cho test B.

## 5. Dự án Spring Boot 3.3.x chạy được: kiểm tra các loại override

Ví dụ dùng **Java 17, Spring Boot 3.3.5, Gradle Groovy DSL, JUnit Jupiter** và không cần database hay web server. `PricingProperties` được Spring Boot bind từ `Environment`, còn `QuoteService` dùng giá trị đó tính phí. Nhờ vậy assertion kiểm tra được cả nguồn property lẫn hành vi thực tế.

### 5.1. Bố cục

```text
settings.gradle
build.gradle
src/main/resources/application.yml
src/main/java/com/example/testproperties/PropertyDemoApplication.java
src/main/java/com/example/testproperties/PricingProperties.java
src/main/java/com/example/testproperties/QuoteService.java
src/test/resources/pricing-override.properties
src/test/resources/application-test.yml
src/test/java/com/example/testproperties/BootInlinePropertiesTest.java
src/test/java/com/example/testproperties/FileAndInlinePropertiesTest.java
src/test/java/com/example/testproperties/CombinedAnnotationsTest.java
src/test/java/com/example/testproperties/ActiveProfilePropertiesTest.java
src/test/java/com/example/testproperties/DynamicPricingPropertyTest.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'test-property-overrides'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-test` chứa các thư viện kiểm thử Spring/JUnit cần thiết. Dùng Gradle Wrapper tương thích với Java 17 và Spring Boot 3.3.5 cho các lệnh ở dưới. Không yêu cầu một HTTP server vì bài chỉ khảo sát binding, precedence và hành vi service.

**`src/main/resources/application.yml`**

```yaml
pricing:
  base-fee: 100
  provider: standard
  feature-enabled: false
```

Đây là bộ giá trị mặc định của ví dụ; nếu không có override hoặc profile test, service sẽ cộng phí 100 vào `subtotal`.

**`src/main/java/com/example/testproperties/PropertyDemoApplication.java`**

```java
package com.example.testproperties;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class PropertyDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(PropertyDemoApplication.class, args);
    }
}
```

**`src/main/java/com/example/testproperties/PricingProperties.java`**

```java
package com.example.testproperties;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "pricing")
public record PricingProperties(
        int baseFee,
        String provider,
        boolean featureEnabled) {
}
```

`@ConfigurationPropertiesScan` giúp Spring Boot tìm và đăng ký record `PricingProperties`. Với Java record có một constructor canonical, Spring Boot có thể bind constructor parameters từ `pricing.base-fee`, `pricing.provider`, `pricing.feature-enabled`. Kiểu `int` và `boolean` được convert từ property source. Ví dụ không đặt Bean Validation constraints nên đây là **demo binding**, chưa phải demo chặn mọi cấu hình thiếu hoặc sai.

**`src/main/java/com/example/testproperties/QuoteService.java`**

```java
package com.example.testproperties;

import org.springframework.stereotype.Service;

@Service
public class QuoteService {
    private final PricingProperties pricing;

    public QuoteService(PricingProperties pricing) {
        this.pricing = pricing;
    }

    public int quote(int subtotal) {
        if (subtotal < 0) {
            throw new IllegalArgumentException(
                    "subtotal must be non-negative");
        }
        return Math.addExact(subtotal, pricing.baseFee());
    }
}
```

`quote(100)` phải trả 120 nếu `baseFee=20`, 135 nếu `baseFee=35`, 180 nếu `baseFee=80`. `Math.addExact` ném `ArithmeticException` khi tràn `int`; đây là cơ chế Java độc lập với property source, giúp demo không trả số tràn sai âm thầm.

### 5.2. Test `@SpringBootTest(properties)`: override ngắn ngay trên annotation

**`src/test/java/com/example/testproperties/BootInlinePropertiesTest.java`**

```java
package com.example.testproperties;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

@SpringBootTest(properties = {
        "pricing.base-fee=20",
        "pricing.provider=boot-inline"
})
class BootInlinePropertiesTest {
    @Autowired
    private Environment environment;

    @Autowired
    private PricingProperties pricing;

    @Autowired
    private QuoteService service;

    @Test
    void inlinePropertiesReachEnvironmentBeanAndBusinessCode() {
        assertEquals("20", environment.getProperty("pricing.base-fee"));
        assertEquals(20, pricing.baseFee());
        assertEquals("boot-inline", pricing.provider());
        assertFalse(pricing.featureEnabled());
        assertEquals(120, service.quote(100));
    }
}
```

Giá trị `pricing.feature-enabled` không được override ở annotation nên tiếp tục lấy `false` từ `application.yml`. Đây là bằng chứng về việc override **chọn lọc** chứ không thay cả tập cấu hình.

### 5.3. Test `@TestPropertySource(locations, properties)`: file cộng inline

**`src/test/resources/pricing-override.properties`**

```properties
pricing.base-fee=70
pricing.provider=file-test
pricing.feature-enabled=true
```

**`src/test/java/com/example/testproperties/FileAndInlinePropertiesTest.java`**

```java
package com.example.testproperties;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.TestPropertySource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@TestPropertySource(
        locations = "classpath:/pricing-override.properties",
        properties = "pricing.base-fee=35"
)
class FileAndInlinePropertiesTest {
    @Autowired
    private Environment environment;

    @Autowired
    private PricingProperties pricing;

    @Autowired
    private QuoteService service;

    @Test
    void inlineValueOverridesFileButOtherFileValuesRemain() {
        assertEquals("35", environment.getProperty("pricing.base-fee"));
        assertEquals(35, pricing.baseFee());
        assertEquals("file-test", pricing.provider());
        assertTrue(pricing.featureEnabled());
        assertEquals(135, service.quote(100));
    }
}
```

Ba nguồn cùng có `pricing.base-fee`: file `application.yml` (100), `pricing-override.properties` (70), inline `@TestPropertySource` (35). Kết quả 35 là phép kiểm chủ đích về **inline override**. Test đồng thời chứng minh những key chỉ có ở file test vẫn được bind thành công.

### 5.4. Kết hợp hai annotation và kiểm tra precedence trong Boot 3.3

**`src/test/java/com/example/testproperties/CombinedAnnotationsTest.java`**

```java
package com.example.testproperties;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(properties = {
        "pricing.base-fee=15",
        "pricing.provider=boot-annotation"
})
@TestPropertySource(properties = "pricing.base-fee=45")
class CombinedAnnotationsTest {
    @Autowired
    private PricingProperties pricing;

    @Autowired
    private QuoteService service;

    @Test
    void testPropertySourceWinsForTheSameKey() {
        assertEquals(45, pricing.baseFee());
        assertEquals("boot-annotation", pricing.provider());
        assertEquals(145, service.quote(100));
    }
}
```

Trong precedence của Spring Boot 3.3, `@TestPropertySource` được xếp trên test annotation `properties`. Vì vậy **`base-fee=45`** từ `@TestPropertySource` thắng `base-fee=15` của `@SpringBootTest`. Còn key `pricing.provider` chỉ override bằng `@SpringBootTest`, nên là `boot-annotation`.

Đây là test **để học và chứng minh precedence**, không phải khuyến nghị thường xuyên khai báo trùng key. Ở test nghiệp vụ, chỉ đặt một nguồn giá trị override cho từng key sẽ dễ bảo trì hơn.

### 5.5. Profile test: YAML là cơ chế config-data của Boot

**`src/test/resources/application-test.yml`**

```yaml
pricing:
  base-fee: 80
  provider: profile-test
  feature-enabled: true
```

**`src/test/java/com/example/testproperties/ActiveProfilePropertiesTest.java`**

```java
package com.example.testproperties;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@ActiveProfiles("test")
class ActiveProfilePropertiesTest {
    @Autowired
    private PricingProperties pricing;

    @Autowired
    private QuoteService service;

    @Test
    void profileSpecificYamlOverridesBaseConfiguration() {
        assertEquals(80, pricing.baseFee());
        assertEquals("profile-test", pricing.provider());
        assertTrue(pricing.featureEnabled());
        assertEquals(180, service.quote(100));
    }
}
```

`@ActiveProfiles("test")` kích hoạt profile `test` trong context; Boot tự nạp các config-data có profile phù hợp, ví dụ `application-test.yml`. `@ActiveProfiles` không đồng nghĩa với `@TestPropertySource` và không cần bạn chỉ đường dẫn YAML qua `locations`.

Nếu cùng key còn được ghi ở `@SpringBootTest(properties)` hoặc `@TestPropertySource(properties)`, nguồn test override có thể thắng giá trị trong profile YAML. Khi cần toàn bộ test suite dùng một cấu hình chung, profile YAML là điểm khởi đầu rõ ràng; khi cần 1–2 biến thể nhỏ cho một class, dùng inline property.

### 5.6. Property động: `@DynamicPropertySource` cho giá trị sinh khi chạy

**`src/test/java/com/example/testproperties/DynamicPricingPropertyTest.java`**

```java
package com.example.testproperties;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
class DynamicPricingPropertyTest {
    @DynamicPropertySource
    static void registerProperties(DynamicPropertyRegistry registry) {
        registry.add("pricing.base-fee", () -> 65);
    }

    @Autowired
    private PricingProperties pricing;

    @Autowired
    private QuoteService service;

    @Test
    void dynamicPropertyIsBoundIntoTheContext() {
        assertEquals(65, pricing.baseFee());
        assertEquals(165, service.quote(100));
    }
}
```

`@DynamicPropertySource` phù hợp khi giá trị chỉ biết lúc test chạy, ví dụ port URL của container thật. Method đăng ký phải `static` và nhận đúng một `DynamicPropertyRegistry`. Supplier được dùng để cung cấp giá trị khi property được resolve; **không coi đây là cơ chế tự cập nhật toàn bộ bean đã được bind nếu supplier đổi giá trị sau khi context khởi động**.

Trong ví dụ, dynamic key chỉ được đặt tại một nguồn test để tránh xung đột ưu tiên. Với container động, còn phải quản lý vòng đời container/resource tương ứng; đưa đúng property vào Spring chưa chứng minh dependency đó sẵn sàng hay test nghiệp vụ thành công.

## 6. Chạy toàn bộ ví dụ và tự xác nhận giá trị

Khi dự án có Gradle Wrapper phù hợp, từ thư mục gốc chạy:

```bash
./gradlew test
./gradlew test --tests com.example.testproperties.BootInlinePropertiesTest
./gradlew test --tests com.example.testproperties.FileAndInlinePropertiesTest
./gradlew test --tests com.example.testproperties.CombinedAnnotationsTest
./gradlew test --tests com.example.testproperties.ActiveProfilePropertiesTest
./gradlew test --tests com.example.testproperties.DynamicPricingPropertyTest
```

Trên Windows dùng `gradlew.bat test` với các tham số tương ứng. Test chạy JUnit Jupiter và Spring TestContext; không cần `bootRun` để kiểm tra các annotation vì `@SpringBootTest` tự tạo context cho test. Những test này không khởi chạy HTTP server (mặc định `@SpringBootTest` dùng môi trường web mô phỏng nếu có web application; demo không thêm web starter).

Với code và các property như trên, **các phép kiểm được thiết kế để PASS**. Đây là kết quả kỳ vọng theo logic ví dụ, không phải stdout thực tế của Gradle. Mỗi test assert cả giá trị binding lẫn kết quả service, tránh tình trạng `Environment` chứa key nhưng service không dùng đúng giá trị.

### Bảng kỳ vọng để đối chiếu khi test xanh

| Lớp test | Base fee cuối cùng | Provider | Feature enabled | `service.quote(100)` |
| --- | ---: | --- | --- | ---: |
| `BootInlinePropertiesTest` | 20 | `boot-inline` | false | 120 |
| `FileAndInlinePropertiesTest` | 35 | `file-test` | true | 135 |
| `CombinedAnnotationsTest` | 45 | `boot-annotation` | false | 145 |
| `ActiveProfilePropertiesTest` | 80 | `profile-test` | true | 180 |
| `DynamicPricingPropertyTest` | 65 | `standard` | false | 165 |

Nếu một phép assert không khớp, hãy kiểm tra **test class có annotation nào, profile nào đang active, file resource đã nằm đúng classpath chưa và có một nguồn property khác ghi cùng key hay không**. Không sửa expected result theo giá trị đang thấy cho test xanh; trước hết xác định yêu cầu cấu hình đúng là gì.

## 7. Context caching: property annotation có ảnh hưởng đến tốc độ test

Spring TestContext lưu cache `ApplicationContext` theo **merged context configuration**. Những yếu tố như cấu hình class, active profiles, test property locations, inline test properties và context customizer có thể ảnh hưởng đến cache key. Hai test có khác giá trị inline cho cùng key thường cần các context khác nhau; Spring không “chuyển” cùng một context từ giá 20 sang 35 chỉ bằng thay annotation.

Hậu quả thực tế:

- Gán inline property khác nhau không cần thiết cho hàng chục lớp có thể làm tăng số lần khởi động context.
- Các dòng inline có khác cách viết hoặc khoảng trắng nhưng ngữ nghĩa giống nhau cũng có thể ảnh hưởng việc nhận diện cache vì Spring dùng chuỗi cấu hình khi tạo cache key. Chọn một quy ước như `pricing.base-fee=20` và dùng thống nhất.
- Nếu nhiều test dùng cùng một cấu hình, gom property vào profile/file phù hợp hoặc dùng test base class/composed annotation theo nhu cầu giúp giảm cấu hình trùng.
- `@DirtiesContext` là công cụ yêu cầu loại context đã thay đổi khỏi cache; không dùng chỉ để chuyển một property trên từng test method nếu có thể xây test class/context riêng.

Quan trọng: **các thuộc tính khai báo trong annotation thường được quyết định khi context được tạo**, không phải công tắc có thể đổi tự do từ test method này sang method khác. Gọi `System.setProperty("pricing.base-fee", "99")` sau khi bean `PricingProperties` đã được bind không khiến bean record tự nhận 99. Hơn nữa, system property có phạm vi JVM và có thể làm rò trạng thái giữa test chạy song song.

## 8. Kế thừa `@TestPropertySource` và thứ tự khai báo

Với lớp test kế thừa một lớp cha có `@TestPropertySource`, Spring Test hỗ trợ `inheritLocations` và `inheritProperties`, mặc định đều **true**. Lớp con có thể bổ sung file và inline property; với các phần tử trùng key, cấu hình ở vị trí có precedence cao hơn sẽ thắng. Nếu muốn **thay thế** thay vì kế thừa một nhóm, có thể đặt `inheritLocations=false` hoặc `inheritProperties=false` theo trường hợp.

Các ví dụ sau là **trích đoạn minh họa**; chúng không nằm trong project runnable ở phần 5:

```java
@TestPropertySource(properties = "pricing.provider=parent")
abstract class ParentTestConfig {
}

@TestPropertySource(properties = "pricing.provider=child")
class ChildPricingTest extends ParentTestConfig {
}
```

Lớp con nhận `provider=child` cho key này. `@TestPropertySource` cũng có thể khai báo nhiều lần trên một class ở Spring Framework hiện đại; cấu hình được hợp nhất theo quy tắc TestContext. Khi có nhiều annotation/meta-annotation, hãy kiểm tra giá trị hiệu lực qua `Environment`, tránh suy luận cảm tính chỉ dựa vào thứ tự text trong tệp nguồn.

Nếu thiết kế nhiều lớp test cùng kế thừa cấu hình nền, nên cân nhắc một **composed annotation** hoặc base test context để làm rõ default chung. Cũng cần tránh kế thừa những override quá rộng làm test mới ngẫu nhiên dùng sai datasource, timeout hoặc feature flag.

## 9. Sai lầm thường gặp và hướng xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách sửa đúng |
| --- | --- | --- |
| `@TestPropertySource("config.yml")` không đọc đúng file | Loader mặc định của annotation không tự xử lý YAML | Dùng `.properties` hoặc cơ chế Boot `application-test.yml` theo profile; chỉ dùng custom factory khi cần |
| `@TestPropertySource` trống báo lỗi | Không tìm thấy file mặc định trùng tên lớp test | Ghi rõ `locations` hoặc `properties` |
| Inline ghi key sai, bean vẫn nhận default | Typo tên key; cấu hình khác có giá trị fallback | Assert cả `Environment` và `@ConfigurationProperties`; kiểm tra canonical kebab-case |
| Test đổi property nhưng bean vẫn giữ giá cũ | Bean được bind khi context khởi động; thay system property sau đó | Khai báo nguồn trước startup hoặc tạo context có cấu hình đúng |
| Test A và B có config khác nhưng tưởng cùng bean | TestContext cache key thay đổi theo annotation/profile | Chấp nhận context khác hoặc dùng cấu hình chung khi hợp lý |
| `@TestPropertySource(locations=...)` không thấy file | Sai classpath hoặc nhầm đường dẫn tương đối | Dùng `classpath:/...`, kiểm tra file trong `src/test/resources` |
| Cả hai annotation ghi một key, không rõ giá nào thắng | Chồng property sources với precedence khác nhau | Bỏ khai báo trùng khi không cần; nếu cần, assert kết quả ở runtime |
| Chỉ chạy `new QuoteService(...)` mà muốn thử property override | Không có Spring TestContext để bind config | Dùng `@SpringBootTest`/slice phù hợp và lấy bean bằng `@Autowired` |
| Bật `@ActiveProfiles("test")` nhưng không thấy YAML | File tên/đường dẫn sai, profile khác hoặc override ưu tiên cao hơn | Kiểm tra `application-test.yml`, active profiles, Environment và nguồn trùng key |
| Mock database nhưng tưởng override datasource đã hoạt động | Mock bỏ qua đường kết nối DB thật | Test context/wiring và integration test với datasource thực |
| Test chạy khác giữa IDE và CI | Không đồng nhất JVM args, profile, test resources, biến môi trường | Chuẩn hóa cách chạy; assert config quan trọng thay vì tin vào mặc định |

### Phân biệt “property tồn tại” và “hành vi được cấu hình đúng”

Ví dụ một test chỉ có:

```java
assertEquals("35", environment.getProperty("pricing.base-fee"));
```

mới cho biết `Environment` tra được chuỗi 35. Nếu class `PricingProperties` chưa được scan hoặc service không inject bean đó, test vẫn có thể xanh ở dòng này mà ứng dụng không sử dụng 35. Bởi vậy demo thêm assertion `pricing.baseFee() == 35` **và** `service.quote(100) == 135`. Đây là ba bước bằng chứng: key đã xuất hiện → binder ánh xạ đúng → nghiệp vụ dùng đúng.

Tương tự, nếu thuộc tính kiểu boolean được cấu hình từ chuỗi `true`, nên assert `pricing.featureEnabled()` thay vì chỉ tìm text có chứa chữ `true`. Với dữ liệu phức tạp, test type conversion, missing property và validation khi có yêu cầu.

## 10. Khi nào chọn cách nào trong một dự án thực?

**Chọn `@SpringBootTest(properties)`** khi test full context có một vài key riêng, ví dụ `feature.enabled=false` hoặc một số timeout an toàn. Nó ngắn gọn và giúp reviewer thấy ngay tình huống mà test được chạy.

**Chọn `@TestPropertySource(properties)`** khi cần dùng cơ chế test property của Spring Test, đặc biệt muốn kết hợp với `locations`, kế thừa cấu hình hoặc giải thích precedence một cách rõ ràng.

**Chọn `@TestPropertySource(locations)`** khi có nhiều key trong một fixture `.properties` dùng chung và muốn tách khỏi annotation Java. Giữ file nhỏ, có tên mô tả mục đích, tránh biến test-specific file thành một bản sao hoàn chỉnh của production config.

**Chọn `@ActiveProfiles("test")` + `application-test.yml`** khi cần cả một bộ cấu hình nền chung cho nhiều lớp test, có điều kiện theo profile hoặc muốn tận dụng YAML/config-data của Spring Boot.

**Chọn `@DynamicPropertySource`** khi giá trị xuất hiện sau khi tạo tài nguyên test, thường là URL/cổng của Testcontainers. Property không có sẵn tại compile-time nên inline annotation không biểu đạt tốt.

Các cách này **có thể phối hợp**, nhưng hãy ưu tiên một nguồn rõ ràng cho từng key ở mỗi kịch bản. Với test integration quan trọng, ghi trực tiếp assertion trên property và hành vi để phát hiện cấu hình không khớp.

## 11. Tự kiểm tra kiến thức

**A.** `application.yml` đặt `pricing.base-fee=100`; `@SpringBootTest(properties = "pricing.base-fee=20")`. Trong context của test, phí dự kiến là bao nhiêu? **20**. Đó là override inline của annotation kiểm thử Boot.

**B.** `pricing-override.properties` đặt `pricing.base-fee=70`, nhưng `@TestPropertySource(locations=..., properties="pricing.base-fee=35")`. Giá trị hiệu lực? **35**, vì inline có ưu tiên cao hơn file `locations`.

**C.** `@SpringBootTest(properties="pricing.base-fee=15")` và `@TestPropertySource(properties="pricing.base-fee=45")` dùng cùng key trong Spring Boot 3.3. Test ví dụ chứng minh gì? **45** thắng. Trong code nghiệp vụ, tránh tạo xung đột trùng key nếu không thật sự cần.

**D.** Có thể trỏ `@TestPropertySource(locations="classpath:/application-test.yml")` và mặc định YAML được parse như Boot config-data không? **Không**. Hãy dùng `@ActiveProfiles("test")` để Boot nạp `application-test.yml`, hoặc một `PropertySourceFactory` phù hợp nếu bắt buộc dùng file YAML qua annotation Spring Test.

**E.** Một unit test tạo `new PricingProperties(20, "test", false)` và inject vào `new QuoteService(...)`. Nó xác minh property trong `application.yml` đã được override chưa? **Chưa**. Nó chỉ kiểm tra logic với một object cấu hình được dựng thủ công.

**F.** Test chạy trong cùng JVM gọi `System.setProperty` để thay một key sau khi Spring context đã được tạo. Có bảo đảm mọi `@ConfigurationProperties` record nhận giá trị mới không? **Không**. Bean đã được bind trong vòng đời context; sửa system property còn gây rủi ro rò cấu hình giữa test.

### Checklist khi review PR có property override

- Mỗi key có nguồn override chủ đích, dùng đúng annotation/context chưa?
- Có lẫn `@TestPropertySource(locations)` với YAML mà không dùng factory không?
- File test `.properties` có trong `src/test/resources`, đường dẫn có rõ ràng không?
- Nếu dùng `@ActiveProfiles`, profile YAML có nạp đúng và có nguồn test ưu tiên cao hơn ghi cùng key không?
- Có assert cả `Environment`, bean `@ConfigurationProperties` và kết quả nghiệp vụ cần thiết không?
- Các test có phụ thuộc system property toàn JVM hoặc phải chạy theo thứ tự mới xanh không?
- Số lượng cấu hình inline khác nhau có làm context cache bị phân mảnh không?
- Test slice đang được dùng có đủ các bean để xác nhận hành vi cần kiểm tra không?
- Có phân biệt test values và cấu hình production; không suy rộng một context test sang môi trường triển khai khác không?

**Kết luận:** `@TestPropertySource` và `properties` trên annotation kiểm thử là các công cụ **tạo giá trị cấu hình dành riêng cho test context**. `@TestPropertySource` linh hoạt với file `.properties` và override inline; `@SpringBootTest(properties)` tiện cho vài key đặt ngay trên lớp test; profile YAML và dynamic properties giải quyết những nhu cầu khác. Cách sử dụng đáng tin cậy là **xác minh giá trị thực sự đã bind và hành vi của bean**, đồng thời hiểu phạm vi context và thứ tự ưu tiên để test độc lập, rõ ràng, dễ bảo trì.

### Tham khảo chính thức

- Spring TestContext — Test Property Sources: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/property-sources.html
- Spring Boot 3.3 — Externalized Configuration và PropertySource order: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring TestContext — Dynamic Property Sources: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html
- Spring Boot — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html
