# JUL bridge: chuyển java.util.logging sang SLF4J và backend

**JUL bridge** là cơ chế đưa các sự kiện do **Java Util Logging** (`java.util.logging`, viết tắt **JUL**) phát ra vào **SLF4J facade**, để chúng được xử lý bởi backend mà ứng dụng đã chọn, chẳng hạn **Logback** hoặc **Log4j 2**. Cơ chế được dùng phổ biến là thư viện `org.slf4j:jul-to-slf4j` và lớp **`org.slf4j.bridge.SLF4JBridgeHandler`**.

Ý tưởng: thư viện cũ vẫn gọi `java.util.logging.Logger`; ứng dụng không cần sửa mã thư viện đó, nhưng có thể gom bản ghi của nó vào một logging pipeline chung.

~~~text
Thư viện legacy gọi JUL                 Mã ứng dụng gọi SLF4J
java.util.logging.Logger                org.slf4j.Logger
          |                                     |
       JUL Logger                                |
   (level và filter)                             |
          |                                     |
          v                                     |
 JUL Handler: SLF4JBridgeHandler                 |
          |                                     |
          +------------- SLF4J API <------------+
                              |
                     SLF4J provider
                              |
                  Logback / Log4j 2 / ...
                              |
                     Appender và filter
                              |
                   stdout / file / collector
~~~

**Nhớ chiều chuyển tiếp:** `jul-to-slf4j` là **JUL → SLF4J**, không phải SLF4J → JUL. Đầu ra cuối cùng vẫn phụ thuộc một **SLF4J provider/backend** có thật ở runtime và cấu hình của backend đó.

## 1. Bài toán mà JUL bridge giải quyết

Trong ứng dụng Java lớn, các thư viện có thể sử dụng nhiều logging API:

| Thành phần mã | API thường dùng | Vấn đề khi vận hành |
| --- | --- | --- |
| Một thư viện Java lâu đời | `java.util.logging.Logger` | Có thể in qua JUL ConsoleHandler với format và level riêng |
| Mã ứng dụng | `org.slf4j.Logger` | Được đưa tới Logback theo cấu hình chung |
| Một thư viện khác | Log4j 2 API hoặc Commons Logging | Có thể lại dùng tuyến ghi khác |
| Backend được chọn | Logback hoặc Log4j 2 | Chỉ nhận đầy đủ các nguồn đã được nối vào đúng tuyến |

Nếu JUL và SLF4J chạy riêng, người vận hành có thể gặp hai kiểu timestamp/pattern, hai ngưỡng mức log, hai nơi ghi, hoặc JUL stderr nằm ngoài file do Logback quản lý. Khi thêm JUL bridge đúng chiều, nhiều bản ghi JUL có thể được định dạng và định tuyến cùng những log SLF4J khác.

Các lợi ích thường gặp:

1. **Tập trung cấu hình đầu ra:** appender, pattern/encoder, file rolling và collector được quản lý tại backend chung.
2. **Dễ tương quan sự kiện:** một logger name và event message từ thư viện JUL có thể xuất cùng log ứng dụng.
3. **Giảm cấu hình song song:** hạn chế phải duy trì riêng console/file handler cho JUL và appender cho Logback.
4. **Không sửa mã thư viện nguồn:** thư viện vẫn dùng JUL, bridge làm vai trò chuyển tiếp ở runtime.

**Giới hạn:** bridge không tự biến mọi bản ghi thành JSON có cấu trúc, không tự sinh requestId/traceId, không bảo đảm không mất log và không thay thế việc bảo vệ dữ liệu nhạy cảm ở nguồn phát.

## 2. Phân biệt bridge, facade, provider và backend

| Thành phần | Artifact/lớp minh họa | Vai trò |
| --- | --- | --- |
| **Nguồn JUL** | `java.util.logging.Logger` | Phát `LogRecord` từ thư viện hoặc ứng dụng |
| **Bridge JUL → SLF4J** | `jul-to-slf4j`, `SLF4JBridgeHandler` | Chuyển JUL record vào SLF4J |
| **Facade SLF4J** | `slf4j-api` | Giao diện chung `Logger`, `LoggerFactory` |
| **Provider SLF4J 2.x** | Trong `logback-classic` hoặc `log4j-slf4j2-impl` | Được SLF4J tìm để chọn implementation khi chạy |
| **Backend** | Logback, Log4j 2 hoặc JUL | Lọc, format và ghi bản ghi |
| **Đích ghi** | ConsoleAppender, FileAppender, collector | Nhận log đã xử lý |

**Không nhầm `jul-to-slf4j` với một SLF4J provider.** Nếu chỉ có `jul-to-slf4j` và `slf4j-api` nhưng thiếu provider, sự kiện JUL có thể được chuyển sang SLF4J rồi rơi vào **NOP logger**: không có output mong đợi.

