# `@ConditionalOnNotWebApplication`: chỉ kích hoạt cấu hình khi ứng dụng không có ngữ cảnh web

## 1. Vấn đề cần giải quyết

Một thư viện Spring Boot có thể phục vụ **cả ứng dụng web** (REST API, MVC, WebFlux) và **ứng dụng không có web context** (CLI, tiến trình xử lý dữ liệu, worker, consumer, batch job). Những ứng dụng này có thể chia sẻ nhiều service, nhưng không phải bean nào cũng thích hợp với cả hai môi trường.

Ví dụ, một starter có thể cung cấp `CommandJob` dành riêng cho chương trình chạy bằng dòng lệnh. Nếu bean này được đăng ký trong một REST API, việc cấu hình xử lý theo chế độ CLI có thể không cần thiết, thậm chí tạo hành vi ngoài dự kiến. Spring Boot cung cấp annotation:

```java
import org.springframework.boot.autoconfigure.condition.ConditionalOnNotWebApplication;
```

`@ConditionalOnNotWebApplication` là một **condition trong auto-configuration**: nó chỉ cho phép Spring đăng ký cấu hình hoặc bean khi ứng dụng hiện tại **không được nhận diện là web application context**.

Ý nghĩa quan trọng:

- **Điều kiện đúng (match):** cấu hình/bean có annotation được phép đăng ký khi context không phải Servlet web context hay Reactive web context.
- **Điều kiện sai (no match):** cấu hình/bean có annotation không được đăng ký trong ứng dụng web được nhận diện là Servlet hoặc Reactive.
- Việc đánh giá diễn ra **trong quá trình tạo ApplicationContext và xử lý bean definitions**. Annotation không kiểm tra từng HTTP request và không liên tục thay đổi kết quả sau khi ứng dụng đã khởi động.
- Annotation **chỉ kiểm soát đăng ký**, không tự chạy batch, không tạo lịch chạy tác vụ, không ngăn ứng dụng thực hiện HTTP request **đi ra ngoài**.

Đây là một annotation của **Spring Boot**, nằm ở package `org.springframework.boot.autoconfigure.condition`, không phải annotation cơ bản của Spring Framework.

## 2. “Không có ngữ cảnh web” nghĩa là gì?

### 2.1. Ba kiểu ứng dụng phổ biến

Spring Boot sử dụng `WebApplicationType` để diễn đạt kiểu ứng dụng mà `SpringApplication` tạo ra:

| `WebApplicationType` | ApplicationContext điển hình | Ý nghĩa với `@ConditionalOnNotWebApplication` |
| --- | --- | --- |
| `NONE` | `AnnotationConfigApplicationContext` | **Match**: ứng dụng không vận hành bằng web context |
| `SERVLET` | `AnnotationConfigServletWebServerApplicationContext` | **Không match**: ứng dụng Servlet web |
| `REACTIVE` | `AnnotationConfigReactiveWebServerApplicationContext` | **Không match**: ứng dụng Reactive web |

Tên lớp trong bảng là các loại context điển hình khi chạy ứng dụng Boot thông thường. Trong ứng dụng phức tạp hoặc context tùy chỉnh, điều kiện web của Spring Boot còn xem xét đặc điểm web của `ApplicationContext`/`Environment` (chẳng hạn Servlet `WebApplicationContext` hoặc Reactive `ReactiveWebApplicationContext`). Vì vậy, về mặt khái niệm cần hiểu là **Spring nhận diện context có đặc tính web hay không**, chứ không chỉ so sánh một chuỗi cấu hình.

### 2.2. Classpath và web context không đồng nghĩa

Sự có mặt của một thư viện web trong dependencies có thể ảnh hưởng đến kiểu ứng dụng được Boot suy đoán, nhưng **không có nghĩa ứng dụng bắt buộc phải chạy web**.

Ví dụ, ứng dụng có `spring-boot-starter-web` nhưng khởi động với:

```properties
spring.main.web-application-type=none
```

thì Boot tạo context không phải web và không khởi động embedded HTTP server. `@ConditionalOnNotWebApplication` có thể match dù thư viện Spring MVC/Tomcat vẫn tồn tại trên classpath.

Ngược lại, chỉ **không khai báo `@RestController`** không biến một ứng dụng `SERVLET` thành `NONE`. Nếu ứng dụng vẫn có Servlet web context, điều kiện **không match**.

