# Chạy `java -jar` từ một thư mục độc lập và xác minh tài nguyên được nạp

## 1. Mục tiêu và ý nghĩa của phép thử

Khi phát triển Spring Boot, ứng dụng thường chạy thành công ngay trong IDE hoặc qua `mvn spring-boot:run` / `./gradlew bootRun`. Tuy nhiên, một bản phát hành phải có khả năng chạy như **một executable JAR độc lập**, không cần thư mục `src/main/resources`, thư mục `target/classes`, mã nguồn, Maven hoặc Gradle ở nơi triển khai.

Bài thực hành này kiểm chứng điều đó bằng cách **đóng gói JAR, chuyển hoặc gọi nó từ một thư mục hoàn toàn khác, rồi chạy `java -jar`**. Ngoài việc khởi động thành công, ta xác nhận file tài nguyên được đọc **từ classpath bên trong JAR**, không phải vô tình đọc một file nằm ở thư mục project.

Sau bài này, bạn có thể:

1. Phân biệt **thư mục làm việc của tiến trình** (current working directory/CWD), **thư mục chứa file JAR**, **classpath** và **đường dẫn đến resource bên trong archive**.
2. Kiểm tra cấu trúc `BOOT-INF/classes`, `BOOT-INF/lib`, Boot launcher và manifest của executable Spring Boot JAR.
3. Đọc tài nguyên đóng gói bằng `ClassPathResource#getInputStream()` hoặc `ClassLoader#getResourceAsStream()`, thay vì giả định resource luôn là `java.io.File`.
4. Tạo và chạy ví dụ Spring Boot 4.1.2 với Java 17, Maven; kiểm tra bằng unit test và một lần chạy JAR ở thư mục trống trên Linux/macOS hoặc Windows PowerShell.
5. Thực hiện thao tác tương đương cho Gradle `bootJar`.
6. Kiểm tra sự khác nhau giữa **resource đóng trong JAR** và **cấu hình bên ngoài** mà Spring Boot tìm ở thư mục làm việc; xử lý các lỗi `FileNotFoundException`, thiếu `BOOT-INF/classes`, sai artifact, sai runtime Java và sai working directory.
7. Biết bằng chứng nào đủ cho smoke test đóng gói và đâu là giới hạn của phép thử.

**Phiên bản ví dụ:** Spring Boot **4.1.2**, Java **17+**, Maven **3.6.3+** hoặc Gradle **8.14+ (nhánh 8.x) / 9.x** theo yêu cầu tương thích của Spring Boot 4.1.2. Các công cụ build cần có ở **máy build**; máy chỉ chạy artifact cần một Java runtime tương thích.

## 2. Ba loại vị trí cần phân biệt

Giả sử sau khi build ta có:

~~~text
/home/developer/resource-jar-demo/
├── pom.xml
├── src/main/resources/
│   ├── application.properties
│   └── samples/payload.txt
└── target/
    └── resource-jar-demo-1.0.0.jar
~~~

Ta tạo thư mục độc lập:

~~~text
/tmp/boot-jar-run-abc123/
└── app.jar
~~~

Và chạy:

~~~bash
cd /tmp/boot-jar-run-abc123
java -jar app.jar
~~~

Lúc đó có ba đường dẫn khác nhau:

| Loại | Giá trị trong tình huống trên | Dùng cho việc gì? |
| --- | --- | --- |
| **CWD / `user.dir`** | `/tmp/boot-jar-run-abc123` | Giải quyết `Path.of("relative.txt")`, `new File("relative.txt")` và những file cấu hình ngoài JAR |
| **Vị trí file JAR** | `/tmp/boot-jar-run-abc123/app.jar` | Java tìm file archive để mở; không nhất thiết trùng CWD nếu dùng đường dẫn tuyệt đối |
| **Classpath resource** | `samples/payload.txt`, trong JAR ở `BOOT-INF/classes/samples/payload.txt` | ClassLoader/Spring Resource API tìm tài nguyên đã đóng gói |

**Điểm quan trọng:** `java -jar /some/path/app.jar` **không tự đổi current working directory sang `/some/path`**. JVM chạy với CWD mà shell, IDE, service manager hoặc container gán cho tiến trình. Có thể chạy một JAR từ CWD A dù file JAR nằm ở B.

Ví dụ:

~~~bash
cd /tmp
java -jar /opt/apps/app.jar
~~~

Với lệnh này, `Path.of("data/input.txt")` sẽ tìm theo `/tmp/data/input.txt`, **không phải** `/opt/apps/data/input.txt`. Resource `samples/payload.txt` dùng classpath vẫn có thể được nạp từ archive.

### Hai phép kiểm chứng khác nhau

- **Chạy được JAR từ thư mục độc lập:** chứng minh launcher, dependencies, entry point và runtime đủ để khởi động khi không có build directory.
- **Nạp được resource trong JAR:** chứng minh tài nguyên đã được copy vào archive và code dùng cách đọc tương thích JAR. Muốn chắc chắn phải đọc **nội dung** resource, không chỉ kiểm tra resource tồn tại ở source tree.

Một ứng dụng có thể `java -jar` chạy được nhưng không đọc được template, file JSON hay dữ liệu cấu hình riêng vì code đã hard-code đường dẫn `src/main/resources/...`. Chính phép thử từ thư mục độc lập sẽ bộc lộ sai lệch này.

## 3. Bên trong executable Spring Boot JAR có gì?

JAR được Spring Boot Maven Plugin `repackage` hoặc Gradle task `bootJar` tạo có cấu trúc tương tự:

~~~text
resource-jar-demo-1.0.0.jar
├── META-INF/
│   └── MANIFEST.MF
├── BOOT-INF/
│   ├── classes/
│   │   ├── dev/example/ResourceJarApplication.class
│   │   ├── application.properties
│   │   └── samples/payload.txt
│   └── lib/
│       ├── spring-boot-...jar
│       └── ...
└── org/springframework/boot/loader/
    └── ...
~~~

- `BOOT-INF/classes` chứa class và resources của **chính ứng dụng**.
- `BOOT-INF/lib` chứa dependency JAR cần cho ứng dụng chạy, theo thiết kế executable archive.
- `META-INF/MANIFEST.MF` chứa thông tin launcher và entry point.
- Spring Boot loader thiết lập classpath cho `BOOT-INF/classes` và các nested dependencies. ClassLoader thấy `samples/payload.txt` theo **đường dẫn logic trên classpath** chứ không cần thêm tiền tố `BOOT-INF/classes/` trong Java code.

Manifest phổ biến cho layout JAR:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: dev.example.ResourceJarApplication
~~~

`Main-Class` là Spring Boot launcher; `Start-Class` mới là class có method `public static void main(String[] args)` của ứng dụng. Đừng đặt `Main-Class` thành tên application mà quên cách Boot loader xử lý dependency JAR lồng bên trong.

