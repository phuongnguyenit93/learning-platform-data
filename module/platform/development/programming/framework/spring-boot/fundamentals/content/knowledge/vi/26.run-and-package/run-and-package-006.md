# `java -jar`, JVM system property và tham số ứng dụng

Một ứng dụng Spring Boot sau khi được đóng gói thành **executable JAR** thường có thể khởi động bằng lệnh:

```bash
java -jar order-service.jar
```

Trong môi trường thực tế, lệnh chạy hiếm khi chỉ có một dòng đơn giản. Bạn có thể cần chọn Spring profile, thay cổng HTTP, giới hạn heap JVM, chỉ định vị trí cấu hình hoặc truyền một chế độ xử lý batch:

```bash
java -Xms256m -Xmx768m \
  -Dapp.instance=order-a \
  -jar order-service.jar \
  --spring.profiles.active=prod \
  --server.port=8085 \
  --app.startup-mode=serve
```

Trong lệnh này có **ba loại thông tin khác nhau**:

1. **Tùy chọn JVM/Java launcher** như `-Xmx768m` và `-Dapp.instance=order-a`.
2. **Tùy chọn chọn file chương trình** là `-jar order-service.jar`.
3. **Tham số ứng dụng** đứng sau tên JAR như `--spring.profiles.active=prod` và `--server.port=8085`.

Nhầm lẫn vị trí của các thành phần có thể khiến ứng dụng không khởi động, profile không được chọn, hoặc một property được truyền nhưng không được Spring Boot sử dụng. Bài học này giải thích đầy đủ cách Java launcher phân tích lệnh, cách Spring Boot tiếp nhận cấu hình, thứ tự ưu tiên, cách đọc tham số trong Java và cách chẩn đoán những lỗi thường gặp.

> **Quy tắc quan trọng nhất:** tùy chọn dành cho JVM đặt **trước** `-jar`; tham số dành cho ứng dụng đặt **sau** tên JAR.

## 1. Đọc đúng cấu trúc lệnh chạy

Cấu trúc tổng quát:

```text
java [JVM / launcher options] -jar <executable-jar> [application arguments]
```

Ví dụ:

```bash
java -Xmx512m -Dserver.port=8081 -jar build/libs/demo.jar --app.mode=import input.csv
```

Phân tách:

```text
java
 |
 +-- -Xmx512m               Tùy chọn JVM: giới hạn heap
 |
 +-- -Dserver.port=8081     Java system property
 |
 +-- -jar                   Chọn chế độ chạy executable JAR
 |
 +-- build/libs/demo.jar    Đường dẫn file JAR
 |
 +-- --app.mode=import      Spring Boot command-line option
 |
 +-- input.csv              Non-option application argument
```

### 1.1. Bảng vị trí tham số

| Cú pháp | Ai tiếp nhận? | Vị trí đúng | Ví dụ |
| --- | --- | --- | --- |
| `-Xmx` | JVM | Trước `-jar` | `-Xmx512m` |
| `-Xms` | JVM | Trước `-jar` | `-Xms256m` |
| `-Dname=value` | Java launcher/JVM system properties | Trước `-jar` | `-Dapp.mode=batch` |
| `-XX:...` | JVM | Trước `-jar` | `-XX:MaxRAMPercentage=70` |
| `-jar` | Java launcher | Trước tên JAR | `-jar app.jar` |
| `--name=value` | Tham số chương trình, Spring Boot có thể đưa vào `Environment` | Sau tên JAR | `--server.port=9090` |
| `--name` | Application option không có value | Sau tên JAR | `--debug` |
| `file.csv` | Tham số chương trình thông thường | Sau tên JAR | `input.csv` |

**Không có một cơ chế chung tự động biến mọi đối số sau tên JAR thành tùy chọn JVM.** Từ sau tên JAR, Java truyền các chuỗi còn lại vào `main(String[] args)` của ứng dụng.

### 1.2. Ví dụ đúng

```bash
java -Dspring.profiles.active=dev -jar app.jar
```

```bash
java -jar app.jar --spring.profiles.active=dev
```

Hai cách trên đều có thể kích hoạt Spring profile `dev` trong một ứng dụng Spring Boot theo cấu hình mặc định, nhưng chúng đi vào Spring `Environment` từ **hai property sources khác nhau**.

### 1.3. Ví dụ sai thứ tự

```bash
java -jar app.jar -Dspring.profiles.active=dev
```

Ở vị trí này, `-Dspring.profiles.active=dev` chỉ là **một application argument**. Nó không được Java launcher xử lý như JVM system property. Hơn nữa, Spring Boot command-line property parser thường nhận option theo cú pháp `--key=value`, không tự coi chuỗi `-D...` ở sau JAR là Spring configuration property.

```bash
java --server.port=9090 -jar app.jar
```

Ở vị trí này, `--server.port=9090` bị đưa cho Java launcher thay vì ứng dụng. Java launcher có thể báo **Unrecognized option** và JVM không khởi động ứng dụng.

## 2. `java -jar` thực sự làm gì?

`java` là chương trình khởi động Java do JDK/JRE cung cấp. Tùy chọn `-jar` yêu cầu Java launcher đọc một file JAR có metadata đủ để xác định **main class** và chuyển quyền chạy vào chương trình bên trong.

```bash
java -jar app.jar
```

Điều kiện cơ bản:

- Máy có Java runtime phù hợp.
- Đường dẫn `app.jar` tồn tại và tiến trình có quyền đọc.
- JAR có manifest hoặc cơ chế packaging tương thích với chạy `-jar`.
- Bytecode và thư viện tương thích với phiên bản Java đang sử dụng.
- Những tài nguyên, cấu hình và dependency runtime cần thiết đã sẵn sàng.

### 2.1. JAR thông thường không chắc là executable JAR

Một file JAR có thể chỉ chứa class/resource của thư viện mà không có entry point:

```text
library.jar
  com/example/Utils.class
  META-INF/MANIFEST.MF
```

Không phải mọi file có đuôi `.jar` đều chạy được bằng:

```bash
java -jar library.jar
```

Nếu manifest không có `Main-Class` thích hợp, launcher có thể báo:

```text
no main manifest attribute, in library.jar
```

Đây là vấn đề **đóng gói JAR**, không phải lỗi `server.port` hoặc `spring.profiles.active`.

### 2.2. Executable JAR của Spring Boot

Khi sử dụng Spring Boot Maven Plugin hoặc Gradle Boot Plugin để tạo executable JAR, phần đóng gói thường bao gồm:

```text
order-service.jar
├── META-INF/
│   └── MANIFEST.MF
├── BOOT-INF/
│   ├── classes/
│   │   └── com/example/orders/OrdersApplication.class
│   └── lib/
│       ├── spring-boot-...jar
│       └── ...
└── org/springframework/boot/loader/...
```

Đây là cấu trúc khái niệm thường thấy ở executable JAR, không phải liệt kê đầy đủ mọi entry hoặc cam kết rằng mọi phiên bản có cùng tên package launcher.

Spring Boot loader biết cách nạp classes và dependency JAR bên trong cấu trúc được đóng gói. Vì vậy, bạn có thể chạy:

```bash
java -jar order-service.jar
```

mà không phải viết một classpath dài liệt kê từng dependency.

### 2.3. `Main-Class` và `Start-Class`

Executable JAR của Spring Boot thường dùng metadata trong manifest tương tự:

```text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.orders.OrdersApplication
```

Tên `Main-Class` thực tế thay đổi giữa các dòng Spring Boot; ví dụ ở một số phiên bản cũ, package loader khác với ví dụ trên.

Ý nghĩa:

- `Main-Class` là điểm Java launcher gọi trước.
- Spring Boot launcher tìm và chạy `Start-Class` là application class của bạn.
- Application class thường chứa `public static void main(String[] args)`.

Bạn không cần tự chỉnh manifest thủ công khi Spring Boot build plugin đã được cấu hình đúng.

## 3. Tạo executable JAR trước khi chạy

### 3.1. Với Gradle

Trong dự án đã sử dụng Spring Boot Gradle plugin:

```bash
./gradlew bootJar
```

