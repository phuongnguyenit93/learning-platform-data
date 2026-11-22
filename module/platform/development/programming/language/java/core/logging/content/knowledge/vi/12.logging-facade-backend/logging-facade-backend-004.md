# Binding runtime: cách Facade kết nối Logging Backend trong Java

## 1. Binding runtime là gì?

Trong kiến trúc logging của Java, **facade** cung cấp API chung để ứng dụng phát sự kiện log, còn **backend** thực hiện việc lọc, định dạng và ghi sự kiện ra console, file hoặc hệ thống thu thập. **Binding runtime** là bước tại thời điểm chạy mà facade kết nối với triển khai backend đang có trong môi trường thực thi.

Ví dụ ứng dụng chỉ gọi API của SLF4J:

```java
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(OrderService.class);

void createOrder(String orderId) {
    LOG.info("event=order.created orderId={}", orderId);
}
```

Đây là **đoạn mã minh họa trong lớp `OrderService`**, không phải chương trình độc lập. Cùng một code như vậy có thể ghi bằng Logback hoặc Log4j 2 nếu runtime có đúng provider tương thích và cấu hình backend tương ứng. Business code không cần đổi từ `LOG.info` sang API riêng của backend.

Mô hình tư duy:

```text
Source code Java
    |
    |  import org.slf4j.Logger; LoggerFactory.getLogger(...)
    v
SLF4J API (compile time)
    |
    |  tìm binding/provider trong runtime classpath
    v
Một backend được kết nối (runtime)
    |
    +-- Logback   -> ConsoleAppender / RollingFileAppender / ...
    +-- Log4j 2   -> Appender / Layout / ...
    +-- JUL       -> java.util.logging Handler / Formatter / ...
    +-- Simple    -> đầu ra đơn giản
    +-- NOP       -> cố ý bỏ log
```

Các lựa chọn backend ở sơ đồ **là phương án thay thế nhau**, không phải danh sách JAR cần cài đồng thời. Thực hành tốt là để **ứng dụng chạy** chọn một provider/backend, trong khi các thư viện dùng chung chỉ phụ thuộc facade/API.

### Khi nào kiến thức này hữu ích?

- Chạy ứng dụng mà log biến mất dù code đã gọi `logger.info()`.
- Một build dùng Logback nhưng lúc deploy lại thấy format của SimpleLogger.
- Console báo `multiple bindings`, `multiple providers` hoặc `No SLF4J providers were found`.
- Một module dùng SLF4J nhưng framework khác ghi JUL/Log4j API.
- Muốn đổi backend mà không sửa hàng trăm lớp chứa log.
- Gặp lỗi khác nhau giữa `gradle run`, Maven tests, ứng dụng trong IDE, JAR đóng gói và Docker image.

**Lưu ý từ vựng:** trong SLF4J 1.7 trở về trước, “binding” thường là một lớp đặc biệt; trong SLF4J 2.x, thuật ngữ kỹ thuật phù hợp là **provider** được nạp bởi Java ServiceLoader. Người ta đôi khi vẫn gọi chung cả hai là “binding runtime”, nhưng phải chẩn đoán đúng phiên bản.

## 2. Phân biệt API, facade, binding, provider và backend

| Khái niệm | Chịu trách nhiệm | Ví dụ |
| --- | --- | --- |
| Logging facade/API | Định nghĩa cách gọi log độc lập với backend | `org.slf4j.Logger`, `LoggerFactory` |
| Binding kiểu cũ | Kết nối API SLF4J 1.7 với implementation | JAR chứa `org.slf4j.impl.StaticLoggerBinder` |
| Provider kiểu mới | Kết nối API SLF4J 2.x với implementation | `SLF4JServiceProvider` được ServiceLoader tìm |
| Logging backend | Xử lý logger hierarchy, level, filter, appender, encoder và đích xuất | Logback, Log4j 2, JUL, slf4j-simple |
| Bridge/adapter | Chuyển các lệnh từ API logging khác sang API/backend mục tiêu | `jul-to-slf4j`, `log4j-to-slf4j` |
| Runtime classpath | Những class và resource thực sự được JVM/runtime classloader nhìn thấy | JAR chạy trong Gradle/Maven/IDE/JAR deploy |

Một thư viện có `slf4j-api` vẫn có thể **biên dịch thành công** nhưng không in log khi chạy vì thiếu provider. Ngược lại, có backend trên classpath nhưng phiên bản không tương thích với facade cũng có thể khiến ứng dụng không kết nối được.

**Thời điểm kết nối và thời điểm cấu hình khác nhau:**

