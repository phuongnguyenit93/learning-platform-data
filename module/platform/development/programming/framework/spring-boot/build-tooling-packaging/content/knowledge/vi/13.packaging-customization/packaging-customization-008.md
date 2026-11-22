# Tạo fully executable archive bằng launch script trên hệ điều hành phù hợp

## 1. Mục đích và điểm cần phân biệt

Một ứng dụng Spring Boot được Maven hoặc Gradle đóng gói theo dạng executable JAR có thể chạy bằng:

~~~bash
java -jar my-app.jar
~~~

Tuy nhiên, một số máy chủ Linux và quy trình triển khai SysV init.d muốn có thể gọi một file như chương trình thực thi:

~~~bash
./my-app.jar
~~~

Spring Boot cung cấp **fully executable archive** cho trường hợp này. Khi được bật trong Maven hoặc Gradle, build plugin **chèn một shell launch script ở đầu JAR/WAR**. Trên hệ Unix phù hợp, hệ điều hành đọc **shebang**, chạy script và script khởi động JVM với ứng dụng đã đóng gói. Kỹ thuật này cũng giúp tích hợp một số service script dạng init.d hỗ trợ các lệnh **start, stop, restart, status**.

**Fully executable JAR không phải Native Image hay file .exe độc lập.** Bên dưới tiền tố script vẫn là Java archive với **BOOT-INF/classes**, **BOOT-INF/lib** và Spring Boot Loader. Nó vẫn cần Java runtime đúng phiên bản. Không nên mặc định dùng loại JAR này cho Windows, mọi Unix-like OS, systemd, Docker hoặc công cụ ZIP thông thường.

Mục tiêu bài học:

- Hiểu điều kiện để **./app.jar** chạy được, khác gì **java -jar app.jar**.
- Tạo fully executable artifact bằng **spring-boot-maven-plugin** và **Spring Boot Gradle Plugin**.
- Chạy thử một ví dụ Java 17 có endpoint HTTP, kiểm tra nội dung đã build.
- Phân biệt **mode=auto**, **MODE=run**, **MODE=service**, **init.d**, **systemd**.
- Tùy chỉnh embedded script khi build và cấu hình Java/process khi chạy.
- Nhận biết giới hạn với **Windows**, **macOS**, **FreeBSD**, **ZIP64**, **jar -xf** và container images.
- Xử lý quyền thực thi, JDK, user, PID, log và bảo mật khi triển khai.

## 2. Executable JAR và fully executable JAR không giống nhau

| Loại | Có Spring Boot Loader? | Có shell script prefix? | Cách chạy chính |
| --- | --- | --- | --- |
| Plain JAR | Không nhất thiết | Không | Classpath ngoài, hoặc java -jar nếu manifest phù hợp |
| Spring Boot executable JAR | Có | Không | **java -jar app.jar** |
| Spring Boot fully executable JAR | Có | **Có** | **./app.jar** trên Unix phù hợp sau khi có quyền execute |

Một Boot executable JAR thông thường có cấu trúc:

~~~text
app.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/com/example/app/...
    ├── classes/application.properties
    └── lib/
        ├── spring-boot-....jar
        ├── spring-context-....jar
        └── ...
~~~

Với fully executable archive, **toàn bộ phần trên vẫn tồn tại**, nhưng được đặt sau một đoạn **shell script** ở đầu file:

