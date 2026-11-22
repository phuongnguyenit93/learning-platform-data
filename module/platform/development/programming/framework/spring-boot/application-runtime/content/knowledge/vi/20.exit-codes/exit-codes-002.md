# SpringApplication.exit và giá trị mã thoát trả về trong Spring Boot

## 1. Mã thoát là gì và vì sao ứng dụng cần nó?

Khi một tiến trình Java kết thúc, hệ điều hành và chương trình đã khởi chạy nó có thể nhận một **mã kết thúc** (*process exit status*). Theo quy ước phổ biến, **0** biểu thị thành công, còn **giá trị khác 0** biểu thị một trạng thái cần chú ý hoặc thất bại theo contract của ứng dụng.

Đối với một chương trình Spring Boot dùng để chạy lệnh CLI, batch import, tác vụ định kỳ hoặc worker theo từng lần chạy, mã thoát giúp:

- Shell script biết có nên tiếp tục bước tiếp theo.
- CI/CD job đánh dấu thành công/thất bại.
- Kubernetes Job xác định container đã hoàn tất thành công hay chưa.
- Scheduler/batch orchestrator phân biệt các loại lỗi.
- Công cụ giám sát và người vận hành biết kết quả cuối cùng của một tiến trình.

Spring Boot cung cấp phương thức:

```java
int code = SpringApplication.exit(context);
```

Tuy nhiên, **hai việc thường bị nhầm là khác nhau**:

1. `SpringApplication.exit(context)`: cho ứng dụng **đóng `ApplicationContext` nếu có thể**, tính toán **mã thoát kiểu `int`** từ các nguồn được hỗ trợ, rồi **trả mã về cho code Java đang gọi**.
2. `System.exit(code)`: yêu cầu **JVM chấm dứt với mã thoát được cung cấp**, để tiến trình cha/hệ điều hành quan sát được trạng thái đó.

Vì vậy:

```java
int code = SpringApplication.exit(context);
```

**không tự động tương đương**:

```java
System.exit(SpringApplication.exit(context));
```

Trong đoạn đầu, Java nhận một biến `int` và có thể tiếp tục chạy những dòng sau. Trong đoạn thứ hai, sau khi Spring xử lý exit và trả code, `System.exit` chủ động yêu cầu JVM kết thúc. Điều này quan trọng khi dùng trong test, thư viện, HTTP service hoặc chương trình có tài nguyên cần cleanup.

Bài học theo **Spring Boot 3.3.x, Spring Framework 6.1.x, Java 17+**. Ta sẽ làm rõ API, nguồn sinh mã, thứ tự generator, cơ chế shutdown, các loại lỗi, ví dụ runnable, cách kiểm tra exit status ở shell và những anti-pattern cần tránh.

## 2. Ba khái niệm phải tách biệt

| Khái niệm | API/hành vi | Ý nghĩa |
| --- | --- | --- |
| Đóng bean container | `ConfigurableApplicationContext.close()` | Dừng Spring context, chạy lifecycle/destroy callbacks; không trả mã thoát nghiệp vụ |
| Tính mã thoát và đóng context | `SpringApplication.exit(context, generators...)` | Trả về `int`, thu thập `ExitCodeGenerator`, cố đóng context |
| Kết thúc JVM có mã thoát | `System.exit(code)` | Yêu cầu JVM chấm dứt với mã gửi cho hệ điều hành |

Ví dụ:

```text
SpringApplication.run(...)
      |
      v
ConfigurableApplicationContext đang active
      |
      +--> SpringApplication.exit(context)
      |          |
      |          +--> Lấy ExitCodeGenerator beans
      |          +--> Kết hợp generators truyền trực tiếp
      |          +--> Xác định mã đầu tiên khác 0 theo thứ tự
      |          +--> Đóng ApplicationContext nếu có thể
      |          +--> return int code
      |
      +--> Java main có thể xử lý code
                 |
                 +--> In log, test, trả status nội bộ
                 |
                 +--> System.exit(code) nếu thực sự muốn JVM kết thúc
```

Sơ đồ mô tả ý nghĩa API, không phải stack trace từng method nội bộ. Thứ tự xử lý lỗi, publish event và destroy callbacks thuộc implementation; contract công khai quan trọng là **trả code** và **đóng context nếu có thể**.

### 2.1. Kết thúc context chưa chắc đồng nghĩa kết thúc tiến trình

Một ứng dụng non-web đơn giản, sau khi context đóng, có thể không còn luồng non-daemon nào giữ JVM nên tiến trình tự kết thúc khi `main` return. Nhưng đó là do **quy tắc sống/chết của các Java threads**, không phải `SpringApplication.exit` đã gọi `System.exit`.

Nếu code của bạn tạo `ExecutorService` không shutdown hoặc một thư viện giữ non-daemon thread ngoài Spring, context đóng chưa chắc JVM đã kết thúc. Ngược lại, gọi `System.exit` một cách đột ngột có thể kết thúc JVM dù vẫn còn tác vụ chưa được xử lý an toàn.

### 2.2. Mã trả về bằng 0 không phải bằng chứng toàn bộ hạ tầng khỏe

Mã `0` có thể chỉ có nghĩa ứng dụng **không có `ExitCodeGenerator` báo lỗi**. Nó không chứng minh:

- Mọi request trong lịch sử đều thành công.
- Không có background task bị thất bại nhưng không được ghi nhận.
- Mọi dữ liệu đã được commit hoặc gửi thành công.
- Tất cả callback cleanup đều thành công.
- Ứng dụng web đang ready trước khi nó dừng.

Phải thiết kế **quy tắc tính mã dựa trên kết quả nghiệp vụ thật**, và test đường lỗi. Đừng xem mã thoát là thay thế logs, tracing, metrics hay job state.

## 3. Chữ ký và contract của SpringApplication.exit

Trong Spring Boot 3.3, API ở `org.springframework.boot.SpringApplication`:

```java
public static int exit(
        ApplicationContext context,
        ExitCodeGenerator... exitCodeGenerators);
```

Lệnh gọi không truyền thêm generator:

```java
int code = SpringApplication.exit(context);
```

Lệnh gọi có generator tường minh:

```java
int code = SpringApplication.exit(context, () -> 5);
```

`ExitCodeGenerator` nằm trong package `org.springframework.boot`, là interface có một method `getExitCode()`, nên có thể viết lambda.

Các điểm do JavaDoc Spring Boot 3.3 xác nhận:

1. Phương thức giúp kết thúc `SpringApplication` và lấy **mã nguyên**: `0` nếu thành công theo quy tắc exit code, khác `0` khi có kết quả phù hợp.
2. Nó dùng **các `ExitCodeGenerator` bạn truyền qua varargs** cộng thêm **các bean Spring implement `ExitCodeGenerator`** trong context.
3. Nếu có nhiều generator, **mã khác 0 đầu tiên theo thứ tự đã sắp xếp** được chọn.
4. Thứ tự được điều khiển qua `Ordered` hoặc `@Order`.
5. Phương thức cố không ném exception ra caller; các lỗi gặp trong quá trình xử lý có thể được ghi ra log/stack trace. Không được diễn giải điều này thành “cleanup luôn thành công”.
6. Context được **đóng nếu có thể**.

