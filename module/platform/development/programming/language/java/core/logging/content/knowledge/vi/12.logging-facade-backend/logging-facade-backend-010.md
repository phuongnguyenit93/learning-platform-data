# Kiểm tra dependency logging trong Java: Facade, backend, provider và bridge

## 1. Vì sao phải kiểm tra dependency logging?

Ứng dụng Java có thể biên dịch thành công, nhưng khi chạy lại **không có log**, ghi sai định dạng, có nhiều cảnh báo về logger provider, hoặc sinh log hai lần. Một nguyên nhân phổ biến là **classpath chứa các thư viện logging không tương thích hoặc có tuyến chuyển tiếp sai**.

Ví dụ, mã nghiệp vụ viết:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

private static final Logger LOG =
        LoggerFactory.getLogger(PaymentService.class);
```

Đoạn trên là **minh họa bên trong lớp `PaymentService`**, không phải chương trình độc lập. Nó dùng **SLF4J API**; chỉ nhìn import chưa thể kết luận runtime đang ghi bằng Logback hay Log4j 2. Ứng dụng còn cần một **provider/backend** được nạp đúng và có cấu hình phù hợp.

Khi kiểm tra dependency logging, mục tiêu không chỉ là thấy có thư viện logger trong `pom.xml` hoặc `build.gradle`. Cần xác minh **toàn bộ đường đi**:

```text
Mã ứng dụng hoặc thư viện
          |
          v
API / Facade logging
  (SLF4J, Log4j 2 API, JUL, Commons Logging...)
          |
          v
Provider / bridge / adapter
          |
          v
Backend thực sự xử lý sự kiện
  (Logback, Log4j 2 Core, JUL, ...)
          |
          v
Level / filter / appender / formatter
          |
          v
Console, file, collector
```

Một bản build có dependency đúng *ở compile time* nhưng thiếu provider *ở runtime* vẫn có thể không xuất log. Ngược lại, một ứng dụng có nhiều provider có thể chọn backend khác dự kiến và làm cấu hình bị bỏ qua.

**Kết quả cần đạt:** biết chính xác API nào được dùng, provider nào hoạt động, backend nào xử lý log, có bridge nào nối các API khác không, có đường chuyển tiếp vòng hay không và cấu hình runtime có thực sự được nạp.

## 2. Từ vựng phải phân biệt trước khi kiểm tra

| Thuật ngữ | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| **Logging API** | Tập interface/phương thức để mã gọi log | `org.slf4j.Logger`, `org.apache.logging.log4j.Logger`, `java.util.logging.Logger` |
| **Facade** | Lớp API trung gian, tách mã gọi log khỏi backend cụ thể | SLF4J |
| **Provider/binding** | Thành phần nối một API facade với hệ thống xử lý thật | SLF4J 2 provider của Logback; `log4j-slf4j2-impl` |
| **Backend/implementation** | Quyết định xử lý sự kiện, filter, appender và nơi ghi | Logback Classic, Log4j 2 Core, JUL |
| **Bridge/adapter** | Chuyển cuộc gọi của API A sang API B | `jcl-over-slf4j`, `jul-to-slf4j`, `log4j-to-slf4j` |
| **Appender/handler** | Gửi sự kiện tới console, file, mạng... | `ConsoleAppender`, `FileAppender`, `ConsoleHandler` |
| **Formatter/layout/encoder** | Biến dữ liệu sự kiện thành text/JSON/byte | `PatternLayout`, `PatternLayoutEncoder` |
| **Logging configuration** | Khai báo mức log, formatter và đích | `logback.xml`, `log4j2.xml`, `logging.properties` |

Ví dụ cấu trúc **SLF4J → Logback**:

```text
Ứng dụng
  import org.slf4j.Logger
        |
        v
slf4j-api (facade)
        |
        v
Logback provider (trong logback-classic)
        |
        v
logback-classic + logback-core
        |
        v
logback.xml -> ConsoleAppender/FileAppender
```

Ví dụ cấu trúc **SLF4J → Log4j 2**:

```text
Ứng dụng
  import org.slf4j.Logger
        |
        v
slf4j-api
        |
        v
log4j-slf4j2-impl
        |
        v
log4j-api + log4j-core
        |
        v
log4j2.xml -> Appenders
```

Và một ứng dụng **dùng trực tiếp API Log4j 2**:

```text
Ứng dụng -> log4j-api -> log4j-core -> log4j2.xml
```

Trường hợp cuối không bắt buộc có SLF4J. Việc thêm `log4j-slf4j2-impl` chỉ cần khi có mã/ thư viện gọi SLF4J và ta muốn các cuộc gọi ấy dùng Log4j 2.

## 3. Dependency trực tiếp và dependency bắc cầu

Một dependency **trực tiếp** là thư viện bạn khai báo trong dự án. Dependency **bắc cầu (transitive)** được thư viện khác đưa vào theo quan hệ phụ thuộc.

Ví dụ một `pom.xml` khai báo:

```xml
<dependency>
    <groupId>ch.qos.logback</groupId>
    <artifactId>logback-classic</artifactId>
    <version>1.5.16</version>
