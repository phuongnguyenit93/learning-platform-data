# Đọc chuỗi nguyên nhân thay vì chỉ thông báo ngoài cùng khi Spring Boot khởi động lỗi

## 1. Vì sao dòng lỗi ngoài cùng thường chưa trả lời được “sửa ở đâu”?

Trong Spring Boot, một bean lỗi có thể làm ứng dụng không thể khởi động. Nhưng exception được ném từ nơi lỗi thường đi qua nhiều tầng của Spring Framework: constructor, factory method, dependency injection, bean creation, application context refresh và cuối cùng là `SpringApplication.run(...)`. Mỗi tầng có thể **bọc exception trước đó thành một exception mới** để bổ sung ngữ cảnh.

Do đó một log dạng:

~~~text
Application run failed
org.springframework.beans.factory.BeanCreationException:
    Error creating bean with name 'startupGuard'
~~~

chỉ nói rằng **container không tạo được một bean**. Nó chưa cho biết **vì sao bean không tạo được**. Nguyên nhân cần sửa có thể nằm sâu hơn:

~~~text
Caused by: org.springframework.beans.BeanInstantiationException:
    Failed to instantiate [...]
Caused by: java.lang.IllegalArgumentException:
    DEMO_MISSING_SETTING
~~~

Ví dụ trên là **minh họa một chuỗi wrapper**, không phải output bắt buộc y hệt cho mọi phiên bản Spring Boot. Khi debug cần đọc **toàn bộ chuỗi `getCause()`**, tên bean/phương thức liên quan và stack frames gần điểm phát sinh.

### Ba lớp thông tin không nên đánh đồng

| Khái niệm | Câu hỏi mà nó trả lời | Hạn chế |
| --- | --- | --- |
| Thông báo ngoài cùng (`exception.getMessage()`) | Tầng gọi cuối quan sát thấy điều gì không thành công? | Có thể chỉ là “Application run failed” hoặc “Error creating bean” |
| Chuỗi nguyên nhân (`Throwable.getCause()` và `Caused by:`) | Những exception nào đã được bọc qua các tầng? | Không phải mọi quan hệ lỗi đều nằm trong một chuỗi tuyến tính |
| Stack trace (`getStackTrace()` / `printStackTrace()`) | Các frame và method khi từng exception được tạo/ném nằm ở đâu? | Framework frames nhiều; có thể bị rút gọn hoặc log chưa đủ |

**Root cause** theo thuật ngữ của Java thường là exception ở **cuối chuỗi `getCause()`**. Nhưng “exception sâu nhất” **không luôn đủ để xác định giải pháp**. Ví dụ `ConnectException: Connection refused` ở đáy chuỗi chỉ mô tả kết nối bị từ chối; cần đối chiếu cấu hình host/port, container network, credentials, service availability và thời điểm startup để xác định nguyên nhân vận hành thực sự.

Bài tập trung vào phương pháp đọc log, hiểu `Throwable`, quan sát các exception Spring Boot thường gặp, thiết kế logging giữ nguyên cause chain, và tạo phép thử Java 17+/Spring Boot có thể tái hiện lỗi một cách kiểm soát.

## 2. Throwable: cấu trúc một exception trong Java 17+

Mọi exception và error của Java đều kế thừa `java.lang.Throwable`. Một đối tượng `Throwable` có thể chứa:

- **Class/type:** ví dụ `IllegalArgumentException`, `ConnectException` hoặc `BeanCreationException`.
- **Message:** chuỗi do người viết exception đặt, đôi khi null.
- **Stack trace:** những `StackTraceElement` liên quan đến điểm lỗi.
- **Cause:** một `Throwable` khác giải thích vì sao exception này được tạo.
- **Suppressed exceptions:** những lỗi phụ, điển hình là lỗi khi đóng resource trong `try-with-resources`.

~~~mermaid
flowchart LR
    OUT["BeanCreationException: không tạo bean"] -->|"getCause"| MID["BeanInstantiationException: factory method lỗi"]
    MID -->|"getCause"| ROOT["IllegalArgumentException: cấu hình không hợp lệ"]
    OUT -.->|"getSuppressed, nếu có"| SIDE["Lỗi phụ khi cleanup"]
~~~

Trong mô hình này, `OUT` là exception ngoài cùng và `ROOT` là exception cuối đường `getCause()`. Lỗi phụ nằm ở **nhánh khác**, không nên trộn nó thành một `Caused by` tiếp theo.

### API cần biết

| API | Kết quả | Khi dùng |
| --- | --- | --- |
| `getMessage()` | `String`, có thể `null` | Đọc thông điệp của **một** exception |
| `toString()` | Thường gồm tên class và message | Hiển thị nhanh loại exception ngoài cùng |
| `getCause()` | `Throwable` hoặc `null` | Duyệt nguyên nhân trực tiếp |
| `getStackTrace()` | `StackTraceElement[]` | Phân tích vị trí tạo/ném exception |
| `printStackTrace()` | In exception, causes và suppressed xuống stream | Debug độc lập hoặc khi chưa có logger |
| `getSuppressed()` | `Throwable[]` | Tìm lỗi phụ phát sinh trong dọn resource |
| `initCause(Throwable)` | Gắn cause trong một số trường hợp hợp lệ | Khi một API chưa dùng constructor có cause; thường ưu tiên constructor |
| `addSuppressed(Throwable)` | Gắn lỗi phụ vào exception chính | Library/resource-management; không thay thế `initCause` |

**Đừng tự tạo một `RuntimeException` mới chỉ với message** khi có một exception gốc quan trọng cần bảo tồn. Constructor như `new IllegalStateException("Could not initialize", cause)` lưu lại chain; constructor chỉ có message không làm việc đó.

## 3. Đọc một stack trace theo đúng hướng

Ví dụ đơn giản:

~~~text
org.springframework.beans.factory.BeanCreationException:
Error creating bean with name 'pricingClient'
    at org.springframework.beans.factory.support.AbstractAutowireCapableBeanFactory...
Caused by: org.springframework.beans.BeanInstantiationException:
Failed to instantiate [com.example.PricingClient]
    at org.springframework.beans.factory.support.SimpleInstantiationStrategy...
Caused by: java.lang.IllegalArgumentException:
pricing.base-url must not be blank
    at com.example.config.PricingConfiguration.pricingClient(PricingConfiguration.java:42)
    ... 24 common frames omitted
~~~

Cách đọc nên làm:

1. **Xác định thời điểm thất bại:** nếu log là `Application run failed`, lỗi xảy ra trong đường `SpringApplication.run`. Nếu log phát ra sau `ApplicationReadyEvent`, đó có thể là lỗi runtime chứ không phải startup.
2. **Ghi tên bean** trong exception bọc như `pricingClient`; tên đó định hướng nơi tìm factory method, constructor hoặc dependency.
3. **Lần theo từng dòng `Caused by:`** thay vì dừng ở wrapper đầu tiên.
4. **Tìm exception đầu tiên đủ cụ thể về điều kiện sai:** chẳng hạn `pricing.base-url must not be blank`, `Port 8080 was already in use` hoặc `NoSuchBeanDefinitionException`.
5. **Tìm frame đầu tiên do ứng dụng sở hữu** gần cause có ý nghĩa, ví dụ `com.example.config.PricingConfiguration.pricingClient`.
6. **Đọc phần còn lại để hiểu ngữ cảnh:** bean nào yêu cầu bean lỗi, profile/property nào đang active, lỗi trước đó trong log, và liệu có suppressed/related errors hay không.
7. **Kiểm chứng bằng thay đổi nhỏ có kiểm soát**, không đoán mò: xác nhận value được bind, thử port, kiểm tra dependency, hoặc tái chạy trong cùng môi trường.

### Dòng “... N common frames omitted” không có nghĩa thiếu cause

Java `Throwable.printStackTrace()` có thể rút gọn những stack frames lặp lại với exception bao ngoài để tránh in lại nhiều dòng. Đó là định dạng hiển thị bình thường; nó **không có nghĩa phần nguyên nhân bị bỏ mất**.

Nếu log bị hệ thống thu thập cắt/truncate, tình huống khác: `Caused by` có thể thật sự chưa được gửi/ghi. Cần lấy bản log đầy đủ trong khoảng startup, tăng giới hạn message của collector hợp lý hoặc sửa cách cấu hình logging.

### Đọc từ dưới lên nhưng không bỏ ngữ cảnh trên

Một quy tắc thực dụng là đọc exception sâu nhất trước để biết điều kiện cụ thể, rồi đi ngược từ dưới lên:
- Tại sao điều kiện đó xảy ra?
- Nó nằm ở constructor/factory nào?
- Bean nào phụ thuộc vào bean đó?
- Vì sao Spring cần bean đó ở giai đoạn startup hiện tại?

Không tự động sửa “class ở đáy stack” nếu đó là library hoặc JDBC driver. Code hoặc cấu hình ứng dụng gọi library với input sai mới có thể là nguyên nhân thực.

## 4. Ví dụ Java 17 thuần: tạo chuỗi cause rõ ràng

Trước khi đọc stack trace của Spring Boot, hãy tạo một chương trình Java thuần để nhìn thấy chuỗi nguyên nhân.

Tạo file **`ThrowableChainLab.java`**:

~~~java
import java.io.IOException;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

public final class ThrowableChainLab {

    public static void main(String[] args) {
        Throwable root = new IllegalArgumentException(
                "SETTING_NOT_NUMERIC");

        Throwable service = new IllegalStateException(
                "SERVICE_INITIALIZATION_FAILED", root);

        RuntimeException outer = new RuntimeException(
                "APP_BOOTSTRAP_FAILED", service);

        // Đây là lỗi phụ, không phải cause của outer.
        outer.addSuppressed(new IOException(
                "OPTIONAL_CLOSE_FAILED"));

        printChain(outer);
        System.out.println("SUPPRESSED_COUNT="
                + outer.getSuppressed().length);
        System.out.println("SUPPRESSED_TYPE="
                + outer.getSuppressed()[0].getClass().getSimpleName());
    }

    private static void printChain(Throwable failure) {
        Set<Throwable> seen = Collections.newSetFromMap(
                new IdentityHashMap<>());

        Throwable current = failure;
        Throwable deepest = failure;
        int index = 0;

        while (current != null && seen.add(current)) {
            System.out.println("CAUSE[" + index + "]="
                    + current.getClass().getSimpleName()
                    + ": " + current.getMessage());
            deepest = current;
            current = current.getCause();
            index++;
        }

        System.out.println("ROOT_TYPE="
                + deepest.getClass().getSimpleName());
        System.out.println("ROOT_MESSAGE=" + deepest.getMessage());
    }
}
~~~

Build và chạy bằng Java 17+:

~~~bash
javac -encoding UTF-8 ThrowableChainLab.java
java ThrowableChainLab
~~~

Output do chương trình chủ động in, theo đúng thứ tự:

~~~text
CAUSE[0]=RuntimeException: APP_BOOTSTRAP_FAILED
CAUSE[1]=IllegalStateException: SERVICE_INITIALIZATION_FAILED
CAUSE[2]=IllegalArgumentException: SETTING_NOT_NUMERIC
ROOT_TYPE=IllegalArgumentException
ROOT_MESSAGE=SETTING_NOT_NUMERIC
SUPPRESSED_COUNT=1
SUPPRESSED_TYPE=IOException
~~~

Ở đây:
- `CAUSE[0]` là lỗi ngoài cùng, chỉ mô tả thất bại khởi tạo ứng dụng.
- `CAUSE[1]` mô tả lỗi tầng service.
- `CAUSE[2]` là thông điệp cụ thể hơn về dữ liệu sai.
- `SUPPRESSED_COUNT=1` cho thấy lỗi cleanup là **nhánh phụ**, không phải một tầng trong chain.

### Vì sao dùng IdentityHashMap trong vòng lặp?

Trong các exception bình thường, `getCause()` đi đến `null`. Nhưng `Throwable` có thể được tùy biến bởi code bất thường; nếu vì lý do nào đó cause graph có vòng hoặc cùng object xuất hiện lại, một vòng `while (cause != null)` mù quáng có thể lặp mãi. `Collections.newSetFromMap(new IdentityHashMap<>())` đánh dấu **object identity**, không dựa vào method `equals`, giúp trình duyệt chẩn đoán dừng an toàn.

Đây là biện pháp phòng vệ khi viết tiện ích log/diagnostics; không có nghĩa Java thường xuyên tạo cause graph vòng.

### Điều gì xảy ra nếu chỉ lấy message ngoài cùng?

~~~java
System.out.println(outer.getMessage());
~~~

Kết quả chỉ là:

~~~text
APP_BOOTSTRAP_FAILED
~~~

Mất thông điệp `SETTING_NOT_NUMERIC`. Muốn giữ chain trong log, log **Throwable object**, không chỉ log text của nó.

