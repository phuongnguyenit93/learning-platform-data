# Kiểm soát build.time và metadata thay đổi sau mỗi lần build

## 1. Vấn đề: cùng mã nguồn nhưng JAR có checksum khác

Một bản dựng **tái lập** (*reproducible build*) hướng đến mục tiêu: với **cùng mã nguồn, cùng input, cùng phiên bản công cụ và dependency đã được khóa**, ta có thể tạo lại artifact có nội dung **giống nhau từng byte**. Đây là nền tảng quan trọng khi kiểm chứng nguồn gốc phần mềm, so sánh checksum, xác minh release và sử dụng cache có thể tin cậy.

Spring Boot có thể tạo metadata tại `META-INF/build-info.properties`. Các thông tin như `build.artifact`, `build.group` và `build.version` thường không đổi giữa hai lần build cùng một commit. Nhưng `build.time` thường biểu diễn **thời điểm build thực tế**, nên thay đổi ở mỗi lượt chạy và làm file metadata khác đi, kéo theo **executable JAR khác checksum**. Ngoài metadata, ZIP/JAR entry timestamps, thứ tự entries, build number, CI run ID, timestamp trong manifest và các file được generate khác cũng có thể gây sai khác.

Tình huống minh họa:

~~~text
Git commit: abc123  (không thay đổi)
Project version: 1.0.0
Maven / Gradle / JDK / dependencies: giữ nguyên

Build A, 09:00:
  META-INF/build-info.properties
    build.version=1.0.0
    build.time=2026-11-09T02:00:00Z

Build B, 09:05:
  META-INF/build-info.properties
    build.version=1.0.0
    build.time=2026-11-09T02:05:00Z

=> Nội dung file khác.
=> JAR có thể khác checksum dù source không đổi.
~~~

**Điểm cốt lõi:** khi mục tiêu là **reproducibility**, không nhúng dữ liệu phụ thuộc thời gian chạy CI vào artifact; hoặc phải biến nó thành một **đầu vào bất biến, xác định trước**. Đặc biệt cần phân biệt **giá trị `build.time`** với **timestamp của các ZIP entries**: hai vấn đề độc lập, phải xử lý cả hai.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Giải thích `build.time`, `project.build.outputTimestamp`, archive-entry timestamp, build number và commit ID khác nhau ra sao.
2. Chọn chính sách metadata: **bỏ `build.time`**, hoặc **cố định từ một thời gian nguồn đã biết** thay vì lấy đồng hồ hiện tại.
3. Cấu hình Spring Boot Maven Plugin `build-info` dùng `<time>off</time>` và `project.build.outputTimestamp` cho packaging.
4. Cấu hình Gradle `bootBuildInfo` loại trừ `time`, đồng thời chuẩn hóa thứ tự và timestamp archive.
5. Viết ví dụ Java 17/Spring Boot 4.1.2 chạy được, kiểm tra `META-INF/build-info.properties` bằng JUnit và Java runtime.
6. So sánh **hai clean builds** bằng SHA-256 và so sánh byte, phân tích chính xác nơi phát sinh khác biệt.
7. Thiết kế metadata provenance ngoài artifact, tránh nhúng CI run ID, thời điểm build, hostname, đường dẫn workspace hay bí mật vào JAR.

**Bối cảnh của bài:** Spring Boot Build Tooling Packaging → *Bản dựng tái lập*. Ví dụ sử dụng Java 17, Spring Boot 4.1.2, Maven và Gradle Groovy DSL. Trong dự án thật, phải khóa đúng phiên bản plugin/Gradle wrapper/JDK/dependency theo chính sách.

## 2. Ba khái niệm thường bị đánh đồng

| Khái niệm | Nằm ở đâu? | Ý nghĩa | Có thể thay đổi theo mỗi lần build? |
| --- | --- | --- | --- |
| `build.time` | `META-INF/build-info.properties` | Một property do Spring Boot build-info tạo; có thể hiển thị qua Actuator | **Có**, nếu lấy wall clock |
| `project.build.outputTimestamp` | Cấu hình Maven | Timestamp ổn định dùng cho **JAR/ZIP entries** của plugin hỗ trợ; cũng có thể được Boot Maven build-info sử dụng | Nên **không** đổi khi input không đổi |
| ZIP/JAR entry timestamps | Metadata của từng entry trong archive | Thời gian được ghi ở định dạng ZIP/JAR | Có, nếu plugin giữ timestamp gốc |
| `build.version` | `build-info.properties` | Version của project | Không đổi nếu version là input cố định |
| `build.commit` (tùy biến) | Build metadata, manifest hoặc SBOM theo thiết kế | Git revision xác định source | Ổn định cho cùng commit |
| CI job ID / build number | CI system | Định danh **một lần thực thi pipeline** | **Có**, dù source giống nhau |
| Release/deployment timestamp | Hệ thống phát hành/vận hành | Thời điểm công bố hoặc triển khai | Có; không nhất thiết thuộc artifact |
| Hash SHA-256 của JAR | File/registry/attestation | Dấu vân tay của bytes artifact | Chỉ giống khi bytes giống |

**Ví dụ:** cố định `project.build.outputTimestamp` không tự sửa một file generated chứa `Instant.now()`. Ngược lại, bỏ `build.time` khỏi Spring metadata cũng không tự chuẩn hóa thời gian của từng entry trong archive. Cần xử lý ở cả **content layer** và **container/archive layer**.

### Mức độ tái lập cần kiểm chứng