Trên Windows:

```powershell
.\gradlew.bat bootJar
```

Artifact thường được ghi vào:

```text
build/libs/
```

Ví dụ:

```text
build/libs/order-service-1.0.0.jar
```

Tên file phụ thuộc cấu hình project và task output. Hãy sử dụng tên file **thực sự được tạo ra**, thay vì mặc định mọi project đều có `app.jar`.

### 3.2. Với Maven

Một dự án dùng `spring-boot-maven-plugin` với goal `repackage` được cấu hình phù hợp có thể build bằng:

```bash
./mvnw package
```

Trên Windows:

```powershell
.\mvnw.cmd package
```

Artifact thường nằm ở:

```text
target/order-service-1.0.0.jar
```

Nếu build chưa cấu hình Spring Boot repackage, `mvn package` có thể chỉ tạo JAR thông thường không mang đầy đủ dependency runtime để chạy bằng `java -jar`.

### 3.3. Phân biệt `jar`, `bootJar` và `repackage`

| Khái niệm | Vai trò |
| --- | --- |
| Gradle `jar` | Task đóng gói JAR thông thường |
| Gradle `bootJar` | Task tạo executable Spring Boot JAR |
| Maven `package` | Lifecycle phase tạo artifact theo plugin configuration |
| Spring Boot Maven `repackage` | Đóng gói lại artifact thành executable Spring Boot archive |

Không nên kết luận một artifact là executable chỉ từ phần mở rộng `.jar`.

### 3.4. Một ví dụ lệnh chạy hoàn chỉnh

Giả sử build tạo:

```text
build/libs/order-service-1.0.0.jar
```

Chạy:

```bash
java -jar build/libs/order-service-1.0.0.jar
```

Kèm cấu hình:

```bash
java -Xmx512m \
  -Dapp.instance=local-01 \
  -jar build/libs/order-service-1.0.0.jar \
  --spring.profiles.active=dev \
  --server.port=8081
```

Các option phía trước `-jar` được Java launcher xử lý. Các option phía sau JAR đi vào `main(String[] args)` và có thể được Spring Boot sử dụng.

## 4. JVM system property là gì?

**Java system properties** là tập key–value gắn với một tiến trình JVM. Một cách phổ biến để thiết lập chúng ngay khi khởi động:

```bash
java -Dapp.mode=batch -jar app.jar
```

Trong Java:

```java
String mode = System.getProperty("app.mode");
```

Nếu property đã được thiết lập đúng, `mode` có giá trị:

```text
batch
```

### 4.1. Cú pháp `-D`

```text
-D<property-name>=<property-value>
```

Ví dụ:

```bash
java -Dapp.instance=worker-02 -Dapp.feature.enabled=true -jar app.jar
```

Mỗi property là một JVM launcher argument riêng:

```text
-Dapp.instance=worker-02
-Dapp.feature.enabled=true
```

Chúng đều phải đặt trước `-jar`.

### 4.2. System property không phải biến môi trường

So sánh:

```java
System.getProperty("app.mode")
```

với:

```java
System.getenv("APP_MODE")
```

Hai API đọc hai nguồn khác nhau.

| Nguồn | Cách thiết lập | Java đọc bằng |
| --- | --- | --- |
| JVM system property | `-Dapp.mode=batch` | `System.getProperty("app.mode")` |
| OS environment variable | `APP_MODE=batch` | `System.getenv("APP_MODE")` |
| Spring Boot application argument | `--app.mode=batch` sau JAR | `ApplicationArguments`, hoặc `Environment` khi được bật |

Spring Boot có thể **kết hợp cả ba** thành các property sources để cấu hình ứng dụng, nhưng điều đó không làm `System.getProperty()` và `System.getenv()` trở thành cùng một API.

### 4.3. Đọc system property với giá trị mặc định

```java
String instanceName =
        System.getProperty("app.instance", "unnamed");
```

Giá trị `unnamed` được dùng khi system property không tồn tại.

Đây là logic Java thuần, không cần application context.

### 4.4. Có thể đặt system property bằng code không?

Java hỗ trợ:

```java
System.setProperty("app.mode", "batch");
```

Nhưng nếu cần thay một Spring Boot configuration property, hãy đặt giá trị **trước giai đoạn Spring Boot xử lý cấu hình tương ứng**. Thay system property muộn sau khi context đã refresh không tự động bind lại mọi bean hoặc khởi động lại web server.

Trong phần lớn ứng dụng, nên cấu hình từ CLI, environment hoặc Config Data thay vì thay đổi system properties tùy tiện trong business code.

## 5. JVM options khác với Java system properties

Tất cả các option sau thường đứng trước `-jar`, nhưng không có cùng tác dụng:

```bash
java -Xms256m -Xmx1g -Dapp.mode=batch -jar app.jar
```

### 5.1. `-Xms` và `-Xmx`

Ví dụ:

```text
-Xms256m
-Xmx1g
```

Ý nghĩa:

- `-Xms`: mức kích thước heap khởi tạo theo JVM option tương ứng.
- `-Xmx`: mức heap tối đa JVM được phép sử dụng.

Các option này không phải Spring Boot properties. Chúng không được dùng như:

```bash
java -jar app.jar --Xmx1g
```

và không thể đọc bằng:

```java
System.getProperty("Xmx")
```

để tìm lại heap limit.

### 5.2. `-XX` và những JVM flags khác

Ví dụ:

```bash
java -XX:MaxRAMPercentage=70 -jar app.jar
```

Một số `-XX` options phụ thuộc JVM vendor và Java version. Hãy kiểm tra runtime thực tế, đặc biệt khi chạy trong container.

Không phải mọi JVM option đều có thể kết hợp tùy ý; ví dụ, giới hạn heap cụ thể bằng `-Xmx` có thể thay đổi cách JVM sử dụng các thiết lập dựa trên phần trăm bộ nhớ.

### 5.3. Đừng nhầm `--debug` với JVM debugger

Trong Spring Boot:

```bash
java -jar app.jar --debug
```

`--debug` là một Spring Boot application option thường dùng để tăng thông tin chẩn đoán startup, trong đó có Conditions Evaluation Report.

Nó **không tương đương** việc bật Java remote debugger/JDWP. Các tùy chọn debugger thuộc JVM và phải được cấu hình riêng, với biện pháp bảo vệ cổng debug phù hợp.

## 6. Tham số ứng dụng là gì?

Khi Java launcher đã đọc `-jar` và đường dẫn JAR, phần còn lại được chuyển cho:

```java
public static void main(String[] args)
```

Ví dụ:

```bash
java -jar app.jar --app.mode=import customers.csv
```

Các chuỗi của `args` về mặt khái niệm:

```text
args[0] = "--app.mode=import"
args[1] = "customers.csv"
```

Chúng là **application arguments**, không phải JVM system properties.

### 6.1. Spring Boot static `run(...)` nhận chính các tham số này

Một class khởi động:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

`SpringApplication.run(..., args)` nhận các chuỗi mà Java đã truyền vào `main`.

Bạn không cần tự tách `--server.port=8081` bằng code để Spring Boot biết cổng HTTP trong thiết lập mặc định.

### 6.2. Hai nhóm tham số bên trong ứng dụng

Spring Boot phân biệt:

- **Option arguments**: bắt đầu bằng `--`.
- **Non-option arguments**: những chuỗi còn lại.

Ví dụ:

```bash
java -jar app.jar --app.mode=import --app.dry-run=true input.csv
```

Khi phân tích bằng `ApplicationArguments`:

```text
Option:
  app.mode = import
  app.dry-run = true

Non-option:
  input.csv
```

### 6.3. Nên dùng `--name=value` cho option có giá trị

Đúng:

```bash
java -jar app.jar --app.mode=import
```

Không nên mặc định hai chuỗi sau sẽ được Spring Boot xem là một cặp option–value:

```bash
java -jar app.jar --app.mode import
```

Trong cơ chế parsing option mặc định của Spring Boot, dạng rõ ràng là `--app.mode=import`; chuỗi `import` đứng riêng có thể được phân loại thành non-option argument.

### 6.4. Option không có value