### 3.1. Đừng nhầm overload context và một lệnh exit của hệ điều hành

Tham số là `ApplicationContext`, không phải PID, shell command, exit code ban đầu hoặc `SpringApplication` instance. Code chỉ nên gọi sau khi thực sự có một context đã được tạo thành công (trừ khi bạn đang xử lý API failure theo contract riêng).

```java
ConfigurableApplicationContext context =
        SpringApplication.run(MyApp.class, args);

int code = SpringApplication.exit(context);
```

Đây là snippet trong `main` của một project có class `MyApp`. Sau lời gọi exit, **không tiếp tục sử dụng bean từ context này để xử lý công việc mới**.

### 3.2. Đừng gọi exit hai lần để “lấy lại code”

Sau khi `SpringApplication.exit(context)` đóng context, bean lifecycle đã đi vào trạng thái shutdown. Các lần gọi tiếp theo không phải một protocol tính lại kết quả đáng tin; không viết luồng nghiệp vụ dựa vào việc `exit` được gọi nhiều lần.

**Thiết kế tốt:** chỉ một nơi quyết định thời điểm kết thúc và gọi SpringApplication.exit một lần; lưu biến mã đã nhận rồi sử dụng nó.

## 4. ExitCodeGenerator: nguồn chính để xác định kết quả

Interface:

```java
package org.springframework.boot;

@FunctionalInterface
public interface ExitCodeGenerator {
    int getExitCode();
}
```

Đây là bản mô tả chữ ký API (không phải file để bạn tự định nghĩa lại, vì interface đã có trong Spring Boot). Một bean implement interface có thể quyết định mã dựa trên job result hoặc trạng thái nghiệp vụ được kiểm soát.

### 4.1. Đăng ký generator dưới dạng @Bean

```java
@Bean
ExitCodeGenerator jobExitCode(JobResult result) {
    return () -> result.isSuccessful() ? 0 : 12;
}
```

Đây là **snippet trong class cấu hình**, giả định `JobResult` là bean nghiệp vụ có `isSuccessful()`. Spring sẽ tìm bean `ExitCodeGenerator` khi `SpringApplication.exit` tính code.

Mục tiêu: **kết quả từ task quyết định exit status**, không phải ghi cứng `System.exit(1)` ở nhiều chỗ.

### 4.2. Truyền generator trực tiếp

```java
int exitCode = SpringApplication.exit(context, () -> 17);
```

Cách này tiện nếu `main` đã biết kết quả lệnh vừa chạy. Generator truyền trực tiếp tham gia cùng với generator beans có sẵn; nếu đã có các bean trả mã khác 0, không tự giả định `17` chắc chắn thắng. Cần nắm **thứ tự generator** và điều kiện “first non-zero”.

### 4.3. Chỉ cần một generator trả 0

Nếu hệ thống chỉ có một generator và nó trả `0`, kết quả sẽ là `0`. Nếu một generator đầu trả `0` còn một generator sau trả `9`, hệ thống tiếp tục tìm và chọn `9` theo thứ tự áp dụng.

**`0` là giá trị “không có lỗi ở nguồn này”**, không phải dấu hiệu bắt buộc phải kết thúc việc xem xét các generator còn lại.

## 5. Nếu có nhiều ExitCodeGenerator: thứ tự quan trọng

Giả sử ba generator có kết quả:

| Generator | Thứ tự ưu tiên | `getExitCode()` |
| --- | ---: | ---: |
| Kiểm tra cấu hình | 10 | 0 |
| Kiểm tra dữ liệu | 20 | 14 |
| Kiểm tra hệ thống ngoài | 30 | 7 |

Theo quy tắc **first non-zero** của Spring Boot 3.3, mã được chọn là **14**, không phải `7`, không phải `14 + 7 = 21` và cũng không mặc định là mã có giá trị số lớn nhất.

### 5.1. Ví dụ type-safe với Ordered

```java
package com.example.exit;

import org.springframework.boot.ExitCodeGenerator;
import org.springframework.core.Ordered;

public final class OrderedExitCode
        implements ExitCodeGenerator, Ordered {

    private final int code;
    private final int order;

    public OrderedExitCode(int code, int order) {
        this.code = code;
        this.order = order;
    }

    @Override
    public int getExitCode() {
        return code;
    }

    @Override
    public int getOrder() {
        return order;
    }
}
```

Đây là **file Java hoàn chỉnh** trong project có Spring Boot 3.3: `src/main/java/com/example/exit/OrderedExitCode.java`. Một configuration class có thể tạo:

```java
@Bean
ExitCodeGenerator configResult() {
    return new OrderedExitCode(0, 10);
}

@Bean
ExitCodeGenerator dataResult() {
    return new OrderedExitCode(14, 20);
}

@Bean
ExitCodeGenerator dependencyResult() {
    return new OrderedExitCode(7, 30);
}
```

Đây là **các method minh họa** bên trong `@Configuration`/`@SpringBootApplication` có import `@Bean` và `ExitCodeGenerator`. Nếu cả ba được đăng ký, theo thứ tự đã chỉ định, kết quả ưu tiên là **14**.

**Không copy thêm ba bean này vào project demo phần 8** nếu muốn giữ kết quả đúng như phần thực hành; đó là hai ví dụ độc lập với nhau.

### 5.2. Ordered và @Order

Spring Boot hỗ trợ `Ordered` hoặc `@Order` để quyết định thứ tự generator. Trong Spring, order có giá trị **nhỏ hơn** thì độ ưu tiên thường **cao hơn**. Cách dùng `Ordered` trên đối tượng rõ ràng hơn khi code cần quyết định ở runtime.

Nếu hai generator có cùng độ ưu tiên, **không dựa vào thứ tự đăng ký không được đảm bảo** để quyết định một mã quan trọng. Hãy đặt thứ tự phân biệt hoặc tập trung quy tắc lỗi vào một generator tổng hợp.

### 5.3. Mã thoát là contract, không phải random integer

Một hệ thống batch có thể dùng:

```text
0  = Completed successfully
2  = Invalid arguments or configuration
4  = Business validation failed
8  = External dependency unavailable
16 = Internal error that requires investigation
```

Đây là **bảng quy ước minh họa do ứng dụng tự chọn**, không phải mã tiêu chuẩn bắt buộc của Spring Boot. Giá trị nào được dùng, có retry hay không, và hậu quả với scheduler phải được ghi trong tài liệu vận hành.

