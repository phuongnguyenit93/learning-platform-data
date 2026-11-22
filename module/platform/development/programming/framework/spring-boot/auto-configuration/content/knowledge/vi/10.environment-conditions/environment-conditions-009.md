# @ConditionalOnThreading: cấu hình bean theo mô hình luồng được hỗ trợ

## 1. Mục tiêu và bối cảnh

Từ **Spring Boot 3.2.0**, Spring Boot cung cấp annotation `@ConditionalOnThreading` để một auto-configuration chỉ đăng ký thành phần phù hợp với **mô hình luồng (threading model) đang được kích hoạt**: `Threading.PLATFORM` hoặc `Threading.VIRTUAL`. Đây là một loại *environment condition*: nó dựa vào khả năng của JVM và cấu hình môi trường của ứng dụng khi Spring tạo bean definitions, chứ không phải kiểm tra thread đang thực thi một method bất kỳ.

Một ví dụ thực tế: starter cần cấu hình `ExecutorService` khác nhau khi ứng dụng dùng platform threads và khi dùng virtual threads (Project Loom). Nếu đăng ký cả hai executor một cách vô điều kiện, ứng dụng có thể có các bean trùng vai trò và không rõ bean nào sẽ được inject. `@ConditionalOnThreading` giúp đặt hai cấu hình vào hai nhánh loại trừ nhau.

**Hai kết luận quan trọng:**

1. `Threading.VIRTUAL` chỉ được coi là active khi ứng dụng đang chạy trên **Java 21 trở lên** *và* cấu hình `spring.threads.virtual.enabled=true`. Chỉ có Java 21 mà chưa bật thuộc tính thì chưa đủ.
2. `Threading.PLATFORM` active khi virtual threads *không* được kích hoạt theo quy tắc trên. Vì vậy Java 17 vẫn có thể chạy Spring Boot 3.2/3.5 với nhánh `PLATFORM`; không bắt buộc toàn bộ ứng dụng phải dùng Java 21 chỉ vì API enum tồn tại.

Tên annotation, enum và các điều kiện kể trên cần được đọc theo **phiên bản Spring Boot** sử dụng; API xuất hiện lần đầu ở 3.2.0, không có trong các bản 3.1 trở về trước.

## 2. API và cách khai báo

Trong **Spring Boot 3.2–3.5**, import:

```java
import org.springframework.boot.autoconfigure.condition.ConditionalOnThreading;
import org.springframework.boot.autoconfigure.thread.Threading;
```

Hai cách đặt điều kiện thông dụng:

```java
// Đặt trên phương thức @Bean:
@Bean
@ConditionalOnThreading(Threading.VIRTUAL)
MyVirtualComponent virtualComponent() {
    return new MyVirtualComponent();
}
```

```java
// Đặt trên một lớp cấu hình:
@Configuration(proxyBeanMethods = false)
@ConditionalOnThreading(Threading.PLATFORM)
class PlatformOnlyConfiguration {
    // @Bean bên trong chỉ được xét khi PLATFORM active
}
```

Hai đoạn trên là **mảnh mã minh họa**, chỉ có thể biên dịch khi đã khai báo `MyVirtualComponent`, import `@Bean`/`@Configuration` và đặt vào cấu hình Spring hợp lệ. Ví dụ đầy đủ có thể chạy nằm ở mục 5.

Annotation này có **một thuộc tính bắt buộc** là `Threading value()`. Hai giá trị enum được hỗ trợ là `Threading.PLATFORM` và `Threading.VIRTUAL`; không tồn tại `Threading.AUTO` hoặc `Threading.BOTH`. Phía sau annotation là `OnThreadingCondition`, dùng để đánh giá enum threading được yêu cầu.

**Lưu ý thay đổi API ở Spring Boot 4.0:** `ConditionalOnThreading` vẫn ở gói `org.springframework.boot.autoconfigure.condition`, nhưng enum `Threading` được chuyển sang gói **`org.springframework.boot.thread.Threading`**. Khi nâng phiên bản, sửa import này; đừng sao chép import của ví dụ Spring Boot 3.5 vào dự án Boot 4.0 rồi kết luận annotation đã bị xóa.

