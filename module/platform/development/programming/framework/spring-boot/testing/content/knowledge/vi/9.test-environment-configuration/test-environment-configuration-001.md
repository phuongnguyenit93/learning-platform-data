# Tìm @SpringBootConfiguration và ảnh hưởng của cấu trúc package

## 1. Vấn đề: vì sao cùng một @SpringBootTest nhưng có lớp chạy được, lớp báo thiếu cấu hình?

Trong dự án Spring Boot, các test thường dùng `@SpringBootTest`, `@WebMvcTest`, `@DataJpaTest` hoặc những test slice khác. Khi không khai báo class cấu hình cụ thể, Spring Boot cần tìm một **primary configuration** để làm điểm bắt đầu dựng `ApplicationContext`. Trường hợp thông dụng nhất là class chạy ứng dụng có `@SpringBootApplication`.

Vị trí đặt **package** của class test ảnh hưởng trực tiếp tới quá trình tìm cấu hình. Test nằm dưới package gốc ứng dụng có thể được phát hiện tự động; test ở package ngang hàng hoặc một nhánh không cùng cây cha có thể thất bại với thông báo gần như:

```text
IllegalStateException:
Unable to find a @SpringBootConfiguration, you need to use
@ContextConfiguration or @SpringBootTest(classes=...)
with your test
```

Thông báo cụ thể thay đổi theo phiên bản Spring Boot và loại test. Cốt lõi là: **Boot chưa tìm được class làm nguồn cấu hình**. Lỗi này khác hoàn toàn với lỗi **không tìm được bean** khi context đã được khởi tạo.

Bài học giúp bạn:

1. Hiểu mối quan hệ của `@SpringBootConfiguration`, `@SpringBootApplication`, `@Configuration` và `@TestConfiguration`.
2. Giải thích chính xác **thuật toán tìm primary configuration theo package** trong Spring Boot Test.
3. Thiết kế cấu trúc `src/main/java` và `src/test/java` để test tìm đúng cấu hình.
4. Phân biệt **tìm được class cấu hình** với **component scan tìm được bean**.
5. Khắc phục các lỗi không tìm được cấu hình, có nhiều cấu hình, và test slice lấy sai bean.
6. Viết và chạy các bài test Java 17+ chứng minh cơ chế auto-discovery và nguồn cấu hình tường minh.

## 2. Các annotation tham gia vào quá trình tìm cấu hình

| Annotation | Ý nghĩa | Có phải ứng viên primary configuration cho Boot Test? |
| --- | --- | --- |
| `@Configuration` | Đánh dấu class khai báo bean/configuration của Spring Framework | **Không tự động** được chọn bởi thuật toán tìm `@SpringBootConfiguration` theo package |
| `@SpringBootConfiguration` | Dạng `@Configuration` mang ý nghĩa cấu hình gốc của ứng dụng Boot | **Có**, khi nằm trong package được tìm |
| `@SpringBootApplication` | Kết hợp `@SpringBootConfiguration`, `@EnableAutoConfiguration` và `@ComponentScan` | **Có**, vì mang `@SpringBootConfiguration` theo meta-annotation |
| `@TestConfiguration` | Cấu hình chuyên dành cho test, bổ sung bean/thiết lập kiểm thử | **Không nên dùng làm primary application configuration mặc định**; nested test config thường được thêm vào root tìm được |
| `@SpringBootTest(classes = ...)` | Chỉ rõ class nguồn cho Spring Boot Test | **Bỏ qua nhu cầu tìm root tự động** cho những class đã chỉ định |
| `@ContextConfiguration(classes = ...)` | Chỉ rõ nguồn context cho Spring TestContext | Có thể dùng để cung cấp cấu hình tường minh thay cho discovery tự động |

Ba thành phần quan trọng của `@SpringBootApplication`:

```java
@SpringBootConfiguration
@EnableAutoConfiguration
@ComponentScan
public @interface SpringBootApplication {
    // Đây là mô tả ý nghĩa cấu thành, không phải
    // mã nguồn đầy đủ của annotation trong Spring Boot.
}
```

- `@SpringBootConfiguration` giúp Boot nhận diện class cấu hình gốc.
- `@EnableAutoConfiguration` kích hoạt các auto-configuration phù hợp classpath và điều kiện.
- `@ComponentScan` mặc định tìm Spring component từ package chứa application class xuống các package con.

Vì thế **`@SpringBootConfiguration` một mình không đồng nghĩa với `@SpringBootApplication`**: class được tìm làm root nhưng chưa chắc tự động scan service/controller/repository hoặc bật toàn bộ auto-configuration. Nếu tự viết root bằng `@SpringBootConfiguration`, phải chỉ rõ các cấu hình/scan/auto-configuration cần thiết.

## 3. Thuật toán tìm @SpringBootConfiguration theo package

Với các annotation test tích hợp Spring Boot, khi **chưa chỉ định nguồn cấu hình**, Spring Boot tìm từ **package của class test**, rồi lần lượt xét package cha, cho tới khi tìm thấy class có `@SpringBootApplication` hoặc `@SpringBootConfiguration`.

Ví dụ:

```text
Class test: com.example.catalog.order.OrderServiceTest

Các package được xét từ gần tới xa:

com.example.catalog.order
          ↓
com.example.catalog
          ↓
com.example
          ↓
com
          ↓
(package mặc định)

Class ứng dụng:
com.example.catalog.CatalogApplication
    @SpringBootApplication

=> Tìm thấy khi xét com.example.catalog.
```

**Điểm cần nhớ:** “đi ngược lên” là đi theo **chuỗi package cha của test**, không phải quét đệ quy mọi package con của mỗi package cha để tìm mọi application class. Test ở `com.example.qa` không tự nhìn sang `com.example.catalog` chỉ vì hai package cùng có tiền tố `com.example`.

### 3.1. Vì sao vị trí class test có tác dụng?

Giả sử class ứng dụng được đặt:

```java
package com.example.catalog;

@SpringBootApplication
public class CatalogApplication { /* ... */ }
```

- Test ở `com.example.catalog`: phát hiện class ứng dụng.
- Test ở `com.example.catalog.order`: đi lên `com.example.catalog` và phát hiện.
- Test ở `com.example.catalog.order.read`: đi qua các package cha rồi phát hiện.
- Test ở `com.example.qa`: đi lên `com.example`, nhưng class ứng dụng lại ở **package con ngang hàng** `com.example.catalog`, nên không tự phát hiện.
- Test ở `com.other.catalog`: không cùng đường dẫn package với root.
- Test ở **default package** (không khai báo `package`): khó kiểm soát discovery và component scan; không nên thiết kế dự án Boot theo cách này.

Đây là lý do thông thường nên đặt test trong cùng package hoặc **package con** của application root.

### 3.2. Đường dẫn thư mục và package Java là hai khái niệm phải phân biệt

`src/main/java/com/example/catalog/CatalogApplication.java` chứa khai báo:

```java
package com.example.catalog;
```

Test có thể nằm ở:

```text
src/test/java/com/example/catalog/order/OrderServiceTest.java
```

với khai báo `package com.example.catalog.order;`. Hai file nằm ở hai **source set** khác nhau nhưng vẫn thuộc cây package thích hợp. Classpath test thường chứa class đã biên dịch từ cả `src/main/java` và `src/test/java`, nên test tìm thấy primary config nằm ở main source set.

Nếu đường dẫn thư mục và khai báo `package` không khớp, Java compiler có thể vẫn biên dịch trong một số cách build, nhưng package **được khai báo trong file** mới xác định tên class và ảnh hưởng tới search, không phải tên thư mục do mắt người nhìn thấy. Nên tổ chức chúng khớp nhau để tránh sai sót và hỗ trợ IDE.

### 3.3. Tìm class cấu hình không phải quét mọi bean

Hai thuật toán có điểm khởi đầu khác nhau:

```text
A. Test tìm primary configuration:
   package(test class) → package cha → @SpringBootConfiguration

B. Spring component scan mặc định:
   package(application class) → các package con
   → @Component, @Service, @Repository, @Controller, ...
```

Ví dụ test ở `com.example.catalog.order` đã tìm được `CatalogApplication` tại `com.example.catalog`, nhưng bean `com.example.billing.PaymentService` nằm ở package **ngang hàng** với `com.example.catalog`. Nếu chỉ dùng component scan mặc định, bean đó **không được tìm**. Đây là lỗi `NoSuchBeanDefinitionException` hoặc `UnsatisfiedDependencyException` sau khi đã tìm được root, không phải lỗi thiếu `@SpringBootConfiguration`.

Ngược lại, thêm `@ComponentScan("com.example.billing")` vào root có thể giúp tìm bean nhưng **không sửa thuật toán test tìm root** khi test đang nằm ở `com.example.qa`. Cần giải quyết đúng một trong hai tầng.

## 4. Cấu trúc package khuyến nghị cho Spring Boot

Với một ứng dụng Boot một root:

```text
catalog-service/
├── src/main/java/com/example/catalog/
│   ├── CatalogApplication.java         @SpringBootApplication
│   ├── order/
│   │   ├── OrderService.java           @Service
│   │   └── OrderRepository.java        @Repository
│   └── web/
│       └── OrderController.java        @RestController
└── src/test/java/com/example/catalog/
    ├── CatalogApplicationTests.java    @SpringBootTest
    ├── order/
    │   └── OrderServiceTest.java       @SpringBootTest hoặc unit test
    └── web/
        └── OrderControllerTest.java    @WebMvcTest
```

Vị trí `CatalogApplication` trong package **chung cao nhất mà ứng dụng sở hữu** giúp component scan tìm được hầu hết bean của cùng application. Test ở nhánh dưới đó có thể tìm primary configuration tự động.

Không đặt application class vào package `com.example.catalog.bootstrap.internal` nếu phần lớn controller/service nằm ở `com.example.catalog.order`, trừ khi ứng dụng đã chủ động cấu hình scan/import; làm vậy sẽ khiến component scan mặc định bỏ sót bean ở package anh em.

Mặt khác, đưa root lên package quá rộng như `com.example` có thể quét nhầm bean của nhiều ứng dụng hoặc module dùng chung nếu chúng cùng classpath. Chọn **package root đủ bao trùm một ứng dụng nhưng không bao trùm các ứng dụng độc lập**.

### Những bố cục dễ gây lỗi