- **Tính đúng chức năng:** hai bản build đều chạy và trả kết quả như nhau — chưa phải tái lập bytes.
- **Tính xác định của đầu vào:** cùng commit, cùng dependency versions/checksums, cùng JDK/toolchain và cấu hình — là điều kiện cần.
- **Tái lập metadata:** không chứa thông tin biến thiên vô lý; build-info, manifest, các generated resources nhất quán.
- **Tái lập từng byte:** hai JAR có **SHA-256 giống nhau** và `cmp` không tìm thấy byte khác. Đây là bằng chứng trực tiếp cho cặp build cụ thể, không phải lời hứa tự động cho mọi máy.

## 3. Spring Boot tạo `build-info.properties` như thế nào?

Spring Boot hỗ trợ tạo file:

~~~text
META-INF/build-info.properties
~~~

Các key chuẩn thường gồm:

~~~properties
build.group=dev.example
build.artifact=repro-demo
build.name=repro-demo
build.version=1.0.0
build.time=2026-11-09T02:00:00Z
~~~

Đây là **ví dụ có thời gian động**, không phải output của cấu hình tái lập sau này. Trật tự key trong file, escaping và comment không phải API contract nên khi viết test hãy đọc `java.util.Properties`, không so sánh file text theo một thứ tự cố định.

- Maven: goal `spring-boot:build-info` đọc thông tin `MavenProject`, tạo file ở `target/classes/META-INF/build-info.properties` (đường dẫn output mặc định), rồi file được đóng vào executable JAR khi packaging.
- Gradle: `springBoot { buildInfo() }` cấu hình task `bootBuildInfo`, tạo file `META-INF/build-info.properties` trong thư mục output của task. Với Spring Boot Gradle Plugin 4.1, output directory thông thường là `build/bootBuildInfo`; main source set resources nhận output này để đưa vào classpath/JAR. **Không mặc định file chỉ có ở `build/resources/main` trong 4.1.**
- Spring Boot Actuator có thể dùng build metadata để xuất thông tin ở `/actuator/info` nếu có starter/endpoint/exposure phù hợp. Việc metadata được hiển thị không biến nó thành thông tin bắt buộc phải chứa thời điểm build thực tế.
- Nếu code có `BuildProperties`, `getTime()` có thể không có giá trị khi `build.time` bị loại; code dùng thời điểm phải xử lý trường hợp vắng mặt thay vì giả định non-null.

### Những thuộc tính phù hợp để ghi vào artifact

| Thuộc tính | Phù hợp với reproducibility? | Điều kiện |
| --- | --- | --- |
| `build.version=1.0.0` | Có | Version không đổi giữa hai lần build cùng input |
| `build.group` / `build.artifact` / `build.name` | Có | Cấu hình dự án ổn định |
| `build.commit=<full Git SHA>` | Có | Nguồn Git revision bất biến và được truyền như một input có kiểm soát |
| `build.channel=stable` | Có | Channel được xác định từ quy tắc release/branch, không đổi tùy ý |
| `build.time=Instant.now()` | Không | Giá trị khác sau mỗi lần build |
| `build.job-id=CI_RUN_ID` | Không | Mỗi CI run có ID khác, kể cả khi commit giống nhau |
| `build.hostname` / `build.workspace` | Không | Phụ thuộc máy/runner |
| `build.random=UUID.randomUUID()` | Không | Không xác định |
| `build.timestamp=commitDate` | Có thể | Dùng thời gian commit có ý nghĩa rõ, bất biến và được xử lý đúng format |

**Không nên gọi thời gian commit là “thời điểm build thật”**. Nếu cần cả hai, hãy đặt **source/commit time** như một input ổn định trong provenance và ghi **CI execution time** vào log, CI run record hoặc attestation **ngoài artifact**.

## 4. Maven: `build.time` dùng time nào?

Theo Spring Boot Maven Plugin:

- Goal `build-info` có tham số `time`.
- Nếu `project.build.outputTimestamp` có giá trị, giá trị đó được dùng mặc định cho `build.time`.
- Nếu `project.build.outputTimestamp` chưa được đặt, plugin có thể dùng thời điểm bắt đầu Maven session — đây là giá trị thay đổi giữa những lần build.
- Muốn **bỏ `build.time` hoàn toàn**, cấu hình `<time>off</time>`. Có thể dùng `excludeInfoProperties` để loại `time`, nhưng `time=off` là cách ngắn, tường minh và được tài liệu plugin hỗ trợ.
- Muốn **giữ `build.time` với giá trị ổn định**, đặt một timestamp cố định phù hợp `Instant.parse(...)` và bảo đảm cả hai lần build cùng lấy nó; không dùng giờ hiện tại.

**Phân biệt:** `spring-boot:build-info` là goal **sinh metadata**, còn `spring-boot:repackage` là goal **đóng gói executable archive**. Không có mục tiêu nào thay thế nhiệm vụ của mục tiêu kia.

## 5. Maven POM hoàn chỉnh ưu tiên tái lập

Bài thực hành chọn **chính sách A: không đóng `build.time` vào JAR**, giữ metadata bất biến `build.version` và `build.channel`. Đồng thời khóa timestamp của JAR entries vào một giá trị ổn định.

Cấu trúc:

~~~text
repro-demo/
├── pom.xml
├── src/
│   ├── main/
│   │   ├── java/dev/example/repro/ReproDemoApplication.java
│   │   └── resources/application.properties
│   └── test/
│       └── java/dev/example/repro/BuildInfoTest.java
~~~

### 5.1. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>dev.example</groupId>
    <artifactId>repro-demo</artifactId>
    <version>1.0.0</version>
    <name>repro-demo</name>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <!-- Giá trị cố định làm ví dụ; production nên lấy từ source/release policy -->
        <project.build.outputTimestamp>1704067200</project.build.outputTimestamp>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <executions>
                    <execution>
                        <id>generate-build-info</id>
                        <goals>
                            <goal>build-info</goal>
                        </goals>
                        <configuration>
                            <time>off</time>
                            <additionalProperties>
                                <channel>stable</channel>
                            </additionalProperties>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Giải thích và chú ý kỹ thuật:**

