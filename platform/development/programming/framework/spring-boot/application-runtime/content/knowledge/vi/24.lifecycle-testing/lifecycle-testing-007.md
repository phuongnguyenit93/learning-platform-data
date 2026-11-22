# Chọn useMainMethod khi cần kiểm chứng thiết lập trong main

**Module:** Spring Boot Application Runtime → **Kiểm thử vòng đời**. Bài học giải thích thuộc tính `useMainMethod` của `@SpringBootTest`, cách chọn `NEVER`, `WHEN_AVAILABLE` hoặc `ALWAYS`, và cách viết integration test chứng minh những cấu hình **được thực hiện trong `public static void main(String[] args)`** thực sự đã tham gia tạo `ApplicationContext`. Đối chiếu với trường hợp test tạo context **không đi qua main**, cách xử lý app không có main, side effects, cache context và tương tác với lifecycle startup.

**Môi trường thực hành:** Java 17+, Spring Boot 3.5.x, JUnit Jupiter 5, AssertJ, Maven. Dự án độc lập không cần mở web server; các test dùng `@SpringBootTest(webEnvironment = NONE)`. Các file Java và `pom.xml` dưới đây tạo một lab có thể build, không phải snippets rời. Một số đoạn mã mở rộng được đánh dấu rõ để tránh copy nhầm vào phần runnable.

**Điểm cốt lõi:** `@SpringBootTest` **mặc định không gọi `main()`**. Nếu cấu hình quan trọng chỉ nằm trong main — chẳng hạn `SpringApplication.setAdditionalProfiles(...)`, `addInitializers(...)`, `setApplicationStartup(...)` hoặc custom listeners — test mặc định có thể **không kiểm chứng** luồng khởi động production. Muốn kiểm chứng đúng đường `main`, chọn `useMainMethod = UseMainMethod.ALWAYS` và assert kết quả cụ thể.

## 1. Mục tiêu học tập

Sau bài, bạn cần:

1. Biết `useMainMethod` là thuộc tính của `org.springframework.boot.test.context.SpringBootTest`, kiểu `SpringBootTest.UseMainMethod`.
2. Diễn giải chính xác `NEVER` (mặc định), `WHEN_AVAILABLE` và `ALWAYS`.
3. Giải thích vì sao cùng một `@SpringBootApplication` có thể tạo hai contexts với thiết lập khác nhau khi test có hoặc không gọi main.
4. Chọn `ALWAYS` khi những hành vi main-only là hợp đồng bắt buộc của production.
5. Chọn `WHEN_AVAILABLE` khi muốn tận dụng main **nếu có**, nhưng chấp nhận fallback khi không có.
6. Chọn `NEVER` khi muốn bootstrap context theo test riêng, không cho phép side effects của main xen vào.
7. Viết test chứng minh profile riêng được `main()` thêm có/không active.
8. Viết test chứng minh `ApplicationContextInitializer` đăng ký trong main có/không tạo bean marker.
9. Kiểm `ConfigurableApplicationContext.getApplicationStartup()` sau main đã set `BufferingApplicationStartup`.
10. Phân biệt chạy `main` để cấu hình `SpringApplication` với gọi `main` trực tiếp từ một `@Test` (có nguy cơ tạo context thứ hai).
11. Biết `ALWAYS` fail khi không có main, còn `WHEN_AVAILABLE` fallback; có bài thực hành riêng với `@SpringBootConfiguration` không khai báo main.
12. Hiểu context caching của Spring Test, lifecycle hooks và vì sao main không chạy trước **mỗi** test method.
13. Nhận diện nguy cơ `System.exit`, static/global state, browser/service start, event listener, JVM shutdown hook và ports khi cho test chạy main.
14. Có ma trận QA xác nhận behavior mà không dựa vào thứ tự logs hoặc Maven test order.

## 2. @SpringBootTest khác việc gọi main trực tiếp ra sao?

Thông thường application có entrypoint:

~~~java
@SpringBootApplication
public class MyApplication {
    public static void main(String[] args) {
        SpringApplication.run(MyApplication.class, args);
    }
}
~~~

Đây là **snippet kiến trúc**, không phải file hoàn chỉnh của lab bên dưới. Nếu main chỉ gọi `SpringApplication.run(...)`, kết quả của test context mặc định thường khá tương đồng. Nhưng trong app thực, main có thể tạo `SpringApplication` rồi cấu hình:

~~~java
SpringApplication application =
        new SpringApplication(MyApplication.class);

application.setAdditionalProfiles("production-bootstrap");
application.addInitializers(context -> {
    // Thêm bean/nguồn cấu hình trong giai đoạn prepare.
});
application.setApplicationStartup(
        new BufferingApplicationStartup(2048));

application.run(args);
~~~

Đây là **snippet** cần import, class MyApplication và implementation initializer thích hợp; lab runnable ở mục 6 có mã đầy đủ.

Vì các lời gọi `setAdditionalProfiles`, `addInitializers`, `setApplicationStartup` **xảy ra trước khi Spring refresh context**, chúng có thể ảnh hưởng:

- Profile nào được bật khi đánh giá `@Profile`.
- Bean nào có sẵn ngay từ prepare/initialize context.
- Cách đo các bước startup và các event/metrics khởi động.
- Chế độ tạo `ApplicationContext`, banner, lazy initialization, listener registration và một số khởi tạo khác.
- Logic chạy trong `ApplicationRunner`, `CommandLineRunner` hoặc lifecycle components phụ thuộc environment/bean definitions.

`@SpringBootTest` không mặc định gọi method main chỉ vì annotation `@SpringBootApplication` trỏ tới class đó. Spring Boot Test có cơ chế **khởi tạo SpringApplication phục vụ test** từ configuration class. Vì thế test thông thường có thể thành công, trong khi runtime khởi động thực lại có profile/initializer/listener khác.

### 2.1. Ba đường bootstrap

~~~text
Ứng dụng chạy production/CLI
  -> Java main(args)
  -> customizations trên SpringApplication
  -> application.run(args)
  -> ApplicationContext refresh / lifecycle / runners / ready

@SpringBootTest (useMainMethod = NEVER) [mặc định]
  -> Spring Boot Test bootstrapper
  -> tạo SpringApplication phục vụ test
  -> load @SpringBootConfiguration
  -> refresh context / lifecycle / runners / ready
  -> KHÔNG gọi Java main

@SpringBootTest (useMainMethod = ALWAYS)
  -> Spring Boot Test bootstrapper
  -> tìm main trên @SpringBootConfiguration
  -> thực thi main trong luồng bootstrap do TestContext quản lý
  -> main cấu hình SpringApplication, gọi run(args)
  -> test sử dụng context của chính luồng bootstrap đó
~~~

`WHEN_AVAILABLE` chọn nhánh **dùng main nếu tìm được**, nếu không quay về nhánh **test-specific SpringApplication**. Không xem bản mô tả trên như một internal implementation diagram đảm bảo tất cả callback/thread timing; đó là sơ đồ ngữ nghĩa API được tài liệu Spring Boot 3.5 xác nhận.

