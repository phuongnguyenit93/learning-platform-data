# Đăng ký runner bằng @Component hoặc phương thức @Bean trong Spring Boot

## 1. Runner dùng để làm gì?

Trong Spring Boot, **runner** là một bean mà framework gọi một lần trong chuỗi khởi động của mỗi lần `SpringApplication.run(...)` thành công đến giai đoạn gọi runner. Runner rất phù hợp cho những việc cần thực hiện **sau khi `ApplicationContext` đã được refresh** và các phụ thuộc Spring thông thường có thể sử dụng, nhưng **trước mốc `ApplicationReadyEvent`**.

Ví dụ thực tế:

- Kiểm tra dữ liệu hoặc cấu hình bắt buộc bằng một service/repository đã được Spring tạo.
- Nạp một lượng dữ liệu khởi tạo nhỏ hoặc làm nóng cache phải hoàn tất trước khi ứng dụng được coi là ready.
- Nhận tham số dòng lệnh cho công việc xử lý một lần (`--job=import`, tên file, mã vùng).
- Thực hiện một bước kiểm tra kết nối có timeout và báo lỗi rõ ràng nếu ứng dụng chưa đáp ứng điều kiện chạy.

**Hai cách đăng ký runner thường gặp** là khai báo lớp triển khai interface với `@Component`, hoặc khai báo phương thức `@Bean` trả về đối tượng triển khai interface. Cả hai đều đưa runner vào **Spring container**; Spring Boot thu thập các runner bean trong context, sắp xếp nếu có thứ tự và gọi chúng trong startup.

Điểm quan trọng: Spring Boot không yêu cầu tên bean là `runner`, không yêu cầu phải đặt mã runner trong lớp chứa `main` và không tự quét mọi class Java triển khai interface. **Đối tượng phải thực sự được đăng ký là bean trong context đang khởi động.**

## 2. Runner được gọi ở đâu trong chuỗi khởi động?

Dòng thời gian đơn giản của Spring Boot 3.3:

```text
SpringApplication.run(args)
         |
Chuẩn bị Environment và tạo ApplicationContext
         |
Tải cấu hình, tạo bean, refresh context
         |
ApplicationStartedEvent
         |
LivenessState.CORRECT (trình tự mặc định)
         |
+--------------------------------------------+
| Spring Boot tìm các runner bean             |
|  - ApplicationRunner                        |
|  - CommandLineRunner                        |
| Sắp xếp theo order, rồi gọi run(...)        |
+--------------------------------------------+
         |
ApplicationReadyEvent
         |
ReadinessState.ACCEPTING_TRAFFIC (mặc định)
         |
SpringApplication.run(...) trả về context
         |
Ứng dụng tiếp tục chạy hoặc thoát
```

`ApplicationStartedEvent` đến **trước runner**; `ApplicationReadyEvent` đến **sau khi các runner hoàn tất thành công**. Vì thế một runner lỗi có thể khiến ứng dụng không đạt Ready. Dòng log quen thuộc `Started MyApplication in ... seconds` thường phản ánh mốc *started*, **không chứng minh rằng các runner đã chạy xong**.

Đây là ranh giới **lifecycle ứng dụng**, không đồng nghĩa máy chủ Web chắc chắn chưa mở socket. Trong một ứng dụng Servlet/Reactive, Web server có thể đã được khởi tạo trước khi runner chạy. Nếu một runner thực hiện việc quan trọng cho an toàn dữ liệu, cần phối hợp thêm readiness probe và chính sách định tuyến traffic của hạ tầng triển khai; không chỉ tin vào thứ tự log.

Runner được thực thi trong lời gọi bootstrap của `SpringApplication.run(...)`, thông thường trên luồng khởi động và đồng bộ. Một tác vụ runner chờ lâu sẽ kéo dài thời gian đi tới Ready; không phải cơ chế scheduling định kỳ.

## 3. Hai interface: ApplicationRunner và CommandLineRunner

Spring Boot có hai interface đơn giản:

```java
package org.springframework.boot;

// Chữ ký cốt lõi, rút gọn để minh họa:
@FunctionalInterface
public interface ApplicationRunner {
    void run(ApplicationArguments args) throws Exception;
}

@FunctionalInterface
public interface CommandLineRunner {
    void run(String... args) throws Exception;
}
```

Đoạn trên là **sơ đồ chữ ký**, không phải tệp để sao chép vào project: hai interface đã có trong thư viện Spring Boot, và các khai báo thực tế có thể có thêm thông tin API khác.

Sự khác biệt là **kiểu đối số đầu vào**:

| Tiêu chí | `ApplicationRunner` | `CommandLineRunner` |
|---|---|---|
| Phương thức | `run(ApplicationArguments args)` | `run(String... args)` |
| Đọc tham số có tên | `getOptionNames()`, `containsOption()`, `getOptionValues()` | Tự phân tích chuỗi hoặc dùng parser phù hợp |
| Đọc tham số không có tên | `getNonOptionArgs()` | Nhận nguyên chuỗi trong `args` |
| Truy cập đối số gốc | `getSourceArgs()` | Chính mảng `String... args` |
| Thích hợp | Ứng dụng xử lý flags/options như `--name=Lan` | Logic đơn giản hoặc cần nguyên danh sách arguments |
| Khả năng đăng ký | `@Component` hoặc `@Bean` | `@Component` hoặc `@Bean` |

Ví dụ khởi chạy:

```bash
java -jar app.jar --name=Lan --mode=demo file-a.csv
```

Trong `ApplicationRunner`, có thể đọc:

```java
String name = arguments.getOptionValues("name").get(0);
String mode = arguments.getOptionValues("mode").get(0);
String file = arguments.getNonOptionArgs().get(0);
```

Với `CommandLineRunner`, bạn nhận mảng chuỗi tương đương:

```text
[--name=Lan, --mode=demo, file-a.csv]
```

**Đừng ép** `getOptionValues("name").get(0)` trong mã sản xuất mà không kiểm tra option có tồn tại và có giá trị: `getOptionValues` có thể trả `null` khi không có option, hoặc danh sách không có phần tử phù hợp. Ví dụ an toàn sẽ được trình bày ở phần 6.

Lưu ý thêm: các đối số dùng để cấu hình Spring Boot như `--spring.profiles.active=dev` cũng nằm trong arguments của lần chạy, nếu người dùng truyền chúng vào `main`. Vì vậy không đưa toàn bộ arguments ra log sản xuất khi có khả năng chứa mật khẩu, token hoặc dữ liệu nhạy cảm.

## 4. Cách A: đăng ký runner bằng @Component

Đây là cách dễ đọc khi công việc khởi động có trách nhiệm riêng và cần được tổ chức thành một class:

```java
package com.example.runner;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class StartupCheckRunner implements ApplicationRunner {

    private final CatalogService catalogService;

    public StartupCheckRunner(CatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @Override
    public void run(ApplicationArguments arguments) {
        catalogService.checkRequiredData();
    }
}
```

Đoạn trên **minh họa cách triển khai**; `CatalogService` và `checkRequiredData()` phải tồn tại trong project. Spring tạo `StartupCheckRunner` như một bean nhờ `@Component`, tìm dependency `CatalogService`, gọi constructor để tiêm nó, rồi Spring Boot nhận ra bean này triển khai `ApplicationRunner`.

**Điều kiện quan trọng:**

1. Lớp phải nằm trong phạm vi **component scan**, ví dụ cùng package hoặc package con của lớp `@SpringBootApplication` mặc định.
2. Project phải có Spring Boot dependency phù hợp, và startup phải đi qua `SpringApplication.run(...)`.
3. Constructor dependency phải được giải quyết thành công. Nếu bean `CatalogService` thiếu hoặc ambiguous, context có thể không khởi tạo, runner cũng không được gọi.
4. Không cần đánh dấu phương thức `run` bằng `@Bean` hay `@PostConstruct`. Bản thân object là runner bean, còn `run` được Boot gọi đúng giai đoạn.

### 4.1. CommandLineRunner bằng @Component cũng hợp lệ

```java
package com.example.runner;

import java.util.Arrays;

import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

@Component
public class EchoArgumentsRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("Arguments: " + Arrays.toString(args));
    }
}
```

Nếu project chứa đồng thời `StartupCheckRunner` và `EchoArgumentsRunner` như hai bean, **cả hai** đều được Spring Boot gọi trong một lần startup bình thường. Chúng **không phải** hai phương thức đăng ký thay thế tự động triệt tiêu nhau.

### 4.2. Ưu điểm và giới hạn của @Component

- Định nghĩa class rõ ràng; thích hợp nếu logic có nhiều nhánh, cần nhiều dependency và có unit test riêng.
- Constructor injection giúp dependency minh bạch, final fields được khởi tạo đầy đủ.
- Có thể áp dụng `@Profile`, `@ConditionalOnProperty` (nếu điều kiện/phạm vi phù hợp), `@Order` hoặc triển khai `Ordered`.
- Hạn chế là class cần được component scan và được đăng ký đúng một lần; không phù hợp khi class nằm ngoài source hoặc thuộc thư viện không thể sửa annotation.

Không nên dùng `@Component` chỉ để lưu vài dòng lambda nếu việc đó khiến repository có quá nhiều class nhỏ khó theo dõi. `@Bean` thường gọn hơn khi công việc ngắn và thuộc cấu hình của một module.

## 5. Cách B: đăng ký runner bằng phương thức @Bean

Không cần lớp triển khai riêng nếu chỉ muốn một callback nhỏ. Đặt phương thức `@Bean` trong lớp `@Configuration` hoặc `@SpringBootApplication`:

```java
package com.example.runner;

import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class StartupTasksConfiguration {

    @Bean
    CommandLineRunner printStartupMessage() {
        return args -> System.out.println("Startup task executed");
    }
}
```

Khi context được tạo:

1. Spring xử lý `StartupTasksConfiguration`.
2. Spring gọi phương thức bean factory phù hợp và **đăng ký đối tượng lambda** được trả về như một bean kiểu `CommandLineRunner`.
3. Spring Boot tìm thấy bean này trong context.
4. Boot gọi `run(String... args)` của bean **sau khi context refresh và trước Ready**.

**Spring gọi phương thức `@Bean` để tạo bean; Boot gọi `run(...)` khi đến giai đoạn runner.** Hai lời gọi đó khác nhau và không nên lẫn chúng. Với mặc định singleton, phương thức factory được gọi lúc Spring tạo bean, còn callback `run` được gọi một lần trong startup thông thường của context đó.

### 5.1. Tiêm service qua tham số phương thức @Bean

```java
@Configuration
public class StartupTasksConfiguration {

    @Bean
    CommandLineRunner warmup(CacheService cacheService) {
        return args -> cacheService.loadInitialKeys();
    }
}
```

Đây là code **minh họa tích hợp** cần có `CacheService` thật. Spring giải quyết `CacheService` tại thời điểm tạo bean, rồi đối tượng lambda giữ reference này để dùng **khi runner được gọi**.

