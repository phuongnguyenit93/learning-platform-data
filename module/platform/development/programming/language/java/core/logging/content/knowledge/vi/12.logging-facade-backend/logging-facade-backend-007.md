# JCL bridge trong Java Logging: từ Apache Commons Logging đến SLF4J và Log4j 2

**JCL bridge** là cơ chế chuyển các lời gọi ghi log viết theo **Apache Commons Logging (JCL)** sang một API hoặc backend logging mà ứng dụng đã chọn, thường là SLF4J/Logback hoặc Log4j 2. Nó giúp thư viện Java cũ tiếp tục dùng `org.apache.commons.logging.Log` mà toàn bộ ứng dụng vẫn tuân theo một chính sách logging thống nhất.

Nội dung này thuộc mảng **Facade và backend**. Để dùng JCL bridge đúng, cần giải đáp bốn câu hỏi: **mã nguồn gọi API gì, lớp nào thực sự cung cấp JCL, cầu nối chuyển sự kiện theo chiều nào, và backend nào ghi kết quả cuối cùng?** Sai ở một bước có thể dẫn đến mất log, trùng log, lỗi classloader hoặc vòng lặp chuyển tiếp.

## 1. Apache Commons Logging (JCL) là gì?

JCL là một abstraction logging lâu đời của Apache. Nó cung cấp interface `Log` và factory `LogFactory` trong package `org.apache.commons.logging`. Thay vì phụ thuộc trực tiếp vào Logback hay Log4j Core, thư viện gọi một API tương đối ổn định:

```java
import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;

public final class LegacyOrderClient {
    private static final Log LOG =
            LogFactory.getLog(LegacyOrderClient.class);

    public void submit(String orderId) {
        LOG.info("event=order_submit orderId=" + orderId);
    }
}
```

Đây là **một lớp minh họa**, không có `main`, và cần một thư viện cung cấp API JCL để biên dịch. `LogFactory.getLog(LegacyOrderClient.class)` lấy logger có category tương ứng với lớp. Các method JCL quen thuộc gồm `trace`, `debug`, `info`, `warn`, `error`, `fatal` và các overload nhận `Throwable`.

**Điểm khác SLF4J:** JCL `Log.info(Object)` không tự cung cấp bộ overload tham số `{}` giống SLF4J. Nếu mã nguồn đã viết theo JCL, việc thêm một backend SLF4J không làm biến đổi cú pháp của những lời gọi JCL. Bridge giải quyết **đường đi của sự kiện**, không thay đổi API mà source code đang biên dịch.

JCL ban đầu sử dụng các cơ chế factory/discovery và classloader để chọn implementation. Điều đó cho phép framework hoặc ứng dụng chủ đưa vào một logging implementation khác nhưng đôi khi gây khó tìm lỗi nếu nhiều JAR cùng cung cấp class `org.apache.commons.logging` hoặc các classloader nạp khác nhau.

## 2. API, bridge và backend khác nhau như thế nào?

```text
Code của thư viện
  |
  | org.apache.commons.logging.Log.info(...)
  v
JCL API / implementation được classloader chọn
  |
  | cầu nối theo một hướng
  v
SLF4J API hoặc Log4j 2 API
  |
  | provider / implementation
  v
Logback, Log4j Core, JUL...
  |
  | level/filter -> formatter/encoder -> appender/handler
  v
Console / file / collector
```

| Khái niệm | Ví dụ | Trách nhiệm |
| --- | --- | --- |
| **Facade/API** | JCL, SLF4J, Log4j 2 API | Cho mã nguồn các method để phát log |
| **JCL bridge/adapter** | `jcl-over-slf4j`, `log4j-jcl` | Đưa lời gọi JCL tới API đích |
| **SLF4J provider** | `logback-classic`, `slf4j-simple`, `log4j-slf4j2-impl` | Triển khai SLF4J API tại runtime |
| **Logging backend** | Logback, Log4j Core, JUL | Quản lý level, layout, context và đường đi log |
| **Đích ghi** | ConsoleAppender, RollingFileAppender, ConsoleHandler | Ghi event ra console/file/collector |

