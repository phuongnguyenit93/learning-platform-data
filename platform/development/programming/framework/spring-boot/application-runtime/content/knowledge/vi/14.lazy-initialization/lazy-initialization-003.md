# Chọn ngoại lệ bằng @Lazy(false) khi bật khởi tạo lười trong Spring Boot

## 1. Bài toán: muốn startup nhanh nhưng một số bean vẫn phải được tạo ngay

Spring Boot có chế độ **khởi tạo lười (lazy initialization)**: thay vì tạo phần lớn các singleton ứng dụng ngay khi context được refresh, framework chỉ tạo chúng lúc thật sự cần. Tính năng này có thể làm **thời gian đến mốc started ngắn hơn**, đặc biệt với ứng dụng có nhiều bean mà một phiên làm việc không cần dùng hết. Tuy nhiên, việc trì hoãn tạo bean cũng có cái giá:

- Lỗi thiếu cấu hình, tạo kết nối hoặc khởi tạo nội bộ có thể **chỉ xuất hiện ở request đầu tiên**.
- Lời gọi đầu tiên phải chịu chi phí constructor, dependency injection, `@PostConstruct`, proxy, tạo connection, tải cache hoặc kiểm tra dữ liệu.
- Một service tưởng như đã “started” có thể chưa thực sự đã thử khởi tạo những thành phần tối quan trọng.
- Khối lượng bộ nhớ JVM sau startup có thể tăng khi các bean còn lại được gọi lần đầu.

Đôi khi bạn muốn **bật lazy initialization cho phần lớn ứng dụng nhưng chọn một vài bean buộc khởi tạo ngay**. Spring Boot cho phép làm điều này bằng annotation:

```java
@Lazy(false)
```

Ví dụ:

```properties
# src/main/resources/application.properties
spring.main.lazy-initialization=true
```

```java
@Service
@Lazy(false)
public class CriticalConfigVerifier {
    // Bean này không còn lazy mặc định theo cấu hình toàn ứng dụng.
}
```

Đoạn code trên là **mẫu tích hợp** cần các import Spring và một dự án thực tế. `@Lazy(false)` tại **định nghĩa bean** nói với container rằng bean này **không phải bean khởi tạo lười**. Đối với **singleton thông thường** trong một `ApplicationContext` có cơ chế pre-instantiation, bean sẽ được khởi tạo trong giai đoạn khởi động context, không đợi tới request đầu tiên.

**Ý nghĩa đúng:** “Hãy tạo sớm bean được chỉ định.” **Ý nghĩa sai:** “Toàn ứng dụng đã ready”, “tất cả bean còn lại sẽ giữ nguyên trạng thái lazy trong mọi trường hợp” hoặc “mọi loại scope đều bị buộc tạo sẵn”.

## 2. Bật chế độ lazy toàn ứng dụng trước khi chọn ngoại lệ

### 2.1. Bật bằng application.properties

```properties
spring.main.lazy-initialization=true
```

Đây là thuộc tính cấu hình của **Spring Boot**, không phải `spring.lazy=true` hay `@Lazy` trên lớp main. Thuộc tính có thể đặt trong `application.properties` hoặc nguồn cấu hình có độ ưu tiên cao hơn như đối số ứng dụng:

```bash
java -jar myapp.jar --spring.main.lazy-initialization=true
```

### 2.2. Bật bằng application.yaml

```yaml
spring:
  main:
    lazy-initialization: true
```

Hai ví dụ properties và YAML là **hai cách thay thế**, không cần dùng cùng lúc trong bài thực hành.

### 2.3. Bật tường minh từ mã Java

```java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setLazyInitialization(true);
app.run(args);
```

Đây là mã mẫu tích hợp vào `main`, cần import Spring Boot và lớp ứng dụng thật. Việc gọi `setLazyInitialization(true)` cấu hình đối tượng `SpringApplication` trước khi `run` bắt đầu. Nếu đồng thời có property bên ngoài, cần nắm quy tắc binder/khởi tạo cụ thể; không suy luận đơn giản rằng Java setter và property CLI thuộc cùng một `PropertySource`.

### 2.4. Nếu không bật lazy toàn cục thì sao?

Spring Framework theo mặc định **pre-instantiate các singleton không lazy** khi refresh context. Do đó, nếu `spring.main.lazy-initialization=false` hoặc không bật lazy và bean không bị cấu hình lazy khác, thêm `@Lazy(false)` thường chỉ làm ý định khởi tạo sớm trở nên **tường minh**, không phải tăng thêm một khả năng mới.

`@Lazy` **không có đối số** tương đương `@Lazy(true)` — tức *yêu cầu khởi tạo lười*. `@Lazy(false)` có tác dụng ngược lại — *tắt lazy cho bean được đánh dấu*. Hai annotation chỉ khác một giá trị Boolean nhưng tác động ngược nhau, nên rất dễ gây nhầm khi đọc code.

## 3. @Lazy(false) thay đổi điều gì ở vòng đời bean?

Xem ba nhóm:

```text
SpringApplication bắt đầu
          |
          v
spring.main.lazy-initialization=true
          |
          v
Xử lý bean definitions và tạo ApplicationContext
          |
          +-----------------------------------------+
          | Bean A: @Service                        |
          | không có ngoại lệ                       |
          | -> có thể lazy                          |
          +-----------------------------------------+
          |
          +-----------------------------------------+
          | Bean B: @Service @Lazy(false)           |
          | -> không lazy                           |
          +-----------------------------------------+
          |
          +-----------------------------------------+
          | Bean C: @Bean @Lazy(false)              |
          | -> không lazy                           |
          +-----------------------------------------+
          |
          v
refresh(): pre-instantiate các non-lazy singletons
          |
          +--> tạo B (+ dependency cần thiết)
          +--> tạo C (+ dependency cần thiết)
          |    A vẫn chưa cần tạo nếu không bị tham chiếu
          v
ApplicationStartedEvent
          |
Spring Boot gọi ApplicationRunner / CommandLineRunner
          |
ApplicationReadyEvent
          |
Request/lookup đầu tiên của A -> tạo A nếu vẫn chưa tạo
```

**Không được biến sơ đồ này thành một thứ tự chính xác giữa B và C.** Hai bean eager độc lập có thể được tạo theo thứ tự phụ thuộc vào metadata, dependency graph và quy trình của container. `@Lazy(false)` không cung cấp một thứ tự ưu tiên giữa nhiều bean.

