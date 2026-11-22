# @SpringBootTest và việc main không mặc nhiên được thực thi

## 1. Kết luận trọng tâm

Trong Spring Boot, một lớp thường vừa chứa cấu hình ứng dụng vừa chứa điểm vào Java:

~~~java
@SpringBootApplication
public class MyApplication {
    public static void main(String[] args) {
        SpringApplication.run(MyApplication.class, args);
    }
}
~~~

Đây là **đoạn minh họa**, chưa phải file Java đầy đủ vì thiếu imports. Khi chạy `java -jar` hoặc khởi chạy class bằng Java, JVM vào phương thức `public static void main(String[] args)`; method đó gọi `SpringApplication.run(...)` để tạo `ApplicationContext`.

Nhưng **`@SpringBootTest` không mặc nhiên gọi method `main` này**. Theo tài liệu Spring Boot 3.5.16, giá trị mặc định là:

~~~java
@SpringBootTest(useMainMethod = SpringBootTest.UseMainMethod.NEVER)
~~~

Đây là **cú pháp minh họa đặt trên test class**, tương đương hành vi mặc định của `@SpringBootTest`. Spring Boot Test dùng một `SpringApplication` do test loader tạo để khởi động `ApplicationContext` trực tiếp từ class cấu hình, **bỏ qua thân method `main`**.

Điều này **không có nghĩa ứng dụng không được khởi động trong test**. Spring vẫn:
- Tải cấu hình và auto-configuration thích hợp.
- Đăng ký/tạo bean trong context.
- Thực hiện dependency injection.
- Gọi `@PostConstruct` và các bean initialization callbacks.
- Tự khởi động `SmartLifecycle` thích hợp trong quá trình refresh.
- Gửi các application events của quá trình SpringApplication startup.
- Thực thi `ApplicationRunner` và `CommandLineRunner` được đăng ký khi bootstrap thành công.
- Cho test inject `ApplicationContext`, `Environment`, các service và repository.

**Điểm khác biệt là phần logic đặt bên ngoài `SpringApplication.run(...)` trong thân `main` không tự được thực thi**. Nếu method `main` cấu hình profile, banner, listener, default property hoặc thực hiện side effect khác trước `run(...)`, các thiết lập ấy có thể bị bỏ qua trong test mặc định.

## 2. Phân biệt JVM main, SpringApplication.run và ApplicationRunner

Ba khái niệm này nằm ở các tầng khác nhau:

| Thành phần | Ai gọi? | Chức năng | Có xảy ra trong @SpringBootTest mặc định? |
| --- | --- | --- | --- |
| Java `main(String[] args)` | Java launcher hoặc caller tường minh, khi test cấu hình dùng main | Điểm vào process và nơi ứng dụng tùy biến bootstrap | **Không** |
| `SpringApplication.run(...)` | Thường do main gọi; trong test do `SpringBootContextLoader`/test infrastructure gọi | Tạo, cấu hình, refresh context và hoàn thành Boot startup | **Có** |
| `ApplicationRunner.run(ApplicationArguments)` | Spring Boot trong đường `SpringApplication.run(...)` sau refresh | Công việc sau khi context bắt đầu | **Có**, nếu runner bean được tạo và startup thành công |
| `CommandLineRunner.run(String...)` | Spring Boot sau refresh | Công việc sau startup với raw arguments | **Có**, nếu bean tồn tại và startup thành công |
| `@PostConstruct` | Cơ chế bean initialization của Spring | Khởi tạo bean sau injection | **Có**, cho bean được tạo |
| `SmartLifecycle.start()` | Spring lifecycle processor trong refresh nếu auto-start | Bắt đầu component có lifecycle | **Có**, theo contract của bean |
| `@PreDestroy` | Cơ chế bean destruction khi context đóng | Dọn resource | Khi context bị hủy, không nhất thiết sau mỗi test method |

Điểm cần ghi nhớ:

~~~text
Chạy ứng dụng bình thường:
  JVM launcher
      -> MyApplication.main(args)
          -> SpringApplication.run(MyApplication.class, args)
              -> refresh ApplicationContext
              -> @PostConstruct / SmartLifecycle
              -> ApplicationRunner / CommandLineRunner
              -> ApplicationReadyEvent

@SpringBootTest mặc định:
  JUnit + Spring TestContext
      -> SpringBootContextLoader
          -> SpringApplication dùng cho test
              -> refresh ApplicationContext
              -> @PostConstruct / SmartLifecycle
              -> ApplicationRunner / CommandLineRunner
              -> ApplicationReadyEvent
          -> test method
  (KHÔNG tự đi qua MyApplication.main)
~~~

Đây là sơ đồ cơ chế chung; thứ tự giữa những bean khác nhau, runner được sắp theo `@Order`/`Ordered` và loại web environment còn phụ thuộc cấu hình. Nó không phải trace nội bộ từng method của một phiên bản framework cụ thể.

### Tại sao runner vẫn được gọi mà main lại không?

`ApplicationRunner` là **bean của Spring**. Khi `SpringApplication.run(...)` chạy, Spring Boot gọi runner sau khi refresh context. Test loader vẫn khởi tạo context thông qua SpringApplication, nên runner vẫn được thực thi.

`main` lại là **một Java static method**, không phải lifecycle hook của Spring bean. Việc một class có `@SpringBootApplication` chỉ giúp Spring nhận diện nguồn cấu hình; annotation đó không khiến Spring tự tìm và chạy mọi static method tên `main`.

Nếu ứng dụng cần tránh gửi email, gọi remote API hoặc chỉnh database khi chạy integration test, **không thể chỉ dựa vào việc main bị bỏ qua**: nếu side effect nằm trong `ApplicationRunner`, `CommandLineRunner`, `@PostConstruct`, `SmartLifecycle` hoặc event listener thì test vẫn có thể chạy chúng.

## 3. Ba giá trị của useMainMethod

Spring Boot 3.5 cung cấp `org.springframework.boot.test.context.SpringBootTest.UseMainMethod`:

| Giá trị | Quy tắc | Nếu không tìm thấy main | Khi nên dùng |
| --- | --- | --- | --- |
| `NEVER` | Không gọi main; tạo SpringApplication của test | Vẫn có thể bootstrap từ configuration class | Mặc định; kiểm thử context độc lập với entry point |
| `WHEN_AVAILABLE` | Có main thì sử dụng; không có thì dùng test loader thông thường | **Fallback**, không fail chỉ vì thiếu main | Test có nhiều kiểu cấu hình, muốn tận dụng main khi có |
| `ALWAYS` | Bắt buộc sử dụng main để tạo context | **Fail** nếu không có configuration/main phù hợp | Kiểm tra cấu hình bootstrap mà production thật dùng |

Annotation mặc định tương đương:

~~~java
@SpringBootTest(useMainMethod = UseMainMethod.NEVER)
~~~

Muốn yêu cầu test dùng main:

~~~java
@SpringBootTest(useMainMethod = UseMainMethod.ALWAYS)
~~~

Muốn dùng main khi tồn tại nhưng không ép mọi configuration có method này:

~~~java
@SpringBootTest(useMainMethod = UseMainMethod.WHEN_AVAILABLE)
~~~

Ba dòng là **minh họa annotation**, cần import `SpringBootTest` và `UseMainMethod`, rồi đặt trên một JUnit test class thực tế.

### ALWAYS không phải “fork một JVM mới”

Khi `ALWAYS` được chọn, Spring Boot TestContext gọi method main phù hợp trong **JVM của test runner** để tạo SpringApplication/context. Điều đó khác việc khởi chạy một process mới bằng `java -jar`. Vì vậy:
- Mọi `System.setProperty` từ main có thể ảnh hưởng toàn bộ JVM test, kể cả test khác.
- `System.exit(...)` trong main có thể kết thúc cả test process; rất nguy hiểm.
- Thread, hook hoặc file được main tạo ngoài container có thể rò giữa tests.
- Maven/Gradle test runner vẫn quản lý thứ tự test, context caching và shutdown.
- `ALWAYS` không mặc nhiên kiểm chứng OS process exit code, command-line packaging hay launch scripts.

