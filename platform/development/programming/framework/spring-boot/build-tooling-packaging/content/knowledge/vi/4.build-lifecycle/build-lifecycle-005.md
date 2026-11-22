# Vị trí của repackage, bootJar và bootWar trong bản dựng Spring Boot

## 1. Bài học giải quyết vấn đề gì?

Trong một dự án Spring Boot, thao tác đóng gói ứng dụng có tên khác nhau tùy build tool:

- **Maven:** goal `spring-boot:repackage` của Spring Boot Maven Plugin đóng gói lại JAR/WAR đã được tạo trong lifecycle.
- **Gradle:** task `bootJar` tạo executable JAR, task `bootWar` tạo executable WAR.
- **Maven `package`, Gradle `assemble` và Gradle `build`:** là các điểm vào của quá trình build, không đồng nghĩa trực tiếp với ba thao tác Spring Boot trên.

Bài học giúp trả lời được: thao tác chạy ở bước nào; cần cấu hình/plugin nào; archive được tạo từ đâu; `package`/`build` có chạy kiểm thử hay không; khi nào sinh plain archive và executable archive cùng lúc; và cách xác minh kết quả mà không suy đoán từ tên file.

Sau bài học, bạn có thể đọc log Maven/Gradle, chỉ ra nơi `repackage` hoặc `bootJar`/`bootWar` thực sự chạy, chọn đúng artifact để triển khai và tránh áp dụng executable packaging cho module thư viện.

## 2. Ba thao tác khác nhau như thế nào?

| Khía cạnh | Maven `repackage` | Gradle `bootJar` | Gradle `bootWar` |
| --- | --- | --- | --- |
| Chủ sở hữu | Spring Boot Maven Plugin | Spring Boot Gradle Plugin | Spring Boot Gradle Plugin |
| Loại thao tác | Maven goal | Gradle task loại `BootJar` | Gradle task loại `BootWar` |
| Đầu vào | JAR/WAR cơ sở đã được tạo trong `package` | Application classes/resources + runtime dependencies | Classes/resources + dependencies và cấu hình WAR |
| Đầu ra | Executable JAR hoặc WAR | Executable JAR | Executable WAR |
| Mốc lifecycle mặc định | Goal gắn vào Maven phase `package` khi có execution hợp lệ | Nối vào Gradle `assemble` khi có Java plugin | Nối vào Gradle `assemble` khi có War plugin |
| Cách gọi điển hình | `./mvnw package` | `./gradlew bootJar` hoặc `./gradlew build` | `./gradlew bootWar` hoặc `./gradlew build` |

**Điểm quan trọng:** không tồn tại chuỗi mặc định `repackage → bootJar → bootWar`. Chúng giải quyết các tình huống tương ứng của **hai hệ build**. Một dự án dùng Maven không cần chạy task Gradle để hoàn thành `repackage`, và một dự án dùng Gradle không cần Maven goal để hoàn thành `bootJar`.

Executable Boot JAR/WAR thường có thư viện runtime được đóng vào archive và metadata cần thiết để Spring Boot loader khởi chạy ứng dụng:

~~~bash
java -jar path/to/app.jar
# hoặc
java -jar path/to/app.war
~~~

Tuy nhiên, đuôi `.jar`/`.war` **không tự chứng minh** file có thể chạy bằng `java -jar`.

## 3. Vòng đời Maven: `repackage` nằm tại phase `package`

### 3.1. Vị trí trong Maven lifecycle

Maven định nghĩa một vòng đời mặc định với các phase có thứ tự. Chuỗi rút gọn:

~~~text
validate
   ↓
compile
   ↓
test
   ↓
package             ← tạo JAR/WAR và có thể chạy repackage
   ↓
verify
   ↓
install
   ↓
deploy
~~~

Đây chỉ là hình minh họa: Maven còn có `process-resources`, `test-compile`, `integration-test` và các phase trung gian khác. Khi gọi `./mvnw package`, Maven thực thi các phase cần thiết đến và bao gồm `package`. Khi gọi `./mvnw verify` hoặc `./mvnw install`, Maven đi qua `package` trên đường tới phase được yêu cầu.

Theo packaging của project, phase `package` có các goal tiêu chuẩn:

- `<packaging>jar</packaging>`: thường chạy goal `maven-jar-plugin:jar`, tạo regular JAR.
- `<packaging>war</packaging>`: thường chạy goal `maven-war-plugin:war`, tạo regular WAR.
- `<packaging>pom</packaging>`: thường áp dụng cho root aggregator/parent; không mặc nhiên có application archive để repackage.

Goal `spring-boot:repackage` chạy **sau khi có archive cơ sở** để chuyển thành executable Boot archive. Mô hình:

~~~text
Java source + dependencies
    ↓ compile, test...
maven-jar-plugin:jar hoặc maven-war-plugin:war
    ↓ tạo JAR/WAR cơ sở trong phase package
spring-boot-maven-plugin:repackage
    ↓ chuyển thành executable Boot JAR/WAR
verify / install / deploy nếu được yêu cầu
~~~

Nếu `repackage` và plugin tạo archive cùng được ràng buộc vào `package`, thứ tự goal phải đảm bảo **JAR/WAR được tạo trước rồi mới repackage**. Khi cấu hình thủ công, xem execution order trong effective POM và log thực tế.

### 3.2. “`repackage` có default phase” không có nghĩa luôn chạy

Đừng kết luận `mvn package` sẽ tự tạo Boot archive chỉ vì `pom.xml` khai báo dependency `spring-boot-starter-web`. Dependency là thư viện; executable packaging phụ thuộc **plugin và execution**.

**Cách A: kế thừa `spring-boot-starter-parent`.** Parent Spring Boot cung cấp execution `repackage` được cấu hình sẵn. Module ứng dụng khai báo `spring-boot-maven-plugin` trong `build/plugins` để dùng cấu hình đó; khi gọi `package`, goal repackage được đưa vào lifecycle.

**Cách B: dùng parent khác hoặc chỉ import `spring-boot-dependencies` BOM.** BOM quản lý phiên bản dependency, **không tự cung cấp toàn bộ cấu hình Maven plugin của starter parent**. Nếu muốn `repackage` chạy trong `package`, cần khai báo Maven plugin version và execution phù hợp ở POM hoặc parent hiện hành.

Đoạn minh họa cho cách B, chèn vào POM đầy đủ:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <!-- Version cần được xác định tại đây hoặc bằng pluginManagement. -->
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

Đây là **fragment XML** cần tích hợp vào POM của dự án, không phải pom.xml độc lập.

### 3.3. Maven JAR: ví dụ hoàn chỉnh để thử

Với Spring Boot 3.3.13 và Java 17, một pom.xml tối giản của ứng dụng web:

~~~xml
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
    <artifactId>demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

Tệp `src/main/java/com/example/demo/DemoApplication.java`:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

@RestController
class PingController {
    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }
}
~~~

Mã Java trên chạy được với cấu hình dependency đã cho, JDK và Maven tương thích. Nếu project có Maven wrapper:

~~~bash
./mvnw clean package
java -jar target/demo-0.0.1-SNAPSHOT.jar
~~~

Nếu không có wrapper, dùng `mvn clean package` với Maven được cài hợp lệ. Trong PowerShell Windows, dùng `.\mvnw.cmd clean package` khi wrapper có sẵn. Sau khi ứng dụng chạy trên cổng mặc định, request `GET http://localhost:8080/ping` trả response body chính xác:

~~~text
pong
~~~

Điều kiện thực thi: cổng mặc định chưa bị chiếm và không có application config ghi đè cổng/route. Kết quả build phụ thuộc JDK, repository và cấu hình môi trường.

Trong log `./mvnw package`, bạn sẽ thấy plugin tạo JAR cơ sở và goal `spring-boot:repackage` theo execution của parent. Tài liệu Spring Boot mô tả goal repackage biến archive cơ sở thành executable JAR/WAR.

### 3.4. Vì sao không chỉ gọi `spring-boot:repackage`?

So sánh:

~~~bash
./mvnw package
# Chạy Maven lifecycle tới package; tạo archive rồi tự repackage
# nếu execution đã được cấu hình.

./mvnw spring-boot:repackage
# Chỉ yêu cầu goal repackage; archive cơ sở cần tồn tại từ trước.
~~~

`repackage` **không thay thế chuỗi compile/test/package**. Khi cần chạy thủ công goal cùng việc tạo archive, tài liệu Spring Boot nêu cách gọi `mvn package spring-boot:repackage`. Nhưng khi `repackage` đã bind vào `package`, gọi thêm goal trực tiếp có thể khiến thao tác này được kích hoạt lặp; với cấu hình starter parent thông thường, chỉ `./mvnw package` là đủ.