Một singleton được khởi tạo sớm vẫn đi qua vòng đời cơ bản:

1. Spring chọn bean definition và constructor/factory method.
2. Tạo instance, giải quyết dependency.
3. Gọi `BeanPostProcessor` liên quan.
4. Thực hiện callbacks như `@PostConstruct`, `InitializingBean` hoặc init method khi áp dụng.
5. Hoàn tất post-processing, có thể tạo proxy.
6. Công bố reference bean để các consumer sử dụng.

`@Lazy(false)` tác động **mốc bắt đầu tạo instance**, không bỏ qua các bước khởi tạo, validation, dependency injection hay post-processing.

Cần phân biệt **bean definition đã được đăng ký** với **singleton instance đã tồn tại**. Một bean lazy có definition trong container nhưng chưa có instance. Gọi `context.containsBean("myBean")` có thể trả `true` ngay cả khi đối tượng chưa được tạo. Phần 7 sẽ kiểm tra bằng `beanFactory.containsSingleton(...)` để tránh nhầm lẫn này.

## 4. Cú pháp chọn ngoại lệ cho lớp @Component hoặc @Service

Các stereotype như `@Component`, `@Service` hoặc `@Repository` đều là các bean được Spring đăng ký qua component scan. Với một bean singleton thuộc nhóm này:

```java
package com.example.lazy;

import org.springframework.context.annotation.Lazy;
import org.springframework.stereotype.Service;

@Service
@Lazy(false)
public class CriticalService {

    public CriticalService() {
        System.out.println("CriticalService created");
    }
}
```

Nếu global lazy đang bật, Spring vẫn lên lịch tạo instance này trong quá trình refresh thông thường. Nó không phải đợi người dùng gọi `getBean(CriticalService.class)`.

Một cách tương đương khi muốn viết rõ giá trị annotation:

```java
@Lazy(value = false)
```

**Vị trí:** gắn annotation trực tiếp trên **lớp component**, không gắn chỉ lên một method nghiệp vụ rồi tưởng rằng toàn lớp được eager. `@Lazy` dành cho định nghĩa bean, phương thức `@Bean` hoặc điểm tiêm dependency; nó không phải annotation điều khiển **lần đầu gọi mỗi method**.

### Chọn bean nào để đặt @Lazy(false)?

Thường cân nhắc:

- Bean kiểm tra cấu hình quan trọng mà sai phải làm startup thất bại.
- Thành phần chuẩn bị hạ tầng bắt buộc trước khi bắt đầu nhận traffic.
- Bean quản lý tài nguyên cần đảm bảo đã sẵn sàng từ đầu theo yêu cầu vận hành.
- Thành phần khởi tạo dữ liệu bắt buộc, **nếu** thiết kế phù hợp với callback bean (đối với thao tác phối hợp nhiều service, runner thường rõ ràng hơn).

Không nên gắn `@Lazy(false)` lên toàn bộ service chỉ vì chúng “quan trọng”. Làm vậy mất lợi ích của global lazy và tăng chi phí startup. Hãy hỏi: **thành phần này cần tồn tại lúc context refresh hay chỉ cần được kiểm tra xong trước readiness?** Hai yêu cầu có thể dẫn tới hai cơ chế khác nhau.

## 5. Cú pháp chọn ngoại lệ trên phương thức @Bean

Không phải bean nào cũng do `@ComponentScan` phát hiện. Một bean có thể được tạo từ phương thức factory trong `@Configuration`:

```java
package com.example.lazy;

import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Lazy;

@Configuration
public class ClockConfiguration {

    @Bean
    @Lazy(false)
    Clock businessClock() {
        return Clock.systemUTC();
    }

    @Bean
    ExpensiveFormatter expensiveFormatter() {
        return new ExpensiveFormatter();
    }
}
```

Đây là **mẫu tích hợp**, không phải project tự chứa: cần class `ExpensiveFormatter` phù hợp. Khi global lazy = true, `businessClock` là ngoại lệ eager; `expensiveFormatter` có thể vẫn lazy nếu không bị bean khác yêu cầu.

**Phải đặt `@Lazy(false)` trên chính phương thức `@Bean` tạo bean mà bạn muốn khởi tạo sớm**. Việc gắn annotation vào một phương thức Java thông thường không đăng ký bean không khiến Spring theo dõi nó.

Ví dụ factory method có điều kiện:

```java
@Bean
@Lazy(false)
@ConditionalOnProperty(
        prefix = "demo",
        name = "startup-verification-enabled",
        havingValue = "true")
StartupVerifier startupVerifier() {
    return new StartupVerifier();
}
```

Đây là snippet tích hợp cần class `StartupVerifier` và import `ConditionalOnProperty`. **`@Lazy(false)` không ghi đè `@ConditionalOnProperty`**. Nếu điều kiện không thỏa, bean definition tương ứng có thể **không được đăng ký**, nên cũng không có instance nào để buộc eager.

### @Lazy trên lớp @Configuration có ảnh hưởng gì?

`@Lazy` đặt trên một `@Configuration` có thể thiết lập chính sách lazy cho các phương thức `@Bean` được khai báo trong lớp đó. Spring Framework cho phép `@Lazy(false)` tại một **phương thức `@Bean` riêng** để ghi đè trạng thái lazy chung từ lớp cấu hình:

```java
@Configuration
@Lazy
class BatchConfiguration {

    @Bean
    ExpensiveImporter importer() {
        return new ExpensiveImporter(); // lazy mặc định theo lớp cấu hình
    }

    @Bean
    @Lazy(false)
    CriticalChecker criticalChecker() {
        return new CriticalChecker(); // ngoại lệ non-lazy
    }
}
```

Đây cũng là snippet minh họa, cần lớp `ExpensiveImporter` và `CriticalChecker`; ý chính là **override tại phương thức bean**. Khi cần chọn rất ít ngoại lệ, đặt `@Lazy(false)` ở **định nghĩa cụ thể** sẽ dễ đọc và dễ QA hơn so với gắn một annotation phạm vi rộng rồi suy từ đó.

## 6. Nguyên tắc quyết định: yêu cầu sớm đến mức nào?

Hãy phân biệt ba nhu cầu:

| Nhu cầu thực tế | Cơ chế thích hợp | Thời điểm bảo đảm theo thiết kế |
|---|---|---|
| “Tạo singleton quan trọng khi context refresh” | `@Lazy(false)` trên bean definition | Trong giai đoạn pre-instantiation của non-lazy singleton |
| “Chạy kiểm tra bằng nhiều service khi context đã refresh, trước Ready” | `ApplicationRunner` / `CommandLineRunner` | Sau `ApplicationStartedEvent`, trước `ApplicationReadyEvent` |
| “Chạy hành động khi ứng dụng hoàn thành startup” | Listener `ApplicationReadyEvent` | Sau các runner |
| “Tạo bean khi code dùng tới lần đầu” | Để lazy theo global policy hoặc `@Lazy` | Lần đầu bị container yêu cầu; có thể sớm nếu dependency eager đòi hỏi |
| “Hoãn giải quyết một dependency riêng” | `@Lazy` tại điểm tiêm hoặc `ObjectProvider<T>` | Điều khiển việc lấy reference dependency, không nhất thiết là policy của bean definition |

Một bean non-lazy có thể có constructor nhẹ, rồi triển khai `@PostConstruct` để kiểm tra cấu hình nội bộ. Nhưng nếu yêu cầu là gọi repository, network API và nhiều service sau khi toàn context đã refresh, một runner có timeout phù hợp thường làm mục đích rõ hơn.

**Đừng dùng `@Lazy(false)` thay readiness probe.** Việc một constructor đã chạy không đủ chứng minh database, endpoint bên ngoài hay toàn bộ luồng HTTP sẵn sàng. Với dịch vụ có orchestrator, phải thiết kế thêm health/readiness đúng yêu cầu.

## 7. Ví dụ Spring Boot 3.3.x + Java 17+: hai ngoại lệ eager và một bean lazy

Đây là ví dụ chạy được để bạn quan sát trực tiếp:

- Một `@Service @Lazy(false)` được tạo trước khi runner kiểm tra.
- Một `@Bean @Lazy(false)` cũng được tạo trước runner.
- Một `@Service` không đánh dấu gì có thể giữ trạng thái **chưa có singleton instance** khi global lazy bật.
- Khi chủ động `getBean(...)`, bean lazy mới được tạo và `containsSingleton` chuyển từ `false` sang `true`.

Ứng dụng là **non-web**, không cần HTTP server hay database. Nó dùng `System.out` chỉ để dễ thấy thứ tự khi học.

### 7.1. Thư mục project

```text
lazy-exception-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/lazydemo/
    │   ├── LazyExceptionApplication.java
    │   ├── CriticalService.java
    │   └── OnDemandService.java
    └── resources/
        └── application.properties
```

**`settings.gradle`:**

```groovy
rootProject.name = 'lazy-exception-demo'
```

**`build.gradle` (Gradle Groovy DSL):**

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
}
```

**`src/main/resources/application.properties`:**

```properties
spring.application.name=lazy-exception-demo
spring.main.lazy-initialization=true
```

Đặt file properties trong `src/main/resources` để nó có trên runtime classpath. Không tạo thêm `application.yaml` có nội dung mâu thuẫn cho cùng bài thực hành.

### 7.2. Bean ngoại lệ thứ nhất: @Service @Lazy(false)

**`src/main/java/com/example/lazydemo/CriticalService.java`:**

```java
package com.example.lazydemo;

import org.springframework.context.annotation.Lazy;
import org.springframework.stereotype.Service;

@Service
@Lazy(false)
public class CriticalService {

    public CriticalService() {
        System.out.println("CREATE criticalService");
    }

    public String status() {
        return "critical-ok";
    }
}
```

Class này nằm trong phạm vi component scan vì cùng package với lớp chính. Tên bean mặc định của `CriticalService` là `criticalService`. Constructor in thông điệp để kiểm tra thời điểm **instance** được tạo; không cần gọi `getBean` để nó xuất hiện.

### 7.3. Bean lazy thông thường: chỉ @Service

**`src/main/java/com/example/lazydemo/OnDemandService.java`:**

```java
package com.example.lazydemo;

import org.springframework.stereotype.Service;

@Service
public class OnDemandService {

    public OnDemandService() {
        System.out.println("CREATE onDemandService");
    }

    public String ping() {
        return "pong";
    }
}
```

Không có `@Lazy(false)` tại định nghĩa này. Trong bài thực hành, **không bean eager nào constructor-inject `OnDemandService`**, nên khi global lazy được bật, bean có thể chưa được tạo khi runner mới bắt đầu.

### 7.4. Bean ngoại lệ thứ hai và ApplicationRunner quan sát trạng thái

**`src/main/java/com/example/lazydemo/LazyExceptionApplication.java`:**

```java
package com.example.lazydemo;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Lazy;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;

