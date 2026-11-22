# Bridge giữa API logging trong Java

## 1. Bridge giữa API là gì?

Một ứng dụng Java thường phụ thuộc vào nhiều thư viện được phát triển độc lập. Thư viện thứ nhất gọi **Java Util Logging (JUL)**, thư viện thứ hai dùng **SLF4J**, thư viện thứ ba phát sự kiện qua **Log4j2 API**. Mỗi thư viện có thể dùng tên level, đối tượng logger và cơ chế truyền exception khác nhau. Nếu không có cấu hình phù hợp, log có thể được ghi ra các nơi khác nhau, có định dạng không nhất quán hoặc thậm chí bị mất.

**Logging bridge** là một lớp **chuyển tiếp** các sự kiện phát qua một API logging nguồn sang API hoặc pipeline logging đích. Bridge giúp hợp nhất các sự kiện của thư viện cũ và mới, để ứng dụng có thể lựa chọn một backend quản lý level, định dạng, đích ghi và chính sách lưu trữ.

Ví dụ:

```text
Mã ứng dụng  ─────── SLF4J API ──────────────┐
Thư viện cũ ── JUL API ── jul-to-slf4j ──────┼──> SLF4J provider ──> Logback ──> Console/File
Thư viện C  ── Log4j2 API ── log4j-to-slf4j ─┘
```

Đây là **một phương án kiến trúc** khi chọn Logback làm backend. Không phải ứng dụng nào cũng cần đủ các cầu nối này; chỉ thêm bridge cho những API nguồn thực sự được dùng, đồng thời giữ **một hướng chuyển tiếp rõ ràng**.

Một bridge **không phải** công cụ tạo distributed trace. Nó chuyển log records giữa các API, không tự sinh span, trace ID, thời lượng request hoặc tracing context.

### Mục tiêu bài học

Sau bài này, bạn có thể:

- Phân biệt **facade**, **API nguồn**, **bridge**, **provider/adapter** và **backend**.
- Đọc đúng hướng chuyển tiếp của các artifact thông dụng: `jul-to-slf4j`, `slf4j-jdk14`, `log4j-to-slf4j`, `log4j-slf4j2-impl`, `jcl-over-slf4j`.
- Xây một ứng dụng Java 17+ nhận log từ JUL và SLF4J, cùng xuất qua Logback.
- Tránh **vòng lặp bridge**, cảnh báo nhiều provider, mất stack trace và log trùng.
- Biết cách quyết định khi nào cần bridge và kiểm tra pipeline thực tế.

## 2. Phân biệt facade, bridge, provider và backend

Bốn khái niệm dễ bị gọi nhầm là “thư viện logging”:

| Khái niệm | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| **Logging API** | Mã nguồn gọi các phương thức nào để tạo sự kiện? | `java.util.logging.Logger`, `org.apache.logging.log4j.Logger` |
| **Facade** | Có API chung nào để mã nguồn ít phụ thuộc backend? | `org.slf4j.Logger` thuộc `slf4j-api` |
| **Bridge** | Làm sao sự kiện từ API A đi sang API B? | `jul-to-slf4j`: JUL → SLF4J; `log4j-to-slf4j`: Log4j2 API → SLF4J |
| **Provider / adapter backend** | Lời gọi của facade được thực thi bởi hệ thống logging nào? | `logback-classic`, `slf4j-simple`, `log4j-slf4j2-impl` |
| **Backend** | Ai áp level, filter, formatter, appender và xuất dữ liệu? | Logback, Log4j2 Core, JUL |

**Facade** đứng ở **phía gọi API**: mã của bạn chỉ biết `LOG.info(...)`. **Bridge** đứng trên một **đường chuyển từ API nguồn** sang API đích. **Provider** cung cấp implementation cho facade. **Backend** xử lý record thành output thực tế.

Một provider cũng có thể là adapter về backend khác: chẳng hạn `slf4j-jdk14` nhận lời gọi SLF4J rồi chuyển sang JUL. Ở trường hợp này, nó đóng vai trò provider cho SLF4J nhưng cũng tạo một hướng chuyển tiếp.

Điều quan trọng nhất là trả lời được **“sự kiện xuất phát từ API nào và đi về backend nào?”**. Tên của artifact thường gợi ý, nhưng cần đọc đủ chiều và vai trò trước khi ghép dependencies.

## 3. Bản đồ hướng chuyển tiếp của những bridge phổ biến

