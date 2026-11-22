# Profile cấu hình Logback trong Java: dev, test, staging và production

## 1. Profile cấu hình là gì?

**Profile cấu hình logging** là cách chọn các thiết lập ghi log phù hợp với môi trường hoặc chế độ chạy ứng dụng. Cùng một chương trình Java có thể cần:

- **Development (`dev`):** thông tin chi tiết, dễ đọc trên console để tìm lỗi.
- **Test (`test`):** đầu ra nhất quán, hạn chế nhiễu và tránh ghi file không cần thiết.
- **Staging:** gần production để kiểm thử pipeline, nhưng có thể bật thêm một số chẩn đoán có kiểm soát.
- **Production (`prod`):** mức log vừa đủ, định dạng ổn định để collector phân tích, dữ liệu nhạy cảm được kiểm soát và lưu trữ/rotation phù hợp.

Ví dụ, trong `dev` ta có thể thấy sự kiện `DEBUG com.example.orders.OrderService - cache miss`, nhưng ở `prod` chỉ cần `INFO/WARN/ERROR` tùy chính sách. Mục tiêu là **thay cách log được xử lý, không thay logic nghiệp vụ mỗi khi triển khai**.

Cần phân biệt ngay hai khái niệm:

1. **Logback thuần** là backend logging. Nó có file cấu hình, property substitution, appender, logger, level, filter và cơ chế chọn cấu hình. Nó **không có một khái niệm Spring profile mặc định trong bản thân Logback**.
2. **Spring Boot + Logback** có tích hợp riêng cho Spring Environment, đặc biệt các thẻ `<springProfile>` và `<springProperty>` trong `logback-spring.xml`. Các thẻ đó **không phải XML chuẩn của Logback độc lập**.

Vì thế “cấu hình theo profile” có thể là **chọn giá trị cấu hình bằng environment/system property** trong ứng dụng Java thuần, hoặc **chọn nhánh cấu hình theo Spring profile** khi dùng Spring Boot. Bài này trình bày cả hai và chỉ ra ranh giới của chúng.

## 2. Profile tác động vào thành phần nào của logging?

Logback thường hoạt động theo luồng:

```text
Ứng dụng → SLF4J Logger → Logback event → Appender → Encoder/Layout → Console/File/Collector
                  |               |             |
                Level        Filter/route     Pattern/JSON
```

Sơ đồ mang tính khái quát; appender điều phối encoder/layout, và điều kiện lọc có thể ở nhiều tầng khác nhau.

Profile có thể điều khiển:

| Thành phần | Dev/test | Production |
|---|---|---|
| **Level root** | `DEBUG` hoặc `INFO` theo nhu cầu | `INFO` hoặc `WARN` theo đặc thù hệ thống |
| **Level theo package** | Bật `DEBUG` riêng cho `com.example.orders` | Chỉ bật khi điều tra, có kiểm soát |
| **Appender** | Console để quan sát | Console cho collector; có thể thêm file/remote appender nếu cần |
| **Encoder/layout** | Pattern text dễ đọc | Pattern ổn định hoặc JSON có cấu trúc qua encoder phù hợp |
| **Dữ liệu ngữ cảnh** | Request ID, trace ID phục vụ debug | Vẫn cần correlation ID, nhưng giới hạn dữ liệu nhạy cảm |
| **Rotation/retention** | Thường đơn giản | Cần chính sách bảo toàn, giới hạn, quyền truy cập và retention |
| **Async/buffering** | Chỉ khi hữu ích | Đánh giá bằng lưu lượng và yêu cầu tránh mất log |

Profile **không tự sinh** `requestId`, `traceId`, MDC, JSON field hay dữ liệu nghiệp vụ. Ứng dụng và backend phải cung cấp chúng; profile chỉ quyết định có xuất và xử lý chúng như thế nào.

## 3. Chọn cấu hình với Logback thuần (không cần Spring)

### 3.1. Biến môi trường và system properties

Với Logback độc lập, cách đơn giản nhất là giữ **một cấu hình** và sử dụng property substitution:

