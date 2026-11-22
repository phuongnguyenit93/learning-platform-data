# Thí nghiệm một khóa qua tệp, biến môi trường, JVM và dòng lệnh trong Spring Boot

## 1. Tình huống và câu hỏi cần trả lời

Trong một dự án Spring Boot, một property có thể được khai báo đồng thời ở nhiều nơi:

```properties
# application.properties
lab.message=from-file
```

```bash
# Biến môi trường của hệ điều hành
LAB_MESSAGE=from-env
```

```bash
# Java system property
-Dlab.message=from-jvm
```

```bash
# Đối số dòng lệnh của Spring Boot
--lab.message=from-cli
```

Nếu tất cả cùng tồn tại, **ứng dụng sử dụng giá trị nào?** Vì sao giá trị trong file có thể bị ghi đè mà không cần sửa source? Và làm cách nào để biết ta thực sự đã đưa `-D` vào JVM chạy ứng dụng chứ không chỉ vào Gradle đang thực thi lệnh build?

Bài thực hành này dùng **một khóa duy nhất**:

```text
lab.message
```

và bốn nhóm nguồn: **tệp cấu hình, biến môi trường OS, Java system property và application command-line argument**.

Mục tiêu không phải ghi nhớ một câu trả lời cố định rồi đoán theo cảm giác. Bạn sẽ khởi động **cùng một JAR** với nhiều tổ hợp nguồn, ghi lại giá trị thắng trong từng lượt và đối chiếu với quy tắc `PropertySource` precedence của Spring Boot 3.3.

Bài thuộc nhóm **Thực hành tổng hợp** của chủ đề **Spring Boot Externalized Configuration**.

### Bạn sẽ học được

1. Phân biệt **source code Java**, **file được đóng gói trong JAR** và **file cấu hình ngoài JAR**.
2. Hiểu `Environment` tập hợp nhiều `PropertySource` và cách một key trùng tên được giải quyết.
3. Ghi đè tệp cấu hình bằng biến môi trường `LAB_MESSAGE`.
4. Ghi đè biến môi trường bằng `java -Dlab.message=...`.
5. Ghi đè JVM system property bằng `--lab.message=...` đặt **sau** tên JAR.
6. Dùng `Environment`, `@ConfigurationProperties` và `@Value` để đọc cùng một giá trị hiệu lực.
7. Phân biệt `System.getenv()`, `System.getProperty()` và cơ chế resolve property của Spring.
8. Hiểu vì sao tệp `./config/application.properties` có thể được Boot tự phát hiện.
9. Khởi chạy với Java 21 / Gradle / Spring Boot 3.3 mà không phụ thuộc một server bên ngoài.
10. Xác định nguồn gây bất ngờ khi chạy qua IDE, `bootRun`, Docker hoặc Kubernetes.
11. Biết giới hạn của thí nghiệm: thứ tự ưu tiên có ngoại lệ khi thêm JSON, test property sources, DevTools hoặc các integration khác.
12. Xây dựng một ma trận kiểm tra lặp lại, hữu ích cho CI và xử lý sự cố.

**Phiên bản minh họa:** Java 21, Spring Boot 3.3.13, Gradle. Giá trị `from-file`, `from-env`, `from-jvm`, `from-cli` chỉ là nhãn huấn luyện; không dùng password, token hay secret thật.

---

## 2. Kết quả cần chứng minh trước khi chạy

Trong tình huống thông thường của Spring Boot 3.3, nếu chỉ xét bốn lớp nguồn được giao, thứ tự ưu tiên **từ cao xuống thấp** là:

```text
        ƯU TIÊN CAO NHẤT
                 |
                 v
    --lab.message=from-cli
                 |
                 v
    -Dlab.message=from-jvm
                 |
                 v
    LAB_MESSAGE=from-env
                 |
                 v
    Config Data: application.properties / application.yaml
                 |
                 v
        ƯU TIÊN THẤP HƠN
```

Trong phạm vi Config Data, một file cấu hình **ở ngoài JAR** tại vị trí mặc định có thể ghi đè file nền **đóng gói trong JAR**.

Do đó, một ma trận dự đoán là:

| Nguồn đang cung cấp `lab.message` | Giá trị hiệu lực |
| --- | --- |
| Chỉ file trong JAR | `from-classpath` |
| Có thêm file `./config/application.properties` | `from-file` |
| File ngoài JAR + biến môi trường | `from-env` |
| File ngoài JAR + biến môi trường + JVM `-D` | `from-jvm` |
| Đủ cả file, env, JVM `-D` và CLI `--` | `from-cli` |
| Bỏ CLI, vẫn còn JVM `-D` | `from-jvm` |
| Bỏ tiếp JVM `-D`, vẫn còn env | `from-env` |
| Bỏ tiếp env, còn file ngoài | `from-file` |
| Xóa/đổi tên file ngoài, còn file đóng gói | `from-classpath` |

**Chú ý:** bảng này chỉ xét các nguồn của bài. Trong một ứng dụng thật, còn có những nguồn khác như `SPRING_APPLICATION_JSON`, Servlet/JNDI, test properties, profile-specific Config Data, `@PropertySource`, default properties và các provider remote. Không mở rộng kết luận “CLI luôn thắng mọi thứ trong mọi hoàn cảnh” sang test hoặc một hệ thống tự thay đổi `PropertySources` mà không kiểm tra ngữ cảnh.

### 2.1. Một nguồn không có key thì không tham gia cạnh tranh

Nếu không đặt `LAB_MESSAGE`, nguồn OS environment không cung cấp giá trị cho `lab.message`, nên Spring tiếp tục tìm giá trị từ nguồn ưu tiên thấp hơn.

Tương tự:

- Không có `-Dlab.message=...` nghĩa là Java system properties không đưa ra key này.
- Không có `--lab.message=...` nghĩa là command-line `PropertySource` không cung cấp key này.
- Khi file ngoài JAR vắng mặt, Boot có thể dùng file đóng gói trong JAR.

Precedence quyết định **trong những nguồn có cùng key**, không có nghĩa phải khai báo mọi nguồn mới chạy được.

### 2.2. Giá trị cuối không phải phép cộng chuỗi

Nếu bốn nguồn là:

```text
from-classpath
from-file
from-env
from-jvm
from-cli
```

kết quả không phải:

```text
from-classpath-from-file-from-env-from-jvm-from-cli
```

Với một **scalar String**, Spring chọn một giá trị hiệu lực cho property. Các quy tắc merge/replace của `List` hoặc bind các object phức tạp là chủ đề riêng, không cần dùng để giải thích khóa scalar này.

---

## 3. Những thành phần Spring Boot tham gia thí nghiệm

Một sơ đồ:

```text
         Java process
              |
              v
      SpringApplication.run(...)
              |
              v
          Environment
              |
      +-------+--------+----------------+----------------+
      |                |                |                |
  commandLineArgs   systemProperties  systemEnvironment  Config Data
      |                |                |                |
      |            -Dlab.message    LAB_MESSAGE       application.*
      |                                                 |
      +--------------------+----------------------------+
                           |
                           v
              Resolve "lab.message"
                           |
           +---------------+----------------+
           |               |                |
           v               v                v
  Environment.getProperty  @Value      @ConfigurationProperties
           |               |                |
           +---------------+----------------+
                           |
                           v
                  Console output
```

Mỗi mũi tên đóng một vai trò:

- **Property sources** cung cấp dữ liệu và có thứ tự ưu tiên.
- **Environment** cung cấp API tra cứu dữ liệu cấu hình.
- **`@Value`** resolve placeholder khi bean được tạo.
- **`@ConfigurationProperties`** bind một nhóm cấu hình có kiểu, hỗ trợ relaxed binding và conversion.
- **ApplicationRunner** in kết quả sau khi context được tạo; nó không tự quyết định precedence.

### 3.1. `System.getenv()` khác `Environment.getProperty()`

```java
System.getenv("LAB_MESSAGE")
```

chỉ hỏi **biến môi trường OS**. Nó không biết `-Dlab.message` hay `--lab.message`.

Trong khi:

```java
environment.getProperty("lab.message")
```

hỏi **Environment của Spring**, nơi đã tập hợp nhiều nguồn.

Nếu đặt:

```text
LAB_MESSAGE=from-env
-Dlab.message=from-jvm
--lab.message=from-cli
```

thì:

```text
System.getenv("LAB_MESSAGE")               -> from-env
System.getProperty("lab.message")          -> from-jvm
Environment.getProperty("lab.message")     -> from-cli
```

Không có mâu thuẫn nào. Ba lời gọi giải quyết ba câu hỏi khác nhau.

### 3.2. `System.getProperty()` cũng không phải Environment

```java
System.getProperty("lab.message")
```

đọc **Java system properties** của JVM đang chạy. Nó không tự tìm file YAML hoặc environment variable.

Một JVM system property thường được truyền bằng `-D`:

```bash
java -Dlab.message=from-jvm -jar app.jar
```

Lệnh khác:

```bash
java -jar app.jar --lab.message=from-cli
```

đưa option đến **application arguments**, và Spring Boot có thể thêm chúng làm một `PropertySource` ưu tiên cao.

**Vị trí đối số rất quan trọng.**

---

## 4. Khởi tạo project Gradle để quan sát một khóa

Cấu trúc project tối thiểu:

```text
config-source-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── config/                            # tạo trong quá trình thí nghiệm
│   └── application.properties        # file ngoài JAR
└── src/
    ├── main/
    │   ├── java/dev/example/configlab/
    │   │   ├── ConfigSourceLabApplication.java
    │   │   └── LabProperties.java
    │   └── resources/
    │       └── application.yaml
    └── test/
        └── java/dev/example/configlab/
            └── LabPropertiesTest.java
```

Tạo project bằng Spring Initializr với Java 21, Gradle, Spring Boot 3.3.x và starter cơ bản. Giữ Gradle Wrapper (`gradlew` và `gradlew.bat`) mà project cung cấp.

Ứng dụng là **console application**, không mở HTTP port. Như vậy mỗi lần chạy sẽ in đúng một báo cáo, rồi process kết thúc. Không cần database, Docker, Kubernetes, Vault hay Spring Cloud Config Server để làm thí nghiệm này.

### 4.1. `settings.gradle`

```groovy
rootProject.name = 'config-source-lab'
```

### 4.2. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'dev.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter` cung cấp những dependency cơ bản cho ứng dụng và hỗ trợ đọc YAML qua cơ chế phù hợp của Boot. Không cần thêm một thư viện chuyển đổi type tự viết cho `String`.

