# Giới hạn tương thích của launch script với công cụ đọc JAR và chế độ trích xuất

## 1. Mục tiêu

Spring Boot có thể đóng gói ứng dụng thành **executable JAR** chạy bằng `java -jar` mà không cần cài Gradle hay Maven trên máy triển khai. Ngoài ra, plugin đóng gói của Spring Boot hỗ trợ **fully executable archive**: một shell launch script được thêm vào **đầu chính tệp JAR/WAR**. Trên Unix/Linux thích hợp, file đó có thể được chạy trực tiếp như một script hoặc sử dụng trong mô hình service.

Sự tiện lợi này có đánh đổi: file có **bytes script đứng trước ZIP/JAR archive**, khiến một số công cụ đọc ZIP/JAR không chấp nhận định dạng. Spring Boot 3.3 cảnh báo `jar -xf` có thể **thất bại âm thầm** khi giải nén fully executable archive. Đồng thời, tài liệu Spring Boot 3.3 xác nhận chế độ **`-Djarmode=tools` không dùng được với archive có launch script**. Nếu hệ thống cần extract JAR để xây image hoặc kiểm tra nội dung, **đừng bật launch script** trên artifact đưa vào bước trích xuất.

Sau bài này, bạn sẽ:

- Phân biệt regular/“plain” JAR, Spring Boot executable JAR tiêu chuẩn và fully executable JAR có shell prefix.
- Giải thích được nguồn gốc hạn chế của `jar -tf`/`jar -xf`, ZIP readers, tools extraction và container image pipeline.
- Cấu hình launch script đúng bằng Gradle Groovy/Kotlin DSL và Spring Boot Maven Plugin; biết cách tắt khi cần tương thích.
- Tạo, chạy, lưu hai biến thể JAR của cùng ứng dụng Java 17, tự kiểm tra byte-prefix và xác minh kết quả giải nén.
- Chọn định dạng phù hợp với Unix direct execution, `java -jar`, WAR deploy, layered JAR extraction và CI/CD.
- Phân biệt lỗi packaging/extraction với lỗi Java application hoặc dependency.

**Phạm vi:** ví dụ dùng Spring Boot 3.3.13, Java 17 và plugin Gradle/Maven của Spring Boot. Phiên bản này chỉ là mốc minh họa nhất quán, không phải bản Spring Boot mới nhất. Khi áp dụng vào dự án thật, tra tài liệu đúng phiên bản plugin/loader và test bằng chính JDK/công cụ dùng trong pipeline.

## 2. Ba khái niệm không được đánh đồng

### 2.1. Plain JAR

Gradle Java plugin có task `jar`. Nó thường đóng classes/resources của module, nhưng không tự đưa tất cả runtime dependencies vào file. Trong Spring Boot Gradle Plugin 3.3, khi có cả `jar` và `bootJar`, JAR chuẩn từ task `jar` thường có hậu tố:

~~~text
build/libs/launch-demo-0.1.0-plain.jar
~~~

Plain JAR không nhất thiết là executable application. `java -jar` có thể lỗi thiếu manifest main hoặc thiếu thư viện. Việc `jar -tf` đọc được plain JAR không chứng minh file đó đúng để phát hành Spring Boot service.

### 2.2. Spring Boot executable JAR tiêu chuẩn, không script

Task `bootJar` hoặc goal `spring-boot:repackage` có thể tạo JAR chứa:

~~~text
launch-demo-0.1.0.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/launch/JarLauncher.class
└── BOOT-INF/
    ├── classes/com/example/demo/LaunchApplication.class
    ├── lib/spring-boot-3.3.13.jar
    └── lib/... các runtime dependencies ...
~~~

Bố cục là minh họa rút gọn; danh sách thư viện phụ thuộc build. Boot Loader nạp nested JARs từ `BOOT-INF/lib` và gọi ứng dụng qua manifest, ví dụ:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.demo.LaunchApplication
~~~

File này đã **executable bằng `java -jar`**, dù chưa có shell launch script. Nội dung file ZIP tiêu chuẩn thường bắt đầu bằng các byte `50 4B 03 04` (ZIP local file header).

### 2.3. Fully executable JAR có launch script

Khi Gradle gọi `launchScript()` hoặc Maven đặt `<executable>true</executable>`, plugin thêm script ở **phía trước** phần dữ liệu ZIP:

~~~text
app.jar
+--------------------------------+
| #!/bin/bash                     |
| ... Spring Boot launch script ... |  ← prefix
+--------------------------------+
| PK... ZIP/JAR bytes             |
| META-INF/MANIFEST.MF           |
| BOOT-INF/classes               |
| BOOT-INF/lib                   |
| Boot Loader                    |
+--------------------------------+
~~~

Sơ đồ mô tả ý tưởng, không phải output byte-for-byte. Prefix cho phép hệ Unix gọi trực tiếp file qua shell launcher, nhưng có nghĩa **file không còn bắt đầu ở byte 0 bằng ZIP header thông thường**.

**Cần nhớ:** fully executable chỉ là **thêm cách khởi động**, không phải “JAR executable thực sự” còn bản không script thì “không executable”. Hai biến thể đều có thể chứa cùng một Spring Boot app và runtime dependencies; khác nhau ở contract với OS và công cụ xử lý archive.

## 3. Bảng tương thích — đâu là lựa chọn đúng?