| Artifact / cơ chế | Hướng sự kiện | Khi nào dùng? |
| --- | --- | --- |
| `jul-to-slf4j` | **JUL API → SLF4J API** | Thư viện phát JUL, ứng dụng chọn Logback hoặc backend thông qua SLF4J |
| `slf4j-jdk14` | **SLF4J API → JUL backend** | Ứng dụng dùng SLF4J nhưng muốn JUL làm nơi thực thi |
| `log4j-to-slf4j` | **Log4j2 API → SLF4J API** | Thư viện dùng Log4j2 API, ứng dụng chọn backend SLF4J khác |
| `log4j-slf4j2-impl` | **SLF4J API 2.x → Log4j2 Core** | Chọn Log4j2 làm backend cho mã dùng SLF4J 2.x |
| `log4j-slf4j-impl` | **SLF4J API 1.7.x → Log4j2** | Adapter đời cũ; không nhầm với provider dành cho SLF4J 2.x |
| `jcl-over-slf4j` | **Apache Commons Logging API → SLF4J API** | Thư viện cũ gọi JCL và ứng dụng cần hợp nhất sang SLF4J |
| `log4j-over-slf4j` | **API Log4j 1.x → SLF4J API** | Thư viện cũ dùng API Log4j 1.x; cần đánh giá tương thích |
| `slf4j-reload4j` | **SLF4J API → reload4j backend** | Hệ thống chủ đích sử dụng backend tương thích thế hệ Log4j 1.x |

**Không cấu hình cả hai chiều của cùng một cặp API**. Ví dụ:

```text
SAI: JUL ── jul-to-slf4j ──> SLF4J
       ^                        |
       |                        |
       └───── slf4j-jdk14 ─────┘

SAI: Log4j2 API ── log4j-to-slf4j ──> SLF4J
          ^                            |
          |                            |
          └──── log4j-slf4j2-impl ─────┘
```

Tùy bridge và phiên bản, vòng lặp có thể bị phát hiện để báo lỗi, hoặc dẫn đến gọi đệ quy, tràn stack, log trùng hoặc mất log. Không nên xem hành vi của một bản thử nghiệm như bảo đảm an toàn chung cho các phiên bản khác.

### Ví dụ chọn backend

**Chọn Logback làm backend:**

```text
JUL API ───────── jul-to-slf4j ─────┐
Log4j2 API ────── log4j-to-slf4j ───┼─> SLF4J API ─> Logback
Mã mới ─────────────────────────────┘
```

**Chọn Log4j2 Core làm backend:**

```text
SLF4J API ─── log4j-slf4j2-impl ───┐
Log4j2 API ────────────────────────┼─> Log4j2 Core
JUL API ─── (adapter thích hợp) ────┘
```

Với JUL trong phương án thứ hai, cần **chọn và cấu hình giải pháp JUL→Log4j2 cụ thể** phù hợp với phiên bản (chẳng hạn mô-đun tích hợp JUL của Log4j2), không suy ra chỉ từ hình minh họa rằng JUL tự động chuyển sang Core. Bridge còn có thể yêu cầu JVM property hoặc thiết lập lúc khởi động.

**Chọn JUL làm backend:**

```text
Mã SLF4J API ── slf4j-jdk14 ──> JUL Logger/Handler
Mã JUL API ───────────────────> JUL Logger/Handler
```

Trong phương án này không thêm `jul-to-slf4j` theo hướng ngược.

## 4. Đặc biệt với SLF4J 2.x: provider khác binding đời cũ

SLF4J có hai thế hệ tích hợp mà người học dễ nhầm:

- SLF4J **1.7.x** dùng mô hình binding truyền thống, liên quan đến class `org.slf4j.impl.StaticLoggerBinder`.
- SLF4J **2.x** khám phá implementation qua Java `ServiceLoader` và giao diện `org.slf4j.spi.SLF4JServiceProvider`.

Vì vậy:

- `log4j-slf4j2-impl` là provider theo hướng SLF4J 2.x → Log4j2.
- `log4j-slf4j-impl` dành cho mô hình binding của SLF4J 1.7.x, **không thay thế** provider 2.x chỉ vì tên khá giống nhau.
- `logback-classic` ở thế hệ tương thích sẽ cung cấp provider cho SLF4J 2.x.
- `slf4j-simple` cũng có thể làm provider; nếu thêm đồng thời với Logback thường gây cảnh báo **multiple providers**.

Không có provider SLF4J 2.x hợp lệ, ứng dụng có thể cảnh báo dạng `No SLF4J providers were found` rồi chuyển sang NOP, nghĩa là các lời gọi qua facade không được ghi ra đích như kỳ vọng. Đây **khác** với việc bridge chưa được cài: có provider nhưng thiếu bridge thì log của API nguồn vẫn có thể xuất theo hệ riêng.