## 3. Enum SpringBootTest.UseMainMethod

Đúng package:

~~~java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.UseMainMethod;
~~~

Bảng so sánh:

| Giá trị | Có gọi main? | Nếu không tìm thấy main | Trường hợp nên chọn |
|---|---|---|---|
| `NEVER` | **Không** | Vẫn tạo test-specific context nếu configuration hợp lệ | Test context cô lập khỏi setup main |
| `WHEN_AVAILABLE` | **Có nếu tìm được** | **Fallback** về cách test-specific | Project có module có/không có main, yêu cầu linh hoạt |
| `ALWAYS` | **Bắt buộc** | **Test fail** lúc bootstrap | Hợp đồng test phải đi qua setup trong main |

Giá trị mặc định của `@SpringBootTest.useMainMethod` là **`UseMainMethod.NEVER`**. Đây là hành vi có chủ đích của Spring Boot, không phải một lỗi test framework bỏ sót class main.

### 3.1. NEVER: chọn context test đặc thù

~~~java
@SpringBootTest(useMainMethod = UseMainMethod.NEVER)
class SomeContextTest {
}
~~~

Điều này cũng tương đương default khi chỉ xét useMainMethod:

~~~java
@SpringBootTest
class SomeContextTest {
}
~~~

Hai snippets trên không phải các file test đầy đủ; phần runnable ở mục 7 có assertions. Với `NEVER`, SpringBootTest vẫn refresh context, tạo beans, chạy các callback thích hợp cho bootstrapping test; chỉ **không thực thi Java main**. **Sai** khi nói “NEVER bỏ qua startup lifecycle”.

### 3.2. WHEN_AVAILABLE: chấp nhận không có main

~~~java
@SpringBootTest(useMainMethod = UseMainMethod.WHEN_AVAILABLE)
class MainOptionalTest {
}
~~~

Nếu class được xác định là `@SpringBootConfiguration` có `main`, Boot sử dụng nó; nếu không, Boot tạo test-specific `SpringApplication`. Khi yêu cầu “test chắc chắn đã chạy mã trong main”, `WHEN_AVAILABLE` **không đủ chặt**: nếu ai đó xóa hoặc chuyển main, test vẫn có thể boot thành công theo fallback và che đi thay đổi kiến trúc.

### 3.3. ALWAYS: fail-fast nếu thiếu main

~~~java
@SpringBootTest(useMainMethod = UseMainMethod.ALWAYS)
class MainContractTest {
}
~~~

Nếu configuration class không có main hợp lệ, test **không fallback** mà thất bại ở bootstrap. Khi main bắt buộc thực hiện instrumentation/initializer/listener, đây thường là giá trị phù hợp nhất.

**Lưu ý:** `ALWAYS` không thay `@SpringBootTest` bằng một process con. Main được thực thi trong cơ chế bootstrap test của Spring Boot; test framework vẫn quản lý context, dependency injection, cache và teardown. Không mặc định có PID/JVM mới hoặc hành vi giống `java -jar` 100%.

### 3.4. Phạm vi của annotation

`UseMainMethod` là **nested enum của `@SpringBootTest`**, không phải property `spring.test.use-main-method` trong `application.properties`. Đặt biến hệ thống hoặc khai báo một custom property giống tên enum không tự thay thế việc khai báo annotation.

Các test slice `@WebMvcTest`, `@DataJpaTest`, `@JsonTest` có bootstrap và phạm vi component khác. Không giả định mỗi slice có một thuộc tính `useMainMethod` hoặc cần chạy full main để test controller/repository. Mục tiêu của `ALWAYS` là **kiểm chứng full-context bootstrapping** khi main có cấu hình đáng kiểm.

## 4. Khi nào thật sự cần test đi qua main?

Các cấu hình xuất hiện trong main nên được đưa vào contract của integration test nếu chúng ảnh hưởng behavior:

| Thiết lập trong main | Có thể kiểm chứng bằng gì? | Lý do default NEVER bỏ sót |
|---|---|---|
| `setAdditionalProfiles("custom")` | `Environment.acceptsProfiles(...)`, bean `@Profile` | Profile không được thêm qua code main |
| `addInitializers(...)` | Bean marker, property source, init side effect | Initializer không được đăng ký từ main |
| `setApplicationStartup(...)` | `getApplicationStartup()`, timeline recorder | Test tạo SpringApplication riêng |
| `addListeners(...)` | Marker/log/bean observable từ listener | Listener main-only không được attach |
| `setDefaultProperties(...)` | `Environment.getProperty(...)` | Default properties từ main không được nạp |
| `setLazyInitialization(...)` | Bean creation timing/behavior phù hợp | Test có thể eager-init khác |
| `setApplicationContextFactory(...)` | Context class/type và infrastructure | Test có thể dùng context factory mặc định |
| `setBannerMode(...)` | Banner/log output | Thường ít giá trị nghiệp vụ; không test quá chặt stdout |
| Custom `SpringApplicationBuilder` | Parent/child structure, profiles, context | Bootstrap test mặc định không chạy builder code |
| Custom early listeners | Side-effect đo được hoặc trace marker | Bean `@EventListener` đăng ký trong context có thể quá muộn |

**Phân loại:** Nếu setup main chỉ là banner đổi màu hoặc in lời chào, không nhất thiết cần full test gọi main. Nếu setup đó quyết định bean graph, environment, startup instrumentation, observability, shutdown hooks hoặc cách bootstrap, nên kiểm chứng bằng `ALWAYS`. Ngoài ra các side effects khó kiểm thử có thể được tách ra thành configuration bean/initializer được kiểm riêng để đơn giản hóa.

## 5. Chọn kiểu test theo mục tiêu

| Mục đích | Cấu hình khuyến nghị | Bằng chứng tối thiểu |
|---|---|---|
| Kiểm service business đơn lẻ | Unit test không tạo context | Method result và fake dependencies |
| Kiểm Spring wiring chung | `@SpringBootTest` mặc định `NEVER` | Beans, config, lifecycle |
| Kiểm runtime đúng như main cấu hình | `@SpringBootTest(useMainMethod=ALWAYS)` | Profile/initializer/applicationStartup |
| Main có thể có/không theo module | `WHEN_AVAILABLE` | Tách nhánh có main và không main |
| Test thiếu main nhưng vẫn cần boot context | `WHEN_AVAILABLE` hoặc `NEVER` | Context load và bean đủ |
| Xác minh **test phải fail khi main bị xóa** | `ALWAYS` | Bootstrap fail khi không tìm thấy main |
| Kiểm HTTP thật | `@SpringBootTest(webEnvironment=RANDOM_PORT,...)` khi phù hợp | HTTP response + lifecycle |
| Test MVC không mở server thật | `@WebMvcTest` / full context MOCK | Request mapping/service boundary |
| Kiểm OS exit status, shutdown hooks và `System.exit` | Fork subprocess/JAR integration test | Process exit status, signals, logs |

Có thể dùng `@SpringBootTest(webEnvironment=NONE, useMainMethod=ALWAYS)` cho bài này, vì ta không kiểm HTTP. Đừng mở cổng thật để kiểm một profile/initializer mà test không cần. Các bean lifecycle vẫn khởi tạo được trong non-web context nếu có những dependencies tương ứng.