1. **Build/compile:** mã biên dịch dựa vào phương thức và kiểu của API.
2. **Khởi tạo runtime:** SLF4J tìm một binding/provider thích hợp và khởi tạo `ILoggerFactory`.
3. **Phát sự kiện:** facade chuyển lời gọi đến backend đang hoạt động.
4. **Backend quyết định đầu ra:** level, filter, appender/handler và encoder/layout quyết định event có đến đích ghi không.

Chỉ cần file cấu hình đẹp chưa đủ: nếu runtime không chọn backend mà file đó dành cho, file cấu hình có thể không có tác dụng. Ví dụ `logback.xml` không thể điều khiển `slf4j-simple` nếu SimpleLogger là backend thực sự được chọn.

## 3. Binding trong SLF4J 1.7 và provider trong SLF4J 2.x

### 3.1. SLF4J 1.7: `StaticLoggerBinder`

Ở hệ SLF4J 1.7.x và cũ hơn, binding JAR cung cấp lớp có tên:

```text
org/slf4j/impl/StaticLoggerBinder.class
```

Khi khởi tạo, `LoggerFactory` của SLF4J 1.7 dùng cơ chế này để tìm implementation. Ví dụ các artifact thuộc thế hệ 1.7 có thể kết nối tới Logback hoặc backend khác.

Các tình huống điển hình:

- **Không có binding hợp lệ:** SLF4J có thể cảnh báo không tải được `StaticLoggerBinder` rồi dùng NOP fallback.
- **Có một binding đúng thế hệ:** lời gọi được chuyển tới backend tương ứng.
- **Có nhiều binding:** xuất cảnh báo kiểu `Class path contains multiple SLF4J bindings`; một binding được chọn, nhưng không nên dựa vào thứ tự tìm thấy.
- **API/binding không tương thích:** không thể coi việc có cùng tên artifact là bằng chứng đã kết nối đúng.

Thông báo mẫu:

```text
SLF4J: Class path contains multiple SLF4J bindings.
SLF4J: Found binding in [...]
SLF4J: Actual binding is of type [...]
```

Đây chỉ là **mẫu rút gọn**. Đường dẫn thực, loại binding và prefix warning phụ thuộc phiên bản/classpath.

### 3.2. SLF4J 2.x: `SLF4JServiceProvider`

SLF4J 2.x chuyển sang Java `ServiceLoader` và SPI:

```java
org.slf4j.spi.SLF4JServiceProvider
```

Các provider triển khai SPI này và có cơ chế đăng ký tương thích với ServiceLoader, thường qua resource:

```text
META-INF/services/org.slf4j.spi.SLF4JServiceProvider
```

Khi `LoggerFactory` được khởi tạo, facade tìm provider, kiểm tra tính phù hợp và kết nối với một triển khai để tạo Logger.

Ví dụ `slf4j-api:2.0.x` và `logback-classic:1.5.x` tương thích có thể sử dụng Logback. `slf4j-simple:2.0.x` là một backend/provider khác dành cho môi trường đơn giản. Trong cùng runtime **không nên thêm cả hai** chỉ để “dự phòng”.

Một số kết quả khác nhau:

```text
API 2.x + provider 2.x tương thích:
    -> một backend được kết nối

API 2.x + không có provider:
    -> cảnh báo no providers, NOP fallback

API 2.x + hai provider:
    -> cảnh báo multiple providers, một provider được chọn

API 2.x + chỉ binding 1.7:
    -> binding cũ bị bỏ qua; không trở thành provider 2.x
```

Cảnh báo loại `multiple providers` và `no providers` là **hai vấn đề khác nhau**. Với trường hợp thứ nhất, thường cần loại provider dư; với trường hợp thứ hai, cần bổ sung provider đúng thế hệ hoặc sửa classpath.

### 3.3. Đối chiếu hai thế hệ

| Trục so sánh | SLF4J 1.7.x | SLF4J 2.x |
| --- | --- | --- |
| Cơ chế kết nối | `StaticLoggerBinder` | `ServiceLoader` và `SLF4JServiceProvider` |
| Cảnh báo nhiều implementation | Multiple bindings | Multiple providers |
| Không có implementation hợp lệ | Có thể rơi về NOP | Cảnh báo no providers và dùng NOP |
| Binding cũ `StaticLoggerBinder` | Có thể sử dụng khi tương thích | Bị bỏ qua, không phải provider hợp lệ |
| Đặc tả provider/binding | Phụ thuộc thế hệ API | Provider cần tương thích với SPI của API 2.x |

Không trộn `slf4j-api` 2.x với một binding 1.7.x rồi mong nó hoạt động như trước. Cũng không chỉ nhìn tên `logback-classic` mà bỏ qua phiên bản Logback và SLF4J API mà framework đã quản lý.