## 5. Giữ lại nguyên nhân khi ném exception qua nhiều tầng

### Cách làm mất cause

~~~java
try {
    connectToRemoteService();
} catch (IOException e) {
    throw new IllegalStateException("Cannot initialize remote client");
}
~~~

Đây là snippet, cần method `connectToRemoteService()`. Người debug chỉ thấy `IllegalStateException`, không biết `IOException` gốc là timeout, DNS, connection reset hay lỗi khác.

### Cách đúng: wrap và truyền cause

~~~java
try {
    connectToRemoteService();
} catch (IOException e) {
    throw new IllegalStateException(
            "Cannot initialize remote client", e);
}
~~~

Điều này bảo tồn `e` dưới `getCause()`, giúp các tầng phía ngoài tiếp tục biết lỗi I/O gốc.

### Đừng chỉ tạo cause rồi mất stack

Một lỗi logging hay gặp:

~~~java
logger.error("Startup failure: {}", exception.getMessage());
~~~

Snippet này chỉ ghi thông điệp, không tự in toàn bộ stack trace. Nếu muốn logger SLF4J in throwable cùng chain:

~~~java
logger.error("Startup failure", exception);
~~~

Đây là snippet cần biến `logger` là `org.slf4j.Logger` hoặc logger tương thích, và biến `exception` là `Throwable`. Thông thường logging framework sẽ in stack trace, cause chain và các suppressed exceptions tùy cấu hình encoder/layout.

**Không log cùng một exception ở mọi tầng** nếu nó sẽ được ném lên trên và log lại nhiều lần: dễ gây hàng trăm dòng trùng nhau mà không tăng thông tin. Một nguyên tắc hợp lý là wrap kèm context khi đi qua boundary và log đầy đủ **một lần tại boundary xử lý cuối**, trừ khi có nhu cầu observability riêng.

### Message ngoài cùng có thể chứa message của cause

Một số exception Spring tự ghép nested cause vào `getMessage()`. Điều này có thể làm thông điệp ngoài cùng nhìn dài và hữu ích hơn. Nhưng **vẫn không nên thay thế `getCause()` bằng parse text**: thông điệp có thể mất type, stack frames, suppressed branches hoặc bị cấu hình khác nhau theo phiên bản.

## 6. Chuỗi cause trong Spring Framework và Spring Boot

Một lỗi khởi tạo thường đi qua:

~~~mermaid
flowchart TD
  A["SpringApplication.run"] --> B["ApplicationContext.refresh"]
  B --> C["Pre-instantiate singleton beans"]
  C --> D["Tạo bean theo constructor / @Bean"]
  D --> E["Bean method/constructor ném exception"]
  E -. "bọc" .-> F["BeanInstantiationException"]
  F -. "bọc" .-> G["BeanCreationException"]
  G -. "lan" .-> H["Startup failure handling"]
  H --> I["FailureAnalyzer / log / ApplicationFailedEvent"]
~~~

Sơ đồ **minh họa trường hợp bean factory method ném lỗi**. Không phải mọi startup exception đều tạo đủ ba lớp wrapper. Ví dụ lỗi bind property, web server port hoặc classpath có cấu trúc nguyên nhân khác.

### Các exception Spring có vai trò gì?

| Lớp/nhóm | Ý nghĩa thường gặp | Hướng đọc tiếp |
| --- | --- | --- |
| `BeanCreationException` | Container không tạo được bean | Xem bean name, bean definition/resource và cause |
| `UnsatisfiedDependencyException` | Một dependency cần inject không thỏa | Xem dependency nào thiếu, sau đó cause của dependency |
| `BeanInstantiationException` | Không khởi tạo được instance qua constructor/factory | Xem stack và exception từ constructor/factory |
| `NoSuchBeanDefinitionException` | Không có bean hợp lệ theo yêu cầu | Kiểm tra scan/configuration/conditional bean/profile |
| `NoUniqueBeanDefinitionException` | Có nhiều bean ứng viên, không chọn được | Kiểm tra `@Qualifier`, `@Primary`, generic/type |
| `BindException` hoặc validation-related failure | Cấu hình không được bind/validate đúng | Kiểm tra property key, type, value, source và constraints |
| `PortInUseException`/web server startup error | Không bind được port | Xác định process/port/configuration |
| `ClassNotFoundException`, `NoClassDefFoundError` | Thiếu hoặc không load/initialize được class | Kiểm tra runtime dependencies, shaded JAR, JVM compatibility |
| `ConnectException`, `UnknownHostException` | Không thể kết nối/resolve service bên ngoài | Kiểm tra endpoint, DNS, mạng, service uptime và policy |
| `IllegalArgumentException`, `IllegalStateException` do app ném | Vi phạm điều kiện/argument/invariant | Đọc thông điệp và frame ứng dụng đầu tiên |

**Đừng chỉ dựa vào tên exception ngoài cùng để tự động chọn “sửa cấu hình X”.** Ví dụ `UnsatisfiedDependencyException` có thể do bean implementation bị lỗi khi khởi tạo, chứ không nhất thiết do thiếu một `@Component`.

### Spring NestedRuntimeException có tiện ích riêng

Một số exception Spring kế thừa `org.springframework.core.NestedRuntimeException`, cung cấp:

~~~java
Throwable root = exception.getRootCause();
Throwable mostSpecific = exception.getMostSpecificCause();
~~~

Đây là snippet khi `exception` có kiểu thích hợp. Theo API:
- `getRootCause()` trả **innermost cause**, hoặc `null` nếu không có cause.
- `getMostSpecificCause()` trả innermost cause, **hoặc chính exception** nếu không có cause.

Không dùng `getRootCause()` rồi dereference ngay nếu nó có thể null. Đối với `Throwable` bất kỳ (không nhất thiết là Spring exception), có thể tự đi `getCause()` an toàn như ví dụ ở mục 4.

### BeanCreationException có “related causes”

`BeanCreationException` có `getRelatedCauses()`, mô tả các lỗi có liên quan phát sinh trong quá trình tạo bean nhưng **không nhất thiết là direct cause** trong chuỗi `getCause()`. Nếu đọc từ object Java trong tooling/debugger, nên kiểm tra cả nhánh này khi có dữ liệu. Không tự gán các related causes thành chuỗi tuyến tính hay chỉ chọn nguyên nhân cuối rồi bỏ qua những lỗi song song.

## 7. Spring Boot FailureAnalyzer: thông báo dễ hành động không thay thế cause chain