Không cần gọi:

```java
// Không gọi thủ công trong main:
warmup(cacheService).run(args);
```

Nếu tự gọi `run(...)` rồi vẫn đăng ký runner bean, tác vụ có thể thực hiện **hai lần** (một lần do bạn gọi, một lần do Boot). Ngoài ra, một `@Bean` method trong lớp cấu hình không được thiết kế để nhận tham số tùy tiện từ mã `main` như một Java function thông thường.

### 5.2. @Bean cũng có thể trả ApplicationRunner

```java
@Bean
ApplicationRunner validateArguments() {
    return arguments -> {
        if (arguments.containsOption("mode")) {
            System.out.println(
                    "Mode: " + arguments.getOptionValues("mode"));
        }
    };
}
```

Đây là method thêm vào lớp `@Configuration`; không phải một file Java chạy độc lập. Vì `ApplicationRunner` là functional interface, Java lambda đáp ứng được nó.

### 5.3. Khi nên dùng @Bean

Chọn `@Bean` khi:

- Muốn đặt tác vụ startup ngắn ngay cạnh các bean cấu hình liên quan.
- Cần chuyển một đối tượng thư viện **không thể chỉnh sửa class** thành runner bean.
- Cần tạo runner dựa trên tham số factory, feature flag hoặc các bean khác.
- Muốn kiểm soát việc có tạo bean runner hay không tại cấp phương thức `@Bean`.

Với logic dài, đừng dồn hết nghiệp vụ vào lambda nhiều trăm dòng. Hãy đặt nghiệp vụ trong một service có thể test độc lập, và để lambda đóng vai trò gọi service ở mốc startup.

## 6. Ví dụ hoàn chỉnh: một @Component ApplicationRunner và một @Bean CommandLineRunner

Ví dụ Spring Boot **3.3.x**, **Java 17+**, Gradle Groovy DSL và không cần Web server. Ta chủ động đăng ký **cả hai** runner để chứng minh hai cách đăng ký hoạt động cùng lúc, có thể sắp xếp bằng `Ordered`, và có quyền truy cập Spring service sau khi context refresh.

### 6.1. Cấu trúc project

```text
runner-registration-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/runnerdemo/
    ├── RunnerRegistrationApplication.java
    ├── GreetingService.java
    └── ComponentStartupRunner.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'runner-registration-demo'
```

**`build.gradle`:**

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

Dự án có thể được khởi tạo bằng Spring Initializr với tùy chọn Gradle để nhận sẵn các tệp **Gradle Wrapper**. Nếu tự tạo ba file trên, cần tự cài Gradle hoặc tạo wrapper tương thích trước khi chạy `./gradlew`/`gradlew.bat`. Spring Boot 3.3 yêu cầu Java 17 hoặc mới hơn; ví dụ dùng Java 17.

### 6.2. Service dùng chung

**`src/main/java/com/example/runnerdemo/GreetingService.java`:**

```java
package com.example.runnerdemo;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    public String greet(String name) {
        return "Xin chao " + name;
    }
}
```

`@Service` là một stereotype của Spring component. Vì class ở cùng package với lớp chính, component scan mặc định của `@SpringBootApplication` có thể phát hiện nó.

### 6.3. @Component ApplicationRunner: lấy option có tên

**`src/main/java/com/example/runnerdemo/ComponentStartupRunner.java`:**

```java
package com.example.runnerdemo;

import java.util.List;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.Ordered;
import org.springframework.stereotype.Component;

@Component
public class ComponentStartupRunner implements ApplicationRunner, Ordered {

    private final GreetingService greetingService;

    public ComponentStartupRunner(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @Override
    public int getOrder() {
        return 10;
    }

    @Override
    public void run(ApplicationArguments arguments) {
        List<String> values = arguments.getOptionValues("name");

        String name = (values == null || values.isEmpty())
                ? "ban" : values.get(0);

        System.out.println(
                "1. @Component ApplicationRunner: "
                + greetingService.greet(name));

        System.out.println(
                "1. Option names: " + arguments.getOptionNames());

        System.out.println(
                "1. Non-option args: " + arguments.getNonOptionArgs());

        if (arguments.containsOption("demo.fail")) {
            throw new IllegalStateException("Minh hoa loi runner");
        }
    }
}
```

Điểm cần hiểu:

- `@Component` làm class trở thành runner bean.
- Constructor nhận một `GreetingService` do Spring quản lý; không cần tạo bằng `new`.
- `ApplicationArguments` phân biệt `--name=Lan` với một đối số vị trí như `job-a`.
- `getOptionValues("name")` được kiểm tra `null` và empty trước khi lấy phần tử để có default `ban`.
- `Ordered.getOrder() = 10` yêu cầu thứ tự ưu tiên cao hơn runner có order 20 trong ví dụ.
- `--demo.fail` là tùy chọn thử lỗi cố ý, không phải thuộc tính Spring Boot đặc biệt.

### 6.4. @Bean CommandLineRunner: nhận chuỗi gốc

**`src/main/java/com/example/runnerdemo/RunnerRegistrationApplication.java`:**

