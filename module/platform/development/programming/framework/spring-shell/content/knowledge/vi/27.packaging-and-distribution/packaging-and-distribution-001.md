# Tạo executable JAR phù hợp cấu hình Spring Boot

## 1. Executable JAR dùng để làm gì?

Trong quá trình phát triển, Spring Shell thường được chạy từ IDE hoặc bằng task của Maven/Gradle. Khi phân phối CLI, người dùng cần một artifact có thể chạy trên máy khác mà không phải tự ghép classpath của ứng dụng và từng thư viện.

Spring Boot cung cấp executable JAR chứa:

- Class và resource của ứng dụng.
- Các dependency cần thiết khi chạy.
- Spring Boot Loader để nạp ứng dụng từ cấu trúc JAR có thư viện lồng bên trong.
- Manifest mô tả loader và main class của ứng dụng.

Sau khi đóng gói, người dùng có thể chạy bằng `java -jar`. Đây là cách phân phối phù hợp cho CLI Spring Shell khi môi trường đích có Java runtime tương thích.

Một JAR Java thông thường chỉ chứa class và resource của project; lệnh `java -jar` sẽ không tự tìm các dependency bên ngoài nếu không có classpath hoặc launcher phù hợp. Vì vậy, chỉ chạy `mvn package` hoặc task `jar` chưa chắc đã tạo ra executable JAR của Spring Boot. Cần để Spring Boot Maven Plugin hoặc Gradle Plugin đóng gói lại artifact.

## 2. Chọn phiên bản Spring Boot và Spring Shell tương thích

Trước khi cấu hình build, hãy chọn một cặp phiên bản thuộc cùng dòng tương thích. Bảng tương thích do dự án Spring Shell công bố có các cặp chính sau:

| Spring Boot | Spring Shell |
|---|---|
| 3.4.x hoặc 3.5.x | 3.4.x |
| 4.0.x hoặc 4.1.x | 4.0.x |
| 3.3.x | 3.3.x |
| 3.2.x | 3.2.x |
| 2.7.x | 2.1.x |

Không chọn Spring Shell 4.x chỉ vì đây là phiên bản mới hơn nếu ứng dụng vẫn dùng Spring Boot 3.x. Spring Shell 4 dựa trên Spring Framework 7 và yêu cầu Spring Boot 4 trở lên. Khi nâng cấp major version, hãy kiểm tra cả migration guide vì ngoài phiên bản dependency, package và API của Spring Shell cũng có thay đổi.

Ví dụ trong bài sử dụng Spring Boot `3.4.13`, Spring Shell `3.4.3` và Java 17. Đây là một cặp thuộc dòng tương thích. Nếu dự án dùng Boot 3.5.x hoặc Boot 4.x, hãy thay phiên bản theo compatibility matrix và dùng Spring Shell tương ứng. Spring Boot 3.4.13 yêu cầu Java 17 trở lên; Spring Boot 4.0.10 cũng có baseline Java 17. Một terminal provider đặc biệt có thể có yêu cầu cao hơn baseline này, ví dụ JLine FFM cần JDK 22+.

Không tự nâng riêng Spring Framework, Spring Boot hoặc JLine bằng một phiên bản tùy ý. Các release Spring Boot được kiểm thử với một bộ dependency cụ thể; override không phù hợp có thể tạo lỗi tương thích khi build hoặc khi khởi động JAR.

## 3. Cấu trúc tối thiểu của ứng dụng Spring Shell

Ứng dụng cần một main class để khởi tạo Spring Boot:

~~~java
package com.example.cli;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CliApplication {

    public static void main(String[] args) {
        SpringApplication.run(CliApplication.class, args);
    }
}
~~~

`@SpringBootApplication` bật cấu hình tự động và component scan từ package của lớp ứng dụng. Vì vậy, nên đặt command và service trong package con hoặc cấu hình scan rõ ràng để chúng được đưa vào executable JAR và được Spring phát hiện khi khởi động.