Ngược lại, có `logback-classic` mà không lắp bridge thì Logback vẫn nhận những lời gọi SLF4J thông thường, nhưng không tự bảo đảm các lời gọi `java.util.logging.Logger` sẽ đi vào Logback.

### Cơ chế SLF4J theo phiên bản

- SLF4J **1.7.x** dùng binding kiểu `StaticLoggerBinder`; chọn artifact binding tương thích phiên bản đó.
- SLF4J **2.x** dùng `SLF4JServiceProvider` qua `ServiceLoader`; cần provider đúng major version.
- `jul-to-slf4j` là **bridge ở phía nguồn JUL**, không phải binding kiểu cũ hay provider kiểu mới. Dù dùng bridge, ứng dụng vẫn cần chọn đúng backend theo phiên bản facade.

Một hệ thống đang dùng SLF4J 2.x mà chỉ có binding legacy 1.7 vẫn có thể báo thiếu provider; thêm JUL bridge **không sửa** mismatch đó.

## 3. SLF4JBridgeHandler thực sự hoạt động như thế nào?

`SLF4JBridgeHandler` là một **JUL Handler**. Khi được gắn vào hệ JUL, nó nhận `LogRecord` đã vượt qua những kiểm tra ở phía JUL rồi chuyển sự kiện tương ứng sang SLF4J.

Luồng chi tiết:

~~~text
julLogger.info(...) / julLogger.warning(...)
                  |
                  v
            JUL Logger
     logger level + logger filter
                  |
                  v
           JUL LogRecord
                  |
       handlers gắn với logger
                  |
         parent handlers nếu bật
                  |
                  v
        SLF4JBridgeHandler
           (JUL Handler)
                  |
           ánh xạ JUL level
                  |
                  v
       LoggerFactory / SLF4J Logger
                  |
      SLF4J provider và backend
                  |
       backend level/filter/appender
                  |
                  v
                Output
~~~

Hai ngưỡng đáng phân biệt:

- **JUL chấp nhận sự kiện hay không:** nếu `java.util.logging.Logger` loại FINE ở ngưỡng INFO, không có `LogRecord` tới bridge; backend DEBUG cũng không thể phục hồi sự kiện đã bị JUL loại.
- **Backend có xuất sự kiện đã bridge hay không:** khi JUL chấp nhận FINE và bridge chuyển thành DEBUG, Logback vẫn có thể loại DEBUG nếu effective level của Logback logger là INFO.

Bridge không tắt bộ lọc JUL bằng phép màu. Khi không thấy DEBUG của thư viện JUL, **kiểm tra cả JUL level và backend level**, thay vì chỉ kiểm tra `logback.xml`.

### JUL logger name và log context

Bridge thường dùng tên logger được gắn với `LogRecord` để chọn logger tương ứng ở phía SLF4J. Ví dụ một record có logger name `com.vendor.client.HttpTransport` có thể tới logger cùng tên trong backend và chịu cấu hình của namespace đó.

Tuy nhiên **không có nghĩa mọi metadata của JUL tự chuyển thành field có cấu trúc** ở mọi backend. Thông tin Throwable/message có thể được chuyển tiếp, nhưng cách format tham số, resource bundle, caller data và structured fields cần được kiểm tra với version và backend cụ thể. Nếu cần JSON hoặc traceId, hãy cấu hình encoder/context ở pipeline cuối.

## 4. Cài bridge: ba việc khác nhau

Để dùng `jul-to-slf4j` với Logback:

1. **Đưa `jul-to-slf4j` vào runtime dependency** cùng `slf4j-api` và Logback provider/backend tương thích.
2. **Lắp `SLF4JBridgeHandler` vào JUL**, thường trên root JUL logger, đủ sớm trong quá trình khởi động.
3. **Quản lý các JUL handler đã tồn tại** để tránh cùng một record vừa đi qua bridge vừa được ghi trực tiếp bởi ConsoleHandler/FileHandler cũ.

Các API thường dùng:

~~~java
// Đoạn cấu hình startup: không phải chương trình độc lập.
import org.slf4j.bridge.SLF4JBridgeHandler;

SLF4JBridgeHandler.removeHandlersForRootLogger();
SLF4JBridgeHandler.install();
~~~

Ý nghĩa:

- `removeHandlersForRootLogger()` gỡ các **handler đang gắn trực tiếp với root JUL logger**, giúp tránh vừa dùng root ConsoleHandler JUL vừa đưa record qua bridge.
- `install()` **gắn một instance bridge handler vào root JUL logger**. Nếu cần xác minh, dùng `SLF4JBridgeHandler.isInstalled()`.
- Đây là hành động **thay đổi logging toàn cục trong cùng JVM**. Chỉ thực hiện khi ứng dụng sở hữu quá trình khởi tạo JUL, không tùy tiện xóa root handlers do application server/framework/thư viện quan trọng khác quản lý.
- Cài bridge **một lần** vào lúc startup, không gọi `install()` từ mỗi class hoặc mỗi request. Cài lặp có thể khiến nhiều handler bridge cùng nhận một event, tạo log trùng.
- Gỡ các **root** JUL handlers không tự gỡ handler riêng gắn ở các JUL logger con. Nếu một logger con còn FileHandler hoặc ConsoleHandler, bản ghi vẫn có thể đi qua hai đường. Cần kiểm tra cấu hình thực tế.