Cũng cần phân biệt:

- `server.port=0`: ứng dụng web vẫn chạy, chỉ sử dụng **cổng ngẫu nhiên**; điều kiện non-web **không match**.
- `server.port=-1` (trong các cấu hình Boot hỗ trợ): có thể tắt việc lắng nghe HTTP, nhưng **không nhất thiết thay đổi loại ApplicationContext thành non-web**; không nên dùng nó để kích hoạt condition này.
- `spring.main.web-application-type=none`: yêu cầu Boot khởi động ở chế độ non-web, là cách rõ ràng nhất khi muốn giữ web dependencies mà không tạo web context.
- Một CLI vẫn có thể dùng `RestClient`/`WebClient` để gọi API bên ngoài; việc **gửi HTTP request** không tự biến nó thành web server application.

### 2.3. So với các annotation gần nghĩa

| Annotation | Điều kiện được kiểm tra | Dùng khi |
| --- | --- | --- |
| `@ConditionalOnNotWebApplication` | Ứng dụng **không có web context** | Chỉ tạo bean hỗ trợ non-web CLI/worker/batch |
| `@ConditionalOnWebApplication` | Ứng dụng **có web context**; có thể giới hạn `SERVLET` hoặc `REACTIVE` | Bean cho servlet filter, web handler, web-specific integration |
| `@ConditionalOnClass` | Một class có trên classpath | Chỉ cấu hình nếu dependency có mặt |
| `@ConditionalOnProperty` | Thuộc tính cấu hình đáp ứng điều kiện | Bật/tắt tính năng theo cờ cấu hình |
| `@ConditionalOnMissingBean` | Chưa có bean phù hợp được đăng ký | Cho phép ứng dụng **thay thế default bean** |
| `@Profile` | Profile đang hoạt động | Phân chia cấu hình theo môi trường/profile |

`@ConditionalOnNotWebApplication` và `@ConditionalOnClass` không thay thế cho nhau: một annotation kiểm tra **đặc tính runtime context**, annotation còn lại kiểm tra **thư viện**. Nó cũng không cần đối số `type = SERVLET` hay `type = REACTIVE`; khả năng giới hạn kiểu này thuộc `@ConditionalOnWebApplication`, còn `@ConditionalOnNotWebApplication` được thiết kế cho trường hợp **không phải web nói chung**.

## 3. Đặt annotation tại lớp hay tại phương thức `@Bean`?

### 3.1. Điều kiện cấp lớp: toàn bộ nhóm cấu hình chỉ dành cho non-web

```java
@AutoConfiguration
@ConditionalOnNotWebApplication
public class CliJobAutoConfiguration {

    @Bean
    public CommandJob commandJob() {
        return new CommandJob("daily-import");
    }

    @Bean
    public CliJobSettings cliJobSettings() {
        return new CliJobSettings(5);
    }
}
```

Đây là **đoạn minh họa**, giả định hai kiểu `CommandJob` và `CliJobSettings` đã được khai báo. Nếu ứng dụng đang dùng web context, Spring **bỏ qua toàn bộ `CliJobAutoConfiguration`**: cả hai bean đều không được cung cấp từ lớp này.

Chọn cách đặt tại lớp nếu **cả nhóm bean chỉ có ý nghĩa trong chương trình không có web context**.

### 3.2. Điều kiện tại từng `@Bean`: chỉ một bean dành riêng cho non-web

```java
@AutoConfiguration
public class SharedAutoConfiguration {

    @Bean
    @ConditionalOnNotWebApplication
    public CommandJob commandJob() {
        return new CommandJob("daily-import");
    }

    @Bean
    public java.time.Clock applicationClock() {
        return java.time.Clock.systemUTC();
    }
}
```

Đây cũng là **đoạn minh họa** với `CommandJob` đã được khai báo. Trong ứng dụng web, bean `applicationClock` vẫn được cung cấp; chỉ `commandJob` bị bỏ qua. Trong ứng dụng non-web, cả hai đều có thể được đăng ký.

Chọn cách đặt tại phương thức khi cùng một auto-configuration có **bean dùng chung** và **bean chỉ dành cho non-web**. Không đặt điều kiện lên cả lớp nếu cần giữ lại các bean dùng chung.