~~~text
app.jar (fully executable)
+--------------------------------------+
| #!/bin/...                           |
| Shell launch script của Spring Boot  |
+--------------------------------------+
| Dữ liệu JAR/ZIP                       |
| META-INF/MANIFEST.MF                 |
| BOOT-INF/classes/...                 |
| BOOT-INF/lib/*.jar                   |
| Spring Boot Loader classes           |
+--------------------------------------+
~~~

Khi người dùng gọi **./app.jar**, hệ điều hành thực thi đoạn shell theo shebang; script chọn Java, nhận các tùy chỉnh runtime và khởi động ứng dụng. Sau đó **Spring Boot Loader** mới giải quyết việc nạp classes từ JAR lồng bên trong archive.

### 2.1. Launch script khác Boot Loader

**Launch script** chạy ở tầng hệ điều hành, trước JVM. Nó có thể xử lý JAVA_HOME, JAVA_OPTS, process mode hoặc init.d controls.

**Boot Loader** là mã Java trong archive, chạy bên trong JVM và hiểu định dạng nested JAR của Spring Boot. Nó tìm class ở **BOOT-INF/classes** và thư viện trong **BOOT-INF/lib**. **Application main()** sau đó gọi SpringApplication.run và khởi tạo Spring context.

~~~text
./app.jar
   |
   v
OS + embedded shell script
   |
   v
Java process / JVM
   |
   v
Boot Loader + classloader
   |
   v
Application.main(args)
   |
   v
SpringApplication.run(...) -> server/job
~~~

Không được suy luận rằng script tự tạo được Java classpath cho mọi thư viện một cách độc lập với Boot Loader. Cũng không được suy luận việc bật shell prefix có thể thay thế một JDK đã thiếu hoặc quá cũ.

### 2.2. Vì sao phải bật riêng tính năng?

Phần script thêm các byte **trước nội dung ZIP**. Một số công cụ archive không chấp nhận JAR có tiền tố này. Spring Boot cảnh báo **jar -xf** có thể âm thầm không trích xuất được một archive đã được làm fully executable. Vì vậy **executable** mặc định là **false** trong Maven Plugin; còn Gradle cần chủ động gọi **launchScript()**.

**Quy tắc chọn:** chỉ bật khi thực sự muốn **thực thi trực tiếp** một JAR/WAR qua launch script trên hệ điều hành phù hợp. Nếu mục đích là chạy **java -jar**, triển khai vào servlet container hoặc tạo OCI image, dùng standard executable Spring Boot JAR thường ít tương thích rủi ro hơn.

## 3. Hệ điều hành và phương án triển khai nào phù hợp?

| Nền tảng | Phương án hợp lý | Lưu ý |
| --- | --- | --- |
| Linux chạy trực tiếp trong shell | Fully executable JAR + chmod + MODE=run | Yêu cầu shell, Java và filesystem cho phép execute |
| Linux SysV init.d | Fully executable JAR + init.d symlink | Use case Spring Boot hướng dẫn, phải bảo vệ user/PID/log |
| Linux systemd | Standard Boot JAR + systemd unit gọi java -jar | Thường không cần nhúng launch script |
| Docker/Kubernetes | Standard Boot JAR + JVM entrypoint | Tránh làm phức tạp archive reader/image tooling |
| Windows CMD/PowerShell | Standard JAR + java -jar hoặc WinSW service | Launch script kiểu Unix không phải .exe |
| macOS, FreeBSD | Standard JAR hoặc custom launch script đã test | Script mặc định không được bảo đảm trên các OS này |
| WAR deploy vào servlet container | WAR hợp lệ cho container | Không tự prepend shell script nếu container/tooling không hỗ trợ |

Theo hướng dẫn Spring Boot 3.5, **default embedded launch script** hỗ trợ nhiều Linux distributions và đã được thử nghiệm trên Ubuntu/CentOS. Các nền tảng như macOS và FreeBSD cần **custom script** khi muốn dùng cùng kỹ thuật direct execution. Đây là giới hạn của **script/OS tools**, không có nghĩa Spring Boot Java application nói chung không chạy trên macOS.

### 3.1. Fully executable không đồng nghĩa chạy mọi nơi

Windows không có cơ chế native dùng Unix shebang để trực tiếp chạy **./app.jar** trong CMD hoặc PowerShell. Một bản fully executable JAR được build trên Windows vẫn phải được mang sang môi trường phù hợp nếu muốn dùng prefix script.

Linux container có thể có filesystem **noexec**, shell tối giản không chứa interpreter của script, hoặc JRE không được cài. Nếu muốn dùng JAR trong image dạng distroless không có shell, **java -jar standard JAR** thường là lựa chọn thích hợp.

Một số ứng dụng chỉ cần **java -jar** dưới systemd; lúc này thêm launch script có thể không tạo thêm giá trị mà lại gây khó khăn cho công cụ kiểm tra ZIP.

## 4. Bài thực hành Spring Boot Java 17

Để chứng minh launch script thực sự khởi động ứng dụng, ta viết service HTTP nhỏ với endpoint **/launch-check**. Phần Java dùng chung cho cả Maven và Gradle; người học **chỉ chọn một** bộ cấu hình build.

Ví dụ sử dụng Spring Boot **3.5.16** và Java **17** để có phiên bản rõ ràng. Với dự án đang phát triển, cần chọn Spring Boot branch và JDK hiện được hỗ trợ theo chính sách tổ chức; không suy luận rằng các version minh họa là đề xuất nâng cấp cho mọi project.

### 4.1. Cấu trúc tệp

~~~text
launch-demo/
├── pom.xml                       (nếu chọn Maven)
│   hoặc
├── build.gradle                  (nếu chọn Gradle)
├── settings.gradle               (nếu chọn Gradle)
├── mvnw, mvnw.cmd, .mvn/wrapper/...
│   hoặc
├── gradlew, gradlew.bat, gradle/wrapper/...
└── src/
    ├── main/
    │   ├── java/com/example/launchdemo/
    │   │   ├── LaunchDemoApplication.java
    │   │   └── LaunchController.java
    │   └── resources/application.properties
    └── test/java/com/example/launchdemo/
        └── LaunchControllerTests.java
~~~

Maven Wrapper và Gradle Wrapper phải được tạo bằng Spring Initializr hoặc các công cụ Wrapper tương ứng; việc chỉ tạo POM/build script không tự tạo script **mvnw** hoặc **gradlew**.

### 4.2. Main class

Tệp **src/main/java/com/example/launchdemo/LaunchDemoApplication.java**:

~~~java
package com.example.launchdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LaunchDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(LaunchDemoApplication.class, args);
    }
}
~~~

### 4.3. Controller

Tệp **src/main/java/com/example/launchdemo/LaunchController.java**:

~~~java
package com.example.launchdemo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class LaunchController {
    @GetMapping("/launch-check")
    public String launchCheck() {
        return "fully-executable-ok";
    }
}
~~~

### 4.4. application.properties

Tệp **src/main/resources/application.properties**:

~~~properties
spring.application.name=launch-demo
server.port=8080
~~~

Nếu cổng 8080 bận, có thể truyền đối số Spring **--server.port=9090** để ghi đè cổng ở runtime; khi đó cũng đổi URL kiểm tra.

### 4.5. Unit/integration-style HTTP test

Tệp **src/test/java/com/example/launchdemo/LaunchControllerTests.java**:

~~~java
package com.example.launchdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LaunchControllerTests {
    @Autowired
    private MockMvc mvc;

    @Test
    void endpointReturnsExpectedText() throws Exception {
        mvc.perform(get("/launch-check"))
                .andExpect(status().isOk())
                .andExpect(content().string("fully-executable-ok"));
    }
}
~~~

Test bảo đảm Spring endpoint hoạt động trong test classpath. Nó **chưa chứng minh** shell script chạy trên Linux, vì các test được Maven/Gradle khởi động theo classpath của build system. Phải chạy artifact với **./file.jar** để kiểm tra khả năng direct execution.

## 5. Maven: bật tiền tố launch script bằng executable=true

### 5.1. pom.xml đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>launch-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
                <configuration>
                    <executable>true</executable>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Phần quyết định là:

~~~xml
<executable>true</executable>
~~~

**Spring Boot Maven Plugin** thực hiện goal **repackage** để tạo Boot executable archive rồi prepend embedded launch script khi executable được bật. Khi project kế thừa **spring-boot-starter-parent**, execution **repackage** đã được cấu hình sẵn; với cấu hình này chỉ cần khai báo plugin.

