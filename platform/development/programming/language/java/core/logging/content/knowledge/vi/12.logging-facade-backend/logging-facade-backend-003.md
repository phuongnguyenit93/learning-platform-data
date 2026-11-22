# Chọn implementation logging trong Java: facade, provider và backend

## 1. Vì sao phải chọn implementation?

Trong Java, lời gọi ghi log của mã ứng dụng và hệ thống thực sự xử lý log có thể là hai lớp trách nhiệm khác nhau.

Ví dụ, một lớp nghiệp vụ sử dụng SLF4J:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class OrderService {
    private static final Logger LOG =
            LoggerFactory.getLogger(OrderService.class);

    public void accept(String orderId) {
        LOG.info("event=order_accepted orderId={}", orderId);
    }
}
```

Đây là một **lớp minh họa**, chưa phải chương trình có `main`. Dòng `LOG.info(...)` không tự quyết định việc ghi ra console, file hay JSON collector. Nó gọi **SLF4J API**; một implementation/provider tương thích ở runtime sẽ xử lý sự kiện qua backend cụ thể.

Với hệ thống dùng Logback:

```text
Mã ứng dụng
    |
    | LoggerFactory.getLogger(...), log.info(...)
    v
SLF4J API (facade)
    |
    | Tìm SLF4J provider trên classpath (SLF4J 2.x)
    v
Logback provider/backend
    |
    | Logger level, filter, appender, encoder/layout
    v
Console / File / hệ thống thu thập log
```

Đây là mô hình logic: **provider** là phần kết nối SLF4J API với implementation; backend thường cung cấp logger thực tế, filter, định dạng và appender. Với Logback, artifact `logback-classic` chứa phần tích hợp SLF4J và sử dụng `logback-core`.

**Chọn implementation** nghĩa là quyết định hệ thống sẽ dùng backend nào ở runtime, tùy yêu cầu về định dạng, hiệu năng, cấu hình, tương thích framework, bảo mật và vận hành. Đây không phải việc đổi tên logger hay thay một phương thức `info` thành `debug`.

## 2. Phân biệt facade, API, provider và backend

| Thành phần | Trách nhiệm | Ví dụ |
|---|---|---|
| **Logging API** | Những phương thức mà mã nguồn gọi để ghi sự kiện | `org.slf4j.Logger`, `java.util.logging.Logger`, `org.apache.logging.log4j.Logger` |
| **Facade** | Giao diện thống nhất, hạn chế phụ thuộc trực tiếp vào backend | SLF4J API |
| **Provider/binding** | Nối facade với implementation cụ thể tại runtime | Tích hợp SLF4J trong Logback, `log4j-slf4j2-impl`, `slf4j-simple` |
| **Backend/implementation** | Lọc level, tạo sự kiện, xử lý appender, định dạng và xuất log | Logback, Log4j 2 Core, JUL, simple backend |
| **Bridge/adapter** | Chuyển lời gọi từ API logging này sang API logging khác | `jul-to-slf4j`, `log4j-to-slf4j` |
| **Collector/agent** | Nhận, vận chuyển, lưu và tìm kiếm log sau khi ứng dụng xuất | Agent đọc stdout/file hoặc pipeline tập trung |

### Ví dụ: một API, nhiều backend

Cùng đoạn mã SLF4J ở đầu bài có thể chạy với:

- Logback, dùng provider của `logback-classic`.
- Log4j 2, dùng provider `log4j-slf4j2-impl` và phần triển khai Log4j 2 thích hợp.
- `slf4j-simple`, một provider tối giản.
- `slf4j-jdk14`, provider chuyển lời gọi SLF4J tới **JUL**.
- `slf4j-nop`, implementation cố ý không ghi log.

**Không có nghĩa các backend có cùng output hoặc cùng tính năng.** SLF4J tạo ra một cách gọi thống nhất, còn layout, MDC/structured fields, file rotation, async, filters và config thuộc khả năng implementation thực tế.

Ngược lại, ứng dụng gọi trực tiếp `java.util.logging.Logger` là dùng **API JUL**, không tự động đi qua SLF4J. Muốn đưa log JUL vào backend đang dùng SLF4J cần bridge hoặc cơ chế tích hợp riêng.

## 3. SLF4J 2.x tìm implementation như thế nào?

Trong **SLF4J 2.x**, API dùng cơ chế `ServiceLoader` để tìm những `SLF4JServiceProvider` phù hợp có trên runtime classpath/module path. Khái niệm provider thay thế cơ chế binding của SLF4J 1.7 trở xuống, vốn thường được nhận diện bằng lớp `org.slf4j.impl.StaticLoggerBinder`.

### 3.1. Quy tắc quan trọng: một provider phù hợp tại runtime

Với ứng dụng thông thường, hãy để **một provider SLF4J 2.x** được chọn trong classpath. Ví dụ:

```text
ĐÚNG:
slf4j-api 2.x
   └── logback-classic (phiên bản tương thích)