**Nguyên tắc dependency:** xác định phiên bản chính của SLF4J API, chọn đúng **một** provider runtime và chỉ bổ sung bridge **một chiều** cho từng API nguồn cần hội tụ.

## 5. Ví dụ hoàn chỉnh Java 17: gom JUL và SLF4J về Logback

Ví dụ sau minh họa sự khác biệt giữa “mã đã được viết bằng SLF4J” và “một thư viện cũ vẫn gọi JUL”. Ta giữ nguyên cả hai API trong mã nguồn nhưng dùng `jul-to-slf4j` để đưa cả hai đến **Logback**, nhờ vậy áp một cấu hình format/level chung.

Các thành phần:

- `slf4j-api`: facade mà chương trình có thể gọi.
- `jul-to-slf4j`: bridge từ JUL API sang SLF4J.
- `logback-classic`: provider SLF4J 2.x và backend Logback.
- `logback.xml`: cấu hình console appender và level của ứng dụng.

### 5.1. Cấu trúc thư mục

```text
bridge-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── BridgeDemo.java
        └── resources/
            └── logback.xml
```

### 5.2. Tệp pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>bridge-demo</artifactId>
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
            <groupId>org.slf4j</groupId>
            <artifactId>jul-to-slf4j</artifactId>
            <version>2.0.16</version>
        </dependency>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.12</version>
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
        </plugins>
    </build>
</project>
```

Các version được ghim để **minh họa một bộ dependency cụ thể**, không nhằm khẳng định là những bản mới nhất hoặc bản nên dùng trên production tại mọi thời điểm. Khi xây dựng dự án thật, cần đồng bộ theo dependency management, các bản vá và tương thích Java/SLF4J của backend.

Không thêm `slf4j-simple` hoặc `slf4j-jdk14` vào ví dụ này; Logback đã là provider đích, còn `jul-to-slf4j` chỉ làm bridge.

### 5.3. Tệp src/main/resources/logback.xml

```xml
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
            <pattern>%-5level | %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="demo" level="DEBUG"/>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

Cấu hình này cho phép mọi logger trong namespace `demo` xuất tới mức DEBUG, trong khi root mặc định dùng INFO. `STDOUT` là console appender của Logback. Prefix `%-5level` định dạng level trong trường rộng tối thiểu năm ký tự, `%msg` là message, `%n` là xuống dòng.

Không gắn thêm appender riêng vào `demo` để tránh in trùng thông qua root. Mặc dù root có mức INFO, bản ghi DEBUG từ logger `demo.*` vẫn có thể tới appender của root khi logger ở namespace `demo` cho phép và không có filter khác chặn.

### 5.4. Tệp src/main/java/demo/BridgeDemo.java

```java
package demo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.bridge.SLF4JBridgeHandler;

public final class BridgeDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(BridgeDemo.class);

    public static void main(String[] args) {
        // Chương trình demo sở hữu cấu hình JUL của JVM này.
        // Loại root handler JUL mặc định để tránh ghi cùng record hai lần.
        SLF4JBridgeHandler.removeHandlersForRootLogger();
        SLF4JBridgeHandler.install();

        LOG.info("SLF4J event");

        // Giả lập một thư viện cũ gọi thẳng JUL API.
        java.util.logging.Logger legacy =
                java.util.logging.Logger.getLogger("demo.LegacyApi");

        // JUL phải cho phép FINE trước khi bridge nhận được nó.
        legacy.setLevel(java.util.logging.Level.FINE);
        legacy.info("JUL event");
        legacy.fine("JUL detail");

        System.out.println("business-finished");
    }
}
```

### 5.5. Biên dịch và chạy