## 3. Cách quyết định PLATFORM hay VIRTUAL

Thông tin nền quyết định điều kiện là:

- **Phiên bản JVM đang chạy**: virtual threads được Java chính thức hỗ trợ từ Java 21.
- **Thuộc tính cấu hình**: `spring.threads.virtual.enabled`, mặc định `false`.
- **Enum yêu cầu**: giá trị trong `@ConditionalOnThreading(...)`.

Bảng với Spring Boot 3.2+:

| JVM chạy ứng dụng | `spring.threads.virtual.enabled` | `Threading.VIRTUAL` | `Threading.PLATFORM` |
| --- | --- | --- | --- |
| Java 17 | không khai báo | Không khớp | Khớp |
| Java 17 | `false` | Không khớp | Khớp |
| Java 17 | `true` | Không khớp | Khớp |
| Java 21+ | không khai báo | Không khớp | Khớp |
| Java 21+ | `false` | Không khớp | Khớp |
| Java 21+ | `true` | Khớp | Không khớp |

Hàng "Java 17, property true" cho thấy vì sao không nên thay `@ConditionalOnThreading(Threading.VIRTUAL)` đơn thuần bằng `@ConditionalOnProperty(name="spring.threads.virtual.enabled", havingValue="true")`: điều kiện thuộc tính chỉ đọc key/value và **không tự xác minh khả năng virtual threading của JVM**. Khi cần kiểm tra threading model đang active, hãy dùng condition chuyên biệt.

Spring Boot API cũng cung cấp `Threading.VIRTUAL.isActive(environment)` và `Threading.PLATFORM.isActive(environment)` để đánh giá trạng thái mô hình luồng từ `Environment` theo cùng ngữ nghĩa. Tuy vậy, khi quyết định có đăng ký bean hay không, dùng annotation sẽ diễn đạt ý định rõ hơn.

### Phân biệt ba câu hỏi

1. **Cấu hình nào được kích hoạt?** `@ConditionalOnThreading(Threading.VIRTUAL)` trả lời câu hỏi về cấu hình và khả năng JVM trong giai đoạn Spring xây dựng context.
2. **Bean executor đang dùng loại thread nào?** Phải xem bean thực tế, ví dụ Spring Boot auto-configured `AsyncTaskExecutor` hay `ExecutorService` do ứng dụng định nghĩa.
3. **Task hiện tại có chạy trên virtual thread không?** Java 21 có `Thread.currentThread().isVirtual()`, phải gọi **bên trong task** đang chạy. Đọc ở test thread, web request thread hoặc main thread không thay cho đo ở executor cần kiểm tra.

Cả ba có liên quan nhưng không đồng nhất: bạn vẫn có thể tự tạo một platform-thread executor trong ứng dụng đã bật virtual threads, hoặc dùng virtual-thread executor thủ công trong context mà `Threading.PLATFORM` vẫn active. Điều kiện không ép mọi thread trong JVM chuyển sang cùng một loại.

## 4. Liên hệ với cấu hình mặc định của Spring Boot

Với Java 21+ và:

```properties
spring.threads.virtual.enabled=true
```

Spring Boot có thể tự cấu hình những thành phần tích hợp để dùng virtual threads, tùy vào loại bean hiện có:

- Khi Spring Boot tự cấu hình `AsyncTaskExecutor` cho task execution và không bị cấu hình người dùng thay thế, nhánh virtual dùng `SimpleAsyncTaskExecutor` được thiết lập sử dụng virtual threads; nhánh thường dùng `ThreadPoolTaskExecutor`.
- Với task scheduling, nhánh virtual dùng `SimpleAsyncTaskScheduler` thay cho `ThreadPoolTaskScheduler` khi các điều kiện auto configuration tương ứng được thỏa.
- Các tích hợp cụ thể như một số servlet web server, tác vụ `@Async`, hoặc xử lý bất đồng bộ có thể hưởng lợi khi chúng dùng executor do Boot cấu hình. Không được suy luận rằng **mọi** thư viện, mọi thread và mọi executor tùy biến đều tự đổi mô hình.