**Nếu framework đã cài JUL bridge**, không tự gọi lại các phương thức trên chỉ vì muốn “chắc chắn”. Hãy xác định chủ thể quản lý hệ logging của ứng dụng.

### Cài sớm mới nhận được sự kiện sớm

Bridge bắt đầu nhận những JUL records phát sau khi nó được gắn. Các message phát trước lúc `install()` **không được phát lại**. Thư viện có thể log rất sớm trong static initializer hoặc giai đoạn bootstrapping; khi cần những bản ghi ấy, tích hợp bridge ở giai đoạn khởi tạo logging của framework/container.

## 5. Mức log được ánh xạ như thế nào?

JUL và SLF4J dùng tên level khác nhau. Một cách đọc thông dụng với `SLF4JBridgeHandler` là:

| JUL Level | Mức SLF4J tương ứng thường dùng | Mục đích |
| --- | --- | --- |
| `SEVERE` | ERROR | Lỗi nghiêm trọng |
| `WARNING` | WARN | Cảnh báo |
| `INFO` | INFO | Sự kiện thông tin |
| `CONFIG` | DEBUG | Chi tiết cấu hình |
| `FINE` | DEBUG | Chẩn đoán |
| `FINER` / `FINEST` | TRACE | Chẩn đoán rất chi tiết |

`ALL` và `OFF` thường được dùng như **ngưỡng lọc của JUL**, không phải những mức log nghiệp vụ nên chủ động phát. Nếu có custom JUL levels, cần kiểm tra quy tắc ánh xạ của phiên bản bridge sử dụng.

Lưu ý **hai bước lọc**:

| JUL Logger level | Record | Backend Logback level | Kết quả |
| --- | --- | --- | --- |
| INFO | FINE | DEBUG | Không có log: JUL loại FINE trước bridge |
| FINE | FINE | INFO | FINE được bridge thành DEBUG, rồi backend loại |
| FINE | FINE | DEBUG | Có thể xuất DEBUG nếu appender/filter cho phép |
| INFO | WARNING | INFO | Có thể xuất WARN nếu tuyến bridge và appender đúng |
| OFF | INFO | TRACE | Không có log: JUL tắt ngay tại nguồn |

Khi phân tích kết quả, còn phải xét JUL Filter, parent handlers, appender filter và đích ghi. Hai cột level không mô tả mọi điều kiện trong một ứng dụng thực tế.

## 6. Ví dụ Maven + Java 17+: JUL và SLF4J cùng đi qua Logback

Ví dụ sau dùng một chương trình Java và ba dependency:

- **SLF4J API 2.0.17:** facade cho logging.
- **jul-to-slf4j 2.0.17:** JUL Handler bridge.
- **Logback 1.5.18:** SLF4J provider/backend.

Đây là **bộ phiên bản minh họa đã biên dịch và chạy thực tế**, không phải tuyên bố về phiên bản mới nhất. Dự án production nên quản lý dependency theo phiên bản tương thích và chính sách cập nhật riêng.

### 6.1. Cấu trúc dự án

~~~text
jul-bridge-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/demo/JulBridgeDemo.java
        └── resources/logback.xml
~~~

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>jul-bridge-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.slf4j</groupId>
      <artifactId>slf4j-api</artifactId>
      <version>2.0.17</version>
    </dependency>
    <dependency>
      <groupId>org.slf4j</groupId>
      <artifactId>jul-to-slf4j</artifactId>
      <version>2.0.17</version>
    </dependency>
    <dependency>
      <groupId>ch.qos.logback</groupId>
      <artifactId>logback-classic</artifactId>
      <version>1.5.18</version>
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
        <version>3.5.1</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Nếu dự án đã kéo `slf4j-api` qua `logback-classic`, Maven có thể giải quyết dependency đó gián tiếp; ví dụ khai báo tường minh để người học thấy **facade / bridge / provider** là các trách nhiệm khác nhau.

### 6.3. JulBridgeDemo.java

Tạo `src/main/java/demo/JulBridgeDemo.java`:

~~~java
package demo;

import java.util.logging.Level;
import java.util.logging.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.bridge.SLF4JBridgeHandler;

public final class JulBridgeDemo {
    private static final Logger JUL =
            Logger.getLogger("demo.legacy.PaymentClient");
    private static final org.slf4j.Logger SLF4J =
            LoggerFactory.getLogger(JulBridgeDemo.class);