@SpringBootApplication
public class LazyExceptionApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(LazyExceptionApplication.class);

        // Demo không sử dụng web server.
        application.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context =
                application.run(args)) {
            // Chương trình non-web có thể đóng context sau runner.
        }
    }

    @Bean
    @Lazy(false)
    StartupPolicy startupPolicy() {
        System.out.println("CREATE startupPolicy");
        return new StartupPolicy("strict");
    }

    @Bean
    ApplicationRunner inspectLazyBehavior(ApplicationContext context) {
        return args -> {
            ConfigurableListableBeanFactory factory =
                    ((ConfigurableApplicationContext) context)
                            .getBeanFactory();

            System.out.println(
                    "Runner: criticalService singleton = "
                    + factory.containsSingleton("criticalService"));

            System.out.println(
                    "Runner: startupPolicy singleton = "
                    + factory.containsSingleton("startupPolicy"));

            System.out.println(
                    "Runner: onDemandService before = "
                    + factory.containsSingleton("onDemandService"));

            OnDemandService service =
                    context.getBean(OnDemandService.class);

            System.out.println(
                    "Runner: onDemandService ping = " + service.ping());

            System.out.println(
                    "Runner: onDemandService after = "
                    + factory.containsSingleton("onDemandService"));
        };
    }

    public record StartupPolicy(String mode) {
    }
}
```

Giải thích chính xác những lựa chọn trong demo:

1. `@Bean @Lazy(false)` được đặt trên `startupPolicy()`, nên `StartupPolicy` trở thành singleton non-lazy trong cấu hình mặc định của bean factory.
2. `@Bean ApplicationRunner` có thể được Spring Boot tìm và gọi trong pha runner dù toàn ứng dụng đang ở chế độ lazy; các runner bean được dùng trong chính chuỗi startup.
3. Runner **không constructor-inject `OnDemandService`**. Nó chỉ yêu cầu `ApplicationContext`, sau đó quan sát cache singleton trước khi gọi `getBean(...)`. Nhờ vậy phép thử không vô tình buộc `OnDemandService` tạo sớm trong lúc dựng runner.
4. `containsSingleton("...")` kiểm tra **instance singleton đã đăng ký trong singleton cache**, không chỉ bean definition có tồn tại hay không. Nó thích hợp để minh họa trạng thái trước/sau của bean singleton trong bài.
5. `context.getBean(OnDemandService.class)` là mốc yêu cầu bean lazy; Spring tạo instance, chạy vòng đời bean và trả về reference cuối cùng phù hợp.
6. Class `StartupPolicy` dùng Java `record` (Java 17 hỗ trợ). Nó được tạo bởi factory method `startupPolicy()`, không phải do `@ComponentScan`.
7. `try-with-resources` đóng context sau khi `application.run(args)` trả về để demo non-web kết thúc sạch. Với một Web service cần tiếp tục phục vụ HTTP, **không tự đóng context ngay sau khởi động**.

### 7.5. Chạy chương trình

Nếu project có **Gradle Wrapper** (ví dụ tạo skeleton dự án từ Spring Initializr):

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Nếu bạn tự viết các file bằng tay, `gradlew`/`gradlew.bat` không tự được tạo chỉ vì có `build.gradle`. Có thể dùng một Gradle đã cài tương thích hoặc tạo Wrapper đúng phiên bản.

### 7.6. Kết quả mong đợi

Bỏ qua banner, log thông thường của Spring Boot và Gradle, các **dòng do code demo in ra** có những quan hệ sau:

```text
CREATE criticalService
CREATE startupPolicy
Runner: criticalService singleton = true
Runner: startupPolicy singleton = true
Runner: onDemandService before = false
CREATE onDemandService
Runner: onDemandService ping = pong
Runner: onDemandService after = true
```

**Thứ tự hai dòng `CREATE criticalService` và `CREATE startupPolicy` có thể đảo nhau**: đây là hai bean eager độc lập, và `@Lazy(false)` không ép thứ tự giữa chúng. Nội dung `Runner: ...` và thời điểm `CREATE onDemandService` là bằng chứng quan trọng:

- Trước khi runner bắt đầu, `criticalService` và `startupPolicy` đã có singleton instance.
- Tại thời điểm kiểm tra đầu tiên trong runner, `onDemandService` chưa có singleton instance.
- Sau `context.getBean(OnDemandService.class)`, constructor in `CREATE onDemandService` và cache singleton phản ánh `true`.
- Không cần đo số mili-giây cố định: thí nghiệm về **thời điểm tạo bean**, không phải benchmark.

Nếu có code ngoài ví dụ tự động tham chiếu `OnDemandService` trước runner, hoặc có auto-configuration/custom BeanPostProcessor mới, kết quả trước `getBean` có thể khác. Đó là lý do ví dụ cố ý giữ dependency graph tối giản.

### 7.7. Thí nghiệm đối chứng: tắt global lazy

Giữ nguyên code, chạy:

```bash
./gradlew bootRun --args='--spring.main.lazy-initialization=false'
```

Khi property này ghi đè giá trị `true` trong file, trong thiết lập thông thường `OnDemandService` cũng là **non-lazy singleton** và sẽ được tạo trong quá trình khởi động context.

Các dòng đáng kiểm tra lúc này:

```text
CREATE onDemandService
Runner: onDemandService before = true
Runner: onDemandService ping = pong
Runner: onDemandService after = true
```

`CREATE onDemandService` xảy ra **trước** dòng `Runner: onDemandService before = true`, thay vì ngay sau dòng `before = false` như trường hợp bật lazy. Việc bật/tắt global lazy không xóa bean definition hoặc thay đổi API `getBean`; nó chỉ tác động tới cách/container quyết định **khi nào tạo instance**.

### 7.8. Thí nghiệm đối chứng: bỏ @Lazy(false)

Khôi phục `spring.main.lazy-initialization=true`, sau đó:

- Tạm bỏ `@Lazy(false)` trên `CriticalService`.
- Tạm bỏ `@Lazy(false)` trên `startupPolicy()`.
- Giữ nguyên logic runner không yêu cầu hai bean này bằng `getBean`.

Trong cấu hình demo, hai bean đó sẽ có cơ hội trì hoãn khởi tạo; `containsSingleton("criticalService")` và `containsSingleton("startupPolicy")` có thể là `false` trước khi được yêu cầu. Đây là phép thử cho thấy **chính annotation trên định nghĩa bean** tạo ra ngoại lệ.

Khôi phục hai annotation sau thí nghiệm để tránh làm thay đổi điều kiện startup của bài học.

## 8. Bean lazy có thể bị tạo sớm vì dependency của bean eager

Đây là **ngoại lệ quan trọng nhất** khi bạn chọn `@Lazy(false)`:

> `@Lazy(false)` trên một bean đảm bảo bean đó **không bị trì hoãn do lazy policy của chính nó**. Nó không đảm bảo những bean khác giữ nguyên trạng thái chưa được tạo.

Ví dụ:

```java
@Service
public class RemoteClient {

    public RemoteClient() {
        System.out.println("RemoteClient created");
    }
}
```

```java
@Service
@Lazy(false)
public class StartupValidator {

    private final RemoteClient remoteClient;

    public StartupValidator(RemoteClient remoteClient) {
        this.remoteClient = remoteClient;
        System.out.println("StartupValidator created");
    }
}
```

Hai lớp là **snippet tích hợp** cần các import `@Service` và `@Lazy`, đặt vào project được component scan. Khi `spring.main.lazy-initialization=true`:

- `StartupValidator` là eager singleton.
- Constructor của `StartupValidator` yêu cầu `RemoteClient`.
- Để xây dựng `StartupValidator`, Spring phải giải quyết dependency. Vì vậy **`RemoteClient` có thể được tạo ngay trong startup dù bản thân nó không có `@Lazy(false)`**.

Kết quả logic có thể là:

```text
RemoteClient created
StartupValidator created
```

Tại đây ý quan trọng không nằm ở tốc độ tạo, mà ở **đường phụ thuộc**. Đánh dấu eager một bean có nhiều dependency có thể “kéo” cả đồ thị dependency được tạo sớm. Nếu bạn muốn tối ưu số bean tạo khi startup, hãy xem xét **đồ thị phụ thuộc của những ngoại lệ eager**, không chỉ đếm số annotation `@Lazy(false)`.

### Dùng ObjectProvider khi dependency thực sự chỉ cần ở thời điểm muộn

Nếu một bean cần eager để kiểm tra cấu hình nội bộ, nhưng chỉ dùng một service lớn sau này, bạn có thể tránh giải quyết service đó trong constructor bằng `ObjectProvider`:

```java
@Service
@Lazy(false)
public class StartupValidator {