Khi Spring Boot thất bại ở startup, những `FailureAnalyzer` được đăng ký có cơ hội phân tích exception và hiển thị một bản báo cáo thân thiện, ví dụ dạng:

~~~text
***************************
APPLICATION FAILED TO START
***************************

Description:
Embedded servlet container failed to start. Port 8080 was already in use.

Action:
Identify and stop the process using port 8080,
or configure the application to listen on another port.
~~~

Đây là **mẫu nội dung minh họa** từ tình huống port đã sử dụng, không phải format cố định của mọi analyzer. Mục tiêu là gắn **Description + Action** cho loại lỗi mà analyzer nhận diện được.

Nếu log có `APPLICATION FAILED TO START` và chỉ dẫn rõ ràng, hãy đọc nó trước. Nhưng nếu action vẫn quá chung hoặc không khớp với thực tế, tiếp tục điều tra exception cause chain và môi trường. `FailureAnalyzer` không bắt buộc biến mọi exception thành một lời giải chính xác.

### Khi không có FailureAnalyzer phù hợp

Boot có thể log exception khởi động bình thường. Nếu vấn đề liên quan auto-configuration/conditional beans, có thể bật:

~~~bash
java -jar app.jar --debug
~~~

hoặc logger DEBUG cho `ConditionEvaluationReportLoggingListener`. **`--debug` không có nghĩa luôn in cause chain của mọi lỗi theo cùng định dạng**; nó cung cấp thêm condition evaluation report, giúp giải thích vì sao một số auto-configurations match hoặc không match.

Cần phân biệt:
- **Cause chain:** tại sao một exception được ném và bọc.
- **Condition evaluation report:** điều kiện cấu hình nào phù hợp hoặc không.
- **Failure analysis:** giải thích lỗi được phân loại và hướng hành động.
- **Application startup events:** thời điểm failure xảy ra.

Dùng kết hợp khi cần; không phải bốn tên khác nhau của cùng một đối tượng.

### Viết analyzer riêng khi có lỗi thường gặp trong framework nội bộ

Spring Boot hỗ trợ tạo `FailureAnalyzer` của riêng thư viện/ứng dụng. `AbstractFailureAnalyzer<T>` cung cấp khả năng tìm một exception kiểu `T` trong chain, sau đó trả `FailureAnalysis(description, action, cause)`.

Đăng ký một analyzer custom qua:

~~~properties
# src/main/resources/META-INF/spring.factories
org.springframework.boot.diagnostics.FailureAnalyzer=\
com.example.startup.DemoFailureAnalyzer
~~~

Đây là file **spring.factories** chứ không phải `application.properties`. Đăng ký qua metadata Boot cho phép analyzer được tải khi context startup có thể chưa khởi tạo hoàn chỉnh. Tránh trông chờ một bean thường phải được tạo thành công rồi mới phân tích lỗi khi chính quá trình tạo bean thất bại.

Trong bài demo phía dưới có một phiên bản tùy chọn.

## 8. Ví dụ Spring Boot 3.5.x / Java 17+: gây lỗi có chủ đích và tìm root cause

Mục tiêu: tái tạo tình huống **constructor/factory bean thất bại** để thấy exception đi qua Spring wrapper và tìm **IllegalArgumentException gốc**.

Dùng Spring Boot **3.5.16**, Java **17+**, Maven. Chỉ cần `spring-boot-starter`, không cần web server.

Cấu trúc:

~~~text
startup-cause-demo/
├── pom.xml
└── src/main/java/com/example/startup/
    ├── StartupCauseApplication.java
    └── CauseChainPrinter.java
~~~

### 8.1. File pom.xml

~~~xml
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
    <artifactId>startup-cause-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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

### 8.2. File StartupCauseApplication.java

~~~java
package com.example.startup;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class StartupCauseApplication {

    public static void main(String[] args) {
        try {
            SpringApplication.run(StartupCauseApplication.class, args);
        } catch (RuntimeException failure) {
            // Chỉ dành cho lab: Boot có thể đã log lỗi.
            CauseChainPrinter.print(failure);
            throw failure;
        }
    }

    @Bean
    StartupGuard startupGuard(Environment environment) {
        boolean fail = environment.getProperty(
                "demo.fail", Boolean.class, false);

        if (fail) {
            throw new IllegalStateException(
                    "Failed to create StartupGuard",
                    new IllegalArgumentException(
                            "DEMO_MISSING_SETTING"));
        }

        return new StartupGuard("OK");
    }

    @Bean
    CommandLineRunner report(StartupGuard guard) {
        return args -> System.out.println(
                "STARTUP_SUCCESS guard=" + guard.status());
    }

    record StartupGuard(String status) {
    }
}
~~~

**Điểm quan trọng trong code:**

- `@Bean startupGuard(...)` được Spring gọi trong quá trình tạo singleton cần cho startup.
- Khi `--demo.fail=true`, method cố tình ném `IllegalStateException` với cause là `IllegalArgumentException("DEMO_MISSING_SETTING")`.
- Spring có thể bọc thêm `BeanInstantiationException` và `BeanCreationException` khi factory method lỗi. Số lượng wrapper là chi tiết framework, không nên khẳng định cố định.
- `main` nhận lại một `RuntimeException` từ `SpringApplication.run` trong trường hợp lab này, in chain rồi **ném lại**. Ném lại rất quan trọng: không được nuốt lỗi khiến hệ thống/CI tưởng startup thành công.
- `CommandLineRunner` chỉ chạy khi context tạo thành công; nếu lỗi ở bean, đường runner không hoàn tất.
- `StartupGuard` là nested record có cú pháp Java 17 hợp lệ và chỉ mang một giá trị để kiểm tra.

### 8.3. File CauseChainPrinter.java

~~~java
package com.example.startup;

import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

public final class CauseChainPrinter {
    private CauseChainPrinter() {
    }

    public static void print(Throwable failure) {
        Set<Throwable> visited = Collections.newSetFromMap(
                new IdentityHashMap<>());

        Throwable current = failure;
        Throwable deepest = failure;
        int depth = 0;

        while (current != null && visited.add(current)) {
            System.err.println("CAUSE[" + depth + "]="
                    + current.getClass().getName()
                    + ": " + String.valueOf(current.getMessage()));

            deepest = current;
            current = current.getCause();
            depth++;
        }

        if (deepest != null) {
            System.err.println("ROOT_TYPE="
                    + deepest.getClass().getName());
            System.err.println("ROOT_MESSAGE="
                    + String.valueOf(deepest.getMessage()));
        }
    }
}
~~~