Dự án dùng một version cố định để dễ tái lập. Khi nâng cấp phiên bản Spring Boot cho dự án thật, kiểm tra các yêu cầu Java/Gradle và tài liệu tương ứng.

### 4.3. `application.yaml` đóng gói trong JAR

Tạo file:

`src/main/resources/application.yaml`

```yaml
spring:
  application:
    name: config-source-lab
  main:
    web-application-type: none
    banner-mode: "off"

lab:
  message: "from-classpath"
```

Giá trị này đóng vai trò **fallback**. Nó được đóng gói trong artifact khi chạy `bootJar`.

**Phân biệt hai nghĩa của “file”:**

1. `src/main/resources/application.yaml`: tài nguyên được đóng gói vào JAR.
2. `./config/application.properties`: file bên ngoài artifact, nằm trong **working directory** khi tiến trình khởi động.

Nếu chỉ có file (1), kết quả ban đầu là:

```text
from-classpath
```

Khi thêm file (2), bạn sẽ quan sát rằng Spring Boot có thể chọn:

```text
from-file
```

dù Java code và JAR không đổi.

---

## 5. `@ConfigurationProperties`: bean nhận giá trị đã chọn

Tạo `src/main/java/dev/example/configlab/LabProperties.java`:

```java
package dev.example.configlab;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "lab")
public record LabProperties(String message) {}
```

Spring Boot Binder tìm key dưới prefix `lab`, sau đó bind component `message` từ property `lab.message`.

Vì đây là Java record với một component, Spring Boot 3.3 có thể sử dụng constructor binding theo quy ước mà không cần class-level `@ConstructorBinding`.

Không cần gắn `@Component` lên record; root sẽ được đăng ký bằng `@ConfigurationPropertiesScan` ở main class.

### 5.1. Vì sao dùng một record đơn giản?

Vì bài học cần cô lập **thứ tự ưu tiên nguồn**, không phải cú pháp converter phức tạp.

Với:

```java
public record LabProperties(String message) {}
```

không có yếu tố nào như:

- `Duration` hay `DataSize` conversion.
- Nested records.
- List/Map merge rules.
- Validation tùy biến.
- Profile-specific binding logic.

Kết quả có thể được đối chiếu trực tiếp với giá trị text của từng nguồn.

### 5.2. Có thể dùng `@Value` thay thế không?

Có thể, nhưng ở đây chúng ta dùng **cả ba cách quan sát** (`Environment`, `@Value`, `@ConfigurationProperties`) để chứng minh chúng đều nhận giá trị hiệu lực từ cùng một hệ thống property sources trong lần khởi động.

Nếu một kết quả bất ngờ, hãy phân biệt lỗi resolve property khỏi lỗi bean registration hoặc binding.

---

## 6. Main class in cả giá trị hiệu lực lẫn dữ liệu từng kênh

Tạo `src/main/java/dev/example/configlab/ConfigSourceLabApplication.java`:

```java
package dev.example.configlab;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigSourceLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigSourceLabApplication.class, args);
    }

    @Bean
    ApplicationRunner showResolvedValue(
            Environment environment,
            LabProperties properties,
            @Value("${lab.message}") String injected) {

        return (ApplicationArguments args) -> {
            System.out.println("=== ONE KEY / FOUR SOURCES ===");

            System.out.println("resolved.environment = "
                    + environment.getProperty("lab.message"));

            System.out.println("resolved.configprops = "
                    + properties.message());

            System.out.println("resolved.value = "
                    + injected);

            System.out.println("raw.osEnvironment = "
                    + System.getenv("LAB_MESSAGE"));

            System.out.println("raw.jvmSystemProperty = "
                    + System.getProperty("lab.message"));

            System.out.println("raw.cliOption = "
                    + args.getOptionValues("lab.message"));

            System.out.println("==============================");
        };
    }
}
```

Những dòng `resolved.*` là **kết quả cuối** của Spring Boot đối với key đang xét:

```text
resolved.environment
resolved.configprops
resolved.value
```

Ba dòng `raw.*` giúp hiểu **những kênh riêng**:

```text
raw.osEnvironment
raw.jvmSystemProperty
raw.cliOption
```

Nếu kênh chưa được cung cấp, API có thể trả `null`. Nếu có CLI option, `args.getOptionValues("lab.message")` trả danh sách giá trị tương ứng. Bài này luôn dùng một option `--lab.message=...` trong mỗi lượt chạy.

**Chú ý:** Chương trình cố ý in toàn bộ giá trị của một **key giả, không nhạy cảm**. Không copy chiến lược này cho password, token, private key, connection URL chứa credential hoặc dữ liệu cá nhân. Trong production, chỉ nên log nguồn, tính hợp lệ hoặc phiên bản cấu hình đã được phê duyệt.

### 6.1. Kết quả ban đầu mong đợi

Nếu bạn không có biến `LAB_MESSAGE`, không có JVM `-Dlab.message`, không có CLI `--lab.message` và chưa có file ngoài:

```text
=== ONE KEY / FOUR SOURCES ===
resolved.environment = from-classpath
resolved.configprops = from-classpath
resolved.value = from-classpath
raw.osEnvironment = null
raw.jvmSystemProperty = null
raw.cliOption = null
==============================
```

Đây là baseline để so sánh các lượt tiếp theo.

### 6.2. Vì sao chỉ dùng một instance ứng dụng mỗi lượt?

`ApplicationRunner` chạy sau khi bean đã được tạo và bind. Mỗi lệnh `java -jar` tạo một process độc lập, do đó `-D`, environment variables và command-line args được áp dụng ngay từ đầu.

Nếu bạn muốn đổi một giá trị giữa lúc ứng dụng đang chạy, đó là bài toán **refresh**, không phải thí nghiệm precedence startup đơn giản này. Spring Boot thuần không mặc định tự nạp lại file và tạo lại mọi bean khi nguồn đổi.

---

## 7. Đóng gói JAR một lần, chạy nhiều lần

Để tránh trộn cấu hình của Gradle daemon với JVM application, hãy xây JAR trước:

**macOS/Linux:**

```bash
./gradlew clean bootJar
```

**Windows PowerShell:**

```powershell
.\gradlew.bat clean bootJar
```

Với build trên, artifact thường có đường dẫn:

```text
build/libs/config-source-lab-0.0.1-SNAPSHOT.jar
```

Sau khi build thành công, các lượt thí nghiệm sử dụng **chính JAR đó**.

macOS/Linux:

```bash
java -jar build/libs/config-source-lab-0.0.1-SNAPSHOT.jar
```

Windows PowerShell:

```powershell
java -jar .\build\libs\config-source-lab-0.0.1-SNAPSHOT.jar
```

Hãy thực hiện từ **thư mục gốc project** vì một số lần chạy dựa trên `./config/application.properties`. Nếu chạy từ working directory khác, Boot sẽ tìm đường dẫn `./config/` tương ứng với **directory hiện tại của process**, không nhất thiết là thư mục chứa file JAR.

### 7.1. Vì sao dùng `java -jar` cho thí nghiệm này?

Lệnh:

```bash
./gradlew bootRun -Dlab.message=from-jvm
```

không phải một minh họa đáng tin cậy về việc truyền system property tới **JVM ứng dụng**. `-D` trên dòng lệnh Gradle có thể được xử lý như system property của **Gradle process**, trong khi `bootRun` sử dụng một JavaExec task để khởi chạy ứng dụng. Muốn truyền system property tới app qua Gradle phải cấu hình task/jvmArgs thích hợp.

Với:

```bash
java -Dlab.message=from-jvm -jar app.jar
```

thì `-D` chắc chắn nằm ở **đối số JVM** đang chạy chính application.

Còn:

```bash
java -jar app.jar --lab.message=from-cli
```

thì `--lab.message=...` nằm ở **đối số ứng dụng**. Đây chính là hai kênh cần phân biệt.

### 7.2. Kiểm tra Java

```bash
java -version
```

Kỳ vọng Java 21 hoặc runtime mà artifact hỗ trợ. Nếu máy có nhiều bản Java, cần chắc chắn `java` ở terminal hiện tại trỏ tới bản đúng. Gradle toolchain khi build và Java runtime khi chạy JAR là hai điểm cần quan sát riêng.

---

## 8. Lượt 1 — Chỉ có file trong JAR

Điều kiện:

- Chưa tạo `config/application.properties` trong working directory.
- Không có `LAB_MESSAGE` được thiết lập.
- Không truyền `-Dlab.message`.
- Không truyền `--lab.message`.

Chạy:

```bash
java -jar build/libs/config-source-lab-0.0.1-SNAPSHOT.jar
```

Kỳ vọng:

```text
resolved.environment = from-classpath
resolved.configprops = from-classpath
resolved.value = from-classpath
raw.osEnvironment = null
raw.jvmSystemProperty = null
raw.cliOption = null
```

**Giải thích:** `src/main/resources/application.yaml` đã được đóng gói vào JAR và Spring Boot nạp Config Data từ classpath. Không có nguồn ưu tiên cao hơn đưa key `lab.message`, nên giá trị còn lại là `from-classpath`.

Nếu kết quả khác:

1. Kiểm tra có file cấu hình ngoài đang được nạp không.
2. Kiểm tra process có biến `LAB_MESSAGE` không.
3. Kiểm tra JVM được khởi chạy với system property nào.
4. Kiểm tra có CLI args nào được truyền qua script/IDE không.
5. Kiểm tra có `SPRING_APPLICATION_JSON` hoặc profile khác không.

Không sửa code ngay khi chưa xác minh nguồn dữ liệu runtime.

---

## 9. Lượt 2 — File cấu hình bên ngoài JAR

Spring Boot 3.3 mặc định tìm `application.properties` hoặc `application.yaml` ở một số vị trí bên ngoài JAR, trong đó có thư mục `./config/` ở working directory. Trong lab, dùng:

```text
./config/application.properties
```

**macOS/Linux:**

```bash
mkdir -p config
printf 'lab.message=from-file\n' > config/application.properties
```

**Windows PowerShell:**

```powershell
New-Item -ItemType Directory -Force -Path .\config | Out-Null
Set-Content -LiteralPath .\config\application.properties `
    -Encoding ASCII -Value 'lab.message=from-file'