| Bố cục | Vấn đề | Cách khắc phục phù hợp |
| --- | --- | --- |
| `@SpringBootApplication` ở `com.acme.app`, test ở `com.acme.tests` | Không tìm thấy root qua package cha | Đưa test dưới `com.acme.app` hoặc dùng `classes = AppApplication.class` |
| Application ở `com.acme.app.bootstrap`, `@Service` ở `com.acme.app.domain` | Có thể tìm được root nhưng scan mặc định bỏ qua domain | Đặt application ở `com.acme.app` hoặc định nghĩa scan/import rõ ràng |
| Có hai root Boot cùng được tìm ở một package | Không xác định primary configuration duy nhất | Chỉ định `classes` cho test hoặc điều chỉnh vị trí/role của root |
| Dự án nhiều module, test chung không cùng package app | Discovery phụ thuộc package của test | Chỉ định root application đúng của module đang kiểm tra |
| Một top-level `@Configuration` của test vô tình được scan | Bean thử nghiệm có thể xuất hiện ở test khác | Dùng `@TestConfiguration` + `@Import` có chủ đích |
| Đặt cấu hình quá đặc thù vào application root | Slice test có thể phải xử lý thêm cấu hình không thuộc phạm vi | Tách cấu hình thành class riêng và chỉ import khi cần |

## 5. Dự án ví dụ Java 17+ và Spring Boot 3.3.x

Ta tạo một ứng dụng nhỏ để **chứng minh trực tiếp** việc test tìm primary configuration theo package. Dùng Spring Boot 3.3.5 làm ví dụ phiên bản cụ thể, Java 17+ và Gradle. Những phiên bản này phục vụ bài thực hành, không ngụ ý là phiên bản mới nhất.

Cấu trúc:

```text
configuration-discovery-demo/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/catalog/
│   ├── CatalogApplication.java
│   └── service/
│       └── GreetingService.java
└── src/test/java/
    ├── com/example/catalog/service/
    │   ├── AutomaticPrimaryConfigTest.java
    │   ├── AdditiveTestConfigurationTest.java
    │   └── ExplicitMinimalConfigurationTest.java
    └── com/example/qa/
        └── ExplicitPrimaryConfigTest.java
```

### 5.1. Gradle setup

`settings.gradle`:

```groovy
rootProject.name = 'configuration-discovery-demo'
```

`build.gradle`:

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
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

`spring-boot-starter-test` cung cấp JUnit Jupiter, Spring Test và Spring Boot Test, cùng các thư viện kiểm thử phổ biến. Trong **ứng dụng Boot đã có Gradle/BOM riêng**, tái sử dụng dependency management hiện hữu; không cần đổi phiên bản dự án chỉ để thử đoạn code này.

### 5.2. Class ứng dụng làm primary configuration

`src/main/java/com/example/catalog/CatalogApplication.java`:

```java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
```

`src/main/java/com/example/catalog/service/GreetingService.java`:

```java
package com.example.catalog.service;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name is required");
        }
        return "Xin chào, " + name.strip() + "!";
    }
}
```

Class application ở `com.example.catalog`. Vì `@SpringBootApplication` chứa component scan mặc định, bean `GreetingService` ở `com.example.catalog.service` được phát hiện.

## 6. Ví dụ 1: test trong package con tự tìm được application

`src/test/java/com/example/catalog/service/AutomaticPrimaryConfigTest.java`:

```java
package com.example.catalog.service;

import com.example.catalog.CatalogApplication;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest
class AutomaticPrimaryConfigTest {
    @Autowired
    ApplicationContext context;

    @Autowired
    GreetingService greetingService;

    @Test
    void findsApplicationRootFromParentPackage() {
        assertNotNull(context.getBean(CatalogApplication.class));
        assertEquals("Xin chào, An!", greetingService.greet(" An "));
    }
}
```

Chạy:

```bash
./gradlew test --tests 'com.example.catalog.service.AutomaticPrimaryConfigTest'
```

**Kỳ vọng:** 1 test PASS nếu build/dependency tải thành công. Test không chỉ biết context tạo được mà còn xác minh `CatalogApplication` là một bean trong context và `GreetingService` có thể inject từ component scan.

Diễn biến:

1. Class test nằm ở `com.example.catalog.service`, không khai báo `classes` trong `@SpringBootTest`.
2. Boot tìm primary configuration ở `com.example.catalog.service`, sau đó `com.example.catalog`.
3. Tại `com.example.catalog`, Boot tìm thấy `CatalogApplication` mang `@SpringBootApplication`.
4. Spring Boot tạo `ApplicationContext` từ cấu hình này.
5. Component scan bắt đầu từ package của `CatalogApplication` và tìm thấy `GreetingService`.

Lưu ý `@SpringBootTest` và JUnit Jupiter phối hợp qua `SpringExtension` đã được tích hợp sẵn trong annotation Boot Test; không cần thêm `@ExtendWith(SpringExtension.class)` chỉ để test này chạy.

## 7. Ví dụ 2: test ở package ngang hàng phải chỉ rõ classes

Giờ đặt test tại `com.example.qa`. Đây là package **không nằm dưới `com.example.catalog`**. Nếu test chỉ viết `@SpringBootTest`, Boot có thể không tìm thấy root.

Cách chính xác và ổn định là chỉ định source:

`src/test/java/com/example/qa/ExplicitPrimaryConfigTest.java`:

```java
package com.example.qa;

import com.example.catalog.CatalogApplication;
import com.example.catalog.service.GreetingService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(classes = CatalogApplication.class)
class ExplicitPrimaryConfigTest {
    @Autowired
    GreetingService greetingService;

    @Test
    void usesExplicitApplicationEvenOutsideItsPackageTree() {
        assertEquals("Xin chào, Bình!",
                greetingService.greet(" Bình "));
    }
}
```

Chạy:

```bash
./gradlew test --tests 'com.example.qa.ExplicitPrimaryConfigTest'
```

**Kỳ vọng:** 1 test PASS. `classes = CatalogApplication.class` xác định rõ configuration source; test không cần phụ thuộc đường dò package. **Điểm quan trọng:** vì class nguồn vẫn là `CatalogApplication` ở `com.example.catalog`, phạm vi component scan mặc định **vẫn gắn với application class**, không đổi thành `com.example.qa`.

### Phản ví dụ: thiếu classes ở package sai

Nếu sửa annotation trong class ở `com.example.qa` thành:

```java
@SpringBootTest
class FailingOutsidePackageTest {
    @Test
    void contextLoads() {
    }
}
```

đây là **đoạn minh họa lỗi**, không thuộc bốn class PASS trong dự án thực hành. Với bố cục đã nêu và không có root Boot phù hợp ở các package cha, Boot không tìm được `@SpringBootConfiguration`. Không nên thêm file phản ví dụ vào bộ test chạy mặc định rồi kỳ vọng `gradle test` vẫn PASS.

Cách sửa có hai hướng: chuyển test vào nhánh `com.example.catalog` nếu hợp lý với module, hoặc giữ vị trí test và khai báo `@SpringBootTest(classes = CatalogApplication.class)`.

## 8. Ví dụ 3: nested @TestConfiguration bổ sung cấu hình vào root

Trong test có thể cần một bean chỉ dùng cho test, ví dụ `Clock.fixed(...)` để kết quả không phụ thuộc thời gian thực. Với Spring Boot, **nested `@TestConfiguration` được dùng bổ sung vào primary application configuration**, không thay thế cấu hình gốc.

`src/test/java/com/example/catalog/service/AdditiveTestConfigurationTest.java`:

```java
package com.example.catalog.service;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest
class AdditiveTestConfigurationTest {

    @TestConfiguration(proxyBeanMethods = false)
    static class FixedClockConfiguration {
        @Bean
        Clock testClock() {
            return Clock.fixed(
                    Instant.parse("2024-01-01T00:00:00Z"),
                    ZoneOffset.UTC
            );
        }
    }

    @Autowired
    Clock clock;

    @Autowired
    GreetingService greetingService;

    @Test
    void keepsApplicationBeanAndAddsTestClock() {
        assertNotNull(greetingService);
        assertEquals("2024-01-01T00:00:00Z",
                clock.instant().toString());
        assertEquals("Xin chào, An!",
                greetingService.greet("An"));
    }
}
```

Chạy:

```bash
./gradlew test --tests 'com.example.catalog.service.AdditiveTestConfigurationTest'
```

**Kỳ vọng:** 1 test PASS. Root ứng dụng được tìm từ package của test như ví dụ 1; class nested `@TestConfiguration` cung cấp thêm `Clock`; `GreetingService` của application vẫn có sẵn.

### @TestConfiguration khác nested @Configuration

- **Nested `@TestConfiguration`:** Boot Test dùng *thêm vào* primary configuration đã tìm. Phù hợp bổ sung bean fixture, cấu hình test đặc thù.
- **Nested `@Configuration` thông thường:** Spring Test có thể sử dụng làm nguồn cấu hình **thay cho** primary application configuration; đây là khác biệt có thể khiến bean ứng dụng không được nạp.
- **Top-level `@TestConfiguration`:** được đánh dấu không tự xuất hiện từ component scan thông thường; nên import có chủ đích vào test cần nó bằng `@Import(MyTestConfiguration.class)`.

Đừng đổi nested `@TestConfiguration` thành `@Configuration` chỉ để tránh import: điều đó có thể thay đổi toàn bộ context đang kiểm tra. Và đừng đặt top-level `@Configuration` phục vụ test vào một package mà application scan rộng tới đó nếu không muốn các bean test xuất hiện bất ngờ.

## 9. Ví dụ 4: classes tường minh với cấu hình nhỏ

Đôi khi mục tiêu test chỉ là kiểm tra một vài bean, không cần scan cả ứng dụng. `@SpringBootTest(classes = ...)` có thể dùng một `@Configuration` cụ thể. Đó là **lựa chọn có chủ đích**, khác với việc để Boot tự tìm root.

`src/test/java/com/example/catalog/service/ExplicitMinimalConfigurationTest.java`:

```java
package com.example.catalog.service;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import com.example.catalog.CatalogApplication;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.NoSuchBeanDefinitionException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest(classes = ExplicitMinimalConfigurationTest.MinimalConfig.class)
class ExplicitMinimalConfigurationTest {

    @Configuration(proxyBeanMethods = false)
    static class MinimalConfig {
        @Bean
        Clock testClock() {
            return Clock.fixed(
                    Instant.parse("2024-03-01T00:00:00Z"),
                    ZoneOffset.UTC
            );
        }
    }

    @Autowired
    Clock clock;

    @Autowired
    ApplicationContext context;

    @Test
    void usesOnlyRequestedConfigurationSource() {
        assertEquals("2024-03-01T00:00:00Z",
                clock.instant().toString());
        assertThrows(NoSuchBeanDefinitionException.class,
                () -> context.getBean(CatalogApplication.class));
        assertThrows(NoSuchBeanDefinitionException.class,
                () -> context.getBean(GreetingService.class));
    }
}
```

