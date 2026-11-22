# Phân biệt tham số JVM, system property và đối số ứng dụng khi chạy Spring Boot

## 1. Ba loại tham số đi qua ba tầng khác nhau

Khi phát triển hoặc chạy ứng dụng Java/Spring Boot, cùng một dòng lệnh có thể chứa **JVM options**, **Java system properties** và **application arguments**. Chúng có vị trí, phạm vi và cách đọc khác nhau. Một chương trình có thể biên dịch thành công nhưng hoạt động sai nếu đặt đúng tên cấu hình ở sai vị trí.

Ví dụ:

```bash
java -Xms128m -Xmx256m -Ddemo.mode=jvm -jar target/argument-lab-0.0.1-SNAPSHOT.jar --demo.mode=cli hello
```

Đọc từ trái sang phải:

| Phần lệnh | Loại | Ai xử lý? |
|---|---|---|
| `java` | Java launcher | Tạo JVM và chọn cách khởi chạy chương trình |
| `-Xms128m` | JVM option | Đặt heap ban đầu khoảng 128 MiB |
| `-Xmx256m` | JVM option | Đặt giới hạn heap tối đa khoảng 256 MiB |
| `-Ddemo.mode=jvm` | **Java system property** (được truyền bằng tùy chọn `-D` của launcher) | Thiết lập `System.getProperty("demo.mode")` trong JVM ứng dụng |
| `-jar` | Tùy chọn Java launcher | Chạy JAR có entrypoint thích hợp |
| `target/argument-lab-0.0.1-SNAPSHOT.jar` | Đường dẫn artifact | JAR sẽ được chạy |
| `--demo.mode=cli` | **Application argument**, đồng thời là command-line property của Spring Boot mặc định | Đến `main(String[] args)` và Spring `Environment` |
| `hello` | **Application argument** thông thường (non-option) | Đến `main(String[] args)`/`ApplicationArguments` |

Theo cú pháp Java launcher, khi chạy JAR:

```text
java [JVM/launcher options] -jar file.jar [application arguments...]
     └─ trước -jar ───────┘            └─ sau file.jar ──┘
```

**Quy tắc quan trọng nhất:** phần đứng **sau tên JAR** được truyền đến ứng dụng, không còn được Java launcher hiểu như tùy chọn JVM. Ví dụ `java -jar app.jar -Xmx256m` không đặt heap 256 MiB; chuỗi `-Xmx256m` chỉ là đối số ứng dụng. Tương tự, `java -jar app.jar -Ddemo.mode=jvm` **không** tự đặt Java system property. Đặt `-D...` trước `-jar`.

## 2. JVM options là gì?

**JVM options** điều khiển môi trường thực thi Java hoặc cách launcher tìm/nạp ứng dụng. Một số nhóm thường gặp:

| Ví dụ | Tác dụng | Thời điểm cần |
|---|---|---|
| `-Xms128m` | Kích thước heap ban đầu | Tuning bộ nhớ khi đo đạc, kiểm thử giới hạn |
| `-Xmx512m` | Kích thước heap tối đa | Kiểm soát vùng nhớ Java heap |
| `-XX:+HeapDumpOnOutOfMemoryError` | Tạo heap dump khi OOME theo chính sách JVM | Chẩn đoán thiếu bộ nhớ |
| `-XX:HeapDumpPath=./heap.hprof` | Nơi lưu heap dump theo cấu hình | Phân tích lỗi memory |
| `-ea` | Bật Java assertions | Kiểm thử mã dùng `assert` |
| `-Dfile.encoding=UTF-8` | Đặt một system property của JVM | Khi có lý do rõ ràng về encoding, tránh phụ thuộc môi trường |
| `-agentlib:jdwp=...` | Bật Java Debug Wire Protocol (JDWP) | Gắn debugger vào một JVM |
| `-cp out` / `--class-path out` | Thiết lập classpath cho chế độ chạy main class | Chạy bytecode/JAR bên ngoài |

Lưu ý `-D...` **vừa là một option của Java launcher, vừa là cơ chế cung cấp system property**. Vì thế người học thường gọi `-Ddemo.mode=jvm` là “JVM argument”, nhưng về **ngữ nghĩa cấu hình** nó thuộc nhóm Java system properties, khác với tùy chọn bộ nhớ như `-Xmx`.

Không được giả định rằng đặt `-Xmx512m` thì toàn bộ RSS của tiến trình Java sẽ nhỏ hơn 512 MiB. JVM còn có metaspace, stack, native memory, direct buffers và các vùng bộ nhớ khác. Muốn tối ưu phải đo bộ nhớ thực tế.