Từ thư mục `bridge-demo`, dùng JDK 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.BridgeDemo
```

**Dữ liệu stdout dự kiến do ứng dụng + appender tạo ra:**

```text
INFO  | SLF4J event
INFO  | JUL event
DEBUG | JUL detail
business-finished
```

Dòng `JUL detail` xuất ở mức DEBUG vì bridge ánh xạ mức JUL `FINE` sang mức SLF4J tương ứng trong pipeline. Dấu cách sau INFO do pattern `%-5level |`: level INFO có bốn chữ, được đệm thêm một khoảng trắng trước dấu cách cố định.

Maven/plugin hoặc thư viện khác có thể in thêm thông báo ngoài những dòng trên. Ví dụ này cố ý dùng output chỉ chứa message và level để dễ kiểm tra; trong production nên thêm timestamp, logger name, thread và context an toàn.

### 5.6. Vì sao ví dụ cần cả hai mức lọc?

Lời gọi `legacy.fine("JUL detail")` **đầu tiên** được JUL kiểm tra theo level hiệu lực của logger JUL. Nếu logger JUL vẫn ở INFO, record FINE đã bị lọc và bridge **không thể khôi phục** nó. Bởi vậy ví dụ đặt `legacy.setLevel(Level.FINE)`.

Sau khi bridge chuyển một record JUL sang SLF4J, provider/backend đích vẫn có bộ lọc riêng. Nếu Logback chỉ nhận INFO, record được ánh xạ sang DEBUG sẽ không xuất, dù JUL đã cho phép FINE. Ví dụ cấu hình logger `demo` ở DEBUG để sự kiện này xuất hiện.

Ta có thể tóm tắt:

```text
legacy.fine(...)
  │
  ├─ Level/filter của JUL logger: cho FINE không?
  │           │ Có
  │           ▼
  └── SLF4JBridgeHandler (đã cài trên JUL root)
              │ ánh xạ level / chuyển event
              ▼
         SLF4J API
              │
              ▼
       Logback Logger: DEBUG được bật?
              │ Có
              ▼
       STDOUT ConsoleAppender
```

Để chạy demo, `SLF4JBridgeHandler.removeHandlersForRootLogger()` chủ động tháo những handler đang gắn ở JUL root. **Đây là thao tác tác động toàn JVM**, phù hợp trong chương trình học độc lập trước khi ứng dụng bắt đầu xử lý công việc; không gọi tùy tiện trong một ứng dụng đã chạy hoặc một container dùng chung logging. `SLF4JBridgeHandler.install()` cũng nên được thực hiện một lần trong giai đoạn khởi tạo. Trong server có lifecycle phức tạp, cần cơ chế bootstrap/shutdown phù hợp, tránh cài bridge lặp lại.

## 6. Các mức log được ánh xạ thế nào?

Mỗi API có bộ level riêng, nên khi qua bridge cần ánh xạ mức tương đương để backend có thể lọc và format.

Với `jul-to-slf4j`, cách hiểu khái quát thường gặp:

| JUL source | Mức SLF4J thường ánh xạ | Lưu ý |
| --- | --- | --- |
| `SEVERE` | `ERROR` | Sự kiện lỗi nghiêm trọng |
| `WARNING` | `WARN` | Sự kiện bất thường |
| `INFO` | `INFO` | Thông tin vận hành |
| `CONFIG` | `DEBUG` | Chi tiết cấu hình |
| `FINE` | `DEBUG` | Chẩn đoán |
| `FINER` | `TRACE` | Chi tiết hơn |
| `FINEST` | `TRACE` | Chi tiết sâu nhất |

Bảng thể hiện **hành vi ánh xạ thông thường của bridge được nêu**, không phải một chuẩn chung buộc mọi bridge chuyển tất cả level theo cách y hệt. Các `Level` tùy biến có thể được ánh xạ dựa trên giá trị số hay chính sách riêng; cần kiểm tra adapter đang dùng nếu ứng dụng có custom levels.

Bridge không thể bảo đảm giữ nguyên mọi trường dữ liệu của từng API. Một số điểm cần quan sát:

- Tên logger, message, tham số định dạng và exception có thể được chuyển đổi.
- Timestamp hoặc source location (class/method/file/line) có thể khác do bridge tạo một event ở tầng khác.
- Filter/marker và các thuộc tính riêng của backend không phải lúc nào cũng có đối ứng.
- Thread context/MDC không tự nhiên xuất hiện từ mọi JUL log chỉ vì đã cài bridge.
- Formatter/encoder backend vẫn quyết định cuối cùng stack trace và metadata có được ghi ra hay không.

Đừng đánh giá thành công chỉ bằng việc “có một dòng log”: hãy kiểm thử **level, Throwable, logger name, context và nơi nhận**.

## 7. Bridge có thể được cài theo những cách khác nhau

**Không có API cài đặt bridge duy nhất cho mọi framework.** Mỗi hệ sinh thái có cách tích hợp riêng.

### 7.1. JUL → SLF4J

Mô-đun `jul-to-slf4j` cung cấp `SLF4JBridgeHandler` có thể được cài vào root logger JUL. Đây là hướng mà ví dụ Java 17 dùng. Cần hiểu cơ chế handler của JUL: một logger con có thể truyền record lên handler cha/root. Nếu `setUseParentHandlers(false)` ở logger con và không gắn bridge handler trực tiếp, record có thể không tới bridge.

Bridge handler chạy sau khi JUL logger cho phép event. Do đó, nếu muốn backend đích quyết định mức chi tiết, phải đặt level JUL nguồn đủ thấp để log cần thiết đi qua, nhưng **mở rộng JUL quá mức có thể tạo overhead** ngay cả khi backend SLF4J đang chặn phần lớn sự kiện. Cân nhắc công cụ đồng bộ level (nếu backend hỗ trợ) hoặc cấu hình các logger có chủ đích.

### 7.2. SLF4J → Log4j2

Khi ứng dụng dùng `org.slf4j.Logger` nhưng chọn Log4j2 Core, sử dụng provider phù hợp SLF4J 2.x như `log4j-slf4j2-impl` và các dependency Log4j2 liên quan. Trong mã nghiệp vụ vẫn viết `LoggerFactory.getLogger(...)`; cấu hình appender/layout/level ở Log4j2. **Đây là provider**, không phải `log4j-to-slf4j`.

### 7.3. Log4j2 API → SLF4J

Khi thư viện gọi `org.apache.logging.log4j.LogManager.getLogger(...)` nhưng backend ứng dụng là Logback, có thể dùng `log4j-to-slf4j`. Adapter này chuyển sự kiện **từ API Log4j2** sang facade SLF4J. Không dùng đồng thời với provider SLF4J→Log4j2 ở mục trước.

### 7.4. Commons Logging (JCL) → SLF4J

Một số thư viện cũ sử dụng `org.apache.commons.logging.Log`. `jcl-over-slf4j` cung cấp API tương thích JCL và chuyển sự kiện sang SLF4J. Cần kiểm tra phụ thuộc runtime để tránh cùng lúc giữ nhiều JAR cung cấp các class `org.apache.commons.logging.*`. Một số môi trường Spring có **spring-jcl** thay thế/tích hợp riêng; không nên thêm `jcl-over-slf4j` chỉ vì thấy tên JCL mà chưa hiểu cấu hình hiện tại.

### 7.5. Log4j 1.x API → SLF4J

`log4j-over-slf4j` cung cấp một phần API tương thích Log4j 1.x để chuyển sự kiện vào SLF4J. Tuy nhiên, không giả định mọi API và hành vi đặc thù của Log4j 1.x đều được bridge mô phỏng đầy đủ; dự án có appender custom hoặc cấu hình cũ cần migration thực tế.

Đặc biệt tránh dùng `log4j-over-slf4j` (Log4j 1.x API → SLF4J) đồng thời với provider `slf4j-reload4j` (SLF4J → backend kiểu Log4j 1.x/reload4j), vì có thể hình thành vòng lặp.

## 8. Cách chọn kiến trúc logging cho dự án

Đầu tiên hãy xác định **backend đích** phù hợp với cách vận hành, rồi mới xét các API nguồn cần chuyển tiếp.

### Trường hợp A: ứng dụng mới dùng SLF4J + Logback

```text
Application code (SLF4J API)
                    │
                    ▼
            Logback provider
                    │
                    ▼
             Console / File