Ví dụ:

```bash
java -jar app.jar --debug
```

Spring Boot nhận diện `debug` như một option không có giá trị tường minh.

Nhưng với **boolean property tùy chỉnh**, để binding rõ ràng nên dùng:

```bash
java -jar app.jar --app.dry-run=true
```

thay vì giả định mọi binder sẽ hiểu một option rỗng như Boolean `true`.

## 7. `ApplicationArguments`: đọc tham số theo kiểu Spring Boot

Spring Boot cung cấp interface:

```java
org.springframework.boot.ApplicationArguments
```

Nó hỗ trợ:

```java
args.containsOption("app.mode")
args.getOptionValues("app.mode")
args.getNonOptionArgs()
args.getOptionNames()
args.getSourceArgs()
```

### 7.1. Một `ApplicationRunner` hoàn chỉnh

```java
package com.example.demo.startup;

import java.util.List;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class ImportArgumentsRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        if (args.containsOption("app.mode")) {
            List<String> modes =
                    args.getOptionValues("app.mode");

            System.out.println("Modes: " + modes);
        }

        List<String> files = args.getNonOptionArgs();
        System.out.println("Input file count: " + files.size());
    }
}
```

Chạy:

```bash
java -jar app.jar --app.mode=import input.csv
```

Kết quả minh họa:

```text
Modes: [import]
Input file count: 1
```

Ví dụ cố ý chỉ in số lượng file, không in mọi argument nguyên giá trị; đối số CLI có thể chứa đường dẫn nhạy cảm hoặc secret nếu người vận hành truyền sai cách.

### 7.2. `getOptionValues()` có thể trả về gì?

Với option không tồn tại:

```java
args.getOptionValues("missing")
```

thường trả về `null`.

Với option hiện diện nhưng không có value, như `--debug`, kết quả có thể là một danh sách rỗng.

Với `--app.mode=import`, kết quả là danh sách chứa giá trị `import`.

Khi viết code, hãy kiểm tra option tồn tại trước, đồng thời xử lý trường hợp danh sách rỗng hoặc nhiều giá trị nếu điều đó ảnh hưởng nghiệp vụ.

### 7.3. `ApplicationArguments` khác với `Environment`

`ApplicationArguments` biểu diễn các đối số dòng lệnh.

`Environment` biểu diễn cấu hình kết hợp từ nhiều property sources.

Nếu một property đến từ:

```properties
app.mode=serve
```

trong `application.properties`, `Environment` có thể đọc được nó, nhưng `ApplicationArguments.containsOption("app.mode")` không tự trở thành `true`.

`ApplicationArguments` chỉ biết những chuỗi đã được truyền vào tiến trình qua command line.

## 8. `CommandLineRunner`: nhận chuỗi đối số thô

Ngoài `ApplicationRunner`, Spring Boot còn cung cấp:

```java
org.springframework.boot.CommandLineRunner
```

Ví dụ:

```java
package com.example.demo.startup;

import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

@Component
public class RawArgumentsRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println(
                "Argument count: " + args.length
        );
    }
}
```

`CommandLineRunner` nhận chính các chuỗi application arguments theo thứ tự được truyền vào chương trình, không chuyển chúng thành option model.

### 8.1. So sánh hai runner

| Tiêu chí | `ApplicationRunner` | `CommandLineRunner` |
| --- | --- | --- |
| Tham số | `ApplicationArguments` | `String... args` |
| Phân biệt option/non-option | Có | Bạn tự xử lý |
| Đọc giá trị `--name=value` | Qua `getOptionValues()` | Phải tự parse nếu cần |
| Giai đoạn được gọi | Sau context refresh, trước `ApplicationReadyEvent` | Cùng giai đoạn |
| Hữu ích cho | CLI mode, batch option, command configuration | Xử lý các đối số thô hoặc ứng dụng đơn giản |

Spring Boot sắp xếp các runner được hỗ trợ theo `@Order` hoặc `Ordered` khi có nhiều runner. Không nên dựa vào thứ tự ngẫu nhiên nếu các bước startup có dependency nghiệp vụ.

### 8.2. Runner thất bại thì sao?

Nếu runner ném exception không được xử lý, Spring Boot có thể xem startup thất bại, không đi tới `ApplicationReadyEvent` trong luồng thành công.

Một runner không nên chạy vòng lặp vô hạn chỉ vì ứng dụng cần xử lý công việc nền. Dùng cơ chế lifecycle, scheduler, queue consumer hoặc worker có quản lý phù hợp với mục tiêu thực tế.

## 9. Spring Boot biến command-line options thành configuration properties

Trong thiết lập mặc định, Spring Boot thêm các option kiểu:

```text
--server.port=8081
--spring.profiles.active=dev
--app.mode=import
```

vào một command-line `PropertySource` trong `Environment`.

Vì vậy:

```bash
java -jar app.jar --server.port=8081
```

có thể tương đương về **giá trị cấu hình đọc được từ Spring** với:

```properties
server.port=8081
```

trong file cấu hình, nhưng hai nguồn có độ ưu tiên khác nhau.

### 9.1. Đọc từ `Environment`

```java
package com.example.demo.startup;

import org.springframework.core.env.Environment;
import org.springframework.stereotype.Service;

@Service
public class PortSettings {

    private final Environment environment;

    public PortSettings(Environment environment) {
        this.environment = environment;
    }

    public int configuredPort() {
        return environment.getProperty(
                "server.port",
                Integer.class,
                8080
        );
    }
}
```

Giá trị trả về là property mà Environment resolve được theo các nguồn hiện diện. Nếu dùng `server.port=0` để yêu cầu cổng ngẫu nhiên, `Environment.getProperty("server.port")` vẫn có thể là `0` dù embedded server đã được hệ điều hành cấp một cổng thực tế khác.

Để xác định cổng web server thực tế, có thể sử dụng web server initialized event hoặc công cụ dành cho integration testing.

### 9.2. Đọc bằng `@Value`

```java
@Service
public class ModeService {

    private final String mode;

    public ModeService(
            @Value("${app.mode:serve}") String mode) {
        this.mode = mode;
    }

    public String mode() {
        return mode;
    }
}
```

Nếu không có `app.mode`, default `serve` được dùng theo placeholder syntax.

### 9.3. Đọc bằng `@ConfigurationProperties`

Với nhiều property cùng nhóm, nên dùng typed binding:

```java
package com.example.demo.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.import")
public record ImportProperties(
        boolean dryRun,
        int batchSize,
        Duration timeout
) {
}
```

Một lệnh chạy:

```bash
java -jar app.jar \
  --app.import.dry-run=true \
  --app.import.batch-size=100 \
  --app.import.timeout=15s
```

Spring Boot có thể bind các giá trị vào record thông qua configuration properties binding nếu class được đăng ký trong context, ví dụ bằng `@ConfigurationPropertiesScan` ở application class.

Đây là cơ chế Spring Boot binding, khác với việc tự gọi `System.getProperty()` để parse từng chuỗi.

## 10. `-D` và `--` khác nhau thế nào?

Đây là phần dễ nhầm nhất.

### 10.1. JVM system property

```bash
java -Dapp.mode=batch -jar app.jar
```

Java launcher đặt `app.mode=batch` vào JVM system properties.

Đọc bằng Java:

```java
System.getProperty("app.mode")
```

Spring Boot cũng có thể đọc `app.mode` từ `Environment` vì JVM system properties là một property source thường được Spring tích hợp.

### 10.2. Spring Boot command-line property

```bash
java -jar app.jar --app.mode=batch
```

Java launcher truyền chuỗi `--app.mode=batch` vào `main(args)`.

Spring Boot nhận nó như command-line option và có thể cung cấp giá trị qua `Environment`.

Nhưng:

```java
System.getProperty("app.mode")
```

**không tự có** giá trị `batch` chỉ vì bạn truyền `--app.mode=batch`.

### 10.3. Bảng so sánh