Các thuộc tính liên quan pool, ví dụ `spring.task.execution.pool.core-size` hoặc `spring.task.scheduling.pool.size`, **không áp dụng cho executor/scheduler dùng virtual threads theo cơ chế này**. Virtual threads không được điều phối bởi một fixed-size pool virtual-thread thông thường. Đừng chọn kích thước pool làm tiêu chí phân nhánh khi đang bật mô hình virtual.

Ngược lại, `@ConditionalOnThreading` chỉ là **điều kiện đăng ký bean**: bản thân annotation không tạo executor, không sửa application properties, không bật virtual threads và không thay thế `@EnableAsync`/`@EnableScheduling`.

## 5. Ví dụ runnable với Spring Boot 3.5, Java 21 và Maven

Ví dụ sử dụng `@ConditionalOnThreading` để tạo **đúng một** `ExecutorService`. Nhánh `PLATFORM` dùng fixed platform-thread pool, nhánh `VIRTUAL` dùng executor tạo virtual thread cho mỗi task. Ba phép thử xác nhận cả việc **chọn bean** và **loại thread thực sự chạy task**.

Bản minh họa này dùng **Spring Boot 3.5.0** và **JDK 21**. Cần Java 21 để biên dịch `Executors.newVirtualThreadPerTaskExecutor()` và `Thread.isVirtual()`. Đây là yêu cầu của **ví dụ**, không có nghĩa mọi ứng dụng Spring Boot 3.5 đều yêu cầu Java 21.

Cấu trúc thư mục:

```text
threading-condition-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── example/
                └── ThreadingConditionTest.java
```

### Tệp `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>threading-condition-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

### Tệp `src/test/java/example/ThreadingConditionTest.java`

```java
package example;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnThreading;
import org.springframework.boot.autoconfigure.thread.Threading;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

class ThreadingConditionTest {

    @AutoConfiguration
    static class DemoExecutorAutoConfiguration {

        @Bean(destroyMethod = "shutdown")
        @ConditionalOnThreading(Threading.PLATFORM)
        ExecutorService platformExecutor() {
            return Executors.newFixedThreadPool(2);
        }

        @Bean(destroyMethod = "shutdown")
        @ConditionalOnThreading(Threading.VIRTUAL)
        ExecutorService virtualExecutor() {
            return Executors.newVirtualThreadPerTaskExecutor();
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    DemoExecutorAutoConfiguration.class
                            )
                    );

    @Test
    void missingPropertyUsesPlatformThreads() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(ExecutorService.class);
            assertThat(context).hasBean("platformExecutor");
            assertThat(context).doesNotHaveBean("virtualExecutor");

            ExecutorService executor = context.getBean(ExecutorService.class);
            assertThat(isWorkerThreadVirtual(executor)).isFalse();
        });
    }

    @Test
    void explicitFalseUsesPlatformThreads() {
        runner.withPropertyValues("spring.threads.virtual.enabled=false")
                .run(context -> {
                    assertThat(context).hasSingleBean(ExecutorService.class);
                    assertThat(context).hasBean("platformExecutor");
                    assertThat(context).doesNotHaveBean("virtualExecutor");

                    ExecutorService executor =
                            context.getBean(ExecutorService.class);
                    assertThat(isWorkerThreadVirtual(executor)).isFalse();
                });
    }

    @Test
    void enabledOnJava21UsesVirtualThreads() {
        runner.withPropertyValues("spring.threads.virtual.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(ExecutorService.class);
                    assertThat(context).doesNotHaveBean("platformExecutor");
                    assertThat(context).hasBean("virtualExecutor");

                    ExecutorService executor =
                            context.getBean(ExecutorService.class);
                    assertThat(isWorkerThreadVirtual(executor)).isTrue();
                });
    }

    private static boolean isWorkerThreadVirtual(ExecutorService executor) {
        return CompletableFuture.supplyAsync(
                () -> Thread.currentThread().isVirtual(),
                executor
        ).join();
    }
}
```