Đối với Java 17+, ví dụ debug chỉ lắng nghe trên loopback:

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -jar app.jar
```

Đây là **cú pháp minh họa**, chỉ dùng khi thực sự có `app.jar` và cần debug. Tránh mở cổng JDWP ra mạng công cộng. `--debug` của **Spring Boot** chỉ tăng thông tin chẩn đoán của Spring Boot, hoàn toàn khác với JDWP debugger của JVM.

## 3. Java system property là gì?

**Java system properties** là tập giá trị khóa–giá trị trong một **JVM process**. Chúng có thể đến từ `-Dname=value`, hệ thống JVM hoặc mã Java gọi `System.setProperty`. Đọc bằng:

```java
String mode = System.getProperty("demo.mode");
String fallback = System.getProperty("demo.mode", "default");
```

Một số ví dụ: `file.encoding`, `user.dir`, `java.version`, `spring.profiles.active` hoặc property tùy chỉnh `demo.mode`.

Phân biệt:

- `System.getProperty("demo.mode")` đọc từ **Java system properties** trong JVM hiện tại.
- `System.getenv("DEMO_MODE")` đọc từ **OS environment variable** của process, không phải Java system property. Một biến môi trường tên `DEMO_MODE` không tự trở thành `System.getProperty("demo.mode")`.
- `environment.getProperty("demo.mode")` trong Spring đọc từ **nhiều PropertySource** như command-line arguments, Java system properties, OS environment, application config.
- `System.setProperty("demo.mode","x")` thay đổi property trong JVM hiện tại; không thay đổi hệ điều hành hay JVM khác, cũng không nhất thiết khiến mọi bean đã bind sẵn tự cập nhật.

Ví dụ:

```bash
java -Ddemo.mode=local -jar app.jar
```

Nếu ứng dụng chưa ghi đè property bằng mã, `System.getProperty("demo.mode")` trả `local`. Nhưng Spring Environment có thể trả giá trị khác nếu command-line argument `--demo.mode=...` hoặc một property source có mức ưu tiên cao hơn cùng key.

Một process Maven/Gradle và một process Java ứng dụng là **hai JVM khác nhau** khi công cụ build fork JVM để chạy app. `-Ddemo.mode=...` được truyền vào **Maven/Gradle JVM** không có nghĩa sẽ tự truyền sang JVM chạy Spring Boot; cần sử dụng tham số plugin/task dành cho child process.

## 4. Đối số ứng dụng là gì?

**Application arguments** là các chuỗi Java launcher đưa vào `public static void main(String[] args)`. Chúng đứng sau tên main class hoặc sau đường dẫn JAR. Bản thân Java launcher **không yêu cầu** đối số có cú pháp `--name=value`; đó chỉ là quy ước của framework hay ứng dụng.

Ví dụ:

```bash
java -jar app.jar --demo.mode=cli hello --dry-run
```

Mảng `args` nhận các chuỗi:

```text
[--demo.mode=cli, hello, --dry-run]
```

Với Spring Boot, `SpringApplication` mặc định chuyển những option đối số bắt đầu bằng `--` thành **command-line properties** của Spring `Environment`:

- `--server.port=9090` thường đặt HTTP port của ứng dụng web.
- `--spring.profiles.active=dev` kích hoạt profile runtime `dev`.
- `--demo.mode=cli` đưa khóa `demo.mode` vào Spring Environment.
- `hello` vẫn là non-option argument, không tự biến thành property.
- `--dry-run` có thể được nhận diện là một option không có giá trị bởi `ApplicationArguments`, nhưng **không** có nghĩa Spring Boot tự triển khai hành vi “dry run”; ứng dụng phải tự xử lý.

Nếu dùng `SpringApplication.setAddCommandLineProperties(false)`, Spring Boot sẽ không tự đưa command-line options vào Environment; tuy nhiên mã vẫn có thể đọc các raw arguments. Ví dụ trong bài giả định hành vi mặc định là **đã bật**.

### API Spring Boot ApplicationArguments

Spring cung cấp giao diện `org.springframework.boot.ApplicationArguments`:

| Phương thức | Mục đích |
|---|---|
| `getSourceArgs()` | Trả raw `String[]` ban đầu |
| `containsOption("demo.mode")` | Kiểm tra sự hiện diện của option |
| `getOptionNames()` | Tập tên các option |
| `getOptionValues("demo.mode")` | Các giá trị option; có thể null nếu không có option |
| `getNonOptionArgs()` | Các đối số không bắt đầu bằng cú pháp option `--...` |

`ApplicationRunner` nhận `ApplicationArguments` trong phương thức `run`; `CommandLineRunner` nhận trực tiếp `String... args`. Cả hai là hook chạy sau khi Spring ApplicationContext khởi tạo; chọn API nào phù hợp với việc cần xử lý raw args hay các option đã phân tách.

## 5. Thí nghiệm Java 17 thuần: xem tận mắt hai kênh khác nhau

Ví dụ này không phụ thuộc Spring Boot, Maven hay Gradle. Tạo file `src/demo/ArgsBasics.java`:

```java
package demo;