| Câu hỏi | `-Dapp.mode=batch` trước JAR | `--app.mode=batch` sau JAR |
| --- | --- | --- |
| Được JVM launcher nhận trực tiếp? | Có | Không; được truyền cho application |
| Xuất hiện trong `System.getProperty("app.mode")`? | Có | Không tự động |
| Xuất hiện trong `ApplicationArguments`? | Không, nếu chỉ truyền `-D` | Có |
| Có thể xuất hiện trong Spring `Environment`? | Có | Có, theo cấu hình mặc định |
| Dùng để cấu hình Spring Boot? | Được | Được |
| Mức ưu tiên thông thường so với nhau | Thấp hơn command-line properties | Cao hơn JVM system properties |

### 10.4. Hai cách có cùng tên property nhưng không cùng giá trị

```bash
java -Dapp.mode=serve -jar app.jar --app.mode=import
```

Trong JVM:

```java
System.getProperty("app.mode")  // "serve"
```

Trong Spring `Environment` theo mặc định:

```java
environment.getProperty("app.mode")  // "import"
```

Trong `ApplicationArguments`:

```java
args.getOptionValues("app.mode")  // ["import"]
```

Lý do: command-line property source của Spring Boot thường có độ ưu tiên cao hơn Java system property source. Còn `System.getProperty()` đọc riêng tập JVM system properties.

**Không nên lẫn lộn API đọc một nguồn cụ thể với API resolve cấu hình nhiều nguồn.**

## 11. Thứ tự ưu tiên cấu hình

Spring Boot externalized configuration không chỉ có hai nguồn từ `-D` và `--`.

Một ứng dụng có thể nhận property từ:

- Default properties của `SpringApplication`.
- File `application.properties` / `application.yml`.
- File profile-specific như `application-prod.yml`.
- Biến môi trường của hệ điều hành.
- Java system properties (`-D...`).
- JSON application properties trong cơ chế tương ứng.
- Command-line application arguments (`--...`).
- Property sources dành riêng cho test hoặc môi trường phát triển.

### 11.1. Thứ tự khái quát các nguồn phổ biến

Trong một Spring Boot application điển hình, đối với một key trùng nhau và không có nguồn test hoặc custom source đặc biệt ghi đè, có thể hình dung từ **thấp đến cao**:

```text
Default properties
        |
        v
Config Data: application.*, profile documents
        |
        v
OS environment variables
        |
        v
JVM system properties (-D...)
        |
        v
Spring Boot command-line properties (--...)
```

Đây là sơ đồ rút gọn; Spring Boot còn nhiều property sources với vị trí ưu tiên cụ thể. Nếu một trường hợp có `SPRING_APPLICATION_JSON`, test properties, import hoặc property source tùy chỉnh, hãy tham khảo thứ tự đầy đủ của phiên bản đang dùng.

### 11.2. Ví dụ cùng một key ở nhiều nguồn

File `application.properties`:

```properties
server.port=8080
```

Biến môi trường:

```text
SERVER_PORT=8081
```

Lệnh chạy:

```bash
java -Dserver.port=8082 \
  -jar app.jar \
  --server.port=8083
```

Với thiết lập Spring Boot mặc định và không có nguồn cao hơn, property hiệu lực là:

```text
server.port=8083
```

Do option `--server.port=8083` có độ ưu tiên cao hơn các nguồn còn lại trong ví dụ.

### 11.3. Không phải mọi giá trị cấu hình đều ảnh hưởng runtime tức thì

Spring Boot thường bind nhiều property khi tạo bean hoặc khởi động server. Nếu sau startup bạn thay một environment variable của hệ điều hành, JVM đang chạy **không tự động nạp lại** và tái cấu hình toàn bộ bean.

Nếu cần cấu hình động, phải sử dụng một cơ chế refresh/dynamic configuration được thiết kế riêng. Không suy luận rằng thay giá trị ngoài tiến trình sẽ tự làm web server đổi cổng.

## 12. `setAddCommandLineProperties(false)` thay đổi điều gì?

Spring Boot cho phép tạo `SpringApplication` instance để điều khiển việc chuyển command-line options vào `Environment`.

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(DemoApplication.class);

        application.setAddCommandLineProperties(false);
        application.run(args);
    }
}
```

Khi đặt `false`, Spring Boot không bổ sung các option command line vào property sources theo cơ chế mặc định.

Vì vậy:

```bash
java -jar app.jar --app.mode=import
```

vẫn cung cấp argument cho:

```java
ApplicationArguments
```

nhưng không còn bảo đảm:

```java
environment.getProperty("app.mode")
```

lấy được `import` từ command-line option.

### 12.1. Có ảnh hưởng tới `--spring.profiles.active` không?

Có thể. Nếu option command line bị loại khỏi `Environment`, giá trị:

```text
--spring.profiles.active=dev
```

không còn được xử lý như một property source để chọn profile theo cách mặc định nữa.

**Chỉ tắt command-line property source khi bạn thực sự muốn Spring Boot không dùng `--...` để cấu hình môi trường.**

### 12.2. Có ảnh hưởng tới `-D` không?

`setAddCommandLineProperties(false)` không có mục đích loại bỏ JVM system properties. System properties vẫn là nguồn riêng trong Spring Environment theo cơ chế thông thường.

Ví dụ:

```bash
java -Dapp.mode=batch -jar app.jar
```

vẫn tạo system property, dù bạn không cho Spring thêm application options vào `Environment`.

## 13. Kích hoạt Spring profile bằng CLI

Profile thường quyết định file cấu hình và bean nào được áp dụng.

Một ứng dụng có:

```text
src/main/resources/
├── application.yml
├── application-dev.yml
└── application-prod.yml
```

`application.yml`:

```yaml
spring:
  application:
    name: order-service

server:
  port: 8080
```

`application-dev.yml`:

```yaml
server:
  port: 8081

logging:
  level:
    com.example.orders: DEBUG
```

`application-prod.yml`:

```yaml
logging:
  level:
    root: INFO
```

### 13.1. Chọn `dev` bằng application argument

```bash
java -jar app.jar --spring.profiles.active=dev
```

### 13.2. Chọn `dev` bằng JVM system property

```bash
java -Dspring.profiles.active=dev -jar app.jar
```

### 13.3. Chọn bằng environment variable

Trong Bash:

```bash
SPRING_PROFILES_ACTIVE=dev java -jar app.jar
```

Trong Windows PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = 'dev'
java -jar app.jar
```

Các cách trên đều có thể khiến Spring Boot kích hoạt profile `dev`, với điều kiện nguồn cấu hình không bị nguồn ưu tiên cao hơn thay thế.

### 13.4. Nhiều profile

```bash
java -jar app.jar --spring.profiles.active=prod,cloud
```

Spring Boot có thể xét đồng thời những profile này. Nếu nhiều file/document cùng ghi một key, cần xác định quy tắc precedence giữa những nguồn được nạp và thứ tự profile phù hợp.

### 13.5. Profile không phải bí mật

Chọn `prod` không tự bật bảo mật, không tạo secret và không phân quyền dữ liệu. Profile chỉ tham gia lựa chọn cấu hình và điều kiện bean.

Không hard-code credential production vào command line hoặc file profile chỉ vì đang chọn profile `prod`.

## 14. Tham số `server.port` trong ứng dụng web

Một ví dụ dễ quan sát:

```bash
java -jar app.jar --server.port=9090
```

Nếu ứng dụng là Spring Boot web application dùng embedded server phù hợp, Spring Boot thường cấu hình server lắng nghe ở cổng 9090.

Với system property:

```bash
java -Dserver.port=9090 -jar app.jar
```

cũng có thể đạt cùng giá trị cấu hình nếu không có nguồn ưu tiên cao hơn ghi đè.

### 14.1. Nếu ứng dụng không phải web application?

Một ứng dụng chạy với:

```java
application.setWebApplicationType(WebApplicationType.NONE);
```

không tự có embedded HTTP server để dùng `server.port`. Truyền:

```text
--server.port=9090
```

không biến một ứng dụng non-web thành web application.

Property chỉ có tác dụng khi component hoặc auto-configuration phù hợp thực sự sử dụng nó.

### 14.2. Dùng cổng ngẫu nhiên

```bash
java -jar app.jar --server.port=0
```