Chạy trong thư mục `threading-condition-demo`:

```bash
java -version
mvn test
```

Đảm bảo lệnh `java -version` và JDK mà Maven đang dùng đều là Java 21 trở lên. Nếu môi trường có nhiều JDK, kiểm tra thêm `mvn -version` để xác nhận Java runtime thực sự của Maven.

**Kết quả kỳ vọng:** ba JUnit tests thành công, Maven kết thúc `BUILD SUCCESS`. Không có stdout nghiệp vụ cố định, vì mã không gọi `System.out.println`. Báo cáo test nằm trong `target/surefire-reports`.

**Vì sao ví dụ đáng tin:**

1. Các điều kiện được đặt tại chính hai phương thức `@Bean`, mỗi phương thức có kiểu trả về `ExecutorService` nhưng chỉ một condition được thỏa trong một context.
2. `ApplicationContextRunner` tạo các context riêng biệt. `withPropertyValues(...)` thêm property cho từng kịch bản mà không làm nhiễm tình huống còn lại.
3. `hasSingleBean(ExecutorService.class)` xác minh không tạo ra cả hai bean cùng lúc.
4. `isWorkerThreadVirtual` thực sự submit task vào **executor được Spring đăng ký** và hỏi `Thread.currentThread().isVirtual()` ở trong task. Trả lời `true` chỉ khi task đó chạy trên virtual thread.
5. `destroyMethod = "shutdown"` giúp Spring dọn executor khi context kiểm thử đóng. Cách này tránh bỏ lại fixed pool sau test.

**Phân biệt với runtime Java 17:** không thể lấy nguyên tệp trên rồi biên dịch bằng Java 17, vì `newVirtualThreadPerTaskExecutor()` và `Thread.isVirtual()` là API của Java 21. Để minh họa nhánh `PLATFORM` trên Java 17, hãy dùng ví dụ chỉ khai báo API có từ 17 và loại bỏ phương thức tạo virtual-thread executor; điều kiện `Threading.VIRTUAL` tự nó vẫn có thể tồn tại trong Spring Boot 3.2+.

## 6. Cách ứng dụng thật bật hoặc tắt mô hình

### 6.1. Bật qua application.yml

```yaml
spring:
  threads:
    virtual:
      enabled: true
```

Hoặc trong `application.properties`:

```properties
spring.threads.virtual.enabled=true
```

Có thể ghi đè cấu hình bằng tham số chạy ứng dụng:

```bash
java -jar app.jar --spring.threads.virtual.enabled=true
```

Ví dụ `app.jar` là artifact giả định của ứng dụng Spring Boot đã build; đây không phải kết quả từ dự án chỉ chứa test ở mục 5.

### 6.2. Tắt hoặc giữ mặc định

```properties
spring.threads.virtual.enabled=false
```

Nếu không khai báo property thì default là `false`; trên Java 21, Spring Boot vẫn chọn nhánh `PLATFORM`. Chuyển `enabled` từ `false` sang `true` là thay đổi **cấu hình lúc tạo ApplicationContext**. Một bean đã được chọn bằng condition trong context hiện tại không tự biến thành bean khác khi bạn sửa file properties mà không khởi tạo lại context.

### 6.3. Threading model và tính sống còn của tiến trình

Virtual threads là **daemon threads**. Khi một ứng dụng chỉ còn những daemon threads, JVM có thể kết thúc ngay cả khi tác vụ lịch định vẫn cần chạy. Với các ứng dụng dựa chủ yếu vào `@Scheduled`, Spring Boot khuyến nghị cân nhắc:

```properties
spring.threads.virtual.enabled=true
spring.main.keep-alive=true
```

`spring.main.keep-alive` là một quyết định về vòng đời JVM, **không phải** thuộc tính giúp `@ConditionalOnThreading` khớp. Không nên bật một cách máy móc nếu cách chạy ứng dụng đã quản lý vòng đời khác; hiểu nhu cầu của dịch vụ trước khi áp dụng.