import java.util.Arrays;

public final class ArgsBasics {
    public static void main(String[] args) {
        System.out.println("System property: "
                + System.getProperty("demo.mode", "unset"));
        System.out.println("Arguments: " + Arrays.toString(args));
    }
}
```

Trong thư mục gốc chứa `src`, dùng JDK 17 trở lên:

```bash
javac -d out src/demo/ArgsBasics.java
java -Xmx256m -Ddemo.mode=jvm -cp out demo.ArgsBasics --demo.mode=cli hello
```

**Stdout chính xác của lệnh `java ...`:**

```text
System property: jvm
Arguments: [--demo.mode=cli, hello]
```

Vì sao? `-Ddemo.mode=jvm` đặt system property trong JVM, còn `--demo.mode=cli` và `hello` được truyền nguyên vẹn vào `args`. `-Xmx256m` là tham số JVM nên **không** xuất hiện trong mảng `args`.

Để chứng minh khác biệt khi đảo vị trí:

```bash
java -cp out demo.ArgsBasics -Ddemo.mode=late
```

**Stdout chính xác** (giả sử môi trường không thiết lập trước property `demo.mode`):

```text
System property: unset
Arguments: [-Ddemo.mode=late]
```

`-Ddemo.mode=late` lúc này nằm **sau main class** nên chỉ là application argument. Nếu máy có `JAVA_TOOL_OPTIONS`/`JDK_JAVA_OPTIONS` đặt sẵn `demo.mode`, kết quả property có thể khác; nên kiểm tra các biến môi trường đó khi chẩn đoán.

### Khác biệt cú pháp classpath giữa hệ điều hành

Ví dụ trên chỉ cần một thư mục `out` nên lệnh dùng giống nhau trên nhiều hệ điều hành. Nếu có hai mục classpath:

- Linux/macOS: `-cp "out:lib/demo.jar"`.
- Windows: `-cp "out;lib/demo.jar"`.

Dấu `:`/`;` thuộc **cú pháp classpath**, không liên quan đến phân loại JVM/system/app arguments.

## 6. Bài thực hành Spring Boot 3.x chạy được

Ví dụ dùng **Java 17**, Spring Boot **3.5.0** (một phiên bản minh họa đã pin, không khẳng định mới nhất) và Maven. Tạo cấu trúc:

```text
argument-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/argumentlab/ArgumentLabApplication.java
    │   └── resources/application.properties
    └── test/
```

### 6.1. POM hoàn chỉnh

Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>argument-lab</artifactId>
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
```

`spring-boot-starter-parent` quản lý các phiên bản dependency/plugin tương thích trong bản ví dụ. `spring-boot-maven-plugin` chịu trách nhiệm tạo executable JAR khi phase package chạy với execution từ parent. Không cần web starter vì ta chỉ in thông tin ở console.

### 6.2. Java class hoàn chỉnh

Tạo `src/main/java/com/example/argumentlab/ArgumentLabApplication.java`:

```java
package com.example.argumentlab;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class ArgumentLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(ArgumentLabApplication.class, args);
    }

    @Bean
    ApplicationRunner showArguments(Environment environment) {
        return arguments -> {
            System.out.println("JVM property: "
                    + System.getProperty("demo.mode", "unset"));
            System.out.println("Spring property: "
                    + environment.getProperty("demo.mode", "unset"));
            System.out.println("CLI option: "
                    + arguments.getOptionValues("demo.mode"));
            System.out.println("Non-options: "
                    + arguments.getNonOptionArgs());
        };
    }
}
```