```

Nếu toàn bộ dependency đã phát bằng SLF4J và không có API logging khác cần hợp nhất, **không cần thêm bridge**. Thêm bridge khi không có dữ liệu nguồn tương ứng chỉ làm tăng độ phức tạp.

### Trường hợp B: ứng dụng có thư viện JUL cũ, nhưng muốn một format chung

```text
JUL library ── jul-to-slf4j ─┐
Application ─── SLF4J ──────┼─> Logback
```

Đây chính là trường hợp của demo. Để thu đủ sự kiện JUL, cần cài bridge handler đúng thời điểm, xét ngưỡng JUL source và loại handler không mong muốn trên root để tránh log trùng.

### Trường hợp C: ứng dụng chọn Log4j2 Core làm backend

```text
SLF4J clients ── log4j-slf4j2-impl ──┐
Log4j2 API clients ──────────────────┼─> Log4j2 Core
```

Trường hợp này không thêm `log4j-to-slf4j`. Nếu có các nguồn JUL/JCL, chọn adapter riêng **cùng hướng về backend đích**, kiểm tra thêm nhu cầu context propagation và quản lý level.

### Trường hợp D: ứng dụng đã vận hành với JUL

Nếu toàn bộ code chỉ dùng JUL và JUL handler/formatter đáp ứng nhu cầu, không bắt buộc đưa SLF4J vào. Nếu có thư viện dùng SLF4J, có thể cân nhắc `slf4j-jdk14` để đưa nguồn đó về JUL. Không cần tự tạo thêm chu trình chuyển JUL ngược về SLF4J.

### Quy tắc kiến trúc ngắn gọn

**Nhiều nguồn API → bridge một chiều (khi cần) → một provider/backend → các đích xuất log được quản lý.**

Chữ “một backend” không có nghĩa chỉ được một appender: backend có thể đồng thời xuất console và file. Nó có nghĩa là không để các API tự chia thành những pipeline đối nghịch hoặc vòng lặp khó kiểm soát.

## 9. Điều gì có thể xảy ra với message, Throwable và MDC khi bridge?

### Message và placeholder

JUL thường cho phép message với tham số theo định dạng của JUL/`MessageFormat`. SLF4J dùng placeholder `{}`. Bridge có nhiệm vụ tạo sự kiện ở API đích, nhưng **không nên kỳ vọng các cú pháp placeholder của hai API có thể dùng lẫn nhau trong mã nguồn**.

Ví dụ mã JUL:

```java
java.util.logging.Logger jul =
        java.util.logging.Logger.getLogger("demo.LegacyApi");