Tránh lấy trực tiếp HTTP status như 404 hoặc 503 làm process exit code. HTTP status và process status thuộc hai giao thức khác nhau; trong một số shell/OS, giá trị lớn có thể bị biểu diễn/truncated khác kỳ vọng.

## 6. Vì sao cần gọi System.exit để truyền mã về OS?

Xét hai chương trình:

**Trường hợp A — chỉ tính code và đóng Spring context:**

```java
int code = SpringApplication.exit(context);
System.out.println("Computed code = " + code);
```

Code Java có thể tiếp tục chạy sau `println`. Nếu `main` kết thúc bình thường và JVM không bị một cơ chế khác ép mã thoát, OS có thể nhận **0** dù biến `code` mang giá trị `7`.

**Trường hợp B — chuyển code tới JVM:**

```java
int code = SpringApplication.exit(context);
System.exit(code);
```

Lời gọi `System.exit` yêu cầu JVM dừng với mã đó. Đây là mẫu trong tài liệu Spring Boot dành cho các chương trình command-line mà tiến trình **phải báo kết quả** cho runner/scheduler.

### 6.1. Đặt System.exit ở đâu?

Thường chỉ **entrypoint `main`** hoặc một lớp orchestration ở biên ứng dụng mới nên quyết định kết thúc **toàn JVM**. Không gọi `System.exit` tùy tiện trong:

- Controller xử lý một HTTP request.
- Repository hoặc service nghiệp vụ tái sử dụng được.
- Một listener có thể được gọi nhiều lần.
- `@PostConstruct` hoặc constructor của bean.
- Unit test chạy chung JVM với nhiều test khác.
- Code thư viện dùng trong nhiều ứng dụng.

Nếu chỉ một request thất bại, trả HTTP error/failure response phù hợp, **không dừng cả JVM**.

### 6.2. System.exit không phải graceful orchestration tự động

`System.exit` kích hoạt quá trình shutdown của JVM và shutdown hooks, nhưng **không thay thế việc bạn đã thiết kế drain traffic, stop producer, await task, commit transaction và cleanup tài nguyên**.

Gọi `SpringApplication.exit(context)` trước `System.exit(code)` là cách hợp lý để Spring có cơ hội chạy lifecycle callbacks. Nhưng nếu task đang chạy bị kẹt hoặc hệ điều hành giết container do timeout, các bước cleanup vẫn có thể bị cắt ngang.

## 7. SpringApplication.exit và ApplicationContext.close khác nhau thế nào?

`ConfigurableApplicationContext.close()` đóng context nhưng không tính mã nghiệp vụ từ các `ExitCodeGenerator`.

```java
context.close();
// Không có giá trị int trả về từ close().
```

`SpringApplication.exit(context)` xử lý thêm generator và trả mã:

```java
int code = SpringApplication.exit(context);
// Sau khi exit, context thường đã đóng.
```

Vì vậy nếu ứng dụng batch cần mã thoát, đừng chỉ gọi `context.close()` rồi mặc định Spring sẽ chuyển trạng thái job sang OS.

### 7.1. Không cần double-close bằng try-with-resources

`ConfigurableApplicationContext` là `AutoCloseable`; có thể viết:

```java
try (ConfigurableApplicationContext context =
             SpringApplication.run(MyApp.class, args)) {
    // Làm việc với context.
}
// Auto-close, nhưng không gọi ExitCodeGenerator.
```

Đây là snippet trong chương trình có `MyApp`. Nếu bạn cần mã từ `SpringApplication.exit(context)`, một owner ở `main` có thể chủ động gọi nó đúng **một lần**. Không nên vừa dùng try-with-resources để close, vừa gọi exit tùy tiện nhiều lần trong các path khác nhau rồi suy luận rằng callbacks sẽ chạy đúng một lần theo ý mình.

### 7.2. Nếu dùng web application thì sao?

`SpringApplication.exit(context)` có thể đóng một web `ApplicationContext` và dừng embedded web server theo lifecycle. Nhưng đó không phải một endpoint HTTP admin an toàn mặc định. Một web service đang phục vụ nhiều clients cần:

- Readiness/drain traffic.
- Ngừng nhận công việc mới.
- Dừng server và xử lý in-flight requests.
- Dừng schedulers, message consumers, background workers.
- Bảo đảm các dependencies được đóng sau consumers.
- Phối hợp deadline shutdown của Spring Boot và Kubernetes.

Mã `int` của `SpringApplication.exit` không nên được dùng như HTTP response status.

## 8. Ví dụ Spring Boot 3.3 hoàn chỉnh: tính mã thoát nhưng không ép JVM kết thúc

Mục tiêu là **có thể chạy và quan sát** mà không buộc process đột ngột dừng trong lần thử đầu. Demo gồm:

- Spring Boot **non-web** (`WebApplicationType.NONE`).
- Một `ExitCodeGenerator` bean lấy giá trị từ property `demo.exit-code`.
- Một `ApplicationRunner` giả lập công việc.
- Một bean resource có `close()` để chứng minh context được destroy.
- Sau `SpringApplication.exit(context)`, chương trình in mã, trạng thái active của context.
- Tùy chọn `--demo.os-exit=true` để thực sự gọi `System.exit(code)` và truyền code cho hệ điều hành.

### 8.1. Cấu trúc thư mục

```text
exit-code-lesson/
  settings.gradle
  build.gradle
  src/main/resources/application.properties
  src/main/java/com/example/exit/
    ExitCodeLessonApplication.java
```

### 8.2. settings.gradle

```groovy
rootProject.name = 'exit-code-lesson'
```

### 8.3. build.gradle (Groovy DSL)

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
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

Đây là build script cơ bản có thể sử dụng với Java 17+ và Spring Boot 3.3.13. Các lệnh `./gradlew` giả định project đã có **Gradle Wrapper**; bạn có thể tạo project bằng Spring Initializr hoặc tạo wrapper qua Gradle nếu cần.

### 8.4. application.properties

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off

# Mã nghiệp vụ để quan sát, mặc định thành công.
demo.exit-code=0

# Không bắt buộc System.exit khi đang học.
demo.os-exit=false
```

Ví dụ dùng Java main để kiểm tra tùy chọn `--demo.os-exit=true`. Property trong file và command-line argument có thể được Spring Boot xử lý theo các nguồn cấu hình thông thường; giá trị trong CLI thường có ưu tiên cao hơn file.

### 8.5. ExitCodeLessonApplication.java — mã hoàn chỉnh

```java
package com.example.exit;