**Lưu ý:** nếu chỉ dùng `maven-jar-plugin:jar` mà không repackage, output có thể là **plain JAR**. File plain JAR không tự có layout Boot hoặc runtime dependencies đầy đủ, nên test từ thư mục độc lập có thể báo `NoClassDefFoundError` hoặc `no main manifest attribute`. Tên đuôi `.jar` không chứng minh đó là executable Spring Boot archive.

## 4. Cách đọc resource đúng trong executable JAR

### 4.1. `ClassPathResource#getInputStream()`

Spring Framework cung cấp `ClassPathResource` để đọc tài nguyên từ classpath, dù nó nằm ở folder ngoài hay trong JAR:

~~~java
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.ClassPathResource;

ClassPathResource resource =
        new ClassPathResource("samples/payload.txt");

try (InputStream input = resource.getInputStream()) {
    String content = new String(input.readAllBytes(),
            StandardCharsets.UTF_8).strip();
    System.out.println(content);
}
~~~

Đây là **đoạn minh họa đặt trong một method có quyền ném `IOException`**. Ví dụ đầy đủ ở mục 6 có class, method và tất cả import. Với file `samples/payload.txt` có nội dung `IN_JAR_RESOURCE_OK`, dòng do đoạn code này in ra chính xác là:

~~~text
IN_JAR_RESOURCE_OK
~~~

Dùng `InputStream` giúp đọc được resource qua cơ chế classloader của executable JAR, không phụ thuộc việc resource có hiện hữu thành file vật lý trên ổ đĩa hay không. Dùng try-with-resources để đóng stream sau khi đọc.

### 4.2. Java `ClassLoader#getResourceAsStream()`

Một cách dùng Java API thuần, không phụ thuộc Spring Resource abstraction:

~~~java
try (InputStream input =
        ResourceJarApplication.class.getClassLoader()
                .getResourceAsStream("samples/payload.txt")) {
    if (input == null) {
        throw new IllegalStateException("Resource not found on classpath");
    }
    String value = new String(input.readAllBytes(),
            StandardCharsets.UTF_8).strip();
    System.out.println(value);
}
~~~

Đoạn này cũng cần ở trong method phù hợp vì `readAllBytes()` có thể ném `IOException`. Tên đưa cho ClassLoader là **`samples/payload.txt`**, không có dấu `/` mở đầu. Nếu dùng `ResourceJarApplication.class.getResourceAsStream("/samples/payload.txt")`, dấu `/` đầu lại có ý nghĩa “từ classpath root”. Với `Class#getResourceAsStream("payload.txt")` không có dấu `/`, đường dẫn được tìm tương đối với package của class. Phân biệt hai API để tránh lỗi đặt path.

### 4.3. Vì sao `getFile()` và `Path.of(...)` dễ lỗi?

Đoạn sau **không phải cách đọc resource trong JAR được khuyến nghị**:

~~~java
new ClassPathResource("samples/payload.txt").getFile();
~~~

Khi IDE chạy từ exploded classes directory, `getFile()` có thể trả về file thật và trông như hoạt động. Nhưng khi resource nằm **bên trong JAR**, nó không phải một file hệ thống tệp riêng có thể lấy bằng `java.io.File`; `getFile()` có thể ném `FileNotFoundException`. Dùng `getInputStream()` để đọc.

Tương tự:

~~~java
Path path = Path.of("src/main/resources/samples/payload.txt");
~~~

đọc **source tree theo CWD**, không đọc từ classpath. Nếu đem JAR sang máy chỉ có Java mà không có source tree, path này không tồn tại. `Path.of("samples/payload.txt")` cũng là đường dẫn **CWD-relative**; nó không tự nhảy vào `BOOT-INF/classes`.

Nếu một thư viện thật sự đòi `java.io.File`, có thể cần **sao chép resource sang một temporary file** với `getInputStream()`, dùng file tạm cho thư viện rồi dọn theo vòng đời ứng dụng. Không cố chuyển URL có scheme `jar:`/nested JAR thành `Path` thông thường rồi giả định nó tồn tại độc lập.

### 4.4. Đọc resource đóng gói khác với ghi file runtime

Tài nguyên trong JAR là **nội dung của artifact**, không nên sửa trực tiếp để lưu dữ liệu của người dùng. Nếu ứng dụng cần ghi upload, log, cache, report hay file kết quả, dùng **đường dẫn bên ngoài** có quyền ghi, ví dụ giá trị cấu hình `app.storage-dir` rồi giải quyết bằng `Path.of(...)`.

| Nhu cầu | API phù hợp | Ví dụ |
| --- | --- | --- |
| Đọc template/JSON/TXT cố định đi cùng ứng dụng | `ClassPathResource#getInputStream()` | `classpath:samples/payload.txt` |
| Đọc một resource Java thuần trên classpath | `ClassLoader#getResourceAsStream()` | `samples/payload.txt` |
| Đọc file external đã cấu hình | `Files.newInputStream(Path.of(configuredPath))` | `/srv/app/config/data.json` |
| Ghi dữ liệu sinh ra ở runtime | `Files.write(Path, bytes)` với thư mục có quyền ghi | `/var/lib/myapp/outputs` |
| Đọc `application.properties` theo Spring | Spring Boot Config Data / `Environment` | `app.setting` |

**Quy tắc ngắn:** file “mang theo bản build” → classpath; file “được cung cấp hoặc thay đổi lúc deploy” → filesystem/config ngoài JAR.

## 5. Đầu vào, đầu ra và dấu hiệu PASS

| Giai đoạn | Đầu vào | Đầu ra | Bằng chứng đạt |
| --- | --- | --- | --- |
| Chuẩn bị source | Java 17 code, `pom.xml`/`build.gradle`, `src/main/resources/...` | Workspace build được | Kiểm tra đúng path resource, version toolchain |
| Process resources | `samples/payload.txt`, `application.properties` | `target/classes` hoặc `build/resources/main` | File có mặt và nội dung không bị filter sai |
| Compile | Java source + classpath | `.class` | Không lỗi compile; class đúng Java release |
| Unit test | Test source + processed resources | JUnit report | Test classpath resource pass, không có test failure |
| Package | Compiled classes + resources + runtime deps | Boot executable JAR | Có `BOOT-INF/classes/samples/payload.txt` và nested libs |
| Isolated run | Chỉ JAR + Java runtime, CWD khác project | Process chạy/thoát với status 0 | In dấu hiệu nạp resource chính xác, không phụ thuộc source tree |
| Runtime configuration | `application.properties` trong JAR và config ngoài nếu có | Spring `Environment` | Biết giá trị đến từ package hay external override |
| Release gate | Reports, artifact, checksum | Artifact sẵn sàng phát hành | Cả kiểm tra archive và chạy thực tế đều pass |