Nếu dự án không kế thừa starter parent, phải khai báo phiên bản plugin và bind repackage execution phù hợp. **executable=true** đặt trong plugin không được gọi **không tự tạo** fully executable artifact.

### 5.2. Thực hiện build

Trên Linux/macOS, tại project root:

~~~bash
./mvnw --version
./mvnw clean verify
~~~

**verify** bao gồm package trong Maven default lifecycle nên, với POM trên và test PASS, output dự kiến là:

~~~text
target/launch-demo-1.0.0.jar
~~~

Đây là Maven artifact đã được repackage. **mvnw.cmd** dùng trên Windows để build; nhưng khả năng chạy trực tiếp bằng shell prefix phải kiểm tra trên Unix OS thích hợp. Không mặc định lệnh Maven build thành công đồng nghĩa Linux host đã có Java/chmod đúng.

### 5.3. Đọc config Maven hiệu lực

Nếu artifact không có shell prefix dù POM đã chỉnh:

~~~bash
./mvnw help:effective-pom
./mvnw help:describe -Dplugin=org.springframework.boot:spring-boot-maven-plugin -Dgoal=repackage -Ddetail=true
~~~

Trong effective POM, tìm plugin **spring-boot-maven-plugin**, configuration **executable**, goal **repackage** cùng những profile đang kích hoạt. Plugin và execution khác nhau: phần **pluginManagement** chỉ quản lý defaults, không bảo đảm goal đã được kích hoạt.

**Không nên gọi spring-boot:repackage độc lập** nếu source JAR chưa được package; plugin repackage làm việc trên archive đã được tạo.

## 6. Gradle: gọi bootJar.launchScript()

### 6.1. settings.gradle

~~~groovy
rootProject.name = 'launch-demo'
~~~

### 6.2. build.gradle Groovy DSL đầy đủ

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}

tasks.named('bootJar') {
    launchScript()
}
~~~

**launchScript()** yêu cầu Spring Boot Gradle Plugin prepend default launch script khi thực thi **bootJar**. Nó **không** tạo Windows EXE, không làm cho mọi Gradle JAR task đều có script, và không thay Spring Boot nested-JAR class loader.

Mẫu này dùng plugin **io.spring.dependency-management** để áp dụng managed dependency versions của Spring Boot. Khi project chọn native Gradle BOM support thay thế, phải cấu hình **platform(...)** và classpaths đúng; đừng bỏ version của tất cả thư viện mà không có cơ chế BOM.

### 6.3. Build bằng Gradle

Nếu project có Gradle Wrapper tương thích, ví dụ Gradle **8.14** trong dải phù hợp với Spring Boot 3.5:

~~~bash
./gradlew --version
./gradlew clean test bootJar
~~~

Tên artifact thường là:

~~~text
build/libs/launch-demo-1.0.0.jar
~~~

Nếu đổi project name/version hoặc **bootJar.archiveFileName**, đường dẫn sẽ khác. Kiểm tra đúng output của **bootJar** thay vì nhầm với plain JAR do **jar** task tạo.

### 6.4. Kotlin DSL tương đương

Với project đã dùng **build.gradle.kts**, đoạn riêng để bật script là:

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named<BootJar>("bootJar") {
    launchScript()
}
~~~

Đây chỉ là phần bổ sung trong build.gradle.kts, **không phải toàn bộ tệp build.gradle.kts**. Những khai báo plugins/dependencies/toolchain cần chuyển sang Kotlin DSL tương ứng. Không đặt đoạn Groovy **tasks.named('bootJar')** nguyên văn trong file Kotlin DSL.

## 7. Chạy trực tiếp trên Linux

Sau khi đã chuyển artifact từ CI/build machine sang Linux tương thích, xác định đúng file. Với ví dụ Maven:

~~~bash
ls -l target/launch-demo-1.0.0.jar
head -n 1 target/launch-demo-1.0.0.jar
chmod +x target/launch-demo-1.0.0.jar
~~~