</dependency>
```

Khi Maven giải dependency, `logback-classic` thường kéo thêm các thành phần cần thiết, như `logback-core` và một phiên bản `slf4j-api` tương thích. Một thư viện khác của ứng dụng có thể đồng thời mang tới `slf4j-api`, `log4j-to-slf4j`, `log4j-core` hoặc một provider khác. **Không chỉ đọc các dòng `<dependency>` do mình viết rồi cho rằng đã biết toàn bộ runtime.**

Phân biệt ba không gian:

1. **Compile classpath:** cần các API/class để `javac` biên dịch.
2. **Runtime classpath:** các JAR thực sự hiện diện khi JVM khởi động và nạp provider.
3. **Test classpath:** thường có thêm logger/provider hoặc file cấu hình test; có thể khác production.

Một bài test chạy đúng nhưng bản `jar` hoặc container không log có thể do runtime không chứa cùng dependency, provider bị loại khi đóng gói, hoặc cấu hình/test resource khác.

### “Có API” không đồng nghĩa với “có backend”

`slf4j-api` chỉ cung cấp API và cơ chế kết nối provider, không phải backend ghi log. Với SLF4J 2.x, khi không tìm được provider phù hợp, SLF4J thường cảnh báo và dùng NOP/no-operation logger: lời gọi logging có thể bị bỏ qua. Ứng dụng vẫn có thể tiếp tục chạy, nên đây là lỗi khó nhận ra nếu chỉ kiểm thử chức năng nghiệp vụ.

Mặt khác, hai provider SLF4J được phát hiện cùng lúc không có nghĩa log được ghi qua cả hai. Runtime thường chọn một provider và cảnh báo có nhiều provider, nhưng **không nên phụ thuộc vào thứ tự lựa chọn**. Mục tiêu vận hành là một tuyến backend chủ đích, được kiểm chứng.

## 4. Phiên bản SLF4J: cơ chế binding 1.7 khác provider 2.x

Đây là lỗi tương thích rất thường gặp khi nâng cấp framework:

| Phiên bản API | Cơ chế triển khai | Dấu hiệu / lưu ý |
| --- | --- | --- |
| SLF4J 1.7.x | **Binding** kiểu `StaticLoggerBinder` | Thường tìm class `org.slf4j.impl.StaticLoggerBinder`. |
| SLF4J 2.x | **Service provider** dựa vào `SLF4JServiceProvider` | Thường tìm provider qua cơ chế Java ServiceLoader. |
| Logback 1.2.x | Thường ghép với SLF4J 1.7.x | Không mặc nhiên là provider của SLF4J 2.x. |
| Logback 1.3/1.4/1.5 theo nhánh tương thích | Dùng cơ chế SLF4J 2.x | Cần chọn bản phù hợp với Java và framework của dự án. |
| `log4j-slf4j-impl` | Dành cho SLF4J 1.7 | Không thay thế cho `log4j-slf4j2-impl` khi chạy SLF4J 2.x. |
| `log4j-slf4j2-impl` | Provider/adapter SLF4J 2.x sang Log4j 2 | Dùng cùng bản Log4j 2 phù hợp. |

Không phải chỉ cần “có tên logback” là đúng. Ví dụ, dự án nâng `slf4j-api` lên 2.x nhưng vẫn giữ một binding dành cho API 1.7 có thể khiến binding ấy **bị bỏ qua**. Thường xuất hiện cảnh báo “không có SLF4J provider phù hợp” hoặc “binding nhắm tới API 1.7 bị bỏ qua”.

Ngược lại, việc dùng provider của SLF4J 2.x trong ứng dụng còn `slf4j-api` 1.7 cũng không thể mặc nhiên hoạt động.

**Quy tắc:** kiểm tra cả **API version + cơ chế provider/binding + backend version + yêu cầu JDK**. Một bảng phiên bản chỉ có ý nghĩa khi kiểm tra nguồn dependency thực tế, không dùng tên JAR để suy luận.

Đối với ví dụ Java 17 ở phần sau, ta dùng **Logback Classic 1.5.16** làm provider/backend SLF4J 2.x. Đây là **một bộ phiên bản ví dụ cố định**, không có nghĩa là bản mới nhất hay bản phải dùng cho production. Khi triển khai thật, cần kiểm tra khuyến cáo bảo mật và tương thích framework/JDK hiện hành.

## 5. Maven: các lệnh kiểm tra dependency logging

### 5.1. Xem cây phụ thuộc toàn bộ

Từ thư mục có `pom.xml`:

```bash
mvn dependency:tree
```

Đọc đường đi **từ project đến từng dependency logging**, không chỉ một danh sách tên:

```text
my-service
+- framework-starter
|  +- logging-module
|     +- logback-classic
|     \- slf4j-api
\- some-library
   \- log4j-api