    public static void main(String[] args) {
        SLF4JBridgeHandler.removeHandlersForRootLogger();
        SLF4JBridgeHandler.install();

        JUL.setLevel(Level.FINE);

        JUL.info("event=legacy_ready");
        JUL.warning("event=legacy_retry attempt=2");
        JUL.fine("event=legacy_diagnostic");
        SLF4J.info("event=modern_ready");

        System.out.println("bridgeInstalled="
                + SLF4JBridgeHandler.isInstalled());
    }
}
~~~

Điểm quan trọng:

- `JUL` thuộc `java.util.logging.Logger`; `SLF4J` thuộc `org.slf4j.Logger`. Hai class có tên Logger tương tự nhưng **khác API**.
- `removeHandlersForRootLogger()` gỡ handler root JUL trong ví dụ để tránh in bản ghi JUL qua đường cũ.
- `install()` gắn bridge vào root JUL; các JUL logger con như `demo.legacy.PaymentClient` thường chuyển record lên root nếu chưa tắt parent handlers.
- `JUL.setLevel(Level.FINE)` cho phép FINE vượt qua **bước kiểm tra level của JUL**. Nếu bỏ dòng này, cấu hình JUL mặc định có thể loại FINE trước khi tới bridge.
- `SLF4J.info(...)` là đường đi trực tiếp vào facade, không cần qua JUL bridge.
- `isInstalled()` kiểm tra bridge handler đang được gắn vào root JUL.
- Trong ứng dụng nhiều lớp, logic cài bridge thuộc **startup/configuration**, không nằm trong từng lớp nghiệp vụ.

Chương trình chạy ngắn nên không minh họa cleanup. Nếu xây ứng dụng/plugin quản lý vòng đời logger riêng, có thể tìm hiểu `SLF4JBridgeHandler.uninstall()`; không tự tháo bridge đang được framework hoặc các thành phần khác sử dụng.

### 6.4. logback.xml

Tạo `src/main/resources/logback.xml`:

~~~xml
<configuration>
  <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
    <encoder><pattern>%level | %logger | %msg%n</pattern></encoder>
  </appender>

  <logger name="demo.legacy" level="DEBUG"/>

  <root level="INFO">
    <appender-ref ref="CONSOLE"/>
  </root>
</configuration>
~~~

Ở đây logger namespace `demo.legacy` cho phép DEBUG, root giữ INFO. Logback ConsoleAppender nhận cả bản ghi JUL đã bridge và bản ghi SLF4J trực tiếp, theo **cùng một pattern**.

### 6.5. Biên dịch, chạy và kết quả

Từ thư mục có `pom.xml`, dùng JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.JulBridgeDemo
~~~

**Output chính xác** của chương trình với các tệp trên:

~~~text
INFO | demo.legacy.PaymentClient | event=legacy_ready
WARN | demo.legacy.PaymentClient | event=legacy_retry attempt=2
DEBUG | demo.legacy.PaymentClient | event=legacy_diagnostic
INFO | demo.JulBridgeDemo | event=modern_ready
bridgeInstalled=true
~~~

Giải thích kết quả:

1. JUL `INFO` được chuyển sang SLF4J/Logback `INFO`.
2. JUL `WARNING` được chuyển sang `WARN`.
3. JUL `FINE` được chuyển sang `DEBUG`; record này xuất được vì JUL logger chấp nhận FINE **và** Logback logger `demo.legacy` cho phép DEBUG.
4. Log SLF4J trực tiếp `modern_ready` đi qua cùng appender, hiển thị giống các bản ghi từ JUL.
5. Dòng `bridgeInstalled=true` do `System.out.println` phát, **không phải một log event đi qua SLF4J**.

Trong ví dụ, thông điệp JUL là các chuỗi cố định. Khi dùng JUL `{0}`/resource bundles, hãy kiểm tra cách version bridge/backend format tham số. **Không mặc định** template JUL `{0}` hoạt động giống cú pháp `{}` của SLF4J.

## 7. JUL bridge với Gradle

Nếu muốn biểu diễn cùng lựa chọn dependency trong Gradle Groovy DSL:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.slf4j:slf4j-api:2.0.17'
    runtimeOnly 'org.slf4j:jul-to-slf4j:2.0.17'
    runtimeOnly 'ch.qos.logback:logback-classic:1.5.18'
}

application {
    mainClass = 'demo.JulBridgeDemo'
}
~~~

**Lưu ý quan trọng:** mã `JulBridgeDemo.java` import trực tiếp `org.slf4j.bridge.SLF4JBridgeHandler`, vì vậy **ví dụ Java được đưa ở phần trước cần `jul-to-slf4j` trên compile classpath**. Nếu muốn copy nguyên ví dụ đó sang Gradle, hãy dùng cấu hình sau thay cho dòng `runtimeOnly 'org.slf4j:jul-to-slf4j:2.0.17'` ở trên:

~~~groovy
implementation 'org.slf4j:jul-to-slf4j:2.0.17'
~~~