| Công cụ / mục đích | Boot JAR không script | Fully executable với launch script |
| --- | --- | --- |
| `java -jar app.jar` | Cách khởi động tiêu chuẩn | Không phải lựa chọn được Spring Boot khuyến nghị khi chỉ cần java -jar |
| `./app.jar` trên Unix | Không có shebang/script mặc định | Mục tiêu chính; cần execute bit, shell và OS phù hợp |
| `jar -tf app.jar` | Đọc archive tiêu chuẩn | Kết quả có thể phụ thuộc công cụ/JDK; phải thử |
| `jar -xf app.jar` | Phù hợp với archive tiêu chuẩn hợp lệ | Spring Boot cảnh báo **có thể fail âm thầm** |
| `unzip`/`zipinfo` hoặc ZIP library | Thường phù hợp | Khả năng đọc prefix khác nhau theo parser |
| `-Djarmode=tools -jar app.jar extract`, Boot 3.3 | Hỗ trợ nếu có JAR tools | **Không được hỗ trợ** với file có script |
| `extract --layers` trong container builder | Phù hợp khi tools/layers có mặt | Không dùng loại script-prefixed |
| Deploy WAR vào servlet container | Dùng WAR chuẩn, phù hợp container | Không khuyến nghị; container phải đọc archive |
| Direct Unix service/script | Dùng service wrapper bên ngoài | Có thể thích hợp khi đã xác định yêu cầu |
| Scanner/checksum/signing pipeline | Kiểm tra theo contract ZIP/JAR | Cần kiểm tra công cụ có chấp nhận prefix hay không |

Đây là các **giới hạn về định dạng và hỗ trợ chính thức**, không phải cam kết mọi tiện ích đều có cùng hành vi. Một `unzip` implementation có thể đọc được file có prefix; một thư viện khác có thể từ chối. Không được suy ra “unzip hoạt động nên Spring Boot jarmode cũng hoạt động”.

**Quy tắc chọn:** nếu ứng dụng chỉ được chạy bằng `java -jar`, đưa vào Docker image, phân tích ZIP/JAR hay deploy WAR, ưu tiên **Spring Boot archive không launch script**. Chỉ bật script khi yêu cầu chạy file trực tiếp trên Unix là thực sự cần.

## 4. Vì sao một số công cụ đọc JAR lỗi?

JAR có nền tảng là ZIP archive. Nhiều công cụ quét signature/offsets/central directory để tìm entry. Một script được prepend làm vị trí bắt đầu dữ liệu ZIP bị dời đi. Không phải công cụ nào cũng hỗ trợ loại ZIP có phần tiền tố.

- ZIP parser đơn giản có thể yêu cầu hai byte đầu là `PK`.
- Một parser khác có thể tìm central directory từ cuối, điều chỉnh offsets và vẫn đọc được.
- Một số phiên bản `jar` có thể liệt kê/giải nén, nhưng điều này **không phải contract chung** cho fully executable archive.
- Theo chính tài liệu Spring Boot, `jar -xf` đôi khi **không tạo file mong đợi mà không báo lỗi rõ ràng**.

Ví dụ pipeline sai về kiểm chứng:

~~~bash
mkdir -p extracted
(cd extracted && jar -xf ../app.jar)
echo "Extract complete"
~~~

Dòng `echo` không xác minh extraction. Nếu process không dừng hoặc exit code không phản ánh lỗi, pipeline có thể công bố thành công giả. Tối thiểu phải kiểm tra **file cụ thể** được tạo và xử lý thất bại rõ ràng:

~~~bash
test -f extracted/BOOT-INF/classes/com/example/demo/LaunchApplication.class
~~~

Lệnh `test -f` chỉ đúng khi class path của app và cấu trúc extraction thật tương ứng. Không tự tạo archive không hợp lệ rồi “sửa” bằng cách cắt script với `tail`/`dd`: cách làm phụ thuộc offset/script length, dễ phá checksum và metadata ZIP. Giải pháp bền vững là **build lại một bản JAR không script**.

## 5. Ứng dụng Java 17 mẫu cho việc kiểm chứng

Ta tạo Spring Boot command-line application có một dòng output do chương trình tự in:

~~~text
LAUNCH_DEMO_OK
~~~

Mã dưới đây cần Spring Boot starter dependency nhưng không cần HTTP server. Tệp `src/main/java/com/example/demo/LaunchApplication.java`:

~~~java
package com.example.demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class LaunchApplication {

    public static void main(String[] args) {
        SpringApplication.run(LaunchApplication.class, args);
    }

    @Bean
    CommandLineRunner reportStart() {
        return args -> System.out.println("LAUNCH_DEMO_OK");
    }
}
~~~

Đây là một file Java đầy đủ. Spring Boot khởi tạo context, gọi `CommandLineRunner`; vì không có web starter/background worker, process có thể tự kết thúc sau startup. Các dòng log của Spring Boot có thể xuất hiện ngoài dòng stdout trên. File phải nằm đúng đường dẫn tương ứng với `package com.example.demo;`.

## 6. Gradle Groovy DSL: build chuẩn không launch script

Tạo `settings.gradle`:

~~~groovy
rootProject.name = 'launch-demo'
~~~