```

Cây trên là **minh họa cấu trúc**, không phải kết quả thật của một dự án cụ thể.

Hãy chú ý:

- Có bao nhiêu backend/provider (Logback, Log4j 2 Core/provider SLF4J, JUL provider...)?
- Có phiên bản `slf4j-api` nào được chọn sau khi giải xung đột?
- Thư viện nào đưa vào dependency bắc cầu không mong muốn?
- Có bridge hướng A → B và đồng thời bridge hướng B → A không?
- Dependency runtime có được giữ khi đóng gói ứng dụng không?

### 5.2. Lọc những thư viện đáng chú ý

Ví dụ:

```bash
mvn dependency:tree -Dincludes=org.slf4j:slf4j-api
mvn dependency:tree -Dincludes=ch.qos.logback:logback-classic
mvn dependency:tree -Dincludes=org.apache.logging.log4j:log4j-core
```

`-Dincludes` giới hạn phần cây được hiển thị, hữu ích khi dự án có hàng trăm dependency. Với Maven hoặc shell cụ thể, có thể cần đặt chuỗi filter trong dấu nháy kép.

Để tra backend và adapter ở cấp rộng hơn, có thể xem cả group:

```bash
mvn dependency:tree -Dincludes=org.slf4j
mvn dependency:tree -Dincludes=ch.qos.logback
mvn dependency:tree -Dincludes=org.apache.logging.log4j
```

Lưu ý: lọc theo group **không thay thế** xem cây toàn bộ, vì một bridge có thể nằm dưới group khác (`commons-logging`, `log4j` cũ, `org.slf4j`...). Không phải mọi phụ thuộc trực tiếp Log4j 2 đều là backend: `log4j-api` tự nó là API; `log4j-core` mới là một implementation chính.

### 5.3. Đọc phiên bản hiệu lực và phạm vi

Maven có quy tắc dependency mediation; một phiên bản khác có thể được chọn so với phiên bản xuất hiện trong nhánh sâu của cây. Kiểm tra output về các dependency bị bỏ qua do conflict khi cần bằng chế độ chi tiết được Maven Dependency Plugin đang dùng hỗ trợ, chẳng hạn:

```bash
mvn dependency:tree -Dverbose
```

Kết quả `-Dverbose` phụ thuộc phiên bản plugin; nếu không có thông tin cần thiết, kiểm tra `mvn help:effective-pom`, cấu hình `dependencyManagement` và báo cáo của plugin phù hợp.

Các scope quan trọng:

| Maven scope | Ý nghĩa thường gặp đối với logging |
| --- | --- |
| `compile` | Có trên compile và runtime classpath trong mô hình Maven thông dụng. |
| `runtime` | Không cần để biên dịch mã gọi API, nhưng cần khi chạy. |
| `test` | Chỉ phục vụ test; không nên kỳ vọng xuất hiện trong package production. |
| `provided` | Biên dịch được nhưng runtime được trông chờ cung cấp bởi môi trường bên ngoài; dễ thiếu khi triển khai độc lập. |

Ví dụ, mã có `slf4j-api` ở compile nhưng provider chỉ nằm ở test sẽ chạy unit test có log, còn bản production có thể không có provider.

### 5.4. Xem runtime classpath của Maven

Khi nghi JAR bị mất ở runtime hoặc khi công cụ chạy khác nhau:

```bash
mvn dependency:build-classpath -Dmdep.outputFile=runtime-classpath.txt -DincludeScope=runtime
```

Mục tiêu của lệnh là xuất classpath của dependency Maven để kiểm tra. Đây **không phải** một bản sao chính xác của classpath bên trong mọi fat JAR, module path hoặc container; launcher có thể thay đổi tập JAR. Không lấy kết quả build-classpath làm bằng chứng cuối cùng nếu thực tế chạy bằng một launcher khác.

## 6. Gradle: kiểm tra cấu hình đúng, tránh chỉ xem compileClasspath

Gradle dùng các **configuration** như `compileClasspath`, `runtimeClasspath`, `testRuntimeClasspath`. Khi backend không có lúc chạy, hãy nhìn đúng `runtimeClasspath`.

Trên Linux/macOS:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency slf4j-api --configuration runtimeClasspath
./gradlew dependencyInsight --dependency logback-classic --configuration runtimeClasspath
```

Trên Windows:

```powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency slf4j-api --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency logback-classic --configuration runtimeClasspath
```

`dependencies` cho thấy cấu trúc các module và phiên bản đã giải; `dependencyInsight` giúp tìm **vì sao một phiên bản được chọn**, đường phụ thuộc và quy tắc giải xung đột. Hãy chạy với configuration phù hợp cho ứng dụng hoặc cho test.

Nếu dự án nhiều module, chọn đúng module:

```bash
./gradlew :payment-service:dependencies --configuration runtimeClasspath
```

Đừng suy luận rằng mọi module dùng cùng runtime classpath chỉ vì chung root build. Một module thư viện có thể chỉ cần API logging, còn module ứng dụng chạy thực tế có provider.

### Chọn một backend tại module ứng dụng

Một cách khai báo Gradle minh họa khi dùng SLF4J + Logback:

```groovy
dependencies {
    implementation 'org.slf4j:slf4j-api:2.0.16'
    runtimeOnly 'ch.qos.logback:logback-classic:1.5.16'
}
```

Đây là **đoạn của `build.gradle`**, chưa phải dự án Gradle hoàn chỉnh. Nó mô tả việc mã biên dịch dựa trên API và runtime dùng Logback, nhưng phiên bản hiệu lực còn phụ thuộc resolution rules, platform/BOM và dependency khác. Cần kiểm tra `runtimeClasspath` sau khi giải dependency. Trong dự án thật, nên để framework/BOM phù hợp quản lý phiên bản thống nhất khi có thể, không ghim thêm phiên bản tùy tiện trái với nền tảng.

## 7. Ví dụ chạy được bằng Java 17 và Maven: chứng minh backend runtime

Bài thực hành này cố ý có **một** backend: SLF4J 2.x + Logback Classic. Mã Java kiểm tra factory được nạp tại runtime, sau đó phát một sự kiện. Kết quả có thể dự đoán, không lệ thuộc vào timestamp.

Yêu cầu: **JDK 17+, Maven**, và khả năng lấy các dependency đã khai báo.

Tạo dự án:

```text
logging-dependency-check/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── LoggingDependencyCheck.java
        └── resources/
            └── logback.xml
```

### 7.1. Tệp `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>logging-dependency-check</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-api</artifactId>
            <version>2.0.16</version>
        </dependency>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.16</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-dependency-plugin</artifactId>
                <version>3.8.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Giải thích:

- `slf4j-api`: mã Java dùng API thống nhất.
- `logback-classic`: backend và provider SLF4J 2.x cho ví dụ.
- `logback-core`: được kéo theo theo phụ thuộc của Logback Classic.
- Các plugin Maven cho phép biên dịch Java 17, chạy main và in dependency tree.
- Phiên bản ghi rõ nhằm có ví dụ có thể tái lập; **không tuyên bố là phiên bản mới nhất hoặc không có lỗ hổng hiện tại**.

### 7.2. Tệp `src/main/resources/logback.xml`

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%level|%logger{0}|%msg%n</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE" />
    </root>
</configuration>
```

Đặt pattern không có timestamp và tên luồng để có kết quả ổn định. `logback.xml` chỉ có tác dụng nếu **Logback thật sự là backend đang chạy**. Nếu runtime chọn Log4j 2 hoặc NOP provider, tệp này không điều khiển output của backend ấy.

### 7.3. Tệp `src/main/java/demo/LoggingDependencyCheck.java`

```java
package demo;

import org.slf4j.ILoggerFactory;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class LoggingDependencyCheck {
    private static final Logger LOG =
            LoggerFactory.getLogger(LoggingDependencyCheck.class);

    private LoggingDependencyCheck() {
    }

    public static void main(String[] args) {
        ILoggerFactory factory = LoggerFactory.getILoggerFactory();
        String actual = factory.getClass().getName();
        String expected = "ch.qos.logback.classic.LoggerContext";

        if (!expected.equals(actual)) {
            throw new IllegalStateException(
                    "Unexpected logging factory: " + actual);
        }

        System.out.println("factory=" + actual);
        LOG.info("event=logging.ready api={} backend={}",
                "slf4j", "logback");
    }
}
```

Lệnh chạy từ thư mục dự án:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.LoggingDependencyCheck
```

**Hai dòng do chương trình chủ động in, khi dùng đúng dependencies và cấu hình mẫu:**

```text
factory=ch.qos.logback.classic.LoggerContext
INFO|LoggingDependencyCheck|event=logging.ready api=slf4j backend=logback
```

Maven hoặc môi trường chạy có thể ghi thêm thông báo riêng; nội dung trên là đầu ra ứng dụng dự kiến khi cấu hình được tải chính xác.

### 7.4. Vì sao hai dòng đó có ý nghĩa?

1. `LoggerFactory.getILoggerFactory()` trả về factory được provider SLF4J đang hoạt động cung cấp. Trong Logback Classic, tên implementation phù hợp cho ví dụ là `ch.qos.logback.classic.LoggerContext`.
2. So sánh tên factory khiến chương trình **báo lỗi rõ ràng** nếu runtime chọn provider khác hoặc NOP factory; nó không im lặng kết luận từ sự tồn tại của JAR trong `pom.xml`.
3. Logger `LoggingDependencyCheck` phát `INFO` và root được cấu hình `INFO`, nên sự kiện được chấp nhận.
4. `%logger{0}` cho tên ngắn `LoggingDependencyCheck`; `%msg` chứa tham số sau khi thay `{}`.
5. Ví dụ chứng minh backend thực tế của **đường SLF4J trong process đang chạy bằng Maven**. Nó không tự chứng minh rằng bản Docker/fat JAR được đóng gói về sau có classpath giống vậy.

### 7.5. Kiểm tra cây dependency của chính bài mẫu

```bash
mvn dependency:tree
mvn dependency:tree -Dincludes=org.slf4j
mvn dependency:tree -Dincludes=ch.qos.logback
```

Mục tiêu là xác minh `slf4j-api`, `logback-classic` và `logback-core` đang nằm trong cây, không có provider ngoài ý muốn. Việc công cụ in các dòng tree, conflict và phiên bản phụ thuộc bắc cầu cụ thể có thể thay đổi theo metadata của bản phát hành; đừng viết test phụ thuộc toàn bộ chuỗi text tree.

## 8. Ma trận các cách kết hợp thường gặp

| Mã ứng dụng gọi | Backend muốn dùng | Thành phần cần hiểu | Tệp cấu hình thường gặp |
| --- | --- | --- | --- |
| SLF4J 2.x | Logback | `slf4j-api` + `logback-classic` tương thích | `logback.xml` |
| SLF4J 2.x | Log4j 2 | `slf4j-api` + `log4j-slf4j2-impl` + `log4j-core` tương thích | `log4j2.xml` |
| API Log4j 2 | Log4j 2 | `log4j-api` + `log4j-core` | `log4j2.xml` |
| JUL | JUL | API `java.util.logging` của JDK và handler | `logging.properties` |
| SLF4J 2.x | JUL | `slf4j-jdk14` provider tương thích | Cấu hình JUL |
| Commons Logging | SLF4J + backend cuối | Một bridge được chọn rõ ràng, ví dụ `jcl-over-slf4j` | Theo backend cuối |
| JUL | SLF4J + backend cuối | `jul-to-slf4j` và bridge JUL được cài ở runtime | Theo backend cuối |

Bảng mô tả **hướng đi cần thiết**, không phải gợi ý cài tất cả thư viện vào cùng một ứng dụng. Đặc biệt, không nên coi `log4j-core` và `logback-classic` cùng xuất hiện trên classpath là bằng chứng chắc chắn có hai SLF4J provider; phải xem bridge/provider nào có mặt và cái nào thực sự được nạp.

### Bridge đi theo hướng nào?

Trong tên dependency, thứ tự ký hiệu rất dễ gây nhầm:

```text
log4j-to-slf4j
    Log4j 2 API  ---> SLF4J

log4j-slf4j2-impl
    SLF4J 2.x    ---> Log4j 2

jul-to-slf4j
    JUL          ---> SLF4J

slf4j-jdk14
    SLF4J        ---> JUL

jcl-over-slf4j
    Commons Logging ---> SLF4J

slf4j-jcl
    SLF4J        ---> Commons Logging
```