## 4. Runtime quyết định backend như thế nào?

Để dễ hiểu, giả sử mã ứng dụng được biên dịch dựa vào `slf4j-api` mà không import các lớp Logback.

```text
Biên dịch thành công:
  MyService.java
       |
       v
  slf4j-api.jar
       |
       v
  MyService.class

Khi chạy:
  MyService.class + slf4j-api.jar + đúng một provider/backend
                                             |
                                             v
                                     LoggerFactory được khởi tạo
                                             |
                                             v
                                       ILoggerFactory thực tế
                                             |
                                             v
                                         log event
```

**Binding runtime không phải phép “đổi backend vô hạn giữa lúc ứng dụng đang chạy”.** Trong mô hình SLF4J thông thường, quá trình khởi tạo `LoggerFactory` và lựa chọn provider diễn ra ở runtime initialization, sau đó các Logger dùng provider đã chọn. Thay JAR trên đĩa khi ứng dụng đang chạy không đồng nghĩa hệ thống đang chạy tự chuyển backend; việc chuyển backend thường được áp dụng khi **khởi động lại với classpath và cấu hình phù hợp**.

Ngoài ra, Java classloader thực tế có thể bị ảnh hưởng bởi app server, plugin system, fat JAR, module path hoặc launcher. Dependency xuất hiện trong build file không bảo đảm nó đã được đóng vào **runtime classpath mà process đang dùng**.

### 4.1. Compile classpath khác runtime classpath

Với Gradle:

```groovy
dependencies {
    implementation 'org.slf4j:slf4j-api:2.0.17'
    runtimeOnly 'ch.qos.logback:logback-classic:1.5.18'
}
```

Đây là **mảnh cấu hình Gradle**. `implementation` đưa API vào compile/runtime của ứng dụng, còn `runtimeOnly` đưa Logback vào runtime mà không ép Java source dùng class Logback. Cách tách này làm rõ ý định: **code phụ thuộc facade, runtime phụ thuộc implementation**.

Một thư viện Java xuất bản cho bên khác thường chỉ cần phụ thuộc API; nó không nên áp provider/backend lên mọi ứng dụng sử dụng thư viện. Tùy cấu trúc build, cần dùng `api` hoặc `implementation` của Gradle phù hợp với các kiểu public API được expose, nhưng **không tự gắn `logback-classic` vào library chỉ để log hoạt động khi chạy test**. Test có thể có backend dành riêng qua cấu hình test.

### 4.2. Chọn backend khác, giữ Java source

Muốn đổi ứng dụng từ Logback sang `slf4j-simple` trong một demo Gradle, thay dependency runtime của Logback:

```groovy
runtimeOnly 'ch.qos.logback:logback-classic:1.5.18'
```

bằng:

```groovy
runtimeOnly 'org.slf4j:slf4j-simple:2.0.17'
```

Không giữ đồng thời cả hai provider. Mã gọi `LoggerFactory` và `logger.info` vẫn có thể giữ nguyên; **định dạng, đích ghi và cách cấu hình** không giữ nguyên vì phụ thuộc backend. `logback.xml` không phải file cấu hình của `slf4j-simple`.

## 5. Những backend/provider thường gặp

| Artifact | Vai trò trong runtime | Ghi chú |
| --- | --- | --- |
| `org.slf4j:slf4j-api` | API/facade | Không phải provider |
| `ch.qos.logback:logback-classic` | Backend/provider Logback | Dành cho SLF4J phiên bản phù hợp |
| `org.slf4j:slf4j-simple` | Backend/provider đơn giản | Hợp cho demo/CLI nhỏ |
| `org.slf4j:slf4j-nop` | Provider bỏ qua log | NOP là lựa chọn cố ý, có thể làm “mất log” nếu chọn nhầm |
| `org.slf4j:slf4j-jdk14` | Chuyển lời gọi SLF4J sang JUL | Không nhầm chiều với `jul-to-slf4j` |
| `org.slf4j:slf4j-reload4j` | Chuyển lời gọi SLF4J sang reload4j | Cần quản lý phiên bản phù hợp |
| `org.apache.logging.log4j:log4j-slf4j2-impl` | Provider SLF4J 2.x hướng tới Log4j 2 | Không cài kèm bridge ngược chiều `log4j-to-slf4j` |
| `org.apache.logging.log4j:log4j-slf4j-impl` | Binding SLF4J 1.7 hướng tới Log4j 2 | Không thay thế trực tiếp provider 2.x |
| `org.slf4j:jul-to-slf4j` | Bridge JUL → SLF4J | Không phải provider |
| `org.apache.logging.log4j:log4j-to-slf4j` | Bridge Log4j API → SLF4J | Không phải provider |