```xml
<configuration>
    <property name="SERVICE_NAME" value="orders-api"/>

    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>%level %logger{0} app=${SERVICE_NAME} env=${APP_ENV:-local} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="${ROOT_LOG_LEVEL:-INFO}">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

Đây là file `logback.xml` cho Logback, không phải file Spring Boot mở rộng. Các biến:

- `SERVICE_NAME` được khai báo ngay trong file để dùng lại trong pattern.
- `APP_ENV` có thể đến từ biến môi trường hoặc system property; `local` là giá trị fallback trong cú pháp của Logback.
- `ROOT_LOG_LEVEL` chọn mức root. Nếu không được cung cấp, fallback là `INFO`.
- `%logger{0}` trong pattern rút gọn tên logger để hiển thị phần tên cuối, không thay đổi định danh logger trong event.
- `%msg%n` xuất message và kết thúc dòng.
- `target=System.out` định tuyến appender này sang stdout. Đây là cấu hình **Logback**, khác với `java.util.logging.ConsoleHandler` thường ghi stderr.

Khi chạy với `ROOT_LOG_LEVEL=DEBUG`, các lời gọi `DEBUG` sẽ được chấp nhận nếu không còn filter khác loại bỏ chúng. Khi `ROOT_LOG_LEVEL=INFO`, `DEBUG` bị loại. Mức thực tế còn chịu ảnh hưởng của logger con có level riêng, filter và additivity.

**Không đưa bí mật vào pattern** hoặc khai báo các biến nhạy cảm chỉ để xuất ra log. Property substitution chọn cấu hình; nó không phải cơ chế che thông tin.

### 3.2. Chọn file cấu hình khác theo môi trường

Nếu các môi trường thật sự cần topology appender khác nhau, ta có thể dùng các file riêng như `logback-dev.xml` và `logback-prod.xml`. Với **ứng dụng Logback thuần**, có thể chỉ định file bằng JVM system property khi khởi động:

```bash
java -Dlogback.configurationFile=/opt/app/config/logback-prod.xml -cp "app.jar:lib/*" com.example.Main
```

Lệnh chỉ là **hình thức minh họa** cho Unix-like environment: phải có các jar, class main và đường dẫn tương ứng; trên Windows dấu phân cách classpath và đường dẫn sẽ khác. Property cần được thiết lập đủ sớm, trước khi Logback khởi tạo.

Ưu điểm: mỗi cấu hình có thể có appender và policy độc lập. Nhược điểm: các file dễ **trôi cấu hình**, quên sửa đồng bộ pattern, logger name, security policy và chuẩn output. Do đó, chỉ tách file khi lợi ích lớn hơn chi phí duy trì; phần chung có thể tái sử dụng qua cơ chế include của Logback nếu phù hợp.

Trong Spring Boot, `logging.config` là lựa chọn khác để chỉ định vị trí cấu hình; đừng trộn lẫn cách nạp config của Spring Boot và cách Logback tự khởi tạo mà không kiểm tra thứ tự startup.

### 3.3. Độ ưu tiên của file cấu hình

Khi dùng cơ chế auto-configuration thông dụng của Logback, `logback-test.xml` thường được ưu tiên so với `logback.xml` nếu cùng có mặt trên classpath. Điều này giúp test có cấu hình riêng mà không ghi file production hoặc làm output quá nhiễu.

Các cơ chế cấu hình programmatic, system property, SPI, trình khởi tạo của framework hoặc phiên bản Logback có thể thay đổi đường nạp cấu hình. Vì vậy nếu log hiển thị “không đúng profile”, hãy xác nhận **file nào thật sự được load** trước khi đổi hàng loạt level.

## 4. Ví dụ Java 17 chạy được với Logback thuần và Maven

Ví dụ nhỏ này chứng minh **một file `logback.xml` có thể đổi level và nhãn môi trường mà không sửa code Java**. Phần code dùng SLF4J API với backend Logback. **Không thể chạy chỉ với `javac ProfileLoggingDemo.java`**, vì cần các dependency Maven; lệnh Maven bên dưới biên dịch và chạy chương trình.

### 4.1. Cấu trúc dự án

```text
logback-profile-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/example/logging/ProfileLoggingDemo.java
        └── resources/
            └── logback.xml