1. Starter parent quản lý dependency/plugin versions và cấu hình execution `repackage`. Khi Boot Maven Plugin được khai báo, executable `target/repro-demo-1.0.0.jar` được tạo khi `package` chạy.
2. Execution `generate-build-info` gắn goal `build-info` vào Maven lifecycle theo **default phase của goal**; nó tạo `META-INF/build-info.properties` để các bước compile/test/package tiếp theo sử dụng. Không dùng lệnh `mvn spring-boot:build-info` riêng rồi giả định các resource đã được đóng vào JAR; `mvn clean verify` an toàn hơn.
3. `<time>off</time>` bảo đảm file generated **không có key `build.time`**. Đây là **nội dung**, không phải chỉ cách format ISO timestamp.
4. `<additionalProperties><channel>stable</channel></additionalProperties>` sinh key `build.channel=stable`; chỉ dùng giá trị ổn định, không lấy CI run ID tùy biến mỗi lần.
5. `project.build.outputTimestamp=1704067200` là **seconds since Unix epoch**, tức `2024-01-01T00:00:00Z`. Đây là mốc minh họa có chủ đích; nó **không phải giờ hiện tại**. Maven JAR Plugin và Spring Boot `repackage` hỗ trợ property này để ấn định timestamp cho ZIP/JAR entries.
6. Nếu dự án đặt `project.build.outputTimestamp` bằng mốc khác tại CI, hai build dùng hai mốc khác nhau vẫn có thể tạo archive khác nhau. Muốn tái lập **cùng một release**, policy phải cho cùng một giá trị khi input không đổi.
7. `java.version=17` chỉ định Java target theo parent. Để có reproducibility xuyên máy cao hơn, còn cần kiểm soát phiên bản JDK compiler, Maven và plugins, dependencies và environment.

**Cẩn trọng:** nếu thêm custom Maven resources filtering, manifest timestamp hoặc build number từ CI, chính chúng vẫn có thể làm artifact khác nhau dù POM ở trên không chứa `build.time`.

## 6. Ví dụ Java 17 và JUnit kiểm tra build-info không có thời gian động

Mục tiêu code: chạy Spring Boot như command-line application, đọc **file metadata thật** trên classpath, in ra version/channel và xác nhận `build.time` **vắng mặt**. Ví dụ không mở web server và kết thúc sau khi runner chạy xong.

### 6.1. `src/main/resources/application.properties`

~~~properties
spring.application.name=repro-demo
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=OFF
~~~

Những cấu hình này hạn chế log nền. **Không suy ra** JVM hoặc các thư viện sẽ tuyệt đối không phát thêm stderr/stdout.

### 6.2. `src/main/java/dev/example/repro/ReproDemoApplication.java`

~~~java
package dev.example.repro;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ReproDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReproDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner showBuildInfo() {
        return args -> {
            Properties properties = new Properties();

            try (InputStream input = getClass().getClassLoader()
                    .getResourceAsStream("META-INF/build-info.properties")) {
                if (input == null) {
                    throw new IllegalStateException("Missing build-info.properties");
                }
                properties.load(input);
            }

            System.out.println("BUILD_VERSION="
                    + properties.getProperty("build.version"));
            System.out.println("BUILD_CHANNEL="
                    + properties.getProperty("build.channel"));
            System.out.println("BUILD_TIME_PRESENT="
                    + properties.containsKey("build.time"));
        };
    }
}
~~~

Code chỉ dùng Java 17 API. `Properties#load(InputStream)` đọc cú pháp Java Properties của file generated; các giá trị ví dụ đều ASCII, không phát sinh lỗi mã hóa. `InputStream` lấy tài nguyên từ classpath, tương thích cả exploded classes directory và executable JAR.

**Ba dòng kết quả do code in khi cấu hình như mục 5:**

~~~text
BUILD_VERSION=1.0.0
BUILD_CHANNEL=stable
BUILD_TIME_PRESENT=false
~~~

Dòng `BUILD_TIME_PRESENT=false` là tiêu chí chính. Nếu bạn đã cấu hình `build-info` theo cách giữ thời gian cố định thay vì bỏ đi, dòng này sẽ thành `true`; không gọi đó là thất bại nếu policy đã đổi có chủ đích.

### 6.3. `src/test/java/dev/example/repro/BuildInfoTest.java`

~~~java
package dev.example.repro;

import java.io.InputStream;
import java.util.Properties;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class BuildInfoTest {

    @Test
    void buildInfoHasStablePropertiesAndNoBuildTime() throws Exception {
        Properties info = new Properties();

        try (InputStream input = getClass().getClassLoader()
                .getResourceAsStream("META-INF/build-info.properties")) {
            assertNotNull(input, "Build metadata missing from classpath");
            info.load(input);
        }

        assertEquals("repro-demo", info.getProperty("build.artifact"));
        assertEquals("1.0.0", info.getProperty("build.version"));
        assertEquals("stable", info.getProperty("build.channel"));
        assertFalse(info.containsKey("build.time"));
    }
}
~~~

Test đọc **resource đã được sinh ra trong lifecycle build**, không mở file `src/main/resources/META-INF/...` do người viết tay. Nhờ đó test phát hiện nếu goal/task `build-info` bị bỏ qua, resource thiếu, version sai hoặc `build.time` xuất hiện trở lại.

Trong dự án thật, test không nên hardcode `1.0.0` vĩnh viễn nếu version thay đổi thường xuyên; có thể truyền version kỳ vọng từ build input bằng một cách độc lập, tránh test chỉ xác nhận một giá trị bị copy từ cùng biến sai.

## 7. Chạy Maven và đọc đúng metadata