CẦN XỬ LÝ:
slf4j-api 2.x
   ├── logback-classic
   └── slf4j-simple

CẦN XỬ LÝ:
slf4j-api 2.x
   └── chỉ có backend/binding dành cho SLF4J 1.7
```

Nếu có nhiều provider, SLF4J có thể cảnh báo và chọn một provider; **đừng dựa vào thứ tự classpath để coi đó là một chính sách cấu hình**. Hành vi cuối có thể bất ngờ và thay đổi sau khi cập nhật dependency hoặc cách đóng gói.

Nếu không có provider phù hợp, SLF4J 2.x có thể dùng no-operation fallback và cảnh báo, dẫn tới các lời gọi SLF4J không sinh log như mong muốn. Một binding chỉ phù hợp với SLF4J 1.7 không phải provider 2.x; nó không giải quyết vấn đề thiếu provider ở runtime.

### 3.2. Compatibility của version

Không chọn implementation chỉ dựa trên tên artifact. Cần kiểm tra đồng thời:

- Major version của `slf4j-api`: 1.7 và 2.x dùng cơ chế binding/provider khác nhau.
- Phiên bản backend tương thích với SLF4J API và JDK mục tiêu.
- Dependency transitively kéo theo `slf4j-api`, một provider khác hoặc bridge.
- Framework hoặc application server có logging stack mặc định và classloader riêng.
- Phiên bản được hỗ trợ, bản vá bảo mật và BOM/dependency management mà dự án đang dùng.

Ví dụ, `log4j-slf4j2-impl` dành cho **SLF4J 2.x**; `log4j-slf4j-impl` (không có số 2) thuộc tích hợp với thế hệ SLF4J trước đó. Không thay hai artifact chỉ vì tên trông gần giống nhau.

**Nhớ:** facade không “chọn backend bằng annotation trên logger”; provider được xác định bởi những gì có mặt và có thể được nạp **khi ứng dụng khởi tạo logging**.

## 4. Các lựa chọn backend thường gặp

| Lựa chọn | Hợp với tình huống nào | Điều cần lưu ý |
|---|---|---|
| **Logback** | Ứng dụng SLF4J phổ biến, cần pattern, rolling file, async appender, điều chỉnh logger | Cần `logback-classic` cùng các dependency phù hợp; JSON/structured logging có thể cần cấu hình hoặc encoder bổ sung |
| **Log4j 2** | Muốn dùng Log4j 2 API/Core hoặc cần các tính năng cấu hình, routing, async, layout do Log4j 2 cung cấp | Với SLF4J 2.x cần provider `log4j-slf4j2-impl` và implementation tương thích; tránh vòng bridge |
| **JUL** | Java CLI, thư viện hoặc service tối giản dependency, yêu cầu ghi console/file đơn giản | Có sẵn JDK, nhưng MDC/JSON/rolling/async phong phú không có đầy đủ trong chuẩn mặc định |
| **slf4j-simple** | Demo, ví dụ nhỏ, test hay tiện ích rất đơn giản | Đầu ra/config giản lược; không thay thế một backend production với mọi yêu cầu nâng cao |
| **slf4j-nop** | Trường hợp có chủ đích tắt toàn bộ lời gọi SLF4J | Dễ làm mất bằng chứng khi bị đóng gói nhầm vào runtime |
| **Provider SLF4J → JUL** (`slf4j-jdk14`) | Code gọi SLF4J nhưng muốn dùng handlers/config của JUL | Cần hiểu hướng chuyển tiếp; không ghép với bridge đối nghịch gây vòng lặp |

Đây là **gợi ý lựa chọn**, không phải xếp hạng tốc độ hay độ an toàn. Các tiêu chí như độ trễ, throughput, bộ nhớ, phiên bản JDK và tính năng hỗ trợ cần được kiểm chứng với version/cấu hình thực tế.

### Logback không phải SLF4J

SLF4J là API/facade; Logback là một implementation phổ biến. Nhiều dự án dùng chung chúng nên dễ gọi nhầm “SLF4J logging” như thể facade tự quyết định file rotation hoặc pattern layout. Khi lỗi xuất hiện ở lớp appender/encoder, phải kiểm tra cấu hình **Logback**, không chỉ chữ ký các hàm `Logger.info`.

### Log4j 2 API không phải Log4j 2 Core

Ứng dụng có thể gọi trực tiếp Log4j 2 API; runtime cần một provider/implementation thích hợp để xuất log. Trong mô hình thường gặp, `log4j-api` định nghĩa API và `log4j-core` thực hiện xử lý backend. Nếu mã ứng dụng gọi **SLF4J**, bridge/provider dành cho SLF4J và Log4j 2 phải được chọn đúng hướng.

### JUL không phải implementation SLF4J tự động

JUL có logger, handler, formatter và level riêng trong JDK. Nó chỉ trở thành đích của lời gọi SLF4J khi có adapter thích hợp như `slf4j-jdk14`. Ngược lại, `jul-to-slf4j` chuyển log phát bởi API JUL **sang SLF4J**, chứ không chuyển SLF4J vào JUL.

## 5. Đặt tiêu chí chọn implementation từ yêu cầu thực tế

Trước khi sửa dependency, nên trả lời một tập câu hỏi ngắn nhưng cụ thể:

1. **Nguồn sự kiện là gì?** Mã mới dùng SLF4J, JUL hay Log4j 2 API? Thư viện bên thứ ba đang dùng API nào?
2. **Backend mặc định của framework là gì?** Spring Boot, application server và các starter có thể đã chọn sẵn.
3. **Đích nhận log là gì?** Console được container thu thập, rolling file, hệ thống tìm kiếm hay collector qua agent?
4. **Định dạng nào cần dùng?** Text dễ đọc, JSON có schema, key–value fields hoặc message/trace correlation?
5. **Khối lượng log dự kiến?** Throughput, peak, latency mục tiêu, disk/CPU/RAM và khả năng chậm của downstream?
6. **Yêu cầu xử lý lỗi?** Phải có stack trace/cause chain, retry, log diagnostic, cảnh báo hoặc audit độc lập?
7. **Vận hành bằng cách nào?** Cần thay level không restart, cấu hình theo profile, mask dữ liệu và kiểm soát retention?
8. **Chính sách phụ thuộc?** JDK, supported version, security patches, licenses và dependency/BOM trong tổ chức?

### Ma trận quyết định mang tính định hướng

| Yêu cầu chính | Hướng đơn giản thường phù hợp |
|---|---|
| Ứng dụng rất nhỏ, chỉ muốn log cơ bản và không muốn dependency | Dùng JUL |
| Code đã dùng SLF4J, cần config pattern + rolling/async thông dụng | Dùng một provider, chẳng hạn Logback |
| Hệ thống đang chuẩn hóa Log4j 2, có quy chuẩn cấu hình/quan sát riêng | Dùng Log4j 2 và provider tương thích với API hiện tại |
| Ứng dụng Spring Boot mặc định đã dùng Logback, không có yêu cầu đặc biệt | Giữ backend mặc định, cấu hình nó đúng trước khi cân nhắc thay |
| Logging cần JSON/OTel/trace fields | Chọn backend/encoder tương thích pipeline và kiểm chứng schema; không chỉ dựa vào tên backend |
| Trường hợp test nhỏ không cần feature phức tạp | Cân nhắc `slf4j-simple` hoặc test appender trong phạm vi phù hợp |

**Đừng chọn Log4j 2 chỉ vì nghe “nhanh hơn”, hoặc chọn Logback chỉ vì “mọi người đều dùng”.** Tốc độ và độ bền phụ thuộc cơ chế async, appender, formatter, mức log, I/O, logger context và các chính sách cấu hình. Đo benchmark đại diện cho hệ thống thật, không suy từ marketing hoặc một microbenchmark không cùng điều kiện.

## 6. Ví dụ hoàn chỉnh: SLF4J 2.x + Logback với Java 17

Ví dụ này dùng **SLF4J làm API** và **Logback làm provider/backend**. Người học có thể chạy cùng mã Java trong hai cấu hình level mà không sửa mã nghiệp vụ.

Yêu cầu: **JDK 17+**, Maven và khả năng tải dependencies. Phiên bản được cố định để ví dụ có tính tái hiện, **không phải tuyên bố đó là bản mới nhất hoặc khuyến nghị bảo mật cho mọi dự án**.

### 6.1. Cấu trúc dự án

```text
logging-choice-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/example/logging/LoggingChoiceDemo.java
        └── resources/
            └── logback.xml