```

Vì ví dụ chỉ có ký tự ASCII, PowerShell `-Encoding ASCII` giúp tránh BOM không mong muốn trong một file `.properties` khi dùng Windows PowerShell 5.1. Với ứng dụng thật cần Unicode, hãy chọn encoding được build/runtime hỗ trợ rõ ràng.

Chạy lại **cùng JAR**:

```bash
java -jar build/libs/config-source-lab-0.0.1-SNAPSHOT.jar
```

Kỳ vọng:

```text
resolved.environment = from-file
resolved.configprops = from-file
resolved.value = from-file
raw.osEnvironment = null
raw.jvmSystemProperty = null
raw.cliOption = null
```

### 9.1. Điểm cần quan sát

Bạn đã thay:

```text
Config source bên ngoài
```

chứ không sửa:

```text
Java source
Gradle build
JAR artifact
```

Giá trị đổi vì **Config Data bên ngoài JAR** được nạp và có precedence cao hơn tài liệu nền được đóng gói trong JAR trong cấu hình mặc định phù hợp.

Không cần:

- `@PropertySource` cho file `application.properties` mặc định.
- Custom `EnvironmentPostProcessor`.
- Spring Cloud Config Server.
- `@RefreshScope`.
- `@Value` field riêng cho từng nguồn.

### 9.2. Nếu file ngoài không thắng

Kiểm tra:

- `config/application.properties` có nằm dưới working directory hiện tại không.
- Tên file có đúng `application.properties`, không phải `applications.properties`.
- Property có đúng `lab.message` không.
- File có bị lưu thành `application.properties.txt` trên Windows không.
- Có một nguồn ưu tiên cao hơn cùng key hay không.
- Có `spring.config.location` làm thay đổi danh sách location không.
- Một profile-specific file hoặc import khác có đang tác động không.

Không kết luận external file bị bỏ qua chỉ từ việc giá trị cuối khác; có thể file đã được nạp nhưng bị một nguồn ưu tiên cao hơn ghi đè.

### 9.3. So sánh packaged YAML và external properties

Trong cùng một experiment:

```yaml
# Packaged application.yaml
lab:
  message: from-classpath
```

và:

```properties
# External config/application.properties
lab.message=from-file
```

Mặc dù hai file dùng **khác định dạng**, chúng vẫn biểu diễn cùng canonical property key `lab.message`.

Precedence không mặc định cho `.yaml` hay `.properties` ưu tiên tuyệt đối ở mọi nơi. **Vị trí, nhóm Config Data, profile, import và nguồn bên ngoài** là những yếu tố cần xét. Thí nghiệm cố ý đặt hai file ở **hai location khác nhau** để quan sát hiệu ứng external vs packaged, không phải tranh luận `.properties` và YAML khi ở cùng một location.

---

## 10. Lượt 3 — Biến môi trường OS ghi đè file

Giữ file ngoài:

```properties
lab.message=from-file
```

**Bash/macOS/Linux:**

```bash
LAB_MESSAGE=from-env \
  java -jar build/libs/config-source-lab-0.0.1-SNAPSHOT.jar
```

Cú pháp đặt biến ngay trước lệnh làm `LAB_MESSAGE` có hiệu lực trong **process được khởi chạy** mà không cần export lâu dài trong shell.

**Windows PowerShell:**

```powershell
$env:LAB_MESSAGE = 'from-env'
java -jar .\build\libs\config-source-lab-0.0.1-SNAPSHOT.jar
Remove-Item Env:LAB_MESSAGE
```

Kỳ vọng:

```text
resolved.environment = from-env
resolved.configprops = from-env
resolved.value = from-env
raw.osEnvironment = from-env
raw.jvmSystemProperty = null
raw.cliOption = null
```

**Giải thích:** `systemEnvironment` đóng góp `LAB_MESSAGE`; Spring Boot áp dụng quy tắc tra cứu và relaxed binding phù hợp để thấy `lab.message`. Nguồn OS environment có precedence cao hơn Config Data thông thường nên file `from-file` bị ghi đè.

### 10.1. Tại sao dùng `LAB_MESSAGE` chứ không phải `lab.message` làm tên biến?

Trên nhiều hệ điều hành và shell, tên biến môi trường thường được giới hạn bởi chữ, số và dấu gạch dưới. Spring Boot quy định cách biểu diễn environment variable cho tên property canonical:

1. Thay dấu chấm `.` bằng `_`.
2. Bỏ dấu gạch nối `-`.
3. Chuyển sang chữ hoa.

Ở đây:

```text
lab.message -> LAB_MESSAGE
```

Ví dụ phức tạp hơn:

```text
my.main-project.person.first-name
    -> MY_MAINPROJECT_PERSON_FIRSTNAME
```

Không chỉ đổi dấu gạch nối thành underscore một cách tùy tiện. Với relaxed binding vào `@ConfigurationProperties`, cần tuân thủ quy tắc tên environment variable của Spring Boot.

### 10.2. Biến môi trường không tự tạo Java system property

Dòng:

```text
raw.osEnvironment = from-env
```

và:

```text
raw.jvmSystemProperty = null
```

là **đúng**. Bạn chưa khai báo `-Dlab.message`, nên `System.getProperty("lab.message")` có thể là `null`.

Spring `Environment` hợp nhất thông tin từ nhiều nguồn cho nhu cầu binding; nó **không sao chép mọi biến môi trường sang `System.getProperties()`**.

### 10.3. Trường hợp `LAB_MESSAGE` vẫn không có hiệu lực

- IDE process chưa được cấu hình biến đó.
- Bạn thiết lập biến ở một terminal nhưng chạy JAR ở terminal khác.
- PowerShell session đã xóa biến trước khi khởi chạy.
- Biến nằm trong container nhưng đang kiểm tra process chạy trên host.
- Có `-Dlab.message` hoặc `--lab.message` ưu tiên cao hơn.
- Tên environment variable không tương ứng với canonical property đang đọc.

Để xác định nguồn, in `System.getenv("LAB_MESSAGE")` trong lab (chỉ với giá trị giả) là một phép thử tốt hơn việc suy đoán shell nào đã truyền biến.

---

## 11. Lượt 4 — JVM `-D` ghi đè biến môi trường

Giữ file ngoài `from-file`. Cùng lúc đặt:

```text
LAB_MESSAGE=from-env
```

và:

```text
-Dlab.message=from-jvm
```

**Bash/macOS/Linux:**

```bash
LAB_MESSAGE=from-env \
  java -Dlab.message=from-jvm \
  -jar build/libs/config-source-lab-0.0.1-SNAPSHOT.jar
```

**Windows PowerShell:**

```powershell
$env:LAB_MESSAGE = 'from-env'
java -Dlab.message=from-jvm `
  -jar .\build\libs\config-source-lab-0.0.1-SNAPSHOT.jar
Remove-Item Env:LAB_MESSAGE
```

Kỳ vọng:

```text
resolved.environment = from-jvm
resolved.configprops = from-jvm
resolved.value = from-jvm
raw.osEnvironment = from-env
raw.jvmSystemProperty = from-jvm
raw.cliOption = null
```

### 11.1. Giải thích từng dòng

- `LAB_MESSAGE` **vẫn tồn tại**, do đó `System.getenv()` tiếp tục trả `from-env`.
- JVM system property `lab.message` có giá trị `from-jvm`.
- Khi `Environment` resolve `lab.message`, Java system properties thắng OS environment trong thứ tự mặc định của Boot cho các nguồn này.
- `@Value("${lab.message}")` được resolve theo giá trị hiệu lực, do đó nhận `from-jvm`.
- Record `LabProperties` được bind cùng giá trị hiệu lực, do đó nhận `from-jvm`.

Bài học không phải “env var bị xóa” mà là **env var vẫn có, nhưng không thắng cạnh tranh precedence**.

### 11.2. Cú pháp `-D` phải trước `-jar`

Đúng:

```bash
java -Dlab.message=from-jvm -jar app.jar
```

Vì `-D...` là **JVM launcher option**.

Không sử dụng:

```bash
java -jar app.jar -Dlab.message=from-jvm
```

để minh họa Java system property, vì khi đặt sau tên JAR, chuỗi đó là một đối số ứng dụng thông thường. `System.getProperty("lab.message")` không được đặt bởi cách viết ấy.

Lệnh sai vị trí có thể khiến Spring Boot không nhận `lab.message` từ system properties, còn app chỉ thấy một argument không có dạng `--key=value` mà Boot mặc định dùng cho command-line properties.

### 11.3. `-D` của Gradle và `-D` của ứng dụng

Một lệnh như:

```bash
./gradlew bootRun -Dlab.message=from-jvm
```

thường được Gradle xử lý ở phía Gradle; không nên suy ra thuộc tính đó đã truyền vào JVM riêng chạy application.

Muốn chạy app qua Gradle và vẫn đặt JVM properties, có thể cấu hình JavaExec/BootRun task, ví dụ trong Gradle:

```groovy
tasks.named('bootRun') {
    systemProperty 'lab.message', 'from-jvm'
}
```

Nhưng khi đó property nằm **trong build script** và có thể khiến các lượt thí nghiệm tiếp theo bị ảnh hưởng. Vì vậy lab này dùng `java -D... -jar` để cô lập nguồn, không sửa build script giữa các lượt.

---

## 12. Lượt 5 — Dòng lệnh `--` ghi đè JVM property

Lượt này có **đủ bốn nguồn**:

1. External file `lab.message=from-file`.
2. OS environment `LAB_MESSAGE=from-env`.
3. JVM system property `-Dlab.message=from-jvm`.
4. Application argument `--lab.message=from-cli`.

**Bash/macOS/Linux:**

```bash
LAB_MESSAGE=from-env \
  java -Dlab.message=from-jvm \
  -jar build/libs/config-source-lab-0.0.1-SNAPSHOT.jar \
  --lab.message=from-cli
```

**Windows PowerShell:**

```powershell
$env:LAB_MESSAGE = 'from-env'
java -Dlab.message=from-jvm `
  -jar .\build\libs\config-source-lab-0.0.1-SNAPSHOT.jar `
  --lab.message=from-cli
Remove-Item Env:LAB_MESSAGE
```

Kỳ vọng:

```text
resolved.environment = from-cli
resolved.configprops = from-cli
resolved.value = from-cli
raw.osEnvironment = from-env
raw.jvmSystemProperty = from-jvm
raw.cliOption = [from-cli]
```

### 12.1. Bằng chứng trực tiếp về precedence