```java
package com.example.runnerdemo;

import java.util.Arrays;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.core.Ordered;

@SpringBootApplication
public class RunnerRegistrationApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(RunnerRegistrationApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context =
                application.run(args)) {
            // Context đóng sau khi runner và ReadyEvent hoàn tất.
        }
    }

    @Bean
    CommandLineRunner beanStartupRunner(GreetingService greetingService) {
        return new OrderedBeanStartupRunner(greetingService);
    }

    @EventListener(ApplicationStartedEvent.class)
    public void onStarted() {
        System.out.println("0. ApplicationStartedEvent");
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onReady() {
        System.out.println("3. ApplicationReadyEvent");
    }

    // Implementation chỉ phục vụ bean do @Bean factory tạo.
    static final class OrderedBeanStartupRunner
            implements CommandLineRunner, Ordered {

        private final GreetingService greetingService;

        OrderedBeanStartupRunner(GreetingService greetingService) {
            this.greetingService = greetingService;
        }

        @Override
        public int getOrder() {
            return 20;
        }

        @Override
        public void run(String... args) {
            System.out.println(
                    "2. @Bean CommandLineRunner: "
                    + greetingService.greet("team"));

            System.out.println(
                    "2. Raw args: " + Arrays.toString(args));
        }
    }
}
```

Tại sao cách này phù hợp?

- `@SpringBootApplication` bao gồm cơ chế cấu hình/scan cần thiết. `@Bean` method nằm trong lớp này nên được xử lý như một phương thức factory.
- `beanStartupRunner(GreetingService ...)` nhận bean service qua Spring method-parameter injection.
- Đối tượng trả về triển khai `CommandLineRunner` nên Spring Boot nhận diện là runner.
- Implementation cũng triển khai `Ordered` và trả 20. Nó chạy **sau** runner `@Component` có order 10 trong cùng danh sách đã sắp xếp.
- `@EventListener` trong lớp cấu hình quan sát Started/Ready vì lúc này các listener bean đã được khởi tạo trong context.
- `WebApplicationType.NONE` bảo đảm ví dụ không khởi động HTTP server, không phụ thuộc server port.

**Không cần gọi `new OrderedBeanStartupRunner(...).run(...)` trong `main`.** Nếu làm vậy, bạn bypass cơ chế giải quyết dependency của container và làm tăng nguy cơ chạy tác vụ hai lần.

### 6.5. Chạy và kiểm tra kết quả

Trong project đã có Gradle Wrapper:

```bash
./gradlew bootRun --args='--name=Lan job-a'
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun --args="--name=Lan job-a"
```

Trong stdout có thể có banner/log Spring Boot hoặc Gradle đan xen. **Các dòng do mã nguồn ví dụ tự in** có thứ tự như sau, trong trường hợp arguments được chuyển đúng cho ứng dụng:

```text
0. ApplicationStartedEvent
1. @Component ApplicationRunner: Xin chao Lan
1. Option names: [name]
1. Non-option args: [job-a]
2. @Bean CommandLineRunner: Xin chao team
2. Raw args: [--name=Lan, job-a]
3. ApplicationReadyEvent
```

Đây là kết quả mong đợi đối với **chính ví dụ này** với một option `name` và một đối số vị trí; thứ tự các phần tử trong một tập option names nhiều phần tử không nên dùng làm hợp đồng logging. Với classpath/cấu hình thông thường, các runner được sắp xếp theo `Ordered` và hai sự kiện Started/Ready xuất hiện ở hai phía của runner.

Bạn có thể thử lại không truyền đối số:

```bash
./gradlew bootRun
```

Khi đó `ComponentStartupRunner` dùng fallback `ban`, `Option names` và `Non-option args` là những tập/danh sách trống; `BeanStartupRunner` nhận mảng arguments rỗng.

### 6.6. Chạy nhánh lỗi có chủ đích

```bash
./gradlew bootRun --args='--demo.fail'
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun --args="--demo.fail"
```

Sau khi in các dòng của runner thứ nhất, `ComponentStartupRunner` ném `IllegalStateException`. Trong tình huống này:

1. Context đã refresh và `ApplicationStartedEvent` đã được phát.
2. Runner order 10 bắt đầu và thất bại.
3. Runner order 20 **không được gọi** vì Boot không tiếp tục chuỗi runner sau exception này.
4. `ApplicationReadyEvent` **không được phát** cho lượt startup thất bại.
5. Spring Boot xử lý thất bại startup, ghi exception và có thể phát `ApplicationFailedEvent`; Gradle task thường báo thất bại.

Thứ tự được dự đoán dựa trên `Ordered`, không phụ thuộc việc một bean được khai báo bằng `@Component` và bean còn lại bằng `@Bean`. Lỗi minh họa rõ tác động của một runner không thành công lên toàn bộ startup.

## 7. Chọn @Component hay @Bean trong dự án thật?

| Tiêu chí | `@Component` trên class runner | `@Bean` factory method |
|---|---|---|
| Nơi đăng ký | Trên lớp triển khai `ApplicationRunner`/`CommandLineRunner` | Trong `@Configuration` hoặc `@SpringBootApplication` |
| Cách Spring tạo | Component scan phát hiện và khởi tạo class | Spring xử lý phương thức factory để lấy instance |
| Tổ chức logic | Thường thuận tiện với nhiệm vụ dài/riêng biệt | Gọn với callback ngắn hoặc cấu hình module |
| Dependency injection | Constructor/field/setter theo cách Spring hỗ trợ; nên ưu tiên constructor | Tham số phương thức `@Bean`, hoặc class được trả về có dependency |
| Class ở thư viện không sửa được | Khó dùng `@Component` nếu class không gắn annotation | Có thể xây adapter/trả instance từ factory |
| Bật/tắt theo môi trường | `@Profile`/`@Conditional...` trên class | `@Profile`/`@Conditional...` trên method |
| Thứ tự runner | `@Order` hoặc `Ordered` trên object | `Ordered` của instance trả về hoặc thiết kế class có `@Order` phù hợp |
| Khi nhiều runner cùng tồn tại | Tất cả bean phù hợp đều có thể được gọi | Tất cả bean phù hợp đều có thể được gọi |