Trong trường hợp embedded server hỗ trợ, cổng `0` yêu cầu hệ điều hành chọn một cổng khả dụng.

Không dùng `Environment.getProperty("server.port")` làm nguồn chắc chắn để biết cổng thực tế khi property được đặt bằng `0`; cần xem web server runtime hoặc web server initialized event.

## 15. Biến môi trường và tên property

Trong môi trường container hoặc orchestrator, biến môi trường thường tiện hơn việc sửa lệnh `java -jar` thủ công:

```text
SERVER_PORT=8081
SPRING_PROFILES_ACTIVE=prod
```

Spring Boot hỗ trợ quy tắc relaxed binding để chuyển những tên environment variable phù hợp thành property names.

Ví dụ:

```properties
app.import.batch-size=100
```

Theo quy tắc canonical-to-environment được Spring Boot dùng cho configuration binding, tên environment variable phù hợp có thể là:

```text
APP_IMPORT_BATCHSIZE=100
```

Với canonical property name dạng kebab-case, quy tắc tổng quát thường là thay dấu chấm bằng `_`, loại dấu gạch ngang `-`, rồi chuyển thành chữ hoa.

### 15.1. Không tự suy luận mọi tên biến đều tương đương

Ví dụ:

```text
APP_IMPORT_BATCH_SIZE
```

có thể được hiểu khác với `app.import.batch-size` tùy quy tắc mapping/binding. Khi triển khai, hãy sử dụng cách đặt tên được tài liệu Spring Boot của phiên bản đang dùng hướng dẫn và xác nhận bằng binding test.

### 15.2. Environment variable và `System.getenv`

```java
String port = System.getenv("SERVER_PORT");
```

đọc một biến môi trường có tên chính xác `SERVER_PORT`.

Trong khi:

```java
environment.getProperty("server.port")
```

cho Spring cơ hội resolve `server.port` từ nhiều nguồn, trong đó có environment variable theo các quy tắc phù hợp.

Vì vậy, với code nghiệp vụ sử dụng cấu hình Spring Boot, `Environment` hoặc `@ConfigurationProperties` thường linh hoạt hơn việc gọi `System.getenv()` trực tiếp.

## 16. Chỉ định vị trí file cấu hình khi chạy JAR

Spring Boot hỗ trợ Config Data từ những vị trí mặc định và từ các vị trí được chỉ định thêm.

Giả sử deployment:

```text
deploy/
├── order-service.jar
└── config/
    └── application-prod.yml
```

Bạn có thể cung cấp vị trí cấu hình bằng một tham số startup phù hợp.

### 16.1. `spring.config.additional-location`

Ví dụ:

```bash
java -jar order-service.jar \
  --spring.profiles.active=prod \
  --spring.config.additional-location=optional:file:./config/
```

Ý nghĩa:

- `additional-location` bổ sung vị trí tìm Config Data ngoài các vị trí mặc định.
- `file:./config/` là một thư mục tương đối so với working directory.
- Dấu `/` cuối thể hiện đây là thư mục để Spring Boot xét tên file cấu hình.
- `optional:` cho phép vị trí đó không tồn tại mà không làm startup thất bại chỉ vì thiếu location.

### 16.2. Dùng JVM system property

Một cách viết khác:

```bash
java -Dspring.config.additional-location=optional:file:./config/ \
  -jar order-service.jar \
  --spring.profiles.active=prod
```

Những property điều khiển việc tìm Config Data, như `spring.config.name`, `spring.config.location` và `spring.config.additional-location`, cần được cung cấp **đủ sớm** để Spring Boot biết nơi tìm cấu hình.

### 16.3. Phân biệt `location` và `additional-location`

| Property | Mục đích |
| --- | --- |
| `spring.config.location` | Chỉ định các vị trí cấu hình và có thể thay thế những vị trí mặc định |
| `spring.config.additional-location` | Bổ sung vị trí vào danh sách tìm kiếm mặc định |
| `spring.config.name` | Thay tên logic mặc định `application` |
| `spring.config.import` | Nhập thêm nguồn Config Data từ cấu hình đang được đọc |

Nếu thay hoàn toàn locations mà quên các vị trí mặc định, ứng dụng có thể không nạp file cấu hình bạn nghĩ là vẫn hiện diện.

### 16.4. Working directory quan trọng

Lệnh:

```bash
java -jar /opt/apps/order-service.jar \
  --spring.config.additional-location=optional:file:./config/
```

giải quyết `./config/` dựa trên **working directory hiện tại**, không nhất thiết dựa trên thư mục chứa JAR.

Nếu service manager chạy tiến trình ở `/var/run`, `./config/` có thể tham chiếu tới đường dẫn khác với khi bạn chạy lệnh từ `/opt/apps`.

Khi triển khai, xác định working directory rõ ràng hoặc sử dụng đường dẫn tuyệt đối phù hợp.

## 17. Khi nào dùng `-D`, khi nào dùng `--`?

| Nhu cầu | Lựa chọn thường hợp lý |
| --- | --- |
| Điều chỉnh heap JVM | `-Xms`, `-Xmx`, `-XX` trước JAR |
| Thiết lập Java system property cho thư viện Java | `-Dname=value` trước JAR |
| Ghi đè Spring Boot property cho một lần chạy | `--name=value` sau JAR |
| Đặt active profile khi chạy ứng dụng | `--spring.profiles.active=...`, `-D...` hoặc environment |
| Truyền file input cho batch CLI | Non-option application argument |
| Đọc option từ `ApplicationArguments` | `--name=value` |
| Sử dụng typed Spring configuration binding | Property sources + `@ConfigurationProperties` |
| Cấu hình từ orchestrator mà không sửa lệnh JAR | Environment variables hoặc hệ thống cấu hình phù hợp |

### 17.1. Một nguyên tắc thiết kế

Nếu giá trị là **cấu hình của ứng dụng Spring Boot** (timeout, feature flag, endpoint), có thể dùng `--` hoặc externalized configuration.

Nếu giá trị là **tùy chọn điều hành JVM** (heap, garbage collector hoặc JVM system property cần cho runtime), cấu hình trước `-jar`.

Nếu giá trị là **đối số của một lệnh nghiệp vụ**, như tên file đầu vào hoặc chế độ import, `ApplicationArguments` là API phù hợp.

Không cần ép mọi thông tin vào một nguồn duy nhất.

## 18. Ví dụ tổng hợp: ứng dụng vừa có cấu hình vừa có CLI mode

Giả sử một ứng dụng có thể chạy web server hoặc thực hiện tác vụ import.

### 18.1. Application class

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 18.2. Cấu hình mặc định

`application.properties`:

```properties
spring.application.name=demo-runner
app.import.batch-size=100
app.import.dry-run=false
app.import.timeout=20s
```

### 18.3. Typed configuration

`ImportProperties.java`:

```java
package com.example.demo.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.import")
public record ImportProperties(
        int batchSize,
        boolean dryRun,
        Duration timeout
) {
}
```

### 18.4. Runner xử lý tham số

`ImportRunner.java`:

```java
package com.example.demo.startup;

import com.example.demo.config.ImportProperties;
import java.util.List;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class ImportRunner implements ApplicationRunner {

    private final ImportProperties properties;

    public ImportRunner(ImportProperties properties) {
        this.properties = properties;
    }

    @Override
    public void run(ApplicationArguments args) {
        List<String> modes = args.getOptionValues("app.mode");

        String mode =
                modes == null || modes.isEmpty()
                        ? "serve"
                        : modes.get(0);

        System.out.println("Selected mode: " + mode);

        if ("import".equals(mode)) {
            List<String> files = args.getNonOptionArgs();

            if (files.size() != 1) {
                throw new IllegalArgumentException(
                        "Import mode requires one input file"
                );
            }

            String inputFile = files.get(0);

            System.out.println(
                    "Import started, batchSize=" +
                    properties.batchSize() +
                    ", dryRun=" +
                    properties.dryRun() +
                    ", timeout=" +
                    properties.timeout()
            );

            // Gọi import service với inputFile trong ứng dụng thực tế.
            // Không in nguyên file path nếu nó có thể chứa PII/secret.
        }
    }
}
```