Bạn đang thấy **ba giá trị nguồn vẫn tồn tại**, nhưng **một giá trị hiệu lực** được chọn:

```text
OS environment:   from-env
JVM system prop:  from-jvm
CLI option:       from-cli
Spring resolved:  from-cli
```

File ngoài JAR vẫn có `from-file`, file trong JAR vẫn có `from-classpath`, nhưng chúng bị các nguồn ưu tiên cao hơn ghi đè.

Điều này minh họa:

```text
Những nguồn khác nhau có thể đồng thời có cùng key.
Nguồn ưu tiên cao nhất trong số những nguồn đang cung cấp key thắng.
Không phải nguồn còn lại bị xóa khỏi hệ thống.
```

### 12.2. Command-line args của ứng dụng, không phải args của Java launcher

Cần phân biệt:

```bash
java -Dlab.message=from-jvm -jar app.jar --lab.message=from-cli
```

Với:

- `-Dlab.message=from-jvm`: được JVM launcher xử lý.
- `-jar app.jar`: chọn artifact để chạy.
- `--lab.message=from-cli`: truyền cho `main(String[] args)` của ứng dụng, và Spring Boot mặc định thêm option này vào một property source.

Nếu bạn gọi:

```bash
java -Dlab.message=from-jvm --lab.message=from-cli -jar app.jar
```

thì `--lab.message` xuất hiện ở vị trí **Java launcher option**, có thể bị JVM từ chối. Đối số của ứng dụng phải nằm **sau** `-jar app.jar`.

### 12.3. `ApplicationArguments` cho ta biết điều gì?

Spring Boot tạo `ApplicationArguments`, trong đó `args.getOptionValues("lab.message")` trả danh sách giá trị của option ứng dụng nếu tồn tại.

Như vậy, lời gọi:

```java
args.getOptionValues("lab.message")
```

xác nhận rằng option `--lab.message=from-cli` thực sự đã đi vào ứng dụng.

Nhưng `ApplicationArguments` không phải một API để liệt kê mọi property source. Nó chỉ phân tích những arguments của lần chạy.

---

## 13. Lượt 6 — Gỡ từng nguồn để thấy thứ tự quay ngược

Sau khi chứng minh đủ bốn nguồn, ta gỡ dần để xem ai được chọn tiếp theo.

### 13.1. Bỏ CLI, giữ JVM và env

**Bash:**

```bash
LAB_MESSAGE=from-env \
  java -Dlab.message=from-jvm \
  -jar build/libs/config-source-lab-0.0.1-SNAPSHOT.jar
```

Kỳ vọng:

```text
resolved.environment = from-jvm
```

**Giải thích:** đã bỏ nguồn cao nhất là CLI, JVM system property là nguồn cao nhất còn lại.

### 13.2. Bỏ JVM `-D`, giữ env

**Bash:**

```bash
LAB_MESSAGE=from-env \
  java -jar build/libs/config-source-lab-0.0.1-SNAPSHOT.jar
```

Kỳ vọng:

```text
resolved.environment = from-env
```

**Giải thích:** OS environment thắng external Config Data.

### 13.3. Bỏ environment variable, giữ external file

**Bash:**

```bash
java -jar build/libs/config-source-lab-0.0.1-SNAPSHOT.jar
```

Kỳ vọng:

```text
resolved.environment = from-file
```

**Giải thích:** khi không còn env, JVM system property hoặc CLI option, file ngoài JAR cung cấp giá trị cao nhất trong nhóm còn lại.

### 13.4. Bỏ external file, quay về classpath

**Bash:**

```bash
mv config/application.properties config/application.properties.off
java -jar build/libs/config-source-lab-0.0.1-SNAPSHOT.jar
```

**Windows PowerShell:**

```powershell
Rename-Item -LiteralPath .\config\application.properties `
    -NewName 'application.properties.off'
java -jar .\build\libs\config-source-lab-0.0.1-SNAPSHOT.jar
```

Kỳ vọng:

```text
resolved.environment = from-classpath
```

Hãy khôi phục file khi cần thử tiếp:

```bash
mv config/application.properties.off config/application.properties
```

PowerShell:

```powershell
Rename-Item -LiteralPath .\config\application.properties.off `
    -NewName 'application.properties'
```

### 13.5. Vì sao cách gỡ ngược có giá trị?

Một bảng “CLI > JVM > env > file” dễ học thuộc. Nhưng việc **bỏ lần lượt từng nguồn** chứng minh:

- Các giá trị trước đó không bị xóa khỏi nơi khai báo.
- Giá trị thắng thay đổi theo **những nguồn hiện diện**.
- File cấu hình vẫn đóng vai trò fallback khi các nguồn runtime vắng mặt.
- Có thể chuyển giữa local/staging/production mà không rebuild JAR cho từng giá trị nhỏ.

Đây chính là ý tưởng quan trọng của **externalized configuration**.

---

## 14. Bảng kiểm thực nghiệm đầy đủ

Hãy điền bảng sau sau khi chạy mỗi lệnh:

| Lượt | Classpath YAML | External file | `LAB_MESSAGE` | JVM `-D` | CLI `--` | Kết quả cần thấy |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `from-classpath` | — | — | — | — | `from-classpath` |
| 2 | `from-classpath` | `from-file` | — | — | — | `from-file` |
| 3 | `from-classpath` | `from-file` | `from-env` | — | — | `from-env` |
| 4 | `from-classpath` | `from-file` | `from-env` | `from-jvm` | — | `from-jvm` |
| 5 | `from-classpath` | `from-file` | `from-env` | `from-jvm` | `from-cli` | `from-cli` |
| 6 | `from-classpath` | `from-file` | `from-env` | `from-jvm` | — | `from-jvm` |
| 7 | `from-classpath` | `from-file` | `from-env` | — | — | `from-env` |
| 8 | `from-classpath` | `from-file` | — | — | — | `from-file` |
| 9 | `from-classpath` | — | — | — | — | `from-classpath` |

Ở mỗi lượt, đối chiếu ba dòng:

```text
resolved.environment
resolved.configprops
resolved.value
```

Với một key scalar hợp lệ và bean đã được đăng ký, ba dòng thường giống nhau. Nếu khác, không vội quy lỗi cho thứ tự nguồn; có thể đã dùng sai placeholder, sai prefix, nhiều context hoặc có một bean bị tạo tại thời điểm khác.

### 14.1. Điều kiện để bảng có ý nghĩa

- Chạy **cùng một JAR** cho tất cả lượt.
- Dùng đúng working directory.
- Không bật profile khác ngoài ý định.
- Không có `SPRING_APPLICATION_JSON` chứa `lab.message`.
- Không có một wrapper/IDE tự chèn thêm `-D` hoặc CLI option.
- Không sửa file trong JAR giữa các lượt.
- Không thêm `@PropertySource` riêng cho cùng key.
- Không có provider Spring Cloud, Vault, Consul ghi đè key.
- Không chạy test harness đang tự áp dụng test property source ưu tiên cao.

Nếu những giả định khác đi, kết quả phải được phân tích theo **toàn bộ** nguồn thực tế, không chỉ bốn nguồn của bảng.

---

## 15. Cách đối chiếu trực tiếp bằng `Environment` và `PropertySource`

Để làm rõ hơn vì sao một key thắng, ta có thể quan sát danh sách các `PropertySource` của Spring tại runtime. Đây là công cụ **chỉ dùng trong local lab với key không nhạy cảm**.

Bạn có thể thay `Environment` trong runner bằng `ConfigurableEnvironment`:

```java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;
```

Sau đó, tại runner:

```java
for (PropertySource<?> source : environment.getPropertySources()) {
    Object candidate = source.getProperty("lab.message");

    if (candidate != null) {
        System.out.println("candidate.source = "
                + source.getName());
        System.out.println("candidate.value = "
                + candidate);
    }
}
```

**Lưu ý quan trọng:** `Environment` có thể chứa một số nguồn thích ứng hoặc tổng hợp, chẳng hạn `configurationProperties`, nên không phải mọi entry hiển thị theo cách hoàn toàn tương đương với một file gốc. Ngoài ra, các nguồn có thể sử dụng cơ chế tên property khác nhau. Do đó, hãy dùng đoạn code để **hỗ trợ quan sát**, không xem entry đầu tiên in ra luôn là một bản đồ chứng minh origin vật lý duy nhất của property.

Với source order thuần, bạn thường sẽ thấy các tên liên quan tới:

```text
commandLineArgs
systemProperties
systemEnvironment
Config resource 'file [.../config/application.properties]'
Config resource 'class path resource [application.yaml]'
```

Tên hiển thị chính xác phụ thuộc Spring Boot version, cấu hình load và môi trường. Chỉ ghi nhận **ý nghĩa** của nguồn, không phụ thuộc vào string hoàn toàn giống ví dụ.

### 15.1. `Environment` được resolve theo precedence

Một lời gọi:

```java
environment.getProperty("lab.message")
```

là API cần dùng khi bạn muốn biết **giá trị hiệu lực** tại thời điểm tra cứu.

Đoạn lặp `PropertySource` là công cụ phụ để xem các candidates. Nếu một source có alias hoặc wrapper, giá trị candidate có thể trùng với nguồn khác; không vì thế mà có hai giá trị đang được bind.

### 15.2. Origin tracking là thông tin bổ sung

Spring Boot Config Data có khả năng mang origin metadata cho một số property từ file. Các công cụ như Actuator `/env` có thể giúp điều tra nguồn và đường file, tùy endpoint exposure, bảo mật và sanitization.

Không bắt đầu một sự cố production bằng cách mở `/actuator/env` công khai hoặc log toàn bộ `PropertySources`. Trong lab, chúng ta chỉ in một key giả. Với secret thật, ngay cả key names và file paths cũng có thể nhạy cảm.

### 15.3. Vẫn cần phân biệt “candidate” và “effective value”

Ví dụ:

```text
file candidate:       from-file
environment candidate: from-env
system JVM candidate:  from-jvm
CLI candidate:         from-cli
```

thì:

```text
effective value:       from-cli
```

Đối chiếu nhiều candidates giúp hiểu **nguồn bị ghi đè** chứ không chỉ nguồn thắng.

---

## 16. Thử cùng một key qua `application.properties` và `application.yaml`

Bạn đã dùng:

```yaml
# Packaged application.yaml
lab:
  message: "from-classpath"
```

và:

```properties
# External config/application.properties
lab.message=from-file
```