```

### 6.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>logging-choice-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
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
                <configuration>
                    <mainClass>com.example.logging.LoggingChoiceDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`logback-classic` cung cấp backend và SLF4J provider, kéo các dependency liên quan (trong đó có SLF4J API) theo quan hệ phụ thuộc tương thích. Với dự án lớn, nên dùng dependency management/BOM phù hợp để khóa phiên bản và tránh kéo nhiều provider.

### 6.3. `src/main/resources/logback.xml`

```xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>%level %logger{0} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

Pattern xuất level, tên logger rút gọn và message, mỗi event kết thúc bằng newline. Chỉ định `System.out` giúp output demo thuộc **stdout**, khác JUL `ConsoleHandler` thường ghi vào stderr.

### 6.4. `src/main/java/com/example/logging/LoggingChoiceDemo.java`

```java
package com.example.logging;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class LoggingChoiceDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(LoggingChoiceDemo.class);

    public static void main(String[] args) {
        LOG.info("event=app_started service={}", "orders-api");
        LOG.debug("event=cache_lookup key={}", "ORD-7");
        LOG.warn("event=retry_scheduled attempt={}", 1);
    }
}
```

`LoggerFactory` thuộc SLF4J, không thuộc Logback API; code nghiệp vụ này không nhắc tên `ConsoleAppender` hay `logback.xml`. Chính provider trên runtime classpath sẽ chọn cách xử lý các lời gọi.