Tạo `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.1.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
~~~

Với Gradle wrapper phù hợp:

~~~bash
./gradlew --version
./gradlew clean bootJar
java -jar build/libs/launch-demo-0.1.0.jar
~~~

Trên Windows PowerShell dùng `.\gradlew.bat`; nếu repository chưa có wrapper thì phải cung cấp/tạo wrapper hoặc dùng Gradle cài tương thích. `build.gradle` không tự sinh `gradlew`. Dòng ứng dụng tự in là `LAUNCH_DEMO_OK`.

Cấu hình **không có `launchScript()`**. `bootJar` vẫn tạo executable Boot JAR. Nếu build tạo cả `-plain.jar`, hãy dùng output của task `bootJar` chứ không dùng `jar`.

## 7. Gradle Kotlin DSL: build tương đương

Tạo `settings.gradle.kts`:

~~~kotlin
rootProject.name = "launch-demo"
~~~

Tạo `build.gradle.kts`:

~~~kotlin
plugins {
    id("java")
    id("org.springframework.boot") version "3.3.13"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "0.1.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
}
~~~

Dùng chính `LaunchApplication.java` ở mục 5, cùng các lệnh Gradle. **Chỉ chọn một DSL** cho root project, không dùng cả `build.gradle` và `build.gradle.kts` để cố gắng cấu hình hai biến thể cùng lúc.

## 8. Bật launch script bằng Gradle

### 8.1. Groovy DSL

Khi muốn chạy trực tiếp trên Unix, **thêm fragment** sau vào `build.gradle` từ mục 6:

~~~groovy
tasks.named("bootJar") {
    launchScript()
}
~~~

Chạy lại `./gradlew clean bootJar`. Output tên file thường vẫn là `build/libs/launch-demo-0.1.0.jar`, nhưng bây giờ nó có script prefix. Với Unix và quyền phù hợp:

~~~bash
chmod +x build/libs/launch-demo-0.1.0.jar
./build/libs/launch-demo-0.1.0.jar
~~~

Không giả định script luôn in log ra terminal: script/service mode có thể điều chỉnh log redirection hoặc process lifecycle. Với Java app mẫu, dòng ứng dụng tự in là `LAUNCH_DEMO_OK` khi code được khởi chạy thật.

### 8.2. Kotlin DSL

Trong `build.gradle.kts`, đặt import ở đầu file:

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar
~~~

Sau đó thêm:

~~~kotlin
tasks.named<BootJar>("bootJar") {
    launchScript()
}
~~~

`BootJar` là kiểu task do Spring Boot plugin cung cấp. Đây không phải API của task Java `Jar` thuần. Nếu module không apply Spring Boot/Java plugin nên không có `bootJar`, phải sửa đúng plugin/module thay vì đổi tên task tùy tiện.

### 8.3. Đặt launch script properties

Spring Boot 3.3 cho phép cấu hình properties mặc định, ví dụ log filename:

**Groovy fragment:**

~~~groovy
tasks.named("bootJar") {
    launchScript {
        properties 'logFilename': 'launch-demo.log'
    }
}
~~~

**Kotlin fragment:**

~~~kotlin
tasks.named<BootJar>("bootJar") {
    launchScript {
        properties(mapOf("logFilename" to "launch-demo.log"))
    }
}
~~~

Hai fragment này là **biến thể thay cho** `launchScript()` trống; không cần dùng cả hai. Việc thiết lập log filename không tự bảo đảm filesystem writable; kiểm tra môi trường service, UID/GID, filesystem permissions.

Nếu cần custom script, plugin có API như:

~~~groovy
tasks.named("bootJar") {
    launchScript {
        script = file('src/custom-launch.sh')
    }
}
~~~

**Đây là fragment minh họa, không độc lập**: nó yêu cầu file `src/custom-launch.sh` thực sự có nội dung shell script hợp lệ, được kiểm thử và không chứa secrets. Đừng dùng fragment khi chưa tạo file tương ứng.

## 9. Maven: lựa chọn `executable` của repackage

Maven Spring Boot Plugin không có Gradle task `bootJar`. Maven dùng goal `spring-boot:repackage` để tạo executable archive trong lifecycle. Với Spring Boot starter parent, goal repackage được cấu hình sẵn khi plugin được khai báo.

### 9.1. POM Maven hoàn chỉnh cho bản không script

Một project Maven **thay thế** Gradle có thể dùng cùng Java source ở mục 5 và file `pom.xml` sau:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>launch-demo</artifactId>
    <version>0.1.0</version>

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
                <configuration>
                    <executable>false</executable>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`<executable>false</executable>` là mặc định; đặt tường minh ở đây để người học thấy lựa chọn. Với Maven/JDK tương thích:

~~~bash
mvn clean package
java -jar target/launch-demo-0.1.0.jar
~~~

Nếu dự án có Maven wrapper, dùng `./mvnw` trên Linux/macOS hoặc `.\mvnw.cmd` trên Windows. `mvn package` tạo JAR cơ sở và execution `repackage` của Spring Boot parent biến nó thành executable Boot JAR. Không lấy nhầm file `.original`.

### 9.2. Tạo fully executable Maven archive

Trong POM ở trên, **chỉ sửa**:

~~~xml
<executable>true</executable>
~~~

Rồi chạy `mvn clean package`. Trên Unix có thể chạy:

~~~bash
chmod +x target/launch-demo-0.1.0.jar
./target/launch-demo-0.1.0.jar
~~~

Tài liệu Maven Plugin cảnh báo `jar -xf` có thể fail âm thầm với kiểu này; không bật option nếu chủ yếu muốn `java -jar` hoặc deploy vào external servlet container.

### 9.3. Maven custom launch script

Spring Boot Maven Plugin cung cấp `embeddedLaunchScript` và `embeddedLaunchScriptProperties`, ví dụ fragment cho cấu hình plugin:

~~~xml
<configuration>
    <executable>true</executable>
    <embeddedLaunchScript>src/custom-launch.sh</embeddedLaunchScript>
    <embeddedLaunchScriptProperties>
        <logFilename>launch-demo.log</logFilename>
    </embeddedLaunchScriptProperties>
</configuration>
~~~

**Đây là fragment**, thay phần `configuration` trong POM hoàn chỉnh; không cần chép vào hai khối `build` riêng. File script phải tồn tại, quyền ghi log phải hợp lệ, và cần test trên OS triển khai thật.

## 10. Lưu bản chuẩn và bản có script thành hai artifact riêng

Đừng để `clean` xóa mất artifact trước khi so sánh. Dùng thư mục `samples` **nằm ngoài `build`**:

**Trên Linux/macOS, khi build Gradle vẫn ở chế độ không có launchScript:**

~~~bash
mkdir -p samples
./gradlew clean bootJar
cp build/libs/launch-demo-0.1.0.jar samples/standard-boot.jar
~~~

**Sau khi thêm `launchScript()` vào đúng DSL và build lại:**

~~~bash
./gradlew clean bootJar
cp build/libs/launch-demo-0.1.0.jar samples/script-prefixed-boot.jar
~~~

Lúc này:

- `samples/standard-boot.jar` là Boot executable JAR **không** có shell prefix.
- `samples/script-prefixed-boot.jar` là Boot executable JAR **có** shell prefix.
- Cả hai **không phải** cặp plain vs Boot; plain JAR là artifact khác.
- Đây là minh họa tại máy cá nhân; nếu đang làm CI, đặt artifact name/variant rõ ràng theo quy trình publish.

Chạy bản chuẩn:

~~~bash
java -jar samples/standard-boot.jar
~~~

Chạy bản script trên Unix phù hợp:

~~~bash
chmod +x samples/script-prefixed-boot.jar
./samples/script-prefixed-boot.jar
~~~

Java application sẽ có dòng `LAUNCH_DEMO_OK` khi thực sự chạy. Không cần bật script cho bản chuẩn chỉ để đảm bảo `java -jar` hoạt động.

## 11. Kiểm tra byte-prefix bằng Java 17, không cần thư viện ZIP ngoài

Bên cạnh ứng dụng Spring Boot, tạo một **chương trình Java SE độc lập** ở project root (không đặt trong `src/main/java`):

Tệp `ArchivePrefixProbe.java`:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ArchivePrefixProbe {

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            System.err.println("Usage: java ArchivePrefixProbe <jar-file>");
            System.exit(2);
        }

        try (InputStream in = Files.newInputStream(Path.of(args[0]))) {
            byte[] first = in.readNBytes(4);

            if (first.length < 2) {
                throw new IOException("File is too short");
            }

            boolean zip = first.length >= 4
                    && first[0] == 0x50
                    && first[1] == 0x4B
                    && first[2] == 0x03
                    && first[3] == 0x04;

            boolean script = first[0] == '#'
                    && first[1] == '!';

            if (zip) {
                System.out.println("ZIP_HEADER");
            } else if (script) {
                System.out.println("SCRIPT_PREFIX");
            } else {
                System.out.println("OTHER_PREFIX");
            }
        }
    }
}
~~~

Compile bằng JDK 17:

~~~bash
javac ArchivePrefixProbe.java
java ArchivePrefixProbe samples/standard-boot.jar
java ArchivePrefixProbe samples/script-prefixed-boot.jar
~~~

Với hai file tạo bằng plugin trong ví dụ (script mặc định có shebang), hai kết quả **tương ứng theo từng lệnh**:

~~~text
ZIP_HEADER
SCRIPT_PREFIX
~~~

Giải thích: file standard Boot bắt đầu bằng ZIP local header; file fully executable bắt đầu bằng `#!` của script. Nếu dùng **custom launch script không có shebang** hoặc một định dạng khác, công cụ có thể in `OTHER_PREFIX`.