Nếu ghép **hai bridge đối nghịch** theo cách tạo vòng, một sự kiện có thể chạy qua lại giữa các API/implementation thay vì tới backend cuối.

## 9. Phát hiện và sửa vòng chuyển tiếp logging

### 9.1. Log4j 2 API ↔ SLF4J

Một sai lầm nghiêm trọng là để đồng thời:

- `log4j-to-slf4j`: Log4j 2 API → SLF4J.
- `log4j-slf4j2-impl`: SLF4J 2 → Log4j 2.

Đây là **hai hướng ngược nhau**. Không sử dụng chúng cùng nhau như một tuyến logging duy nhất vì có thể tạo vòng chuyển tiếp; các phiên bản và implementation còn có thể chủ động phát hiện hoặc từ chối tổ hợp sai.

Chọn một kiến trúc:

**Phương án A — Log4j 2 là backend cuối**

```text
SLF4J calls ---> log4j-slf4j2-impl ---> Log4j 2 Core
Log4j 2 API calls --------------------> Log4j 2 Core
```

Loại `log4j-to-slf4j` khỏi runtime khi dùng tuyến này.

**Phương án B — Logback là backend cuối**

```text
SLF4J calls ---------------------> Logback Classic
Log4j 2 API calls -> log4j-to-slf4j -> SLF4J -> Logback
```

Không đưa `log4j-slf4j2-impl` vào runtime của tuyến này.

Mục tiêu không phải xóa mọi dependency có chữ “log4j”. Một thư viện có thể chỉ dùng **`log4j-api`** mà không đưa `log4j-core`; hãy xem rõ đường dẫn và backend mong muốn trước khi thêm exclusions.

### 9.2. JUL ↔ SLF4J

Nếu ứng dụng muốn đưa **JUL → SLF4J → Logback**, có thể sử dụng `jul-to-slf4j` và cài `SLF4JBridgeHandler` trong runtime theo hướng dẫn của library/framework.

Không được đồng thời cấu hình **SLF4J → JUL** bằng `slf4j-jdk14` rồi lại cài bridge **JUL → SLF4J** theo hướng đối nghịch, vì có thể tạo vòng ghi log khi đường đi thực sự được kích hoạt.

Một điểm tinh tế: chỉ thêm JAR `jul-to-slf4j` vào dependency tree chưa chứng minh JUL event đang được bridge. Cần xác định **handler được cài** và cấu hình JUL đang chạy. Một số framework tự quản lý bước này; không được cài trùng hoặc bỏ qua lifecycle của framework.

### 9.3. Commons Logging ↔ SLF4J

`jcl-over-slf4j` chuyển lời gọi Commons Logging về SLF4J. `slf4j-jcl` hướng ngược lại. Tránh cả hai cùng nằm trong một tuyến để không tạo vòng hoặc xung đột class. Với framework có cơ chế Commons Logging riêng (ví dụ các biến thể JCL tích hợp framework), kiểm tra tài liệu và dependency thực tế thay vì thêm bridge theo thói quen.

**Nguyên tắc kiểm tra:** vẽ **mũi tên một chiều từ API đang gọi đến backend cuối cùng**, rồi xác nhận không có mũi tên quay ngược.

## 10. Nhiều provider SLF4J: nhận diện và xử lý

Nếu SLF4J 2.x phát hiện nhiều `SLF4JServiceProvider`, startup có thể báo có nhiều provider và liệt kê class tương ứng. Một tình huống ví dụ:

```text
slf4j-api
logback-classic
log4j-slf4j2-impl
log4j-core
```

Khi cả Logback và provider SLF4J của Log4j 2 cùng có mặt, ứng dụng có thể chọn provider không theo ý muốn. Có thể thấy `logback.xml` dường như bị bỏ qua bởi runtime thực sự chạy Log4j 2, hoặc ngược lại.

Quy trình sửa:

1. Quyết định **backend cuối** trước: Logback hay Log4j 2 hay JUL.
2. Tìm dependency cha đã kéo provider thừa bằng Maven `dependency:tree` hoặc Gradle `dependencyInsight`.
3. Loại provider thừa bằng cách **điều chỉnh dependency đúng module**, dùng exclude khi cần.
4. Giữ provider tương thích với phiên bản API và JDK.
5. Kiểm tra lại runtime dependency tree.
6. Chạy smoke test để xác nhận factory/provider thực sự được chọn.
7. Quan sát một sự kiện mẫu trên đầu ra đã cấu hình, không chỉ kiểm tra thông báo startup.

### Maven: exclusion khi một dependency kéo backend thừa

Ví dụ một module `com.example:legacy-library` đưa vào `logback-classic` ngoài ý muốn, còn ứng dụng chủ đích dùng Log4j 2:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>legacy-library</artifactId>
    <version>1.0.0</version>
    <exclusions>
        <exclusion>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
        </exclusion>
    </exclusions>