**Chỉ nên có một provider được chọn trong runtime** của ứng dụng. Nhiều JAR có thể dùng SLF4J API đồng thời; điều đó hoàn toàn bình thường. Vấn đề không phải “nhiều thư viện ghi log”, mà là **nhiều backend cạnh tranh làm điểm đích cho một API**.

## 6. Ví dụ Java 17 đầy đủ: compile với facade, bind Logback lúc chạy

Bài thực hành sau dùng Java 17, Gradle và SLF4J 2.x. Java source **chỉ import `org.slf4j.*`**, không import class Logback. Khi chạy, dependency `logback-classic` trong runtime sẽ trở thành provider, còn file `logback.xml` định nghĩa cách xuất message.

Ta cấu hình pattern đơn giản, không có timestamp để **stdout có thể đối chiếu chính xác**. Trong ứng dụng thật, nên có timestamp, service/instance, `traceId` và các trường ngữ cảnh cần thiết.

Cấu trúc thư mục:

```text
runtime-binding-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        demo/
          BindingRuntimeDemo.java
      resources/
        logback.xml
```

### 6.1. File `settings.gradle`

```groovy
rootProject.name = 'runtime-binding-demo'
```

### 6.2. File `build.gradle`

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.slf4j:slf4j-api:2.0.17'
    runtimeOnly 'ch.qos.logback:logback-classic:1.5.18'
}

application {
    mainClass = 'demo.BindingRuntimeDemo'
}
```

**Giải thích dependency:** `slf4j-api` là thứ mã Java cần để compile. `logback-classic` cung cấp implementation ở runtime và kéo theo các dependency cần thiết của nó. Những số phiên bản trên là **mốc cố định để bài thực hành có thể lặp lại**, không phải khẳng định đó là phiên bản mới nhất. Ở dự án thật, sử dụng dependency management/BOM tương thích, cập nhật phiên bản đã được kiểm tra bảo mật và tránh thêm provider thứ hai.

### 6.3. File `src/main/resources/logback.xml`

```xml
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>%level %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

Cấu hình này dành cho **Logback**. `ConsoleAppender` dùng stdout; `%level %msg%n` in level, message đã thay tham số, rồi newline. Root level `INFO` làm `DEBUG` không xuất. Khi chuyển sang provider khác, cần định dạng và file cấu hình tương ứng của provider đó.

### 6.4. File `src/main/java/demo/BindingRuntimeDemo.java`

```java
package demo;

import org.slf4j.ILoggerFactory;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class BindingRuntimeDemo {
    public static void main(String[] args) {
        ILoggerFactory factory = LoggerFactory.getILoggerFactory();
        System.out.println("factory=" + factory.getClass().getName());

        Logger log = LoggerFactory.getLogger(BindingRuntimeDemo.class);
        log.info("event=invoice.created invoiceId={}", "inv-9");
        log.debug("event=diagnostic.hidden");
        log.warn("event=payment.retry attempt={}", 2);
    }
}
```

Ở đây `getILoggerFactory()` cho biết **factory được provider thực sự chọn**. Khi dùng Logback Classic, tên class thông thường là `ch.qos.logback.classic.LoggerContext`. Đoạn code không import một class nào thuộc Logback. Nếu thay provider mà vẫn tương thích SLF4J API, mã Java vẫn gọi các phương thức như cũ.

### 6.5. Biên dịch và chạy

Từ thư mục `runtime-binding-demo`, với JDK 17 và một bản Gradle hỗ trợ Java 17, chạy:

```bash
gradle run --quiet
```

Nếu dự án đã có Gradle Wrapper, có thể dùng `./gradlew run --quiet` trên Linux/macOS hoặc `gradlew.bat run --quiet` trên Windows. Ví dụ không tạo kèm Wrapper; cần có Gradle và quyền truy cập repository dependency khi build lần đầu.

**stdout của chương trình khi runtime có duy nhất provider Logback và dùng chính xác `logback.xml` trên:**

```text
factory=ch.qos.logback.classic.LoggerContext
INFO event=invoice.created invoiceId=inv-9
WARN event=payment.retry attempt=2
```

**Vì sao chỉ có ba dòng?** Dòng đầu in class của factory. Dòng `INFO` và `WARN` được root Logger chấp nhận; placeholder `{}` được API/backend format thành giá trị truyền vào. Dòng `DEBUG` không xuất vì root ở `INFO`. Không có timestamp, thread name hay log level từ Gradle trong pattern trên, nên phần **stdout do chương trình phát ra** có thể kiểm tra dễ dàng; thông báo build/download của Gradle hoặc cảnh báo nền tảng nếu có là phần ngoài chương trình.