```

### 4.2. Tệp `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>logback-profile-demo</artifactId>
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
                    <mainClass>com.example.logging.ProfileLoggingDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`logback-classic` đưa Logback backend vào runtime và kéo SLF4J API qua dependency phù hợp. Phiên bản trong `pom.xml` là **phiên bản minh họa cố định cho bài học**, không phải tuyên bố đây là bản mới nhất. Với hệ thống thật, kiểm tra yêu cầu JDK, CVE, dependency management và phiên bản tương thích đang được nhóm quản lý.

### 4.3. Tệp `src/main/resources/logback.xml`

```xml
<configuration>
    <property name="SERVICE_NAME" value="orders-api"/>

    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>%level %logger{0} app=${SERVICE_NAME} env=${APP_ENV:-local} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="${ROOT_LOG_LEVEL:-INFO}">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

File này giống ví dụ ở mục 3 và nằm trên classpath dưới `src/main/resources`. Không cần định nghĩa profile trong mã Java.

### 4.4. Tệp `src/main/java/com/example/logging/ProfileLoggingDemo.java`

```java
package com.example.logging;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class ProfileLoggingDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(ProfileLoggingDemo.class);

    public static void main(String[] args) {
        LOG.info("event=app_started");
        LOG.debug("event=cache_probe");
    }
}
```

`LoggerFactory.getLogger(ProfileLoggingDemo.class)` tạo logger có tên đầy đủ theo lớp. `root` trong cấu hình định mức hiệu lực mặc định nếu logger con không chỉ định level riêng. Mã phát cả INFO và DEBUG, nhưng **backend chỉ xuất những event được level/filter cho phép**.

### 4.5. Chạy với profile mặc định

Từ thư mục `logback-profile-demo`, yêu cầu JDK 17+ và Maven:

```bash
mvn -q compile exec:java
```

Giả định chưa thiết lập `APP_ENV` hay `ROOT_LOG_LEVEL` trong hệ điều hành/JVM và không có file cấu hình khác được ưu tiên, **stdout do chương trình tạo** sẽ gồm đúng dòng:

```text
INFO ProfileLoggingDemo app=orders-api env=local - event=app_started
```

Dòng DEBUG không xuất vì root mặc định là INFO. Logback trong cấu hình này ghi ra stdout. Maven có thể có thông báo riêng ở stderr hoặc stdout trong trường hợp cấu hình build/môi trường khác; đoạn trên mô tả **output của logger trong ví dụ**, không cam kết toàn bộ output của Maven sẽ chỉ có một dòng.

### 4.6. Chạy với profile dev

Trên Linux/macOS (shell tương thích POSIX):

```bash
APP_ENV=dev ROOT_LOG_LEVEL=DEBUG mvn -q compile exec:java
```

Trên Windows PowerShell:

```powershell
$env:APP_ENV = "dev"
$env:ROOT_LOG_LEVEL = "DEBUG"
mvn -q compile exec:java
Remove-Item Env:APP_ENV
Remove-Item Env:ROOT_LOG_LEVEL
```

Khi chạy với hai biến môi trường trên, output của logger là:

```text
INFO ProfileLoggingDemo app=orders-api env=dev - event=app_started
DEBUG ProfileLoggingDemo app=orders-api env=dev - event=cache_probe
```

Ở đây, giá trị `APP_ENV=dev` chỉ được hiển thị trong pattern; **việc bật DEBUG là nhờ `ROOT_LOG_LEVEL=DEBUG`**, không phải vì Logback tự hiểu chữ `dev`. Nếu chỉ đặt `APP_ENV=dev` mà không đặt `ROOT_LOG_LEVEL`, logger vẫn giữ INFO. Đó là điểm khác biệt quan trọng giữa **nhãn môi trường** và **quy tắc điều kiện cấu hình**.

Nếu muốn profile điều khiển nhiều appender, JSON encoder hay routing khác nhau, phải thêm cấu hình điều kiện hoặc cơ chế chọn file, không chỉ đổi nhãn `env`.

## 5. Spring Boot: `logback-spring.xml` và `springProfile`

Với ứng dụng **Spring Boot dùng Logback** làm backend, Spring Boot cung cấp thẻ mở rộng để áp dụng cấu hình dựa trên Spring Environment. Hai thành phần nổi bật:

- `<springProfile name="dev"> ... </springProfile>`: chỉ kích hoạt phần cấu hình bên trong khi biểu thức profile khớp.
- `<springProperty .../>`: đưa một thuộc tính từ Spring Environment vào context cấu hình Logback để sử dụng trong pattern, appender hoặc cấu hình khác.

Các thẻ này cần được Spring Boot xử lý; **Logback thuần không hiểu chúng**. Thông thường đặt file tại `src/main/resources/logback-spring.xml` thay vì `logback.xml` để Spring Boot điều phối lúc khởi động.

### 5.1. Ví dụ `logback-spring.xml`

```xml
<configuration>
    <springProperty scope="context"
                    name="serviceName"
                    source="spring.application.name"
                    defaultValue="orders-api"/>

    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>%level [${serviceName}] %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <!-- Mặc định: INFO cho những logger không override. -->
    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>

    <!-- Chỉ namespace này chi tiết hơn ở dev. -->
    <springProfile name="dev">
        <logger name="com.example" level="DEBUG"/>
    </springProfile>

    <!-- Namespace này ít nhiễu hơn ở production. -->
    <springProfile name="prod">
        <logger name="com.example" level="WARN"/>
    </springProfile>