## 6. Dự án Maven Java 17/Spring Boot 3.5 chạy được

### 6.1. Cấu trúc thư mục

Tạo một Maven project tên `use-main-method-lab` với Java 17, Spring Boot 3.5.16, package `com.example.mainmethod`. Không cần dependency Spring Web/Actuator; `spring-boot-starter` và `spring-boot-starter-test` là đủ.

~~~text
use-main-method-lab/
  pom.xml
  src/main/java/com/example/mainmethod/
    MainMethodLabApplication.java
  src/main/resources/
    application.properties
  src/test/java/com/example/mainmethod/
    DefaultNeverTest.java
    AlwaysMainTest.java
    WhenAvailableMainTest.java
  src/test/java/com/example/nomain/
    NoMainConfiguration.java
    NoMainFallbackTest.java
~~~

**Chú ý packages:** `com.example.nomain` nằm **ngoài** phạm vi component scan mặc định của `com.example.mainmethod`, tránh configuration của thử nghiệm fallback bị scan vào full app. Mỗi `public class` được đặt vào file đúng tên. Chạy toàn bộ bằng Maven `test`.

### 6.2. pom.xml hoàn chỉnh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <groupId>com.example</groupId>
    <artifactId>use-main-method-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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

`spring-boot-starter-test` mang JUnit Jupiter, Spring Test và AssertJ phù hợp theo dependency management của parent POM. Không cần thêm version rời cho từng thư viện test. Nếu công ty đã chọn bản Spring Boot 3.5.x được phê duyệt khác, dùng version đó và chạy lại QA. Spring Boot 3.5.16 được phát hành vào tháng 6/2026; dùng nó ở đây như một phiên bản xác định cho lab, không khẳng định nó luôn là bản được khuyến nghị cho sản phẩm về lâu dài.

### 6.3. Main: ba thay đổi chỉ tồn tại khi chạy main()

File `src/main/java/com/example/mainmethod/MainMethodLabApplication.java`:

~~~java
package com.example.mainmethod;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;

@SpringBootApplication
public class MainMethodLabApplication {

    public static void main(String[] args) {
        System.out.println("LAB_MAIN_ENTER");

        SpringApplication app =
                new SpringApplication(MainMethodLabApplication.class);

        // (1) Them profile chi khi main() duoc goi.
        app.setAdditionalProfiles("main-only");

        // (2) Them initializer chi khi main() duoc goi.
        app.addInitializers(context -> context.getBeanFactory()
                .registerSingleton(
                        "registeredInMain",
                        new MainMarker("initializer")));

        // (3) Thay recorder truoc khi context refresh.
        app.setApplicationStartup(
                new BufferingApplicationStartup(2048));

        app.run(args);
    }

    @Bean
    @Profile("main-only")
    ProfileOnlyService profileOnlyService() {
        return new ProfileOnlyService("profile-bean");
    }

    public record MainMarker(String source) {
    }

    public record ProfileOnlyService(String source) {
    }
}
~~~

**Giải thích cơ chế:**

1. `LAB_MAIN_ENTER` là marker phụ để nhìn console, **không dùng nó làm assertion chính** vì context có thể được cache hoặc logs bị trộn bởi nhiều test.
2. `setAdditionalProfiles("main-only")` thêm profile active cho `SpringApplication` do main khởi tạo; method `@Bean @Profile("main-only")` chỉ được đăng ký khi profile đó active.
3. `addInitializers(...)` thêm một `ApplicationContextInitializer`. Trong `initialize(...)`, code đăng ký singleton tên `registeredInMain` thuộc type `MainMarker`. Bean marker này **không có `@Component` hay `@Bean`** nào khác, nên nó chỉ xuất hiện khi initializer ở main thực sự được dùng.
4. `setApplicationStartup(new BufferingApplicationStartup(2048))` thiết lập recorder trước `run`; context có `getApplicationStartup()` thuộc type `BufferingApplicationStartup` trong đường main.
5. `app.run(args)` là nơi Spring dựng/refresh context, tạo bean profile, kích hoạt runners/lifecycle như ứng dụng thông thường.
6. Không có `System.exit`, `SpringApplication.exit`, gọi lệnh hệ điều hành, mở server ngoài hoặc cấu hình global/static biến đổi trạng thái test. Nhờ vậy gọi main trong test an toàn hơn.
7. `MainMarker` và `ProfileOnlyService` là Java records nested **public**; test có thể truy xuất kiểu qua `MainMethodLabApplication.MainMarker.class` và `ProfileOnlyService.class`.
8. Marker được đăng ký bằng tên riêng, không bị Spring component scanning tạo trong nhánh `NEVER`.
9. Nếu chạy `java -jar` trực tiếp, không có Spring Web nên app sẽ khởi tạo CLI context và kết thúc bình thường nếu không có non-daemon work khác. Đây không phải web service cần giữ socket mở.

**Thiết lập thực tế cũng có thể thêm listener hoặc context factory trong main**, nhưng lab chọn ba cấu hình dễ assert bằng context. Không biến `System.out.println` hoặc static counter thành bằng chứng chính của luồng bootstrap.

### 6.4. application.properties

File `src/main/resources/application.properties`:

~~~properties
spring.application.name=use-main-method-lab
spring.main.banner-mode=off
logging.level.root=WARN
~~~

**Không đặt** `spring.profiles.active=main-only`, không đăng ký `registeredInMain` bằng configuration khác, và không khai báo custom `ApplicationStartup` ngoài main. Nếu thêm các thứ đó, test `NEVER` có thể nhìn thấy hiệu ứng tương tự dù không gọi main, làm hỏng thiết kế thí nghiệm.

## 7. Test 1 — NEVER: main không chạy và ba dấu hiệu không xuất hiện

File `src/test/java/com/example/mainmethod/DefaultNeverTest.java`:

~~~java
package com.example.mainmethod;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.core.env.Profiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = MainMethodLabApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class DefaultNeverTest {

    @Autowired
    private ApplicationContext context;

    @Test
    void defaultNeverSkipsMainCustomization() {
        assertThat(context.getEnvironment().acceptsProfiles(
                Profiles.of("main-only"))).isFalse();

        assertThat(context.getBeanNamesForType(
                MainMethodLabApplication.ProfileOnlyService.class))
                .isEmpty();

        assertThat(context.containsBean("registeredInMain"))
                .isFalse();
    }
}
~~~

**Tại sao không ghi `useMainMethod`?** Để chứng minh giá trị mặc định của `@SpringBootTest` là `NEVER`. Cùng annotation có thể viết rõ `useMainMethod = UseMainMethod.NEVER`, kết quả tương đương. Test vẫn load context, inject `ApplicationContext` và chạy JUnit. Nó không gọi Java main, nên profile `main-only` và initializer marker không xuất hiện.