## 7. So sánh với các điều kiện thường gặp

| Annotation / kiểm tra | Phép kiểm tra chính | Khi nào nên dùng |
| --- | --- | --- |
| `@ConditionalOnThreading(Threading.VIRTUAL)` | Cấu hình virtual active, kể cả điều kiện Java 21+ | Đăng ký bean theo threading model |
| `@ConditionalOnThreading(Threading.PLATFORM)` | Virtual không active | Cấu hình thay thế cho platform threads |
| `@ConditionalOnProperty(name="spring.threads.virtual.enabled", havingValue="true")` | Giá trị property trên Environment | Khi cố ý chỉ quan tâm key/value, không thay cho kiểm tra khả năng JVM |
| `@ConditionalOnJava(JavaVersion.TWENTY_ONE)` | Runtime Java đạt ngưỡng yêu cầu | Khi cần API của JVM phiên bản cụ thể, không tự yêu cầu property bật virtual |
| `@ConditionalOnBean(ExecutorService.class)` | Bean cùng kiểu có mặt | Khi phụ thuộc vào bean, không suy ra kiểu thread mà executor tạo |
| `Thread.currentThread().isVirtual()` | Loại của chính thread đang gọi | Khi kiểm tra task thật ở runtime; không phải annotation điều kiện |

**Tránh lỗi trong auto configuration:** Nếu chỉ viết `@ConditionalOnJava(JavaVersion.TWENTY_ONE)` thì một ứng dụng chạy Java 21 nhưng chưa bật `spring.threads.virtual.enabled` vẫn có thể khớp. Nếu chỉ viết `@ConditionalOnProperty` thì Java 17 với property bật vẫn có thể khớp. `@ConditionalOnThreading` kết hợp đúng cả hai yếu tố cho khái niệm active threading.

## 8. Quy tắc thiết kế auto configuration theo mô hình luồng

1. **Dùng hai nhánh điều kiện tương hỗ** cho hai kiểu bean có cùng trách nhiệm, hoặc dùng class `@Configuration` riêng cho mỗi nhánh.
2. **Phân biệt một bean bạn tạo với auto-configuration sẵn có của Boot.** Khi định nghĩa bean `Executor`/`ExecutorService` riêng, bạn có thể ảnh hưởng cơ chế back-off của task execution. Nếu mục tiêu chỉ là dùng executor mặc định của Boot, trước tiên hãy xem có cần tự tạo bean không.
3. **Không phụ thuộc vào class concrete một cách vô tình.** Nếu phần còn lại của hệ thống chỉ cần `Executor` hoặc `AsyncTaskExecutor`, đừng inject `ThreadPoolTaskExecutor` khi bật virtual; trong mô hình virtual, Boot có thể cấp một implementation khác.
4. **Xem điều kiện như quyết định ở thời điểm context được tạo.** Nó không hot-swap executor sau khi chạy; việc cấu hình lại động đòi hỏi cơ chế quản lý vòng đời riêng.
5. **Kiểm tra đủ ma trận.** Ít nhất: property thiếu, `false`, `true` trên Java 21+; nếu dự án còn hỗ trợ Java 17, kiểm tra mã tương thích và xử lý fallback ở runtime đó.
6. **Quan tâm tới tải thực tế.** Virtual threads rất hữu ích cho những tác vụ chờ I/O theo mô hình thread per request/task; không làm CPU tự nhanh hơn. Các điểm chặn/pinning, connection pool, giới hạn downstream và backpressure vẫn cần kiểm soát.
7. **Kiểm tra việc đóng tài nguyên.** Với executor tự tạo, dùng shutdown/close có kiểm soát khi context dừng; bean không khớp condition sẽ không tồn tại để dọn.
8. **Di trú theo phiên bản.** Khi chuyển 3.x sang 4.0, kiểm tra import enum `Threading`, phiên bản Java, các auto-configuration liên quan và test; không trộn code Boot 3 với API Boot 4.