Tại thư mục có `pom.xml`:

~~~bash
java -version
mvn -version
mvn clean verify
~~~

Các file đáng kiểm tra:

~~~text
target/classes/META-INF/build-info.properties
target/repro-demo-1.0.0.jar
target/surefire-reports/TEST-dev.example.repro.BuildInfoTest.xml
~~~

Trong file `target/classes/META-INF/build-info.properties`, phải có các cặp key/value tương đương:

~~~properties
build.artifact=repro-demo
build.group=dev.example
build.name=repro-demo
build.version=1.0.0
build.channel=stable
~~~

**Không có `build.time`.** Thứ tự các dòng hoặc chú thích có thể khác và không nên dùng để đánh giá tính đúng của cấu hình. Việc file có thêm những key cố định khác không tự làm reproducibility thất bại, nhưng các key phải được xem xét theo nguồn giá trị.

Chạy artifact:

~~~bash
java -jar target/repro-demo-1.0.0.jar
~~~

Ba dòng do ứng dụng in:

~~~text
BUILD_VERSION=1.0.0
BUILD_CHANNEL=stable
BUILD_TIME_PRESENT=false
~~~

Kiểm tra archive trên Linux/macOS khi có `unzip`:

~~~bash
jar tf target/repro-demo-1.0.0.jar
unzip -p target/repro-demo-1.0.0.jar BOOT-INF/classes/META-INF/build-info.properties
~~~

**Chú ý cấu trúc:** trong executable Boot JAR, resource này nằm tại `BOOT-INF/classes/META-INF/build-info.properties`; còn khi Java code đọc qua ClassLoader, path logic là `META-INF/build-info.properties`. Không dùng `Path.of("src/main/resources/...")` để đọc nó sau khi package.

Nếu project không gắn goal `build-info`, file này **không được tạo mặc định chỉ vì có `spring-boot-starter`**. Bạn cần cấu hình goal/task tương ứng.

## 8. Maven: tách `build.time` và timestamp của JAR entries

Spring Boot Maven Plugin `repackage` hỗ trợ tham số `outputTimestamp`, mặc định tham chiếu `project.build.outputTimestamp`. Maven JAR Plugin cũng hỗ trợ property này. Khi dùng starter parent và plugin versions hỗ trợ, bạn có thể đặt:

~~~xml
<properties>
    <project.build.outputTimestamp>1704067200</project.build.outputTimestamp>
</properties>
~~~

Cách biểu diễn tương đương bằng ISO 8601 cũng được các plugin liên quan hỗ trợ:

~~~xml
<project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
~~~

**Chỉ chọn một cách** trong POM thực tế. Số `1704067200` ở ví dụ là Unix seconds, **không phải milliseconds**; đưa milliseconds sẽ sai đơn vị.

### Khi nào giữ `build.time` nhưng vẫn tái lập?

Nếu policy yêu cầu key `build.time` luôn tồn tại, có thể thay `<time>off</time>` trong execution `build-info` bằng:

~~~xml
<time>${project.build.outputTimestamp}</time>
~~~

với điều kiện `project.build.outputTimestamp` cố định. Khi đó file `build-info.properties` chứa `build.time` bằng mốc đã chọn, ổn định qua hai lần build dùng cùng input. **Nhưng nó không còn nhất thiết có nghĩa “thời điểm CI vừa thực thi”**. Hãy ghi rõ semantics của timestamp: ví dụ release-source timestamp hoặc một mốc đã được xác nhận trước.

Nếu không thiết lập `project.build.outputTimestamp` và để `build-info` dùng thời gian session, `build.time` có thể thay mỗi lần. Không lấy mỗi lần `date -u` mới rồi gán vào outputTimestamp nếu mục tiêu so sánh cùng commit: cách làm đó chỉ chuyển nguồn ngẫu nhiên từ file metadata sang property khác.

### `SOURCE_DATE_EPOCH` trong thực hành

`SOURCE_DATE_EPOCH` là quy ước phổ biến để biểu diễn timestamp nguồn ổn định dưới dạng **Unix seconds**. CI có thể lấy mốc từ commit/release policy rồi **truyền rõ** vào Maven:

~~~bash
mvn clean verify -Dproject.build.outputTimestamp=1704067200
~~~

Không khẳng định rằng mọi Maven plugin tự đọc biến môi trường `SOURCE_DATE_EPOCH`: **phải kiểm tra tài liệu từng plugin và cách CI chuyển giá trị**. Đồng bộ giá trị cho các plugin đóng gói/đóng tài nguyên là trách nhiệm cấu hình.

## 9. Gradle: `bootBuildInfo` và vì sao `time` phá incremental build

Spring Boot Gradle Plugin có DSL:

~~~groovy
springBoot {
    buildInfo()
}
~~~

Nó cấu hình task `bootBuildInfo`, tạo `META-INF/build-info.properties`. Theo tài liệu Spring Boot Gradle Plugin, mặc định `build.time` được lấy từ thời điểm build. Vì giá trị thay đổi theo đồng hồ, output của task cũng thay đổi; task có thể **không được xem là up-to-date** và kéo theo những tác vụ phụ thuộc (resource processing, test, packaging) phải thực hiện lại.

Spring Boot khuyến nghị loại bỏ thuộc tính `time` nếu ưu tiên hiệu năng và repeatability:

~~~groovy
springBoot {
    buildInfo {
        excludes = ['time']
    }
}
~~~

Khi đó vẫn có `build.version`, `build.group`, `build.artifact`, `build.name`, nhưng **không có `build.time`**.

### Timestamps và thứ tự entries trong Gradle archives

Theo hướng dẫn Gradle, từ **Gradle 9.0** các archive tasks có cấu hình reproducible mặc định (thứ tự file ổn định, timestamp cố định, quyền file được chuẩn hóa). Nếu project còn hỗ trợ Gradle 8.x, có thể cấu hình tường minh:

~~~groovy
tasks.withType(org.gradle.api.tasks.bundling.AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

Đoạn trên áp dụng cho nhiều archive tasks, bao gồm `jar` và `bootJar`. **Nó không vô hiệu hóa generated content động** như `build.time`, UUID hay CI run number. Vì thế vẫn cần `excludes = ['time']` hoặc giải pháp nội dung tương đương.

## 10. Ví dụ Gradle hoàn chỉnh, tương đương Maven

Dùng lại ba file Java/properties của mục 6; chọn **Gradle thay Maven** làm build tool chính cho project. Tạo:

**`settings.gradle`**

~~~groovy
rootProject.name = 'repro-demo'
~~~

**`build.gradle` (Groovy DSL)**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.2'
}

group = 'dev.example'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:4.1.2')
    testImplementation platform('org.springframework.boot:spring-boot-dependencies:4.1.2')
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}

springBoot {
    buildInfo {
        excludes = ['time']
        properties {
            additional = ['channel': 'stable']
        }
    }
}

tasks.withType(org.gradle.api.tasks.bundling.AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

**Vì sao các phần này cần thiết?**

- `java` cung cấp compile/test/resources tasks; `org.springframework.boot` cung cấp `bootJar`.
- `java.toolchain` yêu cầu Java 17 cho các tasks Java tương ứng. Phiên bản **Gradle runtime/daemon** vẫn phải tương thích với plugin/JDK; dùng Gradle Wrapper theo dự án.
- `platform(...)` dùng BOM để version của Spring Boot starters được quản lý; Boot Gradle Plugin tự nó không nên được xem là thay thế hoàn toàn việc quản lý dependency versions.
- `springBoot.buildInfo` cấu hình output `META-INF/build-info.properties`, bỏ `build.time` và thêm `build.channel=stable`.
- `preserveFileTimestamps=false` và `reproducibleFileOrder=true` chuẩn hóa archive entries. Trên Gradle 9+, các giá trị này đã là default cho archive tasks; khai báo tường minh hữu ích nếu project cần chạy cả Gradle 8.
- `test.useJUnitPlatform` cho phép JUnit Jupiter test `BuildInfoTest` được phát hiện.

### Chạy và kiểm tra

Nếu project đã có Gradle Wrapper:

~~~bash
./gradlew clean build
java -jar build/libs/repro-demo-1.0.0.jar
jar tf build/libs/repro-demo-1.0.0.jar
~~~

**Ba dòng kết quả do app in:**

~~~text
BUILD_VERSION=1.0.0
BUILD_CHANNEL=stable
BUILD_TIME_PRESENT=false
~~~

Đường dẫn task `bootBuildInfo` thường sinh metadata tại:

~~~text
build/bootBuildInfo/META-INF/build-info.properties
~~~

trong **Spring Boot Gradle Plugin 4.1.x**. Nội dung cũng được main resources classpath cung cấp và đưa vào executable archive tại `BOOT-INF/classes/META-INF/build-info.properties`. Khi kiểm tra dự án đang dùng phiên bản khác, không suy ra mọi Spring Boot Gradle Plugin version đều dùng cùng generated output directory.

Lệnh `./gradlew bootBuildInfo` chỉ tạo metadata, **không tương đương** toàn bộ build. `./gradlew bootJar` tạo executable nhưng không tự bảo đảm JUnit test chạy; dùng `./gradlew clean build` để thực hiện verification tasks đã gắn.

## 11. Chứng minh reproducibility bằng hai clean builds

Đánh giá bằng hash **chỉ có ý nghĩa nếu source và inputs được giữ cố định**. Ví dụ dưới đây xây hai lần **không thay source/config/dependency/JDK**, và kiểm tra cùng artifact:

### 11.1. Linux/macOS — Maven

Từ project root:

~~~bash
set -eu
CHECK_DIR="$(mktemp -d)"

mvn -q clean verify
cp target/repro-demo-1.0.0.jar "$CHECK_DIR/first.jar"

mvn -q clean verify
cp target/repro-demo-1.0.0.jar "$CHECK_DIR/second.jar"

sha256sum "$CHECK_DIR/first.jar" "$CHECK_DIR/second.jar"

if cmp -s "$CHECK_DIR/first.jar" "$CHECK_DIR/second.jar"; then
    echo "JAR_BYTES_IDENTICAL"
else
    echo "JAR_BYTES_DIFFER"
    exit 1
fi
~~~

**Output cuối cùng nếu bytes trùng khớp:**

~~~text
JAR_BYTES_IDENTICAL
~~~

`sha256sum` là lệnh phổ biến trên Linux; macOS có thể dùng `shasum -a 256`. Các dòng hash thực tế không được bịa sẵn: giá trị phụ thuộc toàn bộ bytes của artifact, còn `cmp` trực tiếp xác nhận hai file hoàn toàn giống nhau.

**Không xóa thư mục tạm tùy tiện.** Trong CI thật, tạo thư mục tạm trong phạm vi riêng của job rồi cleanup theo policy. Nếu JAR khác bytes, giữ cả hai để phân tích bằng `unzip`, `jar tf` và công cụ so sánh archive; đừng vội sửa timestamp mà chưa tìm file khác trước tiên.

### 11.2. Linux/macOS — Gradle

~~~bash
set -eu
CHECK_DIR="$(mktemp -d)"

./gradlew clean build
cp build/libs/repro-demo-1.0.0.jar "$CHECK_DIR/first.jar"

./gradlew clean build
cp build/libs/repro-demo-1.0.0.jar "$CHECK_DIR/second.jar"

sha256sum "$CHECK_DIR/first.jar" "$CHECK_DIR/second.jar"

if cmp -s "$CHECK_DIR/first.jar" "$CHECK_DIR/second.jar"; then
    echo "JAR_BYTES_IDENTICAL"
else
    echo "JAR_BYTES_DIFFER"
    exit 1
fi
~~~

Nếu Gradle local build cache phục hồi artifact thay vì thực hiện lại các bước cần thử, kết quả hash giống nhau **không chứng minh một fresh execution độc lập**. Trong kiểm thử nghiêm ngặt có thể chạy `--no-build-cache` và dùng runner/checkout độc lập theo policy. `clean` chỉ xóa build output của project, không tự vô hiệu hóa mọi remote/local cache.

### 11.3. Windows PowerShell

Sau khi build lần thứ nhất, copy JAR vào thư mục kiểm tra; build lần thứ hai rồi so SHA-256:

~~~powershell
$checkDir = Join-Path $env:TEMP ("repro-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $checkDir | Out-Null

mvn clean verify
if ($LASTEXITCODE -ne 0) { throw "First build failed" }
Copy-Item .\target\repro-demo-1.0.0.jar (Join-Path $checkDir "first.jar")

mvn clean verify
if ($LASTEXITCODE -ne 0) { throw "Second build failed" }
Copy-Item .\target\repro-demo-1.0.0.jar (Join-Path $checkDir "second.jar")

$first = (Get-FileHash (Join-Path $checkDir "first.jar") -Algorithm SHA256).Hash
$second = (Get-FileHash (Join-Path $checkDir "second.jar") -Algorithm SHA256).Hash

if ($first -eq $second) {
    "SHA256_MATCH=true"
} else {
    throw "SHA256_MATCH=false"
}
~~~

Đây là script cho **Maven** trên Windows; nếu dùng Gradle, thay hai lệnh build bằng `.\gradlew.bat clean build` và nguồn copy bằng `.\build\libs\repro-demo-1.0.0.jar`. `Get-FileHash` xác nhận checksum, `$LASTEXITCODE` kiểm tra lệnh build thành công.

### 11.4. Phân tích nếu hash khác

1. So `META-INF/build-info.properties` trong hai JAR, đặc biệt `build.time` và các custom keys.
2. So `META-INF/MANIFEST.MF` (build number, hostname, timestamp, classpath entries).
3. Kiểm tra ZIP/JAR entry timestamps và thứ tự entries bằng công cụ ZIP.
4. So generated resource files, annotation processor outputs, embedded Git metadata hoặc `application.properties` đã được resource filtering.
5. Kiểm tra source commit, git dirty state, JDK/compiler version, Maven/Gradle/plugin versions, dependency resolution và network input.
6. Kiểm tra locale/timezone, path, file permissions và OS nếu build trên máy khác.
7. Nếu cần, dùng công cụ như `diffoscope` để so binary archive; **đừng kết luận nguyên nhân chỉ từ một hash mismatch**.

**Lưu ý:** hai JAR trùng hash trên một runner chưa bảo đảm reproducible giữa Windows/Linux hoặc giữa nhiều JDK vendor/version. Đó là một mốc QA, không phải chứng minh tuyệt đối cho mọi môi trường.

## 12. Metadata nào được nhúng và metadata nào nên nằm bên ngoài?

| Metadata | Nguồn đề xuất | Vị trí nên lưu |
| --- | --- | --- |
| App version | Release POM/Gradle version | Trong artifact |
| Group/artifact/name | Cấu hình project ổn định | Trong artifact |
| Commit SHA | Git revision cố định của source | Có thể trong artifact hoặc provenance ngoài |
| Commit timestamp | Timestamp của commit, có semantics rõ | Có thể làm input ổn định, tránh gọi là thời điểm build thật |
| Dependency versions/checksums | Lockfiles/SBOM | SBOM, lock, provenance |
| CI run ID/job URL | CI pipeline | CI record hoặc attestation **ngoài JAR** |
| Build wall-clock time | Máy/runner CI | CI logs, artifact registry event, provenance **ngoài JAR** |
| Deployment timestamp | Deployment system | Release management/deployment records |
| Machine hostname/workspace | Runner | Tránh nhúng; thường không nên publish |
| Secrets/tokens | Secret manager | **Không bao giờ nhúng vào build-info.properties** |

### Build provenance có thể giải quyết nhu cầu audit

Việc bỏ `build.time` **không đồng nghĩa mất khả năng truy xuất**. Một quy trình phát hành có thể lưu:

~~~text
artifact:
  name: repro-demo-1.0.0.jar
  sha256: <được tính từ chính artifact>
source:
  git_commit: <full SHA>
toolchain:
  java: <JDK version>
  maven_or_gradle: <version>
execution:
  ci_run_id: <run identifier>
  started_at: <actual UTC timestamp>
~~~

Đây là **sơ đồ minh họa trường dữ liệu**, không phải file đã được tạo hoặc một định dạng attestation tiêu chuẩn hoàn chỉnh. CI có thể lưu thông tin này thành provenance attestation và liên kết nó bằng digest artifact. Nhờ vậy hai lần rebuild cùng source vẫn có thể tạo **JAR byte-identical**, trong khi mỗi lượt chạy CI vẫn có một execution record riêng.

### Khi cần commit hash bên trong JAR

Nếu version hoặc commit phải được hiển thị lúc runtime, chọn giá trị bất biến từ **chính commit được checkout**, không dùng `CI_PIPELINE_ID` hay thời điểm hiện tại. Đảm bảo CI truyền cùng Git SHA ở hai lần build cùng commit.

**Không dùng random UUID làm build ID trong tài nguyên được đóng gói** nếu mục tiêu là tái lập. Có thể định danh artifact bằng hash hoặc cặp `version + commit` mà không cần sinh số ngẫu nhiên ở mỗi lần build.

## 13. Rủi ro khác ngoài `build.time`

### 13.1. Snapshot và dynamic dependencies

Dùng `1.2.+`, `latest.release` hoặc SNAPSHOT không được khóa có thể resolve bytes khác khi repository thay đổi. Ngay cả khi `build.time` bị loại và archive timestamps cố định, hai build có dependencies khác nhau vẫn khác.

**Hướng xử lý:** pin versions, dùng dependency locking/verification, repository policy và lưu resolved dependency graph theo toolchain.

### 13.2. Build plugin / Java vendor thay đổi

Cùng Java release target `17` không nhất thiết bảo đảm bytecode giống nhau giữa mọi JDK patch/vendor. Maven/Gradle, annotation processors, compiler options và plugin versions cũng là build inputs.

**Hướng xử lý:** dùng Maven/Gradle wrapper khi có, quản lý JDK toolchain/CI image và pin plugin versions. Kiểm tra output ở môi trường tái lập độc lập.

### 13.3. Generated source và environment leakage

File được sinh từ `new Date()`, `System.currentTimeMillis()`, `Instant.now()`, `UUID.randomUUID()`, build number, hostname, absolute path hoặc file ordering không ổn định vẫn làm JAR khác nhau. Annotation processors cũng có thể sinh timestamp/comment.

**Hướng xử lý:** tránh lấy wall clock trong generated files; định nghĩa thứ tự ổn định, truyền giá trị từ input bất biến và review các custom tasks/plugins.

### 13.4. Docker image và JAR là hai đối tượng khác

Ngay cả khi JAR byte-identical, container image có thể có metadata creation time, layer order, base image digest hoặc file ownership khác. `docker build` thành công không tự chứng minh **image** reproducible.

**Hướng xử lý:** đánh giá reproducibility riêng ở cấp JAR và image, pin base image digest khi cần, lưu provenance và so digest của đúng đối tượng cần phát hành.

### 13.5. Tính tái lập khác với tính an toàn

Hai bản build cùng hash không tự bảo đảm không có lỗ hổng, dependency độc hại hoặc source có bản quyền hợp lệ. Reproducibility là một bằng chứng về **tính nhất quán của quy trình**, cần đi cùng vulnerability scanning, SBOM, code review và kiểm tra provenance.

## 14. Bảng lỗi thường gặp và hướng sửa

| Triệu chứng | Giả thuyết có khả năng | Kiểm tra và sửa |
| --- | --- | --- |
| Hai JAR khác hash, `build.time` khác | Build-info dùng thời gian hiện tại | Maven `<time>off</time>`; Gradle `excludes=['time']` |
| Maven đã đặt `outputTimestamp` nhưng metadata vẫn khác | Custom resources/manifest dùng thời gian khác, hoặc property bị override | So `build-info.properties`, effective POM và CI arguments |
| Maven `build.time` vẫn có dù muốn bỏ | Execution `build-info` không nhận configuration đúng | Xem Maven goal/execution, đúng tag `time` và generated file |
| Gradle `bootBuildInfo` luôn chạy lại | Default `build.time` từ wall clock | Exclude `time`, kiểm tra task inputs/output |
| Gradle `bootJar` khác dù build-info giống | Archive timestamps/order, dependencies, generated files | Kiểm tra `preserveFileTimestamps`, `reproducibleFileOrder` và resolved graph |
| JAR có timestamps khác nhưng nội dung resources giống | ZIP entry metadata không được normalize | Maven `outputTimestamp` / Gradle archive settings |
| `BuildProperties.getTime()` trả null | `build.time` được cố ý bỏ | Xử lý optionality trong code; không giả định time luôn tồn tại |
| `META-INF/build-info.properties` không có | Goal/task chưa bind hoặc output không được package | Maven `build-info`, Gradle `bootBuildInfo` và classpath |
| Runtime còn timestamp cũ sau build mới | Chạy artifact cũ hoặc incremental output stale | Kiểm tra JAR đang chạy, clean build có chủ đích, classpath |
| Version hoặc commit khác khi cùng source | CI override property, repo checkout/tag khác | So exact inputs, git SHA và release policy |
| Hai build cùng runner trùng hash nhưng máy khác không | Toolchain/OS/locale/permissions khác | Cố định toolchain, môi trường và kiểm chứng cross-runner |
| Build cache làm test so hash luôn trùng | Cả hai lấy lại cùng cached artifact | Dùng clean runner/cấm cache nếu cần kiểm tra rebuild thực |
| `build-info.properties` có hostname/run ID | Custom additionalProperties lấy env động | Dời execution metadata ra provenance ngoài JAR |
| CI audit không thấy thời gian sau khi bỏ `build.time` | Thời gian chỉ lưu trong artifact trước đây | Ghi CI run record và liên kết digest với provenance |
| Test so file text bị fail do thứ tự key | Java Properties không bắt buộc có trật tự key nhất định | Parse bằng `Properties`, assert key/value và key absence |
| Test pass nhưng executable JAR chưa được kiểm | Test đọc `target/classes` hoặc Gradle generated output | `jar tf`, `unzip -p`, `java -jar` và so hash artifact |

**Quy trình chẩn đoán:** (1) kiểm tra file generated → (2) kiểm tra nội dung file trong packaged JAR → (3) kiểm tra ZIP entry metadata → (4) so dependency graph/toolchain → (5) so hai clean builds độc lập. Sửa **điểm đầu tiên tạo ra sự khác biệt**, không thay đổi mọi cấu hình cùng lúc.

## 15. Checklist triển khai vào pipeline

- [ ] Xác định mục tiêu là **functional equivalence** hay **byte-for-byte identical JAR**.
- [ ] Pin source commit, dependency graph, plugins và toolchain versions.
- [ ] Maven: goal `build-info` sinh metadata; `<time>off</time>` nếu ưu tiên tái lập.
- [ ] Maven: đặt `project.build.outputTimestamp` từ nguồn **ổn định**, không lấy wall clock của mỗi CI run.
- [ ] Gradle: `springBoot.buildInfo { excludes = ['time'] }`.
- [ ] Gradle: archive tasks có `preserveFileTimestamps=false`, `reproducibleFileOrder=true` (đặc biệt trước Gradle 9).
- [ ] Không nhúng run ID, random UUID, hostname, workspace path hoặc timestamp động vào manifest/resources.
- [ ] Dùng commit SHA/version làm metadata ổn định khi được quản lý đúng.
- [ ] Lưu CI build time, job ID và provenance **ngoài JAR** nhưng có liên kết tới digest.
- [ ] Unit test xác minh `build-info.properties` có các key mong muốn và **không có `build.time`** theo policy.
- [ ] Kiểm tra file generated và entry `BOOT-INF/classes/META-INF/build-info.properties` trong JAR.
- [ ] Chạy ứng dụng và xác nhận output runtime phù hợp.
- [ ] Thực hiện **hai clean builds** với input cố định; so SHA-256 và bytes của đúng JAR.
- [ ] Khi hash khác, dùng diff/ZIP inspection để tìm file hoặc metadata gây biến thiên.
- [ ] Kiểm tra Gradle build cache, Maven local repo và network inputs không che việc thử tái lập.
- [ ] Không đánh đồng reproducibility của JAR với reproducibility của container image.

**Ghi nhớ:** **`build.time` là giá trị nội dung; `outputTimestamp` và Gradle archive options điều khiển metadata ZIP/JAR.** Nếu cần hai bản build cùng source cho ra cùng digest, xử lý cả hai và đưa các thông tin **chỉ thuộc một lượt CI** ra khỏi artifact.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Đặt `project.build.outputTimestamp` cố định nhưng giữ một generated file có `Instant.now()`. JAR có chắc tái lập không?

**Đáp án:** Không. ZIP timestamps được cố định nhưng file generated có nội dung động, làm archive bytes khác.

**Câu 2.** Maven `spring-boot:build-info` lấy `build.time` từ đâu khi không có `project.build.outputTimestamp`?

**Đáp án:** Thường từ thời điểm bắt đầu Maven session theo plugin; giá trị có thể khác giữa hai lần build.

**Câu 3.** Cách tắt `build.time` trong Maven mà không tắt hẳn build info?

**Đáp án:** Trong configuration của `build-info` goal đặt `<time>off</time>`. Các key như `build.version` vẫn được tạo.

**Câu 4.** Cách loại bỏ `build.time` khỏi Gradle `bootBuildInfo`?

**Đáp án:** `springBoot { buildInfo { excludes = ['time'] } }`.

**Câu 5.** Vì sao build-info time làm Gradle incremental build kém hiệu quả?

**Đáp án:** Giá trị thay đổi theo wall clock làm output của task thay đổi; các task phụ thuộc có thể không up-to-date.

**Câu 6.** `project.build.outputTimestamp=1704067200` có đơn vị gì?

**Đáp án:** **Seconds since Unix epoch**, tương đương 2024-01-01T00:00:00Z; không phải milliseconds.

**Câu 7.** Muốn có thời gian phát hành thật nhưng không thay checksum JAR, làm gì?

**Đáp án:** Ghi thời gian phát hành/CI run vào external provenance/registry/log liên kết với digest artifact, không nhúng thời gian đó vào JAR.

**Câu 8.** Hai JAR có hash trùng trên một máy có chứng minh tái lập trên mọi máy không?

**Đáp án:** Chưa. Cần thử trong môi trường/runner độc lập, pin JDK/plugin/dependencies và kiểm tra OS-dependent inputs.

**Câu 9.** Thêm `build.commit` có phá reproducibility không?

**Đáp án:** Không nếu đó là Git revision bất biến, giống nhau cho cùng source. Có thể phá nếu lấy một giá trị biến thiên như build number hoặc dirty working tree metadata không kiểm soát.

**Câu 10.** Vì sao không nên dùng `java.util.Properties` text order làm kiểm tra?

**Đáp án:** Thứ tự xuất key không phải là hợp đồng API ổn định; test nên parse key/value và xác minh các thuộc tính cần/không cần có.

## 17. Tài liệu tham khảo chính thức

1. [Spring Boot Maven Plugin 4.1 — Generating Build Information](https://docs.spring.io/spring-boot/maven-plugin/build-info.html)
2. [Spring Boot Maven Plugin — Repackage / outputTimestamp](https://docs.spring.io/spring-boot/maven-plugin/packaging.html)
3. [Spring Boot Gradle Plugin 4.1 — Integrating with Actuator / bootBuildInfo](https://docs.spring.io/spring-boot/gradle-plugin/integrating-with-actuator.html)
4. [Spring Boot Gradle Plugin — BuildInfo Task API](https://docs.spring.io/spring-boot/gradle-plugin/api/java/org/springframework/boot/gradle/tasks/buildinfo/BuildInfo.html)
5. [Maven JAR Plugin — jar Goal / outputTimestamp](https://maven.apache.org/plugins/maven-jar-plugin/jar-mojo.html)
6. [Gradle — Working with Files / Reproducible Archives](https://docs.gradle.org/current/userguide/working_with_files.html)
7. [Gradle — Best Practices for Security: Reproducible Builds](https://docs.gradle.org/current/userguide/best_practices_security.html)
8. [Spring Boot — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
9. [Reproducible Builds Project — SOURCE_DATE_EPOCH](https://reproducible-builds.org/docs/source-date-epoch/)