### 6.6. Thử đổi backend mà giữ Java source

**Trong chính dự án demo**, thay Logback ở `runtimeOnly` bằng:

```groovy
runtimeOnly 'org.slf4j:slf4j-simple:2.0.17'
```

Sau đó chạy lại cùng chương trình. Kết quả factory dự kiến của SimpleLogger:

```text
factory=org.slf4j.simple.SimpleLoggerFactory
```

Đây là **dòng stdout từ `System.out.println`**, không phải toàn bộ output của lần chạy; `slf4j-simple` thường ghi log ra **stderr** theo cấu hình mặc định và có pattern riêng. Không coi `logback.xml` là cấu hình của SimpleLogger. Quan sát sự thay đổi backend mà **không sửa `BindingRuntimeDemo.java`** mới là mục tiêu của bài thực hành.

Nếu runtime chỉ có `slf4j-api` 2.x mà không có provider, SLF4J có thể cảnh báo `No SLF4J providers were found` và dùng NOP fallback. Khi đó `INFO`/`WARN` do SLF4J phát ra không đến backend xuất log, dù mã nghiệp vụ vẫn thực hiện lời gọi.

## 7. Runtime classpath: nơi lỗi thực sự xuất hiện

### 7.1. Gradle

Trong module chạy ứng dụng, kiểm tra dependencies của classpath runtime:

```bash
gradle dependencies --configuration runtimeClasspath
```

Nếu ứng dụng nhiều module, phải chọn task và module khởi động phù hợp. Ví dụ một dự án có module `app` (chỉ là tên minh họa):

```bash
gradle :app:dependencies --configuration runtimeClasspath
```

Để tìm dependency nào kéo vào một provider không mong muốn:

```bash
gradle dependencyInsight --configuration runtimeClasspath --dependency slf4j-simple
gradle dependencyInsight --configuration runtimeClasspath --dependency logback-classic
```

Lưu ý `testRuntimeClasspath` khác `runtimeClasspath`; test có thể dùng provider riêng hoặc bị kéo thêm một backend từ dependency test.

```bash
gradle dependencies --configuration testRuntimeClasspath
```

Với Gradle Wrapper có sẵn, thay `gradle` bằng `./gradlew` trên Unix hoặc `gradlew.bat` trên Windows.

### 7.2. Maven

Một ứng dụng Maven có thể phụ thuộc vào API khi compile và thêm backend ở scope runtime. Ví dụ **đoạn trong `pom.xml`**, chưa phải POM độc lập:

```xml
<dependencies>
    <dependency>
        <groupId>org.slf4j</groupId>
        <artifactId>slf4j-api</artifactId>
        <version>2.0.17</version>
    </dependency>
    <dependency>
        <groupId>ch.qos.logback</groupId>
        <artifactId>logback-classic</artifactId>
        <version>1.5.18</version>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Để xác định provider nào đến từ dependency trực tiếp hay bắc cầu:

```bash
mvn dependency:tree
```

Nếu một thư viện transitively kéo `slf4j-simple`, `slf4j-nop` hay backend khác, cần sửa dependency hoặc dùng exclusion tại **đường phụ thuộc đúng**. Không sửa bằng cách xóa các file JAR trong Maven/Gradle cache: build lại có thể tải chúng xuống và xung đột tái xuất hiện.

### 7.3. Bản chạy đóng gói mới là bằng chứng cuối

Có thể build sạch ở IDE nhưng một executable JAR, container image, application server hoặc launcher của framework lại có classpath khác. Khi điều tra, xác nhận cả:

- Dependency graph của **module khởi động**.
- Runtime/test classpath nơi cảnh báo xuất hiện.
- Dependency đóng trong fat JAR hoặc bản phân phối cuối.
- Các JAR do server/container/runtime bổ sung.
- Những tài nguyên khai báo service provider có được giữ khi shading/đóng gói.

Với SLF4J 2.x, một bản fat JAR tự đóng gói sai có thể làm mất hoặc ghi đè `META-INF/services` và khiến `ServiceLoader` không tìm được provider. Dự án dùng công cụ shading cần bảo toàn/ghép các service descriptor đúng cách. Đây là một dạng **lỗi đóng gói runtime** dù build vẫn thành công.

## 8. Chẩn đoán backend đã được chọn

Khi mã đang chạy có SLF4J trên classpath, có thể in:

```java
System.out.println(
        org.slf4j.LoggerFactory.getILoggerFactory()
                .getClass().getName()
);
```

Đây là **mảnh mã**, không phải chương trình chạy độc lập. Những class name thường gặp:

| Factory được phát hiện | Cách diễn giải |
| --- | --- |
| `ch.qos.logback.classic.LoggerContext` | Đang sử dụng Logback Classic |
| `org.slf4j.simple.SimpleLoggerFactory` | Đang sử dụng SimpleLogger |
| `org.slf4j.helpers.NOPLoggerFactory` | Không phát log qua backend thông thường |
| Factory của backend Log4j 2 | SLF4J đang nối sang provider của Log4j 2 |

Tên factory là chứng cứ về **implementation mà SLF4J đang sử dụng**, không có nghĩa mọi event đã xuất tới file/console. Nếu log không xuất hiện dù đúng factory, tiếp tục kiểm tra logger level, filter, appender, encoder và nơi thu thập log.

### 8.1. Quy trình điều tra theo thứ tự

1. Xác định **phiên bản `slf4j-api` thực tế** trong runtime.
2. Nếu là 1.7, tìm binding `StaticLoggerBinder`; nếu là 2.x, tìm provider `SLF4JServiceProvider`.
3. Xem thông báo khởi tạo SLF4J, phân biệt **không có**, **có nhiều** và **không tương thích**.
4. Kiểm tra dependency graph, bỏ provider không mong muốn và xác nhận phiên bản tương thích.
5. Xem `ILoggerFactory` thực tế rồi kiểm tra cấu hình của đúng backend đó.
6. Ghi thử một event `INFO`, `WARN` và một exception theo cấu hình mong muốn.
7. Xác nhận stdout, stderr, file hoặc collector nhận event; kiểm tra cả artifact deploy/test nếu khác local.

### 8.2. Những thông báo hay gặp

```text
SLF4J: Class path contains multiple SLF4J bindings.
```

Mẫu này gắn với hệ 1.7 và nhiều binding. Trong 2.x, lỗi tương đương thường có cụm `multiple SLF4J providers`. Nếu thấy:

```text
SLF4J(W): No SLF4J providers were found.
```

thì cần kiểm tra **thiếu provider 2.x**, không phải “quá nhiều”. Các thông báo trên là **dòng tiêu biểu**, không phải toàn bộ stdout/stderr của một lần chạy; prefix có thể khác tùy phiên bản.

Khi provider thiếu, đừng thêm đồng thời `slf4j-simple` và `logback-classic` để “chắc ăn”; điều đó dễ tạo multiple providers. Chọn một backend đúng nhu cầu.

## 9. Binding khác bridge: tránh vòng chuyển tiếp log

Một **binding/provider** trả lời câu hỏi “lời gọi SLF4J sẽ đi tới backend nào?”. Một **bridge** chuyển lời gọi **từ một logging API khác** vào SLF4J hoặc ngược lại. Những artifact có tên gần giống nhau nhưng chiều chuyển đổi trái ngược rất dễ gây lỗi.

### 9.1. JUL và SLF4J

```text
JUL API --jul-to-slf4j--> SLF4J API --Logback provider--> Logback
```

`jul-to-slf4j` giúp định tuyến log từ JUL sang SLF4J khi được cài bridge/handler đúng cách, nhưng **không phải SLF4J provider**. Ngược lại:

```text
SLF4J API --slf4j-jdk14--> java.util.logging (JUL)
```

Đây là provider đưa lời gọi SLF4J sang JUL. Nếu cấu hình **hai chiều đồng thời** và cài bridge tương ứng, có thể xảy ra vòng chuyển tiếp `SLF4J → JUL → SLF4J → ...`. Không thêm bridge chỉ vì thấy tên chứa “slf4j”; phải xác định mũi tên nguồn → đích.

### 9.2. Log4j 2 và SLF4J

```text
SLF4J API --log4j-slf4j2-impl--> Log4j 2 backend
```

Khác với:

```text
Log4j API --log4j-to-slf4j--> SLF4J API
```

**Không cài `log4j-slf4j2-impl` đồng thời với `log4j-to-slf4j` trong cùng đường xử lý**, vì hai chiều có thể gây vòng định tuyến hoặc xung đột mà backend không thể xử lý đúng. Tương tự, `log4j-slf4j-impl` dành cho thế hệ API SLF4J 1.7, không phải lựa chọn tương đương hoàn toàn cho hệ 2.x.

Việc một bridge không phải provider không có nghĩa nó vô hại: thay bridge có thể khiến log từ thư viện dùng JUL/Log4j API đi đường khác hoặc không còn được thu thập.

## 10. Framework, ứng dụng nhiều module và môi trường triển khai

### 10.1. Spring Boot và framework đã quản lý backend

Nhiều ứng dụng Spring Boot sử dụng starter logging mặc định dựa trên Logback. Khi đó:

- Không cần tự thêm một provider thứ hai chỉ để gọi `LoggerFactory.getLogger()`.
- Việc đặt `logback.xml` hoặc `logback-spring.xml` có hiệu lực tùy cơ chế cấu hình và phiên bản Spring Boot.
- Nếu chuyển sang Log4j 2, cần điều chỉnh đúng **starter/dependency/provider** và loại backend cũ; không chỉ thêm JAR Log4j 2 cạnh Logback.
- Dependency bắc cầu từ thư viện có thể mang provider dư, tạo cảnh báo chỉ xuất hiện ở runtime.

Xác định backend thực tế trước khi chỉnh config. Một file `logback.xml` hoàn toàn hợp lệ vẫn không điều khiển ứng dụng khi SLF4J thực sự nối vào SimpleLogger hoặc Log4j 2.

### 10.2. Library và application có trách nhiệm khác nhau

**Library:** chỉ nên log qua API mà ứng dụng tiêu thụ có thể điều khiển, ví dụ SLF4J, và thường không ép một provider trong dependency runtime của người dùng thư viện.

**Application:** chọn một provider phù hợp, cấu hình mức log, encoder/formatter, appender và chính sách quản trị. Đây là nơi hợp lý để đưa `runtimeOnly` backend và kiểm tra dependency tree.

**Test:** có thể cần backend phục vụ test output, nhưng `testRuntimeClasspath` có thể khác môi trường chạy thật. Test pass không chứng minh production runtime đã bind đúng.

### 10.3. Classloader và hệ module

Với plugin systems hoặc application servers, nhiều classloader có thể nhìn thấy những dependency khác nhau. Một module chạy độc lập có thể nối vào provider khác so với chương trình cha nếu cách nạp class khác nhau. Với Java Module System, tính hiển thị module và việc đăng ký `provides`/`uses` hoặc service descriptor cũng ảnh hưởng ServiceLoader. Vì vậy cần điều tra đúng classloader/runtime mà ứng dụng đang dùng, không suy ra chỉ từ file build ở thư mục nguồn.

## 11. Lỗi phổ biến và cách sửa

| Triệu chứng | Nguyên nhân khả dĩ | Hành động phù hợp |
| --- | --- | --- |
| Build được nhưng log không xuất | Chỉ có API, không có provider; NOP được chọn; hoặc level/filter chặn | Kiểm tra warning, factory và runtime provider trước khi sửa level |
| Có `logback.xml` nhưng format khác | Provider thực tế không phải Logback | In factory class, kiểm tra dependency bắc cầu |
| SLF4J 1.7 báo multiple bindings | Hai JAR đều có `StaticLoggerBinder` | Loại binding dư ở đúng nhánh dependency |
| SLF4J 2.x báo multiple providers | Hai provider qua ServiceLoader | Chỉ giữ một provider phù hợp |
| API 2.x có JAR binding 1.7 nhưng vẫn NOP | Binding cũ bị bỏ qua | Dùng provider 2.x tương thích |
| `getILoggerFactory()` trả NOP | Không có implementation phù hợp hoặc chủ động dùng `slf4j-nop` | Bổ sung/chọn provider đúng nhu cầu |
| CLI chạy đúng, fat JAR mất log | Provider bị bỏ/descriptor mất khi đóng gói | Kiểm tra artifact, ServiceLoader descriptor và launcher |
| Test có log nhưng app deploy không | Classpath hoặc cấu hình môi trường khác | So sánh runtime/test/deployed artifact |
| Ghi log bị lặp | Appender ở nhiều tầng, additivity, nhiều đường routing | Kiểm tra backend config và bridge, không đổ hết cho multiple providers |
| Log4j/JUL xảy ra lỗi định tuyến | Bridge đi ngược chiều provider đang chọn | Vẽ lại chiều chuyển log, bỏ vòng hai chiều |
| Muốn đổi provider mà không restart | LoggerFactory đã khởi tạo | Đổi runtime dependencies/config và chạy lại theo quy trình deploy |
| Một số message ở stderr thay vì stdout | Backend mặc định dùng stderr, hoặc cảnh báo nội bộ SLF4J | Kiểm tra đích output của provider; đừng nhầm stderr với log mất |

### Tránh cách sửa chỉ che triệu chứng

- Không thêm `slf4j-nop` để hết warning nếu bạn vẫn muốn ghi log.
- Không loại `slf4j-api` chỉ vì nhìn thấy tên SLF4J trong dependency tree; phần API vẫn cần thiết.
- Không dựa vào thứ tự JAR để cố chọn provider khi có nhiều implementation.
- Không giả định warning là log event đi qua appender của ứng dụng. Warning khi khởi tạo SLF4J có thể được báo trực tiếp trên stderr.
- Không trộn các thế hệ API/binding mà không đọc tài liệu tương thích.
- Không sửa dependency cache thủ công; thay build config rồi kiểm tra lại artifact runtime.

## 12. Bài tập áp dụng

**Bài tập A — nhận diện backend:** Giữ nguyên `BindingRuntimeDemo.java`, chạy với Logback như mục 6, ghi lại tên factory và output. Thay chỉ provider runtime bằng SimpleLogger rồi chạy lại. Giải thích vì sao Java source không thay đổi nhưng factory/định dạng log có thể khác.

**Bài tập B — tái tạo thiếu provider:** Bỏ dòng `runtimeOnly` ra khỏi demo trong môi trường thực hành. Dự đoán warning thiếu provider của SLF4J 2.x và NOP fallback. Kiểm tra bằng việc in factory. Sau đó khôi phục đúng một provider tương thích. Đây là thí nghiệm; không cố ý deploy production trong trạng thái thiếu backend.

**Bài tập C — nhiều provider:** Trong bản demo cục bộ, thêm đồng thời `slf4j-simple` và `logback-classic` ở runtime. Dự đoán cảnh báo multiple providers. **Không dự đoán backend nào được chọn**; quan sát factory và giải thích vì sao cần loại provider dư. Sau thử nghiệm, trả lại cấu hình chỉ một backend.

**Bài tập D — bridge hai chiều:** Vẽ sơ đồ mũi tên cho `jul-to-slf4j`, `slf4j-jdk14`, `log4j-to-slf4j` và `log4j-slf4j2-impl`. Chỉ ra cặp nào tạo nguy cơ routing loop khi dùng cùng nhau; chưa cần thử chạy một cấu hình vòng lặp nguy hiểm.

## 13. Checklist kiến trúc runtime binding

- [ ] Source code phụ thuộc facade/API đã chọn, không import backend ở khắp business logic.
- [ ] Đã xác định phiên bản SLF4J API tại **runtime**.
- [ ] Với SLF4J 1.7, dùng binding `StaticLoggerBinder` tương thích; với SLF4J 2.x, dùng provider `SLF4JServiceProvider`.
- [ ] Chỉ tồn tại **một** binding/provider chủ đích trong runtime của ứng dụng.
- [ ] `ILoggerFactory` được chọn đúng backend và config file dành cho backend đó.
- [ ] Logger level, filter, appender/handler, formatter/encoder cho ra output mong muốn.
- [ ] Không tồn tại bridge ngược chiều gây vòng chuyển tiếp.
- [ ] Đã kiểm tra runtimeClasspath, testRuntimeClasspath và artifact deploy khi các môi trường khác nhau.
- [ ] Service descriptors được giữ đúng khi đóng gói/shading nếu dùng SLF4J 2.x.
- [ ] Thư viện dùng chung không ép provider cho ứng dụng tiêu thụ.
- [ ] Đã kiểm tra warning khi khởi tạo, output INFO/WARN/ERROR và nơi nhận log.
- [ ] Kế hoạch thay backend có bước đổi dependency, cập nhật config và restart, không trông chờ hot swap tùy ý.

### Tài liệu tham khảo

- [SLF4J Manual](https://www.slf4j.org/manual.html): API facade và provider runtime.
- [SLF4J FAQ](https://www.slf4j.org/faq.html): khác biệt giữa SLF4J 1.7 và 2.x.
- [SLF4J Error Codes](https://www.slf4j.org/codes.html): no providers, multiple providers, ignored bindings và cảnh báo tương ứng.
- [Logback Manual](https://logback.qos.ch/manual/index.html): backend Logback, Appender, level và cấu hình.
- [Apache Log4j components](https://logging.apache.org/log4j/2.x/components.html): API, provider và bridge trong hệ Log4j 2.

**Kết luận:** **Binding runtime** chính là chặng nối facade tới backend khi ứng dụng khởi tạo. Trong SLF4J 1.7, chặng này dựa trên `StaticLoggerBinder`; trong SLF4J 2.x, nó dựa vào `SLF4JServiceProvider` và ServiceLoader. Thiết kế mã phụ thuộc API, runtime chỉ có một provider phù hợp, kiểm tra factory thực tế và tránh bridge hai chiều sẽ giúp đổi backend có kiểm soát, không mất log và không khóa logic nghiệp vụ vào một triển khai cụ thể.