Trong môi trường test chuẩn, điều kiện PASS của test này là **ba assertions đều false/empty**. Nếu người chạy đặt một global profile `main-only` qua environment, IDE hoặc JVM args, test có thể fail vì chính môi trường ngoài đã bật profile. Khi cần tính tái lập, dùng tên profile sentinel riêng và đảm bảo không có property profile ngoài can thiệp; không sửa test để chấp nhận profile vô tình bật.

**Không nhầm:** Không có `registeredInMain` **không** có nghĩa `@PostConstruct`, bean initialization hoặc Spring Boot lifecycle bị bỏ qua. `NEVER` chỉ ảnh hưởng đường **tìm và gọi `main`** trong lúc boot test context.

## 8. Test 2 — ALWAYS: bắt buộc main và xác nhận cả ba thay đổi

File `src/test/java/com/example/mainmethod/AlwaysMainTest.java`:

~~~java
package com.example.mainmethod;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.UseMainMethod;
import org.springframework.context.ApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.Profiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = MainMethodLabApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        useMainMethod = UseMainMethod.ALWAYS)
class AlwaysMainTest {

    @Autowired
    private ApplicationContext context;

    @Test
    void mainCustomizationsArePresent() {
        assertThat(context.getEnvironment().acceptsProfiles(
                Profiles.of("main-only"))).isTrue();

        assertThat(context.getBean(
                MainMethodLabApplication.ProfileOnlyService.class)
                .source()).isEqualTo("profile-bean");

        assertThat(context.getBean(
                "registeredInMain",
                MainMethodLabApplication.MainMarker.class)
                .source()).isEqualTo("initializer");

        assertThat(((ConfigurableApplicationContext) context)
                .getApplicationStartup())
                .isInstanceOf(BufferingApplicationStartup.class);
    }
}
~~~

**Ý nghĩa của bốn assertions:**

1. `main-only` có trong profiles vì `main` gọi `setAdditionalProfiles`.
2. Bean `ProfileOnlyService` được tạo vì `@Profile("main-only")` khớp environment.
3. Bean `registeredInMain` chứng minh initializer đăng ký riêng trong main đã được áp dụng.
4. `BufferingApplicationStartup` chứng minh cấu hình startup instrumentation gắn trước `run` đi vào context.

Những assertions này **mạnh hơn** việc chỉ tìm `LAB_MAIN_ENTER` trong stdout; không có đường nào khác trong lab tự tạo những hiệu ứng trên. Nếu ai vô tình bỏ `addInitializers(...)` hoặc `setApplicationStartup(...)` ở main, test báo lỗi đúng điều kiện cần kiểm.

**Một điểm cần nhớ:** `ALWAYS` **không** có nghĩa main chạy trước mỗi `@Test`. TestContext có thể cache application context; main được thực thi khi context cần được tạo. Assert hiệu ứng **đang có** trong context, không assert số lần method main được gọi từ một static counter.

## 9. Test 3 — WHEN_AVAILABLE: có main thì dùng

File `src/test/java/com/example/mainmethod/WhenAvailableMainTest.java`:

~~~java
package com.example.mainmethod;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.UseMainMethod;
import org.springframework.context.ApplicationContext;
import org.springframework.core.env.Profiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = MainMethodLabApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        useMainMethod = UseMainMethod.WHEN_AVAILABLE)
class WhenAvailableMainTest {

    @Autowired
    private ApplicationContext context;

    @Test
    void usesMainBecauseItExists() {
        assertThat(context.getEnvironment().acceptsProfiles(
                Profiles.of("main-only"))).isTrue();

        assertThat(context.containsBean("registeredInMain"))
                .isTrue();
    }
}
~~~

Trong dự án này `MainMethodLabApplication` có `public static void main(String[] args)`, nên `WHEN_AVAILABLE` đi qua main và hai assertions đều true. Nhưng nếu main bị chuyển/xóa trong một refactor và class configuration không còn main, `WHEN_AVAILABLE` **không fail-fast**; nó sẽ tạo test-specific context thay thế. Vì thế nếu bạn yêu cầu “main có setup bắt buộc”, hãy dùng **ALWAYS**, không dùng WHEN_AVAILABLE chỉ vì test hiện đang pass.

Điều khác biệt giữa `ALWAYS` và `WHEN_AVAILABLE` không nằm ở việc “có main thì cái nào cũng có hiệu quả”, mà ở **hợp đồng khi main không tồn tại**.

## 10. Test 4 — WHEN_AVAILABLE khi không có main: fallback

Để chứng minh fallback thực, tạo một configuration **không có main** ngoài package của app chính.

File `src/test/java/com/example/nomain/NoMainConfiguration.java`:

~~~java
package com.example.nomain;

import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.context.annotation.Bean;

@SpringBootConfiguration
@EnableAutoConfiguration
public class NoMainConfiguration {

    @Bean
    String fallbackBean() {
        return "created-without-main";
    }
}
~~~

File `src/test/java/com/example/nomain/NoMainFallbackTest.java`:

~~~java
package com.example.nomain;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.UseMainMethod;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = NoMainConfiguration.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        useMainMethod = UseMainMethod.WHEN_AVAILABLE)
class NoMainFallbackTest {

    @Autowired
    private ApplicationContext context;

    @Test
    void loadsContextWithoutAnyMainMethod() {
        assertThat(context.getBean("fallbackBean", String.class))
                .isEqualTo("created-without-main");
    }
}
~~~

Ở đây cấu hình hợp lệ `@SpringBootConfiguration + @EnableAutoConfiguration` không có `main()`, nhưng `WHEN_AVAILABLE` vẫn cho phép context được tạo. Đó là **fallback có chủ ý**. Test không phụ thuộc app chính có profile main-only.

### 10.1. ALWAYS với NoMainConfiguration sẽ như thế nào?

Nếu đổi annotation ở `NoMainFallbackTest` thành:

~~~java
@SpringBootTest(
        classes = NoMainConfiguration.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        useMainMethod = UseMainMethod.ALWAYS)
~~~

thì TestContext không tìm thấy main hợp lệ và **thất bại khi bootstrap**. Đây là **snippet thí nghiệm âm tính**, không để thay thế trong bộ bốn test xanh mặc định. Làm trên bản copy hoặc lệnh test riêng, sau đó phục hồi `WHEN_AVAILABLE`.

**Không cố khẳng định một exception message duy nhất:** Nội dung stack trace có thể thay đổi giữa các patch versions, nhưng điều kiện đúng là **test không thể hoàn tất bootstrap bằng fallback** khi `ALWAYS` mà cấu hình thiếu main.

### 10.2. Vì sao tách package?

Nếu đặt `NoMainConfiguration` dưới `com.example.mainmethod` và vô tình thêm `@ComponentScan`, nó có thể bị scan vào app chính, thay đổi bean graph/context search. Tách thành `com.example.nomain` và khai báo `classes` cụ thể ở các test giúp minh họa sạch, không “hai @SpringBootConfiguration cạnh tranh” trong cùng package auto scan.

## 11. Chạy tất cả test và đọc kết quả

### 11.1. Build/test bằng Maven

Trên Linux/macOS nếu project có Maven Wrapper:

~~~bash
java -version
./mvnw -version
./mvnw clean test
~~~