Đây là hai cách biểu diễn tương đương của **cùng một khóa canonical**.

Trong YAML:

```yaml
lab:
  message: "hello"
```

được flatten về dạng property path:

```text
lab.message
```

Trong `.properties`:

```properties
lab.message=hello
```

Không có hai biến `lab` và `message` tách rời nhau trong ví dụ; `lab` là prefix và `message` là trường con.

### 16.1. Tại sao không đặt cả `application.yaml` và `application.properties` cùng thư mục để thử?

Spring Boot có quy tắc precedence riêng khi cả `.properties` và YAML cùng nằm ở một location. Một số phiên bản Boot ưu tiên `.properties` theo tài liệu. Nếu cùng lúc kiểm tra cả **format precedence** lẫn **source precedence**, kết quả dễ gây nhầm lẫn.

Trong bài này:

- YAML đóng gói trong JAR.
- Properties ở `./config/` ngoài JAR.
- Mỗi location chỉ có một file liên quan.
- Một key và năm nhãn phân biệt.

Cách tổ chức đó cô lập **nguồn gốc giá trị** rõ hơn.

### 16.2. Nếu muốn dùng external YAML

Thay file ngoài bằng:

```yaml
# ./config/application.yaml
lab:
  message: "from-file"
```

Về ý tưởng, external Config Data vẫn có thể ghi đè file packaged. Nhưng hãy chỉ giữ một dạng file liên quan trong một location khi làm thí nghiệm, tránh cuộc cạnh tranh phụ giữa hai định dạng.

---

## 17. Thử một file được chỉ định rõ bằng `spring.config.additional-location`

Trong bài chính, `./config/application.properties` được Spring Boot phát hiện theo các vị trí mặc định. Bạn cũng có thể chủ động chỉ định một thư mục khác.

Ví dụ tạo:

```text
./overrides/application.properties
```

với:

```properties
lab.message=from-file
```

Rồi chạy:

```bash
java -jar build/libs/config-source-lab-0.0.1-SNAPSHOT.jar \
  --spring.config.additional-location=optional:file:./overrides/
```

**PowerShell:**

```powershell
java -jar .\build\libs\config-source-lab-0.0.1-SNAPSHOT.jar `
  --spring.config.additional-location=optional:file:./overrides/
```

Với file ở đúng location, Boot có thể nạp thêm external Config Data. `additional-location` **bổ sung** search locations ngoài những vị trí mặc định. Trong khi đó, `spring.config.location` thay đổi các location mà Boot tìm (và có thể thay thế search locations mặc định), nên dùng sai có thể vô tình làm mất packaged file mà bạn đang dùng làm fallback.

Cần phân biệt:

```text
spring.config.location
spring.config.additional-location
spring.config.import
```

Chúng đều điều khiển Config Data loading nhưng không hoàn toàn giống nhau.

### 17.1. Dấu slash ở cuối directory có ý nghĩa

Khi cấu hình một **directory** bằng `spring.config.location` hoặc `spring.config.additional-location`, Spring Boot thường yêu cầu đường location kết thúc bằng `/` để phân biệt với một file.

Ví dụ:

```text
file:./overrides/
```

là directory location.

Còn:

```text
file:./overrides/application.properties
```

là một file location cụ thể.

Không dùng một đường dẫn Windows backslash nguyên dạng trong một chuỗi URI `file:` mà không xét cách escape/URI syntax; đường dẫn URL-style với slash `/` thường dễ portable trong Spring Boot config locations.

### 17.2. Có thể dùng environment để chỉ định search location

Ví dụ:

```bash
SPRING_CONFIG_ADDITIONALLOCATION=optional:file:./overrides/ \
  java -jar build/libs/config-source-lab-0.0.1-SNAPSHOT.jar
```

Cần dùng tên environment theo quy tắc bỏ dấu gạch nối và thay dấu chấm bằng underscore. `spring.config.additional-location` là một property ảnh hưởng rất sớm đến **quá trình tìm cấu hình**, nên nên đặt trong OS environment, JVM system property hoặc command-line args, không cố khai báo nó trong một file mà Boot chỉ tìm được sau khi biết location ấy.

Để thí nghiệm một khóa `lab.message` thuần, phần 17 là **mở rộng tùy chọn**, không cần áp dụng vào ma trận gốc.

---

## 18. Profile-specific files có thể bổ sung một tầng cạnh tranh khác

Giả sử ngoài file nền, bạn tạo:

```text
./config/application-dev.properties
```

với:

```properties
lab.message=from-dev-file
```

và bật:

```bash
java -jar build/libs/config-source-lab-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=dev
```

Trong phạm vi Config Data, file profile-specific có thể ghi đè file nền theo quy tắc profile của Spring Boot.

Tuy nhiên, nếu đồng thời đặt:

```bash
LAB_MESSAGE=from-env
```

thì **OS environment vẫn có precedence cao hơn Config Data thông thường** đối với cùng key, dù file đó là profile-specific.

### 18.1. Profile chọn tập Config Data, không biến file thành CLI

`application-dev.properties` vẫn là **file config**.

Nó không được đưa lên cấp ưu tiên giống Java system properties hay CLI chỉ vì tên chứa `dev`. Profile quyết định file/document nào được active và cách các Config Data documents cạnh tranh trong tầng của chúng.

Một hình dung:

```text
CLI -> JVM -> Environment -> Config Data
                              |
                              +-- profile-specific
                              +-- external vs packaged
                              +-- imports / document ordering
```

Các quy tắc cụ thể bên trong Config Data phức tạp hơn sơ đồ trên, nhưng điều đó không làm thay đổi phép so sánh cơ bản của bốn nguồn trong bài.

### 18.2. Vì sao không bật profile trong năm lượt gốc?

Mục tiêu là **giữ nguyên mọi biến trừ một nguồn đang được thêm hoặc gỡ**. Bật profile sẽ làm thay đổi cả tập Config Data, khiến ta khó chứng minh nguồn nào đang thắng.

Hãy hoàn thành ma trận gốc rồi mới thử profile như một bài bổ sung.

---

## 19. `SPRING_APPLICATION_JSON` nằm ngoài bốn nguồn nhưng cần biết

Spring Boot hỗ trợ nguồn đặc biệt `SPRING_APPLICATION_JSON`, chứa JSON được cung cấp qua environment variable hoặc system property theo cách framework cho phép.

Ví dụ:

```bash
SPRING_APPLICATION_JSON='{"lab":{"message":"from-json"}}' \
  java -jar build/libs/config-source-lab-0.0.1-SNAPSHOT.jar
```

Đối với các nguồn chuẩn ở Spring Boot 3.3, `SPRING_APPLICATION_JSON` có precedence **cao hơn** Java system properties và OS environment thông thường, nhưng **thấp hơn** command-line arguments.

Vì vậy, nếu CI hoặc platform đã đặt biến này mà bạn không biết, bảng bốn nguồn có thể không đúng kết quả dự đoán.

Đừng tự thêm JSON vào các lượt 1–5 khi chưa hoàn tất bài chính; đây là **một nguồn thứ năm** và sẽ làm mất khả năng so sánh một biến thay đổi mỗi lượt.

### 19.1. `null` trong JSON không phải phép xóa property nguồn dưới

Theo tài liệu Spring Boot, key có giá trị `null` được thêm vào property source từ JSON nhưng `PropertySourcesPropertyResolver` có thể coi null như một giá trị thiếu. Vì thế, đặt null trong `SPRING_APPLICATION_JSON` không phải cách chắc chắn để “xóa” một giá trị đã định nghĩa ở nguồn ưu tiên thấp hơn.

Nếu muốn vô hiệu hóa chức năng, tốt hơn là có một property boolean/enum có hợp đồng rõ, chẳng hạn:

```properties
lab.enabled=false
```

không dựa vào null như một lệnh override đặc biệt.

---

## 20. Command-line property của Spring Boot có thể bị tắt

Spring Boot mặc định thêm những arguments dạng:

```text
--name=value
```

vào `Environment`.

Tuy nhiên, một ứng dụng có thể cấu hình:

```java
SpringApplication app =
        new SpringApplication(ConfigSourceLabApplication.class);
app.setAddCommandLineProperties(false);
app.run(args);
```

Khi đó command-line property source **không còn được thêm theo cơ chế mặc định**, dù `ApplicationArguments` vẫn có thể thấy option.

Đây là một ví dụ để hiểu **kết quả bảng phụ thuộc cấu hình ứng dụng**. Không áp dụng thay đổi này vào main class của lab gốc; nếu muốn thử, hãy tạo bản thực hành riêng và khôi phục main class sau đó.

Một giá trị bị xem là không thắng không có nghĩa CLI parser bị hỏng; có thể chính ứng dụng đã tắt việc thêm command-line properties.

---

## 21. Có thể chạy với `bootRun` không?

Có. Spring Boot Gradle plugin cung cấp task `bootRun`, và bạn có thể truyền application arguments:

```bash
./gradlew bootRun --args='--lab.message=from-cli'
```

**PowerShell:**

```powershell
.\gradlew.bat bootRun --args="--lab.message=from-cli"
```

Lệnh trên phù hợp để thử **CLI option** với Gradle.

Nhưng khi mục tiêu là so sánh **Java system property của app** và **Java system property của Gradle**, dùng JAR có lợi thế minh bạch:

```bash
java -Dlab.message=from-jvm -jar app.jar
```

### 21.1. Hai JVM có thể khác nhau

Một lệnh `bootRun` có thể liên quan tới:

```text
Gradle client / daemon JVM
          |
          v
BootRun / JavaExec task
          |
          v
Application JVM
```

Không suy ra mọi `-D` ở command line Gradle đều truyền qua cho application JVM.

Nếu cần cố ý truyền property qua `bootRun`, dùng cấu hình Gradle task rõ ràng:

```groovy
tasks.named('bootRun') {
    systemProperty 'lab.message', 'from-jvm'
}
```

Hoặc sử dụng `jvmArgs` theo đúng API của task. Nhưng cách đó sửa định nghĩa build và sẽ tác động các lượt test tiếp theo nếu bạn quên bỏ đi.

### 21.2. Gradle environment cũng cần chú ý

Khi đặt environment variable ở shell chạy Gradle, task `bootRun` thường nhận môi trường từ process được tạo. Tuy nhiên, IDE/daemon/container wrapper có thể thay môi trường. Nếu kết quả bất ngờ, đối chiếu dòng `raw.osEnvironment` do chính **application** in ra, thay vì chỉ kiểm tra biến ở shell.

---

## 22. Một integration test về binding, và giới hạn của test đó

Tạo `src/test/java/dev/example/configlab/LabPropertiesTest.java`:

```java
package dev.example.configlab;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "lab.message=from-test"
})
class LabPropertiesTest {