Nếu cần test một lỗi ở tầng **process entry point**, hãy dùng subprocess có timeout và kiểm tra exit code riêng; đừng biến test chạy trong JVM thành một `System.exit` thực.

### WHEN_AVAILABLE không tự bảo đảm main đã chạy

Nếu cấu hình tìm thấy method main phù hợp, `WHEN_AVAILABLE` sẽ dùng nó; nếu không, Spring Boot fallback. Vì vậy test chạy PASS trong chế độ WHEN_AVAILABLE **không tự chứng minh main luôn được gọi** trên mọi module hoặc sau refactor. Nếu mục tiêu của test là bắt buộc xác nhận chính entry point, hãy dùng `ALWAYS` và assertion lên cấu hình/hành vi phát sinh từ main.

## 4. Hành vi mặc định được xác định từ đâu?

`@SpringBootTest` mở rộng cách dùng Spring TestContext Framework. Trong Spring Boot 3.5.16:

- Bootstrapper: `SpringBootTestContextBootstrapper`.
- Context loader mặc định: `SpringBootContextLoader`.
- Nguồn cấu hình: explicit `classes`, nested `@Configuration` hoặc cơ chế tìm kiếm `@SpringBootConfiguration`.
- `useMainMethod()` có default là `UseMainMethod.NEVER`.
- `webEnvironment()` có default là `WebEnvironment.MOCK`.
- `args()` cho phép truyền application arguments vào đường SpringApplication dùng trong test.
- `properties()`/`value()` cho phép thêm properties vào test Environment.

**Ý nghĩa:** mặc định, test dùng một class có `@SpringBootApplication` làm **configuration source**, chứ không phải tự gọi entrypoint method `main` của class đó.

### Cơ chế tìm lớp cấu hình

Spring Boot test thường tìm từ package của test đi lên để gặp một lớp được annotate `@SpringBootApplication` hoặc `@SpringBootConfiguration`. Với project chuẩn, app class nằm trong root package và test nằm trong cùng package hoặc package con, nên tìm thấy cấu hình đúng.

Ví dụ cây package:

~~~text
src/main/java/com/example/lesson/MainMethodLifecycleApplication.java
src/test/java/com/example/lesson/MainDefaultTest.java
src/test/java/com/example/lesson/MainAlwaysTest.java
~~~

Đặt test ngoài cây package của application có thể khiến framework không tìm được `@SpringBootConfiguration`, dù method main thực sự tồn tại ở nơi khác. Trong trường hợp đó, dùng `@SpringBootTest(classes = MainMethodLifecycleApplication.class)` để chỉ rõ nguồn cấu hình, thay vì cố gọi main thủ công từ test.

### classes chỉ định nguồn cấu hình, không bắt buộc chạy main

Câu lệnh:

~~~java
@SpringBootTest(classes = MainMethodLifecycleApplication.class)
~~~

**không có nghĩa** method `MainMethodLifecycleApplication.main(...)` sẽ được gọi. Nó chọn class để nạp configuration. Chỉ `useMainMethod` (khi hỗ trợ) mới thay đổi chính sách gọi main.

### main đơn thuần delegate thì khác biệt ít được nhìn thấy

Nếu main chỉ có:

~~~java
public static void main(String[] args) {
    SpringApplication.run(MyApplication.class, args);
}
~~~

thì test mặc định và test dùng ALWAYS có thể tạo ra các context tương đương về bean graph, dù đường vào khác nhau. Sự khác biệt lộ rõ khi **main có tùy biến ngoài lời gọi SpringApplication.run**.

## 5. Những tùy biến trong main dễ bị mất khi test không gọi main

### 5.1. SetAdditionalProfiles

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setAdditionalProfiles("from-main");
app.run(args);
~~~

Nếu test dùng `NEVER`, profile do main bổ sung **không tự active**. Một bean có `@Profile("from-main")` có thể không tồn tại trong test mặc định dù chạy production có. Với `ALWAYS`, main được dùng và profile đó có cơ hội được áp dụng.

Đây là ví dụ minh họa trong method main, không độc lập. Với test muốn profile rõ ràng, cũng có thể dùng `@ActiveProfiles("...")`; quyết định cần phụ thuộc bạn muốn kiểm thử **bootstrap production thật** hay tạo môi trường test độc lập.

### 5.2. Default properties

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setDefaultProperties(Map.of("lesson.main.origin", "from-main"));
app.run(args);
~~~

Property nguồn default này chỉ được thiết lập khi code đi qua main. `@SpringBootTest` mặc định không biết nó trừ khi cùng cấu hình được cung cấp qua con đường khác. Test có thể thêm `@SpringBootTest(properties = "...")` hoặc `@TestPropertySource`, nhưng điều đó **không chứng minh main đã được thực thi**.

Đây là đoạn minh họa, cần import `java.util.Map` và Spring Boot. Default properties có **độ ưu tiên thấp** hơn nhiều property sources khác; nếu test hoặc environment override key, giá trị có thể khác.

### 5.3. Banner, logging và SpringApplication settings

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setBannerMode(Banner.Mode.OFF);
app.setLogStartupInfo(false);
app.run(args);
~~~

Nếu main bị bỏ qua, các thiết lập do method này làm có thể khác trong test. Không nhất thiết gây lỗi assertion, nhưng có thể tạo chênh lệch cấu hình giữa production và test.

Đây là minh họa, cần import `org.springframework.boot.Banner` và `SpringApplication`.

### 5.4. Listeners và initializers

Nếu main tạo `SpringApplication` rồi đăng ký:
- `ApplicationListener` cho startup events,
- `ApplicationContextInitializer`,
- nguồn cấu hình bổ sung,
- xử lý arguments hoặc profiles,
- cài đặt lazy initialization/web application type,

thì test dùng `NEVER` có thể không nhận cùng customization. Khi muốn test đó có mặt, sử dụng `ALWAYS` hoặc đưa customization sang một hook/config được Spring Boot TestContext tải theo hợp đồng (đặc biệt nếu nhiều loại context cần dùng).

### 5.5. Side effects ngoài Spring

Một method main có thể:
- Ghi file, đổi `System.setProperty`.
- Mở một socket/connection bằng code thủ công.
- Đăng ký một JVM shutdown hook.
- Gọi external service trước khi context được tạo.
- Gọi `System.exit`.
- Thay đổi JVM-global state.

Test mặc định bỏ qua thân main nên có thể **không kích hoạt** các side effect ấy. Nếu bật `ALWAYS`, chúng có thể xảy ra **ngay trong test process**. Đây là lý do cần cân nhắc kỹ trước khi bật ALWAYS cho toàn bộ suite.

## 6. Điều không bị bỏ qua: Spring bean lifecycle vẫn chạy

Đừng hiểu “main không chạy” thành “test không đi qua lifecycle”:

~~~text
@SpringBootTest mặc định
    |
    +-- TestContext tạo SpringApplication
    +-- Environment / auto-configuration
    +-- ApplicationContext.refresh()
    |      +-- BeanDefinition / singleton creation
    |      +-- @PostConstruct / init callbacks
    |      +-- SmartLifecycle auto-start (khi áp dụng)
    |      +-- ContextRefreshedEvent
    |
    +-- ApplicationStartedEvent
    +-- LivenessState.CORRECT trong đường Boot chuẩn
    +-- ApplicationRunner / CommandLineRunner
    +-- ApplicationReadyEvent
    +-- ReadinessState.ACCEPTING_TRAFFIC trong đường Boot chuẩn
    |
    +-- JUnit @Test methods
~~~