Nếu chỉ có Maven đã cài:

~~~bash
java -version
mvn -version
mvn clean test
~~~

Windows PowerShell với Maven Wrapper:

~~~powershell
java -version
./mvnw.cmd -version
./mvnw.cmd clean test
~~~

Windows PowerShell với Maven cài sẵn:

~~~powershell
java -version
mvn -version
mvn clean test
~~~

Dự án đặt `java.version=17`. Hãy xác nhận `java -version` và Maven đang dùng đúng JDK 17+; nếu `JAVA_HOME` chỉ sang JDK cũ, build có thể fail dù mã code đúng. Mỗi file test có class name kết thúc `Test` nên Maven Surefire nhận diện theo quy tắc mặc định từ parent POM.

### 11.2. Kết quả kỳ vọng

Bốn tests theo các classes:

| Test | useMainMethod | Main hiện hữu? | Kỳ vọng |
|---|---|---|---|
| `DefaultNeverTest` | NEVER (ngầm định) | Có | Profile main-only false, marker absent |
| `AlwaysMainTest` | ALWAYS | Có | Profile/bean/initializer/startup recorder present |
| `WhenAvailableMainTest` | WHEN_AVAILABLE | Có | Profile và marker present |
| `NoMainFallbackTest` | WHEN_AVAILABLE | Không | Fallback context load, bean present |

Khi sử dụng đúng file cấu hình và dependency, dự kiến bốn methods đều **PASS**. Maven Surefire có thể in summary tương tự “Tests run: 4, Failures: 0, Errors: 0”, nhưng format và thứ tự classes có thể thay đổi theo Maven/JDK, không bắt buộc phải giống một dòng stdout cố định.

Trong console, `LAB_MAIN_ENTER` có thể xuất hiện ở lần bootstrap context của `ALWAYS`/`WHEN_AVAILABLE`. Đừng assert tổng số lần in marker bằng 2 theo mọi môi trường, vì context caching, test execution order, test parallelism và việc test build có thể thay đổi. Assertions trên context là nguồn bằng chứng chính.

### 11.3. Chạy riêng từng class

Linux/macOS:

~~~bash
mvn -Dtest=DefaultNeverTest test
mvn -Dtest=AlwaysMainTest test
mvn -Dtest=WhenAvailableMainTest test
mvn -Dtest=NoMainFallbackTest test
~~~

Windows PowerShell với Maven:

~~~powershell
mvn "-Dtest=DefaultNeverTest" test
mvn "-Dtest=AlwaysMainTest" test
mvn "-Dtest=WhenAvailableMainTest" test
mvn "-Dtest=NoMainFallbackTest" test
~~~

Việc chạy riêng giúp tìm lỗi lớp nào mà không lệ thuộc vào thứ tự test suite. `mvn -Dtest=... test` có thể tạo context mới cho mỗi lần JVM test, không so sánh console count qua các tiến trình như một bất biến.

### 11.4. Chạy JAR thật

~~~bash
mvn clean package
java -jar target/use-main-method-lab-0.0.1-SNAPSHOT.jar
~~~

Khi chạy theo cách này, JVM gọi `main` theo entrypoint của JAR, nên có `LAB_MAIN_ENTER`, profile main-only và initializer. App là CLI không có server nên có thể kết thúc sau startup khi không còn non-daemon work. Nếu muốn kiểm profile/bean trong production entrypoint, cần thêm marker hoặc integration probe có kiểm soát; đừng chỉ in log mà bỏ qua trạng thái context.

**Không gọi `MainMethodLabApplication.main(args)` trực tiếp ở trong `@Test`** khi muốn dùng context do `@SpringBootTest` đã quản lý; hành động đó có thể tạo thêm một context độc lập, chạy callbacks hai lần và gây leak/conflict. Dùng `useMainMethod` để Spring Boot Test bootstrapper kiểm soát lifecycle.

## 12. Phân biệt tác động lên main và tác động lên ApplicationContext

### 12.1. Main trước refresh, Bean callbacks sau

Với code ở lab:

~~~text
TestContext bắt đầu tạo context
    |
    +-- Nếu NEVER:
    |      TestContext tạo SpringApplication riêng
    |      Không chạy LAB_MAIN_ENTER / setAdditionalProfiles
    |
    +-- Nếu ALWAYS hoặc WHEN_AVAILABLE có main:
    |      gọi main
    |      setAdditionalProfiles("main-only")
    |      addInitializers(...)
    |      setApplicationStartup(...)
    |      app.run(args)
    |
    +-- tạo/prepare ApplicationContext
    +-- chạy ApplicationContextInitializer
    +-- refresh bean factory
    +-- evaluate @Profile("main-only")
    +-- instantiate beans, @PostConstruct, callbacks
    +-- lifecycle start, events, runners
    +-- test method được chạy với context
~~~

Một `@PostConstruct` trong bean không được “bỏ qua” chỉ vì main không chạy. Khác biệt nằm ở **trạng thái/configuration đã được thiết lập trước khi bean lifecycle bắt đầu**.

### 12.2. Ngữ nghĩa của initializer

`app.addInitializers(...)` đăng ký initializer để Spring gọi **trong quá trình chuẩn bị context trước refresh**. Nó không phải listener gọi sau khi server ready. Nếu initializer thêm property source hoặc bean singleton thì bean graph của ứng dụng có thể khác so với test `NEVER`. Mục 6 dùng marker để kiểm điều đó.

Khi ứng dụng thực cần thiết lập initializer theo profile hoặc test mode, nên tách business rule khỏi method main để không hardcode điều kiện khó kiểm. Nhưng nếu production thực sự dựa vào initializer được đăng ký ở main, ít nhất một integration test phải đi qua main và assert outcome.

### 12.3. ApplicationStartup recorder

`BufferingApplicationStartup` phải được gắn trước `SpringApplication.run` mới có thể đo các steps từ giai đoạn bootstrap sớm. Test `ALWAYS` xác nhận context dùng đúng recorder. Test `NEVER` không nhận recorder main-only; nếu người dùng muốn test startup timeline, phải hoặc dùng `ALWAYS` hoặc tự cấu hình recorder trong TestContext theo phương thức được hỗ trợ.

Đừng thấy Actuator `/actuator/startup` không có events trong một test `NEVER` rồi suy rằng production chưa ghi. Hai đường bootstrap có thể khác.

### 12.4. Events và listeners

Một bean `@EventListener` trong context thường được đăng ký trong quá trình context refresh; những sự kiện **rất sớm** (trước context/bean creation) có thể đã xảy ra. Nếu main dùng `app.addListeners(...)` để đăng ký early listener, `NEVER` bỏ qua listener đó. Với `ALWAYS`, test có thể quan sát side effect của listener nếu được thiết kế có marker an toàn. Không nên dùng static counter global chung mọi tests để kết luận chính xác số events do context caching/parallel tests.

## 13. @SpringBootTest.args, properties và active profiles

`@SpringBootTest` có thể truyền arguments/property để tùy chỉnh context, nhưng **không biến `NEVER` thành `ALWAYS`**.