</configuration>
```

**Kết quả cấu hình:**

- Khi profile `dev` đang active, các logger thuộc `com.example` có mức hiệu lực DEBUG; event DEBUG của chúng có thể đi tới appender CONSOLE kế thừa từ root.
- Khi chỉ `prod` đang active, `com.example` có mức WARN; event INFO/DEBUG ở namespace đó không được xuất.
- Nếu không có profile `dev` hoặc `prod` khớp, namespace không được override và có thể kế thừa INFO từ root.
- Các logger ngoài `com.example` vẫn theo root INFO nếu không có rule khác.

Ví dụ này có **một root và một console appender**. Profile chỉ đổi level của một namespace, giúp tập trung vào hành vi có thể kiểm chứng. Nếu muốn cấu hình appender khác theo profile, có thể đặt định nghĩa appender, root/logger hoặc tham chiếu appender trong các nhánh `<springProfile>`, nhưng phải tránh khai báo trùng tên hoặc nhiều root tranh chấp khi nhiều profile active cùng lúc.

**Lưu ý môi trường:** `dev` và `prod` không nên được kích hoạt đồng thời nếu hai nhánh cùng định nghĩa level cho `com.example`. Khi nhiều profile khớp, kết quả cuối có thể phụ thuộc quá trình xử lý cấu hình; hãy thiết kế các nhóm profile loại trừ nhau và kiểm tra effective level.

### 5.2. Kích hoạt Spring profile

Có thể đặt tên ứng dụng trong `application.yml`:

```yaml
spring:
  application:
    name: orders-api