Đây là thứ tự khái quát cho một `SpringApplication` khởi động thành công; có thể khác theo version/customizations. `@SpringBootTest` cũng có thể dùng webEnvironment không mở socket thật, nên `ApplicationReadyEvent` của một **test context** không đồng nghĩa một pod production đang nhận traffic.

### @PostConstruct và @PreDestroy

`@PostConstruct` gắn với lúc bean được tạo; dù main không chạy, test context vẫn tạo bean, nên callback có thể chạy. `@PreDestroy` gắn với lúc bean bị destroy; không được giả định nó chạy **sau từng @Test method** vì Spring TestContext có **context caching**.

### ApplicationRunner và CommandLineRunner

Hai loại runner chạy khi SpringApplication hoàn tất bootstrap của context. Vì thế chúng có thể:
- Seed dữ liệu.
- Gửi message.
- Gọi API.
- Chạy job.
- Thay đổi database.

Những side effect đó **có thể xảy ra trong @SpringBootTest mặc định**, ngay cả khi main không được gọi. Nếu không phù hợp cho test, nên guard bằng profile/property hoặc thay thế dependency, dùng test-specific configuration và thiết kế idempotent. Không đặt việc nguy hiểm trong runner rồi chỉ dựa vào việc main không chạy.

### SmartLifecycle

Một bean SmartLifecycle có `isAutoStartup()==true` có thể khởi động trong refresh. Nó cần stop/cleanup khi test context bị đóng, không được tưởng toàn bộ worker đã dừng khi một test method trả về. Nếu test đo lifecycle, phải nắm rõ context scope/cache và điều khiển trạng thái trong phạm vi test phù hợp.

## 7. Demo hoàn chỉnh: Java 17+, Spring Boot 3.5.16, JUnit 5

Ta xây dựng project Maven minh họa **bốn** loại test:

1. `MainDefaultTest`: `@SpringBootTest` không nêu useMainMethod; chứng minh default không gọi main.
2. `MainAlwaysTest`: `useMainMethod=ALWAYS`; chứng minh main configuration được áp dụng.
3. `MainWhenAvailableTest`: `useMainMethod=WHEN_AVAILABLE`; main có mặt nên được dùng.
4. `MainArgumentsTest`: không gọi main nhưng vẫn chuyển `args` cho SpringApplication và nhận chúng trong `Environment`.

Ứng dụng có:
- Method main đặt `lesson.main.origin=from-main` thông qua `SpringApplication.setDefaultProperties`.
- Method main thêm profile `from-main` qua `setAdditionalProfiles`.
- Một bean `StartupState` có `@PostConstruct` / `@PreDestroy`.
- Một bean `ApplicationRunner` tăng số lần runner chạy trên **mỗi context**.

Không có network server hay external database. Các test assertions là bằng chứng mạnh hơn việc đếm log của nhiều class khi context cache có thể được dùng lại.

### 7.1. Cấu trúc thư mục

~~~text
main-method-test-demo/
├── pom.xml
├── src/
│   ├── main/
│   │   └── java/com/example/mainmethod/
│   │       └── MainMethodLifecycleApplication.java
│   └── test/
│       └── java/com/example/mainmethod/
│           ├── MainDefaultTest.java
│           ├── MainAlwaysTest.java
│           ├── MainWhenAvailableTest.java
│           └── MainArgumentsTest.java
~~~

Tên package trong cả năm file Java là `com.example.mainmethod`. Các file test có hậu tố `Test` để Maven Surefire nhận diện. Không có cấu hình YAML hoặc mock đặc biệt cần bổ sung.

### 7.2. pom.xml đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>main-method-test-demo</artifactId>
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

`spring-boot-starter-test` cấp JUnit Jupiter cùng Spring Boot TestContext cho scope test. `spring-boot-starter` đủ chạy CLI không-web. Không cần thêm `spring-boot-starter-web`, tránh mở port và giảm nhiễu lifecycle.

### 7.3. MainMethodLifecycleApplication.java

Tệp `src/main/java/com/example/mainmethod/MainMethodLifecycleApplication.java`:

~~~java
package com.example.mainmethod;