### 6.5. Chạy và xác nhận stdout

Trong thư mục chứa `pom.xml`, chạy:

```bash
mvn -q compile exec:java
```

Với file cấu hình như trên, **các dòng do Logback appender của chương trình tạo ra** là:

```text
INFO LoggingChoiceDemo - event=app_started service=orders-api
WARN LoggingChoiceDemo - event=retry_scheduled attempt=1
```

`DEBUG` không xuất do root INFO. Maven có thể in thông báo build/dependency riêng nếu cấu hình môi trường khác; phần trên là output logging của ứng dụng, không cam kết mọi thông báo từ Maven đều bị loại. Tên `LoggingChoiceDemo` xuất ra vì `%logger{0}` hiển thị phần tên logger cuối.

### 6.6. Đổi level mà không sửa mã Java

Thay dòng:

```xml
<root level="INFO">
```

thành:

```xml
<root level="DEBUG">
```

và chạy lại. Những dòng do appender xuất là:

```text
INFO LoggingChoiceDemo - event=app_started service=orders-api
DEBUG LoggingChoiceDemo - event=cache_lookup key=ORD-7
WARN LoggingChoiceDemo - event=retry_scheduled attempt=1
```

Không có thay đổi trong `LoggingChoiceDemo.java`. Đây là lợi ích của việc tách **lời gọi API** và **chính sách backend**. Trong production, hãy chọn level, appender và format theo nhu cầu vận hành; tránh bật root DEBUG diện rộng nếu không kiểm soát volume.

## 7. Nếu thay Logback bằng `slf4j-simple` thì sao?

Trong dự án minh họa ở mục 6, có thể **thay dependency** `logback-classic` bằng:

```xml
<dependency>
    <groupId>org.slf4j</groupId>
    <artifactId>slf4j-simple</artifactId>
    <version>2.0.16</version>
</dependency>
```

**Thay** có nghĩa là xóa dependency Logback cũ khỏi `pom.xml`, không thêm song song. `slf4j-simple` cung cấp provider SLF4J và cách xử lý đầu ra tối giản, vì vậy code `LoggingChoiceDemo.java` vẫn có thể giữ nguyên.

Những khác biệt quan trọng:

- File `logback.xml` không còn là cấu hình của backend đang dùng; provider simple không sử dụng XML Logback.
- Cú pháp thay thế `{}` trong message vẫn thuộc API SLF4J.
- Format/đích mặc định và cách chỉnh level thuộc `slf4j-simple`; nó thường xuất ra **stderr** và có format khác hẳn ví dụ Logback. Không được kỳ vọng hai dòng mẫu ở mục 6 sẽ xuất giống hệt.
- Simple backend thích hợp cho một số demo hoặc tiện ích nhỏ, nhưng thiếu nhiều khả năng appender/rolling/encoder của backend lớn.

Phiên bản `2.0.16` và `1.5.12` ở bài là **ví dụ cố định** để minh họa cách thay implementation, không phải danh sách bản phát hành mới nhất. Khi nâng version, kiểm tra SLF4J API/provider compatibility cùng các phụ thuộc transitive.

Thí nghiệm này cho thấy: **đổi provider/backend thường không bắt buộc thay lời gọi logging trong mã nghiệp vụ nếu code chỉ dùng SLF4J API**. Nhưng nếu mã ứng dụng import trực tiếp các class riêng của Logback, nó đã phụ thuộc backend và phải được chỉnh sửa khi thay.

## 8. Chọn Log4j 2 làm backend cho SLF4J 2.x

Khi muốn sử dụng Log4j 2 nhưng giữ code gọi SLF4J, hướng thông thường là:

```text
SLF4J API 2.x
    |
    v
log4j-slf4j2-impl (SLF4J provider)
    |
    v
Log4j 2 API / Core
    |
    v
Log4j 2 Appenders / Layouts
```