    @Autowired
    LabProperties properties;

    @Test
    void bindsCanonicalProperty() {
        assertEquals("from-test", properties.message());
    }
}
```

Chạy:

**Bash:**

```bash
./gradlew test
```

**PowerShell:**

```powershell
.\gradlew.bat test
```

Test này kiểm tra việc **đăng ký và bind `@ConfigurationProperties`**, không phải thí nghiệm precedence bốn nguồn. `@SpringBootTest(properties=...)` đưa thêm **test-specific properties** với độ ưu tiên riêng; do đó kết quả `from-test` không mâu thuẫn với ma trận startup bằng `java -jar`.

Nếu muốn tự động hóa chính ma trận, cách phù hợp là một **integration script chạy JAR nhiều lần với environment và JVM args được kiểm soát**.

### 22.1. Vì sao không dùng một JUnit test có `System.setProperty()` cho mọi scenario?

Có thể viết test riêng kiểm tra system properties, nhưng cần xử lý:

- Lúc nào Spring application context được tạo?
- Context caching của Spring Test.
- Property precedence của test framework.
- Cleanup những system properties toàn JVM.
- Test chạy song song có dùng cùng global state không?
- Cấu hình outside `./config` có ảnh hưởng working directory của test không?

Nếu không kiểm soát các yếu tố đó, test có thể gây sai lệch so với một process `java -jar` bình thường. Bài thực hành dùng **mỗi lượt một process** để tránh nhầm lẫn.

---

## 23. Tự động hóa bằng Bash script cho macOS/Linux

Sau khi đã làm thủ công, có thể tạo `scripts/run-matrix.sh` để thử lại nhanh trên môi trường Bash. Script dùng một JAR, tạo external file và kiểm tra giá trị đã resolve.

```bash
#!/usr/bin/env bash
set -euo pipefail

JAR="build/libs/config-source-lab-0.0.1-SNAPSHOT.jar"

if [[ ! -f "$JAR" ]]; then
  echo "Build the JAR first: ./gradlew bootJar" >&2
  exit 1
fi

mkdir -p config
printf 'lab.message=from-file\n' > config/application.properties

run_case() {
  local expected="$1"
  shift

  local output
  output="$("$@")"

  printf '%s\n' "$output" |
    grep -F "resolved.environment = $expected" >/dev/null || {
      printf 'Expected: %s\n' "$expected" >&2
      printf '%s\n' "$output" >&2
      return 1
    }

  printf 'PASS: %s\n' "$expected"
}

# Lượt 2: file ngoài.
run_case from-file java -jar "$JAR"

# Lượt 3: biến môi trường.
run_case from-env env LAB_MESSAGE=from-env \
  java -jar "$JAR"

# Lượt 4: JVM system property.
run_case from-jvm env LAB_MESSAGE=from-env \
  java -Dlab.message=from-jvm -jar "$JAR"

# Lượt 5: đối số CLI.
run_case from-cli env LAB_MESSAGE=from-env \
  java -Dlab.message=from-jvm -jar "$JAR" \
  --lab.message=from-cli
```

Chạy:

```bash
chmod +x scripts/run-matrix.sh
./scripts/run-matrix.sh
```

Script sử dụng dữ liệu giả và không cần thông tin đăng nhập. Nó kiểm tra **effective value** trong stdout.

### 23.1. Lưu ý về tính độc lập

Nếu shell vốn có `LAB_MESSAGE` hoặc `SPRING_APPLICATION_JSON` đang được export, kết quả file-only có thể bị ảnh hưởng. Để có môi trường lặp lại, dùng một shell/container sạch hoặc xóa những biến liên quan trước khi chạy.

Có thể đặt:

```bash
unset LAB_MESSAGE
unset SPRING_APPLICATION_JSON
```

trong một shell thử nghiệm riêng, nhưng không làm điều đó một cách mù quáng trong terminal chứa thông tin vận hành quan trọng. Các process thực tế có thể cần environment variables khác, nên không dùng `env -i` nếu chưa hiểu các biến đường dẫn/JAVA_HOME cần thiết.

### 23.2. Script là một phép thử triển khai, không phải unit test

Một integration script tạo process và đọc stdout kiểm tra:

- JAR artifact chạy được.
- Config Data file ngoài được nạp.
- Env và JVM/CLI args tới đúng process.
- Kết quả resolve của Spring Boot đúng kỳ vọng.

Nó không thay thế unit test cho business logic và không kiểm tra tất cả profile/provider có thể tồn tại.

---

## 24. Tự động hóa bằng PowerShell trên Windows

Trong Windows PowerShell, có thể thực hiện lần lượt:

```powershell
$jar = '.\build\libs\config-source-lab-0.0.1-SNAPSHOT.jar'

New-Item -ItemType Directory -Force -Path '.\config' | Out-Null
Set-Content -LiteralPath '.\config\application.properties' `
    -Encoding ASCII -Value 'lab.message=from-file'

# File only:
Remove-Item Env:LAB_MESSAGE -ErrorAction SilentlyContinue
java -jar $jar

# Environment:
$env:LAB_MESSAGE = 'from-env'
java -jar $jar

# JVM property:
java -Dlab.message=from-jvm -jar $jar

# CLI có ưu tiên cao hơn:
java -Dlab.message=from-jvm -jar $jar --lab.message=from-cli

# Dọn môi trường sau khi thử:
Remove-Item Env:LAB_MESSAGE -ErrorAction SilentlyContinue
```

Quan sát `resolved.environment` sau mỗi lần:

```text
from-file
from-env
from-jvm
from-cli
```

Một khác biệt đáng chú ý giữa Bash và PowerShell là:

```bash
LAB_MESSAGE=from-env java -jar app.jar
```

là cú pháp Bash cho **một process**; PowerShell dùng:

```powershell
$env:LAB_MESSAGE = 'from-env'
java -jar app.jar
Remove-Item Env:LAB_MESSAGE
```

Nếu bạn chỉ gõ:

```powershell
LAB_MESSAGE=from-env
```

thì đó không phải cách chuẩn để cấp environment variable cho child process trong PowerShell.

### 24.1. Vì sao dùng `-ErrorAction SilentlyContinue` khi xóa biến?

Khi biến chưa tồn tại, lệnh xóa có thể báo lỗi không cần thiết. Ví dụ dùng tùy chọn này chỉ trong lab để cleanup một biến giả mà bài học vừa thiết lập.

Không dùng cleanup scripts để xóa hàng loạt biến môi trường của một terminal production.

---

## 25. Debug khi kết quả khác dự đoán

### 25.1. File ngoài JAR không được nạp

**Triệu chứng:** kỳ vọng `from-file`, nhận `from-classpath`.

Kiểm tra:

1. Working directory của process hiện tại.
2. Có thư mục `./config/` trong directory đó không?
3. Tên file là `application.properties` hay nhầm phần mở rộng?
4. File có key `lab.message` đúng không?
5. Có đang chạy một JAR khác build chưa cập nhật không?
6. Có `spring.config.location` đã thay thế default locations không?
7. Có một profile-specific document hoặc import khác đang đổi giá trị không?

Có thể bật trace logging riêng cho cơ chế Config Data khi cần:

```bash
java -jar build/libs/config-source-lab-0.0.1-SNAPSHOT.jar \
  --logging.level.org.springframework.boot.context.config=TRACE
```

Không log toàn bộ environment hoặc secret trong production để giải quyết vấn đề source loading. Chỉ bật TRACE có thời hạn và kiểm soát nơi log được lưu.

### 25.2. Đặt `LAB_MESSAGE` nhưng giá trị không thay

**Triệu chứng:** `raw.osEnvironment` là `null`.

Nguyên nhân có thể:

- Biến chưa export vào process.
- Terminal/IDE chạy app không phải terminal đã thiết lập biến.
- PowerShell dùng sai syntax.
- Docker/Kubernetes manifest không inject biến vào container hiện tại.
- Môi trường có chữ thường/chữ hoa khác kỳ vọng.

Nếu `raw.osEnvironment = from-env` nhưng resolved value không phải `from-env`, khả năng cao có một nguồn **ưu tiên cao hơn** cùng key, như JVM `-D` hoặc CLI option.

### 25.3. `-D` dường như không có tác dụng

**Triệu chứng:** `raw.jvmSystemProperty` là `null`.

Kiểm tra:

- `-D` nằm **trước** `-jar` không?
- Có đang truyền `-D` cho Gradle thay vì application JVM không?
- Bạn có dùng `java` launcher như trong ví dụ không?
- Có typo `-Dlab.message` thành `-Dlab-message` không?
- Có wrapper script sửa/thêm JVM arguments không?

Nếu `raw.jvmSystemProperty` đúng nhưng resolved value khác, kiểm tra có CLI option hoặc nguồn có precedence cao hơn.

### 25.4. CLI không thắng

**Triệu chứng:** có `--lab.message=from-cli` nhưng effective value khác.

Kiểm tra:

- Option có xuất hiện **sau** tên JAR không?
- Có đúng hai dấu `--` không?
- Main class có dùng `SpringApplication.run(...)` với args gốc không?
- Ứng dụng có gọi `setAddCommandLineProperties(false)` không?
- Có một test framework hoặc custom code thay đổi property sources không?
- Có nhiều lần khai báo cùng option khiến kết quả không như dự đoán không?

Trong lab, `raw.cliOption = [from-cli]` là một tín hiệu cho biết application đã nhận option đúng.

### 25.5. `@Value` khác `@ConfigurationProperties`

Có thể do:

- Placeholder khác canonical key.
- Sai prefix hoặc record chưa được đăng ký.
- Một bean được tạo tại thời điểm không như giả định.
- Dữ liệu thay đổi sau khi context startup và chỉ một nguồn được cập nhật.
- Converter hoặc custom Binding logic khác nhau.
- Một nơi đang đọc `System.getenv()` thay vì Spring `Environment`.

Trong lab với một scalar key, startup một lần và không có cơ chế refresh, ba dòng resolved phải cho cùng giá trị.

### 25.6. `System.getProperty` vẫn null dù Environment đúng