```

Sau đó kích hoạt profile tại thời điểm chạy bằng cơ chế của Spring Boot, ví dụ:

```bash
java -jar orders-api.jar --spring.profiles.active=dev
java -jar orders-api.jar --spring.profiles.active=prod
```

Hai lệnh này là **minh họa**, yêu cầu ứng dụng Spring Boot đã được đóng gói thành `orders-api.jar`; chúng không chạy được từ dự án Maven Logback thuần ở mục 4.

Hoặc thiết lập biến môi trường:

```bash
SPRING_PROFILES_ACTIVE=prod java -jar orders-api.jar
```

Cấu hình ở `application.properties`/`application.yml`, biến môi trường, command-line arguments và môi trường triển khai có quy tắc ưu tiên của Spring Boot. Khi có nhiều nguồn, cần xác nhận **active profiles thật sự** và thuộc tính cuối cùng mà Spring Environment cung cấp. Tránh cố định `spring.profiles.active=dev` trong artifact sẽ triển khai production; chọn profile từ deployment.

### 5.3. Phân biệt Spring profile và Logback property

Trong ví dụ Maven thuần, `APP_ENV=dev` và `ROOT_LOG_LEVEL=DEBUG` là **hai biến độc lập**. Trong Spring Boot, `SPRING_PROFILES_ACTIVE=dev` điều khiển biểu thức `<springProfile name="dev">`. Chỉ viết:

```properties
APP_ENV=dev
```

không làm Spring Boot tự kích hoạt profile `dev`. Ngược lại, chỉ kích hoạt profile `dev` cũng không tự bảo đảm mọi logger đều bật DEBUG: phải có rule trong `logback-spring.xml` hoặc cấu hình level tương ứng.

Spring Boot còn hỗ trợ cấu hình mức log qua `logging.level.root` hoặc `logging.level.com.example` trong Spring Environment. Khi trộn `logging.level.*` với định nghĩa level trong `logback-spring.xml`, phải kiểm thử **mức hiệu lực thực tế sau khi ứng dụng khởi động**, không suy từ duy nhất một file. Thứ tự nạp cấu hình và cách Spring Boot quản lý logging có thể làm kết quả khác ý muốn.

### 5.4. Vì sao `logback.xml` khác `logback-spring.xml`?

- `logback.xml` là tên chuẩn cho Logback tự nạp; Logback có thể xử lý file này **trước khi** Spring Boot Environment sẵn sàng cho các extension Spring.
- `logback-spring.xml` là tên được Spring Boot chủ động xử lý, phù hợp khi dùng `springProfile` và `springProperty`.
- Không sao chép các thẻ `springProfile` vào một ứng dụng Java/Maven thuần rồi mong Logback hiểu; nó có thể báo lỗi “no applicable action” hoặc lỗi cấu hình tương đương.
- Với các extension Spring của Logback, **không bật cơ chế `scan="true"` của Logback một cách tùy tiện**: khả năng cấu hình lại bằng scanner của Logback không tương thích với cách Spring xử lý các phần mở rộng này. Dùng phương pháp reload/quản trị do Spring Boot hoặc kiến trúc ứng dụng hỗ trợ.
- Nếu ứng dụng dùng `logging.config` hoặc Logback customization khác, kiểm tra đường dẫn file đang được nạp, thay vì mặc định mọi `logback-spring.xml` đều chắc chắn được chọn.

**Ví dụ `logback-spring.xml` ở trên không phải chương trình độc lập.** Nó phải nằm trong ứng dụng Spring Boot có Logback backend; không dùng câu lệnh `javac`/`java` của ví dụ Logback thuần để khởi chạy file này.

## 6. Tách cấu hình chung và phần riêng từng profile

Nếu dự án lớn có nhiều môi trường, cần giữ tối đa các quy tắc **chung** như:

- Format timestamp và timezone; quyết định cấu trúc JSON/text.
- Tên logger từ package/class và event name.
- Correlation ID, trace ID, error code, trường nghiệp vụ cần thiết.
- Chính sách không ghi secret, che dữ liệu và giới hạn log volume.
- Quy ước exception/cause và cách collector gom multiline stack trace.

Chỉ tách những thứ thật sự cần khác: level, nơi xuất, verbosity, sampling, chính sách file, một vài filter.

Có hai cách chính:

**Cách A — Một cấu hình, property cho điểm thay đổi ít.**

```xml
<root level="${ROOT_LOG_LEVEL:-INFO}">
    <appender-ref ref="CONSOLE"/>