Đây là ví dụ phân biệt API. Trong ứng dụng thật, `inputFile` phải được kiểm tra đường dẫn, quyền truy cập và kiểu nội dung trước khi mở.

Ngoài ra, ví dụ **không tự tắt web server trong import mode**. Nếu muốn import chạy một lần rồi kết thúc tiến trình, hãy thiết kế startup mode và lifecycle rõ ràng, ví dụ chạy với `WebApplicationType.NONE` theo cách phù hợp hoặc tách ứng dụng batch khỏi web service.

### 18.5. Lệnh chạy nhập dữ liệu

```bash
java -Xmx512m \
  -Dapp.instance=import-worker-01 \
  -jar demo-runner.jar \
  --app.mode=import \
  --app.import.batch-size=250 \
  --app.import.dry-run=true \
  --app.import.timeout=30s \
  input.csv
```

Phân tích:

| Thành phần | Nguồn/ý nghĩa |
| --- | --- |
| `-Xmx512m` | JVM heap option |
| `-Dapp.instance=import-worker-01` | JVM system property |
| `--app.mode=import` | Application option, runner đọc từ `ApplicationArguments` |
| `--app.import.batch-size=250` | Spring property để bind vào `ImportProperties` |
| `--app.import.dry-run=true` | Spring Boolean property |
| `--app.import.timeout=30s` | Spring property được convert thành `Duration` |
| `input.csv` | Non-option application argument |

### 18.6. Java và Spring có thể đọc những gì?

Trong ví dụ trên:

```java
System.getProperty("app.instance")  // "import-worker-01"
```

```java
args.getOptionValues("app.mode")    // ["import"]
```

```java
properties.batchSize()             // 250
```

```java
properties.dryRun()                // true
```

```java
properties.timeout()               // PT30S
```

Đây là các giá trị minh họa khi có đủ configuration properties registration và không có lỗi startup.

## 19. Truyền tham số có dấu cách và ký tự đặc biệt

Shell xử lý lệnh **trước khi** Java nhận arguments. Dấu cách, dấu nháy và ký tự điều khiển của shell có thể làm một value bị tách thành nhiều argument.

### 19.1. Bash: Linux/macOS

Ví dụ:

```bash
java '-Dapp.display-name=Order Service' \
  -jar 'build/libs/order-service.jar' \
  '--app.greeting=Hello Team'
```

Các đoạn được quote giúp shell truyền mỗi thành phần làm **một argument**.

Với path chứa dấu cách:

```bash
java -jar '/opt/apps/Order Service/order-service.jar'
```

### 19.2. Windows PowerShell

Ví dụ:

```powershell
java '-Dapp.display-name=Order Service' `
  -jar '.\build\libs\order-service.jar' `
  '--app.greeting=Hello Team'
```

Trong PowerShell, ký tự tiếp dòng là backtick. Backtick phải nằm cuối dòng, không có dấu cách thừa sau nó.

Cú pháp môi trường:

```powershell
$env:SPRING_PROFILES_ACTIVE = 'dev'
java -jar '.\build\libs\order-service.jar'
```

### 19.3. Windows Command Prompt

Ví dụ một dòng:

```bat
java "-Dapp.display-name=Order Service" -jar "C:\Apps\Order Service\order-service.jar" "--app.greeting=Hello Team"
```

Cú pháp quote có thể khác giữa Bash, PowerShell và CMD. Tránh sao chép nguyên lệnh nhiều dòng dùng `\` của Bash vào PowerShell/CMD rồi cho rằng tất cả shell diễn giải giống nhau.

### 19.4. URL và ký tự `&`

Ví dụ URL:

```text
https://example.test/api?mode=full&lang=vi
```

Ký tự `&` có ý nghĩa đặc biệt trong một số shell. Khi truyền giá trị URL ở command line, hãy quote toàn bộ argument:

```bash
java -jar app.jar '--app.partner-url=https://example.test/api?mode=full&lang=vi'
```

Đây là ví dụ cú pháp shell, không có nghĩa một URL chứa token hoặc secret được phép đặt trong process arguments.

## 20. Không truyền secret vào command line nếu có cách an toàn hơn

Ví dụ không nên:

```bash
java -Ddb.password=super-secret -jar app.jar
```

hoặc:

```bash
java -jar app.jar --db.password=super-secret
```

Những giá trị này có thể xuất hiện trong:

- Shell history.
- Process command line hoặc thông tin giám sát tiến trình.
- Diagnostic tools, crash reports hoặc công cụ JVM.
- Deployment scripts và CI/CD logs.
- Nội dung chụp màn hình/terminal output khi điều tra sự cố.

JVM system properties cũng có thể bị đọc bởi code trong cùng process và một số công cụ chẩn đoán tùy quyền.

### 20.1. Dùng secret management phù hợp

Ví dụ property trong file:

```properties
spring.datasource.password=${DB_PASSWORD}
```

Hoặc YAML:

```yaml
spring:
  datasource:
    password: "${DB_PASSWORD}"
```

Sau đó cung cấp secret qua cơ chế quản lý bí mật của môi trường triển khai. Environment variables vẫn cần quyền truy cập và kiểm soát phù hợp; với yêu cầu bảo vệ cao có thể dùng mounted secrets hoặc secrets manager.

**Không in toàn bộ `ApplicationArguments`, `System.getProperties()` hoặc `Environment` vào log**, vì chúng có thể chứa thông tin nhạy cảm.

### 20.2. Không đặt credential trong `--spring.config.location`

Đường dẫn cấu hình có thể không phải secret, nhưng một số URL hoặc location string có thể chứa token hoặc thông tin xác thực.

Không tạo lệnh deploy chứa secret trong URL trừ khi có thiết kế bảo vệ, và tránh ghi nguyên command line vào log vận hành.

## 21. Docker và container: JVM options vẫn phải đúng vị trí

Trong container, quy tắc Java launcher không thay đổi.

Ví dụ Dockerfile dạng khái niệm:

```dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY build/libs/order-service.jar /app/app.jar
ENTRYPOINT ["java", "-Xmx512m", "-jar", "/app/app.jar"]
```

Khi chạy:

```bash
docker run --rm order-service:latest \
  --spring.profiles.active=prod \
  --server.port=8080
```

Với ENTRYPOINT ở dạng JSON exec như trên, những tham số sau tên image được nối vào cuối lệnh, **sau** `/app/app.jar`, nên trở thành application arguments.

### 21.1. Nếu cần thay JVM heap trong container?

Không thể giả định:

```bash
docker run order-service:latest -Xmx1g
```

sẽ thay đổi JVM heap khi image dùng ENTRYPOINT:

```text
java -Xmx512m -jar /app/app.jar
```

Vì `-Xmx1g` khi được nối ở cuối là application argument, không phải JVM option.

Thay JVM arguments thông qua ENTRYPOINT được thiết kế cho cấu hình đó, Java launcher environment options được hỗ trợ như `JAVA_TOOL_OPTIONS` trong tình huống phù hợp, hoặc deployment configuration thích hợp.

### 21.2. Dùng biến môi trường cho Spring config

Ví dụ:

```bash
docker run --rm \
  -e SPRING_PROFILES_ACTIVE=prod \
  -e SERVER_PORT=8080 \
  order-service:latest
```

Đây là cách phổ biến để cấu hình Spring Boot trong container mà không cần thay command sau tên JAR.

### 21.3. Memory limit của container khác heap limit

`-Xmx512m` giới hạn heap, nhưng JVM còn sử dụng bộ nhớ ngoài heap cho metaspace, native allocations, direct buffers, thread stacks và các thành phần khác.

Nếu container có giới hạn 512 MiB, đặt heap tối đa 512 MiB có thể khiến tổng bộ nhớ process vượt giới hạn. Hãy thiết kế JVM memory budget theo bộ nhớ toàn tiến trình, không coi `-Xmx` là giới hạn RSS tuyệt đối.

## 22. Dùng `java -jar` từ systemd hoặc service manager

Trong production, tiến trình thường do service manager quản lý chứ không chạy thủ công trong terminal.

Ví dụ minh họa một unit file:

```ini
[Unit]
Description=Order Service
After=network.target