### 3.3. Kết hợp với cơ chế nhường chỗ

Trong starter dùng chung, ta thường cần đồng thời hai yêu cầu:

1. Chỉ cung cấp default `CommandJob` trong **ứng dụng non-web**.
2. Nếu người dùng đã định nghĩa `CommandJob` riêng, default phải **nhường chỗ**.

Hai annotation giải quyết hai trục khác nhau:

```java
@Bean
@ConditionalOnNotWebApplication
@ConditionalOnMissingBean(CommandJob.class)
public CommandJob commandJob() {
    return new CommandJob("daily-import");
}
```

Bean mặc định chỉ được đăng ký khi **đồng thời** không có web context **và** chưa có bean `CommandJob` phù hợp. Điều kiện non-web không có nghĩa Spring Boot sẽ tự nhường chỗ khi có bean do người dùng khai báo; muốn back-off phải khai báo quy tắc tương ứng.

## 4. Ví dụ Spring Boot 3.3.x / Java 17+ chạy được

Ta xây một chương trình nhỏ có **`spring-boot-starter-web` trên classpath** để so sánh hai cách khởi động trên **chính cùng một JAR**:

- Chạy thông thường: Boot tạo Servlet web context, `@ConditionalOnNotWebApplication` **không match**.
- Chạy với `--spring.main.web-application-type=none`: Boot tạo non-web context, annotation **match**.

Ví dụ đặt `@ConditionalOnNotWebApplication` tại **lớp auto-configuration**, đồng thời đặt `@ConditionalOnMissingBean` tại bean mặc định. Class auto-configuration nằm ngoài package component scan và được đăng ký qua `AutoConfiguration.imports` đúng chuẩn Spring Boot 3.x.

### 4.1. Cấu trúc dự án

```text
non-web-condition-demo/
├── pom.xml
└── src/main/
    ├── java/
    │   └── demo/
    │       ├── api/CommandJob.java
    │       ├── app/DemoApplication.java
    │       └── autoconfigure/CliJobAutoConfiguration.java
    └── resources/
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

### 4.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>non-web-condition-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
```

Dùng `spring-boot-starter-web` **có chủ đích**: nhờ đó, nếu không cấu hình gì thêm, Spring Boot chọn kiểu Servlet web. Mục tiêu là chứng minh condition dựa vào **context đang chạy**, không chỉ có hay thiếu thư viện web.

### 4.3. `src/main/java/demo/api/CommandJob.java`

```java
package demo.api;

public record CommandJob(String name) {

    public String runOnce() {
        return "ran:" + name;
    }
}
```

`CommandJob` là bean minh họa một tác vụ CLI. Phương thức `runOnce()` không chạy tự động khi bean được tạo; `main()` sẽ gọi nó để ví dụ có output xác định.

### 4.4. `src/main/java/demo/autoconfigure/CliJobAutoConfiguration.java`

```java
package demo.autoconfigure;

import demo.api.CommandJob;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnNotWebApplication;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnNotWebApplication
public class CliJobAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CommandJob.class)
    public CommandJob commandJob() {
        return new CommandJob("daily-import");
    }
}
```

**Hai điều kiện có vai trò riêng:**

- Cấp lớp: nếu ứng dụng là web context, toàn bộ auto-configuration bị loại.
- Cấp `@Bean`: trong non-web context, default `CommandJob` chỉ xuất hiện nếu ứng dụng chưa cung cấp một bean cùng kiểu phù hợp.

### 4.5. `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

```text
demo.autoconfigure.CliJobAutoConfiguration
```

Spring Boot 3.x đọc file này để biết danh sách lớp auto-configuration. Dòng trong file phải trùng **fully-qualified class name**. Không đặt `CliJobAutoConfiguration` trong package bị quét bởi `@SpringBootApplication`: auto-configuration nên được nạp bằng imports, để đảm bảo thứ tự và quy tắc áp dụng có thể dự đoán.

### 4.6. `src/main/java/demo/app/DemoApplication.java`

```java
package demo.app;

import demo.api.CommandJob;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(DemoApplication.class, args)) {

            CommandJob job = context.getBeanProvider(CommandJob.class)
                    .getIfAvailable();

            System.out.println("commandJobExists=" + (job != null));

            if (job != null) {
                System.out.println(job.runOnce());
            }
        }
    }
}
```