    private final ObjectProvider<RemoteClient> remoteClientProvider;

    public StartupValidator(
            ObjectProvider<RemoteClient> remoteClientProvider) {
        this.remoteClientProvider = remoteClientProvider;
    }

    public void validateLater() {
        RemoteClient client = remoteClientProvider.getObject();
        // Dùng client khi thực sự cần.
    }
}
```

Đây là đoạn **minh họa tích hợp**, cần import `org.springframework.beans.factory.ObjectProvider` và các class đã có. `ObjectProvider` cho phép trì hoãn việc lấy reference tới khi gọi `getObject()`, nhưng **không hứa rằng dependency chưa được tạo bởi một consumer khác**. Và nếu bạn gọi `validateLater()` trong `@PostConstruct` của bean eager, chính bạn vẫn sẽ kéo dependency tạo sớm. Vì thế thời điểm **lấy object** mới là yếu tố cần kiểm soát.

Đừng dùng provider để che giấu một dependency bắt buộc của nghiệp vụ chỉ nhằm giảm một vài mili-giây startup. Nếu hệ thống phải chắc chắn remote client hoạt động trước Ready, hãy thiết kế bước validation thích hợp và có timeout.

## 9. @Lazy(false) tại định nghĩa bean khác @Lazy đặt ở điểm tiêm

Spring cũng cho phép `@Lazy` trên **điểm tiêm phụ thuộc** (`@Autowired` field/constructor parameter). Trong ngữ cảnh này, annotation có ý nghĩa khác với đánh dấu bean definition.

### 9.1. @Lazy trên bean definition

```java
@Service
@Lazy(false)
public class InventoryService {
}
```

Ý nghĩa: bean `InventoryService` không lazy trong bean factory (với scope thông thường); có thể được tạo lúc startup theo cơ chế pre-instantiation.

### 9.2. @Lazy trên điểm tiêm

```java
@Service
public class OrderService {

    private final InventoryService inventoryService;

    public OrderService(@Lazy InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }
}
```

Đây là snippet minh họa, cần import `@Service`, `@Lazy` và những class liên quan. `@Lazy` trên **constructor parameter** có thể yêu cầu Spring tiêm một **lazy-resolution proxy** cho dependency; target được giải quyết khi dùng lần đầu. Nó **không đồng nghĩa** với việc đánh dấu `InventoryService` có bean definition lazy. Nếu có một consumer khác yêu cầu target sớm, target vẫn có thể đã tồn tại.

Vì vậy:

| Vị trí | Ví dụ | Ý nghĩa |
|---|---|---|
| Trên class component | `@Service @Lazy(false)` | Tắt lazy **của bean được định nghĩa bởi class** |
| Trên factory method | `@Bean @Lazy(false)` | Tắt lazy **của bean được tạo từ method** |
| Trên lớp cấu hình | `@Configuration @Lazy` | Đặt chính sách lazy cho những `@Bean` method trong lớp theo cơ chế Spring |
| Trên tham số tiêm | `OrderService(@Lazy InventoryService inv)` | Có thể tạo lazy proxy cho **reference dependency** |
| Trên tham số tiêm với false | `OrderService(@Lazy(false) InventoryService inv)` | Không yêu cầu lazy-resolution proxy tại điểm tiêm đó; **không dùng để đổi bean definition sang eager toàn cục** |

Nếu mục tiêu của bạn là “bean quan trọng phải xuất hiện trong startup”, hãy đặt `@Lazy(false)` trên **class bean hoặc factory method**, không chỉ trên tham số constructor của một bean khác.

**Chú ý về optional dependencies:** lazy-resolution proxy có thể được tạo ngay cả khi target thật chưa tồn tại; lỗi thiếu target chỉ xuất hiện khi proxy được sử dụng. Với dependency tùy chọn, `ObjectProvider<T>` thường giúp biểu đạt tình huống “có hoặc không có” rõ hơn so với mặc định tưởng rằng mọi proxy đều có target.

## 10. Scope, điều kiện tạo bean và thứ tự khởi tạo

`@Lazy(false)` không có khả năng ghi đè mọi cơ chế quản lý vòng đời trong Spring.

### 10.1. Singleton và prototype

Điển hình:

```java
@Component
@Lazy(false)
public class SingletonHealthValidator {
}
```

Với scope singleton mặc định, bean sẽ được xem là non-lazy và được pre-instantiate trong context bình thường.

Nhưng nếu dùng:

```java
@Component
@Scope("prototype")
@Lazy(false)
public class TransientWorker {
}
```

thì **không** có nghĩa Spring phải tạo sẵn mọi prototype. Prototype được tạo theo lần yêu cầu; pre-instantiation của singleton không áp dụng tương tự cho prototype. Tại một thời điểm, có thể còn **chưa có instance prototype** dù bean definition mang `@Lazy(false)`.

Đây là những class minh họa, cần import Spring annotations và dự án phù hợp.

### 10.2. Bean có điều kiện

`@Profile`, `@ConditionalOnProperty` và các cơ chế condition khác quyết định **có đăng ký bean hay không**. `@Lazy(false)` chỉ điều chỉnh khởi tạo khi definition của bean đã tồn tại.

```java
@Component
@Profile("production")
@Lazy(false)
public class ProductionAuditService {
}
```

Nếu profile `production` không active, Spring có thể không đăng ký bean này; `@Lazy(false)` không thể tự khởi tạo thứ mà container không định nghĩa.

### 10.3. @DependsOn và dependency graph

`@DependsOn("otherBean")` giúp yêu cầu một bean khác được khởi tạo trước bean hiện tại, và đặc biệt có thể làm bean lazy `otherBean` bị kéo tạo sớm khi bean non-lazy phụ thuộc vào nó:

```java
@Component
@Lazy(false)
@DependsOn("otherBean")
public class CriticalWorkflow {
}
```

Snippet minh họa cần bean tên `otherBean` và các import tương ứng. `@Lazy(false)` **không tự đặt thứ tự** giữa mọi eager beans; `@DependsOn` mô tả một phụ thuộc khởi tạo cụ thể. Tuy nhiên, nếu có quan hệ nghiệp vụ thật, constructor injection hoặc thiết kế API rõ ràng thường dễ hiểu hơn phụ thuộc bằng chuỗi tên bean.

### 10.4. @PostConstruct và thứ tự

Bean được đánh dấu eager đi qua `@PostConstruct` khi được khởi tạo. Tuy nhiên, **thứ tự giữa nhiều bean không phụ thuộc nhau** có thể thay đổi. Nếu cần công việc phối hợp giữa nhiều service **sau context refresh**, `ApplicationRunner` vẫn thường là vị trí tốt hơn việc chèn một quy trình dài vào `@PostConstruct` của một bean eager.

### 10.5. @Lazy(false) không bắt bean luôn sống mãi

Với singleton chuẩn, bean tồn tại trong context sau khi được tạo, nhưng có thể đóng khi context shutdown. Với scope khác, lifecycle khác. `@Lazy(false)` chỉ liên quan đến **khởi tạo**, không phải hợp đồng đảm bảo service luôn reachable, kết nối luôn khỏe hoặc không bao giờ bị destroy/recreate do cơ chế quản lý ngoài phạm vi.

## 11. Những trường hợp nên chọn ngoại lệ eager

### 11.1. Phát hiện lỗi cấu hình quan trọng ngay khi startup

Một singleton cần kiểm tra cấu hình bất biến:

```java
@Service
@Lazy(false)
public class SigningConfigurationVerifier {