jul.log(java.util.logging.Level.INFO, "User {0} signed in",
        new Object[]{"alice"});
```

Đây là **đoạn minh họa**. `{0}` là cú pháp tham số thông dụng của JUL, còn `{}` là cú pháp placeholder SLF4J. Lớp bridge phải xử lý/đưa tham số nguồn đi phù hợp; nếu thấy literal `{0}` hoặc biến bị lệch, cần kiểm tra phiên bản bridge và formatter, không chỉ đổi mọi thông điệp sang cú pháp của backend đích.

### Throwable và stack trace

Khi cần ghi exception trong JUL:

```java
try {
    Integer.parseInt("bad");
} catch (NumberFormatException exception) {
    jul.log(java.util.logging.Level.SEVERE,
            "Invalid numeric configuration", exception);
}
```

Đây là snippet có biến `jul` đã khai báo. Nếu bridge và backend giữ tham chiếu `Throwable`, formatter Logback hoặc Log4j2 có thể hiển thị stack trace; nhưng cuối cùng vẫn phải kiểm chứng **tại đích log thật**. Tránh chỉ gọi `exception.getMessage()` nếu muốn cả stack frames và cause chain.

### Correlation ID và MDC

SLF4J hỗ trợ `MDC` và Log4j2 hỗ trợ `ThreadContext`. JUL mặc định không có cùng API MDC. Cài `jul-to-slf4j` không tự động tạo `requestId`/`traceId` cho từng JUL record. Khi cần tương quan nhiều request, context nên được đặt/khôi phục đúng cho thread hoặc task và encoder phải xuất nó.

Trong thread pool, context của luồng gọi không nhất thiết được truyền sang thread thực thi tác vụ. Không nên lưu request ID trong biến static global để chia sẻ giữa nhiều request đồng thời. Ghi vừa đủ ngữ cảnh an toàn; không ghi token, mật khẩu, cookie hay dữ liệu cá nhân nhạy cảm vào message hoặc MDC.

## 10. Hiệu năng và vòng đời của bridge

Một bridge làm thêm công việc: nhận sự kiện nguồn, có thể ánh xạ level/format, tạo sự kiện ở API đích và chuyển cho backend. Đây không phải chi phí bằng không.

Các yếu tố cần cân nhắc:

- **Lọc ở nguồn:** record bị JUL lọc trước khi tạo không thể được backend khôi phục.
- **Lọc ở đích:** record đã qua bridge vẫn có thể bị backend loại bỏ.
- **Công việc dư:** khi nguồn cho phép log cực chi tiết nhưng đích chỉ giữ WARN, chi phí tạo và chuyển record có thể không cần thiết.
- **Địa điểm cài bridge:** cài một lần ở giai đoạn bootstrap; không cài lại trên mỗi request.
- **Handler/appender trùng:** giữ handler JUL cũ và thêm bridge có thể làm một sự kiện xuất qua cả JUL console và Logback console.
- **Classloader và shutdown:** ứng dụng chạy trong container hoặc có cơ chế hot reload cần tránh giữ handler/provider sai vòng đời.
- **Mất dữ liệu khi thoát đột ngột:** backend async, bộ đệm hoặc collector downstream có thể còn event chưa được flush.

Nếu dùng Logback, có thể xem xét công cụ hỗ trợ đồng bộ level JUL và SLF4J trong hệ sinh thái phù hợp để giảm overhead, nhưng phải cấu hình theo đúng phiên bản và triển khai. Không tự cho rằng bridge luôn tự điều chỉnh mức JUL theo Logback.

## 11. Bảo mật và an toàn dependency

Logging có thể đi qua nhiều lớp, nên việc kiểm soát dependency và output càng quan trọng:

1. **Kiểm tra phiên bản bridge và backend**: giữ phiên bản đang được hỗ trợ và đã vá lỗi bảo mật; không sao chép dependency cũ vào production mà không kiểm tra.
2. **Không mang nhiều SLF4J provider**: cảnh báo multiple providers có thể khiến cấu hình được chọn khác mong đợi.
3. **Không tạo vòng lặp**: tránh các cặp bridge hai chiều đã nêu; vòng lặp có thể gây sự cố nghiêm trọng khi log được phát.
4. **Không bỏ sót log quan trọng**: kiểm tra exception, WARN/ERROR, startup và shutdown ở đúng sink.
5. **Không nhân bản log**: nếu hai pipeline cùng đẩy sự kiện tới collector, chi phí tăng và số liệu cảnh báo có thể bị tính hai lần.
6. **Không ghi bí mật**: bridge không tự xóa password, token, secret, PII hoặc stack trace có thông điệp nhạy cảm.
7. **Không mở cơ chế thay đổi logging công khai**: việc thay level hoặc nạp cấu hình runtime phải được phân quyền.
8. **Giữ cấu hình đích rõ ràng**: format có thể mất thông tin nếu layout chỉ in message mà bỏ Throwable, logger hoặc correlation ID.

Trong hệ thống thực tế, kiểm tra artifacts **đã được đóng gói ở runtime** thay vì chỉ nhìn tệp build dự kiến; dependency gián tiếp có thể mang theo provider hoặc bridge ngoài ý muốn.

## 12. Những lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Log từ SLF4J có, nhưng JUL vẫn mang format khác | Chưa cài `jul-to-slf4j`, JUL handler mặc định vẫn ghi riêng | Kiểm tra bridge installation và handler trên JUL root |
| Log JUL không thấy sau khi cài bridge | JUL lọc tại nguồn, `useParentHandlers=false`, hoặc backend chặn | Kiểm tra logger JUL, đường handler và level backend |
| JUL `FINE` không xuất qua Logback DEBUG | JUL source còn INFO hoặc backend không bật DEBUG | Hạ ngưỡng JUL đúng logger và cấu hình backend tương ứng |
| Một sự kiện xuất hai lần | Handler JUL cũ và bridge cùng nhận; hoặc backend có appender trùng | Kiểm tra toàn pipeline và additivity |
| Thêm `slf4j-jdk14` khiến lỗi/loop | Đã có `jul-to-slf4j` chiều ngược | Chỉ giữ một hướng JUL ↔ SLF4J |
| Thêm `log4j-to-slf4j` gây lỗi vòng lặp | Đã có `log4j-slf4j2-impl` | Xóa một chiều, chọn backend đích rõ ràng |
| Cảnh báo multiple SLF4J providers | Có đồng thời Logback, Simple hoặc adapter khác | Dùng dependency tree, giữ một provider |
| Cảnh báo no providers, log biến mất | Chỉ có API/bridge, không có provider runtime hợp lệ | Thêm provider tương thích và đúng scope |
| SLF4J 2.x không nhận binding cũ | JAR `StaticLoggerBinder` từ hệ 1.7 | Chọn provider SPI tương thích SLF4J 2.x |
| JCL class conflict | Cùng đóng gói `jcl-over-slf4j` và JCL/`spring-jcl` không phù hợp | Xem dependency tree và cách framework tích hợp |
| Thiếu stack trace sau bridge | Mã chỉ log message, adapter/encoder bỏ Throwable | Truyền exception nguyên vẹn và kiểm tra layout |
| MDC/request ID không có | Context chưa được đặt hoặc chưa propagate, encoder không in | Kiểm tra MDC adapter và ranh giới thread |
| Chỉ một số log xuất sau deploy | Mỗi instance có classpath/config khác nhau | Xác nhận runtime provider và bridge trên từng instance |

### Quy trình chẩn đoán theo hướng nguồn → đích

1. **Xác định API nguồn:** `java.util.logging.Logger`, `org.slf4j.Logger`, `org.apache.logging.log4j.Logger` hoặc JCL.
2. **Vẽ mũi tên:** ghi rõ từng bridge dẫn về đâu, provider nào là đích; tìm vòng khép kín.
3. **Kiểm tra runtime dependency:** với Maven dùng `mvn dependency:tree`; xác nhận đúng phiên bản SLF4J 2.x, Logback, Log4j2 nếu có.
4. **Kiểm tra provider được chọn:** cảnh báo startup, logger factory và backend thực tế.
5. **Kiểm tra ngưỡng nguồn:** ví dụ `JUL FINE` cần được nguồn chấp nhận trước khi chuyển.
6. **Kiểm tra ngưỡng và filter đích:** backend có chấp nhận mức đã ánh xạ không?
7. **Kiểm tra handler/appender:** một record đi tới mấy sink, có duplication/additivity không?
8. **Kiểm thử exception và context:** lỗi có stack trace, các trường tương quan có đúng không?
9. **Quan sát sau khi sửa:** kiểm tra console/file/collector ở môi trường chạy thật, tránh kết luận chỉ dựa vào compile thành công.

## 13. Thực hành chuyển dần một ứng dụng cũ

Ví dụ dự án có một mô-đun lâu đời dùng JUL và các mô-đun mới dùng SLF4J:

**Trước khi hợp nhất:**

```text
LegacyService → JUL → ConsoleHandler → stderr
NewService    → SLF4J → Logback → stdout/file
```

Điều này có thể gây hai định dạng và hai chính sách level/retention.

**Sau khi hợp nhất:**

```text
LegacyService → JUL → jul-to-slf4j ─┐
NewService    → SLF4J ─────────────┴→ Logback → stdout/file
```

Quy trình chuyển đổi hợp lý:

1. Kiểm kê các API và backend thực tế, bao gồm dependency gián tiếp.
2. Chọn Logback hoặc backend khác làm **đích duy nhất**.
3. Giữ một SLF4J provider tương thích.
4. Cài bridge JUL → SLF4J một lần ở bootstrap, quản lý các handler JUL để tránh in trùng.
5. Xác minh level ở cả JUL và Logback; kiểm tra log của package legacy.
6. So sánh output INFO/WARN/ERROR, exception và các trường context với yêu cầu giám sát.
7. Giám sát hiệu năng, số lượng log, số lượng cảnh báo trước và sau.
8. Loại những dependency hoặc handler cũ không còn cần thiết, nhưng không gỡ các API mà thư viện còn sử dụng ở compile/runtime.

Bridge là công cụ **chuyển đổi dần**, không bắt buộc là giải pháp vĩnh viễn. Khi có thể cập nhật mã thư viện một cách an toàn sang API chung, hệ thống có thể đơn giản hóa thêm. Ngược lại, nếu thư viện bên thứ ba vẫn dùng JUL, bridge một chiều có thể là giải pháp thực tế lâu dài.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** `jul-to-slf4j` chuyển dữ liệu theo chiều nào?  
**Đáp án:** Từ sự kiện phát qua JUL API sang SLF4J API. Cần provider SLF4J tương thích để log tới backend.

**Câu 2.** `slf4j-jdk14` làm gì?  
**Đáp án:** Cung cấp implementation cho SLF4J API bằng backend JUL; ngược hướng với `jul-to-slf4j`.

**Câu 3.** Vì sao không nên kết hợp `log4j-to-slf4j` và `log4j-slf4j2-impl`?  
**Đáp án:** Hai mô-đun chuyển event theo hai chiều Log4j2 API ↔ SLF4J, có thể tạo vòng lặp logging.

**Câu 4.** Có `jul-to-slf4j` nhưng logger JUL ở INFO, Logback ở DEBUG. `jul.fine(...)` có xuất không?  
**Đáp án:** Không. JUL đã lọc FINE trước khi bridge nhận được event.

**Câu 5.** Một ứng dụng dùng Logback làm provider, có cần thêm `slf4j-simple` không?  
**Đáp án:** Không. Hai provider thường gây cảnh báo hoặc khiến việc chọn implementation không chắc chắn.

**Câu 6.** Vì sao log JUL xuất hai lần sau khi cài bridge?  
**Đáp án:** Có thể root JUL vẫn giữ console handler gốc trong khi bridge cũng chuyển event sang backend có console appender; cần kiểm tra cả hai nơi nhận.

**Câu 7.** Bridge có tự tạo request ID hoặc distributed trace không?  
**Đáp án:** Không. Bridge chủ yếu chuyển event giữa API. Correlation ID, context propagation và tracing cần được tích hợp riêng.

**Câu 8.** Thư viện sử dụng `org.apache.commons.logging.Log` có thể được hợp nhất với SLF4J thế nào?  
**Đáp án:** Có thể dùng giải pháp như `jcl-over-slf4j` khi tương thích, đồng thời kiểm soát JCL/`spring-jcl` trong runtime để tránh trùng class.

**Ghi nhớ:** **Bridge giữa API là một đường chuyển log có hướng**. Hãy quyết định backend đích, chọn một provider, thêm bridge một chiều cho API nguồn thật sự cần thiết, kiểm tra level ở cả hai đầu và tránh cấu hình vòng lặp. Điều này giúp hệ thống Java có log nhất quán, dễ chẩn đoán mà không buộc mọi thư viện cũ phải đổi API ngay lập tức.