</root>
```

Dễ quản lý khi mỗi môi trường chỉ đổi vài giá trị. Property fallback phải hợp lý; sản phẩm thật nên theo dõi giá trị đã nạp.

**Cách B — Chọn nhánh hoặc chọn file riêng.**

Ví dụ trong Spring Boot:

```xml
<springProfile name="dev">
    <logger name="com.example.orders" level="DEBUG"/>
</springProfile>

<springProfile name="prod">
    <logger name="com.example.orders" level="INFO"/>
</springProfile>
```

Dùng khi cần thay đổi theo profile và có Spring Boot extension. Với Logback thuần, có thể chọn file cấu hình lúc startup hoặc tổ chức file chung/include; đừng dùng `<springProfile>` nếu không có Spring Boot.

**Không nên lặp lại toàn bộ root/appender/filter ở mọi profile nếu chỉ khác một level**, vì dễ khiến một profile quên khai báo encoder, masking, exception format hoặc có hai output destination khác nhau ngoài dự kiến.

## 7. Level theo package: tránh bật DEBUG toàn hệ thống

Với service nhiều module, thường nên chọn mức root đủ an toàn và chỉ bật chi tiết ở nơi đang xử lý sự cố.

```xml
<root level="INFO">
    <appender-ref ref="CONSOLE"/>
</root>

<logger name="com.example.orders" level="DEBUG"/>
```

Đây là **fragment Logback**, giả định appender `CONSOLE` đã được khai báo trong cấu hình đầy đủ. Như vậy logger thuộc `com.example.orders` được bật DEBUG, các phần khác tiếp tục dùng INFO. Tên logger phải theo package/class nhất quán; logger có tên tùy ý không nằm trong namespace sẽ không nhận rule như dự kiến.

### Một lỗi dễ nhầm: root INFO có cản DEBUG từ logger con không?

Trong Logback, khi một logger con có effective level DEBUG, event DEBUG của nó được tạo rồi truyền tới appender theo hierarchy/additivity. **Mức INFO của root không tự lọc lại event đã được logger con chấp nhận** chỉ vì appender gắn ở root. Appender có filter riêng thì vẫn có thể chặn.

Nếu một record được xuất hai lần, hãy kiểm tra appender được gắn cả ở logger con và root, cùng giá trị `additivity`. Không sửa bằng cách tắt propagation bừa bãi: có thể làm mất đường thu thập log duy nhất.

## 8. Profile và môi trường test

Test thường cần ít log để không che mất kết quả kiểm thử. Với Logback thuần, có thể tạo `src/test/resources/logback-test.xml`, ví dụ:

```xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%level %logger{0} - %msg%n</pattern>
        </encoder>
    </appender>
    <root level="WARN">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

Khi file này nằm trên **test classpath** theo cơ chế Logback thông thường, nó có thể được chọn thay `logback.xml` trong lúc chạy test. Đừng đưa cấu hình chỉ dùng test vào artifact production ngoài ý muốn.

Với Spring Boot, profile `test` có thể đi kèm `application-test.yml` và nhánh `<springProfile name="test">`. Nhưng cần phân biệt:

- **Spring test profile** là trạng thái Spring Environment.
- **`logback-test.xml`** là cơ chế chọn file của Logback/classpath.
- Hai cơ chế độc lập về ý nghĩa; tên “test” giống nhau **không tự biến chúng thành một hệ thống duy nhất**.

Khi test quan tâm nội dung log, có thể dùng test appender để thu event và xác nhận level, logger name, message/arguments thay vì dựa hoàn toàn vào text console. Không nên kiểm thử snapshot có timestamp động mà không kiểm soát dữ liệu thời gian.

## 9. Structured logging, JSON và MDC theo profile

Ở development, pattern text dễ đọc thường đủ:

```text
INFO  [http-17] OrderService - event=order_accepted orderId=ORD-7
```

Ở production, hệ thống thu thập có thể ưu tiên JSON:

```json
{"timestamp":"2026-11-09T08:15:03.125Z","level":"INFO","logger":"com.example.orders.OrderService","traceId":"trace-42","event":"order_accepted","orderId":"ORD-7"}
```