**Giới hạn:** chương trình chỉ đọc bốn byte đầu file, không kiểm tra central directory, manifest, class loading, dependency graph, checksum, security signature hay tương thích thực sự của `jar -xf`. Đây là công cụ minh họa chẩn đoán tiền tố, không phải ZIP validator. Nó chạy bằng Java SE, không cần ứng dụng Spring Boot khởi động.

## 12. Kiểm tra nội dung và giải nén bằng JDK `jar`

Đối với file **không có launch script**:

~~~bash
jar -tf samples/standard-boot.jar
~~~

Tìm entry tương tự:

~~~text
META-INF/MANIFEST.MF
BOOT-INF/classes/com/example/demo/LaunchApplication.class
BOOT-INF/lib/
org/springframework/boot/loader/launch/JarLauncher.class
~~~

Để kiểm tra extract, nên dùng thư mục riêng thay vì giải nén vào root dự án:

~~~bash
mkdir -p inspect-standard
(cd inspect-standard && jar -xf ../samples/standard-boot.jar)
test -f inspect-standard/BOOT-INF/classes/com/example/demo/LaunchApplication.class
~~~

Lệnh `test -f` thành công chứng tỏ **file cụ thể mong đợi** xuất hiện. Nếu project thay package/class, chỉnh path cho đúng. Khi unpack archive từ nguồn không tin cậy, phải kiểm soát directory và quyền ghi để tránh ghi đè file.

Nếu muốn khảo sát lỗi với file có script, dùng một thư mục tách biệt khác:

~~~bash
mkdir -p inspect-prefixed
(cd inspect-prefixed && jar -xf ../samples/script-prefixed-boot.jar)
test -f inspect-prefixed/BOOT-INF/classes/com/example/demo/LaunchApplication.class
~~~

Kết quả phép thử thứ hai **không được bảo đảm**; Spring Boot cảnh báo `jar -xf` có thể silently fail trên fully executable archive. Đừng coi exit code bằng 0 hoặc việc không thấy exception là bằng chứng đã extract. Chỉ dựa vào output đã kiểm tra.

Một số bản `unzip`/`zipinfo` có thể xử lý file ZIP có script prefix, bản khác có thể lỗi/cảnh báo. **Không có cam kết chung** cho mọi ZIP reader và runtime environment. Nếu pipeline phải trích xuất/đọc một archive bằng nhiều công cụ khác nhau, chọn standard Boot archive là cách an toàn hơn.

## 13. Chế độ trích xuất `jarmode=tools` của Spring Boot 3.3

Đây là giới hạn quan trọng nhất của chủ đề.

### 13.1. JAR tools làm gì?

Spring Boot 3.3 có `spring-boot-jarmode-tools`, có thể đưa vào layered executable archive. Khi kích hoạt special mode, JVM **không chạy business application** mà Boot loader gọi công cụ để xem/extract nội dung archive, chẳng hạn:

~~~bash
java -Djarmode=tools -jar samples/standard-boot.jar
~~~

Theo tài liệu Spring Boot 3.3, các command gồm `extract`, `list-layers` và `help`. Để xem tùy chọn:

~~~bash
java -Djarmode=tools -jar samples/standard-boot.jar help extract
~~~

### 13.2. Extract layout thông thường

~~~bash
java -Djarmode=tools -jar samples/standard-boot.jar extract
~~~

Trong mô hình mặc định của Spring Boot 3.3, kết quả là một layout có libraries trong `lib/` và một application JAR chứa app classes/manifest tham chiếu các libraries đó. Nó **không giống hoàn toàn** việc giải nén ZIP thủ công bằng `jar -xf`.

Cần xem `help extract` để biết thư mục đầu ra và các option thực tế của version đang chạy, không tự đoán một tên folder cố định rồi hardcode trong CI.

### 13.3. Extract theo layers để làm container image

~~~bash
java -Djarmode=tools -jar samples/standard-boot.jar extract --layers --destination extracted
~~~

Với layer defaults, có các nhóm thường gặp:

~~~text
extracted/
├── dependencies/
├── spring-boot-loader/
├── snapshot-dependencies/
└── application/
~~~

Đây là layout hỗ trợ copy từng layer riêng trong container builder. Nếu team đổi cấu hình layer, tên và phân chia nội dung có thể khác. `layers.idx` là metadata, còn jarmode tools thực sự tạo output.

### 13.4. Vì sao không dùng file có launch script?

**Quy tắc chính thức Spring Boot 3.3: chế độ `tools` không được dùng với fully executable Spring Boot archive có launch script.** Hãy disable launch script khi xây JAR cho lệnh `extract`.

Không sửa bằng cách chạy `jar -xf` trước rồi nghĩ rằng `jarmode=tools` đương nhiên hoạt động trên cùng file; đây là hai cơ chế khác nhau và cả hai đều có vấn đề với script prefix trong môi trường/phiên bản tương ứng.

### 13.5. Hai điều kiện phải đúng cùng lúc

Để dùng extract mode:

1. **Không có launch script prefix.**
2. **Có JAR tools phù hợp** trong artifact.

Spring Boot 3.3 thông thường thêm `spring-boot-jarmode-tools` khi tạo layered JAR/WAR; nếu build chủ động loại nó bằng `includeTools=false`, extract mode cũng có thể không sẵn có.

Đoạn Gradle Groovy minh họa một **cấu hình cần tránh khi còn muốn dùng extract**:

~~~groovy
tasks.named("bootJar") {
    includeTools = false
}
~~~

Kotlin:

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named<BootJar>("bootJar") {
    includeTools.set(false)
}
~~~

Maven fragment:

~~~xml
<configuration>
    <includeTools>false</includeTools>
</configuration>
~~~

Các đoạn này chỉ giải thích nguyên nhân `tools` thiếu, **không phải** cấu hình khuyến nghị. Trên Spring Boot dòng cũ, có chế độ `layertools` thay vì `tools` hoặc khác lệnh; luôn kiểm tra đúng phiên bản trước khi copy script CI.

## 14. Container image: giữ JAR chuẩn cho extract

Rất nhiều Docker/OCI workflows dùng lệnh:

~~~text
ENTRYPOINT ["java", "-jar", "application.jar"]
~~~

hoặc chạy `jarmode=tools extract --layers` trong một build stage. Cả hai **không cần** launch script Unix trong chính JAR.

Một Dockerfile dạng ví dụ cho Spring Boot 3.3, giả định `build/libs/launch-demo-0.1.0.jar` là **Boot JAR không script**, có JAR tools và layers:

~~~dockerfile
FROM eclipse-temurin:17-jre AS builder
WORKDIR /builder
COPY build/libs/launch-demo-0.1.0.jar application.jar
RUN java -Djarmode=tools -jar application.jar extract --layers --destination extracted