`main()` kiểm tra sự tồn tại của `CommandJob` rồi gọi tác vụ **chỉ khi bean được đăng ký**. `try-with-resources` đóng context ngay sau khi minh họa xong, vì vậy cả chế độ web có embedded server cũng kết thúc thay vì tiếp tục lắng nghe HTTP.

### 4.7. Build một lần, chạy hai chế độ

Cần có **JDK 17+** và **Maven 3.6+**. Tại thư mục `non-web-condition-demo`, build:

```bash
mvn -q -DskipTests package
```

**Lần A — Servlet web context** (được chọn mặc định do `spring-boot-starter-web`):

```bash
java -jar target/non-web-condition-demo-0.0.1-SNAPSHOT.jar --server.port=0 --spring.main.banner-mode=off --logging.level.root=OFF
```

Dòng output do chương trình in ra:

```text
commandJobExists=false
```

Giải thích: Boot khởi tạo Servlet web context; `CliJobAutoConfiguration` bị loại do `@ConditionalOnNotWebApplication` không match. `--server.port=0` chỉ yêu cầu web server dùng cổng động; **ứng dụng vẫn là ứng dụng web**.

**Lần B — non-web context** (cùng JAR, đổi chế độ khởi động):

```bash
java -jar target/non-web-condition-demo-0.0.1-SNAPSHOT.jar --spring.main.web-application-type=none --spring.main.banner-mode=off --logging.level.root=OFF
```

Dòng output do chương trình in ra:

```text
commandJobExists=true
ran:daily-import
```

Giải thích: `web-application-type=none` khiến Boot sử dụng context không phải web. Điều kiện tại `CliJobAutoConfiguration` match, default `CommandJob` được đăng ký và phương thức `runOnce()` có thể chạy.

**Điều được chứng minh:** hai lần chạy sử dụng **cùng artifact với cùng dependencies** nhưng kết quả condition khác nhau vì **loại ApplicationContext** thay đổi. Đây là điểm khác biệt cốt lõi với điều kiện dựa thuần vào classpath như `@ConditionalOnClass`.

### 4.8. Thử biến thể đặt condition trên `@Bean`

Nếu cấu hình có một bean dùng chung cho cả web và non-web, chuyển `@ConditionalOnNotWebApplication` từ **lớp** xuống đúng phương thức `commandJob()`:

```java
package demo.autoconfigure;

import demo.api.CommandJob;
import java.time.Clock;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnNotWebApplication;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class CliJobAutoConfiguration {

    @Bean
    @ConditionalOnNotWebApplication
    @ConditionalOnMissingBean(CommandJob.class)
    public CommandJob commandJob() {
        return new CommandJob("daily-import");
    }

    @Bean
    public Clock applicationClock() {
        return Clock.systemUTC();
    }
}
```

Đây là **một lớp thay thế hoàn chỉnh** cho `CliJobAutoConfiguration.java` ở ví dụ trên. Sau khi build lại, hai lần chạy vẫn cho các output của `CommandJob` như trước. Khác biệt là `applicationClock` được đăng ký trong **cả hai chế độ** vì chỉ `commandJob()` mang điều kiện non-web.

## 5. Cách áp dụng trong starter/ứng dụng thật

**Tình huống 1 — starter dùng cho batch và REST API.** Thư viện có `SharedClient` dùng chung và `CliJobRunner` chỉ dành cho CLI:

```java
@AutoConfiguration
public class SharedClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    SharedClient sharedClient() {
        return new SharedClient();
    }

    @Bean
    @ConditionalOnNotWebApplication
    @ConditionalOnMissingBean
    CliJobRunner cliJobRunner() {
        return new CliJobRunner();
    }
}
```

*Đoạn này mang tính thiết kế; `SharedClient` và `CliJobRunner` là các kiểu giả định, chưa được định nghĩa trong ví dụ chạy.* Điều kiện phải đặt tại phương thức `cliJobRunner()` để web app vẫn nhận bean `SharedClient`. Nếu gắn annotation lên cả lớp, web app mất luôn client dùng chung.