Đây là nguyên tắc phân biệt dependency quan trọng: **`implementation` khi mã trực tiếp import bridge**, còn `runtimeOnly` có thể phù hợp nếu framework/bootstrap khác đã nạp bridge một cách gián tiếp và mã ứng dụng không phụ thuộc class bridge lúc biên dịch.

Khi dùng Gradle Wrapper của dự án:

~~~bash
./gradlew run
~~~

Tệp `logback.xml` vẫn đặt ở `src/main/resources`. Nếu một framework đã cung cấp logging starter và bridge, không tự thêm dependencies trùng trước khi xem runtime dependency graph.

## 8. Lỗi phổ biến nhất: cài bridge nhưng JUL FINE vẫn không thấy

Giả sử bạn đã:

~~~xml
<logger name="com.vendor" level="DEBUG"/>
~~~

trong Logback. Nhưng thư viện JUL dưới `com.vendor` phát `julLogger.fine(...)` mà không có output.

**Nguyên nhân có thể nằm ở JUL:** effective level của JUL logger đang là INFO. Record FINE bị chặn **trước** khi đến bridge. Đổi Logback logger sang TRACE cũng không giúp vì bridge chưa thấy record.

Có ba hướng xử lý:

1. **Cấu hình JUL level** đủ chi tiết cho namespace nguồn, ví dụ `java.util.logging.Logger.getLogger("com.vendor").setLevel(Level.FINE)`. Nếu thư viện con không có level riêng thì có thể kế thừa mức FINE.
2. **Dùng JUL `logging.properties`** hoặc cơ chế cấu hình phù hợp để đặt level cho các JUL logger cần chuyển.
3. **Với Logback**, xem xét `LevelChangePropagator` nhằm đồng bộ các level Logback thích hợp sang JUL để giảm chi phí chuyển tiếp không cần thiết.

Không nên giải quyết bằng cách đặt **toàn JVM** vào ALL rồi để Logback lọc một lượng log rất lớn nếu ứng dụng có tải cao: JUL vẫn có thể tạo `LogRecord` và gọi bridge cho các bản ghi cuối cùng bị backend loại.

### LevelChangePropagator của Logback

Logback có `ch.qos.logback.classic.jul.LevelChangePropagator`, một context listener hỗ trợ chuyển một số thay đổi level của Logback sang JUL:

~~~xml
<configuration>
  <contextListener class="ch.qos.logback.classic.jul.LevelChangePropagator">
    <resetJUL>true</resetJUL>
  </contextListener>

  <!-- Appender, logger và root được khai báo như cấu hình Logback bình thường -->
</configuration>
~~~

Đây là **đoạn cấu hình minh họa**, không phải file `logback.xml` độc lập. Khi dùng, phải hiểu ảnh hưởng lên **các JUL logger toàn JVM** và chỉ bật nếu ứng dụng cho phép Logback kiểm soát level JUL.

**LevelChangePropagator không tự cài `SLF4JBridgeHandler`**. Nó phục vụ phần **đồng bộ ngưỡng level**, còn bridge handler phục vụ **chuyển LogRecord**. Hai vai trò khác nhau. Thứ tự khởi tạo, logger đang tồn tại và framework đang quản lý cấu hình đều cần được kiểm tra khi tích hợp.

## 9. Rủi ro hiệu năng khi chuyển JUL sang SLF4J

Bridge có chi phí trung gian: tạo/nhận `LogRecord` JUL, lấy thông tin cần thiết, ánh xạ level và gọi lại Logger phía SLF4J.

Trường hợp tốt: JUL đã loại sự kiện chi tiết không cần thiết hoặc level được đồng bộ hợp lý. Trường hợp xấu: nhiều JUL FINEST/FINER được chấp nhận ở JUL rồi mới bị Logback INFO loại; sự kiện không được xuất nhưng hệ thống vẫn đã tốn chi phí.

Các điểm cần kiểm tra:

- **Hot path:** thư viện tạo hàng chục nghìn bản ghi chi tiết mỗi giây thì bridge có thể trở thành một phần chi phí đáng kể.
- **Level đồng bộ:** JUL và Logback phải thống nhất mức chi tiết theo nhu cầu điều tra thực tế.
- **Tham số message:** cấu trúc thông điệp và cách format có thể tạo thêm chi phí, đặc biệt với object nặng.
- **Stack trace:** exception và caller/location data có thể đắt tiền nếu bật không cần thiết.
- **Backend appender:** file, async queue, network và JSON encoder thường cũng đóng góp chi phí; không đổ mọi độ trễ lên bridge.

Dùng test tải hoặc profiling nếu hệ thống có khối lượng log đáng kể; không suy ra hiệu năng chỉ từ số dòng console trong ví dụ nhỏ.

## 10. Tránh vòng lặp JUL ↔ SLF4J

Đây là lỗi thiết kế nguy hiểm nhất khi chọn các dependency theo tên mà không nhìn **chiều chuyển tiếp**.