FROM eclipse-temurin:17-jre
WORKDIR /application
COPY --from=builder /builder/extracted/dependencies/ ./
COPY --from=builder /builder/extracted/spring-boot-loader/ ./
COPY --from=builder /builder/extracted/snapshot-dependencies/ ./
COPY --from=builder /builder/extracted/application/ ./
ENTRYPOINT ["java", "-jar", "application.jar"]
~~~

**Đây là mô hình Dockerfile độc lập**, nhưng chỉ hoạt động khi Docker/container runtime có sẵn, image/tag được tổ chức cho phép, JAR đã build trước trong Docker context, và các tên layer/directory phù hợp Spring Boot 3.3. Nếu dùng Maven, chỉnh đường dẫn COPY từ `target`; nếu artifact được đổi tên/classifier, chọn đúng file.

Không dùng `COPY build/libs/*.jar` khi thư mục chứa cả `-plain.jar` và executable JAR. Tránh việc Docker copy nhầm artifact; nếu build với `launchScript()`, lệnh extract trong Dockerfile trên **không thuộc workflow được Spring Boot 3.3 hỗ trợ**. Hãy loại script và build lại.

Nếu không cần layered extract, bạn có thể build một image đơn giản với standard Boot JAR và `java -jar`. Khi đó lựa chọn launch script cũng không tạo lợi ích thiết yếu.

## 15. Servlet container, executable WAR và launch script

Spring Boot Gradle plugin có `bootWar` khi áp dụng War plugin, còn Maven có `repackage` cho WAR. Một WAR thông thường được servlet container đọc/giải nén theo các quy tắc riêng. Nếu prepend shell script, container hoặc archive reader có thể không chấp nhận file.

Ví dụ fragment Gradle (chỉ để hiểu tính năng, **không khuyến nghị cho WAR deploy external**):

**Groovy:**

~~~groovy
tasks.named("bootWar") {
    launchScript()
}
~~~

**Kotlin:**

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootWar

tasks.named<BootWar>("bootWar") {
    launchScript()
}
~~~

Hai đoạn trên chỉ hợp lệ trong module **có Spring Boot plugin và War plugin**. Đừng thêm vào project `bootJar`-only để rồi gặp lỗi task không tồn tại.

Cần phân biệt:

- Executable WAR chạy bằng `java -jar` qua Boot Loader.
- WAR deployed vào external servlet container qua cơ chế của container.
- Fully executable WAR có shell prefix; Spring Boot cảnh báo archive tools có thể không chấp nhận, và khuyến nghị **không dùng tính năng script nếu mục tiêu là servlet container deployment**.

Nếu team hỗ trợ cả lệnh `java -jar` và external WAR, hãy kiểm chứng từng cách triển khai và chọn artifact phù hợp, tránh ép cả hai dùng một file script-prefixed.

## 16. Khi nào fully executable script thực sự đáng dùng?

Một ví dụ hợp lý là môi trường Unix/Linux muốn triển khai **một file có thể chạy trực tiếp như script/service**, với vận hành đã quyết định rõ cách quản lý process, logs và lifecycle.

Trước khi bật:

- Kiểm tra OS và shell tương thích; JAR có script Unix không trở thành Windows `.exe`.
- Kiểm tra execute bit, owner, mount có `noexec` hay không, và working directory.
- Kiểm tra file log, service manager, signal handling và restart policy.
- Kiểm tra custom launch script không hardcode credentials/secrets vào artifact hoặc log.
- Thử trên môi trường thật; thành công của `bootJar`/`repackage` không chứng minh script chạy được trên production.
- Ghi rõ trong tài liệu rằng biến thể này **không dùng cho JAR tools extract**.

`chmod +x` trên Boot JAR tiêu chuẩn **không sinh ra shell script**. Nếu gọi `./standard-boot.jar` khi nó bắt đầu bằng ZIP header, hệ điều hành có thể báo lỗi execution format; hãy chạy bằng `java -jar`. Nếu file có script nhưng không đủ quyền, direct execution cũng có thể lỗi dù payload Java hợp lệ.

## 17. Quy trình kiểm chứng trong CI/CD

Một pipeline có thể lặp lại nên xác định **artifact contract** trước:

1. **Lấy đúng output:** xác định task `bootJar` hay Maven `repackage`, version, classifier và output filename. Không glob tùy tiện.
2. **Xác định consumer:** JVM `java -jar`, Unix script, tool `jar -xf`, `jarmode=tools` hay servlet container.
3. **Chọn định dạng:** phần lớn trường hợp chọn standard Boot archive; chỉ dùng script khi direct Unix execution là mục tiêu.
4. **Kiểm chứng prefix:** dùng công cụ như `ArchivePrefixProbe` để phát hiện bất thường trước bước ZIP processing.
5. **Kiểm chứng nội dung:** dùng `jar -tf`, kiểm tra `BOOT-INF`/manifest và entry cần thiết.
6. **Kiểm chứng extraction:** với `jar -xf` xác nhận file xuất hiện; với JAR tools xác nhận layers/layout thật tồn tại.
7. **Kiểm chứng startup:** chạy `java -jar` trên standard artifact hoặc chạy script trên Unix thật, tùy mục tiêu.
8. **Kiểm chứng phát hành:** hash, ký số, attestation và scan phải áp dụng cho **chính file cuối cùng**, không tái sử dụng checksum của file trước khi prepend script.

Thêm script thay đổi bytes nên checksum sẽ khác dù application classes/dependencies cùng version. Nếu pipeline có signing/verification, xác minh mỗi biến thể bằng signer/verifier thật. Đừng sửa archive bằng tool ghép/đọc thủ công sau khi ký mà không kiểm tra lại.