[Service]
WorkingDirectory=/opt/order-service
ExecStart=/usr/bin/java -Xms256m -Xmx768m -jar /opt/order-service/app.jar --spring.profiles.active=prod
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Đây là cấu hình tối giản để minh họa `ExecStart` và working directory, chưa bao gồm user chạy service, sandboxing, secret management, health checks hoặc các yêu cầu vận hành production khác.

### 22.1. Tại sao `WorkingDirectory` quan trọng?

Nếu một application argument chứa:

```text
--spring.config.additional-location=optional:file:./config/
```

thì `./config/` được giải quyết theo working directory của process.

Trong systemd, `WorkingDirectory` giúp tránh việc ứng dụng nạp một thư mục cấu hình khác với mong đợi.

### 22.2. Đừng dùng command-line argument làm cơ chế lưu secret

Service manager có thể lưu hoặc expose các thành phần của lệnh khởi động trong metadata. Credential cần đi qua cơ chế secret phù hợp thay vì ghi trực tiếp trong `ExecStart`.

## 23. Chẩn đoán lỗi chạy `java -jar`

### 23.1. `Unable to access jarfile`

Ví dụ:

```text
Error: Unable to access jarfile app.jar
```

Nguyên nhân thường gặp:

- Đường dẫn sai.
- Working directory không đúng.
- File chưa build hoặc tên artifact khác dự đoán.
- Process thiếu quyền đọc file.

**Cách xử lý:** xác nhận file tồn tại tại đường dẫn thực tế, sử dụng path tuyệt đối khi cần và kiểm tra quyền đọc. Đây không phải lỗi Spring profile.

### 23.2. `no main manifest attribute`

Ví dụ:

```text
no main manifest attribute, in app.jar
```

Nguyên nhân: JAR không có entry point thích hợp cho chế độ `-jar`.

**Cách xử lý:** kiểm tra build plugin, `bootJar`/`repackage` và lựa chọn artifact executable thay vì JAR thư viện hoặc plain JAR.

### 23.3. `UnsupportedClassVersionError`

Ví dụ Java runtime cũ cố chạy bytecode được build bằng Java mới hơn.

**Cách xử lý:** xác định target bytecode của build và runtime Java version:

```bash
java -version
```

Không thể sửa lỗi này bằng `--server.port` hoặc đổi active profile.

### 23.4. `Unrecognized option`

Ví dụ:

```bash
java --server.port=8081 -jar app.jar
```

Nguyên nhân: đưa application option vào vị trí dành cho JVM options.

**Cách xử lý:**

```bash
java -jar app.jar --server.port=8081
```

### 23.5. `-D` không có tác dụng

Sai:

```bash
java -jar app.jar -Dserver.port=8081
```

Đúng:

```bash
java -Dserver.port=8081 -jar app.jar
```

Hoặc:

```bash
java -jar app.jar --server.port=8081
```

### 23.6. `--server.port` bị bỏ qua

Cần xem:

1. Ứng dụng có thực sự là web application không?
2. `--server.port=...` có đứng sau tên JAR không?
3. `SpringApplication.setAddCommandLineProperties(false)` có được dùng không?
4. Application có custom property source, profile hoặc web server factory customization không?
5. Command-line đã được shell parse thành đúng một argument chưa?
6. Có đang kiểm tra configured port hay actual runtime port không?

Đừng mặc định mọi lỗi cổng là lỗi precedence.

### 23.7. Profile `prod` không được kích hoạt

Kiểm tra:

```bash
java -jar app.jar --spring.profiles.active=prod
```

hoặc:

```bash
java -Dspring.profiles.active=prod -jar app.jar
```

Nếu vẫn sai, kiểm tra active profiles thực tế và các nguồn override, nhất là environment variables, command-line options khác hoặc logic startup tự cấu hình.

### 23.8. Lỗi parse `ApplicationArguments`

Bạn truyền:

```bash
java -jar app.jar --app.mode import
```

nhưng `getOptionValues("app.mode")` không có `import`.

**Cách sửa:**

```bash
java -jar app.jar --app.mode=import
```

Đừng giả định `--name value` được xử lý giống `--name=value` trong parser mặc định.

### 23.9. Đọc `System.getProperty` thấy `null`

Bạn chạy:

```bash
java -jar app.jar --app.mode=import
```

rồi gọi:

```java
System.getProperty("app.mode")
```

Giá trị có thể là `null` vì đó là command-line application argument, không phải JVM system property.

Sử dụng:

```java
environment.getProperty("app.mode")
```

hoặc:

```java
args.getOptionValues("app.mode")
```

tùy ý định.

### 23.10. Application JAR và plain classpath

Java launcher có một số quy tắc riêng khi dùng `-jar`; không nên giả định thêm `-cp` hoặc `-classpath` sẽ thay thế cơ chế classpath của executable JAR.

Nếu cần thay cơ chế nạp dependency ngoài JAR, phải dùng cách đóng gói và launcher tương ứng được Spring Boot/JVM hỗ trợ, thay vì ghép tùy tiện `-cp` với `-jar`.

## 24. Cách kiểm tra cấu hình startup thực tế

### 24.1. Ghi nhận cấu hình không nhạy cảm qua runner

Ví dụ:

```java
package com.example.demo.startup;

import java.util.Arrays;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class StartupReporter implements ApplicationRunner {

    private final Environment environment;

    public StartupReporter(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(
                "Active profiles: " +
                Arrays.toString(environment.getActiveProfiles())
        );

        System.out.println(
                "Configured port: " +
                environment.getProperty("server.port", "default")
        );

        System.out.println(
                "Mode: " +
                environment.getProperty("app.mode", "serve")
        );

        System.out.println(
                "Has mode CLI option: " +
                args.containsOption("app.mode")
        );
    }
}
```

Ví dụ chỉ đọc các property được đánh giá là không nhạy cảm. Không in toàn bộ `Environment` hoặc `ApplicationArguments` để debug trong môi trường có thể chứa secret.

### 24.2. Quan sát Conditions Evaluation Report

Khi cần xem vì sao một auto-configuration được áp dụng hoặc bị bỏ qua, có thể chạy:

```bash
java -jar app.jar --debug
```

Điều này giúp chẩn đoán conditions của Spring Boot; nó không phải công cụ liệt kê đầy đủ mọi giá trị trong property sources.

### 24.3. Actuator cho môi trường được kiểm soát

Spring Boot Actuator có thể cung cấp endpoint về environment và configuration properties khi dependency và exposure đã được cấu hình phù hợp:

```text
/actuator/env
/actuator/configprops
```

Các endpoint này có thể có metadata nhạy cảm. Không expose công khai chỉ để kiểm tra `server.port`; cần authentication/authorization, masking và giới hạn mạng phù hợp.

### 24.4. Kiểm tra bằng hành vi thực tế

Nếu muốn xác nhận HTTP server chạy ở cổng 8081, hãy kiểm tra log startup hoặc gửi HTTP request thực tế tới cổng đó.

Nếu muốn xác nhận import chạy ở batch size 250, kiểm tra typed configuration value và hành vi xử lý, không chỉ nhìn chuỗi trong lệnh shell.

## 25. Tình huống thực tế và cách chọn câu lệnh

| Nhu cầu | Câu lệnh minh họa |
| --- | --- |
| Chạy JAR mặc định | `java -jar app.jar` |
| Giới hạn heap 512 MiB | `java -Xmx512m -jar app.jar` |
| Chọn profile dev | `java -jar app.jar --spring.profiles.active=dev` |
| Chọn profile prod bằng system property | `java -Dspring.profiles.active=prod -jar app.jar` |
| Đổi cổng HTTP | `java -jar app.jar --server.port=9090` |
| Chạy cổng ngẫu nhiên | `java -jar app.jar --server.port=0` |
| Bật debug report của Spring Boot | `java -jar app.jar --debug` |
| Đặt system property cho thư viện | `java -Dapp.instance=worker-1 -jar app.jar` |
| Truyền chế độ import và file | `java -jar app.jar --app.mode=import input.csv` |
| Thêm vị trí config ngoài | `java -jar app.jar --spring.config.additional-location=optional:file:./config/` |
| Kết hợp JVM và Spring options | `java -Xmx512m -Dapp.instance=a -jar app.jar --server.port=8081` |