**Không đánh đồng:** test unit đọc resource trong `target/classes` pass chưa chứng minh JAR có đúng resource; `jar tf` thấy resource trong JAR chưa chứng minh code đọc thành công sau khi đổi CWD. Bài thực hành phải hoàn tất **cả hai lớp bằng chứng**.

## 6. Ví dụ Maven hoàn chỉnh với Spring Boot 4.1.2 và Java 17

Ta tạo **ứng dụng dòng lệnh Spring Boot**, không chạy web server. Cách này giúp `java -jar` in kết quả rồi tự kết thúc, dễ kiểm tra trên CI và không cần quản lý port/process. Ví dụ cố ý in ba dấu hiệu:

~~~text
CLASSPATH_RESOURCE=IN_JAR_RESOURCE_OK
APP_SETTING=from-packaged-config
CWD_RESOURCE_EXISTS=false
~~~

Ba dòng là **phần output do code in**, với điều kiện chạy trong thư mục trống không có `samples/payload.txt` và không có nguồn cấu hình ngoài ghi đè `app.setting`. Log/hành vi JVM hoặc công cụ khác có thể xuất hiện tùy môi trường.

### 6.1. Cấu trúc project

~~~text
resource-jar-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/dev/example/ResourceJarApplication.java
    │   └── resources/
    │       ├── application.properties
    │       └── samples/
    │           └── payload.txt
    └── test/
        └── java/dev/example/ResourceJarApplicationTest.java
~~~

Tất cả file nguồn được đặt đúng **vị trí tiêu chuẩn Maven**. Trong đó `samples/payload.txt` không được đặt cạnh `pom.xml` hoặc bên cạnh `resource-jar-demo-1.0.0.jar`; nó thuộc classpath resource của ứng dụng.

### 6.2. POM độc lập — `pom.xml`

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
    <artifactId>resource-jar-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

Giải thích:

- **Starter parent** quản lý dependency và plugin defaults; khi khai báo `spring-boot-maven-plugin`, execution `repackage` được parent cung cấp để tạo Boot executable JAR tại phase `package`.
- `spring-boot-starter` cung cấp các thành phần cơ bản cho Spring Boot application, không cần Web MVC vì ví dụ này không mở HTTP server.
- `spring-boot-starter-test` cung cấp JUnit Jupiter và thư viện test; parent chọn phiên bản plugin tương thích.
- `<java.version>17</java.version>` chọn mục tiêu Java 17 cho compile ở cấu hình parent.
- `<packaging>jar</packaging>` giúp Maven tạo JAR nguồn để Boot plugin repackage.
- Tên artifact dự kiến là `target/resource-jar-demo-1.0.0.jar`. Nếu dùng `finalName` hay `classifier` khác, cần thay các lệnh theo tên thực.

**Nếu không dùng starter parent:** import BOM `spring-boot-dependencies` không tự gắn execution `repackage`. Bạn phải tự cấu hình Boot Maven Plugin, phiên bản plugin và execution goal `repackage` ở `package` để tạo archive chạy được. Đừng dùng một JAR thường thay thế rồi kết luận resource không nạp được.

### 6.3. Resource cần xác minh — `src/main/resources/samples/payload.txt`

Nội dung file (một dòng, có thể có newline cuối):

~~~text
IN_JAR_RESOURCE_OK
~~~

Ta cố ý dùng chuỗi ngắn, không phụ thuộc encoding ngoài ASCII. Trong code sẽ dùng `UTF-8` và `strip()` để bỏ newline/whitespace ở hai đầu, vì vậy dấu xuống dòng cuối file không làm thay đổi dấu hiệu đầu ra.

### 6.4. Cấu hình Spring — `src/main/resources/application.properties`

~~~properties
spring.application.name=resource-jar-demo
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=OFF
app.setting=from-packaged-config
~~~

- `web-application-type=none`: chạy ứng dụng như command-line program, không mở web server.
- `banner-mode=off`, `log-startup-info=false` và `logging.level.root=OFF`: giảm output nền trong ví dụ. Không đồng nghĩa mọi thư viện/JVM sẽ không bao giờ in gì ra stderr.
- `app.setting`: một Spring property được đọc từ `Environment` lúc runtime. Nó giúp kiểm tra **application.properties đã được đóng gói và được Spring Boot nạp**.
- Không đặt dữ liệu bí mật trong file được đóng gói. Ứng dụng thật nên lấy mật khẩu/token từ nguồn cấu hình bên ngoài thích hợp.

### 6.5. Class chính — `src/main/java/dev/example/ResourceJarApplication.java`

~~~java
package dev.example;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
import org.springframework.core.io.ClassPathResource;

@SpringBootApplication
public class ResourceJarApplication {

    public static void main(String[] args) {
        SpringApplication.run(ResourceJarApplication.class, args);
    }

    @Bean
    CommandLineRunner verifyResources(Environment environment) {
        return args -> {
            ClassPathResource resource =
                    new ClassPathResource("samples/payload.txt");

            String content;
            try (InputStream input = resource.getInputStream()) {
                content = new String(input.readAllBytes(),
                        StandardCharsets.UTF_8).strip();
            }

            System.out.println("CLASSPATH_RESOURCE=" + content);
            System.out.println("APP_SETTING="
                    + environment.getProperty("app.setting"));
            System.out.println("CWD_RESOURCE_EXISTS="
                    + Files.exists(Path.of("samples/payload.txt")));
        };
    }
}
~~~

**Vì sao mã này hoạt động trên Java 17?**

- `InputStream#readAllBytes()` có từ Java 9, `String#strip()` từ Java 11 và `Path.of()` từ Java 11: tất cả sẵn có trong Java 17.
- `CommandLineRunner` là functional interface của Spring Boot. Bean do method `@Bean` tạo được thực thi sau khi application context đã khởi động; vì ứng dụng không có web server/service giữ tiến trình, nó thường kết thúc sau khi runner hoàn thành.
- `ClassPathResource("samples/payload.txt")` tìm file theo classpath. Trong `java -jar`, Spring Boot loader trình bày `BOOT-INF/classes` như classpath root.
- `Environment#getProperty("app.setting")` lấy cấu hình Spring đã được nạp, không mở trực tiếp file `src/main/resources/application.properties`.
- `Files.exists(Path.of("samples/payload.txt"))` **cố tình kiểm tra sai loại vị trí** để chứng minh filesystem CWD không chứa file đó. Nó sẽ là `false` khi chạy trong thư mục độc lập chỉ có JAR.
- Vì `CommandLineRunner#run` có thể ném checked exception, code đọc `InputStream` có thể ném `IOException` mà lambda vẫn biên dịch được.

**Không có file nguồn nào được truy cập bằng `Path.of("src/main/resources/...")`**. Điều này rất quan trọng: JAR có thể chạy trên host không có dự án Maven.

### 6.6. Unit test — `src/test/java/dev/example/ResourceJarApplicationTest.java`