import java.util.Arrays;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.ExitCodeGenerator;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class ExitCodeLessonApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ExitCodeLessonApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);

        ConfigurableApplicationContext context = application.run(args);

        // Spring đóng context và trả exit code, không gọi System.exit.
        int exitCode = SpringApplication.exit(context);

        System.out.println("RETURNED_EXIT_CODE=" + exitCode);
        System.out.println("CONTEXT_ACTIVE=" + context.isActive());

        // Opt-in chỉ tại entrypoint nếu thực sự muốn OS nhận code.
        if (Arrays.asList(args).contains("--demo.os-exit=true")) {
            System.exit(exitCode);
        }
    }

    @Bean
    ExitCodeGenerator configuredExitCode(Environment environment) {
        return () -> environment.getProperty(
                "demo.exit-code", Integer.class, 0);
    }

    @Bean
    DemoResource demoResource() {
        return new DemoResource();
    }

    @Bean
    ApplicationRunner sampleJob(DemoResource resource) {
        return args -> System.out.println("RUNNER_DONE");
    }

    public static final class DemoResource
            implements AutoCloseable {

        @Override
        public void close() {
            System.out.println("RESOURCE_CLOSED");
        }
    }
}
```

**Đây là một file Java hoàn chỉnh**, không cần thêm class ngoài hoặc server/database. `DemoResource` là nested class của application, được tạo làm Spring bean nhờ `@Bean`. Spring nhận biết `AutoCloseable.close()` để gọi khi bean bị destroy; nếu muốn rõ contract hơn có thể dùng `@Bean(destroyMethod="close")` cho method tạo resource.

Những điểm mấu chốt:

1. `application.run(args)` tạo context và chạy runner bình thường.
2. `sampleJob` có dependency `DemoResource`, nên resource được tạo trước khi runner thực thi.
3. `configuredExitCode` là bean `ExitCodeGenerator`. Khi `SpringApplication.exit` được gọi, generator đọc property `demo.exit-code`.
4. `SpringApplication.exit(context)` xác định `int exitCode`, đóng context và kích hoạt `DemoResource.close()`.
5. Sau khi exit trả về, main in `RETURNED_EXIT_CODE` và `CONTEXT_ACTIVE`.
6. Chỉ khi CLI có chính xác chuỗi `--demo.os-exit=true`, main mới gọi `System.exit(exitCode)`.
7. Nếu không gọi `System.exit`, chương trình non-web này bình thường tự hết khi `main` return và không còn non-daemon threads, nên process status không nhất thiết bằng `RETURNED_EXIT_CODE` nếu code khác 0.

### 8.6. Cách chạy mặc định

Tại thư mục có Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows CMD:

```bat
gradlew.bat bootRun
```

Kết quả **những dòng do demo tự in** theo thứ tự trong đường chạy thành công:

```text
RUNNER_DONE
RESOURCE_CLOSED
RETURNED_EXIT_CODE=0
CONTEXT_ACTIVE=false
```

Banner và các log thông thường đã giảm bằng property, nhưng Gradle/Spring vẫn có thể in thông tin khác. Không hứa **toàn bộ stdout** chỉ gồm bốn dòng trên.

### 8.7. Thử mã khác 0 nhưng CHƯA chuyển cho OS

Chạy:

```bash
./gradlew bootRun --args="--demo.exit-code=7"
```

Output của demo:

```text
RUNNER_DONE
RESOURCE_CLOSED
RETURNED_EXIT_CODE=7
CONTEXT_ACTIVE=false
```

Vì main không gọi `System.exit(7)`, lệnh chạy vẫn có thể kết thúc **thành công ở cấp JVM/Gradle** dù nó in `RETURNED_EXIT_CODE=7`. Đây là khác biệt quan trọng nhất của bài.

**Đừng dùng trường hợp này để kiểm thử rằng CI/CD hoặc scheduler nhận code 7.** Nó chỉ chứng minh **SpringApplication.exit trả về 7**.

### 8.8. Chuyển mã thật cho OS

Với cùng project, build file thực thi:

```bash
./gradlew bootJar
```

Sau đó chạy (tên file khớp `group`/`version` trong ví dụ):

```bash
java -jar build/libs/exit-code-lesson-0.0.1-SNAPSHOT.jar \
  --demo.exit-code=7 --demo.os-exit=true
```

Những dòng do code demo in vẫn là:

```text
RUNNER_DONE
RESOURCE_CLOSED
RETURNED_EXIT_CODE=7
CONTEXT_ACTIVE=false
```

Nhưng lần này JVM đã được gọi `System.exit(7)`. Trên các shell phổ biến, process status tương ứng được báo ra chương trình cha.

Với Bash/zsh, chạy **ngay sau lệnh java**:

```bash
echo $?
```

Kết quả kỳ vọng:

```text
7
```

Windows PowerShell:

```powershell
$LASTEXITCODE
```

Windows CMD:

```bat
echo %ERRORLEVEL%
```

Lệnh kiểm tra phải được thực hiện **ngay sau process cần đo**, vì chạy một command khác có thể thay đổi giá trị exit status được shell nhớ.

Nếu truyền `--demo.exit-code=0 --demo.os-exit=true`, mã gửi cho OS sẽ là 0 và thường được coi thành công.

### 8.9. Vì sao không dùng Gradle bootRun để chứng minh mọi mã OS?

`bootRun` là tác vụ Gradle chạy một Java process và có thể chuyển non-zero process exit thành **Gradle task failure**. Khi đó mã status của chính lệnh `gradlew` không nhất thiết giữ nguyên bằng số bạn đã gọi `System.exit` trong Java. Để kiểm tra mã thoát thực của ứng dụng, hãy chạy **`java -jar` trực tiếp** (hoặc một wrapper có contract bảo toàn exit status).

Đây không phải lỗi SpringApplication.exit; đây là khác biệt giữa **process con ứng dụng** và **process cha công cụ build**.

## 9. ExitCodeEvent: quan sát mã đã được xác định

Spring Boot có `org.springframework.boot.ExitCodeEvent`. JavaDoc mô tả đây là application event được phát khi một mã thoát được xác định từ `ExitCodeGenerator`.

API chính:

```java
int code = event.getExitCode();
```

Một listener có thể dùng để log/telemetry:

```java
@Component
public class ExitCodeAudit {