Với Gradle, thay **target/** bằng **build/libs/**.

**head -n 1** phải thấy một dòng shebang bắt đầu bằng **#!** theo script được nhúng; tên interpreter cụ thể phụ thuộc phiên bản và custom script. **chmod +x** cấp quyền execute cho file trong filesystem. Nếu artifact đã đi qua công cụ lưu artifact hoặc Windows filesystem, bit execute có thể không còn như ban đầu, nên đừng bỏ bước kiểm tra.

### 7.1. Thử chạy foreground

Với Maven:

~~~bash
MODE=run ./target/launch-demo-1.0.0.jar
~~~

Với Gradle:

~~~bash
MODE=run ./build/libs/launch-demo-1.0.0.jar
~~~

**MODE=run** yêu cầu default embedded script khởi động tiến trình ở foreground, không suy đoán chế độ service theo vị trí symlink. Khi app đã startup thành công, mở terminal thứ hai:

~~~bash
curl http://localhost:8080/launch-check
~~~

**Response body chính xác** từ source code là:

~~~text
fully-executable-ok
~~~

Có thể truyền Spring argument, ví dụ:

~~~bash
MODE=run ./target/launch-demo-1.0.0.jar --server.port=9090
~~~

và kiểm tra **http://localhost:9090/launch-check**. Lệnh đổi port là cho Maven output; nếu chọn Gradle, thay đường dẫn tương ứng.

Nếu request thất bại, cần xem log startup, JDK, port và exception. Việc script có thể được thực thi **không đồng nghĩa** Spring ApplicationContext đã khởi tạo thành công.

### 7.2. MODE=auto, run và service

Theo Spring Boot default script:

| Chế độ | Ý nghĩa | Khi nào dùng |
| --- | --- | --- |
| **auto** | Script cố nhận biết đang chạy như init.d hay chạy trực tiếp | Default script khi không ép mode |
| **run** | Chạy ứng dụng ở foreground | Dev smoke test và process supervisor |
| **service** | Bật hành vi quản lý start/stop/status kiểu service script | Linux init.d phù hợp |

Một archive được gọi qua symlink bên trong thư mục **init.d** có thể được script tự nhận biết ở mode auto. Còn lệnh **./app.jar start** trong mode run **không nhất thiết** được diễn giải giống **service app start**. Đối số truyền cho Spring Boot và lệnh quản lý của script là hai ngữ cảnh khác nhau.

Để dừng thử nghiệm foreground, dùng Ctrl+C trong terminal đang chạy. Không mặc định dùng **kill -9** khi ứng dụng có thể thực hiện graceful shutdown.

### 7.3. Vì sao lệnh java -jar không phải cách chính ở đây?

Một số Java launchers có thể chấp nhận ZIP/JAR có shell prefix, nhưng Spring Boot khuyến nghị chỉ bật fully executable nếu mục tiêu là **chạy trực tiếp**, không phải dựa vào **java -jar** hoặc deploy vào servlet container. Tiền tố script làm tăng khác biệt giữa các công cụ ZIP/JDK. Để dùng java -jar làm phương thức chính, nên tạo một **standard Boot executable JAR không có script prefix**.

## 8. Tùy chỉnh embedded script tại build time

Default Spring Boot script hỗ trợ nhiều giá trị được expand khi đóng gói. Với Maven dùng **embeddedLaunchScriptProperties**; với Gradle dùng **launchScript { properties ... }**.

### 8.1. Maven XML minh họa

Trong POM có spring-boot-maven-plugin, **thay** phần plugin ở mục 5 bằng:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <executable>true</executable>
        <embeddedLaunchScriptProperties>
            <initInfoShortDescription>Launch Demo Service</initInfoShortDescription>
            <logFilename>launch-demo.log</logFilename>
            <stopWaitTime>45</stopWaitTime>
        </embeddedLaunchScriptProperties>
    </configuration>
</plugin>
~~~

Đoạn trên **không phải một POM độc lập**; nó phải ở **build/plugins**. Không thêm hai plugin definitions trùng cùng chức năng rồi dự đoán cả hai tạo artifact riêng. Khi starter parent được kế thừa, repackage execution vẫn dùng theo cách của parent.

**initInfoShortDescription** là mô tả init.d; **logFilename** và **stopWaitTime** là giá trị của default script. **logFilename** liên quan logging của script trong chế độ init.d, **không phải** property **logging.file.name** của Spring Boot runtime.

### 8.2. Gradle Groovy DSL minh họa

Trong **build.gradle**, thay khối bootJar hiện tại bằng:

~~~groovy
tasks.named('bootJar') {
    launchScript {
        properties 'initInfoShortDescription': 'Launch Demo Service',
                   'logFilename': 'launch-demo.log',
                   'stopWaitTime': '45'
    }
}
~~~

Đây là **một biến thể** của **launchScript()**, không cần gọi thêm một launchScript() thứ hai. Các properties được sử dụng khi task tạo shell prefix.

### 8.3. Gradle Kotlin DSL minh họa

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named<BootJar>("bootJar") {
    launchScript {
        properties(
            mapOf(
                "initInfoShortDescription" to "Launch Demo Service",
                "logFilename" to "launch-demo.log",
                "stopWaitTime" to "45"
            )
        )
    }
}
~~~

Đây là đoạn task configuration thay cho **tasks.named('bootJar') { launchScript() }** trong file Kotlin DSL tương ứng.

### 8.4. Build-time khác runtime

Những thuộc tính được plugin thay vào script **khi tạo artifact**. Nếu chỉnh **initInfoShortDescription** thì cần build lại để script mới xuất hiện trong file JAR. Những thay đổi môi trường như Java home, heap, Spring profile hoặc RUN_ARGS thường được cấp **khi process chạy** và không đòi hỏi rebuild artifact.

## 9. Cấu hình launch script lúc chạy

Default script có thể đọc một số biến môi trường hoặc file **.conf**.

| Biến | Tác dụng |
| --- | --- |
| **MODE** | Chọn auto/run/service |
| **JAVA_HOME** | Chỉ thư mục Java, nếu dùng thay PATH |
| **JAVA_OPTS** | JVM options như -Xmx512m |
| **RUN_ARGS** | Đối số truyền vào Spring Boot application |
| **RUN_AS_USER** | Chọn user chạy trong service mode |
| **PID_FOLDER** | Thư mục PID file trong init.d mode |
| **LOG_FOLDER** | Thư mục log trong init.d mode |
| **LOG_FILENAME** | Tên log file trong init.d mode |
| **STOP_WAIT_TIME** | Thời gian chờ khi dừng service, mặc định 60 giây |
| **APP_NAME** | Tên application script sử dụng |
| **CONF_FOLDER** | Nơi script tìm file .conf |
| **USE_START_STOP_DAEMON** | Tùy chọn dùng start-stop-daemon nếu có |

**PID_FOLDER, LOG_FOLDER, LOG_FILENAME** theo hướng dẫn Spring Boot chỉ dùng cho **init.d service**; khi dùng systemd phải cấu hình PID/log bằng **systemd unit/service manager**.

Ví dụ chạy foreground với JVM options và Spring profile:

~~~bash
JAVA_OPTS='-Xms128m -Xmx512m' MODE=run RUN_ARGS='--spring.profiles.active=dev' ./target/launch-demo-1.0.0.jar
~~~

- **JAVA_OPTS** cấu hình JVM, không tự đặt Spring profile.
- **RUN_ARGS** đi tới ứng dụng Spring Boot.
- **MODE** điều khiển script process mode.
- Các biến này không tạo ra JVM nếu máy thiếu Java; cần một JDK/JRE tương thích.

### 9.1. Cấu hình .conf

Với file JAR được triển khai tại:

~~~text
/opt/launch-demo/launch-demo.jar
~~~

script mặc định có thể tìm config ở cùng thư mục:

~~~text
/opt/launch-demo/launch-demo.conf
~~~

Ví dụ nội dung shell-style:

~~~bash
JAVA_OPTS=-Xmx512m
STOP_WAIT_TIME=45
~~~

**.conf** không phải **application.properties**, và không tự được Spring Environment nạp. Nó dành cho launch script. **JARFILE** và **APP_NAME** là hai ngoại lệ Spring Boot không hỗ trợ cấu hình theo cùng cách trong .conf; cần truyền qua cơ chế khác thích hợp nếu thực sự cần.

**Bảo mật cực kỳ quan trọng:** trong ngữ cảnh init.d được root điều khiển, .conf có thể được **source/evaluate bởi shell với quyền root**. Không cho user ứng dụng hoặc tài khoản không tin cậy ghi vào .conf. Spring Boot minh họa owner **root:root** và permission **400** khi dùng script theo cách này.

### 9.2. Vì sao không để secret trong script?

Không hardcode mật khẩu DB/API key vào **embedded script** hoặc build-time properties: file JAR có thể được trích xuất/đọc, có thể lưu trong artifact repository và log build. Cũng không đặt secrets trong JAVA_OPTS/RUN_ARGS một cách bừa bãi vì chúng có thể lộ qua process listings hoặc logs.

Dùng cơ chế phân phối secrets của tổ chức, quyền file hạn chế và cấu hình runtime phù hợp. Khi lưu cấu hình trong .conf, đánh giá rủi ro shell evaluation và cách cấp quyền của init.d.

## 10. Tích hợp init.d/SysV service trên Linux

**init.d** là use case chính mà Spring Boot mô tả cho fully executable archive. Các lệnh bên dưới là **ví dụ triển khai có đặc quyền quản trị**: chỉ dùng khi máy thực sự sử dụng SysV init hoặc có compatibility mechanism tương thích và bạn có quyền thay đổi service. Không chạy trực tiếp trên production khi chưa có change plan/rollback.

### 10.1. Đặt JAR vào thư mục của service

Giả sử system admin đã tạo user/group **launchdemo** và thư mục **/opt/launch-demo**, artifact đã được build/test:

~~~bash
sudo cp target/launch-demo-1.0.0.jar /opt/launch-demo/launch-demo.jar
sudo chown launchdemo:launchdemo /opt/launch-demo/launch-demo.jar
sudo chmod 500 /opt/launch-demo/launch-demo.jar
~~~

Nếu build bằng Gradle, copy từ **build/libs/** thay cho **target/**. Đoạn này **giả định directory và user đã tồn tại**, không phải script provisioning hoàn chỉnh.

**chmod 500** cấp read/execute cho owner, không cấp write; tài liệu Spring Boot dùng để minh họa bảo vệ artifact. Cần đánh giá quyền sở hữu thực tế, khả năng sửa file bởi tài khoản runtime và cơ chế triển khai không cho user ứng dụng thay nội dung artifact trái phép. Không chạy process dưới root.

### 10.2. Tạo liên kết init.d

~~~bash
sudo ln -s /opt/launch-demo/launch-demo.jar /etc/init.d/launch-demo
sudo service launch-demo start
sudo service launch-demo status
~~~

Default embedded script biết ngữ cảnh được gọi từ symlink bên trong **init.d** và có thể hỗ trợ **start/stop/restart/status**. Khi xong thử nghiệm hoặc cần dừng:

~~~bash
sudo service launch-demo stop
~~~

Trước khi tạo symlink, xác minh tên service chưa tồn tại và distro đang hỗ trợ hành vi này. Với Linux dùng systemd, **service** có thể chỉ là compatibility command và không phải cách quản lý mới được khuyên dùng.

Script init.d thường ghi PID và console logs vào đường dẫn được cấu hình, mặc định liên quan **/var/run** và **/var/log**. Các thư mục/permissions phải phù hợp. Nếu service startup thất bại, kiểm tra đường log và biến PID/LOG thay vì tự đoán ứng dụng đã khởi động vì lệnh shell không báo lỗi rõ.

### 10.3. Chạy dưới user nào?

Spring Boot default script khi được root gọi trong service mode cố chạy ứng dụng bằng user xác định từ **RUN_AS_USER**, hoặc user sở hữu JAR nếu không cấu hình. Không bao giờ để **RUN_AS_USER=root**, và không cấu hình artifact theo cách khiến Spring Boot application chạy với quyền root.

Tài liệu Spring Boot còn đề xuất tạo tài khoản không có login shell và bảo vệ file JAR/.conf phù hợp. Một process Java bị khai thác không nên có khả năng dễ dàng sửa artifact hoặc startup configuration rồi leo thang quyền trong lượt khởi động service tiếp theo.

### 10.4. Không bật tự khởi động vô điều kiện

Một số Debian/SysV systems dùng **update-rc.d** để bật startup at boot. Đây là thao tác quản trị riêng, chỉ thực hiện sau khi đã kiểm chứng start/stop, security, log rotation và rollback. Đừng tự coi fully executable archive vừa được build là service đã được đăng ký trên máy đích.

## 11. systemd: phần lớn trường hợp không cần fully executable archive

Với Linux dùng **systemd**, Spring Boot hướng dẫn tạo unit file gọi một **standard Boot executable JAR** bằng **java -jar**. systemd chịu trách nhiệm process lifecycle, restart và stdout/stderr logs; không cần dùng PID/log của init.d launch script.

Ví dụ unit tại **/etc/systemd/system/launch-demo.service**:

~~~ini
[Unit]
Description=Launch Demo Spring Boot
After=network.target

[Service]
Type=exec
User=launchdemo
Group=launchdemo
WorkingDirectory=/opt/launch-demo
ExecStart=/usr/bin/java -jar /opt/launch-demo/launch-demo.jar
SuccessExitStatus=143
Restart=on-failure