Ứng dụng cố ý đọc **hai API khác nhau** với cùng key `demo.mode`. `System.getProperty` xem đúng property trong JVM; `Environment` áp dụng quy tắc ưu tiên các nguồn cấu hình Spring. `ApplicationRunner` nhận option và non-option đã phân tách.

Tạo `src/main/resources/application.properties`:

```properties
demo.mode=file
spring.main.banner-mode=off
```

### 6.3. Build và chạy bằng java -jar

Tại root:

```bash
# Với dự án có Maven Wrapper:
./mvnw clean package

# Hoặc Maven đã được cài trong PATH:
mvn clean package

# Chạy executable JAR:
java -Xmx256m -Ddemo.mode=jvm -jar target/argument-lab-0.0.1-SNAPSHOT.jar --demo.mode=cli hello
```

Trong Windows PowerShell, nếu dự án có Maven Wrapper, dùng `.\mvnw.cmd clean package`; lệnh `java` có cùng trật tự đối số. Ví dụ chỉ cần chạy **một** trong hai lệnh build tương đương; nếu đã dùng wrapper không cần chạy lại `mvn`.

Khi build/chạy thành công, console có thể còn log Spring, Maven hoặc cảnh báo môi trường, nhưng **bốn dòng do `ApplicationRunner` in ra** chính xác là:

```text
JVM property: jvm
Spring property: cli
CLI option: [cli]
Non-options: [hello]
```

Giải thích:

1. `-Ddemo.mode=jvm` đặt `System.getProperty("demo.mode") = "jvm"`.
2. `--demo.mode=cli` tạo command-line property cho Spring Environment; mặc định nó **ưu tiên hơn** Java system property cùng key và `application.properties`.
3. `ApplicationArguments.getOptionValues("demo.mode")` trả danh sách một phần tử `[cli]`.
4. `hello` là non-option và được trả dưới dạng `[hello]`.

Đổi một tham số để thử:

```bash
java -Ddemo.mode=jvm -jar target/argument-lab-0.0.1-SNAPSHOT.jar hello
```

Khi **không có** `--demo.mode=...`, `System.getProperty` và `Environment` đều đọc `jvm` (vì Java system property ưu tiên hơn `application.properties`). `CLI option` trả `null`, còn `Non-options` vẫn `[hello]`. Đây là cách thấy rõ từng nguồn cấu hình.

Nếu chạy:

```bash
java -jar target/argument-lab-0.0.1-SNAPSHOT.jar --demo.mode=cli
```

`JVM property` là `unset` nếu không có nguồn khác đặt system property, `Spring property` là `cli` và `CLI option` là `[cli]`. Không cần và cũng không nên cố chuyển mọi Spring property sang `-D`.

## 7. Thứ tự ưu tiên của cấu hình trong Spring Boot

Spring Boot `Environment` kết hợp nhiều **PropertySource**. Đối với cách khởi chạy điển hình (không có test override hay các property source tùy chỉnh có thứ tự cao hơn), nguồn nào thường ưu tiên nguồn nào?

```text
Ưu tiên cao hơn (cho trường hợp đang xét)
    --demo.mode=cli                  # command-line property
    -Ddemo.mode=jvm                  # Java system property
    DEMO_MODE=from-env               # OS environment variable
    application.properties           # config data
Ưu tiên thấp hơn
```

Bảng này chỉ so sánh **bốn nguồn thường gặp**. Spring Boot còn có `SPRING_APPLICATION_JSON`, profile-specific files, test property sources, config import và nhiều nguồn khác. Muốn xác định tuyệt đối một giá trị cần xét toàn bộ PropertySource của ứng dụng đang chạy.

| Nguồn | Ví dụ | Cách đọc |
|---|---|---|
| Application config | `demo.mode=file` trong `application.properties` | `Environment.getProperty("demo.mode")` |
| OS environment | `DEMO_MODE=env` | `System.getenv("DEMO_MODE")`, cũng có thể map vào Environment qua relaxed binding |
| Java system property | `-Ddemo.mode=jvm` trước `-jar` | `System.getProperty("demo.mode")` và Environment |
| Spring command-line option | `--demo.mode=cli` sau JAR | `ApplicationArguments`, `Environment.getProperty` |
| Raw non-option argument | `hello` sau JAR | `String[] args`, `getNonOptionArgs()` |