**Không có ưu tiên mặc định “`@Component` luôn chạy trước `@Bean`”.** Spring Boot không phân loại thứ tự theo nơi khai báo. Nếu có nhiều runner với phụ thuộc thứ tự, hãy chỉ định thứ tự bằng `Ordered`/`@Order` và kiểm chứng kết quả. Những runner có cùng mức ưu tiên không nên được dùng làm một pipeline phụ thuộc vào thứ tự tình cờ.

Dấu hiệu nên tách lớp `@Component`: runner có nhiều phụ thuộc, cần error handling riêng, nhiều bước xử lý hoặc cần test riêng. Dấu hiệu nên dùng `@Bean`: callback chỉ gọi một service và cấu hình module sẽ rõ ràng hơn khi đặt chung.

Trong nhiều kiến trúc, cách tối ưu là giữ **logic thật ở một service**, còn runner (dù dùng `@Component` hay `@Bean`) chỉ là adapter cho mốc startup.

## 8. Thứ tự nhiều runner: @Order, Ordered và quan hệ phụ thuộc

Spring Boot có thể tìm thấy **nhiều `ApplicationRunner` và `CommandLineRunner`** trong cùng context. Các runner được đưa vào cơ chế sắp xếp, vì vậy hai interface **có thể được sắp xếp chung theo order**, không phải tất cả ApplicationRunner nhất thiết chạy trước mọi CommandLineRunner.

Ví dụ với `@Component`:

```java
@Component
@Order(10)
public class FirstRunner implements ApplicationRunner {
    @Override
    public void run(ApplicationArguments args) {
        System.out.println("First");
    }
}
```

Và:

```java
@Component
@Order(20)
public class SecondRunner implements CommandLineRunner {
    @Override
    public void run(String... args) {
        System.out.println("Second");
    }
}
```

Đây là **hai lớp minh họa**, cần các import Spring Boot/Spring Core tương ứng và đặt chúng trong dự án có component scan. Với các giá trị 10 và 20, runner order 10 được ưu tiên chạy trước order 20. **Order càng nhỏ, độ ưu tiên càng cao**.

Ngoài `@Order`, class có thể triển khai `org.springframework.core.Ordered` như ví dụ phần 6:

```java
@Override
public int getOrder() {
    return 10;
}
```

**Lưu ý với `@Bean` lambda:** nếu bạn muốn thứ tự thật sự ổn định và dễ kiểm chứng, ví dụ phần 6 trả một implementation `Ordered` thay vì dựa vào thứ tự tình cờ của hai phương thức bean factory. Điều quan trọng là bean runner **mà Boot nhận được** có metadata/order thích hợp để bộ sắp xếp dùng.

Không nên dùng order như sự thay thế cho thiết kế dependency. Nếu công việc B **bắt buộc** sử dụng kết quả A, hãy cân nhắc một service điều phối rõ ràng gọi `A` rồi `B` trong **một runner**, thay vì dựa vào hai runner tách rời và chỉ ép thứ tự bằng một con số. Cách này giảm lỗi khi người khác thêm một runner mới hoặc thay đổi điều kiện đăng ký.

## 9. Bật/tắt runner theo profile hoặc thuộc tính

Runner rất dễ thực hiện **ngoài ý muốn** nếu class được quét hoặc method `@Bean` luôn có hiệu lực. Đối với tác vụ import dữ liệu, làm mới chỉ mục hoặc bảo trì, nên quy định rõ khi nào runner tồn tại.

### 9.1. @Profile cho runner class

```java
@Component
@Profile("seed")
public class SeedDataRunner implements ApplicationRunner {
    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Seed mode");
    }
}
```

Đây là lớp minh họa, cần import và project phù hợp. Chỉ khi profile `seed` active thì component này mới được Spring tạo thành bean. Một cách bật profile lúc chạy:

```bash
./gradlew bootRun --args='--spring.profiles.active=seed'
```

Lưu ý: profile cũng tác động những bean khác có điều kiện theo profile, không chỉ runner. Không dùng profile toàn cục nếu nhu cầu thực tế chỉ là một feature flag nhỏ và không muốn thay đổi nhiều cấu hình môi trường.

### 9.2. @ConditionalOnProperty trên phương thức @Bean

```java
@Configuration
public class OptionalStartupConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "demo",
            name = "startup-check-enabled",
            havingValue = "true")
    CommandLineRunner optionalCheck(HealthCheckService healthCheckService) {
        return args -> healthCheckService.verify();
    }
}
```

Đây là đoạn **minh họa tích hợp**: cần `HealthCheckService` có thật và import `@Configuration`, `@Bean`, `@ConditionalOnProperty` và `CommandLineRunner`. Khi thuộc tính `demo.startup-check-enabled=true`, Spring tạo runner bean; khi false hoặc vắng mặt (với điều kiện mặc định), runner này không được đăng ký. Để bật khi chạy:

```bash
./gradlew bootRun --args='--demo.startup-check-enabled=true'
```

**Khác biệt giữa “không đăng ký runner” và “runner tồn tại nhưng tự bỏ qua”:** với `@ConditionalOnProperty`, BeanDefinition có thể bị bỏ qua theo điều kiện, runner không có trong danh sách Boot gọi. Nếu runner luôn có mặt và trong `run` kiểm tra một flag, mọi dependency của runner có thể đã được tạo dù flag false. Chọn đúng cách tùy chi phí khởi tạo và ý nghĩa điều kiện.