Dependency tối thiểu về **vai trò** gồm:

- `slf4j-api`: API code nghiệp vụ gọi (có thể đến theo dependency transitive).
- `log4j-slf4j2-impl`: provider chuyển SLF4J 2.x tới Log4j 2.
- `log4j-core`: implementation xử lý event; `log4j-api` là API nền tảng của Log4j 2.

Đây là **sơ đồ dependency**, không phải một `pom.xml` có pin version; các artifact Log4j 2 phải được đồng bộ phiên bản tương thích trong dependency management. Backend này thường được cấu hình bằng `log4j2.xml` hoặc dạng cấu hình Log4j 2 tương ứng, **không phải `logback.xml`**.

Khi chuyển từ Logback:

1. Xóa hoặc exclude `logback-classic` khỏi runtime.
2. Thêm provider Log4j 2 dành cho SLF4J 2.x và các thành phần Core cần thiết, cùng version tương thích.
3. Chuyển cấu hình appender/layout/filter sang cơ chế Log4j 2.
4. Kiểm tra level, placeholder, Throwable, MDC/context, output và cấu hình production.
5. Xác nhận runtime chỉ có provider được lựa chọn, không phải cả Logback và Log4j 2 cùng giành quyền.

Các mức log và chiến lược cấu hình có vẻ tương tự nhưng không phải mọi pattern/layout hay hành vi async đều tương thích một-một.

## 9. Bridge: khi ứng dụng hoặc thư viện dùng API khác nhau

Một ứng dụng lớn có thể chứa cả lời gọi SLF4J, JUL và Log4j 2 API. Không nên vội thay tất cả mã thư viện. **Bridge** giúp chuyển sự kiện về cùng một backend để thống nhất định dạng và thu thập.

### 9.1. Đọc đúng chiều của bridge

| Artifact hoặc adapter | Chiều chuyển thông thường | Tình huống sử dụng |
|---|---|---|
| `jul-to-slf4j` | JUL API → SLF4J API | Thư viện/JDK dùng JUL, ứng dụng chuẩn hóa về backend của SLF4J |
| `log4j-to-slf4j` | Log4j 2 API → SLF4J API | Thư viện dùng Log4j 2 API, ứng dụng backend Logback |
| `slf4j-jdk14` | SLF4J API → JUL | Mã nghiệp vụ dùng SLF4J nhưng đích thực thi là JUL |
| `log4j-slf4j2-impl` | SLF4J 2.x API → Log4j 2 | Mã nghiệp vụ dùng SLF4J, backend Log4j 2 |

**Điểm cực kỳ quan trọng: hai adapter chạy ngược chiều không được ghép thành vòng lặp.**

Chẳng hạn:

```text
NGUY HIỂM:
SLF4J -> Log4j 2   (log4j-slf4j2-impl)
Log4j 2 -> SLF4J   (log4j-to-slf4j)
=> có thể tạo vòng chuyển tiếp / xung đột cấu hình
```

Tương tự, ghép `jul-to-slf4j` (JUL → SLF4J) với `slf4j-jdk14` (SLF4J → JUL) là cấu hình đối nghịch cần tránh.

Trên thực tế, một số adapter phát hiện xung đột và báo lỗi trước thay vì chạy vòng vô hạn; kết quả phụ thuộc thư viện và phiên bản. **Dù biểu hiện là lỗi khởi tạo hay vòng lặp, đây không phải topology hợp lệ.**

### 9.2. Cài đặt JUL → SLF4J cần thiết kế có chủ đích

Nếu dùng `jul-to-slf4j`, nhiều ứng dụng cấu hình `SLF4JBridgeHandler` để chuyển LogRecord từ JUL sang SLF4J. Các lệnh dưới đây là **đoạn minh họa API, không phải chương trình Java độc lập**:

```java
import org.slf4j.bridge.SLF4JBridgeHandler;

// Gọi trong startup khi muốn thay các root handlers JUL:
SLF4JBridgeHandler.removeHandlersForRootLogger();
SLF4JBridgeHandler.install();
```

Phải bảo đảm `jul-to-slf4j` có mặt và backend SLF4J không gửi ngược về JUL. Việc xóa root handlers có thể ảnh hưởng đến những nguồn log JUL đang dựa vào các handlers đó; không áp dụng tùy tiện trong container/framework đã quản lý logging.

Các lời gọi JUL bị bridge chuyển tiếp còn chịu tác động của level/filter JUL. Với lượng log JUL rất lớn, cần đánh giá chi phí của bridge và các cấu hình hiệu năng liên quan. Bridge không thể tạo ra request ID hoặc structured field chưa được cung cấp.

### 9.3. Không cần bridge nếu chỉ muốn đọc chung một collector