**Tình huống 2 — toàn bộ cấu hình dành riêng cho worker.** Một nhóm bean như file reader, CLI parser và tác vụ nhập dữ liệu chỉ có ý nghĩa trong non-web context. Đặt `@ConditionalOnNotWebApplication` lên một `@AutoConfiguration` độc lập để giữ ranh giới rõ ràng.

**Tình huống 3 — task cần chạy cả trong REST API.** Không nên sử dụng điều kiện non-web chỉ vì thành phần đó chạy nền hoặc không dùng Servlet API. Scheduled task, queue consumer và batch job **vẫn có thể chạy bên trong ứng dụng web**. Nếu yêu cầu thực sự là bật theo cờ, hãy dùng `@ConditionalOnProperty` (và, nếu cần, `@ConditionalOnMissingBean`) thay cho việc suy ra ý định từ loại web context.

**Tình huống 4 — bắt buộc tách hai điểm khởi chạy.** Một REST API và một worker có thể nằm trong cùng codebase nhưng cần cấu hình/điểm khởi động khác nhau. Có thể dùng `spring.main.web-application-type=none` cho tiến trình worker, nhưng vẫn cần quản lý dependencies, config, các công việc tự chạy và lifecycle rõ ràng. Annotation không tự định nghĩa cấu trúc triển khai hay bảo đảm worker chỉ được chạy một lần.

## 6. Debug khi condition không hoạt động như dự kiến

Khi một bean không xuất hiện, đừng kết luận ngay rằng `@ConditionalOnNotWebApplication` bị lỗi. Kiểm tra theo thứ tự sau:

1. **Xác định context thật sự:** ứng dụng đang chạy `NONE`, `SERVLET` hay `REACTIVE`? Có `spring-boot-starter-web`/`spring-boot-starter-webflux` và có ép `spring.main.web-application-type` không?
2. **Kiểm tra class auto-configuration có được nạp:** đối với starter, tên lớp có đúng trong `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` không? Package auto-configuration có bị component scan nhầm không?
3. **Kiểm tra các điều kiện còn lại:** `@ConditionalOnMissingBean` có thể làm default nhường chỗ; `@ConditionalOnProperty` hoặc `@ConditionalOnClass` có thể không match; tất cả điều kiện áp dụng phải đồng thời thỏa.
4. **Xem Condition Evaluation Report:** thêm `--debug` khi chạy, hoặc bật log liên quan đến auto-configuration. Report cho biết condition nào match/no match và vì sao; thông báo cụ thể phụ thuộc phiên bản Spring Boot.
5. **Kiểm tra mức đặt annotation:** nếu gắn trên lớp, tất cả bean trong lớp phụ thuộc điều kiện. Nếu chỉ gắn trên phương thức, các bean khác của lớp vẫn có thể được đăng ký.
6. **Kiểm tra test context:** một unit test dùng `ApplicationContextRunner` thường tạo non-web context, nên có thể thấy bean xuất hiện, trong khi ứng dụng thực chạy Servlet lại không có. Test cần mô phỏng **đúng loại context**.

Có thể kiểm chứng ma trận theo mục tiêu sau:

| Kịch bản | Kết quả kỳ vọng với default `CommandJob` |
| --- | --- |
| Non-web context, chưa có `CommandJob` người dùng | Có một bean mặc định |
| Non-web context, đã có `CommandJob` người dùng | Không tạo default do `@ConditionalOnMissingBean` |
| Servlet web context, chưa có `CommandJob` người dùng | Không tạo default |
| Reactive web context, chưa có `CommandJob` người dùng | Không tạo default |
| Có Spring MVC trên classpath nhưng ép `web-application-type=none` | Có default nếu không bị condition khác loại |

Trong bộ test auto-configuration, sử dụng `ApplicationContextRunner` cho trường hợp non-web; với web, dùng loại context runner phù hợp như `WebApplicationContextRunner` hoặc `ReactiveWebApplicationContextRunner`. Các test nên kiểm tra cả **sự hiện diện** lẫn **sự vắng mặt** của bean, thay vì chỉ kiểm tra ứng dụng khởi động thành công.

## 7. Các nhầm lẫn thường gặp

**Nhầm 1 — “Không có controller thì là non-web.”** Sai: một web application không cần khai báo controller vẫn có Servlet/Reactive web context. Đặc tính context mới là yếu tố cần xem.