Hai dòng này là **mẫu format minh họa**, không phải đầu ra từ demo Maven ở mục 4. Logback không tự biến `%msg` thành JSON có trường `orderId`; muốn có structured fields phải dùng API/context/encoder phù hợp, có thể cần thêm dependency.

**MDC** (Mapped Diagnostic Context) cho phép gắn `requestId`, `traceId` với event nếu ứng dụng thiết lập và chuyển ngữ cảnh đúng. Trong Logback, pattern `%X{traceId}` thường đọc giá trị từ MDC; nó không tự tạo trace ID. Với thread pool hoặc async, ngữ cảnh phải được truyền và dọn thích hợp để tránh nhiễm thông tin request khác.

Đừng để profile dev ghi payload nhạy cảm rồi vô tình deploy cùng cấu hình sang production. Dù profile có thể đổi độ chi tiết, **quy tắc bảo vệ dữ liệu phải áp dụng nhất quán** ở mọi môi trường có dữ liệu thật.

## 10. Quy tắc an toàn khi thiết kế profile logging

### 10.1. Level không phải cơ chế bảo mật

Chỉ giảm level từ DEBUG xuống INFO không bảo đảm thông tin nhạy cảm biến mất: secret có thể nằm trong message INFO, exception, MDC hoặc structured fields. Không ghi password, access token, API key, session cookie, dữ liệu thẻ và thông tin cá nhân không cần thiết; cân nhắc masking ở nguồn và kiểm chứng encoder.

### 10.2. Chú ý stdout, stderr và nơi thu thập

Trong demo, `ConsoleAppender` đặt `System.out`; một số môi trường lại định tuyến stderr riêng. Nếu triển khai container, quyết định xem collector nhận stdout, stderr hay cả hai. Thêm đồng thời file appender và console appender có thể làm tăng lượng lưu trữ hoặc trùng dữ liệu nếu cả hai được collector thu thập.

### 10.3. Rotation và retention không do Spring profile tự bảo đảm

Một profile có thể chọn `RollingFileAppender`, nhưng bản thân cái tên `prod` không tạo ra giới hạn file, chính sách nén/giữ/xóa hoặc bảo đảm dữ liệu không mất. Cần kiểm tra chính sách rolling theo version Logback đang chạy, quyền ghi file, khối lượng log, disk quota và pipeline thu thập.

### 10.4. Async không đồng nghĩa với không mất log

Nếu prod sử dụng `AsyncAppender`, hãy định nghĩa chính sách queue, khả năng drop, block, flush/shutdown và xử lý khi downstream lỗi. Mỗi môi trường có thể chọn mức hiệu năng khác nhau, nhưng phải kiểm thử thực tế thay vì mặc định async là tốt hơn.

### 10.5. Tránh cấu hình phụ thuộc profile chồng lấn

Nếu cả `dev` và `prod` active, các rule cho cùng logger có thể xung đột. Nếu đặt root/appender khác ở cả hai nhánh, sự cố còn khó xác định hơn. Ưu tiên những profile có vai trò rõ, không chồng lấn hoặc nhóm điều kiện loại trừ nhau.

### 10.6. Quan sát cấu hình đã hiệu lực

Sau startup, nên xác nhận ít nhất: active profile, đường dẫn config đang load, root level, các package override, appender đích, output format và ngữ cảnh thực sự được ghi. Không dùng một thông điệp chứa secret chỉ để chứng minh biến môi trường được đọc thành công.