Chạy:

```bash
./gradlew test --tests 'com.example.catalog.service.ExplicitMinimalConfigurationTest'
```

**Kỳ vọng:** 1 test PASS với cấu hình mẫu. Bean `Clock` được tạo trực tiếp; `CatalogApplication` và `GreetingService` không được scan vì root được cung cấp chỉ là `MinimalConfig`, vốn không khai báo `@ComponentScan`. `SpringBootTest(classes=...)` không tự “bật full application” nếu class chỉ định thực chất là một `@Configuration` tối giản.

Với kiểm thử bean nhỏ, cũng có thể dùng `@SpringJUnitConfig(MinimalConfig.class)` để tạo context Spring Framework mà không cần lựa chọn mô hình Spring Boot đầy đủ. Chọn cách phù hợp với điều cần chứng minh: application auto-configuration hay cấu hình component cụ thể.

### Bốn test PASS có ý nghĩa khác nhau

| Test | Package test | Configuration source | Kỳ vọng |
| --- | --- | --- | --- |
| `AutomaticPrimaryConfigTest` | `com.example.catalog.service` | Auto-discovery từ parent package | Có app bean và service |
| `ExplicitPrimaryConfigTest` | `com.example.qa` | `classes = CatalogApplication.class` | Có service dù test ở package ngoài |
| `AdditiveTestConfigurationTest` | `com.example.catalog.service` | App root + nested `@TestConfiguration` | Có service và clock cố định |
| `ExplicitMinimalConfigurationTest` | `com.example.catalog.service` | `classes = MinimalConfig.class` | Có clock, không có app/service |

Chạy cả bộ:

```bash
./gradlew test
```

**Kỳ vọng:** 4 test PASS (mỗi class có một method), miễn project được tạo đúng cấu trúc và dependencies tải được. Không có stdout nghiệp vụ cố định; Gradle báo trạng thái build/test và ghi HTML report ở `build/reports/tests/test/index.html`. Test context có thể khởi tạo nhiều lần do cấu hình khác nhau; điều đó không làm thay đổi số method.

## 10. Khi nào việc tìm @SpringBootConfiguration bị lỗi?

### 10.1. Không có root trên nhánh package cha

Triệu chứng điển hình:

```text
Unable to find a @SpringBootConfiguration
```

Nguyên nhân thường là test nằm ở `com.example.tests`, trong khi app ở `com.example.orders`; hoặc ứng dụng có nhiều module nhưng class test nằm ở package dùng chung không thuộc module cần kiểm tra.

Hướng xử lý:

1. Xác định **package khai báo thực tế của test class**.
2. Xác định package/class mang `@SpringBootApplication` hoặc `@SpringBootConfiguration` của ứng dụng cần kiểm tra.
3. Kiểm tra class application có thuộc chính package test hoặc một package cha không.
4. Nếu có thể, tổ chức test trong cây package ứng dụng.
5. Nếu test ở vị trí đặc biệt có lý do, khai báo `classes = YourApplication.class` đúng source.

Không giải quyết bằng cách thêm một `@SpringBootApplication` mới tùy tiện trong `src/test/java`: một root giả có thể khiến test khởi tạo sai cấu hình và bỏ qua bean thật của ứng dụng.

### 10.2. Có nhiều root ứng viên

Nếu Spring Boot tìm thấy **nhiều class `@SpringBootConfiguration` trong phạm vi package đang xét**, nó có thể báo lỗi kiểu:

```text
Found multiple @SpringBootConfiguration annotated classes
```

Điều này có thể xảy ra khi một source set/test classpath đưa nhiều application root vào **cùng phạm vi tìm kiếm**, nhất là multi-module hoặc ứng dụng thử nghiệm có nhiều bootstrapping class. Không nên nhầm rằng hai root ở hai package con bất kỳ luôn bị quét cùng lúc: thuật toán đi **theo package cha**, không phải quét cả cây con.

Cách xử lý thường là chỉ rõ một source phù hợp bằng `@SpringBootTest(classes = CorrectApplication.class)` hoặc tách cấu hình ứng dụng để mỗi test có primary configuration không nhập nhằng.

### 10.3. Đã tìm được root nhưng vẫn thiếu bean

Ví dụ:

```text
NoSuchBeanDefinitionException:
No qualifying bean of type 'com.example.billing.PaymentService'
```

Đây là dấu hiệu **context đã được khởi tạo đến bước wiring bean** nhưng thiếu bean theo yêu cầu. Kiểm tra component scan base package, `@Component`/`@Service` annotations, điều kiện `@Conditional...`, `@Profile`, `@Import`, `@Bean` và phạm vi test slice. Việc thêm `classes=...` chỉ sửa lỗi source khi root bị chọn sai; nó không tự bảo đảm bean nằm ở package ngoài phạm vi scan.