`CauseChainPrinter` không phụ thuộc Spring: nó nhận `Throwable` và duyệt từ exception ngoài cùng tới innermost. `String.valueOf(...)` tránh `NullPointerException` nếu một message là null, nhưng **không che bí mật**: production logging phải có redaction và chính sách bảo vệ dữ liệu riêng.

### 8.4. Build và chạy thành công

~~~bash
mvn -q -DskipTests package
java -jar target/startup-cause-demo-0.0.1-SNAPSHOT.jar
~~~

Dòng do runner chủ động in:

~~~text
STARTUP_SUCCESS guard=OK
~~~

Spring Boot cũng in các startup logs theo cấu hình logging, nên không xem dòng trên là toàn bộ stdout.

### 8.5. Chạy nhánh lỗi

~~~bash
java -jar target/startup-cause-demo-0.0.1-SNAPSHOT.jar \
  --demo.fail=true
~~~

Trong các dòng diagnostic do demo hoặc Boot in ra, tìm:

~~~text
ROOT_TYPE=java.lang.IllegalArgumentException
ROOT_MESSAGE=DEMO_MISSING_SETTING
~~~

Dòng từ `CauseChainPrinter` là kết quả **kỳ vọng có thể dự đoán** nhờ code chủ động tạo root exception, nhưng số lượng và kiểu của những dòng `CAUSE[0]`, `CAUSE[1]`, ... có thể khác theo cách Spring Boot/Spring Framework wrap exception. Đừng viết assertion “phải có chính xác bốn CAUSE lines” nếu điều đó không thuộc contract của ứng dụng.

Boot còn có thể log `Application run failed`, `BeanCreationException`, tên bean và stack trace. Nếu `SpringApplication.run` rethrow thành lỗi khác trong cấu hình đặc thù, cần bảo đảm logging/catch phù hợp; đây là lab của một lỗi factory method runtime thông thường, không phải template xử lý mọi `Error` nghiêm trọng.

**Không có dòng `STARTUP_SUCCESS guard=OK` trong nhánh lỗi**, vì bean `StartupGuard` bị reject trước khi runner có thể chạy thành công.