**Nhầm 2 — “Có `spring-boot-starter-web` thì condition luôn false.”** Không nhất thiết: nếu cấu hình `web-application-type=none`, context có thể là non-web dù dependency vẫn hiện diện.

**Nhầm 3 — “Đổi `server.port=0` thành non-web.”** Sai: cổng ngẫu nhiên không làm mất web context. Muốn dùng chế độ non-web hãy đặt `spring.main.web-application-type=none`.

**Nhầm 4 — “Non-web nghĩa là không được gọi HTTP.”** Sai: một worker CLI có thể dùng HTTP client để gọi dịch vụ khác. Điều kiện liên quan đến **ngữ cảnh ứng dụng đóng vai trò web server**, không phải khả năng sử dụng giao thức HTTP.

**Nhầm 5 — “Annotation sẽ tự chạy hoặc chặn job.”** Sai: nó chỉ cho phép/không cho phép Spring **đăng ký bean**. Việc thực thi phụ thuộc `CommandLineRunner`, `ApplicationRunner`, scheduler, listener hoặc lời gọi nghiệp vụ; phải thiết kế riêng lifecycle và tính idempotent của job.

**Nhầm 6 — “Condition loại bean do người dùng tự khai báo.”** Sai: một condition trên auto-configuration chỉ điều khiển cấu hình/bean mang condition; nó không tự xóa bean mà ứng dụng đã khai báo. Muốn cấp default có thể thay thế, kết hợp `@ConditionalOnMissingBean`.

**Nhầm 7 — “Có thể dùng non-web condition để phân biệt Servlet với Reactive.”** Sai: annotation này loại **cả hai loại web**. Nếu muốn cấu hình riêng Servlet hay Reactive, dùng `@ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.SERVLET)` hoặc `REACTIVE` tương ứng.

**Nhầm 8 — “Cứ gắn condition lên cả class cho gọn.”** Nếu lớp còn chứa bean dùng chung, web app sẽ mất cả bean đó. Đặt condition tại `@Bean` để giới hạn chính xác phạm vi.

## 8. Ghi nhớ và câu hỏi tự kiểm tra

- `@ConditionalOnNotWebApplication`: **match trong non-web context**, không match trong Servlet/Reactive web context.
- `spring.main.web-application-type=none` là cách rõ ràng để ép chương trình Boot chạy non-web, kể cả khi có web dependencies.
- Annotation ở **lớp** ảnh hưởng toàn bộ cấu hình; ở **`@Bean`** chỉ ảnh hưởng bean được đánh dấu.
- Đây là điều kiện **đăng ký bean lúc khởi động**, không phải công cụ lên lịch, điều phối job hay kiểm tra HTTP request.
- Khi cung cấp bean mặc định trong starter, thường kết hợp thêm `@ConditionalOnMissingBean` để người dùng thay thế được.

**Tự kiểm tra:**

1. Một ứng dụng có `spring-boot-starter-web`, không có controller, chạy mặc định. `@ConditionalOnNotWebApplication` có match không? **Không**: Boot vẫn tạo Servlet web context.
2. Giữ nguyên JAR đó nhưng thêm `--spring.main.web-application-type=none`. Có match không? **Có**, nếu không có điều kiện khác ngăn cấu hình.
3. Một `@AutoConfiguration` có bean A dùng chung và bean B chỉ dành cho CLI. Đặt điều kiện ở đâu? **Trên `@Bean` tạo B**, để A vẫn hoạt động trong web app.
4. Nếu người dùng đã tạo B riêng, chỉ có `@ConditionalOnNotWebApplication` thì default B có tự nhường chỗ không? **Không**; cần thêm `@ConditionalOnMissingBean` hoặc quy tắc tương đương.

## Tài liệu chính thức

- [Spring Boot 3.3 — Creating Your Own Auto-configuration, Web Application Conditions](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): cách dùng điều kiện web, điều kiện bean và `AutoConfiguration.imports`.
- [Spring Boot 3.3 — WebApplicationType API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/WebApplicationType.html): ý nghĩa của `NONE`, `SERVLET` và `REACTIVE`.
- [Spring Boot 3.3 — ConditionalOnNotWebApplication API](https://docs.spring.io/spring-boot/3.3.13/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnNotWebApplication.html): annotation chỉ match khi ApplicationContext không phải web context.