### 17.1. Tránh false positive khi extract

Sai:

~~~bash
jar -xf app.jar
echo "OK"
~~~

Tốt hơn (trong thư mục extraction được kiểm soát):

~~~bash
jar -xf ../app.jar
test -f BOOT-INF/classes/com/example/demo/LaunchApplication.class
~~~

Nhưng tốt nhất vẫn là **không đặt shell prefix vào JAR có contract phải extract bằng ZIP/JAR tools**.

## 18. Các triệu chứng thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách điều tra đúng |
| --- | --- | --- |
| `jar -xf` không báo lỗi nhưng không có file | Fully executable JAR có script prefix | Kiểm tra 4 byte đầu, dùng archive chuẩn, test file kết quả |
| `jar -tf`/ZIP parser lỗi ở CI nhưng unzip local được | Mức hỗ trợ prefix/offset khác nhau | Dùng non-prefixed archive và test đúng tool của CI |
| `-Djarmode=tools` extract thất bại | Script prefix hoặc tools bị loại, mode sai version | Tắt launchScript, kiểm tra `includeTools`/Boot 3.3 docs |
| Docker builder dừng tại `extract --layers` | Artifact là file script-prefixed, thiếu tools hoặc sai path | Build lại standard Boot JAR, xác nhận layer output |
| `./app.jar` báo permission denied | Thiếu execute bit, owner/mount hạn chế | Kiểm tra quyền và runtime OS |
| `./app.jar` báo exec format error | Không có shell script/shebang hoặc shell không tương thích | Dùng `java -jar` cho standard archive hoặc build script variant |
| `java -jar` chạy nhưng `jar -xf` fail | Startup và ZIP extraction có contract khác | Chọn file phù hợp với nhu cầu tool |
| Có `BOOT-INF/layers.idx` nhưng tools mode không nhận | `includeTools=false` hoặc archive không hỗ trợ mode | Kiểm tra dependencies trong archive, version plugin |
| `jar -xf` ra JAR nhưng không có Boot classes | Có thể lấy nhầm plain JAR hoặc output cũ | Xem task outputs, manifest và `BOOT-INF` |
| Maven executable option không có tác dụng | `repackage` không thực thi hoặc cấu hình đặt sai plugin | Xem effective POM và log `mvn package` |
| External WAR container không deploy | WAR format hoặc prefix không phù hợp parser | Dùng WAR không script, kiểm tra container logs |
| Fully executable chạy như service nhưng không có stdout | Script có logging/redirect/service mode | Kiểm tra script props, logs/process status |
| Khác hash so với lần build trước | Có script prefix/version/reproducibility thay đổi | So sánh artifact thực, ký/ghi hash lại |
| Một ZIP reader từ chối `PK` không ở offset 0 | Thư viện giả định ZIP header bắt đầu file | Cấp standard archive thay vì dựa vào workaround |

Không chữa lỗi ở tầng file format bằng cách đổi `@SpringBootApplication`, dependency versions ngẫu nhiên hoặc tắt tests. Xác định rõ lỗi **archive parser**, **jarmode tools**, **shell runtime** hay **Java application startup** trước khi sửa.

## 19. Các hiểu lầm cần tránh

**“Cứ là executable JAR thì phải có launchScript.”** Sai. Bản Boot không script đã chạy được bằng `java -jar`.

**“`launchScript()` chỉ chmod file.”** Sai. Nó **prepend shell script bytes** vào artifact, có thể tác động tới ZIP/JAR parsers.

**“`jar -xf` không hiện exception nghĩa là đã extract.”** Không chắc; Spring Boot cảnh báo fail âm thầm với fully executable archive. Kiểm tra file kết quả.

**“Unzip mở được thì `jarmode=tools` cũng mở được.”** Sai. Đây là hai cơ chế khác nhau; Boot 3.3 chính thức không hỗ trợ tools mode cho archive có script.

**“Layered JAR luôn có tools.”** Không nhất thiết nếu build tắt `includeTools` hoặc dùng plugin/version khác. Xem archive và cấu hình plugin thực tế.

**“`requiresUnpack` có thể sửa `jar -xf` lỗi vì launch script.”** Sai. `requiresUnpack` đánh dấu một nested dependency cần unpack ở **runtime** khi Boot Loader chạy; nó không xóa shell prefix của outer JAR.

**“Đổi shell script sẽ làm Boot JAR nhỏ hơn hoặc tăng tốc startup.”** Đây không phải mục tiêu của tính năng. Script thêm bytes; hiệu quả startup và image layers là chủ đề khác.

**“Một artifact có thể dùng ở mọi đích nếu đổi đuôi `.jar`/`.war`.”** Sai. File format và cách startup/deployment quyết định compatibility; external servlet container và container builder có các yêu cầu khác Unix direct execution.

## 20. Bài tập tự thực hành

### Bài 1. Phân biệt Boot JAR và plain JAR

**Đề:** Gradle tạo `launch-demo-0.1.0.jar` và `launch-demo-0.1.0-plain.jar`. File nào là output `bootJar` theo defaults ở bài, và có cần launchScript để chạy bằng `java -jar` không?

**Đáp án:** `launch-demo-0.1.0.jar` là output `bootJar` thông thường, `-plain.jar` là output `jar`. Không cần script để `java -jar` chạy Boot executable JAR.

### Bài 2. Quyết định cho container