    @EventListener
    public void onExitCode(ExitCodeEvent event) {
        System.out.println("EXIT_EVENT_CODE=" + event.getExitCode());
    }
}
```

Đây là **class minh họa** đặt trong package được Spring scan, cần import `@Component`, `@EventListener` và `ExitCodeEvent`. Không thêm class này vào demo nếu muốn giữ stdout bốn dòng như phần 8.

Không dùng event handler để **thay đổi** code bằng cách gọi `System.exit` hoặc ném exception: event là thông báo; nơi quyết định kết thúc process vẫn phải có ownership rõ ràng. Cũng không thiết kế correctness dựa trên kỳ vọng event nhất định xuất hiện với mọi trường hợp trả 0 hoặc mọi đường startup failure; phải theo contract từng pha.

### 9.1. ExitCodeEvent khác ContextClosedEvent

- `ExitCodeEvent` nói về **mã được xác định** trong cơ chế exit-code của Boot.
- `ContextClosedEvent` của Spring Framework nói rằng **context đang đóng**.
- Một context có thể được đóng qua `context.close()` hoặc shutdown hook **không cần** ứng dụng tính exit code từ `ExitCodeGenerator`.
- Khi SpringApplication.exit được gọi, có thể phát event liên quan đến exit code rồi thực hiện đóng context; listener mỗi event cần code theo đúng loại.
- `ApplicationFailedEvent` thuộc **đường startup thất bại**, không phải chỉ vì application chủ động thoát với mã khác 0 sau một job.

Đừng đánh đồng một event “process kết thúc” với mọi loại sự kiện shutdown.

## 10. Exception cũng có thể cung cấp ExitCodeGenerator

Tài liệu Spring Boot 3.3 cho phép exception implement `ExitCodeGenerator` để cung cấp mã thoát khi một lỗi cụ thể được xử lý trong đường thất bại của Spring Boot.

Ví dụ:

```java
package com.example.exit;

import org.springframework.boot.ExitCodeGenerator;

public final class InvalidImportException
        extends RuntimeException
        implements ExitCodeGenerator {

    public InvalidImportException(String message) {
        super(message);
    }

    @Override
    public int getExitCode() {
        return 12;
    }
}
```

Đây là **file Java hoàn chỉnh** với mục đích biểu diễn loại lỗi, không tự tạo startup failure. Nếu một runner hoặc bean ném loại exception này trong đường khởi động, Spring Boot có thể sử dụng `getExitCode()` trong cơ chế xử lý lỗi.

**Quan trọng:** nếu `SpringApplication.run(...)` đã ném exception, lệnh tiếp theo:

```java
System.exit(SpringApplication.exit(
        SpringApplication.run(MyApp.class, args)));
```

**không thể chạy theo nhánh thành công bình thường**, vì `run` chưa trả một context. Spring Boot có xử lý failure/exit-code riêng cho trường hợp này; đừng nghĩ rằng code trong `main` đã chủ động gọi `SpringApplication.exit` với một context hợp lệ.

Việc hệ điều hành/launcher cuối cùng biểu diễn mã thất bại như thế nào còn phụ thuộc vào đường startup failure và cách chạy process. Với một job production, hãy test **mã thực tế của process** trong script/container đang sử dụng.

### 10.1. Không dùng exception cho kết quả nghiệp vụ bình thường

Nếu job xử lý 10.000 record và phát hiện ba bản ghi bị validation fail nhưng vẫn hoàn tất, bạn có thể dùng kết quả nghiệp vụ được lưu lại trong `JobResult` và generator bean thay vì ném một exception cho toàn bộ quá trình.

Exception nên diễn đạt **đường lỗi bất thường**; exit code bean thích hợp khi muốn ánh xạ trạng thái cuối của một job có chủ đích.

## 11. ExitCodeExceptionMapper: ánh xạ lỗi sang mã có ý nghĩa

Spring Boot còn có interface `org.springframework.boot.ExitCodeExceptionMapper`, dùng ánh xạ một `Throwable` sang một mã:

```java
int getExitCode(Throwable exception);
```

Một bean mapper mẫu:

```java
@Bean
ExitCodeExceptionMapper invalidImportMapper() {
    return error -> {
        Throwable current = error;

        while (current != null) {
            if (current instanceof InvalidImportException) {
                return 12;
            }
            current = current.getCause();
        }

        return 0;
    };
}
```

Đây là **snippet trong configuration class**, cần import `ExitCodeExceptionMapper` và class `InvalidImportException` đã định nghĩa trong ví dụ phần 10. Nó minh họa việc đi theo chuỗi cause vì exception gốc có thể bị bọc bởi một exception khác.

Khi Spring Boot xử lý lỗi trong những giai đoạn mà mapper bean đã được tạo và có thể truy cập, mapper có thể đóng góp mã thích hợp. **Đừng cam kết mapper bean sẽ hoạt động cho lỗi quá sớm**, khi context chưa khởi tạo đủ để bean đó tồn tại. Trong trường hợp lỗi như không đọc được cấu hình, không load được classpath hoặc JVM không chạy được `main`, cơ chế Spring bean chưa chắc đã sẵn sàng.

### 11.1. 0 từ mapper có nghĩa gì?

Trong contract mapper, `0` có thể được dùng để biểu thị mapper này **không gán mã đặc biệt** cho exception được đưa vào. Khi có nhiều mapper/generator, cần xác định ưu tiên và kiểm tra kết quả trong phiên bản Spring Boot đang dùng; đừng giả định một mapper trả 0 sẽ luôn xóa trạng thái lỗi đã được mapper khác xác định.

### 11.2. Tránh trộn logic lỗi ở nhiều lớp

Đừng vừa để exception implement `ExitCodeGenerator`, vừa có mapper khác trả mã mâu thuẫn cho chính exception đó, lại thêm generator bean của một job thất bại, nếu bạn chưa xác định rõ contract ưu tiên.

Đối với bài tập, chọn một trong hai cơ chế lỗi là đủ:

- Exception implement `ExitCodeGenerator` nếu bản thân kiểu exception **mang ý nghĩa exit code**.
- `ExitCodeExceptionMapper` nếu muốn tách phân loại lỗi khỏi class exception.

Đối với kết quả job sau khi chạy thành công đến lúc exit chủ động, dùng `ExitCodeGenerator` bean hoặc generator truyền trực tiếp.

## 12. Mã thoát trong batch/CLI khác mã HTTP và availability

Một ứng dụng Spring Boot có thể chạy theo ba kiểu:

| Kiểu ứng dụng | Tín hiệu chính cho người điều phối |
| --- | --- |
| CLI chạy một lần | **Process exit code** |
| Kubernetes Job/CronJob | Exit status của container/process và Job status |
| Long-running HTTP service | Readiness, liveness, request responses, logs, metrics |
| Consumer chạy dài hạn | Liveness/readiness, consumer state và cơ chế restart/checkpoint |

**Không nên** gọi `SpringApplication.exit` ở cuối mỗi HTTP request. Đóng context sẽ ảnh hưởng toàn bộ users và background tasks đang dùng nó.

### 12.1. Một job thành công thường nên tự kết thúc

Với CLI/batch, mốc kết thúc thường là:

```text
Start JVM
   |
SpringApplication.run()
   |
ApplicationRunner / CommandLineRunner
   |
Job result đã hoàn tất và được ghi nhận
   |
SpringApplication.exit(context)
   |
System.exit(code) nếu cần truyền chính xác cho OS
   |