Ví dụ một command đơn giản:

~~~java
package com.example.cli.commands;

import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
public class BuildCommands {

    @ShellMethod(key = "build info", value = "Hiển thị thông tin bản build")
    public String info() {
        return "Build CLI is ready";
    }

    @ShellMethod(key = "project list", value = "Liệt kê project theo chủ sở hữu")
    public String list(@ShellOption(value = "--owner", defaultValue = "all") String owner) {
        return "Projects for " + owner;
    }
}
~~~

Khi chạy ứng dụng đã đóng gói, command này phải xuất hiện trong `help` và có thể được gọi qua shell runner phù hợp.

Ví dụ command này dùng legacy annotation model của Spring Shell 3.4.x (`@ShellComponent`, `@ShellMethod`). Spring Shell 4.0 đã loại bỏ các annotation legacy này; khi dùng 4.0.x, hãy chuyển sang `@Command`, `@Option`, `@Argument` và các annotation mới theo migration guide.

## 4. Đóng gói bằng Maven

### Cấu hình pom.xml

Một cấu hình Maven thường dùng Spring Boot parent để nhận dependency management, compiler defaults và execution `repackage` được cấu hình sẵn.

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>build-cli</artifactId>
    <version>1.0.0</version>
    <name>build-cli</name>
    <description>Command line application built with Spring Shell</description>

    <properties>
        <java.version>17</java.version>
        <spring-shell.version>3.4.3</spring-shell.version>
        <start-class>com.example.cli.CliApplication</start-class>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.shell</groupId>
                <artifactId>spring-shell-dependencies</artifactId>
                <version>${spring-shell.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.shell</groupId>
            <artifactId>spring-shell-starter</artifactId>
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

Các phần quan trọng:

- `spring-boot-starter-parent` quản lý phiên bản dependency Spring Boot và cấu hình Maven mặc định.
- `spring-shell-dependencies` BOM quản lý các module Spring Shell cùng một release train.
- `spring-shell-starter` đưa các module cần thiết cho Spring Shell vào runtime classpath.
- `spring-boot-maven-plugin` đóng gói JAR thực thi bằng goal `repackage`.
- `start-class` chỉ rõ lớp khởi động nếu cần cố định main class. Plugin cũng có thể tự phát hiện lớp chứa `main` nếu chỉ có một ứng viên phù hợp.

Khi kế thừa `spring-boot-starter-parent`, execution `repackage` đã được khai báo với ID `repackage`. Chỉ cần thêm plugin như ví dụ; không cần khai báo thêm một execution khác với ID mặc định vì có thể khiến goal chạy hai lần.

### Build artifact

Trên Linux/macOS:

~~~bash
./mvnw clean package
~~~

Trên Windows:

~~~powershell
.\mvnw.cmd clean package
~~~

Nếu dự án không dùng Maven Wrapper, chạy `mvn clean package` sau khi đã cài Maven đúng phiên bản. Artifact mặc định nằm trong `target/`, ví dụ:

~~~text
target/build-cli-1.0.0.jar
~~~

Khi parent không được dùng, vẫn có thể gọi Spring Boot Maven Plugin nhưng phải tự quản lý version và khai báo execution có goal `repackage`. Đồng thời import `spring-boot-dependencies` BOM để quản lý dependency Spring Boot. Ví dụ rút gọn:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <version>${spring-boot.version}</version>
            <executions>
                <execution>
                    <goals>
                        <goal>repackage</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

Trong cấu hình không dùng parent, hãy thay `${spring-boot.version}` bằng property đã định nghĩa, đồng bộ với Boot BOM đang import.

## 5. Đóng gói bằng Gradle

Spring Boot Gradle Plugin tạo task `bootJar` để đóng gói executable JAR. Khi plugin Java và Spring Boot được áp dụng, task `assemble` và `build` được cấu hình để chạy `bootJar`.

Ví dụ `build.gradle` dùng Groovy DSL:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

ext {
    set('springShellVersion', '3.4.3')
}

dependencyManagement {
    imports {
        mavenBom "org.springframework.shell:spring-shell-dependencies:${springShellVersion}"
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.shell:spring-shell-starter'
}

springBoot {
    mainClass = 'com.example.cli.CliApplication'
}
~~~

Trong ví dụ, Spring Boot Gradle Plugin tạo `bootJar`; dependency management plugin nhập BOM của Spring Shell để các module dùng cùng phiên bản. Nếu dự án đã có cơ chế quản lý dependency bằng Gradle platform hoặc version catalog, hãy tích hợp BOM vào cơ chế đó thay vì khai báo nhiều nguồn version chồng chéo.

Build executable JAR:

~~~bash
./gradlew clean bootJar
~~~

Trên Windows:

~~~powershell
.\gradlew.bat clean bootJar
~~~

Artifact nằm trong `build/libs/`, ví dụ `build-cli-1.0.0.jar`. Task `build` cũng chạy `bootJar` thông qua `assemble`, nên có thể dùng `./gradlew clean build` khi muốn chạy cả các kiểm tra đã cấu hình.

Nếu dùng Kotlin DSL (`build.gradle.kts`), cấu hình `mainClass` bằng `mainClass.set("com.example.cli.CliApplication")` trong `springBoot {}` hoặc trong task `bootJar`.

## 6. Spring Boot repackages JAR như thế nào?

Spring Boot Maven Plugin và Gradle Plugin tạo cấu trúc executable JAR riêng. Một số thành phần thường thấy:

~~~text
build-cli-1.0.0.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   ├── application.properties
    │   └── com/example/cli/...
    ├── lib/
    │   ├── spring-boot-*.jar
    │   ├── spring-shell-*.jar
    │   └── other-dependencies.jar
    └── classpath.idx
~~~

`BOOT-INF/classes` chứa class và resource của ứng dụng; `BOOT-INF/lib` chứa các dependency lồng bên trong. Manifest chứa thông tin launcher và main class ứng dụng. Với layout JAR mặc định, Spring Boot Loader khởi chạy ứng dụng rồi nạp các dependency lồng.

Hai thuộc tính manifest có ý nghĩa khác nhau:

- `Main-Class`: lớp launcher của Spring Boot.
- `Start-Class`: main class của ứng dụng, ví dụ `com.example.cli.CliApplication`.

Spring Boot Plugin quản lý các thuộc tính này. Nếu main class không được phát hiện đúng, hãy cấu hình `mainClass` trong Spring Boot Plugin hoặc `start-class` khi dùng parent. Không cố ghi đè `Main-Class` bằng `maven-jar-plugin` theo cách JAR Java thông thường, vì `repackage` sẽ quản lý manifest của executable archive.

## 7. Chạy JAR ở interactive và non-interactive mode

Sau khi đóng gói, hãy kiểm tra cả hai cách sử dụng.

### Interactive mode

Người dùng khởi động shell rồi nhập nhiều command trong cùng phiên:

~~~bash
java -jar target/build-cli-1.0.0.jar --spring.shell.interactive.enabled=true
~~~

Ví dụ trên dành cho Spring Shell 3.4.x, nơi chỉ `NonInteractiveShellRunner` được bật mặc định. Trong Spring Shell 4.0.x, interactive mode được bật mặc định nên có thể chạy `java -jar target/build-cli-1.0.0.jar` để vào REPL. Trong interactive mode, shell hiển thị prompt và chờ người dùng nhập lệnh. Đây là cách phù hợp cho công cụ quản trị hoặc CLI cần nhiều thao tác liên tiếp.

### Non-interactive mode

Ứng dụng chạy một command từ tham số tiến trình rồi kết thúc:

~~~bash
java -jar target/build-cli-1.0.0.jar help
java -jar target/build-cli-1.0.0.jar build info
~~~

Các lệnh trên dùng mặc định non-interactive của Spring Shell 3.4.x. Với Spring Shell 4.0.x, interactive mode mặc định vẫn được bật khi có tham số; hãy đặt `spring.shell.interactive.enabled=false` để chạy command từ process arguments:

~~~bash
java -jar target/build-cli-1.0.0.jar --spring.shell.interactive.enabled=false help
java -jar target/build-cli-1.0.0.jar --spring.shell.interactive.enabled=false build info
~~~

Nếu command nhận option, có thể truyền tiếp sau tên command:

~~~bash
java -jar target/build-cli-1.0.0.jar project list --owner=team-a
~~~

Với Spring Shell 4.0.x, thêm `--spring.shell.interactive.enabled=false` trước tên command như ví dụ trên.

### Khác biệt cấu hình giữa Spring Shell 3.4 và 4.0

Không nên sao chép property về interactive mode giữa hai major version mà không kiểm tra tài liệu tương ứng:

| Dòng Spring Shell | Hành vi mặc định và cấu hình |
|---|---|
| 3.3.x/3.4.x | `NonInteractiveShellRunner` được bật mặc định. Muốn có REPL, bật `spring.shell.interactive.enabled=true`. |
| 4.0.x | Interactive mode được bật mặc định, kể cả khi có tham số command line. Muốn chạy command từ process arguments, đặt `spring.shell.interactive.enabled=false`. |

Ví dụ với Spring Shell 3.4.x, thêm vào `application.properties` để mở REPL:

~~~properties
spring.shell.interactive.enabled=true
~~~

Ví dụ với Spring Shell 4.0.x, dùng non-interactive mode để chạy command từ tham số tiến trình:

~~~bash
java -jar build-cli.jar --spring.shell.interactive.enabled=false build info
~~~

Property này chọn runner. Nó không phải option nghiệp vụ của command. Khi phân phối CLI, hãy ghi rõ mode mặc định và cách chuyển mode trong tài liệu sử dụng.

## 8. Cấu hình Spring Boot bên ngoài executable JAR

Executable JAR không nên chứa cấu hình riêng của từng máy hoặc môi trường triển khai. Hãy đóng gói giá trị mặc định không nhạy cảm, sau đó cho phép môi trường đích cung cấp cấu hình bên ngoài.

Spring Boot tự tìm `application.properties` hoặc `application.yaml` ở classpath và một số vị trí bên ngoài JAR, gồm thư mục hiện tại, `./config/` và các thư mục con trực tiếp của `config/`. File cấu hình bên ngoài có thể ghi đè giá trị mặc định đóng gói trong JAR.

Ví dụ file `application.properties` nằm trong `src/main/resources`:

~~~properties
spring.application.name=build-cli
app.export.default-format=json
app.export.output-directory=./output
~~~

Khi phân phối, có thể đặt file override cạnh JAR:

~~~text
distribution/
├── build-cli-1.0.0.jar
└── config/
    └── application.properties
~~~

Ví dụ `config/application.properties` trên máy đích:

~~~properties
app.export.output-directory=/var/lib/build-cli/output
~~~

Chạy từ thư mục `distribution/`, Spring Boot tự phát hiện file cấu hình trong `config/`.

### Profile theo môi trường

Đặt giá trị chung trong `application.properties`, giá trị riêng trong `application-prod.properties` hoặc `application-dev.properties`. Kích hoạt profile khi chạy:

~~~bash
java -jar build-cli.jar --spring.profiles.active=prod build info
~~~

Ví dụ này chạy theo mặc định non-interactive của Spring Shell 3.4.x. Với Spring Shell 4.0.x, thêm `--spring.shell.interactive.enabled=false` trước `--spring.profiles.active=prod`.

Hoặc dùng biến môi trường:

~~~bash
SPRING_PROFILES_ACTIVE=prod java -jar build-cli.jar build info
~~~

Nếu dùng Spring Shell 4.0.x, thêm `--spring.shell.interactive.enabled=false` sau tên JAR để command được thực thi từ process arguments.

Trên PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "prod"
java -jar .\build-cli.jar build info
~~~

Trong ứng dụng Spring Shell 4.0.x, thêm `--spring.shell.interactive.enabled=false` vào lệnh `java -jar` nếu muốn chạy command từ tham số tiến trình.

### Thứ tự ưu tiên cấu hình

Spring Boot cho phép cấu hình từ file trong JAR, file bên ngoài, biến môi trường, system property và command-line property. Nhìn chung, command-line property có độ ưu tiên cao hơn file cấu hình và có thể ghi đè giá trị đã đóng gói.

Ví dụ:

~~~bash
java -jar build-cli.jar \
  --spring.profiles.active=prod \
  --app.export.default-format=csv \
  build info
~~~

Ví dụ này dùng mặc định non-interactive của Spring Shell 3.4.x. Với Spring Shell 4.0.x, thêm `--spring.shell.interactive.enabled=false` ngay sau tên JAR.

Nếu muốn bổ sung thư mục cấu hình ngoài mà vẫn giữ các vị trí tìm kiếm mặc định, dùng `spring.config.additional-location`:

~~~bash
java -jar build-cli.jar \
  --spring.config.additional-location=optional:file:./runtime-config/ \
  build info
~~~

Với Spring Shell 4.0.x, thêm `--spring.shell.interactive.enabled=false` ngay sau tên JAR để chạy command từ process arguments.

`spring.config.location` thay thế các vị trí tìm kiếm mặc định; `spring.config.additional-location` bổ sung vị trí mới. Dùng nhầm hai property có thể khiến ứng dụng không còn nạp file cấu hình mà bạn tưởng vẫn được đọc.

Không đóng gói mật khẩu, access token, private key hoặc thông tin bí mật vào `application.properties` trong JAR. Dùng biến môi trường, secret manager hoặc file được cấp quyền phù hợp trên máy đích.

## 9. Chọn main class và tên artifact

Nếu project có nhiều lớp chứa `main(...)`, plugin có thể không xác định được lớp khởi động duy nhất. Với Maven parent, khai báo:

~~~xml
<properties>
    <start-class>com.example.cli.CliApplication</start-class>
</properties>
~~~

Nếu không dùng parent, cấu hình `mainClass` trong `spring-boot-maven-plugin`:

~~~xml
<configuration>
    <mainClass>com.example.cli.CliApplication</mainClass>
</configuration>
~~~

Với Gradle:

~~~groovy
springBoot {
    mainClass = 'com.example.cli.CliApplication'
}
~~~

Tên artifact có thể đặt bằng `finalName` trong Maven:

~~~xml
<build>
    <finalName>build-cli</finalName>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

Khi đó artifact thực thi có thể là `target/build-cli.jar`. Với Gradle, dùng `archiveFileName` trên task `bootJar`:

~~~groovy
tasks.named('bootJar') {
    archiveFileName = 'build-cli.jar'
}
~~~

Tên file phân phối nên ổn định và có version rõ ràng. Nếu script triển khai tham chiếu tên artifact, hãy giữ quy ước tên nhất quán giữa các bản phát hành.

## 10. Khi cần cả JAR thực thi và JAR dùng làm dependency

Executable JAR không phải artifact phù hợp để dùng như thư viện thông thường. Class của ứng dụng nằm dưới `BOOT-INF/classes`, nên một project khác không thể tìm thấy chúng theo cách classpath JAR tiêu chuẩn.

Nếu project cần phát hành cả ứng dụng chạy độc lập và thư viện dùng lại, hãy tạo hai artifact:

- JAR thường chứa class của project để project khác có thể dùng làm dependency.
- JAR executable chứa loader và dependency để chạy bằng `java -jar`.

Với Maven, cấu hình classifier cho execution `repackage` có ID `repackage` khi dùng Spring Boot parent:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <id>repackage</id>
            <configuration>
                <classifier>exec</classifier>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Kết quả có thể gồm JAR thường và JAR có classifier `exec`. Chỉ dùng JAR `exec` để chạy ứng dụng; dùng JAR thường làm dependency.

Với Gradle, task `jar` và `bootJar` có thể tạo artifact riêng. Theo mặc định, Gradle Spring Boot Plugin dùng classifier `plain` cho JAR thường để phân biệt với executable JAR. Kiểm tra tên file trong `build/libs/` trước khi upload hoặc publish.

Nếu nhiều module cần dùng chung code, cấu trúc tốt hơn thường là tách phần domain hoặc library thành module riêng, rồi để ứng dụng CLI phụ thuộc module đó.

## 11. Layered JAR và tối ưu đóng gói cho container

Spring Boot có thể tạo layered executable JAR. Layer metadata phân chia nội dung như dependency ổn định, Spring Boot Loader, snapshot dependency và application code. Khi xây Docker image, các layer ít thay đổi có thể được cache độc lập; sửa một class ứng dụng không nhất thiết làm mất cache của toàn bộ dependency layer.

Layered JAR vẫn chạy được bằng `java -jar`; metadata layer phục vụ công cụ build image hoặc trích xuất layer. Nếu chỉ phân phối CLI cho người dùng chạy trực tiếp trên máy, không cần tùy chỉnh layer để JAR hoạt động.

Hãy ưu tiên cấu hình mặc định của Spring Boot trước. Chỉ tùy chỉnh thứ tự hoặc nội dung layer khi pipeline container có yêu cầu cụ thể và đã đo được lợi ích cache.

## 12. Chọn terminal provider phù hợp với môi trường đích

Spring Shell starter có thể đưa JLine provider phù hợp vào ứng dụng. Danh sách starter/provider thay đổi theo phiên bản: tài liệu Spring Shell 3.4.3 liệt kê Jansi, JNI và JNA; tài liệu Spring Shell 4.0 có thêm starter FFM. FFM dùng Foreign Function and Memory API của JDK, yêu cầu JDK 22 trở lên và native access. Hãy chọn provider theo phiên bản Spring Shell và môi trường đích thay vì thêm mọi provider vào cùng một ứng dụng.

Nếu dùng FFM, cần bật native access khi chạy:

~~~bash
java --enable-native-access=ALL-UNNAMED -jar build-cli.jar
~~~

Hoặc có thể cấu hình manifest attribute `Enable-Native-Access: ALL-UNNAMED` trong lúc build theo hướng dẫn Spring Shell. Chỉ thêm tùy chọn này khi ứng dụng thực sự dùng provider yêu cầu native access; không áp dụng một cách máy móc cho mọi executable JAR.

Khi phân phối trên Windows, Linux và macOS, kiểm thử trên từng hệ điều hành mục tiêu. Đặc biệt kiểm tra terminal tích hợp IDE, SSH, tmux/screen và môi trường không có TTY nếu CLI hỗ trợ các trường hợp đó.

## 13. Kiểm tra artifact trước khi phân phối

Đừng chỉ xác nhận lệnh build kết thúc với exit code `0`. Hãy kiểm tra file JAR, nội dung, manifest và khả năng chạy từ môi trường sạch.

### Kiểm tra file được tạo

Maven:

~~~bash
ls -lh target/build-cli-1.0.0.jar
~~~

PowerShell:

~~~powershell
Get-Item .\target\build-cli-1.0.0.jar | Select-Object Name, Length
~~~

### Kiểm tra cấu trúc JAR

~~~bash
jar tf target/build-cli-1.0.0.jar
~~~

Trong output, tìm `BOOT-INF/classes/` và `BOOT-INF/lib/`. Nếu chỉ thấy class project và không có dependency lồng bên trong, có thể bạn đang xem plain JAR thay vì executable JAR.

### Kiểm tra manifest

Có thể trích `META-INF/MANIFEST.MF` bằng `unzip -p`:

~~~bash
unzip -p target/build-cli-1.0.0.jar META-INF/MANIFEST.MF
~~~

Xác nhận manifest có `Main-Class` thuộc Spring Boot Loader và `Start-Class` trỏ đến main class của ứng dụng. Tên launcher cụ thể phụ thuộc dòng Spring Boot; hãy đọc giá trị thực tế thay vì tự viết manifest theo một phiên bản cũ.

### Chạy từ JAR đã đóng gói

~~~bash
java -jar target/build-cli-1.0.0.jar help
java -jar target/build-cli-1.0.0.jar build info
~~~

Với artifact dùng Spring Shell 4.0.x, thêm `--spring.shell.interactive.enabled=false` trước command để smoke test chạy theo non-interactive mode.

Kiểm tra cả interactive mode nếu sản phẩm cung cấp REPL. Chạy thử từ một thư mục làm việc khác để phát hiện phụ thuộc nhầm vào file local của project hoặc working directory của IDE.

### Kiểm tra runtime và cấu hình ngoài

~~~bash
java -version
java -jar target/build-cli-1.0.0.jar \
  --spring.profiles.active=test \
  --app.export.default-format=csv \
  build info
~~~

Đảm bảo Java runtime trên máy đích đáp ứng baseline của Spring Boot và terminal provider đã chọn. Kiểm tra file cấu hình ngoài có được nạp, profile có đúng và command có dùng đúng giá trị override.

## 14. Tích hợp build vào pipeline phát hành

Một pipeline tối thiểu nên thực hiện các bước:

1. Checkout source code và thiết lập JDK tương thích.
2. Khôi phục dependency từ Maven/Gradle repository.
3. Chạy unit test và integration test.
4. Chạy `clean package` với Maven hoặc `clean build`/`bootJar` với Gradle.
5. Kiểm tra executable JAR có trong thư mục output.
6. Chạy smoke test bằng `java -jar` trên artifact vừa tạo.
7. Tạo checksum và lưu artifact cùng version, commit hoặc build metadata.
8. Phát hành JAR cùng hướng dẫn Java runtime, cấu hình môi trường và lệnh chạy.

Không build xong rồi upload nhầm plain JAR. Hãy chọn artifact theo tên/classifier cụ thể và xác nhận bằng `jar tf` hoặc smoke test trước khi publish.

## 15. Các lỗi đóng gói thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `no main manifest attribute` | JAR chưa được Spring Boot `repackage` hoặc đang chạy plain JAR | Kiểm tra plugin, task và artifact được chọn. |
| `Could not find or load main class` | Main class cấu hình sai hoặc manifest không đúng | Cấu hình `start-class`/`mainClass`, kiểm tra `Start-Class`. |
| `ClassNotFoundException` khi chạy JAR | Dependency bị để sai scope hoặc bị loại khỏi archive | Kiểm tra dependency runtime và nội dung `BOOT-INF/lib`. |
| Chạy trong IDE được nhưng JAR lỗi | IDE dùng classpath khác với artifact đã đóng gói | Chạy smoke test trực tiếp bằng `java -jar`. |
| Command không xuất hiện | Command bean không được scan hoặc cấu hình đăng ký không được nạp | Kiểm tra package, profile và Spring context. |
| JAR chạy vào REPL trong khi script cần một command | Interaction mode không đúng với phiên bản Spring Shell | Cấu hình `spring.shell.interactive.enabled` theo major version. |
| Không đọc được file cấu hình ngoài | Dùng `spring.config.location` thay cho `additional-location`, hoặc chạy từ thư mục khác | Kiểm tra working directory và config search locations. |
| Lỗi native access của JLine | Chọn FFM provider nhưng JDK hoặc JVM option không đáp ứng | Dùng provider phù hợp hoặc bật native access với JDK yêu cầu. |
| Project khác không dùng được class trong executable JAR | Đang dùng executable archive làm library dependency | Phát hành JAR thường riêng hoặc tách module library. |

## 16. Checklist tạo executable JAR

- [ ] Spring Boot và Spring Shell thuộc cặp phiên bản tương thích.
- [ ] JDK build và runtime đáp ứng yêu cầu của Boot và terminal provider.
- [ ] Main class khởi tạo bằng `SpringApplication.run(...)`.
- [ ] Command và service nằm trong phạm vi component scan.
- [ ] Dependency BOM của Spring Shell được quản lý nhất quán.
- [ ] Maven `spring-boot-maven-plugin` hoặc Gradle `bootJar` được cấu hình.
- [ ] Artifact được tạo là executable JAR, không phải plain JAR.
- [ ] Manifest có launcher và Start-Class phù hợp.
- [ ] Có thể chạy `java -jar ... help` và command nghiệp vụ.
- [ ] Interactive/non-interactive mode được cấu hình theo đúng dòng Spring Shell.
- [ ] Cấu hình theo môi trường được đưa ra ngoài JAR khi cần.
- [ ] Không đóng gói secret hoặc thông tin riêng của máy đích.
- [ ] Đã smoke test artifact trên JRE sạch và hệ điều hành mục tiêu.
- [ ] Pipeline phát hành chọn đúng file JAR và lưu checksum/version.

## Kết luận

Để phân phối Spring Shell bằng executable JAR, hãy căn chỉnh phiên bản Spring Boot và Spring Shell trước, sau đó dùng Spring Boot Maven Plugin với goal `repackage` hoặc Gradle task `bootJar`. Plugin đóng gói class, resource, dependency và manifest để JAR có thể chạy bằng `java -jar`. Hãy cấu hình main class rõ ràng khi cần, phân biệt interactive và non-interactive mode theo major version của Spring Shell, đưa cấu hình riêng của môi trường ra ngoài JAR và kiểm tra artifact trực tiếp trước khi phát hành.

## Tài liệu tham khảo

- [Spring Shell – Spring Boot Compatibility](https://github.com/spring-projects/spring-shell/wiki/Spring-Boot-compatibility)
- [Spring Shell 4.0.4 – Building](https://docs.spring.io/spring-shell/reference/building.html)
- [Spring Shell 4.0.4 – Execution](https://docs.spring.io/spring-shell/reference/execution.html)
- [Spring Shell 4.0 – Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)
- [Spring Shell 3.4 – Getting Started](https://docs.spring.io/spring-shell/reference/3.4/getting-started.html)
- [Spring Boot 3.4 – System Requirements](https://docs.spring.io/spring-boot/3.4/system-requirements.html)
- [Spring Boot 4.0 – System Requirements](https://docs.spring.io/spring-boot/4.0/system-requirements.html)
- [Spring Boot 4.0 – Packaging Executable Archives](https://docs.spring.io/spring-boot/4.0/maven-plugin/packaging.html)
- [Spring Boot 4.0 – Using the Maven Plugin](https://docs.spring.io/spring-boot/4.0/maven-plugin/using.html)
- [Spring Boot 4.2 – Gradle Packaging](https://docs.spring.io/spring-boot/gradle-plugin/packaging.html)
- [Spring Boot 3.4 – Externalized Configuration](https://docs.spring.io/spring-boot/3.4/reference/features/external-config.html)
- [Spring Shell 3.4.3 – Building](https://docs.spring.io/spring-shell/reference/3.4/building.html)
- [Spring Shell 3.4.3 – Execution](https://docs.spring.io/spring-shell/reference/3.4/execution.html)
- [Spring Boot 3.4 – Packaging Executable Archives](https://docs.spring.io/spring-boot/3.4/maven-plugin/packaging.html)
- [Spring Boot 3.4 – Using the Maven Plugin](https://docs.spring.io/spring-boot/3.4/maven-plugin/using.html)
- [Spring Boot 3.4 – Gradle Packaging](https://docs.spring.io/spring-boot/3.4/gradle-plugin/packaging.html)