**Không nhầm tên property và nơi lưu property:** `spring.profiles.active` có thể được cấp qua `-Dspring.profiles.active=dev` (Java system property), qua `--spring.profiles.active=dev` (application argument được Spring xử lý) hoặc qua `SPRING_PROFILES_ACTIVE=dev` (OS environment variable). Chúng có thể tạo kết quả Spring profile giống nhau nhưng đi qua các kênh khác nhau, có độ ưu tiên khác nhau, và `System.getProperty("spring.profiles.active")` chỉ nhìn thấy bản Java system property.

Nếu muốn **tắt** việc Spring đưa CLI options vào Environment, ứng dụng có thể gọi:

```java
SpringApplication application =
        new SpringApplication(ArgumentLabApplication.class);
application.setAddCommandLineProperties(false);
application.run(args);
```

Đây là **đoạn thay thế cho thân phương thức `main`** trong ví dụ Java trên, không phải file độc lập. Khi dùng cấu hình này, `ApplicationArguments` vẫn đọc raw options, nhưng `Environment` sẽ không tự lấy `--demo.mode=...` từ command line. Chỉ chỉnh khi có lý do rõ ràng.

## 8. Maven spring-boot:run: phân biệt JVM của Maven và JVM của app

Lệnh `mvn spring-boot:run` hoặc `./mvnw spring-boot:run` thường dùng để chạy ứng dụng trong lúc phát triển mà chưa phải tạo executable JAR. Spring Boot Maven Plugin thực hiện chạy ứng dụng ở **process fork riêng**, nên cần tách:

1. **Tham số cho Maven**: ví dụ `-DskipTests`, `-Pdev`, `-Dsome.build.property`.
2. **Tham số JVM của ứng dụng**: plugin `spring-boot.run.jvmArguments` hoặc `spring-boot.run.systemPropertyVariables`.
3. **Application arguments của ứng dụng**: plugin `spring-boot.run.arguments`, hoặc `spring-boot.run.profiles` để kích hoạt Spring profiles.

Ví dụ Linux/macOS (một lệnh, xuống dòng chỉ để dễ đọc):

```bash
./mvnw spring-boot:run \
  -Dspring-boot.run.jvmArguments="-Xmx256m -Ddemo.mode=jvm" \
  -Dspring-boot.run.arguments="--demo.mode=cli hello"
```

Bốn dòng do `ApplicationRunner` in giống mục 6.3:

```text
JVM property: jvm
Spring property: cli
CLI option: [cli]
Non-options: [hello]
```

Ở đây những tham số bắt đầu bằng `-Dspring-boot.run....` là **Maven user properties dùng để cấu hình plugin**. Plugin lấy các giá trị đó rồi chuyển phần JVM/app đến process Spring Boot. Không nên hiểu đó là các Java system properties có cùng tên được ứng dụng đọc trực tiếp.

Lệnh PowerShell một dòng để tránh quy tắc nối dòng khác Bash:

```powershell
.\mvnw.cmd spring-boot:run "-Dspring-boot.run.jvmArguments=-Xmx256m -Ddemo.mode=jvm" "-Dspring-boot.run.arguments=--demo.mode=cli hello"
```

Cú pháp truyền/quote tham số có khoảng trắng khác nhau giữa shell và phiên bản công cụ; nếu thấy app thiếu một phần argument, kiểm tra log và chạy lệnh trên một dòng với cách quote phù hợp shell đang dùng.

Để bật Spring runtime profile qua Maven plugin:

```bash
./mvnw spring-boot:run -Dspring-boot.run.profiles=dev
```

Lưu ý `-Pdev` là **Maven build profile**, không đồng nghĩa `spring.profiles.active=dev` của Spring runtime. Tương tự, lệnh:

```bash
./mvnw spring-boot:run -Ddemo.mode=jvm
```

chỉ đặt user property cho **Maven process**; không bảo đảm Java system property `demo.mode` có trong **JVM ứng dụng**. Nếu thật sự cần, dùng `-Dspring-boot.run.jvmArguments="-Ddemo.mode=jvm"` hoặc cấu hình plugin system property variables.

### MAVEN_OPTS không phải application args

`MAVEN_OPTS` ảnh hưởng JVM **chạy Maven**, còn `spring-boot.run.jvmArguments` điều khiển JVM chạy ứng dụng do plugin khởi tạo. `JAVA_TOOL_OPTIONS`/`JDK_JAVA_OPTIONS` có thể được Java launcher hoặc JVM của nhiều process nhận và đôi khi tác động cả Maven lẫn ứng dụng; vì thế chúng có phạm vi rộng, dễ gây bất ngờ khi debug. Không dùng chúng để truyền argument chứa thông tin nhạy cảm một cách tùy tiện.