Scheduler/CI/CD đọc process exit status
```

Nếu code phải chạy dài hạn, **không** chủ động kết thúc context sau khi startup xong chỉ để trả một mã 0.

### 12.2. Đối với Kubernetes

Một pod chạy **Job** sẽ được nền tảng theo dõi exit status và pod phase. Mã khác 0 thường khiến Job retry/fail theo `backoffLimit` và restart policy, nhưng hành vi cụ thể phụ thuộc manifest/hạ tầng.

Với **Deployment** hoặc server dài hạn, đừng dùng application exit code như cơ chế kiểm soát traffic thay thế readiness. Nếu instance không thể phục hồi nội bộ, có thể dùng `LivenessState` và liveness probes phù hợp; khi cần ngừng nhận traffic tạm thời, dùng readiness. Các cơ chế này không đồng nghĩa với mã trả về từ `SpringApplication.exit`.

## 13. Mã thoát và trạng thái hệ điều hành: những giới hạn cần biết

Java `System.exit(int)` nhận một số nguyên `int`, nhưng hệ điều hành và shell có quy tắc biểu diễn status riêng.

- **0** thường là thành công.
- **Khác 0** thường được coi failure hoặc trạng thái cần xử lý.
- Trên các shell Unix phổ biến, phần status quan sát được thường nằm trong **8 bit thấp** đối với exit status thường; mã lớn hơn 255 hoặc âm có thể không được bảo toàn như số Java ban đầu.
- Trên Windows, các command processors có cơ chế biểu diễn và biến trạng thái khác Unix.
- Build tools, Docker wrappers, scripts hoặc schedulers có thể nhận/đổi mã theo contract riêng.

**Khuyến nghị:** dùng một tập mã **nhỏ, dương, ổn định**, ví dụ 0, 2, 4, 8, 16. Ghi định nghĩa bằng văn bản, giữ tương thích với pipeline và tránh dùng số ngẫu nhiên hoặc số giống HTTP status.

### 13.1. Bash set -e có thể dừng script trước khi echo status

Ví dụ:

```bash
set +e
java -jar build/libs/exit-code-lesson-0.0.1-SNAPSHOT.jar \
  --demo.exit-code=7 --demo.os-exit=true
code=$?
echo "Java exit status: $code"

if [ "$code" -ne 0 ]; then
    echo "Job failed"
    exit "$code"