### 9.3. Cẩn trọng với tên property

Không nhầm thuộc tính `spring.main.web-application-type` (kiểu Web) với flag do ứng dụng tự định nghĩa như `demo.startup-check-enabled`. Flag riêng chỉ có tác dụng nếu code cấu hình đọc/áp dụng nó. Dùng một tên có tiền tố riêng và ghi rõ default giúp người vận hành tránh kích hoạt tác vụ không chủ ý.

## 10. Runner và vòng đời bean: những mốc không thay thế nhau

So sánh các điểm thường gặp:

| Cơ chế | Khi chạy | Có service đã tiêm? | Dùng để |
|---|---|---|---|
| `@PostConstruct` | Trong giai đoạn khởi tạo **chính bean đó** | Dependency của bean thường đã được tiêm | Chuẩn bị trạng thái nội bộ của bean |
| `SmartInitializingSingleton.afterSingletonsInstantiated()` | Sau khi các non-lazy singleton được tạo trong chu kỳ khởi tạo tương ứng | Các singleton non-lazy cơ bản đã khởi tạo | Phối hợp một số việc sau khi tạo singleton, không tự động là Ready |
| `ApplicationStartedEvent` | Sau refresh, **trước runner** | Context đã refresh; bean bình thường có thể dùng | Quan sát mốc started |
| `ApplicationRunner` / `CommandLineRunner` | Sau Started, trước Ready | Có thể dùng bean thông thường | Khởi tạo/kiểm tra phải hoàn tất trước Ready |
| `ApplicationReadyEvent` | Sau runner | Có thể dùng bean đã tạo | Quan sát mốc hoàn tất chuỗi startup, thông báo hoạt động |
| `@Scheduled` | Theo lịch sau khi hạ tầng scheduling được cấu hình | Có bean do Spring quản lý | Tác vụ **lặp theo lịch**, không phải chỉ chạy một lần trong startup |

Một class runner có thể có `@PostConstruct`. Khi ấy:

1. Spring tạo instance runner.
2. Chạy `@PostConstruct` trong vòng đời bean.
3. Sau khi context refresh, Boot gọi `runner.run(...)`.
4. Nếu tất cả runner xong, Boot tiến tới Ready.

Không nên để `@PostConstruct` tự gọi `run(...)`. Làm vậy có thể lặp nghiệp vụ, thiếu arguments hoặc chạy ở thời điểm không thích hợp.

### Một trường hợp đặc biệt: lazy initialization

Với lazy bean, không phải mọi bean ứng dụng đều đã được khởi tạo trước `ApplicationStartedEvent`. Tuy nhiên một runner bean phải được container tạo trước khi Boot có thể gọi `run` của nó; các dependency cần thiết sẽ được giải quyết theo quy tắc container. Vì vậy runner dùng service trong ví dụ có thể hoạt động, nhưng không nên suy luận rằng **mọi bean lazy của toàn ứng dụng** đều đã tồn tại.

## 11. Runner, Web server và readiness trong triển khai

Tài liệu Spring Boot mô tả runner như công cụ cho tác vụ chạy sau khi ứng dụng đã started và trước khi hệ thống sẵn sàng phục vụ traffic. Cần hiểu đúng trong thực tiễn:

- Servlet hoặc Reactive Web server có thể được khởi tạo và bắt đầu lắng nghe cổng **trước** khi runner hoàn thành.
- `ApplicationReadyEvent` đánh dấu mốc sau runners; sau đó Spring Boot phát trạng thái `ReadinessState.ACCEPTING_TRAFFIC` trong luồng mặc định.
- Một load balancer hoặc Kubernetes có thể dựa vào readiness probe để quyết định khi nào gửi traffic; nhưng phụ thuộc cấu hình probe, không chỉ phụ thuộc sự kiện Spring Boot.
- Runner chạy chậm có thể kéo dài thời gian startup vượt giới hạn của orchestrator. Khi tác vụ dài, cần cân nhắc tách sang Job riêng, migration tool, background worker, hoặc thiết kế không bắt toàn ứng dụng chờ.

Ví dụ: nạp 50.000 dòng dữ liệu từ service ngoài trong một runner ngay lúc mọi replica khởi động có thể tạo bão tải lên database. Cách làm an toàn hơn có thể là chạy migration/seed một lần có kiểm soát, dùng idempotency và phân quyền phù hợp, rồi để các replica khởi động nhanh.

**Runner không phải một khóa phân tán.** Khi có ba replicas, mỗi instance `SpringApplication.run(...)` sẽ gọi runner bean của chính instance đó. Nếu runner thay đổi dữ liệu dùng chung, phải xem xét xung đột và tính lặp lại giữa các instance.

## 12. Xử lý lỗi runner đúng cách

`run(...)` trong hai interface cho phép ném `Exception`. Nếu runner ném lỗi không được xử lý, Spring Boot xem đó là lỗi trong chuỗi startup và có thể đóng context/ghi nhận startup failure. Do đó việc thất bại sẽ ngăn Ready của lần chạy đó.

Cân nhắc phân loại:

- **Lỗi không thể chấp nhận để phục vụ:** thiếu cấu hình bắt buộc, schema không tương thích, dữ liệu khởi tạo quan trọng không có. Có thể chủ động **fail fast** với exception rõ ràng.
- **Lỗi tạm thời:** network timeout, service khác chưa sẵn sàng. Nếu cần retry, phải có giới hạn thời gian, backoff và xử lý ngắt; không retry vô hạn trong runner.
- **Công việc tùy chọn:** làm nóng cache không bắt buộc. Có thể ghi log cảnh báo và tiếp tục, nhưng phải rõ ảnh hưởng và không nuốt lỗi dữ liệu quan trọng.

Ví dụ fail-fast trong `ApplicationRunner`:

```java
@Override
public void run(ApplicationArguments args) throws Exception {
    if (!requiredDataExists()) {
        throw new IllegalStateException(
                "Du lieu bat buoc khong ton tai");
    }
}
```

Đây là **đoạn minh họa**, cần phương thức `requiredDataExists()` thật trong lớp runner. Đừng sao chép vào chương trình thiếu phương thức này mà gọi đó là mã runnable hoàn chỉnh.

### Tính lặp lại (idempotency) khi restart

Runner không phải một migration/versioning system. Nếu ghi dữ liệu khi startup, hãy đảm bảo chạy lại sau restart không nhân đôi bản ghi hoặc phá trạng thái. Chẳng hạn, tạo seed data bằng kiểm tra khóa duy nhất, upsert hợp lệ hoặc công cụ migration chuyên dụng tùy mục đích.

Khi deploy rolling update, có thể có nhiều instance phiên bản cũ và mới cùng chạy. Một runner thay đổi schema ở từng instance có thể gây cạnh tranh; nên tách trách nhiệm migration khỏi startup thường ngày nếu nó có rủi ro.

### Tác vụ quá dài

Không đặt một vòng lặp vô hạn trong `CommandLineRunner` của Web service rồi chờ Ready, vì toàn bộ chuỗi startup có thể không kết thúc. Nếu ứng dụng là batch xử lý một lần, dùng `WebApplicationType.NONE` và một runner đồng bộ là phù hợp; nếu là service cần chạy dài, cân nhắc hạ tầng scheduling/message consumer/lifecycle thích hợp.

## 13. Những lỗi phổ biến khi đăng ký runner

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra hoặc sửa |
|---|---|---|
| Class triển khai `ApplicationRunner` nhưng không chạy | Không có `@Component`, không được component scan, không có `@Bean` hoặc bị điều kiện vô hiệu | Kiểm tra bean thực sự được đăng ký trong context |
| Dùng `@Component` nhưng ứng dụng không khởi tạo | Runner cần một dependency không tồn tại hoặc có nhiều bean trùng type | Đọc nguyên nhân gốc của exception dependency injection |
| Phương thức `@Bean` trả `void` nên không thành runner | Không trả về instance triển khai runner | Định nghĩa bean có kiểu `CommandLineRunner`/`ApplicationRunner` và trả instance hợp lệ |
| `@Bean` method tạo lambda nhưng không thấy log | Class `@Configuration` không được import/scan hoặc điều kiện không thỏa | Kiểm tra cấu hình chứa phương thức và active profiles |
| Task chạy hai lần | Có runner `@Component` lẫn `@Bean` cùng chức năng, hoặc gọi thủ công `run` | Chỉ giữ một đăng ký cho cùng nhiệm vụ, tránh tự gọi callback |
| Muốn A trước B nhưng thấy đảo thứ tự | Không chỉ định order hoặc cùng order | Dùng `@Order`/`Ordered`, hoặc gộp thành một runner điều phối |
| Đọc `--name=Lan` trực tiếp như positional argument | Nhầm phân tích đối số của `CommandLineRunner` và `ApplicationRunner` | Dùng `ApplicationArguments.getOptionValues("name")` khi cần option |
| `getOptionValues("name").get(0)` báo lỗi | Option thiếu hoặc không có giá trị | Kiểm tra `null` và danh sách rỗng trước khi lấy |
| Ứng dụng log `Started` rồi không có Ready | Runner ném exception hoặc vẫn đang chạy | Kiểm tra runner log, stack trace, thời gian chờ và timeout |
| Web server trả HTTP khi runner chưa xong | Socket mở trước sự kiện Ready | Dùng readiness probe và cơ chế routing phù hợp |
| Restart làm tạo dữ liệu trùng | Runner ghi dữ liệu không idempotent | Thiết kế thao tác an toàn khi chạy nhiều lần và nhiều instance |
| Dùng `@PostConstruct` thay runner để gọi nhiều service | Hook của từng bean chạy trước mốc toàn context, khó phối hợp | Dùng runner cho nghiệp vụ cần context đã refresh |
| Cố dùng runner như scheduler | Runner chạy trong startup, không phải mỗi phút/mỗi giờ | Dùng `@Scheduled` khi thật sự cần chạy định kỳ |
| Cố dùng `@Bean` trên phương thức `run` | Nhầm bean factory với runner callback | Khai báo `@Bean` method **trả về** runner, không chú thích trực tiếp lên `run` |
| Thêm `@Order` cho lớp cấu hình nhưng thứ tự runner vẫn không như ý | Đã sắp xếp nhầm đối tượng/metadata | Đặt order trên runner bean/instance thực sự và kiểm chứng bằng log |

Không nên kết luận “`@Bean` không hoạt động” chỉ vì chưa thấy log runner nếu thực tế ứng dụng **thất bại trước giai đoạn gọi runner**. Hãy xác định context có refresh thành công không, Started có phát không, bean có tồn tại không, và lỗi nào xuất hiện trước.

## 14. Kiểm chứng bằng bài thực hành