**Cầu nối không phải appender.** Thêm `jcl-over-slf4j` không tự tạo file log; muốn có log cần cả provider/backend được chọn đúng, level cho phép, appender/handler hoạt động và hệ thống thu thập đọc đúng đích.

Trong một ứng dụng lớn có thể có nhiều **API nguồn**, nhưng nên có một **backend đích chính** hoặc một thiết kế định tuyến có chủ đích, chứ không để các adapter ngẫu nhiên tạo thành chu trình.

## 3. Bảng các JCL bridge và chiều chuyển tiếp

| Artifact / cơ chế | Chiều và ý nghĩa | Khi nào đánh giá? |
| --- | --- | --- |
| `org.slf4j:jcl-over-slf4j` | **JCL API → SLF4J API** | Thư viện vẫn dùng JCL nhưng ứng dụng đã dùng SLF4J |
| `org.apache.logging.log4j:log4j-jcl` | **JCL → Log4j 2 API** | Một số ứng dụng dùng Commons Logging 1.2 hoặc cũ hơn và muốn Log4j 2 Core |
| `org.springframework:spring-jcl` | Implementation JCL của Spring, chọn **Log4j 2 API, SLF4J hoặc JUL** theo classpath | Hạ tầng Spring Framework/Spring Boot |
| `commons-logging:commons-logging` 1.3.x+ | JCL chính chủ có adapter tích hợp, **bao gồm Log4j API** | Không phải luôn cần bridge Log4j bổ sung |
| `org.slf4j:slf4j-jcl` | **SLF4J → JCL** (chiều ngược), thiên về tích hợp legacy | Khi môi trường bắt buộc JCL, cần xét phiên bản/binding |
 
**Không cài tất cả các artifact ở bảng.** `commons-logging`, `jcl-over-slf4j` và `spring-jcl` có thể cung cấp các lớp cùng package `org.apache.commons.logging`. Sự hiện diện của nhiều implementation cùng tên class làm kết quả phụ thuộc classloader và có thể gây cảnh báo hoặc hành vi khó hiểu. Hãy chọn **một implementation JCL có chủ đích**.

Một thay đổi cần biết: **từ Apache Commons Logging 1.3.0**, JCL chính chủ hỗ trợ Log4j API trong các adapter của mình. Vì vậy, với JCL **1.3+**, cần kiểm tra discovery/backend thực tế trước khi thêm `log4j-jcl`. Với **JCL 1.2 và cũ hơn**, `log4j-jcl` là cầu nối được tài liệu Log4j nêu cho trường hợp muốn chuyển log sang Log4j 2.

## 4. Trường hợp phổ biến: JCL → SLF4J → Logback

Giả sử thư viện cũ dùng JCL, còn ứng dụng mới chọn SLF4J làm facade và Logback làm backend:

```text
Legacy library
    |
    | org.apache.commons.logging.LogFactory.getLog(...)
    v
jcl-over-slf4j
    |
    v
SLF4J API
    |
    | Logback là provider
    v
Logback
    |
    +-- ConsoleAppender
    +-- RollingFileAppender
```

`jcl-over-slf4j` được thiết kế như **thư viện thay thế tương thích với public API của JCL**. Mã legacy vẫn có thể import `org.apache.commons.logging.Log` và `LogFactory`, nhưng implementation đưa sự kiện sang SLF4J.

Thông thường cần:

1. `jcl-over-slf4j` để nhận lời gọi JCL.
2. `slf4j-api` cho API đích.
3. **Một provider SLF4J thích hợp**, chẳng hạn `logback-classic`.
4. Cấu hình backend về level, formatter/layout và appender.

Nếu dependency của thư viện cũ kéo `commons-logging:commons-logging` vào runtime, phải kiểm tra có cần **exclude JAR đó** để tránh hai implementation cùng cung cấp `LogFactory` hay không. Không loại dependencies một cách mù quáng: trong một dự án Spring, `spring-jcl` có thể là implementation JCL mà framework đã chọn.