fi
```

Đây là snippet cho Bash/sh; giả định file JAR của demo đã được build. Nếu trước đó script bật `set -e`, một command trả non-zero có thể khiến shell dừng trước khi bạn kịp lưu `$?`; vì vậy cần xử lý status có chủ đích.

Không viết:

```bash
java -jar app.jar
echo "Job completed"
```

rồi mặc định job đã thành công, nếu code thực ra trả một status nonzero nhưng script bỏ qua. Shell pipeline cần xác định rõ điều kiện success/failure.

## 14. Shutdown hook và @PreDestroy liên hệ thế nào?

Spring Boot thông thường đăng ký JVM shutdown hook để đóng `ApplicationContext` khi tiến trình kết thúc theo đường thích hợp. Vì vậy với nhiều ứng dụng web, gửi tín hiệu dừng có trật tự có thể kích hoạt bean destruction callbacks ngay cả khi code không tự gọi `SpringApplication.exit`.

Nhưng:

- Shutdown hook **không tự tính và gửi mã nghiệp vụ** theo contract `ExitCodeGenerator` trừ khi cơ chế exit-code được gọi/xử lý theo đường phù hợp.
- Một JVM bị **SIGKILL**, mất điện, crash nghiêm trọng hoặc container bị buộc hạ không được bảo đảm chạy đầy đủ shutdown hooks.
- Một `@PreDestroy` có thể chạy khi context đóng nhưng không đồng nghĩa mọi async task đã kết thúc.
- Shutdown timeouts của hạ tầng có thể cắt ngang cleanup.

### 14.1. Ví dụ resource cleanup trong demo

Trong phần 8, `DemoResource.close()` in `RESOURCE_CLOSED`. Dòng đó xuất hiện **trước khi SpringApplication.exit trả về mã** trong đường thành công. Nó chứng minh Spring đã gọi resource destroy callback thông thường khi đóng context.

Tuy vậy, nếu cleanup thực tế ném exception hoặc giữ lock, không nên kết luận chỉ từ một mã 0 rằng mọi resource đã được thu hồi. Muốn đảm bảo, cần test startup/shutdown khi có load và các failure paths.

### 14.2. Thứ tự shutdown là một vấn đề riêng

Khi batch job có HTTP client, DataSource hoặc executor đang chạy:

1. Ngừng submit tác vụ mới.
2. Chờ tasks in-flight trong thời hạn.
3. Xử lý transaction/checkpoint/cancellation.
4. Đóng responses và JDBC connections mượn.
5. Đóng shared clients, connection pools và executor theo bean lifecycle.
6. Trả mã thoát phù hợp và kết thúc tiến trình.

`SpringApplication.exit` hỗ trợ đóng context, nhưng **không tự biến một task không cooperative thành task được checkpoint**, không tự tạo durable queue và không thể làm hạ tầng chờ vô hạn.

## 15. Trường hợp nhiều ExitCodeGenerator beans

Một số dự án có generator từ:

- Job processor.
- Validation module.
- External dependency checker.
- Plugin hoặc starter bên ngoài.
- Spring Batch (ví dụ `JobExecutionExitCodeGenerator` khi tích hợp phù hợp).

Khi nhiều generator tồn tại, Spring Boot không cộng các mã, không chọn mã lớn nhất và không ưu tiên “bean mới nhất”. Nó dùng **mã khác 0 đầu tiên theo order**.

### 15.1. Quản lý thứ tự như một hợp đồng nghiệp vụ

Giả sử bạn muốn ưu tiên:

1. Cấu hình không hợp lệ.
2. Dữ liệu đầu vào không hợp lệ.
3. Lỗi hệ thống ngoài.
4. Job hoàn tất bình thường.

Gán `Ordered`/`@Order` có ý nghĩa thay vì phụ thuộc vào tên bean hoặc insertion order. Nếu nghiệp vụ cần một quy tắc tổng hợp phức tạp, một **aggregating ExitCodeGenerator** có thể rõ ràng hơn nhiều generator cạnh tranh.

### 15.2. Generator nên nhẹ và không có side effect

`getExitCode()` nên trả kết quả đã được job xác lập, ví dụ từ một immutable `JobResult`. Không nên:

- Gọi lại job.
- Ghi dữ liệu lần thứ hai.
- Gọi remote API timeout dài.
- Mở thêm thread pool.
- Đóng `ApplicationContext` bên trong generator.
- Gọi `System.exit(...)` trong `getExitCode()`.
- Ném exception tùy tiện để “thắng” generator khác.

Đây là pha quyết định status và shutdown, không phải nơi bắt đầu công việc nghiệp vụ mới.

## 16. Kiểm thử mà không giết JVM test runner

Một lỗi test nguy hiểm:

```java
@Test
void testExit() {
    System.exit(7); // Không làm: kết thúc cả JVM chạy test.
}
```

Đây là **phản ví dụ**; muốn kiểm thử mã, không gọi `System.exit` trong cùng test process.

Cách test được khuyến nghị:

1. Unit test `ExitCodeGenerator.getExitCode()` với job result khác nhau.
2. Unit test `Ordered`/priority policy khi có nhiều generator.
3. Integration test tạo **một context riêng**, gọi `SpringApplication.exit(context)` rồi assert mã trả về và context đã đóng.
4. Process-level test chạy `java -jar` bằng `ProcessBuilder` hoặc shell **ở process con**, kiểm tra exit code thật.
5. Nếu kiểm tra exception path, xác minh nguồn exception/mapper có được Boot nhìn thấy ở pha đó không.

### 16.1. Ví dụ integration test khái niệm

```java
@SpringBootTest(
    classes = ExitCodeLessonApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class ExitCodeLessonTest {

    @Autowired
    ConfigurableApplicationContext context;

    @Test
    void exitReturnsExpectedCode() {
        int code = SpringApplication.exit(context);
        assertEquals(0, code);
        assertFalse(context.isActive());
    }
}
```

**Đây là snippet minh họa, không phải test khuyến nghị chạy nguyên trạng trên cached context dùng chung.** Nó còn cần import `@SpringBootTest`, `@Autowired`, JUnit assertions và `SpringApplication`. Việc gọi `exit(context)` đóng context mà TestContext cache có thể tái sử dụng, khiến các tests sau bị ảnh hưởng.

**Tốt hơn** là tạo context biệt lập trong test và đóng nó dưới ownership riêng. Nếu cố tình test lifecycle bằng `@SpringBootTest`, đánh dấu scope/dirties context đúng chỗ và hiểu tác động lên cache.

### 16.2. Process-level test với Java ProcessBuilder

```java
ProcessBuilder builder = new ProcessBuilder(
        "java",
        "-jar",
        "build/libs/exit-code-lesson-0.0.1-SNAPSHOT.jar",
        "--demo.exit-code=7",
        "--demo.os-exit=true"
);
builder.inheritIO();

Process process = builder.start();
int status = process.waitFor();

System.out.println("OBSERVED_STATUS=" + status);
```

Đây là **snippet bên trong một method có `throws IOException, InterruptedException`** và file JAR đã được build. Nó không cần gọi `System.exit` ở test process; chỉ process con kết thúc. Nếu dùng với build server, đặt timeout và cleanup process nếu bị kẹt, không gọi `waitFor()` vô hạn trên công việc không tin cậy.

Trên môi trường hỗ trợ code 7 đầy đủ, output của process cha gồm:

```text
OBSERVED_STATUS=7
```

Đó là cách kiểm tra **process status thật**, khác với chỉ assert giá trị `int` mà SpringApplication.exit trả cho một JVM đang chạy.

## 17. Nếu startup thất bại trước khi có context thì sao?

Không được giả định:

```java
ConfigurableApplicationContext context =
        SpringApplication.run(App.class, args);
int code = SpringApplication.exit(context);
```

luôn chạy đến dòng thứ hai. Nếu `run` throw do property sai, circular dependency, runner lỗi, bean init failure hoặc web server không bind được port, biến `context` có thể chưa được gán.

Trong đường startup failure, Spring Boot có cơ chế:

- `ApplicationFailedEvent`.
- `FailureAnalyzer` để báo thông tin dễ hiểu.
- `ExitCodeGenerator` trên exception.
- `ExitCodeExceptionMapper` cho lỗi được ánh xạ khi mapper khả dụng.

Không viết một `catch (Exception ex) { return 0; }` khiến scheduler thấy thành công giả. Cũng không gọi `SpringApplication.exit(null)` chỉ để cố có mã; dùng failure handling rõ ràng và test trong launcher thật.

### 17.1. ApplicationFailedEvent không phải ExitCodeEvent

`ApplicationFailedEvent` biểu thị startup thất bại; `ExitCodeEvent` mô tả một mã exit đã được xác định. Chúng có thể cùng xuất hiện trên một đường failure cụ thể, nhưng không thay thế nhau. Event listeners đăng ký như Spring beans có thể **chưa sẵn sàng** nếu startup lỗi rất sớm.

Nếu cần bắt failure events cực sớm, listener cần được đăng ký theo cơ chế của `SpringApplication` trước `run`. Đừng mặc định `@EventListener` trong một component luôn bắt được lỗi xảy ra trước khi component được tạo.

## 18. Các anti-pattern phổ biến

| Sai lầm | Hậu quả | Cách thay |
| --- | --- | --- |
| Chỉ gọi SpringApplication.exit rồi nghĩ OS nhận code | Giá trị int chỉ ở Java, process có thể kết thúc 0 | System.exit(code) ở main khi cần báo OS |
| Gọi System.exit trong controller | Tắt toàn bộ service vì một request | Trả HTTP error phù hợp |
| Gọi context.close() rồi nghĩ đã tính exit code | Không lấy ExitCodeGenerator | Dùng SpringApplication.exit khi cần mã |
| Gọi SpringApplication.exit nhiều lần | Lifecycle đã đóng, code không còn hợp đồng lặp | Một owner, một lần exit |
| Dùng exit code để biểu diễn HTTP 404/503 | Trộn protocol, số lớn có thể biến đổi trong shell | Mã nhỏ, tài liệu riêng |
| Nghĩ nonzero lớn nhất luôn thắng | Boot chọn first non-zero theo order | Ordered/@Order với policy rõ |
| Không định nghĩa thứ tự nhiều generators | Kết quả có thể phụ thuộc ordering không chủ đích | Priority rõ hoặc aggregator |
| Generator gọi API mạng trong shutdown | Có thể treo exit, mở thêm resource | Lưu kết quả trước khi tính code |
| Generator gọi System.exit bên trong | Cắt ngang Spring cleanup | Chỉ main được terminate JVM |
| Trả 0 khi job bị lỗi | CI/Kubernetes coi thành công | ExitCodeGenerator từ job result |
| Runner ném exception nhưng vẫn tin code sau run chạy | SpringApplication.run đã throw | Test đường failure riêng |
| Dùng ExitCodeExceptionMapper cho lỗi trước khi context tạo bean | Mapper chưa chắc tồn tại | Handling sớm phù hợp |
| Dùng System.exit trong JUnit cùng JVM | Kết thúc test runner | Test int trực tiếp hoặc subprocess |
| Đóng cached SpringBootTest context | Test khác hỏng do shared cache | Context biệt lập/dirties context phù hợp |
| Dùng Gradle exit status để suy ra số Java nguyên gốc | Gradle có thể đổi child error thành task failure | Chạy JAR trực tiếp kiểm tra |
| Dùng code âm/ngoài 0–255 mà không test shell | Platform có thể biểu diễn khác | Quy ước code nhỏ ổn định |
| Nghĩ shutdown hook luôn chạy dù SIGKILL | Cleanup bị bỏ qua khi kill cứng | Checkpoint/idempotence, grace period |
| Đánh dấu exitCode=0 là mọi tài nguyên chắc chắn clean | Không chứng minh cleanup toàn diện | Test close/failure paths và monitoring |

## 19. Checklist cho một ứng dụng Spring Boot CLI/batch

1. Xác định chương trình có **kết thúc sau một lần chạy** hay là service sống lâu.
2. Định nghĩa rõ ý nghĩa exit code 0 và các mã thất bại.
3. Chọn nơi lưu **kết quả nghiệp vụ** đã hoàn thành.
4. Dùng `ExitCodeGenerator` bean nếu status thuộc kết quả job trong context.
5. Có thể truyền generator trực tiếp qua `SpringApplication.exit` nếu `main` đã biết code.
6. Nếu nhiều generator, gán thứ tự `Ordered`/`@Order` không mơ hồ.
7. Giữ `getExitCode()` ngắn, an toàn, không I/O nặng.
8. Dùng `SpringApplication.exit(context)` đúng một lần sau khi có context hợp lệ.
9. Chỉ gọi `System.exit(code)` ở entrypoint khi cần process báo mã OS.
10. Không gọi exit/System.exit ở controller hoặc service có thể tái sử dụng.
11. Với startup failure, phân biệt exception generator/mapper với exit chủ động.
12. Không giả định bean mapper luôn tồn tại nếu startup lỗi trước refresh.
13. Đảm bảo resource có destroy callbacks và background jobs có deadline.
14. Đo/checkpoint công việc chưa hoàn tất trước khi process kết thúc.
15. Chạy integration test mã trả về **không dùng System.exit** trong test JVM.
16. Chạy process-level test với JAR thật để kiểm tra shell/container status.
17. Kiểm tra Bash `$?` / PowerShell `$LASTEXITCODE`/CMD `%ERRORLEVEL%` đúng cách.
18. Không trộn SpringApplication.exit code với liveness/readiness/HTTP status.
19. Với Kubernetes Job, xác minh `backoffLimit`, retry và idempotence.
20. Nếu code 0 trong production, phải có bằng chứng job result đã được commit.
21. Ghi log mã thoát, job id và error category nhưng không lộ secrets.
22. Tài liệu hóa contract exit codes cho CI/CD, operator và runbooks.

## 20. Câu hỏi tự kiểm tra

**1. SpringApplication.exit(context) có tự gọi System.exit không?**

Không. Nó trả `int` và đóng context nếu có thể; Java caller quyết định có gọi `System.exit(int)` hay không.

**2. Nếu ExitCodeGenerator bean trả 7 nhưng main không gọi System.exit(7), OS chắc nhận 7 chứ?**

Không. Chỉ có biến int trong Java; nếu main kết thúc bình thường, process có thể trả 0.

**3. SpringApplication.exit có thể lấy code từ đâu?**

Từ các `ExitCodeGenerator` beans trong context và các generators truyền vào varargs của lời gọi exit.

**4. Nhiều generator trả 0, 14, 7 thì mã nào được chọn?**

`14` nếu thứ tự chính xác là 0 rồi 14 rồi 7. Spring Boot dùng **first non-zero**, không cộng hay chọn giá trị lớn nhất.

**5. Làm sao kiểm soát thứ tự?**

Implement `Ordered` hoặc dùng `@Order` theo contract Spring.

**6. ConfigurableApplicationContext.close() và SpringApplication.exit() khác gì?**

`close()` đóng context; `SpringApplication.exit` còn tính và trả mã từ generator.

**7. Có nên gọi System.exit trong REST controller?**

Không. Nó chấm dứt toàn bộ JVM và ảnh hưởng tất cả request/tác vụ khác.

**8. Exception implement ExitCodeGenerator được dùng khi nào?**

Trong cơ chế Spring Boot xử lý đường lỗi thích hợp, đặc biệt startup failure; nó không phải lời gọi generator bean chủ động sau job thành công.

**9. ExitCodeExceptionMapper có thể xử lý lỗi trước khi Spring BeanFactory tạo mapper không?**

Không có bảo đảm. Lỗi quá sớm có thể xảy ra trước khi bean mapper tồn tại.

**10. ExitCodeEvent và ContextClosedEvent có giống nhau không?**

Không. Một loại liên quan mã thoát được xác định, một loại liên quan đóng context.

**11. Cách tốt nhất test System.exit(7) mà không hại test runner?**

Chạy ứng dụng ở **subprocess**, đợi/đọc process exit status; test mã từ SpringApplication.exit trực tiếp trong context độc lập.

**12. Gradle bootRun báo task fail có nghĩa SpringApplication.exit trả số mấy?**

Không suy luận được số nguyên chính xác nếu không đọc log/contract build tool. Dùng `java -jar` trực tiếp và kiểm tra OS status.

## 21. Tóm tắt nhớ nhanh

```text
Spring Boot application completed its work
                 |
      business outcome recorded
                 |
      ExitCodeGenerator(s)
                 |
SpringApplication.exit(context)
                 |
    +--> tính first non-zero
    +--> đóng ApplicationContext
    +--> trả về int exitCode
                 |
       Java main receives code
                 |
        +--------+--------+
        |                 |
  Chỉ in/kiểm tra     System.exit(code)
  int trong Java           |
        |              OS / parent process
  OS chưa chắc nhận     nhận process status
  chính mã này
```

**Quy tắc cốt lõi:** `SpringApplication.exit` **tính và trả** mã thoát, đồng thời yêu cầu đóng Spring context; `System.exit` mới là lời gọi chuyển mã sang cơ chế kết thúc JVM. Với nhiều `ExitCodeGenerator`, Spring Boot chọn **mã khác 0 đầu tiên theo order**. Hãy dùng exit codes như **hợp đồng có tài liệu** cho CLI/batch/scheduler, đừng nhầm với HTTP status hoặc availability của web service, và test trong môi trường thực tế để chắc chắn process trả mã bạn mong đợi.

## Tài liệu chính thức

- [Spring Boot 3.3.13 — SpringApplication.exit API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html)
- [Spring Boot 3.3.13 — SpringApplication: Application Exit](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Boot 3.3.13 — ExitCodeGenerator API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ExitCodeGenerator.html)
- [Spring Boot 3.3.13 — ExitCodeEvent API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ExitCodeEvent.html)
- [Spring Boot 3.3.13 — ExitCodeExceptionMapper API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ExitCodeExceptionMapper.html)
- [Spring Framework — ApplicationContext lifecycle and destroy callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Java 17 — Runtime.exit and System.exit](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html)
- [Gradle — Spring Boot 3.3: Running your application](https://docs.spring.io/spring-boot/3.3/gradle-plugin/running.html)