### Chiều đúng khi Logback là backend

~~~text
JUL --jul-to-slf4j--> SLF4J --Logback provider--> Logback
~~~

Đây là tuyến một chiều. Logback là backend cuối, không đẩy trở lại JUL.

### Chiều ngược: slf4j-jdk14

`org.slf4j:slf4j-jdk14` là **provider chuyển SLF4J → JUL**. Nó có ích nếu ứng dụng chủ động chọn JUL làm backend, **nhưng không phải một JUL bridge thay thế**.

Nếu một ứng dụng đồng thời cài `jul-to-slf4j` để JUL → SLF4J và chọn `slf4j-jdk14` làm provider SLF4J → JUL, có thể hình thành:

~~~text
JUL --> SLF4J --> JUL --> SLF4J --> ...
~~~

Vòng lặp này có thể gây đệ quy logging nghiêm trọng, thậm chí `StackOverflowError` hoặc mất khả năng quan sát. **Không cố chạy thử cấu hình vòng lặp trên hệ thống thật.**

| Muốn backend cuối là | Provider ở phía SLF4J | Có nên cài JUL → SLF4J? |
| --- | --- | --- |
| Logback | `logback-classic` phù hợp SLF4J API | Có, nếu cần gom JUL vào Logback |
| Log4j 2 | `log4j-slf4j2-impl` cho SLF4J 2.x | Có thể, nếu không tạo tuyến ngược |
| JUL | `slf4j-jdk14` phù hợp SLF4J API | **Không** cài bridge JUL → SLF4J vào cùng tuyến |
| SLF4J Simple | `slf4j-simple` | Chỉ khi cần JUL qua Simple và hiểu giới hạn |

Một vòng tương tự có thể xảy ra nếu đồng thời dùng **`log4j-to-slf4j`** (Log4j 2 API → SLF4J) và **`log4j-slf4j2-impl`** (SLF4J → Log4j 2). Đây không phải JUL bridge, nhưng cùng bài học: **vẽ rõ các mũi tên trước khi thêm bridge**.

### Bridge không quyết định provider

`jul-to-slf4j` không tự chọn Logback. Nếu runtime vô tình nạp `slf4j-simple` thay Logback, bridge có thể đưa JUL tới SimpleLogger. Nếu runtime không có provider, có thể rơi vào NOP. Luôn xác minh backend/provider thực sự ở runtime.

## 11. Tránh log trùng: root handler và handler ở logger con

Nếu JUL root vẫn có ConsoleHandler và bạn chỉ gọi `SLF4JBridgeHandler.install()`, một record JUL có thể:

1. Được ConsoleHandler JUL in trực tiếp ra stderr.
2. Được bridge chuyển vào SLF4J rồi backend Logback in ra console.

Một sự kiện sẽ có **hai dòng định dạng khác nhau**. Đây không phải vì ứng dụng gọi logger hai lần; chính đường đi có hai handler.

Cách xử lý thường gặp là gỡ root handlers trước khi cài bridge:

~~~java
SLF4JBridgeHandler.removeHandlersForRootLogger();
SLF4JBridgeHandler.install();
~~~

Nhưng cần cân nhắc:

- Các handler **gắn trên logger con** vẫn có thể hoạt động; `removeHandlersForRootLogger()` không phải thao tác dọn toàn bộ cây JUL.
- Một container/framework có thể cần root handler riêng; gỡ nó tùy tiện có thể làm mất log mà framework đang quản lý.
- Logback cũng có thể gây trùng vì cùng appender được gắn ở logger con và root với additivity mặc định. Nếu đã hết handler JUL trùng mà output vẫn lặp, kiểm tra tiếp backend.
- Cài bridge lặp ở nhiều điểm startup có thể tạo thêm bridge handlers. Đảm bảo lifecycle do **một chủ thể** điều phối.

Muốn xác nhận, phát một JUL WARNING với ID thử nghiệm, kiểm tra nó xuất **đúng số lần** ở mỗi đích và không còn bản ghi từ đường JUL cũ nếu kiến trúc yêu cầu gom hoàn toàn.

## 12. Những gì JUL bridge không tự làm được

| Kỳ vọng nhầm | Thực tế |
| --- | --- |
| Thêm JAR `jul-to-slf4j` là tất cả JUL log lập tức vào Logback | Thường cần **cài bridge handler** và xử lý handler JUL hiện hữu |
| Bridge tự cung cấp backend | Vẫn cần **SLF4J provider** tương thích |
| Root Logback DEBUG luôn làm JUL FINE xuất | JUL FINE có thể đã bị JUL level chặn trước bridge |
| JUL `{0}` và SLF4J `{}` luôn format hệt nhau | Hai API có cơ chế template khác nhau; kiểm tra behavior bridge/backend cụ thể |
| Mỗi LogRecord sẽ thành structured JSON đầy đủ | Tùy encoder/backend, context và cách chuyển metadata |
| Bridge tự thêm traceId | Cần hệ thống context/tracing phù hợp |
| `System.out.println` cũng đi qua bridge | Không: stdout trực tiếp không phải JUL LogRecord |
| Các JUL event trước lúc install được chuyển lại | Không: bridge không replay lịch sử |
| Một warning của backend là lỗi ở JUL | Cần xác định nó đến từ JUL source, SLF4J provider, appender hay collector |
| Bridge đảm bảo log đã lưu bền vững | Không: vẫn phụ thuộc appender, hàng đợi, file/network và pipeline |