### Bài A — xác nhận cả hai cách đăng ký

Chạy project phần 6 với `--name=Lan job-a`. Xác nhận:

1. `ApplicationStartedEvent` xuất hiện trước cả hai runner.
2. `@Component ApplicationRunner` đọc được option `name` và positional `job-a`.
3. `@Bean CommandLineRunner` nhận mảng arguments gốc.
4. `@Component` order 10 chạy trước `@Bean` order 20.
5. `ApplicationReadyEvent` xuất hiện sau hai runner.

### Bài B — bỏ @Component, kiểm tra bean discovery

Tạm xóa `@Component` khỏi `ComponentStartupRunner`, chạy lại. Class vẫn biên dịch, nhưng không được đăng ký thành runner bởi component scan; `@Bean CommandLineRunner` vẫn tồn tại và được gọi. Khôi phục annotation sau khi quan sát.

### Bài C — bỏ phương thức @Bean

Tạm bỏ `@Bean` khỏi phương thức `beanStartupRunner(...)` hoặc bỏ hẳn phương thức này khi thực hành (tránh để lại dependency vô tình). Khi chạy, `ComponentStartupRunner` vẫn hoạt động; bean thứ hai không còn được Spring Boot tự gọi. Khôi phục cấu hình sau thử nghiệm.

### Bài D — đổi thứ tự

Đổi `getOrder()` của `ComponentStartupRunner` từ 10 thành 30 và giữ `OrderedBeanStartupRunner` là 20. Quan sát các dòng runner đổi thứ tự, trong khi Started vẫn ở trước và Ready vẫn ở sau. Không đổi order cùng lúc với thay đổi logic để dễ xác định nguyên nhân.

### Bài E — lỗi startup ngăn Ready

Chạy `--demo.fail` theo phần 6. Kiểm tra exception xuất phát từ runner, runner order 20 không được gọi và `ApplicationReadyEvent` không xuất hiện. Giải thích vì sao việc thất bại sau `ApplicationStartedEvent` vẫn là lỗi startup.

### Bài F — đưa runner vào profile tùy chọn

Chuyển một runner thử nghiệm sang profile `seed`. Chạy lần lượt với và không với `--spring.profiles.active=seed`. Quan sát bean có/không được đăng ký. Trước khi dùng trong môi trường thật, xác định rõ dữ liệu mà runner sẽ ghi và điều kiện chạy lại.

### Bài G — thêm thời gian đo

Bổ sung một công việc đồng bộ có thời gian đo bằng `System.nanoTime()` trong một runner. So sánh mốc `ApplicationStartedEvent` và `ApplicationReadyEvent` để xác định runner kéo dài thời gian tới Ready. Không dùng số giây `Started ... in` như bằng chứng runner đã xong.

### Câu hỏi tự đánh giá

1. Vì sao hai class cùng triển khai `CommandLineRunner` nhưng chỉ class được đăng ký thành bean mới chạy?
2. Điểm khác nhau giữa Spring gọi phương thức factory `@Bean` và Spring Boot gọi `runner.run(...)` là gì?
3. `@Component ApplicationRunner` và `@Bean CommandLineRunner` có thể cùng hoạt động trong một context không?
4. Làm sao đảm bảo thứ tự giữa hai runner? Thứ tự mặc định có phải dựa vào `@Component` so với `@Bean` không?
5. Nếu cần đọc `--name=Lan`, nên chọn interface nào và cần kiểm tra trường hợp thiếu option ra sao?
6. Vì sao runner là một nơi hợp lý cho kiểm tra trước Ready, nhưng không phải scheduler?
7. Vì sao runner có side effect cần được thiết kế idempotent khi restart hoặc chạy nhiều replicas?

Trả lời được các câu hỏi này và chứng minh bằng log ở dự án thực hành nghĩa là bạn đã hiểu cả **cách đăng ký** lẫn **hợp đồng vòng đời** của runner.

## 15. Tóm tắt lựa chọn

**Chọn `@Component`** nếu muốn một class runner riêng, dễ unit test, có constructor injection rõ ràng. **Chọn `@Bean`** khi muốn một callback ngắn gọn hoặc muốn tạo runner từ cấu hình/module hiện có. Hai cách **cùng đưa một instance triển khai `ApplicationRunner` hoặc `CommandLineRunner` vào container** và không có ưu tiên tuyệt đối theo cách khai báo.

Khi có nhiều runner, dùng `Ordered`/`@Order` để nói rõ thứ tự, hoặc gom nghiệp vụ có phụ thuộc chặt thành một runner điều phối. Khi runner lỗi, chuỗi startup có thể dừng trước Ready. Vì thế cần cân nhắc timeout, bảo mật arguments, idempotency và khả năng nhiều instance cùng khởi động.

## Tài liệu chính thức để đối chiếu

- Spring Boot 3.3, `SpringApplication`, mục *Using the ApplicationRunner or CommandLineRunner*: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3, `ApplicationRunner` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationRunner.html
- Spring Boot 3.3, `CommandLineRunner` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/CommandLineRunner.html
- Spring Boot 3.3, `ApplicationArguments` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationArguments.html
- Spring Framework, `@Bean` và `@Configuration`: https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html

**Kết luận kỹ thuật:** runner là **bean startup** được Spring Boot gọi sau khi context đã refresh và trước khi application ready. `@Component` và `@Bean` chỉ khác **cách đưa runner vào container**; còn thời điểm và điều kiện Boot gọi runner phụ thuộc vào interface, thứ tự được cấu hình và thành công của startup.