**Đề:** Dockerfile sử dụng `java -Djarmode=tools -jar application.jar extract --layers`, một người muốn bật `launchScript()` để “chạy tiện hơn”.

**Đáp án:** không bật. Với Spring Boot 3.3, tools mode không hỗ trợ fully executable archive có launch script. Dùng standard Boot JAR không script, đảm bảo tools/layers được đóng gói.

### Bài 3. Java byte probe

**Đề:** Hai bản của cùng app in lần lượt `ZIP_HEADER` và `SCRIPT_PREFIX` khi dùng `ArchivePrefixProbe`.

**Đáp án:** byte-prefix khác nhau: bản đầu có ZIP local header, bản sau có shebang. Chưa chứng minh toàn bộ ZIP archive hợp lệ hay extract tool hoạt động.

### Bài 4. Silent extraction failure

**Đề:** `jar -xf` trên một fully executable JAR kết thúc mà không có message lỗi, nhưng thư mục extraction vẫn trống.

**Đáp án:** đây là tình huống được Spring Boot cảnh báo. Xác nhận post-condition của extraction và **build lại JAR không script** để dùng làm input cho extraction pipeline.

### Bài 5. Maven

**Đề:** POM dùng `<executable>true</executable>` nhưng pipeline mới cần `jar -xf`.

**Đáp án:** chuyển `executable` về false hoặc bỏ property mặc định, chạy lại `mvn clean package`; xác nhận đúng Boot archive, rồi mới extract.

### Bài 6. Unix execution

**Đề:** Một JAR tiêu chuẩn đã `chmod +x` nhưng gọi `./app.jar` báo lỗi.

**Đáp án:** permission không tạo shell prefix. Dùng `java -jar`, hoặc bật `launchScript()`/Maven `executable` khi direct Unix execution thật sự là yêu cầu.

### Bài 7. WAR

**Đề:** WAR sẽ được deploy vào servlet container ngoài. Có nên bật launch script để “fully executable” không?

**Đáp án:** không phải lựa chọn khuyến nghị; external container cần xử lý WAR như archive và script prefix có thể phá compatibility. Dùng WAR không script và kiểm thử trên container mục tiêu.

**Tiêu chí hoàn thành:** bạn chạy được JAR chuẩn bằng `java -jar`, tạo được biến thể script và thử direct Unix execution khi phù hợp, dùng Java probe thấy khác byte-prefix, kiểm tra `jar -xf` qua file output thực tế, và giải thích vì sao JAR tools extraction cần bản không script.

## 21. Checklist phát hành

- [ ] Đã xác định rõ consumer của artifact: Java runtime, Unix shell, ZIP reader, jarmode tools hay external container.
- [ ] Đúng output `bootJar` hoặc `repackage`, không nhầm plain JAR/old artifact.
- [ ] Với `java -jar`/ZIP extraction/Docker layered extraction, **không bật launchScript**.
- [ ] Với direct Unix execution, script đã được cấu hình/kiểm thử, filesystem có execute bit và shell phù hợp.
- [ ] Với JAR tools, `includeTools` không bị tắt, version/mode và `extract` options khớp Spring Boot đang dùng.
- [ ] `jar -xf`/tools extract có kiểm tra post-condition thay vì tin exit code/chuỗi log.
- [ ] Docker build không dùng glob có thể copy nhầm `-plain.jar` hoặc script-prefixed variant.
- [ ] WAR deploy external không dùng prefix gây cản trở archive reader.
- [ ] Các biến thể được đặt tên, test, kiểm tra checksum/ký số riêng; không sửa bytes sau ký mà không xác minh.
- [ ] Team có ghi chú vì sao cần launch script và công cụ nào không được dùng với file đó.

**Kết luận:** launch script được tạo để giúp **khởi động trực tiếp trên Unix**, không phải điều kiện để Spring Boot JAR chạy bằng `java -jar`. Vì nó prepend bytes trước cấu trúc ZIP, một số công cụ đọc JAR có thể không tương thích; `jar -xf` có thể thất bại âm thầm. **Trên Spring Boot 3.3, `-Djarmode=tools` extract không được dùng với fully executable archive có launch script.** Khi cần công cụ đọc/trích xuất JAR, hãy phát hành bản **Spring Boot executable archive không script**.

## 22. Tài liệu tham khảo chính thức

- Spring Boot 3.3.13 — Gradle Plugin, *Packaging Executable Archives / Making an Archive Fully Executable*: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Spring Boot 3.3.13 — Maven Plugin, `repackage`, `executable` và `embeddedLaunchScript`: https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot 3.3.13 — *Dockerfiles*, cảnh báo `tools` mode và fully executable archive: https://docs.spring.io/spring-boot/3.3/reference/packaging/container-images/dockerfiles.html
- Spring Boot 3.3.13 — *Efficient Deployments*, extract JAR và layout: https://docs.spring.io/spring-boot/3.3/reference/packaging/efficient.html
- Spring Boot 3.3 — Executable JAR specification: https://docs.spring.io/spring-boot/3.3/specification/executable-jar/index.html
- Gradle Java Plugin: https://docs.gradle.org/current/userguide/java_plugin.html
- Java SE 17, JAR API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/package-summary.html

Khi nâng Spring Boot hoặc thay đổi launcher/build tool, hãy đọc lại tài liệu **đúng phiên bản** và chạy kiểm tra tương thích bằng đúng công cụ sẽ được sử dụng sau khi phát hành. Không chọn fully executable chỉ vì tên gọi có chữ “fully”.