Để chứng minh execution có hiệu lực:

~~~bash
./mvnw help:effective-pom -Doutput=target/effective-pom.xml
./mvnw package
~~~

Trong effective POM, tìm plugin `spring-boot-maven-plugin` và execution chứa goal `repackage`. Trong build log, tìm dòng goal `spring-boot:repackage` của **đúng module**. Nếu không có, kiểm tra cấu hình plugin/execution trước khi chỉnh application code.

### 3.5. Kết quả Maven: archive gốc và executable archive

Mặc định, `repackage` có thể thay thế artifact chính bằng archive executable và giữ bản archive gốc với hậu tố `.original`. Ví dụ với `demo`:

~~~text
target/
├── demo-0.0.1-SNAPSHOT.jar            # JAR Spring Boot executable
└── demo-0.0.1-SNAPSHOT.jar.original   # JAR trước khi repackage
~~~

Tên file phụ thuộc `finalName`, packaging, classifier và cấu hình plugin. Khi cấu hình classifier riêng, ví dụ `exec`, hệ build có thể giữ artifact gốc và tạo thêm `demo-0.0.1-SNAPSHOT-exec.jar`; lúc publish phải chỉ rõ artifact nào dành cho runtime.

Chú ý: `.jar.original` là cách giữ bản gốc của Maven trong trường hợp mặc định, không phải cùng quy tắc đặt tên của Gradle `-plain.jar`.

## 4. Gradle: `bootJar` và `bootWar` nằm trong task graph

### 4.1. Lifecycle task của Gradle khác Maven phase

Gradle điều phối **task và dependency giữa task**. Với Java plugin, phần vòng đời thông dụng có dạng:

~~~text
build
├── assemble       # tập hợp output đã đóng gói
└── check          # các kiểm tra; thường bao gồm test
~~~

Spring Boot Gradle Plugin phản ứng với các plugin nền tảng:

- Có Java plugin → tạo task `bootJar` kiểu `BootJar` và mặc định nối vào `assemble`.
- Có War plugin → tạo task `bootWar` kiểu `BootWar` và mặc định nối vào `assemble`.
- Task `jar` và `war` chuẩn có thể vẫn tồn tại và tạo plain archive.

Cấu hình phổ biến của một ứng dụng JAR:

~~~text
./gradlew build
    ├── assemble
    │    ├── jar       → plain JAR, nếu enabled
    │    └── bootJar   → executable Spring Boot JAR
    └── check
         └── test      → test suite, theo Java plugin
~~~

Đây là sơ đồ **quan hệ thường gặp**, không cam kết mọi build luôn có cùng task. Build logic, plugin khác, task disabled, dependency project và các chỉ thị CLI có thể thay đổi graph.

Vì vậy:

- `./gradlew bootJar` chạy những task cần thiết để tạo Boot JAR; **không mặc định chứng minh unit tests đã chạy**.
- `./gradlew assemble` dựng các artifact gắn với assemble, bao gồm Boot JAR/WAR theo cấu hình.
- `./gradlew build` thường chạy `assemble` và `check`; do đó thường vừa đóng gói vừa kiểm thử.
- `./gradlew bootWar` tương tự bootJar nhưng output là Boot WAR khi task tồn tại.

### 4.2. Gradle JAR: một build.gradle chạy được

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'demo'
~~~

Tệp `build.gradle` (Groovy DSL, ví dụ Spring Boot 3.3.13):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Tạo tệp Java `src/main/java/com/example/demo/DemoApplication.java` với mã ở ví dụ Maven. Đây là **một project Gradle riêng**; không kết hợp POM và Gradle build từ hai ví dụ như thể chúng tự chia sẻ lifecycle.

Khi có Gradle wrapper tương thích:

~~~bash
./gradlew tasks --all
./gradlew bootJar
./gradlew assemble
./gradlew build
~~~

- `tasks --all`: xem task được khai báo và phát sinh từ plugin.
- `bootJar`: tạo executable Boot JAR.
- `assemble`: tạo các output đăng ký trong lifecycle assemble.
- `build`: thêm check/test theo task graph và build logic của project.