## 9. Những ngộ nhận phổ biến và cách sửa

### Sai lầm 1: “Chạy Java 21 là mặc nhiên dùng virtual threads”

**Không.** Java 21 hỗ trợ API, còn Spring Boot chọn mô hình virtual khi `spring.threads.virtual.enabled=true`. Nếu thiếu property, `Threading.PLATFORM` là active.

### Sai lầm 2: “Có property true thì bất kỳ JVM nào cũng dùng virtual threads”

**Không.** Java 17 không có virtual threads chuẩn. `Threading.VIRTUAL` yêu cầu cả JDK 21+ và property bật. Vì thế hãy kiểm tra runtime thực tế, không chỉ file cấu hình.

### Sai lầm 3: “@ConditionalOnThreading tự chuyển thread pool của tôi sang virtual threads”

**Không.** Annotation chỉ quyết định có đăng ký cấu hình hoặc bean. Bạn vẫn phải tạo hoặc lấy đúng executor. Trong ví dụ, virtual threads xuất hiện vì nhánh được chọn **tự gọi** `Executors.newVirtualThreadPerTaskExecutor()`.

### Sai lầm 4: “Nếu tôi bật virtual threads, tất cả các task phải có isVirtual() == true”

**Không.** Một executor tùy biến, thư viện không sử dụng executor mặc định, hay main thread vẫn có thể là platform thread. Kiểm tra tại chính task mà bạn cần đánh giá.

### Sai lầm 5: “Cài đặt pool size sẽ giới hạn số virtual threads giống fixed thread pool”

**Không.** Khi Boot chọn `SimpleAsyncTaskExecutor` hoặc `SimpleAsyncTaskScheduler` cho mô hình virtual, các thuộc tính thread pool tương ứng không hoạt động như với `ThreadPoolTaskExecutor`/`ThreadPoolTaskScheduler`. Hãy dùng các cơ chế giới hạn đồng thời và tài nguyên tương ứng với executor, thư viện và nhu cầu thật.

### Sai lầm 6: “Có thể dùng cùng import Threading cho mọi phiên bản Spring Boot”

**Không.** Boot 3.2–3.5 sử dụng `org.springframework.boot.autoconfigure.thread.Threading`, còn Boot 4.0 sử dụng `org.springframework.boot.thread.Threading`. Luôn đối chiếu Javadoc đúng phiên bản.

### Sai lầm 7: “Một bean bị điều kiện loại bỏ vẫn có thể inject như bình thường”

**Không.** Nếu `@ConditionalOnThreading(Threading.VIRTUAL)` không khớp, bean đánh dấu điều kiện đó không được đăng ký theo nhánh ấy. Mọi dependency bắt buộc cần có bean thay thế ở nhánh platform, hoặc phải điều chỉnh dependency là tùy chọn.

### Sai lầm 8: “Có @ConditionalOnThreading là đủ để tối ưu hóa hiệu năng”

**Không.** Chọn thread model là một quyết định cấu hình, còn hiệu quả phụ thuộc đặc tính công việc, các đoạn blocking, tài nguyên giới hạn và mức độ hỗ trợ của framework. Cần đo throughput, latency và khả năng chịu tải sau khi triển khai.

## 10. Chẩn đoán vì sao condition khớp hoặc không khớp

Khi thấy bean kỳ vọng không xuất hiện, hãy lần lượt kiểm tra:

1. **Phiên bản Spring Boot:** annotation có từ 3.2; nếu build báo không tìm thấy `ConditionalOnThreading`, kiểm tra dependency version.
2. **Đúng import:** enum `Threading` khác gói giữa Boot 3.x và 4.x; tránh chọn nhầm class qua IDE auto-import.
3. **JVM thực tế:** `java -version` và `mvn -version` có thể chỉ đến các JDK khác nhau. Khi chạy container hoặc service, kiểm tra Java runtime bên trong môi trường chạy.
4. **Giá trị property cuối cùng:** cấu hình từ profile, environment variable, CLI arguments hoặc các PropertySource có ưu tiên cao hơn có thể ghi đè file mặc định.
5. **Điều kiện khác cùng bean:** `@ConditionalOnClass`, `@ConditionalOnMissingBean`, auto-configuration order hoặc custom executor có thể tác động độc lập.
6. **Báo cáo condition:** chạy ứng dụng với `--debug` để xem condition evaluation report. Nếu dùng Actuator và đã bật endpoint thích hợp, `/actuator/conditions` cũng giúp xem điều kiện.
7. **Đường thực thi thực tế:** dùng `Thread.currentThread().isVirtual()` trong task, cùng kiểm tra loại `Executor` và nguồn tạo nó; điều này trả lời câu hỏi khác với condition matching.

Ví dụ cấu hình chẩn đoán:

```bash
java -jar app.jar --debug --spring.threads.virtual.enabled=true
```

Dòng trên giả định đã có ứng dụng executable jar. Trong dự án chỉ có các JUnit tests ở mục 5, hãy dùng `mvn test` thay thế.

## 11. Tự kiểm tra kiến thức

**Câu 1.** Ứng dụng chạy Java 21, không có property `spring.threads.virtual.enabled`. Nhánh nào khớp?  
**Đáp án:** `Threading.PLATFORM`.

**Câu 2.** Ứng dụng chạy Java 17, property `spring.threads.virtual.enabled=true`. Có nên chỉ dùng `@ConditionalOnProperty` để đăng ký bean gọi API Java 21?  
**Đáp án:** Không. Property true không chứng minh API virtual thread khả dụng. `Threading.VIRTUAL` không active trên Java 17; nếu code phải *biên dịch* trên Java 17, vẫn cần quản lý source/bytecode và API cho đúng phiên bản.

**Câu 3.** Java 21+ với property true, `@ConditionalOnThreading(Threading.PLATFORM)` có khớp không?  
**Đáp án:** Không; nhánh `VIRTUAL` active.

**Câu 4.** Nếu một bean chỉ tạo khi `Threading.VIRTUAL` active, vậy mọi method trong ứng dụng sẽ chạy trên virtual thread?  
**Đáp án:** Không. Annotation kiểm soát **đăng ký bean**, không thay đổi toàn bộ thread do JVM hoặc các thư viện tạo.

**Câu 5.** Tại sao test nên submit task vào executor thay vì kiểm tra `Thread.currentThread().isVirtual()` ngay trong phương thức `@Test`?  
**Đáp án:** Vì JUnit test method chạy trên thread của test runner, không phải thread mà executor được kiểm tra sử dụng.

**Câu 6.** Import `Threading` khi nâng từ Spring Boot 3.5 lên 4.0 cần thay đổi thế nào?  
**Đáp án:** Từ `org.springframework.boot.autoconfigure.thread.Threading` sang `org.springframework.boot.thread.Threading`; annotation `ConditionalOnThreading` giữ package `org.springframework.boot.autoconfigure.condition`.

## Tài liệu chính thức để tra cứu

- Spring Boot API 3.5 — `@ConditionalOnThreading` (giới thiệu từ 3.2.0): https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnThreading.html
- Spring Boot API 3.5 — `Threading`, giá trị `PLATFORM` và `VIRTUAL`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/thread/Threading.html
- Spring Boot 3.5 Reference — Task Execution and Scheduling: https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html
- Spring Boot 3.5 Reference — SpringApplication, Virtual threads: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
- Spring Boot 4.0 API — `Threading` ở package mới: https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/thread/Threading.html
- Spring Boot 3.2 Release Notes — Support for Virtual Threads và annotation mới: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.2-Release-Notes

**Ghi nhớ:** `@ConditionalOnThreading` lựa chọn cấu hình theo **mô hình luồng active của Spring Boot**, kết hợp hỗ trợ của JVM và `spring.threads.virtual.enabled`. Đây là công cụ để đăng ký bean đúng nhánh; khi cần xác minh task thật chạy ở đâu, hãy kiểm tra executor và `Thread.currentThread().isVirtual()` ngay trong task.