Đôi khi một thư viện ghi JUL ra stderr, còn ứng dụng ghi Logback ra stdout, và agent thu cả hai. Có thể đủ cho yêu cầu cơ bản mà không phải cài bridge. Tuy nhiên, format, correlation và kiểm soát level sẽ kém nhất quán. Quyết định bridge dựa trên nhu cầu điều hành và chi phí, không chỉ mong muốn “mọi API thành một”.

## 10. Spring Boot và các hệ sinh thái đã chọn backend mặc định

Spring Boot thường dùng SLF4J cùng **Logback** trong cấu hình logging mặc định của nhiều starter. Nếu ứng dụng đang chạy ổn và Logback đáp ứng các yêu cầu, **không nhất thiết phải thay implementation** chỉ vì có backend khác.

Nếu có lý do thực sự dùng Log4j 2, cần:

1. Xem dependency tree để xác nhận starter logging mặc định đang đến từ đâu.
2. Exclude `spring-boot-starter-logging` ở các dependency thích hợp theo cách hướng dẫn của phiên bản Spring Boot đang sử dụng.
3. Thêm `spring-boot-starter-log4j2` hoặc tích hợp tương thích do phiên bản Spring Boot hỗ trợ.
4. Dùng file cấu hình phù hợp với Log4j 2 và cơ chế của Spring Boot.
5. Kiểm tra dependency tree, runtime provider, logging trong test, stack trace, profile và output.

Đây là **quy trình định hướng**, không phải bản `pom.xml` áp dụng nguyên xi cho mọi phiên bản Spring Boot. Không loại dependency mặc định rồi thêm một provider khác mà chưa kiểm tra thư viện còn phụ thuộc vào những gì.

Một số application server có hệ thống logging riêng, classloader phân tầng hoặc đã cài JUL/SLF4J bridge. Ở những môi trường này, “chỉ một provider” cần được kiểm tra trong **runtime thực tế** chứ không chỉ nhìn dependency ở dự án.

## 11. Thư viện Java nên chọn API hay backend?

Một **library** được nhúng vào nhiều ứng dụng thường nên tránh ép ứng dụng chủ chọn backend, trừ khi có lý do rất cụ thể. Một cách thiết kế thông dụng là:

- Library gọi `slf4j-api` và để ứng dụng cuối cung cấp provider/runtime implementation.
- Không đóng gói `logback-classic` hoặc `slf4j-simple` như một dependency runtime bắt buộc của library nếu không được yêu cầu.
- Không tự ý thay root logger, xóa handler, thay cấu hình global hoặc quyết định nơi lưu log thay ứng dụng chủ.
- Ghi logger name rõ ràng theo package/class và truyền `Throwable`/context đúng.

Ví dụ Maven cho **thư viện**:

```xml
<dependency>
    <groupId>org.slf4j</groupId>
    <artifactId>slf4j-api</artifactId>
    <version>2.0.16</version>
</dependency>
```

Đây là **snippet dependency**, không phải `pom.xml` hoàn chỉnh. Ứng dụng dùng library sẽ có quyền chọn Logback, Log4j 2, JUL adapter hay provider khác. Các dự án đặc biệt cần giữ dependency tối thiểu có thể chọn trực tiếp JUL, nhưng phải tính tới cách host ứng dụng muốn thống nhất logging.

**Không nên gói provider ẩn trong thư viện rồi khiến ứng dụng có hai provider.** Nếu nhà phát triển library cần log trong test của chính library, có thể thêm test-scoped provider riêng, tránh phát hành nó trong runtime dependency.

## 12. Kiểm tra implementation thực sự đang chạy

Không suy ra backend chỉ từ import `org.slf4j.Logger`. Cần kiểm tra dependency và runtime.

### 12.1. Xem cây phụ thuộc

Với Maven:

```bash
mvn dependency:tree
```

Hoặc lọc các artifact liên quan trong đầu ra:

```text
org.slf4j:slf4j-api
ch.qos.logback:logback-classic
org.slf4j:slf4j-simple
org.apache.logging.log4j:log4j-slf4j2-impl
org.slf4j:jul-to-slf4j
org.apache.logging.log4j:log4j-to-slf4j
```

Danh sách trên là **các artifact cần chú ý**, không phải một cây dependency hợp lệ chứa tất cả cùng lúc. Kiểm tra cả scope (compile, runtime, test), dependencyManagement, các dependency transitive, fat JAR/shaded JAR và classpath thực tế của môi trường deploy. Cây Maven lúc build không tự bảo đảm mọi container sẽ nạp đúng cùng các JAR đó.

### 12.2. Kiểm tra logger factory ở runtime

Trong chương trình có `slf4j-api`:

```java
// Đoạn minh họa, bên trong main của ứng dụng:
System.out.println(
        org.slf4j.LoggerFactory.getILoggerFactory()
                .getClass().getName());
```

Khi dùng provider Logback phổ biến, kết quả lớp factory thường là `ch.qos.logback.classic.LoggerContext`. Với provider khác, kết quả sẽ khác. Đừng viết logic nghiệp vụ phụ thuộc tuyệt đối vào tên class của provider; dùng cách kiểm tra này để **chẩn đoán**, không làm API chung.

SLF4J có thể báo cảnh báo lúc khởi động nếu thiếu provider hoặc tìm thấy nhiều provider. Đọc các cảnh báo đó thay vì chỉ nhìn xem code compile thành công.

### 12.3. Thử một event tại runtime

Tạo một lời gọi `INFO` với message dễ nhận diện và kiểm tra:

- Backend nào nhận log?
- Event xuất vào stdout, stderr, file hay collector?
- Level DEBUG/INFO/WARN có được lọc đúng?
- Tên logger, message parameters và stack trace có được render chính xác?
- Có log trùng do bridge, appenders hoặc additivity không?
- Có dữ liệu ngữ cảnh bị mất khi qua bridge không?

Không in secret hay dữ liệu thật nhạy cảm chỉ để thực hiện bài kiểm tra.

## 13. Các lỗi phổ biến khi chọn backend và cách xử lý

| Biểu hiện | Nguyên nhân thường gặp | Cách khắc phục |
|---|---|---|
| SLF4J báo không tìm thấy provider | Chỉ có `slf4j-api`, chưa có implementation 2.x hợp lệ | Thêm đúng một provider phù hợp hoặc dùng hệ thống logging của framework |
| SLF4J báo nhiều providers | Logback và simple/Log4j provider cùng có trên runtime | Loại các provider dư, kiểm tra dependency transitive |
| Binding `StaticLoggerBinder` không dùng được với SLF4J 2 | Provider/binding thuộc SLF4J 1.7 | Nâng cấp tích hợp tương thích đúng major |
| `logback.xml` không đổi output | Runtime đang chọn backend khác hoặc file không được load | Kiểm tra provider thực tế, vị trí config và classpath |
| `log4j2.xml` bị bỏ qua | Runtime không chạy Log4j 2 Core hoặc config không được nạp | Xác nhận provider/Core, đường nạp và startup logs |
| Log không xuất hiện | No-op backend, level/filter loại sự kiện hoặc đích khác dự kiến | Kiểm tra runtime implementation, effective level, output |
| Log xuất nhiều lần | Gắn nhiều appenders, propagation hoặc bridge/collector nhân bản | Kiểm tra topology và additivity, không chỉ lời gọi logger |
| Ứng dụng lỗi khi khởi động bridge | Có hai bridge đối nghịch hoặc version không tương thích | Xóa adapter gây vòng, thống nhất một hướng routing |
| Không có JSON fields hay MDC | Chỉ có message placeholder và pattern text | Thêm structured arguments/encoder/context phù hợp |
| Phần test log khác production | Test-scoped provider/config khác | Kiểm tra test runtime và file cấu hình test |
| Backend có CVE/compatibility issue | Phiên bản cũ hoặc dependency transitive không đồng bộ | Rà soát dependency management, advisory và cập nhật có kiểm thử |

## 14. Vận hành: lựa chọn backend ảnh hưởng điều gì?

### 14.1. Structured logging và observability

Nếu cần log JSON với `traceId`, `requestId`, `service.name` và field nghiệp vụ có thể truy vấn, backend phải hỗ trợ encoder/schema tương ứng. Chỉ dùng SLF4J placeholder `{}` thường tạo một message text, **không bảo đảm collector nhận các field độc lập**.

Ví dụ JSON mong muốn:

```json
{
  "timestamp": "2026-11-09T08:15:03.125Z",
  "level": "INFO",
  "service": "orders-api",
  "logger": "com.example.orders.OrderService",
  "traceId": "trace-42",
  "event": "order_accepted",
  "orderId": "ORD-7"
}
```

Đây là **output minh họa**, không phải output tự động của chương trình mục 6. Việc cấp phát trace ID, truyền context và bảo đảm schema là trách nhiệm của ứng dụng và observability pipeline. Đổi provider không thể tự sinh ra dữ liệu chưa được truyền vào event.

### 14.2. Exception và bảo mật

Ứng dụng phải truyền `Throwable` qua API phù hợp nếu cần stack trace. Không chỉ ghi `error.getMessage()` khi mục tiêu là điều tra cause chain. Chọn backend có layout/encoder bảo toàn exception nhưng không vô tình xuất credentials, token hoặc request payload nhạy cảm.