## 11. Các lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân khả dĩ | Hướng kiểm tra |
|---|---|---|
| `<springProfile>` không được nhận diện | File nạp bởi Logback thuần hoặc `logback.xml` thay vì Spring Boot extension | Dùng `logback-spring.xml` với Spring Boot, kiểm tra đường nạp |
| Đã bật `SPRING_PROFILES_ACTIVE=dev` nhưng không có DEBUG | Không có rule dev, logger name khác namespace, hoặc filter | Kiểm tra active profiles, effective level, filter |
| `APP_ENV=dev` hiện trong log nhưng level vẫn INFO | Đây chỉ là biến hiển thị; chưa đặt `ROOT_LOG_LEVEL` hoặc rule | Kiểm tra biến level, không nhầm nhãn môi trường |
| Test log nhiều dù có `logback-test.xml` | File không trên test classpath hoặc framework dùng config khác | Kiểm tra classpath và file được nạp |
| Không thấy profile production áp dụng | Active profile khác, tên `prod`/`production` không khớp | Xác nhận chính xác tên profile tại runtime |
| Log trùng hai lần | Appender gắn ở logger con và root hoặc additivity | Kiểm tra appender-ref, additivity và thu thập ngoài |
| JSON không parse được | Pattern text giả JSON hoặc encode chuỗi sai escape | Dùng encoder/serializer có cấu trúc |
| Thiếu `traceId` | Không gán MDC hoặc không truyền qua async | Kiểm tra khởi tạo và dọn context |
| Production bỗng ghi quá nhiều DEBUG | Root/package level bị override bằng biến/profile sai | Xác nhận config thực tế, thêm cảnh báo log volume |
| Đổi `logging.level.*` nhưng mức log không như nghĩ | Quy tắc Spring Boot, Logback file và thứ tự khởi tạo cùng tác động | Kiểm tra effective level sau startup |
| Logback scanner báo lỗi với `springProfile` | Dùng scan/reload không tương thích Spring extension | Bỏ scan tự động kiểu Logback; dùng cơ chế phù hợp |
| Console và file cùng ghi làm số log tăng | Hai destination được collector thu thập | Xác định rõ pipeline và chống trùng ở collector |

## 12. Checklist triển khai theo môi trường

Trước khi phát hành một cấu hình Logback mới, hãy xác nhận:

1. **Môi trường được xác định ở đâu?** Environment variable, JVM system property, file config, Spring profile hay deployment manifest?
2. **Phần nào thay đổi?** Level, appender, pattern/JSON encoder, rolling, async hoặc package-specific logger?
3. **Có cấu hình fallback an toàn không?** Nếu không chọn profile, hệ thống sẽ dùng mức và đích nào?
4. **Có xuất sai định dạng không?** Test text/JSON, timestamp, timezone, newline, Unicode, exception stack trace.
5. **Có log trùng hoặc biến mất không?** Kiểm tra additivity, root, appender-ref, filter, collector.
6. **Có correlation context không?** Request ID/trace ID phải được ứng dụng cung cấp, không tự xuất hiện vì profile.
7. **Có dữ liệu nhạy cảm không?** Kiểm tra message, parameters, MDC, Throwable và retention.
8. **Có giới hạn chi phí không?** Log volume, CPU/IO, async queue, rotation, storage/quota.
9. **Có phù hợp đúng runtime không?** `logback.xml` cho Logback thuần, `logback-spring.xml` cho Spring Boot extensions.
10. **Đã kiểm thử sau khi đóng gói chưa?** Kiểm tra file trên classpath, profile active, cấu hình có hiệu lực và output thật.
11. **Đã giữ khả năng rollback chưa?** Cần có cách trở lại cấu hình ổn định nếu profile mới làm mất log hoặc tăng tải.
12. **Có tài liệu vận hành không?** Ghi rõ cách bật chẩn đoán tạm thời mà không phải sửa ứng dụng và cách tắt sau khi xử lý.

**Kết luận:** Logback cho phép cấu hình theo môi trường bằng property, file cấu hình và rule logger/appender. Trong **ứng dụng Spring Boot**, `logback-spring.xml` mở rộng thêm `springProfile` và `springProperty` để điều kiện hóa cấu hình theo Spring Environment. Để cấu hình đáng tin cậy, cần tách rõ nhãn môi trường và mức log thực sự, giữ tên logger nhất quán, kiểm thử effective level và output, đồng thời bảo vệ dữ liệu ở mọi profile.