[Install]
WantedBy=multi-user.target
~~~

Đây là **unit mẫu** dành cho **standard executable Spring Boot JAR**. Đường **/usr/bin/java** phải phù hợp với máy thực, JDK phải đáp ứng requirements, user/group đã tồn tại và artifact có quyền đọc. Không tự đặt **RUN_AS_USER/PID_FOLDER/LOG_FOLDER** khi systemd đã quản lý những trách nhiệm đó.

Lệnh quản trị khi có quyền:

~~~bash
sudo systemctl daemon-reload
sudo systemctl start launch-demo.service
sudo systemctl status launch-demo.service
sudo journalctl -u launch-demo.service --no-pager -n 50
~~~

Cần một quyết định riêng nếu muốn **systemctl enable** tự động khởi động sau reboot.

### 11.1. Có thể gọi fully executable JAR từ systemd không?

Có thể nhưng cần lý do và phải test trên đúng distro/script. Ví dụ một phần unit dùng **MODE=run** để tránh script daemonize khi systemd cần theo dõi tiến trình foreground:

~~~ini
[Service]
Type=exec
User=launchdemo
Group=launchdemo
WorkingDirectory=/opt/launch-demo
Environment=MODE=run
ExecStart=/opt/launch-demo/launch-demo.jar
Restart=on-failure
~~~

Đây là **đoạn cấu hình thay thế**, không phải unit hoàn chỉnh; nó giả định fully executable JAR có shebang đúng và file executable. Với một dịch vụ systemd mới, standard JAR + **ExecStart=java -jar** thường đơn giản và tương thích với ZIP/JAR tooling hơn.

## 12. Windows, macOS, FreeBSD và containers

### 12.1. Windows

Một Unix shell shebang không biến JAR thành chương trình **.exe**. Windows CMD/PowerShell không sử dụng cùng cơ chế Linux để gọi trực tiếp **./app.jar**. Dùng standard Boot JAR và:

~~~powershell
java -jar .\launch-demo.jar
~~~

Khi cần Windows service, Spring Boot documentation đề xuất **WinSW** (Windows Service Wrapper) hoặc công cụ dịch vụ phù hợp. Không thay mục tiêu bằng cách bật **executable=true** rồi mong Windows Service Manager tự nhận được file JAR như service.

### 12.2. macOS và FreeBSD

Các OS này có shell nhưng không dùng đầy đủ các conventions/utilities mà default Spring Boot launch script được test trên Linux. Theo Spring Boot, muốn direct execution ở macOS/FreeBSD cần **custom launch script** phù hợp, hoặc chọn standard JAR chạy bằng **java -jar**. Chạy được trên terminal Linux không chứng minh tương thích mọi OS tương tự Unix.

### 12.3. Docker/OCI và Kubernetes

Container thường chạy foreground process để orchestrator theo dõi, restart, log và gửi signals. Một Dockerfile minh họa cho **standard Boot JAR**:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY app.jar app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Đây là ví dụ, cần pin image/JDK theo policy production. Trong nhiều pipeline, Spring Boot layered archive và OCI image build tooling thao tác ZIP/JAR; script prefix có thể gây lỗi đọc. Chỉ bật fully executable khi có nhu cầu đã được kiểm tra trên image/toolchain cụ thể; mặc định dùng standard Boot JAR.

## 13. ZIP tools và giới hạn ZIP64

### 13.1. Vì sao jar -xf có thể không trích xuất được?

Một fully executable archive có byte đầu tiên là script text, không phải chữ ký ZIP/JAR như tệp thông thường. Một số ZIP tools vẫn tìm được ZIP structures, nhưng **không phải công cụ nào cũng hỗ trợ**. Spring Boot nêu rõ **jar -xf** có thể âm thầm thất bại.

Vì vậy lệnh:

~~~bash
jar xf target/launch-demo-1.0.0.jar
~~~

**không nên dùng như bài kiểm tra duy nhất** của fully executable archive. Nó còn có thể ghi nhiều file vào current working directory. Khi cần inspect entries, dùng một công cụ hiểu loại archive này hoặc build thêm một **standard Boot JAR** để kiểm tra cấu trúc BOOT-INF/MANIFEST.

### 13.2. ZIP64 quan trọng ở tầng nào?

Theo đặc tả Spring Boot 3.5, **outer JAR có định dạng ZIP64 không thể làm fully executable**; thêm prefix có thể làm nó bị báo hỏng khi chạy. Tuy nhiên **standard-format outer JAR** vẫn có thể chứa một nested JAR bên trong dùng ZIP64.

Đừng nói chung chung “Spring Boot không hỗ trợ ZIP64” — đây là ràng buộc riêng của **fully executable outer archive**. Với ứng dụng quá lớn đến mức cần ZIP64 ở outer file, hãy chọn chiến lược đóng gói khác thay vì cố prepend shell script.

## 14. Thay default script bằng custom launch script khi thật sự cần

Spring Boot hỗ trợ file script do người dùng cung cấp khi default script không phù hợp. Trong Maven Plugin có option **embeddedLaunchScript**, và trong Gradle Plugin có **launchScript { script = file(...) }**.

Maven excerpt:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <executable>true</executable>
        <embeddedLaunchScript>src/launch/launch.sh</embeddedLaunchScript>
    </configuration>
</plugin>
~~~

Gradle excerpt:

~~~groovy
tasks.named('bootJar') {
    launchScript {
        script = file('src/launch/launch.sh')
    }
}
~~~

**Đây là cấu hình trỏ tới file script**, không phải script chạy được độc lập. File **src/launch/launch.sh** phải tồn tại, có shebang đúng và chứa logic khởi động được kiểm tra trên OS đích. Nếu script riêng cần hỗ trợ **start/stop/restart/status**, xử lý user, signals, PID, logs và error codes thì bạn phải tự thiết kế những behavior đó.