## 9. Gradle bootRun: ứng dụng chạy trong JVM fork từ Gradle

Spring Boot Gradle Plugin bổ sung task `bootRun` thuộc lớp `BootRun` kế thừa `JavaExec`. Bởi vậy ta có các phương thức cấu hình khác nhau cho **JVM**, **system property** và **application arguments**.

Ví dụ `build.gradle` **Groovy DSL hoàn chỉnh về phần build**, dùng bản Spring Boot minh họa giống phần Maven:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
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
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.5.0'
    )
    implementation 'org.springframework.boot:spring-boot-starter'
}

tasks.named('bootRun') {
    jvmArgs '-Xmx256m'                // JVM option
    systemProperty 'demo.mode', 'jvm' // System property của JVM ứng dụng
    args '--demo.mode=cli', 'hello'   // Application args
}
```

Dùng lại **cùng class Java** và `application.properties` ở mục 6, nhưng chạy bằng Gradle (không trộn `pom.xml` và `build.gradle` để mong chúng tự đồng bộ). `settings.gradle` tối thiểu:

```groovy
rootProject.name = 'argument-lab'
```

Khi dự án đã có Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows dùng `gradlew.bat bootRun`. Ứng dụng được chạy trong JVM do `bootRun` tạo; bốn dòng in bởi class Java vẫn là `jvm`, `cli`, `[cli]`, `[hello]`. Cần một phiên bản Gradle tương thích với Spring Boot Gradle Plugin 3.5 và JDK 17+; nếu máy chỉ có Gradle quá cũ, hãy cập nhật Wrapper theo hướng dẫn của dự án.

### Truyền application args từ dòng lệnh Gradle

```bash
./gradlew bootRun --args="--demo.mode=cli hello"
./gradlew bootRun --args="--spring.profiles.active=dev"
```

Tham số `--args` của task `JavaExec/BootRun` truyền argument cho **ứng dụng**, không thay đổi JVM heap. Khi `--args` được cung cấp, nó thay thế arguments được cấu hình trên task bằng giá trị từ command line theo cơ chế Gradle. Nếu muốn chỉ định bộ đối số mặc định, đặt `args` trong task như ở trên; nếu muốn thay đổi tại lần chạy, truyền `--args`.

Cần đặc biệt tránh:

```bash
./gradlew bootRun -Ddemo.mode=jvm
```

`-Ddemo.mode=jvm` ở đây chủ yếu là **Gradle system property** cho tiến trình Gradle/daemon, không bảo đảm được chuyển tự động sang JVM ứng dụng. Nếu muốn chuyển từ command line sang `bootRun`, thiết kế một project property rồi map nó vào child JVM:

```groovy
tasks.named('bootRun') {
    systemProperty 'demo.mode', providers.gradleProperty('appMode').orElse('local').get()
}
```

Đây là **đoạn bổ sung/thay thế dòng systemProperty** của task `bootRun`, không đặt hai dòng cấu hình trái nhau trong file rồi mong một giá trị duy nhất. Khi đó:

```bash
./gradlew bootRun -PappMode=jvm --args="--demo.mode=cli hello"
```

`-PappMode=jvm` là **Gradle project property**; script chuyển nó thành **Java system property trong JVM ứng dụng**. `--demo.mode=cli` vẫn là **app argument** và theo mặc định Spring Environment ưu tiên `cli` trước `jvm`.

Trong build dùng Kotlin DSL, cú pháp sẽ khác (`tasks.named<BootRun>("bootRun") { ... }` với import/class tương ứng); không trộn cú pháp Groovy và Kotlin vào một file.

## 10. Chạy từ IDE, container và script: biết tham số vào process nào

### IDE

Trong cấu hình Run/Debug của IDE, thường có các vùng riêng:

- **VM options / JVM arguments**: `-Xmx512m -Ddemo.mode=jvm`.
- **Program arguments / application arguments**: `--demo.mode=cli hello`.
- **Environment variables**: `DEMO_MODE=env`, `SPRING_PROFILES_ACTIVE=dev`.
- **Working directory**: ảnh hưởng đường dẫn tương đối khi ứng dụng mở file; không phải tham số command line.

Nếu cấu hình Maven Run/Gradle Task trong IDE, cần biết IDE đang chạy **build process** hay **Spring Boot application process**; một ô “VM options” có thể áp vào Maven/Gradle trước khi ứng dụng được fork. Muốn chắc chắn, kiểm tra bằng `System.getProperty` trong chính JVM Spring Boot.

### Docker/container

Một container chạy executable JAR qua Java vẫn tuân quy tắc:

```dockerfile
# Minh họa phần ENTRYPOINT khi image đã có JRE và app.jar
ENTRYPOINT ["java", "-Xmx256m", "-Ddemo.mode=jvm", "-jar", "/app/app.jar"]
```

Nếu chạy container với thêm argument:

```bash
docker run --rm example/argument-lab:demo --demo.mode=cli hello
```

Với ENTRYPOINT dạng JSON/exec ở trên, các đối số sau image name được nối sau JAR và trở thành **application arguments**. Ví dụ `example/argument-lab:demo` là tên image **giả định**, phải build image trước; snippet Dockerfile chưa phải Dockerfile hoàn chỉnh và không bảo đảm image ấy tồn tại.

Để cấu hình JVM qua container, nên đặt JVM options **trước** `-jar` trong ENTRYPOINT hoặc dùng cơ chế cấu hình có kiểm soát. Không kỳ vọng một chuỗi `-Xmx` ở cuối `docker run ... image ...` có tác dụng với JVM khi entrypoint đã chạy `-jar`.

### Start scripts và CI

Một script có thể chứa:

```bash
java -Xmx512m -Ddemo.mode=ci -jar build/libs/argument-lab-0.0.1-SNAPSHOT.jar --spring.profiles.active=ci
```

Chú ý đường dẫn `build/libs` ở đây là **quy ước Gradle**, còn Maven thường dùng `target/`. Cả hai chỉ hợp lệ khi task tương ứng đã tạo executable JAR với tên đó. CI cần in/kiểm tra command đang chạy, version JDK và phiên bản artifact thật để tránh đổi nhầm thứ tự.

## 11. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân đáng kiểm tra | Sửa thế nào |
|---|---|---|
| `-Xmx512m` không tác dụng khi chạy JAR | Đặt sau `app.jar` | Chuyển `-Xmx512m` về trước `-jar` |
| `System.getProperty("demo.mode")` trả `null` dù có `--demo.mode=cli` | `--...` là Spring app argument, không tạo Java system property | Đọc `Environment` hoặc truyền `-Ddemo.mode=...` trước `-jar` |
| Spring Environment trả `cli` dù `-Ddemo.mode=jvm` | CLI property mặc định ưu tiên cao hơn Java system property | Kiểm tra nguồn ưu tiên; bỏ hoặc đổi `--demo.mode` |
| `System.getenv("DEMO_MODE")` không có giá trị khi chỉ dùng `-Ddemo.mode=...` | Environment variables khác Java system properties | Đặt OS env var hoặc đọc `System.getProperty` |
| Maven `-Ddemo.mode=x` không đến Spring Boot | Build tool và app chạy JVM khác nhau | Dùng `spring-boot.run.jvmArguments` hoặc plugin systemPropertyVariables |
| Gradle `-Ddemo.mode=x` không đến `bootRun` | JVM daemon khác JVM ứng dụng | Dùng `bootRun.systemProperty`, map từ `-P...` |
| `--spring.profiles.active=dev` không có tác dụng | Đặt sai vào JVM options/Gradle options hoặc không truyền đến app | Đặt sau JAR, dùng Maven run arguments hoặc Gradle `--args` |
| `-Pprod` của Maven/Gradle không bật Spring profile | Build profile/project property không phải Spring runtime profile | Truyền `--spring.profiles.active=prod` hay `-Dspring.profiles.active=prod` đúng process |
| Không thấy option trong `ApplicationArguments` | Chưa truyền cho app, hoặc dùng non-option sai cú pháp | In `getSourceArgs()`/`getOptionNames()` và so lại lệnh |
| Cấu hình IDE khác terminal | IDE dùng JVM/working dir/env hoặc app args khác | So VM options, program args, environment, JDK |
| Lỗi `Unrecognized VM option` | Flag JVM không hợp lệ với JDK hoặc nằm sai chỗ | Xem `java -version`, thử option trên JDK thực tế |
| Có `--debug` nhưng debugger không attach được | Spring Boot debug logging khác JDWP | Cấu hình debug JVM/IDE theo JDWP |
| App đổi port không hiệu lực | Không có web server hoặc property bị ghi đè | Kiểm tra starter web, Spring Environment và các property source |
| Docker option JVM bị nhận như tham số ứng dụng | ENTRYPOINT đã đặt `-jar` trước tham số thêm | Chỉnh ENTRYPOINT/biến cấu hình JVM thích hợp |

### Chiến lược chẩn đoán nhanh

1. **Xác định process:** có phải JVM ứng dụng thực sự đang chạy, hay chỉ là JVM Maven/Gradle?
2. **In raw args:** tạm ghi `Arrays.toString(args)` hoặc `ApplicationArguments.getSourceArgs()`.
3. **In Java property:** `System.getProperty("demo.mode")`.
4. **In Spring property:** `Environment.getProperty("demo.mode")` hoặc Actuator `/actuator/env` nếu ứng dụng có Actuator và quyền truy cập thích hợp.
5. **Kiểm tra JVM settings** bằng công cụ thích hợp (như `jcmd <pid> VM.flags` ở JDK có hỗ trợ), hoặc log/tùy chọn JVM, thay vì trông đợi `-Xmx` xuất hiện trong `args`.
6. **So lại trật tự** `java [options] -jar app.jar [args]` và các tham số plugin/task khi chạy qua Maven/Gradle.
7. Với môi trường nhiều profile/property source, xác định **nguồn nào thắng** theo cấu hình ứng dụng đang chạy; không chỉ nhìn `application.properties`.

Khi bật Actuator endpoint chẩn đoán, cấu hình quyền truy cập và cơ chế che giá trị nhạy cảm phù hợp; không mở toàn bộ cấu hình/biến môi trường ra bên ngoài.

## 12. Bảng ghi nhớ và bài tập

| Bạn muốn làm gì? | Ví dụ đúng | Đọc ở đâu? |
|---|---|---|
| Đổi giới hạn heap JVM | `java -Xmx512m -jar app.jar` | JVM/runtime settings, không nằm trong `args` |
| Đặt một Java system property | `java -Ddemo.mode=jvm -jar app.jar` | `System.getProperty("demo.mode")` |
| Truyền một giá trị cấu hình Spring | `java -jar app.jar --demo.mode=cli` | Spring `Environment` / `ApplicationArguments` |
| Truyền non-option argument | `java -jar app.jar hello` | `main(args)`/`getNonOptionArgs()` |
| Bật Spring runtime profile | `java -jar app.jar --spring.profiles.active=dev` | Spring `Environment` |
| Đặt OS environment variable | `DEMO_MODE=env java -jar app.jar` (Unix shell) | `System.getenv("DEMO_MODE")` và Spring Environment |
| Chạy ứng dụng qua Maven | `./mvnw spring-boot:run -Dspring-boot.run.profiles=dev` | Spring Boot Maven Plugin chuyển profile đến app |
| Chạy ứng dụng qua Gradle | `./gradlew bootRun --args="--spring.profiles.active=dev"` | Gradle `BootRun` truyền app args |

**Bài tập tự kiểm tra:**

- Dự đoán `System.getProperty("demo.mode")` và `Environment.getProperty("demo.mode")` khi truyền đồng thời `-Ddemo.mode=jvm` trước JAR và `--demo.mode=cli` sau JAR.
- Thử chạy `ArgsBasics` với `-Ddemo.mode=late` ở trước và sau main class; đối chiếu `args`.
- Chạy Spring Boot bằng Maven/Gradle rồi thay một giá trị lần lượt ở **build tool property**, **child JVM system property**, **application arguments**; quan sát dòng nào thay đổi.
- Đổi `--demo.mode=cli` thành `--demo.mode=preview`, giữ `-Ddemo.mode=jvm`; kiểm tra vì sao `System.getProperty` không đổi, còn Spring Environment đổi.

**Kết luận kiến thức:** JVM options điều khiển **máy ảo Java**, Java system properties là **key–value trong đúng JVM đang chạy**, application arguments là **chuỗi truyền cho phương thức main**. Spring Boot còn chuyển một phần application arguments dạng `--key=value` thành cấu hình có ưu tiên trong `Environment`. Khi chạy qua Maven hoặc Gradle, trước tiên phải xác định **tham số đang được truyền cho build tool hay JVM ứng dụng**.

### Tài liệu tham khảo chính thức

- [Java launcher — The java Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html)
- [Spring Boot Maven Plugin — Running Your Application](https://docs.spring.io/spring-boot/3.5/maven-plugin/run.html)
- [Spring Boot Gradle Plugin — Running Your Application](https://docs.spring.io/spring-boot/3.5/gradle-plugin/running.html)
- [Gradle — JavaExec task](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.JavaExec.html)