Nếu chỉ có `jcl-over-slf4j` và `slf4j-api` nhưng **không có provider phù hợp**, ứng dụng có thể nhận cảnh báo SLF4J và sử dụng logger no-op (NOP). Khi đó API hoạt động về mặt gọi method nhưng event không tới đích. Đừng nhầm tình huống này với lỗi Java không tìm thấy `LogFactory`.

## 5. Ví dụ chạy độc lập: Java 17 + Maven + jcl-over-slf4j

Ví dụ cho thấy **hai facade khác nhau cùng đi tới một provider**. Dự án dùng JDK 17, Maven, JCL bridge của SLF4J và `slf4j-simple` 2.x để dễ quan sát. Đây là lựa chọn học tập; ứng dụng production có thể dùng Logback hoặc một provider khác đã được tổ chức phê duyệt.

Cấu trúc:

```text
jcl-bridge-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/logging/JclBridgeDemo.java
    └── resources/simplelogger.properties
```

### 5.1. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>jcl-bridge-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <slf4j.version>2.0.17</slf4j.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-api</artifactId>
            <version>${slf4j.version}</version>
        </dependency>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>jcl-over-slf4j</artifactId>
            <version>${slf4j.version}</version>
        </dependency>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-simple</artifactId>
            <version>${slf4j.version}</version>
            <scope>runtime</scope>
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
                <configuration>
                    <mainClass>com.example.logging.JclBridgeDemo</mainClass>
                    <classpathScope>runtime</classpathScope>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**Lưu ý:** Bản XML thực sự phải có `<version>${slf4j.version}</version>` — không có dấu backslash trước ký tự `$`. Ba module SLF4J được cố định cùng version để hạn chế xung đột. Đây là **phiên bản ví dụ cụ thể**, không phải tuyên bố phiên bản mới nhất.

### 5.2. `JclBridgeDemo.java`

```java
package com.example.logging;

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class JclBridgeDemo {
    private static final Log JCL =
            LogFactory.getLog(JclBridgeDemo.class);

    private static final Logger SLF4J =
            LoggerFactory.getLogger(JclBridgeDemo.class);

    private JclBridgeDemo() {
    }

    public static void main(String[] args) {
        System.out.println("loggerName=" + SLF4J.getName());

        JCL.info("event=jcl_accepted requestId=req-17");
        SLF4J.warn("event=slf4j_retry attempt={}", 2);

        System.out.println("finished=true");
    }
}
```

**Giải thích:** `JCL` mang kiểu `org.apache.commons.logging.Log`, còn `SLF4J` là `org.slf4j.Logger`. Cả hai lấy logger theo cùng lớp, có tên category `com.example.logging.JclBridgeDemo`. Code không gọi hai API cho **cùng một event**; nó tạo hai sự kiện riêng để chứng minh cả hai tới một provider.

### 5.3. `simplelogger.properties`

Tạo `src/main/resources/simplelogger.properties`:

```properties
org.slf4j.simpleLogger.defaultLogLevel=info
org.slf4j.simpleLogger.showDateTime=false
org.slf4j.simpleLogger.showThreadName=false
org.slf4j.simpleLogger.showLogName=true
org.slf4j.simpleLogger.showShortLogName=false
org.slf4j.simpleLogger.logFile=System.err
```

Các key này dành riêng cho provider `slf4j-simple`. Nếu thay backend bằng Logback hoặc Log4j Core, phải thay cấu hình đích tương ứng; bản thân bridge không dùng file cấu hình backend này.

### 5.4. Biên dịch và chạy

Trong thư mục `jcl-bridge-demo/`:

```bash
mvn -q compile exec:java
```

**Stdout do mã ứng dụng tự in** theo đúng thứ tự:

```text
loggerName=com.example.logging.JclBridgeDemo
finished=true
```

**Hai dòng log ứng dụng được SimpleLogger xuất ra stderr** theo pattern đã cấu hình:

```text
INFO com.example.logging.JclBridgeDemo - event=jcl_accepted requestId=req-17
WARN com.example.logging.JclBridgeDemo - event=slf4j_retry attempt=2
```