Không sao chép một dòng **exec java -jar "$0"** rồi mặc định nó đúng với mọi prefixed JAR và JDK. Tính tương thích của Java/ZIP reader với archive prefix không được bảo đảm như JAR chuẩn. Khi default script đáp ứng yêu cầu, dùng **embeddedLaunchScriptProperties** hoặc **launchScript.properties** ít rủi ro hơn viết lại toàn bộ launch logic.

## 15. Kiểm tra artifact sau build mà không phá archive

### 15.1. Xác nhận tiền tố shell và quyền file

Với Maven:

~~~bash
test -s target/launch-demo-1.0.0.jar
head -n 1 target/launch-demo-1.0.0.jar
ls -l target/launch-demo-1.0.0.jar
~~~

Với Gradle thay bằng **build/libs/launch-demo-1.0.0.jar**. Các dấu hiệu:
- **test -s**: file tồn tại và không rỗng.
- **head -n 1**: dòng đầu bắt đầu **#!** nếu launch script đúng.
- **ls -l**: quyền file trên filesystem hiện tại. Nếu chưa có quyền execute, dùng **chmod +x** ở môi trường được phép.

Có thể dùng **file** để nhận dạng loại file, nhưng output thay đổi theo bản magic database; đừng xem một chuỗi output cụ thể là chuẩn bắt buộc.

### 15.2. Chạy thử chức năng thực

~~~bash
MODE=run ./target/launch-demo-1.0.0.jar --server.port=9090
~~~

Ở terminal khác:

~~~bash
curl --fail http://localhost:9090/launch-check
~~~

Kết quả body chính xác:

~~~text
fully-executable-ok
~~~

Lệnh dùng Maven output; với Gradle thay đường dẫn JAR. **curl --fail** cho tín hiệu lỗi khi HTTP response code >=400, nhưng vẫn cần đọc body/log và xác minh điều kiện môi trường.

### 15.3. Kiểm tra checksum của file triển khai

~~~bash
sha256sum target/launch-demo-1.0.0.jar
~~~

Checksum giúp chứng minh file sau khi chuyển từ CI sang server **không đổi byte**. Nó không chứng minh script/JDK/OS tương thích hay endpoint hoạt động. Trên Windows có thể dùng **Get-FileHash**, macOS có thể dùng **shasum -a 256**.

## 16. Bảng chẩn đoán những lỗi thường gặp

| Dấu hiệu | Nguyên nhân thường gặp | Cách kiểm tra/khắc phục |
| --- | --- | --- |
| **Permission denied** khi ./app.jar | Thiếu executable bit, mount noexec hoặc owner sai | ls -l, chmod +x hợp lệ, kiểm tra mount |
| **Exec format error** | File không có shebang hoặc script header hỏng | head -n 1, kiểm tra Maven/Gradle packaging |
| **bad interpreter** | Dòng shebang trỏ tới shell không có hoặc line endings CRLF | Kiểm tra interpreter trên OS đích |
| Dòng đầu JAR là **PK** | Chưa prepend launch script hoặc kiểm tra nhầm JAR | Xem executable=true / bootJar.launchScript |
| **java: command not found** | JAVA_HOME/PATH của runtime user không đúng | java -version, environment của user/service |
| **UnsupportedClassVersionError** | Java runtime quá cũ | Chọn JVM tương thích class file/Spring Boot |
| **Port already in use** | Spring server không bind được port | Đổi server.port hoặc dừng process khác |
| **./app.jar start** không như mong đợi | MODE đang là run/auto, không phải service | Xem MODE và symlink init.d |
| Không ghi được PID/log | Quyền/thư mục mặc định không phù hợp | PID_FOLDER, LOG_FOLDER, user/group |
| **service app start** không hoạt động | Distro dùng systemd hoặc init.d script chưa cấu hình đúng | Dùng systemd unit phù hợp, đọc logs |
| **jar -xf** không thấy nội dung | ZIP tool không chấp nhận shell prefix | Dùng reader phù hợp hoặc standard JAR |
| Scanner/OCI builder báo JAR lỗi | Không nhận định dạng script + archive | Phát hành standard Boot JAR |
| ZIP64 outer JAR hỏng | Fully executable outer ZIP64 không hỗ trợ | Đổi chiến lược đóng gói |
| Windows không chạy **./app.jar** | Không hỗ trợ Unix shebang theo cách này | Dùng java -jar và Windows service wrapper |
| macOS/FreeBSD lỗi khi chạy script | Default script chỉ được kiểm tra trên Linux cụ thể | Dùng custom script hoặc standard JAR |
| Ứng dụng khởi động rồi lỗi bean/database | Script/JVM chạy được, lỗi ở Spring runtime | Đọc exception/stack trace/config |

**Phân tầng lỗi:** OS có gọi được script không → script có tìm Java không → Java có mở archive không → Spring context có khởi động không → endpoint/job có hoạt động không. Xác định đúng tầng trước khi chỉnh code build hoặc OS.

## 17. Bài tập so sánh hai cách đóng gói

Tạo hai biến thể cùng source Java:

**Biến thể A — standard Boot executable JAR:**
- Maven bỏ **executable=true** để quay về default false.
- Gradle không gọi **launchScript()**.
- Chạy **java -jar** trong môi trường có Java phù hợp.
- Dùng cho systemd thông thường, Windows hoặc OCI image.

**Biến thể B — fully executable Boot JAR:**
- Maven có **<executable>true</executable>**.
- Gradle có **tasks.named('bootJar') { launchScript() }**.
- Trên Linux, kiểm tra shebang, chmod +x, chạy **MODE=run ./app.jar**.
- Khi có init.d, thử service commands với quyền/user phù hợp.

| Quan sát | A | B |
| --- | --- | --- |
| Shebang ở đầu file | Không | Có |
| BOOT-INF/classes và BOOT-INF/lib | Có | Có |
| Phương thức chạy được thiết kế | java -jar | Trực tiếp trên Unix phù hợp |
| Tương thích jar -xf như standard ZIP | Thông thường | Không bảo đảm |
| Cần Java runtime | Có | Có |