Một điểm quan trọng khi debug: **logger name được bridge giữ** không có nghĩa runtime tự biết requestId. Nếu thư viện cũ không có correlation ID, hãy đối chiếu qua ngữ cảnh bên ngoài hoặc phần mã do ứng dụng kiểm soát; không tạo logger name động để thay ID.

## 13. Chẩn đoán khi JUL bridge không hoạt động

Tiến hành theo thứ tự thay vì thêm ngẫu nhiên dependencies:

1. **Xác định nguồn:** lời gọi thực sự là `java.util.logging.Logger` hay API khác? Xem import và logger name.
2. **Xác định đích:** ứng dụng muốn JUL → SLF4J → Logback/Log4j 2 hay một tuyến khác?
3. **Kiểm tra runtime dependencies:** phải có `jul-to-slf4j`, `slf4j-api`, đúng **một provider phù hợp**, và backend đi kèm.
4. **Xác minh bridge được cài:** dùng `SLF4JBridgeHandler.isInstalled()`; thêm JAR không đồng nghĩa `install()` đã được gọi.
5. **Kiểm tra JUL level và filter:** `Logger.isLoggable(Level.FINE)` có cho phép record cần quan sát không?
6. **Kiểm tra parent handlers:** record có tới root bridge không? Nếu logger con `setUseParentHandlers(false)` và không có bridge handler ở nhánh đó, record có thể không đi vào bridge.
7. **Kiểm tra Logback/Log4j 2 level và appender:** logger phía backend có chấp nhận INFO/DEBUG tương ứng không? Có filter/threshold chặn không?
8. **Kiểm tra log trùng:** root JUL handlers, logger con JUL handlers, bridge lặp và backend additivity.
9. **Kiểm tra vòng lặp:** có `slf4j-jdk14` hoặc bridge ngược chiều đang được cài không?
10. **Kiểm tra output thực:** log có nằm ở stderr/stdout, file, container log hay collector khác nơi mong đợi không?

### Lệnh Maven và Gradle để xem dependency

~~~bash
mvn dependency:tree
~~~

Nếu dự án dùng Gradle Wrapper:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jul-to-slf4j --configuration runtimeClasspath
./gradlew dependencyInsight --dependency slf4j-api --configuration runtimeClasspath
~~~

Chú ý **runtime classpath** của artifact được triển khai. Một dependency có trong test classpath không bảo đảm nó nằm trong JAR/container đang chạy.

Nếu SLF4J 2.x cảnh báo thiếu hoặc nhiều provider, sửa cấu hình provider trước. **JUL bridge không thay thế việc xử lý lỗi SLF4J provider.**

### Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng sửa |
| --- | --- | --- |
| JUL vẫn xuất định dạng cũ | Bridge chưa install hoặc root JUL handler cũ vẫn còn | Cài bridge đúng startup; kiểm tra handlers |
| JUL INFO xuất hai lần | Cả JUL ConsoleHandler và SLF4JBridgeHandler cùng nhận record | Quản lý root/con handlers và backend appenders |
| JUL FINE im lặng, SLF4J DEBUG vẫn xuất | JUL logger đang ở INFO | Đặt level JUL đủ thấp hoặc dùng LevelChangePropagator phù hợp |
| JUL FINE tới bridge nhưng không in | Backend đang ở INFO hoặc appender filter chặn | Kiểm tra effective backend level và appender |
| Cài bridge nhưng mất toàn bộ log | SLF4J không có provider, provider NOP hoặc backend sai | Xác minh ILoggerFactory và runtime dependencies |
| Log bị đệ quy hoặc stack overflow | JUL → SLF4J và SLF4J → JUL cùng hoạt động | Loại một chiều bridge/provider ngược |
| JUL của thư viện không đi vào bridge | Logger con tắt parent handlers hoặc gắn handler riêng | Xem hierarchy và đường đi của `LogRecord` |
| Log startup đầu tiên không qua bridge | Bridge được cài sau khi thư viện phát log | Tích hợp ở giai đoạn bootstrap sớm |
| Log đúng trong IDE nhưng sai trong container | Runtime dependencies, config, output đích khác | Xem classpath và log của tiến trình triển khai |
| Chương trình chậm dù backend không xuất DEBUG | JUL đã tạo record rồi mới bị backend loại | Đồng bộ/nghiên cứu JUL level, hạn chế log không cần thiết |
| Maven có bridge, nhưng không compile được import | Bridge chỉ nằm ở runtime scope | Đặt bridge trên compile classpath khi code trực tiếp import nó |