~~~java
package dev.example;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ResourceJarApplicationTest {

    @Test
    void canReadResourceFromTestClasspath() throws Exception {
        ClassPathResource resource =
                new ClassPathResource("samples/payload.txt");

        assertTrue(resource.exists());

        try (InputStream input = resource.getInputStream()) {
            String value = new String(input.readAllBytes(),
                    StandardCharsets.UTF_8).strip();
            assertEquals("IN_JAR_RESOURCE_OK", value);
        }
    }
}
~~~

Test trên xác nhận tài nguyên có thể được đọc từ **test classpath**. Khi chạy Maven, file trong `src/main/resources` đã được copy vào `target/classes` và thường có mặt trong classpath của test. Nó là **unit-level check**, chưa phải phép thử đóng gói của archive. Muốn bảo đảm độc lập phải chạy thêm JAR thực tế từ thư mục khác như mục 8.

Unit test không cần `@SpringBootTest` vì chỉ kiểm tra Spring `ClassPathResource` (không khởi động application context) và Java stream; điều này giúp test nhanh, mục tiêu rõ.

## 7. Build và kiểm tra file JAR trước khi chuyển thư mục

Tại thư mục dự án có `pom.xml`:

~~~bash
java -version
mvn -version
mvn clean verify
~~~

`mvn clean verify` xóa output build cũ rồi chạy đến phase `verify`, bao gồm compile, unit tests và package. Khi POM dùng Boot starter parent và khai báo Boot Maven Plugin như trên, goal `repackage` tạo executable archive trong `target`. Không chỉ dựa vào chữ `BUILD SUCCESS`; kiểm tra artifact và report thực tế.

### 7.1. Xem kết quả build

~~~text
target/
├── classes/
│   ├── application.properties
│   ├── dev/example/ResourceJarApplication.class
│   └── samples/payload.txt
├── surefire-reports/
│   └── ...
├── resource-jar-demo-1.0.0.jar
└── resource-jar-demo-1.0.0.jar.original
~~~

`.jar.original` là JAR gốc thường được giữ lại khi Boot plugin repackage main artifact mặc định; **không** lấy `.jar.original` làm file phát hành. Mỗi project có thể cấu hình khác (`classifier` hoặc `attach`), nên dùng đúng file executable được log xác nhận.

### 7.2. Liệt kê nội dung archive

~~~bash
jar tf target/resource-jar-demo-1.0.0.jar
~~~

Trong danh sách phải có:

~~~text
META-INF/MANIFEST.MF
BOOT-INF/classes/dev/example/ResourceJarApplication.class
BOOT-INF/classes/application.properties
BOOT-INF/classes/samples/payload.txt
BOOT-INF/lib/...
org/springframework/boot/loader/...
~~~

Nếu thiếu `BOOT-INF/classes/samples/payload.txt`, kiểm tra:

- Tệp thật có ở `src/main/resources/samples/payload.txt` (đúng chữ hoa/thường).
- `target/classes/samples/payload.txt` có được `maven-resources-plugin` copy hay không.
- Cấu hình `<resources>`, `<includes>`, `<excludes>`, filtering hoặc profile nào đã loại tệp.
- File nào thực sự được package; có thể bạn kiểm tra nhầm plain JAR, artifact cũ hoặc module library.

### 7.3. Đọc trực tiếp nội dung file trong JAR (tùy công cụ)

Trên Linux/macOS khi có `unzip`:

~~~bash
unzip -p target/resource-jar-demo-1.0.0.jar \
    BOOT-INF/classes/samples/payload.txt
~~~

Output mong đợi:

~~~text
IN_JAR_RESOURCE_OK
~~~

Với file config:

~~~bash
unzip -p target/resource-jar-demo-1.0.0.jar \
    BOOT-INF/classes/application.properties
~~~

Bạn phải thấy `app.setting=from-packaged-config`. Đây là **bằng chứng nội dung đóng gói**, độc lập với việc IDE/source file đã đúng. Không cần giải nén cả JAR để kiểm tra.

Nếu máy không có `unzip`, dùng lệnh `jar tf` để xem entry; có thể dùng `jar xf` trong một thư mục tạm riêng để kiểm tra nội dung, tránh trích xuất vào workspace và ghi đè các file khác.

## 8. Thực hành bắt buộc: chạy từ một thư mục độc lập

### 8.1. Linux/macOS: copy JAR vào thư mục mới

Từ **project root** sau khi `mvn clean verify` PASS:

~~~bash
RUN_DIR="$(mktemp -d)"
cp target/resource-jar-demo-1.0.0.jar "$RUN_DIR/app.jar"

# Thư mục mới không có src/, target/, pom.xml hay samples/
(cd "$RUN_DIR" && pwd && java -jar app.jar)
~~~

`mktemp -d` tạo thư mục mới; vì chỉ copy một file JAR, dưới CWD của process không có `samples/payload.txt` ở ngoài. `(...)` tạo subshell để đổi thư mục **chỉ cho lệnh chạy**, không làm terminal chính mất vị trí đang đứng.

Ba dòng do ứng dụng in (loại trừ dòng đường dẫn `pwd` và mọi log/diagnostic phụ thuộc môi trường) cần đúng:

~~~text
CLASSPATH_RESOURCE=IN_JAR_RESOURCE_OK
APP_SETTING=from-packaged-config
CWD_RESOURCE_EXISTS=false
~~~

**Điều kiện của kết quả `APP_SETTING`:** không truyền `--app.setting` và không có env var/system property hay nguồn cấu hình khác với độ ưu tiên cao hơn đã ghi đè. Nếu CI đặt `APP_SETTING`, hãy xem mục 10 để phân biệt hành vi hợp lệ với lỗi packaging.

Giải thích ba dòng:

1. `CLASSPATH_RESOURCE=IN_JAR_RESOURCE_OK`: nội dung file **được đọc thật** thông qua `ClassPathResource`, dù không có source tree.
2. `APP_SETTING=from-packaged-config`: Spring Boot đã nạp một property trong `application.properties` đóng trong JAR.
3. `CWD_RESOURCE_EXISTS=false`: đường dẫn file tương đối `samples/payload.txt` **không tồn tại ngoài filesystem** tại thư mục mới. Điều này củng cố rằng việc đọc tài nguyên ở dòng 1 không phụ thuộc đường dẫn CWD.

Nếu output trông giống nhưng process trả mã exit khác 0, vẫn phải xem lỗi. Ví dụ thêm lệnh tách biệt để xem exit code ngay sau khi chạy `java -jar` nếu cần; trong script POSIX `$?` là trạng thái lệnh vừa hoàn tất, không nên gọi lệnh khác trước khi kiểm tra.

### 8.2. Linux/macOS: chạy JAR bằng đường dẫn tuyệt đối mà không copy

Một biến thể khác cũng kiểm tra CWD khác project:

~~~bash
PROJECT_ROOT="$(pwd)"
RUN_DIR="$(mktemp -d)"
(
    cd "$RUN_DIR"
    java -jar "$PROJECT_ROOT/target/resource-jar-demo-1.0.0.jar"
)
~~~

Trong biến thể này, **JAR vẫn nằm ở thư mục project**, nhưng process chạy với CWD của thư mục tạm. Nó chứng minh rằng `java -jar` không yêu cầu CWD trùng thư mục chứa artifact. Để kiểm tra tính **tự mang theo dependency/resource** ở mức mạnh nhất, biến thể copy JAR ở mục 8.1 vẫn dễ quan sát hơn.

### 8.3. Windows PowerShell: tạo thư mục mới và chạy

Từ project root trong PowerShell:

~~~powershell
$runDir = Join-Path $env:TEMP ("boot-jar-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $runDir | Out-Null
Copy-Item .\target\resource-jar-demo-1.0.0.jar (Join-Path $runDir "app.jar")

Push-Location $runDir
try {
    java -jar .\app.jar
    if ($LASTEXITCODE -ne 0) {
        throw "java -jar failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
~~~

- `[guid]::NewGuid()` tạo một tên thư mục rất khó trùng; không dùng folder build cũ.
- `Push-Location`/`Pop-Location` khôi phục vị trí làm việc.
- `$LASTEXITCODE` kiểm tra mã trả về của Java process, không đánh đồng việc PowerShell thực thi script với JVM thành công.
- Kết quả ba dòng `CLASSPATH_RESOURCE`, `APP_SETTING`, `CWD_RESOURCE_EXISTS` vẫn tương tự ví dụ Linux/macOS nếu không có external overrides.
- Trong PowerShell, đường dẫn tương đối `.\app.jar` là file JAR **trên filesystem**, còn `samples/payload.txt` được ClassLoader tìm **bên trong archive**.

Không viết đường dẫn Linux `/tmp/...` làm đường dẫn cố định trong mã Java. Ứng dụng chỉ dùng relative classpath resource và Spring Environment, nên cùng một JAR có thể chạy trên những hệ thống tệp khác nhau.

### 8.4. Kiểm chứng rằng thư mục test thật sự độc lập

Điều kiện tối thiểu:

- Thư mục chạy **không chứa** `src/main/resources`.
- Không có file `samples/payload.txt` ngoài filesystem.
- Không dùng IDE hoặc Maven để khởi động class trực tiếp.
- Không thêm `target/classes` hoặc classpath của máy build bằng `-cp`.
- Chỉ cần `app.jar` và một Java runtime hợp lệ; dependencies cần thiết nằm trong executable Boot JAR.
- Java process exit thành công và có dấu hiệu đọc resource đúng.
- Nếu bạn cần giữ artifact nguyên trạng để release, có thể so hash của JAR ở project và bản copy.

Ví dụ tùy chọn khi máy có `sha256sum`:

~~~bash
sha256sum target/resource-jar-demo-1.0.0.jar
sha256sum "$RUN_DIR/app.jar"
~~~

Hai hash phải trùng nhau vì chỉ copy file, không sửa archive. Trên macOS có thể dùng `shasum -a 256`; trên PowerShell dùng `Get-FileHash`. Hash kiểm tra file copy không bị biến đổi, nhưng **không thay thế** kiểm tra startup/resource.

## 9. Gradle: làm cùng phép thử với `bootJar`

Dùng **cùng mã Java** và các file trong `src/main/resources` của mục 6. Không cần thay code chỉ vì build tool khác. Nếu dùng Gradle thay Maven, đặt hai file:

**`settings.gradle`**:

~~~groovy
rootProject.name = 'resource-jar-demo'
~~~

**`build.gradle`** (Groovy DSL, Java 17):

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
~~~

Giải thích:

- Gradle Java plugin tạo source sets và tasks `processResources`, `compileJava`, `test`.
- Spring Boot Gradle plugin tạo task `bootJar` để đóng gói **executable JAR**, khác với task `jar` tạo plain JAR.
- Dùng Gradle native `platform` để import Boot BOM cho runtime và test dependencies, vì Boot Gradle plugin đơn lẻ không có nghĩa mọi dependencies tự có version.
- `java.toolchain.languageVersion=17` yêu cầu JDK 17 cho các task Java phù hợp; Gradle daemon JVM có thể khác, nhưng phải tương thích bản Gradle đang chạy.
- `useJUnitPlatform()` cho phép test JUnit Jupiter được phát hiện.
- File `src/main/resources/samples/payload.txt` được `processResources` copy sang `build/resources/main/samples/payload.txt`, rồi `bootJar` đưa vào `BOOT-INF/classes/samples/payload.txt`.

Khi có Gradle Wrapper hợp lệ:

~~~bash
./gradlew clean build
jar tf build/libs/resource-jar-demo-1.0.0.jar
~~~

`./gradlew clean build` chạy các lifecycle tasks build/verification của project; `./gradlew bootJar` tạo executable archive nhưng **không tự chứng minh đã chạy unit test**. Nếu cần quality gate, hãy dùng `build` hoặc gọi các task verification bắt buộc.

Chạy độc lập trên Linux/macOS:

~~~bash
RUN_DIR="$(mktemp -d)"
cp build/libs/resource-jar-demo-1.0.0.jar "$RUN_DIR/app.jar"
(cd "$RUN_DIR" && java -jar app.jar)
~~~

Ba dòng xác minh giống mục 8.1. Trên Windows thay nguồn copy sang `.\build\libs\resource-jar-demo-1.0.0.jar` rồi dùng PowerShell script mục 8.3.

**Tránh lấy nhầm plain JAR:** một project Gradle có thể sinh thêm file `*-plain.jar` hoặc một archive khác. Hãy dùng output của task `bootJar`, kiểm tra `BOOT-INF/classes`, `BOOT-INF/lib` và manifest trước khi chạy.

## 10. Resource bên trong JAR khác cấu hình Spring bên ngoài

Spring Boot có cơ chế **externalized configuration**. Với các file application configuration mặc định, Boot tìm từ nhiều vị trí, trong đó có:

- Classpath root và `classpath:/config/` — có thể nằm trong executable JAR.
- Thư mục làm việc hiện tại `./`.
- Thư mục `./config/` và một số đường dẫn con của nó.
- Environment variables, system properties, command-line arguments và các property sources khác theo thứ tự ưu tiên đã được Spring quy định.

Điều này làm cho `APP_SETTING=from-packaged-config` **không phải một hằng bất biến** của runtime. Nếu nơi deploy cố ý cung cấp cấu hình bên ngoài với cùng key `app.setting`, Spring có thể dùng giá trị bên ngoài dù file `BOOT-INF/classes/application.properties` vẫn giữ nguyên.

### 10.1. Thử bằng command-line argument

Ở thư mục chỉ có `app.jar`:

~~~bash
java -jar app.jar --app.setting=from-command-line
~~~

Ba dòng do code in lúc này:

~~~text
CLASSPATH_RESOURCE=IN_JAR_RESOURCE_OK
APP_SETTING=from-command-line
CWD_RESOURCE_EXISTS=false
~~~

Kết quả hợp lệ vì command-line property có độ ưu tiên cao hơn `app.setting` trong file application config đóng gói. **Resource `samples/payload.txt` không đổi** vì code vẫn đọc classpath. Điều đó chứng minh cấu hình runtime độc lập với nội dung artifact.

### 10.2. Thử với `application.properties` bên ngoài

Tạo file `application.properties` **ngay trong CWD nơi chạy JAR** với nội dung:

~~~properties
app.setting=from-external-file
~~~

Khi chạy:

~~~bash
java -jar app.jar
~~~

kết quả mong đợi, nếu không có nguồn cấu hình nào khác ưu tiên cao hơn:

~~~text
CLASSPATH_RESOURCE=IN_JAR_RESOURCE_OK
APP_SETTING=from-external-file
CWD_RESOURCE_EXISTS=false
~~~

File config bên ngoài trong CWD có thể ghi đè giá trị cùng key nằm trong `BOOT-INF/classes/application.properties`. Đây là hành vi **được thiết kế**, không phải Spring Boot đọc nhầm resource. Cặp kiểm chứng giúp bạn nhận ra JAR đã nạp đúng tài nguyên nhưng Spring Environment sử dụng external configuration theo thứ tự ưu tiên.

**Cẩn trọng với việc tạo file test:** nếu yêu cầu một thư mục “hoàn toàn trống, chỉ có app.jar”, hãy chạy phép thử ban đầu trước; sau đó mới tạo `application.properties` bên ngoài cho thí nghiệm override. Không vô tình để file config từ lần thử trước làm sai baseline.

### 10.3. Biến môi trường

Spring có cơ chế relaxed binding cho property names. Một environment variable `APP_SETTING` thường có thể override `app.setting`. Trên Linux/macOS, để thực hành độc lập không bị env can thiệp, có thể kiểm tra `printenv APP_SETTING` trước khi chạy; trong PowerShell dùng `$env:APP_SETTING`. Không xuất toàn bộ environment lên CI log vì có thể chứa secrets.

Khi muốn kiểm chứng **đúng nội dung packaged**, nên đọc trực tiếp `BOOT-INF/classes/application.properties` trong JAR, còn khi muốn kiểm chứng **giá trị runtime**, dùng `Environment`/`@ConfigurationProperties` và ghi nhận các nguồn override hợp lệ.

### 10.4. `spring.config.location` và `spring.config.additional-location`

Spring Boot hỗ trợ chỉ định vị trí cấu hình bên ngoài:

~~~bash
java -jar app.jar --spring.config.additional-location=optional:file:./config/
~~~

Cú pháp `optional:` cho phép đường dẫn không tồn tại mà không nhất thiết làm startup fail. `spring.config.additional-location` **bổ sung** vị trí bên cạnh vị trí mặc định; `spring.config.location` có thể **thay thế** tập vị trí mặc định nếu được cấu hình. Dùng đúng nhu cầu; nếu thay thế mà quên nguồn classpath, có thể làm mất các default config bạn muốn giữ.

Với dự án chạy từ CWD không cố định (service manager, Kubernetes, scheduled task), nên đặt external config path rõ ràng thay vì phụ thuộc `./config/` nếu hệ thống triển khai không đảm bảo CWD.

## 11. Cách kiểm tra resource ở nhiều tầng

Một khi `CLASSPATH_RESOURCE` sai hoặc lỗi, hãy kiểm tra từ trái sang phải:

~~~text
src/main/resources/samples/payload.txt
          |
          | Maven resources:resources
          | hoặc Gradle processResources
          v
target/classes/samples/payload.txt
hoặc build/resources/main/samples/payload.txt
          |
          | Spring Boot repackage / bootJar
          v
BOOT-INF/classes/samples/payload.txt trong JAR
          |
          | Spring Boot launcher + class loader
          v
ClassPathResource("samples/payload.txt").getInputStream()
          |
          v
"IN_JAR_RESOURCE_OK"
~~~

Bảng khoanh vùng:

| Vị trí đầu tiên không đúng | Giả thuyết chính | Kiểm tra |
| --- | --- | --- |
| Source file thiếu | Đặt sai đường dẫn, quên commit | Kiểm tra `src/main/resources/samples/payload.txt` |
| Processed resource thiếu | Resource include/exclude, profile, plugin task | `target/classes` / `build/resources/main` |
| JAR thiếu entry | Sai artifact/task/plugin, packaging rules | `jar tf`, Boot plugin repackage, `bootJar` |
| JAR có entry nhưng code không nạp | Sai tên resource, dùng filesystem path, classloader không phù hợp | `ClassPathResource#getInputStream`, path chính xác |
| Nạp được resource nhưng app config sai | External config override, profile, `spring.config.location` | `Environment`, nội dung packaged config, CWD |
| IDE chạy nhưng `java -jar` lỗi | Source tree bị phụ thuộc ngầm; code dùng `getFile` hoặc `Path.of("src/...")` | Chạy JAR ở CWD trống, xem stack trace |
| Runtime chỉ lỗi trên Linux | Độ phân biệt chữ hoa/thường của đường dẫn | So `Samples` với `samples`, `Payload.txt` với `payload.txt` |
| JAR chạy được ở máy dev nhưng không ở CI | JDK/runtime thiếu hoặc version không tương thích | `java -version`, `UnsupportedClassVersionError` |
| `ClassNotFoundException` khi `java -jar` | Plain JAR, sai manifest hoặc dependency runtime thiếu | `BOOT-INF/lib`, `Main-Class`, `Start-Class` |

**Không chữa bằng cách copy `src/main/resources` vào thư mục release** chỉ để ứng dụng chạy được; như vậy bạn đã che lỗi đóng gói hoặc lỗi đọc resource, trái mục tiêu phát hành JAR độc lập.

## 12. Những sai lầm phổ biến trong code

### Sai 1: giả định project root luôn tồn tại

~~~java
Files.readString(Path.of("src/main/resources/samples/payload.txt"));
~~~

Chỉ hoạt động nếu process đang chạy từ project root **và** source tree vẫn còn. Đây không phải cách kiểm tra một packaged resource. Sửa bằng `ClassPathResource#getInputStream()`.

### Sai 2: dùng `getFile()` trên resource trong JAR

~~~java
new ClassPathResource("samples/payload.txt").getFile();
~~~

Khi chạy từ IDE classpath directory, nó có thể thành công; khi resource nằm trong archive, `getFile()` có thể báo lỗi vì không phải physical filesystem file. Sửa bằng `getInputStream()`; nếu thư viện cần `File`, copy resource tạm ra filesystem.

### Sai 3: nhầm tên path với entry name

Trong JAR có `BOOT-INF/classes/samples/payload.txt`, nhưng khi truy cập:

~~~java
new ClassPathResource("samples/payload.txt");
~~~

**Không** viết `new ClassPathResource("BOOT-INF/classes/samples/payload.txt")` vì launcher đã coi `BOOT-INF/classes` là classpath root. Sai prefix sẽ dẫn tới không tìm được resource.

### Sai 4: dùng dấu `/` sai với ClassLoader

~~~java
ResourceJarApplication.class.getClassLoader()
        .getResourceAsStream("/samples/payload.txt");
~~~

`ClassLoader` API mong tên resource dạng tương đối classpath root, **không có dấu `/` đầu**. Sửa thành `"samples/payload.txt"`. Nếu dùng `SomeClass.class.getResourceAsStream("/samples/payload.txt")` thì dấu `/` có ý nghĩa tìm từ root của classpath; hai API không đồng nhất.

### Sai 5: kiểm tra chỉ một nơi

`mvn test` xanh nhưng `bootJar` hoặc `repackage` làm rơi resource; ngược lại, `jar tf` thấy file nhưng code runtime lại đọc relative filesystem path. Cần **cả artifact inspection và isolated run**; không bỏ một trong hai.

### Sai 6: đóng gói bí mật và file cần ghi

File classpath trong JAR không phải chỗ cho mật khẩu runtime, token, upload data hay file nhật ký. Đóng gói như vậy khiến thay đổi dữ liệu cần build lại artifact, tăng nguy cơ rò rỉ secrets và có thể sai kỳ vọng ghi. Dùng external configuration/file storage với quyền truy cập phù hợp.

### Sai 7: chạy nhầm file JAR

- Maven có thể có `*.jar.original` sau repackage.
- Gradle có thể có `*-plain.jar`.
- Multi-module có nhiều JAR library/application.
- Custom `classifier` hoặc `finalName` thay đổi tên.

Chọn artifact được tạo bởi Spring Boot packaging goal/task. Kiểm tra manifest và `BOOT-INF` trước khi chạy.

## 13. Khi dùng container, service manager hoặc Docker

Khái niệm CWD vẫn quan trọng khi ứng dụng được container hoặc system service khởi động. Ví dụ Dockerfile **minh họa**, chỉ dùng sau khi đã build JAR tại local/CI:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /opt/app
COPY target/resource-jar-demo-1.0.0.jar app.jar
ENTRYPOINT ["java", "-jar", "app.jar"]
~~~

Trong ví dụ này, `WORKDIR /opt/app` quyết định CWD; ứng dụng vẫn tìm `samples/payload.txt` từ classpath bên trong `app.jar`. Nếu đổi `WORKDIR` hoặc cấu hình orchestrator thay working directory, resource classpath vẫn độc lập; `Path.of("relative.txt")` có thể thay ý nghĩa.

Dockerfile ở trên yêu cầu bạn **đã build file JAR ở build context** và không có chính sách container riêng. Đây là ví dụ đơn giản, không bao gồm non-root user, provenance, image scanning, read-only filesystem hay multi-stage build. Trong hệ thống thực, áp dụng policy bảo mật và nguyên tắc build reproducibility của tổ chức.

Với systemd hoặc Windows service, working directory cũng có thể được chỉ định riêng. Đừng suy ra CWD từ thư mục đặt executable JAR. Hãy xác định đường dẫn external configuration rõ ràng.

## 14. Checklist CI cho kiểm chứng portable executable JAR

Một quality gate hữu ích nên kiểm tra:

1. **Source đúng:** resource có tại `src/main/resources/...` trong commit đang build.
2. **Resources task đúng:** file được copy vào output classes/resources của build.
3. **Test pass:** unit tests phát hiện resource và không có failed/errors.
4. **Artifact đúng:** Boot executable JAR tồn tại, có manifest đúng, `BOOT-INF/classes/samples/payload.txt` và các dependency cần thiết trong `BOOT-INF/lib`.
5. **Artifact duy nhất:** CI lấy đúng JAR app, không lấy `.jar.original`, `*-plain.jar`, JAR thư viện hoặc bản build từ lần trước.
6. **CWD độc lập:** chạy trong một thư mục tạm mới không có source/resources directory.
7. **Không cần build tool:** chỉ dùng runtime Java để chạy `java -jar` sau khi copy JAR.
8. **Exit code bằng 0:** ứng dụng hoàn tất, không có stack trace.
9. **Dấu hiệu đọc resource đúng:** `CLASSPATH_RESOURCE=IN_JAR_RESOURCE_OK`.
10. **Spring config đúng:** `APP_SETTING=from-packaged-config` trong môi trường không bị override; kiểm tra external override riêng khi cần.
11. **Không phụ thuộc file ngoài:** `CWD_RESOURCE_EXISTS=false` trong CWD mới.
12. **Artifact integrity:** hash JAR copy trùng bản build nếu cần; lưu artifact checksum.
13. **Đa nền tảng:** nếu deploy Linux sau khi dev trên Windows, kiểm tra path case sensitivity và separator.
14. **Không ghi secrets:** không đưa env vars hoặc nội dung cấu hình nhạy cảm vào log smoke test.
15. **Dọn môi trường tạm:** cleanup folder được tạo bởi job, không xóa tùy tiện folder ngoài phạm vi CI.

### Script kiểm tra tối thiểu trên Linux/macOS

Từ project root sau khi build:

~~~bash
set -eu
mvn clean verify

JAR="$(pwd)/target/resource-jar-demo-1.0.0.jar"
RUN_DIR="$(mktemp -d)"
cp "$JAR" "$RUN_DIR/app.jar"

output="$(cd "$RUN_DIR" && java -jar app.jar)"
printf '%s\n' "$output"

printf '%s\n' "$output" |
    grep -Fx 'CLASSPATH_RESOURCE=IN_JAR_RESOURCE_OK'
printf '%s\n' "$output" |
    grep -Fx 'APP_SETTING=from-packaged-config'
printf '%s\n' "$output" |
    grep -Fx 'CWD_RESOURCE_EXISTS=false'
~~~

Đây là một **script smoke test minh họa**: với `set -e`, lệnh `java -jar` hoặc `grep` không thành công sẽ khiến script dừng với exit code khác 0. Thực tế cần có cleanup bằng `trap` và chính sách artifact/runner tùy CI, đồng thời loại trừ nguồn config ngoài như `APP_SETTING` nếu baseline phải cố định. Script không gọi Maven từ trong thư mục tạm; Maven chỉ thực hiện tại project root ở bước build.

## 15. Tình huống trước–sau dễ nhầm

### Tình huống A — IDE xanh, triển khai lỗi

**Trước:** Java code dùng `Path.of("src/main/resources/samples/payload.txt")`. IDE chạy tại project root nên tìm được file. Sau khi copy JAR sang `/opt/app` thì `NoSuchFileException` xuất hiện.

**Sau:** đổi cách đọc thành `new ClassPathResource("samples/payload.txt").getInputStream()`, xác nhận file ở `BOOT-INF/classes/samples/payload.txt`. Chạy thử từ CWD trống, kết quả đọc đúng.

### Tình huống B — JAR chạy nhưng config khác

**Trước:** test đòi `APP_SETTING=from-packaged-config`; thực tế hệ thống có `./application.properties` chứa `app.setting=from-external-file`. JAR vẫn chạy và resource được đọc đúng, nhưng test so giá trị config fail.

**Sau:** phân biệt config đóng trong JAR và externalized config, kiểm tra CWD/property precedence. Test baseline trong thư mục không có config ngoài, và kiểm tra override ở testcase khác.

### Tình huống C — sao chép source resources để “fix”

**Trước:** build không copy `payload.txt` vào JAR; người triển khai copy cả `src/main/resources` sang máy production để đường dẫn tương đối hoạt động.

**Sau:** sửa `<resources>`/`processResources` và cách đọc classpath, không đòi hỏi source tree ở production. CI phải chặn release nếu `jar tf` thiếu resource.

### Tình huống D — nhầm Gradle plain JAR

**Trước:** dùng `java -jar build/libs/resource-jar-demo-1.0.0-plain.jar`, gặp thiếu launcher/dependency.

**Sau:** lấy output `bootJar`, kiểm tra `BOOT-INF/lib` và chạy từ thư mục độc lập. Plain JAR phù hợp cho mục đích thư viện, không tự có cùng semantics của Boot executable.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Chạy `java -jar /opt/app/app.jar` khi CWD là `/tmp/run`. `Path.of("data.txt")` tìm ở đâu?

**Đáp án:** `/tmp/run/data.txt`. Nó dựa vào CWD, không tự tìm ở `/opt/app`.

**Câu 2.** File resource nằm trong JAR tại `BOOT-INF/classes/samples/payload.txt`. Với `ClassPathResource` nên truyền đường dẫn nào?

**Đáp án:** `samples/payload.txt`. Boot loader đã cung cấp classpath root tương ứng `BOOT-INF/classes`.

**Câu 3.** Vì sao `ClassPathResource#getFile()` có thể chạy trong IDE nhưng lỗi khi chạy JAR?

**Đáp án:** IDE thường dùng exploded classes trên filesystem; bên trong executable JAR, resource không phải file vật lý riêng. Đọc bằng `getInputStream()`.

**Câu 4.** Unit test đọc resource từ test classpath pass có đủ chứng minh bản JAR portable không?

**Đáp án:** Chưa. Cần xác minh entry trong JAR và chạy `java -jar` từ thư mục không có source tree.

**Câu 5.** Kết quả `CWD_RESOURCE_EXISTS=false` nhưng `CLASSPATH_RESOURCE=IN_JAR_RESOURCE_OK` có mâu thuẫn không?

**Đáp án:** Không. Một phép thử filesystem CWD; phép kia đọc classpath resource bên trong JAR. Đây là kết quả mong muốn.

**Câu 6.** Thêm file `application.properties` bên ngoài chứa `app.setting=override` làm kết quả khác với packaged config. Có phải resource trong JAR hỏng?

**Đáp án:** Không nhất thiết. Spring Boot ưu tiên các nguồn cấu hình runtime theo quy tắc externalized configuration; phải kiểm tra resource trong JAR và value Environment riêng biệt.

**Câu 7.** Khi dùng Maven starter parent và khai báo `spring-boot-maven-plugin`, goal nào giúp tạo executable JAR?

**Đáp án:** Goal `repackage` được bind vào phase `package` theo cấu hình của starter parent.

**Câu 8.** Trong Gradle, task nào đóng gói executable Spring Boot JAR?

**Đáp án:** `bootJar`. `jar` thông thường có mục đích khác và không tự tương đương `bootJar`.

**Câu 9.** Có nên dùng một đường dẫn `src/main/resources` trong Docker image để đọc resource đã đóng trong JAR không?

**Đáp án:** Không. Hãy đọc resource qua classpath; Docker image không cần copy source tree chỉ để ứng dụng chạy.

**Câu 10.** Vì sao chỉ có `jar tf` chưa đủ?

**Đáp án:** Nó chứng minh file nằm trong archive, nhưng không chứng minh JVM boot launcher chạy được, code dùng path đúng, Spring config được load đúng hoặc process exit 0.

## 17. Ghi nhớ và checklist cuối

- [ ] Tạo **Boot executable JAR**, không lấy plain JAR hay `.jar.original`.
- [ ] Resource nằm ở `src/main/resources/...` và trong artifact là `BOOT-INF/classes/...`.
- [ ] Code đọc classpath resource qua stream, không dựa vào `src/main/resources` hoặc `Resource#getFile()`.
- [ ] Chạy `java -jar` từ một CWD mới không có source/target/build/classes.
- [ ] Kiểm tra đúng nội dung đã đọc và mã trả về của Java process.
- [ ] Hiểu CWD, JAR location và classpath resource là ba khái niệm khác nhau.
- [ ] Phân biệt `application.properties` đóng gói với external configuration có thể override.
- [ ] Kiểm tra manifest launcher, dependency nested JAR, source resource và processed resource khi có lỗi.
- [ ] Không ghi dữ liệu runtime vào resource đóng trong JAR.
- [ ] Có automated smoke test cho artifact trước khi phát hành.

**Kết luận:** Một ứng dụng thật sự portable không cần nằm cạnh source tree. Khi JAR được đóng gói đúng, `ClassPathResource("samples/payload.txt")` sẽ đọc được dữ liệu ở `BOOT-INF/classes/samples/payload.txt`, ngay cả khi `Path.of("samples/payload.txt")` trả về file không tồn tại trong thư mục làm việc. Đây là phép chứng minh quan trọng nhất của bài học.

## 18. Tài liệu chính thức

1. [Spring Boot Maven Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/maven-plugin/packaging.html)
2. [Spring Boot — Executable JAR Format](https://docs.spring.io/spring-boot/specification/executable-jar/nested-jars.html)
3. [Spring Boot — Launching Executable Jars](https://docs.spring.io/spring-boot/specification/executable-jar/launching.html)
4. [Spring Boot — NestedJarFile and Class Loading](https://docs.spring.io/spring-boot/specification/executable-jar/jarfile-class.html)
5. [Spring Framework — Resources / ClassPathResource](https://docs.spring.io/spring-framework/reference/core/resources.html)
6. [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
7. [Spring Boot Maven Plugin — Using the Plugin](https://docs.spring.io/spring-boot/maven-plugin/using.html)
8. [Spring Boot Gradle Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/gradle-plugin/packaging.html)
9. [Spring Boot — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
10. [Oracle Java — ClassLoader#getResourceAsStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