Maven/plugin có thể phát thêm thông tin build ở môi trường khác. Terminal có thể hiển thị stdout và stderr cùng lúc nhưng **không bảo đảm thứ tự xen kẽ giữa hai stream**. Kết quả cần xác nhận là cả thông điệp JCL và SLF4J được ghi qua **cùng provider và cùng format**.

Để thấy vai trò của bridge, nếu loại `jcl-over-slf4j` mà không có JCL API nào khác, source Java sẽ không còn biên dịch vì thiếu `org.apache.commons.logging`. Nếu chỉ loại `slf4j-simple` và không có provider khác, SLF4J có thể cảnh báo thiếu provider; lúc ấy những lời gọi log có thể không xuất ra stderr như dự kiến.

## 6. Trường hợp JCL → Log4j 2 Core

Nếu đích cuối là Log4j Core thay vì Logback, cần quan sát phiên bản và implementation JCL.

### Trường hợp Commons Logging 1.2 hoặc cũ hơn

Apache Log4j có bridge `log4j-jcl`:

```text
commons-logging 1.2 (JCL)
            |
            | log4j-jcl
            v
       Log4j 2 API
            |
            v
       Log4j 2 Core
            |
            v
      Appender
```

Một đoạn dependency Maven cho ứng dụng đang dùng Log4j BOM:

```xml
<dependency>
    <groupId>org.apache.logging.log4j</groupId>
    <artifactId>log4j-jcl</artifactId>
    <scope>runtime</scope>
</dependency>
```

Đây chỉ là **dependency fragment**, không phải POM hoàn chỉnh. Bạn còn cần JCL phù hợp, Log4j API/Core và cấu hình appender. Nếu artifact không có version riêng, POM phải được quản lý version qua BOM hoặc parent tương thích.

### Trường hợp Commons Logging 1.3+

Apache Commons Logging **1.3.0 trở đi** đã hỗ trợ trực tiếp Log4j API trong các adapter. Một dự án với JCL phiên bản mới có thể không cần `log4j-jcl` riêng. Hãy xác định JCL factory đang chọn implementation nào và kiểm thử output thực tế.

**Không hiểu nhầm:** JCL có hỗ trợ Log4j API không đồng nghĩa với việc ứng dụng tự có Log4j Core/config. Backend cuối vẫn phải tồn tại để xử lý event, và việc chọn implementation JCL chịu ảnh hưởng classpath/classloader.

Nếu ứng dụng đã có SLF4J và Logback làm backend chính, không nên thêm Log4j Core chỉ vì một thư viện dùng JCL. Cách chuyển tiếp **JCL → SLF4J → Logback** thường rõ ràng hơn trong tình huống đó.

## 7. `spring-jcl`: Spring đã cung cấp API JCL tương thích

Spring Framework có module **`spring-jcl`** phục vụ logging của framework và những extension liên quan. Module cung cấp API trong package `org.apache.commons.logging` và có cơ chế chọn API logging hiện diện trên classpath: Log4j 2, SLF4J, hoặc fallback JUL, tùy phiên bản Spring và môi trường.

```text
Spring Framework
      |
      | org.apache.commons.logging.Log
      v
  spring-jcl
      |
      +--> Log4j 2 API --> Log4j Core
      |
      +--> SLF4J API --> Logback/provider khác
      |
      +--> JUL nếu không có API tương thích được chọn
```

Các nhánh trên là **lựa chọn**, không phải ba output đồng thời của mỗi event. Trong Spring Boot thông thường, logging starter đã chuẩn bị backend/provider cho ứng dụng. Vì vậy:

- **Không tự thêm `jcl-over-slf4j` chỉ vì code của Spring dùng Commons Logging.**
- Nếu thấy cả `spring-jcl` và `commons-logging`, xem cảnh báo classpath và quyết định ai phải cung cấp JCL.
- Với mã ứng dụng mới, Spring khuyến nghị dùng trực tiếp SLF4J, Log4j API hoặc JUL theo convention; không buộc bạn phải chọn JCL.
- Nếu thật sự thay `spring-jcl` bằng một implementation khác, làm việc đó có chủ đích, kiểm tra dependency tree và log trong ứng dụng sau thay đổi.