Với dự án chưa có wrapper, dùng lệnh `gradle` đã cài phù hợp. Trên PowerShell Windows dùng `.\gradlew.bat` nếu có wrapper.

### 4.3. Plain JAR và executable Boot JAR không giống nhau

Trong Spring Boot Gradle Plugin 3.3, khi có `bootJar`, task `jar` thường dùng classifier `plain` theo convention. Sau khi build, có thể thấy:

~~~text
build/libs/
├── demo-0.0.1-SNAPSHOT.jar        # bootJar, executable
└── demo-0.0.1-SNAPSHOT-plain.jar  # jar, plain
~~~

Hai file đều là JAR hợp lệ nhưng thường có mục đích khác nhau:

- Executable Boot JAR chứa lớp ứng dụng, nested runtime JAR dependencies, Boot loader và manifest phù hợp để chạy `java -jar`.
- Plain JAR chứa classes/resources kiểu Java archive chuẩn; có thể được dùng như thư viện, không mặc nhiên có đầy đủ dependencies/Boot launcher.

Trong build Gradle Groovy DSL, nếu chính sách dự án muốn tắt task tạo plain JAR:

~~~groovy
tasks.named('jar') {
    enabled = false
}
~~~

Đây là fragment thêm vào build.gradle có Java plugin. **Không tắt bừa task `jar`** nếu library publication, nhiệm vụ khác hoặc quy trình native-image cần plain archive. Ngoài việc disable, có thể điều chỉnh classifier để hai loại artifact có tên rõ ràng hơn.

### 4.4. Gradle WAR: khi nào có `bootWar`?

`bootWar` được tạo khi áp dụng Spring Boot Gradle Plugin cùng War plugin. Ví dụ phần cần điều chỉnh của một ứng dụng Servlet:

~~~groovy
plugins {
    id 'java'
    id 'war'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'
}
~~~

Đây là **fragment** cho build.gradle, cần kết hợp vào build.gradle đầy đủ có `group`, `version`, `repositories` và cấu hình Java đã thấy ở ví dụ JAR. Khi chuyển từ JAR sang WAR, sửa các khối `plugins` và `dependencies` hiện hữu, tránh chèn nhiều khối `plugins` trùng nhau.

Ở Gradle, `providedRuntime` dùng cho dependencies của servlet container được cung cấp khi chạy trên external servlet container. Với Spring Boot executable WAR, các dependency thuộc phạm vi này được lưu ở `WEB-INF/lib-provided`, nhờ vậy WAR có thể chạy độc lập mà không gây xung đột thư viện container khi triển khai truyền thống.