</dependency>
```

Đây là **mẫu exclusion**, không phải dependency thực tế đã được kiểm chứng. Phải thay tọa độ library/version bằng module thật trong cây. Maven exclusion áp dụng trên **đường phụ thuộc cụ thể**: nếu provider thừa còn được kéo bởi một nhánh khác, cần xử lý nhánh đó. Không xóa bừa `slf4j-api` nếu các thư viện vẫn cần nó để chạy.

### Gradle: exclude theo nhóm và module

```groovy
dependencies {
    implementation('com.example:legacy-library:1.0.0') {
        exclude group: 'ch.qos.logback', module: 'logback-classic'
    }
}
```

Đây là đoạn cấu hình minh họa. Với Gradle, một exclude ở một cạnh không nhất thiết loại module khỏi toàn bộ graph nếu cạnh khác vẫn yêu cầu nó. Luôn chạy lại `runtimeClasspath` sau khi thay đổi.

## 11. Phát hiện provider/binding ở runtime

**Dependency tree chỉ cho biết các artifact đã được giải.** Runtime có thể khác do ứng dụng được đóng gói thành fat JAR, WAR, chạy trong application server, hệ thống module JPMS, hoặc plugin classloader.

Đối với SLF4J:

```java
String factoryName =
        org.slf4j.LoggerFactory.getILoggerFactory()
                               .getClass()
                               .getName();