**Ví dụ chọn sai hướng:** thêm `commons-logging`, `spring-jcl` và `jcl-over-slf4j` đồng thời để “đủ mọi framework”. Những artifact này có thể cung cấp các lớp trùng package, dẫn đến cảnh báo hoặc provider không được dùng như người viết nghĩ. Cần giữ **một nguồn JCL hợp lệ** ở classloader tương ứng.

## 8. Đừng nhầm `jcl-over-slf4j` với `slf4j-jcl`

Hai tên rất giống nhưng có **chiều ngược nhau**:

```text
jcl-over-slf4j:
    JCL API ----------> SLF4J API ----------> backend

slf4j-jcl:
    SLF4J API --------> JCL API ------------> implementation
```

`slf4j-jcl` xuất hiện trong những kịch bản tích hợp cũ khi môi trường cần JCL làm đầu mối logging. Với các dự án SLF4J 2.x, phải xét lại hỗ trợ **provider/binding đúng phiên bản**; không giả định một binding dành cho SLF4J 1.7 hoạt động với 2.x.

**Không bao giờ ghép cả hai chiều vào cùng runtime:**

```text
JCL --> jcl-over-slf4j --> SLF4J
 ^                            |
 |                            v
 +---------- slf4j-jcl --------+
```

Khi lời gọi đi vòng liên tục, ứng dụng có thể gặp **`StackOverflowError`** hoặc logging không thể khởi tạo đúng. Tài liệu SLF4J đã cảnh báo trường hợp này. Cách sửa là **bỏ bridge chiều ngược**, không phải thêm appender, tăng level hay bắt exception vòng lặp.

Nguyên tắc tương tự áp dụng với những cặp bridge khác như SLF4J ↔ Log4j 2 hoặc JUL ↔ SLF4J: tránh tạo chu trình trong đồ thị logging.

## 9. Dùng Maven kiểm tra xung đột dependency

Trong dự án thực tế, lỗi JCL bridge thường là **lỗi runtime classpath**, không phải lỗi một dòng code `LogFactory.getLog`. Có thể xem bằng:

```bash
mvn dependency:tree
```

Tìm những artifact sau trong kết quả:

```text
commons-logging:commons-logging
org.springframework:spring-jcl
org.slf4j:jcl-over-slf4j
org.slf4j:slf4j-jcl
org.slf4j:slf4j-api
org.slf4j:slf4j-simple
ch.qos.logback:logback-classic
org.apache.logging.log4j:log4j-jcl
org.apache.logging.log4j:log4j-core
org.apache.logging.log4j:log4j-slf4j2-impl
org.apache.logging.log4j:log4j-to-slf4j
```

Đây là **danh sách kiểm tra, không phải danh sách tất cả đều phải cài**. Xem cả dependency trực tiếp và transitive (từ HTTP client, starter Spring, thư viện legacy). Với một bộ phận mã chạy trong application server hoặc classloader riêng, dependency tree Maven có thể chưa phản ánh đầy đủ classpath thực của runtime.

Nếu một dependency kéo `commons-logging` cũ không mong muốn vào dự án đang dùng `jcl-over-slf4j`, có thể loại nó bằng Maven exclusions ở dependency đã kéo vào:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>some-legacy-library</artifactId>
    <version>1.0.0</version>
    <exclusions>
        <exclusion>
            <groupId>commons-logging</groupId>
            <artifactId>commons-logging</artifactId>
        </exclusion>
    </exclusions>
</dependency>
```

Đây là **fragment minh họa**; `com.example:some-legacy-library:1.0.0` không phải dependency được xác nhận tồn tại. Hãy xác nhận classpath sau khi loại và kiểm thử vì một số thư viện/framework có yêu cầu riêng đối với JCL.

### Xác định class `LogFactory` được nạp từ đâu

Để điều tra nguồn class JCL tại runtime (với các class đã có trong chương trình), có thể in nguồn bảo vệ code:

```java
// Fragment nằm trong một chương trình đã có dependency JCL.
var source = org.apache.commons.logging.LogFactory.class
        .getProtectionDomain()
        .getCodeSource();