Để WAR có thể được deploy vào servlet container ngoài, một class ứng dụng Servlet MVC có thể mở rộng `SpringBootServletInitializer`:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class DemoApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(SpringApplicationBuilder application) {
        return application.sources(DemoApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Nếu dùng class này, thay thế class DemoApplication của ví dụ JAR; không khai báo hai public class cùng tên trong cùng package. Có thể giữ controller `PingController` ở một file riêng để kiểm tra request. Ví dụ external WAR phù hợp với ứng dụng Servlet; không mặc định áp dụng nguyên cách này cho dự án WebFlux thuần.

Lệnh:

~~~bash
./gradlew tasks --all
./gradlew bootWar
./gradlew assemble
./gradlew build
~~~

Build WAR thường cho executable `.war` và plain `-plain.war` nếu cả `bootWar` và `war` được bật. Vì War plugin dùng cơ sở Java, **một project có thể đồng thời có `bootJar` và `bootWar`**. Kiểm tra đúng graph và artifact cần triển khai, và chỉ disable task không mong muốn sau khi xác định chính sách packaging.

## 5. Maven WAR và Gradle WAR: cùng đích, khác đường đi

### 5.1. Maven WAR

Khai báo `<packaging>war</packaging>`, có plugin WAR tạo archive cơ sở trong phase `package` và Spring Boot Maven Plugin thực hiện `repackage` nếu có execution. Sơ đồ:

~~~text
Maven: package
  ├─ maven-war-plugin:war      → regular WAR
  └─ spring-boot:repackage    → executable Boot WAR
~~~

Trong POM Maven ví dụ ở mục 3, đổi packaging và dependency cho Servlet WAR:

~~~xml
<packaging>war</packaging>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-tomcat</artifactId>
        <scope>provided</scope>
    </dependency>
</dependencies>
~~~

Đây là fragment để **thay** packaging/dependencies trong POM hoàn chỉnh, không phải POM độc lập. Vẫn cần `spring-boot-maven-plugin` đã được cấu hình. Nếu muốn deploy WAR trong servlet container bên ngoài, thêm `SpringBootServletInitializer` như ví dụ Gradle WAR và kiểm tra version servlet container tương thích với Spring Boot sử dụng.

### 5.2. Gradle WAR

Gradle chạy task `bootWar` trực tiếp; không gọi `maven-war-plugin:war` và không có phase Maven `package`. Task `assemble` được nối để tạo executable WAR; task `build` thường bao gồm `assemble` và `check`.

Sự khác nhau quan trọng:

| Nhu cầu | Maven | Gradle |
| --- | --- | --- |
| Đóng gói executable JAR | `./mvnw package` có goal `repackage` đúng execution | `./gradlew bootJar` hoặc `./gradlew assemble/build` |
| Đóng gói executable WAR | `packaging=war`, WAR plugin rồi `repackage` | War plugin, task `bootWar` |
| Xem vị trí thực thi | Effective POM, lifecycle log, execution ID | `tasks --all`, `--dry-run`, task graph và log |
| Kiểm thử trong build đầy đủ | Lifecycle tới `package` thường có test, theo plugin/bỏ qua test | `build` thường có `check/test`; `bootJar`/`bootWar` trực tiếp không đảm bảo test |
| Artifact thường | `target/*.jar` hoặc `target/*.war` | `build/libs/*.jar` hoặc `build/libs/*.war` |

Không xem biểu hiện “BUILD SUCCESSFUL” hoặc “BUILD SUCCESS” đơn lẻ là bằng chứng đã chạy đúng mọi test hay đã tạo đúng loại executable: phải kiểm tra goals/tasks và output.

## 6. Archive bên trong: nhận ra plain và executable

Executable Spring Boot JAR thường có:

~~~text
META-INF/MANIFEST.MF
BOOT-INF/classes/               # application classes/resources
BOOT-INF/lib/                   # nested runtime JAR dependencies
org/springframework/boot/loader/...
~~~

Executable Spring Boot WAR thường có:

~~~text
META-INF/MANIFEST.MF
WEB-INF/classes/                # application classes/resources
WEB-INF/lib/                    # runtime libraries
WEB-INF/lib-provided/           # provided libraries, nếu có
org/springframework/boot/loader/...
~~~

Trong archive executable, manifest thường có `Main-Class` là launcher của Spring Boot và `Start-Class` là entrypoint ứng dụng. Vì vậy regular JAR chỉ chứa classes/resources không tự có cùng hành vi với executable JAR, dù cùng hậu tố file.

Dùng JDK tool `jar` để liệt kê nội dung:

~~~bash
# Maven JAR ví dụ:
jar tf target/demo-0.0.1-SNAPSHOT.jar

# Gradle JAR ví dụ:
jar tf build/libs/demo-0.0.1-SNAPSHOT.jar

# Gradle WAR ví dụ:
jar tf build/libs/demo-0.0.1-SNAPSHOT.war
~~~

Chỉ dùng lệnh ứng với loại artifact thực tế đang có; output filename thay đổi được qua `finalName`/classifier/archiveFileName và module path. Tìm `BOOT-INF/lib` hoặc `WEB-INF/lib` và loader; cuối cùng xác minh chạy `java -jar` với bản executable trong môi trường runtime.

## 7. Dự án nhiều module: chỉ đóng gói Boot tại ứng dụng

Ví dụ:

~~~text
root/
├── common/          # thư viện chia sẻ
├── persistence/     # thư viện dữ liệu
└── api-service/     # ứng dụng Spring Boot có main class
~~~

Không nên áp dụng executable packaging đồng loạt:

- Maven root aggregator dùng `packaging=pom`, module thư viện có thể tạo plain JAR, module `api-service` mới dùng `repackage` để tạo Boot executable. Nếu parent nội bộ áp dụng plugin cho tất cả module, kiểm tra module không có entrypoint có bị gọi `repackage` vô ý không.
- Gradle module `common` và `persistence` có thể dùng `java-library`, module `api-service` áp dụng Spring Boot plugin để có `bootJar` hoặc `bootWar`. Áp dụng Boot plugin đại trà có thể gây lỗi không tìm thấy main class và làm sai artifact cho thư viện.

Lệnh minh họa cho dự án **thực sự** có module tên `api-service`:

~~~bash
# Maven multi-module:
./mvnw -pl api-service -am package

# Gradle multi-project:
./gradlew :api-service:bootJar
./gradlew :api-service:build
~~~

`-am` của Maven chọn thêm các module cần để build module được chọn; Gradle dùng task path của subproject. Không suy ra tên module hay chính sách publish chỉ từ việc thấy file JAR xuất hiện.

## 8. Xác minh lifecycle bằng bằng chứng thay vì đoán

### 8.1. Maven

Chạy trong đúng Maven root:

~~~bash
./mvnw help:effective-pom -Doutput=target/effective-pom.xml
./mvnw package
# Nếu quy trình cần verify:
./mvnw verify
~~~

Đối chiếu 5 yếu tố:

1. Packaging trong POM của module là `jar`, `war` hay `pom`?
2. Effective POM có `spring-boot-maven-plugin` và execution gắn `repackage` không?
3. Log `package` có goal jar/war trước goal `repackage` không?
4. File target có executable archive và bản gốc `.original`/classifier không?
5. Mục tiêu `install`/`deploy` nếu dùng có publish đúng archive mà runtime cần không?

Khi cần chẩn đoán sâu, có thể dùng Maven debug log nhưng tránh đưa credential/settings nhạy cảm ra môi trường chia sẻ. Kiểm tra lỗi thực tế trước khi đổi plugin.

### 8.2. Gradle

Chạy trong Gradle root, chọn đúng module nếu nhiều module:

~~~bash
./gradlew tasks --all
./gradlew bootJar --dry-run
./gradlew build --dry-run
./gradlew build
~~~

Nếu project chỉ làm WAR, thay `bootJar` bằng `bootWar`. Lệnh `bootWar` ở project không áp dụng War plugin có thể báo task not found; đó không phải lỗi packaging của project JAR.

`--dry-run` giúp thấy task được schedule theo graph mà không thực thi task actions; **không tạo archive mới và không chứng minh test pass**. Chạy thật `build`/`bootJar`/`bootWar` để xác nhận output.

Phân biệt trạng thái Gradle:

- Task được liệt kê trong graph.
- Task action thực sự chạy.
- Task bị `UP-TO-DATE` hoặc `FROM-CACHE`.
- Artifact hiện diện và có thể chạy.

Một task xuất hiện trong graph không bảo đảm action vừa được thực thi; một artifact có sẵn trong thư mục build có thể là output từ lần chạy trước. Khi cần điều tra, kiểm tra timestamp/log và clean build theo quy trình thích hợp.

## 9. Lỗi phổ biến và cách tìm nguyên nhân

| Triệu chứng hoặc suy luận sai | Cách xác minh và xử lý |
| --- | --- |
| `mvn package` ra JAR nhưng `java -jar` báo thiếu launcher | Kiểm tra goal `repackage` có được bind/đã chạy chưa, xác định file gốc so với executable |
| Có Spring Boot starter thì `repackage` chắc chắn chạy | Sai: starter là dependency; cần Maven plugin/execution |
| Gọi `mvn spring-boot:repackage` trước khi tạo archive | Goal cần JAR/WAR cơ sở; chạy lifecycle `package` và execution phù hợp |
| Repackage báo không tìm thấy source artifact | Kiểm tra goal tạo jar/war có chạy trước và packaging của module đúng không |
| `./gradlew bootJar` thành công nhưng tests chưa chạy | `bootJar` không thay thế `build`/`check`; kiểm tra graph hoặc chạy test riêng |
| `./gradlew build` không tạo Boot archive | Kiểm tra plugin có được áp dụng, task enabled, `assemble` phụ thuộc task nào và subproject nào |
| Thấy `-plain.jar` nên tưởng đây là Boot executable | `-plain.jar` thường là plain archive; xem `BOOT-INF`/manifest và chọn output của `bootJar` |
| Có task `bootWar` nhưng muốn chỉ xuất WAR | Kiểm tra cả `bootJar` do War/Java plugin và cấu hình task cần disable, rồi xem artifact cuối |
| Triển khai WAR vào external servlet container bị lỗi | Kiểm tra Servlet WAR, `SpringBootServletInitializer`, provided servlet runtime, container compatibility |
| Module library không có main class nên `bootJar` lỗi | Xem lại việc áp dụng Spring Boot plugin; library có thể chỉ cần plain `jar` |
| CI phát hành sai JAR/WAR | Chỉ rõ module, task/goal, classifier và output path; không lấy file đầu tiên khớp `*.jar` |
| Maven và Gradle cùng tồn tại trong repo | Đối chiếu nguồn build được duy trì trong CI và repo; không tự xem hai hệ build là bước nối tiếp |

Không xử lý bằng cách xóa thư mục cache hàng loạt hoặc thêm bừa plugin. Trước hết phải xác định đúng **module**, **goal/task**, **thứ tự thực thi** và **artifact**.

## 10. Thực hành xác minh vị trí từng thao tác

Chọn một ứng dụng Spring Boot có entrypoint và wrapper hợp lệ. Chỉ chạy workflow của build tool đang được dự án sử dụng.

### Bài thực hành Maven

1. Đọc POM, xác định `packaging`, parent và Spring Boot Maven Plugin.
2. Dùng effective POM chỉ ra execution `repackage` có được bind vào lifecycle không.
3. Chạy `./mvnw clean package`; trong log xác nhận archive cơ sở có trước goal `repackage`.
4. Quan sát thư mục target, giải thích file executable và archive nguyên gốc nếu có.
5. Dùng `jar tf` xem cấu trúc và `java -jar` khởi chạy ứng dụng.
6. Trả lời: nếu đổi lệnh thành `./mvnw verify` thì `repackage` có còn được chạy không, và vì sao?

### Bài thực hành Gradle

1. Đọc các plugin trong build.gradle(.kts); xác định project dùng Java, War hay cả hai.
2. Chạy `./gradlew tasks --all` để chứng minh task `bootJar`/`bootWar` tồn tại.
3. Chạy `./gradlew build --dry-run` để tìm đường dẫn từ `build` tới `assemble` và task executable packaging.
4. Chạy `./gradlew clean build`, đối chiếu log với graph và kiểm tra các file dưới build/libs.
5. Phân biệt output plain với output executable và xác minh bằng `jar tf`.
6. So sánh với `./gradlew bootJar --dry-run` hoặc `bootWar --dry-run`. Giải thích tại sao gọi riêng task đóng gói không phải bằng chứng chạy test suite.

### Câu hỏi tự kiểm tra

**1.** Tại sao Maven dùng Spring Boot BOM mà không dùng starter parent có thể không chạy `repackage` trong phase `package`?

**Đáp án:** BOM quản lý dependency versions, còn binding goal đến từ plugin execution. Phải cấu hình execution tại module/parent phù hợp.

**2.** Tại sao Gradle có cả `jar` và `bootJar`?

**Đáp án:** Java plugin cung cấp task plain JAR, còn Spring Boot plugin bổ sung task tạo executable JAR; convention classifier giúp không ghi đè file.

**3.** `./gradlew bootWar` thành công có đồng nghĩa `./gradlew test` đã chạy không?

**Đáp án:** Không. Xem task dependency graph; chạy `build`/`test` theo chính sách kiểm thử dự án.

**4.** Có cần gọi `repackage` rồi `bootJar` mới có executable archive không?

**Đáp án:** Không. Maven và Gradle là hai cơ chế riêng. Chọn workflow tương ứng với build tool được dự án sử dụng.

**Tiêu chí đạt:** bạn trình bày đúng từ source code đến regular archive/executable archive đối với Maven và từ Gradle task graph đến executable JAR/WAR đối với Gradle; đồng thời trưng được log, task/goal và artifact thực tế để chứng minh.

## 11. Tài liệu chính thức tham khảo

- Spring Boot 3.3 — Maven Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot 3.3 — Maven Using the Plugin: https://docs.spring.io/spring-boot/3.3/maven-plugin/using.html
- Spring Boot 3.3 — Gradle Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html

Ví dụ ở đây dùng Spring Boot 3.3 và Java 17 để minh họa. Trong dự án thật, phải đối chiếu tài liệu theo **phiên bản Spring Boot, Maven/Gradle plugin và JDK thực tế**, vì hành vi mặc định có thể thay đổi qua các phiên bản.