Đây có thể là **hành vi đúng** khi giá trị đến từ OS env hoặc file. Không có lý do để JVM properties tự được điền từ tất cả Config Data.

### 25.7. Dùng `config/application.properties` nhưng bị trùng định dạng

Nếu bạn cũng đặt `config/application.yaml` trong cùng location và cùng key, precedence giữa `.properties` và YAML cùng vị trí có thể ảnh hưởng kết quả. Đừng thêm file thứ hai trong một thí nghiệm vốn đang kiểm tra source precedence.

### 25.8. File đã sửa nhưng process đang chạy vẫn in giá trị cũ

Trong lab, mỗi lệnh tạo process mới. Nếu bạn sửa file **khi một process Spring Boot đang phục vụ**, không mặc định có live refresh. Config Data thường được nạp lúc startup; muốn áp dụng bản file mới, cần restart hoặc cơ chế reconfiguration được thiết kế.

Điều này không phải lỗi precedence. Nó thuộc **vòng đời nạp lại cấu hình**.

---

## 26. Liên hệ với IDE Run Configuration

Khi chạy project trong IntelliJ IDEA, Eclipse hoặc VS Code, giao diện Run Configuration thường có các trường tương tự:

```text
Environment variables
VM options
Program arguments
Working directory
```

Bốn trường này map sang những phần khác nhau:

| Trường IDE | Nguồn trong lab | Ví dụ |
| --- | --- | --- |
| Environment variables | OS environment | `LAB_MESSAGE=from-env` |
| VM options | JVM system property | `-Dlab.message=from-jvm` |
| Program arguments | Application CLI args | `--lab.message=from-cli` |
| Working directory | Vị trí tìm file ngoài JAR | Thư mục chứa `config/application.properties` |

Nếu bạn điền `-Dlab.message=from-jvm` vào **Program arguments**, nó không tự trở thành JVM property.

Nếu bạn điền `--lab.message=from-cli` vào **VM options**, Java launcher không xử lý option đó như một Spring Boot argument.

Nếu working directory là project module khác, file `./config/application.properties` của project root có thể không được tìm thấy.

### 26.1. Cách đối chiếu nhanh

Chạy cùng một cấu hình qua IDE và `java -jar`. Nếu kết quả khác, kiểm tra:

- Working directory.
- VM options.
- Program arguments.
- Environment variables.
- Active profiles.
- Artifact/classpath và version code đang chạy.
- IDE có sử dụng DevTools restart hoặc auto-build không.

Không suy luận precedence đã đổi chỉ vì đổi công cụ khởi chạy.

---

## 27. Liên hệ với Docker

Nếu đóng gói JAR vào image:

```dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY build/libs/config-source-lab-0.0.1-SNAPSHOT.jar app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Docker có thể cấp biến môi trường:

```bash
docker run --rm -e LAB_MESSAGE=from-env \
  config-source-lab:demo
```

Khi đó app sẽ thấy `LAB_MESSAGE` trong process.

Muốn thêm JVM system property:

```bash
docker run --rm -e LAB_MESSAGE=from-env \
  config-source-lab:demo \
  --lab.message=from-cli
```

Lưu ý nếu image dùng `ENTRYPOINT ["java","-jar","/app/app.jar"]`, Docker arguments sau tên image được nối vào **ENTRYPOINT** và trở thành application CLI args. Để truyền `-D` trước `-jar`, có thể thiết kế ENTRYPOINT/script phù hợp hoặc dùng `JAVA_TOOL_OPTIONS` với quản trị rõ ràng, nhưng `JAVA_TOOL_OPTIONS` có thể được JVM đọc và in một thông báo trong logs.

Bài học của container vẫn là:

```text
Image/JAR            -> code và packaged application.yaml
Environment          -> LAB_MESSAGE
JVM arguments        -> -Dlab.message
Application arguments -> --lab.message
Mounted config files -> ./config/application.properties hoặc configtree
```

Không vì chạy trong container mà thứ tự bốn nguồn chuẩn đột nhiên đảo ngược.

### 27.1. Tránh ghi secret lên dòng lệnh

Một giá trị đặt bằng CLI args hoặc `-D` có thể xuất hiện trong process list, diagnostics hoặc deployment manifest. Biến môi trường cũng có thể bị đọc qua hạ tầng/log/diagnostics nếu quyền không đúng.

Với secret production, nên dùng secret manager hoặc volume được bảo vệ, không đưa giá trị raw vào ví dụ precedence hoặc in ra console như lab.

---

## 28. Liên hệ với Kubernetes

Một Kubernetes Pod có thể được cấu hình:

```yaml
env:
  - name: LAB_MESSAGE
    value: "from-env"
```

Trong ứng dụng:

```java
System.getenv("LAB_MESSAGE")
```

sẽ thấy giá trị mà container nhận lúc khởi tạo.

Đồng thời, một ConfigMap có thể được mount vào một directory có file `application.properties`, hoặc dữ liệu được cung cấp qua `configtree:`. Những nguồn này có thể nằm trong Config Data theo cách application được cấu hình.

### 28.1. Thứ tự nguồn và thứ tự triển khai là hai khái niệm

Kubernetes ConfigMap update không đồng nghĩa JVM đang chạy tự cập nhật biến môi trường hay tự bind lại file. Một Pod đã tạo có environment snapshot riêng.

Thứ tự precedence trả lời:

> “Khi Spring Boot nạp và resolve, nguồn nào thắng?”

Còn triển khai trả lời:

> “Khi giá trị nguồn ngoài thay đổi, process đang chạy có nhận và áp dụng bản mới không?”

Hai vấn đề khác nhau. Đối với cấu hình quan trọng, rolling restart có kiểm soát thường đơn giản để đảm bảo process mới đọc đúng data revision.

### 28.2. Nếu dùng cả ConfigMap và env var

Giả sử:

```text
ConfigMap mounted file: lab.message=from-file
Pod environment:      LAB_MESSAGE=from-env
```

theo thứ tự tiêu chuẩn của bài, OS environment có thể thắng Config Data file.

Nếu một engineer sửa ConfigMap nhưng app vẫn có `LAB_MESSAGE`, họ có thể nhầm rằng mount không hoạt động. Trước khi debug volume, hãy xem **một key có được cấp từ nhiều nguồn không**.

---

## 29. Điều cần thận trọng khi có Spring Cloud Config, Consul hoặc Vault

Lab ban đầu là **Boot-only**. Khi thêm một provider remote, `spring.config.import` có thể đưa property sources mới vào `Environment`:

```yaml
spring:
  config:
    import: "optional:configserver:"
```

hoặc Consul/Vault import theo dependency và cấu hình tương ứng.

Lúc đó:

- Nguồn `lab.message` có thể nằm trong một remote Config Data document.
- Precedence phụ thuộc import ordering, provider-specific behavior và cấu hình override.
- Có thể có nhiều context/profiles/labels.
- Một update ở backend không tự đồng nghĩa bean trong process đã refresh.
- Secret management có yêu cầu phân quyền và audit riêng.

Đừng áp dụng ma trận chỉ có file-env-JVM-CLI cho hệ thống nhiều provider mà không kiểm tra những property sources đang hoạt động.

### 29.1. Vì sao nên học bốn nguồn trước?

Vì bốn nguồn có thể chạy **không cần mạng và không có service bên ngoài**. Bạn sẽ hiểu ý nghĩa của `Environment` và precedence trước khi thêm những tầng như Config Server, Consul, Vault, Kubernetes Secret hoặc Spring Cloud Refresh.

Điều này giảm số biến số khi gỡ lỗi một ứng dụng production: trước tiên xác định key có bị ghi đè ngay tại JVM/OS/CLI không, rồi mới tìm đến backend remote.

---

## 30. Chính sách đặt default và override trong ứng dụng thật

Một mô hình phù hợp là:

```text
Packaged application.yaml:
  default không nhạy cảm, an toàn

External file / profile:
  thông số triển khai cho từng môi trường

OS environment:
  override do platform cung cấp

JVM system property:
  override theo launcher / runtime (nếu dùng)

Application CLI:
  override tường minh khi khởi chạy
```

Tuy nhiên, việc một nguồn có precedence cao hơn không có nghĩa nó **được phép** override mọi key theo chính sách tổ chức.

Ví dụ:

- Một security setting production có thể cần khóa ở pipeline hoặc admission policy.
- Một database credential không nên dễ dàng bị thay bởi CLI do một người không đủ quyền.
- Một flag thay đổi schema dữ liệu cần rollout/review, không chỉ thay bằng environment variable.
- Một config mặc định quá permissive có thể khiến app chạy sai khi các nguồn cao hơn vắng mặt.

Thiết kế **quyền thay đổi cấu hình** nằm ngoài thứ tự tra cứu property của Boot. Cần kết hợp RBAC, quản lý secrets, CI/CD approvals và kiểm tra startup.

### 30.1. Không nên phụ thuộc mãi vào “CLI luôn thắng” để quản trị

Nếu nhiều nhóm đều có quyền sửa cùng key qua những nguồn khác nhau, họ có thể tạo xung đột khó audit. Hãy ghi rõ:

```text
lab.message:
  owner = learning-team
  default = application.yaml
  allowed overrides = dev/test/CI
  forbidden = real secret