Cả hai biến thể được thiết kế để cùng endpoint trả **fully-executable-ok**, nhưng cách khởi động khác nhau. **Đừng tạo hai bản rồi để chúng ghi đè nhau cùng filename** trong artifact repository; dùng tên/classifier khác và kiểm tra từng bản.

## 18. Tự kiểm tra kiến thức

**Câu 1.** Fully executable có phải native binary không?

**Đáp án:** Không. Đó là Spring Boot executable archive có thêm shell script prefix. JVM vẫn thực thi bytecode bên trong.

**Câu 2.** Dùng tùy chọn nào trong Maven và Gradle?

**Đáp án:** Maven dùng **spring-boot-maven-plugin** với **<executable>true</executable>**; Gradle dùng **bootJar.launchScript()**.

**Câu 3.** Vì sao chmod +x có thể cần thiết sau khi build?

**Đáp án:** File phải có executable bit trên Unix filesystem; quyền ấy có thể mất khi lưu/chuyển qua artifact store hoặc filesystem khác.

**Câu 4.** Vì sao dùng fully executable JAR có thể làm jar -xf thất bại?

**Đáp án:** Vì archive có shell script trước dữ liệu ZIP, và một số JAR/ZIP tools không xử lý loại preamble đó.

**Câu 5.** Có cần fully executable JAR để dùng systemd không?

**Đáp án:** Không. Standard Boot JAR và unit ExecStart=java -jar là phương án được Spring Boot hỗ trợ và thường đơn giản hơn.

**Câu 6.** Trên Windows có dùng ./app.jar thay java -jar được không?

**Đáp án:** Không theo cơ chế default Unix launch script; dùng standard JAR với java -jar hoặc service wrapper như WinSW.

**Câu 7.** mode=run, service và auto có khác nhau không?

**Đáp án:** Có. Run chạy foreground, service phục vụ mô hình quản lý start/stop/status; auto cố nhận biết ngữ cảnh. Đừng dùng lệnh start của service mode rồi mặc định run mode cũng xử lý tương đương.

**Câu 8.** Có thể nhúng mật khẩu vào embeddedLaunchScriptProperties không?

**Đáp án:** Không nên. Build artifact có thể được đọc/copy. Với init.d, file .conf còn có thể được shell đọc bằng quyền cao; bảo vệ secrets theo chính sách runtime.

**Câu 9.** Outer ZIP64 JAR có phù hợp fully executable không?

**Đáp án:** Theo Spring Boot 3.5, không. Outer JAR standard ZIP chứa nested JAR ZIP64 lại là trường hợp khác có thể được hỗ trợ.

## 19. Checklist trước khi triển khai

- [ ] Đã xác định OS và process manager thực tế: Linux direct, init.d, systemd, Windows hay container.
- [ ] Chỉ bật fully executable khi có nhu cầu **./artifact.jar** trên môi trường hỗ trợ.
- [ ] Maven đúng plugin/goal **repackage** và **executable=true**; Gradle đúng task **bootJar** với **launchScript()**.
- [ ] Java runtime đáp ứng Spring Boot và compiler target.
- [ ] Artifact có shebang, file tồn tại, không rỗng và quyền execute phù hợp.
- [ ] Có smoke test trực tiếp **MODE=run ./app.jar**, không chỉ unit test qua Maven/Gradle.
- [ ] Với init.d: kiểm tra user, symlink, PID/log, start/stop/status và file .conf bảo mật.
- [ ] Với systemd: xem xét standard Boot JAR + **ExecStart=java -jar**.
- [ ] Với Windows/macOS/FreeBSD: không mặc định script Linux chạy được.
- [ ] Với OCI image/ZIP tools: tránh shell prefix nếu công cụ cần archive chuẩn.
- [ ] Không dùng fully executable outer ZIP64 JAR.
- [ ] Có kiểm tra checksum/artifact identity sau transfer.
- [ ] Không để runtime user/root có quyền sửa file khởi động trái chính sách.
- [ ] Release gate vẫn chạy tests và QA của ứng dụng; việc shell khởi động không thay verification.

**Kết luận:** Spring Boot fully executable archive dùng **embedded launch script ở đầu file JAR** để hỗ trợ gọi trực tiếp trên hệ Unix phù hợp và phục vụ một số mô hình **init.d**. Điều này hữu ích cho đúng môi trường đích, nhưng không phải lựa chọn tốt nhất cho mọi platform. Nếu triển khai Windows, systemd thông thường, container hoặc toolchain cần JAR/ZIP chuẩn, hãy cân nhắc **standard Spring Boot JAR chạy bằng java -jar**. Quan trọng nhất là xác minh script, quyền, Java runtime và hành vi ứng dụng trên chính hệ điều hành sẽ triển khai.

## 20. Tài liệu chính thức

- Spring Boot 3.5 — Installing Spring Boot Applications, systemd/init.d/launch scripts: https://docs.spring.io/spring-boot/3.5/how-to/deployment/installing.html
- Spring Boot 3.5 — Maven Plugin, Packaging Executable Archives: https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html
- Spring Boot 3.5 — Gradle Plugin, Packaging Executable Archives: https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging.html
- Spring Boot 3.5 — Executable JAR Format: https://docs.spring.io/spring-boot/3.5/specification/executable-jar/index.html
- Spring Boot 3.5 — Gradle Plugin Getting Started: https://docs.spring.io/spring-boot/3.5/gradle-plugin/getting-started.html
- Spring Boot 3.5 — Maven Plugin Using: https://docs.spring.io/spring-boot/3.5/maven-plugin/using.html
- systemd.service — Configuration reference: https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html
- Linux chmod manual: https://man7.org/linux/man-pages/man1/chmod.1.html