Không backend nào tự bảo đảm mọi dữ liệu nhạy cảm đều được che. Cần chính sách bảo vệ từ nguồn, sanitization/escaping, quyền truy cập log, mã hóa, retention và kiểm thử thực tế.

### 14.3. Async, file rotation và độ tin cậy

Các backend khác nhau có async, buffering, rolling và file retention theo cách triển khai riêng. Async có thể giảm độ trễ đường request nhưng cũng tạo nguy cơ mất event khi queue đầy hoặc process chết. Một `RollingFileAppender` không tự bảo đảm dữ liệu đã đến collector. Hãy đánh giá:

- Mức log và số lượng events/giây ở tải đỉnh.
- Chi phí format/serialize JSON và stack trace.
- Queue size, drop/block policy, shutdown/flush.
- Đường đi tới collector, sự cố mạng và retry.
- Disk quota, rotation, retention và quyền file.
- Sự khác biệt giữa thời điểm event và thời điểm event được ghi.

**Backend mạnh không thay thế thiết kế pipeline đúng.** Một ứng dụng dùng Logback/Log4j 2 vẫn có thể log trùng, thiếu trace ID hoặc mất dữ liệu nếu cấu hình sai.

## 15. Quy trình chuyển backend an toàn

Khi backend hiện tại không đáp ứng yêu cầu, có thể thực hiện theo thứ tự:

1. **Ghi lại trạng thái hiện tại:** API đang gọi, provider/backend runtime, config file, các thư viện dùng JUL/Log4j 2, nơi log được xuất.
2. **Chốt yêu cầu đầu ra:** level, JSON fields, stack trace, MDC, routing, rotation, async, bảo mật, retention và throughput cần đạt.
3. **Chọn topology một chiều:** SLF4J 2.x → một provider phù hợp → backend; thêm bridge cho API khác chỉ khi cần, không tạo vòng.
4. **Thay dependencies có kiểm soát:** bỏ provider cũ, thêm provider mới và dependencies backend, đồng bộ version theo BOM.
5. **Chuyển cấu hình:** pattern, logger level, appender, filters, exception conversion, structured encoder và profile.
6. **Kiểm tra test/runtime:** dependency tree, startup warnings, effective provider, output INFO/DEBUG/ERROR, Throwable, context và duplicate.
7. **Đo trước/sau:** throughput, p95/p99 latency, CPU/RAM, dropped logs, disk/collector lag và khối lượng log.
8. **Triển khai từng bước:** thử staging, quan sát cảnh báo, bảo đảm đường rollback nếu không đạt.
9. **Cập nhật hướng dẫn vận hành:** xác định ai sở hữu logging configuration, cách tăng level tạm thời, cách tra cứu log và chu kỳ vá lỗi.

Nếu chỉ muốn thay nơi lưu log, đôi khi **đổi appender/collector** đủ để giải quyết. Không cần đổi toàn bộ API/backend nếu vấn đề nằm ở pipeline xuất log.

## 16. Checklist cuối: “Chọn implementation” đúng chưa?

- [ ] Mã nghiệp vụ dùng một logging API có chủ đích, thường là SLF4J hoặc API mặc định của framework.
- [ ] Runtime có **đúng một SLF4J 2.x provider phù hợp** nếu dùng SLF4J 2.x.
- [ ] Không còn binding 1.7 bị nhầm là provider 2.x.
- [ ] Không có bridge đối nghịch như JUL ↔ SLF4J hay Log4j 2 ↔ SLF4J.
- [ ] Dependency JDK, backend, facade/provider và framework tương thích phiên bản.
- [ ] Đã xác nhận implementation **thực sự chạy** qua dependency tree và runtime diagnostics.
- [ ] Logger name, level, message formatting, exception và MDC/structured fields đúng.
- [ ] File config của backend được nạp đúng, không nhầm `logback.xml` với `log4j2.xml`.
- [ ] Các đầu ra console/file/collector và additivity không làm log trùng hoặc mất log.
- [ ] Đã kiểm tra giới hạn bảo mật, rotation, retention và hiệu năng theo môi trường.
- [ ] Có quy trình đổi cấu hình/triển khai/rollback mà không sửa logic nghiệp vụ.

**Kết luận:** chọn implementation logging là quyết định của **runtime architecture**. SLF4J giúp tách code nghiệp vụ khỏi backend, nhưng không loại bỏ trách nhiệm chọn đúng **một provider**, quản lý dependency/version, cấu hình backend và xử lý bridge một chiều. Logback, Log4j 2, JUL và simple backend đều có chỗ dùng hợp lý; lựa chọn tốt là lựa chọn đáp ứng yêu cầu vận hành có thể kiểm chứng, thay vì chọn theo tên công nghệ.