## 14. Khi nào không nên bật JUL bridge?

JUL bridge không phải luôn là lựa chọn bắt buộc:

- Ứng dụng chỉ dùng JUL, không có SLF4J backend, và JUL ConsoleHandler/FileHandler đáp ứng đủ nhu cầu.
- Framework hoặc application server đang quản lý JUL handlers một cách có chủ ý; thay root handlers có thể ảnh hưởng các ứng dụng/thành phần cùng JVM.
- Ứng dụng dùng `slf4j-jdk14` để đưa SLF4J về JUL làm backend; lắp chiều ngược lại là nguy hiểm.
- Phần lớn log chi tiết JUL không cần được chuyển, nhưng chi phí chuyển tiếp quá lớn; có thể chọn cấu hình JUL riêng hoặc đồng bộ level có kiểm soát.
- Nhu cầu giữ log nguồn theo đường riêng vì ràng buộc vận hành, bảo mật hoặc chính sách lưu trữ đã được thiết kế cụ thể.

Hãy xác định **backend cuối cùng muốn dùng**, vẽ đường đi của từng logging API, rồi mới chọn bridge.

## 15. Bài tập áp dụng

Giả sử một thư viện phát:

~~~java
// Đoạn minh họa trong class có JUL logger.
julLogger.fine("event=remote_call_retry attempt=2");
julLogger.warning("event=remote_call_slow durationMs=900");
~~~

Ứng dụng đã chọn Logback làm backend, root level INFO, còn `com.vendor` trong Logback có DEBUG. JUL logger của thư viện kế thừa mức INFO.

**Câu hỏi:**

1. Nếu đã `install()` bridge đúng cách, sự kiện `fine` có hiển thị DEBUG không? Vì sao?
2. JUL WARNING sẽ được map thành mức gì trong SLF4J?
3. Nếu JUL logger được đặt FINE nhưng Logback logger tương ứng vẫn INFO, sự kiện FINE có xuất không?
4. Nếu gắn đồng thời JUL ConsoleHandler cũ và bridge handler vào root, có rủi ro gì?
5. Nếu provider SLF4J là `slf4j-jdk14`, thêm `jul-to-slf4j` có nguy hiểm không?
6. `LevelChangePropagator` có thay thế `SLF4JBridgeHandler.install()` không?

**Đáp án:**

1. **Không.** JUL đã loại FINE ở mức INFO trước khi bridge nhận `LogRecord`.
2. **WARN**, nếu JUL record đi tới bridge và backend chấp nhận.
3. **Không xuất qua appender mặc định theo ngưỡng INFO**: bridge chuyển FINE thành DEBUG nhưng Logback lọc DEBUG.
4. Có thể **in trùng**, một lần theo handler JUL cũ, một lần qua backend SLF4J.
5. **Có**, vì tạo tuyến JUL → SLF4J → JUL có thể đệ quy.
6. **Không.** LevelChangePropagator hỗ trợ level; `SLF4JBridgeHandler` mới chuyển record.

## 16. Checklist tích hợp an toàn

- [ ] Vẽ tuyến có một chiều rõ ràng: **JUL → SLF4J → backend cuối**.
- [ ] Chọn **một SLF4J provider** tương thích với API.
- [ ] Thêm `jul-to-slf4j` vào đúng classpath; mã import `SLF4JBridgeHandler` phải compile được.
- [ ] Lắp bridge một lần, đủ sớm; tránh trùng với cấu hình framework.
- [ ] Chỉ gỡ root JUL handlers khi thực sự sở hữu cấu hình và đã đánh giá tác động.
- [ ] Kiểm tra level/filter của **cả JUL và backend**.
- [ ] Xác nhận FINE/DEBUG, WARNING/WARN và một thông báo INFO tới đúng đích.
- [ ] Kiểm tra không có vòng `slf4j-jdk14` → JUL → SLF4J.
- [ ] Thử một record có ID giả lập để phát hiện log trùng.
- [ ] Đánh giá overhead khi JUL tạo nhiều bản ghi chi tiết; quản lý level có kiểm soát.
- [ ] Kiểm tra bảo mật dữ liệu log, exception và quyền truy cập log ở backend.
- [ ] Sau khi chỉnh sửa, xác minh runtime artifact/container thay vì chỉ xem file build.

**Ghi nhớ:** JUL bridge giải quyết việc **chuyển sự kiện từ JUL vào SLF4J**, không thay thế provider/backend. Muốn log xuất đúng, phải có **JUL level đủ cho record đi qua**, **bridge handler được cài**, **SLF4J provider tương thích** và **backend appender cho phép ghi**. Đặc biệt tránh **vòng JUL ↔ SLF4J** và xử lý các JUL handlers cũ có thể gây log trùng.