```

Trong production, mỗi nhóm property quan trọng nên có owner, nguồn chính, quy tắc override và phương pháp rollback.

---

## 31. Bài tập mở rộng

### Bài A — Đoán kết quả trước khi chạy

Cho:

```properties
# file outside JAR
lab.message=A
```

```text
LAB_MESSAGE=B
```

```text
-Dlab.message=C
```

```text
--lab.message=D
```

Hãy viết:

1. Giá trị của `Environment.getProperty("lab.message")`.
2. Giá trị `System.getenv("LAB_MESSAGE")`.
3. Giá trị `System.getProperty("lab.message")`.
4. Kết quả `ApplicationArguments.getOptionValues("lab.message")`.

Sau đó chạy ứng dụng với đúng bốn nguồn để kiểm chứng.

### Bài B — Bỏ lần lượt nguồn

Từ trường hợp A, bỏ `--lab.message`, rồi `-Dlab.message`, rồi `LAB_MESSAGE`, sau đó file ngoài. Ghi kết quả sau mỗi lần và giải thích vì sao ứng dụng không phải rebuild JAR.

### Bài C — Sai vị trí tham số JVM

Thử:

```bash
java -jar app.jar -Dlab.message=from-jvm
```

so với:

```bash
java -Dlab.message=from-jvm -jar app.jar
```

Giải thích khác biệt. Hãy xác định `System.getProperty("lab.message")` có giá trị trong trường hợp nào.

### Bài D — Sai nơi khai báo IDE

Trong IDE, `--lab.message=from-cli` được đặt ở VM options, còn `-Dlab.message=from-jvm` được đặt ở Program arguments. Điều gì có thể xảy ra? Chuyển chúng về đúng ô và đối chiếu.

### Bài E — Đổi current working directory

Build cùng một JAR, đặt `./config/application.properties` ở project root rồi chạy JAR từ một thư mục khác. Vì sao file ngoài có thể không được tìm? Hãy dùng `--spring.config.additional-location=...` để chỉ định một location rõ ràng.

### Bài F — Environment variable và relaxed binding

Thay key bằng:

```text
demo.main-project.display-name
```

Hãy suy ra tên biến môi trường theo quy tắc của Spring Boot. Sau đó viết record và kiểm tra binder có nhận tên đó không.

### Bài G — Tạo trường hợp chỉ có file packaged

Xóa hoặc đổi tên file ngoài, xóa biến môi trường trong shell, bỏ `-D` và CLI. Chạy lại. Kết quả nào là fallback? Nếu fallback thiếu hẳn, hệ thống nên xử lý thế nào với một setting bắt buộc?

### Bài H — Thêm `SPRING_APPLICATION_JSON`

Đặt JSON cung cấp một giá trị thứ năm `from-json`, đồng thời giữ `LAB_MESSAGE=from-env` và `-Dlab.message=from-jvm`. Theo thứ tự chuẩn Boot 3.3, nguồn nào thắng khi không có CLI? Nếu có CLI, nguồn nào thắng?

### Bài I — Kiểm tra bean và Environment

Sửa runner để in thêm `LabProperties.message()`. Trên mọi trường hợp startup, nó có đồng ý với `Environment.getProperty("lab.message")` không? Nếu không, hãy kiểm tra bean registration và property naming.

### Bài J — Kịch bản Kubernetes

Giả sử ConfigMap mount file với value `from-file`, còn Deployment env đặt `LAB_MESSAGE=from-env`. Trong Pod mới, key nào có precedence cao hơn? Sau khi sửa ConfigMap, vì sao một Pod đang chạy có thể vẫn giữ `from-env`?

### Bài K — Một key là secret

Nếu `lab.message` được đổi thành `payment.gateway-token`, bạn sẽ thay đổi cách logging, cách cấp cấu hình và quyền truy cập ra sao? Vì sao không nên đưa token lên `-D` hoặc CLI rồi in ra stdout để chẩn đoán?

### Bài L — Tạo script kiểm tra kết quả

Viết một Bash hoặc PowerShell script chạy cùng JAR qua bốn trường hợp: file, env, JVM và CLI. Script phải kiểm tra output tương ứng và trả exit code khác 0 nếu một trường hợp không đạt.

---

## 32. Câu hỏi tự kiểm tra

**1.** Thứ tự precedence giữa CLI option, JVM system property, OS environment và Config Data thông thường trong Spring Boot 3.3 là gì?

**2.** Vì sao cùng một JAR có thể chạy với hai giá trị cấu hình khác nhau?

**3.** `System.getenv("LAB_MESSAGE")` có đọc được `-Dlab.message` không?

**4.** `System.getProperty("lab.message")` có tự đọc `application.yaml` không?

**5.** `Environment.getProperty("lab.message")` khác hai API Java ở điểm nào?

**6.** Vị trí đúng của `-Dlab.message` trong lệnh `java -jar` là trước hay sau `-jar`?

**7.** Vị trí đúng của `--lab.message` là trước hay sau tên JAR?

**8.** Tên environment variable tương ứng `lab.message` là gì?

**9.** Vì sao `lab.message` trong external file có thể ghi đè packaged YAML?

**10.** Nếu một key có trong env và file, `Environment` có ghép hai String vào nhau không?

**11.** Có bắt buộc phải có Cloud Config Server để Boot đọc external `application.properties` không?

**12.** Có cần một custom converter cho `String message` không?

**13.** Trong bài lab, `ApplicationArguments` đang cho biết gì?

**14.** Vì sao một lệnh Gradle có `-D...` không phải lúc nào cũng chứng minh property đã được truyền vào JVM application?

**15.** Nếu `System.getenv()` có `from-env` nhưng Spring resolved là `from-cli`, env có bị xóa không?

**16.** `SPRING_APPLICATION_JSON` có thể ảnh hưởng ma trận này không?

**17.** Nếu sửa external YAML khi process đang chạy, có mặc định rebind bean ngay không?

**18.** Một file `application-dev.properties` có cùng precedence tuyệt đối như CLI option không?

**19.** Tại sao cần kiểm tra working directory khi file nằm ở `./config/`?

**20.** Có nên in raw value của API token để chứng minh source precedence trong production không?

### Gợi ý đáp án

1. CLI cao nhất, rồi JVM system property, OS environment và Config Data.
2. Vì nguồn runtime có thể cấp hoặc ghi đè giá trị mà không thay binary.
3. Không; nó đọc OS environment.
4. Không; nó đọc JVM system properties.
5. Spring Environment hợp nhất nhiều property sources theo precedence.
6. Trước `-jar`.
7. Sau tên JAR.
8. `LAB_MESSAGE`.
9. Vì external Config Data ở location mặc định có thể ưu tiên hơn packaged resource.
10. Không với scalar String; nguồn cao hơn thắng.
11. Không; Boot core đã có Config Data.
12. Không.
13. Các option ứng dụng đã nhận qua `main(String[] args)`.
14. Có thể `-D` thuộc JVM của Gradle, không phải JVM chạy app.
15. Không; env vẫn tồn tại nhưng nguồn cao hơn được chọn.
16. Có; nó là một nguồn có precedence riêng.
17. Không mặc định; cần restart/refresh có chủ đích.
18. Không; vẫn là Config Data.
19. Location tương đối được resolve theo working directory của process.
20. Không; dùng dữ liệu giả, kiểm tra presence/origin có kiểm soát.

## 33. Checklist để áp dụng phương pháp vào công việc

Trước khi kết luận một property có nguồn sai:

- [ ] Ghi chính xác canonical key cần điều tra.
- [ ] Xác định effective value mà Spring đang đọc bằng một cách không lộ secret.
- [ ] Liệt kê các nguồn có thể chứa key này.
- [ ] Kiểm tra CLI arguments mà ứng dụng thật nhận được.
- [ ] Kiểm tra JVM system properties của process ứng dụng, không nhầm với Gradle.
- [ ] Kiểm tra OS environment được truyền vào process/container.
- [ ] Kiểm tra Config Data file trong và ngoài JAR.
- [ ] Kiểm tra working directory và custom config locations.
- [ ] Kiểm tra profile-specific documents và imports nếu có.
- [ ] Kiểm tra `SPRING_APPLICATION_JSON` hoặc test-specific properties.
- [ ] Kiểm tra `@ConfigurationProperties` prefix, record registration và `@Value` placeholder.
- [ ] Không nhầm file thay đổi với process đã refresh dữ liệu.
- [ ] Không in secret hoặc toàn bộ Environment vào log.
- [ ] Khi có remote providers, kiểm tra thêm precedence và refresh semantics của từng provider.
- [ ] Khi so sánh, chỉ thay một biến mỗi lượt.
- [ ] Dùng cùng JAR artifact cho các kịch bản kiểm chứng.
- [ ] Lưu lại expected/actual theo một ma trận có thể chạy lại.
- [ ] Nếu cần kiểm thử CI, chạy mỗi scenario trong process/environment độc lập.
- [ ] Có chính sách owner và quyền override cho các key quan trọng.
- [ ] Có fallback và validation an toàn khi một source vắng mặt.

## 34. Kết luận

Thí nghiệm một khóa đã cho một bằng chứng dễ quan sát:

```text
Packaged file:     lab.message=from-classpath
External file:     lab.message=from-file
OS environment:    LAB_MESSAGE=from-env
JVM property:      -Dlab.message=from-jvm
CLI option:        --lab.message=from-cli

Nếu tất cả cùng tồn tại trong khởi động chuẩn:
Effective value:   from-cli
```

Bỏ nguồn cao nhất đi, nguồn ưu tiên kế tiếp sẽ thắng. **Nguồn bị ghi đè vẫn tồn tại**; Spring Boot chỉ chọn giá trị hiệu lực theo `PropertySource` precedence.

Phân biệt rõ:

```text
System.getenv()         -> chỉ hỏi OS environment
System.getProperty()    -> chỉ hỏi JVM system properties
ApplicationArguments    -> mô tả arguments của app
Environment.getProperty -> resolve qua các Spring property sources
@ConfigurationProperties -> bind giá trị hiệu lực thành object có kiểu
@Value                  -> resolve placeholder qua bean container
```

Với cùng một source/binary, bạn có thể thay cấu hình theo môi trường hoặc theo lần khởi chạy mà không sửa code. Đây là lợi ích nền tảng của **Spring Boot Externalized Configuration**.

Nhưng đừng biến câu “CLI có ưu tiên cao” thành một chính sách vận hành ngầm: cần xác định owner, quyền override, bảo mật secrets, cách restart/refresh và các nguồn bổ sung trước khi áp dụng cho production.

### Tài liệu tham khảo

1. [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html): danh sách `PropertySource` và thứ tự ưu tiên, Config Data, location, `SPRING_APPLICATION_JSON`, command line và relaxed binding.
2. [Spring Boot 3.3 — Accessing Command Line Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.command-line-args): `--key=value` và `SpringApplication.setAddCommandLineProperties(false)`.
3. [Spring Boot 3.3 — Config Data Files](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.files): file YAML/properties, location mặc định, packaged vs external.
4. [Spring Boot 3.3 — Binding from Environment Variables](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.relaxed-binding.environment-variables): quy tắc dot/underscore/kebab-case và env.
5. [Spring Boot 3.3 — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): `@ConfigurationProperties`, constructor binding, `@Value`.
6. [Spring Boot Gradle Plugin — Running your Application](https://docs.spring.io/spring-boot/3.3/gradle-plugin/running.html): `bootRun` và truyền arguments qua Gradle.
7. [Oracle Java 21 Tool Documentation — java Launcher](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): `-Dproperty=value`, `-jar`, VM options và application arguments.