    private final String keyId;

    public SigningConfigurationVerifier(
            @Value("${security.signing-key-id}") String keyId) {
        if (keyId == null || keyId.isBlank()) {
            throw new IllegalArgumentException(
                    "security.signing-key-id must not be blank");
        }
        this.keyId = keyId;
    }
}
```

Đây là snippet tích hợp, cần import `@Service`, `@Lazy`, `@Value` và cấu hình thực tế. Khi key không có, placeholder `@Value` có thể thất bại **trước khi constructor được gọi**; cả hai dạng lỗi đều phản ánh yêu cầu phải có cấu hình lúc startup.

Đừng log giá trị bí mật hoặc private key; đây chỉ là key ID. Trong dự án thực tế, có thể dùng `@ConfigurationProperties` kết hợp validation thích hợp để quản lý tập thuộc tính lớn thay vì dùng nhiều `@Value`.

### 11.2. Bắt buộc xây một bean quản lý tài nguyên

Ví dụ một lớp `@Component @Lazy(false)` khởi tạo bộ nhớ đệm cấu hình nhỏ, validate schema nội bộ hoặc thực hiện bước tạo tài nguyên rất gọn. Nó là ứng viên tốt nếu:

- Việc tạo sớm giúp phát hiện một lỗi **không thể chấp nhận** trước khi phục vụ.
- Chi phí startup có thể dự đoán và được giám sát.
- Logic khởi tạo có timeout/giới hạn tài nguyên phù hợp nếu dùng I/O.
- Không vô tình kéo cả đồ thị service đắt đỏ vào startup.

Không phải cứ là service “quan trọng” thì phải eager. Một service chỉ dùng cho một endpoint hiếm, nhưng không có yêu cầu fail-fast, có thể hưởng lợi từ lazy.

### 11.3. Chọn đúng đối tượng cần eager trong đồ thị dependency

Giả sử một request cần:

```text
OrderController -> OrderService -> ShippingClient -> ExternalAPI
```

Nếu `OrderController` bị buộc khởi tạo sớm và dùng constructor injection trực tiếp, có thể kéo `OrderService` và `ShippingClient` tạo sớm. Ngược lại, chỉ đánh dấu `ShippingClient @Lazy(false)` không có nghĩa đã chạy HTTP request thành công tới external API; constructor có thể chỉ lưu cấu hình. Bạn phải quyết định rõ mình cần:

- **Eager object construction:** dùng `@Lazy(false)`.
- **Functional readiness check:** dùng một bước kiểm tra phù hợp trong runner hoặc health/readiness.
- **First-call warmup:** có thể thiết kế sưởi ấm cache/hot path có kiểm soát, tách khỏi việc chỉ tạo instance.

Tối ưu startup đúng không phải đếm số bean lazy, mà là đảm bảo **các điều kiện phục vụ cần có đã được xác nhận ở đúng mốc**.

## 12. Những trường hợp không nên dùng @Lazy(false) như một giải pháp giả

### 12.1. Muốn hứa rằng toàn ứng dụng “ready”

`@Lazy(false)` trên một bean không tạo `ApplicationReadyEvent`, không tự chạy runner và không đảm bảo readiness probe thành công. Nếu bạn phải kiểm tra toàn bộ dependency trước traffic, cần thiết kế rõ chuỗi startup và readiness chứ không dựa vào một annotation.

### 12.2. Muốn sửa lỗi truy cập bean từ mã quá sớm

Trong `ApplicationStartingEvent`, context thường chưa tồn tại; thêm `@Lazy(false)` vào bean không khiến bean sẵn sàng ở sự kiện này. Annotation chỉ tác động khởi tạo singleton **sau khi bean definitions được load và context đi vào refresh**. Muốn làm việc với `Environment` ở giai đoạn sớm, chọn API bootstrap thích hợp thay vì cố lấy bean.

### 12.3. Muốn khắc phục vòng phụ thuộc constructor

Hai bean A/B constructor-inject lẫn nhau có thể gây circular dependency. `@Lazy(false)` không giải quyết vấn đề này; thậm chí tạo sớm làm lỗi xuất hiện ngay. Cách phù hợp là sửa thiết kế phụ thuộc hoặc tách trách nhiệm. Không nên bật vòng tham chiếu toàn cục chỉ để che lỗi kiến trúc.

### 12.4. Muốn “fix” BeanPostProcessor hoặc AOP proxy

`@Lazy(false)` không thay thế cơ chế `BeanPostProcessor`, proxy hay điều kiện áp dụng `@Transactional`/`@Cacheable`. Bean eager vẫn cần qua đúng vòng đời Spring. Lời gọi `this.method()` trong chính bean vẫn có thể bỏ qua AOP proxy, bất kể eager hay lazy.

### 12.5. Muốn giảm thời gian khởi động bằng cách đặt false ở mọi nơi

`@Lazy(false)` làm các bean được tạo **sớm hơn**, không tự làm startup nhanh hơn. Nếu gắn annotation này rộng khắp, bạn có thể khôi phục gần như toàn bộ chi phí của cách khởi tạo eager mặc định và đánh mất lợi ích global lazy.

### 12.6. Muốn buộc prototype tạo sẵn

Pre-instantiation áp dụng cho **singleton non-lazy**; không có cơ chế tương đương "tạo vô hạn prototype ngay từ đầu". Đừng dùng `@Lazy(false)` như một annotation cấp phát số lượng instance cho prototype, request hoặc session scope.

## 13. Cách chọn ngoại lệ trong dự án thực tế

Một quy trình ra quyết định có căn cứ:

1. **Đo điểm nghẽn thật**: tổng startup, thời gian tới Ready, first-request latency, bean nào tốn thời gian tạo. Đừng giả định lazy luôn là tối ưu.
2. **Liệt kê những điều kiện phải đúng trước traffic**: cấu hình bắt buộc, schema, chứng chỉ, thành phần quan trọng, dữ liệu cần thiết.
3. **Tách "tạo object" và "kiểm tra chức năng"**: tạo bean chỉ xác nhận constructor/DI/init thành công; chưa hẳn kiểm chứng hệ thống ngoài.
4. **Chọn tập eager tối thiểu**: `@Lazy(false)` trên bean definitions thực sự cần tạo trong refresh.
5. **Xem toàn bộ dependency graph**: bean eager có thể kéo các dependency lazy vào startup. Dùng provider/thiết kế tách trách nhiệm nơi hợp lý.
6. **Chạy thử kịch bản thiếu cấu hình**: xem bean cần fail-fast có thực sự thất bại trước Ready không.
7. **Đo lại cold start và first request**: lazy có thể chuyển chi phí từ startup sang request đầu tiên; cả hai đều ảnh hưởng trải nghiệm.
8. **Giám sát sau deploy**: so sánh số lượng bean đã tạo, độ trễ request đầu, lỗi khởi tạo muộn, heap usage và readiness.
9. **Giữ cấu hình dễ hiểu**: comment vì sao một bean được `@Lazy(false)`, tránh copy annotation như công thức trang trí.

Một bảng quyết định ngắn:

| Câu hỏi | Nếu câu trả lời là “có” | Hành động phù hợp |
|---|---|---|
| Bean là singleton và **bản thân instance** phải có khi context refresh? | Có | Cân nhắc `@Lazy(false)` trên định nghĩa |
| Việc cần làm là phối hợp nhiều service sau refresh, trước Ready? | Có | Cân nhắc `ApplicationRunner` |
| Service chỉ dùng trong chức năng ít truy cập? | Có | Cân nhắc để lazy và đo first-call latency |
| Bean có constructor phụ thuộc một service lớn? | Có | Kiểm tra khả năng kéo dependency tạo sớm |
| Bean không được đăng ký vì `@Profile`/`@Conditional`? | Có | Xem lại điều kiện; `@Lazy(false)` không thể tạo bean bị loại |
| Bean có scope prototype/request? | Có | Không suy luận từ pre-instantiation của singleton |
| Cần cache/warmup trong cluster nhiều replica? | Có | Thiết kế idempotency và phân phối trách nhiệm, không chỉ dùng annotation |

## 14. Các lỗi thường gặp và cách kiểm chứng

| Biểu hiện | Nguyên nhân có thể | Phương pháp kiểm tra |
|---|---|---|
| Đặt `@Lazy(false)` nhưng không thấy bean được tạo | Bean nằm ngoài component scan, điều kiện không thỏa hoặc scope không singleton | Kiểm tra bean definition, profile, scope, tên bean và log constructor |
| Đặt `@Lazy(false)` vào method nghiệp vụ | Method không định nghĩa bean | Đặt trên class `@Component` hoặc phương thức `@Bean` |
| Có `@Lazy(false)` nhưng bean khác vẫn được tạo sớm | Bean eager cần dependency hoặc một thành phần chủ động `getBean` | Xem dependency graph/stacktrace tạo bean |
| Có bean definition nhưng `containsSingleton` = false | Definition tồn tại, singleton instance chưa được tạo | Phân biệt `containsBean` và `containsSingleton` |
| Kỳ vọng mọi eager beans chạy theo thứ tự annotation | `@Lazy(false)` không sắp thứ tự | Dùng dependency rõ ràng hoặc `@DependsOn` khi phù hợp |
| Lazy bean lỗi ở request đầu tiên | Validation bị trì hoãn đến lần đầu init | Chọn ngoại lệ eager hoặc thiết kế startup validation |
| Đặt `@Lazy(false)` trên injection point nhưng target vẫn lazy | Annotation tại injection point không đổi lazy flag của bean definition | Đặt annotation ở định nghĩa bean |
| Đánh dấu bean prototype `@Lazy(false)` nhưng không thấy instance sẵn | Prototype tạo theo yêu cầu | Kiểm tra scope và thời điểm `getBean` |
| Tắt global lazy nhưng thấy bean vẫn chưa tạo | Bean có `@Lazy` riêng, có scope khác hoặc definition đặc biệt | Kiểm tra metadata thực tế |
| `@Lazy(false)` làm startup chậm | Bean eager có constructor/DI/init hoặc kéo cả dependency graph | Profile/meter đo thời gian và đối chiếu first-call latency |
| Gắn annotation vào class không được scan | Spring không biết định nghĩa bean | Đăng ký bằng `@ComponentScan`/`@Import`/`@Bean` phù hợp |
| Gọi `getBean` khi đang định “chỉ kiểm tra” bean lazy | Phép kiểm tra vô tình **khởi tạo** bean | Kiểm tra metadata/cache mà không yêu cầu instance |
| Vì bean eager đã tạo nên tưởng HTTP server ready | Bean creation và readiness là hai ranh giới khác | Quan sát `ApplicationReadyEvent`/readiness probe |

### Debug một bean cụ thể mà không vô tình làm nó được tạo

Trong code có `ConfigurableApplicationContext context`:

```java
var factory = context.getBeanFactory();
System.out.println(factory.containsBeanDefinition("onDemandService"));
System.out.println(factory.containsSingleton("onDemandService"));
```

Đây là **đoạn tích hợp**. Hai phương thức trả lời câu hỏi khác nhau:

- `containsBeanDefinition`: bean definition **local** với tên đó có tồn tại không?
- `containsSingleton`: một singleton instance với tên đó **đã đăng ký** trong singleton registry chưa?

Không suy luận `containsSingleton == false` nghĩa là toàn ứng dụng không có bean đó. Nó có thể là bean lazy chờ tạo, prototype hoặc một định nghĩa ở context cha. Ngược lại, `containsBeanDefinition == true` không đảm bảo việc instantiate sẽ thành công.

Tránh gọi `getBeansOfType(...)` hoặc `getBean(...)` chỉ để “xem có bean chưa” nếu mục tiêu đo **chưa được khởi tạo**, vì một số cách lookup có thể kích hoạt việc tạo instance.

## 15. Bài thực hành và câu hỏi kiểm tra

Dùng project phần 7. Mỗi lần chỉ thay đổi một điều, ghi nhận ba mốc: **trước context refresh hoàn thành**, **tại runner** và **sau khi `getBean` lần đầu**.

**Thực hành 1 — ngoại lệ class và factory.** Bật `spring.main.lazy-initialization=true`, chạy dự án. Quan sát `CREATE criticalService` và `CREATE startupPolicy` trước các dòng Runner. Giải thích vì sao thứ tự giữa hai dòng CREATE không bắt buộc cố định.

**Thực hành 2 — giữ một bean lazy.** Xác nhận `Runner: onDemandService before = false`. Gọi `getBean(OnDemandService.class)` và xác nhận constructor chạy rồi `containsSingleton` trở thành `true`.

**Thực hành 3 — tắt global lazy.** Chạy `--spring.main.lazy-initialization=false`. Lúc này `OnDemandService` được tạo trước Runner, trong khi `@Lazy(false)` trên hai ngoại lệ vẫn giữ tác dụng diễn đạt ý định.

**Thực hành 4 — bỏ từng annotation.** Bật lại global lazy, bỏ `@Lazy(false)` ở class CriticalService và chạy; sau đó khôi phục, thử bỏ annotation trên `startupPolicy()`. Quan sát bean nào còn được pre-instantiate. Không dùng kết quả từ một lần chạy để khẳng định thứ tự của mọi hệ thống.

**Thực hành 5 — kéo dependency lazy.** Thêm `RemoteClient` và `StartupValidator` từ phần 8, đặt Validator `@Lazy(false)`. Kiểm tra cả constructor RemoteClient dù RemoteClient không có ngoại lệ eager. Thử thay constructor injection bằng `ObjectProvider` và chỉ lấy object khi cần.

**Thực hành 6 — phân biệt scope.** Tạo một `@Component @Scope("prototype") @Lazy(false)`. Quan sát không có prototype instance tự sinh hàng loạt khi refresh; chỉ tạo instance khi yêu cầu qua `getBean`.

**Thực hành 7 — lỗi cấu hình.** Tạo bean eager có `@PostConstruct` kiểm tra một property giả định, cố ý thiếu property trong môi trường thử. So sánh với bean lazy được gọi lần đầu sau startup. Xác nhận thời điểm phát hiện lỗi khác nhau và đánh giá xem yêu cầu fail-fast của dự án là gì.

**Thực hành 8 — chọn hook đúng.** Giả định ứng dụng phải gọi service sau khi context refresh và trước Ready. Giải thích tại sao dùng `ApplicationRunner` thay vì nhét toàn bộ logic vào constructor của một bean `@Lazy(false)`.

### Câu hỏi tự đánh giá

1. Khi `spring.main.lazy-initialization=true`, tác dụng cụ thể của `@Service @Lazy(false)` là gì?
2. Vì sao `@Lazy` và `@Lazy(false)` có ý nghĩa ngược nhau?
3. Nếu `@Bean` bị `@ConditionalOnProperty` loại khỏi context, `@Lazy(false)` có tạo ra bean không?
4. Vì sao `@Lazy(false)` trên một bean có thể làm nhiều bean khác tạo sớm?
5. `@Lazy(false)` trên constructor parameter có đủ để đánh dấu bean được tiêm là eager toàn cục không?
6. Một bean prototype `@Lazy(false)` được pre-instantiate như singleton không?
7. Vì sao `containsBean` không phải phép đo đáng tin cho “instance đã tồn tại”?
8. Vì sao tăng số bean eager có thể làm startup chậm lại nhưng giảm rủi ro lỗi khởi tạo muộn?
9. Phải dùng runner hay `@Lazy(false)` nếu cần kiểm tra một tập service **sau context refresh**?
10. Làm sao giải thích trường hợp Spring Boot đã Ready nhưng một bean lazy chưa từng được tạo?

## 16. Tổng kết và nguồn tham khảo

**Một câu nhớ lâu:** với global lazy enabled, `@Lazy(false)` là cách **chọn ngoại lệ non-lazy cho một bean definition cụ thể**. Nó làm singleton thông thường được tạo trong giai đoạn context startup, nhưng không ép mọi bean khác giữ lazy, không loại trừ tác động của dependency graph, không override scope/condition và không thay readiness.

Tóm lại, hãy áp dụng ba bước:

1. **Bật lazy khi có lý do đo đạc rõ ràng**: giảm startup nhưng chấp nhận/kiểm soát chi phí first-use.
2. **Chọn bean eager thật sự cần thiết bằng `@Lazy(false)`**: đặt trên class component hoặc phương thức `@Bean` và kiểm tra dependency graph.
3. **Kiểm chứng lifecycle ở runtime**: quan sát constructor/`@PostConstruct` cùng trạng thái singleton; dùng runner/readiness cho điều kiện hệ thống thay vì đồng nhất tạo instance với Ready.

Tài liệu chính thức:

- Spring Boot 3.3 — *SpringApplication / Lazy Initialization* (bao gồm hướng dẫn dùng `@Lazy(false)` để opt out): https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Framework 6.1 — `@Lazy` Javadoc (trên component, `@Bean`, `@Configuration` và injection point): https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Lazy.html
- Spring Framework 6.1 — *Lazy-initialized Beans* (quan hệ lazy và dependency eager): https://docs.spring.io/spring-framework/reference/6.1/core/beans/dependencies/factory-lazy-init.html
- Spring Boot 3.3 — *Application Events and Listeners / Runners* (mốc started/ready): https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html

Không nên dùng `@Lazy(false)` như một “công tắc chung” để sửa mọi lỗi lazy initialization. Giá trị của nó nằm ở việc **nêu tường minh một ngoại lệ có lý do kiến trúc, đúng bean, đúng giai đoạn** và xác minh được bằng hành vi thực tế.