import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class MainMethodLifecycleApplication {

    public static void main(String[] args) {
        System.out.println("MAIN_METHOD_INVOKED");

        SpringApplication application =
                new SpringApplication(MainMethodLifecycleApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setAdditionalProfiles("from-main");
        application.setDefaultProperties(
                Map.of("lesson.main.origin", "from-main"));
        application.run(args);
    }

    @Bean
    StartupState startupState() {
        return new StartupState();
    }

    @Bean
    ApplicationRunner demoRunner(StartupState state) {
        return args -> {
            state.markRunner();
            System.out.println(
                    "APPLICATION_RUNNER_INVOKED count="
                            + state.runnerCalls());
        };
    }

    public static final class StartupState {
        private final AtomicInteger runnerCount = new AtomicInteger();

        @PostConstruct
        public void initialized() {
            System.out.println("BEAN_POST_CONSTRUCT");
        }

        void markRunner() {
            runnerCount.incrementAndGet();
        }

        public int runnerCalls() {
            return runnerCount.get();
        }

        @PreDestroy
        public void destroyed() {
            System.out.println("BEAN_PRE_DESTROY");
        }
    }
}
~~~

Đây là một file Java **đầy đủ** trong project, không có method giả/placeholder. Các dấu hiệu có ý nghĩa:

- `MAIN_METHOD_INVOKED`: in **chỉ khi method main được gọi**.
- `lesson.main.origin`: property được thiết lập chỉ trong thân main.
- Profile `from-main`: chỉ được bổ sung bởi lời gọi `setAdditionalProfiles` bên trong main.
- `BEAN_POST_CONSTRUCT`: in khi Spring tạo bean StartupState, **không phụ thuộc main có được gọi hay không**.
- `APPLICATION_RUNNER_INVOKED count=1`: in khi Boot chạy ApplicationRunner cho context mới.
- `BEAN_PRE_DESTROY`: in lúc Spring destroy bean, có thể **sau khi test cuối cùng kết thúc**, không phải nhất thiết ngay sau mỗi method.

`StartupState.runnerCalls()` đếm trên một bean **thuộc từng context**, không phải một biến static toàn JVM. Điều đó làm assertion ổn định hơn trong điều kiện Spring TestContext cache/reuse context. Nếu có customization khởi tạo thêm context, mỗi context có counter của riêng nó.

### 7.4. Test 1 — MainDefaultTest.java

Tệp `src/test/java/com/example/mainmethod/MainDefaultTest.java`:

~~~java
package com.example.mainmethod;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;

import com.example.mainmethod.MainMethodLifecycleApplication.StartupState;

@SpringBootTest(
        classes = MainMethodLifecycleApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class MainDefaultTest {

    @Autowired
    Environment environment;

    @Autowired
    StartupState state;

    @Test
    void contextStartsWithoutCallingJavaMain() {
        assertNull(environment.getProperty("lesson.main.origin"));
        assertFalse(environment.acceptsProfiles(Profiles.of("from-main")));
        assertEquals(1, state.runnerCalls());
    }
}
~~~

**Giải thích assertion:**
- Không có `useMainMethod`, vì default là `NEVER`.
- `lesson.main.origin` không được thiết lập bởi main → `assertNull` trong môi trường của demo.
- `from-main` không tự active.
- Nhưng `ApplicationRunner` **đã chạy**, nên `runnerCalls()==1`.

Đây chính là khác biệt trung tâm giữa **“không gọi main”** và **“không khởi động Spring application”**. Test vẫn chạy một application context thực.

Lưu ý test này giả định không có một property source/profile bên ngoài khác cố tình đặt `lesson.main.origin` hay `from-main`. Trong môi trường học tập sạch như project trên, assertion xác định. Khi tích hợp vào project hiện hữu có CI profiles riêng, dùng marker thuộc namespace test độc lập hoặc kiểm soát source cấu hình để tránh collision.

### 7.5. Test 2 — MainAlwaysTest.java

Tệp `src/test/java/com/example/mainmethod/MainAlwaysTest.java`:

~~~java
package com.example.mainmethod;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.UseMainMethod;
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;

import com.example.mainmethod.MainMethodLifecycleApplication.StartupState;

@SpringBootTest(
        classes = MainMethodLifecycleApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        useMainMethod = UseMainMethod.ALWAYS)
class MainAlwaysTest {

    @Autowired
    Environment environment;

    @Autowired
    StartupState state;

    @Test
    void mainCustomizationsBecomeVisibleToTestContext() {
        assertEquals("from-main",
                environment.getProperty("lesson.main.origin"));
        assertTrue(environment.acceptsProfiles(Profiles.of("from-main")));
        assertEquals(1, state.runnerCalls());
    }
}
~~~

**Giải thích:** `ALWAYS` yêu cầu TestContext dùng `MainMethodLifecycleApplication.main(...)`. Main tạo SpringApplication, đặt property/profile và gọi run, nên trong context test các tùy biến được nhìn thấy. Runner vẫn chạy như bình thường.

Đây là kiểm thử **cấu hình launcher của ứng dụng**, không phải chỉ kiểm tra một service. Chỉ nên dùng ALWAYS nếu main được viết an toàn cho môi trường test và không gọi System.exit hoặc side effects không mong muốn.

### 7.6. Test 3 — MainWhenAvailableTest.java

Tệp `src/test/java/com/example/mainmethod/MainWhenAvailableTest.java`:

~~~java
package com.example.mainmethod;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.UseMainMethod;
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;

import com.example.mainmethod.MainMethodLifecycleApplication.StartupState;

@SpringBootTest(
        classes = MainMethodLifecycleApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        useMainMethod = UseMainMethod.WHEN_AVAILABLE)
class MainWhenAvailableTest {

    @Autowired
    Environment environment;

    @Autowired
    StartupState state;

    @Test
    void usesMainBecauseThisApplicationHasOne() {
        assertEquals("from-main",
                environment.getProperty("lesson.main.origin"));
        assertTrue(environment.acceptsProfiles(Profiles.of("from-main")));
        assertEquals(1, state.runnerCalls());
    }
}
~~~

Trong project này, cấu hình có method main nên `WHEN_AVAILABLE` đi qua main, giống ALWAYS về kết quả marker. Nếu sau này đổi configuration sang class không có main, `WHEN_AVAILABLE` sẽ fallback thay vì fail.

Đừng dùng `WHEN_AVAILABLE` khi chính test có mục đích bắt lỗi “entry point bị xóa ngoài ý muốn”; dùng `ALWAYS` cho mục đích đó.

### 7.7. Test 4 — MainArgumentsTest.java

Tệp `src/test/java/com/example/mainmethod/MainArgumentsTest.java`:

~~~java
package com.example.mainmethod;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;

import com.example.mainmethod.MainMethodLifecycleApplication.StartupState;

@SpringBootTest(
        classes = MainMethodLifecycleApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        args = "--lesson.cli.marker=passed-by-test-loader")
class MainArgumentsTest {

    @Autowired
    Environment environment;

    @Autowired
    StartupState state;

    @Test
    void appArgsWorkEvenThoughMainWasNotInvoked() {
        assertNull(environment.getProperty("lesson.main.origin"));
        assertEquals("passed-by-test-loader",
                environment.getProperty("lesson.cli.marker"));
        assertEquals(1, state.runnerCalls());
    }
}
~~~

`@SpringBootTest.args` chuyển application arguments cho SpringApplication dùng trong test. Nó **không có nghĩa main được gọi**. Test này cho thấy property từ CLI argument được tạo bởi test loader, trong khi property chỉ được set trong main vẫn vắng mặt.

Cần phân biệt:
- `args`: chuyển application arguments vào bootstrap.
- `properties`: thêm key=value vào Environment test.
- `useMainMethod`: chọn có gọi Java main để tạo SpringApplication hay không.

Ba khả năng độc lập về mục đích.

## 8. Chạy demo và kiểm chứng kết quả

Yêu cầu: JDK 17+, Maven có thể tải dependencies, không có các property/profile bên ngoài cố tình dùng namespace `lesson.main.*`.

Từ thư mục project:

~~~bash
mvn test
~~~

Maven Surefire (được Spring Boot parent quản lý) sẽ thực hiện các test class có hậu tố `Test`. Mỗi test có một method JUnit 5.

**Các kết quả assertion mong đợi:**

| Test | useMainMethod | Property `lesson.main.origin` | Profile `from-main` | Runner calls/context |
| --- | --- | --- | --- | --- |
| MainDefaultTest | NEVER (mặc định) | null | false | 1 |
| MainAlwaysTest | ALWAYS | from-main | true | 1 |
| MainWhenAvailableTest | WHEN_AVAILABLE | from-main | true | 1 |
| MainArgumentsTest | NEVER (mặc định) | null | false nếu không có cấu hình khác | 1; CLI marker có giá trị |

Một project sạch có bốn test methods và kỳ vọng **4 test PASS**, không có failure/error. Maven output còn chứa timestamps, logging framework, test class names và context caching nên **không có một stdout tổng thể cố định** cho toàn `mvn test`.

### Các marker log nào xuất hiện?

Khi một context mới của test được tạo:
- Với `NEVER`: `BEAN_POST_CONSTRUCT` và `APPLICATION_RUNNER_INVOKED count=1`; **không có `MAIN_METHOD_INVOKED` do chính context này**.
- Với `ALWAYS`: `MAIN_METHOD_INVOKED`, sau đó `BEAN_POST_CONSTRUCT` và `APPLICATION_RUNNER_INVOKED count=1`.
- Với `WHEN_AVAILABLE` và có main: tương tự ALWAYS.
- `BEAN_PRE_DESTROY`: có thể xuất hiện khi test context cache được dọn, khi context bị eviction hoặc framework kết thúc; **không gắn cứng với từng test method**.

**Không đếm `MAIN_METHOD_INVOKED` trên toàn log suite rồi suy ra thứ tự test**, vì JUnit có thể chạy test theo thứ tự khác, Spring TestContext có thể cache/reuse context, và test khác có thể nạp một configuration tương tự. Hãy dựa vào assertion trên **Environment của context đang kiểm thử**.

### Chạy một test class riêng để quan sát dễ hơn

~~~bash
mvn -Dtest=MainDefaultTest test
mvn -Dtest=MainAlwaysTest test
mvn -Dtest=MainWhenAvailableTest test
mvn -Dtest=MainArgumentsTest test
~~~

Mỗi command khởi động một Maven test invocation riêng. Nếu chỉ chạy default test trong một JVM thử nghiệm sạch, không có marker `MAIN_METHOD_INVOKED` từ ứng dụng, nhưng vẫn có marker của `ApplicationRunner`.

### Chạy application bình thường

Biên dịch/đóng gói:

~~~bash
mvn package
java -jar target/main-method-test-demo-0.0.1-SNAPSHOT.jar
~~~

Khi chạy bằng Java launcher, `main` thực sự là entry point. Các marker do mã ứng dụng tự in theo thứ tự trong một run thành công:

~~~text
MAIN_METHOD_INVOKED
BEAN_POST_CONSTRUCT
APPLICATION_RUNNER_INVOKED count=1
~~~

Các log/banner Spring Boot có thể xen giữa. Vì đây là ứng dụng không-web, khi main kết thúc và không còn non-daemon thread khác, JVM có thể kết thúc tự nhiên; shutdown hook đóng context và khi đó `BEAN_PRE_DESTROY` có thể xuất hiện. **Không dùng thời điểm xuất hiện @PreDestroy trong log làm bằng chứng một test method cụ thể đã đóng context.**

### Nếu output hoặc assertions không đúng

Kiểm tra:
1. Có thật đang dùng Spring Boot 3.5.16 hoặc version có `useMainMethod` không?
2. Các test file có nằm đúng `src/test/java` và đúng package không?
3. Test có bị một `@SpringBootTest(properties=...)`/`@ActiveProfiles` khác hoặc biến môi trường override không?
4. `classes` có đúng class `@SpringBootApplication` chứa method main không?
5. Main có gọi **một** `SpringApplication.run` để tạo context không?
6. Một runner khác trong project có ném exception làm startup fail trước test method không?
7. Maven có vô tình skip tests hoặc chạy thêm test bị lỗi không?
8. Có dùng JUnit 4 annotation hay test runner không phù hợp trong một project đã chuyển sang JUnit Jupiter không?

## 9. Khi nào nên dùng NEVER, ALWAYS, WHEN_AVAILABLE?

### NEVER (mặc định) — kiểm thử cấu hình ứng dụng và bean graph

Phù hợp với:
- Integration test service/repository cần full Spring context.
- Test cần bootstrap ứng dụng nhưng **không** muốn code orchestration ngoài Spring ở main.
- Test muốn kiểm soát profile/properties riêng thông qua annotations.
- Test không cần kiểm tra banner, listeners và settings do main tự tạo.

Ưu điểm: giảm phụ thuộc vào entrypoint và tránh side effects ngoài Spring do main trực tiếp tạo.

Rủi ro: nếu production main chứa tùy biến quan trọng mà test không tái tạo, test có thể **PASS trong môi trường khác production**. Đây là false confidence, không phải lỗi của TestContext.

### ALWAYS — test đường bootstrap thật từ main

Phù hợp khi:
- Main tạo `new SpringApplication(...)` và đặt additional profiles, banner, initializers, listeners.
- Cần kiểm tra startup configuration của entrypoint có ảnh hưởng tới bean graph.
- Muốn fail ngay nếu class cấu hình không có main method.
- Cần một nhóm integration tests dành riêng cho “launcher parity”.

Rủi ro: side effects của main xảy ra trong process test. Không dùng khi main gọi System.exit, khởi tạo process ngoài, thay đổi static/global state không được dọn hoặc thực hiện việc phá hủy dữ liệu.

### WHEN_AVAILABLE — linh hoạt khi nhiều configuration

Phù hợp với:
- Bộ test chạy trên nhiều application configuration, có module có main và module không có.
- Muốn dùng main của một application nếu có nhưng không bắt buộc mọi test source cung cấp main.
- Có thể chấp nhận rằng một refactor xóa main sẽ khiến test chuyển sang fallback.

Rủi ro: test PASS không chứng minh rằng đường main luôn tồn tại; dùng ALWAYS nếu đây là invariant cần kiểm soát.

### Khuyến nghị thực hành

Phần lớn integration tests có thể dùng mặc định. Bổ sung một số test `ALWAYS` có mục đích cụ thể nếu main chứa customization quan trọng. Tốt hơn nữa, với cấu hình được **cả runtime lẫn test** cần, hãy chuyển phần đó thành bean, `@Configuration`, `ApplicationContextInitializer` hoặc cơ chế Spring Boot configuration có thể kiểm thử riêng—thay vì đặt hàng chục side effects trong method main.

## 10. ApplicationRunner vẫn chạy: rủi ro quan trọng khi kiểm thử vòng đời

Có những ứng dụng đặt job logic trong runner:

~~~java
@Bean
ApplicationRunner sendWelcomeEmails(MailSender sender) {
    return args -> sender.sendWelcomeEmails();
}
~~~

Đây là **đoạn minh họa không độc lập**; `MailSender` và method là kiểu/logic giả định. Trong `@SpringBootTest` mặc định, SpringApplication vẫn có thể tạo bean runner và **thực thi nó**, dù Java main không được gọi.

Nếu code gửi email thật, gọi payment API hoặc publish Kafka, test integration có thể gây side effects ngoài ý muốn.

### Cách thiết kế an toàn

1. Đưa nghiệp vụ vào service riêng, runner chỉ gọi service.
2. Dùng profile hoặc property để quyết định khi nào runner được đăng ký.
3. Trong test, override property hoặc thay thế external dependency bằng test double.
4. Giữ mã job idempotent: nếu startup/retry lặp, không gửi duplicate hoặc sửa dữ liệu sai.
5. Thực hiện integration test riêng để xác minh chính runner theo môi trường an toàn.
6. Không dùng `System.exit` trong runner để “kết thúc test”, vì có thể giết cả test JVM.

Một ví dụ guard bằng property:

~~~java
@Bean
@ConditionalOnProperty(
        prefix = "jobs",
        name = "send-welcome-emails",
        havingValue = "true")
ApplicationRunner sendWelcomeEmails(MailSender sender) {
    return args -> sender.sendWelcomeEmails();
}
~~~

Đây là snippet minh họa. Nếu production cần bật job, phải cấu hình property tường minh; test không cấu hình thì job không chạy. Nhưng cũng cần test chuyên biệt để bảo đảm job bật khi cần. Không tùy tiện chuyển công việc quan trọng sang false mặc định mà không cập nhật yêu cầu sản phẩm.

## 11. @PostConstruct, SmartLifecycle và ApplicationReadyEvent trong test

Dù main không chạy, TestContext khởi động một Spring application thực. Những điểm mở rộng vòng đời có thể chạy:

### @PostConstruct

Là callback được gọi khi Spring khởi tạo bean sau dependency injection. Một bean singleton được tạo trong test context vẫn nhận callback này.

Nếu @PostConstruct mở kết nối hoặc tạo file, cần có `@PreDestroy` hoặc đường cleanup tương ứng. Đừng đặt các side effects không an toàn ở đây rồi cho rằng test mặc định bỏ qua vì main không chạy.

### SmartLifecycle

`SmartLifecycle.isAutoStartup()` thường là true. `DefaultLifecycleProcessor` có thể gọi `start()` trong context refresh. Test nên:
- Biết worker có được auto-start không.
- Dùng profile/property/test config để tắt worker không liên quan.
- Không tự đóng shared bean khi test method kết thúc nếu context còn được cache.
- Xác nhận callback `stop(Runnable)` hoàn tất đúng khi test context bị destroy.

### Application events

Trong một Boot startup thành công, các event như `ApplicationStartedEvent` và `ApplicationReadyEvent` vẫn có thể được phát, dù Java main không chạy. Vì chúng được tạo bởi `SpringApplication.run`, không phải là lệnh do body của main bắt buộc viết thủ công.

Nếu test muốn xác minh event listener, có thể dùng Spring TestContext event recording hoặc listener/test bean cụ thể. Đừng suy rằng không có `ApplicationReadyEvent` chỉ vì có `UseMainMethod.NEVER`.

### ApplicationContext và WebEnvironment

`@SpringBootTest` mặc định có `webEnvironment=MOCK`. Nếu có servlet web libraries, điều này thường tạo mock web environment mà **không mở server thực trên port TCP**.

Các giá trị:
- `MOCK`: mock web application context thích hợp, không nhất thiết mở embedded server.
- `RANDOM_PORT`: embedded server dùng port ngẫu nhiên, phù hợp HTTP integration test.
- `DEFINED_PORT`: server trên port cấu hình hoặc mặc định, dễ xung đột giữa tests.
- `NONE`: không khởi tạo web application context; phù hợp CLI/test lifecycle thuần.

Demo chọn `NONE` để tránh port, giúp tập trung vào **main vs context lifecycle**. Thay `webEnvironment` **không** thay thế `useMainMethod`; đó là hai trục cấu hình khác nhau.

## 12. Context caching: main không chạy mỗi lần @Test

Spring TestContext Framework **cache ApplicationContext** giữa các test có cấu hình tương đương. Vì thế:
- Một lần tạo context → runner và @PostConstruct chạy khi context khởi động.
- Nhiều `@Test` cùng dùng cached context → không tự startup context lại mỗi lần.
- Test runner không gọi `main` mỗi test method chỉ vì bạn đặt `ALWAYS`; nó dùng main khi **tạo context mới** theo loader.
- `@PreDestroy` không có nghĩa chạy sau mỗi test; nó có thể chạy khi context bị evict/dirty, test suite kết thúc hoặc cache bị đóng.
- Thứ tự thực thi test class do build/JUnit quyết định, không dùng log toàn suite để suy ra callback counts ổn định.

### @DirtiesContext

Khi một test thay đổi trạng thái singleton hoặc hạ tầng context và test khác không được dùng lại cùng context, có thể đánh dấu:

~~~java
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_CLASS)
~~~

Đây là annotation minh họa trên test class, cần import `org.springframework.test.annotation.DirtiesContext`. Nó khiến framework đánh dấu context dirty sau class để giải phóng khỏi cache, dẫn tới một lần startup mới khi cần context tương đương về sau.

**Không lạm dụng @DirtiesContext** để “cho main chạy lần nữa”. Nó làm chậm suite và có thể che việc test gây side effects không cleanup đúng. Nếu mục tiêu là verify bean startup một lần, assertion qua per-context marker/counter thường rõ hơn.

### Chạy song song

Nếu JUnit test parallel hoặc nhiều module dùng chung JVM/process, một static counter trong main dễ bị thay đổi bởi test khác. Vì thế demo dùng bean `StartupState` giữ count trong **mỗi context**, kết hợp property/profile trong Environment để tránh phụ thuộc thứ tự.

Tuy nhiên property/profile global vẫn có thể bị can thiệp nếu main khác gọi `System.setProperty`; một lý do nữa để tránh global mutable state trong main.

## 13. Main đã chạy nhưng @SpringBootTest vẫn không giống chạy production hoàn toàn

`useMainMethod=ALWAYS` giúp dùng main để khởi tạo context, nhưng **không bảo đảm đầy đủ parity**:

| Khác biệt | Vì sao |
| --- | --- |
| JVM process/flags | Tests thường chạy trong JVM của Maven/Gradle/IDE, không phải `java -jar` production |
| Classpath | Test includes `spring-boot-starter-test` và test classes; packaged JAR có layout khác |
| Properties | `@SpringBootTest(properties)`, `@ActiveProfiles`, test resources và CI env có thể override |
| Web server | `webEnvironment` có thể tạo mock/port khác production |
| Database | Test có thể dùng H2, Testcontainers hoặc mock khác production |
| Context caching | Spring TestContext giữ context để test nhanh hơn |
| Exit behavior | Không nên gọi System.exit; shutdown hook/test suite khác production |
| Threads và timing | Parallel tests, instrumentation, coverage agent và scheduler khác |
| Time/locale/env | JVM system properties, timezone, clock và external services có thể khác |

Bởi vậy `ALWAYS` là một cách **kiểm tra customization trong main**, không thay thế smoke test chạy artifact thực, kiểm tra health/readiness, database connectivity hoặc kiểm tra exit code trong subprocess.

Nếu một thuộc tính chỉ áp dụng khi main được chạy, test DEFAULT có thể không quan sát nó. Nếu `ALWAYS` pass, cũng cần xác minh thuộc tính đó không bị override ngoài production.

## 14. Trường hợp không có main và ALWAYS sẽ fail

Một `@SpringBootConfiguration` có thể chỉ khai báo bean mà không có method main (ví dụ module thư viện hoặc test configuration). Với:

~~~java
@SpringBootTest(
        classes = LibraryConfiguration.class,
        useMainMethod = UseMainMethod.ALWAYS)
~~~

test sẽ không thể dùng main nếu `LibraryConfiguration` không có method đó và **fail trong bước tạo test context**.

Với `WHEN_AVAILABLE`, test có thể sử dụng loader chuẩn để tạo context từ class cấu hình. Với `NEVER` thì luôn đi đường loader, không cần main.

Đây là **đoạn minh họa**, không thuộc bốn file test PASS ở mục 7 vì `LibraryConfiguration` không được định nghĩa trong demo; nếu muốn thực hành, hãy tạo một class `@SpringBootConfiguration`/`@EnableAutoConfiguration` cụ thể rồi viết một test riêng có chủ đích mong failure. Không đưa test luôn fail vào build mặc định.

Điểm cần hiểu: **thiếu main không có nghĩa không thể có Spring ApplicationContext**. Cấu hình của Spring được tạo từ class annotations/BeanDefinitions, không bắt buộc Java launcher method.

## 15. @SpringBootTest(args) khác tự gọi main(args)

Ví dụ:

~~~java
@SpringBootTest(
        args = "--app.feature.enabled=true",
        useMainMethod = UseMainMethod.NEVER)
~~~

Test loader chuyển argument vào SpringApplication của test. Nếu app định nghĩa một `ApplicationRunner` nhận `ApplicationArguments` hoặc dùng `Environment`, nó có thể quan sát property này, dù main chưa từng được gọi.

**Không được hiểu**: “Chỉ có main(String[] args) mới biết các CLI arguments”. `SpringApplication.run(args)` cũng xử lý arguments, và TestContext có thể tạo SpringApplication rồi truyền args trực tiếp.

Trong demo, `MainArgumentsTest` kiểm chứng `lesson.cli.marker` có mặt trong Environment nhưng `lesson.main.origin` không có.

Nếu test đặt:

~~~java
@SpringBootTest(
        properties = "app.feature.enabled=true",
        useMainMethod = UseMainMethod.NEVER)
~~~

thì đó là **test Environment property**, không phải argument đã đi qua method main. Đường test có thể mang cùng property name với production mà vẫn không gọi main.

## 16. Phân biệt với @ContextConfiguration và test slice

### @ContextConfiguration

`@ContextConfiguration` là annotation của Spring Test Framework để chọn sources và context loader. Nếu không qua `SpringApplication` phù hợp, các Boot-specific features như application arguments/runners/events có thể khác. Không nên suy “mọi Spring test đều chạy ApplicationRunner” nếu test không dùng Boot SpringApplication loader.

`@SpringBootTest` là cách Boot tích hợp TestContext để chạy một Boot application đầy đủ hơn. Nhưng nó mặc định **vẫn không gọi Java main**.

### @WebMvcTest, @DataJpaTest và các test slices

Test slices thường nạp một phần cấu hình phù hợp với tầng cần kiểm tra, không khởi động toàn bộ application như `@SpringBootTest`. Đừng kỳ vọng:
- Một runner production luôn có mặt trong slice.
- Mọi @Component đều được scan.
- Thân main được gọi.
- Có embedded server thực.

Nếu mục tiêu chỉ là test controller hoặc JPA mapping, dùng slice để tránh khởi tạo toàn bộ lifecycle không liên quan. Nếu mục tiêu là xác minh main-specific Boot settings, dùng một integration test `@SpringBootTest(useMainMethod=ALWAYS)` có phạm vi rõ.

### @TestConfiguration

Khi một test cần thay bean hoặc bổ sung configuration mà không sửa main, có thể dùng nested `@TestConfiguration` hoặc import một top-level `@TestConfiguration`. Nó không có ý nghĩa “chạy main”; nó chỉ thêm nguồn cấu hình cho test.

Phân biệt `@TestConfiguration` với nested `@Configuration`: theo Boot docs, nested `@Configuration` có thể trở thành cấu hình chính thay thế source tự động tìm, trong khi nested `@TestConfiguration` có thể bổ sung trên primary app configuration.

## 17. Debug khi cấu hình production đúng nhưng test thiếu bean

Tình huống:

~~~text
Production:
  main():
    new SpringApplication(...)
    setAdditionalProfiles("integration")
    run(...)
  |
  +-- @Profile("integration") BeanA được tạo

@SpringBootTest mặc định:
  TestContext:
    tạo SpringApplication trực tiếp
    không gọi main()
  |
  +-- profile integration không active
  +-- BeanA không tồn tại
  +-- BeanB cần BeanA -> startup test fail
~~~

**Cách điều tra:**

1. Đọc exception thiếu bean và annotation/profile/condition của bean.
2. Xác định setting cần thiết được đặt ở đâu: trong main hay trong file/config chung?
3. Xác nhận test có đang dùng `UseMainMethod.NEVER` không.
4. Nếu test cần giống production launcher, thử `ALWAYS` trong một test tích hợp có kiểm soát.
5. Nếu test muốn môi trường riêng, dùng `@ActiveProfiles`/`properties` hoặc refactor config ra cơ chế chung.
6. Đối chiếu condition report với `--debug`/logger phù hợp nếu bean conditional không được tạo.
7. Kiểm tra test không tự tạo context khác hoặc dùng mock/slice làm thay đổi bean graph.

Không sửa bằng cách thêm bean giả vào test trước khi hiểu vì sao production có bean còn test không. Đôi khi vấn đề thực sự là launcher-only configuration bị bỏ qua.

### Nếu test dùng ALWAYS mà vẫn không thấy main property?

Kiểm tra:
- `classes` có chọn đúng `@SpringBootApplication` chứa main không?
- Main có dùng `SpringApplication.run(...)` với đúng primary source không?
- Property có bị test `properties`, system property, environment variable hoặc profile config ưu tiên cao override không?
- Một test đã custom `ContextLoader` ngoài SpringBootContextLoader chưa?
- Test context có bị cache từ một cấu hình khác không? Kiểm tra merged context configuration và test annotations.
- Có extension/runner nào tự tạo một context thứ hai ngoài context Spring Test không?

Đừng dựa riêng vào log “Started ...” để chứng minh main được gọi: TestContext mặc định cũng ghi log Spring Boot started khi khởi tạo thành công.

## 18. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| “@SpringBootTest luôn chạy main” | Test thiếu custom profile/listener | Dùng `useMainMethod` rõ ràng hoặc refactor bootstrap |
| “main không chạy nên ApplicationRunner không chạy” | Test kích hoạt jobs ngoài ý muốn | Quản lý runner bằng profile/property/test config |
| “@SpringBootTest(classes=App.class) nghĩa là gọi App.main” | Hiểu sai configuration source | Phân biệt `classes` với `useMainMethod` |
| “ALWAYS chạy java -jar trong JVM khác” | Đặt System.exit trong main và giết test runner | Hiểu đây là lời gọi main trong test JVM |
| “WHEN_AVAILABLE bắt buộc có main” | Test có thể fallback im lặng | Dùng ALWAYS nếu cần invariant |
| Đo main bằng static counter duy nhất toàn suite | Flaky do cache/parallel/global state | Dùng marker Environment/per-context bean |
| Dùng `@PreDestroy` để đếm sau mỗi test | Assertion sai vì context caching | Điều khiển cache hoặc test lifecycle riêng |
| Đặt DB migration destructive trong runner | Test và Devtools có thể chạy lại job | Dùng migration framework và idempotence |
| Chuyển mọi test sang ALWAYS để chữa một lỗi | Side effects, test chậm, khó kiểm soát | Chỉ bật test cần launcher parity |
| Chỉ test bằng NEVER | Bỏ qua lỗi main-specific configuration | Có một số test ALWAYS tập trung |
| Mặc định MOCK tưởng mở HTTP server thật | Test gửi request qua localhost thất bại | Dùng RANDOM_PORT khi cần real HTTP |
| Sử dụng @TestConfiguration sai chỗ | Không tìm đúng primary config | Hiểu nested configuration resolution |
| Gọi System.setProperty trong main | Rò cấu hình sang test khác | Ưu tiên Environment property/initializers |
| Test method gọi main() thủ công | Có thể tạo context thứ hai không được TestContext quản lý | Dùng `useMainMethod=ALWAYS` |
| Runner dùng System.exit khi xong | Maven test process bị kill | Runner trả kết quả, entrypoint quyết định exit |
| Chỉ nhìn log thay vì assertion | Log bị reorder/cached khó kết luận | Assert vào Environment và bean state |

## 19. Mô hình test tốt cho logic main-specific

Một chiến lược có ba tầng:

**Tầng A — Unit tests:**
- Test service, business logic bằng JUnit không cần Spring.
- Không phụ thuộc entrypoint hay context.
- Dùng mocks/fakes cho network.

**Tầng B — Spring integration tests:**
- Dùng `@SpringBootTest` default hoặc test slices.
- Chọn profiles/properties phục vụ môi trường test.
- Kiểm tra dependency injection, bean lifecycle, runner behavior và transaction.
- Tránh phụ thuộc vào main customization trừ khi chính nó là đối tượng test.

**Tầng C — Bootstrap/launcher tests:**
- Dùng một số test `@SpringBootTest(useMainMethod=ALWAYS)` có mục tiêu rõ.
- Assert main profiles/default properties/listeners được áp dụng.
- Nếu cần kiểm tra process args, native env và OS exit code, dùng subprocess với packaged artifact.
- Không cho các test “launcher” tạo side effects mà không có dọn dẹp rõ.

Ba tầng giải quyết ba câu hỏi khác nhau: logic có đúng, context có đúng, và đường entrypoint production có đúng.

### Vì sao nên giữ main mỏng?

Một main mỏng:

~~~java
public static void main(String[] args) {
    SpringApplication.run(MyApplication.class, args);
}
~~~

giảm khác biệt giữa đường test và production. Các bean configuration hoặc Boot config properties có thể được nạp bởi cả hai đường. Tuy nhiên không bắt buộc mọi main đều mỏng; có dự án cần customizer ở entrypoint. Khi đó phải **chủ động test** những customization bằng useMainMethod hoặc tách chúng thành cấu hình có thể kiểm chứng.

## 20. Câu hỏi ôn tập

**Câu 1:** `@SpringBootTest` mặc định có gọi `MyApplication.main` không?

**Trả lời:** Không. Default `useMainMethod=NEVER`; TestContext tạo SpringApplication dành cho test từ class cấu hình.

**Câu 2:** Không gọi main thì bean có được tạo không?

**Trả lời:** Có. SpringApplication vẫn tạo/refresh ApplicationContext, xử lý beans, injection và lifecycle theo cấu hình test.

**Câu 3:** `ApplicationRunner` có chạy trong `@SpringBootTest` mặc định không?

**Trả lời:** Có thể có và thường có nếu runner bean tồn tại và SpringApplication startup thành công. Nó là Boot startup hook, không phải code trong thân Java main.

**Câu 4:** Phân biệt ALWAYS với WHEN_AVAILABLE?

**Trả lời:** ALWAYS bắt buộc main và fail nếu thiếu; WHEN_AVAILABLE dùng main nếu có, nếu không fallback.

**Câu 5:** Annotation nào dùng để bắt buộc test gọi main?

**Trả lời:** `@SpringBootTest(useMainMethod = UseMainMethod.ALWAYS)`.

**Câu 6:** Dùng `@SpringBootTest(classes = MyApplication.class)` có bắt buộc main chạy không?

**Trả lời:** Không. `classes` chọn configuration source; `useMainMethod` quyết định gọi main.

**Câu 7:** `@PostConstruct` có bị bỏ qua khi main không chạy?

**Trả lời:** Không nếu bean vẫn được khởi tạo. Nó là lifecycle callback của bean.

**Câu 8:** `ApplicationReadyEvent` có thể xuất hiện trong @SpringBootTest default không?

**Trả lời:** Có trong đường SpringApplication startup thành công; không cần Java main được gọi.

**Câu 9:** Khi nào test không thấy profile setAdditionalProfiles trong main?

**Trả lời:** Khi test dùng NEVER, trừ khi profile đó được kích hoạt bởi nguồn khác.

**Câu 10:** `@SpringBootTest(args = "--x=y")` có làm main chạy không?

**Trả lời:** Không. Args được truyền cho SpringApplication dùng trong test; useMainMethod vẫn độc lập.

**Câu 11:** Test có main gọi `System.exit` thì có an toàn khi dùng ALWAYS không?

**Trả lời:** Không. Nó có thể kết thúc JVM test runner, làm ngừng cả suite.

**Câu 12:** @PreDestroy có chạy sau mỗi @Test không?

**Trả lời:** Không mặc nhiên; context có thể được cache qua nhiều test methods/classes.

**Câu 13:** MAIN_METHOD_INVOKED không xuất hiện, nhưng RUNNER_EXECUTED xuất hiện. Mâu thuẫn không?

**Trả lời:** Không. Đó chính là hành vi điển hình của @SpringBootTest default: SpringApplication chạy qua test loader, không qua main.

**Câu 14:** useMainMethod=ALWAYS có bảo đảm test tương đương java -jar production 100% không?

**Trả lời:** Không. JVM, classpath, profiles, test properties, web environment và external services có thể khác.

**Câu 15:** Khi nào nên refactor logic main thành Spring configuration?

**Trả lời:** Khi customization/side effects cần có trong cả runtime và tests, hoặc cần kiểm tra độc lập, tránh một entrypoint quá phức tạp.

## 21. Bài tập thực hành

### Bài tập 1 — đối chiếu default với ALWAYS

Chạy `mvn -Dtest=MainDefaultTest test` rồi `mvn -Dtest=MainAlwaysTest test`. Ghi lại các marker main, bean và runner; so sánh Environment property/profile bằng assertions.

### Bài tập 2 — thêm một method @Test

Trong `MainDefaultTest`, thêm test method thứ hai cũng inject `StartupState`. Quan sát `runnerCalls()` vẫn là 1 nếu context được tái sử dụng; giải thích vì sao runner không chạy lại với mỗi method.

### Bài tập 3 — đổi configuration trong main

Thay `setAdditionalProfiles("from-main")` bằng `setAdditionalProfiles("another-profile")`, cập nhật assertion của test ALWAYS, chạy lại. Mặc định NEVER vẫn không tự nhận profile mới.

### Bài tập 4 — truyền args

Sửa `MainArgumentsTest.args` thành `--lesson.cli.marker=another-value` và sửa assertion. Xác nhận main marker vẫn không xuất hiện cho context mặc định.

### Bài tập 5 — ALWAYS khi không có main

Tạo class `@SpringBootConfiguration` không có main; viết test với classes chỉ tới class đó, useMainMethod=ALWAYS. Xem lỗi tạo context, rồi đổi sang WHEN_AVAILABLE và kiểm tra có thể bootstrap từ config hợp lệ.

### Bài tập 6 — runner side effects

Thêm một runner giả lập ghi một item vào in-memory list, rồi kiểm chứng nó chạy khi default @SpringBootTest tạo context. Sau đó dùng `@ConditionalOnProperty` để tắt runner ở một nhóm test. Không dùng external email/payment thật.

### Bài tập 7 — kiểm tra cleanup

Thêm một SmartLifecycle hoặc resource bean với `@PreDestroy`. Quan sát callback khi context bị đóng; thử `@DirtiesContext` và giải thích vì sao destroy không gắn cứng với mỗi test method.

### Bài tập 8 — test webEnvironment

Thêm web starter trong một project riêng, thử `MOCK` và `RANDOM_PORT`, xem khác biệt có embedded server port thật hay không. Đừng lấy khác biệt web type để kết luận main đã được gọi.

### Bài tập 9 — profile do test đặt

Dùng `@ActiveProfiles("from-main")` trong một test default NEVER. Xác nhận profile active dù main không chạy; giải thích vì sao profile active **không đủ** để chứng minh main đã chạy.

### Bài tập 10 — context cache

Chạy toàn `mvn test` và xem log thời điểm Spring context được tạo. Nhận diện vì sao số lần in bean init có thể ít hơn số lượng test methods, và dùng per-context state thay vì static count.

### Bài tập 11 — test packaged launcher

Build `mvn package`, chạy `java -jar` ở subprocess và kiểm tra marker MAIN_METHOD_INVOKED. So sánh với MainDefaultTest. Không gọi `System.exit` trong JVM test runner.

### Bài tập 12 — kiểm tra đường lỗi

Đặt main-customization quyết định một bean conditional. Test với NEVER thất bại do thiếu bean, còn ALWAYS thành công. Đọc condition report và xác định **nguyên nhân thực** là bootstrap profile/property thiếu, không phải @SpringBootTest không tạo bean.

## 22. Tài liệu chính thức

- [Spring Boot 3.5.16 — Testing Spring Boot Applications, Using the Test Configuration Main Method](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): mặc định main không chạy, ALWAYS và WHEN_AVAILABLE.
- [Spring Boot 3.5.16 — @SpringBootTest Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/SpringBootTest.html): `classes`, `properties`, `args`, `webEnvironment` và default `useMainMethod=NEVER`.
- [Spring Boot 3.5.16 — SpringBootTest.UseMainMethod Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/SpringBootTest.UseMainMethod.html): NEVER, ALWAYS, WHEN_AVAILABLE.
- [Spring Boot 3.5 — SpringApplication](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): Boot startup sequence, runners, events và profiles.
- [Spring Boot 3.5 — Testing](https://docs.spring.io/spring-boot/3.5/reference/testing/index.html): starter-test, JUnit Jupiter, test slices và TestContext.
- [Spring Framework 6.2 — TestContext Framework Context Caching](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html): cached contexts, @DirtiesContext và cleanup.
- [Spring Framework 6.2 — Bean Lifecycle](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html): @PostConstruct, @PreDestroy và Lifecycle/SmartLifecycle.

## 23. Tổng kết và checklist

Trước khi viết hoặc sửa một test dùng Spring Boot:

1. Test cần **Spring context**, **đường main entry point**, hay cả hai?
2. `useMainMethod` đang là NEVER, ALWAYS hay WHEN_AVAILABLE?
3. Main có tùy biến profiles, properties, listeners hoặc application settings không?
4. Những tùy biến đó có thật sự cần có trong test hay nên chuyển vào shared config?
5. Các `ApplicationRunner`, `CommandLineRunner`, `@PostConstruct` và `SmartLifecycle` có side effects không?
6. Test có vô tình gọi `System.exit` hoặc tạo resource JVM-global không?
7. `classes`/package của test có trỏ đúng primary `@SpringBootConfiguration` không?
8. `webEnvironment` có tạo server thật hay chỉ mock context?
9. `@SpringBootTest(args)` và test `properties` đã được phân biệt với việc gọi main chưa?
10. Có dùng context caching, @DirtiesContext hoặc parallel tests ảnh hưởng counter/log không?
11. Test có assertion chứng minh main-specific customization thực sự được áp dụng không?
12. Có cần một subprocess/smoke test để kiểm tra runtime process ngoài test JVM không?

**Ghi nhớ cuối cùng:**

- **`@SpringBootTest` mặc định không gọi Java `main`**: `UseMainMethod.NEVER`.
- **Context vẫn được khởi động**, bean lifecycle và Boot runners vẫn có thể chạy.
- **`ALWAYS` gọi main và fail nếu main không tồn tại**; **`WHEN_AVAILABLE` gọi nếu có, fallback nếu không**.
- `classes` là configuration source, không phải lệnh gọi main; `args` là application arguments, không tự đổi useMainMethod.
- Logic trong main như `setAdditionalProfiles` và `setDefaultProperties` không tự có ở test mặc định.
- TestContext có **context caching**: không suy callback/startup count từ số `@Test`.
- Khi cần parity với production bootstrap, viết một số test ALWAYS có kiểm soát, không dùng System.exit trong test JVM.
- Nếu chỉ muốn test service/bean graph, default NEVER thường thích hợp hơn; giữ entrypoint mỏng, side effects được quản lý bởi cấu hình/lifecycle có thể kiểm thử riêng.