Lệnh Bash dùng `\` nối dòng; trên Windows PowerShell/cmd, dùng lệnh một dòng hoặc cú pháp nối dòng của shell tương ứng.

### 8.6. Đọc một log startup đầy đủ

Trên Linux/Bash:

~~~bash
java -jar target/startup-cause-demo-0.0.1-SNAPSHOT.jar \
  --demo.fail=true >startup.log 2>&1

# Lệnh Java có thể trả exit code khác 0; xem ở ngay lệnh trước.
echo "exit=$?"

# Tìm các mốc quan trọng, không dựa vào chúng như bản log đầy đủ.
grep -nE 'Application run failed|Caused by:|CAUSE\[|ROOT_|DEMO_MISSING_SETTING' \
  startup.log
~~~

Nếu chạy trong script có `set -e`, một `java -jar` trả mã khác 0 có thể khiến script kết thúc trước khi `grep` chạy. Dùng `set +e` quanh lệnh tạo failure trong lab, sau đó lưu exit status và bật lại `set -e` nếu cần.

**Cần lưu cả stdout và stderr**, vì Boot logging, stack traces và code demo có thể ghi vào các stream khác nhau.

## 9. Dùng ApplicationFailedEvent khi cần quan sát startup failure

Spring Boot phát `ApplicationFailedEvent` khi xảy ra exception trên đường startup. Event này có `getException()` để lấy `Throwable` và `getApplicationContext()` có thể chưa khả dụng trong lỗi rất sớm.

Một số application events được phát **trước khi context tồn tại**, vì vậy listener `@Component`/`@Bean` thông thường **không bảo đảm** nhận được mọi startup failure. Đăng ký một listener programmatic **trước `run`** nếu cần theo dõi lỗi từ rất sớm:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.context.ApplicationListener;

// Bên trong main(), thay vì dùng thẳng static run():
SpringApplication app = new SpringApplication(MyApplication.class);

app.addListeners(
        (ApplicationListener<ApplicationFailedEvent>) event ->
                CauseChainPrinter.print(event.getException()));

app.run(args);
~~~

Đây là **snippet**, cần class `MyApplication` và `CauseChainPrinter` thực tế. Đừng chèn nguyên vào file demo đồng thời giữ `SpringApplication.run(...)` cũ nếu không muốn chạy app hai lần.

**Giới hạn của listener:**
- Context có thể null hoặc đã không còn hợp lệ, tùy startup phase.
- Không nên yêu cầu bean/DB/logger tùy biến chưa chắc được khởi tạo.
- Nếu failure listener tự ném exception, có thể tạo thêm nhiễu và che root cause ban đầu.
- Event thông báo failure, không phải callback để “nuốt lỗi rồi phục hồi” một startup đã thất bại.
- Nếu ứng dụng dùng context hierarchy, sự kiện có thể được truyền lên parent; cần xác định đúng event/context khi thống kê.

### Chọn giữa listener, catch ở main và FailureAnalyzer

| Điểm can thiệp | Ưu điểm | Khi nên dùng |
| --- | --- | --- |
| `main` bắt exception và rethrow | Dễ minh họa, không cần event mechanism | Lab/CLI startup, kiểm thử cause chain |
| `ApplicationFailedEvent` listener sớm | Bắt tín hiệu thất bại của `SpringApplication` | Observability startup nhưng hạn chế dependencies |
| `FailureAnalyzer` | Tạo thông báo Description/Action chính xác hơn | Thư viện/framework có loại lỗi lặp lại |
| Logging config | In toàn bộ stack trace và context | Hầu hết ứng dụng production |
| Integration test | Xác nhận exception xảy ra và root cause | Ngăn regression, cấu hình bắt buộc |

Không nhất thiết triển khai cả ba callback trong một ứng dụng nhỏ. Việc log một stack trace đầy đủ từ nhiều nơi có thể tạo duplicate noise lớn.

## 10. Tùy chọn mở rộng: FailureAnalyzer cho nguyên nhân cụ thể

Nếu lỗi `DEMO_MISSING_SETTING` xảy ra thường xuyên trong một thư viện nội bộ, có thể thêm analyzer:

**File `src/main/java/com/example/startup/DemoFailureAnalyzer.java`:**

~~~java
package com.example.startup;

import org.springframework.boot.diagnostics.AbstractFailureAnalyzer;
import org.springframework.boot.diagnostics.FailureAnalysis;

public final class DemoFailureAnalyzer
        extends AbstractFailureAnalyzer<IllegalArgumentException> {

    @Override
    protected FailureAnalysis analyze(
            Throwable rootFailure, IllegalArgumentException cause) {

        if (!"DEMO_MISSING_SETTING".equals(cause.getMessage())) {
            return null;
        }

        return new FailureAnalysis(
                "Demo startup guard was rejected by a deliberate flag.",
                "Run without --demo.fail=true or fix the required setting.",
                cause);
    }
}
~~~

**File `src/main/resources/META-INF/spring.factories`:**

~~~properties
org.springframework.boot.diagnostics.FailureAnalyzer=\
com.example.startup.DemoFailureAnalyzer
~~~

Analyzer nhận exception root do Spring truyền và có thể tìm `IllegalArgumentException` trong chain. Việc so message là **chủ đích của lab**, còn production nên dùng **một exception type riêng**, tránh so khớp ngẫu nhiên thông điệp có thể thay đổi.

Sau khi thêm analyzer, build lại:

~~~bash
mvn -q -DskipTests package
java -jar target/startup-cause-demo-0.0.1-SNAPSHOT.jar \
  --demo.fail=true
~~~

Nếu được Boot nhận diện, báo cáo `APPLICATION FAILED TO START` có thể mô tả nguyên nhân và action do analyzer tạo. `CauseChainPrinter` trong main vẫn in các dòng CAUSE/ROOT nếu code tương ứng chạy. **Analyzer không sửa lỗi hay thay startup thành success**; nó giúp người vận hành biết phải làm gì tiếp theo.

Đăng ký analyzer qua `META-INF/spring.factories` theo tài liệu Boot; chỉ thêm `@Component` vào analyzer không phải lựa chọn tương đương cho mọi lỗi trong lúc context chưa khởi tạo xong.

## 11. Khi deepest cause chưa đủ: suppressed, related, async và SQL chains

### 11.1. Suppressed exception

Trong `try-with-resources`, nếu cả phần công việc chính và `close()` ném exception, lỗi từ `close` thường được lưu trong `getSuppressed()` của exception chính:

~~~java
import java.io.Closeable;
import java.io.IOException;

class ResourceDemo {
    void run() {
        Closeable resource = () -> {
            throw new IOException("CLOSE_FAILED");
        };

        try (resource) {
            throw new IOException("READ_FAILED");
        } catch (IOException e) {
            System.out.println(e.getMessage());
            System.out.println(e.getSuppressed()[0].getMessage());
        }
    }
}
~~~

Đây là một **class snippet Java 17 hợp lệ**; khi gọi `new ResourceDemo().run()`, hai dòng in là:

~~~text
READ_FAILED
CLOSE_FAILED
~~~

`CLOSE_FAILED` là lỗi phụ khi cleanup, không phải `getCause()` của `READ_FAILED`. Nếu chỉ đi cause chain, bạn bỏ qua nhánh này.

### 11.2. BeanCreationException related causes

Spring `BeanCreationException.getRelatedCauses()` có thể trả các lỗi liên quan phát sinh trong lúc container cố tạo bean. Chúng **không bắt buộc** là một đường `cause→cause`. Khi một bean có nhiều điều kiện cấu hình/lifecycle phức tạp, hãy xem chúng trong log/debugger nếu có.

### 11.3. Future, CompletionException và ExecutionException

Tác vụ chạy async trong `CompletableFuture` hoặc `Future` có thể bọc lỗi thật bằng `CompletionException` hoặc `ExecutionException`. Khi một `ApplicationRunner`/startup listener chờ `Future.get()`, tầng ngoài có thể là `ExecutionException` trong khi nguyên nhân gốc thuộc thread khác.

Tương tự, nếu callback startup chạy bất đồng bộ **và không được chờ**, exception có thể xuất hiện **sau khi app đã ready**, không nhất thiết gây startup failure. Đọc stack/phase và cơ chế async trước khi cho rằng mọi log lỗi trong quá trình deploy đều là lỗi `SpringApplication.run`.

### 11.4. Reflection, InvocationTargetException

Khi gọi method qua reflection, Java có thể bọc lỗi mục tiêu trong `InvocationTargetException`. `getCause()` thường trả exception mục tiêu; còn API `getTargetException()` trả exception đó theo thiết kế reflection. Vẫn cần xem frame code ứng dụng gây lỗi, không dừng ở chữ “InvocationTargetException”.

### 11.5. SQLException.nextException

Một số JDBC failures có chuỗi `SQLException.getNextException()` riêng, bên cạnh `getCause()`. Nếu liên quan database startup (migration, pool, schema), cần xem SQL state, vendor code, next exceptions và database server logs. Không giả định deepest `getCause()` luôn chứa toàn bộ SQL diagnostics.

### 11.6. Multiple causes và graph không tuyến tính

Một failure có thể có **nhiều nguyên nhân độc lập**: nhiều beans lỗi khi init, nhiều cleanup failures, hoặc một retry sau lần lỗi trước. Một exception ở cuối một chain chỉ là một nhánh. Với thông tin đa nguồn, hãy tách **lỗi kích hoạt chính**, **lỗi thứ cấp do cleanup**, **lỗi xảy ra sau đó**. Tránh chọn dòng cuối của một file log rồi tuyên bố nó là root cause của mọi failure.

## 12. Phân loại tình huống Spring Boot thường gặp

### A. Error creating bean with name ...

**Đọc tới các tầng sâu hơn.** Nếu thấy `UnsatisfiedDependencyException`, đọc parameter/constructor và bean dependency được yêu cầu. Nếu tiếp theo là `NoSuchBeanDefinitionException`, kiểm tra component scan, `@Conditional...`, `@Profile`, `@Qualifier`, generic type và bean registration. Nếu tiếp theo là exception trong factory method, xem đúng method đó và dữ liệu nó nhận.

Không sửa bằng cách đánh dấu `@Lazy` toàn bộ bean để “cho app qua startup”. Lazy có thể **chuyển lỗi sang request đầu tiên** và tạo production incident muộn hơn.

### B. Failed to bind properties under ...

Đọc key và target type. Ví dụ `app.retry.limit` có chuỗi không parse được thành `int`. Kiểm tra những nguồn cấu hình có thể override: CLI, JVM system properties, environment variables, YAML/properties, profile-specific files và secrets. Nếu có validation constraint, đọc cause validation. Không log raw value nếu nó có thể chứa secret.

### C. Port already in use

Ở ngoài có thể là `WebServerException`; analyzer của Boot thường trình bày Description/Action hữu ích. Kiểm tra port đang được dùng, network namespace/container/host port mapping và config của embedded server. Không tự thay hàng loạt ports khi root cause là một process cũ chưa được dừng.

### D. Connection refused / UnknownHost

Nếu cause cuối là `java.net.ConnectException`, `UnknownHostException` hoặc timeout, đọc class/method ứng dụng gọi remote dependency. Xác minh host/port, DNS, network policy, certificate/TLS, credential và thời hạn startup. `Connection refused` nói rằng endpoint từ chối kết nối tại thời điểm đó, không chứng minh service bị down vĩnh viễn.

### E. BeanInstantiationException: constructor threw exception

Tìm frame constructor của app và exception mà constructor thực sự ném. Nếu constructor làm I/O dài hoặc gọi remote service, xem xét tái cấu trúc khởi tạo và validation phù hợp. Không sử dụng try/catch để giấu lỗi cốt lõi, rồi giả định bean sẵn sàng phục vụ.

### F. NoClassDefFoundError

Đừng suy rằng chỉ do chưa thêm dependency. Class có thể tồn tại nhưng không initialize được (`ExceptionInInitializerError`), classpath runtime khác test/build, version mismatch hoặc package đổi giữa major versions (ví dụ `javax.*`/`jakarta.*`). Đọc cause của lỗi đầu tiên và kiểm tra dependency tree/JAR.

### G. Circular references

Một số circular constructor dependencies bị framework phát hiện trong lúc tạo bean. Chuỗi exception có thể nhắc nhiều bean theo vòng. Hãy vẽ dependency graph và xem vì sao hai service cần tham chiếu trực tiếp nhau, thay vì bật cấu hình cho phép vòng như một cách sửa mặc định. Giải pháp thường là tách trách nhiệm, thêm abstraction hoặc thay luồng dependency hợp lý.

### H. Failure ngay trong Environment preparation

Lúc config data/property source được chuẩn bị, `ApplicationContext` chưa sẵn sàng để inject bean. Không mong một `@Component` handler luôn bắt được lỗi này. Đăng ký `ApplicationFailedEvent` listener sớm hoặc dựa vào startup logs/FailureAnalyzer đã đăng ký theo cơ chế Boot.

## 13. Quy trình đọc log nhanh trong thực tế

Một quy trình có thể áp dụng khi nhận một file log dài:

1. **Tách một lần startup cụ thể:** dùng PID, timestamp, container ID và deployment revision. Tránh nối lẫn log từ nhiều lần restart.
2. **Tìm mốc kết thúc:** `Application run failed` hoặc `APPLICATION FAILED TO START`; ghi lại khoảng thời gian trước nó.
3. **Đọc toàn bộ exception block**, không chỉ dòng đầu tiên. Ghi class ngoài cùng và stack.
4. **Lần theo `Caused by:`** cho đến exception sâu nhất trong block; kiểm tra `Suppressed` và related causes.
5. **Đánh dấu frame ứng dụng** đầu tiên gần lỗi; ghi bean name, configuration class và method.
6. **Kiểm tra nguồn cấu hình và dependency thực tế** tại đúng môi trường lỗi, không đoán profile theo laptop dev.
7. **Đọc ConditionEvaluationReport** khi lỗi liên quan `@Conditional`/auto-configuration; dùng `--debug` có kiểm soát.
8. **Xác minh bằng thay đổi tối thiểu và tái khởi động**. Duy trì root cause message hoặc failure test để tránh regression.
9. **Báo cáo nguyên nhân, tác động và bằng chứng**, không chỉ copy một dòng “BeanCreationException”.

### Tìm bằng grep nhưng đừng làm mất context

~~~bash
grep -nE 'APPLICATION FAILED|Application run failed|Caused by:|Suppressed:|BeanCreationException|UnsatisfiedDependencyException' startup.log
~~~

Lệnh này tìm mốc, nhưng kết quả là **các dòng rời rạc**. Tiếp tục đọc log gốc quanh vị trí đó để xem stack frames, lời gọi ứng dụng, profile và các message đã bị lược bỏ.

Khi chạy trong Kubernetes:

~~~bash
kubectl logs POD_NAME -c CONTAINER_NAME --timestamps
kubectl logs POD_NAME -c CONTAINER_NAME --previous --timestamps
~~~

Thay `POD_NAME` và `CONTAINER_NAME` bằng giá trị thực. `--previous` hữu ích khi container vừa crash/restart, nhưng chỉ xem được bản instance trước khi log còn được runtime giữ; nó không phải archive vô hạn.

Trong logging pipeline chia sự kiện thành nhiều JSON records, cần bảo đảm stacktrace được thu thập trọn vẹn. Nếu multi-line Java stack trace bị cắt thành nhiều events không cùng correlation ID, kết quả tìm kiếm có thể làm người đọc sai thứ tự cause.

## 14. Vấn đề bảo mật và độ tin cậy của log

### Tránh log secrets

Message của exception có thể chứa:
- JDBC URL có credential;
- endpoint query string hoặc token;
- property values từ secrets;
- connection strings và filesystem paths;
- payload người dùng.

Không mặc định in `getMessage()` của mọi exception trên public API hoặc gửi toàn bộ stacktrace về HTTP response. Với log nội bộ, cấu hình redaction/permissions và retention phù hợp. Nếu cần báo người dùng, trả thông điệp đã được chuẩn hóa và correlation ID.

### Không nuốt lỗi startup để tạo success giả

~~~java
try {
    SpringApplication.run(App.class, args);
} catch (Exception e) {
    System.out.println(e.getMessage());
    // Sai nếu kết thúc với exit code 0
}
~~~

Đây là **snippet anti-pattern**, không phải app hoàn chỉnh. Nếu method `main` kết thúc bình thường sau khi bắt lỗi, caller có thể quan sát exit code success dù startup thật sự thất bại. Với CLI/job, truyền lỗi ra boundary hoặc dùng exit code khác 0 khi thích hợp.

### Không log cả stacktrace vào một metric label

Số lượng class, method, message và đường dẫn rất nhiều; dùng stack trace làm label khiến metrics high-cardinality, lãng phí tài nguyên. Log/traces giữ chi tiết, còn metrics dùng reason code có cardinality kiểm soát.

### Đừng tự tạo lỗi mới làm mất cause

Khi đưa thêm ngữ cảnh:
- Dùng exception class có constructor nhận `Throwable cause`.
- Lưu type/message gốc.
- Tránh wrap nhiều lớp không bổ sung thông tin.
- Không sửa message gốc để chứa mật khẩu.
- Nếu tầng cao đã log đầy đủ, tầng thấp chỉ cần ném cause kèm context.

## 15. Checklist QA và kiểm thử cho lỗi khởi động

Kiểm tra các tình huống sau trong test/staging:

| Trường hợp | Kỳ vọng xác minh |
| --- | --- |
| Bean khởi tạo thành công | Runner/ready đạt, không có startup failure |
| Bean lỗi cấu hình | Startup thất bại, log có bean name + cause có ý nghĩa |
| Wrapper có nhiều tầng | Cause chain giữ exception gốc |
| Exception không có cause | Trình duyệt nguyên nhân không NPE và trả chính exception |
| Cause có message null | Logging không ném lỗi thứ cấp |
| Suppressed exception | Không bị mất do chỉ log message |
| FailureAnalyzer custom | Có Description/Action khi đúng lỗi và không nuốt exception |
| Environment failure rất sớm | Không phụ thuộc bean listener chưa tồn tại |
| Logging truncation | Thu thập được toàn bộ stacktrace hoặc xác định được vị trí bị cắt |
| Lỗi async/runtime sau ready | Không ghi nhầm thành startup failure |
| Production secret data | Không lọt vào log/app response |
| Exit code | Trường hợp startup fail phản ánh failure tới deployment/CI |

**Không đánh đồng kiểm thử startup với `ApplicationContextRunner` đơn thuần.** `ApplicationContextRunner` tốt để test các cấu hình context có giới hạn; nó không mặc định mô phỏng toàn bộ `SpringApplication.run`, event lifecycle hoặc hành vi của entrypoint trong JAR. Với việc kiểm tra fail-fast và exit code, nên dùng integration test chạy SpringApplication thực hoặc process riêng.

## 16. Câu hỏi ôn tập

**1. Vì sao chỉ đọc `Application run failed` chưa đủ?**  
Đó là thông báo ở tầng tổng; nguyên nhân thực có thể bị bọc nhiều lần.

**2. `Throwable.getMessage()` khác `getCause()` thế nào?**  
Message là chuỗi mô tả một exception. Cause là một Throwable khác giải thích nguyên nhân trực tiếp; có thể tiếp tục duyệt.

**3. Dòng `Caused by:` trong stack trace thể hiện gì?**  
Một exception được gắn làm cause của exception đang được in.

**4. Exception ở đáy chuỗi có luôn đủ để đưa ra cách sửa không?**  
Không. Cần thêm bean name, frame ứng dụng, cấu hình và môi trường.

**5. `getMostSpecificCause()` trong Spring khác `getRootCause()` thế nào?**  
MostSpecific trả chính exception nếu không có cause; rootCause có thể null.

**6. `BeanCreationException` thường cho thêm thông tin nào?**  
Tên bean, ngữ cảnh bean definition và những exception nằm bên trong.

**7. `UnsatisfiedDependencyException` có chắc là thiếu bean không?**  
Không. Dependency có thể tồn tại nhưng bị lỗi khi tạo.

**8. Vì sao phải truyền cause khi wrap exception?**  
Để giữ type, message, stack của nguyên nhân cho tầng trên.

**9. `Suppressed` có nằm trong chuỗi `getCause()` không?**  
Không nhất thiết. Nó là các nhánh lỗi phụ, ví dụ lỗi khi close resource.

**10. Khi nào nên dùng `--debug` trong Spring Boot?**  
Khi cần condition evaluation report để điều tra auto-configuration/conditional beans, không phải như phép thay thế duy nhất cho stacktrace.

**11. `FailureAnalyzer` có làm startup thất bại trở thành thành công không?**  
Không. Nó giải thích lỗi và action cho người vận hành.

**12. Vì sao `@Component` listener chưa đủ cho lỗi bootstrap sớm?**  
Context có thể chưa được tạo khi event rất sớm phát ra.

**13. Nếu trong `main` catch rồi chỉ log message và return, nguy cơ gì?**  
Có thể báo thành công giả/exit code 0 dù app không khởi động được.

**14. Vì sao nên đọc log ở đúng lần restart?**  
Logs của nhiều process/PID có thể xen lẫn và làm lẫn nguyên nhân.

**15. Vì sao không in đầy đủ cause chain vào response HTTP công khai?**  
Thông tin class, đường dẫn, cấu hình hoặc secrets có thể bị lộ.

## 17. Tài liệu chính thức

- [Java SE 17 — Throwable API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): `getCause`, `getSuppressed`, `getStackTrace`, `printStackTrace` và cách Java in nested causes.
- [Spring Boot 3.5 — SpringApplication / Startup Failure](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): `FailureAnalyzer`, failure reports, `--debug` và điều kiện startup.
- [Spring Boot 3.5 — Create Your Own FailureAnalyzer](https://docs.spring.io/spring-boot/3.5/how-to/application.html): `AbstractFailureAnalyzer`, `FailureAnalysis` và đăng ký `spring.factories`.
- [Spring Boot 3.5 — ApplicationFailedEvent API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/event/ApplicationFailedEvent.html): `getException()` và application context có thể chưa sẵn.
- [Spring Boot 3.5 — FailureAnalysis API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/diagnostics/FailureAnalysis.html): Description, Action và cause.
- [Spring Framework — BeanCreationException API](https://docs.spring.io/spring-framework/docs/6.2.3/javadoc-api/org/springframework/beans/factory/BeanCreationException.html): tên bean, related causes và nested exception.
- [Spring Framework — NestedRuntimeException API](https://docs.spring.io/spring-framework/docs/6.2.3/javadoc-api/org/springframework/core/NestedRuntimeException.html): `getRootCause()`, `getMostSpecificCause()` và `contains(...)`.

**Kết luận:** khi Spring Boot không khởi động, đừng dừng ở `BeanCreationException` hay thông báo ngoài cùng. Hãy đọc **cause chain đầy đủ**, đánh dấu exception có điều kiện sai cụ thể, xem **frame ứng dụng và bean phụ thuộc**, rồi kiểm chứng trong đúng môi trường. Các công cụ như `FailureAnalyzer`, `ApplicationFailedEvent` và condition report giúp bổ sung góc nhìn, nhưng không thay thế phép phân tích nguyên nhân có bằng chứng.