### 10.4. Tạo nested @Configuration vô tình thay root

Test có thể có dạng:

```java
@SpringBootTest
class OrderServiceContextTest {
    @Configuration
    static class Config {
        @Bean
        Clock clock() {
            return Clock.systemUTC();
        }
    }
}
```

Đây là **đoạn minh họa không độc lập**: cần import các annotation/Clock, và tên test chỉ là ví dụ. Với nested `@Configuration`, cấu hình này có thể được Spring Test chọn như primary context source, khiến app beans không được tải. Nếu mục tiêu là **bổ sung** bean Clock cho Boot context, đổi nested class thành `@TestConfiguration`, như ví dụ 3.

### 10.5. Test chạy từ sai module hoặc source set

Trong Gradle multi-project, task `:module-a:test` sử dụng classpath theo module A. Nếu class `@SpringBootApplication` thực sự thuộc module B nhưng module A không đưa class đó vào test runtime classpath, discovery vẫn thất bại dù package tên trông hợp lệ. Test không thể tìm class **không có trên classpath**.

Đừng giải quyết bằng cách cho mọi module phụ thuộc mọi application module: điều đó có thể phá ranh giới kiến trúc và dẫn tới nhiều root. Kiểm tra module nào sở hữu ứng dụng, nơi test nên chạy, và dependency test cần thiết. Trong module chỉ là thư viện thuần không có root Boot, dùng JUnit Jupiter/Mockito hoặc Spring Test với `@ContextConfiguration`/`@SpringJUnitConfig` phù hợp.

## 11. Ảnh hưởng đến test slice

Các annotation như `@WebMvcTest`, `@DataJpaTest`, `@JsonTest` cũng sử dụng cơ chế Boot test configuration, nhưng **sau khi biết configuration source**, chúng dựng **slice context** thay vì toàn bộ ứng dụng.

Ví dụ:

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {
    // Kiểm tra MVC mapping/HTTP behavior của OrderController.
}
```

Đây là **đoạn minh họa**, cần controller thực và các dependency/MockMvc phù hợp. `@WebMvcTest` thường chỉ nạp các bean liên quan MVC, không tự động tạo mọi service/repository ngoài slice. Việc tìm được `@SpringBootApplication` **không có nghĩa** toàn bộ bean sẽ được nạp trong test slice.

### @ComponentScan tường minh và TypeExcludeFilter

Spring Boot dùng các filter mặc định trong cấu hình scan của `@SpringBootApplication` để hỗ trợ test slice đúng phạm vi. Khi viết thêm `@ComponentScan(...)` tường minh ngay trên application class, những exclude filter mặc định liên quan slice có thể không còn hiệu lực theo cách mong muốn. Kết quả là `@DataJpaTest` hoặc `@WebMvcTest` bất ngờ nạp bean/config ngoài slice và gặp lỗi.

Nếu cần scan thêm package, ưu tiên cân nhắc tách cấu hình scan thành class riêng được import có chủ đích. Khi buộc dùng custom `@ComponentScan`, phải tính đến `TypeExcludeFilter` và các filter cần thiết cho slice test. Không coi việc bỏ qua error bằng cách thêm `@SpringBootTest` vào cùng lớp `@WebMvcTest` là cách sửa: không kết hợp hai kiểu Boot test bootstrap đó.

Một vấn đề khác là đặt cấu hình domain-specific (ví dụ bật Mongo auditing) trên application root: nó có thể gây tác dụng ngoài ý muốn cho các slice không cần Mongo. Hãy tách thành `@Configuration` riêng để test có thể import khi thật sự cần.

## 12. @TestConfiguration: tổ chức test setup mà không làm bẩn ứng dụng

Có hai kiểu sử dụng hữu ích.

**Nested config trong class test**:

```java
@SpringBootTest
class TimeSensitiveServiceTest {
    @TestConfiguration(proxyBeanMethods = false)
    static class FixedTimeConfig {
        @Bean
        Clock clock() {
            return Clock.fixed(
                    Instant.parse("2024-01-01T00:00:00Z"),
                    ZoneOffset.UTC
            );
        }
    }
}
```

Đoạn trên **minh họa cấu trúc**; các import và test method cần được bổ sung nếu dùng riêng. Nó thêm `Clock` vào context của test mà vẫn có primary app root.

**Top-level test config trong `src/test/java`**:

```java
@TestConfiguration(proxyBeanMethods = false)
public class SharedTestClockConfig {
    @Bean
    public Clock testClock() {
        return Clock.fixed(
                Instant.parse("2024-01-01T00:00:00Z"),
                ZoneOffset.UTC
        );
    }
}
```

Class này là **một phần của dự án**, cần package/import phù hợp. Để test sử dụng:

```java
@SpringBootTest
@Import(SharedTestClockConfig.class)
class ReportServiceTest {
    // @Autowired Clock ...
}
```

Việc import chủ động giúp tránh top-level test configuration vô tình ảnh hưởng mọi test. Tránh khai báo cùng lúc nhiều bean cùng type không có `@Primary`/`@Qualifier` rõ ràng vì có thể gây ambiguity. Nếu muốn **thay thế** bean đã tồn tại trong context, cần chọn cơ chế test bean override phù hợp, không mặc định tạo một `@Bean` trùng tên và trông chờ Boot cho phép override.

## 13. Cần phân biệt package search với component scan và auto-configuration

Cùng là “Spring không tìm thấy gì đó”, nhưng có ba giai đoạn độc lập:

```text
Giai đoạn 1 — Boot test chọn configuration source
    Test package -> parent packages -> @SpringBootConfiguration
    hoặc classes = ExplicitApplication.class