Tất cả ví dụ đều giả định có executable JAR hợp lệ và các property được ứng dụng hoặc Spring Boot thực sự hỗ trợ.

## 26. Bài tập thực hành

### Bài 1 — Phân loại từng thành phần của lệnh

Cho:

```bash
java -Xms128m -Xmx512m \
  -Dapp.node=node-01 \
  -jar order-service.jar \
  --spring.profiles.active=staging \
  --server.port=8181 \
  --app.mode=serve
```

Hãy phân loại mỗi phần thành JVM option, JVM system property, executable JAR path hoặc application argument. Giải thích vì sao `-Dapp.node=node-01` và `--app.mode=serve` không đi vào cùng một nguồn cấu hình.

### Bài 2 — Sửa lệnh sai thứ tự

Lệnh sai:

```bash
java -jar order-service.jar -Xmx1g -Dspring.profiles.active=dev
```

Hãy sửa để JVM có heap limit 1 GiB và Spring Boot chạy profile dev. Viết thêm một phiên bản dùng `--spring.profiles.active=dev`.

### Bài 3 — So sánh Java và Spring APIs

Chạy:

```bash
java -Dapp.mode=serve -jar app.jar --app.mode=batch
```

Dự đoán:

```java
System.getProperty("app.mode")
environment.getProperty("app.mode")
applicationArguments.getOptionValues("app.mode")
```

Giải thích vì sao kết quả khác nhau mà không phải là lỗi.

### Bài 4 — Đọc đối số bằng `ApplicationArguments`

Chạy:

```bash
java -jar app.jar --app.mode=import --app.dry-run=true input.csv
```

Viết `ApplicationRunner` in số lượng non-option arguments và kiểm tra `app.mode`, `app.dry-run`. Không in raw file path nếu nó có thể chứa dữ liệu nhạy cảm.

### Bài 5 — `CommandLineRunner`

Viết `CommandLineRunner` đếm số phần tử trong `String... args`.

Giải thích khác biệt với `ApplicationRunner` và trường hợp nào nên chọn từng interface.

### Bài 6 — Ghi đè `server.port`

Đặt:

```properties
server.port=8080
```

Trong môi trường, đặt `SERVER_PORT=8081`. Khởi động với:

```bash
java -Dserver.port=8082 -jar app.jar --server.port=8083
```

Dự đoán giá trị theo precedence mặc định. Sau đó bỏ lần lượt từng nguồn và quan sát thay đổi.

### Bài 7 — `setAddCommandLineProperties(false)`

Chuyển từ static `SpringApplication.run(...)` sang instance `SpringApplication` và gọi:

```java
application.setAddCommandLineProperties(false);
```

Chạy với `--app.mode=import`, kiểm tra `ApplicationArguments` và `Environment`.

Giải thích vì sao một API vẫn biết option, còn API còn lại có thể không còn dùng giá trị option đó.

### Bài 8 — Chọn profile từ ba nguồn

Tạo `application-dev.yml` và `application-prod.yml` với log level hoặc port khác nhau.

Kích hoạt profile lần lượt bằng:

1. `--spring.profiles.active=dev`.
2. `-Dspring.profiles.active=dev`.
3. `SPRING_PROFILES_ACTIVE=dev`.

Kiểm tra active profiles và mô tả khác biệt về cách truyền.

### Bài 9 — Cấu hình `@ConfigurationProperties`

Tạo record `ImportProperties` với `batchSize`, `dryRun` và `timeout`.

Chạy:

```bash
java -jar app.jar \
  --app.import.batch-size=500 \
  --app.import.dry-run=true \
  --app.import.timeout=45s
```

Xác nhận typed binding nhận đúng `500`, `true` và `Duration.ofSeconds(45)`.

### Bài 10 — Đường dẫn cấu hình ngoài

Tạo thư mục `config/` cạnh nơi bạn chạy process và một file `application-dev.yml` trong đó.

Chạy:

```bash
java -jar app.jar \
  --spring.profiles.active=dev \
  --spring.config.additional-location=optional:file:./config/
```

Sau đó đổi working directory rồi chạy lại. Giải thích vì sao `./config/` có thể trỏ tới một nơi khác.

### Bài 11 — Shell quoting

Truyền giá trị:

```text
app.display-name=Order Management Service
```

bằng JVM system property và bằng Spring Boot application argument.

Viết lệnh phù hợp cho Bash và PowerShell, bảo đảm mỗi chuỗi chứa dấu cách được truyền như **một argument**.

### Bài 12 — Xử lý lỗi executable JAR

Giả sử chạy:

```bash
java -jar library.jar
```

và nhận `no main manifest attribute`.

Hãy xác định cần kiểm tra những gì trong Gradle/Maven packaging, phân biệt plain JAR và Spring Boot executable JAR.

### Bài 13 — Container entrypoint

Cho Dockerfile có:

```dockerfile
ENTRYPOINT ["java", "-Xmx512m", "-jar", "/app/app.jar"]
```

Giải thích điều gì xảy ra nếu chạy:

```bash
docker run demo-image -Xmx1g --spring.profiles.active=prod
```

Phần nào là application argument, phần nào thực sự là JVM option? Đề xuất cách quản lý JVM heap và active profile thích hợp cho container.

### Bài 14 — Không lộ secret

Một người vận hành đề xuất:

```bash
java -jar app.jar --spring.datasource.password=my-password
```

Hãy giải thích rủi ro với process command line, shell history và log. Đề xuất sử dụng secret manager hoặc cơ chế cung cấp secret được bảo vệ, đồng thời kiểm tra code không dump `ApplicationArguments`.

### Bài 15 — Thiết kế tài liệu chạy ứng dụng

Viết hướng dẫn vận hành cho một Spring Boot service gồm:

- Lệnh build executable JAR.
- Lệnh chạy với `dev`.
- Lệnh chạy với `prod`.
- Ví dụ cấu hình JVM heap.
- Cách chỉ định external config.
- Cách kiểm tra active profiles.
- Cách phát hiện tùy chọn đặt sai trước/sau `-jar`.
- Nguyên tắc không truyền secret trên command line.

Hãy ghi rõ các giá trị nào là ví dụ, và những thông số nào phải được điều chỉnh theo môi trường thực tế.

## 27. Tổng kết

`java -jar` là chế độ Java launcher dùng để chạy một **executable JAR**. Trong Spring Boot, artifact executable thường được tạo bằng Gradle `bootJar` hoặc Maven `repackage` qua plugin tương ứng.

Một lệnh chạy có cấu trúc:

```text
java [JVM options] -jar app.jar [application arguments]
```

Các JVM options như `-Xmx`, `-Xms` và Java system properties dạng `-Dname=value` phải đứng **trước** `-jar`. Những chuỗi như `--spring.profiles.active=dev`, `--server.port=9090` hoặc `--app.mode=import` đứng **sau** tên JAR để được chuyển vào `main(String[] args)` và được Spring Boot xử lý khi phù hợp.

`System.getProperty()` chỉ đọc JVM system properties; `ApplicationArguments` đọc application arguments; còn Spring `Environment` có thể resolve một property qua nhiều nguồn với thứ tự ưu tiên. Theo thiết lập mặc định, Spring Boot command-line properties thường ưu tiên hơn Java system properties và file `application.*`.

Khi triển khai, hãy phân biệt **tùy chọn điều hành JVM**, **cấu hình của Spring Boot** và **đối số của nghiệp vụ**. Đặt tham số đúng vị trí, kiểm soát property precedence, xác nhận cấu hình thực tế sau startup và tránh truyền mật khẩu, token hoặc thông tin nhạy cảm dưới dạng tham số dòng lệnh. Nắm vững những nguyên tắc này giúp bạn chạy, đóng gói và vận hành ứng dụng Spring Boot một cách dự đoán được trên máy local, server và container.