System.out.println("jclLocation="
        + (source == null ? "unavailable" : source.getLocation()));
```

Đoạn trên không phải chương trình độc lập. `getCodeSource()` có thể `null` trong một số môi trường; việc ghi ra đường dẫn JAR để điều tra nội bộ không nên được bật mặc định trong log production vì có thể lộ cấu trúc triển khai.

## 10. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Không biên dịch được `org.apache.commons.logging.Log` | Thiếu API JCL trong compile classpath | Thêm implementation/API JCL **duy nhất** đúng với kiến trúc |
| JCL chạy nhưng không thấy log | Bridge không đúng, không có provider SLF4J, level/filter tắt | Theo dấu từ JCL factory tới backend và appender |
| SLF4J cảnh báo thiếu provider | `jcl-over-slf4j` đưa log đến SLF4J nhưng runtime không có provider đúng | Thêm một provider tương thích với SLF4J đang dùng |
| SLF4J cảnh báo nhiều provider | Logback, SimpleLogger và các provider khác cùng cạnh tranh | Giữ provider của backend đã chọn |
| `StackOverflowError` ngay khi logging | Bridge JCL → SLF4J → JCL tạo vòng lặp | Loại một chiều bridge |
| Spring cảnh báo Commons Logging discovery | `spring-jcl` cùng tồn tại với `commons-logging` | Kiểm tra dependency tree và class source thực |
| JCL log đi đến JUL thay vì Logback | JCL/spring-jcl đã chọn hướng khác từ classpath | Kiểm tra implementation JCL và provider backend |
| Cùng một event xuất hiện hai lần | Additivity/appender trùng hoặc mã gọi log lặp | Rà đường phát event và cấu hình logger hierarchy |
| `DEBUG` không thấy | Logger hoặc backend đặt level `INFO` | Kiểm tra level hiệu lực và filter/appender |
| Không có stack trace | Không truyền `Throwable` hoặc formatter không xử lý exception | Gọi overload nhận `Throwable`, kiểm tra layout |
| Log thiếu request ID | Bridge không tạo MDC hay context truyền xuyên thread | Cấu hình MDC và propagation chủ động |
| File log không được ghi | Backend chọn sai, appender chưa gắn hoặc lỗi quyền ghi | Kiểm tra backend/appender, filesystem và collector |

Khi chẩn đoán một sự kiện không xuất hiện, hãy kiểm tra từ đầu đến cuối:

```text
JCL LogFactory có được nạp?
  |
  +--> JCL implementation nào đang được sử dụng?
         |
         +--> Chuyển sang SLF4J, Log4j hay JUL?
                |
                +--> Backend/provider đúng đã chạy?
                       |
                       +--> Level và filter cho qua?
                              |
                              +--> Appender/handler ghi đúng đích?
                                     |
                                     +--> Collector có đọc được?