System.out.println(factoryName);
```

Đây là **đoạn minh họa**, dùng trong phương thức khi classpath có SLF4J. Nó giúp biết `ILoggerFactory` hiện tại. Ví dụ:

- `ch.qos.logback.classic.LoggerContext`: Logback Classic đang cung cấp factory.
- `org.slf4j.helpers.NOPLoggerFactory`: có thể đang dùng NOP/no-operation implementation.
- Factory của provider khác: cần tra class/provider đó và so với backend thiết kế.

**Không chỉ dựa vào một chuỗi class name để đảm bảo toàn bộ pipeline hoạt động**. Factory đúng vẫn có thể không ghi vì mức log, appender chưa gắn, filter loại hoặc collector không nhận. Kết hợp smoke test **factory + sự kiện mẫu + kiểm tra đích nhận**.

Với Log4j 2 API, có thể xem implementation của LoggerContext và cấu hình thực tế qua các API/chẩn đoán của Log4j Core, nhưng tránh nhầm `org.apache.logging.log4j.LogManager` với `org.slf4j.LoggerFactory`: chúng thuộc hai API khác nhau.

### ServiceLoader và đóng gói JAR

Trong SLF4J 2.x, provider dùng cơ chế Java service, thường được khai báo qua tài nguyên:

```text
META-INF/services/org.slf4j.spi.SLF4JServiceProvider
```

Khi đóng gói fat JAR hoặc shading, nếu build làm mất hoặc ghi đè tệp dịch vụ này, runtime có thể không thấy provider dù bytecode class vẫn hiện diện. Nếu dùng Maven Shade Plugin hoặc công cụ tương tự, cần bảo đảm **service descriptors được xử lý đúng** và chỉ provider mong muốn còn lại.

Tuy nhiên, không nên tự gộp các service descriptor để giữ *mọi* provider logging: nếu cuối cùng có nhiều nhà cung cấp, SLF4J vẫn có thể cảnh báo hoặc chọn một nhà cung cấp không theo ý định. Mục tiêu là **một tuyến runtime đã được thiết kế**, không phải “càng nhiều JAR càng an toàn”.

## 12. Những tình huống thường gặp ở framework và môi trường triển khai

### 12.1. Framework starter đã mang backend

Một số web/application framework có starter logging mặc định. Nếu thêm `log4j-core` hoặc `logback-classic` thủ công mà không nhìn cây dependency, ứng dụng có thể chứa cả backend mặc định lẫn backend mới.

Cách xử lý là xác định **starter nào mang backend** và dùng cơ chế thay thế logging chính thức của framework. Không tự loại các thư viện nền bằng exclusion hàng loạt nếu chưa biết những module nào phụ thuộc API/bridge.

### 12.2. Unit test PASS nhưng production không log

Các khả năng:

- Provider được khai báo ở test scope, không có trong runtime artifact.
- Classpath của `mvn test` khác classpath của `java -jar`.
- Runtime container nạp file cấu hình khác.
- Trình đóng gói fat JAR làm mất SLF4J service descriptor.
- Framework thực tế đang dùng một backend khác, log file cấu hình muốn dùng bị bỏ qua.

Kiểm tra **runtime artifact cuối cùng** và khởi động cùng JVM options/environment với deployment, không dừng ở dependency tree lúc phát triển.

### 12.3. Nhiều classloader hoặc JPMS

Application server, plugin system và JPMS module path có thể làm logic nạp provider phức tạp hơn. Một classloader có thể nhìn thấy SLF4J API nhưng không thấy provider; nơi khác có provider không đúng phiên bản. Đối với JPMS, cần xem các module cung cấp dịch vụ và cơ chế đọc ServiceLoader phù hợp.

Khi chẩn đoán, ghi rõ **JVM, classloader/module path, package artifact và startup command**. Không giả định rằng một lệnh Maven ở workspace cho kết quả giống application server đang chạy ở môi trường khác.

### 12.4. Cảnh báo startup về provider hoặc binding

Các thông báo thường có ý nghĩa:

| Dấu hiệu | Khả năng phổ biến | Điều cần kiểm tra |
| --- | --- | --- |
| “No SLF4J providers were found” | SLF4J 2.x không tìm thấy provider phù hợp | Runtime classpath và service descriptor, provider/binding version. |
| “Multiple SLF4J providers” | Có hơn một provider SLF4J 2.x | Chọn backend duy nhất, tìm và loại provider thừa. |
| Binding nhắm tới SLF4J 1.7 bị bỏ qua | API 2.x đang gặp binding cũ | Đổi sang provider SLF4J 2.x phù hợp. |
| `ClassNotFoundException`/`NoClassDefFoundError` trong logging | Thiếu dependency, sai phiên bản hoặc bị loại khi package | Kiểm tra API/core/provider và artifact cuối. |
| `NoSuchMethodError` khi khởi tạo hoặc gọi logger | Lệch phiên bản API và implementation | Kiểm tra phiên bản đã giải và các JAR trùng. |
| Log không in nhưng không có exception | Logger mức OFF/quá cao, NOP provider, appender/collector không nhận | Smoke test factory, logger level và output. |
| Log in trùng | Appender additivity, bridge/configuration hoặc collector gửi lại | Đếm từng kênh; kiểm tra tuyến logger → appender. |

Không phải mọi dòng cảnh báo liên quan logging đều do “thiếu Logback”. Đọc đúng tên class, artifact, phiên bản, chiều bridge và cấu hình runtime.

## 13. Bộ checklist kiểm tra dependency logging cho dự án thật

Thực hiện các bước theo thứ tự, tránh nhảy thẳng sang sửa `logback.xml` khi chưa xác nhận backend:

1. **Xác định API ở mã Java.** Các package `org.slf4j`, `org.apache.logging.log4j`, `java.util.logging`, `org.apache.commons.logging` cho biết những API được gọi.
2. **Chọn backend mục tiêu.** Ví dụ SLF4J → Logback hoặc SLF4J → Log4j 2. Vẽ tuyến một chiều.
3. **Xem runtime dependency graph.** Maven `dependency:tree`; Gradle `dependencies --configuration runtimeClasspath`.
4. **Đối chiếu phiên bản.** SLF4J API 1.7 hay 2.x? Provider/binding có cùng thế hệ? Backend có hỗ trợ JDK/framework đang chạy?
5. **Đếm provider, không chỉ đếm JAR.** Có NOP, một provider đúng, hay nhiều provider? Class nào thực sự thực hiện `SLF4JServiceProvider`?
6. **Tìm bridge theo hướng.** Có `log4j-to-slf4j` cùng `log4j-slf4j2-impl` không? JUL và SLF4J có hai chiều cùng kích hoạt không?
7. **Xác minh runtime artifact.** JAR/WAR/fat JAR có chứa provider và service descriptor không? Có JAR logging do container bổ sung không?
8. **Xác minh backend runtime.** In factory/class hoặc dùng chẩn đoán thích hợp; không suy đoán từ file cấu hình.
9. **Kiểm tra cấu hình đang được nạp.** `logback.xml` điều khiển Logback, `log4j2.xml` điều khiển Log4j 2; launcher có thể chỉ định đường dẫn khác.
10. **Phát một sự kiện mẫu.** Ghi level, logger name, event code; xác nhận đúng một sự kiện ở kênh mong muốn.
11. **Kiểm tra đường đến collector.** Console/file có log không? Collector có nhận, parse và lưu không?
12. **Chốt bằng regression test.** Test startup với dependency của artifact thực tế để phát hiện provider trùng và sai backend sau nâng phiên bản.

Để áp dụng cho CI, có thể dùng cơ chế phân tích dependency của build tool và một bài smoke test xác định provider cuối. **Không nên dựa duy nhất vào grep tên JAR** vì một dependency API không tự là provider và một số lớp có thể nằm trong artifact được repackaged/shaded.

## 14. Thực hành: ba tình huống kiểm tra có chủ đích

### Tình huống A — Chỉ có SLF4J API

```text
slf4j-api 2.x
không có provider tương thích
```

Dự đoán: mã Java vẫn có thể biên dịch; runtime thường cảnh báo không có provider và có thể dùng NOP logger. Để sửa, **chọn một backend/provider phù hợp**, không chỉ thêm `log4j-api` (API của Log4j 2) rồi hy vọng SLF4J tự nối sang đó.

### Tình huống B — Hai provider

```text
slf4j-api 2.x
logback-classic tương thích
log4j-slf4j2-impl tương thích
log4j-core tương thích
```

Dự đoán: runtime thấy nhiều provider, có thể cảnh báo và lựa chọn một nhà cung cấp. Cách xử lý là chọn một tuyến cuối, loại provider còn lại, rồi kiểm tra lại bằng factory và log mẫu.

### Tình huống C — Vòng Log4j 2 ↔ SLF4J

```text
log4j-to-slf4j           (Log4j 2 API -> SLF4J)
log4j-slf4j2-impl        (SLF4J 2 -> Log4j 2)
```

Đây là cấu hình có nguy cơ tạo vòng và không nên giữ cùng nhau. Nếu chọn Logback, giữ chuyển Log4j 2 API → SLF4J và Logback làm backend. Nếu chọn Log4j 2, giữ chuyển SLF4J → Log4j 2 và bỏ chuyển ngược.

### Tình huống D — API đúng, output sai

```text
SLF4J -> Logback đúng
nhưng không thấy INFO
```

Không thể kết luận do dependency nữa. Tiếp tục kiểm tra:

- Logger name và mức hiệu lực.
- Filter, appender và additivity.
- `logback.xml` nào được nạp.
- Console/file và quyền truy cập.
- Collector có đọc đúng stream và parse đúng không.
- Lỗi mất log do queue, I/O hoặc shutdown.

**Kiểm tra dependency là bước nền, không thay thế kiểm thử cấu hình và dữ liệu đầu ra.**

## 15. Cách tránh tái phát sau nâng cấp dependency

- **Quản lý phiên bản tập trung:** Maven `dependencyManagement`/BOM hoặc Gradle platform/version catalog để tránh các module tự chọn phiên bản SLF4J/Log4j khác nhau.
- **Nâng API cùng provider:** khi thay SLF4J 1.7 bằng 2.x, đổi binding sang provider tương thích; không chỉ nâng một dòng `slf4j-api`.
- **Giữ một backend chủ đích:** ở module chạy ứng dụng, quản lý provider cuối; ở thư viện tái sử dụng, ưu tiên chỉ phụ thuộc API nếu không có yêu cầu đặc biệt.
- **Đánh giá các dependency bắc cầu:** đặc biệt các starter framework và SDK có thể đưa thêm logging implementation.
- **Chạy smoke test cả artifact cuối:** test `java -jar` hoặc launcher production thực tế, không chỉ Maven exec.
- **Theo dõi cảnh báo startup:** fail build/test khi xuất hiện binding/provider sai đã được xác định; đừng bỏ qua vì “ứng dụng vẫn chạy”.
- **Theo dõi bảo mật:** cập nhật bản vá được hỗ trợ của backend và các bridge. Chọn phiên bản theo khuyến cáo bảo mật/khả năng tương thích hiện tại, không sao chép mãi phiên bản của một ví dụ học tập.
- **Thử shutdown và tải cao:** backend async hoặc collector có thể mất bản ghi; provider đúng không bảo đảm tính bền vững.
- **Bảo vệ dữ liệu nhạy cảm:** thay backend hoặc formatter có thể thay đổi cách ghi Throwable/MDC; kiểm tra token, mật khẩu và dữ liệu riêng tư ở mọi kênh.
- **Ghi nhận kiến trúc logging:** mô tả bằng sơ đồ mũi tên cùng danh sách dependency chủ chốt, người chịu trách nhiệm, tập cấu hình và quy trình nâng cấp.

## 16. Bài tập tự kiểm tra

### Bài 1 — Phân biệt API, provider và backend

Một ứng dụng import `org.slf4j.Logger`, khai báo `slf4j-api` nhưng không có implementation phù hợp. Nó có thể biên dịch được không? Có chắc log xuất ra console không?

**Gợi ý:** Mã có thể biên dịch vì API có mặt. Không có provider SLF4J 2.x phù hợp thì runtime có thể dùng NOP/no-operation logger; không thể kết luận có log. Cần thêm một backend/provider đúng và kiểm tra runtime.

### Bài 2 — Nhận diện xung đột

Cây dependency cuối cùng có `slf4j-api 2.x`, `logback-classic`, `log4j-slf4j2-impl` và `log4j-core`. Bạn sẽ sửa theo các bước nào?

**Gợi ý:** Chọn backend mong muốn; tìm dependency cha kéo provider ngoài ý muốn; loại module dư ở đường phù hợp; xem lại `runtimeClasspath`; chạy factory smoke test và kiểm tra log mẫu. Không cố “tăng thứ tự ưu tiên” classpath làm giải pháp bền vững.

### Bài 3 — Vòng chuyển tiếp

Vì sao không nên dùng đồng thời `log4j-to-slf4j` và `log4j-slf4j2-impl`?

**Gợi ý:** Hai module có hướng ngược nhau: Log4j 2 API → SLF4J và SLF4J → Log4j 2. Dùng chung có thể tạo vòng chuyển tiếp thay vì đến backend cuối. Chọn một hướng và một implementation.

### Bài 4 — Test chạy nhưng production im lặng

Dự án test có log bằng Logback, song `java -jar` trong container không có log. Hãy nêu ít nhất năm thứ cần kiểm tra.

**Gợi ý:** Test/runtime scope; dependency của artifact cuối; fat JAR service descriptor; classloader; provider thực sự; JVM arguments; cấu hình `logback.xml`, mức logger; appender; stdout/file collector. Kết quả compile/test không phải bằng chứng runtime production giống hệt.

### Bài 5 — Phân tích lệnh build

Mục đích của hai lệnh sau khác nhau thế nào?

```bash
mvn dependency:tree
./gradlew dependencyInsight --dependency slf4j-api --configuration runtimeClasspath
```

**Gợi ý:** Maven in cây của dự án theo dependency resolution; Gradle `dependencyInsight` phân tích tại sao một dependency và phiên bản của nó được chọn trong configuration cụ thể. Để xem cả cây Gradle, dùng `dependencies --configuration runtimeClasspath`.

### Bài 6 — Kiểm tra logging không bị trùng

Một sự kiện `order.created` xuất hai lần ở console. Có thể kết luận do hai provider SLF4J không?

**Gợi ý:** Chưa. Nhiều provider thường là vấn đề lựa chọn provider; log trùng còn có thể do appender gắn ở logger con và root, bridge được cấu hình sai, hai lời gọi log trong mã hoặc collector gửi lại. Kiểm tra **provider**, rồi **logger route/appender/additivity**, sau đó **pipeline thu thập**.

### Bài 7 — Thiết kế thư viện Java tái sử dụng

Bạn đang viết một thư viện Java được đưa vào nhiều ứng dụng, mỗi ứng dụng dùng backend khác nhau. Thư viện nên khai báo dependency logging như thế nào?

**Gợi ý:** Thường để thư viện phụ thuộc **API/facade** phù hợp mà không ép toàn bộ ứng dụng dùng một backend. Module ứng dụng chịu trách nhiệm chọn provider thực tế và cấu hình output. Nếu thư viện cần cầu nối logging của hệ thống legacy, phải ghi rõ hướng bridge và tránh gây xung đột cho người tiêu dùng.

**Kết luận:** Một hệ thống logging ổn định cần **đúng API, đúng provider/binding, đúng backend, đúng hướng bridge và đúng classpath tại runtime**. Kiểm tra cây dependency để biết *có gì*, kiểm tra factory/provider để biết *đang dùng gì*, và phát sự kiện mẫu để biết *log có tới nơi hay không*.