Giai đoạn 2 — Tạo context từ configuration source
    @EnableAutoConfiguration và @ComponentScan/@Import/@Bean
    -> Spring tạo bean definitions

Giai đoạn 3 — Resolve dependency vào test và các bean
    @Autowired, constructor injection, conditions, profiles, ...
```

| Lỗi nhìn thấy | Giai đoạn có vấn đề | Cách kiểm tra đúng |
| --- | --- | --- |
| “Unable to find a @SpringBootConfiguration” | 1 | Package test, vị trí application, explicit classes, classpath |
| “Found multiple @SpringBootConfiguration” | 1 | Số class root cùng được tìm, lựa chọn application thích hợp |
| “No qualifying bean of type ...” | 2 hoặc 3 | Scan/import/conditional/profile/test slice |
| “Failed to load ApplicationContext” | 2 hoặc 3 (hoặc hệ phụ thuộc) | Đọc root cause sâu nhất, cấu hình/bean/network/database |
| Application class được tìm nhưng controller không có | 2 hoặc slice restriction | Component scan base package, `@WebMvcTest` filter, bean condition |
| Test chạy từ module khác báo thiếu class/bean | 1 hoặc 2 | Test runtime classpath và module ownership |

Đừng vội sửa package khi lỗi là cấu hình datasource, thiếu profile, component condition hoặc JPA mapping. Cần đọc stack trace để xác định lớp lỗi.

### @ActiveProfiles và test properties không đổi thuật toán tìm root

`@ActiveProfiles("test")`, `@TestPropertySource` hoặc `@SpringBootTest(properties = "...")` thay đổi môi trường/properties hoặc conditional bean selection. Chúng **không tự động làm Boot tìm `@SpringBootConfiguration` ở package khác**. Nếu root không được phát hiện, thêm property không giải quyết nguyên nhân.

### Context cache

Spring Test có cache `ApplicationContext` cho các test có cấu hình tương thích. Khi thay `classes`, nested `@TestConfiguration`, active profiles hoặc properties, cache key có thể khác và Spring phải tạo context mới. Nên tránh dùng `@DirtiesContext` tràn lan và không thay root chỉ để chữa một bean nhỏ nếu không cần; mỗi context mới có thể tốn đáng kể thời gian test.

## 14. Hướng dẫn xử lý khi một test thất bại

Khi gặp lỗi cấu hình, đi theo trình tự sau:

1. **Đọc thông báo nguyên nhân đầu tiên có ích.** Có thật là “Unable to find a @SpringBootConfiguration” hay là “NoSuchBeanDefinitionException” bên trong context đã tìm đúng root?
2. **Đọc khai báo package của test** và application root. Vẽ đường đi từ test lên package cha để xem có gặp root không.
3. **Kiểm tra annotation root:** `@SpringBootApplication` hoặc `@SpringBootConfiguration`; một `@Configuration` độc lập không phải mặc nhiên là root tìm được.
4. **Xác định source có bị thay thế không:** test đã có nested `@Configuration`, `@ContextConfiguration(classes=...)` hoặc `@SpringBootTest(classes=...)` chưa?
5. **Nếu test ngoài cây package app**, chỉ định `classes = CorrectApplication.class` hoặc di chuyển test đúng nhánh.
6. **Nếu đã tìm root**, xem component scan base package; nếu bean nằm ngoài, cần cấu hình scan/import có chủ đích.
7. **Nếu dùng slice**, kiểm tra bean có thuộc slice không và root có custom component scan phá filter không.
8. **Nếu nhiều root**, chọn chính xác một source của ứng dụng muốn test và xem lại bố cục đa module.
9. **Nếu context load vẫn lỗi**, xem root cause về bean, profile, properties, database, port hoặc security; không quy tất cả cho package.
10. **Chạy đúng lớp để xác minh**, sau đó chạy phần test suite liên quan để bảo đảm sửa không ảnh hưởng context khác.

Các lệnh Gradle cho dự án mẫu:

```bash
./gradlew test --tests 'com.example.catalog.service.AutomaticPrimaryConfigTest'
./gradlew test --tests 'com.example.qa.ExplicitPrimaryConfigTest'
./gradlew test --tests 'com.example.catalog.service.AdditiveTestConfigurationTest'
./gradlew test --tests 'com.example.catalog.service.ExplicitMinimalConfigurationTest'
./gradlew test
```

Trên Windows, dùng `gradlew.bat` thay `./gradlew`. Với dự án Maven, cách chọn lớp qua Maven Surefire thường là `./mvnw -Dtest=AutomaticPrimaryConfigTest test`, nhưng project ví dụ này được cung cấp bằng Gradle.

## 15. Câu hỏi thường gặp

**Hỏi: `@SpringBootTest` có bắt buộc nằm cùng package với `@SpringBootApplication` không?**

Không nhất thiết. Test nằm trong **package con** có thể tìm lên package cha. Test ở ngoài cây package app vẫn chạy khi chỉ rõ `classes = Application.class` và class đó có trên test classpath.

**Hỏi: Tên file `CatalogApplication.java` có quyết định thuật toán tìm không?**

Tên file không phải điều kiện chính. Điều kiện là **class có annotation phù hợp trên classpath** và được tìm từ các package liên quan. Tên `*Application` là quy ước dễ đọc.

**Hỏi: `@SpringBootConfiguration` có tự scan `@Service` giống `@SpringBootApplication` không?**

Không. `@SpringBootConfiguration` không tự tương đương bộ ba annotation của `@SpringBootApplication`. Phải kiểm tra `@ComponentScan`, `@EnableAutoConfiguration` và nguồn bean khác.

**Hỏi: Test có `@SpringBootTest(classes=...)` còn phải tìm root theo package không?**

Khi đã chỉ rõ nguồn cấu hình đủ dùng, Boot sử dụng source đó và không cần cơ chế tìm mặc định. Tuy nhiên class được chỉ định có thể tự import cấu hình khác, nên context cuối cùng còn phụ thuộc các annotation/bean trên source đó.

**Hỏi: Dùng nested `@TestConfiguration` có thay thế application không?**

Thông thường không: nó thêm vào primary configuration. Nested `@Configuration` thông thường lại có thể khiến Boot dùng cấu hình này **thay** primary app configuration.

**Hỏi: Tại sao thêm `@WebMvcTest` vẫn báo thiếu service?**

Vì MVC slice chỉ nạp nhóm bean MVC thích hợp. Việc tìm đúng `@SpringBootApplication` không có nghĩa test slice nạp toàn bộ service/repository; hãy mock/import collaborator cần thiết theo mục tiêu MVC.

**Hỏi: Một dự án có nhiều class `@SpringBootApplication` phải làm sao?**

Đảm bảo mỗi test có đúng context cần kiểm tra. Nếu test nằm ở vị trí có thể tìm ra nhiều root, chỉ rõ `classes = SpecificApplication.class`. Tránh dùng một lớp test không xác định app nào là đối tượng kiểm thử.

**Hỏi: Đổi `@ActiveProfiles("test")` có giúp tìm root không?**

Không. Active profile quyết định bean/properties được bật khi context chạy, không thay đổi đường tìm package root.

## 16. Bài thực hành kiểm chứng

Với project ở mục 5:

1. Giữ `AutomaticPrimaryConfigTest` ở `com.example.catalog.service` và chạy: xác nhận root được tìm tự động.
2. Di chuyển nội dung test đó sang package `com.example.qa`, đặt tên khác, giữ `@SpringBootTest` không có `classes`: dự đoán lỗi thiếu `@SpringBootConfiguration`. Chỉ làm trên test thử nghiệm; không phá bộ PASS.
3. Khôi phục, thêm `classes = CatalogApplication.class` cho test ở `com.example.qa`: xác nhận PASS.
4. Ở `AdditiveTestConfigurationTest`, kiểm tra vừa có `GreetingService` từ app vừa có `Clock` từ nested `@TestConfiguration`.
5. Trong `ExplicitMinimalConfigurationTest`, giải thích vì sao clock có mặt nhưng `GreetingService` không có; thay `classes` thành `CatalogApplication.class`, quan sát thay đổi context và điều chỉnh assertion cho hợp lý.
6. Thử tạo một service ở `com.example.billing` (ngoài `com.example.catalog`), sau đó thử autowire nó vào full app test: giải thích vì sao thiếu bean mặc dù root đã tìm được.
7. Đọc test report `build/reports/tests/test/index.html`, xác nhận số test thực thi và nguyên nhân thật của từng lỗi trước khi sửa.

Bài học cần rút ra là **“đường tìm configuration từ test lên package cha”** và **“đường component scan từ application xuống package con”** là hai quy tắc khác nhau.

## 17. Tài liệu tham khảo

- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html), đặc biệt phần *Detecting Test Configuration*, *Excluding Test Configuration* và *User Configuration and Slicing*.
- [Spring Boot 3.3 — @SpringBootTest Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/SpringBootTest.html).
- [Spring Boot 3.3 — @SpringBootConfiguration Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringBootConfiguration.html).
- [Spring Framework 6.1 — TestContext Framework](https://docs.spring.io/spring-framework/reference/6.1/testing/testcontext-framework.html), về context configuration và caching.

## 18. Tổng kết

Spring Boot Test tìm cấu hình gốc bằng cách bắt đầu từ **package của test**, đi ngược lên các package cha và chọn class mang `@SpringBootApplication` hoặc `@SpringBootConfiguration` phù hợp, trừ khi bạn đã cung cấp cấu hình tường minh. Một bố cục package nhất quán giúp phần lớn test tự tìm đúng application. Khi test nằm ở module/package khác hoặc cần context nhỏ, `classes = ...` giải quyết việc lựa chọn source một cách minh bạch.

Sau khi tìm được cấu hình, Spring còn phải **scan/import/tạo bean** theo annotation và phạm vi test slice. Biết phân biệt hai giai đoạn này, cùng vai trò đặc biệt của nested `@TestConfiguration`, sẽ giúp chẩn đoán chính xác lỗi “không tìm được Boot configuration” và lỗi “không tìm được bean”, tránh các cách sửa vô tình làm thay đổi toàn bộ test context.