```

Đừng mặc định lỗi là thiếu bridge chỉ vì `LogFactory.getLog` chạy thành công mà không thấy output. Logger có thể phát event nhưng backend filter hoặc đích ghi bị lỗi.

## 11. Ngoại lệ, level, request context và hiệu năng qua bridge

### Exception

JCL thường có overload `error(Object, Throwable)`, giúp chuyển exception vào pipeline:

```java
// Fragment: đã có org.apache.commons.logging.Log LOG
// và Throwable cause trong catch block.
LOG.error("event=payment_failed requestId=req-17", cause);
```

Bridge phù hợp có thể chuyển `Throwable` sang API/backend đích; việc ghi stack trace, `Caused by` và các frame phụ thuộc encoder/layout. Đừng chỉ ghi `cause.getMessage()` nếu cần điều tra đường đi của lỗi.

### Level

JCL có `FATAL`, SLF4J không có level tương ứng trực tiếp (chủ yếu từ `TRACE` đến `ERROR`). Vì vậy bridge có thể ánh xạ các mức không tương đương theo quy tắc riêng của implementation. Khi tìm một record, hãy kiểm tra level tại **logger API nguồn và backend đích**, thay vì kỳ vọng mọi level được giữ nguyên tên.

### Message

JCL nhận `Object` làm message; SLF4J hỗ trợ placeholder `{}` qua overload của SLF4J. Không viết `LOG.info("id={}", id)` trên một biến `org.apache.commons.logging.Log` như thể nó là SLF4J: đoạn đó không khớp API JCL thông thường.

Với phép tính tốn thời gian chỉ phục vụ log, có thể kiểm tra `LOG.isDebugEnabled()` trước khi tạo message dài. Tránh tính toán nặng hoặc gọi phương thức có side effect chỉ để tạo dữ liệu debug.

### Request ID và bảo mật

Bridge không tự tạo `requestId`, `traceId`, MDC/ThreadContext hoặc tự truyền context qua executor/async. Nếu cần những trường đó, phải cấu hình hệ quan sát và propagation. Không đưa token, password, cookie phiên hoặc dữ liệu cá nhân không cần thiết vào log; nếu dữ liệu nhập từ người dùng có ký tự CR/LF thì phải escape hoặc dùng structured encoder phù hợp.

### Chi phí

Bridge thêm lớp chuyển đổi nhưng vấn đề thường lớn hơn là format, I/O, queue và số lượng event. Tránh chuỗi adapter không cần thiết, cấu hình nhiều backend tranh nhau và log payload cực lớn. Với sản xuất, kiểm tra khả năng mất log khi queue đầy và lifecycle shutdown của backend.

## 12. Checklist chọn JCL bridge cho dự án

1. **Xác định API nguồn**: có code/thư viện đang import `org.apache.commons.logging.Log` không?
2. **Xác định implementation JCL**: `commons-logging`, `spring-jcl` hay `jcl-over-slf4j` thực sự được nạp?
3. **Chọn backend đích**: Logback, Log4j Core hay JUL; đích nào chịu trách nhiệm lưu event?
4. **Vẽ đường một chiều**: JCL → SLF4J → Logback hoặc JCL → Log4j API → Core; không có mũi tên quay lại.
5. **Đối chiếu version**: Commons Logging 1.3+ khác 1.2; SLF4J 2.x dùng provider mới, không giả định binding 1.7 vẫn phù hợp.
6. **Loại lớp trùng**: tránh `spring-jcl`, `commons-logging`, `jcl-over-slf4j` cùng cấp class không kiểm soát.
7. **Kiểm tra provider/backend**: bridge tồn tại không có nghĩa đã có console/file appender đúng.
8. **Chạy thử các API**: một event JCL và một event facade chính; có một record/event mong đợi ở đích, không trùng.
9. **Kiểm tra exception và level**: throwable và các mức `DEBUG`, `INFO`, `WARN`, `ERROR` có được xử lý đúng?
10. **Giữ an toàn và vận hành**: không lộ bí mật, có correlation ID, đúng retention, đủ quyền truy cập và định dạng cho collector.

**Ghi nhớ:** `jcl-over-slf4j` chuyển **JCL → SLF4J**; `log4j-jcl` hỗ trợ các trường hợp **JCL → Log4j 2**; `spring-jcl` là implementation phù hợp hệ Spring; `slf4j-jcl` lại đi chiều **SLF4J → JCL**. Một hệ logging ổn định cần **API rõ ràng, một implementation JCL có chủ đích, bridge đúng chiều và backend cuối được cấu hình/kiểm chứng**.

## Tài liệu chính thức

- Apache Commons Logging User Guide: https://commons.apache.org/proper/commons-logging/guide.html
- SLF4J Bridging legacy APIs: https://www.slf4j.org/legacy.html
- SLF4J diagnostic messages: https://www.slf4j.org/codes.html
- Apache Log4j 2 installation & bridge: https://logging.apache.org/log4j/2.x/manual/installation.html
- Spring Framework logging & spring-jcl: https://docs.spring.io/spring-framework/reference/core/spring-jcl.html