### 13.1. Truyền args tới SpringApplication

Ví dụ **annotation snippet**:

~~~java
@SpringBootTest(
        classes = MainMethodLabApplication.class,
        useMainMethod = UseMainMethod.ALWAYS,
        args = "--lab.mode=integration",
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
~~~

Khi test đi qua main và main gọi `app.run(args)`, arguments do test bootstrap cung cấp có thể được sử dụng trong `Environment`/runners. Code `main` không được cố định `new String[0]` thay vì chuyển `args` nhận được, nếu cần giữ command-line behavior. Snippet này không phải test class hoàn chỉnh; lab chính không cần property `lab.mode`.

### 13.2. Properties không chứng minh main chạy

Nếu test viết:

~~~java
@SpringBootTest(
        properties = "spring.profiles.active=main-only")
~~~

thì test `NEVER` vẫn có thể bật profile main-only nhờ **chính annotation**. Khi đó một assert kiểm bean `@Profile` sẽ pass **mà không chứng minh main đã gọi `setAdditionalProfiles`**. Vì vậy lab dùng ba dấu hiệu độc lập và không đặt profile này trong `application.properties` hoặc test properties.

Tương tự, `@ActiveProfiles("main-only")` có thể tạo kết quả tương tự profile main. Trong test cần kiểm main, phải chọn dấu hiệu **không thể bị cấu hình trùng một cách vô tình**, ví dụ marker singleton chỉ được initializer ở main đăng ký.

### 13.3. Thứ tự ưu tiên thuộc tính

Command-line args, test property sources, environment variables và application properties có các mức ưu tiên khác nhau theo Spring Boot. Không đưa ra khẳng định “main luôn thắng test properties”: `setAdditionalProfiles` thêm profiles, còn `setDefaultProperties` mang tính default và có thể bị nguồn ưu tiên cao hơn override. Khi cần kiểm một property từ main, test cả giá trị cuối của `Environment` và nguồn cấu hình dự kiến, tránh chỉ assert constructor của `SpringApplication` được gọi.

## 14. Context caching và @DirtiesContext

Spring TestContext cache những application contexts có cấu hình tương đương để giảm chi phí chạy test suite. Hệ quả:

- `main()` (khi chọn useMainMethod có gọi main) thực thi khi context **được tạo**, không phải trước mỗi method.
- Nếu nhiều test methods dùng cùng cached context, setup trong main không nhất thiết được chạy lại.
- Nếu test thay đổi singleton state trong context, test sau có thể nhìn thấy trạng thái còn lại; nên tránh mutable shared state và dọn trong `@AfterEach` nếu cần.
- `@DirtiesContext` buộc context bị loại khỏi cache theo scope phù hợp; dùng khi thật sự cần một lượt startup/teardown mới, không lạm dụng để “fix” test flakiness.
- Khi có nhiều configurations/test properties/active profiles, test framework có thể tạo contexts riêng. Không thiết kế assertions lệ thuộc số contexts nếu không thực sự đang đo nó.
- Khi parallel tests cùng mở ports hoặc dùng một global resource, main side effects có thể gây tranh chấp, nhất là khi `webEnvironment=DEFINED_PORT`.

**Ví dụ không nên làm:**

~~~java
@Test
void assumesMainRunsBeforeEveryTestMethod() {
    // Không nên assert biến static mainInvocationCount == 1
    // cho từng test method khi ContextCache có thể tái sử dụng.
}
~~~

Snippet trên chỉ minh họa anti-pattern, không có trong project runnable. Điều đáng assert là **context có profile/initializer/recorder phù hợp**, không phải số lần method main đã được gọi.

## 15. Các side effects nguy hiểm khi test gọi main

Nếu main có những hành vi sau, cần xử lý trước khi bật `ALWAYS` trong CI:

| Hành vi main | Rủi ro khi chạy dưới JUnit | Hướng xử lý |
|---|---|---|
| `System.exit(...)` | Kết thúc cả JVM test runner | Refactor exit path, dùng subprocess cho exit-code test |
| `Runtime.halt(...)` | Bỏ qua shutdown hooks, giết JVM | Không chạy trong TestContext |
| Tạo thread/executor không đóng | Giữ JVM sống, test treo | Đặt owner bean, `@PreDestroy`/`SmartLifecycle` |
| Khởi động HTTP server trên fixed port | Đụng port khi tests parallel | Dùng `webEnvironment=NONE` hoặc RANDOM_PORT |
| Ghi file hoặc xóa dữ liệu | Phá môi trường dev/CI | Test-specific config, temp dir, fake storage |
| Chạm external DB/broker thật | Thay đổi dữ liệu, flakiness | Container test, fake, test environment |
| Gửi email/HTTP webhook thật | Side effects ngoài ý muốn | Stub/disable external integration |
| Thay `System.setProperty` global | Rò state sang test khác | Tránh global, cleanup trong finally |
| `System.setOut(...)` | Làm méo logging và test harness | Tránh sửa global streams |
| Đăng ký custom shutdown hooks | Hook chạy ngoài lifecycle test dự kiến | Tách owner, kiểm shutdown policy |
| Static mutable singletons | Trạng thái rò qua contexts/tests | Refactor vào beans hoặc reset có kiểm soát |
| Early `ApplicationListener` I/O nặng | Làm bootstrap chậm/treo | Handler nhẹ, instrumentation, deadlines |

**Quy tắc:** `useMainMethod=ALWAYS` không có sandbox OS tự động. Nó cho phép method main thực thi trong môi trường test. Nếu main gọi code phá hủy hoặc không thể hoàn tác, hãy refactor thành phương thức cấu hình SpringApplication có thể gọi an toàn, hoặc chạy ứng dụng thật trong **process riêng** với tài nguyên cô lập.

### 15.1. Refactor main để giảm rủi ro

Một thiết kế dễ kiểm có thể là:

~~~java
public static SpringApplication configuredApplication() {
    SpringApplication app =
            new SpringApplication(MyApplication.class);
    app.setAdditionalProfiles("custom");
    return app;
}

public static void main(String[] args) {
    configuredApplication().run(args);
}
~~~

Đây là **snippet** cần class `MyApplication`, imports và các config còn lại; không copy đè lab chính. Cách refactor cho phép unit test `configuredApplication()` (với API/phần trạng thái quan sát được) và một integration test `useMainMethod=ALWAYS` để xác nhận full bootstrap. Đừng dùng unit test của factory thay thế hoàn toàn test runtime nếu ứng dụng phụ thuộc vào effect khi `run(args)`.

### 15.2. Startup failure trong main

Nếu main throw exception trước khi gọi `run(args)`, `ALWAYS` sẽ làm test bootstrap fail. Đây có thể là behavior đúng nếu error thật. Test `NEVER` lại có thể load context thành công và che giấu lỗi này. Vì vậy nên có test đi qua main cho cấu hình cốt lõi.

Nếu main bắt exception rồi gọi `System.exit(0)`, test `ALWAYS` còn nguy hiểm hơn: JVM kết thúc với 0 và CI có thể báo misleading. Cần sửa error handling, không “chữa” bằng cách đổi useMainMethod sang NEVER rồi bỏ qua bug sản phẩm.

## 16. Phân biệt useMainMethod với những kiểu test lifecycle khác

### 16.1. @SpringBootTest không nhất thiết mở HTTP server

`@SpringBootTest.webEnvironment` có các mode phổ biến:

| Mode | Ý nghĩa | Phù hợp với demo main? |
|---|---|---|
| `MOCK` (mặc định) | Test web context mock nếu web framework trên classpath, không nhất thiết mở real port | Được, nhưng không cần web |
| `RANDOM_PORT` | Mở embedded server cổng ngẫu nhiên | Chỉ cần khi test HTTP thật |
| `DEFINED_PORT` | Mở server theo server.port, có thể đụng port | Tránh nếu chỉ đo profile/initializer |
| `NONE` | Không dùng web environment | **Được chọn trong lab** |

`webEnvironment` và `useMainMethod` trả lời **hai câu hỏi khác nhau**: context có mở web server không, và đường boot có dùng method main không. Không đặt RANDOM_PORT rồi cho rằng main đã được gọi.

### 16.2. Test lifecycle callbacks

Một test có `@SpringBootTest(useMainMethod=NEVER)` vẫn có thể kích hoạt:

- Bean construction/dependency injection.
- `@PostConstruct` / init callbacks.
- `SmartInitializingSingleton` của các singletons phù hợp.
- `SmartLifecycle.start()` khi context refresh và điều kiện autoStartup phù hợp.
- Context events, runner callbacks và SpringApplication lifecycle trong đường test startup.

Khác biệt là **các customization trong main bị bỏ qua**. Nếu câu hỏi là “SmartLifecycle có chạy khi refresh không”, test NEVER có thể phù hợp. Nếu câu hỏi là “SmartLifecycle có chạy sau profile/initializer được main thêm không”, nên chọn ALWAYS để đảm bảo đúng điều kiện.

### 16.3. ApplicationContextRunner khác @SpringBootTest

`ApplicationContextRunner` tạo context có kiểm soát rất hữu ích cho unit/auto-configuration tests. Nó **không tự chạy public static void main** của ứng dụng. Dùng nó để kiểm condition/property/bean logic, sau đó bổ sung ít nhất một `@SpringBootTest(useMainMethod=ALWAYS)` nếu production phải có những effect main-only.

### 16.4. Đừng gọi main thủ công trong @BeforeAll

Cách dưới đây **không** tương đương SpringBootTest useMainMethod:

~~~java
@BeforeAll
static void launch() {
    MainMethodLabApplication.main(new String[0]);
}
~~~

Đây là **snippet anti-pattern**; test context đã có thể được bootstrap riêng bởi Spring Test. Gọi main trong `@BeforeAll` có thể tạo **context thứ hai**, application runners chạy hai lần và leak executors/threads/ports. Chọn `useMainMethod=ALWAYS` thay vì tự tạo song song một app lifecycle không thuộc quyền sở hữu TestContext.

## 17. Ma trận QA cho chủ đề này

| Kịch bản | Chế độ | Kết quả mong đợi | Lỗi thiết kế sẽ lộ |
|---|---|---|---|
| Main có 3 customizations | NEVER | Không profile/marker main-only | Test mặc định bỏ qua main |
| Main có 3 customizations | ALWAYS | Profile, initializer marker và recorder có mặt | Main setup bị xóa/thay đổi |
| Main có 3 customizations | WHEN_AVAILABLE | Có mặt vì tìm thấy main | Có thể không fail nếu sau này mất main |
| Config không có main | WHEN_AVAILABLE | Boot test context bằng fallback | Không đòi entrypoint |
| Config không có main | ALWAYS (test âm) | Bootstrap fail | Contract yêu cầu main không được thỏa |
| Main gọi `System.exit` | ALWAYS | Không nên chạy trong cùng JVM JUnit | Cần subprocess |
| Test có `@ActiveProfiles("main-only")` | NEVER | Profile có thể active dù không gọi main | Assertion đơn lẻ tạo false-positive |
| Main thêm initializer nhưng test dùng NEVER | NEVER | Bean marker absent | Trôi cấu hình test so với production |
| Main thêm BufferingApplicationStartup | ALWAYS | Context recorder đúng type | Instrumentation cần cấu hình trước run |
| Nhiều methods cùng context | ALWAYS | Effects giữ nguyên, main không nhất thiết chạy lại | Assertions theo invocation count sai |
| App mở real server | ALWAYS + RANDOM_PORT | Server được test framework quản lý | Không dùng fixed port khi không cần |

**Nguyên tắc pass/fail:** Assert kết quả của **context đã được tạo** thay vì số log lines, số lần gọi main hoặc timing cụ thể của parallel test suite. Đối với việc phản chứng thiếu main, không giữ class `ALWAYS` cố tình fail trong test suite chính.

## 18. Chẩn đoán lỗi phổ biến

| Triệu chứng | Giả thuyết | Cách xác minh |
|---|---|---|
| Profile trong main không active khi @SpringBootTest | Default NEVER | Thêm `useMainMethod=ALWAYS`, assert Environment |
| Bean @Profile khác giữa dev và test | Main thêm profile/PropertySource | So setup main, @ActiveProfiles, test properties |
| @SpringBootTest PASS dù main đã bị xóa | NEVER hoặc WHEN_AVAILABLE fallback | Dùng ALWAYS cho hợp đồng main |
| ALWAYS fail “main method not found” | Configuration class không có main hợp lệ | Xác minh class `@SpringBootConfiguration` test đang dùng |
| WHEN_AVAILABLE vẫn load không có main | Behavior fallback đúng | Xem test NoMainFallbackTest |
| Test runner tự thoát | Main gọi System.exit/halt | Refactor, dùng subprocess |
| Hai ứng dụng xuất hiện trong logs | Test tự gọi main và framework cũng bootstrap | Bỏ manual invocation |
| Actuator startup khác runtime | Recorder chỉ gắn trong main nhưng test NEVER | Dùng ALWAYS hoặc test-specific instrumentation |
| Initializer marker không có trong ALWAYS | Code main bị thay, initializer không được đăng ký hoặc dùng sai config class | Kiểm `classes` và marker registration |
| ALWAYS có profile nhưng không marker | Profile bị bật từ nơi khác | Assert cả initializer marker và recorder |
| Test thấy marker dù NEVER | Đăng ký marker ở @Configuration khác hoặc global shared state | Đảm bảo marker duy nhất từ main |
| Test chậm bất thường | Main mở external services or runners | Test resources, fakes, deadlines |
| Port 8080 đang bận | Main/startup tạo server fixed port | NONE/RANDOM_PORT |
| Mỗi test method không in LAB_MAIN_ENTER | Context caching | Không assert main invocation count |
| @DirtiesContext làm test suite chậm | Ép reload contexts | Dùng khi cần cách ly mutable state |
| Test slice không nhận useMainMethod | Annotation không phải @SpringBootTest | Kiểm scope và dùng full integration test nếu cần |
| JDK thấp hơn 17 | Spring Boot 3.5 cần Java 17+ | Kiểm java/Maven JDK |
| Maven test fail vì không có dependencies | pom thiếu spring-boot-starter-test hoặc plugin | Kiểm Maven effective deps/build |
| Test kết quả khác trong CI | External environment/profile/global properties | Log active profiles, isolate config |
| Main dùng System.setProperty lâu dài | Global state leaks giữa tests | Refactor vào Environment/property sources |

## 19. Bài tập có tiêu chí kiểm chứng

### Bài tập A — Mặc định là NEVER

Chạy `DefaultNeverTest` và giải thích tại sao `main-only` không active, `registeredInMain` không tồn tại nhưng context vẫn load và JUnit vẫn chạy. Ghi rõ `NEVER` là **lựa chọn đường bootstrap**, không phải tắt Spring lifecycle.

### Bài tập B — Bắt buộc main

Chạy `AlwaysMainTest`. Quan sát `LAB_MAIN_ENTER` nếu console còn output; dùng assertions để xác nhận profile, bean profile, initializer marker và recorder. Bỏ tạm `app.setAdditionalProfiles(...)` trong bản copy rồi chạy test: assertion profile fail. Khôi phục code sau thí nghiệm.

### Bài tập C — Phản chứng bằng initializer

Trong bản copy, bỏ `app.addInitializers(...)`. `AlwaysMainTest` phải fail khi tìm `registeredInMain`, trong khi `DefaultNeverTest` vẫn pass. Điều này chứng minh test ALWAYS đang đo setup main-only thật, chứ không chỉ một property vô tình bật.

### Bài tập D — WHEN_AVAILABLE có main

Chạy `WhenAvailableMainTest`. Xác nhận profile/marker có mặt. Giải thích sự khác nhau về guarantee giữa WHEN_AVAILABLE và ALWAYS dù hiện tại chúng cùng tạo kết quả true.

### Bài tập E — WHEN_AVAILABLE không có main

Chạy `NoMainFallbackTest`. Sau đó trong bản copy thay `WHEN_AVAILABLE` thành `ALWAYS`; quan sát test bootstrap fail. Phục hồi để toàn suite xanh. Không phụ thuộc vào đúng message exception.

### Bài tập F — Context cache

Thêm test method thứ hai vào `AlwaysMainTest` để assert marker/recorder lần nữa. Giải thích tại sao phương thức main không bắt buộc phải được gọi hai lần. Không dùng static counter nếu test suite có parallelism hoặc cache.

### Bài tập G — Main chứa System.exit

Đọc một entrypoint thực tế có `System.exit(SpringApplication.exit(...))`. Giải thích vì sao không nên bật ALWAYS trong cùng JVM JUnit nếu chưa refactor. Thiết kế subprocess test `java -jar` và assert exit status, logs, cleanup.

### Bài tập H — Web server hoặc broker

Giả sử main khởi tạo profile để bật một listener container và addInitializer để thay resource URI. Chọn ALWAYS để test wiring đúng; dùng fake/Testcontainers cho dependency, ``webEnvironment=NONE` khi không cần HTTP, `RANDOM_PORT` khi cần verify HTTP. Đo SmartLifecycle running/teardown và không gọi main thủ công thêm lần nữa.

### Bài tập I — Tối ưu chính sách test

Phân loại test suite thành unit, slice, full-context NEVER, full-context ALWAYS và subprocess smoke tests. Chỉ bật ALWAYS cho nhóm thực sự muốn kiểm setup main, tránh mọi test context đều phải chạy side effects không cần thiết.

## 20. Checklist nghiệm thu

- [ ] Biết `@SpringBootTest.useMainMethod` và import `SpringBootTest.UseMainMethod`.
- [ ] Nêu đúng default `NEVER`.
- [ ] Giải thích `WHEN_AVAILABLE` fallback khi không có main.
- [ ] Giải thích `ALWAYS` fail-fast nếu không tìm thấy main.
- [ ] Biết profile/initializer/recorder có thể chỉ được setup trong main.
- [ ] Chạy được Maven Java 17 + Spring Boot 3.5 + JUnit Jupiter.
- [ ] `DefaultNeverTest` xác nhận profile không active, bean marker absent.
- [ ] `AlwaysMainTest` xác nhận profile, bean profile, initializer marker, Buffering recorder.
- [ ] `WhenAvailableMainTest` xác nhận main được dùng nếu có.
- [ ] `NoMainFallbackTest` xác nhận context vẫn load khi thiếu main.
- [ ] Không khai báo `spring.profiles.active=main-only` ngoài main trong lab.
- [ ] Không dùng `System.exit` trực tiếp trong test runner.
- [ ] Không gọi `main` thủ công từ `@Test` hoặc `@BeforeAll` để mở thêm context.
- [ ] Phân biệt `WebEnvironment.NONE` với việc có/không gọi main.
- [ ] Không suy từ số log lines ra số lần main chạy vì context cache.
- [ ] Hiểu ``@Profile` thay đổi bean graph trước bean lifecycle.
- [ ] Có cách kiểm proof context thay vì console-only.
- [ ] Biết khi nào nên dùng default NEVER cho unit/context wiring thay vì ALWAYS.
- [ ] Có subprocess test cho exit status/signal nếu entrypoint cần OS-level verification.
- [ ] Kiểm test resources/ports/globals trước khi chạy main trong CI.

## 21. Tài liệu chính thức

1. Spring Boot 3.5 — **Testing Spring Boot Applications, Using the Test Configuration Main Method**: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
2. Spring Boot 3.5 — **SpringBootTest.UseMainMethod API** (NEVER/WHEN_AVAILABLE/ALWAYS): https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/SpringBootTest.UseMainMethod.html
3. Spring Boot 3.5 — **SpringBootTest API** (`useMainMethod`, `args`, `properties`, `webEnvironment`): https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/SpringBootTest.html
4. Spring Boot 3.5 — **SpringApplication API** (`setAdditionalProfiles`, `addInitializers`, `setApplicationStartup`): https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/SpringApplication.html
5. Spring Boot 3.5 — **Application Startup** và `BufferingApplicationStartup`: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
6. Spring Framework 6.2 — **Testing, Context Caching**: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html
7. Spring Framework 6.2 — **ApplicationContextInitializer**: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/ApplicationContextInitializer.html
8. Spring Boot 3.5.16 phát hành chính thức: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now

**Tổng kết:** Khi một Spring Boot application có logic quan trọng trong `main`, test `@SpringBootTest` mặc định (`NEVER`) có thể tạo một context **không chứa** những thiết lập đó. `WHEN_AVAILABLE` chỉ phù hợp khi chấp nhận fallback; `ALWAYS` là lựa chọn đúng để test **bắt buộc** chạy main và phát hiện nếu main biến mất. Hãy assert **profile, initializer, bean graph và startup recorder thật** thay vì chỉ nhìn log. Với entrypoint gây side effects, `System.exit` hoặc gọi hệ điều hành, đừng cho JUnit chạy thẳng main; hãy tách cấu hình an toàn hoặc kiểm chứng qua subprocess với tài nguyên cô lập.